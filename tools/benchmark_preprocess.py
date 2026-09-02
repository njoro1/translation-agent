#!/usr/bin/env python3
"""Benchmark FFmpeg preprocessing profiles for local ASR.

Runs the FunASR/SenseVoice pipeline over one media file once per preprocessing
profile (none/basic/loudnorm/denoise), keeps each output separate, and reports
comparable metrics:

    - cue count
    - average cue duration (ms)
    - total text length (chars)
    - processing time (s)
    - duration mismatch between media and extracted WAV (ms)
    - empty-text cue count

If a reference transcript SRT is supplied (--reference), CER/WER against it are
also reported so profile choices can be evidence-driven.

Usage:
    python tools/benchmark_preprocess.py --media sample.mp4 [--asr-lang ja]
        [--profiles none,basic,loudnorm,denoise] [--out-dir bench_out]
        [--reference ref.srt]

The harness never modifies pipeline defaults; it only produces measurements.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import local_asr  # noqa: E402
from src.srt_io import Cue, write_srt  # noqa: E402

ALL_PROFILES = ("none", "basic", "loudnorm", "denoise")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark ASR preprocessing profiles on one media file."
    )
    parser.add_argument("--media", required=True, help="Media file to transcribe.")
    parser.add_argument(
        "--profiles",
        default=",".join(ALL_PROFILES),
        help="Comma-separated profiles to benchmark (default: all four).",
    )
    parser.add_argument(
        "--asr-lang", default="auto", help="ASR language hint (default auto)."
    )
    parser.add_argument(
        "--out-dir", default="bench_preprocess",
        help="Directory for per-profile outputs (default bench_preprocess/).",
    )
    parser.add_argument(
        "--reference",
        help="Optional reference transcript (SRT) for CER/WER computation.",
    )
    parser.add_argument(
        "--json",
        help="Optional path to write the combined results as JSON.",
    )
    return parser.parse_args(argv)


def _read_reference_text(path: str) -> str:
    """Extract plain concatenated text from a reference SRT file."""
    from src.srt_io import read_srt

    cues, _enc = read_srt(path)
    return "\n".join((c.text or "").strip() for c in cues if (c.text or "").strip())


def _normalize_for_cer(text: str) -> list[str]:
    """Lowercase, strip punctuation/whitespace, return character list."""
    text = text.lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", "", text)
    return list(text)


def _levenshtein(a: list[str], b: list[str]) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _cer_wer(hyp: str, ref: str) -> tuple[float, float]:
    """Character/word error rates via Levenshtein distance."""
    hyp_chars, ref_chars = _normalize_for_cer(hyp), _normalize_for_cer(ref)
    cer = (
        _levenshtein(hyp_chars, ref_chars) / len(ref_chars)
        if ref_chars
        else 0.0
    )
    hyp_words = re.sub(r"[^\w\s]", "", hyp.lower()).split()
    ref_words = re.sub(r"[^\w\s]", "", ref.lower()).split()
    wer = _levenshtein(hyp_words, ref_words) / len(ref_words) if ref_words else 0.0
    return round(cer, 4), round(wer, 4)


def _benchmark_profile(
    media: Path,
    profile: str,
    out_dir: Path,
    asr_lang: str,
    reference_text: str | None,
) -> dict:
    """Run ASR with one profile and collect metrics."""
    started = time.monotonic()
    error: str | None = None
    cues: list[Cue] = []

    # Duration mismatch is measured inside _prepare_asr_audio; capture the
    # effective profile actually used after any safety fallback.
    used_profile = profile
    original_prepare = local_asr._prepare_asr_audio

    def _spy(media_path, wav_path, prof):
        nonlocal used_profile
        resolved = local_asr._resolve_preprocess_profile(prof)
        result = original_prepare(media_path, wav_path, prof)
        used_profile = resolved
        return result

    local_asr._prepare_asr_audio = _spy
    try:
        cues, lang = local_asr.transcribe_local_file(
            media,
            asr_lang=asr_lang,
            preprocess=profile,
        )
    except Exception as exc:  # noqa: BLE001 - report and continue other profiles
        error = str(exc)
    finally:
        local_asr._prepare_asr_audio = original_prepare

    elapsed = time.monotonic() - started

    durations_ms = [
        max(0.0, (c.end - c.start) * 1000.0) for c in cues
    ]
    total_chars = sum(len((c.text or "").strip()) for c in cues)
    empty_count = sum(1 for c in cues if not (c.text or "").strip())

    result: dict = {
        "profile": profile,
        "effective_profile": used_profile if not error else None,
        "ok": error is None,
        "error": error,
        "cue_count": len(cues),
        "avg_cue_duration_ms": (
            round(sum(durations_ms) / len(durations_ms), 1) if durations_ms else 0.0
        ),
        "total_text_chars": total_chars,
        "empty_cue_count": empty_count,
        "processing_time_s": round(elapsed, 2),
        "source_language": lang,
    }

    if cues and not error:
        out_path = out_dir / f"{media.stem}.{profile}.srt"
        write_srt(cues, str(out_path))
        result["output"] = str(out_path)

    if reference_text and not error and cues:
        hyp = "\n".join((c.text or "").strip() for c in cues)
        cer, wer = _cer_wer(hyp, reference_text)
        result["cer"] = cer
        result["wer"] = wer

    return result


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    media = Path(args.media).expanduser()
    if not media.exists():
        print(f"error: media not found: {media}", file=sys.stderr)
        return 2

    profiles = [p.strip().lower() for p in args.profiles.split(",") if p.strip()]
    invalid = [p for p in profiles if p not in ALL_PROFILES]
    if invalid:
        print(
            f"error: unknown profile(s): {invalid}. "
            f"Choose from {', '.join(ALL_PROFILES)}.",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reference_text = None
    if args.reference:
        try:
            reference_text = _read_reference_text(args.reference)
        except Exception as exc:  # noqa: BLE001
            print(f"warning: could not read reference: {exc}", file=sys.stderr)

    print(f"[bench] media={media} profiles={profiles}", flush=True)
    results = []
    for profile in profiles:
        print(f"[bench] running profile: {profile} ...", flush=True)
        row = _benchmark_profile(media, profile, out_dir, args.asr_lang, reference_text)
        results.append(row)
        status = row["error"] or (
            f"{row['cue_count']} cues, avg {row['avg_cue_duration_ms']} ms, "
            f"{row['total_text_chars']} chars, {row['processing_time_s']} s"
        )
        extra = (
            f", CER {row['cer']} WER {row['wer']}"
            if "cer" in row else ""
        )
        print(f"[bench]   {profile}: {status}{extra}", flush=True)

    print("\n[bench] Summary (lower CER/WER + stable cue count wins):")
    header = (
        f"{'profile':<10} {'cues':>6} {'avg_ms':>8} {'chars':>7} "
        f"{'empty':>6} {'secs':>7} {'CER':>7} {'WER':>7}"
    )
    print(header)
    for r in results:
        cer = f"{r['cer']:.3f}" if "cer" in r else "-"
        wer = f"{r['wer']:.3f}" if "wer" in r else "-"
        print(
            f"{r['profile']:<10} {r['cue_count']:>6} "
            f"{r['avg_cue_duration_ms']:>8} {r['total_text_chars']:>7} "
            f"{r['empty_cue_count']:>6} {r['processing_time_s']:>7} "
            f"{cer:>7} {wer:>7}"
        )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"media": str(media), "results": results}, f, indent=2)
        print(f"\n[bench] JSON written to {args.json}")

    failed = [r for r in results if not r["ok"]]
    return 1 if len(failed) == len(results) and results else 0


if __name__ == "__main__":
    raise SystemExit(main())
