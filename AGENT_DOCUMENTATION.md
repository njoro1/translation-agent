# Translation Agent — AI Agent Documentation

> **Audience:** AI agents, coding assistants, and automated refactoring tools.
> **Goal:** Provide complete, precise, actionable context so an agent can understand, modify, test, and extend this codebase without guessing.
> **Last updated:** Based on working tree at commit `9d2a21afa91ed9f53f29e4c1dc9b230461ae291f` (branch `main`), with uncommitted QML/PyInstaller migration work present.

---

## 1. Project Identity

**Internal name:** Translation Agent
**User-facing name:** YouTube Subtitle Translator
**Platform:** Windows-first (no macOS/Linux support currently guaranteed)
**Language:** Python 3, PySide6 (QML), batch/shell
**Purpose:** Produce English SRT subtitles from either (a) a YouTube URL's original-language captions or (b) a local media file's audio, using LLM translation or local ASR.

---

## 2. Repository Layout (Canonical)

```
translation-agent/
├── AGENT_DOCUMENTATION.md      # ← this file
├── PROJECT.md                  # Developer narrative / history (human-readable)
├── CLAUDE.md                   # Claude Code-specific guidance
├── README.md                   # User-facing docs
│
├── translate.py                # CLI entry point (top-level)
├── main.py                     # PySide6 + QML GUI entry point (canonical)
├── gui.py                      # Compatibility shim → main.main()
│
├── build_exe.bat               # PyInstaller one-file Windows build
├── TranslationAgent.spec       # PyInstaller spec (reference)
│
├── requirements.txt            # Core: PySide6, yt-dlp, youtube-transcript-api, openai, dotenv, imageio-ffmpeg
├── requirements-gui.txt        # Just PySide6 (subset of requirements.txt)
├── requirements-local.txt      # Optional: llama-cpp-python[server]
│
├── .env.example                # Credential template
├── .env                        # Actual secrets (git-ignored)
│
├── src/                        # Framework-free CLI pipeline
│   ├── __init__.py
│   ├── config.py               # .env + OpenAI client construction
│   ├── fetch_subs.py           # YouTube subtitle fetching + title resolution
│   ├── srt_io.py               # Cue dataclass + SRT read/write + filename sanitize
│   ├── translate.py            # LLM-based faithful English translation (batched)
│   ├── local_asr.py            # FunASR + SenseVoiceSmall CPU transcription
│   └── local_server.py         # Auto-start bundled CPU llama-server
│
├── backend/                    # GUI bridge (QObject + QRunnable workers)
│   ├── __init__.py
│   ├── bridge.py               # AppBridge: QML ↔ Python state + pipeline runner
│   ├── controllers/
│   │   ├── __init__.py
│   │   └── translation.py      # TranslationWorker + _SignalWriter
│   └── models/
│       ├── __init__.py
│       └── run_config.py       # RunConfig dataclass (argv + env)
│
├── ui/qml/                     # Qt Quick declarative frontend
│   ├── Main.qml
│   ├── components/
│   │   ├── qmldir
│   │   ├── Card.qml
│   │   ├── CustomTextField.qml
│   │   ├── PrimaryButton.qml
│   │   ├── Sidebar.qml
│   │   └── StyledRadioButton.qml
│   └── views/
│       ├── qmldir
│       ├── DashboardView.qml
│       └── SettingsView.qml
│
├── vendor/                     # Bundled binaries (untracked, not git-ignored)
│   ├── funasr/                 # llama-funasr-sensevoice.exe, llama-funasr-vad.exe + DLLs
│   └── llama/                  # llama-server.exe + DLLs
│
├── gguf/                       # Downloaded GGUF models (SenseVoiceSmall, VAD, Hy-MT2)
│
├── tools/
│   └── check_srt.py            # SRT diagnostic (cue count, avg/max duration)
│
├── build/                      # PyInstaller intermediate build artifacts
├── dist/                       # PyInstaller output (TranslationAgent.exe)
├── debug.log                   # Rotating runtime log (GUI mode)
│
└── __pycache__/                # Python bytecache

---

## 3. System Architecture & Data Flow

### 3.1 High-Level Modes

| Mode | Input | Subtitle Source | Translation |
|------|-------|-----------------|-------------|
| **YouTube (cloud)** | YouTube URL | youtube-transcript-api (manual → auto fallback) | OpenAI-compatible cloud LLM |
| **YouTube (local)** | YouTube URL | youtube-transcript-api | llama.cpp server (auto-started or existing) |
| **Local ASR (cloud)** | Local media file | FunASR + SenseVoiceSmall (VAD + ffmpeg) | OpenAI-compatible cloud LLM |
| **Local ASR (local)** | Local media file | FunASR + SenseVoiceSmall (VAD + ffmpeg) | llama.cpp server (auto-started or existing) |

### 3.2 YouTube Pipeline (CLI)

```
translate.py (main)
  ├─ parse args (url / --file / --local / --model / --out / --batch)
  ├─ if --file:
  │   └─ src.local_asr.transcribe_local_file()
  │       └─ returns (cues, source_language)
  ├─ else (YouTube URL):
  │   └─ src.fetch_subs.fetch_original_subtitles(url)
  │       ├─ extract_video_id(url)
  │       ├─ _yt_dlp_metadata(url) → (title, lang)
  │       ├─ _fetch_english_title(video_id) → english_title
  │       └─ _resolve_transcript(video_id, lang) → snippets → list[Cue]
  │           └─ returns (cues, english_title, source_language)
  ├─ if --local:
  │   ├─ src.local_server.ensure_local_server(model_path, host, port) → (proc, how)
  │   └─ _check_local_ready(base_url)
  └─ src.translate.translate_cues(cues, client, model, batch_size, source_language)
      └─ batches cues, calls LLM with numbered-item protocol
  └─ src.srt_io.write_srt(cues, out_path)
```

### 3.3 Numbered-Item Translation Protocol

This is the **single most important invariant** in the codebase.

1. Cue texts are joined as `1. text1\n2. text2\n...` and sent as a single user message.
2. The LLM is instructed to respond with the same numbers.
3. `_parse_numbered(response, expected)` maps lines back to a list of exactly `expected` strings.
4. If the model's response has the wrong set of numbers, the batch falls back to **per-item translation** (`_translate_one`).
5. If a backend rejects llama.cpp-only params (`top_k`, `repeat_penalty`), they are dropped and the batch is retried plainly.

**Why this matters:** Cue count in == cue count out. The SRT indices (1, 2, 3, ...) are written sequentially; any mismatch between translated list length and cue list length causes misalignment.

### 3.4 Foreignization Directive

The system prompt for cloud translation is built from `_FOREIGNIZATION_DIRECTIVE` (in `src/translate.py`). It is a long, carefully crafted instruction set covering:
- Absolute ideological/political neutrality
- Ban on modern slang and anachronisms
- Register, hierarchy, honorifics preservation
- Cultural specifics and idioms
- Puns and wordplay handling
- `[Translator's Note]` convention for untranslatable elements

**AI agents must preserve this directive intact.** If editing translation logic, keep `_FOREIGNIZATION_DIRECTIVE` and `build_system_prompt()` behavior unchanged unless explicitly asked to modify translation philosophy.

### 4.2 `src/fetch_subs.py`

**Responsibility:** Extract YouTube video ID, get the original-language subtitles, resolve the English title for filename.

**Key types / functions:**
- `extract_video_id(url) -> str`
  - Regex patterns: `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/shorts/`, `youtube.com/embed/`
  - Returns the 11-char video ID.
  - Raises `ValueError` if no pattern matches.
- `fetch_original_subtitles(url) -> tuple[list[Cue], str | None, str | None]`
  - Returns `(cues, english_video_title, source_language_code)`.

**External dependencies:**
- `yt-dlp` (CLI): `yt-dlp --print %(title)s|%(language)s <url>`
  - Called via `subprocess.run` with `CREATE_NO_WINDOW` on Windows.
- `youtube-transcript-api`: `YouTubeTranscriptApi.list(video_id)` → `TranscriptList`
  - `find_manually_created_transcript([lang])` → fallback `find_generated_transcript([lang])` → fallback first available track.
- Innertube player API (HTTP POST to `https://www.youtube.com/youtubei/v1/player` with a public key):
  - Used only to fetch the English-localized title (`hl=en`). Falls back to yt-dlp title on any failure.

### 4.3 `src/srt_io.py`

**Responsibility:** Core data class and SRT serialization/deserialization.

**Key types / functions:**
### 4.4 `src/translate.py`

**Responsibility:** Batch translation of cues via an OpenAI-compatible chat completion API.

**Key types / functions:**
- `build_system_prompt(source_language, target_language="English") -> str`
  - Injects language placeholders into `_FOREIGNIZATION_DIRECTIVE`.
- `translate_cues(cues, client, model, batch_size=40, max_retries=3, source_language=None) -> list[str]`
  - The **canonical entry point** used by both CLI and GUI.
  - Splits cues into batches of `batch_size`.
  - For each batch:
    - Determines if the model is Hy-MT2 via `_is_hy_mt2(model)`.
    - Calls `_translate_batch(...)`.
    - On failure: retries with exponential backoff (`2 ** attempt` seconds).
    - On misalignment (returns `None`): falls back to per-item `_translate_one(...)`.
  - Prints progress: `translated {N}/{total}`.

**Internal helpers:**
- `_is_hy_mt2(model) -> bool`
- `_numbered_block(texts) -> str` -- joins as `1. text\n2. text\n...`
- `_parse_numbered(response, expected) -> list[str] | None`
- `_translate_batch(client, model, texts, system_prompt, ...) -> list[str] | None`
  - Adds `STRICT:` prefix on retry attempts to force exact line count.
  - Passes `extra_body` for llama.cpp-only params.
- `_translate_one(client, model, text, system_prompt, ...) -> str`

**Constants:**
| Constant | Value | Usage |
|----------|-------|-------|
| `HY_MT2_TEMPERATURE` | `0.1` | Hy-MT2 local model |
| `HY_MT2_TOP_P` | `0.6` | Hy-MT2 via `extra_body` |
| `HY_MT2_TOP_K` | `20` | Hy-MT2 via `extra_body` |
| `HY_MT2_REPETITION_PENALTY` | `1.05` | Hy-MT2 via `extra_body` |

### 4.5 `src/local_asr.py`

**Responsibility:** Transcribe local media files using FunASR + SenseVoiceSmall (CPU-only GGUF runtime).

**Key types / functions:**
- `transcribe_local_file(file_path, asr_bin, asr_vad_bin, asr_model, asr_vad_model, asr_lang="auto", threads, ...) -> tuple[list[Cue], str | None]`
  - Returns `(cues, detected_source_language_name_or_None)`.

**Pipeline:**
1. **Extract WAV:** ffmpeg → 16 kHz mono PCM WAV (`_extract_wav`).
2. **VAD segmentation:**
### 4.7 `backend/bridge.py` -- `AppBridge`

**Responsibility:** The single QObject exposed to QML as `appBridge`. Holds all UI state, builds `RunConfig`, runs the pipeline on a background thread, and streams output to the UI log.

**Key signals:**
- `formChanged`
- `statusMessageChanged`
- `logTextChanged`
- `isRunningChanged`
- `canOpenOutputFolderChanged`
- `modelDownloadChanged`

**Key slots / properties:**
- `mode` (`"youtube"` / `"local"`)
- `backend` (`"cloud"` / `"local"`)
- `url`, `filePath`, `outPath`
- `batch`
- `apiKey`, `baseUrl`, `model`
- `host`, `port`, `modelName` (local server params)
- `localModel` (GGUF path for auto-start)
- All ASR fields: `asrLanguage`, `asrBin`, `asrVadBin`, `asrModel`, `asrVadModel`, `asrThreads`, `asrMaxSegmentMs`, `asrMaxEndSilenceMs`, `asrSpeechNoiseThreshold`, `asrNoiseDb`, `asrMinSilenceS`, `asrMaxCueDurationMs`, `asrMaxCueChars`, `asrNoTags`
- `statusMessage`, `logText`, `isRunning`, `canOpenOutputFolder`
- `modelDownloadStatus`, `modelDownloading`
- `runTranslation()` -- builds `RunConfig`, starts `TranslationWorker`
- `openOutputFolder()` -- opens the output directory in Explorer
- `clearLog()` -- clears the log pane
- `downloadAsrModels()` -- downloads SenseVoice + VAD GGUF models
- `downloadLocalModel()` -- downloads Hy-MT2 GGUF model

**Persistence:**
- Non-secret fields are persisted via `QSettings` (registry on Windows).
- API key is **intentionally not persisted**.

**Model download URLs:**
| File | URL |
### 4.10 `main.py`

**Responsibility:** PySide6 application bootstrap.

**Key behavior:**
1. Sets `QT_QUICK_CONTROLS_STYLE=Basic`.
2. Initializes `debug.log` via `setup_logging`.
3. Installs an `excepthook` that logs unhandled exceptions.
4. Resolves QML import paths:
   - Frozen: `sys._MEIPASS/PySide6/qml` (fallback `_MEIPASS/ui/qml`)
   - Dev: `PySide6.__file__/qml`
5. Sets `QT_PLUGIN_PATH` if platform plugins exist.
6. Loads `Main.qml`.
7. Connects `aboutToQuit` → `shutdown_servers()`.

### 4.11 `gui.py`

Compatibility shim. `python gui.py` → `from main import main` → `main()`. Canonical command is `python main.py`.

### 4.12 QML UI

- **`Main.qml`**: `ApplicationWindow` with a `StackView`. Switches between `DashboardView` and `SettingsView` via `currentView` property.
- **`DashboardView.qml`**: Left control panel + right log panel. Contains:
  - Source mode toggle (YouTube / local file)
  - URL / file path / output path inputs
  - Batch size input
  - Run Translation, Open Output Folder, Clear Log buttons
  - Live log `TextArea` (read-only, auto-scrolls)
  - File dialogs for input/output
- **`SettingsView.qml`**: Backend selection (cloud / local), API key / base URL / model fields, local server config, ASR config with file dialogs, model download buttons.

---

## 7. Build & Distribution

### 7.1 PyInstaller Spec (`build_exe.bat`)

Produces `dist/TranslationAgent.exe` with `--onefile --windowed`.

**Bundled data:**
- `ui/qml` (QML source)
- `vendor/funasr` (FunASR binaries)
- `vendor/llama` (llama-server + DLLs)
- `PySide6/qml/Qt`, `PySide6/qml/QtQml`, `PySide6/qml/QtQuick`
- `PySide6/plugins/platforms`, `imageformats`, `styles`, `iconengines`, `qmltooling`
- `ffmpeg` (from `imageio-ffmpeg`)
- Hidden imports: `backend.*`, `src.*`, `translate`, `dotenv`, `openai`

**Prerequisites for build:**
- `vendor/funasr/llama-funasr-sensevoice.exe`
- `vendor/funasr/llama-funasr-vad.exe`
- `vendor/llama/llama-server.exe`
- ffmpeg (via `imageio-ffmpeg`)

**Runtime behavior when frozen:**
- `sys._MEIPASS` is the temp extraction dir.
- QML imports resolve from `_MEIPASS/PySide6/qml` then `_MEIPASS/ui/qml`.
- `vendor/funasr` and `vendor/llama` resolve from `_MEIPASS/vendor/...`.
- `debug.log` is written **next to the `.exe`**, not in `_MEIPASS`.


---

## 12. File Format Reference

### 12.1 SRT (SubRip)

```
1
00:00:01,000 --> 00:00:04,000
Translated text here.

2
00:00:05,000 --> 00:00:08,000
Next line.
```

- 1-based sequential index.
- Timestamps: `HH:MM:SS,mmm` (comma, not period).
- Blank line between cues.
- Encoding: UTF-8.

### 12.2 .env

```
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=gpt-4o-mini
```

No spaces around `=`.

---

## 13. Error Handling Conventions

- **CLI:** `RuntimeError` and `ValueError` are caught in `translate.py`'s `main()` and printed to `stderr` with exit code 1 or 2.
- **GUI:** Exceptions in `TranslationWorker.run()` are caught, emitted as `[error] ...` log lines, and the worker emits `finished(1)`.
- **Network failures:** `fetch_subs.py` catches subprocess/network errors and raises `RuntimeError` with actionable messages.
- **Local server failures:** `local_server.py` raises `RuntimeError` if the server cannot start or becomes ready within `timeout`.

---

## 14. Environment Variables Reference (Consolidated)

| Variable | Module | Default | Purpose |
|----------|--------|---------|---------|
| `OPENAI_API_KEY` | `config.py` | -- | API key |
| `OPENAI_BASE_URL` | `config.py` | None | Endpoint override |
| `OPENAI_MODEL` | `config.py` | -- | Model id |
| `FUNASR_SENSEVOICE_BIN` | `local_asr.py` | `llama-funasr-sensevoice` (PATH) | SenseVoice binary |
| `FUNASR_VAD_BIN` | `local_asr.py` | `llama-funasr-vad` (PATH) | VAD binary |
| `FUNASR_MODEL` | `local_asr.py` | `./gguf/sensevoice-small-q8.gguf` | SenseVoice GGUF |
| `FUNASR_VAD_MODEL` | `local_asr.py` | `./gguf/fsmn-vad.gguf` | VAD GGUF |
| `FUNASR_THREADS` | `local_asr.py` | `4` | CPU threads |
| `FUNASR_MAX_SEGMENT_MS` | `local_asr.py` | `7000` | Max ASR segment ms |
| `FUNASR_MAX_END_SILENCE_MS` | `local_asr.py` | `250` | Max trailing silence ms |
| `FUNASR_SPEECH_NOISE_THRES` | `local_asr.py` | `0.55` | VAD speech threshold |
| `FUNASR_NOISE_DB` | `local_asr.py` | `-35` | ffmpeg silence noise floor |
| `FUNASR_MIN_SILENCE_S` | `local_asr.py` | `0.20` | Min silence duration |
| `FUNASR_MAX_CUE_DURATION_MS` | `local_asr.py` | `3000` | Max cue duration |
| `FUNASR_MAX_CUE_CHARS` | `local_asr.py` | `70` | Max cue chars |
| `FUNASR_VAD_UNITS` | `local_asr.py` | `ms` | VAD output time units |
| `FUNASR_OUTPUT_FLAG` | `local_asr.py` | auto-detect | VAD/ASR output file flag |
| `FFMPEG_BIN` | `local_asr.py` | ffmpeg on PATH | ffmpeg binary path |
| `IMAGEIO_FFMPEG_EXE` | `local_asr.py` | -- | Alternative ffmpeg path |
| `QT_QUICK_CONTROLS_STYLE` | `main.py` | `Basic` | Qt Quick Controls style |
| `QT_PLUGIN_PATH` | `main.py` | auto-set | Qt plugins directory |
| `PYTHONDONTWRITEBYTECODE` | -- | not set | Set to `1` to suppress `__pycache__` |

---

## 15. Testing & Validation

There is **no automated test suite** currently.

**Manual validation checklist:**
1. YouTube URL with manual subtitles → SRT with correct timestamps and translated English text.
2. YouTube URL with auto-generated-only subtitles → same as above.
3. Local video with no subtitles → FunASR transcription → English translation.
4. Local model path (`--local --local-model model.gguf`) → server auto-starts → translation succeeds.
5. Existing server path (`--local` without `--local-model`) → connects to running server.
6. GUI mode: run translation, verify log streaming, verify "Open Output Folder" works after success.
7. `python tools/check_srt.py output.srt` → verify average/max cue durations are reasonable.

**Recommended pytest targets when adding tests:**
- `src/srt_io.py`: `sanitize_filename`, `write_srt` + `read_srt` roundtrip, `_format_timestamp` / `_parse_timestamp`.
- `src/translate.py`: `_parse_numbered`, `_numbered_block`, `build_system_prompt`.
- `src/fetch_subs.py`: `extract_video_id`.

---

## 16. Glossary

| Term | Meaning |
|------|---------|
| **Cue** | One subtitle entry: `start`, `end`, `text`. In code: `src.srt_io.Cue`. |
| **Foreignization** | Translation philosophy: preserve source culture/voice/honorifics; do not domesticate. |
| **Numbered-item protocol** | Batch translation method: cues are numbered `1.` ... `N.` sent to LLM, which must return same numbers. |
| **Hy-MT2** | Tencent's 1.8B-parameter translation model; 1.25-bit STQ quantized GGUF. |
| **SenseVoiceSmall** | FunASR's small ASR model (GGUF). |
| **FunASR VAD** | Voice Activity Detection model (`fsmn-vad.gguf`) used to segment audio. |
| **llama-server** | llama.cpp's OpenAI-compatible HTTP server (`llama-server.exe`). |
| **STQ** | 1.25-bit quantization kernel for llama.cpp (PR #22836). |
| **AppBridge** | `backend.bridge.AppBridge`; the single QObject exposed to QML. |
| **RunConfig** | `backend.models.run_config.RunConfig`; argv + env for one pipeline run. |
| **TranslationWorker** | `backend.controllers.translation.TranslationWorker`; QRunnable that runs `translate.main()` off the UI thread. |
| **_MEIPASS** | PyInstaller's temp extraction directory (when frozen). |
| **QSettings** | Qt's persistent settings (registry on Windows). |

---

## 17. Contact / References

- **GitHub:** `https://github.com/njoro1/translation-agent`
- **Hy-MT2 model:** `https://huggingface.co/tencent/Hy-MT2-1.8B-1.25Bit-GGUF`
- **SenseVoiceSmall GGUF:** `https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF`
- **fsmn-vad GGUF:** `https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF`
- **FunASR runtime:** GitHub releases tagged `runtime-llamacpp-v*`
- **Hy-MT2 translator skill:** `https://skillhub.cn/skills/hy-mt2-translator`

---

## 8. Key Design Invariants (Do Not Break)

1. **Timestamps are sacred.** `start`/`end` are never modified for YouTube or cloud-translated output. Only `text` is replaced.
2. **Cue count in == cue count out.** The numbered-item protocol guarantees this; fallback to per-item translation on misalignment. Never silently drop/merge/reorder cues.
3. **Target language is fixed to English.**
4. **Foreignization is the translation philosophy.** Preserve author voice, culture, honorifics, period register. Never sanitize, domesticate, or inject modern slang. Keep `_FOREIGNIZATION_DIRECTIVE` and `_HY_MT2_STYLE` intact.
5. **Filename is YouTube's English-localized title**, not a translation.
6. **Local servers accept placeholder keys.** Remote endpoints require a real key and fail with an actionable message.
7. **Never block the QML thread.** All pipeline work runs on `QThreadPool`.
8. **Local ASR is FunASR + SenseVoiceSmall only.** Whisper.cpp is not used and must not be reintroduced.

---

## 9. Known Issues & Technical Debt

| Issue | Severity | Details |
|-------|----------|---------|
| Single git commit | High | `9d2a21a` predates QML migration; most current work is uncommitted. |
| `vendor/` untracked | Medium | Binaries exist locally but are not committed or gitignored. Decide policy. |
| No tests | High | No `tests/`, `pytest.ini`, `tox.ini`. Strong candidate: `srt_io`, `_parse_numbered`, `sanitize_filename`. |
| `SectionCard.qml` deleted | Low | Tracked in old commit but absent from disk; not referenced by current QML. |
| `last_completed_task.txt` present | Low | Appears to be a work artifact. |
| `_test_meipass` dir | Low | Appears to be a PyInstaller test artifact. |

---

## 10. Quick Developer Quick-Start

```bash
# CLI
pip install -r requirements.txt
copy .env.example .env          # then edit .env
python translate.py "<youtube_url>"
python translate.py --file video.mp4 --asr-lang ja

# GUI
pip install -r requirements-gui.txt
python main.py

# Build Windows exe
pip install pyinstaller
build_exe.bat

# Check an SRT
python tools/check_srt.py output.srt
```

---

## 11. How to Modify / Extend (AI Agent Guide)

### 11.1 Changing Translation Behavior

- Edit `_FOREIGNIZATION_DIRECTIVE` in `src/translate.py` to change the system prompt.
- Edit `_HY_MT2_STYLE` in `src/translate.py` to change the local model's style instruction.
- Do **not** change the numbered-item protocol without also updating `_parse_numbered` and `_translate_batch`.
- Do **not** remove the per-item fallback in `translate_cues`.

### 11.2 Changing ASR Behavior

- Edit `transcribe_local_file()` in `src/local_asr.py`.
- Tuning knobs: `FUNASR_*` env vars, function defaults.
- VAD logic is in `_binary_vad()` and `_ffmpeg_silences()`.
- Cue splitting logic is in `_segment_to_cues()`.

### 11.3 Adding a New YouTube URL Pattern

Edit `_URL_PATTERNS` in `src/fetch_subs.py`. Each pattern must capture the 11-character video ID in group 1.

### 11.4 Changing GUI Layout

Edit `ui/qml/Main.qml`, `ui/qml/views/DashboardView.qml`, `ui/qml/views/SettingsView.qml`, and components under `ui/qml/components/`.

To expose a new field to QML, add it to `AppBridge` in `backend/bridge.py` as a `Property` with a setter that calls `_set_field` / emits the appropriate signal.

### 11.5 Adding a New Backend

1. Add a new backend option in `AppBridge._backend` (and `SettingsView.qml`).
2. In `AppBridge._build_run_config()`, set `env` / `argv` for the new backend.
3. In `src/config.py` or `translate.py`, handle the new backend type.

### 11.6 Building / Releasing

- Run `build_exe.bat` after any Python/QML change.
- Ensure `vendor/` binaries and `gguf/` models are present.
- The output is `dist/TranslationAgent.exe`. Run it from the folder containing it so relative paths resolve.

- **Components:** `Card`, `CustomTextField`, `PrimaryButton`, `Sidebar`, `StyledRadioButton`.

---

## 5. CLI Reference

### 5.1 All Flags

| Flag | Default | Required | Meaning |
|------|---------|----------|---------|
| `url` (positional) | -- | YouTube mode | YouTube video URL |
| `--file` | -- | Local mode | Local media path |
| `--model` | `OPENAI_MODEL` | No | Override model |
| `--out` | `<title>.srt` | No | Output path |
| `--batch` | `40` | No | Cues per translation call |
| `--local` | off | No | Use llama.cpp server |
| `--local-host` | `127.0.0.1` | No | Server host |
| `--local-port` | `8080` | No | Server port |
| `--local-model-name` | `Hy-MT2-1.8B` | No | Model id for local server |
| `--local-model` | -- | No | Auto-start bundled server against this GGUF |
| `--asr-bin` | `FUNASR_SENSEVOICE_BIN` / PATH | No | SenseVoice binary |
| `--asr-vad-bin` | `FUNASR_VAD_BIN` / PATH | No | VAD binary |
| `--asr-model` | `./gguf/sensevoice-small-q8.gguf` | No | SenseVoice GGUF |
| `--asr-vad-model` | `./gguf/fsmn-vad.gguf` | No | VAD GGUF |
| `--asr-lang` | `auto` | No | ASR source language (`auto`/`zh`/`en`/`ja`/`ko`/`yue`) |
| `--asr-threads` | `4` | No | FunASR CPU threads |
| `--asr-max-segment-ms` | `7000` | No | Max ASR segment length |
| `--asr-max-end-silence-ms` | `250` | No | Trailing silence for VAD |
| `--asr-speech-noise-threshold` | `0.55` | No | VAD speech/noise threshold |
| `--asr-noise-db` | `-35` | No | ffmpeg silencedetect noise floor |
| `--asr-min-silence-s` | `0.20` | No | Min silence for ffmpeg silence detection |
| `--asr-max-cue-duration-ms` | `3000` | No | Max subtitle cue duration |
| `--asr-max-cue-chars` | `70` | No | Max subtitle cue character count |
| `--asr-no-tags` | off | No | Strip SenseVoice language tags |

### 5.2 Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (SRT written) |
| `1` | Runtime error (fetch/transcription/translation failure) |
| `2` | Configuration error (missing API key, missing model) |

### 5.3 Standard Output Lines (parsed by GUI)

- `Wrote {N} cues to {path}` -- enables "Open Output Folder" button.
- `[local] llama-server ({how}) serving {path}` -- informational.
- `Using local llama.cpp server at {url}` -- informational.
- `translated {N}/{total}` -- progress.

---

## 6. GUI Architecture

### 6.1 Threading Model

**Rule: Never block the QML main thread.**

- `AppBridge.runTranslation()` creates a `TranslationWorker` and submits it to `QThreadPool`.
- `TranslationWorker.run()`:
  1. Saves `sys.stdout`/`sys.stderr`.
  2. Replaces them with `_SignalWriter` that emits `logLine` signal.
  3. Temporarily overrides environment variables from `RunConfig.env`.
  4. Calls `translate.main(argv)`.
  5. Restores streams and env in `finally`.
  6. Emits `finished(rc)`.

The GUI is **not** a subprocess wrapper -- it calls the CLI logic in-process with redirected streams.

### 6.2 State Persistence

`QSettings` (registry) persists these fields across app launches:

| QSettings Key | Default | Secret? |
|---------------|---------|---------|
| `asr/language` | `auto` | No |
| `asr/bin` | `""` | No |
| `asr/vadBin` | `""` | No |
| `asr/model` | `""` | No |
| `asr/vadModel` | `""` | No |
| `asr/threads` | `4` | No |
| `asr/maxSegmentMs` | `7000` | No |
| `asr/maxEndSilenceMs` | `250` | No |
| `asr/speechNoiseThreshold` | `0.55` | No |
| `asr/noiseDb` | `-35` | No |
| `asr/minSilenceS` | `0.20` | No |
| `asr/maxCueDurationMs` | `3000` | No |
| `asr/maxCueChars` | `70` | No |
| `asr/noTags` | `false` | No |
| `local/model` | `""` | No |

**API key is NOT persisted.**

|------|-----|
| `sensevoice-small-q8.gguf` | `https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/main/sensevoice-small-q8.gguf` |
| `fsmn-vad.gguf` | `https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF/resolve/main/fsmn-vad.gguf` |
| `Hy-MT2-1.8B-1.25Bit.gguf` | `https://huggingface.co/tencent/Hy-MT2-1.8B-1.25Bit-GGUF/resolve/main/Hy-MT2-1.8B-1.25Bit.gguf` |

**Logging:**
- `setup_logging(base_dir)` creates a rotating `debug.log` (1 MB, 3 backups) in `base_dir`.
- Logs: startup info, exact `argv`, pipeline stdout/stderr, unhandled exceptions.
- In frozen mode, `base_dir` is the directory next to the `.exe`.

### 4.8 `backend/controllers/translation.py`

**Responsibility:** Run the CLI pipeline off the UI thread without blocking QML.

**Key types:**
- `_SignalWriter` -- file-like object that forwards `write()` to a callback.
- `WorkerSignals` -- `logLine(str)`, `finished(int)`
- `TranslationWorker(QRunnable)`
  - Patches `sys.stdout` and `sys.stderr` with `_SignalWriter` so CLI print statements stream to the UI.
  - Temporarily sets environment variables from `RunConfig.env`.
  - Calls `translate.main(self.config.argv)`.
  - Restores streams and env in `finally`.

### 4.9 `backend/models/run_config.py`

```python
@dataclass(slots=True)
class RunConfig:
    argv: list[str]
    env: dict[str, str]
```

   - Try FunASR VAD binary (`_binary_vad`).
   - Refine/fallback with ffmpeg `silencedetect` (`_ffmpeg_silences`).
   - Merge nearby segments; split long segments at midpoint silences (`_split_segments`).
3. **ASR transcription:**
   - Split long audio into ≤ ~7 s chunks.
   - Run `llama-funasr-sensevoice` on each chunk (`_run_sensevoice`).
   - Parse output for `<|zh|>`, `<|en|>`, etc. tags and text.
4. **Cue splitting:**
   - Long recognized text is split into ≤ ~3 s / ≤ ~70 char cues (`_segment_to_cues`), timed proportionally.
   - English-source audio skips translation (text written as-is).

**Environment variables (all optional):**
| Variable | Default | Meaning |
|----------|---------|---------|
| `FUNASR_THREADS` | `4` | CPU threads |
| `FUNASR_MAX_SEGMENT_MS` | `7000` | Max ASR segment length |
| `FUNASR_MAX_END_SILENCE_MS` | `250` | Trailing silence before VAD closes |
| `FUNASR_SPEECH_NOISE_THRES` | `0.55` | VAD speech/noise threshold |
| `FUNASR_NOISE_DB` | `-35` | ffmpeg silencedetect noise floor |
| `FUNASR_MIN_SILENCE_S` | `0.20` | Min silence for ffmpeg silence detection |
| `FUNASR_MAX_CUE_DURATION_MS` | `3000` | Max subtitle cue duration |
| `FUNASR_MAX_CUE_CHARS` | `70` | Max subtitle cue character count |
| `FUNASR_VAD_UNITS` | `ms` | Units in VAD output (`ms` / `s`) |
| `FUNASR_OUTPUT_FLAG` | auto-detect | CLI flag for VAD/ASR output file |
| `FUNASR_SENSEVOICE_BIN` | `llama-funasr-sensevoice` (PATH) | SenseVoice binary path |
| `FUNASR_VAD_BIN` | `llama-funasr-vad` (PATH) | VAD binary path |
| `FUNASR_MODEL` | `./gguf/sensevoice-small-q8.gguf` | SenseVoice GGUF |
| `FUNASR_VAD_MODEL` | `./gguf/fsmn-vad.gguf` | VAD GGUF |

**Binary resolution order (`_find_exe`, `_funasr_dirs`):**
1. Explicit argument or matching env var.
2. `vendor/funasr/`, `vendor/funasr/Release/`, next-to-exe `vendor/funasr/`, `_MEIPASS/vendor/funasr/`.
3. `shutil.which()` on PATH.

### 4.6 `src/local_server.py`

**Responsibility:** Manage a bundled CPU-only `llama-server` process for local translation.

**Key types / functions:**
- `resolve_llama_server(name="llama-server") -> str | None`
  - Searches bundled paths then PATH.
- `start_server(model_path, host, port, n_ctx, n_gpu_layers) -> Popen`
  - Starts hidden background process (`CREATE_NO_WINDOW`).
  - Registers in `_ACTIVE` dict keyed by `(abs_model_path, host, port)`.
- `ensure_local_server(model_path, host, port, ...) -> (Popen | None, str)`
  - If already alive → returns `(None, "reuse")`.
  - Otherwise starts, polls `/health` every 1s up to `timeout` (default 180s).
  - Raises `RuntimeError` on failure (corrupt model, timeout, early exit).
- `server_alive(host, port) -> bool`
- `terminate_server(model_path, host, port)`
- `shutdown_servers()` -- registered via `atexit` to kill all spawned servers.

**Constants:**
| Constant | Value | Meaning |
|----------|-------|---------|
| `N_GPU_LAYERS` | `0` | CPU-only |
| `DEFAULT_N_CTX` | `4096` | Context size |
| `DEFAULT_HOST` | `127.0.0.1` | Bind host |
| `DEFAULT_PORT` | `8080` | Bind port |

- `Cue` (dataclass, slots): `start: float` (seconds), `end: float` (seconds), `text: str`
- `sanitize_filename(title) -> str`
  - Strips `< > : " / \ | ? *` and control chars.
  - Collapses whitespace/dots, max 180 chars.
  - Falls back to `"subtitles"`.
- `write_srt(cues, path) -> None`
  - Writes standard SRT with 1-based indices and `HH:MM:SS,mmm` timestamps.
- `read_srt(path) -> list[Cue]`
  - Tolerant parser (BOM, blank lines, multi-line text).
- `_format_timestamp(seconds) -> str`
- `_parse_timestamp(ts) -> float`

### 3.5 Hy-MT2 Local Model Path

When the model name matches `_is_hy_mt2(model)` (contains `hy-mt2` or `hy_mt2`), the translator **replaces** the cloud prompt recipe with the Hy-MT2 translator skill's approach:
- **No system prompt** is sent.
- Temperature = 0.1 (very low for deterministic line numbering).
- `extra_body` carries `top_p=0.6`, `top_k=20`, `repeat_penalty=1.05`.
- The user message uses the skill's Chinese instruction wording + `_HY_MT2_STYLE` (a Chinese foreignization directive).
- The skill's "context" mode is used when the source language is known; "basic" otherwise.
- The numbered-item protocol is still enforced.

---

## 4. Module Reference

### 4.1 `src/config.py`

**Responsibility:** Load `.env`, validate settings, construct the OpenAI client.

**Key types / functions:**
- `Settings` (dataclass): `api_key`, `base_url`, `model`
- `load_settings(override_model=None) -> Settings`
  - Reads `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`.
  - If `api_key` is missing and `base_url` points to localhost/`127.0.0.1`/`::1`/`0.0.0.0`/`.localhost`, substitutes `"sk-local"`.
  - Raises `RuntimeError` with actionable messages on missing values.
- `make_client(settings) -> OpenAI`
  - Adds OpenRouter attribution headers when `base_url` contains `"openrouter"`.

**Environment variables:**
| Variable | Required | Default | Meaning |
|----------|----------|---------|---------|
| `OPENAI_API_KEY` | Yes (remote) | -- | API key |
| `OPENAI_BASE_URL` | No | None | Override endpoint |
| `OPENAI_MODEL` | Yes | -- | Model id |

```
