"""Tests for the CLI flag wiring added by the improvements pass."""
from __future__ import annotations

import argparse
from types import SimpleNamespace

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


class TestUntranslatedMarkerPreserved:
    """The final output sanitizer must never strip or alter [untranslated]."""

    def test_sensevoice_strip_preserves_marker(self):
        from src.translate import _strip_sensevoice_tag

        assert _strip_sensevoice_tag("[untranslated]") == "[untranslated]"

    def test_lines_ending_in_marker_not_touched(self):
        from src.translate import _strip_sensevoice_tag

        assert _strip_sensevoice_tag("[untranslated]") == "[untranslated]"
        assert _strip_sensevoice_tag("some text") == "some text"