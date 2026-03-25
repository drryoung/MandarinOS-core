# Strategist briefing — Phase 10.5 / 10.6 delivery + alpha testing (handoff to Phase 11)

**Purpose:** Bring ChatGPT (strategist) up to date on **recent implementation work** (Phases **10.5** and **10.6**), **alpha testing takeaways**, and the **product owner’s intent** to **defer further “conversation naturalness” fine-tuning until after Phase 11**. Request your **feedback on sequencing and next-step priorities**.

**Date:** 2026-03-19  
**Audience:** ChatGPT in **strategist** role  
**Implementation context:** Cursor + local `ui_server.py` + `ui/app.js` + runtime JSON under `runtime/out_phase7/`

---

## 1. Executive summary

- **Phase 10.5 (behaviour / conversation operating layer — partial spec):** Significant **server-side selector and stub behaviour** has been implemented in `scripts/ui_server.py` (reaction micro-layer, reciprocity / curiosity gating, weak-loop avoidance, blended topic follow-up, memory-aware behaviours where wired). This sits **alongside** (not replacing) the broader **structural** 10.5 docs (e.g. `move_type` tagging on frames — some items remain **spec-first** or heuristic).
- **Phase 10.6 (ASR / unmatched stabilization):** **`ui/app.js`** changes align with **`docs/specs/PHASE_10_6_ASR_STABILIZATION_MINI_SPEC.md`**: mixed-script tolerance on identity-style open answers, **semantic soft-match** on a small set of closed frames, **two-strike substantive fallback**, richer trace reasons (`semantic_soft_match`, `two_strike_substantive_fallback`), etc.
- **Alpha testing:** The loop is **more stable** and **less brittle** on real speech and option flows, but the owner reports dialogue still **does not feel fully natural** (rhythm, partner voice, option fit — subjective but consistent).
- **Owner decision:** **Postpone dedicated “natural conversation” tuning** until **after Phase 11** (Adaptive Conversation Intelligence per **`docs/project/MandarinOS_project_plan_v2.md`**), on the hypothesis that **capability / energy / adaptive selector** will change the optimisation surface and avoid polishing a moving target.

**Ask to strategist:** Is that deferral **sound**? What should **Phase 11** emphasise first given this baseline? Any **small, low-risk** naturalness tweaks worth doing **before** Phase 11 anyway?

---

## 2. Phase 10.5 — what shipped (implementation-focused)

**Primary code:** `scripts/ui_server.py` (comments in-file reference “Phase 10.5 behaviour tuning”).

Representative themes **implemented or partially implemented** (verify against current file for exact constants):

- **Reaction after meaningful answers** — probabilistic short partner reaction before moving on.
- **Reciprocity / curiosity** — gating and depth caps (e.g. `MAX_CURIOSITY_DEPTH`) so “loop” curiosity does not dominate.
- **Weak-loop avoidance** — reduce repetitive same-topic drilling when signals suggest it.
- **Blended reciprocity / topic follow-up preference** — tuning how often the partner pivots vs stays on-thread.
- **Memory-related hooks** (where Phase 10 memory capture exists) — suppress re-asking captured facts, light recall behaviour (see Phase 10 specs and in-server comments).

**Spec / architecture docs (not all fully encoded in data):**

- `docs/phases/MANDARINOS_PHASE_10_5_STABILISATION_BRIEF.md` — conversation **structure** and `move_type` vocabulary.
- `docs/specs/PHASE_10_5_BEHAVIOUR_IMPLEMENTATION_PLAN.md` — intended selector order (ASK → ANSWER → REACTION → optional LOOP → next).
- `docs/specs/PHASE_10_5_INTEREST_RESPONSIVENESS_REFINEMENT_PLAN.md` — interest / responsiveness refinements.
- `docs/specs/MANDARINOS — PHASE 10.5 BEHAVIOUR TUNING SPEC` — behaviour tuning source.

**Gap to name explicitly:** Full **frame-level tagging** (`move_type` on all frames) may still be **incomplete**; some behaviour may remain **heuristic**. Strategist may wish to recommend **explicit tagging vs heuristic** priority for Phase 11 prep.

---

## 3. Phase 10.6 — what shipped

**Spec:** `docs/specs/PHASE_10_6_ASR_STABILIZATION_MINI_SPEC.md`  
**Code:** `ui/app.js` (unmatched / transcript handling, closed-frame soft match, two-strike fallback, trace fields).

**Intent:** Fewer false “not understood” loops while **keeping** real recovery when input is empty or nonsense.

---

## 4. Adjacent alpha-hardening (not Phase 10.x labelled, but same sprint)

Worth noting for continuity:

- **`ui_server.py`:** **`ThreadingMixIn`** HTTP server — fixes **parallel `fetch` on load** causing `ERR_CONNECTION_RESET` / `ERR_EMPTY_RESPONSE` on Windows with the default single-threaded server.
- **Learning UI:** Explore-word panel polish (layout, character chips, component gloss pipeline via `component_gloss_maps.json`, pinyin-per-glyph fix for cases like **`怎么叫`** + `zěnme jiào` in `ui/pinyinAlign.js`).
- **Strategist noise:** Browser **`content.js` “Host validation / insights whitelist”** messages are **extensions** (e.g. Cursor/Edge), not app errors.

---

## 5. Alpha testing — subjective findings

- **Stability:** Improved (ASR edge cases, server load, fewer hard dead-ends).
- **Naturalness:** Still **below target** — partner turns can feel **template-like**, **cadence** sometimes mechanical, **options** occasionally **misaligned** with what a human partner would say next.
- **Hypothesis (owner):** Much of “naturalness” may require **Phase 11-style adaptation** (capability, energy, richer selector scoring) **plus** later **content / persona voice** passes — hence **delay deep tuning** until after Phase 11 scaffolding exists.

---

## 6. Product owner decision — defer naturalness pass until after Phase 11

**Stated preference:** Invest next in **Phase 11 — Adaptive Conversation Intelligence** (capability map, energy model, repair system, adaptive selector per **`docs/project/MandarinOS_project_plan_v2.md`** and related specs), and **return to explicit “natural dialogue” polish** once that layer is in place.

**Rationale (for strategist to validate):**

- Avoid tuning phrasing and cadence on a selector that will **change its inputs and policies** materially in Phase 11.
- Phase 11 may **surface** which failures are **selection** vs **content** vs **ASR** vs **UX**.

---

## 7. Questions for the strategist (requested feedback)

1. **Sequencing:** Do you **agree** that **deferring heavy naturalness tuning until post–Phase 11** is sensible? If not, what is the **minimum** naturalness work you would **not** defer?
2. **Phase 11 prioritisation:** Given the current build, what **order** would you recommend among: **capability map**, **energy model**, **adaptive selector**, **repair**, and **explicit frame `move_type` / conversation-move taxonomy**?
3. **Risk:** Could Phase 11 **without** any dialogue polish feel **too cold** for alpha testers? Any **1–2 week** “thin” naturalness layer (e.g. reaction variety, option rewording budget) you’d still prescribe **before** Phase 11 ends?
4. **Measurement:** What **3–5 trace or UX metrics** would you define now to judge “naturalness” improvement **after** Phase 11 (so we don’t rely only on gut feel)?

---

## 8. Key reference files (for deep dive)

| Area | Path |
|------|------|
| Roadmap v2 (Phase 11 definition) | `docs/project/MandarinOS_project_plan_v2.md` |
| Phase 10.5 stabilisation (structure) | `docs/phases/MANDARINOS_PHASE_10_5_STABILISATION_BRIEF.md` |
| Phase 10.5 behaviour implementation plan | `docs/specs/PHASE_10_5_BEHAVIOUR_IMPLEMENTATION_PLAN.md` |
| Phase 10.6 ASR mini spec | `docs/specs/PHASE_10_6_ASR_STABILIZATION_MINI_SPEC.md` |
| Prior Phase 10 strategist brief (context) | `docs/briefings/PHASE10_STRATEGIST_BRIEFING_SPECS_GAP_AND_PATH.md` |
| Repo map for implementers | `AI_CONTEXT.md` |

---

## 9. Suggested paste-in prompt for ChatGPT (strategist)

You can paste:

> Read `docs/briefings/PHASE_10_5_10_6_ALPHA_STRATEGIST_BRIEFING.md` as the authoritative handoff. Reply with: (A) agreement or concerns on deferring naturalness tuning until after Phase 11; (B) recommended Phase 11 work order and rationale; (C) any small pre–Phase‑11 naturalness interventions you still recommend; (D) proposed metrics for evaluating conversational quality after Phase 11.

---

*End of briefing.*
