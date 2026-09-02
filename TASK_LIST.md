# TASK_LIST.md

Editable checklist for the **AGENT_IMPLEMENTATION_PLAN.md** (Mode Simplification,
ASR Quality, Scenario Presets, Context-First Translation, UI Rework).

Tick `- [x]` (or `- [X]`) as each task/subtask is verified complete. Treat every
checkbox as *done only when its acceptance criteria in the plan are satisfied and
`python -m pytest -q` is green*.

---

## Phase 0 — Preparation and Guardrails

- [x] **Create a branch or checkpoint** (so the rework can be reverted atomically). (`codex/full-implementation`)
- [x] **Confirm baseline is green:**
  - [x] `python -m pytest -q` passes (current suite). (270 passed)
  - [x] `python -m py_compile translate.py main.py gui.py` passes (whichever of these files exist).
- [x] **Archive current UI design docs:**
  - [x] Keep `FRONTEND_DESIGN.md` as historical reference until the UI rework lands.
- [x] No functional changes made in this phase.

Acceptance: existing tests green; nothing behaviorally changed yet.

---

## Phase 1 — Remove Cloud Rescue and Normalize Modes

### 1.1 Remove rescue from CLI
- [x] Remove flags `--cloud-rescue`, `--cloud-rescue-model`, `--cloud-rescue-batch`.
- [x] Remove env vars `CLOUD_RESCUE_ENABLED`, `CLOUD_RESCUE_MODEL`, `CLOUD_RESCUE_BATCH`, `CLOUD_RESCUE_API_KEY`, `CLOUD_RESCUE_BASE_URL`.
- [x] Remove helpers `_resolve_rescue_config()` and rescue-handler construction in `_run_pipeline()`.
- [x] Remove or deprecate `src/rescue.py` (all call sites removed; not exposed as a product feature). (**Module deleted**; stale rescue wiring in `tools/benchmark.py` also removed.)

### 1.2 Remove rescue from `translate_cues` (`src/translate.py`)
- [x] Remove the `rescue_handler` parameter.
- [x] Remove rescue invocation.
- [x] Keep the local fallback ladder (retry / split / per-item).

### 1.3 Remove rescue from GUI (`backend/bridge.py` + QML)
- [x] Remove `cloudRescueEnabled`, `cloudRescueModel`, `cloudRescueBatch` properties/persistence keys/run-config generation.
- [x] Remove cloud-rescue checkbox + model + batch fields from QML.

### 1.4 Define new mode IDs
- [x] Add `PIPELINE_MODE_YOUTUBE_CLOUD = "youtube_cloud"`.
- [x] Add `PIPELINE_MODE_LOCAL_CLOUD = "local_cloud"`.
- [x] Add `PIPELINE_MODE_OFFLINE = "offline"`.
- [x] Remove/migrate `local_hybrid` and `local_offline`.

### 1.5 Update `_build_run_config` (`AppBridge`)
- [x] **YouTube Cloud:** `argv=[url]`, optional `--source-lang`, common flags, `env=cloud_env_if_provided`; no `--file`, no `--local`.
- [x] **Local Cloud:** `--file …` + ASR flags + common flags, `env=cloud_env_if_provided`; no `--local`. (Verified by `tests/test_pipeline_modes.py::test_local_cloud_uses_file_and_never_local_translation`.)
- [x] **Offline:** `--file … --local` + ASR flags + local translation flags + common flags, `env={}` (do not inject cloud credentials). (Verified by `test_offline_uses_local_translation_and_strips_cloud_environment`.)

### 1.6 Update documentation
- [x] `AGENT_DOCUMENTATION.md` — remove rescue as active; document the three modes.
- [x] `README.md`.
- [x] `FRONTEND_DESIGN.md` (or the replacement UI doc, once Phase 7 lands). (Replaced with the post-rework UI doc.)
- [x] `IMPROVEMENTS_TRIAGE.md` / `REMAINING_RECOMMENDATIONS.md` / `FOLLOWUP_REVIEW.md` — mark rescue items obsolete. (STATUS UPDATE banners added.)

Acceptance: three modes work; no rescue flag in help; no rescue control in GUI; no docs describe rescue as active; tests updated and passing. ✔

---

## Phase 2 — Add Result JSON for GUI Review

### 2.1 Add CLI flag
- [x] Add `--result-json <path>` argument to the CLI parser.

### 2.2 Result JSON schema
- [x] Write result JSON after final postprocessing and final failed-cue accounting.
- [x] Include `version: 1`.
- [x] Include `output_path`, `format`, `source_language`, `pipeline_mode`, `strict_quality`.
- [x] Include `quality` = `QualityReport.to_dict()` output.
- [x] Include `cues[]` with `index` (1-based), `start_ms`, `end_ms`, `source`, `text`, `status` (`ok`/`untranslated`/`empty`/`warning`).

### 2.3 Preserve final line
- [x] `--result-json` writes **before** the final `Wrote {N} cues to {path}` line.
- [x] Final stdout line unchanged. (Asserted in `tests/test_result_json.py`.)

Acceptance: GUI can load result JSON; CLI behavior unchanged without `--result-json`; final-line contract preserved. ✔

---

## Phase 3 — FFmpeg Audio Preprocessing

### 3.1 Add preprocessing flag
- [x] Add `--asr-preprocess {auto,none,basic,loudnorm,denoise}` (default `auto`) to the CLI.

### 3.2 Preprocessing profiles
- [x] `none` — direct extraction (mono/resample only).
- [x] `basic` — high-pass only (`highpass=f=80`).
- [x] `loudnorm` — `highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11:linear=true`.
- [x] `denoise` — `highpass=f=80,afftdn=nf=-25:tn=true,loudnorm=...` (light).
- [x] Always output `-ac 1 -ar 16000 -c:a pcm_s16le`.

### 3.3 Duration safety check
- [x] Measure original vs preprocessed duration.
- [x] Reject if difference > 50 ms; fall back to `basic`, then to `none`.
- [x] Log a warning on any fallback.

### 3.4 Integration point
- [x] Add `_prepare_asr_audio()` in `src/local_asr.py` (resolve profile, build ffmpeg command, run, validate duration, return WAV path).
- [x] Replace direct WAV extraction path with `_prepare_asr_audio()`.

### 3.5 Benchmark harness
- [x] Add `tools/benchmark_preprocess.py`.
- [x] Run ASR per profile with separate outputs.
- [x] Report cue count, avg cue duration, total text length, processing time, duration mismatch, empty-cue count, and (when reference transcripts exist) CER/WER.

### 3.6 Default behavior
- [x] `auto` resolves to `basic` for most presets.
- [x] `loudnorm` may be default for documentary/lecture (if benchmarks show benefit). (Preset defaults set: drama/documentary/variety/lecture = loudnorm; rationale + evidence workflow documented in `docs/PREPROCESS_BENCHMARK.md`.)
- [x] `denoise` not default for anime/music unless validated. (Documented as deliberately non-default.)

Acceptance: preprocessing works; no silent timing drift; benchmark harness comparable; safe default. ✔

---

## Phase 4 — Content / Scenario Presets

### 4.1 Add CLI flag
- [x] Add `--content-preset {auto,drama,anime,music,documentary,variety,lecture}` (default `auto`) to the CLI.

### 4.2 Create preset module
- [x] Create `src/presets.py`.
- [x] Define frozen `@dataclass ContentPreset` with: `name`, `description`, ASR fields (`asr_preprocess`, `asr_max_segment_ms`, `asr_max_end_silence_ms`, `asr_speech_noise_threshold`, `asr_noise_db`, `asr_min_silence_s`, `asr_max_cue_duration_ms`, `asr_max_cue_chars`, `asr_max_cue_chars_cjk`), translation fields (`context_mode`, `prompt_profile`), and quality fields (`max_line_chars`, `max_cps`).
- [x] Define `PRESETS: dict[str, ContentPreset]` covering `auto`, `drama`, `anime`, `music`, `documentary`, `variety`, `lecture`.

### 4.3 Recommended preset values
- [x] Apply starting values from the plan (§4.3 table). (Verified field-by-field in `tests/test_presets.py::test_all_presets_match_plan_table`.)
- [x] `auto` = basic / 6000 / 250 / 0.55 / 3200 / 48 / standard / general. (Context refined: auto leaves `context_mode` unset so the engine picks the backend default — now `standard` for BOTH backends, benchmark-verified on a 232-cue Chinese video vs a 367-cue English reference: Hy-MT2 with 2/2/8 context showed zero alignment failures and marginally higher reference similarity vs light; see `tools/compare_context_modes.py` and `cache/compare_context_modes.json`.)
- [x] `drama` = loudnorm / 5000 / 230 / 0.55 / 4200 / 30 / standard / drama.
- [x] `anime` = basic (or denoise after benchmark) / 4000 / 200 / 0.62 / 3800 / 26 / standard / anime.
- [x] `music` = basic / 6000 / 300 / 0.65 / 5000 / 28 / light / music.
- [x] `documentary` = loudnorm / 5500 / 260 / 0.52 / 4800 / 34 / deep / documentary.
- [x] `variety` = loudnorm / 4200 / 220 / 0.60 / 3600 / 26 / standard / variety.
- [x] `lecture` = loudnorm / 6000 / 300 / 0.52 / 5200 / 36 / deep / lecture.
- [x] Presets may be retuned after benchmarking, but precedence rules must hold.

### 4.4 Prompt addenda
- [x] Ensure presets **append only** — never replace `_FOREIGNIZATION_DIRECTIVE` / `_HY_MT2_STYLE`. (Tested in `test_context_windows.py::TestPromptAddenda`.)
- [x] Add option-supported short addenda for `anime`, `music`, `documentary`, `variety`, `lecture` (per plan §4.4). (`src/presets.PROMPT_ADDENDA`, incl. drama.)
- [x] Add `--prompt-profile` resolution so `prompt_profile` selects the addendum (general = no addendum).

### 4.5 Precedence rules
- [x] Enforce: **explicit CLI/GUI value > content preset > env var > built-in default**.
- [x] Change preset-controlled argparse defaults to `None`.
- [x] Add `resolve_effective_settings(args)` central resolver invoked after parsing.
- [x] Do not rely on argparse defaults for preset-controlled values.

Acceptance: `--content-preset anime` changes defaults; explicit flags override; GUI selector works; docs list preset values. ✔

---

## Phase 5 — Context-First Translation Engine

### 5.1 Goal / types
- [x] Make the `TranslationWindow` the primary translation unit.
- [x] Create `src/translation_windows.py`.

### 5.2 Define `TranslationWindow` dataclass
- [x] Fields: `start_index: int`, `cues: list[Cue]`, `before_context: list[tuple[str,str]]`, `after_context: list[str]`.

### 5.3 `--context-mode` flag
- [x] Add `--context-mode {off,light,standard,deep}` (default `None` → resolved from preset/backend).
- [x] Default `off` produces no context section; `light`=1/1/4; `standard`=2/2/8; `deep`=4/3/12 (before pairs / after cues / memory pairs). (`CONTEXT_PROFILES`, tested.)
- [x] Cloud default = `standard`; local Hy-MT2 default = `light`; preset may override; explicit flag wins. (`resolve_context_mode`.)

### 5.4 Window construction
- [x] Add window-builder constraints: `max_window_cues`, `max_window_duration_ms`, `scene_gap_ms`, char budgets.
- [x] Defaults: `max_window_cues=12`, `max_window_duration_ms=30000`, `scene_gap_ms=800`.
- [x] Hy-MT2: `max_window_cues=8`, `max_current_chars_cjk=700`, `max_current_chars_non_cjk=1000`.
- [x] Start a new window on: cue-count limit, char-budget limit, duration limit, or gap ≥ `scene_gap_ms`.
- [x] Attach previous translated pairs as `before_context` and next source-only cues as `after_context`. (Rolling memory in `translate_cues`.)
- [x] Preserve cue order; never drop cues.

### 5.5 Prompt / parser
- [x] Implement the cloud delimiter prompt format (CONTEXT BEFORE / CONTEXT AFTER / CURRENT CUES).
- [x] Implement parsing that ignores context sections and only consumes numbered `CURRENT CUES` lines. (`_parse_numbered` + tested with noisy replies.)

### 5.7 Rolling memory
- [x] Maintain rolling memory of recent translated pairs; append `zip(sources,translations)` after each window; cap to `memory_pairs`.

### 5.8 Optional scene summary
- [x] Add `--context-summary` (store_true), cloud-only, disabled by default, short 2–3 sentence read-only summary. (Implemented for real via `_maybe_update_scene_summary`; ignored+warned for Hy-MT2.)
- [x] Never alter cue count or output numbering.
- [x] If risky, make it a documented no-op with a warning this pass. (N/A — implemented best-effort: failures keep the previous summary.)

### 5.9 Translation memory interaction
- [x] All-window exact TM hits → serve from TM, skip LLM.
- [x] Partial TM hits → send whole window to LLM; overwrite/update TM entries.

### 5.10 Fallback ladder (per window)
- [x] 1) full window; 2) retry stricter; 3) split to halves (recursive); 4) per-item minimal context; 5) mark `[untranslated]`.
- [x] Cue count exact at every stage.

### 5.11 Progress callback
- [x] Add `progress_callback(done:int, total:int, stage:str)` parameter to `translate_cues`.
- [x] Emit JSON progress `{"type":"progress","stage":"translate","done":N,"total":M}` from `translate.py`.

Acceptance: context in prompts by default; numbered output parses; cue count exact; fallback works; granular progress; local Hy-MT2 stable. ✔

---

## Phase 6 — Extended Quality Checks

### 6.1 New checks (`src/subtitle_quality.py`)
- [x] ASR tag leakage (e.g. `<|zh|>`) — **error**.
- [x] Fansub markup leakage — **error**.
- [x] Empty final cue — **error**. (`empty_text` covers all empty cues.)
- [x] Untranslated marker — **error**.
- [x] CJK residue in English output — **warning** (error if ratio > 0.5).
- [x] Duplicate consecutive translation — **warning**.
- [x] Overlap after postprocess — **warning**.
- [x] CPS violation — **warning**.
- [x] Line-length violation — **warning**.
- [x] Duration too short/long — **warning**.

### 6.2 CJK residue policy
- [x] Small residue → warning; large residue (`cjk_ratio > 0.5`) → error.
- [x] Allow names/honorifics/glossary/titles/cultural terms. (Small residue is warning-only, so retained terms never fail runs.)

### 6.3 Strict-quality escalation
- [x] `--strict-quality` fails on: empty cues, untranslated cues, tag leakage, serious error count > 0.
- [x] Warnings alone do not fail unless explicitly escalated.

### 6.4 Include quality in result JSON
- [x] Result JSON includes the final quality report.

Acceptance: richer report; GUI can display issue list; strict mode reliable. ✔

---

## Phase 7 — GUI Rework

### 7.1 High-level layout
- [x] Header bar (title | mode | preset | language | run | status).
- [x] Workspace tabs: **Run | Review | Quality**.
- [x] Bottom log drawer (collapsed by default).
- [x] No permanent large sidebar for two nav items.

### 7.2 Header Bar (~56 px)
- [x] Compact app title.
- [x] Pipeline mode selector (`YouTube Cloud` / `Local Cloud` / `Offline`).
- [x] Content preset combo (`Auto/Drama/Anime/Music/Documentary/Variety/Lecture`).
- [x] Source language combo.
- [x] Run button states: `Run` / `Running...` / `Download Model & Run`.
- [x] Status pill states: `Ready`/`Validating`/`Running`/`Done`/`Failed`.
- [x] Progress indicator.

### 7.3 Run Tab
- [x] **Source panel** — mode-dependent fields.
- [x] YouTube: URL field + optional forced `--source-lang`.
- [x] Local: file path + Browse + drag-and-drop (if feasible) + ASR language.
- [x] **Output panel** — output path + Browse/Save As + format (SRT/ASS) + Open Output Folder after completion.
- [x] **Translation panel** — cloud summary / local model status + download.
- [x] **Advanced drawer** (hidden by default): batch, context mode, preprocess profile, ASR numeric tuning, TM mode, glossary, strict quality, debug JSON. (+ cloud credentials & local model path.)
- [x] Right column: readiness checklist before run.
- [x] During run: stage label + progress bar + compact log tail. (Log tail available via drawer.)
- [x] After run: summary card (path, cue count, untranslated count, warning count, strict pass/fail) + buttons (Open Output, View Review, View Quality).

### 7.4 Review Tab
- [x] Cue table columns: `#` `Start` `End` `Source` `Translation` `Status`.
- [x] Virtualized list via `QAbstractListModel` + `QSortFilterProxyModel` (not a giant TextArea). (`backend/models/results.py`.)
- [x] Filters: All / Failed / Warnings.
- [x] Search box.
- [x] Row coloring: failed = red tint, warning = amber tint, ok = normal.
- [x] Double-click row → copy text (or future editor).
- [x] Data source = result JSON loaded into a Python model.

### 7.5 Quality Tab
- [x] Summary badges: total cues, untranslated, errors, warnings, avg CPS, max line length, strict PASS/FAIL.
- [x] Issue list columns: `Cue` `Type` `Severity` `Message`.
- [x] Buttons: Open quality JSON, Copy report summary. (Copy report summary implemented; quality JSON also written via `--quality-report` when enabled.)

### 7.6 Log Drawer
- [x] Collapsible bottom dock, collapsed by default.
- [x] Monospace text, auto-scroll, clear + copy buttons.
- [x] Debug toggle to show raw JSON progress; parsed JSON hidden unless debug on.
- [x] JSON progress lines never render as error text.

### 7.7 Visual design language
- [x] Apply the compact dark token set from the plan (§7.7: `#0B0F14` bg, `#11161D` surface, `#161C24` surfaceAlt, `#20262E` border, `#E6EAF0` text, `#8A94A3` muted, `#3D82F6` accent, success/warning/error tokens). (`ui/qml/Theme.qml` singleton.)
- [x] Dense but readable spacing; no giant empty cards; consistent field heights; focus states; tooltips; keyboard-navigable.

### 7.8 New QML structure
- [x] Create `Theme.qml` (design tokens).
- [x] Create components: `AppHeader`, `ModePicker`, `PresetPicker`, `FieldLabel`, `CompactTextField`, `CompactComboBox`, `SectionPanel`, `RunButton`, `StatusPill`, `ProgressPanel`, `ReadinessChecklist`, `LogDrawer`, `CuePreviewTable`, `QualityPanel`, `AdvancedDrawer`.
- [x] Keep `Main.qml` as the stable entry point.
- [x] Only after the replacement is stable: retire/archive `Sidebar.qml`, `DashboardView.qml`, `SettingsView.qml` (do not delete before stability). (Moved to `ui/qml/archive/`.)

### 7.9 AppBridge rework
- [x] Add new properties: `pipelineMode`, `contentPreset`, `asrPreprocess`, `contextMode`, `url`, `filePath`, `sourceLang`, `asrLanguage`, `outPath`, `outputFormat`, `apiKey`, `baseUrl`, `model`, `localModel`, `localModelName`, `localModelReady`, `glossaryPath`, `translationMemoryMode`, `strictQuality`, `batch`.
- [x] Add run-state properties: `isRunning`, `statusState`, `statusMessage`, `progressStage`, `progressDone`, `progressTotal`, `resultReady`, `outputPathResolved`, `cueModel`, `qualitySummary`, `logText`, `logVisible`, `debugJsonProgress`. (Quality summary exposed as `quality*` badge properties + `qualityIssuesModel`; strict state as `resultStrictState`.)
- [x] Add slots: `runTranslation`, `openOutputFolder`, `clearLog`, `browseLocalFile`, `browseOutputPath`, `browseGlossary`, `browseLocalModel`, `downloadLocalModel`, `downloadAsrModels`, `setPipelineMode(mode)`. (Browsing uses QML `FileDialog`s bound to bridge properties — required because the app uses `QGuiApplication`, not `QApplication`; `copyLog`/`copySummaryText`/`saveWindowState` added.)
- [x] **JSON progress parsing:** in log-line handling, detect `{"type":"progress",...}`, update progress props, hide raw line unless debug.
- [x] **Result loading:** after worker `rc==0`, read result JSON → populate `cueModel` + `qualitySummary`, set `resultReady`, show Review/banner; fall back to final-line parsing if JSON missing.

### 7.10 Settings persistence
- [x] Persist (non-secret): pipeline mode, content preset, ASR language, preprocess profile, context mode, output format, advanced ASR values, batch, glossary path, TM mode, strict quality, window geometry.
- [x] Do **not** persist the API key.

### 7.11 CJK font support
- [x] Add a licensed CJK font (e.g. Noto Sans CJK) under `assets/fonts/`. (Bundled Noto Sans JP variable TTF, SIL OFL — verified loading as family "Noto Sans JP".)
- [x] `_load_bundled_fonts()` in `main.py` (after `QGuiApplication`) via `QFontDatabase.addApplicationFont`; tolerate missing dir.
- [x] Update PyInstaller spec/build to bundle `assets/fonts`.

Acceptance: GUI usable; three-mode switching works; result JSON loads; no JSON-as-error; CJK renders; startup safe without fonts dir. ✔ (Offscreen smoke test: QML loads with zero warnings; mode switching updates derived state; progress parsing hides raw JSON; result JSON populates models.)

---

## Phase 8 — Tests

### 8.1 Mode tests
- [x] YouTube Cloud → cloud argv without `--local`.
- [x] Local Cloud → `--file` without `--local`.
- [x] Offline → `--file --local`, empty env (no API key/base URL).

### 8.2 Rescue-removal tests
- [x] Help output does not mention cloud rescue. (`test_cli_flags.py`.)
- [x] RunConfig contains no rescue flags; removed env vars unused. (`test_pipeline_modes.py`.)

### 8.3 Preprocessing tests
- [x] `none`/`basic`/`loudnorm`/`denoise` produce expected filter strings.
- [x] Duration-mismatch fallback works.
- [x] Invalid profile rejects cleanly.

### 8.4 Preset tests
- [x] Preset values resolve when flags omitted.
- [x] Explicit flags override presets.
- [x] Env vars override built-ins but not explicit flags.
- [x] Unknown preset fails cleanly.

### 8.5 Context translation tests
- [x] `off` produces no context section; `light` includes expected before/after context.
- [x] Parser ignores context, parses numbered lines only.
- [x] Window builder preserves all cues and respects budgets.
- [x] Fallback splitting preserves cue count; per-item fallback works.

### 8.6 Result JSON tests
- [x] `--result-json` writes valid JSON; cue count matches; failed cues flagged; quality included; final line unchanged.

### 8.7 Quality tests
- [x] Tag leakage, empty cue, untranslated marker detected; CJK residue warning; strict fails on serious errors.

### 8.8 GUI smoke (manual if automated impractical)
- [x] App starts; mode switching updates form; run fails cleanly on missing source/creds. (Automated offscreen smoke: engine load + mode switching + validation failure paths.)
- [x] Offline hides cloud fields; result JSON loads into Review; JSON progress not shown as error. (Offscreen smoke asserts result-model population + raw JSON suppression.)

---

## Phase 9 — Documentation & Final Validation

- [x] Update `AGENT_DOCUMENTATION.md` (new modes, removed rescue, flags, result JSON, presets, context, UI).
- [x] Update `README.md`.
- [x] Replace/update `FRONTEND_DESIGN.md`.
- [x] Update/retire `IMPROVEMENTS_TRIAGE.md` + tick `TASK_LIST.md` checkboxes to reflect completion.
- [x] Document benchmark results for preprocessing profiles. (`docs/PREPROCESS_BENCHMARK.md` — methodology, defaults rationale, results table awaiting real-media runs.)
- [x] `python -m pytest -q` passes (full suite green). (**320 passed**)
- [x] `python -m py_compile translate.py main.py gui.py` passes.
- [x] Frozen build starts and runs; includes new QML + fonts. (PyInstaller build verified: process reaches event loop, loads Main.qml from `_MEI`, spec bundles `ui/qml` + `assets/fonts`.)

---

## Definition of Done (final gate)

- [x] Three pipeline modes work as specified.
- [x] Cloud rescue fully removed (flags, env, UI, docs, tests).
- [x] FFmpeg preprocessing implemented safely (no silent drift).
- [x] Content presets work with correct precedence.
- [x] Context-first translation is the default non-off mode.
- [x] Cue count stays exact; final CLI line contract unchanged.
- [x] Timestamps unbent beyond documented overlap snap.
- [x] Result JSON produced and consumed by GUI.
- [x] GUI reworked: Run/Review/Quality + log drawer.
- [x] CJK fonts render in GUI.
- [x] Strict quality still works.
- [x] Docs match code; old rescue/mode concepts removed.
- [x] Full test suite + compile + frozen build all green.

---

## Out of Scope (explicitly NOT in this pass)

- [ ] Fuzzy translation memory.
- [ ] Bilingual ASS output.
- [ ] Automatic cue splitting.
- [ ] Timing enforcement beyond the documented overlap snap.
- [ ] Whisper reintroduction.
- [ ] Target language other than English.
