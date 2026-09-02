"""Temporary harness: render the YouTube panel with simulated inspection data."""
import json
import os
import sys

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402  # noqa: registers the type so rootObjects() exposes grabWindow()

from backend.bridge import AppBridge  # noqa: E402
from main import _load_bundled_fonts  # noqa: E402

app = QGuiApplication(sys.argv)
_load_bundled_fonts()

engine = QQmlApplicationEngine()
warnings: list[str] = []
engine.warnings.connect(lambda msgs: warnings.extend(str(m) for m in msgs))

bridge = AppBridge()
engine.rootContext().setContextProperty("appBridge", bridge)
engine.load(QUrl.fromLocalFile(os.path.abspath("ui/qml/Main.qml")))
if not engine.rootObjects():
    print("FATAL: QML failed to load")
    for w in warnings:
        print("warn:", w)
    sys.exit(1)
window = engine.rootObjects()[0]
window.setHeight(1200)

bridge.pipelineMode = "youtube_cloud"
bridge.url = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


def opt(sel, size, ext, fps, merge):
    return {"format_selector": sel, "filesize": size, "ext": ext, "fps": fps,
            "label": "", "has_audio": True, "merge": merge}


info = {
    "title": "Big Buck Bunny 60fps 4K — Official Blender Foundation Short Film",
    "video_id": "aqz-KE-bpKQ",
    "codecs": ["av1", "vp9", "h264"],
    "resolutions": [2160, 1440, 1080, 720, 480],
    "matrix": {
        "av1": {
            2160: opt("merge-av1-2160", 0, "mkv", 0, True),
            1440: opt("1702+251", 1180 * 1024 * 1024, "webm", 60, False),
            1080: opt("683+251", 640 * 1024 * 1024, "webm", 60, False),
            720: opt("398+251", 420 * 1024 * 1024, "webm", 60, False),
        },
        "vp9": {
            2160: opt("merge-vp9-2160", 0, "mkv", 0, True),
            1080: opt("399+251", 700 * 1024 * 1024, "webm", 30, False),
            720: opt("397+251", 380 * 1024 * 1024, "webm", 30, False),
            480: opt("396+251", 190 * 1024 * 1024, "webm", 30, False),
        },
        "h264": {
            1080: opt("137+140", 580 * 1024 * 1024, "mp4", 30, False),
            720: opt("136+140", 310 * 1024 * 1024, "mp4", 30, False),
            480: opt("135+140", 150 * 1024 * 1024, "mp4", 30, False),
            360: opt("134+140", 95 * 1024 * 1024, "mp4", 30, False),
        },
    },
    "best": {"format_selector": "bv*+ba/b", "filesize": 0,
             "label": "Best available (any codec)", "merge": False},
    "codecs_available": {"av1": True, "vp9": True, "h264": True},
    "has_english_subtitle": True,
}
bridge._on_youtube_info("INFO:" + json.dumps(info))
print("rows:", len(bridge.youtubeFormatRows))


def snap() -> None:
    img = window.grabWindow()
    out = os.path.abspath("ui_shots/youtube_inspect.png")
    img.save(out)
    print("saved", out)
    bad = [w for w in warnings if "Theme is not defined" not in w]
    print("qml warnings:", len(bad))
    for w in bad[:8]:
        print("warn:", w)
    app.quit()


QTimer.singleShot(700, snap)
app.exec()
