"""Tests for src.fetch_subs.py — English-first transcript selection."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.fetch_subs import (
    _resolve_english_transcript,
    _resolve_transcript,
    _snippets_to_cues,
)
from src.srt_io import Cue


class _FakeTranscript:
    """Mimics a youtube_transcript_api.Transcript object."""

    def __init__(self, language_code: str, manual: bool, snippets):
        self.language_code = language_code
        self.is_manual = manual
        self._snippets = snippets

    def fetch(self):
        return list(self._snippets)


class _FakeTranscriptList:
    """Mimics youtube_transcript_api.TranscriptList (limited API surface)."""

    def __init__(self, transcripts):
        self._by_code = {t.language_code: t for t in transcripts}
        self._order = transcripts

    def find_manually_created_transcript(self, codes):
        for t in self._order:
            if t.is_manual and t.language_code in codes:
                return t
        raise _import_notfound()

    def find_generated_transcript(self, codes):
        for t in self._order:
            if not t.is_manual and t.language_code in codes:
                return t
        raise _import_notfound()

    def __iter__(self):
        return iter(self._order)


def _import_notfound():
    # Lazy import so the fake raises the same exception type the real code does.
    from youtube_transcript_api import NoTranscriptFound
    return NoTranscriptFound("", ["en"], None)


def _snippet(text, start, duration=2.0):
    return SimpleNamespace(text=text, start=start, duration=duration)


def test_resolve_english_prefers_manual_over_generated():
    manual_en = _FakeTranscript("en", True, [_snippet("hello", 0)])
    gen_en = _FakeTranscript("en", False, [_snippet("hi", 0)])
    tl = _FakeTranscriptList([gen_en, manual_en])
    assert _resolve_english_transcript(tl) is manual_en


def test_resolve_english_falls_back_to_generated():
    gen_en = _FakeTranscript("en", False, [_snippet("hi", 0)])
    tl = _FakeTranscriptList([gen_en])
    assert _resolve_english_transcript(tl) is gen_en


def test_resolve_english_handles_region_code():
    gen_en_us = _FakeTranscript("en-US", False, [_snippet("hi", 0)])
    tl = _FakeTranscriptList([gen_en_us])
    assert _resolve_english_transcript(tl) is gen_en_us


def test_resolve_english_returns_none_when_absent():
    zh = _FakeTranscript("zh", True, [_snippet("ni", 0)])
    tl = _FakeTranscriptList([zh])
    assert _resolve_english_transcript(tl) is None


def test_resolve_transcript_prefers_requested_language():
    zh_manual = _FakeTranscript("zh-Hans", True, [_snippet("a", 0)])
    zh_gen = _FakeTranscript("zh-Hans", False, [_snippet("b", 0)])
    en = _FakeTranscript("en", False, [_snippet("c", 0)])
    tl = _FakeTranscriptList([zh_gen, zh_manual, en])
    assert _resolve_transcript(tl, "zh-Hans") is zh_manual


def test_snippets_to_cues_builds_timing_and_text():
    snippets = [
        _snippet("Line one", 1.0, 2.5),
        _snippet("  Line two  ", 4.0, 3.0),  # whitespace is stripped
    ]
    cues = _snippets_to_cues(snippets)
    assert len(cues) == 2
    assert cues[0].text == "Line one"
    assert cues[0].start == 1.0
    assert cues[0].end == 3.5
    assert cues[1].text == "Line two"
    assert cues[1].start == 4.0
    assert cues[1].end == 7.0


def test_snippets_to_cues_skips_empty():
    snippets = [_snippet("", 0), _snippet("real", 1)]
    cues = _snippets_to_cues(snippets)
    assert len(cues) == 1
    assert cues[0].text == "real"
