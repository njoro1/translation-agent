# Implementation Task Tracker

> Companion to `updated implementation plan.md`. Updated as work progresses.
> Legend: [ ] pending · [~] in progress · [x] done

---

## Phase 0 — Baseline Safety & Repository Hygiene

- [x] Create `pytest.ini`
- [x] Create `tests/__init__.py`
- [x] Baseline tests for `src/srt_io.py` (timestamps, roundtrip, sanitization)
- [x] Baseline tests for `src/translate.py` (`_numbered_block`, `_parse_numbered`, `_is_hy_mt2`)
- [x] `pytest` runs successfully with no network (251 passed)

## Phase 1 — Translation Batching & Hy-MT2 Reliability

- [x] Create `src/batching.py` (`is_cjk_language`, `estimate_text_weight`, `chunk_texts`)
- [x] Add Hy-MT2 batching constants in `src/translate.py`
- [x] Add `_translate_group` fallback ladder (retry → split → smaller split → per-item)
- [x] Modify `translate_cues` for dynamic batching + TM/glossary/rescue hooks
- [x] Tests for batching order preservation, oversized item, empty input, CJK detection

## Phase 2 — Glossary & Translation Memory

- [x] Create `src/glossary.py` (`load_glossary`, `format_glossary`, `glossary_hash`)
- [x] Create `src/translation_memory.py` (SQLite-backed `TranslationMemory`)
- [x] Inject glossary into `build_system_prompt` (cloud) and Hy-MT2 user prompt
- [x] Integrate TM into `translate_cues` flow
- [x] Tests for glossary parsing, TM put/get, graceful failure

## Phase 3 — Local Server Improvements

- [x] Add `warmup_local_server()` in `src/local_server.py`
- [x] Add `LLAMA_SERVER_THREADS` / `LLAMA_SERVER_MLOCK` env support
- [x] Add `_start_with_fallback_flags()` safe optional-flag handling
- [x] Wire warmup into CLI `translate.py`

## Phase 4–5 — ASR Tag Stripping, CJK Limits & Cue Splitting

- [x] Add `asr_max_cue_chars_cjk` parameter & `FUNASR_MAX_CUE_CHARS_CJK` env
- [x] Strip ASR tags by default; `--asr-keep-tags` to disable
- [x] Punctuation-aware splitting with CJK-aware limits in `_segment_to_cues`
- [x] Tests for splitting: short not split, long CJK split, punctuation preference

## Phase 6 — Subtitle Quality Diagnostics

- [x] Create `src/subtitle_quality.py` (`analyze_cues`, `build_report`, `CueIssue`, thresholds)
- [x] Add `--quality-report` CLI flag & JSON report output
- [x] Tests for CPS, overlong, too-short, line-count, empty-text detection

## Phase 7 — Optional Cloud Rescue

- [x] Create `src/rescue.py` (`rescue_failed_cues`)
- [x] Add `--cloud-rescue`, `--cloud-rescue-model`, `--cloud-rescue-batch` CLI flags
- [x] Integrate rescue into `translate_cues` (disabled by default)

## Phase 8 — CLI Updates

- [x] Add all new CLI flags to `translate.py` `_parse_args`
- [x] Add all new env vars with documented defaults

## Phase 9 — GUI Changes

- [x] Add new AppBridge properties + QSettings persistence
- [x] Update `_build_run_config` to map GUI → CLI flags
- [x] Add QML controls in `SettingsView.qml` (Advanced/Quality section)
- [x] Remove redundant "No tags" checkbox (only "Keep ASR tags" per plan §17.3)
- [x] Add indicator text in `DashboardView.qml`

## Phase 10 — Model Download & Documentation

- [x] Update model downloader to prefer `Hy-MT2-1.8B-1.25bit-v2.gguf` (v1 fallback retained)
- [x] `resolve_local_model_path` prefers v2 → v1 → unambiguous Hy-MT2 GGUF
- [x] Verify `_is_hy_mt2` case-insensitivity (recognizes `hy-mt2`/`hy_mt2` variants)
- [x] Update `AGENT_DOCUMENTATION.md` and `README.md`

## Phase 11 — Benchmark Harness

- [x] Create `tools/benchmark.py`
- [x] Create `benchmark/cases.json` and `benchmark/README.md`
- [x] Wire `--cloud-rescue` (model/batch) into the benchmark translation call (credential-guarded)
- [x] Capture reliability metrics via stdout parsing: batch_failures, batch_splits, per_item_fallbacks, cache_hits, rescue_attempts, rescue_successes

## Phase 12 — Full Test Suite

- [x] `tests/test_srt_io.py`
- [x] `tests/test_translate_parsing.py`
- [x] `tests/test_batching.py`
- [x] `tests/test_glossary.py`
- [x] `tests/test_translation_memory.py`
- [x] `tests/test_subtitle_quality.py`
- [x] `tests/test_local_asr_splitting.py`

## Final Validation

- [x] Full `pytest` suite passes (251 passed)
- [x] CLI smoke test: `python translate.py --help` exits 0
- [x] Benchmark smoke test: `python tools/benchmark.py --help` exits 0
- [x] `py_compile` passes for all modified Python modules
- [x] No Whisper.cpp / GPU / breaking-signature changes introduced

## Phase 13 — CJK detection & fansub tooling improvements (this pass)

- [x] Add `src/cjk.py` (script-ratio `detect_cjk_language` / `detect_cjk_from_cues`, `contains_cjk`, `char_width`/`text_width`, kinsoku `break_cjk`)
- [x] Wire CLI auto-detection to the larger cue sample; keep `_detect_cjk_lang` fallback
- [x] Guard `[untranslated]` marker in the final output sanitizer
- [x] Add `src/ass_io.py` `FONT_BY_LANG` / `font_for_language` + `Title:` header
- [x] Add `--ass-font` / `--ass-fontsize` CLI flags and `write_ass` parameters
- [x] Add `--json-progress` structured progress lines (final `Wrote N cues` line unchanged)
- [x] Tests: `test_cjk.py`, `test_cli_flags.py`, extended `test_fansub_upgrade.py`
- [x] Produce `IMPROVEMENTS_TRIAGE.md` (Approved / Rejected / Deferred backlog)

