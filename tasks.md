# tasks.md — UI Redesign Implementation Tasks

Companion to `IMPLEMENTATION_PLAN.md`. Source of truth: `ui_review.txt` v1.0.

**How to use this file**

* Work top to bottom. Phases are ordered by dependency, not by size.
* `T-x.y` = task. Indented `[ ]` lines = subtasks. A task is done only when its
  **Done when** line is satisfied and its tests pass.
* Do not start a phase before the previous phase's gate passes.
* Do not edit `ui/qml/archive/` — retired dead code.
* Every `appBridge` call from QML must target a `@Slot`.

**Test command**

```
BT="C:/Users/Njoro/AppData/Local/Temp/ta_$(date +%s)"; mkdir -p "$BT"
C:\Users\Njoro\AppData\Local\Programs\Python\Python312\python.exe -m pytest \
  --basetemp="$BT" -q -p no:randomly
```

The basetemp must be **fresh and pre-created** every run. Reusing one makes pytest
try to delete the existing tree at exit; the sandbox's safe-delete shim refuses
with `OSError [Errno 53] The network path was not found` and pytest reports a bogus
`error` on whichever test was setting up. That is the whole explanation for every
phantom "N errors" row and for the full-suite run that used to die at ~70 %.

Check `df -h /c` first. A Git-Bash `--basetemp` (`/c/Users/...`) breaks `tmp_path`
fixtures instead.

**Status key:** `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked

---

## Phase 0 — State model & binding hygiene

**Gate:** flipping strict gate on Run updates the Quality header switch, the Quality
body pill, the Settings switch and the top-bar strip in the same frame, with no
reload. Same for theme, mode and spoken language. A widget that has been interacted
with once still mirrors a later external change.

### T-0.1 — Add binding-safe controls (RC-1)
**Notes.** `SegmentedControl` needed no re-sync hook: its `current` is bound by
the *caller* and the control never assigns it (it only emits `activated`), so
the binding is never destroyed. What it gained instead is `disabledIds`, so an
option that cannot be picked renders muted and inert — that is what makes the
fourth matrix cell honest (T-3.1).


Files: `ui/qml/components/BoundComboBox.qml` (new), `BoundField.qml` (new),
`ui/qml/qmldir`, `ui/qml/components/SegmentedControl.qml`

- [x] Create `BoundComboBox.qml` with `storeValue`, `syncOn`, `_apply()` and a
      `Connections { target: appBridge }` re-sync block. Re-apply on
      `onFormChanged` **and** `onPipelineModeChanged`.
- [x] Create `BoundField.qml` for editable text/`editText` controls — re-applies
      the store value on notify, so typing does not destroy the mirror.
- [x] Add an `onActivated`-safe re-sync to `SegmentedControl.qml` (`current:` is a
      binding destroyed by user interaction).
- [x] Register both in `ui/qml/qmldir`.
- [x] Document the pattern in a comment block at the top of each file, naming RC-1.

**Done when:** a widget wrapped in `BoundComboBox` follows a programmatic bridge
change *after* the user has picked a value from it.

### T-0.2 — Migrate every broken binding
**Notes.** The plan's list missed two sites, found by the new static guard in
`tests/test_ui_bindings.py`: `YouTubeVideoPanel.qml:246,271` bound `currentIndex:
Math.max(0, indexOfValue(appBridge.…))` on the codec and resolution pickers.
Both are now `BoundComboBox`, and `applyStoreValue()` compares as strings so the
old `720`-vs-`"720"` snap-back cannot return.


Files: `SettingsPage.qml`, `RunPage.qml`, `PresetPicker.qml`, `CommandBar.qml`

- [x] `SettingsPage.qml:272-290` context mode → `BoundComboBox`
- [x] `SettingsPage.qml:308-324` translation memory → `BoundComboBox`
- [x] `SettingsPage.qml:506-524` FFmpeg preprocess → `BoundComboBox`
- [x] `SettingsPage.qml:492-500` spoken language → `BoundField`
- [x] `SettingsPage.qml:163-167` theme, `:173-177` density → re-synced `SegmentedControl`
- [x] `RunPage.qml:481-487` output format → `BoundComboBox`
- [x] `RunPage.qml:662-683` context mode → `BoundComboBox`
- [x] `RunPage.qml:703-719` translation memory → `BoundComboBox`
- [x] `RunPage.qml:281-292` spoken language → `BoundField`
- [x] `PresetPicker.qml:20-26` content preset → `BoundComboBox` (before it is
      deleted in T-0.3)
- [x] `CommandBar.qml:110-129` source/spoken language → `BoundField` (before it is
      deleted in T-0.4)
- [x] Grep for any remaining `currentIndex: {` containing `appBridge` and fix it.

**Done when:** `grep -n "currentIndex: {" ui/qml` returns no expression reading
`appBridge`.

### T-0.3 — Delete duplicate widgets for one concept (RC-2)

Files: `CommandBar.qml`, `RunPage.qml`, `SettingsPage.qml`, `StatusBar.qml`

- [x] Delete `CommandBar.qml:94-96` (`ModePicker`) + the divider at `:98-103`
- [x] Delete `CommandBar.qml:105-108` (`PresetPicker`)
- [x] Delete `CommandBar.qml:110-129` (unlabeled language `CompactComboBox`)
- [x] Delete `RunPage.qml:776-778` (`PresetPicker`); keep the chip row at `:784-799`
- [x] Delete `RunPage.qml:295-317` (`Translate from` select)
- [x] Collapse the glossary field+button pair into one labelled control:
      `RunPage.qml:722-737` and `SettingsPage.qml:330-344`
- [x] Delete `StatusBar.qml:122-129` (`Log` button); the rail owns Log
- [x] Verify `IconRail.qml` remains the only persistent nav

**Done when:** each concept in the plan's D2 table has exactly one home per screen,
and `ModePicker.qml` / `PresetPicker.qml` are referenced only where the plan says.

### T-0.4 — Invariants become prose, pills become read-only

Files: `SettingsPage.qml`, `RunPage.qml`, `CommandBar.qml`, all pill call sites

- [x] Delete `SettingsPage.qml:259-268` (`Target language: English (locked)` input)
      → prose line *"Output is always English."*
- [x] Add the same prose line to the Run screen; keep the About `KeyValue` (`:1063`)
- [x] Delete `SettingsPage.qml:347-351` (`Foreignization: ✓ Always on`) → prose
- [x] Convert `CommandBar.qml:253-260` (`Light theme` action-label) into a real
      state-showing toggle bound to `ui.theme`
- [x] Audit every `Pill` / `Chip` / `StatusPill` call site for `MouseArea`,
      `onClicked` or an action verb in the text; remove them all
- [x] Delete the `.env` chip from the Run screen (`RunPage.qml:547-551`)

**Done when:** no pill is interactive; no invariant renders as a locked input or
always-on toggle; the word `.env` does not appear anywhere in `RunPage.qml`.

### T-0.5 — Effective value + provenance (no vanishing placeholders)

Files: `backend/bridge.py`, `SettingsPage.qml`

- [x] Add `@Property(str, notify=formChanged)` for `effectiveBaseUrl`,
      `effectiveModel`, `effectiveApiKeyState` and their provenance strings
- [x] Replace `SettingsPage.qml:383, 394, 407` placeholders with effective value +
      secondary provenance text (`gpt-4o-mini · inherited from .env`)
- [x] Replace `SettingsPage.qml:421, 689, 707` (`auto-detected from the models
      folder`) the same way
- [x] Keep `Never persisted to disk` inline on the **API key** row (`:402`)
- [x] Ensure the model field never contradicts the key field

**Done when:** no field in Settings renders as a blank box when a value is in
effect; provenance is visible without hovering.

### T-0.6 — Fix the QML/Python slot contract (RC-4)

Files: `backend/bridge.py`

- [x] Decorate `saveWindowState` (`bridge.py:3481`) with `@Slot(str)`
- [x] Grep QML for every `appBridge.<name>(` call and assert each name is a `@Slot`
      in `backend/bridge.py`; fix any other mismatches found

**Done when:** window geometry persists across a restart.

### T-0.7 — Readiness states get a real fifth value (D3)

Files: `backend/bridge.py`, `ui/qml/components/ReadinessChecklist.qml`

- [x] Change `readinessRows` (`bridge.py:2435`) to emit `ok` / `todo` / `na` /
      `unchecked` instead of the overloaded `n/a`
- [x] Add `actionable: bool` to each row
- [x] `na` = "ASR not used in YouTube mode"; `unchecked` = "not checked until a path
      resolves" (the `_output_readiness_row` case, `bridge.py:2410-2432`)
- [x] Update `ReadinessChecklist.qml:54-99` to render five distinct treatments
- [x] Remove the ad-hoc bolding at `ReadinessChecklist.qml:80`
- [x] Add `StatusMark.qml` and use it for the row glyph

**Done when:** `n/a` and `unchecked` are visually distinct, and the badge
denominator equals the count of `actionable` rows.

### T-0.8 — Phase 0 tests

Files: `tests/test_ui_bindings.py` (new), `tests/test_ux_bridge.py`

- [x] Write `test_ui_bindings.py` using the existing `qml_main` fixture (load
      `Main.qml` **once** — a second engine crashes the process)
- [x] Assert every editor follows a programmatic store change, per concept
- [x] Update `test_ux_bridge.py` to assert readiness states ⊆
      `{ok, todo, na, unchecked}` and that `actionable` is present
- [x] Run the full suite; `tests/test_qml_smoke.py` must stay clean

**Done when:** suite green and the Phase 0 gate holds.

---

## Phase 1 — Global chrome

**Gate:** no truncated or recoloured primary CTA in any mode; no simultaneous
`Saved` + `Save`; top bar shows no duplicate mode/language editors and no
screen-local field.

### T-1.1 — Top bar teardown

Files: `ui/qml/components/CommandBar.qml`

- [x] Reduce the bar to: identity → `StatusStrip` → spacer → theme toggle →
      `Commands` → one primary action
- [x] Delete the `Save` button (`:303-309`)
- [x] Delete the hardcoded `Saved` pill (`:237-241`)
- [x] Move `Search settings…` (`:177-184`) out of the bar into the Settings screen
- [x] Keep the per-page result chips (`:132-164`) and log filter (`:167-174`) only
      where they are genuinely screen-local and not duplicated elsewhere

**Done when:** `CommandBar.qml` contains no `ModePicker`, no `PresetPicker`, no
unlabeled language control, no `Save` button, no Settings search field.

### T-1.2 — `StatusStrip.qml`

Files: `ui/qml/components/StatusStrip.qml` (new), `backend/bridge.py`, `CommandBar.qml`

- [x] Add `@Property(str, notify=formChanged) globalStatusText` and
      `globalStatusTone` to `AppBridge` — derived in Python so it is testable
- [x] Compose e.g. `● Ready · YouTube → Cloud LLM · English out`
- [x] Render the dot with `StatusMark` (`§2.1`)
- [x] Replace the scattered `Ready` / `Strict gate off` / `No report yet` pills with
      this one line

**Done when:** one read-only status line exists in the top bar and its text always
agrees with the store.

### T-1.3 — Bottom bar semantics

Files: `ui/qml/components/StatusBar.qml`

- [x] Style every item as **either** a button **or** a flat hint — never both
- [x] Keep the context-sensitive shortcut legends; make their non-interactivity
      obvious (flat, no border, muted)
- [x] Remove duplicate launchers owned by the rail / palette (the `Log` button)
- [x] Keep `stateWord` + `statusMessage` as the status half

**Done when:** no chip in the bottom bar is ambiguously clickable.

### T-1.4 — Primary action invariants

Files: `ui/qml/components/RunButton.qml`, `RunPage.qml`

- [x] Delete the `needsModelDownload` / `repairingModel` label + colour branches
      (`RunButton.qml:15-23, 30-36`)
- [x] One hue (accent), one label grammar: `▶ Run` / `■ Cancel`
- [x] Blocked → `Run` **disabled** + inline reason (`Run — needs translation model`)
- [x] Failed → `▶ Run` (retry) with the failure reason as a tooltip
- [x] Move model download into the Processing panel as a secondary action
      (`RunPage.qml:556-641`)
- [x] Guarantee no truncation: let the button size to its content, never elide

**Done when:** for every mode × model-state combination, `RunButton.text` ∈
{`Run`, `Cancel`} and the hue is the accent family.

### T-1.5 — Autosave (D5)

Files: `backend/bridge.py`, `ui/qml/components/Toast.qml` (new), `Main.qml`

- [x] Add `@Property(bool, notify=formChanged) dirty` to `AppBridge`
- [x] Add a 400 ms debounce `QTimer` calling the existing `_persist_fields()`
      (`bridge.py:1097`)
- [x] Keep `saveSettings` (`bridge.py:3777`) as a `@Slot` for the palette and the
      `onClosing` flush
- [x] Create `Toast.qml`; fire a transient `Saved ✓` on commit
- [x] Show a dirty indicator (dot on the affected category / `● Unsaved` in the
      status strip) only while a change is pending
- [x] Wire `Main.qml:107-112` `onClosing` to flush before saving window state

**Done when:** `Saved` and `Save` never coexist; a change persists without pressing
anything.

### T-1.6 — Phase 1 tests

Files: `tests/test_ui_chrome.py` (new)

- [x] Assert `CommandBar` has no `ModePicker` / `PresetPicker` / `saveButton`
- [x] Assert primary-action invariants across all mode × model states
- [x] Assert the bottom bar has no duplicate rail/palette launcher

**Done when:** suite green and the Phase 1 gate holds.

---

## Phase 2 — Settings IA

**Gate:** the highlighted category always matches rendered content;
`Clear stored settings` is gated and separated; SIZE column no longer collides;
cache row reads Create/Build; raw paths appear only behind `Copy diagnostics`.

### T-2.1 — True category gating

Files: `ui/qml/pages/SettingsPage.qml`

- [x] Replace `_scrollTo()` (`:38-53`) and the `visible: root._show(...)` filter
      (`:159-1056`) with real gating: only the selected category renders
- [x] Re-file controls per the plan's category table
- [x] Delete the `Environment` category (`:26`, `:988-1008`) and fold its unique
      content into About / Data & privacy
- [x] Keep the rail highlight driven by the same value that drives rendering
- [x] Move `Search settings…` into this screen; it filters **within** the selected
      category only

**Done when:** activating category `X` renders exactly `X`'s owner set — asserted by
test, not by eye.

### T-2.2 — Model inventory table fixes

Files: `backend/bridge.py` (`modelsInventory`, `:4319`), `SettingsPage.qml`

- [x] Remove the `· <path>` fragment from `size` (`f"{size} · {os.path.join(*tail)}"`)
      — it paints over the PURPOSE column
- [x] Give every column a `Layout.minimumWidth` + `Layout.preferredWidth`
      (`SettingsPage.qml:760-764, 786-816`)
- [x] Add a `tm` branch to the row button (`:822-832`) reading **Create** / **Build**
      — not `Download`
- [x] Make the table the single source of the `missing` fact; convert the field
      badge (`:432-437`) into a derived read-only mirror linked to the row
- [x] Keep the STATE column's icon+colour+text encoding — it is the `§2.1` reference

**Done when:** no `size` value contains a path separator; the cache row's verb is
Create/Build; `missing` has one source.

### T-2.3 — Quarantine diagnostics & destruction

Files: `backend/bridge.py`, `SettingsPage.qml`, `ui/qml/components/DangerZone.qml` (new)

- [x] Replace `environmentRows` (`bridge.py:4435-4444`) raw strings with one-line
      summaries
- [x] Push the raw strings behind `copySummaryText` / `Copy diagnostics`
      (`SettingsPage.qml:1078-1083`)
- [x] Un-truncate `Network calls in Offline` (`:1020`) → `Network calls in Offline mode`
- [x] Create `DangerZone.qml`; move `Clear stored settings` (`:1040-1046`) into it
- [x] Add a **typed confirmation** naming what will be erased; replace the OK/Cancel
      `clearDialog` (`:1133-1150`)

**Done when:** no absolute path, registry key, Python/Qt version or `Frozen build`
string renders inline; the destructive action requires typing.

### T-2.4 — Shortcuts become a remap editor

Files: `SettingsPage.qml`, `backend/bridge.py`, `Main.qml`

- [x] Add a `_PERSISTED` entry `("_shortcuts_json", "ui/shortcuts", "{}")`
      (`bridge.py:816-866`)
- [x] Build a record-a-combo surface with conflict detection and reset-to-default
- [x] Drive `Main.qml:62-105` `Shortcut` sequences from the stored map
- [x] Keep the palette and bottom-bar legends reading from the same map

**Done when:** a remapped shortcut takes effect immediately and survives a restart;
conflicts are reported.

### T-2.5 — Provenance & security fields in Settings

Files: `SettingsPage.qml`

- [x] Cloud base URL / model / API key show effective value + provenance inline
- [x] `Never persisted to disk` stays inline on the API key only
- [x] Remove any remaining `.env` jargon from non-Settings screens

**Done when:** the security statement sits on the secret, inline, and does not
contradict the inheritance message.

### T-2.6 — Phase 2 tests

Files: `tests/test_ui_settings_ia.py` (new), `tests/test_ux_bridge.py`

- [x] Assert category ↔ rendered-content equality for all categories
- [x] Assert no `modelsInventory` `size` contains `·` + a path separator
- [x] Assert the cache row verb ≠ `Download`
- [x] Assert `environmentRows` contains no absolute path

**Done when:** suite green and the Phase 2 gate holds.

---

## Phase 3 — Run screen

**Gate:** switching modes moves no header and jumps no layout; the readiness number
equals the visible rows; the fourth matrix cell is disabled-with-reason or works;
Cancel/Retry behave per `§6.6`.

### T-3.1 — Two-axis source × engine
**Notes.** The fourth cell renders **disabled with a stated reason**.
`engineLocalDisabledReason` had to change meaning to do that: it originally
tested the *current pair*, which made it unreachable, because `pipelineMode` can
only ever hold one of the three supported combinations. It now tests the source
axis — "can the local engine be selected right now".


Files: `ui/qml/pages/RunPage.qml`, `backend/bridge.py`, `ui/qml/components/ModePicker.qml`

- [x] Add `@Slot(str, str) setSourceEngine(mode, backend)` with pair validation
- [x] Build two independent selectors: `Source` (YouTube URL | local media file) and
      `Engine` (cloud LLM | local model)
- [x] Keep `pipelineMode` (`bridge.py:1453`) as the derived 3-value id the run builder
      consumes; do not change `_apply_pipeline_mode` (`:1484`)
- [x] Resolve the 4th cell (YouTube source + local engine): implement it, or render
      it **disabled with a stated reason**
- [x] Retire `ModePicker.qml` (its last call site was removed in T-0.3)

**Done when:** the matrix is honest and no combination is silently impossible.

### T-3.2 — Shared baseline + constant-height SOURCE container
**Notes.** The plan's premise was wrong: a `StackLayout` sizes itself to the
**current** child, not to the maximum of its children (measured 387 px in
YouTube mode vs 343 px for a local file). A StackLayout alone therefore still
lets the panel jump. Two fixes were needed:

1. `reservedHeight` — a high-water mark on the StackLayout that grows to the
   tallest branch ever seen and never shrinks.
2. The YouTube-only `VIDEO DOWNLOAD (OPTIONAL)` header and the engine
   disabled-reason line moved **inside** the body, with no `visible:` guard. As
   siblings of the StackLayout they added 28 px + 12 px of spacing in YouTube
   mode only — the measured 40 px jump.

Measured after the fix: the SOURCE card is a constant 590 px and both column
headers share `y = 0` in every combination.


Files: `ui/qml/pages/RunPage.qml`

- [x] Replace the three independent `ScrollView`s (`:41, 402, 829`) with one
      whole-screen scroll for the row
- [x] Pin the `Source` / `Processing` headers to one shared vertical baseline in all
      modes
- [x] Give the SOURCE panel a fixed `implicitHeight` skeleton so YouTube↔local
      toggling swaps **content**, not **layout**
- [x] Ensure the `2` header never clips in any mode

**Done when:** for all 4 source × engine combinations, the header `y` values are
identical and the SOURCE container height is constant.

### T-3.3 — `Processing` rename + stage strip

Files: `ui/qml/pages/RunPage.qml`, `ui/qml/components/StageStrip.qml` (new)

- [x] Rename `PIPELINE` → `Processing` (`:411`)
- [x] Create `StageStrip.qml`: `Source → Transcribe → Translate → Gate → Write`
- [x] Idle-grey normally; light/animate the active stage during a run
- [x] Drive from the existing `stageChanged` (`bridge.py:806`) and `stageIndex`
      (`:2169`) — no new plumbing
- [x] Honour `Theme.reducedMotion` (no animation when enabled)

**Done when:** the strip reflects the real pipeline and animates per stage.

### T-3.4 — Readiness out of the numbered flow

Files: `ui/qml/pages/RunPage.qml`, `ReadinessChecklist.qml`

- [x] Remove `stepNumber: 3` (`:843`)
- [x] Present readiness as a derived status panel (or fold into the status strip +
      a compact card)
- [x] Badge reads `2 of 3 actionable · 1 n/a`, denominator == visible rows
- [x] Use the five `§2.1` treatments from T-0.7
- [x] No ad-hoc bolding

**Done when:** the validator's number matches what is on screen in every mode.

### T-3.5 — De-duplicate inline pickers & fix labels

Files: `ui/qml/pages/RunPage.qml`

- [x] Content preset = chips only
- [x] Glossary = one control
- [x] Language = one labelled pair, present in **every** mode
- [x] Wrap/tooltip `Rolling scene summary` (`:753`)
- [x] Wrap/tooltip `Strict quality gate (errors fail the run)` (`:745`)
- [x] Replace the floating `Open Settings` button (`:817-822`) with a link into the
      bound Settings category, so it no longer overlaps footer text

**Done when:** no control truncates mid-word and no floating element sits over
readable text.

### T-3.6 — Inspect result + video accordion states

Files: `ui/qml/pages/RunPage.qml`, `ui/qml/components/YouTubeSubtitlePanel.qml`,
`YouTubeVideoPanel.qml`

- [x] After inspect, show the detected English subtitle track inline (format, line
      count, preview snippet)
- [x] Enable `Download English subtitle` only when a track exists
- [x] No English track → a `§2.1` warning row with the reason
- [x] Define the `VIDEO DOWNLOAD (OPTIONAL)` expanded state (`:354-396`) with the
      same constant-height discipline

**Done when:** both Inspect outcomes have a designed, non-jittering state.

### T-3.7 — In-progress / failed / cancelled states

Files: `ui/qml/pages/RunPage.qml`, `RunButton.qml`, `StageStrip.qml`,
`backend/bridge.py`

- [x] **In progress:** primary slot → `■ Cancel`; strip animates the active stage; a
      live readout (stage, %/line counter, elapsed) in the readiness area; Log
      streams; no modal blocking
- [x] **Failed:** strip halts on the failing stage with a `§2.1` error marker + reason;
      inline error banner on Run (not only Log); red row appended to Log; primary
      returns to `▶ Run` with the reason as a tooltip; partial output surfaces in
      Review with `failed` severity
- [x] **Cancelled:** strip resets to idle; neutral `cancelled` note in Log; primary
      returns to `Run`
- [x] Reuse `failureOccurred` (`bridge.py:802`) and `_classify_failure`

**Done when:** all three states are represented without inventing a second
vocabulary mid-run.

### T-3.8 — Phase 3 tests

Files: `tests/test_ui_run_layout.py` (new), `tests/test_ui_stage_strip.py` (new),
`tests/test_ux_bridge.py`

- [x] Assert header `y` identity + constant SOURCE height across all 4 combinations
- [x] Assert `setSourceEngine("youtube","local")` succeeds or reports a reason
- [x] Assert readiness denominator == actionable row count
- [x] Drive `stageChanged` / `failureOccurred` and assert the strip's active/halted
      index

**Done when:** suite green and the Phase 3 gate holds.

---

## Phase 4 — Visual language

**Gate:** every status uses icon+colour+text; no mid-word truncation on a control;
helper text meets AA in dark **and** light.

### T-4.1 — Export the status vocabulary

Files: `ui/qml/components/StatusMark.qml`, `ReadinessChecklist.qml`, `QualityPage.qml`,
`ReviewPage.qml`, `SettingsPage.qml`, `Theme.qml`

- [x] Finalise `StatusMark.qml` with the five `§2.1` facts
- [x] Replace ad-hoc status renderings in all four pages
- [x] Generalise the model-table STATE column treatment (`SettingsPage.qml:810-816`)
- [x] Add `Theme` helpers for the open-ring (`unchecked`) and muted-ring (`na`) glyphs

**Done when:** every status in the app is shape-first and greyscale-safe.

**Notes.** `StatusMark` already existed and was already adopted in `RunPage`,
`SettingsPage` and `ReadinessChecklist`; the outstanding work was the *ring*
vocabulary and a guard. Two additions:

1. `Theme.statusRing(status)` / `Theme.statusRingWidth(status)` now own the
   `unchecked` (open ring, 1.5px `borderStrong`) and `na` (closed ring, 1px
   `border`) treatments. They were inline ternaries in `StatusMark.qml`, which
   meant any second renderer would have had to copy them — and the original
   defect was exactly that a second renderer collapsed the pair into one grey
   dash.
2. `QualityPage`'s issues table and `ReviewPage`'s cue table already carry a
   glyph + word (`Chip { iconName: … }` and `Theme.statusIcon`/`statusLabel`),
   so they were left as-is. `tests/test_ui_hygiene.py` now asserts that each of
   the four pages renders status with a glyph or a word, so a future colour-only
   status fails the build.

### T-4.2 — Truncation & overflow policy (D4)

Files: `ui/qml/components/OverflowRow.qml` (new), `StatTile.qml`, `QualityPage.qml`,
`RunPage.qml`, `SettingsPage.qml`, `tests/test_ui_hygiene.py`

- [x] Create `OverflowRow.qml` — wraps instead of clipping at the card edge
- [x] Move the seven-tile Quality metric row (`QualityPage.qml:108-115`) into
      `OverflowRow` (root cause: `StatTile.qml:56` uppercase + `elide`)
- [x] Fix `Rolling scene summar…`, `Only problems → Show…`,
      `Network calls in Offl…`, `Leakage · empty · m…`,
      `Residue · duplicate · …`, the cue-budget row (`SettingsPage.qml:578-605`)
- [x] Add a tooltip to every body/helper label that still elides
- [x] Extend `test_ui_hygiene.py`: flag `elide: Text.ElideRight` on any control label
      (inside `AppButton`, `Chip`, `Pill`, `StatusMark`, `SegmentedControl`,
      `RunButton`) without a tooltip

**Done when:** the hygiene rule passes and no control truncates mid-word.

**Notes.** Three of the six named truncations were **already fixed** and the
plan was working from a stale screenshot: `Rolling scene summary` and the
cue-budget row both live in a `Flow` (which wraps), and `Only problems` is an
`AppSwitch` whose label is not elided. Verified by reading the tree, not by
assuming.

What was actually broken:

1. The Quality metric row. Seven `StatTile`s in a `RowLayout` — `RowLayout` has
   no wrap, so it shrank every cell until `StatTile.qml`'s uppercase + `elide`
   chopped the labels. Fixed by **`OverflowRow.qml`** (a `Flow` wrapper that
   exposes a `cellWidth` derived from `minCellWidth`) plus **`MetricChip.qml`**,
   which is label-first, wraps to two lines, keeps the label's natural case, and
   reveals a per-metric breakdown on click. `StatTile` is untouched and still
   used by `ProgressPanel` and `RunPage`.
2. `KeyValue.qml` — "Network calls in Offline mode" elided at 128px. The key now
   wraps (`keyWidth` is configurable) and the value, which must elide because it
   is often a path, carries its full text in a `ToolTip`.
3. `AppCard.qml`'s note label elided with no escape hatch. Tooltip added.
4. `SettingsPage`'s nav-rail labels elide by design (narrow rail); they now carry
   a tooltip so the full category name stays reachable.

`MetricChip`'s breakdown is backed by a new
`QualityIssuesModel.breakdown(severity)` — the same `_all_issues` rows the table
renders, so the chip and the table cannot disagree.

### T-4.3 — Contrast AA, both themes

Files: `ui/qml/Theme.qml`, `tests/test_theme_contrast.py` (new)

- [x] Measure WCAG ratios for every `(foreground, background)` token pair in dark
- [x] Lift `Theme.textMuted` (`#6E7891` on `#12161E`) to AA for helper text
- [x] Repeat for light theme; fix any failing pair
- [x] Write `test_theme_contrast.py` asserting AA for the helper/secondary pairs

**Done when:** the contrast test passes in both themes.

**Notes.** The plan named one failing pair; the measured sweep found four
families, and two of them were worse than `textMuted`:

1. `textMuted` failed on **five** surfaces per theme, not one. The binding
   surface is the *lightest* one a token can land on — `surfaceRaised` in dark,
   `background` in light — so the test sweeps all five rather than the pair the
   review happened to screenshot. Dark `#6E7891` → `#828DA6` (4.78:1 on
   `surfaceRaised`); light `#7C8698` → `#5E6779` (4.85:1 on `surfaceRaised`).
2. Light `success` (3.59:1) and `warning` (3.92:1) were below AA **as text**.
   Status is never colour-only, but the colour is still painted on a title or a
   row, so it is held to the same bar. `#12945C` → `#0F7F4C`, `#B26A00` →
   `#A16000`. The matching `mint` / `amber` accent swatches moved with them so
   the palette does not fork.
3. `borderSoft` was effectively invisible (1.13:1 dark, 1.19:1 light) — below
   even the 1.2:1 the test allows. `#1B2130` → `#212938`, `#E7EBF3` → `#E1E6F0`,
   both still below `border` so the hairline hierarchy survives.
4. **`accentInk` was the real find.** It was a fixed `#FFFFFF`, which is
   illegible on the dark-theme pastel accents: white on rose is 2.95:1, on mint
   1.88:1, on amber 2.03:1, on azure 2.51:1. It is now
   `isDark ? "#0A0C11" : "#FFFFFF"` — a near-black ink clears AA on all five
   dark swatches *and* on `error`. Dark `iris` also moved `#7C5CFF` → `#8A6BFF`
   because it sat at 4.50:1 against the new ink, i.e. passing by float noise.

### T-4.4 — No floating element over real content

Files: `RunPage.qml`, `tests/test_ui_hygiene.py`

- [x] Confirm the `Open Settings` overlap is resolved (T-3.5)
- [x] Add a hygiene rule: no overlay/`anchors.fill` item declared after a text block
      without a reserved gutter

**Done when:** no readable text is painted over anywhere.

**Notes.** The `Open Settings` fix landed in T-3.5 and is asserted in
`tests/test_ui_run_layout.py` ("Open Settings beside, not over, the footer").
The new hygiene rule is `test_no_opaque_overlay_declared_after_text`, run over
every page: it walks each `Type { … }` block and fails if an `anchors.fill`
sibling that also sets a `color:` is declared *after* a `Label` in the same
parent. Z-order follows declaration order, so that pattern is a paint-over by
construction. All four pages pass unchanged.

### T-4.5 — Theme / density / motion actually apply

Files: `ui/qml/Theme.qml`, `Main.qml`, `StatusBar.qml`, `StatusPill.qml`,
`StageStrip.qml`, `Toast.qml`

- [x] Verify `Theme.comfortable` changes spacing and nothing truncates differently
- [x] Verify `Theme.reducedMotion` disables the `StageStrip` animation, the `Toast`
      motion and the pulsing dots (`StatusBar.qml:65-70`, `StatusPill.qml`)
- [x] Verify the five accent swatches recolour focus rings, active/selected states,
      the primary action and `§2.1` status accents in **both** themes
- [x] Add assertions to `tests/test_ui_hygiene.py`

**Done when:** each of the three appearance toggles has a visible, verified effect.

**Notes.** `reducedMotion` was already honoured in 11 places (`StageStrip`,
`Toast`, `StatusBar`, `StatusPill`, `StatusStrip`, `Pill`, `ProgressPanel`'s
bar, plus four `Behavior` blocks). Density was **not** complete: `comfortable`
only grew the type scale and the control heights, so a "Comfortable" window
packed bigger glyphs into identical gaps and read as *tighter* than Compact. The
spacing scale (`sm`…`xxl`) is now density-aware; `xs` deliberately stays at 4px
because it is used for hairline gaps inside a single control.

Three new rules in `tests/test_ui_hygiene.py`:
`test_reduced_motion_reaches_every_animated_component` (parametrised over the 13
animating components), `test_every_behavior_collapses_under_reduced_motion`
(no `Behavior on …` may omit the toggle), and
`test_accent_swatches_are_never_hardcoded_outside_theme` (the 10 swatch hexes
may appear only in `Theme.qml`), plus `test_density_reaches_spacing_type_and_control_height`
and `test_primary_action_uses_accent_ink`.

### T-4.6 — Empty states unify on the Log pattern

Files: `QualityPage.qml`, `ReviewPage.qml`

- [x] Quality empty = prompt only; remove the ghosted THRESHOLDS table advertising
      `warn 18 · error 22` against zero data
- [x] Review empty = prompt only; remove the ghosted toolbar/timeline/inspector
- [x] Toolbars appear **only** when data exists

**Done when:** no empty screen renders machinery or fake numbers.

**Notes.** New `EmptyState.qml` — icon, title, body, exactly one next action.
It is the *Log* pattern, not a new one: `LogPage` already rendered
`emptyText: "Nothing logged yet. Press Run on the Run screen."` and the other
screens were the outliers. `QualityPage`'s whole content column and
`ReviewPage`'s whole split view are now `visible: appBridge.resultReady`, so an
empty screen shows the prompt and nothing else.

The reason this matters more than tidiness: `qualityThresholds` is a **static**
table (`warn 18 · error 22`, derived from `subtitle_quality` constants, not from
the run), so on an empty screen it rendered real-looking numbers next to a score
of `—`. A user cannot tell a preset default from a measurement.

---

## Phase 5 — Review & Quality populated states

**Gate:** empty screens show a prompt only; populated screens bind to real data;
gauges replaced by labelled chips; cross-links work.

> All `[inferred]` — validate against Appendix A probes 1, 2, 6 before tuning
> density. Record findings in `docs/UI_VALIDATION.md`.

**Status: complete.** Probes 1, 2, 6 and 5 are executable
(`tests/test_ui_validation.py`, 24 tests) and written up in
`docs/UI_VALIDATION.md`. They changed three things inside this phase and produced
three findings that are recorded but deliberately not fixed — a product decision
(the `lines_*` thresholds), an out-of-phase concern (normalising the store rather
than the view), and a feature that does not exist (threshold presets).

### T-5.1 — Review CUES table

Files: `ui/qml/pages/ReviewPage.qml`, `ui/qml/components/CuePreviewTable.qml`

- [x] Virtualize for large subtitle sets
- [x] Columns `# · START · END · SOURCE · TRANSLATION`
- [x] Severity tints the **row's left border + a leading icon**, never the text
- [x] Multi-line translations wrap in-cell with ellipsis + tooltip

**Notes.** Already virtualized (`ListView` + the filter proxy), so nothing to do
there. Three real changes:

1. Row height 32 → **38 px**, and severity moved **off the row fill** onto a 3 px
   `cueRow.severityBar` plus the existing status glyph. Tinting the whole row made
   a warning and an error the same weight at a glance, and put a coloured wash
   behind the text the user is trying to read.
2. Read mode and edit mode are now **different objects**: `transLabel` (a
   wrapping `Text`) and `transField` (a `TextInput`). A `TextInput` is
   single-line by construction, so the second line of a two-line cue was being
   clipped with no ellipsis and no tooltip — the plan diagnosed this as an
   elision-policy problem, and it was not.
3. `displayText()` expands the ASS line separator for display. The store keeps a
   literal `\N` (`src/postprocess.py::break_lines`) and only the writers
   normalise it, so the row printed `first line\Nsecond line` as one visible line.
   Found by Appendix A probe 1 — see `docs/UI_VALIDATION.md`.

`sourceText` collapses real newlines to spaces (a source line break is not
meaningful in the table); the translation preserves them.

### T-5.2 — Review filter pills with live counts

Files: `ReviewPage.qml`

- [x] `All / OK / Warnings / Failed` carry live counts bound to real rows
- [x] Fix the `Only problems` / truncated `Show…` label
- [x] Search spans source + translation

**Notes.** The `Only problems` `AppSwitch` was **deleted, not relabelled**: it
wrote the same `proxy.filterMode` the filter chips own, so it was a second editor
for one concept — the RC-2 pattern. Its work is done by the `Problems only` chip.

Counts come from `appBridge.cueCounts`, which walks the whole model rather than
the filtered view, so selecting a filter cannot zero the other counts. A new
`filterName` property spells the active filter out beside the row count
("warnings only"), because a count with no unit is ambiguous.

### T-5.3 — Review TIMELINE sync

Files: `ReviewPage.qml`, `ui/qml/components/Timeline.qml`

- [x] Click a bar → scroll + highlight the row
- [x] Drag-select a range → filter
- [x] Replace the empty ghosted box (`ReviewPage.qml:88-118`)

**Notes.** `Timeline.qml` was read-only. It now exposes `barClicked(int cue)` and
`rangeSelected(int first, int last)`, with `_cueAt(fraction)` / `_cueSpan(from,
to)` mapping pixels back to cue numbers, a 4 px drag threshold so a click is not
mistaken for a one-cue drag, and a `timeline.rangeBand` overlay for the selection.
The track is `visible: root.hasBars`, so the empty box is gone rather than
ghosted.

The range reaches the table through `CueFilterProxyModel.setCueRange`, which is a
separate axis from `filterMode` — narrowing to cues 10–14 and filtering to
warnings compose, which is what a user expects.

### T-5.4 — Review CUE INSPECTOR

Files: `ui/qml/components/CueInspector.qml`

- [x] Show source / target / timing / notes / quality-flags for the selected cue
- [x] Add prev/next navigation
- [x] Editing the target marks the row dirty (autosave per T-1.5) and re-runs the
      per-cue quality check live

**Notes.** Prev/next step the table selection (`CuePreviewTable.step(±1)`), so the
inspector and the highlighted row cannot disagree.

The live re-check is the substantive change: `setCueText` now calls
`_refresh_quality_from_cues(announce=False)`, which re-runs `build_report` over
the edited cues and pushes the result through `_sync_cue_tags`. A fixed cue
therefore stops being counted as a problem the moment it is fixed, and the strict
gate verdict follows the cues — editing a leaked tag away turns `FAIL` into
`PASS` without a re-run. `Re-check quality` calls the same function with
`announce=True`, so the explicit action and the implicit one can never diverge.

Quality-flag chips are now `clickable` and deep-link to the cue's row in Quality
(`revealIssueForCue`).

**Deviation from the plan:** edits are *not* autosaved to disk. T-1.5's autosave
covers settings (`_persist_fields`), not cue text — see T-5.13, where the missing
save action was added.

### T-5.5 — Review FIND & REPLACE

Files: `ReviewPage.qml`

- [x] Live match count as you type
- [x] Regex toggle
- [x] `Replace all` disabled until ≥1 match
- [x] State the scope: every cue

**Notes.** New `@Slot(str, bool, result=int) countCueMatches(find, use_regex)`
returns how many replacements `replaceInCues` *would* make. An uncompilable regex
returns 0 instead of raising, because a half-typed pattern is the common case and
the count should read "0 matches", not throw.

The card note now says `every cue · N total`, and `review.replaceAll` is
`enabled: appBridge.resultReady && matchLabel.matches > 0`. The plan's point was
that an action which silently does nothing is worse than one that is visibly
unavailable.

### T-5.6 — Review ↔ Quality cross-link

Files: `ReviewPage.qml`, `QualityPage.qml`

- [x] A cue's quality flags deep-link to its row in Quality
- [x] A Quality issue row click jumps to that cue in Review

**Notes.** Both directions, and both had the same bug: a jump that lands on a row
the current filter excludes. `QualityIssuesModel.focus_cue()` therefore sets
`filterMode = "all"` **before** emitting `focusCueChanged`, and `revealCue`
clears the cue range for the same reason. Without that, "reveal this cue" silently
did nothing whenever a filter was active.

The Quality row's 100 px `Fix in Review` button was replaced by a `TapHandler` on
the row itself, with `isFlashing` highlighting the cue that was jumped to. The
button took a third of the row's width to do what clicking the row should do.

### T-5.7 — Quality ISSUES table

Files: `QualityPage.qml`

- [x] `§2.1` status language: row tint + icon + `CUE · TYPE · SEVERITY · MESSAGE`
- [x] Sortable by severity
- [x] Filter by Errors/Warnings with live counts
- [x] `Re-check` re-runs the gate against the loaded result

**Notes.** Severity is carried by a 3 px bar and the status glyph, not by a row
fill, matching T-5.1. The SEVERITY header is a button (`quality.severitySort`)
toggling `QualityIssuesModel.set_severity_sort`, which re-sorts the retained
`_all_issues` so switching back and forth never loses a row.

The filter chips' counts come from a new `counts` property derived from
`_all_issues`, **not** from the visible `_issues`. That is the whole point: the
first version counted the filtered list, so selecting "Errors" made the Warnings
chip read 0. Appendix A probe 2 pins this.

`Re-check quality` re-runs `build_report` against the loaded cues rather than
re-reading the stored report, so it reflects any edits made in Review.

### T-5.8 — Quality GATE card

Files: `QualityPage.qml`

- [x] Header switch = bound editor of `strictQuality`
- [x] Body pill = read-only mirror (no within-card ON/OFF contradiction)
- [x] `Re-run with the gate off` styled as an action

**Notes.** Structurally correct before this phase, as the plan suspected — it was
waiting on RC-1. Verified after the binding work rather than assumed: the header
switch is the only editor and the body pill is read-only, so the two cannot
disagree.

What *was* wrong was the verdict itself. It was computed once at run end, so
editing a cue could not change it. It is now re-derived in
`_refresh_quality_from_cues` as `"fail" if report.error_count else "pass"`, and
the Quality page's blocking line reads
`appBridge.qualityErrors + " error(s) block the run"` from the live count.

### T-5.9 — Quality THRESHOLDS

Files: `QualityPage.qml`, `backend/bridge.py`

- [x] Show the active preset name
- [x] Editing any value marks the preset `custom`
- [x] Un-truncate `Leakage · empty · m…` / `Residue · duplicate · …` with full
      labels + tooltips
- [x] Values derive from the preset, not free-floating

**Notes.** The plan's premise is wrong and the card was corrected to say what is
true. `AppBridge.qualityThresholds` reads module constants out of
`src/subtitle_quality.py` (`CPS_WARNING`, `CPS_ERROR`, …). There is **no preset
system**: nothing to name, no editor, nothing to mark `custom`. The card's note
now reads `"built-in defaults"`, and a `Content preset` row was added so the
value's provenance is stated instead of implied.

The truncation bullet was a layout problem, not a copy problem: the labels
`Leakage · empty · marker` and `Residue · duplicate · overlap` were always full
words, and `KeyValue` was eliding them at a fixed 128 px key width. Fixed in T-4.2
(the key now wraps); no copy changed.

**Not implemented, deliberately:** a preset editor. Inventing one to satisfy a
bullet would have shipped a settings surface for a concept the backend does not
have.

### T-5.10 — Quality DISTRIBUTIONS

Files: `QualityPage.qml`, `ui/qml/components/Histogram.qml`

- [x] Real histograms with **axis labels** for CPS and cue duration
- [x] Consider a log axis if durations skew heavily (decide from Appendix A probe 2)
- [x] Legends wire to the actual preset thresholds and `§2.1` colours

**Notes.** **No log axis — decided from data, not taste.** Probe 2's fixture is
deliberately skewed (45 cues at 0.6 s, 5 at 9.0 s) and the tail is already
visible on a linear axis: two occupied buckets, the overflow bucket at 11 % of the
peak. A log axis would compress the 45-cue mass into one bar to make a 5-cue tail
legible — the wrong trade at this ratio. Recorded in `docs/UI_VALIDATION.md`.

Bar tones are computed in `_distributions`' `_bars(counts, width, warn_over,
error_over)` from the real `CPS_WARNING` / `CPS_ERROR` constants the legend names,
so the legend cannot caption a chart that says something else.

One defect the probe surfaced: the final bucket of each histogram is a clamped
overflow bucket and was labelled with its centre, so a 9.0 s cue sat under an axis
tick reading `6.8`. The final tick is now open-ended (`6.8+`, `38+`), and the
summary line carries the real maximum — one bucket cannot distinguish 7.2 s from
30 s.

### T-5.11 — Replace the micro-gauges with labelled chips

Files: `ui/qml/components/MetricChip.qml` (new), `QualityPage.qml`, `StatTile.qml`

- [x] Create `MetricChip.qml` with a hover/click breakdown
- [x] Move the seven metrics into `MetricChip` inside `OverflowRow`
- [x] Keep the full labels from `bridge.py:3966 qualityTiles` — the defect was
      `StatTile.qml:56` uppercase + elide, not the words
- [x] Never ship an abbreviation a user cannot read

**Notes.** The plan's diagnosis holds: `qualityTiles` already emitted full words
(`Total cues`, `Max line chars`, `Strict gate`), and the defect was `StatTile`'s
uppercase + `elide` inside a non-wrapping `RowLayout`. `StatTile` itself is
untouched — it is still correct for `ProgressPanel` and `RunPage`, where the tile
has a fixed label and a known width.

`MetricChip` is label-first (the label is the information, the value is the
answer), wraps to two lines at natural case, and reveals a per-metric breakdown on
click via `QualityIssuesModel.breakdown(severity)`. The row is an `OverflowRow`
with `minCellWidth: 148`, which wraps instead of shrinking every cell.

**Correction found by probe 2:** the Errors and Warnings tiles read cue-level
counts while the table and filter chips below them counted issue rows, so one cue
with two errors made the tile and the chip disagree — the same defect class as the
original review. The tiles now count rows; `qualityErrors` keeps its cue-level
meaning for the icon-rail badge and the Review page. A tripwire test pins both
units.

### T-5.12 — Quality RUN CONTEXT + EXPORT

Files: `QualityPage.qml`, `backend/bridge.py`

- [x] `runContext` fills from the real run (source, engine, model, duration,
      cue/error/warning counts) — currently `No run loaded`
- [x] Un-ghost `quality_report.json` and `Issue list as CSV` when a run exists
- [x] Add a CSV `@Slot`

**Notes.** `runContext` now returns `Mode · Model · Preset · Context · Batch ·
Translation memory · Windows · Retries · Wall clock` from `_run_metrics` plus the
resolved mode label. `No run loaded` survives only as the honest empty state, and
the whole content column is gated on `resultReady` anyway.

New `@Slot() exportIssueCsv()` writes `cue, type, severity, message` from
`quality_issues_model` — the same rows the table shows, so the CSV and the screen
cannot disagree. Both export buttons are `enabled: appBridge.resultReady`, which
is *disabled*, not ghosted: the plan's distinction, and the right one, because a
greyed button states "not yet" while a ghosted one states "not here".

### T-5.13 — Top-bar result actions bound to the store

Files: `CommandBar.qml`, `QualityPage.qml`, `ReviewPage.qml`

- [x] `Export report` / `Re-check quality` / `Save changes` **disabled** (not
      ghosted-visible) until a run loads
- [x] Enabled state bound to the store

**Notes.** `chrome.primary.recheck` and `chrome.primary.exportReport` are both
`enabled: appBridge.resultReady`; a test asserts the binding so it cannot drift
into a local flag.

**The plan assumed a `Save changes` action existed. It did not.**
`AppBridge.saveEditedSubtitles` / `saveEditedSubtitlesToDefault` had been written
and never called from QML, so a cue edited in Review could only be persisted by
pressing Run again — the edit existed solely in memory. A `Save changes` button was
added to the Review **Cues card header**, beside `Revert all`, because the plan's
"top-bar" premise does not match this chrome: page 1's primary is `Re-check
quality`, and a persistent top-bar save is explicitly forbidden by T-1.6
(autosave). Its binding is `cueEditedCount > 0`, not `resultReady` — a loaded run
with no edits has nothing to save.

### T-5.14 — Validation probes

Files: `docs/UI_VALIDATION.md` (new), `tests/test_ui_validation.py` (new)

- [x] Probe 1: Review with ≥50 cues, ≥1 `failed` row, ≥1 multi-line translation
- [x] Probe 2: Quality with mixed severities + skewed duration distribution
- [x] Probe 6: YouTube Inspect with (a) an English track and (b) none
- [x] Record findings; if a probe contradicts the spec, change **only** the listed
      bullet — Phases 0–4 are data-independent

**Notes.** The probes are **executable**, not narrative: `tests/test_ui_validation.py`
builds synthetic results with deliberately awkward shapes and asserts the data
layer against them, so every figure in `docs/UI_VALIDATION.md` can be re-derived
rather than trusted. 24 tests.

Three findings changed code (all inside Phase 5, per the plan's rule):

1. The Quality Errors/Warnings tiles counted cues while the table and chips under
   them counted issue rows (probe 2).
2. The final histogram tick was labelled with its bucket centre, so a 9.0 s cue sat
   under a tick reading `6.8` (probe 2).
3. The Review read view printed the ASS line separator literally — the store keeps
   `\N` and nothing in QML expanded it (probe 1).

Three findings were **recorded and deliberately not fixed**, because fixing them
is a product decision or reaches outside Phase 5: the inert `lines_*` checks and
their coupling to `LINES_WARNING = 2`; the cue inspector's raw `\N` in an editable
field; and the absent threshold preset system. All three are written up in
`docs/UI_VALIDATION.md` with evidence.

Also recorded: probe 6's assertions are **source-level** — there is no offline
YouTube fixture in the suite, so it proves the branches exist and are gated on the
single store, not that the panel renders against a live inspect. That half needs a
manual network-connected pass.

The probe fixture initially used `[MUSIC]` as a "leaked tag" and 1.8 s cues; both
were wrong. `[MUSIC]` is not something the quality pass flags (the real vocabulary
is `<|…|>`, `<ANGRY>` and `[CHENGYU:…]`), and at 1.8 s every cue also tripped the
CPS error threshold, drowning out the shapes the probe existed for.

---

## Phase 6 — Palette, Log history, appearance verification

**Gate:** palette navigates / acts / toggles / jumps correctly; RUN HISTORY loads
results; all three appearance toggles visibly apply.

### T-6.1 — Commands palette namespaces
**Notes.** The four namespaces landed with 42 entries: 12 Navigate (the five screens
plus a deep link into every Settings category), 20 Actions, 4 Toggles, 6
Jump-to-setting. `tests/test_ui_palette.py` is the guard, and it is deliberately
derived from the two QML files rather than from a copy of the list: every entry's
`action` must appear in `_run`'s switch, every `icon` must exist in `Icon.qml`'s
glyph table, every `jump` target must be an `objectName` that Settings actually
declares, and every Settings category must have a Navigate deep link. A palette
entry that looks real and does nothing is worse than a missing one, and it is
invisible to a QML smoke test because the file still loads.

The Toggles half reads a `toggleStates` object bound to the four stores
(`themeName`, `strictQuality`, `contextSummary`, `reducedMotion`) and the test
asserts that invoking each toggle writes the same store it displays — showing state
is not enough.

Files: `ui/qml/components/CommandPalette.qml`

- [x] **Navigate**: Run, Review, Quality, Log, Settings (+ deep links to a Settings
      category)
- [x] **Actions**: Run, Cancel run, Export report, Re-check quality, Open file,
      Choose glossary, Purge cache, Download model
- [x] **Toggles**: theme, strict gate, rolling summary, reduce motion — each shows
      its **live bound state**; invoking flips the store
- [x] **Jump-to-setting**: typing `api key` / `batch` / `model path` lands on the
      exact field and focuses it
- [x] Keep the existing fuzzy match over all four namespaces

**Done when:** every command resolves to a real bridge slot or a real navigation.

### T-6.2 — Log RUN HISTORY wiring
**Notes.** Two of the three bullets were already true; the third was not, and the
reason is worth recording.

`runHistory` / `selectedRunIndex` / `selectedRunRows` existed on the bridge (at
`bridge.py:4926+`, not the stale `4187-4208` the plan cites), and each row already
carried timestamp, source, engine and outcome. What did **not** work was "click →
loads that result into Review/Quality": clicking only assigned `selectedRunIndex`,
and Review/Quality read the CLI's single `cache/last_result.json`, which every run
overwrites. **Only the newest run could ever be opened**, so every older row was a
row that highlighted and did nothing.

Fix: `_record_run` now copies each successful run's result JSON to
`cache/run_results/<stamp>.json` and stores the *basename* in the entry
(`resultJson`); `selectRun(index)` loads it. The basename, not an absolute path —
an absolute path stored in a persisted entry rots the moment the bundle moves,
which is the failure that already orphaned the downloaded models once. Archives are
pruned with the 20-entry history cap and on `clearRunHistory`.

Three smaller corrections came out of the same work:

1. `YT` / `LC` / `OFF` was a legend the user had to be taught, so the row now spells
   out `sourceLabel` ("YouTube URL" / "Local media file") and `engineLabel`
   ("Cloud LLM" / "Local ASR + Cloud LLM" / "Local model").
2. A failed run has no result, so its row says why instead of silently refusing to
   load (`selectedRunProblem`, rendered beside a `StatusMark`).
3. The `Selected run` card's re-run button called `rerunLastRun()`, which restores
   the *newest* run's snapshot — offering it beside an older entry would re-run the
   wrong thing. It is now gated on `selectedRunIndex === 0` and relabelled.

The live `last_result.json` is still consulted, but only as a fallback for an entry
recorded before archiving existed, and only when that entry succeeded — after a
failed run the live file still holds the *previous* run's result.

Files: `ui/qml/pages/LogPage.qml`, `backend/bridge.py`

- [x] Wire to `runHistory` / `runHistoryCount` / `runHistoryRows`
      (`bridge.py:4187-4208`) — already implemented on the bridge
- [x] Each entry: timestamp, source, engine, outcome with `§2.1` status
- [x] Click → loads that result into Review/Quality

**Done when:** the history is readable, not just listable.

### T-6.3 — Log `empty` filter chip
**Notes.** **Removed, not relabelled** — the plan's second option. It sat first in
the console's `headerExtra`, ahead of the level filters, which is why the review
read it as one; it filtered nothing, and it duplicated both the console's own empty
prompt (`"Nothing logged yet. Press Run on the Run screen."`) and the `0 of 0 lines`
counter beneath it. `blank lines` would have been a filter nobody wants, so the
chip is gone and the level filters (`All` / `Info` / `Warn` / `Error`, with live
counts) are untouched.

Files: `ui/qml/pages/LogPage.qml`

- [x] Label it (`blank lines`) via tooltip, or remove it

### T-6.4 — Appearance verification pass
**Notes.** The pass found one real defect, in the light theme, and it was not the
pair the plan named.

`test_status_colours_clear_aa_as_text` swept only `background` / `surface` /
`surfaceAlt`. But `Chip` paints a toned chip's text on `surfaceRaised`, which in
light theme is the **lightest** surface in the ramp — so every light status colour
sat at 4.22–4.30:1 on a toned chip, just under AA, with the test green. The four
light status colours are darkened ~4 % (`success` `#0F7F4C`→`#0E7948`, `warning`
`#A16000`→`#985B00`, `error` `#D0303F`→`#C72E3C`, `info` `#1F6FD0`→`#1D69C5`), the
`azure` / `mint` / `amber` / `rose` accent swatches moved with them so the palette
does not fork, and the test now sweeps all five surfaces. Measured after the fix:
worst status-on-`surfaceRaised` is 4.61:1 light / 5.38:1 dark; worst `textMuted` is
4.85:1 light / 4.78:1 dark.

Everything else the pass asked for was already wired and is covered where it can be
exhaustive rather than by eye: colour maths in `tests/test_theme_contrast.py`
(ratios parsed out of `Theme.qml`, so editing a hex past the threshold fails the
build), and density / motion in `tests/test_ui_hygiene.py` — including
`test_density_reaches_spacing_type_and_control_height` (the first version grew only
the type scale, so "Comfortable" packed bigger glyphs into identical gaps and read
*tighter* than Compact) and the two reduced-motion rules over 13 animating
components.

**Limitation:** these are computed ratios and source-level wiring checks. No
screenshot is compared against a reference, so a colour that passes AA but is
applied to the wrong element would not be caught.

Files: `ui/qml/Theme.qml`, `tests/test_theme_contrast.py`, `docs/UI_VALIDATION.md`

- [x] Render and AA-check the light theme (Appendix A probe 5)
- [x] Verify accent application across focus rings, active states, primary action and
      `§2.1` accents in both themes
- [x] Verify `Compact` / `Comfortable` density changes spacing
- [x] Verify `Reduce motion` disables every animation/transition
- [x] Record the results in `docs/UI_VALIDATION.md`

### T-6.5 — Docs alignment
**Notes.** §4.24 was stale in almost every particular — 34 components where there
are 43, `ModePicker` / `PresetPicker` still listed as live, eight Settings sections
including `Environment`, a `Pipeline` column, seven `StatTile`s — so it was rewritten
rather than patched. The test count is re-derived, not carried forward: **1096
collected, 1093 pass, 3 fail by design** (`TestBuildIsCurrent`, the stale bundle).

The Editor map is §4.25. It is the review's `§1 Editor map` made real, and it is the
written half of `tests/test_ui_bindings.py` — add a row there and a case here
together.

Files: `AGENT_DOCUMENTATION.md`, `README.md`, `IMPLEMENTATION_PLAN.md`

- [x] Append the `§1 Editor map` (concept → store attribute → editors → mirrors →
      deleted duplicates) to `AGENT_DOCUMENTATION.md`
- [x] Update the QML file inventory (new components) and the test count in both root
      docs
- [x] Re-verify the test count against the tree rather than trusting the previous
      number
- [x] Update the "Last updated" line in both

**Note on `README.md`:** it had no "Last updated" line at all (contrary to the
plan's premise), so one was added rather than edited.

---

## Out of scope — flag to engineering, do not implement

All three are recorded in `AGENT_DOCUMENTATION.md` §18.3b. None is a UI task, and none was
implemented. `[!]` here means "deliberately not done", not "blocked on someone".

- [!] **`build_exe.bat` does not bundle `assets/`** while
      `main.py::_load_bundled_fonts()` reads `<resource>/assets/fonts`, so the
      packaged app falls back to system fonts. One-line `--add-data "assets;assets"`
      fix. Build concern. (Also §9.)
- [!] **XAMPP `htdocs` deployment smell** — `dist/TranslationAgent` running from a
      web docroot is unusual for a Qt app and a likely source of the path-handling
      fragility the UI papers over. The UI's job here was only to stop *displaying*
      it raw (T-2.3), which it does.
- [!] **API-key non-persistence claim vs `QSettings`.** **Verified 2026-09-25:**
      `_PERSISTED` does not contain the key, and `self._api_key` is initialised to
      `""` and only ever set through `_set_field`, so it is session-only and the UI
      statement is accurate as the code stands. It was a *contract*, not an
      invariant, so it is now enforced — `tests/test_ux_bridge.py::test_the_api_key_is_never_persisted`
      fails if the key is ever added to `_PERSISTED`.

---

## Definition of done

Adopted verbatim from the review's `§12`. Each line is verified by a test in
`tests/` or an explicit manual probe in `docs/UI_VALIDATION.md`.

**Verification status (2026-09-25).** The full suite is **1096 collected / 1093 pass / 3
fail by design**. The three failures are
`tests/test_packaged_exe_smoke.py::TestBuildIsCurrent` — `dist/TranslationAgent/` predates
the redesign, which is the intended signal, not a regression
(`AGENT_DOCUMENTATION.md` §18.2). Nothing else fails. Two lines below carry a stated
limitation instead of a bare tick; they are marked inline.

- [x] Flipping **any** bound editor (gate / theme / mode / language / batch / memory /
      glossary / preset) updates **all** its mirrors and editors in the same frame,
      no reload. (`§1`) — `tests/test_ui_bindings.py`
- [x] No status **pill** is clickable or carries an action verb; no editor is a pill.
      (`§1.2`) — audited across every non-archive QML file: no `Pill` or `StatusPill`
      contains a `MouseArea` / `TapHandler` / `onClicked`. Two `Chip` blocks *are*
      interactive and both are deliberate — the content-preset chips (an editor, per
      `§6.5`) and the cue inspector's quality-flag chips (a link into Quality, per `§7`).
- [x] Output language and foreignization appear **only as prose**, never as locked
      inputs / always-on toggles. (`§1.3`) — `SettingsPage.qml:381` ("Always English. The
      product has no other output language."), `:479` ("Always on. Proper nouns and
      honorifics keep their source form."), `RunPage.qml:201`, About `KeyValue`.
- [x] Inheriting fields show **effective value + provenance inline**; `Never
      persisted to disk` is on the **API key**, inline; no `.env` jargon on Run.
      (`§1.4`, `§5.7`) — `SettingsPage.qml:533-591`; the only `.env` left on Run is inside
      a code comment. The persistence promise is now enforced by
      `test_the_api_key_is_never_persisted`.
- [x] Top bar = identity + one read-only status strip + theme toggle + Commands + one
      primary action; **no** mode control, **no** unlabeled language dropdowns,
      **no** persistent Save button. (`§3.1`, `§3.4`) — `tests/test_ui_chrome.py`
- [x] Primary action never truncates and never recolours per mode; blocked = disabled
      `Run` + inline reason; running = `Cancel`; failed = `Run` (retry) + reason.
      (`§3.3`, `§6.6`) — `tests/test_ui_chrome.py`
- [x] Bottom bar distinguishes buttons from hints; no duplicate launchers of
      rail/palette items. (`§3.2`) — `tests/test_ui_chrome.py`
- [x] Settings: highlighted category **matches** rendered content; `Search settings…`
      is convenience, not the only nav. (`§5.2`) — `tests/test_ui_settings_ia.py`
- [x] Settings: raw paths/registry/versions only behind **Copy diagnostics**; privacy
      label un-truncated; `Clear stored settings` in a separated,
      typed-confirmation danger zone. (`§5.6`) — `tests/test_ux_bridge.py`,
      `tests/test_ui_settings_ia.py`
- [x] Model table: SIZE = bytes only (no column collision); cache row verb =
      Create/Build; `missing` has one source. (`§5.4`) — `tests/test_ux_bridge.py`
- [x] Shortcuts: editable remap **or** moved to Help — not a read-only list mis-filed
      under Settings. (`§5.5`) — the remap editor; `tests/test_ui_settings_ia.py` covers
      the round trip and the conflict reporting.
- [x] Run: two independent selectors (source × engine); the flattened 3-cell control
      and the `Local Cloud` label are gone; the 4th combo works or is
      disabled-with-reason. (`§6.1`) — `tests/test_ui_run_layout.py`,
      `tests/test_ux_bridge.py`
- [x] Run: column headers share one baseline across all modes; SOURCE panel is
      constant-height. (`§6.2`, `§2.4`) — measured 590 px and `y = 0` in all four
      combinations; `tests/test_ui_run_layout.py`
- [x] Run: middle column renamed `Processing` with a stage strip that animates during
      a run. (`§6.2`) — `tests/test_ui_stage_strip.py`
- [x] Run: readiness is **not** numbered as a step; its score denominator equals
      visible rows; *n/a* (–) and *unchecked* (○) are visually distinct; no ad-hoc
      bolding. (`§6.4`, `§2.1`) — `tests/test_ux_bridge.py`
- [x] Run: content preset = chips only; glossary = one control; language pair present
      in every mode; no floating button over text. (`§6.5`, `§2.4`) —
      `tests/test_ui_run_layout.py`
- [x] Run: Inspect result and the Video-download accordion have defined states.
      (`§6.3`) — **source-level only.** Probe 6 asserts the branches exist and are gated
      on one store; there is no offline YouTube fixture in the suite, so a live inspect
      still needs a network-connected manual pass (`docs/UI_VALIDATION.md`, probe 6).
- [x] App-wide: every status = icon+colour+text (greyscale-safe); no mid-word
      truncation on controls; truncated text has tooltips; tables don't paint over
      neighbours; overflowing groups wrap/scroll; empty selects have
      placeholders/effective values. (`§2.1`, `§2.2`) — `tests/test_ui_hygiene.py`
- [x] Both themes meet WCAG AA on helper/secondary text; accent/density/reduce-motion
      visibly apply. (`§2.3`, `§10`) — `tests/test_theme_contrast.py` (all five surfaces,
      both themes), `tests/test_ui_hygiene.py`; probe 5 records the measured ratios.
- [x] Empty states everywhere follow the Log pattern (prompt only); Quality shows
      **no** ghosted threshold numbers against zero data. (`§2.6`, `§8`) —
      `tests/test_ui_hygiene.py`
- [x] Review: virtualized cues, left-border+icon severity tint (not text), live filter
      counts, synced timeline, inspector prev/next, find-replace live count. (`§7`) —
      `tests/test_ui_validation.py`
- [x] Quality: issues sortable + cross-linked to Review; gate header = editor, body =
      read-only mirror; thresholds show preset name + `custom` marking; distributions
      are labelled histograms; the seven micro-gauges are replaced by labelled chips;
      run context + export bound to real data. (`§8`) — `tests/test_ui_validation.py`.
      One clause is **not** met, and is documented rather than faked: there is no preset
      system, so the card says "built-in defaults" (`§18.3`,
      `docs/UI_VALIDATION.md` finding 3).
- [x] Log: RUN HISTORY wired and loads results; the `empty` chip is labelled or
      removed. (`§9`) — `tests/test_ui_log_history.py`
- [x] Commands palette navigates / acts / toggles / jumps-to-setting, with toggles
      showing live bound state. (`§4.2`) — `tests/test_ui_palette.py`
