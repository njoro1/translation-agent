"""Screenshot the YouTube panel using the REAL inspection flow (network)."""
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
from PySide6.QtQuick import QQuickWindow  # noqa: E402

from backend.bridge import AppBridge  # noqa: E402
from main import _load_bundled_fonts  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
OUT = sys.argv[2] if len(sys.argv) > 2 else "ui_shots/youtube_real.png"

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
window.setHeight(1400)

bridge.pipelineMode = "youtube_cloud"
bridge.url = URL
bridge.fetchYouTubeInfo()
print("inspect requested, loading:", bridge.youtubeInfoLoading, flush=True)

ticks = {"n": 0}


def poll() -> None:
    ticks["n"] += 1
    if bridge.youtubeInfoLoading:
        if ticks["n"] > 240:  # ~120 s
            print("TIMEOUT waiting for inspection")
            app.quit()
        QTimer.singleShot(500, poll)
        return

    print("loading done. error:", repr(bridge.youtubeInfoError), flush=True)
    print("hasInfo:", bridge.youtubeHasInfo)
    print("rows:", len(bridge.youtubeFormatRows))
    print("codecs:", bridge.youtubeCodecs)
    print("resolutions:", bridge.youtubeResolutions)
    print("selectedCodec:", bridge.youtubeSelectedCodec,
          "selectedRes:", bridge.youtubeSelectedResolution)
    opt = bridge.youtubeSelectedOption
    print("selectedOption:", opt)
    print("hasSelectionFlag:", bool(opt and opt.get("format_selector")))
    print("label:", repr(bridge.youtubeSelectedFormatLabel))
    print("size:", bridge.youtubeSelectedFileSize)

    def snap() -> None:
        img = window.grabWindow()
        out = os.path.abspath(OUT)
        img.save(out)
        print("saved", out)
        bad = [w for w in warnings if "Theme is not defined" not in w]
        print("qml warnings:", len(bad))
        for w in bad[:10]:
            print("warn:", w)
        app.quit()

    QTimer.singleShot(700, snap)


QTimer.singleShot(500, poll)
app.exec()
