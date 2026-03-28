# MANDARINOS — PHASE 12C IMPLEMENTATION BRIEF

Purpose:
Improve multi-turn conversation quality by introducing a lightweight session arc and controlled curiosity behaviour.

This phase is about:
- session-level flow (NOT turn-level correctness)
- soft behavioural shaping (NOT hard rules)
- minimal additions (NO architecture rewrite)

--------------------------------------------------
SECTION 1 — NON-GOALS (CRITICAL)
--------------------------------------------------

Do NOT:
- rewrite selector
- introduce scoring systems
- add new heuristics unrelated to session arc
- implement persona variation or tone variation
- change ASR / repair logic (Phase 10.6)
- change hint system or UI object model

Persona is NOT part of this phase except for consistency (see Section 6).

--------------------------------------------------
SECTION 2 — ADD MINIMAL SESSION STATE
--------------------------------------------------

Extend runtime session state with:

- turns_in_current_engine: int
- loop_count_in_current_engine: int
- engines_visited: list[str]
- recent_confusion_count: int

Rules:
- initialize at session start
- update per turn
- reset loop_count when engine changes

Do NOT persist long-term — session-only.

--------------------------------------------------
SECTION 3 — SOFT SESSION ARC CONSTRAINTS
--------------------------------------------------

Apply as soft bias (NOT hard filters):

1. Loop control
- if loop_count >= 2 → reduce LOOP likelihood
- if loop_count == 0 → allow LOOP freely

2. Engine dwell control
- if turns_in_current_engine >= 4 → increase BRIDGE likelihood
- if turns_in_current_engine <= 2 → prefer staying in engine

3. Reciprocity encouragement
- if no RECIPROCITY used in session → slightly increase its likelihood

4. Engine diversity target
- aim for 2–3 engines per session (do NOT enforce strictly)

Implementation:
- adjust candidate weighting only
- DO NOT eliminate valid candidates

--------------------------------------------------
SECTION 4 — CURIOSITY → TRANSITION POLICY
--------------------------------------------------

Refine LOOP behaviour:

Allow LOOP when:
- user response is meaningful
- loop_count < 2
- no recent confusion

Reduce LOOP when:
- loop_count >= 2
- user shows hesitation/confusion

Transition out of LOOP:

Prefer:
- EXTEND → RECIPROCITY
OR
- LOOP → BRIDGE (if depth reached)

Do NOT allow:
- repeated LOOP chains > 2 without transition

--------------------------------------------------
SECTION 5 — LOW-ENERGY / OVERLOAD DETECTION
--------------------------------------------------

Define overload as:

- recent_confusion_count >= 2
OR
- repair triggered twice in last 3 turns
OR
- repeated weak/empty responses

When overload detected:

- reduce LOOP and EXTEND
- increase BRIDGE or CLOSE likelihood
- prefer simpler frames
- prioritize clarity over exploration

--------------------------------------------------
SECTION 6 — PERSONA (STRICTLY LIMITED)
--------------------------------------------------

Do NOT implement persona variation.

Only ensure:

- partner facts remain consistent within session
- at least one partner fact may be revealed per session (if already supported)
- no random tone/style changes

Persona is a constraint, not a feature in this phase.

--------------------------------------------------
SECTION 7 — SESSION CLOSURE
--------------------------------------------------

When:

- turns >= threshold (~10–15 turns)
OR
- user energy low

Then:

- increase CLOSE likelihood
- optionally include light recap or forward pointer (if already supported)

Do NOT create new content types.

--------------------------------------------------
SECTION 8 — TRACE / OBSERVABILITY
--------------------------------------------------

Add trace fields:

- turns_in_current_engine
- loop_count
- engines_visited
- move_type_selected
- transition_reason (loop_limit / dwell_limit / overload / normal)

Purpose:
- debug session flow
- validate arc behaviour

--------------------------------------------------
SECTION 9 — IMPLEMENTATION RULES
--------------------------------------------------

- All changes must be additive
- All behaviour must fall back to existing Phase 10.5 logic if state missing
- No hard-coded frame-specific logic
- No removal of existing behaviour

--------------------------------------------------
SECTION 10 — SUCCESS CRITERIA
--------------------------------------------------

System should:

- naturally move across 2–3 engines per session
- avoid repetitive looping
- show at least one curiosity loop
- include reciprocity in most sessions
- end without abrupt drop

Do NOT optimize for "personality" or "expression" yet.

--------------------------------------------------
END OF BRIEF
