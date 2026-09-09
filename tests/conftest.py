"""Shared pytest fixtures for the GUI/UX tests.

A single offscreen QGuiApplication is created for the whole session (PySide6
only allows one Q*Application per process), and a fresh AppBridge is provided
to the bridge/QML tests that need a live context object.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QGuiApplication

from backend.bridge import AppBridge


@pytest.fixture(scope="session", autouse=True)
def gui_app():
    if QGuiApplication.instance() is None:
        app = QGuiApplication([])
    else:
        app = QGuiApplication.instance()
    yield app


@pytest.fixture()
def app_bridge():
    bridge = AppBridge()
    yield bridge
