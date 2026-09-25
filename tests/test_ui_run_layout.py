"""Phase 3 gate — the Run screen's layout.

The review's §6.1/§6.2/§6.4/§6.5 findings, as tests. Two of these are layout
assertions measured against real offscreen geometry (see the `qml_shown`
fixture), because "the panel does not jump" is not something a static scan can
prove — the bug that shipped was a 40 px jump produced by a widget that looked
correct in the source.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"
RUN_PAGE = "pages/RunPage.qml"

RUN_PAGE_INDEX = 0

COMBINATIONS = (
    ("youtube", "cloud"),
    ("localfile", "cloud"),
    ("localfile", "local"),
    ("youtube", "local"),  # refused by design; must leave the state untouched
)


def qml(rel: str) -> str:
    return (QML_DIR / rel).read_text(encoding="utf-8")


def code(rel: str) -> str:
    return "\n".join(line.split("//")[0] for line in qml(rel).splitlines())


def _ids(widget: QObject) -> list[str]:
    """`disabledIds` is a JS array; PySide hands it over as a QJSValue."""
    value = widget.property("disabledIds")
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return [str(v) for v in (value or [])]


def _ids(widget: QObject) -> list[str]:
    """`disabledIds` is a JS array; PySide hands it over as a QJSValue."""
    value = widget.property("disabledIds")
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return [str(v) for v in (value or [])]


def by_name(root: QObject, name: str) -> QObject:
    for obj in root.findChildren(QObject):
        if obj.objectName() == name:
            return obj
    raise AssertionError(f"no QML object named {name!r}")


def _sweep(qml_shown, pump):
    """Every source × engine combination, with the geometry each one produces."""
    root = qml_shown.root
    root.setProperty("currentPage", RUN_PAGE_INDEX)
    pump()
    source = by_name(root, "run.sourceCard")
    processing = by_name(root, "run.processingCard")
    out = []
    for src, engine in COMBINATIONS:
        refused = qml_shown.bridge.setSourceEngine(src, engine)
        pump()
        out.append({
            "pair": (src, engine),
            "refused": refused,
            "sourceH": source.property("height"),
            "sourceY": source.property("y"),
            "processingY": processing.property("y"),
            "bodyH": by_name(root, "run.sourceBody").property("height"),
        })
    return out


# --------------------------------------------------------------------------- #
# §6.2 / §2.4 — the SOURCE panel must not change shape
# --------------------------------------------------------------------------- #

def test_source_panel_is_constant_height_in_every_combination(qml_shown, pump):
    """Toggling YouTube <-> local must swap CONTENT, not LAYOUT.

    Regression: the YouTube-only "VIDEO DOWNLOAD (OPTIONAL)" header sat *outside*
    the constant-height StackLayout, so it added 28 px plus 12 px of spacing in
    YouTube mode only and the whole left column jumped 40 px.
    """
    sweep = _sweep(qml_shown, pump)
    heights = {row["sourceH"] for row in sweep}
    assert len(heights) == 1, (
        "the SOURCE panel resizes between modes: "
        + ", ".join(f"{r['pair']}={r['sourceH']}" for r in sweep)
    )
    assert heights.pop() > 0, "the panel never got laid out — is the window shown?"


def test_source_body_is_constant_height_too(qml_shown, pump):
    """The StackLayout is the mechanism; if it resizes the panel will follow."""
    bodies = {row["bodyH"] for row in _sweep(qml_shown, pump)}
    assert len(bodies) == 1, f"the mode body resizes: {bodies}"


def test_column_headers_share_one_baseline(qml_shown, pump):
    """`Source` and `Processing` must start on the same line in every mode."""
    for row in _sweep(qml_shown, pump):
        assert row["sourceY"] == row["processingY"], (
            f"{row['pair']}: the columns start at different y "
            f"({row['sourceY']} vs {row['processingY']})"
        )


def test_the_optional_download_header_lives_inside_the_constant_body():
    """Static guard for the exact regression above — it is easy to move back."""
    source = code(RUN_PAGE)
    body = source.split('objectName: "run.sourceBody"')[1]
    assert "VIDEO DOWNLOAD (OPTIONAL)" in body, (
        "the optional-download header drifted back out of the StackLayout, "
        "which reintroduces the 40 px jump between source modes"
    )


def test_source_body_is_a_stack_layout():
    source = code(RUN_PAGE)
    assert "StackLayout {" in source
    assert "currentIndex: root.isYouTubeMode ? 0 : 1" in source


# --------------------------------------------------------------------------- #
# §6.1 — the matrix is honest
# --------------------------------------------------------------------------- #

def test_the_fourth_cell_is_disabled_with_a_stated_reason(qml_shown, pump):
    bridge = qml_shown.bridge
    root = qml_shown.root
    root.setProperty("currentPage", RUN_PAGE_INDEX)
    pump()
    engine = by_name(root, "bound.run.engine")

    # The local engine is selectable from a local file...
    assert bridge.setSourceEngine("localfile", "cloud") == ""
    pump()
    assert bridge.engineLocalDisabledReason == ""
    assert _ids(engine) == []

    # ...and not from a YouTube URL, where it says why.
    assert bridge.setSourceEngine("youtube", "cloud") == ""
    pump()
    reason = bridge.engineLocalDisabledReason
    assert reason != "", "YouTube + local model is selectable with no explanation"
    assert _ids(engine) == ["local"], (
        "the impossible engine option is still clickable"
    )

    # And the refusal is real, not cosmetic.
    problem = bridge.setSourceEngine("youtube", "local")
    assert problem != "", "YouTube + local model was accepted silently"


def test_the_disabled_reason_is_rendered_inline():
    """The reason is stated where the disabled option is, not only in the log."""
    source = code(RUN_PAGE)
    assert "appBridge.engineLocalDisabledReason" in source
    # It carries no `visible:` guard: a conditionally-present line inside the
    # constant-height body changes the StackLayout's high-water mark and makes
    # the SOURCE card jump between modes.
    label = source.split("appBridge.engineLocalDisabledReason")[1].split("}")[0]
    assert "visible:" not in label, (
        "the engine reason is conditionally visible again, which reintroduces "
        "the layout jump it was moved inside the body to avoid"
    )


# --------------------------------------------------------------------------- #
# §6.4 — readiness is a validator, not step 3
# --------------------------------------------------------------------------- #

def test_readiness_card_is_not_numbered():
    """`1 Source` and `2 Processing` are things the user does; readiness is not."""
    source = code(RUN_PAGE)
    readiness = source.split('objectName: "run.readinessCard"')[1].split("ReadinessChecklist")[0]
    assert "stepNumber" not in readiness, (
        "readiness is numbered as a step again (it is a passive validator)"
    )
    assert "stepNumber: 1" in source and "stepNumber: 2" in source, (
        "the two real steps lost their numbers"
    )


def test_readiness_badge_denominator_matches_the_actionable_rows(qml_shown, pump):
    bridge = qml_shown.bridge
    qml_shown.root.setProperty("currentPage", RUN_PAGE_INDEX)
    pump()
    badge = by_name(qml_shown.root, "run.readinessBadge")
    text = str(badge.property("text"))

    actionable = bridge.readinessActionableCount
    ready = bridge.readinessReadyCount
    na = bridge.readinessNotApplicableCount
    rows = bridge.readinessRows

    assert text.startswith(f"{ready} of {actionable} actionable"), text
    assert actionable == len([r for r in rows if r["actionable"]])
    if na:
        assert f"{na} n/a" in text
    assert sum(1 for r in rows if r["state"] == "na") == na


def test_readiness_na_and_unchecked_render_differently():
    """Five distinct treatments, and no ad-hoc bolding (§2.1)."""
    checklist = code("components/ReadinessChecklist.qml")
    assert "StatusMark" in checklist, "the checklist stopped using the vocabulary"
    assert "font.bold: row.isOk" not in checklist, "ad-hoc bolding came back"
    for state in ("na", "unchecked"):
        assert state in checklist, f"the {state!r} state is not handled"


# --------------------------------------------------------------------------- #
# §6.5 — de-duplicated pickers, no floating element
# --------------------------------------------------------------------------- #

def test_content_preset_is_chips_only():
    source = code(RUN_PAGE)
    assert "PresetPicker" not in source
    assert "contentPreset" in source


def test_glossary_is_one_control():
    """It used to be a field plus a separate `Choose` button."""
    source = code(RUN_PAGE)
    assert source.count("appBridge.chooseGlossary") <= 1, (
        "the glossary has two entry points again"
    )


def test_language_control_is_present_in_every_mode():
    """It used to live only inside the local-file block (§6.3)."""
    source = code(RUN_PAGE)
    # It must be a sibling of the StackLayout, not inside one of its branches:
    # anything after the StackLayout opening only renders in one mode.
    before_body = source.split('objectName: "run.sourceBody"')[0]
    assert 'objectName: "bound.run.language"' in before_body, (
        "the language control moved inside a mode branch, so it disappears "
        "when the other mode is active"
    )


def test_open_settings_is_a_link_not_a_floating_button():
    source = code(RUN_PAGE)
    assert 'variant: "link"' in source
    assert 'text: "Open Settings"' in source


def test_open_settings_sits_beside_the_footer_copy_not_over_it():
    """It used to be an overlay anchored across the footer text."""
    source = code(RUN_PAGE)
    footer = source.split("ASR segmentation, cloud credentials")[1]
    link = footer.split('text: "Open Settings"')[0]
    assert "anchors.fill: parent" not in link, (
        "the Open Settings link is anchored over the footer copy again"
    )
    # The prose and the link are siblings in one RowLayout, so the link sits
    # *beside* the copy rather than on top of it.
    before_copy = source.split("ASR segmentation")[0].rsplit("RowLayout", 1)
    assert len(before_copy) == 2, "the footer copy is not inside a RowLayout"
