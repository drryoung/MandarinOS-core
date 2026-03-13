# Phase 10 Strategy Briefing for ChatGPT (Strategist)

**Purpose:** Brief you on (1) a recent specs-vs-implementation gap assessment and (2) a suggested path forward as we start Phase 10 — Memory and Persona. The project owner is relatively happy with initial alpha testing and wants to tackle Phase 10 in a spec-guided way.

**Date:** 2026-03  
**Audience:** ChatGPT in the role of strategist.  
**Context:** Cursor has produced an architectural gap analysis comparing `docs/specs/` to the current implementation. This briefing summarises that assessment and recommends how to sequence Phase 10 so we implement memory and persona without boiling the ocean.

---

## 1. The gap assessment (source document)

**Full document:** `docs/project/SPECS_TO_IMPLEMENTATION_GAP.md`

That document compares each major spec in `docs/specs/` to what is actually implemented (server, UI, runtime). It covers:

- **Turn data contract** — Prompt/response/event/submission/evaluation payloads
- **Runtime conversation state engine** — State object, state machine, turn cycle, response mode, turn types, repair state, selector modes
- **Next question selector** — Inputs (state, capability, energy, memory, persona, constraints); output types; candidate generation; filters; scoring; hint-aware and memory-aware behaviour
- **Engine specs** — Trigger patterns, bridges, Core/Treasure/Loop, steering
- **Steering engine** — Signal extraction from learner answers, content-driven engine/branch selection
- **Memory model (v1/v2)** — Two-sided memory, persona-attached memory, four layers, memory recall
- **Capability map + update rules** — Per-engine and per-move capability, updates from outcomes
- **Energy model** — Energy levels, signals, decay, selector use
- **Runtime model** — Five move types (ask, reveal statement, reciprocity, filler, repair); decision priority; core rhythm
- **State diagram** — Session mode, persona selection, entry engine, turn loop with repair/reciprocity/curiosity and memory update
- **Persona network** — Persona data, selection, persona-consistent questions and memory

**Headline:** We have a working minimal conversation loop (selector with deterministic order, bridge, recovery, oxygen-loop probes, multi-engine flow). Everything beyond that—memory, persona, capability, energy, full turn contract, state machine, steering from content, scoring, hint-aware selector—is **not implemented**. The gap doc lists 11 “architectural elements not yet implemented” and recommends using it (and the specs) to guide what we build next.

---

## 2. What Phase 10 is in the plan

From **MANDARINOS_PROJECT_PLAN_v1.md**:

**Phase 10 — Memory + Persona**

- **Goal:** Make conversations personal and persistent.
- **Memory items:** name, hometown, job/study, family, favourite food.
- **Persona network:** Multiple characters that the learner can talk to.
- **Acceptance criteria:** Conversation feels continuous across sessions.

So Phase 10 is explicitly about **memory** and **persona**, not about implementing the entire runtime state engine, capability map, or energy model in one go.

---

## 3. Suggested path forward (Cursor’s view for your consideration)

The following is a proposed sequence so Phase 10 stays spec-aligned and deliverable without implementing every gap at once.

### 3.1 Prioritise memory and persona; keep scope bounded

- **Do in Phase 10:** Memory (minimal but real) and persona (as data + identity in the loop). Align with **MandarinOS_conversation_memory_model_v2.md** and **mandarinos_persona_network_relationship_pack_v1.md** (and the gap doc §6, §11).
- **Defer to a later phase:** Full capability map, energy model, steering (signal extraction from learner text), full turn data contract (response_mode, turn evaluation, selector_mode_next), explicit state machine, session modes, five-dimension scoring, hint-aware selector. These remain in the gap doc as the “next wave” after memory and persona are in place.

### 3.2 Recommended sequence for Phase 10

**Step 1 — Minimal memory (session + learner facts)**  
- Implement a **minimal** memory layer consistent with memory model v2:  
  - **Session memory:** What was said this session (we already have something like this via recent_frame_ids and client transcript; can formalise as “session memory” on server if useful).  
  - **Learner memory:** What the app “knows” about the learner: name, hometown, job/study, family, favourite food (and optionally a few more anchors).  
- Storage: In-memory for the session; optionally simple persistence (e.g. one JSON file or local storage keyed by learner/session) so “conversation feels continuous across sessions” can be validated.  
- **No need yet for:** Persona-specific learner memory, persona facts, or two-sided “what persona knows about learner” beyond a single global learner memory if that’s enough for v1.

**Step 2 — Persona as data (one or two personas)**  
- Introduce **persona_id** and a small set of **persona profiles** (stable facts: name, hometown, job, etc.) as in the persona network spec. Start with **one or two** personas, not the full network.  
- Use persona in the loop: e.g. stub answers (我们 already have probe stubs) and any “reveal statement” (e.g. 我老家在苏州) can be persona-specific.  
- **Turn contract / state:** Add **persona_id** (and optionally **memory_context** or a small memory snapshot) to the payload and to conversation state so the selector and responses can depend on “who we’re talking to.” This moves the turn contract and runtime state toward the spec without implementing the full state object or state machine.

**Step 3 — Wire memory and persona into the selector**  
- **Selector inputs:** Feed the selector (in `scripts/ui_server.py` or equivalent) with:  
  - **Memory:** What we already know about the learner (so we can avoid re-asking “你叫什么名字？” when we have a name, or ask a **memory recall** question occasionally, e.g. “你还喜欢成都吗？”).  
  - **Persona:** Current persona_id and persona profile (so we can choose or filter frames/stubs that fit the persona).  
- **Memory recall:** Implement a small set of **memory-recall** moves (e.g. one or two question patterns that reference a stored fact) so “conversation feels continuous” is visible.  
- **No need yet for:** Capability, energy, scoring, or hint-aware adjustment; those can build on top of memory + persona later.

**Step 4 — Persistence and “continuous across sessions”**  
- If not already done in Step 1, add **persistence** for learner memory (and optionally session or persona-related state) so that a later session can reuse “learner name”, “learner hometown”, etc.  
- Validate the Phase 10 acceptance criterion: **Conversation feels continuous across sessions** (e.g. app greets by name or asks a follow-up that references a past fact).

**Step 5 — Optional: extend state and contract only as needed**  
- As we add memory and persona, extend the **turn data contract** and **runtime state** only where necessary: e.g. persona_id, a small memory_context or recent_facts, and (if useful) a simple turn_type or selector_output_type for “memory recall” vs “simple question” vs “bridge.”  
- Defer full response submission (response_mode, hint_level_reached, repair_used, latency_ms) and full turn evaluation (success_level, capability_updates, energy_update, selector_mode_next) to a phase that introduces capability/energy.

### 3.3 What to avoid in Phase 10 (so we don’t get stuck)

- **Avoid** implementing the full **runtime state engine** (all states, state machine, response mode tracking, repair state transitions, selector modes) in one go.  
- **Avoid** implementing the **capability map** and **energy model** in Phase 10 unless you explicitly decide they are required for “conversation feels continuous across sessions.”  
- **Avoid** implementing **content-driven steering** (signal extraction from learner text to choose engine) in Phase 10; bridge-on-exhaust and “Change topic” are enough for now.  
- **Avoid** implementing the **full Next Question Selector** (five-dimension scoring, difficulty bands, hint-aware adjustment) in Phase 10; “selector uses memory and persona” is the goal.

---

## 4. What we’re asking from you (strategist)

1. **Review the gap doc**  
   Read or skim `docs/project/SPECS_TO_IMPLEMENTATION_GAP.md` and confirm whether the “implemented vs not implemented” picture matches your understanding. Note any spec or element you think should be re-prioritised.

2. **Validate or adjust the path**  
   Do you agree with the suggested sequence (minimal memory → persona as data → wire both into selector → persistence → optional contract/state extensions)? Would you add, drop, or reorder any step for Phase 10?

3. **Define Phase 10 acceptance criteria in more detail**  
   The plan says “Conversation feels continuous across sessions.” Should we make that concrete, e.g.:  
   - Within a session: app does not re-ask for name (or hometown, etc.) if it was already stated and stored.  
   - Across sessions: app recalls at least one learner fact (e.g. name or hometown) and uses it in greeting or a follow-up.  
   - Persona: at least one other “character” (persona) with stable facts, and at least one response (e.g. stub or reveal) that is persona-specific.  
   Any other criteria you want to set before implementation starts?

4. **Recommend next step**  
   After your review, recommend the next step: e.g. “Proceed with Step 1 (minimal memory) as above,” or “First add a one-page Phase 10 scope doc that locks Step 1–4 and defers the rest,” or “Adjust the sequence as follows: ….”

---

## 5. References

- **Gap analysis:** `docs/project/SPECS_TO_IMPLEMENTATION_GAP.md`  
- **Architecture index:** `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`  
- **Memory model:** `docs/specs/MandarinOS_conversation_memory_model_v2.md`  
- **Persona network:** `docs/specs/mandarinos_persona_network_relationship_pack_v1.md`  
- **Next question selector:** `docs/specs/MandarinOS_next_question_selector_v1.md`  
- **Project plan:** `docs/project/MANDARINOS_PROJECT_PLAN_v1.md` (Phase 10)

---

*This briefing was prepared by Cursor based on the SPECS_TO_IMPLEMENTATION_GAP assessment and the current codebase. It is intended to focus strategist discussion on Phase 10 scope and sequence, not to commit implementation without your approval.*
