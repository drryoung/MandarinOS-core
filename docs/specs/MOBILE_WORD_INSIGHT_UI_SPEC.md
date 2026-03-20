# Mobile Word Insight UI Spec

## Purpose

Define a **touch-first** way to explore **pinyin, gloss, components, and etymology** when the learner taps words in the **active sentence**, **response option cards**, and (later) **transcript**—without relying on a permanent **right-hand card column** (often absent or cramped on phones).

This spec is **UI/UX only**; implementation may reuse existing token click + card/hint pipelines behind a shared “word insight” surface.

---

## Goals

- One consistent **word insight** interaction across surfaces: active sentence, options, transcript.
- **Mobile**: primary path uses **popover** or **bottom sheet**, not dependence on side panel visibility.
- **Desktop**: optional **hover** preview where `pointer: fine`; full detail still on click.
- **Missing data** is explicit (e.g. etymology not in dataset)—no silent empty panels.

## Non-goals (This Phase)

- Full redesign of conversation engine or card JSON schema.
- Replacing the desktop card panel entirely on wide layouts (it may remain as a secondary or “pin” view).
- Perfect segmentation for every multi-character string without server/token metadata (fallback rules are acceptable).

---

## User Stories

- As a learner on a phone, I can **tap a word** in the question or an option and see **pinyin and meaning** without hunting for a side panel.
- As a learner, I can **open deeper detail** (components, etymology) in the same flow when data exists.
- As a learner, I see a **clear “unavailable” state** when etymology (or other fields) are missing.
- As a learner on desktop, I can **hover** for a light preview and **click** for full insight.

---

## Surfaces (Scope)

| Surface            | Priority | Notes                                      |
|--------------------|----------|--------------------------------------------|
| Active sentence    | P0       | Current token tap behavior → unify         |
| Response options   | P0       | Same token/click semantics as sentence     |
| Transcript lines   | P1       | Same component, lower implementation order |

Each surface passes a **`source`** (e.g. `active_sentence`, `option_index`, `transcript_line`) so hint/`?` routing does not conflict.

---

## Interaction Model

### Touch (primary)

| Gesture        | Default behavior (proposed)                                      |
|----------------|------------------------------------------------------------------|
| **Tap** word   | Open **Word Insight** (popover *or* compact sheet—see below).   |
| **Tap outside**| Dismiss insight (if popover).                                  |
| **Long-press** | Optional **fast path** to **full sheet** (all sections visible). |

### Desktop (secondary)

| Input              | Behavior                                                |
|--------------------|---------------------------------------------------------|
| **Hover** (fine)   | Tooltip: pinyin (+ short gloss if space).               |
| **Click**          | Same as mobile tap: anchored popover or inline expand.  |

Use `@media (hover: hover) and (pointer: fine)` (or equivalent) so touch devices never depend on hover.

---

## Layout Modes: Popover vs Bottom Sheet

### Mode A — Anchored popover (default on phone for “light” insight)

- Appears **near the tapped token** (above if room, else below).
- **Max height** + scroll for overflow.
- **Actions**: `Next` (hint step), `Open full` (escalates to sheet), `Close`.

**When to prefer:** single-line options, dense layouts, quick peek.

### Mode B — Bottom sheet (default for “heavy” insight or long content)

- **Half-screen** (or ~60%) draggable sheet.
- **Sections** (accordion or tabs): e.g. **Read** · **Parts** · **Etymology**.
- **When to prefer:** etymology paragraphs, multiple components, accessibility (large text).

### Escalation rule (recommended)

1. **Tap** → popover with levels 1–2 (pinyin, gloss).
2. **“More”** or **long-press** → bottom sheet with full hierarchy.

---

## Wireframe Notes (ASCII)

### 1) Sentence with tappable tokens

```
┌─────────────────────────────────────┐
│ 你 想 喝 点 什 么 ？                  │
│ ^  ^  ^  ^  ^  ^  ^                  │
│ (each char/word is a hit target)     │
└─────────────────────────────────────┘
```

### 2) Popover anchored under tapped word (“喝”)

```
        ┌──────────────────┐
        │ hē               │
        │ to drink         │
        │ [Next hint] [More]│
        └────────┬─────────┘
                 ▼
              喝
```

### 3) Bottom sheet (full insight)

```
┌─────────────────────────────────────┐
│ ———  (drag handle)                  │
│ 喝  hē  ·  to drink                 │
│ ─────────────────────────────────── │
│ ▼ Components     口 + ...           │
│ ▼ Etymology      (text or “None”)   │
│ [ Open full card ]   (optional)      │
└─────────────────────────────────────┘
```

### 4) Missing etymology (explicit)

```
┌─────────────────────────────────────┐
│ 字 · zì                             │
│ character / word                    │
│ Etymology: Not in dataset yet.      │
│ (no blank card — user understands)  │
└─────────────────────────────────────┘
```

### 5) Response option row (same hit targets as sentence)

```
┌─────────────────────────────────────┐
│ A) 我 想 喝 茶                      │
│ B) 我 不 渴                         │
└─────────────────────────────────────┘
```

---

## Hint Levels 1–4 (Mobile-Friendly Mapping)

Avoid requiring four separate hover states on touch. Map to **progressive disclosure**:

| Level (concept) | Mobile UI                                                    |
|-----------------|--------------------------------------------------------------|
| 1–2             | Popover: pinyin → gloss (`Next` advances).                   |
| 3–4             | Sheet or expanded popover section: examples, nuance, etc.  |
| Deep structure  | Dedicated subsection: **Components**, **Etymology**.         |

**Rule:** One visible “surface” at a time; **Back/Close** always obvious.

---

## Relationship to Desktop Card Panel

- **Wide layout:** Card panel may still update on tap **in addition to** popover, *or* popover offers **“Pin to side panel”** when width ≥ breakpoint.
- **Narrow layout:** Card panel hidden; **popover/sheet is the source of truth**.

---

## Acceptance Criteria

### AC1 — Touch-first insight

- [ ] Tapping a token in the **active sentence** opens word insight without requiring the side card panel to be visible.
- [ ] Same tap behavior works on **response option** text (same token affordance as sentence, modulo layout).

### AC2 — Dismissal and focus

- [ ] Tapping outside the popover dismisses it; focus returns predictably (no stuck overlay).
- [ ] Only **one** word-insight surface is active at a time; opening another token **replaces** the previous.

### AC3 — Popover vs sheet

- [ ] **Popover** is used for the default quick view; content that exceeds popover max height is **scrollable** or offers **“More”** to open the sheet.
- [ ] **Bottom sheet** presents etymology/components without clipping critical text on small screens.

### AC4 — Missing data

- [ ] If etymology (or another field) is missing, UI shows an **explicit** empty state (e.g. “Not in dataset yet”), not a blank region.
- [ ] Loading state is distinct from “missing” (if async fetch is ever used).

### AC5 — Desktop hover (optional path)

- [ ] On fine pointer + hover-capable devices, **hover** shows at most **pinyin (+ short gloss)**; **click** opens the same insight as mobile tap.
- [ ] Touch devices do not require hover for any core action.

### AC6 — Source routing

- [ ] Word insight records **`source`** (sentence vs option index vs transcript) so global hint/`?` behavior does not apply the wrong context.

### AC7 — Accessibility

- [ ] Tokens are reachable by keyboard where applicable; insight surface traps focus appropriately or uses dialog/sheet patterns.
- [ ] Text scales without breaking tap targets (minimum touch target ~44×44 pt equivalent).

---

## Open Questions (For Implementation Phase)

- Breakpoint at which side panel + popover both update vs popover-only.
- Whether **long-press** is v1 or v1.1 (gesture discoverability).
- Canonical tokenization for option strings when `frame_tokens` are absent (character-level vs dictionary word match).

---

## References

- `TRANSCRIPT_REPLAY_TRANSLATION_UI_SPEC.md` — transcript toolbar patterns (future alignment).
- Existing web UI: token rendering, micro-gloss, card panel (`ui/app.js` — implementation not in this doc).

---

## Implementation log

### Step 1 (done) — Popover + option tokens + etymology fixes

**Shipped in:** `ui/app.js`, `ui/index.html`

- **Word insight popover** (`#microGloss`): `position: fixed`, clamped near the tapped token; fills **pinyin / gloss** from `getWordHintData` (no longer depends on an already-resolved card).
- **Etymology line** in popover: explicit *“in dataset”* vs *“not in dataset yet”* (AC4).
- **Active sentence** (Phase 7.4 + 6 + `setActivePartnerStatement`): tap opens popover first; **side card** opens on the same tap only when `matchMedia("(min-width: 960px) and (pointer: fine)")` — tweak breakpoint/gesture in Step 2 if needed.
- **Response options**: Hanzi split into per-character spans with `word-insight-token`; lookup `_hanziToWordId[char]`, or `opt.card_id` when the option is a **single** character. Selecting the option ignores clicks that start on a token (`ev.target.closest(".word-insight-token")`).
- **Global dismiss**: document click closes the popover unless the click is on `#microGloss` or a `.word-insight-token`.
- **Bugfix**: hint level 3 for option `?` used `wordEtymologyIndex["__opt_N"]` — now resolves via `resolveWordIdForEtymology` → real `card_id`. Option etymology row uses the same *“No etymology available yet”* fallback as the main hint row when HTML is empty.
- **Bugfix (popover / title empty)**: `cards_index.by_word_id` maps to **card_id strings**, not `{pinyin, meaning}` objects — `getWordHintData` now resolves gloss from **`_cardsByIdCache`** (primed at startup via `loadCardsByIdBlob()` + merged on each `resolveCard`). Option glyphs use **`opt.card_id`** when per-char etymology lookup misses so multi-character options are not stuck on *“Not in lexicon yet.”*
- **Schema detection**: Phase 7.4 vs Phase 6 is chosen when **every** token has a string `kind` (not only the first token).
- **Desktop hover (light)**: `title` on sentence tokens (and option tokens when data exists) shows pinyin — meaning (AC5 partial).
- **Step 1b**: Option Hanzi uses **`tokenizeHanziForOption`** (greedy longest headword match over `_cardsByIdCache`) so **multi-character words** match the active sentence; **`.option-hanzi-tokens`** restores **1.45rem / teal** like legacy `.option-hanzi`; **`getInsightTitleForWordId`** (+ option `pinyin`/`meaning` when `wid === opt.card_id`) improves hover tooltips.

**Not in Step 1:** bottom sheet, long-press, transcript tokens (P1), focus trap / full a11y dialog behavior.

### Step 2 (done) — Card panel progressive hints + character chips

**Shipped in:** `ui/app.js`, `ui/styles.css`

- **After “Open card”**, word-level depth is **in the card**: **Next hint** steps through pinyin → meaning → **character row** → word etymology (when data exists). Global **`?`** rows stay hidden when `cardPanelCoversWordHints()` (open card matches the clicked word).
- **Character chips**: first tap **TTS**; repeated taps on the **same** chip cycle **pinyin → gloss → deep hint** — pinyin/gloss via `resolveCharPinyinMeaning` (composition row → `content.characters` → `getWordHintData` / `_hanziLongestMatchMap` → **`characters_1200.json`** `pinyin`/`gloss_en` → headword syllable alignment); deep hint via **`buildCharDeepHintHTML(hanzi, openWordId)`**: **(1)** `word_etymology.runtime.json` row for that glyph under the **open card `word_id`**, **(2)** standalone glyph `w_*` etymology, **(3)** `characters_1200.json` breakdown. Word-level etymology: **`buildCardPanelWordEtymologyHTML`**. Authoritative data model: **`AI_CONTEXT.md` §2.4**.
- **Loaders**: `loadCharacters1200Core()` fetches repo-root `/characters_1200.json` (served by `ui_server` for top-level `*.json`).
- **Compact pinyin alignment**: `ui/pinyinAlign.js` — `splitHeadwordPinyinToGraphemes` splits **unspaced** headword readings (e.g. `zěnmeyàng` + 怎么样 → zěn / me / yàng) so chip hints work **without** per-character `w_*` cards. If there is still no radical data, **`buildCharGlyphFallbackHTML`** shows word + syllable context instead of an empty panel.
- **Removed** duplicate composition block + **Show/Hide etymology** toggle from the card body (etymology is via progressive reveal).
- **Redundant `OPTIONS_AVAILABLE` block**: if `section_title` is **“Characters”** (case-insensitive) and the card already has `word_composition.characters`, **modeled options are not re-rendered** (avoids the misleading “Characters · open the card panel…” style duplicate list).
- **Popover copy** when etymology exists: points to **Next hint** / character chips instead of “Show etymology”.
