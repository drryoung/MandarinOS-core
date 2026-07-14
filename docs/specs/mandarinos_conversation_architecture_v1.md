<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class D: Superseded**
>
> - **Current use:** Retained as the earlier conceptual conversation-architecture record.
> - **May guide current implementation:** No.
> - **Current authority:** Verified conversation code and `docs/CONVERSATION_ARCHITECTURE.md`.
> - **Principal caution:** This pre-R2 conceptual architecture has been superseded and must not be treated as the current engine, frame, selector, or progression contract.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS Conversation Architecture v1

Purpose: Capture the current conceptual spine of MandarinOS conversation
design before implementation details are locked.

------------------------------------------------------------------------

## 1. Conversation Engine Template v1

Each engine should follow this structure:

-   Engine Name
-   Purpose
-   Role (Entry / Hub / Secondary)
-   Likely next engines
-   Core Questions
-   Treasure Questions
-   Loop Questions
-   Trigger Patterns
-   Bridges
-   Typical Paths
-   Example Mini Conversation
-   Notes

Canonical tags:

-   `[?]` = core
-   `[T]` = treasure
-   `[L]` = loop
-   `[B→X]` = bridge to engine X

------------------------------------------------------------------------

## 2. P1 Conversation Loop Structure

Every P1 engine should support the same conversational rhythm:

1.  Entry
2.  Orientation
3.  Description
4.  Personal
5.  Loop
6.  Bridge

This gives each engine a self-sustaining micro-conversation rather than
a static topic list.

Functional goal:

question\
→ answer\
→ follow-up\
→ follow-up\
→ transition

Key idea: P1 is about conversation survival, not topic coverage.

------------------------------------------------------------------------

## 3. Conversation Memory Anchors

MandarinOS should store a small set of memorable identity facts so later
conversations can continue naturally.

Minimal anchor set:

-   name
-   hometown
-   family
-   job_or_study
-   favorite_food
-   travel

These are identity memory anchors --- the kinds of facts people actually
remember about one another.

Example:

-   name = Li Wei
-   hometown = Suzhou
-   family = one younger sister
-   job_or_study = software engineer
-   favorite_food = hotpot
-   travel = Japan

Purpose of memory:

1.  store new facts
2.  reuse facts later
3.  confirm facts naturally in later conversation

------------------------------------------------------------------------

## 4. Current Conceptual Stack

MandarinOS conversation design currently looks like this:

Conversation Engines\
→ P1 Conversation Loops\
→ Conversation Repair System\
→ Emergency Phrases\
→ Conversation Memory Anchors

This is a conceptual architecture, not yet an implementation contract.

------------------------------------------------------------------------

## 5. Important Design Note: Reciprocity

At some stage, conversations should include a 你呢？ reciprocity turn so
either person 1 or person 2 can participate in different conversations.

This matters because real conversations are not one-sided.\
The system should support role switching and reciprocal exchange.

Example:

你叫什么名字？\
→ 我叫 Raymond。\
你呢？\
→ 我叫 David。

This reciprocity requirement should be kept in mind when future
conversation engines are refined.

------------------------------------------------------------------------

## 6. What is stable now

The following are stable enough to preserve:

-   Conversation Engine Template v1
-   P1 Conversation Loop Structure
-   Conversation Memory Anchors
-   Reciprocity requirement (你呢？) as a future conversation feature

------------------------------------------------------------------------

## 7. What is not locked yet

The following are still exploratory:

-   persona generation
-   final engine ordering
-   strict difficulty ladder behavior
-   implementation details of memory storage

------------------------------------------------------------------------

## 8. Guiding principle

MandarinOS should feel like a conversation simulator rather than a
vocabulary lesson system.

The design priority is:

interesting → memorable → usable

not:

routine → filler → textbook
