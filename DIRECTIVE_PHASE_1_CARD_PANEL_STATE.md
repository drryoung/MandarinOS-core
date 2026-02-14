DIRECTIVE_PHASE_1_CARD_PANEL_STATE.md

Phase: 1
Title: Card Panel Runtime State + UX Hardening (Trace-Driven)
Status: IMPLEMENT NOW (do not start Phase 2 until Phase 1 is locked)
Scope rule: UI-only changes. No engine/resolver refactors. No event/trace contract changes.

0) Locked assumptions (do not modify)

The following are already complete and correct:

OPEN_CARD resolver implemented + unit-tested

Deterministic OPEN_CARD wiring + trace emission

Golden trace fixture + integration tests passing

Minimal engine pipeline emits: TURN_START → OPEN_CARD → TURN_END

Simulator entrypoint run_turn.py works

Minimal UI shell (stdlib Python server + vanilla JS) runs process_turn, renders trace, shows right-side Card Panel on OPEN_CARD

Event naming is locked:

OPEN_CARD = event type

"OPEN_CARD_FIRED" = result/status label in TURN_END.payload

Constraints:

Do NOT revisit coverage/scanners/content hygiene/runtime contracts.

Do NOT refactor engine/resolver unless explicitly requested.

1) Goal (Phase 1 objective)

Turn the Card Panel from “proof-of-wiring” into a deterministic, testable UI component driven entirely by trace events, with:

Stable open/close semantics

Deterministic card selection on OPEN_CARD

Graceful handling of missing/invalid card IDs (UI error state)

Simple card lookup + in-memory cache

Trace-replay test (no heavy frameworks)

2) Non-goals (explicit)

No new event types

No new engine payload fields

No UI routing framework

No refactor of server architecture

No redesign of visual styling beyond minimal affordances (close button, error box)

3) Deliverables
A) UI state model (single source of truth)

Implement a small reducer-style state container (UI-only):

State fields (minimum):

isOpen: boolean

activeCardId: string | null

activeCard: object | null

error: { kind: string, message: string, cardId?: string } | null

Recommended (lightweight but valuable):

history: string[] (stack of prior cardIds)

future: string[] (optional, for forward navigation)

B) Deterministic OPEN_CARD handling

Rule: the panel is a projection of trace events.

On receiving trace event { type: "OPEN_CARD", payload: { card_id } }:

Set isOpen = true

Set activeCardId = card_id

Resolve card:

If card exists: set activeCard = card, error = null

If missing: set activeCard = null, set error = { kind: "CARD_NOT_FOUND", message: "...", cardId }

Update history:

If activeCardId previously non-null and different from new id: push previous id onto history

Clear future if implemented

No fallback guessing. No silent failure.

C) Close behavior

Add a visible Close button to the Card Panel.

On close action:

Set isOpen = false

Keep history as-is (default)

Keep activeCardId and activeCard either:

Option 1 (preferred for simplicity): keep them (so reopening can show last card immediately)

Option 2: clear them (but keep history)
Pick one and be consistent; prefer Option 1 unless your current UI structure makes it messy.

Next OPEN_CARD must always:

Re-open panel (isOpen = true)

Replace active card with new OPEN_CARD target

D) Card lookup + cache (UI-only)

Implement a minimal card store:

Load cards_index.json once on UI boot.

Load card data in one of these ways (choose based on what already exists):

Load cards.json once and index in memory, OR

Fetch per-card endpoint when needed.

Add in-memory cache:

cache: Map(cardId -> cardObject | null)

Cache “not found” results as null to avoid repeated fetch loops.

E) Error panel UI

When error != null, show deterministic content:

Title: “Card not found” (or equivalent)

Display the cardId

Display a short debug hint: “This card_id was requested by OPEN_CARD but was not present in card store.”
No console-only errors.

F) Trace replay test (framework-free)

Add a small JS test runner that can replay a list of trace events into the reducer/state machine and assert state outcomes.

Must test:

OPEN_CARD with valid id opens panel and sets active card

Close hides panel; second OPEN_CARD reopens and updates active card

OPEN_CARD with invalid id opens panel and sets error state deterministically

Keep it lightweight:

Node script (preferred) OR browser-run script with console asserts.

No Jest/Mocha unless already present.

G) Manual smoke checklist file

Add a small checklist used to confirm lock criteria quickly.

4) File plan (adapt names to your repo, but keep structure)

If your current UI lives under something like ui/ or web/, place files accordingly.

Create or refactor into these UI modules:

ui/state/cardPanelState.js

Exports:

initialState

reduce(state, action)

Action creators (optional)

Actions (minimum):

TRACE_EVENT_RECEIVED (payload: traceEvent)

CARD_RESOLVED (payload: { cardId, card | null, error | null })

CARD_PANEL_CLOSED

ui/data/cardStore.js

Exports:

initCardStore() to load index (and optionally cards)

getCard(cardId) returns { card, error } using cache

ui/render/cardPanelView.js

renderCardPanel(state, domRefs) applies state to DOM

Includes close button wire-up (dispatch close action)

ui/replay/replayTrace.js

Pure function:

applyTraceEvents(events, reducer, initialState) => finalState

Used by tests and optionally by UI debug mode

ui/tests/cardPanelReplay.test.js (or .mjs)

Runs replay tests with simple assert(condition, msg).

ui/SMOKE_PHASE_1.md

Manual smoke steps (short)

If you already have a single app.js, you may keep it but must isolate state/logic in the above modules.

5) Implementation steps (smallest irreversible steps)
Step 1 — Introduce reducer + initial state (no DOM changes yet)

Create cardPanelState.js

Define state shape and reducer skeleton

Add minimal actions: TRACE_EVENT_RECEIVED, CARD_PANEL_CLOSED

Acceptance:

No behavior change yet; existing UI still works (panel may still be driven by old direct logic temporarily).

Step 2 — Route OPEN_CARD trace events through reducer

Identify where trace events are currently rendered/handled.

Instead of directly opening the panel in imperative code, dispatch TRACE_EVENT_RECEIVED.

Reducer behavior for OPEN_CARD:

Set isOpen=true, activeCardId=..., clear/set error placeholder

Trigger async card resolve (see Step 3) in caller (not inside reducer)

Acceptance:

Panel opens on OPEN_CARD (even if card content not yet loaded), no contract changes.

Step 3 — Add cardStore and async resolve path

Implement cardStore.js init + cache + getCard(cardId)

On OPEN_CARD handling path:

call getCard(cardId) and then dispatch CARD_RESOLVED with results

Reducer on CARD_RESOLVED:

only apply if payload.cardId === state.activeCardId (avoid race issues)

Acceptance:

Valid card IDs render actual content

Missing IDs render error UI state (even if minimal at first)

Step 4 — Render layer becomes a pure projection of state

Implement renderCardPanel(state)

It must:

show/hide based on isOpen

render either activeCard or error

wire close button to dispatch CARD_PANEL_CLOSED

Ensure closing is deterministic and does not break trace list rendering.

Acceptance:

Close works; next OPEN_CARD reopens and updates card display.

Step 5 — Add replay function + tests

Implement replayTrace.js

Add cardPanelReplay.test.js with 3 required tests:

valid OPEN_CARD

close + reopen with second OPEN_CARD

invalid OPEN_CARD => error

Acceptance:

Tests run via a simple command (document it), e.g. node ui/tests/cardPanelReplay.test.js

Step 6 — Add manual smoke checklist and lock

Add SMOKE_PHASE_1.md with:

run server

run a turn that produces OPEN_CARD

close panel

run again

force invalid card_id path (either by editing a local fixture input or using a known missing id test turn)

6) Acceptance criteria (Phase 1 lock gate)

Phase 1 is considered LOCKED only when all are true:

Engine tests remain green (no changes expected).

Golden trace fixtures remain unchanged and passing.

UI replay tests pass consistently.

Manual smoke checklist passes.

OPEN_CARD event type and TURN_END "OPEN_CARD_FIRED" label unchanged.

Missing/invalid card ID produces deterministic visible error panel (not blank, not console-only).

7) Notes on determinism (must follow)

Reducer is pure and deterministic.

All async card loading must be outside reducer.

Apply CARD_RESOLVED only if it matches current activeCardId.

UI must not “infer” card IDs or fallback to arbitrary cards.

8) Completion output (what to commit)

Commit should include:

New/updated JS modules for state/store/render

Replay test + runner instructions

Smoke checklist

Any minimal HTML changes required for close button/error box

No other refactors.

End of Phase 1 directive.