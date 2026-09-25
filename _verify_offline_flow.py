"""Drive the fully offline flow through the real QML, offscreen.

Why this exists: the offline pipeline can be verified from the CLI, but the
failures users actually hit live in the bridge/QML layer (a stale persisted
model path, a readiness check that says "ready" for a broken file, a Run button
that starts a download instead of a run). This harness loads `Main.qml` with a
live `AppBridge` and presses Run exactly as the UI does.

Usage:
    python _verify_offline_flow.py [media-file]

With no argument it uses a short clip cut from `cache/compare_media.mp4` if
present, otherwise it stops after printing the readiness state.

Notes that cost real time to rediscover:
  * `HTTP_PROXY` / `HTTPS_PROXY` must be cleared — a proxy in the environment
    makes the OpenAI SDK send `127.0.0.1` traffic through it, and llama-server
    answers with an unrelated HTTP 404. This harness clears them itself; the
    note is here because a CLI run does *not*. Local-only workaround, not an
    app bug.
  * `setApplicationName` / `setOrganizationName` must match `main.py`, otherwise
    `QSettings()` reads an empty store and the user's persisted model paths are
    invisible.
  * Port 8080 is usually XAMPP's Apache on this machine, so the bundled
    llama-server falls back to 8081. That is expected and handled.
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

# A proxy in the environment makes the OpenAI SDK send 127.0.0.1 traffic through
# it, and llama-server answers with an unrelated HTTP 404. Clear it in-process so
# the harness does not depend on the caller's shell. Local-only workaround, not
# an app bug.
for _var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
             "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_var, None)

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

app = QGuiApplication.instance() or QGuiApplication([])
# Same identity as main.py so QSettings() resolves the user's real store.
app.setApplicationName("Translation Agent")
app.setOrganizationName("Translation Agent")

from backend.bridge import AppBridge  # noqa: E402

PROBE_SECONDS = 12


def _cut_probe(source: str) -> str:
    """Cut a short audio clip so the offline run finishes in ~1–2 minutes.

    A full 4-minute video takes ~17 minutes offline (ASR + local translation),
    which is far too slow to iterate on. Returns "" if ffmpeg is unavailable.
    """
    import subprocess
    import tempfile

    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""
    if not os.path.isfile(ffmpeg):
        return ""

    out = os.path.join(tempfile.gettempdir(), "ta_offline_probe.wav")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-ss", "60",
             "-t", str(PROBE_SECONDS), "-i", source,
             "-vn", "-ac", "1", "-ar", "16000", out],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return out if os.path.isfile(out) else ""


def _default_media() -> str:
    for candidate in (
        os.path.join(HERE, "cache", "compare_media.mp4"),
        os.path.join(HERE, "dist", "当我把生活变成了开放世界 RPG…….mp4"),
    ):
        if os.path.isfile(candidate):
            return _cut_probe(candidate) or candidate
    return ""


def main() -> int:
    print("booting…", flush=True)
    media = sys.argv[1] if len(sys.argv) > 1 else _default_media()

    bridge = AppBridge()
    print("bridge ready", flush=True)
    engine = QQmlApplicationEngine()
    engine.addImportPath(os.path.join(HERE, "ui", "qml"))
    engine.rootContext().setContextProperty("appBridge", bridge)
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "ui", "qml", "Main.qml")))
    if not engine.rootObjects():
        print("QML FAILED TO LOAD")
        return 2
    print("qml loaded", flush=True)

    print("pipelineMode            :", bridge.pipelineMode)
    print("asrModel (persisted)    :", bridge.asrModel)
    print("asrModelState           :", bridge.asrModelState, "|", bridge.asrModelProblem)
    print("asrModelSelectionProblem:", bridge.asrModelSelectionProblem)
    print("localModel (persisted)  :", bridge.localModel)
    print("localModelState         :", bridge.localModelState, "|", bridge.localModelProblem)
    print("readinessRows           :")
    for row in bridge.readinessRows:
        print("   ", row)

    if not media:
        print("\nNo media file found; stopping after the readiness report.")
        return 0

    state = {"started": 0.0}

    def start() -> None:
        bridge.filePath = media
        bridge.outPath = os.path.join(HERE, "_verify_offline_flow.srt")
        print("\nRunning offline on:", media)
        state["started"] = time.time()
        bridge.runTranslation()

    def poll() -> None:
        if bridge.isRunning:
            return
        out_path = os.path.join(HERE, "_verify_offline_flow.srt")
        print(f"\n=== finished in {time.time() - state['started']:.0f}s ===")
        print("statusState  :", bridge.statusState)
        print("statusMessage:", bridge.statusMessage)
        print("failureCode  :", bridge.failureCode)
        print("output written:", os.path.isfile(out_path), out_path)
        print("\n--- log ---")
        print(bridge.logText)
        app.quit()

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(500)
    QTimer.singleShot(300, start)
    QTimer.singleShot(3_600_000, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
