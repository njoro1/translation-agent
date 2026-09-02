"""Tests for the context-first translation window engine (Phase 5)."""
from __future__ import annotations

import re

from src.srt_io import Cue
from src.translation_windows import (
    CONTEXT_PROFILES,
    build_cloud_user_content,
    build_hy_mt2_context_user_content,
    build_windows,
    resolve_context_mode,
)
from src.translate import translate_cues


def _cues(n: int, gap_at: set[int] | None = None, gap_s: float = 10.0) -> list[Cue]:
    """n cues of 1s each; a scene gap before indices in ``gap_at``."""
    gap_at = gap_at or set()
    cues = []
    t = 0.0
    for i in range(n):
        if i in gap_at:
            t += gap_s
        cues.append(Cue(t, t + 1.0, f"source{i}"))
        t += 1.0
    return cues


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class ScriptedClient:
    """OpenAI-compatible client that answers numbered lines from a script.

    Each call consumes the next reply; the last one repeats. Records every
    user message so tests can assert on prompt structure.
    """

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.user_messages: list[str] = []
        self.calls = 0

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.calls += 1
        user = [
            m["content"] for m in kwargs.get("messages", [])
            if m.get("role") == "user"
        ]
        self.user_messages.append(user[-1] if user else "")
        reply = (
            self._replies.pop(0) if self._replies else
            (self._replies[-1] if self._replies else "")
        )
        return _Resp(reply)


class EchoNumberedClient(ScriptedClient):
    """Aligns by echoing the CURRENT CUES block back (passthrough)."""

    def __init__(self):
        super().__init__([""])

    def create(self, **kwargs):
        self.calls += 1
        user = [
            m["content"] for m in kwargs.get("messages", [])
            if m.get("role") == "user"
        ]
        self.user_messages.append(user[-1] if user else "")
        items = []
        for line in user[-1].splitlines():
            m = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
            if m:
                items.append(m.group(1).strip())
        return _Resp("\n".join(f"{i}. {t}" for i, t in enumerate(items, 1)))


class TestResolveContextMode:
    def test_backend_defaults(self):
        # Benchmark (cache/compare_context_modes.json, 232-cue Chinese video
        # vs 367-cue English reference): standard context showed zero
        # alignment failures on Hy-MT2 and marginally higher similarity, so
        # both backends default to standard.
        assert resolve_context_mode(None, local=True) == "standard"
        assert resolve_context_mode(None, local=False) == "standard"

    def test_explicit_overrides_backend_default(self):
        assert resolve_context_mode("deep", local=True) == "deep"
        assert resolve_context_mode("off", local=False) == "off"
        assert resolve_context_mode("light", local=False) == "light"

    def test_unknown_falls_back_to_backend_default(self):
        assert resolve_context_mode("bogus", local=False) == "standard"
        assert resolve_context_mode("bogus", local=True) == "standard"


class TestContextProfiles:
    def test_profile_shapes(self):
        assert CONTEXT_PROFILES["off"] == (0, 0, 0)
        assert CONTEXT_PROFILES["light"] == (1, 1, 4)
        assert CONTEXT_PROFILES["standard"] == (2, 2, 8)
        assert CONTEXT_PROFILES["deep"] == (4, 3, 12)


class TestBuildWindows:
    def test_preserves_all_cues_in_order(self):
        cues = _cues(50)
        windows = build_windows(cues, max_window_cues=12)
        flattened = [c for w in windows for c in w.cues]
        assert flattened == cues
        assert windows[0].start_index == 0
        starts = [w.start_index for w in windows]
        assert starts == sorted(starts)

    def test_respects_max_cue_count(self):
        cues = _cues(30)
        windows = build_windows(cues, max_window_cues=12)
        assert all(len(w.cues) <= 12 for w in windows)
        assert len(windows) == 3

    def test_scene_gap_starts_new_window(self):
        cues = _cues(6, gap_at={3})
        windows = build_windows(
            cues, max_window_cues=12, scene_gap_ms=800
        )
        assert [w.start_index for w in windows] == [0, 3]

    def test_char_budget_splits(self):
        cues = [Cue(float(i), float(i) + 1.0, "x" * 60) for i in range(5)]
        windows = build_windows(cues, max_window_cues=12, max_current_chars=100)
        assert all(
            sum(len(c.text) for c in w.cues) <= 160 or len(w.cues) == 1
            for w in windows
        )
        assert len(windows) > 1

    def test_duration_budget_splits(self):
        # Five 20s cues; 30s budget -> max 2 per window.
        cues = [Cue(i * 20.0, i * 20.0 + 20.0, f"s{i}") for i in range(5)]
        windows = build_windows(
            cues, max_window_cues=12, max_window_duration_ms=30000
        )
        assert all(len(w.cues) <= 2 for w in windows)

    def test_invalid_limits_rejected(self):
        try:
            build_windows(_cues(2), max_window_cues=0)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")


class TestPrompts:
    def test_cloud_prompt_contains_context_sections(self):
        texts = ["a", "b"]
        content = build_cloud_user_content(
            texts,
            before_context=[("old", "old translation")],
            after_context=["next"],
            summary="A calm scene.",
        )
        assert "CONTEXT BEFORE" in content
        assert "- old => old translation" in content
        assert "CONTEXT AFTER" in content
        assert "- next" in content
        assert "SCENE SUMMARY" in content
        assert "CURRENT CUES (translate exactly 2 numbered lines):" in content
        assert "1. a" in content and "2. b" in content

    def test_off_prompt_has_no_context_sections(self):
        content = build_cloud_user_content(["a"])
        assert "CONTEXT" not in content
        assert "SCENE SUMMARY" not in content

    def test_parser_ignores_context_and_parses_numbered_lines_only(self):
        from src.translate import _parse_numbered

        noisy_reply = (
            "CONTEXT BEFORE:\n- old => old translation\n\n"
            "Here are the translations:\n"
            "1. First\n2. Second\n\n"
            "I hope this helps!"
        )
        result = _parse_numbered(noisy_reply, 2)
        assert result is not None
        assert result[0] == "First"
        assert result[1].startswith("Second")

    def test_parser_rejects_duplicate_numbers_from_echoed_context(self):
        from src.translate import _parse_numbered

        noisy_reply = (
            "- source => trans\n"
            "1. First\n2. Second\n2. Echoed"
        )
        assert _parse_numbered(noisy_reply, 2) is None

    def test_hy_mt2_prompt_keeps_numbered_block_and_style(self):
        from src.translate import _HY_MT2_STYLE

        content = build_hy_mt2_context_user_content(
            ["a", "b"], source_language="ja",
            before_context=[("old", "old en")], after_context=["nx"],
        )
        assert "1. a" in content and "2. b" in content
        assert _HY_MT2_STYLE in content
        assert "old => old en" in content
        assert "nx" in content


class TestTranslateCuesContextEngine:
    def test_before_context_flows_from_rolling_memory(self):
        client = ScriptedClient([
            "1. first one\n2. second one",
            "1. third one",
        ])
        cues = _cues(3, gap_at={2})
        progress: list[tuple[int, int, str]] = []

        result = translate_cues(
            cues, client, "gpt-4o-mini",
            batch_size=12, source_language="ja",
            context_mode="standard",
            progress_callback=lambda d, t, s: progress.append((d, t, s)),
        )

        assert result == ["first one", "second one", "third one"]
        # Second window's user prompt carries before-context pairs.
        second_prompt = client.user_messages[1]
        assert "CONTEXT BEFORE" in second_prompt
        assert "source0 => first one" in second_prompt
        assert "source1 => second one" in second_prompt
        # Progress reported per window and totals exact.
        assert progress == [(2, 3, "translate"), (3, 3, "translate")]

    def test_after_context_attached_from_next_window(self):
        client = ScriptedClient(["1. alpha\n2. beta"])
        cues = _cues(2, gap_at={1})
        translate_cues(
            cues, client, "gpt-4o-mini",
            batch_size=12, source_language="ja", context_mode="standard",
        )
        prompt = client.user_messages[0]
        assert "CONTEXT AFTER" in prompt
        assert "- source1" in prompt

    def test_off_mode_produces_no_context_sections(self):
        client = ScriptedClient(["1. x"])
        translate_cues(
            _cues(1), client, "gpt-4o-mini",
            batch_size=12, source_language="ja", context_mode="off",
        )
        assert "CONTEXT" not in client.user_messages[0]

    def test_light_mode_single_before_pair(self):
        client = ScriptedClient([
            "1. one",
            "1. two",
        ])
        cues = _cues(2, gap_at={1})
        translate_cues(
            cues, client, "gpt-4o-mini",
            batch_size=12, source_language="ja", context_mode="light",
        )
        second = client.user_messages[1]
        assert "source0 => one" in second
        assert "source-1" not in second  # only ONE pair retained

    def test_split_fallback_preserves_cue_count(self):
        # Window reply misaligned three times, then each half succeeds.
        client = ScriptedClient([
            "garbage", "garbage", "garbage",   # full-window attempts
            "1. first ok",                     # left half
            "1. second ok",                    # right half
        ])
        cues = _cues(2)
        result = translate_cues(
            cues, client, "gpt-4o-mini",
            batch_size=12, source_language="ja", context_mode="off",
        )
        assert len(result) == 2
        assert result == ["first ok", "second ok"]

    def test_single_cue_window_keeps_context(self):
        # A one-cue window (e.g. after a scene gap) must still receive
        # before-context via the numbered protocol.
        client = ScriptedClient([
            "1. one",
            "1. two",
        ])
        cues = _cues(2, gap_at={1})
        translate_cues(
            cues, client, "gpt-4o-mini",
            batch_size=12, source_language="ja", context_mode="light",
        )
        second_prompt = client.user_messages[1]
        assert "CURRENT CUES" in second_prompt
        assert "CONTEXT BEFORE" in second_prompt

    def test_per_item_fallback_still_works(self):
        class PerItemOnlyClient(ScriptedClient):
            """Answers only the minimal per-item prompt; garbage otherwise."""

            def create(self, **kwargs):
                self.calls += 1
                user = [
                    m["content"] for m in kwargs.get("messages", [])
                    if m.get("role") == "user"
                ]
                self.user_messages.append(user[-1] if user else "")
                if user and user[-1].startswith("Translate into English"):
                    return _Resp(f"trans{self.calls}")
                return _Resp("garbage")

        client = PerItemOnlyClient([])
        cues = _cues(2)
        result = translate_cues(
            cues, client, "gpt-4o-mini",
            batch_size=12, source_language="ja", context_mode="off",
        )
        assert len(result) == 2
        assert all(r.startswith("trans") for r in result)
        assert result[0] != result[1]

    def test_echo_never_shipped_or_cached(self, tmp_path):
        from src.translation_memory import TranslationMemory

        client = EchoNumberedClient()
        cues = [Cue(0.0, 1.0, "第一句"), Cue(1.0, 2.0, "第二句")]
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        try:
            result = translate_cues(
                cues, client, "hy-mt2-1.8b",
                batch_size=2, source_language="zh",
                context_mode="light", translation_memory=tm,
            )
        finally:
            tm.close()
        assert result == ["", ""]
        tm2 = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        try:
            assert tm2.get(
                source_language="zh", source_text="第一句",
                model_profile="hy-mt2-local",
                glossary_hash=__import__("hashlib").sha256(b"").hexdigest(),
            ) is None
        finally:
            tm2.close()

    def test_all_tm_hits_skip_llm(self, tmp_path):
        import hashlib

        from src.translation_memory import TranslationMemory

        g_hash = hashlib.sha256(b"").hexdigest()
        db = str(tmp_path / "tm.sqlite3")
        tm = TranslationMemory(db)
        tm.put(
            source_language="zh", source_text="你好",
            translated_text="Hello", model_profile="cloud:test-model",
            glossary_hash=g_hash,
        )
        client = ScriptedClient([])
        cues = [Cue(0.0, 1.0, "你好")]
        try:
            result = translate_cues(
                cues, client, "test-model",
                batch_size=4, source_language="zh",
                context_mode="off", translation_memory=tm,
            )
        finally:
            tm.close()
        assert result == ["Hello"]
        assert client.calls == 0  # LLM never called

    def test_partial_tm_hits_send_whole_window_to_llm(self, tmp_path):
        import hashlib

        from src.translation_memory import TranslationMemory

        g_hash = hashlib.sha256(b"").hexdigest()
        db = str(tmp_path / "tm.sqlite3")
        tm = TranslationMemory(db)
        tm.put(
            source_language="zh", source_text="第一句",
            translated_text="stale cached version",
            model_profile="cloud:test-model", glossary_hash=g_hash,
        )
        client = ScriptedClient(["1. fresh one\n2. fresh two"])
        cues = [Cue(0.0, 1.0, "第一句"), Cue(1.0, 2.0, "第二句")]
        try:
            result = translate_cues(
                cues, client, "test-model",
                batch_size=4, source_language="zh",
                context_mode="off", translation_memory=tm,
            )
            # Whole window went to the LLM; TM entry overwritten with fresh.
            assert result == ["fresh one", "fresh two"]
            assert tm.get(
                source_language="zh", source_text="第一句",
                model_profile="cloud:test-model", glossary_hash=g_hash,
            ) == "fresh one"
        finally:
            tm.close()

    def test_empty_input_returns_empty(self):
        assert translate_cues([], ScriptedClient([]), "m") == []


class TestLocalHyMt2Context:
    """The fully local (Hy-MT2) pipeline must translate with context by default.

    Default = standard (2 before pairs / 2 after cues / 8 memory pairs) for
    both backends, benchmark-verified on a 232-cue Chinese video: zero
    alignment failures with standard vs light. Windows cap at 8 cues; the
    numbered protocol stays exact.
    """

    def _cues(self, n: int, gap_at: set[int] | None = None) -> list[Cue]:
        return _cues(n, gap_at=gap_at)

    def test_auto_preset_defers_context_to_backend(self):
        # GUI offline runs pass --content-preset auto with no --context-mode.
        import translate as cli

        from src.presets import resolve_effective_settings

        args = cli._parse_args(["--file", "x.mp4", "--local"])
        resolve_effective_settings(args)
        assert args.context_mode is None  # backend decides
        assert resolve_context_mode(args.context_mode, local=True) == "standard"
        assert resolve_context_mode(args.context_mode, local=False) == "standard"

    def test_named_preset_still_pins_context_for_local(self):
        import translate as cli

        from src.presets import resolve_effective_settings

        args = cli._parse_args(["--file", "x.mp4", "--local",
                                "--content-preset", "documentary"])
        resolve_effective_settings(args)
        assert args.context_mode == "deep"  # explicit preset choice wins

    def test_hy_mt2_prompt_carries_before_and_after_context(self):
        client = ScriptedClient([
            "1. First line\n2. Second line",
            "1. Third line",
        ])
        cues = self._cues(3, gap_at={2})
        translate_cues(
            cues, client, "Hy-MT2-1.8B-Q8_0",
            batch_size=8, source_language="ja",
            # context_mode=None -> backend default (light) for Hy-MT2
        )
        second = client.user_messages[1]
        assert "【上文参考（已翻译，仅供理解，不要输出）】" in second
        # standard mode keeps TWO before pairs.
        assert "source1 => Second line" in second
        assert "source0 => First line" in second
        assert "【下文参考（原文，仅供理解，不要输出）】" not in second  # last window
        # Numbered protocol intact and style directive present.
        assert "【待翻译文本" in second
        assert "1. source2" in second

    def test_hy_mt2_first_window_has_no_empty_context_section(self):
        client = ScriptedClient(["1. first"])
        translate_cues(
            self._cues(1), client, "Hy-MT2-1.8B-Q8_0",
            batch_size=8, source_language="ja",
        )
        prompt = client.user_messages[0]
        assert "【上文参考" not in prompt
        assert "【下文参考" not in prompt
        assert "1. source0" in prompt

    def test_hy_mt2_windows_capped_at_eight_cues(self):
        from src.translation_windows import build_windows

        cues = self._cues(30)
        windows = build_windows(cues, max_window_cues=8)
        assert all(len(w.cues) <= 8 for w in windows)
        flattened = [c for w in windows for c in w.cues]
        assert flattened == cues

    def test_hy_mt2_context_survives_split_fallback(self):
        # Window 2 (after a scene gap, so rolling memory exists) fails
        # alignment 3x and splits into halves — the split halves must still
        # carry the read-only before-context.
        client = ScriptedClient([
            "1. one\n2. two",                 # window 1 fine
            "garbage", "garbage", "garbage",  # window 2 attempts
            "1. three ok",                    # left half
            "1. four ok",                     # right half
        ])
        cues = self._cues(4, gap_at={2})
        result = translate_cues(
            cues, client, "Hy-MT2-1.8B-Q8_0",
            batch_size=8, source_language="ja",
        )
        assert result == ["one", "two", "three ok", "four ok"]
        # At least one split-half prompt carried the context header, with the
        # most recent pair (light = 1 before pair).
        split_prompts = client.user_messages[4:]  # after the 3 failed attempts
        assert any("【上文参考" in m for m in split_prompts)
        assert any("source1 => two" in m for m in split_prompts)

    def test_hy_mt2_scene_summary_ignored_with_warning(self, capsys):
        client = ScriptedClient(["1. ok"])
        translate_cues(
            self._cues(1), client, "Hy-MT2-1.8B-Q8_0",
            batch_size=8, source_language="ja",
            scene_summary_enabled=True,
        )
        assert "cloud-only" in capsys.readouterr().out


class TestPromptAddenda:
    def test_addendum_appended_to_system_prompt_not_replacing_directive(self):
        from src.presets import get_prompt_addendum
        from src.translate import _FOREIGNIZATION_DIRECTIVE, build_system_prompt

        addendum = get_prompt_addendum("anime")
        assert addendum is not None
        prompt = build_system_prompt("ja", addendum=addendum)
        assert _FOREIGNIZATION_DIRECTIVE.split("\n")[0] in prompt
        assert "honorifics" in prompt

    def test_general_profile_has_no_addendum(self):
        from src.presets import get_prompt_addendum

        assert get_prompt_addendum("general") is None
        assert get_prompt_addendum(None) is None

    def test_all_preset_profiles_resolve(self):
        from src.presets import PRESETS, get_prompt_addendum

        for preset in PRESETS.values():
            if preset.prompt_profile == "general":
                continue
            assert get_prompt_addendum(preset.prompt_profile), preset.name
