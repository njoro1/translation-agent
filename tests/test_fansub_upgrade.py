"""Tests for the fansub-quality upgrade: postprocess, ass_io, and new
translate/local_asr/srt_io helpers."""
from __future__ import annotations

from src.ass_io import AssStyle, _seconds_to_ass_time, font_for_language, write_ass
from src.postprocess import (
    apply_all,
    break_lines,
    clean_translation_text,
    fix_fused_english,
    format_translator_note,
    snap_overlaps,
    strip_residual_cjk,
)
from src.srt_io import Cue, output_path_for
from src.translate import (
    _detect_cjk_lang,
    _flag_chengyu,
    _is_classical_chinese,
    _strip_sensevoice_tag,
)


class TestBreakLines:
    def test_short_text_untouched(self):
        assert break_lines("Hello world") == "Hello world"

    def test_splits_at_midpoint_word_boundary(self):
        out = break_lines("The quick brown fox jumps over the lazy dog")
        assert "\\N" in out

    def test_no_space_returns_unchanged(self):
        assert break_lines("abcdefghijklmnop" * 4) == "abcdefghijklmnop" * 4

    def test_max_chars_respected(self):
        out = break_lines("one two three four five six seven eight nine ten", 8)
        assert "\\N" in out


class TestSnapOverlaps:
    def test_small_gap_trimmed(self):
        cues = [Cue(0.0, 5.0, "a"), Cue(5.0, 8.0, "b")]  # 0.0 gap
        out = snap_overlaps(cues, gap_ms=50)
        # cue[0].end trimmed to 5.0 - 0.05 = 4.95
        assert abs(out[0].end - 4.95) < 1e-6
        assert out[1].end == 8.0

    def test_does_not_trim_long_cue_below_min(self):
        # cue[0] is only 0.2s wide; trimming below 0.3 is forbidden.
        cues = [Cue(0.0, 0.2, "a"), Cue(0.2, 8.0, "b")]
        out = snap_overlaps(cues, gap_ms=50)
        assert out[0].end == 0.2  # left untouched

    def test_already_spaced_untouched(self):
        cues = [Cue(0.0, 4.0, "a"), Cue(5.0, 8.0, "b")]
        out = snap_overlaps(cues, gap_ms=50)
        assert out[0].end == 4.0

    def test_preserves_count(self):
        cues = [Cue(0.0, 6.0, "a"), Cue(6.0, 9.0, "b"), Cue(9.0, 12.0, "c")]
        out = snap_overlaps(cues)
        assert len(out) == 3


class TestFormatTranslatorNote:
    def test_moves_note_to_second_line(self):
        out = format_translator_note("Main text. [TN: explanation]")
        assert out == "Main text.\\N[TN: explanation]"

    def test_no_note_unchanged(self):
        assert format_translator_note("Just dialogue") == "Just dialogue"

    def test_case_insensitive_tn(self):
        out = format_translator_note("Text [tn: note]")
        assert "[tn: note]" in out


class TestApplyAll:
    def test_count_in_equals_count_out(self):
        cues = [
            Cue(0.0, 5.0, "A long line that should get broken into two. [TN: hey]"),
            Cue(5.0, 8.0, "Short"),
        ]
        out = apply_all(cues)
        assert len(out) == len(cues)
        assert all(c.text for c in out)


class TestCleanTranslationText:
    """Post-processing must repair the local model's missing-space / leaked-CJK
    output so subtitles read as clean, separated English. These guard the exact
    defects observed in the 50元 local-run regression."""

    def test_preserves_normal_text(self):
        assert clean_translation_text("The expensive one did my makeup.") == \
            "The expensive one did my makeup."

    def test_split_camelcase_fusion(self):
        # Model glued a sentence-alternative on with an internal capital.
        assert clean_translation_text("Detect promptlyAddress surface flaws") == \
            "Detect promptly Address surface flaws"
        assert clean_translation_text("it also showsIt's not that clean") == \
            "it also shows It's not that clean"

    def test_split_digit_fusion(self):
        assert clean_translation_text("Total time3more than an hour") == \
            "Total time 3 more than an hour"
        assert clean_translation_text("differ by 200times") == "differ by 200 times"

    def test_curated_lowercase_fusion(self):
        assert clean_translation_text("more noisyover this.") == "more noisy over this."
        assert clean_translation_text("helps with shapingto fix it") == "helps with shaping to fix it"

    def test_strip_residual_cjk(self):
        assert clean_translation_text("Super加倍 highlighter-lined lashes") == \
            "Super highlighter-lined lashes"

    def test_strip_literal_gloss(self):
        assert clean_translation_text(
            "One of the cheapest makeup shops (lit. most cheap化妆店之)"
        ) == "One of the cheapest makeup shops"

    def test_keeps_brand_camelcase(self):
        assert "iPhone" in clean_translation_text("bought an iPhone today")
        assert "YouTube" in clean_translation_text("a YouTube video")

    def test_preserves_legitimate_ellipsis(self):
        assert clean_translation_text("This shop is really...") == "This shop is really..."

    def test_fix_fused_and_strip_count_preserved_in_apply_all(self):
        cues = [Cue(0.0, 5.0, "Detect promptlyAddress surface flaws")]
        out = apply_all(cues)
        assert len(out) == 1

    def test_does_not_blank_fully_cjk_lines(self):
        # A line that is entirely source-language with no Latin content must not
        # be reduced to an empty string.
        assert strip_residual_cjk("这是一个中文句子") == "这是一个中文句子"


class TestAssOutput:
    def test_seconds_to_ass_time(self):
        assert _seconds_to_ass_time(0.0) == "0:00:00.00"
        assert _seconds_to_ass_time(65.5) == "0:01:05.50"
        assert _seconds_to_ass_time(3661.25) == "1:01:01.25"

    def test_write_ass_roundtrip(self, tmp_path):
        path = str(tmp_path / "out.ass")
        cues = [
            Cue(0.0, 2.5, "Hello\\Nworld"),
            Cue(3.0, 5.0, "Second line"),
        ]
        count = write_ass(path, cues, AssStyle())
        assert count == 2

        with open(path, "r", encoding="utf-8-sig") as f:
            data = f.read()
        assert "[Script Info]" in data
        assert "[V4+ Styles]" in data
        assert "[Events]" in data
        assert "Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,Hello\\Nworld" in data
        assert data.count("Dialogue:") == 2


class TestAssFontForLanguage:
    def test_unknown_returns_arial(self):
        assert font_for_language(None) == "Arial"
        assert font_for_language("en") == "Arial"

    def test_japanese(self):
        assert font_for_language("ja") == "Noto Sans CJK JP"

    def test_chinese_region_resolves_to_primary(self):
        assert font_for_language("zh-CN") == "Noto Sans CJK SC"
        assert font_for_language("zh-tw") == "Noto Sans CJK TC"

    def test_korean(self):
        assert font_for_language("ko") == "Noto Sans CJK KR"


class TestAssWriteFontParameters:
    def test_source_language_selects_cjk_font(self, tmp_path):
        from src.srt_io import Cue

        path = str(tmp_path / "out.ass")
        write_ass(path, [Cue(0.0, 1.0, "Hello")], source_language="ja")
        with open(path, "r", encoding="utf-8-sig") as f:
            data = f.read()
        assert "Noto Sans CJK JP" in data

    def test_explicit_font_override(self, tmp_path):
        from src.srt_io import Cue

        path = str(tmp_path / "out.ass")
        write_ass(path, [Cue(0.0, 1.0, "Hello")], font="Custom Font")
        with open(path, "r", encoding="utf-8-sig") as f:
            data = f.read()
        assert "Custom Font" in data

    def test_fontsize_override(self, tmp_path):
        from src.srt_io import Cue

        path = str(tmp_path / "out.ass")
        write_ass(path, [Cue(0.0, 1.0, "Hello")], fontsize=64)
        with open(path, "r", encoding="utf-8-sig") as f:
            data = f.read()
        assert ",64," in data

    def test_title_in_header(self, tmp_path):
        from src.srt_io import Cue

        path = str(tmp_path / "out.ass")
        write_ass(path, [Cue(0.0, 1.0, "Hello")], title="My Video")
        with open(path, "r", encoding="utf-8-sig") as f:
            data = f.read()
        assert "Title: My Video" in data
class TestNewTranslateHelpers:
    def test_flag_chengyu(self):
        assert _flag_chengyu("点睛之笔") == "[CHENGYU:点睛之笔]"

    def test_flag_chengyu_multiple(self):
        out = _flag_chengyu("画龙点睛和锦上添花")
        # Spec-mandated non-overlapping {4} regex: wraps runs of 4 CJK chars.
        assert "[CHENGYU:画龙点睛]" in out
        assert out.startswith("[CHENGYU:")

    def test_is_classical_chinese(self):
        assert _is_classical_chinese("知其不可而为之者也，吾亦未之信矣。") is True
        assert _is_classical_chinese("这是一段非常普通的现代中文句子") is False

    def test_detect_cjk_lang(self):
        assert _detect_cjk_lang("こんにちは世界") == "ja"
        assert _detect_cjk_lang("안녕하세요") == "ko"
        assert _detect_cjk_lang("你好世界") == "zh"
        assert _detect_cjk_lang("hello") is None

    def test_strip_sensevoice_tag(self):
        assert _strip_sensevoice_tag("<HAPPY> 你好") == "你好"
        assert _strip_sensevoice_tag("<|HAPPY|> 你好") == "你好"
        assert _strip_sensevoice_tag("No tag") == "No tag"

    def test_strip_sensevoice_tag_full_group(self):
        # The exact leaking prefix from the 50元 regression run: language +
        # emotion + event + itn tags, all pipe-delimited, lowercase language.
        assert _strip_sensevoice_tag(
            "<|zh|><|ANGRY|><|BGM|><|withitn|>hello world"
        ) == "hello world"
        assert _strip_sensevoice_tag(
            "<|zh|><|NEUTRAL|><|Speech|><|withitn|>Is this worth it?"
        ) == "Is this worth it?"
        assert _strip_sensevoice_tag(
            "<|zh|><|EMO_UNKNOWN|><|Speech|><|withitn|>Is this really it?"
        ) == "Is this really it?"

    def test_strip_sensevoice_tag_repairs_chengyu_leak(self):
        # If the model echoes a [CHENGYU:...] wrapper back, it must be unwrapped.
        assert _strip_sensevoice_tag(
            "[CHENGYU:you must have also] applied makeup"
        ) == "you must have also applied makeup"

    def test_strip_sensevoice_tag_repairs_unclosed_chengyu_leak(self):
        # The local model often emits [CHENGYU: with NO closing bracket
        # ("[CHENGYU: many people"). The marker must still be removed.
        assert _strip_sensevoice_tag(
            "I see there are already[CHENGYU: many people hereearly in the morning."
        ) == "I see there are already many people hereearly in the morning."
        assert _strip_sensevoice_tag(
            "Yes, it can go up to 5 digits,[CHENGYU: The price is completely 200 times different."
        ) == "Yes, it can go up to 5 digits, The price is completely 200 times different."

    def test_strip_sensevoice_tag_repairs_chained_chengyu_leak(self):
        # Chained wrappers with no separators: brackets are removed, leaving the
        # translated phrases (best-effort; spacing is the model's responsibility).
        assert _strip_sensevoice_tag(
            "[CHENGYU:Who was there][CHENGYU:Didn't you][CHENGYU:Apply a little]"
        ) == "Who was thereDidn't youApply a little"


from src.local_asr import _cjk_adjusted_char_count, _snap_cues_to_keyframes


class TestCjkAdjustedCharCount:
    def test_ascii_counts_one_each(self):
        assert _cjk_adjusted_char_count("hello") == 5

    def test_cjk_counts_two_each(self):
        # 4 CJK chars -> weighted 8.
        assert _cjk_adjusted_char_count("你好世界") == 8

    def test_mixed(self):
        # "hi" (2) + "好" (2) = 4
        assert _cjk_adjusted_char_count("hi好") == 4


class TestSnapCuesToKeyframes:
    def test_snaps_within_window(self):
        cues = [Cue(1.02, 4.0, "text")]
        out = _snap_cues_to_keyframes(cues, [1.0, 5.0], snap_window_s=0.10)
        assert out[0].start == 1.0
        # duration preserved: end shifted by same delta (-0.02)
        assert abs(out[0].end - 3.98) < 1e-9

    def test_no_snap_outside_window(self):
        cues = [Cue(1.20, 4.0, "text")]
        out = _snap_cues_to_keyframes(cues, [1.0, 5.0], snap_window_s=0.10)
        assert out[0].start == 1.20

    def test_empty_keyframes_returns_unchanged(self):
        cues = [Cue(1.02, 4.0, "text")]
        out = _snap_cues_to_keyframes(cues, [])
        assert out[0].start == 1.02
        assert len(out) == 1

    def test_preserves_count(self):
        cues = [
            Cue(1.02, 4.0, "a"),
            Cue(5.03, 8.0, "b"),
            Cue(9.10, 12.0, "c"),
        ]
        out = _snap_cues_to_keyframes(cues, [1.0, 5.0, 9.1])
        assert len(out) == 3
class TestOutputPathFor:
    def test_sanitizes_and_appends_ext(self):
        assert output_path_for("My Video: clip", ".ass") == "My Video clip.ass"

    def test_default_srt(self):
        assert output_path_for("hello world").endswith(".srt")