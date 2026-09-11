"""Inspect and download YouTube media (codec-aware) via yt-dlp.

This complements :mod:`src.fetch_subs` (which only pulls the *text* transcript).
Here we focus on the actual video/audio streams so the user can grab the file
in the modern codec YouTube may serve for a given video:

  * AV1 (``av01``) and VP9 (``vp9``/``vp09``) are the "new" efficiency codecs;
    H.264 (``avc1``) is the legacy fallback. We surface which of these are
    available for the video and let the caller pick a codec *and* a resolution.

The same module can download an English subtitle track (manual preferred,
auto-generated fallback) when one exists.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

from .fetch_subs import extract_video_id

# yt-dlp invocation (subprocess, or in-process when frozen) — see src/ytdlp.py.
from .ytdlp import (
    YtdlpError,
    YtdlpFailed,
    YtdlpTimeout,
    YtdlpUnavailable,
    run_ytdlp,
    run_ytdlp_capture,
    yt_dlp_available,
    yt_dlp_cmd as _yt_dlp_cmd,
)

# Codec family detection -------------------------------------------------------
# Maps a format's ``vcodec`` prefix to a short human label.
_CODEC_FAMILIES = {
    "av01": "AV1",
    "av1": "AV1",
    "vp9": "VP9",
    "vp09": "VP9",
    "vp8": "VP8",
    "avc1": "H.264",
    "h264": "H.264",
    "hvc1": "H.265",
    "hev1": "H.265",
}

# Mapping between our short codec ids and yt-dlp's vcodec prefixes / labels.
_CODEC_IDS = {"AV1": "av1", "VP9": "vp9", "H.264": "h264"}
_CODEC_PREFIX = {"av1": "av01", "vp9": "vp9", "h264": "avc1"}
_CODEC_LABEL = {"av1": "AV1", "vp9": "VP9", "h264": "H.264"}
# Preference order for default codec selection (newer codecs first).
_CODEC_ORDER = ("av1", "vp9", "h264")

# YouTube's DASH stream URLs expire (roughly six hours). Resuming a partial
# download after the URL has expired makes YouTube answer ``403 Forbidden``,
# so a ``.part`` file older than this is treated as dead and discarded before
# the download is restarted. 15 minutes is comfortably inside the URL lifetime,
# so a genuine "retry 30 seconds later" still resumes normally.
_STALE_PART_AGE = 15 * 60

# A 403 from an expired URL is recoverable, so one clean-slate retry is worth
# it. A second failure is reported instead of looping.
_MAX_DOWNLOAD_ATTEMPTS = 2

# Shared by video and subtitle downloads: YouTube throttles long transfers and
# drops individual fragments, so without these a single hiccup is reported as a
# hard failure instead of being retried.
_RESILIENCE_FLAGS = [
    "--retries", "10",
    "--fragment-retries", "10",
    "--extractor-retries", "5",
    "--file-access-retries", "5",
    "--retry-sleep", "http:exp=1:20",
    "--retry-sleep", "fragment:exp=1:20",
    "--sleep-requests", "0.75",
]

# Video only. YouTube serves video in chunks and stalls hard between them;
# below this rate yt-dlp re-extracts the format rather than crawling for hours.
_THROTTLED_RATE = "50K"


def _codec_family(vcodec: str | None) -> str | None:
    """Return the codec family label for a yt-dlp ``vcodec`` string."""
    if not vcodec or vcodec == "none":
        return None
    low = vcodec.lower()
    for key, label in _CODEC_FAMILIES.items():
        if low.startswith(key) or key in low:
            return label
    return vcodec.split(".")[0] or vcodec


def _ensure_ffmpeg_exe_named(binary: str) -> str:
    """Return a path to a file literally named ``ffmpeg.exe``.

    yt-dlp's ``--ffmpeg-location`` only recognises a binary called
    ``ffmpeg``/``ffmpeg.exe`` when it scans a directory. A packaged binary such
    as ``ffmpeg-win-x86_64-v7.1.exe`` is never found by that scan, so the
    video+audio merge silently never runs and the user gets two separate files
    (a video-only stream + an audio-only stream) instead of one. If the
    discovered binary is not already named ``ffmpeg.exe``, copy it next to
    itself (or into a writable temp dir when the frozen bundle is read-only) and
    return that ``ffmpeg.exe``.
    """
    import shutil as _shutil

    if os.path.basename(binary).lower() == "ffmpeg.exe":
        return binary
    target_dir = os.path.dirname(os.path.abspath(binary))
    if not os.access(target_dir, os.W_OK):
        import tempfile
        target_dir = tempfile.gettempdir()
    target = os.path.join(target_dir, "ffmpeg.exe")
    if (not os.path.isfile(target)
            or os.path.getsize(target) != os.path.getsize(binary)):
        try:
            _shutil.copyfile(binary, target)
        except OSError:
            return binary
    return target


def _ffmpeg_exe() -> str | None:
    """Locate ffmpeg (needed to merge separate video+audio streams).

    Mirrors the resolution strategy used by ``src.local_asr``, plus a
    frozen-build fallback: in a packaged app ``shutil.which`` cannot see the
    binary PyInstaller unpacked next to the executable, so the bundle directory
    is searched directly and every candidate is checked for existence (a
    packaged ``imageio_ffmpeg`` can report a path that was never collected).
    """
    candidates: list[str] = []

    # In a packaged build the bundled binary wins: it is the one that was
    # verified at build time, and it is the only one guaranteed to be there.
    if getattr(sys, "frozen", False):
        for directory in (
            getattr(sys, "_MEIPASS", "") or "",
            os.path.dirname(os.path.abspath(sys.executable)),
        ):
            if directory:
                candidates.extend(sorted(glob.glob(os.path.join(directory, "ffmpeg*.exe"))))

    env = os.environ.get("FFMPEG_BIN")
    if env:
        candidates.append(env)
    try:
        import imageio_ffmpeg

        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    exe = shutil.which("ffmpeg")
    if exe:
        candidates.append(exe)

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return _ensure_ffmpeg_exe_named(candidate)
    return None


# ``_yt_dlp_cmd`` lives in :mod:`src.ytdlp` (and is re-exported by
# :mod:`src.fetch_subs`) because that is the lowest-level module.

_YTDLP_HINT = (
    "yt-dlp is not installed. Install it with: pip install yt-dlp"
)


# --- Inspection ---------------------------------------------------------------
def _yt_dlp_json(url: str) -> dict:
    """Run ``yt-dlp --dump-json`` and return the parsed info dict."""
    try:
        stdout = run_ytdlp_capture(
            _yt_dlp_cmd() + ["--no-warnings", "--no-playlist", "--dump-json", url],
            timeout=120,
        )
    except YtdlpUnavailable as exc:
        raise RuntimeError(_YTDLP_HINT) from exc
    except YtdlpTimeout as exc:
        raise RuntimeError("Timed out inspecting the video with yt-dlp.") from exc
    except YtdlpFailed as exc:
        raise RuntimeError(
            "Could not inspect the video with yt-dlp: "
            + (exc.output or str(exc) or "unknown error")
        ) from exc
    except YtdlpError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Could not run yt-dlp: {exc}") from exc

    try:
        return json.loads(stdout)
    except ValueError as exc:
        raise RuntimeError("Could not parse yt-dlp's output for this video.") from exc


def _build_matrix(formats: list[dict]) -> tuple[list[str], list[int], dict, dict]:
    """Build a codec × resolution selection matrix from yt-dlp's formats.

    Returns ``(codecs, resolutions, matrix, best)`` where:

      * ``codecs``      — available codec ids in preference order (e.g.
                          ``["av1", "vp9", "h264"]``), possibly a subset.
      * ``resolutions`` — available heights (int) sorted descending.
      * ``matrix``      — ``{codec_id: {height: option_dict}}``; each option has a
                          ``format_selector`` (yt-dlp ``-f`` string), a ``filesize``
                          (bytes, estimated for merges when known), ``ext``, ``fps``
                          and a human ``label``.
      * ``best``        — an option dict for "best available (any codec)".

    Every (codec, height) pair YouTube actually serves gets an option: we
    prefer a *combined* (video+audio) single file when one exists, and
    otherwise build a merge selector from the *real* video-only format id
    plus the best audio stream — so the options shown to the user always
    correspond to streams that genuinely exist for this video.
    """
    combined_by_key: dict[tuple[str, int], dict] = {}
    video_only_by_key: dict[tuple[str, int], dict] = {}
    heights: set[int] = set()

    for f in formats:
        vcodec = (f.get("vcodec") or "none").lower()
        acodec = (f.get("acodec") or "none").lower()
        if vcodec == "none":
            continue
        family = _codec_family(vcodec) or "other"
        if family not in _CODEC_IDS:
            continue
        cid = _CODEC_IDS[family]
        height = int(f.get("height") or 0)
        if height:
            heights.add(height)
        tbr = float(f.get("tbr") or 0)

        key = (cid, height)
        if acodec != "none":
            cur = combined_by_key.get(key)
            if cur is None or tbr > float(cur.get("tbr") or 0):
                combined_by_key[key] = f
        else:
            cur = video_only_by_key.get(key)
            if cur is None or tbr > float(cur.get("tbr") or 0):
                video_only_by_key[key] = f

    audio_size = _best_audio_size(formats)
    matrix: dict[str, dict[int, dict]] = {}

    # Combined (single-file) formats need no merging.
    for (cid, height), f in combined_by_key.items():
        matrix.setdefault(cid, {})[height] = _option_from_combined(f, cid, height)

    # Separate video+audio streams: fill in every remaining (codec, height)
    # pair, even when the codec also has a combined format at some other
    # height (e.g. muxed 360p alongside video-only 480p–2160p).
    for (cid, height), f in video_only_by_key.items():
        fam = matrix.setdefault(cid, {})
        if height in fam:
            continue
        fam[height] = _merge_option_from_format(f, cid, height, audio_size)

    # Keep codec order stable/preferred.
    codecs = sorted(
        matrix.keys(),
        key=lambda c: _CODEC_ORDER.index(c) if c in _CODEC_ORDER else 99,
    )

    resolutions = sorted(heights, reverse=True)
    best = _option_best()
    return codecs, resolutions, matrix, best


def _option_from_combined(f: dict, cid: str, height: int) -> dict:
    ext = f.get("ext") or ""
    filesize = f.get("filesize") or f.get("filesize_approx") or 0
    fps = f.get("fps") or 0
    label = f"{height}p · {_CODEC_LABEL[cid]}"
    if ext:
        label += f" · {ext}"
    if fps:
        label += f" · {int(fps)}fps"
    if filesize:
        label += f" · {_human_size(int(filesize))}"
    return {
        "codec": cid,
        "resolution": height,
        "ext": ext,
        "fps": int(fps) if fps else 0,
        "filesize": int(filesize) if filesize else 0,
        "has_audio": True,
        "merge": False,
        "label": label,
        "format_selector": f.get("format_id"),
    }


def _audio_safe_fallback(cid: str, height: int | None) -> str:
    """Fallback chain that always keeps an audio track.

    Used when the preferred video-only stream cannot be fetched. The final
    ``/best``-style resort of these chains used to be a *video-only* selector,
    which meant a failure in the audio leg silently produced a muted file while
    still reporting success. This chain instead retries another video stream of
    the same codec and height cap, and only then accepts a muxed stream that
    already carries audio (``[acodec!=none]``).
    """
    prefix = _CODEC_PREFIX.get(cid, "")
    cap = f"[height<={height}]" if height else ""
    codec = f"[vcodec^={prefix}]" if prefix else ""
    return (
        f"bestvideo{codec}{cap}+bestaudio"
        f"/best{codec}{cap}[acodec!=none]"
        f"/best{cap}[acodec!=none]"
    )


def _merge_option(cid: str, height: int | None = None) -> dict:
    prefix = _CODEC_PREFIX.get(cid, "")
    height_clause = f"[height={height}]" if height else ""
    # Every fallback in the chain must stay codec- (and height-) constrained: a
    # bare ``/best`` would silently download a *different* codec or resolution
    # than the user picked when the preferred alternative is unavailable.
    # (_audio_safe_fallback applies the height cap itself.)
    codec_clause = f"[vcodec^={prefix}]" if prefix else ""
    fallback = _audio_safe_fallback(cid, height)
    selector = f"bestvideo{codec_clause}{height_clause}+bestaudio/{fallback}"
    res_label = f"{height}p" if height else "best"
    return {
        "codec": cid,
        "resolution": height if height else "best",
        "ext": "mkv",
        "fps": 0,
        "filesize": 0,
        "has_audio": True,
        "merge": True,
        "label": f"Best {_CODEC_LABEL[cid]} ({res_label}, video + audio merge)",
        "format_selector": selector,
    }


def _merge_option_from_format(
    f: dict, cid: str, height: int, audio_size: int = 0
) -> dict:
    """Merge option built from a *real* video-only format.

    Uses the actual yt-dlp format id so the selector can never point at a
    stream the video doesn't serve, and estimates the merged size as video +
    best audio when both parts are known.
    """
    format_id = str(f.get("format_id") or "")
    if not format_id:
        return _merge_option(cid, height)
    ext = f.get("ext") or ""
    fps = int(f.get("fps") or 0)
    video_size = int(f.get("filesize") or f.get("filesize_approx") or 0)
    filesize = video_size + audio_size if video_size else 0
    res_label = f"{height}p" if height else "best"
    label = f"{res_label} · {_CODEC_LABEL[cid]}"
    if ext:
        label += f" · {ext}"
    if fps:
        label += f" · {fps}fps"
    label += " · video + audio merge"
    return {
        "codec": cid,
        "resolution": height if height else "best",
        "ext": ext,
        "fps": fps,
        "filesize": filesize,
        "has_audio": False,
        "merge": True,
        "label": label,
        # ``/{format_id}`` used to be the last resort, which downloaded the
        # video-only stream when the audio leg failed — a silent file reported
        # as a success. The audio-safe chain never ends on a video-only format.
        "format_selector": f"{format_id}+bestaudio/{_audio_safe_fallback(cid, height)}",
    }


def _best_audio_size(formats: list[dict]) -> int:
    """Estimate the size of the best audio track (largest audio-only format)."""
    sizes = []
    for f in formats:
        if (f.get("vcodec") or "none") == "none" and (f.get("acodec") or "none") != "none":
            size = int(f.get("filesize") or f.get("filesize_approx") or 0)
            if size > 0:
                sizes.append(size)
    return max(sizes) if sizes else 0


def _option_best() -> dict:
    return {
        "codec": "",
        "resolution": "best",
        "ext": "",
        "fps": 0,
        "filesize": 0,
        "has_audio": True,
        "merge": False,
        "label": "Best available (any codec)",
        "format_selector": "bv*+ba/b",
    }


def _option_best_height(height: int) -> dict:
    """Option for "best available (any codec)" capped at ``height`` pixels.

    Used when the codec dropdown says "Best (any)" but the user still picked a
    resolution: the selector keeps yt-dlp at or below the chosen height instead
    of ignoring the pick entirely.
    """
    h = int(height)
    cap = f"[height<={h}]"
    return {
        "codec": "best",
        "resolution": h,
        "ext": "",
        "fps": 0,
        "filesize": 0,
        "has_audio": True,
        "merge": False,
        "label": f"Best available (\u2264 {h}p)",
        # ``best{cap}`` alone can resolve to a video-only stream; prefer a
        # muxed stream with audio first.
        "format_selector": f"bestvideo{cap}+bestaudio/best{cap}[acodec!=none]/best{cap}",
    }


def normalize_resolution(value) -> str:
    """Normalise a resolution selection to ``"best"`` or a digit string.

    The UI can hand us an int (``720``), a float (``720.0`` — JavaScript has a
    single number type, so an int that has been through QML can come back as a
    double) or a string (``"720"`` / ``"best"``). Everything downstream
    compares against the string stored on the bridge, so collapse them here:
    no caller has to care which of the three it received.
    """
    if value is None or isinstance(value, bool):
        return "best"
    if isinstance(value, int):
        return "best" if value <= 0 else str(value)
    if isinstance(value, float):
        return "best" if value <= 0 else str(int(value))
    text = str(value).strip().lower()
    if text in ("", "best", "auto", "none", "null", "undefined"):
        return "best"
    try:
        return str(int(float(text)))
    except ValueError:
        return "best"


def _available_heights(info: dict) -> list[int]:
    """Every video height the inspected video serves, descending."""
    heights: set[int] = set()
    for family in (info.get("matrix") or {}).values():
        for height in family:
            heights.add(int(height))
    return sorted(heights, reverse=True)


def resolve_video_option(info: dict, codec: str, resolution) -> dict | None:
    """Pick the option dict for a (codec, resolution) selection.

    ``codec`` is one of ``"av1"``/``"vp9"``/``"h264"``/``"best"``; ``resolution``
    is an int height or the string ``"best"``. Returns the matching option dict
    (with ``format_selector`` + ``filesize``) or ``None`` when the video is not
    available in that combination.

    Strict by design — the pair must genuinely exist:

      * ``codec="best"`` + ``"best"``  → the unconstrained "best" selector.
      * ``codec="best"`` + a height    → any codec, capped at that height
                                         (reported as "≤ Np", never as Np).
      * a specific codec + ``"best"``  → the highest height that codec serves.
      * a specific codec + a height    → **exact match or ``None``**.

    There is deliberately no "closest height" substitution: silently swapping
    the requested resolution for a nearby one is what made the app look like it
    was ignoring the dropdowns. Callers get ``None`` and must tell the user the
    requested format/resolution is not available (see
    :func:`describe_unavailable`).
    """
    best = info.get("best") or _option_best()
    res = normalize_resolution(resolution)
    cid = (codec or "best").strip().lower()

    if cid in ("", "best"):
        if res == "best":
            return best
        height = int(res)
        # "Best (any)" is a *cap*, so at least one stream must be within it —
        # otherwise yt-dlp would quietly resolve to something lower.
        if not any(h <= height for h in _available_heights(info)):
            return None
        return _option_best_height(height)

    fam = info.get("matrix", {}).get(cid) or {}
    if not fam:
        # Not a single stream of this codec: nothing to serve, and inventing a
        # synthetic ``bestvideo[vcodec^=…]`` merge would only produce a file
        # that does not match what the user asked for.
        return None

    if res == "best":
        # Highest height this codec actually serves.
        height = max(int(h) for h in fam)
        opt = dict(fam[height])
        opt["label"] = f"Best {_CODEC_LABEL.get(cid, cid.upper())} ({height}p)"
        return opt

    try:
        requested = int(res)
    except ValueError:
        return None
    return fam.get(requested)


def describe_unavailable(info: dict, codec: str, resolution) -> str:
    """Explain why a (codec, resolution) pair cannot be downloaded.

    Returns ``""`` when the pair *is* available. Otherwise the message names
    the codec/resolution that was asked for and lists what the video does
    serve, so a rejected selection is actionable instead of mysterious.
    """
    res = normalize_resolution(resolution)
    cid = (codec or "best").strip().lower()
    codec_label = ("any codec" if cid in ("", "best")
                   else _CODEC_LABEL.get(cid, cid.upper()))

    if cid in ("", "best"):
        heights = _available_heights(info)
        if res == "best":
            return ""
        if not heights:
            return "This video is not available: yt-dlp reported no video streams."
        if not any(h <= int(res) for h in heights):
            return (f"This video is not available at or below {res}p "
                    f"(the lowest available is {min(heights)}p).")
        return ""

    fam = (info.get("matrix") or {}).get(cid) or {}
    if not fam:
        return (f"This video is not available in {codec_label}: "
                f"no {codec_label} stream was found.")
    if res == "best":
        return ""
    if int(res) in {int(h) for h in fam}:
        return ""
    served = sorted((int(h) for h in fam), reverse=True)
    return (f"This video is not available in {codec_label} at {res}p. "
            f"Available {codec_label} resolutions: "
            + ", ".join(f"{h}p" for h in served) + ".")


def _human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024:
            return f"{num:.0f}{unit}"
        num /= 1024
    return f"{num:.0f}PB"


def inspect_video(url: str) -> dict:
    """Return video metadata + a codec×resolution selection matrix.

    Result shape::

        {
          "title": str,
          "video_id": str,
          "codecs": [ "av1", "vp9", "h264" ],     # available, preference order
          "resolutions": [1080, 720, ...],          # available heights, desc
          "matrix": { cid: { height: {format_selector, filesize, ext,
                                      fps, label, has_audio, merge} } },
          "best": { format_selector, filesize, label, ... },
          "codecs_available": {"av1": bool, "vp9": bool, "h264": bool},
          "has_english_subtitle": bool,
        }
    """
    video_id = extract_video_id(url)
    info = _yt_dlp_json(url)
    title = info.get("title") or ""
    formats = info.get("formats") or []
    codecs, resolutions, matrix, best = _build_matrix(formats)

    codecs_available = {
        "av1": "av1" in codecs,
        "vp9": "vp9" in codecs,
        "h264": "h264" in codecs,
    }

    # Does an English subtitle (manual or auto) exist for this video?
    subs = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}
    has_en = any(k.split("-")[0] == "en" for k in subs) or any(
        k.split("-")[0] == "en" for k in auto_subs
    )

    return {
        "title": title,
        "video_id": video_id,
        "codecs": codecs,
        "resolutions": resolutions,
        "matrix": matrix,
        "best": best,
        "codecs_available": codecs_available,
        "has_english_subtitle": has_en,
    }


# --- Download -----------------------------------------------------------------
_PROGRESS_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_DESTINATION_RE = re.compile(r"\[download\] Destination: (.+)$")


def _partial_files(out_template: str, lines: list[str]) -> list[str]:
    """``.part`` files that this download may have left behind.

    Two complementary strategies, because the exact filename is not always
    known: yt-dlp announces the destination it is writing to (so ``<dest>.part``
    and the per-stream ``<dest>.f<id>.part`` variants are precise matches), and
    -- failing that -- any sufficiently old ``.part`` in the output directory
    is stale by definition and safe to sweep.
    """
    found: set[str] = set()
    for line in lines:
        m = _DESTINATION_RE.search(line)
        if not m:
            continue
        dest = m.group(1).strip()
        if not dest:
            continue
        for cand in [dest + ".part", *glob.glob(dest + ".f*.part")]:
            if os.path.isfile(cand):
                found.add(cand)
    directory = os.path.dirname(os.path.abspath(out_template)) or "."
    cutoff = time.time() - _STALE_PART_AGE
    for cand in glob.glob(os.path.join(directory, "*.part")):
        try:
            if os.path.getmtime(cand) < cutoff:
                found.add(cand)
        except OSError:
            continue
    return sorted(found)


def _is_expired_url_error(tail: str) -> bool:
    """True when yt-dlp was refused while resuming/fetching video data."""
    low = (tail or "").lower()
    return "403" in low and "forbidden" in low


def _translate_ytdlp_error(stderr: str) -> str:
    """Turn common yt-dlp failures into actionable user guidance."""
    low = (stderr or "").lower()
    # Most specific first: a bot/age gate is a different problem from a
    # transport-level 403 even though both can surface as "403".
    if (
        "sign in to confirm" in low
        or ("age" in low and "confirm" in low)
        or ("cookies" in low and ("sign in" in low or "confirm" in low))
    ):
        return (
            "YouTube requires sign-in for this video (age-restricted or "
            "bot-checked). yt-dlp cannot fetch it anonymously."
        )
    if "403" in low and "forbidden" in low:
        return (
            "YouTube rejected the download with HTTP 403 Forbidden. The usual "
            "cause is a partial download left behind by an earlier attempt: "
            "YouTube's stream URLs expire after a few hours, so resuming one "
            "is refused. The app discards the stale partial and retries "
            "automatically — if it still fails, pick a lower resolution or "
            "try again later."
        )
    if "po_token" in low or "yt-dlp-ejs" in low:
        return (
            "YouTube now needs the yt-dlp-ejs helper for full support. "
            "Install it with: pip install -U yt-dlp-ejs"
        )
    # "player" alone is far too broad — yt-dlp logs "Downloading android vr
    # player API JSON" on every successful run.
    if "unable to extract" in low or "nsig" in low or "player response" in low:
        return (
            "yt-dlp could not read this video — its extractor is likely "
            "outdated for YouTube's latest changes. Update it: "
            "pip install -U yt-dlp"
        )
    if "video unavailable" in low or "private video" in low:
        return "This video is unavailable or private."
    if "is not a valid url" in low or "unsupported url" in low:
        return "That does not look like a supported video URL."
    return ""


def _run_yt_dlp(
    cmd: list[str],
    progress_cb=None,
    percent_cb=None,
    proc_ref: dict | None = None,
    cancel_check=None,
) -> int:
    """Run yt-dlp, streaming its output lines to ``progress_cb``.

    ``--newline`` is passed so progress updates arrive as separate lines; the
    percentage is parsed out of them and reported via ``percent_cb`` (0-100
    int). When ``percent_cb`` is given, transient progress ticks are *not*
    forwarded to ``progress_cb`` (keeps the log readable).

    ``proc_ref`` (if given) receives the running ``Popen`` under ``"proc"`` so
    the caller can terminate the download. ``cancel_check`` is polled per
    output line — once it returns True the process is terminated and the loop
    exits early.

    Frozen builds have no subprocess to terminate, so the same contract is met
    by :mod:`src.ytdlp`: the abort is raised inside yt-dlp's own output write
    and reported as a non-zero exit code.
    """
    env = os.environ.copy()
    ffmpeg = _ffmpeg_exe()
    if ffmpeg:
        env["PATH"] = os.path.dirname(ffmpeg) + os.pathsep + env.get("PATH", "")
        cmd += ["--ffmpeg-location", os.path.dirname(ffmpeg)]
    cmd += ["--newline"]
    # Video-only and audio-only parts are fetched sequentially; a combined
    # "[Merger]" stage follows. Tag each line with the stage it belongs to so
    # the UI can report which part is downloading instead of showing a
    # progress bar that jumps back to 0% mid-run.
    stage = {"name": "video"}

    def _tagged(line: str) -> str:
        if line.startswith("[info]") or line.startswith("[download]"):
            low = line.lower()
            if "destination" in low:
                if stage["name"] != "video":
                    stage["name"] = "audio"
                return f"[{stage['name']}] {line}"
        return line

    def on_line(raw: str) -> bool:
        text = _tagged(raw)
        m = _PROGRESS_RE.search(text)
        if m:
            if percent_cb is not None:
                try:
                    percent_cb(max(0, min(100, int(float(m.group(1))))))
                except ValueError:
                    pass
                return True  # transient tick — not worth a log line
        if progress_cb:
            progress_cb(text)
        return True

    return run_ytdlp(
        cmd,
        on_line=on_line if (progress_cb or percent_cb) else None,
        cancel_check=cancel_check,
        proc_ref=proc_ref,
        env=env,
    )


def _resolve_output_path(lines: list[str], fallback_base: str | None) -> str:
    """Best-effort extraction of the final downloaded file path from yt-dlp logs."""
    merged = None
    last_dest = None
    for line in lines:
        m = re.search(r'Merging formats into "(.+?)"', line)
        if m:
            merged = m.group(1).strip()
        m = re.search(r"\[download\] Destination: (.+)$", line)
        if m:
            last_dest = m.group(1).strip()
    path = merged or last_dest
    if path and os.path.exists(path):
        return path
    if fallback_base:
        # Glob for the produced file next to the base name.
        base = os.path.splitext(fallback_base)[0]
        if os.path.isdir(os.path.dirname(base) or "."):
            for cand in sorted(
                os.listdir(os.path.dirname(base) or "."),
                key=lambda n: os.path.getmtime(os.path.join(os.path.dirname(base) or ".", n)),
                reverse=True,
            ):
                full = os.path.join(os.path.dirname(base) or ".", cand)
                if full.startswith(base) and os.path.isfile(full):
                    return full
    return path or ""


# ffprobe codec names -> our short codec ids (for post-download verification).
_FFPROBE_FAMILY = {
    "h264": "h264", "avc1": "h264",
    "av1": "av1", "av01": "av1",
    "vp9": "vp9", "vp09": "vp9",
    "hevc": "h265", "h265": "h265",
    "mpeg4": "mpeg4",
}


def _ffprobe_exe() -> str | None:
    """Locate ffprobe: next to the ffmpeg we already resolved, else on PATH."""
    ffmpeg = _ffmpeg_exe()
    if ffmpeg:
        sibling = os.path.join(
            os.path.dirname(os.path.abspath(ffmpeg)),
            "ffprobe.exe" if os.name == "nt" else "ffprobe",
        )
        if os.path.isfile(sibling):
            return sibling
    return shutil.which("ffprobe")


def _run_probe(exe: str, args: list[str], timeout: int = 30):
    """Run a probe binary, returning the completed process or ``None``."""
    try:
        return subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                           if os.name == "nt" else 0),
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


# "Stream #0:0(und): Video: h264 (High) (avc1 / 0x31637661), yuv420p, 640x360"
_FFMPEG_STREAM_RE = re.compile(
    r"Stream\s+#\d+:\d+(?:\([^)]*\))?:\s*Video:\s*([A-Za-z0-9_.-]+)"
    r".*?\b(\d{2,5})x(\d{2,5})\b",
    re.IGNORECASE,
)


def _probe_via_ffprobe(exe: str, path: str) -> dict | None:
    proc = _run_probe(exe, ["-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=codec_name,height,width",
                            "-of", "json", path])
    if proc is None or proc.returncode != 0:
        return None
    try:
        streams = (json.loads(proc.stdout or "{}") or {}).get("streams") or []
    except ValueError:
        return None
    if not streams:
        return None
    stream = streams[0] or {}
    name = str(stream.get("codec_name") or "").strip().lower()
    try:
        height = int(stream.get("height") or 0)
        width = int(stream.get("width") or 0)
    except (TypeError, ValueError):
        height = width = 0
    return _probe_result(name, width, height)


def _probe_via_ffmpeg(exe: str, path: str) -> dict | None:
    """Fall back to plain ``ffmpeg -i`` when ffprobe is absent.

    Most installs (notably ``imageio_ffmpeg``, which this app already depends
    on for merging) ship ``ffmpeg`` **without** ``ffprobe``. Without this the
    post-download check would silently never run. ``ffmpeg -i`` with no output
    file exits non-zero by design, so the return code is deliberately ignored —
    the stream listing is written to stderr either way.
    """
    proc = _run_probe(exe, ["-hide_banner", "-i", path])
    if proc is None:
        return None
    match = _FFMPEG_STREAM_RE.search(proc.stderr or "")
    if not match:
        return None
    name = match.group(1).strip().lower()
    try:
        width, height = int(match.group(2)), int(match.group(3))
    except (TypeError, ValueError):
        width = height = 0
    return _probe_result(name, width, height)


def _probe_result(name: str, width: int, height: int) -> dict:
    return {
        "codec": _FFPROBE_FAMILY.get(name, name),
        "codec_name": name,
        "height": height,
        "width": width,
    }


def probe_video_file(path: str) -> dict | None:
    """Best-effort codec + height of an already downloaded file.

    Returns ``{"codec": <our codec id>, "codec_name": str, "height": int,
    "width": int}`` or ``None`` when the file cannot be inspected (no usable
    ffmpeg/ffprobe, missing file, unreadable stream). Never raises: this is a
    *verification* step, and an unavailable probe must not fail an otherwise
    good download.

    ffprobe is tried first; if it is missing we fall back to ``ffmpeg -i``.
    """
    if not path or not os.path.isfile(path):
        return None
    exe = _ffprobe_exe()
    if exe:
        found = _probe_via_ffprobe(exe, path)
        if found:
            return found
    ffmpeg = _ffmpeg_exe()
    if ffmpeg:
        found = _probe_via_ffmpeg(ffmpeg, path)
        if found:
            return found
    return None


def download_video(
    url: str,
    format_selector: str,
    out_template: str,
    progress_cb=None,
    percent_cb=None,
    proc_ref: dict | None = None,
    cancel_check=None,
) -> str:
    """Download a video using ``yt-dlp`` with the given format selector.

    ``out_template`` is a yt-dlp ``-o`` template (without extension for merges,
    or with a fixed ext for combined formats). ``percent_cb`` receives the
    download percentage (0-100 int) as it progresses; ``cancel_check`` aborts
    the download when it returns True. Returns the final file path.

    A ``403 Forbidden`` while fetching video data is almost always an expired
    stream URL behind a leftover ``.part`` file, so it is retried once from a
    clean slate before being reported as a failure.
    """
    cmd = _yt_dlp_cmd() + [
        "--no-warnings",
        "--no-playlist",
        "--concurrent-fragments", "4",
        *_RESILIENCE_FLAGS,
        "--throttled-rate", _THROTTLED_RATE,
        "-f",
        format_selector,
        "-o",
        out_template,
        url,
    ]
    lines: list[str] = []
    rc = 0
    for attempt in range(_MAX_DOWNLOAD_ATTEMPTS):
        lines = []
        rc = _run_yt_dlp(
            cmd,
            progress_cb=lambda line: (lines.append(line), progress_cb and progress_cb(line)),
            percent_cb=percent_cb,
            proc_ref=proc_ref,
            cancel_check=cancel_check,
        )
        if rc == 0 or (cancel_check is not None and cancel_check()):
            break
        if attempt == _MAX_DOWNLOAD_ATTEMPTS - 1:
            break
        tail = "\n".join(lines[-8:]).strip()
        stale = _partial_files(out_template, lines)
        if not _is_expired_url_error(tail) or not stale:
            break
        # The URL behind the partial has expired: keeping it would only
        # reproduce the 403, so start over. Only reached after a failure, so
        # no in-progress download can lose data here.
        for path in stale:
            try:
                os.remove(path)
            except OSError:
                pass
        if percent_cb is not None:
            percent_cb(0)
        if progress_cb:
            progress_cb(
                "[warn] Stale partial download removed — YouTube stream URLs "
                "expire after a few hours, so the old progress could not be "
                "resumed. Restarting this download from the beginning…"
            )

    if rc != 0:
        if cancel_check is not None and cancel_check():
            raise RuntimeError("Video download canceled.")
        tail = "\n".join(lines[-8:]).strip()
        hint = _translate_ytdlp_error(tail)
        msg = "Video download failed:\n" + (tail or f"exit code {rc}")
        if hint:
            msg += f"\n\n{hint}"
        raise RuntimeError(msg)

    base = os.path.splitext(out_template)[0]
    return _resolve_output_path(lines, base)


def download_subtitle(
    url: str,
    lang: str = "en",
    out_template_base: str = "",
    progress_cb=None,
    proc_ref: dict | None = None,
    cancel_check=None,
) -> str:
    """Download an English subtitle track if one exists.

    Tries the manual (``--write-subs``) track first, then falls back to the
    auto-generated (``--write-auto-subs``) track. Returns the subtitle file path
    or raises RuntimeError if no English track is available.
    """
    # Candidate filenames yt-dlp writes for this language.
    base = os.path.splitext(out_template_base)[0]
    exts = ("srt", "vtt")
    candidates = [
        f"{base}.{lang}.{ext}" for ext in exts
    ]
    # Auto-generated tracks sometimes use a suffix; check broadly too.
    candidates += [f"{base}.{lang}-*.{ext}" for ext in exts]

    def _already_present() -> str:
        for cand in candidates:
            if "*" in cand:
                import glob

                matches = glob.glob(cand)
                if matches:
                    return sorted(matches, key=os.path.getmtime)[-1]
            elif os.path.exists(cand):
                return cand
        return ""

    found = _already_present()
    if found:
        return found

    if not yt_dlp_available():
        # A frozen build has no "yt-dlp" on PATH; it runs the bundled copy
        # in-process instead, so only a genuinely missing yt-dlp fails here.
        raise RuntimeError(_YTDLP_HINT)

    attempts = [
        _yt_dlp_cmd() + ["--no-warnings", "--no-playlist", "--skip-download",
         *_RESILIENCE_FLAGS,
         "--sub-langs", lang, "--sub-format", "srt/best", "--write-subs",
         "-o", out_template_base, url],
        _yt_dlp_cmd() + ["--no-warnings", "--no-playlist", "--skip-download",
         *_RESILIENCE_FLAGS,
         "--sub-langs", lang, "--sub-format", "srt/best", "--write-auto-subs",
         "-o", out_template_base, url],
    ]

    lines: list[str] = []
    last_error = ""
    for cmd in attempts:
        lines = []
        # The exit code is deliberately ignored: success is decided by the
        # subtitle file actually appearing on disk (_already_present), which
        # also makes a re-run reuse a track fetched earlier.
        _run_yt_dlp(
            cmd,
            progress_cb=lambda line: (lines.append(line), progress_cb and progress_cb(line)),
            proc_ref=proc_ref,
            cancel_check=cancel_check,
        )
        found = _already_present()
        if found:
            return found
        last_error = "\n".join(lines[-6:]).strip()

    if cancel_check is not None and cancel_check():
        raise RuntimeError("Subtitle download canceled.")
    raise RuntimeError(
        f"No English subtitle ({lang}) is available for this video."
        + (("\n" + last_error) if last_error else "")
    )
