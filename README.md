# YouTube Subtitle Translator

A command-line tool that takes a YouTube URL, fetches the video's
**original-language** subtitles (manual if available, auto-generated as fallback),
translates them **faithfully into English** using an OpenAI-compatible LLM, and
writes an SRT file named after the video while preserving the original timing.

## Install

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit .env and fill in your credentials
```

## Configure (`.env`)

| Variable         | Required | Meaning                                                        |
| ---------------- | -------- | ------------------------------------------------------------- |
| `OPENAI_API_KEY` | yes      | API key for your OpenAI-compatible endpoint.                  |
| `OPENAI_MODEL`   | yes      | Model used for translation (e.g. `gpt-4o-mini`).              |
| `OPENAI_BASE_URL`| no       | Base URL for any OpenAI-compatible API; leave blank for OpenAI, or `https://openrouter.ai/api/v1` for OpenRouter. |

## Usage

```bash
python translate.py "<youtube_url>"
python translate.py "<youtube_url>" --model gpt-4o --out my_subs.srt --batch 30
```

- Output is written to `<video_title>.srt` in the current directory by default.
- `--out` overrides the output path.
- `--model` overrides `OPENAI_MODEL`.
- `--batch` sets how many subtitle cues are sent per translation call (default 40).

## GUI (Windows)

A modern desktop frontend built with **PySide6 + QML** wraps the same CLI. The
interface is now split cleanly into a declarative QML view layer and a Python
`QObject` bridge that streams pipeline output back into the UI:

```bash
pip install -r requirements-gui.txt   # installs PySide6
python main.py
```

`python gui.py` still works as a compatibility launcher, but it now forwards to the
same PySide6 entry point.

The frontend exposes the same options as the command line: choose a YouTube URL or
a local file, set the output SRT path and batch size, pick the translation backend
(cloud API or a local llama.cpp server), and — for local files — the SenseVoiceSmall
ASR language and binary/model paths. **Run Translation** executes the pipeline on a
background worker and streams stdout/stderr into the log pane in real time;
**Open Output Folder** opens the generated subtitle location when done. The ASR
binary/model paths default to `./gguf/*.gguf` and the binaries on PATH (override
via the fields or the `FUNASR_*` env vars).

### Building a Windows executable

Package the GUI as a standalone `.exe` (no Python install needed to run it) with
PyInstaller:

```bash
pip install pyinstaller
build_exe.bat          # or run the pyinstaller command inside it directly
```

This produces `dist/TranslationAgent.exe`. The PyInstaller build bundles the QML
files from `ui/qml`, and at runtime the app writes a rotating `debug.log` in the
**same directory as the exe** (startup info, the exact `argv` each run uses,
pipeline stdout/stderr, and any crash tracebacks). Run the exe from that folder so
`debug.log` and any relative model paths resolve correctly.

## How it works

1. The video id is parsed from the URL.
2. `yt-dlp` supplies YouTube's declared original language. The output filename
   uses YouTube's **English-localized title** (fetched via the Innertube player
   API with `hl=en`); when a video has no English title, it falls back to the
   original title.
3. `youtube-transcript-api` resolves the original-language track:
   manual subtitles first, auto-generated captions if no manual track exists.
   If the video has no subtitles at all, the tool exits with a clear message.
4. Cues are translated in batches via the LLM, using numbered items so cue
   order and count stay aligned with the original timestamps. The translator
   follows a **foreignization** philosophy (see `src/translate.py`): it preserves
   the original author's voice, cultural context, honorifics, and period
   register, and never sanitizes, domesticates, or injects modern target-culture
   slang. The source language (from YouTube) is injected into the system prompt.
5. The translated text is written back into the original SRT cues, keeping
   `start`/`end` times intact.

## Notes

- Target language is fixed to English.
- The "original language" is YouTube's declared video language; if that is wrong
  for a given video, results may reflect a different source language.
- Auto-generated captions are accepted when no manual subtitles exist (lower
  fidelity, but wider coverage).

## Local video / audio (no subtitles)

Instead of a YouTube URL you can point at a **local file that has no subtitles at
all**. The audio is transcribed with Alibaba's **SenseVoiceSmall** ASR (via the
FunASR GGUF CPU runtime — no Python or GPU needed at runtime), timed with its
built-in VAD, then translated into English by the same LLM pipeline.

```bash
python translate.py --file my_video.mp4
python translate.py --file clip.mkv --asr-lang ja --out ja_subs.srt
```

### 1. Install ffmpeg
Required to extract a 16 kHz mono WAV from any container (mp4/mkv/webm/mov/mp3/…).
Download from ffmpeg.org and put it on your PATH.

### 2. Get the SenseVoiceSmall GGUF runtime + models
Grab the prebuilt binaries (`llama-funasr-sensevoice`, `llama-funasr-vad`) for your
OS from the FunASR GitHub releases (tags `runtime-llamacpp-v*`), and the models:

```bash
# Option A — download script (fetches the GGUF model + VAD into ./gguf)
bash download-funasr-model.sh sensevoice ./gguf

# Option B — manual, from Hugging Face
huggingface-cli download FunAudioLLM/SenseVoiceSmall-GGUF --include "sensevoice-small-q8.gguf" --local-dir ./gguf
huggingface-cli download FunAudioLLM/fsmn-vad-GGUF --include "fsmn-vad.gguf" --local-dir ./gguf
```

Use `sensevoice-small-q8.gguf` (~235 MB) — same accuracy as `f16` at half the size.
On Windows the binaries are `.exe`; put them on PATH or pass their full path.

### 3. Point the tool at them
Either via environment variables (no flags needed):

```bash
FUNASR_SENSEVOICE_BIN=./bin/llama-funasr-sensevoice \
FUNASR_VAD_BIN=./bin/llama-funasr-vad \
FUNASR_MODEL=./gguf/sensevoice-small-q8.gguf \
FUNASR_VAD_MODEL=./gguf/fsmn-vad.gguf \
  python translate.py --file my_video.mp4
```

…or via flags (`--asr-bin`, `--asr-vad-bin`, `--asr-model`, `--asr-vad-model`).
Defaults if neither is set: the binaries resolved from PATH, and `./gguf/*.gguf`.

| Flag              | Env var                 | Default                          | Meaning                                  |
| ----------------- | ----------------------- | -------------------------------- | ---------------------------------------- |
| `--asr-bin`       | `FUNASR_SENSEVOICE_BIN` | `llama-funasr-sensevoice` (PATH) | Path to the sensevoice binary.           |
| `--asr-vad-bin`   | `FUNASR_VAD_BIN`        | `llama-funasr-vad` (PATH)        | Path to the VAD binary.                  |
| `--asr-model`     | `FUNASR_MODEL`          | `./gguf/sensevoice-small-q8.gguf`| SenseVoiceSmall GGUF model.              |
| `--asr-vad-model` | `FUNASR_VAD_MODEL`      | `./gguf/fsmn-vad.gguf`           | fsmn-vad GGUF model.                     |
| `--asr-lang`      | —                       | `auto`                           | Source language (`auto`/`zh`/`en`/`ja`/`ko`/`yue`). |
| `--asr-threads`   | `FUNASR_THREADS`        | `4`                              | CPU threads for FunASR.                  |
| `--asr-max-segment-ms` | `FUNASR_MAX_SEGMENT_MS` | `7000`                       | Max ASR audio segment before cue splitting. |
| `--asr-max-end-silence-ms` | `FUNASR_MAX_END_SILENCE_MS` | `250`                    | Trailing silence before VAD closes a segment. |
| `--asr-speech-noise-threshold` | `FUNASR_SPEECH_NOISE_THRES` | `0.55`          | FunASR VAD speech/noise threshold.       |
| `--asr-noise-db`  | `FUNASR_NOISE_DB`        | `-35`                            | ffmpeg silencedetect noise threshold (dB). |
| `--asr-min-silence-s` | `FUNASR_MIN_SILENCE_S` | `0.20`                          | Min silence for ffmpeg silence detection. |
| `--asr-max-cue-duration-ms` | `FUNASR_MAX_CUE_DURATION_MS` | `3000`                | Preferred max subtitle cue duration.     |
| `--asr-max-cue-chars` | `FUNASR_MAX_CUE_CHARS` | `70`                            | Preferred max subtitle cue character count. |
| `--asr-no-tags`   | —                       | off                              | Do not request SenseVoice tag output.    |

### How timing works
Audio is extracted to a 16 kHz mono WAV, then a **FunASR VAD pass** yields speech
segments (AGGRESSIVE settings keep them short), refined/fallback via **ffmpeg
silencedetect**, and long speech regions are split into ≤ ~7-second ASR segments.
Each segment is transcribed by **SenseVoiceSmall**. Long recognized text is then
split into **short subtitle cues** on punctuation (target ~3 s / ~70 chars each)
and timed proportionally inside the segment's start/end range — so local output is
a series of short, phrase-sized cues instead of one giant paragraph block. Use
`tools/check_srt.py output.srt` to verify cue count/duration. The original
`start`/`end` times are never altered afterwards — only the `text` is replaced by
the translation.

English-source audio skips translation (the ASR text is written as-is). Translation
can still use your local llama.cpp server via `--local`, exactly as with YouTube.

## Local model (offline)

You can translate without a cloud API by pointing the translator at a local
llama.cpp server. The app bundles a **CPU-only `llama-server`** (in `vendor/llama/`)
and, when you supply a local GGUF via `--local-model` (or pick/download one in the
GUI Settings), it **auto-starts** the server for you — no manual server setup and
no GPU needed. If you prefer to run your own server, just omit `--local-model` and
the tool will connect to the host/port you give it, exactly as before.

### Auto-started server (recommended)

Pick or download the GGUF in Settings, then run with `--local-model`:

```bash
python translate.py "<youtube_url>" --local --local-model models/Hy-MT2-1.8B-1.25Bit.gguf
python translate.py "<youtube_url>" --local --local-port 8080 \
  --local-model-name Hy-MT2-1.8B --local-model models/Hy-MT2-1.8B-1.25Bit.gguf
```

The app starts its bundled CPU `llama-server` against that file, waits until it is
ready, translates, and tears the server down when the app exits.

### Connected to an existing server

If you already run a llama.cpp server yourself (any OpenAI-compatible build):

```bash
# Example with llama-cpp-python (install once: pip install -r requirements-local.txt)
python -m llama_cpp.server --model models/Hy-MT2-1.8B-1.25Bit.gguf --n_ctx 4096
# -> listens on http://127.0.0.1:8080/v1
```

Then just use `--local` (no `--local-model`):

```bash
python translate.py "<youtube_url>" --local
python translate.py "<youtube_url>" --local --local-port 8080 --local-model-name Hy-MT2-1.8B
```

…or purely via environment variables (no flag needed):

```bash
OPENAI_BASE_URL=http://localhost:8080/v1 OPENAI_API_KEY=sk-local OPENAI_MODEL=Hy-MT2-1.8B \
  python translate.py "<youtube_url>"
```

A missing API key is accepted for local (localhost) endpoints — any placeholder works.
If the server isn't running, the tool fails fast with a clear message instead of a
cryptic connection error.

Relevant flags (only used with `--local`):

| Flag                | Default        | Meaning                                                        |
| ------------------- | -------------- | ------------------------------------------------------------- |
| `--local`           | off            | Use a llama.cpp server (auto-started or already running).     |
| `--local-host`      | `127.0.0.1`    | Host of the llama.cpp server.                                  |
| `--local-port`      | `8080`         | Port of the llama.cpp server.                                  |
| `--local-model-name`| `Hy-MT2-1.8B`  | Model id sent to the local server.                            |
| `--local-model`     | —              | Path to a GGUF; when given the app auto-starts bundled CPU `llama-server` against it. |

Notes:
- **STQ kernel:** the default target model, `Hy-MT2-1.8B-1.25Bit-GGUF`, is a 1.25-bit
  **STQ** quantization that needs the llama.cpp STQ kernel (PR #22836). The bundled
  `llama-server` is a recent release build that includes it. If translations come out as
  garbage, your local copy may be stale — use a recent `llama-server`.
- **Sampling:** the model card suggests `temperature 0.7, top_p 0.6, top_k 20,
  repetition_penalty 1.05`. For the cloud path the translator intentionally uses a low
  `temperature 0.3` for translation fidelity. When the model is detected as Hy-MT2
  (model name contains `hy-mt2` / `hy_mt2`, which the local default `Hy-MT2-1.8B` does),
  it instead follows the
  [hy-mt2-translator skill](https://skillhub.cn/skills/hy-mt2-translator): no system
  prompt, the skill's own Chinese instruction wording, and a low `temperature 0.1` (kept
  low so the numbered-item protocol parses deterministically). It also applies the
  model-card `top_p` / `top_k` / `repetition_penalty` via `extra_body`, and — crucially —
  folds the project's **foreignization philosophy** into the prompt as a `style`, so the
  local model preserves the author's voice, culture, and honorifics exactly like the
  cloud path's system prompt. The skill's "context" mode is used when the source language
  is known (passed as background); our numbered-item protocol is kept so cue
  count/order stay aligned. If a backend rejects the llama.cpp-only params
  (`top_k` / `repeat_penalty`), they are dropped and the batch is retried plainly.
- Target language stays English; the original `start`/`end` times and cue count are
  preserved exactly as with the cloud path.

