from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import sys
import urllib.request

from PySide6.QtCore import QObject, Property, QRunnable, QSettings, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

import translate

from src import youtube_media
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


def resolve_local_model_path(gguf_dir: str) -> str:
    """Resolve the preferred local translation model path in `gguf_dir`.

    Preference order:
        1. gguf/Hy-MT2-1.8B-Q8_0.gguf
        2. Any single unambiguous Hy-MT2 GGUF in the directory.

    Returns the chosen path or an empty string if none is found.
    """
    import glob

    candidate = os.path.join(gguf_dir, _LOCAL_MODEL)
    if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
        return candidate

    # Any Hy-MT2 GGUF, preferring Q8_0 files.
    hy_mt2_files = glob.glob(os.path.join(gguf_dir, "Hy-MT2*.gguf"))
    if len(hy_mt2_files) == 1:
        return hy_mt2_files[0]
    if len(hy_mt2_files) > 1:
        q8_files = [f for f in hy_mt2_files if "q8" in os.path.basename(f).lower()]
        if q8_files:
            return sorted(q8_files)[0]
        return sorted(hy_mt2_files)[0]
    return ""


_DONE_PATTERN = re.compile(r"^Wrote \d+ cues to (?P<path>.+)$")

PIPELINE_MODE_YOUTUBE_CLOUD = "youtube_cloud"
PIPELINE_MODE_LOCAL_CLOUD = "local_cloud"
PIPELINE_MODE_OFFLINE = "offline"

CONTENT_PRESETS = ("auto", "drama", "anime", "music", "documentary", "variety", "lecture")
ASR_PREPROCESS_PROFILES = ("auto", "none", "basic", "loudnorm", "denoise")
CONTEXT_MODES = ("", "off", "light", "standard", "deep")

STATUS_READY = "ready"
STATUS_VALIDATING = "validating"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


class _WorkerSignal(QObject):
    progress = Signal(str)
    done = Signal(str)


def _gguf_dir() -> str:
    """Where to place downloaded GGUF models (next to the app and importable)."""
    base = _base_dir()
    path = os.path.join(base, "gguf")
    os.makedirs(path, exist_ok=True)
    return path


def _result_json_path() -> str:
    """Stable path for the CLI's --result-json output (GUI review data)."""
    base = _base_dir()
    cache = os.path.join(base, "cache")
    os.makedirs(cache, exist_ok=True)
    return os.path.join(cache, "last_result.json")


class _ModelDownloadWorker(QRunnable):
    """Streams GGUF model files into ./gguf, reporting progress per chunk."""

    def __init__(self, urls: tuple = _MODEL_URLS) -> None:
        super().__init__()
        self.signals = _WorkerSignal()
        self.downloaded: list[str] = []
        self.urls = urls

    @Slot()
    def run(self) -> None:
        dest_dir = _gguf_dir()
        try:
            for filename, url in self.urls:
                dest = os.path.join(dest_dir, filename)
                if os.path.exists(dest) and os.path.getsize(dest) > 0:
                    self.signals.progress.emit(f"[ok] already present: {filename}\n")
                    self.downloaded.append(dest)
                    continue
                self.signals.progress.emit(f"Downloading {filename}…\n")
                with urllib.request.urlopen(url) as resp, open(dest, "wb") as out:
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
                self.downloaded.append(dest)
                self.signals.progress.emit(f"[ok] saved: {dest}\n")
        except Exception as exc:  # noqa: BLE001
            self.signals.progress.emit(f"[error] download failed: {exc}\n")
        self.signals.done.emit("done")


class _YouTubeInfoWorker(QRunnable):
    """Inspects a YouTube URL for available formats/codecs off the UI thread."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url
        self.signals = _WorkerSignal()

    @Slot()
    def run(self) -> None:
        try:
            info = youtube_media.inspect_video(self.url)
            self.signals.done.emit("INFO:" + json.dumps(info))
        except Exception as exc:  # noqa: BLE001
            self.signals.done.emit("INFOERROR:" + str(exc))


class _YouTubeDownloadWorker(QRunnable):
    """Downloads a YouTube video or English subtitle off the UI thread."""

    def __init__(self, mode: str, url: str, format_selector: str, out_template: str) -> None:
        super().__init__()
        self.mode = mode  # "video" or "subtitle"
        self.url = url
        self.format_selector = format_selector
        self.out_template = out_template
        self.signals = _WorkerSignal()

    @Slot()
    def run(self) -> None:
        try:
            if self.mode == "video":
                path = youtube_media.download_video(
                    self.url, self.format_selector, self.out_template,
                    progress_cb=lambda line: self.signals.progress.emit(line + "\n"),
                )
            else:
                path = youtube_media.download_subtitle(
                    self.url, "en", self.out_template,
                    progress_cb=lambda line: self.signals.progress.emit(line + "\n"),
                )
            self.signals.done.emit(f"YTDONE:{self.mode}:{path}")
        except Exception as exc:  # noqa: BLE001
            self.signals.done.emit(f"YTERROR:{self.mode}:{exc}")


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
    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
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

        self._pipeline_mode = PIPELINE_MODE_YOUTUBE_CLOUD
        self._mode = "youtube"
        self._backend = "cloud"
        self._url = ""
        self._file_path = ""
        self._source_lang = ""
        self._out_path = ""
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
        self._youtube_downloading = False
        self._youtube_download_status = ""
        self._youtube_downloaded_video = ""
        self._youtube_downloaded_subtitle = ""

        self._win_x = 60
        self._win_y = 60
        self._win_w = 1280
        self._win_h = 840

        self.cue_model = CueResultModel(self)
        self.cue_proxy = CueFilterProxyModel(self)
        self.cue_proxy.setSourceModel(self.cue_model)
        self.quality_issues_model = QualityIssuesModel(self)

        self._load_persisted()

    _BOOL_FIELDS = {
        "_asr_no_tags",
        "_asr_keep_tags",
        "_local_mlock",
        "_strict_quality",
        "_context_summary",
    }

    _INT_FIELDS = {
        "_win_x",
        "_win_y",
        "_win_w",
        "_win_h",
    }

    def _load_persisted(self) -> None:
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
        # Keep source mode and backend in lock-step with the saved pipeline flow.
        # A previous build used different IDs; migrate saved values before
        # deriving the source/backend fields that the run builder consumes.
        legacy_modes = {
            "youtube": PIPELINE_MODE_YOUTUBE_CLOUD,
            "local_hybrid": PIPELINE_MODE_LOCAL_CLOUD,
            "local_offline": PIPELINE_MODE_OFFLINE,
        }
        self._pipeline_mode = legacy_modes.get(
            self._pipeline_mode, self._pipeline_mode
        )
        self._apply_pipeline_mode(self._pipeline_mode)
        # Recompute every derived binding (e.g. `localModelReady`, `asrModelReady`,
        # `backend`) against the just-loaded persisted state. Without this a model
        # the user previously selected would not be reflected until some unrelated
        # field changed, wrongly showing "Download model & Run" at launch.
        self.formChanged.emit()

    def _persist_fields(self) -> None:
        for attr, key, default in self._PERSISTED:
            self._settings.setValue(key, getattr(self, attr, default))
        self._settings.sync()

    def _set_field(self, attr: str, value) -> None:
        if getattr(self, attr) != value:
            setattr(self, attr, value)
            self.formChanged.emit()

    def _append_log(self, text: str) -> None:
        self._log_text += text
        self.logTextChanged.emit()

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            level = logging.ERROR if line.startswith("[error]") else logging.INFO
            self.logger.log(level, line)
            match = _DONE_PATTERN.match(line)
            if match:
                path = match.group("path").strip()
                if path:
                    self._resolved_out_path = os.path.abspath(path)
                    self.canOpenOutputFolderChanged.emit()

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

        self._progress_stage = stage
        self._progress_done = done
        self._progress_total = total

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
                if value:
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
            if not local_model:
                # Self-contained desktop app: auto-pick a bundled translation
                # model if one is present; otherwise fail fast with clear
                # guidance instead of silently hanging against an empty port.
                candidate = resolve_local_model_path(_gguf_dir())
                if candidate and os.path.exists(candidate):
                    local_model = candidate
            if local_model:
                argv += ["--local-model", local_model]
            else:
                raise ValueError(
                    "No local translation model found. Download it via "
                    "Settings → Download models (fetches Hy-MT2-1.8B-Q8_0.gguf) "
                    "or Browse to select a GGUF file."
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
            self.formChanged.emit()

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
            # Drop any stale inspection results for the previous URL.
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
            self.formChanged.emit()
            self.youtubeInfoChanged.emit()
            self.youtubeDownloadChanged.emit()

    @Property(str, notify=formChanged)
    def filePath(self) -> str:
        return self._file_path

    @filePath.setter
    def filePath(self, value: str) -> None:
        self._set_field("_file_path", value)

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
        self._set_field("_out_path", value)

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
        """True when a usable translation GGUF is available.

        A model counts as ready if either:
          1. the user has selected/persisted a valid path (`_local_model` that
             exists on disk — whatever they browsed to, wherever it lives), or
          2. an auto-detected Hy-MT2 GGUF is present in the app's gguf folder.
        """
        try:
            selected = (self._local_model or "").strip()
            if selected and os.path.exists(selected):
                return True
            path = resolve_local_model_path(_gguf_dir())
            return bool(path) and os.path.exists(path)
        except Exception:  # noqa: BLE001
            return False

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
            self.formChanged.emit()

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
        """True when the SenseVoice ASR GGUF is available."""
        try:
            gguf = _gguf_dir()
            default_sensevoice = os.path.join(gguf, "sensevoice-small-q8.gguf")
            selected = (self._asr_model or "").strip()
            if selected and os.path.exists(selected):
                return True
            return os.path.exists(default_sensevoice)
        except Exception:  # noqa: BLE001
            return False

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
            self.formChanged.emit()

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
            self.formChanged.emit()

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
            self.formChanged.emit()

    @Property(bool, notify=formChanged)
    def strictQuality(self) -> bool:
        return self._strict_quality

    @strictQuality.setter
    def strictQuality(self, value: bool) -> None:
        value = bool(value)
        if self._strict_quality != value:
            self._strict_quality = value
            self.formChanged.emit()

    @Property(str, notify=formChanged)
    def outputFormat(self) -> str:
        return self._output_format

    @outputFormat.setter
    def outputFormat(self, value: str) -> None:
        value = (value or "srt").strip().lower()
        if value not in ("srt", "ass"):
            value = "srt"
        self._set_field("_output_format", value)

    @Property(str, notify=statusMessageChanged)
    def statusMessage(self) -> str:
        return self._status_message

    @Property(str, notify=statusStateChanged)
    def statusState(self) -> str:
        return self._status_state

    @Property(str, notify=logTextChanged)
    def logText(self) -> str:
        return self._log_text

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

    @Property(QObject, constant=True)
    def cueModel(self) -> CueResultModel:
        return self.cue_model

    # --- YouTube media (video download + codec inspection) --------------------

    def _youtube_out_dir(self) -> str:
        """Where downloaded video/subtitle files land.

        Defaults to the directory of the user's output path (if set),
        otherwise the app's base directory.
        """
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
        """Resolution choices: available heights plus "best"."""
        items = [{"value": h, "label": f"{h}p"} for h in self._youtube_resolutions]
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
        if self._youtube_selected_codec != value:
            self._youtube_selected_codec = value
            self.youtubeInfoChanged.emit()

    @Property(object, notify=youtubeInfoChanged)
    def youtubeSelectedResolution(self):
        return self._youtube_selected_resolution

    @youtubeSelectedResolution.setter
    def youtubeSelectedResolution(self, value) -> None:
        if self._youtube_selected_resolution != value:
            self._youtube_selected_resolution = value
            self.youtubeInfoChanged.emit()

    @Property(dict, notify=youtubeInfoChanged)
    def youtubeSelectedOption(self) -> dict:
        if not self._youtube_matrix and not self._youtube_best:
            return {}
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
    def youtubeDownloading(self) -> bool:
        return self._youtube_downloading

    @Property(str, notify=youtubeDownloadChanged)
    def youtubeDownloadStatus(self) -> str:
        return self._youtube_download_status

    @Property(str, notify=youtubeDownloadChanged)
    def youtubeDownloadedVideo(self) -> str:
        return self._youtube_downloaded_video

    @Property(str, notify=youtubeDownloadChanged)
    def youtubeDownloadedSubtitle(self) -> str:
        return self._youtube_downloaded_subtitle

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

        worker = _YouTubeInfoWorker(url)
        worker.signals.done.connect(self._on_youtube_info)
        self.threadpool.start(worker)

    def _on_youtube_info(self, payload: str) -> None:
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
        opt = self.youtubeSelectedOption
        if opt and opt.get("format_selector"):
            return opt["format_selector"]
        return "bv*+ba/b"

    @Slot()
    def downloadYouTubeVideo(self) -> None:
        url = (self._url or "").strip()
        if not url:
            self._set_status("Enter a YouTube URL first.")
            return
        if self._youtube_downloading:
            return
        selector = self._selected_format_selector()
        template = self._youtube_out_template() + ".%(ext)s"
        self._youtube_downloading = True
        self._youtube_download_status = "Starting video download…\n"
        self._youtube_downloaded_video = ""
        self.youtubeDownloadChanged.emit()

        worker = _YouTubeDownloadWorker("video", url, selector, template)
        worker.signals.progress.connect(self._append_log)
        worker.signals.progress.connect(self._on_youtube_download_progress)
        worker.signals.done.connect(self._on_youtube_downloaded)
        self.threadpool.start(worker)

    @Slot()
    def downloadYouTubeSubtitle(self) -> None:
        url = (self._url or "").strip()
        if not url:
            self._set_status("Enter a YouTube URL first.")
            return
        if self._youtube_downloading:
            return
        template = self._youtube_out_template()
        self._youtube_downloading = True
        self._youtube_download_status = "Starting subtitle download…\n"
        self._youtube_downloaded_subtitle = ""
        self.youtubeDownloadChanged.emit()

        worker = _YouTubeDownloadWorker("subtitle", url, "", template)
        worker.signals.progress.connect(self._append_log)
        worker.signals.progress.connect(self._on_youtube_download_progress)
        worker.signals.done.connect(self._on_youtube_downloaded)
        self.threadpool.start(worker)

    def _on_youtube_download_progress(self, text: str) -> None:
        self._youtube_download_status += text
        self.youtubeDownloadChanged.emit()

    def _on_youtube_downloaded(self, payload: str) -> None:
        self._youtube_downloading = False
        if payload.startswith("YTERROR:"):
            # payload: YTERROR:<mode>:<message>
            _, mode, msg = payload.split(":", 2)
            self._youtube_download_status += f"[error] {msg}\n"
            self._set_status(f"YouTube {mode} download failed. See the log.")
            self.youtubeDownloadChanged.emit()
            return
        if not payload.startswith("YTDONE:"):
            self._youtube_download_status += "[error] Unexpected download result.\n"
            self.youtubeDownloadChanged.emit()
            return
        _, mode, path = payload.split(":", 2)
        if mode == "video":
            self._youtube_downloaded_video = path
        else:
            self._youtube_downloaded_subtitle = path
        self._youtube_download_status += f"[ok] saved: {path}\n"
        self._set_status(
            f"YouTube {mode} saved: {os.path.basename(path)}"
        )
        self.youtubeDownloadChanged.emit()

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
        if not self._asr_model.strip():
            candidate = os.path.join(gguf, "sensevoice-small-q8.gguf")
            if candidate in downloaded or os.path.exists(candidate):
                self._set_field("_asr_model", candidate)
        if not self._asr_vad_model.strip():
            candidate = os.path.join(gguf, "fsmn-vad.gguf")
            if candidate in downloaded or os.path.exists(candidate):
                self._set_field("_asr_vad_model", candidate)
        self._persist_fields()
        self.modelDownloadChanged.emit()
        self._set_status("ASR model ready.")

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
        if not self._local_model.strip():
            candidate = resolve_local_model_path(_gguf_dir())
            if candidate and (
                candidate in downloaded or os.path.exists(candidate)
            ):
                self._set_field("_local_model", candidate)
                print(
                    f"[local] Using Hy-MT2 model: {os.path.relpath(candidate)}",
                    flush=True,
                )
        self._persist_fields()
        self.modelDownloadChanged.emit()
        self._set_status("Local translation model ready.")
        self.localModelDownloadPendingChanged.emit()

        # If a run was waiting on this download, kick it off now.
        if was_pending:
            self.runTranslation()

    @Slot()
    def clearLog(self) -> None:
        self._log_text = ""
        self.logTextChanged.emit()
        self._set_status("Ready.")

    @Slot()
    def copyLog(self) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(self._log_text)
        self._set_status("Log copied to clipboard.")

    @Slot(result=str)
    def copySummaryText(self) -> str:
        """Human-readable summary of the last result for bug reports."""
        q = self._quality_summary
        lines = [
            f"Output: {self._resolved_out_path or '-'}",
            f"Cues: {q.get('cue_count', 0)}",
            f"Untranslated: {self.qualityUntranslated}",
            f"Errors: {self.qualityErrors}  Warnings: {self.qualityWarnings}",
            f"Avg CPS: {self.qualityAverageCps}  Max line chars: {self.qualityMaxLineChars}",
            f"Strict quality: {self._result_strict_state}",
        ]
        text = "\n".join(lines)
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(text)
        return text

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
            # Auto-trigger model download when the only blocker is a missing
            # local translation GGUF, so the user does not have to configure
            # anything manually.
            if (
                self._backend == "local"
                and "No local translation model found" in msg
                and not self._local_model_downloading
                and not self._local_model_download_pending
            ):
                self._local_model_download_pending = True
                self.localModelDownloadPendingChanged.emit()
                self._set_status("Downloading local translation model…")
                self._set_status_state(STATUS_RUNNING)
                worker = _ModelDownloadWorker(_LOCAL_MODEL_URLS)
                worker.signals.progress.connect(self._append_log)
                worker.signals.progress.connect(self._set_local_model_download_status_text)
                worker.signals.done.connect(self._on_local_model_downloaded)
                self.threadpool.start(worker)
                return
            self._set_status(msg)
            self._set_status_state(STATUS_FAILED)
            return

        self._persist_fields()
        self._resolved_out_path = ""
        self.canOpenOutputFolderChanged.emit()
        self._reset_result_state()
        self._progress_stage = ""
        self._progress_done = 0
        self._progress_total = 0
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
        self._set_running(False)
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
        else:
            self._set_status_state(STATUS_FAILED)
            self._set_status(f"Finished with errors (exit {rc}). See the log.")

    def _reset_result_state(self) -> None:
        self._result_ready = False
        self._result_strict_state = "pass" if self._strict_quality else "off"
        self._quality_summary = {}
        self.cue_model.clear()
        self.quality_issues_model.clear()
        self.resultReadyChanged.emit()

    def _load_result_json(self) -> bool:
        """Load cache/last_result.json into the Review/Quality models."""
        path = _result_json_path()
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
        self.cue_model.load(cues)
        self.quality_issues_model.load_from_report(quality)
        if self._strict_quality:
            self._result_strict_state = "pass"
        self._result_ready = True
        self.resultReadyChanged.emit()
        return True

    @Slot(str)
    def saveWindowState(self, geometry: str) -> None:
        """Persist window geometry: 'x,y,width,height'."""
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
