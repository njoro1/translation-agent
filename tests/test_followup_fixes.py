"""Tests for P0 correctness fixes from FOLLOWUP_REVIEW.md.

Covers final-output failure accounting and source-language precedence.
"""
from __future__ import annotations

import translate


class TestIsFailedText:
    def test_empty_or_whitespace_is_failed(self):
        assert translate._is_failed_text("") is True
        assert translate._is_failed_text("   ") is True
        assert translate._is_failed_text(None) is True

    def test_untranslated_marker_is_failed(self):
        assert translate._is_failed_text("[untranslated]") is True
        assert translate._is_failed_text("  [untranslated]  ") is True

    def test_real_text_is_not_failed(self):
        assert translate._is_failed_text("Hello world.") is False


class TestIsKnownSourceCode:
    """P1-1: a specific fetched/ASR source code must not be downgraded."""

    def test_specific_cjk_codes_preserved(self):
        for code in ("zh", "zh-TW", "zh-HK", "zh-Hans", "yue", "ja", "ko"):
            assert translate._is_known_source_code(code) is True

    def test_unknown_auto_und_are_not_specific(self):
        for code in ("auto", "und", "none", "", None):
            assert translate._is_known_source_code(code) is False

    def test_region_code_with_cjk_base(self):
        # Any base-language CJK code is specific (zh-TW -> zh base).
        assert translate._is_known_source_code("zh-TW") is True
        assert translate._is_known_source_code("ko-KR") is True
