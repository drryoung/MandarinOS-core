# Phase 9 — Content & Engines Implementation Plan

**Purpose:** Plan for (1) more content, (2) new topics, (3) richer engine logic, (4) emergency/recovery phrases. Execute one step at a time; stop for review after each.

---

## Current state

- **Selector:** Uses frames from `p1_frames.json` / `p2_frames.json`; prefers partner questions (text contains ？); bridge tier switches engine after 2+ turns.
- **Engines in data:** identity, place, family, work, hobby, travel, life (tagged on frames).
- **Recovery:** UI loads `recovery_phrases.runtime.json`; used when speech “not understood”; spec in `mandarinos_emergency_phrases_p1_p2_v2.md`. Runtime file may be built by a tool or missing (to confirm).
- **Engine specs:** `MandarinOS_engine_specs_v1.md`, ladders, support packs define Core / Treasure / Loop / Bridges per engine; frames do not yet have a `question_type` (or similar) field.

---

## 1. More content (frames per engine)

**Goal:** Add more partner-question frames to existing engines so each topic has more variety and natural depth.

**Steps:**

| Step | Action | Owner |
|------|--------|--------|
| 1.1 | Audit current frame count per engine (identity, place, family, work, hobby, travel, life) and list gaps vs engine specs / ladders. | Cursor or human |
| 1.2 | Add new frames to `p1_frames.json` / `p2_frames.json` for at least one engine (e.g. identity or place) using spec/ladder as source: hanzi, pinyin, text_en, engine, speaker, option_tokens where applicable. | Content / Cursor |
| 1.3 | Re-run any builders that depend on frames (e.g. frame_options, frame_tokens) and verify UI shows new frames. | Cursor |
| 1.4 | Repeat for other engines in priority order. | — |

**Reference:** `MandarinOS_engine_specs_v1.md`, `MandarinOS_conversation_ladders_full_draft_v2.md`, existing frame schema in p1/p2_frames.json.

---

## 2. New topics (new engine tags)

**Goal:** Add at least one new topic (e.g. **Food**) so the selector can use it and bridge to/from it.

**Steps:**

| Step | Action | Owner |
|------|--------|--------|
| 2.1 | Choose new engine(s): e.g. Food (吃什么, 喜欢什么菜, 那里的菜怎么样). | Human / strategist |
| 2.2 | Add frames with `"engine": "food"` (or chosen tag) to the lexicon; ensure speaker, text, pinyin, option_tokens. | Content / Cursor |
| 2.3 | Add `"food"` (or new tag) to `_BRIDGE_TARGETS` in `scripts/ui_server.py` and add bridge targets *to* food (e.g. place, travel). | Cursor |
| 2.4 | Rebuild runtime artifacts if needed; test Next button and bridge to/from new engine. | Cursor |

**Reference:** Engine specs (Food section), `_BRIDGE_TARGETS` in ui_server.

---

## 3. Richer engine logic (question type, order)

**Goal:** Use Core / Treasure / Loop (and optionally Bridge) so the selector can prefer “core” questions first, then treasure/loop, and order within an engine more logically.

**Steps:**

| Step | Action | Owner |
|------|--------|--------|
| 3.1 | **Schema:** Add optional `question_type` (or `move_type`) to frame schema: e.g. `"core"`, `"treasure"`, `"loop"`, `"bridge"`. Document in a short schema or AI_CONTEXT. | Cursor |
| 3.2 | **Content:** Tag existing and new frames with `question_type` where known (from engine specs / ladders). | Content / Cursor |
| 3.3 | **Selector:** In `_engine_partner_question_frame_ids` (or a new helper), prefer order: core → treasure → loop (and optionally treat bridge as transition). Return frames in that order so “first valid” gives logical progression. | Cursor |
| 3.4 | If needed, add a small “canonical order” list per engine (ordered frame_ids) and use that instead of or in addition to question_type. | Cursor |

**Reference:** `MandarinOS_engine_specs_v1.md` (Core / Treasure / Loop / Bridges), `MandarinOS_conversation_ladders_full_draft_v2.md`.

---

## 4. Emergency / recovery phrases

**Goal:** Ensure emergency/recovery phrases are fully specified, built, and used so the learner can repair (什么？, 再说一次, 慢一点, 我不懂, etc.) and the partner can respond appropriately.

### Design decision: recovery as option panels

**Decision:** Recovery phrases are **not** a separate engine with partner + response turns. They appear **in the same response-options area** as one or more option panels, alongside (or instead of) the usual answer options.

- **Other engines:** Partner asks (e.g. 你叫什么名字？) → options are possible **user answers** (e.g. 我叫李明, 我叫张瑞).
- **Recovery:** The “partner” has already asked the current question. The **options** we show include (or are) **recovery phrases** (什么？, 再说一次, 慢一点, 我不懂, etc.). So the learner chooses a repair phrase from the same UI as answer options.

**Implementation approach:**

1. **Data:** Recovery phrases have the same shape needed for an option panel: `hanzi`, `pinyin`, `text_en` (or meaning), and a type flag (e.g. `kind: "RECOVERY"` or `is_recovery: true`) so we don’t treat them as gold/slot and we can handle selection differently.
2. **Rendering:** When we render the options area (e.g. after “Show options” or in respond mode), we **append** one or more recovery phrases as additional option panels—same `.option-panel` / `.option-hanzi` UI, so they look like the other options but are clearly repair phrases (and can be styled or labelled if desired).
3. **On select:** When the user selects a recovery-option panel, we record “user said [phrase]” in the transcript and then the **partner response** is defined by rule (e.g. repeat the current question, or “好，再说一次：……”). We do **not** run the normal “next question” selector for recovery; we either repeat the current frame or use a simple rule (e.g. TTS repeat, or one predefined line).
4. **Placement:** Either (A) always show 1–2 recovery panels at the end of the options list for every turn, or (B) show them only when “Uncertain / Help” (or similar) has been used, or (C) configurable. Design choice can be decided in the first implementation step.

So the “recovery engine” is: **a fixed set of user-utterance options injected into the options area + a simple rule for the partner’s response (repeat or one line)**. No separate engine in the selector.

---

**Steps:**

| Step | Action | Owner |
|------|--------|--------|
| 4.1 | **Source of truth:** Confirm or create a single source (e.g. JSON or markdown) for recovery phrases with id, hanzi, pinyin, text_en, level (P1/P2). Align with `mandarinos_emergency_phrases_p1_p2_v2.md` and `MandarinOS_support_packs_v1.md`. | Cursor / human |
| 4.2 | **Build:** Ensure a builder (or script) produces `recovery_phrases.runtime.json` consumed by the UI at `/runtime/out_phase7/recovery_phrases.runtime.json`. If missing, add builder and wire into build. | Cursor |
| 4.3 | **UI — option panels:** When rendering options, append recovery phrases from runtime as option panels (same area as answer options), with `kind: "RECOVERY"` (or equivalent). On select: record user line, then partner response by rule (e.g. repeat current question or “好，再说一次：……”). | Cursor |
| 4.4 | **UI:** Keep or adapt `getRecoveryPhraseForNotUnderstood` for the “speech not understood” path (partner says a recovery-style line); ensure it uses the same phrase list and doesn’t duplicate logic. | Cursor |
| 4.5 | **Selector (optional):** After user selects a recovery option, partner repeats or simplifies; optionally next “Next” could prefer same question or easier frame. | Cursor |

**Reference:** `mandarinos_emergency_phrases_p1_p2_v2.md`, `MandarinOS_support_packs_v1.md`, UI recovery flow in app.js.

---

## Suggested order of execution

1. **4. Emergency/recovery** — Small, self-contained; unblocks “repair” experience.
2. **1. More content** — One engine first (e.g. identity or place); validates pipeline.
3. **2. New topics** — Add Food (or one topic); validates bridge map and new engine.
4. **3. Richer engine logic** — Add question_type and selector ordering; improves flow.

---

## Out of scope for this plan

- Full capability map, memory, or energy model (Phase 10).
- Persona network (Phase 10).
- Changes to Phase 6 runtime contract or trace schema unless explicitly needed.

---

*Plan for review. After approval, implement one step at a time and stop for review after each.*
