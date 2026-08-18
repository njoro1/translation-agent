"""Tests for src/subtitle_quality.py — CPS, duration, char count, lines."""
from __future__ import annotations

import json

from src.srt_io import Cue
from src.subtitle_quality import analyze_cues, build_report


def _mk(text, start, end):
    return Cue(start=start, end=end, text=text)


class TestCpsThresholds:
    def test_cps_error(self):
        # 60 chars over 2s = 30 CPS >= 22 -> error
        cue = _mk("x" * 60, 0.0, 2.0)
        issues = analyze_cues([cue])
        assert len(issues) == 1
        assert "cps_error" in issues[0].issues

    def test_cps_warning(self):
        # 40 chars over 2s = 20 CPS (>=18, <22) -> warning
        cue = _mk("x" * 40, 0.0, 2.0)
        issues = analyze_cues([cue])
        assert "cps_warning" in issues[0].issues
        assert "cps_error" not in issues[0].issues

    def test_cps_ok(self):
        cue = _mk("short", 0.0, 5.0)
        issues = analyze_cues([cue])
        assert issues == []  # no issues at all for a clean cue


class TestOverlongCue:
    def test_too_long_error(self):
        cue = _mk("text", 0.0, 9.0)
        issues = analyze_cues([cue])
        assert "too_long_error" in issues[0].issues

    def test_too_long_warning(self):
        cue = _mk("text", 0.0, 6.5)
        issues = analyze_cues([cue])
        assert "too_long_warning" in issues[0].issues
        assert "too_long_error" not in issues[0].issues


class TestTooShortCue:
    def test_too_short_error(self):
        cue = _mk("hi", 0.0, 0.4)
        issues = analyze_cues([cue])
        assert "too_short_error" in issues[0].issues

    def test_too_short_warning(self):
        cue = _mk("hi", 0.0, 0.7)
        issues = analyze_cues([cue])
        assert "too_short_warning" in issues[0].issues
        assert "too_short_error" not in issues[0].issues


class TestLineCount:
    def test_lines_error(self):
        cue = _mk("a\nb\nc\nd", 0.0, 5.0)
        issues = analyze_cues([cue])
        assert "lines_error" in issues[0].issues

    def test_lines_warning(self):
        cue = _mk("a\nb", 0.0, 5.0)
        issues = analyze_cues([cue])
        assert "lines_warning" in issues[0].issues
        assert "lines_error" not in issues[0].issues


class TestEmptyText:
    def test_empty_text_issue(self):
        cue = _mk("", 0.0, 1.0)
        issues = analyze_cues([cue])
        assert "empty_text" in issues[0].issues

    def test_whitespace_only_has_length(self):
        # Whitespace characters count toward visible length, so whitespace-only
        # text is not flagged as empty_text.
        cue = _mk("   ", 0.0, 1.0)
        issues = analyze_cues([cue])
        assert all("empty_text" not in i.issues for i in issues)


class TestBuildReport:
    def test_empty_cues(self):
        report = build_report([])
        assert report.cue_count == 0
        assert report.warning_count == 0
        assert report.error_count == 0

    def test_counts_issues(self):
        cues = [
            _mk("x" * 60, 0.0, 1.0),
            _mk("good", 0.0, 5.0),
            _mk("", 0.0, 1.0),
        ]
        report = build_report(cues)
        assert report.cue_count == 3
        assert report.empty_count == 1
        assert report.error_count >= 1

    def test_to_json(self):
        report = build_report([])
        data = json.loads(report.to_json())
        assert data["cue_count"] == 0

    def test_to_dict(self):
        assert isinstance(build_report([]).to_dict(), dict)


class TestUntranslatedCount:
    def test_default_zero(self):
        assert build_report([]).untranslated_count == 0
        report = build_report([_mk("ok", 0.0, 1.0)])
        assert report.untranslated_count == 0

    def test_explicit_count_reported(self):
        report = build_report([_mk("ok", 0.0, 1.0)], untranslated_count=3)
        assert report.untranslated_count == 3

    def test_count_in_json(self):
        report = build_report([], untranslated_count=2)
        data = json.loads(report.to_json())
        assert data["untranslated_count"] == 2

    def test_print_summary_mentions_untranslated(self, capsys):
        from src.subtitle_quality import print_summary

        print_summary([_mk("ok", 0.0, 1.0)], untranslated_count=1)
        out = capsys.readouterr().out
        assert "cue(s) untranslated" in out
