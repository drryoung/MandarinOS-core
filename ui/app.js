import { initialState as _initialState, reduce } from "./state/cardPanelState.js";
import { ttsSpeak } from "./ttsSpeak.js";

const frameSelect = document.getElementById("frameSelect");
const runBtn = document.getElementById("runBtn");
const traceEl = document.getElementById("trace");
const cardPanel = document.getElementById("cardPanel");
const noCard = document.getElementById("noCard");
const cardIdEl = document.getElementById("cardId");
const cardTitle = document.getElementById("cardTitle");
const cardBody = document.getElementById("cardBody");
const cardError = document.getElementById("cardError");
const playBtn = document.getElementById("playBtn");

let state = Object.assign({}, _initialState);
let uiTrace = [];
let currentPlay = null; // { utterance_id, start, timeoutId, duration_ms }

function dispatch(action) {
  state = reduce(state, action);
  render();
}

function appendTrace(event) {
  uiTrace.push(event);
  // If you already have a dedicated trace renderer, call it here.
  // Otherwise render() + any existing trace rendering will handle it.
}

function render() {
  // trace is rendered separately by runTurn; card panel driven by reducer state
  if (state.isOpen) {
    cardPanel.classList.remove("hidden");
    noCard.style.display = "none";
    cardError.textContent = state.error ? (state.error.message || state.error.kind || "Error") : "";
    cardIdEl.textContent = state.activeCardId || "";
    cardTitle.textContent = (state.activeCard && state.activeCard.title) || "";
    cardBody.textContent = (state.activeCard && state.activeCard.content) || "";
    // play affordance visible for surface devices; enable when a card is active
    if (playBtn) {
      playBtn.style.display = "inline-block";
      playBtn.disabled = !(state.activeCardId || (state.activeCard && (state.activeCard.content || state.activeCard.title)));
    }
  } else {
    cardPanel.classList.add("hidden");
    noCard.style.display = "block";
    cardError.textContent = "";
    cardIdEl.textContent = "";
    cardTitle.textContent = "";
    cardBody.textContent = "";
    if (playBtn) playBtn.style.display = "none";
  }
}

function renderTrace() {
  traceEl.textContent = JSON.stringify(uiTrace, null, 2);
}

function emitUITrace(ev) {
  uiTrace.push(ev);
  renderTrace();
  // also feed into reducer pipeline
  dispatch({ type: "TRACE_EVENT_RECEIVED", payload: { traceEvent: ev } });

}

async function resolveCard(cardId, cards_path) {
  try {
    const q = new URLSearchParams({ path: cards_path });
    const cardsResp = await fetch(`/api/cards?${q.toString()}`);
    const cards = await cardsResp.json();
    const card = cards && cards[cardId] ? cards[cardId] : null;
    if (card) {
      dispatch({ type: "CARD_RESOLVED", payload: { cardId, card, error: null } });
    } else {
      dispatch({ type: "CARD_RESOLVED", payload: { cardId, card: null, error: { kind: "CARD_NOT_FOUND", message: "Card not found", cardId } } });
    }
  } catch (e) {
    dispatch({ type: "CARD_RESOLVED", payload: { cardId, card: null, error: { kind: "FETCH_ERROR", message: String(e), cardId } } });
  }
}

async function runTurn() {
  const frame_path = frameSelect.value;
  const payload = {
    frame_path,
    cards_index_path: "tests/fixtures/cards_index.fixture.json",
    cards_path: "tests/fixtures/cards.fixture.json",
    env: "prod",
  };

  try {
    const resp = await fetch("/api/run_turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    console.log("run_turn response:", data);
    if (data.error) {
      traceEl.textContent = `Error: ${data.error}`;
      // close panel via reducer
      dispatch({ type: "CARD_PANEL_CLOSED" });
      return;
    }

    const trace = data.trace || [];
    console.log("trace length:", trace.length, "first:", trace[0] && trace[0].type);
      uiTrace = uiTrace.concat(trace);
      renderTrace();

    // Dispatch trace events to reducer
    for (const ev of trace) {
      dispatch({ type: "TRACE_EVENT_RECEIVED", payload: { traceEvent: ev } });
    }

    // If reducer opened a card and it needs resolution, resolve it
    if (state.isOpen && state.activeCardId && !state.activeCard) {
      await resolveCard(state.activeCardId, payload.cards_path);
    }
  } catch (e) {
    traceEl.textContent = `Exception: ${e}`;
    dispatch({ type: "CARD_PANEL_CLOSED" });
  }
}

// allow clicking the card panel to close it
cardPanel.addEventListener("click", (e) => {
  if (e.target === cardPanel) dispatch({ type: "CARD_PANEL_CLOSED" });
});

// defaults
window.addEventListener("load", () => {
  frameSelect.value = "tests/fixtures/frame_open_card.json";
  render();
});

runBtn.addEventListener("click", runTurn);
if (playBtn) {
  playBtn.addEventListener("click", () => {
    if (!state.isOpen) return;

    const text =
      (state.activeCard && (state.activeCard.content || state.activeCard.title)) ||
      "";

    if (!text) return;

    const utterance_id = `card:${state.activeCardId || "unknown"}:panel`;

    // Trace: intent
    dispatch({
      type: "TRACE_EVENT_RECEIVED",
      event: {
        type: "AUDIO_PLAY_REQUESTED",
        ts: Date.now(),
        utterance_id,
        source: "card_panel",
        card_id: state.activeCardId || null,
        text,
      },
    });

    // Speak (side-effect)
    ttsSpeak({
      text,
      lang: "zh-CN",
      utterance_id,
      onEvent: (evt) => {
        dispatch({
          type: "TRACE_EVENT_RECEIVED",
          event: evt.utterance_id ? evt : { ...evt, utterance_id },
        });
      },
    });
  });
}

