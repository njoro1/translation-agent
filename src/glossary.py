"""Glossary support: load user terminology and format it for prompt injection.

Supported glossary file format (plain text, UTF-8)::

    # comment
    source<TAB>target
    source = target
    source -> target

Blank lines and comments (``#``) are ignored. Entries are deduplicated by
source term (first occurrence wins). The glossary is kept small so it never
overwhelms the prompt.
"""
from __future__ import annotations

import os
import re

MAX_GLOSSARY_ENTRIES = 80
MAX_GLOSSARY_CHARS = 2000

# Separators recognised in glossary lines (tried in order).
_SEPARATORS = ("\t", "->", " = ", "=")


def _parse_line(line: str) -> tuple[str, str] | None:
    """Parse a single glossary line into (source, target) or None if invalid."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Try tab first (most explicit), then arrow, then equals.
    if "\t" in line:
        parts = line.split("\t", 1)
    elif "->" in line:
        parts = line.split("->", 1)
    elif "=" in line:
        parts = line.split("=", 1)
    else:
        return None

    if len(parts) != 2:
        return None

    source = parts[0].strip()
    target = parts[1].strip()

    if not source or not target:
        return None

    return source, target


def load_glossary(path: str | None) -> list[tuple[str, str]]:
    """Load a glossary from ``path``.

    - If ``path`` is None or empty, returns ``[]``.
    - If the file is missing, logs a warning and returns ``[]``.
    - Parses UTF-8, deduplicates by source term (first occurrence wins).
    - Truncates to ``MAX_GLOSSARY_ENTRIES`` entries and logs when truncation
      occurs.
    """
    if not path or not path.strip():
        return []

    path = path.strip()

    if not os.path.isfile(path):
        print(f"[glossary] Glossary file not found: {path}", flush=True)
        return []

    entries: list[tuple[str, str]] = []
    seen: set[str] = set()

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                parsed = _parse_line(line)
                if parsed is None:
                    continue
                source, target = parsed
                if source in seen:
                    continue
                seen.add(source)
                entries.append((source, target))
    except OSError as exc:
        print(f"[glossary] Error reading glossary {path}: {exc}", flush=True)
        return []

    print(f"[glossary] Loaded {len(entries)} glossary entries from {path}", flush=True)

    if len(entries) > MAX_GLOSSARY_ENTRIES:
        print(
            f"[glossary] Truncated glossary from {len(entries)} entries to "
            f"{MAX_GLOSSARY_ENTRIES}",
            flush=True,
        )
        entries = entries[:MAX_GLOSSARY_ENTRIES]

    return entries


def format_glossary(entries: list[tuple[str, str]]) -> str:
    """Format glossary entries as an instruction block for the LLM.

    Returns an empty string if ``entries`` is empty so callers can simply
    check truthiness before injecting.

    The formatted output is capped at ``MAX_GLOSSARY_CHARS`` characters.
    """
    if not entries:
        return ""

    lines = ["Use the following glossary consistently:"]
    for source, target in entries:
        lines.append(f"- {source} -> {target}")

    formatted = "\n".join(lines)

    if len(formatted) > MAX_GLOSSARY_CHARS:
        # Cut at the last complete line that fits.
        cut = formatted[:MAX_GLOSSARY_CHARS]
        last_nl = cut.rfind("\n")
        if last_nl > 0:
            formatted = cut[:last_nl]
        else:
            formatted = cut

    return formatted


def glossary_hash(entries: list[tuple[str, str]]) -> str:
    """Return a SHA-256 hash of the formatted glossary string.

    Used as a component of translation-memory keys so that a glossary change
    invalidates cached translations. An empty glossary hashes the empty string.
    """
    import hashlib

    formatted = format_glossary(entries)
    return hashlib.sha256(formatted.encode("utf-8")).hexdigest()
