"""Faithful English translation of subtitle cues via an OpenAI-compatible LLM.

Cues are translated in batches (default 40) for context and token efficiency.
Each batch is sent as numbered items and the model returns the same numbers,
so cue order/count stays aligned with the original timestamps.
"""
from __future__ import annotations

import re
import time

from openai import OpenAI

from .srt_io import Cue

# Foreignization directive: preserve the author's voice, cultural context, and
# intent; never domesticate to target-culture sensibilities. The [SOURCE LANGUAGE]
# / [TARGET LANGUAGE] placeholders are filled per run by build_system_prompt().
_FOREIGNIZATION_DIRECTIVE = """Role: You are an elite, highly precise, and culturally respectful translator. Your core philosophy is "Foreignization"—preserving the original author's voice, cultural context, and intent. You believe the target audience should adapt to the text's culture, not the other way around.

You will translate from [SOURCE LANGUAGE] to [TARGET LANGUAGE].

### Core Directives

1. Absolute Ideological & Political Neutrality:
   - Do not sanitize, modify, or censor the text to conform to modern social, political, or cultural sensitivities of the target culture.
   - If the source text contains controversial, sensitive, offensive, or politically incorrect elements, translate them with exact fidelity. Do not "soften" or rewrite lines to protect or preach to the audience.
   - Do not inject modern political terminology, social justice discourse, or localized cultural debates into the translation unless it is explicitly present in the source text.

2. Ban on Modern Slang & Anachronisms:
   - Absolutely forbid the injection of contemporary internet slang, memes, or transient target-language buzzwords (e.g., do not use terms like "mid," "cringe," "gaslighting," "toxic," "bussing" unless the original source text literally used their exact equivalents in the source language).
   - Match the historical, fantasy, or contemporary period of the source setting. If a story is set in a historical or fantasy era, the vocabulary must match that specific temporal register.

3. Nuance & Subtext Preservation (Register & Hierarchy):
   - Pay close attention to interpersonal relationships, social hierarchy, and relational distance.
   - Honorifics & Titles: If the source language uses honorifics, status indicators, or formal/informal pronouns (e.g., Japanese "-san/-kun", French "tu/vous", Korean speech levels), preserve this social distance. If the target language has no direct equivalent, use subtle tone shifts, vocabulary choices, or grammatical registers (formal vs. casual phrasing) to convey the relative social standing of the characters.
   - Do not flatten the text. If a character speaks with a highly poetic, archaic, or indirect subtext, preserve that exact level of obliqueness. Do not "explain" the subtext in the dialogue; let the reader infer it, just as a native speaker would.

4. Handling Cultural Specifics & Idioms:
   - Do not "Americanize" or domesticate cultural artifacts, food, or traditional practices (e.g., do not translate "onigiri" as "donut" or "rice ball" if the context demands its specific cultural identity; keep the native word or its closest literal translation).
   - Idioms: If an idiom makes zero sense when translated literally, do not replace it with a hyper-specific Western/modern equivalent. Instead, find a neutral equivalent that conveys the exact same semantic weight, or translate the literal metaphor if the context allows the reader to understand it through deductive reasoning.

5. Puns and Wordplay:
   - If a joke, pun, or wordplay relies entirely on the linguistic quirks of the source language and cannot be translated, prioritize maintaining the character's intent (e.g., if they are trying to be witty, make them witty; if they are making a terrible dad joke, keep it a terrible dad joke). Do not insert unrelated target-language pop-culture references to replace it.

### Output Format

Provide only the clean translation. If there is a highly complex pun, cultural reference, or linguistic double-entendre that is physically impossible to capture in the text without losing massive subtext, you may provide a brief, objective "[Translator's Note]" explaining the linguistic mechanics.

Crucial placement rule: when you add a [Translator's Note], place it on new lines DIRECTLY BELOW that item's translation, inside the same numbered item. Never place notes at the very end of the whole response, and never put a note above the translation it refers to. This keeps each note attached beneath its own translated line rather than altering the dialogue to force-fit it."""


def build_system_prompt(
    source_language: str | None, target_language: str = "English"
) -> str:
    """Fill the foreignization directive's language placeholders."""
    src = source_language or "the video's original language"
    return (
        _FOREIGNIZATION_DIRECTIVE.replace("[SOURCE LANGUAGE]", src)
        .replace("[TARGET LANGUAGE]", target_language)
    )

_USER_INSTRUCTION = (
    "Translate each numbered item into English. Respond with the same numbers, "
    "one translation per line, in the same order. Do not merge items, renumber, "
    "or add commentary.\n\n"
)

# --- Hy-MT2 skill prompts ---------------------------------------------------
# When the local model is Tencent's Hy-MT2 we follow the hy-mt2-translator skill
# (https://skillhub.cn/skills/hy-mt2-translator) instead of the foreignization
# directive. That skill prompts the model with a single user message (no system
# prompt) using Hy-MT2's own Chinese instruction wording, and offers 6 modes
# (basic / terminology / style / delimiter-preserving / structured-data /
# context). We keep our numbered-item protocol for cue alignment, use the skill's
# "context" mode when the source language is known, its "basic" mode otherwise,
# and fold the project's foreignization philosophy into the "style" it always
# applies — so the local model honors the same "keep the author's voice" invariant
# as the cloud path's system prompt.
_HY_MT2_HINTS = ("hy-mt2", "hy_mt2")
HY_MT2_TARGET_LANG = "英语"  # English, in the form the skill expects

# Sampling the Hy-MT2 model card recommends (https://huggingface.co/collections/
# tencent/hy-mt2). Temperature is kept low on purpose: the numbered-item protocol
# needs deterministic line numbering, and a chatty/higher-temp reply risks breaking
# alignment (we still fall back to per-item on a misalignment). The other card
# params are passed via extra_body to the local llama.cpp server.
HY_MT2_TEMPERATURE = 0.1
HY_MT2_TOP_P = 0.6
HY_MT2_TOP_K = 20
HY_MT2_REPETITION_PENALTY = 1.05

# Foreignization "style" we always ask the local model to honor — the same
# philosophy as the cloud path's _FOREIGNIZATION_DIRECTIVE, but written in Chinese
# because Hy-MT2 is a Chinese-trained MT model and the skill drives it with Chinese
# instructions. Without this the local path would get NO guidance to preserve
# voice/culture/honorifics, contradicting the project's core translation invariant.
_HY_MT2_STYLE = (
    "翻译时忠实保留原文的作者语气、文化语境与人际关系（敬语、社会地位、亲疏）；"
    "不要为迎合目标语读者而本土化、删改或注入现代俚语；"
    "若原文含敏感或争议内容，请照样直译，不要软化或说教。"
)


def _is_hy_mt2(model: str) -> bool:
    """True if `model` looks like a Tencent Hy-MT2 model."""
    m = (model or "").lower()
    return any(hint in m for hint in _HY_MT2_HINTS)


def _hy_mt2_single_prompt(text: str) -> str:
    """Skill 'basic' template for one text (used for per-item fallback)."""
    return (
        f"将以下文本翻译为{HY_MT2_TARGET_LANG}，"
        f"注意只需要输出翻译后的结果，不要额外解释。{_HY_MT2_STYLE}\n\n{text}"
    )


def build_hy_mt2_user_prompt(
    texts: list[str], source_language: str | None
) -> str:
    """User-message prompt for Hy-MT2, per the hy-mt2-translator skill.

    Wraps our numbered-item block in the skill's 'context' template (when the
    source language is known, giving the model disambiguation background) or its
    'basic' template otherwise. The foreignization philosophy is always appended
    as a 'style' so the local model preserves voice/culture/honorifics exactly
    like the cloud path's system prompt would.
    """
    block = _numbered_block(texts)
    if source_language:
        return (
            f"【背景信息】\n源语言：{source_language}\n文本类型：视频字幕\n\n"
            f"请结合背景信息将以下文本翻译为{HY_MT2_TARGET_LANG}。"
            f"{_HY_MT2_STYLE}\n\n"
            f"【待翻译文本】\n{block}"
        )
    return (
        f"将以下文本翻译为{HY_MT2_TARGET_LANG}，"
        f"注意只需要输出翻译后的结果，不要额外解释。{_HY_MT2_STYLE}\n\n{block}"
    )



def _numbered_block(texts: list[str]) -> str:
    return "\n".join(f"{i}. {t}" for i, t in enumerate(texts, start=1))


def _parse_numbered(response: str, expected: int) -> list[str] | None:
    """Map 'N. text' lines back to a list of `expected` translations, or None."""
    items: dict[int, list[str]] = {}
    current: int | None = None
    buf: list[str] = []
    for line in response.splitlines():
        m = re.match(r"^\s*(\d+)\.\s?(.*)$", line)
        if m:
            if current is not None:
                items[current] = buf
            current = int(m.group(1))
            buf = [m.group(2)]
        elif current is not None:
            buf.append(line)
    if current is not None:
        items[current] = buf

    if set(items.keys()) == set(range(1, expected + 1)):
        return ["\n".join(items[i]).strip() for i in range(1, expected + 1)]
    return None


def _translate_batch(
    client: OpenAI,
    model: str,
    texts: list[str],
    system_prompt: str,
    attempt: int = 0,
    temperature: float = 0.3,
    user_content: str | None = None,
    extra_body: dict | None = None,
) -> list[str] | None:
    strict = (
        "STRICT: output exactly %d lines, each starting with its number and a "
        "period, no extra text.\n\n" % len(texts)
        if attempt > 0
        else ""
    )
    # `user_content` lets callers (e.g. the Hy-MT2 skill path) supply their own
    # user message; otherwise we use the default numbered-item instruction.
    if user_content is None:
        user_content = strict + _USER_INSTRUCTION + _numbered_block(texts)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})
    kwargs: dict = {"model": model, "messages": messages, "temperature": temperature}
    # extra_body carries llama.cpp-only sampling params (top_k, repeat_penalty).
    # Passed only for the local Hy-MT2 path; the cloud path leaves it None.
    if extra_body:
        kwargs["extra_body"] = extra_body
    resp = client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""
    return _parse_numbered(content, len(texts))


def _translate_one(
    client: OpenAI,
    model: str,
    text: str,
    system_prompt: str,
    temperature: float = 0.3,
    user_content: str | None = None,
    extra_body: dict | None = None,
) -> str:
    """Per-item fallback when batch alignment fails."""
    if user_content is None:
        user_content = "Translate into English:\n\n" + text
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})
    kwargs: dict = {"model": model, "messages": messages, "temperature": temperature}
    if extra_body:
        kwargs["extra_body"] = extra_body
    resp = client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or text).strip()


def translate_cues(
    cues: list[Cue],
    client: OpenAI,
    model: str,
    batch_size: int = 40,
    max_retries: int = 3,
    source_language: str | None = None,
) -> list[str]:
    """Translate cue texts into English, preserving order. Returns translations."""
    # Hy-MT2 (local model) uses the hy-mt2-translator skill's prompt recipe: no
    # system prompt, the skill's own Chinese instruction wording, and the
    # model-card sampling params via extra_body. The foreignization philosophy is
    # folded into the user message (see _HY_MT2_STYLE) so it matches the cloud
    # path's directive.
    hy_mt2 = _is_hy_mt2(model)
    if hy_mt2:
        system_prompt: str | None = None
        temperature = HY_MT2_TEMPERATURE
        extra_body = {
            "top_p": HY_MT2_TOP_P,
            "top_k": HY_MT2_TOP_K,
            "repeat_penalty": HY_MT2_REPETITION_PENALTY,
        }
        print(
            f"  Using Hy-MT2 skill prompts (no system prompt, temp {temperature}, "
            f"top_p {HY_MT2_TOP_P}, top_k {HY_MT2_TOP_K}, "
            f"rep_penalty {HY_MT2_REPETITION_PENALTY}).",
            flush=True,
        )
    else:
        system_prompt = build_system_prompt(source_language)
        temperature = 0.3
        extra_body = None

    texts = [c.text for c in cues]
    out: list[str] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        translated: list[str] | None = None
        for attempt in range(max_retries):
            try:
                if hy_mt2:
                    user_content = build_hy_mt2_user_prompt(batch, source_language)
                    translated = _translate_batch(
                        client, model, batch, system_prompt,
                        attempt=attempt, temperature=temperature,
                        user_content=user_content, extra_body=extra_body,
                    )
                else:
                    translated = _translate_batch(
                        client, model, batch, system_prompt, attempt=attempt
                    )
            except Exception as exc:
                # A backend that rejects llama.cpp-only params (top_k /
                # repeat_penalty) raises here; drop extra_body and retry with just
                # temperature so we don't lose the batch.
                if extra_body is not None:
                    extra_body = None
                print(f"  [warn] batch {start}-{start+len(batch)} error: {exc}", flush=True)
            if translated is not None:
                break
            time.sleep(2 ** attempt)
        if translated is None:
            # Fall back to translating items individually so we never lose a cue.
            print(f"  [warn] batch {start} misaligned; translating item-by-item.", flush=True)
            if hy_mt2:
                translated = [
                    _translate_one(
                        client, model, t, system_prompt,
                        temperature=temperature,
                        user_content=_hy_mt2_single_prompt(t),
                        extra_body=extra_body,
                    )
                    for t in batch
                ]
            else:
                translated = [
                    _translate_one(client, model, t, system_prompt) for t in batch
                ]
        out.extend(translated)
        print(f"  translated {min(start + batch_size, len(texts))}/{len(texts)}", flush=True)

    return out
