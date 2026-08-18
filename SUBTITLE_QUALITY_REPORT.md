# Subtitle Quality Report — Fully Offline Local Runs

**Date of analysis:** 2026-08-11
**Executable:** latest build in `dist\` (Fully Offline / `local_offline` mode)
**Files analyzed:**

| File | Cues | Source lang | Notes |
|---|---|---|---|
| `dist\50元 vs 10000元化妆师：同一张脸，差距能有多离谱？.srt` | 217 | zh | Primary subject of this report |
| `dist\当我把生活变成了开放世界 RPG…….srt` | 39 | zh | Short run; appears truncated |
| `dist\sample outputs\50元 ... (2).srt` | 260 | zh | Earlier offline run (100% untranslated) — historical baseline |

---

## 1. How the system works

### 1.1 The three routes

The desktop app exposes exactly three user-facing pipelines, selected by a radio group in the **Dashboard → Pipeline Mode** card. Each maps onto a `(source, backend, cloud-rescue)` triple in `backend/bridge.py` (`AppBridge._apply_pipeline_mode`):

| Route | `pipeline_mode` | Source | Translation backend | Cloud rescue |
|---|---|---|---|---|
| **YouTube → Cloud** | `youtube` | Existing YouTube subtitles (yt-dlp → youtube-transcript-api) | Cloud OpenAI-compatible API (`OPENAI_BASE_URL` / key) | Disabled |
| **Local file → Local + AI fallback** | `local_hybrid` | Local media → local ASR | Local llama.cpp (Hy-MT2) | **Enabled** (retry failed cues via cloud) |
| **Local file → Local only (offline)** | `local_offline` | Local media → local ASR | Local llama.cpp (Hy-MT2) | **Disabled** |

The **Fully Offline** route is the one exercised in every run analyzed here. It is designed to touch no network: no YouTube, no cloud LLM, no API key.

### 1.2 The offline pipeline step by step

```
Local media file
  → ffmpeg audio extraction
  → FunASR VAD (fsmn-vad.gguf) segmentation
  → SenseVoiceSmall (sensevoice-small-q8.gguf) CPU transcription
  → long text split into short, proportionally-timed cues
  → bundled llama-server auto-started against Hy-MT2-1.8B-Q8_0.gguf
      (127.0.0.1:8080, auto port discovery if busy)
  → Hy-MT2 batch translation (numbered-item protocol)
  → translation-memory cache (SQLite)
  → SRT output (timestamps preserved)
```
**ASR.** `src/local_asr.py::transcribe_local_file` shells out to the bundled FunASR binaries. A VAD pass segments speech, each segment is transcribed by SenseVoiceSmall on CPU, and the resulting text is split into short cues whose timing is derived proportionally from the segmentation. Source language is auto-detected (`--asr-lang auto` → detected `zh`). The log for these runs confirms `[asr] Stripping ASR tags` and `[asr] Using CJK max cue chars: 48`.

**Local translation server.** `src/local_server.py` auto-launches the bundled CPU-only `llama-server` against the user-specified GGUF (`Hy-MT2-1.8B-Q8_0.gguf`). It validates the server before reuse (queries `/v1/models`), finds a free port if 8080 is occupied, then points the OpenAI client at the discovered URL. Translation therefore never depends on a separately-started server and never touches the network.

**Translation.** `src/translate.py` batches cues as numbered items (`1. text` …) and expects the model to return `1. translation` … on matching lines, preserving cue count and order. Because the local model is Hy-MT2, it uses the hy-mt2-translator skill prompt (a single Chinese user message, **no system prompt**), `temperature 0.1`, `top_p 0.6`, `top_k 20`, `repeat_penalty 1.05`. Dynamic batching caps the batch at **≤ 12 cues / ≤ 700 CJK chars** (smaller than the cloud path's 40). A robust fallback ladder applies: `batch → retry → split-in-half → per-item`.

**Fallback behavior — the crux.** When a batch cannot be aligned, it is split and retried; ultimately each cue is translated individually via `_translate_one`. If that call throws, or the model returns empty content, the code **keeps the original source text as the "translation"**:

```python
# _per_item_translate
except Exception as exc:
    ...
    result = text          # <-- leaves the cue UNTRANSLATED (keeps Chinese)
```

Similarly, `_translate_one` returns `(content or text)` — an empty model reply silently becomes the source line.

**Translation memory.** `src/translation_memory.py` caches `(source_language, model_profile, glossary_hash, source_text) → translated_text` in `cache\translation_memory.sqlite3`. The log shows `[tm] 67 cache hits, 150 to translate`. Critically, **any non-empty returned string is stored**, including the source-text fallback described above (see §2.4).

**Cloud rescue (hybrid only).** In `local_hybrid`, failed cues are re-translated by a cloud client. In `local_offline` there is **no rescue handler**, so any cue that fails the local path is written out as-is (untranslated). This is why offline runs are the most exposed to the fallback-to-source behavior.
---

## 2. Analysis of the produced subtitles

### Summary of findings

| # | Issue | Severity | Evidence |
|---|---|---|---|
| 1 | **31% of cues left untranslated (Chinese)** | **Critical** | 68/217 cues in the 50元 file |
| 2 | Untranslated cues cluster in long runs, worsening in the 2nd half | **High** | Cues 153–168, 186–194, 209–217 untranslated |
| 3 | Mixed/code-switched single lines (Chinese/Korean inside English) | High | "Super加倍 …", "그제 다시 배우的 그어데." |
| 4 | Truncated / incomplete translations | High | "one A.", "The eyelashes just make...", "The." |
| 5 | Nonsense / hallucinated / wrong-register translations | Medium | "VEBO era", "Little girl, the milk tea…", "divining fortunes" |
| 6 | Inconsistent pronoun/gender for an object ("it" vs "he/him") | Medium | "His AI mode", "Let him act", "he will serve…" |
| 7 | Earlier offline run was **100% untranslated** | High (context) | 260/260 Chinese in `(2).srt` |
| 8 | Possible truncated/incomplete run (RPG file) | Medium | ends at 2:15 with "The." + 20 s gap |
| 9 | Timestamps preserved (no overlaps) | ✔ (good) | 0 overlaps; minor gaps only |

---

### 2.1 Critical — 31% of cues are left in the original language

In the 50元 file, **68 of 217 cues (31%)** are untranslated Chinese mixed into otherwise-English subtitles. Examples:

- Cue 1–2: `你一定也化过妆` / `谁在小时候没有在眉心上点过一点红呢`
- Cue 9: `这能值吗？`
- Cue 20: `店里也更加人声鼎沸`
- Cue 23: `就当是假装登上百大舞台了吧`
- Cue 28–29: `但这位名叫白雪的化妆师主动给我准备了一` / `个新的`
- Cue 34–43 (10 in a row): `就像是在给脸做泰式按摩` … `我看这边真的一早就好多人了`

This is the single most serious defect: the deliverable is a bilingual mix, not an English subtitle track. A viewer gets whole sentences in Chinese with no translation.

> **Mechanism.** When a local translation attempt fails (empty model output, misaligned numbered reply, or an exception), the fallback ladder eventually returns the **original source text** (§1.2). Offline mode has no cloud rescue to recover these, so the untranslated cue is written verbatim.

### 2.2 High — failures cluster and worsen toward the end of the file

The untranslated cues are **not** uniformly scattered; they form contiguous runs, concentrated in the second half:

```
CJK  1 - 2        (untranslated)
EN   3 - 8
CJK  9
EN   10 - 19
CJK  20
EN   21 - 22
CJK  23 - 24
EN   25 - 27
CJK  28 - 32      (5 in a row)
EN   33
CJK  34 - 43      (10 in a row)
EN   44 - 49
CJK  50 - 51
EN   52 - 67
CJK  68
EN   69 - 100
CJK  101
...
CJK  153 - 168    (16 in a row)
EN   169 - 185
CJK  186 - 194    (9 in a row)
EN   195 - 205
CJK  206
EN   207 - 208
CJK  209 - 217    (9 in a row — the closing summary)
```

The pattern (long blocks of failure, especially from cue ~153 onward) suggests the local CPU model is **degrading over the run** — e.g. slow inference leading to timeouts, or the batch response repeatedly failing to align — rather than one-off glitches. The closing narration (cues 209–217) is entirely untranslated.
### 2.3 High — code-switching and mixed-language corruption inside a single line

Some cues are not just untranslated — they are internally corrupted:

| Cue | Text | Problem |
|---|---|---|
| 50元 cue 50 | `Super加倍 highlighter-lined lashes are very popular.` | A Chinese word **加倍** ("double/amplify") is embedded in an English sentence. |
| 50元 cue 30 | `그제 다시 배우的 그어데.` | Korean Hangul + Chinese character mixed into gibberish. Likely a SenseVoice mis-transcription of a speech segment as (bad) Korean, or a model hallucination. |
| 50元 cue 51 | `很流行的超级立体小巧高亮鼻子` | Untranslated (styling term). |

These make individual cues unreadable and are a strong signal that either the **ASR mis-transcribed** a segment (SenseVoice is multilingual and can mis-detect language) or the **translation model hallucinated** a non-target-language string that the pipeline passed through unchanged.

### 2.4 High — truncated / incomplete translations

Several cues are unfinished fragments, indicating the model hit a token/stop limit or the response was cut:

- RPG cue 12: `Ultimately, it can automatically generate a simple vlog and one A.` — "one A." is cut off (likely "…an A.I./avatar/…").
- 50元 cue 55: `The eyelashes just make...` — sentence unfinished.
- RPG cue 30: `They in this` — fragment.
- RPG cue 26: `Translate either your wonderful or…` — this is **not** a translation at all; it looks like the model **echoed a fragment of the English instruction/prompt** ("Translate either your wonderful or…"). An instruction leak means the model, at least once, output part of its prompt instead of the source text.
- RPG cue 39 (last cue): `The.` — the file ends with a single word and a 20-second trailing gap, strongly suggesting the subtitle run did not complete (see §2.7).

### 2.5 Medium — nonsense, hallucinated, or wrong-register translations

Even where the model produced English, several lines are wrong or awkward enough to damage meaning:

- RPG cue 23: `…keeping a diary in the VEBO era.` — "VEBO" is an unexplained transliteration (the source likely referenced a specific app/period, e.g. 备忘录/微博-era); the translation gives no meaning.
- RPG cue 16: `Little girl, the milk tea is delicious, but don't overdo it.` — this is the AI **device's spoken reminder**, but the translation reads as awkward narrative; "Little girl" is an odd address.
- 50元 cue 60: `The girl group vibe, you can also accept it as a side business of Korean girl groups—divining fortunes.` — garbled meaning.
- 50元 cue 33: `Powerful strokes, classical secrets.` — likely a mistranslation of an idiom/onomatopoeia about the makeup process.

### 2.6 Medium — inconsistent pronoun/gender for a single object

In the RPG file the wearable device is referred to inconsistently:

- Cue 13: `His AI mode is different from your question-and-answer AI tool.`
- Cue 18: `Let him act according to the rules I specify.`
- Cue 25: `He will serve as a competent external brain…`
- …while elsewhere it is `It`/`its` (cues 5, 7, 9, 11, 12).

An object should not oscillate between "it" and "he/him"; this is a translation/register inconsistency that reads as sloppy.

### 2.7 Medium — possibly incomplete run (RPG file)

The RPG subtitle file has only **39 cues** and ends at **00:02:13 (135 s)** with a final cue `The.`, preceded by a **20.1-second gap** (cue 38 → 39). Combined with the truncated final line, this is consistent with the ASR/translation run **ending early** (the media's full duration is not covered), rather than a clean completion. This run should be treated as incomplete / low-confidence.

### 2.8 Good — timestamps are preserved

Across both files there are **zero overlapping cues**, and timestamps otherwise track the source segmentation (the project's "timestamps are sacred" invariant holds). The only notable timing items are a few gaps > 2 s (max 8.1 s in the 50元 file), which are plausible as natural pauses and are not defects per se.
---

## 3. Root-cause discussion

The defects trace to a few concrete mechanisms in the offline path:

1. **Fallback-to-source is silent and permanent.** `_per_item_translate`/`_translate_one` return the original text when a local call fails or returns empty. There is no per-cue retry with a different prompt, no "mark as failed" remediation, and (in offline mode) no rescue. Result: entire sentences shipped untranslated.

2. **Translation memory can cache the untranslated source as a "translation".** Because the fallback value is non-empty, `translation_memory.put(...)` stores the **Chinese source** as the cached result for that `source_text`. Any repeated line (and any future run) then returns the untranslated Chinese straight from cache — **compounding the problem across runs**. This is a genuine propagation bug.

3. **No offline recovery for failed cues.** The cloud-rescue handler is only wired for `local_hybrid`. `local_offline` has no second chance, so a single CPU-timeout or misalignment permanently loses that cue.

4. **ASR mis-transcription / model hallucination is passed through unvalidated.** Mixed-language and gibberish lines (e.g. the Korean+Chinese cue) are never caught. There is no sanity check that the output is in the target language / script.

5. **Batch alignment fragility on weak hardware.** The clustering of failures in the second half points to the small CPU model degrading under a long run (slow inference, timeouts, borderline context), which the fallback ladder converts into source-text passthrough rather than a clean translated result.

---

## 4. Recommendations

1. **Never emit untranslated source as a "successful" translation.** When a cue fails, mark it explicitly (e.g. leave it empty or tag it `[untranslated: <source>]`), log it, and count it — so the user can see exactly how many cues were not translated and which ones.
2. **Do not write source text into the translation memory.** Only store a cache entry when the output is non-empty and free of the source script. Treat source-script passthrough as a failure, not a cacheable result.
3. **Add an offline retry tactic.** Before giving up on a cue, retry with a degraded prompt (single-item, no numbered block) or a lower `max_tokens`; if it still fails, leave it flagged rather than silently untranslated.
4. **Validate output language/script.** Reject or flag responses that contain CJK/Hangul when translating to English, since these indicate ASR mis-transcription or model hallucination.
5. **Add a completion check for the run.** Compare the last cue's end time against the media duration and warn if the subtitle file looks truncated (as in the RPG file).
6. **Consider reducing the untranslated-cue rate at the source.** Stabilize the local model (more CPU threads, or smaller effective batches late in the run) and/or surface a per-run quality report so regressions are visible.
7. **For offline mode specifically,** surface a clear warning at the end of the run: *# cues left untranslated* — so a partially-broken output is never mistaken for a complete translation.

---

## 5. Bottom line

The Fully Offline route is architecturally sound — it launches the local server automatically, preserves timestamps, and never touches the network. But the current output quality is **not ready for production**: roughly a third of the 50元 video's cues remained untranslated Chinese, with additional truncated, mixed-language, and mis-registered English lines, and the RPG run appears incomplete. The dominant, addressable root cause is the **silent fallback-to-source combined with source-text caching in translation memory**, which converts model failures into permanent untranslated subtitles.