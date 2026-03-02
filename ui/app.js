import { initialState as _initialState, reduce } from "./state/cardPanelState.js";
import { ttsSpeak } from "./ttsSpeak.js";

const frameSelect = document.getElementById("frameSelect");
const runBtn = document.getElementById("runBtn");
const traceEl = document.getElementById("trace");
const dataBuildInfoEl = document.getElementById("dataBuildInfo");
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

// ── Phase 7.3: Frame Render Tokens ──────────────────────────────────────────

/** @type {{ schema_version: string, frames: Record<string, Array<{t:string,id?:string,s:string}>> } | null} */
let frameRenderTokens = null;

/** @type {{ by_word_id: Record<string, string> } | null} */
let cardsIndex = null;

async function loadFrameRenderTokens() {
  try {
    const resp = await fetch("/runtime/out_phase7/frame_render_tokens.runtime.json");
    if (!resp.ok) {
      console.warn(`[app] frame_render_tokens not available (HTTP ${resp.status}); sentence rendering degraded.`);
      return;
    }
    frameRenderTokens = await resp.json();
    console.info(`[app] frame_render_tokens loaded (${Object.keys(frameRenderTokens.frames || {}).length} frame(s))`);
  } catch (e) {
    console.warn("[app] frame_render_tokens load failed:", e);
  }
}

async function loadCardsIndex() {
  try {
    const resp = await fetch("/runtime/out_phase7/cards_index.runtime.json");
    if (!resp.ok) {
      console.warn(`[app] cards_index not available (HTTP ${resp.status})`);
      return;
    }
    cardsIndex = await resp.json();
    console.info(`[app] cards_index loaded`);
  } catch (e) {
    console.warn("[app] cards_index load failed:", e);
  }
}

/**
 * Render the frame sentence into #frameSentence using builder-produced tokens.
 * Falls back to frame.text if tokens are unavailable for this frame.
 * @param {{ id: string, text: string }} frame
 */
function renderFrameSentence(frame) {
  const el = document.getElementById("frameSentence");
  if (!el) return;

  while (el.firstChild) el.removeChild(el.firstChild);

  const tokens =
    frameRenderTokens &&
    frameRenderTokens.frames &&
    frame &&
    frame.id &&
    frameRenderTokens.frames[frame.id];

  if (!tokens) {
    // Fallback: plain text, no guessing
    el.textContent = (frame && frame.text) || "";
    return;
  }

  tokens.forEach((tok) => {
    const span = document.createElement("span");
    span.textContent = tok.s;

    if (tok.t === "word") {
      span.className = "frame-word-token";
      span.style.cursor = "pointer";
      span.title = tok.id;
      span.addEventListener("click", () => {
        const cardId =
          cardsIndex &&
          cardsIndex.by_word_id &&
          cardsIndex.by_word_id[tok.id];
        if (!cardId) {
          console.warn(`[app] renderFrameSentence: no card_id for word_id '${tok.id}' in cards_index`);
          return;
        }
        emitUITrace({
          type: "OPEN_CARD",
          timestamp: new Date().toISOString(),
          payload: {
            engine_id: frameSelect.options[frameSelect.selectedIndex]?.dataset?.engineId || null,
            frame_id: frame.id,
            card_id: cardId,
            reason: "card_available"
          }
        });
        dispatch({ type: "OPEN_CARD", payload: { card_id: cardId } });
        resolveCard(cardId, "tools/cards/out/cards_by_id.json");
      });
    } else {
      span.className = "frame-lit-token";
    }

    el.appendChild(span);
  });
}

// ── end Phase 7.3 ────────────────────────────────────────────────────────────

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
    const titleText = (state.activeCard && state.activeCard.title) || "";
    cardTitle.textContent = titleText;


    // Phase 6: Single source of truth for card content
    const cardContent = (state.activeCard && state.activeCard.content) || {};
    const headwordHanzi =
      (cardContent.headword && cardContent.headword.hanzi)
        ? cardContent.headword.hanzi
        : "";
    const pinyin =
      (cardContent.headword && cardContent.headword.pinyin)
        ? cardContent.headword.pinyin
        : "";
    const meaning = cardContent.meaning || "";

    // Main display text
    const mainText = [headwordHanzi, pinyin, meaning]
      .filter(Boolean)
      .join("\n");

    // Render main text
    clearEl(cardBody);

    const mainDisplayDiv = document.createElement("div");
    mainDisplayDiv.className = "card-main";

    if (headwordHanzi) mainDisplayDiv.appendChild(makeDiv("card-main-hanzi", headwordHanzi));
    if (pinyin) mainDisplayDiv.appendChild(makeDiv("card-main-pinyin", pinyin));
    if (meaning) mainDisplayDiv.appendChild(makeDiv("card-main-meaning", meaning));

cardBody.appendChild(mainDisplayDiv);


    // Phase 6: Word-level play button
    if (headwordHanzi) {
      const wordPlay = document.createElement("button");
      wordPlay.type = "button";
      wordPlay.className = "word-play";
      wordPlay.textContent = " 🔊 Play word";

      wordPlay.addEventListener("click", (e) => {
        e.stopPropagation();
        const cardId = state.activeCardId || "unknown_card";
        const utterance_id = `card:${cardId}:word`;

        emitUITrace({
          type: "AUDIO_PLAY_REQUESTED",
          timestamp: new Date().toISOString(),
          payload: { utterance_id, text: headwordHanzi, source: "card_headword" }
        });

        ttsSpeak({
          text: headwordHanzi,
          lang: "zh-CN",
          utterance_id,
          onEvent: (traceEntry) => emitUITrace(traceEntry),
        });
      });

      cardTitle.appendChild(wordPlay);
    }


renderModeledOptions(cardBody, state.panelOptions, state);
// --- Phase 6: render clickable characters from content.word_composition (if present)
const compChars =

  state.activeCard &&
  state.activeCard.content &&
  state.activeCard.content.word_composition &&
  Array.isArray(state.activeCard.content.word_composition.characters)
    ? state.activeCard.content.word_composition.characters
    : null;

if (compChars && compChars.length) {
  const compWrap = makeDiv("card-composition", "");
  



  const row = document.createElement("div");
  row.className = "card-composition-row";

  compChars.forEach((c, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "char-chip";
    btn.textContent = c.char || c.hanzi || "";
    btn.disabled = !btn.textContent;

    btn.addEventListener("click", async () => {
      const ch = btn.textContent;
      const cardId = state.activeCardId || "unknown_card";
      const utteranceId = `card:${cardId}:char:${idx}`;

      emitUITrace({
        type: "AUDIO_PLAY_REQUESTED",
        timestamp: new Date().toISOString(),
        payload: { utterance_id: utteranceId, text: ch, source: "card_composition_char" }
      });

      ttsSpeak({
        text: ch,
        lang: "zh-CN",
        utterance_id: utteranceId,
        onEvent: (traceEntry) => emitUITrace(traceEntry),
      });
    });

    row.appendChild(btn);
  });

  compWrap.appendChild(row);

  const hint = document.createElement("div");
  hint.className = "card-composition-hint";
  hint.innerHTML = "<em>Tap a character to hear it.</em>";
  compWrap.appendChild(hint);

  cardBody.appendChild(compWrap);
}
// --- end composition rendering



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
  if (!traceEl) {
    console.warn("traceEl not found in DOM");
    return;
  }

  // Presentation-only: show latest line + cap rendered events to avoid UI slowdown
  const MAX_RENDER_EVENTS = 200;

  const last = Array.isArray(uiTrace) && uiTrace.length ? uiTrace[uiTrace.length - 1] : null;
  const t = last && typeof last === "object" ? (last.type || "(no type)") : "(none)";
  const ts = last && typeof last === "object" ? (last.timestamp || "") : "";
  const header = ts ? `Latest: ${t} @ ${ts}\n` : `Latest: ${t}\n`;

  const total = Array.isArray(uiTrace) ? uiTrace.length : 0;
  const start = Math.max(0, total - MAX_RENDER_EVENTS);
  const slice = Array.isArray(uiTrace) ? uiTrace.slice(start) : [];

  // Presentation-only: hide noisy TTS interruptions (still exist in uiTrace; just not shown)
  const filtered = slice.filter((ev) => {
    if (!ev || typeof ev !== "object") return true;
    if (ev.type !== "AUDIO_ERROR") return true;
    const err = ev.payload && ev.payload.error;
    return err !== "interrupted";
  });

  const hiddenCount = slice.length - filtered.length;

  const noteBase =
    total > MAX_RENDER_EVENTS
      ? `Showing last ${MAX_RENDER_EVENTS} of ${total} events (render-capped)\n`
      : `Showing ${total} events\n`;

  const noteHidden = hiddenCount
    ? `Hidden: ${hiddenCount} AUDIO_ERROR interrupted (trace-noise filter)\n\n`
    : `\n`;

  try {
    traceEl.textContent = header + noteBase + noteHidden + JSON.stringify(filtered, null, 2);
  } catch (err) {
    console.error("Trace render failed:", err);
    traceEl.textContent = "[Trace render error — see console]";
  }
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

async function loadPackFramesIntoDropdown() {
  emitUITrace({ type: "UI_INFO", timestamp: new Date().toISOString(), payload: { message: "loadPackFramesIntoDropdown start" } });

  try {
    const packs = ["p1_frames.json", "p2_frames.json"];
    const items = [];

    for (const pack of packs) {
      const resp = await fetch(`/${pack}`);
      if (!resp.ok) continue;
      const data = await resp.json();
      const frames = Array.isArray(data.frames) ? data.frames : [];

      for (const f of frames) {
        if (!f) continue;
        const eid = f.engine;
        const fid = f.id;
        if (typeof eid === "string" && eid && typeof fid === "string" && fid) {
          items.push({ engine_id: eid, frame_id: fid });
        }
      }
    }

    // If nothing loaded, do nothing (keep existing fixture dropdown)
    if (items.length === 0) {
      emitUITrace({ type: "UI_ERROR", timestamp: new Date().toISOString(), payload: { message: "Pack frames loaded, but 0 usable (missing engine_id/frame_id?)" } });
      return;
    }

    items.sort((a, b) => (a.engine_id + "::" + a.frame_id).localeCompare(b.engine_id + "::" + b.frame_id));

    frameSelect.innerHTML = "";
    for (const it of items) {
      const opt = document.createElement("option");
      opt.value = it.frame_id;
      opt.textContent = `${it.engine_id} :: ${it.frame_id}`;
      opt.dataset.engineId = it.engine_id;
      frameSelect.appendChild(opt);
    }
    frameSelect.selectedIndex = 0;
  } catch (e) {
    // If anything goes wrong, keep existing fixture dropdown and keep UI running.
    emitUITrace({
      type: "UI_ERROR",
      timestamp: new Date().toISOString(),
      payload: { message: "loadPackFramesIntoDropdown failed (kept fixtures)", error: String(e) }
    });
  }
}



async function runTurn() {
  const selected = frameSelect.value;
  const payload = {
    env: "dev",
    turn_uid: "ui_" + Date.now()
  };

  if (selected && selected.endsWith(".json")) {
    payload.frame_path = selected;
  } else {
    const selectedOption = frameSelect.options[frameSelect.selectedIndex];
    const engineId = selectedOption && selectedOption.dataset ? selectedOption.dataset.engineId : null;

    if (!engineId) {
      emitUITrace({
        type: "UI_ERROR",
        timestamp: new Date().toISOString(),
        payload: { message: "Missing engine id for selected pack frame" }
      });
      return;
    }

    payload.engine_id = engineId;
    payload.frame_id = selected;
  }

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

  // Phase 7.3: render the frame sentence after each turn
  const frameId = payload.frame_id || null;
  const fallbackText = (data.frame && data.frame.text) || "";
  if (frameId) {
    renderFrameSentence({ id: frameId, text: fallbackText });
  }

  // Important: resolve the opened card so the panel Play button has content
  if (state.isOpen && state.activeCardId && !state.activeCard) {
    const usingFixtureFrame = String(frameSelect.value || "").includes("tests/fixtures/");
    const cardsPath = usingFixtureFrame
      ? "tests/fixtures/cards.fixture.json"
      : "tools/cards/out/cards_by_id.json";
    await resolveCard(state.activeCardId, cardsPath);
  }
}


// allow clicking the card panel to close it
cardPanel.addEventListener("click", (e) => {
  if (e.target === cardPanel) dispatch({ type: "CARD_PANEL_CLOSED" });
});

// UI-only: human-readable label for which data build is currently in use
const UI_DATA_BUILD_LABEL = "p1/p2 enriched (schema-preserving) + characters_1200 (v3 content) + runtime_indexes_v1";


// defaults
window.addEventListener("load", async () => {
  // Phase 7.3: load render tokens and cards index in parallel with existing loads
  await Promise.all([
    loadPackFramesIntoDropdown(),
    loadFrameRenderTokens(),
    loadCardsIndex(),
  ]);
  if (dataBuildInfoEl) dataBuildInfoEl.textContent = `Data: ${UI_DATA_BUILD_LABEL}`;
  render();
});

runBtn.addEventListener("click", runTurn);
if (playBtn) {
  playBtn.addEventListener("click", () => {
        // Panel Play: derive speakable text from DOM (presentation truth), not reducer state
    const hanziEl = document.querySelector("#cardBody .card-main-hanzi");
    const titleEl = document.getElementById("cardTitle");
    const bodyEl = document.getElementById("cardBody");

    let text = "";
    if (hanziEl && hanziEl.textContent && hanziEl.textContent.trim()) {
      text = hanziEl.textContent.trim();
    } else if (titleEl && titleEl.textContent && titleEl.textContent.trim()) {
      text = titleEl.textContent.trim();
    } else if (bodyEl && bodyEl.textContent && bodyEl.textContent.trim()) {
      text = bodyEl.textContent.trim();
    }

    if (!text) {
      emitUITrace({
        type: "AUDIO_ERROR",
        timestamp: new Date().toISOString(),
        payload: { utterance_id: "card:unknown:panel", error: "No speakable text found in Card Panel DOM" },
      });
      return;
    }

  //  if (!state || !state.activeCard) return;

        if (state.activeCard) {
      const hw = state.activeCard.headword && state.activeCard.headword.hanzi;
      if (typeof hw === "string" && hw.trim()) {
        text = hw.trim();
      } else if (typeof state.activeCard.content === "string" && state.activeCard.content.trim()) {
        text = state.activeCard.content.trim();
      } else if (typeof state.activeCard.title === "string" && state.activeCard.title.trim()) {
        text = state.activeCard.title.trim();
      }
    }

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

// UI-only: make card ID clickable to copy
if (cardIdEl) {
  cardIdEl.style.cursor = "pointer";

  cardIdEl.addEventListener("click", async () => {
    const text = cardIdEl.textContent;
    if (!text) return;

    try {
      await navigator.clipboard.writeText(text);

      // Show a temporary indicator without overwriting the ID text
      const original = cardIdEl.textContent;
      cardIdEl.textContent = `${original} (copied)`;
      setTimeout(() => {
        // Remove only the indicator
        if (cardIdEl.textContent === `${original} (copied)`) {
          cardIdEl.textContent = original;
        }
      }, 1000);


    } catch (err) {
      console.warn("Clipboard copy failed:", err);
    }
  });
}

