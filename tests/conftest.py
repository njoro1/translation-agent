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
