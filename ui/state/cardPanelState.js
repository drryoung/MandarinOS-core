export const initialState = {
  isOpen: false,
  activeCardId: null,
  activeCard: null,
  error: null,
  history: [],

  panelOptions: null,
};



export function reduce(state, action) {
  const s = Object.assign({}, state);
  if (!action || !action.type) return s;

  switch (action.type) {
    case "TRACE_EVENT_RECEIVED": {
      const te = action.payload && action.payload.traceEvent;

      // OPEN_CARD trace
      if (te && te.type === "OPEN_CARD") {
        const cardId = te.payload && te.payload.card_id;

        // push current active onto history when navigating to a new card
        if (s.activeCardId) {
          s.history = Array.isArray(s.history)
            ? s.history.concat([s.activeCardId])
            : [s.activeCardId];
        }

        s.isOpen = true;
        s.activeCardId = cardId || null;
        s.activeCard = null;
        s.error = null;

        // clear options when changing cards
        s.panelOptions = null;
      }

      // OPTIONS_AVAILABLE trace
      if (te && te.type === "OPTIONS_AVAILABLE") {
        const p = te.payload || {};

        // Ignore stale options (wrong card)
        if (p.card_id && s.activeCardId && p.card_id !== s.activeCardId) {
          return s;
        }

        s.panelOptions = {
          section_title: p.section_title || "Modeled options",
          options: Array.isArray(p.options) ? p.options : []
        };
      }

      return s;
    }

    case "CARD_RESOLVED": {
      const p = action.payload || {};
      const cardId = p.cardId;

      // Ignore CARD_RESOLVED events that don't match the currently active card id
      if (s.activeCardId !== cardId) {
        return s;
      }

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
      s.panelOptions = null;
      return s;
    }

    case "CARD_PANEL_BACK": {
      // navigate back in history; if none, close panel
      if (Array.isArray(s.history) && s.history.length > 0) {
        const prev = s.history[s.history.length - 1];
        s.history = s.history.slice(0, s.history.length - 1);

        s.isOpen = true;
        s.activeCardId = prev || null;
        s.activeCard = null;
        s.error = null;

        s.panelOptions = null;
        return s;
      }

      s.isOpen = false;
      s.activeCardId = null;
      s.activeCard = null;
      s.error = null;
      s.history = [];
      s.panelOptions = null;

      return s;
    }

    default:
      return s;
  }
}

