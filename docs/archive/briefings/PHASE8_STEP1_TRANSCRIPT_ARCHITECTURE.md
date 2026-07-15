# Phase 8 Step 1 — Conversation transcript (architecture)

**Role: Architect.** Minimal safe design for one implementation step. Programmer implements after this.

---

## Goal

Visible transcript panel; append Partner and You turns; one simple acknowledgement + reciprocity path after the user answers. UI only; runtime and builder untouched.

---

## Data

- **Source of truth:** existing `conversationTranscript` array in `ui/app.js`.
- **Entry shape:** `{ role: 'partner' | 'user', text: string }` (already used for `user`; add `partner`).

---

## Flow (one path)

1. **Run Turn** → frame sentence is shown. **Append** one partner turn: `{ role: 'partner', text: frameSentenceText }`. Render transcript.
2. **User selects option** → already append `{ role: 'user', text: chosenText }`. **Then append** two partner turns: acknowledgement (e.g. one fixed line), then reciprocity (`你呢？`). Render transcript.
3. **Turn markers:** each line in the panel shows a label ("Partner:" / "You:") then the text.

---

## UI placement

- **Transcript panel:** in the left column, between controls/frame area and the Trace section (or above Trace). Section heading "Conversation", scrollable list of lines with turn markers. No new right-column area.

---

## Out of scope this step

- Clearing transcript on new session; multiple Run Turns (transcript accumulates).
- Variable acknowledgement text; engine-driven partner lines.
- Builder or runtime changes.

---

*Implement: transcript panel (HTML + CSS) + `renderTranscript()` + append partner turn in runTurn + append user then acknowledgement + reciprocity on option select. Then stop for review.*
