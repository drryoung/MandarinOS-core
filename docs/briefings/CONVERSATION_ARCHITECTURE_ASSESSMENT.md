<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class E: Dated report or historical evidence**
>
> - **Current use:** Retained as a dated assessment of the conversation architecture.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current conversation code and `docs/CONVERSATION_ARCHITECTURE.md`.
> - **Principal caution:** This assessment may explain concerns or reasoning from its review date, but it must not override the approved R2 conversation contract.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Conversation Architecture — Senior Architect Assessment

**Date:** 2026-03-08  
**Role:** Cursor as senior architect  
**Question:** Are the design architectures for conversations in MandarinOS clear? Is ChatGPT or Cursor aware of all decisions made (including iPhone/ChatGPT work from 6–8 March) and can implement when the time is right?

---

## 1. Summary: Is it clear?

**Yes.** The conversation design is documented in enough detail for a senior architect (or strategist) to understand the system and for implementation to proceed when agreed. The work done in ChatGPT on iPhone and copied into the repo is present under `docs/specs/` in a consistent structure: engines, selector, memory, capability, steering, ladders, persona network, and support packs.

**Gap that was fixed:** There was no single place that listed *all* of these decisions and file locations. Without it, awareness depended on searching. So an explicit **Conversation Architecture Index** has been added and linked from AI_CONTEXT and MANDARINOS_SYSTEM_MAP.

---

## 2. What is documented (and clear)

### 2.1 Six–seven conversation engines

- **Identity** — Entry; name, 你呢？; bridges to Place, Family, Study/Work.  
  Specs: `mandarinos_identity_engine_v4.md` + `MandarinOS_engine_specs_v1.md`.
- **Place** — Entry + Hub; 哪里人, 老家, 住哪儿; bridges to Food, Travel, Family.  
  In `MandarinOS_engine_specs_v1.md` + `mandarinos_place_engine_v1.md`.
- **Food** — Secondary; local food, taste; bridges to Place, Travel.  
  In `MandarinOS_engine_specs_v1.md` + `mandarinos_food_engine_v1.md`.
- **Family** — Secondary; 几个人, 兄弟姐妹, 孩子; bridges to Place, Study/Work, personas.  
  Specs: `mandarinos_family_engine_v4.md` + engine_specs_v1.
- **Study / Work** — Secondary; 你做什么？, 你学什么？.  
  Specs: `mandarinos_study_work_engine_v10.md` + engine_specs_v1.
- **Travel** — Secondary; 去过中国/北京; curiosity-driven.  
  Specs: `mandarinos_travel_engine_v4.md` + engine_specs_v1.
- **Interests** — Secondary; 你喜欢做什么？; hobbies, culture.  
  Specs: `mandarinos_interests_engine_v1.md`.

All follow the same template: Purpose, Role, Core [?], Treasure [T], Loop [L], Triggers, Bridges [B→X], Typical Paths. This is clear and implementable.

### 2.2 Sentence / next-question selector

- **MandarinOS_next_question_selector_v1.md** is marked LOCKED. It defines:
  - Inputs: conversation state, capability map, energy model, memory, persona data, learning constraints.
  - Output types: simple question, follow-up, bridge, recovery, repair, memory recall.
  - Candidate generation, hard filters, five scoring dimensions (comprehensibility, relevance, interest, learning, stretch), engine switching, hint-aware adjustment.
  - Minimum viable selector (v1) steps.

Clear and sufficient to implement when the time is right.

### 2.3 Conversation architecture (overall)

- **MandarinOS_conversation_system_blueprint_v1.md** — Philosophy, layers (Engines → Curiosity → Fillers → Repair → Memory → Persona), P1 loop, design principles.
- **mandarinos_conversation_architecture_v1.md** — Engine template, P1 loop structure, memory anchors, reciprocity, stable vs exploratory.
- **mandarinos_conversation_steering_engine_v1.md** — How conversation moves between engines (triggers, steering loop).
- **MandarinOS_conversation_memory_model_v2.md** — Two-sided memory, four layers, persona-attached memory.
- **MandarinOS_conversation_capability_map_v1.md** — Per-engine and per-move capability; curiosity and repair; modality; used by selector.
- **mandarinos_conversation_energy_model_v1.md** — Momentum, hesitation, hint burden, engagement.

These are consistent with each other and with the engine set above. No conflicting high-level direction was found.

### 2.4 Ladders, support packs, persona network

- Conversation ladders (per-engine frames, treasure/loop/bridge questions): **MandarinOS_conversation_ladders_full_draft_v2.md** and family-specific ladder docs.
- Support packs (emergency phrases, fillers, orientation): **MandarinOS_support_packs_v1.md**, **mandarinos_emergency_phrases_p1_p2_v2.md**, **mandarinos_emergency_curiosity_pack_v1.md**.
- Persona network: **mandarinos_persona_network_relationship_pack_v1.md**.

All are findable and usable for implementation.

---

## 3. Gaps that were addressed

1. **No single index**  
   Conversation specs were only discoverable by search or prior knowledge. **Fix:** Added **`docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`** listing every relevant doc, the 7 engines, selector, memory, capability, steering, ladders, packs, and persona network, with paths and one-line roles. Suggested implementation order is noted at the end of the index.

2. **AI_CONTEXT and MANDARINOS_SYSTEM_MAP did not point to conversation design**  
   They mentioned “conversation-first” and `engine_id` but not where the conversation architecture lives. **Fix:**  
   - In **AI_CONTEXT.md**, added §5.0 “Conversation architecture (design specs)” pointing to the index.  
   - In **MANDARINOS_SYSTEM_MAP.md**, under “Engine”, added a sentence pointing to the index for conversation engines and design.

With these changes, both **ChatGPT (strategist)** and **Cursor (senior architect)** have an explicit path to “all conversation design decisions” and can implement when the time is right.

---

## 4. Minor notes (no block to implementation)

- **Blueprint vs engine_specs:** The blueprint lists “Future engines: Family, Study/Work, Travel, Hobbies” but **MandarinOS_engine_specs_v1.md** already includes Family, Study/Work, Travel. “Hobbies” is covered by **Interests** in the index. So the engine_specs doc is the more up-to-date catalogue; the index aligns with it and adds Interests.
- **Duplicate or overlapping files:** Some engines have both a section in `MandarinOS_engine_specs_v1.md` and a standalone file (e.g. identity_v4, family_v4, travel_v4, study_work_v10). The index treats the consolidated doc plus the standalone as the full spec; implementation can use both (standalone for detail, engine_specs for consistency).
- **Stable vs not locked:** **mandarinos_conversation_architecture_v1.md** §7 says persona generation, final engine ordering, strict difficulty ladder behaviour, and memory storage implementation are still exploratory. That is useful context for the strategist when prioritising what to lock next.

---

## 5. Conclusion

- **Clarity:** The conversation architectures (engines, selector, memory, capability, steering, ladders, persona network) are clear enough for a senior architect to understand and for implementation to proceed in small steps when strategy and architecture agree.
- **Awareness:** With the new **CONVERSATION_ARCHITECTURE_INDEX.md** and the links from AI_CONTEXT and MANDARINOS_SYSTEM_MAP, both ChatGPT and Cursor have an explicit, single place to find all decisions from the iPhone/ChatGPT work (6–8 March) and the rest of the conversation design. Implementation can proceed when the time is right, using the index and the step-by-step discipline in AI_CONTEXT and the Design Constitution.

**Artifacts added:**

- **`docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`** — Master list of conversation design docs and suggested implementation order.
- **`docs/briefings/CONVERSATION_ARCHITECTURE_ASSESSMENT.md`** — This assessment.

**Artifacts updated:**

- **`AI_CONTEXT.md`** — §5.0 pointing to the conversation index.
- **`MANDARINOS_SYSTEM_MAP.md`** — Engine bullet pointing to the index for conversation engines and design.
