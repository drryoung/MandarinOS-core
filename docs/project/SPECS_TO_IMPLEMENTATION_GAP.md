# Specs vs implementation — architectural gap analysis

**Purpose:** Compare the conversation architecture defined in `docs/specs/` with the current implementation so development can be guided by the spec files rather than piecemeal. This document lists what each key spec requires and what is **implemented** vs **not implemented**.

**References:** [CONVERSATION_ARCHITECTURE_INDEX.md](../specs/CONVERSATION_ARCHITECTURE_INDEX.md) is the single entry point for all conversation design docs.

---

## 1. MandarinOS Turn Data Contract v1

**Spec:** `MandarinOS_turn_data_contract_v1.md`

| Element | Spec | Implemented? |
|--------|------|--------------|
| **Prompt payload (Runtime → UI)** | turn_id, session_id, persona_id, engine_id, branch_id, turn_type, prompt_text_hanzi, prompt_audio_url, prompt_pinyin, prompt_translation, word_items[], candidate_options[] | **Partial.** We have frame_id, engine_id, frame_text, frame_pinyin, frame_text_en, options. Missing: turn_id (we use turn_uid), persona_id, branch_id, turn_type, word_items as first-class, prompt_audio_url. |
| **Response option structure** | option_id, hanzi, audio_url, pinyin, translation, word_items[], is_gold | **Partial.** Options have card_id, hanzi, pinyin, meaning, is_gold. Missing: option_id, audio_url, word_items[] per option. |
| **UI event payload (UI → Runtime)** | event_type, turn_id, timestamp, payload; PROMPT_RENDERED, AUDIO_PLAYED, HINT_LEVEL_OPENED, OPTION_SELECTED, FREE_SPEECH_SUBMITTED, REPAIR_USED, TURN_COMPLETED | **Partial.** Trace/emit events exist in UI but are not sent to server as the contract’s “UI event payload”; server does not consume event log. |
| **Response submission payload** | turn_id, response_mode (free_speech | assisted_selection | repair_supported | no_response), spoken_text, selected_option_id, hint_level_reached, repair_used, audio_replays, latency_ms | **No.** Server receives frame_id + engine_id (or next_question + conversation_state, or probe_id). No response_mode, hint_level_reached, repair_used, latency_ms. |
| **Turn evaluation payload (runtime internal)** | success_level, capability_updates[], memory_updates[], energy_update, repair_state, selector_mode_next, engine_switch_recommended | **No.** No turn evaluation, no capability/memory/energy/repair/selector-mode updates on server. |

**Gap:** The contract’s full prompt/response/event/submission/evaluation flow is not implemented. Runtime does not use persona_id, branch_id, turn_type, or response_mode; no turn evaluation or selector_mode_next.

---

## 2. MandarinOS Runtime Conversation State Engine v1

**Spec:** `MandarinOS_runtime_conversation_state_engine_v1.md`

| Element | Spec | Implemented? |
|--------|------|--------------|
| **State object** | session_id, persona_id, session_mode, current_engine, current_branch, current_turn_type, current_energy, hint_burden, recent_turns, recent_anchors, engine_path, memory_context, capability_snapshot, repair_state, selector_mode | **Partial.** We have session_id (client), current_engine, recent_frame_ids (subset of recent_turns). Missing: persona_id, session_mode, current_branch, current_turn_type, current_energy, hint_burden, recent_anchors, engine_path, memory_context, capability_snapshot, repair_state, selector_mode. |
| **Main runtime states** | READY, PROMPT_RENDERED, WAITING_FOR_RESPONSE, HINT_INTERACTION, RESPONSE_EVALUATION, STATE_UPDATE, NEXT_MOVE_SELECTION, REPAIR_MODE, SESSION_REVIEW | **No.** No explicit state machine on server; client has UI modes (READ, RESPOND) but no formal state engine. |
| **Turn cycle** | Render prompt → Learner interaction → Evaluate interaction → Update state → Select next move | **Partial.** We do “render prompt” (frame + options) and “select next move” (ladder/bridge). We do not: evaluate interaction (success/hint depth/repair), update state (capability, energy, repair, selector mode). |
| **Response mode tracking** | free_speech, assisted_selection, repair_supported, no_response | **No.** Not sent or stored. |
| **Response support level** | none, audio_only, pinyin, translation, gloss, deep_hint | **No.** Not tracked. |
| **Turn types** | ENTRY_QUESTION, FOLLOW_UP, BRIDGE_QUESTION, ANCHOR_REINFORCEMENT, MEMORY_RECALL, REPAIR_SUPPORT, RECAP_OR_RESET | **No.** Frames are not tagged with turn_type; selector does not emit turn type. |
| **Engine branch tracking** | e.g. entry, destination, time, reaction, food_bridge per engine; exhaustion | **No.** We only have engine + recent_frame_ids; no branch or exhaustion per branch. |
| **Engine switching rules** | Stay if coping well / follow-ups available / energy high; switch if hint burden, low capability, natural bridge, topic fatigue | **Partial.** We switch on exhaust (no unseen frames) or prefer_bridge (recovery/change topic). No capability, energy, or hint-burden input. |
| **Repair state** | STABLE → STRUGGLING → REPAIR_ACTIVE → RECOVERED → STABLE | **No.** Not implemented. |
| **Selector modes** | NORMAL, SIMPLIFY, REINFORCE, PIVOT, DEEPEN | **No.** Selector has no mode. |
| **Runtime event log** | PROMPT_RENDERED, AUDIO_PLAYED, OPTION_SELECTED, TURN_EVALUATED, ENGINE_SWITCHED, etc. | **Partial.** Client emits trace events; server does not maintain or use event log. |
| **Simplified loop** | on_turn_start(): generate_candidate_moves, select_next_move, render_prompt; on_response(): evaluate_response, update_capabilities, update_memory, update_energy, update_repair_state, choose_selector_mode, next_turn | **Partial.** We have select_next_move + render (frame + options). We do not evaluate_response, update_* or choose_selector_mode. |

**Gap:** No formal state object, no state machine, no response mode/support level, no turn types or branches, no repair state or selector mode, no evaluation → state update loop.

---

## 3. MandarinOS Next Question Selector v1

**Spec:** `MandarinOS_next_question_selector_v1.md` (LOCKED)

| Element | Spec | Implemented? |
|--------|------|--------------|
| **Inputs** | Conversation state (current engine, depth, recent turns, who spoke last); Capability map; Energy model; Memory model; Persona data; Learning constraints | **Partial.** We use current_engine, recent_frame_ids. We do not use: capability map, energy model, memory model, persona data, learning constraints. |
| **Output types** | A. Simple question, B. Follow-up question, C. Bridge question, D. Simpler recovery question, E. Repair support, F. Memory recall | **Partial.** We output a single “next frame” (could be simple or bridge). We do not distinguish output type; no explicit follow-up vs bridge vs recovery vs repair vs memory recall. |
| **Candidate generation** | From current engine, engine bridge questions, curiosity toolkit, repair toolkit, memory recall, anchor reinforcement | **Partial.** Candidates = partner-question frames in _FRAME_ORDER per engine + bridge targets. No repair toolkit, memory recall, or anchor reinforcement as candidate sources. |
| **Hard filters** | Recently asked, contradictory to memory, too difficult for capability, lexically overloaded, unrelated, repetitive | **Partial.** We filter “recent” (recent_frame_ids). No memory, capability, lexical, or relevance filters. |
| **Scoring** | Comprehensibility, Relevance, Interest value, Learning value, Stretch value; priority order | **No.** We use a fixed order (same engine order, then bridge). No scoring. |
| **Hint-aware adjustment** | If many hints used recently: shorten sentence, reduce complexity, favor familiar patterns | **No.** Selector has no hint input. |
| **Persona realism** | Questions consistent with persona identity | **No.** No persona data. |
| **Memory integration** | Memory-aware questions get bonus; recall frequency | **No.** No memory. |
| **Difficulty bands** | Safe zone, comfort-growth zone, avoid break zone | **No.** No capability or difficulty bands. |
| **Minimum viable selector steps** | Generate candidates → Filter → Score (five dimensions) → Select highest → Adjust if hint burden high | **Partial.** We do generate (ordered list), filter (recent), and select (first unseen). We do not score or adjust by hint burden. |

**Gap:** Selector is “minimal viable” only: deterministic order + recent + bridge. No capability, energy, memory, persona, learning constraints; no scoring; no turn-type or output-type distinction; no hint-aware or memory-aware behaviour.

---

## 4. MandarinOS Engine Specs v1 (+ individual engine docs)

**Spec:** `MandarinOS_engine_specs_v1.md` and per-engine specs (identity, place, family, food, travel, study/work, interests)

| Element | Spec | Implemented? |
|--------|------|--------------|
| **Engine template** | Purpose, Role, Core [?], Treasure [T], Loop [L], Trigger patterns, Bridges [B→X], Typical paths, Example mini conversation | **Partial.** We use engine names and frame lists; _FRAME_ORDER and _BRIDGE_TARGETS align roughly with core/treasure/loop and bridges. We do not use: trigger patterns (content-driven steering), typical paths, or explicit Core/Treasure/Loop tags on frames. |
| **Trigger patterns** | e.g. “Name origin → family”, “Location mention → Place engine” | **No.** Steering is not content-based; we do not extract triggers from learner text to choose engine. |
| **Bridges** | Per-engine bridge targets (e.g. Identity → Place, Family, Work) | **Yes.** _BRIDGE_TARGETS and recovery bridge order. |
| **Core / Treasure / Loop** | Frames tagged [?], [T], [L] in specs | **Partial.** Order in _FRAME_ORDER reflects core-then-treasure style; no question_type field on frames. |

**Gap:** No trigger-based steering from learner content; no explicit frame metadata (question_type, branch); no use of “typical paths” or example flows in logic.

---

## 5. Conversation steering engine v1

**Spec:** `mandarinos_conversation_steering_engine_v1.md`

| Element | Spec | Implemented? |
|--------|------|--------------|
| **Steering loop** | User answer → Extract signals → Evaluate curiosity triggers → Select next engine → Ask next question | **No.** We do not parse the learner’s answer for signals (location, family, work, food, travel, opportunity). Next engine is chosen by exhaust or explicit bridge, not by content. |
| **Trigger types** | Location, family, work, food, travel, opportunity signals from learner text | **No.** Not implemented. |
| **Priority rule** | New information → Personal → Emotional → Curiosity → Neutral | **No.** Not implemented. |

**Gap:** Steering is not implemented. No signal extraction from learner answers; no content-driven engine or branch selection.

---

## 6. Conversation memory model v1/v2

**Spec:** `MandarinOS_conversation_memory_model_v1.md`, `MandarinOS_conversation_memory_model_v2.md`

| Element | Spec | Implemented? |
|--------|------|--------------|
| **Two-sided memory** | What learner knows about persona; what persona knows about learner | **No.** No persistent memory. |
| **Memory attached to persona** | persona_id → memory_of_learner, learner_memory_of_persona | **No.** No persona_id; no memory storage. |
| **Four layers** | Global learner memory; persona-specific learner memory; persona facts; session memory | **No.** Session state is only current_engine + recent_frame_ids (and client-side transcript). No persistence, no persona facts. |
| **Memory recall** | Selector can ask memory-recall questions (e.g. “你刚才说你喜欢成都，还想再去吗？”) | **No.** No memory; no recall questions. |

**Gap:** No memory layer is implemented. No storage of learner or persona facts; no cross-session or persona-attached memory.

---

## 7. Conversation capability map v1 + capability update rules

**Spec:** `MandarinOS_conversation_capability_map_v1.md`, `MandarinOS_capability_update_rules_v1.md`

| Element | Spec | Implemented? |
|--------|------|--------------|
| **Capability map** | Per-engine capability; per-move capability; modality; curiosity capability; repair capability; lexical/pattern | **No.** Not implemented. |
| **Update rules** | Update capability from turn outcomes (success, hint level, repair) | **No.** No turn evaluation; no updates. |
| **Selector use** | Filter/score by capability; avoid too-difficult questions | **No.** Selector does not read capability. |

**Gap:** Capability map and update rules are not implemented. No adaptation to learner strength per engine or move.

---

## 8. Conversation energy model v1

**Spec:** `mandarinos_conversation_energy_model_v1.md`

| Element | Spec | Implemented? |
|--------|------|--------------|
| **Energy levels** | Light (Identity, Place, Travel, Food); Personal curiosity (Family, Work, Hobbies); Deeper topics | **No.** Not implemented. |
| **Energy decay** | After deep discussion, return to lighter topics | **No.** Not implemented. |
| **Energy signals** | Low energy: 还行, 一般; high: longer answers, enthusiasm | **No.** Not used. |
| **Selector use** | Energy feeds selector (e.g. simplify when low) | **No.** Selector has no energy input. |

**Gap:** Energy model is not implemented. No energy state or signals; no effect on next move.

---

## 9. Conversation runtime model v1

**Spec:** `MandarinOS_conversation_runtime_model_v1.md`

| Element | Spec | Implemented? |
|--------|------|--------------|
| **Five next moves** | A. Ask a question, B. Reveal a short statement (persona), C. Reciprocity (你呢？), D. Reaction/filler (是吗？, 哦), E. Repair | **Partial.** We do A (ask question). We have repair phrases in UI but not as “next move” type. We do not: B (reveal statement), C (reciprocity as system move), D (reaction/filler). Oxygen loop probes let the *learner* ask 为什么？ etc.; no system-initiated reciprocity/filler. |
| **Decision priority** | 1. Repair, 2. Reciprocity, 3. Curiosity trigger, 4. Ask next engine question, 5. Filler | **Partial.** We effectively do “ask next question” and repair (via recovery UI). We do not prioritize reciprocity or curiosity trigger as system moves. |
| **Core rhythm** | Question → Answer → Short statement → Reciprocity | **No.** We have Question → Answer → (next question). No short statement or reciprocity step. |

**Gap:** Only “ask question” is implemented as a system move. No “reveal statement”, no system 你呢？, no fillers/reactions as moves; no formal decision priority.

---

## 10. Conversation state diagram v1

**Spec:** `MandarinOS_conversation_state_diagram_v1.md`

| Element | Spec | Implemented? |
|--------|------|--------------|
| **Session flow** | Session start → Select session mode → Select persona → Select entry engine → Run turn loop → Store/update memory → Continue/Bridge/End | **Partial.** We have turn loop and bridge. No session mode selection, no persona selection, no entry engine selection (we start from first frame in order), no memory store. |
| **Session modes** | Drill, Mixed, Continue | **No.** Not implemented. |
| **Entry engine** | Identity or Place | **Partial.** We have engines; first question depends on initial engine/frame, not explicit “entry engine” selection. |
| **Turn loop** | Current engine → Check repair → Check reciprocity → Check curiosity → Select next move → Render → Capture response → Update memory → Stay/Bridge/Repair/End | **Partial.** We have current engine, select next move, render, capture response, stay/bridge. No check repair/reciprocity/curiosity as formal steps; no update memory. |

**Gap:** No session mode or persona selection; no formal loop steps for repair/reciprocity/curiosity; no memory update.

---

## 11. Other spec references

| Spec | Role | Implemented? |
|------|------|--------------|
| **MandarinOS_Conversation_UX_Protocol_v1.md** | UX behaviour | Partially (transcript, options, recovery, probe row); not systematically aligned. |
| **MandarinOS_conversation_system_blueprint_v1.md** | Layers: Engines → Curiosity → Fillers → Repair → Memory → Persona | Engines and repair (recovery) partially; curiosity (probes) partially; fillers, memory, persona not. |
| **MandarinOS_conversation_ladders_full_draft_v2.md** | Oxygen loop questions, treasure, bridge per engine | Probe list and frame order used; ladders not used as single source of truth for frame set. |
| **mandarinos_emergency_curiosity_pack_v1.md** | Beginner curiosity phrases | Used conceptually for probe list; emergency flow not wired. |
| **mandarinos_persona_network_relationship_pack_v1.md** | Persona network, relationships | Not implemented. |

---

## Summary: architectural elements not yet implemented

1. **Turn data contract (full)** — persona_id, branch_id, turn_type; response submission (response_mode, hint_level_reached, repair_used, latency_ms); turn evaluation payload (success_level, capability_updates, memory_updates, energy_update, repair_state, selector_mode_next).
2. **Runtime state engine** — Full state object (persona_id, session_mode, branch, turn_type, energy, hint_burden, anchors, memory_context, capability_snapshot, repair_state, selector_mode); explicit state machine; response mode and support level tracking; turn types; engine branch tracking; repair state transitions; selector modes.
3. **Next question selector (full)** — All six inputs (especially capability, energy, memory, persona, learning constraints); output type distinction (follow-up, bridge, recovery, repair, memory recall); candidate sources (repair toolkit, memory recall, anchor reinforcement); hard filters (memory, capability, relevance); five-dimension scoring; hint-aware and memory-aware behaviour; difficulty bands.
4. **Engine specs (content-driven)** — Trigger patterns and signal extraction from learner text; steering by “typical paths”; explicit question_type (and optionally branch) on frames.
5. **Steering engine** — Extract signals from learner answer; evaluate curiosity triggers; select next engine by content (not only exhaust/bridge).
6. **Memory model** — Two-sided memory; persona-attached memory; four layers; memory recall questions; persistence.
7. **Capability map + update rules** — Per-engine and per-move capability; updates from turn outcomes; selector using capability.
8. **Energy model** — Energy levels and signals; decay; selector using energy.
9. **Runtime model (full)** — Reveal statement (B), reciprocity (C), reaction/filler (D) as system moves; decision priority (repair → reciprocity → curiosity → question → filler); core rhythm (question → answer → short statement → reciprocity).
10. **State diagram (full)** — Session mode and persona selection; entry engine selection; formal turn loop with repair/reciprocity/curiosity checks and memory update.
11. **Persona network** — Persona data, persona selection, persona-consistent questions and memory.

---

## Recommended use of this document

- **Before adding features:** Check the relevant spec (index → spec file) and this gap doc so new work aligns with the architecture.
- **Phase 10 (Memory + Persona):** Use §6 (memory), §11 (persona), and §3 (selector inputs: memory, persona) as the checklist.
- **Selector evolution:** Use §3 and §2 (state object, turn evaluation) so that when we add scoring or hint-aware behaviour, we also add the contract and state fields the spec expects.
- **Steering and triggers:** Use §5 and §4 so that when we add content-driven steering, we implement trigger extraction and engine/branch selection per steering spec.

*Created 2026-03. Update as implementation catches up to specs.*
