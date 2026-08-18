"""Tests for src/translate.py — numbered-block parsing and Hy-MT2 detection."""
from __future__ import annotations

from src.translate import (
    _endpoint_fatal_message,
    _raise_if_fatal,
    _is_hy_mt2,
    _numbered_block,
    _parse_numbered,
    _PerfMetrics,
    TranslationEndpointError,
)


class _FakeStatusError(Exception):
    """Mimics the openai SDK status errors we classify on."""

    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class TestNumberedBlock:
    def test_single_item(self):
        assert _numbered_block(["hello"]) == "1. hello"

    def test_multiple_items(self):
        result = _numbered_block(["a", "b", "c"])
        assert result == "1. a\n2. b\n3. c"

    def test_empty(self):
        assert _numbered_block([]) == ""


class TestParseNumbered:
    def test_valid_output(self):
        response = "1. Hello\n2. World\n3. Test"
        result = _parse_numbered(response, 3)
        assert result == ["Hello", "World", "Test"]

    def test_missing_number(self):
        response = "1. Hello\n3. Test"
        result = _parse_numbered(response, 3)
        assert result is None

    def test_duplicate_number(self):
        response = "1. Hello\n1. World\n2. Test"
        result = _parse_numbered(response, 2)
        assert result is None

    def test_extra_number(self):
        response = "1. Hello\n2. World\n3. Extra"
        result = _parse_numbered(response, 2)
        assert result is None

    def test_wrong_count(self):
        response = "1. Hello\n2. World"
        result = _parse_numbered(response, 3)
        assert result is None

    def test_empty_response(self):
        result = _parse_numbered("", 3)
        assert result is None

    def test_multiline_item(self):
        response = "1. Hello\n   continuation\n2. World"
        result = _parse_numbered(response, 2)
        assert result is not None
        assert "Hello" in result[0]
        assert "continuation" in result[0]
        assert result[1] == "World"


class TestIsHyMt2:
    def test_hy_mt2_lowercase(self):
        assert _is_hy_mt2("hy-mt2") is True

    def test_hy_mt2_underscore(self):
        assert _is_hy_mt2("hy_mt2") is True

    def test_hy_mt2_mixed_case(self):
        assert _is_hy_mt2("Hy-MT2") is True

    def test_hy_mt2_uppercase(self):
        assert _is_hy_mt2("HY_MT2") is True

    def test_hy_mt2_with_suffix(self):
        assert _is_hy_mt2("Hy-MT2-1.8B-1.25bit-v2.gguf") is True

    def test_non_hy_mt2(self):
        assert _is_hy_mt2("gpt-4o") is False

    def test_empty_string(self):
        assert _is_hy_mt2("") is False

    def test_none(self):
        assert _is_hy_mt2(None) is False


class TestEndpointFatalError:
    """A non-OpenAI endpoint (e.g. a web app answering 404/405) must abort
    translation instantly instead of retrying forever."""

    def test_405_is_fatal(self):
        assert _endpoint_fatal_message(_FakeStatusError(405)) is not None

    def test_404_is_fatal(self):
        assert _endpoint_fatal_message(_FakeStatusError(404)) is not None

    def test_501_is_fatal(self):
        assert _endpoint_fatal_message(_FakeStatusError(501)) is not None

    def test_500_is_transient(self):
        # Transient server errors should still go through the retry ladder.
        assert _endpoint_fatal_message(_FakeStatusError(500)) is None

    def test_timeout_is_transient(self):
        assert _endpoint_fatal_message(_FakeStatusError(408)) is None

    def test_no_status_code_is_transient(self):
        assert _endpoint_fatal_message(RuntimeError("boom")) is None

    def test_raise_if_fatal_propagates(self):
        try:
            _raise_if_fatal(_FakeStatusError(405))
        except TranslationEndpointError as exc:
            assert "127.0.0.1:8080/v1" in str(exc)
        else:
            assert False, "expected TranslationEndpointError"

    def test_raise_if_fatal_allows_transient(self):
        # Should NOT raise for transient errors.
        _raise_if_fatal(_FakeStatusError(500))
        _raise_if_fatal(RuntimeError("connection refused"))


class _FakeUsage:
    def __init__(self, prompt_tokens, completion_tokens):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _TimedResp:
    """Mimics an openai completion response with usage + llama.cpp timings."""

    def __init__(self, prompt, completion, gen_per_s, prompt_per_s, gen_ms):
        self.usage = _FakeUsage(prompt, completion)
        self.model_extra = {
            "timings": {
                "prompt_per_second": prompt_per_s,
                "predicted_per_second": gen_per_s,
                "predicted_ms": gen_ms,
            }
        }


class TestPerfMetrics:
    def test_accumulates_usage_and_summary(self):
        m = _PerfMetrics()
        m.print_call(_TimedResp(prompt=100, completion=20, gen_per_s=10.0, prompt_per_s=50.0, gen_ms=2000.0), "batch (12 cues)")  # noqa: E501
        m.print_call(_TimedResp(prompt=50, completion=10, gen_per_s=8.0, prompt_per_s=40.0, gen_ms=1250.0), "single item")  # noqa: E501
        assert m.requests == 2
        assert m.prompt_tokens == 150
        assert m.completion_tokens == 30
        # overall tok/s = total / gen_seconds = 180 / 3.25
        assert abs(m.gen_seconds - 3.25) < 1e-9
        m.print_summary()  # must not raise
        assert m.prompt_tokens == 150

    def test_ignores_responses_without_usage(self):
        m = _PerfMetrics()
        m.print_call(object(), "no usage")  # no usage/timings
        assert m.requests == 0

    def test_reset(self):
        m = _PerfMetrics()
        m.print_call(_TimedResp(prompt=10, completion=5, gen_per_s=1.0, prompt_per_s=2.0, gen_ms=5000.0), "x")  # noqa: E501
        m.reset()
        assert m.requests == 0 and m.prompt_tokens == 0 and m.completion_tokens == 0

