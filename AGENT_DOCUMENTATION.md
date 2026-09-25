# Translation Agent — AI Agent Documentation

> **Audience:** AI agents, coding assistants, and automated refactoring tools.
> **Goal:** Provide complete, precise, actionable context so an agent can understand, modify, test, and extend this codebase without guessing.
> **Last updated:** 2026-09-25 — the UI redesign (`IMPLEMENTATION_PLAN.md` / `tasks.md`, Phases 0–6) is complete: one store with binding-safe editors (§4.25), autosave instead of a Save button, a five-fact status vocabulary, real Settings category gating, a two-axis Run screen, and a Log history whose rows open. The suite is **1096 tests** (§18.2).
>
> **Canonical source of truth:** This file is the consolidated developer/AI reference. It supersedes the
> now-archived `PROJECT.md`, `CLAUDE.md`, `TASKS.md`, and `updated implementation plan.md` (their content has
> been folded in below). `README.md` is the user-facing quick start and is kept in sync with this file.
>
> **2026-09-25 UI-redesign pass:** every claim below was re-verified against the working tree. What changed
> relative to the 2026-09-16 revision: the QML layer was rebuilt around a single store and binding-safe
> editors (§4.24, §4.25); `ModePicker` / `PresetPicker` were deleted and the Run screen now exposes two
> independent axes (§4.24); `SettingsPage` moved from a one-blob scroll to seven gated categories; the
> command palette gained Navigate / Actions / Toggles / Jump-to-setting namespaces; the Log screen's run
> history now loads a run into Review/Quality. The test suite went from 682 to **1096** collected tests.
>
> **2026-09-16 alignment pass (historical):** the QML frontend was rewritten (§4.24 —
> `DashboardView`/`SettingsView` are gone, replaced by a five-page shell); `backend/bridge.py` grew a
> structured failure classifier, a three-valued model-state layer and a YouTube inspect/download panel
> (§4.19); `src/gguf_check.py` was added (§4.18); the CLI gained `--download-video` / `--download-subtitle`
> / `--translation-memory-db`. Newly documented defects are listed in §9.
>
> **2026-09-11 root cleanup (historical):** ten planning/review documents that had accumulated in the
> project root were verified against the code, folded in where still relevant, and removed. The two
> documents that remain at the root are this file and `README.md`. See §18 for the classification.

---

## 1. Project Identity

**Internal name:** Translation Agent
**User-facing name:** YouTube Subtitle Translator
**Platform:** Windows-first (no macOS/Linux support currently guaranteed)
**Language:** Python 3.12, PySide6 (QML), batch/shell
**Purpose:** Produce English SRT/ASS subtitles from either (a) a YouTube URL's subtitles or (b) a local media file's audio, using LLM translation or a fully local ASR + translation stack.

---

## 2. Repository Layout (Canonical)

```
translation-agent/
├── AGENT_DOCUMENTATION.md      # ← this file (consolidated developer/AI reference + project state)
├── README.md                   # User-facing quick start
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
├── pytest.ini                  # testpaths = tests, pythonpath = .
├── .gitignore                  # ignores dist/, build/, *.spec, *.gguf, models/, ui_shots/, debug.log, .env
├── .env.example                # Credential template
├── .env                        # Actual secrets (git-ignored)
│
├── src/                        # Framework-free CLI pipeline (19 modules)
│   ├── __init__.py
│   ├── config.py               # .env loading + OpenAI client construction
│   ├── fetch_subs.py           # YouTube subtitle fetching + English title resolution
│   ├── ytdlp.py                # yt-dlp resolution + subprocess/in-process runner
│   ├── youtube_media.py        # Video inspect, codec×resolution matrix, download, ffmpeg merge
│   ├── srt_io.py               # Cue dataclass + SRT read/write + filename sanitize
│   ├── translate.py            # LLM translation (context windows, numbered-item protocol) + validation
│   ├── batching.py             # Character-aware batch splitting for small CPU models
│   ├── presets.py              # Content presets + central settings resolver
│   ├── translation_windows.py  # Context-first TranslationWindow engine (before/after context)
│   ├── glossary.py             # Source→target glossary parse + prompt injection
│   ├── translation_memory.py   # SQLite exact-match translation cache
│   ├── subtitle_quality.py     # CPS / duration / char / line / leakage / residue diagnostics
│   ├── local_asr.py            # FunASR + SenseVoiceSmall CPU transcription (+ FFmpeg preprocessing)
│   ├── local_server.py         # Auto-start bundled CPU llama-server
│   ├── gguf_check.py           # GGUF header/integrity validation (detects truncated downloads)
│   ├── postprocess.py          # Fansub post-processing (line break / overlap snap / TN)
│   ├── cjk.py                  # CJK script detection + kinsoku line breaking
│   └── ass_io.py               # Aegisub-compatible ASS writer
│
├── backend/                    # GUI bridge (QObject + QRunnable workers)
│   ├── __init__.py             # Lazy re-exports: AppBridge, TranslationWorker, WorkerSignals,
│   │                           #   RunConfig, _base_dir, setup_logging
│   ├── bridge.py               # AppBridge: QML ↔ Python state + pipeline runner (~4.2k lines)
│   ├── controllers/
│   │   ├── __init__.py
│   │   └── translation.py      # TranslationWorker + _SignalWriter + WorkerSignals
│   └── models/
│       ├── __init__.py
│       ├── run_config.py       # RunConfig dataclass (argv + env)
│       └── results.py          # CueResultModel / CueFilterProxyModel / QualityIssuesModel
│
├── ui/qml/                     # Qt Quick declarative frontend
│   ├── Main.qml                # ApplicationWindow shell: CommandBar + IconRail + StackLayout + StatusBar
│   ├── Theme.qml               # Design tokens (singleton): colours, spacing, radii, type, geometry
│   ├── qmldir                  # `singleton Theme 1.0 Theme.qml`
│   ├── pages/                  # One file per screen (no qmldir; loaded via directory import)
│   │   ├── RunPage.qml         # Source → Pipeline → Inspector (3 columns)
│   │   ├── ReviewPage.qml      # Cue table + timeline + cue inspector + find & replace
│   │   ├── QualityPage.qml     # Score ring, stat tiles, issue list, histograms, gate, exports
│   │   ├── LogPage.qml         # Run history + full-height console with tone filters
│   │   └── SettingsPage.qml    # 8-section settings surface with search
│   ├── components/             # 34 components, all registered in components/qmldir
│   │   ├── qmldir
│   │   ├── AppButton, AppCard, AppCheckBox*, AppSwitch, Chip, Pill, Icon, KeyValue,
│   │   │   FieldLabel, SettingsRow, StatTile, SegmentedControl, FilterChip
│   │   ├── CommandBar.qml      # 56 px top bar; per-page controls, Run, status pill
│   │   ├── IconRail.qml        # 64 px left navigation rail (Run/Review/Quality/Log/Settings)
│   │   ├── StatusBar.qml       # 30 px bottom bar: state dot, log ticker, shortcut hints
│   │   ├── CommandPalette.qml  # Ctrl K overlay (23 commands)
│   │   ├── ModePicker.qml      # YouTube Cloud / Local Cloud / Offline segmented control
│   │   ├── PresetPicker.qml    # Content preset combo
│   │   ├── RunButton.qml       # Run / Download-model-&-Run / Repair-model-&-Run / Cancel
│   │   ├── StatusPill.qml, ProgressPanel.qml, ProgressRing.qml, ReadinessChecklist.qml
│   │   ├── ConsoleView.qml     # Shared log console (parses logText, tone filters)
│   │   ├── CuePreviewTable.qml # Virtualized cue table (QAbstractListModel-backed, inline edit)
│   │   ├── CueInspector.qml    # Master–detail single-cue editor with ±50 ms nudges
│   │   ├── Timeline.qml, Histogram.qml, ErrorCard.qml
│   │   ├── YouTubeVideoPanel.qml, YouTubeSubtitlePanel.qml
│   │   └── CompactTextField, CompactComboBox, AppButton, AppCard, …
│   │                           # * AppCheckBox.qml is registered but never instantiated — see §9
│   └── archive/                # Retired pre-rework UI — NOT loaded at runtime (dead code)
│
├── assets/fonts/               # Optional bundled CJK font (NotoSansJP-Regular.ttf) + README.txt (SIL OFL)
│                               #   NOTE: main.py loads these, but build_exe.bat does not bundle them — §9
│
├── vendor/                     # Bundled binaries (untracked, not git-ignored)
│   ├── funasr/                 # llama-funasr-sensevoice.exe, llama-funasr-vad.exe + DLLs
│   └── llama/                  # llama-server.exe + DLLs
│
├── gguf/                       # Downloaded GGUF models (SenseVoiceSmall, VAD, Hy-MT2)
│
├── tools/
│   ├── benchmark.py            # Offline benchmark harness
│   ├── benchmark_preprocess.py # ASR preprocessing profile benchmark (cue counts, CER/WER)
│   ├── compare_context_modes.py# Context-mode A/B harness (alignment failures, reference similarity)
│   ├── check_srt.py            # SRT diagnostic (cue count, avg/max duration)
│   ├── screenshot_ui.py        # Offscreen UI screenshot helper (STALE — see §9)
│   └── stamp_spec_header.py    # Applies the "GENERATED FILE" banner to TranslationAgent.spec
│
├── tests/                      # pytest suite (41 test modules; 1096 tests collected)
│   ├── conftest.py, gguf_fixtures.py
│   ├── test_srt_io.py, test_translate_parsing.py, test_translate_validation.py
│   ├── test_batching.py, test_glossary.py, test_translation_memory.py
│   ├── test_subtitle_quality.py, test_quality_extended.py, test_local_asr_splitting.py
│   ├── test_local_server.py, test_fetch_subs.py, test_fansub_upgrade.py, test_cjk.py
│   ├── test_cli_flags.py, test_presets.py, test_context_windows.py, test_result_json.py
│   ├── test_pipeline_modes.py, test_asr_preprocess.py, test_followup_fixes.py
│   ├── test_gguf_integrity.py, test_model_integrity.py
│   ├── test_youtube_media.py, test_youtube_format_selection.py, test_ytdlp.py
│   ├── test_build_contract.py, test_packaged_exe_smoke.py
│   └── test_ui_models.py, test_ux_bridge.py, test_ui_hygiene.py, test_qml_smoke.py
│
├── benchmark/
│   ├── README.md               # How to add test media
│   ├── cases.json              # Benchmark case definitions
│   ├── cues/, ref/             # Cue dumps and reference SRTs
│   └── *.srt
│
├── docs/
│   ├── PREPROCESS_BENCHMARK.md # Preprocessing profile methodology + results
│   └── archive/                # Archived docs: CLAUDE.md, IMPLEMENTATION_PLAN.md, PROJECT.md,
│                               #   TASKS.md, root-md-2026-09-11/, root-scratch-2026-09-11/
│
├── mockups/                    # Static HTML design proposal for the UI rework (tracked, 15 files)
│   ├── README.md               # Design tokens, shell zones, constraints, build order
│   ├── index.html, design-system.html
│   ├── assets/ (mock.css, icons.js, app.js)
│   └── screens/ (01-run-youtube … 09-empty)
│
├── ui_shots/                   # Offscreen UI screenshots (git-ignored, produced by screenshot_ui.py)
├── cache/                      # Runtime cache: translation_memory.sqlite3, last_result.json, bench data
│
├── _e2e_download.py            # Root scratch probe: real codec/resolution download verification
├── _probe_youtube.py           # Root scratch probe: live YouTube inspection + selector replay
├── _shot_youtube.py            # Root scratch probe: offscreen YouTube panel screenshots
├── _shot_youtube_real.py       # Root scratch probe: same, against the live API
├── _verify_offline_flow.py     # Root scratch probe: drive the offline flow through real QML
├── _verify_ui_message.py       # Root scratch probe: assert the QML shows the right message
│
├── build/                      # PyInstaller intermediate build artifacts
├── dist/                       # PyInstaller output (dist/TranslationAgent/TranslationAgent.exe)
├── debug.log                   # Rotating runtime log (GUI mode; git-ignored)
├── .claude/ .cline/ .openclaude/ .uploads/ .workbuddy-ai/   # Local tooling state, not shipped
└── __pycache__/                # Python bytecache
```

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

`AppBridge._apply_pipeline_mode()` maps the mode id onto the internal
`(mode, backend)` pair used by `_build_run_config()`:

| `pipelineMode` | `_mode` | `_backend` |
|---|---|---|
| `youtube_cloud` | `youtube` | `cloud` |
| `local_cloud` | `file` | `cloud` |
| `offline` | `file` | `local` |

### 3.2 CLI Pipeline (both input paths)

```
translate.py::main(argv)
  ├─ reset_cancel()                     # a stale GUI cancel must not leak into this run
  ├─ _parse_args(argv)
  ├─ src.presets.resolve_effective_settings(args)
  │    └─ explicit CLI > named preset > env var > built-in default
  ├─ if --file:
  │   └─ src.local_asr.transcribe_local_file(...) -> (cues, source_language)
  │       └─ optional --source-lang hint applied only when ASR lang is auto/unknown
  ├─ else (YouTube URL):
  │   └─ src.fetch_subs.fetch_original_subtitles(url, preferred_lang=--source-lang)
  │       ├─ extract_video_id(url)
  │       ├─ _yt_dlp_metadata(url)          → (title, lang) via src.ytdlp.run_ytdlp_capture
  │       ├─ _fetch_english_title(video_id) → Innertube player API (hl=en)
  │       ├─ --source-lang given? → _resolve_language_transcript (forced; no wrong-language fallback)
  │       └─ else → _resolve_transcript / _resolve_english_transcript (English-first)
  │   └─ if --download-video or --download-subtitle: _download_youtube_media(args)
  ├─ if --local:
  │   ├─ src.local_server.ensure_local_server(...) -> (proc, how, port)
  │   ├─ _check_local_ready(base_url)       # GET /models, 10 s
  │   ├─ src.local_server.warmup_local_server(base_url, model_name)
  │   └─ os.environ["OPENAI_BASE_URL"] = base_url   (restored in `finally`)
  └─ _run_pipeline(args, settings, fetched)
      ├─ _json_progress("fetch", 0, N)
      ├─ script-ratio CJK detection when the language is missing/auto/unknown
      ├─ src.glossary.load_glossary / format_glossary
      ├─ src.translation_memory.TranslationMemory  (auto = on for Hy-MT2 only)
      ├─ English source? → pass text through, no LLM call
      │  else → src.translate.translate_cues(..., cancel_check=_poll_cancel)
      │      └─ builds TranslationWindows (src/translation_windows.py) with read-only
      │         before/after context; numbered-item protocol; retry→split→per-item ladder
      ├─ final sanitizer: strip SenseVoice tags / `[CHENGYU:]` markup, keep `[untranslated]`
      ├─ report failed cues loudly, then src.postprocess.apply_all(cues)
      ├─ resolve output path/format, src.ass_io.write_ass or src.srt_io.write_srt
      ├─ src.subtitle_quality.build_report → optional --quality-report / --result-json
      ├─ --strict-quality → exit 1 on any error or untranslated cue
      └─ print(f"Wrote {N} cues to {path}")     # MUST be the final line (GUI regex)
```

### 3.3 Numbered-Item Translation Protocol

This is the **single most important invariant** in the codebase.

1. Cue texts are joined as `1. text1\n2. text2\n...` (`_numbered_block`) and sent as one user message.
2. The LLM is instructed to respond with the same numbers.
3. `_parse_numbered(response, expected)` maps lines back to exactly `expected` strings; duplicate numbers are rejected.
4. On misalignment a window is retried with a stricter instruction, split in half recursively (`MAX_SPLIT_DEPTH = 8`), and finally translated per item (`_per_item_translate`).
5. If a backend rejects llama.cpp-only params (`top_k`, `repeat_penalty`), they are dropped and the batch retried plainly.

**Why this matters:** cue count in == cue count out. The SRT indices (1, 2, 3, …) are
written sequentially; any mismatch between translated list length and cue list length
causes misalignment.

### 3.4 Foreignization Directive

The system prompt for cloud translation is built from `_FOREIGNIZATION_DIRECTIVE` (in
`src/translate.py`). It is a long, carefully crafted instruction set covering:

- Absolute ideological/political neutrality
- Ban on modern slang and anachronisms
- Register, hierarchy, honorifics preservation
- Cultural specifics and idioms
- Puns and wordplay handling
- `[Translator's Note]` convention for untranslatable elements

**AI agents must preserve this directive intact.** If editing translation logic, keep
`_FOREIGNIZATION_DIRECTIVE` and `build_system_prompt()` behaviour unchanged unless
explicitly asked to modify translation philosophy.

### 3.5 Hy-MT2 Local Model Path

When the model name matches `_is_hy_mt2(model)` (contains `hy-mt2` or `hy_mt2`), the
translator **replaces** the cloud prompt recipe with the Hy-MT2 translator skill's approach:

- **No system prompt** is sent.
- Temperature = `0.1` (very low, so the numbered-item protocol parses deterministically).
- `extra_body` carries `top_p=0.6`, `top_k=20`, `repeat_penalty=1.05`.
- The user message uses the skill's Chinese instruction wording plus `_HY_MT2_STYLE`
  (a Chinese foreignization directive); `HY_MT2_TARGET_LANG = "英语"`.
- The skill's "context" mode is used when the source language is known; "basic" otherwise.
- The numbered-item protocol is still enforced.
- **Window budgets:** `max_window_cues = min(batch_size, 8)`; chars = 700 (CJK) / 1000 (non-CJK).
- **Preferred model file:** `./gguf/Hy-MT2-1.8B-Q8_0.gguf`. See `resolve_local_model_path` in `backend/bridge.py`.

Chengyu flagging applies only for Chinese sources and **never** for Hy-MT2.

### 3.6 Cancellation Contract

The GUI calls `translate.main()` **in-process**, so a "Stop" click cannot kill a
subprocess. Cancellation is therefore cooperative and module-global:

- `translate.request_cancel()` sets `_cancel_requested = True`.
- `translate.reset_cancel()` clears it; `main()` calls this first thing, so a cancel
  cannot leak into the next run.
- The flag is passed into `translate_cues(..., cancel_check=translate._poll_cancel)`.
- On cancel, `translate_cues` raises `TranslationCancelled`; `_run_pipeline` prints a
  notice and returns **2**, and no output file is written.
- `TranslationWorker.run()` catches `TranslationCancelled` and also returns 2; the bridge
  distinguishes a real cancel from a configuration error by checking
  `getattr(translate, "_cancel_requested", False)`.

---

## 4. Module Reference

### 4.1 `src/config.py`

**Responsibility:** Load `.env`, validate settings, construct the OpenAI client.

**Key types / functions:**
- `Settings` (dataclass): `api_key`, `base_url`, `model`
- `load_settings(override_model=None) -> Settings`
  - Reads `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`; calls `load_dotenv()` at import.
  - If `api_key` is missing and `base_url` points to a local host (`localhost`, `127.0.0.1`, `::1`, `0.0.0.0`, `*.localhost`), substitutes `"sk-local"`.
  - Raises `RuntimeError` with actionable messages on missing values.
- `make_client(settings) -> OpenAI`
  - Adds OpenRouter attribution headers (`HTTP-Referer`, `X-Title`) when `base_url` contains `"openrouter"`.

**Constants:** `ENV_API_KEY` / `ENV_BASE_URL` / `ENV_MODEL`, `_LOCAL_HOSTS`.

| Variable | Required | Default | Meaning |
|----------|----------|---------|---------|
| `OPENAI_API_KEY` | Yes (remote) | `""` | API key |
| `OPENAI_BASE_URL` | No | `""` → `None` | Override endpoint |
| `OPENAI_MODEL` | Yes | `""` | Model id |

### 4.2 `src/srt_io.py`

**Responsibility:** Core data class and SRT serialization/deserialization.

**Key types / functions:**
- `Cue` (dataclass, slots): `start: float` (seconds), `end: float` (seconds), `text: str`
- `sanitize_filename(title) -> str` — strips `< > : " / \ | ? *` and control chars, collapses whitespace/dots, max 180 chars, falls back to `"subtitles"`.
- `output_path_for(input_path_or_title, ext=".srt") -> str`
- `write_srt(cues, path) -> None` — standard SRT, 1-based indices, `HH:MM:SS,mmm`.
- `read_srt(path) -> list[Cue]` — tolerant parser (BOM, blank lines, multi-line text).
- `_format_timestamp(seconds)`, `_parse_timestamp(ts)`
- `_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')`

### 4.3 `src/fetch_subs.py`

**Responsibility:** Extract the YouTube video ID, get subtitles, resolve the English title for the filename.

**Key types / functions:**
- `extract_video_id(url) -> str` — patterns for `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/shorts/`, `youtube.com/embed/`; returns the 11-char id; raises `ValueError`.
- `fetch_original_subtitles(url, preferred_lang=None) -> tuple[list[Cue], str | None, str | None]`
  - Returns `(cues, english_video_title, source_language_code)`.
- Helpers: `_yt_dlp_metadata`, `_fetch_english_title`, `_resolve_transcript`, `_resolve_language_transcript`, `_resolve_english_transcript`, `_snippets_to_cues`.
- Re-exports from `.ytdlp`: `YtdlpError`, `_SUBPROCESS_CREATION_FLAGS`, `run_ytdlp_capture`, `yt_dlp_cmd as _yt_dlp_cmd`.

**External dependencies:**
- `yt-dlp` — invoked through `src/ytdlp.run_ytdlp_capture()` (subprocess normally, in-process when frozen).
- `youtube-transcript-api` — `YouTubeTranscriptApi.list(video_id)`; manual track first, then generated, then first available.
- Innertube player API — `POST https://www.youtube.com/youtubei/v1/player?key=<_INNERTUBE_KEY>` (public web-client key), payload `clientName="WEB"`, `clientVersion="2.20240101"`, `hl="en"`, `gl="US"`; used **only** to fetch the English-localized title, falling back to the yt-dlp title on any failure.

**English language codes:** `["en", "en-US", "en-GB", "en-CA", "en-AU"]`.

### 4.4 `src/ytdlp.py` — how yt-dlp is invoked

**Responsibility:** Locate yt-dlp and run it, both from source and from the packaged executable.

**Two execution modes** (chosen by `use_inprocess()`):

| Mode | When | How |
| --- | --- | --- |
| Subprocess | normal installs | `yt-dlp` on PATH (or `YT_DLP_BIN`), else `python -m yt_dlp`; stdout streamed, `Popen` exposed for cancellation |
| In-process | `sys.frozen` (no `YT_DLP_BIN`) | `yt_dlp.main(argv)` runs in this thread with `sys.stdout`/`sys.stderr` swapped for a line sink |

**Why the in-process mode exists:** a one-file PyInstaller build has no Python
interpreter to spawn — `sys.executable` *is* the app — and an end user cannot be assumed
to have `yt-dlp.exe` installed. `yt_dlp.main()` is called with the same CLI arguments
(minus the launcher prefix, stripped by `_strip_launcher()`), so the output is identical
to the subprocess version and every existing `[download]` / `[info]` / `Destination:`
parser keeps working. It also fixes `--windowed` builds, where `sys.stdout` is `None`.

**Key functions:**
- `is_frozen() -> bool`
- `yt_dlp_cmd() -> list[str]` — subprocess prefix (`YT_DLP_BIN` → PATH → `python -m yt_dlp`).
- `use_inprocess() -> bool`
- `yt_dlp_available() -> bool` — accounts for the bundled copy (the old `shutil.which("yt-dlp")` guard was wrong for frozen builds).
- `run_ytdlp(cmd, on_line=None, cancel_check=None, proc_ref=None, env=None) -> int` — streaming; `on_line(line)` may return `False` to abort.
- `run_ytdlp_capture(cmd, timeout=None, env=None) -> str` — one-shot `--dump-json` / `--print` queries.

**Errors:** `YtdlpError` (base, `.output` carries yt-dlp's own message), `YtdlpUnavailable`, `YtdlpTimeout`, `YtdlpFailed`. Escape hatch: `YT_DLP_INPROC=1` forces the in-process path, which is how the tests exercise it. `_INPROC_LOCK` serializes in-process calls.

**Related:** `src/youtube_media._ffmpeg_exe()` also looks in `sys._MEIPASS` / next to the `.exe` for a bundled `ffmpeg*.exe`, because `shutil.which()` cannot see binaries PyInstaller unpacked there.

> **ffmpeg must be named `ffmpeg.exe` for the merge to run.** yt-dlp's
> `--ffmpeg-location <dir>` only recognises a binary literally called `ffmpeg` /
> `ffmpeg.exe`; a packaged binary such as `ffmpeg-win-x86_64-v7.1.exe` is *never* found,
> so the video+audio merge silently never runs and the user gets two separate files.
> `_ffmpeg_exe()` therefore returns a `ffmpeg.exe` — copying the discovered binary to a
> `ffmpeg.exe` sidecar (in the bundle dir if writable, else a temp dir) when the real name
> differs — and `_run_yt_dlp` passes that file's directory to `--ffmpeg-location`.
> `build_exe.bat` bundles the binary under its real name because PyInstaller's
> `--add-binary` treats the destination as a *directory* and cannot rename at build time.
> Regression tests live in `tests/test_ytdlp.py` (`TestFfmpegMerge`, `TestFrozenFfmpegLookup`).

### 4.5 `src/youtube_media.py`

**Responsibility:** Inspect a YouTube video, build a codec × resolution selection matrix, then download the chosen video (with merge) or an English subtitle track.

**Public API:**
- `inspect_video(url) -> dict` — `yt-dlp --dump-json` → matrix of `(codec, height)` → `{format_selector, filesize, ext, fps, label, has_audio, merge}`, plus available codecs/resolutions, per-codec availability flags and `has_english_subtitle`.
- `resolve_video_option(info, codec, resolution) -> dict | None`
- `describe_unavailable(info, codec, resolution) -> str` — actionable "what this video does serve" message.
- `download_video(url, format_selector, out_template, progress_cb=None, percent_cb=None, proc_ref=None, cancel_check=None) -> str`
- `download_subtitle(url, lang="en", out_template_base="", progress_cb=None, proc_ref=None, cancel_check=None) -> str`
- `probe_video_file(path) -> dict | None`
- `normalize_resolution(value) -> str`

**Format-selection rules (`--download-video best|av1|vp9|h264`):**

| Codec | Resolution | Behaviour |
|---|---|---|
| `best` | `best` | unconstrained `bv*+ba/b` |
| `best` | height | any codec capped at that height; `None` if nothing is at/below it |
| specific | `best` | highest height that codec serves |
| specific | height | **exact match or refuse** — never a closest-height substitution |

Unknown codec → `None`. Combined single-file formats use the real `format_id`
(`merge: False`); video-only formats use `<format_id>+bestaudio/<audio-safe fallback>`
(`merge: True`). The audio-safe fallback never ends on a video-only stream, which avoids
silently muted output.

**Resilience:** `_RESILIENCE_FLAGS` (retries, fragment retries, extractor retries,
exponential retry-sleep, `--sleep-requests 0.75`), `--throttled-rate 50K`,
`--concurrent-fragments 4`, and one clean-slate retry after a stale-part 403
(`_STALE_PART_AGE = 900 s`, `_MAX_DOWNLOAD_ATTEMPTS = 2`).

**Errors:** `_translate_ytdlp_error` produces specific messages for sign-in/age-gate,
expired-URL 403, `po_token`/`yt-dlp-ejs`, outdated extractor, unavailable/private video,
and invalid URL. `download_subtitle` raises `RuntimeError("No English subtitle …")`.

**Env:** `FFMPEG_BIN` (candidate for `_ffmpeg_exe()`).

### 4.6 `src/translate.py`

**Responsibility:** Context-window translation of cues via an OpenAI-compatible chat completion API.

**Public entry points:**

```python
def build_system_prompt(source_language, target_language="English", *, glossary=None,
                        chengyu=False, classical=False, emotion=False, addendum=None) -> str

def translate_cues(cues, client, model, batch_size=8, max_retries=3, source_language=None, *,
                   glossary=None, translation_memory=None, context_mode=None,
                   prompt_profile=None, progress_callback=None,
                   scene_summary_enabled=False, cancel_check=None) -> list[str]

def build_hy_mt2_user_prompt(texts, source_language, glossary=None) -> str
```

- `build_system_prompt` fills `_FOREIGNIZATION_DIRECTIVE` placeholders, then appends (in order) the chengyu note, the Classical-Chinese note, the emotion note, the content-preset `addendum`, and the glossary. The addendum is appended, never substituted.
- `translate_cues` is the **canonical entry point** used by both CLI and GUI. It splits cues into context-aware `TranslationWindow`s, attaches read-only before/after context plus a rolling memory of recent translated pairs, and calls `_translate_group` per window.
  - `context_mode`: `off`/`light`/`standard`/`deep`; `None` resolves via `translation_windows.resolve_context_mode` to `standard`.
  - `prompt_profile`: selects a scoped content addendum via `src.presets.get_prompt_addendum`.
  - `progress_callback(done, total, stage)`: invoked after each window finalizes (drives GUI JSON progress).
  - `scene_summary_enabled`: cloud-only rolling scene summary.
  - TM interaction: a window whose cues are **all** exact TM hits is served from TM (no LLM); a partially-hit window goes to the LLM whole and TM entries are overwritten with the fresh in-context translations.
  - On misalignment: stricter retry → recursive split (`MAX_SPLIT_DEPTH = 8`) → per-item. Cue count is exact at every stage.

**Internal helpers:**
- `_is_hy_mt2(model) -> bool`
- `_numbered_block(texts) -> str` — joins as `1. text\n2. text\n…`
- `_parse_numbered(response, expected) -> list[str] | None`
- `_translate_batch(client, model, texts, system_prompt, attempt=0, temperature=0.3, user_content=None, extra_body=None, metrics=None) -> list[str] | None`
- `_translate_one(...) -> str` — never falls back to the source text
- `_translate_group(...)` — the window-level orchestrator with the fallback ladder
- `_translate_one_checked(...)` — retries at `min(temp + 0.2, 0.7)` and drops `extra_body`; returns `""` on failure
- `_per_item_translate(...) -> list[str]`
- `_maybe_update_scene_summary(client, model, summary, recent_sources, metrics=None) -> str` — best-effort, never raises, never alters numbering; refreshes every 15 windows; output capped at 600 chars
- `looks_untranslated(source_text, translation, source_language) -> bool` — true on empty, whitespace-folded source echo, any Hangul, CJK ratio ≥ 0.5, or a short (≤ 24 non-space chars) reply still containing CJK
- `_flag_chengyu`, `_strip_sensevoice_tag`, `_is_classical_chinese`, `_detect_cjk_lang`, `_cjk_count`
- `_endpoint_fatal_message(exc)`, `_raise_if_fatal(exc)` — abort instead of retrying forever when the endpoint is not an OpenAI-compatible chat API (`_FATAL_HTTP_STATUS = {404, 405, 501}`)

**Classes:** `TranslationEndpointError(RuntimeError)`, `TranslationCancelled(RuntimeError)`, `_PerfMetrics`.

**Constants:**

| Constant | Value | Usage |
|----------|-------|-------|
| `HY_MT2_TEMPERATURE` | `0.1` | Hy-MT2 local model |
| `HY_MT2_TOP_P` | `0.6` | Hy-MT2 via `extra_body` |
| `HY_MT2_TOP_K` | `20` | Hy-MT2 via `extra_body` |
| `HY_MT2_REPETITION_PENALTY` | `1.05` | Hy-MT2 via `extra_body` |
| `HY_MT2_TARGET_LANG` | `"英语"` | Hy-MT2 prompt target |
| cloud temperature | `0.3` | fidelity-first; `extra_body=None` |
| `MAX_SPLIT_DEPTH` | `8` | recursion cap in the fallback ladder |

> **Dead env vars — see §9.** `HY_MT2_MAX_BATCH_CUES`, `HY_MT2_MAX_BATCH_CHARS_CJK` and
> `HY_MT2_MAX_BATCH_CHARS_NON_CJK` are still read into module constants
> (`HY_MT2_DEFAULT_MAX_BATCH_CUES`, `HY_MT2_MAX_BATCH_CHARS_CJK`,
> `HY_MT2_MAX_BATCH_CHARS_NON_CJK`) but **nothing reads those constants**. The real
> budgets come from `translation_windows.HY_MT2_MAX_WINDOW_CUES` / `HY_MT2_MAX_CHARS_CJK`
> / `HY_MT2_MAX_CHARS_NON_CJK`. Setting those env vars has no effect today.

### 4.7 `src/batching.py`

**Responsibility:** Split lists of cue texts into model-safe request batches, respecting cue-count and character limits (CJK-aware).

- `is_cjk_language(source_language) -> bool` — normalized, region-stripped; covers zh/zho/chi/chs/cht/chinese, ja/jpn/japanese, ko/kor/korean, yue/cantonese.
- `estimate_text_weight(text, source_language) -> int` — non-whitespace character count (the CJK distinction applies at the *batch budget* level, not per character).
- `chunk_texts(texts, *, max_items, max_total_chars, source_language=None) -> list[list[int]]` — returns batches of original indices, order preserved, never drops; raises `ValueError` on non-positive limits.

### 4.8 `src/translation_windows.py`

**Responsibility:** The context-first engine — the primary translation unit.

- `CONTEXT_PROFILES: dict[str, tuple[int, int, int]]` = before-pairs / after-cues / memory-pairs
  - `off: (0, 0, 0)`, `light: (1, 1, 4)`, `standard: (2, 2, 8)`, `deep: (4, 3, 12)`
- `TranslationWindow` (dataclass): `start_index`, `cues`, `before_context: list[tuple[str, str]]`, `after_context: list[str]`
- `resolve_context_mode(mode, *, local) -> str` — unknown/`None` → `"standard"`
- `build_windows(cues, *, max_window_cues=DEFAULT_MAX_WINDOW_CUES, max_window_duration_ms=DEFAULT_MAX_WINDOW_DURATION_MS, scene_gap_ms=DEFAULT_SCENE_GAP_MS, max_current_chars=8000) -> list[TranslationWindow]`
- `build_cloud_user_content(texts, *, before_context=None, after_context=None, summary=None, strict_note=None) -> str`
- `build_hy_mt2_context_user_content(texts, *, source_language, glossary=None, before_context=None, after_context=None) -> str`

**Constants:** `DEFAULT_MAX_WINDOW_CUES = 12`, `DEFAULT_MAX_WINDOW_DURATION_MS = 30000`,
`DEFAULT_SCENE_GAP_MS = 800`, `HY_MT2_MAX_WINDOW_CUES = 8`, `HY_MT2_MAX_CHARS_CJK = 700`,
`HY_MT2_MAX_CHARS_NON_CJK = 1000`.

### 4.9 `src/presets.py`

**Responsibility:** Content presets and the single central settings resolver.

- `ContentPreset` (frozen dataclass): `name`, `description`, `asr_preprocess`, `asr_max_segment_ms`, `asr_max_end_silence_ms`, `asr_speech_noise_threshold`, `asr_noise_db`, `asr_min_silence_s`, `asr_max_cue_duration_ms`, `asr_max_cue_chars`, `asr_max_cue_chars_cjk`, `context_mode`, `prompt_profile`, `max_line_chars`, `max_cps`
- `PRESETS: dict[str, ContentPreset]`, `PROMPT_ADDENDA: dict[str, str]`, `get_prompt_addendum(profile)`, `resolve_effective_settings(args)`

**Resolved preset table:**

| Preset | preprocess | segment ms | end-silence ms | speech thres | cue dur ms | cue chars CJK | context | prompt |
|---|---|---|---|---|---|---|---|---|
| `auto` | `basic` | 6000 | 250 | 0.55 | 3200 | 48 | *(→ standard)* | `general` |
| `drama` | `loudnorm` | 5000 | 230 | 0.55 | 4200 | 30 | `standard` | `drama` |
| `anime` | `basic` | 4000 | 200 | 0.62 | 3800 | 26 | `standard` | `anime` |
| `music` | `basic` | 6000 | 300 | 0.65 | 5000 | 28 | `light` | `music` |
| `documentary` | `loudnorm` | 5500 | 260 | 0.52 | 4800 | 34 | `deep` | `documentary` |
| `variety` | `loudnorm` | 4200 | 220 | 0.60 | 3600 | 26 | `standard` | `variety` |
| `lecture` | `loudnorm` | 6000 | 300 | 0.52 | 5200 | 36 | `deep` | `lecture` |

All presets share `asr_noise_db = -35.0`, `asr_min_silence_s = 0.25`,
`asr_max_cue_chars = 70`, `max_line_chars = 40`, `max_cps = 18.0`.
`PROMPT_ADDENDA` has keys `drama`, `anime`, `music`, `documentary`, `variety`, `lecture`
— there is deliberately **no** `general` addendum.

**Precedence enforced by `resolve_effective_settings(args)`:**
1. An explicit CLI/GUI value (attribute is not `None`) always wins and is left untouched.
2. Otherwise, if the preset is **not** `auto`, the **named preset value** wins over the environment (deliberate product choice).
3. In `auto` only, the environment variable wins over the `auto` baseline; if unset, the `auto` value is used.

Values are coerced to `int`/`float` to match the target field. Unknown preset names raise `ValueError`.

**Controlled env vars** (`_CONTROLLED`, read with no default):
`FUNASR_PREPROCESS`, `FUNASR_MAX_SEGMENT_MS`, `FUNASR_MAX_END_SILENCE_MS`,
`FUNASR_SPEECH_NOISE_THRES`, `FUNASR_NOISE_DB`, `FUNASR_MIN_SILENCE_S`,
`FUNASR_MAX_CUE_DURATION_MS`, `FUNASR_MAX_CUE_CHARS`, `FUNASR_MAX_CUE_CHARS_CJK`,
`TRANSLATION_CONTEXT_MODE`, `TRANSLATION_PROMPT_PROFILE`.

### 4.10 `src/glossary.py`

**Responsibility:** Parse an optional `source→target` glossary file and format it into the prompt.

- `load_glossary(path) -> list[tuple[str, str]]` — plain text, `source<TAB>target`, `source = target`, or `source -> target`; `#` comments; dedupes and truncates.
- `format_glossary(entries) -> str` — bullet list for the prompt (capped length).
- `glossary_hash(entries) -> str` — SHA-256 of the formatted glossary (part of the TM key).

**Constants:** `MAX_GLOSSARY_ENTRIES = 80`, `MAX_GLOSSARY_CHARS = 2000`,
`_SEPARATORS = ("\t", "->", " = ", "=")`. **Env:** `TRANSLATION_GLOSSARY` (via the CLI flag default).

### 4.11 `src/translation_memory.py`

**Responsibility:** SQLite-backed exact-match cache of previously translated source lines.

- `make_key(*, source_language, source_text, model_profile, glossary_hash) -> str` — SHA-256 of `lang|model_profile|glossary_hash|normalized_source`
- `TranslationMemory(db_path=...)` — opens/creates the DB (running `_purge_poisoned_entries`), disables itself gracefully on any DB error
  - `.enabled -> bool`, `.get(...)`, `.put(...)`, `.close()`

**Schema:** table `translation_memory` (`key, source_language, source_text, translated_text, model_profile, glossary_hash, created_at, last_used_at, hits`).

**Poisoned-entry purge (on open):** rows where `translated_text = source_text`, or containing `[CHENGYU:`, or containing `<|`.

**Constants / env:** `_DEFAULT_DB_PATH = cache/translation_memory.sqlite3`;
`TRANSLATION_MEMORY_MODE` (`auto`/`on`/`off`), `TRANSLATION_MEMORY_DB` — both read by the CLI flag defaults in `translate.py`.

### 4.12 `src/subtitle_quality.py`

**Responsibility:** Post-translation quality diagnostics for the generated SRT.

- `clean_translation_text(text) -> str`
- `CueIssue` (dataclass): `cue_index`, `start`, `end`, `issues`; properties `has_errors`, `has_warnings`
- `analyze_cues(cues) -> list[CueIssue]`
- `QualityReport` (dataclass): `cue_count`, `warning_count`, `error_count`, `empty_count`, `untranslated_count`, `untranslated_marker_count`, `tag_leakage_count`, `cjk_residue_count`, `duplicate_count`, `overlap_count`, `average_cps`, `max_cps`, `average_duration`, `max_duration`, `issues`; `.to_dict()`, `.to_json(indent=2)`
- `build_report(cues, *, untranslated_count=0) -> QualityReport`
- `print_summary(cues, *, untranslated_count=0) -> QualityReport`

**Thresholds:**

| Check | Warning | Error |
|---|---|---|
| CPS | ≥ 18.0 | ≥ 22.0 |
| Visible chars | ≥ 80 | ≥ 110 |
| Duration (too short) | ≤ 0.8 s | ≤ 0.5 s |
| Duration (too long) | ≥ 6.0 s | ≥ 8.0 s |
| Line count | ≥ 2 | ≥ 3 |
| CJK residue ratio | > 0 (warning) | > 0.5 |

**Severity policy:** leakage/empty/untranslated-marker are errors; a small CJK residue
(ratio ≤ 0.5 — likely a retained name, honorific or glossary term) is a warning;
mostly-CJK lines are errors; duplicates/overlaps/CPS/length/duration are warnings.
`--strict-quality` fails on any error or untranslated cue; warnings alone never fail.
`has_errors` is true when any issue ends in `_error` **or** is `empty_text`.

**Detection regexes:** `_ASR_TAG_RE` (`<|...|>`), `_EMOTION_TAG_RE`
(`<HAPPY|SAD|ANGRY|NEUTRAL|FEARFUL|DISGUSTED|SURPRISED>`), `_FANSUB_MARKUP_RE`
(`[CHENGYU:…]` / `[TRANSLATOR…`), `_UNTRANSLATED_MARKER = "[untranslated]"`.

### 4.13 `src/postprocess.py`

**Responsibility:** Fansub-quality cleanup of model output.

- `fix_fused_english(text)`, `strip_residual_cjk(text)`, `strip_literal_gloss(text)`,
  `clear_redundant_punctuation(text)`, `clean_translation_text(text)`
- `break_lines(text, max_chars=37) -> str` — emits `\N`
- `snap_overlaps(cues, gap_ms=50) -> list` — trims a cue's `end` only when consecutive cues overlap, never below `MIN_DURATION = 0.300` s
- `format_translator_note(text)`, `apply_all(cues, max_line_chars=37, overlap_gap_ms=50) -> list`

**Notable constants:** `_PRESERVE_CAMEL` (iPhone, YouTube, Hy-MT2, …), `_CJK_RE`,
`_LIT_GLOSS_RE` (`(lit. …)`), `_DIGIT_WORD_BOUNDARY_RE`, `_FUSION_FIXES`.

### 4.14 `src/ass_io.py`

**Responsibility:** Write Aegisub-compatible `.ass` files with a default style and CJK-capable fonts.

- `AssStyle` (dataclass) — defaults `fontname="Arial"`, `fontsize=52`, alignment 2, `margin_v=30`, …
- `font_for_language(source_language) -> str`
- `write_ass(path, cues, style=None, *, title="Subtitles", source_language=None, font=None, fontsize=None) -> int`

**`FONT_BY_LANG`:** `""`→Arial, `ja`→Noto Sans CJK JP, `zh`/`zh-cn`/`zh-sg`→Noto Sans CJK SC,
`zh-tw`→Noto Sans CJK TC, `zh-hk`/`yue`→Noto Sans CJK HK, `ko`→Noto Sans CJK KR.
Script info: `PlayResX 1920`, `PlayResY 1080`, `WrapStyle 0`, `YCbCr Matrix TV.709`.

### 4.15 `src/cjk.py`

**Responsibility:** Dependency-free CJK script detection, display width and kinsoku line breaking.

- `char_width(ch) -> int` (2 for East-Asian F/W), `text_width(text) -> int`
- `contains_cjk(text) -> bool`
- `detect_cjk_language(text, default=None) -> str | None` — `zh`/`ja`/`ko` by script ratio; needs ≥ 8 CJK chars
- `detect_cjk_from_cues(cues, sample_size=80) -> str | None`
- `break_cjk(text, max_width=26, max_lines=2) -> str` — kinsoku-aware `\N`-joined lines

**Constants:** `NO_LINE_START` (closing punctuation / small kana), `NO_LINE_END`
(opening brackets), `_PUNCT_SPLIT_RE`. Extra lines are kept, never dropped.

### 4.16 `src/local_asr.py`

**Responsibility:** Transcribe local media files using FunASR + SenseVoiceSmall (CPU-only GGUF runtime).

```python
def transcribe_local_file(
    file_path, asr_bin=None, asr_vad_bin=None, asr_model=None, asr_vad_model=None,
    asr_lang="auto", threads=None, max_segment_ms=None, max_end_silence_ms=None,
    speech_noise_thres=None, noise_db=None, min_silence_s=None,
    max_cue_duration_ms=None, max_cue_chars=None, no_tags=False,
    max_cue_chars_cjk=None, keep_tags=None, preprocess="auto",
) -> tuple[list[Cue], str | None]
```

**Pipeline, in order:**
1. Resolve `threads` (`FUNASR_THREADS` → `max(2, min(4, cpu_count))`) and apply `None` defaults from env.
2. `effective_keep = bool(keep_tags)` — tag stripping is the default; keeping is opt-in.
3. Resolve the SenseVoice binary, VAD binary, SenseVoice model and VAD model. Raise if the binary or SenseVoice model is missing.
4. **Extract WAV** — ffmpeg → 16 kHz mono `pcm_s16le` with the preprocessing profile; any output drifting > 50 ms from the source is rejected and retried `profile → basic → none`.
5. Duration check (raise if ≤ 0.1 s).
6. **VAD / segmentation** — ffmpeg `silencedetect`; the FunASR VAD binary unless `FUNASR_FORCE_FFMPEG_VAD=1`; fall back to silence-derived speech; refine with `_split_long_segments` (a VAD segment is kept intact while it is ≤ `max_segment_s × 1.25`, i.e. up to 7.5 s at the 6000 ms default, then split).
7. Raise if no segments. For each segment ≥ 0.10 s: cut a chunk WAV, run SenseVoice, parse the output.
8. **Cue splitting** — `_segment_to_cues` uses a CJK-weighted char budget (CJK codepoints count 2) and `max_cue_duration_s`; the split loop shrinks the budget by ×0.8 down to a floor of 18 chars; minimum cue duration 0.12 s.
9. Resolve `source_language` from explicit `asr_lang` or the detected language.
10. **Keyframe snap** for video extensions (`.mp4/.mkv/.webm/.mov/.avi`) when ffprobe is available — ±100 ms; never fatal.
11. `maybe_warn_incomplete(cues, duration)` — warns when the tail is uncovered.
12. Return `(cues, source_language)`.

**Env vars:**

| Variable | Default | Meaning |
|----------|---------|---------|
| `FUNASR_SENSEVOICE_BIN` | `llama-funasr-sensevoice` (PATH) | SenseVoice binary |
| `FUNASR_VAD_BIN` | `llama-funasr-vad` (PATH) | VAD binary |
| `FUNASR_MODEL` | `gguf/sensevoice-small-q8.gguf` | SenseVoice GGUF |
| `FUNASR_VAD_MODEL` | `gguf/fsmn-vad.gguf` | VAD GGUF |
| `FUNASR_THREADS` | `max(2, min(4, cpu_count))` | CPU threads |
| `FUNASR_MAX_SEGMENT_MS` | `6000` | Max ASR segment length (pre-split ceiling 7.5 s) |
| `FUNASR_MAX_END_SILENCE_MS` | `250` | Trailing silence before VAD closes |
| `FUNASR_SPEECH_NOISE_THRES` | `0.55` | VAD speech/noise threshold |
| `FUNASR_NOISE_DB` | `-35` | ffmpeg silencedetect noise floor |
| `FUNASR_MIN_SILENCE_S` | `0.25` | Min silence for ffmpeg silencedetect |
| `FUNASR_MAX_CUE_DURATION_MS` | `3200` | Max cue duration |
| `FUNASR_MAX_CUE_CHARS` | `70` | Max cue chars (non-CJK) |
| `FUNASR_MAX_CUE_CHARS_CJK` | `48` | Max cue chars (CJK) |
| `FUNASR_KEEP_TAGS` | `0` | If `1`, keep ASR tags |
| `FUNASR_INCOMPLETE_WARN_SECONDS` | `8.0` | Min uncovered tail to warn about |
| `FUNASR_VAD_UNITS` | `ms` | VAD output time units (`ms`/`s`) |
| `FUNASR_OUTPUT_FLAG` / `FUNASR_VAD_OUTPUT_FLAG` / `FUNASR_ASR_OUTPUT_FLAG` | auto-detect | CLI flag for the VAD/ASR output file |
| `FUNASR_FORCE_FFMPEG_VAD` | unset (`"1"` = on) | Skip the binary VAD pass |
| `FFMPEG_BIN`, `FFPROBE_BIN`, `IMAGEIO_FFMPEG_EXE` | unset | ffmpeg/ffprobe resolution |

**Preprocessing profiles (`ASR_PREPROCESS_PROFILES`):**
`none` → `None`; `basic` → `highpass=f=80`;
`loudnorm` → `highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11:linear=true`;
`denoise` → `highpass=f=80,afftdn=nf=-25:tn=true,loudnorm=…`.

**Binary resolution order (`_find_exe`, `_funasr_dirs`):** explicit argument / env var →
`vendor/funasr/`, `vendor/funasr/Release/`, next-to-exe `vendor/funasr/`,
`_MEIPASS/vendor/funasr/` → `shutil.which()` on PATH.

### 4.17 `src/local_server.py`

**Responsibility:** Manage a bundled CPU-only `llama-server` process for local translation.

**Public API:**
- `resolve_llama_server(name="llama-server") -> str | None` — bundled paths first, then PATH.
- `server_alive(host, port) -> bool` — `GET /health`, 2 s timeout.
- `server_serves_model(host, port, model_path, timeout=3.0) -> bool` — `GET /v1/models` must list the requested model.
- `start_server(model_path, host, port, n_ctx, n_gpu_layers, *, threads=0, mlock=False) -> Popen` — hidden window (`CREATE_NO_WINDOW`), registered in `_ACTIVE` keyed by `(abs_model_path, host, port)`.
- `_start_with_fallback_flags(base_cmd, optional_flags, key) -> Popen` — tries the optional flags; if the process exits within ~2 s, logs and restarts without them.
- `warmup_local_server(base_url, model, *, timeout=30.0) -> bool` — one tiny chat completion (`temperature 0.1`, `max_tokens 8`); never fatal.
- `ensure_local_server(model_path, host, port, n_ctx, n_gpu_layers, timeout=180.0, *, threads=0, mlock=False) -> tuple[Popen | None, str, int]`
  - Reuses only when `server_alive()` **and** `server_serves_model()` → `(None, "reuse", port)`.
  - If the port is busy with a *different* server, `_find_free_port` (up to 50 attempts) and reports `"started"` / `"reused-on"`.
  - On early process death it surfaces captured stderr, summarised into a hint for corrupt GGUF / unsupported quantisation.
  - On timeout it calls `terminate_server` and raises `RuntimeError`.
- `terminate_server(model_path, host, port)`, `shutdown_servers()` (registered via `atexit` and wired to `QGuiApplication.aboutToQuit`).

**Constants:** `N_GPU_LAYERS = 0`, `DEFAULT_N_CTX = 4096`, `DEFAULT_HOST = "127.0.0.1"`,
`DEFAULT_PORT = 8080`.

**Launch command:** `llama-server -m <model> --host <host> --port <port> --ctx-size <n_ctx> -ngl 0`
plus `-t <threads>` (when > 0) and `--mlock` (when requested).

**Endpoints used:** `/health`, `/v1/models`, `/chat/completions`.

### 4.18 `src/gguf_check.py` — model integrity

**Responsibility:** Decide whether a `.gguf` file on disk is a *complete* model before anything tries to load it.

`inspect_gguf(path) -> (usable, reason)` parses the GGUF header, the metadata KV pairs
and the tensor table (via `mmap`, so the tokenizer metadata of a 1.9 GB model is walked in
well under a second; results are cached on `(abspath, size, mtime_ns)`, cache limit 64).
It then checks that the file is long enough to hold the last tensor's payload — computed
from the tensor's dimensions and its GGML quantisation type — which is what catches a
download cut short by a dropped connection or a full disk. `is_usable_gguf(path)` is the
boolean form; `GgufError` is the exception type.

**Validated:** exists, non-empty, ≥ 32 bytes; magic `b"GGUF"`; version ∈ {1, 2, 3};
plausible tensor/metadata counts; parseable KV and tensor table; `tensor_count > 0`;
`data_start + max_offset + last_tensor_bytes` ≤ file size (else
`"file is incomplete: N byte(s) short…"`). `_GGML_TYPES` carries the quantisation
table (F32 … BF16, including Q8_0 = (32, 34)).

**Not covered:** tensor *payload* contents. Reading gigabytes to verify a file would defeat the point of a pre-flight check.

**Why it exists.** `os.path.exists()` is not a validity check. An interrupted download
leaves a non-empty partial file, so every existence-based check reported the model as
ready; the offline run then failed ~60 s later inside the FunASR binary
(`failed to read tensor data binary blob`) with an error that the failure classifier
mislabelled as "No subtitles could be fetched for this source". Model state is now
three-valued — `ready` / `missing` / `corrupt` (`AppBridge.localModelState`,
`asrModelState`) — the download worker writes to `<name>.part` and renames only after
validation, and `_build_run_config` never hands the CLI an unusable path (it falls back to
the copy in the models folder and logs a `[warn]`).

**Related invariant — `[warn]` lines never drive failure classification.**
The fallback above emits `[warn] Ignoring --asr-model <path>: file is incomplete. Falling
back to the models folder.` That line names a model file *and* the word "incomplete", so it
matched the `ASR_MODEL` pattern in `_FAILURE_PATTERNS` and reported "The local
transcription model could not be used." for runs that failed for an unrelated reason — or
that succeeded. `_classify_failure` now drops advisory lines before scanning (every
`[warn]` in this codebase reports something the app already recovered from); real failures
still arrive as `[error]`, tracebacks or raw subprocess output. The `ASR_MODEL` pattern is
also anchored on the `*.gguf` filename so a bare `--asr-model <path>` argument cannot
match. Covered by
`tests/test_model_integrity.py::TestAdvisoryLinesDoNotDriveClassification`.

**Related invariant — models are searched in more than one folder.**
The bundle used to be written straight into `dist/`, so `_base_dir()` (and the models
folder with it) was `dist/`. The build now uses `--onedir --name TranslationAgent`, which
moved the app folder to `dist/TranslationAgent/` — and with it the models folder,
orphaning everything already downloaded into `dist/gguf/`. The symptom is the one users
report as "but the models are already downloaded": the app cannot see them, downloads them
again, and on a full disk that second download is cut short.

`_model_search_dirs()` is therefore the single lookup path — `_gguf_dir()` (the download
destination) followed by `_legacy_gguf_dirs()`, which adds the sibling `gguf/` folder when
frozen. `_find_model_file()` / `_find_local_model()` read through it, `_build_run_config`
passes the resolved **absolute** path for `--asr-model` / `--asr-vad-model` (the CLI's own
fallback in `src/local_asr.py::_resolve_model` is relative to the working directory, which
is not the app folder for a frozen build), and the Models & storage table reports where a
file was found. A broken copy shadowed by a good one is noted in the row rather than shown
as its state, so the table always agrees with the readiness tick.

### 4.19 `backend/bridge.py` — `AppBridge`

**Responsibility:** The single QObject exposed to QML as the context property `appBridge`
(`main.py`: `engine.rootContext().setContextProperty("appBridge", bridge)`). There is **no**
`qmlRegisterSingleton` / `QmlElement` / `qmlRegisterType` anywhere in `backend/`. It holds
all UI state, builds `RunConfig`, runs the pipeline on a background thread, streams output
to the log, classifies failures, and owns model downloads.

**Classes:** `AppBridge(QObject)`; workers `_ModelDownloadWorker`, `_YouTubeInfoWorker`,
`_YouTubeDownloadWorker` (all `QRunnable`); signal holders `_WorkerSignal`
(`progress(str)`, `done(str)`) and `_YouTubeDownloadSignal` (`progress(str)`, `percent(int)`,
`done(str)`).

**Signals (28):**
`formChanged`, `statusMessageChanged`, `statusStateChanged`, `logTextChanged`,
`logVisibleChanged`, `isRunningChanged`, `canOpenOutputFolderChanged`,
`modelDownloadChanged`, `pipelineModeChanged`, `localModelDownloadPendingChanged`,
`progressChanged`, `resultReadyChanged`, `debugJsonProgressChanged`, `youtubeInfoChanged`,
`youtubeDownloadChanged`, `themeChanged`, `readinessChanged`,
`failureOccurred(str, str, str, str)`, `reviewDirtyChanged`, `logCountsChanged`,
`requestTab(int)`, `stageChanged`, `focusCueIndexChanged`, `failureChanged`,
`requestAdvanced`, `accentChanged`, `cueDataChanged`, `runHistoryChanged`.

**Properties (152), grouped:**

| Group | Properties |
|---|---|
| Mode / backend | `mode`, `pipelineMode`, `backend` |
| Source input | `url`, `filePath`, `sourceLang`, `contentPreset`, `contextMode`, `contextSummary`, `fileSizeText` |
| Output | `outPath`, `outputFormat`, `outputPathResolved`, `canOpenOutputFolder` |
| Translation / cloud | `batch`, `apiKey`, `baseUrl`, `model`, `host`, `port`, `modelName` |
| Local server | `localThreads`, `localMlock`, `localModel`, `localModelReady`, `localModelState`, `localModelProblem`, `localModelCorrupt`, `localModelSelectionProblem`, `localModelDownloadPending`, `localModelDownloadStatus`, `localModelDownloading` |
| ASR | `asrLanguage`, `asrPreprocess`, `asrBin`, `asrVadBin`, `asrModel`, `asrVadModel`, `asrModelReady`, `asrModelState`, `asrModelProblem`, `asrModelCorrupt`, `asrModelSelectionProblem`, `asrThreads`, `asrMaxSegmentMs`, `asrMaxEndSilenceMs`, `asrSpeechNoiseThreshold`, `asrNoiseDb`, `asrMinSilenceS`, `asrMaxCueDurationMs`, `asrMaxCueChars`, `asrMaxCueCharsCjk`, `asrNoTags`, `asrKeepTags` |
| Quality / TM / glossary | `glossaryPath`, `translationMemoryMode`, `translationMemoryDbPath`, `strictQuality`, `qualityTotalCues`, `qualityUntranslated`, `qualityErrors`, `qualityWarnings`, `qualityAverageCps`, `qualityMaxLineChars`, `qualityAverageCpsText`, `qualityScore`, `qualityGrade`, `qualityScoreTone`, `qualityTiles`, `qualityLimits`, `qualityThresholds`, `qualityCpsHistogram`, `qualityDurationHistogram`, `runContext` |
| UI state | `statusMessage`, `statusState`, `logText`, `logErrorCount`, `logWarnCount`, `logVisible`, `isRunning`, `progressStage`, `progressDone`, `progressTotal`, `stageList`, `currentStageElapsed`, `estimatedRemainingSec`, `runElapsedSec`, `resultReady`, `resultStrictState`, `debugJsonProgress`, `failureCode`, `failureTitle`, `failureDetail`, `failureRemediation`, `failureActive`, `outputDirWritable`, `readinessRows`, `cueModel`*, `cueProxy`*, `qualityIssuesModel`*, `cueEditedCount`, `cueCounts`, `cueTimeline`, `cueTimelineRuler`, `focusCueIndex`, `runHistory`, `selectedRunIndex`, `selectedRunRows`, `windowX`*, `windowY`*, `windowWidth`*, `windowHeight`*, `appVersion`*, `environmentRows`* |
| Model download / state | `modelDownloadStatus`, `modelDownloading`, `modelsFolder`*, `modelsUsedText`, `modelsInventory` |
| YouTube media | `youtubeCodecs`, `youtubeResolutions`, `youtubeHasInfo`, `youtubeFormatRows`, `youtubeInfoLoading`, `youtubeInfoError`, `youtubeTitle`, `youtubeHasAv1`, `youtubeHasVp9`, `youtubeHasH264`, `youtubeHasEnglishSubtitle`, `youtubeSelectedCodec`, `youtubeSelectedResolution`, `youtubeSelectionError`, `youtubeSelectedOption`, `youtubeSelectedFileSize`, `youtubeSelectedFormatLabel`, `youtubeDownloadDir`, `youtubeVideoDownloading`, `youtubeVideoProgress`, `youtubeVideoStatus`, `youtubeVideoNotice`, `youtubeSubDownloading`, `youtubeSubStatus`, `youtubeDownloading`, `youtubeDownloadStatus`, `youtubeDownloadedVideo`, `youtubeDownloadedSubtitle` |
| Appearance | `themeName`, `comfortable`, `reducedMotion`, `accentName` |

`*` = `constant=True`.

**Invokable `@Slot` methods (47):**
`setPipelineMode`, `toggleTheme`, `setComfortable`, `setReducedMotion`, `dismissFailure`,
`openAdvancedSettings`, `openDocumentation`, `logFirstErrorPosition`,
`setYouTubeDownloadDir`, `fetchYouTubeInfo`, `downloadYouTubeVideo`,
`cancelYouTubeVideoDownload`, `downloadYouTubeSubtitle`, `cancelYouTubeSubtitleDownload`,
`openFolderForPath`, `downloadAsrModels`, `downloadLocalModel`, `clearLog`, `copyLog`,
`copySummaryText`, `localPath`, `runTranslation`, `cancelRun`, `openOutputFolder`,
`_on_finished`, `saveEditedSubtitles`, `saveEditedSubtitlesToDefault`, `recheckQuality`,
`replaceInCues`, `revertAllEdits`, `openInExternalEditor`, `revealCue`, `saveSettings`,
`setCueText`, `revertCue`, `nudgeCueStart`, `nudgeCueEnd`, `autoFixCue`, `copyToClipboard`,
`exportQualityReport`, `exportIssueCsv`, `exportLog`, `clearRunHistory`, `rerunLastRun`,
`openModelsFolder`, `purgeTranslationMemory`, `openDebugLog`, `clearStoredSettings`.

`saveWindowState(geometry: str)` is a **plain method without `@Slot`** yet is called from
`Main.qml` — see §9.

**Three-valued model state (`ready` / `missing` / `corrupt`):**
- `_model_status(path) -> (state, reason)` — empty/absent → `missing`; else `gguf_check.inspect_gguf(path)` → `ready` or `corrupt` + reason.
- `_resolve_model_status(selected, *fallbacks) -> (state, path, reason)` — a usable fallback masks a corrupt selection; a corrupt selection with no fallback reports `corrupt`.
- `localModelState` = `_resolve_model_status(_local_model, _find_local_model())`.
- `asrModelState` resolves SenseVoice and VAD separately: either `corrupt` → `corrupt`; else either `missing` → `missing`; else `ready`.
- `localModelSelectionProblem` / `asrModelSelectionProblem` use bare `_model_status()` on the user's own path only, so the Settings field can flag the user's file even when a fallback masks it.

**Failure classification — `_FAILURE_PATTERNS`** (compiled with `re.IGNORECASE`, scanned in
this table order inside a newest-first loop over the last `_FAILURE_TAIL_LINES = 200`
non-`[warn]` lines):

| # | Code | Title | Remedy |
|---|---|---|---|
| 1 | `AUTH` | The translation service rejected the API key. | `cloud` |
| 2 | `QUOTA` | The translation service rate-limited the request or ran out of credit. | `cloud` |
| 3 | `NETWORK` | The computer could not reach the translation service. | `retry` |
| 4 | `SOURCE_UNAVAILABLE` | No subtitles could be fetched for this source. | `check_source` |
| 5 | `MISSING_DEPENDENCY` | A required external tool is not installed. | `install_dependency` |
| 6 | `MODEL_DOWNLOAD` | A model download failed. | `download_model` |
| 7 | `MODEL_LOAD` | The local model could not be loaded. | `download_model` |
| 8 | `ASR_MODEL` | The local transcription model could not be used. | `download_model` |
| 9 | `ASR_FAILED` | Local transcription (ASR) failed. | `retry` |
| 10 | `WRITE_FAILED` | The subtitle file could not be written. | `retry` |

Remedy constants: `REMEDY_CLOUD`, `REMEDY_RETRY`, `REMEDY_DOWNLOAD_MODEL`,
`REMEDY_INSTALL_DEPENDENCY`, `REMEDY_CHECK_SOURCE`, `REMEDY_LOG`, `REMEDY_FORM`.

`_classify_failure(log_text) -> (code, title, detail, remedy)`:
1. Split into non-empty stripped lines.
2. **Drop every line starting with `[warn]`** (advisory only).
3. Keep the last 200 lines.
4. Newest-first scan; first regex match in table order wins.
5. Unmatched fallbacks, newest-first: `[error]` prefix → `UNKNOWN` / "The run failed." /
   `REMEDY_LOG`; a traceback line → "The run stopped on an unexpected error."; an
   `error:` line → "The run failed."
6. Otherwise the last tail line, else the last raw line (warn-only log), else
   `"No output was captured. See the log below."`

> The in-code comment above `ASR_MODEL` claims it "Must precede SOURCE_UNAVAILABLE", but in
> the actual tuple `SOURCE_UNAVAILABLE` is entry 4 and `ASR_MODEL` is entry 8 — the comment
> is stale. See §9.

**Model downloads:**
- `_MODEL_URLS`: `sensevoice-small-q8.gguf` → `https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/main/sensevoice-small-q8.gguf`; `fsmn-vad.gguf` → `https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF/resolve/main/fsmn-vad.gguf`
- `_LOCAL_MODEL = "Hy-MT2-1.8B-Q8_0.gguf"` → `https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q8_0.gguf`

`_ModelDownloadWorker.run()` flow: usable file already present → `[ok] already present`;
present but unusable → `[warn] … incomplete or unreadable; downloading it again`
(**damaged destinations are repaired, not skipped**); stream to `<name>.part` in 1 MiB
chunks; `inspect_gguf` the partial; on failure remove it and report the free-disk hint;
`os.replace(partial, dest)` (atomic); append to `downloaded`. After completion the bridge
latches a path only if it is in `worker.downloaded` **and** passes `is_usable_gguf`.

**Search-path helpers:** `_base_dir()` (frozen → dir of `sys.executable`; else the repo
root), `_gguf_dir()` (`<base>/gguf`, created on demand), `_legacy_gguf_dirs()` (frozen only:
the sibling `gguf/`), `_model_search_dirs()` = `[_gguf_dir(), *_legacy_gguf_dirs()]`,
`_find_model_file(filename)`, `_find_local_model()` = `resolve_local_model_path(*_model_search_dirs())`,
`resolve_local_model_path(gguf_dir, *extra_dirs)` (prefers `Hy-MT2-1.8B-Q8_0.gguf`, then a
single unambiguous usable `Hy-MT2*.gguf`, then the sorted Q8 file first).

**`_build_run_config() -> RunConfig` — argv/env per mode:**

*Source branch* — `youtube`: the URL as the positional arg, plus `--source-lang` if set.
`file`: `--file <path>` plus the full ASR block:
`--asr-bin` / `--asr-vad-bin` (skipped with a `[warn]` when the file does not exist),
`--asr-model` / `--asr-vad-model` (used verbatim when `is_usable_gguf`, else
`[warn] Ignoring <flag> <value>: <reason>.` and the absolute `_find_model_file()` fallback,
or the flag is omitted entirely),
`--asr-lang`, `--source-lang`, `--asr-preprocess`, `--asr-threads`,
`--asr-max-segment-ms`, `--asr-max-end-silence-ms`, `--asr-speech-noise-threshold`,
`--asr-noise-db`, `--asr-min-silence-s`, `--asr-max-cue-duration-ms`, `--asr-max-cue-chars`,
`--asr-max-cue-chars-cjk`, `--asr-no-tags`, `--asr-keep-tags`.

*Common to every mode* — `--out` (if set), `--format`, `--batch` (validated; empty → `8`,
non-positive → `ValueError`), `--content-preset`, `--context-mode` (only when valid),
`--context-summary`, `--glossary`, `--translation-memory` (only when not `auto`),
`--translation-memory-db`, `--strict-quality`, and always
`--json-progress --result-json <_result_json_path()>`.

*Backend branch* — `youtube_cloud` and `local_cloud` both use the cloud branch:
`--model` if set, `env["OPENAI_API_KEY"]`, `env["OPENAI_BASE_URL"]`.
`offline` uses: `--local`, `--local-host`, `--local-port`, `--local-model-name`,
`--local-model <resolved absolute path>` (falling back from an unusable selection with a
`[warn]`; raises `ValueError` with download instructions when nothing usable exists),
`--local-threads` (only when > 0), `--local-mlock`, and **no env vars at all**.

Only `OPENAI_API_KEY` and `OPENAI_BASE_URL` are ever written, and never with an empty
value. `TranslationWorker` supports stripping a key by setting a falsy value, but the
bridge never emits one.

**QSettings persistence (`_PERSISTED`, 41 entries — attr, key, default):**

| Group / name | Default | Group / name | Default |
|---|---|---|---|
| `pipeline/mode` | `youtube_cloud` | `asr/maxCueChars` | `70` |
| `pipeline/contentPreset` | `auto` | `asr/maxCueCharsCjk` | `48` |
| `translation/sourceLang` | `""` | `asr/noTags` | `False` |
| `translation/contextMode` | `""` | `asr/keepTags` | `False` |
| `translation/contextSummary` | `False` | `local/model` | `""` |
| `translation/batch` | `8` | `local/threads` | `0` |
| `translation/glossaryPath` | `""` | `local/mlock` | `False` |
| `translation/translationMemoryMode` | `auto` | `quality/strict` | `False` |
| `translation/translationMemoryDbPath` | `""` | `output/format` | `srt` |
| `asr/language` | `auto` | `youtube/downloadDir` | `""` |
| `asr/preprocess` | `auto` | `ui/theme` | `dark` |
| `asr/bin`, `asr/vadBin`, `asr/model`, `asr/vadModel` | `""` | `ui/comfortable` | `False` |
| `asr/threads` | `4` | `ui/reducedMotion` | `False` |
| `asr/maxSegmentMs` | `6000` | `ui/accent` | `iris` |
| `asr/maxEndSilenceMs` | `250` | `run/history` | `[]` |
| `asr/speechNoiseThreshold` | `0.55` | `run/historyMsPerCue` | `0` |
| `asr/noiseDb` | `-35` | `window/x`, `window/y` | `60` |
| `asr/minSilenceS` | `0.25` | `window/w` | `1280` |
| `asr/maxCueDurationMs` | `3200` | `window/h` | `840` |

**Deliberately NOT persisted:** `_api_key` (secrets), plus `_base_url`, `_model`, `_host`,
`_port`, `_model_name`, `_url`, `_file_path`, `_out_path` and all runtime/result state.
`_url` / `_file_path` are captured into `_last_run_snapshot` at run time (for
"Rerun last run") but never written to QSettings. Type coercion: `_BOOL_FIELDS` accept
`"1"/"true"/"yes"`; `_INT_FIELDS` parse `int`; other string defaults apply when the stored
value is a `str`.

**Theme:** `themeName` (`dark` default, coerced) with `toggleTheme()`; `comfortable`,
`reducedMotion`, `accentName` (`iris`/`azure`/`mint`/`amber`/`rose`). Application happens
in QML (`Main.qml` binds `Theme.*` to the bridge); there is no `QPalette` / `setStyle` use
in `bridge.py`.

**Logging:** `setup_logging(base_dir)` creates a rotating `debug.log` (1 MB, 3 backups) in
`base_dir`. In frozen mode `base_dir` is the directory next to the `.exe`. `_MAX_LOG_LINES = 5000`
with a truncation notice; `_LOG_ERROR_RE` / `_LOG_WARN_RE` feed the log counters.

**Also module-level:** `_DONE_PATTERN` (matches `Wrote N cues to …`), `_result_json_path()`
(`cache/last_result.json`), `_remove_file`, `_format_bytes`, `_format_seconds`,
`_format_clock_ms`, `_base_dir`, `setup_logging`.

### 4.20 `backend/models/results.py`

**Responsibility:** The three QAbstractItemModels backing the Review and Quality screens.

**`CueResultModel(QAbstractListModel)`** — virtualized list of final cues from the result
JSON, editable in the Review table. Signals: `countChanged`, `editedCountChanged`.

| Role constant | `roleNames()` |
|---|---|
| `IndexRole` | `cueIndex` |
| `StartRole` | `startText` |
| `EndRole` | `endText` |
| `SourceRole` | `sourceText` |
| `TextRole` | `translationText` |
| `StatusRole` | `statusText` |
| `TagsRole` | `cueTags` |
| `EditedRole` | `cueEdited` |

Methods: `rowCount`, `data`, `setData`, `flags`, `roleNames`, `load(cues, tags_by_index)`,
`clear`, `edited_count`, `revert_cue`, `revert_all`, `get_cue` (copies), `peek_cue` (no
copy), `set_times(row, start_ms, end_ms)`, `count` property. `EditedRole` compares `text`
against `original_text`.

**`CueFilterProxyModel(QSortFilterProxyModel)`** — All / Failed / Warnings / Errors
filtering plus case-insensitive search. Signals `filterModeChanged`, `searchTextChanged`,
`countChanged`. `get(row)` returns a dict for the cue inspector. `filterMode` and
`searchText` are **plain Python `@property`**, not Qt `@Property`, yet are read and written
from QML — see §9. Both setters call the deprecated `invalidateFilter()`
(`results.py:250`, `results.py:261`), which produces the 4 deprecation warnings in the test
run.

**`QualityIssuesModel(QAbstractListModel)`** — flat issue rows from `QualityReport['issues']`
with an `all` / `errors` / `warnings` filter. Signals `countChanged`, `filterModeChanged`.
Roles: `cueNumber`, `issueType`, `severity`, `message`, `friendlyType`, `rawType`.
`_friendly_message(tag)` maps 19 quality tags to human strings; unknown tags fall back to
`tag.replace("_", " ")`.

Module helpers: `_STATUS_ORDER`, `_SEVERITY_ORDER`, `_format_ms(ms)`.

### 4.21 `backend/models/run_config.py`

```python
@dataclass(slots=True)
class RunConfig:
    """Resolved argv + env for a single translation run."""

    argv: list[str]
    env: dict[str, str]
```

### 4.22 `backend/controllers/translation.py`

**Responsibility:** Run the CLI pipeline off the UI thread without blocking QML.

- `_SignalWriter` — file-like object forwarding `write()` to a callback; `flush()` is a no-op.
- `WorkerSignals(QObject)` — `logLine(str)`, `finished(int)`.
- `TranslationWorker(QRunnable)` — constructed with a `RunConfig`.

`TranslationWorker.run()` sequence:
1. `rc = 1`; save `sys.stdout` / `sys.stderr`; snapshot the previous value of every key in `config.env`.
2. Replace both streams with `_SignalWriter(self.signals.logLine.emit)`.
3. Apply env overrides: truthy value → set; falsy → pop.
4. `rc = translate.main(self.config.argv)` — **in-process**.
5. On `TranslationCancelled` → `rc = 2`; on any other exception → emit `[error] …` and `rc = 1`.
6. `finally`: restore streams, restore every env key (pop when the previous value was `None`), emit `finished(rc)`.

The GUI is **not** a subprocess wrapper.

### 4.23 `main.py` / `gui.py`

**`main.py`** — PySide6 bootstrap:
1. `os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")`.
2. `setup_logging(_base_dir())` + installs an `excepthook` that logs unhandled exceptions.
3. Resolves QML/plugin dirs: frozen → `_MEIPASS/PySide6/qml` (fallback `_MEIPASS/ui/qml`); dev → `<PySide6>/qml`. Sets `QT_PLUGIN_PATH` when the plugins dir exists.
4. `QGuiApplication` with `setApplicationName("Translation Agent")` / `setOrganizationName("Translation Agent")` (this is what gives `QSettings` its registry key).
5. `app.aboutToQuit.connect(shutdown_servers)`.
6. `_load_bundled_fonts()` — registers every `.ttf`/`.otf`/`.ttc` under `<resource>/assets/fonts`; a missing directory is fine.
7. `QQmlApplicationEngine`, collects `engine.warnings`, sets the `appBridge` context property, loads `<resource>/ui/qml/Main.qml`.
8. Returns `-1` when no root object was created (logging the collected QML warnings, and dumping the frozen PySide6 tree at debug level).

**`gui.py`** — compatibility shim: `from main import main` → `main()`. Canonical command is `python main.py`.

### 4.24 QML UI (`ui/qml/`)

**`Main.qml`** — `ApplicationWindow` (id `window`) with a single `ColumnLayout`:

```
ApplicationWindow
└─ ColumnLayout
   ├─ CommandBar            (Theme.topbarHeight = 56 px)
   ├─ RowLayout
   │  ├─ IconRail           (Theme.railWidth = 64 px)
   │  └─ StackLayout        (currentIndex: window.currentPage)
   │     ├─ 0 RunPage   1 ReviewPage   2 QualityPage   3 LogPage   4 SettingsPage
   └─ StatusBar             (Theme.statusbarHeight = 30 px)
└─ CommandPalette            (anchors.fill: parent)
```

- **Navigation is `window.currentPage` (int 0–4)** — not a `StackView`, not a tab bar. All five pages are instantiated once and kept alive. `switchToTab(index)` guards the range.
- Navigation sources: `IconRail.navigate(index)`, `CommandPalette.navigateRequested(index)`, keyboard shortcuts, and bridge-initiated `Connections` (`requestTab`, `requestAdvanced`, `focusCueIndexChanged`).
- **Icon rail items:** 0 Run (`play`), 1 Review (`list`, warning badge = `qualityErrors + qualityWarnings`), 2 Quality (`shield`), 3 Log (`terminal`), 4 Settings (`settings`).
- **Shortcuts:** `Ctrl+1..4` pages, `Ctrl+,` Settings, `Ctrl+K` palette, `Ctrl+Return`/`Ctrl+Enter`/`Ctrl+R` run, `Ctrl+.` cancel, `Ctrl+S` save edited subtitles, `Ctrl+F` Review + focus search, `Ctrl+L` Log.
- Window geometry is bound to `appBridge.windowX/windowY/windowWidth/windowHeight`; `onClosing` calls `appBridge.saveWindowState(...)`.
- Theme push: `Binding { target: Theme; … }` for `themeName`, `comfortable`, `reducedMotion`, `accentName` (a singleton cannot read the `appBridge` context property directly).

**Pages:**

| Page | Contents |
|---|---|
| `RunPage.qml` | Three columns, one whole-screen scroll, both column headers on a shared baseline. **Source** — the two-axis `Source` (YouTube URL / local media file) and `Engine` (cloud LLM / local model) selectors, then the URL + preview tile or the local drop-zone; a constant-height container, so switching source swaps content and not layout. **Processing** — output path/format, model state, ASR state, context mode, batch, translation memory, glossary, the strict-gate switch, the content-preset chip row, `StageStrip`, and the model downloads as *secondary* actions. **Inspector** — `ReadinessChecklist` (a derived validator, not a numbered step), `ErrorCard`, `ProgressPanel`, last-run card, live log. Opens `YouTubeSubtitlePanel` / `YouTubeVideoPanel`. |
| `ReviewPage.qml` | Cues card wrapping `CuePreviewTable` (edit count, save changes, open in external editor, revert all), `Timeline` card, cue inspector card, find & replace card. Whole content column is `visible: appBridge.resultReady`. |
| `QualityPage.qml` | Score card (`ProgressRing` + `MetricChip` row inside an `OverflowRow`), issues card (`qualityIssuesModel` + filter chips with live counts + `revealCue`), distributions card (CPS/duration `Histogram`), gate / thresholds / run context / export cards. Whole content column is `visible: appBridge.resultReady`. |
| `LogPage.qml` | Run history list (timestamp, source, engine, outcome; click **opens** the run into Review/Quality) + selected-run detail; full-height console with tone filters and copy/export/clear. |
| `SettingsPage.qml` | **7** categories — Appearance, Translation, Transcription, Models & storage, Shortcuts, Data & privacy, About — with real gating (only the selected category renders) and an in-category keyword filter. The old single-scroll blob and the `Environment` category are gone. |

**Components (43 files, all in `components/qmldir`):** `AppButton`, `AppCard`, `AppCheckBox`*,
`AppSwitch`, `BoundComboBox`, `BoundField`, `Chip`, `CommandBar`, `CommandPalette`,
`CompactComboBox`, `CompactTextField`, `ConsoleView`, `CueInspector`, `CuePreviewTable`,
`DangerZone`, `EmptyState`, `ErrorCard`, `FieldLabel`, `FilterChip`, `Histogram`, `Icon`
(QtQuick.Shapes stroke set on a 24×24 grid, ~45 named paths), `IconRail`, `KeyValue`,
`MetricChip`, `OverflowRow`, `Pill`, `ProgressPanel`, `ProgressRing`, `ReadinessChecklist`,
`RunButton`, `SegmentedControl`, `SettingsRow`, `ShortcutRecorder`, `StageStrip`, `StatTile`,
`StatusBar`, `StatusMark`, `StatusPill`, `StatusStrip`, `Timeline`, `Toast`,
`YouTubeSubtitlePanel`, `YouTubeVideoPanel`.
`*` = registered but never instantiated (see §9).

Components added by the UI rework, and why each exists rather than being inlined:

| Component | Purpose |
|---|---|
| `BoundComboBox` / `BoundField` | Binding-safe editors. A `currentIndex:` / `editText:` expression over a bridge value is destroyed by the control's own internal assignment, so the widget stops mirroring the store from the second interaction onward. These re-apply imperatively on notify. |
| `StatusMark` | The app's single status vocabulary: icon + colour + text, five facts (`ok` / `todo` / `error` / `na` / `unchecked`). `na` and `unchecked` must look different — collapsing them is what made the readiness denominator disagree with the visible rows. |
| `StageStrip` | `Source → Transcribe → Translate → Gate → Write`, idle-grey normally, lighting per stage during a run. Driven by the existing `stageChanged` / `stageIndex`. |
| `StatusStrip` | The top bar's single derived read-only status line. |
| `OverflowRow` | A horizontal group that **wraps** instead of shrinking every cell until the labels clip. `RowLayout` has no wrap, which is what produced `TOT/UNG/ERN/…`. |
| `MetricChip` | Label-first metric with a click-through breakdown. Replaces the seven `StatTile` micro-gauges. |
| `DangerZone` | Spatially separated destructive block with a typed confirmation naming what it erases. |
| `EmptyState` | The *Log* empty pattern, extracted: icon, title, body, exactly one next action. |
| `Toast` | Transient `Saved ✓` for autosave. |
| `ShortcutRecorder` | Records a key combo for the shortcut remap editor. |

**Mode labels** live on the bridge, not in a QML picker: `youtube_cloud` → "YouTube Cloud",
`local_cloud` → "Local ASR + Cloud LLM", `offline` → "Offline". The Run screen exposes the
two underlying axes (`Source` × `Engine`) through `appBridge.setSourceEngine(mode,
backend)`, which validates the pair; the previously-unreachable fourth combination
(YouTube source + local engine) renders **disabled with a stated reason**. `ModePicker.qml`
and `PresetPicker.qml` no longer exist.

**`Theme.qml`** — `pragma Singleton`, registered in `ui/qml/qmldir` as
`singleton Theme 1.0 Theme.qml`; root type `QtObject`.
- Theme switching: `themeName` (`dark` default, `light`) with `readonly property bool isDark`;
  plus `comfortable` (density, `fontBoost`), `reducedMotion`, `accentName` with
  `accentChoices` = iris/azure/mint/amber/rose.
- Tokens: spacing `xs 4 … xxl 32`; radii `radiusXs 6 … radiusXl 16`; type scale
  `fontTiny 11 … fontH1 22` (+`fontBoost`); surfaces `background`, `surface`, `surfaceAlt`,
  `surfaceRaised`, `inset`, `border`, `borderSoft`, `borderStrong`, `fieldSecretBackground`;
  text `text`, `textDim`, `textMuted`; semantics `accent`, `accentHover`, `accentInk`,
  `accentSoft`, `accentLine`, `success`, `warning`, `error`, `info`, plus `*Tint` variants;
  fonts `monoFont "Consolas"`, `uiFont "Segoe UI"`; geometry `controlHeight` (38/34),
  `controlHeightSmall` (32/28), `rowHeight`, `topbarHeight 56`, `railWidth 64`,
  `statusbarHeight 30`.
- Functions: `statusIcon/statusLabel/statusColor/statusTint`, `toneColor/toneTint/toneBorder`,
  `formatDuration(sec)`, `formatClock(sec)`.

**`ui/qml/archive/`** — retired pre-rework UI (`Card.qml`, `CustomTextField.qml`,
`PrimaryButton.qml`, `Sidebar.qml`, `StyledRadioButton.qml`,
`views/DashboardView.qml`, `views/SettingsView.qml`, `views/qmldir`). **Nothing in the
current QML or Python references it**; it is dead code kept for reference. Do not edit it,
and do not describe it as the current UI.

### 4.25 Editor map — one store, one editor per screen, mirrors are read-only

`AppBridge` **is** the store. There is no second one, and there must not be: `Theme.qml`
is a QML singleton and cannot read the `appBridge` context property, so a QML-side store
would need the same `Binding` shim `Main.qml` already uses for the theme.

The rule, per concept: **one backing attribute, one editor per screen, mirrors read-only,
duplicates deleted.** A second *editor* for one concept is the defect that produced every
"two widgets, one concept, different values" report.

`tests/test_ui_bindings.py` is the executable half of this table. It writes each store
attribute programmatically, simulates the user having interacted with the widget
(assigning `currentIndex` / `editText` by hand, which is exactly what the control does
internally), then changes the store again and asserts the widget followed. Add a row here
and a case there together.

| Concept | Store attribute | Editor(s) | Read-only mirror(s) | Duplicates removed |
|---|---|---|---|---|
| **Pipeline mode** (source × engine) | `pipelineMode`, derived; written via `setSourceEngine(mode, backend)` | `bound.run.source`, `bound.run.engine` (RunPage) | `StatusStrip`; the `Selected run` card; every Log history row | `CommandBar` `ModePicker`, `ModePicker.qml`, the Settings mode editor |
| **Content preset** | `contentPreset` | RunPage chip row (`RunPage.qml:951-956`) | Quality `Run context` | `CommandBar` `PresetPicker`, `RunPage` `PresetPicker`, `PresetPicker.qml` |
| **Spoken / source language** | `sourceLang` (YouTube) · `asrLanguage` (local file) | `bound.run.language` (RunPage), `bound.settings.spokenLanguage` (Settings) | — | the two unlabeled `CommandBar` dropdowns, the empty `Translate from` select |
| **Output format** | `outputFormat` | `bound.run.outputFormat` (RunPage) | — | — |
| **Context mode** | `contextMode` | `bound.run.contextMode`, `bound.settings.contextMode` | — | — |
| **Translation memory** | `translationMemoryMode` | `bound.run.translationMemory`, `bound.settings.translationMemory` | — | — |
| **Strict quality gate** | `strictQuality` | Quality card header switch, RunPage switch, Settings switch | Quality card body `Pill`; `StatusStrip` | — (the header/body pair was already correct; it was RC-1 that made them disagree) |
| **Rolling scene summary** | `contextSummary` | RunPage switch, Settings switch, palette toggle | — | — |
| **Theme** | `themeName` | `bound.chrome.theme` (CommandBar), `bound.settings.theme` (Settings), palette toggle | — | the `Light theme` action-label (a label that looked like a button) |
| **Density** | `comfortable` | `bound.settings.density` | — | — |
| **Accent** | `accentName` | Settings swatch row | — | — |
| **Reduce motion** | `reducedMotion` | Settings switch, palette toggle | — | — |
| **Batch size** | `batch` | `settings.batch` (Settings), RunPage field | — | — |
| **Glossary** | `glossaryPath` | one labelled control per screen (Run, Settings) | — | the field+`Choose` button *pairs* |
| **Local model path** | `localModel` | `settings.localModel` | RunPage model-state line | — |
| **Audio preprocessing** | `asrPreprocess` | `bound.settings.ffmpegPreprocess` | — | — |
| **Shortcuts** | `ui/shortcuts` (JSON map) | `ShortcutRecorder` in Settings | `Main.qml` `Shortcut` sequences; palette hints; bottom-bar legends | the read-only shortcut list |
| **Run history** | `run/history` (JSON list) | written by the run itself | Log left column; `Selected run` card | — |
| **Log** | `logText` | — | `ConsoleView` (Run + Log) | the `StatusBar` `Log` button (the rail owns it) |

Two conventions that are not visible in the table:

* **A mirror is never given a `MouseArea` / `onClicked` / action verb.** A `Pill`, `Chip`
  or `StatusPill` states a value; if it needs to change something it is a button instead.
  `tests/test_ui_hygiene.py` enforces the elision half of this; the pill half is a review
  rule, not a test.
* **Every QML call into `appBridge` targets a `@Slot`.** A plain Python method is not
  callable from QML, and the failure is silent — `saveWindowState` was a plain method for
  the whole life of the five-page shell, so window geometry never persisted.

---

## 5. CLI Reference

### 5.1 All Flags

| Flag | Default | Required | Meaning |
|------|---------|----------|---------|
| `url` (positional) | -- | YouTube mode | YouTube video URL |
| `--file` | -- | Local mode | Local media path (ignores the URL) |
| `--model` | `OPENAI_MODEL` | No | Override model |
| `--out` | `<title>.srt` | No | Output path (a `.ass`/`.srt` extension overrides `--format`) |
| `--format` | `srt` | No | `srt` or `ass` |
| `--ass-font` | source-detect | No | Override ASS font name |
| `--ass-fontsize` | `52` (effective) | No | Override ASS font size |
| `--batch` | `8` | No | Cues per translation call |
| `--local` | off | No | Use a llama.cpp server |
| `--local-host` | `127.0.0.1` | No | Server host |
| `--local-port` | `8080` | No | Server port |
| `--local-model-name` | `Hy-MT2-1.8B-Q8_0` | No | Model id sent to the local server |
| `--local-model` | -- | No | Auto-start the bundled server against this GGUF |
| `--local-threads` | `0` | No | Local server CPU threads (`LLAMA_SERVER_THREADS`) |
| `--local-mlock` | off | No | Lock the local model in RAM (`LLAMA_SERVER_MLOCK`) |
| `--asr-bin` | `FUNASR_SENSEVOICE_BIN` / PATH | No | SenseVoice binary |
| `--asr-vad-bin` | `FUNASR_VAD_BIN` / PATH | No | VAD binary |
| `--asr-model` | `FUNASR_MODEL` / `gguf/sensevoice-small-q8.gguf` | No | SenseVoice GGUF |
| `--asr-vad-model` | `FUNASR_VAD_MODEL` / `gguf/fsmn-vad.gguf` | No | VAD GGUF |
| `--asr-lang` | `auto` | No | ASR source language (`auto`/`zh`/`en`/`ja`/`ko`/`yue`) |
| `--source-lang` | unset | No | YouTube: force a source track (`ja`, `zh`, `zh-TW`, `ko`, `yue`, `en`). Local: translation source hint when `--asr-lang` is auto/unknown |
| `--download-video` | off | No | Also download the video; optional codec `best`/`av1`/`vp9`/`h264` |
| `--download-subtitle` | off | No | Also download the English subtitle track |
| `--asr-threads` | `4` | No | FunASR CPU threads |
| `--asr-max-segment-ms` | preset/env → `6000` | No | Max ASR segment length |
| `--asr-max-end-silence-ms` | preset/env → `250` | No | Trailing silence before VAD closes |
| `--asr-speech-noise-threshold` | preset/env → `0.55` | No | VAD speech/noise threshold |
| `--asr-noise-db` | preset/env → `-35` | No | ffmpeg silencedetect noise floor |
| `--asr-min-silence-s` | preset/env → `0.25` | No | Min silence for ffmpeg silence detection |
| `--asr-max-cue-duration-ms` | preset/env → `3200` | No | Max subtitle cue duration |
| `--asr-max-cue-chars` | preset/env → `70` | No | Max cue chars (non-CJK) |
| `--asr-max-cue-chars-cjk` | preset/env → `48` | No | Max cue chars (CJK) |
| `--asr-no-tags` | off | No | Do not request SenseVoice tag output |
| `--asr-keep-tags` | off | No | Keep ASR `<\|...\|>` tags (disable default stripping) |
| `--asr-preprocess` | `auto` | No | FFmpeg preprocessing (`auto`/`none`/`basic`/`loudnorm`/`denoise`) |
| `--content-preset` | `auto` | No | Scenario preset (`auto`/`drama`/`anime`/`music`/`documentary`/`variety`/`lecture`) |
| `--prompt-profile` | unset | No | Prompt addendum (`general` = none, plus the six content profiles) |
| `--context-mode` | preset/backend | No | Translation context level (`off`/`light`/`standard`/`deep`) |
| `--context-summary` | off | No | Cloud-only rolling scene summary |
| `--glossary` | `TRANSLATION_GLOSSARY` | No | Glossary file path |
| `--translation-memory` | `auto` | No | TM mode (`auto`/`on`/`off`) |
| `--translation-memory-db` | `cache/translation_memory.sqlite3` | No | TM database path |
| `--quality-report` | unset | No | Write a JSON quality report |
| `--result-json` | unset | No | Write machine-readable result JSON for GUI review |
| `--strict-quality` | off | No | Exit 1 on serious quality errors or untranslated cues |
| `--json-progress` | off | No | Emit machine-readable progress lines |

**Removed flags (do not reintroduce):** `--cloud-rescue`, `--cloud-rescue-model`,
`--cloud-rescue-batch`; also `--asr-preset` and `--context-window`, superseded by
`--content-preset` and `--context-mode`.

### 5.2 Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (subtitle file written) |
| `1` | Runtime error (fetch / transcription / translation / write failure, endpoint-fatal error, `--strict-quality` violation) |
| `2` | Configuration error (missing key/model, bad preset, no URL and no `--file`) **or user cancellation** |

### 5.3 Standard Output Lines (parsed by GUI / tests)

| Line | Meaning |
|---|---|
| `[mode] source=YouTube backend=cloud` | run summary, first line of the pipeline |
| `Fetched {N} cues. Translating into English...` | post-fetch |
| `[detect] --asr-lang auto; script heuristic detected '{lang}' …` | auto language detection |
| `[tm] Translation memory disabled due to error: …` | TM degraded gracefully |
| `[translation] WARNING: {n}/{N} cues were NOT translated.` | failed-cue report (followed by up to 30 `cue i: 'source'` lines) |
| `[local] llama-server ({how}) on {host}:{port} serving {path}` | auto-started server |
| `Using local llama.cpp server at {url}` | connected to a server |
| `[mode] Completed: {N} cues written, {M} untranslated. Format: {fmt}.` | completion summary |
| `[quality] Report written to {path}` | `--quality-report` |
| `[result] JSON written to {path}` | `--result-json` |
| `Downloaded subtitle: {path}` / `Downloaded video: {path}` | `--download-*` |
| `Wrote {N} cues to {path}` | **must be the final line** — the GUI regex keys off it |
| `{"type":"progress","stage":"…","done":n,"total":n}` | `--json-progress` |

---

## 6. GUI Architecture

### 6.1 Threading Model

**Rule: never block the QML main thread.**

- `AppBridge.runTranslation()` builds a `RunConfig` and submits a `TranslationWorker` to `QThreadPool`.
- The worker patches `sys.stdout`/`sys.stderr` with `_SignalWriter`, applies `RunConfig.env`, calls `translate.main(argv)` in-process, then restores streams and env in `finally` and emits `finished(rc)`.
- `AppBridge._on_finished(rc)` maps the code onto the status state, loads the result JSON into the cue/quality models, classifies the failure, and appends a run-history entry.
- Model downloads, YouTube inspection and YouTube downloads each run on their own `QRunnable` with their own signal holder, so a download never blocks a run.

### 6.2 State Persistence

See §4.19 for the full `_PERSISTED` table (41 QSettings keys). `QSettings` resolves to
`HKCU\Software\Translation Agent\Translation Agent` on Windows.
`clearStoredSettings()` calls `QSettings.clear()` + `sync()`. **The API key is never
persisted.**

### 6.3 Model Download URLs

| File | URL |
|---|---|
| `sensevoice-small-q8.gguf` | `https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/main/sensevoice-small-q8.gguf` |
| `fsmn-vad.gguf` | `https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF/resolve/main/fsmn-vad.gguf` |
| `Hy-MT2-1.8B-Q8_0.gguf` | `https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q8_0.gguf` |

Downloads land in `<app dir>/gguf/`; a frozen build also looks in the sibling `gguf/`
(§4.18).

---

## 7. Build & Distribution

### 7.1 PyInstaller Build (`build_exe.bat`)

Produces a **onedir** bundle at `dist/TranslationAgent/TranslationAgent.exe`
(`--noconfirm --onedir --windowed --name TranslationAgent`). We deliberately avoid
`--onefile`: onefile re-extracts the whole bundle to `%TEMP%\_MEIxxxx` on every launch,
which triggers "Failed to extract Crypto…" (PYI-16308) when antimalware blocks the crypto
`.pyd` mid-extraction, or when the temp drive is full / the path exceeds MAX_PATH. onedir
keeps files on disk, so there is no runtime extraction and that error class disappears
(and startup is far faster).

**Measured size:** `dist/TranslationAgent/` is ≈ 856 MB, of which `_internal/` is ≈ 832 MB.
The build deletes `dist\TranslationAgent` before rebuilding, so free disk space of roughly
one bundle (~1 GB) is required. An interrupted COLLECT leaves a **mixed** bundle that still
launches — see the integrity tests in §15.

**Bundled data:**
- `ui` (the whole directory, via `--add-data "ui;ui"`) and `ui/qml`, `ui/qml/components`
- `vendor/funasr` (FunASR binaries), `vendor/llama` (llama-server + DLLs)
- `PySide6/qml/Qt`, `QtQml`, `QtQuick`, `builtins.qmltypes`, `jsroot.qmltypes`
- `PySide6/plugins/platforms`, `imageformats`, `styles`, `iconengines`, `qmltooling`
- `ffmpeg` from `imageio-ffmpeg`, under its real name (`ffmpeg-win-x86_64-v7.1.exe`);
  `src.youtube_media._ensure_ffmpeg_exe_named()` copies it to `ffmpeg.exe` at runtime
- `yt-dlp` as a Python package (`--hidden-import yt_dlp` pulls in its own PyInstaller hook,
  which collects the extractors, `requests`/`certifi` and the yt-dlp-ejs JS helpers)

**Declared hidden imports:** `PySide6.QtCore`, `QtGui`, `QtQml`, `QtQuick`,
`QtQuickControls2`, `QtNetwork`, `QtWidgets`; `backend`, `backend.bridge`,
`backend.controllers`, `backend.controllers.translation`, `backend.models`,
`backend.models.run_config`; `src`, `src.config`, `src.fetch_subs`, `src.gguf_check`,
`src.translate`, `src.youtube_media`, `src.ytdlp`, `src.srt_io`, `src.local_asr`,
`src.local_server`; `translate`, `dotenv`, `openai`, `yt_dlp`.

> **`assets/fonts` is NOT bundled.** `main.py::_load_bundled_fonts()` reads
> `<resource>/assets/fonts`, but `build_exe.bat` has no `--add-data "assets;assets"` line
> and `dist/TranslationAgent/_internal/assets/` does not exist. The packaged app therefore
> falls back to system fonts. See §9.

**Prerequisites for build** (each guarded by `if not exist`):
`vendor/funasr/llama-funasr-sensevoice.exe`, `vendor/funasr/llama-funasr-vad.exe`,
`vendor/llama/llama-server.exe`, plus PySide6 and `imageio-ffmpeg` resolvable via
`python -c` (so the script stays machine-portable).

**Runtime behaviour when frozen:**
- `sys._MEIPASS` is the extraction dir (onedir: the `_internal` folder).
- QML imports resolve from `_MEIPASS/PySide6/qml`, then `_MEIPASS/ui/qml`.
- `vendor/funasr` and `vendor/llama` resolve from `_MEIPASS/vendor/...`.
- `debug.log` is written **next to the `.exe`**, not in `_MEIPASS`.
- yt-dlp runs **in-process** (§4.4); it must not be shelled out to.
- **yt-dlp-ejs** needs a JS runtime (deno/node/bun) for some YouTube formats. The JS
  helpers are bundled, but the runtime is not — if it is missing, yt-dlp reports the usual
  "yt-dlp-ejs" error and the app surfaces it.

### 7.2 `TranslationAgent.spec` is machine-specific

The `GENERATED FILE — do not hand-edit` banner is applied *after* the build by
`tools/stamp_spec_header.py`, called from `build_exe.bat`. It cannot live in the spec
itself: PyInstaller rewrites the file from the CLI flags on every run, so a hand-added
comment is destroyed by the very next build — exactly when a contributor is most likely to
open it and start editing. The stamper keeps the `# -*- coding: utf-8 -*-` declaration on
line 1 (Python only honours it within the first two lines) and is idempotent.

`build_exe.bat` invokes `python -m PyInstaller` with explicit flags and does **not** read
the `.spec`; PyInstaller happens to write a spec back out after each run, which is why the
committed file contains absolute paths such as
`C:\Users\Njoro\...\Python312\Lib\site-packages\...`. Those paths describe the last build
machine only. Building with the committed spec on any other machine will fail; use
`build_exe.bat`, or regenerate the spec there. The spec is git-ignored (`*.spec`).

---

## 8. Key Design Invariants (Do Not Break)

1. **Timestamps are sacred.** `start`/`end` are preserved for YouTube or
   cloud-translated output; only `text` is replaced. The **only** exception is the fansub
   post-processing overlap snap in `postprocess.snap_overlaps`, which trims a cue's `end`
   *only* when two consecutive cues actually overlap, never below 300 ms duration.
2. **Cue count in == cue count out.** The numbered-item protocol guarantees this; fallback
   to per-item translation on misalignment. Never silently drop/merge/reorder cues.
3. **Target language is fixed to English.**
4. **Foreignization is the translation philosophy.** Preserve author voice, culture,
   honorifics, period register. Never sanitize, domesticate, or inject modern slang. Keep
   `_FOREIGNIZATION_DIRECTIVE` and `_HY_MT2_STYLE` intact.
5. **Filename is YouTube's English-localized title**, not a translation.
6. **Local servers accept placeholder keys.** Remote endpoints require a real key and fail
   with an actionable message.
7. **Never block the QML thread.** All pipeline work runs on `QThreadPool`.
8. **Local ASR is FunASR + SenseVoiceSmall only.** Whisper.cpp is not used and must not be
   reintroduced.
9. **Model validity is decided by `gguf_check.inspect_gguf()`, never by `os.path.exists()`.**
   Model state is three-valued: `ready` / `missing` / `corrupt`.
10. **`[warn]` lines never drive failure classification.** Advisory output describes
    something the app already recovered from.
11. **A successful run has `failureCode == ""`, even with `[warn]` lines present.**
12. **Cancellation is cooperative and reset per run.** `reset_cancel()` runs first in
    `main()`.

---

## 9. Known Issues & Technical Debt

Verified against the working tree on 2026-09-25. Nothing here is a correctness bug in the
translation pipeline itself unless stated.

**Fixed by the UI redesign (Phases 0–6) — kept here as a record, do not re-report:**

| Was | Fix |
|---|---|
| `saveWindowState` was a plain method, so QML could not call it and window geometry never persisted | `@Slot(str)` (`backend/bridge.py:4285`) |
| `SettingsPage.qml` compared `pipelineMode` against the dead string `"local_asr_cloud_translate"`, so the mode chip read "YouTube Cloud" in Local Cloud mode | the string and the chip are gone; the mode label is derived on the bridge |
| A `currentIndex:` binding on any bridge-backed `ComboBox` was destroyed by the control's own assignment, so editors stopped mirroring the store after one interaction | `BoundComboBox` / `BoundField` (§4.25, `tests/test_ui_bindings.py`) |
| The Quality card could show a header switch reading ON beside a body pill reading OFF | binding hygiene; `tests/test_ui_bindings.py` pins it |
| `Saved` pill and an enabled `Save` button rendered simultaneously on every Settings frame | autosave + `dirty`; the Save button is deleted |
| The seven Quality micro-gauges rendered as `TOT/UNG/ERN/WP/AW/MS/STRETCH` | `MetricChip` inside `OverflowRow`; the labels were always full words — `StatTile`'s uppercase + elide was the defect |
| `tests/test_ui_hygiene.py` matched literal `Icon { name: … }` usages with `name:/s*` instead of `name:\s*`, so the icon-name check ran over an empty list | regex fixed; the check now covers 20 literal usages and all resolve |

| Issue | Severity | Details |
|-------|----------|---------|
| `assets/fonts` not bundled | Medium | `main.py::_load_bundled_fonts()` reads `<resource>/assets/fonts`, but `build_exe.bat` never adds `assets`, and `dist/TranslationAgent/_internal/assets/` does not exist. The packaged app silently falls back to system fonts. Fix: `--add-data "assets;assets"`. |
| `HY_MT2_MAX_BATCH_*` env vars have no effect | Medium | `src/translate.py:277-284` reads `HY_MT2_MAX_BATCH_CUES`, `HY_MT2_MAX_BATCH_CHARS_CJK`, `HY_MT2_MAX_BATCH_CHARS_NON_CJK` into module constants that **nothing reads**. Real budgets come from `translation_windows.HY_MT2_MAX_*`. Either wire them up or delete them. |
| `_FAILURE_PATTERNS` comment contradicts the table order | Low | The comment above `ASR_MODEL` says it "Must precede SOURCE_UNAVAILABLE", but `SOURCE_UNAVAILABLE` is entry 4 and `ASR_MODEL` entry 8. The comment is stale (the behaviour is correct because `[warn]` lines are excluded and the pattern is anchored on `*.gguf`). |
| `CueFilterProxyModel.filterMode` / `searchText` are plain Python properties | Low | `backend/models/results.py` exposes them as `@property`, not Qt `@Property`, yet QML reads *and writes* them. Works today via PySide6's attribute bridging but is fragile; converting to `@Property` with notify signals is the correct fix. |
| `invalidateFilter()` deprecation | Low | `backend/models/results.py` (4 call sites) uses the Qt 6-deprecated `invalidateFilter()`. Replace with `invalidateRowsFilter()`. |
| `tools/screenshot_ui.py` is stale | Low | It looks up `objectName`s `mainTabs`, `advancedDrawer` and `presetPicker`, none of which exist. The current naming scheme is documented and test-enforced: `bound.<screen>.<concept>` for editors, `chrome.*` / `run.*` / `settings.*` for structural anchors. It needs to target `window.currentPage` / the `IconRail`. |
| `ui/qml/archive/` is dead code | Low | 8 retired files (old `DashboardView` / `SettingsView` / `Sidebar` / `Card`). Nothing references them, but `--add-data "ui;ui"` still ships them in the bundle. Delete or exclude. |
| `AppCheckBox.qml` is unreferenced | Low | Registered in `components/qmldir` but never instantiated anywhere (the UI uses `AppSwitch`). |
| `asr/maxSegmentMs` has two defaults | Low | `_PERSISTED` declares `"6000"` while `AppBridge.__init__` initialises `"7000"`; `_load_persisted` runs at construction so the effective default is `6000`. Harmless but confusing. |
| Git history is coarse + one missing object | Medium | History is effectively 12 commits; the UI redesign is entirely uncommitted working-tree state. `git fsck` still reports `missing commit 9e8057259b73d725be9aa9a03b165b3ccfe72036` (parent of `7fd6d713`), so `git log` dies after a few commits and `git rev-list` fails. `git fetch origin` should restore it. See §18.5. |
| `dist/TranslationAgent/` predates the UI redesign | Medium | `TestBuildIsCurrent` (3 tests) fails by design until the bundle is rebuilt. Not a regression — see §18.2. |
| `vendor/` untracked | Medium | Binaries exist locally but are neither committed nor git-ignored. Decide policy. |
| `TranslationAgent.spec` is machine-specific | Low | Regenerated by every build; contains absolute paths from the last build machine. Git-ignored. Never hand-edit. |
| Root scratch probe scripts | Low | `_e2e_download.py`, `_probe_youtube.py`, `_shot_youtube.py`, `_shot_youtube_real.py`, `_verify_offline_flow.py`, `_verify_ui_message.py`, `_polish_*.py`. Not part of the shipped pipeline; they hit the network and/or render offscreen. |

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

# Tests
python -m pytest -q --basetemp="C:/Users/<you>/AppData/Local/Temp/ta_pytest"

# Check an SRT
python tools/check_srt.py output.srt
```

---

## 11. How to Modify / Extend (AI Agent Guide)

### 11.1 Changing Translation Behavior

- Edit `_FOREIGNIZATION_DIRECTIVE` in `src/translate.py` to change the cloud system prompt.
- Edit `_HY_MT2_STYLE` in `src/translate.py` to change the local model's style instruction.
- Do **not** change the numbered-item protocol without also updating `_parse_numbered` and `_translate_batch`.
- Do **not** remove the per-item fallback in `translate_cues`.
- Window sizing lives in `src/translation_windows.py` (`CONTEXT_PROFILES`, `HY_MT2_MAX_*`).

### 11.2 Changing ASR Behavior

- Edit `transcribe_local_file()` in `src/local_asr.py`.
- Tuning knobs: `FUNASR_*` env vars, content presets (`src/presets.py`), function defaults.
- VAD logic is in `_binary_vad()` and `_ffmpeg_silences()`; segmentation in `_prepare_segments()` / `_split_long_segments()`.
- Cue splitting is in `_segment_to_cues()`.
- If you add a tuning knob, add it to `PRESETS` **and** `_CONTROLLED` in `src/presets.py`, then expose it on `AppBridge` + `SettingsPage.qml`.

### 11.3 Adding a New YouTube URL Pattern

Edit `_URL_PATTERNS` in `src/fetch_subs.py`. Each pattern must capture the 11-character
video ID in group 1.

### 11.4 Changing the GUI

- Shell and navigation: `ui/qml/Main.qml` (add a page → extend `IconRail.items`, the
  `StackLayout`, the shortcut list, and `switchToTab`'s range guard).
- A screen: `ui/qml/pages/<Name>Page.qml`. Shared widgets: `ui/qml/components/`.
- Design tokens: `ui/qml/Theme.qml` (both themes come from one token set).
- Do **not** edit `ui/qml/archive/**` — retired UI, not loaded at runtime.
- To expose a new field to QML, add a `Property` to `AppBridge` in `backend/bridge.py`
  with a setter that calls `_set_field` / emits the right signal, then register any new
  component in `ui/qml/components/qmldir`. Keep presentation in QML and state in the bridge.
- Anything a QML file *calls* must be a `@Slot` (or `Q_INVOKABLE`) — see the
  `saveWindowState` defect in §9.

### 11.5 Adding a New Backend

1. Add the mode to `PIPELINE_MODE_*` and `_apply_pipeline_mode` in `backend/bridge.py`, plus a label in `ui/qml/components/ModePicker.qml`.
2. In `AppBridge._build_run_config()`, set `env` / `argv` for the new backend.
3. In `src/config.py` or `translate.py`, handle the new backend type.

### 11.6 Adding a Test

Drop a `tests/test_*.py` file; `pytest.ini` already sets `testpaths = tests` and
`pythonpath = .`. Tests must not need network, API keys or vendor binaries. If you touch
`build_exe.bat`, remember `tests/test_build_contract.py` reads the real script.

### 11.7 Building / Releasing

- Run `build_exe.bat` after any Python/QML change.
- Ensure `vendor/` binaries and `gguf/` models are present.
- Check free disk space first: the build deletes and rewrites ~856 MB.
- The output is `dist/TranslationAgent/TranslationAgent.exe` (onedir). Run it from that
  folder so `debug.log` and relative model paths resolve.
- **Check the exit code.** A PyInstaller run can fail during COLLECT and still leave a
  plausible-looking `dist/`. The observed causes were a sandbox blocking PyInstaller's own
  cleanup of a large output directory and `ENOSPC` when the target drive is full.
- `tests/test_packaged_exe_smoke.py` and `TestBuildIsCurrent` will fail until the bundle is
  rebuilt; that is a signal, not a bug.

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

- 1-based sequential index; timestamps `HH:MM:SS,mmm` (comma, not period); blank line between cues; UTF-8.
- In-memory, `\N` denotes a line break; the SRT writer converts it to a literal newline and the ASS writer keeps it.

### 12.2 `.env`

```
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=gpt-5-mini
```

No spaces around `=`. See `.env.example` for the commented template.

### 12.3 Result JSON (`--result-json`)

```jsonc
{
  "version": 1,
  "output_path": "<absolute path>",
  "format": "srt",
  "source_language": "ja",
  "pipeline_mode": "youtube_cloud",   // or local_cloud / offline
  "strict_quality": false,
  "quality": { /* QualityReport.to_dict() */ },
  "cues": [
    { "index": 1, "start_ms": 1000, "end_ms": 4000,
      "source": "<original text>", "text": "<translated text>",
      "status": "ok" }                 // ok | warning | untranslated
  ]
}
```

---

## 13. Error Handling Conventions

- **CLI:** `RuntimeError` and `ValueError` are caught in `translate.py`'s `main()` and `_run_pipeline()` and printed to `stderr`; exit 1 for runtime failures, 2 for configuration errors and cancellation.
- **GUI:** `TranslationWorker.run()` catches everything, emits `[error] …` log lines and `finished(rc)`; the bridge then runs `_classify_failure()` over the log and populates `failureCode` / `failureTitle` / `failureDetail` / `failureRemediation` for `ErrorCard.qml`.
- **Network failures:** `fetch_subs.py` catches subprocess/network errors and raises `RuntimeError` with actionable messages.
- **Endpoint misconfiguration:** `TranslationEndpointError` aborts instead of retrying forever (`_FATAL_HTTP_STATUS = {404, 405, 501}`), with a message pointing at Settings → Base URL.
- **Local server failures:** `local_server.py` raises `RuntimeError` if the server cannot start or becomes ready within `timeout`, including a summarised hint from the server's stderr.
- **Model files:** validated by `gguf_check.inspect_gguf()` before use; downloads are `.part`-then-rename and damaged destinations are re-downloaded.
- **Translation memory / glossary:** degrade gracefully — a corrupt TM database disables itself with a log line rather than failing the run.

---

## 14. Environment Variables Reference (Consolidated)

| Variable | Module | Default | Purpose |
|----------|--------|---------|---------|
| `OPENAI_API_KEY` | `config.py` | -- | API key (remote endpoints only) |
| `OPENAI_BASE_URL` | `config.py` | `None` | Endpoint override |
| `OPENAI_MODEL` | `config.py` | -- | Model id |
| `FUNASR_SENSEVOICE_BIN` | `local_asr.py` | `llama-funasr-sensevoice` (PATH) | SenseVoice binary |
| `FUNASR_VAD_BIN` | `local_asr.py` | `llama-funasr-vad` (PATH) | VAD binary |
| `FUNASR_MODEL` | `local_asr.py` | `gguf/sensevoice-small-q8.gguf` | SenseVoice GGUF |
| `FUNASR_VAD_MODEL` | `local_asr.py` | `gguf/fsmn-vad.gguf` | VAD GGUF |
| `FUNASR_THREADS` | `local_asr.py` | `max(2, min(4, cpu_count))` | CPU threads |
| `FUNASR_MAX_SEGMENT_MS` | `local_asr.py` / `presets.py` | `6000` | Max ASR segment ms |
| `FUNASR_MAX_END_SILENCE_MS` | `local_asr.py` / `presets.py` | `250` | Max trailing silence ms |
| `FUNASR_SPEECH_NOISE_THRES` | `local_asr.py` / `presets.py` | `0.55` | VAD speech threshold |
| `FUNASR_NOISE_DB` | `local_asr.py` / `presets.py` | `-35` | ffmpeg silencedetect noise floor |
| `FUNASR_MIN_SILENCE_S` | `local_asr.py` / `presets.py` | `0.25` | Min silence duration |
| `FUNASR_MAX_CUE_DURATION_MS` | `local_asr.py` / `presets.py` | `3200` | Max cue duration |
| `FUNASR_MAX_CUE_CHARS` | `local_asr.py` / `presets.py` | `70` | Max cue chars (non-CJK) |
| `FUNASR_MAX_CUE_CHARS_CJK` | `local_asr.py` / `presets.py` | `48` | Max cue chars (CJK) |
| `FUNASR_KEEP_TAGS` | `local_asr.py` | `0` | If `1`, keep ASR tags |
| `FUNASR_INCOMPLETE_WARN_SECONDS` | `local_asr.py` | `8.0` | Min uncovered tail to warn about |
| `FUNASR_VAD_UNITS` | `local_asr.py` | `ms` | VAD output time units |
| `FUNASR_OUTPUT_FLAG` | `local_asr.py` | auto-detect | Shared VAD/ASR output-file flag |
| `FUNASR_VAD_OUTPUT_FLAG` | `local_asr.py` | auto-detect | VAD-specific override |
| `FUNASR_ASR_OUTPUT_FLAG` | `local_asr.py` | auto-detect | ASR-specific override |
| `FUNASR_FORCE_FFMPEG_VAD` | `local_asr.py` | unset | `1` = skip the binary VAD pass |
| `FUNASR_PREPROCESS` | `presets.py` | unset | Preprocessing profile override (auto preset only) |
| `FFMPEG_BIN` | `local_asr.py`, `youtube_media.py` | ffmpeg on PATH | ffmpeg binary |
| `FFPROBE_BIN` | `local_asr.py` | ffprobe on PATH | ffprobe binary |
| `IMAGEIO_FFMPEG_EXE` | `local_asr.py` | -- | Alternative ffmpeg path |
| `TRANSLATION_GLOSSARY` | `translate.py` | unset | Glossary file path |
| `TRANSLATION_MEMORY_MODE` | `translate.py` | `auto` | `auto` \| `on` \| `off` |
| `TRANSLATION_MEMORY_DB` | `translate.py` | `cache/translation_memory.sqlite3` | TM database path |
| `TRANSLATION_CONTEXT_MODE` | `presets.py` | unset | Context mode override (auto preset only) |
| `TRANSLATION_PROMPT_PROFILE` | `presets.py` | unset | Prompt profile override (auto preset only) |
| `LLAMA_SERVER_THREADS` | `translate.py` | `0` | Local server threads |
| `LLAMA_SERVER_MLOCK` | `translate.py` | `0` | Enable mlock (`1` = on) |
| `YT_DLP_BIN` | `ytdlp.py` | unset | Explicit yt-dlp executable |
| `YT_DLP_INPROC` | `ytdlp.py` | unset | Truthy forces the in-process yt-dlp path |
| `QT_QUICK_CONTROLS_STYLE` | `main.py` | `Basic` | Qt Quick Controls style |
| `QT_PLUGIN_PATH` | `main.py` | auto-set | Qt plugins directory |
| `PYTHONDONTWRITEBYTECODE` | -- | not set | Set to `1` to suppress `__pycache__` |

**Read but ineffective (see §9):** `HY_MT2_MAX_BATCH_CUES` (declared default `12`),
`HY_MT2_MAX_BATCH_CHARS_CJK` (`700`), `HY_MT2_MAX_BATCH_CHARS_NON_CJK` (`1000`).

**Removed variables (do not reintroduce):** `CLOUD_RESCUE_ENABLED`, `CLOUD_RESCUE_MODEL`,
`CLOUD_RESCUE_BATCH`, `CLOUD_RESCUE_API_KEY`, `CLOUD_RESCUE_BASE_URL`. Cloud rescue was
removed by product decision.

---

## 15. Testing & Validation

```bash
python -m pytest -q --basetemp="C:/Users/<you>/AppData/Local/Temp/ta_pytest"
```

**Latest verified run: 682 passed, 4 warnings in 98.7 s** (2026-09-16, Python 3.12,
`dist/TranslationAgent/` present so the 14 packaged-exe tests ran rather than skipped). The
4 warnings are all
`DeprecationWarning: QSortFilterProxyModel.invalidateFilter() is marked as deprecated`
from `backend/models/results.py:250` — see §9.

> **Always pass `--basetemp <a path that does not exist yet>`.** Without it, pytest's
> garbage collection of old numbered temp dirs becomes a bulk delete that the sandbox
> blocks, and the process dies before printing the summary. A Git-Bash-style path
> (`/c/Users/...`) breaks `tmp_path` fixtures; use a Windows path.

**Test files and what they cover (34 files):**

| File | Covers |
|---|---|
| `test_srt_io.py` | timestamp format/parse, SRT roundtrip, filename sanitization |
| `test_translate_parsing.py` | `_numbered_block`, `_parse_numbered`, `_is_hy_mt2` |
| `test_translate_validation.py` | `looks_untranslated`, per-item failure behaviour |
| `test_batching.py` | `chunk_texts`, `estimate_text_weight`, `is_cjk_language` |
| `test_glossary.py` | glossary parsing, formatting, hashing |
| `test_translation_memory.py` | TM put/get, key separation, graceful failure |
| `test_subtitle_quality.py` | CPS/duration/char/line thresholds, report building |
| `test_quality_extended.py` | tag/markup leakage, CJK residue, duplicates, overlap |
| `test_local_asr_splitting.py` | `_split_text`, `_segment_to_cues` |
| `test_local_server.py` | server auto-start / warmup helpers (no network) |
| `test_fetch_subs.py` | video-id parsing, fetch helpers |
| `test_fansub_upgrade.py` | `postprocess`, `ass_io` (incl. `font_for_language`) |
| `test_cjk.py` | `src/cjk.py` detection, width, kinsoku line breaking |
| `test_cli_flags.py` | `--json-progress`, `--ass-font`/`--ass-fontsize` wiring |
| `test_presets.py` | preset table values, precedence, addenda |
| `test_context_windows.py` | window builder, context modes, prompts, TM interaction, fallback ladder |
| `test_result_json.py` | `--result-json` schema, final-line contract, untranslated flagging |
| `test_asr_preprocess.py` | preprocessing filter strings, auto→basic, duration-mismatch fallback |
| `test_pipeline_modes.py` | GUI run-config per mode (no `--local` leakage, offline strips cloud env) |
| `test_followup_fixes.py` | P0 fixes from `FOLLOWUP_REVIEW.md`: final-output failure accounting, source-language precedence |
| `test_gguf_integrity.py` | `gguf_check` header/tensor-table validation, against synthetic GGUF files (12 tests) |
| `test_model_integrity.py` | model state resolution, advisory-line classification, search dirs (35 tests) |
| `test_youtube_media.py` | `youtube_media` inspection, selection matrix, probing |
| `test_youtube_format_selection.py` | codec/resolution resolution and refusal messages |
| `test_ytdlp.py` | `TestFfmpegMerge`, `TestFrozenFfmpegLookup`, in-process mode |
| `test_build_contract.py` | parses the real `build_exe.bat` (see below) |
| `test_packaged_exe_smoke.py` | launches the built exe (14 tests) |
| `test_ui_models.py` | `CueResultModel` (editable), the All/Failed/Warnings/Errors proxy, `QualityIssuesModel` roles |
| `test_ux_bridge.py` | failure classification, honest readiness rows, null-safe CPS text, the Quality→Review jump, log counters, theme toggle, subtitle save-back |
| `test_ui_hygiene.py` | encoding/legibility hygiene — guards the mojibake (double-encoded UTF-8) and BOM regressions the UX pass cleaned up |
| `test_qml_smoke.py` | loads `Main.qml` with a live `AppBridge` offscreen — a single QML error fails it, so it guards every component at once |
| `conftest.py` | one session-wide offscreen `QGuiApplication` + fresh `AppBridge` fixtures |
| `gguf_fixtures.py` | builders for tiny synthetic GGUF files (correct header + real tensor table) |

**Static checks (run these too):**

```bash
python -m pyflakes translate.py main.py gui.py backend/*.py backend/**/*.py src/*.py
```

pyflakes catches `undefined name` and unused-variable bugs the test suite cannot reach. It
is deliberately **not** part of the runtime requirements — install it in a scratch venv.

Worth knowing: two shipped bugs were invisible to tests and only pyflakes found them —
`backend/bridge.py` used `Qt.EditRole` without importing `Qt` (the "Replace all" button
raised `NameError`), and `translate.py` referenced `youtube_media` from a function while the
import lived inside a *different* function (the CLI could not download video at all). Treat
a clean pyflakes run as a release gate.

**Scope — and what is *not* a bug.** `translate.py` imports `openai` and `dotenv` at module
level without referencing them in that file. That is intentional: PyInstaller only bundles
modules it can see are imported, and `src/translate.py` imports `openai` lazily, so these
top-level imports exist purely to make the packaged build include them. Do **not** "clean
them up". Anything genuinely unused should still be removed.

**The build has no full end-to-end test — but its contract is checked.**

`tests/test_build_contract.py` parses the real `build_exe.bat` and fails if the build could
not succeed, without running PyInstaller:

- every path the script guards with `if not exist` (vendor binaries) exists, and every `--add-data` / `--add-binary` source exists;
- every `--hidden-import` name actually resolves (a stale name silently drops code out of the exe);
- the runtime-critical modules are declared;
- **every `PySide6.QtXxx` imported in first-party code has a matching `--hidden-import`** — the built exe ships a trimmed Qt, so a new Qt import would otherwise crash only *inside the packaged app*;
- the spec is not treated as build input, still parses, and carries its header;
- the script resolves PySide6/ffmpeg dynamically (i.e. stays portable).

Mutation-checked: adding an undeclared `PySide6.QtBluetooth` import and renaming a guarded
vendor binary each make it fail, so it is not vacuous.

**The built exe is also smoke-tested, and its currency is enforced.**

`tests/test_packaged_exe_smoke.py` (14 tests) launches
`dist/TranslationAgent/TranslationAgent.exe` with `QT_QPA_PLATFORM=offscreen`, waits for
`debug.log` to report the QML load, then kills it. It skips (not passes) when the bundle is
absent — a skip is honest about what was not verified.

Unlike a plain "does it start" test, it guards against **green-lighting a build that does
not reflect the source**, which is how a smoke test normally lies:

- `test_build_is_newer_than_all_bundled_sources` — fails if any bundled first-party `.py` / `.qml` is newer than the exe, naming the stale files.
- `test_bundle_is_internally_consistent` — buckets `_internal/**` by build *date* and fails when the newest date holds under half the files. This is the signature of a build interrupted mid-COLLECT: the old directory survives, a few new files land on top, and **the exe still launches**.
- `test_bundled_qml_matches_the_source_tree` — an `--add-data` miss can ship an older `Main.qml`; compares bytes.

> The fixture deletes `dist/TranslationAgent/debug.log` at setup and now degrades to
> truncation if the delete is refused (sandbox policy, locked file), because letting that
> raise aborted the whole module and turned one hiccup into nine errors.

**Manual validation checklist:**

1. YouTube URL with manual subtitles → SRT with correct timestamps and translated English text.
2. YouTube URL with auto-generated-only subtitles → same as above.
3. `--source-lang ja` on a video with no Japanese track → clear error, no wrong-language fallback.
4. Local video with no subtitles → FunASR transcription → English translation.
5. Local model path (`--local --local-model model.gguf`) → server auto-starts → translation succeeds.
6. Existing server path (`--local` without `--local-model`) → connects to the running server.
7. Local Hy-MT2: confirm the effective window size is reduced and cue count matches.
8. Local media CJK: confirm ASR tags are stripped and cues are shorter for CJK.
9. Cloud rescue: REMOVED — verify no `--cloud-rescue*` flag exists and no docs describe it as active.
10. GUI: run a translation, verify the progress ring/stage stepper updates from JSON progress, Review/Quality pages populate from the result JSON, and the Log page collects the run.
11. GUI: edit a cue, confirm `cueEditedCount` rises, save, and re-check quality.
12. GUI: press Stop mid-run → status "Cancelled", no output file, next run still starts.
13. `python tools/check_srt.py output.srt` → average/max cue durations are reasonable.
14. Preprocessing benchmark: `python tools/benchmark_preprocess.py --media sample.mp4` → comparable per-profile metrics.
15. Frozen build: `build_exe.bat`, run `TranslationAgent.exe`, verify vendor binaries + QML + logs (and note the missing bundled font, §9).

---

## 16. Glossary

| Term | Meaning |
|------|---------|
| **Cue** | One subtitle entry: `start`, `end`, `text`. In code: `src.srt_io.Cue`. |
| **Foreignization** | Translation philosophy: preserve source culture/voice/honorifics; do not domesticate. |
| **Numbered-item protocol** | Batch translation method: cues are numbered `1.` … `N.` sent to the LLM, which must return the same numbers. |
| **Hy-MT2** | Tencent's 1.8B-parameter translation model; Q8_0-quantized GGUF (`Hy-MT2-1.8B-Q8_0.gguf`). |
| **SenseVoiceSmall** | FunASR's small ASR model (GGUF). |
| **FunASR VAD** | Voice Activity Detection model (`fsmn-vad.gguf`) used to segment audio. |
| **llama-server** | llama.cpp's OpenAI-compatible HTTP server (`llama-server.exe`). |
| **AppBridge** | `backend.bridge.AppBridge`; the single QObject exposed to QML as `appBridge`. |
| **RunConfig** | `backend.models.run_config.RunConfig`; argv + env for one pipeline run. |
| **TranslationWorker** | `backend.controllers.translation.TranslationWorker`; QRunnable that runs `translate.main()` off the UI thread. |
| **Translation memory (TM)** | SQLite cache of exact source→target lines, keyed by language/model/glossary hash. |
| **Glossary** | Plain-text source→target term list injected into prompts for consistent terminology. |
| **Cloud rescue** | REMOVED. Local translation never falls back to the cloud; users pick cloud or local per run. |
| **Content preset** | `src/presets.py` scenario profile (auto/drama/anime/music/documentary/variety/lecture) tuning ASR, preprocessing, context mode and prompt addenda. |
| **Context window** | `src.translation_windows.TranslationWindow`; current cues plus read-only before/after context; the primary translation unit. |
| **Context mode** | `off`/`light`/`standard`/`deep` — how much before/after context and rolling memory a window carries. |
| **Result JSON** | Machine-readable run output (`--result-json`) consumed by the Review/Quality pages. |
| **Fallback ladder** | Retry → split-in-half → per-item fallback used when a numbered window fails. |
| **Model state** | Three-valued model validity: `ready` / `missing` / `corrupt`, from `gguf_check.inspect_gguf`. |
| **Failure code** | `_classify_failure()` output (`AUTH`, `NETWORK`, `ASR_MODEL`, …) driving `ErrorCard.qml`. |
| **Remedy** | The action a failure card offers (`cloud`, `retry`, `download_model`, `install_dependency`, `check_source`, `log`, `form`). |
| **Readiness rows** | `AppBridge.readinessRows` — the pre-run checklist on the Run page (ok / warn / n/a). |
| **Cue proxy** | `AppBridge.cueProxy` — the filtered/editable view of `cueModel` used by the Review table. |
| **Run history** | JSON-encoded list of past runs persisted under `run/history`, shown on the Log page. |
| **Command palette** | Ctrl K overlay (`CommandPalette.qml`) exposing 23 commands. |
| **Icon rail** | The 64 px left navigation rail (`IconRail.qml`). |
| **Quality report** | JSON diagnostics of CPS / duration / char-count / line-count / empty cues / tag leakage / CJK residue / duplicates / overlaps. |
| **_MEIPASS** | PyInstaller's extraction directory (when frozen; onedir → `_internal`). |
| **QSettings** | Qt's persistent settings (registry on Windows). |
| **STQ** | 1.25-bit quantization kernel for llama.cpp; no longer used now that the default model is Q8_0. |

---

## 17. Archived documentation (consolidated into this file)

To reduce repository-root clutter, the following historical documents were folded into this
canonical reference and **moved to `docs/archive/`** (content preserved):

- **`PROJECT.md`** (now `docs/archive/PROJECT.md`) — the developer narrative/history. Unique, still-relevant parts preserved here: the fansub philosophy (foreignization over fluency, `[Translator's Note]` convention), the recommended roadmap, and known-gaps notes.
- **`CLAUDE.md`** (now `docs/archive/CLAUDE.md`) — Claude Code guidance. Unique parts preserved: Windows platform conventions (use `python`, not `python3`; `copy`, not `cp`; backslash paths) and the key invariants list.
- **`TASKS.md`** (now `docs/archive/TASKS.md`) — the implementation task tracker (baseline tests, batching, glossary/TM, local server warmup, ASR tag stripping, quality diagnostics, CLI updates, GUI changes, model download, benchmark, test suite, CJK detection). Every item was completed.
- **`updated implementation plan.md`** (now `docs/archive/IMPLEMENTATION_PLAN.md`) — the original multi-phase plan spec. Fully superseded; no open tasks remain.
- `docs/archive/root-md-2026-09-11/` — the nine root planning/review documents removed in the 2026-09-11 cleanup (see §18.1).
- `docs/archive/root-scratch-2026-09-11/` — the root scratch logs and the `_mix_probe` fixture removed in the same pass (see §18.1b).

### Key invariants (preserved from CLAUDE.md / PROJECT.md)

- Original `start`/`end` times are preserved — only `text` is replaced — with the **single
  exception** of the post-processing overlap snap (`postprocess.snap_overlaps`), which trims
  a cue's `end` only when consecutive cues overlap, and never below 300 ms. For
  locally-ASR'd cues, timing is *created* by the ASR pass (keyframe snap), so it is not
  "original" YouTube timing.
- Cue count out == cue count in (numbered-item protocol). Never drop/merge/reorder.
- Target language is English, fixed by design.
- The returned title from `fetch_subs.py` is YouTube's **English** title (used for the
  filename), not a translation we produce.
- Local ASR is **FunASR + SenseVoiceSmall only**; Whisper.cpp is removed and must not be
  reintroduced.
- `_FOREIGNIZATION_DIRECTIVE` / `_HY_MT2_STYLE` prompt invariants stay intact.
- Cloud endpoints require a real key; local servers accept a placeholder.
- Never block the QML thread — the pipeline runs on the `QThreadPool`, the CLI is invoked
  in-process with patched streams.

### Recommended roadmap (still open)

- Validate end-to-end output on a range of videos (manual vs. auto captions, various source
  languages, the offline Hy-MT2 path).
- Handle absent `vendor/` binaries gracefully at runtime (currently enforced only at build
  time).
- Bundle `assets/fonts` so the packaged app ships the CJK font (§9).
- Fix the `saveWindowState` slot defect and the `local_asr_cloud_translate` dead branch (§9).
- Delete or exclude `ui/qml/archive/`, and repair or retire `tools/screenshot_ui.py`.
- See §18.3 for the open backlog.

---

## 18. Project State Record

### 18.1 What was removed from the repository root (2026-09-11)

Ten root-level Markdown documents were read, checked against the working tree, and deleted.
Each had either been fully executed, superseded by a later pass, or made obsolete by a
product decision.

| Document | Verdict | Why |
|---|---|---|
| `TASK_LIST.md` | **Implemented** | Checklist for the mode-simplification / presets / context / UI pass. Every box ticked. Superseded by the code. |
| `full implementation.md` (self-titled `AGENT_IMPLEMENTATION_PLAN.md`) | **Implemented** | Master brief for that same pass. All five requirements landed. |
| `implementation_plan.md` | **Implemented** | YouTube download / flow-separation plan, marked `STATUS: COMPLETE` at 348 tests. Superseded by later YouTube-format-selection work. |
| `FOLLOWUP_REVIEW.md` | **Implemented + partly obsolete** | P0-1…P0-7 and P1-1/P1-2 all fixed. Its cloud-rescue sections describe a feature that was subsequently removed. |
| `IMPROVEMENTS_TRIAGE.md` | **Superseded + partly obsolete** | Approved items landed; many "Deferred" items were later implemented; rescue items obsolete. |
| `REMAINING_RECOMMENDATIONS.md` | **Obsolete** | Forward-looking backlog almost entirely delivered: context windows, content presets, extended CJK quality checks, GUI JSON-progress consumption, bundled CJK fonts, cue preview table, quality panel. |
| `UX_FIXES_IMPLEMENTATION_PLAN.md` | **Implemented, 5 sub-items not** | 23-task UX plan. See §18.3 for the sub-items that never landed. |
| `UX_RESEARCH_REPORT.md` | **Superseded** | A 3 KB fragment reporting the same 23 tasks complete. |
| `FRONTEND_DESIGN.md` | **Superseded** | Design spec for the reworked GUI. The design landed, then the whole UI was rewritten again ("New UI"); §4.24 is now authoritative. |
| — | — | (`README.md` was kept: it is the user-facing quick start.) |

Copies are in `docs/archive/root-md-2026-09-11/`.

### 18.1b Text files removed from the repository root (2026-09-11)

Thirteen root `*.txt` files plus one scratch directory were inspected and removed in the same
cleanup. **Kept:** `requirements.txt`, `requirements-gui.txt`, `requirements-local.txt` and
`assets/fonts/README.txt`. No code reads any `*.txt` at runtime. Archived to
`docs/archive/root-scratch-2026-09-11/`.

### 18.2 Current verified state (2026-09-25)

- **1096 tests collected; 1093 pass, 3 fail by design.** Verified 2026-09-25 with
  `python -m pytest -q --basetemp=… --junitxml=…` (104 s). The three failures are all
  `tests/test_packaged_exe_smoke.py::TestBuildIsCurrent` — the on-disk
  `dist/TranslationAgent/` bundle predates the UI rework. That is the intended signal, not
  a regression: rebuilding is a separate, ~1 GB operation (`build_exe.bat` deletes the old
  bundle first). Rebuild before shipping, not as part of a UI change.
- **Exactly three pipeline modes**: `youtube_cloud`, `local_cloud`, `offline`. Cloud rescue
  is **removed** — no `--cloud-rescue*` flag, no `CLOUD_RESCUE_*` env var, no `src/rescue.py`,
  no GUI control. The only surviving mention in the tree is a stale string in
  `ui/qml/archive/views/SettingsView.qml` (retired UI, not loaded).
- **Content presets** (`src/presets.py`): `auto`, `drama`, `anime`, `music`, `documentary`,
  `variety`, `lecture` — verified field-by-field against §4.9.
- **Context-first translation** (`src/translation_windows.py`): `off`/`light`/`standard`/`deep`;
  `standard` is the resolved default for both backends.
- **GUI**: five-page shell (Run / Review / Quality / Log / Settings) with an icon rail,
  56 px command bar, 30 px status bar, Ctrl K command palette (Navigate / Actions / Toggles /
  Jump-to-setting), dark and light themes, accent choice, density and reduced-motion toggles,
  inline-editable virtualized cue table with save-back and re-check, YouTube inspect +
  video/subtitle download panels, and structured failure cards with remediation. The UI
  redesign added: one store with binding-safe editors (§4.25), autosave instead of a Save
  button, one derived status line, real Settings category gating, a two-axis Run screen with
  a constant-height source panel, and a run history whose rows load a run back into
  Review/Quality.
- **Run history**: `run/history` keeps the last 20 runs; each successful run's result JSON is
  copied to `cache/run_results/<stamp>.json` and pruned with the entry that owns it, because
  the CLI's own `cache/last_result.json` is overwritten every run. `selectRun(index)` loads an
  entry; a failed run says why it has nothing to show.
- **Model integrity**: three-valued model state via `src/gguf_check.py`; `.part`-then-rename
  downloads; multi-folder model search.
- **Build**: `build_exe.bat` produces an **onedir** bundle at
  `dist/TranslationAgent/TranslationAgent.exe` (≈856 MB, deliberately not onefile — §7.1).
- **`--asr-preset` and `--context-window` do not exist.** Superseded by `--content-preset`
  and `--context-mode`. Do not reintroduce them.

### 18.3 Open backlog (verified as *not* implemented)

Small UI items from `UX_FIXES_IMPLEMENTATION_PLAN.md` that were never built. The shell they
were specified against has since been replaced twice, so each needs re-specifying before it
is built. Status against the current UI:

1. **S-04 mode-aware language labels** — **resolved differently.** There is now one labelled
   language control on Run (`bound.run.language`) that reads `sourceLang` for a YouTube
   source and `asrLanguage` for a local file, plus a bound editor in Settings.
2. **S-06 resolved-preset echo** — **still absent.** No "Auto → detected: anime" echo of the
   resolved preset. The Run screen shows the chosen preset, not the resolved one.
3. **S-08 YouTube step strip** — **superseded** by `StageStrip` (`Source → Transcribe →
   Translate → Gate → Write`), which reports the *actual* pipeline rather than the YouTube
   sub-flow. The video panel and subtitle panel did land.
4. **S-11 expand chevron** for long cue lines in the Review table — **still absent.** The
   inspector shows the full cue, so this is convenience, not capability.

Longer-horizon items, all still deferred by design:

- Fuzzy translation memory (`--tm-fuzzy`).
- Bilingual ASS output (`--bilingual`) — blocked by the "target language is English" invariant.
- Automatic cue splitting — blocked by the "cue count in == cue count out" invariant.
- Timing enforcement beyond the documented overlap snap.
- Sound-tag modes (`--sound-tags strip|note|ass-comment`).
- Whisper reintroduction — explicitly forbidden.
- Runtime graceful degradation when `vendor/` binaries are missing (build-time only today).
- **A threshold preset system.** `AppBridge.qualityThresholds` reads module constants out of
  `src/subtitle_quality.py`; there is no preset to name and no editor to mark `custom`. The
  Quality card says "built-in defaults" rather than pretending otherwise. Inventing a preset
  editor would ship a settings surface for a concept the backend does not have.

### 18.3b Flagged to engineering by the UI redesign (deliberately not implemented there)

The UI work stopped at the display boundary. These three are recorded in
`IMPLEMENTATION_PLAN.md` §12 and are **not** UI tasks:

1. **`build_exe.bat` does not bundle `assets/`** while `main.py::_load_bundled_fonts()` reads
   `<resource>/assets/fonts`, so the packaged app falls back to system fonts. One-line
   `--add-data "assets;assets"` fix. (Also listed in §9.)
2. **The XAMPP `htdocs` deployment smell.** The app runs from
   `C:\xampp\htdocs\translation-agent\dist\TranslationAgent` — unusual for a Qt desktop app
   and a plausible source of the path-handling fragility the UI has to paper over. The UI's
   only job here was to stop *displaying* those paths raw, which it does (they now sit behind
   `Copy diagnostics`).
3. **The API-key non-persistence claim — verified 2026-09-25, still engineering's call.**
   The UI promises "Never persisted to disk" on the API-key field. `_PERSISTED`
   (`backend/bridge.py`) does **not** contain the key, and `self._api_key` is initialised to
   `""` at construction and only ever set through `_set_field`, which writes the in-memory
   attribute and the debounce flag — so the key is session-only and the UI statement is
   accurate as the code stands. It remains a *contract* rather than an invariant: nothing
   fails if a future change adds `_api_key` to `_PERSISTED`. If it matters, assert it in a
   test rather than trusting the table.
5. **S-07 stage timers** — partially landed: `ProgressPanel.qml` consumes `stageList`, `currentStageElapsed`, `runElapsedSec` and `estimatedRemainingSec`, but the ordered stage history / per-stage elapsed log described in the plan is not exposed.

Longer-horizon items, all still deferred by design:

- Fuzzy translation memory (`--tm-fuzzy`).
- Bilingual ASS output (`--bilingual`) — blocked by the "target language is English" invariant.
- Automatic cue splitting — blocked by the "cue count in == cue count out" invariant.
- Timing enforcement beyond the documented overlap snap.
- Sound-tag modes (`--sound-tags strip|note|ass-comment`).
- Whisper reintroduction — explicitly forbidden.
- Runtime graceful degradation when `vendor/` binaries are missing (build-time only today).

### 18.4 Documentation conventions for the next pass

- Update **this file** for any developer/architecture/CLI/env change.
- Update **`README.md`** for anything user-visible.
- Do not create new root-level planning or review documents. If a plan is needed, put it in
  `docs/` and delete it when the work lands.
- Keep the "Last updated" line and §18.2's test count current — they are the first thing a
  future agent checks, and a stale count is how this document drifted before.

### 18.5 Known repository-integrity defect (found 2026-09-11, still present)

`git fsck` reports **one missing commit object**:

```
missing commit 9e8057259b73d725be9aa9a03b165b3ccfe72036
broken link from commit 7fd6d713be955efbd080ea4a70d7381a5aefcdc2
```

`7fd6d713` is in `main`'s ancestry (it is the parent of `9d2a21a`), and **its own parent
`9e80572…` is absent from the object store**. Effects:

- `git log` prints a few commits and then dies; history older than `7fd6d713` is unreadable.
- `git rev-list --count HEAD` and `git rev-list HEAD` fail outright.
- Every git command emits `geometric-repack` / `commit-graph` maintenance errors, because auto-maintenance cannot build a graph over a broken parent link.

Working state is unaffected — HEAD, index and working tree are intact.

**Likely cause.** `git count-objects -v` reports `packs: 0, in-pack: 0` with ~1333 loose
objects, i.e. a repack that deleted its old pack but never wrote a replacement. The project
log records the `C:` drive reaching `238G/238G used, 0 available` during an interrupted build
on 2026-09-11; a `git gc`/`repack` running in that window would produce exactly this.

**Fix.** Run `git fetch origin` — the remote is
`https://github.com/njoro1/translation-agent.git` and the missing object should be
restorable if it was ever pushed. Fetch only adds objects, so it is safe. Then confirm with
`git fsck --no-progress`; once the `missing commit` line is gone, `git gc` is safe again.

**Do not run `git gc --prune=now` before this is fixed** — pruning against a broken graph
risks deleting more objects. Note also that `refs/cline/checkpoints/*` holds 116 refs (from
the Cline extension), which is what generates most of the dangling-commit noise in
`git fsck` output.

---

## 19. Contact / References

- **GitHub:** `https://github.com/njoro1/translation-agent`
- **Hy-MT2 model:** `https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF`
- **SenseVoiceSmall GGUF:** `https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF`
- **fsmn-vad GGUF:** `https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF`
- **FunASR runtime:** GitHub releases tagged `runtime-llamacpp-v*`
- **Hy-MT2 translator skill:** `https://skillhub.cn/skills/hy-mt2-translator`
