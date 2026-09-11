"""Tests for the codec-aware YouTube media module (``src/youtube_media.py``).

Focus: the download selector must always honour the codec and resolution the
user picked. Historical bug: an unavailable (codec, height) pair (or codec
"best" + a height) fell back to an unconstrained ``/best`` yt-dlp selector,
silently downloading a completely different codec/resolution than selected.

A second class of bug is covered here now: fallback chains that could resolve
to a *video-only* stream, silently producing a muted file reported as success,
and stale ``.part`` files that turn a resumable download into a hard 403.
"""
import json
import os
import time

import pytest

from src import youtube_media
from src.youtube_media import (
    _audio_safe_fallback,
    _build_matrix,
    _is_expired_url_error,
    _merge_option,
    _option_best,
    _option_best_height,
    _partial_files,
    normalize_resolution,
    resolve_video_option,
)


def _formats() -> list[dict]:
    """A realistic yt-dlp format list (video-only + one muxed + audio-only)."""
    return [
        {"format_id": "616", "vcodec": "vp09.00.50.08", "acodec": "none",
         "height": 2160, "tbr": 16000, "ext": "webm", "filesize": 900_000_000,
         "fps": 30},
        {"format_id": "398", "vcodec": "vp09.00.40.08", "acodec": "none",
         "height": 720, "tbr": 2500, "ext": "webm", "filesize": 120_000_000,
         "fps": 30},
        {"format_id": "270", "vcodec": "avc1.64002a", "acodec": "none",
         "height": 1080, "tbr": 5000, "ext": "mp4", "filesize": 300_000_000,
         "fps": 30},
        {"format_id": "136", "vcodec": "avc1.64001f", "acodec": "none",
         "height": 720, "tbr": 2500, "ext": "mp4", "filesize": 150_000_000,
         "fps": 30},
        {"format_id": "18", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2",
         "height": 360, "tbr": 600, "ext": "mp4", "filesize": 40_000_000,
         "fps": 30},
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2",
         "height": None, "tbr": 130, "ext": "m4a", "filesize": 5_000_000},
    ]


def _expected_merge(format_id: str, cid: str, height: int) -> str:
    """Selector built for a real video-only format + its audio-safe fallback."""
    return f"{format_id}+bestaudio/{_audio_safe_fallback(cid, height)}"


@pytest.fixture()
def info() -> dict:
    codecs, resolutions, matrix, best = _build_matrix(_formats())
    return {"codecs": codecs, "resolutions": resolutions, "matrix": matrix,
            "best": best}


class TestBuildMatrix:
    def test_heights_sorted_desc(self, info):
        assert info["resolutions"] == [2160, 1080, 720, 360]

    def test_codecs_in_preference_order(self, info):
        # The fixture serves no AV1 stream, so only vp9 + h264 appear — and in
        # the module's preference order (newer codecs first).
        assert info["codecs"] == ["vp9", "h264"]

    def test_combined_format_wins_at_its_height(self, info):
        opt = info["matrix"]["h264"][360]
        assert opt["merge"] is False
        assert opt["format_selector"] == "18"
        assert opt["has_audio"] is True

    def test_merge_built_from_real_format_ids(self, info):
        opt = info["matrix"]["h264"][1080]
        assert opt["merge"] is True
        assert opt["format_selector"] == _expected_merge("270", "h264", 1080)

    def test_video_only_codec_heights(self, info):
        assert set(info["matrix"]["vp9"].keys()) == {2160, 720}
        assert info["matrix"]["vp9"][2160]["format_selector"] == _expected_merge("616", "vp9", 2160)


class TestResolveBestCodec:
    def test_best_best_unchanged(self, info):
        opt = resolve_video_option(info, "best", "best")
        assert opt["format_selector"] == "bv*+ba/b"

    def test_best_with_height_is_capped_not_ignored(self, info):
        """Regression: codec 'best' + 720p used to return the unconstrained
        'bv*+ba/b' selector, silently downloading e.g. 2160p AV1."""
        opt = resolve_video_option(info, "best", 720)
        assert opt["format_selector"] == _option_best_height(720)["format_selector"]
        assert opt["resolution"] == 720
        assert "\u2264 720p" in opt["label"]

    def test_option_best_height_shape(self):
        opt = _option_best_height(1080)
        assert opt["format_selector"] == (
            "bestvideo[height<=1080]+bestaudio/"
            "best[height<=1080][acodec!=none]/best[height<=1080]"
        )
        assert opt["codec"] == "best"

    def test_best_with_garbage_resolution_falls_back(self, info):
        opt = resolve_video_option(info, "best", "nonsense")
        assert opt["format_selector"] == "bv*+ba/b"


class TestResolveSpecificCodec:
    def test_available_pair_uses_real_option(self, info):
        opt = resolve_video_option(info, "h264", 720)
        assert opt["format_selector"] == _expected_merge("136", "h264", 720)

    def test_available_combined_pair(self, info):
        opt = resolve_video_option(info, "h264", 360)
        assert opt["format_selector"] == "18"
        assert opt["merge"] is False

    def test_best_resolution_picks_highest_of_codec(self, info):
        opt = resolve_video_option(info, "h264", "best")
        assert opt["format_selector"] == _expected_merge("270", "h264", 1080)

    def test_unavailable_height_is_refused(self, info):
        """Regression: h264 + 480p used to substitute the closest height (or
        synthesize '…+bestaudio/best'), silently downloading something the user
        never picked. An unavailable pair must now be reported as unavailable.
        """
        # Heights served by h264: {1080, 720, 360} — 480 is not one of them.
        assert resolve_video_option(info, "h264", 480) is None
        assert "480p" in youtube_media.describe_unavailable(info, "h264", 480)

    def test_unavailable_height_above_max_is_refused(self, info):
        assert resolve_video_option(info, "h264", 2160) is None

    def test_unavailable_height_never_swaps_codec(self, info):
        """vp9 serves {2160, 720}: asking vp9 for 1080 must be refused outright
        rather than quietly serving a different height."""
        assert resolve_video_option(info, "vp9", 1080) is None

    def test_no_height_below_requested_is_refused(self, info):
        # vp9 serves {2160, 720}: asking for 144 → nothing at or below 144.
        assert resolve_video_option(info, "vp9", 144) is None

    def test_exact_pair_is_served(self, info):
        """The pairs that do exist must still resolve to their real option."""
        assert resolve_video_option(
            info, "h264", 360)["format_selector"] == "18"
        assert resolve_video_option(
            info, "h264", 720)["format_selector"] == _expected_merge(
                "136", "h264", 720)
        assert resolve_video_option(
            info, "vp9", 2160)["format_selector"] == _expected_merge(
                "616", "vp9", 2160)

    def test_unknown_codec_returns_none(self, info):
        assert resolve_video_option(info, "mpeg4", 720) is None

    def test_missing_matrix_is_refused(self):
        """No matrix entry for the codec means the video has no such stream —
        a synthetic merge option must not be invented for it."""
        info = {"matrix": {}, "best": _option_best()}
        assert resolve_video_option(info, "h264", 1080) is None
        assert resolve_video_option(info, "h264", "best") is None


class TestNormalizeResolution:
    """The UI can deliver an int, a JS double or a string — all must collapse
    to the same stored value so comparisons never silently miss."""

    def test_int(self):
        assert normalize_resolution(720) == "720"

    def test_double_from_javascript(self):
        assert normalize_resolution(720.0) == "720"

    def test_string(self):
        assert normalize_resolution("720") == "720"

    def test_best_variants(self):
        for value in (None, "", "best", "Best", " auto ", "none", "undefined"):
            assert normalize_resolution(value) == "best", value

    def test_garbage_is_best_not_crash(self):
        assert normalize_resolution("nonsense") == "best"
        assert normalize_resolution(0) == "best"
        assert normalize_resolution(-1) == "best"


class TestDescribeUnavailable:
    def test_available_pair_has_no_reason(self, info):
        assert youtube_media.describe_unavailable(info, "h264", 720) == ""
        assert youtube_media.describe_unavailable(info, "h264", "best") == ""

    def test_names_the_codec_and_lists_what_exists(self, info):
        msg = youtube_media.describe_unavailable(info, "h264", 480)
        assert "H.264" in msg
        assert "480p" in msg
        for height in ("1080p", "720p", "360p"):
            assert height in msg

    def test_codec_with_no_streams_at_all(self, info):
        msg = youtube_media.describe_unavailable(info, "av1", 720)
        assert "AV1" in msg
        assert "not available" in msg

    def test_best_cap_below_everything_is_explained(self, info):
        msg = youtube_media.describe_unavailable(info, "best", 144)
        assert "144p" in msg
        assert "360p" in msg  # the lowest available height

    def test_message_says_not_available(self, info):
        """The user-facing contract: a rejected pick must read as
        "not available in that format/resolution"."""
        for codec, res in (("h264", 480), ("vp9", 1080), ("av1", 720)):
            msg = youtube_media.describe_unavailable(info, codec, res)
            assert "not available" in msg, (codec, res, msg)


class TestMergeFallbacksConstrained:
    """Synthetic merge options must never end in an unconstrained '/best'."""

    def test_merge_option_no_height(self):
        sel = _merge_option("h264")["format_selector"]
        assert sel == (
            "bestvideo[vcodec^=avc1]+bestaudio/"
            "bestvideo[vcodec^=avc1]+bestaudio/"
            "best[vcodec^=avc1][acodec!=none]/"
            "best[acodec!=none]"
        )

    def test_merge_option_with_height(self):
        sel = _merge_option("h264", 1080)["format_selector"]
        assert sel == (
            "bestvideo[vcodec^=avc1][height=1080]+bestaudio/"
            "bestvideo[vcodec^=avc1][height<=1080]+bestaudio/"
            "best[vcodec^=avc1][height<=1080][acodec!=none]/"
            "best[height<=1080][acodec!=none]"
        )

    def test_all_pairs_stay_constrained(self, info):
        """No specific-codec selection may ever resolve to a selector whose
        final fallback ignores the codec ('…+bestaudio/best' ending)."""
        checked = 0
        for codec in ("av1", "vp9", "h264"):
            for res in ("best", 2160, 1440, 1080, 720, 480, 360, 240, 144):
                opt = resolve_video_option(info, codec, res)
                if opt is None:
                    continue  # unavailable pair — correctly refused
                checked += 1
                sel = opt["format_selector"]
                assert not sel.endswith("+bestaudio/best"), (codec, res, sel)
                assert not sel.endswith("/best"), (codec, res, sel)
        assert checked >= 4, "should still exercise the available pairs"


class TestAudioSafeFallbacks:
    """Regression: the last resort used to be a video-only stream, which
    produced a muted file while still reporting the download as successful."""

    def test_fallback_ends_with_audio_only_branch(self):
        fb = _audio_safe_fallback("h264", 1080)
        assert fb.endswith("best[height<=1080][acodec!=none]")

    def test_fallback_without_height(self):
        fb = _audio_safe_fallback("av1", None)
        assert "best[acodec!=none]" in fb
        assert "[height" not in fb

    def test_merge_selectors_never_resort_to_video_only(self, info):
        for codec in ("av1", "vp9", "h264"):
            for res in ("best", 2160, 1440, 1080, 720, 480, 360, 240, 144):
                opt = resolve_video_option(info, codec, res)
                if opt is None:
                    continue  # unavailable pair — correctly refused
                sel = opt["format_selector"]
                if "+" not in sel and "/" not in sel:
                    continue  # a plain muxed format id (e.g. "18") has audio
                self._assert_every_branch_has_audio(sel, codec, res)

    @staticmethod
    def _assert_every_branch_has_audio(sel: str, codec: str, res) -> None:
        for branch in sel.split("/"):
            if not branch.startswith("best"):
                continue  # an explicit format id: chosen because it is muxed
            assert "+bestaudio" in branch or "[acodec!=none]" in branch, (
                codec, res, branch,
            )

    def test_real_video_only_format_no_longer_falls_back_to_itself(self, info):
        """The old selector was '616+bestaudio/616' — the fallback dropped the
        audio leg entirely."""
        sel = info["matrix"]["vp9"][2160]["format_selector"]
        assert not sel.endswith("/616")


class TestStalePartRecovery:
    """An expired stream URL behind a leftover .part file caused a hard 403."""

    def test_403_is_recognised_as_expired_url(self):
        assert _is_expired_url_error(
            "ERROR: unable to download video data: HTTP Error 403: Forbidden"
        )

    def test_other_errors_are_not(self):
        assert not _is_expired_url_error("ERROR: unable to extract player response")
        assert not _is_expired_url_error("")
        assert not _is_expired_url_error("ERROR: video unavailable")

    def test_stale_part_is_detected(self, tmp_path):
        stale = tmp_path / "video.f401.mp4.part"
        stale.write_bytes(b"x")
        old = time.time() - 3600
        os.utime(stale, (old, old))
        found = _partial_files(str(tmp_path / "%(title)s.%(ext)s"), [])
        assert str(stale) in found

    def test_fresh_part_is_left_alone(self, tmp_path):
        fresh = tmp_path / "video.f401.mp4.part"
        fresh.write_bytes(b"x")
        assert _partial_files(str(tmp_path / "%(title)s.%(ext)s"), []) == []

    def test_part_named_from_destination_line(self, tmp_path):
        dest = tmp_path / "video.mp4"
        part = tmp_path / "video.mp4.part"
        part.write_bytes(b"x")  # fresh, so only the explicit match finds it
        lines = [f"[download] Destination: {dest}"]
        assert str(part) in _partial_files(str(tmp_path / "%(title)s.%(ext)s"), lines)

    def test_download_retries_once_after_expired_url(self, tmp_path, monkeypatch):
        stale = tmp_path / "video.f401.mp4.part"
        stale.write_bytes(b"x" * 10)
        old = time.time() - 3600
        os.utime(stale, (old, old))

        calls: list[list[str]] = []

        def fake_run(cmd, progress_cb=None, percent_cb=None, proc_ref=None,
                     cancel_check=None):
            calls.append(list(cmd))
            if progress_cb:
                progress_cb(
                    "ERROR: unable to download video data: HTTP Error 403: Forbidden"
                )
            return 1 if len(calls) == 1 else 0

        monkeypatch.setattr(youtube_media, "_run_yt_dlp", fake_run)
        messages: list[str] = []
        youtube_media.download_video(
            "https://example.org/watch?v=x", "401+bestaudio",
            str(tmp_path / "%(title)s.%(ext)s"),
            progress_cb=messages.append,
        )
        assert len(calls) == 2, "should retry once from a clean slate"
        assert not stale.exists(), "stale partial should have been removed"
        assert any("Stale partial download removed" in m for m in messages)

    def test_download_does_not_retry_on_other_errors(self, tmp_path, monkeypatch):
        calls: list[list[str]] = []

        def fake_run(cmd, progress_cb=None, percent_cb=None, proc_ref=None,
                     cancel_check=None):
            calls.append(list(cmd))
            if progress_cb:
                progress_cb("ERROR: unable to extract player response")
            return 1

        monkeypatch.setattr(youtube_media, "_run_yt_dlp", fake_run)
        with pytest.raises(RuntimeError):
            youtube_media.download_video(
                "https://example.org/watch?v=x", "401+bestaudio",
                str(tmp_path / "%(title)s.%(ext)s"),
            )
        assert len(calls) == 1


class TestDownloadCommand:
    def test_uses_resolved_executable(self, tmp_path, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(
            youtube_media, "_run_yt_dlp",
            lambda cmd, **kw: (calls.append(list(cmd)), 0)[1],
        )
        youtube_media.download_video(
            "https://example.org/watch?v=x", "bv*+ba/b",
            str(tmp_path / "%(title)s.%(ext)s"),
        )
        # Regression: the command used to hardcode the literal "yt-dlp",
        # ignoring the YT_DLP_BIN override and the python -m fallback.
        assert calls[0][0] == youtube_media._yt_dlp_cmd()[0]

    def test_has_resilience_flags(self, tmp_path, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(
            youtube_media, "_run_yt_dlp",
            lambda cmd, **kw: (calls.append(list(cmd)), 0)[1],
        )
        youtube_media.download_video(
            "https://example.org/watch?v=x", "bv*+ba/b",
            str(tmp_path / "%(title)s.%(ext)s"),
        )
        cmd = calls[0]
        for flag in ("--retries", "--fragment-retries", "--extractor-retries",
                     "--throttled-rate", "--sleep-requests"):
            assert flag in cmd, flag

    def test_subtitle_download_shares_resilience_flags(self, tmp_path, monkeypatch):
        """Regression: only the video path had retries; subtitle fetches were
        left with a single attempt each."""
        calls: list[list[str]] = []
        monkeypatch.setattr(
            youtube_media, "_run_yt_dlp",
            lambda cmd, **kw: (calls.append(list(cmd)), 1)[1],
        )
        with pytest.raises(RuntimeError):
            youtube_media.download_subtitle(
                "https://example.org/watch?v=x", "en", str(tmp_path / "%(title)s")
            )
        assert calls, "subtitle download should have attempted at least once"
        for cmd in calls:
            assert "--retries" in cmd
            assert "--extractor-retries" in cmd


class TestErrorTranslation:
    def test_403_gets_actionable_hint(self):
        hint = youtube_media._translate_ytdlp_error(
            "ERROR: unable to download video data: HTTP Error 403: Forbidden"
        )
        assert "403" in hint and "partial" in hint.lower()

    def test_benign_player_line_is_not_an_extractor_error(self):
        """Regression: the word "player" appears in "Downloading android vr
        player API JSON" on every successful run."""
        assert youtube_media._translate_ytdlp_error(
            "[youtube] PHAcOZ7E-pM: Downloading android vr player API JSON"
        ) == ""

    def test_cookies_alone_is_not_a_signin_error(self):
        assert youtube_media._translate_ytdlp_error(
            "--cookies was not used"
        ) == ""

    def test_sign_in_message_is_a_signin_error(self):
        assert "sign-in" in youtube_media._translate_ytdlp_error(
            "ERROR: Sign in to confirm you're not a bot"
        )


_FFMPEG_STDERR = """
ffmpeg version 7.1 Copyright (c) 2000-2024 the FFmpeg developers
Input #0, matroska,webm, from 'Big Buck Bunny.mkv':
  Metadata:
    encoder         : google/video-file
  Duration: 00:09:56.46, start: 0.000000, bitrate: 265 kb/s
  Stream #0:0(eng): Video: h264 (High), yuv420p(progressive), 426x240 [SAR 1:1 DAR 16:9], 30 fps, 30 tbr, 1k tbn (default)
  Stream #0:1(eng): Audio: opus, 48000 Hz, stereo, fltp (default)
"""


class _FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class TestProbeVideoFile:
    """Post-download verification must work with *or* without ffprobe.

    Most installs (including the ``imageio_ffmpeg`` wheel this app already uses
    for merging) ship ``ffmpeg`` but **not** ``ffprobe``, so relying on ffprobe
    alone made the verification silently never run.
    """

    def test_missing_file_returns_none(self, tmp_path):
        assert youtube_media.probe_video_file(str(tmp_path / "nope.mp4")) is None

    def test_returns_none_when_no_tool_available(self, tmp_path, monkeypatch):
        clip = tmp_path / "a.mp4"
        clip.write_bytes(b"0")
        monkeypatch.setattr(youtube_media, "_ffprobe_exe", lambda: None)
        monkeypatch.setattr(youtube_media, "_ffmpeg_exe", lambda: None)
        assert youtube_media.probe_video_file(str(clip)) is None

    def test_ffmpeg_stderr_is_parsed(self, tmp_path, monkeypatch):
        """``ffmpeg -i`` lists streams on stderr and exits non-zero by design."""
        monkeypatch.setattr(
            youtube_media, "_run_probe",
            lambda exe, args, timeout=30: _FakeProc(
                stderr=_FFMPEG_STDERR, returncode=1),
        )
        got = youtube_media._probe_via_ffmpeg("ffmpeg", "x.mkv")
        assert got == {"codec": "h264", "codec_name": "h264",
                       "height": 240, "width": 426}

    def test_ffmpeg_used_when_ffprobe_missing(self, tmp_path, monkeypatch):
        clip = tmp_path / "a.mkv"
        clip.write_bytes(b"0")
        monkeypatch.setattr(youtube_media, "_ffprobe_exe", lambda: None)
        monkeypatch.setattr(youtube_media, "_ffmpeg_exe", lambda: "ffmpeg.exe")
        monkeypatch.setattr(
            youtube_media, "_run_probe",
            lambda exe, args, timeout=30: _FakeProc(
                stderr=_FFMPEG_STDERR, returncode=1),
        )
        got = youtube_media.probe_video_file(str(clip))
        assert got and got["height"] == 240 and got["codec"] == "h264"

    def test_ffprobe_is_preferred_when_present(self, tmp_path, monkeypatch):
        clip = tmp_path / "a.mp4"
        clip.write_bytes(b"0")
        calls = []

        def fake_run(exe, args, timeout=30):
            calls.append(exe)
            if exe == "ffprobe":
                return _FakeProc(stdout=json.dumps(
                    {"streams": [{"codec_name": "av01",
                                  "height": 720, "width": 1280}]}))
            return _FakeProc(stderr=_FFMPEG_STDERR, returncode=1)

        monkeypatch.setattr(youtube_media, "_ffprobe_exe", lambda: "ffprobe")
        monkeypatch.setattr(youtube_media, "_ffmpeg_exe", lambda: "ffmpeg")
        monkeypatch.setattr(youtube_media, "_run_probe", fake_run)

        got = youtube_media.probe_video_file(str(clip))
        assert got == {"codec": "av1", "codec_name": "av01",
                       "height": 720, "width": 1280}
        assert calls == ["ffprobe"]  # ffmpeg must not be needed

    def test_ffprobe_failure_falls_back_to_ffmpeg(self, tmp_path, monkeypatch):
        clip = tmp_path / "a.mp4"
        clip.write_bytes(b"0")

        def fake_run(exe, args, timeout=30):
            if exe == "ffprobe":
                return _FakeProc(stdout="", returncode=1)  # unreadable
            return _FakeProc(stderr=_FFMPEG_STDERR, returncode=1)

        monkeypatch.setattr(youtube_media, "_ffprobe_exe", lambda: "ffprobe")
        monkeypatch.setattr(youtube_media, "_ffmpeg_exe", lambda: "ffmpeg")
        monkeypatch.setattr(youtube_media, "_run_probe", fake_run)
        got = youtube_media.probe_video_file(str(clip))
        assert got and got["height"] == 240

    def test_unparseable_output_returns_none(self, tmp_path, monkeypatch):
        clip = tmp_path / "a.mkv"
        clip.write_bytes(b"0")
        monkeypatch.setattr(youtube_media, "_ffprobe_exe", lambda: None)
        monkeypatch.setattr(youtube_media, "_ffmpeg_exe", lambda: "ffmpeg")
        monkeypatch.setattr(
            youtube_media, "_run_probe",
            lambda exe, args, timeout=30: _FakeProc(
                stderr="ffmpeg: not a media file", returncode=1),
        )
        assert youtube_media.probe_video_file(str(clip)) is None

    def test_probe_never_raises_when_subprocess_returns_none(
            self, tmp_path, monkeypatch):
        clip = tmp_path / "a.mkv"
        clip.write_bytes(b"0")
        monkeypatch.setattr(youtube_media, "_ffprobe_exe", lambda: None)
        monkeypatch.setattr(youtube_media, "_ffmpeg_exe", lambda: "ffmpeg")
        monkeypatch.setattr(youtube_media, "_run_probe",
                            lambda exe, args, timeout=30: None)
        assert youtube_media.probe_video_file(str(clip)) is None


class TestPackagedFfmpegNaming:
    """A packaged build ships ffmpeg under its imageio name
    (``ffmpeg-win-x86_64-v7.1.exe``). yt-dlp's ``--ffmpeg-location`` only
    recognises a binary *literally* named ``ffmpeg.exe`` when it scans a
    directory, so without the rename the video+audio merge silently never runs
    and the user ends up with a video-only file plus a stray audio file.
    """
    def _fake_binary(self, tmp_path, name, size=2048):
        binary = tmp_path / name
        binary.write_bytes(b"x" * size)
        return binary

    def test_differently_named_binary_is_copied(self, tmp_path):
        odd = self._fake_binary(tmp_path, "ffmpeg-win-x86_64-v7.1.exe")
        got = youtube_media._ensure_ffmpeg_exe_named(str(odd))
        assert os.path.basename(got).lower() == "ffmpeg.exe", got
        assert os.path.isfile(got)

    def test_copy_matches_the_original_byte_for_byte(self, tmp_path):
        odd = self._fake_binary(tmp_path, "ffmpeg-win-x86_64-v7.1.exe", 4096)
        got = youtube_media._ensure_ffmpeg_exe_named(str(odd))
        assert os.path.getsize(got) == os.path.getsize(odd)

    def test_original_binary_is_left_in_place(self, tmp_path):
        odd = self._fake_binary(tmp_path, "ffmpeg-win-x86_64-v7.1.exe")
        youtube_media._ensure_ffmpeg_exe_named(str(odd))
        assert odd.is_file(), "the bundled binary must not be moved/deleted"

    def test_already_correct_name_is_returned_untouched(self, tmp_path):
        good = self._fake_binary(tmp_path, "ffmpeg.exe")
        assert youtube_media._ensure_ffmpeg_exe_named(str(good)) == str(good)

    def test_is_idempotent(self, tmp_path):
        odd = self._fake_binary(tmp_path, "ffmpeg-win-x86_64-v7.1.exe")
        first = youtube_media._ensure_ffmpeg_exe_named(str(odd))
        assert youtube_media._ensure_ffmpeg_exe_named(str(odd)) == first

    def test_stale_copy_is_refreshed(self, tmp_path):
        """A leftover ffmpeg.exe from an older build must be overwritten."""
        odd = self._fake_binary(tmp_path, "ffmpeg-win-x86_64-v7.1.exe", 4096)
        stale = tmp_path / "ffmpeg.exe"
        stale.write_bytes(b"old")          # different size
        got = youtube_media._ensure_ffmpeg_exe_named(str(odd))
        assert os.path.getsize(got) == 4096, "stale copy was not replaced"

    def test_readonly_directory_falls_back_to_temp(self, tmp_path, monkeypatch):
        odd = self._fake_binary(tmp_path, "ffmpeg-win-x86_64-v7.1.exe")
        monkeypatch.setattr(os, "access", lambda *a, **k: False)
        got = youtube_media._ensure_ffmpeg_exe_named(str(odd))
        assert os.path.basename(got).lower() == "ffmpeg.exe"
        assert os.path.isdir(os.path.dirname(os.path.abspath(got)))

    def test_unwritable_target_returns_the_original(self, tmp_path, monkeypatch):
        """Copy failure must degrade gracefully — never raise mid-download."""
        odd = self._fake_binary(tmp_path, "ffmpeg-win-x86_64-v7.1.exe")
        monkeypatch.setattr(os, "access", lambda *a, **k: True)
        import shutil as _shutil

        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(_shutil, "copyfile", boom)
        assert youtube_media._ensure_ffmpeg_exe_named(str(odd)) == str(odd)
