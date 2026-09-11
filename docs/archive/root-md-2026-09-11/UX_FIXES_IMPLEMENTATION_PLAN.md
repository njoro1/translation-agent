# UX Fixes — Implementation Plan

**Source:** `UX_RESEARCH_REPORT.md` (27 findings U-01…U-27, solutions S-01…S-13)
**Date:** 2026-09-08
**Toolchain:** `C:\Users\Njoro\AppData\Local\Programs\Python\Python312\python.exe` (PySide6 6.11.1, pytest 9.1.1)
**Baseline:** `pytest tests/ -q` → 348 passed

---

## 0. Guiding principles

1. **Bridge owns state, QML owns presentation.** Every new UI capability lands as a
   `Property`/`Signal`/`Slot` on `AppBridge` first, then is bound in QML. Nothing
   user-visible is computed in QML from raw pipeline data.
2. **Never break the three known-good fixes** (Run/Stop never disabled, elapsed timer via
   `Connections`, full-pane `DropArea`). They are covered by regression tests.
3. **Null-safe formatting in Python, not QML.** QML binding exceptions are silent; format
   in Python where they are testable.
4. **Every fix gets a test.** The report's root cause for recurring UX debt is "1 of 22
   test files touches the UI". This plan raises that floor.
5. **Files are written UTF-8 without BOM**, ASCII-only where practical; a CI-style test
   enforces it (that is the root cause of U-05).

---

## 1. Challenge-by-challenge approach

### S-01 · U-01 — Make Review editable and close the job loop *(severity 4, P0)*

**Problem.** `CuePreviewTable.qml` is copy-only. Users cannot fix a mistranslation without
leaving the app and re-running the whole pipeline.

**Approach.**
- `backend/models/results.py`
  - `CueResultModel` gains `_original` snapshot, `setData()` (writes `text`, emits
    `dataChanged` + `editedCountChanged`), `EditedRole` (bool), `hasErrorRole`,
    `tagsRole`, plus `editedCount`, `revertCue(row)`, `revertAll()`, and
    `load(cues, issues_by_cue=None)` so per-cue error/warning tags are available to the
    filter proxy (needed by S-05).
  - `CueFilterProxyModel.filterMode` accepts `("all", "errors", "failed", "warnings")`.
    `"errors"` matches cues carrying a `*_error` tag. `"failed"` is renamed in the UI to
    **Untranslated** (see U-08).
- `backend/bridge.py`
  - `cueEditedCount` property (mirrors model), `dirtyChanged` signal.
  - `Slot(str) saveEditedSubtitles(path)` → rebuilds `src.srt_io.Cue` list from the model
    (original timing, edited text) and writes SRT or ASS according to `outputFormat`.
  - `Slot() saveEditedSubtitlesToDefault()` → writes back to the resolved output path.
  - `Slot() recheckQuality()` → re-runs `src.subtitle_quality.build_report` on the edited
    cues **without** re-translating; refreshes badges + issue model.
  - `Slot(str,str,bool) replaceInCues(find, replace, useRegex)` → bulk find/replace.
  - `Slot() openInExternalEditor()` → `QDesktopServices.openUrl` on the output path.
  - `Slot() revertAllEdits()`.
- `ui/qml/components/CuePreviewTable.qml` — rewritten:
  - Translation cell becomes an inline `TextInput` (single click focus, `Enter` commit,
    `Esc` revert). `Double-click` remains copy.
  - Toolbar adds **Save subtitles**, **Save as…**, **Re-check**, **Revert all**,
    **Open in external editor**, and a find/replace disclosure.
  - Counter reads `Showing X of Y cues` with a clear-filter chip.
  - `ElideRight` (not `ElideMiddle`), `maximumLineCount: 3`.
  - Status cell renders **icon + text** (not colour alone).

**Verification.** Unit tests for `setData`/`editedCount`/revert/filters; bridge tests for
save-back writing valid SRT and for `recheckQuality` changing badge counts; QML smoke test
instantiating the component.

---

### S-02 · U-02, U-20 — Structured error surface *(severity 4, P0)*

**Problem.** Every failure collapses to *"Finished with errors (exit N). See the log."*
and the log drawer is collapsed by default.

**Approach.**
- `backend/bridge.py`
  - `_FAILURE_PATTERNS`: ordered list of `(code, regex, title, remediation)` covering
    `AUTH` (401/403/invalid api key), `NETWORK` (connection/timeout/DNS),
    `SOURCE_UNAVAILABLE` (yt-dlp unavailable/private/removed),
    `MISSING_DEPENDENCY` (ffmpeg/yt-dlp not found), `MODEL_DOWNLOAD`, `MODEL_LOAD`
    (llama.cpp/GGUF), `ASR_FAILED`, `TRANSLATE_FAILED`, `WRITE_FAILED`
    (PermissionError/read-only), `CANCELLED`, `UNKNOWN`.
  - `_classify_failure(rc, log_text) -> dict` scans the **last** ~200 lines first (most
    specific errors appear last), falls back to `UNKNOWN`.
  - New signal `failureOccurred(code, title, detail, remediation)` plus properties
    `failureCode/Title/Detail/Remediation` and `failureActive`.
  - `_on_finished` emits it and **auto-expands the log** (`logVisible = True`) when
    the run failed (not when cancelled).
  - Remediation actions are QML-side: `AUTH` → `openAdvanced("apiKey")`,
    `MISSING_DEPENDENCY` → open the docs URL, `MODEL_DOWNLOAD` → `downloadLocalModel()`,
    else → `Retry`.
- New `ui/qml/components/ErrorCard.qml` — inline card in the Run tab result column:
  cause in plain language, one remediation button, "Show details" disclosing the log excerpt.
- `LogDrawer.qml` — badge counts now come from `appBridge.logErrorCount` /
  `appBridge.logWarnCount` (fixes U-19 and U-20 together); adds **"Jump to first error"**.

**Verification.** Table-driven test over ~15 representative log samples asserting the
expected code; test that `logVisible` flips True on failure.

---

### S-03 · U-03a, U-03b — Honest Readiness checklist *(severity 3, P0)*

**Approach.**
- `backend/bridge.py` exposes `outputDirWritable` (directory exists + writable, or blank),
  and `readinessRows` is computed in **Python** as a list of
  `{id, label, state, hint}` where `state ∈ {"ok","n/a","todo"}` — no more QML
  functions that hardcode `true`.
- `ReadinessChecklist.qml` becomes a thin renderer over `appBridge.readinessRows`:
  - `ok` → green ✓, `todo` → amber ✕ + hint, `n/a` → dimmed "—" + "Not needed for this mode".
- The "Translation backend reachable" row becomes real: in cloud modes it is `ok` when a
  key/base URL/model is present **or** `.env` supplies one; in offline mode it is
  `localModelReady`.

**Verification.** Tests for all three modes × both backend states; asserts no row is
permanently `ok`.

---

### S-04 · U-04, U-17 — One mode-aware language control *(severity 3, P0)*

**Problem.** Header `Lang` → `--source-lang`; Run-tab `ASR lang` → `--asr-lang`. Both
visible in local modes.

**Approach (preferred option from the report).**
- **YouTube mode:** the header control is labelled **Source language** and binds
  `sourceLang` (`--source-lang`).
- **Local modes:** the header control is labelled **Spoken language** and binds
  `asrLanguage` (`--asr-lang`). The Run-tab `ASR lang` row is **removed** (merged).
- A new row in Advanced → **Translation source language (override)** binds
  `sourceLang`, default `""` = *same as spoken language*. A live hint under the header
  control states which flag is in play.
- The empty `""` entry becomes the literal string **`Auto`**, mapped to `""` at the
  bridge boundary (fixes U-17).
- `bridge.languageControlLabel` / `bridge.languageControlHint` expose the mode-aware text.

**Verification.** Existing `test_pipeline_modes.py` argv assertions still hold; new tests
assert the header control writes the right attribute per mode and that `Auto` maps to `""`.

---

### S-05 · U-07, U-08 — Link Quality to Review *(severity 3/2, P1)*

**Approach.**
- `QualityIssuesModel` gains `FriendlyTypeRole` (`issueFriendly`) so the `Type` column
  shows the human phrase; the raw tag stays in the tooltip via `RawTypeRole`.
- Issue rows become clickable → `appBridge.revealCue(cueNumber)`:
  sets `focusCueIndex`, clears the Review filter, sets search to `""`, switches the tab
  (`requestTab(1)`), and the table scrolls to + flash-highlights the row.
- `CueFilterProxyModel` gains `"errors"`; the Review chip labels become
  **All / Errors / Untranslated / Warnings** — "Failed" is retired so it no longer
  collides with the status pill's "Failed run".

**Verification.** Filter tests for `errors`; friendly-message test; `revealCue` sets the
expected bridge state.

---

### S-06 · U-14, U-16, U-22 — Explain the technical controls *(severity 3/2, P1)*

**Approach.**
- `AdvancedDrawer.qml`
  - Tooltips on all 8 ASR numeric fields (units, safe range, symptom of getting it wrong),
    following the file's existing `ToolTip.visible/delay/text` pattern.
  - The 8 fields move under a **Segmentation (advanced)** sub-group, collapsed by default,
    with **Reset to preset defaults**.
  - `Component.onCompleted` assignments are replaced with declarative bindings
    (`text: appBridge.asrMaxSegmentMs`) guarded so typing is not clobbered mid-edit
    (fixes U-15): bind only when the field is not focused.
  - Mo jibake `…` → `…` (also U-05).
- `PresetPicker.qml` + bridge: expose `resolvedPresetLabel` so after a run the UI can say
  *"Auto → detected: anime"*. Bridge gains `lastResolvedPreset`, set from the result JSON
  when available, otherwise echoing the chosen preset.
- Tooltip coverage raised on remaining unlabelled controls.

---

### S-07 · U-11 — Make waiting legible *(severity 2, P1)*

**Approach.**
- `backend/bridge.py` records `progressStage` history: `stageSequence` (ordered unique
  stages seen this run), `stageStartedAt` (epoch ms), `stageElapsedSec` (1 s timer on the
  bridge so QML never has to derive it), and `estimatedRemainingSec` from a persisted
  history of `cue_count → wall_seconds` stored in QSettings (`run/historyMsPerCue`).
- `ProgressPanel.qml` renders a **named stage list** (Fetch → Transcribe → Translate →
  Write → Check) with the current stage highlighted and completed stages ticked, plus a
  per-stage elapsed timer that shows even when the total is unknown, and a heuristic
  "about N min" line when history exists.

---

### S-08 · U-12, U-13 — Clarify the YouTube flow *(severity 3/2, P1)*

**Approach.**
- `SectionPanel.qml` gains `collapsible` / `collapsed` and a disclosure caret.
  `YouTubeVideoPanel` becomes collapsible and **collapsed by default**, titled
  **"Also download the video (optional)"** — it is a side feature, not run configuration.
- `YouTubeSubtitlePanel.qml` gains the data-flow sentence:
  *"Run translates the English subtitle downloaded here. Clear it to transcribe the audio
  instead."*
- `humanSize()` unknown-size text is unified to a single string used in both the row and
  the tooltip (*"Size is calculated during download"*).
- A step strip **1 Paste link → 2 Get subtitles → 3 Translate** is added above the
  YouTube panels, driven by `appBridge.youtubeStep`.

---

### S-09 · U-05, U-06, U-15, U-21, U-23 — Correctness and robustness

| Fix | File | Change |
|---|---|---|
| U-05 mojibake ×7 | `AdvancedDrawer.qml`, `CuePreviewTable.qml` | `…` → `…`; files rewritten without BOM |
| U-25 BOM ×15 | all QML | rewrite without BOM; test enforces it |
| U-06 `toFixed` | `QualityPanel.qml` + bridge | use `appBridge.qualityAverageCpsText` (formatted in Python, `—` when unavailable) |
| U-23 `NameError` | `main.py` | add `import logging`; add a regression test |
| U-15 stale fields | `AdvancedDrawer.qml` | declarative bindings, focus-guarded |
| U-21 popup height | `CompactComboBox.qml` | `implicitHeight: Math.min(contentHeight, 320)` |

---

### S-10 · U-18 — Accessibility and keyboard foundation *(severity 3, P1)*

**Approach.**
- `Theme.qml` gains a **light palette** (all colours become `dark ? … : …` expressions
  driven by `Theme.themeName`), a **comfortable density** (`fieldHeight` 32→36, `fontBoost`
  +2), and `reducedMotion`.
- `AppBridge` persists `themeName` and `comfortable`; `AppHeader` gets a theme toggle.
- `Accessible.name` / `Accessible.role` / `Accessible.description` added to every
  interactive control; `CompactTextField` / `CompactComboBox` accept a `label` property
  that is wired to `Accessible.name` so callers set it once.
- `Main.qml` adds `Shortcut`s: `Ctrl+R` run, `Ctrl+.` cancel, `Ctrl+F` search cues,
  `Ctrl+1/2/3` tabs, `Ctrl+L` log, `Ctrl+S` save subtitles, `Ctrl+Shift+F` find/replace.
- `CuePreviewTable` rows: `↑/↓` move, `Enter`/`F2` edit, `Esc` cancel edit.
- Row states get **icon + text**, not colour alone; animations honour `Theme.reducedMotion`.
- Focus rings: `border.color: activeFocus ? Theme.accent : Theme.border` already exists on
  text fields — extended to buttons and list rows.

---

### S-11 · U-09, U-10 — Review legibility *(severity 2, P2)*

Covered inside the S-01 rewrite: `ElideRight`, `maximumLineCount: 3`,
`Showing X of Y cues`, active-filter chip with one-click clear, hover tooltip, and an
expand chevron for long lines.

---

### S-12 · U-19 — Performance *(severity 2, P2)*

- `AppBridge` maintains `logErrorCount` / `logWarnCount` incrementally in `_append_log`
  (one pass over the *new* text only) and caps `logText` at the last 5,000 lines,
  prepending a `… log truncated …` marker. Removes the O(n) per-append regex in QML.
- Log classification broadened (U-20) to tracebacks and known third-party patterns.

---

### S-13 · U-25, U-26, U-27 — Hygiene *(severity 1, P3)*

- Re-encode `FOLLOWUP_REVIEW.md`, `REMAINING_RECOMMENDATIONS.md`, `IMPROVEMENTS_TRIAGE.md`
  (mojibake → correct characters).
- Re-indent the result card `GridLayout` in `Main.qml`.
- Add `.editorconfig` (UTF-8 no BOM, LF, 4 spaces) and a lint test.

---

## 2. Test strategy (raises UI coverage from 1/22 files)

New `tests/test_ui_models.py`
- `CueResultModel`: setData, editedCount, revert, tags, load with issues.
- `CueFilterProxyModel`: all/errors/failed/warnings + search.
- `QualityIssuesModel`: friendly type, errors-first ordering.

New `tests/test_ux_bridge.py`
- Failure classification table (≈15 samples).
- Readiness rows per mode (no permanently-`ok` row).
- Language control mapping per mode; `Auto` → `""`.
- Log counters incremental + truncation.
- Save-back produces a parseable SRT; recheck updates badges.
- `qualityAverageCpsText` never throws and returns `—` when unset.

New `tests/test_ui_hygiene.py`
- No QML file starts with a BOM; no `…`-style mojibake anywhere in `ui/` or `*.md`.
- `main.py` imports `logging`.
- Every `Button {` in the rewritten components carries an `Accessible.name` (best-effort
  structural check).

New `tests/test_qml_smoke.py`
- Under `QT_QPA_PLATFORM=offscreen`, instantiate every QML component (and `Main.qml`) in a
  `QQmlApplicationEngine` and fail on any QML warning/error. This is the guard that would
  have caught U-06 and would catch any future binding exception.
- Skipped automatically if the offscreen platform is unavailable.

Existing `tests/test_pipeline_modes.py` is preserved and must stay green.

---

## 3. Execution order

| Phase | Content | Depends on |
|---|---|---|
| **P0** | Theme foundation + bridge state/signals plumbing | — |
| **P1** | S-09/S-13 hygiene & correctness (cheap, high visibility) | P0 |
| **P2** | S-02 error surface + S-12 log performance | P0 |
| **P3** | S-03 readiness + S-04 language controls | P0 |
| **P4** | S-01 Review editing (largest change) | P0, P2 |
| **P5** | S-05 Quality↔Review linkage | P4 |
| **P6** | S-06 tooltips/preset, S-07 wait legibility, S-08 YouTube flow | P0 |
| **P7** | S-10 accessibility, keyboard, light theme, density | P0, all UI |
| **P8** | Tests, verification, docs update | all |

---

## 4. Risk register

| Risk | Mitigation |
|---|---|
| Light theme breaks contrast in custom-coloured labels | Only semantic tokens change; every colour goes through `Theme`. Contrast pairs are listed in a test. |
| Declarative bindings fight user typing in ASR fields | Bind only while the field is **not** `activeFocus`. |
| `saveEditedSubtitles` overwrites the user's file | Save writes to the resolved output path only via an explicit button; "Save as…" opens a dialog; the model tracks `dirty` so the button is disabled when there is nothing to save. |
| QML smoke test is flaky headless | Skipped when the offscreen platform is unavailable; warnings are filtered to the app's own QML files only. |
| Removing the Run-tab `ASR lang` row breaks existing tests | `test_pipeline_modes.py` asserts on `_build_run_config()` argv, not on QML — unaffected. |
