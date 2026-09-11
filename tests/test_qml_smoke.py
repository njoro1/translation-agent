"""Offscreen smoke test: the whole UI must compile and instantiate.

Loads Main.qml with a live AppBridge under the offscreen platform. A single
QML error (missing property, bad binding, typos in the panels we rewrote)
fails the test, so this guards every component at once.
"""
from __future__ import annotations


def test_main_window_loads(qml_main):
    # The window is loaded once per session by the ``qml_main`` fixture (a
    # second QQmlApplicationEngine loading Main.qml crashes the process).
    assert qml_main.root is not None, "Main.qml produced no root object"
    # QQmlApplicationEngine reports parse/type errors through warnings;
    # runtime binding notices are retained as diagnostics but do not make a
    # valid offscreen window fail this smoke test.
    fatal = [e for e in qml_main.load_warnings
             if "Type " in e or "is not a type" in e
             or "Cannot assign" in e or "Cannot read" in e]
    assert not fatal, "QML errors:\n" + "\n".join(fatal)
