"""Probe: load Main.qml offscreen, switch through every page, print all QML warnings."""
import os
import sys

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from backend.bridge import AppBridge  # noqa: E402

app = QGuiApplication(sys.argv)
app.setApplicationName("Translation Agent")
app.setOrganizationName("Translation Agent")
bridge = AppBridge()
bridge._settings.clear()

engine = QQmlApplicationEngine()
warnings = []
engine.warnings.connect(lambda msgs: warnings.extend(str(m) for m in msgs))
engine.rootContext().setContextProperty("appBridge", bridge)
engine.load(QUrl.fromLocalFile(os.path.abspath("ui/qml/Main.qml")))
if not engine.rootObjects():
    print("QML FAILED TO LOAD")
    for w in warnings:
        print("  ", w)
    sys.exit(1)
window = engine.rootObjects()[0]

seen = set()
step = {"i": -1}
NAMES = ["run", "review", "quality", "log", "settings"]


def tick():
    step["i"] += 1
    if step["i"] > 5:
        print("=== unique warnings ===")
        for w in sorted(seen):
            print(w)
        app.quit()
        return
    if step["i"] < 5:
        window.setProperty("currentPage", step["i"])
    for w in warnings:
        if w not in seen:
            seen.add(w)
            print(f"[{NAMES[min(step['i'], 4)]}] {w}", flush=True)
    QTimer.singleShot(600, tick)


QTimer.singleShot(700, tick)
app.exec()
