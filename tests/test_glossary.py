"""Tests for src/glossary.py — loading, formatting, hashing."""
from __future__ import annotations

from src.glossary import format_glossary, glossary_hash, load_glossary


class TestLoadGlossary:
    def test_none_path(self):
        assert load_glossary(None) == []

    def test_empty_path(self):
        assert load_glossary("") == []

    def test_missing_file(self, tmp_path):
        assert load_glossary(str(tmp_path / "nonexistent.txt")) == []

    def test_blank_file(self, tmp_path):
        path = tmp_path / "blank.txt"
        path.write_text("\n\n\n", encoding="utf-8")
        assert load_glossary(str(path)) == []

    def test_comments_ignored(self, tmp_path):
        path = tmp_path / "comments.txt"
        path.write_text("# comment\n\n# another\n", encoding="utf-8")
        assert load_glossary(str(path)) == []

    def test_tab_delimiter(self, tmp_path):
        path = tmp_path / "tab.txt"
        path.write_text("先輩\tsenpai\n", encoding="utf-8")
        assert load_glossary(str(path)) == [("先輩", "senpai")]

    def test_equals_delimiter(self, tmp_path):
        path = tmp_path / "equals.txt"
        path.write_text("先生 = sensei\n", encoding="utf-8")
        assert load_glossary(str(path)) == [("先生", "sensei")]

    def test_arrow_delimiter(self, tmp_path):
        path = tmp_path / "arrow.txt"
        path.write_text("騎士団 -> Knight Order\n", encoding="utf-8")
        assert load_glossary(str(path)) == [("騎士団", "Knight Order")]

    def test_duplicate_source(self, tmp_path):
        path = tmp_path / "dup.txt"
        path.write_text("先輩 = senpai\n先輩 = sempai\n", encoding="utf-8")
        entries = load_glossary(str(path))
        assert len(entries) == 1
        assert entries[0] == ("先輩", "senpai")

    def test_multiple_entries(self, tmp_path):
        path = tmp_path / "multi.txt"
        path.write_text(
            "# Glossary\n"
            "先輩 = senpai\n"
            "先生 = sensei\n"
            "魔法少女\tmagical girl\n",
            encoding="utf-8",
        )
        entries = load_glossary(str(path))
        assert len(entries) == 3

    def test_empty_source_or_target_rejected(self, tmp_path):
        path = tmp_path / "bad.txt"
        path.write_text("= target\nsource =\n\n", encoding="utf-8")
        assert load_glossary(str(path)) == []


class TestFormatGlossary:
    def test_empty(self):
        assert format_glossary([]) == ""

    def test_non_empty(self):
        entries = [("先輩", "senpai"), ("先生", "sensei")]
        result = format_glossary(entries)
        assert "Use the following glossary consistently:" in result
        assert "先輩 -> senpai" in result
        assert "先生 -> sensei" in result


class TestGlossaryHash:
    def test_deterministic(self):
        entries = [("a", "b")]
        assert glossary_hash(entries) == glossary_hash(entries)

    def test_different_entries_different_hash(self):
        assert glossary_hash([("a", "b")]) != glossary_hash([("a", "c")])

    def test_empty_hash(self):
        assert len(glossary_hash([])) == 64
