<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class D: Superseded**
>
> - **Current use:** Retained for traceability of the earlier turn-data contract.
> - **May guide current implementation:** No.
> - **Current authority:** Verified request/response code, `docs/STATE_CONTRACT.md`, and `docs/ANSWER_SOURCE_CONTRACT.md`.
> - **Principal caution:** Its earlier payload and field assumptions have been superseded. Current field meaning and transport behaviour must be verified against code and the approved contracts.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->


# MandarinOS Turn Data Contract (v1)
Purpose: Define the minimal and recommended data exchanged for a single conversation turn
between the UI, runtime conversation state engine, hint cascade system, and selector.

This contract focuses only on highly useful fields needed for the current development stage:
UI + cascading hint system + response panel.

---------------------------------------------------------------------
1. PROMPT PAYLOAD (Runtime → UI)

Fields required to render the prompt.

turn_id
session_id
persona_id
engine_id
branch_id
turn_type

prompt_text_hanzi
prompt_audio_url

Optional support layers (for hint cascade):

prompt_pinyin
prompt_translation

word_items[]
candidate_options[]

---------------------------------------------------------------------
2. WORD ITEM STRUCTURE

Supports cascading help system.

word_id
hanzi
pinyin
english
etymology
character_items[]

---------------------------------------------------------------------
3. CHARACTER ITEM STRUCTURE

Only used when deeper hints are opened.

character
pinyin
meaning
radicals[]
etymology

---------------------------------------------------------------------
4. RESPONSE OPTION STRUCTURE

Used in Assisted Response Mode.

option_id
hanzi
audio_url
pinyin
translation
word_items[]
is_gold

The UI allows the learner to:

• tap an option
• listen to audio
• reveal pinyin
• reveal translation
• reveal deeper hints

---------------------------------------------------------------------
5. UI EVENT PAYLOAD (UI → Runtime)

event_type
turn_id
timestamp
payload

Important events:

PROMPT_RENDERED
AUDIO_PLAYED
HINT_LEVEL_OPENED
WORD_HINT_OPENED
CHARACTER_HINT_OPENED
ASSISTED_RESPONSE_OPENED
OPTION_SELECTED
FREE_SPEECH_SUBMITTED
REPAIR_USED
TURN_COMPLETED

---------------------------------------------------------------------
6. RESPONSE SUBMISSION PAYLOAD

Sent when the learner finishes the turn.

turn_id
response_mode
spoken_text
selected_option_id
hint_level_reached
repair_used
audio_replays
latency_ms

response_mode values:

free_speech
assisted_selection
repair_supported
no_response

---------------------------------------------------------------------
7. TURN EVALUATION PAYLOAD (Runtime Internal)

turn_id
success_level
capability_updates[]
memory_updates[]
energy_update
repair_state
selector_mode_next
engine_switch_recommended

success_level values:

strong_success
partial_success
failure

---------------------------------------------------------------------
8. MINIMUM VIABLE CONTRACT (MVP)

For current development stage, implement only:

PROMPT
turn_id
prompt_text_hanzi
prompt_audio_url
prompt_pinyin
prompt_translation
word_items[]
candidate_options[]

RESPONSE
response_mode
selected_option_id
spoken_text
hint_level_reached
latency_ms

EVENTS
PROMPT_RENDERED
AUDIO_PLAYED
HINT_LEVEL_OPENED
OPTION_SELECTED
FREE_SPEECH_SUBMITTED
TURN_COMPLETED

---------------------------------------------------------------------
Design Rule:

Every prompt supports:
• hint cascade
• assisted responses
• event logging

Adaptive intelligence will be layered later once the UI loop is stable.
