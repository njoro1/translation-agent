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

import json
import os
import re
import shutil
import subprocess
import sys

from .fetch_subs import _SUBPROCESS_CREATION_FLAGS, extract_video_id

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


def _codec_family(vcodec: str | None) -> str | None:
    """Return the codec family label for a yt-dlp ``vcodec`` string."""
    if not vcodec or vcodec == "none":
        return None
    low = vcodec.lower()
    for key, label in _CODEC_FAMILIES.items():
        if low.startswith(key) or key in low:
            return label
    return vcodec.split(".")[0] or vcodec


def _ffmpeg_exe() -> str | None:
    """Locate ffmpeg (needed to merge separate video+audio streams).

    Mirrors the resolution strategy used by ``src.local_asr`` so behaviour is
    consistent across the app.
    """
    env = os.environ.get("FFMPEG_BIN")
    if env and shutil.which(env):
        return env
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    exe = shutil.which("ffmpeg")
    return exe


# --- yt-dlp resolution --------------------------------------------------------
def _yt_dlp_cmd() -> list[str]:
    """Resolve the yt-dlp executable to invoke.

    Order: the ``YT_DLP_BIN`` environment variable (absolute path or command
    name), ``yt-dlp`` on PATH, then ``python -m yt_dlp`` — the last fallback
    keeps the GUI usable in bundled environments where the ``yt-dlp`` script
    exists as a module but no launcher landed on PATH.
    """
    env = os.environ.get("YT_DLP_BIN", "").strip()
    if env:
        # Accept "C:\\tools\\yt-dlp.exe" as well as "C:\\tools yt-dlp …"-style
        # pre-quoted strings from users who know what they are doing.
        if shutil.which(env) or os.path.exists(env):
            return [env]
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    return [sys.executable, "-m", "yt_dlp"]


_YTDLP_HINT = (
    "yt-dlp is not installed. Install it with: pip install yt-dlp"
)


# --- Inspection ---------------------------------------------------------------
def _yt_dlp_json(url: str) -> dict:
    """Run ``yt-dlp --dump-json`` and return the parsed info dict."""
    try:
        result = subprocess.run(
            _yt_dlp_cmd() + ["--no-warnings", "--no-playlist", "--dump-json", url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=True,
            creationflags=_SUBPROCESS_CREATION_FLAGS,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(_YTDLP_HINT) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Timed out inspecting the video with yt-dlp.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (getattr(exc, "stderr", "") or "").strip()
        raise RuntimeError(
            "Could not inspect the video with yt-dlp: "
            + (stderr or str(exc) or "unknown error")
        ) from exc

    try:
        return json.loads(result.stdout)
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


def _merge_option(cid: str, height: int | None = None) -> dict:
    prefix = _CODEC_PREFIX.get(cid, "")
    height_clause = f"[height={height}]" if height else ""
    # Every fallback in the chain must stay codec- (and height-) constrained: a
    # bare ``/best`` would silently download a *different* codec or resolution
    # than the user picked when the preferred alternative is unavailable.
    cap_clause = f"[height<={height}]" if height else ""
    codec_clause = f"[vcodec^={prefix}]" if prefix else ""
    fallback = f"bestvideo{codec_clause}{cap_clause}/best{codec_clause}{cap_clause}"
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
        "format_selector": f"{format_id}+bestaudio/{format_id}",
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
        "format_selector": f"bestvideo{cap}+bestaudio/best{cap}",
    }


def resolve_video_option(info: dict, codec: str, resolution) -> dict | None:
    """Pick the option dict for a (codec, resolution) selection.

    ``codec`` is one of ``"av1"``/``"vp9"``/``"h264"``/``"best"``; ``resolution``
    is an int height or the string ``"best"``. Returns the matching option dict
    (with ``format_selector`` + ``filesize``) or ``None`` if unavailable.

    The returned selector always honours *both* picks:

      * ``codec="best"`` + a height → any codec, but capped at that height.
      * a specific codec + a height it does not serve → the closest height it
        does serve (largest ≤ requested, else the smallest available), marked
        in the label. Never a different codec, never an unconstrained
        ``/best`` fallback that would download whatever is globally best.
    """
    best = info.get("best") or _option_best()
    if codec == "best":
        if resolution in ("best", None):
            return best
        try:
            return _option_best_height(int(resolution))
        except (TypeError, ValueError):
            return best

    fam = info.get("matrix", {}).get(codec, {})
    if not fam:
        # No stream of this codec at all: a best-of-codec merge, still
        # constrained to the requested height when one was given.
        if codec not in _CODEC_PREFIX:
            return None
        height = None if resolution in ("best", None) else int(resolution)
        return _merge_option(codec, height)

    if resolution in ("best", None):
        # Highest available resolution for this codec.
        height = max(int(h) for h in fam.keys())
        return fam[height]

    try:
        requested = int(resolution)
    except (TypeError, ValueError):
        height = max(int(h) for h in fam.keys())
        return fam[height]

    if requested in fam:
        return fam[requested]
    # Requested height not served by this codec: fall back to the closest
    # height that *is* served — prefer the largest ≤ requested, otherwise the
    # smallest available. Both the codec and "as close as possible" are kept.
    available = sorted(int(h) for h in fam.keys())
    lower = [h for h in available if h <= requested]
    height = max(lower) if lower else min(available)
    opt = dict(fam[height])
    base_label = opt.get("label") or f"{height}p"
    opt["label"] = f"{base_label} (closest to {requested}p)"
    return opt


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


def _translate_ytdlp_error(stderr: str) -> str:
    """Turn common yt-dlp failures into actionable user guidance."""
    low = (stderr or "").lower()
    if "sign in to confirm" in low or "cookies" in low or "age" in low and "confirm" in low:
        return (
            "YouTube requires sign-in for this video (age-restricted or "
            "bot-checked). yt-dlp cannot fetch it anonymously."
        )
    if "unable to extract" in low or "player" in low:
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

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_SUBPROCESS_CREATION_FLAGS,
        env=env,
    )
    if proc_ref is not None:
        proc_ref["proc"] = proc
    if proc.stdout is not None:
        for line in proc.stdout:
            if cancel_check is not None and cancel_check():
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break
            text = _tagged(line.rstrip("\n"))
            m = _PROGRESS_RE.search(text)
            if m:
                if percent_cb is not None:
                    try:
                        percent_cb(max(0, min(100, int(float(m.group(1))))))
                    except ValueError:
                        pass
                    continue  # transient tick — not worth a log line
            if progress_cb:
                progress_cb(text)
    return proc.wait()


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
    """
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--no-playlist",
        "--concurrent-fragments", "4",
        "-f",
        format_selector,
        "-o",
        out_template,
        url,
    ]
    lines: list[str] = []
    rc = _run_yt_dlp(
        cmd,
        progress_cb=lambda line: (lines.append(line), progress_cb and progress_cb(line)),
        percent_cb=percent_cb,
        proc_ref=proc_ref,
        cancel_check=cancel_check,
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

    if shutil.which("yt-dlp") is None and not os.path.exists(
        os.environ.get("YT_DLP_BIN", "").strip()
    ):
        raise RuntimeError(_YTDLP_HINT)

    attempts = [
        _yt_dlp_cmd() + ["--no-warnings", "--no-playlist", "--skip-download",
         "--sub-langs", lang, "--sub-format", "srt/best", "--write-subs",
         "-o", out_template_base, url],
        _yt_dlp_cmd() + ["--no-warnings", "--no-playlist", "--skip-download",
         "--sub-langs", lang, "--sub-format", "srt/best", "--write-auto-subs",
         "-o", out_template_base, url],
    ]

    lines: list[str] = []
    last_error = ""
    for cmd in attempts:
        lines = []
        rc = _run_yt_dlp(
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
