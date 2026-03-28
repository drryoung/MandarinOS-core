import { initialState as _initialState, reduce } from "./state/cardPanelState.js";
import { ttsSpeak } from "./ttsSpeak.js";
import { splitHeadwordPinyinToGraphemes } from "./pinyinAlign.js";

const frameSelect = document.getElementById("frameSelect");
const runBtn = document.getElementById("runBtn");
const nextBtn = document.getElementById("nextBtn");
const traceEl = document.getElementById("trace");
const cardPanel = document.getElementById("cardPanel");
const noCard = document.getElementById("noCard");
const cardTitle = document.getElementById("cardTitle");
const cardBody = document.getElementById("cardBody");
const cardError = document.getElementById("cardError");

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
// Phase 11C: active conversation partner (distinct from learner persona_id above)
if (typeof window._partnerId === "undefined") window._partnerId = null;
// Phase 12B: tracks how many consecutive probe follow-ups have been asked; resets on real answer
if (typeof window._probeDepth === "undefined") window._probeDepth = 0;
// Tracks consecutive user-led questions (probes + direction turns) so partner can reclaim after a natural run
if (typeof window._userQuestionChain === "undefined") window._userQuestionChain = 0;
if (typeof window._lastProbeOptions === "undefined") window._lastProbeOptions = [];
const MAX_USER_QUESTION_CHAIN = 3;  // after this many consecutive user questions the partner reclaims the lead
// Phase 11C: per-engine reveal tracking — reset when partner changes or session resets
if (typeof window._revealedVoiceLines === "undefined") window._revealedVoiceLines = {};
if (typeof window._revealedPartnerFacts === "undefined") window._revealedPartnerFacts = {};
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
if (typeof window._unmatchedByFrame === "undefined") window._unmatchedByFrame = {};
// Phase 12C: session arc state
if (typeof window._loopCountInEngine    === "undefined") window._loopCountInEngine    = 0;
if (typeof window._enginesVisited       === "undefined") window._enginesVisited        = ["identity"];
if (typeof window._recentConfusionCount === "undefined") window._recentConfusionCount  = 0;
// In-card progressive hints (no need to use ? after opening card)
let _cardRevealCardId = null;
/** How many optional blocks are visible after headword: 0 = hanzi only, then +pinyin, +meaning, +composition, +etymology in order. */
let _cardExtrasVisible = 0;
/** Focused character chip index + step for per-char reveal (0 TTS, 1 pinyin, 2 meaning, 3 char etymology). */
let _cardCharFocusIdx = null;
let _cardCharPhase = 0;

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

// ── Phase 7.4 + Mobile word insight: singleton popover (fixed position) ─────
let _microGlossActiveTokenEl = null;

/** True on large + fine pointer: also open side card panel on token tap (desktop habit). */
function _shouldAlsoOpenCardPanel() {
  try {
    return window.matchMedia("(min-width: 960px) and (pointer: fine)").matches;
  } catch (e) {
    return false;
  }
}

/** Map __opt_N (option-hint pseudo id) to real card_id for etymology index lookup. */
function resolveWordIdForEtymology(wordId) {
  if (!wordId || typeof wordId !== "string") return null;
  if (wordId.startsWith("__opt_")) {
    const idx = parseInt(wordId.slice(6), 10);
    const opt = Array.isArray(window._tapOptions) && Number.isInteger(idx) ? window._tapOptions[idx] : null;
    return opt?.card_id || null;
  }
  return wordId;
}

/** Card id we can open in the side panel (index map or direct key in cards_by_id cache). */
function resolveOpenableCardId(wordId) {
  if (!wordId || typeof wordId !== "string") return null;
  const resolved = resolveWordIdForEtymology(wordId) || wordId;
  const fromIdx = cardsIndex?.by_word_id?.[resolved];
  if (typeof fromIdx === "string" && fromIdx) return fromIdx;
  if (window._cardsByIdCache?.[resolved]) return resolved;
  return null;
}

function getCardFromCacheByWordId(wordId) {
  const key = resolveOpenableCardId(wordId);
  if (!key || !window._cardsByIdCache) return null;
  return window._cardsByIdCache[key] || null;
}

function _closeMicroGloss() {
  const mg = document.getElementById("microGloss");
  if (mg) {
    mg.style.display = "none";
    delete mg.dataset.insightSource;
  }
  const openBtn = document.getElementById("microGlossOpenCard");
  if (openBtn) {
    openBtn.style.display = "";
    openBtn.onclick = null;
  }
  const etymEl = document.getElementById("microGlossEtym");
  if (etymEl) {
    etymEl.textContent = "";
    etymEl.style.display = "none";
  }
  _microGlossActiveTokenEl = null;
}

function _positionMicroGlossNearEl(tokenEl) {
  const mg = document.getElementById("microGloss");
  if (!mg || !tokenEl) return;
  const rect = tokenEl.getBoundingClientRect();
  const margin = 8;
  const gap = 6;
  const maxW = Math.min(280, window.innerWidth - 2 * margin);
  mg.style.maxWidth = `${maxW}px`;
  mg.style.position = "fixed";
  mg.style.zIndex = "10000";
  let left = rect.left;
  let top = rect.bottom + gap;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (left + maxW > vw - margin) left = Math.max(margin, vw - margin - maxW);
  if (left < margin) left = margin;
  mg.style.left = `${Math.round(left)}px`;
  mg.style.top = `${Math.round(top)}px`;
  requestAnimationFrame(() => {
    const mh = mg.offsetHeight || 120;
    if (top + mh > vh - margin) {
      const up = rect.top - mh - gap;
      if (up >= margin) top = up;
      else top = Math.max(margin, vh - margin - mh);
    }
    mg.style.top = `${Math.round(top)}px`;
  });
}

/**
 * Word insight popover (MOBILE_WORD_INSIGHT_UI_SPEC): pinyin/gloss, etymology status, optional open card.
 * @param {HTMLElement} tokenEl
 * @param {string|null} wordId
 * @param {string} surfaceText
 * @param {string} [insightSource] e.g. active_sentence, option:0
 */
function _openWordInsightPopover(tokenEl, wordId, surfaceText, insightSource) {
  const mg = document.getElementById("microGloss");
  const headwordEl = document.getElementById("microGlossHeadword");
  const bodyEl = document.getElementById("microGlossBody");
  const etymEl = document.getElementById("microGlossEtym");
  const openCardBtn = document.getElementById("microGlossOpenCard");
  if (!mg || !headwordEl || !bodyEl || !openCardBtn) return;
  if (insightSource) mg.dataset.insightSource = insightSource;
  else delete mg.dataset.insightSource;

  headwordEl.textContent = surfaceText || "";

  if (!wordId) {
    bodyEl.textContent = "Not in lexicon yet.";
    if (etymEl) {
      etymEl.textContent = "";
      etymEl.style.display = "none";
    }
    openCardBtn.style.display = "none";
    openCardBtn.onclick = null;
    _positionMicroGlossNearEl(tokenEl);
    mg.style.display = "block";
    _microGlossActiveTokenEl = tokenEl;
    return;
  }

  const hint = getWordHintData(wordId);
  const py = (hint?.pinyin || "").trim();
  const mean = (hint?.meaning || "").trim();
  bodyEl.textContent = [py, mean].filter(Boolean).join(" — ") || "(No pinyin or gloss in index yet.)";

  if (etymEl) {
    etymEl.textContent = "";
    etymEl.style.display = "none";
  }

  const openId = resolveOpenableCardId(wordId);
  if (openId) {
    openCardBtn.style.display = "";
    openCardBtn.onclick = () => {
      _closeMicroGloss();
      _openCardForWordId(wordId);
    };
  } else {
    openCardBtn.style.display = "none";
    openCardBtn.onclick = null;
  }

  _positionMicroGlossNearEl(tokenEl);
  mg.style.display = "block";
  _microGlossActiveTokenEl = tokenEl;
}

async function _openCardForWordId(wordId) {
  if (!wordId) return;
  const cardId = resolveOpenableCardId(wordId);
  if (!cardId) { console.warn(`[app] _openCardForWordId: no card for word_id "${wordId}"`); return; }
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

/** Hanzi → row from `characters_1200.json` (radical, decomposition, notes). Fills gaps when word_etymology.runtime.json is absent. */
let charCoreByHanzi = Object.create(null);

/** Merged from `/component_gloss_maps.json` (radical variants + teaching supplement). */
window._radicalVariantGlossEn = window._radicalVariantGlossEn || Object.create(null);
window._teachingSupplementGlossEn = window._teachingSupplementGlossEn || Object.create(null);

async function loadComponentGlossMaps() {
  try {
    // Repo root (ui_server: top-level *.json) — same pattern as characters_1200.json
    let r = await fetch("/component_gloss_maps.json");
    if (!r.ok) {
      r = await fetch("/data/component_gloss_maps.json");
    }
    if (!r.ok) {
      console.warn(`[app] component_gloss_maps not available (HTTP ${r.status})`);
      return;
    }
    const d = await r.json();
    const rv = d.radical_variant_gloss_en && typeof d.radical_variant_gloss_en === "object" ? d.radical_variant_gloss_en : {};
    const ts = d.teaching_supplement_en && typeof d.teaching_supplement_en === "object" ? d.teaching_supplement_en : {};
    Object.assign(window._radicalVariantGlossEn, rv);
    Object.assign(window._teachingSupplementGlossEn, ts);
    console.info(
      `[app] component gloss maps loaded (${Object.keys(rv).length} radical variant(s), ${Object.keys(ts).length} teaching supplement(s))`
    );
  } catch (e) {
    console.warn("[app] component_gloss_maps load failed:", e);
  }
}

async function loadCharacters1200Core() {
  try {
    let resp = await fetch("/characters_1200.json");
    if (!resp.ok) {
      resp = await fetch("/data/characters_1200.json");
    }
    if (!resp.ok) {
      console.warn(`[app] characters_1200 not available (HTTP ${resp.status})`);
      return;
    }
    const data = await resp.json();
    const arr = Array.isArray(data.characters) ? data.characters : [];
    const map = Object.create(null);
    for (const row of arr) {
      const hz = row && row.hanzi != null ? String(row.hanzi).trim() : "";
      if (hz && map[hz] === undefined) map[hz] = row;
    }
    charCoreByHanzi = map;
    window._charCoreByHanzi = charCoreByHanzi;
    console.info(`[app] characters_1200 core loaded (${Object.keys(map).length} character(s))`);
  } catch (e) {
    console.warn("[app] characters_1200 load failed:", e);
  }
}

// ── §2.4 + §3.3 Hint cascade — Phase 6 ────────────────────────────────────
let hint_cascade_state = { level: 0, turn_uid: null };
let lastClickedWordId = null;
window.lastClickedWordId = null;
let _hanziToWordId = {};  // Phase 6 — reverse lookup hanzi → word_id

/** Pinyin + gloss from a full card JSON object. */
function _hintFromCardPayload(card) {
  if (!card?.content) return null;
  return {
    pinyin: card.content.headword?.pinyin || "",
    meaning: card.content.meaning || "",
  };
}

/** Native `title` / tooltip: prefer getWordHintData, then read card cache (covers race before index merge). */
function getInsightTitleForWordId(wid) {
  if (!wid) return "";
  const h = getWordHintData(wid);
  const a = [h.pinyin, h.meaning].filter((x) => x && String(x).trim());
  if (a.length) return a.join(" — ");
  const c = window._cardsByIdCache?.[wid];
  if (c?.content) {
    const py = c.content.headword?.pinyin;
    const mn = c.content.meaning;
    const b = [py, mn].filter((x) => x && String(x).trim());
    if (b.length) return b.join(" — ");
  }
  return "";
}

/**
 * Greedy longest-match hanzi → word_id (card_id), aligned with frame tokeniser / cards headwords.
 * Call after _cardsByIdCache is populated or extended.
 */
function rebuildHanziWordLookupFromCardsCache() {
  const cache = window._cardsByIdCache;
  if (!cache || typeof cache !== "object") {
    window._hanziLongestMatchMap = {};
    return;
  }
  const pairs = [];
  for (const [cid, card] of Object.entries(cache)) {
    if (typeof cid !== "string" || !cid.startsWith("w_")) continue;
    const hz = card?.content?.headword?.hanzi;
    if (typeof hz === "string" && hz.length > 0) pairs.push({ hz, wid: cid });
  }
  pairs.sort((a, b) => b.hz.length - a.hz.length || a.wid.localeCompare(b.wid));
  const map = Object.create(null);
  for (const { hz, wid } of pairs) {
    if (map[hz] === undefined) map[hz] = wid;
  }
  window._hanziLongestMatchMap = map;
}

/**
 * Tokenise option Hanzi like the active sentence: multi-character words first, then single CJK fallback.
 * @param {string} hanziStr
 * @param {{ card_id?: string }} opt
 * @returns {Array<{ t: string, word_id: string | null }>}
 */
function tokenizeHanziForOption(hanziStr, opt) {
  const text = hanziStr || "";
  const map = window._hanziLongestMatchMap || {};
  const keys = Object.keys(map);
  keys.sort((a, b) => b.length - a.length);
  let i = 0;
  const segments = [];
  while (i < text.length) {
    let matched = false;
    for (const hz of keys) {
      if (hz && text.startsWith(hz, i)) {
        segments.push({ t: hz, word_id: map[hz] });
        i += hz.length;
        matched = true;
        break;
      }
    }
    if (!matched) {
      const ch = [...text.slice(i)][0];
      if (!ch) break;
      const isCjk = /[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch);
      const wid = isCjk ? (_hanziToWordId[ch] || opt.card_id || null) : null;
      segments.push({ t: ch, word_id: wid });
      i += ch.length;
    }
  }
  return segments;
}

/**
 * Word-level hint content: last resolved card > cards_by_id cache > index object > tap option.
 * cards_index.by_word_id is usually word_id → card_id (string); we resolve gloss via _cardsByIdCache.
 */
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
  const cardIdFromIndex = typeof fromIndex === "string" ? fromIndex : null;
  const cache = window._cardsByIdCache;
  for (const cid of [cardIdFromIndex, wordId]) {
    if (!cid || !cache) continue;
    const fromCache = _hintFromCardPayload(cache[cid]);
    if (fromCache && (fromCache.pinyin || fromCache.meaning)) return fromCache;
  }
  const opt = window._tapOptions?.find(o => o.card_id === wordId);
  return opt ? { pinyin: opt.pinyin || "", meaning: opt.meaning || "" } : { pinyin: "", meaning: "" };
}

/** Single-Hanzi → word_id using cards cache (same as option tokeniser). */
function resolveWordIdForSingleHanziChar(ch) {
  const s = ch && String(ch).trim();
  if (!s || [...s].length !== 1) return null;
  const map = window._hanziLongestMatchMap || {};
  return map[s] || null;
}

/**
 * Pinyin + gloss for one composition row: prefer inline card fields, then content.characters, then lexicon (w_* card for that Hanzi).
 * Most cards leave word_composition.characters[].pinyin|meaning null — those are filled from the matching headword card.
 */
function resolveCharPinyinMeaning(cardContent, compChar, compIndex) {
  const ch = (compChar && (compChar.char || compChar.hanzi || "")).trim();
  const pick = (o) => {
    if (!o || typeof o !== "object") return { pinyin: "", meaning: "" };
    const py = o.pinyin != null && String(o.pinyin).trim() ? String(o.pinyin).trim() : "";
    const mn = o.meaning != null && String(o.meaning).trim() ? String(o.meaning).trim() : "";
    return { pinyin: py, meaning: mn };
  };
  const fromComp = pick(compChar);
  if (fromComp.pinyin || fromComp.meaning) return fromComp;

  const arr = cardContent && Array.isArray(cardContent.characters) ? cardContent.characters : null;
  if (arr && ch) {
    const byIndex = arr[compIndex];
    if (byIndex && String(byIndex.char || byIndex.hanzi || "").trim() === ch) {
      const p = pick(byIndex);
      if (p.pinyin || p.meaning) return p;
    }
    const byMatch = arr.find((x) => String(x.char || x.hanzi || "").trim() === ch);
    if (byMatch) {
      const p = pick(byMatch);
      if (p.pinyin || p.meaning) return p;
    }
  }

  const wid = resolveWordIdForSingleHanziChar(ch);
  if (wid) {
    const h = getWordHintData(wid);
    return {
      pinyin: (h.pinyin || "").trim(),
      meaning: (h.meaning || "").trim(),
    };
  }

  /** Author `characters_1200.json` fields (pinyin, gloss_en) — same file may hold thousands of rows at repo root. */
  const coreMap = window._charCoreByHanzi || charCoreByHanzi;
  const coreRow = ch && coreMap ? coreMap[ch] : null;
  if (coreRow && typeof coreRow === "object") {
    const cpy = coreRow.pinyin != null && String(coreRow.pinyin).trim() ? String(coreRow.pinyin).trim() : "";
    const cgloss = coreRow.gloss_en != null && String(coreRow.gloss_en).trim() ? String(coreRow.gloss_en).trim() : "";
    if (cpy || cgloss) return { pinyin: cpy, meaning: cgloss };
  }

  /** Multi-character headword on this card: align compact pinyin (e.g. zěnmeyàng) to each 字 — no single-char w_* card needed. */
  const hw = (cardContent?.headword?.hanzi || "").trim();
  const headPy = cardContent?.headword?.pinyin;
  const glyphs = [...hw];
  if (ch && hw && glyphs.length > 1 && glyphs[compIndex] === ch) {
    const per = splitHeadwordPinyinToGraphemes(hw, headPy);
    if (per && per[compIndex]) {
      const wm = (cardContent.meaning != null && String(cardContent.meaning).trim()) ? String(cardContent.meaning).trim() : "";
      return {
        pinyin: per[compIndex],
        meaning: wm ? `In “${hw}”: ${wm}` : `Part of “${hw}”.`,
      };
    }
  }

  return { pinyin: "", meaning: "" };
}

/** Word id to use for character-level etymology HTML: etymology index first, else same card map as gloss. */
function resolveWordIdForCharEtymology(ch) {
  const s = ch && String(ch).trim();
  if (!s) return null;
  return _hanziToWordId[s] || resolveWordIdForSingleHanziChar(s) || null;
}

/** Fallback English gloss for components when corpus/card omit gloss_en (curriculum-safe). */
const GLYPH_TEACHING_GLOSS_EN = {
  吃: "eat",
  喝: "drink",
  看: "look",
  见: "see",
  说: "speak",
  听: "listen",
  走: "walk",
  来: "come",
  去: "go",
  有: "have",
  没: "not have",
  不: "not",
  很: "very",
  吗: "(question particle)",
  呢: "(topic particle)",
  了: "(completed action)",
  的: "(modifier particle)",
  我: "I; me",
  你: "you",
  他: "he",
  她: "she",
  们: "(plural)",
  口: "mouth",
  女: "woman",
  子: "child",
  木: "tree; wood",
  水: "water",
  火: "fire",
  心: "heart; mind",
  手: "hand",
  足: "foot",
  目: "eye",
  人: "person",
  大: "big",
  小: "small",
  上: "up; on",
  下: "down",
  中: "middle",
  国: "country",
  学: "study",
  生: "life; born",
  先: "first",
  明: "bright",
  天: "day; sky",
  今: "today",
  昨: "yesterday",
  什: "what",
  么: "(particle)",
  怎: "how",
  样: "kind; appearance",
  好: "good",
  多: "many",
  少: "few",
  几: "how many",
  点: "point; o'clock",
  钟: "clock",
  气: "air; qi",
  雨: "rain",
  门: "door",
  问: "ask",
  题: "topic",
  工: "work",
  作: "do; make",
  名: "name",
  字: "character",
  爱: "love",
  喜: "happy",
  欢: "joy",
  北: "north",
  京: "capital",
  白: "white",
  菜: "dish; vegetable",
  饭: "rice; meal",
  茶: "tea",
  书: "book",
  车: "vehicle",
  飞: "fly",
  机: "machine",
  电: "electric",
  话: "speech",
  谢: "thanks",
  请: "please",
  对: "correct; to",
  起: "rise",
  早: "early",
  晚: "late",
  忙: "busy",
  累: "tired",
  饿: "hungry",
  冷: "cold",
  热: "hot",
  高: "tall",
  新: "new",
  旧: "old",
  快: "fast",
  慢: "slow",
  难: "difficult",
  易: "easy",
  想: "think; want",
  要: "want; need",
  会: "can; will",
  能: "can",
  可: "can; may",
  以: "by means of; in order to",
  所: "that which; place",
  因: "cause",
  为: "for; as",
  打: "hit; do",
  算: "count; plan",
  计: "plan",
  划: "draw; plan",
  最: "most",
  近: "near; recent",
  面: "face; side",
  过: "pass; experienced",
  乞: "beg (formal piece in some graphs)",
};

function cjkGraphemesFromString(hz) {
  return [...String(hz || "").trim()].filter((ch) => /[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch));
}

/** English gloss for one Hanzi: card headword → gloss_en → teaching map. */
function resolveGlyphGlossEn(glyph) {
  const g = glyph && String(glyph).trim();
  if (!g) return "";
  const wid = resolveWordIdForSingleHanziChar(g);
  if (wid) {
    const m = (getWordHintData(wid).meaning || "").trim();
    if (m) {
      const first = m.split(/[;；]/)[0].split(/[,，]/)[0].trim();
      return first.length > 56 ? `${first.slice(0, 53)}…` : first;
    }
  }
  const core = (window._charCoreByHanzi || charCoreByHanzi)?.[g];
  const ge = core?.gloss_en != null ? String(core.gloss_en).trim() : "";
  if (ge) {
    const seg = ge.split(/[;/]/)[0].trim();
    return seg.length > 56 ? `${seg.slice(0, 53)}…` : seg;
  }
  const rv = (window._radicalVariantGlossEn || {})[g];
  if (rv != null && String(rv).trim()) {
    const s = String(rv).trim();
    return s.length > 56 ? `${s.slice(0, 53)}…` : s;
  }
  const sup = (window._teachingSupplementGlossEn || {})[g];
  if (sup != null && String(sup).trim()) {
    const s = String(sup).trim();
    return s.length > 56 ? `${s.slice(0, 53)}…` : s;
  }
  return GLYPH_TEACHING_GLOSS_EN[g] || "";
}

/** e.g. 好 + 吃 → tasty (word-level “why this word”, not per-character IDS). */
function buildWordLevelCompositionExplainerHTML(wordId, cardContent) {
  const hw = (cardContent?.headword?.hanzi || "").trim();
  let wordMeaning =
    cardContent?.meaning != null && String(cardContent.meaning).trim()
      ? String(cardContent.meaning).trim()
      : "";
  if (!wordMeaning && wordId) {
    wordMeaning = (getWordHintData(wordId).meaning || "").trim();
    wordMeaning = wordMeaning.split(/[;；]/)[0].split(/[,，]/)[0].trim();
  }
  const glyphs = cjkGraphemesFromString(hw);
  if (glyphs.length < 2) return "";

  const glosses = glyphs.map((g) => resolveGlyphGlossEn(g));
  const usable = glosses.filter(Boolean);
  if (usable.length < 2) return "";

  const e = escapeHtmlForInsight;
  const joined = usable.join(" + ");
  const arrow = wordMeaning ? ` → ${e(wordMeaning)}` : "";
  return `<div class="etym-word-compositional"><p class="etym-origin">${e(joined)}${arrow}</p></div>`;
}

/** English line for radical + pieces (e.g. 吃 → mouth + …) from characters_1200 tree. */
function buildComponentEnglishGlossLine(hz) {
  const ch = hz && String(hz).trim();
  if (!ch) return "";
  const core = (window._charCoreByHanzi || charCoreByHanzi)?.[ch];
  if (!core || typeof core !== "object") return "";

  const bits = [];
  const radTxt = core.primary_radical ? _etymRadicalToText(core.primary_radical) : "";
  if (radTxt) bits.push(`Radical: ${radTxt}`);

  const args = core.decomposition_tree && Array.isArray(core.decomposition_tree.args) ? core.decomposition_tree.args : null;
  if (args && args.length) {
    const pieces = args
      .map((a) => {
        const c = a?.char;
        if (!c) return null;
        const g = resolveGlyphGlossEn(c);
        return g ? `${c} (${g})` : String(c);
      })
      .filter(Boolean);
    if (pieces.length) bits.push(`Form: ${pieces.join(" + ")}`);
  } else if (Array.isArray(core.components_flat) && core.components_flat.length) {
    const pieces = core.components_flat.map((c) => {
      const g = resolveGlyphGlossEn(c);
      return g ? `${c} (${g})` : String(c);
    });
    bits.push(`Form: ${pieces.join(" · ")}`);
  }

  const decompOnly = _etymDecompToText(core.decomposition);
  if (!bits.some((b) => /^Form:\s/i.test(b)) && decompOnly) {
    bits.push(`Form: ${decompOnly}`);
  }

  return bits.length ? bits.join(" · ") : "";
}

/** Whether a hint level has content (shared by getNextHintLevel and renderHintAffordance). */
function hintLevelHasContent(lvl, sentenceMode, sentenceHint, activeWordId) {
  if (lvl === 0) return false; // skip 0 so we don't land on "nothing" after Hide
  if (sentenceMode) {
    if (lvl === 1) return !!(sentenceHint.pinyin && String(sentenceHint.pinyin).trim());
    if (lvl === 2) return !!(sentenceHint.text_en && String(sentenceHint.text_en).trim());
    if (lvl === 3) return !!(sentenceHint.etymology && String(sentenceHint.etymology).trim());
    return true;
  }
  const goldWordId = window._tapOptions?.find(o => o.is_gold)?.card_id;
  const wordId = activeWordId || goldWordId;
  if (!wordId) return false;
  // Word / option: deeper exploration (etymology, parts) lives in the card panel after Open card — not under ?.
  if (lvl === 3) return false;
  const cardData = getWordHintData(wordId);
  if (lvl === 1) return !!(cardData.pinyin && String(cardData.pinyin).trim());
  if (lvl === 2) return !!(cardData.meaning && String(cardData.meaning).trim());
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
  if (level === 2) return "Hide hints \u2192";
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
      : (lvl) => lvl !== 3 && hintLevelHasContent(lvl, false, sentenceHint, activeWordId);
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
      if (optHintEtymology) {
        optHintEtymology.innerHTML = "";
        optHintEtymology.style.display = "none";
      }
      const hasContent = level >= 1 && (levelHasContent(1) || levelHasContent(2));
      optionHintBlock.style.setProperty("display", hasContent ? "block" : "none");
      optionHintBlock.setAttribute("aria-hidden", hasContent ? "false" : "true");
    }
    if (hintBtn) {
      const hasAny = levelHasContent(1) || levelHasContent(2);
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
    // Word in active sentence: use global hint rows only until the matching card is open — then hints live in the card panel.
    const goldWordId = window._tapOptions?.find(o => o.is_gold)?.card_id;
    const wordId = activeWordId || goldWordId;
    const container = document.getElementById("optionsContainer");
    container?.querySelectorAll(".option-hint-block").forEach((blk) => {
      blk.style.display = "none";
      blk.querySelectorAll(".option-hint-pinyin, .option-hint-meaning, .option-hint-etymology").forEach((el) => {
        el.textContent = ""; if (el.classList.contains("option-hint-etymology")) el.innerHTML = ""; el.style.display = "none";
      });
    });
    if (cardPanelCoversWordHints()) {
      if (hintPinyin) { hintPinyin.textContent = ""; hintPinyin.style.display = "none"; }
      if (hintMeaning) { hintMeaning.textContent = ""; hintMeaning.style.display = "none"; }
      if (hintEtymEl) { hintEtymEl.innerHTML = ""; hintEtymEl.style.display = "none"; }
      if (hintBtn) hintBtn.style.display = "none";
      return;
    }
    const cardData = getWordHintData(wordId);
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
      hintEtymEl.innerHTML = "";
      hintEtymEl.style.display = "none";
    }
    if (hintBtn) {
      const hasAny = levelHasContent(1) || levelHasContent(2);
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
    console.info(`[app] cards_index loaded`);
  } catch (e) {
    console.warn("[app] cards_index load failed:", e);
  }
}

/** Full card payloads for hint/popover text (cards_index only maps word_id → card_id string). */
async function loadCardsByIdBlob() {
  const path = "tools/cards/out/cards_by_id.json";
  try {
    const q = new URLSearchParams({ path });
    const resp = await fetch(`/api/cards?${q.toString()}`);
    if (!resp.ok) {
      console.warn(`[app] cards_by_id preload not available (HTTP ${resp.status})`);
      return;
    }
    const cards = await resp.json();
    window._cardsByIdCache = cards && typeof cards === "object" ? cards : {};
    rebuildHanziWordLookupFromCardsCache();
    console.info(`[app] cards_by_id cache primed (${Object.keys(window._cardsByIdCache).length} card(s))`);
  } catch (e) {
    console.warn("[app] cards_by_id preload failed:", e);
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
  // Phase 12C: overload signal — server uses this to reduce LOOP and prefer bridge
  window._recentConfusionCount = (window._recentConfusionCount || 0) + 1;

  // Phase 12B: first failure → soft pool (curious, not corrective). Falls back if pool empty.
  if (consecutive === 1) {
    const softPool = (data.phrases || []).filter((p) => (p.recovery_action || "") === "soft");
    if (softPool.length > 0) {
      const chosen = softPool[Math.floor(Math.random() * softPool.length)];
      return { id: chosen.id, hanzi: chosen.hanzi, pinyin: chosen.pinyin || "", text_en: chosen.text_en || "", etymology: chosen.etymology || "", recovery_action: "soft" };
    }
  }

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
  // Two passes: exact match first, then best partial match.
  // Partial match requires the option to be at least 2 characters so that single-character
  // vocabulary tiles (e.g. "你") don't absorb a longer utterance (e.g. "你好").
  let bestPartial = null;
  let bestPartialLen = 0;
  for (const opt of options) {
    const hanzi = (opt.hanzi || "").trim();
    if (!hanzi) continue;
    const optNorm = normalizeForMatch(hanzi);
    if (optNorm) {
      if (n === optNorm) return opt;                               // exact match wins immediately
      if (optNorm.length >= 2 && n.includes(optNorm) && optNorm.length > bestPartialLen) {
        bestPartial = opt; bestPartialLen = optNorm.length;        // transcript contains option
      }
      if (optNorm.length >= 2 && optNorm.includes(n) && optNorm.length > bestPartialLen) {
        bestPartial = opt; bestPartialLen = optNorm.length;        // option contains transcript
      }
    }
    const pinyin = (opt.pinyin || "").trim();
    if (pinyin) {
      const pyNorm = normalizeForMatch(pinyin);
      if (pyNorm) {
        if (n === pyNorm) return opt;
        if (pyNorm.length >= 2 && n.includes(pyNorm) && pyNorm.length > bestPartialLen) {
          bestPartial = opt; bestPartialLen = pyNorm.length;
        }
      }
    }
  }
  return bestPartial;
}

function isOpenEndedFrame(frameId) {
  const fid = (frameId || "").trim();
  return new Set([
    // Identity
    "f_ask_you_name", "p2_id_2", "p2_id_4", "p2_id_5", "f_ask_name_meaning",
    // Place — life-quality, local character, and leisure questions are all open
    "f_from_where", "frame.location.live_question",
    "p2_pl_1", "p2_pl_ext1", "p2_pl_3", "p2_pl_4",
    // Family — open questions that invite any free answer
    "f_have_family", "f_have_siblings", "p2_fa_1", "p2_fa_2", "p2_fa_5",
    // Work — retirement / job description can be anything
    "f_what_work", "f_like_work", "p2_wk_1", "p2_wk_2",
    // Hobby — "what are your hobbies" is inherently open
    "f_what_hobby", "f_often_do", "f_like_do_what", "f_weekend_do",
    "f_difficult_ma", "f_recommend_ma", "p2_hb_1", "p2_hb_2",
    // Food & travel
    "f_food_what_good", "f_travel_where", "f_want_go_where",
  ]).has(fid);
}

function isLikelyUnderstandableFreeAnswer(text, frameId = "") {
  const s = (text || "").trim();
  if (!s) return false;
  const fid = (frameId || "").trim();
  const zhMatches = s.match(/[\u4e00-\u9fff]/g) || [];
  const zhCount = zhMatches.length;
  const latinCount = (s.match(/[A-Za-z]/g) || []).length;
  // Too short in Chinese usually means we likely misheard.
  if (zhCount > 0 && zhCount < 2) return false;
  // Mixed-script is common for names in identity frames (e.g., Raymond).
  const identityOpen = new Set(["f_ask_you_name", "p2_id_2", "p2_id_4", "p2_id_5", "f_ask_name_meaning"]).has(fid);
  if (!identityOpen && latinCount > zhCount + 2) return false;
  // Repeated single word noise (e.g., 牛肉牛肉牛肉) should trigger repair.
  const norm = s.replace(/[，。！？、\s]/g, "");
  if (norm.length >= 4) {
    const half = Math.floor(norm.length / 2);
    if (half > 0 && norm.slice(0, half) === norm.slice(half)) return false;
  }
  return s.length >= 2;
}

function semanticSoftMatch(transcript, frameId) {
  const t = (transcript || "").trim();
  const fid = (frameId || "").trim();
  if (!t) return false;
  // Turn-around / reciprocity phrases — always accept regardless of the current frame.
  // ASR rarely captures the trailing "？" so match without it.
  // Matches: standalone "你呢", leading "你呢…", AND trailing "[answer]，你呢" compound answers.
  if (/^(那?你呢|你怎么想|为什么这么问|为什么这样问|换我问|那你|你来问)/.test(t) || t === "你呢") return true;
  if (/[，。！]?(那?你呢|你怎么想|为什么这么问)[？?]?$/.test(t)) return true;
  // Direct questions aimed at the partner — user turns the conversation around by
  // asking the app about its origin, city, job, hobbies, or family.
  if (/你(是哪里人|从哪里来|老家在哪|住(在哪|哪里|的地方)|做什么工作|的工作|是做什么|喜欢(什么|做什么)|有什么爱好|有家人|有没有家人)/.test(t)) return true;
  // Identity nickname question: allow "大家叫我Raymond" style free answers.
  if (fid === "p2_id_2") {
    if (t.includes("叫我") || t.includes("大家叫")) return true;
    const hasZh = /[\u4e00-\u9fff]/.test(t);
    const hasLatin = /[A-Za-z]/.test(t);
    if (hasZh && hasLatin) return true;
  }
  // Famous dish: accept concrete food nouns and valid "don't know/no famous dish" replies.
  if (fid === "f_food_famous_dish") {
    if (/汉堡|牛肉|羊肉|火锅|饺子|面|米饭|烤|汤|鱼|鸡|菜/.test(t)) return true;
    if (/不知道|没有|不清楚/.test(t)) return true;
  }
  // Family frequency: accept natural free responses about seeing family.
  if (fid === "p2_fa_2") {
    if (/(家人|妈妈|爸爸|父母)/.test(t) && /(天|周|月|常|每天|经常|周末)/.test(t)) return true;
  }
  // Work "why like this job": accept reason-like content.
  if (fid === "p2_wk_1") {
    if (/(因为|为了|可以|能|学|帮助|工资|时间|喜欢)/.test(t)) return true;
  }
  return false;
}

function shouldAcceptUnmatchedFreeAnswer(transcript, options, frameId, unmatchedCount) {
  const opts = Array.isArray(options) ? options : [];
  if (opts.length === 0) return true;
  if (isOpenEndedFrame(frameId)) return isLikelyUnderstandableFreeAnswer(transcript, frameId);
  // If this turn is mostly closed options, be stricter and prefer repair on unmatched speech.
  const hasStructuredSlots = opts.some((o) => (o?.kind || "").toUpperCase() === "FRAME_WITH_SLOTS");
  if (hasStructuredSlots) return isLikelyUnderstandableFreeAnswer(transcript, frameId);
  // Semantic soft-match for selected closed frames.
  if (semanticSoftMatch(transcript, frameId)) return true;
  // Two-strike graceful fallback: avoid endless "not understood" loop when answer is substantive.
  if ((unmatchedCount || 0) >= 2 && isLikelyUnderstandableFreeAnswer(transcript, frameId)) return true;
  return false;
}

function classifyUnmatchedFreeAnswerDecision(transcript, options, frameId, unmatchedCount) {
  const opts = Array.isArray(options) ? options : [];
  const hasStructuredSlots = opts.some((o) => (o?.kind || "").toUpperCase() === "FRAME_WITH_SLOTS");
  const openEnded = isOpenEndedFrame(frameId);
  const understandable = isLikelyUnderstandableFreeAnswer(transcript, frameId);
  const semantic = semanticSoftMatch(transcript, frameId);
  // Learner skip signal: "我不懂" / "不明白" → advance gracefully without repair loop
  if (/不懂|不明白/.test(transcript || "")) return { accept: true, reason: "learner_skip_signal" };
  if (opts.length === 0) return { accept: true, reason: "no_options" };
  if (semantic) return { accept: true, reason: "semantic_soft_match" };
  // One-strike fallback: after one repair attempt, accept any substantive Chinese answer
  if ((unmatchedCount || 0) >= 1 && understandable) return { accept: true, reason: "one_strike_substantive_fallback" };
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
      span.className = "tok tok-word word-insight-token";
      span.dataset.kind = "word";
      if (seg.word_id) span.dataset.wordId = seg.word_id;
      span.dataset.insightSource = "active_sentence";
      span.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (seg.word_id) {
          lastClickedWordId = seg.word_id;
          window.lastClickedWordId = seg.word_id;
          _openWordInsightPopover(span, seg.word_id, seg.t || "", "active_sentence");
          if (_shouldAlsoOpenCardPanel()) await _openCardForWordId(seg.word_id);
        } else {
          lastClickedWordId = null;
          window.lastClickedWordId = null;
          _openWordInsightPopover(span, null, seg.t || "", "active_sentence");
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
      span.className = "tok tok-word word-insight-token";
      span.dataset.kind = "word";
      span.dataset.insightSource = "active_sentence";
      span.addEventListener("click", (e) => {
        e.stopPropagation();
        lastClickedWordId = null;
        window.lastClickedWordId = null;
        _openWordInsightPopover(span, null, char, "active_sentence");
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

  // Phase 7.4: every token has string `kind`. Phase 6 uses `t` as type ("word"|"lit") without `kind`.
  const isNewSchema = rawTokens.length > 0 && rawTokens.every((t) => t && typeof t.kind === "string");

  rawTokens.forEach((tok) => {
    const span = document.createElement("span");

    if (isNewSchema) {
      // ── Phase 7.4 schema ──
      const wordId74 = tok.word_id ?? tok.id ?? null;
      span.textContent          = tok.t;
      span.dataset.kind         = tok.kind;
      span.dataset.text         = tok.t;
      if (frame?.id)    span.dataset.frameId  = frame.id;
      if (wordId74)     span.dataset.wordId   = wordId74;
      if (tok.slot_name) span.dataset.slotName = tok.slot_name;

      if (tok.kind === "word" && wordId74) {
        span.className = "tok tok-word word-insight-token";
        span.dataset.insightSource = "active_sentence";
        const hd = getWordHintData(wordId74);
        if (hd.pinyin || hd.meaning) span.title = [hd.pinyin, hd.meaning].filter(Boolean).join(" — ");
        span.addEventListener("click", async (e) => {
          e.stopPropagation();
          lastClickedWordId        = wordId74;
          window.lastClickedWordId = lastClickedWordId;
          _openWordInsightPopover(span, wordId74, tok.t, "active_sentence");
          const turnUid = window._currentTurnUid || frame?.id || "";
          hint_cascade_state = { level: 1, turn_uid: turnUid };
          renderHintAffordance({ ...(window._currentHintAffordance || {}), visible: true }, turnUid, "tap");
          if (_shouldAlsoOpenCardPanel()) await _openCardForWordId(wordId74);
        });
      } else if (tok.kind === "word") {
        // Unknown word — no word_id
        span.className = "tok tok-word tok-word-unknown word-insight-token";
        span.dataset.insightSource = "active_sentence";
        span.addEventListener("click", (e) => {
          e.stopPropagation();
          _openWordInsightPopover(span, null, tok.t, "active_sentence");
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
        span.className    = "frame-word-token word-insight-token";
        span.style.cursor = "pointer";
        span.dataset.insightSource = "active_sentence";
        const hd = tok.id ? getWordHintData(tok.id) : {};
        if (hd.pinyin || hd.meaning) span.title = [hd.pinyin, hd.meaning].filter(Boolean).join(" — ");
        else span.title = tok.id || "";
        span.addEventListener("click", async () => {
          lastClickedWordId        = tok.id;
          window.lastClickedWordId = lastClickedWordId;
          const turnUid = window._currentTurnUid || frame?.id || "";
          hint_cascade_state = { level: 1, turn_uid: turnUid };
          renderHintAffordance({ ...(window._currentHintAffordance || {}), visible: true }, turnUid, "tap");
          _openWordInsightPopover(span, tok.id, span.textContent, "active_sentence");
          const cardId = cardsIndex?.by_word_id?.[tok.id];
          if (!cardId) {
            console.warn(`[app] renderFrameSentence: no card_id for word_id '${tok.id}'`);
            return;
          }
          if (_shouldAlsoOpenCardPanel()) {
            emitUITrace({
              type: "OPEN_CARD", timestamp: new Date().toISOString(),
              payload: { frame_id: frame?.id, card_id: cardId, reason: "card_available" }
            });
            dispatch({ type: "OPEN_CARD", payload: { card_id: cardId } });
            await resolveCard(cardId, "tools/cards/out/cards_by_id.json");
          }
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
/** Strip internal corpus disclaimer; keep learner-facing copy uncluttered. */
function scrubStructuralEtymologyDisclaimer(text) {
  if (text == null) return "";
  let t = String(text).trim();
  if (!t) return "";
  const disclaim =
    "Derived structural metadata only. No historical etymology asserted.";
  const re = new RegExp(disclaim.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*", "gi");
  t = t.replace(re, "").trim();
  return t.replace(/^[,;.\s—-]+|[,;.\s—-]+$/g, "").trim();
}

/**
 * Inferred narratives often prefix with “High-frequency lexicalized…”. Learners only need the
 * short core line when present, e.g. “Core sense/role: good.”
 */
function simplifyInferredNarrativeForLearner(text) {
  if (text == null) return "";
  const t = String(text).trim();
  if (!t) return "";
  const re = /(core\s*sense\/role\s*:\s*[^.]+)(\.|$)/i;
  const m = t.match(re);
  if (m) {
    let s = m[1].trim();
    if (!s.endsWith(".")) s += ".";
    return s;
  }
  return t;
}

/** Normalize radical field: runtime / JSON may use string or `{ glyph, meaning_en }`. */
function _etymRadicalToText(r) {
  if (r == null || r === "") return "";
  if (typeof r === "string") return r.trim();
  if (typeof r === "object") {
    const g = r.glyph != null ? String(r.glyph).trim() : "";
    const m = r.meaning_en != null ? String(r.meaning_en).trim() : "";
    if (g && m) return `${g} (${m})`;
    return g || m;
  }
  return String(r);
}

/** Normalize decomposition: string or `{ type, components: [] }` from characters_1200. */
function _etymDecompToText(d) {
  if (d == null || d === "") return "";
  if (typeof d === "string") return d.trim();
  if (typeof d === "object" && Array.isArray(d.components)) {
    return d.components.filter(Boolean).join(" + ");
  }
  if (typeof d === "object" && d.type) return String(d.type);
  return "";
}

/** One character block from `characters_1200` (no outer etym-word wrapper). */
function buildCharacterCoreInsightInnerHTML(hanzi) {
  const map = window._charCoreByHanzi || charCoreByHanzi;
  const ch = hanzi && String(hanzi).trim();
  if (!ch || !map) return null;
  const entry = map[ch];
  if (!entry || typeof entry !== "object") return null;
  const rad = _etymRadicalToText(entry.primary_radical);
  const decomp = _etymDecompToText(entry.decomposition);
  const origin = scrubStructuralEtymologyDisclaimer(
    entry.etymology?.origin_note ? String(entry.etymology.origin_note).trim() : ""
  );
  const story = entry.mnemonic?.story ? String(entry.mnemonic.story).trim() : "";
  const disclaim = entry.mnemonic?.disclaimer ? String(entry.mnemonic.disclaimer).trim() : "";
  let compLine = buildComponentEnglishGlossLine(ch);
  if (!compLine && decomp) compLine = `Form: ${decomp}`;
  if (!rad && !origin && !story && !compLine) return null;
  let html = `<div class="etym-char char-core-insight"><span class="etym-hanzi">${ch}</span>`;
  if (rad) html += `<span class="etym-radical">Radical: ${rad}</span>`;
  if (compLine) {
    html += `<span class="etym-components-en">${escapeHtmlForInsight(compLine)}</span>`;
  }
  if (origin) html += `<span class="etym-origin">${origin}</span>`;
  if (story) html += `<span class="etym-mnemonic">${story}</span>`;
  if (disclaim) html += `<span class="etym-disclaimer">${disclaim}</span>`;
  html += `</div>`;
  return html;
}

function buildCharacterCoreInsightHTML(hanzi) {
  const inner = buildCharacterCoreInsightInnerHTML(hanzi);
  return inner ? `<div class="etym-word">${inner}</div>` : null;
}

/** Multi-character headword: stack per-glyph core rows when runtime word etymology is missing. */
function buildAggregatedCharCoreHTML(headwordHanzi) {
  const hz = (headwordHanzi || "").trim();
  if (!hz) return null;
  const parts = [];
  for (const grapheme of hz) {
    const inner = buildCharacterCoreInsightInnerHTML(grapheme);
    if (inner) parts.push(inner);
  }
  if (!parts.length) return null;
  return `<div class="etym-word">${parts.join("")}</div>`;
}

/**
 * Chip “deep” step: prefer runtime row for this glyph under the **open card’s** word_id (e.g. 样 inside 怎么样),
 * then standalone w_* for that Hanzi, else characters_1200.
 */
function buildCharDeepHintHTML(hanzi, openWordId) {
  const ch = hanzi && String(hanzi).trim();
  if (!ch) return null;

  const ow = openWordId != null ? String(openWordId).trim() : "";
  if (ow && wordEtymologyIndex[ow]) {
    const entry = wordEtymologyIndex[ow];
    const row = (entry.characters || []).find((r) => String(r?.char || "").trim() === ch);
    if (row) {
      const inner = formatWordEtymologyCharRecordHtml(row);
      if (inner) return `<div class="etym-word">${inner}</div>`;
    }
  }

  const wid = resolveWordIdForCharEtymology(ch);
  if (wid) {
    const fromRuntime = buildEtymologyHTML(wid);
    if (fromRuntime) return fromRuntime;
  }
  return buildCharacterCoreInsightHTML(ch);
}

function escapeHtmlForInsight(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * No characters_1200 / word_etymology row for this glyph: explain syllable + word context from the open card headword.
 */
function buildCharGlyphFallbackHTML(cardContent, chText, charIndex) {
  const hz = (cardContent?.headword?.hanzi || "").trim();
  const mean =
    cardContent?.meaning != null && String(cardContent.meaning).trim()
      ? String(cardContent.meaning).trim()
      : "";
  const pyFull =
    cardContent?.headword?.pinyin != null && String(cardContent.headword.pinyin).trim()
      ? String(cardContent.headword.pinyin).trim()
      : "";
  const ch = (chText || "").trim();
  if (!hz || ![...hz].includes(ch)) return null;
  const per = splitHeadwordPinyinToGraphemes(hz, pyFull);
  const pyOne = per && charIndex >= 0 && per[charIndex] ? per[charIndex] : "";
  const e = escapeHtmlForInsight;
  let body = `This character appears in <strong>${e(hz)}</strong>`;
  if (pyFull) body += ` (${e(pyFull)})`;
  if (pyOne) body += ` — syllable for this glyph: <strong>${e(pyOne)}</strong>`;
  if (mean) body += `. Gloss for the whole word: ${e(mean)}`;
  body += `. No row yet for this glyph under this word in <code>word_etymology.runtime.json</code> (run <code>tools/build_runtime_artifacts.py</code> after <code>word_character_links.json</code> + <code>characters_1200.json</code> include it), and no Hanzi match in the loaded character corpus.`;
  return `<div class="etym-word"><div class="etym-char char-glyph-fallback"><span class="etym-hanzi">${e(ch)}</span><span class="etym-origin">${body}</span></div></div>`;
}

/**
 * Word-level “Show word …” block: for multi-character words prefer compositional gloss (好 + 吃 → tasty)
 * plus optional curated narrative — not a repeat of per-character chip breakdown.
 */
function buildEtymologyWordPanelHTML(wordId, headwordHanzi, cardContent) {
  const entry = wordId && wordEtymologyIndex[wordId];
  const narr = entry ? buildWordNarrativeSectionHTML(entry.word_narrative) : "";
  const compExpl = buildWordLevelCompositionExplainerHTML(wordId, cardContent || {});
  const glyphs = cjkGraphemesFromString(headwordHanzi || "");
  const multi = glyphs.length >= 2;

  if (multi && compExpl) {
    const body = `${narr}${compExpl}`;
    return body ? `<div class="etym-word">${body}</div>` : null;
  }

  const runtimeFull = wordId ? buildEtymologyHTML(wordId) : null;
  if (runtimeFull) return runtimeFull;
  return buildAggregatedCharCoreHTML(headwordHanzi || "");
}

/** Word-level card etymology (Explore word panel). */
function buildCardPanelWordEtymologyHTML(wordId, headwordHanzi, cardContent) {
  if (!wordId && !headwordHanzi) return null;
  return buildEtymologyWordPanelHTML(wordId, headwordHanzi, cardContent);
}

/** Curated inferred narrative block (merged at build from data/word_etymology_top1000_…). */
function buildWordNarrativeSectionHTML(wordNarrative) {
  if (!wordNarrative || !wordNarrative.etymology) return "";
  const et = wordNarrative.etymology;
  let ex = et.explanation_en != null ? String(et.explanation_en).trim() : "";
  ex = simplifyInferredNarrativeForLearner(ex);
  if (!ex) return "";
  const mag = escapeHtmlForInsight;
  let h = `<div class="etym-word-narrative">`;
  h += `<span class="etym-origin">${mag(ex)}</span>`;
  h += `</div>`;
  return h;
}

/**
 * One character row from word_etymology.runtime.json (structural fields + optional glyph_narrative).
 */
function formatWordEtymologyCharRecordHtml(ch) {
  if (!ch || !ch.char) return "";
  const e = escapeHtmlForInsight;
  const hz = String(ch.char).trim();
  const map = window._charCoreByHanzi || charCoreByHanzi;
  const core = map && map[hz] && typeof map[hz] === "object" ? map[hz] : null;

  let rad =
    ch.radical != null && ch.radical !== "" ? _etymRadicalToText(ch.radical) : "";
  if (!rad && core) rad = _etymRadicalToText(core.primary_radical);

  let decomp = _etymDecompToText(ch.decomposition);
  if (!decomp && core) {
    decomp = _etymDecompToText(core.decomposition);
    if (!decomp && Array.isArray(core.components_flat) && core.components_flat.length) {
      decomp = core.components_flat.filter(Boolean).join(" · ");
    }
  }

  const et = ch.etymology;
  let structNote = "";
  if (et && typeof et === "object") {
    structNote = scrubStructuralEtymologyDisclaimer(
      et.origin_note ? String(et.origin_note).trim() : ""
    );
    if (!structNote && et.explanation_en) {
      structNote = scrubStructuralEtymologyDisclaimer(String(et.explanation_en).trim());
    }
  }
  const gn = ch.glyph_narrative;
  let usageNote = "";
  if (gn && gn.etymology && gn.etymology.explanation_en) {
    usageNote = simplifyInferredNarrativeForLearner(String(gn.etymology.explanation_en).trim());
  }
  if (structNote) structNote = simplifyInferredNarrativeForLearner(structNote);

  let compEn = buildComponentEnglishGlossLine(hz);
  if (!compEn && decomp) compEn = `Form: ${decomp}`;

  if (!rad && !structNote && !usageNote && !compEn) return "";

  let html = `<div class="etym-char char-runtime-insight"><span class="etym-hanzi">${e(hz)}</span>`;
  if (rad) html += `<span class="etym-radical">Radical: ${e(rad)}</span>`;
  if (compEn) html += `<span class="etym-components-en">${e(compEn)}</span>`;
  if (structNote) html += `<span class="etym-structure">${e(structNote)}</span>`;
  if (usageNote) html += `<span class="etym-usage-narrative">${e(usageNote)}</span>`;
  html += `</div>`;
  return html;
}

/** Returns HTML string for word etymology, or null if none. Card_id equals word_id in our data. */
function buildEtymologyHTML(wordId) {
  if (!wordId || !wordEtymologyIndex[wordId]) return null;
  const entry = wordEtymologyIndex[wordId];
  const narr = buildWordNarrativeSectionHTML(entry.word_narrative);
  const parts = (entry.characters || [])
    .map((ch) => formatWordEtymologyCharRecordHtml(ch))
    .filter(Boolean)
    .join("");
  if (!narr && !parts) return null;
  const body = `${narr}<div class="etym-under-chars">${parts}</div>`;
  return `<div class="etym-word">${body}</div>`;
}

/** While this word’s card is open, hide global ? rows — progressive hints are in the card. */
function cardPanelCoversWordHints() {
  try {
    if (!state?.isOpen || !state.activeCardId) return false;
    const wid = window.lastClickedWordId;
    if (!wid || String(wid).startsWith("__opt_")) return false;
    return resolveOpenableCardId(wid) === state.activeCardId;
  } catch (e) {
    return false;
  }
}

/** Ordered blocks after headword: word story sits under pinyin + gloss, then character chips. */
function buildCardRevealExtras(cardContent, activeCardId) {
  const extras = [];
  const py = cardContent.headword?.pinyin;
  if (py && String(py).trim()) extras.push({ key: "pinyin" });
  const mean = cardContent.meaning;
  if (mean && String(mean).trim()) extras.push({ key: "meaning" });
  const hw = cardContent.headword?.hanzi || "";
  if (buildCardPanelWordEtymologyHTML(activeCardId, hw, cardContent)) extras.push({ key: "etymology" });
  const comp = cardContent.word_composition?.characters;
  if (comp && comp.length) extras.push({ key: "composition", chars: comp });
  return extras;
}

function syncCardRevealUiForCard(activeCardId) {
  if (activeCardId !== _cardRevealCardId) {
    _cardRevealCardId = activeCardId;
    _cardExtrasVisible = 0;
    _cardCharFocusIdx = null;
    _cardCharPhase = 0;
  }
}

function nextCardRevealButtonLabel(extras, visible) {
  if (visible >= extras.length) return "Reset hints";
  const nx = extras[visible];
  if (nx.key === "pinyin") return "Show pinyin →";
  if (nx.key === "meaning") return "Show meaning →";
  if (nx.key === "etymology") return "Show word story →";
  if (nx.key === "composition") return "Show characters →";
  return "Next →";
}
// ── end Phase 6 ────────────────────────────────────────────────────────────

function dispatch(action) {
  state = reduce(state, action);
  render();
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
    const titleText = (state.activeCard && state.activeCard.title) || "";
    while (cardTitle.firstChild) cardTitle.removeChild(cardTitle.firstChild);
    if (titleText) cardTitle.appendChild(document.createTextNode(titleText));

    const activeCardId = state.activeCardId || "";
    syncCardRevealUiForCard(activeCardId);

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

    const extras = buildCardRevealExtras(cardContent, activeCardId);
    const maxExtras = extras.length;

    clearEl(cardBody);

    const mainDisplayDiv = document.createElement("div");
    mainDisplayDiv.className = "card-main";

    const toolbar = document.createElement("div");
    toolbar.className = "card-panel-toolbar";
    const toolbarLeft = document.createElement("div");
    toolbarLeft.className = "card-toolbar-left";
    if (maxExtras > 0) {
      const nextHintBtn = document.createElement("button");
      nextHintBtn.type = "button";
      nextHintBtn.className = "card-inhint-next";
      nextHintBtn.textContent = nextCardRevealButtonLabel(extras, _cardExtrasVisible);
      nextHintBtn.title =
        "Reveal the next level (pinyin → English → word story under those → character chips). Then Reset.";
      nextHintBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (_cardExtrasVisible >= maxExtras) {
          _cardExtrasVisible = 0;
          _cardCharFocusIdx = null;
          _cardCharPhase = 0;
        } else {
          _cardExtrasVisible += 1;
        }
        render();
      });
      toolbarLeft.appendChild(nextHintBtn);
    }
    toolbar.appendChild(toolbarLeft);
    const closePanelBtn = document.createElement("button");
    closePanelBtn.type = "button";
    closePanelBtn.className = "card-close-btn";
    closePanelBtn.setAttribute("aria-label", "Close panel");
    closePanelBtn.title = "Close";
    closePanelBtn.textContent = "✕";
    closePanelBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      dispatch({ type: "CARD_PANEL_CLOSED" });
    });
    toolbar.appendChild(closePanelBtn);
    mainDisplayDiv.appendChild(toolbar);

    if (headwordHanzi) {
      const headRow = document.createElement("div");
      headRow.className = "card-headword-row";
      headRow.appendChild(makeDiv("card-main-hanzi", headwordHanzi));
      const headSpeak = document.createElement("button");
      headSpeak.type = "button";
      headSpeak.className = "card-headword-speak";
      headSpeak.setAttribute("aria-label", "Play word");
      headSpeak.title = "Play word";
      headSpeak.textContent = "🔊";
      headSpeak.addEventListener("click", (e) => {
        e.stopPropagation();
        const cardId = state.activeCardId || "unknown_card";
        const utterance_id = `card:${cardId}:word`;
        emitUITrace({
          type: "AUDIO_PLAY_REQUESTED",
          timestamp: new Date().toISOString(),
          payload: { utterance_id, text: headwordHanzi, source: "card_headword" },
        });
        ttsSpeak({
          text: headwordHanzi,
          lang: "zh-CN",
          utterance_id,
          onEvent: (traceEntry) => emitUITrace(traceEntry),
        });
      });
      headRow.appendChild(headSpeak);
      mainDisplayDiv.appendChild(headRow);
    }

    for (let i = 0; i < _cardExtrasVisible && i < extras.length; i++) {
      const ex = extras[i];
      if (ex.key === "pinyin" && pinyin) mainDisplayDiv.appendChild(makeDiv("card-main-pinyin", pinyin));
      else if (ex.key === "meaning" && meaning) mainDisplayDiv.appendChild(makeDiv("card-main-meaning", meaning));
      else if (ex.key === "composition" && ex.chars && ex.chars.length) {
        const compWrap = makeDiv("card-composition", "");
        const row = document.createElement("div");
        row.className = "card-composition-row";
        ex.chars.forEach((c, idx) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "char-chip" + (_cardCharFocusIdx === idx ? " char-chip-focus" : "");
          const chSurface = c.char || c.hanzi || "";
          btn.textContent = chSurface;
          btn.disabled = !btn.textContent;
          btn.addEventListener("click", (ev) => {
            ev.stopPropagation();
            const cardId = state.activeCardId || "unknown_card";
            const utteranceId = `card:${cardId}:char:${idx}`;
            if (_cardCharFocusIdx !== idx) {
              _cardCharFocusIdx = idx;
              _cardCharPhase = 1;
              emitUITrace({
                type: "AUDIO_PLAY_REQUESTED",
                timestamp: new Date().toISOString(),
                payload: { utterance_id: utteranceId, text: chSurface, source: "card_composition_char" },
              });
              ttsSpeak({
                text: chSurface,
                lang: "zh-CN",
                utterance_id: utteranceId,
                onEvent: (traceEntry) => emitUITrace(traceEntry),
              });
            } else {
              // Phases 1→2→3 = pinyin → +gloss → +character form. Avoid %4→0, which cleared focus on the 4th tap
              // (users expected a 4th “level”, but got reset). After 3, cycle back to 1 + replay TTS.
              if (_cardCharPhase >= 3) {
                _cardCharPhase = 1;
                emitUITrace({
                  type: "AUDIO_PLAY_REQUESTED",
                  timestamp: new Date().toISOString(),
                  payload: { utterance_id: utteranceId, text: chSurface, source: "card_composition_char" },
                });
                ttsSpeak({
                  text: chSurface,
                  lang: "zh-CN",
                  utterance_id: utteranceId,
                  onEvent: (traceEntry) => emitUITrace(traceEntry),
                });
              } else {
                _cardCharPhase += 1;
              }
            }
            render();
          });
          row.appendChild(btn);
        });
        compWrap.appendChild(row);

        const det = document.createElement("div");
        det.className = "card-char-detail";
        if (_cardCharFocusIdx == null) {
          det.textContent = "click character to explore";
        } else if (_cardCharPhase === 0) {
          det.textContent = "click character to explore";
        } else {
          const c = ex.chars[_cardCharFocusIdx];
          const chText = (c?.char || c?.hanzi || "").trim();
          const reading = resolveCharPinyinMeaning(cardContent, c, _cardCharFocusIdx);
          if (_cardCharPhase >= 1) {
            const pyLine = document.createElement("div");
            pyLine.className = "card-char-detail-py";
            pyLine.textContent = reading.pinyin || "—";
            det.appendChild(pyLine);
          }
          if (_cardCharPhase >= 2) {
            const mnLine = document.createElement("div");
            mnLine.className = "card-char-detail-mean";
            mnLine.textContent = reading.meaning || "—";
            det.appendChild(mnLine);
          }
          if (_cardCharPhase >= 3) {
            const et =
              buildCharDeepHintHTML(chText, activeCardId) ||
              buildCharGlyphFallbackHTML(cardContent, chText, _cardCharFocusIdx);
            if (et) {
              const etDiv = document.createElement("div");
              etDiv.className = "card-char-detail-etym";
              etDiv.innerHTML = et;
              det.appendChild(etDiv);
            } else {
              const miss = document.createElement("div");
              miss.className = "card-char-detail-etym card-char-detail-etym-empty";
              miss.textContent =
                "No breakdown or word context available for this glyph.";
              det.appendChild(miss);
            }
          }
        }
        compWrap.appendChild(det);

        const hint = document.createElement("div");
        hint.className = "card-composition-hint";
        hint.innerHTML =
          "<em>Same character: pinyin → gloss → structure. Next tap returns to pinyin (focus stays).</em>";
        compWrap.appendChild(hint);

        mainDisplayDiv.appendChild(compWrap);
      } else if (ex.key === "etymology") {
        const etHTML = buildCardPanelWordEtymologyHTML(activeCardId, headwordHanzi, cardContent);
        if (etHTML) {
          const ew = document.createElement("div");
          ew.className = "card-etymology card-etymology-revealed";
          const inner = document.createElement("div");
          inner.className = "card-etymology-content";
          inner.innerHTML = etHTML;
          ew.appendChild(inner);
          mainDisplayDiv.appendChild(ew);
        }
      }
    }

    cardBody.appendChild(mainDisplayDiv);

    const compCharsForSkip = cardContent.word_composition?.characters;
    const skipModeledOpts =
      state.panelOptions &&
      /^\s*characters\b/i.test(String(state.panelOptions.section_title || "").trim()) &&
      Array.isArray(compCharsForSkip) &&
      compCharsForSkip.length > 0;
    if (!skipModeledOpts) {
      renderModeledOptions(cardBody, state.panelOptions, state);
    }

  } else {
    cardPanel.classList.add("hidden");
    noCard.style.display = "block";
    cardError.textContent = "";
    cardTitle.textContent = "";
    cardBody.textContent = "";
    _cardRevealCardId = null;
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
    if (cards && typeof cards === "object") {
      window._cardsByIdCache = window._cardsByIdCache || {};
      Object.assign(window._cardsByIdCache, cards);
      rebuildHanziWordLookupFromCardsCache();
    }
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

// ── Phase 11C: Persona layer ──────────────────────────────────────────────────
async function loadPersonas() {
  try {
    const res = await fetch("/api/personas");
    if (!res.ok) return;
    const data = await res.json();
    const personas = data.personas || [];
    const btns = document.getElementById("personaBtns");
    if (!btns) return;
    btns.innerHTML = "";

    const noneBtn = document.createElement("button");
    noneBtn.className = "persona-btn-none" + (!window._partnerId ? " active" : "");
    noneBtn.textContent = "No partner";
    noneBtn.addEventListener("click", () => {
      window._partnerId = null;
      window._revealedVoiceLines = {};
      window._revealedPartnerFacts = {};
      _updatePersonaBtnState();
      _updatePartnerHeader("", "", "");
    });
    btns.appendChild(noneBtn);

    personas.forEach((p) => {
      const btn = document.createElement("button");
      btn.className = "persona-btn" + (window._partnerId === p.id ? " active" : "");
      btn.textContent = p.display_name;
      btn.title = [p.name_pinyin, p.description].filter(Boolean).join(" — ");
      btn.dataset.personaId = p.id;
      btn.addEventListener("click", () => {
        if (window._partnerId !== p.id) {
          // Switching to a different partner resets per-engine reveal history
          window._revealedVoiceLines = {};
          window._revealedPartnerFacts = {};
          _updatePartnerHeader("", "", "");
        }
        window._partnerId = p.id;
        _updatePersonaBtnState();
      });
      btns.appendChild(btn);
    });
  } catch (e) {
    console.warn("[app] loadPersonas failed:", e);
  }
}

function _updatePersonaBtnState() {
  const btns = document.getElementById("personaBtns");
  if (!btns) return;
  btns.querySelectorAll(".persona-btn-none").forEach((b) =>
    b.classList.toggle("active", !window._partnerId)
  );
  btns.querySelectorAll(".persona-btn[data-persona-id]").forEach((b) =>
    b.classList.toggle("active", b.dataset.personaId === window._partnerId)
  );
}

function _updatePartnerHeader(partnerName, partnerPrefix, partnerFact) {
  const header = document.getElementById("partnerHeader");
  const nameLabel = document.getElementById("partnerNameLabel");
  const prefixLine = document.getElementById("partnerPrefixLine");
  const factLine = document.getElementById("partnerFactLine");
  if (!header || !nameLabel || !prefixLine) return;
  if (partnerName) {
    nameLabel.textContent = `${partnerName}:`;
    prefixLine.textContent = partnerPrefix || "";
    header.style.display = "flex";
  } else {
    header.style.display = "none";
  }
  if (factLine) {
    if (partnerFact) {
      factLine.textContent = partnerFact;
      factLine.style.display = "";
    } else {
      factLine.style.display = "none";
    }
  }
}
// ─────────────────────────────────────────────────────────────────────────────

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

/**
 * Graceful topic-change acknowledgements the partner says before moving on.
 * Models real conversation: normalise the difficulty, then signal the pivot.
 * Each entry: { zh, en }. Multiple variants rotate by time for variety.
 * Keyed by recovery phrase ID.
 */
const _RECOVERY_TOPIC_TRANSITIONS = {
  wo_bu_dong: [
    { zh: "没关系！我们换个话题吧。",   en: "No worries! Let's change the subject." },
    { zh: "没事！那我们聊点别的。",       en: "It's fine! Let's talk about something else." },
  ],
  ting_bu_dong: [
    { zh: "没事，换个话题吧。",           en: "No worries, let's change topics." },
    { zh: "没关系，我们换一个。",         en: "No worries, let's try something else." },
  ],
  bu_haoyisi_mei_tingdong: [
    { zh: "没关系！那我们换个话题。",     en: "No problem! Let's change the subject." },
    { zh: "没问题，换一个！",             en: "No problem, let's try another one!" },
  ],
  bu_zhidao: [
    { zh: "不知道没关系！",               en: "That's OK — no need to know!" },
    { zh: "不知道没问题！",               en: "No worries at all!" },
  ],
  women_liao_dian_jiandan_ba: [
    { zh: "好的，没问题！",               en: "Sure, no problem!" },
    { zh: "当然！",                       en: "Of course!" },
  ],
  women_keyi_liao_bie_de_ma: [
    { zh: "当然可以！",                   en: "Of course we can!" },
    { zh: "好的！",                       en: "Sure!" },
  ],
};

/** Pick a transition object { zh, en } for a recovery phrase ID, or null if none defined. */
function getTopicChangeTransition(phraseId) {
  const pool = _RECOVERY_TOPIC_TRANSITIONS[phraseId];
  if (!pool || !pool.length) return null;
  return pool[Math.floor(Date.now() / 1000) % pool.length];
}

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

/**
 * Render the "Need help?" recovery phrase panel into any container element.
 * Used by renderSentenceOptions so recovery phrases remain visible even when
 * optionsContainer is hidden.
 */
function renderRecoveryPanelInto(targetContainer, frameId) {
  const opt = getRecoveryPanelOption();
  if (!opt) return;

  const panel = document.createElement("div");
  panel.className = "option-panel";
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
      targetContainer.querySelectorAll(".option-panel").forEach((p) => p.classList.remove("selected"));
      panel.classList.add("selected");
      const userText = (phrase.hanzi || "").trim();
      addTranscriptEntry("user", userText, { text_en: phrase.meaning || "" });
      const action = getRecoveryAction(phrase);
      const currentQuestion = (window._currentFrameText || "").trim();

      if (action === "next_turn") {
        renderTranscript();
        const _transition = getTopicChangeTransition(phrase.id);
        ttsSpeak({
          text: userText, lang: "zh-CN",
          onEvent: (e) => {
            if (!e?.payload?.completed) return;
            if (_transition) {
              // Partner acknowledges and signals the pivot before the next question
              addTranscriptEntry("partner", _transition.zh, { text_en: _transition.en });
              renderTranscript();
              ttsSpeak({
                text: _transition.zh, lang: "zh-CN",
                onEvent: (e2) => { if (e2?.payload?.completed) runTurn(true, { prefer_bridge: true }); },
              });
            } else {
              runTurn(true, { prefer_bridge: true });
            }
          },
        });
        return;
      }

      let partnerLine, segments;
      const rawTokens = (frameTokens || window._frameTokens)?.frames?.[frameId];
      const hasNewSchema = rawTokens && rawTokens.length > 0 && "kind" in rawTokens[0];
      if (action === "slower") {
        partnerLine = currentQuestion ? "好的，慢一点：" + currentQuestion : "好的，慢一点。";
        segments = [{ t: currentQuestion ? "好的，慢一点：" : "好的，慢一点。" }];
        if (hasNewSchema && rawTokens.length) segments = segments.concat(rawTokens.map((t) => ({ t: t.t, word_id: t.word_id || undefined })));
        else if (currentQuestion) segments = segments.concat(currentQuestion.split("").map((c) => ({ t: c })));
      } else {
        partnerLine = currentQuestion || "好。";
        if (hasNewSchema && rawTokens.length) segments = rawTokens.map((t) => ({ t: t.t, word_id: t.word_id || undefined }));
        else segments = (currentQuestion || "").split("").map((c) => ({ t: c }));
      }
      addTranscriptEntry("partner", partnerLine);
      renderTranscript();
      setActivePartnerStatement(partnerLine, "recovery_repeat", segments);
      ttsSpeak({
        text: userText, lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed)
            ttsSpeak({ text: partnerLine, lang: "zh-CN", rate: action === "slower" ? 0.82 : undefined, queue: true });
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
  targetContainer.appendChild(panel);
}

function renderOptions(options, frameId) {
  // Normalize kind so validation and ? button behave consistently (default WORD when missing)
  options = (options || []).map(opt => ({
    ...opt,
    kind: (opt.kind && String(opt.kind).toUpperCase()) || "WORD",
  }));
  // Recovery panel is now rendered in sentenceOptionsContainer via renderRecoveryPanelInto().
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
      const hanziStr = opt.hanzi || "";
      const hanziWrap = document.createElement("span");
      hanziWrap.className = "option-hanzi option-hanzi-tokens";
      const segments = tokenizeHanziForOption(hanziStr, opt);
      segments.forEach((seg) => {
        const wid = seg.word_id;
        const surface = seg.t;
        const span = document.createElement("span");
        span.textContent = surface;
        span.className = wid ? "tok tok-word word-insight-token" : "tok tok-word-unknown word-insight-token";
        span.dataset.kind = "word";
        if (wid) span.dataset.wordId = wid;
        span.dataset.insightSource = `option:${idx}`;
        let tip = wid ? getInsightTitleForWordId(wid) : "";
        if (!tip && wid && wid === opt.card_id && (opt.pinyin || opt.meaning))
          tip = [opt.pinyin, opt.meaning].filter(Boolean).join(" — ");
        if (tip) span.title = tip;
        span.addEventListener("click", async (ev) => {
          ev.stopPropagation();
          ev.preventDefault();
          if (!wid) {
            _openWordInsightPopover(span, null, surface, `option:${idx}`);
            return;
          }
          lastClickedWordId = wid;
          window.lastClickedWordId = wid;
          _openWordInsightPopover(span, wid, surface, `option:${idx}`);
          const turnUid = window._currentTurnUid || frameId;
          hint_cascade_state = { level: 1, turn_uid: turnUid };
          renderHintAffordance({ ...(window._currentHintAffordance || {}), visible: true }, turnUid, "tap");
          if (_shouldAlsoOpenCardPanel()) await _openCardForWordId(wid);
        });
        hanziWrap.appendChild(span);
      });
      optionContent.appendChild(hanziWrap);
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

    btn.addEventListener("click", async (ev) => {
      if (ev.target.closest(".word-insight-token")) return;
      emitUITrace({ type: "OPTION_SELECTED", timestamp: new Date().toISOString(),
        payload: { frame_id: frameId, card_id: opt.card_id, is_gold: opt.is_gold, is_slot: opt.is_slot, option_idx: idx, kind: opt.kind } });
      container.querySelectorAll(".option-panel").forEach(p => p.classList.remove("selected"));
      panel.classList.add("selected");
      const userText = (opt.hanzi || "").trim();
      if (opt.kind !== "RECOVERY" && opt.kind !== "RECOVERY_PANEL") {
        window._consecutiveNotUnderstood = 0;
        window._recentConfusionCount = 0;  // Phase 12C: real answer clears overload signal
        hideDiscoveryPanel();  // user answered partner's question — exit discovery mode
      }

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
// ---------------------------------------------------------------------------
// Sentence-level response options  (replaces probe buttons + direction buttons)
// ---------------------------------------------------------------------------

function renderSentenceOptions(sentenceOptions, frameId) {
  const container = document.getElementById("sentenceOptionsContainer");
  if (!container) return;
  container.innerHTML = "";

  const answers = (sentenceOptions || []).filter(o => o.kind === "SENTENCE" || !o.kind);
  const hasSteerReverse = _directionCaps.supports_reverse;
  const hasSteerWhy     = _directionCaps.supports_why;
  if (!answers.length && !hasSteerReverse && !hasSteerWhy) { container.style.display = "none"; return; }

  // Build each answer as a standard option-panel so speaker, ?, and word-exploration all work
  answers.forEach((opt, idx) => {
    const hanziStr = (opt.zh || "").trim();
    const pinyin   = (opt.py || "").trim();
    const meaning  = (opt.en || "").trim();
    const cardId   = "__sentence_" + idx;

    const panel = document.createElement("div");
    panel.className = "option-panel";
    panel.setAttribute("data-option-index", String(idx));

    // Main button — tokenised hanzi + action icons
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "option-btn";

    const optionContent = document.createElement("div");
    optionContent.className = "option-content";

    const hanziWrap = document.createElement("span");
    hanziWrap.className = "option-hanzi option-hanzi-tokens";
    const pseudoOpt = { card_id: cardId, pinyin, meaning, hanzi: hanziStr };
    tokenizeHanziForOption(hanziStr, pseudoOpt).forEach((seg) => {
      const wid     = seg.word_id;
      const surface = seg.t;
      const span    = document.createElement("span");
      span.textContent = surface;
      span.className    = wid ? "tok tok-word word-insight-token" : "tok tok-word-unknown word-insight-token";
      span.dataset.kind = "word";
      if (wid) span.dataset.wordId = wid;
      span.dataset.insightSource = `sentence:${idx}`;
      const tip = wid ? getInsightTitleForWordId(wid) : "";
      if (tip) span.title = tip;
      span.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        ev.preventDefault();
        if (!wid) { _openWordInsightPopover(span, null, surface, `sentence:${idx}`); return; }
        lastClickedWordId = wid;
        window.lastClickedWordId = wid;
        _openWordInsightPopover(span, wid, surface, `sentence:${idx}`);
        if (_shouldAlsoOpenCardPanel()) await _openCardForWordId(wid);
      });
      hanziWrap.appendChild(span);
    });
    optionContent.appendChild(hanziWrap);
    btn.appendChild(optionContent);

    // 🔊 speaker + ? hint buttons
    const optionActions = document.createElement("div");
    optionActions.className = "option-actions";

    if (hanziStr) {
      const speakerBtn = document.createElement("button");
      speakerBtn.type = "button";
      speakerBtn.className = "option-speaker-btn";
      speakerBtn.setAttribute("title", "Speak this option");
      speakerBtn.setAttribute("aria-label", "Speak this option");
      speakerBtn.textContent = "\uD83D\uDD0A";
      speakerBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        ttsSpeak({ text: hanziStr, lang: "zh-CN" });
      });
      optionActions.appendChild(speakerBtn);
    }

    if (pinyin || meaning) {
      const hintBtn = document.createElement("button");
      hintBtn.type = "button";
      hintBtn.className = "option-hint-btn";
      hintBtn.setAttribute("title", "Show pinyin / meaning");
      hintBtn.setAttribute("aria-label", "Hint for this option");
      hintBtn.textContent = "?";
      hintBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const hintBlock = panel.querySelector(".option-hint-block");
        if (!hintBlock) return;
        const isVisible = hintBlock.style.display !== "none";
        hintBlock.style.display = isVisible ? "none" : "block";
        if (!isVisible) {
          const pyEl = hintBlock.querySelector(".option-hint-pinyin");
          const enEl = hintBlock.querySelector(".option-hint-meaning");
          if (pyEl) pyEl.textContent = pinyin;
          if (enEl) enEl.textContent = meaning;
        }
      });
      optionActions.appendChild(hintBtn);
    }

    if (optionActions.childNodes.length) btn.appendChild(optionActions);
    panel.appendChild(btn);

    // Hint block (hidden until ? clicked)
    const hintBlock = document.createElement("div");
    hintBlock.className = "option-hint-block";
    hintBlock.setAttribute("data-option-index", String(idx));
    hintBlock.style.display = "none";
    hintBlock.appendChild(Object.assign(document.createElement("div"), { className: "option-hint-row option-hint-pinyin" }));
    hintBlock.appendChild(Object.assign(document.createElement("div"), { className: "option-hint-row option-hint-meaning" }));
    panel.appendChild(hintBlock);

    // Click: mirror questions ask the persona; regular sentences are submitted as user answers
    btn.addEventListener("click", async (ev) => {
      if (ev.target.closest(".word-insight-token")) return;
      emitUITrace({ type: "SENTENCE_OPTION_SELECTED", timestamp: new Date().toISOString(),
        payload: { frame_id: frameId, text: hanziStr, topic: opt.topic || null } });
      container.querySelectorAll(".option-panel").forEach(p => p.classList.remove("selected"));
      panel.classList.add("selected");
      if (opt.topic) {
        // Mirror question — ask the persona, not submit as own answer
        runMirrorTurn(hanziStr, meaning, opt.topic);
      } else {
        window._consecutiveNotUnderstood = 0;
        addTranscriptEntry("user", hanziStr, { text_en: meaning });
        renderTranscript();
        container.style.display = "none";
        const optC = document.getElementById("optionsContainer");
        if (optC) optC.style.display = "none";
        window._lastAnswer = { frame_id: frameId || "", submitted_text: hanziStr };
        // Keep legacy UX: play chosen response first, then advance turn.
        ttsSpeak({
          text: hanziStr,
          lang: "zh-CN",
          onEvent: (e) => {
            if (e?.payload?.completed) {
              runTurn(true, { last_turn_was_answer: true, submitted_text: hanziStr });
            }
          },
        });
      }
    });

    container.appendChild(panel);
  });

  // --- Steer cards: "Turn it around" options — rendered as full option-panel cards --------
  // These give the learner a clearly-signposted way to redirect the conversation.
  const _steerDefs = [
    hasSteerReverse && { zh: "你呢？", py: "nǐ ne?", en: "And you? What about you?", intent: "reverse" },
    hasSteerWhy     && { zh: "为什么这么问？", py: "wèishéme zhème wèn?", en: "Why do you ask?", intent: "why" },
  ].filter(Boolean);

  if (_steerDefs.length) {
    const steerLabel = document.createElement("div");
    steerLabel.className = "steer-panel-label";
    steerLabel.textContent = "↩ Turn it around";
    container.appendChild(steerLabel);

    _steerDefs.forEach((def) => {
      const panel = document.createElement("div");
      panel.className = "option-panel";
      panel.setAttribute("data-steer", "true");

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "option-btn";

      const optionContent = document.createElement("div");
      optionContent.className = "option-content";
      const hanziWrap = document.createElement("span");
      hanziWrap.className = "option-hanzi option-hanzi-tokens";
      tokenizeHanziForOption(def.zh, { card_id: "__steer_" + def.intent, pinyin: def.py, meaning: def.en, hanzi: def.zh })
        .forEach((seg) => {
          const span = document.createElement("span");
          span.textContent = seg.t;
          span.className = "tok tok-word";
          hanziWrap.appendChild(span);
        });
      optionContent.appendChild(hanziWrap);
      btn.appendChild(optionContent);

      // 🔊 + ? inline
      const optionActions = document.createElement("div");
      optionActions.className = "option-actions";

      const speakerBtn = document.createElement("button");
      speakerBtn.type = "button";
      speakerBtn.className = "option-speaker-btn";
      speakerBtn.setAttribute("title", "Hear pronunciation");
      speakerBtn.textContent = "\uD83D\uDD0A";
      speakerBtn.addEventListener("click", (e) => { e.stopPropagation(); ttsSpeak({ text: def.zh, lang: "zh-CN" }); });
      optionActions.appendChild(speakerBtn);

      const hintBtn2 = document.createElement("button");
      hintBtn2.type = "button";
      hintBtn2.className = "option-hint-btn";
      hintBtn2.setAttribute("title", "Show pinyin / meaning");
      hintBtn2.textContent = "?";
      hintBtn2.addEventListener("click", (e) => {
        e.stopPropagation();
        const hb = panel.querySelector(".option-hint-block");
        if (!hb) return;
        hb.style.display = hb.style.display !== "none" ? "none" : "block";
        const pyEl = hb.querySelector(".option-hint-pinyin");
        const enEl = hb.querySelector(".option-hint-meaning");
        if (pyEl) pyEl.textContent = def.py;
        if (enEl) enEl.textContent = def.en;
      });
      optionActions.appendChild(hintBtn2);
      btn.appendChild(optionActions);
      panel.appendChild(btn);

      const hintBlock = document.createElement("div");
      hintBlock.className = "option-hint-block";
      hintBlock.style.display = "none";
      hintBlock.appendChild(Object.assign(document.createElement("div"), { className: "option-hint-row option-hint-pinyin" }));
      hintBlock.appendChild(Object.assign(document.createElement("div"), { className: "option-hint-row option-hint-meaning" }));
      panel.appendChild(hintBlock);

      btn.addEventListener("click", (ev) => {
        if (ev.target.closest(".word-insight-token")) return;
        container.querySelectorAll(".option-panel").forEach(p => p.classList.remove("selected"));
        panel.classList.add("selected");
        ttsSpeak({
          text: def.zh, lang: "zh-CN",
          onEvent: (e) => { if (e?.payload?.completed) runDirectionTurn(def.intent); },
        });
      });

      container.appendChild(panel);
    });
  }

  // Keep the reverseActionsRow clear — steer cards in the panel are the primary affordance
  const reverseActionsRow = document.getElementById("reverseActionsRow");
  if (reverseActionsRow) reverseActionsRow.innerHTML = "";

  // Recovery phrases ("Need help?") always live in the same container as sentence options
  renderRecoveryPanelInto(container, frameId);

  container.style.display = "flex";
}

function hideSentenceOptions() {
  const container = document.getElementById("sentenceOptionsContainer");
  if (container) { container.innerHTML = ""; container.style.display = "none"; }
  // Clear the inline reverse buttons alongside the speaker
  const reverseActionsRow = document.getElementById("reverseActionsRow");
  if (reverseActionsRow) reverseActionsRow.innerHTML = "";
  // Legacy cleanup: remove any stale probe-ladder buttons
  const ladder = document.getElementById("actionLadder");
  if (ladder) ladder.querySelectorAll(".probe-ladder-btn").forEach((b) => b.remove());
}

// Keep these as no-ops so existing call-sites don't break
function renderProbeRow() {}
function hideProbeRow() { hideSentenceOptions(); }
function renderDirectionButtons() {}

async function runDirectionTurn(intent) {
  _cancelProbeAutoAdvance();
  hideSentenceOptions();
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
  const _dirPersonaId = window._partnerId || window._personaId;
  if (_dirPersonaId) payload.persona_id = _dirPersonaId;

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
  window._userQuestionChain = (window._userQuestionChain || 0) + 1;
  if (stub) {
    addTranscriptEntry("partner", stub);
    renderTranscript();
    if (window._userQuestionChain >= MAX_USER_QUESTION_CHAIN) {
      // User has asked enough — partner reclaims the lead after speaking
      ttsSpeak({
        text: stub, lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed) { window._userQuestionChain = 0; runTurn(true); }
        },
      });
    } else {
      ttsSpeak({ text: stub, lang: "zh-CN" });
      // Show mirror questions (engine-specific) so the learner can interrogate the persona
      renderSentenceOptions(data.mirror_options || [], null);
      _startProbeAutoAdvance();
    }
  } else {
    runTurn(true);
  }
}

/**
 * Learner asked a specific mirror question about the persona (e.g. "你的名字是什么意思？").
 * Sends the question to the server, shows the persona's answer, then offers further mirror questions.
 */
async function runMirrorTurn(zh, en, topic) {
  _cancelProbeAutoAdvance();
  hideSentenceOptions();
  const userText = (zh || "").trim();
  if (!userText) return;
  addTranscriptEntry("user", userText, { text_en: en || "" });
  renderTranscript();
  ttsSpeak({ text: userText, lang: "zh-CN" });

  const currentEngine = window._currentEngineId ?? "identity";
  const payload = {
    env: "dev",
    turn_uid: "ui_mirror_" + Date.now(),
    direction_intent: "mirror",
    direction_question_zh:    userText,
    direction_question_topic: topic || "",
    conversation_state: {
      session_id:            window._sessionId,
      current_engine:        currentEngine,
      last_partner_frame_id: window._lastPartnerFrameId ?? null,
      recent_frame_ids:      Array.isArray(window._recentFrameIds) ? window._recentFrameIds : [],
    },
  };
  const _mirrorPersonaId = window._partnerId || window._personaId;
  if (_mirrorPersonaId) payload.persona_id = _mirrorPersonaId;

  let res;
  try {
    res = await fetch("/api/run_turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    console.warn("[app] runMirrorTurn fetch failed", e);
    return;
  }
  if (!res.ok) return;
  let data = {};
  try { data = await res.json(); } catch (_) { return; }

  const stub = (data.frame_text || "").trim();
  window._userQuestionChain = (window._userQuestionChain || 0) + 1;
  if (stub) {
    addTranscriptEntry("partner", stub);
    renderTranscript();
    if (window._userQuestionChain >= MAX_USER_QUESTION_CHAIN) {
      ttsSpeak({
        text: stub, lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed) { window._userQuestionChain = 0; runTurn(true); }
        },
      });
    } else {
      ttsSpeak({ text: stub, lang: "zh-CN" });
      // Offer remaining mirror questions (excluding the one just asked)
      const remaining = (data.mirror_options || []).filter(m => m.zh !== userText);
      renderSentenceOptions(remaining, null);
      _startProbeAutoAdvance();
    }
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
  // Phase 12B: increment probe depth so the server can suppress chained probes
  window._probeDepth = (window._probeDepth || 0) + 1;
  const payload = {
    env: "dev",
    turn_uid: "ui_probe_" + Date.now(),
    probe_id: probe.id || "",
    probe_hanzi: hanzi,
    conversation_state: {
      session_id: window._sessionId,
      current_engine: currentEngine,
      last_partner_frame_id: window._lastPartnerFrameId ?? null,
      recent_frame_ids: Array.isArray(window._recentFrameIds) ? window._recentFrameIds : [],
      probe_depth: window._probeDepth
    }
  };
  const _probePersonaId = window._partnerId || window._personaId;
  if (_probePersonaId) payload.persona_id = _probePersonaId;
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
  window._userQuestionChain = (window._userQuestionChain || 0) + 1;
  if (stub) {
    addTranscriptEntry("partner", stub);
    renderTranscript();
    if (window._userQuestionChain >= MAX_USER_QUESTION_CHAIN) {
      ttsSpeak({
        text: stub, lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed) { window._userQuestionChain = 0; runTurn(true); }
        },
      });
    } else {
      ttsSpeak({ text: stub, lang: "zh-CN" });
      renderSentenceOptions([], null);
      _startProbeAutoAdvance();
    }
  } else {
    runTurn(true);
  }
}

/**
 * Start a countdown that auto-advances the partner's turn if the user doesn't
 * click a probe button within PROBE_IDLE_MS milliseconds.
 * Any new probe click or runTurn call cancels this timer first.
 */
const PROBE_IDLE_MS = 8000;
function _startProbeAutoAdvance() {
  _cancelProbeAutoAdvance();
  window._probeAutoAdvanceTimer = setTimeout(() => {
    window._probeAutoAdvanceTimer = null;
    hideProbeRow();
    window._userQuestionChain = 0;
    runTurn(true);
  }, PROBE_IDLE_MS);
}
function _cancelProbeAutoAdvance() {
  if (window._probeAutoAdvanceTimer) {
    clearTimeout(window._probeAutoAdvanceTimer);
    window._probeAutoAdvanceTimer = null;
  }
}

/**
 * Reset all session state and clear learner memory on the server, then restart from the greeting.
 * Called by the "Start Fresh" button so the app treats the user as a first-time learner.
 */
async function startFreshLearner() {
  // Switch to a new learner ID so the server starts with empty memory automatically —
  // no API call required.  The old data remains in the file but is never used again.
  window._learnerId = "learner_" + Date.now();

  // Also ask the server to clear the old ID in the background (best-effort cleanup).
  // This may fail silently if the server is not available — that is fine.
  try {
    await fetch("/api/reset_memory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ learner_id: "default_learner" })
    });
  } catch (_) {}

  // Reset all client-side session state
  _cancelProbeAutoAdvance();
  hideSentenceOptions();
  window._runTurnInFlight        = false;   // clear any stale in-flight guard
  window._sessionId              = "session_" + Date.now();
  window._recentFrameIds         = [];
  window._lastAnswer             = null;
  window._probeDepth             = 0;
  window._userQuestionChain      = 0;
  window._lastProbeOptions       = [];
  window._revealedVoiceLines     = {};
  window._revealedPartnerFacts   = {};
  window._exchangeCount          = 0;
  window._curiosityDepth         = 0;
  window._askChainCount          = 0;
  window._lastPartnerTurnType    = "question";
  window._sameEngineChainCount   = 0;
  window._sameSlotChainCount     = 0;
  window._lastFocusSlot          = "";
  window._pendingListeningMove   = false;
  window._listeningWaitTurns     = 0;
  window._lastInterestLevel      = "low";
  window._lastUserText           = "";
  window._unmatchedByFrame       = {};
  window._consecutiveNotUnderstood = 0;
  window._currentEngineId        = "identity";
  // Phase 12C: session arc state
  window._loopCountInEngine      = 0;
  window._enginesVisited         = ["identity"];
  window._recentConfusionCount   = 0;

  // Clear the "Remembered:" facts banner
  const rememberedEl = document.getElementById("rememberedFacts");
  if (rememberedEl) {
    rememberedEl.textContent = "";
    rememberedEl.style.display = "none";
  }

  // Clear the transcript so the slate looks visually fresh
  const transcriptEl = document.getElementById("transcript");
  if (transcriptEl) transcriptEl.innerHTML = "";

  // Clear the active partner question area
  const frameSentenceEl = document.getElementById("frameSentence");
  if (frameSentenceEl) frameSentenceEl.textContent = "";

  hideSentenceOptions();

  // Show a brief status message — do NOT auto-start a turn.
  // The user can now select any frame from the dropdown and press Run Turn,
  // or press the mic to speak the first greeting themselves.
  const statusEl = document.getElementById("statusMsg") || document.createElement("div");
  statusEl.textContent = "Memory cleared — ready for a new conversation.";
  statusEl.style.cssText = "color:#0891b2;font-size:0.85rem;padding:6px 14px;";
  if (!document.getElementById("statusMsg")) {
    statusEl.id = "statusMsg";
    document.getElementById("actionLadder")?.prepend(statusEl);
  }
  setTimeout(() => { statusEl.textContent = ""; }, 4000);
}

/**
 * Run a turn: either "Run Turn" (frame from dropdown) or "Next" (selector-driven next frame).
 * @param {boolean} [isNext=false] When true, send next_question + conversation_state; server chooses frame.
 * @param {{ prefer_bridge?: boolean, force_bridge?: boolean, last_turn_was_answer?: boolean }} [opts] When isNext: prefer_bridge tries bridge first (e.g. after interesting answer or recovery); force_bridge only bridge; last_turn_was_answer triggers probe_offer.
 */
async function runTurn(isNext = false, opts = {}) {
  // Cancel any pending idle auto-advance so it doesn't conflict with this turn.
  _cancelProbeAutoAdvance();
  hideSentenceOptions();
  // Guard: prevent two runTurn calls from firing simultaneously (e.g. double ASR fire).
  if (window._runTurnInFlight) return;
  window._runTurnInFlight = true;
  try { await _runTurnInner(isNext, opts); } finally { window._runTurnInFlight = false; }
}

async function _runTurnInner(isNext = false, opts = {}) {
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
      last_user_text: window._lastUserText || "",
      // Phase 12C: session arc state
      loop_count_in_current_engine: window._loopCountInEngine || 0,
      engines_visited: Array.isArray(window._enginesVisited) ? window._enginesVisited : ["identity"],
      recent_confusion_count: window._recentConfusionCount || 0,
    };
    if (window._learnerId) conversation_state.learner_id = window._learnerId;
    // Use the UI-selected partner (Phase 11C) as the persona_id for name/stub resolution.
    // Fall back to the legacy _personaId only if no partner is selected.
    const _effectivePersonaId = window._partnerId || window._personaId;
    if (_effectivePersonaId) conversation_state.persona_id = _effectivePersonaId;
    if (window._partnerId) {
      conversation_state.partner_id = window._partnerId;
      conversation_state.revealed_voice_lines = window._revealedVoiceLines || {};
      conversation_state.revealed_partner_facts = window._revealedPartnerFacts || {};
    }
    // Phase 12B: reset probe depth on real (non-probe) answer; pass current depth to server
    if (opts.last_turn_was_answer === true) {
      window._probeDepth = 0;
      window._userQuestionChain = 0;  // user gave a real answer — partner leads again
    }
    conversation_state.probe_depth = window._probeDepth || 0;
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
  // Phase 12C: update session arc state from server response
  if (data.arc_state) {
    if (typeof data.arc_state.loop_count === "number")
      window._loopCountInEngine = data.arc_state.loop_count;
    if (Array.isArray(data.arc_state.engines_visited))
      window._enginesVisited = data.arc_state.engines_visited;
  }
  // Track engine visits locally too (client knows engine_id before arc_state arrives)
  const _arcEngineId = (data.engine_id || "").toLowerCase();
  if (_arcEngineId && !window._enginesVisited.includes(_arcEngineId))
    window._enginesVisited = [...window._enginesVisited, _arcEngineId];

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
  window._lastAcceptedAsrKey = "";  // reset dedup so fresh answers on new questions are accepted
  // Counter-reply: persona's answer to a user counter-question (你呢？ 你是哪里人？ etc.)
  // Must appear in transcript BEFORE the next question and be spoken first.
  console.log("[DBG counter_reply]", { counter_reply: data.counter_reply, user_led: data.user_led, disc_q_count: (data.discovery_questions || []).length });
  const _counterReply = (data.counter_reply || "").trim();
  if (_counterReply) {
    addTranscriptEntry("partner", _counterReply);
  }
  // Phase 8: append partner question to transcript when we show a new question
  if (window._currentFrameText) {
    addTranscriptEntry("partner", window._currentFrameText, {
      text_en: data.frame_text_en || "",
      pinyin: data.frame_pinyin || "",
      frame_id: frameId,
      turn_uid: payload.turn_uid,
    });
  }
  // Always render — ensures counter_reply entry is visible even if _currentFrameText is absent
  renderTranscript();

  // Discovery mode: persona answered the user's question — show "Ask them more" cards
  if (data.user_led && Array.isArray(data.discovery_questions) && data.discovery_questions.length > 0) {
    renderDiscoveryPanel(data.discovery_questions);
  } else {
    hideDiscoveryPanel();
  }
  // Auto-play: if a counter_reply exists, speak it first, then the frame question.
  if (fallbackText && fallbackText.trim()) {
    if (_counterReply) {
      ttsSpeak({
        text: _counterReply, lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed) ttsSpeak({ text: fallbackText.trim(), lang: "zh-CN" });
        },
      });
    } else {
      ttsSpeak({ text: fallbackText.trim(), lang: "zh-CN" });
    }
  } else if (_counterReply) {
    ttsSpeak({ text: _counterReply, lang: "zh-CN" });
  }
  // Phase 6 — options: prefer server-sent options when server chose the frame (next_question) so options always match the displayed question after bridge
  const _frameData     = window._frameOptionsRuntime?.frames?.[frameId] || {};
  const tapOptions     = (payload.next_question && Array.isArray(data.options) && data.options.length > 0)
    ? data.options
    : (_frameData.options || data.options || []);
  // Default to visible:true so the ? button always shows for frames not yet in the runtime JSON.
  const hintAffordance = _frameData.hint_affordance || { visible: true };
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

  // Phase 12C: update direction caps from server so steer cards show correctly
  _directionCaps = {
    supports_reverse: data.supports_reverse !== false,
    supports_why:     data.supports_why !== false,
  };
  // Sentence-level response options (answers + always-on reverse/oxygen row)
  // These replace the word-hint panels as the primary response UI when present.
  renderSentenceOptions(data.sentence_options || [], frameId);
  // Hide the word-hint panels when sentence options are showing — they are redundant.
  const hasSentenceOptions = (data.sentence_options || []).some(o => o.kind === "SENTENCE" || !o.kind);
  if (hasSentenceOptions) {
    const optC = document.getElementById("optionsContainer");
    if (optC) optC.style.display = "none";
  }
  // Legacy probe state: store for runProbeTurn compatibility but don't render separately
  if (data.probe_offer === true && Array.isArray(data.probe_options) && data.probe_options.length > 0) {
    window._lastProbeOptions = data.probe_options;
  }
  // Phase 11C: show partner name, voice_line prefix, and discoverable fact
  _updatePartnerHeader(data.partner_name || "", data.partner_prefix || "", data.partner_fact || "");
  // Record which reveals have fired so the server gates correctly on the next turn
  if (data.partner_prefix && engineId) window._revealedVoiceLines[engineId] = true;
  if (data.partner_fact  && engineId) window._revealedPartnerFacts[engineId] = true;
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
  // Suppress for intentional stubs (direction/probe responses have option_count:0 by design)
  // and for frames that provide sentence_options (the primary UI since Phase 10.7)
  const _hasSentenceOptions = Array.isArray(data.sentence_options) && data.sentence_options.length > 0;
  const _isStubResponse = data.is_direction_response || data.is_probe_response;
  if (!_isStubResponse && !_hasSentenceOptions && (data.option_count === 0 || data.gold_option_present === false)) {
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

// defaults
window.addEventListener("load", async () => {
  // Phase 6: load render tokens and cards index in parallel with existing loads
  await Promise.all([
    loadPackFramesIntoDropdown(),
    loadFrameRenderTokens(),
    loadCardsIndex(),
    loadCardsByIdBlob(),
    loadFrameOptions(),
    loadWordEtymology(),
    loadComponentGlossMaps(),
    loadCharacters1200Core(),
    loadFrameTokens(),
    loadRecoveryPhrases(),
    loadPersonas(),
  ]);
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
      if (frameId) window._unmatchedByFrame[frameId] = 0;
      window._consecutiveNotUnderstood = 0;
      window._recentConfusionCount = 0;  // Phase 12C: real answer clears overload signal
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
      // If the SPOKEN text (not the matched card) contained a turn-around phrase, preserve it
      // as submitted_text so the server can detect the counter-question.  Without this, the
      // "你呢" part of "我喜欢工作，你呢？" is swallowed when an option card matched the first part.
      const _spokenRaw = (transcript || "").trim();
      const _spokenHasTurnAround = _spokenRaw && (
        /^(那?你呢|你怎么想|为什么这么问|为什么这样问|换我问|那你|你来问)/.test(_spokenRaw)
        || _spokenRaw === "你呢"
        || /[，。！]?(那?你呢|你怎么想|为什么这么问)[？?]?$/.test(_spokenRaw)
        || /你(是哪里人|从哪里来|老家在哪|住(在哪|哪里|的地方)|做什么工作|的工作|是做什么|喜欢(什么|做什么)|有什么爱好|有家人|有没有家人)/.test(_spokenRaw)
      );
      const _spokenSubmitted = _spokenHasTurnAround
        ? (_spokenRaw.endsWith("？") || _spokenRaw.endsWith("?") ? _spokenRaw : _spokenRaw + "？")
        : undefined;
      window._lastAnswer = {
        frame_id: frameId,
        selected_option_hanzi: saidText,
        selected_option_meaning: matchedOption.meaning || undefined,
        ...(_spokenSubmitted ? { submitted_text: _spokenSubmitted } : {}),
      };
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

    // ASR dedup guard: Edge sometimes fires the same recognition result twice within a few
    // seconds (once as interim, once as final). Suppress if the same text was already accepted
    // for the same frame in the last 6 seconds so we don't get duplicate partner turns.
    const _asrDedupKey = saidTrimmed + "|" + frameId;
    const _now = Date.now();
    if (window._lastAcceptedAsrKey === _asrDedupKey &&
        (_now - (window._lastAcceptedAsrTime || 0)) < 6000) {
      console.warn("[app] ASR duplicate suppressed:", saidTrimmed);
      return;
    }

    const unmatchedCount = frameId ? (window._unmatchedByFrame?.[frameId] || 0) : 0;
    const unmatchedDecision = classifyUnmatchedFreeAnswerDecision(saidTrimmed, options, frameId, unmatchedCount);
    const substantialAnswer = unmatchedDecision.accept;
    if (substantialAnswer) {
      window._lastAcceptedAsrKey  = _asrDedupKey;
      window._lastAcceptedAsrTime = _now;
      if (frameId) window._unmatchedByFrame[frameId] = 0;
      window._consecutiveNotUnderstood = 0;
      window._recentConfusionCount = 0;  // Phase 12C: real answer clears overload signal
      emitUITrace({
        type: "SPEECH_ACCEPTED_AS_ANSWER",
        timestamp: new Date().toISOString(),
        payload: { transcript: saidTrimmed, matched: false, unmatched_decision_reason: unmatchedDecision.reason, frame_id: frameId }
      });
      // Learner skip signal ("我不懂"): advance without saving as scored answer
      if (unmatchedDecision.reason === "learner_skip_signal") {
        addTranscriptEntry("user", saidTrimmed);
        renderTranscript();
        lastClickedWordId = null;
        window.lastClickedWordId = null;
        setUiMode("READ");
        runTurn(true);
        return;
      }
      // Normalise turn-around phrases: ensure trailing "？" so the server reliably
      // detects them as counter-questions (ASR often strips punctuation).
      const _isTurnAround = /^(那?你呢|你怎么想|为什么这么问|为什么这样问|换我问|那你|你来问)/.test(saidTrimmed)
        || saidTrimmed === "你呢"
        || /[，。！]?(那?你呢|你怎么想|为什么这么问)[？?]?$/.test(saidTrimmed)
        || /你(是哪里人|从哪里来|老家在哪|住(在哪|哪里|的地方)|做什么工作|的工作|是做什么|喜欢(什么|做什么)|有什么爱好|有家人|有没有家人)/.test(saidTrimmed);
      // Ensure trailing "？" so server _is_user_question reliably fires
      const submittedForServer = _isTurnAround && !/[？?]$/.test(saidTrimmed) ? saidTrimmed + "？" : saidTrimmed;
      addTranscriptEntry("user", saidTrimmed);
      renderTranscript();
      window._lastAnswer = { frame_id: frameId, submitted_text: submittedForServer };
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
      payload: { transcript, unmatched_decision_reason: unmatchedDecision.reason, frame_id: frameId, unmatched_count: unmatchedCount + 1 }
    });
    if (frameId) window._unmatchedByFrame[frameId] = unmatchedCount + 1;
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
  // Close word-insight popover on click outside (tokens use stopPropagation; option tokens included)
  document.addEventListener("click", (e) => {
    const mg = document.getElementById("microGloss");
    if (!mg || mg.style.display === "none") return;
    if (mg.contains(e.target)) return;
    if (e.target.closest(".word-insight-token")) return;
    _closeMicroGloss();
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
const showOptionsBtn = document.getElementById("showOptionsBtn");
if (showOptionsBtn) showOptionsBtn.addEventListener("click", () => {
  const sentenceContainer = document.getElementById("sentenceOptionsContainer");
  const legacyContainer = document.getElementById("optionsContainer");
  const hasSentence = !!(sentenceContainer && sentenceContainer.children.length > 0);
  const hasLegacy = !!(legacyContainer && legacyContainer.children.length > 0);

  if (hasSentence && sentenceContainer) {
    const isVisible = sentenceContainer.style.display !== "none";
    sentenceContainer.style.display = isVisible ? "none" : "flex";
    setUiMode("RESPOND");
    if (!isVisible) sentenceContainer.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }
  if (hasLegacy && legacyContainer) {
    const isVisible = legacyContainer.style.display !== "none";
    legacyContainer.style.display = isVisible ? "none" : "flex";
    setUiMode("RESPOND");
    if (!isVisible) legacyContainer.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }
  console.info("[app] showOptionsBtn: no suggested responses available for this turn");
});
const startFreshBtn = document.getElementById("startFreshBtn");
if (startFreshBtn) startFreshBtn.addEventListener("click", () => {
  if (confirm("This will clear all memory of you and restart the conversation from the beginning. Continue?")) {
    startFreshLearner();
  }
});
// ── Discovery panel: "You interview the persona" mode ───────────────────────
/**
 * Render clickable "Ask them:" cards so the learner can interview the persona
 * instead of being relentlessly asked questions themselves.
 * questions: array of { zh, py, en, topic }
 */
function renderDiscoveryPanel(questions) {
  let panel = document.getElementById("discoveryPanel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "discoveryPanel";
    // Insert between the action ladder and the sentence options
    const anchor = document.getElementById("sentenceOptionsContainer")
                || document.getElementById("optionsContainerParent")
                || document.getElementById("engInputPanel");
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(panel, anchor);
    } else {
      document.body.appendChild(panel);
    }
  }
  panel.style.display = "block";
  panel.innerHTML = `<div class="discovery-header">你还想了解什么？ <span class="discovery-sub">Ask them:</span></div>`;

  (questions || []).forEach((q) => {
    const card = document.createElement("div");
    card.className = "option-panel discovery-question";
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");

    const zhSpan = document.createElement("span");
    zhSpan.className = "op-zh";
    zhSpan.textContent = q.zh || "";
    card.appendChild(zhSpan);

    if (q.py) {
      const pySpan = document.createElement("span");
      pySpan.className = "op-py";
      pySpan.textContent = q.py;
      card.appendChild(pySpan);
    }
    if (q.en) {
      const enSpan = document.createElement("span");
      enSpan.className = "op-en";
      enSpan.textContent = q.en;
      card.appendChild(enSpan);
    }

    const speakBtn = document.createElement("button");
    speakBtn.className = "op-icon-btn";
    speakBtn.title = "Hear pronunciation";
    speakBtn.textContent = "🔊";
    speakBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (q.zh) ttsSpeak({ text: q.zh, lang: "zh-CN" });
    });
    card.appendChild(speakBtn);

    card.addEventListener("click", () => submitDiscoveryQuestion(q));
    card.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") submitDiscoveryQuestion(q); });
    panel.appendChild(card);
  });
}

function hideDiscoveryPanel() {
  const panel = document.getElementById("discoveryPanel");
  if (panel) panel.style.display = "none";
}

function submitDiscoveryQuestion(q) {
  const zh = (q.zh || "").trim();
  if (!zh) return;
  hideDiscoveryPanel();
  addTranscriptEntry("user", zh, { text_en: q.en || "", pinyin: q.py || "" });
  renderTranscript();
  // Ensure trailing "？" so the server reliably detects this as a counter-question
  const submitted = zh.endsWith("？") ? zh : zh + "？";
  window._lastAnswer = { frame_id: window._lastPartnerFrameId || "", submitted_text: submitted };
  ttsSpeak({
    text: zh, lang: "zh-CN",
    onEvent: (e) => {
      if (e?.payload?.completed) runTurn(true, { last_turn_was_answer: true });
    },
  });
}

// ── English → Chinese translation panel ─────────────────────────────────────
(function setupEngTranslationPanel() {
  const engInput       = document.getElementById("engInput");
  const translateBtn   = document.getElementById("translateBtn");
  const engMicBtn      = document.getElementById("engMicBtn");
  const engResult      = document.getElementById("engTranslateResult");
  const engTranslated  = document.getElementById("engTranslatedZh");
  const speakBtn       = document.getElementById("speakTranslationBtn");
  const useBtn         = document.getElementById("useTranslationBtn");
  if (!engInput || !translateBtn || !engResult || !engTranslated || !useBtn) return;

  async function doTranslate() {
    const text = engInput.value.trim();
    if (!text) return;
    translateBtn.disabled = true;
    translateBtn.textContent = "…";
    engResult.style.display = "none";
    try {
      const url = "https://api.mymemory.translated.net/get?q=" +
                  encodeURIComponent(text) + "&langpair=en%7Czh";
      const res = await fetch(url);
      const data = await res.json();
      const zh = (data?.responseData?.translatedText || "").trim();
      if (zh && zh !== text) {
        engTranslated.textContent = zh;
        engResult.style.display = "flex";
        // Auto-play so the user hears pronunciation immediately
        ttsSpeak({ text: zh, lang: "zh-CN" });
      } else {
        engTranslated.textContent = "（翻译失败，请再试）";
        engResult.style.display = "flex";
      }
    } catch (_) {
      engTranslated.textContent = "（无法连接翻译服务）";
      engResult.style.display = "flex";
    } finally {
      translateBtn.disabled = false;
      translateBtn.textContent = "Translate";
    }
  }

  translateBtn.addEventListener("click", doTranslate);
  engInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); doTranslate(); }
  });

  // ── English microphone: speak English → auto-fill field → translate ───────
  if (engMicBtn) {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      engMicBtn.title = "Speech recognition not supported in this browser";
      engMicBtn.style.opacity = "0.4";
      engMicBtn.disabled = true;
    } else {
      let _engRec = null;
      let _engRecording = false;

      engMicBtn.addEventListener("click", () => {
        if (_engRecording && _engRec) {
          _engRec.stop();
          return;
        }
        _engRec = new SpeechRec();
        _engRec.lang = "en-US";
        _engRec.interimResults = false;
        _engRec.maxAlternatives = 1;
        _engRec.continuous = false;

        _engRec.onstart = () => {
          _engRecording = true;
          engMicBtn.classList.add("recording");
          engMicBtn.title = "Listening… (click to stop)";
        };
        _engRec.onend = () => {
          _engRecording = false;
          engMicBtn.classList.remove("recording");
          engMicBtn.title = "Speak in English";
          _engRec = null;
        };
        _engRec.onerror = () => {
          _engRecording = false;
          engMicBtn.classList.remove("recording");
          engMicBtn.title = "Speak in English";
          _engRec = null;
        };
        _engRec.onresult = (ev) => {
          const transcript = (ev.results[0]?.[0]?.transcript || "").trim();
          if (transcript) {
            engInput.value = transcript;
            doTranslate();
          }
        };
        _engRec.start();
      });
    }
  }

  // Speaker button: play the translated Chinese without submitting
  if (speakBtn) {
    speakBtn.addEventListener("click", () => {
      const zh = (engTranslated.textContent || "").trim();
      if (zh && !zh.startsWith("（")) ttsSpeak({ text: zh, lang: "zh-CN" });
    });
  }

  useBtn.addEventListener("click", () => {
    const zh = (engTranslated.textContent || "").trim();
    if (!zh || zh.startsWith("（")) return;
    const enOrig = engInput.value.trim();
    // Add to transcript and speak
    addTranscriptEntry("user", zh, { text_en: enOrig });
    renderTranscript();
    ttsSpeak({ text: zh, lang: "zh-CN" });
    engInput.value = "";
    engResult.style.display = "none";
    // Store as last answer so the server can use it for slot inference and interest scoring
    window._lastAnswer = { frame_id: window._lastPartnerFrameId || "", submitted_text: zh };
    // Advance the conversation as if the user gave a free-text spoken answer
    runTurn(true, { last_turn_was_answer: true });
  });
})();

// ── Phase 6 — expose to window for console access + external callers ────────
window.SystemFaultLog          = SystemFaultLog;
window.buildDiagnosticCompleted = buildDiagnosticCompleted;
window.hint_cascade_state   = hint_cascade_state;
window.renderHintAffordance = renderHintAffordance;


















