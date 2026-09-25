"""Tests for GGUF integrity checking.

The bug these cover: an interrupted download left a *truncated* GGUF on disk.
Because every check only asked "does the file exist?", the app reported the
model as ready, and the fully offline run then failed minutes later with
"FunASR produced no transcription" — which the UI mislabelled as "no subtitles
could be fetched for this source".
"""
from __future__ import annotations

import os

import pytest

from src.gguf_check import inspect_gguf, is_usable_gguf
from tests.gguf_fixtures import build_gguf, write_gguf


def _write(tmp_path, name: str, data: bytes) -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


class TestInspectGguf:
    def test_accepts_a_complete_file(self, tmp_path):
        path = write_gguf(tmp_path, "ok.gguf")
        assert inspect_gguf(path) == (True, "")

    def test_rejects_a_truncated_file(self, tmp_path):
        path = write_gguf(tmp_path, "cut.gguf", truncate_bytes=100,
                          tensors=2, elements=64)
        ok, reason = inspect_gguf(path)
        assert not ok
        assert "incomplete" in reason
        assert "100 byte" in reason

    def test_rejects_a_file_cut_inside_the_header(self, tmp_path):
        # Long enough to pass the "too small to be a GGUF" guard, but the
        # metadata section is cut off mid-string.
        path = _write(tmp_path, "header.gguf", build_gguf()[:40])
        ok, reason = inspect_gguf(path)
        assert not ok
        assert "not a valid GGUF" in reason

    def test_rejects_a_file_too_small_to_be_a_model(self, tmp_path):
        path = _write(tmp_path, "tiny.gguf", b"GGUF")
        assert inspect_gguf(path) == (False, "file is too small to be a GGUF model")

    def test_rejects_a_foreign_file(self, tmp_path):
        path = _write(tmp_path, "notes.gguf", b"# just a text file\n" * 4)
        ok, reason = inspect_gguf(path)
        assert not ok
        assert "bad magic" in reason

    def test_rejects_an_empty_file(self, tmp_path):
        path = _write(tmp_path, "empty.gguf", b"")
        assert inspect_gguf(path) == (False, "file is empty")

    def test_reports_a_missing_file(self, tmp_path):
        assert inspect_gguf(str(tmp_path / "nope.gguf")) == (False, "file not found")

    def test_reports_a_directory(self, tmp_path):
        assert inspect_gguf(str(tmp_path)) == (False, "file not found")

    def test_reports_no_path(self):
        assert inspect_gguf("") == (False, "no path given")
        assert inspect_gguf(None) == (False, "no path given")

    def test_is_usable_gguf_matches_inspect(self, tmp_path):
        good = write_gguf(tmp_path, "good.gguf")
        bad = write_gguf(tmp_path, "bad.gguf", truncate_bytes=4)
        assert is_usable_gguf(good) is True
        assert is_usable_gguf(bad) is False

    def test_result_is_cached_until_the_file_changes(self, tmp_path):
        path = write_gguf(tmp_path, "cache.gguf")
        assert is_usable_gguf(path) is True
        # Rewriting the file changes size+mtime, so the cached verdict is dropped.
        with open(path, "r+b") as handle:
            handle.truncate(16)
        assert is_usable_gguf(path) is False

    def test_reads_a_real_model_when_present(self):
        """The shipped ASR models must pass — they are what the app loads."""
        for name in ("sensevoice-small-q8.gguf", "fsmn-vad.gguf"):
            path = os.path.join("gguf", name)
            if not os.path.isfile(path):
                pytest.skip(f"{path} not downloaded in this checkout")
            assert is_usable_gguf(path), f"{path} failed validation"
