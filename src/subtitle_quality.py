"""Subtitle quality diagnostics.

Analyzes a list of cues and reports issues based on characters-per-second (CPS),
cue duration, character count, line count, and empty text. Issues are classified
as warnings or errors with configurable thresholds.

The report is plain data (no external dependencies) so it can be serialized to
JSON for the ``--quality-report`` CLI flag.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Sequence

from .srt_io import Cue

# --- Thresholds -------------------------------------------------------------

CPS_WARNING = 18.0
CPS_ERROR = 22.0
CHARS_WARNING = 80
CHARS_ERROR = 110
MIN_DURATION_WARNING = 0.8
MIN_DURATION_ERROR = 0.5
MAX_DURATION_WARNING = 6.0
MAX_DURATION_ERROR = 8.0
LINES_WARNING = 2
LINES_ERROR = 3

# --- Leakage / residue detection --------------------------------------------
# SenseVoice ASR control tokens (`<|zh|>`, `<|ANGRY|>`, `<|BGM|>`) must never
# reach the final output; neither may fansub prompt markup such as the
# [CHENGYU:...] wrapper echoed back by a model.
_ASR_TAG_RE = re.compile(r"<\|[a-zA-Z0-9_]*\|>")
_EMOTION_TAG_RE = re.compile(r"<(?:HAPPY|SAD|ANGRY|NEUTRAL|FEARFUL|DISGUSTED|SURPRISED)>", re.I)
_FANSUB_MARKUP_RE = re.compile(r"\[CHENGYU:[^\]]*\]|\[TRANSLATOR", re.I)
_UNTRANSLATED_MARKER = "[untranslated]"

# A CJK residue above this non-space ratio means the line is essentially
# untranslated source text (error), below it is likely a name/honorific/glossary
# term that survived foreignization (warning).
CJK_RESIDUE_ERROR_RATIO = 0.5


def clean_translation_text(text: str) -> str:
    """Strip the artefacts the quality checks flag, for the "Auto-fix" action.

    Removes leaked ASR tags (``<|zh|>``), emotion tags, fansub markup and the
    ``[untranslated]`` marker, then collapses the whitespace left behind. This
    is deliberately the same set of patterns ``analyze_cues`` reports, so
    auto-fix can only clear issues the report actually raised.
    """
    cleaned = _ASR_TAG_RE.sub("", text or "")
    cleaned = _EMOTION_TAG_RE.sub("", cleaned)
    cleaned = _FANSUB_MARKUP_RE.sub("", cleaned)
    cleaned = cleaned.replace(_UNTRANSLATED_MARKER, "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    return cleaned.strip()


def _cjk_char_count(text: str) -> int:
    return sum(
        1 for ch in text
        if "\u3400" <= ch <= "\u4dbf"
        or "\u4e00" <= ch <= "\u9fff"
        or "\uac00" <= ch <= "\ud7af"
        or "\u3040" <= ch <= "\u30ff"
    )


def _normalize_for_duplicate(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


@dataclass
class CueIssue:
    """A single quality issue for one cue."""

    cue_index: int
    start: float
    end: float
    issues: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.endswith("_error") or i == "empty_text" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.endswith("_warning") for i in self.issues)


def _visible_text_length(text: str) -> int:
    """Length of cue text excluding newline characters."""
    return len(text.replace("\n", "").replace("\r", ""))


def _line_count(text: str) -> int:
    """Number of non-empty lines in the cue text."""
    return len([ln for ln in text.splitlines() if ln.strip()])


def _cps(text: str, duration: float) -> float:
    """Characters per second for a cue."""
    if duration <= 0:
        return 0.0
    return _visible_text_length(text) / duration


def analyze_cues(cues: Sequence[Cue]) -> list[CueIssue]:
    """Analyze a sequence of cues and return a list of per-cue issues.

    Only cues with at least one issue are included in the result.
    """
    results: list[CueIssue] = []
    prev_normalized: str | None = None

    for i, cue in enumerate(cues):
        issues: list[str] = []
        duration = cue.end - cue.start
        text = cue.text or ""
        visible_len = _visible_text_length(text)
        cps = _cps(text, duration)
        lines = _line_count(text)

        # Empty text.
        if visible_len == 0:
            issues.append("empty_text")

        # Untranslated marker: a failed cue must stay visible in the report.
        if text.strip() == _UNTRANSLATED_MARKER:
            issues.append("untranslated_marker_error")

        # ASR tag leakage (SenseVoice control tokens / emotion tags).
        if _ASR_TAG_RE.search(text) or _EMOTION_TAG_RE.search(text):
            issues.append("asr_tag_leakage_error")

        # Fansub prompt markup leakage ([CHENGYU:...] etc.).
        if _FANSUB_MARKUP_RE.search(text):
            issues.append("fansub_markup_error")

        # CJK residue in English output. Small residue is usually a retained
        # name/honorific/glossary term (warning); a mostly-CJK line is
        # effectively untranslated source (error).
        if visible_len > 0 and text.strip() != _UNTRANSLATED_MARKER:
            non_space = "".join(text.split())
            cjk = _cjk_char_count(non_space)
            if cjk > 0:
                if cjk / len(non_space) > CJK_RESIDUE_ERROR_RATIO:
                    issues.append("cjk_residue_error")
                else:
                    issues.append("cjk_residue_warning")

        # Duplicate consecutive translation (exact, whitespace-folded).
        normalized = _normalize_for_duplicate(text)
        if normalized and normalized == prev_normalized:
            issues.append("duplicate_translation_warning")
        prev_normalized = normalized

        # Overlap with the previous cue (postprocess normally snaps these).
        if i > 0 and cues[i - 1].end > cue.start + 1e-9:
            issues.append("overlap_warning")

        # Characters-per-second.
        if cps >= CPS_ERROR:
            issues.append("cps_error")
        elif cps >= CPS_WARNING:
            issues.append("cps_warning")

        # Character count.
        if visible_len >= CHARS_ERROR:
            issues.append("chars_error")
        elif visible_len >= CHARS_WARNING:
            issues.append("chars_warning")

        # Too short.
        if duration <= MIN_DURATION_ERROR:
            issues.append("too_short_error")
        elif duration <= MIN_DURATION_WARNING:
            issues.append("too_short_warning")

        # Too long.
        if duration >= MAX_DURATION_ERROR:
            issues.append("too_long_error")
        elif duration >= MAX_DURATION_WARNING:
            issues.append("too_long_warning")

        # Line count.
        if lines >= LINES_ERROR:
            issues.append("lines_error")
        elif lines >= LINES_WARNING:
            issues.append("lines_warning")

        if issues:
            results.append(
                CueIssue(cue_index=i, start=cue.start, end=cue.end, issues=issues)
            )

    return results


@dataclass
class QualityReport:
    """Aggregated quality report over a set of cues."""

    cue_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    empty_count: int = 0
    untranslated_count: int = 0
    untranslated_marker_count: int = 0
    tag_leakage_count: int = 0
    cjk_residue_count: int = 0
    duplicate_count: int = 0
    overlap_count: int = 0
    average_cps: float = 0.0
    max_cps: float = 0.0
    average_duration: float = 0.0
    max_duration: float = 0.0
    issues: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def build_report(
    cues: Sequence[Cue],
    *,
    untranslated_count: int = 0,
) -> QualityReport:
    """Build an aggregated quality report from a list of cues.

    ``untranslated_count`` is the number of cues the translation stage explicitly
    marked as failed (empty output after retry/language validation). It is
    reported (and JSON-serialized) separately from the SRT-heuristic issues so a
    partially-broken output is never mistaken for a complete translation.
    """
    cue_issues = analyze_cues(cues)
    warning_count = sum(1 for ci in cue_issues if ci.has_warnings)
    error_count = sum(1 for ci in cue_issues if ci.has_errors)
    empty_count = sum(1 for ci in cue_issues if "empty_text" in ci.issues)

    def _count(tag: str) -> int:
        return sum(1 for ci in cue_issues if tag in ci.issues)

    if cues:
        durations = [c.end - c.start for c in cues]
        cps_values = [_cps(c.text or "", c.end - c.start) for c in cues]
        avg_dur = sum(durations) / len(durations)
        max_dur = max(durations)
        avg_cps = sum(cps_values) / len(cps_values)
        max_cps = max(cps_values) if cps_values else 0.0
    else:
        avg_dur = max_dur = avg_cps = max_cps = 0.0

    return QualityReport(
        cue_count=len(cues),
        warning_count=warning_count,
        error_count=error_count,
        empty_count=empty_count,
        untranslated_count=untranslated_count,
        untranslated_marker_count=_count("untranslated_marker_error"),
        tag_leakage_count=(
            _count("asr_tag_leakage_error") + _count("fansub_markup_error")
        ),
        cjk_residue_count=(
            _count("cjk_residue_warning") + _count("cjk_residue_error")
        ),
        duplicate_count=_count("duplicate_translation_warning"),
        overlap_count=_count("overlap_warning"),
        average_cps=round(avg_cps, 2),
        max_cps=round(max_cps, 2),
        average_duration=round(avg_dur, 3),
        max_duration=round(max_dur, 3),
        issues=[
            {"cue_index": ci.cue_index, "start": ci.start, "end": ci.end,
             "issues": ci.issues}
            for ci in cue_issues
        ],
    )


def print_summary(
    cues: Sequence[Cue],
    *,
    untranslated_count: int = 0,
) -> QualityReport:
    """Analyze cues, print a human-readable summary, and return the report."""
    report = build_report(cues, untranslated_count=untranslated_count)
    print(f"[quality] {report.warning_count} warnings, {report.error_count} errors",
          flush=True)
    if untranslated_count:
        print(f"[quality] {untranslated_count} cue(s) untranslated", flush=True)
    if report.tag_leakage_count:
        print(f"[quality] {report.tag_leakage_count} cue(s) with ASR/fansub tag leakage",
              flush=True)
    if report.cjk_residue_count:
        print(f"[quality] {report.cjk_residue_count} cue(s) with CJK residue in English output",
              flush=True)
    for issue_dict in report.issues:
        idx = issue_dict["cue_index"]
        for tag in issue_dict["issues"]:
            if tag in ("cps_warning", "cps_error"):
                cps = _cps(cues[idx].text or "", cues[idx].end - cues[idx].start)
                level = "error" if tag.endswith("error") else "warning"
                print(f"[quality] Cue {idx}: CPS {cps:.1f} exceeds {level} threshold",
                      flush=True)
            elif tag == "untranslated_marker_error":
                print(f"[quality] Cue {idx}: carries the [untranslated] marker",
                      flush=True)
            elif tag == "asr_tag_leakage_error":
                print(f"[quality] Cue {idx}: ASR tag leaked into output: "
                      f"{cues[idx].text!r}", flush=True)
            elif tag == "fansub_markup_error":
                print(f"[quality] Cue {idx}: fansub markup leaked into output: "
                      f"{cues[idx].text!r}", flush=True)
            elif tag == "cjk_residue_error":
                print(f"[quality] Cue {idx}: mostly-CJK (untranslated?) line: "
                      f"{cues[idx].text!r}", flush=True)
    return report
