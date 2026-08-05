"""Launch a local, OpenAI-compatible llama.cpp server from a bundled `llama-server`.

Used by `translate.py --local --local-model <file.gguf>`. The user supplies (or
downloads in the GUI) a translation GGUF; this module resolves the **bundled**
CPU-only `llama-server.exe` that ships with the app and runs it against that
model, so nobody has to manually start a llama.cpp server beforehand. The server
speaks the OpenAI `/v1` API, which the rest of the translator already talks to.

The server is deliberately CPU-only (no `-ngl` GPU offload) for full
compatibility with machines that have no GPU. The model file is loaded once when
the server starts.
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

# CPU-only build; never offload layers to a GPU.
N_GPU_LAYERS = 0
DEFAULT_N_CTX = 4096
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080

# (model_path, host, port) -> Popen for every server we started this session, so
# we can terminate them on exit instead of leaking background processes.
_ACTIVE: dict[tuple[str, str, int], subprocess.Popen] = {}


def _resource_base_dirs() -> list[str]:
    """Directories that may hold bundled resources (binaries, models).

    When frozen by PyInstaller, data and binaries land under `sys._MEIPASS`;
    next-to-the-exe (or repo root when running from source) is secondary.
    """
    dirs: list[str] = []
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        dirs.append(bundle_dir)
    dirs.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    return dirs


def _exe_name(tool: str) -> str:
    """Add .exe on Windows so bundled tools resolve by exact filename."""
    return tool + ".exe" if sys.platform.startswith("win") else tool


def _resolve_bundled(binary_name: str, subdir: str) -> str | None:
    """Return the bundled path for `binary_name` under vendor/<subdir>, if any."""
    for base in _resource_base_dirs():
        candidate = os.path.join(base, "vendor", subdir, binary_name)
        if os.path.exists(candidate):
            return candidate
    return None


def resolve_llama_server(name: str = "llama-server") -> str | None:
    """Return a usable llama-server executable, preferring the bundled copy.

    Searches `_MEIPASS/vendor/llama` and next to the exe/repo root first (where
    the PyInstaller build unpacks it), then falls back to whatever is on PATH so
    a manually installed llama.cpp still works.
    """
    exe = _exe_name(name)
    bundled = _resolve_bundled(exe, "llama")
    if bundled:
        return bundled
    found = shutil.which(name)
    return found if found else None


def _health_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/health"


def server_alive(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """True if a llama.cpp server is already responding on host:port."""
    try:
        with urllib.request.urlopen(_health_url(host, port), timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _start_process(cmd: list[str]) -> subprocess.Popen:
    """Start a hidden background process (no console window) on Windows."""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def start_server(
    model_path: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    n_ctx: int = DEFAULT_N_CTX,
    n_gpu_layers: int = N_GPU_LAYERS,
) -> subprocess.Popen:
    """Launch a bundled llama-server against `model_path` and return the process.

    Raises RuntimeError if the bundled binary is missing or the model path is
    invalid. The returned process is tracked so it is cleaned up on exit.
    """
    server_bin = resolve_llama_server()
    if not server_bin:
        raise RuntimeError(
            "Could not find a llama-server executable. The bundled "
            "vendor\\llama\\llama-server.exe is missing."
        )
    if not os.path.exists(model_path):
        raise RuntimeError(
            f"Local translation model not found: {model_path}. "
            "Download it in Settings or point the field at your GGUF file."
        )

    cmd = [
        server_bin,
        "-m", model_path,
        "--host", str(host),
        "--port", str(port),
        "--ctx-size", str(n_ctx),
        "-ngl", str(n_gpu_layers),  # 0 -> CPU only
    ]
    key = (os.path.abspath(model_path), host, int(port))
    proc = _start_process(cmd)
    _ACTIVE[key] = proc
    return proc


def ensure_local_server(
    model_path: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    n_ctx: int = DEFAULT_N_CTX,
    n_gpu_layers: int = N_GPU_LAYERS,
    timeout: float = 180.0,
) -> tuple[subprocess.Popen | None, str]:
    """Make sure a server for `model_path` is up; start one if needed.

    Returns `(process, how)` where `how` is either "reuse" (a server was already
    listening) or "started" (this call launched it). If `process` is None the
    server was reused (owned elsewhere).

    Raises RuntimeError if the server cannot be brought up within `timeout`.
    """
    if server_alive(host, port):
        return None, "reuse"

    proc = None
    try:
        proc = start_server(model_path, host, port, n_ctx, n_gpu_layers)
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001 - wrap launch failures clearly
        raise RuntimeError(f"Failed to start llama-server: {exc}") from exc

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server_alive(host, port):
            return proc, "started"
        # If the process died before reporting ready, surface it immediately.
        if proc.poll() is not None:
            rc = proc.returncode
            raise RuntimeError(
                f"llama-server exited before becoming ready (rc={rc}). "
                "The model may be corrupt or unsupported by this build."
            )
        time.sleep(1.0)
    # Timed out waiting for readiness.
    terminate_server(model_path, host, port)
    raise RuntimeError(
        f"Timed out waiting for llama-server to load the model at "
        f"{_health_url(host, port)}. It may be too slow on this CPU."
    )


def _popen_terminate(proc: subprocess.Popen) -> None:
    """Best-effort terminate a server process tree."""
    try:
        if sys.platform.startswith("win"):
            # Whole tree: llama-server may have forked helper processes.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            proc.terminate()
    except Exception:  # noqa: BLE001 - best effort only
        pass


def shutdown_servers() -> None:
    """Terminate every llama-server this process started."""
    for key, proc in list(_ACTIVE.items()):
        if proc.poll() is None:
            _popen_terminate(proc)
        del _ACTIVE[key]


# Ensure background servers are cleaned up if the host process exits (CLI or GUI).
atexit.register(shutdown_servers)


def terminate_server(
    model_path: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
) -> None:
    """Stop a specific tracked server (no-op if it isn't running)."""
    key = (os.path.abspath(model_path), host, int(port))
    proc = _ACTIVE.pop(key, None)
    if proc is not None and proc.poll() is None:
        _popen_terminate(proc)

