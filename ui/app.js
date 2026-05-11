import { initialState as _initialState, reduce } from "./state/cardPanelState.js";
import { ttsSpeak, ttsUnlock } from "./ttsSpeak.js";
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
/** Normalized zh → en from /api/gloss (shared with partner lines). */
const glossLineCache = new Map();
const _glossFetchInFlight = new Set();

// ── Challenge Mode state (C1–C4) ──────────────────────────────────────────
// Single source of truth. window._challengeMode is exposed for console debugging.
const _challenge = {
  active: false,
  helpLevel: 0,     // 0=none | 1=replay | 2=slow | 3=textRevealed | 4=suggestShown
  recoveryCount: 0, // recovery clicks this turn; reset per turn
};
window._challengeMode = _challenge;

// ── Session tracker — observational telemetry only ─────────────────────────
// Counts signals emitted by the user during this session.
// Read-only from the perspective of all conversation logic: this object must
// never be read by frame selection, selector scoring, recovery, or hints.
// Exposed on window for console inspection only.
const _tracker = {
  mode: "normal",                // "normal" | "challenge" — mirrors _challenge.active at session start
  total_turns: 0,                // user-submitted turns (incremented once per accepted /api/run_turn response)
  recovery_uses: 0,              // times user tapped a recovery phrase card
  successful_recoveries: 0,      // recovery uses where the immediately following turn was accepted
  suggestion_clicks: 0,          // times user selected a suggested response option
  card_opens: 0,                 // user-initiated card-panel opens (not re-renders)
  questions_asked: 0,            // user turns containing a question marker (吗/什么/怎么/为什么)
  depth_responses: 0,            // user turns containing a depth marker (因为/所以/觉得/但是/其实/对我来说)
  unmatched_responses: 0,        // turns where ASR input did not match any option and was rejected
  engines_used: new Set(),       // engine IDs seen in responses this session
  _pendingRecovery: false,       // transient: true if last user action was a recovery tap (cleared on next turn)
};
window._sessionTracker = _tracker;

// Duration answer pattern — used in acceptance logic, semantic detection, and tracking.
// Matches "20年", "5天", "二十年", "三个月" (Arabic or Chinese numeral + 年/月/天).
const _DURATION_ANSWER_PAT = /\d+[年月天]|[一二三四五六七八九十百千万零两][年月天]/;

/**
 * Record question and depth signals from a single accepted user turn.
 * Called once per submitted answer; each turn counts at most once for each dimension.
 * Never touches conversation logic — observational only.
 */
function _trackUserTextSignals(text) {
  if (!text || typeof text !== "string") return;

  // ── Question detection ─────────────────────────────────────────────────────
  // A sentence is a question only when it carries an interrogative structure —
  // not just because it contains a question word used in a declarative clause.
  //
  // Structural tests (any one is sufficient alone):
  //   hasMa           — contains the yes/no particle 吗
  //   endsWithQmark   — ends with ASCII ? or fullwidth ？
  //   shortIntPattern — ≤10 chars AND starts with 你/他/她/这/那
  //
  // Question words (什么, 哪…, 谁, 为什么, 怎么, 几, 多少, 多久) are only counted
  // when AT LEAST ONE structural test also passes — this prevents declarative
  // clauses like "我不知道怎么说" or "我想去哪里都可以" from being counted.
  //
  // 你呢 (reciprocal "and you?") is always a question regardless of length.
  const QUESTION_WORDS = ["什么", "哪里", "哪儿", "哪个", "谁", "为什么", "怎么", "几", "多少", "多久"];
  const textTrimmed    = text.trim();
  const hasMa          = text.includes("吗");
  const hasYouNe       = text.includes("你呢");
  const endsWithQmark  = /[?？]$/.test(textTrimmed);
  const hasQWord       = QUESTION_WORDS.some(m => text.includes(m));
  // Short interrogative pattern: ≤10 chars AND subject-initial (你/他/她/这/那)
  const shortIntPattern = textTrimmed.length <= 10 && /^[你他她这那]/.test(textTrimmed);
  const isStructuralQ   = hasMa || endsWithQmark || shortIntPattern;
  const isQuestion      = hasYouNe || hasMa || endsWithQmark || (hasQWord && isStructuralQ);

  if (isQuestion) {
    _tracker.questions_asked++;
    window._learnerObs.question_count++;
  }

  // ── Depth markers (scorecard depth_responses counter — unchanged) ──────────
  const DEPTH_MARKERS = ["因为", "所以", "觉得", "但是", "其实", "对我来说", "最喜欢", "想", "希望"];
  if (DEPTH_MARKERS.some(m => text.includes(m))) _tracker.depth_responses++;

  // ── Extended answer detection ──────────────────────────────────────────────
  // "Extended" = carries temporal / relational / causal / quantitative context,
  // or is long enough to contain meaningful extra information, or uses duration /
  // comparison patterns that indicate the learner elaborated.
  const EXTEND_MARKERS   = ["以前", "现在", "已经", "因为", "所以", "但是", "还", "和", "跟", "一起"];
  // Duration: "20年", "二十年", "3个月" — Arabic or Chinese numeral + time unit
  const COMPARISON_PAT   = /好多了|好很多|好一点|更好|比以前|进步|改善/;
  const isExtended = text.length > 8
                  || EXTEND_MARKERS.some(m => text.includes(m))
                  || _DURATION_ANSWER_PAT.test(text)
                  || COMPARISON_PAT.test(text);
  if (isExtended) window._learnerObs.extended_answer_count++;

  // ── Recovery resilience ────────────────────────────────────────────────────
  // Count only when:
  //   (a) the previous turn ended with a repair prompt, AND
  //   (b) this submission differs from what was previously rejected
  //       (identical retries are persistence, not resilience).
  // Cleared after the first answer so the counter increments at most once
  // per repair sequence.
  if (window._pendingRepairPrompt) {
    if (text !== (window._lastRepairSubmittedText || "")) {
      window._learnerObs.recovery_resilience_count++;
    }
    window._pendingRepairPrompt      = false;
    window._lastRepairSubmittedText  = "";
  }
}

function addTranscriptEntry(role, textZh, extras = {}) {
  const entry = {
    id: "line_" + Date.now() + "_" + Math.floor(Math.random() * 10000),
    role: role === "partner" ? "partner" : "user",
    text_zh: textZh || "",
    text_en: extras.text_en || "",
    pinyin: extras.pinyin || "",
    frame_id: extras.frame_id || "",
    turn_uid: extras.turn_uid || "",
    replayable: true,
    created_at: new Date().toISOString(),
    _glossPending: false,
  };
  conversationTranscript.push(entry);
  maybeRequestGlossForEntry(entry);
}

/** Fill missing English via server /api/gloss (optional deep-translator) for any Chinese line. */
function maybeRequestGlossForEntry(entry) {
  if (!entry) return;
  const zh = (entry.text_zh || entry.text || "").trim();
  if (!/[\u4e00-\u9fff]/.test(zh)) return;
  if ((entry.text_en || "").trim()) return;
  const key = _normalizeTranscriptText(zh);
  if (!key) return;
  if (glossLineCache.has(key)) {
    entry.text_en = glossLineCache.get(key);
    if (entry.role === "user") userTranslationIndex[key] = entry.text_en;
    return;
  }
  if (_glossFetchInFlight.has(key)) return;
  _glossFetchInFlight.add(key);
  entry._glossPending = true;
  renderTranscript();
  fetch("/api/gloss", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q: zh }),
  })
    .then((r) => r.json())
    .then((j) => {
      if (j && j.ok && j.en && String(j.en).trim()) {
        const en = String(j.en).trim();
        glossLineCache.set(key, en);
        entry.text_en = en;
        if (entry.role === "user") userTranslationIndex[key] = en;
      }
    })
    .catch(() => {})
    .finally(() => {
      entry._glossPending = false;
      _glossFetchInFlight.delete(key);
      renderTranscript();
    });
}

function resolveLineEnglish(entry) {
  if (!entry) return "";
  const direct = (entry.text_en || "").trim();
  if (direct) return direct;
  const key = _normalizeTranscriptText(entry.text_zh || entry.text || "");
  if (!key) return "";
  if (entry.role === "user" && userTranslationIndex[key]) return userTranslationIndex[key];
  if (glossLineCache.has(key)) return glossLineCache.get(key);
  return "";
}

/** EN/PY for repeated partner lines after recovery (repeat / slower); uses current sentence hint for the question body. */
function transcriptExtrasForRecoveryPartnerRepeat(action) {
  const h = window._sentenceHint || {};
  const en = (h.text_en || "").trim();
  const py = (h.pinyin || "").trim();
  if (!en && !py) return {};
  if (action === "slower" && en) {
    return { text_en: "OK, a bit slower: " + en, pinyin: py || "" };
  }
  return { text_en: en, pinyin: py };
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
// Display name for partner header (cleared prefix line must still show "Name:" when frame holds full utterance)
if (typeof window._partnerDisplayName === "undefined") window._partnerDisplayName = "";
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
/** Partner recovery lines already shown for this question frame_id (caps repair spam per frame). */
if (typeof window._recoveryPromptsByFrame === "undefined") window._recoveryPromptsByFrame = {};
// Phase 12C: session arc state
if (typeof window._loopCountInEngine    === "undefined") window._loopCountInEngine    = 0;
if (typeof window._enginesVisited       === "undefined") window._enginesVisited        = ["identity"];
if (typeof window._recentConfusionCount === "undefined") window._recentConfusionCount  = 0;
if (typeof window._repairAttemptCount   === "undefined") window._repairAttemptCount   = 0;
// Phase L1: learner observation counters — observation only, no behavior changes.
// Reset on startFreshLearner. Updated from signal hooks throughout app.js.
if (typeof window._learnerObs === "undefined") window._learnerObs = {
  turns_observed:           0,
  hint_clicks:              0,
  word_clicks:              0,
  recovery_uses:            0,
  successful_answers:       0,
  asr_rejections:           0,
  mirror_uses:              0,   // user clicked a mirror/user-led question
  question_count:           0,   // questions detected in any user text (typed or spoken)
  extended_answer_count:    0,   // answers with length or connector markers
  recovery_resilience_count: 0,  // times user answered again after a repair prompt
};
if (typeof window._seededBridgeEngines  === "undefined") window._seededBridgeEngines   = [];
if (typeof window._mediumProbeFiredEngines === "undefined") window._mediumProbeFiredEngines = [];
if (typeof window._lastRepairKind       === "undefined") window._lastRepairKind         = null;
if (typeof window._prevRepairKind       === "undefined") window._prevRepairKind         = null;
if (typeof window._pendingRepairPrompt  === "undefined") window._pendingRepairPrompt    = false;
if (typeof window._lastRepairSubmittedText === "undefined") window._lastRepairSubmittedText = "";
if (typeof window._lastAcceptedFreeTranscript === "undefined") window._lastAcceptedFreeTranscript = "";
if (typeof window._lastAcceptedFreeTranscriptAt === "undefined") window._lastAcceptedFreeTranscriptAt = 0;
if (typeof window._lastAcceptedFreeFrameId === "undefined") window._lastAcceptedFreeFrameId = "";
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
  window._learnerObs.word_clicks++;           // Phase L1 observation
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
    lastClickedWordId = null;
    window.lastClickedWordId = null;
    // Avoid leaving a previous Explore Word card visible when this tap has no card.
    if (state?.isOpen) dispatch({ type: "CARD_PANEL_CLOSED" });
    const raw = (surfaceText || "").trim();
    const graphemes = [...raw].filter((ch) => _CJK_FOR_PINYIN.test(ch));
    if (graphemes.length >= 1 && graphemes.length <= 16) {
      const lines = [];
      for (const ch of graphemes) {
        const py = pinyinForSingleCharFallback(ch);
        const gloss = resolveGlyphGlossEn(ch);
        const parts = [py, gloss].filter((x) => x && String(x).trim());
        lines.push(parts.length ? `${ch}: ${parts.join(" — ")}` : `${ch}`);
      }
      bodyEl.textContent = lines.join("\n");
      if (etymEl) {
        if (graphemes.length === 1) {
          const html = buildCharacterCoreInsightHTML(graphemes[0]);
          if (html) {
            etymEl.innerHTML = html;
            etymEl.style.display = "block";
          } else {
            etymEl.textContent = "";
            etymEl.style.display = "none";
          }
        } else {
          etymEl.textContent = "";
          etymEl.style.display = "none";
        }
      }
    } else {
      bodyEl.textContent = "Not in lexicon yet.";
      if (etymEl) {
        etymEl.textContent = "";
        etymEl.style.display = "none";
      }
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
  _tracker.card_opens++;
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
function getWordHintDataInner(wordId) {
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

/**
 * When a w_* card exists but omits pinyin and/or meaning (stub), fill from characters_1200 + teaching maps
 * using the card headword graphemes. Does not use resolveGlyphGlossEn (avoids recursion via getWordHintData).
 */
function enrichWordHintFromCharCore(wordId, hint) {
  const py0 = (hint?.pinyin || "").trim();
  const mn0 = (hint?.meaning || "").trim();
  if (py0 && mn0) return hint;
  const cache = window._cardsByIdCache;
  if (!cache || !wordId) return hint;
  const fromIndex = window.cardsIndex?.by_word_id?.[wordId];
  const cid = typeof fromIndex === "string" ? fromIndex : null;
  let card = null;
  for (const c of [cid, wordId]) {
    if (c && cache[c]) {
      card = cache[c];
      break;
    }
  }
  const hw = card?.content?.headword?.hanzi;
  if (!hw || typeof hw !== "string") return hint;
  const _cjk = /[\u4e00-\u9fff\u3400-\u4dbf]/;
  const glyphs = [...hw].filter((ch) => _cjk.test(ch));
  if (!glyphs.length) return hint;
  let py = py0;
  let mn = mn0;
  if (!py) {
    const parts = glyphs.map((c) => pinyinForSingleCharFallback(c)).filter(Boolean);
    if (parts.length) py = parts.join(" ");
  }
  if (!mn) {
    const glossParts = [];
    const coreMap = window._charCoreByHanzi || charCoreByHanzi;
    for (const c of glyphs) {
      const row = coreMap && coreMap[c];
      let g = row?.gloss_en != null && String(row.gloss_en).trim() ? String(row.gloss_en).split(/[;/]/)[0].trim() : "";
      if (!g && (window._radicalVariantGlossEn || {})[c]) g = String((window._radicalVariantGlossEn || {})[c]).trim();
      if (!g && (window._teachingSupplementGlossEn || {})[c]) g = String((window._teachingSupplementGlossEn || {})[c]).trim();
      if (!g) g = GLYPH_TEACHING_GLOSS_EN[c] || "";
      if (g) glossParts.push(g);
    }
    if (glossParts.length) mn = glossParts.join("; ");
  }
  if (!py && !mn) return hint;
  return { pinyin: py || hint.pinyin || "", meaning: mn || hint.meaning || "" };
}

function getWordHintData(wordId) {
  return enrichWordHintFromCharCore(wordId, getWordHintDataInner(wordId));
}

/** Single-Hanzi → word_id using cards cache (same as option tokeniser). */
function resolveWordIdForSingleHanziChar(ch) {
  const s = ch && String(ch).trim();
  if (!s || [...s].length !== 1) return null;
  const map = window._hanziLongestMatchMap || {};
  return map[s] || null;
}

const _CJK_FOR_PINYIN = /[\u4e00-\u9fff\u3400-\u4dbf]/;

/**
 * When `characters_1200` has pinyin: null (auto rows) and no w_* card yet — keep common
 * syllables so sentence hints and taps are not all "(?)".
 */
const PINYIN_TEACHING_FALLBACK = {
  书: "shū",
  法: "fǎ",
  练: "liàn",
  品: "pǐn",
  茶: "chá",
  术: "shù",
  墨: "mò",
  笔: "bǐ",
  纸: "zhǐ",
  画: "huà",
  字: "zì",
  词: "cí",
  读: "dú",
  写: "xiě",
  听: "tīng",
  说: "shuō",
  歌: "gē",
  舞: "wǔ",
  跑: "pǎo",
  游: "yóu",
  泳: "yǒng",
  棋: "qí",
  牌: "pái",
  球: "qiú",
  篮: "lán",
  网: "wǎng",
  影: "yǐng",
  视: "shì",
  音: "yīn",
  乐: "yuè",
  器: "qì",
  钢: "gāng",
  琴: "qín",
  吉: "jí",
  足: "zú",
};

/**
 * Single CJK: characters_1200 → word_etymology hanzi→word_id → longest-match card headword.
 * Used to build sentence-level pinyin when the server sends none.
 */
function pinyinForSingleCharFallback(ch) {
  const c = ch && String(ch).trim();
  if (!c || [...c].length !== 1) return "";
  const coreMap = window._charCoreByHanzi || charCoreByHanzi;
  const row = coreMap && coreMap[c];
  if (row && row.pinyin != null && String(row.pinyin).trim()) return String(row.pinyin).trim();
  const ht = window._hanziToWordId && window._hanziToWordId[c];
  if (ht) {
    const h = getWordHintData(ht);
    if (h.pinyin && String(h.pinyin).trim()) return String(h.pinyin).trim();
  }
  const wid = resolveWordIdForSingleHanziChar(c);
  if (wid) {
    const h = getWordHintData(wid);
    if (h.pinyin && String(h.pinyin).trim()) return String(h.pinyin).trim();
  }
  const teach = PINYIN_TEACHING_FALLBACK[c];
  if (teach && String(teach).trim()) return String(teach).trim();
  return "";
}

/**
 * Pinyin for one tokenised segment: prefer card headword (multi-char), else per-char fallbacks.
 */
function pinyinForSegmentFromLexicon(seg) {
  const t = (seg && seg.t) || "";
  if (!t) return "";
  const wid = seg.word_id;
  if (wid) {
    const h = getWordHintData(wid);
    const py = h.pinyin && String(h.pinyin).trim() ? String(h.pinyin).trim() : "";
    if (py) {
      const graphemes = [...t];
      if (graphemes.length === 1) {
        const first = py.split(/\s+/)[0];
        return (first || py).trim();
      }
      const per = splitHeadwordPinyinToGraphemes(t, py);
      if (per && per.length === graphemes.length) return per.join(" ");
      return py;
    }
  }
  const parts = [];
  for (const ch of t) {
    if (!_CJK_FOR_PINYIN.test(ch)) continue;
    parts.push(pinyinForSingleCharFallback(ch) || "(?)");
  }
  return parts.join(" ");
}

/**
 * Spaced pinyin for a full line when curated pinyin is absent (counter-reply, mirror stubs).
 * Uses longest-match tokenisation (same as options) + characters_1200 + lexicon; unknown syllables as "(?)".
 */
function buildSentencePinyinFromLexicon(zh) {
  const s = zh || "";
  if (!s) return "";
  const segs = tokenizeHanziForOption(s, {});
  const parts = [];
  for (const seg of segs) {
    const t = seg.t || "";
    if (!t) continue;
    const hasCjk = [...t].some((ch) => _CJK_FOR_PINYIN.test(ch));
    if (!hasCjk) continue;
    const pySeg = pinyinForSegmentFromLexicon(seg);
    if (pySeg) parts.push(pySeg);
  }
  return parts.join(" ");
}

/**
 * Prefer server/author `existingPinyin`; otherwise derive from characters_1200 + lexicon.
 */
function fillSentenceHintPinyin(zh, existingPinyin) {
  const ex = existingPinyin != null && String(existingPinyin).trim() ? String(existingPinyin).trim() : "";
  if (ex) return ex;
  return buildSentencePinyinFromLexicon(zh || "");
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
  法: "law; method; way",
  练: "to practise; train",
  品: "quality; taste; savour",
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
    // Clear stale pinyin/English from the previous turn so they don't persist when
    // the new frame has no hint data (e.g. a short closing statement like "这样啊。").
    if (hintPinyin) { hintPinyin.textContent = ""; hintPinyin.style.display = "none"; }
    if (hintMeaning) { hintMeaning.textContent = ""; hintMeaning.style.display = "none"; }
    if (hintEtymEl) { hintEtymEl.innerHTML = ""; hintEtymEl.style.display = "none"; }
    hint_cascade_state = { level: 0, turn_uid: null };
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
    const textEn = resolveLineEnglish(entry);
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
      if (shouldShowEn && (textEn || entry._glossPending || role === "user")) {
        chunks.push(textEn || (entry._glossPending ? "…" : role === "user" ? "…" : ""));
      }
      detail.textContent = chunks.join("  |  ");
      container.appendChild(detail);
    }
  });
  const panel = document.getElementById("transcriptPanel");
  if (panel) panel.scrollTop = panel.scrollHeight;
}

function resolveUserLineTranslation(entry) {
  if (!entry || entry.role !== "user") return "";
  return resolveLineEnglish(entry);
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
      maybeRequestGlossForEntry(entry);
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
const NOT_UNDERSTOOD_ROTATION_ACTION = new Set(["repeat", "slower", "meaning"]);
const NOT_UNDERSTOOD_MOVE_ON_ACTION = "next_turn";
const NOT_UNDERSTOOD_MOVE_ON_AFTER = 3;

/**
 * Learner-side recovery lines only (exclude persona_deflect / deflection_ack).
 * Includes not_understood, topic_reset, topic_shift (v1.2 briefing).
 */
function learnerRecoveryPhrases(data) {
  const arr = (data && data.phrases) || [];
  const uok = new Set(["not_understood", "topic_reset", "topic_shift"]);
  return arr.filter((p) => uok.has(p.use || "not_understood"));
}

/**
 * Phase 12C: strength of partial overlap between transcript and frame options (no exact match).
 * @returns {{ hasPartial: boolean, partialScore: number }}
 */
function optionPartialMatchStrength(transcript, options) {
  if (!transcript || !Array.isArray(options) || options.length === 0) {
    return { hasPartial: false, partialScore: 0 };
  }
  const n = normalizeForMatch(transcript);
  if (!n) return { hasPartial: false, partialScore: 0 };
  let best = 0;
  for (const opt of options) {
    const hanzi = (opt.hanzi || "").trim();
    if (!hanzi) continue;
    const optNorm = normalizeForMatch(hanzi);
    if (optNorm.length >= 2) {
      if (n.includes(optNorm)) best = Math.max(best, optNorm.length / Math.max(n.length, 1));
      if (optNorm.includes(n)) best = Math.max(best, n.length / Math.max(optNorm.length, 1));
    }
    const pinyin = (opt.pinyin || "").trim();
    if (pinyin) {
      const pyNorm = normalizeForMatch(pinyin);
      if (pyNorm.length >= 2) {
        if (n.includes(pyNorm)) best = Math.max(best, pyNorm.length / Math.max(n.length, 1));
        if (pyNorm.includes(n)) best = Math.max(best, n.length / Math.max(pyNorm.length, 1));
      }
    }
  }
  return { hasPartial: best > 0, partialScore: Math.min(1, best) };
}

/** Match user transcript to a learner recovery phrase (explicit repair line). */
function matchTranscriptToLearnerPhrase(transcript, phrases) {
  if (!transcript || !Array.isArray(phrases) || phrases.length === 0) return null;
  const n = normalizeForMatch(transcript);
  if (!n) return null;
  for (const p of phrases) {
    const hz = normalizeForMatch(p.hanzi || "");
    if (hz && (n === hz || (hz.length >= 2 && (n.includes(hz) || hz.includes(n))))) return p;
    const pyRaw = (p.pinyin || "").trim();
    if (pyRaw) {
      const py = normalizeForMatch(pyRaw.replace(/\s+/g, ""));
      if (py.length >= 2 && (n === py || n.includes(py) || py.includes(n))) return p;
    }
  }
  return null;
}

function _pickRandomPhrase(arr) {
  if (!arr || arr.length === 0) return null;
  return arr[Math.floor(Math.random() * arr.length)];
}

function _phrasesByRepairKind(phrases, kind) {
  return phrases.filter((p) => (p.repair_kind || "") === kind);
}

/**
 * Phase 12C: inputs for recovery trigger overlay (client-only).
 * repeat_repair_count = consecutive not-understood recoveries already completed before this turn.
 */
function computeRecoveryTriggerContext(input) {
  const transcript = (input && input.transcript != null) ? String(input.transcript) : "";
  const options = Array.isArray(input?.options) ? input.options : [];
  let asr = input?.asr_confidence;
  if (typeof asr !== "number" || Number.isNaN(asr)) asr = null;

  let asr_confidence_band = "unknown";
  if (asr != null) {
    if (asr < 0.45) asr_confidence_band = "low";
    else if (asr < 0.70) asr_confidence_band = "medium";
    else asr_confidence_band = "high";
  }

  const is_empty_input = !transcript.trim();
  const optPart = optionPartialMatchStrength(transcript, options);
  const has_partial_signal = !!(optPart.hasPartial && optPart.partialScore > 0);
  const repeat_repair_count = Math.max(0, parseInt(input?.repeat_repair_count, 10) || 0);

  const learner = learnerRecoveryPhrases(recoveryPhrasesRuntime || window._recoveryPhrases);
  const explicit_recovery_match = !is_empty_input ? matchTranscriptToLearnerPhrase(transcript, learner) : null;

  return {
    transcript,
    transcript_normalized: normalizeForMatch(transcript),
    is_empty_input,
    asr_confidence: asr,
    asr_confidence_band,
    partial_match_score: optPart.partialScore,
    has_partial_signal,
    repeat_repair_count,
    explicit_recovery_match,
    explicit_recovery_phrase_id: explicit_recovery_match ? explicit_recovery_match.id : null,
    frame_id: input?.frame_id || null,
    frame_recovery_shown: Math.max(0, parseInt(input?.frame_recovery_shown, 10) || 0),
    incomplete_utterance: input?.incomplete_utterance === true,
  };
}

/**
 * Phase 12C: choose a learner recovery phrase using trigger context (additive overlay).
 * Updates window._consecutiveNotUnderstood and _recentConfusionCount once.
 */
function selectRecoveryPhrase(ctx, { phrases, data, avoidPhraseId }) {
  const before = ctx.repeat_repair_count;
  const band = ctx.asr_confidence_band;
  const isEmpty = ctx.is_empty_input;
  const hasPartial = ctx.has_partial_signal;
  const frameRecoveryShown = Math.max(0, parseInt(ctx.frame_recovery_shown, 10) || 0);
  /** After two recovery lines on the same frame, force move-on phrasing (additive cap). */
  const forcePerFrameMoveOn = frameRecoveryShown >= 2;

  const basePhrases = Array.isArray(phrases) ? phrases : [];
  let phrasePool = basePhrases;
  if (ctx.incomplete_utterance === true) {
    phrasePool = basePhrases.filter((p) => p && p.id !== "wo_xiang_xiang" && (p.hanzi || "").trim() !== "我想想");
    if (phrasePool.length === 0) phrasePool = basePhrases;
  }

  let recovery_trigger_reason = "legacy_rotation";
  let repair_kind = null;
  const explicit_recovery_phrase_id = ctx.explicit_recovery_phrase_id || null;
  let chosen = null;

  const tryKind = (kind, reason) => {
    const pool = _phrasesByRepairKind(phrasePool, kind);
    const p = _pickRandomPhrase(pool);
    if (p) {
      recovery_trigger_reason = reason;
      repair_kind = p.repair_kind || kind;
      return p;
    }
    return null;
  };

  if (ctx.explicit_recovery_match) {
    chosen = ctx.explicit_recovery_match;
    recovery_trigger_reason = "explicit_recovery_phrase";
    repair_kind = chosen.repair_kind || null;
  } else if (forcePerFrameMoveOn || before >= 3) {
    // Termination guarantee (Phase 12C): after 3+ consecutive repairs the system MUST
    // exit the repair chain. Bypass simplify/meaning — force next_turn unconditionally.
    const moveOnPool = phrasePool.filter((p) => (p.recovery_action || "") === NOT_UNDERSTOOD_MOVE_ON_ACTION);
    chosen = _pickRandomPhrase(moveOnPool) || moveOnPool[0] || null;
    if (chosen) {
      recovery_trigger_reason = forcePerFrameMoveOn ? "per_frame_recovery_cap" : "tier3_forced_exit";
      repair_kind = chosen.repair_kind || "bridge";
    }
  } else if (isEmpty) {
    if (before === 0) {
      chosen = tryKind("soft_hold", "empty_input_soft_hold")
        || _pickRandomPhrase(phrasePool.filter((p) => (p.recovery_action || "") === "soft"));
      if (chosen) recovery_trigger_reason = chosen.repair_kind === "soft_hold" ? "empty_input_soft_hold" : "empty_input_soft_fallback";
    } else if (before === 1) {
      chosen = tryKind("buffer", "empty_input_buffer")
        || _pickRandomPhrase(_phrasesByRepairKind(phrasePool, "buffer"));
      if (chosen) recovery_trigger_reason = "empty_input_buffer";
    } else {
      chosen = tryKind("meaning", "empty_input_escalate_meaning")
        || tryKind("simplify", "empty_input_escalate_simplify")
        || _pickRandomPhrase(phrasePool.filter((p) => (p.recovery_action || "") === NOT_UNDERSTOOD_MOVE_ON_ACTION));
      if (chosen) recovery_trigger_reason = "empty_input_escalate";
    }
  } else if (band === "low") {
    if (before === 0) {
      chosen = tryKind("soft_hold", "low_asr_soft_hold") || _pickRandomPhrase(phrasePool.filter((p) => (p.recovery_action || "") === "soft"));
    } else if (before === 1) {
      chosen = tryKind("repeat", "low_asr_delivery_repeat")
        || tryKind("slower", "low_asr_delivery_slower")
        || _pickRandomPhrase(phrasePool.filter((p) => NOT_UNDERSTOOD_ROTATION_ACTION.has(p.recovery_action || "")));
    } else {
      chosen = tryKind("simplify", "low_asr_escalate_simplify")
        || tryKind("meaning", "low_asr_escalate_meaning")
        || _pickRandomPhrase(phrasePool.filter((p) => (p.recovery_action || "") === NOT_UNDERSTOOD_MOVE_ON_ACTION));
      if (chosen) recovery_trigger_reason = "low_asr_escalate";
    }
  } else if (band === "medium" || band === "high") {
    if (hasPartial) {
      chosen = tryKind("meaning", "weak_match_meaning") || tryKind("simplify", "weak_match_simplify");
      if (!chosen) chosen = _pickRandomPhrase(_phrasesByRepairKind(phrasePool, "meaning"));
    } else if (ctx.incomplete_utterance === true) {
      chosen = tryKind("repeat", "incomplete_delivery_repeat")
        || tryKind("soft_hold", "incomplete_soft_hold")
        || _pickRandomPhrase(phrasePool.filter((p) => (p.recovery_action || "") === "soft"));
    } else {
      chosen = tryKind("buffer", "stall_buffer") || _pickRandomPhrase(phrasePool.filter((p) => (p.repair_kind || "") === "buffer"));
    }
  } else {
    if (hasPartial) {
      chosen = tryKind("meaning", "unknown_band_partial_meaning") || tryKind("meaning", "unknown_band_meaning");
    } else if (ctx.incomplete_utterance === true) {
      chosen = tryKind("repeat", "unknown_incomplete_repeat")
        || tryKind("soft_hold", "unknown_incomplete_soft")
        || _pickRandomPhrase(phrasePool.filter((p) => (p.recovery_action || "") === "soft"));
    }
  }

  if (!chosen) {
    const consecutive = before + 1;
    if (consecutive === 1) {
      const softPool = phrasePool.filter((p) => (p.recovery_action || "") === "soft");
      if (softPool.length > 0) {
        chosen = _pickRandomPhrase(softPool);
        recovery_trigger_reason = "legacy_soft_first";
        repair_kind = chosen.repair_kind || null;
      }
    }
    if (!chosen && consecutive >= NOT_UNDERSTOOD_MOVE_ON_AFTER) {
      const moveOnPool = phrasePool.filter((p) => (p.recovery_action || "") === NOT_UNDERSTOOD_MOVE_ON_ACTION);
      if (moveOnPool.length > 0) {
        chosen = moveOnPool[0];
        recovery_trigger_reason = "legacy_move_on";
        repair_kind = chosen.repair_kind || null;
      }
    }
    if (!chosen) {
      const rotationPool = phrasePool.filter((p) => NOT_UNDERSTOOD_ROTATION_ACTION.has(p.recovery_action || ""));
      const pool = rotationPool.length > 0 ? rotationPool : phrasePool;
      if (avoidPhraseId && pool.length > 1) {
        const i = pool.findIndex((p) => p.id === avoidPhraseId);
        const nextIdx = i >= 0 ? (i + 1) % pool.length : 0;
        chosen = pool[nextIdx];
      } else {
        const defaultId = data.default_for_not_understood;
        const found = defaultId ? pool.find((p) => p.id === defaultId) : null;
        chosen = found || pool[0] || phrasePool[0];
      }
      recovery_trigger_reason = "legacy_rotation";
      repair_kind = chosen.repair_kind || repair_kind;
    }
  }

  if (!chosen) {
    chosen = phrasePool[0];
    recovery_trigger_reason = "emergency_fallback";
    repair_kind = chosen.repair_kind || null;
  }

  window._consecutiveNotUnderstood = before + 1;
  window._recentConfusionCount = (window._recentConfusionCount || 0) + 1;
  window._prevRepairKind = window._lastRepairKind || null;
  window._lastRepairKind = chosen.repair_kind || null;

  const recovery_trace = {
    recovery_trigger_reason,
    repair_kind: repair_kind || chosen.repair_kind || null,
    asr_confidence_band: band,
    repeat_repair_count: before,
    frame_recovery_shown: frameRecoveryShown,
    explicit_recovery_phrase_id: explicit_recovery_phrase_id || null,
    asr_confidence: ctx.asr_confidence,
    partial_match_score: ctx.partial_match_score,
    has_partial_signal: hasPartial,
    is_empty_input: isEmpty,
    chosen_phrase_id: chosen.id,
  };

  emitUITrace({
    type: "RECOVERY_TRIGGER",
    timestamp: new Date().toISOString(),
    payload: recovery_trace,
  });

  return {
    id: chosen.id,
    hanzi: chosen.hanzi,
    pinyin: chosen.pinyin || "",
    text_en: chosen.text_en || chosen.meaning || "",
    etymology: chosen.etymology || "",
    recovery_action: chosen.recovery_action || "repeat",
    recovery_trace,
  };
}

/**
 * Thin wrapper: uses precomputed trigger context when provided; otherwise minimal context (legacy callers).
 */
function getRecoveryPhraseForNotUnderstood(avoidPhraseId = null, precomputedContext = null) {
  const data = recoveryPhrasesRuntime || window._recoveryPhrases;
  // Phase 12D: partner auto-selects only from CORE_RECOVERY_SET + EXIT (好吧).
  // Non-core phrases (e.g. 可以简单说吗？, 换个话题吧) are excluded from auto-selection.
  // Phrases marked speaker:"learner" (等一下, 我想想) are learner-owned pause/buffer phrases —
  // the app must not say them when signalling misunderstanding; they remain in the learner panel.
  // The full list is still used for explicit_recovery_match (ASR recognition of learner speech).
  const phrases = learnerRecoveryPhrases(data).filter(
    (p) => (p.always_surface === true || p.routing_group === "EXIT") && p.speaker !== "learner"
  );
  if (!data || phrases.length === 0) {
    const recovery_trace = {
      recovery_trigger_reason: "no_runtime_phrases",
      repair_kind: null,
      asr_confidence_band: "unknown",
      repeat_repair_count: window._consecutiveNotUnderstood || 0,
      explicit_recovery_phrase_id: null,
      asr_confidence: null,
    };
    emitUITrace({ type: "RECOVERY_TRIGGER", timestamp: new Date().toISOString(), payload: recovery_trace });
    return {
      id: "fallback",
      hanzi: "什么？再说一次。",
      pinyin: "Shénme? Zài shuō yí cì.",
      text_en: "What? Say it again?",
      etymology: "",
      recovery_action: "repeat",
      recovery_trace,
    };
  }
  const ctx = precomputedContext
    || computeRecoveryTriggerContext({
      transcript: "",
      options: [],
      asr_confidence: null,
      frame_id: null,
      repeat_repair_count: window._consecutiveNotUnderstood || 0,
    });
  const selected = selectRecoveryPhrase(ctx, { phrases, data, avoidPhraseId });
  // Hard block: these are learner-owned pause phrases that must never be emitted
  // by the app as a misunderstanding response, regardless of runtime data state.
  const _LEARNER_PAUSE_PHRASES = new Set(["等一下", "等一等", "等等"]);
  if (_LEARNER_PAUSE_PHRASES.has((selected.hanzi || "").trim())) {
    console.warn("[recovery] blocked learner-owned phrase:", selected.hanzi, "— using fallback");
    return phrases.find((p) => p.id === "a") || phrases.find((p) => p.hanzi === "啊？") || {
      id: "a_fallback",
      hanzi: "啊？",
      pinyin: "a?",
      text_en: "Huh?",
      recovery_action: "soft",
      recovery_trace: selected.recovery_trace,
    };
  }
  return selected;
}

/** Normalize for match: trim, collapse spaces, remove common punctuation. */
function normalizeForMatch(s) {
  if (typeof s !== "string") return "";
  return s.trim().replace(/\s+/g, "").replace(/[。？！，、；：""''\s]/g, "");
}

/** Single-token fillers / fragments — not substantive answers; avoid persona-stall recovery tone. */
function isIncompleteLearnerUtterance(transcript) {
  const raw = (transcript || "").trim();
  if (!raw) return false;
  const t = normalizeForMatch(raw);
  if (!t) return false;
  const fillers = new Set(["我", "嗯", "啊", "呃", "哦", "喔", "哎", "诶", "这个", "那个", "就是"]);
  if (fillers.has(t)) return true;
  if (t.length === 1 && /[\u4e00-\u9fff]/.test(t)) return true;
  return false;
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
    // Identity (incl. nickname + name-story questions — free-text answers common)
    "f_ask_you_name", "p2_id_2", "p2_id_4", "p2_id_5", "f_ask_name_meaning",
    "f_id_friends_call", "f_probe_id_nickname", "f_name_story", "f_name_story_elicit", "f_how_old",
    // Place — life-quality, local character, leisure, and travel questions are all open
    "f_from_where", "frame.location.live_question",
    "f_place_why_like", "f_place_like_there",
    "f_probe_place_miss", "f_probe_place_moved", "f_probe_place_stay", "f_probe_place_why_move",
    "f_place_travel",  // 你会去别的地方吗？ — any destination answer is valid
    "p2_pl_1", "p2_pl_ext1", "p2_pl_3", "p2_pl_4",
    // Family — open questions that invite any free answer
    "f_have_family", "f_have_siblings", "p2_fa_1", "p2_fa_2", "p2_fa_5",
    // Family member / living-with questions: "爸爸妈妈老婆" / "我老婆" are valid free answers
    "f_live_with_who", "p2_fa_live_with", "f_probe_family_closest",
    // Family activity: "吃饭", "一起出去" etc. are valid free answers
    "p2_fa_activity", "f_probe_family_together",
    // Work — retirement / job description can be anything
    "f_what_work", "f_like_work", "p2_wk_1", "p2_wk_2",
    // Work duration: "20年", "很多年" are valid answers here
    "f_work_tenure",
    // Hobby — "what are your hobbies" is inherently open
    "f_what_hobby", "f_often_do", "f_like_do_what", "f_weekend_do",
    "f_difficult_ma", "f_recommend_ma", "p2_hb_1", "p2_hb_2",
    // Hobby duration (how long have you done this)
    "p2_hb_5",
    // Food & travel
    "f_food_what_good", "f_travel_where", "f_want_go_where",
    // Travel depth: "why go there", "what's fun", "how was the trip" — any feeling/reason is valid
    "f_travel_why_want_go", "p2_tr_3", "p2_tr_4",
    // Travel narrowing frames: city/province answers are valid free answers
    "f_travel_narrow_city", "f_travel_dest_generic_clarify",
    // Emotional / health check-in: "现在怎么样？" — any meaningful reply is valid
    "f_probe_emotional_checkin",
    // Hobby probe: how/why/social follow-ups accept any explanation
    "f_probe_hobby_origin", "f_probe_hobby_social", "f_probe_hobby_change",
  ]).has(fid);
}

/** Frames where learners often give foreign place names (Christchurch, Auckland) — Latin-heavy text is valid. */
const _MIXED_SCRIPT_PLACE_FRAMES = new Set([
  "frame.location.live_question",
  "p2_pl_ext1",
  "f_from_where",
]);

/** Partner asked how others address the learner — includes legacy p2_id_2 wording. */
const _NICKNAME_CALL_FRAMES = new Set(["f_id_friends_call", "f_probe_id_nickname", "p2_id_2"]);

function containsLatinNameLikeContent(text) {
  return typeof text === "string" && /[A-Za-z]{2,}/.test(text);
}

/** Heuristic: nickname / call-name reply (tolerates 教 misread for 叫). */
function looksLikeNicknameCallAnswer(transcript, frameId) {
  if (!_NICKNAME_CALL_FRAMES.has((frameId || "").trim())) return false;
  const t = (transcript || "").trim();
  if (!t) return false;
  if (/叫我|大家叫我|朋友们叫我|朋友叫我/.test(t)) {
    if (containsLatinNameLikeContent(t)) return true;
    const afterCall = (t.split(/叫/).pop() || "").replace(/我|的|了|是|说|嘛|呀|哦|喔/g, "");
    if ((afterCall.match(/[\u4e00-\u9fff]/g) || []).length >= 2) return true;
  }
  const subject = /朋友|家里人|家人|他们|他|她|大家|人们|别人/.test(t);
  const verb = /叫|教/.test(t);
  const me = /我/.test(t);
  if (subject && verb && me) {
    if (containsLatinNameLikeContent(t)) return true;
    const stripped = t.replace(
      /我的朋友|人们|别人|朋友|家里人|家人|他们|他|她|大家|一般|通常|都|会|叫|教|我|的|了|是|说|被|怎么|如何|么|嘛|呀|哦|喔|给|被|一般|通常/g,
      "",
    );
    if ((stripped.match(/[\u4e00-\u9fff]/g) || []).length >= 2) return true;
  }
  if (/^[A-Za-z][A-Za-z\s.'-]{0,28}[A-Za-z]$/.test(t.trim())) return true;
  return false;
}

function isLikelyUnderstandableFreeAnswer(text, frameId = "") {
  const s = (text || "").trim();
  if (!s) return false;
  // Duration answers: "20年", "5天" — zhCount=1 fails the < 2 guard below, but these are valid.
  if (_DURATION_ANSWER_PAT.test(s)) return true;
  const fid = (frameId || "").trim();
  const zhMatches = s.match(/[\u4e00-\u9fff]/g) || [];
  const zhCount = zhMatches.length;
  const latinCount = (s.match(/[A-Za-z]/g) || []).length;
  // Too short in Chinese usually means we likely misheard.
  if (zhCount > 0 && zhCount < 2) return false;
  // Mixed-script is common for names in identity frames (e.g., Raymond) and nickname-call questions.
  const identityOpen = new Set([
    "f_ask_you_name", "p2_id_2", "p2_id_4", "p2_id_5", "f_ask_name_meaning",
    "f_id_friends_call", "f_probe_id_nickname", "f_how_old",
  ]).has(fid);
  const placeMixedScript = _MIXED_SCRIPT_PLACE_FRAMES.has(fid);
  if (!identityOpen && !placeMixedScript && latinCount > zhCount + 2) return false;
  // Repeated single word noise (e.g., 牛肉牛肉牛肉) should trigger repair.
  const norm = s.replace(/[，。！？、\s]/g, "");
  if (norm.length >= 4) {
    const half = Math.floor(norm.length / 2);
    if (half > 0 && norm.slice(0, half) === norm.slice(half)) return false;
  }
  // Same Hanzi 3+ times in a row (e.g. 拿拿拿, 呃呃呃) — hesitation / ASR noise, not a place answer.
  if (/([\u4e00-\u9fff])\1{2,}/.test(norm)) return false;
  // "Where do you live?" — name-only clauses (我叫…) with no place cue are usually wrong-Q or garbled ASR.
  if (_MIXED_SCRIPT_PLACE_FRAMES.has(fid) && /我叫|大家叫我|我的名字/.test(norm)) {
    const hasPlaceCue =
      /住/.test(norm) ||
      /[A-Za-z]/.test(s) ||
      /(北京|上海|成都|香港|台湾|广州|深圳|西安|奥克兰|惠灵顿|新西兰|纽约|伦敦|悉尼|墨尔本|洛杉矶|温哥华|多伦多|国|市|区|县|村|镇|国外|国内|海外|那儿|这里|那边)/.test(norm) ||
      /在(这儿|那里|那边|国内|国外)/.test(norm);
    if (!hasPlaceCue) return false;
  }
  return s.length >= 2;
}

/**
 * Detect the semantic intent category of user input using keyword clusters.
 * Called AFTER semanticSoftMatch returns false — if we can identify *what* the
 * learner is trying to say, we route to targeted clarification instead of generic
 * repair (啊？). Returns a category string or null.
 *
 * Categories: "name" | "food" | "duration" | "family_health" | "family" |
 *             "work_status" | "location"
 */
function _detectSemanticCategory(text) {
  const t = (text || "").trim();
  if (!t) return null;
  if (/我叫|名字|英文名|[A-Za-z]{3,}/.test(t)) return "name";
  if (/吃|喜欢吃|牛肉|羊肉|好吃|食物/.test(t)) return "food";
  if (_DURATION_ANSWER_PAT.test(t) || /很多年|几年|很久/.test(t)) return "duration";
  if (/身体|健康|好多了|好很多|好一点|不好|生病|康复/.test(t)) return "family_health";
  if (/爸爸|妈妈|太太|家人|老婆|父母|家里|爱人|老公/.test(t)) return "family";
  if (/退休|以前.*工作|以前是|做.*工作/.test(t)) return "work_status";
  if (/住在|搬到|搬来/.test(t)) return "location";
  // "哪里什么" / "哪儿什么" — learner confused about a location prompt → treat as location
  if (/^哪里|^哪儿/.test(t)) return "location";
  return null;
}

/** Targeted clarification phrases indexed by semantic category.
 *  Displayed instead of generic 啊？ when intent is detectable but answer is too noisy to accept. */
const _SEMANTIC_CLARIFICATION_PHRASES = {
  name:          { hanzi: "你是说你的英文名字吗？",     pinyin: "nǐ shì shuō nǐ de yīngwén míngzi ma?",   text_en: "Do you mean your English name?" },
  food:          { hanzi: "你最喜欢吃什么？",           pinyin: "nǐ zuì xǐhuān chī shénme?",              text_en: "What do you like eating most?" },
  duration:      { hanzi: "大概多少年了？",             pinyin: "dàgài duōshǎo nián le?",                 text_en: "About how many years?" },
  family_health: { hanzi: "现在好一点了吗？",           pinyin: "xiànzài hǎo yīdiǎn le ma?",              text_en: "Is it a bit better now?" },
  family:        { hanzi: "是说你的家人吗？",           pinyin: "shì shuō nǐ de jiārén ma?",              text_en: "Are you talking about your family?" },
  work_status:   { hanzi: "你是说你已经退休了吗？",     pinyin: "nǐ shì shuō nǐ yǐjīng tuìxiū le ma?",   text_en: "Do you mean you've retired?" },
  location:      { hanzi: "你是说一个城市吗？",         pinyin: "nǐ shì shuō yīgè chéngshì ma?",          text_en: "Are you referring to a city?" },
};

/** Returns the targeted clarification phrase object for the given category, or null. */
function _getSemanticClarification(category) {
  return _SEMANTIC_CLARIFICATION_PHRASES[category] || null;
}

/**
 * Build a context-anchored restatement for when the learner echoes back our
 * "哪里？" / "在哪里？" probe with confusion ("哪里什么").
 * Uses the learner's previous accepted answer as the reference so the output
 * reads "我是问：你说「X」，是在哪里？" rather than the terse generic probe.
 */
function _buildWhereRestatement(prevUserText) {
  const clipped = (prevUserText || "").trim().slice(0, 12);
  const inner = clipped ? `你说"${clipped}"，是在哪里？` : "在哪里？";
  return { hanzi: `我是问：${inner}`, pinyin: "", text_en: "I'm asking: where was that?" };
}


/**
 * Replace ambiguous place pronouns (那儿 / 那里) with an anchored reference when
 * a specific place was recently mentioned. Keeps partner text coherent after e.g.
 * "我想去甘肃" → next frame "那你喜欢在那儿生活吗？" becomes "在甘肃那边生活吗？".
 * Conservative: only rewrites "在那儿" and "在那里" patterns, not bare 那个地方.
 *
 * Also expands the ultra-terse micro-probe "哪里？" (f_micro_probe_where) that appears
 * after an echo-reaction, so "哦，很好吃！哪里？" becomes "哦，很好吃！你是说在哪里？"
 */
function _anchorVagueReferences(text, place) {
  if (!text) return text;
  // The frame fires after an echo like "哦，很好吃！" making the compound too cryptic.
  if (text.trim() === "哪里？" || text.trim() === "哪里?") {
    return place ? `你是说${place}吗？` : "你是说在哪里？";
  }
  // "...！哪里？" → "...！你是说在哪里？" (anchored where possible)
  text = text.replace(/([！!])\s*哪里[?？]\s*$/,
    place ? `$1 你是说${place}吗？` : "$1 你是说在哪里？"
  );
  if (!place) return text;
  return text
    .replace(/在那儿/g, `在${place}那边`)
    .replace(/在那里/g, `在${place}那边`);
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
  // Scenery / place-quality free answers (often unmatched to word tiles)
  if (/(风景|山水|漂亮|好看|很美|美|空气|环境|舒服|安静|不错|挺好|海|湖|山|树|绿)/.test(t)) return true;
  // Travel destination answers — scoped to frames where "going somewhere" is the actual question.
  // Prevents "中国" / "会去" from triggering travel matching on identity or origin questions.
  const _TRAVEL_DEST_FRAMES = new Set([
    "f_place_travel",              // 你会去别的地方吗？
    "f_travel_where",              // 你去过哪里？
    "f_want_go_where",             // 你想去哪里？
    "f_want_go_place",             // 你想去的地方
    "f_travel_narrow_city",        // 你想去哪个城市？ (narrowing step)
    "f_travel_dest_generic_clarify", // 那你说的是哪里？ (clarification)
    "p2_tr_1", "p2_tr_2", "p2_tr_3", "p2_tr_4",
  ]);
  if (_TRAVEL_DEST_FRAMES.has(fid) || /^(f_travel|p2_tr)/.test(fid)) {
    // Travel-verb patterns: "我会去中国", "我要去日本", "我打算去欧洲"
    if (/会去|要去|去过|打算去|计划去/.test(t)) return true;
    // Country / region names are only valid destination signals inside travel frames
    if (/(中国|日本|英国|美国|法国|德国|澳大利亚|加拿大|欧洲|亚洲|新西兰|香港|台湾|韩国|东南亚|泰国|印度|新加坡|越南|意大利|西班牙)/.test(t)) return true;
  }
  // Foreign city / region names in Latin (Christchurch is longer than Dunedin — same rule as identity mixed-script).
  if (_MIXED_SCRIPT_PLACE_FRAMES.has(fid) && /[\u4e00-\u9fff]/.test(t) && /[A-Za-z]/.test(t)) return true;
  // Identity: how people call you — tolerate ASR / mixed-script name answers.
  if (_NICKNAME_CALL_FRAMES.has(fid)) {
    if (looksLikeNicknameCallAnswer(t, fid)) return true;
    if (t.includes("叫我") || t.includes("大家叫")) return true;
    const hasZh = /[\u4e00-\u9fff]/.test(t);
    const hasLatin = /[A-Za-z]/.test(t);
    if (hasZh && hasLatin) return true;
  }
  // Food frames: accept food nouns combined with any evaluator, and standalone good/bad evaluators.
  // Covers: "羊肉不错", "饺子很好吃", "面条挺好", "这里的羊肉不错", "有很多好吃的东西".
  const _FOOD_FRAMES = new Set(["f_food_what_good", "f_food_tasty", "f_food_famous_dish", "f_food_like_spicy", "f_food_expensive"]);
  if (_FOOD_FRAMES.has(fid)) {
    if (/羊肉|牛肉|猪肉|鸡肉|鱼|面|饺子|火锅|米饭|汤|菜|包子|烤|粥|寿司|蛋糕|海鲜|蔬菜|水果/.test(t)) return true;
    if (/不错|好吃|很好|好香|很香|挺好|非常好|很棒|好喝|很甜|很辣|很鲜|好吃的/.test(t)) return true;
    if (/不知道|没有|不清楚|都行|随便/.test(t)) return true;
  }
  // Family frequency: accept natural free responses about seeing family.
  if (fid === "p2_fa_2") {
    if (/(家人|妈妈|爸爸|父母)/.test(t) && /(天|周|月|常|每天|经常|周末)/.test(t)) return true;
  }
  // Family member / living-with frames: accept any answer naming a family relationship.
  // Covers: "爸爸妈妈老婆", "我老婆", "家里人", "我和父母", "妻子孩子" etc.
  const _FAMILY_MEMBER_FRAMES = new Set([
    "f_live_with_who", "p2_fa_live_with", "f_probe_family_closest", "f_probe_family_together",
    "f_probe_family_influence",
  ]);
  if (_FAMILY_MEMBER_FRAMES.has(fid)) {
    if (/(老婆|妻子|老公|丈夫|先生|爱人|妈妈|爸爸|母亲|父亲|父母|哥哥|弟弟|姐姐|妹妹|儿子|女儿|孩子|家人|家里|爷爷|奶奶|外公|外婆)/.test(t)) return true;
    if (/(一个人|自己住|单独住|独居|和.*一起住|跟.*住)/.test(t)) return true;
  }
  // Family activity frames: accept any activity as a valid answer.
  // Covers: "吃饭", "一起出去", "我们最喜欢吃饭", "散步", etc.
  const _FAMILY_ACTIVITY_FRAMES = new Set(["p2_fa_activity", "f_probe_family_together"]);
  if (_FAMILY_ACTIVITY_FRAMES.has(fid)) {
    if (/[\u4e00-\u9fff]{2,}/.test(t)) return true;  // any 2+ Chinese chars is a valid activity answer
  }
  // Work "why like this job": accept reason-like content.
  if (fid === "p2_wk_1") {
    if (/(因为|为了|可以|能|学|帮助|工资|时间|喜欢)/.test(t)) return true;
  }
  // Duration tenure: "20年", "5年", "很多年" for work or hobby duration frames.
  // isLikelyUnderstandableFreeAnswer returns false for "20年" (zhCount=1); catch it here.
  const _DURATION_FRAMES = new Set(["f_work_tenure", "p2_hb_5"]);
  if (_DURATION_FRAMES.has(fid) && (_DURATION_ANSWER_PAT.test(t) || /很多年|几年|很久|多年/.test(t))) return true;
  // Family health / emotional check-in: accept any meaningful response to "now how is it?".
  if (fid === "f_probe_emotional_checkin") {
    if (/身体|健康|好多了|好很多|好一点|不好|生病|康复|恢复|没事了|好转|现在好/.test(t)) return true;
    if (/[\u4e00-\u9fff]{3,}/.test(t)) return true;  // 3+ Chinese chars is a valid "how is it now?" reply
  }
  // Name-statement frames: "我叫X" / "英文名" / Latin name in frames asking the learner's name.
  const _NAME_STATEMENT_FRAMES = new Set(["f_ask_you_name", "p2_id_4", "p2_id_5", "f_name_story", "f_name_story_elicit"]);
  if (_NAME_STATEMENT_FRAMES.has(fid)) {
    if (/我叫|名字是|英文名|[A-Za-z]{2,}/.test(t)) return true;
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

/** True when the learner is asking about a word/meaning or probing their home country — not a repair "not understood" signal. */
function isLexicalContentQuestion(transcript) {
  const s = (transcript || "").trim();
  if (!s) return false;
  if (/(是什么|什么意思|什么意思啊|什么意思呢|什么叫|指的是什么)/.test(s)) return true;
  if (/新西兰/.test(s) && /(哪里|最有|最好|好玩|有趣|特别)/.test(s)) return true;
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
  if (isLexicalContentQuestion(transcript)) return { accept: true, reason: "lexical_content_question" };
  // Linguistic confusion signal: learner echoes the frame's question word + "什么" to express
  // confusion ("哪里什么" = "what do you mean by 'where'?"). Reject so the not-understood path
  // fires with a targeted clarification rather than accepting and sending to the server.
  const _isLinguisticConfusion = /^(哪里什么|哪儿什么|什么哪里|什么哪儿|哪里啊什么|哪里啊)/i.test((transcript || "").trim());
  if (_isLinguisticConfusion) return { accept: false, reason: "linguistic_confusion_signal" };
  if (opts.length === 0) return { accept: true, reason: "no_options" };
  if (semantic) return { accept: true, reason: "semantic_soft_match" };
  // Emotional vocabulary: feeling/enjoyment words are valid answers to "why/how" type frames
  // regardless of whether the frame is explicitly open-ended. Guard: not a structured slot drill.
  const _hasEmotionalVocab = /(开心|快乐|好玩|有趣|放松|舒服|满足|享受|高兴|愉快|幸福|有意思|很好玩|很舒服|很开心|让我|使我)/.test(transcript || "");
  if (_hasEmotionalVocab && !hasStructuredSlots) return { accept: true, reason: "emotional_vocab_match" };
  // One-strike fallback: after one repair attempt, accept any substantive Chinese answer
  if ((unmatchedCount || 0) >= 1 && understandable) return { accept: true, reason: "one_strike_substantive_fallback" };
  // Topic persistence: after 2+ rejections, accept if a semantic category is detectable —
  // the learner is clearly trying to answer on-topic, even if phrasing is too garbled for
  // the stricter understandability check above.
  if ((unmatchedCount || 0) >= 2 && _detectSemanticCategory(transcript)) {
    return { accept: true, reason: "topic_persistence_semantic" };
  }
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
// Milliseconds of silence after the last detected speech before the turn ends.
// Increase this to give learners more time to construct sentences.
const SPEECH_SILENCE_MS = 3000;

// ── Listening state indicator ────────────────────────────────────────────────
// Drives #listenStatus through: idle → listening → waiting → processing → idle.
// No Chinese text — system feedback is always in English for clarity.
function _setListenState(state) {
  const el = document.getElementById("listenStatus");
  if (!el) return;
  el.dataset.state = state;
  switch (state) {
    case "listening":
      el.innerHTML = '<span class="listen-icon">🎙️</span><span>Listening…</span>';
      break;
    case "waiting":
      el.innerHTML = '<span class="listen-icon">🎙️</span><span>Keep speaking or pause to finish</span>';
      break;
    case "processing":
      el.innerHTML = '<span class="listen-spinner"></span><span>Processing…</span>';
      break;
    default:
      el.innerHTML = "";
      break;
  }
}

function listenForResponse(options, timeoutMs) {
  return new Promise((resolve) => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      emitUITrace({ type: "SPEECH_NOT_AVAILABLE", timestamp: new Date().toISOString(), payload: { message: "SpeechRecognition not supported" } });
      resolve({ transcript: "", matchedOption: null, asr_confidence: null });
      return;
    }
    // Stop partner TTS before opening the mic — prevents ASR from transcribing speaker output
    // (echo loop: app "talking to itself" / user line duplicating partner line).
    try {
      if (window.speechSynthesis) window.speechSynthesis.cancel();
    } catch (_) {}
    const postCancelDelayMs = 380;

    const rec = new SpeechRecognition();
    // continuous=true keeps the mic open across pauses so we control when the turn ends
    // via SPEECH_SILENCE_MS rather than the browser's built-in ~1 s VAD cutoff.
    rec.continuous = true;
    rec.lang = "zh-CN";
    rec.interimResults = true;
    let finalTranscript = "";
    let lastConf = null;
    let resolved = false;
    let silenceTid = null;
    let wallClockTid = null;
    let waitingTid = null;   // transitions indicator to "waiting" ~800ms after last speech event
    let speechStarted = false;
    // Wall-clock budget once speech has begun — gives slow learners time to complete sentences.
    const SPEECH_ACTIVE_MAX_MS = 13000;

    // ── finish(reason): single guarded submission point ─────────────────────
    // Called by the silence timer, wall-clock timer, or onend (backup).
    // Whichever fires first wins; all subsequent calls are no-ops.
    function finish(reason) {
      if (resolved) return;
      resolved = true;
      console.log(`[ASR] finish: reason=${reason}, transcript="${finalTranscript}"`);
      if (silenceTid)  { clearTimeout(silenceTid);  silenceTid  = null; }
      if (wallClockTid){ clearTimeout(wallClockTid); wallClockTid = null; }
      if (waitingTid)  { clearTimeout(waitingTid);  waitingTid  = null; }
      _setListenState("processing");
      try { rec.abort(); } catch (_) {}
      const matched = matchTranscriptToOption(finalTranscript, options || []);
      const ac = typeof lastConf === "number" && !Number.isNaN(lastConf) ? lastConf : null;
      resolve({ transcript: finalTranscript, matchedOption: matched ?? null, asr_confidence: ac });
    }

    function resetSilenceTimer() {
      if (resolved) return;
      if (silenceTid) clearTimeout(silenceTid);
      // Fire finish() directly — no dependency on rec.stop() → onend chain.
      silenceTid = setTimeout(() => {
        console.log(`[ASR] silence timeout fired, transcript="${finalTranscript}"`);
        finish("silence");
      }, SPEECH_SILENCE_MS);
    }

    rec.onresult = (e) => {
      // On first speech: swap the short "never-spoke" wall-clock for a longer active-speech cap.
      if (!speechStarted) {
        speechStarted = true;
        if (wallClockTid) { clearTimeout(wallClockTid); wallClockTid = null; }
        wallClockTid = setTimeout(() => {
          console.log("[ASR] active-speech wall-clock fired");
          finish("wall_clock_active");
        }, SPEECH_ACTIVE_MAX_MS);
        console.log(`[ASR] speech started — active wall-clock set to ${SPEECH_ACTIVE_MAX_MS}ms`);
      }

      // Append only NEW final segments using resultIndex (prevents re-reading old ones).
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) {
          const seg = e.results[i][0];
          finalTranscript += seg.transcript;
          if (typeof seg.confidence === "number") lastConf = seg.confidence;
          console.log(`[ASR] onresult isFinal: "${seg.transcript}" → accumulated: "${finalTranscript}"`);
        }
      }
      finalTranscript = finalTranscript.trim();
      // Show "Listening…" while speech is active; after 800ms of silence switch to "waiting".
      _setListenState("listening");
      if (waitingTid) clearTimeout(waitingTid);
      waitingTid = setTimeout(() => {
        if (!resolved) _setListenState("waiting");
      }, 1400);
      // Reset silence timer on every speech event so mid-sentence pauses don't end the turn.
      resetSilenceTimer();
    };

    // onend is a backup: fires if rec.stop() / rec.abort() is called or browser ends on its own.
    rec.onend = () => {
      console.log(`[ASR] onend fired, transcript="${finalTranscript}"`);
      finish("onend");
    };

    rec.onerror = (e) => {
      console.log(`[ASR] onerror: ${e.error}`);
      if (e.error === "aborted") return;    // expected when finish() calls rec.abort()
      if (e.error === "no-speech") return;  // let silence/onend handle the empty-speech case
      finish("error");
    };

    setTimeout(() => {
      if (resolved) return;
      // Wall-clock limit: only fires if the learner never speaks at all.
      wallClockTid = setTimeout(() => {
        console.log("[ASR] wall-clock timeout fired");
        finish("wall_clock");
      }, timeoutMs);
      // Silence timer starts immediately — covers "user never speaks" before wall-clock fires.
      resetSilenceTimer();
      try {
        rec.start();
        _setListenState("listening");
        emitUITrace({ type: "SPEECH_LISTEN_START", timestamp: new Date().toISOString(), payload: { lang: "zh-CN", silence_ms: SPEECH_SILENCE_MS } });
      } catch (err) {
        console.log(`[ASR] rec.start() error: ${err}`);
        finish("start_error");
      }
    }, postCancelDelayMs);
  });
}

// Segments for "你呢？" so each word opens the card panel when clicked (2nd+ turns)
const ACTIVE_NE_SEGMENTS = [{ t: "你", word_id: "w_ni" }, { t: "呢", word_id: "w_ne" }, { t: "？" }];

/**
 * #frameSentence holds the full partner utterance — clear stale voice-line / recovery text from
 * #partnerPrefixLine (Phase 11C) so it does not compete with the active line.
 */
function syncPartnerHeaderWhenFrameSentenceIsPrimary() {
  const nm = (window._partnerDisplayName || "").trim();
  if (nm) _updatePartnerHeader(nm, "", "");
  else _updatePartnerHeader("", "", "");
}

/** Show or clear the English translation below the active frame sentence.
 *  In challenge mode the English is intentionally hidden until the learner clicks ? twice;
 *  it is revealed there via #hintMeaning, not this element. */
function _setFrameEnglish(enText) {
  const el = document.getElementById("frameEnglish");
  if (!el) return;
  if (_challenge.active) {
    el.textContent = "";
    el.style.display = "none";
    return;
  }
  const t = (enText || "").trim();
  el.textContent = t;
  el.style.display = t ? "block" : "none";
}

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
  syncPartnerHeaderWhenFrameSentenceIsPrimary();
  if (!turnUidForHint) {
    el.textContent = str;
    _setFrameEnglish("");
    return;
  }
  const turnUid = turnUidForHint;
  const effectiveSegments =
    Array.isArray(segments) && segments.length > 0
      ? segments
      : tokenizeHanziForOption(str, {});
  if (effectiveSegments.length > 0) {
    for (const seg of effectiveSegments) {
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
    const wasHidden = cardPanel.classList.contains("hidden");
    cardPanel.classList.remove("hidden");
    noCard.style.display = "none";
    // Only scroll when the panel just became visible (card newly opened).
    if (wasHidden) {
      setTimeout(() => cardPanel.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    }
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
        window._partnerDisplayName = (p.display_name || "").trim();
        _updatePersonaBtnState();
      });
      btns.appendChild(btn);
    });
    // Auto-select: if no partner is set yet, default to the first available persona.
    if (!window._partnerId && personas.length > 0) {
      window._partnerId = personas[0].id;
      window._partnerDisplayName = (personas[0].display_name || "").trim();
    }
    if (window._partnerId) {
      const sel = personas.find((x) => x && x.id === window._partnerId);
      if (sel) window._partnerDisplayName = (sel.display_name || "").trim();
    }
    _updatePersonaBtnState();
  } catch (e) {
    console.warn("[app] loadPersonas failed:", e);
  }
}

function _updatePersonaBtnState() {
  const btns = document.getElementById("personaBtns");
  if (!btns) return;
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
  // Challenge Mode: show partner name only — suppress Chinese prefix and discoverable fact
  if (_challenge.active) {
    if (partnerName) { nameLabel.textContent = `${partnerName}:`; prefixLine.textContent = ""; header.style.display = "flex"; }
    else header.style.display = "none";
    if (factLine) factLine.style.display = "none";
    return;
  }
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

// Priority frames shown at the top of the dropdown (in declared order).
// These bypass the starter-candidate filter — f_from_where is slotted but is
// handled server-side via reciprocal alias and is intentionally kept here.
const _PRIORITY_FRAME_IDS = [
  "f_from_where",
  "f_what_work",
  "f_ask_you_name",
  "f_hobby_special",
];

// Engine ordering for the "── Other questions ──" group.
// Mirrors the natural arc of a getting-to-know-you conversation.
const _ENGINE_ORDER = [
  "identity", "place", "family", "work", "hobby", "travel", "food", "plans", "opinion", "study",
];

// On narrow viewports, only the first N "Other questions" rows are shown (after engine + file sort).
// Desktop shows the full filtered list. Aligns with mobile CSS breakpoint (~600px).
const _OTHER_QUESTIONS_MOBILE_MAX = 9;

function _isNarrowFrameDropdownViewport() {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(max-width: 600px)").matches;
}

// Starter-candidate filter: only partner ASK frames with no slots.
// Priority frames bypass this filter entirely (they are added unconditionally).
function _isStarterCandidate(f) {
  return f.speaker === "partner" &&
         f.move_type === "ASK" &&
         (f.slots || []).length === 0;
}

async function loadPackFramesIntoDropdown() {
  emitUITrace({ type: "UI_INFO", timestamp: new Date().toISOString(), payload: { message: "loadPackFramesIntoDropdown start" } });

  try {
    const packs = ["p1_frames.json", "p2_frames.json"];
    const byId = {};  // frame_id → item (p2 wins on duplicate)
    let fileOrder = 0;

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
          byId[fid] = {
            engine_id: eid,
            frame_id:  fid,
            speaker:   f.speaker  || "",
            move_type: f.move_type || "",
            slots:     Array.isArray(f.slots) ? f.slots : [],
            file_order: fileOrder++,
            label: (f.text_en || "").trim() || `${eid} :: ${fid}`,
          };
        }
      }
    }

    if (Object.keys(byId).length === 0) {
      emitUITrace({ type: "UI_ERROR", timestamp: new Date().toISOString(), payload: { message: "Pack frames loaded, but 0 usable (missing engine_id/frame_id?)" } });
      return;
    }

    const makeOpt = (it) => {
      const opt = document.createElement("option");
      opt.value = it.frame_id;
      opt.textContent = it.label;
      opt.dataset.engineId = it.engine_id;
      return opt;
    };

    frameSelect.innerHTML = "";

    // Priority group: the 3 visible starters + 1 under More, in declared order
    const priorityGroup = document.createElement("optgroup");
    priorityGroup.label = "── Start here ──";
    let firstPriorityId = null;
    for (const fid of _PRIORITY_FRAME_IDS) {
      const it = byId[fid];
      if (!it) continue;
      priorityGroup.appendChild(makeOpt(it));
      if (!firstPriorityId) firstPriorityId = fid;
    }
    if (priorityGroup.children.length > 0) frameSelect.appendChild(priorityGroup);

    // Other questions group: starter-candidate frames not already in priority group.
    // Sorted by conversation-arc engine order, then file order within each engine.
    const otherGroup = document.createElement("optgroup");
    otherGroup.label = "── Other questions ──";
    const prioritySet = new Set(_PRIORITY_FRAME_IDS);
    const others = Object.values(byId)
      .filter((it) => !prioritySet.has(it.frame_id) && _isStarterCandidate(it))
      .sort((a, b) => {
        const ea = _ENGINE_ORDER.indexOf(a.engine_id);
        const eb = _ENGINE_ORDER.indexOf(b.engine_id);
        const engDiff = (ea === -1 ? 99 : ea) - (eb === -1 ? 99 : eb);
        return engDiff !== 0 ? engDiff : a.file_order - b.file_order;
      });
    const narrow = _isNarrowFrameDropdownViewport();
    const othersShown = narrow ? others.slice(0, _OTHER_QUESTIONS_MOBILE_MAX) : others;
    for (const it of othersShown) otherGroup.appendChild(makeOpt(it));
    if (otherGroup.children.length > 0) frameSelect.appendChild(otherGroup);
    console.log(
      `[app] dropdown: ${priorityGroup.children.length} priority, ${othersShown.length} other questions` +
        (narrow && others.length > othersShown.length ? ` (mobile cap ${ _OTHER_QUESTIONS_MOBILE_MAX }, ${others.length} total filtered)` : ` (${others.length} filtered)`) +
        ` from ${Object.keys(byId).length} total frames`,
    );

    // Default to first priority frame
    frameSelect.value = firstPriorityId || Object.keys(byId)[0];
  } catch (e) {
    emitUITrace({
      type: "UI_ERROR",
      timestamp: new Date().toISOString(),
      payload: { message: "loadPackFramesIntoDropdown failed (kept fixtures)", error: String(e) }
    });
    console.error("[app] loadPackFramesIntoDropdown error:", e);
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

/** Resolve recovery_action from phrase metadata. All current phrases carry recovery_action in JSON (v1.2+). */
function getRecoveryAction(phrase) {
  if (phrase.recovery_action === "next_turn" || phrase.recovery_action === "slower" || phrase.recovery_action === "repeat")
    return phrase.recovery_action;
  if (phrase.recovery_action === "meaning")
    return "repeat";
  return "repeat";
}

function getRecoveryPanelOption() {
  const data = recoveryPhrasesRuntime || window._recoveryPhrases;
  const learner = learnerRecoveryPhrases(data);
  if (!data || learner.length === 0) return null;
  const repairCount = window._consecutiveNotUnderstood || 0;
  // Core-set phrases (always_surface) always first, ordered by routing group.
  const _groupOrder = { MICRO_REACTION: 0, HOLD: 1, REPEAT_CONTROL: 2, UNDERSTANDING: 3 };
  const core = learner
    .filter((p) => p.always_surface === true)
    .sort((a, b) => (_groupOrder[a.routing_group] ?? 9) - (_groupOrder[b.routing_group] ?? 9));
  const coreIds = new Set(core.map((p) => p.id));
  // EXIT group (好吧): surface only when TRIGGER_A or TRIGGER_B fires.
  // TRIGGER_A: repair_count >= 2 AND same repair type repeated (learner is stuck in a loop).
  // TRIGGER_B: repair_count >= 3 (persistence limit regardless of type).
  const lastRepairKind = window._lastRepairKind || null;
  const prevRepairKind = window._prevRepairKind || null;
  const TRIGGER_A = repairCount >= 2 && lastRepairKind !== null && lastRepairKind === prevRepairKind;
  const TRIGGER_B = repairCount >= 3;
  const exitEligible = TRIGGER_A || TRIGGER_B;
  const exit = exitEligible ? learner.filter((p) => p.routing_group === "EXIT") : [];
  // Panel shows only CORE_RECOVERY_SET + EXIT (好吧 when eligible) — no extra non-core lines.
  const pool = [...core, ...exit];
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
      meaning: p.text_en || p.meaning || "",
      recovery_action: getRecoveryAction(p),
      repair_kind: p.repair_kind || null,
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

  const header = document.createElement("div");
  header.className = "recovery-panel-label";
  header.textContent = "Need help?";
  targetContainer.appendChild(header);

  const scrollWrap = document.createElement("div");
  scrollWrap.className = "recovery-phrases-scroll";
  targetContainer.appendChild(scrollWrap);

  // Each phrase uses the same flat flex-wrap structure as discovery panels:
  // op-zh / op-py / op-en are direct card children so they wrap naturally on narrow screens.
  (opt.recoveryPhrases || []).forEach((phrase) => {
    const panel = document.createElement("div");
    panel.className = "option-panel recovery-card";
    panel.setAttribute("data-recovery", "true");
    panel.setAttribute("data-card-id", opt.card_id || "");
    panel.setAttribute("role", "button");
    panel.setAttribute("tabindex", "0");

    const zhSpan = document.createElement("span");
    zhSpan.className = "op-zh";
    zhSpan.textContent = phrase.hanzi || "";
    panel.appendChild(zhSpan);

    if (phrase.pinyin) {
      const pySpan = document.createElement("span");
      pySpan.className = "op-py";
      pySpan.textContent = phrase.pinyin;
      panel.appendChild(pySpan);
    }
    if (phrase.meaning) {
      const enSpan = document.createElement("span");
      enSpan.className = "op-en";
      enSpan.textContent = phrase.meaning;
      panel.appendChild(enSpan);
    }

    const speakBtn = document.createElement("button");
    speakBtn.type = "button";
    speakBtn.className = "op-icon-btn";
    speakBtn.setAttribute("title", "Speak this phrase");
    speakBtn.textContent = "\uD83D\uDD0A";
    speakBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      ttsSpeak({ text: phrase.hanzi || "", lang: "zh-CN" });
    });
    panel.appendChild(speakBtn);

    // Tap the card to use it (speaker click excluded)
    panel.addEventListener("click", async (ev) => {
      if (ev.target.closest(".op-icon-btn")) return;
      _tracker.recovery_uses++;
      _tracker._pendingRecovery = true;
      emitUITrace({ type: "OPTION_SELECTED", timestamp: new Date().toISOString(),
        payload: { frame_id: frameId, card_id: "recovery:" + (phrase.id || ""), kind: "RECOVERY" } });
      window._learnerObs.recovery_uses++;     // Phase L1 observation
      targetContainer.querySelectorAll(".option-panel").forEach((p) => p.classList.remove("selected"));
      panel.classList.add("selected");
      const userText = (phrase.hanzi || "").trim();
      addTranscriptEntry("user", userText, { text_en: phrase.meaning || "" });
      const action = getRecoveryAction(phrase);
      // Challenge Mode: track help usage; cascade to text reveal after 2 recovery clicks
      if (_challenge.active) {
        _challenge.recoveryCount++;
        _challenge.helpLevel = Math.max(_challenge.helpLevel, action === "slower" ? 2 : 1);
        if (_challenge.recoveryCount >= 2) _challengeRevealText();
      }
      // Use the most recently spoken partner text — in discovery mode this may be a persona stub answer
      // rather than _currentFrameText (which holds the pending queued question).
      const currentQuestion = (window._lastPartnerSpokenText || window._currentFrameText || "").trim();

      if (action === "next_turn") {
        renderTranscript();
        const _isExitRelease = phrase.repair_kind === "exit_release";
        if (_isExitRelease) window._consecutiveNotUnderstood = 0;
        const _transition = _isExitRelease ? null : getTopicChangeTransition(phrase.id);
        ttsSpeak({
          text: userText, lang: "zh-CN",
          onEvent: (e) => {
            if (!e?.payload?.completed) return;
            if (_transition) {
              addTranscriptEntry("partner", _transition.zh, { text_en: _transition.en });
              renderTranscript();
              ttsSpeak({
                text: _transition.zh, lang: "zh-CN",
                onEvent: (e2) => { if (e2?.payload?.completed) runTurn(true, { prefer_bridge: true }); },
              });
            } else if (_isExitRelease) {
              runTurn(true);
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
      addTranscriptEntry("partner", partnerLine, transcriptExtrasForRecoveryPartnerRepeat(action));
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

    scrollWrap.appendChild(panel);
  });
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
          const currentQuestion = (window._lastPartnerSpokenText || window._currentFrameText || "").trim();

          if (action === "next_turn") {
            renderTranscript();
            const _isExitRelease = phrase.repair_kind === "exit_release";
            if (_isExitRelease) window._consecutiveNotUnderstood = 0;
            const _transition = _isExitRelease ? null : getTopicChangeTransition(phrase.id);
            ttsSpeak({
              text: userText,
              lang: "zh-CN",
              onEvent: (e) => {
                if (!e?.payload?.completed) return;
                if (_transition) {
                  addTranscriptEntry("partner", _transition.zh, { text_en: _transition.en });
                  renderTranscript();
                  ttsSpeak({
                    text: _transition.zh,
                    lang: "zh-CN",
                    onEvent: (e2) => { if (e2?.payload?.completed) runTurn(true, { prefer_bridge: true }); },
                  });
                } else if (_isExitRelease) {
                  runTurn(true);
                } else {
                  runTurn(true, { prefer_bridge: true });
                }
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
          addTranscriptEntry("partner", partnerLine, transcriptExtrasForRecoveryPartnerRepeat(action));
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
        window._repairAttemptCount = 0;    // valid answer resets server-side repair escalation
        window._lastRepairKind = null; window._prevRepairKind = null;
        hideDiscoveryPanel();  // user answered partner's question — exit discovery mode
        window._pendingFrameText = null;
      }

      if (opt.kind === "RECOVERY") {
        const action = getRecoveryAction(opt);
        const currentQuestion = (window._lastPartnerSpokenText || window._currentFrameText || "").trim();

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
      _trackUserTextSignals(userText);
      _tracker.suggestion_clicks++;
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
  // Recovery panel lives here too — do not bail before it is appended.
  const hasRecoveryPanel = !!getRecoveryPanelOption();
  if (!answers.length && !hasRecoveryPanel) {
    container.style.display = "none";
    return;
  }

  // Recovery phrases: route to #challengeRecoveryZone in challenge mode so they remain visible
  // while sentenceOptionsContainer is hidden. Normal mode behaviour is unchanged.
  if (_challenge.active) {
    const zone = document.getElementById("challengeRecoveryZone");
    if (zone) { zone.innerHTML = ""; renderRecoveryPanelInto(zone, frameId); }
  } else {
    renderRecoveryPanelInto(container, frameId);
  }

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
      _tracker.suggestion_clicks++;
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
        let _soFired = false;
        ttsSpeak({
          text: hanziStr,
          lang: "zh-CN",
          onEvent: (e) => {
            if (!_soFired && e?.payload?.completed) {
              _soFired = true;
              runTurn(true, { last_turn_was_answer: true, submitted_text: hanziStr });
            }
          },
        });
      }
    });

    container.appendChild(panel);
  });

  // Keep the reverseActionsRow clear
  const reverseActionsRow = document.getElementById("reverseActionsRow");
  if (reverseActionsRow) reverseActionsRow.innerHTML = "";

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

/**
 * Direction / mirror / probe stubs are returned by /api/run_turn without going through
 * _runTurnInner — they must still populate #frameSentence and sentence hints.
 */
function applyPartnerStubToActiveSentence(stub, data, turnUid) {
  const t = (stub || "").trim();
  if (!t) return;
  const uid = turnUid || "partner_stub";
  setActivePartnerStatement(t, uid);
  window._sentenceHint = {
    pinyin: fillSentenceHintPinyin(t, data?.frame_pinyin),
    text_en: data?.frame_text_en != null ? String(data.frame_text_en).trim() : "",
  };
  _setFrameEnglish(window._sentenceHint.text_en);
  lastClickedWordId = null;
  window.lastClickedWordId = null;
  window._currentHintAffordance = { visible: true };
  window._currentTurnUid = uid;
  renderHintAffordance({ visible: true }, uid, "tap");
}

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
    applyPartnerStubToActiveSentence(stub, data, payload.turn_uid);
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
  window._learnerObs.mirror_uses++;             // Phase L1 observation
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
    applyPartnerStubToActiveSentence(stub, data, payload.turn_uid);
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
    applyPartnerStubToActiveSentence(stub, data, payload.turn_uid);
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
 * Render the learner memory object into the #rememberedFacts banner.
 * Pass an empty / null object to clear and hide the banner.
 * Called on page load, after each run_turn response, and after clearing memory.
 */
function _renderMemoryBanner(mem) {
  const el = document.getElementById("rememberedFacts");
  if (!el) return;
  const m = (mem && typeof mem === "object") ? mem : {};
  const LABELS = [
    ["learner_name", "Name"],
    ["hometown",     "From"],
    ["lives_in",     "Lives in"],
    ["job_or_study", "Job"],
    ["family",       "Family"],
    ["favourite_food","Fav food"],
  ];
  const parts = LABELS
    .map(([key, label]) => m[key] ? `${label}: ${m[key]}` : null)
    .filter(Boolean);
  if (parts.length > 0) {
    el.textContent = "Memory — " + parts.join(" · ");
    el.style.display = "";
  } else {
    el.textContent = "Memory — empty";
    el.style.display = "";
  }
}

/** Fetch current learner memory from the server and update the banner immediately. */
async function _refreshMemoryBanner() {
  try {
    const res = await fetch("/api/memory?learner_id=default_learner");
    if (res.ok) {
      const data = await res.json();
      _renderMemoryBanner(data.memory || {});
    }
  } catch (_) {}
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
  window._recoveryPromptsByFrame = {};
  window._consecutiveNotUnderstood = 0;
  window._lastRepairKind          = null;
  window._prevRepairKind          = null;
  window._currentEngineId        = "identity";
  // Phase 12C: session arc state
  window._loopCountInEngine      = 0;
  window._enginesVisited         = ["identity"];
  window._recentConfusionCount   = 0;
  // Phase 13B: seeded bridge queue reset on new session
  window._seededBridgeEngines    = [];
  window._mediumProbeFiredEngines = [];
  // Phase L1: reset learner observation counters on fresh session
  window._learnerObs = { turns_observed: 0, hint_clicks: 0, word_clicks: 0,
                         recovery_uses: 0, successful_answers: 0, asr_rejections: 0,
                         mirror_uses: 0, question_count: 0, extended_answer_count: 0,
                         recovery_resilience_count: 0 };
  window._pendingRepairPrompt     = false;
  window._lastRepairSubmittedText = "";

  // Clear the "Remembered:" facts banner
  _renderMemoryBanner({});

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

  // Reset session tracker — preserve mode based on current challenge state
  // (challenge button stays toggled; a fresh start begins a new tracked session in the same mode)
  _tracker.total_turns = 0;
  _tracker.recovery_uses = 0;
  _tracker.successful_recoveries = 0;
  _tracker.suggestion_clicks = 0;
  _tracker.card_opens = 0;
  _tracker.questions_asked = 0;
  _tracker.depth_responses = 0;
  _tracker.unmatched_responses = 0;
  _tracker.engines_used = new Set();
  _tracker._pendingRecovery = false;
  _tracker.mode = _challenge.active ? "challenge" : "normal";
}

/**
 * Run a turn: either "Run Turn" (frame from dropdown) or "Next" (selector-driven next frame).
 * @param {boolean} [isNext=false] When true, send next_question + conversation_state; server chooses frame.
 * @param {{ prefer_bridge?: boolean, force_bridge?: boolean, last_turn_was_answer?: boolean, learner_skip_confusion?: boolean }} [opts] When isNext: prefer_bridge tries bridge first; learner_skip_confusion clears bridge intent after "我不明白" advance.
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
  // Clear any lingering listening indicator now that the partner is about to respond.
  _setListenState("idle");
  // Challenge Mode: reset per-turn help state before rendering begins
  if (_challenge.active) _resetChallengeHelpState();
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
      seeded_bridge_engines: Array.isArray(window._seededBridgeEngines) ? window._seededBridgeEngines : [],
      recent_reactions: Array.isArray(window._recentReactions) ? window._recentReactions : [],
      medium_probe_fired_engines: Array.isArray(window._mediumProbeFiredEngines) ? window._mediumProbeFiredEngines : [],
      pending_listening_move: window._pendingListeningMove === true,
      listening_wait_turns: window._listeningWaitTurns || 0,
      last_interest_level: window._lastInterestLevel || "low",
      last_user_text: window._lastUserText || "",
      // Phase 12C: session arc state
      loop_count_in_current_engine: window._loopCountInEngine || 0,
      engines_visited: Array.isArray(window._enginesVisited) ? window._enginesVisited : ["identity"],
      recent_confusion_count: window._recentConfusionCount || 0,
      last_counter_reply: window._lastCounterReply || "",
      repair_attempt_count: window._repairAttemptCount || 0,
      // EFC: entity follow-up chain state — round-tripped so server can continue the chain
      efc_entity: window._efcEntity || null,
      efc_depth:  window._efcDepth  || 0,
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
    if (opts.learner_skip_confusion === true) conversation_state.learner_skip_confusion = true;
    if (opts.last_turn_was_answer === true) {
      conversation_state.last_turn_was_answer = true;
      // Send last_answer as long as it exists and has some content — even if frame_id is
      // null/empty (e.g. speech before first partner turn) so the server can detect
      // counter-questions via submitted_text.
      if (window._lastAnswer && (window._lastAnswer.submitted_text || window._lastAnswer.selected_option_hanzi)) {
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
  if (Array.isArray(data.seeded_bridge_engines)) window._seededBridgeEngines = data.seeded_bridge_engines;
  if (Array.isArray(data.recent_reactions)) window._recentReactions = data.recent_reactions;
  if (Array.isArray(data.medium_probe_fired_engines)) window._mediumProbeFiredEngines = data.medium_probe_fired_engines;
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

  // ── Session tracker hooks (observational only — do not gate any conversation logic on these) ──
  // Count user-submitted turns only (same gate as _exchangeCount).
  // "Next"-driven advances and bridge/probe auto-advances do not set last_turn_was_answer.
  if (opts?.last_turn_was_answer === true) {
    _tracker.total_turns++;
    window._learnerObs.successful_answers++;  // Phase L1 observation
  }
  window._learnerObs.turns_observed++;        // Phase L1: every server response = one observed turn
  // Track every engine ID returned by the server (includes recovery-driven advances).
  if (engineId) _tracker.engines_used.add(engineId.toLowerCase());
  // _pendingRecovery: check whether this turn was routed to a real frame.
  // Using data.frame_id (before the || selected fallback) as a conservative proxy for
  // "server returned a genuine continuation frame, not a stub or closing response".
  // TODO: data.frame_id is not a guaranteed accepted/routed signal — the server could
  //       return a frame_id for a closing or soft-fallback stub too. Revisit once a
  //       dedicated "turn_accepted" field is confirmed in /api/run_turn responses.
  if (_tracker._pendingRecovery) {
    if (data.frame_id) _tracker.successful_recoveries++;
    _tracker._pendingRecovery = false; // always clear regardless of outcome
  }
  // ── end session tracker hooks ──

  // Phase 9.1: update conversation state from response so Next has correct state
  window._currentEngineId = engineId;
  window._lastPartnerFrameId = frameId;
  // Post-closing-move flag: enables mirror fallback in showOptionsBtn when no normal options exist.
  // Set only when the server fires a soft-close reaction (e.g. "明白了"). Cleared on every other turn
  // so it cannot bleed into normal conversation turns.
  window._isPostClosingMove = (frameId === "closing_move" || data.closing_move === true);
  if (window._isPostClosingMove) {
    window._closingMoveEngine = engineId || window._currentEngineId;
    // Reflection is now shown in the scorecard panel only (via renderScorecard).
    // It is NOT rendered in the conversation window at closing_move.
  }
  // Merge state_update fields
  if (data.state_update && typeof data.state_update === "object") {
    if (data.state_update.last_counter_reply !== undefined)
      window._lastCounterReply = data.state_update.last_counter_reply;
    // EFC state: persist entity and depth so chain continues across turns
    if (data.state_update.efc_entity !== undefined)
      window._efcEntity = data.state_update.efc_entity;
    if (data.state_update.efc_depth !== undefined)
      window._efcDepth = data.state_update.efc_depth;
    if (data.state_update.repair_attempt_count !== undefined)
      window._repairAttemptCount = data.state_update.repair_attempt_count;
  }
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
  const fallbackText = _anchorVagueReferences(
    data.prompt_text || data.frame_text || "",
    window._lastMentionedPlace || ""
  );
  setUiMode("READ");
  window._currentFrameText = (fallbackText && fallbackText.trim()) ? fallbackText.trim() : "";
  window._lastAcceptedAsrKey = "";  // reset dedup so fresh answers on new questions are accepted
  // Counter-reply: persona's answer to a user counter-question (你呢？ 你是哪里人？ etc.)
  // Must appear in transcript BEFORE the next question and be spoken first.
  console.log("[DBG counter_reply]", { counter_reply: data.counter_reply, user_led: data.user_led, disc_q_count: (data.discovery_questions || []).length });
  const _counterReply = (data.counter_reply || "").trim();
  const _counterReplyEn = (data.counter_reply_en || "").trim();
  const _counterReplyPinyin = (data.counter_reply_pinyin || "").trim();
  if (_counterReply) {
    addTranscriptEntry("partner", _counterReply, {
      text_en: _counterReplyEn,
      pinyin: _counterReplyPinyin,
    });
    // Track for repeat/slower recovery so "慢一点" repeats the persona's reply, not the pending frame question.
    window._lastPartnerSpokenText = _counterReply;
    // Show counter_reply in the main interactive frame (Cluster 1 fix):
    // learner can now click characters in the persona's answer to explore words.
    // When in user-led mode the pending question is stored in _pendingFrameMeta and
    // shown after the learner taps "Continue →". So we skip renderFrameSentence here.
    setActivePartnerStatement(_counterReply, payload.turn_uid || "counter_reply");
    // Override _sentenceHint so the ? button shows the persona answer's EN, not the next question's EN.
    window._sentenceHint = { pinyin: fillSentenceHintPinyin(_counterReply, _counterReplyPinyin), text_en: _counterReplyEn };
    _setFrameEnglish(_counterReplyEn);
    window._lastPartnerTurnText = _counterReply;
  } else {
    // No counter_reply — render the app's next question into the main frame as normal.
    window._lastPartnerTurnText = fallbackText;
    renderFrameSentence({ id: frameId, text: fallbackText });
  }
  // Phase 8: append partner question to transcript — but only when NOT in discovery mode.
  // When user_led:true the frame question is held as a pending question; adding it now would
  // make it look like the app has already asked, giving the learner no chance to interview first.
  //
  // IMPORTANT: pause whenever the persona replied to the user's question (counter_reply set),
  // even if there are no discovery_questions (e.g. graceful deflections like "不太好说年龄！").
  // This prevents the conversation from abruptly jumping to the next topic.
  const _hasDiscovery = data.user_led && Array.isArray(data.discovery_questions) && data.discovery_questions.length > 0;
  const _isUserLed = !!_counterReply || _hasDiscovery;
  if (window._currentFrameText && !_isUserLed) {
    window._lastPartnerSpokenText = window._currentFrameText; // for repeat/slower recovery
    addTranscriptEntry("partner", window._currentFrameText, {
      text_en: data.frame_text_en || "",
      pinyin: data.frame_pinyin || "",
      frame_id: frameId,
      turn_uid: payload.turn_uid,
    });
  }
  // Always render — ensures counter_reply entry is visible even if _currentFrameText is absent
  renderTranscript();

  // Discovery mode: persona answered the user's question — show "Ask them more" cards.
  // Also store frame metadata so it can be added to the transcript when "Continue" fires.
  const _dq = data.discovery_questions || [];
  console.log(
    "[blue_panel_client]",
    "user_led=" + !!_isUserLed,
    "| discovery_questions=" + _dq.length,
    "| counter_reply=" + !!data.counter_reply,
    "| last_partner_frame_id=" + JSON.stringify(data.last_partner_frame_id ?? null),
    "| frame_id=" + JSON.stringify(frameId),
    "| blue_panel_shown=" + (_isUserLed && _dq.length > 0),
    _isUserLed && _dq.length === 0 ? "| note=user_led_but_no_cards" : "",
  );
  if (_isUserLed) {
    window._pendingFrameMeta = {
      text: fallbackText.trim(),
      text_en: data.frame_text_en || "",
      pinyin: fillSentenceHintPinyin(fallbackText.trim(), data.frame_pinyin || ""),
      frame_id: frameId,
    };
    renderDiscoveryPanel(_dq.slice(0, 2), fallbackText);
  } else {
    hideDiscoveryPanel();
    window._pendingFrameText = null;
    window._pendingFrameMeta = null;
  }
  // Auto-play: if a counter_reply exists, speak it first.
  // When user_led=true we PAUSE after the counter_reply so the learner can keep
  // interviewing the persona.  The frame question is queued in _pendingFrameText
  // and only spoken when they tap "Continue →" in the discovery panel.
  // IMPORTANT: use queue:true on the counter_reply TTS to avoid speechSynthesis.cancel()
  // triggering a spurious second onend on the previous utterance (Windows/Chrome bug).
  if (_counterReply) {
    // Always use queue:true for counter_reply — avoids speechSynthesis.cancel() triggering
    // a spurious second onend on the previous utterance (Windows/Chrome TTS bug).
    ttsSpeak({ text: _counterReply, lang: "zh-CN", queue: true });
    if (fallbackText && fallbackText.trim() && !_isUserLed) {
      // Non-user-led: queue the partner question immediately after the counter_reply.
      // Using queue:true on both avoids the fragile onEvent completion callback chain
      // that could silently drop the frame question on Windows.
      ttsSpeak({ text: fallbackText.trim(), lang: "zh-CN", queue: true });
    }
  } else if (fallbackText && fallbackText.trim()) {
    ttsSpeak({ text: fallbackText.trim(), lang: "zh-CN" });
  }
  // Phase 6 — options: prefer server-sent options when server chose the frame (next_question) so options always match the displayed question after bridge
  const _frameData     = window._frameOptionsRuntime?.frames?.[frameId] || {};
  const tapOptions     = (payload.next_question && Array.isArray(data.options) && data.options.length > 0)
    ? data.options
    : (_frameData.options || data.options || []);
  // Default to visible:true so the ? button always shows for frames not yet in the runtime JSON.
  const hintAffordance = _frameData.hint_affordance || { visible: true };
  const turnUid        = frameId;

  // Sentence-level hints (pinyin → English); used when no word is selected.
  // When counter_reply is active, the active sentence shows the persona's answer,
  // not the pending frame — so preserve the counter_reply hint set earlier.
  // Only overwrite with frame metadata when no counter_reply is displayed.
  if (!_counterReply) {
    window._sentenceHint = {
      pinyin: fillSentenceHintPinyin(fallbackText, data.frame_pinyin),
      text_en: data.frame_text_en ?? "",
    };
    _setFrameEnglish(window._sentenceHint.text_en);
  }
  lastClickedWordId = null;
  window.lastClickedWordId = null;

  window._tapOptions = tapOptions;
  window._currentHintAffordance = hintAffordance;
  window._currentTurnUid = turnUid;
  renderOptions(tapOptions, frameId);
  // Phase 10 Step 7: show remembered facts when server sends learner_memory (cross-session continuity)
  if (data.learner_memory && typeof data.learner_memory === "object") {
    _renderMemoryBanner(data.learner_memory);
  }

  // Sentence-level response options (answers + recovery row)
  // These replace the word-hint panels as the primary response UI when present.
  renderSentenceOptions(data.sentence_options || [], frameId);
  // Challenge Mode: re-hide response containers after render so "Suggested responses" is the only reveal path
  if (_challenge.active) {
    const _soc = document.getElementById("sentenceOptionsContainer");
    if (_soc) _soc.style.display = "none";
    const _optC = document.getElementById("optionsContainer");
    if (_optC) _optC.style.display = "none";
  }
  // Hide word-level options only when the sentence row actually rendered panels (answers / steer / recovery).
  // If the server sent sentence_options but nothing rendered (edge case), keep word cards visible.
  const hasSentenceOptions = (data.sentence_options || []).some(o => o.kind === "SENTENCE" || !o.kind);
  const soc = document.getElementById("sentenceOptionsContainer");
  const sentenceRowVisible =
    soc && soc.style.display !== "none" && soc.querySelector(".option-panel");
  if (hasSentenceOptions && sentenceRowVisible) {
    const optC = document.getElementById("optionsContainer");
    if (optC) optC.style.display = "none";
  }
  const optCAfter = document.getElementById("optionsContainer");
  emitUITrace({
    type: "TURN_RENDER",
    timestamp: new Date().toISOString(),
    payload: {
      frame_id: frameId,
      next_question: !!payload.next_question,
      sentence_row_visible: !!sentenceRowVisible,
      recovery_panel_present: !!(soc && soc.querySelector('[data-recovery="true"]')),
      word_options_visible: !!(optCAfter && optCAfter.style.display !== "none"),
      prefer_bridge: opts.prefer_bridge === true,
      force_bridge: opts.force_bridge === true,
      recent_confusion_count: window._recentConfusionCount || 0,
      arc_transition_reason: data.arc_state?.transition_reason ?? null,
      learner_state: _computeLearnerState(),   // Phase L1 observation — trace only
    },
  });
  // Legacy probe state: store for runProbeTurn compatibility but don't render separately
  if (data.probe_offer === true && Array.isArray(data.probe_options) && data.probe_options.length > 0) {
    window._lastProbeOptions = data.probe_options;
  }
  // Phase 11C: partner name + optional voice-line prefix + fact (EXTEND frames).
  // When counter_reply fills #frameSentence with the persona's full answer, never show a stale
  // partner_prefix / recovery line above it — that text belongs only in #frameSentence.
  {
    const _nameFromServer = (data.partner_name || "").trim();
    if (_nameFromServer) window._partnerDisplayName = _nameFromServer;
    const _pn = _nameFromServer || (window._partnerDisplayName || "").trim();
    if (_counterReply) {
      _updatePartnerHeader(_pn, "", "");
    } else {
      _updatePartnerHeader(_pn, data.partner_prefix || "", data.partner_fact || "");
    }
  }
  // Record which reveals have fired so the server gates correctly on the next turn
  if (data.partner_prefix && engineId && !_counterReply) window._revealedVoiceLines[engineId] = true;
  if (data.partner_fact  && engineId && !_counterReply) window._revealedPartnerFacts[engineId] = true;
  renderHintAffordance(hintAffordance, turnUid, "tap");
  
  // Wire hint button click: use current turn so recovery (and 你呢？) hint isn't reset to frame
  const _hintBtn = document.getElementById("hintBtn");
  if (_hintBtn) {
    const _newBtn = _hintBtn.cloneNode(true);
    _hintBtn.parentNode.replaceChild(_newBtn, _hintBtn);
    _newBtn.addEventListener("click", () => {
      window._learnerObs.hint_clicks++;       // Phase L1 observation
      // Challenge mode: first ? click reveals Chinese characters; subsequent clicks
      // cascade through pinyin → English as normal.
      if (_challenge.active && _challenge.helpLevel < 3) {
        _challengeRevealText();
        emitUITrace({ type: "HINT_ADVANCED", timestamp: new Date().toISOString(),
          payload: { frame_id: frameId, level: "challenge_reveal", turn_uid: hint_cascade_state.turn_uid || turnUid } });
        return;
      }
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

  // Mobile typing-mode re-focus: if the previous turn was submitted via the English
  // input field, keep keyboard open by re-focusing the field after the turn renders.
  // Conditions: mobile viewport + typing mode + no discovery panel open (discovery
  // panel has its own "Continue" tap flow; forcing keyboard there is disruptive).
  if (window._typingMode && window.innerWidth <= 600) {
    const _disc = document.getElementById("discoveryPanel");
    const _discVisible = _disc && _disc.style.display !== "none";
    if (!_discVisible) {
      const _engInputEl = document.getElementById("engInput");
      if (_engInputEl) {
        // Short delay: allow TTS to start and DOM to settle before pulling focus
        setTimeout(() => {
          _engInputEl.focus({ preventScroll: false });
        }, 450);
      }
    }
  }
  // Clear typing mode — next turn starts tap-neutral unless useBtn sets it again
  window._typingMode = false;
}


// allow clicking the card panel to close it
cardPanel.addEventListener("click", (e) => {
  if (e.target === cardPanel) dispatch({ type: "CARD_PANEL_CLOSED" });
});

// defaults
window.addEventListener("load", async () => {
  // Show current memory state immediately — before the user clicks Start,
  // so they can see if a previous session left data and clear it if needed.
  _refreshMemoryBanner();

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
    ttsUnlock();
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
    const { transcript, matchedOption, asr_confidence } = await listenForResponse(options, LISTEN_BEFORE_RECOVERY_MS);
    emitUITrace({
      type: "SPEECH_RESULT",
      timestamp: new Date().toISOString(),
      payload: {
        transcript: transcript || "",
        transcript_length: (transcript || "").length,
        matched: !!matchedOption,
        asr_confidence: asr_confidence != null ? asr_confidence : null,
      },
    });
    if (btn) {
      btn.textContent = "\uD83C\uDFA4";
      btn.title = "Speak your answer";
    }
    if (matchedOption) {
      if (frameId) {
        window._unmatchedByFrame[frameId] = 0;
        delete window._recoveryPromptsByFrame[frameId];
      }
      window._consecutiveNotUnderstood = 0;
      window._recentConfusionCount = 0;  // Phase 12C: real answer clears overload signal
      window._lastRepairKind = null; window._prevRepairKind = null;
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
      // When spoken transcript is longer than the partially-matched word option, use the full
      // transcript as the canonical answer. This prevents "羊肉不错" (spoken) from collapsing to
      // "不错" (the matched 2-char word tile) in both the transcript display and TTS playback.
      // The matched option is still used for word-card highlighting only.
      const _spokenRaw = (transcript || "").trim();
      const _matchedHanzi = (matchedOption.hanzi || "").trim();
      const saidText = (_spokenRaw.length > _matchedHanzi.length) ? _spokenRaw : _matchedHanzi;
      addTranscriptEntry("user", saidText, { text_en: matchedOption.meaning || "" });
      renderTranscript();
      _trackUserTextSignals(saidText);
      const _spokenHasTurnAround = _spokenRaw && (
        /^(那?你呢|你怎么想|为什么这么问|为什么这样问|换我问|那你|你来问)/.test(_spokenRaw)
        || _spokenRaw === "你呢"
        || /[，。！]?(那?你呢|你怎么想|为什么这么问)[？?]?$/.test(_spokenRaw)
        || /你(是哪里人|从哪里来|老家在哪|住(在哪|哪里|的地方)|做什么工作|的工作|是做什么|喜欢(什么|做什么)|有什么爱好|有家人|有没有家人)/.test(_spokenRaw)
      );
      // Add "？" for turn-around so the server detects the counter-question correctly.
      // For all other speech, send the transcript verbatim.
      const _spokenSubmitted = _spokenRaw
        ? (_spokenHasTurnAround && !(/[？?]$/.test(_spokenRaw)) ? _spokenRaw + "？" : _spokenRaw)
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

    // Same utterance repeated (ASR punctuation drift) — accept as answer, not partner "嗯？" recovery.
    const _normNow = normalizeForMatch(saidTrimmed);
    const _normPrev = normalizeForMatch(window._lastAcceptedFreeTranscript || "");
    if (
      _normNow && _normNow === _normPrev && frameId &&
      frameId === window._lastAcceptedFreeFrameId &&
      (_now - (window._lastAcceptedFreeTranscriptAt || 0)) < 15000
    ) {
      window._lastAcceptedAsrKey = _asrDedupKey;
      window._lastAcceptedAsrTime = _now;
      if (frameId) {
        window._unmatchedByFrame[frameId] = 0;
        delete window._recoveryPromptsByFrame[frameId];
      }
      window._consecutiveNotUnderstood = 0;
      window._recentConfusionCount = 0;
      window._lastRepairKind = null; window._prevRepairKind = null;
      emitUITrace({
        type: "SPEECH_REPEAT_ACCEPTED",
        timestamp: new Date().toISOString(),
        payload: { transcript: saidTrimmed, frame_id: frameId },
      });
      _trackUserTextSignals(saidTrimmed);
      addTranscriptEntry("user", saidTrimmed);
      renderTranscript();
      window._lastAnswer = { frame_id: frameId, submitted_text: saidTrimmed };
      let _turnFired2 = false;
      ttsSpeak({
        text: saidTrimmed,
        lang: "zh-CN",
        onEvent: (e) => {
          if (!_turnFired2 && e?.payload?.completed) {
            _turnFired2 = true;
            runTurn(true, { last_turn_was_answer: true });
          }
        },
      });
      lastClickedWordId = null;
      window.lastClickedWordId = null;
      setUiMode("READ");
      return;
    }

    const unmatchedCount = frameId ? (window._unmatchedByFrame?.[frameId] || 0) : 0;
    const unmatchedDecision = classifyUnmatchedFreeAnswerDecision(saidTrimmed, options, frameId, unmatchedCount);
    const substantialAnswer = unmatchedDecision.accept;
    if (substantialAnswer) {
      window._lastAcceptedAsrKey  = _asrDedupKey;
      window._lastAcceptedAsrTime = _now;
      if (frameId) {
        window._unmatchedByFrame[frameId] = 0;
        delete window._recoveryPromptsByFrame[frameId];
      }
      window._consecutiveNotUnderstood = 0;
      window._recentConfusionCount = 0;  // Phase 12C: real answer clears overload signal
      window._lastRepairKind = null; window._prevRepairKind = null;
      emitUITrace({
        type: "SPEECH_ACCEPTED_AS_ANSWER",
        timestamp: new Date().toISOString(),
        payload: { transcript: saidTrimmed, matched: false, unmatched_decision_reason: unmatchedDecision.reason, frame_id: frameId }
      });
      window._lastAcceptedFreeTranscript = saidTrimmed;
      window._lastAcceptedFreeTranscriptAt = Date.now();
      window._lastAcceptedFreeFrameId = frameId || "";
      // Learner skip signal ("我不懂"): advance without saving as scored answer
      if (unmatchedDecision.reason === "learner_skip_signal") {
        addTranscriptEntry("user", saidTrimmed);
        renderTranscript();
        lastClickedWordId = null;
        window.lastClickedWordId = null;
        setUiMode("READ");
        runTurn(true, { learner_skip_confusion: true });
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
      _trackUserTextSignals(saidTrimmed);
      // Track the most recently mentioned place for vague-reference anchoring in partner text.
      // e.g. "甘肃" → later frame "那儿生活" becomes "甘肃那边生活".
      const _PLACE_ANCHOR_LIST = ['甘肃', '中国', '美国', '英国', '法国', '日本', '韩国', '新西兰', '台湾', '香港', '澳大利亚', '北京', '上海', '广州', '成都', '欧洲', '泰国', '新加坡', '越南', '意大利', '西班牙', '德国', '加拿大'];
      const _newAnchorPlace = _PLACE_ANCHOR_LIST.find(p => saidTrimmed.includes(p));
      if (_newAnchorPlace) window._lastMentionedPlace = _newAnchorPlace;
      addTranscriptEntry("user", saidTrimmed);
      renderTranscript();
      window._lastAcceptedFreeTranscript = saidTrimmed;
      window._lastAcceptedFreeTranscriptAt = Date.now();
      window._lastAcceptedFreeFrameId = frameId || "";
      window._lastAnswer = { frame_id: frameId, submitted_text: submittedForServer };
      console.log("[DBG lastAnswer set]", JSON.stringify(window._lastAnswer));
      // One-shot guard: browser onend can fire twice (Windows/Chrome speechSynthesis bug).
      // Without this, a second call reaches runTurn after _runTurnInFlight is already false.
      let _turnFired = false;
      ttsSpeak({
        text: saidTrimmed,
        lang: "zh-CN",
        onEvent: (e) => {
          if (!_turnFired && e?.payload?.completed) {
            _turnFired = true;
            console.log("[DBG runTurn fire] lastAnswer=", JSON.stringify(window._lastAnswer));
            runTurn(true, { last_turn_was_answer: true });
          }
        },
      });
      lastClickedWordId = null;
      window.lastClickedWordId = null;
      setUiMode("READ");
      return;
    }
    // Not understood: update conversation with what we heard and partner's recovery (Phase 9: improve decision so reasonable answers aren't treated as not understood)
    _tracker.unmatched_responses++;             // unmatchedDecision.accept === false
    window._learnerObs.asr_rejections++;        // Phase L1 observation
    window._pendingRepairPrompt     = true;          // next user text = recovery attempt (recovery_resilience_count)
    window._lastRepairSubmittedText = saidTrimmed;   // store rejected text so identical retries don't count
    const _frameRecShown = frameId ? (window._recoveryPromptsByFrame?.[frameId] || 0) : 0;
    const recoveryCtx = computeRecoveryTriggerContext({
      transcript: saidTrimmed,
      options,
      asr_confidence,
      frame_id: frameId,
      repeat_repair_count: window._consecutiveNotUnderstood || 0,
      frame_recovery_shown: _frameRecShown,
      incomplete_utterance: isIncompleteLearnerUtterance(saidTrimmed),
    });
    const lastRecoveryId = window._lastRecoveryPhraseId || null;
    const phrase = getRecoveryPhraseForNotUnderstood(lastRecoveryId, recoveryCtx);

    // Semantic clarification override: if we can detect the learner's intent, use a
    // targeted question instead of generic repair (啊？). This applies from the very
    // first rejection — generic repair only fires when NO semantic signal is detectable.
    const _semCategory    = _detectSemanticCategory(saidTrimmed);
    // Context-anchored confusion recovery: if the learner echoes back our location probe
    // ("哪里什么") AND our immediately previous turn was itself a 哪里？ clarification,
    // rephrase with their previous answer as context so the intent is unambiguous.
    // e.g. "我是问：你说「这里羊肉牛肉都很好吃」，是在哪里？"
    const _prevWasWherePrompt = /哪里[?？]/.test(window._lastPartnerTurnText || "");
    const _isEchoConfusion    = /^(哪里|哪儿)/.test(saidTrimmed.trim()) && /什么|不懂|不明白/.test(saidTrimmed);
    const _semClarifyData = (_prevWasWherePrompt && _isEchoConfusion)
      ? _buildWhereRestatement(window._lastAcceptedFreeTranscript)
      : (_semCategory ? _getSemanticClarification(_semCategory) : null);
    const _displayPhrase  = _semClarifyData
      ? Object.assign({}, phrase, {
          hanzi:           _semClarifyData.hanzi,
          pinyin:          _semClarifyData.pinyin,
          text_en:         _semClarifyData.text_en,
          recovery_action: "soft",   // stay in RESPOND; do not auto-advance turn
          id:              "sem_clarify_" + _semCategory,
        })
      : phrase;

    emitUITrace({
      type: "SPEECH_NOT_UNDERSTOOD",
      timestamp: new Date().toISOString(),
      payload: {
        transcript,
        answer_rejected_reason: unmatchedDecision.reason,
        unmatched_decision_reason: unmatchedDecision.reason,
        frame_id: frameId,
        unmatched_count: unmatchedCount + 1,
        recovery_phrase_selected: _displayPhrase.hanzi || null,
        recovery_phrase_id: _displayPhrase.id || null,
        repair_phrase_source: "getRecoveryPhraseForNotUnderstood",
        recovery_trigger_reason: phrase.recovery_trace?.recovery_trigger_reason,
        repair_kind: phrase.recovery_trace?.repair_kind,
        asr_confidence_band: phrase.recovery_trace?.asr_confidence_band,
        repeat_repair_count: phrase.recovery_trace?.repeat_repair_count,
        frame_recovery_shown_before: _frameRecShown,
        explicit_recovery_phrase_id: phrase.recovery_trace?.explicit_recovery_phrase_id,
        asr_confidence: phrase.recovery_trace?.asr_confidence,
        semantic_category: _semCategory || null,
        semantic_clarify_used: !!_semClarifyData,
      },
    });
    if (frameId) window._unmatchedByFrame[frameId] = unmatchedCount + 1;
    if (frameId) {
      window._recoveryPromptsByFrame[frameId] = _frameRecShown + 1;
    }
    addTranscriptEntry("user", (transcript && transcript.trim()) ? transcript.trim() : "[couldn't understand]");
    window._lastRecoveryPhraseId = _displayPhrase.id;
    addTranscriptEntry("partner", _displayPhrase.hanzi, {
      text_en: _displayPhrase.text_en || "",
      pinyin: _displayPhrase.pinyin || "",
    });
    renderTranscript();
    const recoverySegments = (_displayPhrase.hanzi || "").split("").map((c) => ({ t: c }));
    setActivePartnerStatement(_displayPhrase.hanzi, "recovery", recoverySegments);
    window._sentenceHint = {
      pinyin: fillSentenceHintPinyin(_displayPhrase.hanzi, _displayPhrase.pinyin),
      text_en: _displayPhrase.text_en,
      etymology: _displayPhrase.etymology || "",
    };
    _setFrameEnglish(_displayPhrase.text_en);
    lastClickedWordId = null;
    window.lastClickedWordId = null;
    hint_cascade_state = { level: 0, turn_uid: "recovery" };
    renderHintAffordance({ visible: true }, "recovery", "tap");
    if (_displayPhrase.recovery_action === "next_turn") {
      window._consecutiveNotUnderstood = 0;
      if (frameId) delete window._recoveryPromptsByFrame[frameId];
      setUiMode("READ");
      ttsSpeak({
        text: _displayPhrase.hanzi,
        lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed) runTurn(true, { prefer_bridge: true });
        },
      });
    } else {
      ttsSpeak({ text: _displayPhrase.hanzi, lang: "zh-CN" });
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

runBtn.addEventListener("click", () => { ttsUnlock(); runTurn(false); });
if (nextBtn) nextBtn.addEventListener("click", () => { ttsUnlock(); runTurn(true); });
const changeTopicBtn = document.getElementById("changeTopicBtn");
if (changeTopicBtn) changeTopicBtn.addEventListener("click", () => { ttsUnlock(); runTurn(true, { prefer_bridge: true }); });
// ── Challenge Mode helpers ────────────────────────────────────────────────
function _resetChallengeHelpState() {
  _challenge.helpLevel = 0;
  _challenge.recoveryCount = 0;
  document.body.classList.remove("challenge-text-revealed");
  // Reset hint cascade so pinyin/English from the previous turn never carry over
  // into the new turn's hidden-text state.
  hint_cascade_state = { level: 0, turn_uid: null };
}

function _challengeRevealText() {
  if (_challenge.helpLevel >= 3) return;
  _challenge.helpLevel = 3;
  document.body.classList.add("challenge-text-revealed");
  // Text is now visible — let normal hint affordance render
  renderHintAffordance(window._currentHintAffordance || { visible: false }, window._currentTurnUid || null, "tap");
}

function toggleChallengeMode() {
  _challenge.active = !_challenge.active;
  _tracker.mode = _challenge.active ? "challenge" : "normal";
  document.body.classList.toggle("challenge-mode", _challenge.active);
  const btn = document.getElementById("challengeModeBtn");
  if (btn) {
    btn.textContent = _challenge.active ? "🔒 Challenge ON" : "Challenge Mode";
    btn.classList.toggle("challenge-active", _challenge.active);
  }
  if (!_challenge.active) {
    // Exiting: remove text-revealed class so state is clean on re-entry
    document.body.classList.remove("challenge-text-revealed");
    const zone = document.getElementById("challengeRecoveryZone");
    if (zone) zone.innerHTML = "";
  }
}

const challengeModeBtn = document.getElementById("challengeModeBtn");
if (challengeModeBtn) challengeModeBtn.addEventListener("click", toggleChallengeMode);

const showOptionsBtn = document.getElementById("showOptionsBtn");
if (showOptionsBtn) showOptionsBtn.addEventListener("click", () => {
  const sentenceContainer = document.getElementById("sentenceOptionsContainer");
  const legacyContainer = document.getElementById("optionsContainer");
  const hasSentence = !!(sentenceContainer && sentenceContainer.children.length > 0);
  const hasLegacy = !!(legacyContainer && legacyContainer.children.length > 0);

  if (hasSentence && sentenceContainer) {
    const isVisible = sentenceContainer.style.display !== "none";
    sentenceContainer.style.display = isVisible ? "none" : "flex";
    // Challenge Mode: record that suggested responses were revealed
    if (_challenge.active && !isVisible) _challenge.helpLevel = Math.max(_challenge.helpLevel, 4);
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
  // Additive post-closing-move fallback: show mirror/user-led questions after a terminal
  // acknowledgement (e.g. "明白了"). Only activates when both containers are already empty
  // AND the server signalled a closing move — never fires during normal active conversation.
  if (window._isPostClosingMove) {
    _showPostCloseMirrorOptions();
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
// ── Phase L1: Ability Dashboard ─────────────────────────────────────────────
/**
 * Build a session-level ability summary from accumulated observation counters.
 * Pure data — no DOM changes. Returns { capability_lines, progress_lines,
 * next_steps, internal_state }. Observation only; no effect on conversation.
 */
function _buildAbilitySummary() {
  const obs          = window._learnerObs || {};
  const successCount = obs.successful_answers      || 0;
  const hintCount    = obs.hint_clicks             || 0;
  const repairCount  = window._repairAttemptCount  || 0;
  // Combined question signal: typed/spoken questions + mirror-button clicks
  const questionCount = (obs.question_count || 0) + (obs.mirror_uses || 0);
  const extendedCount = obs.extended_answer_count   || 0;
  const resilCount    = obs.recovery_resilience_count || 0;
  const turns         = obs.turns_observed          || 0;

  // ── capability_lines ──────────────────────────────────────────────────────
  const capability_lines = [];
  if (successCount >= 3) capability_lines.push("Answer basic questions about yourself");
  if (successCount >= 5) capability_lines.push("Handle short conversations");
  if (questionCount >= 1) capability_lines.push("Ask simple follow-up questions");
  if (capability_lines.length === 0) capability_lines.push("Starting to respond to simple questions");

  // ── progress_lines ────────────────────────────────────────────────────────
  // Scope: capability + emotional reinforcement only.
  // Hint usage and participation counts belong to the scorecard.
  const progress_lines = [];
  if (successCount >= 3) progress_lines.push("You answered several questions");
  // Graded extended-answer lines
  if (extendedCount >= 2)      progress_lines.push("You gave more detailed answers");
  else if (extendedCount === 1) progress_lines.push("You started adding more detail");
  // Graded recovery-resilience lines
  if (resilCount >= 2)          progress_lines.push("You worked through misunderstandings");
  else if (resilCount === 1)    progress_lines.push("You kept going after a misunderstanding");
  // Generic repair line only when no specific resilience signal is present
  if (repairCount >= 3 && resilCount === 0)
    progress_lines.push("You worked through understanding — keep going");
  if (progress_lines.length === 0 && turns > 0)
    progress_lines.push("You showed up and tried — that's the start");

  // ── next_steps (max 2) ────────────────────────────────────────────────────
  const next_steps = [];
  // Never suggest asking questions if the learner already asked one
  if (questionCount === 0) next_steps.push("Try asking a question back");
  // Prefer connector-linking advice when learner already gives extended answers
  if (extendedCount >= 2) {
    next_steps.push("Try linking two ideas with 因为 / 但是 / 所以");
  } else if (successCount >= 3) {
    next_steps.push("Try a longer answer next time");
  }
  // Repair-heavy session: suggest simplification
  if (repairCount >= 3 && next_steps.length < 2)
    next_steps.push("Try saying the same idea in a shorter way first");
  // General advancement suggestion when slots remain
  if (successCount >= 5 && next_steps.length < 2)
    next_steps.push("Try talking about your work or daily life");
  if (next_steps.length === 0) next_steps.push("Try answering a question in Chinese");
  const capped_next = next_steps.slice(0, 2);

  // ── headline ──────────────────────────────────────────────────────────────
  let headline;
  if (questionCount >= 1 && (extendedCount >= 2 || resilCount >= 2))
    headline = "You're starting to handle more natural conversation flow.";
  else if (successCount >= 5 && questionCount >= 1)
    headline = "You're starting to handle real conversations.";
  else if (successCount >= 5)
    headline = "You're getting comfortable answering in Chinese.";
  else if (successCount >= 3)
    headline = "You're building confidence with simple conversations.";
  else
    headline = "You're starting to respond in Chinese.";

  const summary = {
    headline,
    capability_lines,
    progress_lines,
    next_steps: capped_next,
    internal_state: {
      success_count:    successCount,
      hint_count:       hintCount,
      repair_count:     repairCount,
      question_count:   questionCount,
      extended_count:   extendedCount,
      resil_count:      resilCount,
    },
  };
  console.log("[ability_summary]", summary);
  return summary;
}

/**
 * GUARD — Reflection must not render inside the conversation window.
 * All reflection content is now rendered by renderScorecard() in the scorecard panel.
 *
 * This function is kept as a named no-op so existing references do not throw.
 * Any call here is a bug: log a warning and block rendering.
 *
 * trace field: reflection_render_blocked_in_conversation = true
 */
function _renderAbilityDashboard() {
  console.warn(
    "[reflection_guard] _renderAbilityDashboard() called — blocked.",
    "Reflection must only render via renderScorecard() in the scorecard panel.",
    { reflection_render_blocked_in_conversation: true }
  );
  // Do NOT render anything in the conversation window.
}
// Expose for console inspection and external test scripts.
window._buildAbilitySummary  = _buildAbilitySummary;
window._renderAbilityDashboard = _renderAbilityDashboard;

// ── Phase L1: Learner state observation layer ────────────────────────────────
/**
 * Compute a lightweight observational learner state snapshot from accumulated
 * signal counters. Observation only — no behavior change anywhere in the app.
 *
 * Returns a plain object suitable for inclusion in emitUITrace payloads or
 * console inspection via window._computeLearnerState().
 *
 * Level thresholds are intentionally loose; they will be calibrated in Phase L2
 * once real session data is available.
 */
function _computeLearnerState() {
  const obs = window._learnerObs || {};
  const t   = Math.max(obs.turns_observed || 0, 1);  // avoid div/0

  const hint_rate     = (obs.hint_clicks      || 0) / t;
  const recovery_rate = (obs.recovery_uses    || 0) / t;
  const word_rate     = (obs.word_clicks      || 0) / t;
  const success_rate  = (obs.successful_answers || 0) / t;
  const asr_rate      = (obs.asr_rejections   || 0) / t;
  const repair_now    = window._repairAttemptCount        || 0;
  const confused_now  = window._consecutiveNotUnderstood  || 0;
  const turns         = obs.turns_observed || 0;

  const reasons = [];
  let level      = "unknown";
  let confidence = "low";

  if (turns < 3) {
    reasons.push("insufficient_data");
  } else if (hint_rate > 0.5 || recovery_rate > 0.35 || asr_rate > 0.4 || (confused_now >= 2 && turns < 8)) {
    level = "P1_fragile";
    if (hint_rate     > 0.5)                      reasons.push("high_hint_rate");
    if (recovery_rate > 0.35)                     reasons.push("high_recovery_rate");
    if (asr_rate      > 0.4)                      reasons.push("high_asr_rejection_rate");
    if (confused_now >= 2)                        reasons.push("consecutive_confusion");
  } else if (success_rate > 0.6 && hint_rate < 0.15 && recovery_rate < 0.15 && asr_rate < 0.15) {
    level = "P2_early";
    reasons.push("high_success_rate");
    if (word_rate  > 0.2) reasons.push("active_word_exploration");
    if (hint_rate  < 0.1) reasons.push("low_hint_dependency");
  } else {
    level = "P1_stable";
    if (success_rate  > 0.4)  reasons.push("moderate_success_rate");
    if (hint_rate     < 0.5)  reasons.push("manageable_hint_rate");
    if (word_rate     > 0.1)  reasons.push("some_word_exploration");
  }

  confidence = turns >= 10 ? "high" : turns >= 5 ? "medium" : "low";

  return {
    // Raw counters
    turns_observed:     turns,
    hint_clicks:        obs.hint_clicks       || 0,
    word_clicks:        obs.word_clicks       || 0,
    recovery_uses:      obs.recovery_uses     || 0,
    successful_answers: obs.successful_answers || 0,
    asr_rejections:     obs.asr_rejections    || 0,
    // Live window state (snapshot)
    current_repair_count:   repair_now,
    current_confused_count: confused_now,
    current_engine:         window._currentEngineId || "unknown",
    challenge_active:       !!(window._challenge?.active),
    // Provisional level estimate
    estimated_level_candidate: level,
    confidence,
    reasons,
  };
}
// Expose for browser console and external test scripts (ES module scope not on window by default).
window._computeLearnerState = _computeLearnerState;

// ── Post-close mirror fallback ───────────────────────────────────────────────
/**
 * Additive fallback only for the terminal-acknowledgement state (window._isPostClosingMove === true).
 * Fetches mirror/user-led questions from the server, or uses a hardcoded starter set if the fetch
 * fails. Renders via the SAME renderSentenceOptions path used during active conversation
 * (line 4586 pattern) so speaker, ?, and word-insight all work correctly.
 *
 * Do NOT call this during normal conversation turns — it is guarded by window._isPostClosingMove.
 */
async function _showPostCloseMirrorOptions() {
  const FALLBACK_MIRROR = [
    { zh: "你呢？",          py: "nǐ ne?",                  en: "How about you?",          topic: "general"  },
    { zh: "你叫什么名字？",  py: "nǐ jiào shénme míngzì?",  en: "What's your name?",       topic: "identity" },
    { zh: "你住在哪儿？",    py: "nǐ zhù zài nǎr?",         en: "Where do you live?",      topic: "place"    },
    { zh: "你做什么工作？",  py: "nǐ zuò shénme gōngzuò?",  en: "What kind of work do you do?", topic: "work" },
  ];

  let mirrorOpts = null;
  try {
    const engine = window._closingMoveEngine || window._currentEngineId || "identity";
    const res = await fetch("/api/run_turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        direction_intent: "mirror",
        conversation_state: {
          session_id: window._sessionId,
          current_engine: engine,
          last_partner_frame_id: window._lastPartnerFrameId ?? null,
          recent_frame_ids: Array.isArray(window._recentFrameIds) ? window._recentFrameIds : [],
        },
        persona_id: window._partnerId || window._personaId || null,
      }),
    });
    if (res.ok) {
      const d = await res.json();
      if (Array.isArray(d.mirror_options) && d.mirror_options.length > 0) {
        mirrorOpts = d.mirror_options;
      }
    }
  } catch (_) { /* fall through to hardcoded fallback */ }

  const opts = mirrorOpts || FALLBACK_MIRROR;

  // Render via the existing sentence-options path (same as mid-conversation mirror rendering).
  // opts with a `topic` field → runMirrorTurn click handler; no `topic` → submitted as answer.
  renderSentenceOptions(opts, null);

  const soc = document.getElementById("sentenceOptionsContainer");
  if (soc) {
    soc.style.display = "flex";
    setUiMode("RESPOND");
    soc.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}
// Expose on window so browser console validation and test scripts can call it directly.
// app.js is an ES module — module-scope functions are not automatically on window.
window._showPostCloseMirrorOptions = _showPostCloseMirrorOptions;

// ── Discovery panel: "You interview the persona" mode ───────────────────────
/**
 * Render clickable "Ask them:" cards so the learner can interview the persona
 * instead of being relentlessly asked questions themselves.
 * questions: array of { zh, py, en, topic }
 */
function renderDiscoveryPanel(questions, pendingFrameText) {
  // Store the queued frame question so "Continue" can speak it later.
  if (pendingFrameText) window._pendingFrameText = pendingFrameText.trim();

  let panel = document.getElementById("discoveryPanel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "discoveryPanel";
    // Insert after sentence options so blue mirror questions sit below suggested responses
    const anchor = document.getElementById("optionsContainerParent")
                || document.getElementById("sentenceOptionsContainer");
    if (anchor) {
      anchor.after(panel);
    } else {
      document.body.appendChild(panel);
    }
  }
  panel.style.display = "flex";
  const _hasCards = Array.isArray(questions) && questions.length > 0;

  // In deflect mode, pull acknowledgment phrases from the recovery vocabulary.
  const _recovData = window._recoveryPhrases || {};
  const _ackPhrases = (_recovData.phrases || []).filter(p => p.use === "deflection_ack");

  panel.innerHTML = _hasCards
    ? `<div class="discovery-header">你想了解什么？ <span class="discovery-sub">Tap to ask the persona:</span></div>`
    : `<div class="discovery-header discovery-header--deflect">怎么回应？ <span class="discovery-sub">Tap a phrase to acknowledge and continue:</span></div>`;

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

    card.addEventListener("click", () => { ttsUnlock(); submitDiscoveryQuestion(q); });
    card.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { ttsUnlock(); submitDiscoveryQuestion(q); } });
    panel.appendChild(card);
  });

  // Deflect mode: render acknowledgment phrases so the learner can respond gracefully
  // and continue rather than being left with only a "Continue" button.
  if (!_hasCards && _ackPhrases.length > 0) {
    _ackPhrases.forEach((p) => {
      const card = document.createElement("div");
      card.className = "option-panel discovery-ack";
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");

      const zhSpan = document.createElement("span");
      zhSpan.className = "op-zh";
      zhSpan.textContent = p.hanzi || "";
      card.appendChild(zhSpan);

      if (p.pinyin) {
        const pySpan = document.createElement("span");
        pySpan.className = "op-py";
        pySpan.textContent = p.pinyin;
        card.appendChild(pySpan);
      }
      if (p.text_en) {
        const enSpan = document.createElement("span");
        enSpan.className = "op-en";
        enSpan.textContent = p.text_en;
        card.appendChild(enSpan);
      }

      const _handleAck = () => {
        const hanzi = (p.hanzi || "").trim();
        if (!hanzi) return;
        hideDiscoveryPanel();
        addTranscriptEntry("user", hanzi, { text_en: p.text_en || "", pinyin: p.pinyin || "" });
        renderTranscript();
        // Speak the ack phrase, then continue with the pending frame question
        const pending = window._pendingFrameText;
        const meta    = window._pendingFrameMeta || {};
        window._pendingFrameText = null;
        window._pendingFrameMeta = null;
        ttsSpeak({
          text: hanzi, lang: "zh-CN",
          onEvent: (e) => {
            if (!e?.payload?.completed) return;
            if (pending) {
              window._lastPartnerSpokenText = pending;
              addTranscriptEntry("partner", pending, {
                text_en:  meta.text_en  || "",
                pinyin:   meta.pinyin   || "",
                frame_id: meta.frame_id || "",
              });
              renderTranscript();
              window._sentenceHint = { pinyin: fillSentenceHintPinyin(pending, meta.pinyin || ""), text_en: meta.text_en || "" };
              _setFrameEnglish(meta.text_en || "");
              syncPartnerHeaderWhenFrameSentenceIsPrimary();
              renderFrameSentence({ id: meta.frame_id || "", text: pending });
              ttsSpeak({ text: pending, lang: "zh-CN" });
            }
          },
        });
      };
      card.addEventListener("click", _handleAck);
      card.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") _handleAck(); });
      panel.appendChild(card);
    });
  }

  // "Continue →" footer: dismisses discovery mode and speaks the pending frame question.
  const footer = document.createElement("div");
  footer.className = "discovery-footer";
  const continueBtn = document.createElement("button");
  continueBtn.className = "discovery-continue-btn";
  continueBtn.textContent = "继续聊  Continue →";
  continueBtn.addEventListener("click", () => {
    hideDiscoveryPanel();
    const pending = window._pendingFrameText;
    const meta    = window._pendingFrameMeta || {};
    window._pendingFrameText = null;
    window._pendingFrameMeta = null;
    if (pending) {
      // Now the question is actually being asked — add it to the transcript
      window._lastPartnerSpokenText = pending; // for repeat/slower recovery
      addTranscriptEntry("partner", pending, {
        text_en:  meta.text_en  || "",
        pinyin:   meta.pinyin   || "",
        frame_id: meta.frame_id || "",
      });
      renderTranscript();
      window._sentenceHint = { pinyin: fillSentenceHintPinyin(pending, meta.pinyin || ""), text_en: meta.text_en || "" };
      _setFrameEnglish(meta.text_en || "");
      syncPartnerHeaderWhenFrameSentenceIsPrimary();
      renderFrameSentence({ id: meta.frame_id || "", text: pending });
      ttsSpeak({ text: pending, lang: "zh-CN" });
    }
  });
  footer.appendChild(continueBtn);
  panel.appendChild(footer);
}

function hideDiscoveryPanel() {
  const panel = document.getElementById("discoveryPanel");
  if (panel) panel.style.display = "none";
}

async function submitDiscoveryQuestion(q) {
  const zh = (q.zh || "").trim();
  if (!zh) return;
  hideDiscoveryPanel();
  // NOTE: do NOT clear _pendingFrameText/_pendingFrameMeta here.
  // The queued frame question stays until the learner taps "Continue →".

  addTranscriptEntry("user", zh, { text_en: q.en || "", pinyin: q.py || "" });
  renderTranscript();
  // queue:true avoids speechSynthesis.cancel() spurious double-onend on Windows
  ttsSpeak({ text: zh, lang: "zh-CN", queue: true });

  const currentEngine = window._currentEngineId ?? "identity";
  const payload = {
    env: "dev",
    turn_uid: "ui_disc_" + Date.now(),
    direction_intent: "mirror",
    direction_question_zh: zh,
    direction_question_topic: q.topic || "",
    conversation_state: {
      session_id: window._sessionId,
      current_engine: currentEngine,
      last_partner_frame_id: window._lastPartnerFrameId ?? null,
      recent_frame_ids: Array.isArray(window._recentFrameIds) ? window._recentFrameIds : [],
    },
  };
  const _pid = window._partnerId || window._personaId;
  if (_pid) payload.persona_id = _pid;

  let data = {};
  try {
    const res = await fetch("/api/run_turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) data = await res.json();
  } catch (e) {
    console.warn("[app] submitDiscoveryQuestion fetch failed", e);
  }

  const stub = (data.frame_text || "").trim();
  if (stub) {
    window._lastPartnerSpokenText = stub; // for repeat/slower recovery
    addTranscriptEntry("partner", stub);
    renderTranscript();
    applyPartnerStubToActiveSentence(stub, data, payload.turn_uid);
    ttsSpeak({ text: stub, lang: "zh-CN", queue: true });
  }

  // Re-render discovery panel with remaining questions (server already excluded the asked one).
  // Pass null so _pendingFrameText is preserved (Continue button still works).
  const remaining = (data.mirror_options || []).filter(m => (m.zh || "") !== zh);
  renderDiscoveryPanel(remaining, null);
}

// ── MandarinOS-style ZH naturalizer ─────────────────────────────────────────
// Shared post-processor applied to every EN→ZH translation output.
// Converts formal/written vocabulary to spoken/learner-friendly equivalents
// and fixes structural patterns that are misleading in context.
//
// Add new entries to _ZH_VOCAB_PAIRS as they are discovered.
// Longer / more-specific patterns MUST appear before shorter ones.
const _ZH_VOCAB_PAIRS = [
  // Multi-character formal → spoken (order matters: longer first)
  ["父母亲",   "爸爸妈妈"],
  ["父母",     "爸爸妈妈"],
  ["祖父母",   "爷爷奶奶"],
  ["丈夫",     "老公"],
  ["妻子",     "老婆"],
  ["父亲",     "爸爸"],
  ["母亲",     "妈妈"],
  ["祖父",     "爷爷"],
  ["祖母",     "奶奶"],
  ["兄弟姐妹", "兄弟姐妹"],   // already fine, keep for completeness
  ["家庭成员", "家人"],
  ["配偶",     "老公/老婆"],
];

/**
 * Returns true when the English source text implies emotional / relational
 * closeness rather than physical distance, so we can safely rewrite
 * "离 X 最近" → "跟 X 最亲近".
 */
function _isEmotionalClosenessContext(sourceEn) {
  const s = (sourceEn || "").toLowerCase();
  if (!/(closest to|close to|close with|emotionally close)/.test(s)) return false;
  // Physical-distance cues rule it out
  if (/(live near|walk|drive|travel|km|mile|store|shop|school|office|distance|building|block)/.test(s)) return false;
  return true;
}

/**
 * Normalize a machine-translated ZH string to MandarinOS learner-natural style.
 *
 * @param {string} zh        Raw ZH from translation API.
 * @param {string} sourceEn  Original English input (used for context detection).
 * @returns {string}         Naturalized ZH.
 */
function naturalizeZhTranslation(zh, sourceEn) {
  if (!zh) return zh;
  let s = zh;

  // 1. Vocabulary substitution (formal/written → spoken/natural)
  for (const [formal, spoken] of _ZH_VOCAB_PAIRS) {
    s = s.split(formal).join(spoken);
  }

  // 2. Structural fix: "离 X 最近" → "跟 X 最亲近" in relational context only
  if (_isEmotionalClosenessContext(sourceEn)) {
    s = s.replace(/离(.{1,6}?)最近/g, "跟$1最亲近");
    // Also catch "和 X 最近" (less common but possible)
    s = s.replace(/和(.{1,6}?)最近([，。！？]|$)/g, "和$1最亲近$2");
  }

  return s;
}

// ── MandarinOS translation override map ──────────────────────────────────────
// High-confidence EN→ZH overrides for frequent conversational phrases.
// These are checked BEFORE calling any external translation API, guaranteeing
// learner-natural output for the most important expressions.
//
// Rules:
//  • Keys are lowercase, no leading/trailing whitespace.
//  • Punctuation is stripped during lookup (see _lookupTranslationOverride).
//  • Keep this map SMALL — only add phrases where the API consistently fails
//    or where exact natural Chinese is business-critical.
//  • Values are already naturalized; naturalizeZhTranslation is NOT re-applied.
//
// Sections: family closeness · family members · work / retirement · daily life
const TRANSLATION_OVERRIDES = {
  // ── Emotional closeness ────────────────────────────────────────────────────
  "i am closest to my wife":           "我跟我老婆最亲近",
  "i'm closest to my wife":            "我跟我老婆最亲近",
  "i am closest to my husband":        "我跟我老公最亲近",
  "i'm closest to my husband":         "我跟我老公最亲近",
  "i am closest to my mother":         "我跟我妈妈最亲近",
  "i'm closest to my mother":          "我跟我妈妈最亲近",
  "i am closest to my mom":            "我跟我妈妈最亲近",
  "i'm closest to my mom":             "我跟我妈妈最亲近",
  "i am closest to my father":         "我跟我爸爸最亲近",
  "i'm closest to my father":          "我跟我爸爸最亲近",
  "i am closest to my dad":            "我跟我爸爸最亲近",
  "i'm closest to my dad":             "我跟我爸爸最亲近",
  "i am closest to my parents":        "我跟爸爸妈妈最亲近",
  "i'm closest to my parents":         "我跟爸爸妈妈最亲近",
  "i am closest to my children":       "我跟我孩子们最亲近",
  "i am closest to my son":            "我跟我儿子最亲近",
  "i am closest to my daughter":       "我跟我女儿最亲近",
  // ── Who I live with ───────────────────────────────────────────────────────
  "i live with my wife":               "我跟我老婆一起住",
  "i live with my husband":            "我跟我老公一起住",
  "i live with my parents":            "我跟爸爸妈妈一起住",
  "i live with my parents and wife":   "我跟爸爸妈妈和老婆一起住",
  "i live alone":                      "我一个人住",
  "i live by myself":                  "我一个人住",
  // ── Family members ────────────────────────────────────────────────────────
  "my wife":                           "我老婆",
  "my husband":                        "我老公",
  "my mother":                         "我妈妈",
  "my mom":                            "我妈妈",
  "my father":                         "我爸爸",
  "my dad":                            "我爸爸",
  "my parents":                        "我爸爸妈妈",
  "my children":                       "我的孩子们",
  "my son":                            "我儿子",
  "my daughter":                       "我女儿",
  "my family":                         "我家人",
  // ── Work & retirement ─────────────────────────────────────────────────────
  "i am retired":                      "我退休了",
  "i'm retired":                       "我退休了",
  "i retired":                         "我退休了",
  "i have retired":                    "我退休了",
  "i don't work":                      "我不工作",
  "i don't work anymore":              "我不工作了",
  "i no longer work":                  "我不工作了",
  "i used to be a teacher":            "我以前是老师",
  "i used to work as a teacher":       "我以前是老师",
  "i used to be a doctor":             "我以前是医生",
  "i used to be an engineer":          "我以前是工程师",
  "i work as a teacher":               "我是老师",
  "i am a teacher":                    "我是老师",
  "i am a doctor":                     "我是医生",
  "i am an engineer":                  "我是工程师",
  "i am a student":                    "我是学生",
  "i am studying":                     "我在读书",
  // ── Identity / origin ─────────────────────────────────────────────────────
  "i am from guangzhou":               "我是广州人",
  "i am from guangdong":               "我是广东人",
  "i am from beijing":                 "我是北京人",
  "i am from shanghai":                "我是上海人",
  "i am from china":                   "我是中国人",
  "i am originally from guangzhou":    "我老家在广州",
  "my hometown is guangzhou":          "我老家在广州",
  // ── Daily life / food ─────────────────────────────────────────────────────
  "i like lamb":                       "我喜欢羊肉",
  "lamb is delicious":                 "羊肉很好吃",
  "lamb is good":                      "羊肉不错",
  "the food here is good":             "这里的东西很好吃",
  "the food here is delicious":        "这里的东西很好吃",
  "i like to eat together with family":"我喜欢跟家人一起吃饭",
  "i enjoy eating with my family":     "我喜欢跟家人一起吃饭",
  "my mother is not well":             "我妈妈身体不太好",
  "my mom is not well":                "我妈妈身体不太好",
  "my mother is sick":                 "我妈妈身体不好",
};

/**
 * Normalise an English string for override lookup:
 * lowercase, trim, collapse whitespace, strip trailing punctuation.
 */
function _normalizeEnForOverride(s) {
  return (s || "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ")
    .replace(/[.!?,;:]+$/, "")
    .trim();
}

/**
 * Return a MandarinOS-curated Chinese translation if the input matches a
 * known high-quality override, otherwise return null.
 *
 * @param {string} englishInput  Raw English text from the user.
 * @returns {string|null}        Override ZH string, or null if no match.
 */
function _lookupTranslationOverride(englishInput) {
  const key = _normalizeEnForOverride(englishInput);
  return TRANSLATION_OVERRIDES[key] ?? null;
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

  const engTranslatedPy = document.getElementById("engTranslatedPy");

  function _setTranslationPinyin(zh) {
    if (!engTranslatedPy) return;
    const py = (typeof buildSentencePinyinFromLexicon === "function")
      ? buildSentencePinyinFromLexicon(zh)
      : "";
    engTranslatedPy.textContent = py;
    engTranslatedPy.style.display = py ? "block" : "none";
  }

  /** Render zh as clickable explore-word tokens inside #engTranslatedZh. */
  function _renderTranslationTokens(zh) {
    while (engTranslated.firstChild) engTranslated.removeChild(engTranslated.firstChild);
    const segs = (typeof tokenizeHanziForOption === "function")
      ? tokenizeHanziForOption(zh, {})
      : [{ t: zh, word_id: null }];
    for (const seg of segs) {
      const span = document.createElement("span");
      span.textContent = seg.t || "";
      const isCjk = /[\u4e00-\u9fff\u3400-\u4dbf]/.test(seg.t || "");
      if (isCjk) {
        span.className = seg.word_id
          ? "tok tok-word word-insight-token"
          : "tok tok-word tok-word-unknown word-insight-token";
        span.dataset.insightSource = "translate_result";
        if (seg.word_id) span.dataset.wordId = seg.word_id;
        span.addEventListener("click", async (e) => {
          e.stopPropagation();
          lastClickedWordId = seg.word_id || null;
          window.lastClickedWordId = lastClickedWordId;
          _openWordInsightPopover(span, seg.word_id || null, seg.t || "", "translate_result");
          if (seg.word_id && _shouldAlsoOpenCardPanel()) await _openCardForWordId(seg.word_id);
        });
      }
      engTranslated.appendChild(span);
    }
  }

  async function doTranslate() {
    const text = engInput.value.trim();
    if (!text) return;
    translateBtn.disabled = true;
    translateBtn.textContent = "…";
    engResult.style.display = "none";
    if (engTranslatedPy) { engTranslatedPy.textContent = ""; engTranslatedPy.style.display = "none"; }

    // ── Priority 1: curated override map (instant, no API call) ──────────────
    const override = _lookupTranslationOverride(text);
    if (override) {
      _renderTranslationTokens(override);
      _setTranslationPinyin(override);
      engResult.style.display = "flex";
      ttsSpeak({ text: override, lang: "zh-CN" });
      translateBtn.disabled = false;
      translateBtn.textContent = "Translate";
      return;
    }

    // ── Priority 2: external API + naturalizer post-processing ───────────────
    try {
      const url = "https://api.mymemory.translated.net/get?q=" +
                  encodeURIComponent(text) + "&langpair=en%7Czh";
      const res = await fetch(url);
      const data = await res.json();
      const rawZh = (data?.responseData?.translatedText || "").trim();
      const zh = naturalizeZhTranslation(rawZh, text);
      if (zh && zh !== text) {
        _renderTranslationTokens(zh);
        _setTranslationPinyin(zh);
        engResult.style.display = "flex";
        // Auto-play so the user hears pronunciation immediately
        ttsSpeak({ text: zh, lang: "zh-CN" });
      } else {
        engTranslated.textContent = "（翻译失败，请再试）";
        if (engTranslatedPy) { engTranslatedPy.textContent = ""; engTranslatedPy.style.display = "none"; }
        engResult.style.display = "flex";
      }
    } catch (_) {
      engTranslated.textContent = "（无法连接翻译服务）";
      if (engTranslatedPy) { engTranslatedPy.textContent = ""; engTranslatedPy.style.display = "none"; }
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

  // On mobile, the virtual keyboard can push the input out of view.
  // Scroll it into view after a short delay so the keyboard has time to open.
  engInput.addEventListener("focus", () => {
    setTimeout(() => engInput.scrollIntoView({ behavior: "smooth", block: "nearest" }), 320);
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
    ttsUnlock();
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
    // Mark typing mode so the next turn re-focuses the input on mobile
    window._typingMode = true;
    // Advance the conversation as if the user gave a free-text spoken answer
    runTurn(true, { last_turn_was_answer: true });
  });
})();

// ── Phase 6 — expose to window for console access + external callers ────────
window.SystemFaultLog          = SystemFaultLog;
window.buildDiagnosticCompleted = buildDiagnosticCompleted;
window.hint_cascade_state   = hint_cascade_state;
window.renderHintAffordance = renderHintAffordance;

// ── Session scorecard ─────────────────────────────────────────────────────────

/**
 * Render the six scorecard metrics as a modal overlay.
 * Accepts the full /api/end_session response object.
 * Removed on close; re-entrant (removes any previous overlay first).
 */
function renderScorecard(response) {
  if (!response || !response.metrics) return;
  const m    = response.metrics;
  const mode = (response.mode || "normal");

  // Remove any leftover overlay from an older session (defensive)
  const prev = document.getElementById("scorecardOverlay");
  if (prev) prev.remove();

  const content = document.getElementById("scorecardContent");
  if (!content) {
    console.warn("[renderScorecard] #scorecardContent not found");
    return;
  }

  content.innerHTML = "";
  content.classList.remove("scorecard-placeholder");

  // ── Reflection section (top of scorecard) ──────────────────────────────
  // Render headline + capability / progress / next-step lines above metrics.
  // Data comes from _buildAbilitySummary() — the same source previously used
  // by _renderAbilityDashboard(). Only the render location has changed.
  const summary = _buildAbilitySummary();
  const reflDiv = document.createElement("div");
  reflDiv.className = "sc-reflection";

  const headlineEl = document.createElement("div");
  headlineEl.className = "sc-reflection-headline";
  headlineEl.textContent = summary.headline;
  reflDiv.appendChild(headlineEl);

  const reflSections = [
    { title: "What you can do now", lines: summary.capability_lines },
    { title: "Recent progress",     lines: summary.progress_lines   },
    { title: "Next step",           lines: summary.next_steps       },
  ];
  reflSections.forEach(({ title, lines }) => {
    if (!lines || lines.length === 0) return;
    const sec = document.createElement("div");
    sec.className = "ab-section";

    const titleEl = document.createElement("div");
    titleEl.className = "ab-section-title";
    titleEl.textContent = title;
    sec.appendChild(titleEl);

    const ul = document.createElement("ul");
    ul.className = "ab-list";
    lines.forEach((line) => {
      const li = document.createElement("li");
      li.textContent = line;
      ul.appendChild(li);
    });
    sec.appendChild(ul);
    reflDiv.appendChild(sec);
  });
  content.appendChild(reflDiv);

  // Visual divider between reflection and performance metrics
  const divider = document.createElement("hr");
  divider.className = "sc-divider";
  content.appendChild(divider);

  // Mode badge
  const modeBadge = document.createElement("div");
  modeBadge.className = "sc-mode-badge";
  modeBadge.textContent = mode === "challenge" ? "Challenge Mode" : "Normal Mode";
  content.appendChild(modeBadge);

  // Metric rows: [ rawText, label, meaning ]
  const rows = [
    [
      `${m.flow.raw} turns`,
      m.flow.label,
      "How long you kept the conversation going",
    ],
    [
      `${m.recovery.raw_uses} recoveries (${m.recovery.raw_successes} successful)`,
      m.recovery.label,
      "How well you got unstuck",
    ],
    [
      `${m.support.raw_uses} support uses`,
      m.support.label,
      "How much help you used",
    ],
    [
      `${m.participation.raw} questions`,
      m.participation.label,
      "Whether you only answered or also drove the conversation",
    ],
    [
      `${m.depth.raw} extended answers`,
      m.depth.label,
      "Whether you went beyond short answers",
    ],
    [
      `${m.stability.raw_unmatched} unmatched responses`,
      m.stability.label,
      "How often the system could not understand or route your response",
    ],
  ];

  rows.forEach(([rawText, label, meaning]) => {
    const row = document.createElement("div");
    row.className = "sc-row";

    const top = document.createElement("div");
    top.className = "sc-row-top";

    const rawEl = document.createElement("span");
    rawEl.className = "sc-raw";
    rawEl.textContent = rawText;

    const sep = document.createElement("span");
    sep.className = "sc-sep";
    sep.textContent = "→";

    const labelEl = document.createElement("span");
    labelEl.className = "sc-label";
    labelEl.textContent = label;

    top.appendChild(rawEl);
    top.appendChild(sep);
    top.appendChild(labelEl);

    const meaningEl = document.createElement("div");
    meaningEl.className = "sc-meaning";
    meaningEl.textContent = meaning;

    row.appendChild(top);
    row.appendChild(meaningEl);
    content.appendChild(row);
  });
}

/**
 * Collect the current session tracker, POST it to /api/end_session,
 * log the response to console, and render the scorecard overlay.
 * Intentionally read-only with respect to conversation state.
 */
async function endSession() {
  const t = _tracker;
  const payload = {
    session_id:            window._sessionId || "",
    mode:                  t.mode,
    total_turns:           t.total_turns,
    recovery_uses:         t.recovery_uses,
    successful_recoveries: t.successful_recoveries,
    suggestion_clicks:     t.suggestion_clicks,
    card_opens:            t.card_opens,
    questions_asked:       t.questions_asked,
    depth_responses:       t.depth_responses,
    unmatched_responses:   t.unmatched_responses,
    engines_used:          Array.from(t.engines_used),
  };

  let result = null;
  try {
    const res = await fetch("/api/end_session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    result = await res.json();
  } catch (err) {
    console.error("[endSession] request failed:", err);
    return null;
  }

  console.log("[endSession] scorecard result:", result);
  // renderScorecard now includes the ability reflection section at the top.
  // _renderAbilityDashboard() is intentionally NOT called here.
  if (result?.ok) renderScorecard(result);
  return result;
}

window.endSession    = endSession;
window.renderScorecard = renderScorecard;


















