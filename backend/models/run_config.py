"""The argv + env one translation run is started with.

Plain Python on purpose: this module is imported by the worker thread and by
``backend.__init__`` without pulling in PySide6.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RunConfig:
    """Resolved argv + env for a single translation run.

    ``argv`` is what ``translate.main()`` is called with; ``env`` holds the
    environment overrides the run needs (the API key, the base URL, the model
    name, …). An empty value in ``env`` means *unset it* rather than *set it
    to the empty string* — that is how the offline mode drops the cloud
    credentials.
    """

    argv: list[str]
    env: dict[str, str]
