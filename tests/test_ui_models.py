"""Tests for the Review/Quality list models (backend/models/results.py).

Covers the editable cue model, the All/Failed/Warnings/Errors proxy, and the
quality-issue model's friendly/raw type roles introduced by the UX fixes.
"""
from __future__ import annotations

from backend.models.results import CueFilterProxyModel, CueResultModel, QualityIssuesModel


def _make_cues():
    return [
        {"index": 1, "start_ms": 1000, "end_ms": 2500, "source": "Hello",
         "text": "\u3053\u3093\u306b\u3061\u306f", "status": "ok"},
        {"index": 2, "start_ms": 2500, "end_ms": 4000, "source": "World",
         "text": "", "status": "empty"},
        {"index": 3, "start_ms": 4000, "end_ms": 5500, "source": "Bye",
         "text": "[untranslated]", "status": "untranslated"},
    ]


def test_cue_model_load_and_roles():
    m = CueResultModel()
    m.load(_make_cues(), {2: ["empty_text"]})
    assert m.rowCount() == 3
    assert m.data(m.index(0, 0), CueResultModel.IndexRole) == 1
    assert m.data(m.index(0, 0), CueResultModel.TextRole) == "\u3053\u3093\u306b\u3061\u306f"
    assert m.data(m.index(2, 0), CueResultModel.TagsRole) == ["empty_text"]


def test_cue_edit_and_revert():
    m = CueResultModel()
    m.load(_make_cues())
    assert m.edited_count() == 0
    idx = m.index(0, 0)
    assert m.setData(idx, "Konnichiwa", CueResultModel.TextRole) is True
    assert m.data(idx, CueResultModel.TextRole) == "Konnichiwa"
    assert m.data(idx, CueResultModel.EditedRole) is True
    assert m.edited_count() == 1
    m.revert_cue(0)
    assert m.data(idx, CueResultModel.TextRole) == "\u3053\u3093\u306b\u3061\u306f"
    assert m.data(idx, CueResultModel.EditedRole) is False


def test_proxy_errors_filter():
    m = CueResultModel()
    # 0-based positions: 0=ok(+cjk error tag), 1=empty, 2=untranslated.
    m.load(_make_cues(), {0: ["cjk_residue_error"]})
    proxy = CueFilterProxyModel()
    proxy.setSourceModel(m)

    proxy.filterMode = "errors"
    assert proxy.rowCount() == 3  # cjk error + empty + untranslated

    proxy.filterMode = "failed"
    assert proxy.rowCount() == 2  # empty + untranslated

    proxy.filterMode = "warnings"
    assert proxy.rowCount() == 0

    proxy.filterMode = "all"
    assert proxy.rowCount() == 3


def test_quality_issues_friendly_types():
    q = QualityIssuesModel()
    quality = {
        "issues": [
            {"cue_index": 0, "issues": ["untranslated_marker_error", "cjk_residue_error"]},
            {"cue_index": 2, "issues": ["cps_warning"]},
        ]
    }
    q.load_from_report(quality)
    assert q.rowCount() == 3

    r0 = q.index(0, 0)
    assert q.data(r0, QualityIssuesModel.RawTypeRole) == "untranslated_marker_error"
    assert q.data(r0, QualityIssuesModel.FriendlyTypeRole) == "Carries the [untranslated] marker"

    severities = [
        q.data(q.index(i, 0), QualityIssuesModel.SeverityRole)
        for i in range(q.rowCount())
    ]
    assert severities == ["error", "error", "warning"]
