"""Tests for the codec-aware YouTube media module (``src/youtube_media.py``).

Focus: the download selector must always honour the codec and resolution the
user picked. Historical bug: an unavailable (codec, height) pair (or codec
"best" + a height) fell back to an unconstrained ``/best`` yt-dlp selector,
silently downloading a completely different codec/resolution than selected.
"""
import pytest

from src.youtube_media import (
    _build_matrix,
    _merge_option,
    _option_best,
    _option_best_height,
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
        assert opt["format_selector"] == "270+bestaudio/270"

    def test_video_only_codec_heights(self, info):
        assert set(info["matrix"]["vp9"].keys()) == {2160, 720}
        assert info["matrix"]["vp9"][2160]["format_selector"] == "616+bestaudio/616"


class TestResolveBestCodec:
    def test_best_best_unchanged(self, info):
        opt = resolve_video_option(info, "best", "best")
        assert opt["format_selector"] == "bv*+ba/b"

    def test_best_with_height_is_capped_not_ignored(self, info):
        """Regression: codec 'best' + 720p used to return the unconstrained
        'bv*+ba/b' selector, silently downloading e.g. 2160p AV1."""
        opt = resolve_video_option(info, "best", 720)
        assert opt["format_selector"] == "bestvideo[height<=720]+bestaudio/best[height<=720]"
        assert opt["resolution"] == 720
        assert "\u2264 720p" in opt["label"]

    def test_option_best_height_shape(self):
        opt = _option_best_height(1080)
        assert opt["format_selector"] == "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        assert opt["codec"] == "best"

    def test_best_with_garbage_resolution_falls_back(self, info):
        opt = resolve_video_option(info, "best", "nonsense")
        assert opt["format_selector"] == "bv*+ba/b"


class TestResolveSpecificCodec:
    def test_available_pair_uses_real_option(self, info):
        opt = resolve_video_option(info, "h264", 720)
        assert opt["format_selector"] == "136+bestaudio/136"

    def test_available_combined_pair(self, info):
        opt = resolve_video_option(info, "h264", 360)
        assert opt["format_selector"] == "18"
        assert opt["merge"] is False

    def test_best_resolution_picks_highest_of_codec(self, info):
        opt = resolve_video_option(info, "h264", "best")
        assert opt["format_selector"] == "270+bestaudio/270"

    def test_unavailable_height_falls_to_closest_lower(self, info):
        """Regression: h264 + 480p used to synthesize
        'bestvideo[vcodec^=avc1][height=480]+bestaudio/best' — the bare '/best'
        fallback downloading any codec at any height."""
        opt = resolve_video_option(info, "h264", 480)
        # Heights served by h264: {1080, 720, 360} → closest ≤ 480 is 360.
        assert opt["format_selector"] == "18"
        assert "closest to 480p" in opt["label"]

    def test_unavailable_height_above_max_falls_to_max(self, info):
        opt = resolve_video_option(info, "h264", 2160)
        assert opt["format_selector"] == "270+bestaudio/270"
        assert "closest to 2160p" in opt["label"]

    def test_unavailable_height_keeps_same_codec(self, info):
        """vp9 serves {2160, 720}: asking for 1080 must give vp9 720, never a
        different codec."""
        opt = resolve_video_option(info, "vp9", 1080)
        assert opt["format_selector"] == "398+bestaudio/398"
        assert opt["codec"] == "vp9"

    def test_no_height_above_requested_uses_smallest(self, info):
        # vp9 serves {2160, 720}: asking for 144 → no height ≤ 144 → smallest
        # available (720).
        opt = resolve_video_option(info, "vp9", 144)
        assert opt["format_selector"] == "398+bestaudio/398"

    def test_unknown_codec_returns_none(self, info):
        assert resolve_video_option(info, "mpeg4", 720) is None

    def test_missing_matrix_constrained_merge(self):
        info = {"matrix": {}, "best": _option_best()}
        opt = resolve_video_option(info, "h264", 1080)
        assert opt is not None
        sel = opt["format_selector"]
        assert "[height=1080]" in sel
        assert "[height<=1080]" in sel
        assert "best[vcodec^=avc1][height<=1080]" in sel


class TestMergeFallbacksConstrained:
    """Synthetic merge options must never end in an unconstrained '/best'."""

    def test_merge_option_no_height(self):
        sel = _merge_option("h264")["format_selector"]
        assert sel == ("bestvideo[vcodec^=avc1]+bestaudio/"
                       "bestvideo[vcodec^=avc1]/best[vcodec^=avc1]")

    def test_merge_option_with_height(self):
        sel = _merge_option("h264", 1080)["format_selector"]
        assert sel == (
            "bestvideo[vcodec^=avc1][height=1080]+bestaudio/"
            "bestvideo[vcodec^=avc1][height<=1080]/"
            "best[vcodec^=avc1][height<=1080]"
        )

    def test_all_pairs_stay_constrained(self, info):
        """No specific-codec selection may ever resolve to a selector whose
        final fallback ignores the codec ('…+bestaudio/best' ending)."""
        for codec in ("av1", "vp9", "h264"):
            for res in ("best", 2160, 1440, 1080, 720, 480, 360, 240, 144):
                opt = resolve_video_option(info, codec, res)
                assert opt is not None, (codec, res)
                sel = opt["format_selector"]
                assert not sel.endswith("+bestaudio/best"), (codec, res, sel)
                assert not sel.endswith("/best"), (codec, res, sel)
