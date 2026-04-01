# AI_CONTEXT.md — MandarinOS Repo Map (Authoritative)

This file is the *fast orientation map* for any AI assistant (Cursor, ChatGPT) working on MandarinOS.
If you are an AI tool: **read this file first** before proposing or writing code.

---

## AI roles (how tools are used)

- **ChatGPT:** Strategist and testing. Use for high-level strategy, acceptance criteria, test scenarios, and review. Does not implement code.
- **Cursor (Claude):** Senior architect and programmer. Use for architecture decisions and all implementation. When acting as **programmer**, Cursor must make **small, step-by-step changes only**—one concern at a time, no large refactors—to avoid drift from the Design Constitution. The constitution is non-negotiable; when in doubt, make the smallest safe change and stop for review.
- **Protocol reminder:** One feature per step; architect (plan) before programmer (code); stop for user and ChatGPT review after each step.

GitHub Copilot is no longer used in this workflow.
---
See docs/project/MANDARINOS_PROJECT_PLAN_v1.md for the current development roadmap.
See docs/design/MANDARINOS_ARCHITECTURE_MAP.png for system architecture.
---
AI governance rules are defined in:
docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md
---
Cursor must read docs/design/CURSOR_STARTUP_PROTOCOL.md before performing any analysis or code changes.
---
## Project Plan

The authoritative development roadmap is:

docs/project_plan/MandarinOS_project_plan_v2.md

This supersedes:
MandarinOS_project_plan_v1.md

Key update:
The roadmap now includes Phase 11 — Adaptive Conversation Intelligence,
which implements capability tracking, energy model, repair logic,
and adaptive selector behaviour.

All development decisions must align with the v2 roadmap.
---
## 0) Project goal (what MandarinOS is designed to do)

MandarinOS is a **conversation-first Mandarin learning system** designed to build **usable spoken competence**.

The core interaction loop is:

1) **Show and speak a frame sentence**
   - The system displays a sentence pattern (“frame”).
   - Audio playback allows the learner to hear natural pronunciation.

2) **Let the user respond**
   - The user may respond by:
     - speaking the response, and/or
     - selecting a response option from the UI.
   - In structured exercises, several response options may be presented (including one gold answer).

3) **Provide progressive hints when needed**
   - A hint system provides multiple levels of help.
   - Hints should move from light guidance toward clearer assistance without immediately revealing the answer.

4) **Allow exploration of words and characters**
   - Users can click words within a sentence to open the **Card Panel**.
   - The card panel may include:
     - hanzi
     - pinyin
     - meaning
     - pronunciation playback
     - character structure / etymology (future feature).

5) **Record learning signals through trace events**
   - All important user actions generate trace events.
   - These events allow the system to:
     - diagnose learner ability
     - evaluate UX quality
     - support future adaptive learning.

The system prioritizes **spoken usability and comprehension**, not passive vocabulary memorization.

---

## 1) Non-negotiable rules (architecture guardrails)

### 1.1 Do NOT manually edit generated artifacts
Generated JSON and runtime artifacts must only be produced by builders/tools.
If coverage or data is missing, fix the *source inputs* or *builders*, not the outputs.

Examples of generated/runtime artifacts (do not hand-edit):
- cards_by_id.json (runtime cards)
- runtime index files
- frame_tokens.runtime.json (tokenized frame text)
- any `*.runtime.json` or `tools/.../out/...` outputs

### 1.2 Always consult (architecture authority)
Before making architectural or behavioral changes, always consult these documents:

- **MandarinOS Design Constitution:** `docs/design/mandarinos_design_constitution.txt`
- **MandarinOS AI Interaction Protocol** (if present)
- **Trace contract:** `docs/design/TRACE_CONTRACT_v1.md`
- **Phase architecture lock:** `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`
- Other phase docs: `docs/phases/` (freezes, checklists, rollback)

These documents define the **authoritative system architecture**.
If proposed changes conflict with these documents, the documents take precedence unless the user explicitly approves a revision.

### 1.3 Minimal change policy (Cursor as programmer: strict)
When implementing code, apply the **smallest possible change** that satisfies the task:

- **One concern at a time** — do not bundle refactors, renames, and feature work in one edit.
- **One file (or a very small set) per step** — prefer one file at a time; if multiple files are required, make the change in the fewest files and smallest edits possible.
- **No large refactors** unless the user explicitly requests them — avoid "cleaning up" or "improving" structure while implementing a feature.
- **Preserve existing behavior** unless the task explicitly changes behavior.
- **Stop after each step** — present what changed, run tests, and allow review before proceeding. This keeps the codebase aligned with the Design Constitution and prevents drift.

---

## 2) The “source of truth” data model (important)

### 2.1 Lexicons (human-curated / canonical inputs)
These contain the *real linguistic content* (words, frames, etc).

Key facts:
- `p1_words.json` / `p2_words.json` have top-level key: `words` (a list)
- each word uses key `id` (not `word_id`) and includes `hanzi`
- `p1_frames.json` / `p2_frames.json` have top-level key: `frames` (a list)
- each frame uses key `id` (not `frame_id`) and includes `text`

### 2.2 Runtime cards are NOT the lexicon
Runtime cards (e.g., in `cards_by_id.json`) are for UI display and actions.
Important: card objects contain fields like:
- `actions`, `card_id`, `content`, `state`

They do **not** reliably contain hanzi.
If you need hanzi for a word, read it from the lexicons.

### 2.3 Runtime indexes link everything
A runtime index typically maps:
- word_id → card_id
- frame_id → card_id

so the UI can open the correct card panel for a clicked word or selected frame.

Important known mapping:
- runtime `cards_index.by_word_id` maps both **word_id and frame_id** to **card_id**.

### 2.4 Character breakdown & etymology (authoritative — do not invent fields)

**Sources of truth (human-curated / canonical):**

| Input | Role |
|--------|------|
| **`characters_1200.json`** (repo root **and/or** `data/characters_1200.json`) | Character records: `id`, `hanzi`, `pinyin`, `gloss_en`, `primary_radical`, `decomposition`, `etymology`, `mnemonic`, etc. The filename reflects the original core set; the **same schema** may hold a much larger corpus (e.g. thousands of characters). Builder and audit **load both paths if present and pick the file with more `characters[]` rows** (so a tiny root sample does not shadow a full `data/` copy). UI dev server serves `/data/…` so the client can load the large file without copying to root. |
| **`word_character_links.json`** (repo root) | Maps **`word_id` → `character_id`s** (and optional roles). Regenerate from p1/p2 + corpus: **`python tools/generate_word_character_links.py --write`**, then rebuild runtime. |

**Generated runtime (builder only — never hand-edit):**

- **`tools/build_runtime_artifacts.py`** reads the two files above plus cards and writes **`runtime/out_phase7/word_etymology.runtime.json`**. If a link row’s `character_id` is absent from the corpus (e.g. old `c_de` vs new `c_auto_*`), the builder **resolves the row by `hanzi`** when present so etymology still merges.
- Shape: `words[word_id].characters[]` — each row is the merged character payload for that **word’s** component glyphs (radical, decomposition, notes), suitable for UI lookup **in the context of the open card’s `word_id`**.
- **Inferred word narratives (optional):** if **`data/word_etymology_top1000_curated_v2_inferred_narrative.json`** exists, the builder adds **`word_narrative`** when the headword equals a narrative row’s `hanzi`, else **`glyph_narrative`** on each `characters[]` row whose `char` appears in that file. Stats: **`build_report.narrative_merge`**. UI shows these in the card etymology block (`buildWordNarrativeSectionHTML` + `formatWordEtymologyCharRecordHtml` in `ui/app.js`).

**UI rule:** Resolve character hints by **looking up existing rows** in `word_etymology` for the **open word** first (match glyph to `characters[].char`), then single-character `word_id` if present, then **`characters_1200.json`** loaded for Hanzi→row. Do not treat card JSON nulls as the place “where data lives”; cards are for display/actions, not the character corpus.

**Coverage audit:** Run `python scripts/audit_vocab_character_coverage.py` from repo root; it prints gaps and writes `docs/reports/vocab_character_coverage_audit.md` (UTF-8). Use it whenever lexicon, links, or `characters_1200.json` change.

**Deferred product plans (not implemented):**
- Lighter “learner memory bridge” between Form and full etymology — **`docs/plans/learner_etymology_hints_plan.md`**.
- Parenthetical **component/radical glosses** on the Form line — implemented via **`component_gloss_maps.json`** at repo root (UI: `GET /component_gloss_maps.json`; fallback `/data/…`) + `loadComponentGlossMaps()` in `ui/app.js`; audit **`python scripts/audit_component_gloss_coverage.py`** → `docs/reports/component_gloss_coverage.md`; optional corpus sync **`python tools/backfill_component_gloss_en.py`**. Plan: **`docs/plans/component_radical_gloss_plan.md`**.

**Corpus recovery:** If the full character DB is missing from the clone, see **`docs/reports/CORPUS_RECOVERY_NOTES.md`** (git/OneDrive forensic notes from Step 1).

---

## 3) Critical runtime contract: OPEN_CARD payload

The OPEN_CARD payload structure includes:
- `engine_id`
- `frame_id`
- `card_id`
- `reason`

Any implementation must preserve this payload shape.

---

## 4) Derived artifact: tokenized frame text

There is a canonical derived artifact that tokenizes each frame’s text to support word-level rendering:

- `frame_tokens.runtime.json` (canonical)
- `frame_render_tokens.runtime.json` (compat alias; byte-identical)

This supports future UI where individual tokens are clickable (word → card panel).

---

## 5) Where things live (repo map)

> File names may evolve; this is the *conceptual map*.
> Always search the repo if unsure, but keep the rules above.

### 5.0 Conversation architecture (design specs)

All conversation-design decisions (engines, sentence selector, memory, capability map, steering, ladders, persona network) live under **`docs/specs/`**. The single entry point is:

- **`docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`** — Lists every conversation-related spec: 7 engines (Identity, Place, Food, Family, Study/Work, Travel, Interests), Next Question Selector, memory model, capability map, steering engine, ladders, support packs, persona network. Use it when implementing or reviewing conversation logic so no iPhone/ChatGPT design work is missed.

**Strategist handoffs (ChatGPT):** e.g. **`docs/briefings/PHASE_10_5_10_6_ALPHA_STRATEGIST_BRIEFING.md`** — Phase 10.5/10.6 delivery summary, alpha notes, defer-naturalness-until-post–Phase‑11 intent, and questions for next-step feedback. Older context: `docs/briefings/PHASE10_STRATEGIST_BRIEFING_SPECS_GAP_AND_PATH.md`. Phase 10.7 / move grammar: **`docs/briefings/MANDARINOS_PHASE_10_7_PHASE_11_BRIEFING.txt`**, **`docs/briefings/MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt`**. **Minimal implementation plan (preserve 10.5/10.6):** **`docs/plans/PHASE_10_7_MINIMAL_IMPLEMENTATION_PLAN.md`**. **User-led discovery & next-phase alignment:** **`docs/briefings/USER_LED_DISCOVERY_STRATEGIST_BRIEF.md`**, **`docs/briefings/MandarinOS_Phase_12C_Alignment_Brief.md`**, **`docs/briefings/MandarinOS_Phase12D_Cursor_Implementation_Brief.md`**.

### 5.1 Runtime (server-side)
Likely areas:
- `runtime/` — runtime resolver logic, open-card resolver, etc.
- `api/` or similar — endpoints such as `/api/run_turn`

### 5.2 UI (client-side)
Likely areas:
- `ui/` — `index.html`, `styles.css`, `app.js` (or similar)

UI responsibilities:
- render frame text
- speak frame text (audio playback)
- accept spoken input and/or option selection (where implemented)
- show hint affordances
- open/close card panel
- emit trace events

### 5.3 Builders / Tools (generate runtime artifacts)
Likely areas:
- `tools/` — builder scripts that generate runtime JSON artifacts
Examples include tokenization builder(s) producing `frame_tokens.runtime.json`.

---

## 6) How to run the local UI server (canonical command)

From repo root, start the server with:

    python -m scripts.ui_server

Stop it with Ctrl+C.

Open UI at:

    http://localhost:8765/ui/index.html

(If the port differs, trust what the server prints, but 8765 is the canonical expectation.)

---

## 7) Testing expectations

We prefer deterministic build outputs:
- same inputs → identical artifacts
- golden tests verify runtime JSON content

If tests exist for a builder:
- update the builder AND update/extend the tests accordingly
- do not “fix” tests by weakening assertions unless explicitly instructed

---

## 8) Common failure modes (avoid these)

1) Assuming runtime cards contain hanzi/pinyin (often false)
2) Editing generated JSON by hand (breaks determinism)
3) Breaking trace event shapes or names
4) Refactoring UI rendering in a way that removes required affordances (hint button, option buttons, word click)
5) Creating “helpful” new fields in payloads without updating the contract docs

---

## 9) If you are asked to implement a feature (Cursor as programmer)

Use this sequence—and keep each implementation step **small**:

1) Identify the contract constraints (trace + payload shapes) and the Design Constitution rules that apply.
2) Identify the source-of-truth data (lexicons vs runtime artifacts).
3) Identify the builder that must change (if any).
4) **Implement one small, reviewable change** — do not bundle multiple concerns (e.g. "add feature X and refactor Y"). If the task is large, break it into steps and implement one step at a time.
5) Run tests.
6) Summarize changes + files touched + why it is safe and consistent with the constitution.

If a change would conflict with the Design Constitution or phase locks, do not implement it; report the conflict and ask for direction.

---

## 10) Glossary (short)

- Frame: a target sentence pattern the user learns to produce/respond to
- Word: lexicon entry with hanzi/pinyin/meaning metadata
- Card: UI panel content for a word/frame (display + actions)
- Runtime artifact: generated JSON used by UI/runtime
- Builder: script that generates runtime artifacts deterministically
- Trace: structured events emitted by UI/runtime for debugging and learning analytics

---

## 11) “Read-first” files for any AI assistant

If present, read these before making architectural suggestions:
- `docs/design/mandarinos_design_constitution.txt` (Design Constitution)
- MandarinOS AI Interaction Protocol (if present)
- `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`
- `docs/design/TRACE_CONTRACT_v1.md` (trace contract)
- Other phase docs: `docs/phases/`
- Build directives under `integration_kit/` (if relevant to the task)
- **`docs/briefings/Cursor_Directive_MandarinOS_Extensibility_Strategy.md`** — extensibility directive (mandatory for any change proposal)
- **`docs/briefings/MandarinOS_Phase_12C_Alignment_Brief.md`** — 12C / 12C.1 / 12D separation (mandatory for conversation-layer work)
- **`docs/briefings/MandarinOS_Phase12D_Cursor_Implementation_Brief.md`** — when implementing or scoping Phase 12D overlay
- **`docs/briefings/USER_LED_DISCOVERY_STRATEGIST_BRIEF.md`** — user-led discovery, counter-reply, recovery; architectural debt AD-1–AD-3

### Extensibility strategy (mandatory — read before proposing any change)

- **`docs/briefings/Cursor_Directive_MandarinOS_Extensibility_Strategy.md`** — Standing Cursor directive (authoritative copy; a parallel copy may exist under `docs/specs/`). Defines: treat the architecture as a **stable extensible base**; decision priority order (**content → ordering/builder → minimal selector hygiene → architecture only with justification**); beta-feedback classification **A–E** (content value, selector/flow, builder/options, structural discourse, alpha polish); rules: **selector independence**, **additive growth**, **soft `FRAME_ORDER`**, **extensibility test** (20–50 new frames must not force selector/scoring/runtime rewrites), **builder-first**; what to optimise for (extensibility, stability, conversational value density, minimal churn); proposals must state intervention level and why it is the **lowest sufficient** level.
- **`docs/specs/MandarinOS_Extensibility_Strategy.md`** — Strategist-level strategy doc. Core principles: stable backbone, additive growth, competitive coexistence, builder-centric improvement.

These files define the **mandatory working framework** for all future MandarinOS development. A Cursor rule at `.cursor/rules/mandarinos-architecture.mdc` enforces the key points automatically every session.

### Phase alignment — 12C, 12C.1, 12D (mandatory for near-term work)

- **`docs/briefings/MandarinOS_Phase_12C_Alignment_Brief.md`** — Canonical separation of three layers:
  - **Phase 12C — Repair → Comprehension:** user input unclear / ASR mismatch → soft repair → one targeted clarification → then fallback. No cultural explanation or strategic advice in this layer.
  - **Phase 12C.1 — Reciprocity & exploration:** user questions, direction shifts, 你呢？→ persona responds coherently, progressive depth, no forced return to prior flow. Aligns with **user-led discovery / counter-reply** work.
  - **Phase 12D — Meaning + Move overlay:** ambiguous **partner** language → show likely meaning + 2–3 safe next moves. Direction: **Persona → User** (interpret + act). **Must not** change Phase 6 runtime, merge layers, or add selector complexity.

**Implementation priority (from alignment brief):** (1) finish/stabilise **12C** (repair), (2) stabilise **12C.1** (reciprocity), (3) then **12D** (overlay). **Optimise for:** conversation survival, interaction continuity, user confidence under uncertainty — not abstract “correctness” or completeness.

- **`docs/briefings/MandarinOS_Phase12D_Cursor_Implementation_Brief.md`** — Detailed build spec for **12D**: thin **content + UI overlay** (`meaning_move_overlay` runtime artifact, ~20–30 high-value items v1), keyed by **`frame_id`**, expandable “Meaning + Move” UI, fail-soft if missing, **no** selector/engine/move_type rewrite. Non-goals: live meeting assistant, ASR rewrite, personalization engine, cultural essays on every turn.

**User-led discovery & recovery (12C.1-related product track):** see **`docs/briefings/USER_LED_DISCOVERY_STRATEGIST_BRIEF.md`** — counter-reply, discovery panel, recovery phrases, data-driven mirror/deflection JSON.

---

## 11a) Overall direction — next phases (summary for strategists and implementers)

MandarinOS is in a **refinement phase**: gains should come mainly from **better frames, responses, options, and tagging**, not from repeated architectural rework. The north star for the next stretch is:

1. **Keep the stable backbone** — Phase 6 runtime, selector, and conversation engine stay the default path; changes are **additive** unless explicitly approved.
2. **Layer conversation support cleanly** — **12C** (repair/clarify before fallback), **12C.1** (reciprocity and user-led exploration — already partially implemented via counter-reply and discovery), **12D** (optional Meaning + Move overlay for ambiguous partner lines). Do not merge these into one system or hide them inside the selector.
3. **Ship 12D as a small overlay** — separate JSON artifact + UI; improves how alpha testers experience **interpretation and safe next moves** without changing core turn logic.
4. **Continue systematic content quality** — curiosity probes, persona coverage, mirror/tagged-frame migration (see USER_LED_DISCOVERY strategist brief), phrase banks in JSON, matrix tests — all **content and hygiene**, not selector rewrites.

**Success for this era:** the product feels like a **growing network of conversational moves** plus **survival tooling** (repair, reciprocity, interpretation) — not a brittle script and not a one-off patch stack.

---

## 12) Hybrid AI vision (concept-level — not yet implemented)

**Source:** `docs/design/MANDARINOS_PHASE_12_HYBRID_AI_CONCEPT_BRIEFING.txt`
**Status:** Architectural north-star only. Do NOT implement AI execution layer yet.

### Core principle (non-negotiable)

> MandarinOS is "a structured conversation training system with controlled moments of AI improvisation."

AI is a **conditional extension layer**, not the main engine. Every conversation architecture decision must be compatible with this future layer being bolted on without rewriting the structured engine.

### How the hybrid layer will eventually work

```
User Input
  → Structured Engine (default path — always tried first)
  → AI Eligibility Check (only if structured path is weak/absent)
      ├─ Structured Path (no AI needed) → continue normally
      └─ Bounded AI Path (max 1–2 turns) → return to structured engine
```

### AI eligibility conditions (all must be met)

1. Input is meaningful and relevant to current topic
2. Structured continuation is weak or absent (no good next frame)
3. Input is interesting enough to reward
4. A safe return path to the structured engine exists

AI must NOT trigger for: ASR mismatch, unclear input, or already-supported responses.

### AI output contract (when eventually triggered)

AI must return structured output only — never free-form text:
```json
{
  "acknowledgement": "...",
  "follow_up": "...",
  "move_type": "LOOP",
  "difficulty_band": "beginner_mid",
  "return_target_engine": "food",
  "return_target_move_type": "ASK"
}
```

### What AI is NOT allowed to do

- Run multi-turn free conversation
- Control topic direction fully
- Bypass the hint/repair system
- Escalate vocabulary complexity beyond difficulty_band
- Replace repair logic

### Implementation roadmap (future — in order)

- Stage 1: Log-only (record AI-eligible moments, no execution)
- Stage 2: Single-turn AI pilot
- Stage 3: Bridge integration
- Stage 4: Expanded hybrid

### How current work prepares for this

Every improvement to the structured engine (curiosity loops, repair ladder, difficulty ramp, frame mutual exclusion, engine depth guard) makes the "structured path" more robust. This directly reduces the frequency AI would need to trigger, and ensures the structured engine is strong enough to be the default. **Do not shortcut the structured engine to make room for AI.** Build the structured engine first; AI fills the remaining gaps.

### State model to add (Stage 1, future)

When implementing Stage 1, add to `conversation_state`:
- `ai_mode_active` (bool)
- `ai_turn_count` (int)
- `ai_trigger_reason` (str)
- `ai_return_target` (engine id)

---

## 13) Current phase status

Updated: 2026-03-29 (extensibility + 12C/12D alignment integrated)

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 10.5 | Complete | Legacy selector, curiosity depth, slot followup |
| Phase 10.6 | Complete | ASR / unmatched handling, UI word insight + character exploration |
| Phase 10.7 | Complete | move_type tagging (all p1/p2 frames), transition calibration |
| Phase 11.0.x | Complete | Conservative scoring scaffold; capability/energy diagnostic signals |
| Phase 11.1 | Complete | Engine depth guard, identity re-entry block, FRAME_ORDER priority, hobby reorder, work options builder fix |
| Phase 11.1.1 | Complete | Post-fix observation pass; extended identity guard to ladder + coherence gate |
| Phase 12 | Complete | EXTEND frames, persona layer, discoverability (voice_line + partner_fact), Phase 12B curiosity chain limit + soft repair ladder |
| **12C — Repair → Comprehension** | **In progress / next** | Clarification before fallback on unclear input; see alignment brief. Does not subsume 12C.1 or 12D. |
| **12C.1 — Reciprocity & exploration** | **Active / evolving** | User questions, 你呢？, counter-reply, discovery panel, progressive persona answers; strategist brief: `USER_LED_DISCOVERY_STRATEGIST_BRIEF.md`. |
| **12D — Meaning + Move overlay** | **Planned** | Thin UI + `meaning_move_overlay` artifact; **after** 12C stable; see `MandarinOS_Phase12D_Cursor_Implementation_Brief.md`. |
| **Alpha tuning** | **Active** | Conversation quality, matrix tests, content/data iteration per extensibility directive |

### Active alpha tuning — what has been implemented (baseline)

- **Mutual exclusion frames:** `f_ask_you_name` ↔ `p2_id_2`, `f_travel_where` ↔ `p2_tr_1`, food frames — prevents semantic duplicate questions
- **Difficulty ramp:** within each engine, difficulty-1 frames appear before difficulty-2, which appear before difficulty-3 (stable sort preserving FRAME_ORDER within tier); "life" engine blocked until `exchange_count ≥ 16`
- **User-question chain:** after a probe/direction answer, probe row re-shows so user can ask 1–3 consecutive follow-up questions before partner reclaims lead (`MAX_USER_QUESTION_CHAIN = 3`)
- **Double-turn guard:** `_runTurnInFlight` flag prevents concurrent `runTurn` calls that caused duplicate partner questions
- **Bridge prefix:** only `顺便问一下，` remains; `对了，` removed (caused awkward "对了，好吃吗？" transitions)
- **Probe row frequency:** `MAX_PROBE_CHAIN` raised 1 → 2
- **User-led discovery stack:** counter-reply, `_lastPartnerSpokenText` for recovery, `content/mirror_questions.json`, `recovery_phrases.json` (`persona_deflect`, `deflection_ack`), age/marriage/children frames wired; systematic matrix: `scripts/test_counter_reply_matrix.py`

### Near-term roadmap (aligned with briefings — not optional opinion)

1. **Stabilise 12C** — repair ladder behaviour before heavy fallback.
2. **Stabilise 12C.1** — reciprocity and exploration (incl. curiosity probes where data supports; see strategist brief on “curiosity question gap”).
3. **Implement 12D** — Meaning + Move overlay per implementation brief (separate artifact, no selector rewrite).
4. **Ongoing** — extensibility-first content work; avoid selector rewrites unless justified.

### Parked / later (unchanged)

- **Hybrid AI layer:** see Section 12 above; prerequisite is a robust structured engine; not a substitute for 12C–12D layers.

END.
