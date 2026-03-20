# MandarinOS Phase 10.6 Mini Spec (ASR Stabilization)

## Goal

Reduce false "not understood" loops while preserving recovery behavior when speech is genuinely unclear.

## Why

Phase 10.5 improved curiosity and topic selection, but real UI traces still show:
- valid free answers rejected in mixed-script identity replies
- repeated "not understood" loops on closed-option frames
- forced topic exits caused by repeated recovery failures

## Scope

- File: `ui/app.js`
- No API contract changes
- No frame schema changes

## Behavior Updates

1. Mixed-script acceptance in open identity frames
- Accept Chinese + Latin name patterns (e.g., "大家叫我Raymond。") in identity open-ended frames.

2. Semantic soft-match for selected closed frames
- If unmatched transcript still clearly expresses expected meaning, accept and continue.
- Initial frame set:
  - `p2_id_2` (nickname)
  - `f_food_famous_dish` (dish/no famous dish)
  - `p2_fa_2` (family frequency)
  - `p2_wk_1` (work reason)

3. Two-strike graceful fallback
- If same frame has 2 consecutive unmatched attempts but answer is substantive, accept and continue.
- Prevents endless repair loops.

## Trace Additions

- Existing `unmatched_decision_reason` values extended with:
  - `semantic_soft_match`
  - `two_strike_substantive_fallback`
- `SPEECH_NOT_UNDERSTOOD` includes `unmatched_count`.

## Acceptance Criteria

- Identity mixed-script reply (e.g. "大家叫我Raymond。") is accepted in relevant frame.
- Closed-frame semantically valid free responses are accepted more often.
- Repeated "什么?/再说一次" loops drop significantly on the same frame.
- Recovery still appears when transcript is short/noisy/low confidence.

