import { initialState as _initialState, reduce } from "./state/cardPanelState.js";

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
// Play button handler: simulate audio playback and emit AUDIO_PLAYED traces
if (playBtn) {
  playBtn.addEventListener("click", (e) => {
  e.stopPropagation();
    // compute utterance id and text
    const baseId = (state.activeCard && (state.activeCard.utterance_id || state.activeCard.id)) || state.activeCardId;
const utterance_id = baseId ? `card:${baseId}` : "card:unknown";
    const text = (state.activeCard && (state.activeCard.content || state.activeCard.title)) || "";
    console.log("PLAY clicked. text length =", text.length);
console.log("PLAY text preview =", text.slice(0, 80));
console.log("voices =", window.speechSynthesis ? window.speechSynthesis.getVoices().length : "no speechSynthesis");
  // Minimal TTS (no helpers)
try {
  if (!("speechSynthesis" in window) || !text) return;

  const synth = window.speechSynthesis;

  const speak = () => {
    const voices = synth.getVoices();
    console.log("VOICE LIST:", voices.map(v => ({ name: v.name, lang: v.lang })));

    synth.cancel();

  const u = new SpeechSynthesisUtterance(text);
 
// prefer Chinese voice if available
const zh = voices.find(v => (v.lang || "").toLowerCase().startsWith("zh"));
if (zh) {
  u.voice = zh;
  u.lang = zh.lang;
} else {
  // fallback: English voice so it always speaks
  const en = voices.find(v => (v.lang || "").toLowerCase().startsWith("en"));
  if (en) {
    u.voice = en;
    u.lang = en.lang;
  }
}

       synth.speak(u);
  };

  // If voices are not loaded yet, wait once
  if (synth.getVoices().length === 0) {
    synth.onvoiceschanged = () => {
      synth.onvoiceschanged = null; // run once
      speak();
    };
  } else {
    speak();
  }
} catch (err) {
  console.error("TTS error:", err);
}
    const duration_ms = Math.max(200, Math.round(text.length * 40));

    // if something is currently playing, cancel and emit incomplete event
    if (currentPlay) {
      const now = Date.now();
      const elapsed = now - currentPlay.start;
      clearTimeout(currentPlay.timeoutId);
      emitUITrace({ type: "AUDIO_PLAYED", payload: { utterance_id: currentPlay.utterance_id, duration_ms: elapsed, completed: false } });
      currentPlay = null;
    }

    // emit start event (completed: false) and schedule completion
    emitUITrace({ type: "AUDIO_PLAYED", payload: { utterance_id, duration_ms, completed: false } });
    const timeoutId = setTimeout(() => {
      emitUITrace({ type: "AUDIO_PLAYED", payload: { utterance_id, duration_ms, completed: true } });
      currentPlay = null;
    }, duration_ms);

    currentPlay = { utterance_id, start: Date.now(), timeoutId, duration_ms };
  });
}

// defaults
window.addEventListener("load", () => {
  frameSelect.value = "tests/fixtures/frame_open_card.json";
  render();
});

runBtn.addEventListener("click", runTurn);

