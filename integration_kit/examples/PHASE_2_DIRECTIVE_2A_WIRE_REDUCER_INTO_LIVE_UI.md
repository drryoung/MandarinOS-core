PHASE_2_DIRECTIVE_2A_WIRE_REDUCER_INTO_LIVE_UI.txt

Phase: 2A
Title: Wire cardPanelState reducer into live UI runtime (trace-driven)
Status: IMPLEMENT NOW (do not start Phase 3 until Phase 2A is locked)
Scope rule: UI-only changes. No engine/resolver refactors. No event/trace contract changes.

Locked assumptions (DO NOT MODIFY)

Already complete and correct:

Engine/runtime:

OPEN_CARD resolver implemented and unit-tested

Deterministic OPEN_CARD wiring and trace emission

Golden trace fixture and integration tests passing

process_turn emits TURN_START → OPEN_CARD → TURN_END

Simulator run_turn.py works

UI shell:

stdlib Python server + vanilla JS

runs process_turn via POST /api/run_turn

renders trace events

shows right-side Card Panel when OPEN_CARD appears

Event naming locked:

OPEN_CARD = event type

"OPEN_CARD_FIRED" = result/status label in TURN_END.payload

Phase 1 locked + committed:

ui/state/cardPanelState.js exists and exports initialState and reduce

ui/tests/cardPanelReplay.test.mjs passes via:
node ui/tests/cardPanelReplay.test.mjs

Constraints:

Do NOT revisit coverage/scanners/content hygiene/earlier runtime contracts.

Do NOT refactor engine/resolver.

Do NOT change trace event shapes or names.

Goal (Phase 2A objective)

Make the live UI Card Panel state be driven by the Phase 1 reducer:

Maintain a single UI state object (initialState)

Dispatch TRACE_EVENT_RECEIVED for every trace event in arrival order

Dispatch CARD_PANEL_CLOSED on close button click

Render Card Panel strictly as a projection of reducer state

Result: “What is tested” (reducer behavior) becomes “what ships” (live UI behavior).

Non-goals

No new event types

No new engine payload fields

No UI framework introduction

No redesign of layout/styling beyond minimal wiring

No new cardStore implementation unless it already exists (Phase 2A may use existing card loading approach)

Required code changes

A) Introduce UI state + dispatch loop in app.js (or equivalent)

Import reducer:

Import { initialState, reduce } from ui/state/cardPanelState.js

If your JS is not module-based yet, convert the minimal necessary files to ES module usage:

Prefer adding type="module" on the main script tag, OR

Use a minimal bundling-free approach consistent with your current setup

Keep changes minimal and localized.

Add module-level state:

let uiState = initialState;

Add dispatch(action):

uiState = reduce(uiState, action);

renderCardPanel(uiState); (see Section B)

(Optional) render debug state (not required)

When a turn returns trace array:

Do NOT directly open/close the card panel imperatively.

Instead:

Reset uiState = initialState at the start of each run (recommended for determinism per run)
OR preserve state across runs if current UI requires it. Choose one and document it.

For each event in trace in order:
dispatch({ type: "TRACE_EVENT_RECEIVED", payload: { traceEvent: event } })

Important: apply trace events in the exact order returned by the server.

B) Make Card Panel rendering state-driven

Implement (or adapt existing) rendering so that:

If uiState.isOpen is true:

Card panel is visible

“No card opened” placeholder is hidden

If uiState.isOpen is false:

Card panel is hidden

“No card opened” placeholder is visible (or show last state if that is current behavior; pick one and be consistent)

Displayed content priority:

If uiState.error != null:

Show deterministic error UI (title + cardId + short explanation)

Else if uiState.activeCard != null:

Show active card content (minimal is fine)

Else:

Show loading/placeholder (optional)

Close button behavior:

Close button must dispatch:
dispatch({ type: "CARD_PANEL_CLOSED" })

Do NOT mutate DOM state outside renderCardPanel(uiState).

C) Integrate card resolution path (minimal, using existing mechanism)

Phase 2A must ensure uiState.activeCard is populated in live UI.

You may use whichever card loading mechanism already exists in the repo:

Existing server endpoint: GET /api/cards?path=...

Existing fixtures: cards_index.fixture.json, cards.fixture.json

Existing in-app lookup logic

Minimal requirement:

When OPEN_CARD is received and you obtain card content (or discover it missing), dispatch:
dispatch({ type: "CARD_RESOLVED", payload: { cardId, card, error } })

Notes:

If card loading is synchronous today (preloaded JSON), dispatch CARD_RESOLVED immediately.

If asynchronous (fetch), dispatch when fetch completes.

Keep implementation minimal and consistent with current code.

Acceptance criteria (Phase 2A lock gate)

Phase 2A is LOCKED only when all are true:

Live UI behavior is reducer-driven:

No direct “if OPEN_CARD then open panel” imperative toggles remain

OPEN_CARD handling flows through TRACE_EVENT_RECEIVED into reducer

Close button works via reducer:

Clicking close dispatches CARD_PANEL_CLOSED

Panel hides deterministically

Card resolution updates reducer state:

Valid card_id shows card content

Invalid/missing card_id shows error state (visible in UI)

Existing engine + golden trace tests remain green (no changes expected)

Phase 1 replay test still passes:
node ui/tests/cardPanelReplay.test.mjs

Minimal verification checklist

A) Automated:

Run:
node ui/tests/cardPanelReplay.test.mjs

Must output ALL TESTS PASSED.

B) Manual UI smoke:

Start UI server

Click Run (or equivalent) using a turn that emits OPEN_CARD

Confirm:

panel opens

content appears OR deterministic error UI appears

Click Close

Confirm panel closes

Run again

Confirm panel opens again on OPEN_CARD

Implementation order (smallest irreversible steps)

Step 1: Import reducer + establish uiState + dispatch() (no UI changes yet)
Step 2: Replace imperative OPEN_CARD toggles with TRACE_EVENT_RECEIVED dispatch loop
Step 3: Implement renderCardPanel(uiState) and remove direct DOM mutations outside it
Step 4: Ensure CARD_RESOLVED dispatch updates uiState.activeCard/error in live path
Step 5: Verify replay test still passes + manual smoke checklist passes
Step 6: Commit with tight scope message (UI-only)

Completion output (commit requirements)

Commit must include only UI wiring changes for reducer-driven Card Panel and any minimal helper functions needed (renderCardPanel, small imports).

Do NOT:

Change runtime contracts

Change event names

Refactor unrelated UI areas

END OF PHASE_2_DIRECTIVE_2A_WIRE_REDUCER_INTO_LIVE_UI.md