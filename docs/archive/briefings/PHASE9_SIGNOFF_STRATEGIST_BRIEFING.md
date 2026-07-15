# Phase 9 Sign-Off Briefing for ChatGPT (Strategist)

**Purpose:** Prepare you to evaluate and recommend sign-off for **Phase 9 — Conversation Engine Activation**. The project owner is seeking your sign-off before moving to Phase 10 (Memory + Persona) or to personal alpha testing.

**Date:** 2026-03-12  
**Context:** Cursor has implemented the minimal Next Question Selector, engine switching (bridge), and conversation flow across all seven engines. This briefing summarises what was built, how it maps to the plan, and what to verify.

---

## 1. Phase 9 in the project plan

From **MANDARINOS_PROJECT_PLAN_v1.md**:

**Goal:** Activate the Next Question Selector v1.

**Inputs (listed in plan):** conversation state — capability map — memory — energy model — persona data  

**Outputs:** follow‑up question — bridge to another topic — repair move — curiosity prompt  

**Acceptance criteria:**  
- Engine switching works  
- Conversation continues across topics  
- No conversational dead ends  

**Scope note:** Phase 9.1 acceptance criteria (see `docs/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md`) explicitly scope the *first* step to a **minimal** selector: deterministic, same-engine only, no capability/memory/energy. The plan’s “inputs” beyond conversation state are therefore **out of scope** for this phase and reserved for Phase 10 or a later evolution of the selector.

---

## 2. What was delivered (summary for sign-off)

| Deliverable | Implementation |
|-------------|----------------|
| **Next Question Selector (minimal)** | Server chooses next partner-question frame from conversation state. Deterministic order per engine; excludes recently used frames; respects frame dependencies (e.g. name before name meaning). |
| **Engine switching (bridge)** | When the current engine has no unused partner questions, the selector bridges to another engine (place → food, work → identity, etc.). Bridge map and per-engine question order are defined in `scripts/ui_server.py`. |
| **No dead ends** | When *all* engines have been used (bridge finds no unseen frame), the next question is the **least recently used** in the session (oldest in `recent_frame_ids`), so the conversation cycles back to an earlier topic instead of repeating the same question. |
| **Bridge as user option** | “Change topic” button in the UI. When used, the next request sends `prefer_bridge: true`; the server tries bridge first, then falls back to same-topic if no bridge target. |
| **Bridge on recovery (too hard)** | When the user selects a recovery phrase with `recovery_action: "next_turn"` (e.g. 我们聊点简单的吧, or after several “not understood”), the next turn sends `prefer_bridge: true`, so the next question is from another topic. |
| **Conversation continues across topics** | Seven engines are active: identity, place, family, work, hobby (interests), travel, food, plus life. Full-sentence response options are built for key questions (name, name meaning, place, work, hobby, travel, food). |
| **Sensible question order** | Per-engine order and dependencies (e.g. 你叫什么名字？ before 你的名字是什么意思？; place: 哪里人 → 喜欢那儿吗？ → 住哪里). |
| **Food engine** | Added per spec: 那儿有什么好吃的？, 最有名的菜, 喜欢吃辣吗？, 好吃吗？, 贵不贵？ with sentence options and bridge targets. |
| **Interests (hobby) expanded** | Per spec: 你喜欢做什么？, 你周末做什么？, 你常做吗？, 难吗？, 你推荐吗？, 你喜欢中国文化吗？, 你喜欢什么？ (cultural), 你收藏什么吗？ (collecting), plus P2 curiosity frames; sentence options and cultural/collecting fillers. |

**Key files:**  
- Selector and bridge: `scripts/ui_server.py` (`_select_next_frame_ladder`, `_select_next_frame_bridge`, `_FRAME_ORDER`, `_BRIDGE_TARGETS`, `_FRAME_AFTER`).  
- UI: `ui/app.js` (runTurn with `next_question` and `conversation_state`; “Change topic” and recovery→prefer_bridge).  
- Frames and options: `p1_frames.json`, `p2_frames.json`, `p1_fillers.json`, `tools/build_runtime_artifacts.py` (QUESTION_FRAME_SENTENCE_OPTIONS).

---

## 3. Acceptance criteria vs implementation

| Criterion | Met? | How |
|-----------|------|-----|
| Engine switching works | Yes | Bridge tier in selector; “Change topic” and recovery next_turn send prefer_bridge; server tries bridge then ladder. |
| Conversation continues across topics | Yes | All seven engines used; bridge and exhaust handling move across identity, place, family, work, hobby, travel, food, life. |
| No conversational dead ends | Yes | Exhaust: bridge; if bridge empty, Tier 2.5 returns least-recently-used frame (no immediate repeat of same question). |

Phase 9.1 “out of scope” (no engine switching in first pass) was superseded by Phase 9.2 bridge tier and the current behaviour; the plan’s Phase 9 acceptance criteria are satisfied.

---

## 4. Scope boundaries (for your review)

- **In scope for this phase:** Conversation state (current_engine, last_partner_frame_id, recent_frame_ids), minimal deterministic selector, bridge, frame order/dependencies, no dead end, bridge as option and on recovery.  
- **Out of scope (deferred):** Capability map, memory, energy model, persona data, scored/adaptive selector, random selection, auto-advance. These align with Phase 10 or “Phase 9 evolution” in the architecture docs.  
- **Design alignment:** No “correct” answer; options are suggested responses; “gold” is internal only (see `docs/project/ARCHITECTURE_ALIGNMENT_OPTIONS_AND_GOLD.md`). Conversation is sustained for as long as the user’s vocabulary allows.

---

## 5. Known limitations and deferred items

1. **Response validity**  
   Short or incomplete answers (e.g. “家人”, “喜欢”, “我的名字有。”) are accepted as “substantial” (2+ characters) so the conversation does not stall. This is intentional (sustain conversation, no right/wrong) but can look odd in the transcript. Improving this (e.g. full-sentence options for family yes/no, or a higher bar for “substantial”) is documented as Phase 9 polish / Phase 10 backlog in `docs/project/PHASE9_STATUS_AND_RESPONSE_QUALITY.md`.

2. **Explicit core/treasure/loop**  
   Frames are not tagged with question_type (core/treasure/loop). Order is fixed per engine, not by type. Richer “core → treasure → bridge” with tags is planned for a later step (Phase 9 Content & Engines Plan, step 3).

3. **SRS / level / capability**  
   No integration with SRS (spaced repetition), level assessment, or capability map. See `docs/project/NEXT_QUESTION_SELECTOR_AND_LEVEL_TIE_IN.md` and `docs/project/ENGINES_P1_P2_AND_SRS_REFERENCE.md` for when those tie in (Phase 10+).

---

## 6. What we suggest you do for sign-off

1. **Confirm scope**  
   Confirm that Phase 9 sign-off is for the **minimal** selector (conversation state + deterministic order + bridge + no dead end), with capability/memory/energy/persona explicitly deferred.

2. **Verify acceptance**  
   Satisfy yourself that the three plan criteria (engine switching, conversation across topics, no dead ends) are met from the description above and, if possible, from a short manual run (Next, Change topic, recovery “next_turn”, exhaust one engine then another).

3. **Decide on response quality**  
   Either accept “response validity” as a known limitation and backlog item for the next phase, or request one or two targeted improvements (e.g. full-sentence options for “你有家人吗？”) before sign-off.

4. **Recommend next step**  
   After sign-off, recommend the next step: e.g. Phase 10 (Memory + Persona), or a short Phase 9 polish sprint (response quality / core–treasure tagging), or move to Phase 11 (Personal Alpha Testing) with current behaviour and iterate from there.

---

## 7. References for deeper review

| Document | Use |
|----------|-----|
| `docs/project/MANDARINOS_PROJECT_PLAN_v1.md` | Phase 9 goal and acceptance criteria |
| `docs/project/PHASE9_STATUS_AND_RESPONSE_QUALITY.md` | What’s done, repeat-question fix, response validity |
| `docs/project/CORE_TREASURE_BRIDGE_STATUS.md` | Bridge as option, auto on exhaust and recovery |
| `docs/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md` | Original 9.1 scope (minimal selector) |
| `docs/specs/MandarinOS_next_question_selector_v1.md` | Full selector spec (for later; we implemented minimal) |
| `docs/project/ENGINES_P1_P2_AND_SRS_REFERENCE.md` | Seven engines, P1/P2, SRS tie-in |
| `docs/project/ARCHITECTURE_ALIGNMENT_OPTIONS_AND_GOLD.md` | No correct answer; gold = internal only |

---

**Request:** Please review this briefing and the referenced docs, then advise: (1) whether Phase 9 can be signed off as complete, (2) any conditions or small follow-ups you recommend, and (3) what the project owner should do next (Phase 10, polish, or alpha test).
