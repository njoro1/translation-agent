# Translation Agent — AI Agent Documentation

> **Audience:** AI agents, coding assistants, and automated refactoring tools.
> **Goal:** Provide complete, precise, actionable context so an agent can understand, modify, test, and extend this codebase without guessing.
> **Last updated:** Strict YouTube format selection (codec/resolution picks are now honoured exactly or refused with a reason) + pyflakes clean-up + packaged-build integrity guards. 593-test suite (`python -m pytest -q`; the 14 packaged-exe tests skip only when `dist/TranslationAgent/` is absent).
>
> **Canonical source of truth:** This file is the consolidated developer/AI reference. It supersedes the
> now-archived `PROJECT.md`, `CLAUDE.md`, `TASKS.md`, and `updated implementation plan.md` (their content has
> been folded in below). `README.md` remains the user-facing quick start.
>
> **2026-09-11 root cleanup:** ten planning/review documents that had accumulated in the
> project root were verified against the code, folded in below where still relevant, and
> removed. Gone: `TASK_LIST.md`, `full implementation.md` (a.k.a. `AGENT_IMPLEMENTATION_PLAN.md`),
> `FOLLOWUP_REVIEW.md`, `IMPROVEMENTS_TRIAGE.md`, `REMAINING_RECOMMENDATIONS.md`,
> `UX_RESEARCH_REPORT.md`, `UX_FIXES_IMPLEMENTATION_PLAN.md`, `FRONTEND_DESIGN.md`,
> `implementation_plan.md`. All were fully executed, superseded, or made obsolete by the
> mode-simplification pass (cloud rescue removal in particular). The two documents that
> remain at the root are this file and `README.md`. See §18 for the classification and for
> the small number of items that were **not** implemented.

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
├── AGENT_DOCUMENTATION.md      # ← this file (consolidated developer/AI reference)
├── README.md                   # User-facing quick start
├── IMPROVEMENTS_TRIAGE.md      # Triage of improvements.txt (Approved / Rejected / Deferred)
├── SUBTITLE_QUALITY_REPORT.md  # Offline-quality analysis + resolution status
│
├── translate.py                # CLI entry point (top-level)
├── main.py                     # PySide6 + QML GUI entry point (canonical)
├── gui.py                      # Compatibility shim → main.main()
│
├── build_exe.bat               # PyInstaller onedir Windows build
├── TranslationAgent.spec       # PyInstaller spec (git-ignored, machine-specific, regenerated per build)
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
│   ├── config.py               # .env loading + OpenAI client construction
│   ├── fetch_subs.py           # YouTube subtitle fetching + title resolution
│   ├── ytdlp.py                # yt-dlp resolution + subprocess/in-process runner
│   ├── youtube_media.py        # Video/subtitle download, format selection, ffmpeg merge
│   ├── srt_io.py               # Cue dataclass + SRT read/write + filename sanitize
│   ├── translate.py            # LLM translation (context windows, numbered-item protocol) + validation
│   ├── batching.py             # Character-aware batch splitting for small CPU models
│   ├── presets.py              # Content presets + central settings resolver (CLI > preset > env > default)
│   ├── translation_windows.py  # Context-first TranslationWindow engine (before/after context)
│   ├── glossary.py             # Source→target glossary parse + prompt injection
│   ├── translation_memory.py   # SQLite exact-match translation cache
│   ├── subtitle_quality.py     # CPS / duration / char / line / leakage / residue diagnostics
│   ├── local_asr.py            # FunASR + SenseVoiceSmall CPU transcription (+ FFmpeg preprocessing)
│   ├── local_server.py         # Auto-start bundled CPU llama-server
│   ├── postprocess.py          # Fansub post-processing (line break / overlap snap / TN)
│   ├── cjk.py                  # CJK script detection + kinsoku line breaking
│   ├── ass_io.py               # Aegisub-compatible ASS writer
│   └── …
│
├── backend/                    # GUI bridge (QObject + QRunnable workers)
│   ├── __init__.py
│   ├── bridge.py               # AppBridge: QML ↔ Python state + pipeline runner
│   ├── controllers/
│   │   ├── __init__.py
│   │   └── translation.py      # TranslationWorker + _SignalWriter
│   └── models/
│       ├── __init__.py
│       ├── run_config.py       # RunConfig dataclass (argv + env)
│       └── results.py          # CueResultModel / filter proxy / QualityIssuesModel (Review + Quality tabs)
│
├── ui/qml/                     # Qt Quick declarative frontend
│   ├── Main.qml                # Header bar + Run/Review/Quality tabs + log drawer
│   ├── Theme.qml               # Design tokens (singleton)
│   ├── qmldir                  # Singleton registration
│   ├── components/
│   │   ├── qmldir
│   │   ├── AppHeader.qml       # Title | mode | preset | language | Run | status pill
│   │   ├── ModePicker.qml      # YouTube Cloud / Local Cloud / Offline segmented control
│   │   ├── PresetPicker.qml    # Content preset combo
│   │   ├── FieldLabel.qml, CompactTextField.qml, CompactComboBox.qml
│   │   ├── SectionPanel.qml, RunButton.qml, StatusPill.qml, ProgressPanel.qml
│   │   ├── ReadinessChecklist.qml, AdvancedDrawer.qml
│   │   ├── LogDrawer.qml       # Collapsible bottom log (JSON progress hidden unless debug)
│   │   ├── CuePreviewTable.qml # Virtualized review table (QAbstractListModel-backed)
│   │   └── QualityPanel.qml    # Quality badges + issue list
│   └── archive/                # Retired pre-rework UI (Sidebar/Dashboard/Settings views)
│
├── assets/fonts/               # Optional bundled CJK fonts (Noto Sans CJK; see README.txt)
│
├── vendor/                     # Bundled binaries (untracked, not git-ignored)
│   ├── funasr/                 # llama-funasr-sensevoice.exe, llama-funasr-vad.exe + DLLs
│   └── llama/                  # llama-server.exe + DLLs
│
├── gguf/                       # Downloaded GGUF models (SenseVoiceSmall, VAD, Hy-MT2)
│
├── tools/
│   ├── benchmark.py            # Offline benchmark harness (tools/benchmark.py)
│   ├── benchmark_preprocess.py # ASR preprocessing profile benchmark (cue counts, CER/WER)
│   ├── compare_context_modes.py# Context-mode A/B harness (alignment failures, reference similarity)
│   ├── check_srt.py            # SRT diagnostic (cue count, avg/max duration)
│   ├── screenshot_ui.py        # Offscreen UI screenshot helper
│   └── stamp_spec_header.py    # Applies the "GENERATED FILE" banner to TranslationAgent.spec
│
├── tests/                      # pytest suite (593 collected; no network/keys/binaries)
│   ├── test_srt_io.py, test_translate_parsing.py, test_translate_validation.py
│   ├── test_batching.py, test_glossary.py, test_translation_memory.py
│   ├── test_subtitle_quality.py, test_quality_extended.py, test_local_asr_splitting.py
│   ├── test_local_server.py, test_fetch_subs.py, test_fansub_upgrade.py, test_cjk.py
│   ├── test_cli_flags.py, test_presets.py, test_context_windows.py, test_result_json.py
│   ├── test_pipeline_modes.py, test_asr_preprocess.py, test_followup_fixes.py
│   ├── test_youtube_media.py, test_youtube_format_selection.py, test_ytdlp.py
│   ├── test_build_contract.py, test_packaged_exe_smoke.py
│   ├── test_ui_models.py, test_ux_bridge.py, test_ui_hygiene.py, test_qml_smoke.py
│   └── …
│
├── benchmark/
│   ├── README.md               # How to add test media
│   └── cases.json              # Benchmark case definitions
│
├── docs/
│   ├── PREPROCESS_BENCHMARK.md # Preprocessing profile methodology + results
│   └── archive/                # Archived docs (PROJECT.md, CLAUDE.md, TASKS.md, IMPLEMENTATION_PLAN.md)
│
├── build/                      # PyInstaller intermediate build artifacts
├── dist/                       # PyInstaller output (dist/TranslationAgent/TranslationAgent.exe)
├── debug.log                   # Rotating runtime log (GUI mode; git-ignored)
│
└── __pycache__/                # Python bytecache

---

## 3. System Architecture & Data Flow

### 3.1 High-Level Modes

Exactly three user-facing pipeline modes (cloud rescue has been removed):

| Mode ID | UI Label | Input | ASR | Translation | Requires API Key | Requires Local Translation Model |
|---------|----------|-------|-----|-------------|------------------|----------------------------------|
| `youtube_cloud` | YouTube Cloud | YouTube URL | No | Cloud LLM | Yes | No |
| `local_cloud` | Local Cloud | Local media file | FunASR + SenseVoiceSmall | Cloud LLM | Yes | No |
| `offline` | Offline | Local media file | FunASR + SenseVoiceSmall | llama.cpp (Hy-MT2) | No | Yes |

There is deliberately **no mixed mode**: local translation never falls back to
cloud rescue. The user chooses cloud or local translation per run; offline mode
never receives cloud credentials (`env={}` in the GUI run config).

### 3.2 YouTube Pipeline (CLI)

```
translate.py (main)
  ├─ parse args (url / --file / --local / --model / --out / --batch)
  ├─ if --file:
  │   └─ src.local_asr.transcribe_local_file()
  │       └─ returns (cues, source_language)
  ├─ else (YouTube URL):
  │   └─ src.fetch_subs.fetch_original_subtitles(url, preferred_lang=--source-lang)
  │       ├─ extract_video_id(url)
  │       ├─ _yt_dlp_metadata(url) → (title, lang)
  │       ├─ _fetch_english_title(video_id) → english_title
  │       ├─ (--source-lang given?) → _resolve_language_transcript (forced, no
  │       │   wrong-language fallback; skips English-first when non-English)
  │       └─ else → _resolve_transcript(video_id, lang) / _resolve_english_transcript
  │           └─ returns (cues, english_title, source_language)
  ├─ if --local:
  │   ├─ src.local_server.ensure_local_server(model_path, host, port) → (proc, how)
  │   └─ _check_local_ready(base_url)
  └─ src.translate.translate_cues(cues, client, model, batch_size, source_language,
           context_mode=…, prompt_profile=…, progress_callback=…)
      └─ builds context windows (src/translation_windows.py), calls LLM with
         numbered-item protocol + read-only before/after context
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
- `yt-dlp`: `--print %(title)s|%(language)s <url>`
  - Invoked through `src/ytdlp.run_ytdlp_capture()` — a subprocess in normal
    runs, in-process when the app is frozen. See §4.13.
- `youtube-transcript-api`: `YouTubeTranscriptApi.list(video_id)` → `TranscriptList`
  - `find_manually_created_transcript([lang])` → fallback `find_generated_transcript([lang])` → fallback first available track.
- Innertube player API (HTTP POST to `https://www.youtube.com/youtubei/v1/player` with a public key):
  - Used only to fetch the English-localized title (`hl=en`). Falls back to yt-dlp title on any failure.

### 4.3 `src/srt_io.py`

**Responsibility:** Core data class and SRT serialization/deserialization.

**Key types / functions:**
### 4.4 `src/translate.py`

**Responsibility:** Context-window translation of cues via an OpenAI-compatible chat completion API.

**Key types / functions:**
- `build_system_prompt(source_language, target_language="English", *, glossary=None, chengyu=False, classical=False, emotion=False, addendum=None) -> str`
  - Fills `_FOREIGNIZATION_DIRECTIVE` language placeholders; appends glossary, optional fansub augmentations (chengyu, Classical-Chinese register, emotion-tag awareness), and the content-preset addendum (`addendum` — appended only, never replaces the directive).
- `translate_cues(cues, client, model, batch_size=8, max_retries=3, source_language=None, *, glossary=None, translation_memory=None, context_mode=None, prompt_profile=None, progress_callback=None, scene_summary_enabled=False) -> list[str]`
  - The **canonical entry point** used by both CLI and GUI.
  - Splits cues into context-aware `TranslationWindow`s (`src/translation_windows.py`), attaches read-only before/after context plus a rolling memory of recent translated pairs, and calls `_translate_group` per window.
  - `context_mode`: `off`/`light`/`standard`/`deep` — `None` resolves to the backend default (`standard` for both; benchmark-verified safe for Hy-MT2 — see `tools/compare_context_modes.py`).
  - `prompt_profile`: selects a scoped content addendum via `src/presets.get_prompt_addendum`.
  - `progress_callback(done, total, stage)`: invoked after each window finalizes (drives GUI JSON progress).
  - `scene_summary_enabled`: optional cloud-only rolling scene summary.
  - Translation-memory interaction: a window whose cues are ALL exact TM hits is served from TM (no LLM); a partially-hit window goes to the LLM whole and TM entries are overwritten with the fresh in-context translations.
  - On misalignment a window is retried with a stricter instruction, split in half recursively, and finally translated per-item. Cue count is exact at every stage.

**Internal helpers:**
- `_is_hy_mt2(model) -> bool`
- `_numbered_block(texts) -> str` -- joins as `1. text\n2. text\n...`
- `_parse_numbered(response, expected) -> list[str] | None`
- `_translate_batch(client, model, texts, system_prompt, ...) -> list[str] | None`
  - Adds `STRICT:` prefix on retry attempts to force exact line count.
  - Passes `extra_body` for llama.cpp-only params.
- `_translate_one(client, model, text, system_prompt, ...) -> str`
- `_maybe_update_scene_summary(client, model, summary, recent_sources) -> str`
  - Best-effort rolling summary for cloud prompts; never raises, never alters numbering.

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

### 4.13 `src/ytdlp.py` — how yt-dlp is invoked

**Responsibility:** Locate yt-dlp and run it, both from source and from the
packaged executable.

**Two execution modes** (chosen by `use_inprocess()`):

| Mode | When | How |
| --- | --- | --- |
| Subprocess | normal installs | `yt-dlp` on PATH (or `YT_DLP_BIN`), else `python -m yt_dlp`; stdout is streamed and the `Popen` is exposed for cancellation |
| In-process | `sys.frozen` (no `YT_DLP_BIN`) | `yt_dlp.main(argv)` runs in this thread with `sys.stdout`/`sys.stderr` swapped for a line sink |

**Why the in-process mode exists:** a one-file PyInstaller build has no Python
interpreter to spawn — `sys.executable` *is* the app — and an end user cannot be
assumed to have `yt-dlp.exe` installed. `yt_dlp.main()` is called with the same
CLI arguments (minus the launcher prefix, stripped by `_strip_launcher()`), so
the output is identical to the subprocess version and every existing
`[download]` / `[info]` / `Destination:` parser keeps working. It also fixes
`--windowed` builds, where `sys.stdout` is `None`.

**Key functions:**
- `yt_dlp_cmd() -> list[str]` — subprocess prefix (`YT_DLP_BIN` → PATH → `python -m yt_dlp`).
- `run_ytdlp(cmd, on_line, cancel_check, proc_ref, env) -> int` — streaming; `on_line(line)` may return `False` to abort.
- `run_ytdlp_capture(cmd, timeout, env) -> str` — one-shot `--dump-json` / `--print` queries.
- `yt_dlp_available() -> bool` — accounts for the bundled copy (the old `shutil.which("yt-dlp")` guard was wrong for frozen builds).

**Errors:** `YtdlpUnavailable`, `YtdlpTimeout`, `YtdlpFailed` (`.output` carries
yt-dlp's own message). Escape hatch: `YT_DLP_INPROC=1` forces the in-process
path, which is how the tests exercise it.

**Related:** `src/youtube_media._ffmpeg_exe()` also looks in
`sys._MEIPASS` / next to the `.exe` for a bundled `ffmpeg*.exe`, because
`shutil.which()` cannot see binaries PyInstaller unpacked there.

> **ffmpeg must be named `ffmpeg.exe` for the merge to run.** yt-dlp's
> `--ffmpeg-location <dir>` only recognises a binary literally called
> `ffmpeg` / `ffmpeg.exe`; a packaged binary such as
> `ffmpeg-win-x86_64-v7.1.exe` is *never* found, so the video+audio merge
> silently never runs and the user gets two separate files. `_ffmpeg_exe()`
> therefore returns a `ffmpeg.exe` — copying the discovered binary to a
> `ffmpeg.exe` sidecar (in the bundle dir if writable, else a temp dir) when the
> real name differs — and `_run_yt_dlp` passes that file's directory to
> `--ffmpeg-location`. Note: `build_exe.bat` bundles the binary under its real
> name (`ffmpeg-win-x86_64-v7.1.exe`) — PyInstaller's `--add-binary` treats the
> destination as a *directory*, so it cannot rename at build time. The runtime
> rename above is what yields the `ffmpeg.exe` yt-dlp needs. Regression tests
> live in `tests/test_ytdlp.py`
> (`TestFfmpegMerge`, `TestFrozenFfmpegLookup`).

---

## 7. Build & Distribution

### 7.1 PyInstaller Spec (`build_exe.bat`)

Produces a **onedir** bundle at `dist/TranslationAgent/TranslationAgent.exe`
(with `--onedir --windowed`). We deliberately avoid `--onefile`: the bundle is
~350 MB (it embeds the funasr + llama vendored binaries), and onefile re-extracts
the whole thing to `%TEMP%\_MEIxxxx` on every launch — which triggers
"Failed to extract Crypto…" (PYI-16308) when antimalware blocks the crypto `.pyd`
mid-extraction, or when the temp drive is full / the path exceeds MAX_PATH.
onedir keeps files on disk, so there is no runtime extraction and that error class
disappears (and startup is far faster). Run the app from
`dist/TranslationAgent/TranslationAgent.exe`.

**Bundled data:**
- `ui/qml` (QML source)
- `vendor/funasr` (FunASR binaries)
- `vendor/llama` (llama-server + DLLs)
- `PySide6/qml/Qt`, `PySide6/qml/QtQml`, `PySide6/qml/QtQuick`
- `PySide6/plugins/platforms`, `imageformats`, `styles`, `iconengines`, `qmltooling`
- `ffmpeg` (from `imageio-ffmpeg`) — bundled under its real name
  (`ffmpeg-win-x86_64-v7.1.exe`); `src.youtube_media._ensure_ffmpeg_exe_named()`
  copies it to `ffmpeg.exe` at runtime so yt-dlp's `--ffmpeg-location` scan
  finds it and the video+audio merge actually runs (otherwise downloads ship as
  two separate files)
- `yt-dlp` (as a Python package — `--hidden-import yt_dlp` pulls in yt-dlp's own
  PyInstaller hook, which collects the extractors, `requests`/`certifi` and the
  yt-dlp-ejs JS helpers)
- Hidden imports: `backend.*`, `src.*`, `translate`, `dotenv`, `openai`, `yt_dlp`

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
- yt-dlp runs **in-process** (§4.13); it must not be shelled out to.
- **yt-dlp-ejs** needs a JS runtime (deno/node/bun) for some YouTube formats.
  The JS helpers are bundled, but the runtime itself is not — if it is missing,
  yt-dlp reports the usual "yt-dlp-ejs" error and the app surfaces it.


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
| `FUNASR_MAX_SEGMENT_MS` | `local_asr.py` | `6000` | Max ASR segment ms |
| `FUNASR_MAX_END_SILENCE_MS` | `local_asr.py` | `250` | Max trailing silence ms |
| `FUNASR_SPEECH_NOISE_THRES` | `local_asr.py` | `0.55` | VAD speech threshold |
| `FUNASR_NOISE_DB` | `local_asr.py` | `-35` | ffmpeg silence noise floor |
| `FUNASR_MIN_SILENCE_S` | `local_asr.py` | `0.25` | Min silence duration |
| `FUNASR_MAX_CUE_DURATION_MS` | `local_asr.py` | `3200` | Max cue duration |
| `FUNASR_MAX_CUE_CHARS` | `local_asr.py` | `70` | Max cue chars (non-CJK) |
| `FUNASR_MAX_CUE_CHARS_CJK` | `local_asr.py` | `48` | Max cue chars (CJK) |
| `FUNASR_KEEP_TAGS` | `local_asr.py` | `0` | If `1`, keep ASR tags |
| `TRANSLATION_GLOSSARY` | `translate.py` | unset | Glossary file path |
| `TRANSLATION_MEMORY_MODE` | `translate.py` | `auto` | `auto` \| `on` \| `off` |
| `TRANSLATION_MEMORY_DB` | `translate.py` | `./cache/translation_memory.sqlite3` | TM database path |
| `HY_MT2_MAX_BATCH_CUES` | `translate.py` | `12` | Hy-MT2 max window cues (legacy alias) |
| `HY_MT2_MAX_BATCH_CHARS_CJK` | `translate.py` | `700` | Hy-MT2 max window chars (CJK) |
| `HY_MT2_MAX_BATCH_CHARS_NON_CJK` | `translate.py` | `1000` | Hy-MT2 max window chars (non-CJK) |
| `FUNASR_PREPROCESS` | `presets.py` | unset | ASR preprocessing profile override (auto preset only) |
| `TRANSLATION_CONTEXT_MODE` | `presets.py` | unset | Context mode override (auto preset only) |
| `TRANSLATION_PROMPT_PROFILE` | `presets.py` | unset | Prompt profile override (auto preset only) |
| `LLAMA_SERVER_THREADS` | `local_server.py` | `0` | Local server threads |
| `LLAMA_SERVER_MLOCK` | `local_server.py` | `0` | Enable mlock (1 = on) |
| `FUNASR_VAD_UNITS` | `local_asr.py` | `ms` | VAD output time units |
| `FUNASR_OUTPUT_FLAG` | `local_asr.py` | auto-detect | VAD/ASR output file flag |
| `FFMPEG_BIN` | `local_asr.py` | ffmpeg on PATH | ffmpeg binary path |
| `IMAGEIO_FFMPEG_EXE` | `local_asr.py` | -- | Alternative ffmpeg path |
| `QT_QUICK_CONTROLS_STYLE` | `main.py` | `Basic` | Qt Quick Controls style |
| `QT_PLUGIN_PATH` | `main.py` | auto-set | Qt plugins directory |
| `PYTHONDONTWRITEBYTECODE` | -- | not set | Set to `1` to suppress `__pycache__` |

---

## 15. Testing & Validation

Run the automated unit test suite (no network / keys / binaries required):

```bash
python -m pytest -q
```

Tests live in `tests/` and cover:
- `test_srt_io.py` — timestamp format/parse, SRT roundtrip, filename sanitization.
- `test_translate_parsing.py` — `_numbered_block`, `_parse_numbered`, `_is_hy_mt2`.
- `test_translate_validation.py` — `looks_untranslated`, per-item failure behavior.
- `test_batching.py` — `chunk_texts`, `estimate_text_weight`, `is_cjk_language`.
- `test_glossary.py` — glossary file parsing, formatting, hashing.
- `test_translation_memory.py` — TM put/get, key separation, graceful failure.
- `test_subtitle_quality.py` — CPS/duration/char/line thresholds, report building.
- `test_local_asr_splitting.py` — `_split_text` and `_segment_to_cues`.
- `test_local_server.py` — server auto-start / warmup helpers (no network).
- `test_fetch_subs.py` — video-id parsing and fetch helpers.
- `test_fansub_upgrade.py` — `postprocess`, `ass_io` (incl. `font_for_language` / font flags).
- `test_cjk.py` — `src/cjk.py` detection, width, and kinsoku line breaking.
- `test_cli_flags.py` — `--json-progress`, `--ass-font`/`--ass-fontsize` wiring.
- `test_pipeline_modes.py` — GUI run-config per mode (no `--local` leakage, offline strips cloud env).
- `test_asr_preprocess.py` — preprocessing filter strings, auto→basic, duration-mismatch fallback.
- `test_presets.py` — preset table values, precedence (explicit > preset > env > default), addenda.
- `test_context_windows.py` — window builder, context modes, prompts, TM interaction, fallback ladder.
- `test_result_json.py` — `--result-json` schema, final-line contract, untranslated flagging.
- `test_quality_extended.py` — tag/markup leakage, CJK residue, duplicates, overlap.

Run with `python -m pytest -q` (593 tests, ~110 s; no network / keys / binaries
required). Latest verified run: **593 passed**, 4 deprecation warnings.
The 14 `tests/test_packaged_exe_smoke.py` tests **skip** when `dist/TranslationAgent/`
is absent and **run** when it is present — a skip is honest about what was not verified.
Note: always pass `--basetemp <a path that does not exist yet>`; pytest's garbage
collection of old numbered temp dirs becomes a bulk delete that the sandbox blocks.

**Static checks (run these too):**

```bash
python -m pyflakes translate.py main.py gui.py backend/*.py backend/**/*.py src/*.py
```

pyflakes catches `undefined name` and unused-variable bugs that the test suite
cannot reach. It is deliberately **not** part of the runtime requirements —
install it in a scratch venv (`pip install pyflakes`).

Worth knowing: two shipped bugs were invisible to tests and only pyflakes found
them — `backend/bridge.py` used `Qt.EditRole` without importing `Qt` (the
"Replace all" button raised `NameError`), and `translate.py` referenced
`youtube_media` from a function while the import lived inside a *different*
function (the CLI could not download video at all). Treat a clean pyflakes run
as a release gate.

**Scope — and what is *not* a bug.** `translate.py` imports `openai` and
`dotenv` at module level without referencing them in that file. That is
intentional: PyInstaller only bundles modules it can see are imported, and
`src/translate.py` imports `openai` lazily, so these top-level imports exist
purely to make the packaged build include them. Do **not** "clean them up".
Anything genuinely unused should still be removed — pyflakes only reports
`imported but unused`, so the gate above is filtered to undefined names and
unused variables.

**The build has no full end-to-end test — but its contract is checked.**

`tests/test_build_contract.py` parses the real `build_exe.bat` and fails if the
build could not succeed, without running PyInstaller:

- every path the script guards with `if not exist` (vendor binaries) exists, and
  every `--add-data` / `--add-binary` source exists;
- every `--hidden-import` name actually resolves (a stale name silently drops
  code out of the exe);
- the runtime-critical modules are declared;
- **every `PySide6.QtXxx` imported in first-party code has a matching
  `--hidden-import`** — the built exe ships a trimmed Qt, so a new Qt import
  would otherwise crash only *inside the packaged app*;
- the spec is not treated as build input, still parses, and carries its header;
- the script resolves PySide6/ffmpeg dynamically (i.e. stays portable).

Mutation-checked: adding an undeclared `PySide6.QtBluetooth` import and
renaming a guarded vendor binary each make it fail, so it is not vacuous.

**The built exe is also smoke-tested, and its currency is enforced.**

`tests/test_packaged_exe_smoke.py` launches `dist/TranslationAgent/TranslationAgent.exe`
with `QT_QPA_PLATFORM=offscreen`, waits for `debug.log` to report the QML load,
then kills it. It skips (not passes) when the bundle is absent — a skip is
honest about what was not verified.

Unlike a plain "does it start" test, it guards against **green-lighting a build
that does not reflect the source**, which is how a smoke test normally lies:

- `test_build_is_newer_than_all_bundled_sources` — fails if any bundled
  first-party `.py` / `.qml` is newer than the exe, naming the stale files.
- `test_bundle_is_internally_consistent` — buckets `_internal/**` by build
  *date* and fails when the newest date holds under half the files. This is the
  signature of a build interrupted mid-COLLECT: the old directory survives, a
  few new files land on top, and **the exe still launches**. The mtime check
  above cannot see it, because the exe is the *old* file and looks current.
- `test_bundled_qml_matches_the_source_tree` — an `--add-data` miss can ship an
  older `Main.qml` / `YouTubeVideoPanel.qml`; compares bytes.

> **If you rebuild, check the exit code.** A PyInstaller run can fail during
> COLLECT and still leave a plausible-looking `dist/`. The observed causes were
> a sandbox blocking PyInstaller's own cleanup of a large output directory
> (`SAFE_DELETE_BULK_CONFIRM_REQUIRED`), and `ENOSPC` when the target drive is
> full. On the latter: a full onedir build needs roughly 1 GB free.

**Known limitation: `TranslationAgent.spec` is machine-specific.**

The `GENERATED FILE — do not hand-edit` banner is applied *after* the build by
`tools/stamp_spec_header.py`, called from `build_exe.bat`. It cannot live in the
spec itself: PyInstaller rewrites the file from the CLI flags on every run, so a
hand-added comment is destroyed by the very next build — exactly when a
contributor is most likely to open it and start editing. The stamper keeps the
`# -*- coding: utf-8 -*-` declaration on line 1 (Python only honours it within
the first two lines) and is idempotent.

`build_exe.bat` invokes `python -m PyInstaller` with explicit flags and does
**not** read the `.spec`; PyInstaller happens to write a spec back out after
each run, which is why the committed file contains absolute paths such as
`C:\Users\Njoro\...\Python312\Lib\site-packages\...`. Those paths describe the
last build machine only. Building with the committed spec on any other machine
will fail; use `build_exe.bat` (it resolves PySide6 and ffmpeg via `python -c`
at build time), or regenerate the spec there. Do not hand-edit the committed
spec — the next build overwrites it.

**Manual validation checklist:**
1. YouTube URL with manual subtitles → SRT with correct timestamps and translated English text.
2. YouTube URL with auto-generated-only subtitles → same as above.
3. Local video with no subtitles → FunASR transcription → English translation.
4. Local model path (`--local --local-model model.gguf`) → server auto-starts → translation succeeds.
5. Existing server path (`--local` without `--local-model`) → connects to running server.
6. Local Hy-MT2: confirm effective window size is reduced and cue count matches.
7. Local media CJK: confirm ASR tags are stripped and cues are shorter for CJK.
8. Cloud rescue: REMOVED — verify no `--cloud-rescue*` flag exists and no docs describe it as active.
9. GUI mode: run translation, verify progress bar updates from JSON progress, Review/Quality tabs populate from result JSON, log drawer stays collapsed.
10. `python tools/check_srt.py output.srt` → verify average/max cue durations are reasonable.
11. Preprocessing benchmark: `python tools/benchmark_preprocess.py --media sample.mp4` → comparable per-profile metrics.
12. Frozen build: `build_exe.bat`, run `TranslationAgent.exe`, verify vendor binaries + QML + fonts + logs.

---

## 16. Glossary

| Term | Meaning |
|------|---------|
| **Cue** | One subtitle entry: `start`, `end`, `text`. In code: `src.srt_io.Cue`. |
| **Foreignization** | Translation philosophy: preserve source culture/voice/honorifics; do not domesticate. |
| **Numbered-item protocol** | Batch translation method: cues are numbered `1.` ... `N.` sent to LLM, which must return same numbers. |
| **Hy-MT2** | Tencent's 1.8B-parameter translation model; Q8_0-quantized GGUF (`Hy-MT2-1.8B-Q8_0.gguf`). |
| **SenseVoiceSmall** | FunASR's small ASR model (GGUF). |
| **FunASR VAD** | Voice Activity Detection model (`fsmn-vad.gguf`) used to segment audio. |
| **llama-server** | llama.cpp's OpenAI-compatible HTTP server (`llama-server.exe`). |
| **STQ** | 1.25-bit quantization kernel for llama.cpp (PR #22836); no longer used now that the default model is Q8_0. |
| **AppBridge** | `backend.bridge.AppBridge`; the single QObject exposed to QML. |
| **RunConfig** | `backend.models.run_config.RunConfig`; argv + env for one pipeline run. |
| **TranslationWorker** | `backend.controllers.translation.TranslationWorker`; QRunnable that runs `translate.main()` off the UI thread. |
| **Translation memory (TM)** | SQLite cache of exact source→target lines, keyed by language/model/glossary hash. |
| **Glossary** | Plain-text source→target term list injected into prompts for consistent terminology. |
| **Cloud rescue** | REMOVED. Local translation never falls back to the cloud; users pick cloud or local per run. |
| **Content preset** | `src/presets.py` scenario profile (auto/drama/anime/music/documentary/variety/lecture) tuning ASR, preprocessing, context mode, and prompt addenda. |
| **Context window** | `src/translation_windows.TranslationWindow`; current cues plus read-only before/after context; the primary translation unit. |
| **Result JSON** | Machine-readable run output (`--result-json`) consumed by the GUI Review/Quality tabs. |
| **Fallback ladder** | Retry → split-in-half → per-item fallback used when a numbered window fails. |
| **Quality report** | JSON diagnostics of CPS / duration / char-count / line-count / empty cues / tag leakage / CJK residue / duplicates / overlaps. |
| **_MEIPASS** | PyInstaller's temp extraction directory (when frozen). |
| **QSettings** | Qt's persistent settings (registry on Windows). |

---

## 17. Contact / References

- **GitHub:** `https://github.com/njoro1/translation-agent`
- **Hy-MT2 model:** `https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF`
- **SenseVoiceSmall GGUF:** `https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF`
- **fsmn-vad GGUF:** `https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF`
- **FunASR runtime:** GitHub releases tagged `runtime-llamacpp-v*`
- **Hy-MT2 translator skill:** `https://skillhub.cn/skills/hy-mt2-translator`

---

## 8. Key Design Invariants (Do Not Break)

1. **Timestamps are sacred.** `start`/`end` are preserved for YouTube or
   cloud-translated output; only `text` is replaced. The **only** exception is the
   fansub post-processing overlap snap in `postprocess.snap_overlaps`, which trims
   a cue's `end` *only* when two consecutive cues actually overlap, never below
   300 ms duration (see §postprocess).
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
| Git history is coarse | Medium | Six commits total (`9ae8599` latest); the mode-simplification, UX-rework and YouTube-format work is largely uncommitted working-tree state. Commit before any risky change. |
| `vendor/` untracked | Medium | Binaries exist locally but are not committed or gitignored. Decide policy. |
| `TranslationAgent.spec` is machine-specific | Low | Regenerated by every build; contains absolute paths from the last build machine. Git-ignored. Never hand-edit. |
| `_probe_youtube.py`, `_e2e_download.py`, `_verify_ui_message.py`, `_shot_*.py`, `_check_*.py`, `_mix_probe/` in root | Low | Scratch probes/artifacts; not part of the shipped pipeline. |
| `combined md files.txt`, `improvements.txt`, `full implementation.md` predecessors | Low | Historical scratch inputs. (`full implementation.md` was removed in the 2026-09-11 cleanup.) |
| 5 UI sub-features from the UX plan never landed | Low | See §18.3 — stage timers, mode-aware language labels, resolved-preset label, YouTube step strip. |

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

Edit `ui/qml/Main.qml` and the components under `ui/qml/components/`. Do **not** edit
`ui/qml/archive/**` — that tree is retired pre-rework UI and is not loaded at runtime.

To expose a new field to QML, add it to `AppBridge` in `backend/bridge.py` as a `Property` with a setter that calls `_set_field` / emits the appropriate signal. Keep presentation in QML and state in the bridge.

### 11.5 Adding a New Backend

1. Add a new backend option in `AppBridge._backend` (and `SettingsView.qml`).
2. In `AppBridge._build_run_config()`, set `env` / `argv` for the new backend.
3. In `src/config.py` or `translate.py`, handle the new backend type.

### 11.6 Building / Releasing

- Run `build_exe.bat` after any Python/QML change.
- Ensure `vendor/` binaries and `gguf/` models are present.
- The output is `dist/TranslationAgent/TranslationAgent.exe` (onedir). Run it from
  that folder so `debug.log` and relative model paths resolve.

---

## 5. CLI Reference

### 5.1 All Flags

| Flag | Default | Required | Meaning |
|------|---------|----------|---------|
| `url` (positional) | -- | YouTube mode | YouTube video URL |
| `--file` | -- | Local mode | Local media path |
| `--model` | `OPENAI_MODEL` | No | Override model |
| `--out` | `<title>.srt` | No | Output path |
| `--batch` | `8` | No | Cues per translation call |
| `--local` | off | No | Use llama.cpp server |
| `--local-host` | `127.0.0.1` | No | Server host |
| `--local-port` | `8080` | No | Server port |
| `--local-model-name` | `Hy-MT2-1.8B-Q8_0` | No | Model id for local server |
| `--local-model` | -- | No | Auto-start bundled server against this GGUF |
| `--asr-bin` | `FUNASR_SENSEVOICE_BIN` / PATH | No | SenseVoice binary |
| `--asr-vad-bin` | `FUNASR_VAD_BIN` / PATH | No | VAD binary |
| `--asr-model` | `./gguf/sensevoice-small-q8.gguf` | No | SenseVoice GGUF |
| `--asr-vad-model` | `./gguf/fsmn-vad.gguf` | No | VAD GGUF |
| `--asr-lang` | `auto` | No | ASR source language (`auto`/`zh`/`en`/`ja`/`ko`/`yue`) |
| `--asr-threads` | `4` | No | FunASR CPU threads |
| `--asr-max-segment-ms` | `6000` | No | Max ASR segment length |
| `--asr-max-end-silence-ms` | `250` | No | Trailing silence for VAD |
| `--asr-speech-noise-threshold` | `0.55` | No | VAD speech/noise threshold |
| `--asr-noise-db` | `-35` | No | ffmpeg silencedetect noise floor |
| `--asr-min-silence-s` | `0.25` | No | Min silence for ffmpeg silence detection |
| `--asr-max-cue-duration-ms` | `3200` | No | Max subtitle cue duration |
| `--asr-max-cue-chars` | `70` | No | Max subtitle cue character count |
| `--asr-max-cue-chars-cjk` | `48` | No | Max subtitle cue character count (CJK) |
| `--asr-no-tags` | off | No | Strip SenseVoice language tags |
| `--asr-keep-tags` | off | No | Keep ASR `<|...|>` tags (disable default stripping) |
| `--asr-preprocess` | `auto` | No | FFmpeg preprocessing profile (`auto`/`none`/`basic`/`loudnorm`/`denoise`) |
| `--content-preset` | `auto` | No | Scenario preset (`auto`/`drama`/`anime`/`music`/`documentary`/`variety`/`lecture`) |
| `--prompt-profile` | preset | No | Prompt addendum profile (general = none) |
| `--context-mode` | preset/backend | No | Translation context level (`off`/`light`/`standard`/`deep`) |
| `--context-summary` | off | No | Cloud-only rolling scene summary |
| `--source-lang` | unset | No | YouTube: force a source track (ja/zh/zh-TW/ko/yue/en); Local: translation source hint when ASR is auto/unknown |
| `--format` | `srt` | No | Output format (`srt` or `ass`) |
| `--ass-font` | source-detect | No | Override ASS font name |
| `--ass-fontsize` | `52` (effective) | No | Override ASS font size |
| `--glossary` | `TRANSLATION_GLOSSARY` | No | Glossary file path |
| `--translation-memory` | `auto` | No | TM mode (`auto`/`on`/`off`) |
| `--quality-report` | unset | No | Write a JSON quality report |
| `--result-json` | unset | No | Write machine-readable result JSON for GUI review |
| `--strict-quality` | off | No | Exit 1 on serious quality errors |
| `--json-progress` | off | No | Emit machine-readable progress lines |
| `--local-threads` | `0` | No | Local server CPU threads |
| `--local-mlock` | off | No | Lock local model in RAM |

Removed flags (do not reintroduce): `--cloud-rescue`, `--cloud-rescue-model`,
`--cloud-rescue-batch`. Cloud rescue was removed by product decision; local
translation never falls back to the cloud.

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
| `asr/maxSegmentMs` | `6000` | No |
| `asr/maxEndSilenceMs` | `250` | No |
| `asr/speechNoiseThreshold` | `0.55` | No |
| `asr/noiseDb` | `-35` | No |
| `asr/minSilenceS` | `0.25` | No |
| `asr/maxCueDurationMs` | `3200` | No |
| `asr/maxCueChars` | `70` | No |
| `asr/maxCueCharsCjk` | `48` | No |
| `asr/noTags` | `false` | No |
| `local/model` | `""` | No |

**API key is NOT persisted.**

|------|-----|
| `sensevoice-small-q8.gguf` | `https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/main/sensevoice-small-q8.gguf` |
| `fsmn-vad.gguf` | `https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF/resolve/main/fsmn-vad.gguf` |
| `Hy-MT2-1.8B-Q8_0.gguf` | `https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q8_0.gguf` |

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
| `FUNASR_MAX_SEGMENT_MS` | `6000` | Max ASR segment length |
| `FUNASR_MAX_END_SILENCE_MS` | `250` | Trailing silence before VAD closes |
| `FUNASR_SPEECH_NOISE_THRES` | `0.55` | VAD speech/noise threshold |
| `FUNASR_NOISE_DB` | `-35` | ffmpeg silencedetect noise floor |
| `FUNASR_MIN_SILENCE_S` | `0.25` | Min silence for ffmpeg silence detection |
| `FUNASR_MAX_CUE_DURATION_MS` | `3200` | Max subtitle cue duration |
| `FUNASR_MAX_CUE_CHARS` | `70` | Max subtitle cue character count (non-CJK) |
| `FUNASR_MAX_CUE_CHARS_CJK` | `48` | Max subtitle cue character count (CJK) |
| `FUNASR_KEEP_TAGS` | `0` | If `1`, keep ASR tags |
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
- `start_server(model_path, host, port, n_ctx, n_gpu_layers, *, threads=0, mlock=False) -> Popen`
  - Starts hidden background process (`CREATE_NO_WINDOW`).
  - Registers in `_ACTIVE` dict keyed by `(abs_model_path, host, port)`.
  - Optional `threads` > 0 adds `-t <n>`; `mlock=True` adds `--mlock`. Uses
    `_start_with_fallback_flags` to retry without optional flags if rejected.
- `_start_with_fallback_flags(base_cmd, optional_flags, key) -> Popen`
  - Tries optional flags; if the process exits within ~2s, retries without them.
- `warmup_local_server(base_url, model, *, timeout=30.0) -> bool`
  - Sends a tiny chat completion to initialize the model/caches. Never fatal.
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
- **Dynamic batching** (see `src/batching.py`): Hy-MT2 uses ≤ 12 cues / ≤ 700 (CJK) or 1000 (non-CJK) chars per request, with a `retry → split → per-item` fallback ladder.
- **Preferred model file:** `./gguf/Hy-MT2-1.8B-Q8_0.gguf`. See `resolve_local_model_path` in `backend/bridge.py`.

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

---

## 4. Module Reference (pipeline support modules)

### 4.13 `src/batching.py`

**Responsibility:** Split lists of cue texts into model-safe request batches, respecting cue-count and character limits (CJK-aware).

**Key types / functions:**
- `is_cjk_language(source_language: str | None) -> bool` — True when the *language code/name* is Chinese, Japanese, Korean, or Cantonese (normalized, region-stripped).
- `estimate_text_weight(text: str, source_language: str | None) -> int` — non-whitespace character count (the CJK distinction applies at the *batch budget* level, not per-character).
- `chunk_texts(texts, *, max_items, max_total_chars, source_language=None) -> list[list[int]]` — returns batches of original indices (order preserved, never drops).

### 4.13b `src/cjk.py` *(new)*

**Responsibility:** Lightweight CJK script detection and kinsoku-aware line breaking. Used by the CLI to auto-detect the source language from a large cue sample, and available for future CJK-target/bilingual output.

**Key types / functions:**
- `contains_cjk(text: str) -> bool`
- `detect_cjk_language(text: str, default=None) -> str | None` — `zh`/`ja`/`ko` by script ratios; requires ≥ 8 CJK chars to avoid guessing.
- `detect_cjk_from_cues(cues, sample_size=80) -> str | None`
- `char_width(ch) / text_width(text)` — display units (full-width = 2).
- `break_cjk(text, max_width=26, max_lines=2) -> str` — kinsoku-aware `\N`-joined lines.

### 4.14 `src/glossary.py`

**Responsibility:** Parse an optional `source→target` glossary file and format it into the prompt.

**Key functions:**
- `load_glossary(path) -> list[tuple[str, str]]` — plain-text `source<TAB>target`, `source = target`, or `source -> target`; dedupes and truncates.
- `format_glossary(entries) -> str` — bullet list for the prompt (capped length).
- `glossary_hash(entries) -> str` — SHA-256 of the formatted glossary (part of the TM key).

**Environment variable:** `TRANSLATION_GLOSSARY` (path, optional; no-op when unset).

### 4.15 `src/translation_memory.py`

**Responsibility:** SQLite-backed exact-match cache of previously translated source lines.

**Key API (class-based):**
- `TranslationMemory(db_path=...)` — opens/creates the DB (with `_purge_poisoned_entries`), disables itself gracefully on any DB error.
- `translation_memory.get(*, source_language, source_text, model_profile, glossary_hash) -> str | None`
- `translation_memory.put(*, source_language, source_text, translated_text, model_profile, glossary_hash) -> None`
- `translation_memory.close() -> None`
- `make_key(*, source_language, source_text, model_profile, glossary_hash) -> str` — SHA-256 of `lang|model_profile|glossary_hash|normalized_source`.

**Environment variables:** `TRANSLATION_MEMORY_MODE` (`auto`/`on`/`off`), `TRANSLATION_MEMORY_DB`.

### 4.16 `src/subtitle_quality.py`

**Responsibility:** Post-translation quality diagnostics for the generated SRT.

**Key functions:**
- `analyze_cues(cues) -> list[CueIssue]` — per-cue issues (CPS, chars, duration, lines, empty text, ASR/fansub tag leakage, untranslated marker, CJK residue, duplicate consecutive translation, overlap).
- `build_report(cues, *, untranslated_count=0) -> QualityReport` — aggregated counts + issues (incl. `tag_leakage_count`, `cjk_residue_count`, `duplicate_count`, `overlap_count`).
- `QualityReport.to_dict() / to_json(indent=2)` — serializable.
- `print_summary(cues, *, untranslated_count=0) -> QualityReport`.

Severity policy: leakage/empty/untranslated-marker are errors; small CJK residue
(ratio ≤ 0.5 — likely a retained name/honorific/glossary term) is a warning;
mostly-CJK lines are errors; duplicates/overlaps/CPS/length/duration are warnings.
`--strict-quality` fails on any error or untranslated cue; warnings alone never fail.

### 4.17 `src/presets.py` and `src/translation_windows.py`

**`src/presets.py`:** frozen `ContentPreset` dataclasses (`PRESETS`) for
auto/drama/anime/music/documentary/variety/lecture plus
`resolve_effective_settings(args)` enforcing precedence
explicit CLI/GUI value > content preset > environment variable > built-in default,
and `PROMPT_ADDENDA` / `get_prompt_addendum(profile)` for scoped prompt addenda.

**`src/translation_windows.py`:** the context-first engine. `TranslationWindow`
(start_index, cues, before_context pairs, after_context sources),
`CONTEXT_PROFILES` (off/light/standard/deep → before/after/memory budgets),
`build_windows()` (cue-count / char / duration / scene-gap constraints; never
drops or reorders cues), and the cloud/Hy-MT2 context prompt builders.

### 4.18 `src/postprocess.py` and `src/ass_io.py`

**Responsibility:** `postprocess.py` applies fansub-quality cleanup (fusion repair, residual-CJK strip, line breaking, translator-note placement, overlap snapping) to every output cue. `ass_io.py` writes Aegisub-compatible ASS with a style header, a `Title:` field, and a font chosen from the source language via `font_for_language(source_language)` (see `FONT_BY_LANG`).

---

## 17. Archived documentation (consolidated into this file)

To reduce repository-root clutter, the following historical documents were folded
into this canonical reference and **moved to `docs/archive/`** (content preserved):

- **`PROJECT.md`** (now `docs/archive/PROJECT.md`) — the developer narrative/history
  ("Translation Agent — Project Documentation"). Unique, still-relevant parts
  preserved here: the fansub philosophy (foreignization over fluency,
  `[Translator's Note]` convention), the recommended roadmap, and known-gaps notes.
- **`CLAUDE.md`** (now `docs/archive/CLAUDE.md`) — Claude Code guidance. Unique parts
  preserved: Windows platform conventions (use `python`, not `python3`; `copy`, not
  `cp`; backslash paths) and the key invariants list below.
- **`TASKS.md`** (now `docs/archive/TASKS.md`) — the implementation task tracker. It
  recorded the phases (baseline tests, batching, glossary/TM, local server warmup,
  ASR tag stripping, quality diagnostics, CLI updates, GUI changes,
  model download, benchmark, test suite, CJK detection). Every item was completed.
  (Cloud rescue, originally on that list, was later removed by product decision.)
- **`updated implementation plan.md`** (now `docs/archive/IMPLEMENTATION_PLAN.md`) —
  the original multi-phase plan spec (~3.2k lines). Fully superseded by the
  completed work described in this file; no open tasks remain.

### Key invariants (preserved from CLAUDE.md / PROJECT.md)

- Original `start`/`end` times are preserved — only `text` is replaced — with the
  **single exception** of the post-processing overlap snap
  (`postprocess.snap_overlaps`), which trims a cue's `end` only when consecutive
  cues overlap, and never below 300 ms. For locally-ASR'd cues, timing is *created*
  by the ASR pass (keyframe snap), so it is not "original" YouTube timing.
- Cue count out == cue count in (numbered-item protocol). Never drop/merge/reorder.
- Target language is English, fixed by design.
- The returned title from `fetch_subs.py` is YouTube's **English** title (used for
  the SRT filename), not a translation we produce.
- Local ASR is **FunASR + SenseVoiceSmall only**; Whisper.cpp is removed and must
  not be reintroduced.
- `_FOREIGNIZATION_DIRECTIVE` / `_HY_MT2_STYLE` prompt invariants stay intact.
- Cloud endpoints require a real key; local servers accept a placeholder.
- Never block the QML thread — the pipeline runs on the `QThreadPool`, the CLI is
  invoked in-process with patched streams.

### Recommended roadmap (from PROJECT.md, still open)

- Validate end-to-end output on a range of videos (manual vs. auto captions, various
  source languages, offline Hy-MT2 path).
- Consider graceful handling when `vendor/` binaries are absent at runtime (currently
  only enforced at build time).
- See §18.3 for the open backlog.

---

## 18. Project State Record (2026-09-11 consolidation)

### 18.1 What was removed from the repository root

Ten root-level Markdown documents were read, checked against the working tree, and
deleted. Each had either been fully executed, superseded by a later pass, or made
obsolete by a product decision.

| Document | Verdict | Why |
|---|---|---|
| `TASK_LIST.md` | **Implemented** | Checklist for the mode-simplification / presets / context / UI pass. Every box ticked, Definition of Done met. Superseded by the code. |
| `full implementation.md` (self-titled `AGENT_IMPLEMENTATION_PLAN.md`) | **Implemented** | The master brief for that same pass. All five requirements landed (3 modes, rescue removal, FFmpeg preprocessing, content presets, context-first windows, UI rework). |
| `implementation_plan.md` | **Implemented** | YouTube download / flow-separation plan, marked `STATUS: COMPLETE` at 348 tests. Superseded by later YouTube-format-selection work (now 593 tests). |
| `FOLLOWUP_REVIEW.md` | **Implemented + partly obsolete** | P0-1…P0-7 and P1-1/P1-2 all fixed. Its cloud-rescue sections (P0-1, and the rescue rows in the tables) describe a feature that was subsequently **removed** — obsolete. |
| `IMPROVEMENTS_TRIAGE.md` | **Superseded + partly obsolete** | Triage of `improvements.txt`. Approved items landed; many "Deferred" items (context window, ASR presets, extended quality checks) were later implemented; rescue items obsolete. Its own banner already declared itself superseded. |
| `REMAINING_RECOMMENDATIONS.md` | **Obsolete** | A forward-looking backlog that has since been almost entirely delivered: context windows, ASR presets (as content presets), extended CJK quality checks, GUI JSON-progress consumption, bundled CJK fonts, cue preview table, quality panel. |
| `UX_FIXES_IMPLEMENTATION_PLAN.md` | **Implemented, 5 sub-items not** | 23-task UX plan. Verified implemented: inline cue editing + save-back, failure classification + `ErrorCard`, honest readiness rows, log counters, `revealCue`, light theme, accessibility names, hygiene tests. See §18.3 for the sub-items that never landed. |
| `UX_RESEARCH_REPORT.md` | **Superseded** | A 3 KB fragment (its §11 status section only) reporting the same 23 tasks complete. The plan file above carried the substance. |
| `FRONTEND_DESIGN.md` | **Superseded** | Design spec for the reworked GUI. The design landed; the code and §4.12 are now authoritative, and the doc's `AppBridge` contract listing had drifted. |
| — | — | (`README.md` was kept: it is the user-facing quick start.) |

Nothing was lost: every still-relevant fact from these documents is either already in
this file or recorded in §18.3 below. Copies are in
`docs/archive/root-md-2026-09-11/`.

### 18.2 Current verified state

- **593 tests pass** — verified 2026-09-11 with `python -m pytest -q` (108.8 s, 4
  non-blocking `QSortFilterProxyModel.invalidateFilter()` deprecation warnings from
  `backend/models/results.py:218`). The 14 packaged-exe tests run rather than skip when
  `dist/TranslationAgent/` exists.
- **Exactly three pipeline modes**: `youtube_cloud`, `local_cloud`, `offline`.
  Cloud rescue is **removed** — no `--cloud-rescue*` flag, no `CLOUD_RESCUE_*` env var,
  no `src/rescue.py`, no GUI control. The only surviving mention in the tree is a stale
  string in `ui/qml/archive/views/SettingsView.qml` (retired UI, not loaded).
- **Content presets** (`src/presets.py`): `auto`, `drama`, `anime`, `music`,
  `documentary`, `variety`, `lecture` — verified field-by-field against the plan table.
- **Context-first translation** (`src/translation_windows.py`): `off`/`light`/`standard`/`deep`;
  `standard` is the default for both backends, benchmark-verified.
- **`--asr-preset` and `--context-window` do not exist.** They were superseded by
  `--content-preset` and `--context-mode` respectively. Do not reintroduce them.
- **GUI**: Run / Review / Quality tabs + log drawer; inline-editable virtualized cue
  table with save-back and re-check; failure classification with remediation; light and
  dark themes; bundled Noto Sans JP.
- **Build**: `build_exe.bat` produces an **onedir** bundle at
  `dist/TranslationAgent/TranslationAgent.exe` (deliberately not onefile — see §7.1).

### 18.3 Open backlog (verified as *not* implemented)

Small UI items from `UX_FIXES_IMPLEMENTATION_PLAN.md` that were never built. None are
correctness issues; all are polish.

1. **S-07 stage timers** — `stageSequence`, `stageStartedAt`, `stageElapsedSec`,
   `estimatedRemainingSec` history. (`estimatedRemainingSec` exists as a property, but
   the ordered stage list and per-stage elapsed timer do not.)
2. **S-04 mode-aware language labels** — `languageControlLabel` / `languageControlHint`.
   The single header control exists; the label does not switch between
   "Source language" and "Spoken language" per mode.
3. **S-06 resolved-preset echo** — `resolvedPresetLabel` / `lastResolvedPreset`
   ("Auto → detected: anime") is not exposed.
4. **S-08 YouTube step strip** — `youtubeStep` ("1 Paste link → 2 Get subtitles →
   3 Translate") is not implemented. The collapsible video panel and the subtitle-panel
   data-flow sentence did land.
5. **S-11 expand chevron** for long cue lines in the Review table.

Longer-horizon items, all still deferred by design:

- Fuzzy translation memory (`--tm-fuzzy`).
- Bilingual ASS output (`--bilingual`) — blocked by the "target language is English"
  invariant.
- Automatic cue splitting — blocked by the "cue count in == cue count out" invariant.
- Timing enforcement beyond the documented overlap snap.
- Sound-tag modes (`--sound-tags strip|note|ass-comment`).
- Whisper reintroduction — explicitly forbidden.
- Runtime graceful degradation when `vendor/` binaries are missing (build-time only today).

### 18.4 Documentation conventions for the next pass

- Update **this file** for any developer/architecture/CLI/env change.
- Update **`README.md`** for anything user-visible.
- Do not create new root-level planning or review documents. If a plan is needed, put it
  in `docs/` and delete it when the work lands.
