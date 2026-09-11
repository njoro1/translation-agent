"""Render the YouTube panel offscreen and read what the user would actually see.

The backend was already proven to *produce* the right "not available in that
format" message; this checks the QML actually **shows** it — the label text, the
warning colour, and the status text after pressing Download.
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
# Imported at module level on purpose: this must happen *before*
# ``rootObjects()`` or the window comes back as a plain QWindow with no
# ``grabWindow()``.
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401

app = QGuiApplication(sys.argv)

from backend.bridge import AppBridge  # noqa: E402
from src import youtube_media  # noqa: E402

PAYLOAD = {
    "title": "Synthetic format test",
    "duration": 600,
    "codecs": ["h264", "vp9"],
    "resolutions": [1080, 720, 360],
    "has_english_subtitle": False,
    "formats": [
        # H.264: 1080 + 720 + 360 only (no 1440/2160)
        {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none",
         "height": 1080, "ext": "mp4", "tbr": 4000, "filesize": 90_000_000,
         "fps": 30},
        {"format_id": "136", "vcodec": "avc1.4d401f", "acodec": "none",
         "height": 720, "ext": "mp4", "tbr": 2500, "filesize": 50_000_000,
         "fps": 30},
        {"format_id": "134", "vcodec": "avc1.4d401e", "acodec": "none",
         "height": 360, "ext": "mp4", "tbr": 1000, "filesize": 20_000_000,
         "fps": 30},
        # VP9: 1080 only
        {"format_id": "248", "vcodec": "vp09.00.41.08", "acodec": "none",
         "height": 1080, "ext": "webm", "tbr": 2000, "filesize": 40_000_000,
         "fps": 30},
        # audio
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2",
         "height": 0, "ext": "m4a", "tbr": 128, "filesize": 8_000_000},
    ],
}


def build_info() -> dict:
    codecs, res, matrix, best = youtube_media._build_matrix(PAYLOAD["formats"])
    return {
        "title": PAYLOAD["title"], "duration": PAYLOAD["duration"],
        "codecs": codecs, "resolutions": res, "matrix": matrix, "best": best,
        "has_english_subtitle": False,
    }


def find(root: QObject, name: str) -> QObject | None:
    return root.findChild(QObject, name)


def main() -> int:
    info = build_info()
    bridge = AppBridge()
    bridge._settings.clear()
    bridge.url = "https://www.youtube.com/watch?v=aaaaaaaaaaa"

    engine = QQmlApplicationEngine()
    warnings: list[str] = []
    engine.warnings.connect(lambda w: warnings.append(f"{w}"))
    engine.rootContext().setContextProperty("appBridge", bridge)

    qml_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "ui", "qml")
    from PySide6.QtCore import QUrl
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    if not engine.rootObjects():
        print("FAILED to load Main.qml")
        return 2
    root = engine.rootObjects()[0]

    # Inject only after load (the generation guard needs a matching tag).
    bridge._youtube_info_gen += 1
    bridge._on_youtube_info(f"INFO:{bridge._youtube_info_gen}|" + json.dumps(info))

    label = find(root, "youtubeSelectionLabel")
    if label is None:
        print("FAILED: youtubeSelectionLabel not found")
        return 3

    failures = []

    # --- Case A: an available pair ------------------------------------------
    bridge.youtubeSelectedCodec = "h264"
    bridge.youtubeSelectedResolution = "720"
    text_a = label.property("text")
    color_a = label.property("color")
    print("== available pair (H.264 / 720p) ==")
    print("  label text :", text_a)
    print("  label color:", color_a)
    if not str(text_a).startswith("Selected:"):
        failures.append(("available", text_a))

    # --- Case B: an unavailable pair ----------------------------------------
    bridge.youtubeSelectedCodec = "h264"
    bridge.youtubeSelectedResolution = "2160"
    text_b = label.property("text")
    color_b = label.property("color")
    print("\n== unavailable pair (H.264 / 2160p) ==")
    print("  label text :", text_b)
    print("  label color:", color_b)
    if "not available" not in str(text_b).lower():
        failures.append(("unavailable-label", text_b))
    if color_a == color_b:
        failures.append(("warning-colour", f"{color_a} == {color_b}"))

    # --- Case C: pressing Download must refuse, not fetch --------------------
    started = []
    bridge.threadpool = type(
        "T", (), {"start": lambda self, w: started.append(w)})()
    bridge.downloadYouTubeVideo()
    status = bridge.youtubeVideoStatus
    print("\n== download pressed on the unavailable pair ==")
    print("  status  :", status.strip())
    print("  started :", started)
    if started:
        failures.append(("started-a-download", started))
    if "not available" not in status.lower():
        failures.append(("download-status", status))

    # --- Case D: switching back to a good pair clears the error --------------
    bridge.youtubeSelectedResolution = "360"
    text_d = label.property("text")
    print("\n== back to an available pair (H.264 / 360p) ==")
    print("  label text :", text_d)
    if not str(text_d).startswith("Selected:"):
        failures.append(("recovered", text_d))

    # Screenshot so a human can confirm the layout still renders correctly.
    try:
        root.show()
        app.processEvents()
        image = root.grabWindow()
        if image is not None and not image.isNull():
            shot = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "ui_shots", "youtube_message_check.png")
            os.makedirs(os.path.dirname(shot), exist_ok=True)
            image.save(shot)
            print("\nscreenshot:", shot, f"({image.width()}x{image.height()})")
    except Exception as exc:  # noqa: BLE001
        print("\nscreenshot skipped:", exc)

    layout_warnings = [w for w in warnings if "managed by a layout" in w]
    print("QML warnings:", len(warnings),
          f"(layout anchor warnings: {len(layout_warnings)})")
    if layout_warnings:
        print("  e.g.", layout_warnings[0])
    print("\nRESULT:", "UI SHOWS THE RIGHT MESSAGE" if not failures
          else f"FAILURES -> {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
