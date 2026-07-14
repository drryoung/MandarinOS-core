<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as the latest named version in the project-roadmap document family.
> - **May guide current implementation:** No.
> - **Current authority:** Verified production code and the nine-document R2 architecture-governance package.
> - **Principal caution:** Being the latest named roadmap version does not make this document current implementation authority. Its milestones and proposed features must be verified individually against code and approved architectural decisions.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS Development Roadmap --- Strategic Plan v2

Purpose: Align ChatGPT (strategist), Cursor (architect/programmer), and
the project owner (reviewer) around a clear and complete development
roadmap for MandarinOS.

This document supersedes **MandarinOS_project_plan_v1.md** by clarifying
the missing architectural phase required to implement full adaptive
conversation intelligence.

Date: 2026-03-13

------------------------------------------------------------------------

# Current Project Status

Phase 7 --- Learning Interaction Layer ✔ Complete\
Phase 8 --- Conversation Loop UI ✔ Complete\
Phase 9 --- Conversation Engine Integration ✔ Signed Off

The system now contains the **core MandarinOS conversation loop**:

Frame → User Response → Partner Acknowledgement → Reciprocity (你呢？) →
Next Frame

This provides a **stable deterministic conversation system**, but it is
**not yet fully adaptive**.

------------------------------------------------------------------------

# Key Architectural Insight

MandarinOS adaptive conversation requires five layers of intelligence:

1.  Conversation Loop Infrastructure\
2.  Conversation Selection Logic\
3.  Memory + Persona Context\
4.  Learner State Modelling\
5.  Adaptive Steering and Repair

Phases 7--9 built layers 1--2.

Phases 10--11 will implement layers 3--5.

------------------------------------------------------------------------

# Phase Overview (Updated)

Phase 7 --- Learning Interaction Layer\
Phase 8 --- Conversation Loop UI\
Phase 9 --- Conversation Engine Activation ✔\
Phase 10 --- Memory + Persona Foundations\
Phase 11 --- Adaptive Conversation Intelligence\
Phase 12 --- Personal Alpha Testing\
Phase 13 --- Closed Beta (10--100 users)\
Phase 14 --- Data‑Driven Iteration

------------------------------------------------------------------------

# Phase 7 --- Learning Interaction Layer

Goal: Ensure the learner can understand sentences and respond.

Scope: - Frame display - Word click → card panel - Hint cascade (pinyin
→ meaning → etymology) - Response options - "You said" confirmation

Acceptance criteria: - Hints render reliably - Response options
selectable - Card panels stable - No runtime crashes - Responses
recorded in trace

------------------------------------------------------------------------

# Phase 8 --- Conversation Loop UI

Goal: Turn sentence practice into a visible conversation.

New UI component: Conversation transcript panel.

Example flow:

AI: 你叫什么名字？\
You: 我叫 Raymond。\
AI: 很高兴认识你。\
AI: 你呢？

Features: - Transcript panel - Partner acknowledgement - Reciprocity
turn - Question audio - Turn markers

Acceptance criteria: User experiences a clear multi‑turn interaction.

------------------------------------------------------------------------

# Phase 9 --- Conversation Engine Activation ✔

Goal: Activate the Next Question Selector v1.

Selector responsibilities: - choose next frame - bridge across engines -
prevent conversation dead ends

Inputs: - conversation state - current engine - recent frames

Acceptance criteria: - Engine switching works - Conversation continues
across topics - No conversational dead ends - Runtime architecture
remains unchanged

------------------------------------------------------------------------

# Phase 10 --- Memory + Persona Foundations

Goal: Make conversations personal and persistent.

Learner Memory Fields: - learner_name - hometown - lives_in -
job_or_study - family - favourite_food

Persona Network: Conversation partners with stable identities.

Persona data includes: - persona name - hometown - occupation -
interests - food preferences

Selector responsibilities in Phase 10: - avoid repeating known learner
facts - occasionally recall known facts - produce persona‑consistent
dialogue

Acceptance criteria:

A learner fact entered in Session 1 can influence conversation in
Session 2.

Conversation feels **continuous across sessions**.

------------------------------------------------------------------------

# Phase 11 --- Adaptive Conversation Intelligence

This phase implements the **adaptive intelligence described in the
MandarinOS design specifications**.

New systems introduced:

## Capability Map

Tracks learner development across dimensions:

-   comprehension
-   recall
-   speaking confidence
-   topic familiarity

## Energy Model

Tracks learner engagement and fatigue using signals such as:

-   hint usage
-   response latency
-   response completeness
-   conversation length

## Repair System

Handles conversational breakdowns:

-   misunderstanding
-   confusion
-   learner hesitation

## Adaptive Selector Logic

The selector evaluates signals including:

-   capability map
-   learner energy
-   hint usage
-   learner memory
-   persona context

Possible conversation moves:

-   ask_question
-   follow_up_question
-   recall_check
-   curiosity_prompt
-   topic_bridge
-   repair_move
-   persona_story

Acceptance criteria:

The system dynamically adapts conversation difficulty, topic choice, and
conversational strategy based on learner interaction signals.

This phase transforms MandarinOS from a **scripted conversation system**
into a **fully adaptive conversational learning system**.

------------------------------------------------------------------------

# Phase 12 --- Personal Alpha Testing

Goal: Determine whether MandarinOS meaningfully improves speaking
ability.

Testing duration: 2--4 weeks.

Evaluation questions:

-   Does recall improve?
-   Does speaking confidence improve?
-   Are conversations sustained longer?
-   Do hints meaningfully assist comprehension?

Data collected:

-   session length
-   hint usage
-   response success rate
-   topic transitions

------------------------------------------------------------------------

# Phase 13 --- Closed Beta

Participants: 10--100 learners.

Metrics:

-   session duration
-   conversation depth
-   hint usage
-   drop‑off points
-   engine transitions

Key question:

"Does this feel like a real conversation?"

------------------------------------------------------------------------

# Phase 14 --- Data‑Driven Iteration

Improvements based on real usage data:

-   selector logic tuning
-   curiosity prompts
-   persona realism
-   speech input
-   vocabulary expansion
-   capability model refinement

------------------------------------------------------------------------

# Implementation Discipline

Cursor must:

-   implement one feature at a time
-   modify minimal files per step
-   preserve runtime stability
-   stop after each change for review

ChatGPT (strategist) must:

-   ensure architectural coherence
-   prevent scope creep
-   maintain alignment with the design constitution

Project owner responsibilities:

-   perform regular alpha testing
-   evaluate conversation realism
-   identify weak frames and awkward responses

------------------------------------------------------------------------

# Strategic Vision

MandarinOS is not simply a language learning app.

It is a **conversation operating system for language acquisition**.

Development follows a layered architecture:

Conversation Loop\
→ Deterministic Selector\
→ Memory + Persona\
→ Adaptive Intelligence\
→ Data‑Driven Optimisation

This roadmap ensures each layer is implemented in the correct order
while preserving system stability.
