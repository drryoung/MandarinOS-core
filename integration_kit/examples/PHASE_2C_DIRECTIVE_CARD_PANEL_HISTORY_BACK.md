PHASE_2C_DIRECTIVE_CARD_PANEL_HISTORY_BACK.txt

Phase: 2C
Title: Card Panel history + Back navigation (UI-only, trace-driven)
Status: IMPLEMENT NOW (do not start Phase 4 until Phase 3B is locked)
Scope rule: UI-only changes. No engine/resolver refactors. No event/trace contract changes.

Locked assumptions (DO NOT MODIFY)

Locked and complete:

Runtime/engine contracts unchanged:

OPEN_CARD event type

payload.card_id exists

TURN_END.payload includes "OPEN_CARD_FIRED" label (unchanged)

Phase 1 locked:

ui/state/cardPanelState.js exports initialState and reduce

node ui/tests/cardPanelReplay.test.mjs passes

Phase 2A locked:

Live UI wired to reducer (trace-driven)

app.js is ES module, dispatches TRACE_EVENT_RECEIVED and CARD_RESOLVED

Card Panel render is driven by reducer state

Phase 2B locked:

Reducer ignores stale CARD_RESOLVED (cardId must equal activeCardId)

Replay tests include test_stale_card_resolved_is_ignored and pass

Goal (Phase 2C objective)

Add simple Card Panel navigation history so the user can go Back to the previously opened card within the panel, without any new runtime events.

Behavior:

Each time a new OPEN_CARD becomes active, push the previous activeCardId onto history (if different and non-null)

Back button pops history and makes that card the active card

Back operation is UI-only and does not require engine involvement

Non-goals

No Forward button (unless trivial and explicitly included below; default is NO)

No persistence across page refresh

No new trace events

No changes to engine/resolver

No multi-turn replay across server runs (history is UI session only)

Required state changes (reducer)

In ui/state/cardPanelState.js:

A) Extend initialState with:

history: [] (array of cardId strings)

B) Update reducer logic for TRACE_EVENT_RECEIVED handling OPEN_CARD:
When receiving OPEN_CARD with newCardId:

If state.activeCardId exists and state.activeCardId !== newCardId:
history = state.history + [state.activeCardId]

Set activeCardId = newCardId

Set isOpen = true

Clear activeCard and error as per current behavior (keep existing logic)

Do not add duplicates for same cardId

C) Add new reducer action type:

CARD_PANEL_BACK

Handling CARD_PANEL_BACK:

If history is empty:
return state unchanged

Else:

let prevId = last element of history

history = history without last element

set activeCardId = prevId

set isOpen = true

set activeCard = null (until resolved)

clear error = null
Important:

Back should behave like selecting a card: it changes activeCardId and expects a CARD_RESOLVED later to fill activeCard.

The stale CARD_RESOLVED guard from Phase 2B must continue to apply.

Required UI changes (render + wiring)

In the Card Panel UI (app.js + index.html if needed):

A) Add a Back button inside the Card Panel UI:

Label: "Back"

Visible/enabled only when uiState.history.length > 0

On click:
dispatch({ type: "CARD_PANEL_BACK" })
Then trigger card resolution for the new activeCardId (same mechanism used for OPEN_CARD path)
i.e., fetch/lookup the card and dispatch CARD_RESOLVED

B) Ensure Close still works:

Close dispatches CARD_PANEL_CLOSED (unchanged)

C) History must be purely UI session state:

Do not store in localStorage

Keep visual changes minimal.

Tests (replay test additions)

Update ui/tests/cardPanelReplay.test.mjs to add ONE new test:

Test name:

test_history_back_restores_previous_card

Scenario:

OPEN_CARD("card_a") + CARD_RESOLVED("card_a")

OPEN_CARD("card_b") + CARD_RESOLVED("card_b")
-> history should now contain ["card_a"]

CARD_PANEL_BACK
-> activeCardId becomes "card_a"
-> activeCard becomes null until resolved

CARD_RESOLVED("card_a")
-> activeCard is card_a

Assertions:

After step 2: history length === 1 and history[0] === "card_a"

After step 3: activeCardId === "card_a" and activeCard == null

After step 4: activeCard.id === "card_a"

Ensure all existing tests still pass.

Acceptance criteria (Phase 2C lock gate)

Phase 2C is LOCKED only when:

Node replay tests pass:

node ui/tests/cardPanelReplay.test.mjs

Includes new test_history_back_restores_previous_card

Outputs ALL TESTS PASSED

Live UI:

Opening two cards enables Back

Clicking Back returns to previous card deterministically

Close still works

No contract changes; no new runtime events

No scope creep:

No engine/resolver modifications

Minimal changes limited to UI state + UI wiring + replay test

Implementation order (smallest irreversible steps)

Step 1: Add history to initialState + OPEN_CARD push behavior in reducer
Step 2: Add CARD_PANEL_BACK action in reducer
Step 3: Add replay test test_history_back_restores_previous_card
Step 4: Update UI: add Back button + dispatch + trigger resolution for activeCardId
Step 5: Run node ui/tests/cardPanelReplay.test.mjs and confirm ALL TESTS PASSED
Step 6: Manual UI smoke: open two cards, back, close
Step 7: Commit with tight scope message

Commit requirements

Commit should include only:

ui/state/cardPanelState.js

ui/tests/cardPanelReplay.test.mjs

index.html and/or app.js for Back button UI wiring (minimal)

No other changes.

END OF PHASE_2C_DIRECTIVE_CARD_PANEL_HISTORY_BACK.txt