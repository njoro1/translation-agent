# AGENT_IMPLEMENTATION_PLAN.md

## Full Implementation Plan: Translation Agent - Mode Simplification, ASR Quality, Scenario Presets, Context-First Translation, and UI Rework

This document is the authoritative implementation plan for the next major pass.

It covers:

1. Current state analysis.
2. Remaining work from previous reviews.
3. New product requirements.
4. Research-backed design decisions.
5. Detailed implementation instructions.
6. Acceptance criteria.
7. Test and documentation requirements.

The implementation agent should treat this as a complete brief, not a suggestion list.

---

# 1. Current State Summary

## 1.1 What has already been done

The project is already structurally strong.

Implemented and verified:

- CLI pipeline:
  - YouTube subtitle fetching.
  - Local ASR via FunASR/SenseVoiceSmall.
  - Cloud or local llama.cpp translation.
  - SRT and ASS output.
  - Quality report and strict-quality mode.
  - JSON progress output via `--json-progress`.
- Translation robustness:
  - Numbered-item protocol.
  - Batch fallback ladder.
  - Per-item fallback.
  - Translation memory.
  - Glossary support.
- CJK improvements:
  - `src/cjk.py`.
  - Script-ratio language detection.
  - Kinsoku line breaking helper.
  - ASS CJK font selection.
- Correctness fixes:
  - Transactional environment mutation around local mode.
  - Translation memory closure on failure paths.
  - Final failed-cue accounting after postprocessing.
  - Source-language precedence improvements.
  - `[untranslated]` marker protection.
- GUI:
  - PySide6/QML shell.
  - `AppBridge` state object.
  - Background worker execution.
  - Settings persistence.
  - Model download flow.
  - Log streaming from CLI stdout/stderr.

## 1.2 What remains from previous reviews

The previous remaining backlog included:

- ASR presets/profiles.
- Translation context.
- Extended CJK quality checks.
- GUI consumption of JSON progress.
- Granular translation progress.
- Bundled CJK fonts.
- Cue preview table.
- Quality panel.
- UI polish.

This plan absorbs those items into a larger rework.

The following previous backlog items remain explicitly out of scope unless stated otherwise:

- Fuzzy translation memory.
- Bilingual ASS output.
- Automatic cue splitting.
- Timing enforcement that changes timestamps beyond the documented overlap snap.
- Whisper reintroduction.
- Target language other than English.

---

# 2. New Product Requirements

The user has requested five major changes.

## Requirement 1: Simplify pipeline modes and remove cloud rescue

There should be exactly three user-facing pipeline options:

1. **YouTube ? Cloud**
   - Fetch YouTube subtitles.
   - Translate with cloud LLM.

2. **Local File ? Cloud**
   - Transcribe local media locally using FunASR/SenseVoiceSmall.
   - Translate with cloud LLM.

3. **Local File ? Fully Offline**
   - Transcribe local media locally.
   - Translate using local llama.cpp model.
   - No cloud translation.

Cloud rescue must be abandoned.

There must be no mixed mode where local translation silently falls back to cloud rescue. The user chooses either cloud translation or local translation.

## Requirement 2: Implement FFmpeg preprocessing if it improves ASR

The first step, ASR, must be maximized. If FFmpeg preprocessing improves ASR output quality without damaging timing or speech, implement it.

This must be evidence-driven:

- Add preprocessing profiles.
- Benchmark them.
- Use a safe default.
- Avoid filters that introduce timing drift or speech artifacts.

## Requirement 3: Add scenario presets

Add content presets such as:

- drama,
- anime,
- music,
- documentary,
- variety,
- lecture,
- auto.

Each preset should tune:

- ASR/VAD behavior.
- FFmpeg preprocessing.
- Translation context level.
- Prompt style addendum.
- Quality thresholds where appropriate.

## Requirement 4: Replace cue-isolated translation with context-first translation

The current approach of translating cues as isolated or weakly contextualized batches is insufficient for CJK.

Context must become a first-class part of translation:

- Pronouns must be resolved more reliably.
- Speaker continuity must improve.
- Scene context must be preserved.
- Named entities and honorifics must remain consistent.
- Cue alignment must remain perfect.

The numbered-item protocol must remain because it protects cue count alignment.

## Requirement 5: Completely rework the UI

The current UI wastes space and contains redundancies.

The UI must be reworked from the ground up with:

- a compact professional layout,
- clear mode selection,
- preset-driven operation,
- visible progress,
- result review,
- quality inspection,
- log access without log domination,
- no redundant settings panes.

The implementation agent has full authority over UI/UX design within the constraints of PySide6, QML, and existing backend invariants.

---

# 3. Non-Negotiable Invariants

The following invariants remain binding unless this document explicitly changes one.

## 3.1 Cue count in == cue count out

Never drop, merge, duplicate, or reorder cues.

The final subtitle file must contain the same number of cues as the fetched or ASR-generated source.

## 3.2 Numbered-item protocol remains the alignment mechanism

The LLM must return numbered translations corresponding exactly to the current cue block.

Context may be added around the block, but the parseable output must remain numbered lines.

## 3.3 Target language remains English

This project translates into English only.

Do not add target-language selection in this pass.

## 3.4 Original timestamps are sacred except documented overlap snap

Do not retime cues except the already documented overlap snap behavior.

Do not implement automatic cue splitting in this pass.

## 3.5 Final CLI line contract remains unchanged

The final line of CLI output must remain exactly:

```text
Wrote {N} cues to {path}
```

The GUI relies on this.

## 3.6 Foreignization directive remains intact

Do not replace or weaken `_FOREIGNIZATION_DIRECTIVE` or `_HY_MT2_STYLE`.

Content presets may append carefully scoped addenda, but must not replace the core translation philosophy.

## 3.7 Cloud rescue is removed

All cloud rescue behavior, flags, environment variables, UI controls, documentation, and tests must be removed or explicitly deprecated as removed.

---

# 4. Research Summary and Design Rationale

This plan is based on established best practices for subtitle pipelines, ASR preprocessing, LLM context handling, and desktop QML UX.

## 4.1 FFmpeg preprocessing for ASR

Best practices:

- ASR models generally expect consistent sample rate and channel layout.
- 16 kHz mono PCM is the standard safe input for many speech models.
- High-pass filtering around 60-100 Hz can remove rumble, HVAC noise, and low-frequency music energy without harming speech.
- Loudness normalization can help quiet dialogue, but aggressive dynamic processing can pump background music or introduce artifacts.
- Denoising can help, but consumer-grade FFmpeg denoisers may damage fricatives, breaths, and high-frequency CJK consonant cues.
- Any filter that changes duration can shift subtitle timestamps and must be rejected or compensated.

Design conclusion:

- Implement preprocessing as opt-in profiles.
- Use a conservative default.
- Validate duration before accepting preprocessed audio.
- Benchmark against unprocessed audio.
- Do not use aggressive noise removal by default.

## 4.2 Scenario presets

Different media types need different segmentation and translation behavior.

Examples:

- Drama: dialogue-focused, moderate pacing.
- Anime: background music, sound effects, honorifics, songs, rapid exchanges.
- Music: singing is hard for ASR; longer phrasing and looser segmentation may be necessary.
- Documentary: narration, formal register, longer sentences.
- Variety: laughter, applause, overlapping speech.
- Lecture: long monologues, stable speaker, longer cues acceptable.

Design conclusion:

Create a `ContentPreset` object that controls multiple subsystems at once.

Presets should be defaults, not hard locks. Explicit user flags must override preset values.

## 4.3 Context-first translation

Subtitle translation fails when cues are translated in isolation, especially for CJK languages where subjects, objects, and pronouns are often omitted.

Best practices:

- Translate in coherent windows, not isolated cues.
- Provide previous source and previous final translation as read-only context.
- Provide upcoming source text as read-only context.
- Require the model to translate only the current numbered block.
- Keep a rolling memory of recent translated pairs.
- Optionally maintain a concise scene/state summary for cloud models.
- Fall back to smaller windows and per-cue translation if alignment fails.

Design conclusion:

Replace batch-only translation with a **context window engine** while preserving the numbered-item protocol.

The primary unit becomes a `TranslationWindow`, not a raw batch.

## 4.4 UI/UX

Modern desktop tool UX principles:

- Use progressive disclosure.
- Keep primary controls visible.
- Hide advanced settings behind a drawer or popover.
- Make results, not logs, the center of the experience.
- Use presets to reduce configuration burden.
- Avoid large permanent sidebars for only two navigation items.
- Use dense but readable spacing.
- Provide clear run states: ready, validating, running, succeeded, failed.
- Make failures actionable.

Design conclusion:

Remove the current sidebar/dashboard/settings split.

Replace it with:

- a top command bar,
- a compact run workspace,
- a review/quality workspace,
- a collapsible log drawer.

---

# 5. Target Pipeline Modes

## 5.1 Mode definitions

| UI Mode | Internal ID | Input | ASR | Translation | Requires API Key | Requires Local Translation Model |
|---|---|---|---:|---:|---:|---:|
| YouTube ? Cloud | `youtube_cloud` | YouTube URL | No | Cloud | Yes | No |
| Local File ? Cloud | `local_cloud` | Local media file | Yes | Cloud | Yes | No |
| Local File ? Offline | `offline` | Local media file | Yes | Local | No | Yes |

## 5.2 CLI mapping

The existing CLI can express these modes cleanly:

| UI Mode | CLI shape |
|---|---|
| YouTube ? Cloud | `python translate.py URL` |
| Local File ? Cloud | `python translate.py --file media.mp4` |
| Local File ? Offline | `python translate.py --file media.mp4 --local` |

No rescue flags should be used.

## 5.3 GUI behavior rules

### YouTube Cloud

Show:

- URL field.
- source language selector.
- output format.
- output path.
- content preset.
- cloud settings if API key/base URL/model missing.

Hide:

- local file picker.
- ASR options.
- local model options.

### Local Cloud

Show:

- local file picker/drop area.
- ASR language.
- content preset.
- preprocessing profile.
- output format.
- output path.
- cloud settings if needed.

Hide:

- URL field.
- local translation model controls.

### Offline

Show:

- local file picker/drop area.
- ASR language.
- content preset.
- preprocessing profile.
- local translation model status.
- output format.
- output path.

Hide:

- URL field.
- cloud API fields.
- cloud rescue controls.

Offline mode must not pass cloud credentials into the pipeline.

---

# 6. Implementation Phases

The agent should implement in this order.

## Phase 0: Preparation and Guardrails

Tasks:

1. Create a branch or checkpoint.
2. Run:
   ```bash
   python -m pytest -q
   python -m py_compile translate.py main.py gui.py
   ```
3. Confirm the current suite is green.
4. Archive current UI design docs if needed:
   - keep `FRONTEND_DESIGN.md` as historical reference until replaced.

Acceptance:

- Existing tests pass.
- No functional changes yet.

---

## Phase 1: Remove Cloud Rescue and Normalize Modes

### 1.1 Remove rescue from CLI

Remove or delete:

CLI flags:

```text
--cloud-rescue
--cloud-rescue-model
--cloud-rescue-batch
```

Environment variables:

```text
CLOUD_RESCUE_ENABLED
CLOUD_RESCUE_MODEL
CLOUD_RESCUE_BATCH
CLOUD_RESCUE_API_KEY
CLOUD_RESCUE_BASE_URL
```

Functions/helpers:

```python
_resolve_rescue_config()
rescue_handler construction in _run_pipeline()
```

Optional module deletion:

```text
src/rescue.py
```

If deleting `src/rescue.py` is too invasive in one pass, the agent may first deprecate it by removing all call sites and marking it unused, but the final state should not expose rescue as a product feature.

### 1.2 Remove rescue from `translate_cues`

Update `src/translate.py`:

- Remove `rescue_handler` parameter if present.
- Remove rescue invocation.
- Keep fallback ladder:
  - retry,
  - split,
  - per-item.

The fallback ladder remains local to the selected backend.

### 1.3 Remove rescue from GUI

Remove from `backend/bridge.py`:

- `cloudRescueEnabled`
- `cloudRescueModel`
- `cloudRescueBatch`
- rescue-related persistence keys
- rescue-related run-config generation

Remove from QML:

- cloud rescue checkbox
- rescue model field
- rescue batch field

### 1.4 Define new mode IDs

Replace old mode concepts with:

```python
PIPELINE_MODE_YOUTUBE_CLOUD = "youtube_cloud"
PIPELINE_MODE_LOCAL_CLOUD = "local_cloud"
PIPELINE_MODE_OFFLINE = "offline"
```

Remove or migrate:

```text
local_hybrid
local_offline
```

### 1.5 Update RunConfig generation

`AppBridge._build_run_config()` must produce:

#### YouTube Cloud

```python
argv = [url]
if source_lang: argv += ["--source-lang", source_lang]
argv += common_flags
env = cloud_env_if_provided
```

No `--file`, no `--local`.

#### Local Cloud

```python
argv = ["--file", file_path]
argv += asr_flags
argv += common_flags
env = cloud_env_if_provided
```

No `--local`.

#### Offline

```python
argv = ["--file", file_path, "--local"]
argv += asr_flags
argv += local_translation_flags
argv += common_flags
env = {}  # do not inject cloud credentials
```

### 1.6 Update documentation

Update:

- `AGENT_DOCUMENTATION.md`
- `README.md`
- `FRONTEND_DESIGN.md` or replacement UI doc
- any triage/remaining recommendations docs

Remove all references to cloud rescue as an active feature.

Acceptance:

- Three modes work.
- No rescue flag appears in help.
- No rescue control appears in GUI.
- No docs describe rescue as active.
- Tests updated and passing.

---

## Phase 2: Add Result JSON for GUI Review

The GUI needs structured output, not just log parsing.

### 2.1 Add CLI flag

Add:

```python
parser.add_argument(
    "--result-json",
    help="Write a machine-readable JSON result file for GUI review.",
)
```

This flag is primarily for the GUI but may also be useful for tooling.

### 2.2 Result JSON schema

Write this after final postprocessing and final failed-cue accounting.

Schema:

```json
{
  "version": 1,
  "output_path": "output.srt",
  "format": "srt",
  "source_language": "ja",
  "pipeline_mode": "local_cloud",
  "strict_quality": false,
  "quality": {},
  "cues": [
    {
      "index": 1,
      "start_ms": 1000,
      "end_ms": 2500,
      "source": "original text",
      "text": "translated text",
      "status": "ok"
    }
  ]
}
```

Fields:

- `index`: 1-based cue index.
- `start_ms`: integer milliseconds.
- `end_ms`: integer milliseconds.
- `source`: original cue text.
- `text`: final output text.
- `status`: one of:
  - `ok`
  - `untranslated`
  - `empty`
  - `warning`

`quality` should contain the same structure produced by `QualityReport.to_dict()`.

### 2.3 Preserve final line

The final stdout line must still be:

```text
Wrote {N} cues to {path}
```

The result JSON must be written before that final line.

Acceptance:

- GUI can load result JSON.
- CLI behavior unchanged when `--result-json` is not supplied.
- Final line contract preserved.

---

## Phase 3: FFmpeg Audio Preprocessing

Goal: improve ASR input quality without damaging timing.

### 3.1 Add preprocessing flag

Add:

```python
parser.add_argument(
    "--asr-preprocess",
    choices=["auto", "none", "basic", "loudnorm", "denoise"],
    default="auto",
    help="FFmpeg preprocessing applied before ASR.",
)
```

### 3.2 Preprocessing profiles

Recommended definitions:

| Profile | Purpose | Filter chain |
|---|---|---|
| `none` | Direct extraction | no extra filters beyond mono/resample |
| `basic` | Safe default | high-pass only |
| `loudnorm` | Quiet/uneven dialogue | high-pass + EBU R128 loudness normalization |
| `denoise` | Noisy/BGM sources | high-pass + light denoise + loudnorm |
| `auto` | Use content preset's preferred profile | resolved later |

Suggested FFmpeg chains:

```text
basic:
highpass=f=80

loudnorm:
highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11:linear=true

denoise:
highpass=f=80,afftdn=nf=-25:tn=true,loudnorm=I=-16:TP=-1.5:LRA=11:linear=true
```

Always output:

```text
-ac 1
-ar 16000
-c:a pcm_s16le
```

### 3.3 Duration safety check

Before using the preprocessed WAV:

1. Measure original duration.
2. Measure preprocessed duration.
3. If difference exceeds 50 ms, reject the preprocessed file.
4. Fall back to `basic`.
5. If `basic` also drifts, fall back to `none`.
6. Log a warning.

Do not accept preprocessing that shifts timestamps.

### 3.4 Integration point

Modify `src/local_asr.py`:

- Replace direct WAV extraction with:
  ```python
  _prepare_asr_audio()
  ```
- This function should:
  - resolve effective preprocessing profile,
  - build FFmpeg command,
  - run it,
  - validate duration,
  - return the WAV path to use.

### 3.5 Benchmark harness

Add:

```text
tools/benchmark_preprocess.py
```

It should:

- run ASR over benchmark media using each preprocessing profile,
- keep outputs separate,
- report:
  - cue count,
  - average cue duration,
  - total text length,
  - processing time,
  - duration mismatch,
  - obvious empty cue count.

If reference transcripts exist, also report CER/WER.

### 3.6 Default behavior

Until benchmark evidence says otherwise:

- `auto` should resolve to `basic` for most presets.
- `loudnorm` may be default for documentary/lecture if benchmarks show benefit.
- `denoise` should not be default for anime/music unless benchmarks and listening tests confirm it helps.

Acceptance:

- Preprocessing flag works.
- No timing drift is accepted silently.
- Benchmark harness produces comparable outputs.
- Default preprocessing is safe.

---

## Phase 4: Content/Scenario Presets

Goal: provide one high-level control that tunes the whole pipeline.

### 4.1 Add CLI flag

Add:

```python
parser.add_argument(
    "--content-preset",
    choices=["auto", "drama", "anime", "music", "documentary", "variety", "lecture"],
    default="auto",
    help="Scenario preset controlling ASR, preprocessing, context, and prompt style.",
)
```

### 4.2 Create preset module

Create:

```text
src/presets.py
```

Define:

```python
@dataclass(frozen=True)
class ContentPreset:
    name: str
    description: str

    # ASR/preprocessing
    asr_preprocess: str
    asr_max_segment_ms: int
    asr_max_end_silence_ms: int
    asr_speech_noise_threshold: float
    asr_noise_db: float
    asr_min_silence_s: float
    asr_max_cue_duration_ms: int
    asr_max_cue_chars: int
    asr_max_cue_chars_cjk: int

    # Translation
    context_mode: str
    prompt_profile: str

    # Quality
    max_line_chars: int
    max_cps: float
```

### 4.3 Recommended preset values

These are starting values. The agent may tune them after benchmarking, but must preserve the precedence rules.

| Preset | preprocess | max segment ms | end silence ms | speech/noise | max cue duration ms | max CJK chars | context mode | prompt profile |
|---|---|---:|---:|---:|---:|---:|---|---|
| auto | basic | 6000 | 250 | 0.55 | 3200 | 48 | standard | general |
| drama | loudnorm | 5000 | 230 | 0.55 | 4200 | 30 | standard | drama |
| anime | basic or denoise after benchmark | 4000 | 200 | 0.62 | 3800 | 26 | standard | anime |
| music | basic | 6000 | 300 | 0.65 | 5000 | 28 | light | music |
| documentary | loudnorm | 5500 | 260 | 0.52 | 4800 | 34 | deep | documentary |
| variety | loudnorm | 4200 | 220 | 0.60 | 3600 | 26 | standard | variety |
| lecture | loudnorm | 6000 | 300 | 0.52 | 5200 | 36 | deep | lecture |

### 4.4 Prompt addenda

Presets must not replace the foreignization directive.

They may append short addenda.

Examples:

```text
anime:
Preserve honorifics and culturally specific address terms unless glossary says otherwise.
Be careful with songs, sound effects, and abrupt speaker changes.

music:
The source may be sung lyrics. Preserve emotional meaning and line rhythm.
Do not over-explain. Prefer concise singable phrasing when possible.

documentary:
Use formal, clear narration-style English.
Avoid slang and overly casual phrasing.

variety:
Preserve rapid conversational tone, reactions, and humor.
Do not flatten energetic speech into formal prose.

lecture:
Prefer precise terminology and complete sentences.
Maintain instructional clarity.
```

### 4.5 Precedence rules

Precedence must be:

```text
explicit CLI/GUI value
> content preset value
> environment variable
> built-in default
```

To implement this cleanly:

- Change preset-controlled argparse defaults to `None`.
- After parsing, resolve each value through a central function:
  ```python
  resolve_effective_settings(args)
  ```
- Do not rely on argparse defaults for preset-controlled values.

Acceptance:

- `--content-preset anime` changes defaults.
- Explicit flags override preset values.
- GUI preset selector works.
- Docs list preset values.

---

## Phase 5: Context-First Translation Engine

This is the most important translation-quality change.

### 5.1 Goal

Replace isolated batch translation with context-aware translation windows.

The new primary translation unit is:

```python
TranslationWindow
```

not a simple batch.

### 5.2 New module

Create:

```text
src/translation_windows.py
```

Define:

```python
@dataclass
class TranslationWindow:
    start_index: int
    cues: list[Cue]
    before_context: list[tuple[str, str]]  # (source, translation)
    after_context: list[str]               # source only
```

### 5.3 Context modes

Add CLI flag:

```python
parser.add_argument(
    "--context-mode",
    choices=["off", "light", "standard", "deep"],
    default=None,
    help="Context level for translation windows.",
)
```

If omitted, resolve from preset and backend:

- Cloud default: `standard`.
- Local Hy-MT2 default: `light`.
- Preset may override.
- Explicit flag overrides all.

Suggested profiles:

| Mode | Before pairs | After cues | Memory pairs | Use case |
|---|---:|---:|---:|---|
| off | 0 | 0 | 0 | debugging / compatibility |
| light | 1 | 1 | 4 | local small models |
| standard | 2 | 2 | 8 | normal cloud/local |
| deep | 4 | 3 | 12 | cloud long-form content |

### 5.4 Window construction

Create windows using these constraints:

- maximum current cues,
- maximum current characters,
- maximum window duration,
- gap-based scene breaks.

Suggested defaults:

```python
max_window_cues = 12
max_window_duration_ms = 30000
scene_gap_ms = 800
```

For Hy-MT2, reduce:

```python
max_window_cues = 8
max_current_chars_cjk = 700
max_current_chars_non_cjk = 1000
```

For cloud, allow larger budgets but still cap prompt size.

Window construction rules:

1. Preserve cue order.
2. Never drop cues.
3. Start a new window when:
   - current cue count exceeds limit,
   - current character budget exceeds limit,
   - cumulative duration exceeds limit,
   - gap before current cue exceeds `scene_gap_ms`.
4. Attach previous translated pairs as `before_context`.
5. Attach next source-only cues as `after_context`.

### 5.5 Prompt format for cloud models

Use a strict delimiter format.

Example:

```text
CONTEXT BEFORE (already translated; read only; do not translate):
- {source} => {translation}
- {source} => {translation}

CONTEXT AFTER (source only; read only; do not translate):
- {source}
- {source}

CURRENT CUES (translate exactly {N} numbered lines):
1. {source}
2. {source}
3. {source}

Return only the numbered English translations for CURRENT CUES.
Do not repeat context.
Do not include labels.
Do not change numbering.
```

The parser must only accept output lines matching the numbered protocol.

### 5.6 Prompt format for Hy-MT2

Preserve the existing Hy-MT2 style instruction, but add minimal context.

Example:

```text
?????(????):
??:
- {source} => {translation}
??:
- {source}

?????????,????,?????:
1. {source}
2. {source}
```

For Hy-MT2:

- keep context smaller,
- avoid long summaries,
- avoid JSON,
- keep numbered output exact.

### 5.7 Rolling memory

Maintain a rolling memory of recently translated cue pairs.

After each successful window:

```python
memory.extend(zip(window_sources, window_translations))
memory = memory[-memory_pairs:]
```

This memory feeds `before_context` for subsequent windows.

### 5.8 Optional cloud scene summary

Add optional flag:

```python
parser.add_argument(
    "--context-summary",
    action="store_true",
    help="Maintain a rolling scene summary for cloud translation context.",
)
```

Rules:

- Cloud only.
- Disabled by default initially.
- Must not be used for Hy-MT2 unless explicitly validated.
- Summary must be short, e.g. 2-3 sentences.
- Summary must be included as read-only context.
- Summary generation must never alter cue count or output numbering.

If implementation risk is high, make this flag a no-op with a warning in this pass.

### 5.9 Translation memory interaction

To preserve context quality:

- If all cues in a window are exact TM hits, use TM and skip LLM.
- If only some cues are TM hits, send the whole window to the LLM and overwrite/update TM with the new translations.
- Exact repeated lines may still be served from TM if the implementation can prove no context loss, but when in doubt, prefer context.

### 5.10 Fallback ladder

For each window:

1. Attempt full window translation.
2. If parsing fails:
   - retry with stricter instruction,
   - split window into halves,
   - recursively continue.
3. If a single cue fails:
   - translate per-item with minimal context.
4. If still failed:
   - mark `[untranslated]`.

Cue count must remain exact at every stage.

### 5.11 Progress callback

Add progress support to translation:

```python
def translate_cues(
    ...,
    progress_callback=None,
):
```

Callback signature:

```python
progress_callback(done: int, total: int, stage: str)
```

`translate.py` should use this to emit JSON progress:

```json
{"type":"progress","stage":"translate","done":48,"total":420}
```

Acceptance:

- Context is present in prompts by default.
- Numbered output still parses.
- Cue count remains exact.
- Fallback works.
- Progress is granular.
- Local Hy-MT2 remains stable.

---

## Phase 6: Extended Quality Checks

Extend `src/subtitle_quality.py`.

### 6.1 New checks

Add warnings/errors for:

| Check | Default severity |
|---|---|
| ASR tag leakage, e.g. `<\|zh\|>` | error |
| Fansub markup leakage | error |
| Empty final cue | error |
| Untranslated marker | error |
| CJK residue in English output | warning |
| Duplicate consecutive translation | warning |
| Overlap after postprocess | warning |
| CPS violation | warning |
| Line-length violation | warning |
| Duration too short/long | warning |

### 6.2 CJK residue policy

CJK residue should not automatically be fatal.

Allowed cases may include:

- names,
- honorifics,
- glossary terms,
- titles,
- cultural terms.

Default:

- small residue: warning.
- large residue: error in strict mode.

Suggested heuristic:

```python
if cjk_ratio > 0.5:
    error
else:
    warning
```

### 6.3 Strict quality escalation

`--strict-quality` should fail on:

- empty cues,
- untranslated cues,
- tag leakage,
- serious error count > 0.

Warnings alone should not fail unless explicitly escalated.

### 6.4 Include quality in result JSON

The result JSON must include the final quality report.

Acceptance:

- Quality report is richer.
- GUI can display issue list.
- Strict mode remains reliable.

---

## Phase 7: GUI Rework

This is a full UI replacement.

The new UI should feel like a professional desktop subtitle tool, not a settings dashboard.

---

## 7.1 High-level layout

```text
+----------------------------------------------------------------------------------+
| Header Bar                                                                       |
| App title | Mode Selector | Content Preset | Language | Run Button | Status      |
+----------------------------------------------------------------------------------+
| Workspace Tabs: Run | Review | Quality                                           |
+----------------------------------------------------------------------------------+
| Run Tab                                                                          |
| +----------------------+ +------------------------------------------------------+ |
| | Source Panel         | | Status / Progress / Result Placeholder               | |
| | Output Panel         | |                                                      | |
| | Translation Panel    | |                                                      | |
| | Advanced Drawer      | |                                                      | |
| +----------------------+ +------------------------------------------------------+ |
+----------------------------------------------------------------------------------+
| Bottom Dock: Log Drawer (collapsed by default)                                   |
+----------------------------------------------------------------------------------+
```

Do not use a permanent large sidebar.

---

## 7.2 Header Bar

Height: ~56 px.

Contents:

- compact app title,
- pipeline mode selector,
- content preset combo,
- source language combo,
- Run button,
- status pill,
- progress indicator.

Mode selector labels:

```text
YouTube Cloud
Local Cloud
Offline
```

Preset combo labels:

```text
Auto
Drama
Anime
Music
Documentary
Variety
Lecture
```

Run button states:

```text
Run
Running...
Download Model & Run
```

Status pill states:

```text
Ready
Validating
Running
Done
Failed
```

---

## 7.3 Run Tab

The Run tab is the default view.

### Left column: configuration

Width: 380-440 px.

Sections:

#### Source

Mode-dependent fields.

YouTube Cloud:

- URL field.
- optional forced source language.

Local Cloud / Offline:

- file path field,
- Browse button,
- drag-and-drop support if feasible,
- ASR language combo.

#### Output

- output path field,
- Browse/Save As button,
- format combo: SRT / ASS,
- open output folder button after completion.

#### Translation

Mode-dependent summary.

YouTube Cloud / Local Cloud:

- cloud backend summary,
- API key/base URL/model fields in collapsible advanced area,
- note that leaving fields blank uses `.env` if present.

Offline:

- local model status,
- model download button if missing,
- local model path browser in advanced area.

#### Advanced drawer

Hidden by default.

Contains:

- batch size,
- context mode,
- preprocessing profile,
- ASR numeric tuning,
- translation memory mode,
- glossary path,
- strict quality toggle,
- debug JSON progress toggle.

Do not show advanced numeric ASR fields by default.

### Right column: state and results

Before run:

- readiness checklist:
  - source selected,
  - backend ready,
  - output path valid.

During run:

- stage label,
- progress bar,
- current stage details,
- compact log tail if desired.

After run:

- summary card:
  - output path,
  - cue count,
  - untranslated count,
  - warning count,
  - strict quality pass/fail,
- buttons:
  - Open Output Folder,
  - View Review,
  - View Quality.

---

## 7.4 Review Tab

Purpose: inspect final cues.

Columns:

```text
#
Start
End
Source
Translation
Status
```

Features:

- virtualized list,
- filtering:
  - All,
  - Failed,
  - Warnings,
- search box,
- row coloring:
  - failed: red tint,
  - warning: amber tint,
  - ok: normal,
- double-click row to copy text or open future editor,
- status badges.

Data source:

- result JSON loaded into a Python model.

Implementation recommendation:

Use a `QAbstractListModel` plus `QSortFilterProxyModel`.

Do not build the entire preview by appending thousands of lines to a QML `TextArea`.

---

## 7.5 Quality Tab

Purpose: show quality report in human-readable form.

Top summary badges:

```text
Total cues
Untranslated
Errors
Warnings
Average CPS
Max line length
Strict quality: PASS/FAIL
```

Issue list columns:

```text
Cue
Type
Severity
Message
```

Buttons:

- Open quality JSON,
- Copy report summary.

---

## 7.6 Log Drawer

The log must not dominate the UI.

Use a collapsible bottom drawer:

- collapsed by default,
- expandable during run,
- monospace text,
- auto-scroll,
- clear button,
- copy button,
- debug toggle to show raw JSON progress.

JSON progress lines should be parsed and hidden unless debug mode is enabled.

---

## 7.7 Visual design language

Use a compact dark professional theme.

Suggested tokens:

```text
spacing.xs = 4
spacing.sm = 8
spacing.md = 12
spacing.lg = 16
spacing.xl = 24

radius.sm = 6
radius.md = 8
radius.lg = 10

font.small = 12
font.body = 13
font.label = 14
font.title = 16
font.header = 18

color.background = "#0B0F14"
color.surface = "#11161D"
color.surfaceAlt = "#161C24"
color.border = "#20262E"
color.text = "#E6EAF0"
color.textMuted = "#8A94A3"
color.accent = "#3D82F6"
color.success = "#22C55E"
color.warning = "#F59E0B"
color.error = "#EF4444"
```

Design rules:

- no giant empty cards,
- no permanent sidebar for two items,
- dense but readable spacing,
- clear focus states,
- consistent field heights,
- tooltips for advanced fields,
- keyboard navigable controls.

---

## 7.8 New QML structure

Recommended file layout:

```text
ui/qml/
  Main.qml
  Theme.qml
  components/
    qmldir
    AppHeader.qml
    ModePicker.qml
    PresetPicker.qml
    FieldLabel.qml
    CompactTextField.qml
    CompactComboBox.qml
    SectionPanel.qml
    RunButton.qml
    StatusPill.qml
    ProgressPanel.qml
    ReadinessChecklist.qml
    LogDrawer.qml
    CuePreviewTable.qml
    QualityPanel.qml
    AdvancedDrawer.qml
```

Retire or archive:

```text
ui/qml/components/Sidebar.qml
ui/qml/views/DashboardView.qml
ui/qml/views/SettingsView.qml
```

Only delete after replacement is stable.

---

## 7.9 AppBridge rework

The bridge should become UI-state driven, not a loose collection of fields.

### New properties

At minimum:

```python
pipelineMode: str
contentPreset: str
asrPreprocess: str
contextMode: str

url: str
filePath: str
sourceLang: str
asrLanguage: str

outPath: str
outputFormat: str

apiKey: str
baseUrl: str
model: str

localModel: str
localModelName: str
localModelReady: bool

glossaryPath: str
translationMemoryMode: str
strictQuality: bool
batch: str

isRunning: bool
statusState: str
statusMessage: str

progressStage: str
progressDone: int
progressTotal: int

resultReady: bool
outputPathResolved: str
cueModel: QObject
qualitySummary: QObject

logText: str
logVisible: bool
debugJsonProgress: bool
```

### New slots

```python
runTranslation()
openOutputFolder()
clearLog()
browseLocalFile()
browseOutputPath()
browseGlossary()
browseLocalModel()
downloadLocalModel()
downloadAsrModels()
setPipelineMode(mode)
```

### JSON progress parsing

In log line handling:

```python
if line.strip().startswith("{") and '"type":"progress"' in line:
    try:
        obj = json.loads(line)
        self._update_progress(obj)
        if not self.debugJsonProgress:
            return
    except Exception:
        pass
```

Update:

```python
progressStage
progressDone
progressTotal
statusMessage
```

Do not display raw JSON progress as error text.

### Result loading

After worker finishes with `rc == 0`:

1. Read result JSON path.
2. Populate cue model.
3. Populate quality summary.
4. Set `resultReady = True`.
5. Switch UI to Review or show result banner.

If result JSON is missing, fall back to final-line parsing for output folder support.

---

## 7.10 Settings persistence

Persist non-secret fields via `QSettings`.

Persist:

- pipeline mode,
- content preset,
- ASR language,
- preprocessing profile,
- context mode,
- output format,
- advanced ASR values,
- batch,
- glossary path,
- TM mode,
- strict quality,
- window geometry.

Do not persist:

- API key.

---

## 7.11 CJK font support

Add bundled CJK font loading.

### Font choice

Use a licensed CJK font such as:

```text
Noto Sans CJK
```

Place in:

```text
assets/fonts/
```

### main.py loading

After creating `QGuiApplication`:

```python
def _load_bundled_fonts() -> None:
    font_dir = _resource_path("assets", "fonts")
    if not os.path.isdir(font_dir):
        return

    for name in os.listdir(font_dir):
        if name.lower().endswith((".ttf", ".otf", ".ttc")):
            QFontDatabase.addApplicationFont(os.path.join(font_dir, name))
```

Call:

```python
app = QGuiApplication(sys.argv)
_load_bundled_fonts()
```

### Packaging

Update PyInstaller spec/build script to include:

```text
assets/fonts
```

Acceptance:

- Japanese/Chinese/Korean text renders consistently in GUI.
- Missing font directory does not crash startup.

---

# 8. Detailed CLI Specification After Implementation

The final CLI should include these controls.

## 8.1 Core

```text
url
--file
--model
--out
--format {srt,ass}
--batch
--source-lang
```

## 8.2 Local translation

```text
--local
--local-host
--local-port
--local-model-name
--local-model
--local-threads
--local-mlock
```

## 8.3 ASR

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
--asr-max-cue-chars-cjk
--asr-no-tags
--asr-keep-tags
--asr-preprocess
```

## 8.4 Presets/context/quality

```text
--content-preset
--context-mode
--context-summary
--glossary
--translation-memory
--translation-memory-db
--strict-quality
--quality-report
--json-progress
--result-json
```

## 8.5 Removed

```text
--cloud-rescue
--cloud-rescue-model
--cloud-rescue-batch
```

---

# 9. Suggested Code Sketches

These are guides, not final code.

## 9.1 Preset dataclass

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ContentPreset:
    name: str
    description: str

    asr_preprocess: str
    asr_max_segment_ms: int
    asr_max_end_silence_ms: int
    asr_speech_noise_threshold: float
    asr_noise_db: float
    asr_min_silence_s: float
    asr_max_cue_duration_ms: int
    asr_max_cue_chars: int
    asr_max_cue_chars_cjk: int

    context_mode: str
    prompt_profile: str

    max_line_chars: int
    max_cps: float


PRESETS: dict[str, ContentPreset] = {
    "auto": ContentPreset(
        name="auto",
        description="Balanced default behavior.",
        asr_preprocess="basic",
        asr_max_segment_ms=6000,
        asr_max_end_silence_ms=250,
        asr_speech_noise_threshold=0.55,
        asr_noise_db=-35,
        asr_min_silence_s=0.25,
        asr_max_cue_duration_ms=3200,
        asr_max_cue_chars=70,
        asr_max_cue_chars_cjk=48,
        context_mode="standard",
        prompt_profile="general",
        max_line_chars=40,
        max_cps=18.0,
    ),
    # add drama, anime, music, documentary, variety, lecture
}
```

## 9.2 Translation window dataclass

```python
from dataclasses import dataclass
from src.srt_io import Cue


@dataclass
class TranslationWindow:
    start_index: int
    cues: list[Cue]
    before_context: list[tuple[str, str]]
    after_context: list[str]
```

## 9.3 Context prompt skeleton

```python
def build_context_prompt(
    window: TranslationWindow,
    *,
    source_language: str | None,
    glossary: str | None,
    prompt_profile: str,
) -> str:
    parts: list[str] = []

    if window.before_context:
        parts.append("CONTEXT BEFORE (already translated; read only):")
        for source, translation in window.before_context:
            parts.append(f"- {source} => {translation}")
        parts.append("")

    if window.after_context:
        parts.append("CONTEXT AFTER (source only; read only):")
        for source in window.after_context:
            parts.append(f"- {source}")
        parts.append("")

    parts.append(
        f"CURRENT CUES (translate exactly {len(window.cues)} numbered lines):"
    )

    for i, cue in enumerate(window.cues, start=1):
        parts.append(f"{i}. {cue.text}")

    parts.append("")
    parts.append(
        "Return only the numbered English translations for CURRENT CUES. "
        "Do not repeat context. Do not include labels. Do not change numbering."
    )

    return "\n".join(parts)
```

## 9.4 Bridge JSON progress parsing

```python
import json


def _handle_log_line(self, line: str) -> None:
    stripped = line.strip()

    if stripped.startswith("{") and '"type":"progress"' in stripped:
        try:
            obj = json.loads(stripped)
        except Exception:
            obj = None

        if obj and obj.get("type") == "progress":
            self._update_progress(obj)
            if not self._debug_json_progress:
                return

    self._append_visible_log(line)


def _update_progress(self, obj: dict) -> None:
    stage = str(obj.get("stage", ""))
    done = int(obj.get("done", 0))
    total = int(obj.get("total", 0))

    self._progress_stage = stage
    self._progress_done = done
    self._progress_total = total

    if stage == "fetch":
        self._status_message = "Fetching subtitles..."
    elif stage == "asr":
        self._status_message = "Transcribing audio..."
    elif stage == "translate":
        self._status_message = f"Translating {done}/{total}..."
    elif stage == "write":
        self._status_message = "Writing output..."

    self.progressChanged.emit()
```

---

# 10. Test Plan

The agent must add or update tests.

## 10.1 Mode tests

- YouTube Cloud mode produces cloud argv without `--local`.
- Local Cloud mode produces `--file` without `--local`.
- Offline mode produces `--file --local` and no cloud env.
- Offline mode does not inject API key/base URL.

## 10.2 Rescue removal tests

- Help output does not mention cloud rescue.
- RunConfig contains no rescue flags.
- Removed env vars are not used.

## 10.3 Preprocessing tests

- `none`, `basic`, `loudnorm`, and `denoise` produce expected filter strings.
- Duration mismatch fallback works.
- Invalid preprocessing profile rejects cleanly.

## 10.4 Preset tests

- Preset values resolve when flags are omitted.
- Explicit flags override presets.
- Environment variables override built-in defaults but not explicit flags.
- Unknown preset fails cleanly.

## 10.5 Context translation tests

- Context mode `off` produces no context section.
- Context mode `light` includes expected before/after context.
- Parser ignores context sections and only parses numbered lines.
- Window builder preserves all cues.
- Window builder respects max cue and max char budgets.
- Fallback splitting preserves cue count.
- Per-item fallback still works.

## 10.6 Result JSON tests

- `--result-json` writes valid JSON.
- Cue count matches output cue count.
- Failed cues are marked correctly.
- Quality report is included.
- Final CLI line remains unchanged.

## 10.7 Quality tests

- Tag leakage detected.
- Empty cue detected.
- Untranslated marker detected.
- CJK residue warning generated.
- Strict quality fails on serious errors.

## 10.8 GUI smoke tests

If automated GUI tests are impractical, at minimum verify manually:

- app starts,
- mode switching updates form,
- run fails cleanly with missing source,
- run fails cleanly with missing cloud credentials,
- offline mode hides cloud fields,
- result JSON loads into Review tab,
- JSON progress does not appear as error text.

---

# 11. Documentation Updates Required

After implementation, update:

1. `AGENT_DOCUMENTATION.md`
2. `README.md`
3. `FRONTEND_DESIGN.md` or replacement UI document
4. `IMPROVEMENTS_TRIAGE.md` or successor tracking doc
5. Any benchmark documentation

Documentation must describe:

- new pipeline modes,
- removal of cloud rescue,
- preprocessing profiles,
- content presets,
- context modes,
- result JSON,
- new UI layout,
- new CLI flags,
- removed flags,
- test count and manual validation checklist.

---

# 12. Manual Validation Checklist

The agent should run or describe how to run these checks.

## 12.1 YouTube Cloud

```bash
python translate.py "https://www.youtube.com/watch?v=..." --content-preset drama
```

Expected:

- fetch succeeds,
- cloud translation runs,
- no local model required,
- result JSON and SRT/ASS written.

## 12.2 Local Cloud

```bash
python translate.py --file sample.mp4 --asr-lang ja --content-preset anime
```

Expected:

- local ASR runs,
- cloud translation runs,
- no local translation model required.

## 12.3 Offline

```bash
python translate.py --file sample.mp4 --asr-lang ja --local --content-preset drama
```

Expected:

- local ASR runs,
- local translation model runs,
- no cloud credentials required.

## 12.4 GUI

Check:

- YouTube Cloud mode hides local controls.
- Local Cloud hides local translation model controls.
- Offline hides cloud controls.
- Preset changes advanced defaults.
- Run progress updates.
- Review tab loads cues.
- Quality tab displays report.
- Log drawer does not dominate layout.

---

# 13. Risks and Mitigations

## Risk 1: FFmpeg filters shift timestamps

Mitigation:

- validate duration,
- fall back automatically,
- avoid time-stretching filters.

## Risk 2: Context prompts destabilize Hy-MT2

Mitigation:

- use smaller context for local,
- preserve numbered protocol,
- robust fallback ladder,
- benchmark local model separately.

## Risk 3: UI rework introduces QML loading failures

Mitigation:

- keep `Main.qml` entry point stable,
- test frozen and dev modes,
- preserve existing bridge startup contract,
- add QML warning logs.

## Risk 4: Removing rescue reduces recovery options

Mitigation:

- keep strong local fallback ladder,
- expose clear failure markers,
- result JSON makes failed cues visible.

This is an intentional product decision requested by the user.

## Risk 5: Presets hide too much from advanced users

Mitigation:

- keep advanced drawer,
- allow explicit flag overrides,
- document precedence.

---

# 14. Definition of Done

The implementation is complete when all of the following are true.

## Functional

- Three pipeline modes work as specified.
- Cloud rescue is fully removed.
- FFmpeg preprocessing is implemented safely.
- Content presets work.
- Context-first translation is the default non-off mode.
- Cue count remains exact.
- Result JSON is produced and consumed by GUI.
- GUI is reworked and usable.
- CJK fonts render in GUI.

## Quality

- Existing tests pass.
- New tests added for all major features.
- No regression in final CLI line contract.
- No timestamp drift introduced by preprocessing.
- Strict quality still works.

## Documentation

- Docs match code.
- Old rescue/mode concepts removed.
- New flags documented.
- UI design doc replaced or updated.

## Build

- `python -m pytest -q` passes.
- `python -m py_compile translate.py main.py gui.py` passes.
- Frozen build starts and runs.
- Frozen build includes new QML and fonts.

---

# 15. Recommended Implementation Order

For lowest risk, implement in this sequence:

1. Remove cloud rescue and define new mode IDs.
2. Add result JSON.
3. Add preprocessing profiles and duration safety.
4. Add content presets.
5. Implement context-first translation engine.
6. Extend quality checks.
7. Add granular JSON progress.
8. Rework AppBridge.
9. Rework QML UI.
10. Add CJK fonts and packaging.
11. Update docs and tests.
12. Run full validation.

Do not attempt the UI rework before the backend mode model and result JSON are stable.

---

# 16. Final Note to the Implementation Agent

This is a quality-first pass.

The primary success metric is not feature count. It is:

- better ASR input,
- better contextual translation,
- clearer user workflow,
- visible quality results,
- no regression in cue alignment or timing integrity.

Prefer boring, robust implementations over clever but fragile ones.

When forced to choose between:

- preserving cue alignment,
- preserving timestamps,
- adding a new feature,

preserve alignment and timestamps first.