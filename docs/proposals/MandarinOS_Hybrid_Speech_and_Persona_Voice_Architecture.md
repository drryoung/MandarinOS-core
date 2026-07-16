<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as a proposed architecture for hybrid speech processing and persona voice behaviour.
> - **May guide current implementation:** No.
> - **Current authority:** Verified browser speech behaviour, `docs/ASR_PIPELINE.md`, and the deferred speech and Hybrid AI decisions in `docs/ARCHITECTURAL_DECISIONS.md`.
> - **Principal caution:** This architecture is deferred and unimplemented as a complete system. It must not be used to infer a current managed speech provider, persona-voice pipeline, or runtime service boundary.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS — Future Release Development Note
## Hybrid Speech + Persona Voice Architecture

### Current Position
MandarinOS currently uses browser-based speech recognition (Web Speech API). This is sufficient for alpha/beta validation but produces uneven behavior across platforms, especially iPhone/iOS browsers due to WebKit limitations and HTTPS/security constraints.

---

## Strategic Direction
MandarinOS should evolve toward a hybrid speech architecture rather than relying permanently on browser-native speech recognition.

---

# Target Architecture

## Layer 1 — Default Browser STT
Use browser speech recognition by default for:
- low-cost operation
- onboarding
- casual practice
- free-tier users
- rapid iteration

## Layer 2 — Cloud STT Fallback / Premium
Introduce cloud speech-to-text selectively for:
- iPhone/browser failure recovery
- repeated recognition failures
- low-confidence recognition
- challenge/scoring mode
- premium subscribers
- high-value sessions

### Key principle
Cloud STT should initially augment browser STT, not replace it globally.

### Potential future behavior
- browser STT first-pass
- fallback to cloud STT if confidence/quality low
- premium users optionally default to higher-accuracy mode

---

# Strategic Benefits
- more consistent cross-device behavior
- improved challenge-mode fairness
- better telemetry/debugging
- higher reliability for paid users
- controlled infrastructure cost
- graceful degradation on weaker browsers

---

# Separate Future Layer — Persona Voice System (TTS)

### Important distinction
- STT = listening
- TTS = app speaking

MandarinOS differentiation opportunity likely lies more strongly in persona voice realism than raw STT accuracy.

---

# Future Persona Voice System Possibilities

The future persona voice system may include:
- male/female voices
- age/style variation
- regional accents
  - Mainland Mandarin
  - Taiwanese Mandarin
- emotional tone variation
- slower beginner speech
- personality-linked pacing and warmth

### Possible persona examples
- friendly university student
- café owner
- retired uncle
- young professional
- travel enthusiast
- soft-spoken tutor

### Voice characteristics may eventually become linked to:
- persona profile
- engine/topic
- learner level
- challenge mode
- immersion mode

---

# Strategic Observation

Natural conversational pacing, warmth, and recognizable persona identity may become a stronger competitive differentiator than perfect transcription accuracy.

---

# Recommended Sequencing

## Current priority
1. conversation quality
2. interaction realism
3. onboarding
4. retention
5. mobile UI stability
6. transcript/runtime integrity

## Next major infrastructure layer
- cloud TTS persona voices

## Later
- hybrid cloud STT infrastructure

### Final principle
Do not prematurely optimize infrastructure before validating long-term retention and willingness to pay.
