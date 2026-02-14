MandarinOS — Phase 3 Acceptance Checklist

(Conversation Fidelity & Hint Embodiment)

Use this checklist to evaluate any Phase 3 feature, UI change, or proposal before acceptance.

A Phase 3 item is acceptable only if all applicable checks pass.

A. Phase Scope Integrity (Hard Gate)

A1. Does this feature operate entirely within the current conversation turn?

☐ Yes → continue

☐ No → REJECT (out of Phase 3 scope)

A2. Does this feature avoid implying “learning later”, “studying”, or “managing progress”?
(e.g. save, review, bookmark, queue, mastery, progress)

☐ Yes → continue

☐ No → REJECT

A3. Does this feature avoid duplicating responsibilities of a locked subsystem (e.g. SRS)?

☐ Yes → continue

☐ No → REJECT

B. Conversation Ontology (Non-Negotiable)

B1. Does this preserve the feeling of a live conversation (Partner → User → Partner)?

☐ Yes → continue

☐ No → REJECT

B2. Does this avoid introducing lesson, curriculum, or teaching metaphors?

☐ Yes → continue

☐ No → REJECT

B3. Is there no visible grading, correctness signaling, or pedagogical meta-commentary?

☐ Yes → continue

☐ No → REJECT

C. Audio-First Compliance

C1. Is all learner-relevant content speakable?
(including cards, modeled options, structured templates where applicable)

☐ Yes → continue

☐ No → REJECT or FIX

C2. Does audio feel like “the partner speaking”, not “playing lesson audio”?

☐ Yes → continue

☐ No → REJECT or REFRAME

D. Hint Ladder Integrity (H0–H3)

D1. If a hint is involved, does invoking it cause a measurable state change?
(narrowing, structuring, or modeling — not just text)

☐ Yes → continue

☐ No → REJECT

D2. Are H0–H3 effects clearly visible in the UI state?
(e.g. fewer options, template appears, ≥2 modeled options)

☐ Yes → continue

☐ No → REJECT or FIX

D3. Does the feature preserve at least one clear forward path at all times?

☐ Yes → continue

☐ No → REJECT

D4. If modeling occurs, are there ≥2 valid options and no single “correct” answer?

☐ Yes → continue

☐ No → REJECT

E. Trace & Instrumentation (Silent but Required)

E1. Does the feature emit trace events for meaningful conversational actions?
(e.g. audio played, option selected, slot filled, hint used)

☐ Yes → continue

☐ No → FIX REQUIRED

E2. Are these traces sufficient for downstream consumers without adding UI controls?

☐ Yes → continue

☐ No → FIX REQUIRED

F. Negative Capability Check (Quick Kill Test)

Ask explicitly:

If this feature existed in a real human conversation, would it feel strange?

☐ No → acceptable

☐ Yes → REJECT

(This single question catches most subtle drift.)

Acceptance Rule (Final)

A Phase 3 feature may be accepted only if:

All A, B, and D checks pass

Any failures in C or E are explicitly fixed before merge

No item triggers the Negative Capability Check

Enforcement Principle

If a feature requires reinterpreting the Constitution or Phase Boundaries to justify it, the feature is invalid.
