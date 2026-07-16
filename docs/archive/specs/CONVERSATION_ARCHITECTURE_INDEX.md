<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class C: Historical context**
>
> - **Current use:** Retained as an index of earlier conversation-design specifications.
> - **May guide current implementation:** No.
> - **Current authority:** `docs/ARCHITECTURE.md`, `docs/CONVERSATION_ARCHITECTURE.md`, and `docs/ANSWER_SOURCE_CONTRACT.md`.
> - **Principal caution:** Specifications marked `LOCKED` inside this index remain historical design records unless separately reflected in verified R2 behaviour.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS Conversation Architecture Index

**Purpose:** Single entry point for all conversation-design decisions created (including iPhone/ChatGPT work copied into the repo). Use this so **ChatGPT (strategist)** and **Cursor (senior architect)** are aware of every decision and can implement when the time is right.

**Last updated:** 2026-03-08

---

## 1. High-level architecture (read first)

| Document | Role | Content |
|----------|------|--------|
| [MandarinOS_conversation_system_blueprint_v1.md](./MandarinOS_conversation_system_blueprint_v1.md) | Blueprint | Core philosophy, layers (Engines → Curiosity → Fillers → Repair → Memory → Persona), engine list, P1 loop, design principles |
| [mandarinos_conversation_architecture_v1.md](../superseded/mandarinos_conversation_architecture_v1.md) | Spine | Engine template, P1 loop structure, memory anchors, reciprocity (你呢？), what is stable vs exploratory |
| [MandarinOS_engine_specs_v1.md](./MandarinOS_engine_specs_v1.md) | Engine catalogue | **Six engines** in one doc: Identity, Place, Food, Family, Study/Work, Travel — Core/Treasure/Loop questions, triggers, bridges, paths, examples |
| [MANDARINOS_CONVERSATION_FLOW_DESIGN.md](../../specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md) | **Implementation rules** | Curiosity-led ordering, `skip_when` mechanism, oxygen/echo questions, recovery hierarchy, selector anti-patterns. **Read before any selector or ordering change.** |

---

## 2. Conversation engines (7 topic modules)

Each engine is a topic module. Identity and Place are entry/hub; others are secondary. All follow the same template: Purpose, Role, Core [?], Treasure [T], Loop [L], Triggers, Bridges [B→X], Typical Paths.

| Engine | Spec document | Role | Notes |
|--------|----------------|------|--------|
| **Identity** | [mandarinos_identity_engine_v4.md](./mandarinos_identity_engine_v4.md) | Entry | Name, 你呢？, bridges to Place, Family, Study/Work |
| **Place** | [MandarinOS_engine_specs_v1.md](./MandarinOS_engine_specs_v1.md) (§ Place) | Entry + Hub | 哪里人, 老家, 住哪儿; bridges to Food, Travel, Family |
| **Food** | [MandarinOS_engine_specs_v1.md](./MandarinOS_engine_specs_v1.md) (§ Food) | Secondary | Local food, taste, bridges to Place, Travel |
| **Family** | [mandarinos_family_engine_v4.md](./mandarinos_family_engine_v4.md) | Secondary | 几个人, 兄弟姐妹, 孩子; bridges to Place, Study/Work, personas |
| **Study / Work** | [mandarinos_study_work_engine_v10.md](./mandarinos_study_work_engine_v10.md) | Secondary | 你做什么？, 你学什么？; bridges to Place, Family |
| **Travel** | [mandarinos_travel_engine_v4.md](./mandarinos_travel_engine_v4.md) | Secondary | 去过中国/北京; curiosity-driven; bridges to Place, Food |
| **Interests** | [mandarinos_interests_engine_v1.md](./mandarinos_interests_engine_v1.md) | Secondary | 你喜欢做什么？; hobbies, culture; bridges to Travel, Food, Family, Work |

Additional engine-related content:

- [mandarinos_curiosity_engine_v1.md](./mandarinos_curiosity_engine_v1.md) — Curiosity triggers and follow-ups
- [mandarinos_food_engine_v1.md](./mandarinos_food_engine_v1.md) — Food engine detail (if distinct from engine_specs)
- [mandarinos_place_engine_v1.md](./mandarinos_place_engine_v1.md) — Place engine detail

---

## 3. Sentence / next-question selection

| Document | Role | Content |
|----------|------|--------|
| [MandarinOS_next_question_selector_v1.md](./MandarinOS_next_question_selector_v1.md) | **LOCKED** | How to choose the next conversational move: inputs (state, capability map, energy, memory, persona, constraints), output types, candidate generation, hard filters, scoring (comprehensibility, relevance, interest, learning, stretch), engine switching, hint-aware adjustment, minimum viable selector |

---

## 4. Conversation state, memory, and capability

| Document | Role | Content |
|----------|------|--------|
| [MandarinOS_runtime_conversation_state_engine_v1.md](../superseded/MandarinOS_runtime_conversation_state_engine_v1.md) | Runtime state | Conversation state at runtime (implementation-facing) |
| [MandarinOS_conversation_memory_model_v1.md](../superseded/MandarinOS_conversation_memory_model_v1.md) | Memory v1 | Conversation memory design |
| [MandarinOS_conversation_memory_model_v2.md](./MandarinOS_conversation_memory_model_v2.md) | Memory v2 | Two-sided memory (learner↔persona), four layers (global learner, persona-specific learner, persona facts, session), persona-attached memory |
| [MandarinOS_conversation_capability_map_v1.md](./MandarinOS_conversation_capability_map_v1.md) | Capability | Per-engine and per-move capability; curiosity and repair capability; modality; lexical/pattern; used by Next Question Selector |
| [MandarinOS_capability_update_rules_v1.md](./MandarinOS_capability_update_rules_v1.md) | Update rules | How capability scores are updated from conversation outcomes |

---

## 5. Steering, energy, and flow

| Document | Role | Content |
|----------|------|--------|
| [mandarinos_conversation_steering_engine_v1.md](./mandarinos_conversation_steering_engine_v1.md) | Steering | How conversation moves between engines: trigger types (location, family, work, food, travel, opportunity), steering loop (answer → signals → curiosity → next engine) |
| [mandarinos_conversation_energy_model_v1.md](./mandarinos_conversation_energy_model_v1.md) | Energy | Conversation momentum, hesitation, hint burden, engagement (feeds Next Question Selector) |

---

## 6. Ladders, vocab, and support packs

| Document | Role | Content |
|----------|------|--------|
| [MandarinOS_conversation_ladders_full_draft_v2.md](./MandarinOS_conversation_ladders_full_draft_v2.md) | Ladders | Per-engine: current frames (P1/P2), treasure questions, oxygen loop questions, bridge questions |
| [mandarinos_family_conversation_ladder_v2.md](./mandarinos_family_conversation_ladder_v2.md) | Family ladder | Family-specific ladder |
| [mandarinos_family_conversation_ladder.md](../superseded/mandarinos_family_conversation_ladder.md) | Family ladder (alt) | Earlier family ladder |
| [MandarinOS_support_packs_v1.md](./MandarinOS_support_packs_v1.md) | Support packs | Emergency phrases, fillers, orientation vocab, adjectives, relationship vocab — reusable across engines |
| [mandarinos_emergency_phrases_p1_p2_v2.md](./mandarinos_emergency_phrases_p1_p2_v2.md) | Emergency | Repair and recovery phrases |
| [mandarinos_emergency_curiosity_pack_v1.md](./mandarinos_emergency_curiosity_pack_v1.md) | Curiosity pack | Curiosity triggers and fallbacks |

---

## 7. Persona network and UX

| Document | Role | Content |
|----------|------|--------|
| [mandarinos_persona_network_relationship_pack_v1.md](./mandarinos_persona_network_relationship_pack_v1.md) | Persona network | Connected personas (e.g. 5–7), relationships, bridges between characters |
| [MandarinOS_Conversation_UX_Protocol_v1.md](./MandarinOS_Conversation_UX_Protocol_v1.md) | UX protocol | How conversation UX should behave |
| [MandarinOS_conversation_state_diagram_v1.md](../superseded/MandarinOS_conversation_state_diagram_v1.md) | State diagram | Conversation state machine / diagram |
| [MandarinOS_conversation_runtime_model_v1.md](../superseded/MandarinOS_conversation_runtime_model_v1.md) | Runtime model | Runtime conversation model |
| [MandarinOS_conversation_expansion_audit_v2.md](../../specs/MandarinOS_conversation_expansion_audit_v2.md) | Audit | Expansion audit of conversation design |

---

## 8. Other references

- [MandarinOS_master_AI_bootstrap_context.md](../superseded/MandarinOS_master_AI_bootstrap_context.md) — High-level project and session design; references conversation philosophy.
- [MandarinOS_turn_data_contract_v1.md](../superseded/MandarinOS_turn_data_contract_v1.md) — Turn/response contract (implementation).
- PDF: [MandarinOS_conversation_architecture_decisions_v1.pdf](../../specs/MandarinOS_conversation_architecture_decisions_v1.pdf) — Architecture decisions (if needed for history).

---

## 9. Implementation order (when the time is right)

Suggested dependency order for implementation:

1. **Lexicons and frames** (existing P1/P2 frames) — already in repo; ensure engine_id and content align with engine specs.
2. **Engine content** — Map each engine (Identity, Place, Food, Family, Study/Work, Travel, Interests) to frames and option sets; use engine_specs_v1 + individual engine docs.
3. **Memory model** — Implement memory layers (v2) and attach to persona/session.
4. **Capability map** — Implement capability tracking per engine and move; feed from trace/turn outcomes.
5. **Next Question Selector** — Implement minimum viable selector (candidates → filters → score → select); use capability map and energy.
6. **Steering** — Implement trigger extraction and engine switching using steering engine and bridges from engine specs.
7. **Persona network** — Wire persona data and relationships into memory and selector.

Current runtime (Phase 6 frozen) already has frames, options, hints, and trace; conversation logic (selector, steering, memory) is the next layer to add when strategy and architecture agree to proceed.

---

**For ChatGPT (strategist):** Use this index to review completeness, prioritise engines or features, and define acceptance criteria before implementation.  
**For Cursor (senior architect):** Use this index to locate every design decision; implement in small steps per AI_CONTEXT.md and the Design Constitution.
