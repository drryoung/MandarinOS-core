# Strategist proposal — Phase 12C priorities (curiosity-led, persona-visible, 10-minute session design)

**Purpose:** Propose the next steps for MandarinOS after current Phase 12B stabilization, focusing on your stated concerns:
- personas may not be used strongly enough,
- curiosity/engine transitions may not be graceful enough,
- sessions should stay within ~10 minutes,
- each session should discover something interesting about learner and/or persona.

**Date:** 2026-03-27  
**Audience:** ChatGPT (strategist), project owner, implementer

---

## 1) Strategic assessment of current state

The project appears to be in a good position technically:
- Core architecture is stable (Phases 7-11 complete at core level).
- 11B/11C added role expansion and persona discoverability hooks.
- 12B repaired major UX regressions and abrupt-thread behavior.

But your concern is valid: **the system can feel locally smooth without feeling globally purposeful**.

Current gap is not core architecture. It is **session choreography**:
- persona signals are present but not always salient,
- curiosity appears but does not yet reliably create a "discovery journey",
- engine transitions are safer than before but still not consistently "motivated",
- session objective/timebox is implicit, not explicit.

---

## 2) Proposed next phase objective (Phase 12C)

### Objective
Define and enforce a **10-minute conversation arc** that is curiosity-led, persona-grounded, and gracefully adaptive to user energy/comprehension.

### Success condition
In one session, the learner should feel:
1. "I discovered something about this partner (persona)."
2. "The partner discovered something about me."
3. "The conversation ended at a natural point before fatigue."

---

## 3) Recommended work order (minimal architecture churn)

Follow this order to preserve the locked extensibility strategy.

### Step A — Session arc contract (highest priority)
Add a strategist-level "session contract" before any deeper tuning:
- Session target duration: 7-10 min (hard cap 10 min).
- Session target depth: 2-3 engines max (not 5+ shallow hops).
- Session target outcomes:
  - 1 learner fact captured (new or enriched),
  - 1 persona fact revealed (new this session),
  - 1 curiosity loop completed (question + follow-up answer).

This should be treated as a product-level requirement, not just telemetry.

### Step B — Persona salience pass
Persona is technically present but should be made narratively visible:
- Ensure each persona contributes a distinct "voice signature" in EXTEND moments.
- Ensure at least one persona-specific reveal appears by mid-session.
- Prefer differences in values/preferences/background rather than just labels.

No selector rewrite required; this is primarily content and reveal policy tuning.

### Step C — Curiosity-to-bridge policy tuning
Refine "when to stay curious" vs "when to transition":
- If user answer is meaningful and energy is healthy: one curiosity extension.
- If comprehension drops or energy drops: graceful bridge with acknowledgement.
- If engine has already yielded a good nugget: bridge to second engine intentionally.

Key principle: **bridge should feel earned**, not random.

### Step D — Low-energy safety rail (graceful degradation)
Add a soft "conversation load" behavior:
- When repeated repair, short answers, or confusion signals accumulate:
  - simplify language,
  - reduce loop depth,
  - offer easier adjacent topic,
  - preserve relationship tone (encouraging, not abrupt).

This should reuse existing repair/recovery mechanisms rather than new architecture.

### Step E — End-of-session closure pattern
Introduce a light closing pattern near minute 9-10:
- quick recap ("今天我知道了…"),
- optional mirror question,
- optional invitation to continue next session.

This turns 10-minute cap into a satisfying finish, not sudden stop.

---

## 4) Concrete strategist metrics to require next

Define these before implementing more behavior changes:

1. **Persona Salience Rate**
   - % sessions where learner can correctly identify a partner-specific fact by end.

2. **Meaningful Discovery Rate**
   - % sessions with at least:
     - one new learner fact captured, and
     - one new persona fact revealed.

3. **Graceful Transition Score**
   - % engine changes preceded by a semantically coherent bridge/acknowledgement.

4. **Repair Recovery Success**
   - After confusion event, % sessions that recover into productive dialogue within 2 turns.

5. **Timebox Fit**
   - % sessions ending naturally in 7-10 minutes (not drifting long, not ending too early).

---

## 5) Suggested implementation boundaries (to avoid regressions)

- Keep "no selector rewrite" constraint.
- Prefer policy + content + ordering refinements.
- Keep UI on canonical option-panel objects (already enforced by rule).
- Treat console warning cleanup as observability hygiene, not primary product work.

---

## 6) Immediate next sprint recommendation (1-2 weeks)

If we run a short sprint now, prioritize:
1. Session arc contract + telemetry fields.
2. Persona salience content pass (EXTEND + discoverable facts by engine).
3. Curiosity-to-bridge threshold tuning for low energy / low comprehension.
4. End-of-session closure message pattern.

Defer:
- Major scoring expansion,
- Heavy selector complexity,
- Broad architecture changes.

---

## 7) Questions for ChatGPT strategist

1. Do you agree with introducing a strict 10-minute session contract now?
2. Should persona salience be optimized before broader engine-diversity tuning?
3. What is the minimum policy set for "curiosity-led but graceful transition" without overfitting?
4. What exact threshold signals should trigger low-energy simplification?
5. What closure pattern best preserves motivation for the next session?

---

## 8) Paste-in prompt for ChatGPT strategist

> Read `docs/briefings/PHASE_12C_STRATEGIST_PROPOSAL_CURIOSITY_PERSONA_SESSION_ARC.md`.  
> Please respond with:  
> (A) confirm/challenge this next-phase ordering,  
> (B) propose the minimum viable policy spec for curiosity-led transitions under a 10-minute cap,  
> (C) propose concrete thresholds for low-energy/overload detection,  
> (D) suggest a 1-week validation plan with measurable pass/fail criteria.

---

*End of strategist proposal.*
