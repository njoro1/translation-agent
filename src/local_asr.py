"""
Local ASR backend: FunASR + SenseVoiceSmall only.

This module replaces the old whisper.cpp implementation.

Design goals:
- CPU-only.
- No Whisper.
- No PyTorch.
- Produce short subtitle cues instead of large text blocks.
- Use FunASR VAD when possible.
- Use ffmpeg silencedetect as fallback/refinement.
- Split long recognized text into cue-sized pieces.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from .srt_io import Cue
from .batching import is_cjk_language

# Hide console windows spawned by subprocess on Windows.
_SUBPROCESS_CREATION_FLAGS = 0
if os.name == "nt":
    _SUBPROCESS_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


DEFAULT_SENSEVOICE_MODEL = os.path.join("gguf", "sensevoice-small-q8.gguf")
DEFAULT_VAD_MODEL = os.path.join("gguf", "fsmn-vad.gguf")

# A transcript that stops well before the media ends (a long silent tail between
# the last cue and the audio duration) is a strong sign the VAD/ASR run ended
# early. We warn when the uncovered tail exceeds BOTH the absolute floor below
# AND 5% of the whole media — generous enough to never flag natural pauses.
INCOMPLETE_WARN_SECONDS = float(
    os.environ.get("FUNASR_INCOMPLETE_WARN_SECONDS", "8.0")
)
INCOMPLETE_WARN_MEDIA_RATIO = 0.05

_CODE_TO_NAME = {
    "zh": "Chinese",
    "yue": "Cantonese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
}

# File extensions treated as video for the snap-to-keyframe pass. Pure audio
# files (mp3/wav/m4a/flac/ogg...) are skipped.
_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi"}

_SENSEVOICE_LANG_RE = re.compile(r"<\|\s*(zh|en|ja|ko|yue|auto)\s*\|>", re.I)
_TAG_RE = re.compile(r"<\|[^<>|]*\|>")

_TEXT_SEPARATORS = [
    "\n",
    "。",
    "！",
    "？",
    "!",
    "?",
    "；",
    ";",
    "…",
    "，",
    ",",
    "、",
    "：",
    ":",
    "—",
    "–",
    " ",
]

_HELP_CACHE: dict[str, str] = {}


def _run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_SUBPROCESS_CREATION_FLAGS,
    )
    if p.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            f"{cmd}\n\n"
            f"stdout:\n{p.stdout}\n\n"
            f"stderr:\n{p.stderr}"
        )
    return p


def _ffmpeg_exe() -> str:
    env = os.environ.get("FFMPEG_BIN")
    if env and shutil.which(env):
        return env

    env = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if env and shutil.which(env):
        return env

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    exe = shutil.which("ffmpeg")
    if exe:
        return exe

    raise RuntimeError("ffmpeg not found. Set FFMPEG_BIN or install ffmpeg.")


def _funasr_dirs() -> list[Path]:
    dirs = [
        Path("vendor/funasr"),
        Path("vendor/funasr/Release"),
        Path(sys.executable).parent,
        Path(sys.executable).parent / "vendor" / "funasr",
    ]

    if hasattr(sys, "_MEIPASS"):
        dirs.append(Path(sys._MEIPASS) / "vendor" / "funasr")

    return [d for d in dirs if d.is_dir()]


def _find_exe(explicit: str | None, env_var: str, base_name: str) -> str | None:
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return str(p)
        which = shutil.which(explicit)
        if which:
            return which

    env = os.environ.get(env_var)
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return str(p)
        which = shutil.which(env)
        if which:
            return which

    exe_name = base_name + (".exe" if os.name == "nt" else "")

    for d in _funasr_dirs():
        candidate = d / exe_name
        if candidate.is_file():
            return str(candidate)

    which = shutil.which(base_name)
    if which:
        return which

    return None


def _app_model_dirs() -> list[Path]:
    """Folders a GGUF may be dropped into, best-first.

    Mirrors ``backend.bridge._model_search_dirs`` (which cannot be imported
    here without a cycle): the executable's own folder first, so shipping the
    ``.gguf`` files next to ``TranslationAgent.exe`` works, then the ``gguf`` /
    ``models`` subfolders beside it, then a per-user folder for installs where
    the app folder is read-only.
    """
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
    else:
        exe_dir = Path(__file__).resolve().parent.parent
    dirs.extend([exe_dir, exe_dir / "gguf", exe_dir / "models"])

    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or ""
    elif sys.platform == "darwin":
        root = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"
        )
    if root:
        dirs.append(Path(root) / "TranslationAgent" / "gguf")

    if hasattr(sys, "_MEIPASS"):
        dirs.append(Path(sys._MEIPASS))

    return dirs


def _resolve_model(explicit: str | None, env_var: str, default: str) -> str:
    if explicit:
        p = Path(explicit).expanduser()
        if p.exists():
            return str(p)
        return explicit

    env = os.environ.get(env_var)
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return str(p)
        return env

    name = Path(default).name
    candidates = [Path(default), Path("dist") / default]
    for directory in _app_model_dirs():
        candidates.append(directory / name)
        candidates.append(directory / default)

    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / default)

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return default


def _wav_duration(path: Path) -> float:
    with contextlib.closing(wave.open(str(path), "rb")) as w:
        frames = w.getnframes()
        rate = w.getframerate()
        if rate <= 0:
            return 0.0
        return frames / float(rate)


ASR_PREPROCESS_PROFILES = {
    "none": None,
    "basic": "highpass=f=80",
    "loudnorm": "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11:linear=true",
    "denoise": "highpass=f=80,afftdn=nf=-25:tn=true,loudnorm=I=-16:TP=-1.5:LRA=11:linear=true",
}


def _resolve_preprocess_profile(profile: str | None) -> str:
    """Resolve the safe default used when no content preset overrides it."""
    profile = (profile or "auto").strip().lower()
    if profile == "auto":
        return "basic"
    if profile not in ASR_PREPROCESS_PROFILES:
        raise ValueError(
            "Invalid ASR preprocessing profile: "
            f"{profile!r}. Choose auto, none, basic, loudnorm, or denoise."
        )
    return profile


def _preprocess_filter(profile: str) -> str | None:
    return ASR_PREPROCESS_PROFILES[_resolve_preprocess_profile(profile)]


def _extract_wav(media_path: Path, wav_path: Path, profile: str = "basic") -> None:
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(media_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(wav_path),
    ]
    audio_filter = _preprocess_filter(profile)
    if audio_filter:
        cmd[8:8] = ["-af", audio_filter]
    _run(cmd)


def _media_duration(path: Path) -> float:
    """Return a media duration without decoding it; 0 means unavailable."""
    ffprobe = _ffprobe_exe()
    if ffprobe:
        try:
            p = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=60, creationflags=_SUBPROCESS_CREATION_FLAGS,
            )
            if p.returncode == 0:
                return float(p.stdout.strip())
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    try:
        return _wav_duration(path)
    except (OSError, wave.Error):
        return 0.0


def _prepare_asr_audio(media_path: Path, wav_path: Path, profile: str = "auto") -> Path:
    """Extract duration-safe ASR audio, falling back to less processing safely."""
    requested = _resolve_preprocess_profile(profile)
    original_duration = _media_duration(media_path)
    candidates = [requested]
    if requested not in ("basic", "none"):
        candidates.append("basic")
    if "none" not in candidates:
        candidates.append("none")

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            _extract_wav(media_path, wav_path, candidate)
            processed_duration = _wav_duration(wav_path)
            mismatch_ms = abs(processed_duration - original_duration) * 1000
            if original_duration > 0 and mismatch_ms > 50:
                raise RuntimeError(
                    f"duration mismatch {mismatch_ms:.1f} ms exceeds 50 ms"
                )
            if candidate != requested:
                print(
                    f"[asr] WARNING: preprocessing fallback {requested} -> {candidate}",
                    flush=True,
                )
            print(f"[asr] Preprocessing profile: {candidate}", flush=True)
            return wav_path
        except Exception as exc:  # noqa: BLE001 - fallback is intentionally broad
            last_error = exc
            if candidate != candidates[-1]:
                print(
                    f"[asr] WARNING: preprocessing {candidate} failed ({exc}); "
                    "trying fallback.",
                    flush=True,
                )
    raise RuntimeError(f"Could not prepare ASR audio: {last_error}")


def _cut_wav(wav_path: Path, start: float, end: float, out_path: Path) -> None:
    duration = max(0.05, end - start)
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(wav_path),
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-ac", "1",
        "-ar", "16000",
        "-acodec", "pcm_s16le",
        str(out_path),
    ]
    _run(cmd)



def _help_text(exe: str) -> str:
    if exe in _HELP_CACHE:
        return _HELP_CACHE[exe]

    text = ""
    for flag in ("--help", "-h"):
        try:
            p = subprocess.run(
                [exe, flag],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                creationflags=_SUBPROCESS_CREATION_FLAGS,
            )
            candidate = (p.stdout or "") + (p.stderr or "")
            if candidate.strip():
                text = candidate
                break
        except Exception:
            pass

    text = text.lower()
    _HELP_CACHE[exe] = text
    return text


def _detect_output_flag(exe: str, env_name: str) -> str | None:
    env = os.environ.get(env_name) or os.environ.get("FUNASR_OUTPUT_FLAG")
    if env:
        return env

    help_text = _help_text(exe)

    for flag in ("--output-file", "--output", "-of", "-o"):
        if flag in help_text:
            return flag

    return None


def _detect_lang_flag(exe: str) -> str | None:
    help_text = _help_text(exe)

    if "--language" in help_text:
        return "--language"

    if re.search(r"(^|\s)-l(\s|,|$)", help_text):
        return "-l"

    return None


def _detect_keep_tags(exe: str) -> bool:
    return "keep-tags" in _help_text(exe)


def _ffmpeg_silences(
    wav_path: Path,
    duration: float,
    noise_db: float = -35.0,
    min_silence_s: float = 0.20,
) -> list[tuple[float, float]]:
    cmd = [
        _ffmpeg_exe(),
        "-hide_banner",
        "-i", str(wav_path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_s}",
        "-f", "null",
        "-",
    ]

    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
        creationflags=_SUBPROCESS_CREATION_FLAGS,
    )

    output = (p.stderr or "") + (p.stdout or "")

    starts = [
        float(x)
        for x in re.findall(r"silence_start:\s*([0-9]+(?:\.[0-9]+)?)", output)
    ]
    ends = [
        float(x)
        for x in re.findall(r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)", output)
    ]

    silences: list[tuple[float, float]] = []

    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else duration

        s = max(0.0, min(float(s), duration))
        e = max(0.0, min(float(e), duration))

        if e > s:
            silences.append((s, e))

    return silences


def _speech_from_silences(
    silences: list[tuple[float, float]],
    duration: float,
    min_speech_s: float = 0.25,
) -> list[tuple[float, float]]:
    speech: list[tuple[float, float]] = []
    pos = 0.0

    for s, e in silences:
        if s > pos:
            speech.append((pos, s))
        pos = max(pos, e)

    if pos < duration:
        speech.append((pos, duration))

    speech = [(s, e) for s, e in speech if e - s >= min_speech_s]

    if not speech:
        return [(0.0, duration)]

    return speech



def _split_long_segments(
    segments: list[tuple[float, float]],
    silences: list[tuple[float, float]],
    max_segment_s: float,
    min_part_s: float = 1.0,
) -> list[tuple[float, float]]:
    def split(a: float, b: float) -> list[tuple[float, float]]:
        length = b - a

        if length <= max_segment_s or length <= min_part_s * 2:
            return [(a, b)]

        mid = (a + b) / 2.0
        best_point = None
        best_distance = float("inf")

        for ss, se in silences:
            point = (ss + se) / 2.0
            if a + min_part_s <= point <= b - min_part_s:
                distance = abs(point - mid)
                if distance < best_distance:
                    best_distance = distance
                    best_point = point

        if best_point is not None:
            return split(a, best_point) + split(best_point, b)

        n = max(2, math.ceil(length / max_segment_s))
        part = length / n
        return [(a + i * part, a + (i + 1) * part) for i in range(n)]

    out: list[tuple[float, float]] = []

    for s, e in segments:
        out.extend(split(float(s), float(e)))

    cleaned: list[tuple[float, float]] = []
    for s, e in out:
        s = max(0.0, float(s))
        e = max(s + 0.05, float(e))
        cleaned.append((s, e))

    return cleaned


def _parse_vad_output(raw: str, duration: float) -> list[tuple[float, float]]:
    if not raw or not raw.strip():
        return []

    segments: list[tuple[float, float]] = []

    try:
        obj = json.loads(raw)

        def walk(o):
            if isinstance(o, dict):
                for k1 in ("start", "start_time", "begin", "st", "start_ms"):
                    for k2 in ("end", "end_time", "stop", "et", "end_ms"):
                        if k1 in o and k2 in o:
                            try:
                                segments.append((float(o[k1]), float(o[k2])))
                            except Exception:
                                pass

                for v in o.values():
                    walk(v)

            elif isinstance(o, list):
                if len(o) >= 2:
                    try:
                        a = float(o[0])
                        b = float(o[1])
                        segments.append((a, b))
                    except Exception:
                        pass

                for item in o:
                    walk(item)

        walk(obj)
    except Exception:
        pass

    if not segments:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue

            if re.search(
                r"\b(model|load|loaded|loading|threads|version|sample|rate|usage|help|error|warn|info)\b",
                line,
                re.I,
            ):
                continue

            nums = re.findall(r"[-+]?[0-9]+(?:\.[0-9]+)?", line)
            if len(nums) < 2:
                continue

            try:
                a = float(nums[-2])
                b = float(nums[-1])
            except Exception:
                continue

            if b > a:
                segments.append((a, b))

    if not segments:
        return []

    unit = os.environ.get("FUNASR_VAD_UNITS", "ms").strip().lower()

    converted: list[tuple[float, float]] = []

    for a, b in segments:
        if unit == "ms":
            a /= 1000.0
            b /= 1000.0
        elif unit == "s":
            pass
        else:
            if b > 1000.0:
                a /= 1000.0
                b /= 1000.0

        if a < 0:
            a = 0.0
        if b <= a:
            continue

        if duration > 0 and b > duration + 1.0:
            continue

        converted.append((a, b))

    if not converted:
        return []

    converted.sort()

    merged: list[list[float]] = []
    for s, e in converted:
        if not merged or s > merged[-1][1] + 0.02:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)

    final = [(float(s), float(e)) for s, e in merged if e - s >= 0.05]
    return final



def _binary_vad(
    wav_path: Path,
    duration: float,
    vad_bin: str | None,
    vad_model: str,
    max_segment_ms: int,
    max_end_silence_ms: int,
    speech_noise_thres: float | None,
    threads: int,
) -> list[tuple[float, float]]:
    if not vad_bin or not Path(vad_bin).is_file():
        return []

    if not Path(vad_model).exists():
        return []

    output_flag = _detect_output_flag(vad_bin, "FUNASR_VAD_OUTPUT_FLAG")

    base_cmd = [
        vad_bin,
        "-m", str(vad_model),
        "-a", str(wav_path),
    ]

    tune_sets: list[list[str]] = []

    tune_gnu: list[str] = []
    if max_segment_ms:
        tune_gnu += ["--max-single-segment-time", str(int(max_segment_ms))]
    if max_end_silence_ms:
        tune_gnu += ["--max-end-silence-time", str(int(max_end_silence_ms))]
    if speech_noise_thres is not None:
        tune_gnu += ["--speech-noise-thres", str(float(speech_noise_thres))]
    if tune_gnu:
        tune_sets.append(tune_gnu)

    tune_alt: list[str] = []
    if max_segment_ms:
        tune_alt.append(f"--max_single_segment_time={int(max_segment_ms)}")
    if max_end_silence_ms:
        tune_alt.append(f"--max_end_silence_time={int(max_end_silence_ms)}")
    if speech_noise_thres is not None:
        tune_alt.append(f"--speech_noise_thres={float(speech_noise_thres)}")
    if tune_alt:
        tune_sets.append(tune_alt)

    tune_sets.append([])

    output_options = [True, False] if output_flag else [False]

    for tune in tune_sets:
        for use_output in output_options:
            cmd = base_cmd + tune

            out_path: Path | None = None
            if use_output and output_flag:
                fd, out_name = tempfile.mkstemp(suffix=".txt", prefix="funasr-vad-")
                os.close(fd)
                out_path = Path(out_name)
                cmd = cmd + [output_flag, str(out_path)]

            try:
                p = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=3600,
                    creationflags=_SUBPROCESS_CREATION_FLAGS,
                )

                raw = p.stdout or ""

                if out_path and out_path.exists():
                    try:
                        raw = out_path.read_text(encoding="utf-8", errors="replace") + "\n" + raw
                    except Exception:
                        pass

                segs = _parse_vad_output(raw, duration)
                if segs:
                    return segs

            except Exception:
                pass
            finally:
                if out_path and out_path.exists():
                    try:
                        out_path.unlink()
                    except Exception:
                        pass

    return []



def _prepare_segments(
    wav_path: Path,
    duration: float,
    vad_bin: str | None,
    vad_model: str,
    max_segment_ms: int,
    max_end_silence_ms: int,
    speech_noise_thres: float | None,
    threads: int,
    noise_db: float,
    min_silence_s: float,
) -> list[tuple[float, float]]:
    max_segment_s = max(1.0, float(max_segment_ms) / 1000.0)

    silences = _ffmpeg_silences(
        wav_path,
        duration,
        noise_db=noise_db,
        min_silence_s=min_silence_s,
    )

    segments: list[tuple[float, float]] = []

    if os.environ.get("FUNASR_FORCE_FFMPEG_VAD", "").strip() != "1":
        segments = _binary_vad(
            wav_path=wav_path,
            duration=duration,
            vad_bin=vad_bin,
            vad_model=vad_model,
            max_segment_ms=max_segment_ms,
            max_end_silence_ms=max_end_silence_ms,
            speech_noise_thres=speech_noise_thres,
            threads=threads,
        )

    if not segments:
        speech = _speech_from_silences(silences, duration)
        return _split_long_segments(speech, silences, max_segment_s)

    refined: list[tuple[float, float]] = []
    for s, e in segments:
        if e - s <= max_segment_s * 1.25:
            refined.append((s, e))
        else:
            refined.extend(
                _split_long_segments([(s, e)], silences, max_segment_s)
            )

    expected = max(1, int(duration // max_segment_s))
    if len(refined) < max(2, expected // 4):
        speech = _speech_from_silences(silences, duration)
        ffmpeg_segments = _split_long_segments(speech, silences, max_segment_s)

        if len(ffmpeg_segments) > len(refined):
            return ffmpeg_segments

    return refined


def _parse_sensevoice_output(raw: str, keep_tags: bool = False) -> tuple[str, str | None]:
    if not raw or not raw.strip():
        return "", None

    try:
        obj = json.loads(raw)

        if isinstance(obj, dict) and "text" in obj:
            raw = str(obj["text"])
        elif isinstance(obj, list) and obj:
            parts = []
            for item in obj:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            raw = "\n".join(parts)
    except Exception:
        pass

    lang_match = _SENSEVOICE_LANG_RE.search(raw)
    lang = lang_match.group(1).lower() if lang_match else None

    lines: list[str] = []

    for line in raw.splitlines():
        if _TAG_RE.search(line):
            lines.append(line)
            continue

        if re.search(
            r"\b(model|load|loaded|loading|threads|version|sample|rate|usage|help|error|warn|info|system_info|av_|ffmpeg|vad)\b",
            line,
            re.I,
        ) and not re.search(r"[A-Za-z0-9\u4e00-\u9fff]{4,}", line):
            continue

        lines.append(line)

    text = "\n".join(lines)

    if not keep_tags:
        text = _TAG_RE.sub(" ", text)
        text = re.sub(r"<[^>\n]*>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

    return text, lang



def _run_sensevoice(
    asr_bin: str,
    model_path: str,
    chunk_path: Path,
    lang: str,
    threads: int,
    no_tags: bool,
) -> str:
    output_flag = _detect_output_flag(asr_bin, "FUNASR_ASR_OUTPUT_FLAG")
    lang_flag = _detect_lang_flag(asr_bin)
    keep_tags_supported = _detect_keep_tags(asr_bin)

    def build_command(use_lang: bool, use_tags: bool, use_output: bool):
        cmd = [
            asr_bin,
            "-m", str(model_path),
            "-a", str(chunk_path),
        ]

        if use_lang and lang and lang.lower() != "auto" and lang_flag:
            cmd += [lang_flag, lang.lower()]

        if use_tags and keep_tags_supported and not no_tags:
            cmd += ["--keep-tags"]

        out_path: Path | None = None
        if use_output and output_flag:
            fd, out_name = tempfile.mkstemp(suffix=".txt", prefix="funasr-asr-")
            os.close(fd)
            out_path = Path(out_name)
            cmd += [output_flag, str(out_path)]

        return cmd, out_path

    output_options = [True, False] if output_flag else [False]
    lang_options = [True, False]
    tag_options = [not no_tags, False]

    last_error = "unknown SenseVoice failure"

    for use_output in output_options:
        for use_lang in lang_options:
            for use_tags in tag_options:
                cmd, out_path = build_command(use_lang, use_tags, use_output)

                try:
                    p = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=3600,
                        creationflags=_SUBPROCESS_CREATION_FLAGS,
                    )

                    raw = p.stdout or ""

                    if out_path and out_path.exists():
                        try:
                            raw = out_path.read_text(encoding="utf-8", errors="replace") + "\n" + raw
                        except Exception:
                            pass

                    if p.returncode == 0 and raw.strip():
                        return raw

                    last_error = (
                        f"rc={p.returncode}\n"
                        f"stdout:\n{p.stdout}\n"
                        f"stderr:\n{p.stderr}"
                    )

                except Exception as exc:
                    last_error = str(exc)
                finally:
                    if out_path and out_path.exists():
                        try:
                            out_path.unlink()
                        except Exception:
                            pass

    raise RuntimeError(f"SenseVoice failed on {chunk_path.name}: {last_error}")


def _cjk_adjusted_char_count(text: str) -> int:
    """Count characters, weighting each CJK codepoint as 2.

    CJK characters require roughly 2x the reading time of ASCII characters, so a
    batch/line budget of N Latin characters should be a budget of ~N/2 CJK
    characters for the same on-screen duration. This helper gives CJK scripts
    the same *reading-time* weight as Latin text while keeping the effective
    budget controlled by the existing ``--asr-max-cue-chars`` flag.
    """
    count = 0
    for ch in text:
        cp = ord(ch)
        # CJK Unified Ideographs, Hangul syllables, Hiragana, Katakana.
        if (0x4E00 <= cp <= 0x9FFF
                or 0xAC00 <= cp <= 0xD7A3
                or 0x3040 <= cp <= 0x30FF):
            count += 2
        else:
            count += 1
    return count


def _split_text(text: str, max_chars: int) -> list[str]:
    text = text.strip()

    if not text:
        return []

    if _cjk_adjusted_char_count(text) <= max_chars:
        return [text]

    for sep in _TEXT_SEPARATORS:
        if sep not in text:
            continue

        parts = text.split(sep)
        out: list[str] = []
        buf = ""

        for part in parts:
            part = part.strip()
            if not part:
                continue

            candidate = part if not buf else buf + sep + part

            if _cjk_adjusted_char_count(candidate) <= max_chars:
                buf = candidate
            else:
                if buf:
                    out.append(buf.strip())

                if _cjk_adjusted_char_count(part) > max_chars:
                    out.extend(_split_text(part, max_chars))
                    buf = ""
                else:
                    buf = part

        if buf:
            out.append(buf.strip())

        out = [x.strip() for x in out if x.strip()]
        if out:
            return out

    # No separator available: hard chunk by weighted char budget.
    result: list[str] = []
    current = ""
    current_weight = 0
    for ch in text:
        w = 2 if (
            0x4E00 <= ord(ch) <= 0x9FFF
            or 0xAC00 <= ord(ch) <= 0xD7A3
            or 0x3040 <= ord(ch) <= 0x30FF
        ) else 1
        if current and current_weight + w > max_chars:
            result.append(current)
            current = ""
            current_weight = 0
        current += ch
        current_weight += w
    if current:
        result.append(current)
    return result if result else [text]



def _segment_to_cues(
    text: str,
    start: float,
    end: float,
    max_cue_chars: int,
    max_cue_duration_s: float,
) -> list[Cue]:
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    duration = max(0.1, float(end) - float(start))
    needed = max(1, math.ceil(duration / max(1.0, max_cue_duration_s)))

    current_max_chars = max(20, int(max_cue_chars))
    units = _split_text(text, current_max_chars)

    while len(units) < needed and current_max_chars > 18:
        current_max_chars = max(18, int(current_max_chars * 0.8))
        units = _split_text(text, current_max_chars)

    if not units:
        return []

    # Weighted by CJK-adjusted length so characters get proportional share of
    # the segment duration based on real reading time.
    weights = [max(1, _cjk_adjusted_char_count(u)) for u in units]
    total_weight = sum(weights)

    cues: list[Cue] = []
    t = float(start)

    for i, (unit, weight) in enumerate(zip(units, weights)):
        unit_duration = duration * (weight / float(total_weight))

        if i == len(units) - 1:
            unit_end = float(end)
        else:
            unit_end = t + unit_duration

        if unit_end - t < 0.12:
            unit_end = min(float(end), t + 0.12)

        cues.append(
            Cue(
                start=t,
                end=unit_end,
                text=unit,
            )
        )

        t = unit_end

        if t >= end:
            break

    cleaned: list[Cue] = []
    for cue in cues:
        if cue.end <= cue.start:
            continue
        if not cue.text.strip():
            continue
        cleaned.append(cue)

    return cleaned


def _lang_name(code: str | None) -> str | None:
    if not code:
        return None

    code = code.strip().lower()

    if code == "auto":
        return None

    return _CODE_TO_NAME.get(code, code)


def _ffprobe_exe() -> str | None:
    """Return the ffprobe binary path, or None if unavailable.

    Preferred source is ``imageio_ffmpeg.get_ffmpeg_exe()``, with the ffprobe
    sibling derived by replacing the executable name (imageio_ffmpeg only ships
    ffmpeg, not ffprobe, so this usually returns the next best candidate).
    """
    candidates: list[str] = []

    env = os.environ.get("FFPROBE_BIN")
    if env:
        candidates.append(env)
    env = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if env:
        candidates.append(
            os.path.join(os.path.dirname(env), "ffprobe.exe")
            if env.lower().endswith(".exe")
            else env
        )

    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        base = os.path.splitext(ffmpeg)[0]
        sibling = base + ".exe" if os.name == "nt" else base
        candidates.append(sibling)
    except Exception:  # noqa: BLE001
        pass

    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        candidates.append(ffprobe)

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
        if candidate and os.path.sep not in candidate:
            which = shutil.which(candidate)
            if which:
                return which
    return None


def _extract_keyframe_times(video_path: str, ffprobe_bin: str) -> list[float]:
    """Return a sorted list of keyframe PTS times (seconds) for the video stream.

    Uses ffprobe packet flags. On any error or an empty result it returns ``[]``
    so callers can fall back to no snapping — this must never be fatal.
    """
    times: list[float] = []
    try:
        p = subprocess.run(
            [ffprobe_bin, "-v", "quiet", "-select_streams", "v",
             "-show_entries", "packet=pts_time:packet=flags",
             "-of", "csv", video_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            creationflags=_SUBPROCESS_CREATION_FLAGS,
        )
    except Exception:  # noqa: BLE001
        return times
    for line in p.stdout.splitlines():
        if "K" not in line:
            continue
        # CSV: packet,<pts_time>,<flags>  ->  e.g. packet,0.000000,K_
        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            pts = float(parts[1])
        except ValueError:
            continue
        if pts >= 0 and (times == [] or pts > times[-1]):
            times.append(pts)
    return times


def _snap_cues_to_keyframes(
    cues: list,
    keyframe_times: list[float],
    snap_window_s: float = 0.10,
) -> list:
    """Snap each cue ``start`` to the nearest keyframe within ``snap_window_s``.

    Prevents a subtitle from appearing mid-scene-cut. Duration is preserved: the
    ``end`` shifts by the same delta as the ``start``. Cues whose nearest
    keyframe is farther than ``snap_window_s`` away are left untouched.
    """
    if not keyframe_times:
        return cues
    import bisect
    from dataclasses import replace

    snapped = []
    for cue in cues:
        idx = bisect.bisect_left(keyframe_times, cue.start)
        candidates = []
        if idx < len(keyframe_times):
            candidates.append(keyframe_times[idx])
        if idx > 0:
            candidates.append(keyframe_times[idx - 1])
        nearest = min(candidates, key=lambda t: abs(t - cue.start))
        if abs(nearest - cue.start) <= snap_window_s:
            delta = nearest - cue.start
            cue = replace(cue, start=nearest, end=cue.end + delta)
        snapped.append(cue)
    return snapped

def maybe_warn_incomplete(cues: list[Cue], duration: float) -> None:
    """Print a warning when the transcript seems to stop before the media ends.

    A long uncovered tail (last cue end far short of the media duration) is a
    strong signal the ASR/segmentation run ended early — see SUBTITLE_QUALITY_REPORT
    §2.7, where a subtitle file stopped at 2:15 while the video was much longer.
    Thresholds are generous so natural pauses are never flagged.
    """
    if not cues or duration <= 0:
        return
    last_end = cues[-1].end
    uncovered = duration - last_end
    if uncovered > max(INCOMPLETE_WARN_SECONDS, INCOMPLETE_WARN_MEDIA_RATIO * duration):
        print(
            f"[asr] WARNING: transcription may be incomplete — last cue ends at "
            f"{last_end:.1f}s but media is {duration:.1f}s "
            f"({uncovered:.1f}s / {uncovered / duration * 100:.0f}% uncovered). "
            f"The subtitle output will be shorter than the source video.",
            flush=True,
        )


def transcribe_local_file(
    file_path: str | Path,
    asr_bin: str | None = None,
    asr_vad_bin: str | None = None,
    asr_model: str | None = None,
    asr_vad_model: str | None = None,
    asr_lang: str = "auto",
    threads: int | None = None,
    max_segment_ms: int | None = None,
    max_end_silence_ms: int | None = None,
    speech_noise_thres: float | None = None,
    noise_db: float | None = None,
    min_silence_s: float | None = None,
    max_cue_duration_ms: int | None = None,
    max_cue_chars: int | None = None,
    no_tags: bool = False,
    max_cue_chars_cjk: int | None = None,
    keep_tags: bool | None = None,
    preprocess: str = "auto",
) -> tuple[list[Cue], str | None]:
    """
    Transcribe a local media file using FunASR SenseVoiceSmall.

    Returns:
        (cues, source_language_name_or_None)
    """

    media_path = Path(file_path).expanduser()

    if not media_path.exists():
        raise FileNotFoundError(f"Media file not found: {media_path}")

    if threads is None:
        env_threads = os.environ.get("FUNASR_THREADS")
        if env_threads:
            try:
                threads = int(env_threads)
            except ValueError:
                threads = 4
        else:
            threads = max(2, min(4, os.cpu_count() or 2))


    if max_segment_ms is None:
        max_segment_ms = int(os.environ.get("FUNASR_MAX_SEGMENT_MS", "6000"))

    if max_end_silence_ms is None:
        max_end_silence_ms = int(os.environ.get("FUNASR_MAX_END_SILENCE_MS", "250"))

    if speech_noise_thres is None:
        speech_noise_thres = float(os.environ.get("FUNASR_SPEECH_NOISE_THRES", "0.55"))

    if noise_db is None:
        noise_db = float(os.environ.get("FUNASR_NOISE_DB", "-35"))

    if min_silence_s is None:
        min_silence_s = float(os.environ.get("FUNASR_MIN_SILENCE_S", "0.25"))

    if max_cue_duration_ms is None:
        max_cue_duration_ms = int(os.environ.get("FUNASR_MAX_CUE_DURATION_MS", "3200"))

    if max_cue_chars is None:
        max_cue_chars = int(os.environ.get("FUNASR_MAX_CUE_CHARS", "70"))

    if max_cue_chars_cjk is None:
        max_cue_chars_cjk = int(os.environ.get("FUNASR_MAX_CUE_CHARS_CJK", "48"))

    # Determine whether tags should be kept.
    # FUNASR_KEEP_TAGS=1 (or --asr-keep-tags) -> keep tags (disable stripping).
    if keep_tags is None:
        keep_tags = os.environ.get("FUNASR_KEEP_TAGS", "0") == "1"

    # Effective tag-keeping. The DEFAULT is to STRIP SenseVoice tags (this is
    # documented as the intended behavior: "Strip ASR tags by default;
    # --asr-keep-tags to disable"). Tags are preserved into the cue text ONLY
    # when the user explicitly opts in via --asr-keep-tags / FUNASR_KEEP_TAGS=1.
    #
    # Regression note: this used to be `bool(keep_tags) or not no_tags`, which
    # silently enabled tag-keeping whenever no_tags was False (the default), so
    # the `<|zh|><|ANGRY|><|BGM|><|withitn|>` SenseVoice tag group flowed all
    # the way into the final SRT and made subtitles unusable. The default must
    # strip tags; keeping being opt-in restores that.
    #
    # NOTE: `no_tags` still governs whether the binary's own `--keep-tags` flag
    # is requested (see _run_sensevoice). With the default we request tags from
    # SenseVoice, then strip them here (in _parse_sensevoice_output) so clean
    # source text reaches upstream.
    effective_keep = bool(keep_tags)
    if effective_keep:
        print("[asr] Keeping ASR tags due to user setting", flush=True)
    else:
        print("[asr] Stripping ASR tags", flush=True)

    # Log CJK cue char limit if the explicit language is CJK.
    if is_cjk_language(asr_lang):
        print(f"[asr] Using CJK max cue chars: {max_cue_chars_cjk}", flush=True)

    max_cue_duration_s = max(1.0, float(max_cue_duration_ms) / 1000.0)

    sensevoice_bin = _find_exe(
        explicit=asr_bin,
        env_var="FUNASR_SENSEVOICE_BIN",
        base_name="llama-funasr-sensevoice",
    )

    vad_bin = _find_exe(
        explicit=asr_vad_bin,
        env_var="FUNASR_VAD_BIN",
        base_name="llama-funasr-vad",
    )

    if not sensevoice_bin:
        raise RuntimeError(
            "FunASR SenseVoice binary not found. Expected vendor/funasr/llama-funasr-sensevoice.exe "
            "or FUNASR_SENSEVOICE_BIN."
        )

    sensevoice_model = _resolve_model(
        explicit=asr_model,
        env_var="FUNASR_MODEL",
        default=DEFAULT_SENSEVOICE_MODEL,
    )

    vad_model = _resolve_model(
        explicit=asr_vad_model,
        env_var="FUNASR_VAD_MODEL",
        default=DEFAULT_VAD_MODEL,
    )

    if not Path(sensevoice_model).exists():
        raise RuntimeError(
            f"SenseVoice model not found: {sensevoice_model}\n"
            "Download sensevoice-small-q8.gguf into ./gguf or set FUNASR_MODEL."
        )

    with tempfile.TemporaryDirectory(prefix="funasr-") as td:
        temp_dir = Path(td)

        wav_path = temp_dir / "audio16k.wav"
        _prepare_asr_audio(media_path, wav_path, preprocess)

        duration = _wav_duration(wav_path)
        if duration <= 0.1:
            raise RuntimeError("Input audio is empty or too short.")

        segments = _prepare_segments(
            wav_path=wav_path,
            duration=duration,
            vad_bin=vad_bin,
            vad_model=vad_model,
            max_segment_ms=max_segment_ms,
            max_end_silence_ms=max_end_silence_ms,
            speech_noise_thres=speech_noise_thres,
            threads=threads,
            noise_db=noise_db,
            min_silence_s=min_silence_s,
        )

        if not segments:
            raise RuntimeError(
                "FunASR segmentation produced no segments. "
                "Try FUNASR_FORCE_FFMPEG_VAD=1 or adjust silence/VAD settings."
            )

        cues: list[Cue] = []
        detected_lang: str | None = None

        for i, (seg_start, seg_end) in enumerate(segments):
            if seg_end - seg_start < 0.10:
                continue

            chunk_path = temp_dir / f"segment_{i:05d}.wav"

            try:
                _cut_wav(wav_path, seg_start, seg_end, chunk_path)
            except Exception:
                continue

            try:
                raw = _run_sensevoice(
                    asr_bin=sensevoice_bin,
                    model_path=sensevoice_model,
                    chunk_path=chunk_path,
                    lang=asr_lang or "auto",
                    threads=threads,
                    no_tags=no_tags,
                )
            except Exception:
                continue

            text, seg_lang = _parse_sensevoice_output(raw, keep_tags=effective_keep)

            if not detected_lang and seg_lang:
                detected_lang = seg_lang

            if not text:
                continue

            # CJK-aware cue char limit: once we know the language (from the
            # explicit asr_lang or detected_lang), use the tighter CJK limit.
            if is_cjk_language(asr_lang) or is_cjk_language(detected_lang):
                effective_max_chars = max_cue_chars_cjk
            else:
                effective_max_chars = max_cue_chars

            cues.extend(
                _segment_to_cues(
                    text=text,
                    start=seg_start,
                    end=seg_end,
                    max_cue_chars=effective_max_chars,
                    max_cue_duration_s=max_cue_duration_s,
                )
            )

    if not cues:
        raise RuntimeError(
            "FunASR produced no transcription. "
            "Check SenseVoice binary/model, try --asr-lang auto, "
            "or adjust VAD/silence thresholds."
        )

    if asr_lang and asr_lang.lower() != "auto":
        source_language = _lang_name(asr_lang)
    else:
        source_language = _lang_name(detected_lang)

    # --- Snap-to-keyframe pass ----------------------------------------------
    # Only for video containers, and only when ffprobe is available. Never
    # fatal: if keyframes can't be extracted we log and continue unsnapped.
    if media_path.suffix.lower() in _VIDEO_EXTENSIONS:
        ffprobe = _ffprobe_exe()
        if not ffprobe:
            print(
                "[asr] ffprobe not available; skipping snap-to-keyframe pass.",
                flush=True,
            )
        else:
            keyframes = _extract_keyframe_times(str(media_path), ffprobe)
            if not keyframes:
                print(
                    "[asr] No keyframes extracted; skipping snap-to-keyframe pass.",
                    flush=True,
                )
            else:
                before = [(c.start, c.end) for c in cues]
                cues = _snap_cues_to_keyframes(cues, keyframes)
                moved = sum(
                    1 for a, b in zip(before, [(c.start, c.end) for c in cues])
                    if a != b
                )
                print(
                    f"[asr] Snap-to-keyframe: snapped {moved}/{len(cues)} cues to "
                    f"{len(keyframes)} keyframes",
                    flush=True,
                )

    maybe_warn_incomplete(cues, duration)

    return cues, source_language
