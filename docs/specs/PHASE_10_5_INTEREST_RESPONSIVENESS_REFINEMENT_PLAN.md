# Phase 10.5 Interest Responsiveness Refinement Plan

## Purpose

Reduce "stays on topic too long" behavior by making selector decisions react quickly when the user gives interesting input.

This is a behavior-layer refinement only:
- no schema changes
- no API contract removals
- no architecture rewrite

## Target Behavior

After an interesting user answer, the next move should look like active listening:
1. short reaction (existing behavior),
2. curiosity follow-up or bridge within 1-2 turns,
3. avoid prolonged same-topic dwell.

## Scope

- File: `scripts/ui_server.py`
- Areas:
  - next-question selector branch in `do_POST`
  - helper functions near slot inference/selector helpers
  - response debug telemetry

## Constants to Add

- `INTEREST_MEDIUM_THRESHOLD = 2`
- `INTEREST_HIGH_THRESHOLD = 3`
- `P_CURIOUS_WHEN_INTEREST_MED = 0.60`
- `P_CURIOUS_WHEN_INTEREST_HIGH = 0.80`
- `P_BRIDGE_WHEN_INTEREST_HIGH = 0.55`
- `MAX_SAME_ENGINE_AFTER_INTEREST = 1`
- `MAX_SAME_SLOT_CHAIN_AFTER_INTEREST = 1`
- `INTEREST_FORCE_WINDOW_TURNS = 1`

## Helper Functions to Add

- `_norm_text(s)`
- `_answer_text_from_last_answer(last_answer)`
- `_stable_gate(seed)`
- `_score_answer_interest(last_answer, slot_names, new_memory_written, cs)`
- `_classify_interest(score)`
- `_topic_chain_exceeded(cs, slot_names)`
- `_should_force_listening_move(cs, interest_level)`

## Selector Decision Refinement

Inside `do_POST` next-question path:

1. Compute `interest_score` and `interest_level` after current slot inference.
2. Set `pending_listening_move` when interest is medium/high.
3. Add a listen-first policy before the current loop/ladder gate:
   - try loop first if depth allows,
   - else bridge,
   - else continue to existing fallback logic.
4. Apply anti-overstay cap using same-engine/same-slot chain counters.
5. Keep identity coherence gate and frame dependency checks unchanged.

## State Fields (lightweight, additive)

Read defaults from `conversation_state` when present:
- `same_engine_chain_count`
- `same_slot_chain_count`
- `last_focus_slot`
- `pending_listening_move`
- `listening_wait_turns`
- `last_interest_level`
- `last_user_text`

Return updated values as optional response fields for the UI/client to use.

## Debug Telemetry Additions

Include in response:
- `interest_score`
- `interest_level`
- `pending_listening_move`
- `listening_wait_turns`
- `listening_move_selected`
- `listening_move_reason`
- `same_engine_chain_count`
- `same_slot_chain_count`
- `last_focus_slot`
- `last_user_text`

## Validation

1. `python -m py_compile scripts/ui_server.py`
2. Restart UI server.
3. Exercise transcript cases:
   - interesting answer with new slot and/or "because/opinion" text
   - minimal short answer
   - repeated answer
4. Verify:
   - curiosity or bridge appears within 1-2 turns after interesting input
   - no incoherent dependency breaks
   - no regression to recovery/reciprocity flow

