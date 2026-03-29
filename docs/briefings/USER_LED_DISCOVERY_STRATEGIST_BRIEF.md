# User-Led Discovery & Recovery — Strategist Brief

**Date context:** March 2026 (last updated: 29 March 2026)  
**Audience:** Executive / product strategist (e.g. ChatGPT strategist session)  
**Purpose:** Capture where MandarinOS is on **learner-as-interviewer** behaviour, **counter-replies**, and **recovery**, and propose how to refine this work without architectural churn.

---

## Session update — 29 March 2026

Since the original brief was written, two systematic passes have been completed before returning to alpha testing.

**Pass 1 — Architectural clean-up (data extraction)**

All hardcoded strings have been extracted from Python into data files. No more hardcoded phrases or question banks in server code.

| What was extracted | From | To |
|----|----|----|
| Mirror question bank (`_MIRROR_QUESTIONS_BY_ENGINE` dict) | `ui_server.py` | `content/mirror_questions.json` |
| Graceful deflection phrases (generic + age + marriage + children) | `ui_server.py` | `content/recovery_phrases.json` (`use: "persona_deflect"`) |

New `_persona_deflect(topic, seed)` helper loads phrases from the JSON at startup. Adding or editing any deflection phrase is now a **data-only edit** — no server code change.

**Pass 2 — Frame additions (age, marriage, children)**

Three forward question frames that were listed in `FRAME_ORDER` but had broken token references have been fully wired up:

| Frame | Question | Engine | What was added |
|---|---|---|---|
| `f_how_old` | 你多大了？ | identity | Token `w_duo`, token `w_sui`, filler `ages`, user response frame `f_i_am_age` |
| `f_married` | 你结婚了吗？ | family | Token `w_jiehun`, response frames `f_not_married_yet` / `f_am_married` |
| `f_have_children` | 你有孩子吗？ | family | Token `w_haizi`, response frames `f_no_children` / `f_have_a_child` |

All three question frames now carry a `mirror_topic` tag (first step toward tagged-frame architecture — see AD-1 below). Age, marriage, and children have been added to `content/mirror_questions.json` so they appear in the learner discovery panel. `_mirror_persona_stub` routes these topics to the appropriate `_persona_deflect` call with the correct specific phrases.

**Quality gate**

Systematic coverage matrix (`scripts/test_counter_reply_matrix.py`) was run after each pass: **31/31 tests passing** across all groups (A–E, cross-persona). D3 (你多大了？) and D4 (你结婚了吗？) now return correct specific deflection phrases, not the generic fallback.

**Current state entering alpha test**

Architecture is clean, all known content gaps are closed, and the three missing frames are live. Alpha testing now targets **quality of conversational flow** — specifically the curiosity question problem described in the gaps section below.

---

## One-sentence summary

The app can now **reverse the direction of questions** (learner interviews the persona), **pause** after persona answers so the learner stays in control, and **model recovery** (repeat/slower, deflection acknowledgments). The feature is **powerful but not yet refined** — polish belongs in **content policy, phrase banks, and edge-case detection**, not in rewriting the selector.

---

## What is working now (technical + UX)

| Area | Status |
|------|--------|
| **Counter-reply** | Server returns `counter_reply` when the learner's turn is detected as a question (including 你呢？, direct persona questions, many paraphrases). |
| **User-led pause** | Client pauses after **any** `counter_reply` (not only when discovery cards exist), queues the next frame question, and defers transcript until **Continue** or an acknowledgment path. |
| **Discovery panel** | Mirror-question bank surfaces **follow-ups the learner can ask the persona**; progressive disclosure on **first clause** of `discoverable_facts` + deeper topics for follow-up taps. |
| **Mirror turns** | Discovery taps use `direction_intent: "mirror"` so the main frame does not advance spuriously; TTS `queue: true` mitigates Windows/Chrome double-`onend`. |
| **Recovery: repeat/slower** | Uses `_lastPartnerSpokenText` so "慢一点" repeats what was **actually spoken**, not the pending queued question. |
| **Recovery: deflection** | Catch-all persona phrases when no scripted answer; **deflection_ack** phrases in `recovery_phrases.json` render as learner cards to acknowledge and continue. |
| **Age / marriage / children frames** | `f_how_old`, `f_married`, `f_have_children` now fully wired with tokens, fillers, user-response frames, and discovery panel entries. |
| **Data-driven phrases** | All deflection phrases live in `recovery_phrases.json`; all mirror questions live in `mirror_questions.json`. No bare strings in Python. |
| **Ops hardening** | Server UTF-8 stdout on Windows, stale-process cleanup on port bind, payload logging by keys only. |

**Canonical UI rule preserved:** interactive response surfaces use `option-panel` patterns; discovery uses the same family of panels/cards.

---

## What is not refined yet (product gaps)

1. **Curiosity questions — primary alpha testing target**  
   When the learner reveals slot-type information (e.g. "I have two brothers, one sister") the app moves to the next topic instead of probing deeper ("do they also live in Dunedin?"). This is the most consistently reported gap across alpha sessions. Fix requires new **curiosity probe frames** that fire after specific slot fills. Cannot be fully scoped without live session observation — **this is what the next alpha test is specifically measuring**.

2. **Full persona coverage audit**  
   Matrix validates xiaoyun (primary) + xiaoming (cross-check); `zhiyuan`, `jianguo`, `meiling` are untested. Some may have thin `discoverable_facts` causing silent deflections where a real answer was possible. This is a 30-minute data audit, not a code task.

3. **Coverage vs. depth**  
   Not every plausible learner question has a **consistent** path: some still fall through to generic deflection or ASR/phrase mismatch. "Graceful" is better than silence, but **quality of match** varies across paraphrase variants.

4. **Deflection tone**  
   Graceful lines tuned for complete sentences; strategist may want a **single voice policy** (warm, brief, consistent with Phase 12 persona salience goals).

5. **Discovery + deflection together**  
   When both discovery cards and deflection acknowledgments could apply, **ordering and copy** may still confuse tired learners.

6. **Session arc**  
   Reversing questions is strong for **agency**; it does not yet guarantee a **session-level contract** (e.g. dual discovery, closure) — see existing Phase 12C brief for arc KPIs.

---

## Architectural debt — deferred enhancements (intentionally not done yet)

These are improvements identified but deliberately deferred to avoid scope creep before alpha testing. The system functions correctly without them; they reduce **future maintenance burden** rather than fixing live bugs.

### AD-1 — Replace `mirror_questions.json` with tagged forward frames *(medium — content audit + minimal server change)*

**Problem:** `content/mirror_questions.json` is a parallel question bank that must be kept in sync with `p1_frames.json` / `p2_frames.json`. Every time a new forward question frame is added, it should also appear as a learner discovery option — but currently requires editing two separate files.

**Solution:** Add `mirror_topic` field to all forward frames that are reversible discovery questions. The server's `_find_mirror_answer` already has the routing logic; it just needs to read from tagged frames instead of the JSON bank. `mirror_questions.json` would then be retired.

**Groundwork already laid:** `f_how_old`, `f_married`, and `f_have_children` already carry `mirror_topic` tags as of 29 March. The convention is established; the remaining ~20 reversible forward frames need tagging. **Add `mirror_topic` to new frames as they are created — do not do a big-bang backfill until this is the focus of a dedicated session.**

**Risk:** Low. `mirror_questions.json` continues to work as a fallback during any transition.

### AD-2 — Full 5-persona matrix test *(small — 30 min data work)*

Extend `test_counter_reply_matrix.py` Groups B/C/E to cover `zhiyuan`, `jianguo`, and `meiling`. For each, add 3–5 test cases matching their `discoverable_facts` structure. Patch any thin facts found before the next alpha round.

### AD-3 — Curiosity probe frames *(large — requires alpha signal first)*

After alpha testing characterises when curiosity follow-ups are missed, design **curiosity probe frames** that the selector fires after specific slot-fill ANSWERs. These would ask deeper questions about information the learner has just volunteered (family members → location/relationship; hobby → how long / why). Proposed as a new `move_type: "CURIOSITY"` with `_FRAME_AFTER` guards — a **selector extension**, not a rewrite.

**Do not design or implement AD-3 until at least 3 clear documented examples of the curiosity gap have been observed in alpha sessions**, so frame design addresses real patterns rather than hypothetical ones.

---

## Strategic value (why keep investing)

- **Pedagogical:** Models **real conversation** — asking, repairing, acknowledging — not only answering textbook prompts.
- **Differentiation:** Few apps give **structured** "you interview the partner" plus **recovery** vocabulary aligned to the same UX.
- **Extensibility:** New frames/options/phrases **add** behaviour without touching selector core (aligns with MandarinOS extensibility strategy).

---

## Recommended continuation order

1. **Alpha test — curiosity question focus** *(now)*  
   Run 2–3 sessions. Log every instance where the app moves to a new topic after a slot-fill without a follow-up curiosity question. Collect at least 3 clear examples before designing AD-3.

2. **Full persona coverage audit** *(AD-2 — 30 min, can do before or after alpha)*  
   Run extended matrix against zhiyuan, jianguo, meiling. Patch thin facts.

3. **Curiosity probe frame design** *(AD-3 — after step 1 generates signal)*  
   Design and add the first 3–5 curiosity probe frames. Validate in alpha.

4. **Tagged-frame migration** *(AD-1 — ongoing, add with each new frame addition)*  
   Add `mirror_topic` to frames as they are created or revised. No big-bang backfill needed.

5. **Session contract (link to Phase 12C)**  
   Tie "at least one sustained user-led discovery block per session" into the 10-minute arc when strategist approves.

---

## Guardrails (do not break)

- No **selector rewrite** for this feature set.
- **Additive** content: frames, options, `recovery_phrases.json`, persona `discoverable_facts`, `mirror_questions.json`.
- **Canonical option-panel** rendering for learner-facing cards.
- **Selector independence** — avoid hard-coding behaviour to specific `frame_id`s except documented hygiene exceptions.
- **Data-first phrases** — all persona deflection and recovery phrases live in JSON files; no bare strings in Python.

---

## Suggested KPIs for strategist approval

| KPI | Definition |
|-----|------------|
| **Counter-reply hit rate** | % of user question turns that receive a non-empty `counter_reply`. |
| **Deflection appropriateness** | % of deflections where follow-up telemetry shows learner used **ack** or **Continue** without repeat confusion. |
| **Persona fact alignment** | % of user questions that could be answered from facts **and** were (manual or sampled review). |
| **Curiosity probe rate** | % of slot-fill ANSWERs followed by a curiosity follow-up rather than a topic change. |
| **Dual agency** | % sessions with both app-led questions **and** at least one sustained user-led block (discovery or mirror chain). |

---

## Files the implementer will touch next (reference)

- `content/mirror_questions.json` — add new topics as frames are added (until AD-1 is complete).
- `content/recovery_phrases.json` — `use: "persona_deflect"` phrases; `use: "deflection_ack"` phrases.
- `p1_frames.json` / `p2_frames.json` — new frames + `mirror_topic` tags.
- `p1_words.json` / `p1_fillers.json` — tokens and fillers for new frames.
- `scripts/ui_server.py` — `_mirror_persona_stub` (new topics), `_find_mirror_answer` (new fuzzy patterns), `_FRAME_ORDER` / `_FRAME_AFTER` (new frame sequencing).
- `personas/*.json` — `discoverable_facts` depth (clause structure for progressive reveal).

---

## Closing line for the room

**We are past "does it work?" and into "does it feel fair, teachable, and like one coherent partner?"** The machinery for reversing questions and recovery is clean and fully data-driven. The next phase is **curiosity question design** and **persona coverage** — both are content tasks, not architecture tasks.
