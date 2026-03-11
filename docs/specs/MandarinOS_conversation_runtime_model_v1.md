# MandarinOS Conversation Runtime Model v1

Purpose: Define how the MandarinOS conversation system decides what to
say next during a conversation.

This document bridges the gap between: - conversation engine design -
runtime implementation

MandarinOS should feel like a **conversation partner**, not a scripted
lesson.

------------------------------------------------------------------------

# 1. Core Runtime Concept

MandarinOS operates in **conversation turns** rather than lesson pages.

Each turn evaluates:

current_engine\
current_persona\
memory_anchors\
last_moves\
repair_state

The runtime then chooses the **next conversational move**.

------------------------------------------------------------------------

# 2. The Five Possible Next Moves

At any point the system can choose one of five actions.

## A. Ask a Question

Example:

你是哪里人？\
Where are you from?

Use when: - opening an engine - missing an important memory anchor -
guiding conversation forward

------------------------------------------------------------------------

## B. Reveal a Short Statement

Example:

我老家在苏州。\
My hometown is Suzhou.

Purpose: - reveal persona information - create curiosity triggers

------------------------------------------------------------------------

## C. Reciprocity

Example:

你呢？\
And you?

Use when: - the persona has spoken - the learner should respond -
conversation balance is needed

------------------------------------------------------------------------

## D. Reaction / Filler

Examples:

是吗？ -- Really?\
哦 -- I see\
然后呢？ -- And then?

Purpose: - make conversation feel natural - show listening

------------------------------------------------------------------------

## E. Repair

Used when comprehension fails.

Examples:

什么？ -- What?\
再说一次 -- Say again please\
慢一点 -- Slower please\
听不懂 -- I can't understand

Repair actions may: - repeat - simplify - slow speech - change topic

------------------------------------------------------------------------

# 3. Runtime Decision Priority

When selecting the next move:

Priority order:

1.  Repair (if learner signaled confusion)
2.  Reciprocity (if conversation is unbalanced)
3.  Curiosity trigger (if available)
4.  Ask next engine question
5.  Filler response

------------------------------------------------------------------------

# 4. Core Conversation Rhythm

Most turns should follow this pattern:

Question\
→ Answer\
→ Short statement\
→ Reciprocity

Example:

你是哪里人？\
Where are you from?

我是苏州人。\
I'm from Suzhou.

在上海附近。\
It's near Shanghai.

你呢？\
And you?

------------------------------------------------------------------------

# 5. Memory Influence

Memory anchors guide future conversation.

Example anchors:

-   name
-   hometown
-   family
-   work/study
-   favorite food
-   travel experience

Runtime behaviors:

Ask missing anchors\
Reuse known anchors\
Trigger curiosity from stored anchors

Example:

你不是说你老家在苏州吗？\
Didn't you say your hometown was Suzhou?

------------------------------------------------------------------------

# 6. Persona Influence

Personas affect conversation direction.

Example weighting:

Student → study, food, place\
Parent → family, place, food\
Traveller → travel, place, food

Runtime should prefer engines aligned with persona type.

------------------------------------------------------------------------

# 7. Engine Candidate Pool

Each engine provides candidate moves:

Questions\
Loop questions\
Trigger statements\
Bridge questions

Runtime selects among them using:

memory\
persona\
conversation balance\
repair state

------------------------------------------------------------------------

# 8. Engine Switching

Switch engines when:

Bridge question occurs\
Curiosity trigger points elsewhere\
Repair requires easier topic\
Engine loops are exhausted

Example:

Place → Food\
Family → Study\
Travel → Food

------------------------------------------------------------------------

# 9. Engine Weighting

Avoid rigid scripts.

Not:

Identity → Place → Food → Travel

Instead use weighted transitions:

Identity → Place (strong) Place → Food or Family Food → Travel Family →
Study/Work

------------------------------------------------------------------------

# 10. Minimal Runtime State

The runtime likely needs only:

current_engine\
current_persona\
memory_anchors\
last_two_moves\
repair_state\
who_spoke_last

This small state object is sufficient to guide dynamic conversation.

------------------------------------------------------------------------

# 11. Anti‑Interrogation Rule

No more than **two questions in a row**.

If two questions have occurred:

prefer

statement\
filler\
reciprocity

------------------------------------------------------------------------

# 12. Suggested Initial Implementation

Simple runtime algorithm:

1.  Check repair state
2.  Check reciprocity need
3.  Check curiosity trigger availability
4.  Select candidate from engine pool
5.  Apply bridge if strong

------------------------------------------------------------------------

# 13. Simplest Conceptual Summary

MandarinOS conversation flow:

Ask\
→ Listen\
→ Reveal\
→ Invite\
→ Bridge

Where:

Ask = question\
Listen = process learner response\
Reveal = short statement / trigger\
Invite = 你呢？ or follow-up\
Bridge = move to next engine
