# Probe questions and sensible response options — following the conversation architecture

**Purpose:** Document the gap between current behaviour and the design. The **conversation architecture** already defines probe-style follow-ups (**oxygen loop questions**, **Curiosity** layer, **curiosity capability**). Response options do not yet offer these to the learner. This note aligns with the architecture and describes what is missing and what would be needed to implement it (now or in Phase 10).

---

## 1. Conversation architecture (design authority)

Probe behaviour must follow these documents.

- **Blueprint** ([MandarinOS_conversation_system_blueprint_v1.md](../specs/MandarinOS_conversation_system_blueprint_v1.md))  
  Layers: **Engines → Curiosity → Fillers → Repair → Memory → Persona**. The **Curiosity** layer is where learner follow-ups (e.g. 为什么？, 谁？, 哪里？) and curiosity triggers live.

- **Architecture index** ([CONVERSATION_ARCHITECTURE_INDEX.md](../archive/specs/CONVERSATION_ARCHITECTURE_INDEX.md))  
  Single entry point for conversation design; points to ladders (oxygen loop questions), curiosity engine, emergency curiosity pack, selector, capability map.

- **Conversation ladder model** ([mandarinos_copilot_architecture_update.txt](../directives/mandarinos_copilot_architecture_update.txt))  
  Each engine: Opener → Core → Treasure → **Oxygen loops** (short reusable follow-ups) → Bridge. "Oxygen loops" are the canonical reusable probe set.

- **Ladders spec** ([MandarinOS_conversation_ladders_full_draft_v2.md](../archive/specs/MandarinOS_conversation_ladders_full_draft_v2.md))  
  Defines **OXYGEN LOOP QUESTIONS** per engine. Use this as the **canonical probe set**:

  | Phrase        | Pinyin / meaning     |
  |---------------|----------------------|
  | 为什么？      | Why?                 |
  | 谁？          | Who?                 |
  | 什么时候？    | When?                |
  | 哪里？        | Where?               |
  | 怎么样？      | How is it?           |
  | 喜欢吗？      | Do you like it?      |
  | 跟谁一起？    | With whom?           |
  | 什么时候开始？| When did it start?   |

- **Next Question Selector v1** ([MandarinOS_next_question_selector_v1.md](../archive/specs/MandarinOS_next_question_selector_v1.md))  
  Output types include **B. Follow-up question** (e.g. 为什么？). Candidate generation uses the **curiosity toolkit**. Follow-up/probe is a first-class move type; the selector (or a sibling "option selector") should eventually drive when the **learner** is offered probe options.

- **Capability map** ([MandarinOS_conversation_capability_map_v1.md](../specs/MandarinOS_conversation_capability_map_v1.md))  
  **Curiosity capability** = learner's ability to keep the conversation alive with 为什么？, 怎么样？, 你推荐吗？, etc. Offering oxygen loop questions as response options implements this from the UI side.

- **Curiosity engine** ([mandarinos_curiosity_engine_v1.md](../specs/mandarinos_curiosity_engine_v1.md))  
  When new/unfamiliar information appears, the learner should be able to probe (为什么？, 难吗？, etc.). Emergency Curiosity loop: Unknown thing → What is it? → What do you mainly do? → Is it difficult? → Why?

- **Emergency curiosity pack** ([mandarinos_emergency_curiosity_pack_v1.md](../specs/mandarinos_emergency_curiosity_pack_v1.md))  
  Core beginner questions: 这是什么？, 什么意思？, 你主要做什么？, 难吗？, 为什么？, 像什么？; plus follow-ups (可以再说一次吗？, 可以慢一点吗？, etc.). Use for P1 probe options alongside oxygen loop questions where appropriate.

- **Engine specs** ([MandarinOS_engine_specs_v1.md](../archive/specs/MandarinOS_engine_specs_v1.md))  
  Each engine defines Loop questions [L] (e.g. 为什么？, 谁？, 哪里？, 跟谁一起？); these align with the ladder's oxygen loop list.

---

## 2. Current behaviour (gap)

- **Response options** are built **per partner frame** (the question the app just asked) from `frame_options.runtime.json` (word cards or `QUESTION_FRAME_SENTENCE_OPTIONS` in the builder). The user only sees **answer options** (e.g. 我叫X, 喜欢, etc.).
- There is **no** logic or UI that offers **oxygen loop questions** (or emergency curiosity phrases) as response choices so the learner can **ask back** (为什么？, 谁？, 哪里？, etc.). The **Curiosity** layer and **curiosity capability** are not yet implemented from the response-option side.

Result: the app does not "seize opportunities" to offer these architecture-defined probes, and the learner cannot easily turn the conversation and dig deeper.

---

## 3. What a probe / response-options module would do (aligned with architecture)

Implementing the **Curiosity** layer from the learner side: offer **oxygen loop questions** (and optionally emergency curiosity phrases) as response choices when context allows.

1. **Probe phrase set**
   - Use the **canonical set** from the ladders spec (OXYGEN LOOP QUESTIONS above). Optionally add emergency curiosity phrases (这是什么？, 什么意思？, 难吗？, 你主要做什么？, etc.) for P1. Each phrase has an id (e.g. `probe_weishenme`, `probe_shei`) and optional link to a "persona answer" frame or stub for Phase 10.

2. **When to offer probe options**
   - **Context rules:** After certain partner frames (or answer types), the system decides that probe options are available. Examples: after "why"-inviting content → 为什么？; after person mention → 谁？ or 跟谁一起？; after place mention → 哪里？. Can be a mapping (last_partner_frame_id or engine → probe_ids) or a **selector extension** (next-question selector or "option selector" returns suggested response options including 1–2 probes when appropriate), per Next Question Selector v1 and curiosity toolkit.

3. **Option composition**
   - For each turn, **options** = (current frame's answer options) **plus** (0–2 probe options when context allows). Or a separate "Ask back" area (你也可以问：为什么？ / 谁？ / 哪里？). When the user selects a probe, the turn records the probe as the user's message; the next system move is either a **persona answer to that probe** (Phase 10) or a generic follow-up / next question.

4. **Turn handling**
   - User taps a probe (e.g. 为什么？) → client sends as user's response (e.g. with `probe_id` or `frame_id`). **Minimal (now):** next move = next question or a fixed "answer to 为什么？" stub. **Phase 10:** map probe to a persona-appropriate answer frame so the conversation stays coherent.

---

## 4. Implementation options

| Approach | When | Scope |
|----------|------|--------|
| **A. Probe options in option set** | Phase 9 polish / pre–Phase 10 | Use **oxygen loop** list from ladders; for selected frames/engines, append 1–2 probe options so the user can answer or ask 为什么？/ 谁？/ 哪里？. Next move = next question or one stub answer. |
| **B. "Ask back" panel** | Phase 9 polish | Same data; UI shows a separate row/panel (你也可以问：为什么？ 谁？ 哪里？) when context allows. No change to existing frame_options build. |
| **C. Full option selector** | Phase 10 | Option set (including probes) chosen by the backend per turn (conversation state + engine + last answer + persona). Enables persona-appropriate probes and persona answers to probes. |

---

## 5. Recommendation

- **Follow the conversation architecture:** oxygen loop questions (ladders), Curiosity layer (blueprint), Follow-up output type and curiosity toolkit (selector), curiosity capability (capability map). Treat probe options as implementing the **Curiosity** layer from the response-option side.
- **Short term (Phase 9 polish):** Implement **A** or **B** using the **canonical oxygen loop list** (为什么？, 谁？, 什么时候？, 哪里？, 怎么样？, 喜欢吗？, 跟谁一起？, 什么时候开始？) and simple context rules; on probe tap, send as user message and advance with next question or one stub answer.
- **Phase 10:** Integrate with persona and memory: probe options and "when to show" driven by persona/context; persona answers to probes so the conversation stays sensible and personal.

---

## 6. References (architecture-first)

- [CONVERSATION_ARCHITECTURE_INDEX.md](../archive/specs/CONVERSATION_ARCHITECTURE_INDEX.md) — entry point; ladders, curiosity, selector, capability.
- [MandarinOS_conversation_system_blueprint_v1.md](../specs/MandarinOS_conversation_system_blueprint_v1.md) — Curiosity layer.
- [MandarinOS_conversation_ladders_full_draft_v2.md](../archive/specs/MandarinOS_conversation_ladders_full_draft_v2.md) — **OXYGEN LOOP QUESTIONS** (canonical probe set).
- [mandarinos_copilot_architecture_update.txt](../directives/mandarinos_copilot_architecture_update.txt) — oxygen loops in ladder model.
- [MandarinOS_next_question_selector_v1.md](../archive/specs/MandarinOS_next_question_selector_v1.md) — Follow-up question, curiosity toolkit.
- [MandarinOS_conversation_capability_map_v1.md](../specs/MandarinOS_conversation_capability_map_v1.md) — curiosity capability.
- [mandarinos_curiosity_engine_v1.md](../specs/mandarinos_curiosity_engine_v1.md) — when learner can probe.
- [mandarinos_emergency_curiosity_pack_v1.md](../specs/mandarinos_emergency_curiosity_pack_v1.md) — beginner probes.
- [MandarinOS_engine_specs_v1.md](../archive/specs/MandarinOS_engine_specs_v1.md) — Loop [L] per engine.
- [ARCHITECTURE_ALIGNMENT_OPTIONS_AND_GOLD.md](ARCHITECTURE_ALIGNMENT_OPTIONS_AND_GOLD.md) — current option/gold design.
- `tools/build_runtime_artifacts.py` — `build_frame_options`; no probe layer yet.

*Created 2026-03. Updated to follow conversation architecture; oxygen loop questions from ladders spec. Update when probe module is scoped or implemented.*
