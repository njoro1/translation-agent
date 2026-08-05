#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from backend.bridge import AppBridge, _base_dir, setup_logging
from src.local_server import shutdown_servers


def _resource_path(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", _base_dir())
    return os.path.join(base, *parts)


def _resolve_qml_dirs(frozen_base: str | None):
    """Return (qml_dir, plugins_dir) for the PySide6 installation."""
    if frozen_base:
        candidate_qml = os.path.join(frozen_base, "PySide6", "qml")
        candidate_plugins = os.path.join(frozen_base, "PySide6", "plugins")
        if os.path.isdir(candidate_qml):
            return candidate_qml, candidate_plugins
        # Fallback to ui/qml if PySide6/qml is not found
        candidate_qml = os.path.join(frozen_base, "ui", "qml")
        if os.path.isdir(candidate_qml):
            return candidate_qml, candidate_plugins
        return candidate_qml, candidate_plugins
    try:
        import PySide6
        _pyside6 = os.path.dirname(PySide6.__file__)
    except Exception:
        _pyside6 = ""
    qml_dir = os.path.join(_pyside6, "qml") if _pyside6 else ""
    plugins_dir = os.path.join(_pyside6, "plugins") if _pyside6 else ""
    return qml_dir, plugins_dir


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

    _frozen_base = getattr(sys, "_MEIPASS", None)
    qml_dir, plugins_dir = _resolve_qml_dirs(_frozen_base)

    if os.path.isdir(plugins_dir) and "QT_PLUGIN_PATH" not in os.environ:
        os.environ["QT_PLUGIN_PATH"] = plugins_dir
        logger.info("Set QT_PLUGIN_PATH=%s", plugins_dir)
    elif not os.path.isdir(plugins_dir):
        logger.warning("Qt plugins path not found: %s", plugins_dir)

    app = QGuiApplication(sys.argv)
    app.setApplicationName("Translation Agent")
    app.setOrganizationName("Translation Agent")
    # Stop any bundled llama-server the app started when the user quits.
    app.aboutToQuit.connect(shutdown_servers)

    engine = QQmlApplicationEngine()

    if os.path.isdir(qml_dir):
        engine.addImportPath(qml_dir)
        logger.info("Added QML import path: %s", qml_dir)
    else:
        logger.warning("QML import path not found: %s", qml_dir)

    qml_warnings: list[str] = []
    engine.warnings.connect(lambda msgs: qml_warnings.extend(str(m) for m in msgs))

    bridge = AppBridge()
    engine.rootContext().setContextProperty("appBridge", bridge)

    qml_file = _resource_path("ui", "qml", "Main.qml")
    logger.info("Loading QML: %s", os.path.abspath(qml_file))
    engine.load(QUrl.fromLocalFile(os.path.abspath(qml_file)))

    if not engine.rootObjects():
        logger.error("QML failed to load: %s", qml_file)
        for w in qml_warnings:
            logger.error("QML warning: %s", w)
        if _frozen_base:
            for dirpath, dirnames, filenames in os.walk(_frozen_base):
                rel = os.path.relpath(dirpath, _frozen_base)
                if rel.startswith("PySide6") and rel.count(os.sep) <= 2:
                    logger.debug("  %s/ -> %s", rel, dirnames[:10])
        return -1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
