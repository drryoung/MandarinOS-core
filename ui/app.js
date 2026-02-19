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
const cardCloseBtn = document.getElementById("cardCloseBtn");

let state = Object.assign({}, _initialState);
let uiTrace = [];
let currentPlay = null; // { utterance_id, start, timeoutId, duration_ms }


function dispatch(action) {
  state = reduce(state, action);
  render();
}
if (cardCloseBtn) {
  cardCloseBtn.addEventListener("click", () => {
    dispatch({ type: "CARD_PANEL_CLOSED" });
  });
}

function appendTrace(event) {
  uiTrace.push(event);
  // If you already have a dedicated trace renderer, call it here.
  // Otherwise render() + any existing trace rendering will handle it.
}
function clearEl(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

function makeDiv(className, text) {
  const d = document.createElement("div");
  if (className) d.className = className;
  if (text !== undefined) d.textContent = text;
  return d;
}
function renderModeledOptions(containerEl, panelOptions, state) {
  if (!panelOptions || !Array.isArray(panelOptions.options) || panelOptions.options.length === 0) return;

  const h3 = document.createElement("h3");
  h3.textContent = panelOptions.section_title || "Modeled options";
  containerEl.appendChild(h3);

  const list = makeDiv("option-list");
  panelOptions.options.forEach((opt, idx) => {
    const row = makeDiv("option-row");

    const textWrap = makeDiv("option-text");
    textWrap.appendChild(makeDiv("", opt.text || ""));

    if (opt.pinyin) {
      textWrap.appendChild(makeDiv("option-pinyin", opt.pinyin));
    }

    const btn = document.createElement("button");
    btn.className = "option-play";
    btn.textContent = "🔊";

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!state.isOpen) return;

      const optionId = opt.id || String(idx);
      const cardId = state.activeCardId || panelOptions.card_id || "card";
      const utterance_id = `card:${cardId}:opt:${optionId}`;
      const text = opt.text || "";

      emitUITrace({
        type: "AUDIO_PLAY_REQUESTED",
        timestamp: new Date().toISOString(),
        payload: {
          utterance_id,
          source: "card_panel_option",
          card_id: cardId,
          option_id: optionId,
          text,
        },
      });

      ttsSpeak({
        text,
        lang: "zh-CN",
        utterance_id,
        onEvent: (traceEntry) => emitUITrace(traceEntry),
      });
    });

    row.appendChild(textWrap);
    row.appendChild(btn);
    list.appendChild(row);
  });

  containerEl.appendChild(list);
}

function render() {
  // trace is rendered separately by runTurn; card panel driven by reducer state
  if (state.isOpen) {
    cardPanel.classList.remove("hidden");
    noCard.style.display = "none";
    cardError.textContent = state.error ? (state.error.message || state.error.kind || "Error") : "";
    cardIdEl.textContent = state.activeCardId || "";
    cardTitle.textContent = (state.activeCard && state.activeCard.title) || "";
const mainText = (state.activeCard && state.activeCard.content) || "";
clearEl(cardBody);
cardBody.appendChild(makeDiv("card-main", mainText));
renderModeledOptions(cardBody, state.panelOptions, state);


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
  // Force a default selection if none is selected
  if (frameSelect.selectedIndex === -1 && frameSelect.options.length > 0) {
    frameSelect.selectedIndex = 0;
  }

  const selected = frameSelect.value; 
  // expected format: "engine_id|frame_id"

  const [engine_id, frame_id] = selected.split("|");

  const payload = {
    engine_id,
    frame_id,
    env: "prod",
    turn_uid: "ui_" + Date.now()
  };


  let res;
  try {
    res = await fetch("/api/run_turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    emitUITrace({
      type: "UI_ERROR",
      timestamp: new Date().toISOString(),
      payload: { message: String(e) }
    });
    return;
  }

  if (!res.ok) {
    const txt = await res.text();
    emitUITrace({
      type: "UI_ERROR",
      timestamp: new Date().toISOString(),
      payload: { status: res.status, body: txt }
    });
    return;
  }

  const data = await res.json();
  const trace = data.trace || [];
  for (const ev of trace) emitUITrace(ev);

  // Important: resolve the opened card so the panel Play button has content
  if (state.isOpen && state.activeCardId && !state.activeCard) {
    await resolveCard(state.activeCardId, "tests/fixtures/cards.fixture.json");
  }
}


// allow clicking the card panel to close it
cardPanel.addEventListener("click", (e) => {
  if (e.target === cardPanel) dispatch({ type: "CARD_PANEL_CLOSED" });
});

// defaults
window.addEventListener("load", () => {
  frameSelect.value = "tests/fixtures/frame_open_card_with_options.json";
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
   emitUITrace({
  type: "AUDIO_PLAY_REQUESTED",
  timestamp: new Date().toISOString(),
  payload: {
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
     onEvent: (traceEntry) => {
        emitUITrace(traceEntry);
      },
    });
  });
}

