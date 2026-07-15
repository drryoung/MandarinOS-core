# Cursor Directive — Apply the MandarinOS Extensibility Strategy

Read and adopt this directive as a standing architectural rule for future MandarinOS work.

## Purpose
MandarinOS is now entering a refinement phase where future gains should come mainly from **adding higher-value frames, responses, and option sets**, not from repeated architectural rework.

Your role is to preserve the current stable architecture while making the system easier to extend.

---

## Core Rule
Treat the current MandarinOS architecture as a **stable extensible base**.

Future improvement should happen primarily by:
- adding better frames
- adding better responses
- adding better options
- improving tagging
- improving builder output quality

Future improvement should **not** primarily happen by:
- rewriting existing frame sets
- hardcoding special conversational cases
- increasing selector complexity without strong evidence
- modifying runtime architecture just to support more content

---

## Required Working Assumption
When evaluating a proposed improvement, first ask:

**Can this be solved by adding or reordering frames/responses/options without changing selector, scoring, or runtime architecture?**

If yes, prefer that route.

If no, explain clearly why the architecture truly needs to change.

---

## Architectural Rules You Must Preserve

### 1. Selector Independence
Do not make selector logic depend on specific frame IDs unless there is an explicit strategist-approved hygiene exception.

Allowed exception examples:
- blocking repeated identity re-entry
- preventing previously used OPEN frames from reappearing too soon

Disallowed pattern:
- "if frame_id == X, then always do Y" for normal flow control

### 2. Additive Growth
Prefer:
- adding new frames
- adding new variants
- improving ordering
- improving option generation

Avoid:
- replacing large groups of existing frames
- restructuring engines unless explicitly requested

### 3. Soft Ordering
Treat `FRAME_ORDER` as guidance for exposure and coherence, not as a rigid script.

New frames should be insertable into an engine without requiring a rewrite of selector logic.

### 4. Extensibility Constraint
A good MandarinOS change should satisfy this test:

**Adding 20–50 new frames should not require major changes to:**
- selector logic
- scoring logic
- runtime architecture
- conversation grammar layer

If a proposed change fails this test, flag it as an extensibility risk.

### 5. Builder-First Mindset
When output quality is poor, first check whether the problem is better solved in:
- builder logic
- distractor pool construction
- option relevance
- tagging quality
- frame ordering

Do not default to selector changes when the real issue is content or build quality.

---

## How To Classify Beta Feedback
When future beta testers report problems, classify them before proposing fixes.

### Category A — Content Value Issue
Examples:
- awkward question
- boring question
- too generic
- not useful
- repetitive wording

Preferred fix:
- add a better frame
- add a better response variant
- add a higher-value alternative

### Category B — Selector / Flow Issue
Examples:
- topic changes too early
- jumps too fast
- repeats same type of question
- illogical order within engine

Preferred fix:
- minimal selector hygiene rule
- ordering tweak
- soft priority adjustment

### Category C — Builder / Option Quality Issue
Examples:
- irrelevant distractors
- wrong domain vocabulary
- poor option set
- weak gloss output

Preferred fix:
- builder improvement
- per-engine pool tightening
- option generation refinement

### Category D — Structural Conversation Design Issue
Examples:
- conversation feels like an interview
- partner never volunteers information
- lack of natural mutual exchange
- discourse role missing entirely

Preferred fix:
- future grammar / architecture phase
- not a local patch

### Category E — Alpha Polish Issue
Examples:
- unresolved slot token
- rough English gloss
- minor UI wording problem

Preferred fix:
- isolated polish fix
- do not escalate to architecture

---

## Decision Priority Order
When you identify a problem, use this order:

1. Can it be solved by better content?
2. Can it be solved by ordering or builder refinement?
3. Can it be solved by a minimal selector hygiene rule?
4. Only then consider deeper architecture change.

This priority order must be followed unless explicitly overridden.

---

## What To Optimize For
Optimize for:
- extensibility
- stability
- better conversational value density
- easy future addition of frames and responses
- minimal architectural churn

Do not optimize for:
- cleverness
- special-case logic
- hidden heuristics
- short-term patching that makes future extension harder

---

## Definition of Success
Success means MandarinOS can improve over time by:
- keeping most existing frames stable
- adding better frames gradually
- adding better responses gradually
- improving quality through beta feedback
- absorbing new content without major rework

---

## Instruction For Future Proposals
When proposing work, explicitly state which of these it is:

- content addition
- ordering adjustment
- builder refinement
- selector hygiene
- structural grammar change
- polish only

And explain why the chosen level is the **lowest sufficient level of intervention**.

---

## Final Rule
MandarinOS should evolve as a **growing network of conversational moves**, not a brittle scripted flow.

Protect the architecture that allows future frame growth.
Do not trade extensibility for local cleverness.
