"""Polish harness: render every page of the real UI offscreen, dark + light.

Writes PNGs to ui_shots/polish/. Not part of the shipped app.
"""
import json
import os
import sys

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
# The offscreen platform ships an empty font database on Windows; point Qt at
# the system fonts or every label renders as tofu.
if os.path.isdir(r"C:\Windows\Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer, QUrl, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402
import shiboken6  # noqa: E402

from backend.bridge import AppBridge  # noqa: E402

OUT = os.path.join("ui_shots", "polish")
os.makedirs(OUT, exist_ok=True)

PAGES = ["run", "review", "quality", "log", "settings"]

app = QGuiApplication(sys.argv)
app.setApplicationName("Translation Agent")
app.setOrganizationName("Translation Agent")

bridge = AppBridge()
bridge.clearStoredSettings()

# Seed a fake result so Review/Quality pages render content.
cues = []
import random
random.seed(7)
t = 1000
for i in range(1, 41):
    dur = random.choice([1200, 1800, 2400, 3200, 900])
    status = "ok"
    if i in (7, 19, 33):
        status = "warning"
    if i in (14, 27):
        status = "untranslated"
    cues.append({
        "index": i, "start_ms": t, "end_ms": t + dur,
        "source": f"これはテスト用の日本語字幕行 {i} です。",
        "text": f"This is a sample translated subtitle line number {i}." if status != "untranslated" else "[untranslated]",
        "status": status,
    })
    t += dur + 200
result = {
    "version": 1,
    "output_path": os.path.abspath("cache/sample.srt"),
    "format": "srt",
    "source_language": "ja",
    "pipeline_mode": "youtube_cloud",
    "strict_quality": False,
    "quality": {
        "cue_count": 40, "warning_count": 3, "error_count": 2,
        "empty_count": 0, "untranslated_count": 2, "untranslated_marker_count": 2,
        "tag_leakage_count": 0, "cjk_residue_count": 0, "duplicate_count": 0,
        "overlap_count": 0, "average_cps": 14.2, "max_cps": 23.1,
        "average_duration": 1.9, "max_duration": 3.4,
        "issues": [
            {"cue_index": 7, "start": 0.0, "end": 0.0, "issues": ["cps_warning"]},
            {"cue_index": 14, "start": 0.0, "end": 0.0, "issues": ["empty_text"]},
            {"cue_index": 19, "start": 0.0, "end": 0.0, "issues": ["chars_warning"]},
            {"cue_index": 27, "start": 0.0, "end": 0.0, "issues": ["untranslated_marker_error"]},
            {"cue_index": 33, "start": 0.0, "end": 0.0, "issues": ["too_long_warning"]},
        ],
    },
    "cues": cues,
}
with open("cache/last_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False)
bridge._load_result_json()

engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("appBridge", bridge)
engine.load(QUrl.fromLocalFile(os.path.abspath("ui/qml/Main.qml")))
if not engine.rootObjects():
    print("QML FAILED TO LOAD")
    sys.exit(1)

window = engine.rootObjects()[0]
window.show()

plan = []
for theme in ("dark", "light"):
    for idx, name in enumerate(PAGES):
        plan.append((theme, idx, name))
    plan.append((theme, 0, "run_zoomed"))  # placeholder, unused

step = {"i": 0}


def grab():
    step["i"] += 1
    if step["i"] > len(plan):
        app.quit()
        return
    theme, page, name = plan[step["i"] - 1]
    if name == "run_zoomed":
        return grab()  # skip
    bridge.themeName = theme
    window.setProperty("currentPage", page)

    def cap():
        qwin = shiboken6.wrapInstance(
            shiboken6.getCppPointer(window)[0], QQuickWindow
        )
        img = qwin.grabWindow()
        out = os.path.join(OUT, f"{name}_{theme}.png")
        img.save(out)
        print("wrote", out, flush=True)
        grab()

    QTimer.singleShot(450, cap)


QTimer.singleShot(700, grab)
sys.exit(app.exec())
