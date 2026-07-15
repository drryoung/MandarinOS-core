# MandarinOS Release 1.0 Boundary

## Design Decision

Release 1.0 is a controlled conversation-training system, not a general chatbot.

The goal is to train:
- answering
- asking back
- recovering
- continuing
- using support tools

within deterministic beginner conversation lanes.

## What Release 1.0 Should Do

- Select deterministic beginner frames.
- Keep frame flow stable.
- Support recovery after noisy beginner speech.
- Prevent catastrophic failures such as random topic jumps, persona echo, and generic filler after confusion.
- Keep blue questions available for learner agency.
- Support the 10-day alpha test using a limited set of stable conversations.
- Provide evidence-based reflection after sessions.

## What Release 1.0 Should NOT Try to Do

- Understand arbitrary natural speech.
- Resolve every ASR distortion.
- Infer every learner intention from noisy multi-utterance bursts.
- Behave like a fully natural human conversation partner.
- Patch unlimited place-name, name, or topic edge cases.
- Use large rule lists to simulate human judgment.

## Release 1.0 Guardrail

If a behaviour requires human-like interpretation, do not keep adding fragile rules.

Instead classify it as:

> **Future: Release 2.0 constrained AI interpreter**

## Release 2.0 Direction

Release 2.0 may add a constrained AI interpretation layer.

That layer should not replace MandarinOS.

It should classify learner input into a small decision set:

- `ANSWER_CURRENT_FRAME`
- `ASK_PERSONA_QUESTION`
- `CONFUSION`
- `PARTIAL_CONFIRMATION`
- `EXPLICIT_TOPIC_SWITCH`
- `UNKNOWN`

MandarinOS deterministic logic should still decide the final teaching behaviour.

## Current Engineering Rule

Do not patch new live edge cases unless they are:
1. catastrophic,
2. common in the controlled alpha scripts,
3. directly blocking the 10-day alpha trial.

Otherwise document as Release 2.0.

## Regression Tests

Keep the existing interaction regression tests.

They protect Release 1.0 from regressions.

But do not endlessly expand tests to chase every natural conversation edge case.

Add tests only for controlled Release 1.0 behaviours.

## Product Positioning

Release 1.0 should be described as:

> **"Conversation training mode"**

Not:

> ~~"Fully natural AI conversation partner"~~

## Final Note

The purpose of Release 1.0 is not perfect naturalness.

The purpose is stable, repeatable beginner conversation practice with recovery support.
