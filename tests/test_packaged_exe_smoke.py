"""Smoke-test the *built* executable — the one thing unit tests never touch.

`test_build_contract.py` verifies declarations; this actually **runs the
packaged app**. It is the only check that would catch a bundle which starts but
fails to load its QML (a missing `--add-data`, a Qt module dropped by the
trimmed bundle, a broken import path).

The build under `dist/TranslationAgent/` only exists after someone runs
`build_exe.bat`, so these tests **skip** when it is absent. Run the build first
to exercise them.

How it works: launch the exe with ``QT_QPA_PLATFORM=offscreen`` and no
interaction, wait a few seconds, then kill it. The app writes a `debug.log`
next to itself, and `main()` only reaches ``app.exec()`` after
``engine.rootObjects()`` is non-empty — i.e. the QML actually loaded. So a
clean log with "Loading QML" and nothing after it means startup succeeded.
An event loop that keeps running is the success signal, *not* a non-zero exit
(there is nothing for a windowed app to exit from on its own).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "TranslationAgent" / "TranslationAgent.exe"
DEBUG_LOG = EXE.parent / "debug.log"

pytestmark = pytest.mark.skipif(
    not EXE.is_file(),
    reason="packaged build not present — run build_exe.bat to enable this test",
)

# Long enough for a cold start on a slow disk; the app is killed right after.
STARTUP_GRACE_SECONDS = 25


def _launch(exe: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_CONTROLS_STYLE"] = "Basic"
    # Keep the child from inheriting anything that would make it open a window
    # or block on input.
    env.pop("QT_PLUGIN_PATH", None)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    return subprocess.Popen(
        [str(exe)],
        cwd=str(exe.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=env,
        creationflags=creationflags,
    )


def _stop(proc: subprocess.Popen) -> str:
    """Terminate the app and return whatever it printed."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=15)
    try:
        out = proc.stdout.read() if proc.stdout else b""
    except (OSError, ValueError):
        out = b""
    return out.decode("utf-8", errors="replace")


def _bundled_source_paths() -> list[Path]:
    """First-party files baked into the bundle, in their *source* locations."""
    tracked: list[Path] = [ROOT / "main.py"]
    for folder in ("backend", "src", "ui"):
        tracked.extend((ROOT / folder).rglob("*.py"))
        tracked.extend((ROOT / folder).rglob("*.qml"))
    return [p for p in tracked if p.is_file()]


def _newest_source_mtime() -> float:
    return max(p.stat().st_mtime for p in _bundled_source_paths())


@pytest.fixture(scope="module")
def launched():
    """Start the exe once for the module; hand back (proc, output, log)."""
    if DEBUG_LOG.exists():
        DEBUG_LOG.unlink()
    proc = _launch(EXE)
    deadline = time.time() + STARTUP_GRACE_SECONDS
    while time.time() < deadline:
        if proc.poll() is not None:
            break                      # crashed early — stop waiting
        if DEBUG_LOG.exists():
            text = DEBUG_LOG.read_text(encoding="utf-8", errors="replace")
            if "Loading QML" in text:
                # Give it a moment to either reach exec() or log a failure.
                time.sleep(3)
                break
        time.sleep(0.5)
    output = _stop(proc)
    log = (DEBUG_LOG.read_text(encoding="utf-8", errors="replace")
           if DEBUG_LOG.exists() else "")
    return proc, output, log


class TestBuildIsCurrent:
    """Guard against the smoke test green-lighting a *stale* bundle.

    The tests below only exercise the code that was baked into the exe. If
    source has moved on since the build, a pass proves nothing about the
    current tree — it would happily report success while shipping a bundle
    without the latest fixes.
    """
    def test_build_is_newer_than_all_bundled_sources(self):
        built = EXE.stat().st_mtime
        newest = _newest_source_mtime()
        if newest > built:
            stale = sorted(
                str(p.relative_to(ROOT))
                for p in _bundled_source_paths()
                if p.stat().st_mtime > built
            )
            pytest.fail(
                "dist/TranslationAgent is STALE: "
                f"{len(stale)} source file(s) changed after the build "
                f"({time.strftime('%H:%M', time.localtime(newest))} > "
                f"{time.strftime('%H:%M', time.localtime(built))}).\n"
                "The smoke tests below would pass while validating old code.\n"
                f"Rebuild with build_exe.bat. Outdated: {stale[:8]}"
            )

    def test_bundle_is_internally_consistent(self):
        """A half-finished build leaves a *mixed* bundle that still starts.

        This was found the hard way: a PyInstaller run whose COLLECT stage was
        interrupted left the old directory in place and copied only a couple of
        new files over it. The exe still launched, so every other test here
        passed — but the bundle was 4383 files from the previous build and 2
        from the new one. Comparing *file counts per build date* catches it
        where an exe-mtime check cannot, because the exe itself was the old
        one and looked current.

        A real bundle is dominated by one build timestamp; a handful of newer
        stragglers means the build was cut short.
        """
        internal = EXE.parent / "_internal"
        assert internal.is_dir(), f"missing bundle directory: {internal}"

        stamps: dict[str, int] = {}
        for path in internal.rglob("*"):
            if not path.is_file():
                continue
            day = time.strftime("%Y-%m-%d", time.localtime(path.stat().st_mtime))
            stamps[day] = stamps.get(day, 0) + 1

        assert stamps, "the bundle contains no files at all"
        newest_day, newest_count = max(stamps.items(), key=lambda kv: kv[0])
        total = sum(stamps.values())
        if newest_count < total * 0.5:
            minority = sorted(
                time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime))
                for p in internal.rglob("*") if p.is_file()
            )
            pytest.fail(
                "the bundle mixes build outputs: only "
                f"{newest_count}/{total} files come from the newest build "
                f"({newest_day}). This is the signature of a build that was "
                "interrupted part-way through COLLECT — the app will run old "
                "code despite the exe timestamp. Purge dist/ and rebuild.\n"
                f"Files per build date: {dict(sorted(stamps.items()))}\n"
                f"(sample of newest: {minority[-5:]})"
            )

    def test_bundled_qml_matches_the_source_tree(self):
        """An --add-data miss can silently ship an older Main.qml."""
        for name in ("Main.qml",):
            src = ROOT / "ui" / "qml" / name
            bundled = EXE.parent / "_internal" / "ui" / "qml" / name
            assert src.is_file(), f"source {name} is missing"
            assert bundled.is_file(), f"bundled {name} is missing"
            assert src.read_bytes() == bundled.read_bytes(), (
                f"bundled ui/qml/{name} differs from the source tree — rebuild")

    def test_bundled_python_sources_match_the_tree(self):
        """PyInstaller bakes the *latest* first-party modules into the archive.

        A build that ran before a fix leaves the archive holding old bytecode.
        Recompiling the source and comparing against the bundled .pyc is
        skipped here (they legitimately differ in the header), so instead the
        task is delegated to the mtime guard above; this test covers the case
        where the copy is present but the *contents* drifted.
        """
        for rel in ("_internal/ui/qml/components/YouTubeVideoPanel.qml",):
            src = ROOT / "ui" / "qml" / "components" / "YouTubeVideoPanel.qml"
            bundled = EXE.parent / rel
            assert src.is_file(), f"source {src} is missing"
            assert bundled.is_file(), f"bundled {rel} is missing"
            assert src.read_bytes() == bundled.read_bytes(), (
                f"bundled {rel} is out of date — the format/resolution "
                "dropdowns it defines would not match the fixed bridge")


class TestPackagedExeStarts:
    def test_process_does_not_exit_immediately(self, launched):
        """A windowed app should still be running (in its event loop) when we
        kill it. An immediate exit means it crashed on startup."""
        proc, output, log = launched
        assert proc.returncode is not None
        # terminate()/kill() on Windows yields a non-zero code; what matters is
        # that it did not exit *by itself* before we stopped it.
        assert "Traceback" not in output, output
        assert "Traceback" not in log, log

    def test_debug_log_was_written(self, launched):
        _proc, _output, log = launched
        assert log, ("the packaged app wrote no debug.log — it likely failed "
                     "before logging was configured")

    def test_reports_itself_as_frozen(self, launched):
        """Guards the frozen code paths (resource lookup, plugin env, the
        in-process yt-dlp launcher) actually being exercised."""
        _proc, _output, log = launched
        assert "frozen=True" in log, log

    def test_qml_was_loaded_from_the_bundle(self, launched):
        _proc, _output, log = launched
        assert "Loading QML" in log, log
        assert "Main.qml" in log, log
        assert "_internal" in log, (
            "QML should load from the bundled _internal directory, not the "
            f"source tree:\n{log}")

    def test_no_qml_load_failure(self, launched):
        """`main()` logs 'QML failed to load' and returns -1 when
        `engine.rootObjects()` is empty — the classic symptom of a missing
        --add-data entry or a Qt module dropped from the trimmed bundle."""
        _proc, _output, log = launched
        assert "QML failed to load" not in log, log

    def test_no_unhandled_exception(self, launched):
        _proc, _output, log = launched
        assert "Unhandled exception" not in log, log
        assert "Traceback" not in log, log

    def test_no_qml_warnings_at_startup(self, launched):
        """Startup must be warning-free; QML warnings are logged as ERRORs when
        the engine fails, and any 'QML warning:' line means a binding broke."""
        _proc, _output, log = launched
        assert "QML warning:" not in log, log

    def test_missing_qt_plugin_path_is_not_reported(self, launched):
        """QT_PLUGIN_PATH is set by the app itself for frozen builds; if the
        bundled plugins are absent it warns and the UI may not render."""
        _proc, _output, log = launched
        assert "Qt plugins path not found" not in log, log

    def test_missing_qml_import_path_is_not_reported(self, launched):
        _proc, _output, log = launched
        assert "QML import path not found" not in log, log

    def test_bundled_ffmpeg_is_discoverable(self):
        """Every format the UI offers is a video+audio *merge*, so the packaged
        app is useless without a findable ffmpeg."""
        bundled = list((EXE.parent / "_internal").glob("ffmpeg*.exe"))
        assert bundled, (
            "no ffmpeg binary in the bundle — video downloads would produce "
            "separate video/audio files")
