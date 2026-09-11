"""Locating and running yt-dlp — from source *and* from a frozen executable.

Normally the app shells out to ``yt-dlp`` (falling back to ``python -m yt_dlp``)
and streams its output, which is what :func:`run_ytdlp` does by default.

A PyInstaller one-file executable cannot do that: ``sys.executable`` is the app
itself, so ``python -m yt_dlp`` is impossible, and an external ``yt-dlp.exe``
cannot be assumed to exist on the end user's machine. For that case
:func:`run_ytdlp` calls :func:`yt_dlp.main` *inside* this process and captures
its output by temporarily swapping in a sink object for ``sys.stdout`` /
``sys.stderr``.

Staying on yt-dlp's CLI code path is deliberate: the output is byte-identical to
the subprocess version (the same ``[download] 42%``, ``[info]``, ``Destination:``
and ``Merging formats into`` lines), so all existing parsing keeps working — and
a ``--windowed`` build, where ``sys.stdout`` is ``None``, works too instead of
crashing on the first write.

Deliberately free of intra-package imports so both :mod:`src.fetch_subs` and
:mod:`src.youtube_media` can use it without an import cycle.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time

# Hide the console window that would otherwise flash up on every call.
_SUBPROCESS_CREATION_FLAGS = 0
if os.name == "nt":
    _SUBPROCESS_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

_TRUTHY = ("1", "true", "yes", "on")

# yt-dlp is not re-entrant: ``main()`` flips process-wide globals ("IN_CLI") and
# writes to the redirected ``sys.stdout``. Serialising in-process calls keeps two
# concurrent downloads from interleaving their output into one stream.
_INPROC_LOCK = threading.RLock()


class YtdlpError(RuntimeError):
    """Base class for "yt-dlp could not be run" failures."""

    kind = "unavailable"

    def __init__(self, message: str = "", output: str = "") -> None:
        super().__init__(message or self.kind)
        self.output = output


class YtdlpUnavailable(YtdlpError):
    """yt-dlp is neither installed nor bundled into this build."""

    kind = "unavailable"


class YtdlpTimeout(YtdlpError):
    """yt-dlp did not finish within the allotted time."""

    kind = "timeout"


class YtdlpFailed(YtdlpError):
    """yt-dlp ran but exited with a non-zero status."""

    kind = "failed"

    def __init__(self, code: int, output: str = "") -> None:
        super().__init__(f"yt-dlp exited with status {code}", output)
        self.code = code


class _Cancelled(Exception):
    """Internal: raised inside yt-dlp when the caller asked it to stop."""


class _LineSink:
    """Minimal writable stream that forwards yt-dlp's output one line at a time.

    yt-dlp writes through ``write_string()``, which only needs ``write()`` and
    ``flush()`` and degrades gracefully when ``mode``/``buffer`` are absent. It
    is also the cancellation point: without a subprocess there is nothing to
    terminate, so an abort is raised from inside yt-dlp's own write call. That
    unwinds the download (yt-dlp may turn it into an error report, which is
    fine — the caller already knows ``cancel_check()`` is true).
    """

    def __init__(self, on_line=None, cancel_check=None, collector=None) -> None:
        self._on_line = on_line
        self._cancel_check = cancel_check
        self._collector = collector
        self._buf = ""

    def write(self, s) -> int:
        if isinstance(s, bytes):
            s = s.decode("utf-8", "replace")
        if self._cancel_check is not None and self._cancel_check():
            raise _Cancelled()
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._emit(line.rstrip("\r"))
        return len(s)

    def _emit(self, line: str) -> None:
        if self._collector is not None:
            self._collector.append(line)
        if self._on_line is not None and self._on_line(line) is False:
            raise _Cancelled()

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        """Pretend not to be a terminal so yt-dlp skips ANSI/VT formatting."""
        return False

    def drain(self) -> None:
        """Emit a trailing partial line (yt-dlp's last write may lack ``\\n``)."""
        rest, self._buf = self._buf, ""
        if rest.strip():
            self._emit(rest.rstrip("\r"))


def is_frozen() -> bool:
    """True when running as a PyInstaller (or similar) bundled executable."""
    return bool(getattr(sys, "frozen", False))


def _explicit_exe() -> str | None:
    """A yt-dlp executable pinned by the operator via ``YT_DLP_BIN``."""
    env = os.environ.get("YT_DLP_BIN", "").strip()
    if env and (shutil.which(env) or os.path.exists(env)):
        return env
    return None


def yt_dlp_cmd() -> list[str]:
    """Resolve the yt-dlp command prefix used to *spawn* yt-dlp.

    Order: the ``YT_DLP_BIN`` environment variable (absolute path or command
    name), ``yt-dlp`` on PATH, then ``python -m yt_dlp``.

    When :func:`use_inprocess` is true this prefix is never executed — the
    in-process runner strips it and calls :func:`yt_dlp.main` directly.
    """
    exe = _explicit_exe() or shutil.which("yt-dlp")
    if exe:
        return [exe]
    return [sys.executable, "-m", "yt_dlp"]


def use_inprocess() -> bool:
    """True when yt-dlp must run inside this process rather than as a child."""
    if os.environ.get("YT_DLP_INPROC", "").strip().lower() in _TRUTHY:
        return True
    # A frozen app has no interpreter to spawn and cannot rely on an external
    # yt-dlp.exe being installed, so the bundled copy is the only option —
    # unless the operator pinned one explicitly with YT_DLP_BIN.
    return is_frozen() and _explicit_exe() is None


def yt_dlp_available() -> bool:
    """True when yt-dlp can actually be invoked in this environment."""
    if use_inprocess():
        try:
            import yt_dlp  # noqa: F401
        except Exception:  # noqa: BLE001
            return False
        return True
    return _explicit_exe() is not None or shutil.which("yt-dlp") is not None


def _strip_launcher(cmd: list[str]) -> list[str]:
    """Drop the executable/"python -m" prefix, leaving yt-dlp's own arguments.

    The caller builds ``yt_dlp_cmd() + [args]``; in-process we need just
    ``[args]``. Matching the launcher tokens (rather than assuming a count) keeps
    this correct for all three resolutions performed by :func:`yt_dlp_cmd`.
    """
    i = 0
    for token in cmd:
        s = str(token)
        base = os.path.basename(s).lower()
        if s in ("-m", "yt_dlp") or (s and s == sys.executable) or base.startswith("yt-dlp"):
            i += 1
            continue
        break
    return list(cmd[i:])


def _exit_code(code) -> int:
    """Normalise ``SystemExit.code`` (None / int / message string) to an int."""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    try:
        return int(code)
    except (TypeError, ValueError):
        return 1


def _run_inprocess(cmd: list[str], sink: _LineSink) -> int:
    """Run ``yt_dlp.main()`` in this process, streaming output into ``sink``."""
    try:
        import yt_dlp
    except Exception as exc:  # noqa: BLE001
        raise YtdlpUnavailable(f"yt-dlp is not available: {exc}") from exc

    argv = _strip_launcher(list(cmd))
    saved = (sys.stdout, sys.stderr)
    rc = 0
    try:
        with _INPROC_LOCK:
            sys.stdout = sys.stderr = sink
            try:
                yt_dlp.main(argv)
            except SystemExit as exc:
                rc = _exit_code(exc.code)
            except _Cancelled:
                rc = 1
            finally:
                sys.stdout, sys.stderr = saved
    finally:
        sys.stdout, sys.stderr = saved
        try:
            sink.drain()
        except _Cancelled:
            pass
    return rc


def _terminate(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def _run_subprocess(
    cmd: list[str],
    on_line=None,
    cancel_check=None,
    proc_ref: dict | None = None,
    env: dict | None = None,
) -> int:
    proc = subprocess.Popen(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_SUBPROCESS_CREATION_FLAGS,
        env=env,
    )
    if proc_ref is not None:
        proc_ref["proc"] = proc
    if proc.stdout is not None:
        for line in proc.stdout:
            if cancel_check is not None and cancel_check():
                _terminate(proc)
                break
            if on_line is not None and on_line(line.rstrip("\r\n")) is False:
                _terminate(proc)
                break
    return proc.wait()


def run_ytdlp(
    cmd: list[str],
    on_line=None,
    cancel_check=None,
    proc_ref: dict | None = None,
    env: dict | None = None,
) -> int:
    """Run yt-dlp, handing each output line to ``on_line``.

    ``on_line(line)`` may return ``False`` to abort. Returns yt-dlp's exit code
    (0 on success). Dispatches to the subprocess or in-process implementation
    depending on :func:`use_inprocess`.
    """
    if use_inprocess():
        return _run_inprocess(cmd, _LineSink(on_line=on_line, cancel_check=cancel_check))
    return _run_subprocess(
        cmd, on_line=on_line, cancel_check=cancel_check, proc_ref=proc_ref, env=env
    )


def _deadline_check(timeout):
    """A ``cancel_check`` that fires once ``timeout`` seconds have elapsed.

    Best effort: it is only consulted when yt-dlp writes something, so it cannot
    interrupt a long silent network wait the way ``subprocess`` can.
    """
    if not timeout:
        return None
    deadline = time.monotonic() + float(timeout)
    return lambda: time.monotonic() > deadline


def run_ytdlp_capture(
    cmd: list[str],
    timeout: float | None = None,
    env: dict | None = None,
) -> str:
    """Run yt-dlp to completion and return its output as text.

    Used for ``--dump-json`` / ``--print`` style one-shot queries. Raises
    :class:`YtdlpUnavailable`, :class:`YtdlpTimeout` or :class:`YtdlpFailed`.
    """
    if use_inprocess():
        collected: list[str] = []
        deadline = _deadline_check(timeout)
        sink = _LineSink(collector=collected, cancel_check=deadline)
        rc = _run_inprocess(cmd, sink)
        out = "\n".join(collected)
        if rc != 0:
            # The in-process deadline is advisory, so a timeout surfaces here.
            if deadline is not None and deadline():
                raise YtdlpTimeout(out)
            raise YtdlpFailed(rc, out)
        return out

    try:
        result = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=True,
            creationflags=_SUBPROCESS_CREATION_FLAGS,
            env=env,
        )
    except FileNotFoundError as exc:
        raise YtdlpUnavailable(str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise YtdlpTimeout("yt-dlp timed out") from exc
    except subprocess.CalledProcessError as exc:
        out = "".join(
            part for part in (getattr(exc, "stderr", ""), getattr(exc, "stdout", ""))
            if part
        ).strip()
        raise YtdlpFailed(exc.returncode, out) from exc
    return result.stdout
