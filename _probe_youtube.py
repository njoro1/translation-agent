"""Probe the YouTube inspection pipeline with a REAL video.

Runs youtube_media.inspect_video() live, feeds the result through the same
JSON round-trip as the bridge, then replays every (codec, resolution) pair the
UI can actually offer and reports the exact yt-dlp selector each one resolves
to — plus a couple of pairs the UI cannot offer, which must now be refused.
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
# ``_on_youtube_info`` drops any payload whose generation tag does not match
# the bridge's current one, and the tag travels before the first "|". Setting
# the URL bumps the generation, so take the value *after* that.
b._youtube_info_gen += 1
b._on_youtube_info(f"INFO:{b._youtube_info_gen}|" + json.dumps(info))

print("hasInfo:", b.youtubeHasInfo)
print("youtubeCodecs    :", b.youtubeCodecs)
print("youtubeResolutions:", b.youtubeResolutions)
print("format rows:", len(b.youtubeFormatRows))
for r in b.youtubeFormatRows:
    print("   ", r)

failures = []

print("\n== every pair the UI can offer ==")
# The resolution list is codec-aware, so it must be read *after* selecting the
# codec — that is the only way to enumerate combinations a user can pick.
for codec_item in b.youtubeCodecs:
    codec = codec_item["id"]
    b.youtubeSelectedCodec = codec
    for res_item in b.youtubeResolutions:
        res = res_item["value"]
        b.youtubeSelectedResolution = res
        opt = b.youtubeSelectedOption
        ok = bool(opt and opt.get("format_selector"))
        tag = "OK " if ok else "FAIL"
        print(f"  [{tag}] codec={codec!r:6} res={res!r:8} -> "
              f"{(opt or {}).get('format_selector')!r} "
              f"size={(opt or {}).get('filesize')}")
        if not ok:
            failures.append((codec, res, opt))

print("\n== pairs that genuinely do not exist (must refuse) ==")
# Do NOT hard-code "144p" — plenty of videos really do serve it. Instead build
# the cartesian product of every codec x every height the video offers anywhere,
# and keep only the holes in the matrix. Those are the true "unavailable" pairs.
all_heights = sorted(
    {int(h) for fam in (info.get("matrix") or {}).values() for h in fam}
    | {int(h) for h in (info.get("resolutions") or [])},
    reverse=True,
)
missing = []
for codec_item in b.youtubeCodecs:
    cid = codec_item["id"]
    if cid == "best":
        continue  # "best (any)" legitimately serves every height, capped
    fam = (info.get("matrix") or {}).get(cid) or {}
    have = {int(h) for h in fam}
    for h in all_heights:
        if h not in have:
            missing.append((cid, h))

if not missing:
    print("  (this video offers every codec x height combination; nothing to refuse)")
else:
    for cid, h in missing:
        b.youtubeSelectedCodec = cid
        b.youtubeSelectedResolution = str(h)
        opt = b.youtubeSelectedOption
        served = bool((opt or {}).get("format_selector"))
        reason = b.youtubeSelectionError
        status = "SERVED " if served else "REFUSED"
        print(f"  [{status}] codec={cid!r:6} res={h!r:6} -> {reason!r}")
        if served:
            failures.append((cid, h, opt))
        elif "not available" not in reason.lower():
            print("      ^ refused but the message does not say 'not available'")
            failures.append((cid, h, reason))

# The dropdown list itself must never offer a hole either: for every codec, each
# listed resolution has to resolve.
print("\n== dropdown lists contain no holes ==")
for codec_item in b.youtubeCodecs:
    cid = codec_item["id"]
    b.youtubeSelectedCodec = cid
    for res_item in b.youtubeResolutions:
        res = res_item["value"]
        b.youtubeSelectedResolution = res
        if not (b.youtubeSelectedOption or {}).get("format_selector"):
            print(f"  [HOLE] codec={cid!r} res={res!r}")
            failures.append(("hole", cid, res))
print("  (no output above == every offered entry resolves)")

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
sys.exit(1 if failures else 0)
