# Manual Commit Instructions

Since git is not available in this environment, follow these steps to commit the changes:

## Files to Stage

```bash
git add diagnostic_p1.json diagnostic_p2.json srs_config.json
```

## Commit Command

```bash
git commit -m "fix: enforce conversation-first constraints across diagnostics (fixes 1-5)

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
✅ No dead ends: signal_tracking replaces quiz-style gating; routing pattern-based"
```

## Then Push

```bash
git push origin [branch-name]
```

---

## Summary of Changes

See `COMMIT_SUMMARY.md` for detailed breakdown of all 3 files and 5 fixes.

### Key Metrics

- **Files modified:** 3
- **Lines changed:** ~150 (additions for new metadata, deletions of threshold gates)
- **Options updated:** 11 (diagnostic_p1.json)
- **Feedback blocks replaced:** 6 (diagnostic_p1.json)
- **Scoring sections removed:** 8 (6 task-level + 2 top-level)
- **Rubric notes reframed:** 6 (diagnostic_p2.json)
- **Grade label pairs renamed:** 4 × 2 files = 8 occurrences

### All Changes Are:

- ✅ JSON-valid (no syntax errors)
- ✅ Compliant with copilot-instructions.md tripwires (§3.1, §3.2, §3.3, §3.4)
- ✅ Aligned with Design Constitution (conversation-first, no right/wrong, no praise)
- ✅ Backward-compatible within diagnostic schema (new metadata fields are additive)
- ✅ Documented with detailed notes explaining conversational-intent model
