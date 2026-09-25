# Translation Agent — durable project notes

Curated, cross-session facts. Daily detail lives in `YYYY-MM-DD.md`.

## Environment

- Run Python from the **system** interpreter:
  `C:\Users\Njoro\AppData\Local\Programs\Python\Python312\python.exe`.
  The managed venv has no PySide6.
- Run the full suite with a **fresh, unique, pre-created `--basetemp`**:
  `BT="C:/Users/Njoro/AppData/Local/Temp/ta_$(date +%s)"; mkdir -p "$BT"` then
  `--basetemp="$BT"`. **Reusing** the same basetemp makes pytest try to delete
  the existing tree at session start; the sandbox's safe-delete shim fails with
  `OSError [Errno 53] The network path was not found` and pytest reports a bogus
  `error` on whichever test was setting up. That is what produced every
  "N errors" row in per-file sweeps — with a fresh basetemp they all vanish
  (`test_ux_bridge.py`: 45 passed + 1 error → **46 passed**). A Git-Bash path
  (`/c/Users/...`) breaks `tmp_path` fixtures and fabricates ~121 errors.
  Add `-p no:randomly` for a stable order.
- **pytest's stdout is unreliable here — read the result from a JUnit XML instead.**
  Redirecting the suite to a file (or piping it through `tail`) repeatedly yields a
  *truncated* log: the run finishes, but the captured text stops mid-progress-bar
  (seen at 26 % and 74 %), so the failure summary never appears and the failure
  count looks wrong. Use
  `--junitxml="C:/xampp/htdocs/translation-agent/.suite.xml"` and parse it. The root
  element is sometimes `<testsuite>`, sometimes `<testsuites>` — sum over the
  children rather than reading the root's attributes. Delete the XML afterwards.
- `reg.exe` is blocked — read `HKCU\Software\Translation Agent\Translation Agent`
  via Python's `winreg`. Invoking PowerShell from Bash is blocked.
- `C:` has repeatedly been at 100 %. Check `df -h /c` before any build.

## Model resolution (the rules that keep breaking)

- **Never use `os.path.exists()` as a model validity check.** Use
  `src/gguf_check.inspect_gguf(path)` → `(usable, reason)`. An interrupted
  download leaves a non-empty partial file that passes every existence check and
  then fails minutes into a run.
- Model state is three-valued: `ready` / `missing` / `corrupt`
  (`localModelState`, `asrModelState`, plus `…Problem` for the model a run would
  use and `…SelectionProblem` for the user's own saved path when a fallback
  masks it).
- **Look in every folder a model may live in**, not just the download
  destination: `_model_search_dirs()` = `_gguf_dir()` + `_legacy_gguf_dirs()`.
  The packaged app's models folder moved from `dist/gguf/` to
  `dist/TranslationAgent/gguf/` when `build_exe.bat` switched from `--onefile` to
  `--onedir` (commit `0216a76`, 2026-09-11), orphaning models the user had
  already downloaded. `_build_run_config` must pass **absolute** paths for
  `--asr-model` / `--asr-vad-model`: the CLI's own fallback is relative to the
  working directory, which is not the app folder when frozen.
- Downloads write to `<name>.part`, are validated, then `os.replace`d. A damaged
  destination is repaired, not skipped.

## Failure classification

- `_classify_failure` scans the whole log, newest-first. **`[warn]` lines are
  advisory and are excluded** — every `[warn]` in this codebase reports something
  the app already recovered from. Advisory text must never name the failure
  (that is how `[warn] Ignoring --asr-model … incomplete …` came to be reported
  as "The local transcription model could not be used.").
- Pattern order matters, and patterns are anchored on the `*.gguf` filename so a
  bare `--asr-model <path>` argument cannot match. **The actual table order is
  `AUTH`, `QUOTA`, `NETWORK`, `SOURCE_UNAVAILABLE`, `MISSING_DEPENDENCY`,
  `MODEL_DOWNLOAD`, `MODEL_LOAD`, `ASR_MODEL`, `ASR_FAILED`, `WRITE_FAILED`** —
  i.e. `ASR_MODEL` comes *after* `SOURCE_UNAVAILABLE`. The in-code comment above
  `ASR_MODEL` still claims the opposite ("Must precede SOURCE_UNAVAILABLE") and is
  stale; the behaviour is fine only because `[warn]` lines are excluded and the
  pattern is anchored on `*.gguf`.
- A successful run must have `failureCode == ""`, even when `[warn]` lines are
  present.

## Build

- `build_exe.bat` deletes `dist\TranslationAgent` before building, so it needs
  roughly the size of one bundle free. **Measured: the onedir bundle is ≈856 MB**
  (`_internal` ≈832 MB), so budget ~1 GB. An interrupted COLLECT leaves a
  **mixed** bundle that still launches; `TestBuildIsCurrent` and
  `test_bundle_is_internally_consistent` exist to catch that.
- `TestBuildIsCurrent::test_build_is_newer_than_all_bundled_sources` fails by
  design until the bundle is rebuilt. That is a signal, not a bug.
- `tests/test_packaged_exe_smoke.py` deletes `dist/TranslationAgent/debug.log` at
  fixture setup; if that delete is refused it now degrades to truncating the file
  (the old version let the refusal abort the module fixture and turned one hiccup
  into nine setup errors).
- **`build_exe.bat` does not bundle `assets/`**, but `main.py::_load_bundled_fonts()`
  reads `<resource>/assets/fonts`. The packaged app currently falls back to system
  fonts. Adding `--add-data "assets;assets"` is the fix.

## GUI layer

- The UI is a five-page shell: `Main.qml` = `ApplicationWindow` → `CommandBar`
  (56 px) + `IconRail` (64 px) + `StackLayout` + `StatusBar` (30 px), plus a Ctrl K
  `CommandPalette`. Navigation is `window.currentPage` (int 0–4), **not** a
  `StackView`. Pages live in `ui/qml/pages/`; widgets in `ui/qml/components/`
  (**43**). `ui/qml/archive/` is retired dead code — never edit or document it as
  current.
- **The UI redesign (Phases 0–6) is complete.** `IMPLEMENTATION_PLAN.md` and
  `tasks.md` are the record; every box in `tasks.md` is ticked. Read §4.24/§4.25 of
  `AGENT_DOCUMENTATION.md` before touching the UI: **§4.25 is the Editor map**
  (concept → store attribute → editor → read-only mirror → deleted duplicates), and
  `tests/test_ui_bindings.py` is its executable half. Add a row there and a case
  here together.
- **Anything QML calls on `appBridge` must be a `@Slot`.** This is now enforced by
  inspection rather than memory — `saveWindowState` was the long-standing violation
  and is fixed.
- **`currentIndex: { …appBridge.X… }` on a `ComboBox` is not a durable binding.**
  `ComboBox` assigns `currentIndex` internally on activation, which destroys the
  declarative binding. Fixed by `BoundComboBox` / `BoundField` (they re-apply the
  store value imperatively on notify). Never reintroduce the declarative form. A QML
  singleton store is not an option — a singleton cannot read the `appBridge` context
  property (see `Theme.qml`'s header comment).
- **Run history stores its own result copies.** The CLI writes one fixed
  `cache/last_result.json` and overwrites it every run, so `_record_run` copies each
  successful run's result to `cache/run_results/<stamp>.json` and stores the
  **basename** in the entry (`resultJson`) — a basename, not an absolute path, so
  moving the bundle does not orphan the archive. `selectRun(index)` loads it;
  archives are pruned with the 20-entry cap and on `clearRunHistory`. The live
  `last_result.json` is only a fallback, and only for a *successful* entry — after a
  failed run it still holds the previous run's result.
- `CueFilterProxyModel.filterMode` / `searchText` are plain Python `@property`
  objects that QML writes to — works via PySide6 attribute bridging, but fragile.
- **`StackLayout` sizes itself to the *current* child, not the maximum of its
  children.** Verified by measurement (387 px vs 343 px between branches). Do
  not trust the "implicit height is the max" claim that used to sit in
  `RunPage.qml`; hold a panel steady with an explicit `Layout.preferredHeight`
  high-water mark instead.
- **A widget the user has not touched yet still needs `objectName`.** The QML
  type names PySide reports (`BoundComboBox_QMLTYPE_78`) change between runs, so
  `findChildren` cannot address a widget reliably. Bound editors carry
  `bound.<screen>.<concept>`; structural anchors carry
  `chrome.*` / `run.*` / `settings.*`. `tests/test_ui_bindings.py` fails if a
  `bound.*` editor has no test.
- **Layout assertions need a shown window.** Offscreen Qt never polishes an
  invisible one: every `height` reads 0 and every child of a non-current page
  reports `visible == False`. `tests/conftest.py::qml_shown` shows the window,
  sets `currentPage`, pumps the loop — and stubs `_persist_fields` to a no-op,
  because showing the window lets the 400 ms autosave debounce fire and rewrite
  the real `QSettings`.
- **A wrap-layout wrapper must never publish an implicit size derived from
  children whose size depends on its own size.** `OverflowRow` bound
  `implicitWidth: flow.implicitWidth` while its children's widths came from
  `cellWidth`, which comes from its own `width`. The parent `Layout` then derives
  the assigned width from a preferred width that is a function of the assigned
  width: the cycle never settles and `QGuiApplication.processEvents()` **never
  returns** — a silent freeze with no QML warning, only when the page is first
  laid out (so `test_qml_smoke` passes, because it never shows the window).
- **Diagnosing a silent Qt Quick freeze.** `pytest -o faulthandler_timeout=45`
  proves only that the process is stuck inside `processEvents`. To find the page,
  write a throwaway test that sweeps `root.setProperty("currentPage", 0..4)` and
  appends progress to a **file** — pytest's stdout is lost when the run is killed,
  so `print()` tells you nothing. Then bisect the blocks that page added.
- **Theme tokens are checked, not eyeballed.** `tests/test_theme_contrast.py`
  parses the `isDark ? "…" : "…"` table out of `Theme.qml` and asserts WCAG AA
  (4.5:1) for `text`/`textDim`/`textMuted` on **all five** surfaces, for the status
  colours as text on **all five** (the binding one is `surfaceRaised`, because
  `Chip` paints toned-chip text there — sweeping only three surfaces is what let
  every light status colour sit at 4.2–4.3:1 unnoticed), and for `accentInk` on all
  five accent swatches. Editing a hex past the threshold fails the build.
  `accentInk` flips with the theme (`isDark ? "#0A0C11" : "#FFFFFF"`) because the
  dark accents are bright pastels — a fixed white label was 1.88:1 on mint. The
  light status colours and the azure/mint/amber/rose swatches move **together**;
  they are the same hues by design.
- `Theme.comfortable` drives the spacing scale as well as the type scale and the
  control heights; `xs` (4 px) is deliberately exempt because it is used for
  hairline gaps inside a single control.

## Documentation

- The two root docs are `AGENT_DOCUMENTATION.md` (developer/AI reference) and
  `README.md` (user-facing). Do not create new root-level planning documents.
- Both carry a "Last updated" line and a test count that go stale fast. (`README.md`
  had none until 2026-09-25 — the plan assumed it did; it was added, not edited.)
  Re-verify against the tree rather than trusting the previous numbers: the count
  went 348 → 593 → 682 → **1096** (1093 pass, 3 fail by design).
- `docs/UI_VALIDATION.md` holds the Appendix A probe results, and the probes are
  **executable** (`tests/test_ui_validation.py`), so every figure in it can be
  re-derived rather than trusted. Record new findings there; keep "already
  satisfied" claims in the table so the same work is not done twice.
