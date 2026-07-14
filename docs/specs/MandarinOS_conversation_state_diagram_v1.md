<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class D: Superseded**
>
> - **Current use:** Retained as the earlier conversation-state diagram and design snapshot.
> - **May guide current implementation:** No.
> - **Current authority:** Verified code and `docs/STATE_CONTRACT.md`.
> - **Principal caution:** This diagram has been superseded and must not be relied upon for current state ownership, transport, reset, or persistence behaviour.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS Conversation State Diagram v1

Purpose: Show how a MandarinOS conversation moves between engines,
turns, memory, repair, and session modes.

This document is a visual implementation aid for the conversation
runtime.

------------------------------------------------------------------------

# 1. Top-Level Conversation Flow

``` text
Session Start
   ↓
Select Session Mode
   ↓
Select Persona
   ↓
Select Entry Engine
   ↓
Run Conversation Turn Loop
   ↓
Store / Update Memory
   ↓
Continue / Bridge / End Session
```

------------------------------------------------------------------------

# 2. Session Mode Layer

MandarinOS supports three session modes.

``` text
Session Mode
 ├─ Drill
 ├─ Mixed
 └─ Continue
```

### Drill

-   ignore most learner memory during turn selection
-   repeat core phrases
-   prioritize P1 loops

### Mixed

-   light memory reuse
-   still allows repetition

### Continue

-   strong memory reuse
-   follow-up based on past facts

------------------------------------------------------------------------

# 3. Entry Engine Selection

A session can begin from more than one entry point.

``` text
Entry Engine
 ├─ Identity
 └─ Place
```

Identity is useful for: - introductions - name / age / family / work

Place is useful for: - casual encounters - hometown / city / country /
food / travel

------------------------------------------------------------------------

# 4. Runtime Turn Loop

Each turn follows the same basic cycle.

``` text
Current Engine
   ↓
Check Repair State
   ↓
Check Reciprocity Need
   ↓
Check Curiosity Trigger
   ↓
Select Next Move
   ↓
Render / Speak Turn
   ↓
Capture Learner Response
   ↓
Update Memory
   ↓
Stay / Bridge / Repair / End
```

------------------------------------------------------------------------

# 5. The Five Next-Move Types

``` text
Next Move
 ├─ Ask Question
 ├─ Reveal Statement
 ├─ Reciprocity (你呢？)
 ├─ Filler / Reaction
 └─ Repair
```

### Ask Question

Used to: - open an engine - fill a missing memory anchor - move
conversation forward

### Reveal Statement

Used to: - expose persona information - create curiosity

### Reciprocity

Used to: - keep conversation balanced - invite learner participation

### Filler / Reaction

Used to: - sound human - acknowledge what was said

### Repair

Used when: - the learner is confused - speech needs slowing / repeating
/ simplifying - topic needs resetting

------------------------------------------------------------------------

# 6. Engine-Level Flow

Within an engine, the preferred rhythm is:

``` text
Question
→ Answer
→ Short Statement
→ Reciprocity / Follow-up
→ Loop / Bridge
```

Equivalent P1 loop structure:

``` text
Entry
→ Orientation
→ Description
→ Personal
→ Loop
→ Bridge
```

------------------------------------------------------------------------

# 7. Engine Transition Logic

Conversation engines are connected by weighted bridges.

``` text
Identity
 ├─ Place
 ├─ Family
 └─ Study/Work

Place
 ├─ Food
 ├─ Travel
 ├─ Family
 └─ Place (loop)

Food
 ├─ Travel
 ├─ Place
 └─ Food (loop)

Family
 ├─ Study/Work
 ├─ Place
 └─ Persona-linked conversation

Study/Work
 ├─ Place
 ├─ Family
 └─ Study/Work (loop)

Travel
 ├─ Food
 ├─ Place
 └─ Travel (loop)
```

These are preferences, not rigid scripts.

------------------------------------------------------------------------

# 8. Memory Layer

Memory sits underneath every turn.

``` text
Memory
 ├─ Persona Memory
 ├─ Learner Memory
 ├─ Session Memory
 └─ Session Mode Activation
```

### Persona Memory

Predefined facts about the current persona.

### Learner Memory

Facts learned about the user.

### Session Memory

Temporary state: - current engine - who spoke last - recent moves -
repair state

### Session Mode Activation

Controls how strongly memory is reused: - Drill = weak / mostly
ignored - Mixed = partial - Continue = strong

------------------------------------------------------------------------

# 9. Repair Subsystem

Repair interrupts the normal turn flow when needed.

``` text
Repair Trigger
   ↓
Select Repair Action
   ↓
Repeat / Slow / Simplify / Change Topic
   ↓
Return to Turn Loop
```

Typical repair ladder:

``` text
什么？        → repeat
再说一次      → repeat clearly
慢一点        → slower audio / pinyin
我不懂        → simplify
什么意思？    → gloss key word
听不懂        → topic reset
```

------------------------------------------------------------------------

# 10. Topic Reset / Safe Restart

If conversation difficulty rises too far, MandarinOS should reset
smoothly.

``` text
Difficult Topic
   ↓
Repair Trigger
   ↓
Safe Engine Choice
   ↓
Fresh P1 Loop
```

Typical safe engines: - Identity - Place - Food

This prevents the conversation from collapsing.

------------------------------------------------------------------------

# 11. Reciprocity Rule

At some point the system should invite the learner to answer.

``` text
Persona says something
   ↓
你呢？
   ↓
Learner answers
   ↓
Memory capture opportunity
```

Example:

``` text
我喜欢面。你呢？
→ 我喜欢火锅。
→ store favorite_food = hotpot
```

------------------------------------------------------------------------

# 12. Minimal Runtime State Object

A first implementation likely only needs:

``` text
current_engine
current_persona
session_mode
learner_memory
persona_memory
last_two_moves
repair_state
who_spoke_last
```

This is enough to drive dynamic conversation.

------------------------------------------------------------------------

# 13. Simplest One-Line Summary

``` text
Ask
→ Listen
→ Reveal
→ Invite
→ Bridge
→ Remember
```

That is the core MandarinOS conversation state machine.
