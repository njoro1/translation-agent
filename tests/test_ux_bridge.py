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


# --- YouTube download recovery notice ---------------------------------------

def test_warn_line_becomes_video_notice(app_bridge):
    """A yt-dlp recovery step is promoted to a banner, not buried in the log."""
    app_bridge._on_youtube_video_progress_line(
        "[warn] Stale partial download removed — restarting…\n"
    )
    assert "Stale partial download removed" in app_bridge.youtubeVideoNotice


def test_ordinary_progress_lines_are_not_notices(app_bridge):
    app_bridge._on_youtube_video_progress_line("[download]   3.4% of 3.31GiB\n")
    app_bridge._on_youtube_video_progress_line("[info] Downloading 1 format(s): 401+251\n")
    assert app_bridge.youtubeVideoNotice == ""


def test_video_notice_clears_once_the_file_lands(app_bridge):
    """A lingering 'restarting…' banner would be stale after a success."""
    app_bridge._youtube_video_notice = "restarting…"
    app_bridge._youtube_video_gen = 5
    app_bridge._on_youtube_video_done("YTDONE:5|video:/tmp/clip.mp4")
    assert app_bridge.youtubeVideoNotice == ""


def test_stale_completion_does_not_clear_the_notice(app_bridge):
    app_bridge._youtube_video_notice = "restarting…"
    app_bridge._youtube_video_gen = 5
    app_bridge._on_youtube_video_done("YTDONE:4|video:/tmp/old.mp4")
    assert app_bridge.youtubeVideoNotice == "restarting…"


def test_video_panel_binds_the_notice_property():
    """Guard the UI coupling: dropping the binding would silently stop
    showing recovery messages while the backend still emits them."""
    from pathlib import Path

    panel = (
        Path(__file__).resolve().parent.parent
        / "ui" / "qml" / "components" / "YouTubeVideoPanel.qml"
    )
    assert "youtubeVideoNotice" in panel.read_text(encoding="utf-8")


# --- YouTube resolution / codec selection (the 720p/AV1 bug) -----------------


def test_youtube_resolution_setter_coerces_int_to_str(app_bridge):
    """The QML picker can hand a bare int (720); if the bridge stored the int,
    the combo's strict comparison against the stored string never matched and
    the pick was silently dropped. The setter must normalise to a string."""
    app_bridge.youtubeSelectedResolution = 720
    assert app_bridge.youtubeSelectedResolution == "720"
    app_bridge.youtubeSelectedResolution = "best"
    assert app_bridge.youtubeSelectedResolution == "best"


def test_youtube_selected_option_honors_av1_720(app_bridge):
    """Regression: codec AV1 + resolution 720p must resolve to a 720p AV1
    selector, never an unconstrained /best that downloads 4K."""
    from src.youtube_media import _build_matrix

    formats = [
        {"format_id": "398", "vcodec": "av01.0.08", "acodec": "none",
         "height": 720, "ext": "mp4", "tbr": 2500, "filesize": 120_000_000},
        {"format_id": "251", "vcodec": "none", "acodec": "opus",
         "height": None, "ext": "webm", "tbr": 160},
    ]
    codecs, resolutions, matrix, best = _build_matrix(formats)
    app_bridge._youtube_matrix = matrix
    app_bridge._youtube_best = best
    app_bridge._youtube_selected_codec = "av1"
    app_bridge._youtube_selected_resolution = "720"

    opt = app_bridge.youtubeSelectedOption
    assert opt["resolution"] == 720
    sel = opt["format_selector"]
    assert "av01" in sel or "398" in sel
    # Must stay capped at 720p — no 2160p, no unconstrained /best fallback.
    assert "2160" not in sel


def test_resolution_combo_uses_value_role():
    """Regression guard for the 720p selection bug: the combo looked the pick
    up with a hand-rolled strict comparison between an int model value (720)
    and a string selection ('720'), which never matched, so the picker snapped
    back to 'Best'. Selection must go through ``valueRole`` + ``indexOfValue``
    on string values.
    """
    from pathlib import Path

    panel = (
        Path(__file__).resolve().parent.parent
        / "ui" / "qml" / "components" / "YouTubeVideoPanel.qml"
    )
    text = panel.read_text(encoding="utf-8")
    assert 'valueRole: "value"' in text
    assert "indexOfValue(appBridge.youtubeSelectedResolution)" in text
    assert "items[i].value === sel" not in text


def test_youtube_resolution_values_are_strings(app_bridge):
    """The model hands its values straight back to the bridge, so they must be
    the same type the bridge stores (strings) — an int value is what made the
    pick impossible to match."""
    from src.youtube_media import _build_matrix

    formats = [
        {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none",
         "height": 1080, "ext": "mp4", "tbr": 4500, "filesize": 300_000_000},
        {"format_id": "136", "vcodec": "avc1.4d401f", "acodec": "none",
         "height": 720, "ext": "mp4", "tbr": 2500, "filesize": 150_000_000},
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2",
         "height": None, "ext": "m4a", "tbr": 130, "filesize": 5_000_000},
    ]
    _codecs, _res, matrix, best = _build_matrix(formats)
    app_bridge._youtube_matrix = matrix
    app_bridge._youtube_best = best
    app_bridge._youtube_selected_codec = "h264"

    values = [item["value"] for item in app_bridge.youtubeResolutions]
    assert values == ["1080", "720", "best"]
    assert all(isinstance(v, str) for v in values)


def test_youtube_resolution_setter_normalises_numbers(app_bridge):
    """QML numbers can arrive as ints or as JS doubles; both must land as the
    same string, otherwise the stored selection never matches the model."""
    for value in (720, 720.0, "720", " 720 "):
        app_bridge.youtubeSelectedResolution = value
        assert app_bridge.youtubeSelectedResolution == "720", value
    app_bridge.youtubeSelectedResolution = 0
    assert app_bridge.youtubeSelectedResolution == "best"


def test_no_bv_fallback_when_pair_is_unavailable(app_bridge):
    """Regression: an unavailable (codec, resolution) used to fall back to the
    unconstrained 'bv*+ba/b' selector — the download then grabbed the globally
    best stream while the UI showed the user's pick."""
    from src.youtube_media import _build_matrix

    formats = [
        {"format_id": "136", "vcodec": "avc1.4d401f", "acodec": "none",
         "height": 720, "ext": "mp4", "tbr": 2500, "filesize": 150_000_000},
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2",
         "height": None, "ext": "m4a", "tbr": 130, "filesize": 5_000_000},
    ]
    _codecs, _res, matrix, best = _build_matrix(formats)
    app_bridge._youtube_matrix = matrix
    app_bridge._youtube_best = best
    app_bridge._youtube_selected_codec = "h264"
    app_bridge._youtube_selected_resolution = "480"  # not served

    assert app_bridge.youtubeSelectedOption == {}
    assert app_bridge._selected_format_selector() == ""
    assert "480p" in app_bridge.youtubeSelectionError
    assert "720p" in app_bridge.youtubeSelectionError


def test_download_refuses_unavailable_pair_without_touching_yt_dlp(app_bridge):
    """Clicking Download on an unavailable pair must fail with a clear message
    rather than starting a download of 'whatever is best'."""
    from src.youtube_media import _build_matrix

    formats = [
        {"format_id": "136", "vcodec": "avc1.4d401f", "acodec": "none",
         "height": 720, "ext": "mp4", "tbr": 2500, "filesize": 150_000_000},
    ]
    _codecs, _res, matrix, best = _build_matrix(formats)
    app_bridge._youtube_matrix = matrix
    app_bridge._youtube_best = best
    app_bridge._url = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    app_bridge._youtube_selected_codec = "h264"
    app_bridge._youtube_selected_resolution = "2160"

    started = []
    app_bridge.threadpool = type("T", (), {"start": lambda self, w: started.append(w)})()

    app_bridge.downloadYouTubeVideo()

    assert started == [], "no download may be started for an unavailable pair"
    assert app_bridge._youtube_video_downloading is False
    assert "not available" in app_bridge.youtubeVideoStatus.lower()
    assert app_bridge.youtubeSelectionError in app_bridge.youtubeVideoStatus


class TestDownloadVerification:
    """The post-download sanity check must be right *and* quiet.

    A wrong warning is worse than none: it makes the app look broken after a
    perfectly good download.
    """
    @staticmethod
    def _worker(expect):
        from backend.bridge import _YouTubeDownloadWorker
        return _YouTubeDownloadWorker("video", "u", "sel", "t", 1, expect=expect)

    @staticmethod
    def _probe(codec, height, monkeypatch):
        from src import youtube_media
        monkeypatch.setattr(youtube_media, "probe_video_file",
                            lambda path: {"codec": codec, "height": height,
                                          "width": 0, "codec_name": codec})

    def test_no_expectation_is_silent(self, monkeypatch):
        self._probe("h264", 480, monkeypatch)
        assert self._worker(None)._verify("x.mp4") == ""

    def test_matching_file_is_silent(self, monkeypatch):
        self._probe("h264", 720, monkeypatch)
        assert self._worker({"codec": "h264", "height": 720,
                             "cap": False})._verify("x.mp4") == ""

    def test_height_mismatch_warns(self, monkeypatch):
        self._probe("h264", 2160, monkeypatch)
        warn = self._worker({"codec": "h264", "height": 720,
                             "cap": False})._verify("x.mp4")
        assert "2160p" in warn and "720p" in warn

    def test_codec_mismatch_warns(self, monkeypatch):
        self._probe("av1", 720, monkeypatch)
        warn = self._worker({"codec": "h264", "height": 720,
                             "cap": False})._verify("x.mp4")
        assert "AV1" in warn and "H.264" in warn

    def test_best_any_codec_does_not_warn_about_codec(self, monkeypatch):
        """Regression: the expectation for "Best (any)" literally stores the
        codec id "best". Comparing that to the real codec flagged *every*
        download as a codec mismatch."""
        self._probe("h264", 480, monkeypatch)
        # codec="best" + cap=True is what _selected_expectation() builds.
        assert self._worker({"codec": "best", "height": 720,
                             "cap": True})._verify("x.mp4") == ""

    def test_cap_accepts_a_smaller_height(self, monkeypatch):
        self._probe("h264", 480, monkeypatch)
        assert self._worker({"codec": "best", "height": 720,
                             "cap": True})._verify("x.mp4") == ""

    def test_cap_rejects_a_larger_height(self, monkeypatch):
        self._probe("h264", 2160, monkeypatch)
        warn = self._worker({"codec": "best", "height": 720,
                             "cap": True})._verify("x.mp4")
        assert "2160p" in warn

    def test_unreadable_file_is_silent(self, monkeypatch):
        from src import youtube_media
        monkeypatch.setattr(youtube_media, "probe_video_file", lambda path: None)
        assert self._worker({"codec": "h264", "height": 720,
                             "cap": False})._verify("x.mp4") == ""

    def test_empty_path_is_silent(self, monkeypatch):
        self._probe("h264", 2160, monkeypatch)
        assert self._worker({"codec": "h264", "height": 720,
                             "cap": False})._verify("") == ""


def _cues() -> list[dict]:
    """Note: in this model the ``text`` key **is** the editable translation —
    ``CueResultModel`` exposes it to QML as ``translationText`` and stores the
    untouched original under ``source``."""
    return [
        {"start_ms": 0, "end_ms": 1000, "source": "orig one",
         "text": "hello world", "status": "ok", "tags": []},
        {"start_ms": 1000, "end_ms": 2000, "source": "orig two",
         "text": "goodbye hello", "status": "ok", "tags": []},
    ]


class TestReplaceInCues:
    """``replaceInCues`` (the "Replace all" button) used ``Qt.EditRole`` while
    ``backend/bridge.py`` never imported ``Qt`` — so it raised
    ``NameError: name 'Qt' is not defined`` as soon as a replacement was made.
    """
    def _bridge(self, app_bridge):
        app_bridge.cue_model.load(_cues())
        return app_bridge

    def test_plain_replace_updates_cues(self, app_bridge):
        bridge = self._bridge(app_bridge)
        made = bridge.replaceInCues("hello", "HI", False)
        assert made == 2, made
        assert bridge.cue_model.get_cue(0)["text"] == "HI world"
        assert bridge.cue_model.get_cue(1)["text"] == "goodbye HI"

    def test_replace_returns_zero_when_nothing_matches(self, app_bridge):
        bridge = self._bridge(app_bridge)
        assert bridge.replaceInCues("zzzz", "x", False) == 0

    def test_empty_find_is_a_noop(self, app_bridge):
        bridge = self._bridge(app_bridge)
        assert bridge.replaceInCues("", "x", False) == 0
        assert bridge.cue_model.get_cue(0)["text"] == "hello world"

    def test_regex_replace_works(self, app_bridge):
        bridge = self._bridge(app_bridge)
        made = bridge.replaceInCues(r"h\w+", "X", True)
        assert made == 2, made
        assert bridge.cue_model.get_cue(0)["text"] == "X world"

    def test_invalid_regex_is_a_noop_not_a_crash(self, app_bridge):
        bridge = self._bridge(app_bridge)
        assert bridge.replaceInCues("([", "x", True) == 0

    def test_original_text_is_preserved_for_revert(self, app_bridge):
        bridge = self._bridge(app_bridge)
        bridge.replaceInCues("hello", "HI", False)
        assert bridge.cue_model.edited_count() == 2
        bridge.revertAllEdits()
        assert bridge.cue_model.get_cue(0)["text"] == "hello world"
        assert bridge.cue_model.edited_count() == 0


class TestCjkFromCues:
    """``detect_cjk_from_cues`` had a ``for ch in text:`` loop *after* its
    ``return`` — dead code referencing an undefined name."""
    def test_detects_chinese(self):
        from src.cjk import detect_cjk_from_cues

        class C:
            def __init__(self, t):
                self.text = t

        # >= 8 CJK chars: a smaller sample is deliberately treated as ambiguous.
        assert detect_cjk_from_cues([C("你好世界"), C("早上好呀")]) == "zh"

    def test_returns_none_for_latin(self):
        from src.cjk import detect_cjk_from_cues

        class C:
            def __init__(self, t):
                self.text = t

        assert detect_cjk_from_cues([C("hello"), C("world")]) is None

    def test_handles_empty_and_missing_text(self):
        from src.cjk import detect_cjk_from_cues

        class C:
            def __init__(self, t):
                self.text = t

        assert detect_cjk_from_cues([]) is None
        assert detect_cjk_from_cues([C(None), C("")]) is None
