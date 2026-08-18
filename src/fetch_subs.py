"""Fetch a YouTube video's original-language subtitles.

Strategy:
  1. Extract the video id from the URL.
  2. Ask yt-dlp for the video title (used for the output filename) and
     YouTube's declared original language code.
  3. Use youtube-transcript-api to resolve the original-language track:
     manual subtitles preferred, auto-generated captions as fallback.
  4. The output filename uses YouTube's English-localized title (hl=en),
     falling back to the original title when no English title exists.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request

from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

from .srt_io import Cue

# Hide console windows spawned by subprocess on Windows.
_SUBPROCESS_CREATION_FLAGS = 0
if os.name == "nt":
    _SUBPROCESS_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

# Public web-client Innertube key YouTube ships in its pages; used only to ask
# for the English-localized title (hl=en). If it ever stops working, the code
# falls back to the original title.
_INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcLSE"

_URL_PATTERNS = [
    r"(?:youtube\.com/watch\?(?:[^&]*&)*v=)([\w-]{11})",
    r"(?:youtu\.be/)([\w-]{11})",
    r"(?:youtube\.com/shorts/)([\w-]{11})",
    r"(?:youtube\.com/embed/)([\w-]{11})",
]


def extract_video_id(url: str) -> str:
    for pattern in _URL_PATTERNS:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    raise ValueError(
        f"Could not parse a YouTube video id from: {url!r}. "
        f"Expected a watch, youtu.be, shorts, or embed URL."
    )


def _yt_dlp_metadata(url: str) -> tuple[str | None, str | None]:
    """Return (title, language_code) via yt-dlp, or (None, None) on failure."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--no-warnings", "--print", "%(title)s|%(language)s", url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=True,
            creationflags=_SUBPROCESS_CREATION_FLAGS,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None, None

    line = result.stdout.strip()
    if "|" not in line:
        return (line or None), None
    title, lang = line.rsplit("|", 1)
    title = title.strip() or None
    lang = lang.strip().lower() or None
    if lang in (None, "none", "und"):
        lang = None
    return title, lang


def _fetch_english_title(video_id: str) -> str | None:
    """Best-effort: YouTube's English-localized title (hl=en).

    Returns the title YouTube shows to an English-locale viewer, or None if it
    can't be retrieved (caller falls back to the original title).
    """
    api = "https://www.youtube.com/youtubei/v1/player?key=" + _INNERTUBE_KEY
    payload = {
        "videoId": video_id,
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20240101",
                "hl": "en",
                "gl": "US",
            }
        },
    }
    try:
        req = urllib.request.Request(
            api,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
        title = (
            data.get("microformat", {})
            .get("playerMicroformatRenderer", {})
            .get("title", {})
        )
        if isinstance(title, dict):
            title = title.get("simpleText") or title.get("runs", [{}])[0].get("text")
        return title.strip() if isinstance(title, str) and title.strip() else None
    except Exception:
        return None


def _resolve_transcript(transcript_list, lang: str | None):
    """Pick the original-language transcript (manual preferred, auto fallback).

    ``transcript_list`` is an already-listed ``TranscriptList``; ``lang`` is an
    optional original-language hint from the video metadata.
    """
    # Prefer the original language when we know it.
    if lang:
        try:
            return transcript_list.find_manually_created_transcript([lang])
        except NoTranscriptFound:
            pass
        try:
            return transcript_list.find_generated_transcript([lang])
        except NoTranscriptFound:
            pass

    # Fallback: first manual track, else first auto-generated track.
    for transcript in transcript_list:  # iterates manual, then generated
        return transcript

    return None


def _resolve_english_transcript(transcript_list):
    """Return an English track (manual preferred, then generated), or None.

    Some videos ship an English subtitle/manual caption even when the narration
    is in another language. When one exists we use it verbatim instead of running
    the transcribe+translate pipeline — it is the platform's own translation.
    """
    en_codes = ["en", "en-US", "en-GB", "en-CA", "en-AU"]
    try:
        return transcript_list.find_manually_created_transcript(en_codes)
    except NoTranscriptFound:
        pass
    try:
        return transcript_list.find_generated_transcript(en_codes)
    except NoTranscriptFound:
        pass
    return None


def _snippets_to_cues(snippets) -> list[Cue]:
    """Convert a fetched transcript (or snippet container) into Cue objects."""
    cues: list[Cue] = []
    for s in snippets:
        text = (s.text or "").strip()
        if not text:
            continue
        start = float(s.start)
        duration = float(getattr(s, "duration", 0) or 0)
        cues.append(Cue(start=start, end=start + duration, text=text))
    return cues


def fetch_original_subtitles(url: str) -> tuple[list[Cue], str | None, str | None]:
    """Fetch subtitles for a YouTube URL, preferring an existing English track.

    Returns (cues, english_video_title, source_language_code). The title used for
    the output filename is YouTube's English-localized title, falling back to the
    original title when no English title exists. Raises RuntimeError/ValueError
    with an actionable message on failure.

    English-first: if YouTube already provides an English subtitle (manual or
    auto-generated), we return those cues with source_language_code ``"en"`` so the
    caller writes them as-is and skips translation. Only when no English track
    exists do we fall back to the video's original-language track, which the caller
    then translates.
    """
    video_id = extract_video_id(url)
    title, lang = _yt_dlp_metadata(url)

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
    except Exception as exc:  # network / unavailable / disabled errors
        raise RuntimeError(f"Could not retrieve subtitles: {exc}") from exc

    def _english_title() -> str | None:
        return _fetch_english_title(video_id) or title

    # 1) Prefer the existing English subtitle (YouTube's own translation).
    english = _resolve_english_transcript(transcript_list)
    if english is not None:
        cues = _snippets_to_cues(english.fetch())
        return cues, _english_title(), "en"

    # 2) No English track: fall back to the video's original language, which the
    #    caller translates into English.
    transcript = _resolve_transcript(transcript_list, lang)
    if transcript is None:
        raise RuntimeError(
            "No subtitles (manual or auto-generated) are available for this video."
        )

    snippets = transcript.fetch()
    source_lang = getattr(snippets, "language_code", None) or lang

    cues = _snippets_to_cues(snippets)
    if not cues:
        raise RuntimeError("Retrieved subtitles were empty for this video.")

    return cues, _english_title(), source_lang
