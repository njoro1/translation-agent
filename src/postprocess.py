"""Post-processing for fansub-quality subtitle output."""
from __future__ import annotations
import re
from dataclasses import replace
from typing import Sequence


# Latin words that legitimately contain an internal capital letter and must never
# be split by the CamelCase de-fusion pass (brands/terms/trademarks).
_PRESERVE_CAMEL = {
    "iPhone", "iPad", "iPod", "eBay", "MacBook", "McDonald", "McDonalds",
    "YouTube", "GitHub", "OpenAI", "OpenAI-compatible", "SenseVoice",
    "Hy-MT2", "Qwen", "CamelCase", "Spotify", "PayPal", "AirPods", "Chrome",
}

# CJK ideographs (Ext A + Unified) and Hangul syllables — any script that this
# English-target pipeline should not carry into the final subtitle.
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]+")

# Literal-gloss annotations the model sometimes appends, e.g. "(lit. for '主动给我':
# actively give to me)". These are translation aids, not subtitle content.
_LIT_GLOSS_RE = re.compile(r"\(lit\.[^)]*\)", re.IGNORECASE)

# A trailing-alone word-fragment is hard to repair generically, but a digit glued
# into a Latin word ("time3more" -> "time 3 more", "200times" -> "200 times") is a
# safe, reversible split.
_DIGIT_WORD_BOUNDARY_RE = re.compile(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])")

# Specific lowercase-word fusions the model repeatedly produces ("noisyover",
# "shapingto"); these have no [a-z][A-Z] cue to split on, so handle them with a
# small curated map. Kept tiny and conservative — only unambiguous merges.
_FUSION_FIXES = {
    "noisyover": "noisy over",
    "shapingto": "shaping to",
    "time3more": "time 3 more",
    "alreadytapped": "already tapped",
    "myface": "my face",
}


def fix_fused_english(text: str) -> str:
    """Repair the Hy-MT2 model's missing-space output.

    The small local model frequently concatenates words/sentence-alternatives with
    no separator ("showsIt's", "promptlyAddress", "time3more", "200times"). This
    reconstructs the word boundaries that a comma/sentence runner would otherwise
    merge, so each subtitle line reads legibly. Known camelCase brand tokens are
    preserved so "iPhone", "YouTube", etc. are never split.
    """
    if not text:
        return text

    # 0) Curated whole-word fusions first (they may span a digit boundary too).
    for src, dst in _FUSION_FIXES.items():
        text = text.replace(src, dst)

    # 1) Digit <-> letter boundaries: "time3more" -> "time 3 more".
    text = _DIGIT_WORD_BOUNDARY_RE.sub(" ", text)

    # 2) Internal-caps boundaries: "showsIt's" -> "shows It's". Split at a
    #    lowercase-Latin + uppercase-Latin boundary, but never inside a token in
    #    the preserve list.
    parts = re.split(r"(\s+)", text)
    out: list[str] = []
    for part in parts:
        if not part or part.isspace():
            out.append(part)
            continue
        joined = part
        while True:
            m = re.search(r"([a-z])([A-Z])", joined)
            if not m:
                break
            # Don't split inside a recognized term (check the containing token).
            start = m.start(0)
            l_ws = joined.rfind(" ", 0, start)
            r_ws = joined.find(" ", start)
            token = joined[l_ws + 1:r_ws if r_ws != -1 else None]
            if token in _PRESERVE_CAMEL:
                break
            joined = joined[:start + 1] + " " + joined[start + 1:]
        out.append(joined)
    return "".join(out)


def strip_residual_cjk(text: str) -> str:
    """Remove stray CJK/Hangul that leaked into an English line.

    The local model occasionally leaves a Chinese token in place ("Super加倍",
    "万元档化"). Remove those runs and tidy leftover whitespace. If the line had
    no Latin content to begin with, return it unchanged so we never blank a cue.
    """
    if not text:
        return text
    cleaned = _CJK_RE.sub(" ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if not re.search(r"[A-Za-z]", cleaned):
        return text
    return cleaned


def strip_literal_gloss(text: str) -> str:
    """Drop the '(lit. ...)' annotations (and any leftover CJK inside them)."""
    if not text:
        return text
    cleaned = _LIT_GLOSS_RE.sub(" ", text)
    cleaned = clear_redundant_punctuation(cleaned)
    return cleaned


def clear_redundant_punctuation(text: str) -> str:
    """Collapse whitespace/markup artefacts left by stripping markup.

    Fixes artifacts like 'X, , Y' (empty comma from a removed token), double
    spaces, and spaces before commas. Legitimate ellipses ('...') are preserved.
    """
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,\s*,+", ",", text)
    text = re.sub(r"\s+,", ",", text)
    return text.strip()


def clean_translation_text(text: str) -> str:
    """All model-output cleanup, in dependency order (strips gloss/CJK first so
    the later fusion pass never re-glues a CJK token to neighboring Latin text)."""
    text = text.strip()
    if not text:
        return text
    text = strip_literal_gloss(text)
    text = strip_residual_cjk(text)
    text = fix_fused_english(text)
    text = clear_redundant_punctuation(text)
    return text.strip()


def break_lines(text: str, max_chars: int = 37) -> str:
    """
    Split subtitle text into at most 2 lines of max_chars each.
    Breaks at the last word boundary before or nearest to the midpoint.
    Returns text with \\N as the line separator (ASS) or \\n (SRT).
    Uses \\N by default; caller may replace for SRT.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text
    # Find split point nearest to midpoint
    mid = len(text) // 2
    # Search left from mid for a space
    left = text.rfind(" ", 0, mid + 1)
    # Search right from mid for a space
    right = text.find(" ", mid)
    if left == -1 and right == -1:
        return text  # no word boundary; leave as-is
    if left == -1:
        split = right
    elif right == -1:
        split = left
    else:
        split = left if (mid - left) <= (right - mid) else right
    line1 = text[:split].strip()
    line2 = text[split:].strip()
    # Hard cap: if either line still exceeds max_chars, don't split further
    return f"{line1}\\N{line2}"


def snap_overlaps(cues: list, gap_ms: int = 50) -> list:
    """
    Ensure consecutive cues have at least gap_ms milliseconds of separation.
    If cue[i].end > cue[i+1].start, trim cue[i].end to cue[i+1].start - gap_ms/1000.
    Never trims a cue below 300 ms duration.
    """
    MIN_DURATION = 0.300
    result = list(cues)
    for i in range(len(result) - 1):
        gap = gap_ms / 1000.0
        if result[i].end > result[i + 1].start - gap:
            new_end = result[i + 1].start - gap
            if new_end - result[i].start >= MIN_DURATION:
                result[i] = replace(result[i], end=new_end)
    return result


def format_translator_note(text: str) -> str:
    """
    Move [TN: ...] annotations to a second subtitle line.
    Input:  "Main dialogue text. [TN: honorific explanation]"
    Output: "Main dialogue text.\\N[TN: honorific explanation]"
    """
    tn_pattern = re.compile(r"\s*(\[TN:[^\]]+\])", re.IGNORECASE)
    match = tn_pattern.search(text)
    if not match:
        return text
    main = text[:match.start()].strip()
    tn = match.group(1).strip()
    return f"{main}\\N{tn}"


def apply_all(cues: list, max_line_chars: int = 37, overlap_gap_ms: int = 50) -> list:
    """Run all post-processing steps in order.

    Returns exactly the same number of cues it receives — no merging or dropping.
    """
    result = []
    for cue in cues:
        t = cue.text
        t = clean_translation_text(t)
        t = format_translator_note(t)
        t = break_lines(t, max_line_chars)
        result.append(replace(cue, text=t))
    result = snap_overlaps(result, overlap_gap_ms)
    return result