"""Batching helpers for subtitle translation.

Splits cue texts into safe, model-aware batches so small CPU models like
Hy-MT2 don't choke on oversized requests. The helpers are deterministic and
fast — no tokenizers, just character-weight estimation.

Public API:
    is_cjk_language(source_language)  -> bool
    estimate_text_weight(text, source_language) -> int
    chunk_texts(texts, *, max_items, max_total_chars, source_language) -> list[list[int]]
"""
from __future__ import annotations

# Languages treated as CJK-dominant (Chinese/Japanese/Korean/Cantonese and
# their ISO 639-2/3 codes + human-readable names). Matched case-insensitively.
_CJK_LANGUAGE_CODES = {
    "zh", "zho", "chi", "chs", "cht", "chinese",
    "ja", "jpn", "japanese",
    "ko", "kor", "korean",
    "yue", "cantonese",
}


def is_cjk_language(source_language: str | None) -> bool:
    """Return True if the source language is Chinese, Japanese, Korean, or Cantonese.

    Normalizes case and strips whitespace before comparison.
    """
    lang = (source_language or "").strip().lower()
    if not lang:
        return False
    # Allow codes like "zh-CN" or "ja-JP" — match on the primary subtag.
    primary = lang.split("-")[0].split("_")[0]
    return primary in _CJK_LANGUAGE_CODES or lang in _CJK_LANGUAGE_CODES


def estimate_text_weight(text: str, source_language: str | None) -> int:
    """Estimate how expensive a single line is for batching purposes.

    Counts non-whitespace characters. Deterministic and fast — no tokenizers.
    A CJK character generally maps to ~1 weight unit; non-CJK characters also
    count as 1 each. The distinction matters at the *batch* level (CJK batches
    use a lower char budget) rather than per-item.
    """
    if not text:
        return 0
    return len("".join(text.split()))


def chunk_texts(
    texts: list[str],
    *,
    max_items: int,
    max_total_chars: int,
    source_language: str | None = None,
) -> list[list[int]]:
    """Split ``texts`` into batches of original indices.

    Rules:
        - Never reorder indices.
        - Never drop indices — every index appears exactly once.
        - Each batch has at most ``max_items`` entries.
        - Each batch's total non-whitespace char count stays within
          ``max_total_chars`` *unless a single item alone exceeds the limit*
          (it still becomes its own batch).
        - A single cue text is never split here; cue-text splitting is ASR's
          responsibility.

    Args:
        texts: The cue texts to batch (order is preserved).
        max_items: Maximum number of items per batch.
        max_total_chars: Maximum total non-whitespace characters per batch.
        source_language: Optional source language (currently informational).

    Returns:
        A list of batches, each a list of original 0-based indices.

    Raises:
        ValueError: If ``max_items`` or ``max_total_chars`` is <= 0.
    """
    if max_items <= 0:
        raise ValueError(f"max_items must be > 0, got {max_items}")
    if max_total_chars <= 0:
        raise ValueError(f"max_total_chars must be > 0, got {max_total_chars}")

    batches: list[list[int]] = []
    current: list[int] = []
    current_chars = 0

    for idx, text in enumerate(texts):
        item_chars = estimate_text_weight(text, source_language)

        # Flush the current batch if adding this item would exceed either limit.
        # An empty current batch always accepts at least one item (so oversized
        # single items get their own batch instead of being dropped).
        if current and (
            len(current) >= max_items
            or current_chars + item_chars > max_total_chars
        ):
            batches.append(current)
            current = []
            current_chars = 0

        current.append(idx)
        current_chars += item_chars

    if current:
        batches.append(current)

    return batches
