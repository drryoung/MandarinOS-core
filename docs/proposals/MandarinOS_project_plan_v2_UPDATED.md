<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as an updated variant within the version-two roadmap document family.
> - **May guide current implementation:** No.
> - **Current authority:** Verified production code and the nine-document R2 architecture-governance package.
> - **Principal caution:** The `UPDATED` filename does not establish current authority, canonical status, or implementation. It is one of several overlapping class-F roadmap variants.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS Development Roadmap — Strategic Plan v2 (Updated)

Purpose: Align ChatGPT (strategist), Cursor (architect/programmer), and
the project owner (reviewer) around a clear and complete development
roadmap for MandarinOS.

This document supersedes **MandarinOS_project_plan_v1.md** and reflects
current implementation progress as of March 2026.

---

# Current Project Status

Phase 7 — Learning Interaction Layer ✔ Complete  
Phase 8 — Conversation Loop UI ✔ Complete  
Phase 9 — Conversation Engine Integration ✔ Signed Off  
Phase 10 — Memory + Persona Foundations ✔ Core Implemented  
Phase 11 — Adaptive Conversation Intelligence ✔ Core Implemented (Refinement Ongoing)

The system now contains a **stable, extensible conversation engine** with:
- deterministic loop
- structured move_type grammar
- selector hygiene and ordering
- scoring scaffold (diagnostic)
- validated conversation flow

---

# Key Architectural Insight

MandarinOS adaptive conversation requires five layers:

1. Conversation Loop Infrastructure  
2. Conversation Selection Logic  
3. Memory + Persona Context  
4. Learner State Modelling  
5. Adaptive Steering and Repair  

Phases 7–9 built layers 1–2.  
Phases 10–11 implemented core of layers 3–5.

Remaining work is **refinement and content-driven realism**, not foundational architecture.

---

# Phase Overview (Updated)

Phase 7 — Learning Interaction Layer  
Phase 8 — Conversation Loop UI  
Phase 9 — Conversation Engine Activation ✔  
Phase 10 — Memory + Persona Foundations ✔  
Phase 11 — Adaptive Conversation Intelligence (Core Implemented)  
Phase 11B — Conversational Role Expansion (Content Layer) ← NEW  
Phase 12 — Personal Alpha Testing (Post-Content Expansion)  
Phase 13 — Closed Beta (10–100 users)  
Phase 14 — Data‑Driven Iteration  

---

# Phase 11 — Adaptive Conversation Intelligence (Updated Status)

Status (2026-03):
- move_type grammar implemented  
- transition model calibrated  
- selector hygiene complete  
- FRAME_ORDER respected  
- scoring scaffold implemented (diagnostic layer)  
- system validated via alpha observation  

This phase is now considered **functionally complete at core level**.

Remaining work:
- refinement only
- no major selector or scoring expansion required at this stage

---

# Phase 11B — Conversational Role Expansion (Content Layer)

Goal:
Improve conversational realism by expanding partner behaviour beyond questions.

Problem addressed:
Current system is structurally sound but overly interrogative (100% question flow).

Scope:
- Introduce EXTEND (self-disclosure) frames
- Add 1–2 EXTEND frames per engine
- Reduce interview-style interaction
- Improve conversational rhythm

Design constraints:
- Content-first (no selector changes)
- No scoring changes
- No new heuristics
- Frames must be:
  - persona-agnostic
  - reusable
  - low-specificity
  - extensible for future persona binding

Acceptance criteria:
- Conversations include natural partner statements
- Reduced interrogation feel
- No regression in flow or stability
- EXTEND frames appear naturally without forcing

---

# Phase 12 — Personal Alpha Testing (Post-Content Expansion)

Goal:
Evaluate whether MandarinOS improves real conversational ability.

Testing duration: 2–4 weeks

Evaluation:
- conversation naturalness
- learner engagement
- speaking confidence
- conversation length
- perceived realism

Data collected:
- session length
- hint usage
- response success rate
- topic transitions
- conversational balance (questions vs statements)

---

# Phase 13 — Closed Beta

Participants: 10–100 learners

Focus:
- real-world usage patterns
- drop-off behaviour
- conversational depth
- persona realism (if introduced)

Key question:
"Does this feel like a real conversation?"

---

# Phase 14 — Data‑Driven Iteration

Improvements based on usage:
- frame quality expansion
- option refinement
- persona realism
- capability model tuning
- speech integration
- vocabulary growth

---

# Extensibility Strategy (Locked)

MandarinOS will evolve primarily through:

- adding higher-value frames and responses
- increasing conversational value density
- improving builder output quality

Not through:
- rewriting existing frames
- expanding selector complexity unnecessarily
- hardcoding conversational behaviour

Critical constraint:

Adding new frames must NOT require changes to:
- selector logic
- scoring system
- runtime architecture

If this constraint is violated, the architecture must be reconsidered.

---

# Implementation Discipline

Cursor must:
- implement one feature at a time
- modify minimal files
- preserve runtime stability
- stop for review after each step

ChatGPT (strategist) must:
- ensure architectural coherence
- prevent over-engineering
- enforce extensibility rules

Project owner must:
- run alpha tests
- evaluate conversational realism
- identify weak frames and low-value responses

---

# Strategic Vision

MandarinOS is a **conversation operating system for language acquisition**.

Development path:

Conversation Loop  
→ Structured Selector  
→ Memory + Context  
→ Adaptive Intelligence  
→ Content Expansion  
→ Persona Layer  
→ Real-world optimisation  

The system is now transitioning from:
**“making it work” → “making it feel human”**
