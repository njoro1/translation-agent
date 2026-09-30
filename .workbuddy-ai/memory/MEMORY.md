# Translation Agent — durable project notes

Daily detail lives in `YYYY-MM-DD.md`. Root docs: `AGENT_DOCUMENTATION.md`
(dev/AI reference) and `README.md` (user-facing). Do not add root planning docs.

## Environment

- Python: use the **system** interpreter
  `C:\Users\Njoro\AppData\Local\Programs\Python\Python312\python.exe`
  (the managed venv has no PySide6).
- Suite: fresh, unique, pre-created `--basetemp`, plus `-p no:randomly`.
  `BT="C:/Users/Njoro/AppData/Local/Temp/ta_$(date +%s)"; mkdir -p "$BT"`.
  Reusing a basetemp makes the sandbox safe-delete shim raise
  `OSError [Errno 53]` and pytest reports a bogus `error`. A Git-Bash path
  (`/c/Users/...`) breaks `tmp_path` fixtures and fabricates ~121 errors.
- **pytest stdout truncates here** (stops mid-progress-bar). Read the result from
  `--junitxml=.../.suite.xml`; the root is sometimes `<testsuite>`, sometimes
  `<testsuites>` — sum over the children. Delete the XML afterwards.
- `reg.exe` is blocked → read the registry via Python `winreg`. PowerShell-from-Bash
  is blocked.
- Check `df -h /c` before any build; `C:` has repeatedly hit 100 %.

## Model resolution

- **Never use `os.path.exists()` as a model validity check** — use
  `src/gguf_check.inspect_gguf(path) -> (usable, reason)`. An interrupted download
  leaves a non-empty partial that passes existence checks, then fails minutes in.
- State is three-valued: `ready` / `missing` / `corrupt` (`localModelState`,
  `asrModelState`, plus `…Problem` for the model a run would use and
  `…SelectionProblem` for a masked user-saved path).
- Search **every** folder a model may live in: `_model_search_dirs()` =
  `_gguf_dir()` + `_legacy_gguf_dirs()`. The bundle's models moved `dist/gguf/` →
  `dist/TranslationAgent/gguf/` when the build switched `--onefile`→`--onedir`
  (commit `0216a76`). `_build_run_config` must pass **absolute** `--asr-model` /
  `--asr-vad-model` (the CLI fallback is cwd-relative, wrong when frozen).
- Downloads write `<name>.part`, validate, then `os.replace`. A damaged
  destination is repaired, not skipped.

## Failure classification

- `_classify_failure` scans newest-first and **excludes `[warn]` lines** — every
  `[warn]` here reports something already recovered from. Advisory text must never
  name the failure.
- Table order is `AUTH, QUOTA, NETWORK, SOURCE_UNAVAILABLE, MISSING_DEPENDENCY,
  MODEL_DOWNLOAD, MODEL_LOAD, ASR_MODEL, ASR_FAILED, WRITE_FAILED`. Patterns are
  anchored on the `*.gguf` filename. The in-code comment claiming `ASR_MODEL`
  precedes `SOURCE_UNAVAILABLE` is stale.
- A successful run must have `failureCode == ""`, even with `[warn]` lines.

## Build

- `build_exe.bat` deletes `dist\TranslationAgent` before building. Measured onedir
  bundle ≈856 MB (`_internal` ≈832 MB) — budget ~1 GB. An interrupted COLLECT
  leaves a **mixed** bundle that still launches; `TestBuildIsCurrent` and
  `test_bundle_is_internally_consistent` catch it.
- `TestBuildIsCurrent::test_build_is_newer_than_all_bundled_sources` fails by
  design until the bundle is rebuilt — a signal, not a bug.
- `build_exe.bat` does **not** bundle `assets/`, but `main.py::_load_bundled_fonts()`
  reads `<resource>/assets/fonts`. Fix: `--add-data "assets;assets"`.

## GUI layer

- Five-page shell: `Main.qml` = `ApplicationWindow` → `CommandBar` (56 px) +
  `IconRail` (64 px) + `StackLayout` + `StatusBar` (30 px), plus a Ctrl K
  `CommandPalette`. Navigation is `window.currentPage` (int 0–4), **not** a
  `StackView`. Pages in `ui/qml/pages/`; 43 widgets in `ui/qml/components/`.
  `ui/qml/archive/` is retired dead code.
- **Redesign Phases 0–6 are complete** (`IMPLEMENTATION_PLAN.md`, `tasks.md`, all
  boxes ticked). Read §4.24/§4.25 of `AGENT_DOCUMENTATION.md` before touching the
  UI: **§4.25 is the Editor map** (concept → store attribute → editor →
  read-only mirror → deleted duplicates) and `tests/test_ui_bindings.py` is its
  executable half. Add a row there and a case here together.
- **Anything QML calls on `appBridge` must be a `@Slot`** — now enforced by
  inspection (`saveWindowState` was the long-standing violation).
- **`currentIndex: { …appBridge.X… }` on a `ComboBox` is not a durable binding** —
  the control assigns `currentIndex` internally on activation. Use
  `BoundComboBox` / `BoundField` (re-apply the store value imperatively on notify).
  A QML singleton store is not an option: it cannot read the `appBridge` context
  property.
- **Run history stores its own result copies.** The CLI overwrites one fixed
  `cache/last_result.json`, so `_record_run` copies each successful run to
  `cache/run_results/<stamp>.json` and stores the **basename** in `resultJson` (a
  basename, so moving the bundle does not orphan the archive). `selectRun(index)`
  loads it; archives are pruned at the 20-entry cap and on `clearRunHistory`.
  `last_result.json` is a fallback only, and only for a *successful* entry.
- `CueFilterProxyModel.filterMode` / `searchText` are plain Python `@property`
  objects QML writes to — works via attribute bridging, but fragile.
- **`StackLayout` sizes itself to the *current* child, not the maximum** (measured
  387 vs 343 px). Hold a panel steady with an explicit `Layout.preferredHeight`
  high-water mark.
- **A widget the user has not touched yet still needs `objectName`** — PySide's QML
  type names change between runs, so `findChildren` cannot address a widget
  reliably. Bound editors carry `bound.<screen>.<concept>`; structural anchors
  carry `chrome.*` / `run.*` / `settings.*`. `test_ui_bindings.py` fails if a
  `bound.*` editor has no test.
- **Layout assertions need a shown window** (`tests/conftest.py::qml_shown`, which
  also stubs `_persist_fields` so the 400 ms autosave cannot rewrite `QSettings`).
- **A wrap-layout wrapper must never publish an implicit size derived from children
  whose size depends on its own size.** That cycle never settles and
  `QGuiApplication.processEvents()` never returns — a silent freeze with no QML
  warning (`test_qml_smoke` still passes, because it never shows the window).
- Diagnosing a freeze: `-o faulthandler_timeout=45` proves only where it hangs.
  Sweep `currentPage` 0..4 in a throwaway test, appending progress to a **file**
  (stdout is lost when the run is killed), then bisect.
- **Theme tokens are checked, not eyeballed.** `tests/test_theme_contrast.py`
  parses the `isDark ? "…" : "…"` table out of `Theme.qml` and asserts WCAG AA for
  `text`/`textDim`/`textMuted` on all five surfaces, status colours as text on all
  five (`surfaceRaised` is the binding one — `Chip` paints toned text there), and
  `accentInk` on all five swatches. `accentInk` flips with the theme; the light
  status colours and the azure/mint/amber/rose swatches move **together**.
- `Theme.comfortable` drives spacing, type scale and control heights; `xs` (4 px)
  is deliberately exempt.

## Documentation

- Both root docs carry a "Last updated" line and a test count that goes stale
  fast. Re-verify against the tree rather than trusting the previous number:
  348 → 593 → 682 → **1096** (1093 pass, 3 fail by design).
- `docs/UI_VALIDATION.md` holds the Appendix A probe results, and the probes are
  **executable** (`tests/test_ui_validation.py`) — re-derive every figure rather
  than trusting it. Record new findings there.
