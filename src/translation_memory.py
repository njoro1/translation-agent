"""Translation memory: SQLite-backed cache for exact repeated source lines.

Stores (source_language, model_profile, glossary_hash, normalized_source_text)
-> translated_text so that repeated greetings, catchphrases, and recurring
lines are reused without calling the model again.

Design:
    - Exact matching only (no fuzzy match).
    - Key is SHA-256 of "source_language|model_profile|glossary_hash|normalized_source".
    - Graceful degradation: if SQLite fails, the memory disables itself and
      translation continues without caching.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB_PATH = os.path.join("cache", "translation_memory.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS translation_memory (
    key TEXT PRIMARY KEY,
    source_language TEXT NOT NULL,
    source_text TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    model_profile TEXT NOT NULL,
    glossary_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    hits INTEGER NOT NULL DEFAULT 1
);
"""


def _normalize(text: str) -> str:
    """Normalize source text for key generation.

    - Trim leading/trailing whitespace.
    - Collapse consecutive whitespace to a single space.
    - Preserve Unicode case and punctuation.
    """
    return re.sub(r"\s+", " ", text.strip())


def make_key(
    *,
    source_language: str | None,
    source_text: str,
    model_profile: str,
    glossary_hash: str,
) -> str:
    """Generate the SHA-256 key for a translation-memory entry."""
    lang = (source_language or "").strip()
    normalized = _normalize(source_text)
    payload = f"{lang}|{model_profile}|{glossary_hash}|{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TranslationMemory:
    """SQLite-backed translation memory with graceful failure handling.

    If the database cannot be opened or any operation fails, the instance
    disables itself and ``get``/``put`` become no-ops so translation never
    crashes due to a cache problem.
    """

    def __init__(self, db_path: str | Path = _DEFAULT_DB_PATH):
        self._db_path = str(db_path)
        self._enabled = True
        self._db: sqlite3.Connection | None = None

        try:
            db_dir = os.path.dirname(self._db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self._db = sqlite3.connect(self._db_path, check_same_thread=False)
            self._db.execute(_SCHEMA)
            self._db.commit()
            self._purge_poisoned_entries()
            print(f"[tm] Using translation memory: {self._db_path}", flush=True)
        except Exception as exc:  # noqa: BLE001 - graceful degradation
            print(f"[tm] Translation memory disabled due to error: {exc}", flush=True)
            self._enabled = False
            self._db = None

    @property
    def enabled(self) -> bool:
        """True if the memory is operational (DB opened successfully)."""
        return self._enabled and self._db is not None

    def _purge_poisoned_entries(self) -> None:
        """Remove old entries whose cached "translation" is broken garbage.

        Two classes of poisoned data are removed so they are never replayed:

        1. Passthrough entries whose 'translation' is identical to their source.
           Before output validation existed, a failed local call could store the
           source text as the cached "translation" (see SUBTITLE_QUALITY_REPORT
           §3.2): every later run then replayed untranslated Chinese straight from
           the cache — compounding the defect across runs.

        2. Entries whose translation carries leaked fansub/ASR markup — a literal
           `[CHENGYU:` wrapper or a raw SenseVoice `<|...|>` control tag. These
           arise when the model echoes the chengyu-flagging/emotion prompts back
           (the exact 50元 regression), producing run-on or marker-laced lines.
           Such entries are strictly worse than re-translating, so they are purged
           on startup.
        """
        conditions = [
            "translated_text = source_text",
            "translated_text LIKE '%[CHENGYU:%'",
            "translated_text LIKE '%<|%'",
        ]
        try:
            for cond in conditions:
                row = self._db.execute(
                    f"SELECT COUNT(*) FROM translation_memory WHERE {cond}"
                ).fetchone()
                poisoned = int(row[0]) if row else 0
                if poisoned:
                    self._db.execute(
                        f"DELETE FROM translation_memory WHERE {cond}"
                    )
                    self._db.commit()
                    print(
                        f"[tm] Purged {poisoned} poisoned cache entrie(s) "
                        f"({cond})",
                        flush=True,
                    )
        except Exception as exc:  # noqa: BLE001 - cleanup must never kill the cache
            print(f"[tm] Poisoned-entry cleanup skipped: {exc}", flush=True)

    def get(
        self,
        *,
        source_language: str | None,
        source_text: str,
        model_profile: str,
        glossary_hash: str,
    ) -> str | None:
        """Return a cached translation for an exact source match, or None."""
        if not self.enabled:
            return None
        key = make_key(
            source_language=source_language,
            source_text=source_text,
            model_profile=model_profile,
            glossary_hash=glossary_hash,
        )
        try:
            cur = self._db.execute(
                "SELECT translated_text FROM translation_memory WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            now = datetime.now(timezone.utc).isoformat()
            self._db.execute(
                "UPDATE translation_memory SET last_used_at = ?, hits = hits + 1 "
                "WHERE key = ?",
                (now, key),
            )
            self._db.commit()
            return row[0]
        except Exception as exc:  # noqa: BLE001 - graceful degradation
            print(f"[tm] Translation memory disabled due to error: {exc}", flush=True)
            self._enabled = False
            return None

    def put(
        self,
        *,
        source_language: str | None,
        source_text: str,
        translated_text: str,
        model_profile: str,
        glossary_hash: str,
    ) -> None:
        """Store a translation. No-op if disabled or translation is empty."""
        if not self.enabled:
            return
        if not translated_text or not translated_text.strip():
            return
        if not source_text or not source_text.strip():
            return
        # Never cache a passthrough: storing the source as its own "translation"
        # poisons every future run (a failed cue would be replayed as translated).
        if _normalize(translated_text) == _normalize(source_text):
            return

        key = make_key(
            source_language=source_language,
            source_text=source_text,
            model_profile=model_profile,
            glossary_hash=glossary_hash,
        )
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._db.execute(
                "INSERT INTO translation_memory "
                "(key, source_language, source_text, translated_text, "
                " model_profile, glossary_hash, created_at, last_used_at, hits) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(key) DO UPDATE SET "
                "  translated_text = excluded.translated_text, "
                "  last_used_at = excluded.last_used_at",
                (
                    key,
                    (source_language or "").strip(),
                    _normalize(source_text),
                    translated_text.strip(),
                    model_profile,
                    glossary_hash,
                    now,
                    now,
                ),
            )
            self._db.commit()
        except Exception as exc:  # noqa: BLE001 - graceful degradation
            print(f"[tm] Translation memory disabled due to error: {exc}", flush=True)
            self._enabled = False

    def close(self) -> None:
        """Close the database connection (no-op if already closed/disabled)."""
        if self._db is not None:
            try:
                self._db.close()
            except Exception:  # noqa: BLE001 - best effort
                pass
            self._db = None

