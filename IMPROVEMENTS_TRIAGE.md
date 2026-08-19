# Improvements Triage

> Reviewed against the current working tree (commit `3dce98f`, 251-test suite).
> Each recommendation from `improvements.txt` is categorized as **Approved**,
> **Rejected**, or **Deferred**, with the reasoning grounded in the actual code.
> Approved items are broken down into a sequential, atomic task checklist below.

---

## Summary

| Category | Count | Notes |
|---|---:|---|
| **Approved** (implemented) | 4 | Higher-value, non-breaking, aligned with project conventions |
| **Deferred** | 10 | Reasonable ideas, but need benchmark data, are large/risky, or are not core |
| **Rejected** | 6 | Already implemented, not applicable, or contradict project invariants |

---

## Per-item triage

### Section 1 — Critical quality issues

**1.1 Avoid extremely low-bit translation models for CJK** → **Approved (already
satisfied).** The code already defaults to `Hy-MT2-1.8B-Q8_0` everywhere
(`--local-model-name` default in `translate.py`, `_LOCAL_MODEL` in
`backend/bridge.py`). The `1.25bit` file referenced by `_gguf_check.py` is a
scratch script, not the shipped default.

**1.2 Improve CJK language detection** → **Approved (implemented).**
Added `src/cjk.py` (`detect_cjk_language`, `detect_cjk_from_cues`, `contains_cjk`,
kinsoku line breaking) and wired the CLI (`translate.py`) to classify from a large
sample (up to 80 cues) instead of 5, keeping `_detect_cjk_lang` as a fallback.

**1.3 Preserve the untranslated marker during sanitization** → **Approved
(implemented).** Added an explicit guard in `_run_pipeline._sanitize_output` and
a test ensuring `[untranslated]` survives the tag-stripping / fansub-markup pass.

### Section 2 — CJK ASR improvements

**2.1 Recommended SenseVoice defaults for CJK** → **Deferred.** These are
tuning presets. The knobs already exist as CLI flags/env vars
(`--asr-max-cue-chars-cjk`, `--asr-max-segment-ms`, etc.), and changing hard
defaults risks regressions without benchmark evidence. Tracked as future work.

**2.2 Optional audio preprocessing (loudnorm/denoise)** → **Deferred.** New
ffmpeg-filter pipeline adds complexity and runtime; needs a benchmark to prove
quality gain before landing.

**2.3 Sound-tags handling (`--sound-tags`) modes** → **Deferred.** The `strip`
behavior already exists (`--asr-no-tags` / `--asr-keep-tags`). The
`keep-as-note` / `keep-ass-comments` modes are a larger feature with no immediate
consumer.

### Section 3 — Translation improvements

**3.1 Use cue IDs and strict output mapping** → **Rejected (already
implemented).** The numbered-item protocol (`1. text` → `1. translation`) already
enforces alignment, with a per-item fallback ladder and misalignment handling
(`_numbered_block` / `_parse_numbered` / `_translate_batch`).

**3.2 Add previous/next context** → **Deferred.** Improving pronoun consistency
is valuable, but it changes the prompt for every cloud/Hy-MT2 call and risks the
foreignization directive and output-format stability. Needs staged validation.

**3.3 Add a translation style/profile** → **Deferred.** Additive, but touches the
system prompt for all cloud calls; deferred until prompt-hygiene testing is set up.

**3.4 Improve glossary handling (note/case_sensitive columns)** → **Deferred.**
The glossary hash is already part of the TM key (see `translation_memory.make_key`
and the `glossary_hash` flow). Extended TSV columns are a nice-to-have, not core.

**3.5 Translation memory quality metadata** → **Rejected (not needed now).** The
existing schema (`hits`, `last_used_at`, `created_at`) plus the
`_purge_poisoned_entries` pass already serve the exact-match cache; quality-score
columns add unused complexity.

**3.6 Add source-residue validation** → **Rejected (already implemented).**
`looks_untranslated` plus `postprocess.strip_residual_cjk` already detect and
clean CJK residue; the quality report surfaces untranslated counts.

**3.7 Automatic individual retry** → **Rejected (already implemented).** The full
fallback ladder (retry → split → smaller split → per-item) plus optional cloud
rescue is present in `translate_cues` and `rescue.py`.

### Section 4 — Subtitle timing & line quality

**4.1 Target-language line wrapping** → **Rejected (already implemented).**
`postprocess.break_lines` performs English-aware wrapping (max 37 chars, 2 lines).

**4.2 CJK line breaking (`src/cjk.py` kinsoku)** → **Approved (implemented,
module only).** The kinsoku-aware `break_cjk` helper was added to `src/cjk.py`.
It is *not* wired into the English-only output path (target is English, so
English wrapping applies), keeping it available for future bilingual/CJK-target
modes without changing current output.

**4.3 Enforce minimum duration & overlap snapping** → **Deferred.**
`postprocess.snap_overlaps` already handles overlap; enforcing a 900 ms minimum
display is a timing change that needs media validation.

**4.4 Reading-speed checks** → **Rejected (already implemented).** CPS checks with
warning/error thresholds exist in `src/subtitle_quality.py` (`analyze_cues`).
### Section 5 — ASS output improvements

**5.1 Use CJK fonts by language** → **Approved (implemented).** Added
`FONT_BY_LANG` + `font_for_language` in `src/ass_io.py`; `write_ass` now picks a
CJK-capable font from the source language by default.

**5.2 Better ASS header** → **Approved (implemented).** Added a `Title:` field to
`[Script Info]` plus `--ass-font` / `--ass-fontsize` CLI overrides.

**5.3 Optional bilingual ASS output** → **Deferred.** Target is fixed to English;
bilingual output is a distinct feature for a future learning/QA mode.

### Section 6 — Quality report improvements

**6 (overlaps/glossary/duplicate checks)** → **Deferred.** The existing report
already covers empty, CPS, chars, duration, lines, and untranslated counts.
Additional checks (overlap, glossary violations) are additive but untested on
real media; tracked as future work.

### Section 7 — Frontend improvements

**7.1 Four-pane UI / cue preview table** → **Deferred.** Large UI rework with
binding surface; high regression risk. The current Dashboard/Settings split
already covers the pipeline controls.

**7.2 Suggested AppBridge API rework** → **Deferred.** The bridge already exposes
the needed state/slots; a wholesale rewire is unnecessary churn.

**7.3 Improved Main.qml skeleton** → **Deferred.** Cosmetic superset of the
current shell; low priority.

**7.4 Add structured progress from CLI** → **Approved (implemented).** Added
`--json-progress` emitting `{"type":"progress",...}` lines while keeping the
final `Wrote N cues to ...` contract intact for the GUI worker regex.

**7.5 Improve `main.py` (Fusion/Material style)** → **Deferred.** Style-picking is
a visual preference; the current `Basic` style is stable.

---

## Approved implementation checklist (atomic tasks)

- [x] **A1 — Robust CJK language detection.** Create `src/cjk.py`
      (`detect_cjk_language`, `detect_cjk_from_cues`, `contains_cjk`,
      `char_width`/`text_width`, `break_cjk`, kinsoku sets). Wire
      `translate.py` to use the larger-sample detector with `_detect_cjk_lang`
      retained as a fallback.
- [x] **A2 — Preserve `[untranslated]` marker.** Explicit guard in
      `_run_pipeline._sanitize_output`; regression tests.
- [x] **A3 — ASS CJK fonts + header.** `FONT_BY_LANG`, `font_for_language`,
      `Title:` in `[Script Info]`, `--ass-font`/`--ass-fontsize` CLI flags,
      `write_ass` signature extension; tests.
- [x] **A4 — Structured JSON progress.** Add `--json-progress` and
      `_json_progress()`; emit fetch/translate/write milestones; keep the final
      `Wrote N ...` line exact; tests.
- [x] **Verification.** Full `pytest` suite green (251 passed); `py_compile`
      clean for all modified modules.

### Deferred backlog (not in this pass)
- ASR tuning presets (2.1), audio preprocessing (2.2), sound-tag note modes (2.3).
- Translation context (3.2) and profile (3.3) prompting.
- Glossary extended columns (3.4).
- Min-duration timing (4.3), bilingual ASS (5.3), extra quality checks (6).
- Frontend pane/table rework (7.1-7.3, 7.5).
