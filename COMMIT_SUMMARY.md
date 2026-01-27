# Commit Summary: Conversation-First Constraint Implementation (Fixes 1-5)

**Date:** January 27, 2026  
**Status:** Ready for commit  
**Files Modified:** 3

---

## Overview

This commit implements all 5 fixes to enforce conversation-first constraints across MandarinOS diagnostics, in compliance with `.github/copilot-instructions.md` and the Design Constitution.

---

## Files Modified

### 1. `diagnostic_p1.json` (655 lines)

**Fix 3: Option Marking Schema**
- **Lines 35-50, 125-165, 250-275, 380-410, 455-475, 575-600**
- Replaced all 11 instances of `"is_correct": true` with new schema:
  - `target_frame`: References the expected frame (e.g., "frame.greeting.hello")
  - `frame_slots_satisfied`: Array tracking which slots (if any) are filled
  - `intent_tags`: Semantic intent labels for validation
  - `quality_signal`: Internal metadata ("gold" for target options)
- **Compliance:** Turn option invariant (§3.1), frame-slot invariant (§3.2)

**Fix 1: Response Model Replacement**
- **Lines 77-81, 184-188, 277-281, 383-387, 460-464, 593-597**
- Replaced evaluative feedback blocks with conversational response_model:
  - Removed "correct" feedback messages (e.g., "对！很好！")
  - Removed incorrect feedback hints
  - Added partner's natural next conversational turn
  - Each response models the dialogue continuation without evaluation
- **Compliance:** Design Constitution (no right/wrong, no praise tokens)

**Fix 4: Silent Signal Tracking**
- **Lines 85-99 (p1_greeting), 190-200 (p1_name), 275-285 (p1_nationality), 388-398 (p1_location), 461-471 (p1_yesno), 590-600 (p1_opinion)**
- Replaced 6 task-level `scoring` sections with `signal_tracking`:
  - Removed `pass_threshold` (0.8), `partial_threshold` (0.5)
  - Removed metrics and accuracy weighting
  - Added primary/secondary signal metadata
  - Added `silent_extraction: true` flag
- **Lines 600-615: Replaced `placement_rules` section**
  - Removed explicit score thresholds
  - Added `signal_aggregation` model
  - Included confidence downgrade triggers (option count, gold presence, signal extraction failures)
- **Compliance:** Diagnostic resilience (§3.4), no arbitrary thresholds

---

### 2. `srs_config.json` (191 lines)

**Fix 2: Grading Label Transformation**
- **Lines 4-12**
- Replaced evaluative grade meanings:
  ```json
  // Before
  "0": "fail"        → "0": "lapse_signal"
  "1": "hard"        → "1": "slow_recall_signal"
  "2": "good"        → "2": "routine_recall_signal"
  "3": "easy"        → "3": "fluent_recall_signal"
  ```
- SM-2 formula and `grade_to_sm2_q` mapping unchanged; only semantic interpretation shifted
- **Compliance:** Removes teacher-grader mental model from system infrastructure

---

### 3. `diagnostic_p2.json` (541 lines)

**Fix 2: Grading Label Transformation**
- **Lines 8-16**
- Same transformation as srs_config.json: "fail/hard/good/easy" → signal-based labels
- Replaced old `pass_threshold` and `routing_thresholds` with `signal_extraction` guidance
- **Compliance:** Internal consistency across diagnostic and SRS systems

**Fix 4: Remove Scoring Thresholds**
- **Lines 8-26 (top-level scoring section)**
- Removed:
  - `pass_threshold.per_task_average_min: 2`
  - `pass_threshold.overall_average_min: 2`
  - `routing_thresholds.engine_gap_if_avg_below: 2`
  - `routing_thresholds.skill_gap_if_avg_below: 2`
- Added `signal_extraction` object describing silent extraction model
- **Compliance:** Diagnostic resilience (§3.4)

**Fix 5: Rubric Notes Reframed**
- **Lines 76-79, 131-134, 174-177, 328-331, 376-379, 432-435**
- All 6 task rubric notes transformed from grammar-correctness to conversational-intent:

| Task | Before | After |
|------|--------|-------|
| p2_t1_planning | "Produces...with correct patterns..." | "User demonstrates planning intent...; routing signal: engine_Life.planning = ready" |
| p2_t2_opinion_reason | "Uses...pattern correctly" | "User demonstrates causal reasoning intent...; can link opinion to supporting reason" |
| p2_t3_story_sequence | "Maintains correct temporal order..." | "User demonstrates narrative sequencing intent; manages temporal markers...to convey story coherence" |
| p2_t6_family_frequency | "Produces...sentence correctly" | "User demonstrates family relationship identification intent; can produce role-aware responses..." |
| p2_t7_work_problem | "Uses patterns correctly..." | "User demonstrates problem-solving communication intent...; can articulate issue and suggest solution" |
| p2_t8_hobby_reason | "...patterns correctly" | "User demonstrates preference comparison intent...; can produce both question and opinion patterns" |

- **Compliance:** Design Constitution (frame-first, intent-based, no correctness framing)

---

## Compliance Checklist

### Engineering Tripwires (copilot-instructions.md §3)

- ✅ **§3.1 Turn option invariant**: Options now include `target_frame`, `quality_signal`, `intent_tags` metadata required by `validateOption(option, targetItem)` function
- ✅ **§3.2 Frame-slot invariant**: `frame_slots_satisfied` explicitly tracks slot presence; at least one option per frame with slots carries slot metadata
- ✅ **§3.3 Hint affordance invariant**: Preserved; signals array unchanged, not gated by removed thresholds
- ✅ **§3.4 Diagnostic confidence downgrade**: Confidence downgrade now only triggers on system faults (option_count < 3, gold missing, signal extraction failed), not arbitrary pass/fail thresholds

### Design Constitution Requirements

- ✅ **No right/wrong framing**: All evaluative language ("correct", "fail", "good", "easy", "对", "很好") removed
- ✅ **No praise tokens**: Removed all feedback praise; partner models next turn without evaluation
- ✅ **No answer reveals**: Diagnostic silently extracts signals; no explicit correctness messaging
- ✅ **Conversation > evaluation**: Feedback replaced with natural dialogue continuation
- ✅ **No dead ends**: Signal-tracking replaces threshold gating; routing based on observed patterns
- ✅ **Intent-driven validation**: Rubric notes now describe what users CAN DO conversationally

---

## Behavioral Changes (User-Facing)

1. **No visible scores or grades** - Diagnostics extract signals silently; user never sees a number, percentage, or "pass/fail" label
2. **No correctness feedback** - Partner doesn't say "对" or "很好" or acknowledge right/wrong; simply continues conversation
3. **Natural conversation flow** - No interruption for assessment; dialogue feels organic
4. **Adaptive routing without gates** - Diagnostic places users and routes engines based on conversational patterns, not arbitrary thresholds
5. **Intent-focused diagnostics** - Observes what users CAN SAY and DO in Chinese, not whether they achieved grammatical perfection

---

## Commit Message

```
fix: enforce conversation-first constraints across diagnostics (fixes 1-5)

- Fix 3: Replace 'is_correct' with 'target_frame', 'frame_slots_satisfied', 'intent_tags', 'quality_signal' in diagnostic_p1.json options. Complies with turn_option_invariant (§3.1) and frame-slot invariant (§3.2) from copilot-instructions.md.

- Fix 2: Rename SRS grading labels from evaluative ('fail', 'hard', 'good', 'easy') to signal-based ('lapse_signal', 'slow_recall_signal', 'routine_recall_signal', 'fluent_recall_signal') in srs_config.json and diagnostic_p2.json. Removes teacher-grader mental model from system infrastructure.

- Fix 1: Replace evaluative feedback blocks ('对', '很好', praise) with conversational response_model in diagnostic_p1.json. Partner naturally continues conversation without correctness messaging. Preserves immersion and complies with Design Constitution (no right/wrong framing, no praise tokens).

- Fix 4: Remove task-level scoring thresholds (pass_threshold, partial_threshold) from all 6 tasks in diagnostic_p1.json. Replace with signal_tracking metadata and silent extraction. Remove pass/fail gates from diagnostic_p2.json top-level scoring. Replace placement_rules with signal_aggregation model. Complies with diagnostic_resilience (§3.4) - no arbitrary thresholds gate content.

- Fix 5: Rewrite all 6 rubric notes in diagnostic_p2.json from grammar-correctness language to conversational-intent language. Notes now clarify what users CAN DO, not whether they got grammar 'right'. Includes routing signals (e.g., 'engine_Life.planning = ready').

Compliance:
✅ Turn option invariant (§3.1): options carry target_frame, quality_signal metadata
✅ Frame-slot invariant (§3.2): slot presence tracked in frame_slots_satisfied
✅ Hint affordance invariant (§3.3): signals preserved, not gated by removed scores
✅ Diagnostic confidence downgrade (§3.4): downgrade only on system faults, not thresholds
✅ Design Constitution: no right/wrong, no praise, no answer reveals, conversation > evaluation
✅ No dead ends: signal_tracking replaces quiz-style gating; routing pattern-based
```

---

## Testing Recommendations

- [ ] Validate JSON syntax on all 3 files (currently passing)
- [ ] Verify option generation pipeline uses new `target_frame` and `quality_signal` fields
- [ ] Verify signal extraction doesn't depend on removed `pass_threshold` fields
- [ ] Verify diagnostic routing uses `signal_aggregation` model, not old `placement_rules`
- [ ] Confirm no user-facing code references removed "fail", "good", "easy" labels
- [ ] Check that response_model fields are rendered in UI (partner's conversation continuation)

---

## Rollback Plan

If issues arise:
1. Revert to previous commit with quiz-style scoring
2. Note: Requires schema migration if content has already been created with new format
3. Recommend: Test thoroughly before rolling back to avoid data inconsistency

---

**Status:** All 5 fixes implemented, JSON validated, ready for peer review and merge.
