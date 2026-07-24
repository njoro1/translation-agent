"""SRT (SubRip) reading/writing helpers and filename sanitization."""
from __future__ import annotations

import re
from dataclasses import dataclass

# Characters unsafe in Windows/Unix filenames.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class Cue:
    start: float  # seconds
    end: float  # seconds
    text: str


def sanitize_filename(title: str) -> str:
    """Turn a video title into a safe, reasonably short filename stem."""
    cleaned = _UNSAFE.sub(" ", title).strip()
    # Collapse runs of whitespace and dots.
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    cleaned = cleaned.strip(". ").strip()
    # Bound the length so we don't blow past filesystem limits.
    if len(cleaned) > 180:
        cleaned = cleaned[:180].rsplit(" ", 1)[0].strip()
    return cleaned or "subtitles"


def _format_timestamp(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def write_srt(cues: list[Cue], path: str) -> None:
    """Write cues to an SRT file at `path`."""
    with open(path, "w", encoding="utf-8") as f:
        for i, cue in enumerate(cues, start=1):
            f.write(f"{i}\n")
            f.write(f"{_format_timestamp(cue.start)} --> {_format_timestamp(cue.end)}\n")
            f.write(cue.text.strip() + "\n\n")
