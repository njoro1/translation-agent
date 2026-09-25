"""Encoding/legibility hygiene for the UI source.

Guards against regressions of the mojibake (double-encoded UTF-8) and BOM
issues the UX pass cleaned up, plus the legibility rules from the review:

* **D4** — a control label must never be truncated mid-word. Controls carry
  fixed, hand-written labels, so an `elide` on one is always a layout bug being
  papered over. Data labels (metric values, file paths) may elide, but then the
  full text has to stay reachable, which in this codebase means a `ToolTip`.
* **D4b** — nothing opaque is painted over readable text.
* **§2.1** — status is shape-first. A status rendering that only changes colour
  fails greyscale, so every status must carry a glyph or a word.
"""
from __future__ import annotations

import re

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QML = ROOT / "ui" / "qml"

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

# `ui/qml/archive/` is retired dead code — never edited, never policed.
EXCLUDED = ("ui/qml/archive",)


def _iter_sources():
    for entry in SCAN_ROOTS:
        if entry.is_file():
            yield entry
        else:
            yield from entry.rglob("*.py")
            yield from entry.rglob("*.qml")


def _live(entry: Path) -> bool:
    rel = str(entry.relative_to(ROOT)).replace("\\", "/")
    return not any(rel.startswith(prefix) for prefix in EXCLUDED)


_SOURCES = [p for p in _iter_sources() if _live(p)]


# --- Rules that apply to every source ---------------------------------------

@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_byte_order_mark(path):
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf"), f"BOM found in {path}"


@pytest.mark.parametrize("path", _SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_mojibake(path):
    text = path.read_text(encoding="utf-8")
    for frag in MOJIBAKE_FRAGMENTS:
        assert frag not in text, f"Mojibake {frag!r} detected in {path}"


# --- D4: no truncated control labels ----------------------------------------

# Controls whose labels are fixed strings chosen by the author. If one of these
# elides, the layout is too tight — fix the layout, not the word.
CONTROL_COMPONENTS = (
    "AppButton",
    "Chip",
    "Pill",
    "StatusMark",
    "SegmentedControl",
    "RunButton",
)

# Components that render *data* (metric values, paths, counts). These may elide,
# but the full text must remain reachable on hover.
DATA_COMPONENTS = ("StatTile", "MetricChip", "KeyValue", "AppCard")

_OBJECT_RE = re.compile(r"^(\s*)(?:[\w.]+\s*:\s*)?([A-Z][\w.]*)\s*\{\s*$")


def _component_path(name: str) -> Path:
    return QML / "components" / f"{name}.qml"


def _object_blocks(text: str):
    """`[(type_name, body_text)]` for every multi-line `Type {` block.

    Indentation-based rather than brace-counted: this codebase is uniformly
    four-space indented, and a block ends at the first line that closes at or
    above its own indent.
    """
    lines = text.splitlines()
    blocks = []
    for i, line in enumerate(lines):
        m = _OBJECT_RE.match(line)
        if not m:
            continue
        indent = len(m.group(1))
        body = []
        for nxt in lines[i + 1:]:
            if nxt.strip().startswith("}") and (len(nxt) - len(nxt.lstrip())) <= indent:
                break
            body.append(nxt)
        blocks.append((m.group(2), "\n".join(body)))
    return blocks


@pytest.mark.parametrize("name", CONTROL_COMPONENTS)
def test_control_components_never_elide(name):
    """A control label that elides is a control that lies about its own name."""
    source = _component_path(name).read_text(encoding="utf-8")
    offenders = [
        block_type
        for block_type, body in _object_blocks(source)
        if "elide:" in body and "Text.ElideNone" not in body
    ]
    assert not offenders, (
        f"{name}.qml elides inside {offenders}. Control labels are fixed "
        f"strings — widen the control instead (UI review D4)."
    )


@pytest.mark.parametrize("name", DATA_COMPONENTS)
def test_data_components_keep_elided_text_reachable(name):
    """Eliding a value is fine; hiding it is not. `ToolTip` is the escape hatch."""
    source = _component_path(name).read_text(encoding="utf-8")
    elides = any(
        "elide:" in body and "Text.ElideNone" not in body
        for _, body in _object_blocks(source)
    )
    if elides:
        assert "ToolTip" in source, (
            f"{name}.qml elides text but offers no ToolTip, so the full value is "
            f"unreachable (UI review D4)."
        )


def test_metric_chip_does_not_uppercase_or_clip_its_label():
    """The exact defect: `StatTile` uppercased + elided the metric label."""
    source = _component_path("MetricChip").read_text(encoding="utf-8")
    assert ".toUpperCase()" not in source, (
        "MetricChip uppercases its label — that is what turned 'Max line chars' "
        "into 'MAX LINE CH…' (UI review D4 / 5.11)."
    )
    assert "wrapMode: Text.WordWrap" in source, (
        "MetricChip's label must wrap; the row is the thing that should grow."
    )


def test_quality_metric_row_wraps_instead_of_clipping():
    """`RowLayout` cannot wrap, so seven tiles across always clipped."""
    page = (QML / "pages" / "QualityPage.qml").read_text(encoding="utf-8")
    assert "OverflowRow" in page, "QualityPage's metric row must use OverflowRow"
    assert "MetricChip" in page, "QualityPage's metric row must use MetricChip"
    assert "quality.metricRow" in page, "the metric row needs a stable objectName"

    row = _component_path("OverflowRow").read_text(encoding="utf-8")
    m = re.search(r"property int minCellWidth:\s*(\d+)", row)
    assert m and int(m.group(1)) >= 140, (
        "'Max line chars' and 'Strict gate' need >= 140px to wrap into two "
        "whole lines rather than elide."
    )


def test_metric_labels_are_full_words():
    """Never ship an abbreviation a user cannot decode (UI review 5.11)."""
    source = (ROOT / "backend" / "bridge.py").read_text(encoding="utf-8")
    block = source.split("def qualityTiles", 1)[1].split("def qualityLimits", 1)[0]
    for label in ("Total cues", "Untranslated", "Errors", "Warnings",
                  "Avg CPS", "Max line chars", "Strict gate"):
        assert f'"{label}"' in block, f"qualityTiles lost the label {label!r}"
    # An abbreviation with no vowel-dot or word boundary is the smell.
    assert "MAX LINE" not in block.upper() or "Max line chars" in block


# --- D4b: nothing opaque is painted over text -------------------------------

_PAGES = sorted((QML / "pages").glob("*.qml"))


@pytest.mark.parametrize("path", _PAGES, ids=lambda p: p.name)
def test_no_opaque_overlay_declared_after_text(path):
    """A filled rectangle anchored over a sibling label hides the label.

    The review's `Open Settings` finding was exactly this: a floating action
    declared last in the card, covering the readiness footer. Z-order follows
    declaration order, so an opaque `anchors.fill` sibling *after* a `Label` is
    a paint-over by construction.
    """
    text = path.read_text(encoding="utf-8")
    offenders = []
    for _, body in _object_blocks(text):
        seen_label = False
        for line in body.splitlines():
            if re.match(r"^\s*(?:Label|Text)\s*\{", line):
                seen_label = True
                continue
            if not seen_label:
                continue
            if "anchors.fill" in line and "color:" in line:
                offenders.append(line.strip())
    assert not offenders, (
        f"{path.name} declares an opaque `anchors.fill` sibling after a label, "
        f"so it paints over readable text: {offenders}"
    )


# --- §2.1: status is shape-first -------------------------------------------

_STATUS_PAGE_HINTS = {
    "RunPage.qml": "the readiness checklist",
    "QualityPage.qml": "the issues table",
    "ReviewPage.qml": "the cues table",
    "SettingsPage.qml": "the model table",
}


@pytest.mark.parametrize("page,what", sorted(_STATUS_PAGE_HINTS.items()))
def test_status_renderings_are_shape_first(page, what):
    """Every status in a page carries a glyph or a word, not just a colour."""
    text = (QML / "pages" / page).read_text(encoding="utf-8")
    if page == "ReviewPage.qml":
        # Review's status lives in the shared table component.
        text += (QML / "components" / "CuePreviewTable.qml").read_text(encoding="utf-8")
    has_status = any(
        token in text
        for token in ("StatusMark", "Chip {", "statusIcon", "statusLabel", "iconName")
    )
    assert has_status, (
        f"{page} renders {what} without a glyph or a word — colour alone fails "
        f"greyscale (UI review 2.1)."
    )


# --- T-4.5: the three appearance toggles must actually do something ---------

_ANIMATED_COMPONENTS = (
    "StageStrip", "Toast", "StatusBar", "StatusPill", "StatusStrip",
    "Pill", "ProgressRing", "ProgressPanel", "AppButton", "AppSwitch",
    "RunButton", "Timeline", "Histogram",
)


@pytest.mark.parametrize("name", _ANIMATED_COMPONENTS)
def test_reduced_motion_reaches_every_animated_component(name):
    """A pulsing dot that keeps pulsing after the toggle is a broken toggle."""
    source = _component_path(name).read_text(encoding="utf-8")
    animates = any(
        token in source
        for token in ("Behavior on", "NumberAnimation", "ColorAnimation",
                      "SequentialAnimation", "running:")
    )
    if animates:
        assert "reducedMotion" in source, (
            f"{name}.qml animates but never consults Theme.reducedMotion, so it "
            f"keeps moving when the user asked it to stop (UI review 2.4)."
        )


def test_every_behavior_collapses_under_reduced_motion():
    """`Behavior on x { NumberAnimation { duration: N } }` must become 0ms."""
    offenders = []
    for path in sorted(QML.rglob("*.qml")):
        if "archive" in str(path):
            continue
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"Behavior on \w+\s*\{[^}]*\}", src, re.S):
            if "reducedMotion" not in m.group(0):
                offenders.append(f"{path.name}: {m.group(0).strip()[:70]}")
    assert not offenders, (
        "these Behaviours ignore the reduced-motion toggle:\n  " + "\n  ".join(offenders)
    )


def test_density_reaches_spacing_type_and_control_height():
    """Comfortable must widen the gaps as well as the glyphs."""
    src = (QML / "Theme.qml").read_text(encoding="utf-8")
    spacing = src.split("--- Spacing scale", 1)[1].split("--- Radii", 1)[0]
    assert "comfortable" in spacing, (
        "the spacing scale ignores `comfortable`, so a comfortable window packs "
        "bigger text into the same gaps."
    )
    for token in ("fontBoost", "controlHeight:", "rowHeight:"):
        assert token in src, f"Theme.qml lost `{token}`"


def test_accent_swatches_are_never_hardcoded_outside_theme():
    """One accent table, one source of truth for the brand hue."""
    theme = (QML / "Theme.qml").read_text(encoding="utf-8")
    swatches = re.findall(r'"(#[0-9A-Fa-f]{6})"', theme)
    # Only the hexes that belong to the accent table, not every colour token.
    table = theme.split("accentChoices", 1)[1].split("]", 1)[0]
    accent_hexes = set(re.findall(r'"(#[0-9A-Fa-f]{6})"', table))
    assert len(accent_hexes) == 10, f"expected 5 swatches x 2 themes, got {accent_hexes}"

    offenders = []
    for path in sorted(QML.rglob("*.qml")):
        if "archive" in str(path) or path.name == "Theme.qml":
            continue
        src = path.read_text(encoding="utf-8")
        for hex_value in accent_hexes:
            if hex_value in src:
                offenders.append(f"{path.name}: {hex_value}")
    assert not offenders, (
        "accent hexes are hardcoded outside Theme.qml, so changing the accent "
        "would not recolour them:\n  " + "\n  ".join(offenders)
    )
    assert swatches  # the parser above is not vacuous


def test_primary_action_uses_accent_ink():
    """The label on a filled accent surface comes from the ink token."""
    for name in ("AppButton", "RunButton", "SegmentedControl", "StatusMark"):
        src = _component_path(name).read_text(encoding="utf-8")
        if "Theme.accent" in src:
            assert "Theme.accentInk" in src, (
                f"{name}.qml fills with the accent but does not use "
                f"`Theme.accentInk` for the label painted on it."
            )


# --- T-4.6: empty screens show a prompt, not machinery ---------------------

_EMPTY_STATE_MARKERS = {
    "QualityPage.qml": "quality.emptyState",
    "ReviewPage.qml": "review.emptyState",
}


@pytest.mark.parametrize("page,marker", sorted(_EMPTY_STATE_MARKERS.items()))
def test_empty_pages_prompt_instead_of_showing_ghost_data(page, marker):
    src = (QML / "pages" / page).read_text(encoding="utf-8")
    assert "EmptyState" in src, f"{page} has no empty state"
    assert marker in src, f"{page}'s empty state needs a stable objectName"
    assert "!appBridge.resultReady" in src, (
        f"{page}'s empty state must be gated on the absence of a result"
    )
    # The prompt names the next action; "no data" is not actionable.
    assert "actionLabel" in src, (
        f"{page}'s empty state does not offer a next action"
    )


def _lines_after(src: str, needle: str, count: int = 12) -> str:
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return "\n".join(lines[i:i + count])
    return ""


@pytest.mark.parametrize("page,anchor", [
    ("QualityPage.qml", "id: content"),
    ("ReviewPage.qml", "anchors.margins: 18"),
])
def test_populated_content_is_hidden_when_empty(page, anchor):
    """Ghosted machinery with fake numbers is worse than an empty screen.

    `warn 18 · error 22` rendered against zero cues reads as a real report.
    The populated column must be *hidden*, not filled with placeholders.
    """
    src = (QML / "pages" / page).read_text(encoding="utf-8")
    window = _lines_after(src, anchor)
    assert "visible: appBridge.resultReady" in window, (
        f"{page}: the populated content starting at `{anchor}` is not gated on "
        f"`appBridge.resultReady`, so it renders placeholders on an empty screen."
    )


def test_empty_state_is_the_log_pattern():
    """One empty-screen shape for the whole app: icon, title, body, one action."""
    src = _component_path("EmptyState").read_text(encoding="utf-8")
    for part in ("iconName", "title", "body", "actionLabel", "actionTriggered"):
        assert part in src, f"EmptyState lost `{part}`"
    assert src.count("AppButton") == 1, (
        "EmptyState must offer exactly one next action — a menu of options on an "
        "empty screen is the same friction as the machinery it replaced."
    )


def test_log_page_keeps_its_empty_text():
    """Log was the reference implementation; it must not regress."""
    src = (QML / "pages" / "LogPage.qml").read_text(encoding="utf-8")
    assert "emptyText" in src and "Nothing logged yet" in src




# --- §2.1b — an icon name that does not exist renders nothing, silently ------
#
# `Icon` looks its name up in a geometry table and returns an empty path for an
# unknown key, so a typo is invisible: no warning, no placeholder, just a gap.
# Nothing else in the suite reads that table, which is how a command palette can
# ship with `icon: "key"` and `icon: "trash"` against a registry that has
# neither.

def _icon_glyphs() -> set[str]:
    src = (QML / "components" / "Icon.qml").read_text(encoding="utf-8")
    table = src.split("readonly property var _paths: ({", 1)[1].split("\n    })", 1)[0]
    return set(re.findall(r"^\s*(\w+):", table, re.MULTILINE))


_ICON_USES = [
    (path, name)
    for path in _SOURCES
    if path.suffix == ".qml"
    for name in re.findall(
        # `name:\s*"…"` — the `\s` was written as `/s` here, which matched
        # nothing at all, so `test_every_icon_name_resolves_to_a_glyph` ran over
        # an empty list and the guard below never fired on a real typo.
        r'Icon\s*\{[^{}]*?name:\s*"([^"]+)"',
        path.read_text(encoding="utf-8"),
        re.DOTALL,
    )
]


@pytest.mark.parametrize(
    "path,name", _ICON_USES, ids=[f"{p.name}:{n}" for p, n in _ICON_USES]
)
def test_every_icon_name_resolves_to_a_glyph(path, name):
    assert name in _icon_glyphs(), (
        f"{path.relative_to(ROOT)} renders Icon {{ name: \"{name}\" }}, which "
        f"Icon.qml does not define — it will draw nothing at all"
    )


def test_the_icon_table_is_not_empty():
    """A parse failure would make the rule above vacuously pass.

    The usage count is low by design: most `Icon` blocks take their name from
    data (`name: modelData.icon`, `name: root.statusIcon(...)`), and only the
    literal names can be checked statically.
    """
    assert len(_icon_glyphs()) > 30, "could not read Icon.qml's glyph table"
    assert len(_ICON_USES) >= 10, "found almost no literal Icon usages to check"
