"""Shared pytest fixtures for the GUI/UX tests.

A single offscreen QGuiApplication is created for the whole session (PySide6
only allows one Q*Application per process), and a fresh AppBridge is provided
to the bridge/QML tests that need a live context object.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Must match main.py: the custom controls replace `background` / `contentItem`,
# which the native Windows style refuses (and then silently ignores them).
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from backend.bridge import AppBridge

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"


@pytest.fixture(scope="session", autouse=True)
def gui_app():
    if QGuiApplication.instance() is None:
        app = QGuiApplication([])
    else:
        app = QGuiApplication.instance()
    yield app


@pytest.fixture(scope="session")
def qml_main(gui_app):
    """``Main.qml`` loaded exactly **once** for the whole test session.

    Creating a second ``QQmlApplicationEngine`` and loading ``Main.qml`` again
    intermittently crashes the process (access violation inside
    ``engine.load()``): ``deleteLater()`` on an engine is only processed while
    an event loop runs, and offscreen pytest never spins one, so a "deleted"
    engine can still be torn down while the next one is starting up.

    Every QML test therefore shares this one instance.
    """
    bridge = AppBridge()
    engine = QQmlApplicationEngine()
    warnings: list[str] = []
    engine.warnings.connect(lambda errs: warnings.extend(e.toString() for e in errs))
    engine.addImportPath(str(QML_DIR))
    engine.rootContext().setContextProperty("appBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("Main.qml failed to load:\n" + "\n".join(warnings))

    yield SimpleNamespace(
        bridge=bridge,
        root=engine.rootObjects()[0],
        # Snapshot taken right after loading, so tests that run later and
        # mutate the bridge do not change what the load-time checks see.
        load_warnings=list(warnings),
        warnings=warnings,
    )
    engine.deleteLater()


@pytest.fixture()
def app_bridge():
    bridge = AppBridge()
    yield bridge


@pytest.fixture()
def qml_shown(qml_main, monkeypatch):
    """`qml_main` with the window actually shown, so layout geometry is real.

    Offscreen Qt never polishes an invisible window: every `height` reads 0 and
    every `visible` reads False for a child of a non-current page. Tests about
    layout (constant panel height, shared header baseline) and about category
    gating therefore need the window shown and an event loop turn or two.

    `_persist_fields` is stubbed out for the duration. Showing the window lets
    the 400 ms autosave debounce actually fire during `processEvents()`, and a
    test must never rewrite the developer's real `QSettings`.
    """
    monkeypatch.setattr(
        qml_main.bridge, "_persist_fields", lambda: None, raising=False
    )
    qml_main.root.setProperty("width", 1400)
    qml_main.root.setProperty("height", 900)
    qml_main.root.setProperty("visible", True)
    pump_events()
    yield qml_main


def pump_events(turns: int = 4) -> None:
    """Run the event loop just long enough for bindings and layouts to settle."""
    for _ in range(turns):
        QGuiApplication.processEvents()


@pytest.fixture()
def pump():
    """Callable form of :func:`pump_events`, for tests that need their own turn."""
    return pump_events
