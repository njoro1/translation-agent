"""Phase 1 gate — the global chrome.

The review's §3 findings, as tests:

* the top bar carried eight concerns, two of which duplicated Settings/Run;
* its primary action mutated label + colour per mode and truncated;
* the bottom bar mixed clickable chips with legend chips indistinguishably and
  repeated entry points the rail and the palette already own.

Static assertions cover the composition (what must not be there), dynamic ones
cover the behaviour (what the widget must do).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"

PRIMARY = {
    0: "chrome.primary.run",
    1: "chrome.primary.recheck",
    2: "chrome.primary.exportReport",
    3: "chrome.primary.exportLog",
}


def qml(rel: str) -> str:
    return (QML_DIR / rel).read_text(encoding="utf-8")


def code(rel: str) -> str:
    """The QML with `//` comments removed.

    Every one of these components documents the pattern it replaced, so a naive
    substring scan matches the comment explaining why the thing is gone.
    """
    lines = []
    for line in qml(rel).splitlines():
        stripped = line.split("//")[0]
        lines.append(stripped)
    return "\n".join(lines)


def by_name(root: QObject, name: str) -> QObject:
    for obj in root.findChildren(QObject):
        if obj.objectName() == name:
            return obj
    raise AssertionError(f"no QML object named {name!r}")


# --------------------------------------------------------------------------- #
# §3.1 / §3.4 — what the top bar must NOT contain any more
# --------------------------------------------------------------------------- #

def test_top_bar_has_no_duplicate_editors():
    """Mode, preset and language all had a second home in the top bar."""
    bar = code("components/CommandBar.qml")
    for gone in ("ModePicker", "PresetPicker"):
        assert gone not in bar, f"{gone} is still instantiated in the top bar"
    assert bar.count("SegmentedControl") == 1, (
        "the top bar must carry exactly one segmented control (the theme "
        "toggle); a second one is a duplicated editor"
    )


def test_top_bar_has_no_persistent_save_button():
    """Autosave replaced it; `Saved` and `Save` must never coexist (§3.4)."""
    bar = code("components/CommandBar.qml")
    assert "Save" not in bar, "the top bar still carries a Save affordance"
    assert "saveSettingsRequested" not in bar


def test_top_bar_has_no_settings_search_field():
    """`Search settings…` is convenience inside Settings, not the only nav."""
    assert "Search settings" not in code("components/CommandBar.qml")
    assert 'objectName: "settings.search"' in qml("pages/SettingsPage.qml")


def test_top_bar_composition_is_the_documented_six():
    bar = qml("components/CommandBar.qml")
    for anchor in ('objectName: "chrome.statusStrip"',
                   'objectName: "chrome.commands"',
                   'objectName: "bound.chrome.theme"'):
        assert anchor in bar, f"the top bar lost {anchor}"


# --------------------------------------------------------------------------- #
# §3.3 — the primary action
# --------------------------------------------------------------------------- #

def test_exactly_one_primary_action_per_screen(qml_shown, pump):
    root = qml_shown.root
    for page, name in PRIMARY.items():
        root.setProperty("currentPage", page)
        pump()
        visible = [
            n for n in PRIMARY.values()
            if by_name(root, n).property("visible")
        ]
        assert visible == [name], (
            f"page {page} shows {visible}; exactly one primary action is allowed"
        )


def test_settings_screen_has_no_primary_action(qml_shown, pump):
    """Settings autosaves; a primary action there would be a lie (§3.4)."""
    root = qml_shown.root
    root.setProperty("currentPage", 4)
    pump()
    visible = [n for n in PRIMARY.values() if by_name(root, n).property("visible")]
    assert visible == [], f"the Settings screen shows primary actions: {visible}"


def test_primary_action_label_is_always_run_or_cancel(qml_shown, pump):
    bridge = qml_shown.bridge
    button = by_name(qml_shown.root, "chrome.primary.run")
    qml_shown.root.setProperty("currentPage", 0)
    pump()

    was_running = bridge._is_running
    try:
        for running in (False, True):
            bridge._is_running = running
            bridge.isRunningChanged.emit()
            pump()
            assert button.property("text") in ("Run", "Cancel"), (
                "the primary action changed its identity instead of its state "
                "(it used to become 'Download model & Run')"
            )
            assert button.property("text") == ("Cancel" if running else "Run")
    finally:
        bridge._is_running = was_running
        bridge.isRunningChanged.emit()
        pump()


def test_running_primary_action_is_never_disabled(qml_shown, pump):
    """A bad run must always be stoppable (§6.6)."""
    bridge = qml_shown.bridge
    button = by_name(qml_shown.root, "chrome.primary.run")
    was_running = bridge._is_running
    try:
        bridge._is_running = True
        bridge.isRunningChanged.emit()
        pump()
        assert button.property("enabled") is True
    finally:
        bridge._is_running = was_running
        bridge.isRunningChanged.emit()
        pump()


def test_blocked_primary_action_stays_run_and_is_disabled(qml_shown):
    """A precondition does not redefine the action — it disables it."""
    bridge = qml_shown.bridge
    button = by_name(qml_shown.root, "chrome.primary.run")

    reason = bridge.runBlockedReason
    if reason == "":
        pytest.skip("this machine has every precondition satisfied")

    assert button.property("text") == "Run"
    assert button.property("enabled") is False
    assert str(button.property("blockedReason")) == reason, (
        "the disabled button must carry the reason, so it can state why"
    )


def test_primary_action_never_elides():
    """It sizes to its content, so a mid-word cut is impossible (§3.3)."""
    source = code("components/RunButton.qml")
    body = source.split("contentItem:")[1]
    assert "elide" not in body, "the primary action label elides again"


def test_result_actions_are_disabled_rather_than_ghosted():
    """`Re-check quality` / `Export report` are bound to the store.

    Both are page primaries, so with no result loaded the button used to look
    live and do nothing when pressed (UI review 5.13). The binding is on the
    store's own `resultReady`, so the enabled state cannot drift from the data.
    """
    bar = code("components/CommandBar.qml")
    for name in ("chrome.primary.recheck", "chrome.primary.exportReport"):
        start = bar.index(f'objectName: "{name}"')
        assert "enabled: appBridge.resultReady" in bar[start:start + 400], (
            f"{name} is not bound to the store's resultReady"
        )


def test_the_review_save_action_exists_and_is_bound_to_the_edit_count():
    """Edits had no way to be kept: `saveEditedSubtitles` had no caller at all.

    A fixed cue could only be persisted by pressing Run again. The binding is on
    the edit count rather than on `resultReady`, because a loaded run with no
    edits has nothing to save.
    """
    page = code("pages/ReviewPage.qml")
    start = page.index('objectName: "review.saveChanges"')
    block = page[start:start + 500]
    assert "enabled: appBridge.cueEditedCount > 0" in block
    assert "appBridge.saveEditedSubtitlesToDefault()" in block


# --------------------------------------------------------------------------- #
# §3.1 / §3.2 — the read-only mirrors
# --------------------------------------------------------------------------- #

def test_status_strip_is_read_only():
    strip = code("components/StatusStrip.qml")
    for interactive in ("MouseArea", "onClicked", "TapHandler", "onTapped"):
        assert interactive not in strip, (
            f"the status strip is a mirror, not a control ({interactive})"
        )


def test_status_strip_text_agrees_with_the_store(qml_shown):
    strip = by_name(qml_shown.root, "chrome.statusStrip")
    assert str(strip.property("label")) == qml_shown.bridge.globalStatusText
    assert str(strip.property("tone")) == qml_shown.bridge.globalStatusTone


def test_bottom_bar_has_no_duplicate_launchers():
    """The rail owns navigation and the palette launches things (§3.2)."""
    bar = code("components/StatusBar.qml")
    assert "openLog" not in bar, "the Log button came back"
    assert "MouseArea" not in bar, "the bottom bar should hold no buttons at all"
    assert "onClicked" not in bar


def test_bottom_bar_hints_are_labelled_as_hints():
    """The legend must read as a legend, not as a row of chips."""
    bar = code("components/StatusBar.qml")
    assert '"Shortcuts"' in bar
    hints = bar.split('"Shortcuts"')[1]
    assert "border.width" not in hints, (
        "a bordered chip in the hints row reads as a button"
    )


def test_bottom_bar_status_half_is_intact():
    bar = code("components/StatusBar.qml")
    for anchor in ("stateWord", "appBridge.statusMessage", "stateColor"):
        assert anchor in bar
