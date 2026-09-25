"""Dump geometry of each page's top-level layout children."""
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
from PySide6.QtQuick import QQuickWindow  # noqa: E402
import shiboken6  # noqa: E402

from backend.bridge import AppBridge  # noqa: E402

app = QGuiApplication(sys.argv)
app.setApplicationName("Translation Agent")
app.setOrganizationName("Translation Agent")
bridge = AppBridge()
bridge._settings.clear()
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("appBridge", bridge)
engine.load(QUrl.fromLocalFile(os.path.abspath("ui/qml/Main.qml")))
window = shiboken6.wrapInstance(
    shiboken6.getCppPointer(engine.rootObjects()[0])[0], QQuickWindow
)
print("window:", window.width(), "x", window.height())
root_item = window.contentItem()

NAMES = ["RunPage", "ReviewPage", "QualityPage", "LogPage", "SettingsPage"]
step = {"i": -1}


def dump(item, depth=0, max_depth=1):
    if depth > max_depth:
        return
    cls = item.metaObject().className()
    print("  " * depth + f"{cls}: x={item.x():.0f} y={item.y():.0f} "
          f"w={item.width():.0f} h={item.height():.0f} vis={item.isVisible()}")
    for ch in item.childItems():
        dump(ch, depth + 1, max_depth)


def find_by_class(item, want):
    hits = []
    if item.metaObject().className().startswith(want):
        hits.append(item)
    for ch in item.childItems():
        hits += find_by_class(ch, want)
    return hits


def tick():
    step["i"] += 1
    if step["i"] >= 5:
        app.quit()
        return
    window.setProperty("currentPage", step["i"])

    def report():
        print(f"\n=== {NAMES[step['i']]} ===")
        hits = find_by_class(root_item, NAMES[step["i"]])
        if not hits:
            print("  page not found!")
        for h in hits[:1]:
            dump(h, 0, 5)
        QTimer.singleShot(300, tick)

    QTimer.singleShot(400, report)


QTimer.singleShot(700, tick)
app.exec()
