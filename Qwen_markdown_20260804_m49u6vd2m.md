# FunASR-Only Restoration Instructions

Filename: `FUNASR_ONLY_MIGRATION.md`

This document replaces all previous Whisper-based local ASR instructions.

The project must use **FunASR + SenseVoiceSmall only** for local transcription.

Do **not** keep Whisper.cpp as a fallback. Do not keep Whisper binaries, Whisper models, Whisper CLI flags, Whisper GUI labels, or Whisper build checks.

---

## 1. Goal

The local subtitle path must no longer produce giant text blocks.

The current bad local output looks like this:

```srt
2
00:00:05,775 --> 00:00:18,449
lottieLE, in short, can help me record and let AI understand my life. lottieLE has two main modes: Story Mode and AI Mode. Story Mode is very simple to use—just enable Story Mode, and it will record according to the frequency I set.
```

The desired output should be paced more like the YouTube route:

```srt
1
00:00:00,000 --> 00:00:01,041
Recently, I received a

2
00:00:01,041 --> 00:00:03,000
Seeming rather novel little gadget

3
00:00:03,000 --> 00:00:03,500
Actually,

4
00:00:03,500 --> 00:00:05,916
It is a multimodal AI wearable device
```

The YouTube example does not need to be matched exactly, but the local output must move from:

```text
19 huge paragraph cues
```

to something like:

```text
many short phrase-sized cues
average cue duration around 2-4 seconds
no cue should normally exceed 6-7 seconds
```

For the provided sample video, the YouTube reference has about **59 cues**. The old local output has **19 cues**. The new FunASR-only output should aim for approximately:

```text
Minimum cue count:      35-45+
Preferred cue count:      45-60+
Average cue duration:     under 3.5 seconds
Maximum cue duration:     normally under 6 seconds
```

Exact cue count is not sacred. The important requirement is:

> Local subtitles must not appear as large text blocks.

---

## 2. Root cause

SenseVoiceSmall is fast and suitable for an old CPU-only laptop, but it does not provide YouTube-quality native timestamps.

The old FunASR implementation relied too much on coarse VAD segments. When VAD produced a small number of long speech segments, the app created one subtitle cue per long VAD segment.

That caused the local SRT to contain long blocks of text.

The fix is not Whisper. The fix is:

1. Restore FunASR + SenseVoiceSmall.
2. Make VAD segmentation more aggressive.
3. Use ffmpeg silence detection as a fallback/refiner.
4. Force maximum ASR segment length.
5. Split recognized text into shorter subtitle cues.
6. Distribute timing proportionally inside each ASR segment.
7. Remove Whisper completely.

---

## 3. Non-negotiable constraints

### 3.1 No Whisper

Remove all Whisper-related things from the active project:

- `vendor/whisper/`
- `whisper-cli.exe`
- `ggml-large-v3-turbo-q5_0.bin`
- `WHISPER_CLI_BIN`
- `WHISPER_MODEL`
- Whisper labels in the GUI
- Whisper download URLs
- Whisper build preflight checks
- Whisper fallback logic
- Whisper documentation

Do not reintroduce Whisper as an optional backend.

### 3.2 CPU-only

The solution must remain usable on an old laptop with no GPU.

Therefore:

- Do not add PyTorch.
- Do not add a heavy ML stack.
- Use the bundled FunASR GGML/llama.cpp-style binaries.
- Keep thread counts conservative.

### 3.3 Preserve pipeline invariants

The existing translation pipeline expects:

```python
Cue(start: float, end: float, text: str)
```

The local ASR module must return:

```python
(list[Cue], source_language_name_or_None)
```

The translation pipeline must still receive the original cue order and count.

Do not merge, drop, or reorder cues after translation.

---

## 4. Required repository state

### 4.1 FunASR binaries

The following binaries must exist:

```text
vendor/funasr/llama-funasr-sensevoice.exe
vendor/funasr/llama-funasr-vad.exe
```

Keep any DLLs that came with them in the same directory.

The other FunASR binaries may remain, but only these two are required:

```text
llama-funasr-sensevoice.exe
llama-funasr-vad.exe
```

If missing, restore them from the FunASR GitHub release runtime package that matches the project’s existing `vendor/funasr` artifacts.

### 4.2 FunASR models

The project needs:

```text
gguf/sensevoice-small-q8.gguf
gguf/fsmn-vad.gguf
```

Old copies may exist in:

```text
dist/gguf/sensevoice-small-q8.gguf
dist/gguf/fsmn-vad.gguf
```

If they exist there, move or copy them:

```bat
mkdir gguf 2>nul
copy dist\gguf\sensevoice-small-q8.gguf gguf\
copy dist\gguf\fsmn-vad.gguf gguf\
```

If missing, download them using the existing helper:

```bash
bash vendor/funasr/download-funasr-model.sh
```

If that script is unavailable, use the same FunASR model URLs that were used during the original FunASR era.

### 4.3 Remove Whisper artifacts

Delete or stop using:

```text
vendor/whisper/
gguf/ggml-large-v3-turbo-q5_0.bin
dist/gguf/ggml-large-v3-turbo-q5_0.bin
```

Also remove any Whisper references from:

```text
translate.py
src/local_asr.py
backend/bridge.py
ui/qml/views/SettingsView.qml
ui/qml/views/DashboardView.qml
build_exe.bat
README.md
CLAUDE.md
PROJECT.md
```

---

## 5. Replace `src/local_asr.py`

Replace the current Whisper-based `src/local_asr.py` with a FunASR-only implementation.

The new module must:

1. Extract audio to 16 kHz mono WAV using ffmpeg.
2. Try FunASR FSMN-VAD.
3. Use aggressive VAD settings.
4. Use ffmpeg `silencedetect` as fallback/refinement.
5. Split long speech regions into shorter ASR segments.
6. Transcribe segments with SenseVoiceSmall.
7. Strip SenseVoice tags.
8. Detect source language if `auto`.
9. Split long recognized text into shorter subtitle cues.
10. Return normal `Cue` objects.

Below is the reference implementation.

Replace the entire contents of `src/local_asr.py` with this:

```python
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


DEFAULT_SENSEVOICE_MODEL = os.path.join("gguf", "sensevoice-small-q8.gguf")
DEFAULT_VAD_MODEL = os.path.join("gguf", "fsmn-vad.gguf")

_CODE_TO_NAME = {
    "zh": "Chinese",
    "yue": "Cantonese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
}

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

    candidates = [
        Path(default),
        Path("dist") / default,
    ]

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


def _extract_wav(media_path: Path, wav_path: Path) -> None:
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(media_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-acodec", "pcm_s16le",
        str(wav_path),
    ]
    _run(cmd)


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
        "-i", str(wav_path),
        "-t", str(int(threads)),
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
            "-i", str(chunk_path),
            "-t", str(int(threads)),
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


def _split_text(text: str, max_chars: int) -> list[str]:
    text = text.strip()

    if not text:
        return []

    if len(text) <= max_chars:
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

            if len(candidate) <= max_chars:
                buf = candidate
            else:
                if buf:
                    out.append(buf.strip())

                if len(part) > max_chars:
                    out.extend(_split_text(part, max_chars))
                    buf = ""
                else:
                    buf = part

        if buf:
            out.append(buf.strip())

        out = [x.strip() for x in out if x.strip()]
        if out:
            return out

    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


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

    weights = [max(1, len(u)) for u in units]
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
        max_segment_ms = int(os.environ.get("FUNASR_MAX_SEGMENT_MS", "7000"))

    if max_end_silence_ms is None:
        max_end_silence_ms = int(os.environ.get("FUNASR_MAX_END_SILENCE_MS", "250"))

    if speech_noise_thres is None:
        speech_noise_thres = float(os.environ.get("FUNASR_SPEECH_NOISE_THRES", "0.55"))

    if noise_db is None:
        noise_db = float(os.environ.get("FUNASR_NOISE_DB", "-35"))

    if min_silence_s is None:
        min_silence_s = float(os.environ.get("FUNASR_MIN_SILENCE_S", "0.20"))

    if max_cue_duration_ms is None:
        max_cue_duration_ms = int(os.environ.get("FUNASR_MAX_CUE_DURATION_MS", "3000"))

    if max_cue_chars is None:
        max_cue_chars = int(os.environ.get("FUNASR_MAX_CUE_CHARS", "70"))

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
        _extract_wav(media_path, wav_path)

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

            text, seg_lang = _parse_sensevoice_output(raw, keep_tags=False)

            if not detected_lang and seg_lang:
                detected_lang = seg_lang

            if not text:
                continue

            cues.extend(
                _segment_to_cues(
                    text=text,
                    start=seg_start,
                    end=seg_end,
                    max_cue_chars=max_cue_chars,
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

    return cues, source_language
```

---

## 6. Update `translate.py`

The CLI must no longer mention Whisper.

Remove any Whisper-specific flags, help text, defaults, or environment variables.

The local ASR flags should now be FunASR-only.

### 6.1 Required CLI flags

Use these flags:

```text
--asr-bin
--asr-vad-bin
--asr-model
--asr-vad-model
--asr-lang
--asr-threads
--asr-max-segment-ms
--asr-max-end-silence-ms
--asr-speech-noise-threshold
--asr-noise-db
--asr-min-silence-s
--asr-max-cue-duration-ms
--asr-max-cue-chars
--asr-no-tags
```

Recommended argparse block:

```python
parser.add_argument(
    "--asr-bin",
    default=os.environ.get("FUNASR_SENSEVOICE_BIN"),
    help="Path to llama-funasr-sensevoice binary.",
)

parser.add_argument(
    "--asr-vad-bin",
    default=os.environ.get("FUNASR_VAD_BIN"),
    help="Path to llama-funasr-vad binary.",
)

parser.add_argument(
    "--asr-model",
    default=os.environ.get("FUNASR_MODEL"),
    help="Path to sensevoice-small-q8.gguf.",
)

parser.add_argument(
    "--asr-vad-model",
    default=os.environ.get("FUNASR_VAD_MODEL"),
    help="Path to fsmn-vad.gguf.",
)

parser.add_argument(
    "--asr-lang",
    default="auto",
    help="Source language: auto, zh, en, ja, ko, yue.",
)

parser.add_argument(
    "--asr-threads",
    type=int,
    default=int(os.environ.get("FUNASR_THREADS", "4")),
    help="CPU threads for FunASR.",
)

parser.add_argument(
    "--asr-max-segment-ms",
    type=int,
    default=int(os.environ.get("FUNASR_MAX_SEGMENT_MS", "7000")),
    help="Maximum ASR audio segment length before post-splitting into cues.",
)

parser.add_argument(
    "--asr-max-end-silence-ms",
    type=int,
    default=int(os.environ.get("FUNASR_MAX_END_SILENCE_MS", "250")),
    help="Trailing silence allowed before VAD closes a speech segment.",
)

parser.add_argument(
    "--asr-speech-noise-threshold",
    type=float,
    default=float(os.environ.get("FUNASR_SPEECH_NOISE_THRES", "0.55")),
    help="FunASR VAD speech/noise threshold.",
)

parser.add_argument(
    "--asr-noise-db",
    type=float,
    default=float(os.environ.get("FUNASR_NOISE_DB", "-35")),
    help="ffmpeg silencedetect noise threshold in dB.",
)

parser.add_argument(
    "--asr-min-silence-s",
    type=float,
    default=float(os.environ.get("FUNASR_MIN_SILENCE_S", "0.20")),
    help="Minimum silence duration for ffmpeg silence detection.",
)

parser.add_argument(
    "--asr-max-cue-duration-ms",
    type=int,
    default=int(os.environ.get("FUNASR_MAX_CUE_DURATION_MS", "3000")),
    help="Preferred maximum subtitle cue duration.",
)

parser.add_argument(
    "--asr-max-cue-chars",
    type=int,
    default=int(os.environ.get("FUNASR_MAX_CUE_CHARS", "70")),
    help="Preferred maximum subtitle cue character count.",
)

parser.add_argument(
    "--asr-no-tags",
    action="store_true",
    help="Do not request SenseVoice tag output.",
)
```

### 6.2 Call the local ASR module

The local-file branch should call:

```python
from src import local_asr

cues, source_language = local_asr.transcribe_local_file(
    args.file,
    asr_bin=args.asr_bin,
    asr_vad_bin=args.asr_vad_bin,
    asr_model=args.asr_model,
    asr_vad_model=args.asr_vad_model,
    asr_lang=args.asr_lang,
    threads=args.asr_threads,
    max_segment_ms=args.asr_max_segment_ms,
    max_end_silence_ms=args.asr_max_end_silence_ms,
    speech_noise_thres=args.asr_speech_noise_threshold,
    noise_db=args.asr_noise_db,
    min_silence_s=args.asr_min_silence_s,
    max_cue_duration_ms=args.asr_max_cue_duration_ms,
    max_cue_chars=args.asr_max_cue_chars,
    no_tags=args.asr_no_tags,
)
```

Remove any code path that calls Whisper.

---

## 7. Recommended timing defaults

These defaults are chosen to avoid large blocks while remaining usable on an old CPU.

```text
FUNASR_THREADS=4
FUNASR_MAX_SEGMENT_MS=7000
FUNASR_MAX_END_SILENCE_MS=250
FUNASR_SPEECH_NOISE_THRES=0.55
FUNASR_NOISE_DB=-35
FUNASR_MIN_SILENCE_S=0.20
FUNASR_MAX_CUE_DURATION_MS=3000
FUNASR_MAX_CUE_CHARS=70
```

Meaning:

- FunASR/VAD should try to keep speech segments under about 7 seconds.
- Subtitle cues are then split to target about 3 seconds each.
- Long text is split on punctuation and proportionally timed.

### 7.1 If output still has large blocks

Use more aggressive values:

```text
--asr-max-segment-ms 5000
--asr-max-end-silence-ms 200
--asr-max-cue-duration-ms 2600
--asr-max-cue-chars 60
```

Or environment variables:

```text
FUNASR_MAX_SEGMENT_MS=5000
FUNASR_MAX_END_SILENCE_MS=200
FUNASR_MAX_CUE_DURATION_MS=2600
FUNASR_MAX_CUE_CHARS=60
```

### 7.2 If performance is too slow

Use slightly larger ASR segments but keep cue display short:

```text
--asr-max-segment-ms 9000
--asr-max-cue-duration-ms 3200
```

This reduces the number of SenseVoice process launches while still preventing giant subtitle cues.

### 7.3 If words are being cut mid-speech

Increase:

```text
--asr-max-segment-ms
--asr-min-silence-s
```

Example:

```text
--asr-max-segment-ms 8000
--asr-min-silence-s 0.30
```

### 7.4 If background music prevents silence detection

Try:

```text
--asr-noise-db -30
```

If quiet speech is being missed, try:

```text
--asr-noise-db -40
```

---

## 8. Update `backend/bridge.py`

The GUI bridge must be rewired from Whisper to FunASR.

### 8.1 Remove Whisper state

Remove or replace any references to:

```text
whisper
WHISPER_CLI_BIN
WHISPER_MODEL
ggml-large-v3-turbo-q5_0.bin
```

Do not keep Whisper properties.

### 8.2 Restore and wire FunASR properties

The bridge already contains dead legacy properties:

```python
asrBin
asrVadBin
asrVadModel
```

These must no longer be dead code.

Ensure these properties exist and are persisted via `QSettings`:

```text
asr/bin
asr/vadBin
asr/model
asr/vadModel
asr/lang
asr/threads
asr/maxSegmentMs
asr/maxEndSilenceMs
asr/speechNoiseThreshold
asr/noiseDb
asr/minSilenceS
asr/maxCueDurationMs
asr/maxCueChars
asr/noTags
```

Recommended QObject property names:

```python
asrBin
asrVadBin
asrModel
asrVadModel
asrLang
asrThreads
asrMaxSegmentMs
asrMaxEndSilenceMs
asrSpeechNoiseThreshold
asrNoiseDb
asrMinSilenceS
asrMaxCueDurationMs
asrMaxCueChars
asrNoTags
```

### 8.3 Build FunASR argv

In `_build_run_config()`, the local-file branch must include:

```python
argv += ["--file", self.filePath]

argv += ["--asr-bin", self.localPath(self.asrBin)]
argv += ["--asr-vad-bin", self.localPath(self.asrVadBin)]
argv += ["--asr-model", self.localPath(self.asrModel)]
argv += ["--asr-vad-model", self.localPath(self.asrVadModel)]

argv += ["--asr-lang", self.asrLang]
argv += ["--asr-threads", str(self.asrThreads)]
argv += ["--asr-max-segment-ms", str(self.asrMaxSegmentMs)]
argv += ["--asr-max-end-silence-ms", str(self.asrMaxEndSilenceMs)]
argv += ["--asr-speech-noise-threshold", str(self.asrSpeechNoiseThreshold)]
argv += ["--asr-noise-db", str(self.asrNoiseDb)]
argv += ["--asr-min-silence-s", str(self.asrMinSilenceS)]
argv += ["--asr-max-cue-duration-ms", str(self.asrMaxCueDurationMs)]
argv += ["--asr-max-cue-chars", str(self.asrMaxCueChars)]

if self.asrNoTags:
    argv += ["--asr-no-tags"]
```

Only add paths if they are non-empty.

### 8.4 Update model download URLs

Remove the Whisper model URL.

The downloader must fetch the two FunASR models:

```text
sensevoice-small-q8.gguf
fsmn-vad.gguf
```

Use the same URLs that appear in:

```text
vendor/funasr/download-funasr-model.sh
```

Do not invent new model URLs if the script already contains the correct ones.

After download, set:

```text
asrModel     -> gguf/sensevoice-small-q8.gguf
asrVadModel  -> gguf/fsmn-vad.gguf
```

---

## 9. Update QML

Update:

```text
ui/qml/views/DashboardView.qml
ui/qml/views/SettingsView.qml
```

Remove all Whisper wording.

The Local ASR section should say something like:

```text
Local ASR: FunASR + SenseVoiceSmall
```

The settings page should expose:

```text
SenseVoice binary
VAD binary
SenseVoice model
VAD model
ASR language
ASR threads
Max segment ms
Max end silence ms
Speech/noise threshold
Noise dB
Minimum silence seconds
Max cue duration ms
Max cue chars
No tags
```

Recommended default values in the UI:

```text
ASR language:             auto
ASR threads:              4
Max segment ms:           7000
Max end silence ms:       250
Speech/noise threshold:   0.55
Noise dB:                 -35
Minimum silence seconds:  0.20
Max cue duration ms:      3000
Max cue chars:            70
No tags:                  unchecked
```

The one-click ASR model download button must download FunASR models, not Whisper.

---

## 10. Update `build_exe.bat`

The standalone build must no longer require Whisper.

### 10.1 Remove Whisper checks

Remove lines similar to:

```bat
if not exist vendor\whisper\Release\whisper-cli.exe ...
```

Remove Whisper data bundling similar to:

```bat
--add-data "vendor\whisper\Release;vendor/whisper/Release"
```

### 10.2 Add FunASR checks

Add:

```bat
if not exist vendor\funasr\llama-funasr-sensevoice.exe (
    echo Missing vendor\funasr\llama-funasr-sensevoice.exe
    echo Place the FunASR SenseVoice runtime binary there before building.
    exit /b 1
)

if not exist vendor\funasr\llama-funasr-vad.exe (
    echo Missing vendor\funasr\llama-funasr-vad.exe
    echo Place the FunASR VAD runtime binary there before building.
    exit /b 1
)
```

### 10.3 Bundle FunASR binaries

Add to the PyInstaller command:

```bat
--add-data "vendor\funasr;vendor/funasr"
```

Do not bundle Whisper.

Models may remain downloaded at runtime instead of embedded, because `sensevoice-small-q8.gguf` is large.

If you choose to bundle models, add:

```bat
--add-data "gguf\sensevoice-small-q8.gguf;gguf"
--add-data "gguf\fsmn-vad.gguf;gguf"
```

But this is optional and will increase exe size substantially.

---

## 11. Environment variables

The FunASR-only backend should respect these environment variables:

```text
FUNASR_SENSEVOICE_BIN
FUNASR_VAD_BIN
FUNASR_MODEL
FUNASR_VAD_MODEL
FUNASR_THREADS
FUNASR_MAX_SEGMENT_MS
FUNASR_MAX_END_SILENCE_MS
FUNASR_SPEECH_NOISE_THRES
FUNASR_NOISE_DB
FUNASR_MIN_SILENCE_S
FUNASR_MAX_CUE_DURATION_MS
FUNASR_MAX_CUE_CHARS
FUNASR_FORCE_FFMPEG_VAD
FUNASR_VAD_UNITS
FUNASR_OUTPUT_FLAG
FUNASR_ASR_OUTPUT_FLAG
FUNASR_VAD_OUTPUT_FLAG
```

Remove all Whisper environment variables from documentation and code:

```text
WHISPER_CLI_BIN
WHISPER_MODEL
```

### 11.1 Useful debugging variables

If FunASR VAD output is unusable:

```text
FUNASR_FORCE_FFMPEG_VAD=1
```

If VAD output is in seconds instead of milliseconds:

```text
FUNASR_VAD_UNITS=s
```

If VAD output is in milliseconds:

```text
FUNASR_VAD_UNITS=ms
```

If a FunASR binary requires a specific output flag:

```text
FUNASR_OUTPUT_FLAG=-o
```

or separately:

```text
FUNASR_ASR_OUTPUT_FLAG=-o
FUNASR_VAD_OUTPUT_FLAG=-o
```

---

## 12. Manual smoke test

Before testing the GUI, test the CLI.

### 12.1 Basic run

```bat
python translate.py --file "path\to\video.mp4"
```

This should now use FunASR.

### 12.2 Explicit FunASR settings

```bat
python translate.py --file "path\to\video.mp4" ^
  --asr-lang auto ^
  --asr-threads 4 ^
  --asr-max-segment-ms 7000 ^
  --asr-max-end-silence-ms 250 ^
  --asr-speech-noise-threshold 0.55 ^
  --asr-noise-db -35 ^
  --asr-min-silence-s 0.20 ^
  --asr-max-cue-duration-ms 3000 ^
  --asr-max-cue-chars 70
```

### 12.3 More aggressive cue splitting

```bat
python translate.py --file "path\to\video.mp4" ^
  --asr-max-segment-ms 5000 ^
  --asr-max-end-silence-ms 200 ^
  --asr-max-cue-duration-ms 2600 ^
  --asr-max-cue-chars 60
```

---

## 13. Acceptance test using the provided sample subtitles

You provided two reference files:

```text
当我把生活变成了开放世界 RPG…… - Copy.txt
当我把生活变成了开放世界 RPG……-youtube option - Copy.txt
```

The first is the bad local output. The second is the desired YouTube-style pacing.

Rename them locally if useful:

```text
samples/local_old.srt
samples/youtube_reference.srt
```

Then compare new local output against these targets.

### 13.1 Old local output characteristics

The old local file has about:

```text
19 cues
average duration around 7 seconds
some cues over 10 seconds
large paragraph-style text blocks
```

This is unacceptable.

### 13.2 YouTube reference characteristics

The YouTube reference has about:

```text
59 cues
average duration around 2 seconds
short phrase-style lines
```

This is the visual target.

### 13.3 New local output requirements

For the same source media, the new FunASR-only output should satisfy:

```text
Cue count:          at least 35, preferably 45+
Average cue length: under 3.5 seconds
Maximum cue length: normally under 6 seconds
No cue should contain multiple full sentences when punctuation allows splitting.
```

If the new output still contains cues like:

```srt
2
00:00:05,775 --> 00:00:18,449
lottieLE, in short, can help me record and let AI understand my life. lottieLE has two main modes: Story Mode and AI Mode. Story Mode is very simple to use—just enable Story Mode, and it will record according to the frequency I set.
```

the fix is not complete.

---

## 14. Simple SRT inspection script

Create `tools/check_srt.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.srt_io import read_srt


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/check_srt.py output.srt")
        raise SystemExit(1)

    path = Path(sys.argv[1])
    cues = read_srt(path)

    if not cues:
        print("No cues found.")
        return

    durations = [c.end - c.start for c in cues]

    print(f"file: {path}")
    print(f"cues: {len(cues)}")
    print(f"average duration: {sum(durations) / len(durations):.3f}s")
    print(f"max duration: {max(durations):.3f}s")
    print(f"min duration: {min(durations):.3f}s")

    long_cues = [c for c in cues if (c.end - c.start) > 6.0]
    print(f"cues longer than 6s: {len(long_cues)}")

    for c in long_cues[:10]:
        print(f"  {c.start:.3f} -> {c.end:.3f}: {c.text[:80]}")


if __name__ == "__main__":
    main()
```

Run:

```bat
python tools\check_srt.py output.srt
```

Target:

```text
cues: 45+
average duration: under 3.5s
max duration: under 6s
cues longer than 6s: few or zero
```

---

## 15. Troubleshooting

### 15.1 SenseVoice binary not found

Error:

```text
FunASR SenseVoice binary not found
```

Fix:

- Confirm `vendor/funasr/llama-funasr-sensevoice.exe` exists.
- Confirm all DLLs are beside it.
- Or set:

```text
FUNASR_SENSEVOICE_BIN=C:\path\to\llama-funasr-sensevoice.exe
```

---

### 15.2 VAD model not found

Error:

```text
fsmn-vad.gguf not found
```

Fix:

```bat
mkdir gguf 2>nul
copy dist\gguf\fsmn-vad.gguf gguf\
```

Or download it again using the FunASR model script.

---

### 15.3 SenseVoice model not found

Error:

```text
sensevoice-small-q8.gguf not found
```

Fix:

```bat
mkdir gguf 2>nul
copy dist\gguf\sensevoice-small-q8.gguf gguf\
```

Or download it again.

---

### 15.4 Still too few cues

Try:

```bat
--asr-max-segment-ms 5000
--asr-max-end-silence-ms 200
--asr-max-cue-duration-ms 2600
--asr-max-cue-chars 60
```

Also try:

```bat
set FUNASR_FORCE_FFMPEG_VAD=1
python translate.py --file video.mp4
```

---

### 15.5 Cues are too fragmented

Try:

```bat
--asr-max-segment-ms 9000
--asr-max-end-silence-ms 400
--asr-max-cue-duration-ms 3500
--asr-max-cue-chars 85
```

---

### 15.6 Timing is acceptable but text is cut mid-sentence

Increase:

```bat
--asr-max-segment-ms
--asr-min-silence-s
```

Example:

```bat
--asr-max-segment-ms 8000
--asr-min-silence-s 0.30
```

---

### 15.7 Background music causes bad segmentation

Try:

```bat
--asr-noise-db -30
```

If quiet speech is lost:

```bat
--asr-noise-db -40
```

---

### 15.8 FunASR binary flags differ

The FunASR runtime CLI can vary by release.

Check:

```bat
vendor\funasr\llama-funasr-sensevoice.exe --help
vendor\funasr\llama-funasr-vad.exe --help
```

The implementation probes common flags, but if your build requires a special output flag, set:

```text
FUNASR_OUTPUT_FLAG=-o
```

or separately:

```text
FUNASR_ASR_OUTPUT_FLAG=-o
FUNASR_VAD_OUTPUT_FLAG=-o
```

---

## 16. Documentation updates

Update all documentation so FunASR is the only local ASR direction.

### 16.1 `README.md`

Replace Whisper local ASR documentation with:

- FunASR + SenseVoiceSmall local transcription.
- Required binaries:
  - `vendor/funasr/llama-funasr-sensevoice.exe`
  - `vendor/funasr/llama-funasr-vad.exe`
- Required models:
  - `gguf/sensevoice-small-q8.gguf`
  - `gguf/fsmn-vad.gguf`
- FunASR CLI flags.
- FunASR environment variables.
- No mention of Whisper.

### 16.2 `CLAUDE.md`

Update invariants:

```text
Local ASR is FunASR + SenseVoiceSmall only.
Whisper.cpp is not used and must not be reintroduced.
Local cue timing is produced by VAD + silence refinement + proportional cue splitting.
```

### 16.3 `PROJECT.md`

Update the ASR backend drift section.

The new state should be:

```text
Direction A — FunASR + SenseVoiceSmall: live/default
Direction B — whisper.cpp: removed, not optional, not a fallback
```

Remove wording that describes Whisper as the current implementation.

---

## 17. Definition of done

The task is complete when:

1. `python translate.py --file video.mp4` uses FunASR.
2. No Whisper binary, model, flag, env var, or GUI label remains.
3. `vendor/funasr` binaries are used.
4. `gguf/sensevoice-small-q8.gguf` and `gguf/fsmn-vad.gguf` are used.
5. Local SRT output no longer contains giant paragraph cues.
6. For the provided sample, local cue count is much closer to the YouTube reference than the old 19-cue output.
7. Average cue duration is usually under 3.5 seconds.
8. No cue normally exceeds 6 seconds.
9. The GUI settings expose FunASR binaries/models and timing controls.
10. The standalone build bundles FunASR, not Whisper.
11. Documentation matches the implementation.