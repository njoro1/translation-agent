# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

A CLI tool (not a service) that takes a YouTube URL, fetches the video's
**original-language** subtitles — manual if available, auto-generated captions as
fallback — translates them faithfully into **English** with an OpenAI-compatible LLM,
and writes an SRT file named after the video while preserving the original timing.

This replaced an earlier real-time audio-capture/dubbing concept; none of that
streaming/FastAPI/client code remains.

## Architecture / Big Picture

Single CLI (`translate.py`) → `fetch` → `translate` → write SRT. All logic lives in
the `src/` package:

- `src/config.py` — loads `.env` (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`)
  and builds the OpenAI client. Errors clearly if key/model are missing.
- `src/fetch_subs.py` — parses the video id from the URL, uses **yt-dlp** for
  YouTube's declared original language, then **youtube-transcript-api** to resolve
  the track: `manually_created` preferred, `generated` (auto) as fallback. Returns
  `list[Cue]`, the **English-localized title** (via Innertube `player` API, `hl=en`,
  falling back to the original title), and the source language code. The returned
  title is what the SRT filename is built from — it is intentionally YouTube's
  English title, NOT our translation of the title.
- `src/translate.py` — batches cues (default 40) and sends them as **numbered items**
  (`1. text`) so the model returns `1. translation`, keeping cue count/order aligned
  with timestamps. Falls back to per-item translation if a batch misaligns, and
  retries transient API errors with backoff.
  - The **system prompt is a foreignization directive** (preserve author voice,
    cultural context, honorifics, period register; never sanitize/domesticate/inject
    modern slang). `build_system_prompt(source_language)` fills the source/target
    language placeholders. Keep this directive intact when editing translation.
- `src/srt_io.py` — `Cue` dataclass, SRT writer (`HH:MM:SS,mmm` timestamps), filename
  sanitization.

**Key invariants:**
- The original `start`/`end` times are NEVER modified — only the `text` is replaced
  with the translation. Preserve this in any change.
- Cue count out must equal cue count in; alignment is what the numbered-item protocol
  guarantees. Don't silently drop or merge cues.
- Target language is English, fixed by design (see README).

## Dev Commands

No build/lint/test framework exists. It's plain Python run directly:

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in OPENAI_API_KEY / OPENAI_MODEL
python translate.py "<youtube_url>" [--model ...] [--out path.srt] [--batch N]
```

## Operational Notes

- The "original language" comes from yt-dlp's declared `language` field, which can be
  wrong for some uploads; there is no manual `--from` override yet.
- `.env` is git-ignored — never commit API keys.
- yt-dlp and youtube-transcript-api are external CLIs/libraries; if a fetch fails, the
  code raises a clear `RuntimeError`/`ValueError` and the CLI exits non-zero without
  writing a file.
