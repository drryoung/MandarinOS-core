# Next Question Selector vs current implementation, and when level / SRS tie in

**Purpose:** Clarify (1) whether we should be implementing the full "next most sensible question" spec now, and (2) when SRS (spaced repetition system), level assessment, and options-at-user-level tie in.  
**Audience:** Project owner and implementers.

---

## 1. The "next most sensible question" spec — what we have

The design doc is **MandarinOS Next Question Selector v1** (`docs/specs/MandarinOS_next_question_selector_v1.md`), marked **LOCKED**.

It defines the **full** selector:

- **Inputs:** conversation state, capability map, energy model, memory, persona data, learning constraints
- **Process:** candidate generation → **hard filters** (recently asked, too difficult for capability, etc.) → **scoring** (comprehensibility, relevance, interest, learning, stretch) → select
- **Output types:** simple question, follow-up, bridge, recovery, repair, memory recall
- **Engine switching:** when learner stalls, energy drops, natural bridge exists, or another engine has higher capability

So the "next most sensible question" is the **full** Next Question Selector: not just order and dependencies, but **scored** choice using capability, energy, and memory.

---

## 2. What we're implementing now (Phase 9.1 / 9.2)

Phase 9.1 acceptance criteria (`docs/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md`) explicitly define a **minimal** version:

- **Selector:** Next frame **within current engine only**, **deterministic** order, exclude `recent_frame_ids`; fallback to repeat if all used.
- **Out of scope for 9.1:** engine switching, capability, memory, energy, persona.

Phase 9.2 added:

- **Bridge tier:** when all frames in current engine are used, switch to another engine (new topic) instead of repeating.

What we added on top (sensible order + dependencies):

- **Per-engine order** (`_FRAME_ORDER`): e.g. identity = name → name meaning; place = from where → like there? → where live.
- **Frame dependencies** (`_FRAME_AFTER`): e.g. don’t ask "你的名字是什么意思？" until "你叫什么名字？" has been asked.

So **right now we are implementing the minimal, deterministic ladder** that Phase 9.1/9.2 describe — **not** the full Next Question Selector (no scoring, no capability, no energy, no memory).

---

## 3. Should we implement the full Next Question Selector now?

**Recommendation: no — not yet.**

- The **project plan** (Phase 9) says: activate the Next Question Selector v1; acceptance criteria are engine switching and no dead ends. The **Phase 9.1 doc** deliberately limits scope to "smallest safe version" and leaves capability/memory/energy out.
- The **CONVERSATION_ARCHITECTURE_ASSESSMENT** says the full selector is "clear and sufficient to implement **when the time is right**."
- Implementing the full selector would require:
  - **Capability map** (per-engine / per-move capability)
  - **Energy model** (momentum, hint burden, engagement)
  - **Memory** (what was asked, facts shared)
  - Candidate generation beyond "all partner questions in engine"
  - Hard filters (e.g. "too difficult for current capability")
  - Scoring and selection by comprehensibility, relevance, interest, learning, stretch

That’s a larger step. The plan’s next steps are:

- **Phase 9 Content & Engines Plan:** more content, new topics (e.g. Food), richer engine logic (e.g. question_type / Core–Treasure–Loop), then iterate.
- **Phase 10:** Memory + persona foundations.

So: **staying with the current minimal selector and moving on to other conversation engines (more content, new topics, question_type/order)** is consistent with the design. The **full** "next most sensible question" selector (scoring, capability, energy, memory) fits **after** we have capability/memory data and stable engines — e.g. Phase 9 evolution or Phase 10.

---

## 4. When do SRS, level assessment, and options-at-user-level tie in?

### 4.1 SRS (spaced repetition system)

**SRS** is the spaced-repetition system in MandarinOS. It uses the **SM2** (SuperMemo 2) algorithm. Relevant files:

- `srs_config.json` (e.g. `grade_to_sm2_q`, `sm2` parameters)
- `pack_meta.json` (`sm2_config`)
- `docs/design/MandarinOS_brief.md` — "SM-2 spaced repetition engine (Anki-style)"

**When it ties in:** The Next Question Selector v1 spec lists **learning constraints** as an input, including "anchor phrases due" and "vocabulary budget" — i.e. what should be reinforced or reviewed. The **SRS** (via SM2) drives *when* a word or phrase is "due"; the selector could then prefer questions that surface those items. So SRS ties in when we:

1. Feed SRS "due" data into conversation state or learning constraints, and
2. Let the selector (or a later, fuller version) use that to favour questions that reinforce due items.

That is **Phase 10 (Memory + Persona)** or a later learning-integration step — not required for the minimal selector or for "other conversation engines" now.

### 4.2 Level assessment

In the **Next Question Selector v1** spec, "level" is represented as **capability**, not a single global level:

- **Capability map** (`MandarinOS_conversation_capability_map_v1.md`): per-engine and per-move capability, curiosity, repair; used by the selector.
- **Hard filters:** e.g. "too difficult for current capability" — so the selector **would** use level/capability once it exists.
- **Master bootstrap context:** "Learners are not assigned levels" in a simple sense; the system tracks **conversation capability** (uneven across engines/moves).

So "level assessment" ties in when:

1. We have a **capability map** (or a simpler placement/level signal) that the backend or UI can compute/update.
2. The **selector** (or a later version of it) uses that to filter candidates ("too difficult for current capability") and optionally to score comprehensibility/stretch.
3. Optionally, **recovery phrases** and **options** are filtered by level (see RECOVERY_AND_CONVERSATION_FUTURE_NOTES: "Filter or sort recovery options by the learner's current level").

Right now we have **no capability map and no level** in the server or UI; the minimal selector does not take level into account. So level assessment ties in **when we implement the capability map (or a simpler level) and plug it into the selector and/or options**.

### 4.3 Display of options at the user’s level

- **Current behaviour:** Options are built by the **builder** from frames + fillers (e.g. sentence options for mapped questions); the **server** returns the same options for everyone for a given frame.
- **Design (Phase 8 / 9):** PHASE8_OPTIONS_APPROPRIATENESS says: in Phase 9 the engine can return **per-turn options** (e.g. one gold + plausible distractors), and option quality can be **adaptive (e.g. by user level)**.
- **Selector spec:** Hard filter "too difficult for current capability" and hint-aware adjustment (shorter sentences, less lexical complexity after heavy hint use) imply that **questions and, by extension, options** can be level-aware once capability exists.

So **options at the user’s level** tie in when:

1. We have a **level or capability** signal (from placement, assessment, or capability map).
2. Either:
   - The **server/selector** returns options that are filtered or chosen by level for that turn, and the UI just displays what the server sends, or
   - The **builder** produces level-tagged options and the **UI or server** filters by user level, or
   - We add a **runtime layer** that, given frame + user level, picks a subset of options (e.g. from a level-indexed option set).

None of this is in place yet; it’s the natural next step **after** we have a level/capability signal and decide whether filtering happens in the selector, the builder, or the UI.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| **Should we implement the full "next most sensible question" (Next Question Selector v1) spec now?** | **No.** We’re correctly implementing the **minimal** selector (Phase 9.1/9.2): deterministic order, exclude recent, bridge when exhausted, sensible order + dependencies. The **full** selector (scoring, capability, energy, memory) should come **after** more engines/content and when we have capability/memory (e.g. Phase 9 evolution / Phase 10). |
| **What’s the actual name of the design doc?** | **MandarinOS Next Question Selector v1** (`docs/specs/MandarinOS_next_question_selector_v1.md`), LOCKED. |
| **When do we tie in SRS (spaced repetition)?** | When we feed SRS "due" data into **learning constraints**. **Phase 10 or later.** See §4.1 above. |
| **When do level assessment and options-at-user-level tie in?** | When we have a **level/capability** signal (placement, assessment, or capability map). Then: (1) selector can filter/score by capability, (2) options can be chosen or filtered by level (server, builder, or UI). Right now we don’t have that signal; the minimal selector and current options are level-agnostic. |

---

*Created 2026-03-12. Updated: SRS (spaced repetition) tie-in; update when capability/level is implemented.*
