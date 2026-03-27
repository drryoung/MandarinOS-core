# MandarinOS Development Roadmap — Strategic Plan v2 (Corrected)

Purpose: Align ChatGPT (strategist), Cursor (architect/programmer), and
the project owner (reviewer) around a clear and complete development
roadmap for MandarinOS.

This document reflects current implementation progress as of March 2026
and corrects missing phases related to conversational content and persona systems.

---

# Current Project Status

Phase 7 — Learning Interaction Layer ✔ Complete  
Phase 8 — Conversation Loop UI ✔ Complete  
Phase 9 — Conversation Engine Integration ✔ Signed Off  
Phase 10 — Memory + Persona Foundations ✔ Core Implemented  
Phase 11 — Adaptive Conversation Intelligence ✔ Core Implemented (Refinement Ongoing)

The system now contains a **stable, extensible conversation engine**.

---

# Key Architectural Insight

MandarinOS adaptive conversation requires five layers:

1. Conversation Loop Infrastructure  
2. Conversation Selection Logic  
3. Memory + Persona Context  
4. Learner State Modelling  
5. Adaptive Steering and Repair  

Phases 7–9 built layers 1–2.  
Phases 10–11 implemented the core of layers 3–5.

The system is now transitioning from **architecture building → conversational realism and identity**.

---

# Phase Overview (Corrected)

Phase 7 — Learning Interaction Layer  
Phase 8 — Conversation Loop UI  
Phase 9 — Conversation Engine Activation ✔  
Phase 10 — Memory + Persona Foundations ✔  
Phase 11 — Adaptive Conversation Intelligence (Core Implemented)  
Phase 11B — Conversational Role Expansion (EXTEND Frames)  
Phase 11C — Persona Layer & Discoverable Partner Content ← NEW  
Phase 12 — Personal Alpha Testing (Full Conversation Experience)  
Phase 13 — Closed Beta (10–100 users)  
Phase 14 — Data-Driven Iteration  

---

# Phase 11 — Adaptive Conversation Intelligence (Status)

Status (2026-03):
- move_type grammar implemented  
- transition model calibrated  
- selector hygiene complete  
- FRAME_ORDER respected  
- scoring scaffold implemented (diagnostic layer)  
- system validated via alpha observation  

This phase is **functionally complete at core level**.

---

# Phase 11B — Conversational Role Expansion (EXTEND Frames)

Goal:
Reduce interview feel by enabling partner self-disclosure.

Scope:
- Introduce EXTEND frames
- Add 1–2 EXTEND frames per engine
- Improve conversational rhythm

Constraints:
- Content-first (no selector changes)
- Persona-agnostic content
- No scoring or architecture changes

Outcome:
Conversation becomes less interrogative and more natural.

---

# Phase 11C — Persona Layer & Discoverable Partner Content

Goal:
Introduce multiple conversation partners with distinct, discoverable identities.

This phase transforms MandarinOS from:
“a conversation system” → “a conversation with someone”

---

## Core Features

- 5+ personas (conversation partners)
- Each persona has:
  - name
  - background
  - interests
  - preferences
  - small discoverable facts

- Learners can:
  - ask about the partner
  - learn new information gradually
  - encounter differences across partners

---

## Design Principles

1. Separation of layers:
   - Frames define conversational capability
   - Personas provide content variation

2. No hardcoding:
   - Persona details must NOT be embedded directly into frame text
   - Persona data must live in structured persona profiles

3. Discoverability:
   - Information is revealed gradually
   - Not all persona information is exposed immediately

4. Reuse:
   - EXTEND frames from Phase 11B are reused and enriched by persona data

---

## Example (Conceptual)

Generic frame:
“我也很喜欢这个。”

Persona A:
“我也很喜欢这个，我周末常去爬山。”

Persona B:
“我也很喜欢这个，特别是吃辣的。”

---

## Acceptance Criteria

- At least 5 distinct personas available
- Conversations feel different depending on partner
- Learner can discover new facts over multiple turns
- No selector rewrite required
- Frame architecture remains unchanged

---

# Phase 12 — Personal Alpha Testing (Full Conversation Experience)

Goal:
Evaluate MandarinOS with:
- EXTEND frames
- Persona system
- Adaptive selector

Evaluation:
- conversational realism
- emotional engagement
- perceived personality of partner
- learner comfort and confidence

---

# Phase 13 — Closed Beta

Participants: 10–100 learners

Focus:
- engagement
- conversation depth
- persona preference
- retention

Key question:
“Does this feel like a real conversation with a person?”

---

# Phase 14 — Data-Driven Iteration

Improve:
- frame quality
- persona realism
- option generation
- adaptive behaviour
- speech integration

---

# Extensibility Strategy (Locked)

MandarinOS evolves through:

- adding higher-value frames
- improving responses
- expanding persona richness
- refining builder output

NOT through:
- rewriting existing frames
- increasing selector complexity unnecessarily
- hardcoding behaviour

Constraint:

Adding new frames or personas must NOT require changes to:
- selector logic
- scoring system
- runtime architecture

---

# Strategic Vision

MandarinOS is a **conversation operating system for language acquisition**.

Development path:

Conversation Loop  
→ Structured Selector  
→ Adaptive Intelligence  
→ Conversational Role Expansion  
→ Persona Layer  
→ Real-world Testing  
→ Continuous Improvement  

The system is now entering:

**“humanisation phase” — from functional to relational conversation**
