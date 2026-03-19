import { initialState as _initialState, reduce } from "./state/cardPanelState.js";
import { ttsSpeak } from "./ttsSpeak.js";

const frameSelect = document.getElementById("frameSelect");
const runBtn = document.getElementById("runBtn");
const nextBtn = document.getElementById("nextBtn");
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
let _directionCaps = { supports_reverse: false, supports_why: false };

// Phase 7 completion: transcript array for "You said" + Phase 8 Conversation Loop UI reuse.
// Each entry: { role: 'user'|'partner', text: string }. Append on option select; Phase 8 will render full transcript.
let conversationTranscript = [];
let transcriptDisplayMode = "zh";
let transcriptReplaySpeed = 1.0;
let transcriptLineUiState = {}; // { [lineId]: { showEn: boolean, showPy: boolean } }
let transcriptReplayState = { active: false, activeLineId: null, queue: [] };
let transcriptSegmentMode = false;
let transcriptSelectedLineIds = [];
let transcriptReplayToken = 0;
let userTranslationIndex = {};

function addTranscriptEntry(role, textZh, extras = {}) {
  conversationTranscript.push({
    id: "line_" + Date.now() + "_" + Math.floor(Math.random() * 10000),
    role: role === "partner" ? "partner" : "user",
    text_zh: textZh || "",
    text_en: extras.text_en || "",
    pinyin: extras.pinyin || "",
    frame_id: extras.frame_id || "",
    turn_uid: extras.turn_uid || "",
    replayable: true,
    created_at: new Date().toISOString(),
  });
}

function _normalizeTranscriptText(s) {
  return (s || "").trim().replace(/\s+/g, "");
}

function _upsertUserTranslation(hanzi, english) {
  const key = _normalizeTranscriptText(hanzi);
  const val = (english || "").trim();
  if (!key || !val) return;
  userTranslationIndex[key] = val;
}
// Phase 9.1: minimal conversation state for selector-driven next question (session_id, current_engine, last_partner_frame_id, recent_frame_ids)
if (typeof window._sessionId === "undefined") window._sessionId = "session_" + Date.now();
if (typeof window._recentFrameIds === "undefined") window._recentFrameIds = [];
// Phase 10: learner_id for memory persistence; last_answer (frame_id + selected_option_hanzi/submitted_text) sent with next_question when last_turn_was_answer
if (typeof window._learnerId === "undefined") window._learnerId = "default_learner";
if (typeof window._lastAnswer === "undefined") window._lastAnswer = null;
// Phase 10 Step 6: persona_id for persona-consistent stubs (e.g. probe responses); default first persona
if (typeof window._personaId === "undefined") window._personaId = "zhang_wei";
// Phase 10.5 behaviour state (client-side, lightweight)
if (typeof window._exchangeCount === "undefined") window._exchangeCount = 0;
if (typeof window._curiosityDepth === "undefined") window._curiosityDepth = 0;
if (typeof window._askChainCount === "undefined") window._askChainCount = 0;
if (typeof window._lastPartnerTurnType === "undefined") window._lastPartnerTurnType = "question";
if (typeof window._sameEngineChainCount === "undefined") window._sameEngineChainCount = 0;
if (typeof window._sameSlotChainCount === "undefined") window._sameSlotChainCount = 0;
if (typeof window._lastFocusSlot === "undefined") window._lastFocusSlot = "";
if (typeof window._pendingListeningMove === "undefined") window._pendingListeningMove = false;
if (typeof window._listeningWaitTurns === "undefined") window._listeningWaitTurns = 0;
if (typeof window._lastInterestLevel === "undefined") window._lastInterestLevel = "low";
if (typeof window._lastUserText === "undefined") window._lastUserText = "";
// Card panel: which cards have etymology expanded (click "Show etymology" to reveal). Enables future brush/radical clicks.
let _cardEtymologyExpanded = new Set();

// ── Phase 6: Frame Render Tokens ──────────────────────────────────────────

/** @type {{ schema_version: string, frames: Record<string, Array<{t:string,id?:string,s:string}>> } | null} */
let frameRenderTokens = null;

// Phase 7.4: canonical frame_tokens (byte-identical to frame_render_tokens; preferred)
let frameTokens = null;

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
    window._frameRenderTokens = frameRenderTokens;
    console.info(`[app] frame_render_tokens loaded (${Object.keys(frameRenderTokens.frames || {}).length} frame(s))`);
  } catch (e) {
    console.warn("[app] frame_render_tokens load failed:", e);
  }
}

// Phase 7.4: load canonical frame_tokens; fallback to frameRenderTokens
async function loadFrameTokens() {
  try {
    const resp = await fetch("/runtime/out_phase7/frame_tokens.runtime.json");
    if (!resp.ok) {
      console.warn(`[app] frame_tokens not available (HTTP ${resp.status}); falling back to frame_render_tokens.`);
      frameTokens = frameRenderTokens;
      return;
    }
    const data = await resp.json();
    // New schema: frames is array of {frame_id, text, tokens:[]}
    // Convert to dict keyed by frame_id for O(1) lookup
    if (Array.isArray(data.frames)) {
      frameTokens = { frames: {} };
      for (const f of data.frames) {
        frameTokens.frames[f.frame_id] = f.tokens;
      }
    } else {
      frameTokens = data;
    }
    window._frameTokens = frameTokens;
    console.info(`[app] frame_tokens loaded (${Object.keys(frameTokens.frames || {}).length} frame(s))`);
  } catch (e) {
    console.warn("[app] frame_tokens load failed:", e);
    frameTokens = frameRenderTokens;
  }
}

// ── §2.4 frame_options loader ─────────────────────────────────────────────────

// ── Phase 7.4: ui_mode state (READ / RESPOND; REPAIR removed as redundant with Hint) ─
let _uiMode = "READ";

function setUiMode(mode) {
  const effective = (mode === "RESPOND") ? "RESPOND" : "READ";
  _uiMode = effective;
  const main = document.querySelector("main");
  if (main) {
    main.classList.remove("ui-mode-read", "ui-mode-respond");
    main.classList.add(`ui-mode-${effective.toLowerCase()}`);
  }
  // Mic / Speak: always microphone icon for consistency.
  const tryBtn = document.getElementById("tryRespondingBtn");
  if (tryBtn) {
    tryBtn.classList.add("mic-only");
    tryBtn.textContent = "\uD83C\uDFA4";
    tryBtn.title = "Speak your answer";
    tryBtn.setAttribute("aria-label", "Speak your answer");
  }
}

// ── Phase 7.4: Micro-gloss singleton ────────────────────────────────────────
let _microGlossActiveTokenEl = null;

function _closeMicroGloss() {
  const mg = document.getElementById("microGloss");
  if (mg) mg.style.display = "none";
  const openBtn = document.getElementById("microGlossOpenCard");
  if (openBtn) openBtn.style.display = "";
  _microGlossActiveTokenEl = null;
}

function _openMicroGloss(tokenEl, wordId, surfaceText) {
  const mg          = document.getElementById("microGloss");
  const headwordEl  = document.getElementById("microGlossHeadword");
  const bodyEl      = document.getElementById("microGlossBody");
  const openCardBtn = document.getElementById("microGlossOpenCard");
  if (!mg || !headwordEl || !bodyEl || !openCardBtn) return;
  headwordEl.textContent = surfaceText;
  const rc = window._resolvedCard;
  if (rc && rc.card_id && cardsIndex?.by_word_id?.[wordId] === rc.card_id) {
    const pinyin  = rc.content?.headword?.pinyin || "";
    const meaning = rc.content?.meaning || "";
    bodyEl.textContent = [pinyin, meaning].filter(Boolean).join(" — ");
  } else {
    bodyEl.textContent = "";
  }
  const sentEl   = document.getElementById("frameSentence");
  const rect     = tokenEl.getBoundingClientRect();
  const sentRect = sentEl ? sentEl.getBoundingClientRect() : { left: 0, top: 0 };
  mg.style.position = "absolute";
  mg.style.left     = `${rect.left - sentRect.left}px`;
  mg.style.top      = `${rect.bottom - sentRect.top + 4}px`;
  mg.style.display  = "";
  openCardBtn.onclick = () => { _closeMicroGloss(); _openCardForWordId(wordId); };
  _microGlossActiveTokenEl = tokenEl;
}

async function _openCardForWordId(wordId) {
  if (!wordId) return;
  const cardId = cardsIndex?.by_word_id?.[wordId];
  if (!cardId) { console.warn(`[app] _openCardForWordId: no card_id for word_id "${wordId}"`); return; }
  const frameId  = document.getElementById("frameSelect")?.value || null;
  const sel      = document.getElementById("frameSelect");
  const engineId = sel?.options[sel?.selectedIndex]?.dataset?.engineId || null;
  emitUITrace({ type: "OPEN_CARD", timestamp: new Date().toISOString(),
    payload: { engine_id: engineId, frame_id: frameId, card_id: cardId, reason: "token_click" } });
  dispatch({ type: "OPEN_CARD", payload: { card_id: cardId } });
  await resolveCard(cardId, "tools/cards/out/cards_by_id.json");
  // NOTE: does NOT advance turn, reset hints, or change ui_mode
}

let frameOptionsRuntime = {};
function rebuildUserTranslationIndex() {
  userTranslationIndex = {
    [_normalizeTranscriptText("你呢？")]: "And you?",
    [_normalizeTranscriptText("为什么？")]: "Why?",
  };
  const byFrame = frameOptionsRuntime?.frames || {};
  Object.values(byFrame).forEach((f) => {
    (f?.options || []).forEach((opt) => {
      _upsertUserTranslation(opt?.hanzi || "", opt?.text_en || opt?.meaning || "");
    });
  });
}
async function loadFrameOptions() {
  try {
    const resp = await fetch("/runtime/out_phase7/frame_options.runtime.json");
    if (!resp.ok) { console.warn(`[app] frame_options not available (HTTP ${resp.status})`); return; }
    frameOptionsRuntime = await resp.json();
    rebuildUserTranslationIndex();
    window._frameOptionsRuntime = frameOptionsRuntime;
    console.info(`[app] frame_options loaded (${Object.keys(frameOptionsRuntime.frames || {}).length} frame(s))`);
  } catch (e) {
    console.warn("[app] frame_options load failed:", e);
  }
}

// ── §2.4 word_etymology loader — Phase 6 ───────────────────────────────────
let wordEtymologyIndex = {};
async function loadWordEtymology() {
  try {
    const resp = await fetch("/runtime/out_phase7/word_etymology.runtime.json");
    if (!resp.ok) { console.warn(`[app] word_etymology not available (HTTP ${resp.status})`); return; }
    const data = await resp.json();
    wordEtymologyIndex = data.words || {};
    // Build hanzi → word_id reverse index
    Object.entries(wordEtymologyIndex).forEach(([wid, entry]) => {
      if (entry.hanzi) _hanziToWordId[entry.hanzi.trim()] = wid;
    });
    window._wordEtymologyIndex = wordEtymologyIndex;
    window._hanziToWordId = _hanziToWordId;
    console.info(`[app] word_etymology loaded (${Object.keys(wordEtymologyIndex).length} words)`);
  } catch (e) {
    console.warn("[app] word_etymology load failed:", e);
  }
}

// ── §2.4 + §3.3 Hint cascade — Phase 6 ────────────────────────────────────
let hint_cascade_state = { level: 0, turn_uid: null };
let lastClickedWordId = null;
window.lastClickedWordId = null;
let _hanziToWordId = {};  // Phase 6 — reverse lookup hanzi → word_id

/** Word-level hint content: resolved card > index object > option from _tapOptions or by __opt_ index (runtime index is word_id→string). */
function getWordHintData(wordId) {
  if (typeof wordId === "string" && wordId.startsWith("__opt_")) {
    const idx = parseInt(wordId.slice(6), 10);
    const opt = Array.isArray(window._tapOptions) && Number.isInteger(idx) ? window._tapOptions[idx] : null;
    return opt ? { pinyin: opt.pinyin || "", meaning: opt.meaning || "" } : { pinyin: "", meaning: "" };
  }
  const resolvedContent = window._resolvedCard?.content;
  if (window._resolvedCardId === wordId && resolvedContent)
    return { pinyin: resolvedContent.headword?.pinyin || "", meaning: resolvedContent.meaning || "" };
  const fromIndex = window.cardsIndex?.by_word_id?.[wordId];
  if (fromIndex && typeof fromIndex === "object" && (fromIndex.pinyin != null || fromIndex.meaning != null))
    return { pinyin: fromIndex.pinyin || "", meaning: fromIndex.meaning || "" };
  const opt = window._tapOptions?.find(o => o.card_id === wordId);
  return opt ? { pinyin: opt.pinyin || "", meaning: opt.meaning || "" } : { pinyin: "", meaning: "" };
}

/** Whether a hint level has content (shared by getNextHintLevel and renderHintAffordance). */
function hintLevelHasContent(lvl, sentenceMode, sentenceHint, activeWordId) {
  if (lvl === 0) return false; // skip 0 so we don't land on "nothing" after Hide
  if (lvl === 3) return true;  // hide is valid stop
  if (sentenceMode) {
    if (lvl === 1) return !!(sentenceHint.pinyin && String(sentenceHint.pinyin).trim());
    if (lvl === 2) return !!(sentenceHint.text_en && String(sentenceHint.text_en).trim());
    if (lvl === 3) return !!(sentenceHint.etymology && String(sentenceHint.etymology).trim());
    return true;
  }
  const goldWordId = window._tapOptions?.find(o => o.is_gold)?.card_id;
  const wordId = activeWordId || goldWordId;
  const cardData = getWordHintData(wordId);
  if (lvl === 1) return !!(cardData.pinyin && String(cardData.pinyin).trim());
  if (lvl === 2) return !!(cardData.meaning && String(cardData.meaning).trim());
  if (lvl === 3) {
    const entry = wordEtymologyIndex[wordId];
    return !!(entry?.characters && entry.characters.length > 0);
  }
  return true;
}

/** Advance to next hint level that has content, so empty levels auto-rotate. */
function getNextHintLevel(currentLevel) {
  const sentenceHint = window._sentenceHint || { pinyin: "", text_en: "" };
  const activeWordId = window.lastClickedWordId || null;
  const sentenceMode = !activeWordId;
  const levelHasContent = (lvl) => hintLevelHasContent(lvl, sentenceMode, sentenceHint, activeWordId);
  let next = (currentLevel + 1) % 4;
  for (let i = 0; i < 4; i++) {
    if (levelHasContent(next)) return next;
    next = (next + 1) % 4;
  }
  return next;
}

/** Normalize level to first that has content (or 0); so we never sit on an empty level. */
function normalizeHintLevel(level, sentenceMode, sentenceHint, activeWordId) {
  const levelHasContent = (lvl) => hintLevelHasContent(lvl, sentenceMode, sentenceHint, activeWordId);
  if (levelHasContent(level)) return level;
  if (level === 0) return 0;
  for (let i = 0; i < 4; i++) {
    const next = (level + i) % 4;
    if (next === 0) return 0;
    if (levelHasContent(next)) return next;
  }
  return 0;
}

/** Single place for Hint/? button label: only show next-step label when that step has data. */
function getHintButtonLabel(level, levelHasContent) {
  if (level === 0) return levelHasContent(1) ? "Hint \u2192" : "";
  if (level === 1) return levelHasContent(2) ? "Meaning \u2192" : "Hide hints \u2192";
  if (level === 2) return levelHasContent(3) ? "Etymology \u2192" : "Hide hints \u2192";
  return "Hide hints \u2192";
}

/**
 * @param {object} hintAffordance
 * @param {string} turnUid
 * @param {string} inputMode
 * @param {HTMLElement|null} [optionPanelEl] When provided, hints are rendered inside this panel (for option ? click).
 */
function renderHintAffordance(hintAffordance, turnUid, inputMode, optionPanelEl) {
  const hintBtn     = document.getElementById("hintBtn");
  const hintPinyin  = document.getElementById("hintPinyin");
  const hintMeaning = document.getElementById("hintMeaning");
  const hintEtymEl  = document.getElementById("hintEtymology");

  if (!hintAffordance?.visible) {
    if (hintBtn) hintBtn.style.display = "none";
    return;
  }

  const activeWordId = window.lastClickedWordId || null;
  const isOptionContext = (optionPanelEl && optionPanelEl.matches?.(".option-panel")) || (activeWordId && String(activeWordId).startsWith("__opt_"));
  const optionIndex = isOptionContext ? (optionPanelEl?.getAttribute?.("data-option-index") != null ? parseInt(optionPanelEl.getAttribute("data-option-index"), 10) : parseInt(String(activeWordId || "").slice(6), 10)) : -1;

  // Option ? clicked: render hints ONLY inside that response panel; never show in active conversation area
  if (isOptionContext && (optionPanelEl || optionIndex >= 0)) {
    if (hintPinyin) { hintPinyin.textContent = ""; hintPinyin.style.display = "none"; }
    if (hintMeaning) { hintMeaning.textContent = ""; hintMeaning.style.display = "none"; }
    if (hintEtymEl) { hintEtymEl.innerHTML = ""; hintEtymEl.style.display = "none"; }
    const sentenceHint = window._sentenceHint || { pinyin: "", text_en: "" };
    const optForHint = (window._tapOptions && optionIndex >= 0 && window._tapOptions[optionIndex]) ? window._tapOptions[optionIndex] : null;
    const cardData = (optForHint && optForHint.kind === "RECOVERY")
      ? { pinyin: optForHint.pinyin || "", meaning: optForHint.meaning || "" }
      : getWordHintData(activeWordId);
    const levelHasContent = (optForHint && optForHint.kind === "RECOVERY")
      ? (lvl) => (lvl === 1 && !!(cardData?.pinyin && String(cardData.pinyin).trim())) || (lvl === 2 && !!(cardData?.meaning && String(cardData.meaning).trim()))
      : (lvl) => hintLevelHasContent(lvl, false, sentenceHint, activeWordId);
    if (hint_cascade_state.turn_uid !== turnUid) {
      hint_cascade_state = { level: 0, turn_uid: turnUid };
    }
    let level = normalizeHintLevel(hint_cascade_state.level, false, sentenceHint, activeWordId);
    // Recovery options: normalize uses word lookup and gets no content, so level stays 0; force level 1 when we have pinyin
    if (optForHint?.kind === "RECOVERY" && level === 0 && (cardData?.pinyin || cardData?.meaning)) {
      level = 1;
      hint_cascade_state.level = 1;
    }
    hint_cascade_state.level = level;
    const container = document.getElementById("optionsContainer");
    container?.querySelectorAll(".option-hint-block").forEach((blk) => {
      blk.style.display = "none";
      const py = blk.querySelector(".option-hint-pinyin");
      const me = blk.querySelector(".option-hint-meaning");
      const et = blk.querySelector(".option-hint-etymology");
      if (py) { py.textContent = ""; py.style.display = "none"; }
      if (me) { me.textContent = ""; me.style.display = "none"; }
      if (et) { et.innerHTML = ""; et.style.display = "none"; }
    });
    const optionPanel = optionPanelEl || container?.querySelector(`.option-panel[data-option-index="${optionIndex}"]`);
    const optionHintBlock = optionPanel?.querySelector(".option-hint-block");
    if (optionHintBlock) {
      const optHintPinyin = optionHintBlock.querySelector(".option-hint-pinyin");
      const optHintMeaning = optionHintBlock.querySelector(".option-hint-meaning");
      const optHintEtymology = optionHintBlock.querySelector(".option-hint-etymology");
      if (level >= 1 && cardData?.pinyin) {
        if (optHintPinyin) { optHintPinyin.textContent = cardData.pinyin; optHintPinyin.style.display = "block"; }
      } else if (optHintPinyin) optHintPinyin.style.display = "none";
      if (level >= 2 && cardData?.meaning) {
        if (optHintMeaning) { optHintMeaning.textContent = cardData.meaning; optHintMeaning.style.display = "block"; }
      } else if (optHintMeaning) optHintMeaning.style.display = "none";
      const wordIdForEtymology = (window._tapOptions && window._tapOptions[optionIndex]) ? window._tapOptions[optionIndex].card_id : null;
      if (level >= 3 && levelHasContent(3) && wordIdForEtymology) {
        if (optHintEtymology) {
          optHintEtymology.style.display = "block";
          const html = buildEtymologyHTML(wordIdForEtymology);
          optHintEtymology.innerHTML = html || "";
        }
      } else if (optHintEtymology) optHintEtymology.style.display = "none";
      const hasContent = level >= 1 && (levelHasContent(1) || levelHasContent(2) || levelHasContent(3));
      optionHintBlock.style.setProperty("display", hasContent ? "block" : "none");
      optionHintBlock.setAttribute("aria-hidden", hasContent ? "false" : "true");
    }
    if (hintBtn) {
      const hasAny = levelHasContent(1) || levelHasContent(2) || levelHasContent(3);
      hintBtn.style.display = hasAny ? "block" : "none";
      hintBtn.textContent = "?";
      hintBtn.title = getHintButtonLabel(level, levelHasContent);
    }
    return;
  }

  if (hint_cascade_state.turn_uid !== turnUid) {
    hint_cascade_state = { level: 0, turn_uid: turnUid };
  }

  const sentenceHint = window._sentenceHint || { pinyin: "", text_en: "" };
  const sentenceMode = !activeWordId;

  let level = normalizeHintLevel(hint_cascade_state.level, sentenceMode, sentenceHint, activeWordId);
  hint_cascade_state.level = level;

  const levelHasContent = (lvl) => hintLevelHasContent(lvl, sentenceMode, sentenceHint, activeWordId);

  if (sentenceMode) {
    if (hintPinyin) {
      if (level >= 1 && sentenceHint.pinyin) {
        hintPinyin.textContent = sentenceHint.pinyin;
        hintPinyin.style.display = "block";
      } else {
        hintPinyin.style.display = "none";
      }
    }
    if (hintMeaning) {
      if (level >= 2 && sentenceHint.text_en) {
        hintMeaning.textContent = sentenceHint.text_en;
        hintMeaning.style.display = "block";
      } else {
        hintMeaning.style.display = "none";
      }
    }
    if (hintEtymEl) {
      if (level >= 3 && sentenceHint.etymology) {
        hintEtymEl.innerHTML = sentenceHint.etymology;
        hintEtymEl.style.display = "block";
      } else {
        hintEtymEl.style.display = "none";
      }
    }
    if (hintBtn) {
      const hasAny = levelHasContent(1) || levelHasContent(2) || levelHasContent(3);
      hintBtn.style.display = hasAny ? "block" : "none";
      hintBtn.textContent = "?";
      hintBtn.title = getHintButtonLabel(level, levelHasContent);
    }
  } else {
    // Word in active sentence: use global hint rows; clear option hint blocks
    const goldWordId = window._tapOptions?.find(o => o.is_gold)?.card_id;
    const wordId = activeWordId || goldWordId;
    const cardData = getWordHintData(wordId);
    const container = document.getElementById("optionsContainer");
    container?.querySelectorAll(".option-hint-block").forEach((blk) => {
      blk.style.display = "none";
      blk.querySelectorAll(".option-hint-pinyin, .option-hint-meaning, .option-hint-etymology").forEach((el) => {
        el.textContent = ""; if (el.classList.contains("option-hint-etymology")) el.innerHTML = ""; el.style.display = "none";
      });
    });
    if (hintPinyin) {
      if (level >= 1 && cardData?.pinyin) {
        hintPinyin.textContent = cardData.pinyin;
        hintPinyin.style.display = "block";
      } else {
        hintPinyin.style.display = "none";
      }
    }
    if (hintMeaning) {
      if (level >= 2 && cardData?.meaning) {
        hintMeaning.textContent = cardData.meaning;
        hintMeaning.style.display = "block";
      } else {
        hintMeaning.style.display = "none";
      }
    }
    if (hintEtymEl) {
      if (level >= 3 && levelHasContent(3)) {
        hintEtymEl.style.display = "block";
        renderEtymologyForWord(wordId);
      } else {
        hintEtymEl.style.display = "none";
      }
    }
    if (hintBtn) {
      const hasAny = levelHasContent(1) || levelHasContent(2) || levelHasContent(3);
      hintBtn.style.display = hasAny ? "block" : "none";
      hintBtn.textContent = "?";
      hintBtn.title = getHintButtonLabel(level, levelHasContent);
    }
  }
}
// ── end Phase 6 ────────────────────────────────────────────────────────────

// ── Phase 8: Conversation transcript panel (UI only; uses conversationTranscript) ──
function renderTranscript() {
  const container = document.getElementById("transcriptContent");
  if (!container) return;
  container.innerHTML = "";
  (conversationTranscript || []).forEach((entry, idx) => {
    const lineId = entry.id || String(idx);
    const text = entry.text_zh || entry.text || "";
    const textEn = entry.text_en || "";
    const textPy = entry.pinyin || "";
    const role = entry.role === "partner" ? "partner" : "user";
    const uiState = transcriptLineUiState[lineId] || { showEn: false, showPy: false };

    const line = document.createElement("div");
    line.className = "transcript-line " + role;
    line.setAttribute("data-line-id", lineId);
    if (transcriptReplayState.active && transcriptReplayState.activeLineId === lineId) {
      line.classList.add("active-replay");
    }

    const main = document.createElement("div");
    main.className = "transcript-main";
    const marker = document.createElement("span");
    marker.className = "turn-marker";
    marker.textContent = role === "partner" ? "APP:" : "You:";
    main.appendChild(marker);
    if (transcriptSegmentMode) {
      const sel = document.createElement("input");
      sel.type = "checkbox";
      sel.className = "transcript-select";
      sel.checked = transcriptSelectedLineIds.includes(lineId);
      sel.setAttribute("aria-label", "Select transcript line");
      sel.addEventListener("change", () => {
        if (sel.checked) {
          if (!transcriptSelectedLineIds.includes(lineId)) transcriptSelectedLineIds.push(lineId);
        } else {
          transcriptSelectedLineIds = transcriptSelectedLineIds.filter((id) => id !== lineId);
        }
        updateReplaySelectedButton();
      });
      main.appendChild(sel);
    }
    const contentSpan = document.createElement("span");
    contentSpan.className = /[\u4e00-\u9fff\u3400-\u4dbf]/.test(text) ? "transcript-text transcript-zh" : "transcript-text transcript-en";
    contentSpan.textContent = " " + text;
    main.appendChild(contentSpan);
    line.appendChild(main);

    const actions = document.createElement("div");
    actions.className = "transcript-actions";
    const replayBtn = document.createElement("button");
    replayBtn.type = "button";
    replayBtn.className = "transcript-action-btn";
    replayBtn.textContent = "🔊";
    replayBtn.title = "Replay line";
    replayBtn.setAttribute("aria-label", "Replay this line");
    replayBtn.disabled = transcriptReplayState.active && transcriptReplayState.activeLineId === lineId;
    replayBtn.addEventListener("click", () => replayTranscriptLine(lineId));
    actions.appendChild(replayBtn);

    const enBtn = document.createElement("button");
    enBtn.type = "button";
    enBtn.className = "transcript-action-btn";
    enBtn.textContent = "EN";
    enBtn.title = "Toggle translation";
    enBtn.setAttribute("aria-label", "Toggle English translation");
    enBtn.addEventListener("click", () => toggleLineEnglish(lineId));
    actions.appendChild(enBtn);
    if (role === "partner" && textPy) {
      const pyBtn = document.createElement("button");
      pyBtn.type = "button";
      pyBtn.className = "transcript-action-btn";
      pyBtn.textContent = "PY";
      pyBtn.title = "Toggle pinyin";
      pyBtn.setAttribute("aria-label", "Toggle pinyin");
      pyBtn.addEventListener("click", () => {
        const st = transcriptLineUiState[lineId] || { showEn: false, showPy: false };
        transcriptLineUiState[lineId] = { ...st, showPy: !st.showPy };
        renderTranscript();
      });
      actions.appendChild(pyBtn);
    }
    line.appendChild(actions);
    container.appendChild(line);

    const shouldShowEn = transcriptDisplayMode === "zh_en" || uiState.showEn;
    const shouldShowPy = !!uiState.showPy;
    if (shouldShowEn || shouldShowPy) {
      const detail = document.createElement("div");
      detail.className = "transcript-line-detail";
      const chunks = [];
      if (shouldShowPy) chunks.push(textPy ? textPy : "Pinyin not available");
      if (shouldShowEn) chunks.push(textEn ? textEn : "No translation available yet");
      detail.textContent = chunks.join("  |  ");
      container.appendChild(detail);
    }
  });
  const panel = document.getElementById("transcriptPanel");
  if (panel) panel.scrollTop = panel.scrollHeight;
}

function resolveUserLineTranslation(entry) {
  if (!entry || entry.role !== "user") return "";
  if ((entry.text_en || "").trim()) return entry.text_en.trim();
  const key = _normalizeTranscriptText(entry.text_zh || entry.text || "");
  return userTranslationIndex[key] || "";
}

function toggleLineEnglish(lineId) {
  const entry = (conversationTranscript || []).find((e, idx) => (e.id || String(idx)) === lineId);
  const st = transcriptLineUiState[lineId] || { showEn: false, showPy: false };
  if (!entry) return;
  if (entry.role === "user" && !(entry.text_en || "").trim()) {
    const resolved = resolveUserLineTranslation(entry);
    if (resolved) {
      entry.text_en = resolved;
    } else if (!st.showEn) {
      entry.text_en = "No translation available yet";
    }
  }
  transcriptLineUiState[lineId] = { ...st, showEn: !st.showEn };
  renderTranscript();
}


function updateReplaySelectedButton() {
  const btn = document.getElementById("replaySelectedBtn");
  if (!btn) return;
  btn.disabled = !transcriptSegmentMode || transcriptSelectedLineIds.length < 2;
}

function setReplayStatus(text) {
  const statusEl = document.getElementById("replayStatus");
  const stopBtn = document.getElementById("stopReplayBtn");
  if (!statusEl || !stopBtn) return;
  if (text) {
    statusEl.style.display = "";
    statusEl.textContent = text;
    stopBtn.style.display = "";
  } else {
    statusEl.style.display = "none";
    statusEl.textContent = "";
    stopBtn.style.display = "none";
  }
}

function stopTranscriptReplay() {
  transcriptReplayToken += 1;
  transcriptReplayState = { active: false, activeLineId: null, queue: [] };
  try {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  } catch (_) {}
  setReplayStatus("");
  renderTranscript();
}

function replayTranscriptLine(lineId) {
  const entry = (conversationTranscript || []).find((e, idx) => (e.id || String(idx)) === lineId);
  if (!entry) return;
  const text = (entry.text_zh || entry.text || "").trim();
  if (!text) return;
  replayTranscriptQueue([lineId]);
}

function speakTranscriptLine(entry, token) {
  const text = (entry?.text_zh || entry?.text || "").trim();
  if (!text) return Promise.resolve();
  return new Promise((resolve) => {
    if (token !== transcriptReplayToken) return resolve();
    ttsSpeak({
      text,
      lang: "zh-CN",
      rate: transcriptReplaySpeed,
      onEvent: (ev) => {
        if (token !== transcriptReplayToken) return resolve();
        if (ev?.payload?.completed || ev?.type === "AUDIO_ERROR") resolve();
      },
    });
  });
}

function waitMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function replayTranscriptQueue(lineIds) {
  const ids = (lineIds || []).filter(Boolean);
  if (!ids.length) return;
  stopTranscriptReplay();
  const token = transcriptReplayToken;
  transcriptReplayState = { active: true, activeLineId: null, queue: ids.slice() };
  for (let i = 0; i < ids.length; i += 1) {
    if (token !== transcriptReplayToken) return;
    const lineId = ids[i];
    const entry = (conversationTranscript || []).find((e, idx) => (e.id || String(idx)) === lineId);
    if (!entry) continue;
    transcriptReplayState.activeLineId = lineId;
    setReplayStatus(ids.length > 1 ? `Replaying selected ${i + 1}/${ids.length}...` : "Replaying line...");
    renderTranscript();
    await speakTranscriptLine(entry, token);
    if (i < ids.length - 1) await waitMs(320);
  }
  if (token !== transcriptReplayToken) return;
  transcriptReplayState = { active: false, activeLineId: null, queue: [] };
  setReplayStatus("");
  renderTranscript();
}

function replaySelectedTranscriptLines() {
  if (!transcriptSegmentMode || transcriptSelectedLineIds.length < 2) return;
  // Keep transcript order
  const orderedIds = (conversationTranscript || [])
    .map((e, idx) => e.id || String(idx))
    .filter((id) => transcriptSelectedLineIds.includes(id));
  replayTranscriptQueue(orderedIds);
}

async function loadCardsIndex() {
  try {
    const resp = await fetch("/runtime/out_phase7/cards_index.runtime.json");
    if (!resp.ok) {
      console.warn(`[app] cards_index not available (HTTP ${resp.status})`);
      return;
    }
    cardsIndex = await resp.json();
    window.cardsIndex = cardsIndex;
    window.cardsIndex = cardsIndex; // <-- ADD THIS LINE
    console.info(`[app] cards_index loaded`);
  } catch (e) {
    console.warn("[app] cards_index load failed:", e);
  }
}

// ── Recovery vocabulary (emergency phrases); used by speak-first recovery flow ─
/** @type {{ phrases: Array<{id:string,hanzi:string,pinyin:string,text_en:string,use?:string}>, default_for_not_understood?: string } | null} */
let recoveryPhrasesRuntime = null;
async function loadRecoveryPhrases() {
  try {
    const resp = await fetch("/runtime/out_phase7/recovery_phrases.runtime.json");
    if (!resp.ok) {
      console.warn(`[app] recovery_phrases not available (HTTP ${resp.status}); using fallback.`);
      return;
    }
    recoveryPhrasesRuntime = await resp.json();
    window._recoveryPhrases = recoveryPhrasesRuntime;
    const n = (recoveryPhrasesRuntime.phrases || []).length;
    console.info(`[app] recovery_phrases loaded (${n} phrase(s))`);
  } catch (e) {
    console.warn("[app] recovery_phrases load failed:", e);
  }
}

/**
 * Rotation pool for "not understood": repeat/slower phrases so we don't always say "什么？".
 * After 2+ consecutive not-understoods we return a next_turn phrase to move the conversation on.
 */
const NOT_UNDERSTOOD_ROTATION_ACTION = new Set(["repeat", "slower"]);
const NOT_UNDERSTOOD_MOVE_ON_ACTION = "next_turn";
const NOT_UNDERSTOOD_MOVE_ON_AFTER = 3;

/** Returns the phrase to show when user was not understood. Rotates among repeat/slower; after a few times, moves on (next_turn). */
function getRecoveryPhraseForNotUnderstood(avoidPhraseId = null) {
  const data = recoveryPhrasesRuntime || window._recoveryPhrases;
  if (!data || !Array.isArray(data.phrases) || data.phrases.length === 0) {
    return { id: "fallback", hanzi: "什么？再说一次。", pinyin: "Shénme? Zài shuō yí cì.", text_en: "What? Say it again.", etymology: "" };
  }
  const consecutive = (window._consecutiveNotUnderstood || 0) + 1;
  window._consecutiveNotUnderstood = consecutive;

  if (consecutive >= NOT_UNDERSTOOD_MOVE_ON_AFTER) {
    const moveOnPool = (data.phrases || []).filter((p) => (p.recovery_action || "") === NOT_UNDERSTOOD_MOVE_ON_ACTION);
    if (moveOnPool.length > 0) {
      const chosen = moveOnPool[0];
      return { id: chosen.id, hanzi: chosen.hanzi, pinyin: chosen.pinyin || "", text_en: chosen.text_en || "", etymology: chosen.etymology || "", recovery_action: NOT_UNDERSTOOD_MOVE_ON_ACTION };
    }
  }

  const rotationPool = (data.phrases || []).filter((p) => NOT_UNDERSTOOD_ROTATION_ACTION.has(p.recovery_action || ""));
  const pool = rotationPool.length > 0 ? rotationPool : data.phrases;
  let chosen;
  if (avoidPhraseId && pool.length > 1) {
    const i = pool.findIndex((p) => p.id === avoidPhraseId);
    const nextIdx = i >= 0 ? (i + 1) % pool.length : 0;
    chosen = pool[nextIdx];
  } else {
    const defaultId = data.default_for_not_understood;
    const found = defaultId ? pool.find((p) => p.id === defaultId) : null;
    chosen = found || pool[0] || data.phrases[0];
  }
  return { id: chosen.id, hanzi: chosen.hanzi, pinyin: chosen.pinyin || "", text_en: chosen.text_en || "", etymology: chosen.etymology || "", recovery_action: chosen.recovery_action || "repeat" };
}

/** Normalize for match: trim, collapse spaces, remove common punctuation. */
function normalizeForMatch(s) {
  if (typeof s !== "string") return "";
  return s.trim().replace(/\s+/g, "").replace(/[。？！，、；：""''\s]/g, "");
}

/**
 * Match recognized transcript to an option (by hanzi or pinyin). Returns the option or null.
 * Phase 9: The speech engine records Chinese accurately; recovery is often triggered when the
 * answer was reasonable because this matching is strict/simple. Phase 9 should improve
 * "understood" vs "not understood" decision logic (e.g. fuzzy match, confidence, or engine).
 */
function matchTranscriptToOption(transcript, options) {
  if (!transcript || !Array.isArray(options) || options.length === 0) return null;
  const n = normalizeForMatch(transcript);
  if (!n) return null;
  for (const opt of options) {
    const hanzi = (opt.hanzi || "").trim();
    if (!hanzi) continue;
    const optNorm = normalizeForMatch(hanzi);
    if (optNorm && (n === optNorm || n.includes(optNorm) || optNorm.includes(n))) return opt;
    const pinyin = (opt.pinyin || "").trim();
    if (pinyin) {
      const pyNorm = normalizeForMatch(pinyin);
      if (pyNorm && (n === pyNorm || n.includes(pyNorm) || pyNorm.includes(n))) return opt;
    }
  }
  return null;
}

function isOpenEndedFrame(frameId) {
  const fid = (frameId || "").trim();
  return new Set([
    "f_ask_you_name",
    "p2_id_2",
    "p2_id_4",
    "p2_id_5",
    "f_ask_name_meaning",
    "f_from_where",
    "frame.location.live_question",
    "f_what_work",
    "f_food_what_good",
    "f_travel_where",
    "f_want_go_where",
  ]).has(fid);
}

function isLikelyUnderstandableFreeAnswer(text) {
  const s = (text || "").trim();
  if (!s) return false;
  const zhMatches = s.match(/[\u4e00-\u9fff]/g) || [];
  const zhCount = zhMatches.length;
  const latinCount = (s.match(/[A-Za-z]/g) || []).length;
  // Too short in Chinese usually means we likely misheard.
  if (zhCount > 0 && zhCount < 2) return false;
  // Heavy Latin in a Chinese answer often indicates ASR noise for this app mode.
  if (latinCount > zhCount + 2) return false;
  // Repeated single word noise (e.g., 牛肉牛肉牛肉) should trigger repair.
  const norm = s.replace(/[，。！？、\s]/g, "");
  if (norm.length >= 4) {
    const half = Math.floor(norm.length / 2);
    if (half > 0 && norm.slice(0, half) === norm.slice(half)) return false;
  }
  return s.length >= 2;
}

function shouldAcceptUnmatchedFreeAnswer(transcript, options, frameId) {
  const opts = Array.isArray(options) ? options : [];
  if (opts.length === 0) return true;
  if (isOpenEndedFrame(frameId)) return isLikelyUnderstandableFreeAnswer(transcript);
  // If this turn is mostly closed options, be stricter and prefer repair on unmatched speech.
  const hasStructuredSlots = opts.some((o) => (o?.kind || "").toUpperCase() === "FRAME_WITH_SLOTS");
  if (hasStructuredSlots) return isLikelyUnderstandableFreeAnswer(transcript);
  return false;
}

function classifyUnmatchedFreeAnswerDecision(transcript, options, frameId) {
  const opts = Array.isArray(options) ? options : [];
  const hasStructuredSlots = opts.some((o) => (o?.kind || "").toUpperCase() === "FRAME_WITH_SLOTS");
  const openEnded = isOpenEndedFrame(frameId);
  const understandable = isLikelyUnderstandableFreeAnswer(transcript);
  if (opts.length === 0) return { accept: true, reason: "no_options" };
  if (openEnded && understandable) return { accept: true, reason: "open_ended_understandable" };
  if (hasStructuredSlots && understandable) return { accept: true, reason: "slot_frame_understandable" };
  if (openEnded && !understandable) return { accept: false, reason: "open_ended_low_confidence" };
  if (hasStructuredSlots && !understandable) return { accept: false, reason: "slot_frame_low_confidence" };
  return { accept: false, reason: "closed_options_unmatched" };
}

/**
 * Listen for speech (zh-CN) and try to match to current options. Resolves with { transcript, matchedOption }.
 * Uses Web Speech API; if unavailable or error, resolves with transcript "" and matchedOption null.
 */
function listenForResponse(options, timeoutMs) {
  return new Promise((resolve) => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      emitUITrace({ type: "SPEECH_NOT_AVAILABLE", timestamp: new Date().toISOString(), payload: { message: "SpeechRecognition not supported" } });
      resolve({ transcript: "", matchedOption: null });
      return;
    }
    const rec = new SpeechRecognition();
    rec.continuous = false;
    rec.lang = "zh-CN";
    rec.interimResults = true;
    let finalTranscript = "";
    let resolved = false;
    function done(transcript, matchedOption) {
      if (resolved) return;
      resolved = true;
      try { rec.abort(); } catch (_) {}
      clearTimeout(tid);
      resolve({ transcript: transcript || finalTranscript || "", matchedOption: matchedOption ?? null });
    }
    const tid = setTimeout(() => {
      const matched = matchTranscriptToOption(finalTranscript, options || []);
      done(finalTranscript, matched);
    }, timeoutMs);
    rec.onresult = (e) => {
      const last = e.results[e.results.length - 1];
      const item = last.isFinal ? last[0] : (last.length ? last[0] : null);
      if (item) {
        const t = (item.transcript || "").trim();
        if (last.isFinal) {
          finalTranscript = t;
          const matched = matchTranscriptToOption(t, options || []);
          done(t, matched);
        } else {
          finalTranscript = t;
        }
      }
    };
    rec.onend = () => {
      if (resolved) return;
      const matched = matchTranscriptToOption(finalTranscript, options || []);
      done(finalTranscript, matched);
    };
    rec.onerror = (e) => {
      if (e.error === "no-speech" && finalTranscript) {
        const matched = matchTranscriptToOption(finalTranscript, options || []);
        done(finalTranscript, matched);
      } else {
        done(finalTranscript || "", null);
      }
    };
    try {
      rec.start();
      emitUITrace({ type: "SPEECH_LISTEN_START", timestamp: new Date().toISOString(), payload: { lang: "zh-CN" } });
    } catch (err) {
      done("", null);
    }
  });
}

// Segments for "你呢？" so each word opens the card panel when clicked (2nd+ turns)
const ACTIVE_NE_SEGMENTS = [{ t: "你", word_id: "w_ni" }, { t: "呢", word_id: "w_ne" }, { t: "？" }];

/**
 * Set the active conversation area to show a partner statement (e.g. "你呢？" or recovery phrase).
 * When turnUidForHint is provided, renders clickable tokens. Optional segments can supply word_id
 * so clicking a word opens the card panel and shows pinyin/meaning/etymology for that word.
 * @param {string} text - Fallback when segments not provided.
 * @param {string} [turnUidForHint] - If set, tokens are clickable (hint and/or card).
 * @param {Array<{t:string, word_id?:string}>} [segments] - Optional; if provided, each segment rendered; word_id opens card on click.
 */
function setActivePartnerStatement(text, turnUidForHint, segments) {
  const el = document.getElementById("frameSentence");
  if (!el) return;
  while (el.firstChild) el.removeChild(el.firstChild);
  _closeMicroGloss();
  const str = text || "";
  if (!str && (!segments || segments.length === 0)) return;
  if (!turnUidForHint) {
    el.textContent = str;
    return;
  }
  const turnUid = turnUidForHint;
  if (Array.isArray(segments) && segments.length > 0) {
    for (const seg of segments) {
      const span = document.createElement("span");
      span.textContent = seg.t || "";
      span.className = "tok tok-word";
      span.dataset.kind = "word";
      if (seg.word_id) span.dataset.wordId = seg.word_id;
      span.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (seg.word_id) {
          lastClickedWordId = seg.word_id;
          window.lastClickedWordId = seg.word_id;
          await _openCardForWordId(seg.word_id);
        } else {
          lastClickedWordId = null;
          window.lastClickedWordId = null;
        }
        hint_cascade_state = { level: 1, turn_uid: turnUid };
        renderHintAffordance({ ...(window._currentHintAffordance || {}), visible: true }, turnUid, "tap");
      });
      el.appendChild(span);
    }
  } else {
    for (const char of str) {
      const span = document.createElement("span");
      span.textContent = char;
      span.className = "tok tok-word";
      span.dataset.kind = "word";
      span.addEventListener("click", (e) => {
        e.stopPropagation();
        lastClickedWordId = null;
        window.lastClickedWordId = null;
        hint_cascade_state = { level: 1, turn_uid: turnUid };
        renderHintAffordance({ ...(window._currentHintAffordance || {}), visible: true }, turnUid, "tap");
      });
      el.appendChild(span);
    }
  }
  el.onclick = (e) => {
    if (!e.target.classList.contains("tok")) _closeMicroGloss();
  };
}

/**
 * Render the frame sentence into #frameSentence using Phase 7.4 token schema.
 * Falls back to frame_render_tokens, then plain text.
 * Two-stage click: micro-gloss (stage 1) → card panel (stage 2).
 * @param {{ id: string, text: string }} frame
 */
function renderFrameSentence(frame) {
  const el = document.getElementById("frameSentence");
  if (!el) return;

  while (el.firstChild) el.removeChild(el.firstChild);
  _closeMicroGloss();

  // Preferred: canonical frame_tokens (Phase 7.4 schema: {kind, t, word_id?, slot_name?})
  // Fallback:  frame_render_tokens (Phase 6 schema: {t, id?, s})
  const tokenSource = frameTokens || frameRenderTokens;
  const rawTokens   = tokenSource?.frames?.[frame?.id];

  if (!rawTokens || !Array.isArray(rawTokens)) {
    el.textContent = (frame && frame.text) || "";
    return;
  }

  // Detect schema version: Phase 7.4 tokens have `kind`; Phase 6 tokens have `t` type field
  const isNewSchema = rawTokens.length > 0 && ("kind" in rawTokens[0]);

  rawTokens.forEach((tok) => {
    const span = document.createElement("span");

    if (isNewSchema) {
      // ── Phase 7.4 schema ──
      span.textContent          = tok.t;
      span.dataset.kind         = tok.kind;
      span.dataset.text         = tok.t;
      if (frame?.id)    span.dataset.frameId  = frame.id;
      if (tok.word_id)  span.dataset.wordId   = tok.word_id;
      if (tok.slot_name) span.dataset.slotName = tok.slot_name;

      if (tok.kind === "word" && tok.word_id) {
        span.className = "tok tok-word";
        span.addEventListener("click", async (e) => {
          e.stopPropagation();
          lastClickedWordId        = tok.word_id;
          window.lastClickedWordId = lastClickedWordId;
          await _openCardForWordId(tok.word_id);
          // Update hint area for this word (pinyin → meaning → etymology) so user can explore
          const turnUid = window._currentTurnUid || frame?.id || "";
          hint_cascade_state = { level: 1, turn_uid: turnUid };
          renderHintAffordance({ ...(window._currentHintAffordance || {}), visible: true }, turnUid, "tap");
        });
      } else if (tok.kind === "word") {
        // Unknown word — no word_id





        // Unknown word — no word_id
        span.className = "tok tok-word tok-word-unknown";
        span.addEventListener("click", (e) => {
          e.stopPropagation();
          const mg       = document.getElementById("microGloss");
          const hwEl     = document.getElementById("microGlossHeadword");
          const bodyEl   = document.getElementById("microGlossBody");
          const openBtn  = document.getElementById("microGlossOpenCard");
          if (!mg || !hwEl || !bodyEl || !openBtn) return;
          hwEl.textContent    = tok.t;
          bodyEl.textContent  = "Not in lexicon yet";
          openBtn.style.display = "none";
          const rect     = span.getBoundingClientRect();
          const sentRect = el.getBoundingClientRect();
          mg.style.left    = `${rect.left - sentRect.left}px`;
          mg.style.top     = `${rect.bottom - sentRect.top + 4}px`;
          mg.style.display = "";
          _microGlossActiveTokenEl = span;
        });
      } else if (tok.kind === "slot") {
        span.className = "tok tok-slot";
      } else {
        span.className = `tok tok-${tok.kind || "other"}`;
      }

    } else {
      // ── Phase 6 schema fallback (tok.t is kind, tok.s is surface) ──
      span.textContent = tok.text ?? tok.s ?? tok.t ?? "";
      if (tok.t === "word") {
        span.className    = "frame-word-token";
        span.style.cursor = "pointer";
        span.title        = tok.id || "";
        span.addEventListener("click", () => {
          lastClickedWordId        = tok.id;
          window.lastClickedWordId = lastClickedWordId;
          const turnUid = window._currentTurnUid || frame?.id || "";
          hint_cascade_state = { level: 1, turn_uid: turnUid };
          renderHintAffordance({ ...(window._currentHintAffordance || {}), visible: true }, turnUid, "tap");
          const cardId = cardsIndex?.by_word_id?.[tok.id];
          if (!cardId) {
            console.warn(`[app] renderFrameSentence: no card_id for word_id '${tok.id}'`);
            return;
          }
          emitUITrace({
            type: "OPEN_CARD", timestamp: new Date().toISOString(),
            payload: { frame_id: frame?.id, card_id: cardId, reason: "card_available" }
          });
          dispatch({ type: "OPEN_CARD", payload: { card_id: cardId } });
          resolveCard(cardId, "tools/cards/out/cards_by_id.json");
        });
      } else {
        span.className = "frame-lit-token";
      }
    }

    el.appendChild(span);
  });

  // Close micro-gloss on click outside tokens (within sentence area)
  el.onclick = (e) => {
    if (!e.target.classList.contains("tok")) _closeMicroGloss();
  };
}

// ── §2.4 Etymology (shared: hint + card panel) — Phase 6 ───────────────────
/** Returns HTML string for word etymology, or null if none. Card_id equals word_id in our data. */
function buildEtymologyHTML(wordId) {
  if (!wordId || !wordEtymologyIndex[wordId]) return null;
  const entry = wordEtymologyIndex[wordId];
  if (!entry.characters || entry.characters.length === 0) return null;
  const parts = entry.characters.map(ch => {
    let html = `<div class="etym-char"><span class="etym-hanzi">${ch.char}</span>`;
    if (ch.radical)                 html += `<span class="etym-radical">Radical: ${ch.radical}</span>`;
    if (ch.decomposition)           html += `<span class="etym-decomp">Parts: ${ch.decomposition}</span>`;
    if (ch.etymology?.origin_note)  html += `<span class="etym-origin">${ch.etymology.origin_note}</span>`;
    if (ch.mnemonic?.story)         html += `<span class="etym-mnemonic">${ch.mnemonic.story}</span>`;
    if (ch.mnemonic?.disclaimer)    html += `<span class="etym-disclaimer">${ch.mnemonic.disclaimer}</span>`;
    html += `</div>`;
    return html;
  }).join("");
  return `<div class="etym-word">${parts}</div>`;
}

function renderEtymologyForWord(wordId) {
  const el = document.getElementById("hintEtymology");
  if (!el) return;
  const html = buildEtymologyHTML(wordId);
  el.innerHTML = html || "<span class='etym-fallback'>No etymology available yet</span>";
}
// ── end Phase 6 ────────────────────────────────────────────────────────────

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

    // Etymology in card panel: "Show etymology" link, expands in place (room for future brush/radical clicks).
    const etymHTML = buildEtymologyHTML(state.activeCardId);
    if (etymHTML) {
      const etymWrap = document.createElement("div");
      etymWrap.className = "card-etymology";
      const cardId = state.activeCardId;
      const isExpanded = _cardEtymologyExpanded.has(cardId);
      const trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "card-etymology-trigger";
      trigger.textContent = isExpanded ? "Hide etymology" : "Show etymology";
      trigger.addEventListener("click", () => {
        if (_cardEtymologyExpanded.has(cardId)) _cardEtymologyExpanded.delete(cardId);
        else _cardEtymologyExpanded.add(cardId);
        render();
      });
      etymWrap.appendChild(trigger);
      if (isExpanded) {
        const etymInner = document.createElement("div");
        etymInner.className = "card-etymology-content";
        etymInner.innerHTML = etymHTML;
        etymWrap.appendChild(etymInner);
      }
      cardBody.appendChild(etymWrap);
    }

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
      window._resolvedCard = card;
      window._resolvedCardId = cardId;
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
    console.error("[app] loadPackFramesIntoDropdown error:", e);
    return;
  }
}



// ── Phase 6: render response options ───────────────────────────────────────
// ── §3.4 SystemFaultLog — idempotent session-level fault accumulator ─────────
const SystemFaultLog = {
  _faults: [],
  _keys:   new Set(),
  record(fault) {
    const key = [fault.fault_type, fault.turn_uid||"", fault.frame_id||"", fault.failure_reason||"", fault.input_mode||""].join("|");
    if (this._keys.has(key)) return;
    this._keys.add(key);
    this._faults.push(fault);
    console.warn("[app][fault]", fault.fault_type, fault.failure_reason, fault);
  },
  all()   { return [...this._faults]; },
  any()   { return this._faults.length > 0; },
  reset() { this._faults = []; this._keys = new Set(); }
};

// ── §3.4 buildDiagnosticCompleted ────────────────────────────────────────────
function buildDiagnosticCompleted(sessionMeta) {
  const faults     = SystemFaultLog.all();
  const confidence = faults.length > 0 ? "low" : "medium";
  return {
    type:          "diagnostic_completed",
    timestamp:     new Date().toISOString(),
    confidence,
    system_faults: faults,
    ...(sessionMeta || {})
  };
}

// ── §5 validateOption — Phase 6 ────────────────────────────────────────────
const ALLOWED_OPTION_KINDS = new Set(["WORD", "FRAME_WITH_SLOTS", "FILLER", "FREE_TEXT", "RECOVERY", "RECOVERY_PANEL"]);

function validateOption(option, targetItem) {
  if (!option || typeof option !== "object")
    return { valid: false, failure_reason: "malformed_option" };
  const kind = option.kind && String(option.kind).toUpperCase();
  if (kind === "RECOVERY") {
    if (!option.hanzi || typeof option.hanzi !== "string" || option.hanzi.trim() === "")
      return { valid: false, failure_reason: "unrenderable_option" };
    return { valid: true, failure_reason: null };
  }
  if (kind === "RECOVERY_PANEL") {
    if (!Array.isArray(option.recoveryPhrases) || option.recoveryPhrases.length === 0)
      return { valid: false, failure_reason: "unrenderable_option" };
    return { valid: true, failure_reason: null };
  }
  if (!option.card_id || typeof option.card_id !== "string" || option.card_id.trim() === "")
    return { valid: false, failure_reason: "malformed_option" };
  if (!option.hanzi || typeof option.hanzi !== "string" || option.hanzi.trim() === "")
    return { valid: false, failure_reason: "unrenderable_option" };
  const kindNorm = option.kind && String(option.kind).toUpperCase();
  if (!kindNorm || !ALLOWED_OPTION_KINDS.has(kindNorm))
    return { valid: false, failure_reason: "malformed_option" };
  // RECOVERY already validated above (hanzi only).
  // Do not fail WORD options when frame is slotted; only require at least one FRAME_WITH_SLOTS (checked in validateOptionsArray).
  return { valid: true, failure_reason: null };
}

function validateOptionsArray(options, frameId, targetItem) {
  const failures = [];
  if (!Array.isArray(options) || options.length < 1)
    failures.push({ failure_reason: "insufficient_options", option_count: (options||[]).length });
  // gold = one suggested response for this turn (conversation-sustaining); validation is not about "correct answer"
  const goldOptions = (options || []).filter(o => o.is_gold);
  if (goldOptions.length > 1)
    failures.push({ failure_reason: "multiple_gold", gold_count: goldOptions.length });
  (options || []).forEach((opt, idx) => {
    const r = validateOption(opt, targetItem);
    if (!r.valid) failures.push({ failure_reason: r.failure_reason, option_index: idx, card_id: opt.card_id });
  });
  if (targetItem && targetItem.is_slot) {
    if (!(options || []).some(o => o.kind === "FRAME_WITH_SLOTS"))
      failures.push({ failure_reason: "slot_option_missing" });
  }
  if (failures.length > 0) {
    emitUITrace({
      type:         "turn_option_invariant_failed",
      timestamp:    new Date().toISOString(),
      frame_id:     frameId,
      option_count: (options || []).length,
      gold_present: goldOptions.length > 0,
      failures
    });
    console.warn("[app] §3.1 turn_option_invariant_failed", failures);
  }
  return { ok: failures.length === 0, failures };
}
/** Recovery phrases in one scrollable panel (P1 first, then P2). */
const RECOVERY_PHRASES_MAX = 12;

/** Resolve recovery_action so we respond correctly to each phrase (not always "repeat"). */
const RECOVERY_ACTION_NEXT_TURN_IDS = new Set([
  "wo_bu_dong", "ting_bu_dong", "bu_haoyisi_mei_tingdong",
  "women_liao_dian_jiandan_ba", "women_keyi_liao_bie_de_ma", "bu_zhidao",
]);
const RECOVERY_ACTION_SLOWER_IDS = new Set(["man_yi_dian", "ni_keyi_shuo_man_yidian_ma"]);

function getRecoveryAction(phrase) {
  if (phrase.recovery_action === "next_turn" || phrase.recovery_action === "slower" || phrase.recovery_action === "repeat")
    return phrase.recovery_action;
  const id = (phrase.id || "").trim();
  if (RECOVERY_ACTION_NEXT_TURN_IDS.has(id)) return "next_turn";
  if (RECOVERY_ACTION_SLOWER_IDS.has(id)) return "slower";
  return "repeat";
}

function getRecoveryPanelOption() {
  const data = recoveryPhrasesRuntime || window._recoveryPhrases;
  if (!data || !Array.isArray(data.phrases) || data.phrases.length === 0) return null;
  const p1 = data.phrases.filter((p) => (p.level || "").toUpperCase() === "P1");
  const p2 = data.phrases.filter((p) => (p.level || "").toUpperCase() === "P2");
  const pool = [...p1, ...p2].slice(0, RECOVERY_PHRASES_MAX);
  if (pool.length === 0) return null;
  return {
    kind: "RECOVERY_PANEL",
    card_id: "recovery:panel",
    hanzi: "",
    is_gold: false,
    is_slot: false,
    recoveryPhrases: pool.map((p) => ({
      id: p.id,
      hanzi: p.hanzi || "",
      pinyin: p.pinyin || "",
      meaning: p.text_en || "",
      recovery_action: getRecoveryAction(p),
    })),
  };
}

function renderOptions(options, frameId) {
  // Normalize kind so validation and ? button behave consistently (default WORD when missing)
  options = (options || []).map(opt => ({
    ...opt,
    kind: (opt.kind && String(opt.kind).toUpperCase()) || "WORD",
  }));
  // Phase 9.4: append one recovery panel (scrollable list of phrases)
  const recoveryPanel = getRecoveryPanelOption();
  if (recoveryPanel) options.push(recoveryPanel);
  // §3.1 + §5 — validate before render
  const targetItem = options && options.find(o => o.is_gold) || null;
  const validation = validateOptionsArray(options, frameId, targetItem);
  if (!validation.ok) {
    console.warn("[app] renderOptions — option validation had issues (still rendering)", validation.failures);
  }
  let container = document.getElementById("optionsContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "optionsContainer";
    container.className = "options-container options-area";
    const parent = document.getElementById("optionsContainerParent");
    if (parent) parent.appendChild(container);
    else document.body.appendChild(container);
  }
  while (container.firstChild) container.removeChild(container.firstChild);
  if (!options || options.length === 0) { container.style.display = "none"; return; }
  container.style.display = "flex";
  options.forEach((opt, idx) => {
    // Phase 9.4: one scrollable recovery panel instead of multiple panels
    if (opt.kind === "RECOVERY_PANEL") {
      const panel = document.createElement("div");
      panel.className = "option-panel";
      panel.setAttribute("data-option-index", String(idx));
      panel.setAttribute("data-recovery", "true");
      panel.setAttribute("data-card-id", opt.card_id || "");
      const label = document.createElement("div");
      label.className = "recovery-panel-label";
      label.textContent = "Need help?";
      panel.appendChild(label);
      const listWrap = document.createElement("div");
      listWrap.className = "recovery-phrases-list";
      (opt.recoveryPhrases || []).forEach((phrase) => {
        const row = document.createElement("div");
        row.className = "recovery-phrase-row";
        const textBtn = document.createElement("button");
        textBtn.type = "button";
        textBtn.className = "recovery-phrase-text";
        textBtn.textContent = phrase.hanzi || "";
        const tooltipParts = [];
        if (phrase.pinyin) tooltipParts.push(phrase.pinyin);
        if (phrase.meaning) tooltipParts.push(phrase.meaning);
        textBtn.setAttribute("title", tooltipParts.join(" — ") || "");
        textBtn.addEventListener("click", async () => {
          emitUITrace({ type: "OPTION_SELECTED", timestamp: new Date().toISOString(),
            payload: { frame_id: frameId, card_id: "recovery:" + (phrase.id || ""), kind: "RECOVERY" } });
          container.querySelectorAll(".option-panel").forEach((p) => p.classList.remove("selected"));
          panel.classList.add("selected");
          const userText = (phrase.hanzi || "").trim();
          addTranscriptEntry("user", userText, { text_en: phrase.meaning || "" });
          const action = getRecoveryAction(phrase);
          const currentQuestion = (window._currentFrameText || "").trim();

          if (action === "next_turn") {
            renderTranscript();
            // Speak recovery phrase then bridge to another topic (user indicated difficulty)
            ttsSpeak({
              text: userText,
              lang: "zh-CN",
              onEvent: (e) => {
                if (e?.payload?.completed) runTurn(true, { prefer_bridge: true });
              },
            });
            return;
          }

          let partnerLine;
          let segments;
          const rawTokens = (frameTokens || window._frameTokens)?.frames?.[frameId];
          const hasNewSchema = rawTokens && rawTokens.length > 0 && "kind" in rawTokens[0];
          if (action === "slower") {
            partnerLine = currentQuestion ? "好的，慢一点：" + currentQuestion : "好的，慢一点。";
            const prefix = currentQuestion ? "好的，慢一点：" : "好的，慢一点。";
            segments = [{ t: prefix }];
            if (hasNewSchema && rawTokens.length) {
              segments = segments.concat(rawTokens.map((t) => ({ t: t.t, word_id: t.word_id || undefined })));
            } else if (currentQuestion) {
              segments = segments.concat(currentQuestion.split("").map((c) => ({ t: c })));
            }
          } else {
            // repeat: just say the question again, no preamble
            partnerLine = currentQuestion || "好。";
            if (hasNewSchema && rawTokens.length) {
              segments = rawTokens.map((t) => ({ t: t.t, word_id: t.word_id || undefined }));
            } else {
              segments = (currentQuestion || "").split("").map((c) => ({ t: c }));
            }
          }
          addTranscriptEntry("partner", partnerLine);
          renderTranscript();
          setActivePartnerStatement(partnerLine, "recovery_repeat", segments);
          // Speak user's phrase first, then partner response
          ttsSpeak({
            text: userText,
            lang: "zh-CN",
            onEvent: (e) => {
              if (e?.payload?.completed) {
                ttsSpeak({
                  text: partnerLine,
                  lang: "zh-CN",
                  rate: action === "slower" ? 0.82 : undefined,
                  queue: true,
                });
              }
            },
          });
          lastClickedWordId = null;
          window.lastClickedWordId = null;
          hint_cascade_state = { level: 0, turn_uid: "recovery_repeat" };
          renderHintAffordance({ ...(window._currentHintAffordance || {}), visible: true }, "recovery_repeat", "tap");
          setUiMode("READ");
        });
        const speakerBtn = document.createElement("button");
        speakerBtn.type = "button";
        speakerBtn.className = "recovery-speaker-btn";
        speakerBtn.setAttribute("title", "Speak this phrase");
        speakerBtn.setAttribute("aria-label", "Speak this phrase");
        speakerBtn.textContent = "\uD83D\uDD0A";
        speakerBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          ttsSpeak({ text: phrase.hanzi || "", lang: "zh-CN" });
        });
        row.appendChild(textBtn);
        row.appendChild(speakerBtn);
        listWrap.appendChild(row);
      });
      panel.appendChild(listWrap);
      container.appendChild(panel);
      return;
    }

    // Each response is a panel: top row (Chinese + actions) + hint block underneath in the same panel
    const panel = document.createElement("div");
    panel.className = "option-panel";
    panel.setAttribute("data-option-index", String(idx));
    if (opt.is_gold) panel.setAttribute("data-gold", "true"); // internal/trace only; not "correct answer" (Design Constitution)
    if (opt.is_slot) panel.setAttribute("data-slot", "true");
    if (opt.kind === "RECOVERY") panel.setAttribute("data-recovery", "true");
    panel.setAttribute("data-card-id", opt.card_id || "");

    const btn = document.createElement("button");
    btn.className = "option-btn";
    btn.type = "button";
    const optionContent = document.createElement("div");
    optionContent.className = "option-content";
    if (opt.kind === "FRAME_WITH_SLOTS") {
      (opt.hanzi || "").split(/(\{[A-Z_]+\})/).forEach(part => {
        const m = part.match(/^\{([A-Z_]+)\}$/);
        if (m) { const s = document.createElement("span"); s.className = "option-slot-placeholder"; s.textContent = m[1]; optionContent.appendChild(s); }
        else if (part) optionContent.appendChild(document.createTextNode(part));
      });
    } else {
      const h = document.createElement("span"); h.className = "option-hanzi"; h.textContent = opt.hanzi || "";
      optionContent.appendChild(h);
    }
    btn.appendChild(optionContent);
    const optionActions = document.createElement("div");
    optionActions.className = "option-actions";
    const hanziText = (opt.hanzi || "").trim();
    if (hanziText) {
      const speakerBtn = document.createElement("button");
      speakerBtn.type = "button";
      speakerBtn.className = "option-speaker-btn";
      speakerBtn.setAttribute("title", "Speak this option");
      speakerBtn.setAttribute("aria-label", "Speak this option");
      speakerBtn.textContent = "\uD83D\uDD0A";
      speakerBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        ttsSpeak({ text: hanziText, lang: "zh-CN" });
      });
      optionActions.appendChild(speakerBtn);
    }
    const hasHintContent = (opt.pinyin && String(opt.pinyin).trim()) || (opt.meaning && String(opt.meaning).trim()) || opt.kind === "RECOVERY";
    const hasHanzi = (opt.hanzi && String(opt.hanzi).trim());
    const hintId = (opt.card_id && String(opt.card_id).trim()) || "__opt_" + idx;
    if (opt.card_id || hasHintContent || hasHanzi) {
      const hintBtn = document.createElement("button");
      hintBtn.type = "button";
      hintBtn.className = "option-hint-btn";
      hintBtn.setAttribute("title", "Show pinyin, meaning, etymology for this option");
      hintBtn.setAttribute("aria-label", "Hint for this option");
      hintBtn.textContent = "?";
      hintBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const panelEl = e.target.closest(".option-panel");
        const turnUid = window._currentTurnUid || frameId;
        const alreadyShowingThisOption = hint_cascade_state.turn_uid === turnUid && lastClickedWordId === hintId;
        if (alreadyShowingThisOption) {
          hint_cascade_state.level = getNextHintLevel(hint_cascade_state.level);
        } else {
          lastClickedWordId = hintId;
          window.lastClickedWordId = hintId;
          hint_cascade_state = { level: 1, turn_uid: turnUid };
        }
        const hintAffordance = { ...(window._currentHintAffordance || {}), visible: true };
        renderHintAffordance(hintAffordance, turnUid, "tap", panelEl || undefined);
      });
      optionActions.appendChild(hintBtn);
    }
    if (optionActions.childNodes.length) btn.appendChild(optionActions);
    panel.appendChild(btn);

    const optionHintBlock = document.createElement("div");
    optionHintBlock.className = "option-hint-block";
    optionHintBlock.setAttribute("data-option-index", String(idx));
    optionHintBlock.style.display = "none";
    const optHintPinyin = document.createElement("div");
    optHintPinyin.className = "option-hint-row option-hint-pinyin";
    const optHintMeaning = document.createElement("div");
    optHintMeaning.className = "option-hint-row option-hint-meaning";
    const optHintEtymology = document.createElement("div");
    optHintEtymology.className = "option-hint-row option-hint-etymology";
    optionHintBlock.appendChild(optHintPinyin);
    optionHintBlock.appendChild(optHintMeaning);
    optionHintBlock.appendChild(optHintEtymology);
    panel.appendChild(optionHintBlock);

    btn.addEventListener("click", async () => {
      emitUITrace({ type: "OPTION_SELECTED", timestamp: new Date().toISOString(),
        payload: { frame_id: frameId, card_id: opt.card_id, is_gold: opt.is_gold, is_slot: opt.is_slot, option_idx: idx, kind: opt.kind } });
      container.querySelectorAll(".option-panel").forEach(p => p.classList.remove("selected"));
      panel.classList.add("selected");
      const userText = (opt.hanzi || "").trim();
      if (opt.kind !== "RECOVERY" && opt.kind !== "RECOVERY_PANEL") window._consecutiveNotUnderstood = 0;

      if (opt.kind === "RECOVERY") {
        const action = getRecoveryAction(opt);
        const currentQuestion = (window._currentFrameText || "").trim();

        if (action === "next_turn") {
          addTranscriptEntry("user", userText, { text_en: opt.meaning || "" });
          renderTranscript();
          ttsSpeak({
            text: userText,
            lang: "zh-CN",
            onEvent: (e) => {
              if (e?.payload?.completed) runTurn(true, { prefer_bridge: true });
            },
          });
          return;
        }

        let partnerLine;
        let segments;
        const rawTokens = (frameTokens || window._frameTokens)?.frames?.[frameId];
        const hasNewSchema = rawTokens && rawTokens.length > 0 && "kind" in rawTokens[0];
        if (action === "slower") {
          partnerLine = currentQuestion ? "好的，慢一点：" + currentQuestion : "好的，慢一点。";
          const prefix = currentQuestion ? "好的，慢一点：" : "好的，慢一点。";
          segments = [{ t: prefix }];
          if (hasNewSchema && rawTokens.length) {
            segments = segments.concat(rawTokens.map((t) => ({ t: t.t, word_id: t.word_id || undefined })));
          } else if (currentQuestion) {
            segments = segments.concat(currentQuestion.split("").map((c) => ({ t: c })));
          }
        } else {
          partnerLine = currentQuestion || "好。";
          if (hasNewSchema && rawTokens.length) {
            segments = rawTokens.map((t) => ({ t: t.t, word_id: t.word_id || undefined }));
          } else {
            segments = (currentQuestion || "").split("").map((c) => ({ t: c }));
          }
        }
        addTranscriptEntry("user", userText, { text_en: opt.meaning || "" });
        addTranscriptEntry("partner", partnerLine);
        renderTranscript();
        setActivePartnerStatement(partnerLine, "recovery_repeat", segments);
        ttsSpeak({
          text: userText,
          lang: "zh-CN",
          onEvent: (e) => {
            if (e?.payload?.completed) {
              ttsSpeak({
                text: partnerLine,
                lang: "zh-CN",
                rate: action === "slower" ? 0.82 : undefined,
                queue: true,
              });
            }
          },
        });
        lastClickedWordId = null;
        window.lastClickedWordId = null;
        hint_cascade_state = { level: 0, turn_uid: "recovery_repeat" };
        renderHintAffordance({ ...(window._currentHintAffordance || {}), visible: true }, "recovery_repeat", "tap");
        setUiMode("READ");
        return;
      }

      if (opt.card_id && opt.kind !== "FRAME_WITH_SLOTS") {
        dispatch({ type: "OPEN_CARD", payload: { card_id: opt.card_id } });
        resolveCard(opt.card_id, "tools/cards/out/cards_by_id.json");
      }
      // Phase 8: append user answer, then advance to next turn so the server picks the next partner line
      // (e.g. 很高兴认识你。 or 你的名字是什么意思？) instead of staying on hardcoded "你呢？"
      // Phase 10: record last_answer for fact-capture (server stores by learner_id)
      window._lastAnswer = { frame_id: frameId, selected_option_hanzi: userText, selected_option_meaning: opt.meaning || undefined };
      addTranscriptEntry("user", userText, { text_en: opt.meaning || "" });
      renderTranscript();
      // Speak the user's response, then advance to next turn (server returns next partner line and we speak it)
      ttsSpeak({
        text: userText,
        lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed) {
            runTurn(true, { last_turn_was_answer: true });
          }
        },
      });
      lastClickedWordId = null;
      window.lastClickedWordId = null;
      setUiMode("READ");
    });
    container.appendChild(panel);
  });
}
// ── end Phase 6 ────────────────────────────────────────────────────────────

/** Oxygen loop: "Ask back" row — show probe options (为什么？, 谁？, 哪里？, etc.) when server set probe_offer. */
function renderProbeRow(probeOptions) {
  let parent = document.getElementById("optionsContainerParent");
  if (!parent) return;
  let row = document.getElementById("probeRowContainer");
  if (!row) {
    row = document.createElement("div");
    row.id = "probeRowContainer";
    row.className = "probe-row-container";
    parent.appendChild(row);
  }
  row.style.display = "block";
  row.textContent = "";
  const label = document.createElement("div");
  label.className = "probe-row-label";
  label.textContent = "你也可以问：";
  row.appendChild(label);
  const wrap = document.createElement("div");
  wrap.className = "probe-row-buttons";
  (probeOptions || []).forEach((probe) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "probe-btn";
    btn.setAttribute("data-probe-id", probe.id || "");
    btn.setAttribute("data-probe-hanzi", probe.hanzi || "");
    btn.textContent = probe.hanzi || "";
    btn.title = (probe.pinyin || "") + (probe.meaning ? " — " + probe.meaning : "");
    btn.addEventListener("click", () => runProbeTurn(probe));
    wrap.appendChild(btn);
  });
  row.appendChild(wrap);
}

function hideProbeRow() {
  const row = document.getElementById("probeRowContainer");
  if (row) row.style.display = "none";
}

function renderDirectionButtons() {
  const reverseBtn = document.getElementById("reverseBtn");
  const whyBtn = document.getElementById("whyBtn");
  if (!reverseBtn || !whyBtn) return;
  reverseBtn.style.display = _directionCaps.supports_reverse ? "" : "none";
  whyBtn.style.display = _directionCaps.supports_why ? "" : "none";
}

async function runDirectionTurn(intent) {
  const map = { reverse: "你呢？", why: "为什么？" };
  const userText = map[intent] || "";
  if (!userText) return;
  addTranscriptEntry("user", userText, { text_en: intent === "reverse" ? "And you?" : "Why?" });
  renderTranscript();
  ttsSpeak({ text: userText, lang: "zh-CN" });

  const currentEngine = window._currentEngineId ?? "identity";
  const payload = {
    env: "dev",
    turn_uid: "ui_direction_" + Date.now(),
    direction_intent: intent,
    direction_hanzi: userText,
    conversation_state: {
      session_id: window._sessionId,
      current_engine: currentEngine,
      last_partner_frame_id: window._lastPartnerFrameId ?? null,
      recent_frame_ids: Array.isArray(window._recentFrameIds) ? window._recentFrameIds : []
    }
  };
  if (window._personaId) payload.persona_id = window._personaId;

  let res;
  try {
    res = await fetch("/api/run_turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    console.warn("[app] runDirectionTurn fetch failed", e);
    return;
  }
  if (!res.ok) return;
  let data = {};
  try { data = await res.json(); } catch (_) { return; }

  const stub = (data.frame_text || "").trim();
  if (stub) {
    addTranscriptEntry("partner", stub);
    renderTranscript();
    ttsSpeak({
      text: stub,
      lang: "zh-CN",
      onEvent: (e) => {
        if (e?.payload?.completed) runTurn(true);
      },
    });
  } else {
    runTurn(true);
  }
}

/** Send probe as user message, show partner stub, then request next question. */
async function runProbeTurn(probe) {
  const hanzi = (probe.hanzi || "").trim();
  if (!hanzi) return;
  addTranscriptEntry("user", hanzi, { text_en: probe.meaning || "" });
  renderTranscript();
  ttsSpeak({ text: hanzi, lang: "zh-CN" });

  const currentEngine = window._currentEngineId ?? "identity";
    const payload = {
    env: "dev",
    turn_uid: "ui_probe_" + Date.now(),
    probe_id: probe.id || "",
    probe_hanzi: hanzi,
    conversation_state: {
      session_id: window._sessionId,
      current_engine: currentEngine,
      last_partner_frame_id: window._lastPartnerFrameId ?? null,
      recent_frame_ids: Array.isArray(window._recentFrameIds) ? window._recentFrameIds : []
    }
  };
  if (window._personaId) payload.persona_id = window._personaId;
  let res;
  try {
    res = await fetch("/api/run_turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    console.warn("[app] runProbeTurn fetch failed", e);
    return;
  }
  if (!res.ok) return;
  let data = {};
  try {
    data = await res.json();
  } catch (e) {
    return;
  }
  const stub = (data.frame_text || "").trim();
  if (stub) {
    addTranscriptEntry("partner", stub);
    renderTranscript();
    ttsSpeak({
      text: stub,
      lang: "zh-CN",
      onEvent: (e) => {
        if (e?.payload?.completed) runTurn(true);
      },
    });
  } else {
    runTurn(true);
  }
  hideProbeRow();
}

/**
 * Run a turn: either "Run Turn" (frame from dropdown) or "Next" (selector-driven next frame).
 * @param {boolean} [isNext=false] When true, send next_question + conversation_state; server chooses frame.
 * @param {{ prefer_bridge?: boolean, force_bridge?: boolean, last_turn_was_answer?: boolean }} [opts] When isNext: prefer_bridge tries bridge first (e.g. after interesting answer or recovery); force_bridge only bridge; last_turn_was_answer triggers probe_offer.
 */
async function runTurn(isNext = false, opts = {}) {
  const selected = frameSelect.value;
  const selectedOption = frameSelect.options[frameSelect.selectedIndex];
  const engineIdFromDropdown = selectedOption?.dataset?.engineId || null;

  let payload;
  if (isNext) {
    const firstOptionEngine = frameSelect.options[0]?.dataset?.engineId || null;
    const currentEngine = window._currentEngineId ?? engineIdFromDropdown ?? firstOptionEngine ?? "identity";
    const lastPartnerFrameId = window._lastPartnerFrameId ?? selected;
    const conversation_state = {
      session_id: window._sessionId,
      current_engine: currentEngine,
      last_partner_frame_id: lastPartnerFrameId,
      recent_frame_ids: Array.isArray(window._recentFrameIds) ? window._recentFrameIds : [],
      // Phase 10.5 selector state
      exchange_count: window._exchangeCount || 0,
      curiosity_depth: window._curiosityDepth || 0,
      ask_chain_count: window._askChainCount || 0,
      last_partner_turn_type: window._lastPartnerTurnType || "question",
      same_engine_chain_count: window._sameEngineChainCount || 0,
      same_slot_chain_count: window._sameSlotChainCount || 0,
      last_focus_slot: window._lastFocusSlot || "",
      pending_listening_move: window._pendingListeningMove === true,
      listening_wait_turns: window._listeningWaitTurns || 0,
      last_interest_level: window._lastInterestLevel || "low",
      last_user_text: window._lastUserText || ""
    };
    if (window._learnerId) conversation_state.learner_id = window._learnerId;
    if (window._personaId) conversation_state.persona_id = window._personaId;
    if (opts.prefer_bridge === true) conversation_state.prefer_bridge = true;
    if (opts.force_bridge === true) conversation_state.force_bridge = true;
    if (opts.last_turn_was_answer === true) {
      conversation_state.last_turn_was_answer = true;
      if (window._lastAnswer && window._lastAnswer.frame_id) {
        conversation_state.last_answer = window._lastAnswer;
        window._lastAnswer = null; // send once only
      }
    }
    payload = {
      env: "dev",
      turn_uid: "ui_" + Date.now(),
      next_question: true,
      conversation_state
    };
    if (!currentEngine) {
      emitUITrace({
        type: "UI_ERROR",
        timestamp: new Date().toISOString(),
        payload: { message: "Next question requires current_engine (run a turn first or select a frame)" }
      });
      return;
    }
  } else {
    payload = {
      env: "dev",
      turn_uid: "ui_" + Date.now(),
      frame_id: selected,
      engine_id: engineIdFromDropdown
    };
    if (selected && selected.endsWith(".json")) {
      payload.frame_path = selected;
    } else {
      if (!engineIdFromDropdown) {
        emitUITrace({
          type: "UI_ERROR",
          timestamp: new Date().toISOString(),
          payload: { message: "Missing engine id for selected pack frame" }
        });
        return;
      }
    }
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

  // Phase 6: parse response and open card if card_id returned
  let data = {};
  try {
    data = await res.json();
  } catch (e) {
    console.warn("[app] runTurn: failed to parse response JSON", e);
  }

  // Phase 10.5: update behaviour counters from server response (UI can ignore extras; we use for next selector call).
  if (opts?.last_turn_was_answer === true) {
    window._exchangeCount = (window._exchangeCount || 0) + 1;
  }
  if (typeof data.turn_type === "string") {
    window._lastPartnerTurnType = data.turn_type;
    if (data.turn_type === "loop_question") {
      window._curiosityDepth = Math.min((window._curiosityDepth || 0) + 1, 2);
      window._askChainCount = 0;
    } else if (data.turn_type === "question") {
      window._askChainCount = (window._askChainCount || 0) + 1;
      // Leaving a curiosity chain resets depth.
      if ((window._askChainCount || 0) >= 1) window._curiosityDepth = 0;
    } else if (data.turn_type === "reaction") {
      window._askChainCount = 0;
    }
  }
  if (typeof data.same_engine_chain_count === "number") window._sameEngineChainCount = data.same_engine_chain_count;
  if (typeof data.same_slot_chain_count === "number") window._sameSlotChainCount = data.same_slot_chain_count;
  if (typeof data.last_focus_slot === "string") window._lastFocusSlot = data.last_focus_slot;
  if (typeof data.pending_listening_move === "boolean") window._pendingListeningMove = data.pending_listening_move;
  if (typeof data.listening_wait_turns === "number") window._listeningWaitTurns = data.listening_wait_turns;
  if (typeof data.last_interest_level === "string") window._lastInterestLevel = data.last_interest_level;
  if (typeof data.last_user_text === "string") window._lastUserText = data.last_user_text;

  const frameId = data.frame_id || selected;
  const engineId = data.engine_id ?? (payload.engine_id || engineIdFromDropdown);

  // Phase 9.1: update conversation state from response so Next has correct state
  window._currentEngineId = engineId;
  window._lastPartnerFrameId = frameId;
  if (Array.isArray(window._recentFrameIds)) {
    window._recentFrameIds.push(frameId);
    if (window._recentFrameIds.length > 50) window._recentFrameIds = window._recentFrameIds.slice(-50);
  } else {
    window._recentFrameIds = [frameId];
  }

  // Emit TURN_START
  emitUITrace({
    type: "TURN_START",
    timestamp: null,
    payload: { turn_uid: payload.turn_uid, engine_id: engineId, frame_id: frameId }
  });

  // Sync dropdown to chosen frame when server chose it (e.g. Next)
  if (payload.next_question && frameId) {
    const opt = Array.from(frameSelect.options).find((o) => o.value === frameId);
    if (opt) {
      frameSelect.selectedIndex = Array.from(frameSelect.options).indexOf(opt);
    }
  }

  // Render frame sentence
  const fallbackText = data.prompt_text || data.frame_text || "";
  renderFrameSentence({ id: frameId, text: fallbackText });
  setUiMode("READ");
  window._currentFrameText = (fallbackText && fallbackText.trim()) ? fallbackText.trim() : "";
  // Phase 8: append partner question to transcript when we show a new question
  if (window._currentFrameText) {
    addTranscriptEntry("partner", window._currentFrameText, {
      text_en: data.frame_text_en || "",
      pinyin: data.frame_pinyin || "",
      frame_id: frameId,
      turn_uid: payload.turn_uid,
    });
    renderTranscript();
  }
  // Auto-play active sentence (most people better at hearing than reading)
  if (fallbackText && fallbackText.trim()) {
    ttsSpeak({ text: fallbackText.trim(), lang: "zh-CN" });
  }
  // Phase 6 — options: prefer server-sent options when server chose the frame (next_question) so options always match the displayed question after bridge
  const _frameData     = window._frameOptionsRuntime?.frames?.[frameId] || {};
  const tapOptions     = (payload.next_question && Array.isArray(data.options) && data.options.length > 0)
    ? data.options
    : (_frameData.options || data.options || []);
  const hintAffordance = _frameData.hint_affordance || { visible: false };
  const turnUid        = frameId;

  // Sentence-level hints (pinyin → English); used when no word is selected
  window._sentenceHint = {
    pinyin:  data.frame_pinyin  ?? "",
    text_en: data.frame_text_en ?? ""
  };
  lastClickedWordId = null;
  window.lastClickedWordId = null;

  window._tapOptions = tapOptions;
  window._currentHintAffordance = hintAffordance;
  window._currentTurnUid = turnUid;
  renderOptions(tapOptions, frameId);
  // Phase 10 Step 7: show remembered facts when server sends learner_memory (cross-session continuity)
  const rememberedEl = document.getElementById("rememberedFacts");
  if (rememberedEl && data.learner_memory && typeof data.learner_memory === "object") {
    const m = data.learner_memory;
    const parts = [m.learner_name, m.hometown, m.lives_in, m.job_or_study, m.family, m.favourite_food].filter(Boolean);
    if (parts.length > 0) {
      rememberedEl.textContent = "Remembered: " + parts.join(", ");
      rememberedEl.style.display = "";
    } else {
      rememberedEl.style.display = "none";
    }
  } else if (rememberedEl) {
    rememberedEl.style.display = "none";
  }

  // Oxygen loop: show "Ask back" probe options when user just gave an interesting answer
  if (data.probe_offer === true && Array.isArray(data.probe_options) && data.probe_options.length > 0) {
    renderProbeRow(data.probe_options);
  } else {
    hideProbeRow();
  }
  // Direction actions for question reversal/why
  _directionCaps = {
    supports_reverse: data.supports_reverse === true,
    supports_why: data.supports_why === true
  };
  renderDirectionButtons();
  renderHintAffordance(hintAffordance, turnUid, "tap");
  
  // Wire hint button click: use current turn so recovery (and 你呢？) hint isn't reset to frame
  const _hintBtn = document.getElementById("hintBtn");
  if (_hintBtn) {
    const _newBtn = _hintBtn.cloneNode(true);
    _hintBtn.parentNode.replaceChild(_newBtn, _hintBtn);
    _newBtn.addEventListener("click", () => {
      hint_cascade_state.level = getNextHintLevel(hint_cascade_state.level);
      const currentTurnUid = hint_cascade_state.turn_uid || turnUid;
      const currentAffordance = window._currentHintAffordance || hintAffordance;
      renderHintAffordance(currentAffordance, currentTurnUid, "tap");
      emitUITrace({ type: "HINT_ADVANCED", timestamp: new Date().toISOString(),
        payload: { frame_id: frameId, level: hint_cascade_state.level, turn_uid: currentTurnUid } });
    });
  }

  // If server returned a card_id, open the card panel
  if (data.card_id) {
    dispatch({ type: "OPEN_CARD", payload: { card_id: data.card_id } });
    const usingFixtureFrame = String(frameSelect.value || "").includes("tests/fixtures/");
    const cardsPath = usingFixtureFrame
      ? "tests/fixtures/cards.fixture.json"
      : "tools/cards/out/cards_by_id.json";
    await resolveCard(data.card_id, cardsPath);
  }

  // Tripwire 3.1: turn option invariant (section 3.1 of copilot-instructions.md)
  if (data.option_count === 0 || data.gold_option_present === false) {
    emitUITrace({
      type: "turn_option_invariant_failed",
      timestamp: new Date().toISOString(),
      payload: {
        turn_uid: payload.turn_uid,
        frame_id: frameId,
        engine_id: engineId,
        option_count: data.option_count ?? 0,
        gold_present: data.gold_option_present ?? false,
        failure_reason: data.option_count === 0 ? "no_options" : "gold_missing"
      }
    });
    console.warn("[app] turn_option_invariant_failed — stub engine returned no options");
  }

  // Emit TURN_END
  emitUITrace({
    type: "TURN_END",
    timestamp: null,
    payload: { turn_uid: payload.turn_uid, result: data.card_id ? "OPEN_CARD_FIRED" : "NO_CARD" }
  });

  // Legacy: resolve card if already open but card content missing
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
  // Phase 6: load render tokens and cards index in parallel with existing loads
  await Promise.all([
    loadPackFramesIntoDropdown(),
    loadFrameRenderTokens(),
    loadCardsIndex(),
    loadFrameOptions(),
    loadWordEtymology(),
    loadFrameTokens(),
    loadRecoveryPhrases(),
  ]);
  if (dataBuildInfoEl) dataBuildInfoEl.textContent = `Data: ${UI_DATA_BUILD_LABEL}`;
  const displayModeEl = document.getElementById("transcriptDisplayMode");
  if (displayModeEl) {
    displayModeEl.value = transcriptDisplayMode;
    displayModeEl.addEventListener("change", (e) => {
      transcriptDisplayMode = e.target.value === "zh_en" ? "zh_en" : "zh";
      renderTranscript();
    });
  }
  const replaySpeedEl = document.getElementById("transcriptReplaySpeed");
  if (replaySpeedEl) {
    replaySpeedEl.value = String(transcriptReplaySpeed.toFixed(1));
    replaySpeedEl.addEventListener("change", (e) => {
      const v = parseFloat(e.target.value);
      if (!Number.isNaN(v) && v > 0) transcriptReplaySpeed = v;
    });
  }
  const stopReplayBtn = document.getElementById("stopReplayBtn");
  if (stopReplayBtn) {
    stopReplayBtn.addEventListener("click", () => stopTranscriptReplay());
  }
  const segmentModeToggle = document.getElementById("segmentModeToggle");
  if (segmentModeToggle) {
    segmentModeToggle.checked = transcriptSegmentMode;
    segmentModeToggle.addEventListener("change", (e) => {
      transcriptSegmentMode = !!e.target.checked;
      if (!transcriptSegmentMode) transcriptSelectedLineIds = [];
      updateReplaySelectedButton();
      renderTranscript();
    });
  }
  const replaySelectedBtn = document.getElementById("replaySelectedBtn");
  if (replaySelectedBtn) {
    replaySelectedBtn.addEventListener("click", () => replaySelectedTranscriptLines());
  }
  updateReplaySelectedButton();
  // Phase 7.4: Speak-first — actually listen (Web Speech API), then either advance turn or show recovery
  const LISTEN_BEFORE_RECOVERY_MS = 7000;
  document.getElementById("showOptionsBtn")?.addEventListener("click", () => {
    setUiMode("RESPOND");
  });
  document.getElementById("tryRespondingBtn")?.addEventListener("click", async () => {
    const btn = document.getElementById("tryRespondingBtn");
    const frameId = window._lastPartnerFrameId || null;
    const optionsFromFrame = frameId && window._frameOptionsRuntime?.frames?.[frameId]?.options;
    const options = (window._tapOptions && window._tapOptions.length > 0)
      ? window._tapOptions
      : (Array.isArray(optionsFromFrame) ? optionsFromFrame : []);
    if (btn) btn.textContent = "Listening…";
    if (options.length === 0) {
      emitUITrace({ type: "SPEECH_LISTEN_OPTIONS", timestamp: new Date().toISOString(), payload: { frame_id: frameId, option_count: 0, warning: "No options to match against; use Run Turn first or check frame_options" } });
    } else {
      emitUITrace({ type: "SPEECH_LISTEN_OPTIONS", timestamp: new Date().toISOString(), payload: { frame_id: frameId, option_count: options.length } });
    }
    const { transcript, matchedOption } = await listenForResponse(options, LISTEN_BEFORE_RECOVERY_MS);
    emitUITrace({ type: "SPEECH_RESULT", timestamp: new Date().toISOString(), payload: { transcript: transcript || "", transcript_length: (transcript || "").length, matched: !!matchedOption } });
    if (btn) {
      btn.textContent = "\uD83C\uDFA4";
      btn.title = "Speak your answer";
    }
    if (matchedOption) {
      window._consecutiveNotUnderstood = 0;
      // Understood: update conversation and move to next turn (same as selecting that option)
      emitUITrace({ type: "SPEECH_UNDERSTOOD", timestamp: new Date().toISOString(), payload: { transcript, matched_hanzi: matchedOption.hanzi } });
      if (matchedOption.card_id && matchedOption.kind !== "FRAME_WITH_SLOTS") {
        dispatch({ type: "OPEN_CARD", payload: { card_id: matchedOption.card_id } });
        resolveCard(matchedOption.card_id, "tools/cards/out/cards_by_id.json");
      }
      const optionsContainer = document.getElementById("optionsContainer");
      if (optionsContainer) {
        optionsContainer.querySelectorAll(".option-panel").forEach((p) => p.classList.remove("selected"));
        const toSelect = optionsContainer.querySelector(`.option-panel[data-card-id="${(matchedOption.card_id || "").replace(/"/g, "")}"]`);
        if (toSelect) toSelect.classList.add("selected");
      }
      addTranscriptEntry("user", (matchedOption.hanzi || "").trim(), { text_en: matchedOption.meaning || "" });
      renderTranscript();
      const saidText = (matchedOption.hanzi || "").trim();
      window._lastAnswer = { frame_id: frameId, selected_option_hanzi: saidText, selected_option_meaning: matchedOption.meaning || undefined };
      ttsSpeak({
        text: saidText,
        lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed) runTurn(true, { last_turn_was_answer: true });
        },
      });
      lastClickedWordId = null;
      window.lastClickedWordId = null;
      setUiMode("READ");
      return;
    }
    // No option match but user said something substantial — accept and advance to sustain conversation (no "correct answer" required)
    const saidTrimmed = (transcript && typeof transcript === "string") ? transcript.trim() : "";
    const unmatchedDecision = classifyUnmatchedFreeAnswerDecision(saidTrimmed, options, frameId);
    const substantialAnswer = unmatchedDecision.accept;
    if (substantialAnswer) {
      window._consecutiveNotUnderstood = 0;
      emitUITrace({
        type: "SPEECH_ACCEPTED_AS_ANSWER",
        timestamp: new Date().toISOString(),
        payload: { transcript: saidTrimmed, matched: false, unmatched_decision_reason: unmatchedDecision.reason, frame_id: frameId }
      });
      addTranscriptEntry("user", saidTrimmed);
      renderTranscript();
      window._lastAnswer = { frame_id: frameId, submitted_text: saidTrimmed };
      ttsSpeak({
        text: saidTrimmed,
        lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed) runTurn(true, { last_turn_was_answer: true });
        },
      });
      lastClickedWordId = null;
      window.lastClickedWordId = null;
      setUiMode("READ");
      return;
    }
    // Not understood: update conversation with what we heard and partner's recovery (Phase 9: improve decision so reasonable answers aren't treated as not understood)
    emitUITrace({
      type: "SPEECH_NOT_UNDERSTOOD",
      timestamp: new Date().toISOString(),
      payload: { transcript, unmatched_decision_reason: unmatchedDecision.reason, frame_id: frameId }
    });
    addTranscriptEntry("user", (transcript && transcript.trim()) ? transcript.trim() : "[couldn't understand]");
    const lastRecoveryId = window._lastRecoveryPhraseId || null;
    const phrase = getRecoveryPhraseForNotUnderstood(lastRecoveryId);
    window._lastRecoveryPhraseId = phrase.id;
    addTranscriptEntry("partner", phrase.hanzi);
    renderTranscript();
    const recoverySegments = (phrase.hanzi || "").split("").map((c) => ({ t: c }));
    setActivePartnerStatement(phrase.hanzi, "recovery", recoverySegments);
    window._sentenceHint = { pinyin: phrase.pinyin, text_en: phrase.text_en, etymology: phrase.etymology || "" };
    lastClickedWordId = null;
    window.lastClickedWordId = null;
    hint_cascade_state = { level: 0, turn_uid: "recovery" };
    renderHintAffordance({ visible: true }, "recovery", "tap");
    if (phrase.recovery_action === "next_turn") {
      window._consecutiveNotUnderstood = 0;
      setUiMode("READ");
      ttsSpeak({
        text: phrase.hanzi,
        lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed) runTurn(true, { prefer_bridge: true });
        },
      });
    } else {
      ttsSpeak({ text: phrase.hanzi, lang: "zh-CN" });
      setUiMode("RESPOND");
    }
  });
  // Phase 7 completion: Play question (TTS for frame sentence)
  document.getElementById('playQuestionBtn')?.addEventListener('click', () => {
    const fs = document.getElementById('frameSentence');
    const text = (fs && fs.textContent && fs.textContent.trim()) || "";
    if (!text) return;
    const utterance_id = "frame_question:" + (frameSelect?.value || "unknown");
    emitUITrace({
      type: "AUDIO_PLAY_REQUESTED",
      timestamp: new Date().toISOString(),
      payload: { utterance_id, text, source: "play_question" }
    });
    ttsSpeak({
      text,
      lang: "zh-CN",
      utterance_id,
      onEvent: (traceEntry) => emitUITrace(traceEntry),
    });
  });
  // Close micro-gloss on click outside sentence area
  document.addEventListener('click', (e) => {
    const mg = document.getElementById('microGloss');
    const fs = document.getElementById('frameSentence');
    if (mg && fs && !fs.contains(e.target) && !mg.contains(e.target)) _closeMicroGloss();
  });
  render();
});

runBtn.addEventListener("click", () => runTurn(false));
if (nextBtn) nextBtn.addEventListener("click", () => runTurn(true));
const reverseBtn = document.getElementById("reverseBtn");
if (reverseBtn) reverseBtn.addEventListener("click", () => runDirectionTurn("reverse"));
const whyBtn = document.getElementById("whyBtn");
if (whyBtn) whyBtn.addEventListener("click", () => runDirectionTurn("why"));
const changeTopicBtn = document.getElementById("changeTopicBtn");
if (changeTopicBtn) changeTopicBtn.addEventListener("click", () => runTurn(true, { prefer_bridge: true }));
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
// ── Phase 6 — expose to window for console access + external callers ────────
window.SystemFaultLog          = SystemFaultLog;
window.buildDiagnosticCompleted = buildDiagnosticCompleted;
window.hint_cascade_state   = hint_cascade_state;
window.renderHintAffordance = renderHintAffordance;


















