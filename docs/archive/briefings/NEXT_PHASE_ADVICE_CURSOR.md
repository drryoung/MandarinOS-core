# Next Phase Advice — Cursor (Senior Architect)

**Date:** 2026-03-08  
**Context:** You updated AI_CONTEXT.md with references to the project plan (`docs/project/MANDARINOS_PROJECT_PLAN_v1.md`) and architecture map (`docs/design/MANDARINOS_ARCHITECTURE_MAP.png`). You want to know: (1) what phase to do next, (2) whether continuing from where you left off with Copilot is sensible, (3) whether I agree with ChatGPT’s strategic direction and if there are sensible refinements.

**Sources used:** AI_CONTEXT.md, MANDARINOS_PROJECT_PLAN_v1.md, PHASE6_RUNTIME_ARCHITECTURE_LOCK.md, UI_CONVERSATION_LOOP_ASSESSMENT.md, Phase 7 handoff directive, MANDARINOS_SYSTEM_MAP.md, CURSOR_STARTUP_PROTOCOL.md.

---

## 1. Do I agree with the overall direction?

**Yes.** The roadmap (Phase 7 → 8 → 9 → 10 → 11 → 12 → 13) is sound and matches the repo state.

- **Phase 7 (Learning Interaction Layer)** before **Phase 8 (Conversation Loop UI)** is correct: single-turn “see question, get hints, pick answer” should be solid before adding transcript, statement, reciprocity, and next-question flow.
- **Phase 8** before **Phase 9 (Conversation Engine Activation)** is correct: the UI must show the full loop (Question → Answer → Statement → Reciprocity → Next question) before wiring the Next Question Selector to drive that loop.
- **Phase 9** before **Phase 10 (Memory + Persona)** is correct: selector and engine switching can use in-session state first; persistence and persona network can follow.
- Phases 11–13 (alpha, beta, iteration) are the right sequence for validation and data-driven change.

No change to the **order** of phases is recommended.

---

## 2. Is it sensible to continue from where you left off with Copilot?

**Yes.** Continuing from the Copilot stopping point is sensible and consistent with the plan.

- **Phase 6** is frozen (runtime lock). No runtime behaviour changes; builders and UI are the allowed surface. The project plan and phase lock agree.
- **Phase 7.3 (clickable words)** from the handoff directive is effectively done: frame_render_tokens, clickable word tokens, open-card from sentence, hint cascade, response options are in place. That was the last Copilot-era objective.
- The **project plan’s Phase 7** is slightly broader than 7.3: it adds “You said” confirmation and implies stable hints and response options (done). So “continuing from Copilot” means: **finish the rest of Phase 7**, then **Phase 8**.

Sticking with the same phase numbering and the same constraints (no runtime changes, builder + UI only, small steps) keeps continuity and avoids drift.

---

## 3. Recommended next step (phase)

**Next step: complete Phase 7, then start Phase 8.**

### 3.1 Complete Phase 7 (remaining items)

Phase 7 in the plan is: frame display, word→card, hint cascade, response options, **“You said” confirmation**.

- **Already in place:** frame display, word→card (clickable tokens), hint cascade, response options, trace (e.g. OPTION_SELECTED).
- **Missing for Phase 7:**
  - **“You said” confirmation** — After the user selects an option, show a clear confirmation of what they “said” (e.g. a line like “You: 我叫 Raymond.” or “You said: [selected option text]”). This can be a single UI element (e.g. under the options or in a small “last response” area) and does not require a full transcript yet. One small, reviewable change.

**Optional but recommended in Phase 7:** **Play question (TTS for frame sentence)** — A control (e.g. button or icon) next to the frame sentence that speaks the current question via TTS. AI_CONTEXT and the conversation design both expect the learner to hear the question; adding it in Phase 7 keeps “learning interaction” complete (see + hear question, respond, see “You said”) before Phase 8 adds the full loop.

So the concrete next steps are:

1. Implement **“You said” confirmation** (one small UI change, no runtime change).
2. Optionally implement **Play question** (TTS for frame sentence) in the same spirit.
3. Treat Phase 7 as **done** when those are in place and reviewed.

### 3.2 Then start Phase 8 (Conversation Loop UI)

Phase 8 in the plan: **Conversation transcript panel**, partner acknowledgement (statement), reciprocity turn (你呢？), question audio, turn markers.

- This matches what **UI_CONVERSATION_LOOP_ASSESSMENT.md** listed as missing: transcript, statement phase, reciprocity phase, and (if not done in Phase 7) question audio.
- Phase 8 can be broken into small steps, for example:
  - Add a **transcript panel** (append-only list of “Partner: …” / “You: …”).
  - Wire **option selection** to append “You: [selected text]” and, when data exists, “Partner: [statement]” and “Partner: 你呢？”.
  - Add **turn markers** and, if not already in Phase 7, **question audio**.

Statement and reciprocity **content** can be frame-linked or static at first (e.g. from frame metadata or a small lookup). Phase 10 (Memory + Persona) can later drive personalised statement/reciprocity; Phase 8 only needs the UI and a minimal data shape so the loop is visible and testable.

---

## 4. Refinements to the overall direction

Small refinements that keep the strategy intact but make execution clearer:

1. **Phase 7 scope**
   - Explicitly include **“Play question” (TTS for frame sentence)** in Phase 7 so the learner can hear the question in the same phase where they see it and respond. That way Phase 7 fully covers “learning interaction” (see + hear question, respond, see “You said”) and Phase 8 can focus on multi-turn flow and transcript.

2. **Phase 8 data**
   - State that **statement** and **reciprocity** (你呢？) can be implemented with **frame-linked or static content** first (e.g. optional fields on frame or a tiny lookup). Full memory/persona (Phase 10) is not required for Phase 8; the UI and a minimal content contract are enough to validate the loop.

3. **Phase 9 dependency**
   - Phase 9 (Next Question Selector) will need **conversation state** and a way for the UI to request “next turn” from the backend. Phase 8 should leave a clear hook for “request next” (e.g. after reciprocity or after “You said”) so Phase 9 can replace manual frame-pick with selector-driven next question without reworking the UI flow.

4. **Implementation discipline**
   - The plan already says: one feature at a time, minimal files, stop after each change for review. That matches AI_CONTEXT and the Design Constitution. No change to the plan’s “Implementation Discipline” section is needed; just keep following it.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| **Agree with ChatGPT’s direction?** | Yes. Phase order 7→8→9→10→… is correct. |
| **Continue from where Copilot left off?** | Yes. Phase 6 stays frozen; complete Phase 7 (builder + UI), then Phase 8. |
| **Recommended next step?** | **Complete Phase 7** with “You said” confirmation (and optionally “Play question”), then **start Phase 8** (transcript, statement, reciprocity, turn markers). |
| **Refinements?** | (1) Add “Play question” to Phase 7. (2) Allow frame-linked/static statement and reciprocity in Phase 8. (3) Keep Phase 8 UI ready for a “next turn” hook for Phase 9. |

No code was modified; this is advice only. When you are ready to implement, the next concrete task is: **add “You said” confirmation after option selection** (one small UI change, then review).
