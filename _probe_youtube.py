"""Probe the YouTube inspection pipeline with a REAL video.

Runs youtube_media.inspect_video() live, feeds the result through the same
JSON round-trip as the bridge, then replays every (codec, resolution) pair
the UI can select and flags any that resolve to nothing (the source of the
"No matching stream for this codec/resolution." message).
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QGuiApplication  # noqa: E402

app = QGuiApplication(sys.argv)

from backend.bridge import AppBridge  # noqa: E402
from src import youtube_media  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=aqz-KE-bpKQ"

print("== raw inspect_video()", flush=True)
try:
    info = youtube_media.inspect_video(URL)
except Exception as exc:  # noqa: BLE001
    print("INSPECT FAILED:", exc)
    sys.exit(2)

print("title      :", info.get("title"))
print("codecs     :", info.get("codecs"))
print("resolutions:", info.get("resolutions"))
print("en subs    :", info.get("has_english_subtitle"))
print("best       :", json.dumps(info.get("best"), indent=2))
print("matrix:")
for cid, fam in (info.get("matrix") or {}).items():
    for h, opt in fam.items():
        print(f"  {cid:5s} {h:>5} -> sel={opt.get('format_selector')!r:24s} "
              f"size={opt.get('filesize')} merge={opt.get('merge')} ext={opt.get('ext')} "
              f"label={opt.get('label')!r}")

# Also show a raw slice of what yt-dlp itself reported, for context.
raw = youtube_media._yt_dlp_json(URL)
print("\n== yt-dlp raw formats (video-bearing) ==")
for f in raw.get("formats") or []:
    if (f.get("vcodec") or "none") == "none":
        continue
    print(f"  id={f.get('format_id'):>6} ext={f.get('ext'):5} h={f.get('height')} "
          f"vcodec={f.get('vcodec')} acodec={f.get('acodec')} "
          f"tbr={f.get('tbr')} fs={f.get('filesize') or f.get('filesize_approx')}")

print("\n== bridge replay (exact UI path) ==", flush=True)
b = AppBridge()
b._settings.clear()
b.url = URL
b._on_youtube_info("INFO:" + json.dumps(info))

print("hasInfo:", b.youtubeHasInfo)
print("youtubeCodecs    :", b.youtubeCodecs)
print("youtubeResolutions:", b.youtubeResolutions)
print("format rows:", len(b.youtubeFormatRows))
for r in b.youtubeFormatRows:
    print("   ", r)

failures = []
combos = [(c["id"], r["value"]) for c in b.youtubeCodecs for r in b.youtubeResolutions]
combos.append(("best", "best"))
for codec, res in combos:
    b.youtubeSelectedCodec = codec
    b.youtubeSelectedResolution = res
    opt = b.youtubeSelectedOption
    ok = bool(opt and opt.get("format_selector"))
    tag = "OK " if ok else "FAIL"
    print(f"  [{tag}] codec={codec!r:6} res={res!r:8} -> "
          f"{(opt or {}).get('format_selector')!r} size={(opt or {}).get('filesize')}")
    if not ok:
        failures.append((codec, res, opt))

# Row-click simulation (what MouseArea.onClicked does).
print("\n== row-click replay ==")
for r in b.youtubeFormatRows:
    if r["isBest"]:
        b.youtubeSelectedCodec = "best"
        b.youtubeSelectedResolution = "best"
    else:
        b.youtubeSelectedCodec = r["codec"]
        b.youtubeSelectedResolution = r["resolution"]
    opt = b.youtubeSelectedOption
    ok = bool(opt and opt.get("format_selector"))
    print(f"  [{'OK ' if ok else 'FAIL'}] click row {r['codec']}/{r['resolution']} -> "
          f"{(opt or {}).get('format_selector')!r}")
    if not ok:
        failures.append(("click", r, opt))

print("\nRESULT:", "ALL SELECTIONS RESOLVED" if not failures
      else f"{len(failures)} FAILURES -> {failures}")
