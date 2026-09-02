# ASR Preprocessing Benchmark — Methodology & Results

FFmpeg audio preprocessing profiles exist to maximize ASR input quality
**without damaging timing**. Duration safety is enforced in code
(`src/local_asr.py::_prepare_asr_audio`): any output whose duration drifts more
than **50 ms** from the source is rejected, falling back `profile → basic → none`,
with a logged warning. Timestamps are never allowed to shift silently.

## Profiles

| Profile | Filter chain | Intended for |
|---|---|---|
| `none` | *(mono/16 kHz extraction only)* | Baseline; already-clean speech |
| `basic` | `highpass=f=80` | Safe default: removes rumble/HVAC/music low end |
| `loudnorm` | `highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11:linear=true` | Quiet or uneven dialogue |
| `denoise` | `highpass=f=80,afftdn=nf=-25:tn=true,loudnorm=…` | Noisy/BGM-heavy sources (light denoise) |

All profiles always emit `-ac 1 -ar 16000 -c:a pcm_s16le`.

## Harness

```bash
python tools/benchmark_preprocess.py --media sample.mp4 --asr-lang ja \
    [--profiles none,basic,loudnorm,denoise] \
    [--out-dir bench_out] [--reference ref.srt] [--json bench.json]
```

Per profile it reports: cue count, average cue duration, total text length,
processing time, effective profile used after fallback, empty-cue count and,
with a reference SRT (`--reference`), CER/WER. Outputs are written separately
per profile so they can be inspected side by side.

### What "better" looks like

- CER/WER lower than `none` (when a reference transcript exists).
- Cue count / average duration stable vs `none` (segmentation not distorted).
- No empty cues introduced; processing time within budget.
- Effective profile equals requested profile (no silent fallback).

## Current defaults (until benchmarks say otherwise)

- `--asr-preprocess auto` resolves to **basic** for most content
  (`auto` preset) — a conservative, duration-safe choice.
- The named presets **drama**, **documentary**, **variety**, **lecture**
  request `loudnorm` by design (dialogue/narration benefit from loudness
  normalization); **anime** and **music** stay on `basic` because aggressive
  processing risks fricative/BGM artifacts.
- `denoise` is deliberately **not** a default anywhere: consumer-grade FFmpeg
  denoisers can damage fricatives, breaths, and high-frequency CJK consonant
  cues. Only adopt it as a preset default after benchmark + listening tests.

## Recording results

Run the harness against representative media per scenario and paste the summary
table below. Re-tune preset `asr_preprocess` values only with this evidence;
precedence rules (explicit flag > preset > env > default) must keep holding.

| Media | Profile | CER | WER | Cues | Avg cue ms | Notes |
|---|---|---:|---:|---:|---:|---|
| *(pending — run `tools/benchmark_preprocess.py` on real media)* | | | | | | |
