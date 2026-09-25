---
name: translation-agent-debug
description: Debug and verify this project's PySide6/QML desktop app by reproducing user-reported bugs against the app's REAL persisted state, and by running the local (offline) pipeline end to end. Use when a bug report says "X used to work" / "the UI shows Y", when a model/ASR/llama-server run fails, or when you need to prove a GUI fix works. Covers the offscreen QML harness, the real QSettings store, the proxy/port traps that fake app bugs, and the local model inventory.
agent_created: true
---

# Debugging Translation Agent (PySide6/QML + local models)

## 0. Pick the right interpreter

The managed venv has **no PySide6**. Use the system Python:

```bash
/c/Users/Njoro/AppData/Local/Programs/Python/Python312/python.exe
```

Run tests with `-m pytest -q`. `pytest.ini` sets `testpaths = tests` and
`pythonpath = .`, so run from the repo root.

## 1. Read the user's real state before theorising

The app persists everything to `HKCU\Software\Translation Agent\Translation Agent`
via `QSettings`. `reg.exe` is blocked in the sandbox — read it with `winreg`:

```python
import winreg
k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Translation Agent\Translation Agent")
# walk values/subkeys; note pipeline/mode, local/model, asr/model,
# asr/vadModel, run/history (JSON with exit codes + elapsed seconds)
```

`run/history` is the highest-value artefact: it records each run's exit code,
mode, preset and duration. A failure in **~6 s** is a setup error (missing
binary / bad path); **~60–120 s** means ASR actually ran and then failed.

## 2. Reproduce through the real QML, not just the CLI

A bug that only exists in the bridge/QML layer will not show up in a CLI run.
Load `Main.qml` offscreen with a live `AppBridge` and press Run:

```python
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
app = QGuiApplication([])
app.setApplicationName("Translation Agent")      # MUST match main.py
app.setOrganizationName("Translation Agent")     # or QSettings() is empty
bridge = AppBridge()                             # now reads the user's store
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("appBridge", bridge)
engine.load(Main.qml)
bridge.pipelineMode = "offline"; bridge.filePath = ...; bridge.runTranslation()
# spin a QTimer that polls bridge.isRunning, then dump bridge.logText
```

`_verify_offline_flow.py` in the repo root does exactly this for the offline
flow — use it as the template. Do **not** call `bridge._settings.clear()` when
you are trying to reproduce a user report; that deletes the state you need.

Run it as `python -u _verify_offline_flow.py [media]`. With no argument it cuts a
12-second audio probe from `cache/compare_media.mp4` via `imageio_ffmpeg` (there
is no `ffmpeg` on `PATH`) and drives that — a full video takes ~17 min offline,
which is far too slow to iterate on. It prints the readiness report, then
`statusState` / `failureCode` / whether the `.srt` was written, then the whole
log.

**Harness gotcha:** this environment buffers output through pipes and `timeout`.
Redirect to a file and read that instead:

```bash
python -u _verify_offline_flow.py > _vf_out.txt 2>&1   # then Read _vf_out.txt
```

An empty `| head` / exit-124 result means buffering, not a hang — do not go
hunting for a deadlock.

## 3. Two environment traps that look like app bugs

1. **`HTTP_PROXY` / `HTTPS_PROXY` in the sandbox.** The OpenAI SDK (httpx)
   honours them, so `127.0.0.1:8081/v1/chat/completions` is routed through the
   proxy and comes back **HTTP 404**, which `src/translate.py` reports as
   "not an OpenAI-compatible LLM server". It is not an app bug. Clear them:
   `HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy= NO_PROXY=127.0.0.1,localhost`
   `_verify_offline_flow.py` clears them in-process, so use it rather than
   hand-rolling a CLI run.
2. **Port 8080 is XAMPP's Apache** on this machine. `ensure_local_server()`
   correctly detects the foreign server and starts llama-server on 8081
   (`[local] Port 8080 is busy ... starting on 8081 instead.`). Expected.

Also: `src/config.py` calls `load_dotenv()` at import, so a repo `.env` with an
OpenRouter key is loaded even in offline mode. Harmless (the local path
overwrites `OPENAI_BASE_URL`), but it explains stray cloud-looking settings.

## 3b. Failure classification reads the whole log — including your warnings

`_classify_failure(log_text)` in `backend/bridge.py` scans the **entire** captured
log, newest line first, against `_FAILURE_PATTERNS`. Two consequences that have
bitten this project:

- **Never let advisory text name the failure.** `[warn] Ignoring --asr-model
  <path>: file is incomplete … Falling back to the models folder.` contains a
  model filename *and* the word "incomplete", so it matched `ASR_MODEL` and
  reported "The local transcription model could not be used." for runs that
  failed for an unrelated reason — or that succeeded. `_classify_failure` now
  drops every line starting with `[warn]` before scanning; real failures still
  arrive as `[error]`, tracebacks or raw subprocess output. If you add a new
  advisory message, describe what you *did*, not what was wrong.
- **Pattern order matters, and so does anchoring.** `ASR_MODEL` must precede
  `SOURCE_UNAVAILABLE` (`no transcription` vs `no subtitles`), and its
  `*.gguf`-anchored alternatives exist so a bare `--asr-model <path>` argument
  cannot match. `SOURCE_UNAVAILABLE`'s alternative ends in `\b` so
  "no **transcript**ion" no longer reads as "no transcript".

When a run fails, check `failureCode` before believing `statusMessage`: a
misclassified failure sends the user to the wrong remedy. Classifier tests live
in `tests/test_model_integrity.py::TestAsrFailureClassification` and
`::TestAdvisoryLinesDoNotDriveClassification`.

A successful run must have `failureCode == ""` even when `[warn]` lines are
present — that is the cheapest assertion that both features still hold.

## 4. Local model inventory

| File | Purpose | Where the app looks |
|---|---|---|
| `Hy-MT2-1.8B-Q8_0.gguf` | translation | `_gguf_dir()` = `<base>/gguf` |
| `sensevoice-small-q8.gguf` | ASR | same |
| `fsmn-vad.gguf` | VAD (required!) | same |

`_base_dir()` is the repo root for source runs, `dirname(sys.executable)` when
frozen. A packaged run therefore downloads into `dist/TranslationAgent/gguf/`,
**not** the repo's `gguf/` — a classic source of "but the model is right there".
It *looks* in one more folder; see below.

### There is more than one models folder — check all of them

`_gguf_dir()` is only the *download destination*. `_model_search_dirs()` is the
lookup path: `_gguf_dir()` then `_legacy_gguf_dirs()`, which adds
`dirname(_base_dir())/gguf` when frozen. That second folder is not optional
cruft: `build_exe.bat` used to run
`pyinstaller --onefile --name TranslationAgent`, producing a **single file** at
`dist/TranslationAgent.exe` — so `_base_dir()` was `dist/` and models lived in
`dist/gguf/`. Commit `0216a76` (2026-09-11) switched to `--onedir`, which moved
the app folder to `dist/TranslationAgent/` and orphaned every model already
downloaded. (`build_exe.bat` still deletes the fossil `dist\TranslationAgent.exe`.)

On this machine `dist/gguf/` holds a **complete, valid** SenseVoice + VAD pair
while `dist/TranslationAgent/gguf/` holds a truncated 144 MB copy — both dated
to opposite sides of that commit. So when a report says "the models are already
downloaded", believe it and go looking:

```bash
python -c "
from src.gguf_check import inspect_gguf
import glob
for p in glob.glob('dist/**/*.gguf', recursive=True) + glob.glob('gguf/*.gguf'):
    print(inspect_gguf(p), p)"
```

Two related traps:

- The CLI's own fallback (`src/local_asr.py::_resolve_model`) tries
  `Path(default)` and `Path("dist")/default` — both **relative to the working
  directory**. For a frozen build the cwd is not the app folder, so omitting
  `--asr-model` does *not* find the user's models. `_build_run_config` must pass
  resolved absolute paths.
- `modelsInventory` must prefer a *usable* copy across the search dirs, or the
  table reports "Incomplete" for a model the run will happily use, contradicting
  the readiness tick.

Validate a GGUF without loading it:

```bash
python -c "from src.gguf_check import inspect_gguf; print(inspect_gguf('gguf/sensevoice-small-q8.gguf'))"
```

`(False, 'file is incomplete: N byte(s) short ...')` means an interrupted
download. `llama-funasr-sensevoice.exe -m <file> -a <wav>` prints
`gguf_init_from_reader: failed to read tensor data binary blob` for the same
file, which is the fastest way to confirm a corrupt model by hand.

## 5. Cost expectations (CPU-only, no GPU offload)

- Offline run, 4-minute video, 63 cues: **~17 min** wall clock
  (ASR ~90 s, then Hy-MT2 at ~2–4 gen tok/s across 9 context windows).
- A 12-second clip: **~3.5 min** (llama-server model load + warmup dominates —
  the clip length barely matters below ~1 min). Budget the wait, and run it in
  the background rather than shortening it further.
- `build_exe.bat` needs ~1 GB free; `C:` has been at 100% before. Check `df -h /c`
  first, and never let an interrupted build stand — PyInstaller's COLLECT stage
  can be blocked by the 50-file bulk-delete threshold, leaving a mixed bundle
  that still launches.

## 6. Verification checklist before claiming a fix

1. `pytest -q` → only `test_packaged_exe_smoke.py::TestBuildIsCurrent` may fail
   (it fails by design until `build_exe.bat` is re-run).
2. Reproduce the original failure first, then re-run the same harness and show
   the log line that proves the new behaviour.
3. On the successful run, assert `statusState == "done"`, the `.srt` exists, and
   `failureCode == ""` — a non-empty code on a `done` run means the classifier is
   misfiring again.
4. State plainly what is **not** verified (e.g. the packaged exe, if you did not
   rebuild it).

### Reading pytest results in this sandbox

- **The summary can vanish.** pytest's exit-time cleanup of
  `%TEMP%\pytest-of-*/garbage-*` trips the sandbox's bulk-delete guard, which
  kills the process *before* the "N passed" line is printed. Pass a valid
  `--basetemp` (a real Windows path such as
  `C:/Users/Njoro/AppData/Local/Temp/ta_pytest`) to get the summary. A Git-Bash
  path (`/c/Users/...`) breaks `tmp_path` fixtures and fabricates ~121 errors —
  don't.
- **A cluster of `TestPackagedExeStarts` errors** (`ERROR at setup`, one of them
  `SystemExit: 1`) means the module fixture's `DEBUG_LOG.unlink()` of
  `dist/TranslationAgent/debug.log` was refused. Delete that file and re-run; the
  fixture now falls back to truncating it.
- Editing source while a run is in flight produces nonsense results. Wait for the
  background task to finish before touching the tree.

