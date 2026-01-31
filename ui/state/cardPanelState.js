export const initialState = {
  isOpen: false,
  activeCardId: null,
  activeCard: null,
  error: null,
};

export function reduce(state, action) {
  const s = Object.assign({}, state);
  if (!action || !action.type) return s;

  switch (action.type) {
    case "TRACE_EVENT_RECEIVED": {
      const te = action.payload && action.payload.traceEvent;
      if (te && te.type === "OPEN_CARD") {
        const cardId = te.payload && te.payload.card_id;
        s.isOpen = true;
        s.activeCardId = cardId || null;
        s.activeCard = null;
        s.error = null;
      }
      return s;
    }
    case "CARD_RESOLVED": {
      const p = action.payload || {};
      const cardId = p.cardId;
      const card = p.card || null;
      const error = p.error || null;
      s.isOpen = true;
      s.activeCardId = cardId || null;
      s.activeCard = card;
      s.error = error;
      return s;
    }
    case "CARD_PANEL_CLOSED": {
      s.isOpen = false;
      return s;
    }
    default:
      return s;
  }
}
