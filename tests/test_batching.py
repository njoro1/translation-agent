"""Tests for src/batching.py — CJK detection, text weight, chunking."""
from __future__ import annotations

import pytest

from src.batching import chunk_texts, estimate_text_weight, is_cjk_language


class TestIsCjkLanguage:
    def test_zh(self):
        assert is_cjk_language("zh") is True

    def test_zho(self):
        assert is_cjk_language("zho") is True

    def test_chinese(self):
        assert is_cjk_language("chinese") is True

    def test_ja(self):
        assert is_cjk_language("ja") is True

    def test_japanese(self):
        assert is_cjk_language("japanese") is True

    def test_ko(self):
        assert is_cjk_language("ko") is True

    def test_korean(self):
        assert is_cjk_language("korean") is True

    def test_yue(self):
        assert is_cjk_language("yue") is True

    def test_cantonese(self):
        assert is_cjk_language("cantonese") is True

    def test_case_insensitive(self):
        assert is_cjk_language("Japanese") is True
        assert is_cjk_language("CHINESE") is True

    def test_locale_code(self):
        assert is_cjk_language("zh-CN") is True
        assert is_cjk_language("ja-JP") is True

    def test_english(self):
        assert is_cjk_language("en") is False

    def test_english_name(self):
        assert is_cjk_language("english") is False

    def test_none(self):
        assert is_cjk_language(None) is False

    def test_empty(self):
        assert is_cjk_language("") is False


class TestEstimateTextWeight:
    def test_simple(self):
        assert estimate_text_weight("hello", None) == 5

    def test_whitespace_not_counted(self):
        assert estimate_text_weight("  a b c  ", None) == 3

    def test_empty(self):
        assert estimate_text_weight("", None) == 0

    def test_cjk_chars(self):
        assert estimate_text_weight("你好世界", "zh") == 4


class TestChunkTexts:
    def test_empty_input(self):
        assert chunk_texts([], max_items=10, max_total_chars=100) == []

    def test_preserves_order(self):
        texts = ["a", "b", "c", "d", "e"]
        batches = chunk_texts(texts, max_items=2, max_total_chars=1000)
        all_indices = [idx for batch in batches for idx in batch]
        assert all_indices == [0, 1, 2, 3, 4]

    def test_max_items_respected(self):
        texts = ["a"] * 10
        batches = chunk_texts(texts, max_items=3, max_total_chars=1000)
        for batch in batches:
            assert len(batch) <= 3

    def test_max_chars_respected(self):
        texts = ["aaaa", "bbbb", "cccc", "dddd"]
        batches = chunk_texts(texts, max_items=10, max_total_chars=8)
        for batch in batches:
            total = sum(len(texts[idx].replace(" ", "")) for idx in batch)
            if len(batch) > 1:
                assert total <= 8

    def test_single_oversized_item(self):
        texts = ["short", "x" * 200, "short2"]
        batches = chunk_texts(texts, max_items=10, max_total_chars=50)
        oversized_batches = [
            b for b in batches
            if len(b) == 1 and len(texts[b[0]].replace(" ", "")) > 50
        ]
        assert len(oversized_batches) == 1

    def test_no_indices_dropped(self):
        texts = ["a", "b", "c", "d"]
        batches = chunk_texts(texts, max_items=2, max_total_chars=100)
        assert set(idx for batch in batches for idx in batch) == {0, 1, 2, 3}

    def test_invalid_max_items(self):
        with pytest.raises(ValueError):
            chunk_texts(["a"], max_items=0, max_total_chars=100)

    def test_invalid_max_chars(self):
        with pytest.raises(ValueError):
            chunk_texts(["a"], max_items=10, max_total_chars=0)
