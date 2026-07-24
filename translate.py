#!/usr/bin/env python3
"""YouTube subtitle translation CLI, with optional local-file transcription.

Usage:
    python translate.py "<youtube_url>" [--model gpt-4o] [--out path.srt] [--batch 40]
    python translate.py --file video.mp4 [--asr-lang ja] [--out path.srt]

For a YouTube URL it fetches the video's original-language subtitles; for --file it
transcribes a local video/audio file with the SenseVoiceSmall GGUF runtime. In both
cases the text is translated faithfully into English with an OpenAI-compatible LLM
and written to an SRT file while preserving the original timing.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from src.config import load_settings, make_client
from src.fetch_subs import fetch_original_subtitles
from src.translate import translate_cues
from src.srt_io import Cue, write_srt, sanitize_filename


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate a YouTube video's subtitles into English and "
        "write an SRT file."
    )
    parser.add_argument("url", nargs="?", help="YouTube video URL")
    parser.add_argument(
        "--file",
        help="Local video/audio file to transcribe (no subtitles needed). "
        "When given, the YouTube URL is ignored and the audio is transcribed "
        "with the SenseVoiceSmall GGUF runtime, then translated to English.",
    )
    parser.add_argument("--model", help="Override the OPENAI_MODEL from env/.env")
    parser.add_argument(
        "--out",
        help="Output SRT path (default: <video_title>.srt in the current directory)",
    )
    parser.add_argument(
        "--batch", type=int, default=40, help="Cues per translation call (default 40)"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use a llama.cpp server already running on this machine "
        "(pointed at via --local-host/--local-port).",
    )
    parser.add_argument(
        "--local-host",
        default="127.0.0.1",
        help="Host of the running llama.cpp server (default 127.0.0.1)",
    )
    parser.add_argument(
        "--local-port",
        type=int,
        default=8080,
        help="Port of the running llama.cpp server (default 8080)",
    )
    parser.add_argument(
        "--local-model-name",
        default="Hy-MT2-1.8B",
        help="Model id sent to the local server (default Hy-MT2-1.8B).",
    )
    # --- local ASR (SenseVoiceSmall GGUF runtime) flags ---
    parser.add_argument(
        "--asr-bin",
        help="Path to the llama-funasr-sensevoice binary (else "
        "FUNASR_SENSEVOICE_BIN env var, else 'llama-funasr-sensevoice' on PATH).",
    )
    parser.add_argument(
        "--asr-vad-bin",
        help="Path to the llama-funasr-vad binary (else FUNASR_VAD_BIN env var, "
        "else 'llama-funasr-vad' on PATH).",
    )
    parser.add_argument(
        "--asr-model",
        help="Path to the SenseVoiceSmall GGUF model (else FUNASR_MODEL env var, "
        "else ./gguf/sensevoice-small-q8.gguf).",
    )
    parser.add_argument(
        "--asr-vad-model",
        help="Path to the fsmn-vad GGUF model (else FUNASR_VAD_MODEL env var, "
        "else ./gguf/fsmn-vad.gguf).",
    )
    parser.add_argument(
        "--asr-lang",
        default="auto",
        help="Force ASR language: auto, zh, en, ja, ko, yue (default auto).",
    )
    parser.add_argument(
        "--asr-no-tags",
        action="store_true",
        help="Disable --keep-tags (per-segment alignment falls back to "
        "per-segment transcription).",
    )
    return parser.parse_args(argv)


def _is_english(source_lang: str | None) -> bool:
    """True if the detected source language is English (skip translation)."""
    if not source_lang:
        return False
    return source_lang.strip().lower() in {"english", "en", "eng"}


def _check_local_ready(base_url: str, timeout: float = 10.0) -> None:
    """Fail with a clear message if the running llama.cpp server isn't reachable."""
    import urllib.request

    url = base_url.rstrip("/") + "/models"
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001 - any failure means "not up yet"
            last_err = exc
        time.sleep(0.5)
    raise RuntimeError(
        f"llama.cpp server not reachable at {base_url} (last error: {last_err}). "
        f"Start it first, e.g. `python -m llama_cpp.server --model <path> "
        f"--n_ctx 4096`."
    )


def _run_pipeline(
    args: argparse.Namespace, settings, fetched: tuple[list, str | None, str | None]
) -> int:
    """Translate fetched cues and write the SRT. Shared by local/remote."""
    cues, title, source_lang = fetched

    if _is_english(source_lang):
        print(
            f"Fetched {len(cues)} cues. Source is English; writing ASR/subs "
            f"text as-is (no translation)."
        )
        translations = [c.text for c in cues]
    else:
        print(f"Fetched {len(cues)} cues. Translating into English...")
        client = make_client(settings)
        translations = translate_cues(
            cues, client, settings.model, batch_size=args.batch, source_language=source_lang
        )

    out_cues = [
        Cue(start=c.start, end=c.end, text=t) for c, t in zip(cues, translations)
    ]

    if args.out:
        out_path = args.out
    else:
        stem = sanitize_filename(title) if title else "subtitles"
        out_path = f"{stem}.srt"

    write_srt(out_cues, out_path)
    print(f"Wrote {len(out_cues)} cues to {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if not args.url and not args.file:
        print("error: provide a YouTube URL or --file <local_path>", file=sys.stderr)
        return 2

    # Fetch cues from either a YouTube URL or a local file (same output shape).
    if args.file:
        try:
            from src.local_asr import transcribe_local_file, resolve_asr_config

            sb, vb, mp, vmp = resolve_asr_config(args)
            fetched = transcribe_local_file(
                args.file,
                sensevoice_bin=sb,
                vad_bin=vb,
                model_path=mp,
                vad_model_path=vmp,
                language=args.asr_lang,
                keep_tags=not args.asr_no_tags,
            )
        except (RuntimeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        try:
            fetched = fetch_original_subtitles(args.url)
        except (RuntimeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if args.local:
        base_url = f"http://{args.local_host}:{args.local_port}/v1"
        try:
            _check_local_ready(base_url)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"Using local llama.cpp server at {base_url}")
        os.environ["OPENAI_BASE_URL"] = base_url
        try:
            settings = load_settings(override_model=args.local_model_name)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return _run_pipeline(args, settings, fetched)

    try:
        settings = load_settings(override_model=args.model)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return _run_pipeline(args, settings, fetched)


if __name__ == "__main__":
    raise SystemExit(main())
