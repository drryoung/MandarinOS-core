# MandarinOS Laptop Handoff Briefing — UI + Cascading Help Priority

Project: MandarinOS

Purpose:
This briefing transfers the main conceptual decisions from today’s design work into a form that ChatGPT on the laptop can use immediately while coding the UI and cascading help system.

--------------------------------------------------
1. IMMEDIATE PRIORITY

The immediate coding priority is still:

1. finish the UI
2. finish the cascading help / hint system
3. avoid over-implementing higher-level adaptive systems too early

Today’s design work matters, but most of it should influence the UI as **architecture direction**, not as large new code branches yet.

In other words:

- DO implement what affects the current UI and hint flow
- DO NOT yet try to fully implement the entire adaptive conversation operating system

--------------------------------------------------
2. WHAT FROM TODAY IS IMMEDIATELY RELEVANT TO UI

The most relevant decisions for the current build are these:

A. Progressive Hint Cascade is a core MandarinOS feature

Sentence should appear first in Chinese characters.
Audio should play / be available first.
Hints should reveal progressively, not all at once.

Canonical hint cascade:

1. pinyin
2. English translation
3. word meaning
4. character etymology
5. radical breakdown

This is not just help text.
It is a diagnostic and learning system.

B. MandarinOS should be capability-based, not level-based

The system should eventually adapt based on:
- hint usage
- response quality
- response speed
- repair usage

For now, the UI should be built so that this data can be captured later.

C. Sessions are short conversation journeys, not topic silos

A single session may touch multiple engines naturally.
Do not design the UI as if one session = one engine only.

D. The key design word is adaptive

The app should eventually choose what to ask next based on the learner’s actual performance.

--------------------------------------------------
3. WHAT SHOULD BE IMPLEMENTED NOW VS LATER

IMPLEMENT NOW (UI / hint system layer)

- sentence-first display
- audio-first interaction
- tap/click to reveal hints progressively
- per-word hint reveal support
- per-character / radical expansion support if available
- logging / event hooks for hint usage
- minimal UI support for repeated conversation turns
- ability to reset / replay a conversation loop

PREPARE FOR LATER, BUT DO NOT FULLY IMPLEMENT YET

- adaptive steering engine
- energy model
- conversation memory model
- social world / persona network logic
- capability map logic
- full SM-2 integration with anchor deck

The UI should leave room for these systems.

--------------------------------------------------
4. CANONICAL UI / LEARNING FLOW

The intended MandarinOS interaction flow is:

Sentence appears in Chinese characters
→ audio plays or can be played
→ learner attempts response / comprehension
→ if stuck, user reveals hint level 1
→ if still stuck, user reveals deeper hint levels
→ conversation continues

This means the UI must be optimized around:
- sentence cards
- progressive reveal
- low friction
- mobile-friendly clarity

--------------------------------------------------
5. HINT SYSTEM PRINCIPLE

The hint system should not feel like “show me the answer”.

It should feel like:

help me stay in the conversation

That means each hint level should preserve as much productive struggle as possible.

Recommended interpretation:

Hint 1: pinyin
- support decoding
- lowest-cost reading support

Hint 2: translation
- full sentence meaning
- use only when needed

Hint 3: word meaning
- helps connect sentence to reusable vocabulary

Hint 4: etymology
- memory aid
- visual / conceptual support

Hint 5: radical breakdown
- deepest visual learning support
- especially useful for weak readers

--------------------------------------------------
6. VERY IMPORTANT UX PRINCIPLE

The user may be:
- strong at listening
- weak at reading
- weak at characters
- stronger with pinyin
- very uneven overall

Therefore the UI must support uneven development.

This means:
- audio matters a lot
- pinyin must be optional and progressive
- translation must not appear too early
- character support should be deep but optional

This is especially important because the user (Raymond) has explicitly noted:
- strong listening is possible
- reading remains weak
- character support matters for retention

--------------------------------------------------
7. HOW TODAY’S CONCEPTUAL WORK SHOULD SHAPE IMPLEMENTATION

Today’s design work established MandarinOS as an:

Adaptive Conversation Operating System

Key architectural layers now locked conceptually:

User Interaction Layer
- characters first
- audio
- progressive hint cascade

Conversation Runtime Layer
- conversation engines
- turns
- ladders
- persona world

Adaptive Intelligence Layer
- conversation steering
- energy model
- memory

Learning Systems Layer
- SM-2 anchor review
- vocabulary frequency control
- capability map

Knowledge Layer
- lexicons
- characters
- etymology
- radicals
- frame tokens
- persona data

For now, only the first two layers need active UI coding.
The others should be respected as future integration points.

--------------------------------------------------
8. WHAT CHATGPT ON LAPTOP SHOULD DO NEXT

Priority order for laptop coding work:

1. finish sentence-first UI interactions
2. finish the cascading hint system
3. make sure hint levels can be triggered cleanly
4. make sure word-level reveal and future character-level reveal are supported
5. add logging hooks so hint usage can later feed adaptive diagnosis
6. preserve replay / reset ability for repeated practice
7. avoid large architectural expansion until UI loop is stable

--------------------------------------------------
9. SUGGESTED IMPLEMENTATION QUESTIONS FOR CHATGPT ON LAPTOP

ChatGPT on laptop should help answer questions like:

- How should the UI reveal hint levels cleanly?
- What exact data structure should one sentence card expose for hint levels 1–5?
- How should per-word hint reveal be stored and rendered?
- What event log should be emitted when hints are opened?
- How should replay / reset work for one turn?
- How do we preserve clean extensibility for later adaptive systems?

It should NOT jump prematurely into:
- social networking features
- full memory system implementation
- complex learner modeling
- broad backend redesign

--------------------------------------------------
10. MINIMAL IMPLEMENTATION CONTRACT FOR NOW

The current UI work should aim to support this future-ready contract:

For each sentence / turn, the UI should be able to access:

- surface Chinese sentence
- audio
- pinyin
- English translation
- word-level glosses
- optional etymology
- optional radical breakdown
- user hint usage events
- replay / reset action

If this contract is clean, many higher-level systems can be added later without rewriting the UI.

--------------------------------------------------
11. WHY THIS MATTERS

Today’s design work was broad:
- conversation engines
- curiosity engine
- adaptive architecture
- memory
- travel / family / work / interests
- marketing / product identity

But the current coding need is narrower:

Finish the UI and make the hint cascade excellent.

That is the correct next move.
If the hint cascade is good, much of the larger MandarinOS vision becomes implementable later.

--------------------------------------------------
12. SHORT MESSAGE TO CHATGPT ON LAPTOP

Use this exact summary if needed:

MandarinOS is now conceptually defined as an Adaptive Conversation Operating System, but immediate implementation priority remains the UI and the progressive hint cascade. The UI should show Chinese characters first, support audio-first interaction, and reveal help progressively in this order: pinyin → English → word meaning → etymology → radicals. Build the UI so it supports per-word reveal, future per-character expansion, replay/reset, and logging of hint usage for future adaptive diagnosis. Do not yet overbuild the higher-level adaptive systems; just keep the UI architecture compatible with them.

--------------------------------------------------
13. FILES CREATED TODAY THAT MATTER MOST FOR LATER

The following conceptual documents were created today / recently and are especially relevant:

- MandarinOS_adaptive_conversation_architecture_v1.md
- MandarinOS_conversation_memory_model_v2.md
- mandarinos_conversation_steering_engine_v1.md
- mandarinos_conversation_energy_model_v1.md
- mandarinos_curiosity_engine_v1.md
- mandarinos_emergency_curiosity_pack_v1.md
- mandarinos_family_engine_v4.md
- mandarinos_study_work_engine_v10.md
- mandarinos_travel_engine_v4.md
- mandarinos_interests_engine_v1.md
- MandarinOS_marketing_positioning_v1.md

For immediate coding, the most relevant among these are:
- adaptive conversation architecture
- curiosity engine
- emergency curiosity / repair
- engine files only as future content direction

--------------------------------------------------
14. FINAL PRIORITY REMINDER

The correct immediate focus is:

excellent UI
+
excellent cascading hint system
+
future-compatible structure

Not full system implementation yet.
