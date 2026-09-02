"""Screenshot harness: renders the real QML UI and saves PNGs of key states.

Usage:
    python tools/screenshot_ui.py [--out ui_shots]

Uses the offscreen platform (no window flashes) plus QQuickWindow.grabWindow()
so the frames are identical to what a user sees.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# The offscreen GL backend never paints, so grabs come out blank; the software
# backend renders synchronously and grabWindow() captures real frames.
os.environ.setdefault("QT_QUICK_BACKEND", "software")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402
import shiboken6  # noqa: E402

from backend.bridge import AppBridge  # noqa: E402
from main import _load_bundled_fonts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="ui_shots")
    args = parser.parse_args()
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    app = QGuiApplication(sys.argv)
    _load_bundled_fonts()

    engine = QQmlApplicationEngine()
    warnings: list[str] = []
    engine.warnings.connect(lambda msgs: warnings.extend(str(m) for m in msgs))

    bridge = AppBridge()
    bridge._settings.clear()  # deterministic defaults for screenshots
    engine.rootContext().setContextProperty("appBridge", bridge)
    engine.load(QUrl.fromLocalFile(os.path.abspath("ui/qml/Main.qml")))
    if not engine.rootObjects():
        print("FATAL: QML failed to load")
        for w in warnings:
            print("warn:", w)
        return 1
    window = engine.rootObjects()[0]
    tabs = window.findChild(__import__("PySide6").QtCore.QObject, "mainTabs")
    drawer = window.findChild(__import__("PySide6").QtCore.QObject, "advancedDrawer")

    # Fake result so Review/Quality tabs have content.
    result = {
        "version": 1, "output_path": r"C:\Videos\Blue Bird.srt",
        "format": "srt", "source_language": "ja",
        "pipeline_mode": "local_cloud", "strict_quality": False,
        "quality": {
            "cue_count": 65, "warning_count": 7, "error_count": 1,
            "untranslated_count": 0, "untranslated_marker_count": 1,
            "tag_leakage_count": 1, "cjk_residue_count": 3,
            "duplicate_count": 2, "overlap_count": 0,
            "average_cps": 11.4, "max_cps": 24.8,
            "average_duration": 2.31, "max_duration": 6.9,
            "issues": [
                {"cue_index": 4, "start": 9.2, "end": 11.0,
                 "issues": ["asr_tag_leakage_error"]},
                {"cue_index": 12, "start": 30.5, "end": 33.1,
                 "issues": ["cps_warning", "chars_warning"]},
                {"cue_index": 17, "start": 41.0, "end": 43.0,
                 "issues": ["untranslated_marker_error"]},
                {"cue_index": 21, "start": 52.3, "end": 54.9,
                 "issues": ["cjk_residue_warning"]},
                {"cue_index": 22, "start": 55.0, "end": 57.2,
                 "issues": ["duplicate_translation_warning"]},
                {"cue_index": 40, "start": 99.9, "end": 102.4,
                 "issues": ["too_long_warning"]},
            ],
        },
        "cues": [
            {"index": i + 1,
             "start_ms": i * 2600, "end_ms": i * 2600 + 2300,
             "source": f"セリフその{i + 1}、ちゃんと読める長さ。",
             "text": ("Line %d that reads naturally." % (i + 1))
                     if i % 9 else "<|zh|>Leaked tag line",
             "status": ("ok" if i % 9 else "warning")}
            for i in range(65)
        ],
    }
    with open("cache/last_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f)

    def snap(name: str) -> None:
        # rootObjects()[0] comes back typed as plain QWindow; re-wrap the same
        # C++ pointer as QQuickWindow so we get the real scene-grab method.
        qwin = shiboken6.wrapInstance(
            shiboken6.getCppPointer(window)[0], QQuickWindow
        )
        img = qwin.grabWindow()
        path = os.path.join(out_dir, f"{name}.png")
        if not img.save(path):
            print(f"FATAL: failed saving {path}")
            app.quit()
            return
        print(f"saved {path}")

    state = {"step": 0, "proxy": None}

    def step() -> None:
        s = state["step"]
        state["step"] += 1
        try:
            if s == 0:
                snap("01_run_youtube_default")
                # Open the preset dropdown to verify popup content rendering.
                from PySide6.QtCore import QMetaObject

                combo = window.findChild(__import__("PySide6").QtCore.QObject,
                                         "presetPicker")
                QMetaObject.invokeMethod(combo, "openPopupExternally")
            elif s == 1:
                snap("01b_combo_popup_open")
                from PySide6.QtCore import QMetaObject

                combo = window.findChild(__import__("PySide6").QtCore.QObject,
                                         "presetPicker")
                QMetaObject.invokeMethod(combo, "closePopupExternally")
                bridge.pipelineMode = "local_cloud"
            elif s == 2:
                snap("02_run_local_cloud")
                bridge.pipelineMode = "offline"
            elif s == 3:
                snap("03_run_offline")
                if drawer is not None:
                    drawer.setProperty("expanded", True)
            elif s == 4:
                snap("04_offline_advanced_open")
                if drawer is not None:
                    drawer.setProperty("expanded", False)
                bridge.pipelineMode = "youtube_cloud"
            elif s == 5:
                bridge._resolved_out_path = result["output_path"]
                bridge._load_result_json()
                state["proxy"] = bridge.cue_proxy
                tabs.setProperty("currentIndex", 1)
            elif s == 6:
                snap("05_review_all")
                tabs.setProperty("currentIndex", 2)
            elif s == 7:
                snap("06_quality")
                tabs.setProperty("currentIndex", 1)
                state["proxy"].filterMode = "failed"
            elif s == 8:
                snap("07_review_failed_filter")
                state["proxy"].filterMode = "all"
                bridge.logVisible = True
                # logText is a read-only Qt property; use the internal mutator.
                bridge._append_log(
                    "$ python translate.py https://youtu.be/x --content-preset anime\n"
                    "[mode] source=YouTube backend=cloud\n"
                    "Fetched 65 cues. Translating into English...\n"
                    '{"type":"progress","stage":"translate","done":40,"total":65}\n'
                    "[translate] window 4/6: 12 cues\n"
                    "[tm] Stored 38 new translations\n"
                    '[quality] 7 warnings, 1 errors\n'
                    "Wrote 65 cues to C:\\Videos\\Blue Bird.srt\n"
                )
            elif s == 9:
                snap("08_log_drawer_open")
                app.quit()
        except Exception as exc:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            print(f"FATAL during step {s}: {exc}")
            app.quit()

    timer = QTimer(interval=400, timeout=step)
    timer.start()
    app.exec()

    bad = [w for w in warnings if "Theme is not defined" not in w]
    print(f"qml warnings: {len(bad)}")
    for w in bad[:10]:
        print("warn:", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
