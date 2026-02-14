// Minimal card panel reducer module for replay tests
export function initialState() {
  return {
    isOpen: false,
    activeCardId: null,
    error: null,
  };
}

export function applyAction(state, action, cards) {
  const s = Object.assign({}, state);
  if (!action || !action.type) return s;

  switch (action.type) {
    case "OPEN_CARD": {
      const cardId = action.payload && action.payload.card_id;
      if (cardId && cards && Object.prototype.hasOwnProperty.call(cards, cardId)) {
        s.isOpen = true;
        s.activeCardId = cardId;
        s.error = null;
      } else {
        s.isOpen = false;
        s.activeCardId = null;
        s.error = { kind: "CARD_NOT_FOUND" };
      }
      return s;
    }
    case "CLOSE_PANEL": {
      s.isOpen = false;
      return s;
    }
    default:
      return s;
  }
}
