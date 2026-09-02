"""Temporary validation for the YouTube inspection UI changes.

Simulates the real worker path (INFO:<json>) and checks:
  * youtubeHasInfo gating (False before inspect, True after)
  * youtubeFormatRows ordering/content (best first, res desc, codec order)
  * size/format text rendering
  * int-height normalization so combined formats still resolve after the
    JSON round-trip (this was the silent "always merge" bug)
"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QGuiApplication  # noqa: E402

app = QGuiApplication(sys.argv)

from backend.bridge import AppBridge  # noqa: E402

b = AppBridge()
b._settings.clear()

# --- 1) Before inspection: nothing to show -----------------------------------
assert b.youtubeHasInfo is False, "hasInfo must be False before inspecting"
assert list(b.youtubeFormatRows) == [], "format rows must be empty before inspecting"

# --- 2) Simulate a worker result (json.dumps turns int keys into strings) ----
info = {
    "title": "Test Video — Codec Matrix",
    "video_id": "abc123",
    "codecs": ["av1", "vp9", "h264"],
    "resolutions": [2160, 1080, 720],
    "matrix": {
        "av1": {
            2160: {"format_selector": "merge-av1-2160", "filesize": 0, "ext": "mkv",
                    "fps": 0, "label": "2160p · AV1", "has_audio": True, "merge": True},
            1080: {"format_selector": "683", "filesize": 250 * 1024 * 1024,
                    "ext": "mp4", "fps": 30, "label": "1080p · AV1",
                    "has_audio": True, "merge": False},
        },
        "vp9": {
            1080: {"format_selector": "merge-vp9-1080", "filesize": 0, "ext": "mkv",
                    "fps": 0, "label": "1080p · VP9", "has_audio": True, "merge": True},
        },
        "h264": {
            1080: {"format_selector": "137+140", "filesize": 220 * 1024 * 1024,
                    "ext": "mp4", "fps": 30, "label": "1080p · H.264",
                    "has_audio": True, "merge": False},
            720: {"format_selector": "136+140", "filesize": 118 * 1024 * 1024,
                   "ext": "mp4", "fps": 30, "label": "720p · H.264",
                   "has_audio": True, "merge": False},
        },
    },
    "best": {"format_selector": "bv*+ba/b", "filesize": 0,
              "label": "Best available (any codec)", "merge": False},
    "codecs_available": {"av1": True, "vp9": True, "h264": True},
    "has_english_subtitle": True,
}
b._on_youtube_info("INFO:" + json.dumps(info))

assert b.youtubeHasInfo is True, "hasInfo must be True after a good inspection"
assert b.youtubeTitle == "Test Video — Codec Matrix"

# Default selection after inspection: first available codec, resolution "best".
# Exactly one row must be flagged selected: av1 @ its highest height (2160).
sel_rows = [dict(r) for r in b.youtubeFormatRows if r["selected"]]
assert len(sel_rows) == 1, f"expected exactly 1 selected row, got {sel_rows}"
assert sel_rows[0]["codec"] == "av1" and sel_rows[0]["resolution"] == 2160, sel_rows

# Selecting the Best row flags only the best row.
b.youtubeSelectedCodec = "best"
b.youtubeSelectedResolution = "best"
sel_rows = [dict(r) for r in b.youtubeFormatRows if r["selected"]]
assert len(sel_rows) == 1 and sel_rows[0]["isBest"], sel_rows

# Selecting h264 @ "best" flags the highest h264 row (1080).
b.youtubeSelectedCodec = "h264"
b.youtubeSelectedResolution = "best"
sel_rows = [dict(r) for r in b.youtubeFormatRows if r["selected"]]
assert len(sel_rows) == 1 and sel_rows[0]["codec"] == "h264" \
       and sel_rows[0]["resolution"] == 1080, sel_rows

rows = [dict(r) for r in b.youtubeFormatRows]
assert rows[0]["isBest"] is True, "best row must come first"
assert rows[0]["resLabel"] == "Best" and rows[0]["formatText"] == "auto"

seq = [(r["resolution"], r["codec"]) for r in rows[1:]]
expected = [(2160, "av1"), (1080, "av1"), (1080, "vp9"), (1080, "h264"), (720, "h264")]
assert seq == expected, f"row order wrong:\n  got      {seq}\n  expected {expected}"

by_key = {(r["codec"], r["resolution"]): r for r in rows[1:]}
assert by_key[("av1", 1080)]["sizeText"].endswith("MB"), by_key[("av1", 1080)]
assert by_key[("av1", 1080)]["formatText"] == "mp4 · 30fps"
assert by_key[("av1", 2160)]["sizeText"] == "—"
assert by_key[("av1", 2160)]["formatText"] == "video + audio merge"
assert by_key[("av1", 2160)]["merge"] is True
assert by_key[("h264", 720)]["sizeText"].endswith("MB")

# --- 3) Selection still resolves combined formats after the JSON round-trip --
b.youtubeSelectedCodec = "h264"
b.youtubeSelectedResolution = 1080
opt = dict(b.youtubeSelectedOption)
assert opt["format_selector"] == "137+140", (
    "string-height keys broke combined-format resolution again: " + str(opt))
assert opt.get("merge") is False

b.youtubeSelectedResolution = "best"
opt = dict(b.youtubeSelectedOption)
assert opt["format_selector"] == "137+140", "best resolution should pick 1080 for h264"

b.youtubeSelectedCodec = "vp9"
opt = dict(b.youtubeSelectedOption)
assert opt["format_selector"] == "merge-vp9-1080", opt

b.youtubeSelectedCodec = "best"
b.youtubeSelectedResolution = "best"
opt = dict(b.youtubeSelectedOption)
assert opt["format_selector"] == "bv*+ba/b", opt

# --- 4) URL change resets everything -----------------------------------------
b.url = "https://youtu.be/dQw4w9WgXcQ"
assert b.youtubeHasInfo is False, "changing the URL must drop stale inspection"
assert list(b.youtubeFormatRows) == []

print("ALL YOUTUBE-UI CHECKS PASSED")
