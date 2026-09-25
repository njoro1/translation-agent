# UI Validation — Appendix A probes

`IMPLEMENTATION_PLAN.md` §8 deferred all of Phase 5 to empirical validation: every
claim about the Review and Quality screens was marked `[inferred]`, and the plan
asked for three populated-state probes before any density tuning.

The probes are **executable**, not narrative. `tests/test_ui_validation.py` builds
synthetic results with deliberately awkward shapes and asserts the screen's data
layer against them, so every figure in this document can be re-derived rather than
trusted. This file records the *interpretation*: what the numbers mean, which plan
bullets survived contact with the data, and which did not.

---

## How to re-run

```bash
BT="C:/Users/Njoro/AppData/Local/Temp/ta_$(date +%s)"; mkdir -p "$BT"
"C:/Users/Njoro/AppData/Local/Programs/Python/Python312/python.exe" \
    -m pytest tests/test_ui_validation.py --basetemp="$BT" -q -p no:randomly
```

The `--basetemp` must be **fresh and pre-created**. Reusing one makes pytest try
to delete the existing tree at exit; the sandbox's safe-delete shim refuses with
`OSError [Errno 53] The network path was not found` and pytest reports a bogus
`error` on whichever test happened to be setting up. A Git-Bash path
(`/c/Users/...`) breaks `tmp_path` fixtures instead.

Expected: `24 passed`.

---

## Method

**Synthetic, not recorded.** A recorded result only exercises the shapes it
happens to contain. The point of these probes is to force the shapes a clean
sample never has: a `failed` row, a two-line cue, a leaked ASR tag, a heavily
skewed duration distribution.

**The fixtures are shaped so the planted issues are the only issues.** An early
version gave every cue 1.8 s; at that duration every cue also tripped the CPS
*error* threshold (22 cps), so the probe measured a CPS histogram instead of the
three shapes it was built for. Probe 1 now uses 3.0 s cues and text under 80
characters.

**`_load()` mirrors the finished-run path.** It calls `cue_model.load`,
`subtitle_quality.build_report`, then the same `_quality_summary` →
`load_from_report` → `_sync_cue_tags` sequence that
`AppBridge._load_result_json` runs. A probe that bypassed those would validate
nothing.

---

## Probe 1 — Review, 60 cues

| Cue | Shape | Planted to produce |
|---|---|---|
| 8 | blank translation | `empty_text` → a `failed` row |
| 20 | `First line…\NSecond line…` | a two-line cue in the stored form |
| 34 | `<\|BGM\|> Translation with a leaked ASR tag.` | `asr_tag_leakage_error` |
| all others | 3.0 s, < 80 chars | nothing |

Observed:

| Quantity | Value |
|---|---|
| `cueCounts` | `{total: 60, ok: 58, warnings: 1, failed: 1}` |
| Issue rows | `{all: 2, errors: 2, warnings: 0}` |
| Timeline bars | 60 |
| Drag 10–14 | 5 rows, label `cues 10–14` |
| Edit cue 8 → text | `failed` 1 → 0, tags → `[]` |

**The table holds up at 60 cues.** Rows, filtering, search across source *and*
translation, and the timeline drag-to-filter all behave; nothing degrades.

**Three corrections to the plan.**

1. **`[MUSIC]` is not a leak.** The plan's prose implied bracketed ASR
   annotations reach the output. They do not: `subtitle_quality` flags
   `<\|zh\|>`-style control tokens (`_ASR_TAG_RE`), `<ANGRY>`-style emotion tags
   (`_EMOTION_TAG_RE`), and `[CHENGYU:…]` / `[TRANSLATOR…]` fansub markup
   (`_FANSUB_MARKUP_RE`). A `[MUSIC]` prefix is a *source*-side annotation
   convention and is deliberately not flagged. No code change — the fixture now
   leaks a real tag.

2. **The read view must expand the ASS separator.** The store keeps a literal
   `\N` (`src/postprocess.py::break_lines`), and only the writers normalise it —
   the SRT writer converts it to a real newline, the ASS writer converts a real
   newline back to `\N`. The result JSON keeps whichever form the pipeline
   produced. Nothing in QML handled it, so a wrapped cue rendered
   `first line\Nsecond line` as one visible line. The plan's bullet ("wrap in-cell
   with ellipsis + tooltip") did not mention this; it is the difference between
   the bullet working and not. Fixed with a display-only helper
   (`CuePreviewTable.displayText`); the edit field still receives the raw text so
   an edit round-trips unchanged.

3. **`Text` vs `TextInput` was the real defect, not ellipsis.** A `TextInput` is
   single-line by construction, so a two-line translation clipped silently — no
   ellipsis, no tooltip, just a missing half. The plan diagnosed this as an
   elision-policy problem.

---

## Probe 2 — Quality, 50 cues

45 cues at 0.6 s and 5 at 9.0 s, with one leaked tag, one blank cue, one
over-long line. Observed:

| Quantity | Value |
|---|---|
| `cueCounts` | `{total: 50, ok: 0, warnings: 49, failed: 1}` |
| `qualityErrors` (cue-level) | 50 |
| Issue rows (row-level) | `{all: 141, errors: 51, warnings: 90}` |
| Errors tile breakdown | cps 44 · too-long 5 · chars 1 · empty 1 |
| Duration axis | `0.4 … 6.8+`, 2 occupied buckets, mass in bucket 0 |
| Duration summary | `avg 1.4 s · max 9.0 s` |

**Finding 1 — the "Errors" tile and the "Errors" filter chip disagreed.** The tile
read `qualityErrors` (50 **cues**), while the chip and the table below it counted
issue **rows** (51). One cue carried two errors — a blank cue is both `empty_text`
and `cps_error` — which is exactly the "two widgets, one concept, different
values" defect class the review opened with. Fixed: the two tiles that sit on top
of the issue table now count rows, and `qualityErrors` keeps its cue-level meaning
for the icon-rail badge and the Review page, which count cues. A tripwire test
pins both units so a later refactor cannot "unify" them into the wrong one.

**Finding 2 — the duration axis had a wrong label.** The last bucket is a clamped
overflow bucket, and it was labelled with its centre. A 9.0 s cue therefore sat
under an axis tick reading `6.8`. Fixed: the final tick is marked open-ended
(`6.8+`, `38+`). The real maximum is stated by the summary line, which is the
honest place for it — one bucket cannot distinguish 7.2 s from 30 s.

**Decision — no log axis.** The plan said "consider a log axis if durations skew
heavily (decide from Appendix A probe 2)". They do skew: 45 of 50 cues are short
and 5 are 9.0 s. But the tail is *already visible* on a linear axis — two occupied
buckets, with the overflow bucket at 11 % of the peak — and a log axis would
compress the 45-cue mass into one bar to make a 5-cue tail legible. Wrong trade.
Linear axis kept.

**Confirmed as specified.** Severity sort toggles between errors-first and
cue-order while keeping every row; bar tones come from the real `CPS_WARNING` /
`CPS_ERROR` constants the legend names; `runContext` fills from the run
(`Mode, Model, Preset, Context, Batch, Translation memory, Windows, Retries, Wall
clock`) instead of the old `No run loaded`.

---

## Probe 6 — YouTube Inspect

| Assertion | Result |
|---|---|
| Before an inspect | `youtubeHasEnglishSubtitle` is `False` |
| Download action | gated on the flag *and* on `youtubeSubDownloading` |
| No-English-track branch | present, with an explanation and the fallback path |
| Readiness row | `status: youtubeHasEnglishSubtitle ? "ok" : "todo"` |

The honest pre-inspect state is "not found", not "ok" — otherwise the panel
claims a track it has not looked for yet.

**Limitation, stated plainly:** these are source-level assertions over
`YouTubeSubtitlePanel.qml` and `RunPage.qml`. There is no offline YouTube fixture
in the suite, so this probe proves the *branches exist and are gated on the single
store*, not that the panel renders correctly against a live inspect. That half
still needs a manual pass with a network-connected run.

---

## Probe 5 — Appearance

Every appearance axis has a path from the store into `Theme`: `themeName`,
`comfortable`, `reducedMotion` and `accentName` are all bound in `Main.qml`, and
`Theme.accentChoices` holds exactly five presets. `test_main_pushes_every_appearance_axis_into_theme`
pins that wiring, because an axis with no binding is a switch that changes nothing.

The colour maths lives in `tests/test_theme_contrast.py`, which parses the token table out
of `Theme.qml` rather than duplicating it, so editing a hex past the threshold fails the
build. Measured 2026-09-25 (WCAG 2.1, AA = 4.5:1 for text):

| Pair | Dark | Light |
|---|---|---|
| `textMuted` on its **worst** surface (`surfaceRaised` / `background`) | 4.78 on `surfaceRaised` | 4.85 on `surfaceRaised` |
| `text` / `textDim`, worst surface | 13.44 / 7.29 | 15.71 / 6.47 |
| Status colours as text, worst surface (`surfaceRaised`) | 5.38 (`error`) | 4.61 (`error`) |
| `accentInk` on the five accent swatches, worst | 5.24 (`iris`) | 5.41 (`azure`, `rose`) |

**The light theme was the finding, and it was not the pair the plan named.** The plan
pointed at `textMuted` on the dark background; the real miss was light status colours on
`surfaceRaised`. `Chip` paints a toned chip's text on `surfaceRaised`, which in light theme
is the lightest surface in the ramp — and `test_status_colours_clear_aa_as_text` swept only
`background` / `surface` / `surfaceAlt`. Every light status colour therefore sat at
**4.22–4.30:1** on a toned chip, just under AA, with the test green.

Fixed by darkening the four light status colours by ~4 % and moving the `azure` / `mint` /
`amber` / `rose` accent swatches with them, so the palette does not fork (the accent table
and the status tokens are deliberately the same hues in light theme). The test now sweeps
all five surfaces.

Two smaller results from the same sweep, both already in place before this pass: `accentInk`
is `isDark ? "#0A0C11" : "#FFFFFF"` rather than a fixed white — white ink on the dark-theme
pastels is 1.88:1 on mint — and `borderSoft` was lifted because it was effectively invisible
(1.13:1 dark).

Density and motion are covered by `tests/test_ui_hygiene.py`, not here:
`test_density_reaches_spacing_type_and_control_height` (the spacing scale, the type scale and
the control heights all move together — the first version grew only the type, so
"Comfortable" read as *tighter* than Compact), `test_reduced_motion_reaches_every_animated_component`
(13 animating components), and `test_every_behavior_collapses_under_reduced_motion`
(no `Behavior on …` may omit the toggle).

**Limitation, stated plainly:** these are computed ratios and source-level wiring checks.
No screenshot is compared against a reference, so a colour that passes AA but is applied to
the wrong element would not be caught here.

---

## Findings that need a decision (not changed here)

**1. The line-count checks are inert, and fixing them alone would be worse.**
`subtitle_quality._line_count` splits on real newlines, but the pipeline stores a
literal `\N`, so every wrapped cue reports one line and `lines_warning` /
`lines_error` never fire on real output. The obvious fix — teach it to see the
separator — would flood the report: `LINES_WARNING` is `2` and the check is
`lines >= LINES_WARNING`, while `break_lines` deliberately produces exactly two
lines. The two are coupled, and "what counts as too many lines" is a product
decision, not a probe finding. Left alone; pinned by a test so the coupling is not
discovered again by accident.

**2. The cue inspector's edit field shows the raw `\N`.** Same root cause as
probe 1 finding 2. The read view now expands the separator; the inspector's
`TextArea` still shows it. Deliberately untouched: the inspector writes back what
it holds, and its dirty check is `text !== root.cue.text`, so displaying a
converted string would mark every untouched row as edited. Fixing it properly
means normalising the store, not the view.

**3. Quality thresholds have no preset system.** The plan asked for "show the
active preset name" and "editing any value marks the preset `custom`".
`AppBridge.qualityThresholds` reads module constants out of
`src/subtitle_quality.py`; there is no preset to name and no editor to mark
anything custom. The card's note was corrected to say what is actually true
("built-in defaults") rather than implementing a preset system that does not
exist.

---

## Plan bullets that were already satisfied

Recorded so the same work is not done twice. Each was verified against the tree,
not against the review's screenshot:

| Plan claim | Reality |
|---|---|
| `Rolling scene summary` label truncated | It lives in a `Flow` and wraps |
| Cue-budget row truncated | Same `Flow` |
| `Only problems` label truncated | It is an `AppSwitch` with a non-elided label |
| Quality thresholds derive from a preset | They read `src/subtitle_quality` constants |
| Multi-line translations need ellipsis | They needed a wrapping `Text`, not ellipsis |

---

## What changed as a result of the probes

| Change | File |
|---|---|
| Errors / Warnings tiles count issue rows, matching the table and its chips | `backend/bridge.py` (`qualityTiles`) |
| Final histogram tick marked open-ended | `backend/bridge.py` (`_distributions`) |
| Read view expands the ASS separator | `ui/qml/components/CuePreviewTable.qml` (`displayText`) |
| Light status colours darkened ~4 %; `azure`/`mint`/`amber`/`rose` swatches moved with them | `ui/qml/Theme.qml` (probe 5) |
| Status contrast swept over all five surfaces, not three | `tests/test_theme_contrast.py` (probe 5) |
| All of the above, plus the unit tripwire, as executable evidence | `tests/test_ui_validation.py`, `tests/test_theme_contrast.py` |

No change was made to any Phase 0–4 behaviour: the plan's rule was that a probe
contradicting the spec changes **only the listed Phase 5 bullet**, and none of
these findings reach outside Phase 5. The two probe-5 changes are the exception the
rule allows: T-6.4 is itself the appearance pass, so its findings land inside it.
