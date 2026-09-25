from __future__ import annotations

import json
import logging
import logging.handlers
import os
import platform
import re
import shutil
import sys
import time
import urllib.request
from urllib.parse import urlparse

from PySide6.QtCore import (
    QObject,
    Property,
    QRunnable,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
    Slot,
    qVersion,
)
from PySide6.QtGui import QDesktopServices

import translate

from src import ass_io, gguf_check, srt_io, subtitle_quality, youtube_media
from .controllers.translation import TranslationWorker
from .models.results import CueFilterProxyModel, CueResultModel, QualityIssuesModel
from .models.run_config import RunConfig

# FunASR GGUF models for the local ASR runtime, downloaded into ./gguf on demand.
_MODEL_URLS = (
    (
        "sensevoice-small-q8.gguf",
        "https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/main/sensevoice-small-q8.gguf",
    ),
    (
        "fsmn-vad.gguf",
        "https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF/resolve/main/fsmn-vad.gguf",
    ),
)

# Translation GGUF served by the bundled llama-server (auto-started by the app).
# The default local translation model is the Q8_0-quantized Hy-MT2 GGUF.
_LOCAL_MODEL = "Hy-MT2-1.8B-Q8_0.gguf"
_LOCAL_MODEL_URLS = (
    (
        _LOCAL_MODEL,
        "https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q8_0.gguf",
    ),
)


def resolve_local_model_path(gguf_dir: str, *extra_dirs: str) -> str:
    """Resolve the preferred local translation model path.

    Searches `gguf_dir` first, then each of `extra_dirs` (used for model folders
    an earlier app layout left behind — see `_legacy_gguf_dirs`). Preference
    order, per folder:
        1. gguf/Hy-MT2-1.8B-Q8_0.gguf
        2. Any single unambiguous Hy-MT2 GGUF in the directory

    Only files that pass the GGUF integrity check are considered, so an
    interrupted download (a file that exists but is cut short) is never
    returned as a usable model. Returns the chosen path or an empty string if
    none is found.
    """
    import glob

    for directory in (gguf_dir, *extra_dirs):
        candidate = os.path.join(directory, _LOCAL_MODEL)
        if gguf_check.is_usable_gguf(candidate):
            return candidate

    for directory in (gguf_dir, *extra_dirs):
        # Any Hy-MT2 GGUF, preferring Q8_0 files.
        hy_mt2_files = [
            path
            for path in glob.glob(os.path.join(directory, "Hy-MT2*.gguf"))
            if gguf_check.is_usable_gguf(path)
        ]
        if len(hy_mt2_files) == 1:
            return hy_mt2_files[0]
        if len(hy_mt2_files) > 1:
            q8_files = [f for f in hy_mt2_files if "q8" in os.path.basename(f).lower()]
            if q8_files:
                return sorted(q8_files)[0]
            return sorted(hy_mt2_files)[0]
    return ""


_DONE_PATTERN = re.compile(r"^Wrote \d+ cues to (?P<path>.+)$")

# Error/warning detection for the log badge. Deliberately broader than a bare
# "[error]" prefix: Python tracebacks, `ERROR:`-prefixed yt-dlp output and
# `SomeError:` exception lines all count, so the badge can no longer read
# "0 errors" next to a Failed pill.
_LOG_ERROR_RE = re.compile(
    r"^\[error\]|^\s*ERROR\s*:|traceback \(most recent call last\)"
    r"|^\s*[A-Za-z_][\w.]*(?:Error|Exception)\s*:",
    re.IGNORECASE,
)
_LOG_WARN_RE = re.compile(r"^\[warn(ing)?\]|^\s*(?:WARNING|warn)\s*:", re.IGNORECASE)

# Rolling log window: a multi-hour run must not grow the log without bound.
_MAX_LOG_LINES = 5000
_LOG_TRUNCATION_NOTICE = "[warn] earlier log lines trimmed; only the most recent are shown\n"

PIPELINE_MODE_YOUTUBE_CLOUD = "youtube_cloud"
PIPELINE_MODE_LOCAL_CLOUD = "local_cloud"
PIPELINE_MODE_OFFLINE = "offline"

# Readiness row states (UI review 2.1). Five facts, five distinct treatments:
#   ok        - pass / ready / verified
#   todo      - warning / attention / blocking
#   na        - not applicable to the current mode (a fact, not a problem)
#   unchecked - not yet evaluated (a different fact from `na`)
# `na` and `unchecked` used to share one grey dash, which is why the readiness
# score's denominator did not match the visible rows.
READINESS_OK = "ok"
READINESS_TODO = "todo"
READINESS_NA = "na"
READINESS_UNCHECKED = "unchecked"

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _is_local_host(url: str | None) -> bool:
    """True if `url` points at this machine (a local OpenAI-compatible server).

    Mirrors ``src.config._is_local``: a local endpoint accepts any placeholder
    key, so "no API key" is not an error when the base URL is local.
    """
    if not url:
        return False
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return host in _LOCAL_HOSTS or host.endswith(".localhost")


def _setting_provenance(own: str | None, env_name: str) -> tuple[str, str]:
    """(effective value, provenance) for one setting that can inherit.

    UI review 1.4: a field that can inherit must show what is *in effect* with
    the source as secondary text. A placeholder such as "from .env when blank"
    disappears on focus, which makes "unset" and "intentionally inheriting"
    look identical.
    """
    own = (own or "").strip()
    if own:
        return own, "set here"
    inherited = (os.environ.get(env_name) or "").strip()
    if inherited:
        return inherited, "inherited from .env"
    return "", ""

# Model file states. A model is only "ready" once its GGUF header has been
# parsed and the file is provably complete; a file that exists but is cut short
# (an interrupted download) is "corrupt", which is a different, actionable
# state — the UI offers a re-download instead of a green tick.
MODEL_STATE_READY = "ready"
MODEL_STATE_MISSING = "missing"
MODEL_STATE_CORRUPT = "corrupt"


def _model_status(path: str | None) -> tuple[str, str]:
    """Classify one GGUF path as ready / missing / corrupt (plus the reason)."""
    if not path or not os.path.exists(path):
        return MODEL_STATE_MISSING, ""
    ok, reason = gguf_check.inspect_gguf(path)
    if ok:
        return MODEL_STATE_READY, ""
    return MODEL_STATE_CORRUPT, reason


def _resolve_model_status(
    selected: str | None, *fallbacks: str
) -> tuple[str, str, str]:
    """Pick the best model path from a user selection plus fallbacks.

    Returns ``(state, path, reason)``. A corrupt *selected* path is reported as
    corrupt only when no usable fallback exists — otherwise the fallback wins
    and the run proceeds, which is what a user who already has a good copy in
    the models folder expects.
    """
    selected = (selected or "").strip()
    state, reason = _model_status(selected)
    if state == MODEL_STATE_READY:
        return MODEL_STATE_READY, selected, ""

    for candidate in fallbacks:
        fallback_state, _ = _model_status(candidate)
        if fallback_state == MODEL_STATE_READY:
            return MODEL_STATE_READY, candidate, ""

    if state == MODEL_STATE_CORRUPT:
        return MODEL_STATE_CORRUPT, selected, reason
    return MODEL_STATE_MISSING, "", ""


CONTENT_PRESETS = ("auto", "drama", "anime", "music", "documentary", "variety", "lecture")
ASR_PREPROCESS_PROFILES = ("auto", "none", "basic", "loudnorm", "denoise")
CONTEXT_MODES = ("", "off", "light", "standard", "deep")

STATUS_READY = "ready"
STATUS_VALIDATING = "validating"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


# --- Structured failure classification -------------------------------------
# Before this, every failure surfaced as "Finished with errors (exit N). See
# the log." and the log drawer was collapsed, so the user had to discover a
# hidden control and read raw CLI output to find out what went wrong.
# These patterns turn the captured log into a typed cause plus one concrete
# remediation the UI can offer as a button.
REMEDY_CLOUD = "cloud"
REMEDY_RETRY = "retry"
REMEDY_DOWNLOAD_MODEL = "download_model"
REMEDY_INSTALL_DEPENDENCY = "install_dependency"
REMEDY_CHECK_SOURCE = "check_source"
REMEDY_LOG = "log"
REMEDY_FORM = "form"

_FAILURE_PATTERNS: tuple[tuple[str, re.Pattern, str, str], ...] = tuple(
    (code, re.compile(pattern, re.IGNORECASE), title, remedy)
    for code, pattern, title, remedy in (
        (
            "AUTH",
            r"(401|403|unauthoriz|forbidden|invalid api key|incorrect api key|"
            r"authentication|invalid_token|api[_-]?key is (?:invalid|missing))",
            "The translation service rejected the API key.",
            REMEDY_CLOUD,
        ),
        (
            "QUOTA",
            r"(429|rate limit|quota|insufficient_quota|billing|"
            r"exceeded your current quota)",
            "The translation service rate-limited the request or ran out of credit.",
            REMEDY_CLOUD,
        ),
        (
            "NETWORK",
            r"(connectionerror|connection refused|connection reset|timed ?out|"
            r"timeout|temporary failure in name resolution|"
            r"name or service not known|max retries exceeded|"
            r"network is unreachable|proxyerror|sslerror|ssl:)",
            "The computer could not reach the translation service.",
            REMEDY_RETRY,
        ),
        (
            "SOURCE_UNAVAILABLE",
            r"(video unavailable|private video|video has been removed|"
            r"unable to (?:download|extract|fetch)[^\n]{0,40}"
            r"(?:subtitle|transcript|caption)|"
            r"no (?:subtitles|transcript|captions)\b|"
            r"subtitles? (?:are )?disabled|sign in to confirm|"
            r"not a valid url|http error 40[34])",
            "No subtitles could be fetched for this source.",
            REMEDY_CHECK_SOURCE,
        ),
        (
            "MISSING_DEPENDENCY",
            r"(ffmpeg|ffprobe|yt-dlp|yt_dlp)[^\n]{0,40}"
            r"(not found|is not recognized|no such file|missing|"
            r"command not found)"
            # ...and the other word order: "No such file or directory: 'ffmpeg'".
            r"|(not found|no such file[^\n]{0,40}|is not recognized[^\n]{0,40}"
            r"|command not found[^\n]{0,40}|could not find[^\n]{0,40}"
            r"|failed to (?:execute|run)[^\n]{0,40})"
            r"(ffmpeg|ffprobe|yt-dlp|yt_dlp)"
            r"|modulenotfounderror: no module named '?(?:yt_dlp|"
            r"youtube_transcript_api|funasr_onnx)'?",
            "A required external tool is not installed.",
            REMEDY_INSTALL_DEPENDENCY,
        ),
        (
            "MODEL_DOWNLOAD",
            r"(failed to download|download failed|error downloading|"
            r"could not download|did not download completely)"
            r"[^\n]{0,80}(?:gguf|model|byte|space)?",
            "A model download failed.",
            REMEDY_DOWNLOAD_MODEL,
        ),
        (
            "MODEL_LOAD",
            r"(failed to load model|unable to load model|could not load model|"
            r"error loading model|gguf[^\n]{0,30}(?:invalid|corrupt)|"
            r"llama[_-]?server[^\n]{0,40}(?:failed|exited))",
            "The local model could not be loaded.",
            REMEDY_DOWNLOAD_MODEL,
        ),
        (
            # Must precede SOURCE_UNAVAILABLE: "produced no transcription" used
            # to be read as "no transcript was available for this video", which
            # sent the user to check their source file instead of the model.
            "ASR_MODEL",
            r"(no transcription|transcri\w+[^\n]{0,40}(?:produced nothing|empty)|"
            r"funasr[^\n]{0,60}(?:not found|no transcription|failed to load)|"
            # Anchored on the filename: a bare "asr"/"sensevoice" followed by
            # "incomplete" also matches "--asr-model C:\…\sensevoice-small-q8.gguf",
            # which is a *path*, not a diagnosis.
            r"(?:sensevoice|fsmn[-_ ]?vad)[-_.\w]*\.gguf[^\n]{0,20}"
            r"(?:not found|missing|corrupt|incomplete|unreadable)|"
            r"failed to read tensor data|load gguf failed|"
            r"file is incomplete[^\n]{0,60}gguf)",
            "The local transcription model could not be used.",
            REMEDY_DOWNLOAD_MODEL,
        ),
        (
            "ASR_FAILED",
            r"((?:asr|transcri\w+|sensevoice)[^\n]{0,40}(?:failed|error)"
            r"|(?:failed|error)[^\n]{0,40}(?:asr|transcri\w+|sensevoice))",
            "Local transcription (ASR) failed.",
            REMEDY_RETRY,
        ),
        (
            "WRITE_FAILED",
            r"(permissionerror|permission denied|read-only file system|"
            r"no space left on device|errno 28|errno 13|"
            r"failed to write|could not write)",
            "The subtitle file could not be written.",
            REMEDY_RETRY,
        ),
    )
)

_FAILURE_TAIL_LINES = 200


def _classify_failure(log_text: str) -> tuple[str, str, str, str]:
    """Map captured run output to (code, title, detail, remedy).

    Scans newest-first: the specific cause (traceback tail, yt-dlp message)
    almost always appears after the generic preamble.

    "[warn] …" lines are advisory — they report something the app already
    recovered from, e.g. "Ignoring --asr-model <path>: file is incomplete.
    Falling back to the models folder." The run may still succeed, so those
    lines never drive the classification; blaming a model the run did not use
    is exactly the bug this avoids.
    """
    raw_lines = [ln.strip() for ln in (log_text or "").splitlines() if ln.strip()]
    lines = [ln for ln in raw_lines if not ln.lower().startswith("[warn]")]
    tail = lines[-_FAILURE_TAIL_LINES:]

    for line in reversed(tail):
        for code, rx, title, remedy in _FAILURE_PATTERNS:
            if rx.search(line):
                return code, title, line[:400], remedy

    # No typed match: fall back to the most recent explicit error line so the
    # user still sees a real message rather than an exit code.
    for line in reversed(tail):
        lowered = line.lower()
        if lowered.startswith("[error]"):
            return "UNKNOWN", "The run failed.", line[7:].strip()[:400] or line[:400], REMEDY_LOG
        if "traceback (most recent call last)" in lowered:
            return "UNKNOWN", "The run stopped on an unexpected error.", line[:400], REMEDY_LOG
        if "error:" in lowered:
            return "UNKNOWN", "The run failed.", line[:400], REMEDY_LOG

    if tail:
        return "UNKNOWN", "The run failed.", tail[-1][:400], REMEDY_LOG
    if raw_lines:
        # Nothing but advisory lines: still show the user something concrete.
        return "UNKNOWN", "The run failed.", raw_lines[-1][:400], REMEDY_LOG
    return (
        "UNKNOWN",
        "The run failed.",
        "No output was captured. See the log below.",
        REMEDY_LOG,
    )


class _WorkerSignal(QObject):
    progress = Signal(str)
    done = Signal(str)


class _YouTubeDownloadSignal(QObject):
    progress = Signal(str)
    percent = Signal(int)
    done = Signal(str)


_APP_DIR_NAME = "TranslationAgent"


def _is_writable_dir(path: str) -> bool:
    """True when a file can actually be created in `path`.

    A frozen app is routinely installed under ``C:\\Program Files``, where the
    folder next to the .exe is read-only for a standard user. Writing the
    models folder, the result cache or ``debug.log`` there then fails, and the
    app looks broken on a client machine — so every location is probed before
    it is used rather than assumed to be writable.
    """
    if not os.path.isdir(path):
        return False
    probe = os.path.join(path, f".write-probe-{os.getpid()}")
    try:
        with open(probe, "w", encoding="utf-8"):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


_APP_DATA_CACHE: str | None = None


def _app_data_dir() -> str:
    """Per-user writable folder, used when the app folder is read-only."""
    global _APP_DATA_CACHE
    if _APP_DATA_CACHE:
        return _APP_DATA_CACHE
    if sys.platform.startswith("win"):
        root = (
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or os.path.expanduser("~")
        )
    elif sys.platform == "darwin":
        root = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"
        )
    path = os.path.join(root, _APP_DIR_NAME)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        path = os.path.expanduser("~")
    _APP_DATA_CACHE = path
    return path


def _gguf_dir() -> str:
    """Where downloaded GGUF models go: next to the app when that is writable.

    Models living in the same folder as the executable is the point of the
    onedir bundle: a client can drop ``TranslationAgent.exe``, ``_internal``
    and the ``.gguf`` files into one folder and run it. If the app folder is
    read-only (a Program Files install), fall back to the per-user folder so
    downloads still land somewhere usable instead of failing.
    """
    base = _base_dir()
    if _is_writable_dir(base):
        path = os.path.join(base, "gguf")
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except OSError:
            pass
    path = os.path.join(_app_data_dir(), "gguf")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return _app_data_dir()
    return path


def _legacy_gguf_dirs() -> list[str]:
    """Model folders an earlier app layout left behind, best-first.

    The bundle used to be written straight into `dist/`, so `_base_dir()` — and
    with it the models folder — was `dist/`. It is now written into
    `dist/TranslationAgent/`, which moved the models folder to
    `dist/TranslationAgent/gguf/` and orphaned models the user had already
    downloaded into `dist/gguf/`.

    That is the "but the models are already downloaded" report: the app stopped
    looking where they were, downloaded them again, and on a full disk the
    second download was cut short. Returns [] for a source run, whose models
    folder is already the repo's `gguf/`.
    """
    if not getattr(sys, "frozen", False):
        return []
    current = os.path.abspath(_gguf_dir())
    sibling = os.path.join(os.path.dirname(_base_dir()), "gguf")
    if os.path.isdir(sibling) and os.path.abspath(sibling) != current:
        return [sibling]
    return []


def _model_search_dirs() -> list[str]:
    """Every folder searched for an already-present model, best-first.

    Order matters. The folder the executable sits in comes first, because
    "put the .gguf files next to the .exe" is the layout a client machine gets
    handed; then the ``gguf``/``models`` subfolders beside it (what the app
    downloads into), then the per-user fallback folder, then whatever earlier
    layouts left behind so an existing install keeps working after an upgrade.
    """
    base = os.path.abspath(_base_dir())
    candidates = [
        base,
        os.path.join(base, "gguf"),
        os.path.join(base, "models"),
        os.path.join(_app_data_dir(), "gguf"),
        *_legacy_gguf_dirs(),
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for directory in candidates:
        key = os.path.normcase(os.path.abspath(directory))
        if key not in seen:
            seen.add(key)
            ordered.append(directory)
    return ordered


def _find_model_file(filename: str) -> str:
    """A usable `filename` from any search folder ("" when none is usable)."""
    for directory in _model_search_dirs():
        candidate = os.path.join(directory, filename)
        if gguf_check.is_usable_gguf(candidate):
            return candidate
    return ""


def _find_local_model() -> str:
    """A usable local translation model from any search folder."""
    return resolve_local_model_path(*_model_search_dirs())


def _cache_dir() -> str:
    """Writable folder for run artefacts (falls back when the app folder is not)."""
    base = _base_dir()
    if _is_writable_dir(base):
        path = os.path.join(base, "cache")
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except OSError:
            pass
    path = os.path.join(_app_data_dir(), "cache")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return _app_data_dir()
    return path


def _result_json_path() -> str:
    """Stable path for the CLI's --result-json output (GUI review data)."""
    return os.path.join(_cache_dir(), "last_result.json")


def _run_result_dir() -> str:
    """Per-run copies of the result JSON, so the Log screen can reload an old run.

    The CLI writes one fixed file (`last_result.json`) and overwrites it every
    run, so Review/Quality could only ever describe the newest run. A run
    history whose entries cannot be opened is a list of dead rows, so each
    successful run's result is copied here and named by the entry that owns it.
    """
    path = os.path.join(_cache_dir(), "run_results")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return ""
    return path


def _remove_file(path: str) -> None:
    """Best-effort delete; used to clean up failed/partial downloads."""
    try:
        os.remove(path)
    except OSError:
        pass


def _format_bytes(size: int | float) -> str:
    """Human-readable byte size ("1.9 GB"); used by the models table."""
    value = float(max(0.0, float(size)))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0:
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def _format_seconds(seconds: float) -> str:
    """Compact wall-clock ("1 m 42 s") for the run history."""
    total = int(max(0.0, float(seconds)))
    minutes, secs = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} h {minutes:02d} m"
    if minutes:
        return f"{minutes} m {secs:02d} s"
    return f"{secs} s"


def _format_clock_ms(ms: float) -> str:
    """``mm:ss`` (or ``h:mm:ss``) from milliseconds, for timeline rulers."""
    total = int(max(0.0, float(ms)) / 1000.0)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class _ModelDownloadWorker(QRunnable):
    """Streams GGUF model files into ./gguf, reporting progress per chunk.

    Two properties matter more than speed here:

    * **A partial file is never mistaken for a complete one.** Downloads land
      in ``<name>.part`` and are renamed only after the whole file has been
      received *and* the GGUF header parses. A dropped connection or a full
      disk therefore leaves no file that later looks usable.
    * **A damaged file already on disk is repaired.** If the destination exists
      but fails the integrity check, it is re-downloaded instead of being
      reported as "already present".
    """

    def __init__(self, urls: tuple = _MODEL_URLS) -> None:
        super().__init__()
        self.signals = _WorkerSignal()
        self.downloaded: list[str] = []
        self.urls = urls

    @Slot()
    def run(self) -> None:
        dest_dir = _gguf_dir()
        for filename, url in self.urls:
            dest = os.path.join(dest_dir, filename)
            if gguf_check.is_usable_gguf(dest):
                self.signals.progress.emit(f"[ok] already present: {filename}\n")
                self.downloaded.append(dest)
                continue
            if os.path.exists(dest):
                self.signals.progress.emit(
                    f"[warn] {filename} is incomplete or unreadable; "
                    f"downloading it again.\n"
                )
            self.signals.progress.emit(f"Downloading {filename}…\n")
            partial = dest + ".part"
            try:
                with urllib.request.urlopen(url) as resp, open(partial, "wb") as out:
                    total = resp.length or 0
                    got = 0
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                        got += len(chunk)
                        if total:
                            pct = got * 100 // total
                            self.signals.progress.emit(f"  {filename}: {pct}%\n")
            except Exception as exc:  # noqa: BLE001
                self.signals.progress.emit(f"[error] download failed: {exc}\n")
                _remove_file(partial)
                continue

            ok, reason = gguf_check.inspect_gguf(partial)
            if not ok:
                self.signals.progress.emit(
                    f"[error] {filename} did not download completely ({reason}). "
                    f"Check the free disk space and try again.\n"
                )
                _remove_file(partial)
                continue
            try:
                os.replace(partial, dest)
            except OSError as exc:
                self.signals.progress.emit(
                    f"[error] could not save {filename}: {exc}\n"
                )
                _remove_file(partial)
                continue
            self.downloaded.append(dest)
            self.signals.progress.emit(f"[ok] saved: {dest}\n")
        self.signals.done.emit("done")


class _YouTubeInfoWorker(QRunnable):
    """Inspects a YouTube URL for available formats/codecs off the UI thread."""

    def __init__(self, url: str, token: int = 0) -> None:
        super().__init__()
        self.url = url
        self.token = token
        self.signals = _WorkerSignal()

    @Slot()
    def run(self) -> None:
        try:
            info = youtube_media.inspect_video(self.url)
            self.signals.done.emit(f"INFO:{self.token}|" + json.dumps(info))
        except Exception as exc:  # noqa: BLE001
            self.signals.done.emit(f"INFOERROR:{self.token}|{exc}")


class _YouTubeDownloadWorker(QRunnable):
    """Downloads a YouTube video or subtitle track off the UI thread.

    ``kind`` is ``"video"`` or ``"subtitle"``. The worker keeps a reference to
    the running yt-dlp process so the UI can cancel it, and video downloads
    additionally report progress percentages.
    """

    def __init__(
        self, kind: str, url: str, format_selector: str, out_template: str,
        token: int = 0, expect: dict | None = None,
    ) -> None:
        super().__init__()
        self.kind = kind
        self.url = url
        self.format_selector = format_selector
        self.out_template = out_template
        self.token = token
        # What the finished file should look like: {"codec": "h264",
        # "height": 720, "cap": True}. Used only for a post-download sanity
        # check; a mismatch is reported, never silently accepted.
        self.expect = expect or None
        self.proc_ref: dict = {}
        self.canceled = False
        self.signals = _YouTubeDownloadSignal()

    def cancel(self) -> None:
        """Terminate the yt-dlp process (safe to call from any thread)."""
        self.canceled = True
        proc = self.proc_ref.get("proc")
        if proc is not None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass

    def _verify(self, path: str) -> str:
        """Compare the produced file with what the user asked for.

        Best effort: needs ffmpeg or ffprobe to inspect the file, and only ever
        *reports*. Returns a warning line ("" when the file matches or could
        not be checked).
        """
        expect = self.expect
        if not expect or not path:
            return ""
        probe = youtube_media.probe_video_file(path)
        if not probe:
            return ""
        want_codec = (expect.get("codec") or "").strip().lower()
        want_height = int(expect.get("height") or 0)
        got_codec = (probe.get("codec") or "").strip().lower()
        got_height = int(probe.get("height") or 0)
        # "Best (any)" accepts *any* codec, so only the height matters there.
        # Comparing against the literal id "best" would warn on every download.
        any_codec = bool(expect.get("cap")) or want_codec in ("", "best")

        problems = []
        if want_codec and got_codec and not any_codec and want_codec != got_codec:
            problems.append(
                f"codec {youtube_media._CODEC_LABEL.get(got_codec, got_codec)}"
                f" instead of "
                f"{youtube_media._CODEC_LABEL.get(want_codec, want_codec)}")
        if want_height and got_height:
            if expect.get("cap"):
                if got_height > want_height:
                    problems.append(f"{got_height}p instead of \u2264 {want_height}p")
            elif got_height != want_height:
                problems.append(f"{got_height}p instead of {want_height}p")
        if not problems:
            return ""
        return ("[warn] The downloaded file is "
                + " and ".join(problems)
                + ". YouTube sometimes re-maps a stream; re-run the download "
                  "or pick another resolution if this is not what you wanted.")

    @Slot()
    def run(self) -> None:
        try:
            if self.kind == "video":
                path = youtube_media.download_video(
                    self.url, self.format_selector, self.out_template,
                    progress_cb=lambda line: self.signals.progress.emit(line + "\n"),
                    percent_cb=self.signals.percent.emit,
                    proc_ref=self.proc_ref,
                    cancel_check=lambda: self.canceled,
                )
                warning = self._verify(path)
                if warning:
                    self.signals.progress.emit(warning + "\n")
            else:
                path = youtube_media.download_subtitle(
                    self.url, "en", self.out_template,
                    progress_cb=lambda line: self.signals.progress.emit(line + "\n"),
                    proc_ref=self.proc_ref,
                    cancel_check=lambda: self.canceled,
                )
            self.signals.done.emit(f"YTDONE:{self.token}|{self.kind}:{path}")
        except Exception as exc:  # noqa: BLE001
            if self.canceled:
                self.signals.done.emit(f"YTCANCEL:{self.token}|{self.kind}")
            else:
                self.signals.done.emit(f"YTERROR:{self.token}|{self.kind}:{exc}")


def _base_dir() -> str:
    """Directory the app lives in (next to the .exe when frozen)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def setup_logging(base_dir: str) -> logging.Logger:
    """Write a rotating debug.log next to the app; returns the logger."""
    logger = logging.getLogger("translation_agent")
    logger.setLevel(logging.DEBUG)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    path = os.path.join(base_dir, "debug.log")
    if not _is_writable_dir(base_dir):
        # Read-only install (Program Files): keep logging, just not there.
        path = os.path.join(_app_data_dir(), "debug.log")
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
    except OSError:
        return logger
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(file_handler)
    return logger


class AppBridge(QObject):
    formChanged = Signal()
    statusMessageChanged = Signal()
    statusStateChanged = Signal()
    logTextChanged = Signal()
    logVisibleChanged = Signal()
    isRunningChanged = Signal()
    canOpenOutputFolderChanged = Signal()
    modelDownloadChanged = Signal()
    pipelineModeChanged = Signal()
    localModelDownloadPendingChanged = Signal()
    progressChanged = Signal()
    resultReadyChanged = Signal()
    debugJsonProgressChanged = Signal()
    youtubeInfoChanged = Signal()
    youtubeDownloadChanged = Signal()

    # --- Added by the UX remediation pass ---------------------------------
    themeChanged = Signal()
    readinessChanged = Signal()
    # code, title, detail, remediation
    failureOccurred = Signal(str, str, str, str)
    reviewDirtyChanged = Signal()
    logCountsChanged = Signal()
    requestTab = Signal(int)
    stageChanged = Signal()
    focusCueIndexChanged = Signal()
    failureChanged = Signal()
    requestAdvanced = Signal()
    # Redesign surfaces: accent choice, per-cue edits (timing / auto-fix) and
    # the persisted run history.
    accentChanged = Signal()
    cueDataChanged = Signal()
    runHistoryChanged = Signal()
    # Autosave (UI review 3.4). The persistent "Save" button is gone, so the UI
    # needs a dirty flag to mirror and a transient signal to fire the toast on.
    dirtyChanged = Signal()
    savedToast = Signal()
    # The composed top-bar status line depends on form state, run state and the
    # dirty flag, so it gets its own signal rather than piggy-backing on one.
    globalStatusChanged = Signal()
    shortcutsChanged = Signal()

    # Fields persisted across runs, as (attr, QSettings key, default). Bumped
    # whenever a new stored preference is introduced; secrets like the API key
    # are intentionally not persisted.
    _PERSISTED = (
        ("_pipeline_mode", "pipeline/mode", PIPELINE_MODE_YOUTUBE_CLOUD),
        ("_content_preset", "pipeline/contentPreset", "auto"),
        ("_source_lang", "translation/sourceLang", ""),
        ("_context_mode", "translation/contextMode", ""),
        ("_context_summary", "translation/contextSummary", False),
        ("_batch", "translation/batch", "8"),
        ("_asr_language", "asr/language", "auto"),
        ("_asr_preprocess", "asr/preprocess", "auto"),
        ("_asr_bin", "asr/bin", ""),
        ("_asr_vad_bin", "asr/vadBin", ""),
        ("_asr_model", "asr/model", ""),
        ("_asr_vad_model", "asr/vadModel", ""),
        ("_asr_threads", "asr/threads", "4"),
        ("_asr_max_segment_ms", "asr/maxSegmentMs", "6000"),
        ("_asr_max_end_silence_ms", "asr/maxEndSilenceMs", "250"),
        ("_asr_speech_noise_threshold", "asr/speechNoiseThreshold", "0.55"),
        ("_asr_noise_db", "asr/noiseDb", "-35"),
        ("_asr_min_silence_s", "asr/minSilenceS", "0.25"),
        ("_asr_max_cue_duration_ms", "asr/maxCueDurationMs", "3200"),
        ("_asr_max_cue_chars", "asr/maxCueChars", "70"),
        ("_asr_max_cue_chars_cjk", "asr/maxCueCharsCjk", "48"),
        ("_asr_no_tags", "asr/noTags", False),
        ("_asr_keep_tags", "asr/keepTags", False),
        ("_local_model", "local/model", ""),
        ("_local_threads", "local/threads", "0"),
        ("_local_mlock", "local/mlock", False),
        ("_glossary_path", "translation/glossaryPath", ""),
        ("_translation_memory_mode", "translation/translationMemoryMode", "auto"),
        ("_translation_memory_db", "translation/translationMemoryDbPath", ""),
        ("_strict_quality", "quality/strict", False),
        ("_output_format", "output/format", "srt"),
        ("_youtube_download_dir", "youtube/downloadDir", ""),
        # Appearance / ergonomics (UX review S-10: light theme, density, motion).
        ("_theme_name", "ui/theme", "dark"),
        ("_comfortable", "ui/comfortable", False),
        ("_reduced_motion", "ui/reducedMotion", False),
        ("_accent_name", "ui/accent", "iris"),
        # Persisted run history for the Log screen (JSON-encoded list).
        ("_run_history_json", "run/history", "[]"),
        # Keyboard shortcut overrides (JSON object: action id -> sequence).
        # Only user-changed combos are stored; everything else falls back to
        # `_SHORTCUT_DEFAULTS`.
        ("_shortcuts_json", "ui/shortcuts", "{}"),
        # Rolling average wall time per cue, used to project an ETA on later
        # runs (UX review S-07: wait-time uncertainty).
        ("_history_ms_per_cue", "run/historyMsPerCue", "0"),
        ("_win_x", "window/x", 60),
        ("_win_y", "window/y", 60),
        ("_win_w", "window/w", 1280),
        ("_win_h", "window/h", 840),
    )

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.threadpool = QThreadPool()
        self.logger = logging.getLogger("translation_agent")
        self._settings = QSettings()

        # Autosave (UI review 3.4). Two simultaneous save affordances — a
        # "Saved" pill next to an enabled "Save" button — encoded opposite
        # facts on every Settings frame. There is now one truth: a dirty flag
        # plus a debounce timer that commits on its own.
        self._dirty = False
        self._loading = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._commit_pending)

        self._pipeline_mode = PIPELINE_MODE_YOUTUBE_CLOUD
        self._mode = "youtube"
        self._backend = "cloud"
        self._url = ""
        self._file_path = ""
        self._source_lang = ""
        self._out_path = ""
        # True while the output path is derived from the input file rather than
        # typed by the user. Not persisted: every launch starts on auto so the
        # SRT lands next to whichever video is loaded.
        self._out_path_auto = True
        self._batch = "8"
        self._api_key = ""
        self._base_url = ""
        self._model = ""
        self._host = "127.0.0.1"
        self._port = "8080"
        self._model_name = "Hy-MT2-1.8B-Q8_0"
        self._local_model = ""
        self._content_preset = "auto"
        self._context_mode = ""
        self._context_summary = False
        self._asr_language = "auto"
        self._asr_preprocess = "auto"
        self._asr_bin = ""
        self._asr_vad_bin = ""
        self._asr_model = ""
        self._asr_vad_model = ""
        self._asr_threads = "4"
        self._asr_max_segment_ms = "7000"
        self._asr_max_end_silence_ms = "250"
        self._asr_speech_noise_threshold = "0.55"
        self._asr_noise_db = "-35"
        self._asr_min_silence_s = "0.25"
        self._asr_max_cue_duration_ms = "3200"
        self._asr_max_cue_chars = "70"
        self._asr_max_cue_chars_cjk = "48"
        self._asr_no_tags = False
        self._asr_keep_tags = False
        self._local_threads = "0"
        self._local_mlock = False
        self._glossary_path = ""
        self._translation_memory_mode = "auto"
        self._translation_memory_db = ""
        self._strict_quality = False
        self._output_format = "srt"
        self._theme_name = "dark"
        self._comfortable = False
        self._reduced_motion = False
        self._history_ms_per_cue = 0.0
        self._status_message = "Ready."
        self._status_state = STATUS_READY
        self._log_text = ""
        self._is_running = False
        self._resolved_out_path = ""
        self._current_worker: TranslationWorker | None = None
        self._model_download_status = ""
        self._model_downloading = False
        self._local_model_download_status = ""
        self._local_model_downloading = False
        self._local_model_download_pending = False

        # Progress + result review state.
        self._progress_stage = ""
        self._progress_done = 0
        self._progress_total = 0
        self._result_ready = False
        self._result_strict_state = "off"  # off | pass | fail
        self._quality_summary: dict = {}
        self._debug_json_progress = False
        self._log_visible = False

        # --- Structured failure surface (UX review S-02) -------------------
        self._failure_code = ""
        self._failure_title = ""
        self._failure_detail = ""
        self._failure_remediation = ""
        self._failure_active = False

        # --- Incremental log counters + truncation (S-12, U-19, U-20) ------
        self._log_error_count = 0
        self._log_warn_count = 0
        self._log_lines = 0

        # --- Per-stage timing and ETA history (S-07) ------------------------
        self._stage_sequence: list[str] = []
        self._stage_started_at = 0.0
        self._stage_elapsed_sec = 0
        self._run_started_at = 0.0
        self._estimated_remaining_sec = 0

        # --- Review editing (S-01) ------------------------------------------
        self._focus_cue_index = -1
        self._last_result_cues: list[dict] = []

        # YouTube media (video download + codec inspection) state.
        self._youtube_formats: list[dict] = []
        self._youtube_matrix: dict = {}
        self._youtube_best: dict = {}
        self._youtube_codec_ids: list[str] = []
        self._youtube_resolutions: list[int] = []
        self._youtube_info_loading = False
        self._youtube_info_error = ""
        self._youtube_selected_codec = "best"
        self._youtube_selected_resolution = "best"
        self._youtube_title = ""
        self._youtube_has_av1 = False
        self._youtube_has_vp9 = False
        self._youtube_has_h264 = False
        self._youtube_has_en_subtitle = False
        # Video vs subtitle downloads are fully independent: each has its own
        # busy flag, status text, progress and worker so both can run at once
        # (and one can be canceled without touching the other).
        self._youtube_video_downloading = False
        self._youtube_video_progress = 0
        self._youtube_video_status = ""
        # Headline for recoverable hiccups (e.g. a stale partial download that
        # had to be restarted). Kept separate from the raw status log so the UI
        # can show it as a banner instead of burying it in the line noise.
        self._youtube_video_notice = ""
        self._youtube_sub_downloading = False
        self._youtube_sub_status = ""
        self._youtube_downloading = False  # combined convenience flag
        self._youtube_download_status = ""  # combined convenience text
        self._youtube_downloaded_video = ""
        self._youtube_downloaded_subtitle = ""
        self._youtube_video_worker: _YouTubeDownloadWorker | None = None
        self._youtube_sub_worker: _YouTubeDownloadWorker | None = None
        self._youtube_info_worker: _YouTubeInfoWorker | None = None
        # Generation tags: every inspect/download start bumps its counter and
        # the worker echoes the tag in its completion payload. Completions
        # whose tag no longer matches (URL changed, retry after a recovery)
        # are ignored as stale. sender() cannot identify a worker — it is the
        # signals object, never the QRunnable — so the tag must travel in the
        # payload itself.
        self._youtube_info_gen = 0
        self._youtube_video_gen = 0
        self._youtube_sub_gen = 0
        # Worker references for model downloads (same sender() limitation).
        self._asr_model_worker: _ModelDownloadWorker | None = None
        self._local_model_worker: _ModelDownloadWorker | None = None
        # Optional user-chosen folder for downloads ("" = derive automatically).
        self._youtube_download_dir = ""

        self._win_x = 60
        self._win_y = 60
        self._win_w = 1280
        self._win_h = 840

        # --- Redesign surfaces ------------------------------------------------
        # Accent preset (mirrors Theme.accentChoices), the persisted run history
        # and the row currently selected on the Log screen.
        self._accent_name = "iris"
        self._run_history_json = "[]"
        self._selected_run_index = -1
        self._history_ms_per_cue = 0.0
        self._run_started_clock = ""
        self._run_retry_count = 0
        self._run_window_count = 0
        self._run_metrics: dict = {}
        self._last_run_snapshot: dict = {}

        self.cue_model = CueResultModel(self)
        self.cue_proxy = CueFilterProxyModel(self)
        self.cue_proxy.setSourceModel(self.cue_model)
        self.quality_issues_model = QualityIssuesModel(self)
        # Let the UI react to edits made directly in the Review table (S-01).
        self.cue_model.editedCountChanged.connect(self.reviewDirtyChanged.emit)
        # Timing nudges and auto-fixes change the timeline and the inspector,
        # so republish them whenever any cue row changes.
        self._dist_cache: dict | None = None
        self.cue_model.dataChanged.connect(self._on_cue_data_changed)
        self.cue_model.modelReset.connect(self._on_cue_data_changed)

        self._load_persisted()

    _BOOL_FIELDS = {
        "_asr_no_tags",
        "_asr_keep_tags",
        "_local_mlock",
        "_strict_quality",
        "_context_summary",
        "_comfortable",
        "_reduced_motion",
    }

    _INT_FIELDS = {
        "_win_x",
        "_win_y",
        "_win_w",
        "_win_h",
    }

    def _load_persisted(self) -> None:
        # Loading stored values must not look like a user edit, or every launch
        # would start dirty and immediately rewrite the store.
        self._loading = True
        try:
            for attr, key, default in self._PERSISTED:
                value = self._settings.value(key, default)
                if attr in self._BOOL_FIELDS:
                    setattr(self, attr, str(value).lower() in ("1", "true", "yes"))
                elif attr in self._INT_FIELDS:
                    try:
                        setattr(self, attr, int(value))
                    except (TypeError, ValueError):
                        setattr(self, attr, default)
                elif isinstance(value, str):
                    setattr(self, attr, value)
            # Keep source mode and backend in lock-step with the saved pipeline
            # flow. A previous build used different IDs; migrate saved values
            # before deriving the source/backend fields the run builder consumes.
            legacy_modes = {
                "youtube": PIPELINE_MODE_YOUTUBE_CLOUD,
                "local_hybrid": PIPELINE_MODE_LOCAL_CLOUD,
                "local_offline": PIPELINE_MODE_OFFLINE,
            }
            self._pipeline_mode = legacy_modes.get(
                self._pipeline_mode, self._pipeline_mode
            )
            self._apply_pipeline_mode(self._pipeline_mode)
            # Recompute every derived binding (e.g. `localModelReady`,
            # `asrModelReady`, `backend`) against the just-loaded persisted
            # state. Without this a model the user previously selected would not
            # be reflected until some unrelated field changed.
            self._notify_form_changed()
        finally:
            self._loading = False

    def _persist_fields(self) -> None:
        for attr, key, default in self._PERSISTED:
            self._settings.setValue(key, getattr(self, attr, default))
        self._settings.sync()

    def _set_dirty(self, value: bool) -> None:
        if self._dirty != value:
            self._dirty = value
            self.dirtyChanged.emit()
            self.globalStatusChanged.emit()

    def _commit_pending(self) -> None:
        """Debounce target: write the store and tell the UI to show `Saved ✓`."""
        if not self._dirty:
            return
        self._persist_fields()
        self._set_dirty(False)
        self.savedToast.emit()

    def _notify_form_changed(self) -> None:
        """Emit formChanged plus every derived signal that depends on it.

        Readiness rows are derived from form state, so they must be recomputed
        whenever any form field changes. A genuine change also marks the store
        dirty and restarts the autosave debounce.
        """
        self.formChanged.emit()
        self.readinessChanged.emit()
        self.globalStatusChanged.emit()
        if not self._loading:
            self._set_dirty(True)
            self._save_timer.start()

    def _set_field(self, attr: str, value) -> None:
        if getattr(self, attr) != value:
            setattr(self, attr, value)
            self._notify_form_changed()

    def _append_log(self, text: str) -> None:
        self._log_text += text
        # Count newlines on the incoming chunk only. The QML badge used to
        # re-scan the whole log on every append (O(n^2) over a run).
        self._log_lines += text.count("\n")

        errors = warnings = 0
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if _LOG_ERROR_RE.search(line):
                errors += 1
            elif _LOG_WARN_RE.search(line):
                warnings += 1
            level = logging.ERROR if line.startswith("[error]") else logging.INFO
            self.logger.log(level, line)
            match = _DONE_PATTERN.match(line)
            if match:
                path = match.group("path").strip()
                if path:
                    self._resolved_out_path = os.path.abspath(path)
                    self.canOpenOutputFolderChanged.emit()

        if errors or warnings:
            self._log_error_count += errors
            self._log_warn_count += warnings
            self.logCountsChanged.emit()

        self._trim_log()
        self.logTextChanged.emit()

    def _trim_log(self) -> None:
        """Keep the log bounded so a long run cannot grow it without limit."""
        if self._log_lines <= _MAX_LOG_LINES:
            return
        lines = self._log_text.splitlines(keepends=True)
        if len(lines) <= _MAX_LOG_LINES:
            return
        self._log_text = _LOG_TRUNCATION_NOTICE + "".join(lines[-_MAX_LOG_LINES:])
        self._log_lines = _MAX_LOG_LINES + 1

    def _handle_log_line(self, line: str) -> None:
        """Route one stdout/stderr chunk: parse JSON progress, log the rest."""
        stripped = line.strip()
        if stripped.startswith("{") and '"type"' in stripped:
            try:
                obj = json.loads(stripped)
            except Exception:  # noqa: BLE001 - any parse failure => plain log
                obj = None
            if isinstance(obj, dict) and obj.get("type") == "progress":
                self._update_progress(obj)
                if not self._debug_json_progress:
                    return
        self._append_log(line)

    def _update_progress(self, obj: dict) -> None:
        stage = str(obj.get("stage", ""))
        try:
            done = int(obj.get("done", 0))
            total = int(obj.get("total", 0))
        except (TypeError, ValueError):
            done, total = 0, 0

        # Friendly labels: a static set for the stage strip, a dynamic one for
        # the status line.
        stage_labels = {
            "fetch": "Fetching subtitles",
            "asr": "Transcribing audio",
            "translate": "Translating",
            "write": "Writing output",
        }

        # Stage-transition bookkeeping for the legible progress panel (S-07):
        # keep an ordered list of visited stages and finalize each one's elapsed
        # time when the next stage begins.
        if stage and stage != self._progress_stage:
            now = time.time()
            if (self._progress_stage and self._stage_sequence
                    and self._stage_sequence[-1]["name"] == self._progress_stage):
                self._stage_sequence[-1]["elapsed"] = now - self._stage_started_at
            if not any(s["name"] == stage for s in self._stage_sequence):
                self._stage_sequence.append(
                    {"name": stage, "label": stage_labels.get(stage, stage), "elapsed": 0.0}
                )
            self._progress_stage = stage
            self._stage_started_at = now
            self.stageChanged.emit()

        self._progress_done = done
        self._progress_total = total

        # Heuristic ETA: cue throughput once translation is underway.
        if stage == "translate" and total > 0 and done > 0:
            elapsed_total = time.time() - self._run_started_at
            if elapsed_total > 0.5:
                rate = done / elapsed_total
                if rate > 0:
                    self._estimated_remaining_sec = int((total - done) / rate)

        labels = {
            "fetch": "Fetching subtitles…",
            "asr": "Transcribing audio…",
            "translate": f"Translating {done}/{total}…" if total else "Translating…",
            "write": "Writing output…",
        }
        message = labels.get(stage)
        if message:
            self._set_status(message)
        self.progressChanged.emit()

    def _set_status(self, text: str) -> None:
        if self._status_message != text:
            self._status_message = text
            self.statusMessageChanged.emit()

    def _set_status_state(self, state: str) -> None:
        if self._status_state != state:
            self._status_state = state
            self.statusStateChanged.emit()
            self.globalStatusChanged.emit()

    def _set_running(self, value: bool) -> None:
        if self._is_running != value:
            self._is_running = value
            self.isRunningChanged.emit()

    def _validate_batch(self) -> str:
        raw = (self._batch or "").strip()
        if not raw:
            return "8"
        value = int(raw)
        if value <= 0:
            raise ValueError("Batch size must be a positive integer.")
        return str(value)

    def _build_run_config(self) -> RunConfig:
        argv: list[str] = []
        env: dict[str, str] = {}

        # Always derive the input path from the pipeline flow actually selected
        # in the UI (single source of truth), so a local/offline selection can
        # never silently fall through to the YouTube/URL path.
        self._apply_pipeline_mode(self._pipeline_mode)

        if self._mode == "youtube":
            url = self._url.strip()
            if not url:
                raise ValueError("Enter a YouTube URL.")
            argv.append(url)
            source_lang = self._source_lang.strip()
            if source_lang:
                argv += ["--source-lang", source_lang]
        else:
            file_path = self._file_path.strip()
            if not file_path:
                raise ValueError("Choose a local file.")
            argv += ["--file", file_path]
            for flag, value in [
                ("--asr-bin", self.localPath(self._asr_bin)),
                ("--asr-vad-bin", self.localPath(self._asr_vad_bin)),
                ("--asr-model", self.localPath(self._asr_model)),
                ("--asr-vad-model", self.localPath(self._asr_vad_model)),
            ]:
                value = value.strip()
                if flag in ("--asr-model", "--asr-vad-model"):
                    filename = (
                        "fsmn-vad.gguf"
                        if flag == "--asr-vad-model"
                        else "sensevoice-small-q8.gguf"
                    )
                    if value and gguf_check.is_usable_gguf(value):
                        argv += [flag, value]
                        continue
                    # Resolve the model here and pass it explicitly. The CLI's
                    # own fallback is relative to the working directory, which
                    # is not the app folder for a frozen build — so leaving the
                    # flag out would make models the user already has invisible.
                    fallback = _find_model_file(filename)
                    if value:
                        # Never hand the CLI a model that cannot be loaded: it
                        # would burn minutes of preprocessing and then fail with
                        # an opaque ASR error.
                        _ok, reason = gguf_check.inspect_gguf(value)
                        self._append_log(
                            f"[warn] Ignoring {flag} {value}: {reason}. "
                            + (
                                f"Using {fallback} instead.\n"
                                if fallback
                                else f"No usable {filename} was found in the "
                                f"models folder.\n"
                            )
                        )
                    if fallback:
                        argv += [flag, fallback]
                    # With no usable model the flag is left out entirely, so the
                    # CLI reports the missing model itself.
                    continue
                if not value:
                    continue
                if not os.path.exists(value):
                    self._append_log(
                        f"[warn] Ignoring {flag} {value}: file not found.\n"
                    )
                    continue
                argv += [flag, value]
            argv += ["--asr-lang", (self._asr_language or "auto").strip() or "auto"]
            source_lang = self._source_lang.strip()
            if source_lang:
                argv += ["--source-lang", source_lang]
            argv += ["--asr-preprocess", (self._asr_preprocess or "auto").strip() or "auto"]
            argv += ["--asr-threads", str(self._asr_threads or 4)]
            argv += ["--asr-max-segment-ms", str(self._asr_max_segment_ms or 6000)]
            argv += ["--asr-max-end-silence-ms", str(self._asr_max_end_silence_ms or 250)]
            argv += [
                "--asr-speech-noise-threshold",
                str(self._asr_speech_noise_threshold or 0.55),
            ]
            argv += ["--asr-noise-db", str(self._asr_noise_db if self._asr_noise_db != "" else "-35")]
            argv += ["--asr-min-silence-s", str(self._asr_min_silence_s or 0.25)]
            argv += [
                "--asr-max-cue-duration-ms",
                str(self._asr_max_cue_duration_ms or 3200),
            ]
            argv += ["--asr-max-cue-chars", str(self._asr_max_cue_chars or 70)]
            argv += ["--asr-max-cue-chars-cjk", str(self._asr_max_cue_chars_cjk or 48)]
            if self._asr_no_tags:
                argv += ["--asr-no-tags"]
            if self._asr_keep_tags:
                argv += ["--asr-keep-tags"]

        out_path = self._out_path.strip()
        if out_path:
            argv += ["--out", out_path]

        fmt = (self._output_format or "srt").strip().lower() or "srt"
        argv += ["--format", fmt]

        argv += ["--batch", self._validate_batch()]

        # --- Preset / context flags -----------------------------------------
        preset = (self._content_preset or "auto").strip().lower() or "auto"
        if preset not in CONTENT_PRESETS:
            preset = "auto"
        argv += ["--content-preset", preset]
        context_mode = (self._context_mode or "").strip().lower()
        if context_mode:
            if context_mode not in CONTEXT_MODES:
                context_mode = ""
            else:
                argv += ["--context-mode", context_mode]
        if self._context_summary:
            argv += ["--context-summary"]

        # --- Translation consistency / quality flags -------------------------
        glossary_path = self.localPath(self._glossary_path).strip()
        if glossary_path:
            argv += ["--glossary", glossary_path]
        tm_mode = (self._translation_memory_mode or "auto").strip()
        if tm_mode and tm_mode != "auto":
            argv += ["--translation-memory", tm_mode]
        tm_db = self._translation_memory_db.strip()
        if tm_db:
            argv += ["--translation-memory-db", tm_db]
        if self._strict_quality:
            argv += ["--strict-quality"]

        # --- GUI machine interface -------------------------------------------
        # Structured result for the Review/Quality tabs + granular progress.
        argv += ["--json-progress", "--result-json", _result_json_path()]

        if self._pipeline_mode == PIPELINE_MODE_OFFLINE:
            argv += [
                "--local",
                "--local-host",
                (self._host or "127.0.0.1").strip() or "127.0.0.1",
                "--local-port",
                (self._port or "8080").strip() or "8080",
                "--local-model-name",
                (self._model_name or "Hy-MT2-1.8B-Q8_0").strip() or "Hy-MT2-1.8B-Q8_0",
            ]
            local_model = self._local_model.strip()
            if local_model:
                ok, reason = gguf_check.inspect_gguf(local_model)
                if not ok:
                    # The selected file is unusable (typically an interrupted
                    # download). Prefer a good copy in the models folder over
                    # failing the run on a file the user cannot see is broken.
                    fallback = _find_local_model()
                    self._append_log(
                        f"[warn] Local model {local_model} is unusable: {reason}. "
                        + (
                            f"Using {fallback} instead.\n"
                            if fallback
                            else "No usable model was found in the models folder.\n"
                        )
                    )
                    local_model = fallback
            else:
                # Self-contained desktop app: auto-pick a bundled translation
                # model if one is present; otherwise fail fast with clear
                # guidance instead of silently hanging against an empty port.
                local_model = _find_local_model()
            if local_model:
                argv += ["--local-model", local_model]
            else:
                raise ValueError(
                    "No usable local translation model found. Download it via "
                    "Settings → Models & storage (fetches Hy-MT2-1.8B-Q8_0.gguf) "
                    "or Browse to select a GGUF file. If a model file is already "
                    "there, it is incomplete — re-download it."
                )
            local_threads = int(self._local_threads or 0)
            if local_threads > 0:
                argv += ["--local-threads", str(local_threads)]
            if self._local_mlock:
                argv += ["--local-mlock"]
        else:
            model = self._model.strip()
            if model:
                argv += ["--model", model]
            api_key = self._api_key.strip()
            if api_key:
                env["OPENAI_API_KEY"] = api_key
            base_url = self._base_url.strip()
            if base_url:
                env["OPENAI_BASE_URL"] = base_url

        return RunConfig(argv=argv, env=env)

    @Property(str, notify=formChanged)
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        self._set_field("_mode", value)

    @Property(str, notify=pipelineModeChanged)
    def pipelineMode(self) -> str:
        return self._pipeline_mode

    @pipelineMode.setter
    def pipelineMode(self, value: str) -> None:
        value = (value or "").strip().lower() or PIPELINE_MODE_YOUTUBE_CLOUD
        legacy_modes = {
            "youtube": PIPELINE_MODE_YOUTUBE_CLOUD,
            "local_hybrid": PIPELINE_MODE_LOCAL_CLOUD,
            "local_offline": PIPELINE_MODE_OFFLINE,
        }
        value = legacy_modes.get(value, value)
        if value not in (
            PIPELINE_MODE_YOUTUBE_CLOUD,
            PIPELINE_MODE_LOCAL_CLOUD,
            PIPELINE_MODE_OFFLINE,
        ):
            value = PIPELINE_MODE_YOUTUBE_CLOUD
        if self._pipeline_mode != value:
            self._pipeline_mode = value
            self._apply_pipeline_mode(value)
            self.pipelineModeChanged.emit()
            self._notify_form_changed()

    @Slot(str)
    def setPipelineMode(self, mode: str) -> None:
        self.pipelineMode = mode

    def _apply_pipeline_mode(self, mode: str) -> None:
        if mode == PIPELINE_MODE_YOUTUBE_CLOUD:
            self._mode = "youtube"
            self._backend = "cloud"
        elif mode == PIPELINE_MODE_LOCAL_CLOUD:
            self._mode = "file"
            self._backend = "cloud"
        else:
            self._mode = "file"
            self._backend = "local"

    # --- Two-axis source x engine (UI review 6.1) -------------------------
    #
    # The old control flattened two orthogonal axes into three cells
    # (`YouTube Cloud` / `Local Cloud` / `Offline`), which produced the
    # "Local Cloud" oxymoron and hid the fourth combination entirely. Source and
    # engine are now independent, and the matrix is honest: the combination that
    # is genuinely unsupported says so instead of being silently impossible.
    #
    # `pipelineMode` stays as the derived 3-value id the run builder consumes.

    _RUN_SOURCES = ("youtube", "localfile")
    _RUN_ENGINES = ("cloud", "local")

    @Property(str, notify=pipelineModeChanged)
    def runSource(self) -> str:
        return "youtube" if self._mode == "youtube" else "localfile"

    @Property(str, notify=pipelineModeChanged)
    def runEngine(self) -> str:
        return "local" if self._backend == "local" else "cloud"

    @Property(str, notify=pipelineModeChanged)
    def engineLocalDisabledReason(self) -> str:
        """Why the local engine is unavailable for the current source.

        A combination the product cannot run must be *visibly disabled with a
        stated reason*, never silently impossible.
        """
        # The test is on the SOURCE axis, not on the current pair. Testing the
        # pair made this unreachable: `pipelineMode` can only ever hold one of
        # the three supported combinations, so `youtube + local` is never the
        # current state and the reason never rendered. What the UI needs to know
        # is "can the local engine be *selected* right now", and that depends on
        # the source alone.
        if self.runSource == "youtube":
            return ("A downloaded video would have to be transcribed first, which the "
                    "YouTube path does not do. Save the video and switch the source "
                    "to a local file to use the local engine.")
        return ""

    @Property(str, notify=pipelineModeChanged)
    def sourceEngineSummary(self) -> str:
        """One-line description of the active pair, for the selectors' caption."""
        source = "YouTube URL" if self.runSource == "youtube" else "Local media file"
        engine = "Local model" if self.runEngine == "local" else "Cloud LLM"
        return source + " \u2192 " + engine

    @Slot(str, str, result=str)
    def setSourceEngine(self, source: str, engine: str) -> str:
        """Set both axes at once. Returns "" on success, or a reason on refusal."""
        source = (source or "").strip().lower()
        engine = (engine or "").strip().lower()
        if source not in self._RUN_SOURCES:
            return "Unknown source."
        if engine not in self._RUN_ENGINES:
            return "Unknown engine."
        if source == "youtube" and engine == "local":
            return ("YouTube + local model is not supported: the video would have to "
                    "be transcribed first. Use a local file, or the cloud engine.")
        if source == "youtube":
            self.pipelineMode = PIPELINE_MODE_YOUTUBE_CLOUD
        elif engine == "local":
            self.pipelineMode = PIPELINE_MODE_OFFLINE
        else:
            self.pipelineMode = PIPELINE_MODE_LOCAL_CLOUD
        return ""

    @Slot(str, result=str)
    def setRunSource(self, source: str) -> str:
        return self.setSourceEngine(source, self.runEngine)

    @Slot(str, result=str)
    def setRunEngine(self, engine: str) -> str:
        return self.setSourceEngine(self.runSource, engine)

    @Property(str, notify=formChanged)
    def backend(self) -> str:
        return self._backend

    @backend.setter
    def backend(self, value: str) -> None:
        self._set_field("_backend", value)

    @Property(str, notify=formChanged)
    def url(self) -> str:
        return self._url

    @url.setter
    def url(self, value: str) -> None:
        value = (value or "").strip()
        if self._url != value:
            self._url = value
            # Stop any in-flight downloads for the previous URL and drop its
            # stale inspection results.
            for worker in (self._youtube_video_worker, self._youtube_sub_worker):
                if worker is not None:
                    worker.cancel()
            self._youtube_video_worker = None
            self._youtube_sub_worker = None
            # An inspection still running for the old URL must never repopulate
            # the panel once the URL changed: dropping the reference AND
            # bumping the generations makes any completion a no-op (the
            # stale-guards compare payload tags, not senders). The loading
            # flag MUST be cleared with the ref, or the dropped completion
            # leaves "Inspecting…" stuck on forever and every retry click
            # early-returns.
            self._youtube_info_worker = None
            self._youtube_info_loading = False
            self._youtube_info_gen += 1
            self._youtube_video_gen += 1
            self._youtube_sub_gen += 1
            self._youtube_video_downloading = False
            self._youtube_video_progress = 0
            self._youtube_video_status = ""
            self._youtube_sub_downloading = False
            self._youtube_sub_status = ""
            self._youtube_downloading = False
            self._youtube_formats = []
            self._youtube_matrix = {}
            self._youtube_best = {}
            self._youtube_codec_ids = []
            self._youtube_resolutions = []
            self._youtube_selected_codec = "best"
            self._youtube_selected_resolution = "best"
            self._youtube_info_error = ""
            self._youtube_title = ""
            self._youtube_has_av1 = self._youtube_has_vp9 = self._youtube_has_h264 = False
            self._youtube_has_en_subtitle = False
            self._youtube_downloaded_video = ""
            self._youtube_downloaded_subtitle = ""
            self._notify_form_changed()
            self.youtubeInfoChanged.emit()
            self.youtubeDownloadChanged.emit()

    @Property(str, notify=formChanged)
    def filePath(self) -> str:
        return self._file_path

    @filePath.setter
    def filePath(self, value: str) -> None:
        changed = self._file_path != value
        self._set_field("_file_path", value)
        if changed:
            self._sync_auto_out_path()

    @Property(str, notify=formChanged)
    def sourceLang(self) -> str:
        return self._source_lang

    @sourceLang.setter
    def sourceLang(self, value: str) -> None:
        self._set_field("_source_lang", value)

    @Property(str, notify=formChanged)
    def outPath(self) -> str:
        return self._out_path

    @outPath.setter
    def outPath(self, value: str) -> None:
        """Set the output path explicitly; a blank value returns to "auto"."""
        value = value or ""
        self._out_path_auto = not value.strip()
        self._set_field("_out_path", value)
        if self._out_path_auto:
            # Clearing the field means "put it back next to the video", not
            # "write nothing" — otherwise the run falls back to the process
            # working directory, which is the bug this whole path exists to fix.
            self._sync_auto_out_path(force=True)

    @Property(bool, notify=formChanged)
    def outPathAuto(self) -> bool:
        """True while the output path is still derived from the input file."""
        return self._out_path_auto

    @Property(str, notify=formChanged)
    def outPathHint(self) -> str:
        """One line explaining where the subtitles will land."""
        if not self._out_path_auto and self._out_path.strip():
            return ""
        if (self._file_path or "").strip():
            return "Saved next to the video, with the same name."
        if self._pipeline_mode == PIPELINE_MODE_YOUTUBE_CLOUD:
            return "Saved next to the downloaded video, named after the title."
        return "Pick a video, or type a path."

    @Slot()
    def useAutoOutPath(self) -> None:
        """Forget the manual path and go back to "next to the input file"."""
        self._out_path_auto = True
        self._sync_auto_out_path(force=True)

    def _sync_auto_out_path(self, force: bool = False) -> None:
        """Keep the output path glued to the input while it is on auto.

        Picking ``C:\\clips\\talk.mp4`` should fill in ``C:\\clips\\talk.srt``
        without the user typing anything, and it must follow a later change of
        the input file or of the output format. A YouTube run has no local file
        yet, so it uses the download folder plus the video title — that puts the
        subtitle beside the video the app just downloaded. Once the user edits
        the field themselves, ``_out_path_auto`` is False and this stops
        touching it.
        """
        if not self._out_path_auto and not force:
            return
        derived = ""
        source = (self._file_path or "").strip()
        if source:
            derived = translate.default_output_path(
                source, "", self._output_format or "srt"
            )
        else:
            title = (self._youtube_title or "").strip()
            if title and self._pipeline_mode == PIPELINE_MODE_YOUTUBE_CLOUD:
                ext = "." + (self._output_format or "srt").strip().lstrip(".")
                derived = os.path.join(
                    self._youtube_out_dir(), srt_io.sanitize_filename(title) + ext
                )
        if self._out_path != derived:
            self._out_path = derived
            self._notify_form_changed()

    @Property(str, notify=formChanged)
    def batch(self) -> str:
        return self._batch

    @batch.setter
    def batch(self, value: str) -> None:
        self._set_field("_batch", value)

    @Property(str, notify=formChanged)
    def apiKey(self) -> str:
        return self._api_key

    @apiKey.setter
    def apiKey(self, value: str) -> None:
        self._set_field("_api_key", value)

    @Property(str, notify=formChanged)
    def baseUrl(self) -> str:
        return self._base_url

    @baseUrl.setter
    def baseUrl(self, value: str) -> None:
        self._set_field("_base_url", value)

    @Property(str, notify=formChanged)
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        self._set_field("_model", value)

    # --- Effective cloud credentials + provenance (UI review 1.4, 5.7) -----
    #
    # The cloud fields can each inherit from `.env`. The UI shows the value that
    # is actually in effect with the source as secondary text, instead of a
    # placeholder that vanishes on focus.

    @Property(str, notify=formChanged)
    def effectiveApiKeyText(self) -> str:
        """Masked key + provenance. Never renders the secret itself."""
        value, source = _setting_provenance(self._api_key, "OPENAI_API_KEY")
        if value:
            return "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022  \u00b7  " + source
        base = (self._base_url or "").strip() or os.environ.get("OPENAI_BASE_URL", "")
        if _is_local_host(base):
            return "not required for a local endpoint"
        return "not set \u2014 the run will ask for one"

    @Property(str, notify=formChanged)
    def effectiveBaseUrlText(self) -> str:
        value, source = _setting_provenance(self._base_url, "OPENAI_BASE_URL")
        return f"{value}  \u00b7  {source}" if value else "provider default (api.openai.com)"

    @Property(str, notify=formChanged)
    def effectiveModelText(self) -> str:
        value, source = _setting_provenance(self._model, "OPENAI_MODEL")
        return f"{value}  \u00b7  {source}" if value else "not set \u2014 the run will ask for one"

    @Property(bool, notify=formChanged)
    def effectiveModelInherited(self) -> bool:
        """True when the model comes from somewhere other than this field."""
        return not (self._model or "").strip()

    @Property(str, notify=formChanged)
    def host(self) -> str:
        return self._host

    @host.setter
    def host(self, value: str) -> None:
        self._set_field("_host", value)

    @Property(str, notify=formChanged)
    def port(self) -> str:
        return self._port

    @port.setter
    def port(self, value: str) -> None:
        self._set_field("_port", value)

    @Property(str, notify=formChanged)
    def modelName(self) -> str:
        return self._model_name

    @modelName.setter
    def modelName(self, value: str) -> None:
        self._set_field("_model_name", value)

    @Property(str, notify=formChanged)
    def localModel(self) -> str:
        return self._local_model

    @localModel.setter
    def localModel(self, value: str) -> None:
        self._set_field("_local_model", value)

    @Property(bool, notify=formChanged)
    def localModelReady(self) -> bool:
        """True when a *complete* translation GGUF is available.

        A file that merely exists is not enough: an interrupted download leaves
        a partial file behind, and reporting that as ready is what made the
        offline flow fail with an opaque ASR/server error. Use
        :attr:`localModelState` to tell "missing" apart from "corrupt".
        """
        return self.localModelState == MODEL_STATE_READY

    @Property(str, notify=formChanged)
    def localModelState(self) -> str:
        """``ready`` / ``missing`` / ``corrupt`` for the local translation model."""
        try:
            state, _path, _reason = _resolve_model_status(
                self._local_model, _find_local_model()
            )
            return state
        except Exception:  # noqa: BLE001 - never break the UI on a stat error
            return MODEL_STATE_MISSING

    @Property(str, notify=formChanged)
    def localModelProblem(self) -> str:
        """Why the selected local translation model is unusable ("" when fine)."""
        try:
            state, path, reason = _resolve_model_status(
                self._local_model, _find_local_model()
            )
            if state == MODEL_STATE_CORRUPT:
                return f"{os.path.basename(path)}: {reason}"
        except Exception:  # noqa: BLE001
            return ""
        return ""

    @Property(bool, notify=formChanged)
    def localModelCorrupt(self) -> bool:
        """True when a model file exists but is incomplete/unreadable."""
        return self.localModelState == MODEL_STATE_CORRUPT

    @Property(str, notify=formChanged)
    def localModelSelectionProblem(self) -> str:
        """Why the *selected* model path is unusable, even if a fallback exists.

        ``localModelState`` reports the model a run would actually use, so a
        corrupt selection is masked by a good copy in the models folder. The
        Settings field still shows the user's own path, so it needs its own
        explanation rather than silently appearing to work.
        """
        try:
            state, reason = _model_status(self._local_model)
        except Exception:  # noqa: BLE001 - never break the UI on a stat error
            logging.getLogger("translation_agent").debug(
                "localModelSelectionProblem failed", exc_info=True
            )
            return ""
        if state == MODEL_STATE_CORRUPT:
            return (
                f"This file is incomplete ({reason}). Re-download it, or "
                f"clear the field to use the models folder."
            )
        return ""

    @Property(bool, notify=localModelDownloadPendingChanged)
    def localModelDownloadPending(self) -> bool:
        return self._local_model_download_pending

    @Property(str, notify=formChanged)
    def contentPreset(self) -> str:
        return self._content_preset

    @contentPreset.setter
    def contentPreset(self, value: str) -> None:
        value = (value or "auto").strip().lower()
        if value not in CONTENT_PRESETS:
            value = "auto"
        self._set_field("_content_preset", value)

    @Property(str, notify=formChanged)
    def contextMode(self) -> str:
        return self._context_mode

    @contextMode.setter
    def contextMode(self, value: str) -> None:
        value = (value or "").strip().lower()
        if value not in CONTEXT_MODES:
            value = ""
        self._set_field("_context_mode", value)

    @Property(bool, notify=formChanged)
    def contextSummary(self) -> bool:
        return self._context_summary

    @contextSummary.setter
    def contextSummary(self, value: bool) -> None:
        value = bool(value)
        if self._context_summary != value:
            self._context_summary = value
            self._notify_form_changed()

    @Property(str, notify=formChanged)
    def asrLanguage(self) -> str:
        return self._asr_language

    @asrLanguage.setter
    def asrLanguage(self, value: str) -> None:
        self._set_field("_asr_language", value)

    @Property(str, notify=formChanged)
    def asrPreprocess(self) -> str:
        return self._asr_preprocess

    @asrPreprocess.setter
    def asrPreprocess(self, value: str) -> None:
        value = (value or "auto").strip().lower()
        if value not in ASR_PREPROCESS_PROFILES:
            value = "auto"
        self._set_field("_asr_preprocess", value)

    @Property(str, notify=formChanged)
    def asrBin(self) -> str:
        return self._asr_bin

    @asrBin.setter
    def asrBin(self, value: str) -> None:
        self._set_field("_asr_bin", value)

    @Property(str, notify=formChanged)
    def asrVadBin(self) -> str:
        return self._asr_vad_bin

    @asrVadBin.setter
    def asrVadBin(self, value: str) -> None:
        self._set_field("_asr_vad_bin", value)

    @Property(str, notify=formChanged)
    def asrModel(self) -> str:
        return self._asr_model

    @asrModel.setter
    def asrModel(self, value: str) -> None:
        self._set_field("_asr_model", value)

    @Property(str, notify=formChanged)
    def asrVadModel(self) -> str:
        return self._asr_vad_model

    @asrVadModel.setter
    def asrVadModel(self, value: str) -> None:
        self._set_field("_asr_vad_model", value)

    @Property(bool, notify=formChanged)
    def asrModelReady(self) -> bool:
        """True when both the SenseVoice and VAD GGUFs are present and complete.

        Both are required for local transcription; checking only for the
        SenseVoice file let a machine with a missing or truncated VAD model
        report "ASR ready" and then fail mid-run.
        """
        return self.asrModelState == MODEL_STATE_READY

    @Property(str, notify=formChanged)
    def asrModelState(self) -> str:
        """``ready`` / ``missing`` / ``corrupt`` for the local ASR models."""
        try:
            sense_state, _, _ = _resolve_model_status(
                self._asr_model, _find_model_file("sensevoice-small-q8.gguf")
            )
            vad_state, _, _ = _resolve_model_status(
                self._asr_vad_model, _find_model_file("fsmn-vad.gguf")
            )
            if MODEL_STATE_CORRUPT in (sense_state, vad_state):
                return MODEL_STATE_CORRUPT
            if MODEL_STATE_MISSING in (sense_state, vad_state):
                return MODEL_STATE_MISSING
            return MODEL_STATE_READY
        except Exception:  # noqa: BLE001
            return MODEL_STATE_MISSING

    @Property(str, notify=formChanged)
    def asrModelProblem(self) -> str:
        """Why the ASR models are unusable ("" when they are fine)."""
        try:
            for label, selected, fallback in (
                ("SenseVoice", self._asr_model,
                 _find_model_file("sensevoice-small-q8.gguf")),
                ("VAD", self._asr_vad_model, _find_model_file("fsmn-vad.gguf")),
            ):
                state, path, reason = _resolve_model_status(selected, fallback)
                if state == MODEL_STATE_CORRUPT:
                    return f"{label} model {os.path.basename(path)}: {reason}"
        except Exception:  # noqa: BLE001
            return ""
        return ""

    @Property(bool, notify=formChanged)
    def asrModelCorrupt(self) -> bool:
        """True when an ASR model file exists but is incomplete/unreadable."""
        return self.asrModelState == MODEL_STATE_CORRUPT

    @Property(str, notify=formChanged)
    def asrModelSelectionProblem(self) -> str:
        """Why a *selected* ASR/VAD model path is unusable ("" when it is fine).

        Unlike :attr:`asrModelProblem` this ignores the models-folder fallback,
        so the Settings fields can flag the user's own path.
        """
        try:
            for label, selected in (
                ("SenseVoice model", self._asr_model),
                ("VAD model", self._asr_vad_model),
            ):
                state, reason = _model_status(selected)
                if state == MODEL_STATE_CORRUPT:
                    return (
                        f"{label} is incomplete ({reason}). Re-download it, or "
                        f"clear the field to use the models folder."
                    )
        except Exception:  # noqa: BLE001 - never break the UI on a stat error
            logging.getLogger("translation_agent").debug(
                "asrModelSelectionProblem failed", exc_info=True
            )
            return ""
        return ""

    @Property(str, notify=formChanged)
    def asrThreads(self) -> str:
        return self._asr_threads

    @asrThreads.setter
    def asrThreads(self, value: str) -> None:
        self._set_field("_asr_threads", value)

    @Property(str, notify=formChanged)
    def asrMaxSegmentMs(self) -> str:
        return self._asr_max_segment_ms

    @asrMaxSegmentMs.setter
    def asrMaxSegmentMs(self, value: str) -> None:
        self._set_field("_asr_max_segment_ms", value)

    @Property(str, notify=formChanged)
    def asrMaxEndSilenceMs(self) -> str:
        return self._asr_max_end_silence_ms

    @asrMaxEndSilenceMs.setter
    def asrMaxEndSilenceMs(self, value: str) -> None:
        self._set_field("_asr_max_end_silence_ms", value)

    @Property(str, notify=formChanged)
    def asrSpeechNoiseThreshold(self) -> str:
        return self._asr_speech_noise_threshold

    @asrSpeechNoiseThreshold.setter
    def asrSpeechNoiseThreshold(self, value: str) -> None:
        self._set_field("_asr_speech_noise_threshold", value)

    @Property(str, notify=formChanged)
    def asrNoiseDb(self) -> str:
        return self._asr_noise_db

    @asrNoiseDb.setter
    def asrNoiseDb(self, value: str) -> None:
        self._set_field("_asr_noise_db", value)

    @Property(str, notify=formChanged)
    def asrMinSilenceS(self) -> str:
        return self._asr_min_silence_s

    @asrMinSilenceS.setter
    def asrMinSilenceS(self, value: str) -> None:
        self._set_field("_asr_min_silence_s", value)

    @Property(str, notify=formChanged)
    def asrMaxCueDurationMs(self) -> str:
        return self._asr_max_cue_duration_ms

    @asrMaxCueDurationMs.setter
    def asrMaxCueDurationMs(self, value: str) -> None:
        self._set_field("_asr_max_cue_duration_ms", value)

    @Property(str, notify=formChanged)
    def asrMaxCueChars(self) -> str:
        return self._asr_max_cue_chars

    @asrMaxCueChars.setter
    def asrMaxCueChars(self, value: str) -> None:
        self._set_field("_asr_max_cue_chars", value)

    @Property(bool, notify=formChanged)
    def asrNoTags(self) -> bool:
        return self._asr_no_tags

    @asrNoTags.setter
    def asrNoTags(self, value: bool) -> None:
        value = bool(value)
        if self._asr_no_tags != value:
            self._asr_no_tags = value
            self._notify_form_changed()

    @Property(str, notify=formChanged)
    def asrMaxCueCharsCjk(self) -> str:
        return self._asr_max_cue_chars_cjk

    @asrMaxCueCharsCjk.setter
    def asrMaxCueCharsCjk(self, value: str) -> None:
        self._set_field("_asr_max_cue_chars_cjk", value)

    @Property(bool, notify=formChanged)
    def asrKeepTags(self) -> bool:
        return self._asr_keep_tags

    @asrKeepTags.setter
    def asrKeepTags(self, value: bool) -> None:
        value = bool(value)
        if self._asr_keep_tags != value:
            self._asr_keep_tags = value
            self._notify_form_changed()

    @Property(str, notify=formChanged)
    def glossaryPath(self) -> str:
        return self._glossary_path

    @glossaryPath.setter
    def glossaryPath(self, value: str) -> None:
        self._set_field("_glossary_path", value)

    @Property(str, notify=formChanged)
    def translationMemoryMode(self) -> str:
        return self._translation_memory_mode

    @translationMemoryMode.setter
    def translationMemoryMode(self, value: str) -> None:
        self._set_field("_translation_memory_mode", value)

    @Property(str, notify=formChanged)
    def translationMemoryDbPath(self) -> str:
        return self._translation_memory_db

    @translationMemoryDbPath.setter
    def translationMemoryDbPath(self, value: str) -> None:
        self._set_field("_translation_memory_db", value)

    @Property(str, notify=formChanged)
    def localThreads(self) -> str:
        return self._local_threads

    @localThreads.setter
    def localThreads(self, value: str) -> None:
        self._set_field("_local_threads", value)

    @Property(bool, notify=formChanged)
    def localMlock(self) -> bool:
        return self._local_mlock

    @localMlock.setter
    def localMlock(self, value: bool) -> None:
        value = bool(value)
        if self._local_mlock != value:
            self._local_mlock = value
            self._notify_form_changed()

    @Property(bool, notify=formChanged)
    def strictQuality(self) -> bool:
        return self._strict_quality

    @strictQuality.setter
    def strictQuality(self, value: bool) -> None:
        value = bool(value)
        if self._strict_quality != value:
            self._strict_quality = value
            self._notify_form_changed()

    @Property(str, notify=formChanged)
    def outputFormat(self) -> str:
        return self._output_format

    @outputFormat.setter
    def outputFormat(self, value: str) -> None:
        value = (value or "srt").strip().lower()
        if value not in ("srt", "ass"):
            value = "srt"
        self._set_field("_output_format", value)
        # Switching srt <-> ass must also move an auto-derived output path, or
        # the field would still say .srt while the run writes .ass.
        self._sync_auto_out_path()

    @Property(str, notify=statusMessageChanged)
    def statusMessage(self) -> str:
        return self._status_message

    @Property(str, notify=statusStateChanged)
    def statusState(self) -> str:
        return self._status_state

    # --- Global status strip (UI review 3.1) ------------------------------
    #
    # One derived, read-only line for the top bar, composed from the store:
    #   "● Ready · YouTube → Cloud LLM · English out · Saved"
    # It replaces the scattered `Ready` / `Strict gate off` / `No report yet`
    # pills, so there is a single honest mirror instead of several that could
    # disagree. Derived in Python so it is testable.

    @Property(str, notify=globalStatusChanged)
    def globalStatusText(self) -> str:
        return "  \u00b7  ".join(self._global_status_parts())

    @Property(str, notify=globalStatusChanged)
    def globalStatusTone(self) -> str:
        """One of ok / warn / err / acc / mute, for the strip's leading dot."""
        if self._status_state == "failed":
            return "err"
        if self._status_state in ("running", "validating"):
            return "acc"
        if self._status_state == "cancelled":
            return "warn"
        if self._status_state == "done":
            return "ok"
        actionable = self.readinessActionableCount
        ready = self.readinessReadyCount
        if actionable and ready < actionable:
            return "warn"
        return "ok" if actionable else "mute"

    def _global_status_parts(self) -> list[str]:
        """The composed segments, in reading order."""
        state = self._status_state
        if state == "running" or state == "validating":
            head = "Running"
        elif state == "done":
            head = "Done"
        elif state == "failed":
            head = "Failed"
        elif state == "cancelled":
            head = "Cancelled"
        else:
            actionable = self.readinessActionableCount
            ready = self.readinessReadyCount
            head = "Ready" if (actionable and ready == actionable) else "Not ready"

        if self._pipeline_mode == PIPELINE_MODE_YOUTUBE_CLOUD:
            flow = "YouTube \u2192 Cloud LLM"
        elif self._pipeline_mode == PIPELINE_MODE_LOCAL_CLOUD:
            flow = "Local file \u2192 Local ASR \u2192 Cloud LLM"
        else:
            flow = "Local file \u2192 Local ASR \u2192 Local LLM"

        parts = [head, flow, "English out"]
        if self._dirty:
            parts.append("Unsaved changes")
        return parts

    @Property(str, notify=logTextChanged)
    def logText(self) -> str:
        return self._log_text

    @Property(int, notify=logCountsChanged)
    def logErrorCount(self) -> int:
        """Errors counted incrementally as lines arrive (never re-scanned)."""
        return self._log_error_count

    @Property(int, notify=logCountsChanged)
    def logWarnCount(self) -> int:
        return self._log_warn_count

    @Property(bool, notify=logVisibleChanged)
    def logVisible(self) -> bool:
        return self._log_visible

    @logVisible.setter
    def logVisible(self, value: bool) -> None:
        value = bool(value)
        if self._log_visible != value:
            self._log_visible = value
            self.logVisibleChanged.emit()

    @Property(bool, notify=isRunningChanged)
    def isRunning(self) -> bool:
        return self._is_running

    @Property(bool, notify=canOpenOutputFolderChanged)
    def canOpenOutputFolder(self) -> bool:
        return bool(self._resolved_out_path)

    @Property(str, notify=modelDownloadChanged)
    def modelDownloadStatus(self) -> str:
        return self._model_download_status

    @Property(bool, notify=modelDownloadChanged)
    def modelDownloading(self) -> bool:
        return self._model_downloading

    @Property(str, notify=modelDownloadChanged)
    def localModelDownloadStatus(self) -> str:
        return self._local_model_download_status

    @Property(bool, notify=modelDownloadChanged)
    def localModelDownloading(self) -> bool:
        return self._local_model_downloading

    # --- Progress + result-review properties ---------------------------------

    @Property(str, notify=progressChanged)
    def progressStage(self) -> str:
        return self._progress_stage

    @Property(int, notify=progressChanged)
    def progressDone(self) -> int:
        return self._progress_done

    @Property(int, notify=progressChanged)
    def progressTotal(self) -> int:
        return self._progress_total

    @Property("QVariantList", notify=stageChanged)
    def stageList(self) -> list:
        """Ordered list of visited stages: [{"name","label","elapsed"}]."""
        seq = [dict(s) for s in self._stage_sequence]
        if (self._is_running and self._progress_stage and seq
                and seq[-1]["name"] == self._progress_stage):
            seq[-1]["elapsed"] = time.time() - self._stage_started_at
        return seq

    @Property(int, notify=stageChanged)
    def currentStageElapsed(self) -> int:
        if not self._is_running:
            return int(self._stage_elapsed_sec)
        return int(time.time() - self._stage_started_at)

    # --- Stage strip (UI review 6.2, 6.6) ---------------------------------
    #
    # The middle column used to be called `PIPELINE` while being a form, so the
    # name over-promised a flow that did not exist. The column is now
    # `Processing`, and this is the strip that actually honours the name: five
    # canonical stages, idle-grey normally, lighting per stage during a run,
    # and halting on the failing stage when a run fails.

    _CANONICAL_STAGES = (
        ("source", "Source"),
        ("transcribe", "Transcribe"),
        ("translate", "Translate"),
        ("gate", "Gate"),
        ("write", "Write"),
    )

    # Worker stage id -> canonical stage id.
    _STAGE_ALIASES = {
        "fetch": "source",
        "asr": "transcribe",
        "translate": "translate",
        "write": "write",
        "gate": "gate",
    }

    @Property("QVariantList", notify=stageChanged)
    def pipelineStages(self) -> list:
        """Canonical stages with a per-stage state for the Run strip.

        States: ``pending`` | ``active`` | ``done`` | ``failed`` | ``skipped``.
        ``skipped`` is a fact about the mode, not a problem: YouTube mode never
        runs the transcribe stage, and the gate is skipped when it is off.
        """
        visited: list[str] = []
        for entry in self._stage_sequence:
            canonical = self._STAGE_ALIASES.get(entry.get("name", ""), "")
            if canonical and canonical not in visited:
                visited.append(canonical)
        current = self._STAGE_ALIASES.get(self._progress_stage, "")
        failed = self._status_state == "failed"

        rows = []
        for stage_id, label in self._CANONICAL_STAGES:
            if stage_id == "transcribe" and self._pipeline_mode == PIPELINE_MODE_YOUTUBE_CLOUD:
                state = "skipped"
            elif stage_id == "gate" and not self._strict_quality:
                state = "skipped"
            elif failed and stage_id == current:
                state = "failed"
            elif self._is_running and stage_id == current:
                state = "active"
            elif stage_id in visited:
                # Everything visited before the current stage is finished.
                state = "done" if stage_id != current or not self._is_running else "active"
            else:
                state = "pending"
            rows.append({"id": stage_id, "label": label, "state": state})
        return rows

    @Property(int, notify=stageChanged)
    def pipelineStageIndex(self) -> int:
        """Index of the active (or halted) stage, or -1 when idle."""
        for i, row in enumerate(self.pipelineStages):
            if row["state"] in ("active", "failed"):
                return i
        return -1

    @Property(int, notify=stageChanged)
    def pipelineStageTotal(self) -> int:
        return len(self._CANONICAL_STAGES)

    @Property(int, notify=progressChanged)
    def estimatedRemainingSec(self) -> int:
        return int(self._estimated_remaining_sec)

    @Property(int, notify=stageChanged)
    def runElapsedSec(self) -> int:
        if not self._run_started_at:
            return 0
        end = time.time() if self._is_running else self._run_started_at + self._stage_elapsed_sec
        return int(end - self._run_started_at)

    @Property(bool, notify=resultReadyChanged)
    def resultReady(self) -> bool:
        return self._result_ready

    @Property(str, notify=resultReadyChanged)
    def outputPathResolved(self) -> str:
        return self._resolved_out_path

    @Property(str, notify=resultReadyChanged)
    def resultStrictState(self) -> str:
        return self._result_strict_state

    @Property(int, notify=resultReadyChanged)
    def qualityTotalCues(self) -> int:
        return int(self._quality_summary.get("cue_count", 0))

    @Property(int, notify=resultReadyChanged)
    def qualityUntranslated(self) -> int:
        return int(
            self._quality_summary.get("untranslated_count", 0)
            + self._quality_summary.get("untranslated_marker_count", 0)
        )

    @Property(int, notify=resultReadyChanged)
    def qualityErrors(self) -> int:
        return int(self._quality_summary.get("error_count", 0))

    @Property(int, notify=resultReadyChanged)
    def qualityWarnings(self) -> int:
        return int(self._quality_summary.get("warning_count", 0))

    @Property(float, notify=resultReadyChanged)
    def qualityAverageCps(self) -> float:
        return float(self._quality_summary.get("average_cps", 0.0))

    @Property(int, notify=resultReadyChanged)
    def qualityMaxLineChars(self) -> int:
        return int(self._quality_summary.get("max_line_chars", 0))

    @Property(bool, notify=debugJsonProgressChanged)
    def debugJsonProgress(self) -> bool:
        return self._debug_json_progress

    @debugJsonProgress.setter
    def debugJsonProgress(self, value: bool) -> None:
        value = bool(value)
        if self._debug_json_progress != value:
            self._debug_json_progress = value
            self.debugJsonProgressChanged.emit()

    @Property(str, notify=resultReadyChanged)
    def qualityAverageCpsText(self) -> str:
        """Avg CPS pre-formatted for display.

        The Quality tab used to call `toFixed(1)` directly on this value in QML;
        when the summary was unavailable that raised inside a binding, which Qt
        swallows silently and the badge simply rendered empty. Formatting in
        Python keeps it testable and unconditionally safe.
        """
        if not self._result_ready or not self._quality_summary:
            return "\u2014"
        try:
            return f"{float(self._quality_summary.get('average_cps', 0.0)):.1f}"
        except (TypeError, ValueError):
            return "\u2014"

    # --- Appearance / ergonomics (UX review S-10) --------------------------
    @Property(str, notify=themeChanged)
    def themeName(self) -> str:
        return self._theme_name

    @themeName.setter
    def themeName(self, value: str) -> None:
        value = (value or "dark").lower()
        if value not in ("dark", "light"):
            value = "dark"
        if self._theme_name != value:
            self._theme_name = value
            self.themeChanged.emit()
            self._persist_fields()

    @Slot()
    def toggleTheme(self) -> None:
        self.themeName = "light" if self._theme_name == "dark" else "dark"

    @Property(bool, notify=themeChanged)
    def comfortable(self) -> bool:
        return self._comfortable

    @comfortable.setter
    def comfortable(self, value: bool) -> None:
        if self._comfortable != bool(value):
            self._comfortable = bool(value)
            self.themeChanged.emit()
            self._persist_fields()

    @Slot(bool)
    def setComfortable(self, value: bool) -> None:
        self.comfortable = value

    @Property(bool, notify=themeChanged)
    def reducedMotion(self) -> bool:
        return self._reduced_motion

    @reducedMotion.setter
    def reducedMotion(self, value: bool) -> None:
        if self._reduced_motion != bool(value):
            self._reduced_motion = bool(value)
            self.themeChanged.emit()
            self._persist_fields()

    @Slot(bool)
    def setReducedMotion(self, value: bool) -> None:
        self.reducedMotion = value

    # --- Structured failure surface (UX review S-02) -----------------------
    @Property(str, notify=failureChanged)
    def failureCode(self) -> str:
        return self._failure_code

    @Property(str, notify=failureChanged)
    def failureTitle(self) -> str:
        return self._failure_title

    @Property(str, notify=failureChanged)
    def failureDetail(self) -> str:
        return self._failure_detail

    @Property(str, notify=failureChanged)
    def failureRemediation(self) -> str:
        return self._failure_remediation

    @Property(bool, notify=failureChanged)
    def failureActive(self) -> bool:
        return self._failure_active

    def _set_failure(self, code: str, title: str, detail: str, remedy: str) -> None:
        self._failure_code = code or "UNKNOWN"
        self._failure_title = title or "The run failed."
        self._failure_detail = detail or ""
        self._failure_remediation = remedy or REMEDY_LOG
        self._failure_active = True
        self.failureChanged.emit()
        self.failureOccurred.emit(
            self._failure_code, self._failure_title,
            self._failure_detail, self._failure_remediation,
        )

    def _clear_failure(self) -> None:
        if not self._failure_active:
            return
        self._failure_code = ""
        self._failure_title = ""
        self._failure_detail = ""
        self._failure_remediation = ""
        self._failure_active = False
        self.failureChanged.emit()

    @Slot()
    def dismissFailure(self) -> None:
        self._clear_failure()

    @Slot()
    def openAdvancedSettings(self) -> None:
        """Ask the UI to reveal the Advanced drawer (used by the error card)."""
        self.requestAdvanced.emit()

    @Slot()
    def openDocumentation(self) -> None:
        """Open the bundled README so a missing-dependency error has a next step."""
        readme = os.path.join(_base_dir(), "README.md")
        if os.path.isfile(readme):
            QDesktopServices.openUrl(QUrl.fromLocalFile(readme))
        else:
            self._set_status("README.md not found next to the application.")

    @Slot(result=int)
    def logFirstErrorPosition(self) -> int:
        """Character offset of the first error line, or -1.

        Lets the log drawer jump straight to the cause instead of making the
        user scroll through a long run.
        """
        offset = 0
        for line in (self._log_text or "").splitlines(keepends=True):
            stripped = line.strip()
            if stripped.lower().startswith("[error]") or "traceback (most recent call last)" in stripped.lower():
                return offset
            offset += len(line)
        return -1

    # --- Pre-run readiness checklist (UX review S-03) ----------------------
    def _effective_out_path(self) -> str:
        """The path a run will actually write to ("" when not yet knowable).

        Mirrors the derivation in :func:`translate.default_output_path`, so the
        readiness checklist and the Output field agree with what the run does.
        """
        path = (self._out_path or "").strip()
        if path:
            return path
        source = (self._file_path or "").strip()
        if source:
            try:
                return translate.default_output_path(
                    source, "", self._output_format or "srt"
                )
            except Exception:  # noqa: BLE001 - a hint is never worth a crash
                return ""
        return ""

    def _output_readiness_row(self) -> dict:
        """Real check instead of the old hardcoded `return true`.

        With no input and no path there is genuinely nothing to check yet, so
        the row reports `unchecked` — *not* `na`. The two used to share one
        grey dash, which made the readiness score's denominator disagree with
        the rows on screen (UI review 2.1, 6.4). `na` means "this mode never
        uses it"; `unchecked` means "not evaluated yet".
        """
        path = (self._out_path or "").strip()
        derived = self._out_path_auto
        if not path:
            path = self._effective_out_path()
        if not path:
            return {
                "id": "output",
                "label": "Output folder writable",
                "state": READINESS_UNCHECKED,
                "actionable": True,
                "hint": "Pick a video to see the output path",
            }
        directory = os.path.dirname(os.path.abspath(path)) or "."
        hint = "Next to the video" if derived else ""
        if os.path.isdir(directory) and os.access(directory, os.W_OK):
            return {
                "id": "output",
                "label": "Output folder writable",
                "state": READINESS_OK,
                "actionable": True,
                "hint": hint,
            }
        return {
            "id": "output",
            "label": "Output folder writable",
            "state": READINESS_TODO,
            "actionable": True,
            "hint": "Cannot write to " + directory,
        }

    @Property(bool, notify=readinessChanged)
    def outputDirWritable(self) -> bool:
        return self._output_readiness_row()["state"] != "todo"

    @Property(list, notify=readinessChanged)
    def readinessRows(self) -> list:
        """Pre-run checklist rows as {id,label,state,actionable,hint}.

        ``state`` is one of ``ok`` / ``todo`` / ``na`` / ``unchecked`` (see the
        READINESS_* constants). ``na`` and ``unchecked`` are deliberately
        distinct facts with distinct glyphs — collapsing them into one grey
        dash is what made the score's denominator disagree with the visible
        rows. ``actionable`` is True for every row that is a real check, so the
        UI badge can read "2 of 3 actionable · 1 n/a".

        Computed in Python (not QML) so every row is testable and none can be
        silently hardcoded to green.
        """
        mode = self._pipeline_mode
        rows: list[dict] = []

        if mode == PIPELINE_MODE_YOUTUBE_CLOUD:
            source_ok = bool((self._url or "").strip())
            source_hint = "Enter a YouTube URL"
        else:
            source_ok = bool((self._file_path or "").strip())
            source_hint = "Choose a local media file"
        rows.append({
            "id": "source",
            "label": "Source selected",
            "state": READINESS_OK if source_ok else READINESS_TODO,
            "actionable": True,
            "hint": "" if source_ok else source_hint,
        })

        if mode == PIPELINE_MODE_YOUTUBE_CLOUD:
            # Not "not checked" — this mode genuinely never runs the ASR stage,
            # so the row is `na` and does not count toward the denominator.
            rows.append({
                "id": "asr",
                "label": "ASR model available",
                "state": READINESS_NA,
                "actionable": False,
                "hint": "Not used in YouTube mode",
            })
        else:
            asr_ok = bool(self.asrModelReady)
            rows.append({
                "id": "asr",
                "label": "ASR model available",
                "state": READINESS_OK if asr_ok else READINESS_TODO,
                "actionable": True,
                "hint": "" if asr_ok
                        else "Download the SenseVoice model for local transcription",
            })

        if mode == PIPELINE_MODE_OFFLINE:
            backend_ok = bool(self.localModelReady)
            rows.append({
                "id": "backend",
                "label": "Translation backend ready",
                "state": READINESS_OK if backend_ok else READINESS_TODO,
                "actionable": True,
                "hint": "" if backend_ok
                        else "Download or select a local translation model",
            })
        else:
            has_key = bool((self._api_key or "").strip()) or bool(
                os.environ.get("OPENAI_API_KEY")
            ) or _is_local_host(
                (self._base_url or "").strip() or os.environ.get("OPENAI_BASE_URL", "")
            )
            rows.append({
                "id": "backend",
                "label": "Translation backend ready",
                "state": READINESS_OK if has_key else READINESS_TODO,
                "actionable": True,
                "hint": "" if has_key
                        else "Set an API key in Settings, or define OPENAI_API_KEY",
            })

        rows.append(self._output_readiness_row())
        return rows

    @Property(int, notify=readinessChanged)
    def readinessActionableCount(self) -> int:
        """How many rows are real checks (the badge denominator)."""
        return sum(1 for r in self.readinessRows if r.get("actionable"))

    @Property(int, notify=readinessChanged)
    def readinessReadyCount(self) -> int:
        """How many actionable rows are satisfied (the badge numerator)."""
        return sum(
            1 for r in self.readinessRows
            if r.get("actionable") and r.get("state") == READINESS_OK
        )

    @Property(int, notify=readinessChanged)
    def readinessNotApplicableCount(self) -> int:
        return sum(1 for r in self.readinessRows if r.get("state") == READINESS_NA)

    @Property(str, notify=readinessChanged)
    def runBlockedReason(self) -> str:
        """Why Run is disabled, or "" when it is ready.

        The primary action must never redefine itself to work around a
        precondition (UI review 3.3). It stays `Run`, goes disabled, and shows
        this string — derived from the same readiness rows the checklist
        renders, so the two can never disagree.
        """
        if self._is_running:
            return ""
        for row in self.readinessRows:
            if row.get("actionable") and row.get("state") == READINESS_TODO:
                hint = (row.get("hint") or "").strip()
                return hint or row.get("label", "")
        return ""

    @Property(QObject, constant=True)
    def cueModel(self) -> CueResultModel:
        return self.cue_model

    # --- YouTube media (video download + codec inspection) --------------------

    def _youtube_out_dir(self) -> str:
        """Where downloaded video/subtitle files land.

        Preference order: the folder the user picked for downloads, the
        directory of the user's output path (if set), otherwise the app's
        base directory.
        """
        custom = (self._youtube_download_dir or "").strip()
        if custom:
            return custom
        out = (self._out_path or "").strip()
        if out:
            d = os.path.dirname(os.path.abspath(out))
            if d:
                return d
        return _base_dir()

    def _youtube_out_template(self) -> str:
        """yt-dlp ``-o`` template for this video (title + id)."""
        return os.path.join(self._youtube_out_dir(), "%(title)s [%(id)s]")

    @Property(list, notify=youtubeInfoChanged)
    def youtubeCodecs(self) -> list:
        """Codec choices: available families (AV1/VP9/H.264) plus "best"."""
        items = [{"id": c, "label": youtube_media._CODEC_LABEL.get(c, c.upper())}
                 for c in self._youtube_codec_ids]
        items.append({"id": "best", "label": "Best (any)"})
        return items

    @Property(list, notify=youtubeInfoChanged)
    def youtubeResolutions(self) -> list:
        """Resolution choices for the *currently selected codec*, plus "best".

        Heights are those the selected codec actually serves, so the
        (codec, resolution) pair can always be honoured exactly. With codec
        "best" every available height is offered (the download is then capped
        at that height, any codec).
        """
        sel = (self._youtube_selected_codec or "best").strip() or "best"
        fam = (self._youtube_matrix or {}).get(sel) if sel != "best" else None
        if fam:
            heights = sorted((int(h) for h in fam.keys()), reverse=True)
        else:
            heights = sorted((int(h) for h in self._youtube_resolutions), reverse=True)
        # ``value`` is a STRING on purpose. QML hands the picked value straight
        # back to ``youtubeSelectedResolution``, which stores a string; an int
        # here forced every comparison (and every write) through a coercion
        # that silently failed.
        items = [{"value": str(h), "label": f"{h}p"} for h in heights]
        items.append({"value": "best", "label": "Best"})
        return items

    @Property(bool, notify=youtubeInfoChanged)
    def youtubeHasInfo(self) -> bool:
        """True once an inspection succeeded for the current URL."""
        return bool(
            self._youtube_codec_ids or self._youtube_matrix or self._youtube_best
        )

    @Property(list, notify=youtubeInfoChanged)
    def youtubeFormatRows(self) -> list:
        """Flattened codec×resolution rows for the "available formats" table.

        One row per stream combination YouTube serves for this video (highest
        resolution first, codecs in preference order), preceded by the
        "best available (any codec)" row. Text fields are pre-formatted here so
        the QML table stays dumb.
        """
        if not self._youtube_matrix and not self._youtube_best:
            return []
        order = {c: i for i, c in enumerate(youtube_media._CODEC_ORDER)}
        # Which row matches the current selection? "best" resolution means the
        # highest available height of the selected codec (what resolve_video_option
        # actually returns), so highlight exactly that row.
        sel_codec = (self._youtube_selected_codec or "best").strip() or "best"
        sel_res = self._youtube_selected_resolution
        max_height = {
            cid: max(fam.keys())
            for cid, fam in (self._youtube_matrix or {}).items() if fam
        }
        rows: list[dict] = []
        for cid, family in (self._youtube_matrix or {}).items():
            for height, opt in family.items():
                filesize = int(opt.get("filesize") or 0)
                fps = int(opt.get("fps") or 0)
                merge = bool(opt.get("merge"))
                bits = [opt.get("ext") or ""]
                if fps:
                    bits.append(f"{fps}fps")
                fmt = " · ".join(b for b in bits if b)
                if merge:
                    fmt = (fmt + " · " if fmt else "") + "video+audio merge"
                elif not fmt:
                    fmt = "—"
                rows.append({
                    "isBest": False,
                    "selected": (sel_codec == cid
                                 and (height == max_height.get(cid)
                                      if sel_res == "best"
                                      else int(sel_res) == height)),
                    "codec": cid,
                    "codecLabel": youtube_media._CODEC_LABEL.get(cid, str(cid).upper()),
                    "resolution": int(height),
                    "resLabel": f"{int(height)}p" if height else "auto",
                    "formatText": fmt,
                    "sizeText": youtube_media._human_size(filesize) if filesize else "—",
                    "merge": merge,
                    "formatId": str(opt.get("format_selector") or ""),
                })
        if self._youtube_best:
            rows.append({
                "isBest": True,
                "selected": sel_codec == "best",
                "codec": "best",
                "codecLabel": "Best (any)",
                "resolution": "best",
                "resLabel": "Best",
                "formatText": "auto",
                "sizeText": "—",
                "merge": False,
                "formatId": str((self._youtube_best or {}).get("format_selector") or ""),
            })
        rows.sort(key=lambda r: (
            0 if r["isBest"] else 1,
            -int(r["resolution"]) if not r["isBest"] else 0,
            order.get(r["codec"], 99),
        ))
        return rows

    @Property(bool, notify=youtubeInfoChanged)
    def youtubeInfoLoading(self) -> bool:
        return self._youtube_info_loading

    @Property(str, notify=youtubeInfoChanged)
    def youtubeInfoError(self) -> str:
        return self._youtube_info_error

    @Property(str, notify=youtubeInfoChanged)
    def youtubeTitle(self) -> str:
        return self._youtube_title

    @Property(bool, notify=youtubeInfoChanged)
    def youtubeHasAv1(self) -> bool:
        return self._youtube_has_av1

    @Property(bool, notify=youtubeInfoChanged)
    def youtubeHasVp9(self) -> bool:
        return self._youtube_has_vp9

    @Property(bool, notify=youtubeInfoChanged)
    def youtubeHasH264(self) -> bool:
        return self._youtube_has_h264

    @Property(bool, notify=youtubeInfoChanged)
    def youtubeHasEnglishSubtitle(self) -> bool:
        return self._youtube_has_en_subtitle

    @Property(str, notify=youtubeInfoChanged)
    def youtubeSelectedCodec(self) -> str:
        return self._youtube_selected_codec

    @youtubeSelectedCodec.setter
    def youtubeSelectedCodec(self, value: str) -> None:
        value = (value or "best").strip()
        if self._youtube_selected_codec == value:
            return
        self._youtube_selected_codec = value
        # Keep the pair honourable: if the newly selected codec does not serve
        # the currently selected height, reset the resolution to "best" (the
        # resolution choices themselves are codec-aware).
        fam = (self._youtube_matrix or {}).get(value) if value != "best" else None
        if fam and self._youtube_selected_resolution != "best":
            try:
                if int(self._youtube_selected_resolution) not in fam:
                    self._youtube_selected_resolution = "best"
            except (TypeError, ValueError):
                self._youtube_selected_resolution = "best"
        self.youtubeInfoChanged.emit()

    # NOTE: this must stay typed ``str``. Declaring it ``object`` makes PySide6
    # register the property as ``PySide::PyObjectWrapper``, which the QML engine
    # *refuses to write* ("Cannot assign int to PySide::PyObjectWrapper"). Every
    # pick in the resolution dropdown was silently dropped, leaving the stored
    # selection at "best" — which downloads the highest-quality stream while
    # the UI happily shows the resolution the user chose.
    @Property(str, notify=youtubeInfoChanged)
    def youtubeSelectedResolution(self) -> str:
        return self._youtube_selected_resolution

    @youtubeSelectedResolution.setter
    def youtubeSelectedResolution(self, value) -> None:
        # Always store a string ("720" or "best"). The QML picker may hand us a
        # bare int (720), a double (720.0 — JavaScript numbers) or a string;
        # normalize_resolution collapses all of them.
        value = youtube_media.normalize_resolution(value)
        if self._youtube_selected_resolution != value:
            self._youtube_selected_resolution = value
            self.youtubeInfoChanged.emit()

    @Property(str, notify=youtubeInfoChanged)
    def youtubeSelectionError(self) -> str:
        """Why the current (codec, resolution) pair cannot be downloaded.

        Empty when the pair is available. Lets the UI say *what* is missing
        ("no H.264 stream at 480p; available: 1080p, 720p, 360p") instead of a
        generic "no matching stream".
        """
        if not self._youtube_matrix and not self._youtube_best:
            return ""
        return youtube_media.describe_unavailable(
            {"matrix": self._youtube_matrix, "best": self._youtube_best},
            self._youtube_selected_codec,
            self._youtube_selected_resolution,
        )

    @Property(dict, notify=youtubeInfoChanged)
    def youtubeSelectedOption(self) -> dict:
        if not self._youtube_matrix and not self._youtube_best:
            return {}
        # Strict: only an option that *exactly* matches the pair is returned.
        # An unavailable pair yields {} so the UI/download can refuse instead
        # of quietly substituting something else.
        return youtube_media.resolve_video_option(
            {"matrix": self._youtube_matrix, "best": self._youtube_best},
            self._youtube_selected_codec,
            self._youtube_selected_resolution,
        ) or {}

    @Property(int, notify=youtubeInfoChanged)
    def youtubeSelectedFileSize(self) -> int:
        return int((self.youtubeSelectedOption or {}).get("filesize") or 0)

    @Property(str, notify=youtubeInfoChanged)
    def youtubeSelectedFormatLabel(self) -> str:
        return (self.youtubeSelectedOption or {}).get("label") or ""

    @Property(str, notify=youtubeInfoChanged)
    def youtubeDownloadDir(self) -> str:
        return self._youtube_out_dir()

    @Property(bool, notify=youtubeDownloadChanged)
    def youtubeVideoDownloading(self) -> bool:
        return self._youtube_video_downloading

    @Property(int, notify=youtubeDownloadChanged)
    def youtubeVideoProgress(self) -> int:
        return self._youtube_video_progress

    @Property(str, notify=youtubeDownloadChanged)
    def youtubeVideoStatus(self) -> str:
        return self._youtube_video_status

    @Property(str, notify=youtubeDownloadChanged)
    def youtubeVideoNotice(self) -> str:
        """Headline for a recoverable hiccup; empty when nothing went wrong.

        Lets the UI banner a restart (e.g. "stale partial removed, restarting")
        instead of hiding it among the raw yt-dlp log lines.
        """
        return self._youtube_video_notice

    @Property(bool, notify=youtubeDownloadChanged)
    def youtubeSubDownloading(self) -> bool:
        return self._youtube_sub_downloading

    @Property(str, notify=youtubeDownloadChanged)
    def youtubeSubStatus(self) -> str:
        return self._youtube_sub_status

    @Property(bool, notify=youtubeDownloadChanged)
    def youtubeDownloading(self) -> bool:
        """Combined busy flag (video *or* subtitle download in flight)."""
        return self._youtube_video_downloading or self._youtube_sub_downloading

    @Property(str, notify=youtubeDownloadChanged)
    def youtubeDownloadStatus(self) -> str:
        """Combined status text (kept for compatibility)."""
        return self._youtube_video_status + self._youtube_sub_status

    @Property(str, notify=youtubeDownloadChanged)
    def youtubeDownloadedVideo(self) -> str:
        return self._youtube_downloaded_video

    @Property(str, notify=youtubeDownloadChanged)
    def youtubeDownloadedSubtitle(self) -> str:
        return self._youtube_downloaded_subtitle

    @Slot(QUrl)
    def setYouTubeDownloadDir(self, url: QUrl) -> None:
        """Pick the folder video/subtitle downloads are saved to (persisted)."""
        path = url.toLocalFile() if url.isValid() else ""
        if not path:
            return
        if self._youtube_download_dir == path:
            return
        self._youtube_download_dir = path
        self.youtubeDownloadChanged.emit()
        self.youtubeInfoChanged.emit()
        self._set_status(f"YouTube downloads will be saved to: {path}")

    @Slot()
    def fetchYouTubeInfo(self) -> None:
        url = (self._url or "").strip()
        if not url:
            self._youtube_info_error = "Enter a YouTube URL first."
            self.youtubeInfoChanged.emit()
            return
        if self._youtube_info_loading:
            return
        self._youtube_info_loading = True
        self._youtube_info_error = ""
        self._youtube_matrix = {}
        self._youtube_best = {}
        self._youtube_codec_ids = []
        self._youtube_resolutions = []
        self._youtube_selected_codec = "best"
        self._youtube_selected_resolution = "best"
        self.youtubeInfoChanged.emit()
        self._set_status("Inspecting video formats… (large videos can take a minute)")

        self._youtube_info_gen += 1
        worker = _YouTubeInfoWorker(url, self._youtube_info_gen)
        worker.signals.done.connect(self._on_youtube_info)
        self._youtube_info_worker = worker
        self.threadpool.start(worker)

    def _on_youtube_info(self, payload: str) -> None:
        # Stale-guard via generation tags (see the state init): a superseded
        # inspection — URL change, or a retry after the old worker already
        # finished/failed — carries an outdated tag and is dropped. The tag
        # travels in the payload because sender() is the signals object, never
        # the QRunnable; the previous identity check could never match, which
        # made every result look stale and left the UI stuck on "Inspecting…".
        token = -1
        for prefix in ("INFO:", "INFOERROR:"):
            if payload.startswith(prefix):
                head, _, rest = payload[len(prefix):].partition("|")
                try:
                    token = int(head)
                except ValueError:
                    token = -1
                payload = prefix + rest
                break
        if token != self._youtube_info_gen:
            return
        self._youtube_info_worker = None
        self._youtube_info_loading = False
        if payload.startswith("INFOERROR:"):
            self._youtube_info_error = payload[len("INFOERROR:"):].strip()
            self.youtubeInfoChanged.emit()
            self._set_status(self._youtube_info_error)
            return
        if not payload.startswith("INFO:"):
            self._youtube_info_error = "Unexpected inspection result."
            self.youtubeInfoChanged.emit()
            return
        try:
            info = json.loads(payload[len("INFO:"):])
        except (ValueError, TypeError):
            self._youtube_info_error = "Could not parse video information."
            self.youtubeInfoChanged.emit()
            return

        self._youtube_title = info.get("title") or ""
        # The title names the subtitle file, so the auto output path can only be
        # resolved once the video has been inspected.
        self._sync_auto_out_path()
        # JSON object keys are always strings, so the heights arrived as "1080"
        # etc. Restore int keys so resolve_video_option() can still match the
        # combined (single-file) formats shown to the user in the UI.
        self._youtube_matrix = {
            cid: {int(h): opt for h, opt in (family or {}).items()}
            for cid, family in (info.get("matrix") or {}).items()
        }
        self._youtube_best = info.get("best") or {}
        self._youtube_codec_ids = info.get("codecs") or []
        self._youtube_resolutions = info.get("resolutions") or []
        codecs = info.get("codecs_available") or {}
        self._youtube_has_av1 = bool(codecs.get("av1"))
        self._youtube_has_vp9 = bool(codecs.get("vp9"))
        self._youtube_has_h264 = bool(codecs.get("h264"))
        self._youtube_has_en_subtitle = bool(info.get("has_english_subtitle"))
        # Default the codec to the newest available, resolution to best.
        self._youtube_selected_codec = self._youtube_codec_ids[0] if self._youtube_codec_ids else "best"
        self._youtube_selected_resolution = "best"
        self.youtubeInfoChanged.emit()
        self._set_status(
            f"Inspected \u201c{self._youtube_title}\u201d — "
            f"{len(self._youtube_codec_ids)} codec(s), "
            f"{len(self._youtube_resolutions)} resolution(s) available."
        )

    def _selected_format_selector(self) -> str:
        """Exact yt-dlp selector for the current pick; "" when unavailable.

        There is deliberately **no** ``bv*+ba/b`` fallback. Falling back to
        "best" is exactly what made the download ignore the dropdowns: the UI
        showed the chosen codec/resolution while yt-dlp fetched whatever the
        globally best stream was.
        """
        opt = self.youtubeSelectedOption
        if opt and opt.get("format_selector"):
            return str(opt["format_selector"])
        return ""

    def _selected_expectation(self) -> dict:
        """What the finished file must look like, for the post-download check."""
        opt = self.youtubeSelectedOption or {}
        height = opt.get("resolution")
        try:
            height = int(height)
        except (TypeError, ValueError):
            height = 0
        codec = str(opt.get("codec") or "").strip().lower()
        return {
            "codec": codec,
            "height": height,
            # "Best (any)" + a height is a cap (≤ Np), not an exact match.
            "cap": codec == "best",
        }

    # --- Video download (independent of the subtitle download) ---------------

    @Slot()
    def downloadYouTubeVideo(self) -> None:
        url = (self._url or "").strip()
        if not url:
            self._set_status("Enter a YouTube URL first.")
            return
        if self._youtube_video_downloading:
            return
        selector = self._selected_format_selector()
        if not selector:
            # Never silently download "whatever is best" — say what is missing.
            reason = self.youtubeSelectionError or (
                "This video is not available in the selected format "
                f"({self.youtubeSelectedFormatLabel or 'current selection'}).")
            self._youtube_video_progress = 0
            self._youtube_video_status = (
                f"[error] {reason}\n"
                "Choose one of the combinations listed above, then try again.\n")
            self._youtube_video_notice = reason
            self._youtube_downloaded_video = ""
            self.youtubeDownloadChanged.emit()
            self._set_status("Video not available in that format/resolution.")
            return
        template = self._youtube_out_template() + ".%(ext)s"
        self._youtube_video_downloading = True
        self._youtube_video_progress = 0
        self._youtube_video_status = "Starting video download…\n"
        self._youtube_video_notice = ""
        self._youtube_downloaded_video = ""
        self._youtube_downloading = True
        self.youtubeDownloadChanged.emit()
        self._set_status("Downloading YouTube video…")

        self._youtube_video_gen += 1
        worker = _YouTubeDownloadWorker(
            "video", url, selector, template, self._youtube_video_gen,
            expect=self._selected_expectation(),
        )
        worker.signals.progress.connect(self._append_log)
        worker.signals.progress.connect(self._on_youtube_video_progress_line)
        worker.signals.percent.connect(self._on_youtube_video_percent)
        worker.signals.done.connect(self._on_youtube_video_done)
        self._youtube_video_worker = worker
        self.threadpool.start(worker)
        self._append_log(
            f"[youtube] downloading video with selector: {selector}\n"
        )

    @Slot()
    def cancelYouTubeVideoDownload(self) -> None:
        worker = self._youtube_video_worker
        if worker is None:
            return
        self._youtube_video_status += "[info] canceling video download…\n"
        self.youtubeDownloadChanged.emit()
        # Keep the reference until the worker reports done: its completion is
        # tagged with the current generation, so dropping the ref here would
        # make that completion look stale and leave the spinner stuck.
        worker.cancel()

    def _on_youtube_video_progress_line(self, text: str) -> None:
        self._youtube_video_status += text
        # yt-dlp recovery steps are reported as "[warn] …"; promote them to the
        # banner so a restart is visible instead of scrolling past in the log.
        if text.lstrip().startswith("[warn]"):
            notice = text.strip()[len("[warn]"):].strip()
            if notice:
                self._youtube_video_notice = notice
        self.youtubeDownloadChanged.emit()

    def _on_youtube_video_percent(self, pct: int) -> None:
        self._youtube_video_progress = max(0, min(100, int(pct)))
        self.youtubeDownloadChanged.emit()

    @staticmethod
    def _payload_token(payload: str) -> int:
        """Extract the generation tag from a ``KIND:<n>|...`` worker payload."""
        try:
            return int(payload.split("|", 1)[0].rsplit(":", 1)[1])
        except (IndexError, ValueError):
            return -1

    def _on_youtube_video_done(self, payload: str) -> None:
        # Ignore stale completions from a superseded worker (e.g. after the
        # user changed the URL or restarted the download): they must never
        # clobber the status, progress or saved-path of the current run.
        # Generation-tag comparison — sender() cannot identify the worker.
        if self._payload_token(payload) != self._youtube_video_gen:
            return
        self._youtube_video_worker = None
        self._youtube_video_downloading = False
        self._youtube_downloading = self._youtube_sub_downloading
        if payload.startswith("YTCANCEL:"):
            self._youtube_video_progress = 0
            self._youtube_video_status += "[canceled] video download stopped.\n"
            self._set_status("YouTube video download canceled.")
        elif payload.startswith("YTERROR:"):
            # payload: YTERROR:video:<message>
            _, _, msg = payload.split(":", 2)
            self._youtube_video_progress = 0
            self._youtube_video_status += f"[error] {msg}\n"
            self._set_status("YouTube video download failed. See the log.")
        elif payload.startswith("YTDONE:"):
            _, _, path = payload.split(":", 2)
            self._youtube_video_progress = 100
            self._youtube_downloaded_video = path
            # A recovery banner ("restarting…") is stale once the file landed.
            self._youtube_video_notice = ""
            self._youtube_video_status += f"[ok] saved: {path}\n"
            self._set_status(f"YouTube video saved: {os.path.basename(path)}")
        else:
            self._youtube_video_status += "[error] Unexpected download result.\n"
        # Keep the QML Label bounded: status accumulates across stages (two
        # downloads per video) and used to grow without limit.
        self._youtube_video_status = self._youtube_video_status[-8000:]
        self.youtubeDownloadChanged.emit()

    # --- Subtitle download (independent of the video download) ---------------

    @Slot()
    def downloadYouTubeSubtitle(self) -> None:
        url = (self._url or "").strip()
        if not url:
            self._set_status("Enter a YouTube URL first.")
            return
        if self._youtube_sub_downloading:
            return
        template = self._youtube_out_template()
        self._youtube_sub_downloading = True
        self._youtube_sub_status = "Starting subtitle download…\n"
        self._youtube_downloaded_subtitle = ""
        self._youtube_downloading = True
        self.youtubeDownloadChanged.emit()
        self._set_status("Downloading YouTube subtitle…")

        # Tag the completion payload with a fresh generation so a superseded
        # or repeated run can never be mistaken for this one (and a previous
        # run's already-consumed tag can't make this completion look stale).
        self._youtube_sub_gen += 1
        worker = _YouTubeDownloadWorker("subtitle", url, "", template, self._youtube_sub_gen)
        worker.signals.progress.connect(self._append_log)
        worker.signals.progress.connect(self._on_youtube_sub_progress_line)
        worker.signals.done.connect(self._on_youtube_sub_done)
        self._youtube_sub_worker = worker
        self.threadpool.start(worker)

    @Slot()
    def cancelYouTubeSubtitleDownload(self) -> None:
        worker = self._youtube_sub_worker
        if worker is None:
            return
        self._youtube_sub_status += "[info] canceling subtitle download…\n"
        self.youtubeDownloadChanged.emit()
        worker.cancel()

    def _on_youtube_sub_progress_line(self, text: str) -> None:
        self._youtube_sub_status += text
        self.youtubeDownloadChanged.emit()

    def _on_youtube_sub_done(self, payload: str) -> None:
        # Stale-worker guard via generation tag (see _on_youtube_video_done).
        # sender() is the signals object, never the QRunnable, so an identity
        # check against _youtube_sub_worker could never match and silently
        # dropped every completion — leaving the panel stuck on "Downloading…".
        if self._payload_token(payload) != self._youtube_sub_gen:
            return
        self._youtube_sub_worker = None
        self._youtube_sub_downloading = False
        self._youtube_downloading = self._youtube_video_downloading
        if payload.startswith("YTCANCEL:"):
            self._youtube_sub_status += "[canceled] subtitle download stopped.\n"
            self._set_status("YouTube subtitle download canceled.")
        elif payload.startswith("YTERROR:"):
            _, _, msg = payload.split(":", 2)
            self._youtube_sub_status += f"[error] {msg}\n"
            self._set_status("YouTube subtitle download failed. See the log.")
        elif payload.startswith("YTDONE:"):
            _, _, path = payload.split(":", 2)
            self._youtube_downloaded_subtitle = path
            self._youtube_sub_status += f"[ok] saved: {path}\n"
            self._set_status(f"YouTube subtitle saved: {os.path.basename(path)}")
        else:
            self._youtube_sub_status += "[error] Unexpected download result.\n"
        self._youtube_sub_status = self._youtube_sub_status[-8000:]
        self.youtubeDownloadChanged.emit()

    @Slot(str, result=str)
    def folderUrl(self, path: str) -> str:
        """``file://`` URL of the folder holding `path`, for a QML file dialog.

        A picker that always opens at the app folder makes a client re-navigate
        to their videos every single time; this lets the dialogs start where
        the user already is.
        """
        target = (path or "").strip()
        if not target:
            return ""
        folder = target if os.path.isdir(target) else os.path.dirname(os.path.abspath(target))
        if not os.path.isdir(folder):
            return ""
        return QUrl.fromLocalFile(folder).toString()

    @Slot(str, result=str)
    def fileUrl(self, path: str) -> str:
        """``file://`` URL for `path` itself ("" when the path is empty)."""
        target = (path or "").strip()
        if not target:
            return ""
        return QUrl.fromLocalFile(os.path.abspath(target)).toString()

    @Property(str, notify=formChanged)
    def lastInputDir(self) -> str:
        """Folder the file pickers should open in ("" = let the OS choose)."""
        for candidate in (self._file_path, self._out_path, self._youtube_download_dir):
            path = (candidate or "").strip()
            if not path:
                continue
            folder = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
            if os.path.isdir(folder):
                return folder
        return ""

    @Slot(str)
    def openFolderForPath(self, path: str) -> None:
        target = (path or "").strip()
        if not target:
            return
        folder = os.path.dirname(os.path.abspath(target))
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            self._set_status("Could not open the folder.")

    @Property(QObject, constant=True)
    def cueProxy(self) -> CueFilterProxyModel:
        return self.cue_proxy

    @Property(QObject, constant=True)
    def qualityIssuesModel(self) -> QualityIssuesModel:
        return self.quality_issues_model

    @Slot()
    def downloadAsrModels(self) -> None:
        if self._model_downloading:
            return
        self._model_download_status = ""
        self._model_downloading = True
        self.modelDownloadChanged.emit()

        worker = _ModelDownloadWorker()
        worker.signals.progress.connect(self._append_log)
        worker.signals.progress.connect(lambda s: self._set_model_download_status_text(s))
        worker.signals.done.connect(self._on_models_downloaded)
        self.threadpool.start(worker)

    def _set_model_download_status_text(self, text: str) -> None:
        self._model_download_status += text
        self.modelDownloadChanged.emit()

    def _on_models_downloaded(self, _msg: str) -> None:
        self._model_downloading = False
        worker = self.sender()
        downloaded = getattr(worker, "downloaded", []) if worker else []
        gguf = _gguf_dir()
        # Only latch a path that actually validates. Latching on bare existence
        # is what let an interrupted download become the permanently "ready"
        # ASR model, with no way for the user to notice or fix it.
        if not self._asr_model.strip() or _model_status(self._asr_model)[0] == MODEL_STATE_CORRUPT:
            candidate = os.path.join(gguf, "sensevoice-small-q8.gguf")
            if candidate in downloaded and gguf_check.is_usable_gguf(candidate):
                self._set_field("_asr_model", candidate)
        if not self._asr_vad_model.strip() or _model_status(self._asr_vad_model)[0] == MODEL_STATE_CORRUPT:
            candidate = os.path.join(gguf, "fsmn-vad.gguf")
            if candidate in downloaded and gguf_check.is_usable_gguf(candidate):
                self._set_field("_asr_vad_model", candidate)
        self._persist_fields()
        self.modelDownloadChanged.emit()
        if self.asrModelReady:
            self._set_status("ASR model ready.")
        else:
            self._set_status(
                "ASR models are still unavailable. See the log for the download "
                "error (a full disk is the usual cause)."
            )

    @Slot()
    def downloadLocalModel(self) -> None:
        if self._local_model_downloading:
            return
        self._local_model_download_status = ""
        self._local_model_downloading = True
        self.modelDownloadChanged.emit()

        worker = _ModelDownloadWorker(_LOCAL_MODEL_URLS)
        worker.signals.progress.connect(self._append_log)
        worker.signals.progress.connect(self._set_local_model_download_status_text)
        worker.signals.done.connect(self._on_local_model_downloaded)
        self.threadpool.start(worker)

    def _set_local_model_download_status_text(self, text: str) -> None:
        self._local_model_download_status += text
        self.modelDownloadChanged.emit()

    def _on_local_model_downloaded(self, _msg: str) -> None:
        was_pending = self._local_model_download_pending
        self._local_model_downloading = False
        self._local_model_download_pending = False
        worker = self.sender()
        downloaded = getattr(worker, "downloaded", []) if worker else []
        selected_state, _ = _model_status(self._local_model)
        if not self._local_model.strip() or selected_state == MODEL_STATE_CORRUPT:
            # Nothing selected, or the selection points at a file that cannot be
            # loaded (an interrupted download). Either way the freshly verified
            # download is what the user wants to use.
            candidate = _find_local_model()
            if candidate and candidate in downloaded:
                self._set_field("_local_model", candidate)
                print(
                    f"[local] Using Hy-MT2 model: {os.path.relpath(candidate)}",
                    flush=True,
                )
        self._persist_fields()
        self.modelDownloadChanged.emit()
        if self.localModelReady:
            self._set_status("Local translation model ready.")
        else:
            self._set_status(
                "The local translation model is still unavailable. See the log "
                "for the download error (a full disk is the usual cause)."
            )
        self.localModelDownloadPendingChanged.emit()

        # If a run was waiting on this download, kick it off now — but only when
        # the model really is usable, otherwise the run would fail immediately
        # with the same error the user is already looking at.
        if was_pending and self.localModelReady:
            self.runTranslation()

    @Slot()
    def clearLog(self) -> None:
        self._log_text = ""
        self._log_lines = 0
        if self._log_error_count or self._log_warn_count:
            self._log_error_count = 0
            self._log_warn_count = 0
            self.logCountsChanged.emit()
        self.logTextChanged.emit()
        self._set_status("Ready.")

    @Slot()
    def copyLog(self) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(self._log_text)
        self._set_status("Log copied to clipboard.")

    @Slot(result=str)
    def copySummaryText(self) -> str:
        """Human-readable diagnostics for bug reports.

        This is the single home for raw internals: absolute paths, the registry
        store, Python/Qt versions and the frozen flag. They used to be splashed
        across the About/Environment card inline, which is developer telemetry,
        not configuration (UI review 5.6). The card now shows one-line
        summaries and this button carries the full strings.
        """
        q = self._quality_summary
        lines = [
            f"Output: {self._resolved_out_path or '-'}",
            f"Cues: {q.get('cue_count', 0)}",
            f"Untranslated: {self.qualityUntranslated}",
            f"Errors: {self.qualityErrors}  Warnings: {self.qualityWarnings}",
            f"Avg CPS: {self.qualityAverageCps}  Max line chars: {self.qualityMaxLineChars}",
            f"Strict quality: {self._result_strict_state}",
            "",
            "Environment:",
        ]
        lines.extend(f"  {row['k']}: {row['v']}" for row in self.environmentRows)
        text = "\n".join(lines)
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(text)
        return text

    @Slot(result=str)
    def copyToDiagnostics(self) -> str:
        """`Copy diagnostics` — the single home for raw internals (UI review 5.6).

        The About card shows a one-line summary; everything a bug report needs
        (install path, models path, result JSON path, settings store, versions)
        comes out of here, and nowhere else.
        """
        text = self.copySummaryText()
        self._set_status("Diagnostics copied to the clipboard.")
        return text

    @Slot(str)
    def setStatusMessage(self, text: str) -> None:
        """Let QML surface a refusal (e.g. a shortcut conflict) in the status bar."""
        self._set_status(text)

    @Slot(str, result=str)
    def localPath(self, url_or_path: str) -> str:
        if not url_or_path:
            return ""
        qurl = QUrl(url_or_path)
        if qurl.isValid() and qurl.scheme():
            local_file = qurl.toLocalFile()
            if local_file:
                return local_file
        return url_or_path

    @Slot()
    def runTranslation(self) -> None:
        if self._is_running:
            return

        self._set_status_state(STATUS_VALIDATING)
        try:
            config = self._build_run_config()
        except ValueError as exc:
            msg = str(exc)
            # Auto-trigger model download when the only blocker is a missing (or
            # unusable) local translation GGUF, so the user does not have to
            # configure anything manually.
            if (
                self._backend == "local"
                and "No usable local translation model found" in msg
                and not self._local_model_downloading
                and not self._local_model_download_pending
            ):
                self._local_model_download_pending = True
                self.localModelDownloadPendingChanged.emit()
                self._set_status(
                    "Downloading local translation model…"
                    if not self.localModelCorrupt
                    else "The local translation model file is incomplete — "
                         "downloading it again…"
                )
                self._set_status_state(STATUS_RUNNING)
                worker = _ModelDownloadWorker(_LOCAL_MODEL_URLS)
                worker.signals.progress.connect(self._append_log)
                worker.signals.progress.connect(self._set_local_model_download_status_text)
                worker.signals.done.connect(self._on_local_model_downloaded)
                self.threadpool.start(worker)
                return
            self._set_status(msg)
            self._set_status_state(STATUS_FAILED)
            self._set_failure("VALIDATION", msg, msg, REMEDY_FORM)
            return

        self._persist_fields()
        # Snapshot the settings this run is about to use, so the Log screen's
        # "re-run with the same settings" really restores them.
        self._last_run_snapshot = {
            attr: getattr(self, attr, default)
            for attr, _key, default in self._PERSISTED
        }
        self._last_run_snapshot["_url"] = self._url
        self._last_run_snapshot["_file_path"] = self._file_path
        self._run_started_clock = time.strftime("%H:%M:%S")
        self._run_metrics = {}
        self._resolved_out_path = ""
        self.canOpenOutputFolderChanged.emit()
        self._reset_result_state()
        self._clear_failure()
        self._progress_stage = ""
        self._progress_done = 0
        self._progress_total = 0
        # Fresh per-stage timing for the legible progress panel (S-07).
        self._run_started_at = time.time()
        self._stage_sequence = []
        self._stage_started_at = self._run_started_at
        self._stage_elapsed_sec = 0
        self._estimated_remaining_sec = 0
        self.stageChanged.emit()
        self.progressChanged.emit()
        self._set_running(True)
        self._set_status("Running…")
        self._set_status_state(STATUS_RUNNING)

        command_preview = f"$ python translate.py {' '.join(config.argv)}\n"
        self._append_log(command_preview)
        self.logger.info("run argv: %s", " ".join(config.argv))

        worker = TranslationWorker(config)
        worker.signals.logLine.connect(self._handle_log_line)
        worker.signals.finished.connect(self._on_finished)
        self._current_worker = worker
        self.threadpool.start(worker)

    @Slot()
    def cancelRun(self) -> None:
        """Ask the in-process pipeline to stop at the next batch boundary.

        Cancellation is cooperative: the current LLM batch finishes (its
        translation is discarded), then translate_cues raises
        TranslationCancelled and the worker exits with code 2.
        """
        if not self._is_running:
            return
        translate.request_cancel()
        self._set_status("Cancelling\u2026 stops after the current batch.")
        self.logger.info("cancel requested by user")

    @Slot()
    def openOutputFolder(self) -> None:
        if not self._resolved_out_path:
            return
        folder = os.path.dirname(os.path.abspath(self._resolved_out_path))
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        if not ok:
            self._set_status("Could not open the output folder.")

    @Slot(int)
    def _on_finished(self, rc: int) -> None:
        self._current_worker = None
        # Finalize the elapsed time of the last visited stage and the run total.
        now = time.time()
        if (self._progress_stage and self._stage_sequence
                and self._stage_sequence[-1]["name"] == self._progress_stage):
            self._stage_sequence[-1]["elapsed"] = now - self._stage_started_at
        self._stage_elapsed_sec = now - self._run_started_at if self._run_started_at else 0
        self._estimated_remaining_sec = 0
        self._set_running(False)
        self.stageChanged.emit()
        self.logger.info("run finished, rc=%s", rc)

        if rc == 0:
            self._set_status_state(STATUS_DONE)
            loaded = self._load_result_json()
            if self._resolved_out_path:
                self._set_status(
                    f"Done. Saved to {self._resolved_out_path}"
                )
            elif loaded:
                self._set_status("Done.")
            else:
                self._set_status("Done.")
            if not loaded:
                # Result JSON missing: final-line parsing already recovered the
                # output path for Open Output Folder; review stays unavailable.
                self.logger.warning("result JSON missing after successful run")
        elif rc == 2 and getattr(translate, "_cancel_requested", False):
            # Exit code 2 doubles as argparse/validation failure in the CLI,
            # so only treat it as a cancel when the flag is actually set.
            self._set_status_state(STATUS_CANCELLED)
            self._set_status("Cancelled. No output file was written.")
        else:
            self._set_status_state(STATUS_FAILED)
            code, title, detail, remedy = _classify_failure(self._log_text)
            self._set_failure(code, title, detail, remedy)
            # Lead with the cause. The old message pointed at a log drawer
            # that is collapsed by default, so the user had to go hunting.
            self._set_status(title)
            if not self._log_visible:
                self.logVisible = True

        self._record_run(rc)

    # --- Run history ------------------------------------------------------
    _WINDOWS_RE = re.compile(r"\[windows\]\s+(\d+)\s+window", re.IGNORECASE)
    _TM_HITS_RE = re.compile(r"\[tm\]\s+(\d+)\s+exact hit", re.IGNORECASE)
    _RETRY_RE = re.compile(r"\[retry\]", re.IGNORECASE)

    def _scan_run_metrics(self) -> dict:
        """Best-effort counters recovered from the captured log."""
        text = self._log_text or ""
        windows = 0
        tm_hits = 0
        retries = 0
        match = self._WINDOWS_RE.search(text)
        if match:
            windows = int(match.group(1))
        match = self._TM_HITS_RE.search(text)
        if match:
            tm_hits = int(match.group(1))
        retries = len(self._RETRY_RE.findall(text))
        return {"windows": windows, "tm_hits": tm_hits, "retries": retries}

    def _record_run(self, rc: int) -> None:
        """Append this run to the persisted history (Log screen, left column)."""
        metrics = self._scan_run_metrics()
        self._run_metrics = metrics
        if rc == 0:
            status, tone = "ok", "ok"
            result_text = (
                f"{self._quality_summary.get('cue_count', 0)} cues"
                if self._quality_summary
                else "done"
            )
        elif rc == 2 and getattr(translate, "_cancel_requested", False):
            status, tone, result_text = "cancelled", "warn", "cancelled"
        else:
            status, tone = "failed", "err"
            warnings = int(self._quality_summary.get("warning_count", 0))
            result_text = f"{warnings} warnings" if warnings else "failed"

        source = self._url or self._file_path or ""
        title = os.path.basename(source) if source else "Untitled run"
        is_youtube = source.startswith(("http://", "https://"))
        if is_youtube:
            title = self._youtube_title or source

        # The two axes the Run screen exposes, spelled out. `modeCode` alone
        # ("YT" / "LC" / "OFF") is a legend the user has to be taught; the
        # history row states the source and the engine in words (§2.2: never
        # ship an abbreviation a reader cannot resolve).
        source_label = "YouTube URL" if is_youtube else "Local media file"
        engine_label = {
            PIPELINE_MODE_YOUTUBE_CLOUD: "Cloud LLM",
            PIPELINE_MODE_LOCAL_CLOUD: "Local ASR + Cloud LLM",
            PIPELINE_MODE_OFFLINE: "Local model",
        }.get(self._pipeline_mode, self._pipeline_mode)

        entry = {
            "title": title,
            "modeCode": (
                "YT" if self._pipeline_mode == PIPELINE_MODE_YOUTUBE_CLOUD
                else "OFF" if self._pipeline_mode == PIPELINE_MODE_OFFLINE
                else "LC"
            ),
            "mode": self._pipeline_mode,
            "sourceLabel": source_label,
            "engineLabel": engine_label,
            "started": self._run_started_clock or time.strftime("%H:%M:%S"),
            "duration": _format_seconds(self._stage_elapsed_sec),
            "status": status,
            "resultText": result_text,
            "resultTone": tone,
            "output": self._resolved_out_path or self._out_path,
            "exitCode": rc,
            "preset": self._content_preset,
            "model": (
                os.path.basename(self._local_model) if self._backend == "local" and self._local_model
                else (self._model or "from .env")
            ),
            "context": self._context_mode or "preset default",
            "batch": self._batch,
            "windows": metrics["windows"],
            "retries": metrics["retries"],
            "tmHits": metrics["tm_hits"],
            "cues": int(self._quality_summary.get("cue_count", 0)),
            "errors": int(self._quality_summary.get("error_count", 0)),
            "warnings": int(self._quality_summary.get("warning_count", 0)),
            "strict": self._result_strict_state,
            "elapsedSec": int(self._stage_elapsed_sec),
            # Only a successful run leaves a result to reload. A failed or
            # cancelled run gets no key at all, so the Log row can say why it
            # cannot be opened instead of silently doing nothing.
            "resultJson": self._archive_result_json() if rc == 0 else "",
        }

        history = self._history_entries()
        history.insert(0, entry)
        del history[20:]
        self._prune_run_results(history)
        self._run_history_json = json.dumps(history, ensure_ascii=False)
        self._selected_run_index = 0
        self._persist_fields()
        self.runHistoryChanged.emit()

    def _history_entries(self) -> list:
        try:
            data = json.loads(self._run_history_json or "[]")
        except (TypeError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _archive_result_json(self) -> str:
        """Copy the run's result JSON aside and return its filename, or "".

        Returns the *basename* only: the cache folder moves with the app, and an
        absolute path stored in a persisted entry would rot the moment the
        bundle is moved (the same failure that orphaned the downloaded models).
        """
        source = _result_json_path()
        if not os.path.isfile(source):
            return ""
        directory = _run_result_dir()
        if not directory:
            return ""
        stamp = int(time.time() * 1000)
        name = f"{stamp}.json"
        # Two runs can finish inside the same millisecond; a shared filename
        # would make the older entry unreadable the moment the newer one lands.
        suffix = 0
        while os.path.exists(os.path.join(directory, name)):
            suffix += 1
            name = f"{stamp}-{suffix}.json"
        try:
            shutil.copyfile(source, os.path.join(directory, name))
        except OSError as exc:
            self.logger.warning("could not archive the result JSON: %s", exc)
            return ""
        return name

    def _prune_run_results(self, history: list) -> None:
        """Delete archived results no surviving history entry points at."""
        directory = _run_result_dir()
        if not directory:
            return
        keep = {
            str(entry.get("resultJson"))
            for entry in history
            if entry.get("resultJson")
        }
        try:
            names = os.listdir(directory)
        except OSError:
            return
        for name in names:
            if name in keep or not name.endswith(".json"):
                continue
            try:
                os.remove(os.path.join(directory, name))
            except OSError:
                pass

    def _reset_result_state(self) -> None:
        self._result_ready = False
        self._result_strict_state = "pass" if self._strict_quality else "off"
        self._quality_summary = {}
        self.cue_model.clear()
        self.quality_issues_model.clear()
        self.resultReadyChanged.emit()

    def _load_result_json(self, path: str | None = None) -> bool:
        """Load a result JSON into the Review/Quality models.

        Defaults to the CLI's fixed `last_result.json`. The Log screen passes a
        per-run archive instead, which is the only way an older history entry
        can be opened at all.
        """
        path = path or _result_json_path()
        try:
            with open(path, encoding="utf-8") as f:
                result = json.load(f)
        except (OSError, ValueError) as exc:
            self.logger.warning("could not read result JSON %s: %s", path, exc)
            return False

        cues = result.get("cues") or []
        quality = result.get("quality") or {}
        if not isinstance(cues, list):
            return False

        # Max rendered line length (post line-breaking) for the Quality tab.
        max_line_chars = 0
        for cue in cues:
            for line in str(cue.get("text") or "").replace("\\N", "\n").splitlines():
                max_line_chars = max(max_line_chars, len(line.strip()))

        summary = dict(quality)
        summary["max_line_chars"] = max_line_chars
        self._quality_summary = summary

        # Build per-cue issue tags so the Review "Errors" filter can match the
        # same cues the Quality tab flags, without a second copy of the data.
        tags_by_index: dict[int, list[str]] = {}
        for entry in quality.get("issues", []):
            ci = int(entry.get("cue_index", 0))
            for tag in entry.get("issues", []):
                tags_by_index.setdefault(ci, []).append(tag)
        self.cue_model.load(cues, tags_by_index)
        self.quality_issues_model.load_from_report(quality)
        if self._strict_quality:
            self._result_strict_state = "pass"
        self._result_ready = True
        self.resultReadyChanged.emit()
        return True

    # --- Review editing: save / re-check / find-replace (UX review S-01) ------
    @Property(int, notify=reviewDirtyChanged)
    def cueEditedCount(self) -> int:
        return self.cue_model.edited_count()

    def _cues_for_save(self) -> list:
        """Rebuild srt_io.Cue objects from the (possibly edited) model."""
        from src.srt_io import Cue

        cues: list = []
        for i in range(self.cue_model.count):
            c = self.cue_model.get_cue(i)
            if not c:
                continue
            cues.append(
                Cue(
                    start=float(c.get("start_ms", 0)) / 1000.0,
                    end=float(c.get("end_ms", 0)) / 1000.0,
                    text=c.get("text", "") or "",
                )
            )
        return cues

    @Slot(result=bool)
    def saveEditedSubtitles(self, path: str) -> bool:
        """Write the (possibly edited) cues to `path`; format from extension."""
        if not self._result_ready:
            return False
        cues = self._cues_for_save()
        if not cues:
            return False
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".ass":
                ass_io.write_ass(path, cues)
            else:
                srt_io.write_srt(cues, path)
        except OSError as exc:
            self.logger.error("save failed: %s", exc)
            self._set_status(f"Could not save: {exc}")
            return False
        self._resolved_out_path = os.path.abspath(path)
        self.canOpenOutputFolderChanged.emit()
        self._set_status(f"Saved edited subtitles to {path}")
        return True

    @Slot(result=bool)
    def saveEditedSubtitlesToDefault(self) -> bool:
        path = self._resolved_out_path or self._out_path
        if not path:
            return False
        return self.saveEditedSubtitles(path)

    @Slot()
    def recheckQuality(self) -> None:
        """Re-run quality checks on the edited cues without re-translating (S-01)."""
        self._refresh_quality_from_cues(announce=True)

    def _refresh_quality_from_cues(self, *, announce: bool) -> None:
        """Re-run the quality checks against the *edited* cues.

        Shared by the explicit `Re-check` action and by the Review inspector,
        which calls it after every committed edit. Keeping one implementation
        means the live per-cue flags and the explicit re-check can never
        disagree.
        """
        if not self._result_ready:
            return
        cues = self._cues_for_save()
        untranslated = sum(1 for c in cues if not (c.text or "").strip())
        report = subtitle_quality.build_report(cues, untranslated_count=untranslated)
        summary = dict(report.to_dict())
        max_line = 0
        for c in cues:
            for line in (c.text or "").replace("\\N", "\n").splitlines():
                max_line = max(max_line, len(line.strip()))
        summary["max_line_chars"] = max_line
        self._quality_summary = summary
        self.quality_issues_model.load_from_report(summary)
        self._sync_cue_tags(summary)
        # The gate verdict is a function of the cues, so it has to move with
        # them. Editing a leaked tag away turns FAIL into PASS without a re-run
        # (T-5.7).
        if self._strict_quality:
            self._result_strict_state = "fail" if report.error_count else "pass"
        self.resultReadyChanged.emit()
        if announce:
            self._set_status("Re-checked the edited subtitles.")

    def _sync_cue_tags(self, summary: dict) -> None:
        """Push the report's per-cue tags back into the Review rows."""
        tags_by_index: dict[int, list[str]] = {}
        for entry in summary.get("issues", []):
            ci = int(entry.get("cue_index", 0))
            tags_by_index.setdefault(ci, []).extend(entry.get("issues", []))
        self.cue_model.set_tags(tags_by_index)

    @Slot(str, bool, result=int)
    def countCueMatches(self, find: str, use_regex: bool) -> int:
        """How many replacements `replaceInCues` would make, without making them.

        Backs the Review "Find & replace" card's live count and its disabled
        `Replace all` (UI review 5.5). An action that silently does nothing is
        worse than one that is visibly unavailable, and a regex that does not
        compile is the common case.
        """
        if not find:
            return 0
        import re as _re

        try:
            rx = _re.compile(find) if use_regex else None
        except _re.error:
            return 0
        total = 0
        for i in range(self.cue_model.count):
            text = self.cue_model.get_cue(i).get("text", "") or ""
            total += len(rx.findall(text)) if rx is not None else text.count(find)
        return total

    @Slot(str, str, bool, result=int)
    def replaceInCues(self, find: str, replace: str, use_regex: bool) -> int:
        """Bulk find/replace across cue translations. Returns replacements made."""
        if not find:
            return 0
        import re as _re

        try:
            rx = _re.compile(find) if use_regex else None
        except _re.error:
            return 0
        count = 0
        for i in range(self.cue_model.count):
            c = self.cue_model.get_cue(i)
            text = c.get("text", "") or ""
            if rx:
                new, n = rx.subn(replace, text)
            elif find in text:
                new = text.replace(find, replace)
                n = text.count(find)
            else:
                continue
            if n:
                self.cue_model.setData(self.cue_model.index(i, 0), new, Qt.EditRole)
                count += n
        return count

    @Slot()
    def revertAllEdits(self) -> None:
        self.cue_model.revert_all()

    @Slot()
    def openInExternalEditor(self) -> None:
        path = self._resolved_out_path or self._out_path
        if not path:
            self._set_status("No output file to open yet.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self._set_status("Could not open the file in an editor.")

    # --- Quality -> Review navigation (UX review S-05) ------------------------
    @Property(int, notify=focusCueIndexChanged)
    def focusCueIndex(self) -> int:
        return self._focus_cue_index

    @Slot(int)
    def revealCue(self, cue_number: int) -> None:
        """Jump from a Quality issue to the matching cue in the Review tab."""
        self.cue_proxy.filterMode = "all"
        self.cue_proxy.searchText = ""
        # A timeline range left over from an earlier drag would hide the cue we
        # are being asked to reveal.
        self.cue_proxy.clearCueRange()
        self._focus_cue_index = max(0, int(cue_number) - 1)
        self.focusCueIndexChanged.emit()
        self.requestTab.emit(1)

    @Slot(int)
    def revealIssueForCue(self, cue_number: int) -> None:
        """Jump from a cue's quality flags to its row in the Quality issue list."""
        self.quality_issues_model.focus_cue(max(1, int(cue_number)))
        self.requestTab.emit(2)

    @Slot(str)
    def saveWindowState(self, geometry: str) -> None:
        """Persist window geometry: 'x,y,width,height'.

        ``@Slot`` is load-bearing: ``Main.qml`` calls this from ``onClosing``,
        and QML can only invoke slots / invokable methods. Without the
        decorator the call was silently dropped and the window geometry never
        persisted.
        """
        parts = (geometry or "").split(",")
        if len(parts) != 4:
            return
        try:
            x, y, w, h = (int(float(p)) for p in parts)
        except ValueError:
            return
        changed = (x, y, w, h) != (self._win_x, self._win_y, self._win_w, self._win_h)
        self._win_x, self._win_y, self._win_w, self._win_h = x, y, w, h
        if changed:
            self._persist_fields()

    @Property(int, constant=True)
    def windowX(self) -> int:
        return self._win_x

    @Property(int, constant=True)
    def windowY(self) -> int:
        return self._win_y

    @Property(int, constant=True)
    def windowWidth(self) -> int:
        return self._win_w

    @Property(int, constant=True)
    def windowHeight(self) -> int:
        return self._win_h

    # =====================================================================
    # Subtitle Studio shell: accent, cue editing, quality report, run history
    # =====================================================================

    _ACCENTS = ("iris", "azure", "mint", "amber", "rose")

    @Property(str, notify=accentChanged)
    def accentName(self) -> str:
        return self._accent_name

    @accentName.setter
    def accentName(self, value: str) -> None:
        value = (value or "iris").strip().lower()
        if value not in self._ACCENTS:
            value = "iris"
        if self._accent_name != value:
            self._accent_name = value
            self.accentChanged.emit()
            self._persist_fields()

    # --- Keyboard shortcuts (UI review 5.5) -------------------------------
    #
    # The shortcut list used to be read-only, mirrored in three places and
    # mis-filed under Settings — decoration, not configuration. It is now a
    # real remap surface: `shortcutMap` drives Main.qml's `Shortcut.sequence`
    # bindings, `setShortcut` records a new combo, and conflicts are reported
    # rather than silently allowed.

    # (action id, human label, default sequence). Order is display order.
    _SHORTCUT_DEFAULTS = (
        ("run", "Run a translation", "Ctrl+Return"),
        ("cancel", "Cancel the run", "Ctrl+."),
        ("palette", "Command palette", "Ctrl+K"),
        ("save", "Save edited subtitles", "Ctrl+S"),
        ("search", "Search cues", "Ctrl+F"),
        ("goto_run", "Go to Run", "Ctrl+1"),
        ("goto_review", "Go to Review", "Ctrl+2"),
        ("goto_quality", "Go to Quality", "Ctrl+3"),
        ("goto_log", "Go to Log", "Ctrl+L"),
        ("goto_settings", "Go to Settings", "Ctrl+,"),
        ("cue_next", "Next / previous cue", "\u2191 \u2193"),
    )

    def _default_shortcuts(self) -> dict[str, str]:
        return {action: seq for action, _label, seq in self._SHORTCUT_DEFAULTS}

    def _loaded_shortcuts(self) -> dict[str, str]:
        """Stored overrides merged over the defaults, unknown ids dropped."""
        merged = self._default_shortcuts()
        try:
            stored = json.loads(self._shortcuts_json or "{}")
        except (TypeError, ValueError):
            return merged
        if not isinstance(stored, dict):
            return merged
        for action, seq in stored.items():
            if action in merged and isinstance(seq, str) and seq.strip():
                merged[action] = seq.strip()
        return merged

    @Property("QVariantMap", notify=shortcutsChanged)
    def shortcutMap(self) -> dict:
        """action id -> sequence. This is what Main.qml binds its Shortcuts to."""
        return self._loaded_shortcuts()

    @Property("QVariantList", notify=shortcutsChanged)
    def shortcutRows(self) -> list:
        """Display rows: label, current sequence, default, conflict flag."""
        current = self._loaded_shortcuts()
        defaults = self._default_shortcuts()
        # Count each sequence so a duplicate can be flagged on both rows.
        seen: dict[str, int] = {}
        for seq in current.values():
            seen[seq] = seen.get(seq, 0) + 1
        rows = []
        for action, label, default in self._SHORTCUT_DEFAULTS:
            seq = current[action]
            rows.append({
                "action": action,
                "label": label,
                "sequence": seq,
                "default": default,
                "isDefault": seq == default,
                "conflict": seen.get(seq, 0) > 1,
            })
        return rows

    @Slot(str, result=str)
    def shortcutFor(self, action: str) -> str:
        return self._loaded_shortcuts().get(action, "")

    @Slot(str, str, result=str)
    def setShortcut(self, action: str, sequence: str) -> str:
        """Record a new combo. Returns "" on success, or a reason on refusal."""
        sequence = (sequence or "").strip()
        if action not in self._default_shortcuts():
            return "Unknown shortcut."
        if sequence == "":
            return "Press a key combination first."
        try:
            current = json.loads(self._shortcuts_json or "{}")
        except (TypeError, ValueError):
            current = {}
        if not isinstance(current, dict):
            current = {}
        current[action] = sequence
        self._shortcuts_json = json.dumps(current, sort_keys=True)
        self.shortcutsChanged.emit()
        self._notify_form_changed()
        return ""

    @Slot(str)
    def resetShortcut(self, action: str) -> None:
        try:
            current = json.loads(self._shortcuts_json or "{}")
        except (TypeError, ValueError):
            current = {}
        if isinstance(current, dict) and action in current:
            current.pop(action)
            self._shortcuts_json = json.dumps(current, sort_keys=True)
            self.shortcutsChanged.emit()
            self._notify_form_changed()

    @Slot()
    def resetAllShortcuts(self) -> None:
        self._shortcuts_json = "{}"
        self.shortcutsChanged.emit()
        self._notify_form_changed()

    @Slot()
    def saveSettings(self) -> None:
        """Flush the store immediately.

        No longer a visible button (autosave owns the normal path); kept as a
        slot for the command palette and for the ``onClosing`` flush.
        """
        self._save_timer.stop()
        self._persist_fields()
        self._set_dirty(False)
        self._set_status("Settings saved.")

    @Property(bool, notify=dirtyChanged)
    def dirty(self) -> bool:
        """True while an edit is waiting for the autosave debounce.

        One truth for the save lifecycle: the top-bar strip mirrors this, and
        there is no second "Save" affordance to contradict it (UI review 3.4).
        """
        return self._dirty

    @Property(str, notify=dirtyChanged)
    def saveStateText(self) -> str:
        return "Unsaved changes" if self._dirty else "Saved"

    # --- Cue editing ------------------------------------------------------
    def _on_cue_data_changed(self, *_args) -> None:
        self._dist_cache = None
        self.cueDataChanged.emit()

    def _source_row(self, proxy_row: int) -> int:
        """Map a row of the (filtered) Review table onto the source model.

        The Review table shows a filtered proxy, so a visible row index is not
        a source row index. Every editing slot the inspector calls therefore
        maps through here rather than assuming they are the same.
        """
        index = self.cue_proxy.index(proxy_row, 0)
        if not index.isValid():
            return -1
        source = self.cue_proxy.mapToSource(index)
        return source.row() if source.isValid() else -1

    @Slot(int, str)
    def setCueText(self, row: int, text: str) -> None:
        """Write one cue's translation (the Review inspector's text area).

        Re-runs the quality checks immediately so the issue chips under the
        editor, the row's severity bar and the Quality counts all move as the
        edit lands. Without this the flags stayed frozen at the values the last
        run produced, so fixing a cue left it looking broken (UI review 5.4).
        """
        source_row = self._source_row(row)
        if source_row < 0:
            return
        if not self.cue_model.setData(self.cue_model.index(source_row, 0), text, Qt.EditRole):
            return
        self._refresh_quality_from_cues(announce=False)

    @Slot(int)
    def revertCue(self, row: int) -> None:
        source_row = self._source_row(row)
        if source_row >= 0:
            self.cue_model.revert_cue(source_row)

    @Slot(int, int)
    def nudgeCueStart(self, row: int, delta_ms: int) -> None:
        self._nudge_cue(row, "start_ms", delta_ms)

    @Slot(int, int)
    def nudgeCueEnd(self, row: int, delta_ms: int) -> None:
        self._nudge_cue(row, "end_ms", delta_ms)

    def _nudge_cue(self, row: int, key: str, delta_ms: int) -> None:
        """Shift one cue edge by ``delta_ms`` without breaking the ordering.

        The start may not cross the end (and vice versa), so a cue can never be
        nudged into an inverted or zero-length interval.
        """
        source_row = self._source_row(row)
        cue = self.cue_model.peek_cue(source_row)
        if not cue:
            return
        start = float(cue.get("start_ms", 0))
        end = float(cue.get("end_ms", 0))
        if key == "start_ms":
            start = max(0.0, min(start + delta_ms, end - 40.0))
        else:
            end = max(start + 40.0, end + delta_ms)
        self.cue_model.set_times(source_row, start, end)

    @Slot(int)
    def autoFixCue(self, row: int) -> None:
        """Strip ASR tags, fansub markup and stray CJK from one cue."""
        source_row = self._source_row(row)
        cue = self.cue_model.peek_cue(source_row)
        if not cue:
            return
        text = str(cue.get("text", "") or "")
        fixed = subtitle_quality.clean_translation_text(text)
        if fixed != text:
            self.cue_model.setData(self.cue_model.index(source_row, 0), fixed, Qt.EditRole)
            self._set_status(f"Auto-fixed cue {cue.get('index', source_row + 1)}.")

    @Slot(str)
    def copyToClipboard(self, text: str) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(text or "")
        self._set_status("Copied to the clipboard.")

    # --- Cue aggregates ---------------------------------------------------
    @Property("QVariantMap", notify=resultReadyChanged)
    def cueCounts(self) -> dict:
        """Per-status cue counts, for the Review filter chips."""
        ok = warnings = failed = 0
        for i in range(self.cue_model.count):
            status = str(self.cue_model.peek_cue(i).get("status", "ok"))
            if status in ("untranslated", "empty"):
                failed += 1
            elif status == "warning":
                warnings += 1
            else:
                ok += 1
        return {
            "total": self.cue_model.count,
            "ok": ok,
            "warnings": warnings,
            "failed": failed,
        }

    @Property("QVariantList", notify=resultReadyChanged)
    def cueTimeline(self) -> list:
        """One bar per cue: {left, width, tone} as fractions of the total run."""
        total = self._result_duration_ms()
        if total <= 0:
            return []
        bars = []
        for i in range(self.cue_model.count):
            cue = self.cue_model.peek_cue(i)
            start = max(0.0, float(cue.get("start_ms", 0)))
            end = max(start, float(cue.get("end_ms", 0)))
            status = str(cue.get("status", "ok"))
            if status in ("untranslated", "empty"):
                tone = "err"
            elif status == "warning":
                tone = "warn"
            else:
                tone = "ok"
            bars.append(
                {
                    "left": start / total,
                    "width": max(0.0015, (end - start) / total),
                    "tone": tone,
                    # 1-based cue number so the timeline can highlight the cue
                    # the inspector has open even when the table is filtered.
                    "cue": int(cue.get("index", i + 1)),
                }
            )
        return bars

    @Property("QVariantList", notify=resultReadyChanged)
    def cueTimelineRuler(self) -> list:
        total = self._result_duration_ms()
        if total <= 0:
            return []
        return [
            _format_clock_ms(total * i / 4.0) for i in range(5)
        ]

    def _result_duration_ms(self) -> float:
        if self.cue_model.count == 0:
            return 0.0
        return max(
            (float(self.cue_model.peek_cue(i).get("end_ms", 0)) for i in range(self.cue_model.count)),
            default=0.0,
        )

    # --- Quality report ---------------------------------------------------
    @Property(int, notify=resultReadyChanged)
    def qualityScore(self) -> int:
        return self._compute_score()[0]

    @Property(str, notify=resultReadyChanged)
    def qualityGrade(self) -> str:
        return self._compute_score()[1]

    @Property(str, notify=resultReadyChanged)
    def qualityScoreTone(self) -> str:
        return self._compute_score()[2]

    def _compute_score(self) -> tuple[int, str, str]:
        if not self._result_ready or not self._quality_summary:
            return 0, "No report", "mute"
        summary = self._quality_summary
        total = max(1, int(summary.get("cue_count", 0)))
        errors = (
            int(summary.get("error_count", 0))
            + int(summary.get("untranslated_count", 0))
            + int(summary.get("untranslated_marker_count", 0))
        )
        warnings = int(summary.get("warning_count", 0))
        penalty = (errors * 12.0 + warnings * 3.0) / total * 10.0
        score = int(max(0, min(100, round(100.0 - penalty))))
        if score >= 95:
            grade, tone = "Excellent", "ok"
        elif score >= 85:
            grade, tone = "Good", "ok"
        elif score >= 70:
            grade, tone = "Fair", "warn"
        elif score >= 50:
            grade, tone = "Poor", "warn"
        else:
            grade, tone = "Failing", "err"
        return score, grade, tone

    @Property("QVariantList", notify=resultReadyChanged)
    def qualityTiles(self) -> list:
        if not self._result_ready:
            labels = (
                "Total cues", "Untranslated", "Errors", "Warnings",
                "Avg CPS", "Max line chars", "Strict gate",
            )
            return [
                {"value": "\u2014", "label": t, "tone": "mute", "hint": "",
                 "breakdown": []}
                for t in labels
            ]

        summary = self._quality_summary
        untranslated = self.qualityUntranslated
        # These two tiles sit directly above the Issues table and click through
        # to it, so they must count what it lists: issue **rows**, not the cues
        # those rows belong to. A cue can carry two errors (a blank cue is both
        # `empty_text` and `cps_error`), and using the cue-level `qualityErrors`
        # here made the "Errors" tile and the "Errors" filter chip over the same
        # table disagree. `qualityErrors` keeps its cue-level meaning for the
        # icon-rail badge and the Review page, which count cues.
        issue_counts = self.quality_issues_model.counts
        errors = int(issue_counts.get("errors", 0))
        warnings = int(issue_counts.get("warnings", 0))
        gate = self._result_strict_state
        total = int(summary.get("cue_count", 0))
        return [
            {"value": str(total), "label": "Total cues", "tone": "", "hint": "",
             "breakdown": [
                 {"k": "Translated", "v": max(0, total - untranslated)},
                 {"k": "Untranslated", "v": untranslated},
             ]},
            {"value": str(untranslated), "label": "Untranslated",
             "tone": "err" if untranslated else "ok",
             "hint": "Cues the translator failed to fill in.",
             "breakdown": []},
            {"value": str(errors), "label": "Errors",
             "tone": "err" if errors else "ok",
             "hint": "Error-level issues listed in the table below.",
             # The same rows the Issues table lists, grouped by kind.
             "breakdown": self.quality_issues_model.breakdown("error")},
            {"value": str(warnings), "label": "Warnings",
             "tone": "warn" if warnings else "ok",
             "hint": "Warning-level issues listed in the table below.",
             "breakdown": self.quality_issues_model.breakdown("warning")},
            {"value": self.qualityAverageCpsText, "label": "Avg CPS", "tone": "",
             "hint": "Average characters per second across all cues.",
             "breakdown": []},
            {"value": str(self.qualityMaxLineChars), "label": "Max line chars", "tone": "",
             "hint": "Longest rendered subtitle line.",
             "breakdown": []},
            {"value": "PASS" if gate == "pass" else "FAIL" if gate == "fail" else "OFF",
             "label": "Strict gate",
             "tone": "err" if gate == "fail" else "ok" if gate == "pass" else "mute",
             "hint": "Whether the strict quality gate would let this run through.",
             "breakdown": []},
        ]

    @Property("QVariantMap", notify=resultReadyChanged)
    def qualityLimits(self) -> dict:
        return {
            "cpsWarn": subtitle_quality.CPS_WARNING,
            "cpsError": subtitle_quality.CPS_ERROR,
            "charsWarn": subtitle_quality.CHARS_WARNING,
            "charsError": subtitle_quality.CHARS_ERROR,
            "durationMin": subtitle_quality.MIN_DURATION_WARNING,
            "durationMax": subtitle_quality.MAX_DURATION_WARNING,
            "linesWarn": subtitle_quality.LINES_WARNING,
            "linesError": subtitle_quality.LINES_ERROR,
        }

    @Property("QVariantList", notify=resultReadyChanged)
    def qualityThresholds(self) -> list:
        limits = self.qualityLimits
        return [
            {"k": "Characters / second",
             "v": f"warn {limits['cpsWarn']:g} \u00b7 error {limits['cpsError']:g}"},
            {"k": "Characters / line",
             "v": f"warn {limits['charsWarn']:g} \u00b7 error {limits['charsError']:g}"},
            {"k": "Duration",
             "v": f"{limits['durationMin']:g} \u2013 {limits['durationMax']:g} s"},
            {"k": "Lines per cue",
             "v": f"warn {limits['linesWarn']:g} \u00b7 error {limits['linesError']:g}"},
            {"k": "Leakage \u00b7 empty \u00b7 marker", "v": "error", "tone": "err"},
            {"k": "Residue \u00b7 duplicate \u00b7 overlap", "v": "warning", "tone": "warn"},
        ]

    @Property("QVariantMap", notify=resultReadyChanged)
    def qualityCpsHistogram(self) -> dict:
        return self._distributions()["cps"]

    @Property("QVariantMap", notify=resultReadyChanged)
    def qualityDurationHistogram(self) -> dict:
        return self._distributions()["duration"]

    def _distributions(self) -> dict:
        """Cached CPS / duration histograms (invalidated by any cue change)."""
        if self._dist_cache is not None:
            return self._dist_cache

        empty = {
            "cps": {"bars": [], "labels": [], "summary": ""},
            "duration": {"bars": [], "labels": [], "summary": ""},
        }
        if not self._result_ready or self.cue_model.count == 0:
            self._dist_cache = empty
            return empty

        cps_buckets = [0] * 10
        cps_width = 4.0
        dur_buckets = [0] * 9
        dur_width = 0.8
        cps_values: list[float] = []
        durations: list[float] = []
        for i in range(self.cue_model.count):
            cue = self.cue_model.peek_cue(i)
            duration = max(
                0.0, (float(cue.get("end_ms", 0)) - float(cue.get("start_ms", 0))) / 1000.0
            )
            chars = len(re.sub(r"\s+", "", str(cue.get("text", "") or "")))
            cps = chars / duration if duration > 0 else 0.0
            cps_values.append(cps)
            durations.append(duration)
            cps_buckets[min(9, int(cps / cps_width))] += 1
            dur_buckets[min(8, int(duration / dur_width))] += 1

        def _bars(counts, width, warn_over, error_over=None):
            """Bucket counts as 0..1 bars, toned by the *real* thresholds.

            The legend names these numbers, so the bars have to be toned from
            the same constants — a hand-tuned cutoff here would make the legend
            a caption for a chart that says something else (UI review 5.10).
            """
            peak = max(counts) or 1
            out = []
            for index, count in enumerate(counts):
                centre = (index + 0.5) * width
                if error_over is not None and centre > error_over:
                    tone = "err"
                elif centre > warn_over:
                    tone = "warn"
                else:
                    tone = ""
                out.append({"v": count / peak, "tone": tone})
            return out

        cps_sorted = sorted(cps_values)
        p95 = cps_sorted[min(len(cps_sorted) - 1, int(0.95 * len(cps_sorted)))]
        # The last bucket of each histogram is an overflow bucket: values above
        # `(n - 0.5) * width` are clamped into it. Labelling it with its centre
        # made a 9.0 s cue appear under an axis tick reading "6.8" (Appendix A
        # probe 2), so the final tick is marked open-ended.
        result = {
            "cps": {
                "bars": _bars(cps_buckets, cps_width,
                              subtitle_quality.CPS_WARNING,
                              subtitle_quality.CPS_ERROR),
                "labels": [
                    f"{int((i + 0.5) * cps_width)}" + ("+" if i == 9 else "")
                    for i in range(10)
                ],
                "summary": (
                    f"avg {sum(cps_values) / len(cps_values):.1f} \u00b7 p95 {p95:.1f}"
                ),
            },
            "duration": {
                "bars": _bars(dur_buckets, dur_width, subtitle_quality.MAX_DURATION_WARNING),
                "labels": [
                    f"{(i + 0.5) * dur_width:.1f}" + ("+" if i == 8 else "")
                    for i in range(9)
                ],
                "summary": (
                    f"avg {sum(durations) / len(durations):.1f} s "
                    f"\u00b7 max {max(durations):.1f} s"
                ),
            },
        }
        self._dist_cache = result
        return result

    @Property("QVariantList", notify=resultReadyChanged)
    def runContext(self) -> list:
        if not self._result_ready:
            return [{"k": "Status", "v": "No run loaded", "mono": False}]
        metrics = self._run_metrics or {}
        mode_label = {
            PIPELINE_MODE_YOUTUBE_CLOUD: "YouTube Cloud",
            PIPELINE_MODE_LOCAL_CLOUD: "Local ASR + Cloud",
            PIPELINE_MODE_OFFLINE: "Offline",
        }.get(self._pipeline_mode, self._pipeline_mode)
        model = (
            os.path.basename(self._local_model)
            if self._backend == "local" and self._local_model
            else (self._model or "from .env")
        )
        return [
            {"k": "Mode", "v": mode_label},
            {"k": "Model", "v": model, "mono": True},
            {"k": "Preset", "v": self._content_preset, "mono": True},
            {"k": "Context", "v": self._context_mode or "preset default", "mono": True},
            {"k": "Batch", "v": str(self._batch), "mono": True},
            {"k": "Translation memory", "v": f"{metrics.get('tm_hits', 0)} hits", "mono": True},
            {"k": "Windows", "v": str(metrics.get("windows", 0)), "mono": True},
            {"k": "Retries", "v": str(metrics.get("retries", 0)), "mono": True},
            {"k": "Wall clock", "v": _format_seconds(self._stage_elapsed_sec), "mono": True},
        ]

    @Slot()
    def exportQualityReport(self) -> None:
        """Write the current quality report next to the output file."""
        if not self._result_ready or not self._quality_summary:
            self._set_status("No quality report to export yet.")
            return
        target = self._export_target("quality_report.json")
        try:
            with open(target, "w", encoding="utf-8") as handle:
                json.dump(self._quality_summary, handle, indent=2, ensure_ascii=False)
        except OSError as exc:
            self._set_status(f"Could not export the report: {exc}")
            return
        self._set_status(f"Quality report written to {target}")

    @Slot()
    def exportIssueCsv(self) -> None:
        """Write the issue list as CSV next to the output file."""
        if not self._result_ready or not self._quality_summary:
            self._set_status("No issues to export yet.")
            return
        import csv

        target = self._export_target("quality_issues.csv")
        try:
            with open(target, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["cue", "type", "severity", "message"])
                for i in range(self.quality_issues_model.rowCount()):
                    index = self.quality_issues_model.index(i, 0)
                    writer.writerow([
                        self.quality_issues_model.data(index, QualityIssuesModel.CueRole),
                        self.quality_issues_model.data(index, QualityIssuesModel.RawTypeRole),
                        self.quality_issues_model.data(index, QualityIssuesModel.SeverityRole),
                        self.quality_issues_model.data(index, QualityIssuesModel.MessageRole),
                    ])
        except OSError as exc:
            self._set_status(f"Could not export the issue list: {exc}")
            return
        self._set_status(f"Issue list written to {target}")

    def _export_target(self, filename: str) -> str:
        folder = os.path.dirname(self._resolved_out_path or self._out_path or "")
        if not folder or not os.path.isdir(folder):
            folder = _base_dir()
        return os.path.join(folder, filename)

    @Slot()
    def exportLog(self) -> None:
        target = os.path.join(_base_dir(), "translation_agent_log.txt")
        try:
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(self._log_text or "")
        except OSError as exc:
            self._set_status(f"Could not export the log: {exc}")
            return
        self._set_status(f"Log written to {target}")

    # --- Run history ------------------------------------------------------
    @Property("QVariantList", notify=runHistoryChanged)
    def runHistory(self) -> list:
        return self._history_entries()

    @Property(int, notify=runHistoryChanged)
    def selectedRunIndex(self) -> int:
        return self._selected_run_index

    @selectedRunIndex.setter
    def selectedRunIndex(self, value: int) -> None:
        try:
            index = int(value)
        except (TypeError, ValueError):
            return
        history = self._history_entries()
        if index < -1 or index >= len(history):
            index = -1
        if self._selected_run_index != index:
            self._selected_run_index = index
            self.runHistoryChanged.emit()

    @Slot(int)
    def selectRun(self, index: int) -> None:
        """Select a history entry **and** load its result into Review/Quality.

        Selecting without loading left the Log screen as a list of rows that
        could be highlighted but never opened — the review's complaint that the
        history is decorative. Loading is best-effort and says why when it
        cannot: a failed run wrote no result, and an entry whose archive has
        been pruned (or whose cache folder was cleared) has nothing to read.
        """
        self.selectedRunIndex = index
        if self._selected_run_index < 0:
            self._reset_result_state()
            return
        entry = self._history_entries()[self._selected_run_index]

        # The entry's own archive first. The CLI's live output file is only a
        # fallback for an entry recorded before results were archived, and only
        # when that entry actually succeeded — after a failed run the live file
        # still holds the *previous* run's result, so trusting it would show the
        # wrong run under the right row.
        name = str(entry.get("resultJson") or "")
        directory = _run_result_dir()
        if name and directory:
            path = os.path.join(directory, name)
            if os.path.isfile(path) and self._load_result_json(path):
                self._set_status(f"Loaded {entry.get('title', 'the run')}.")
                return
        if (self._selected_run_index == 0 and entry.get("exitCode") == 0
                and self._load_result_json()):
            self._set_status("Showing the most recent run.")
            return

        self._reset_result_state()
        self._set_status(self.selectedRunProblem)

    @Property(bool, notify=runHistoryChanged)
    def selectedRunOpenable(self) -> bool:
        """Whether the selected entry can still be opened in Review/Quality."""
        history = self._history_entries()
        index = self._selected_run_index
        if index < 0 or index >= len(history):
            return False
        entry = history[index]
        name = str(entry.get("resultJson") or "")
        directory = _run_result_dir()
        if name and directory and os.path.isfile(os.path.join(directory, name)):
            return True
        return bool(index == 0 and entry.get("exitCode") == 0
                    and os.path.isfile(_result_json_path()))

    @Property(str, notify=runHistoryChanged)
    def selectedRunProblem(self) -> str:
        """Why the selected entry cannot be opened; empty when it can."""
        history = self._history_entries()
        index = self._selected_run_index
        if index < 0 or index >= len(history):
            return ""
        if self.selectedRunOpenable:
            return ""
        entry = history[index]
        if entry.get("exitCode") != 0:
            return (f"That run {entry.get('status', 'did not finish')}, so it left "
                    f"no result to review.")
        return "That run's result is no longer stored on disk."

    @Property("QVariantList", notify=runHistoryChanged)
    def selectedRunRows(self) -> list:
        history = self._history_entries()
        index = self._selected_run_index
        if index < 0 or index >= len(history):
            return []
        entry = history[index]
        mode_label = {
            PIPELINE_MODE_YOUTUBE_CLOUD: "YouTube Cloud",
            PIPELINE_MODE_LOCAL_CLOUD: "Local ASR + Cloud",
            PIPELINE_MODE_OFFLINE: "Offline",
        }.get(entry.get("mode", ""), entry.get("mode", "\u2014"))
        return [
            {"k": "Source", "v": str(entry.get("sourceLabel") or mode_label)},
            {"k": "Engine", "v": str(entry.get("engineLabel") or mode_label)},
            {"k": "Started", "v": str(entry.get("started", "\u2014")), "mono": True},
            {"k": "Duration", "v": str(entry.get("duration", "\u2014")), "mono": True},
            {"k": "Exit code", "v": str(entry.get("exitCode", "\u2014")),
             "tone": "ok" if entry.get("exitCode") == 0 else "err", "mono": True},
            {"k": "Preset", "v": str(entry.get("preset", "\u2014")), "mono": True},
            {"k": "Model", "v": str(entry.get("model", "\u2014")), "mono": True},
            {"k": "Context", "v": str(entry.get("context", "\u2014")), "mono": True},
            {"k": "Batch", "v": str(entry.get("batch", "\u2014")), "mono": True},
            {"k": "Windows", "v": str(entry.get("windows", 0)), "mono": True},
            {"k": "Retries", "v": str(entry.get("retries", 0)), "mono": True},
            {"k": "Cues", "v": str(entry.get("cues", 0)), "mono": True},
            {"k": "Output", "v": str(entry.get("output", "\u2014")), "mono": True},
        ]

    @Slot()
    def clearRunHistory(self) -> None:
        self._run_history_json = "[]"
        self._selected_run_index = -1
        self._prune_run_results([])
        self._persist_fields()
        self.runHistoryChanged.emit()
        self._set_status("Run history cleared.")

    @Slot()
    def rerunLastRun(self) -> None:
        """Restore the settings the last run used and start it again."""
        if self._is_running:
            return
        if not self._last_run_snapshot:
            self._set_status("Nothing to re-run yet.")
            return
        for attr, value in self._last_run_snapshot.items():
            if attr == "_url":
                self._url = value
            elif attr == "_file_path":
                self._file_path = value
            else:
                setattr(self, attr, value)
        self._apply_pipeline_mode(self._pipeline_mode)
        self._notify_form_changed()
        self._set_status("Re-running the last settings.")
        self.runTranslation()

    # --- Files / models ---------------------------------------------------
    @Property(str, notify=formChanged)
    def fileSizeText(self) -> str:
        path = self._file_path
        if not path or not os.path.isfile(path):
            return "\u2014"
        try:
            return _format_bytes(os.path.getsize(path))
        except OSError:
            return "\u2014"

    @Property(str, constant=True)
    def modelsFolder(self) -> str:
        return _gguf_dir()

    @Property(str, notify=formChanged)
    def modelsUsedText(self) -> str:
        """Disk used by model files across every search folder.

        Only ``*.gguf`` counts: the folder next to the executable is searched
        too, and summing everything in it would add the .exe and the whole
        ``_internal`` tree to a number that claims to be "models".
        """
        total = 0
        try:
            for folder in _model_search_dirs():
                if not os.path.isdir(folder):
                    continue
                for name in os.listdir(folder):
                    if not name.lower().endswith(".gguf"):
                        continue
                    path = os.path.join(folder, name)
                    if os.path.isfile(path):
                        total += os.path.getsize(path)
        except OSError:
            return "\u2014"
        return _format_bytes(total)

    @Property("QVariantList", constant=True)
    def modelSearchPaths(self) -> list:
        """Folders the app looks in for models, in order, as display rows.

        Shown in Settings so a client machine can be told *where* to put the
        ``.gguf`` files instead of guessing.
        """
        rows = []
        for directory in _model_search_dirs():
            exists = os.path.isdir(directory)
            rows.append({
                "path": directory,
                "exists": exists,
                "writable": _is_writable_dir(directory),
                "primary": os.path.normcase(directory) == os.path.normcase(_gguf_dir()),
            })
        return rows

    @Property("QVariantList", notify=formChanged)
    def modelsInventory(self) -> list:
        """The Models & storage table: every file the app can download.

        Two review bugs live here (UI review 5.4):

        * **SIZE is bytes only.** It used to append ``· dist\\gg`` (the folder
          tail), which painted over the PURPOSE column — a cell must not paint
          over its neighbour. Where the file lives and why a copy was rejected
          now travel in ``note``, which the row renders on its own line.
        * **The verb comes from here, not from QML.** The cache row had
          ``action: "tm"`` with no branch in the view, so it fell through to
          "Download" — you do not download a cache the app builds. Every row now
          carries ``actionLabel`` / ``actionEnabled`` / ``actionHint`` decided in
          Python, where it is testable.
        """
        folder = _gguf_dir()
        rows: list[dict] = []

        def _entry(filename: str, purpose: str, action: str) -> dict:
            # Prefer a copy the app can actually use, so the table agrees with
            # the readiness tick. A broken copy that a good one shadows is
            # reported alongside it rather than as the row's state — otherwise
            # the row reads "Incomplete" for a model the run will happily use.
            path = ""
            shadowed = ""
            for directory in _model_search_dirs():
                candidate = os.path.join(directory, filename)
                if not os.path.isfile(candidate):
                    continue
                if gguf_check.is_usable_gguf(candidate):
                    path = candidate
                    break
                shadowed = shadowed or candidate
            if not path:
                path, shadowed = shadowed, ""
            present = bool(path)
            size = "missing"
            note = ""
            if present:
                try:
                    size = _format_bytes(os.path.getsize(path))
                except OSError:
                    size = "\u2014"
            if not present:
                state, tone = "Missing", "warn"
                action_label, action_enabled = "Download", True
                action_hint = ""
            else:
                ok, reason = gguf_check.inspect_gguf(path)
                if ok:
                    state, tone = "Verified", "ok"
                    action_label, action_enabled = "Re-download", True
                    action_hint = ""
                    if os.path.dirname(path) != folder:
                        # Say *where*: "Verified" with an empty models folder
                        # otherwise reads like a bug. This is the note, not the
                        # size, so it cannot collide with the next column.
                        note = "found in " + os.path.dirname(path)
                    if shadowed:
                        note = (note + " \u00b7 " if note else "") \
                            + "a broken copy is also present"
                else:
                    # A file that exists but cannot be parsed is not "present":
                    # say so, so the user can act on it.
                    state, tone = "Incomplete", "warn"
                    action_label, action_enabled = "Repair", True
                    action_hint = ""
                    note = reason
            return {
                "file": filename,
                "size": size,
                "note": note,
                "purpose": purpose,
                "state": state,
                "tone": tone,
                "action": action,
                "actionLabel": action_label,
                "actionEnabled": action_enabled,
                "actionHint": action_hint,
            }

        rows.append(_entry(_LOCAL_MODEL, "Translation", "local"))
        for name, _url in _MODEL_URLS:
            rows.append(_entry(name, "VAD" if "vad" in name else "ASR", "asr"))

        tm_path = self._translation_memory_db or os.path.join(
            _base_dir(), "cache", "translation_memory.sqlite3"
        )
        tm_present = os.path.isfile(tm_path) and os.path.getsize(tm_path) > 0
        tm_size = "\u2014"
        if tm_present:
            try:
                tm_size = _format_bytes(os.path.getsize(tm_path))
            except OSError:
                tm_size = "\u2014"
        rows.append({
            "file": os.path.basename(tm_path),
            "size": tm_size if tm_present else "not created",
            "note": "" if tm_present else "built from your own runs, not downloaded",
            "purpose": "Cache",
            "state": "Healthy" if tm_present else "Not created",
            "tone": "ok" if tm_present else "mute",
            "action": "tm",
            # You do not download a local cache the app builds. When it exists
            # the only sensible verb is Purge; before that the honest answer is
            # "it gets built on the first run", not a disabled Download button.
            "actionLabel": "Purge" if tm_present else "Build",
            "actionEnabled": tm_present,
            "actionHint": "" if tm_present
                else "The cache is created automatically on the first run.",
        })
        return rows

    @Slot(str)
    def runModelRowAction(self, action: str) -> None:
        """Dispatch a Models & storage row button from its ``action`` id."""
        if action == "asr":
            self.downloadAsrModels()
        elif action == "local":
            self.downloadLocalModel()
        elif action == "tm":
            self.purgeTranslationMemory()

    @Slot()
    def openModelsFolder(self) -> None:
        folder = _gguf_dir()
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            self._set_status("Could not open the models folder.")

    @Slot()
    def purgeTranslationMemory(self) -> None:
        """Delete the translation-memory database (Settings > Models & storage)."""
        candidates = [
            path for path in (
                self._translation_memory_db,
                os.path.join(_base_dir(), "cache", "translation_memory.sqlite3"),
            ) if path
        ]
        removed = 0
        for path in candidates:
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    removed += 1
            except OSError as exc:
                self.logger.warning("could not purge %s: %s", path, exc)
        self._set_status(
            "Translation memory purged." if removed
            else "No translation-memory database to purge."
        )
        self.formChanged.emit()

    # --- Environment / about ---------------------------------------------
    _APP_VERSION = "1.0.0"

    @Property(str, constant=True)
    def appVersion(self) -> str:
        return self._APP_VERSION

    @Property("QVariantList", constant=True)
    def environmentRows(self) -> list:
        """Raw internals. Rendered **only** through `Copy diagnostics`."""
        return [
            {"k": "App version", "v": self._APP_VERSION, "mono": True},
            {"k": "Frozen build", "v": "yes" if getattr(sys, "frozen", False) else "no", "mono": True},
            {"k": "Python", "v": platform.python_version(), "mono": True},
            {"k": "Qt", "v": qVersion() or "\u2014", "mono": True},
            {"k": "Working folder", "v": _base_dir(), "mono": True},
            {"k": "Models folder", "v": _gguf_dir(), "mono": True},
            {"k": "Result JSON", "v": _result_json_path(), "mono": True},
            {"k": "Settings store", "v": self._settings.fileName() or "QSettings", "mono": True},
        ]

    @Property(str, constant=True)
    def environmentSummary(self) -> str:
        """One-line, jargon-free replacement for the raw paths (UI review 5.6).

        A user hunting a setting does not need the install path, the registry
        key, or the Python version. They need to know their settings are safe
        and where their files go.
        """
        return ("Settings saved locally \u00b7 models live in your app folder \u00b7 "
                "offline mode makes no network calls")

    @Slot()
    def openDebugLog(self) -> None:
        path = os.path.join(_base_dir(), "debug.log")
        if not os.path.isfile(path):
            self._set_status("No debug.log has been written yet.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self._set_status("Could not open debug.log.")

    @Slot()
    def clearStoredSettings(self) -> None:
        """Reset every persisted preference to its default."""
        self._settings.clear()
        self._settings.sync()
        self._set_status("Stored settings cleared. Restart the app to see the defaults.")
