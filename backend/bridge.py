from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
import urllib.request

from PySide6.QtCore import QObject, Property, QRunnable, QSettings, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

import translate

from .controllers.translation import TranslationWorker
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


class _WorkerSignal(QObject):
    progress = Signal(str)
    done = Signal(str)


def _gguf_dir() -> str:
    """Where to place downloaded GGUF models (next to the app and importable)."""
    base = _base_dir()
    path = os.path.join(base, "gguf")
    os.makedirs(path, exist_ok=True)
    return path


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
    logTextChanged = Signal()
    isRunningChanged = Signal()
    canOpenOutputFolderChanged = Signal()
    modelDownloadChanged = Signal()
    pipelineModeChanged = Signal()
    localModelDownloadPendingChanged = Signal()

    # Fields persisted across runs, as (attr, QSettings key, default). Bumped
    # whenever a new stored preference is introduced; secrets like the API key
    # are intentionally not persisted.
    _PERSISTED = (
        ("_pipeline_mode", "pipeline/mode", "youtube"),
        ("_asr_language", "asr/language", "auto"),
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
        ("_cloud_rescue_enabled", "rescue/enabled", False),
        ("_cloud_rescue_model", "rescue/model", ""),
        ("_cloud_rescue_batch", "rescue/batch", "10"),
        ("_strict_quality", "quality/strict", False),
        ("_output_format", "output/format", "srt"),
    )

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.threadpool = QThreadPool()
        self.logger = logging.getLogger("translation_agent")
        self._settings = QSettings()

        self._pipeline_mode = "youtube"
        self._mode = "youtube"
        self._backend = "cloud"
        self._url = ""
        self._file_path = ""
        self._out_path = ""
        self._batch = "8"
        self._api_key = ""
        self._base_url = ""
        self._model = ""
        self._host = "127.0.0.1"
        self._port = "8080"
        self._model_name = "Hy-MT2-1.8B-Q8_0"
        self._local_model = ""
        self._asr_language = "auto"
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
        self._cloud_rescue_enabled = False
        self._cloud_rescue_model = ""
        self._cloud_rescue_batch = "10"
        self._strict_quality = False
        self._output_format = "srt"
        self._status_message = "Ready."
        self._log_text = ""
        self._is_running = False
        self._resolved_out_path = ""
        self._current_worker: TranslationWorker | None = None
        self._model_download_status = ""
        self._model_downloading = False
        self._local_model_download_status = ""
        self._local_model_downloading = False
        self._local_model_download_pending = False

        self._load_persisted()

    _BOOL_FIELDS = {
        "_asr_no_tags",
        "_asr_keep_tags",
        "_local_mlock",
        "_cloud_rescue_enabled",
        "_strict_quality",
    }

    def _load_persisted(self) -> None:
        for attr, key, default in self._PERSISTED:
            value = self._settings.value(key, default)
            if attr in self._BOOL_FIELDS:
                setattr(self, attr, str(value).lower() in ("1", "true", "yes"))
            elif isinstance(value, str):
                setattr(self, attr, value)
        # Keep source mode and backend in lock-step with the saved pipeline flow.
        # Without this, a persisted "local_offline"/"local_hybrid" would leave
        # _mode at "youtube" and _backend at "cloud", so the run would still ask
        # for a YouTube URL and the Settings page would show the cloud section.
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

    def _set_field(self, attr: str, value: str) -> None:
        value = value or ""
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

    def _set_status(self, text: str) -> None:
        if self._status_message != text:
            self._status_message = text
            self.statusMessageChanged.emit()

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

        # --- Translation consistency / quality flags ---
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

        if self._backend == "local":
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
            # Cloud rescue only makes sense with the local backend.
            if self._cloud_rescue_enabled:
                argv += ["--cloud-rescue"]
                rescue_model = self._cloud_rescue_model.strip()
                if rescue_model:
                    argv += ["--cloud-rescue-model", rescue_model]
                argv += ["--cloud-rescue-batch", str(int(self._cloud_rescue_batch or 10))]
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
        value = (value or "").strip().lower() or "youtube"
        if value not in ("youtube", "local_hybrid", "local_offline"):
            value = "youtube"
        if self._pipeline_mode != value:
            self._pipeline_mode = value
            self._apply_pipeline_mode(value)
            self.pipelineModeChanged.emit()
            self.formChanged.emit()

    def _apply_pipeline_mode(self, mode: str) -> None:
        if mode == "youtube":
            self._mode = "youtube"
            self._backend = "cloud"
            self._cloud_rescue_enabled = False
        elif mode == "local_hybrid":
            self._mode = "file"
            self._backend = "local"
            self._cloud_rescue_enabled = True
        else:
            self._mode = "file"
            self._backend = "local"
            self._cloud_rescue_enabled = False

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
        self._set_field("_url", value)

    @Property(str, notify=formChanged)
    def filePath(self) -> str:
        return self._file_path

    @filePath.setter
    def filePath(self, value: str) -> None:
        self._set_field("_file_path", value)

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

        This keeps the UI (Dashboard "Run Translation" vs "Download model & Run",
        Settings warning) in sync with what the run would actually use.
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
    def asrLanguage(self) -> str:
        return self._asr_language

    @asrLanguage.setter
    def asrLanguage(self, value: str) -> None:
        self._set_field("_asr_language", value)

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
        """True when the SenseVoice + VAD ASR GGUFs are available.

        Mirrors how the run resolves them: the user-selected/persisted paths are
        honored first; otherwise the well-known filenames in the app's gguf folder
        (which the bundled binaries default to) are auto-detected.
        """
        try:
            gguf = _gguf_dir()
            def _present(path: str) -> bool:
                p = (path or "").strip()
                if p and os.path.exists(p):
                    return True
                candidate = os.path.join(gguf, os.path.basename(p)) if p else ""
                return bool(candidate) and os.path.exists(candidate)

            default_sensevoice = os.path.join(gguf, "sensevoice-small-q8.gguf")
            default_vad = os.path.join(gguf, "fsmn-vad.gguf")
            return _present(self._asr_model) or os.path.exists(default_sensevoice)
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
    def cloudRescueEnabled(self) -> bool:
        return self._cloud_rescue_enabled

    @cloudRescueEnabled.setter
    def cloudRescueEnabled(self, value: bool) -> None:
        value = bool(value)
        if self._cloud_rescue_enabled != value:
            self._cloud_rescue_enabled = value
            self.formChanged.emit()

    @Property(str, notify=formChanged)
    def cloudRescueModel(self) -> str:
        return self._cloud_rescue_model

    @cloudRescueModel.setter
    def cloudRescueModel(self, value: str) -> None:
        self._set_field("_cloud_rescue_model", value)

    @Property(str, notify=formChanged)
    def cloudRescueBatch(self) -> str:
        return self._cloud_rescue_batch

    @cloudRescueBatch.setter
    def cloudRescueBatch(self, value: str) -> None:
        self._set_field("_cloud_rescue_batch", value)

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

    @Property(str, notify=logTextChanged)
    def logText(self) -> str:
        return self._log_text

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

        # If a run was waiting on this download, kick it off now.
        if self._local_model_download_pending:
            self._local_model_download_pending = False
            try:
                config = self._build_run_config()
            except ValueError as exc:
                self._set_status(str(exc))
                return
            self._persist_fields()
            self._resolved_out_path = ""
            self.canOpenOutputFolderChanged.emit()
            self._set_running(True)
            self._set_status("Running…")
            worker2 = TranslationWorker(config)
            worker2.signals.logLine.connect(self._append_log)
            worker2.signals.finished.connect(self._on_finished)
            self._current_worker = worker2
            self.threadpool.start(worker2)

    @Slot()
    def clearLog(self) -> None:
        self._log_text = ""
        self.logTextChanged.emit()
        self._set_status("Ready.")

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
                self._set_status("Downloading local translation model…")
                worker = _ModelDownloadWorker(_LOCAL_MODEL_URLS)
                worker.signals.progress.connect(self._append_log)
                worker.signals.progress.connect(self._set_local_model_download_status_text)
                worker.signals.done.connect(self._on_local_model_downloaded)
                self.threadpool.start(worker)
                return
            self._set_status(msg)
            return

        self._persist_fields()
        self._resolved_out_path = ""
        self.canOpenOutputFolderChanged.emit()
        self._set_running(True)
        self._set_status("Running…")

        command_preview = f"$ python translate.py {' '.join(config.argv)}\n"
        self._append_log(command_preview)
        self.logger.info("run argv: %s", " ".join(config.argv))

        worker = TranslationWorker(config)
        worker.signals.logLine.connect(self._append_log)
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
            if self._resolved_out_path:
                self._set_status(f"Done. Saved to {self._resolved_out_path}")
            else:
                self._set_status("Done.")
        else:
            self._set_status(f"Finished with errors (exit {rc}). See the log.")
