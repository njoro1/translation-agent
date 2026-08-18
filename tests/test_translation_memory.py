"""Tests for src/translation_memory.py — SQLite-backed cache."""
from __future__ import annotations

from src.translation_memory import TranslationMemory, make_key


class TestMakeKey:
    def test_deterministic(self):
        k1 = make_key(
            source_language="ja", source_text="こんにちは",
            model_profile="hy-mt2-local", glossary_hash="abc",
        )
        k2 = make_key(
            source_language="ja", source_text="こんにちは",
            model_profile="hy-mt2-local", glossary_hash="abc",
        )
        assert k1 == k2

    def test_different_language_different_key(self):
        k1 = make_key(
            source_language="ja", source_text="text",
            model_profile="p", glossary_hash="g",
        )
        k2 = make_key(
            source_language="zh", source_text="text",
            model_profile="p", glossary_hash="g",
        )
        assert k1 != k2


class TestTranslationMemory:
    def test_enabled_property(self, tmp_path):
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        assert tm.enabled is True
        tm.close()

    def test_put_get_exact_match(self, tmp_path):
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        tm.put(
            source_language="ja", source_text="おはよう",
            translated_text="Good morning",
            model_profile="hy-mt2-local", glossary_hash="g1",
        )
        result = tm.get(
            source_language="ja", source_text="おはよう",
            model_profile="hy-mt2-local", glossary_hash="g1",
        )
        assert result == "Good morning"
        tm.close()

    def test_different_language_does_not_match(self, tmp_path):
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        tm.put(
            source_language="ja", source_text="おはよう",
            translated_text="Good morning",
            model_profile="p", glossary_hash="g",
        )
        assert tm.get(
            source_language="zh", source_text="おはよう",
            model_profile="p", glossary_hash="g",
        ) is None
        tm.close()

    def test_different_glossary_hash_does_not_match(self, tmp_path):
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        tm.put(
            source_language="ja", source_text="text",
            translated_text="t1", model_profile="p", glossary_hash="g1",
        )
        assert tm.get(
            source_language="ja", source_text="text",
            model_profile="p", glossary_hash="g2",
        ) is None
        tm.close()

    def test_different_model_profile_does_not_match(self, tmp_path):
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        tm.put(
            source_language="ja", source_text="text",
            translated_text="t1", model_profile="hy-mt2-local",
            glossary_hash="g",
        )
        assert tm.get(
            source_language="ja", source_text="text",
            model_profile="cloud:gpt-4o", glossary_hash="g",
        ) is None
        tm.close()

    def test_empty_translation_not_stored(self, tmp_path):
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        tm.put(
            source_language="ja", source_text="text",
            translated_text="   ", model_profile="p", glossary_hash="g",
        )
        assert tm.get(
            source_language="ja", source_text="text",
            model_profile="p", glossary_hash="g",
        ) is None
        tm.close()

    def test_whitespace_normalized_source(self, tmp_path):
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        tm.put(
            source_language="ja", source_text="hello   world",
            translated_text="t1", model_profile="p", glossary_hash="g",
        )
        assert tm.get(
            source_language="ja", source_text="hello world",
            model_profile="p", glossary_hash="g",
        ) == "t1"
        tm.close()

    def test_corrupt_db_fails_gracefully(self, tmp_path):
        """Pointing at an invalid DB path disables the memory without crashing."""
        blocker = tmp_path / "blocker_file"
        blocker.write_text("x", encoding="utf-8")
        tm = TranslationMemory(str(blocker / "tm.sqlite3"))
        tm.put(
            source_language="ja", source_text="text",
            translated_text="t1", model_profile="p", glossary_hash="g",
        )
        result = tm.get(
            source_language="ja", source_text="text",
            model_profile="p", glossary_hash="g",
        )
        # Graceful either way — never raises.
        assert result in (None, "t1")
        tm.close()

    def test_corrupt_db_content_disables_on_use(self, tmp_path):
        junk = tmp_path / "junk.sqlite"
        junk.write_text("not a database", encoding="utf-8")
        tm = TranslationMemory(str(junk))
        # get/put must not raise even if schema creation fails.
        assert tm.get(
            source_language="ja", source_text="text",
            model_profile="p", glossary_hash="g",
        ) in (None, "t1")
        tm.close()
        
class TestNoSourcePassthroughCaching:
    """A failed cue must never be cached as a 'translation' (the propagation bug
    identified in SUBTITLE_QUALITY_REPORT §3.2)."""

    def test_identical_translation_not_stored(self, tmp_path):
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        tm.put(
            source_language="zh", source_text="你好",
            translated_text="你好", model_profile="p", glossary_hash="g",
        )
        assert tm.get(
            source_language="zh", source_text="你好",
            model_profile="p", glossary_hash="g",
        ) is None
        tm.close()

    def test_whitespace_normalized_passthrough_not_stored(self, tmp_path):
        tm = TranslationMemory(str(tmp_path / "tm.sqlite3"))
        # "hello   world" vs "hello world" — a whitespace-only difference is a
        # passthrough after normalization, so it must not be cached.
        tm.put(
            source_language="en", source_text="hello   world",
            translated_text="hello world", model_profile="p", glossary_hash="g",
        )
        assert tm.get(
            source_language="en", source_text="hello world",
            model_profile="p", glossary_hash="g",
        ) is None
        tm.close()

    def test_purges_markup_poisoned_rows_on_init(self, tmp_path):
        # Entries whose cached translation carries leaked chengyu markup or raw
        # ASR control tags must be purged so they are never replayed (50元 regression).
        db = str(tmp_path / "tm.sqlite3")
        tm = TranslationMemory(db)

        def insert(src, trn):
            key = make_key(
                source_language="zh", source_text=src,
                model_profile="hy-mt2-local", glossary_hash="g",
            )
            tm._db.execute(
                "INSERT OR REPLACE INTO translation_memory "
                "(key, source_language, source_text, translated_text, model_profile, "
                " glossary_hash, created_at, last_used_at, hits) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 1)",
                (key, "zh", src, trn, "hy-mt2-local", "g"),
            )
        tm._db.commit()

        insert("谁在小时候呢", "[CHENGYU:Who was there when I was a child][CHENGYU:Didn't]")
        insert("<|zh|><|ANGRY|>你一定也化过妆", "<|zh|><|ANGRY|>You must have makeup")
        insert("干净的翻译", "A clean translation")
        tm._db.commit()
        tm.close()

        # Reopening purges the chengyu- and tag-poisoned rows but keeps the clean one.
        tm2 = TranslationMemory(db)
        try:
            assert tm2.get(
                source_language="zh", source_text="谁在小时候呢",
                model_profile="hy-mt2-local", glossary_hash="g",
            ) is None
            assert tm2.get(
                source_language="zh", source_text="<|zh|><|ANGRY|>你一定也化过妆",
                model_profile="hy-mt2-local", glossary_hash="g",
            ) is None
            assert tm2.get(
                source_language="zh", source_text="干净的翻译",
                model_profile="hy-mt2-local", glossary_hash="g",
            ) == "A clean translation"
        finally:
            tm2.close()
        # Simulate an old DB that already contains source == translation entries
        # (created by the pre-fix fallback-to-source code).
        db = str(tmp_path / "tm.sqlite3")
        tm = TranslationMemory(db)
        key = make_key(
            source_language="zh", source_text="你好",
            model_profile="hy-mt2-local", glossary_hash="g",
        )
        tm._db.execute(
            "INSERT INTO translation_memory "
            "(key, source_language, source_text, translated_text, model_profile, "
            " glossary_hash, created_at, last_used_at, hits) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 1)",
            (key, "zh", "你好", "你好", "hy-mt2-local", "g"),
        )
        tm._db.commit()
        tm.close()

        # Reopening must purge the poisoned row so it can never be replayed.
        tm2 = TranslationMemory(db)
        try:
            assert tm2.get(
                source_language="zh", source_text="你好",
                model_profile="hy-mt2-local", glossary_hash="g",
            ) is None
            row = tm2._db.execute(
                "SELECT COUNT(*) FROM translation_memory "
                "WHERE translated_text = source_text"
            ).fetchone()
            assert row[0] == 0
        finally:
            tm2.close()
