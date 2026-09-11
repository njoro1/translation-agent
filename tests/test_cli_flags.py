"""Tests for the CLI flag wiring added by the improvements pass."""
from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

import translate


def _nargs(**overrides) -> argparse.Namespace:
    """A minimal args namespace with the fields the CLIs access."""
    base = {
        "json_progress": False,
        "ass_font": None,
        "ass_fontsize": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestJsonProgress:
    def test_disabled_emits_nothing(self, capsys):
        translate._json_progress(_nargs(), "translate", 0, 10)
        captured = capsys.readouterr()
        assert captured.out.strip() == ""

    def test_enabled_emits_json_line(self, capsys):
        translate._json_progress(_nargs(json_progress=True), "translate", 4, 10)
        captured = capsys.readouterr()
        assert captured.out.strip() == '{"type":"progress","stage":"translate","done":4,"total":10}'

    def test_flag_present_in_parser(self):
        parsed = translate._parse_args(["--json-progress"])
        assert parsed.json_progress is True

    def test_ass_font_flags_present_in_parser(self):
        parsed = translate._parse_args(["--ass-font", "Noto Sans", "--ass-fontsize", "60"])
        assert parsed.ass_font == "Noto Sans"
        assert parsed.ass_fontsize == 60

    def test_source_lang_flag_present_in_parser(self):
        parsed = translate._parse_args(["--source-lang", "ja"])
        assert parsed.source_lang == "ja"
        # Default is unset (None) so behavior is unchanged without the flag.
        assert translate._parse_args([]).source_lang is None


class TestUntranslatedMarkerPreserved:
    """The final output sanitizer must never strip or alter [untranslated]."""

    def test_sensevoice_strip_preserves_marker(self):
        from src.translate import _strip_sensevoice_tag

        assert _strip_sensevoice_tag("[untranslated]") == "[untranslated]"

    def test_lines_ending_in_marker_not_touched(self):
        from src.translate import _strip_sensevoice_tag

        assert _strip_sensevoice_tag("[untranslated]") == "[untranslated]"
        assert _strip_sensevoice_tag("some text") == "some text"

class TestCliVideoSelector:
    """``--download-video <codec>`` must honour the codec, or refuse.

    Same bug class as the GUI dropdowns: a silent fallback to an unconstrained
    ``/best`` selector downloads a *different* codec than the one requested.
    """
    @staticmethod
    def _info() -> dict:
        from src import youtube_media
        formats = [
            {"format_id": "140", "ext": "m4a", "height": None, "vcodec": "none",
             "acodec": "mp4a.40.2", "tbr": 128, "filesize": 4_000_000},
            {"format_id": "401", "ext": "mp4", "height": 2160,
             "vcodec": "av01.0.13M.10", "acodec": "none", "tbr": 10000,
             "filesize": 120_000_000, "fps": 30},
            {"format_id": "315", "ext": "webm", "height": 2160, "vcodec": "vp9",
             "acodec": "none", "tbr": 12000, "filesize": 150_000_000,
             "fps": 30},
            {"format_id": "137", "ext": "mp4", "height": 1080,
             "vcodec": "avc1.640028", "acodec": "none", "tbr": 4500,
             "filesize": 40_000_000, "fps": 30},
        ]
        codecs, res, matrix, best = youtube_media._build_matrix(formats)
        return {"matrix": matrix, "best": best,
                "codecs": codecs, "resolutions": res}

    def test_best_uses_the_unconstrained_selector(self):
        assert translate._video_selector_for("best", self._info()) == "bv*+ba/b"

    @pytest.mark.parametrize(
        "codec,prefix",
        [("h264", "137"), ("vp9", "315"), ("av1", "401")],
    )
    def test_named_codec_is_pinned_to_that_codec(self, codec, prefix):
        selector = translate._video_selector_for(codec, self._info())
        assert selector.startswith(prefix), selector

    def test_h264_does_not_borrow_the_2160p_av1_stream(self):
        """The regression: h264 tops out at 1080p here, so asking for h264 must
        never yield the 2160p AV1/VP9 stream."""
        selector = translate._video_selector_for("h264", self._info())
        assert "401" not in selector and "315" not in selector, selector
        assert "avc1" in selector, selector

    def test_missing_codec_raises_with_an_explanation(self):
        info = self._info()
        info["matrix"].pop("h264")
        with pytest.raises(RuntimeError) as excinfo:
            translate._video_selector_for("h264", info)
        assert "not available" in str(excinfo.value).lower(), excinfo.value

    def test_never_falls_back_to_best_for_a_named_codec(self):
        info = self._info()
        info["matrix"].pop("h264")
        try:
            selector = translate._video_selector_for("h264", info)
        except RuntimeError:
            return
        pytest.fail(f"expected a refusal, got {selector!r}")

    @pytest.mark.parametrize("codec", ["best", "av1", "vp9", "h264"])
    def test_every_cli_choice_resolves(self, codec):
        """The flag's ``choices`` are the contract the resolver must honour."""
        assert translate._video_selector_for(codec, self._info())
