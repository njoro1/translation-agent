"""Transcribe a local video/audio file with no subtitles into timed cues.

Strategy (SenseVoiceSmall GGUF CPU runtime — no Python/GPU at runtime):
  1. Extract audio to a 16 kHz mono WAV with ffmpeg (any input container works).
  2. `llama-funasr-vad` produces per-speech-segment timestamps ([start_ms, end_ms]).
  3. `llama-funasr-sensevoice --vad --keep-tags` transcribes the whole file.
     SenseVoice prepends a `<lang><emotion><event><itn>` tag group per VAD segment,
     and `--keep-tags` keeps them, so the number of tag groups equals the number of
     segments. We split the concatenated text on those groups and verify the count
     against the VAD pass; on any mismatch we fall back to transcribing each VAD
     segment individually (robust, slightly slower).
  4. Return (cues, title, source_lang) in the SAME shape as
     `fetch_original_subtitles`, so the shared translate->SRT pipeline is reused.

This module only shells out to ffmpeg and the FunASR binaries — no heavy pip
dependencies — which keeps the YouTube path's install untouched.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

from .srt_io import Cue, sanitize_filename

# SenseVoice language tags -> human-readable source language for the translator's
# system prompt. Unknown tags map to None (prompt then says "the video's original
# language").
_LANG_MAP = {
    "zh": "Chinese",
    "yue": "Cantonese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
}

# One SenseVoice tag group: four `<|token|>` markers (lang, emotion, event, itn).
_TAG_GROUP = re.compile(
    r"<\|[a-zA-Z]+\|><\|[a-zA-Z]+\|><\|[a-zA-Z]+\|><\|[a-zA-Z]+\|>"
)

# VAD output looks like `[123, 456]` (start_ms, end_ms) per segment. Tolerant of
# floats/whitespace; tune the regex once the real binary's stdout is observed.
_VAD_PAIR = re.compile(r"\[\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\]")


def resolve_asr_config(args, environ: dict | None = None) -> tuple[str, str, str, str]:
    """Resolve ASR binary/model paths from CLI flags, then env vars, then defaults.

    Returns (sensevoice_bin, vad_bin, model_path, vad_model_path).
    """
    environ = environ if environ is not None else os.environ

    def _pick(flag_attr: str, env_key: str, default: str) -> str:
        val = getattr(args, flag_attr, None)
        if val:
            return val
        val = environ.get(env_key)
        if val:
            return val
        return default

    sensevoice_bin = _pick("asr_bin", "FUNASR_SENSEVOICE_BIN", "llama-funasr-sensevoice")
    vad_bin = _pick("asr_vad_bin", "FUNASR_VAD_BIN", "llama-funasr-vad")
    model_path = _pick("asr_model", "FUNASR_MODEL", "./gguf/sensevoice-small-q8.gguf")
    vad_model_path = _pick("asr_vad_model", "FUNASR_VAD_MODEL", "./gguf/fsmn-vad.gguf")
    return sensevoice_bin, vad_bin, model_path, vad_model_path


def transcribe_local_file(
    path: str,
    *,
    sensevoice_bin: str,
    vad_bin: str,
    model_path: str,
    vad_model_path: str,
    language: str = "auto",
    keep_tags: bool = True,
) -> tuple[list[Cue], str | None, str | None]:
    """Transcribe a local video/audio file into timed cues.

    Returns (cues, title, source_lang). `title` is derived from the filename stem
    (there is no YouTube title for a local file). `source_lang` is a human-readable
    language name when detectable, else None.

    Raises RuntimeError with an actionable message on missing tools, conversion
    failure, or empty results.
    """
    if not os.path.exists(path):
        raise RuntimeError(f"Input file not found: {path}")

    wav = _extract_audio(path)
    try:
        segments = _run_vad(vad_bin, vad_model_path, wav)
        if not segments:
            raise RuntimeError(
                "Voice activity detection found no speech in this audio. "
                "Check the audio track / format."
            )

        text = _run_sensevoice(
            sensevoice_bin, model_path, vad_model_path, wav, language, keep_tags
        )
        pieces = _split_text(text, keep_tags)

        if keep_tags and pieces and len(pieces) == len(segments):
            cues = _zip_segments(segments, pieces)
            source_lang = _detect_lang(pieces)
        else:
            # Count mismatch (or no tags): fall back to per-segment transcription so
            # each piece of text is bound to its own known time range.
            if keep_tags:
                print(
                    "  [warn] ASR segment count != VAD segment count; "
                    "falling back to per-segment transcription.",
                    flush=True,
                )
            cues = _transcribe_per_segment(
                sensevoice_bin, model_path, vad_model_path, wav, segments, language
            )
            source_lang = _LANG_MAP.get(language) if language != "auto" else None
    finally:
        _safe_unlink(wav)

    cues = [c for c in cues if c.text and c.text.strip()]
    if not cues:
        raise RuntimeError("ASR produced no text for this audio.")

    title = sanitize_filename(os.path.splitext(os.path.basename(path))[0]) or None
    return cues, title, source_lang


# --- internals ---------------------------------------------------------------


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _extract_audio(path: str) -> str:
    """Convert any media file to a 16 kHz mono 16-bit WAV; return its temp path."""
    if not _has_ffmpeg():
        raise RuntimeError(
            "ffmpeg is required to extract audio from local files but was not "
            "found on PATH. Install ffmpeg (e.g. from ffmpeg.org) and retry."
        )
    wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    cmd = ["ffmpeg", "-y", "-i", path, "-ar", "16000", "-ac", "1",
           "-c:a", "pcm_s16le", wav]
    try:
        subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600, check=True,
        )
    except subprocess.CalledProcessError as exc:
        _safe_unlink(wav)
        raise RuntimeError(
            f"ffmpeg failed to extract audio from {path}: "
            f"{exc.stderr.strip()[:500]}"
        ) from exc
    except subprocess.TimeoutExpired:
        _safe_unlink(wav)
        raise RuntimeError(f"ffmpeg timed out extracting audio from {path}.")
    except FileNotFoundError as exc:  # pragma: no cover - guarded by _has_ffmpeg
        _safe_unlink(wav)
        raise RuntimeError("ffmpeg not found on PATH.") from exc
    return wav


def _run(cmd: list[str], timeout: int | None = None) -> str:
    """Run a FunASR binary, returning stdout. Raises RuntimeError on failure."""
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Could not find binary: {cmd[0]!r}. Download the FunASR GGUF runtime "
            f"and point at it via --asr-bin / FUNASR_SENSEVOICE_BIN (or --asr-vad-bin "
            f"for VAD)."
        ) from exc
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ASR command timed out: {' '.join(cmd)}")
    if res.returncode != 0:
        raise RuntimeError(
            f"ASR command failed ({cmd[0]}): {res.stderr.strip()[:500]}"
        )
    return res.stdout


def _run_vad(vad_bin: str, vad_model_path: str, wav: str) -> list[tuple[float, float]]:
    """Run fsmn-vad and parse [start_ms, end_ms] segment pairs -> (start_s, end_s)."""
    out = _run([vad_bin, "-m", vad_model_path, "-a", wav])
    segments: list[tuple[float, float]] = []
    for m in _VAD_PAIR.finditer(out):
        start = float(m.group(1)) / 1000.0
        end = float(m.group(2)) / 1000.0
        if end > start:
            segments.append((start, end))
    return segments


def _sensevoice_cmd(
    sensevoice_bin: str,
    model_path: str,
    vad_model_path: str,
    wav: str,
    language: str,
    keep_tags: bool,
) -> list[str]:
    cmd = [sensevoice_bin, "-m", model_path, "--vad", vad_model_path, "-a", wav]
    if language and language != "auto":
        cmd += ["--lang", language]
    if keep_tags:
        cmd += ["--keep-tags"]
    return cmd


def _run_sensevoice(
    sensevoice_bin: str,
    model_path: str,
    vad_model_path: str,
    wav: str,
    language: str,
    keep_tags: bool,
) -> str:
    return _run(
        _sensevoice_cmd(sensevoice_bin, model_path, vad_model_path, wav, language, keep_tags)
    )


def _split_text(text: str, keep_tags: bool) -> list[tuple[str | None, str]]:
    """Split concatenated ASR text into (lang_tag, text) per segment.

    With keep_tags, SenseVoice emits a 4-token tag group per segment; we split on
    those. Without tags (or if no groups found) the whole blob is one piece.
    """
    if not keep_tags:
        return [(None, text.strip())]
    matches = list(_TAG_GROUP.finditer(text))
    if not matches:
        return [(None, text.strip())]

    pieces: list[tuple[str | None, str]] = []
    for i, m in enumerate(matches):
        lang = _lang_from_group(m.group(0))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        seg_text = text[start:end].strip()
        if i == 0:
            leading = text[: m.start()].strip()
            if leading:
                seg_text = f"{leading} {seg_text}".strip() if seg_text else leading
        pieces.append((lang, seg_text))
    return pieces


def _lang_from_group(group: str) -> str | None:
    """Extract the first token (language) from a 4-tag group like `<|zh|><|..|>`."""
    token = group.split("|", 2)[1] if "|" in group else ""
    return token or None


def _detect_lang(pieces: list[tuple[str | None, str]]) -> str | None:
    """Majority language tag among pieces -> human-readable name (or None)."""
    from collections import Counter

    counts = Counter(lang for lang, _ in pieces if lang)
    if not counts:
        return None
    top = counts.most_common(1)[0][0]
    return _LANG_MAP.get(top)


def _zip_segments(
    segments: list[tuple[float, float]], pieces: list[tuple[str | None, str]]
) -> list[Cue]:
    return [
        Cue(start=s, end=e, text=txt)
        for (s, e), (_, txt) in zip(segments, pieces)
    ]


def _transcribe_per_segment(
    sensevoice_bin: str,
    model_path: str,
    vad_model_path: str,
    wav: str,
    segments: list[tuple[float, float]],
    language: str,
) -> list[Cue]:
    """Fallback: cut each VAD segment and transcribe it standalone (no --vad).

    Guarantees each piece of text is bound to its own known time range, at the cost
    of launching the binary once per segment (model reload overhead).
    """
    cues: list[Cue] = []
    for start, end in segments:
        slice_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        try:
            _cut_segment(wav, start, end, slice_wav)
            cmd = [sensevoice_bin, "-m", model_path, "-a", slice_wav]
            if language and language != "auto":
                cmd += ["--lang", language]
            txt = _run(cmd).strip()
            cues.append(Cue(start=start, end=end, text=txt))
        finally:
            _safe_unlink(slice_wav)
    return cues


def _cut_segment(src_wav: str, start: float, end: float, out_wav: str) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", src_wav,
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", out_wav,
    ]
    try:
        subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120, check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg failed to cut segment {start:.1f}-{end:.1f}s: "
            f"{exc.stderr.strip()[:300]}"
        ) from exc


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
