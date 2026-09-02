# FOLLOWUP_REVIEW.md

> **STATUS UPDATE (mode-simplification pass):** Cloud rescue has been REMOVED as a
> product feature. Any rescue item below marked Approved/Deferred is obsolete.
> The pipeline now has exactly three modes (youtube_cloud / local_cloud / offline);
> content presets, FFmpeg ASR preprocessing, context-first translation windows,
> result JSON, and the reworked Run/Review/Quality GUI have landed. See
> AGENT_DOCUMENTATION.md and TASK_LIST.md for the authoritative current state.


## Review: Translation Agent â€” CJK Subtitle Quality Follow-up

This document reviews the current project state against the earlier CJK subtitle-quality recommendations.

Reviewed current files:

- `translate.py`
- `main.py`
- `gui.py`
- `AGENT_DOCUMENTATION.md`
- `IMPROVEMENTS_TRIAGE.md`

The project has made strong progress. Many high-value recommendations are now implemented. However, there are a few correctness issues and several quality/UX follow-ups that should be addressed before this can be considered a consistently high-quality CJK subtitle pipeline.

---

# 1. Overall Assessment

## Current State

The project now has:

- Q8_0 Hy-MT2 as the default local translation model.
- Improved CJK detection via `src/cjk.py` / `detect_cjk_from_cues`.
- Protection for the `[untranslated]` marker during sanitization.
- `--source-lang` support for YouTube subtitle track selection.
- ASS font selection based on source language.
- `--ass-font` and `--ass-fontsize` overrides.
- JSON progress output via `--json-progress`.
- Translation memory, glossary, cloud rescue, quality reporting, and strict-quality mode.

This is a solid foundation.

## Main Remaining Risks

The biggest remaining risks are:

1. **Cloud rescue may incorrectly use the local llama.cpp endpoint when running in local mode.**
2. **Environment mutation inside `translate.py` may leak between GUI runs.**
3. **Translation memory may not be closed on some early-return paths.**
4. **Failed/untranslated cue accounting is computed before final sanitization/postprocessing.**
5. **Documentation and code defaults are inconsistent in several places.**
6. **The "timestamps are never modified" invariant needs reconciliation with overlap snapping/postprocessing.**
7. **CJK quality tuning still depends on manual flags; safer presets/profiles are needed.**
8. **The GUI does not yet fully exploit JSON progress or provide cue-level QA review.**

---

# 2. Implemented Recommendations

The following earlier recommendations appear to be implemented or otherwise satisfied.

| Recommendation | Status | Evidence / Notes |
|---|---:|---|
| Avoid extremely low-bit local translation model | Done | Default is `Hy-MT2-1.8B-Q8_0`. The old `1.25Bit` scratch check is not part of the shipped default. |
| Improve CJK language detection | Done | `translate.py` now uses `detect_cjk_from_cues(cues)` with fallback to `_detect_cjk_lang`. |
| Preserve `[untranslated]` marker during sanitization | Done | `_sanitize_output()` explicitly returns the marker unchanged. |
| Numbered cue protocol | Already implemented | Existing numbered-item protocol remains the correct alignment mechanism. |
| Retry / split / per-item fallback | Already implemented | Existing fallback ladder remains good. |
| Cloud rescue architecture | Implemented | Rescue handler exists, but has an endpoint-selection issue; see P0 tasks. |
| English target-side line wrapping | Implemented | Handled by `postprocess` according to documentation. |
| Reading-speed / CPS quality checks | Implemented | Covered by `src/subtitle_quality.py`. |
| CJK utilities | Implemented | `src/cjk.py` exists and is used for detection. Kinsoku line breaking is available for future CJK-target/bilingual output. |
| ASS CJK font selection | Implemented | `write_ass()` receives source language, font override, fontsize override, and title. |
| `--source-lang` for YouTube | Implemented | `fetch_original_subtitles(..., preferred_lang=args.source_lang)` is wired. |
| JSON progress | Implemented | `--json-progress` emits machine-readable progress lines while preserving final `Wrote N cues to ...`. |

---

# 3. Critical Follow-up Issues

These should be treated as P0 or high-priority P1.

---

## P0-1: Cloud rescue can point to the local server in local mode

### Problem

In local mode, `translate.py` sets:

```python
os.environ["OPENAI_BASE_URL"] = base_url
```

before calling `_run_pipeline()`.

Later, cloud rescue setup does:

```python
rescue_base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
```

This means that when the main translation backend is local, cloud rescue may try to use the local llama.cpp server as the rescue endpoint.

That is incorrect: cloud rescue should use a real cloud endpoint.

### Impact

- `--cloud-rescue` may silently fail or produce no rescue.
- The rescue model name may be sent to the local server, which may not host it.
- Users may believe rescue is enabled when it is not usable.

### Recommended Fix

Introduce dedicated rescue endpoint configuration:

```text
CLOUD_RESCUE_API_KEY
CLOUD_RESCUE_BASE_URL
CLOUD_RESCUE_MODEL
```

or snapshot the original cloud environment before overriding `OPENAI_BASE_URL` for local mode.

Preferred behavior:

```text
If CLOUD_RESCUE_BASE_URL is set:
    use it.
Else if original OPENAI_BASE_URL was a cloud endpoint:
    use original OPENAI_BASE_URL.
Else:
    disable cloud rescue with a clear warning.
```

Do not use a local `http://127.0.0.1:...` endpoint for cloud rescue unless explicitly requested by a separate local-rescue flag.

### Acceptance Criteria

- Local translation plus cloud rescue works when valid cloud rescue credentials are provided.
- Local translation without cloud credentials disables rescue with a clear message.
- Rescue never silently uses the local llama.cpp endpoint when described as cloud rescue.
- Add tests for endpoint selection.

---

## P0-2: Global environment mutation may leak between GUI runs

### Problem

`translate.py` mutates global process environment:

```python
os.environ["OPENAI_BASE_URL"] = base_url
```

The GUI runs the pipeline in-process via `TranslationWorker`. If environment restoration is not exact, a local run can contaminate a later cloud run, or vice versa.

### Impact

- GUI may work the first time but fail on subsequent runs.
- Cloud mode may accidentally use a stale local base URL.
- Difficult-to-debug endpoint issues.

### Recommended Fix

Prefer one of:

1. Pass base URL through `Settings` / `load_settings()` instead of mutating environment.
2. Snapshot and restore environment around the local branch:

```python
old_base_url = os.environ.get("OPENAI_BASE_URL")
os.environ["OPENAI_BASE_URL"] = base_url
try:
    settings = load_settings(override_model=args.local_model_name)
    return _run_pipeline(args, settings, fetched)
finally:
    if old_base_url is None:
        os.environ.pop("OPENAI_BASE_URL", None)
    else:
        os.environ["OPENAI_BASE_URL"] = old_base_url
```

### Acceptance Criteria

- Running local mode then cloud mode in the same GUI process works correctly.
- No stale `OPENAI_BASE_URL` remains after a local run.
- Tests cover environment restoration.

---

## P0-3: Translation memory may not be closed on some failure paths

### Problem

In `_run_pipeline()`, TM is opened, but strict-quality failure can return before:

```python
if tm is not None:
    tm.close()
```

Also, endpoint errors return before TM cleanup.

### Impact

- SQLite handle may remain open.
- Windows file locking issues.
- Resource leak in GUI mode.

### Recommended Fix

Use `try/finally` after TM creation:

```python
try:
    # rest of pipeline
    ...
finally:
    if tm is not None:
        tm.close()
```

If a return code is needed, store it and return after cleanup.

### Acceptance Criteria

- TM is closed on success.
- TM is closed on strict-quality failure.
- TM is closed on translation endpoint failure.
- No SQLite lock remains after CLI/GUI run.

---

## P0-4: Failed/untranslated count is computed before final sanitization/postprocessing

### Problem

Current code computes:

```python
failed_indices = [
    i for i, t in enumerate(translations) if not t or not t.strip()
]
```

before final sanitization and postprocessing.

But final text may become empty or marker-like after:

- tag stripping,
- residual CJK stripping,
- postprocess cleanup,
- future normalization.

### Impact

- Quality report may undercount untranslated cues.
- Strict-quality mode may pass when final output contains empty cues.
- Rescue summary may be inaccurate.

### Recommended Fix

Recompute failed cues from final `out_cues` after postprocessing:

```python
def _is_failed_text(text: str | None) -> bool:
    text = (text or "").strip()
    return not text or text == UNTRANSLATED_MARKER

failed_indices = [
    i for i, c in enumerate(out_cues) if _is_failed_text(c.text)
]
```

Use this final count for:

- console warning,
- rescue summary,
- quality report,
- strict-quality mode.

### Acceptance Criteria

- A cue that becomes empty after sanitization is counted as failed.
- `[untranslated]` cues are counted as untranslated.
- Quality report reflects final output, not intermediate translations.

---

## P0-5: Verify newline escaping in `translate.py`

### Problem

The provided file content shows fragments like:

```python
text=c.text.replace("
", "\\N")
```

and:

```python
text=c.text.replace("\\N", "
")
```

If those are literal newline characters inside normal string literals, the file is syntactically invalid.

This may be a display artifact from the knowledge base, but it must be verified.

### Recommended Action

Run:

```bash
python -m py_compile translate.py
```

Ensure the actual source uses:

```python
text=c.text.replace("\n", "\\N")
```

and:

```python
text=c.text.replace("\\N", "\n")
```

### Acceptance Criteria

- `translate.py` compiles cleanly.
- ASS output uses `\N`.
- SRT output uses real newlines.
- Tests cover ASS/SRT line-break conversion.

---

## P0-6: Documentation defaults are inconsistent with code

### Problem

`AGENT_DOCUMENTATION.md` and `translate.py` disagree in several places.

Examples:

| Item | Documentation | Code |
|---|---:|---:|
| `--batch` default | 40 in one CLI table | 8 in `_parse_args` |
| `--asr-max-segment-ms` | 7000 in one CLI table | 6000 in code/env reference |
| `--asr-min-silence-s` | 0.20 in one CLI table | 0.25 in code/env reference |
| `--asr-max-cue-duration-ms` | 3000 in one CLI table | 3200 in code/env reference |
| `--ass-fontsize` | help says default 52 | argparse default is `None`, effective default likely in `write_ass` |

### Recommended Fix

Update documentation to match code, or intentionally change code defaults and update tests.

The documentation should also clearly state:

- effective ASS fontsize default,
- dynamic batching behavior for Hy-MT2,
- source-language precedence,
- JSON progress contract,
- cloud rescue environment variables.

### Acceptance Criteria

- All CLI defaults in docs match code.
- Environment variable defaults match code.
- `--source-lang`, `--ass-font`, `--ass-fontsize`, and `--json-progress` are documented consistently.

---

## P0-7: Reconcile "timestamps are sacred" with overlap snapping

### Problem

The documentation contains both:

- "Original `start`/`end` times are NEVER modified."
- `postprocess.py` performs "overlap snapping".

If overlap snapping changes cue timings, those statements conflict.

### Recommended Action

Inspect `src/postprocess.py` and decide one of:

#### Option A: Preserve invariant strictly

- Do not modify `start`/`end`.
- Only warn about overlaps in quality report.
- Make timing correction a separate opt-in mode.

#### Option B: Introduce explicit timing-adjust mode

Add a flag such as:

```bash
--timing-adjust off|warn|snap
```

Default:

```bash
--timing-adjust off
```

or, if current behavior is intentional:

```bash
--timing-adjust snap
```

but then update the documentation invariant.

### Acceptance Criteria

- Documentation and implementation agree.
- Users can know whether timings are modified.
- Strict mode can fail on overlaps without silently changing timings if desired.

---

# 4. CJK Quality Follow-ups

These are not necessarily blockers, but they are important for the stated goal: quality CJK subtitles.

---

## P1-1: Improve source-language precedence

### Current Behavior

`translate.py` may override `source_lang` using script detection even when the fetcher already returned a valid language code.

### Problem

If YouTube or ASR returns a specific code such as:

- `zh-TW`
- `zh-HK`
- `ja`
- `ko`
- `yue`

script-ratio detection may downgrade it to a generic code such as `zh`.

That can affect:

- ASS font selection,
- glossary behavior,
- translation prompt wording,
- future Traditional/Simplified handling.

### Recommended Rule

Use this precedence:

```text
1. Explicit user flag:
   --source-lang for YouTube
   --asr-lang for local ASR, if not auto

2. Source language returned by fetcher/ASR, if specific and known.

3. Script-ratio detection only when language is missing, auto, unknown, or suspicious.
```

### Suggested Logic

```python
def _resolve_source_language(args, fetched_source_lang, cues):
    explicit = getattr(args, "source_lang", None)

    if explicit:
        return explicit

    if fetched_source_lang and fetched_source_lang.lower() not in {"auto", "und", ""}:
        return fetched_source_lang

    if getattr(args, "asr_lang", "auto") not in (None, "", "auto"):
        return args.asr_lang

    return detect_cjk_from_cues(cues) or fetched_source_lang
```

### Acceptance Criteria

- Explicit user language always wins.
- Specific fetched language codes are preserved.
- Auto-detection is used only when needed.
- Tests cover `zh-TW`, `ja`, `ko`, `yue`, and auto cases.

---

## P1-2: Clarify `--source-lang` behavior for local files

### Problem

`--source-lang` is currently documented primarily for YouTube.

For local files, ASR language is controlled by `--asr-lang`.

However, users may expect:

```bash
python translate.py --file video.mp4 --source-lang ja
```

to influence translation language.

### Recommended Behavior

For local files:

```text
--asr-lang controls ASR.
--source-lang controls translation prompt source language if ASR language is auto or unknown.
```

Alternatively, reject the ambiguity with a clear help message.

### Acceptance Criteria

- Local-file behavior is documented.
- `--source-lang` does not silently do nothing.
- Tests cover local-file language resolution.

---

## P1-3: Add CJK ASR presets/profiles

### Problem

Earlier recommendations suggested lower CJK cue-character limits and tighter VAD segmentation for CJK quality.

Current defaults remain:

```text
FUNASR_MAX_SEGMENT_MS=6000
FUNASR_MAX_END_SILENCE_MS=250
FUNASR_SPEECH_NOISE_THRES=0.55
FUNASR_NOISE_DB=-35
FUNASR_MIN_SILENCE_S=0.25
FUNASR_MAX_CUE_DURATION_MS=3200
FUNASR_MAX_CUE_CHARS_CJK=48
```

For high-quality CJK subtitles, `48` CJK characters per cue is often too long.

### Recommended Approach

Do not change global defaults without benchmark evidence. Instead, add optional presets:

```bash
--asr-preset clean|anime|drama|documentary
```

or environment profiles:

```text
FUNASR_PRESET=clean
FUNASR_PRESET=anime
```

Example preset values:

| Preset | max segment ms | max end silence ms | speech noise threshold | max CJK chars |
|---|---:|---:|---:|---:|
| clean | 5000 | 250 | 0.55 | 32 |
| drama | 4500 | 230 | 0.58 | 28 |
| anime | 4000 | 200 | 0.62 | 24 |
| documentary | 5500 | 280 | 0.52 | 34 |

### Acceptance Criteria

- Presets are opt-in.
- Existing defaults remain unchanged unless benchmarked.
- Presets are documented.
- Tests verify preset-to-flag mapping.

---

## P1-4: Add optional previous/next context to translation

### Problem

CJK languages frequently omit subjects, objects, and pronouns. Without neighboring context, translations can become inconsistent.

### Recommended Implementation

Add an opt-in flag:

```bash
--context-window 0|1|2|3
```

Default:

```bash
--context-window 0
```

or, if safe after testing:

```bash
--context-window 1
```

When enabled, include context outside the numbered block:

```text
Context before (do not translate):
- previous cue text
- previous cue text

Translate these cues:
1. current cue
2. current cue

Context after (do not translate):
- next cue text
```

### Constraints

- Do not break numbered-item protocol.
- Do not change cue count.
- Do not let context lines appear in output.
- Keep Hy-MT2 batch limits safe.
- Make cloud/Hy-MT2 behavior configurable if needed.

### Acceptance Criteria

- Context improves pronoun/name consistency.
- Output alignment remains exact.
- No context text leaks into subtitles.
- Tests cover parsing with context present.

---

## P1-5: Extend quality report with CJK-specific checks

### Current Report

The quality report already covers:

- CPS,
- duration,
- character count,
- line count,
- empty cues,
- untranslated count.

### Recommended Additional Checks

Add these as warnings or errors:

| Check | Suggested Severity |
|---|---|
| ASR tag leakage, e.g. `<\|zh\|>` | Error |
| Fansub markup leakage, e.g. `[CHENGYU:...]` | Error |
| Source CJK residue in English output | Warning, unless glossary/approved term |
| Overlapping cues | Warning/Error depending mode |
| Duplicate consecutive text | Warning |
| Glossary term violation | Warning |
| Excessive line count after final postprocess | Warning |
| Cue became empty after sanitization | Error |

### Important Note

Source CJK residue should not always be treated as fatal. Names, honorifics, titles, and glossary terms may intentionally remain CJK.

Recommended behavior:

```text
CJK residue + glossary term allowed -> info/ok
CJK residue + no glossary match -> warning
Large amount of CJK residue -> error in strict mode
```

### Acceptance Criteria

- Quality JSON includes new check counts.
- Strict-quality mode can fail on tag leakage.
- Source residue is reported with cue indices.
- Tests cover tag leakage and residue cases.
---

## P1-6: Make JSON progress useful in GUI

### Current State

CLI has `--json-progress`, but the GUI may not yet use it fully.

### Recommended GUI Behavior

The bridge should parse lines like:

```json
{"type":"progress","stage":"fetch","done":0,"total":420}
{"type":"progress","stage":"translate","done":420,"total":420}
{"type":"progress","stage":"write","done":420,"total":420}
```

and update a progress indicator.

### Suggested UI States

```text
Fetching subtitles...
Transcribing audio...
Translating...
Post-processing...
Writing output...
Completed.
```

### Acceptance Criteria

- JSON progress lines are parsed and not shown as raw noise unless debug mode is on.
- Progress bar or status label updates.
- Final `Wrote N cues to ...` contract remains unchanged.

---

## P1-7: Add granular translation progress

### Problem

Current JSON progress appears to emit only coarse milestones.

For long files, users need per-batch progress.

### Recommended Addition

Extend `translate_cues()` with an optional callback:

```python
def translate_cues(
    cues,
    client,
    model,
    batch_size=8,
    ...,
    progress_callback=None,
):
```

Callback signature:

```python
progress_callback(done: int, total: int, stage: str = "translate")
```

Then `translate.py` can emit:

```json
{"type":"progress","stage":"translate","done":48,"total":420}
```

### Acceptance Criteria

- No performance regression.
- GUI can show smooth progress.
- CLI output remains stable.
- Final line remains exact.

---

## P1-8: Load bundled CJK fonts in GUI

### Problem

`main.py` does not currently load bundled CJK fonts.

If the GUI displays source CJK text, logs, cue previews, or quality reports, font fallback may be inconsistent.

### Recommended Fix

Add font loading after `QGuiApplication` creation:

```python
from PySide6.QtGui import QFontDatabase

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

### Packaging Requirement

If this is added, the PyInstaller spec must bundle:

```text
assets/fonts
```

Recommended font:

```text
Noto Sans CJK
```

or another licensed CJK font.

### Acceptance Criteria

- GUI consistently renders Japanese/Chinese/Korean text.
- Frozen build includes fonts.
- No startup failure if font directory is absent.
---

# 5. Frontend Follow-ups

These are lower priority than correctness and translation quality, but they significantly improve usability.

---

## P2-1: Add cue preview table

### Goal

Allow the user to inspect final cues before delivery.

Suggested columns:

| # | Start | End | Source | Translation | Status |
|---:|---:|---:|---|---|---|

Status values:

```text
ok
untranslated
empty
too long
too fast
overlap
warning
```

### Recommended Behavior

- Read final SRT/ASS after run.
- Or keep cues in memory and expose them through `AppBridge`.
- Allow double-click editing in a future version.

### Acceptance Criteria

- User can see failed cues without opening the SRT.
- Quality warnings are visible per cue.
- UI remains responsive for large subtitle files.

---

## P2-2: Add quality panel

### Goal

Display the JSON quality report in a human-readable panel.

Suggested fields:

```text
Total cues
Untranslated cues
Empty cues
CPS warnings
Duration warnings
Line-length warnings
Overlap warnings
Tag leakage
Source residue
Serious errors
```

### Acceptance Criteria

- Quality report is visible after run.
- Strict-quality failures are clearly highlighted.
- User can open the JSON report file if saved.

---

## P2-3: Consider Fusion/Material style

### Current State

`main.py` uses `QT_QUICK_CONTROLS_STYLE=Basic`. This is stable.

### Optional Improvement

Consider Fusion or Material with dark theme. This is cosmetic and should not override user preference if an environment variable is already set.

---

# 6. Optional / Deferred Enhancements

These are not required for the next pass, but they remain valuable for future CJK quality work.

---

## P3-1: Audio preprocessing

Possible future flag:

```bash
--asr-preprocess none|loudnorm|denoise
```

Potential ffmpeg filter: `highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11`. Only implement if benchmarking shows measurable ASR improvement.

---

## P3-2: Sound-tag modes

Possible future flag: `--sound-tags strip|note|ass-comment`. Useful for SDH-style subtitles but not essential for normal translation output.

---

## P3-3: Translation profiles

Possible future flag: `--translation-profile general|anime|drama|documentary|literal`. Introduce carefully because it affects the foreignization directive.

---

## P3-4: Bilingual ASS output

Outside the current "target language fixed to English" invariant. Implement as a separate mode with source text as a secondary ASS style.

---

## P3-5: Fuzzy translation memory

Exact-match TM is safer. Fuzzy TM can introduce dangerous CJK mismatches unless segmentation and language codes are stable.

---

# 7. Documentation Updates Needed

After implementing follow-ups, update `AGENT_DOCUMENTATION.md` for:

1. CLI defaults.
2. Environment variables.
3. Cloud rescue configuration.
4. Source-language precedence.
5. JSON progress contract.
6. ASS output behavior.
7. Timing/postprocessing invariant.
8. GUI progress handling.
9. Font bundling, if implemented.
10. New tests.

---

# 8. Recommended Task Order

## P0 â€” Correctness

1. Fix cloud rescue endpoint selection.
2. Make environment mutation transactional.
3. Close translation memory on all exit paths.
4. Recompute failed/untranslated cues from final output.
5. Verify/fix newline escaping in `translate.py`.
6. Sync documentation with code.
7. Reconcile timestamp invariant with postprocessing behavior.

## P1 â€” CJK Quality

8. Improve source-language precedence.
9. Clarify local-file `--source-lang` behavior.
10. Add ASR presets/profiles.
11. Add optional translation context window.
12. Extend quality report with tag leakage, residue, overlap, and glossary checks.
13. Make GUI consume JSON progress.
14. Add granular translation progress callback.
15. Load bundled CJK fonts in GUI.

## P2 â€” UX

16. Add cue preview table.
17. Add quality panel.
18. Consider Fusion/Material styling.

## P3 â€” Optional Future

19. Audio preprocessing.
20. Sound-tag modes.
21. Translation profiles.
22. Bilingual ASS.
23. Fuzzy TM.

---

# 9. Suggested Tests to Add

## Correctness

- Cloud rescue endpoint selection.
- Cloud rescue disabled cleanly when no cloud endpoint is available.
- Environment restoration after local mode.
- TM closure on success / strict-quality failure / translation endpoint error.
- Final failed-cue count after sanitization.
- `[untranslated]` marker remains after all passes.

## Language Handling

- Explicit `--source-lang` wins over detection.
- Fetched `zh-TW` is not downgraded to `zh` unnecessarily.
- Local ASR `--asr-lang ja` is respected.
- Script detection runs only when language is unknown/auto.

## Output

- ASS contains expected font for `ja`, `zh`, `zh-TW`, `ko`.
- ASS fontsize override works.
- SRT line breaks are correct.
- ASS line breaks are correct.
- Final CLI line remains exactly `Wrote {N} cues to {path}`.

## Progress

- `--json-progress` emits valid JSON lines.
- JSON progress does not break the final-line contract.
- GUI bridge parses progress without rendering JSON as error text.

## Quality

- Tag leakage is detected.
- Empty final cue is counted.
- Source residue warning is generated.
- Strict-quality fails on serious errors.

---

# 10. Final Verdict

The project is in a much stronger state than before. The core architecture is sound, and the major approved recommendations have been implemented.

The next pass should focus on:

1. **Correctness around cloud rescue and environment handling.**
2. **Accurate final failure accounting.**
3. **Documentation/invariant consistency.**
4. **CJK-specific quality reporting and optional tuning presets.**
5. **GUI progress and QA visibility.**

Once the P0 items are resolved, the pipeline will be much safer for repeated GUI use and production subtitle generation.

