# Redesign mockups — Translation Agent

Static HTML/CSS mockups for the ground-up UI redesign. **No application code was
changed** — this folder is a design proposal only.

Open `index.html` for the gallery, or any file in `screens/` directly.

```
mockups/
├── index.html                 ← start here: gallery
├── design-system.html         ← tokens, type, components
├── README.md
├── assets/
│   ├── mock.css               ← the design system (dark + light)
│   ├── icons.js               ← inline SVG icon sprite
│   └── app.js                 ← theme toggle + demo interactions
└── screens/
    ├── 01-run-youtube.html    Run, YouTube Cloud, idle
    ├── 02-run-offline.html    Run, Offline/local, model missing
    ├── 03-running.html        Run, in progress (62%)
    ├── 04-review.html         Review, master–detail cue inspector
    ├── 05-quality.html        Quality report dashboard
    ├── 06-settings.html       Settings as a full page
    ├── 07-log.html            Console + run history
    ├── 08-palette.html        Command palette (Ctrl K)
    └── 09-empty.html          First run / empty state
```

## Viewing

Every screen is a standalone HTML file on a 1440 × 900 desktop canvas. Double-click
`index.html`. The theme button in each top bar toggles dark/light; the choice is
remembered across screens.

## Shell

| Zone | Height | Job |
|---|---|---|
| Command bar | 56 px | Mode, preset, language, **live progress**, the single primary action |
| Icon rail | 64 px | Run · Review · Quality · Log · Settings, with an issue badge |
| Workspace | flexible | Source → Pipeline → Inspector, full height, no dead space |
| Status bar | 30 px | One-line log ticker + the shortcuts that matter |

## Design tokens

Dark is the default. Both themes come from one token set, so a QML implementation maps
1:1 onto `Theme.qml`.

| Token | Dark | Light | Notes |
|---|---|---|---|
| `background` | `#0A0C11` | `#F5F6FA` | App canvas, with a soft accent glow |
| `surface` | `#12161E` | `#FFFFFF` | Cards |
| `surfaceAlt` | `#161B25` | `#F3F5FA` | Secondary fills, table headers |
| `surfaceRaised` | `#1C2230` | `#E9EDF6` | Hover, chips, selected segments |
| `inset` | `#0C0F15` | `#F1F3F9` | Text fields and console |
| `border` | `#242B3A` | `#DCE1EC` | Hairlines |
| `text` | `#E9ECF3` | `#11141B` | |
| `textMuted` | `#6E7891` | `#7C8698` | |
| `accent` | `#7C5CFF` | `#5B3DF5` | Iris — primary actions, selection |
| `success` | `#3DD68C` | `#12945C` | |
| `warning` | `#F5A623` | `#B26A00` | |
| `error` | `#FF5F6D` | `#D0303F` | |
| `info` | `#4EA8FF` | `#1F6FD0` | |

Type: 10.5 / 11.5 / 12.5 / 13 / 15 / 19 / 22 px. Space: 4 px base. Radii: 6 / 8 / 10 /
12 / 16. Control height 34 px (28 px for small). Mono for every timecode, path, cue
index and log line.

## Constraints the screens respect

- **No empty real estate** — columns stretch to the window; a scroll region fades at
  its clipped edge rather than cutting a row in half.
- **Status is never colour alone** — icon + word + colour (WCAG 1.4.1).
- **One primary action per screen** — exactly one accent-filled button is visible.
- **Keyboard complete** — Ctrl 1–5 navigate, Ctrl Enter runs, Ctrl . cancels, Ctrl K
  palette, Ctrl L log.

## Product invariants preserved

From `AGENT_DOCUMENTATION.md`:

- Exactly three pipeline modes — YouTube Cloud, Local Cloud, Offline. No cloud rescue.
- Offline mode is visibly credential-free ("nothing leaves this machine").
- Target language is fixed to English, shown as a locked field rather than a control.
- Cue count in == cue count out — the Review screen edits text, and timing edits are
  explicit nudge controls, not silent retiming.
- Strict quality gate semantics: errors fail, warnings never do.

## Suggested build order

1. Port the tokens into `Theme.qml` (add `surfaceRaised`, `inset`, focus ring, tints).
2. Build the shell (command bar, rail, status bar) and drop the existing Run content
   into it unchanged.
3. Move `AdvancedDrawer` contents into the new Settings page — the biggest single win.
4. Rebuild Review (master–detail + timeline), then Quality (score ring, distributions,
   issue → cue links).
5. Polish: command palette, run history, first-run onboarding, light theme, reduced
   motion audit.

## Notes

- `color-mix()` and `backdrop-filter` are used for the translucent bars; any current
  Chromium, Edge or Firefox renders them. Fallbacks degrade to a solid surface.
- The iframes in `index.html` are previews at 45 % scale; the files in `screens/` are
  the real thing.
- Screens are static. Interactions that are only demonstrated: theme toggle, segmented
  controls, filter chips, cue row selection, switches.
