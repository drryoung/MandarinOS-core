
# MandarinOS Runtime Conversation State Engine
Version: v1 (updated)
Purpose: Define the real-time state machine that runs MandarinOS conversations.

This engine coordinates:
- UI prompt rendering
- learner interaction
- cascading hints
- response assistance
- capability diagnostics
- conversation steering
- next-question selection

---------------------------------------------------------------------
CORE PRINCIPLE

MandarinOS is a conversation trainer.

The runtime engine must prioritize:
1. conversational continuity
2. learner success
3. natural topic progression
4. useful phrase reinforcement
5. slight stretch only when appropriate

The system should keep the conversation alive even when the learner cannot respond independently.

---------------------------------------------------------------------
STATE OBJECT (MINIMUM)

session_id
persona_id
session_mode
current_engine
current_branch
current_turn_type
current_energy
hint_burden
recent_turns
recent_anchors
engine_path
memory_context
capability_snapshot
repair_state
selector_mode

---------------------------------------------------------------------
MAIN RUNTIME STATES

READY
PROMPT_RENDERED
WAITING_FOR_RESPONSE
HINT_INTERACTION
RESPONSE_EVALUATION
STATE_UPDATE
NEXT_MOVE_SELECTION
REPAIR_MODE
SESSION_REVIEW

---------------------------------------------------------------------
TURN CYCLE IN PRACTICE

Step 1 — Render Prompt

Display Chinese sentence.

Example:
你喜欢做什么？

Audio available or auto-played.

---------------------------------------------------------------------
Step 2 — Learner Interaction

The learner first has the opportunity to answer freely.

Possible interaction paths:

A. Free spoken response
Learner answers naturally.

B. Free response hesitation or recognition failure
The learner hesitates, does not know what to say, or the system cannot confidently interpret the speech.

C. Assisted Response Mode

The system presents candidate response options.

The learner may:

• tap a response option
• listen to option audio
• open pinyin
• open translation
• reveal deeper hints via cascading help
• replay the prompt audio
• retry speaking

This allows the learner to stay inside the conversation even when they cannot generate an answer independently.

---------------------------------------------------------------------
Step 3 — Evaluate Interaction

The system evaluates:

• response success
• response latency
• hint depth used
• repair usage
• response mode

Example diagnostic outcomes:

answered freely
answered after hints
selected option with pinyin
selected option with translation
multiple audio replays
no usable response

---------------------------------------------------------------------
Step 4 — Update State

Update:

• capability map
• modality signals
• hint burden
• repair state
• conversation energy
• memory context

Free spoken answers indicate stronger mastery than assisted selection.

However, assisted success is still positive progress.

---------------------------------------------------------------------
Step 5 — Select Next Move

The selector chooses the next conversational move.

Possible actions:

• follow-up question
• bridge to new engine
• simplified question
• anchor reinforcement
• repair support
• memory recall

---------------------------------------------------------------------
RESPONSE MODE TRACKING

Each turn should store the response mode.

Possible values:

free_speech
assisted_selection
repair_supported
no_response

---------------------------------------------------------------------
RESPONSE SUPPORT LEVEL

Track support used:

none
audio_only
pinyin
translation
gloss
deep_hint

This helps update learner capability accurately.

---------------------------------------------------------------------
TURN TYPES

ENTRY_QUESTION
FOLLOW_UP
BRIDGE_QUESTION
ANCHOR_REINFORCEMENT
MEMORY_RECALL
REPAIR_SUPPORT
RECAP_OR_RESET

---------------------------------------------------------------------
ENGINE BRANCH TRACKING

Example Travel engine branches:

entry
destination
time
reaction
food_bridge
recommendation
story
future_travel

The state engine tracks active branch and exhaustion.

---------------------------------------------------------------------
ENGINE SWITCHING RULES

Stay in engine if:

• learner coping well
• follow-ups available
• conversation energy high

Switch engine if:

• repeated hint burden
• low engine capability
• natural bridge appears
• topic fatigue detected

---------------------------------------------------------------------
REPAIR STATE TRANSITIONS

STABLE
→ STRUGGLING
→ REPAIR_ACTIVE
→ RECOVERED
→ STABLE

---------------------------------------------------------------------
SELECTOR MODES

NORMAL
SIMPLIFY
REINFORCE
PIVOT
DEEPEN

---------------------------------------------------------------------
RUNTIME EVENT LOG

PROMPT_RENDERED
AUDIO_PLAYED
HINT_LEVEL_OPENED
WORD_HINT_OPENED
CHARACTER_HINT_OPENED
ASSISTED_RESPONSE_OPENED
OPTION_SELECTED
USER_RESPONSE_SUBMITTED
REPAIR_USED
TURN_EVALUATED
ENGINE_SWITCHED
ANCHOR_REINFORCED
MEMORY_CAPTURED
SESSION_COMPLETED

---------------------------------------------------------------------
SIMPLIFIED RUNTIME LOOP

on_turn_start():
    generate_candidate_moves()
    select_next_move()
    render_prompt()

on_user_interaction(event):
    log_event(event)
    update_hint_state()

on_response():
    evaluate_response()
    update_capabilities()
    update_memory()
    update_energy()
    update_repair_state()
    choose_selector_mode()
    next_turn()

---------------------------------------------------------------------
DESIGN SUMMARY

The Runtime Conversation State Engine answers:

"What is happening in the conversation right now, and what should the system do next?"

It connects:

UI hint cascade
conversation engines
capability map
update rules
next question selector
conversation memory
energy model

This makes it the runtime core of MandarinOS.
