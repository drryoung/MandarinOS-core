# Phase 10 — Memory + Persona: Strategist Review Briefing

**Status:** **Approved and closed.**

**Sign-off summary:** Phase 10 — Memory + Persona Foundations delivered and approved. Scope: learner memory capture, persistence by learner_id, memory-aware selector suppression, persona data, persona-aware dialogue stubs, and cross-session continuity. Known follow-up: response-option quality / frame–option alignment (polish; does not block sign-off). Deferred to later phases: recall mode, capability map, energy model, repair logic, selector scoring, and broader adaptive intelligence.

---

**Purpose:** Pause for strategist review after implementing Phase 10 (Memory + Persona foundations). Implementation is complete through Step 7; Step 8 is this review.

**Date:** 2026-03-08  
**Context:** Learner memory (capture, persistence, memory-aware selector), persona data and persona-consistent stubs, and cross-session continuity are in place. The project owner reports that memory works and is ready for review, with one noted limitation (response options sometimes not appropriate).

---

## 1. What was delivered (Steps 1–7)

| Step | Deliverable |
|------|-------------|
| **1** | Learner memory schema (`scripts/learner_memory.py`): six fields (learner_name, hometown, lives_in, job_or_study, family, favourite_food), in-memory store. |
| **2** | Fact-capture (`scripts/learner_memory_capture.py`): map frame_id + selected option / submitted text → memory updates. ui_server calls capture after a response turn; client sends `last_answer` with next_question. |
| **3** | Persistence: `data/learner_memory.json` keyed by **learner_id**. Load on first access, save after updates. |
| **4** | Persona data (`scripts/persona_data.py`): schema + 2 personas (张伟 zhang_wei, 李明 li_ming). `get_persona(persona_id)`. |
| **5** | Memory-aware selector: suppress “ask for fact X” when we **already have X** (no re-ask in normal conversation). Re-asking reserved for future **drill mode** (`drill_mode` flag). |
| **6** | Persona-aware stubs: probe responses (为什么？, 哪里？, 怎么样？) use persona’s favourite_food, hometown, occupation. Request/response include `persona_id`. |
| **7** | Cross-session continuity: response includes `learner_memory`, `persona_id`, `turn_type`. UI shows “Remembered: …” when server sends learner_memory. Same learner_id across sessions → we skip questions we already have answers for. |

**Contract:** Client sends `learner_id`, `persona_id`, `last_answer` (when advancing after an answer). Client **never** sends learner_memory; server is authoritative. Response may include `learner_memory`, `persona_id`, `turn_type`.

---

## 2. Design decisions (for review)

- **Permanent suppression:** We do **not** re-ask for a fact once we have it (e.g. we won’t ask “你叫什么名字？” again). This keeps the conversation moving. A future “drill mode” can allow re-asking for practice.
- **Explicit recall:** No new recall frame_ids or text templates; we simply don’t repeat ask-for-fact questions. Dedicated recall frames (e.g. “你刚才说你来自{X}”) remain deferred.
- **Phase 6 lock:** No changes to `runtime/engine.py`, runtime artifacts, or trace contract. All Phase 10 logic is in `scripts/` and `ui/`.

---

## 3. Known limitation (project owner feedback)

**Response options for the latest questions are often not appropriate.**

Options are currently driven by `frame_options.runtime.json` (one set of options per frame_id). When the selector chooses a question, the UI shows that frame’s options; sometimes they don’t fit the question well or feel generic. This is a **content/option-quality** issue, not a memory or persona bug. Suggested follow-up: review option sets for the most-used frames, add or adjust options per question, or consider per-engine/per-question option refinement in a later phase.

---

## 4. Files touched (Phase 10)

| Added | Purpose |
|-------|---------|
| `scripts/learner_memory.py` | Schema, load/save, file persistence by learner_id. |
| `scripts/learner_memory_capture.py` | Frame_id + option/text → memory updates; `get_memory_field_for_frame` for selector. |
| `scripts/persona_data.py` | Persona schema, 2 personas, `get_persona`, `list_persona_ids`. |
| `data/learner_memory.json` | Persistence file (created on first save). |

| Modified | Changes |
|----------|---------|
| `scripts/ui_server.py` | Capture after turn; load/save memory; memory-aware selector; persona-aware probe stubs; response `learner_memory`, `persona_id`, `turn_type`. |
| `ui/app.js` | Send learner_id, persona_id, last_answer; “Remembered” line from response.learner_memory. |
| `ui/index.html` | “Remembered” div for cross-session display. |

---

## 5. What we suggest you do for review

1. **Confirm scope**  
   Phase 10 is memory + persona **foundations**: capture, persistence, selector suppression, persona stubs, cross-session continuity. Capability map, energy, scoring, large persona network remain deferred.

2. **Verify behaviour**  
   If possible: run a short flow (answer name/origin, restart or new session, same learner_id); confirm we don’t re-ask for name and “Remembered” appears; try a probe (为什么？) and confirm persona-specific stub (e.g. 小笼包 for 张伟).

3. **Note response-options limitation**  
   Acknowledge that “response options for the latest questions are often not appropriate” is a known content/option-quality follow-up, not a Phase 10 defect.

4. **Recommend next step**  
   After sign-off: Phase 10 polish (option quality / frame–option alignment), Phase 11 (per plan), or personal alpha with current behaviour and iterate.

---

## 6. References

| Document | Use |
|----------|-----|
| `docs/phases/PHASE10_TECHNICAL_PROPOSAL.md` | Full proposal, §0 adjustments, schemas, deferred items. |
| `docs/project/MandarinOS_project_plan_v2.md` | Roadmap and phase order. |
| `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` | No changes to runtime. |

---

**Request:** Please review this briefing and the proposal, then advise: (1) whether Phase 10 can be signed off as complete, (2) any conditions or follow-ups (including response-option quality), and (3) recommended next step (polish, Phase 11, or alpha test).
