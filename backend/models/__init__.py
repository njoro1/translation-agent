"""Data models for the GUI backend.

``run_config`` is plain Python (no Qt), so it can be imported without
pulling in PySide6. ``results`` needs Qt and is therefore imported lazily.
"""

def __getattr__(name: str):  # PEP 562
    if name == "RunConfig":
        from .run_config import RunConfig

        return RunConfig
    if name in {"CueResultModel", "CueFilterProxyModel", "QualityIssuesModel"}:
        from . import results

        return getattr(results, name)
    raise AttributeError(f"module 'backend.models' has no attribute {name!r}")


__all__ = [
    "RunConfig",
    "CueResultModel",
    "CueFilterProxyModel",
    "QualityIssuesModel",
]
