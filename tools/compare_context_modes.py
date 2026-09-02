#!/usr/bin/env python3
"""A/B compare context modes (light vs standard) on the local Hy-MT2 pipeline.

Method:
    1. ASR the media ONCE (cached) so both modes translate identical cues.
    2. Start the bundled local llama-server (Hy-MT2).
    3. Translate all cues per context mode (no translation memory — fresh).
    4. Score each mode against a reference SRT via timestamp-overlap alignment:
       normalized exact-match rate + avg SequenceMatcher similarity (both
       directions), plus alignment-health counters from the captured log.

Usage:
    python tools/compare_context_modes.py --media dist/video.mp4 \
        --reference dist/ref.srt [--modes light,standard] [--asr-lang zh] \
        [--cache asr_cues.json] [--json compare.json]
"""
from __future__ import annotations

import argparse
import contextlib
import difflib
import io
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_REPO_ROOT)
# local_server resolves bundled binaries via dirname(abspath(sys.argv[0]));
# point it at a file INSIDE the repo root so vendor/llama is found when the
# tool is launched from tools/.
sys.argv[0] = os.path.join(_REPO_ROOT, "compare_context_modes.py")

from src.srt_io import Cue, read_srt  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--media", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--modes", default="light,standard")
    p.add_argument("--asr-lang", default="auto")
    p.add_argument("--cache", default="cache/compare_asr_cues.json")
    p.add_argument("--json", default="cache/compare_context_modes.json")
    p.add_argument("--max-cues", type=int, default=0,
                   help="Optional cap on cues (0 = all).")
    return p.parse_args()


_PUNCT_RE = re.compile(r"[^\w\s\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", re.UNICODE)


def _norm(text: str) -> str:
    text = (text or "").replace("\\N", " ").replace("\n", " ").lower()
    text = _PUNCT_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


class _CountingClient:
    def __init__(self, client):
        self._client = client
        self.calls = 0
        self.failures = 0

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, *args, **kwargs):
        self.calls += 1
        try:
            return self._client.chat.completions.create(*args, **kwargs)
        except Exception:
            self.failures += 1
            raise


def _asr(media: str, asr_lang: str, cache: str) -> tuple[list[Cue], str | None]:
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            data = json.load(f)
        cues = [Cue(d["start"], d["end"], d["text"]) for d in data["cues"]]
        print(f"[compare] loaded {len(cues)} cached ASR cues from {cache}",
              flush=True)
        return cues, data.get("source_language")

    from src.local_asr import transcribe_local_file

    t0 = time.monotonic()
    cues, lang = transcribe_local_file(media, asr_lang=asr_lang)
    print(f"[compare] ASR: {len(cues)} cues in "
          f"{time.monotonic() - t0:.0f}s (lang={lang})", flush=True)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(
            {"source_language": lang,
             "cues": [{"start": c.start, "end": c.end, "text": c.text}
                      for c in cues]},
            f, ensure_ascii=False,
        )
    return cues, lang


def _reliability(log: str) -> dict:
    low = log.lower()
    return {
        "batch_failures": low.count("batch error") + low.count("batch failed"),
        "window_splits": low.count("splitting into"),
        "per_item_retries": low.count("rejected cue(s)"),
        "per_item_rejections": low.count("per-item result rejected"),
    }


def _reference_scores(
    out_cues: list[Cue], ref_cues: list[Cue],
) -> dict:
    """Timestamp-overlap alignment, similarity both directions."""
    def _best(text: str, candidates: list[Cue]) -> tuple[float, float]:
        norm_a = _norm(text)
        if not norm_a or not candidates:
            return 0.0, 0.0
        best_ratio, best_exact = 0.0, 0.0
        for cand in candidates:
            norm_b = _norm(cand.text)
            if not norm_b:
                continue
            ratio = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
            best_ratio = max(best_ratio, ratio)
            best_exact = max(best_exact, 1.0 if norm_a == norm_b else 0.0)
        return best_ratio, best_exact

    def _overlapping(cue: Cue, pool: list[Cue], pad: float = 1.5):
        return [c for c in pool
                if c.start < cue.end + pad and c.end > cue.start - pad]

    fwd_ratios: list[float] = []
    fwd_exact: list[float] = []
    unmatched = 0
    for cue in out_cues:
        cands = _overlapping(cue, ref_cues)
        if not cands:
            unmatched += 1
            continue
        ratio, exact = _best(cue.text, cands)
        fwd_ratios.append(ratio)
        fwd_exact.append(exact)

    rev_ratios: list[float] = []
    rev_exact: list[float] = []
    for cue in ref_cues:
        cands = _overlapping(cue, out_cues)
        if not cands:
            continue
        ratio, exact = _best(cue.text, cands)
        rev_ratios.append(ratio)
        rev_exact.append(exact)

    avg = lambda xs: round(sum(xs) / len(xs), 4) if xs else 0.0  # noqa: E731
    return {
        "out_cues_scored": len(fwd_ratios),
        "out_cues_unmatched": unmatched,
        "fwd_similarity": avg(fwd_ratios),
        "fwd_exact_rate": avg(fwd_exact),
        "ref_similarity": avg(rev_ratios),
        "ref_exact_rate": avg(rev_exact),
    }


def main() -> int:
    args = _parse_args()
    modes = [m.strip().lower() for m in args.modes.split(",") if m.strip()]

    ref_cues = read_srt(args.reference)
    print(f"[compare] reference: {len(ref_cues)} cues from {args.reference}",
          flush=True)

    cues, lang = _asr(args.media, args.asr_lang, args.cache)
    if args.max_cues:
        cues = cues[:args.max_cues]
        print(f"[compare] capped to first {len(cues)} cues", flush=True)

    # --- Local server -------------------------------------------------------
    from backend.bridge import resolve_local_model_path

    model_path = resolve_local_model_path("gguf")
    if not model_path or not os.path.exists(model_path):
        print(f"[compare] local model not found in ./gguf: {model_path!r}",
              file=sys.stderr)
        return 2
    from src.config import load_settings, make_client
    from src.local_server import ensure_local_server, shutdown_servers, warmup_local_server  # noqa: E501
    from src.translate import _is_hy_mt2, translate_cues

    _proc, how, port = ensure_local_server(model_path, "127.0.0.1", 8080)
    print(f"[compare] llama-server ({how}) on 127.0.0.1:{port}", flush=True)
    base_url = f"http://127.0.0.1:{port}/v1"
    warmup_local_server(base_url, "Hy-MT2-1.8B-Q8_0")

    prev = os.environ.get("OPENAI_BASE_URL")
    os.environ["OPENAI_BASE_URL"] = base_url
    settings = load_settings(override_model="Hy-MT2-1.8B-Q8_0")
    assert _is_hy_mt2(settings.model)

    results = []
    try:
        for mode in modes:
            client = _CountingClient(make_client(settings))
            captured = io.StringIO()
            t0 = time.monotonic()
            with contextlib.redirect_stdout(captured):
                translations = translate_cues(
                    cues, client, settings.model,
                    batch_size=8, source_language=lang,
                    context_mode=mode,
                )
            elapsed = time.monotonic() - t0
            log = captured.getvalue()

            out_cues = [Cue(c.start, c.end, (t or "").strip())
                        for c, t in zip(cues, translations)]
            untranslated = sum(1 for c in out_cues if not c.text)
            rel = _reliability(log)
            scores = _reference_scores(out_cues, ref_cues)

            row = {
                "mode": mode,
                "runtime_s": round(elapsed, 1),
                "model_calls": client.calls,
                "untranslated": untranslated,
                **rel,
                **scores,
            }
            results.append(row)
            print(f"[compare] {mode}: {json.dumps(row)}", flush=True)

            out_srt = f"cache/compare_output_{mode}.srt"
            from src.srt_io import write_srt

            write_srt(out_cues, out_srt)
            print(f"[compare]   output written: {out_srt}", flush=True)
    finally:
        os.environ.pop("OPENAI_BASE_URL", None) if prev is None else None
        if prev is not None:
            os.environ["OPENAI_BASE_URL"] = prev
        shutdown_servers()

    os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump({"media": args.media, "reference": args.reference,
                   "cue_count": len(cues), "ref_count": len(ref_cues),
                   "results": results}, f, indent=2, ensure_ascii=False)

    print("\n[compare] SUMMARY (higher similarity/exact = closer to reference)",
          flush=True)
    print(f"{'mode':<10} {'runtime_s':>9} {'calls':>6} {'untrans':>8} "
          f"{'splits':>7} {'per_item':>9} {'fwd_sim':>8} {'fwd_exact':>10} "
          f"{'ref_sim':>8}", flush=True)
    for r in results:
        print(f"{r['mode']:<10} {r['runtime_s']:>9} {r['model_calls']:>6} "
              f"{r['untranslated']:>8} {r['window_splits']:>7} "
              f"{r['per_item_retries']:>9} {r['fwd_similarity']:>8} "
              f"{r['fwd_exact_rate']:>10} {r['ref_similarity']:>8}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
