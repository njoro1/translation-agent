"""Phase 4 gate — WCAG AA contrast, in both themes.

The review's §2.3 finding: helper and secondary text sat below AA, and the
muted token in particular was almost invisible on the dark surface. Colour is
the one part of a design system that can be checked exactly, so it is checked
here rather than by eye.

The tokens are parsed out of `Theme.qml` rather than duplicated, so this test
fails the moment someone edits a hex value past the threshold — which is the
only way it stays true.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

THEME = Path(__file__).resolve().parent.parent / "ui" / "qml" / "Theme.qml"

# WCAG 2.1 minimums.
AA_NORMAL = 4.5
AA_LARGE = 3.0

# Text roles that must clear AA_NORMAL. `text` is body copy, `textDim` is
# secondary copy, `textMuted` is helper/placeholder copy — all three are read as
# running text, so the large-text exemption does not apply to any of them.
TEXT_ROLES = ("text", "textDim", "textMuted")

# The opaque surfaces those roles are painted on.
SURFACES = ("background", "surface", "surfaceAlt", "surfaceRaised", "inset")

# Status colours are used as text (an error title, a warning row), so they are
# held to the same bar.
STATUS_ROLES = ("success", "warning", "error", "info")


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    """WCAG 2.1 contrast ratio between two `#rrggbb` colours."""
    lf, lb = _relative_luminance(_hex_to_rgb(fg)), _relative_luminance(_hex_to_rgb(bg))
    lighter, darker = max(lf, lb), min(lf, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _tokens() -> dict[str, dict[str, str]]:
    """`{token: {"dark": "#…", "light": "#…"}}` from the theme source."""
    source = THEME.read_text(encoding="utf-8")
    found: dict[str, dict[str, str]] = {}
    pattern = re.compile(
        r"readonly property color (\w+):\s*isDark\s*\?\s*"
        r'"(#[0-9A-Fa-f]{3,8})"\s*:\s*"(#[0-9A-Fa-f]{3,8})"'
    )
    for name, dark, light in pattern.findall(source):
        found[name] = {"dark": dark, "light": light}
    return found


def _accents() -> list[dict[str, str]]:
    """The accent swatch table, plus the ink that is painted on top of it."""
    source = THEME.read_text(encoding="utf-8")
    pattern = re.compile(
        r'\{ id: "(\w+)",\s*label: "[^"]*",\s*dark: "(#[0-9A-Fa-f]{6})",\s*'
        r'light: "(#[0-9A-Fa-f]{6})" \}'
    )
    return [
        {"id": i, "dark": d, "light": l}
        for i, d, l in pattern.findall(source)
    ]


TOKENS = _tokens()
ACCENTS = _accents()
THEMES = ("dark", "light")


def test_the_token_parser_still_sees_the_theme():
    """If this fails the file was restructured and the checks below are vacuous."""
    for role in (*TEXT_ROLES, *SURFACES, *STATUS_ROLES, "accentInk"):
        assert role in TOKENS, f"`{role}` was not parsed out of Theme.qml"
    assert len(ACCENTS) == 5, ACCENTS


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("role", TEXT_ROLES)
def test_text_roles_clear_aa_on_every_surface(theme, role):
    fg = TOKENS[role][theme]
    failures = []
    for surface in SURFACES:
        ratio = contrast(fg, TOKENS[surface][theme])
        if ratio < AA_NORMAL:
            failures.append(f"{role} {fg} on {surface} {TOKENS[surface][theme]}: {ratio:.2f}")
    assert not failures, (
        f"[{theme}] these pairs are below AA ({AA_NORMAL}:1):\n  "
        + "\n  ".join(failures)
    )


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("role", STATUS_ROLES)
def test_status_colours_clear_aa_as_text(theme, role):
    """Status is never colour-only, but the colour is still text (§2.1).

    Swept over **every** surface, not the three a status label is *expected* to
    land on. `Chip` paints a toned chip's text on `surfaceRaised`, and in light
    theme that is the lightest surface in the ramp — so it, not `surface`, is
    the binding constraint. Scoping this to three surfaces is what let every
    light status colour sit at 4.2–4.3:1 on a toned chip unnoticed.
    """
    fg = TOKENS[role][theme]
    failures = []
    for surface in SURFACES:
        ratio = contrast(fg, TOKENS[surface][theme])
        if ratio < AA_NORMAL:
            failures.append(f"{role} {fg} on {surface} {TOKENS[surface][theme]}: {ratio:.2f}")
    assert not failures, (
        f"[{theme}] these pairs are below AA ({AA_NORMAL}:1):\n  "
        + "\n  ".join(failures)
    )


@pytest.mark.parametrize("theme", THEMES)
def test_accent_ink_is_readable_on_every_accent(theme):
    """`accentInk` is the label on the primary action — it must never be a guess."""
    ink = TOKENS["accentInk"][theme]
    failures = []
    for accent in ACCENTS:
        ratio = contrast(ink, accent[theme])
        if ratio < AA_NORMAL:
            failures.append(f"{accent['id']} {accent[theme]}: {ratio:.2f}")
    assert not failures, (
        f"[{theme}] the primary-action label {ink} is below AA on:\n  "
        + "\n  ".join(failures)
    )


@pytest.mark.parametrize("theme", THEMES)
def test_accent_is_readable_as_text_on_surfaces(theme):
    """Accent is used for links and active labels, not only for fills."""
    failures = []
    for accent in ACCENTS:
        for surface in ("surface", "background", "surfaceAlt"):
            ratio = contrast(accent[theme], TOKENS[surface][theme])
            if ratio < AA_LARGE:
                failures.append(
                    f"{accent['id']} on {surface}: {ratio:.2f}"
                )
    assert not failures, (
        f"[{theme}] accent is unreadable as text on:\n  " + "\n  ".join(failures)
    )


@pytest.mark.parametrize("theme", THEMES)
def test_borders_are_visible_against_their_surface(theme):
    """Non-text contrast (WCAG 1.4.11) — a border nobody can see is decoration."""
    for border in ("border", "borderSoft", "borderStrong"):
        ratio = contrast(TOKENS[border][theme], TOKENS["surface"][theme])
        assert ratio >= 1.2, (
            f"[{theme}] {border} {TOKENS[border][theme]} on surface is "
            f"invisible ({ratio:.2f})"
        )


def test_the_two_themes_are_actually_different():
    """A copy-paste that leaves light identical to dark would pass everything."""
    differing = [
        role for role in (*TEXT_ROLES, *SURFACES)
        if TOKENS[role]["dark"] != TOKENS[role]["light"]
    ]
    assert len(differing) >= 6, differing
