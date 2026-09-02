# Remaining Recommendations

> **STATUS UPDATE (mode-simplification pass):** Cloud rescue has been REMOVED as a
> product feature. Any rescue item below marked Approved/Deferred is obsolete.
> The pipeline now has exactly three modes (youtube_cloud / local_cloud / offline);
> content presets, FFmpeg ASR preprocessing, context-first translation windows,
> result JSON, and the reworked Run/Review/Quality GUI have landed. See
> AGENT_DOCUMENTATION.md and TASK_LIST.md for the authoritative current state.


Follow-on work tracked from `FOLLOWUP_REVIEW.md`. This file lists items **not**
implemented in the P0/P1 fix pass (see the "Implemented This Pass" table below
for what is done). Each entry includes its priority, scope note, and acceptance
criteria so a future pass can implement without re-deriving intent.

The companion file `IMPROVEMENTS_TRIAGE.md` covers the broader (already-approved)
backlog; this file is the dedicated, forward-looking list for the follow-up pass.

---

## Implemented This Pass

These came out of the same review and are **already done** (kept here for context
so they are not re-filed):

- [x] P0-1 â€” Cloud rescue endpoint selection (`*CLOUD_RESCUE_*` env vars,
      pre-local snapshot fallback, local-URL exclusion).
- [x] P0-2 â€” Transactional environment mutation (`OPENAI_BASE_URL`/`OPENAI_API_KEY`
      snapshot + `finally` restore, pre-local config stashed on `args`).
- [x] P0-3 â€” Translation-memory closure on all exit paths (success,
      `--strict-quality` failure, translation-endpoint error); `close()` is
      idempotent.
- [x] P0-4 â€” Final failed-cue accounting (`_is_failed_text()` over the
      post-processed `out_cues`).
- [x] P0-5 â€” Newline escaping (verified, pinned by tests).
- [x] P0-6 â€” Documentation/code default sync (`AGENT_DOCUMENTATION.md`,
      `README.md`, CLI + QSettings tables; rescue env vars documented).
- [x] P0-7 â€” Timestamp invariant reconciled with overlap-snap (trim `end` only
      on overlap, never below 300 ms).
- [x] P1-1 â€” Source-language precedence (`_is_known_source_code()`).
- [x] P1-2 â€” `--source-lang` for local files (translation hint when ASR is
      auto/unknown; help text + AGENT_DOC updated; acceptance tests added).

> **Scope rule for everything below:** keep the pipeline non-breaking
> â€” never change the cue count, never alter original timestamps beyond the
> documented overlap snap, preserve the final `Wrote {N} cues to {path}` line
> for the GUI, and do not regress the foreignization directive.

---

## P1 â€” CJK Quality (higher priority)

### 1. ASR presets/profiles (P1-3)

- **Problem:** All CJK ASR tuning currently depends on per-flag fiddling; safer
  defaults for clean / anime / drama / documentary material are missing.
- **Proposed:** Add `--asr-preset {clean,anime,drama,documentary}` mapping to a
  curated set of `sensevoice-small` runtime + VAD + post-processing defaults.
- **Acceptance criteria:**
  - Each preset has a documented, reproducible flag set.
  - Presets do not regress the `auto` default.
  - README/AGENT_DOC list the presetâ†’flag mapping.

### 2. Translation context window (P1-4)

- **Problem:** `translate_cues()` translates cues individually; no
  previous/next context is sent, so CJK pronouns and continuation lines lose
  referents.
- **Proposed:** Add `--context-window {n}` (sentences of surrounding context per
  batch) and feed it through to the batch builder / prompt.
- **Acceptance criteria:**
  - Context never exceeds the model budget / `max_cue_chars` split.
  - Cue count and timestamps unchanged.
  - `--context-window 0` == current behavior.

### 3. Extended CJK quality checks (P1-5)

- **Problem:** The current quality report covers reading speed / CPS but not
  CJK-specific leakage.
- **Add checks for:**
  - ASR tag leakage (`<|...|>` left in output).
  - Fansub source-residue / transliteration residue.
  - Duplicate translated lines.
  - Glossary violation (a `--glossary` term rendered differently in-target).
  - Overlap / min-duration violations after snapping.
- **Acceptance criteria:**
  - Each check emits a named warning with cue index (no hard failure by default).
  - `--strict-quality` escalates a defined subset to exit-code failures.

### 4. Granular translation progress callback (P1-7)

- **Problem:** `translate_cues()` exposes only coarse progress; `--json-progress`
  emits batch-level lines but not per-cue progress.
- **Proposed:** Thread an optional `progress` callable into `translate_cues()`
  reporting `(done, total, last_cue_index)`.
- **Acceptance criteria:**
  - Default remains `None` (no behavior change).
  - Existing `--json-progress` line contract unchanged.

### 5. GUI JSON-progress consumption (P1-6)

- **Problem:** The GUI prints progress lines but renders raw JSON as error text.
- **Proposed:** Have `AppBridge` parse `--json-progress` JSON lines and surface a
  structured progress model to QML.
- **Acceptance criteria:**
  - GUI progress bar advances on `translated {N}/{total}`.
  - JSON lines never appear in the error pane.
  - Final `Wrote N cues to ...` line still fires.

### 6. Bundled CJK fonts in GUI (P1-8)

- **Problem:** ASS output for CJK relies on system fonts which may be missing in
  the packaged GUI.
- **Proposed:** Bundle a fallback CJK font and have `ass_io` resolve
  `font_for_language()` against the bundle first, then system.
- **Acceptance criteria:**
  - `ja`/`zh`/`zh-TW`/`ko` resolve to a bundled font when no system CJK font is
    found.
  - User `--ass-font` override still wins.

### 7. Local-file `--source-lang` finalization (P1-2 â€” follow-up)

- **Status:** Hint behavior is implemented (see above); the deeper semantic
  decision â€” should `--source-lang` *force* the prompt language even when ASR
  confidence is high? â€” is deferred.
- **Proposed decision point for next pass:** keep "hint-only when ASR is
  auto/unknown" (current) vs. "always prefer `--source-lang` for local files".
- **Acceptance criteria:** pick one and document it in README Â§CLI + AGENT_DOC
  5.1; add a test pinning the chosen behavior.

---

## P2 â€” UX / Frontend (medium priority)

### 8. Cue preview table

- **Goal:** A scrollable table of the original cue + translation side-by-side
  with index, start/end, duration, and a status badge
  (`[ok]` / `[untranslated]` / `[rescued]`).
- **Acceptance criteria:**
  - Loads from `--json-progress` final summary or a dedicated JSON dump.
  - Clicking a row opens the editor at that line in the output file.

### 9. Quality panel

- **Goal:** A dedicated pane consuming `quality_report.json` with filterable
  warnings (the CJK checks from item 3, plus CPS / reading-speed).
- **Acceptance criteria:**
  - Each warning links to the offending cue index in the preview table.
  - `--strict-quality` summary is reflected as a banner
    `Strict quality: PASS/FAIL`.

### 10. Fusion / Material styling

- **Goal:** Optional stylesheet for the GUI; **non-functional**, lower risk.
- **Acceptance criteria:** Togglable from a `--gui-theme` setting with no
  functional side effects.

---

## P3 â€” Optional / Future (low priority)

### 11. Audio preprocessing

- Pre-normalize gain / denoise before ASR to improve CJK ASR on noisy sources.
  Criterion: opt-in, `--asr-preprocess` flag, no default behavior change.

### 12. Sound-tag modes

- Recognize and preserve / annotate `â™ª` lines and speaker-koe cues instead of
  translating them. Criterion: configurable mode flag.

### 13. Translation profiles

- Named profiles (e.g. `anime-fansub`, `drama-official`) bundling `--glossary`,
  `--context-window`, `--quality-report`, ASR preset, and quality thresholds.
  Criterion: `--profile {name}` overrides individual flags.

### 14. Bilingual ASS output

- Emit a second target-language style track / dual-line ASS for study use.
  Criterion: `--bilingual` opt-in; default SRT/ASS unchanged.

### 15. Fuzzy translation memory

- Match against near-duplicate source cues (fuzzy ratio) for CJK where verbatim
  repeats are common. Criterion: opt-in (`--tm-fuzzy`), preserves exact TM
  hits' precedence.

---

## Suggested tests to add (for the items above)

- `test_cli_flags.py::test_asr_preset_defaults` (item 1)
- `test_translate_cues.py::test_context_window_noop_for_zero` (item 2)
- `test_subtitle_quality.py::test_cjk_tag_leakage_detected` (item 3)
- `test_translate_cues.py::test_progress_callback_invoked` (item 4)
- `test_quality_report.py::test_strict_quality_flag_in_report` (item 3 / 9)
- `test_cli_flags.py::test_asr_preset_flags` (item 1)
- `test_translate_cues.py::test_translate_cues_invokes_progress` (item 4)
- `test_fetch_subs.py::test_source_lang_hint_when_asr_auto` (item 7)
- `test_as_io.py::test_font_falls_back_to_bundled_cjk` (item 6)
- `test_gui.py::test_progress_does_not_render_as_error` (item 5)
- `test_quality_report.py::test_quality_panel_consumes_report` (item 9)
- `test_quality_report.py::test_quality_panel_links_cue_index` (item 9)
- `test_asr.py::test_preprocess_opt_in` (item 11)
- `test_translate_cues.py::test_context_window_respects_budget` (item 2)




