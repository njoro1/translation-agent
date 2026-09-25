"""Phase 2 gate — the Settings information architecture.

The review's §5 findings, as tests. The headline one: the left rail highlighted a
category while the content pane rendered *every* category and merely scrolled to
the right one, so "the highlighted category" and "what is on screen" could
disagree. That is asserted here against real `visible` properties, not by eye.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QObject

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"
SETTINGS = "pages/SettingsPage.qml"

CATEGORIES = (
    "appearance",
    "translation",
    "transcription",
    "models",
    "shortcuts",
    "privacy",
    "about",
)

SETTINGS_PAGE = 4


def qml(rel: str) -> str:
    return (QML_DIR / rel).read_text(encoding="utf-8")


def code(rel: str) -> str:
    return "\n".join(line.split("//")[0] for line in qml(rel).splitlines())


def by_name(root: QObject, name: str) -> QObject:
    for obj in root.findChildren(QObject):
        if obj.objectName() == name:
            return obj
    raise AssertionError(f"no QML object named {name!r}")


def visible_cards(root: QObject) -> list[str]:
    return sorted(
        obj.objectName()
        for obj in root.findChildren(QObject)
        if obj.objectName().startswith("settings.card.") and obj.property("visible")
    )


@pytest.fixture()
def settings_page(qml_shown, pump):
    """The Settings screen, actually on screen so `visible` is meaningful."""
    qml_shown.root.setProperty("currentPage", SETTINGS_PAGE)
    pump()
    page = by_name(qml_shown.root, "settings.page")
    yield qml_shown.root, page
    page.setProperty("searchQuery", "")
    qml_shown.root.setProperty("currentPage", 0)
    pump()


# --------------------------------------------------------------------------- #
# §5.2 — the rail highlight must equal what is rendered
# --------------------------------------------------------------------------- #

def test_exactly_one_category_renders_at_a_time(settings_page, pump):
    root, page = settings_page
    for category in CATEGORIES:
        page.setProperty("currentSection", category)
        pump()
        assert visible_cards(root) == [f"settings.card.{category}"], (
            f"selecting {category!r} rendered {visible_cards(root)}; the "
            f"highlight and the content pane must agree"
        )


def test_the_category_list_is_the_documented_seven():
    source = code(SETTINGS)
    # Only the rail's own `sections` array — the accent swatches use the same
    # `{ id, label }` shape and would otherwise be counted as categories.
    block = source.split("property var sections: [")[1].split("]")[0]
    declared = re.findall(r'\{ id: "([a-z]+)", label:', block)
    assert tuple(declared) == CATEGORIES, (
        f"categories changed: {declared}. The plan pins exactly these seven; "
        f"`Environment` was folded into About / Data & privacy."
    )
    assert '"environment"' not in source


def test_search_filters_within_the_selected_category_only(settings_page, pump):
    """Search is convenience, not navigation (§5.2)."""
    root, page = settings_page
    page.setProperty("currentSection", "translation")
    page.setProperty("searchQuery", "theme")
    pump()
    assert visible_cards(root) == ["settings.card.translation"], (
        "a query must never re-render a different category"
    )


def test_clearing_the_query_restores_the_full_category(settings_page, pump):
    root, page = settings_page
    page.setProperty("currentSection", "models")
    page.setProperty("searchQuery", "zzz-no-match")
    pump()
    assert visible_cards(root) == ["settings.card.models"]
    page.setProperty("searchQuery", "")
    pump()
    assert visible_cards(root) == ["settings.card.models"]


# --------------------------------------------------------------------------- #
# §5.4 — the model inventory table
# --------------------------------------------------------------------------- #

def test_model_size_never_carries_a_path(app_bridge):
    """SIZE used to read `242.4 MB · dist\\gg`, painting over PURPOSE."""
    for row in app_bridge.modelsInventory:
        assert "\\" not in row["size"] and "/" not in row["size"], (
            f"{row['file']}: SIZE is {row['size']!r}; the folder tail must "
            f"travel in `note`, not in the size cell"
        )


def test_every_model_row_decides_its_own_verb(app_bridge):
    """The verb is decided in Python, where it is testable (§5.4)."""
    for row in app_bridge.modelsInventory:
        assert row["actionLabel"], f"{row['file']} has no verb"
        assert isinstance(row["actionEnabled"], bool)
        assert row["state"] and row["tone"], f"{row['file']} has no §2.1 state"


def test_cache_row_verb_is_never_download(app_bridge):
    """The cache row's action id is `tm` and the view had no branch for it, so
    it fell through to "Download" — you do not download a cache."""
    cache = [r for r in app_bridge.modelsInventory if r["action"] == "tm"]
    assert len(cache) == 1, "the cache row is missing"
    verb = cache[0]["actionLabel"]
    assert verb in ("Purge", "Build"), verb
    assert verb != "Download"


def test_model_table_columns_have_a_minimum_width():
    """Every column is minimum-width, so no cell can paint over its neighbour."""
    source = code(SETTINGS)
    table = source.split('objectName: "settings.modelTable"')[1]
    header = table.split("Repeater")[0]
    assert header.count("Layout.minimumWidth") >= 5, (
        "a column in the model table header has no minimum width"
    )


# --------------------------------------------------------------------------- #
# §5.6 — raw internals behind Copy diagnostics; destruction gated
# --------------------------------------------------------------------------- #

def test_raw_internals_are_not_rendered_inline():
    """No absolute path, registry key, Python/Qt version or `Frozen build`."""
    source = code(SETTINGS)
    assert "environmentRows" not in source, (
        "the raw internals list is being rendered inline again; it belongs "
        "behind Copy diagnostics"
    )
    assert "Copy diagnostics" in source
    assert "appBridge.copyToDiagnostics()" in source
    assert "environmentSummary" in source, (
        "the jargon-free replacement line is gone"
    )


def test_copy_diagnostics_payload_does_contain_the_paths(app_bridge):
    """The paths must still be *reachable* — that is the point of the button."""
    text = app_bridge.copySummaryText()
    assert "Models folder" in text and "Settings store" in text


def test_privacy_label_is_not_truncated():
    source = qml(SETTINGS)
    assert "Network calls in Offline" in source
    assert "Network calls in Offl\u2026" not in source


def test_clear_stored_settings_is_in_a_danger_zone():
    """Destructive and safe actions must not look alike (§5.6)."""
    source = code(SETTINGS)
    assert "DangerZone {" in source
    assert "clearDialog" not in source, "the OK/Cancel dialog came back"

    zone = code("components/DangerZone.qml")
    assert "confirmWord" in zone and "armed" in zone, (
        "the danger zone lost its typed confirmation"
    )
    assert "confirmed()" in zone, "the zone cannot emit its confirmation"


def test_danger_zone_needs_the_exact_word(settings_page):
    zone = by_name(settings_page[0], "settings.dangerZone")
    assert zone.property("armed") is False, "the zone starts armed"
    word = str(zone.property("confirmWord"))
    assert word, "no confirmation word is set"
    # A near miss must not arm it.
    field = zone.findChild(QObject, "dangerZoneConfirm")
    if field is not None:
        field.setProperty("text", word[:-1])
        assert zone.property("armed") is False


# --------------------------------------------------------------------------- #
# §5.5 — shortcuts are an editor, not a read-only list
# --------------------------------------------------------------------------- #

def test_shortcuts_are_remappable(app_bridge):
    rows = app_bridge.shortcutRows
    assert rows, "no shortcut rows"
    for row in rows:
        assert {"action", "label", "sequence", "default"}.issubset(row.keys())


def test_shortcut_map_is_what_qml_reads(app_bridge):
    mapping = app_bridge.shortcutMap
    assert isinstance(mapping, dict) and mapping
    for row in app_bridge.shortcutRows:
        assert mapping[row["action"]] == row["sequence"]


def test_remapping_a_shortcut_round_trips(app_bridge):
    action = app_bridge.shortcutRows[0]["action"]
    original = app_bridge.shortcutMap[action]
    try:
        problem = app_bridge.setShortcut(action, "Ctrl+Alt+Shift+F9")
        assert problem == "", problem
        assert app_bridge.shortcutMap[action] == "Ctrl+Alt+Shift+F9"
    finally:
        app_bridge.resetShortcut(action)
    assert app_bridge.shortcutMap[action] == original


def test_shortcut_conflicts_are_flagged_on_both_rows(app_bridge):
    """A duplicate combo means one binding silently never fires.

    The store accepts the value — a user swapping two shortcuts has to pass
    through a collision — but both affected rows must say so.
    """
    rows = app_bridge.shortcutRows
    if len(rows) < 2:
        pytest.skip("needs two shortcuts")
    first, second = rows[0]["action"], rows[1]["action"]
    clash = app_bridge.shortcutMap[first]
    try:
        app_bridge.setShortcut(second, clash)
        flagged = {
            r["action"]: r["conflict"]
            for r in app_bridge.shortcutRows
            if r["action"] in (first, second)
        }
        assert flagged[first] and flagged[second], (
            f"the duplicate {clash!r} is not flagged on both rows: {flagged}"
        )
    finally:
        app_bridge.resetShortcut(second)
    assert not any(r["conflict"] for r in app_bridge.shortcutRows), (
        "the conflict flag stayed on after the collision was undone"
    )


def test_reset_all_restores_the_defaults(app_bridge):
    action = app_bridge.shortcutRows[0]["action"]
    app_bridge.setShortcut(action, "Ctrl+Alt+Shift+F9")
    app_bridge.resetAllShortcuts()
    row = [r for r in app_bridge.shortcutRows if r["action"] == action][0]
    assert app_bridge.shortcutMap[action] == row["default"]


def test_settings_shortcut_surface_is_a_recorder():
    source = code(SETTINGS)
    assert "ShortcutRecorder" in source
    assert "shortcutRows" in source
