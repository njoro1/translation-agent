"""Backend package for the PySide6 + QML frontend.

Public API is re-exported lazily here so that lightweight modules
(``backend.models.run_config``) can be imported without pulling in PySide6.
Implementations live in:
- ``backend.bridge`` — the QObject bridge exposed to QML.
- ``backend.controllers.translation`` — the QRunnable worker.
- ``backend.models.run_config`` — the RunConfig dataclass.
"""

def __getattr__(name: str):  # PEP 562
    if name in {"AppBridge", "_base_dir", "setup_logging"}:
        from . import bridge

        return getattr(bridge, name)
    if name in {"TranslationWorker", "WorkerSignals"}:
        from .controllers import translation

        return getattr(translation, name)
    if name == "RunConfig":
        from .models.run_config import RunConfig

        return RunConfig
    raise AttributeError(f"module 'backend' has no attribute {name!r}")


__all__ = [
    "AppBridge",
    "TranslationWorker",
    "WorkerSignals",
    "RunConfig",
    "_base_dir",
    "setup_logging",
]
