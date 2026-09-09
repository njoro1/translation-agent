"""Faithful English translation of subtitle cues via an OpenAI-compatible LLM.

Cues are translated as context-aware windows: each window carries read-only
before/after context (previous translated pairs, upcoming source lines) while
the numbered-item protocol keeps cue order/count aligned with the original
timestamps. See src/translation_windows.py for the window engine.
"""
from __future__ import annotations

import re
import time

from openai import OpenAI

from .batching import is_cjk_language
from .srt_io import Cue


class TranslationEndpointError(RuntimeError):
    """Raised when the configured chat/completions endpoint is not an
    OpenAI-compatible LLM server (e.g. a web app / homepage answering HTTP
    404/405 on the /v1/chat/completions route). Retrying can never fix it, so
    translation aborts immediately instead of hanging in the retry/backoff
    ladder against the wrong endpoint."""


class TranslationCancelled(RuntimeError):
    """Raised when a GUI-requested cancel is observed between batches.

    translate.py turns this into a clean exit code (2) so the bridge can tell
    the user the run was stopped on purpose rather than failed."""


_FATAL_HTTP_STATUS = {404, 405, 501}


def _endpoint_fatal_message(exc: Exception) -> str | None:
    """Return an actionable message if ``exc`` is a fatal endpoint error.

    HTTP 404/405/501 on the chat/completions route mean the configured Base URL
    is *not* an OpenAI-compatible LLM server (it is a web page / router instead).
    Such errors never recover with retries, so callers abort rather than hang.
    Returns ``None`` for anything that might be transient (connection refused,
    rate limits, provider 5xx, etc.) so the normal retry ladder still applies.
    """
    status = getattr(exc, "status_code", None)
    if status in _FATAL_HTTP_STATUS:
        return (
            "The chat/completions endpoint returned HTTP {status}, which means it "
            "is not an OpenAI-compatible LLM server at /v1/chat/completions. "
            "Fix your Base URL (OPENAI_BASE_URL / Settings \u2192 Base URL). For the "
            "bundled local llama-server use 'http://127.0.0.1:8080/v1'; for a real "
            "cloud API use its actual /v1 URL. Do not point it at a website or "
            "home page."
        ).format(status=status)
    return None


def _raise_if_fatal(exc: Exception) -> None:
    """Raise TranslationEndpointError if ``exc`` indicates a broken endpoint."""
    fatal = _endpoint_fatal_message(exc)
    if fatal:
        raise TranslationEndpointError(fatal) from exc


class _PerfMetrics:
    """Aggregate token + generation-speed metrics from OpenAI/llama.cpp replies.

    Standard usage (prompt/completion counts) is read from ``resp.usage``;
    llama.cpp additionally returns a top-level ``timings`` object (exposed by the
    SDK as ``resp.model_extra``) with ``predicted_per_second`` (generation
    tokens/sec) and ``prompt_per_second``. Logging these makes it easy to see how
    the local CPU Hy-MT2 run is actually performing (throughput, token counts).
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.requests = 0
        self.gen_seconds = 0.0

    @staticmethod
    def _extract(resp) -> tuple[int | None, int | None, dict | None]:
        usage = getattr(resp, "usage", None)
        prompt = getattr(usage, "prompt_tokens", None) if usage is not None else None
        completion = (
            getattr(usage, "completion_tokens", None) if usage is not None else None
        )
        extra = getattr(resp, "model_extra", None) or {}
        timings = extra.get("timings") if isinstance(extra, dict) else None
        return prompt, completion, timings

    def add(self, resp) -> None:
        prompt, completion, timings = self._extract(resp)
        if prompt is None and completion is None:
            return
        self.prompt_tokens += prompt or 0
        self.completion_tokens += completion or 0
        self.requests += 1
        if isinstance(timings, dict):
            gen_ms = timings.get("predicted_ms")
            if isinstance(gen_ms, (int, float)) and gen_ms > 0:
                self.gen_seconds += gen_ms / 1000.0

    def print_call(self, resp, label: str) -> None:
        """Accumulate response metrics and print a one-line perf summary."""
        prompt, completion, timings = self._extract(resp)
        if prompt is None and completion is None:
            return
        # Always accumulate even if we have nothing to print yet.
        self.add(resp)
        parts: list[str] = []
        if prompt is not None:
            parts.append(f"prompt={prompt} tok")
        if completion is not None:
            parts.append(f"gen={completion} tok")
        if isinstance(timings, dict):
            gen_tok_s = timings.get("predicted_per_second")
            prompt_tok_s = timings.get("prompt_per_second")
            if isinstance(gen_tok_s, (int, float)):
                parts.append(f"{gen_tok_s:.1f} gen tok/s")
            if isinstance(prompt_tok_s, (int, float)):
                parts.append(f"{prompt_tok_s:.1f} prompt tok/s")
        if parts:
            print(f"[perf] {label}: " + ", ".join(parts), flush=True)

    def print_summary(self) -> None:
        """Print overall token totals for the whole run, if any requests happened."""
        if self.requests == 0:
            return
        total = self.prompt_tokens + self.completion_tokens
        parts = [
            f"TOTAL: {self.requests} requests",
            f"prompt={self.prompt_tokens} tok",
            f"gen={self.completion_tokens} tok",
            f"total={total} tok",
        ]
        if self.gen_seconds:
            parts.append(f"~{total / self.gen_seconds:.1f} overall tok/s")
        print("[perf] " + ", ".join(parts), flush=True)

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
    source_language: str | None,
    target_language: str = "English",
    *,
    glossary: str | None = None,
    chengyu: bool = False,
    classical: bool = False,
    emotion: bool = False,
    addendum: str | None = None,
) -> str:
    """Fill the foreignization directive's language placeholders.

    ``glossary``, when non-empty, is appended after the base directive so
    terminology is applied consistently without altering the core directive.

    ``chengyu`` / ``classical`` / ``emotion`` toggle fansub-quality augmentations
    (chengyu literal+functional rendering, Classical-Chinese register, and
    SenseVoice emotion-tag register awareness). These are appended to — never a
    replacement of — ``_FOREIGNIZATION_DIRECTIVE``.

    ``addendum`` (content-preset prompt profile) is a short scoped note
    appended after the directive; it never replaces or weakens it.
    """
    src = source_language or "the video's original language"
    prompt = (
        _FOREIGNIZATION_DIRECTIVE.replace("[SOURCE LANGUAGE]", src)
        .replace("[TARGET LANGUAGE]", target_language)
    )

    if chengyu:
        prompt += (
            "\n\nFor any term marked [CHENGYU:xxxx], provide the idiomatic "
            "English meaning followed by the literal meaning in parentheses, "
            'e.g. "add the finishing touch (lit. dot the eye on the dragon)". '
            "Remove the [CHENGYU:...] markup from your output."
        )

    if classical:
        prompt += (
            "\n\nThe source text contains Classical Chinese (文言文). Preserve "
            "its formal, archaic register in the English translation. Do not "
            "modernize the diction."
        )

    if emotion:
        prompt += (
            "\n\nIf the source text begins with a SenseVoice emotion tag such as "
            "<HAPPY>, <SAD>, <LAUGH>, use it to inform the natural register of "
            "the translation. Do not reproduce the tag in your output."
        )

    if addendum:
        prompt = prompt + "\n\n" + addendum.strip()

    if glossary:
        prompt = prompt + "\n\n" + glossary
    return prompt

_USER_INSTRUCTION = (
    "Translate each numbered item into English. Respond with the same numbers, "
    "one translation per line, in the same order. Do not merge items, renumber, "
    "and do NOT include any reasoning, commentary, or translation notes — output "
    "only the translation text after each number.\n\n"
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

# --- Hy-MT2 context-window budgets ------------------------------------------
# Hy-MT2 is a tiny CPU model; oversized windows increase the chance of missing
# numbered lines, malformed output, or context overflow. These limits can be
# overridden via environment variables.
import os as _os

HY_MT2_DEFAULT_MAX_BATCH_CUES = int(
    _os.environ.get("HY_MT2_MAX_BATCH_CUES", "12")
)
HY_MT2_MAX_BATCH_CHARS_CJK = int(
    _os.environ.get("HY_MT2_MAX_BATCH_CHARS_CJK", "700")
)
HY_MT2_MAX_BATCH_CHARS_NON_CJK = int(
    _os.environ.get("HY_MT2_MAX_BATCH_CHARS_NON_CJK", "1000")
)

# Maximum recursion depth for the batch-split fallback ladder.
MAX_SPLIT_DEPTH = 8

# --- Fansub-quality helpers --------------------------------------------------
# SenseVoice emits a leading tag group per utterance: an optional language tag
# (`<|zh|>`), then emotion/event/itn tags (`<|ANGRY|>`, `<|BGM|>`, `<|withitn|>`).
# The documented shorthand is `<HAPPY>`. These are preserved through ASR only to
# steer the translation register; they must ALWAYS be stripped from the final
# output (SRT/ASS). The regex matches a leading run of `|<token|>` markers
# (language code may be lowercase, e.g. `zh`) plus an optional `<STYLE>` tag.
_LEAD_TAG_ATOM = r"(?:<\|[a-zA-Z0-9_]+\|>|<[A-Za-z_]+>)"
_SENSEVOICE_TAG_RE = re.compile(r"^(?:" + _LEAD_TAG_ATOM + r")+(?:\s*)")

# Residual `[CHENGYU:...]` wrapper leaked by the model echoing the flagged prompt.
# If the model copies the chengyu markup back into its answer instead of a clean
# translation, the wrapper must not reach the SRT. The local model often emits the
# wrapper WITHOUT a closing bracket ("[CHENGYU: many people"), so both the closed
# `[CHENGYU:x]` and the bare `[CHENGYU:` prefix are matched.
_RESIDUAL_CHENGYU_RE = re.compile(r"\[CHENGYU:([^\]]*)\]|\[CHENGYU:")

# Four consecutive CJK characters — a candidate 成语 (chengyu) idiom. These get
# wrapped in [CHENGYU:...] markup so the model supplies a literal + functional
# rendering rather than a flat translation.
_CHENGYU_RE = re.compile(r"[\u4e00-\u9fff]{4}")

# Characters suggestive of Classical Chinese (文言文).
_CLASSICAL_MARKERS = frozenset([
    "之", "乎", "者", "也", "矣", "焉", "哉", "乃", "夫", "兮",
])


def _flag_chengyu(text: str) -> str:
    """Wrap detected 4-char CJK sequences in [CHENGYU:...] for prompt awareness."""
    return _CHENGYU_RE.sub(lambda m: f"[CHENGYU:{m.group(0)}]", text)


def _strip_sensevoice_tag(text: str) -> str:
    """Remove a leading SenseVoice emotion/event tag from translated text.

    The tag is used to steer the translation register but must never appear in
    the final SRT/ASS output. Handles a full leading tag group (which may include
    the language tag `<|zh|>`) so it can never leak through, and also repairs any
    `[CHENGYU:...]` wrapper the model echoed back.
    """
    text = _SENSEVOICE_TAG_RE.sub("", text)
    text = _RESIDUAL_CHENGYU_RE.sub(lambda m: (m.group(1) or "").strip(), text)
    return text.strip()


def _is_classical_chinese(text: str) -> bool:
    """Heuristic: True when a chunk of CJK text looks like Classical Chinese.

    A Classical-Chinese cue has a high density of the ubiquitous function
    characters (之乎者也矣焉哉乃夫兮). We require a minimum of CJK chars and a
    marker ratio above a threshold before flagging, so modern Chinese sentences
    that happen to contain one of these characters are not misclassified.
    """
    chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    if len(chars) < 8:
        return False
    marker_count = sum(1 for c in chars if c in _CLASSICAL_MARKERS)
    return marker_count / len(chars) > 0.12


def _detect_cjk_lang(text: str) -> str | None:
    """Heuristic: return 'zh', 'ja', or 'ko' based on dominant script.

    Returns ``None`` if undetermined (no CJK found or ratios too mixed to be
    confident). Used to fill in the source language for the translation prompt
    when ``--asr-lang`` was left at 'auto'.
    """
    zh = ko = ja = 0
    for ch in text:
        cp = ord(ch)
        if 0xAC00 <= cp <= 0xD7A3:
            ko += 1
        elif 0x3040 <= cp <= 0x30FF:
            ja += 1
        elif 0x4E00 <= cp <= 0x9FFF:
            zh += 1
    total = zh + ko + ja
    if total == 0:
        return None
    if ko / total > 0.4:
        return "ko"
    if ja / total > 0.3:
        return "ja"
    if zh / total > 0.3:
        return "zh"
    return None

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


def _hy_mt2_single_prompt(text: str, glossary: str | None = None) -> str:
    """Skill 'basic' template for one text (used for per-item fallback)."""
    glossary_block = f"{glossary}\n\n" if glossary else ""
    return (
        f"将以下文本翻译为{HY_MT2_TARGET_LANG}，"
        f"注意只需要输出翻译后的结果，不要额外解释。{_HY_MT2_STYLE}\n\n{glossary_block}{text}"
    )


def build_hy_mt2_user_prompt(
    texts: list[str],
    source_language: str | None,
    glossary: str | None = None,
) -> str:
    """User-message prompt for Hy-MT2, per the hy-mt2-translator skill.

    Wraps our numbered-item block in the skill's 'context' template (when the
    source language is known, giving the model disambiguation background) or its
    'basic' template otherwise. The foreignization philosophy is always appended
    as a 'style' so the local model preserves voice/culture/honorifics exactly
    like the cloud path's system prompt would.

    If ``glossary`` is non-empty it is inserted after the style text and before
    the numbered source lines.
    """
    block = _numbered_block(texts)
    glossary_block = f"{glossary}\n\n" if glossary else ""
    if source_language:
        return (
            f"【背景信息】\n源语言：{source_language}\n文本类型：视频字幕\n\n"
            f"请结合背景信息将以下文本翻译为{HY_MT2_TARGET_LANG}。"
            f"{_HY_MT2_STYLE}\n\n{glossary_block}"
            f"【待翻译文本】\n{block}"
        )
    return (
        f"将以下文本翻译为{HY_MT2_TARGET_LANG}，"
        f"注意只需要输出翻译后的结果，不要额外解释。{_HY_MT2_STYLE}\n\n{glossary_block}{block}"
    )



def _numbered_block(texts: list[str]) -> str:
    return "\n".join(f"{i}. {t}" for i, t in enumerate(texts, start=1))


def _parse_numbered(response: str, expected: int) -> list[str] | None:
    """Map 'N. text' lines back to a list of `expected` translations, or None."""
    items: dict[int, list[str]] = {}
    counts: dict[int, int] = {}
    current: int | None = None
    buf: list[str] = []
    for line in response.splitlines():
        m = re.match(r"^\s*(\d+)\.\s?(.*)$", line)
        if m:
            if current is not None:
                items[current] = buf
            current = int(m.group(1))
            counts[current] = counts.get(current, 0) + 1
            buf = [m.group(2)]
        elif current is not None:
            buf.append(line)
    if current is not None:
        items[current] = buf

    # A number appearing more than once is ambiguous -> invalid.
    if any(count > 1 for count in counts.values()):
        return None

    if set(items.keys()) == set(range(1, expected + 1)):
        return ["\n".join(items[i]).strip() for i in range(1, expected + 1)]
    return None

# --- Output validation ------------------------------------------------------
# Detects model replies that are NOT real translations so they can be retried,
# flagged, or counted. A bad reply must not reach the output as a translation.
# reply used to become the SRT line verbatim (see SUBTITLE_QUALITY_REPORT §3): a
# third of the analyzed cues were untranslated Chinese shipped as "translated".
_CJK_IDEOGRAPHS = "\u3400-\u4dbf\u4e00-\u9fff"  # CJK Ext A + Unified Ideographs
_HANGUL = "\uac00-\ud7af"


def _cjk_count(text: str) -> int:
    """Number of CJK ideograph + Hangul characters in ``text``."""
    return sum(
        1 for ch in text
        if "\u3400" <= ch <= "\u4dbf"
        or "\u4e00" <= ch <= "\u9fff"
        or "\uac00" <= ch <= "\ud7af"
    )


def looks_untranslated(
    source_text: str,
    translation: str,
    source_language: str | None,
) -> bool:
    """Return True when ``translation`` cannot be trusted as a translation.

    Used on every returned line (batch and per-item alike) so that an empty
    reply, a source echo, or a reply full of non-target scripts is treated as a
    *failure* — never silently shipped or cached.

    1. Empty / whitespace-only replies are failures.
    2. A reply that exactly repeats the source (after whitespace folding) is a
       passthrough, not a translation.
    3. When the source is a CJK language (zh/ja/ko/yue) and the target is
       English: Korean Hangul is always a red flag (it never belongs in an
       English subtitle line), and a reply whose non-whitespace characters are
       mostly CJK ideographs is essentially untranslated source text.
    4. A short reply that still contains CJK is treated as code-switching
       corruption (e.g. ``Super加倍``), while a long reply with a tiny CJK ratio
       (a proper name, say) is tolerated — callers log those as warnings.
    """
    if not translation or not translation.strip():
        return True
    folded_t = re.sub(r"\s+", " ", translation.strip()).lower()
    folded_s = re.sub(r"\s+", " ", (source_text or "").strip()).lower()
    if folded_s and folded_t == folded_s:
        return True

    if not is_cjk_language(source_language):
        # Non-CJK source: only the generic empty/passthrough rules apply.
        return False

    non_space = "".join(translation.split())
    if not non_space:
        return True
    if re.search(_HANGUL, non_space):
        return True
    cjk = _cjk_count(non_space)
    if cjk == 0:
        return False
    if cjk / len(non_space) >= 0.5:
        return True
    if len(non_space) <= 24:
        return True
    return False

def _translate_batch(
    client: OpenAI,
    model: str,
    texts: list[str],
    system_prompt: str,
    attempt: int = 0,
    temperature: float = 0.3,
    user_content: str | None = None,
    extra_body: dict | None = None,
    metrics: _PerfMetrics | None = None,
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
    if metrics is not None:
        metrics.print_call(
            resp, f"batch ({len(texts)} cues{', attempt ' + str(attempt + 1) if attempt else ''})"
        )
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
    metrics: _PerfMetrics | None = None,
) -> str:
    """Per-item fallback when batch alignment fails."""
    if user_content is None:
        user_content = "Translate into English. Do NOT include reasoning or commentary; output only the translation.\n\n" + text
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})
    kwargs: dict = {"model": model, "messages": messages, "temperature": temperature}
    if extra_body:
        kwargs["extra_body"] = extra_body
    resp = client.chat.completions.create(**kwargs)
    if metrics is not None:
        metrics.print_call(resp, "single item")
    # Never fall back to the source text here: an empty reply is a failure, and
    # the caller decides how to surface it (retry / flag) instead of
    # silently shipping the untranslated source as if it were a translation.
    return (resp.choices[0].message.content or "").strip()


def _translate_group(
    client,
    model,
    texts: list[str],
    system_prompt: str | None,
    *,
    source_language: str | None,
    hy_mt2: bool,
    max_retries: int,
    depth: int = 0,
    glossary: str | None = None,
    extra_body: dict | None = None,
    temperature: float = 0.3,
    metrics: _PerfMetrics | None = None,
    user_content_builder=None,
) -> list[str] | None:
    """Translate a group of texts with a robust fallback ladder.

    Ladder:
        1. If empty, return [].
        2. If single item, use _translate_one.
        3. Try _translate_batch with retries (STRICT instruction on retry).
        4. If still failing and len(texts) > 1, split in half and recurse.
        5. If depth exceeds MAX_SPLIT_DEPTH, fall back to per-item.

    ``user_content_builder(texts, attempt) -> str``, when provided, builds the
    user message for each attempt (used by the context-window engine so
    before/after context survives recursive splitting). It overrides both the
    default numbered block and the Hy-MT2 skill prompt.

    Returns a list of translations (same length as ``texts``) or None if the
    group could not be translated at all (caller decides what to do).
    """
    if not texts:
        return []

    # Depth guard: stop splitting and go per-item.
    if depth > MAX_SPLIT_DEPTH:
        return _per_item_translate(
            client, model, texts, system_prompt,
            source_language=source_language, hy_mt2=hy_mt2,
            glossary=glossary, extra_body=extra_body,
            temperature=temperature, metrics=metrics,
        )

    # Single item without a context builder: translate directly. With a
    # builder (context-window path), even a one-cue window keeps its context
    # by going through the batch protocol first.
    if len(texts) == 1 and user_content_builder is None:
        return _per_item_translate(
            client, model, texts, system_prompt,
            source_language=source_language, hy_mt2=hy_mt2,
            glossary=glossary, extra_body=extra_body,
            temperature=temperature, metrics=metrics,
        )

    # Try batch translation with retries.
    translated: list[str] | None = None
    for attempt in range(max_retries):
        try:
            if user_content_builder is not None:
                user_content = user_content_builder(texts, attempt)
            elif hy_mt2:
                user_content = build_hy_mt2_user_prompt(
                    texts, source_language, glossary=glossary
                )
            else:
                user_content = None  # _translate_batch builds default
            translated = _translate_batch(
                client, model, texts, system_prompt,
                attempt=attempt, temperature=temperature,
                user_content=user_content, extra_body=extra_body,
                metrics=metrics,
            )
        except Exception as exc:  # noqa: BLE001
            _raise_if_fatal(exc)  # broken endpoint -> abort immediately
            if extra_body is not None:
                extra_body = None
            print(
                f"  [translate] Batch error (depth {depth}, "
                f"{len(texts)} cues): {exc}",
                flush=True,
            )
        if translated is not None and len(translated) == len(texts):
            return translated
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    # Batch failed after retries: split in half and recurse.
    if len(texts) > 1:
        mid = len(texts) // 2
        left = texts[:mid]
        right = texts[mid:]
        print(
            f"  [translate] Batch failed; splitting into 2 smaller batches "
            f"({len(left)} + {len(right)})",
            flush=True,
        )
        left_result = _translate_group(
            client, model, left, system_prompt,
            source_language=source_language, hy_mt2=hy_mt2,
            max_retries=max_retries, depth=depth + 1,
            glossary=glossary, extra_body=extra_body,
            temperature=temperature, metrics=metrics,
            user_content_builder=user_content_builder,
        )
        right_result = _translate_group(
            client, model, right, system_prompt,
            source_language=source_language, hy_mt2=hy_mt2,
            max_retries=max_retries, depth=depth + 1,
            glossary=glossary, extra_body=extra_body,
            temperature=temperature, metrics=metrics,
            user_content_builder=user_content_builder,
        )
        if left_result is not None and right_result is not None:
            return left_result + right_result
        # If one half succeeded and the other didn't, fill failed half with
        # per-item results (best effort) so we never lose cues.
        if left_result is not None:
            right_result = _per_item_translate(
                client, model, right, system_prompt,
                source_language=source_language, hy_mt2=hy_mt2,
                glossary=glossary, extra_body=extra_body,
                temperature=temperature, metrics=metrics,
            )
            return left_result + right_result
        if right_result is not None:
            left_result = _per_item_translate(
                client, model, left, system_prompt,
                source_language=source_language, hy_mt2=hy_mt2,
                glossary=glossary, extra_body=extra_body,
                temperature=temperature, metrics=metrics,
            )
            return left_result + right_result

    # All attempts failed: per-item fallback.
    return _per_item_translate(
        client, model, texts, system_prompt,
        source_language=source_language, hy_mt2=hy_mt2,
        glossary=glossary, extra_body=extra_body,
        temperature=temperature, metrics=metrics,
    )


def _translate_one_checked(
    client,
    model,
    text: str,
    system_prompt: str | None,
    *,
    hy_mt2: bool,
    source_language: str | None,
    glossary: str | None = None,
    extra_body: dict | None = None,
    temperature: float = 0.3,
    metrics: _PerfMetrics | None = None,
) -> str:
    """Per-item translation with one degraded retry + output validation.

    Returns the translated text, or ``""`` when the model produced nothing
    usable (empty reply, source echo, Hangul, or mostly-CJK output). It never
    returns the source text as a "translation": a failed cue must be surfaced
    as a failure (counted / flagged) rather than silently shipped untranslated.

    The second attempt drops the llama.cpp-only sampling params (``extra_body``)
    and slightly raises temperature for diversity — a cheap "degraded prompt"
    retry before giving up on the cue.
    """
    attempts = [
        (temperature, extra_body),
        (min(temperature + 0.2, 0.7), None),
    ]
    for attempt_temp, attempt_body in attempts:
        try:
            if hy_mt2:
                result = _translate_one(
                    client, model, text, system_prompt,
                    temperature=attempt_temp,
                    user_content=_hy_mt2_single_prompt(text, glossary=glossary),
                    extra_body=attempt_body, metrics=metrics,
                )
            else:
                result = _translate_one(
                    client, model, text, system_prompt,
                    temperature=attempt_temp, metrics=metrics,
                )
        except Exception as exc:  # noqa: BLE001
            _raise_if_fatal(exc)  # broken endpoint -> abort immediately
            print(f"  [translate] Per-item request failed: {exc}", flush=True)
            continue
        if result and not looks_untranslated(text, result, source_language):
            return result
        print(
            f"  [translate] Per-item result rejected (untranslated/invalid): {result!r}",
            flush=True,
        )
    return ""


def _per_item_translate(
    client,
    model,
    texts: list[str],
    system_prompt: str | None,
    *,
    source_language: str | None,
    hy_mt2: bool,
    glossary: str | None = None,
    extra_body: dict | None = None,
    temperature: float = 0.3,
    metrics: _PerfMetrics | None = None,
) -> list[str]:
    """Translate each text individually (per-item fallback).

    Each item goes through ``_translate_one_checked``, so a failed cue comes
    back as ``""`` (never the source text). Callers treat ``""`` as
    "untranslated" and count or flag it in the output.
    """
    results: list[str] = []
    for text in texts:
        results.append(
            _translate_one_checked(
                client, model, text, system_prompt,
                hy_mt2=hy_mt2, source_language=source_language,
                glossary=glossary, extra_body=extra_body,
                temperature=temperature, metrics=metrics,
            )
        )
    return results



def _maybe_update_scene_summary(
    client,
    model,
    summary: str,
    recent_sources: list[str],
    metrics: _PerfMetrics | None = None,
) -> str:
    """Refresh the rolling cloud scene summary (2-3 sentences max).

    Never raises: on any failure the previous summary is kept. The summary is
    read-only context — it can never alter cue count or numbering.
    """
    try:
        excerpt = "\n".join(f"- {s}" for s in recent_sources[-40:] if s)
        old = f"Current summary:\n{summary}\n\n" if summary else ""
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You maintain a brief running summary of a video's "
                        "story so subtitle translations stay coherent.\n\n"
                        f"{old}New dialogue excerpt:\n{excerpt}\n\n"
                        "Update the summary in at most 3 short sentences: "
                        "who is present, where they are, and the current "
                        "situation/tone. Output ONLY the summary text."
                    ),
                }
            ],
            temperature=0.2,
        )
        if metrics is not None:
            metrics.print_call(resp, "scene summary")
        text = (resp.choices[0].message.content or "").strip()
        text = " ".join(text.split())
        return text[:600] if text else summary
    except Exception as exc:  # noqa: BLE001 - summary is best-effort only
        print(f"[context] Scene summary update failed (kept previous): {exc}",
              flush=True)
        return summary


def translate_cues(
    cues: list[Cue],
    client: OpenAI,
    model: str,
    batch_size: int = 8,
    max_retries: int = 3,
    source_language: str | None = None,
    *,
    glossary: str | None = None,
    translation_memory=None,
    context_mode: str | None = None,
    prompt_profile: str | None = None,
    progress_callback=None,
    scene_summary_enabled: bool = False,
    cancel_check=None,
) -> list[str]:
    """Translate cue texts into English, preserving order. Returns translations.

    Cues are translated as context-aware :class:`TranslationWindow` units:
    each window carries read-only before/after context while the numbered-item
    protocol keeps cue count in == cue count out.

    Keyword-only arguments (additive — existing callers ignore them):
        glossary: Formatted glossary string injected into prompts.
        translation_memory: A ``TranslationMemory`` instance (or None).
        context_mode: off/light/standard/deep; None -> backend default
            (light for local Hy-MT2, standard for cloud).
        prompt_profile: Content-preset profile selecting a scoped prompt
            addendum (never replaces the core directive).
        progress_callback: ``callable(done, total, stage)`` invoked after each
            window finalizes.
        scene_summary_enabled: Cloud-only rolling scene summary (experimental).
        cancel_check: Optional ``callable() -> bool`` polled before each
            window; returning True raises :class:`TranslationCancelled` so a
            GUI stop button stops promptly between LLM calls.
    """
    import hashlib

    from .presets import get_prompt_addendum
    from .translation_windows import (
        CONTEXT_PROFILES,
        DEFAULT_MAX_WINDOW_CUES,
        DEFAULT_MAX_WINDOW_DURATION_MS,
        DEFAULT_SCENE_GAP_MS,
        HY_MT2_MAX_CHARS_CJK,
        HY_MT2_MAX_CHARS_NON_CJK,
        HY_MT2_MAX_WINDOW_CUES,
        build_cloud_user_content,
        build_hy_mt2_context_user_content,
        build_windows,
        resolve_context_mode,
    )

    total = len(cues)
    if total == 0:
        return []

    texts = [c.text for c in cues]
    results: list[str] = [""] * total

    hy_mt2 = _is_hy_mt2(model)
    addendum = get_prompt_addendum(prompt_profile)
    if addendum:
        print(f"[prompt] Content addendum applied ({prompt_profile}).", flush=True)

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
        system_prompt = build_system_prompt(
            source_language, glossary=glossary, addendum=addendum
        )
        temperature = 0.3
        extra_body = None

    # --- Context mode resolution --------------------------------------------
    # Precedence: explicit flag/preset value > backend default.
    mode = resolve_context_mode(context_mode, local=hy_mt2)
    before_pairs, after_cues, memory_pairs = CONTEXT_PROFILES[mode]
    if scene_summary_enabled and hy_mt2:
        print(
            "[context] --context-summary is cloud-only; ignoring for Hy-MT2.",
            flush=True,
        )
        scene_summary_enabled = False
    use_context = mode != "off"
    print(
        f"[context] mode={mode}"
        + (f", summary={'on' if scene_summary_enabled else 'off'}" if not hy_mt2 else "")
        + ("" if use_context else " (no context sections)")
        + f"; before={before_pairs} after={after_cues} memory={memory_pairs}",
        flush=True,
    )

    # --- Window budgets ------------------------------------------------------
    if hy_mt2:
        max_window_cues = max(1, min(batch_size, HY_MT2_MAX_WINDOW_CUES))
        max_window_chars = (
            HY_MT2_MAX_CHARS_CJK
            if is_cjk_language(source_language)
            else HY_MT2_MAX_CHARS_NON_CJK
        )
    else:
        max_window_cues = max(1, min(batch_size, DEFAULT_MAX_WINDOW_CUES))
        max_window_chars = 8000

    # --- Fansub augmentations: chengyu flagging ------------------------------
    # ``prompt_texts`` are what actually reaches the model:
    #   * For a Chinese (zh) source, 4-char idioms are wrapped in [CHENGYU:...]
    #     so the model renders a literal + functional meaning, not a flat gloss.
    #   * The original string is preserved (including any leading SenseVoice
    #     emotion tag) — we translate that augmented text but validate and cache
    #     against the original ``texts`` (and strip emotion tags from output).
    #
    # The chengyu markup is disabled for the local Hy-MT2 path: that small CPU
    # model does not follow the "remove the [CHENGYU:...] markup" instruction
    # and echoes the brackets back-to-back with no separators, producing run-on
    # ("childDidn't", "eyebrowsApply") and leaked-marker subtitles. Plain source
    # yields clean, well-formed translations. Cloud models that honor the
    # directive still get it.
    is_chinese_source = bool(source_language and str(source_language).lower() in (
        "zh", "chinese", "zho", "chi", "chs", "cht", "zh-cn", "zh-tw"
    ))
    _chengyu_flag = bool(is_chinese_source and not hy_mt2)
    prompt_texts = [
        _flag_chengyu(t) if _chengyu_flag else t
        for t in texts
    ]

    # --- Translation memory lookup (per cue) ---------------------------------
    model_profile = "hy-mt2-local" if hy_mt2 else f"cloud:{model}"
    g_hash = hashlib.sha256((glossary or "").encode("utf-8")).hexdigest()

    tm_hit: dict[int, bool] = {}
    if translation_memory and translation_memory.enabled:
        hits = 0
        for idx in range(total):
            cached = translation_memory.get(
                source_language=source_language,
                source_text=texts[idx],
                model_profile=model_profile,
                glossary_hash=g_hash,
            )
            if cached:
                results[idx] = cached
                tm_hit[idx] = True
                hits += 1
        if hits:
            print(
                f"[tm] {hits} cache hits, {total - hits} to translate",
                flush=True,
            )

    # --- Build context windows ------------------------------------------------
    windows = build_windows(
        cues,
        max_window_cues=max_window_cues,
        max_window_duration_ms=DEFAULT_MAX_WINDOW_DURATION_MS,
        scene_gap_ms=DEFAULT_SCENE_GAP_MS,
        max_current_chars=max_window_chars,
    )
    print(
        f"[translate] Context windows: {total} cues -> {len(windows)} "
        f"windows (mode={mode}, max {max_window_cues} cues / "
        f"{max_window_chars} chars per window)",
        flush=True,
    )

    rolling_memory: list[tuple[str, str]] = []
    summary_text = ""
    windows_since_summary = 0
    metrics = _PerfMetrics()
    done_count = 0

    def _extend_rolling(idxs: list[int]) -> None:
        if memory_pairs <= 0:
            return
        for gi in idxs:
            tr = results[gi]
            if tr and tr.strip():
                rolling_memory.append((texts[gi], tr))
        del rolling_memory[:-memory_pairs]

    for wi, window in enumerate(windows):
        if cancel_check is not None and cancel_check():
            raise TranslationCancelled(
                "Translation cancelled by the user."
            )
        idxs = list(
            range(window.start_index, window.start_index + len(window.cues))
        )
        subset_original = [texts[gi] for gi in idxs]
        subset_prompt = [prompt_texts[gi] for gi in idxs]

        # Attach read-only context for THIS attempt.
        before_ctx = (
            list(rolling_memory[-before_pairs:]) if use_context and before_pairs else []
        )
        nxt = windows[wi + 1] if wi + 1 < len(windows) else None
        after_ctx = (
            [c.text or "" for c in nxt.cues[:after_cues]]
            if use_context and after_cues and nxt is not None
            else []
        )

        def _builder(subset: list[str], attempt: int, _b=list(before_ctx),
                     _a=list(after_ctx)) -> str:
            strict = (
                f"STRICT: output exactly {len(subset)} numbered lines, no extra "
                "text."
                if attempt > 0
                else None
            )
            if hy_mt2:
                return build_hy_mt2_context_user_content(
                    subset,
                    source_language=source_language,
                    glossary=glossary,
                    before_context=_b,
                    after_context=_a,
                )
            return build_cloud_user_content(
                subset,
                before_context=_b,
                after_context=_a,
                summary=summary_text if use_context else None,
                strict_note=strict,
            )

        # Per-window TM decision: an all-hit window is served entirely from
        # TM (no LLM call); a partial hit window goes to the LLM whole so the
        # translation stays contextually coherent, then TM is updated.
        n_hits = sum(1 for gi in idxs if tm_hit.get(gi))
        if n_hits == len(idxs):
            done_count += len(idxs)
            _extend_rolling(idxs)
            if progress_callback is not None:
                progress_callback(done_count, total, "translate")
            continue

        # Per-window system-prompt augmentation: classical-Chinese register
        # (when any cue looks like 文言文) and emotion-tag awareness (when any
        # cue carries a SenseVoice emotion prefix).
        batch_classical = bool(subset_original) and any(
            _is_classical_chinese(t) for t in subset_original
        )
        batch_emotion = any(
            bool(_SENSEVOICE_TAG_RE.match(t or "")) for t in subset_original
        )
        if hy_mt2:
            window_system_prompt: str | None = None
        else:
            window_system_prompt = build_system_prompt(
                source_language,
                glossary=glossary,
                addendum=addendum,
                chengyu=_chengyu_flag,
                classical=batch_classical,
                emotion=batch_emotion,
            )

        print(
            f"[translate] window {wi + 1}/{len(windows)}: "
            f"{len(subset_original)} cues"
            + (f" ({n_hits} TM hits re-translated for context)" if n_hits else ""),
            flush=True,
        )

        group_result = _translate_group(
            client, model, subset_prompt, window_system_prompt,
            source_language=source_language, hy_mt2=hy_mt2,
            max_retries=max_retries, glossary=glossary,
            extra_body=dict(extra_body) if extra_body else None,
            temperature=temperature, metrics=metrics,
            user_content_builder=_builder,
        )

        used_per_item = group_result is None
        if used_per_item:
            group_result = _per_item_translate(
                client, model, subset_prompt, window_system_prompt,
                source_language=source_language, hy_mt2=hy_mt2,
                glossary=glossary, extra_body=extra_body,
                temperature=temperature, metrics=metrics,
            )

        # Validate every returned line. A reply that is empty, echoes the
        # source, or is full of non-target scripts (CJK / Hangul) is NOT a
        # translation — it must never reach the SRT or the translation
        # memory. Such lines are left "" so callers can count and flag
        # them explicitly instead of shipping untranslated text.
        failed_local: list[int] = []
        for li, (src, tr) in enumerate(zip(subset_original, group_result)):
            if not tr or not tr.strip() or looks_untranslated(src, tr, source_language):
                failed_local.append(li)
                results[idxs[li]] = ""
            else:
                results[idxs[li]] = _strip_sensevoice_tag(tr)
                if _cjk_count(tr) > 0:
                    print(
                        f"[translate] Cue {idxs[li]} has residual "
                        f"CJK in English output: {tr!r}",
                        flush=True,
                    )

        # A *window* that smuggled untranslated lines through alignment gets
        # one clean per-item retry with a single-cue prompt. Single-cue
        # groups were already handled by _translate_one_checked (which has
        # its own retry), so they are not re-tried here.
        if failed_local and not used_per_item and len(subset_original) > 1:
            print(
                f"[translate] Retrying {len(failed_local)} rejected cue(s) "
                f"per-item: {[subset_original[li] for li in failed_local]!r}",
                flush=True,
            )
            retried = _per_item_translate(
                client, model, [subset_prompt[li] for li in failed_local],
                window_system_prompt,
                source_language=source_language, hy_mt2=hy_mt2,
                glossary=glossary, extra_body=extra_body,
                temperature=temperature, metrics=metrics,
            )
            for li, retr in zip(failed_local, retried):
                if retr and retr.strip():
                    if not looks_untranslated(
                        subset_original[li], retr, source_language
                    ):
                        results[idxs[li]] = _strip_sensevoice_tag(retr)

        # Cache every *validated* translation in the translation memory
        # (including partial-TM windows, whose entries are overwritten with
        # the fresh in-context translations).
        if translation_memory and translation_memory.enabled:
            stored = 0
            for gi in idxs:
                translation = results[gi]
                src = texts[gi]
                if (
                    translation
                    and translation.strip()
                    and not looks_untranslated(src, translation, source_language)
                ):
                    translation_memory.put(
                        source_language=source_language,
                        source_text=src,
                        translated_text=translation,
                        model_profile=model_profile,
                        glossary_hash=g_hash,
                    )
                    stored += 1
            if stored:
                print(f"[tm] Stored {stored} new translations", flush=True)

        _extend_rolling(idxs)
        done_count += len(idxs)
        if progress_callback is not None:
            progress_callback(done_count, total, "translate")

        # Rolling cloud scene summary: refresh periodically; failure keeps
        # the previous summary and never affects alignment.
        if scene_summary_enabled and not hy_mt2:
            windows_since_summary += 1
            if windows_since_summary >= 15 or wi == 0:
                windows_since_summary = 0
                summary_text = _maybe_update_scene_summary(
                    client, model, summary_text,
                    [t for t in texts[max(0, idxs[0] - 20): idxs[-1] + 1]],
                    metrics=metrics,
                )

    metrics.print_summary()

    # --- Untranslated summary ----------------------------------------------
    # Failures are now always "" (never the source text), so a partial output is
    # impossible to mistake for a complete translation: each failed cue is
    # counted, logged with its source text, and (in the CLI) flagged in the SRT.
    untranslated = [i for i, r in enumerate(results) if not r or not r.strip()]
    if untranslated:
        print(
            f"[translate] {len(untranslated)}/{total} cues left UNTRANSLATED "
            f"(indices: {untranslated[:20]}{'...' if len(untranslated) > 20 else ''}).",
            flush=True,
        )
        for i in untranslated[:30]:
            print(f"[translate]   cue {i}: {texts[i]!r}", flush=True)
    else:
        print(f"[translate] All {total} cues translated.", flush=True)

    return results
