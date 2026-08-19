"""CJK (Chinese / Japanese / Korean) script helpers for subtitles.

Provides lightweight, dependency-free helpers used across the translation
pipeline:

- ``contains_cjk(text)`` — detect whether a string carries any CJK/Hangul/kana.
- ``detect_cjk_language(text)`` — classify a sample as ``zh`` / ``ja`` / ``ko``
  by script ratios (robust against short, mixed, or code-switched samples).
- ``char_width`` / ``text_width`` — approximate subtitle display width where
  full-width CJK characters count as 2 display units.
- ``NO_LINE_START`` / ``NO_LINE_END`` and ``break_cjk`` — kinsoku-aware line
  breaking for CJK source/bilingual output.

These are intentionally pure and fast (no tokenizers, no network) so they are
safe to call on large cue samples during a run.
"""
from __future__ import annotations

import re
import unicodedata

# Characters that may never start a subtitle line (kinsoku prohibition at the
# left edge): CJK/full-width closing punctuation, Japanese kana small-forms,
# and ASCII closing delimiters.
NO_LINE_START = set(
    "、。，．・？！：；゛゜ヽヾゝゞ々ーァィゥェォッャュョヮヵヶゕゖ"
    "）〕］｝〉》」』】〙〗〟,.;:!?)]}…‥"
)

# Characters that may never end a subtitle line (kinsoku prohibition at the
# right edge): opening brackets/parens.
NO_LINE_END = set("（〔［｛〈《「『【〘〖([{")


def char_width(ch: str) -> int:
    """Approximate subtitle display width of a single character.

    Full-width / wide East-Asian characters count as 2 display units; everything
    else (Latin, digits, narrow punctuation) counts as 1.
    """
    return 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1


def text_width(text: str) -> int:
    """Total approximate display width of ``text`` in display units."""
    return sum(char_width(ch) for ch in text)


def contains_cjk(text: str) -> bool:
    """Return True if ``text`` contains any CJK ideograph, kana, or Hangul."""
    for ch in text:
        cp = ord(ch)
        if (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0x20000 <= cp <= 0x2A6DF
            or 0xF900 <= cp <= 0xFAFF
            or 0x3040 <= cp <= 0x30FF
            or 0x31F0 <= cp <= 0x31FF
            or 0xFF66 <= cp <= 0xFF9D
            or 0xAC00 <= cp <= 0xD7A3
            or 0x1100 <= cp <= 0x11FF
            or 0x3130 <= cp <= 0x318F
        ):
            return True
    return False


def detect_cjk_language(text: str, default: str | None = None) -> str | None:
    """Detect ``ja`` / ``ko`` / ``zh`` from subtitle text via script ratios.

    Scoring by script families rather than exact seven-segment counts makes the
    classifier robust to code-switching, occasional English, and loanwords:

    - Japanese usually mixes kana + han.
    - Korean is Hangul-dominant.
    - Chinese is Han-only (no kana / Hangul).

    A tiny sample (fewer than ~8 CJK characters) is too ambiguous to classify,
    so it returns ``default`` instead of guessing.
    """
    hangul = 0
    kana = 0
    han = 0

    for ch in text:
        cp = ord(ch)
        if (
            0xAC00 <= cp <= 0xD7A3
            or 0x1100 <= cp <= 0x11FF
            or 0x3130 <= cp <= 0x318F
        ):
            hangul += 1
        elif (
            0x3040 <= cp <= 0x30FF
            or 0x31F0 <= cp <= 0x31FF
            or 0xFF66 <= cp <= 0xFF9D
        ):
            kana += 1
        elif (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0x20000 <= cp <= 0x2A6DF
            or 0xF900 <= cp <= 0xFAFF
        ):
            han += 1

    total = hangul + kana + han
    if total < 8:
        return default

    # Japanese usually contains kana + han.
    if kana and kana + han >= hangul:
        return "ja"
    # Korean usually has dominant Hangul.
    if hangul and hangul >= max(kana, han):
        return "ko"
    # Chinese usually has Han characters without kana/hangul.
    if han and han >= max(kana, hangul):
        return "zh"

    return default


def detect_cjk_from_cues(cues, sample_size: int = 80) -> str | None:
    """Detect the dominant CJK language across the first ``sample_size`` cues.

    Uses a larger sample than a handful of cues so an opening song, sign,
    greeting, or mixed-language segment does not skew the result. Returns
    ``None`` when the sample is not confidently CJK.
    """
    sample = " ".join(c.text or "" for c in cues[:sample_size])
    return detect_cjk_language(sample)

    for ch in text:
        cp = ord(ch)
        if (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0x20000 <= cp <= 0x2A6DF
            or 0xF900 <= cp <= 0xFAFF
            or 0x3040 <= cp <= 0x30FF
            or 0x31F0 <= cp <= 0x31FF
            or 0xFF66 <= cp <= 0xFF9D
            or 0xAC00 <= cp <= 0xD7A3
            or 0x1100 <= cp <= 0x11FF
            or 0x3130 <= cp <= 0x318F
        ):
            return True
    return False

_PUNCT_SPLIT_RE = re.compile(r"(?<=[。！？；，、：,!?;])\s*")


def _can_break_after(text: str, i: int) -> bool:
    """Return True if a newline may be placed between text[i] and text[i+1]."""
    if i < 0 or i >= len(text) - 1:
        return False
    a = text[i]
    b = text[i + 1]
    if b in NO_LINE_START:
        return False
    if a in NO_LINE_END:
        return False
    # Do not split inside an ASCII word.
    if a.isalnum() and b.isalnum() and ord(a) < 128 and ord(b) < 128:
        return False
    return True


def _hard_break(text: str, max_width: int) -> list[str]:
    """Break ``text`` greedily by display width, respecting kinsoku rules."""
    lines: list[str] = []
    while text_width(text) > max_width:
        width = 0
        limit = 0
        break_pos: int | None = None
        for i, ch in enumerate(text):
            cw = char_width(ch)
            if width + cw > max_width:
                break
            width += cw
            limit = i + 1
            if _can_break_after(text, i):
                break_pos = i + 1
        if break_pos is None:
            break_pos = max(1, limit)
        lines.append(text[:break_pos].rstrip())
        text = text[break_pos:].lstrip()
    if text:
        lines.append(text)
    return lines


def break_cjk(text: str, max_width: int = 26, max_lines: int = 2) -> str:
    """Break CJK text into subtitle lines (kinsoku-aware) and join with ``\\N``.

    ``max_width`` is in display units where a full-width character is 2 units:
    26 units ≈ 13 CJK characters. Text longer than ``max_lines`` lines is never
    silently dropped — extra lines are kept so the quality report can flag them.
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return text
    if text_width(text) <= max_width:
        return text

    parts = _PUNCT_SPLIT_RE.split(text)
    lines: list[str] = []
    cur = ""
    for part in parts:
        if not part:
            continue
        candidate = cur + part
        if text_width(candidate) <= max_width:
            cur = candidate
            continue
        if cur:
            lines.append(cur.strip())
        if text_width(part) > max_width:
            lines.extend(_hard_break(part, max_width))
            cur = ""
        else:
            cur = part
    if cur:
        lines.append(cur.strip())

    lines = [ln for ln in lines if ln]
    return "\\N".join(lines)

