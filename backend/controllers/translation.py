"""Worker that runs the translation CLI pipeline off the UI thread.

The bridge resolves a RunConfig from the form state and hands it to
TranslationWorker, which patches stdout/stderr so the CLI's own prints
stream back into the UI as log lines.
"""
from __future__ import annotations

import os
import sys
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

import translate

from ..models.run_config import RunConfig


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
            # translate.main runs in-process, so the bridge's cancelRun() sets
            # a module-level flag (translate.request_cancel) that the pipeline
            # polls between batches/windows; no IPC needed. A cancelled run
            # exits with code 2 (translate._run_pipeline returns it), which
            # the bridge maps to a distinct "cancelled" state.
            try:
                rc = translate.main(self.config.argv)
            except Exception as exc:  # noqa: BLE001 - surface unexpected worker failures
                from src.translate import TranslationCancelled

                if isinstance(exc, TranslationCancelled):
                    rc = 2
                else:
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
