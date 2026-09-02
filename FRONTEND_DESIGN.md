# FRONTEND_DESIGN.md — GUI Design (Post-Rework)

> This document replaces the pre-rework sidebar/dashboard/settings design.
> The old layout is archived in `ui/qml/archive/` for historical reference.

## 1. Goals

- A compact professional desktop subtitle tool — not a settings dashboard.
- Preset-driven operation; progressive disclosure of advanced settings.
- Results, not logs, at the center of the experience.
- Clear run states: Ready → Validating → Running → Done / Failed.
- Failures actionable: failed cues visible in Review, issues in Quality.

## 2. Layout

```
+----------------------------------------------------------------------------------+
| Header Bar (56 px)                                                               |
| Title | Mode Picker | Preset | Language | … | Run Button | Status Pill           |
+----------------------------------------------------------------------------------+
| Tabs: Run | Review | Quality                                                     |
+----------------------------------------------------------------------------------+
| Run tab                                                                          |
|   Left column (~400 px): Source / Output / Translation panels + Advanced drawer  |
|   Right column: Readiness checklist · Progress · Result summary card             |
+----------------------------------------------------------------------------------+
| Log Drawer (collapsed by default)                                                |
+----------------------------------------------------------------------------------+
```

No permanent sidebar. The window geometry persists via QSettings.

## 3. Header Bar

- **Mode picker** (segmented): `YouTube Cloud` / `Local Cloud` / `Offline`.
  Maps to pipeline modes `youtube_cloud` / `local_cloud` / `offline`.
- **Preset combo**: Auto, Drama, Anime, Music, Documentary, Variety, Lecture
  (`--content-preset`).
- **Language combo** (editable): source-language hint (`--source-lang`).
- **Run button**: `Run` / `Running…` / `Download Model & Run` (offline mode when
  the local translation GGUF is missing — clicking auto-downloads then runs).
- **Status pill**: Ready / Validating / Running / Done / Failed.

## 4. Run Tab

### Left column

- **Source** — YouTube Cloud: URL field. Local modes: file path + Browse +
  drag-and-drop onto the right pane, ASR language combo.
- **Output** — output path (+ Save As dialog), format SRT/ASS,
  Open Output Folder after completion.
- **Translation** — cloud summary or local model status + download buttons;
  ASR model download when missing.
- **Advanced drawer** (collapsed by default): batch size, context mode,
  rolling scene summary toggle, preprocessing profile (local modes), ASR numeric
  tuning (local modes), TM mode, glossary file, strict quality, cloud API fields
  (cloud modes; blank = use `.env`), local GGUF path browser (offline).

### Right column

- **Readiness checklist** — source selected, ASR model available (local modes),
  translation backend ready, output path valid.
- **Progress panel** — stage label + progress bar fed by parsed JSON progress
  (`{"type":"progress","stage":...,"done":N,"total":M}`); indeterminate while
  total is unknown.
- **Result card** (after success) — output path, cue count, untranslated count,
  warning count, strict PASS/FAIL/OFF, and buttons: Open Output Folder,
  View Review, View Quality.

## 5. Review Tab

Virtualized cue table backed by `CueResultModel` +
`CueFilterProxyModel` (`backend/models/results.py`) — never a giant TextArea.

- Columns: `#`, Start, End, Source, Translation, Status badge.
- Filters: All / Failed / Warnings; case-insensitive search over source+translation.
- Row tinting: failed = red, warning = amber, ok = normal.
- Double-click a row to copy it.

Data source: the CLI's `--result-json` file (`cache/last_result.json`),
loaded automatically after a successful run.

## 6. Quality Tab

- Summary badges: Total cues, Untranslated, Errors, Warnings, Avg CPS,
  Max line chars, Strict quality PASS/FAIL/OFF.
- Issue list: Cue / Type / Severity / Message (errors first), derived from the
  quality report embedded in the result JSON.
- Copy report summary button.

## 7. Log Drawer

Collapsible bottom dock, collapsed by default. Monospace, auto-scroll,
Clear + Copy buttons, and a "Show raw JSON" debug toggle. JSON progress lines
are parsed into the progress panel and hidden unless debug is on — they are
never rendered as error text.

## 8. Visual Language

Compact dark theme (tokens in `ui/qml/Theme.qml`, registered as a singleton):

```text
spacing xs/sm/md/lg/xl = 4/8/12/16/24     radius sm/md/lg = 6/8/10
font small/body/label/title/header = 12/13/14/16/18
background #0B0F14  surface #11161D  surfaceAlt #161C24  border #20262E
text #E6EAF0  muted #8A94A3  accent #3D82F6
success #22C55E  warning #F59E0B  error #EF4444
field height 30 px, header 56 px
```

Rules: dense but readable spacing; no giant empty cards; consistent field
heights; visible focus states; tooltips on advanced fields; keyboard-navigable.

## 9. AppBridge Contract (summary)

UI-state driven QObject (`backend/bridge.py`). Key additions in this rework:

- Properties: `pipelineMode`, `contentPreset`, `asrPreprocess`, `contextMode`,
  `contextSummary`, `statusState`, `progressStage/Done/Total`, `resultReady`,
  `outputPathResolved`, `resultStrictState`, `quality*` badges, `cueModel`,
  `cueProxy`, `qualityIssuesModel`, `logVisible`, `debugJsonProgress`,
  `windowX/Y/Width/Height`.
- Slots: `runTranslation()`, `setPipelineMode(mode)`, `openOutputFolder()`,
  `clearLog()`, `copyLog()`, `copySummaryText()`, `saveWindowState("x,y,w,h")`,
  `downloadAsrModels()`, `downloadLocalModel()`.
- Log handling: `_handle_log_line` parses JSON progress, updates progress
  properties, hides raw lines unless debug; final-line parsing still recovers
  the output path if result JSON is missing.
- Persistence (QSettings, non-secret only): pipeline mode, content preset,
  context mode/summary, batch, ASR language/preprocess/numeric fields, local
  model, glossary, TM mode/db, strict quality, output format, window geometry.
  The API key is never persisted.

Every GUI run passes `--json-progress --result-json <cache>/last_result.json`
plus `--content-preset` / `--context-mode` / `--context-summary` /
`--asr-preprocess` as configured. Offline runs pass no cloud credentials.

## 10. CJK Fonts

`main.py` registers every `*.ttf|.otf|.ttc` in `assets/fonts/` via
`QFontDatabase.addApplicationFont` after `QGuiApplication` construction.
A missing directory is not an error. Ship Noto Sans CJK (OFL) there for
consistent CJK rendering; the PyInstaller spec bundles the directory.
