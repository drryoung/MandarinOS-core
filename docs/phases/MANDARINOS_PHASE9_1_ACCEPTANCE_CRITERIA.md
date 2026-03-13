# MandarinOS Phase 9.1 Acceptance Criteria

Selector-driven next question (same engine only)

Purpose: Prove that the conversation can continue without the user
selecting the next frame, while keeping the Phase 6 runtime lock intact.

------------------------------------------------------------------------

## 1. Selector controls the next question

When the learner presses **Next**:

UI → sends next_question request\
Server → runs selector\
Selector → chooses next frame\
Server → returns frame + options\
UI → renders next partner question

Verification: - User does not manually choose the next frame. - Frame
selector dropdown is not required for continuation.

------------------------------------------------------------------------

## 2. Runtime architecture remains unchanged

The Phase 6 runtime must remain untouched.

Verification targets: - engine.process_turn - runtime artifacts - trace
contract - runtime schemas

Only the orchestration layer selects the frame.

------------------------------------------------------------------------

## 3. Response shape remains identical

The server response returned after selector execution must be identical
to the current run_turn response shape.

Verification: The UI rendering path for the following must require no
changes:

-   frame text
-   options
-   hint system
-   card panel
-   transcript
-   TTS playback

------------------------------------------------------------------------

## 4. Deterministic frame selection

Selector must not use randomness.

Frame selection must follow:

-   same engine only
-   exclude recent_frame_ids
-   select first valid candidate in stable order

Verification: Repeated runs with identical state produce the same next
frame.

------------------------------------------------------------------------

## 5. No frame repetition

Selector must prevent recently asked questions.

Verification: Frames appearing in recent_frame_ids (last K turns,
e.g. 5) are not selected.

------------------------------------------------------------------------

## 6. Conversation loop remains intact

Transcript continues to show:

Partner question\
User response\
Partner acknowledgement\
Partner reciprocity (你呢？)

Pressing **Next** produces a new partner question chosen by the
selector.

------------------------------------------------------------------------

## 7. UI stability

No Phase 7--8 features regress:

-   hint cascade
-   word clicking
-   card panel
-   option hints
-   "You said" confirmation
-   transcript rendering
-   question TTS

All must behave exactly as before.

------------------------------------------------------------------------

## 8. Engine switching NOT implemented yet

Selector must remain within the current_engine.

Verification: All next questions belong to the same engine as the
previous one.

------------------------------------------------------------------------

## 9. Minimal conversation state

Selector request includes only:

-   session_id
-   current_engine
-   last_partner_frame_id
-   recent_frame_ids

Optional state fields are not required yet.

------------------------------------------------------------------------

## Definition of Done

Phase 9.1 is complete when:

User answers → presses Next → system selects next frame automatically →
conversation continues → runtime unchanged → UI unchanged.
