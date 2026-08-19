"""Tests for the src/cjk.py CJK script helpers."""
from __future__ import annotations

from src.cjk import (
    break_cjk,
    char_width,
    contains_cjk,
    detect_cjk_from_cues,
    detect_cjk_language,
    text_width,
)
from src.srt_io import Cue


class TestContainsCjk:
    def test_chinese(self):
        assert contains_cjk("你好世界")

    def test_japanese_kana(self):
        assert contains_cjk("こんにちは")

    def test_korean_hangul(self):
        assert contains_cjk("안녕하세요")

    def test_ascii_only(self):
        assert not contains_cjk("hello world 123")

    def test_empty(self):
        assert not contains_cjk("")


class TestDetectCjkLanguage:
    def test_chinese(self):
        assert detect_cjk_language("你好世界今天天气很好我们走吧") == "zh"

    def test_japanese_mixes_kana_han(self):
        assert detect_cjk_language("こんにちは世界こんばんは今日は暑いです") == "ja"

    def test_korean(self):
        assert detect_cjk_language("안녕하세요 반갑습니다 오늘은 맑습니다") == "ko"

    def test_ascii_returns_default(self):
        assert detect_cjk_language("hello", default="en") == "en"

    def test_ascii_without_default_is_none(self):
        assert detect_cjk_language("hello") is None

    def test_tolerates_english_interleaved(self):
        # Robust to code-switching: an opening English line amid Chinese still
        # resolves to Chinese.
        text = "Hello everyone. 今天我们来聊一个话题。 你好世界。"
        assert detect_cjk_language(text) == "zh"


class TestDetectCjkFromCues:
    def test_uses_larger_sample(self):
        cues = [
            Cue(0.0, 1.0, "Hello world."),   # English opener
            Cue(1.0, 2.0, "你好世界。"),
            Cue(2.0, 3.0, "今天天气很好。"),
            Cue(3.0, 4.0, "我们走吧。"),
        ]
        assert detect_cjk_from_cues(cues, sample_size=80) == "zh"

    def test_all_english_is_none(self):
        cues = [Cue(0.0, 1.0, "Hello."), Cue(1.0, 2.0, "World.")]
        assert detect_cjk_from_cues(cues) is None


class TestWidth:
    def test_latin_is_one(self):
        assert char_width("a") == 1
        assert text_width("ab") == 2

    def test_fullwidth_is_two(self):
        assert char_width("中") == 2
        assert text_width("中文") == 4

    def test_mixed(self):
        assert text_width("a中") == 3


class TestBreakCjk:
    def test_short_not_broken(self):
        assert break_cjk("你好") == "你好"

    def test_long_splits_with_kinsoku(self):
        text = "这是一个非常非常长的中文句子用来测试自动换行的功能"
        out = break_cjk(text, max_width=20)
        assert "\\N" in out
        for line in out.split("\\N"):
            assert text_width(line) <= 20

    def test_does_not_break_closing_punct(self):
        # The closing period must stay with the preceding text.
        out = break_cjk("今天天气很好。我们出门散步。", max_width=16)
        lines = out.split("\\N")
        assert all(not ln.startswith("。") for ln in lines)
