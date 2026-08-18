"""Optional cloud rescue for cues that failed local translation.

When enabled (``--cloud-rescue``), cues whose local translation failed or
produced empty text are re-translated via a cloud OpenAI-compatible endpoint.
Rescue is **off by default** and only ever touches failed cues — it never
modifies cues that already have a translation.

Key invariants:
    - Returns a mapping {cue_index: translated_text} for rescued cues only.
    - Never returns a full list (callers merge into existing results).
    - Uses the same numbered-item protocol as the main translation path.
    - Does not use the Hy-MT2 local style unless the rescue model *is* Hy-MT2.
"""
from __future__ import annotations

from typing import Sequence

from .srt_io import Cue
from .translate import (
    _is_hy_mt2,
    _numbered_block,
    _translate_batch,
    _translate_one_checked,
    _raise_if_fatal,
    build_hy_mt2_user_prompt,
    build_system_prompt,
    looks_untranslated,
)

DEFAULT_RESCUE_BATCH = 10


def _build_user_content(
    texts: list[str],
    hy_mt2: bool,
    source_language: str | None,
    glossary: str | None,
) -> str:
    """Build the user message for a rescue batch."""
    if hy_mt2:
        content = build_hy_mt2_user_prompt(texts, source_language)
        if glossary:
            content = f"{glossary}\n\n{content}"
        return content
    from .translate import _USER_INSTRUCTION

    parts = []
    if glossary:
        parts.append(glossary)
        parts.append("")
    parts.append(_USER_INSTRUCTION)
    parts.append(_numbered_block(texts))
    return "\n".join(parts)


def rescue_failed_cues(
    *,
    cues: Sequence[Cue],
    failed_indices: list[int],
    client,
    model: str,
    source_language: str | None = None,
    batch_size: int = DEFAULT_RESCUE_BATCH,
    max_retries: int = 3,
    glossary: str | None = None,
) -> dict[int, str]:
    """Re-translate failed cues via a cloud endpoint.

    Args:
        cues: The full cue list (used to extract source text by index).
        failed_indices: 0-based indices of cues that need rescue.
        client: An OpenAI-compatible client for the cloud endpoint.
        model: The cloud model name.
        source_language: Optional source language hint.
        batch_size: Max cues per rescue batch.
        max_retries: Retries per batch before per-item fallback.
        glossary: Optional formatted glossary string.

    Returns:
        A dict mapping {cue_index: translated_text} for successfully rescued
        cues only. Failed rescues are simply omitted from the dict.
    """
    if not failed_indices:
        return {}

    import time

    hy_mt2 = _is_hy_mt2(model)
    system_prompt: str | None = None
    temperature = 0.3
    extra_body = None

    if hy_mt2:
        from .translate import (
            HY_MT2_TEMPERATURE, HY_MT2_TOP_P, HY_MT2_TOP_K,
            HY_MT2_REPETITION_PENALTY,
        )
        temperature = HY_MT2_TEMPERATURE
        extra_body = {
            "top_p": HY_MT2_TOP_P, "top_k": HY_MT2_TOP_K,
            "repeat_penalty": HY_MT2_REPETITION_PENALTY,
        }
    else:
        system_prompt = build_system_prompt(source_language, glossary=glossary)

    print(f"[rescue] {len(failed_indices)} cues failed locally", flush=True)
    rescued: dict[int, str] = {}

    for start in range(0, len(failed_indices), batch_size):
        chunk_indices = failed_indices[start: start + batch_size]
        texts = [cues[idx].text for idx in chunk_indices]

        translated: list[str] | None = None
        for attempt in range(max_retries):
            try:
                user_content = _build_user_content(
                    texts, hy_mt2, source_language, glossary
                )
                translated = _translate_batch(
                    client, model, texts, system_prompt,
                    attempt=attempt, temperature=temperature,
                    user_content=user_content, extra_body=extra_body,
                )
            except Exception as exc:  # noqa: BLE001
                _raise_if_fatal(exc)  # broken endpoint -> abort, don't retry
                if extra_body is not None:
                    extra_body = None
                print(f"[rescue] batch error: {exc}", flush=True)
            if translated is not None and len(translated) == len(texts):
                break
            time.sleep(2 ** attempt)

        # Treat a batch reply as valid only when it aligns AND every line is a
        # genuine translation. Lines that are empty, echo the source, or are
        # full of non-target scripts are marked invalid so they get a clean
        # per-item second chance below (never "rescued" with the source text).
        if translated is None or len(translated) != len(texts):
            translated = [None] * len(texts)
        else:
            for i, (t, tr) in enumerate(zip(texts, translated)):
                if not tr or looks_untranslated(t, tr, source_language):
                    translated[i] = None

        for i, (idx, text) in enumerate(zip(chunk_indices, texts)):
            if translated[i] is not None:
                continue
            translated[i] = _translate_one_checked(
                client, model, text, system_prompt,
                hy_mt2=hy_mt2, source_language=source_language,
                glossary=glossary, temperature=temperature,
            )

        for idx, translation in zip(chunk_indices, translated):
            if translation and translation.strip():
                rescued[idx] = translation.strip()

    print(
        f"[rescue] Cloud rescue succeeded for {len(rescued)}/{len(failed_indices)} cues",
        flush=True,
    )
    return rescued
