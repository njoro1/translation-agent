#!/usr/bin/env python3
"""YouTube subtitle translation CLI, with optional local-file transcription.

Usage:
    python translate.py "<youtube_url>" [--model gpt-4o] [--out path.srt] [--batch 8]
    python translate.py --file video.mp4 [--asr-lang ja] [--out path.srt]

For a YouTube URL it fetches the video's original-language subtitles; for --file it
transcribes a local video/audio file with the SenseVoiceSmall GGUF runtime. In both
cases the text is translated faithfully into English with an OpenAI-compatible LLM
and written to an SRT file while preserving the original timing.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

from src.config import load_settings, make_client
from src.fetch_subs import fetch_original_subtitles
from src.translate import translate_cues, _is_hy_mt2, _detect_cjk_lang
from src.srt_io import Cue, write_srt, sanitize_filename, output_path_for
from src.glossary import load_glossary, format_glossary
from src.subtitle_quality import build_report, print_summary

# Text placed in the SRT for cues that could not be translated (empty output
# after retry/language validation — see src/translate.looks_untranslated). A
# visible marker beats silently shipping the untranslated Chinese source, and it
# lets `read_srt` / the quality report count exactly which cues failed.
UNTRANSLATED_MARKER = "[untranslated]"


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
        "--format",
        choices=["srt", "ass"],
        default="srt",
        help="Output subtitle format. 'ass' produces Aegisub-compatible ASS with styled output.",
    )
    parser.add_argument(
        "--batch", type=int, default=8, help="Cues per translation call (default 8)"
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
        default="Hy-MT2-1.8B-Q8_0",
        help="Model id sent to the local server (default Hy-MT2-1.8B-Q8_0).",
    )
    parser.add_argument(
        "--local-model",
        help="Path to a translation GGUF. When given, the app auto-starts its "
        "bundled CPU llama-server against this file (host/port above); when "
        "omitted, it connects to a server you started yourself, as before.",
    )
    # --- local ASR (FunASR + SenseVoiceSmall) flags ---
    parser.add_argument(
        "--asr-bin",
        default=os.environ.get("FUNASR_SENSEVOICE_BIN"),
        help="Path to llama-funasr-sensevoice binary.",
    )
    parser.add_argument(
        "--asr-vad-bin",
        default=os.environ.get("FUNASR_VAD_BIN"),
        help="Path to llama-funasr-vad binary.",
    )
    parser.add_argument(
        "--asr-model",
        default=os.environ.get("FUNASR_MODEL"),
        help="Path to sensevoice-small-q8.gguf.",
    )
    parser.add_argument(
        "--asr-vad-model",
        default=os.environ.get("FUNASR_VAD_MODEL"),
        help="Path to fsmn-vad.gguf.",
    )
    parser.add_argument(
        "--asr-lang",
        default="auto",
        help="Source language: auto, zh, en, ja, ko, yue.",
    )
    parser.add_argument(
        "--asr-threads",
        type=int,
        default=int(os.environ.get("FUNASR_THREADS", "4")),
        help="CPU threads for FunASR.",
    )
    parser.add_argument(
        "--asr-max-segment-ms",
        type=int,
        default=int(os.environ.get("FUNASR_MAX_SEGMENT_MS", "6000")),
        help="Maximum ASR audio segment length before post-splitting into cues.",
    )
    parser.add_argument(
        "--asr-max-end-silence-ms",
        type=int,
        default=int(os.environ.get("FUNASR_MAX_END_SILENCE_MS", "250")),
        help="Trailing silence allowed before VAD closes a speech segment.",
    )
    parser.add_argument(
        "--asr-speech-noise-threshold",
        type=float,
        default=float(os.environ.get("FUNASR_SPEECH_NOISE_THRES", "0.55")),
        help="FunASR VAD speech/noise threshold.",
    )
    parser.add_argument(
        "--asr-noise-db",
        type=float,
        default=float(os.environ.get("FUNASR_NOISE_DB", "-35")),
        help="ffmpeg silencedetect noise threshold in dB.",
    )
    parser.add_argument(
        "--asr-min-silence-s",
        type=float,
        default=float(os.environ.get("FUNASR_MIN_SILENCE_S", "0.25")),
        help="Minimum silence duration for ffmpeg silence detection.",
    )
    parser.add_argument(
        "--asr-max-cue-duration-ms",
        type=int,
        default=int(os.environ.get("FUNASR_MAX_CUE_DURATION_MS", "3200")),
        help="Preferred maximum subtitle cue duration.",
    )
    parser.add_argument(
        "--asr-max-cue-chars",
        type=int,
        default=int(os.environ.get("FUNASR_MAX_CUE_CHARS", "70")),
        help="Preferred maximum subtitle cue character count (non-CJK).",
    )
    parser.add_argument(
        "--asr-max-cue-chars-cjk",
        type=int,
        default=int(os.environ.get("FUNASR_MAX_CUE_CHARS_CJK", "48")),
        help="Preferred maximum subtitle cue character count for CJK languages.",
    )
    parser.add_argument(
        "--asr-no-tags",
        action="store_true",
        help="Do not request SenseVoice tag output.",
    )
    parser.add_argument(
        "--asr-keep-tags",
        action="store_true",
        help="Keep ASR tags in output (disable default tag stripping).",
    )
    # --- Translation quality / consistency flags ---
    parser.add_argument(
        "--glossary",
        default=os.environ.get("TRANSLATION_GLOSSARY"),
        help="Path to a glossary file for consistent terminology.",
    )
    parser.add_argument(
        "--translation-memory",
        choices=["auto", "on", "off"],
        default=os.environ.get("TRANSLATION_MEMORY_MODE", "auto"),
        help="Translation memory mode: auto (on for local, off for cloud), on, off.",
    )
    parser.add_argument(
        "--translation-memory-db",
        default=os.environ.get(
            "TRANSLATION_MEMORY_DB",
            os.path.join("cache", "translation_memory.sqlite3"),
        ),
        help="Path to the translation memory SQLite database.",
    )
    # --- Local server flags ---
    parser.add_argument(
        "--local-threads",
        type=int,
        default=int(os.environ.get("LLAMA_SERVER_THREADS", "0")),
        help="CPU threads for the local llama-server (0 = let llama.cpp decide).",
    )
    parser.add_argument(
        "--local-mlock",
        action="store_true",
        default=os.environ.get("LLAMA_SERVER_MLOCK", "0") == "1",
        help="Lock the model in RAM (--mlock) for the local server.",
    )
    # --- Cloud rescue flags ---
    parser.add_argument(
        "--cloud-rescue",
        action="store_true",
        default=os.environ.get("CLOUD_RESCUE_ENABLED", "0") == "1",
        help="Enable cloud rescue for cues that failed local translation.",
    )
    parser.add_argument(
        "--cloud-rescue-model",
        default=os.environ.get("CLOUD_RESCUE_MODEL"),
        help="Cloud model to use for rescue translation.",
    )
    parser.add_argument(
        "--cloud-rescue-batch",
        type=int,
        default=int(os.environ.get("CLOUD_RESCUE_BATCH", "10")),
        help="Batch size for cloud rescue translation.",
    )
    # --- Quality flags ---
    parser.add_argument(
        "--strict-quality",
        action="store_true",
        help="Exit with nonzero status if serious subtitle-quality errors are found.",
    )
    parser.add_argument(
        "--quality-report",
        help="Write a JSON quality report to the given path.",
    )
    return parser.parse_args(argv)


def _is_english(source_lang: str | None) -> bool:
    """True if the detected source language is English (skip translation).

    Accepts any ``en``-family code (``en``, ``en-US``, ``en-GB``, ...) since
    YouTube's transcript API reports region-qualified codes like ``en-US``.
    """
    if not source_lang:
        return False
    code = source_lang.strip().lower()
    return code in {"english", "en", "eng"} or code.startswith("en-")


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

    # --- --asr-lang auto-pass-through guard --------------------------------
    # When the user left --asr-lang at 'auto' (not explicitly zh/ja/ko), attempt
    # a lightweight script heuristic on the first 5 cues and forward the
    # detected CJK language to the translation prompt so chengyu flagging and
    # Classical-Chinese detection activate correctly. An explicit user value
    # always wins.
    if getattr(args, "asr_lang", "auto") in (None, "", "auto") and not _is_english(source_lang):
        detected = _detect_cjk_lang(" ".join(c.text or "" for c in cues[:5]))
        if detected:
            print(
                f"[detect] --asr-lang auto; script heuristic detected "
                f"'{detected}' from first cues; forwarding to translation.",
                flush=True,
            )
            source_lang = detected

    # --- Load glossary -----------------------------------------------------
    glossary_str = ""
    if args.glossary:
        entries = load_glossary(args.glossary)
        glossary_str = format_glossary(entries)

    # --- Set up translation memory -----------------------------------------
    tm = None
    tm_mode = getattr(args, "translation_memory", "auto")
    is_local = _is_hy_mt2(settings.model)
    tm_enabled = (
        tm_mode == "on"
        or (tm_mode == "auto" and is_local)
    )
    if tm_enabled:
        try:
            from src.translation_memory import TranslationMemory
            tm = TranslationMemory(getattr(args, "translation_memory_db", None))
        except Exception as exc:  # noqa: BLE001
            print(f"[tm] Translation memory disabled due to error: {exc}", flush=True)
            tm = None

    # --- Set up cloud rescue handler ---------------------------------------
    rescue_handler = None
    if getattr(args, "cloud_rescue", False) and args.cloud_rescue_model:
        # Rescue needs a *cloud* client (separate from the local one).
        # We build it lazily from env/args. If credentials are missing, rescue
        # is silently disabled with a warning.
        try:
            rescue_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            rescue_base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
            if not rescue_api_key and not (rescue_base_url and "localhost" in rescue_base_url):
                print(
                    "[rescue] Cloud rescue enabled but no valid cloud credentials "
                    "are available.",
                    flush=True,
                )
            else:
                from src.rescue import rescue_failed_cues

                rescue_settings = load_settings(override_model=args.cloud_rescue_model)
                rescue_client = make_client(rescue_settings)

                def rescue_handler(cues, failed_indices):
                    return rescue_failed_cues(
                        cues=cues,
                        failed_indices=failed_indices,
                        client=rescue_client,
                        model=args.cloud_rescue_model,
                        source_language=source_lang,
                        batch_size=args.cloud_rescue_batch,
                        glossary=glossary_str or None,
                    )
                print("[rescue] Cloud rescue enabled", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[rescue] Cloud rescue disabled: {exc}", flush=True)
            rescue_handler = None

    # --- Mode summary -------------------------------------------------------
    source_label = "local file" if getattr(args, "file", None) else "YouTube"
    backend_label = "local" if getattr(args, "local", False) else "cloud"
    rescue_label = "enabled" if rescue_handler else "disabled"
    print(
        f"[mode] source={source_label} backend={backend_label} rescue={rescue_label}",
        flush=True,
    )

    # --- Translate ----------------------------------------------------------
    if _is_english(source_lang):
        print(
            f"Fetched {len(cues)} cues. Source is English; writing ASR/subs "
            f"text as-is (no translation)."
        )
        translations = [c.text for c in cues]
    else:
        print(f"Fetched {len(cues)} cues. Translating into English...")
        client = make_client(settings)
        from src.translate import TranslationEndpointError

        try:
            translations = translate_cues(
                cues, client, settings.model,
                batch_size=args.batch, source_language=source_lang,
                glossary=glossary_str or None,
                translation_memory=tm,
                rescue_handler=rescue_handler,
            )
        except TranslationEndpointError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            print(
                "The configured endpoint is not serving an OpenAI-compatible "
                "chat/completions API, so translation was aborted instead of "
                "retrying forever. Check Settings \u2192 Base URL. For the bundled "
                "local llama-server use http://127.0.0.1:8080/v1.",
                file=sys.stderr, flush=True,
            )
            return 1

    out_cues = [
        Cue(
            start=c.start,
            end=c.end,
            text=(t.strip() if t and t.strip() else UNTRANSLATED_MARKER),
        )
        for c, t in zip(cues, translations)
    ]
    # --- Final output sanitizer (fansub markup guard) ------------------------
    # Whatever pipeline produced the translations (local, cloud, English passthrough,
    # or translation-memory replay), the text that is actually written to the SRT/ASS
    # must never carry raw ASR control tokens or leftover fansub prompt markup such
    # as `<|zh|><|ANGRY|><|BGM|><|withitn|>` or `[CHENGYU:...]`. Strip them one final
    # time so a markup leak can never poison the delivered subtitles.
    from src.translate import _strip_sensevoice_tag

    def _sanitize_output(t: str) -> str:
        t = _strip_sensevoice_tag(t)
        # Collapse any whitespace runs/punctuation the tag group left behind.
        return re.sub(r"\s+", " ", t).strip()

    out_cues = [
        Cue(start=c.start, end=c.end, text=_sanitize_output(c.text))
        for c in out_cues
    ]
    failed_indices = [
        i for i, t in enumerate(translations) if not t or not t.strip()
    ]

    # Loud, unambiguous reporting of untranslated cues (addresses the report's
    # biggest defect: 31% of cues shipped as untranslated Chinese with no signal
    # to the user). Every failed cue is counted and listed with its source text.
    if failed_indices:
        print(
            f"[translation] WARNING: {len(failed_indices)}/{len(translations)} "
            f"cues were NOT translated. Their SRT lines are marked "
            f"'{UNTRANSLATED_MARKER}'. See the per-cue list below.",
            flush=True,
        )
        for i in failed_indices[:30]:
            print(f"[translation]   cue {i}: {cues[i].text!r}", flush=True)
        if len(failed_indices) > 30:
            print(
                f"[translation]   ... and {len(failed_indices) - 30} more.",
                flush=True,
            )

    # --- Fansub post-processing ---------------------------------------------
    # Line breaking, translator-note placement, and overlap snapping. Runs on
    # every output cue; returns exactly the same number of cues it receives.
    from src import postprocess
    out_cues = postprocess.apply_all(out_cues)

    # --- Resolve output format & path ---------------------------------------
    fmt = (args.format or "srt").strip().lower()
    if not args.out:
        stem = sanitize_filename(title) if title else "subtitles"
        out_path = output_path_for(stem, f".{fmt}")
    else:
        out_path = args.out
        # If the user gave an explicit --out but no --format, infer from extension.
        if fmt == "srt" and out_path.lower().endswith(".ass"):
            fmt = "ass"
        elif fmt == "ass" and out_path.lower().endswith(".srt"):
            fmt = "srt"

    # --- Write output --------------------------------------------------------
    if fmt == "ass":
        from src.ass_io import write_ass
        # ASS expects \\N line breaks; convert any plain \n to \\N (the
        # postprocessor already emits \\N, but guard against stray \n).
        ass_cues = [
            Cue(start=c.start, end=c.end, text=c.text.replace("\n", "\\N"))
            for c in out_cues
        ]
        write_ass(out_path, ass_cues)
    else:
        # SRT uses a literal newline, so translate the \\N line breaks.
        srt_cues = [
            Cue(start=c.start, end=c.end, text=c.text.replace("\\N", "\n"))
            for c in out_cues
        ]
        write_srt(srt_cues, out_path)

    # --- Completion summary -------------------------------------------------
    # A partially-broken output must never be mistaken for a complete
    # translation: the untranslated count is surfaced unconditionally.
    if rescue_handler:
        rescue_note = (
            f"{len(failed_indices)} cues still failed after rescue"
            if failed_indices
            else "not needed (all cues translated)"
        )
    else:
        rescue_note = "disabled"
    print(
        f"[mode] Completed: {len(out_cues)} cues written, "
        f"{len(failed_indices)} untranslated. Rescue {rescue_note} "
        f"Format: {fmt}.",
        flush=True,
    )

    # --- Quality report ----------------------------------------------------
    if getattr(args, "quality_report", None):
        report = print_summary(out_cues, untranslated_count=len(failed_indices))
        try:
            import json
            with open(args.quality_report, "w", encoding="utf-8") as f:
                f.write(report.to_json())
            print(f"[quality] Report written to {args.quality_report}", flush=True)
        except OSError as exc:
            print(f"[quality] Could not write report: {exc}", flush=True)

    # --- Strict quality check ----------------------------------------------
    if getattr(args, "strict_quality", False):
        report = build_report(out_cues, untranslated_count=len(failed_indices))
        if report.error_count > 0 or report.untranslated_count > 0:
            print(
                f"[quality] {report.error_count} serious errors + "
                f"{report.untranslated_count} untranslated cues found "
                f"(--strict-quality enabled).",
                file=sys.stderr, flush=True,
            )
            return 1

    # Close TM if we opened it.
    if tm is not None:
        tm.close()

    # The `Wrote N cues to ...` line MUST be the final line of CLI output — the
    # GUI TranslationWorker regex keys off this exact line.
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
            from src import local_asr

            cues, source_language = local_asr.transcribe_local_file(
                args.file,
                asr_bin=args.asr_bin,
                asr_vad_bin=args.asr_vad_bin,
                asr_model=args.asr_model,
                asr_vad_model=args.asr_vad_model,
                asr_lang=args.asr_lang,
                threads=args.asr_threads,
                max_segment_ms=args.asr_max_segment_ms,
                max_end_silence_ms=args.asr_max_end_silence_ms,
                speech_noise_thres=args.asr_speech_noise_threshold,
                noise_db=args.asr_noise_db,
                min_silence_s=args.asr_min_silence_s,
                max_cue_duration_ms=args.asr_max_cue_duration_ms,
                max_cue_chars=args.asr_max_cue_chars,
                no_tags=args.asr_no_tags,
                max_cue_chars_cjk=args.asr_max_cue_chars_cjk,
                keep_tags=args.asr_keep_tags,
            )
            stem = os.path.splitext(os.path.basename(args.file))[0]
            fetched = (cues, sanitize_filename(stem), source_language)
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
        local_host = (args.local_host or "127.0.0.1").strip() or "127.0.0.1"
        local_port = int(args.local_port or 8080)
        if args.local_model:
            try:
                from src.local_server import ensure_local_server, warmup_local_server

                _proc, how, local_port = ensure_local_server(
                    args.local_model,
                    local_host,
                    local_port,
                    threads=args.local_threads,
                    mlock=args.local_mlock,
                )
                print(
                    f"[local] llama-server ({how}) on {local_host}:{local_port} "
                    f"serving {args.local_model}\n",
                    flush=True,
                )
            except RuntimeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1

        base_url = f"http://{local_host}:{local_port}/v1"
        try:
            _check_local_ready(base_url)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"Using local llama.cpp server at {base_url}")
        # Warm up the model to reduce first-request latency.
        warmup_local_server(base_url, args.local_model_name)
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
