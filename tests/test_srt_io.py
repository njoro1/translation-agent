"""Tests for src/srt_io.py — timestamp formatting, parsing, SRT I/O, sanitization."""
from __future__ import annotations

from src.srt_io import (
    Cue,
    _format_timestamp,
    _parse_timestamp,
    read_srt,
    sanitize_filename,
    write_srt,
)


class TestTimestampFormatting:
    def test_zero(self):
        assert _format_timestamp(0.0) == "00:00:00,000"

    def test_simple_seconds(self):
        assert _format_timestamp(5.5) == "00:00:05,500"

    def test_minutes(self):
        assert _format_timestamp(65.0) == "00:01:05,000"

    def test_hours(self):
        assert _format_timestamp(3661.5) == "01:01:01,500"

    def test_negative_clamped_to_zero(self):
        assert _format_timestamp(-10.0) == "00:00:00,000"

    def test_roundtrip(self):
        for val in [0.0, 1.5, 59.999, 3600.0, 3661.123]:
            ts = _format_timestamp(val)
            parsed = _parse_timestamp(ts)
            assert abs(parsed - val) < 0.002


class TestTimestampParsing:
    def test_comma_separator(self):
        assert _parse_timestamp("00:00:05,500") == 5.5

    def test_dot_separator(self):
        assert _parse_timestamp("00:00:05.500") == 5.5

    def test_hours_minutes_seconds(self):
        assert abs(_parse_timestamp("01:02:03,000") - 3723.0) < 0.001


class TestSrtRoundtrip:
    def test_write_read_roundtrip(self, tmp_path):
        cues = [
            Cue(start=1.0, end=3.0, text="Hello world"),
            Cue(start=3.5, end=6.0, text="Second cue"),
            Cue(start=7.0, end=10.5, text="Third"),
        ]
        path = str(tmp_path / "test.srt")
        write_srt(cues, path)
        read_back = read_srt(path)
        assert len(read_back) == 3
        assert read_back[0].text == "Hello world"
        assert abs(read_back[0].start - 1.0) < 0.002
        assert read_back[1].text == "Second cue"
        assert read_back[2].text == "Third"

    def test_multi_line_cue(self, tmp_path):
        path = str(tmp_path / "multi.srt")
        content = "1\n00:00:01,000 --> 00:00:03,000\nLine one\nLine two\n\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        cues = read_srt(path)
        assert len(cues) == 1
        assert "Line one" in cues[0].text
        assert "Line two" in cues[0].text

    def test_bom_tolerance(self, tmp_path):
        path = str(tmp_path / "bom.srt")
        content = "\ufeff1\n00:00:01,000 --> 00:00:02,000\nBOM test\n\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        cues = read_srt(path)
        assert len(cues) == 1
        assert cues[0].text == "BOM test"


class TestSanitizeFilename:
    def test_unsafe_chars_removed(self):
        result = sanitize_filename('file<>:"/\\|?*name')
        assert "<" not in result
        assert result != ""

    def test_long_name_truncated(self):
        result = sanitize_filename("a" * 300)
        assert len(result) <= 180

    def test_empty_returns_default(self):
        assert sanitize_filename("") == "subtitles"

    def test_whitespace_collapsed(self):
        result = sanitize_filename("hello    world")
        assert "  " not in result

    def test_normal_name_preserved(self):
        assert sanitize_filename("My Video Title") == "My Video Title"
