"""Encoding/legibility hygiene for the UI source.

Guards against regressions of the mojibake (double-encoded UTF-8) and BOM
issues the UX pass cleaned up.
"""
from __future__ import annotations

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Double-encoded UTF-8 fragments that indicate a previous bad decode.
MOJIBAKE_FRAGMENTS = [
    "\u00e2\u0082\u00ac",  # â‚¬  (Euro)
    "\u00c3\u00a9",          # Ã©    (é)
    "\u00e2\u0080\u0099",    # â€™   (right single quote)
    "\u00e2\u0080\u009c",    # â€œ  (left double quote)
    "\u00e2\u0080\u009d",    # â€   (right double quote)
    "\u00ef\u00bf\u00bd",    # ï¿½  (replacement char)
]

SCAN_ROOTS = [ROOT / "ui", ROOT / "backend", ROOT / "main.py"]


def _iter_sources():
    for entry in SCAN_ROOTS:
        if entry.is_file():
            yield entry
        else:
            yield from entry.rglob("*.py")
            yield from entry.rglob("*.qml")


_SOURCES = list(_iter_sources())


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_byte_order_mark(path):
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf"), f"BOM found in {path}"


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_mojibake(path):
    text = path.read_text(encoding="utf-8")
    for frag in MOJIBAKE_FRAGMENTS:
        assert frag not in text, f"Mojibake {frag!r} detected in {path}"
