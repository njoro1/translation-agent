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
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
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

# id(proc) -> stderr capture file object for the last-started server. When a
# server exits immediately (e.g. an unsupported quantization or a bad flag), the
# captured stderr is surfaced to the user instead of being discarded.
_PROC_STDERR: dict[int, object] = {}


def _read_proc_stderr(proc: subprocess.Popen) -> str:
    """Read and return the captured stderr for `proc`, if any."""
    fh = _PROC_STDERR.pop(id(proc), None)
    if fh is None:
        return ""
    path = getattr(fh, "name", "")
    try:
        fh.flush()
        fh.seek(0)
        text = fh.read()
        return text if isinstance(text, str) else text.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - best effort
        return ""
    finally:
        try:
            fh.close()
        except Exception:
            pass
        if path:
            with contextlib.suppress(Exception):
                os.unlink(path)


def _summarize_server_stderr(text: str) -> str | None:
    """Return a concise actionable hint for common llama-server startup failures.

    Returns ``None`` when the stderr doesn't match a known pattern, so callers
    can fall back to showing the raw captured output.
    """
    if not text:
        return None
    low = text.lower()
    # GGUF corruption: tensor offset mismatch / failed to read tensor data.
    if "failed to read tensor data" in low or "tensor data" in low and "offset" in low:
        return (
            "The GGUF model file appears to be corrupt or truncated. "
            "Re-download it and replace the file:\n"
            "  - GUI: Settings → Download models (or delete the file and retry)\n"
            "  - Manual: https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q8_0.gguf"
        )
    # Missing / unsupported quantization kernel.
    if "stq" in low or "unsupported quantization" in low or "quantization" in low:
        return (
            "The bundled llama-server may not support this quantization. "
            "Ensure you're using the app's bundled llama-server, or try a "
            "different GGUF variant."
        )
    return None


def _cleanup_proc_stderr(proc: subprocess.Popen) -> None:
    """Drop the captured stderr reference without reading it."""
    fh = _PROC_STDERR.pop(id(proc), None)
    if fh is None:
        return
    path = getattr(fh, "name", "")
    try:
        fh.close()
    except Exception:
        pass
    if path:
        with contextlib.suppress(Exception):
            os.unlink(path)


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
    # A client machine may get llama-server.exe copied next to the app rather
    # than inside vendor\llama — accept that layout too before giving up.
    for base in _resource_base_dirs():
        flat = os.path.join(base, exe)
        if os.path.isfile(flat):
            return flat
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


def _models_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/v1/models"


def server_serves_model(
    host: str, port: int, model_path: str, timeout: float = 3.0
) -> bool:
    """True if the server on host:port is an OpenAI-compatible llama-server
    currently serving the model file `model_path`.

    This is the authoritative check used before *reusing* a running server.
    ``server_alive`` only checks ``/health``, which any HTTP service could
    answer; here we hit ``/v1/models`` and confirm the advertised model id
    matches the requested GGUF. A server that answers ``/health`` but returns
    404/405/times out on ``/v1/models`` is treated as *not reusable* so we do
    not blind-reuse a stale or foreign server.
    """
    try:
        with urllib.request.urlopen(_models_url(host, port), timeout=timeout) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - any failure means "not a usable llama-server"
        return False
    ids = [str(m.get("id", "")) for m in data.get("data", []) if isinstance(m, dict)]
    base = os.path.basename(model_path)
    stem = os.path.splitext(base)[0]
    return bool(ids) and (base in ids or stem in ids)


def _port_free(host: str, port: int) -> bool:
    """True if nothing is listening on host:port (fast TCP connect probe)."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return False
    except OSError:
        return True


def _find_free_port(host: str, start_port: int, max_attempts: int = 50) -> int:
    """Return the first free port at/after `start_port` (a TCP connect probe)."""
    for offset in range(max_attempts):
        candidate = start_port + offset
        if _port_free(host, candidate):
            return candidate
    raise RuntimeError(
        f"Could not find a free port starting at {start_port} "
        f"(tried {max_attempts}). Close the other local servers and retry."
    )


def _start_process(cmd: list[str]) -> subprocess.Popen:
    """Start a hidden background process (no console window) on Windows.

    stderr is captured to a temporary file so that, if the server exits
    immediately (e.g. an unsupported quantization or bad flag), the diagnostic
    message can be surfaced to the user instead of being lost. The file is kept
    open for the lifetime of a healthy server and cleaned up on termination.
    """
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    stderr_file = tempfile.NamedTemporaryFile(
        mode="w+", suffix="_llama.stderr.log", delete=False
    )
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=stderr_file,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    # Track the capture file so it can be read on failure and cleaned up on exit.
    proc._stderr_file = stderr_file  # type: ignore[attr-defined]
    _PROC_STDERR[id(proc)] = stderr_file
    return proc


def start_server(
    model_path: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    n_ctx: int = DEFAULT_N_CTX,
    n_gpu_layers: int = N_GPU_LAYERS,
    *,
    threads: int = 0,
    mlock: bool = False,
) -> subprocess.Popen:
    """Launch a bundled llama-server against `model_path` and return the process.

    Raises RuntimeError if the bundled binary is missing or the model path is
    invalid. The returned process is tracked so it is cleaned up on exit.

    Optional keyword args:
        threads: If > 0, pass ``-t <threads>`` to llama-server. 0 = let
            llama.cpp decide (default).
        mlock: If True, pass ``--mlock`` to lock the model in RAM.
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

    # Optional flags — tried first, then retried without if the server rejects them.
    optional_flags: list[str] = []
    if threads > 0:
        optional_flags += ["-t", str(threads)]
    if mlock:
        optional_flags += ["--mlock"]

    key = (os.path.abspath(model_path), host, int(port))
    proc = _start_with_fallback_flags(cmd, optional_flags, key)
    return proc


def _start_with_fallback_flags(
    base_cmd: list[str],
    optional_flags: list[str],
    key: tuple,
) -> subprocess.Popen:
    """Start the server with optional flags; retry without them on early exit.

    Strategy:
        1. Build command with requested optional flags.
        2. Start process.
        3. If the process exits within 2 seconds, retry without optional flags.
        4. Log clearly which path was taken.
    """
    if not optional_flags:
        proc = _start_process(base_cmd)
        _ACTIVE[key] = proc
        return proc

    full_cmd = base_cmd + optional_flags
    proc = _start_process(full_cmd)

    # Give the process a moment to see if it rejects the flags.
    time.sleep(2.0)
    if proc.poll() is not None:
        flag_names = " ".join(optional_flags)
        print(
            f"[local] Server failed with optional flags ({flag_names}); "
            f"retrying without them",
            flush=True,
        )
        try:
            _popen_terminate(proc)
        except Exception:  # noqa: BLE001
            pass
        proc = _start_process(base_cmd)

    _ACTIVE[key] = proc
    return proc


def warmup_local_server(
    base_url: str,
    model: str,
    *,
    timeout: float = 30.0,
) -> bool:
    """Send a tiny warmup request to the local server.

    Purpose: initialize the model, allocate caches, reduce first-request
    latency, and make progress reporting more predictable.

    Returns True if the warmup request succeeded (a response was received),
    False otherwise. A warmup failure is **not** fatal — the caller should
    log a warning and continue.
    """
    import json

    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "1. test"}],
        "temperature": 0.1,
        "max_tokens": 8,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                print("[local] Warmup request sent to llama-server", flush=True)
                return True
    except Exception as exc:  # noqa: BLE001
        print(f"[local] Warmup request failed; continuing anyway ({exc})", flush=True)
        return False
    print("[local] Warmup request failed; continuing anyway", flush=True)
    return False


def ensure_local_server(
    model_path: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    n_ctx: int = DEFAULT_N_CTX,
    n_gpu_layers: int = N_GPU_LAYERS,
    timeout: float = 180.0,
    *,
    threads: int = 0,
    mlock: bool = False,
) -> tuple[subprocess.Popen | None, str, int]:
    """Make sure a server for `model_path` is up; start one if needed.

    Returns `(process, how, port)` where `how` is either ``"reuse"`` (a server
    already serving the **same model** was found on ``host:port``), ``"reused-on"``
    (a server was found on a *different* port serving the same model), or
    ``"started"`` (this call launched a new server). ``port`` is the actual port
    the server is listening on (may differ from the requested one if it was
    occupied by a different service).

    If `process` is None the server was reused (owned elsewhere).

    Optional keyword args:
        threads: If > 0, pass ``-t <threads>`` to llama-server.
        mlock: If True, pass ``--mlock`` to lock the model in RAM.

    Raises RuntimeError if the server cannot be brought up within `timeout`.
    """
    port = int(port)

    # 1. Reuse only if the running server actually serves *our* model.
    #    A blind /health check is too permissive — a stale or foreign server
    #    can answer 200 on /health but 405 on /v1/chat/completions, causing
    #    silent hangs.
    if server_alive(host, port):
        if server_serves_model(host, port, model_path):
            return None, "reuse", port

    # 2. Port is occupied by a wrong/stale server (or not alive). If it's
    #    occupied, find a free port; otherwise use the requested one.
    if _port_free(host, port):
        target_port = port
    else:
        target_port = _find_free_port(host, port)
        print(
            f"[local] Port {port} is busy with a different server; "
            f"starting on {target_port} instead.",
            flush=True,
        )

    # Check if the right model is already running on the discovered port
    # (unlikely but possible if the user has multiple llama-servers).
    if server_alive(host, target_port) and server_serves_model(host, target_port, model_path):
        return None, "reused-on", target_port

    proc = None
    try:
        proc = start_server(
            model_path, host, target_port, n_ctx, n_gpu_layers,
            threads=threads, mlock=mlock,
        )
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001 - wrap launch failures clearly
        raise RuntimeError(f"Failed to start llama-server: {exc}") from exc

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server_alive(host, target_port):
            return proc, "started", target_port
        # If the process died before reporting ready, surface it immediately.
        if proc.poll() is not None:
            rc = proc.returncode
            stderr_text = _read_proc_stderr(proc)
            parts = [
                f"llama-server exited before becoming ready (rc={rc}).",
                "The model may be corrupt or unsupported by this build.",
            ]
            hint = _summarize_server_stderr(stderr_text)
            if hint:
                parts.append(hint)
            elif stderr_text.strip():
                parts.append("Server stderr:")
                indented = "\n".join(
                    f"  {ln}" for ln in stderr_text.strip().splitlines()
                )
                parts.append(indented)
            raise RuntimeError("\n".join(parts))
        time.sleep(1.0)
    # Timed out waiting for readiness.
    terminate_server(model_path, host, target_port)
    raise RuntimeError(
        f"Timed out waiting for llama-server to load the model at "
        f"{_health_url(host, target_port)}. It may be too slow on this CPU."
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
    finally:
        _cleanup_proc_stderr(proc)


def shutdown_servers() -> None:
    """Terminate every llama-server this process started."""
    for key, proc in list(_ACTIVE.items()):
        if proc.poll() is None:
            _popen_terminate(proc)
        else:
            _cleanup_proc_stderr(proc)
        del _ACTIVE[key]


# Ensure background servers are cleaned up if the host process exits (CLI or GUI).
atexit.register(shutdown_servers)


def terminate_server(
    model_path: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
) -> None:
    """Stop a specific tracked server (no-op if it isn't running)."""
    key = (os.path.abspath(model_path), host, int(port))
    proc = _ACTIVE.pop(key, None)
    if proc is not None:
        if proc.poll() is None:
            _popen_terminate(proc)
        else:
            _cleanup_proc_stderr(proc)

