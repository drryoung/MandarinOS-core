<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class E: Dated report or historical evidence**
>
> - **Current use:** Retained as the Phase 9 status and response-quality report.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current conversation code, current tests, `docs/CONVERSATION_ARCHITECTURE.md`, and `docs/ANSWER_SOURCE_CONTRACT.md`.
> - **Principal caution:** The document reflects Phase 9 observations and quality judgments. It does not describe or certify the current R2 conversation system.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Phase 9 status and response quality

**Purpose:** Record whether the current phase of development is complete and how to handle response validity / repeat-question issues.

---

## Phase 9 (Conversation Engine Activation) — what’s done

From **MANDARINOS_PROJECT_PLAN_v1.md**, Phase 9 goal: *Activate the Next Question Selector v1. Acceptance: engine switching works; conversation continues across topics; no conversational dead ends.*

| Item | Status |
|------|--------|
| Next Question Selector (minimal) | Done: deterministic ladder, same-engine order, exclude recent, frame dependencies |
| Engine switching (bridge) | Done: when engine exhausted or user clicks “Change topic” or recovery “next_turn” |
| Conversation continues across topics | Done: identity, place, family, work, hobby, food, travel, life |
| No dead ends | Done: when all engines exhausted, reuse least-recently-used question (Tier 2.5) instead of repeating same question |
| Sensible question order | Done: per-engine order, name before name meaning, etc. |
| Bridge as option + auto on recovery | Done: “Change topic” button; recovery next_turn sends prefer_bridge |
| Food engine | Done |
| Interests (hobby) expanded | Done: cultural, collecting, follow-ups |

So the **current phase of development (Phase 9)** is effectively **complete** for the minimal selector, engine switching, and no dead ends. The plan’s “inputs” (capability map, memory, energy, persona) are explicitly out of scope for Phase 9.1 and belong in Phase 10 or a later evolution.

---

## Issues you raised

### 1. Same question asked again — **fixed**

**What happened:** After exhausting work (你做什么工作？, 你喜欢你的工作吗？), the bridge had no unseen frame in other engines (identity, place, family were already used). The ladder fell back to Tier 3 and returned the current engine’s first question (你做什么工作？) again.

**Fix (in code):** Tier 2.5 now picks the **oldest frame from a different engine** (first in `recent_frame_ids` whose engine ≠ current). So "Change topic" and post-exhaust always switch topic when possible; only if every frame in recent is from the current engine do we fall back to oldest in session. This prevents the loop where 你做什么工作？ repeated when work was exhausted and Tier 2.5 had returned the oldest frame (which was still work if the user had started from that frame).

### 2. Responses not always valid — **for later refinement**

**Examples:** “我的名字有。” (incomplete), “家人”, “喜欢” — the system accepted them (we treat any “substantial” answer, e.g. 2+ characters, as enough to advance) so the conversation continued, but they are fragments or incomplete sentences.

**Design trade-off:** The design is “sustain conversation” and “no correct answer” — so we intentionally allow non-option answers to advance. That leads to:
- **Pro:** Conversation doesn’t stall when the user says something that doesn’t match an option.
- **Con:** Short or incomplete answers (e.g. “家人”, “喜欢”) are accepted and may look odd in the transcript.

**Possible later improvements (not required for Phase 9):**
- Raise the bar for “substantial” (e.g. 3+ characters, or require at least one full clause / option match for certain frames).
- Encourage full-sentence options: ensure every question has clear, tap-able full-sentence options (we already do this for many; family “你有家人吗？” still uses word options).
- Add sentence options for yes/no answers (e.g. “有，我有家人。” for “你有家人吗？”) so “家人” is less tempting.
- In a later phase, use capability/level to tailor options or acceptance.

Recommendation: **treat response validity as a Phase 9 polish / Phase 10 topic**, not a blocker for “phase complete.” We can add a short “Response quality” backlog item and refine in the next iteration.

---

## Summary

| Question | Answer |
|----------|--------|
| Have we finished the current phase of development? | **Yes.** Phase 9 (Conversation Engine Activation) is complete for the minimal selector, engine switching, no dead ends, bridge-as-option, and recovery→bridge. |
| Same question again? | **Fixed.** When the bridge finds no target, we now pick the least recently used question (cycle back to an earlier topic) instead of repeating the current engine’s first question. |
| Invalid / fragment responses? | **Documented for later.** We accept 2+ character “substantial” answers on purpose. Improving validity (full-sentence encouragement, higher bar, or option-match for some frames) can be a follow-up task. |

---

*Created 2026-03-12. Update when response-quality rules or Phase 10 scope change.*
