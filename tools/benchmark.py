#!/usr/bin/env python3
"""Benchmark harness for the subtitle translation pipeline.

Measures pipeline changes objectively without heavyweight dependencies.

Usage:
    python tools/benchmark.py --cases benchmark/cases.json --output benchmark/results/run.json

Optional flags:
    --case-id ID        Only run the case with this id.
    --local             Use the local llama.cpp server (Hy-MT2).
    --model NAME        Cloud model to use for translation.
    --batch N           Batch size override.
    --cloud-rescue      Enable cloud rescue during the run.

Reference-based quality metrics (exact match, length ratio) are computed when a
reference_translation JSON is available. Missing media files produce clear errors.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.srt_io import Cue, read_srt
from src.subtitle_quality import analyze_cues


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="benchmark/cases.json",
                        help="Path to the benchmark cases JSON file.")
    parser.add_argument("--output", default="benchmark/results/run.json",
                        help="Path for the JSON results file.")
    parser.add_argument("--case-id", help="Run only the case with this id.")
    parser.add_argument("--local", action="store_true", help="Use the local server.")
    parser.add_argument("--model", help="Cloud model name.")
    parser.add_argument("--batch", type=int, help="Batch size override.")
    parser.add_argument("--cloud-rescue", action="store_true", help="Enable rescue.")
    parser.add_argument(
        "--cloud-rescue-model",
        default=os.environ.get("CLOUD_RESCUE_MODEL"),
        help="Cloud model used for rescue (default: same as --model).",
    )
    parser.add_argument(
        "--cloud-rescue-batch",
        type=int,
        default=int(os.environ.get("CLOUD_RESCUE_BATCH", "10")),
        help="Batch size for cloud rescue (default 10).",
    )
    return parser.parse_args(argv)


def _load_cases(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


def _load_cues_from_json(path: str) -> list[Cue]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [
        Cue(start=float(item["start"]), end=float(item["end"]), text=item["text"])
        for item in data
    ]


class _CountingClient:
    """Wraps an OpenAI client and counts calls/failures."""

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
        except Exception as exc:  # noqa: BLE001
            self.failures += 1
            raise exc


def _run_case(case: dict, args: argparse.Namespace, local_server_proc) -> dict:
    """Run one benchmark case and return its metrics."""
    case_id = case["id"]
    print(f"Benchmark: {case_id}", flush=True)
    start_total = time.monotonic()

    result: dict = {"id": case_id, "notes": case.get("notes", "")}
    cues: list[Cue] = []
    source_language: str | None = None

    # --- Source stage ------------------------------------------------------
    asr_start = time.monotonic()
    if case.get("type") == "local_media":
        media = case.get("media")
        if not media or not Path(media).exists():
            raise FileNotFoundError(
                f"[benchmark] Missing media file for case {case_id}: {media!r}"
            )
        from src.local_asr import transcribe_local_file

        cues, source_language = transcribe_local_file(
            media, asr_lang=case.get("asr_lang", "auto"),
            max_cue_chars=48, max_cue_chars_cjk=48,
        )
        result["asr_runtime"] = round(time.monotonic() - asr_start, 3)
    elif case.get("type") == "cues_only":
        cues_path = case.get("cues")
        if not cues_path or not Path(cues_path).exists():
            raise FileNotFoundError(
                f"[benchmark] Missing cues file for case {case_id}: {cues_path!r}"
            )
        cues = _load_cues_from_json(cues_path)
        source_language = case.get("source_language")
        result["asr_runtime"] = 0.0
    elif case.get("type") == "srt":
        srt_path = case.get("srt")
        if not srt_path or not Path(srt_path).exists():
            raise FileNotFoundError(
                f"[benchmark] Missing SRT file for case {case_id}: {srt_path!r}"
            )
        cues = read_srt(srt_path)
        source_language = case.get("source_language")
        result["asr_runtime"] = 0.0
    else:
        raise ValueError(f"[benchmark] Unknown case type: {case.get('type')!r}")

    return _translate_case(cues, source_language, case, args, result, start_total)


def _add_subtitle_metrics(cues, out_cues, translations, case, result) -> None:
    """Compute subtitle metrics and optional reference-based quality."""
    durations = [c.end - c.start for c in out_cues]
    empty = sum(1 for c in out_cues if not (c.text or "").strip())
    issues = analyze_cues(out_cues)
    error_count = sum(1 for ci in issues if ci.has_errors)
    warning_count = sum(1 for ci in issues if ci.has_warnings)

    def cps(c):
        d = c.end - c.start
        return 0.0 if d <= 0 else len((c.text or "").replace("\n", "")) / d

    cps_values = [cps(c) for c in out_cues]

    result["cue_count_in"] = len(cues)
    result["cue_count_out"] = len(out_cues)
    result["cue_count_mismatch"] = len(cues) - len(out_cues)
    result["empty_cues"] = empty
    result["average_duration"] = round(sum(durations) / len(durations), 3) if durations else 0.0
    result["max_duration"] = round(max(durations), 3) if durations else 0.0
    result["average_cps"] = round(sum(cps_values) / len(cps_values), 3) if cps_values else 0.0
    result["max_cps"] = round(max(cps_values), 3) if cps_values else 0.0
    result["quality_warnings"] = warning_count
    result["quality_errors"] = error_count

    reference = case.get("reference_translation")
    if reference and Path(reference).exists():
        with open(reference, "r", encoding="utf-8") as f:
            ref = json.load(f)
        ref_texts = [r["text"] for r in ref]
        if len(ref_texts) == len(translations):
            exact = sum(
                1 for a, b in zip(ref_texts, translations)
                if a.strip() == b.strip()
            )
            result["exact_match_rate"] = round(exact / len(ref_texts), 3)
            result["exact_matches"] = exact
            ratios = [
                len(b.replace(" ", "")) / max(1, len(a.replace(" ", "")))
                for a, b in zip(ref_texts, translations)
            ]
            result["avg_length_ratio"] = round(sum(ratios) / len(ratios), 3)


def _build_rescue_handler(args, source_language: str | None):
    """Build an optional cloud-rescue handler, or None if rescue shouldn't run.

    Rescue is only wired when ``--cloud-rescue`` is explicitly passed AND a real
    cloud API key (not the local ``sk-local`` placeholder) is available. This keeps
    the benchmark fully usable offline in local mode — rescue simply stays dormant
    until a cloud key is present.
    """
    if not getattr(args, "cloud_rescue", False):
        return None

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "sk-local":
        print(
            "[benchmark] Cloud rescue requested but no real cloud credentials "
            "are available (OPENAI_API_KEY unset or local placeholder); "
            "rescue skipped.",
            flush=True,
        )
        return None

    rescue_model = (
        getattr(args, "cloud_rescue_model", None)
        or os.environ.get("CLOUD_RESCUE_MODEL")
        or os.environ.get("OPENAI_MODEL")
    )
    if not rescue_model:
        print(
            "[benchmark] Cloud rescue requested but no rescue model is set "
            "(--cloud-rescue-model / CLOUD_RESCUE_MODEL / OPENAI_MODEL); "
            "rescue skipped.",
            flush=True,
        )
        return None

    from src.config import Settings, make_client
    from src.rescue import rescue_failed_cues

    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    settings = Settings(api_key=api_key, base_url=base_url, model=rescue_model)
    rescue_client = make_client(settings)
    batch_size = getattr(args, "cloud_rescue_batch", 10) or 10

    def _handler(cues, failed_indices):
        return rescue_failed_cues(
            cues=cues,
            failed_indices=failed_indices,
            client=rescue_client,
            model=rescue_model,
            source_language=source_language,
            batch_size=batch_size,
            glossary=None,
        )

    print(f"[benchmark] Cloud rescue wired (model={rescue_model})", flush=True)
    return _handler


def _parse_reliability_metrics(log_text: str) -> dict:
    """Extract reliability counters from the pipeline's stdout log lines.

    These mirror the documented log prefixes in ``updated implementation plan.md``
    section 24 (``[translate]``/``[tm]``/``[rescue]``). Counts are best-effort and
    additive; a counter stays 0 when its log line never appears.
    """
    metrics = {
        "batch_failures": 0,
        "batch_splits": 0,
        "per_item_fallbacks": 0,
        "cache_hits": 0,
        "rescue_attempts": 0,
        "rescue_successes": 0,
    }
    for line in log_text.splitlines():
        low = line.lower()
        if "batch error" in low or "batch failed" in low:
            metrics["batch_failures"] += 1
        if "splitting into" in low:
            metrics["batch_splits"] += 1
        if "per-item fallback" in low:
            metrics["per_item_fallbacks"] += 1
        m_tm = re.search(r"\[tm\] (\d+) cache hits", low)
        if m_tm:
            metrics["cache_hits"] += int(m_tm.group(1))
        m_attempt = re.search(r"\[rescue\] (\d+) cues failed locally", low)
        if m_attempt:
            metrics["rescue_attempts"] = int(m_attempt.group(1))
        m_ok = re.search(
            r"\[rescue\] cloud rescue succeeded for (\d+)/(\d+) cues", low
        )
        if m_ok:
            metrics["rescue_successes"] = int(m_ok.group(1))
    return metrics


def _translate_case(cues, source_language, case, args, result, start_total) -> dict:
    """Translate cues and populate translation/subtitle metrics."""
    from src.config import load_settings, make_client
    from src.translate import translate_cues

    batch = args.batch
    if batch is None:
        batch = 12 if args.local else 40

    if args.local:
        settings = load_settings(override_model="Hy-MT2-1.8B")
    else:
        model = args.model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        settings = load_settings(override_model=model)
    client = make_client(settings)
    counting = _CountingClient(client)

    model_name = settings.model
    if args.local:
        from src.local_server import server_alive

        host = os.environ.get("BENCHMARK_LOCAL_HOST", "127.0.0.1")
        port = int(os.environ.get("BENCHMARK_LOCAL_PORT", "8080"))
        if not server_alive(host, port):
            raise RuntimeError(
                f"[benchmark] Local server not reachable at {host}:{port}. "
                "Start it first or pass --model for a cloud run."
            )

        print(f"[benchmark] Translating {len(cues)} cues with {model_name}", flush=True)
    rescue_handler = _build_rescue_handler(args, source_language)
    trans_start = time.monotonic()
    # Capture the pipeline's stdout log lines so we can derive reliability
    # metrics (batch failures/splits, per-item fallbacks, rescue stats, cache
    # hits). The captured text is parsed below; progress is not re-emitted to
    # keep benchmark output concise.
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        translations = translate_cues(
            cues, counting, model_name, batch_size=batch,
            source_language=source_language,
            rescue_handler=rescue_handler,
        )
    result["translation_runtime"] = round(time.monotonic() - trans_start, 3)

    out_cues = [
        Cue(start=c.start, end=c.end, text=t)
        for c, t in zip(cues, translations)
    ]
    _add_subtitle_metrics(cues, out_cues, translations, case, result)

    result["model_calls"] = counting.calls
    result["model_call_failures"] = counting.failures
    result["total_runtime"] = round(time.monotonic() - start_total, 3)

    rel = _parse_reliability_metrics(captured.getvalue())
    result["batch_failures"] = rel["batch_failures"]
    result["batch_splits"] = rel["batch_splits"]
    result["per_item_fallbacks"] = rel["per_item_fallbacks"]
    result["cache_hits"] = rel["cache_hits"]
    result["rescue_attempts"] = rel["rescue_attempts"]
    result["rescue_successes"] = rel["rescue_successes"]

    print(f"  total_time: {result['total_runtime']}s", flush=True)
    if result.get("asr_runtime"):
        print(f"  asr_time: {result['asr_runtime']}s", flush=True)
    print(f"  translation_time: {result['translation_runtime']}s", flush=True)
    print(f"  cue_count_in: {result['cue_count_in']}", flush=True)
    print(f"  cue_count_out: {result['cue_count_out']}", flush=True)
    print(f"  max_cps: {result['max_cps']}", flush=True)
    print(f"  model_calls: {result['model_calls']}", flush=True)
    print(f"  batch_failures: {result['batch_failures']}", flush=True)
    print(f"  batch_splits: {result['batch_splits']}", flush=True)
    print(f"  per_item_fallbacks: {result['per_item_fallbacks']}", flush=True)
    print(f"  cache_hits: {result['cache_hits']}", flush=True)
    if result["rescue_attempts"] or result["rescue_successes"]:
        print(f"  rescue_attempts: {result['rescue_attempts']}", flush=True)
        print(f"  rescue_successes: {result['rescue_successes']}", flush=True)
    if result.get("exact_match_rate") is not None:
        print(f"  exact_match_rate: {result['exact_match_rate']}", flush=True)
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = _parse_args(argv if argv is not None else sys.argv[1:])

    cases_path = args.cases
    if not os.path.exists(cases_path):
        print(f"[benchmark] Cases file not found: {cases_path}", file=sys.stderr)
        return 1

    cases = _load_cases(cases_path)
    if args.case_id:
        cases = [c for c in cases if c.get("id") == args.case_id]
        if not cases:
            print(f"[benchmark] No case with id {args.case_id!r}", file=sys.stderr)
            return 1

    results = []
    failed = []
    for case in cases:
        try:
            results.append(_run_case(case, args, None))
        except Exception as exc:  # noqa: BLE001
            print(f"[benchmark] Case {case.get('id')} failed: {exc}", file=sys.stderr)
            failed.append({"id": case.get("id"), "error": str(exc)})

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": {
            "local": args.local, "model": args.model,
            "batch": args.batch, "cloud_rescue": args.cloud_rescue,
        },
        "results": results,
        "failed": failed,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"[benchmark] Results written to {args.output}", flush=True)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())




