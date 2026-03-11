# Briefing for ChatGPT: Strategist for MandarinOS Conversation Design

**To:** ChatGPT (in your role as **strategist** for MandarinOS)  
**From:** Project owner  
**Date:** 2026-03-08  
**Purpose:** Bring you up to speed on the conversation design architecture so there is no confusion between work done in ChatGPT on iPhone and work on PC. **Assume no prior context has carried over from the iPhone version.** This briefing is the handoff.

---

## 1. Why this briefing exists

A lot of conversation design was created in **ChatGPT on iPhone** (roughly 6–8 March 2026) and then copied into the MandarinOS-core repo. That work may not be visible to **ChatGPT on PC** because session context does not automatically transfer between devices. This document gives the PC version a single, authoritative summary so you can act as strategist without missing any of the decisions that were already made.

---

## 2. Your role: strategist (no code)

You are the **strategist** for MandarinOS conversation design. In this role you:

- **Review** conversation architecture and specs for completeness and consistency.
- **Prioritise** which engines, features, or components to implement first (or next).
- **Define acceptance criteria** and test scenarios before implementation.
- **Review** proposals and diffs to prevent scope creep and keep alignment with the Design Constitution.
- **Do not implement code** — implementation is done by Cursor (senior architect + programmer) in small, step-by-step changes.

ChatGPT is also used for **testing** (test scenarios, test review). GitHub Copilot is no longer used.

---

## 3. What conversation design already exists (all in the repo)

The following was designed (including in iPhone ChatGPT sessions) and is stored under **`docs/specs/`** in the MandarinOS-core repo. Treat this as the full set of conversation-design decisions unless the project owner explicitly changes it.

### 3.1 High-level architecture

- **Conversation system blueprint** — Philosophy: conversation simulator, not vocabulary trainer. Layers: Engines → Curiosity → Fillers → Repair → Memory → Persona. P1 loop: Question → Answer → Short statement → Reciprocity (你呢？).
- **Conversation architecture spine** — Engine template (Purpose, Role, Core [?], Treasure [T], Loop [L], Triggers, Bridges [B→X], Paths). P1 loop structure. Memory anchors (name, hometown, family, job/study, favorite food, travel). Reciprocity requirement. Stable vs exploratory areas.

### 3.2 Seven conversation engines (topic modules)

| Engine    | Role          | Purpose / focus |
|-----------|---------------|------------------|
| **Identity** | Entry        | Name, 你呢？; bridges to Place, Family, Study/Work |
| **Place**    | Entry + Hub | 哪里人, 老家, 住哪儿; bridges to Food, Travel, Family |
| **Food**     | Secondary   | Local food, taste; bridges to Place, Travel |
| **Family**   | Secondary   | 几个人, 兄弟姐妹, 孩子; bridges to Place, Study/Work, personas |
| **Study/Work** | Secondary | 你做什么？, 你学什么？; bridges to Place, Family |
| **Travel**   | Secondary   | 去过中国/北京; curiosity-driven; bridges to Place, Food |
| **Interests** | Secondary  | 你喜欢做什么？; hobbies, culture; bridges to Travel, Food, Family, Work |

All engines use the same template: Core questions [?], Treasure [T], Loop [L], Trigger patterns, Bridges [B→X], Typical paths, Example mini-conversation.

### 3.3 Next Question Selector (sentence selection)

- **Next Question Selector v1** — Document is **LOCKED**. Defines how the system chooses the next conversational move. Inputs: conversation state, capability map, energy model, memory, persona data, learning constraints. Output types: simple question, follow-up, bridge, recovery, repair, memory recall. Process: candidate generation → hard filters → scoring (comprehensibility, relevance, interest, learning, stretch) → select. Includes engine switching and hint-aware adjustment. Minimum viable selector (v1) steps are specified.

### 3.4 Memory, capability, steering, energy

- **Memory model v2** — Two-sided memory (what learner knows about persona, what persona knows about learner). Four layers: global learner memory, persona-specific learner memory, persona facts, session memory. Memory attached to persona.
- **Capability map** — Per-engine and per-move capability; curiosity and repair capability; modality; lexical/pattern. Used by the Next Question Selector.
- **Capability update rules** — How capability scores are updated from conversation outcomes.
- **Steering engine** — How conversation moves between engines: trigger types (location, family, work, food, travel, opportunity), steering loop (answer → extract signals → curiosity → select next engine).
- **Energy model** — Conversation momentum, hesitation, hint burden, engagement; feeds the selector.

### 3.5 Ladders, support packs, persona network

- **Conversation ladders** — Per-engine: current frames (P1/P2), treasure questions, oxygen loop questions, bridge questions. Full draft v2 plus family-specific ladders.
- **Support packs** — Emergency phrases, fillers, orientation vocab, adjectives, relationship vocab; reusable across all engines.
- **Emergency and curiosity packs** — Repair phrases, curiosity triggers and fallbacks.
- **Persona network** — Small connected social network (e.g. 5–7 personas), relationships, bridges between characters so the learner can move between personas in conversation.

### 3.6 Other

- **Conversation UX protocol** — How conversation UX should behave.
- **State diagram, runtime model, expansion audit** — Additional design docs for state machine, runtime behaviour, and audit of conversation expansion.

---

## 4. Single source of truth: the index

Every document listed above (and a few more) is catalogued in one place so you never have to guess what exists:

**`docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`**

That file:

- Lists every conversation-related spec with its path and a one-line description.
- Groups them by: high-level architecture, engines, next-question selector, memory/capability, steering/energy, ladders/packs, persona/UX.
- Suggests an implementation order when the time is right (lexicons → engine content → memory → capability → selector → steering → persona).

**Whenever you need to recall what was decided for conversation design, use that index.** It was created so that iPhone-origin work and PC work stay aligned and nothing is lost between sessions or devices.

---

## 5. Division of labour (reminder)

| Role              | Who     | Responsibility |
|-------------------|--------|-----------------|
| **Strategist**    | ChatGPT | Prioritise, acceptance criteria, test scenarios, review; no code. |
| **Senior architect + programmer** | Cursor | Architecture and all implementation; small step-by-step changes only; must not drift from Design Constitution. |
| **Testing**       | ChatGPT | Test design and test review. |

Implementation happens only when you (strategist) and the project owner are ready. Cursor implements in small steps as defined in **AI_CONTEXT.md** and the **Design Constitution** (`docs/design/mandarinos_design_constitution.txt`).

---

## 6. What to do next (suggested)

1. **Read this briefing** and, if you have access to the repo, open **`docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`** to see the full map of conversation design docs.
2. **Confirm** that you have a clear picture of: (a) the seven engines, (b) the Next Question Selector, (c) memory/capability/steering/energy, (d) ladders and persona network. If anything is unclear, say what is missing or ambiguous.
3. **Optional:** Reply with a short paragraph summarising the conversation architecture in your own words (e.g. “MandarinOS conversation is built from seven topic engines, a Next Question Selector that uses state/capability/memory/energy, steering between engines, and a persona network…”). That will confirm there is no confusion between iPhone and PC context.
4. **From now on:** For any conversation-design question, treat **CONVERSATION_ARCHITECTURE_INDEX.md** as the entry point and the listed docs as the authority. If the project owner asks you to change or add something, do it in the spec docs (or recommend where), not only in chat, so the repo stays the single source of truth.

---

## 7. Repo paths (quick reference)

- Conversation design index: **`docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`**
- Design Constitution: **`docs/design/mandarinos_design_constitution.txt`**
- AI roles and step-by-step discipline: **`AI_CONTEXT.md`** (repo root)
- System pipeline map: **`MANDARINOS_SYSTEM_MAP.md`** (repo root)

All paths are relative to the MandarinOS-core repository root.

---

**End of briefing.** Please confirm you have read and understood it, and use the index whenever you need the full set of conversation design decisions.
