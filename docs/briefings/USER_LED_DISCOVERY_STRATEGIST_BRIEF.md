# User-Led Discovery & Recovery — Strategist Brief

**Date context:** March 2026  
**Audience:** Executive / product strategist (e.g. ChatGPT strategist session)  
**Purpose:** Capture where MandarinOS is on **learner-as-interviewer** behaviour, **counter-replies**, and **recovery**, and propose how to refine this work without architectural churn.

---

## One-sentence summary

The app can now **reverse the direction of questions** (learner interviews the persona), **pause** after persona answers so the learner stays in control, and **model recovery** (repeat/slower, deflection acknowledgments). The feature is **powerful but not yet refined** — polish belongs in **content policy, phrase banks, and edge-case detection**, not in rewriting the selector.

---

## What is working now (technical + UX)

| Area | Status |
|------|--------|
| **Counter-reply** | Server returns `counter_reply` when the learner’s turn is detected as a question (including 你呢？, direct persona questions, many paraphrases). |
| **User-led pause** | Client pauses after **any** `counter_reply` (not only when discovery cards exist), queues the next frame question, and defers transcript until **Continue** or an acknowledgment path. |
| **Discovery panel** | Mirror-question bank surfaces **follow-ups the learner can ask the persona**; progressive disclosure on **first clause** of `discoverable_facts` + deeper topics for follow-up taps. |
| **Mirror turns** | Discovery taps use `direction_intent: "mirror"` so the main frame does not advance spuriously; TTS `queue: true` mitigates Windows/Chrome double-`onend`. |
| **Recovery: repeat/slower** | Uses `_lastPartnerSpokenText` so “慢一点” repeats what was **actually spoken**, not the pending queued question. |
| **Recovery: deflection** | Catch-all persona phrases when no scripted answer; **deflection_ack** phrases in `recovery_phrases.json` render as learner cards to acknowledge and continue. |
| **Ops hardening** | Server UTF-8 stdout on Windows, stale-process cleanup on port bind, payload logging by keys only. |

**Canonical UI rule preserved:** interactive response surfaces use `option-panel` patterns; discovery uses the same family of panels/cards.

---

## What is not refined yet (product gaps)

1. **Coverage vs. depth**  
   Not every plausible learner question has a **consistent** path: some still fall through to generic deflection or ASR/phrase mismatch. “Graceful” is better than silence, but **quality of match** varies.

2. **Persona data vs. deflection**  
   Sometimes a question **could** be answered from `discoverable_facts` or profile (e.g. family location) but the pipeline returns a **generic** line — feels like the partner “doesn’t know themselves.”

3. **Deflection tone**  
   Server-side graceful lines were tuned for **complete sentences**; strategist may want a **single voice policy** (warm, brief, consistent with Phase 12 persona salience goals).

4. **Discovery + deflection together**  
   When both discovery cards and deflection acknowledgments could apply, **ordering and copy** (“ask them” vs “respond to them”) may still confuse tired learners.

5. **Session arc**  
   Reversing questions is strong for **agency**; it does not yet guarantee a **session-level contract** (e.g. dual discovery, closure) — see existing Phase 12C brief for arc KPIs.

6. **Alpha polish**  
   ASR errors, very long persona stubs in content files, and edge phrasings still surface; refinement is **iterative content + detection**, not one more big client rewrite.

---

## Strategic value (why keep investing)

- **Pedagogical:** Models **real conversation** — asking, repairing, acknowledging — not only answering textbook prompts.
- **Differentiation:** Few apps give **structured** “you interview the partner” plus **recovery** vocabulary aligned to the same UX.
- **Extensibility:** New frames/options/phrases **add** behaviour without touching selector core (aligns with MandarinOS extensibility strategy).

---

## Recommended continuation order (low risk, high leverage)

1. **Question detection & routing audit**  
   Expand `_is_user_question` / fuzzy mirror routing with **telemetry** (which phrases hit catch-all). Goal: fewer false “deflection” when facts exist.

2. **Fact routing matrix**  
   Small table: *question pattern → fact key → first clause vs nth clause* — ensures “你妈妈在哪儿？” maps to **family/place** when data exists.

3. **Recovery vocabulary**  
   Keep **deflection_ack** and “need help” phrases in **`recovery_phrases.json`** as the single source; add variants (shorter, more oral) as needed.

4. **Copy pass**  
   One voice for: counter-reply wrappers (“我呢，…”), deflection lines, discovery headers — align with persona pack.

5. **Session contract (link to Phase 12C)**  
   Optionally tie “at least one user-led discovery block per session” into the 10-minute arc when strategist approves.

---

## Guardrails (do not break)

- No **selector rewrite** for this feature set.
- **Additive** content: frames, options, `recovery_phrases.json`, persona `discoverable_facts`, mirror question bank.
- **Canonical option-panel** rendering for learner-facing cards.
- **Selector independence** — avoid hard-coding behaviour to specific `frame_id`s except documented hygiene exceptions.

---

## Suggested KPIs for strategist approval

| KPI | Definition |
|-----|------------|
| **Counter-reply hit rate** | % of user question turns that receive a non-empty `counter_reply`. |
| **Deflection appropriateness** | % of deflections where follow-up telemetry shows learner used **ack** or **Continue** without repeat confusion. |
| **Persona fact alignment** | % of user questions that could be answered from facts **and** were (manual or sampled review). |
| **Dual agency** | % sessions with both app-led questions **and** at least one sustained user-led block (discovery or mirror chain). |

---

## Files the implementer will touch next (reference)

- `scripts/ui_server.py` — `_is_user_question`, `_answer_user_question_prefix`, `_mirror_persona_stub`, `_find_mirror_answer`, `_MIRROR_QUESTIONS_BY_ENGINE`, response `counter_reply` / `user_led` / `discovery_questions`.
- `ui/app.js` — `_runTurnInner`, `renderDiscoveryPanel`, `submitDiscoveryQuestion`, recovery repeat/slower, `_lastPartnerSpokenText`.
- `content/recovery_phrases.json` — phrase banks including `use: "deflection_ack"`.
- `personas/*.json` — `discoverable_facts` length and clause structure (progressive reveal).

---

## Closing line for the room

**We are past “does it work?” and into “does it feel fair, teachable, and like one coherent partner?”** The machinery for reversing questions and recovery is in place; the next phase is **refinement and policy**, not a new architecture.
