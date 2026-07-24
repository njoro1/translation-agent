from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

import translate


_DONE_PATTERN = re.compile(r"^Wrote \d+ cues to (?P<path>.+)$")


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


class _SignalWriter:
    """File-like object that forwards writes to a callback."""

    def __init__(self, callback: Callable[[str], None]):
        self._callback = callback

    def write(self, text: str) -> None:
        if text:
            self._callback(text)

    def flush(self) -> None:  # noqa: D401 - no-op, matches the file interface
        pass


class WorkerSignals(QObject):
    logLine = Signal(str)
    finished = Signal(int)


@dataclass(slots=True)
class RunConfig:
    argv: list[str]
    env: dict[str, str]


class TranslationWorker(QRunnable):
    def __init__(self, config: RunConfig):
        super().__init__()
        self.config = config
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        rc = 1
        old_stdout, old_stderr = sys.stdout, sys.stderr
        old_env = {key: os.environ.get(key) for key in self.config.env}
        sys.stdout = sys.stderr = _SignalWriter(self.signals.logLine.emit)
        try:
            for key, value in self.config.env.items():
                if value:
                    os.environ[key] = value
                elif key in os.environ:
                    os.environ.pop(key)
            rc = translate.main(self.config.argv)
        except Exception as exc:  # noqa: BLE001 - surface unexpected worker failures
            self.signals.logLine.emit(f"[error] {exc}\n")
            rc = 1
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
            for key, previous in old_env.items():
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous
            self.signals.finished.emit(rc)


class AppBridge(QObject):
    formChanged = Signal()
    statusMessageChanged = Signal()
    logTextChanged = Signal()
    isRunningChanged = Signal()
    canOpenOutputFolderChanged = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.threadpool = QThreadPool()
        self.logger = logging.getLogger("translation_agent")

        self._mode = "youtube"
        self._backend = "cloud"
        self._url = ""
        self._file_path = ""
        self._out_path = ""
        self._batch = "40"
        self._api_key = ""
        self._base_url = ""
        self._model = ""
        self._host = "127.0.0.1"
        self._port = "8080"
        self._model_name = "Hy-MT2-1.8B"
        self._asr_language = "auto"
        self._asr_bin = ""
        self._asr_vad_bin = ""
        self._asr_model = ""
        self._asr_vad_model = ""
        self._status_message = "Ready."
        self._log_text = ""
        self._is_running = False
        self._resolved_out_path = ""
        self._current_worker: TranslationWorker | None = None

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
            return "40"
        value = int(raw)
        if value <= 0:
            raise ValueError("Batch size must be a positive integer.")
        return str(value)

    def _build_run_config(self) -> RunConfig:
        argv: list[str] = []
        env: dict[str, str] = {}

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
            if self._asr_language and self._asr_language != "auto":
                argv += ["--asr-lang", self._asr_language]
            for flag, value in [
                ("--asr-bin", self._asr_bin),
                ("--asr-vad-bin", self._asr_vad_bin),
                ("--asr-model", self._asr_model),
                ("--asr-vad-model", self._asr_vad_model),
            ]:
                value = value.strip()
                if value:
                    argv += [flag, value]

        out_path = self._out_path.strip()
        if out_path:
            argv += ["--out", out_path]

        argv += ["--batch", self._validate_batch()]

        if self._backend == "local":
            argv += [
                "--local",
                "--local-host",
                (self._host or "127.0.0.1").strip() or "127.0.0.1",
                "--local-port",
                (self._port or "8080").strip() or "8080",
                "--local-model-name",
                (self._model_name or "Hy-MT2-1.8B").strip() or "Hy-MT2-1.8B",
            ]
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
            self._set_status(str(exc))
            return

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
