"""Appendix A validation probes (T-5.14 / T-6.4), as executable evidence.

The review's Appendix A asked for three populated-state probes. Each is
reproduced here against synthetic data with known properties, so the claims in
`docs/UI_VALIDATION.md` can be re-derived rather than trusted.

The synthetic result is deliberately *not* a recorded one: a recorded result
only exercises the shapes it happens to contain, and the whole point of these
probes is to force the awkward shapes (a failed row, a two-line translation, a
heavily skewed duration distribution) that a clean sample never has.
"""
from __future__ import annotations

import pytest

from backend.bridge import AppBridge
from backend.models.results import QualityIssuesModel
from src import subtitle_quality
from src.srt_io import Cue


# --- Synthetic fixtures -----------------------------------------------------

def _probe1_cues() -> list[dict]:
    """60 cues: 1 untranslated (a `failed` row), 1 two-line, 1 leaked ASR tag.

    Every cue is 3.0 s long and none exceeds 80 characters, so the only issues
    in the report are the ones the probe deliberately plants. That matters:
    with the shorter duration this file first used, every cue also tripped the
    CPS *error* threshold, which drowned out the shapes the probe exists to
    exercise.

    The two-line cue is written in the form the pipeline actually stores — a
    literal ``\\N``, per ``src/postprocess.py::break_lines`` — not a real
    newline. Using the friendly form here would have hidden the finding in
    `test_the_line_count_check_cannot_see_the_stored_separator`.
    """
    cues: list[dict] = []
    for i in range(60):
        text = f"Translation of line {i + 1}."
        if i == 7:
            text = ""                                   # untranslated -> failed
        elif i == 19:
            text = "First line of a two-line cue\\NSecond line of it."
        elif i == 33:
            # The real leak format. `[MUSIC]` is not something the quality
            # checks look for — `_ASR_TAG_RE` matches `<|BGM|>`-style control
            # tokens, `_EMOTION_TAG_RE` matches `<ANGRY>`-style tags, and
            # `_FANSUB_MARKUP_RE` matches `[CHENGYU:...]`/`[TRANSLATOR...]`.
            text = "<|BGM|> Translation with a leaked ASR tag."
        cues.append({
            "start_ms": i * 3200,
            "end_ms": i * 3200 + 3000,
            "source": f"Source line {i + 1}",
            "text": text,
            "status": "ok",
            "tags": [],
        })
    return cues


def _probe2_cues() -> list[dict]:
    """Mixed severities plus a heavily skewed duration distribution.

    50 cues: 45 short (0.6 s) and 5 long (9.0 s). The long tail is what a log
    axis would be for, so the probe measures whether it is actually needed.
    """
    cues: list[dict] = []
    for i in range(50):
        duration = 9000 if i >= 45 else 600
        text = "Short and clean."
        if i == 3:
            text = "[MUSIC] leaked tag"                  # error
        elif i == 4:
            text = ""                                    # untranslated -> error
        elif i == 5:
            text = "This line is deliberately far too long to be readable at any "
            text += "sane reading speed, which should raise a warning."
        cues.append({
            "start_ms": i * 10000,
            "end_ms": i * 10000 + duration,
            "source": f"Source {i}",
            "text": text,
            "status": "ok",
            "tags": [],
        })
    return cues


def _load(bridge: AppBridge, cues: list[dict]) -> dict:
    """Put `cues` through the same path a finished run takes."""
    bridge.cue_model.load(cues)
    srt_cues = [
        Cue(start=c["start_ms"] / 1000.0, end=c["end_ms"] / 1000.0, text=c["text"])
        for c in cues
    ]
    untranslated = sum(1 for c in srt_cues if not (c.text or "").strip())
    report = subtitle_quality.build_report(srt_cues, untranslated_count=untranslated)
    summary = dict(report.to_dict())
    summary["max_line_chars"] = max(
        (len(line.strip())
         for c in srt_cues
         for line in (c.text or "").replace("\\N", "\n").splitlines()),
        default=0,
    )
    bridge._quality_summary = summary
    bridge._result_ready = True
    bridge._dist_cache = None
    bridge.quality_issues_model.load_from_report(summary)
    bridge._sync_cue_tags(summary)
    return summary


# --- Probe 1: Review with 60 cues, a failed row and a multi-line cue --------

class TestProbe1ReviewPopulated:
    def _bridge(self, app_bridge):
        _load(app_bridge, _probe1_cues())
        return app_bridge

    def test_fifty_plus_cues_reach_the_table(self, app_bridge):
        bridge = self._bridge(app_bridge)
        assert bridge.cue_model.count == 60
        assert bridge.cueProxy.rowCount() == 60
        assert bridge.cueCounts["total"] == 60

    def test_the_untranslated_cue_is_a_failed_row(self, app_bridge):
        bridge = self._bridge(app_bridge)
        counts = bridge.cueCounts
        assert counts["failed"] == 1, counts
        proxy = bridge.cueProxy
        proxy.filterMode = "failed"
        assert proxy.rowCount() == 1
        assert proxy.get(0)["index"] == 8, "the blank cue is #8"
        proxy.filterMode = "all"

    def test_a_multi_line_cue_keeps_its_separator(self, app_bridge):
        """The store keeps the ASS form; the read view is what expands it.

        A `TextInput` is single-line by construction, which is why translations
        clipped before the T-5.1 fix. The other half of the same fix is that the
        row must *render* the separator rather than print it.
        """
        bridge = self._bridge(app_bridge)
        cue = bridge.cue_model.get_cue(19)
        assert "\\N" in cue["text"], cue["text"]
        assert "Second line" in cue["text"]

    def test_the_read_view_expands_the_ass_line_separator(self):
        table = _qml("components/CuePreviewTable.qml")
        assert "function displayText(raw)" in table
        assert 'replace(/\\\\N/g, "\\n")' in table
        assert "text: root.displayText(model.translationText)" in table
        assert "ToolTip.text: root.displayText(model.translationText)" in table
        # The editable field keeps the raw text, so an edit round-trips
        # byte-for-byte and does not mark an untouched row as edited.
        assert "text: model.translationText" in table

    def test_the_line_count_check_cannot_see_the_stored_separator(self, app_bridge):
        """Finding: `lines_warning` / `lines_error` are inert in production.

        `subtitle_quality._line_count` splits on real newlines, but the pipeline
        stores a literal ``\\N`` (`postprocess.break_lines`), so every wrapped
        cue reports one line. Deliberately *not* fixed here: `LINES_WARNING` is
        2 and the check is `>=`, so teaching it to see the separator would flag
        the formatter's own two-line output as a warning on every cue. The two
        are coupled and the threshold is a product decision — recorded in
        `docs/UI_VALIDATION.md`.
        """
        bridge = self._bridge(app_bridge)
        assert bridge.cue_model.get_cue(19)["tags"] == []
        assert bridge.quality_issues_model.counts["warnings"] == 0

    def test_the_leaked_tag_is_flagged_and_counted(self, app_bridge):
        bridge = self._bridge(app_bridge)
        tags = bridge.cue_model.get_cue(33)["tags"]
        assert any("leakage" in t for t in tags), tags
        assert bridge.cueCounts["warnings"] >= 1

    def test_search_spans_source_and_translation(self, app_bridge):
        bridge = self._bridge(app_bridge)
        proxy = bridge.cueProxy
        proxy.searchText = "Source line 12"          # source only
        assert proxy.rowCount() == 1
        proxy.searchText = "Translation of line 12"  # translation only
        assert proxy.rowCount() == 1
        proxy.searchText = ""

    def test_timeline_drag_filters_to_a_cue_range(self, app_bridge):
        """Probe 1 asks whether a range selection is usable at 60 cues."""
        bridge = self._bridge(app_bridge)
        proxy = bridge.cueProxy
        proxy.setCueRange(10, 14)
        assert proxy.rowCount() == 5
        assert proxy.cueRangeLabel == "cues 10\u201314"
        assert proxy.get(0)["index"] == 10
        proxy.clearCueRange()
        assert proxy.rowCount() == 60

    def test_live_edit_moves_the_quality_counts(self, app_bridge):
        """Fixing the blank cue must stop it being counted as a problem."""
        bridge = self._bridge(app_bridge)
        assert bridge.cueCounts["failed"] == 1
        bridge.setCueText(7, "Now translated.")
        assert bridge.cueCounts["failed"] == 0
        assert bridge.cue_model.get_cue(7)["tags"] == []


# --- Probe 2: Quality with mixed severities and a skewed distribution -------

class TestProbe2QualityPopulated:
    def _bridge(self, app_bridge):
        _load(app_bridge, _probe2_cues())
        return app_bridge

    def test_filter_chip_counts_are_live_and_disjoint(self, app_bridge):
        bridge = self._bridge(app_bridge)
        counts = bridge.quality_issues_model.counts
        assert counts["all"] == counts["errors"] + counts["warnings"]
        assert counts["all"] > 0

    def test_counts_do_not_shrink_when_a_filter_is_active(self, app_bridge):
        """Selecting "Errors" must not make the Warnings count read 0."""
        bridge = self._bridge(app_bridge)
        model = bridge.quality_issues_model
        before = dict(model.counts)
        model.filterMode = "errors"
        assert model.counts == before
        model.filterMode = "all"

    def test_severity_sort_toggles_and_keeps_every_row(self, app_bridge):
        bridge = self._bridge(app_bridge)
        model = bridge.quality_issues_model
        assert model.severitySort is True
        model.set_severity_sort(False)
        cues_in_order = [
            model.data(model.index(i, 0), QualityIssuesModel.CueRole)
            for i in range(model.rowCount())
        ]
        assert cues_in_order == sorted(cues_in_order)
        model.set_severity_sort(True)
        severities = [
            model.data(model.index(i, 0), QualityIssuesModel.SeverityRole)
            for i in range(model.rowCount())
        ]
        assert severities == sorted(severities, key=lambda s: {"error": 0, "warning": 1}[s])

    def test_metric_breakdown_matches_the_table(self, app_bridge):
        """The chip's click-through must equal the rows it is summarising."""
        bridge = self._bridge(app_bridge)
        model = bridge.quality_issues_model
        for severity, tile_label in (("error", "Errors"), ("warning", "Warnings")):
            rows = [
                model.data(model.index(i, 0), QualityIssuesModel.SeverityRole)
                for i in range(model.rowCount())
            ].count(severity)
            tile = next(t for t in bridge.qualityTiles if t["label"] == tile_label)
            assert int(tile["value"]) == rows
            assert sum(entry["v"] for entry in tile["breakdown"]) == rows

    def test_the_quality_tile_and_the_cue_count_use_different_units(self, app_bridge):
        """`qualityErrors` counts cues; the Quality tile counts issue rows.

        Both numbers are correct for their own screen: the Review page's chips
        and the icon-rail badge ask "how many cues are affected", while the
        Quality tile sits on top of an issue table and clicks through to it.
        Conflating the two is exactly how the tile and the filter chip over the
        same table came to disagree. This test is the tripwire against
        "unifying" them back into one number.
        """
        bridge = self._bridge(app_bridge)
        assert bridge.qualityErrors == 50, "50 cues carry at least one error"
        assert bridge.quality_issues_model.counts["errors"] == 51, (
            "one of those cues carries two errors (empty_text + cps_error)"
        )
        tile = next(t for t in bridge.qualityTiles if t["label"] == "Errors")
        assert int(tile["value"]) == 51

    def test_the_long_tail_is_visible_without_a_log_axis(self, app_bridge):
        """Decides the 'log axis?' question in T-5.10 from data.

        5 of 50 cues sit in the top duration bucket. That is a visible spike on
        a linear axis — a log axis would compress the 45-cue mass into one bar
        to make a 5-cue tail legible, which is the wrong trade here.
        """
        bridge = self._bridge(app_bridge)
        bars = bridge.qualityDurationHistogram["bars"]
        assert len(bars) == 9
        non_empty = [i for i, b in enumerate(bars) if b["v"] > 0]
        assert len(non_empty) >= 2, "a single occupied bucket would justify a log axis"
        assert max(bars, key=lambda b: b["v"]) is bars[0], "the mass is in the low buckets"

    def test_histogram_bars_are_toned_from_the_real_thresholds(self, app_bridge):
        bridge = self._bridge(app_bridge)
        bars = bridge.qualityCpsHistogram["bars"]
        limits = bridge.qualityLimits
        labels = [int(str(v).rstrip("+")) for v in bridge.qualityCpsHistogram["labels"]]
        for label, bar in zip(labels, bars):
            if label > limits["cpsError"]:
                assert bar["tone"] == "err", (label, bar)
            elif label > limits["cpsWarn"]:
                assert bar["tone"] == "warn", (label, bar)
            else:
                assert bar["tone"] == "", (label, bar)

    def test_the_overflow_bucket_says_so(self, app_bridge):
        """The last bucket absorbs everything above its centre.

        Without the open-ended marker the duration axis read "6.8" directly
        under a 9.0 s cue, which is worse than no label: it is a wrong one.
        """
        bridge = self._bridge(app_bridge)
        assert bridge.qualityDurationHistogram["labels"][-1].endswith("+")
        assert bridge.qualityCpsHistogram["labels"][-1].endswith("+")
        # The 9.0 s cues are clamped into the final bucket, so the summary —
        # not the axis — is what states the real maximum.
        assert "max 9.0 s" in bridge.qualityDurationHistogram["summary"]
        assert bridge.qualityDurationHistogram["bars"][-1]["v"] > 0

    def test_run_context_is_filled_from_the_run(self, app_bridge):
        bridge = self._bridge(app_bridge)
        keys = {row["k"] for row in bridge.runContext}
        assert "Status" not in keys, "runContext still reports 'No run loaded'"
        assert {"Mode", "Model", "Preset", "Wall clock"}.issubset(keys)


# --- Probe 6: YouTube Inspect with and without an English track -------------

def _qml(rel: str) -> str:
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "ui" / "qml"
    return (root / rel).read_text(encoding="utf-8")


class TestProbe6YouTubeTracks:
    """The Inspect panel's English-track flag, with and without a track.

    `youtubeHasEnglishSubtitle` is the single store; `YouTubeSubtitlePanel` and
    the RunPage readiness rows are mirrors. With no English track the app must
    *say so* and point at the fallback, not leave a dead download button.
    """

    def test_nothing_inspected_yet_reports_no_track(self, app_bridge):
        """The honest state before an inspect is "not found", not "ok"."""
        assert app_bridge.youtubeHasEnglishSubtitle is False

    def test_the_flag_gates_the_download_action(self):
        panel = _qml("components/YouTubeSubtitlePanel.qml")
        assert ("enabled: !appBridge.youtubeSubDownloading "
                "&& appBridge.youtubeHasEnglishSubtitle") in panel

    def test_the_run_page_has_both_branches(self):
        page = _qml("pages/RunPage.qml")
        assert "visible: !appBridge.youtubeHasEnglishSubtitle" in page, (
            "there is no explanation for the no-English-track case"
        )
        assert "visible: appBridge.youtubeHasEnglishSubtitle" in page, (
            "there is no download path for the English-track case"
        )

    def test_the_readiness_row_follows_the_flag(self):
        page = _qml("pages/RunPage.qml")
        assert 'status: appBridge.youtubeHasEnglishSubtitle ? "ok" : "todo"' in page


# --- Probe 5 (T-6.4): appearance toggles reach the theme --------------------

class TestProbe5Appearance:
    """Every appearance axis has a path from the store into `Theme`.

    The colour maths is in `test_theme_contrast.py`; the density and motion
    wiring is in `test_ui_hygiene.py`. What is checked here is that no axis is
    left unbound, which is how "Reduce motion" came to be a switch that changed
    nothing.
    """

    def test_main_pushes_every_appearance_axis_into_theme(self):
        main = _qml("Main.qml")
        for prop in ("themeName", "comfortable", "reducedMotion", "accentName"):
            assert f'property: "{prop}"' in main, (
                f"`{prop}` is not bound into Theme, so the corresponding setting "
                f"is a switch that changes nothing"
            )

    def test_the_accent_table_is_the_only_accent_source(self):
        theme = _qml("Theme.qml")
        table = theme.split("accentChoices", 1)[1].split("]", 1)[0]
        assert table.count("id:") == 5, "expected five accent presets"
