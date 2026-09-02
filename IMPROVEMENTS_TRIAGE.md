# Improvements Triage

> **STATUS UPDATE (mode-simplification pass):** Cloud rescue has been REMOVED as a
> product feature. Any rescue item below marked Approved/Deferred is obsolete.
> The pipeline now has exactly three modes (youtube_cloud / local_cloud / offline);
> content presets, FFmpeg ASR preprocessing, context-first translation windows,
> result JSON, and the reworked Run/Review/Quality GUI have landed. See
> AGENT_DOCUMENTATION.md and TASK_LIST.md for the authoritative current state.


> Reviewed against the current working tree (commit `0b72f59`, 251-test suite).

---

## Summary

> The triage below covers **all sections of `improvements.txt`** (1â€“13, incl. Â§8â€“13
> which were not in the original triage). Approved items are implemented and
> verified (251-test suite green at commit `0b72f59`).

| Category | Count | Notes |
|---|---:|---|
| **Approved** (implemented) | 10 | Higher-value, non-breaking, aligned with project conventions |
| **Deferred** | 10 | Reasonable ideas, but need benchmark data, are large/risky, or are not core |
| **Rejected / Not applicable** | 9 | Already implemented, not applicable, or contradict project invariants |

---

## Per-item triage

### Section 1 â€” Critical quality issues

**1.1 Avoid extremely low-bit translation models for CJK** â†’ **Approved (already
satisfied).** The code already defaults to `Hy-MT2-1.8B-Q8_0` everywhere
(`--local-model-name` default in `translate.py`, `_LOCAL_MODEL` in
`backend/bridge.py`). The `1.25bit` file referenced by `_gguf_check.py` is a
scratch script, not the shipped default.

**1.2 Improve CJK language detection** â†’ **Approved (implemented).**
Added `src/cjk.py` (`detect_cjk_language`, `detect_cjk_from_cues`, `contains_cjk`,
kinsoku line breaking) and wired the CLI (`translate.py`) to classify from a large
sample (up to 80 cues) instead of 5, keeping `_detect_cjk_lang` as a fallback.

**1.3 Preserve the untranslated marker during sanitization** â†’ **Approved
(implemented).** Added an explicit guard in `_run_pipeline._sanitize_output` and
a test ensuring `[untranslated]` survives the tag-stripping / fansub-markup pass.

### Section 2 â€” CJK ASR improvements

**2.1 Recommended SenseVoice defaults for CJK** â†’ **Deferred.** These are
tuning presets. The knobs already exist as CLI flags/env vars
(`--asr-max-cue-chars-cjk`, `--asr-max-segment-ms`, etc.), and changing hard
defaults risks regressions without benchmark evidence. Tracked as future work.

**2.2 Optional audio preprocessing (loudnorm/denoise)** â†’ **Deferred.** New
ffmpeg-filter pipeline adds complexity and runtime; needs a benchmark to prove
quality gain before landing.

**2.3 Sound-tags handling (`--sound-tags`) modes** â†’ **Deferred.** The `strip`
behavior already exists (`--asr-no-tags` / `--asr-keep-tags`). The
`keep-as-note` / `keep-ass-comments` modes are a larger feature with no immediate
consumer.

### Section 3 â€” Translation improvements

**3.1 Use cue IDs and strict output mapping** â†’ **Rejected (already
implemented).** The numbered-item protocol (`1. text` â†’ `1. translation`) already
enforces alignment, with a per-item fallback ladder and misalignment handling
(`_numbered_block` / `_parse_numbered` / `_translate_batch`).

**3.2 Add previous/next context** â†’ **Deferred.** Improving pronoun consistency
is valuable, but it changes the prompt for every cloud/Hy-MT2 call and risks the
foreignization directive and output-format stability. Needs staged validation.

**3.3 Add a translation style/profile** â†’ **Deferred.** Additive, but touches the
system prompt for all cloud calls; deferred until prompt-hygiene testing is set up.

**3.4 Improve glossary handling (note/case_sensitive columns)** â†’ **Deferred.**
The glossary hash is already part of the TM key (see `translation_memory.make_key`
and the `glossary_hash` flow). Extended TSV columns are a nice-to-have, not core.

**3.5 Translation memory quality metadata** â†’ **Rejected (not needed now).** The
existing schema (`hits`, `last_used_at`, `created_at`) plus the
`_purge_poisoned_entries` pass already serve the exact-match cache; quality-score
columns add unused complexity.

**3.6 Add source-residue validation** â†’ **Rejected (already implemented).**
`looks_untranslated` plus `postprocess.strip_residual_cjk` already detect and
clean CJK residue; the quality report surfaces untranslated counts.

**3.7 Automatic individual retry** â†’ **Rejected (already implemented).** The full
fallback ladder (retry â†’ split â†’ smaller split â†’ per-item) plus optional cloud
rescue is present in `translate_cues` and `rescue.py`.

### Section 4 â€” Subtitle timing & line quality

**4.1 Target-language line wrapping** â†’ **Rejected (already implemented).**
`postprocess.break_lines` performs English-aware wrapping (max 37 chars, 2 lines).

**4.2 CJK line breaking (`src/cjk.py` kinsoku)** â†’ **Approved (implemented,
module only).** The kinsoku-aware `break_cjk` helper was added to `src/cjk.py`.
It is *not* wired into the English-only output path (target is English, so
English wrapping applies), keeping it available for future bilingual/CJK-target
modes without changing current output.

**4.3 Enforce minimum duration & overlap snapping** â†’ **Deferred.**
`postprocess.snap_overlaps` already handles overlap; enforcing a 900 ms minimum
display is a timing change that needs media validation.

**4.4 Reading-speed checks** â†’ **Rejected (already implemented).** CPS checks with
warning/error thresholds exist in `src/subtitle_quality.py` (`analyze_cues`).
### Section 5 â€” ASS output improvements

**5.1 Use CJK fonts by language** â†’ **Approved (implemented).** Added
`FONT_BY_LANG` + `font_for_language` in `src/ass_io.py`; `write_ass` now picks a
CJK-capable font from the source language by default.

**5.2 Better ASS header** â†’ **Approved (implemented).** Added a `Title:` field to
`[Script Info]` plus `--ass-font` / `--ass-fontsize` CLI overrides.

**5.3 Optional bilingual ASS output** â†’ **Deferred.** Target is fixed to English;
bilingual output is a distinct feature for a future learning/QA mode.

### Section 6 â€” Quality report improvements

**6 (overlaps/glossary/duplicate checks)** â†’ **Deferred.** The existing report
already covers empty, CPS, chars, duration, lines, and untranslated counts.
Additional checks (overlap, glossary violations) are additive but untested on
real media; tracked as future work.

### Section 7 â€” Frontend improvements

**7.1 Four-pane UI / cue preview table** â†’ **Deferred.** Large UI rework with
binding surface; high regression risk. The current Dashboard/Settings split
already covers the pipeline controls.

**7.2 Suggested AppBridge API rework** â†’ **Deferred.** The bridge already exposes
the needed state/slots; a wholesale rewire is unnecessary churn.

**7.3 Improved Main.qml skeleton** â†’ **Deferred.** Cosmetic superset of the
current shell; low priority.

**7.4 Add structured progress from CLI** â†’ **Approved (implemented).** Added
`--json-progress` emitting `{"type":"progress",...}` lines while keeping the
final `Wrote N cues to ...` contract intact for the GUI worker regex.

**7.5 Improve `main.py` (Fusion/Material style)** â†’ **Deferred.** Style-picking is
a visual preference; the current `Basic` style is stable.

### Section 8 â€” Suggested new CLI flags

Proposed: `--source-lang`, `--translation-profile`, `--max-line-chars`,
`--max-lines`, `--max-cps`, `--min-cue-ms`, `--min-gap-ms`, `--ass-font`,
`--ass-fontsize`, `--bilingual`, `--json-progress`, `--auto-split-long-cues`.

- **`--ass-font` / `--ass-fontsize` / `--json-progress` / `--source-lang`** â†’
  **Approved (implemented).** `--ass-font`, `--ass-fontsize`, `--json-progress` are
  present in `translate.py::_parse_args` and covered by `tests/test_cli_flags.py`.
  `--source-lang` was added in this pass: it forces a YouTube source language
  (`src/fetch_subs.py::fetch_original_subtitles(preferred_lang=...)` +
  `_resolve_language_transcript`), raises an actionable error when the requested
  language has no track, and respects the "explicit user value wins" rule over
  CJK auto-detection. Covered by `tests/test_fetch_subs.py` +
  `tests/test_cli_flags.py`.
- **`--translation-profile`** â†’ **Deferred.** Same rationale as Â§3.3 (a prompt-layer
  change for all cloud calls; needs prompt-hygiene testing).
- **`--max-line-chars` / `--max-lines` / `--max-cps` / `--min-cue-ms` /
  `--min-gap-ms`** â†’ **Deferred.** The quality report (`src/subtitle_quality.py`)
  already *measures* these; *enforcing* them as timing/line adjustments changes cue
  durations and needs media validation before landing (see Â§4.3).
- **`--bilingual`** â†’ **Rejected.** Target language is fixed to English by design
  (same as Â§5.3).
- **`--auto-split-long-cues`** â†’ **Rejected.** Splitting changes cue count, which
  violates the core invariant "cue count out == cue count in" (see Â§9).

### Section 9 â€” Auto-splitting long translations

**Rejected.** The proposed `split_long_cue()` re-times and increases the number of
cues, directly contradicting two core invariants: **original timestamps are never
modified** and **cue count out == cue count in**. Long English lines are instead
handled by `postprocess` line breaking (which stays within a single cue and keeps
timing intact). Revisit only if a separate, opt-in "split mode" ever becomes a
requirement.

### Section 11 â€” Example commands

**Not applicable.** These are usage examples (anime / drama / Korean / YouTube-JA
pipelines). They map to existing, already-implemented flags and are covered by
`README.md`; nothing to implement.

### Section 12 â€” Fix `_gguf_check.py`

**Rejected / non-applicable.** `_gguf_check.py` no longer exists in the repository.
The shipped default is `Hy-MT2-1.8B-Q8_0` and the lossy `1.25Bit` file is never used,
so there is nothing to fix.

### Section 13 â€” High-impact roadmap

- **Phase 1 (quality stabilization)** â†’ **Approved (implemented).** Q8_0 default,
  explicit `--asr-lang`, reduced CJK cue chars, source-residue detection,
  retry + cloud rescue, strict final-line preservation, `--json-progress`.
- **Phase 2 (CJK-aware postprocessing)** â†’ **Approved (implemented).** `src/cjk.py`
  (detection + kinsoku line breaking), CJK language auto-detection, English line
  wrapping, timing/reading-speed *measurement* (quality report).
- **Phase 3 (ASS output)** â†’ **Approved (implemented), 1 deferred.** CJK font
  selection + `Title:` header done; bilingual output (5.3) deferred/rejected.
- **Phase 4 (GUI workflow)** â†’ **Partially approved.** JSON progress, settings
  persistence, open-output-folder, model/glossary pickers done. Cue preview/edit
  table and quality warning panel deferred (7.1).
- **Phase 5 (advanced quality)** â†’ **Deferred.** Two-pass translation, fuzzy TM,
  glossary-violation detection, auto long-cue splitting, vocal separation, Whisper
  fallback â€” all large/risky or would violate invariants (splitting â‡’ cue-count
  change); not in a non-breaking scope.

---

## Approved implementation checklist (atomic tasks)

- [x] **A1 â€” Robust CJK language detection.** Create `src/cjk.py`
      (`detect_cjk_language`, `detect_cjk_from_cues`, `contains_cjk`,
      `char_width`/`text_width`, `break_cjk`, kinsoku sets). Wire
      `translate.py` to use the larger-sample detector with `_detect_cjk_lang`
      retained as a fallback.
- [x] **A2 â€” Preserve `[untranslated]` marker.** Explicit guard in
      `_run_pipeline._sanitize_output`; regression tests.
- [x] **A3 â€” ASS CJK fonts + header.** `FONT_BY_LANG`, `font_for_language`,
      `Title:` in `[Script Info]`, `--ass-font`/`--ass-fontsize` CLI flags,
      `write_ass` signature extension; tests.
- [x] **A4 â€” Structured JSON progress.** Add `--json-progress` and
      `_json_progress()`; emit fetch/translate/write milestones; keep the final
      `Wrote N ...` line exact; tests.
- [x] **A5 â€” Force YouTube source language (`--source-lang`, this pass).** Add
      `--source-lang` to the CLI; thread it through
      `fetch_original_subtitles(preferred_lang=...)` with a new
      `_resolve_language_transcript` helper (manual â†’ generated, region-code
      aware, no silent wrong-language fallback); skip CJK auto-detection when the
      user forces a language; tests in `test_fetch_subs.py`/`test_cli_flags.py`.
- [x] **Verification.** Full `pytest` suite green; `py_compile` clean for all
      modified modules.

### Deferred backlog (not in this pass)
- ASR tuning presets (2.1), audio preprocessing (2.2), sound-tag note modes (2.3).
- Translation context (3.2) and profile (3.3) prompting.
- Glossary extended columns (3.4).
- Min-duration timing (4.3), bilingual ASS (5.3), extra quality checks (6).
- Frontend pane/table rework (7.1-7.3, 7.5).
- English line/timing *enforcement* (8 / 13-Ph5).

> **Scope note.** Approved items are all implemented. New implementations should
> stay non-breaking: never change cue count, never alter original timestamps, keep
> the final `Wrote N cues to ...` line exact for the GUI, and preserve the
> foreignization directive.

---

## Follow-up pass (from `FOLLOWUP_REVIEW.md`)

Correctness (P0) fixes implemented and verified in this pass:

- [x] **P0-1 â€” Cloud rescue endpoint selection.** `_resolve_rescue_config()`
      prefers dedicated `CLOUD_RESCUE_API_KEY` / `CLOUD_RESCUE_BASE_URL`, falls
      back to the original (pre-local) cloud config, and **never** re-uses the
      local llama.cpp `OPENAI_BASE_URL` for cloud rescue. Rescue disables with a
      clear warning when no usable cloud endpoint exists.
- [x] **P0-2 â€” Transactional environment mutation.** The local-mode branch
      snapshots `OPENAI_BASE_URL` (+ `OPENAI_API_KEY`) and restores them in a
      `finally`, so no stale local URL leaks into later cloud/GUI runs.
- [x] **P0-3 â€” TM closure on all exit paths.** `tm.close()` is now called on the
      strict-quality failure return and the translation-endpoint-error return, in
      addition to the success path.
- [x] **P0-4 â€” Final failed-cue accounting.** `failed_indices` is recomputed from
      the final post-processed `out_cues` via `_is_failed_text` (empty or
      `[untranslated]`), so the summary / rescue note / quality report / strict
      check reflect the real output.
- [x] **P0-5 â€” Newline escaping.** Verified `\n` â†” `\N` conversion is correct in
      `translate.py` (ASS/SRT branches); no syntax defect.
- [x] **P0-6 â€” Documentation/code defaults.** Fixed stale CLI-table and QSettings
      defaults in `AGENT_DOCUMENTATION.md` (`--batch` 40â†’8,
      `--asr-max-segment-ms` 7000â†’6000, `--asr-min-silence-s` 0.20â†’0.25,
      `--asr-max-cue-duration-ms` 3000â†’3200; added `--asr-max-cue-chars-cjk` /
      `asr/maxCueCharsCjk` 48; documented `CLOUD_RESCUE_API_KEY` /
      `CLOUD_RESCUE_BASE_URL`).
- [x] **P0-7 â€” Timestamps â†” overlap snapping reconciled.** Documentation now
      states the single exception: overlap snap trims a cue's `end` only when
      consecutive cues overlap, never below 300 ms (README + AGENT_DOC).
- [x] **P1-1 â€” Source-language precedence.** Added `_is_known_source_code()` so a
      specific fetched/ASR code (`zh-TW`, `ja`, `ko`, `yue`, â€¦) is preserved and
      script-ratio detection runs only for missing/auto/unknown languages.

Not implemented this pass (tracked backlog): ASR presets (P1-3), translation
context window (P1-4), extended CJK quality-report checks (P1-5), GUI JSON-progress
consumption (P1-6), granular progress callback (P1-7), bundled CJK font loading
(P1-8), and frontend cue-table/quality-panel (P2-1/2-2). These are larger, higher-risk
changes; several need benchmark/media validation before landing. See
`FOLLOWUP_REVIEW.md` for details and acceptance criteria.

