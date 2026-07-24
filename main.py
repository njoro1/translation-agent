#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from backend.bridge import AppBridge, _base_dir, setup_logging


def _resource_path(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", _base_dir())
    return os.path.join(base, *parts)


def main() -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    logger = setup_logging(_base_dir())
    logger.info(
        "Starting Translation Agent QML UI | base_dir=%s | frozen=%s | python=%s",
        _base_dir(),
        getattr(sys, "frozen", False),
        sys.version.split()[0],
    )

    def _excepthook(exc_type, exc_value, traceback) -> None:
        logger.exception("Unhandled exception", exc_info=(exc_type, exc_value, traceback))

    sys.excepthook = _excepthook

    app = QGuiApplication(sys.argv)
    app.setApplicationName("Translation Agent")
    app.setOrganizationName("Translation Agent")

    engine = QQmlApplicationEngine()
    bridge = AppBridge()
    engine.rootContext().setContextProperty("appBridge", bridge)

    qml_file = _resource_path("ui", "qml", "Main.qml")
    engine.load(QUrl.fromLocalFile(os.path.abspath(qml_file)))

    if not engine.rootObjects():
        logger.error("QML failed to load: %s", qml_file)
        return -1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
