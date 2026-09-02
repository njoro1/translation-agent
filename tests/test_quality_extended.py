"""Extended quality checks (Phase 6): leakage, residue, duplicates, overlap."""
from __future__ import annotations

from src.srt_io import Cue
from src.subtitle_quality import build_report


def _issue_map(cues):
    report = build_report(cues)
    tags = {}
    for issue in report.issues:
        for tag in issue["issues"]:
            tags.setdefault(tag, []).append(issue["cue_index"])
    return report, tags


def test_asr_tag_leakage_is_error():
    cues = [Cue(0.0, 1.0, "<|zh|><|ANGRY|>Hello there")]
    report, tags = _issue_map(cues)
    assert "asr_tag_leakage_error" in tags
    assert report.error_count >= 1
    assert report.tag_leakage_count == 1


def test_fansub_markup_leakage_is_error():
    cues = [Cue(0.0, 1.0, "[CHENGYU:画蛇添足] drawing a snake")]
    report, tags = _issue_map(cues)
    assert "fansub_markup_error" in tags
    assert report.tag_leakage_count == 1


def test_untranslated_marker_is_error():
    cues = [Cue(0.0, 1.0, "[untranslated]")]
    report, tags = _issue_map(cues)
    assert "untranslated_marker_error" in tags
    assert report.untranslated_marker_count == 1


def test_small_cjk_residue_is_warning():
    # A retained name inside an otherwise English line.
    cues = [Cue(0.0, 2.0, "This is Naruto's 私 jutsu, believe it!")]
    _, tags = _issue_map(cues)
    assert "cjk_residue_warning" in tags
    assert "cjk_residue_error" not in tags


def test_mostly_cjk_line_is_error():
    cues = [Cue(0.0, 2.0, "这是一句没有翻译的中文台词")]
    report, tags = _issue_map(cues)
    assert "cjk_residue_error" in tags
    assert report.cjk_residue_count == 1
    assert report.error_count >= 1


def test_duplicate_consecutive_translation_is_warning():
    cues = [
        Cue(0.0, 1.0, "Really?"),
        Cue(1.0, 2.0, "Really?"),
    ]
    report, tags = _issue_map(cues)
    assert "duplicate_translation_warning" in tags
    assert report.duplicate_count == 1
    # Warnings alone never escalate to errors.
    assert report.error_count == 0
    assert report.warning_count >= 1


def test_identical_different_lines_not_flagged():
    cues = [
        Cue(0.0, 1.0, "Yes."),
        Cue(2.0, 3.0, "No."),
    ]
    _, tags = _issue_map(cues)
    assert "duplicate_translation_warning" not in tags


def test_overlap_after_postprocess_is_warning():
    cues = [
        Cue(0.0, 2.0, "First line"),
        Cue(1.5, 3.0, "Second line"),  # starts before previous ends
    ]
    report, tags = _issue_map(cues)
    assert "overlap_warning" in tags
    assert report.overlap_count == 1


def test_clean_cues_produce_no_new_issues():
    cues = [
        Cue(0.0, 2.0, "A clean English line."),
        Cue(2.5, 4.5, "Another clean line."),
    ]
    report, tags = _issue_map(cues)
    assert not any(
        t.startswith(("asr_", "fansub_", "untranslated_", "cjk_", "duplicate_", "overlap_"))
        for t in tags
    )
    assert report.error_count == 0
    assert report.warning_count == 0


def test_strict_escalation_counts_serious_errors():
    cues = [
        Cue(0.0, 1.0, "<|ja|>leaked"),
        Cue(1.0, 2.0, "Fine line."),
    ]
    report = build_report(cues, untranslated_count=0)
    # Strict mode fails when error_count > 0 — matches translate.py's check.
    assert report.error_count > 0
