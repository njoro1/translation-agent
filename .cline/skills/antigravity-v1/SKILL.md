---
name: antigravity-v1
description: >
  Structured, low-token coding sessions for single-file tasks and focused
  bug fixes. Enforces no-preamble output, chunk-only edits, and a three-mode
  classifier (investigate / fast-path / plan). Use for any coding task in
  one or two files. Triggers on: "antigravity", "fast path", "efficient mode",
  "stop overthinking", or when responses are too verbose and wasted tokens
  are a concern.
---

# Antigravity Protocol v1 — Cline TUI

Structured modes, exact edits, zero chattiness.

---

## Core Directives

**No preamble.** Never open with "I understand…" or "Sure!". Output the action directly.

**No post-action summaries.** Do not narrate what you just did unless asked.

**Stop on ambiguity.** Ask ONE specific question. Do not write exploratory code to guess the intent.

**Chunk edits only.** Use `replace_in_file` with the smallest SEARCH/REPLACE blocks that make the change correct. Never rewrite an entire file.

**No redundant reads.** Do not re-read a file you just wrote to confirm the change.

---

## Mode Classifier — Run This First on Every Request

Silently classify the request into A, B, or C before doing anything.

---

### Mode A — Investigatory (read only, no edits)

**Triggers:** "How does X work?", "Where is Y defined?", "What calls Z?"

1. Run `search_files` or `list_code_definition_names` silently.
2. Output the direct answer in one short paragraph.
3. Stop. No plan, no proposed changes.

---

### Mode B — Fast Path (single targeted change)

**Triggers:** Single-file or single-function changes. "Fix this", "Change X to Y", "Add this field".

1. `search_files` → locate exact position.
2. `replace_in_file` → one minimal SEARCH/REPLACE block.
3. Output: `Done.` Nothing else.

---

### Mode C — Strict Planning (multi-file or architectural)

**Triggers:** Any task touching ≥2 files, new features, refactors, anything needing decisions.

**Step 1 — Silent research (zero edits):**
Use `read_file`, `search_files`, `list_code_definition_names` only. Touch nothing.

**Step 2 — Switch to Plan mode (Tab in TUI). Write `implementation_plan.md`:**

```
## Goal
<one sentence>

## Files
- [NEW]    path/to/file  — purpose
- [MODIFY] path/to/file  — what changes
- [DELETE] path/to/file  — why safe

## Steps
1. ...
2. ...
```

Output only: `Plan written to implementation_plan.md. Awaiting approval.` then stop.

**Step 3 — Wait for user approval before touching any file.**

**Step 4 — Switch to Act mode (Tab in TUI). Execute:**
Write `task.md` with checkboxes. Work through each step using `replace_in_file`
(edits) or `write_to_file` (new files). Tick each box as you go. Do not deviate
from the approved plan without asking first.

---

## Tool Priority Order

| Priority | Tool | Use for |
|---|---|---|
| 1st | `search_files` | Finding patterns, locating code |
| 1st | `list_code_definition_names` | Structural map without reading full files |
| 2nd | `read_file` | Reading only the exact file needed |
| 3rd | `replace_in_file` | All edits — minimal blocks |
| 4th | `write_to_file` | New files only |
| Last | `execute_command` | Tests, package installs, server starts — nothing else |

Never use `execute_command` with `cat`, `grep`, `find`, or `ls` for exploration.
Use the native Cline tools above — they cost fewer tokens and give cleaner output.

---

## Context Management

**At ~60% context:** type `/smol` — compresses history in place.

**At phase boundary or ~75%+ context:** type `/newtask` — clean handoff with
plan, decisions, changed files, and next steps carried forward.

**Use `@filename` in your prompt** to load only the files this turn needs
instead of letting Cline scan the whole project.
