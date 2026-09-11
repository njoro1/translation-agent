"""End-to-end proof: download a real video at a *specific* codec+resolution
and confirm the file on disk actually matches what was requested.

This is the check the user's bug report was really about — the dropdowns were
being ignored and the highest-quality stream arrived instead. So we do not
trust the selector: we inspect the produced file afterwards.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import youtube_media  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
CODEC = sys.argv[2] if len(sys.argv) > 2 else "h264"
RES = sys.argv[3] if len(sys.argv) > 3 else "240"

print(f"URL   : {URL}")
print(f"WANT  : codec={CODEC} resolution={RES}p")
print("ffmpeg :", youtube_media._ffmpeg_exe())
print("ffprobe:", youtube_media._ffprobe_exe())
print()

print("== inspecting ==", flush=True)
info = youtube_media.inspect_video(URL)
print("title :", info.get("title"))

opt = youtube_media.resolve_video_option(info, CODEC, RES)
if not opt:
    print("REFUSED:", youtube_media.describe_unavailable(info, CODEC, RES))
    sys.exit(2)

selector = opt["format_selector"]
print("resolved selector:", selector)
print("label            :", opt.get("label"))
print()

outdir = tempfile.mkdtemp(prefix="ta_e2e_")
template = os.path.join(outdir, "%(title).60s.%(ext)s")

print("== downloading ==", flush=True)
try:
    path = youtube_media.download_video(URL, selector, template)
except Exception as exc:  # noqa: BLE001
    print("DOWNLOAD FAILED:", exc)
    sys.exit(3)

print("file :", path)
print("size :", os.path.getsize(path) if os.path.isfile(path) else "MISSING", "bytes")
print()

print("== verifying the produced file ==", flush=True)
probe = youtube_media.probe_video_file(path)
print("probe:", json.dumps(probe))

if probe is None:
    print("\nRESULT: UNVERIFIED (no ffprobe/ffmpeg could read the file)")
    sys.exit(4)

want_h = int(RES)
got_h = int(probe.get("height") or 0)
want_c = youtube_media._CODEC_PREFIX.get(CODEC, CODEC)
got_c = str(probe.get("codec") or "")

print(f"\nwant : {want_c} @ {want_h}p")
print(f"got  : {got_c} @ {got_h}p  (codec_name={probe.get('codec_name')}, "
      f"{probe.get('width')}x{probe.get('height')})")

ok_h = got_h == want_h
ok_c = got_c == CODEC or str(probe.get("codec_name", "")).startswith(want_c[:4])
print(f"\nheight match : {'PASS' if ok_h else 'FAIL'}")
print(f"codec  match : {'PASS' if ok_c else 'FAIL'}")
print("\nRESULT:", "PASS — downloaded exactly what was requested"
      if (ok_h and ok_c) else "FAIL — file does not match the request")
sys.exit(0 if (ok_h and ok_c) else 1)
