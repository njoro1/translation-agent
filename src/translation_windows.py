"""Context-first translation windows.

The primary translation unit is a :class:`TranslationWindow`, not a raw batch.
Each window carries the current cues to translate plus read-only context:

    - ``before_context``: recent (source, translation) pairs — rolling memory
    - ``after_context``: upcoming source-only cues

The numbered-item protocol is unchanged: the model must return exactly one
numbered line per CURRENT CUES entry, so cue count in == cue count out.

Context modes (before pairs / after cues / memory pairs):

    off      0 / 0 / 0   debugging & compatibility
    light    1 / 1 / 4   minimal prompts (selectable; music preset)
    standard 2 / 2 / 8   default for cloud AND local (benchmark-verified:
                         Hy-MT2 shows no alignment degradation vs light)
    deep     4 / 3 / 12  cloud long-form content
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .srt_io import Cue

CONTEXT_PROFILES: dict[str, tuple[int, int, int]] = {
    "off": (0, 0, 0),
    "light": (1, 1, 4),
    "standard": (2, 2, 8),
    "deep": (4, 3, 12),
}

# Window construction defaults (cloud). Hy-MT2 uses smaller budgets.
DEFAULT_MAX_WINDOW_CUES = 12
DEFAULT_MAX_WINDOW_DURATION_MS = 30000
DEFAULT_SCENE_GAP_MS = 800
HY_MT2_MAX_WINDOW_CUES = 8
HY_MT2_MAX_CHARS_CJK = 700
HY_MT2_MAX_CHARS_NON_CJK = 1000


@dataclass
class TranslationWindow:
    """One context-aware translation unit."""

    start_index: int
    cues: list[Cue]
    before_context: list[tuple[str, str]] = field(default_factory=list)
    after_context: list[str] = field(default_factory=list)


def resolve_context_mode(mode: str | None, *, local: bool) -> str:
    """Resolve an explicit/preset context mode against the backend default.

    Precedence: explicit value > backend default (standard for both backends —
    benchmarked on real Chinese content: Hy-MT2 with 2/2/8 context showed zero
    alignment failures and marginally higher reference similarity vs light).
    Unknown values fall back to the backend default.
    """
    normalized = (mode or "").strip().lower()
    if normalized in CONTEXT_PROFILES:
        return normalized
    return "standard"


def _char_weight(text: str) -> int:
    """Non-whitespace character count used for window char budgets."""
    return len("".join((text or "").split()))


def build_windows(
    cues: list[Cue],
    *,
    max_window_cues: int = DEFAULT_MAX_WINDOW_CUES,
    max_window_duration_ms: int = DEFAULT_MAX_WINDOW_DURATION_MS,
    scene_gap_ms: int = DEFAULT_SCENE_GAP_MS,
    max_current_chars: int = 8000,
) -> list[TranslationWindow]:
    """Split cues into ordered windows without dropping or reordering any.

    A new window starts when adding the next cue would exceed:
        - ``max_window_cues`` current cues,
        - ``max_current_chars`` current characters,
        - ``max_window_duration_ms`` cumulative duration,
    or when the gap before the cue reaches ``scene_gap_ms`` (scene break).
    """
    if max_window_cues <= 0:
        raise ValueError("max_window_cues must be > 0")
    if max_current_chars <= 0:
        raise ValueError("max_current_chars must be > 0")

    windows: list[TranslationWindow] = []
    current: list[tuple[int, Cue]] = []
    current_chars = 0
    current_duration_ms = 0.0

    def flush() -> None:
        nonlocal current, current_chars, current_duration_ms
        if current:
            windows.append(
                TranslationWindow(start_index=current[0][0],
                                  cues=[c for _, c in current])
            )
            current = []
            current_chars = 0
            current_duration_ms = 0.0

    for idx, cue in enumerate(cues):
        gap_ms = 0.0
        if current:
            prev = current[-1][1]
            gap_ms = max(0.0, (cue.start - prev.end) * 1000.0)
        cue_duration_ms = max(0.0, (cue.end - cue.start) * 1000.0)
        cue_chars = _char_weight(cue.text)

        if current and (
            len(current) >= max_window_cues
            or current_chars + cue_chars > max_current_chars
            or current_duration_ms + cue_duration_ms > max_window_duration_ms
            or gap_ms >= scene_gap_ms
        ):
            flush()

        current.append((idx, cue))
        current_chars += cue_chars
        current_duration_ms += cue_duration_ms

    flush()
    return windows


def build_cloud_user_content(
    texts: list[str],
    *,
    before_context: list[tuple[str, str]] | None = None,
    after_context: list[str] | None = None,
    summary: str | None = None,
    strict_note: str | None = None,
) -> str:
    """Strict delimiter user prompt for cloud models.

    Context sections are explicitly read-only; the parser only ever consumes
    the numbered CURRENT CUES lines.
    """
    before_context = before_context or []
    after_context = after_context or []
    parts: list[str] = []

    if summary:
        parts.append("SCENE SUMMARY (read only; do not translate):")
        parts.append(summary.strip())
        parts.append("")

    if before_context:
        parts.append(
            "CONTEXT BEFORE (already translated; read only; do not translate):"
        )
        for source, translation in before_context:
            parts.append(f"- {source} => {translation}")
        parts.append("")

    if after_context:
        parts.append("CONTEXT AFTER (source only; read only; do not translate):")
        for source in after_context:
            parts.append(f"- {source}")
        parts.append("")

    parts.append(f"CURRENT CUES (translate exactly {len(texts)} numbered lines):")
    for i, text in enumerate(texts, start=1):
        parts.append(f"{i}. {text or ''}")
    parts.append("")
    if strict_note:
        parts.append(strict_note)
    parts.append(
        "Return only the numbered English translations for CURRENT CUES. "
        "Do not repeat context. Do not include labels. Do not change numbering."
    )
    return "\n".join(parts)


def build_hy_mt2_context_user_content(
    texts: list[str],
    *,
    source_language: str | None,
    glossary: str | None = None,
    before_context: list[tuple[str, str]] | None = None,
    after_context: list[str] | None = None,
) -> str:
    """Minimal-context Hy-MT2 user prompt (skill-compatible).

    Keeps the numbered protocol exact; context stays tiny (no summaries, no
    JSON) because Hy-MT2 is a small CPU model.
    """
    from .translate import (
        HY_MT2_TARGET_LANG,
        _HY_MT2_STYLE,
        _numbered_block,
    )

    block = _numbered_block([t or "" for t in texts])
    glossary_block = f"{glossary}\n\n" if glossary else ""
    context_parts: list[str] = []
    if before_context:
        context_parts.append("【上文参考（已翻译，仅供理解，不要输出）】")
        for source, translation in before_context:
            context_parts.append(f"- {source} => {translation}")
        context_parts.append("")
    if after_context:
        context_parts.append("【下文参考（原文，仅供理解，不要输出）】")
        for source in after_context:
            context_parts.append(f"- {source}")
        context_parts.append("")
    context_block = "\n".join(context_parts)

    if source_language:
        return (
            f"【背景信息】\n源语言：{source_language}\n文本类型：视频字幕\n\n"
            f"请结合背景信息将以下文本翻译为{HY_MT2_TARGET_LANG}。"
            f"{_HY_MT2_STYLE}\n\n{glossary_block}{context_block}"
            f"【待翻译文本（只需输出这些编号行的翻译）】\n{block}"
        )
    return (
        f"将以下文本翻译为{HY_MT2_TARGET_LANG}，"
        f"注意只需要输出编号行的翻译结果，不要额外解释。{_HY_MT2_STYLE}\n\n"
        f"{glossary_block}{context_block}{block}"
    )
