<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class E: Archival evidence or dated report**
>
> - **Current use:** Dated evidence of system-state findings at Phase 12B.
> - **May guide current implementation:** No.
> - **Current authority:** `docs/STATE_CONTRACT.md` and verified current code.
> - **Principal caution:** Its `LOCKED` constraints describe a dated snapshot and must not be treated as the current state contract.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

MANDARINOS — SYSTEM STATE SNAPSHOT (PHASE 12B)

1. Phase Status
- Phase 7: Learning Interaction Layer (UI loop + spoken/option response capture)
- Phase 8: Conversation Loop UI (transcript, hints, cards UI plumbing)
- Phase 9: Conversation Engine Integration (server-driven next-frame selection)
- Phase 10: Memory + Persona Foundations (learner memory persistence + persona plumbing)
- Phase 11: Adaptive Conversation Intelligence Core (move_type grammar, selector hygiene, ordering guards)
- Phase 11B: Conversational Role Expansion (EXTEND frame set introduced; partner asks + volunteers statements)
- Phase 11C: Persona Layer & Discoverability (runtime persona binding; EXTEND voice_line + discoverable facts)
- Phase 12B: Minimal repair + curiosity refinement (soft first repair + probe chain limit)

2. Core Conversation Loop (CURRENT BEHAVIOUR)
- Partner -> Frame is selected by server; UI renders `frame_text` and speaks it.
- User -> Learner responds either by:
  - speaking and getting ASR matched to an option, or
  - clicking an option panel.
- Ack -> On the next server turn, Phase 10.5 reaction micro-layer may add a short reaction prefix, or a reaction/bridge frame may be selected (depending on selector output).
- Reciprocity -> For early exchanges, server may add a blended reciprocity option ending with `你呢？` onto the next-question options when `last_turn_was_answer` is present (Phase 10.5 behavior).
- Next -> Server chooses the next frame using the existing selector architecture (no selector rewrite).
- Where curiosity fits:
  - After a response turn, server can include `probe_offer=true` and `probe_options=[...]`.
  - UI shows a probe row; learner taps a probe to trigger an additional turn.
- Where repair fits:
  - When the learner’s attempt is not understood (ASR mismatch / unmatched), UI uses recovery phrases and repeats/helps/advances depending on the “consecutive not-understood” count.

3. Curiosity Behaviour (FINAL)
- When `probe_offer` appears:
  - Server sets `probe_offer=true` and returns `probe_options` for the UI probe row.
  - UI shows probe buttons; tapping one sends it as the user’s next turn (via `runProbeTurn()`).
- MAX_PROBE_CHAIN rule:
  - `MAX_PROBE_CHAIN = 1`
  - In server `_should_surface_curiosity()`: if `probe_depth >= 1`, return `False` immediately (suppresses probes).
- `probe_depth` logic (client state -> server gate):
  - Initial: `window._probeDepth = 0`.
  - When a probe is tapped:
    - client increments `window._probeDepth += 1`
    - client sends `conversation_state.probe_depth` in the probe turn payload.
  - Reset:
    - on a normal non-probe understood answer, client sets `window._probeDepth = 0` when calling `runTurn(true, { last_turn_was_answer: true })`.
- When probes are suppressed:
  - When `probe_depth >= 1` (i.e., after the first probe follow-up is answered).
  - After reset to `probe_depth = 0`, probes can appear again later when the existing curiosity rules say yes.
- Engine change / bridge reset:
  - Not currently added as a separate rule.
  - Practically, the reset happens on the next understood non-probe answer.

4. Repair Behaviour (FINAL)
- Source of “not understood” response selection:
  - UI function `getRecoveryPhraseForNotUnderstood()` selects from runtime recovery phrases.
- Ladder on `consecutive_not_understood`:
  - 1st failure (`consecutive == 1`):
    - try phrases with `recovery_action: "soft"` (examples added: `嗯？`, `你说…？`, `啊？`)
    - if soft pool is empty, fall back to the existing behavior (repeat/slower logic).
  - 2nd failure (`consecutive == 2`):
    - use existing rotation pool (phrases where `recovery_action` is `repeat` or `slower`).
  - 3rd or more (`consecutive >= 3`):
    - use existing “move on” pool where `recovery_action: "next_turn"`.
- Reset condition:
  - When the learner produces a valid understood answer (ASR matched option / non-recovery option), UI resets `window._consecutiveNotUnderstood = 0`.

5. Discoverability Layer
- Voice line (`partner_prefix`)
  - Shown only on the FIRST EXTEND visit in a given engine per session.
  - Session tracking:
    - client sends `conversation_state.revealed_voice_lines[engine]`.
    - server gates voice line if not yet revealed for that engine.
- Partner fact (`partner_fact`)
  - Shown once when all gates pass:
    - frame `move_type` is `EXTEND`
    - session gate: `revealed_partner_facts[engine]` is not set yet
    - anti-dump: voice line must have been shown first (fact cannot appear before voice line)
    - depth gate: `same_engine_chain_count >= FACT_REVEAL_DEPTH` (FACT_REVEAL_DEPTH = 3)
    - cross-session gate (suppression): if learner memory already records `partner_facts_seen[partner_id][engine]=true`
  - Session vs cross-session:
    - Session: prevents re-showing within the current session.
    - Cross-session: learner memory suppresses repeat reveals for the same partner and engine.

6. Architecture Constraints (LOCKED)
- No selector rewrite.
- No scoring expansion.
- Frames remain conversational capability; personas remain overlay identity.
- Persona behavior is runtime-bound via `partner_id` and EXTEND frame enrichment only.
- Extensibility principle:
  - Adding personas is data-only (drop new persona JSON files into `personas/`).
  - No persona-specific selector rules; no duplicated frames per persona.

