<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as a proposed transcript replay and translation user-interface specification.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current transcript and UI code, `docs/ARCHITECTURE.md`, `docs/ASR_PIPELINE.md`, and applicable presentation behaviour.
> - **Principal caution:** The specification is not evidence that transcript replay or translation behaviour exists as described. Do not rely on its UI states, data assumptions, or workflows without current-code verification.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Transcript Replay + Translation UI Spec

## Purpose

Turn the transcript into a study timeline for beginner learners:

- replay any line quickly
- replay short segments for shadowing
- reveal translation on demand
- keep Chinese as primary text

This spec is UI-first and designed to fit current MandarinOS architecture with minimal backend changes.

---

## Goals

- Add per-line replay controls in transcript
- Add translation reveal controls (line-level and display mode)
- Add segment replay with simple queue behavior
- Preserve existing conversation flow and option selection UI

## Non-goals (This Phase)

- No full translation service for arbitrary free text
- No persona-specific replay voice behavior
- No architecture rewrite of conversation engine

---

## User Stories

- As a learner, I can replay any transcript line.
- As a learner, I can show/hide English translation when needed.
- As a learner, I can replay a selected span of lines.
- As a learner, I can keep the transcript mostly Chinese and only reveal help on demand.

---

## Information Architecture

### Existing

- Transcript panel: "Record of what was said"
- Active conversation panel

### New

1. Transcript toolbar
2. Per-line action rail
3. Optional line detail row (EN/Pinyin)
4. Replay status strip (active line + stop)

---

## UI Components

### 1) Transcript Toolbar

Location: top of transcript panel.

Controls:

- Display mode:
  - `ZH` (default)
  - `ZH+EN`
  - `ZH + hover EN` (optional, phase 2)
- Replay speed:
  - `0.8x`, `1.0x` (default), `1.2x`
- Segment mode:
  - `Off` / `On`
- `Replay selected` (enabled only when 2+ lines selected)
- `Stop` (visible during replay)

Proposed IDs:

- `#transcriptDisplayMode`
- `#transcriptReplaySpeed`
- `#segmentModeToggle`
- `#replaySelectedBtn`
- `#stopReplayBtn`

### 2) Transcript Line Row

Each row contains:

- role marker (`APP` / `You`)
- Chinese text (always visible)
- action buttons:
  - `🔊` replay line
  - `EN` translation toggle
  - `PY` pinyin toggle (partner lines first)
  - selection checkbox (shown in segment mode)

Suggested attributes:

- `data-line-id`
- `data-role`
- `data-replayable`
- `data-has-translation`

### 3) Line Detail Row

Rendered under each line on demand:

- English translation
- pinyin

Suggested classes:

- `.transcript-line-detail`
- `.transcript-line-en`
- `.transcript-line-py`

---

## Client Data Contract

Current transcript entry is `{ role, text }`.

Proposed entry:

```ts
type TranscriptEntry = {
  id: string;
  role: "partner" | "user";
  text_zh: string;
  text_en?: string;
  pinyin?: string;
  frame_id?: string;
  turn_uid?: string;
  replayable: boolean;
  created_at: string;
};
```

UI state additions:

- `displayMode: "zh" | "zh_en" | "zh_hover_en"`
- `segmentMode: boolean`
- `selectedLineIds: string[]`
- `lineUiState: Record<string, { showEn: boolean; showPy: boolean }>`
- `replayState: { active: boolean; queue: string[]; activeId?: string; speed: number }`

---

## Replay Behavior

### Single-line replay

- Trigger: line `🔊`
- Action: play `text_zh` via existing `ttsSpeak`
- UI:
  - highlight active row
  - disable current replay button while active
  - stop available globally

### Segment replay

- Trigger: `Replay selected`
- Order: transcript chronological
- Gap between lines: 250-500ms
- Speed: toolbar value
- End: clear active highlight, keep selection

### Interrupt rules

- New replay request stops current replay queue.
- `Stop` halts current playback and clears queue.

---

## Translation Behavior

### Source priority

Partner lines:

1. `frame_text_en` captured in turn response
2. frame-level static mapping (if available)
3. empty fallback ("No translation available yet")

User lines:

- MVP: no auto translation
- future: optional on-demand translation

### Display rules

- `ZH`: translation hidden unless line `EN` toggled
- `ZH+EN`: show translation when available
- `ZH + hover EN`: show preview on hover/tap (phase 2)

---

## Integration Plan

### `ui/app.js`

- Extend transcript entry creation to store `text_zh`, `text_en`, `pinyin`, `frame_id`
- Add toolbar state + handlers
- Replace transcript renderer with row actions + detail rows
- Add replay queue helper using existing `ttsSpeak`

### `ui/index.html`

- Add transcript toolbar controls
- Add replay status strip placeholders

### `styles.css` / inline styles

- Add line action rail styles
- Add active replay highlight styles
- Add detail row styles

---

## Accessibility & UX Rules

- All controls keyboard-focusable
- Buttons include `aria-label`
- Minimum tap size >= 32px
- Chinese remains primary visual hierarchy
- Replay highlight and optional auto-scroll during playback

---

## Phased Implementation

### Phase A (MVP)

- Per-line `🔊` + `EN`
- Display mode `ZH` / `ZH+EN`
- Store and render `frame_text_en` for partner lines
- Single-line replay + active highlight

### Phase B

- Segment mode + multi-select
- Replay selected queue
- Stop button + replay queue state
- Pinyin toggle for partner lines

### Phase C

- Optional user-line translation on demand
- Save/bookmark lines to review list

---

## Acceptance Criteria (MVP)

1. Any transcript line can be replayed with one tap.
2. English translation can be toggled per line.
3. Partner transcript lines display `frame_text_en` when available.
4. Display mode switch works (`ZH` and `ZH+EN`).
5. No regression in conversation flow, options, or turn progression.

---

## Open Decisions

- Persist display mode/speed across sessions?
- Translate user lines in MVP or defer?
- Segment replay default: include both APP and You, or APP only?
- Auto-scroll behavior during replay: always vs only when out-of-view?

---

## Notes

- Keep this file updated as implementation decisions change.
- If scope grows, split into:
  - `..._MVP_SPEC.md`
  - `..._PHASE2_SPEC.md`
