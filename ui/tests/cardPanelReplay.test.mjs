import { initialState, reduce } from "../state/cardPanelState.js";

function assert(cond, msg) {
  if (!cond) throw new Error("ASSERTION FAILED: " + msg);
}

function dispatchSequence(actions) {
  return actions.reduce((s, a) => reduce(s, a), initialState);
}

function openCardTrace(cardId) {
  return { type: "OPEN_CARD", payload: { card_id: cardId } };
}

function traceAction(traceEvent) {
  return { type: "TRACE_EVENT_RECEIVED", payload: { traceEvent } };
}

function closeAction() {
  return { type: "CARD_PANEL_CLOSED" };
}

function backAction() {
  return { type: "CARD_PANEL_BACK" };
}

function resolvedAction(cardId, card, error) {
  return { type: "CARD_RESOLVED", payload: { cardId, card, error } };
}

function test_valid_open_card_opens_panel() {
  const actions = [
    traceAction(openCardTrace("card_hello")),
    resolvedAction("card_hello", { id: "card_hello", title: "Hello" }, null),
  ];

  const s = dispatchSequence(actions);
  assert(s.isOpen === true, "panel should open");
  assert(s.activeCardId === "card_hello", "activeCardId should be card_hello");
  assert(!!s.activeCard, "activeCard should exist");
  assert(s.error == null, "error should be null");
}

function test_close_then_open_reopens() {
  const actions = [
    traceAction(openCardTrace("card_a")),
    resolvedAction("card_a", { id: "card_a" }, null),
    closeAction(),
    traceAction(openCardTrace("card_b")),
    resolvedAction("card_b", { id: "card_b" }, null),
  ];

  const s = dispatchSequence(actions);
  assert(s.isOpen === true, "panel should reopen");
  assert(s.activeCardId === "card_b", "activeCardId should update");
}

function test_invalid_open_sets_error() {
  const actions = [
    traceAction(openCardTrace("card_missing")),
    resolvedAction("card_missing", null, {
      kind: "CARD_NOT_FOUND",
      message: "Card not found",
      cardId: "card_missing",
    }),
  ];

  const s = dispatchSequence(actions);
  assert(s.isOpen === true, "panel opens even if missing");
  assert(s.activeCard == null, "activeCard should be null");
  assert(s.error && s.error.kind === "CARD_NOT_FOUND", "error should be set");
}

function test_stale_card_resolved_is_ignored() {
  const actions = [
    // open card_a then receive a resolved for card_b (stale)
    traceAction(openCardTrace("card_a")),
    resolvedAction("card_b", { id: "card_b", title: "Stale" }, null),
  ];

  const s = dispatchSequence(actions);
  assert(s.isOpen === true, "panel should remain open");
  assert(s.activeCardId === "card_a", "activeCardId should remain card_a");
  assert(s.activeCard == null, "activeCard should still be null");
  assert(s.error == null, "error should remain null");
}

function test_history_back_navigates_to_previous_card() {
  const actions = [
    traceAction(openCardTrace("card_a")),
    resolvedAction("card_a", { id: "card_a", title: "A" }, null),
    traceAction(openCardTrace("card_b")),
    resolvedAction("card_b", { id: "card_b", title: "B" }, null),
    backAction(),
  ];

  const s = dispatchSequence(actions);
  assert(s.isOpen === true, "panel should be open after back");
  assert(s.activeCardId === "card_a", "activeCardId should return to card_a");
  assert(s.activeCard == null, "activeCard should be unresolved (null) after back");
}

function test_back_with_empty_history_closes_panel() {
  const actions = [
    traceAction(openCardTrace("card_x")),
    // no resolved; back should close since no history
    backAction(),
  ];

  const s = dispatchSequence(actions);
  assert(s.isOpen === false, "panel should close when history empty");
  assert(s.activeCardId == null, "no activeCardId after close");
}

[test_valid_open_card_opens_panel,
 test_close_then_open_reopens,
 test_invalid_open_sets_error
 , test_stale_card_resolved_is_ignored
 , test_history_back_navigates_to_previous_card
 , test_back_with_empty_history_closes_panel
].forEach(t => {
  t();
  console.log("PASS:", t.name);
});

console.log("ALL TESTS PASSED");
