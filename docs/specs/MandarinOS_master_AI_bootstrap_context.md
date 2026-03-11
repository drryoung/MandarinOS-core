
# MandarinOS Master AI Bootstrap Context
Version: v1
Purpose: Provide a concise but comprehensive briefing so AI assistants (ChatGPT, Cursor)
can understand the MandarinOS project architecture, priorities, and development roadmap.

AI roles: ChatGPT = strategist and testing (spec, boundaries, test scenarios, review).
Cursor = senior architect and programmer (all implementation). Cursor as programmer
must make small, step-by-step changes only to avoid drift from the Design Constitution.
GitHub Copilot is no longer used.

---------------------------------------------------------------------
PROJECT IDENTITY

MandarinOS is an **Adaptive Conversation Operating System** for learning Mandarin.

It is not primarily a vocabulary memorization app.
It is a system that trains users to **maintain and navigate real conversations**.

Core idea:

Fluent speakers do not know every word.
They know how to keep the conversation going.

MandarinOS therefore focuses on:
• conversational moves
• curiosity questions
• topic navigation
• repair strategies
• adaptive conversation flow

---------------------------------------------------------------------
CORE LEARNING PHILOSOPHY

Priority order:

1. Conversational continuity
2. Achievable success for the learner
3. Natural topic flow
4. Reinforcement of useful sentence patterns
5. Slight stretch above comfort level

Difficulty escalation is **not the main goal**.
Maintaining a working conversation is the goal.

---------------------------------------------------------------------
PRIMARY USER INTERACTION MODEL

The UI is **sentence-first**.

Display order:

Chinese sentence
→ audio playback
→ learner attempts understanding or response

If needed, hints appear progressively via a cascading help system.

Hint cascade levels:

1. pinyin
2. English translation
3. word-level meaning
4. character etymology
5. radical breakdown

This cascade serves two purposes:
• learner support
• diagnostic signals for adaptive capability tracking

---------------------------------------------------------------------
SESSION DESIGN

Typical session duration: ~10 minutes

Sessions are **conversation journeys**, not topic silos.

A session typically contains:

• 3–5 anchor sentences
• 2–4 new words
• 1 primary conversation engine
• natural bridges to 2–4 engines
• curiosity expansions

Example flow:

Identity → Place → Travel → Food

---------------------------------------------------------------------
CONVERSATION ENGINE STRUCTURE

Major engines currently designed:

Identity
Place
Family
Travel
Food
Study / Work
Interests

Engines contain:

• entry questions
• curiosity loops
• bridge questions
• topic ladders

Example:

Identity engine
→ name
→ origin
→ age / zodiac
→ family
→ study/work

Engines are **connected through natural bridges**.

---------------------------------------------------------------------
ADAPTIVE ARCHITECTURE

MandarinOS adapts conversations using four major systems.

1. Conversation Capability Map
Tracks learner ability across multiple dimensions.

2. Capability Update Rules
Update the capability map using conversation behaviour.

3. Conversation Energy Model
Detects momentum, hesitation, and topic fatigue.

4. Conversation Steering Engine
Moves between engines when appropriate.

These systems together form the **Adaptive Intelligence Layer**.

---------------------------------------------------------------------
CAPABILITY MAP

Learners are not assigned levels.

Instead MandarinOS tracks uneven capabilities.

Capability categories include:

Engine capability
• Identity
• Place
• Family
• Travel
• Food
• Study/Work
• Interests

Conversation moves
• answer
• follow-up
• give reason
• recommend
• react

Curiosity capability
Repair capability

Modality capability
• listening
• speaking
• reading
• character recognition
• pinyin dependence
• translation dependence

Example profile:

Identity 0.84
Travel 0.70
Work 0.31

Listening strong
Reading weak
Pinyin dependence high

---------------------------------------------------------------------
CAPABILITY UPDATE SIGNALS

Each conversation turn produces diagnostic signals.

Signals include:

• response success
• response latency
• hint depth used
• repair usage
• improvement on retry

Hint depth interpretation:

0 no hint → strong comprehension
1 pinyin → reading support needed
2 translation → vocabulary gap
3 gloss → lexical gap
4 etymology / radicals → visual learning behaviour

Updates occur at:

turn level
session level
long-term smoothing

---------------------------------------------------------------------
NEXT QUESTION SELECTOR

The selector determines the best next conversational move.

Inputs:

conversation state
capability map
energy model
conversation memory
persona data
learning constraints

Selector scoring priorities:

1. conversational relevance
2. comprehensibility
3. interest value
4. learning value
5. stretch value (lowest weight)

Stretch should only occur **slightly above comfort level**.

The selector may produce:

• simple question
• follow-up question
• bridge question
• recovery question
• repair support
• memory recall question

---------------------------------------------------------------------
CONVERSATION MEMORY MODEL

Stores facts revealed during conversation.

Examples:

user hometown
job
hobbies
travel experiences

Allows natural recall questions such as:

"你刚才说你喜欢成都，还想再去吗？"

---------------------------------------------------------------------
ENERGY MODEL

Tracks conversational momentum.

Signals:

short answers
hesitation
hint burden
enthusiasm

Possible actions:

continue topic
expand topic
simplify question
pivot to new engine

---------------------------------------------------------------------
CURRENT DEVELOPMENT PRIORITY

Immediate coding focus:

1. finish UI
2. finish cascading hint system
3. enable word-level hint reveal
4. support character / radical expansion
5. add hint usage logging

Avoid implementing full adaptive systems until the UI loop is stable.

---------------------------------------------------------------------
EXPECTED DATA STRUCTURE PER SENTENCE

Each sentence card should support:

Chinese sentence
audio
pinyin
English translation
word glosses
optional etymology
optional radical breakdown
hint usage events
replay/reset support

---------------------------------------------------------------------
LONG-TERM ROADMAP

Phase 1
UI + cascading hint system

Phase 2
conversation runtime loop

Phase 3
adaptive intelligence layer

Phase 4
persona social world

Phase 5
real user conversation matching

---------------------------------------------------------------------
PROJECT SUMMARY

MandarinOS combines:

conversation engines
curiosity systems
repair strategies
visual character learning
adaptive capability modelling

into a single system designed to train learners to **sustain conversations in Mandarin**.

This is why the system is described as a:

Adaptive Conversation Operating System.
