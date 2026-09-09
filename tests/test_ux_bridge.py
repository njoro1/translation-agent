"""Tests for the UX-facing behaviour added to AppBridge.

Failure classification, honest readiness rows, null-safe CPS text, the
Quality->Review jump, log error counting, theme toggle and subtitle save-back.
"""
from __future__ import annotations

import pytest

from backend.bridge import AppBridge, _classify_failure


def test_classify_auth():
    code, _title, _detail, remedy = _classify_failure(
        "Traceback (most recent call last):\nError: 401 Unauthorized: invalid api key"
    )
    assert code == "AUTH"
    assert remedy == "cloud"


def test_classify_quota():
    code, *_ = _classify_failure("RateLimitError: 429 You exceeded your current quota.")
    assert code == "QUOTA"


def test_classify_missing_dependency():
    code, *_ = _classify_failure(
        "FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'"
    )
    assert code == "MISSING_DEPENDENCY"


def test_classify_network():
    code, *_ = _classify_failure("urllib3 ConnectionError: connection refused")
    assert code == "NETWORK"


def test_classify_falls_back_to_generic_error():
    code, *_ = _classify_failure("something bad happened\n[error] unexpected explosion")
    assert code == "UNKNOWN"


def test_readiness_rows_shape(app_bridge):
    rows = app_bridge.readinessRows
    assert isinstance(rows, list) and rows
    for r in rows:
        assert {"id", "label", "state", "hint"}.issubset(r.keys())
        assert r["state"] in ("ok", "todo", "n/a")


def test_quality_cps_text_no_result(app_bridge):
    assert app_bridge.qualityAverageCpsText == "\u2014"


def test_quality_cps_text_with_value(app_bridge):
    app_bridge._result_ready = True
    app_bridge._quality_summary = {"average_cps": 4.25}
    assert app_bridge.qualityAverageCpsText == "4.2"


def test_reveal_cue_jumps_to_review(app_bridge):
    seen = []
    app_bridge.requestTab.connect(seen.append)
    app_bridge.revealCue(5)
    assert app_bridge.focusCueIndex == 4
    assert seen == [1]


def test_log_error_count_increments(app_bridge):
    before = app_bridge.logErrorCount
    app_bridge._append_log("INFO starting run\n[error] something failed\nnormal line")
    assert app_bridge.logErrorCount == before + 1


def test_theme_toggle_flips(app_bridge):
    start = app_bridge.themeName
    app_bridge.toggleTheme()
    assert app_bridge.themeName != start
    app_bridge.toggleTheme()
    assert app_bridge.themeName == start


def test_save_edited_subtitles_round_trips(tmp_path, app_bridge):
    cues = [
        {"index": 1, "start_ms": 1000, "end_ms": 2000, "source": "a",
         "text": "A", "status": "ok"},
        {"index": 2, "start_ms": 2000, "end_ms": 3000, "source": "b",
         "text": "B", "status": "ok"},
    ]
    app_bridge.cue_model.load(cues, {})
    app_bridge._result_ready = True
    # Edit the first cue through the model, then save it back as SRT.
    from backend.models.results import CueResultModel
    app_bridge.cue_model.setData(app_bridge.cue_model.index(0, 0), "A!", CueResultModel.TextRole)
    out = tmp_path / "out.srt"
    assert app_bridge.saveEditedSubtitles(str(out)) is True
    text = out.read_text(encoding="utf-8")
    assert "A!" in text
    assert "B" in text
