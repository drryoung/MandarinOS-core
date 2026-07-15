# Progress ↔ Scorecard Interpretation Alignment

**Date:** 2026-05-19  
**Scope:** Interpretation-layer only (no routing, counters, or UI architecture changes)

---

## Mismatches identified

| Area | Before | Risk |
|------|--------|------|
| **Scorecard capability** | Required ≤5 hard unclear for “sustained”; ignored soft unclear + recovery without formal repair | Strong messy sessions scored “moderate” |
| **Progress stability graph** | `100 × (1 − unclear_rate)` only | Noisy but successful sessions looked weak on graph |
| **Recovery in progress** | `recovery_success_rate` from formal repair counts only | Continuation after ambiguity not reflected |
| **Progress headlines** | Mostly stability-score delta | Ignored initiative / persistence trends |
| **Client summary** | Event-count lines (“You responded N times”) competed with server interpretation | Mechanical tone when initiative was high |

---

## Refinements applied

### Shared server helper: `_derive_conversation_signals(sess)`

Single source for:

- `turbulence_survived` — unclear moments but many continued turns  
- `continued_after_ambiguity` — recoveries OR engagement after unclear turns  
- `conversational_persistence`, `extended_imperfect`, `strong_reciprocity`  
- `sustained` / `sustained_messy` — includes messy sustained paths  

Used by:

- `_scorecard_conversation_capability()`  
- `_conversation_stability_score(..., sess)` (progress bonus only)  
- `_build_progress_snapshot()` → `progress_signals`  

### Scorecard copy

More survivability-focused lines and headlines (see tests in `test_scorecard_interpretation.py`).

### Progress graph score

Same field name `conversation_stability_score`; formula adds capped **+20 engagement bonus** from signals.  
**Scorecard stability row labels are unchanged** (`_scorecard_stability` untouched).

### Progress headlines (`buildProgressHeadline`)

Now also considers turn length trend, questions-back trend, and `progress_signals.turbulence_survived`.

---

## Historical snapshot compatibility

| Field | Compatible? |
|-------|-------------|
| Snapshot schema | Yes — additive `progress_signals` only |
| Old snapshots without `progress_signals` | Headlines fall back to stability/turn trends |
| Old `conversation_stability_score` values | Frozen at save time; new sessions use bonus formula |

No migration required.

---

## Philosophy

Progress and scorecard both reward **staying alive in conversation**, not linguistic cleanliness.
