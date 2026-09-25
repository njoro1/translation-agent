# YouTube Subtitle Translator

> **Last updated:** 2026-09-25 — the UI redesign is complete (single store with
> binding-safe editors, autosave, real Settings category gating, a two-axis Run screen, and
> a run history whose rows reopen a run). 1096 tests collected. The developer reference is
> `AGENT_DOCUMENTATION.md`.

Takes a YouTube URL or a local video/audio file and writes an English SRT/ASS
file named after the video while preserving the original timing. It ships as both
a **command-line tool** and a **desktop GUI** (PySide6 + QML, Windows).

Subtitle selection is **English-first**: if YouTube already provides an English
track (manual or auto-generated), it is used verbatim and translation is
skipped; only when no English track exists does the tool fall back to the video's
original-language track (manual if available, auto-generated as fallback) and
translate it **faithfully into English** using an OpenAI-compatible LLM.

There are exactly three pipeline modes: **YouTube Cloud**, **Local Cloud**
(local ASR + cloud translation) and **Offline** (local ASR + local llama.cpp).
Local translation never silently falls back to the cloud — you pick per run.

## Install

```bash
pip install -r requirements.txt
copy .env.example .env       # then edit .env and fill in your credentials
```

## Configure (`.env`)

| Variable         | Required | Meaning                                                        |
| ---------------- | -------- | ------------------------------------------------------------- |
| `OPENAI_API_KEY` | yes      | API key for your OpenAI-compatible endpoint.                  |
| `OPENAI_MODEL`   | yes      | Model used for translation (e.g. `gpt-5-mini`, or an OpenRouter slug like `openai/gpt-5-mini`). |
| `OPENAI_BASE_URL`| no       | Base URL for any OpenAI-compatible API; leave blank for OpenAI, or `https://openrouter.ai/api/v1` for OpenRouter. |

## Usage

There are exactly three pipeline modes:

```bash
# 1. YouTube -> Cloud: fetch YouTube subtitles, translate with a cloud LLM
python translate.py "<youtube_url>"
python translate.py "<youtube_url>" --model gpt-4o --out my_subs.srt --batch 30

# 2. Local File -> Cloud: transcribe locally (SenseVoiceSmall), translate in the cloud
python translate.py --file my_video.mp4 --asr-lang ja

# 3. Local File -> Fully Offline: local ASR + local llama.cpp translation, no cloud
python translate.py --file my_video.mp4 --asr-lang ja --local
```

- Output is written to `<video_title>.srt` in the current directory by default
  (`--format ass` writes an Aegisub-compatible `.ass` instead).
- `--out` overrides the output path (a `.ass`/`.srt` extension overrides `--format`).
- `--model` overrides `OPENAI_MODEL`.
- `--batch` sets the maximum cues per translation window (default 8; the local
  Hy-MT2 model never puts more than 8 cues in a window, the cloud path 12).
- `--content-preset auto|drama|anime|music|documentary|variety|lecture` tunes
  ASR segmentation, FFmpeg preprocessing, translation context, and prompt style
  for the content type. Explicit flags always override preset values.
- `--context-mode off|light|standard|deep` controls how much surrounding context
  each translation window carries (default: preset/backend).
- `--prompt-profile general|drama|anime|music|documentary|variety|lecture`
  appends one scoped prompt addendum (`general` adds nothing).
- `--asr-preprocess auto|none|basic|loudnorm|denoise` selects FFmpeg audio
  conditioning before ASR; duration-safe with automatic fallback.
- `--result-json <path>` writes a machine-readable result file (cues + quality)
  used by the GUI Review/Quality pages.
- `--json-progress` emits machine-readable `{"type":"progress",...}` lines for the
  GUI (progress bars) without changing the final `Wrote N cues to ...` line.
- ASS output picks a CJK-capable font from the detected source language by default;
  override with `--ass-font <name>` and/or `--ass-fontsize <size>`.
- `--source-lang <code>` forces a specific source language for YouTube subtitles
  (`ja`, `zh`, `zh-TW`, `ko`, `yue`, `en`). A non-English value overrides the
  English-first shortcut and fetches that language's track (manual preferred,
  auto-generated fallback); an error is raised if no track exists in that language.
  For local files it acts as a translation source-language hint when `--asr-lang`
  is left at `auto` or ASR returns an unknown language.
- When `--asr-lang` is left at `auto` for local files, the source CJK language
  (zh/ja/ko) is auto-detected from the transcript and forwarded to the translation
  prompt.

### Downloading the video / subtitle itself

```bash
python translate.py "<youtube_url>" --download-video            # best available
python translate.py "<youtube_url>" --download-video av1        # or vp9 / h264
python translate.py "<youtube_url>" --download-subtitle         # English track
```

`--download-video` takes an optional codec (`best`, `av1`, `vp9`, `h264`). The
codec/resolution pair is honoured exactly or refused with a reason — there is
deliberately no "closest match" substitution. Downloads need `yt-dlp` + `ffmpeg`;
the video and audio streams are merged into one file.

## GUI (Windows)

A desktop frontend built with **PySide6 + QML** wraps the same CLI. The interface
is split into a declarative QML view layer and a Python `QObject` bridge that
streams pipeline output back into the UI:

```bash
pip install -r requirements-gui.txt   # installs PySide6
python main.py
```

`python gui.py` still works as a compatibility launcher, but it forwards to the
same PySide6 entry point.

### Layout

A 56 px command bar, a 64 px icon rail, a flexible workspace and a 30 px status
bar. Five screens, all kept alive:

| Screen | What it does |
| --- | --- |
| **Run** | Three columns on one scroll. **Source** — two independent selectors, *Source* (YouTube URL / local media file) and *Engine* (cloud LLM / local model), then the URL + preview or the local drop zone. The panel keeps a constant height, so switching source swaps content, not layout. **Processing** — output path/format, model state, context mode, batch, glossary, translation memory, the strict-quality gate, the content-preset chips, the `Source → Transcribe → Translate → Gate → Write` stage strip, and model downloads as secondary actions. **Inspector** — the readiness checklist (a validator, not a numbered step), error card, progress ring + stage stepper, last-run summary, live log. |
| **Review** | Virtualized cue table (filter All / OK / Warnings / Failed with live counts, search, inline editing), a cue timeline synced to the table selection, a master–detail cue inspector with ±50 ms timing nudges and auto-fix, and find & replace (optional regex, live match count). Edits can be saved back to `.srt`/`.ass`. |
| **Quality** | Score ring + labelled metric chips (click one for its breakdown), the issue list with severity filters (click an issue to jump to that cue), CPS and duration histograms, the strict-quality gate, the active thresholds, the run context, and JSON/CSV exports. |
| **Log** | Run history — timestamp, source, engine and outcome per run — beside a full-height console with tone filters and copy/export/clear. **Clicking a run loads it back into Review and Quality**, so a previous run is readable, not just listed. |
| **Settings** | Seven categories — Appearance, Translation, Transcription, Models & storage, Shortcuts, Data & privacy, About — with real gating: only the selected category renders, and the in-category filter searches just that category. Destructive actions live in a separated danger zone that requires typing what will be erased. |

Other things worth knowing:

- **Command palette** — `Ctrl+K` exposes 42 entries in four namespaces: **Navigate** (the
  five screens, plus a deep link into every Settings category), **Actions** (run, cancel,
  export, re-check, open, purge…), **Toggles** (theme, strict gate, rolling summary, reduce
  motion — each showing its current value, not just its name), and **Jump-to-setting**
  (typing `api key`, `batch` or `model path` lands on the exact field and focuses it).
- **Keyboard** — `Ctrl+1…4` screens, `Ctrl+,` Settings, `Ctrl+K` palette, `Ctrl+R` run,
  `Ctrl+.` cancel, `Ctrl+S` save edited subtitles, `Ctrl+F` search cues, `Ctrl+L` log.
- **Settings save themselves.** There is no Save button; a change is written shortly after
  you stop editing, and the top bar says whether anything is still pending.
- **Themes** — dark (default) and light, five accent colours, a comfortable density mode
  and a reduced-motion toggle. All of it persists across launches.
- **Model state is honest** — every model file is validated (GGUF header + tensor table),
  so a half-finished download reads as *corrupt* rather than *ready*, and the Run button
  states why it is disabled instead of launching a doomed run. Downloads are offered from
  the Processing panel.
- **Failures are explained** — a failed run produces a structured card with a code, a plain
  title, the offending log line and a remedy button (check credentials, retry, download a
  model, install a dependency, …).
- **Offline mode never receives credentials.**
- **Stop is cooperative** — the run stops at the next batch boundary, no output file is
  written, and the next run starts cleanly.

### Building a Windows executable

Package the GUI as a standalone `.exe` (no Python install needed to run it) with
PyInstaller:

```bash
pip install pyinstaller
build_exe.bat          # or run the pyinstaller command inside it directly
```

This produces an onedir bundle at `dist/TranslationAgent/TranslationAgent.exe`
(deliberately not `--onefile`: re-extracting the bundle to `%TEMP%` on every launch is
what caused the `Failed to extract Crypto…` error). The bundle is roughly 850 MB on
disk, and the build deletes and rewrites it, so have about 1 GB free.

The PyInstaller build bundles the QML files from `ui/`, the vendored FunASR and
llama.cpp binaries, and a CPU ffmpeg. At runtime the app writes a rotating `debug.log`
in the **same directory as the exe** (startup info, the exact `argv` each run uses,
pipeline stdout/stderr, and any crash tracebacks). Run the exe from that folder so
`debug.log` and any relative model paths resolve correctly.

## How it works

1. The video id is parsed from the URL.
2. `yt-dlp` supplies YouTube's declared original language. The output filename
   uses YouTube's **English-localized title** (fetched via the Innertube player
   API with `hl=en`); when a video has no English title, it falls back to the
   original title.
3. `youtube-transcript-api` resolves subtitles:
   - **English-first:** if YouTube already provides an English subtitle track
     (manual or auto-generated), it is used verbatim and translation is skipped.
   - **Original-language fallback:** when no English track exists, the video's
     original-language track is fetched (manual subtitles first, auto-generated
     captions as fallback).
   If the video has no subtitles at all, the tool exits with a clear message.
4. Cues are translated in context-aware windows via the LLM, using numbered items
   so cue order and count stay aligned with the original timestamps. Each window
   carries read-only before/after context (previous translated pairs, upcoming
   source lines) so pronouns, speaker continuity, and named entities stay
   consistent. The translator follows a **foreignization** philosophy (see
   `src/translate.py`): it preserves the original author's voice, cultural
   context, honorifics, and period register, and never sanitizes, domesticates,
   or injects modern target-culture slang. The source language (from YouTube) is
   injected into the system prompt.
5. Translation failures (empty replies, source echoes, CJK residue) are never
   silently shipped — failed cues are marked `[untranslated]`, counted, logged
   with their source text, and surfaced in the quality report and the GUI Review page.
6. A post-processing pass runs line breaking (English word-boundary splitting),
   overlap snapping, translator-note placement, fused-English repair, residual
   CJK stripping, and literal-gloss cleanup.
7. The translated text is written back into the original cue timestamps, keeping
   `start`/`end` values intact — with the single exception that the post-processing
   overlap snap trims a cue's `end` only when consecutive cues overlap (never below
   300 ms), so overlapping cues are corrected without disturbing `start` times.

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
| `--asr-max-segment-ms` | `FUNASR_MAX_SEGMENT_MS` | `6000`                       | Max ASR audio segment before cue splitting. |
| `--asr-max-end-silence-ms` | `FUNASR_MAX_END_SILENCE_MS` | `250`                    | Trailing silence before VAD closes a segment. |
| `--asr-speech-noise-threshold` | `FUNASR_SPEECH_NOISE_THRES` | `0.55`          | FunASR VAD speech/noise threshold.       |
| `--asr-noise-db`  | `FUNASR_NOISE_DB`        | `-35`                            | ffmpeg silencedetect noise threshold (dB). |
| `--asr-min-silence-s` | `FUNASR_MIN_SILENCE_S` | `0.25`                          | Min silence for ffmpeg silence detection. |
| `--asr-max-cue-duration-ms` | `FUNASR_MAX_CUE_DURATION_MS` | `3200`                | Preferred max subtitle cue duration.     |
| `--asr-max-cue-chars` | `FUNASR_MAX_CUE_CHARS` | `70`                            | Preferred max subtitle cue character count (non-CJK). |
| `--asr-max-cue-chars-cjk` | `FUNASR_MAX_CUE_CHARS_CJK` | `48`                    | Preferred max subtitle cue character count (CJK). |
| `--asr-no-tags`   | —                       | off                              | Do not request SenseVoice tag output.    |
| `--asr-keep-tags` | `FUNASR_KEEP_TAGS`      | off                              | Keep ASR `<|...|>` tags (disable default tag stripping). |

### How timing works
Audio is extracted to a 16 kHz mono WAV with **loudnorm** normalization,
then a **FunASR VAD pass** yields speech segments (AGGRESSIVE settings keep them
short), refined/fallback via **ffmpeg silencedetect**, and long speech regions
are split into ≤ ~6-second ASR segments. Each segment is transcribed by
**SenseVoiceSmall**. Long recognized text is then split into **short subtitle
cues** on punctuation using CJK-weighted character budgets (target ~3 s / ~70
chars non-CJK, ~48 CJK chars by default) and timed proportionally inside the
segment's start/end range — so local output is a series of short, phrase-sized
cues instead of one giant paragraph block. For video files, cues are optionally
snapped to the nearest keyframe (±100 ms) to prevent mid-scene-cut subtitles.

The pipeline warns when the last cue ends well before the media duration (a sign
the ASR run stopped early).

Use `tools/check_srt.py output.srt` to verify cue count/duration.

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
python translate.py "<youtube_url>" --local --local-model models/Hy-MT2-1.8B-Q8_0.gguf
python translate.py "<youtube_url>" --local --local-port 8080 \
  --local-model-name Hy-MT2-1.8B-Q8_0 --local-model models/Hy-MT2-1.8B-Q8_0.gguf
```

The app starts its bundled CPU `llama-server` against that file, waits until it is
ready, translates, and tears the server down when the app exits.

### Connected to an existing server

If you already run a llama.cpp server yourself (any OpenAI-compatible build):

```bash
# Example with llama-cpp-python (install once: pip install -r requirements-local.txt)
python -m llama_cpp.server --model models/Hy-MT2-1.8B-Q8_0.gguf --n_ctx 4096
# -> listens on http://127.0.0.1:8080/v1
```

Then just use `--local` (no `--local-model`):

```bash
python translate.py "<youtube_url>" --local
python translate.py "<youtube_url>" --local --local-port 8080 --local-model-name Hy-MT2-1.8B-Q8_0
```

…or purely via environment variables (no flag needed):

```bash
OPENAI_BASE_URL=http://localhost:8080/v1 OPENAI_API_KEY=sk-local OPENAI_MODEL=Hy-MT2-1.8B-Q8_0 \
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
| `--local-model-name`| `Hy-MT2-1.8B-Q8_0`  | Model id sent to the local server.                            |
| `--local-model`     | —              | Path to a GGUF; when given the app auto-starts bundled CPU `llama-server` against it. |
| `--local-threads`   | `0`            | CPU threads for the local server (`LLAMA_SERVER_THREADS`; 0 = let llama.cpp decide). |
| `--local-mlock`     | off            | Lock the model in RAM (`--mlock`; `LLAMA_SERVER_MLOCK`).       |

Notes:
- **Quantization:** the default target model is the `Hy-MT2-1.8B-Q8_0.gguf` **Q8_0**
  quantization, a standard llama.cpp format supported by the bundled `llama-server`. If
  translations come out as garbage, your local copy may be stale — use a recent
  `llama-server`.
- **Sampling:** the model card suggests `temperature 0.7, top_p 0.6, top_k 20,
  repetition_penalty 1.05`. For the cloud path the translator intentionally uses a low
  `temperature 0.3` for translation fidelity. When the model is detected as Hy-MT2
  (model name contains `hy-mt2` / `hy_mt2`, which the local default `Hy-MT2-1.8B-Q8_0` does),
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

## Consistency & quality features

These are **optional, off-line-friendly** aids that improve the local translation
path without replacing the model.

### Translation windows (context-first)

Cues are translated as context-aware windows rather than isolated batches. Each
window carries read-only context — previously translated pairs and the next
source lines — so pronouns, speaker continuity, and named entities stay
consistent across cuts:

- `--context-mode off|light|standard|deep` (default: `standard` for both
  backends — benchmark-verified safe for the local Hy-MT2 model; use `light`
  for minimal prompts or `deep` for long-form cloud content).
- Windows split on cue count, character budget, duration, and scene gaps
  (≥ 0.8 s of silence), never dropping or reordering cues.
- A rolling memory of recent translated pairs feeds later windows.
- `--content-preset auto|drama|anime|music|documentary|variety|lecture` tunes
  ASR, FFmpeg preprocessing, context level, and a scoped prompt addendum in one
  flag; explicit flags always override preset values.
- `--context-summary` (cloud only, experimental) maintains a short rolling
  scene summary included as read-only context.

### Translation memory

Repeated exact source lines (greetings, catchphrases, opening/ending lines) are
cached in a SQLite database and reused, so they are not re-translated each time.

```bash
python translate.py "<url>" --translation-memory on
python translate.py --file clip.mkv --local --translation-memory-db ./cache/tm.sqlite3
```

- `--translation-memory auto` (default): on for local Hy-MT2, off for cloud.
- `--translation-memory on` / `off`: force it.
- `--translation-memory-db` / `TRANSLATION_MEMORY_DB` (default `./cache/translation_memory.sqlite3`).
- Cache keys include the source language, model, and glossary hash, so a glossary
  or model change invalidates stale entries.
- A window whose cues are all exact cache hits is served entirely from the
  cache; a partially-hit window is translated whole so context stays coherent,
  and the fresh translations overwrite the cached entries.
- **Poisoned entries are purged** on startup: source-text passthroughs (where the
  "translation" is identical to the source) and entries with leaked ASR/markup
  tags (`[CHENGYU:`, `<|...|>`) are automatically removed so a bad past run never
  poisons future runs.
- Corrupt databases degrade gracefully.

### Glossary

Enforce consistent terminology with a plain-text glossary file:

```bash
python translate.py "<url>" --glossary my_terms.txt
```

Format (`#` comments, `TAB`, `=` or `->` separators, UTF-8):

```text
# terms
先輩 = senpai
先生 -> sensei
魔法少女	magical girl
```

The glossary is injected into the prompt without altering the foreignization
directive. `TRANSLATION_GLOSSARY` sets it via the environment.

### Cloud rescue (removed)

Cloud rescue was removed by product decision. There is no mixed mode where local
translation silently falls back to a cloud model: you choose cloud translation
or local translation per run (the three pipeline modes are YouTube Cloud, Local
Cloud, and Offline). Failed cues are clearly marked `[untranslated]`, counted in
the quality report, and visible in the GUI Review page instead.

### Subtitle quality diagnostics

A built-in analyzer reports readability issues: characters-per-second (CPS),
over-long/over-short cues, excessive lines, and empty text.

```bash
python translate.py "<url>" --quality-report report.json
python translate.py "<url>" --strict-quality   # exit 1 if serious errors found
```

Thresholds: CPS warning 18 / error 22; chars warning 80 / error 110; duration
min 0.8/0.5 s and max 6/8 s; lines warning 2 / error 3. Output is a JSON report
and a console summary (`tools/check_srt.py` gives a quick cue-count/duration
overview).

### Local server warmup & tuning

After the local server starts, a tiny warmup request initializes the model and
reduces first-request latency. Optional flags:

- `--local-threads` / `LLAMA_SERVER_THREADS` (0 = auto).
- `--local-mlock` / `LLAMA_SERVER_MLOCK` (lock model in RAM).

If the server rejects an optional flag, it is automatically retried without it.

## Benchmarking

`tools/benchmark.py` measures timing, reliability, and subtitle quality against
`benchmark/cases.json`:

```bash
python tools/benchmark.py --cases benchmark/cases.json --output benchmark/results/run.json
python tools/benchmark.py --case-id ja-short-dialogue --local
```

To choose an ASR preprocessing profile with evidence, `tools/benchmark_preprocess.py`
runs the same media through each FFmpeg profile (none/basic/loudnorm/denoise) and
reports cue counts, average cue duration, text volume, processing time, and — with
a reference transcript (`--reference ref.srt`) — CER/WER:

```bash
python tools/benchmark_preprocess.py --media sample.mp4 --asr-lang ja \
    --out-dir bench_preprocess --reference ref.srt --json bench.json
```

See `benchmark/README.md` for how to add your own test media. The harness runs
offline and needs no real API keys to start; missing media files produce clear
errors. Results are JSON so they can be diffed between runs.

## Environment variables (summary)

| Variable | Default | Purpose |
|---|---:|---|
| `TRANSLATION_GLOSSARY` | unset | Glossary file path |
| `TRANSLATION_MEMORY_MODE` | `auto` | `auto` \| `on` \| `off` |
| `TRANSLATION_MEMORY_DB` | `./cache/translation_memory.sqlite3` | TM database path |
| `TRANSLATION_CONTEXT_MODE` | unset | Context mode override (auto preset only) |
| `TRANSLATION_PROMPT_PROFILE` | unset | Prompt profile override (auto preset only) |
| `FUNASR_PREPROCESS` | unset | Preprocessing profile override (auto preset only) |
| `FUNASR_THREADS` | CPU-derived (`max(2, min(4, cores))`) | ASR CPU threads |
| `FUNASR_MAX_CUE_CHARS_CJK` | `48` | CJK max cue chars |
| `FUNASR_KEEP_TAGS` | `0` | Keep ASR tags (1 = on) |
| `FUNASR_INCOMPLETE_WARN_SECONDS` | `8.0` | Min uncovered tail to warn about |
| `FUNASR_FORCE_FFMPEG_VAD` | `0` | Force ffmpeg VAD (skip binary VAD) |
| `FFMPEG_BIN` / `FFPROBE_BIN` | on PATH | ffmpeg / ffprobe binary override |
| `IMAGEIO_FFMPEG_EXE` | unset | Alternative ffmpeg path |
| `LLAMA_SERVER_THREADS` | `0` | Local server threads |
| `LLAMA_SERVER_MLOCK` | `0` | Local server mlock (1 = on) |
| `YT_DLP_BIN` | unset | Explicit yt-dlp executable |
| `YT_DLP_INPROC` | unset | Force the in-process yt-dlp path |

Removed variables (do not reintroduce): `CLOUD_RESCUE_ENABLED`,
`CLOUD_RESCUE_MODEL`, `CLOUD_RESCUE_BATCH`, `CLOUD_RESCUE_API_KEY`,
`CLOUD_RESCUE_BASE_URL`. Cloud rescue was removed by product decision.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success — the subtitle file was written |
| `1` | Runtime error (fetch, transcription, translation or write failure; `--strict-quality` violation) |
| `2` | Configuration error (missing key/model, bad preset, neither a URL nor `--file`) **or** the run was cancelled |

## Model note

Hy-MT2-1.8B remains the default local translation model because it provides the
best practical balance of size, CPU feasibility, and translation specialization
for the target hardware (a small model loaded on CPU). The preferred file is
`Hy-MT2-1.8B-Q8_0.gguf`. A model swap is only accepted with benchmark evidence
that the replacement is both more accurate **and** faster/equal at equal-or-lower
resource usage.

### Troubleshooting: `llama-server exited before becoming ready (rc=1)`

If startup fails with `rc=1` and the server stderr mentions *failed to read tensor
data* / *tensor offset*, the GGUF file is **corrupt or truncated** — re-download
it:

- **GUI:** Settings → Download models (or delete the file and retry).
- **Manual:** <https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q8_0.gguf>

If the stderr mentions an unsupported quantization, ensure you're using the
app's bundled `llama-server` (under `vendor/llama/`), which supports the Q8_0
quantization used by the default local model.

The GUI's **Settings → Models & storage** section shows the state of every model
file (`ready` / `missing` / `corrupt`) and offers a one-click re-download — a
truncated file is detected before a run starts, not 60 seconds into one.

## Development

```bash
python -m pytest -q --basetemp="C:/Users/<you>/AppData/Local/Temp/ta_pytest"
python tools/check_srt.py output.srt
```

1096 tests collected. No network, API keys or vendor binaries are needed. Three
tests in `tests/test_packaged_exe_smoke.py::TestBuildIsCurrent` fail until
`dist/TranslationAgent/` is rebuilt — that is the intended signal that the
shipped bundle predates the current sources, not a code defect; the other
packaged-exe tests skip themselves when the bundle is absent. Always pass a
Windows `--basetemp` path — without it pytest's temp cleanup is blocked by the
sandbox and the run dies before printing a summary.

`AGENT_DOCUMENTATION.md` is the consolidated developer reference: repository
layout, module-by-module API, the full CLI/env/QSettings tables, build details,
design invariants and known issues. Read it before changing anything structural.

`mockups/` holds the static HTML design proposal the current UI was built from
(open `mockups/index.html`); it is documentation, not application code.

