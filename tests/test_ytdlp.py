"""Tests for src/ytdlp.py — running yt-dlp from source *and* from a frozen app.

The frozen path matters because a PyInstaller one-file build has no Python
interpreter to spawn: ``python -m yt_dlp`` is impossible and an external
``yt-dlp.exe`` cannot be assumed. Those tests drive ``yt_dlp.main()`` with a
stub module so they run offline and in milliseconds.
"""
import json
import os
import subprocess
import sys
import types

import pytest

from src import ytdlp, youtube_media


def _fake_yt_dlp(handler):
    """Install a stub ``yt_dlp`` module; returns a list of the argv it saw."""
    seen: list[list[str]] = []

    module = types.ModuleType("yt_dlp")

    def main(argv=None):
        seen.append(list(argv or []))
        handler(argv or [])
        raise SystemExit(0)

    module.main = main
    return module, seen


# --- launcher resolution -----------------------------------------------------
class TestStripLauncher:
    def test_strips_python_module_prefix(self):
        cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "URL"]
        assert ytdlp._strip_launcher(cmd) == ["--no-warnings", "URL"]

    def test_strips_yt_dlp_executable(self):
        cmd = [r"C:\Tools\yt-dlp.EXE", "--no-warnings", "URL"]
        assert ytdlp._strip_launcher(cmd) == ["--no-warnings", "URL"]

    def test_leaves_bare_arguments_untouched(self):
        cmd = ["--no-warnings", "-f", "best", "URL"]
        assert ytdlp._strip_launcher(cmd) == cmd

    def test_does_not_eat_looking_arguments_after_the_prefix(self):
        cmd = [sys.executable, "-m", "yt_dlp", "-o", "%(title)s -m.%(ext)s", "URL"]
        assert ytdlp._strip_launcher(cmd) == ["-o", "%(title)s -m.%(ext)s", "URL"]


class TestUseInProcess:
    def test_frozen_uses_inprocess(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_BIN", raising=False)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert ytdlp.use_inprocess() is True

    def test_explicit_binary_beats_frozen(self, monkeypatch, tmp_path):
        exe = tmp_path / "yt-dlp.exe"
        exe.write_bytes(b"x")
        monkeypatch.setenv("YT_DLP_BIN", str(exe))
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert ytdlp.use_inprocess() is False

    def test_not_frozen_uses_subprocess(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_INPROC", raising=False)
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert ytdlp.use_inprocess() is False

    def test_env_override_forces_inprocess(self, monkeypatch):
        monkeypatch.setenv("YT_DLP_INPROC", "1")
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert ytdlp.use_inprocess() is True


# --- the output sink ---------------------------------------------------------
class TestLineSink:
    def test_splits_on_newlines(self):
        lines = []
        sink = ytdlp._LineSink(on_line=lambda line: lines.append(line))
        sink.write("[download] 1%[download] 2%\n[download] 3%\n")
        assert lines == ["[download] 1%[download] 2%", "[download] 3%"]

    def test_flushes_trailing_partial_line(self):
        lines = []
        sink = ytdlp._LineSink(on_line=lambda line: lines.append(line))
        sink.write("Merging formats into \"out.mkv\"")
        assert lines == []
        sink.drain()
        assert lines == ["Merging formats into \"out.mkv\""]

    def test_returning_false_aborts(self):
        lines = []
        sink = ytdlp._LineSink(on_line=lambda line: lines.append(line) or False)
        with pytest.raises(ytdlp._Cancelled):
            sink.write("first\nsecond\n")
        assert lines == ["first"]

    def test_cancel_check_is_consulted_on_every_write(self):
        sink = ytdlp._LineSink(on_line=lambda line: True, cancel_check=lambda: True)
        with pytest.raises(ytdlp._Cancelled):
            sink.write("[download] 5%")

    def test_accepts_bytes_and_reports_terminal_absent(self):
        lines = []
        sink = ytdlp._LineSink(on_line=lambda line: lines.append(line))
        sink.write(b"[info] hi\n")
        sink.flush()
        assert lines == ["[info] hi"]
        assert sink.isatty() is False


# --- in-process execution ----------------------------------------------------
class TestInProcessRun:
    def test_streams_lines_and_returns_exit_code(self, monkeypatch):
        def handler(argv):
            print("[download] Destination: out.mp4")
            print("[download]  42.0% of 10MiB")
            print("[download] 100% of 10MiB")
            raise SystemExit(0)

        module, seen = _fake_yt_dlp(handler)
        monkeypatch.setitem(sys.modules, "yt_dlp", module)
        monkeypatch.setenv("YT_DLP_INPROC", "1")

        lines = []
        rc = ytdlp.run_ytdlp(
            ytdlp.yt_dlp_cmd() + ["--newline", "URL"],
            on_line=lambda line: lines.append(line),
        )
        assert rc == 0
        assert seen[0] == ["--newline", "URL"], "launcher prefix must be stripped"
        assert lines[0] == "[download] Destination: out.mp4"
        assert any("100%" in line for line in lines)
        assert sys.stdout is not None, "sys.stdout must be restored"

    def test_nonzero_exit_is_propagated(self, monkeypatch):
        def handler(argv):
            print("ERROR: unable to download video data: HTTP Error 403")
            raise SystemExit(1)

        module, _ = _fake_yt_dlp(handler)
        monkeypatch.setitem(sys.modules, "yt_dlp", module)
        monkeypatch.setenv("YT_DLP_INPROC", "1")

        lines = []
        rc = ytdlp.run_ytdlp(["yt-dlp", "URL"], on_line=lines.append)
        assert rc == 1
        assert any("403" in line for line in lines)

    def test_cancel_stops_the_run(self, monkeypatch):
        def handler(argv):
            for i in range(1000):
                print(f"[download] {i}%")
            raise SystemExit(0)

        module, _ = _fake_yt_dlp(handler)
        monkeypatch.setitem(sys.modules, "yt_dlp", module)
        monkeypatch.setenv("YT_DLP_INPROC", "1")

        seen: list[str] = []
        rc = ytdlp.run_ytdlp(
            ["yt-dlp", "URL"],
            on_line=lambda line: (seen.append(line), False)[1],
        )
        assert rc == 1
        assert len(seen) == 1, "should abort after the first line"
        assert sys.stdout is not None

    def test_missing_yt_dlp_raises_unavailable(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "yt_dlp", None)
        monkeypatch.setenv("YT_DLP_INPROC", "1")
        with pytest.raises(ytdlp.YtdlpUnavailable):
            ytdlp.run_ytdlp(["yt-dlp", "URL"])


class TestInProcessCapture:
    def test_dump_json_is_returned_as_text(self, monkeypatch):
        payload = {"title": "Test video", "formats": [{"format_id": "401"}]}

        def handler(argv):
            assert "--dump-json" in argv
            print(json.dumps(payload))
            raise SystemExit(0)

        module, _ = _fake_yt_dlp(handler)
        monkeypatch.setitem(sys.modules, "yt_dlp", module)
        monkeypatch.setenv("YT_DLP_INPROC", "1")

        out = ytdlp.run_ytdlp_capture(["yt-dlp", "--dump-json", "URL"], timeout=30)
        assert json.loads(out)["title"] == "Test video"

    def test_failure_raises_with_output(self, monkeypatch):
        def handler(argv):
            print("ERROR: video unavailable")
            raise SystemExit(1)

        module, _ = _fake_yt_dlp(handler)
        monkeypatch.setitem(sys.modules, "yt_dlp", module)
        monkeypatch.setenv("YT_DLP_INPROC", "1")

        with pytest.raises(ytdlp.YtdlpFailed) as exc:
            ytdlp.run_ytdlp_capture(["yt-dlp", "--dump-json", "URL"])
        assert "video unavailable" in exc.value.output
        assert exc.value.code == 1


# --- subprocess path (unchanged behaviour) -----------------------------------
class TestSubprocessRun:
    def test_streams_a_real_child_process(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_INPROC", raising=False)
        monkeypatch.delattr(sys, "frozen", raising=False)

        lines = []
        rc = ytdlp.run_ytdlp(
            [sys.executable, "-c", "print('one'); print('two')"],
            on_line=lines.append,
        )
        assert rc == 0
        assert lines == ["one", "two"]

    def test_cancel_terminates_the_child(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_INPROC", raising=False)
        monkeypatch.delattr(sys, "frozen", raising=False)

        proc_ref: dict = {}
        rc = ytdlp.run_ytdlp(
            [sys.executable, "-c",
             "import time\n"
             "for i in range(300):\n"
             "    print(i, flush=True)\n"
             "    time.sleep(0.1)"],
            on_line=lambda line: True,
            cancel_check=lambda: True,
            proc_ref=proc_ref,
        )
        assert rc != 0
        assert proc_ref["proc"].poll() is not None, "child should be gone"


# --- integration with the modules that call it -------------------------------
class TestModuleIntegration:
    def test_inspect_video_works_inprocess(self, monkeypatch):
        payload = {
            "title": "Frozen build video",
            "formats": [
                {"format_id": "401", "vcodec": "av01", "acodec": "none",
                 "height": 2160, "ext": "mp4", "tbr": 20000},
                {"format_id": "251", "vcodec": "none", "acodec": "opus",
                 "height": None, "ext": "webm", "tbr": 160},
            ],
            "subtitles": {"en": []},
            "automatic_captions": {},
        }

        module, seen = _fake_yt_dlp(
            lambda argv: print(json.dumps(payload)) or SystemExit(0)
        )
        monkeypatch.setitem(sys.modules, "yt_dlp", module)
        monkeypatch.setenv("YT_DLP_INPROC", "1")

        info = youtube_media.inspect_video("https://youtu.be/PHAcOZ7E-pM")
        assert info["title"] == "Frozen build video"
        assert info["codecs_available"]["av1"] is True
        assert info["has_english_subtitle"] is True
        # The launcher must never leak into the arguments handed to yt_dlp.
        assert all(arg != "-m" and arg != "yt_dlp" for arg in seen[0])

    def test_download_reports_percent_inprocess(self, monkeypatch, tmp_path):
        def handler(argv):
            print("[download] Destination: video.mp4")
            print("[download]  50.0% of 10MiB")
            print("[download] 100.0% of 10MiB")
            raise SystemExit(0)

        module, _ = _fake_yt_dlp(handler)
        monkeypatch.setitem(sys.modules, "yt_dlp", module)
        monkeypatch.setenv("YT_DLP_INPROC", "1")

        percents: list[int] = []
        logs: list[str] = []
        youtube_media.download_video(
            "https://youtu.be/PHAcOZ7E-pM", "401+bestaudio",
            str(tmp_path / "%(title)s.%(ext)s"),
            progress_cb=logs.append,
            percent_cb=percents.append,
        )
        assert percents == [50, 100]
        assert any("[download] Destination" in line for line in logs)

    def test_subtitle_does_not_demand_a_path_executable_when_frozen(
        self, monkeypatch, tmp_path
    ):
        """The old guard required 'yt-dlp' on PATH, which no frozen build has.

        It must get past that check and fail on the *real* reason instead.
        """
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delenv("YT_DLP_BIN", raising=False)
        monkeypatch.setitem(sys.modules, "yt_dlp", _fake_yt_dlp(lambda argv: None)[0])

        with pytest.raises(RuntimeError) as exc:
            youtube_media.download_subtitle(
                "https://youtu.be/PHAcOZ7E-pM", "en", str(tmp_path / "sub.%(ext)s")
            )
        assert "not installed" not in str(exc.value)
        assert "No English subtitle" in str(exc.value)


class TestFrozenFfmpegLookup:
    def test_finds_ffmpeg_unpacked_next_to_the_exe(self, monkeypatch, tmp_path):
        bundled = tmp_path / "ffmpeg-win-x86_64-v7.1.exe"
        bundled.write_bytes(b"x")

        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.delenv("FFMPEG_BIN", raising=False)

        try:
            import imageio_ffmpeg
        except ImportError:  # pragma: no cover
            imageio_ffmpeg = None
        if imageio_ffmpeg is not None:
            # A packaged imageio can report a path that was never collected.
            monkeypatch.setattr(
                imageio_ffmpeg, "get_ffmpeg_exe", lambda: str(tmp_path / "missing.exe")
            )

        result = youtube_media._ffmpeg_exe()
        # The returned binary must be *literally* named ffmpeg.exe, otherwise
        # yt-dlp's --ffmpeg-location directory scan never finds it and the
        # video+audio merge silently fails.
        assert os.path.basename(result).lower() == "ffmpeg.exe"
        assert os.path.isfile(result)


class TestFfmpegMerge:
    """The video-only + audio streams must become ONE file.

    A packaged ffmpeg is named e.g. ``ffmpeg-win-x86_64-v7.1.exe``; yt-dlp only
    finds ``ffmpeg.exe`` in the directory it is pointed at, so the merge used to
    never run and the user got two separate files. These tests pin that behaviour.
    """

    def test_ensure_ffmpeg_exe_named_copies_when_misnamed(self, tmp_path):
        misnamed = tmp_path / "ffmpeg-win-x86_64-v7.1.exe"
        misnamed.write_bytes(b"binary-bytes")
        named = youtube_media._ensure_ffmpeg_exe_named(str(misnamed))
        assert os.path.basename(named).lower() == "ffmpeg.exe"
        assert os.path.isfile(named)
        assert os.path.getsize(named) == len(b"binary-bytes")

    def test_ensure_ffmpeg_exe_named_passes_through_when_already_named(self, tmp_path):
        good = tmp_path / "ffmpeg.exe"
        good.write_bytes(b"x")
        named = youtube_media._ensure_ffmpeg_exe_named(str(good))
        assert named == str(good)

    def test_run_passes_ffmpeg_location_with_named_binary(self, tmp_path, monkeypatch):
        """_run_yt_dlp must hand yt-dlp a --ffmpeg-location directory that
        contains ffmpeg.exe (the directory for a misnamed binary is silently
        ignored)."""
        ffmpeg = tmp_path / "ffmpeg.exe"
        ffmpeg.write_bytes(b"x")

        seen: list[list[str]] = []

        def handler(argv):
            seen.append(list(argv))
            raise SystemExit(0)

        module, _ = _fake_yt_dlp(handler)
        monkeypatch.setitem(sys.modules, "yt_dlp", module)
        monkeypatch.setenv("YT_DLP_INPROC", "1")
        monkeypatch.setattr(youtube_media, "_ffmpeg_exe", lambda: str(ffmpeg))

        youtube_media._run_yt_dlp(["yt-dlp", "URL"])
        assert seen, "yt-dlp should have been invoked"
        cmd = seen[0]
        idx = cmd.index("--ffmpeg-location")
        loc = cmd[idx + 1]
        assert os.path.isdir(loc)
        assert os.path.isfile(os.path.join(loc, "ffmpeg.exe"))

    def test_download_merges_video_and_audio_into_one_file(self, tmp_path, monkeypatch):
        """End-to-end: a video-only + bestaudio pair must be merged into a single
        file. The stub asserts --ffmpeg-location resolves to a ffmpeg.exe, then
        emits the 'Merging formats into' line yt-dlp writes once the merge runs.
        """
        ffmpeg = tmp_path / "ffmpeg.exe"
        ffmpeg.write_bytes(b"x")
        out_base = tmp_path / "video"
        out_template = str(out_base) + ".%(ext)s"

        def handler(argv):
            idx = argv.index("--ffmpeg-location")
            loc = argv[idx + 1]
            assert os.path.isfile(os.path.join(loc, "ffmpeg.exe")), \
                "yt-dlp must find ffmpeg.exe via --ffmpeg-location"
            merged = out_base.with_suffix(".mkv")
            merged.write_text("merged video+audio")
            print(f'Merging formats into "{merged}"')
            raise SystemExit(0)

        module, _ = _fake_yt_dlp(handler)
        monkeypatch.setitem(sys.modules, "yt_dlp", module)
        monkeypatch.setenv("YT_DLP_INPROC", "1")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(youtube_media, "_ffmpeg_exe", lambda: str(ffmpeg))

        result = youtube_media.download_video(
            "https://youtu.be/abc", "401+bestaudio", out_template
        )
        assert os.path.basename(result) == "video.mkv"
        assert os.path.isfile(result)
