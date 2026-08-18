"""Tests for src/local_asr.py — _split_text and _segment_to_cues splitting."""
from __future__ import annotations

from src.local_asr import _parse_sensevoice_output, _segment_to_cues, _split_text
from src.srt_io import Cue


class TestParseSensevoiceOutput:
    """SenseVoice tag groups must be stripped by default (regression guard):

    The default ASR path now strips the `<|zh|><|ANGRY|><|BGM|><|withitn|>`
    tag group before cues are built, so those tokens can never reach the SRT.
    """

    def test_strips_tag_group_by_default(self):
        text, lang = _parse_sensevoice_output(
            "<|zh|><|ANGRY|><|BGM|><|withitn|>你一定也化过妆", keep_tags=False
        )
        assert lang == "zh"
        assert "<|" not in text
        assert "你一定也化过妆" in text

    def test_strips_all_tag_forms(self):
        text, _ = _parse_sensevoice_output(
            "<|EN|><|NEUTRAL|><|Speech|><|withitn|>Is this worth it?", keep_tags=False
        )
        assert "<|" not in text
        assert "<" not in text
        assert "Is this worth it?" in text

    def test_keeps_tags_only_when_requested(self):
        text, _ = _parse_sensevoice_output(
            "<|zh|><|ANGRY|><|BGM|><|withitn|>hello", keep_tags=True
        )
        # Opt-in tag-keeping still leaves the control tokens in the text so the
        # translation step can use the emotion for register awareness.
        assert "ANGRY" in text


class TestSplitText:
    def test_short_text_not_split(self):
        assert _split_text("hello world", 48) == ["hello world"]

    def test_empty_text(self):
        assert _split_text("", 48) == []

    def test_whitespace_only(self):
        assert _split_text("   ", 48) == []

    def test_long_cjk_split_under_limit(self):
        text = "这是一段比较长的中文文本用来测试字幕切分功能是否正常运作" * 3
        parts = _split_text(text, 20)
        assert len(parts) > 1
        for part in parts:
            assert len(part.replace(" ", "")) <= 60

    def test_sentence_final_punctuation_preferred(self):
        text = "第一句话。第二句话。第三句话。"
        # max_chars small enough to force a split.
        parts = _split_text(text, 12)
        assert len(parts) >= 2
        joined = "。".join(p for p in parts if p)
        assert "第一句话" in joined
        assert "第二句话" in joined

    def test_clause_punctuation_used_when_necessary(self):
        text = "苹果，香蕉，橘子，葡萄，西瓜，芒果，" * 4
        parts = _split_text(text, 12)
        assert len(parts) > 1

    def test_proportional_fallback_preserves_text(self):
        text = "abcdefghijklmnopqrstuvwxyz"
        parts = _split_text(text, 10)
        assert len(parts) == 3
        assert "".join(parts) == text


class TestSegmentToCues:
    def test_empty_text_returns_empty(self):
        assert _segment_to_cues("", 0.0, 5.0, 48, 3.0) == []

    def test_whitespace_only_returns_empty(self):
        assert _segment_to_cues("   ", 0.0, 5.0, 48, 3.0) == []

    def test_timestamps_within_bounds(self):
        text = "第一句话。第二句话。第三句话。第四句话。"
        cues = _segment_to_cues(text, 10.0, 20.0, 20, 3.0)
        assert len(cues) >= 1
        for cue in cues:
            assert cue.start >= 10.0 - 0.001
            assert cue.end <= 20.0 + 0.001
            assert cue.end > cue.start

    def test_last_cue_ends_at_segment_end(self):
        text = "a。b。c。"
        cues = _segment_to_cues(text, 5.0, 10.0, 10, 3.0)
        if cues:
            assert abs(cues[-1].end - 10.0) < 0.02

    def test_short_text_single_cue(self):
        cues = _segment_to_cues("你好", 1.0, 2.0, 48, 3.0)
        assert len(cues) == 1
        assert cues[0].text == "你好"

    def test_all_cues_have_text(self):
        text = "苹果，香蕉，橘子，葡萄，西瓜，芒果，" * 3
        cues = _segment_to_cues(text, 0.0, 10.0, 15, 3.0)
        assert all(c.text.strip() for c in cues)

    def test_proportional_splitting(self):
        text = "这是一句很长的话" + "。这是另外一句很长的话" * 5
        cues = _segment_to_cues(text, 0.0, 10.0, 20, 3.0)
        assert len(cues) >= 1
class TestIncompleteTranscriptWarning:
    """The ASR run must warn when the last cue ends well before the media ends
    (a truncated transcript — see SUBTITLE_QUALITY_REPORT §2.7)."""

    def test_covers_whole_media_no_warning(self, capsys):
        from src.local_asr import maybe_warn_incomplete

        maybe_warn_incomplete([Cue(0.0, 300.0, "text")], 300.0)
        assert "may be incomplete" not in capsys.readouterr().out

    def test_short_tail_no_warning(self, capsys):
        from src.local_asr import maybe_warn_incomplete

        # 10s uncovered on a 260s file is a plausible trailing pause.
        maybe_warn_incomplete([Cue(0.0, 250.0, "text")], 260.0)
        assert "may be incomplete" not in capsys.readouterr().out

    def test_long_tail_warns(self, capsys):
        from src.local_asr import maybe_warn_incomplete

        # Stops at 2:15 while media is 10 minutes — truncated run.
        maybe_warn_incomplete([Cue(0.0, 135.0, "text")], 600.0)
        out = capsys.readouterr().out
        assert "may be incomplete" in out
        assert "600.0s" in out

    def test_empty_cues_no_warning(self, capsys):
        from src.local_asr import maybe_warn_incomplete

        maybe_warn_incomplete([], 100.0)
        assert "may be incomplete" not in capsys.readouterr().out
