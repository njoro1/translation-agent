#!/usr/bin/env python3
"""YouTube subtitle translation CLI, with optional local-file transcription.

Usage:
    python translate.py "<youtube_url>" [--model gpt-4o] [--out path.srt] [--batch 8]
    python translate.py "<youtube_url>" [--source-lang ja]    # force YouTube source language
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


def _is_failed_text(text: str | None) -> bool:
    """True if a *final* cue text counts as failed/untranslated.

    A cue is failed when it is empty/whitespace or carries the explicit
    ``[untranslated]`` marker. This is evaluated on the FINAL post-processed
    output so empty-after-sanitization cues are not undercounted.
    """
    text = (text or "").strip()
    return not text or text == UNTRANSLATED_MARKER


# Codes returned by the fetcher/ASR that are "specific and known" and therefore
# authoritative — script-ratio detection must NOT overwrite them (e.g. a fetched
# ``zh-TW``/``yue`` must not be downgraded to ``zh``).
_SPECIFIC_SOURCE_CODES = {
    "zh", "zh-tw", "zh-hk", "zh-sg", "zh-hans", "zh-hant",
    "yue", "ja", "ko", "kore", "zh-cn",
}


def _is_known_source_code(code: str | None) -> bool:
    """True if ``code`` is a specific, non-ambiguous source-language hint."""
    if not code:
        return False
    code = str(code).strip().lower()
    if code in {"auto", "und", "none", ""}:
        return False
    # Any code whose base language is a known CJK language counts as specific.
    base = code.split("-")[0].strip()
    return code in _SPECIFIC_SOURCE_CODES or base in ("zh", "ja", "ko", "yue")


def default_output_path(source_file: str | None, title: str, fmt: str) -> str:
    """Where subtitles go when ``--out`` is not given.

    A local input file wins: the subtitle belongs next to the video it came
    from (``C:\\clips\\talk.mp4`` -> ``C:\\clips\\talk.srt``). That is what a
    user expects, and it keeps the pair together when the folder is moved or
    copied. A YouTube run has no local file, so it keeps the old
    title-named output in the current directory.
    """
    ext = "." + (fmt or "srt").strip().lstrip(".")
    if source_file:
        source = os.path.abspath(os.path.expanduser(str(source_file)))
        stem = os.path.splitext(os.path.basename(source))[0]
        return os.path.join(os.path.dirname(source), sanitize_filename(stem) + ext)
    stem = sanitize_filename(title) if title else "subtitles"
    return output_path_for(stem, ext)


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
        help="Output SRT path (default: next to the input file, sharing its name — "
        "<video>.srt beside <video>.mp4. YouTube runs without a local file use "
        "<video_title>.srt in the current directory.)",
    )
    parser.add_argument(
        "--format",
        choices=["srt", "ass"],
        default="srt",
        help="Output subtitle format. 'ass' produces Aegisub-compatible ASS with styled output.",
    )
    parser.add_argument(
        "--ass-font",
        help="Override the ASS style font name. Defaults to a CJK-capable font "
        "chosen from the source language (e.g. Noto Sans CJK JP).",
    )
    parser.add_argument(
        "--ass-fontsize",
        type=int,
        help="Override the ASS subtitle font size (default 52).",
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
        "--source-lang",
        help="For YouTube: force a specific source language (ja, zh, zh-TW, ko, "
        "yue, en). A non-English value overrides the English-first shortcut and "
        "fetches that language's track (manual preferred, auto-generated "
        "fallback). For local files (--file): when --asr-lang is left 'auto' or "
        "ASR returns an unknown language, this value is used as the translation "
        "source-language hint.",
    )
    parser.add_argument(
        "--download-video",
        nargs="?",
        const="best",
        default=None,
        choices=["best", "av1", "vp9", "h264"],
        help="Also download the YouTube video. Optionally prefer a codec: "
        "best (default), av1, vp9, or h264. Requires yt-dlp + ffmpeg.",
    )
    parser.add_argument(
        "--download-subtitle",
        action="store_true",
        help="Also download the video's English subtitle track (manual preferred, "
        "auto-generated fallback) if one exists. Requires yt-dlp.",
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
        default=None,
        help="Maximum ASR audio segment length before post-splitting into cues.",
    )
    parser.add_argument(
        "--asr-max-end-silence-ms",
        type=int,
        default=None,
        help="Trailing silence allowed before VAD closes a speech segment.",
    )
    parser.add_argument(
        "--asr-speech-noise-threshold",
        type=float,
        default=None,
        help="FunASR VAD speech/noise threshold.",
    )
    parser.add_argument(
        "--asr-noise-db",
        type=float,
        default=None,
        help="ffmpeg silencedetect noise threshold in dB.",
    )
    parser.add_argument(
        "--asr-min-silence-s",
        type=float,
        default=None,
        help="Minimum silence duration for ffmpeg silence detection.",
    )
    parser.add_argument(
        "--asr-max-cue-duration-ms",
        type=int,
        default=None,
        help="Preferred maximum subtitle cue duration.",
    )
    parser.add_argument(
        "--asr-max-cue-chars",
        type=int,
        default=None,
        help="Preferred maximum subtitle cue character count (non-CJK).",
    )
    parser.add_argument(
        "--asr-max-cue-chars-cjk",
        type=int,
        default=None,
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
    parser.add_argument(
        "--asr-preprocess",
        choices=["auto", "none", "basic", "loudnorm", "denoise"],
        default=None,
        help="FFmpeg preprocessing profile for local ASR (default: auto).",
    )
    parser.add_argument(
        "--content-preset",
        choices=["auto", "drama", "anime", "music", "documentary", "variety", "lecture"],
        default="auto",
        help="Content-aware ASR and translation defaults (default: auto).",
    )
    parser.add_argument(
        "--prompt-profile",
        choices=["general", "drama", "anime", "music", "documentary", "variety", "lecture"],
        default=None,
        help="Optional content addendum appended to the translation prompt.",
    )
    parser.add_argument(
        "--context-mode",
        choices=["off", "light", "standard", "deep"],
        default=None,
        help="Translation context amount; defaults to the content preset.",
    )
    parser.add_argument(
        "--context-summary",
        action="store_true",
        help="Maintain a rolling scene summary for cloud translation context "
        "(cloud only; disabled by default).",
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
    parser.add_argument(
        "--result-json",
        help="Write final cues and quality data as JSON for GUI review.",
    )
    parser.add_argument(
        "--json-progress",
        action="store_true",
        help="Emit machine-readable JSON progress lines for the GUI. The final "
        "'Wrote N cues to ...' line is unchanged.",
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


def _json_progress(args, stage: str, done: int, total: int) -> None:
    """Emit one machine-readable JSON progress line when ``--json-progress`` is set.

    The GUI bridge can parse these lines for a progress bar without changing the
    existing human-readable log or the final ``Wrote N cues to ...`` contract.
    """
    if not getattr(args, "json_progress", False):
        return
    print(
        '{"type":"progress","stage":"%s","done":%d,"total":%d}'
        % (stage, done, total),
        flush=True,
    )


# --- Cooperative cancellation (GUI stop button) ------------------------------
# The GUI worker calls translate.main() in-process; the bridge flips this flag
# from its Slot and the pipeline polls it between stages/batches. It is only
# ever reset at the start of a run, so a cancel clicked mid-run cannot leak
# into the next one.
_cancel_requested = False


def request_cancel() -> None:
    """Ask the running pipeline to stop cleanly at the next checkpoint."""
    global _cancel_requested
    _cancel_requested = True


def reset_cancel() -> None:
    """Clear a previous cancel request so it cannot leak into the next run.

    The GUI worker runs translate.main() in-process, so without this a single
    Stop click would make every later run abort immediately.
    """
    global _cancel_requested
    _cancel_requested = False


def _poll_cancel() -> bool:
    """cancel_check predicate passed into the translation loop."""
    return _cancel_requested


def _run_pipeline(
    args: argparse.Namespace, settings, fetched: tuple[list, str | None, str | None]
) -> int:
    """Translate fetched cues and write the SRT. Shared by local/remote."""
    cues, title, source_lang = fetched
    _json_progress(args, "fetch", 0, max(len(cues), 1))

    # --- Source-language precedence -----------------------------------------
    # Explicit user flags win (--asr-lang on a local file, --source-lang on a
    # YouTube URL). A specific code already returned by the fetcher/ASR
    # (e.g. zh-TW, ja, ko, yue) is authoritative and preserved. Script-ratio
    # detection runs ONLY when the language is missing/auto/unknown (or an
    # English fallback was used), so chengyu flagging and Classical-Chinese
    # detection still activate without downgrading a precise fetched code.
    if (
        getattr(args, "asr_lang", "auto") in (None, "", "auto")
        and not getattr(args, "source_lang", "")
        and not _is_english(source_lang)
        and not _is_known_source_code(source_lang)
    ):
        # Use the robust script-ratio detector on a larger cue sample so an
        # opening song, sign, greeting, or mixed-language segment does not skew
        # the language the translation prompt is built around.
        from src.cjk import detect_cjk_from_cues
        detected = detect_cjk_from_cues(cues) or _detect_cjk_lang(
            " ".join(c.text or "" for c in cues[:5])
        )
        if detected:
            print(
                f"[detect] --asr-lang auto; script heuristic detected "
                f"'{detected}' from source text; forwarding to translation.",
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

    # --- Mode summary -------------------------------------------------------
    source_label = "local file" if getattr(args, "file", None) else "YouTube"
    backend_label = "local" if getattr(args, "local", False) else "cloud"
    print(f"[mode] source={source_label} backend={backend_label}", flush=True)

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
        from src.translate import TranslationEndpointError, TranslationCancelled

        def _translation_progress(done: int, total: int, stage: str) -> None:
            _json_progress(args, stage, done, total)

        try:
            translations = translate_cues(
                cues, client, settings.model,
                batch_size=args.batch, source_language=source_lang,
                glossary=glossary_str or None,
                translation_memory=tm,
                context_mode=getattr(args, "context_mode", None),
                prompt_profile=getattr(args, "prompt_profile", None),
                progress_callback=_translation_progress,
                cancel_check=_poll_cancel,
                scene_summary_enabled=bool(
                    getattr(args, "context_summary", False)
                ),
            )
        except TranslationCancelled:
            print(
                "Cancelled by user; stopping at the next batch boundary. "
                "No output file was written.",
                flush=True,
            )
            # Close TM before returning so the SQLite handle is never left
            # open on the cancelled path.
            if tm is not None:
                tm.close()
            return 2
        except TranslationEndpointError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            print(
                "The configured endpoint is not serving an OpenAI-compatible "
                "chat/completions API, so translation was aborted instead of "
                "retrying forever. Check Settings \u2192 Base URL. For the bundled "
                "local llama-server use http://127.0.0.1:8080/v1.",
                file=sys.stderr, flush=True,
            )
            # Close TM before returning so the SQLite handle is never left open
            # on the endpoint-failure path (P0-3).
            if tm is not None:
                tm.close()
            return 1

    _json_progress(args, "translate", len(cues), len(cues))
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
        # The untranslated marker is intentional -- never strip or alter it so a
        # failed cue stays visible instead of silently becoming an empty/live line.
        if (t or "").strip() == UNTRANSLATED_MARKER:
            return UNTRANSLATED_MARKER
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
        out_path = default_output_path(args.file, title, fmt)
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
        write_ass(
            out_path,
            ass_cues,
            source_language=source_lang,
            font=getattr(args, "ass_font", None),
            fontsize=getattr(args, "ass_fontsize", None),
            title=title or "Subtitles",
        )
    else:
        # SRT uses a literal newline, so translate the \\N line breaks.
        srt_cues = [
            Cue(start=c.start, end=c.end, text=c.text.replace("\\N", "\n"))
            for c in out_cues
        ]
        write_srt(srt_cues, out_path)

    _json_progress(args, "write", len(out_cues), len(out_cues))

    # --- Completion summary -------------------------------------------------
    # A partially-broken output must never be mistaken for a complete
    # translation: the untranslated count is surfaced unconditionally.
    #
    # Recompute the failed/untranslated count from the FINAL post-processed
    # output (not the intermediate translation list) so a cue that became empty
    # or [untranslated] after sanitization/postprocessing is not undercounted.
    failed_indices = [
        i for i, c in enumerate(out_cues) if _is_failed_text(c.text)
    ]
    print(
        f"[mode] Completed: {len(out_cues)} cues written, "
        f"{len(failed_indices)} untranslated. Format: {fmt}.",
        flush=True,
    )

    # --- Quality report ----------------------------------------------------
    report = build_report(out_cues, untranslated_count=len(failed_indices))
    if getattr(args, "quality_report", None):
        print_summary(out_cues, untranslated_count=len(failed_indices))
        try:
            with open(args.quality_report, "w", encoding="utf-8") as f:
                f.write(report.to_json())
            print(f"[quality] Report written to {args.quality_report}", flush=True)
        except OSError as exc:
            print(f"[quality] Could not write report: {exc}", flush=True)

    if getattr(args, "result_json", None):
        import json

        warning_cues = {
            int(issue["cue_index"])
            for issue in report.issues
            if any(tag.endswith("_warning") for tag in issue["issues"])
        }
        pipeline_mode = (
            "offline" if getattr(args, "local", False)
            else "local_cloud" if getattr(args, "file", None)
            else "youtube_cloud"
        )
        result = {
            "version": 1,
            "output_path": os.path.abspath(out_path),
            "format": fmt,
            "source_language": source_lang,
            "pipeline_mode": pipeline_mode,
            "strict_quality": bool(getattr(args, "strict_quality", False)),
            "quality": report.to_dict(),
            "cues": [
                {
                    "index": index + 1,
                    "start_ms": round(cue.start * 1000),
                    "end_ms": round(cue.end * 1000),
                    "source": cues[index].text,
                    "text": cue.text,
                    "status": (
                        "untranslated" if _is_failed_text(cue.text)
                        else "warning" if index in warning_cues else "ok"
                    ),
                }
                for index, cue in enumerate(out_cues)
            ],
        }
        try:
            with open(args.result_json, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"[result] JSON written to {args.result_json}", flush=True)
        except OSError as exc:
            print(f"[result] Could not write result JSON: {exc}", flush=True)

    # --- Strict quality check ----------------------------------------------
    if getattr(args, "strict_quality", False):
        if report.error_count > 0 or report.untranslated_count > 0:
            print(
                f"[quality] {report.error_count} serious errors + "
                f"{report.untranslated_count} untranslated cues found "
                f"(--strict-quality enabled).",
                file=sys.stderr, flush=True,
            )
            # Close TM BEFORE returning so the SQLite handle is never left open
            # on the strict-quality failure path (P0-3).
            if tm is not None:
                tm.close()
            return 1

    # Close TM if we opened it.
    if tm is not None:
        tm.close()

    # The `Wrote N cues to ...` line MUST be the final line of CLI output — the
    # GUI TranslationWorker regex keys off this exact line.
    print(f"Wrote {len(out_cues)} cues to {out_path}")

    return 0


def _video_selector_for(choice: str, info: dict) -> str:
    """Build a yt-dlp format selector for the user's codec preference.

    Raises ``RuntimeError`` when the video has no such stream: there is
    deliberately no ``bv*+ba/b`` fallback, which would quietly download a
    different codec/resolution than the one that was asked for.
    """
    # Local import, like the rest of this module's yt-dlp usage: the import in
    # ``_download_youtube_media`` is function-scoped and does NOT make the name
    # visible here, which used to crash ``--download-video <codec>`` with a
    # NameError instead of downloading.
    from src import youtube_media

    opt = youtube_media.resolve_video_option(info, choice, "best")
    if opt and opt.get("format_selector"):
        return opt["format_selector"]
    reason = youtube_media.describe_unavailable(info, choice, "best")
    raise RuntimeError(
        reason or f"No {choice} stream is available for this video.")


def _download_youtube_media(args) -> None:
    """Download the video and/or English subtitle for a YouTube URL (CLI)."""
    from src import youtube_media

    out_dir = os.path.dirname(os.path.abspath(args.out)) if args.out else "."
    template = os.path.join(out_dir, "%(title)s [%(id)s]")

    if args.download_subtitle:
        try:
            path = youtube_media.download_subtitle(args.url, "en", template)
            print(f"Downloaded subtitle: {path}")
        except RuntimeError as exc:
            print(f"[warn] {exc}")

    if args.download_video:
        try:
            info = youtube_media.inspect_video(args.url)
            selector = _video_selector_for(args.download_video, info)
            path = youtube_media.download_video(
                args.url, selector, template + ".%(ext)s"
            )
            print(f"Downloaded video: {path}")
        except RuntimeError as exc:
            print(f"[error] {exc}")


def main(argv: list[str] | None = None) -> int:
    # A cancel requested during a previous in-process run must never leak into
    # this one (the GUI reuses this module for every run).
    reset_cancel()
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    from src.presets import resolve_effective_settings

    try:
        resolve_effective_settings(args)
    except (TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

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
                preprocess=args.asr_preprocess or "auto",
            )
            stem = os.path.splitext(os.path.basename(args.file))[0]

            # For local files, --source-lang is a translation source-language hint
            # used only when --asr-lang is 'auto' or ASR returned an unknown/und
            # language. It never overrides an explicit --asr-lang (which controls
            # ASR recognition) or a confident ASR detection.
            if args.source_lang and (
                getattr(args, "asr_lang", "auto") in (None, "", "auto")
                or not source_language
                or str(source_language).strip().lower() in ("auto", "und", "none")
            ):
                source_language = args.source_lang

            fetched = (cues, sanitize_filename(stem), source_language)
        except (RuntimeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        try:
            fetched = fetch_original_subtitles(args.url, preferred_lang=args.source_lang)
        except (RuntimeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        # Optional: download the video and/or its English subtitle alongside the
        # subtitle translation pipeline.
        if args.download_video or args.download_subtitle:
            _download_youtube_media(args)

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

        # Point the translation backend at the local server transactionally so
        # subsequent GUI runs are never contaminated by a stale local endpoint.
        # Only OPENAI_BASE_URL is touched here (the API key is read-only in this
        # path), so only it needs restoring afterwards.
        prev_base_url = os.environ.get("OPENAI_BASE_URL")
        os.environ["OPENAI_BASE_URL"] = base_url
        try:
            settings = load_settings(override_model=args.local_model_name)
            return _run_pipeline(args, settings, fetched)
        finally:
            if prev_base_url is None:
                os.environ.pop("OPENAI_BASE_URL", None)
            else:
                os.environ["OPENAI_BASE_URL"] = prev_base_url

    try:
        settings = load_settings(override_model=args.model)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return _run_pipeline(args, settings, fetched)


if __name__ == "__main__":
    raise SystemExit(main())
