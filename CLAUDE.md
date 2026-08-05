# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in the repository.

## Platform

This project runs on **Windows**. All tool calls, commands, and paths must be Windows-compatible:
- Use `python` (not `python3`)
- Use `pip` (not `pip3`)
- Use `copy` (not `cp`) for native Windows Command Prompt; Git Bash `cp` also works in the shell
- Path separators: backslashes `\` for native Windows commands, forward slashes `/` are accepted by Python and most tools
- The default shell is bash (Git Bash), but commands should be written with Windows conventions in mind

## Project Summary

A YouTube subtitle translation tool with two modes:

1. **CLI** (`translate.py`) — fetches original-language subtitles, translates them faithfully into English with an OpenAI-compatible LLM, and writes an SRT file preserving original timestamps.
2. **GUI** (`main.py` / PySide6 + QML) — wraps the same CLI pipeline in a desktop shell with a QObject bridge that streams output live into the UI.

A third path handles **local video/audio** (no YouTube, no subtitles): FunASR VAD + ASR (SenseVoiceSmall GGUF) extracts timed cues, then the same translation pipeline runs on them.

The local llama.cpp path serves Hy-MT2 (or any OpenAI-compatible model) offline via `--local`.

## Architecture / Big Picture

### CLI pipeline (`src/`)

- `src/config.py` — loads `.env` (`OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`) and builds the OpenAI client.
- `src/fetch_subs.py` — parses video id from URL, uses yt-dlp for the declared original language, then youtube-transcript-api to resolve the track (`manually_created` preferred, `generated` as fallback). Returns `list[Cue]`, the English-localized title, and the source language code.
- `src/local_asr.py` — for local media files without subtitles. Shells out to ffmpeg + FunASR binaries (SenseVoiceSmall GGUF CPU runtime). Runs a FunASR VAD pass refined/backed up by ffmpeg silencedetect, splits long speech into short ASR segments, transcribes each with SenseVoiceSmall, then splits long text into short proportionally-timed cues. Returns `tuple[list[Cue], str | None]` (cues + detected source language).
- `src/translate.py` — batches cues (default 40) as numbered items (`1. text`) so the model returns `1. translation`, keeping cue count/order aligned with timestamps. Falls back to per-item translation on misalignment and retries transient API errors with backoff. The **`translate_cues`** entry point is used by both the CLI and the GUI bridge.
  - The **system prompt is a foreignization directive** (preserve author voice, cultural context, honorifics, period register; never sanitize/domesticate/inject modern slang). `build_system_prompt(source_language)` fills the source/target language placeholders. Keep this directive intact when editing translation.
  - The local llama.cpp path (`--local`) sends `extra_body` with Hy-MT2 sampling params (temperature, top_p, top_k, repetition_penalty).
- `src/srt_io.py` — `Cue` dataclass, SRT writer (`HH:MM:SS,mmm` timestamps), filename sanitization.

### GUI bridge (`backend/`)

- `backend/bridge.py` — `AppBridge` (QObject) exposes form state to QML and runs the pipeline on a background thread via `QThreadPool`. Patches stdout/stderr so CLI prints stream into the UI log in real time. Parses the "Wrote N cues to ..." output line to enable the "Open Output Folder" button.
- `backend/controllers/translation.py` — `TranslationWorker` (QRunnable) calls `translate.main()` with patched stdout/stderr and environment variables.
- `backend/models/run_config.py` — `RunConfig` dataclass carrying `argv` and `env` for the worker.

### QML UI (`ui/qml/`)

- `Main.qml` — top-level window; loads `DashboardView` and `SettingsView` via their `qmldir` registries.
- `components/` — reusable QML types: Card, CustomTextField, PrimaryButton, Sidebar, StyledRadioButton.
- `views/` — DashboardView (controls + log) and SettingsView.

### Entry points

- `translate.py` — CLI entry point (top-level, not in `src/`).
- `main.py` — PySide6 GUI entry point; resolves QML import paths for both dev and frozen (`_MEIPASS`) environments.
- `gui.py` — compatibility shim that just imports `main.main()`; `python gui.py` works but `python main.py` is the canonical command.
- `build_exe.bat` — PyInstaller one-file build for the Windows GUI.

## Key invariants

- Original `start`/`end` times are NEVER modified — only the `text` is replaced with the translation. Preserve this in any change.
- Cue count out must equal cue count in; alignment is guaranteed by the numbered-item protocol. Don't silently drop or merge cues.
- Target language is English, fixed by design.
- The returned title from `fetch_subs.py` is YouTube's English title, NOT our translation of the title — it is used for the SRT filename.
- Local ASR is FunASR + SenseVoiceSmall only.
- Whisper.cpp is not used and must not be reintroduced.
- Local cue timing is produced by VAD + silence refinement + proportional cue splitting.

## Dev Commands

```bash
# CLI (requires .env with OPENAI_API_KEY / OPENAI_MODEL)
pip install -r requirements.txt
copy .env.example .env
python translate.py "<youtube_url>" [--model ...] [--out path.srt] [--batch N]

# GUI (PySide6 only)
pip install -r requirements-gui.txt
python main.py            # canonical
python gui.py             # compatibility launcher, forwards to main.py

# Windows standalone build
# build_exe.bat runs PyInstaller --onefile --windowed
```

## Operational Notes

- No test infrastructure exists (no `tests/`, no `pytest.ini`, no `tox.ini`, no packaging config).
- `.env` is git-ignored — never commit API keys.
- yt-dlp and youtube-transcript-api are external CLIs/libraries; fetch failures raise `RuntimeError`/`ValueError` and the CLI exits non-zero without writing a file.
- The local ASR path requires FunASR GGUF binaries (SenseVoiceSmall model + VAD model) and ffmpeg on PATH — no Python GPU runtime needed at runtime.
- The `--local` flag runs a llama.cpp server locally; the model must already be served on the configured host/port (default `127.0.0.1:8080`).
- `src/local_server.py` bundles a **CPU-only `llama-server`** (in `vendor/llama/`) and auto-starts it when `--local --local-model <file.gguf>` is given, so the user never has to launch a llama.cpp server manually. GPU offload is kept at 0 (`-ngl 0`) for full compatibility.
