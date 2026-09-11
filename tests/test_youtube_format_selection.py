"""QML-level regression: a pick in the YouTube dropdowns must reach the bridge.

Historical bug — and the reason the download ignored the dropdowns entirely:
``youtubeSelectedResolution`` was declared ``@Property(object)``, which PySide6
registers with the type ``PySide::PyObjectWrapper``. The QML engine *refuses to
write* that type ("Cannot assign int to PySide::PyObjectWrapper"), so every
resolution pick was silently discarded. The bridge kept its default ("best"),
which resolves to the highest-quality stream — while the UI happily showed the
resolution the user had just chosen.

These tests drive the real ``ComboBox`` objects in ``Main.qml`` so the write
path (QML -> PySide6 -> Python setter) is exercised, not just the logic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject

from src import youtube_media

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"

CODEC_COMBO = "youtubeCodecCombo"
RES_COMBO = "youtubeResolutionCombo"


def _formats() -> list[dict]:
    """h264: 1080/720/480/360 (360 muxed) · vp9: 2160/720 · av1: 2160."""
    def fmt(fid, ext, height, vcodec, acodec, tbr, size):
        return {"format_id": fid, "ext": ext, "height": height,
                "vcodec": vcodec, "acodec": acodec, "tbr": tbr,
                "filesize": size, "fps": 30}

    return [
        fmt("140", "m4a", None, "none", "mp4a.40.2", 128, 4_000_000),
        fmt("401", "mp4", 2160, "av01.0.13M.10", "none", 10000, 120_000_000),
        fmt("315", "webm", 2160, "vp9", "none", 12000, 150_000_000),
        fmt("302", "webm", 720, "vp9", "none", 1800, 15_000_000),
        fmt("137", "mp4", 1080, "avc1.640028", "none", 4500, 40_000_000),
        fmt("136", "mp4", 720, "avc1.4d401f", "none", 2500, 20_000_000),
        fmt("135", "mp4", 480, "avc1.4d401e", "none", 1200, 9_000_000),
        fmt("134", "mp4", 360, "avc1.4d401e", "none", 650, 5_000_000),
        fmt("18", "mp4", 360, "avc1.42001E", "mp4a.40.2", 700, 6_000_000),
    ]


@pytest.fixture(scope="module")
def session(qml_main):
    """Reuse the session-wide Main.qml instance (see ``conftest.qml_main``)."""
    bridge = qml_main.bridge
    root = qml_main.root
    warnings = qml_main.warnings
    bridge._youtube_info_gen += 1
    _codecs, _res, matrix, best = youtube_media._build_matrix(_formats())
    bridge._on_youtube_info(f"INFO:{bridge._youtube_info_gen}|" + json.dumps({
        "title": "Test video", "video_id": "test0000001",
        "codecs": _codecs,
        "resolutions": _res,
        "matrix": matrix,
        "best": best,
        "codecs_available": {"av1": True, "vp9": True, "h264": True},
        "has_english_subtitle": True,
    }))
    yield bridge, root, warnings


@pytest.fixture()
def panel(session):
    bridge, root, warnings = session
    codec = root.findChild(QObject, CODEC_COMBO)
    res = root.findChild(QObject, RES_COMBO)
    assert codec is not None, "codec combo not found (objectName missing?)"
    assert res is not None, "resolution combo not found (objectName missing?)"
    # Back to the default state so the tests do not depend on each other.
    bridge.youtubeSelectedCodec = bridge.youtubeCodecs[0]["id"]
    bridge.youtubeSelectedResolution = "best"
    warnings.clear()
    return bridge, codec, res, warnings


def _pick(combo, index: int) -> None:
    """Emulate a popup click (ComboBox sets the index, then emits activated)."""
    combo.setProperty("currentIndex", index)
    combo.activated.emit(index)


def _index_of(combo, value) -> int:
    model = combo.property("model") or []
    role = "id" if combo.objectName() == CODEC_COMBO else "value"
    for i, item in enumerate(model):
        if str(item[role]) == str(value):
            return i
    raise AssertionError(f"{value!r} not in {combo.objectName()} model: {model}")


class TestDropdownPicksReachTheBridge:
    def test_codec_pick_is_stored(self, panel):
        bridge, codec, _res, _warnings = panel
        _pick(codec, _index_of(codec, "h264"))
        assert bridge.youtubeSelectedCodec == "h264"

    def test_resolution_pick_is_stored(self, panel):
        """The regression: this write used to fail with
        "Cannot assign int to PySide::PyObjectWrapper" and be dropped."""
        bridge, codec, res, warnings = panel
        _pick(codec, _index_of(codec, "h264"))
        _pick(res, _index_of(res, "360"))

        assert bridge.youtubeSelectedResolution == "360", (
            "resolution pick was dropped; warnings: " + "; ".join(warnings))
        assert not [w for w in warnings if "Cannot assign" in w], warnings

    def test_pick_changes_the_download_selector(self, panel):
        """End to end: picking H.264 + 360p must select the real 360p stream,
        not the highest-quality one the video happens to serve."""
        bridge, codec, res, _warnings = panel

        _pick(codec, _index_of(codec, "h264"))
        _pick(res, _index_of(res, "360"))

        selector = bridge._selected_format_selector()
        assert selector == "18", selector
        assert bridge.youtubeSelectedOption["resolution"] == 360
        # The default (av1 @ best) would have been the 2160p stream.
        assert "401" not in selector

    def test_switching_codec_keeps_a_valid_pair(self, panel):
        bridge, codec, res, _warnings = panel
        _pick(codec, _index_of(codec, "vp9"))
        _pick(res, _index_of(res, "2160"))
        assert bridge.youtubeSelectedResolution == "2160"
        assert bridge._selected_format_selector().startswith("315")

    def test_combo_stays_in_sync_after_a_pick(self, panel):
        """The picker must show what was selected — not snap back to "Best"."""
        bridge, codec, res, _warnings = panel
        _pick(codec, _index_of(codec, "h264"))
        idx = _index_of(res, "480")
        _pick(res, idx)
        assert bridge.youtubeSelectedResolution == "480"
        assert res.property("currentIndex") == idx


class TestUnavailablePairIsReported:
    def test_unavailable_resolution_has_no_selector(self, panel):
        """h264 serves no 2160p: the option must be empty so the download can
        refuse, instead of falling back to a "best" stream."""
        bridge, codec, _res, _warnings = panel
        _pick(codec, _index_of(codec, "h264"))
        # 2160 is not offered for h264, so drive the bridge directly.
        bridge.youtubeSelectedResolution = "2160"

        assert bridge.youtubeSelectedOption == {}
        assert bridge._selected_format_selector() == ""
        assert "2160p" in bridge.youtubeSelectionError
        assert "1080p" in bridge.youtubeSelectionError

    def test_download_button_is_disabled_without_a_selection(self, panel):
        """The QML Download button is gated on ``selectedOpt.format_selector``,
        so an empty option must mean no download can start."""
        bridge, codec, _res, _warnings = panel
        _pick(codec, _index_of(codec, "h264"))
        bridge.youtubeSelectedResolution = "2160"
        assert not (bridge.youtubeSelectedOption or {}).get("format_selector")


SELECTION_LABEL = "youtubeSelectionLabel"


class TestSelectionLabelExplainsUnavailablePairs:
    """The panel must *say* what is wrong, not just refuse silently.

    The backend message is covered by unit tests; this checks the QML actually
    renders it (and drops back to the normal colour once the pick is valid).
    """

    @pytest.fixture()
    def labeled(self, session):
        """``session`` is (bridge, root, warnings) — see ``conftest.qml_main``."""
        bridge, root, warnings = session
        label = root.findChild(QObject, SELECTION_LABEL)
        assert label is not None, (
            "youtubeSelectionLabel not found (objectName missing?)")
        bridge.youtubeSelectedCodec = bridge.youtubeCodecs[0]["id"]
        bridge.youtubeSelectedResolution = "best"
        warnings.clear()
        return bridge, label, warnings

    def test_available_pair_shows_the_selection(self, labeled):
        bridge, label, _warnings = labeled
        bridge.youtubeSelectedCodec = "h264"
        bridge.youtubeSelectedResolution = "360"
        text = str(label.property("text"))
        assert text.startswith("Selected:"), text
        assert "360p" in text, text

    def test_unavailable_pair_names_the_missing_format(self, labeled):
        bridge, label, _warnings = labeled
        bridge.youtubeSelectedCodec = "h264"
        bridge.youtubeSelectedResolution = "2160"  # h264 tops out at 1080p
        text = str(label.property("text"))
        assert "not available" in text.lower(), text
        assert "H.264" in text and "2160p" in text, text
        # and it must tell the user what they *can* pick
        assert "1080p" in text, text

    def test_unavailable_pair_uses_the_warning_colour(self, labeled):
        bridge, label, _warnings = labeled
        bridge.youtubeSelectedCodec = "h264"
        bridge.youtubeSelectedResolution = "720"
        ok_colour = label.property("color")
        bridge.youtubeSelectedResolution = "2160"
        bad_colour = label.property("color")
        assert ok_colour != bad_colour, (
            "an unselectable pair must look different from a valid one")

    def test_recovers_when_the_pick_becomes_valid(self, labeled):
        bridge, label, _warnings = labeled
        bridge.youtubeSelectedCodec = "h264"
        bridge.youtubeSelectedResolution = "2160"
        assert "not available" in str(label.property("text")).lower()
        bridge.youtubeSelectedResolution = "1080"
        assert str(label.property("text")).startswith("Selected:"), \
            label.property("text")
