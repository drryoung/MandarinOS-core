
# MandarinOS Conversation Memory Model v2

Purpose:
Allow MandarinOS conversations to continue across sessions by remembering relevant facts about personas and the learner.

This enables relationship-like interactions instead of isolated practice sessions.

--------------------------------------------------
1. TWO-SIDED MEMORY

A. What the learner knows about the persona

Examples:
- Zhang Rui is from Shanghai
- Zhang Rui studies computer science
- Zhang Rui likes noodles
- Zhang Rui’s father is Wang Wei

B. What the persona knows about the learner

Examples:
- learner is from Dunedin
- learner likes hotpot
- learner has children
- learner worked in IT

--------------------------------------------------
2. MEMORY ATTACHED TO PERSONA

Memory must be stored relative to the persona.

Example:

persona_id → memory_of_learner
persona_id → learner_memory_of_persona

Example:

Zhang Rui knows learner likes hotpot
Wang Wei knows learner is from Dunedin

--------------------------------------------------
3. FOUR MEMORY LAYERS

Layer 1 — Global learner memory

Facts true across the whole app.

Examples:
- learner name
- learner hometown
- favorite food
- profession

Layer 2 — Persona-specific learner memory

Example:
Zhang Rui knows learner likes hotpot
Wang Wei knows learner has children

Layer 3 — Persona facts

Stable facts about the persona.

Examples:
- Zhang Rui is a student
- Liu Fang works in Shenzhen

Layer 4 — Session memory

Temporary conversation state.

Examples:
- current engine
- recent topic
- energy level
- repair state

--------------------------------------------------
4. WHAT SHOULD BE REMEMBERED

Identity
- name
- nickname
- age

Place
- hometown
- current city

Family
- siblings
- partner
- children

Study / Work
- student or worker
- major
- university
- job
- industry

Food
- favorite food
- spice preference

Travel
- places visited

Opinions / ambitions
- wants to start a business
- industry interest

--------------------------------------------------
5. MEMORY STRENGTH

Weak
Heard once

Medium
Clearly stated

Strong
Repeated or confirmed

Example:

favorite_food = hotpot (strong)
industry_interest = AI (medium)

--------------------------------------------------
6. MEMORY ACTIONS

Capture
Store a new fact

Confirm
Check a fact

Reuse
Bring back a known fact

Update
Replace outdated information

Deepen
Ask deeper follow-up

--------------------------------------------------
7. RETURN CONVERSATION PATTERNS

Warm recall

Example:
Last time you said you’re from Dunedin.

Confirm and deepen

Example:
You still want to work in banking?

Fresh restart

Ignore memory for drill mode.

--------------------------------------------------
8. BASIC DATA STRUCTURE

global_learner_memory

persona_profiles

persona_to_learner_memory

session_state

Example:

global_learner_memory:
  hometown = Dunedin
  favorite_food = hotpot

persona_profiles:
  zhang_rui:
    city = Shanghai
    study = computer science

persona_to_learner_memory:
  zhang_rui:
    knows:
      hometown = Dunedin
      favorite_food = hotpot

session_state:
  current_engine = Study/Work
  session_mode = mixed
  energy = medium

--------------------------------------------------
9. HUMAN-LIKE MEMORY RULE

Memory should support conversation, not act like a database.

Use memory sparingly and naturally.

Example:

Better:
Last time you said you like hotpot. Have you had good hotpot recently?
