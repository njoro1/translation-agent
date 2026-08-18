# Benchmark Harness

This directory holds optional benchmark cases and results for the translation
pipeline. The harness lives at `tools/benchmark.py`.

## Running a benchmark

```bash
python tools/benchmark.py --cases benchmark/cases.json --output benchmark/results/run.json
```

Run a single case:

```bash
python tools/benchmark.py --case-id ja-short-dialogue
```

Use the local Hy-MT2 server (it must already be running, e.g. via the GUI or
`translate.py --local`):

```bash
python tools/benchmark.py --local
```

Use a specific cloud model:

```bash
python tools/benchmark.py --model gpt-4o-mini
```

## Case types

- `local_media`: transcribes a local audio/video file with FunASR
  (SenseVoiceSmall), then translates the resulting cues.
- `cues_only`: loads a JSON list of cues `[{start, end, text}]` and translates
  them (no ASR). Good for testing translation alignment in isolation.
- `srt`: reads an existing `.srt` file and translates its cues.

## Metrics collected

Per case, the harness reports:

- **Timing**: `total_runtime`, `asr_runtime`, `translation_runtime`
- **Reliability**: `model_calls`, `model_call_failures`
- **Subtitles**: `cue_count_in`, `cue_count_out`, `cue_count_mismatch`,
  `empty_cues`, `average_duration`, `max_duration`, `average_cps`, `max_cps`,
  `quality_warnings`, `quality_errors`
- **Reference quality** (only when `reference_translation` is provided and
  length matches): `exact_match_rate`, `exact_matches`, `avg_length_ratio`

Results are written to a JSON file that can be diffed between runs.

## Adding your own test media

Large media files are **not** committed to the repo by default. To add a case:

1. Create `benchmark/media/` and drop a short clip there (an MP4 or audio file).
2. Add a case entry in `benchmark/cases.json` pointing at it.
3. Optionally add a reference SRT/JSON for quality metrics.

## Deciding on model changes

Per the implementation plan, a new default translation model may only replace
Hy-MT2 if benchmark evidence proves it is **more accurate AND faster/equal** at
equal-or-lower resource usage. Use this harness to gather that evidence before
making any model-swap decision.
