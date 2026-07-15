Phase 3 — Step 1 Implementation Checklist
Audio-First UI (Conversation Fidelity)

Goal:
Ensure that everything the learner is expected to process in the current turn can be heard, in a way that preserves conversational ontology.

0. Scope Guard (Read First)

Before implementation, confirm:

☐ This work affects only UI rendering + trace emission

☐ No learning-management concepts are introduced

☐ No SRS logic is touched

☐ No schema refactors are required

If any box fails → STOP (out of Phase 3 scope)

1. Identify All “Speakable Utterances”

The following UI elements MUST be treated as speakable utterances:

Required

☐ Card main content text

☐ Modeled options (H3)

☐ Structured templates (H2), including slot placeholders

☐ Example fragments surfaced by hints

Explicitly Excluded (do NOT add audio)

UI labels (buttons, icons)

Meta text (“Hint”, “Back”, “Close”)

Developer/debug metadata

If an element can plausibly be read aloud by a conversation partner, it belongs in the Required list.

2. Audio Affordance Rules (UI)

For every speakable utterance:

☐ A play / speak affordance is visible or discoverable

☐ Affordance placement does not break conversational flow

☐ Affordance does not look like “lesson playback” or “study audio”

☐ Affordance is optional (audio does not auto-force progression)

Disallowed:

❌ “Listen carefully” copy

❌ “Repeat after me”

❌ Progress-gated audio (“must listen before continuing”)

3. Audio Rendering Semantics (Critical)

Audio must feel like partner speech, not instructional media.

Check each:

☐ Audio voice matches partner voice (or neutral conversational voice)

☐ No teacher tone, no explanatory cadence

☐ No “example reading” framing

☐ Audio length matches utterance length (no padding)

Negative Capability Test:

Would it feel strange if a human conversation partner suddenly played this audio?

If yes → REJECT or REFRAME

4. Interaction Behaviour

While audio is playing:

☐ User can still see options / templates

☐ Audio playback does not lock the UI

☐ User can interrupt / replay without penalty

☐ Audio does not imply correctness or evaluation

Audio is an assistive modality, not a gate.

5. Trace Emission (Silent but Mandatory)

For each audio playback event:

☐ Emit AUDIO_PLAYED

☐ Include:

utterance_id (card / option / template)

duration_ms

completed (true/false)

☐ Trace fires regardless of whether audio is completed

Do NOT:

introduce “audio mastery”

score listening behaviour

tie audio completion to correctness

Trace exists only to support downstream systems invisibly.

6. Hint Ladder Compatibility Check

Verify that audio does not replace or fake hint actionability:

☐ Playing audio alone does not count as H0–H3 progress

☐ Hint effects (narrow / structure / model) still cause visible state change

☐ Audio is layered on top of hint effects, not instead of them

If audio is the only thing that changes → FAIL (violates Hint Cascade)

7. Acceptance Gate (Must All Pass)

Before marking Step 1 complete:

☐ All learner-relevant utterances are speakable

☐ Audio preserves live conversation feel

☐ No learning-management metaphors introduced

☐ Trace coverage is complete and silent

☐ Phase 3 Acceptance Checklist sections A, B, C, D, E all pass

If any fail → Step 1 is not complete

Definition of “Done” for Step 1

Step 1 is complete when:

A user can progress through a conversational turn while hearing everything they are expected to process, without ever feeling like they have entered a lesson or study mode.

Nothing more. Nothing less.
