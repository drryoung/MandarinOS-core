# MandarinOS Architectural Decisions

## 1. Purpose and authority

This document records the durable architectural decisions that govern MandarinOS at the R2 baseline, and the reasoning behind them.

This document:

- records durable R2 architectural decisions and their rationale;
- is an **approved-decision record** once reviewed;
- is **subordinate to verified code and the detailed behavioural contracts** (`docs/ARCHITECTURE.md`, `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md`, `docs/ASR_PIPELINE.md`, `docs/TEST_STRATEGY.md`, `docs/CHANGE_CHECKLIST.md`);
- must not be used as a substitute for reading the applicable contract before implementing a change;
- distinguishes deliberate decisions from current constraints that are not themselves endorsed as a design target.

> An architectural decision explains why the system is organised this way. A behavioural contract explains exactly what the system currently does.

Application baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Application baseline tag: `architecture-baseline-2026-07-12-r2`

## 2. How to read and maintain this record

- **Decision numbers are stable.** An ADR's number never changes and is never reused for an unrelated decision.
- **Accepted records are not silently rewritten.** A record reflects the decision as accepted at the time; it is not edited after the fact to match a later, different decision.
- **If a decision changes**, either:
  - amend the record with an explicit, dated revision note where the fundamental decision remains intact; or
  - mark the record `Superseded`, link to the replacement ADR, and add the new ADR (§7).
- **Factual corrections that do not change the decision** (a wrong file path, an outdated command) may be made directly, with a short dated correction note in the record.
- **Implementation details belong primarily in the detailed contracts.** This document explains *why*; the seven approved contracts explain *what*, in operational detail. Do not duplicate their inventories here.
- **Historical documents do not override accepted ADRs or verified behaviour.** Older phase locks, briefings, and design documents may explain past intent, but where they conflict with an accepted ADR or with verified R2 behaviour, the ADR and the verified behaviour govern (`docs/ARCHITECTURE.md` §3).
- **Proposed future architecture must identify which ADRs it changes**, using the decision-change template in §5, before implementation begins.

## 3. Decision index

| ADR | Decision | Status | Decision type | Primary contracts |
| --- | -------- | ------ | -------------- | ------------------ |
| ADR-001 | Conversation simulator, not a generic chatbot or conventional course | Accepted — product direction | product | `docs/CONVERSATION_ARCHITECTURE.md` |
| ADR-002 | Personas provide stable social continuity and bounded discoverable facts | Accepted — product direction | product | `docs/ANSWER_SOURCE_CONTRACT.md` |
| ADR-003 | Persona answer generation and next-frame selection are separate mechanisms | Accepted — R2 baseline | conversation architecture | `docs/ANSWER_SOURCE_CONTRACT.md`, `docs/CONVERSATION_ARCHITECTURE.md` |
| ADR-004 | Answer generation uses an explicit ordered priority chain | Accepted — R2 baseline | answer generation | `docs/ANSWER_SOURCE_CONTRACT.md` |
| ADR-005 | Topic engines and frames provide controlled conversational progression | Accepted — R2 baseline | conversation architecture | `docs/CONVERSATION_ARCHITECTURE.md` |
| ADR-006 | E4 engine handoff is deferred to the following request | Accepted — R2 baseline | conversation architecture / state | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md` |
| ADR-007 | State is distributed and ownership must remain explicit | Accepted — recovery safeguard | state | `docs/STATE_CONTRACT.md` |
| ADR-008 | Learner memory is bounded, explicit, and separately persistent | Accepted — R2 baseline | state | `docs/STATE_CONTRACT.md` |
| ADR-009 | Browser-native speech recognition and synthesis are the R2 client boundaries | Accepted — R2 baseline | client/browser | `docs/ASR_PIPELINE.md` |
| ADR-010 | Client-intercepted recovery remains outside the normal server-turn path | Accepted — R2 baseline | client/browser | `docs/ASR_PIPELINE.md` |
| ADR-011 | Challenge Mode is a client-side visibility and reveal layer | Accepted — R2 baseline | client/browser | `docs/ASR_PIPELINE.md` |
| ADR-012 | Conversation content is intentionally hybrid rather than fully data-driven | Current constraint — not an endorsed target | content | `docs/ANSWER_SOURCE_CONTRACT.md`, `docs/ARCHITECTURE.md` |
| ADR-013 | Generated runtime artifacts are derived outputs, not primary editable sources | Accepted — R2 baseline | deployment | `docs/ARCHITECTURE.md`, `docs/TEST_STRATEGY.md` |
| ADR-014 | Ordinary R2 turns do not depend on external generative AI | Accepted — R2 baseline | product | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/ANSWER_SOURCE_CONTRACT.md` |
| ADR-015 | Code identity and functional correctness require separate production verification | Accepted — recovery safeguard | deployment | `docs/ARCHITECTURE.md`, `docs/CHANGE_CHECKLIST.md` |
| ADR-016 | Test evidence is ranked by execution path, not naming or test count | Accepted — recovery safeguard | testing | `docs/TEST_STRATEGY.md` |
| ADR-017 | Architecture and change contracts are mandatory maintenance controls | Accepted — recovery safeguard | maintenance governance | All seven approved documents |
| ADR-018 | Large central client and server files are a documented constraint, not endorsed target architecture | Current constraint — not an endorsed target | current structural constraint | `docs/ARCHITECTURE.md` |
| ADR-019 | Regression recovery prioritises behavioural preservation over architectural elegance | Accepted — recovery safeguard | maintenance governance | `docs/CHANGE_CHECKLIST.md` |
| ADR-020 | Model allocation separates diagnosis from mechanical implementation | Accepted — R2 baseline | maintenance governance | `docs/CHANGE_CHECKLIST.md` |

## ADR-001 — MandarinOS is a conversation simulator, not a generic chatbot or conventional language course

Status: `Accepted — product direction`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Project owner
Decision type: product

### Context
`AI_CONTEXT.md` §0 states the project goal as "usable spoken competence" via a repeating frame → response → hint → exploration loop. The seven approved contracts describe sustained multi-turn exchanges with a persona, not isolated drills or open-ended chat.

### Decision
- The principal unit of practice is a **sustained conversation**, not an isolated drill or unstructured chat.
- The system optimises for responsiveness, follow-up, repair, depth, and confidence across many turns.
- Words, personas, frames, and recovery phrases **serve the conversational experience** rather than becoming independent drill products.
- Ordinary turns remain **structured and deterministic** at R2 (`docs/CONVERSATION_ARCHITECTURE.md`, `docs/ANSWER_SOURCE_CONTRACT.md`).
- Future AI augmentation (`AI_CONTEXT.md` §12) must support, not replace, this control model unless a later ADR changes it.

### Rationale
- Intermediate learners often know components but cannot sustain conversation — the specific gap addressed.
- Deterministic structure keeps behaviour inspectable and testable (`docs/TEST_STRATEGY.md`).
- Generic open-domain AI chat cannot guarantee the same frame progression, persona consistency, or recovery ladder.

### Alternatives considered
- **A conventional structured course** — rejected; does not address the "can't sustain conversation" gap.
- **Unrestricted open-domain AI chat** — deferred (ADR-014, §6); cannot guarantee current deterministic, testable behaviour.

### Consequences
#### Benefits
Conversational depth and repair are first-class goals; deterministic handling stays testable and diagnosable.

#### Costs and constraints
New value requires frame/persona/content work, not just vocabulary; the system forgoes unrestricted-chat flexibility.

### Maintenance obligations
Evaluate new content/features against whether they deepen sustained practice; evaluate any "independent drill product" proposal against this ADR.

### Evidence and traceability
`AI_CONTEXT.md` §0, §12; `docs/CONVERSATION_ARCHITECTURE.md`; `docs/ANSWER_SOURCE_CONTRACT.md`.

### Reconsider when
An evidenced learner need is identified that sustained-conversation practice structurally cannot serve, with a bounded alternative mode that does not displace the simulator as default.

## ADR-002 — Personas provide stable social continuity and bounded discoverable facts

Status: `Accepted — product direction`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Project owner
Decision type: product

### Context
`docs/ANSWER_SOURCE_CONTRACT.md` documents persona answers resolved server-side from `personas/<id>.json`, using structured `discoverable_facts`/`discoverable_facts_en` fields rather than open-ended generation (`AI_CONTEXT.md` §5.2).

### Decision
- Conversations occur with **named personas**, not an anonymous assistant.
- Persona facts, voice lines, and discoverable information create continuity across and within sessions.
- Persona answers are **bounded** by structured data and the approved answer-source mechanisms, not open-domain generation.
- **Persona consistency is prioritised over unlimited open-domain factual coverage.**

### Rationale
- Sustained, human-like exchange requires a continuous counterpart with repeatable answers, not a stateless responder.
- Bounding facts to authored data reduces hallucination risk and keeps answers regression-testable.

### Alternatives considered
- **Fully generative, unbounded persona answers** — rejected; reintroduces hallucination risk and removes testability.
- **A single anonymous partner with no persona identity** — rejected as weaker for continuity.

### Consequences
#### Benefits
Persona answers trace to specific authored content, supporting regression testing; explicit per-topic `discoverable_facts` lines are preferred over brittle clause-splitting (`AI_CONTEXT.md` §5.2).

#### Costs and constraints
A question outside a persona's authored facts cannot be answered with genuine open-domain knowledge; expanding coverage carries schema/translation obligations.

### Maintenance obligations
New persona facts must include English/pinyin companions. At R2, the persona **index** loads at server startup (`_load_personas_index()`); individual persona files are lazy-loaded from disk on first access and cached thereafter (`_resolve_persona()`) — not necessarily reread every request; a content edit needs a process restart to take effect for an already-cached persona.

### Evidence and traceability
`docs/ANSWER_SOURCE_CONTRACT.md`; `AI_CONTEXT.md` §5.2; `scripts/ui_server.py` (`_load_personas_index`, `_resolve_persona`, `personas/*.json`).

### Reconsider when
A bounded, evidenced mechanism for extending persona knowledge beyond authored facts is proposed with defined fallback and consistency guarantees.

## ADR-003 — Persona answer generation and next-frame selection are separate mechanisms

Status: `Accepted — R2 baseline`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: R2 recovery programme
Decision type: conversation architecture

### Context
`docs/ANSWER_SOURCE_CONTRACT.md` and `docs/CONVERSATION_ARCHITECTURE.md` independently document `counter_reply` generation and next-frame selection as distinct code paths with distinct producers.

### Decision
- `counter_reply` generation and next-frame selection remain **conceptually and operationally separate**.
- Current-turn flags (e.g. `force_travel_bridge`) may coordinate them within one response; E4 may coordinate future engine selection across turns (ADR-006).
- **A correct answer does not prove correct frame selection, and vice versa.**

### Rationale
Persona responsiveness and conversational progression have different responsibilities and failure modes; combining them would make priority ordering, pacing, and regression diagnosis far less tractable.

### Alternatives considered
**A single unified "response engine"** — rejected; evaluated as reducing diagnosability with no corresponding benefit.

### Consequences
#### Benefits
Regressions localise to either path, not both at once; each is independently testable (`docs/TEST_STRATEGY.md` §9).

#### Costs and constraints
Both outputs must be validated separately for any change touching either path — testing one is not evidence for the other.

### Maintenance obligations
Changes to answer producers must not silently reorder frame selection, and vice versa; `docs/CHANGE_CHECKLIST.md` §8–§9 require both checklists for changes touching this boundary.

### Evidence and traceability
`docs/ANSWER_SOURCE_CONTRACT.md`; `docs/CONVERSATION_ARCHITECTURE.md`.

### Reconsider when
An evidenced maintenance cost from the current separation is identified, with a replacement design preserving independent testability of both concerns.

## ADR-004 — Answer generation uses an explicit ordered priority chain

Status: `Accepted — R2 baseline`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: R2 recovery programme
Decision type: answer generation

### Context
`docs/ANSWER_SOURCE_CONTRACT.md` documents a numbered priority chain with group-local blocking, plus distinct finalisation stages (deduplication, exact-repeat handling, repair escalation, English alignment, pinyin derivation, late Chinese-only repair). Commit `657529a` ("fix: resolve stale-answer loop via RC-A / RC-B / RC-C", 2026-07-11) is direct evidence that ordering/blocking defects caused real regressions shortly before the R2 baseline.

### Decision
- Answer producers compete through a **defined, ordered priority chain**, not implicit precedence.
- Group-local blocking (a higher-priority branch suppressing a whole lower-priority group) is deliberate.
- Deduplication, repeat handling, repair escalation, English alignment, pinyin derivation, and late repair are **distinct finalisation stages**.
- New producers must be **inserted deliberately** at a considered position, not appended opportunistically.

### Rationale
Many utterances plausibly match more than one interpretation; explicit ordering is the only way to make the resulting choice predictable, and is more maintainable than implicit producer-vs-producer competition. `657529a` demonstrated that small, undocumented ordering changes can cause broad regressions.

### Alternatives considered
- **Confidence-scored competition** — deferred; would need a scoring/calibration effort not undertaken at R2.
- **First-match-wins with no explicit ordering document** — rejected; this is the condition `657529a` fixed.

### Consequences
#### Benefits
Priority/blocking behaviour is documented and inspectable rather than implicit; a defect traces to a specific branch and position.

#### Costs and constraints
Answer-source changes are **high risk** by default (`docs/CHANGE_CHECKLIST.md` §2.D); positive, negative, competing-priority, repeated-turn, and English/pinyin tests are required (`docs/CHANGE_CHECKLIST.md` §8).

### Maintenance obligations
The complete branch inventory lives in `docs/ANSWER_SOURCE_CONTRACT.md`; any priority/producer/fallback/finalisation change must update it in the same change.

### Evidence and traceability
`docs/ANSWER_SOURCE_CONTRACT.md`; commit `657529a`; `docs/CHANGE_CHECKLIST.md` §8.

### Reconsider when
A scoring/alternative competition model is proposed with a concrete calibration and regression-testing plan that demonstrably improves on current predictability.

## ADR-005 — Topic engines and frames provide controlled conversational progression

Status: `Accepted — R2 baseline`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Maintainers
Decision type: conversation architecture

### Context
`scripts/ui_server.py`'s `_FRAME_ORDER` dictionary defines an explicit, per-engine ordered frame ladder with `skip_when` conditions and mutual-exclusion pairs, per `docs/CONVERSATION_ARCHITECTURE.md` and `.cursor/rules/mandarinos-architecture.mdc`.

### Decision
- **Topic engines constrain progression** through a bounded set of topic areas rather than arbitrary drift.
- **Frames and ladders** within each engine provide conversational depth and pacing.
- `_FRAME_ORDER`, eligibility, `skip_when`, and mutual-exclusion logic remain **explicit**, per the declarative-skip-conditions rule.
- The active R2 engine set (verified against `_FRAME_ORDER`) is: `identity`, `place`, `family`, `work`, `hobby`, `travel`, `food`, and a gated `life` engine (blocked until `exchange_count ≥ 16`, `MIN_TURNS_FOR_LIFE_ENGINE`).

### Rationale
Controlled progression prevents random-chat drift; engines permit structured breadth and depth without an unbounded state space; frames make common conversational "dishes" repeatable and testable across personas.

### Alternatives considered
- **Freeform topic drift** — rejected; removes the structure ADR-001 depends on.
- **A single flat frame list with no engine grouping** — rejected; loses topic coherence and makes `skip_when`/mutual-exclusion harder to reason about.

### Consequences
#### Benefits
Engine/frame structure is inspectable directly in `_FRAME_ORDER` and content JSON; new frames are additive within an existing ladder in the common case.

#### Costs and constraints
Frame order/engine changes are **shared-control-flow changes** (`docs/CHANGE_CHECKLIST.md` §2.D); a new engine requires explicit integration and contract updates, not just content files.

### Maintenance obligations
New frames use `skip_when` rather than ad hoc `if`-blocks in the selector; changes to `_FRAME_ORDER`/eligibility/mutual exclusion must update `docs/CONVERSATION_ARCHITECTURE.md` in the same change.

### Evidence and traceability
`scripts/ui_server.py` (`_FRAME_ORDER`, `MIN_TURNS_FOR_LIFE_ENGINE`); `docs/CONVERSATION_ARCHITECTURE.md`; `.cursor/rules/mandarinos-architecture.mdc`.

### Reconsider when
An engine/ladder structure is shown to systematically block conversational value, with a replacement proposed against the 20–50-frame extensibility test.

## ADR-006 — E4 engine handoff is deferred to the following request

Status: `Accepted — R2 baseline`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: R2 recovery programme
Decision type: conversation architecture / state

### Context
Commit `e2f373a` ("Complete E4 handoff for direct persona answers", 2026-07-11) and commit `3be0315` ("fix: apply E4 handoff in primary client flow", 2026-07-12 — the R2 baseline tag commit itself) are direct evidence that E4's cross-turn timing was a source of real defects corrected immediately before the R2 baseline was cut.

### Decision
- An eligible learner initiative can cause a **future-engine handoff**, not an immediate mid-response topic change.
- The server emits `state_update.current_engine` for the current response; the client resolves and applies it for the **following** request via `_resolveNextEngineId()` in `ui/app.js`.
- The current response retains the documented **one-response transition delay**.

### Rationale
Answer generation and the current-frame response must finish coherently before the topic changes; retroactively rewriting an already-sent response is not viable. The delay preserves a clean server/client contract boundary.

### Alternatives considered
- **Immediate mid-response engine switching** — rejected; risks incoherent output and was the source of the defect fixed by `3be0315`.
- **No deferred handoff at all** — rejected as too restrictive for the reciprocity/exploration goals in `AI_CONTEXT.md` §11a.

### Consequences
#### Benefits
The current-turn response and the following-turn engine change are each independently coherent and testable; `3be0315` is the verified R2 baseline itself.

#### Costs and constraints
`data.engine_id` and `state_update.current_engine` must not be conflated; current-turn and following-turn tests are **both mandatory** for any E4-adjacent change.

### Maintenance obligations
Changing this timing requires updating `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, `docs/TEST_STRATEGY.md`, and `docs/CHANGE_CHECKLIST.md` together.

### Evidence and traceability
Commits `e2f373a`, `3be0315`; `docs/CONVERSATION_ARCHITECTURE.md`; `docs/STATE_CONTRACT.md`; `ui/app.js` (`_resolveNextEngineId()`).

### Reconsider when
A concrete, tested design for coherent mid-response engine switching is proposed, explicitly handling the coherence risk this ADR avoids.

## ADR-007 — State is distributed and ownership must remain explicit

Status: `Accepted — recovery safeguard`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: R2 recovery programme
Decision type: state

### Context
`docs/STATE_CONTRACT.md` documents that no single canonical state object exists — state is divided across DOM/UI, client globals, transported `conversation_state`, returned `state_update`, server-local request state, learner memory, and progress/session persistence. This is a direct output of the R2 audit finding regressions caused by unclear ownership.

### Decision
- **No single canonical state object exists at R2.**
- State is divided among: DOM/UI; client globals; transported `conversation_state`; returned `state_update`; server-local request state; learner memory; progress/session persistence.
- Every state change must identify: producer; every consumer; transport direction; all reset paths; persistence duration (`docs/CHANGE_CHECKLIST.md` §7).

### Rationale
The system evolved incrementally across browser, server, and persistence layers rather than a unified design; the R2 recovery found regressions from unclear ownership and incomplete reset/consumption. Explicit, honest documentation of this is safer than presenting a false centralised model.

### Alternatives considered
- **Presenting a simplified "as if centralised" model** — rejected; would misrepresent verified behaviour and reintroduce "state didn't clear" defects.
- **Immediate state centralisation during R2 recovery** — deferred (§6); would have increased regression risk before a stable baseline existed (ADR-019).

### Consequences
#### Benefits
Every field's ownership, producer, and consumers are traceable in `docs/STATE_CONTRACT.md`; reset behaviour is documented per scope rather than assumed uniform.

#### Costs and constraints
A field appearing in `state_update` does not prove client consumption; same-tab reset, reload, and persona switch remain **distinct** scopes requiring separate consideration.

### Maintenance obligations
Future state consolidation requires a new ADR and explicit migration plan (§6) — not an incidental side effect of an unrelated fix.

### Evidence and traceability
`docs/STATE_CONTRACT.md`; `docs/CHANGE_CHECKLIST.md` §7.

### Reconsider when
A concrete state-centralisation proposal is made with a full migration plan, a compatibility strategy for existing consumers, and a rollback plan.

## ADR-008 — Learner memory is bounded, explicit, and separately persistent

Status: `Accepted — R2 baseline`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Maintainers
Decision type: state

### Context
`docs/STATE_CONTRACT.md` documents `LEARNER_MEMORY_KEYS` (`scripts/learner_memory.py:22–29`) as a fixed six-key tuple; `save()`, `_load_file()`, and `clear()` all strip data outside these keys, and a known dead-end field (`job_company`) is silently dropped because it is not in the tuple.

### Decision
- Persistent learner memory uses the **approved canonical keys** — exactly six fields at R2.
- Memory capture is **bounded**: any extracted field outside the canonical keys is not persisted, by design.
- Clear/reset is **explicit** — `clear(learner_id)` writes a literal six-key, all-`None` dict.
- Learner memory is **distinct** from transient conversation state and progress/Challenge history.

### Rationale
Bounded memory improves consistency and reduces the privacy surface; unrestricted extraction would create schema drift. A bounded schema is testable and explainable in a way an open-ended one is not.

### Alternatives considered
**Open-ended key capture** — rejected; close to the current `job_company` dead-end defect, which the audit flagged rather than endorsed.

### Consequences
#### Benefits
Persistence is fully described by a fixed, small schema; `clear()` has one unambiguous effect.

#### Costs and constraints
Fields outside `LEARNER_MEMORY_KEYS` (e.g. `job_company`, `partner_facts_seen`) are computed but never durably persisted — a known, documented gap; expanding the key set is a schema change requiring migration (`migrate_corrupted_memory()` precedent).

### Maintenance obligations
Reference the canonical inventory in `docs/STATE_CONTRACT.md`, not reproduced here; a new canonical key must address `save()`/`_load_file()`/`clear()` consistently, not just capture.

### Evidence and traceability
`scripts/learner_memory.py` (`LEARNER_MEMORY_KEYS`, `save`, `_load_file`, `clear`, `migrate_corrupted_memory`); `docs/STATE_CONTRACT.md`.

### Reconsider when
A bounded new canonical field is proposed with an explicit migration path for existing persisted records.

## ADR-009 — Browser-native speech recognition and speech synthesis are the R2 client boundaries

Status: `Accepted — R2 baseline`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Project owner
Decision type: client/browser

### Context
`docs/ASR_PIPELINE.md` documents that Chinese and auxiliary English recognition use the browser's `SpeechRecognition` API and TTS uses `speechSynthesis`, with no server-side ASR/TTS endpoint anywhere in `scripts/ui_server.py`.

### Decision
- Chinese and auxiliary English recognition use **browser-native `SpeechRecognition`**; TTS uses **browser-native `speechSynthesis`**.
- The server provides no dedicated ASR or TTS endpoint at R2.
- TTS cancellation before recognition starts is a documented **mitigation**, not a guarantee, against self-capture (`docs/ARCHITECTURE.md` §6.1).
- Browser speech behaviour requires **real-browser verification** — no automated test proves the full lifecycle (`docs/TEST_STRATEGY.md` §3.F).

### Rationale
Native browser speech APIs avoid an external speech-service dependency, cost, and credential surface, keeping the application self-contained. The trade-off is browser/OS variability that no automated server-side test can observe.

### Alternatives considered
- **A managed external ASR/TTS provider** — deferred (§6); introduces cost, credentials, privacy, latency, and fallback questions not addressed at R2.
- **A server-side speech pipeline** — rejected; a much larger undertaking with no evidenced necessity.

### Consequences
#### Benefits
No external speech-service cost, credentials, or latency dependency; self-contained browser experience.

#### Costs and constraints
No automated test proves the complete browser speech lifecycle; browser/OS-dependent quality is outside this codebase's control.

### Maintenance obligations
Any browser-behaviour change here requires manual real-browser verification — a passing server-side test is not sufficient evidence.

### Evidence and traceability
`docs/ASR_PIPELINE.md`; `docs/ARCHITECTURE.md` §6.1; `docs/TEST_STRATEGY.md` §3.F.

### Reconsider when
A managed external speech provider is proposed with a concrete cost, privacy, latency, credential-handling, and fallback plan (§6).

## ADR-010 — Client-intercepted recovery remains outside the normal server-turn path

Status: `Accepted — R2 baseline`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: R2 recovery programme
Decision type: client/browser

### Context
`docs/ASR_PIPELINE.md` documents that eligible exact spoken recovery phrases (matched against `content/recovery_phrases.json`) are intercepted client-side in `ui/app.js` before any `/api/run_turn` request is constructed.

### Decision
- Eligible exact spoken recovery phrases **may be intercepted client-side**; a successful interception **does not call `/api/run_turn`**.
- The client may still append the event to its own `conversationTranscript`; optional end-session capture (`MANDARINOS_SESSION_CAPTURE`) may persist that record.
- Non-intercepting actions continue through the ordinary server turn path.

### Rationale
Recovery needs an immediate client-side response without advancing normal server conversation state. Routing recovery phrases through the server risks the server treating a recovery utterance as a genuine semantic answer, corrupting answer-source/frame-selection state.

### Alternatives considered
**Server-side recovery-phrase handling** — rejected; requires the server to reliably distinguish recovery utterances from genuine answers, exactly the ambiguity client-side interception avoids.

### Consequences
#### Benefits
Recovery interception is immediate and does not risk corrupting server-side conversation state.

#### Costs and constraints
**Server tests cannot prove interception** — a successful interception never reaches server-observable code; real-browser checks and longer-utterance false-positive testing are mandatory; diagnostics/session-capture evidence must be interpreted per `docs/ASR_PIPELINE.md`, not assumed to mirror server-side turn records.

### Maintenance obligations
`docs/CHANGE_CHECKLIST.md` §10 and §13's recovery phrase-bank requirements govern verification here.

### Evidence and traceability
`docs/ASR_PIPELINE.md`; `content/recovery_phrases.json`; `docs/TEST_STRATEGY.md` §13.

### Reconsider when
A reliable server-side mechanism for distinguishing recovery utterances from genuine answers is proposed and evidenced.

## ADR-011 — Challenge Mode is a client-side visibility and reveal layer

Status: `Accepted — R2 baseline`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Project owner
Decision type: client/browser

### Context
`docs/ASR_PIPELINE.md` §14 documents Challenge Mode as CSS/DOM visibility and reveal behaviour layered on the ordinary turn path, verified only through static source checks (`tests/test_challenge_recovery.py`) with no dedicated server engine.

### Decision
- Challenge Mode **does not create a separate server conversation engine**; it changes **visibility, recovery presentation, and reveal behaviour** on the client.
- Submitted text and server routing remain governed by the **ordinary turn path** regardless of Challenge Mode.
- Hidden content may still remain in client state/DOM and optional session capture — this is a presentation layer, not a data-removal mechanism.

### Rationale
Increasing listening/recovery demand is the intended effect; duplicating the conversation architecture would create unnecessary divergence and double the testing/maintenance surface for no demonstrated benefit.

### Alternatives considered
**A dedicated server-side "challenge engine"** — rejected; duplicates the conversation architecture without evidenced need.

### Consequences
#### Benefits
Challenge Mode reuses the same server-side answer/frame machinery already covered by the conversation and answer-source contracts.

#### Costs and constraints
Browser verification is required for visibility/reveal changes; privacy language must not imply hidden content is absent from client state — it is hidden from view, not removed from memory or optional capture.

### Maintenance obligations
`docs/CHANGE_CHECKLIST.md` §10 governs verification here; `docs/ASR_PIPELINE.md` §14 is the authoritative behavioural contract.

### Evidence and traceability
`docs/ASR_PIPELINE.md` §14; `tests/test_challenge_recovery.py`.

### Reconsider when
A pedagogical requirement is identified that genuinely requires server-side awareness of Challenge Mode state, with a scope that does not duplicate the ordinary turn path.

## ADR-012 — Conversation content is intentionally hybrid rather than fully data-driven

Status: `Current constraint — not an endorsed target`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Maintainers
Decision type: content

### Context
`docs/ANSWER_SOURCE_CONTRACT.md` documents multiple inline Chinese content pools inside `scripts/ui_server.py` (e.g. `_CITY_LOCATION_BRIEF`, `_CITY_FOOD_POOL`, `_CITY_FEATURE_POOL`) alongside structured JSON content files (`p1_frames.json`, `p2_frames.json`, `personas/*.json`, `content/recovery_phrases.json`). `.cursor/rules/mandarinos-architecture.mdc` separately prohibits *new* inline Chinese strings, consistent with this being an existing condition, not an endorsed pattern to extend.

### Decision
- Frames, personas, recovery phrases, and response patterns use structured content files as the general pattern; some answer logic **remains inline** in `scripts/ui_server.py` at R2.
- R2 does **not** claim one unified content schema.
- New content should use existing authoritative sources and **must not casually create competing duplicates**.

### Rationale
The system reflects incremental development, not a single content-architecture design. Forcing a full migration during R2 recovery would have increased regression risk before a stable baseline existed (ADR-019) — a deliberate trade-off, honestly documented rather than presented as an idealised unified model.

### Alternatives considered
**Migrating all inline content to JSON during R2 recovery** — rejected for R2 specifically due to regression risk; deferred to a future consolidation programme (§6).

### Consequences
#### Benefits
Recovery proceeded without a large, risky content migration blocking it.

#### Costs and constraints
Maintainers must check **both** inline and JSON sources for city/place content or similar; editing one copy without checking the other can produce inconsistent behaviour (`docs/ARCHITECTURE.md` §16).

### Maintenance obligations
`.cursor/rules/mandarinos-architecture.mdc` already prohibits *new* inline Chinese strings. A future consolidation programme requires a separate ADR and migration/testing plan (§4.4) — not authorised by this record.

### Evidence and traceability
`docs/ANSWER_SOURCE_CONTRACT.md` (inline pool inventory); `.cursor/rules/mandarinos-architecture.mdc`; `docs/ARCHITECTURE.md` §16, §19.

### Reconsider when
A content-consolidation proposal is made with a migration plan, a testing plan for both shapes, and a regression-risk assessment against current test coverage.

## ADR-013 — Generated runtime artifacts are derived outputs, not primary editable sources

Status: `Accepted — R2 baseline`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Maintainers
Decision type: deployment

### Context
`docs/ARCHITECTURE.md` §14 and `docs/TEST_STRATEGY.md` §12–§13 document that `runtime/out_phase7/*.runtime.json` is generated by `tools/build_runtime_artifacts.py`, gitignored, and not regenerated automatically by server startup or Railway's build/start configuration.

### Decision
- Source content and builder code are **authoritative**; generated artifacts are derived.
- `runtime/out_phase7/*.runtime.json` is generated and **gitignored**; generation is **explicit-only**, via `python tools/build_runtime_artifacts.py`.
- Server startup and current Railway configuration **do not** regenerate artifacts.
- `/api/version` does **not** prove artifact identity or freshness — code identity only.
- A generated-artifact-dependent change is **not production-ready** without a verified deployed provisioning mechanism.

### Rationale
Generated outputs should remain reproducible from source; editing derived files directly creates undetectable drift. The R2 audit identified a deployment-boundary gap that code-SHA verification alone cannot cover — this ADR makes that gap an explicit obligation rather than a silent risk.

### Alternatives considered
- **Automatic regeneration at server startup** — deferred; not implemented, no performance assessment undertaken.
- **Committing generated artifacts to source control** — rejected as a casual workaround for the provisioning gap.

### Consequences
#### Benefits
Source-of-truth content stays unambiguous — one place to edit per content family.

#### Costs and constraints
Regeneration, local inspection, artifact-dependent testing, provisioning verification, and deployed smoke checks are all **mandatory** for a shipped artifact-dependent change; the deployed provisioning mechanism is not currently verified in this repository's configuration — a real, open gap.

### Maintenance obligations
Selecting a future packaging/provisioning mechanism is **deferred** (§6) and requires a new ADR or amendment — not decided by this record.

### Evidence and traceability
`docs/ARCHITECTURE.md` §14; `docs/TEST_STRATEGY.md` §12–§13; `tools/build_runtime_artifacts.py`; `railway.toml`; `nixpacks.toml`.

### Reconsider when
A concrete deployed-provisioning mechanism is identified and verified, or an automatic regeneration strategy is proposed with an assessed performance/reliability impact.

## ADR-014 — Ordinary R2 turns do not depend on external generative AI

Status: `Accepted — R2 baseline`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Project owner
Decision type: product

### Context
`AI_CONTEXT.md` §12 documents a "Hybrid AI vision" as an explicitly **not-yet-implemented** north star — a future extension layer bolted onto, not replacing, the structured engine. No code path in `/api/run_turn` calls an external generative-AI service at R2.

### Decision
- `/api/run_turn` is handled entirely by the **structured Python conversation engine**; **no external generative-AI call occurs** in the ordinary turn path at R2.
- Future hybrid AI (`AI_CONTEXT.md` §12) remains a possible later direction, not a current implementation.
- Any future AI integration must **not silently replace** the contracts governing state, answer priority, persona consistency, frame progression, and repair.

### Rationale
Deterministic behaviour is inspectable, affordable, and testable. External generative AI would introduce latency, cost, availability, moderation, and consistency concerns not evaluated at R2, and risks diluting the structured-practice differentiation from ADR-001.

### Alternatives considered
**Immediate hybrid-AI integration** — explicitly deferred by `AI_CONTEXT.md` §12 itself ("Do NOT implement AI execution layer yet.").

### Consequences
#### Benefits
The entire ordinary turn path remains deterministic, inspectable, and testable, with no AI-service cost/latency/availability dependency in the critical path.

#### Costs and constraints
A limitation that might plausibly be solved by generative AI must instead be solved through structured behaviour improvements unless and until this ADR is revisited.

### Maintenance obligations
Every structured-engine improvement reduces the eventual need for an AI fallback — the intended relationship between current work and the deferred hybrid-AI direction.

### Evidence and traceability
`AI_CONTEXT.md` §12; `scripts/ui_server.py` (`/api/run_turn`); `docs/CONVERSATION_ARCHITECTURE.md`; `docs/ANSWER_SOURCE_CONTRACT.md`.

### Reconsider when
A specific R2 limitation is identified that structured behaviour cannot reasonably solve, and a bounded AI use case is proposed with defined failure, fallback, privacy, and cost controls (`AI_CONTEXT.md` §12).

## ADR-015 — Code identity and functional correctness require separate production verification

Status: `Accepted — recovery safeguard`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: R2 recovery programme
Decision type: deployment

### Context
`docs/ARCHITECTURE.md` §13 documents that Railway deployment depends on which branch the dashboard is configured to watch — unverifiable from repository files alone — and that `/api/version` confirms deployed code identity. The E4 handoff fix (`3be0315`) and its subsequent production `/api/version` verification are direct evidence this separation was actively exercised at the R2 baseline.

### Decision
- **A local commit is not deployed** until pushed to whichever branch Railway watches.
- `/api/version` verifies **deployed code identity** only — SHA and branch.
- A **functional smoke scenario** verifies affected behaviour separately from code identity.
- Persistence and generated-artifact changes require **additional operational checks** (ADR-013).
- **Documentation-only branch pushes do not require Railway verification.**

### Rationale
The R2 regression recovery exposed branch/commit deployment mismatches — successful local commits/builds had previously been treated, incorrectly, as evidence of correct deployed behaviour. Separating code-identity from functional verification closes that gap.

### Alternatives considered
**Treating a successful Railway build as sufficient deployment evidence** — rejected; the false-confidence pattern this ADR prevents.

### Consequences
#### Benefits
Production claims rest on two independent, named pieces of evidence (SHA match + smoke result) rather than one ambiguous "it deployed."

#### Costs and constraints
Every deployed runtime change requires both checks; Railway branch-watch and volume configuration remain **operational facts outside repository-local tests** and must be verified operationally.

### Maintenance obligations
Production reports must record the deployed SHA and smoke result explicitly; `/api/version` must never be presented as functional or artifact-freshness proof.

### Evidence and traceability
`docs/ARCHITECTURE.md` §13; `docs/CHANGE_CHECKLIST.md` §19; commit `3be0315` and its verified production `/api/version` check.

### Reconsider when
An automated production smoke-testing mechanism is implemented (§6), at which point this ADR should be amended to describe it — the underlying separation of code-identity and functional evidence remains valid regardless.

## ADR-016 — Test evidence is ranked by execution path, not naming or test count

Status: `Accepted — recovery safeguard`
Decision date: `2026-07-13`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: R2 recovery programme
Decision type: testing

### Context
`docs/TEST_STRATEGY.md`'s audit found files named `test_*`/`verify_*` that did not execute the production function they appeared to test (mirrored/static verification instead), and that CI's `unit-tests` job (`python -m unittest -v`) does not run the pytest-based `live_server`/core tiers in `tests/conftest.py` at all.

### Decision
- **Real production execution outweighs mirrored/static verification** for behavioural claims (`docs/TEST_STRATEGY.md` §2, §15).
- Unit, in-process HTTP, external live-server, extracted-JavaScript, browser, deployment, and production evidence each support **different, non-interchangeable** claims.
- **No full browser/client-server automated round trip exists** at R2 — stated plainly, not implied.
- Mirrored ASR tests must remain explicitly labelled as mirrored.
- CI must **not** be assumed to run pytest tiers merely because files are named `test_*.py`.

### Rationale
The audit found misleadingly strong test names not matching their actual execution mechanism; passing static/mirrored tests had created false confidence. Maintenance requires honest evidence labels.

### Alternatives considered
**Treating all passing tests as equivalent evidence regardless of mechanism** — rejected; the false-confidence pattern the audit found.

### Consequences
#### Benefits
Every test category in `docs/TEST_STRATEGY.md` §3 has an explicit "proves"/"does not prove" pair, preventing overclaiming.

#### Costs and constraints
Change reports must list commands, evidence types, skips, and untested areas; CI's actual `unittest.TestCase` execution count is not verified against real GitHub Actions logs as of this baseline — an open, disclosed question.

### Maintenance obligations
Test architecture changes require updating `docs/TEST_STRATEGY.md` in the same change; a future browser-automation framework (§6) would add a strong new evidence category without changing this ADR's central principle.

### Evidence and traceability
`docs/TEST_STRATEGY.md` §2, §3, §4, §15; `.github/workflows/coverage_scan.yml`; `tests/conftest.py`.

### Reconsider when
A browser-automation framework or authoritative CI-to-pytest migration (§6) is implemented, at which point `docs/TEST_STRATEGY.md` §15 and this ADR should be updated together.

## ADR-017 — Architecture and change contracts are mandatory maintenance controls

Status: `Accepted — recovery safeguard`
Decision date: `2026-07-13`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: R2 recovery programme
Decision type: maintenance governance

### Context
This document is part of the seven-document R2 programme, created because prior maintenance depended heavily on knowledge held only by the project owner and past AI conversations.

### Decision
- The **approved architecture documents govern future maintenance**: `docs/ARCHITECTURE.md` (onboarding map), the detailed conversation/state/answer-source/ASR contracts, `docs/TEST_STRATEGY.md` (evidence), and `docs/CHANGE_CHECKLIST.md` (workflow).
- **Historical documents do not override these merely because they carry a "LOCKED" or "FINAL" label** — the authority hierarchy in `docs/ARCHITECTURE.md` §3 governs precedence.

### Rationale
Knowledge held only by the project owner and non-durable AI conversations is not a maintainable artefact; regressions occurred when later changes were made without a complete, current system map.

### Alternatives considered
**Relying on historical phase documents as primary authority** — rejected; the audits repeatedly found historical documents not reconciled with current behaviour.

### Consequences
#### Benefits
A new maintainer (human or AI) has a defined onboarding sequence and authoritative document set; AI agents are instructed to diagnose against approved contracts rather than memory.

#### Costs and constraints
Behavioural changes must update the applicable contract **in the same change** — real, ongoing overhead, not optional polish.

### Maintenance obligations
New maintainers follow the onboarding sequence in `docs/ARCHITECTURE.md` §21; AI agents diagnose against approved contracts rather than memory (`docs/CHANGE_CHECKLIST.md` §23).

### Evidence and traceability
`docs/ARCHITECTURE.md` §3, §20, §21; `docs/CHANGE_CHECKLIST.md`; all six other approved contracts.

### Reconsider when
The documentation set is found systematically out of date with production behaviour despite the maintenance cadence in `docs/TEST_STRATEGY.md` §21 — the maintenance process, not this ADR's principle, should be revisited first.

## ADR-018 — Large central client and server files are a documented constraint, not endorsed target architecture

Status: `Current constraint — not an endorsed target`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Maintainers
Decision type: current structural constraint

### Context
`docs/ARCHITECTURE.md` §16 and §19 document `scripts/ui_server.py` and `ui/app.js` as very large, high-density files implementing routing, normalisation, the answer-source priority chain, frame selection, rendering, ASR lifecycle, recovery interception, and state application — flagged as a structural constraint, not something the architecture proposes to fix.

### Decision
- `scripts/ui_server.py` and `ui/app.js` **remain large central files** at the R2 baseline, **documented honestly** as a constraint, not intentional target architecture.
- The R2 programme **does not authorise opportunistic decomposition**; surgical fixes must avoid unrelated refactoring (`docs/CHANGE_CHECKLIST.md` §6).

### Rationale
These files contain high-density, interdependent behaviour accumulated across many phases. Broad refactoring during recovery would have obscured regressions, conflicting with ADR-019's priority. Decomposition requires dedicated design, migration, and rollback planning not undertaken at R2.

### Alternatives considered
**Immediate decomposition as part of the R2 programme** — rejected, per ADR-019's precedence of behavioural preservation during recovery.

### Consequences
#### Benefits
No new regression risk was introduced by attempting decomposition during a stabilisation effort.

#### Costs and constraints
Both files remain difficult to reason about locally; a local change can shift shared ordering or helper behaviour (`docs/ARCHITECTURE.md` §16's high-risk list) — carried forward into every contract referencing these files as high-risk zones.

### Maintenance obligations
Do not treat "the file is large" as sufficient justification for an unscoped refactor bundled into a behavioural fix.

### Evidence and traceability
`docs/ARCHITECTURE.md` §16, §19; `docs/CHANGE_CHECKLIST.md` §6.

### Reconsider when
The approved contracts and test coverage are judged sufficient to support controlled extraction, a specific maintenance cost justifies the migration risk, and a proposal identifies stable component boundaries with a migration/rollback plan (§5).

## ADR-019 — Regression recovery prioritises behavioural preservation over architectural elegance

Status: `Accepted — recovery safeguard`
Decision date: `2026-07-12`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: R2 recovery programme
Decision type: maintenance governance

### Context
The commit history leading to the R2 baseline (`657529a`, `e2f373a`, `3be0315`) shows a pattern of narrow, named regression fixes rather than broad rewrites, consistent with `AI_CONTEXT.md`'s "minimal change policy" (§1.3) and Regression Discipline section.

### Decision
- During R2 recovery, **restore verified product capability before undertaking broad redesign**.
- Fixes should be **bounded and additive**; **unrelated cleanup is excluded**.
- Architectural improvement proposals must be **separated** from recovery fixes, not bundled into them.

### Rationale
Prior reversions resulted from broad changes interacting with poorly documented behaviour. A stable, well-understood baseline is a precondition for safe evolution, not an optional nicety.

### Alternatives considered
**Combining regression fixes with architectural cleanup** — rejected; identified as a contributing pattern to prior instability.

### Consequences
#### Benefits
Regression fixes remain traceable to a specific named defect (e.g. `tests/test_stale_answer_loop_regression.py`, `tests/test_e4_client_handoff_regression.py`).

#### Costs and constraints
"Cleaner code" is explicitly **not sufficient justification** if behavioural risk is unbounded; large refactors require separate approval and their own ADR.

### Maintenance obligations
`docs/CHANGE_CHECKLIST.md` requires explicit scope declaration for every change and rejects "broad refactoring inside a regression fix" as a reviewer-rejection criterion (§22).

### Evidence and traceability
Commits `657529a`, `e2f373a`, `3be0315`; `AI_CONTEXT.md` §1.3, "Regression Discipline"; `docs/CHANGE_CHECKLIST.md` §6, §22.

### Reconsider when
The system reaches a maintenance state where the approved contracts and test coverage are judged sufficient to absorb larger structural changes without disproportionate regression risk — see also ADR-018, which this ADR's precedence directly gates.

## ADR-020 — Model allocation separates diagnosis from mechanical implementation

Status: `Accepted — R2 baseline`
Decision date: `2026-07-13`
Verified baseline: `3be0315b2c9f7316b03ac2183a887f602ae9a297` / `architecture-baseline-2026-07-12-r2`
Decision owners: Maintainers
Decision type: maintenance governance

### Context
`docs/CHANGE_CHECKLIST.md` §23 records this same policy as part of its AI coding-agent rules, established during the R2 documentation programme's own workflow.

### Decision
- Use **Claude Opus or Claude Sonnet** for diagnosis and review when deeper reasoning is required.
- Use **Claude Sonnet or another cheaper suitable model** for implementation once diagnosis is settled.
- **Model choice never replaces evidence, tests, review, human approval, or scope control** — it governs *which model performs a step*, not *whether the step is required*.

### Rationale
Diagnosis benefits from deeper reasoning across multiple contracts; mechanical implementation, once scope is fixed, typically does not. Cost/token constraints should be managed without lowering verification standards.

### Alternatives considered
**Uniform model allocation regardless of task type** — rejected as unnecessarily costly for mechanical work with no evidenced diagnosis-quality benefit.

### Consequences
#### Benefits
Diagnosis quality is preserved where it matters most; implementation cost is reduced without lowering the evidence/testing/review bar.

#### Costs and constraints
Requires correctly judging when diagnosis is "settled" before switching allocation — a misjudged switch risks applying a cheaper model to a still-open diagnostic question.

### Maintenance obligations
This policy is maintained in `docs/CHANGE_CHECKLIST.md` §23; this ADR records why it exists rather than duplicating its operational wording.

### Evidence and traceability
`docs/CHANGE_CHECKLIST.md` §23.

### Reconsider when
Available model options or their relative cost/capability trade-offs change materially enough that the current allocation no longer reflects the underlying rationale.

## 4. Cross-decision themes

### 4.1 Separation of responsibilities
A recurring pattern across these ADRs is the deliberate separation of concerns that could plausibly have been merged, because merging them was found or judged to reduce diagnosability:

- **Answer and frame** (ADR-003) — what the persona says versus what happens next.
- **Current response and following request** (ADR-006) — E4's deferred handoff.
- **Client and server** (ADR-007, ADR-010) — distributed state ownership; recovery interception that never reaches the server.
- **Transient state and persistent memory** (ADR-007, ADR-008) — `conversation_state`/`state_update` versus `LEARNER_MEMORY_KEYS`-bounded persistence.
- **Code identity and functional correctness** (ADR-015) — `/api/version` versus a smoke scenario.
- **Source content and generated artifacts** (ADR-013) — authoritative input versus derived, gitignored output.
- **Diagnosis and implementation** (ADR-020) — which model performs which kind of step.

In each case, the separation exists because collapsing the two concerns previously made regressions harder to localise and diagnose.

### 4.2 Recovery safeguards
The following accepted practices arose directly from regression recovery, not from a pre-planned design:

- Explicit state ownership (ADR-007).
- The approved-contracts source hierarchy (ADR-017).
- Bounded, additive changes during recovery (ADR-019).
- The seven architecture and change contracts themselves as mandatory controls (ADR-017).
- Deployment SHA verification separated from functional verification (ADR-015).
- Execution-path-based evidence classification (ADR-016).
- The prohibition on unrelated refactoring during a regression fix (ADR-019, ADR-018).

These are labelled `Accepted — recovery safeguard` specifically to distinguish them from deliberate product decisions (ADR-001, ADR-002) — they exist because of what regression recovery found, not because of an independent product judgement.

### 4.3 Current constraints versus target direction
The following current facts are **not** automatically endorsed as future architecture, and should not be cited as if they were:

- Large central files (ADR-018).
- Hybrid inline/JSON content (ADR-012).
- Explicit-only artifact generation with unresolved production provisioning (ADR-013).
- Absence of a browser-automation framework (ADR-016; `docs/TEST_STRATEGY.md` §3.F).
- Distributed state with no single canonical object (ADR-007).
- Manual production smoke checks (ADR-015).

Each of these has an explicit "Reconsider when" condition in its own ADR. Citing one of these as evidence that the system *should* stay this way, rather than *currently is* this way, is a misreading of this document.

### 4.4 How future evolution should occur
A proposal to change any accepted decision in this document should:

1. Identify the ADR affected.
2. Reproduce the limitation that motivates reconsideration.
3. Propose a replacement decision.
4. Document migration and rollback.
5. Identify which of the seven behavioural contracts the change affects.
6. Add appropriate tests, classified honestly per `docs/TEST_STRATEGY.md` §3.
7. Preserve existing behaviour, or explicitly document intentional breakage and its justification.
8. Mark the prior ADR `Superseded` (with a link to the replacement) or amended, per §2 and §7.

## 5. Decision-change template

```text
Affected ADR:
Current decision:
Reason for reconsideration:
Evidence:
Proposed decision:
Alternatives:
Behavioural contracts affected:
State/migration impact:
Compatibility impact:
Testing plan:
Deployment/rollback plan:
Documentation updates:
Proposed status of existing ADR:
```

## 6. Deferred decision register

This register records topics that are known and real, but deliberately not decided at the R2 baseline. It does not choose a solution for any of them.

| Topic | Current state | Why deferred | Evidence needed before deciding |
| ----- | -------------- | -------------- | ---------------------------------- |
| External generative-AI integration | No external AI call in the ordinary turn path (ADR-014) | Cost, latency, moderation, and consistency implications not evaluated; product differentiation depends on structured behaviour (ADR-001) | A bounded use case with defined eligibility, fallback, cost, and privacy controls (`AI_CONTEXT.md` §12) |
| Server/client decomposition | `scripts/ui_server.py` and `ui/app.js` remain large central files (ADR-018) | Decomposition risk during/after recovery outweighs current benefit; no stable component boundaries identified | A concrete decomposition proposal with stable boundaries, migration, and compatibility tests |
| Unified content schema | Hybrid inline/JSON content persists (ADR-012) | Migration risk during recovery; no unified schema designed | A content-consolidation proposal with migration and regression-testing plan |
| Generated-artifact packaging/provisioning | Explicit-only local generation; deployed provisioning mechanism unverified (ADR-013) | No packaging/provisioning architecture selected or verified against Railway | A verified provisioning mechanism, or an explicit packaging decision with deployment testing |
| Browser automation framework | No Playwright/Puppeteer/Selenium/Cypress/Jest/jsdom present (`docs/TEST_STRATEGY.md` §3.F) | Not implemented; scope and maintenance cost of introducing one not assessed | A framework proposal with CI integration and maintenance-cost assessment |
| Managed ASR/TTS provider | Browser-native `SpeechRecognition`/`speechSynthesis` only (ADR-009) | Cost, credentials, privacy, and latency of a managed provider not evaluated | A provider proposal with cost, privacy, latency, and fallback plan |
| State centralisation | State remains distributed across multiple owners (ADR-007) | No migration plan exists; regression risk of a state-model rewrite not assessed | A centralisation proposal with a full migration and compatibility plan for existing consumers |
| CI migration from bare `unittest` to authoritative pytest tiers | CI's `unit-tests` job runs `python -m unittest -v`, which does not execute the pytest `live_server`/core tiers (`docs/TEST_STRATEGY.md` §4) | Actual GitHub Actions execution count has not been verified from workflow logs; migration scope not assessed | Inspection of actual CI logs, followed by a concrete CI workflow proposal |
| Automated production smoke testing | Production verification is manual operational evidence (`/api/version` + manual smoke, ADR-015) | No automated smoke-test mechanism implemented; scope and target scenarios not defined | A concrete smoke-test proposal with target scenarios and a hosting/scheduling plan |
| Challenge-history persistence-path correction | `data/progress_history.json` ignores `MANDARINOS_DATA_DIR` (`docs/ARCHITECTURE.md` §6.4) | Fix scope (migrate the fixed path versus honour the env var) not decided | A proposal specifying the corrected path behaviour and a migration plan for existing files |

## 7. Supersession rules

- **Never delete an accepted ADR solely because the implementation changed.**
- **Mark it `Superseded`** in its `Status` field.
- **Link to the replacement ADR** by number, in both directions.
- **Record the effective commit/date** of the supersession.
- **Preserve the historical rationale** — do not rewrite a superseded record to match the new decision.
- **Update the decision index** (§3) to reflect the new status and any renumbering-free replacement entry.
- **Update affected behavioural contracts** in the same change that supersedes the ADR.
- **Do not use a superseded ADR as current implementation guidance** — check the `Status` field before relying on any ADR's `Decision` section.

## 8. Traceability appendix

| ADR | Primary implementation surfaces | Primary contracts | Representative verification |
| --- | ---------------------------------- | -------------------- | ------------------------------- |
| ADR-001 | Conversation loop overall | `docs/CONVERSATION_ARCHITECTURE.md` | `docs/TEST_STRATEGY.md` §9 (conversation-regression testing) |
| ADR-002 | `personas/*.json`, `_resolve_persona` | `docs/ANSWER_SOURCE_CONTRACT.md` | Persona direct-function tests (`docs/TEST_STRATEGY.md` §3.A) |
| ADR-003 | `scripts/ui_server.py` answer/frame paths | `docs/ANSWER_SOURCE_CONTRACT.md`, `docs/CONVERSATION_ARCHITECTURE.md` | `docs/TEST_STRATEGY.md` §8 |
| ADR-004 | `scripts/ui_server.py` priority chain | `docs/ANSWER_SOURCE_CONTRACT.md` | `docs/TEST_STRATEGY.md` §9, §22 |
| ADR-005 | `_FRAME_ORDER`, `skip_when` | `docs/CONVERSATION_ARCHITECTURE.md` | `tests/test_e4_topic_handoff.py`'s `_FRAME_ORDER` check |
| ADR-006 | `state_update.current_engine`, `_resolveNextEngineId()` | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md` | `docs/TEST_STRATEGY.md` §8 (E4 cross-boundary evidence) |
| ADR-007 | `conversation_state`/`state_update`, client globals | `docs/STATE_CONTRACT.md` | `docs/TEST_STRATEGY.md` §11 |
| ADR-008 | `scripts/learner_memory.py` | `docs/STATE_CONTRACT.md` | `docs/TEST_STRATEGY.md` §11 |
| ADR-009 | `ui/app.js` `SpeechRecognition`/`speechSynthesis` | `docs/ASR_PIPELINE.md` | `docs/TEST_STRATEGY.md` §3.F, §10 |
| ADR-010 | `ui/app.js` recovery interception, `content/recovery_phrases.json` | `docs/ASR_PIPELINE.md` | `docs/TEST_STRATEGY.md` §13's recovery requirements |
| ADR-011 | `ui/app.js`/`ui/styles.css` Challenge Mode | `docs/ASR_PIPELINE.md` §14 | `tests/test_challenge_recovery.py` |
| ADR-012 | Inline pools in `scripts/ui_server.py`; content JSON | `docs/ANSWER_SOURCE_CONTRACT.md` | Content-change checklist (`docs/CHANGE_CHECKLIST.md` §12) |
| ADR-013 | `tools/build_runtime_artifacts.py`, `runtime/out_phase7/` | `docs/ARCHITECTURE.md` §14, `docs/TEST_STRATEGY.md` §12–§13 | Generated-artifact checklist (`docs/CHANGE_CHECKLIST.md` §13) |
| ADR-014 | `scripts/ui_server.py` `/api/run_turn` | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/ANSWER_SOURCE_CONTRACT.md` | Absence of any external-AI call in the handler |
| ADR-015 | `/api/version`, deployment configuration | `docs/ARCHITECTURE.md` §13, `docs/CHANGE_CHECKLIST.md` §19 | Deployment checklist (`docs/CHANGE_CHECKLIST.md` §19) |
| ADR-016 | `tests/`, `.github/workflows/coverage_scan.yml` | `docs/TEST_STRATEGY.md` | `docs/TEST_STRATEGY.md` §3, §4 |
| ADR-017 | All seven approved documents | All seven approved documents | `docs/ARCHITECTURE.md` §20–§21 |
| ADR-018 | `scripts/ui_server.py`, `ui/app.js` | `docs/ARCHITECTURE.md` §16, §19 | Scope-control checklist (`docs/CHANGE_CHECKLIST.md` §6) |
| ADR-019 | Regression-fix commits (e.g. `657529a`, `3be0315`) | `docs/CHANGE_CHECKLIST.md` | Reviewer-rejection criteria (`docs/CHANGE_CHECKLIST.md` §22) |
| ADR-020 | Maintainer/agent workflow | `docs/CHANGE_CHECKLIST.md` §23 | N/A — governance policy, not code |

Application baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Application baseline tag: `architecture-baseline-2026-07-12-r2`
Documentation branch: `docs/architecture-v1`
Document status: `Draft v1`
Last verified date: `2026-07-13`
