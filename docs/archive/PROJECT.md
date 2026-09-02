# Translation Agent — Project Documentation

> A detailed, developer-oriented description of the **Translation Agent** project as it
> stands today. It complements the user-facing `README.md` by covering the architecture,
> the current state of the code, the history of how it evolved, and the known gaps /
> inconsistencies that a future contributor should be aware of before diving in.

---

## 1. What the project does

**Translation Agent** (internally branded **"YouTube Subtitle Translator"**) is a
Windows-focused tool that turns **video content** into **English subtitles** (SRT) in
three complementary ways:

1. **YouTube subtitles → translation.** Given a YouTube URL, it fetches the video's
   **original-language** subtitles (manual captions preferred, auto-generated as fallback),
   translates them **faithfully into English** using an OpenAI-compatible LLM, and writes
   an `.srt` file whose timing exactly matches the original.
2. **Local media → transcription → translation.** Given a local `mp4`/`mkv`/`webm`/`mov`/
   `mp3`/… file with **no subtitles**, it extracts the audio, transcribes it into timed cues
   with a local **FunASR + SenseVoiceSmall** CPU runtime, then translates to English.
3. **Online or fully offline translation backends.** It can call **any OpenAI-compatible
   cloud API** (OpenAI, OpenRouter, etc.) or a **local llama.cpp server** (auto-started and
   bundled) serving a translation model such as Tencent's **Hy-MT2** — so it works entirely
   offline with no GPU.

The GUI (`main.py`, PySide6 + QML) is a modern desktop frontend that wraps the same CLI
pipeline as a background worker, streams its output live into a log pane, and offers
one-click model downloads.

---

## 2. Repository layout

```
translation-agent/
├── main.py                     # PySide6 + QML GUI entry point (canonical)
├── gui.py                      # Compatibility launcher -> calls main.main()
├── translate.py                # CLI entry point (top level, imports src/)
├── build_exe.bat               # PyInstaller one-file Windows build script
├── TranslationAgent.spec       # PyInstaller spec (generated reference)
│
├── src/                        # CLI pipeline (framework-free Python)
│   ├── config.py               # .env loading + OpenAI client construction
│   ├── fetch_subs.py           # YouTube subtitles/title/source-language fetch
│   ├── srt_io.py               # Cue dataclass + SRT read/write + filename sanitize
   │   ├── translate.py            # Faithful English translation (batched, LLM)
   │   ├── batching.py             # Character-aware batch splitting for small CPU models
   │   ├── glossary.py              # Source→target terminology file parser + prompt formatter
   │   ├── translation_memory.py   # SQLite-backed exact-match translation cache
   │   ├── subtitle_quality.py      # CPS / duration / char-count / empty-cue diagnostics
   │   ├── rescue.py                # Optional cloud re-translation of failed cues
   │   ├── local_asr.py            # Local file transcription (FunASR / ffmpeg)
   │   ├── local_server.py         # Auto-start a bundled CPU-only llama-server
   │   ├── postprocess.py          # Fansub post-processing (line breaks / overlap snap / TN)
   │   ├── cjk.py                  # CJK script detection + kinsoku-aware line breaking
   │   └── ass_io.py               # Aegisub-compatible Advanced SubStation Alpha writer
│
├── backend/                    # GUI bridge layer (QObject / QRunnable workers)
│   ├── bridge.py               # AppBridge: QML <-> Python state + pipeline runner
│   ├── controllers/
│   │   └── translation.py      # TranslationWorker (QRunnable) + _SignalWriter
│   └── models/
│       └── run_config.py       # RunConfig dataclass (argv + env for a run)
│
├── ui/qml/                     # Qt Quick declarative frontend
│   ├── Main.qml                # Top-level ApplicationWindow + StackView
│   ├── components/             # Card, CustomTextField, PrimaryButton, Sidebar, StyledRadioButton
│   └── views/                  # DashboardView, SettingsView
│
├── vendor/                     # Bundled binaries (present locally; untracked, not git-ignored)
│   ├── funasr/                  # llama-funasr-sensevoice.exe + llama-funasr-vad.exe + DLLs
│   ├── llama/                  # llama-server.exe + DLLs (local translation)
│   └── funasr/                 # llama-funasr-*.exe binaries + download script (ARCHIVED, see §8.1)
│
├── requirements.txt            # Core deps (CLI + GUI)
├── requirements-gui.txt        # PySide6 only (GUI)
├── requirements-local.txt      # Optional: llama-cpp-python[server]
├── .env.example                # Template for .env (git-ignored)
├── .env                        # Local secrets (never committed)
├── .gitignore
│
├── README.md                   # User-facing usage guide
├── CLAUDE.md                   # Agent/human onboarding notes + invariants
├── "frontend migration guide.txt"  # Blueprint used for the CustomTkinter -> QML rewrite
├── PROJECT.md                  # THIS FILE
│
├── dist/                       # PyInstaller output (git-ignored): TranslationAgent.exe
├── build/                      # PyInstaller intermediates (git-ignored)
└── gguf/                       # Downloaded GGML/GGUF models (git-ignored)
```

> Note: `vendor/` is **untracked** (present in the working tree but not committed, and not
> covered by `.gitignore`). `build_exe.bat` checks for `vendor/funasr/llama-funasr-sensevoice.exe`
> and `vendor/llama/llama-server.exe` and aborts with a clear message if they are missing, so
> they must be present before a standalone build.

---

## 3. Two entry points, one pipeline

### 3.1 CLI — `translate.py`

```
python translate.py "<youtube_url>" [--model ...] [--out path.srt] [--batch 8]
python translate.py --file video.mp4 [--asr-lang ja] [--asr-model ...] [--out path.srt]
python translate.py "<youtube_url>" --local [--local-model models/Hy-MT2-1.8B-Q8_0.gguf]
```

The CLI is deliberately thin: it parses arguments, fetches/transcribes cues, builds an
OpenAI client, calls `src.translate.translate_cues`, and writes the SRT. It produces a
stable, human/machine-readable output contract:

- `Fetched {N} cues. Translating into English...` — start
- `translated {done}/{total}` — per-batch progress
- `Wrote {N} cues to {path}` — final line (**the GUI keys off this line** via a regex)

### 3.2 GUI — `main.py` (+ `gui.py` shim)

`gui.py` is a one-liner that imports `main.main()` so old invocations keep working; the
canonical command is `python main.py`.

`main.py`:
- Creates a `QGuiApplication`, sets up a **rotating `debug.log`** (in the app directory).
- Resolves the PySide6 **QML import path and plugin path** for both dev (`PySide6/qml`) and
  frozen (`sys._MEIPASS/PySide6/qml`) environments, with sensible fallbacks.
- Instantiates a single `AppBridge` `QObject`, exposes it to QML as `appBridge` via the
  root context, and loads `ui/qml/Main.qml`.
- Hooks `app.aboutToQuit` → `shutdown_servers()` so any bundled `llama-server` the app
  started is torn down on exit.
- Installs an `excepthook` so uncaught exceptions end up in `debug.log`.

---

## 4. The CLI pipeline (`src/`)

### 4.1 `src/config.py` — settings & client

- Loads `.env` via `python-dotenv` (`load_dotenv()`), so environment variables take
  precedence and secrets never live in code.
- Reads `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`.
- **Local-endpoint special case:** for `localhost` / `127.0.0.1` / `::1` / `0.0.0.0` /
  `*.localhost` hosts, a missing API key is replaced with the placeholder `sk-local` — a
  local server doesn't need a real key. Remote endpoints throw a clear `RuntimeError` if
  the key is missing.
- `make_client()` builds the `openai.OpenAI` client, and when the base URL contains
  `openrouter`, adds OpenRouter's recommended attribution headers.

### 4.2 `src/srt_io.py` — core data type

- `Cue` dataclass: `start` (s), `end` (s), `text`. **This is the single shared data shape**
  used by every source (YouTube fetch, local ASR) and both translated/untranslated paths.
- `sanitize_filename()` strips Windows/Unix-unsafe characters, collapses whitespace, bounds
  length to ≤180 chars.
- `write_srt()` / `read_srt()` handle `HH:MM:SS,mmm` timestamps; the reader tolerates BOM,
  blank lines, and multi-line cue text (joined with spaces). Reading is used by
  `local_asr.py` to parse the FunASR SenseVoice output into `Cue` objects.

### 4.3 `src/fetch_subs.py` — YouTube path

Flow:
1. `extract_video_id()` parses `watch`, `youtu.be`, `shorts`, and `embed` URL forms.
2. `_yt_dlp_metadata()` shells out to `yt-dlp --print "%(title)s|%(language)s"` to get the
   declared original language and title.
3. **English-first:** `_resolve_english_transcript()` checks for an existing English
   subtitle track (manual preferred, then auto-generated). If one is found, the cues
   are returned verbatim with `source_language_code="en"` and the caller skips
   translation.
4. When no English track exists, `_resolve_transcript()` fetches the video's
   original-language track (manual first, auto-generated as fallback, then first
   available track as a last resort).
5. `_fetch_english_title()` calls YouTube's **Innertube player API** with `hl=en` to get the
   **English-localized title** for the output filename (falling back to the original title).
   The Innertube key is a public web-client key; if it ever stops working the code fails
   gracefully to the original title.
6. Cues are built from the transcript snippets preserving `start`/`end`.

Returns `(cues: list[Cue], english_title, source_language_code)`. Errors surface as
`RuntimeError`/`ValueError` with actionable messages (the CLI prints them and exits
non-zero).


### 4.4 `src/local_asr.py` — local media path (FunASR + SenseVoiceSmall)

This is the **live** local-file transcription module. It uses **FunASR** (SenseVoiceSmall
GGUF + FSMN-VAD) as the only local ASR runtime — no Whisper, no PyTorch, CPU-only.

Flow:
1. `_extract_wav()` converts any container to a 16 kHz mono 16-bit WAV via **ffmpeg**
   (resolved from `FFMPEG_BIN`, bundled/`IMAGEIO_FFMPEG_EXE`, `imageio_ffmpeg`, or PATH),
   applying **loudnorm** normalization before VAD sees the audio.
2. `_prepare_segments()` runs a **FunASR FSMN-VAD** pass (aggressive settings: max segment
   ~6 s, max end silence ~250 ms, speech/noise threshold ~0.55), with **ffmpeg
   silencedetect** as fallback/refiner, and splits long speech regions into shorter ASR
   segments.
3. Each segment is cut out and transcribed by `llama-funasr-sensevoice`.
4. `_segment_to_cues()` splits long recognized text into **short cues** on punctuation
   using CJK-weighted character budgets (each CJK codepoint counts double, so the CJK
   limit of 48 ≈ 24 full-width characters) and distributes the timing proportionally
   inside the segment.
5. For video containers, cues are snapped to the nearest **keyframe** (±100 ms, via
   ffprobe) so subtitles never appear mid-scene-cut; the pass is skipped when ffprobe
   or keyframes are unavailable and is never fatal.
6. `maybe_warn_incomplete()` warns when the last cue ends well before the media
   duration (a sign the ASR run stopped early).
7. Source language is detected from the SenseVoice tag group (or taken from `--asr-lang`);
   `yue`→Cantonese, `zh`→Chinese, etc. Returns `tuple[list[Cue], str | None]`.

Config resolution order is *flag → env → bundled/default* (`FUNASR_SENSEVOICE_BIN`,
`FUNASR_VAD_BIN`, `FUNASR_MODEL`, `FUNASR_VAD_MODEL`, `./gguf/*.gguf`).

### 4.4b `src/postprocess.py` — fansub post-processing

Runs after translation and before writing output, over the final cue list:

- `break_lines(text, max_chars=37)` — splits a long line into at most 2 lines at the
  word boundary nearest the midpoint, using `\\N` as the separator (ASS convention).
- `format_translator_note(text)` — moves a `[TN: ...]` annotation onto its own line.
- `snap_overlaps(cues, gap_ms=50)` — trims the previous cue's `end` so consecutive
  cues keep a minimum separation, never trimming a cue below 300 ms.
- `apply_all(cues)` — runs the steps in order and returns exactly the same number
  of cues it receives (no merging or dropping).

SRT output converts `\\N` to a literal newline; ASS output keeps `\\N`.

### 4.4c `src/ass_io.py` — Advanced SubStation Alpha writer

Writes Aegisub-compatible `.ass` files with a sensible default style (1920×1080
PlayRes, bottom-centred white text, black outline + shadow). `write_ass(path, cues)`
returns the number of cues written. Enabled via `--format ass` (or a `.ass` output
path). Line breaks are emitted as `\\N`.

### 4.4d `src/batching.py` — character-aware batch splitting

`chunk_texts()` splits cue texts into model-safe batches (by item count and
non-whitespace character budget, CJK-aware limits), never reordering or dropping
indices. `is_cjk_language()` and `estimate_text_weight()` support it. Used to cap
Hy-MT2 requests at ≤ 12 cues / ≤ 700 CJK chars (env-overridable).

### 4.4e `src/glossary.py` — terminology consistency

`load_glossary()` parses a plain-text `source → target` glossary (TAB / `->` / `=`
separators, `#` comments, capped at 80 entries / 2000 chars); `format_glossary()`
renders the prompt block; `glossary_hash()` fingerprints entries for cache keys.

### 4.4f `src/translation_memory.py` — SQLite translation cache

`TranslationMemory` stores exact-match `(source_language, model_profile,
glossary_hash, normalized_source) → translation` rows. Passthrough "translations"
are never stored, and **poisoned entries** (source echoes, leaked `[CHENGYU:` /
`<|...|>` markup) are purged on startup. Degrades gracefully to disabled on any
SQLite error.

### 4.4g `src/subtitle_quality.py` — subtitle diagnostics

`analyze_cues()` flags CPS / duration / character-count / line-count / empty-text
issues per cue (warning vs error thresholds); `build_report()` aggregates them
plus the explicit `untranslated_count`; `print_summary()` prints the console
summary. Serialized to JSON via `--quality-report`; `--strict-quality` exits
non-zero on serious errors.

### 4.4h `src/rescue.py` — cloud rescue

`rescue_failed_cues()` re-translates **only** the cues that failed local
translation, via a cloud OpenAI-compatible client, using the same numbered-item
protocol, output validation (`looks_untranslated`), and per-item fallback.
Returns `{cue_index: translation}` for rescued cues only. Enabled with
`--cloud-rescue` / `--cloud-rescue-model` / `--cloud-rescue-batch`.


### 4.5 `src/translate.py` — the heart (faithful English translation)

This is where the translation policy lives.

**Cue alignment protocol.** Cues are translated in **batches** (default 8) for context and
token efficiency. Each batch is sent as **numbered items** (`1. text`, `2. text`, …) and
the model is told to reply with the *same numbers, one per line* — `_parse_numbered()`
verifies the returned keys are exactly `{1..N}`. This keeps cue **order and count** aligned
with the original timestamps.

**Failure handling (defense in depth):**
- Transient API errors: retried up to 3 times with exponential backoff (`time.sleep(2**attempt)`).
- Backend rejecting llama.cpp-only params: drops `extra_body` and retries plainly.
- If a batch still fails/misaligns, it falls back to **per-item translation**
  (`_translate_one`) so no cue is ever lost.

**The foreignization directive (`_FOREIGNIZATION_DIRECTIVE`).** The system prompt is a
strong instruction to preserve the author's voice, cultural context, honorifics, and period
register; **never** sanitize/domesticate/inject modern slang or inject target-culture
political commentary. It also defines a `[Translator's Note]` convention for untranslatable
puns/wordplay. `build_system_prompt(source_language)` fills the `[SOURCE LANGUAGE]` /
`[TARGET LANGUAGE]` placeholders. **This directive is a core invariant — preserve it when
editing translation logic.**


**Hy-MT2 special path.** When the model name contains `hy-mt2`/`hy_mt2` (the local default),
the code switches to the **hy-mt2-translator skill** recipe instead of the cloud system
prompt:
- No system prompt; a single Chinese user message (Hy-MT2 is a Chinese-trained MT model).
- Uses "context"/"basic" modes depending on whether the source language is known.
- Uses the model-card sampling params via `extra_body`: `temperature 0.1`, `top_p 0.6`,
  `top_k 20`, `repeat_penalty 1.05` (temperature kept low so the numbered-item protocol
  parses deterministically).
- Folds the **same foreignization philosophy** into the prompt in Chinese
  (`_HY_MT2_STYLE`) so the local model honors the same "keep the author's voice" invariant.

**English source short-circuits translation.** `translate.py`/CLI detect an English source
and write the ASR/subtitle text **as-is** (no remote call).

### 4.6 `src/local_server.py` — auto-started local llama.cpp

Used for `--local --local-model <file.gguf>`:
- Resolves the **bundled CPU-only `llama-server`** from `vendor/llama/` (or `_MEIPASS`), or
  whatever is on PATH as a fallback.
- `ensure_local_server()` starts it with `-ngl 0` (CPU only, `N_GPU_LAYERS = 0` for full
  compatibility), `--ctx-size 4096`, and polls `/health` until ready (up to 180 s), failing
  fast if the process dies early.
- If a server is **already** listening on the host/port, it is **reused** (`how="reuse"`)
  rather than restarted.
- Tracks every process it started in a module-level `_ACTIVE` dict and **terminates the
  whole process tree** (`taskkill /F /T` on Windows) via `shutdown_servers()`, registered
  with `atexit` and wired into the GUI's `aboutToQuit`.

---

## 5. The GUI bridge (`backend/`)

### 5.1 `backend/models/run_config.py`

A tiny `RunConfig` dataclass (`argv: list[str]`, `env: dict[str, str]`) describing one
pipeline run. It decouples "what to run" (the resolved CLI args + env) from "how to run it".

### 5.2 `backend/controllers/translation.py`

- `TranslationWorker(QRunnable)` runs `translate.main(self.config.argv)` on the `QThreadPool`,
  **off the UI thread** so the interface never freezes.
- `_SignalWriter` is a file-like shim that forwards `write()` calls to a callback. The
  worker temporarily swaps `sys.stdout`/`sys.stderr` to it (and manages the run's env vars),
  so **the CLI's own `print()` output streams live into the GUI log pane**. `stdout`/`stderr`
  and the environment are restored in `finally`.

### 5.3 `backend/bridge.py`

`AppBridge` is the single `QObject` exposed to QML as `appBridge`. Responsibilities:
- **Holds form state** as Qt `Property` fields (URL/file path, output path, batch size,
  backend choice, ASR language, model paths, etc.), with `@Property` + change signals so QML
  two-way binds automatically.
- **Persistence** via `QSettings` (saves user-entered fields between runs).
- **Builds the run config** from the current form state into CLI argv/env
  (e.g. `["http://..."]` or `["--file", ..., "--local", ...]`), then previews the equivalent
  command in the log.
- **Runs** a `TranslationWorker` through a `QThreadPool`, streaming log lines.
- **Detects completion** by regex-matching the CLI's `Wrote N cues to <path>` line
  (`_DONE_PATTERN`), enabling the **Open Output Folder** button from the resolved path.
- **One-click model downloads** via `_ModelDownloadWorker` (a `QRunnable`): fetches the
  the FunASR models (`sensevoice-small-q8.gguf` + `fsmn-vad.gguf`) and/or the **Hy-MT2 translation GGUF**
  (`Hy-MT2-1.8B-Q8_0.gguf`) from Hugging Face into `./gguf`, streaming a percentage
  progress bar into the UI. Downloaded models are auto-picked into the relevant settings.
- **`localPath()`** slot converts a `file://` QML URL into a plain filesystem path.


---

## 6. The QML frontend (`ui/qml/`)

- **`Main.qml`** — `ApplicationWindow` (1360×880, min 1120×760) with a dark gradient
  background, a header bar (logo, title, an animated **Ready / Pipeline active** status
  pill bound to `appBridge.isRunning`), a `Sidebar`, and a `StackView` that switches between
  `DashboardView` and `SettingsView` (instant transitions, no slide animation).
- **`components/`** — reusable widgets:
  - `Card.qml` — themed card container.
  - `CustomTextField.qml` — styled text input.
  - `PrimaryButton.qml` — primary action button.
  - `Sidebar.qml` — navigation rail.
  - `StyledRadioButton.qml` — themed radio button (used for backend / source selection).
- **`views/`**:
  - `DashboardView.qml` — the main controls (YouTube URL / local file, output path, batch,
    backend selection, ASR options) plus the **live log pane** and Run / Open Output Folder /
    Clear Log actions.
  - `SettingsView.qml` — model paths and the download buttons for the FunASR and Hy-MT2
    GGUFs.

Each of `components/` and `views/` ships a `qmldir` so the types resolve by simple name.

---

## 7. Config, dependencies & building

### 7.1 Environment (`.env`)

| Variable            | Required | Meaning                                                        |
| ------------------- | -------- | -------------------------------------------------------------- |
| `OPENAI_API_KEY`    | yes*     | API key for the OpenAI-compatible endpoint (*placeholder ok for localhost). |
| `OPENAI_MODEL`      | yes      | Model id used for translation (e.g. `gpt-5-mini`).             |
| `OPENAI_BASE_URL`   | no       | Base URL; blank → OpenAI, `https://openrouter.ai/api/v1` → OpenRouter. |
| `FUNASR_*` | no | Optional overrides for local ASR binaries/models (flag wins over env). |

### 7.2 Dependencies

- **`requirements.txt`** — core: `PySide6>=6.6.0`, `youtube-transcript-api`, `yt-dlp`,
  `openai`, `python-dotenv`, `imageio-ffmpeg>=0.5`.
- **`requirements-gui.txt`** — `PySide6>=6.6.0` (install only for the GUI; the core file
  already includes it).
- **`requirements-local.txt`** — `llama-cpp-python[server]` (optional; only needed if you
  prefer to serve a GGUF with `python -m llama_cpp.server` instead of letting the app
  auto-start its bundled `llama-server`).

### 7.3 Building the standalone exe

`build_exe.bat` produces `dist\TranslationAgent.exe` with PyInstaller
(`--onefile --windowed`):
- **Trims PySide6** to only the modules used (`QtCore/Gui/QtQml/QtQuick/QtQuickControls2`
  + plugins), via explicit `--hidden-import` and `--add-data`, which drastically speeds up
  builds and shrinks the exe.
- Bundles the QML files (`ui/qml/**`), Qt's QML runtime modules, the **ffmpeg** binary
  (via `imageio_ffmpeg`), and the `vendor/funasr` + `vendor/llama` payloads.
- Adds all `backend/*` and `src/*` modules as hidden imports.
- **Pre-flight checks** that PyInstaller, PySide6, ffmpeg, `llama-funasr-sensevoice`, `llama-funasr-vad`, and `llama-server`
  are all present, aborting with a clear message otherwise.

At runtime the frozen app:
- Resolves resources/AI paths relative to `sys._MEIPASS` (with `ui/qml` fallback).
- Writes a rotating `debug.log` **next to the exe** (startup info, exact `argv`, pipeline
  output, crash tracebacks) — run the exe from its own folder so relative paths resolve.


---

## 8. Known gaps & inconsistencies to be aware of

1. **ASR direction — FunASR + SenseVoiceSmall is the only local ASR.** The repository
   previously drifted between two local-ASR runtimes (documented FunASR vs an
   implemented whisper.cpp). That drift is now resolved: **FunASR + SenseVoiceSmall** is
   the live/default implementation and **whisper.cpp is removed** — it is not optional
   and must not be reintroduced as a fallback.

   ### Direction A — FunASR + SenseVoiceSmall (live / default)

   This is what the code actually does today:

   - **Runtime binaries:** Alibaba's **FunASR** GGML/llama.cpp runtime —
     `llama-funasr-sensevoice` (ASR) and `llama-funasr-vad` (VAD) in `vendor/funasr/`,
     plus the **GGUF models** `gguf/sensevoice-small-q8.gguf` (~235–242 MB) and
     `gguf/fsmn-vad.gguf` (~1.7 MB).
   - **Flow:** ffmpeg extracts a 16 kHz mono WAV → a **FunASR VAD pass** yields speech
     segments (aggressive settings) → ffmpeg **silencedetect** is used as fallback/refiner →
     long speech regions are split into ≤ ~7-second ASR segments → each is transcribed by
     **SenseVoiceSmall** → long recognized text is split into **short cues** on punctuation
     and timed proportionally inside each segment (target ~3 s / ~70 chars), so the output is
     short phrase-sized cues instead of giant paragraph blocks.
   - **CLI surface:** `--asr-bin`, `--asr-vad-bin`, `--asr-model`, `--asr-vad-model`,
     `--asr-lang`, `--asr-threads`, `--asr-max-segment-ms`, `--asr-max-end-silence-ms`,
     `--asr-speech-noise-threshold`, `--asr-noise-db`, `--asr-min-silence-s`,
     `--asr-max-cue-duration-ms`, `--asr-max-cue-chars`, `--asr-no-tags`; env vars
     `FUNASR_SENSEVOICE_BIN`, `FUNASR_VAD_BIN`, `FUNASR_MODEL`, `FUNASR_VAD_MODEL`,
     `FUNASR_THREADS`, `FUNASR_MAX_SEGMENT_MS`, `FUNASR_MAX_END_SILENCE_MS`,
     `FUNASR_SPEECH_NOISE_THRES`, `FUNASR_NOISE_DB`, `FUNASR_MIN_SILENCE_S`,
     `FUNASR_MAX_CUE_DURATION_MS`, `FUNASR_MAX_CUE_CHARS`; plus the
     `download-funasr-model.sh` helper.
   - **GUI:** `backend/bridge.py` `_MODEL_URLS` downloads `sensevoice-small-q8.gguf` and
     `fsmn-vad.gguf`; `SettingsView.qml`'s **Local ASR** card is FunASR-labelled and exposes
     the binary/model paths plus the timing/splitting controls; `_build_run_config()` wires
     every `asr*` setting (including the previously dead `asrBin`/`asrVadBin`/`asrVadModel`
     properties) into the CLI argv.
   - **Build:** `build_exe.bat` bundles `vendor\funasr` (and `vendor\llama`), and its
     pre-flight check requires `llama-funasr-sensevoice.exe` and `llama-funasr-vad.exe`.

   ### Direction B — whisper.cpp (removed)

   Removed. No Whisper binary, model, flag, env var, or GUI label remains in the active
   project, and it is **not** a fallback or optional backend.
2. **Untracked build/runtime artifacts.** `dist/`, `build/`, `*.spec`, `debug.log`, and
   `gguf/` (with downloaded models) are git-ignored. Example outputs and model files present
   in `dist/` locally (sample SRTs/subtitles, the bundled GGUFs) are **not** part of the
   committed repo.
3. **`vendor/` binaries are untracked (not committed, but also not git-ignored).** The repo
   needs `vendor/funasr/llama-funasr-sensevoice.exe`, `vendor/funasr/llama-funasr-vad.exe` and `vendor/llama/llama-server.exe` for the
   standalone build; they exist locally but are Windows binaries that must be fetched/placed
   manually — and they currently don't appear in `git status` cleanly (untracked folder).
   Decide whether to commit them (they're large) or add them to `.gitignore` explicitly.
4. **Automated tests exist.** A `tests/` suite (251 tests, run with
   `python -m pytest -q`, configured by `pytest.ini`) covers `srt_io`, translation
   parsing and validation, batching, glossary, translation memory, subtitle
   quality, local-ASR splitting, local server, fetch_subs, the fansub upgrade
   (postprocess/ass_io), CJK detection (`src/cjk.py`), and the new CLI flags
   (`--json-progress`, `--ass-font`/`--ass-fontsize`). Validation beyond that is
   manual (run the CLI/GUI and check the produced SRT + alignment).
5. **Short, partially-unhealthy commit history.** `git log` shows a handful of
   commits (`9d2a21a` "before pyside6 qml migration", `ba85d4a` "commit before
   redesign", `3dce98f` "progress") and the object store reports a missing object
   when traversing parents — a `git fsck` / re-clone is advisable. Most of the
   current work is committed; `vendor/` remains untracked.

---

## 9. Key design invariants (do not break)

- **Timestamps are sacred.** Original `start`/`end` values are never modified — only the
  `text` is replaced by the translation. (Local ASR is the exception: it *creates* the
  timing from the transcript.)
- **Cue count in == cue count out.** Alignment is guaranteed by the numbered-item protocol;
  never silently drop, merge, or reorder cues.
- **Target language is fixed to English.**
- **Translation dogmas:** *foreignization* (preserve voice/culture/honorifics/register;
  never domesticate or inject modern slang) and a `[Translator's Note]` convention for
  untranslatable wordplay. Keep `_FOREIGNIZATION_DIRECTIVE` intact.
- **The filename is YouTube's English-localized title**, not a translation we make.
- **Local servers accept a placeholder key**; remote endpoints require a real one and fail
  with an actionable message.
- **Never block the QML thread** — all pipeline work runs on the `QThreadPool`, and the CLI
  is invoked in-process (not as a subprocess) with patched streams.

---

## 10. Quick developer quick-start

```bash
# CLI (requires .env with OPENAI_API_KEY / OPENAI_MODEL)
pip install -r requirements.txt
copy .env.example .env          # then edit .env
python translate.py "<youtube_url>"
python translate.py --file video.mp4     # local transcription -> translation

# GUI
python main.py                  # canonical entry point
python gui.py                   # legacy shim (same thing)

# Standalone Windows exe
build_exe.bat                   # -> dist\TranslationAgent.exe
```

---

## 11. Roadmap / natural next steps (suggested)

- Keep `README.md` / `CLAUDE.md` in sync with the current **FunASR + SenseVoiceSmall** ASR implementation.
- ~~Add a lightweight `tests/` suite~~ — done (251 tests under `tests/`, run `python -m pytest -q`).
- Consider graceful handling when `vendor/` binaries are absent (currently only enforced at
  build time).
- Validate end-to-end output on a range of videos (manual/vs auto captions, various source
  languages, offline Hy-MT2 path) to firm up confidence before any release.
- See `IMPROVEMENTS_TRIAGE.md` for the reviewed improvement backlog and its status.

**Fansub-quality upgrade (done):** ASS output (`src/ass_io.py`, `--format ass`),
post-processing pass (`src/postprocess.py` — line breaking, overlap snap, translator-note
placement), CJK-aware cue splitting (weighted char budget in `src/local_asr.py`), and CJK
language auto-detection (`src/cjk.py`).

### Fansub philosophy (design north star)

The pipeline is modeled on the fansub production culture, not the commercial
subtitle one. Its quality bar is **fidelity over fluency** — carry the viewer *into*
the source culture rather than domesticating it:

- **Foreignization:** preserve author voice, cultural references, honorifics
  (e.g. `-san`, `-senpai`), period register, puns, and speech levels. Never
  smooth, localize, or sanitize (the `_FOREIGNIZATION_DIRECTIVE` / `_HY_MT2_STYLE`
  invariants enforce this). Untranslatables get a `[Translator's Note]` on a
  second line, not a rewrite.
- **Deep linguistic/cultural expertise:** the glossary + translation-memory layers
  exist so recurring terms, names, and idioms are applied consistently — the same
  collaborative review fansubs get from their term/translators.
- **Technical execution:** ASS (`--format ass`) with Aegisub-compatible timing,
  styled output, and CJK-capable default fonts, plus `postprocess.snap_overlaps`
  and reading-speed (CPS) guards so the output is insert-ready without manual
  timing fixes.
- **Multi-layer quality control:** every cue line is validated
  (`looks_untranslated`, CJK-residue stripping) and a `--quality-report` /
  `--strict-quality` pass counts CPS, duration, char/line counts, and empty/untranslated
  cues — approximating the fansub editor/timer/typesetter checkpoints.



- **Typesetter integration** — export cues with positional override tags (`{\\anX}` /
  per-line alignment + `\\pos`) for dual-speaker dialogue, so the output is insert-ready
  for Aegisub without manual repositioning.

