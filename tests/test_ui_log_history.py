"""Log screen: a run history whose rows can actually be opened (T-6.2, T-6.3).

The review's §9 complaint was that RUN HISTORY was decorative. Two distinct
failures hid behind that:

1. **Clicking a row selected it but loaded nothing.** Review and Quality read
   the CLI's single `cache/last_result.json`, which every run overwrites, so
   only the newest run could ever be described. A history entry for any older
   run was a row that highlighted and did nothing.
2. **The `empty` chip.** It sat first in the console's `headerExtra`, ahead of
   the level filters, so it read as a filter. It filtered nothing, and it
   duplicated both the console's empty prompt and its `0 of 0 lines` counter.

The behavioural half of this file drives a real `AppBridge` with its result
files redirected into `tmp_path`, so it exercises the archive/load path rather
than asserting that the source mentions it.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import bridge as bridge_mod
from backend.bridge import (
    PIPELINE_MODE_OFFLINE,
    PIPELINE_MODE_YOUTUBE_CLOUD,
    AppBridge,
)

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"

# Two cues, one of them empty — so a loaded result is distinguishable from an
# empty model by `rowCount()` alone.
RESULT = {
    "cues": [
        {"start_ms": 0, "end_ms": 2000, "source": "こんにちは",
         "text": "Hello.", "status": "ok", "tags": []},
        {"start_ms": 2000, "end_ms": 4000, "source": "さようなら",
         "text": "", "status": "ok", "tags": []},
    ],
    "quality": {
        "cue_count": 2,
        "error_count": 1,
        "warning_count": 0,
        "issues": [{"cue_index": 1, "issues": ["empty_text"]}],
    },
}


def log_qml() -> str:
    return (QML_DIR / "pages" / "LogPage.qml").read_text(encoding="utf-8")


@pytest.fixture()
def harness(tmp_path, monkeypatch):
    """An AppBridge whose result files live in `tmp_path` and never persist."""
    live = tmp_path / "last_result.json"
    archive = tmp_path / "run_results"
    archive.mkdir()
    monkeypatch.setattr(bridge_mod, "_result_json_path", lambda: str(live))
    monkeypatch.setattr(bridge_mod, "_run_result_dir", lambda: str(archive))

    bridge = AppBridge()
    # `_record_run` persists, and the developer's real QSettings is not a
    # scratch pad.
    monkeypatch.setattr(bridge, "_persist_fields", lambda: None, raising=False)
    bridge._run_history_json = "[]"
    return SimpleNamespace(bridge=bridge, live=live, archive=archive)


# --------------------------------------------------------------------------- #
# Archiving
# --------------------------------------------------------------------------- #

def test_a_successful_run_archives_its_result(harness):
    harness.live.write_text(json.dumps(RESULT), encoding="utf-8")
    harness.bridge._record_run(0)

    entry = harness.bridge.runHistory[0]
    assert entry["resultJson"], "a successful run must keep its result"
    assert (harness.archive / entry["resultJson"]).is_file()


def test_a_failed_run_archives_nothing(harness):
    """There is no result to keep, and the row must say so rather than lie."""
    harness.bridge._record_run(1)
    assert harness.bridge.runHistory[0]["resultJson"] == ""


def test_archives_are_named_per_run_not_per_path(harness):
    """Two runs must not share a file, or the older entry becomes unreadable."""
    harness.live.write_text(json.dumps(RESULT), encoding="utf-8")
    harness.bridge._record_run(0)
    first = harness.bridge.runHistory[0]["resultJson"]
    harness.bridge._record_run(0)
    second = harness.bridge.runHistory[0]["resultJson"]
    assert first != second
    assert (harness.archive / first).is_file(), (
        "the older run's archive was overwritten by the newer run"
    )


def test_clearing_the_history_removes_the_archives(harness):
    harness.live.write_text(json.dumps(RESULT), encoding="utf-8")
    harness.bridge._record_run(0)
    assert list(harness.archive.glob("*.json"))

    harness.bridge.clearRunHistory()
    assert list(harness.archive.glob("*.json")) == [], (
        "clearing the history left its result files behind on disk"
    )


def test_entries_beyond_the_cap_lose_their_archives(harness):
    """The history keeps 20 entries; the 21st must not leak a 21st file."""
    harness.live.write_text(json.dumps(RESULT), encoding="utf-8")
    for _ in range(22):
        harness.bridge._record_run(0)
    assert len(harness.bridge.runHistory) == 20
    assert len(list(harness.archive.glob("*.json"))) == 20


# --------------------------------------------------------------------------- #
# Opening a run
# --------------------------------------------------------------------------- #

def test_selecting_a_run_loads_it_into_review(harness):
    """The archive is the only way an older run can be read, so use it."""
    harness.live.write_text(json.dumps(RESULT), encoding="utf-8")
    harness.bridge._record_run(0)
    # Simulate the next run overwriting the CLI's single output file.
    harness.live.unlink()

    harness.bridge.selectRun(0)

    assert harness.bridge.resultReady is True
    assert harness.bridge.cue_model.rowCount() == 2


def test_selecting_a_failed_run_clears_the_previous_result_and_says_why(harness):
    harness.live.write_text(json.dumps(RESULT), encoding="utf-8")
    harness.bridge._record_run(0)
    harness.bridge.selectRun(0)
    assert harness.bridge.resultReady is True

    harness.bridge._record_run(1)
    harness.bridge.selectRun(0)

    assert harness.bridge.resultReady is False, (
        "a failed run's entry must not keep showing the previous run's result"
    )
    assert harness.bridge.cue_model.rowCount() == 0
    assert "failed" in harness.bridge.statusMessage.lower()


def test_an_entry_whose_archive_is_gone_says_so(harness):
    harness.live.write_text(json.dumps(RESULT), encoding="utf-8")
    harness.bridge._record_run(0)
    entry = harness.bridge.runHistory[0]
    (harness.archive / entry["resultJson"]).unlink()
    harness.live.unlink()

    harness.bridge.selectRun(0)

    assert harness.bridge.resultReady is False
    assert "no longer stored" in harness.bridge.statusMessage.lower()


def test_openability_matches_what_select_run_does(harness):
    """`selectedRunOpenable` drives the Log card's warning row, so it must not
    promise a load that `selectRun` will refuse."""
    harness.live.write_text(json.dumps(RESULT), encoding="utf-8")
    harness.bridge._record_run(0)
    harness.bridge.selectRun(0)
    assert harness.bridge.selectedRunOpenable is True
    assert harness.bridge.selectedRunProblem == ""

    harness.live.unlink()
    (harness.archive / harness.bridge.runHistory[0]["resultJson"]).unlink()
    assert harness.bridge.selectedRunOpenable is False
    assert "no longer stored" in harness.bridge.selectedRunProblem.lower()


def test_no_selection_is_not_an_error(harness):
    harness.bridge.selectRun(-1)
    assert harness.bridge.selectedRunIndex == -1
    assert harness.bridge.selectedRunOpenable is False
    assert harness.bridge.selectedRunProblem == ""


# --------------------------------------------------------------------------- #
# What each entry states
# --------------------------------------------------------------------------- #

def test_entries_carry_the_source_and_engine_in_words(harness):
    """`YT`/`LC`/`OFF` is a legend; §2.2 forbids abbreviations a reader cannot
    resolve without being taught."""
    harness.bridge._url = "https://www.youtube.com/watch?v=abc"
    harness.bridge._file_path = ""
    harness.bridge._pipeline_mode = PIPELINE_MODE_YOUTUBE_CLOUD
    harness.bridge._record_run(0)
    entry = harness.bridge.runHistory[0]
    assert entry["sourceLabel"] == "YouTube URL"
    assert entry["engineLabel"] == "Cloud LLM"

    harness.bridge._url = ""
    harness.bridge._file_path = "C:/media/episode.mp4"
    harness.bridge._pipeline_mode = PIPELINE_MODE_OFFLINE
    harness.bridge._record_run(0)
    entry = harness.bridge.runHistory[0]
    assert entry["sourceLabel"] == "Local media file"
    assert entry["engineLabel"] == "Local model"


def test_the_selected_run_card_states_timestamp_source_engine_and_outcome(harness):
    harness.bridge._url = "https://www.youtube.com/watch?v=abc"
    harness.bridge._file_path = ""
    harness.bridge._pipeline_mode = PIPELINE_MODE_YOUTUBE_CLOUD
    harness.bridge._record_run(0)

    keys = [row["k"] for row in harness.bridge.selectedRunRows]
    for required in ("Source", "Engine", "Started", "Duration", "Exit code"):
        assert required in keys, f"the Selected run card omits {required!r}"


# --------------------------------------------------------------------------- #
# The QML half
# --------------------------------------------------------------------------- #

def test_clicking_a_row_opens_it():
    source = log_qml()
    assert "appBridge.selectRun(" in source, (
        "the history row only selects; Review and Quality never follow it"
    )
    assert "appBridge.selectedRunIndex = runItem.index" not in source, (
        "assigning the index directly loads nothing — call selectRun instead"
    )


def test_the_row_renders_timestamp_source_engine_and_outcome():
    source = log_qml()
    for field in ("started", "sourceLabel", "engineLabel", "resultText"):
        assert f"modelData.{field}" in source, (
            f"the history row does not render {field!r}"
        )


def test_the_empty_chip_is_gone():
    """§9 #36: `empty` read as a filter, filtered nothing, and duplicated the
    console's own empty prompt. Removed, not relabelled."""
    source = log_qml()
    assert 'text: "empty"' not in source
    assert "session log" not in source


def test_the_console_keeps_its_level_filters_with_counts():
    source = log_qml()
    for level in ("All", "Info", "Warn", "Error"):
        assert f'text: "{level}"' in source, f"the {level} filter chip was lost"
    assert "consoleView.counts" in source, "the filter chips lost their counts"


def test_no_filter_chip_targets_blank_lines():
    """The chip the review complained about must not have been relabelled into
    a real filter that hides lines — `blank lines` is not a useful filter."""
    console = (QML_DIR / "components" / "ConsoleView.qml").read_text(encoding="utf-8")
    assert '"blank lines"' not in log_qml() + console
    assert 'toneFilter === ""' in log_qml(), "the All chip no longer clears the filter"


def test_rerunning_is_offered_only_for_the_newest_run():
    """Only the newest run's settings snapshot is kept, so offering "re-run"
    beside an older entry would re-run the wrong thing."""
    source = log_qml()
    assert "appBridge.selectedRunIndex === 0" in source
