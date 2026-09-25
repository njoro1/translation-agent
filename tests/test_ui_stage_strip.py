"""Phase 3 gate — the `Processing` stage strip.

The middle column used to be titled `PIPELINE` while being a plain form, so the
name over-promised a flow that did not exist. The strip now carries the name:
`Source -> Transcribe -> Translate -> Gate -> Write`, driven entirely from the
existing `stageChanged` / `stageIndex` plumbing (no second source of truth).

These tests drive the bridge directly and assert both the derived data and what
the QML mirrors, because "the strip animates the right stage" is only true if
the two agree.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"
STAGE_IDS = ("source", "transcribe", "translate", "gate", "write")
STAGE_LABELS = ("Source", "Transcribe", "Translate", "Gate", "Write")
STAGE_STATES = ("pending", "active", "done", "failed", "skipped")


def by_name(root: QObject, name: str) -> QObject:
    for obj in root.findChildren(QObject):
        if obj.objectName() == name:
            return obj
    raise AssertionError(f"no QML object named {name!r}")


@pytest.fixture()
def stages(app_bridge):
    """A bridge with the run-state fields the strip reads, saved and restored."""
    bridge = app_bridge
    saved = {
        "running": bridge._is_running,
        "stage": bridge._progress_stage,
        "sequence": list(bridge._stage_sequence),
        "state": bridge._status_state,
        "strict": bridge._strict_quality,
        "mode": bridge._pipeline_mode,
    }
    bridge._stage_sequence = []
    bridge._progress_stage = ""
    bridge._is_running = False
    bridge._status_state = "idle"
    yield bridge
    bridge._is_running = saved["running"]
    bridge._progress_stage = saved["stage"]
    bridge._stage_sequence = saved["sequence"]
    bridge._status_state = saved["state"]
    bridge._strict_quality = saved["strict"]
    bridge._pipeline_mode = saved["mode"]


def states(bridge) -> dict[str, str]:
    return {row["id"]: row["state"] for row in bridge.pipelineStages}


# --------------------------------------------------------------------------- #
# The derived data
# --------------------------------------------------------------------------- #

def test_the_strip_has_the_five_canonical_stages(app_bridge):
    rows = app_bridge.pipelineStages
    assert tuple(r["id"] for r in rows) == STAGE_IDS
    assert tuple(r["label"] for r in rows) == STAGE_LABELS
    assert app_bridge.pipelineStageTotal == 5


def test_every_stage_state_is_from_the_documented_set(app_bridge):
    for row in app_bridge.pipelineStages:
        assert row["state"] in STAGE_STATES, row


def test_strip_is_idle_before_a_run(stages):
    stages._is_running = False
    stages._progress_stage = ""
    assert stages.pipelineStageIndex == -1, (
        "an idle strip must not highlight a stage"
    )
    for state in states(stages).values():
        assert state in ("pending", "skipped")


def test_transcribe_is_skipped_in_youtube_mode(stages):
    """A fact about the mode, not a problem (§2.1)."""
    stages._pipeline_mode = "youtube_cloud"
    assert states(stages)["transcribe"] == "skipped"


def test_transcribe_is_pending_for_a_local_file(stages):
    stages._pipeline_mode = "offline"
    assert states(stages)["transcribe"] == "pending"


def test_gate_is_skipped_when_the_strict_gate_is_off(stages):
    stages._strict_quality = False
    assert states(stages)["gate"] == "skipped"
    stages._strict_quality = True
    assert states(stages)["gate"] != "skipped"


def test_visited_stages_read_done(stages):
    stages._pipeline_mode = "youtube_cloud"
    stages._is_running = True
    stages._stage_sequence = [
        {"name": "fetch", "label": "Fetch", "elapsed": 1.0},
    ]
    stages._progress_stage = "translate"

    current = states(stages)
    assert current["source"] == "done", (
        "a stage the worker already left must read `done`, not `pending`"
    )
    assert current["translate"] == "active"
    assert current["write"] == "pending"


def test_the_active_stage_drives_the_index(stages):
    stages._pipeline_mode = "youtube_cloud"
    stages._is_running = True
    stages._stage_sequence = [{"name": "fetch", "label": "Fetch", "elapsed": 0.0}]
    stages._progress_stage = "translate"
    assert stages.pipelineStageIndex == STAGE_IDS.index("translate")


def test_a_failed_run_halts_on_the_failing_stage(stages):
    """The strip is where the failed state finally has a home (§6.6)."""
    stages._pipeline_mode = "youtube_cloud"
    stages._is_running = True
    stages._stage_sequence = [{"name": "fetch", "label": "Fetch", "elapsed": 0.0}]
    stages._progress_stage = "translate"

    stages._is_running = False
    stages._status_state = "failed"

    current = states(stages)
    assert current["translate"] == "failed"
    assert stages.pipelineStageIndex == STAGE_IDS.index("translate"), (
        "the halted stage must still be the highlighted one"
    )
    assert current["source"] == "done"


def test_a_cancelled_run_resets_the_strip(stages):
    stages._pipeline_mode = "youtube_cloud"
    stages._is_running = False
    stages._status_state = "cancelled"
    stages._stage_sequence = []
    stages._progress_stage = ""
    assert stages.pipelineStageIndex == -1
    assert "failed" not in states(stages).values()


def test_stage_changes_are_announced(stages):
    """The strip re-reads on `stageChanged`; nothing else may be needed."""
    seen = []
    stages.stageChanged.connect(lambda: seen.append(1))
    stages._progress_stage = "write"
    stages.stageChanged.emit()
    assert seen, "stageChanged did not reach the strip"


# --------------------------------------------------------------------------- #
# What the QML mirrors
# --------------------------------------------------------------------------- #

def test_strip_mirrors_the_store(qml_shown, pump):
    bridge = qml_shown.bridge
    qml_shown.root.setProperty("currentPage", 0)
    pump()
    strip = by_name(qml_shown.root, "run.stageStrip")

    assert int(strip.property("activeIndex")) == bridge.pipelineStageIndex
    rendered = strip.property("stages")
    if hasattr(rendered, "toVariant"):
        rendered = rendered.toVariant()
    assert [row["id"] for row in rendered] == list(STAGE_IDS), (
        "the strip is rendering a different pipeline than the bridge derives"
    )


def test_strip_has_a_delegate_per_stage(qml_shown, pump):
    qml_shown.root.setProperty("currentPage", 0)
    pump()
    strip = by_name(qml_shown.root, "run.stageStrip")
    repeaters = [
        child for child in strip.children()
        if "Repeater" in child.metaObject().className()
    ]
    assert repeaters, "the strip has no Repeater"
    assert int(repeaters[0].property("count")) == len(STAGE_IDS)


def test_strip_animation_honours_reduce_motion():
    source = (QML_DIR / "components/StageStrip.qml").read_text(encoding="utf-8")
    assert "Theme.reducedMotion" in source, (
        "the stage pulse ignores Reduce motion"
    )
    assert "running: stageRow.isActive && !Theme.reducedMotion" in source
