# Phase 12C Executive Strategist Brief (One-Page)

**Context:** MandarinOS is now stable and significantly improved in local conversation quality.  
**Current concern:** Global session quality still needs tighter orchestration (persona salience, graceful engine transitions, and a hard 10-minute experience envelope).

---

## What is working now

- Core architecture is stable (Phases 7-11 core complete; 11B/11C + 12B shipped).
- Curiosity and repair loops are more natural than before.
- UI interaction quality is restored (speaker/hint/token exploration/suggested responses).
- Abrupt thread failures and major flow regressions were fixed.

---

## Remaining product gap

The system is smooth turn-to-turn, but not always purposeful session-to-session:

1. **Persona under-salience**  
   Persona exists, but learners do not always feel they are talking to a distinct individual.

2. **Curiosity-to-transition inconsistency**  
   Some transitions are still not clearly motivated by the preceding thread or user energy.

3. **No strict session arc**  
   Experience can drift; there is no enforced 10-minute narrative structure.

---

## Strategic objective for next phase (Phase 12C)

Implement a **10-minute session contract** that guarantees:

- at least **1 learner discovery** (new/expanded user fact),
- at least **1 persona discovery** (new partner fact),
- at least **1 completed curiosity loop**,
- a **graceful close** before fatigue.

Target depth: **2-3 engines per session** (not many shallow hops).

---

## Recommended next-step order (minimal risk)

1. **Session Arc Contract (first)**
   - Encode timebox + outcome targets as explicit requirements.

2. **Persona Salience Pass**
   - Strengthen distinct partner voice/reveal moments (content + reveal policy).

3. **Curiosity-to-Bridge Policy Tuning**
   - Keep curiosity when energy is healthy; bridge gracefully when overload/confusion appears.

4. **Low-Energy Safety Rail**
   - On repeated confusion: simplify, acknowledge, and pivot naturally.

5. **End-of-Session Closure Pattern**
   - Lightweight recap + next-session invitation.

---

## Must-keep guardrails

- No selector rewrite.
- No heavy scoring expansion.
- Content/policy tuning over architectural churn.
- Preserve canonical UI option objects.

---

## KPI set for strategist approval

1. **Persona Salience Rate**  
   % sessions with at least one remembered partner-specific fact.

2. **Dual Discovery Rate**  
   % sessions with both a new learner fact and a new persona fact.

3. **Graceful Transition Rate**  
   % engine changes preceded by coherent acknowledgement/bridge.

4. **Repair Recovery Rate**  
   % confusion events recovered within 2 turns.

5. **Timebox Fit Rate**  
   % sessions ending naturally in 7-10 minutes.

---

## Paste this prompt to ChatGPT strategist

> Read `docs/briefings/PHASE_12C_EXECUTIVE_STRATEGIST_BRIEF.md`.  
> Please provide:  
> (A) agree/challenge this 12C ordering,  
> (B) minimum viable policy spec for curiosity-led transitions under a 10-minute cap,  
> (C) thresholds for low-energy/overload detection,  
> (D) a 1-week validation plan with measurable pass/fail criteria.

