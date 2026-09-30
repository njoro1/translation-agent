"""Old-UI parity — nothing the pre-redesign shell could do was dropped.

The redesign was checked against the UI it replaced (`git archive f6860e6 ui/qml`,
the "New UI" commit) by diffing appBridge members, invocation sites, interaction
primitives and every distinct label literal. That diff found exactly three things
that did not survive, and this module is their regression guard:

1. **`Ctrl+4`** reached the fourth screen (Log) positionally. The redesign moved
   Log onto `Ctrl+L` and left `Ctrl+4` dead. Restored as an alias on
   `chrome.shortcut.goto_log_alt`.
2. **`'Auto-named from the title'`** — the out-path placeholder. The new field
   says `Saved next to the video` and adds a store-backed `outPathHint` line
   underneath, so the affordance is intact; asserted here so it stays that way.
3. **`'Content preset tunes ASR, preprocessing, context and prompt style.'`** —
   a `ToolTip` on the old `PresetPicker`. The new chip row has nothing to hover,
   so the sentence moved to `run.presetHint`.

Everything else in the diff was a rename, a repurposition, or an intentional
consolidation (three per-column `ScrollView`s became one `Flickable`; two
`Dialog`s became one `Dialog` plus the typed-confirmation `DangerZone`).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"

# Store id -> the page index that id must open. Mirrors `_SHORTCUT_DEFAULTS`
# plus the `switchToTab` targets in `Main.qml`.
GOTO_ROUTES = {
    "goto_run": 0,
    "goto_review": 1,
    "goto_quality": 2,
    "goto_log": 3,
    "goto_settings": 4,
}


def qml(rel: str) -> str:
    return (QML_DIR / rel).read_text(encoding="utf-8")


def code(rel: str) -> str:
    """The QML with `//` comments removed.

    Every block that replaced something documents what it replaced, so a naive
    substring scan matches the comment explaining why the thing is gone.
    """
    return "\n".join(
        line.split("//")[0] for line in qml(rel).splitlines()
    )


def by_name(root: QObject, name: str) -> QObject:
    for obj in root.findChildren(QObject):
        if obj.objectName() == name:
            return obj
    raise AssertionError(f"no QML object named {name!r}")


# --------------------------------------------------------------------------- #
# 1. Keyboard routes
# --------------------------------------------------------------------------- #

def test_every_screen_keeps_a_keyboard_route(qml_shown):
    """All five screens are reachable by key, from the store, as before."""
    shell = qml("Main.qml")
    keys = qml_shown.bridge.shortcutMap
    for action, index in GOTO_ROUTES.items():
        assert keys.get(action), f"{action} lost its default sequence"
        assert f'window.keys["{action}"]' in shell, (
            f"{action} is in the store but no Shortcut binds to it"
        )
        assert f"switchToTab({index})" in shell


def test_ctrl_4_still_opens_the_log_screen(qml_shown, pump):
    """The positional binding the redesign dropped. It must actually navigate.

    `qml_shown` wraps the session-scoped `qml_main` engine, so the page index is
    put back afterwards — a leaked `currentPage` makes every later "is this
    widget visible" assertion fail.
    """
    alias = by_name(qml_shown.root, "chrome.shortcut.goto_log_alt")
    assert str(alias.property("sequence")) == "Ctrl+4"

    qml_shown.root.setProperty("currentPage", 0)
    pump()
    try:
        alias.activated.emit()
        pump()
        assert qml_shown.root.property("currentPage") == 3
    finally:
        qml_shown.root.setProperty("currentPage", 0)
        pump()


def test_the_ctrl_4_alias_yields_if_the_user_rebinds_log(qml_shown, pump):
    """Two live Shortcuts on one sequence makes Qt drop both, so the alias yields.

    A user who remaps *Go to Log* onto `Ctrl+4` must keep a working shortcut —
    the hardcoded alias has to stand down, not collide.
    """
    bridge = qml_shown.bridge
    try:
        assert bridge.setShortcut("goto_log", "Ctrl+4") == ""
        pump()
        alias = by_name(qml_shown.root, "chrome.shortcut.goto_log_alt")
        assert str(alias.property("sequence")) == "", "the alias did not stand down"
    finally:
        bridge.resetShortcut("goto_log")
        pump()
    assert str(
        by_name(qml_shown.root, "chrome.shortcut.goto_log_alt").property("sequence")
    ) == "Ctrl+4", "the alias did not come back after the reset"


def test_ctrl_r_still_runs_a_translation():
    """Unchanged: `Ctrl+R` ran the job before the redesign too (it was never a
    navigation key — `Ctrl+1` already owned "go to Run")."""
    shell = qml("Main.qml")
    marker = 'sequence: "Ctrl+R"'
    assert marker in shell
    same_line = shell.split(marker)[1].split("\n")[0]
    assert "runTranslation" in same_line


def test_ctrl_enter_is_still_a_second_run_binding():
    """Kept because many keyboards have no distinct Return key."""
    shell = qml("Main.qml")
    assert 'sequence: "Ctrl+Enter"' in shell


# --------------------------------------------------------------------------- #
# 2. The output path still says it names itself after the title
# --------------------------------------------------------------------------- #

def test_output_path_still_says_it_is_named_automatically(qml_shown, pump):
    """The old placeholder was `Auto-named from the title`.

    The new field carries a placeholder plus a store-backed hint line, so the
    user still learns where the SRT lands without opening anything.
    """
    page = qml("pages/RunPage.qml")
    assert "appBridge.outPathHint" in page, "the out-path hint line was dropped"
    assert 'placeholderText: "Saved next to the video"' in page

    # The session bridge is shared: earlier suites leave their own source,
    # file and out-path behind, so pin a known state instead of asserting on
    # ambient leftovers (YouTube + auto path exercises the "named after the
    # title" wording this test is about).
    bridge = qml_shown.bridge
    bridge.setSourceEngine("youtube", "cloud")
    bridge._file_path = ""
    bridge.useAutoOutPath()
    pump()

    hint = bridge.outPathHint
    assert hint.strip(), "outPathHint is empty, so the hint line renders nothing"
    # The wording is mode-dependent ("the downloaded video" for YouTube, "the
    # video" for a local file), so only the promise is asserted.
    assert "next to the" in hint.lower()


# --------------------------------------------------------------------------- #
# 3. The content preset still explains what it changes
# --------------------------------------------------------------------------- #

def test_content_preset_still_explains_what_it_tunes(qml_shown, pump):
    """`PresetPicker.qml`'s ToolTip text, moved to a line under the chip row."""
    qml_shown.root.setProperty("currentPage", 0)
    pump()
    label = by_name(qml_shown.root, "run.presetHint")
    text = str(label.property("text"))
    assert text.strip(), "the preset hint renders nothing"
    for token in ("ASR", "prompt"):
        assert token.lower() in text.lower(), (
            f"the preset hint no longer mentions {token!r}: {text!r}"
        )
    assert label.property("visible")


def test_the_preset_chip_row_is_still_the_only_editor():
    """Parity both ways: the redundant "Auto · detect" dropdown must not return."""
    page = code("pages/RunPage.qml")
    assert "PresetPicker" not in page
    assert "appBridge.contentPreset = modelData" in page
