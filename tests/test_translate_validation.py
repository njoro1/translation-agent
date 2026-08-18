"""Tests for src/translate.py output validation and no-source-passthrough.

Covers `looks_untranslated`, `_translate_one` (never returns the source), and
`_per_item_translate` (failed cues come back as "" — never as the source text).
These behaviors are what prevent a local/offline run from shipping untranslated
Chinese as if it were a successful translation (see SUBTITLE_QUALITY_REPORT).
"""
from __future__ import annotations

import hashlib
import re

from src.srt_io import Cue
from src.translate import (
    _per_item_translate,
    _translate_one,
    looks_untranslated,
    translate_cues,
)

_EMPTY_GLOSSARY_HASH = hashlib.sha256(b"").hexdigest()


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _FakeResp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _FakeClient:
    """Minimal OpenAI-compatible client whose replies come from a sequence.

    Repeats the last reply for any further call. Tracks the number of calls.
    """

    def __init__(self, contents: list[str]):
        self._contents = list(contents)
        self.calls = 0

    @property
    def chat(self) -> "_FakeClient":
        return self

    @property
    def completions(self) -> "_FakeClient":
        return self

    def create(self, **kwargs) -> _FakeResp:
        content = self._contents[min(self.calls, len(self._contents) - 1)]
        self.calls += 1
        return _FakeResp(content)


class _EchoNumberedClient(_FakeClient):
    """Always aligns the numbered protocol by echoing the source lines back.

    Alignment succeeds, but every 'translation' is just the source text — the
    exact failure the new validation layer must catch before writing or caching.
    """

    def __init__(self):
        super().__init__([""])

    def create(self, **kwargs) -> _FakeResp:
        self.calls += 1
        user = [
            m for m in kwargs.get("messages", []) if (m or {}).get("role") == "user"
        ]
        content = user[-1]["content"] if user else ""
        items = []
        for line in content.splitlines():
            m = re.match(r"^\s*\d+[.)]?\s+(.+)$", line)
            if m:
                items.append(m.group(1).strip())
        if not items:
            return _FakeResp("")
        return _FakeResp(
            "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))
        )


class TestLooksUntranslated:
    def test_empty_or_whitespace_flagged(self):
        assert looks_untranslated("你好", "", "zh") is True
        assert looks_untranslated("你好", "   ", "zh") is True

    def test_exact_passthrough_flagged(self):
        assert looks_untranslated("你好世界", "你好世界", "zh") is True

    def test_passthrough_with_extra_whitespace_flagged(self):
        assert looks_untranslated("你好 世界", "你好世界", "zh") is True

    def test_case_folded_passthrough_flagged(self):
        assert looks_untranslated("Hello", "hello", "en") is True

    def test_clean_english_ok(self):
        assert looks_untranslated(
            "你好世界", "Hello world, this is a fine sentence.", "zh"
        ) is False

    def test_all_chinese_echo_flagged(self):
        assert looks_untranslated("你一定也化过妆", "我一定也化过妆", "zh") is True
        assert looks_untranslated("你一定也化过妆", "你一定也化过妆吧", "zh") is True

    def test_hangul_flagged(self):
        # Hangul never belongs in an English subtitle line.
        assert looks_untranslated("それを", "그제 다시 배우的 그어데.", "ja") is True

    def test_short_line_with_cjk_flagged(self):
        # "Super加倍" — a Chinese word embedded in English corruption.
        assert looks_untranslated("加倍", "Super加倍", "zh") is True

    def test_long_line_small_cjk_ratio_tolerated(self):
        long = "Super加倍 highlighter-lined lashes are very popular today."
        assert looks_untranslated("超级加倍的高光睫毛很流行", long, "zh") is False

    def test_non_cjk_source_only_generic_rules(self):
        assert looks_untranslated("hola", "hola mundo", "es") is False
        assert looks_untranslated("hola", "hola", "es") is True  # exact echo still bad

    def test_unknown_source_language(self):
        assert looks_untranslated("你好", "", None) is True
        assert looks_untranslated("你好", "你好", None) is True
        assert looks_untranslated("你好", "Hello there", None) is False
class TestTranslateOneNoSourcePassthrough:
    def test_empty_reply_returns_empty(self):
        client = _FakeClient([""])
        assert _translate_one(client, "hy-mt2", "你好", None) == ""

    def test_none_content_returns_empty(self):
        class _NullClient(_FakeClient):
            def create(self, **kwargs):
                return _FakeResp(None)

        assert _translate_one(_NullClient([""]), "hy-mt2", "text", None) == ""

    def test_valid_reply_returned(self):
        client = _FakeClient(["Good morning"])
        assert _translate_one(client, "hy-mt2", "おはよう", None) == "Good morning"


class TestPerItemNoSourcePassthrough:
    def test_failures_are_empty_not_source(self):
        client = _FakeClient([""])
        out = _per_item_translate(
            client, "hy-mt2-1.8b", ["第一句", "第二句"], None,
            source_language="zh", hy_mt2=True,
        )
        assert out == ["", ""]

    def test_source_echo_rejected_then_retried(self):
        client = _FakeClient(["你一定也化过妆", "You must have worn makeup before."])
        out = _per_item_translate(
            client, "hy-mt2-1.8b", ["你一定也化过妆"], None,
            source_language="zh", hy_mt2=True,
        )
        assert out == ["You must have worn makeup before."]
        assert client.calls == 2

    def test_persistent_source_echo_returns_empty(self):
        client = _FakeClient(["你一定也化过妆"])
        out = _per_item_translate(
            client, "hy-mt2-1.8b", ["你一定也化过妆"], None,
            source_language="zh", hy_mt2=True,
        )
        assert out == [""]
        assert client.calls >= 2  # primary + degraded retry both attempted

    def test_transient_exception_returns_empty(self):
        class _Boom(_FakeClient):
            def create(self, **kwargs):
                raise RuntimeError("connection refused")

        client = _Boom(["irrelevant"])
        out = _per_item_translate(
            client, "hy-mt2-1.8b", ["text"], None,
            source_language="zh", hy_mt2=True,
        )
        assert out == [""]

    def test_clean_non_hy_mt2_path(self):
        client = _FakeClient(["Good morning"])
        out = _per_item_translate(
            client, "gpt-4o-mini", ["おはよう"], None,
            source_language="ja", hy_mt2=False,
        )
        assert out == ["Good morning"]


class TestTranslateCuesValidation:
    def test_batch_source_echo_never_returned_or_cached(self, tmp_path):
        from src.translation_memory import TranslationMemory

        client = _EchoNumberedClient()
        cues = [Cue(0.0, 1.0, "第一句"), Cue(1.0, 2.0, "第二句")]
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        try:
            result = translate_cues(
                cues, client, "hy-mt2-1.8b",
                batch_size=2, source_language="zh",
                translation_memory=tm,
            )
        finally:
            tm.close()

        # Both lines were numbered echoes of the source -> never shipped/cached.
        assert result == ["", ""]
        tm2 = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        try:
            assert tm2.get(
                source_language="zh", source_text="第一句",
                model_profile="hy-mt2-local", glossary_hash=_EMPTY_GLOSSARY_HASH,
            ) is None
            assert tm2.get(
                source_language="zh", source_text="第二句",
                model_profile="hy-mt2-local", glossary_hash=_EMPTY_GLOSSARY_HASH,
            ) is None
        finally:
            tm2.close()

    def test_valid_batch_results_survive(self):
        client = _FakeClient(["1. First sentence\n2. Second sentence"])
        cues = [Cue(0.0, 1.0, "第一句"), Cue(1.0, 2.0, "第二句")]
        result = translate_cues(
            cues, client, "gpt-4o-mini",
            batch_size=2, source_language="zh",
        )
        assert result == ["First sentence", "Second sentence"]