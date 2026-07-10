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

// ── ASR diagnostic tracing (branch: diagnostics/asr-trace) ────────────────────
// Additive, behaviour-free instrumentation used to trace the spoken-vs-typed
// pipeline divergence. It MUST NOT change ASR selection, submitted text,
// transcript display, normalization, intent routing, or response behaviour.
//
// It is fully OFF unless a diag token is present (via ?diag=TOKEN once, then
// remembered in localStorage). When off, every method is a no-op and no network
// call is made. Events are buffered in memory during recognition and only
// flushed asynchronously (keepalive fetch) after the turn resolves, so no
// synchronous network logging happens inside ASR event handlers.
const AsrDiag = (() => {
  const pending = {};   // trace_id -> record awaiting server response / flush
  let active = null;    // record for the in-progress listen cycle

  function _token() {
    try {
      const q = new URLSearchParams(location.search).get("diag");
      if (q) { try { localStorage.setItem("mandarinos_diag_token", q); } catch (_) {} return q; }
      return localStorage.getItem("mandarinos_diag_token") || "";
    } catch (_) { return ""; }
  }
  function enabled() { return !!_token(); }
  function _clock() {
    return (window.performance && performance.now) ? Math.round(performance.now()) : Date.now();
  }
  function _mkId(prefix) {
    return prefix + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  }
  function begin(meta) {
    if (!enabled()) { active = null; return null; }
    active = { trace_id: _mkId("asr-"), started_at: new Date().toISOString(), device: meta || {}, events: [] };
    return active.trace_id;
  }
  function beginSynthetic(meta) {
    // For the typed/translated path: no ASR cycle, but we still want the server
    // side of the trace (raw input, routing, intent, response) for comparison.
    if (!enabled()) { active = null; return null; }
    active = { trace_id: _mkId("typ-"), started_at: new Date().toISOString(), device: meta || {}, events: [], synthetic: true };
    return active.trace_id;
  }
  function id() { return active ? active.trace_id : null; }
  function ev(type, data) {
    if (!active) return;
    const e = { t: _clock(), type };
    if (data) Object.assign(e, data);
    active.events.push(e);
  }
  function set(k, v) { if (active) active[k] = v; }
  function submit(extra) {
    // Detach the active record so a later async server response can complete it
    // without being clobbered by the next listen cycle.
    if (!active) return null;
    if (extra) Object.assign(active, extra);
    const tid = active.trace_id;
    pending[tid] = active;
    active = null;
    return tid;
  }
  function complete(traceId, serverDiag, extra) {
    const rec = pending[traceId];
    if (!rec) return;
    if (serverDiag) rec.server = serverDiag;
    if (extra) Object.assign(rec, extra);
    delete pending[traceId];
    _flush(rec);
  }
  function _flush(rec) {
    const tok = _token();
    let body;
    try { body = JSON.stringify(rec); } catch (_) { return; }
    try {
      fetch("/api/diag/asr-trace", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Diag-Token": tok },
        body,
        keepalive: true,
      }).catch(() => {});
    } catch (_) {}
  }
  return { enabled, begin, beginSynthetic, id, ev, set, submit, complete };
})();

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
  conversational_recoveries: 0,  // learner self-repair attempts after confusion/repair prompt
  successful_conversational_recoveries: 0,  // self-repair accepted (conversation continued)
  suggestion_clicks: 0,          // times user selected a suggested response option
  card_opens: 0,                 // user-initiated card-panel opens (not re-renders)
  display_en_clicks: 0,          // transcript EN reveals (hidden → shown only)
  display_py_clicks: 0,          // transcript PY reveals (hidden → shown only)
  translation_help_uses: 0,      // EN→ZH translation panel uses (Translate / Use)
  questions_asked: 0,            // user turns containing a question marker (吗/什么/怎么/为什么)
  depth_responses: 0,            // user turns containing a depth/extension marker
  unmatched_responses: 0,        // hard-fail turns (no Chinese signal / nonsense) — used in scorecard stability
  soft_unmatched_responses: 0,   // soft-fail turns (partial meaning, not routable) — weighted at 0.5 in scorecard
  turbulence_events: 0,          // informational turbulence count: ASR rejects + confusion signals + repair loops + challenge reveals
  engines_used: new Set(),       // engine IDs seen in responses this session
  _pendingRecovery: false,       // transient: true if last user action was a recovery tap (cleared on next turn)
  _pendingNaturalRecovery: false, // transient: true if natural re-attempt after rejection (cleared on next turn)
};
window._sessionTracker = _tracker;

// ── Session Intelligence — lightweight UX event log (Phase 0 Slice 1) ─────
// Accumulates UX events during the session for capture in the session_record.
// Entries: { t_offset_ms, type, frame_id?, kind?, engine? }
// Populated by _siLogEvent(); cleared in _resetCurrentSessionState().
window._siEventLog = [];
window._siSessionStart = Date.now();

/**
 * Append a UX event to the session intelligence event log.
 * No-op outside a conversation (guard: total_turns === 0 and no event yet).
 * Called from existing event handlers — never changes UI or tracker behaviour.
 */
function _siLogEvent(type, extras) {
  try {
    const entry = Object.assign(
      { t_offset_ms: Date.now() - (window._siSessionStart || Date.now()), type: type },
      extras || {}
    );
    window._siEventLog.push(entry);
  } catch (_) {}
}
window._siLogEvent = _siLogEvent;

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
  // A turn counts as a question when any of these hold:
  //   1. Contains 吗 (yes/no particle)
  //   2. Ends with ? or ？
  //   3. Ends with sentence-final 啊/呢 (spoken ASR: "你是哪里人啊")
  //   4. Contains 你呢 (reciprocal "and you?") anywhere
  //   5. Common embedded question patterns anywhere in the utterance
  //      (covers multi-clause inputs like "我喜欢出中国你去过哪里")
  //   6. QWord (什么/哪里/谁/…) + at least one structural marker
  //
  // Declarative clauses like "我不知道怎么说" or "我想去哪里都可以"
  // do not trigger (no particle, no embedded pattern, no 吗, no ？).
  const QUESTION_WORDS  = ["什么", "哪里", "哪儿", "哪个", "谁", "为什么", "怎么", "几", "多少", "多久"];
  const textTrimmed     = text.trim();
  const hasMa           = text.includes("吗");
  const hasYouNe        = text.includes("你呢");
  const endsWithQmark   = /[?？]$/.test(textTrimmed);
  // Sentence-final 啊/呢 as structural marker for spoken questions (e.g. "你是哪里人啊")
  const endsWithParticle = /[啊呢][？?]?$/.test(textTrimmed);
  const hasQWord        = QUESTION_WORDS.some(m => text.includes(m));
  // Short interrogative: ≤10 chars AND subject-initial (你/他/她/这/那)
  const shortIntPattern = textTrimmed.length <= 10 && /^[你他她这那]/.test(textTrimmed);
  // Embedded question patterns — detected anywhere in the utterance so multi-clause
  // inputs like "我现在在等你你是哪里人啊" are counted even without standalone structure.
  const hasEmbeddedQ    = /你(是哪里人|从哪里来|老家在哪|做什么工作|去过哪里|喜欢[^，。！?？]{0,6}吗|家里有几|有没有家人)/.test(text);
  const isStructuralQ   = hasMa || endsWithQmark || endsWithParticle || shortIntPattern;
  const isQuestion      = hasYouNe || hasMa || endsWithQmark || hasEmbeddedQ
                       || (hasQWord && isStructuralQ);

  if (isQuestion) {
    _tracker.questions_asked++;
    window._learnerObs.question_count++;
  }

  // ── Extended answer detection (unified for scorecard + ability summary) ────
  // "Extended" = learner elaborated beyond a bare noun/verb phrase. Detected when:
  //   a) ≥ 8 Chinese characters (multi-clause, noun expansion, correction patterns)
  //   b) Causal/concessive/temporal marker (因为, 所以, 以前, 但是, …)
  //   c) Repetition-based correction ("苏州我工作在苏州", "老师大学的老师")
  //   d) Duration or comparison pattern
  //
  // Both _tracker.depth_responses (scorecard) and _learnerObs.extended_answer_count
  // (ability summary) now use this single unified check.
  const DEPTH_AND_EXTEND_MARKERS = [
    "因为", "所以", "觉得", "但是", "其实", "对我来说", "最喜欢", "想", "希望",
    "以前", "现在", "已经", "还", "和", "跟", "一起",
  ];
  const COMPARISON_PAT   = /好多了|好很多|好一点|更好|比以前|进步|改善/;
  // Repetition: same 2-char Chinese span appears at least twice ("苏州…苏州", "老师…老师")
  const REPETITION_PAT   = /(\S{2})\S*\1/;
  const zhCharCount      = (text.match(/[\u4e00-\u9fff]/g) || []).length;
  const isExtended = zhCharCount >= 8
                  || DEPTH_AND_EXTEND_MARKERS.some(m => text.includes(m))
                  || _DURATION_ANSWER_PAT.test(text)
                  || COMPARISON_PAT.test(text)
                  || REPETITION_PAT.test(text);
  if (isExtended) {
    _tracker.depth_responses++;
    window._learnerObs.extended_answer_count++;
  }

  // ── Natural recovery tracking ──────────────────────────────────────────────
  // Count only when:
  //   (a) the previous turn ended with a repair prompt (rejection), AND
  //   (b) this submission differs from the rejected text (not an identical retry).
  // Also set _pendingNaturalRecovery so the server-response handler can credit a
  // successful_conversational_recoveries increment when the re-attempt routes correctly.
  if (window._pendingRepairPrompt) {
    if (text !== (window._lastRepairSubmittedText || "")) {
      window._learnerObs.recovery_resilience_count++;
      if (_isConversationalRecoveryAttempt(text)) {
        _tracker.conversational_recoveries++;
        _tracker._pendingNaturalRecovery = true; // cleared in _runTurnInner on next response
      }
    }
    window._pendingRepairPrompt      = false;
    window._lastRepairSubmittedText  = "";
  }
}

/** True when learner text after a repair/confusion prompt looks like self-repair, not noise. */
function _isConversationalRecoveryAttempt(text) {
  const t = (text || "").trim();
  if (!t) return false;
  const frameId = window._currentFrameId || document.getElementById("frameSelect")?.value || "";
  if (_detectSemanticCategory(t, window._currentEngineId || "")) return true;
  if (isLikelyUnderstandableFreeAnswer(t, frameId)) return true;
  const zhCount = (t.match(/[\u4e00-\u9fff]/g) || []).length;
  if (zhCount >= 3) return true;
  if (zhCount >= 2 && /(\S{2})\S*\1/.test(t)) return true; // repeat/clarify pattern
  return false;
}

function addTranscriptEntry(role, textZh, extras = {}) {
  const _zh = textZh || "";
  const _isPartner = role === "partner";
  // Diagnostics: capture the transcript actually shown to the learner for the
  // active mic cycle (behaviour-free; only records when diag is enabled).
  try {
    if (!_isPartner && AsrDiag.id()) AsrDiag.set("displayed_transcript", _zh);
  } catch (_) {}
  const entry = {
    id: "line_" + Date.now() + "_" + Math.floor(Math.random() * 10000),
    role: _isPartner ? "partner" : "user",
    text_zh: _zh,
    text_en: extras.text_en || "",
    // Partner turns: always derive pinyin from lexicon when the server didn't supply it.
    // fillSentenceHintPinyin returns the server value when non-empty, otherwise builds
    // from the character lexicon — so curated frame pinyin is never overwritten.
    // User turns: no pinyin is stored (not needed for capture).
    pinyin: _isPartner ? fillSentenceHintPinyin(_zh, extras.pinyin || "") : (extras.pinyin || ""),
    frame_id: extras.frame_id || "",
    turn_uid: extras.turn_uid || "",
    replayable: true,
    created_at: new Date().toISOString(),
    _glossPending: false,
  };
  conversationTranscript.push(entry);
  _initTranscriptLineUiState(entry);
  maybeRequestGlossForEntry(entry);
}

function _initTranscriptLineUiState(entry) {
  if (!entry || !entry.id) return;
  transcriptLineUiState[entry.id] = _defaultTranscriptLineUiState(entry.role);
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
    if (entry.role === "partner") _syncActiveEnglishFromGloss(entry, entry.text_en);
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
        _syncActiveEnglishFromGloss(entry, en);
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

/** Map run_turn / stub response fields onto partner transcript extras (no new server fields). */
function partnerTranscriptExtrasFromData(data, zh) {
  if (!data) return {};
  const z = (zh || "").trim();
  const counter = (data.counter_reply || "").trim();
  let text_en = "";
  let pinyin = "";
  if (z && counter && z === counter) {
    text_en = (data.counter_reply_en || "").trim();
    pinyin = (data.counter_reply_pinyin || "").trim();
  } else {
    text_en = data.frame_text_en != null ? String(data.frame_text_en).trim() : "";
    pinyin = (data.frame_pinyin || "").trim();
  }
  const out = {};
  if (text_en) out.text_en = text_en;
  if (pinyin || z) out.pinyin = fillSentenceHintPinyin(z, pinyin);
  return out;
}

/** When async gloss completes, keep active #frameEnglish in sync if this is still the spoken partner line. */
function _initActiveTurnRecord(zh, en, pinyin, turnUid) {
  const z = (zh || "").trim();
  window._activeTurnRecord = {
    zh: z,
    en: (en || "").trim(),
    pinyin: fillSentenceHintPinyin(z, pinyin || ""),
    turnUid: turnUid || "",
  };
  window._sentenceHint = {
    pinyin: window._activeTurnRecord.pinyin,
    text_en: window._activeTurnRecord.en,
  };
  if (z) window._lastPartnerSpokenText = z;
  _refreshActiveDisplayFromTurnRecord();
}

function _updateActiveTurnRecordEn(en) {
  const rec = window._activeTurnRecord;
  if (!rec) return;
  const val = (en || "").trim();
  if (!val) return;
  rec.en = val;
  window._sentenceHint = { ...(window._sentenceHint || {}), text_en: val };
  _refreshActiveDisplayFromTurnRecord();
}

/** Re-render EN/PY hint surfaces from the single active turn record (prevents cross-turn desync). */
function _refreshActiveDisplayFromTurnRecord() {
  const rec = window._activeTurnRecord;
  if (!rec || !rec.zh) return;
  const recordKey = _normalizeTranscriptText(rec.zh);
  const activeKey = _normalizeTranscriptText(window._lastPartnerSpokenText || "");
  if (activeKey && recordKey && activeKey !== recordKey) return;
  _setFrameEnglish(rec.en || "");
}

function _syncActiveEnglishFromGloss(entry, en) {
  if (!entry || entry.role !== "partner" || !(en || "").trim()) return;
  const entryKey = _normalizeTranscriptText(entry.text_zh || entry.text || "");
  const rec = window._activeTurnRecord;
  const recordKey = rec ? _normalizeTranscriptText(rec.zh || "") : "";
  const activeKey = _normalizeTranscriptText(window._lastPartnerSpokenText || "");
  if (!entryKey || (recordKey && entryKey !== recordKey && entryKey !== activeKey)) return;
  _updateActiveTurnRecordEn(en);
}

/** Refresh active English from current sentence hint (e.g. after recovery repeat). */
function _refreshActiveEnglishFromSentenceHint() {
  if (window._activeTurnRecord && window._activeTurnRecord.zh) {
    _refreshActiveDisplayFromTurnRecord();
    return;
  }
  const en = ((window._sentenceHint || {}).text_en || "").trim();
  if (en) _setFrameEnglish(en);
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
if (typeof window._sessionStartedAt === "undefined") window._sessionStartedAt = Date.now();
if (typeof window._recentFrameIds === "undefined") window._recentFrameIds = [];
// Phase 10: learner_id for memory persistence; last_answer (frame_id + selected_option_hanzi/submitted_text) sent with next_question when last_turn_was_answer
const _LEARNER_ID_STORAGE_KEY = "manos_learner_id";

function _normalizeBetaLearnerId(code) {
  const c = String(code || "").trim().replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 48);
  if (!c) return null;
  return c.startsWith("beta_") ? c : `beta_${c}`;
}

function setLearnerId(id) {
  const lid = String(id || "").trim();
  if (!lid || !/^[a-zA-Z0-9_-]{1,64}$/.test(lid)) return false;
  window._learnerId = lid;
  try {
    localStorage.setItem(_LEARNER_ID_STORAGE_KEY, lid);
  } catch (_) {}
  return true;
}

function initLearnerId() {
  try {
    const params = new URLSearchParams(window.location.search);
    const beta = params.get("beta");
    if (beta) {
      const normalized = _normalizeBetaLearnerId(beta);
      if (normalized && setLearnerId(normalized)) return;
    }
    const stored = localStorage.getItem(_LEARNER_ID_STORAGE_KEY);
    if (stored && /^[a-zA-Z0-9_-]{1,64}$/.test(stored.trim())) {
      window._learnerId = stored.trim();
      return;
    }
  } catch (_) {}
  if (typeof window._learnerId === "undefined") window._learnerId = "default_learner";
}

if (typeof window._learnerId === "undefined") window._learnerId = "default_learner";
initLearnerId();
window.setLearnerId = setLearnerId;

// Beta learner profile — practice comfort level (L1/L2)
const _VALID_LEARNER_LEVELS = new Set(["beginner", "lower_intermediate", "intermediate"]);
const _LEVEL_LABELS = {
  beginner: "Just getting started",
  lower_intermediate: "Studied some Mandarin",
  intermediate: "Can hold a basic conversation",
};

if (typeof window._learnerLevel === "undefined") window._learnerLevel = null;
if (typeof window._comfortMode === "undefined") window._comfortMode = false;
if (typeof window._isFirstTimeBetaUser === "undefined") window._isFirstTimeBetaUser = false;
if (typeof window._onboardingGuideDismissed === "undefined") window._onboardingGuideDismissed = false;

const _FIRST_TIME_ONBOARDING_TEXT =
  "Choose persona and conversation frame, then try to have a conversation.";

function _defaultTranscriptLineUiState(role) {
  const showPy = !!(window._comfortMode && role === "partner");
  return { showEn: false, showPy };
}

function _applyBetaProfileDefaults(profile) {
  const level = profile && profile.learner_level;
  window._learnerLevel = _VALID_LEARNER_LEVELS.has(level) ? level : null;
  window._comfortMode = !!(profile && profile.comfort_mode);
  document.body.classList.toggle("comfort-mode", window._comfortMode);
  document.body.classList.toggle("learner-beginner", window._learnerLevel === "beginner");
  if (window._comfortMode) {
    transcriptDisplayMode = "zh_en";
    const displayModeEl = document.getElementById("transcriptDisplayMode");
    if (displayModeEl) displayModeEl.value = "zh_en";
  }
  _updateChallengeModeVisibility();
  renderTranscript();
}

async function saveBetaProfile(level, levelSource) {
  const lid = window._learnerId || "default_learner";
  try {
    const res = await fetch("/api/beta_profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        learner_id: lid,
        learner_level: level,
        level_source: levelSource || "self_selected",
      }),
    });
    const data = await res.json();
    if (data.ok && data.profile) {
      _applyBetaProfileDefaults(data.profile);
      return data.profile;
    }
  } catch (_) {}
  return null;
}

function _showLevelGateOverlay(force) {
  const overlay = document.getElementById("levelGateOverlay");
  if (!overlay) return;
  overlay.classList.remove("hidden");
  overlay.querySelectorAll(".level-gate-option").forEach((btn) => {
    btn.onclick = async () => {
      const level = btn.getAttribute("data-level");
      if (!_VALID_LEARNER_LEVELS.has(level)) return;
      overlay.classList.add("hidden");
      await saveBetaProfile(level, "self_selected");
      _updatePracticeLevelBtnLabel();
    };
  });
  if (force) overlay.setAttribute("data-force", "1");
  else overlay.removeAttribute("data-force");
}

function _hideLevelGateOverlay() {
  const overlay = document.getElementById("levelGateOverlay");
  if (overlay) overlay.classList.add("hidden");
}

function _updatePracticeLevelBtnLabel() {
  const btn = document.getElementById("practiceLevelBtn");
  if (!btn) return;
  const level = window._learnerLevel;
  const hasLevel = level && _LEVEL_LABELS[level];
  const label = hasLevel ? _LEVEL_LABELS[level] : "Select…";
  btn.textContent = label;
  btn.dataset.set = hasLevel ? "1" : "0";
  btn.title = hasLevel
    ? `Choose starting point: ${label} — click to change`
    : "Choose your practice comfort level";
}

function _dismissOnboardingGuideIfActive() {
  if (!window._isFirstTimeBetaUser || window._onboardingGuideDismissed) return;
  window._onboardingGuideDismissed = true;
  renderSessionObjective();
}

/** Clear browser carryover so a server-verified first-time beta user starts clean. */
function _applyFirstTimeBetaHygiene() {
  try {
    localStorage.removeItem("manos_last_session");
    localStorage.removeItem("manos_progress_history");
  } catch (_) {}
  window._lastMentionedPlace = null;
  window._lastAcceptedFreeTranscript = "";
  window._lastAcceptedFreeFrameId = "";
  window._lastAcceptedAsrKey = "";
  window._lastAcceptedAsrTime = 0;
  window._learnerWorkContext = null;
  _resetCurrentSessionState();
  _renderMemoryBanner({});
  window._isFirstTimeBetaUser = true;
  window._onboardingGuideDismissed = false;
}

function _updateChallengeModeVisibility() {
  const btn = document.getElementById("challengeModeBtn");
  if (!btn) return;
  const hide = window._learnerLevel === "beginner";
  btn.style.display = hide ? "none" : "";
  if (hide && _challenge.active) {
    _challenge.active = false;
    _tracker.mode = "normal";
    document.body.classList.remove("challenge-mode", "challenge-text-revealed");
    btn.textContent = "Challenge Mode";
    btn.classList.remove("challenge-active");
    const zone = document.getElementById("challengeRecoveryZone");
    if (zone) zone.innerHTML = "";
  }
}

async function initBetaProfile() {
  const lid = window._learnerId || "default_learner";
  let isFirstTime = false;
  try {
    const res = await fetch(`/api/beta_profile?learner_id=${encodeURIComponent(lid)}`);
    const data = await res.json();
    if (data.ok) {
      if (typeof data.is_first_time_beta_user === "boolean") {
        isFirstTime = data.is_first_time_beta_user;
      }
      window._isFirstTimeBetaUser = isFirstTime;
      if (data.profile && data.profile.learner_level) {
        _applyBetaProfileDefaults(data.profile);
        _updatePracticeLevelBtnLabel();
        return data.profile;
      }
    }
  } catch (_) {}

  window._isFirstTimeBetaUser = isFirstTime;

  if (lid === "default_learner") {
    await saveBetaProfile("lower_intermediate", "operator_set");
    _updatePracticeLevelBtnLabel();
    return null;
  }

  _showLevelGateOverlay(false);
  _updatePracticeLevelBtnLabel();
  return null;
}

window.initBetaProfile = initBetaProfile;
window.saveBetaProfile = saveBetaProfile;
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
// Discovery/blue-panel state — round-tripped from server state_update so proactive
// triggers accumulate correctly across turns.
if (typeof window._discoveryShownLastTurn    === "undefined") window._discoveryShownLastTurn    = false;
if (typeof window._consecutiveAppQuestions   === "undefined") window._consecutiveAppQuestions   = 0;
if (typeof window._lastPersonaReveal         === "undefined") window._lastPersonaReveal         = false;
if (typeof window._recentlySeenDiscTopics    === "undefined") window._recentlySeenDiscTopics    = [];
if (typeof window._lastPartnerFrameText      === "undefined") window._lastPartnerFrameText      = "";
if (typeof window._lastSemanticClarifyText   === "undefined") window._lastSemanticClarifyText   = "";
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
  extended_answer_count:    0,   // answers with length or connector/repetition markers
  recovery_resilience_count: 0,  // times user answered again after a repair prompt
  soft_unmatched_count:     0,   // partial-meaning rejections (partial Chinese, not routable)
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

/** Mobile: Explore Word is bottom-sheet — only open via explicit "Explore word" tap. */
function _closeExploreWordPanelIfMobile() {
  if (!_isMobileLayout()) return;
  if (state?.isOpen) dispatch({ type: "CARD_PANEL_CLOSED" });
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
  _siLogEvent("card_open", { frame_id: frameId, engine: engineId });
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
    _syncActiveEnglishDisplay();
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
    _syncActiveEnglishDisplay();
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
    _syncActiveEnglishDisplay();
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
    const uiState = transcriptLineUiState[lineId] || _defaultTranscriptLineUiState(role);

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
      pyBtn.addEventListener("click", () => toggleLinePinyin(lineId));
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
  const st = transcriptLineUiState[lineId] || _defaultTranscriptLineUiState(entry?.role);
  if (!entry) return;
  if (entry.role === "user" && !(entry.text_en || "").trim()) {
    const resolved = resolveUserLineTranslation(entry);
    if (resolved) {
      entry.text_en = resolved;
    } else if (!st.showEn) {
      maybeRequestGlossForEntry(entry);
    }
  }
  if (!st.showEn) { _tracker.display_en_clicks++; _siLogEvent("display_en_click"); }
  transcriptLineUiState[lineId] = { ...st, showEn: !st.showEn };
  renderTranscript();
}

function toggleLinePinyin(lineId) {
  const entry = (conversationTranscript || []).find((e, idx) => (e.id || String(idx)) === lineId);
  const st = transcriptLineUiState[lineId] || _defaultTranscriptLineUiState(entry?.role);
  if (!st.showPy) _tracker.display_py_clicks++;
  transcriptLineUiState[lineId] = { ...st, showPy: !st.showPy };
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

// Machine-translation register artifacts → spoken conversational forms (longer first).
const _SPOKEN_REGISTER_PAIRS = [
  ["同住", "一起住"],
  ["居住", "住"],
  ["共同", "一起"],
  ["您",   "你"],
  ["与",   "跟"],
];

/** Normalize formal/written register for matching and live translation post-processing. */
function _normalizeSpokenRegister(text) {
  if (!text) return text;
  let s = text;
  for (const [formal, spoken] of _SPOKEN_REGISTER_PAIRS) {
    s = s.split(formal).join(spoken);
  }
  return s;
}

/** Normalize for match: trim, collapse spaces, remove common punctuation. */
function normalizeForMatch(s) {
  if (typeof s !== "string") return "";
  const spoken = _normalizeSpokenRegister(s.trim());
  return spoken.replace(/\s+/g, "").replace(/[。？！，、；：""''\s]/g, "");
}

/** Acoustic filler particles — semantic emptiness does not become meaningful through repetition. */
const _FILLER_CHAR_SET = new Set(["嗯", "啊", "呃", "哦", "喔", "哎", "诶", "呀", "唉"]);
const _DISCOURSE_FRAGMENT_FILLERS = new Set(["这个", "那个", "就是"]);

function _isPureFillerUtterance(normalized) {
  if (!normalized) return false;
  if (_DISCOURSE_FRAGMENT_FILLERS.has(normalized)) return true;
  for (const ch of normalized) {
    if (!_FILLER_CHAR_SET.has(ch)) return false;
  }
  return normalized.length > 0;
}

function _hasNonFillerCjkChar(transcript) {
  const t = normalizeForMatch(transcript);
  if (!t) return false;
  for (const ch of t) {
    if (/[\u4e00-\u9fff]/.test(ch) && !_FILLER_CHAR_SET.has(ch)) return true;
  }
  return false;
}

function _isAffirmationAfterParaphrase(transcript) {
  const t = _normalizeSpokenRegister((transcript || "").trim());
  if (!t) return false;
  const prevWasParaphrase =
    (window._lastSemanticClarifyText || "").includes("你是说") ||
    (window._lastPartnerTurnText || "").includes("你是说") ||
    (window._lastPartnerFrameText || "").includes("你是说");
  if (!prevWasParaphrase) return false;
  return /^(对|是|嗯|好|对的|是的|没错|对啊|嗯嗯|对对|嗯呢)$/.test(t.replace(/[。！？,，\s]/g, ""));
}

function _isTurnAroundPhrase(transcript) {
  const t = _normalizeSpokenRegister((transcript || "").trim());
  if (!t) return false;
  const tn = normalizeConversationalFillers(t);
  if (/^(那?你呢|你怎么想|为什么这么问|为什么这样问|换我问|那你|你来问)/.test(t) || t === "你呢") return true;
  if (/[，。！]?(那?你呢|你怎么想|为什么这么问)[？?]?$/.test(t)) return true;
  if (/你(是哪里人|从哪里来|老家在哪|住(在哪|哪里|的地方)|做什么工作|的工作|是做什么|喜欢(什么|做什么)|有什么爱好|有家人|有没有家人)/.test(tn)) return true;
  return false;
}

/** Filler suppressor only — not a semantic gatekeeper. */
function _isSufficientLinguisticSignal(transcript, frameId) {
  const s = (transcript || "").trim();
  if (!s) return false;
  if (/不懂|不明白/.test(s)) return true;
  if (_isAffirmationAfterParaphrase(s)) return true;
  if (_isTurnAroundPhrase(s)) return true;
  if (_detectSemanticCategory(s)) return true;
  if (_DURATION_ANSWER_PAT.test(s)) return true;
  if (/[A-Za-z]/.test(s)) return true;
  if (isIncompleteLearnerUtterance(s)) return false;
  if (_hasNonFillerCjkChar(s)) return true;
  return false;
}

/** Single-token fillers / fragments — not substantive answers; avoid persona-stall recovery tone. */
function isIncompleteLearnerUtterance(transcript) {
  const raw = (transcript || "").trim();
  if (!raw) return false;
  const t = normalizeForMatch(raw);
  if (!t) return false;
  const fillers = new Set(["我", "嗯", "啊", "呃", "哦", "喔", "哎", "诶", "这个", "那个", "就是"]);
  if (fillers.has(t)) return true;
  if (_isPureFillerUtterance(t)) return true;
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
    "f_from_where", "frame.location.live_question", "f_live_where", "f_home_where",
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

/** Frames where learners often give foreign place names (Christchurch, Auckland, Dunedin) — Latin-heavy text is valid.
 *  f_live_where  = "你现在住哪里？"  (p2_frames.json)
 *  f_home_where  = "你老家在哪儿？"  (p2_frames.json)
 *  Both were previously missing, causing "我住在 Dunedin" to fail the latinCount veto. */
const _MIXED_SCRIPT_PLACE_FRAMES = new Set([
  "frame.location.live_question",
  "p2_pl_ext1",
  "f_from_where",
  "f_live_where",
  "f_home_where",
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
function _detectSemanticCategory(text, engineHint = "") {
  // Strip fillers so "啊我退休了" → "work_status", "就是我以前是老师" → "work_teacher".
  const t = normalizeConversationalFillers((text || "").trim());
  if (!t) return null;
  if (/我叫|名字|英文名/.test(t)) return "name";
  if (/吃|喜欢吃|牛肉|羊肉|好吃|食物/.test(t)) return "food";
  if (_DURATION_ANSWER_PAT.test(t) || /很多年|几年|很久/.test(t)) return "duration";
  if (/身体|健康|好多了|好很多|好一点|不好|生病|康复/.test(t)) return "family_health";
  if (/爸爸|妈妈|太太|家人|老婆|父母|家里|爱人|老公|女儿|儿子|孩子/.test(t)) return "family";
  if (/退休|以前.*工作|做.*工作/.test(t)) return "work_status";
  if (/是老师|教书|教学|大学.*老师|老师.*大学|以前是.*老师|以前在大学|在学校.*工作/.test(t)) return "work_teacher";
  // Distance / travel-time answers — place-context signals that satisfy distance frames.
  if (/很远|超远|好远|远着呢|坐飞机|乘飞机|坐火车|乘火车|飞机.*小时|小时.*飞机|小时.*火车|走路.*分钟/.test(t)) return "distance";
  // University / academic institution context — checked before Latin catch-all so
  // "Liverpool大学" or "西安交通大学" resolves to "education" not "name".
  if (/大学|学院|学校/.test(t) && /[A-Za-z]{2,}|交通|复旦|浙大|北大|清华|交大/.test(t)) return "education";
  // "我住在 Dunedin" / "我来自 Dunedin" must return "location" — checked before the
  // Latin-token catch-all below so the place context wins over the script heuristic.
  if (/住在|搬到|搬来|来自/.test(t)) return "location";
  if (/^哪里|^哪儿/.test(t)) return "location";
  if (/在哪里|在哪儿|哪里啊/.test(t)) return "location";
  // Nationality statement (新西兰人, 中国人 …)
  if (/新西兰人|澳大利亚人|中国人|英国人|美国人|加拿大人|日本人|韩国人/.test(t)) return "nationality";
  // History / culture signal
  if (/(历史|文化|景点|名胜)/.test(t)) return "history";
  // Latin token catch-all: only treat as a name attempt when the current engine is
  // identity/name-related.  In work/place/travel context the Latin text is likely a
  // proper noun (place name, institution) and should not surface the "你是说你的英文名字吗？"
  // clarification — that is a context mismatch and feels confusing to the learner.
  const _eng = (engineHint || window._currentEngineId || "").toLowerCase();
  if (/[A-Za-z]{3,}/.test(t) && (!_eng || /identity|name/.test(_eng))) return "name";
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
  work_teacher:  { hanzi: "你是说你以前是老师吗？",     pinyin: "nǐ shì shuō nǐ yǐqián shì lǎoshī ma?",   text_en: "Do you mean you were a teacher?" },
  distance:      { hanzi: "那个地方很远吗？",           pinyin: "nà ge dìfāng hěn yuǎn ma?",               text_en: "Is that place far away?" },
  location:      { hanzi: "你是说一个城市吗？",         pinyin: "nǐ shì shuō yīgè chéngshì ma?",          text_en: "Are you referring to a city?" },
  nationality:   { hanzi: "你是说你来自哪里？",         pinyin: "",                                         text_en: "Are you saying where you're from?" },
  history:       { hanzi: "你是说那里有很多历史吗？",   pinyin: "",                                         text_en: "Do you mean that place has a lot of history?" },
  education:     { hanzi: "你是说：你以前在大学工作吗？", pinyin: "",                                       text_en: "Do you mean you used to work at a university?" },
};

/** Returns the targeted clarification phrase object for the given category, or null. */
function _getSemanticClarification(category) {
  return _SEMANTIC_CLARIFICATION_PHRASES[category] || null;
}

// ── Work-context helpers (repeated-failure escalation model-answer tables removed) ──────────

// ── Work-context helpers ───────────────────────────────────────────────────────
/**
 * Updates window._learnerWorkContext based on the learner's text.
 * "retired" takes priority over "teacher" so that "以前是老师，现在退休了" is
 * classified as "retired".  Once set, the context persists until a fresh session.
 */
function _updateLearnerWorkContext(text) {
  const t = (text || "").trim();
  // Current employment explicitly stated → clear any prior education/retirement context
  // so company follow-up questions are no longer suppressed.
  if (t.includes("现在") && /公司|上班|工作/.test(t)) {
    window._learnerWorkContext = null;
    return;
  }
  if (/退休/.test(t)) {
    window._learnerWorkContext = "retired";
  } else if (/老师|学校|大学|教书|教学|学院/.test(t)) {
    window._learnerWorkContext = "teacher";
  }
}

// ── Partial-confirmation helpers ──────────────────────────────────────────────
/**
 * Builds a varied confirmation phrase for a given understood fragment.
 * forms[0] is currently always used; increment _confirmVariantIdx to rotate
 * among the other forms when confirmed safe in live testing.
 */
let _confirmVariantIdx = 0; // eslint-disable-line prefer-const
function _pickConfirmForm(body) {
  const forms = [
    `你是说：${body}吗？`,
    `${body}吗？`,
    `你说的是${body}吗？`,
  ];
  return forms[0]; // rotate with (_confirmVariantIdx++ % forms.length) when ready
}

/** Simple factual answers for known city/place location questions. */
const _CITY_LOCATION_MAP = {
  '重庆': '重庆在中国西南。',
  '西安': '西安在中国西北。',
  '上海': '上海在中国东边。',
  '成都': '成都在中国西南。',
  '北京': '北京在中国北方。',
  '广州': '广州在中国南边。',
  '新西兰': '新西兰在南半球。',
};

/**
 * Tries to extract a specific understood fragment from noisy rejected speech and
 * returns a "你是说：{content}吗？" confirmation phrase.
 * Checks are ordered most-specific first so the richest match wins.
 * Returns null when no strong signal is found (fall through to generic clarification).
 */
function _buildPartialConfirmation(text) {
  const t = (text || "").trim();
  if (!t) return null;

  // City + location-question → echo the city and answer where it is
  for (const [city, locationFact] of Object.entries(_CITY_LOCATION_MAP)) {
    if (t.includes(city) && /在哪里|在哪儿|哪里|哪里啊|地方/.test(t)) {
      return { hanzi: `你是问：${city}在哪里吗？${locationFact}`, pinyin: "", text_en: "" };
    }
  }

  // Nationality/from (新西兰人, 中国人 …)
  const natMatch = t.match(/新西兰人|澳大利亚人|中国人|英国人|美国人|加拿大人|日本人|韩国人|法国人|德国人/);
  if (natMatch) {
    return { hanzi: _pickConfirmForm(`你是${natMatch[0]}`), pinyin: "", text_en: "" };
  }

  // 老家 / 来自 + place word (2–4 chars)
  const laoJiaMatch = t.match(/老家[在是]?([\u4e00-\u9fff]{2,4})/);
  if (laoJiaMatch) {
    return { hanzi: _pickConfirmForm(`你老家在${laoJiaMatch[1]}`), pinyin: "", text_en: "" };
  }

  // Place name + history / culture signal
  const placeMatch = t.match(/(中国|重庆|西安|上海|成都|北京|广州|新西兰)/);
  if (placeMatch && /(历史|文化|特别|好玩|有名|特色|景点)/.test(t)) {
    return { hanzi: _pickConfirmForm(`${placeMatch[1]}有很多历史`), pinyin: "", text_en: "" };
  }

  // Specific food item
  const foodMatch = t.match(/(火锅|羊肉|牛肉|饺子|面条|炒饭)/);
  if (foodMatch) {
    return { hanzi: _pickConfirmForm(`你喜欢${foodMatch[1]}`), pinyin: "", text_en: "" };
  }

  // Spouse / partner + living-with signal
  if (/太太|老婆|老公|先生|爱人/.test(t) && /住|一起/.test(t)) {
    return { hanzi: _pickConfirmForm("你和太太一起住"), pinyin: "", text_en: "" };
  }

  // Family member health
  if (/(妈妈|爸爸|父母|家人)/.test(t) && /(身体|不好|生病|康复)/.test(t)) {
    return { hanzi: _pickConfirmForm("家人身体不太好"), pinyin: "", text_en: "" };
  }

  // Specific job title
  const jobMatch = t.match(/(老师|医生|工程师|护士|厨师|司机|律师)/);
  if (jobMatch) {
    return { hanzi: _pickConfirmForm(`你是${jobMatch[1]}`), pinyin: "", text_en: "" };
  }

  return null;
}

/**
 * Beginner output cap — prefers keeping two short clauses over a hard cut.
 *
 * 1. If the text is short or has no complex connectors, return as-is.
 * 2. Split on Chinese commas; keep first two clauses joined with "。".
 * 3. Fallback: truncate at first full-stop/exclamation boundary.
 * 4. Last resort: return original unchanged.
 */
function _simplifySentenceForBeginner(text) {
  if (!text) return text;
  const connectors = ["但是", "因为", "所以", "然后", "到处", "虽然", "不但", "况且", "不过", "一就"];
  const hasConnector = connectors.some(c => text.includes(c))
    || /一.{0,2}就/.test(text);  // 一…就 pattern
  if (text.length <= 22 || !hasConnector) return text;

  // Split on comma boundaries and keep first two clauses
  const parts = text.split(/[，,]/);
  if (parts.length >= 2) {
    const simplified = parts.slice(0, 2).join("，") + "。";
    // Only return simplified if it's actually shorter than the original
    if (simplified.length < text.length) return simplified;
  }

  // Fallback: truncate at first full sentence boundary
  const breakIdx = text.search(/[。！]/);
  if (breakIdx > 5 && breakIdx < text.length - 1) return text.slice(0, breakIdx + 1);

  return text;
}

/**
 * Returns true when the text looks like a well-formed short sentence that does NOT
 * need partial-confirmation ("你是说…吗？").  Saves the confirmation path for genuinely
 * noisy or structure-unclear inputs only.
 *
 * Heuristic: text has a subject (我/你), a verb-like word, an object, and is short (<20
 * chars).  Clean sentences should be acknowledged normally, not confirmed back at the
 * learner as if they were noisy.
 */
function _isLikelyCleanSentence(text) {
  if (!text) return false;
  const t = (text || "").trim();
  const hasSubject  = t.includes("我") || t.includes("你");
  const hasVerbLike = /(是|有|喜欢|去|住|在|做|想|爱|要|会|能)/.test(t);
  const hasObject   = t.length >= 4;
  // Presence of a repeated syllable pattern or strong noise markers means the text
  // is not clean even if it contains a subject and verb.
  const hasNoiseMarker = /(.)\1/.test(t) ||  // any repeated character (不不, 舍舍, etc.)
    /对不起|不好意思|啊啊|呃呃|嗯嗯/.test(t);
  return hasSubject && hasVerbLike && hasObject && t.length < 20 && !hasNoiseMarker;
}

// ── Interaction-priority helpers ─────────────────────────────────────────────
/**
 * Returns true when the learner's utterance is directed at the persona as a
 * question that should be answered before the app resumes its own agenda.
 * Covers: 你…吗, explicit ？, sentence-final question particles paired with
 * a persona-addressed subject word, and reciprocal "你呢" turns.
 */
function _isUserDirectedQuestion(text) {
  if (!text) return false;
  const t = (text || "").trim();
  // Guard: learner disclosures starting with "你知道吗" + first-person family/health content
  // must NOT be classified as persona questions — "你知道吗" contains 你+吗 but is a
  // disclosure opener, not a turn-around question.
  if (/^你知道吗/.test(t) && /我(妈|爸|家|孩子|家人|身体|最近很担心)/.test(t)) return false;
  if (/你/.test(t) && /[吗？?]/.test(t)) return true;   // 你…吗 / 你…?
  if (/[？?]$/.test(t)) return true;                      // explicit question mark
  if (/吗[？?]?$/.test(t)) return true;                   // sentence-final 吗
  if (/你呢/.test(t)) return true;                        // reciprocal turn
  // 你 + sentence-final question particle (spoken ASR omits ？)
  if (/你/.test(t) && /[啊呢][？?]?$/.test(t)) return true;
  // Omitted-subject question forms: learner addresses persona without an explicit "你"
  // but the structure is clearly a question directed at the persona.
  if (/结婚了吗|有孩子吗|多大[啊？?]?$|几岁[啊？?]?$|做多久了|多久了[啊？?]?$|去过哪里|喜欢吗[？?]?$/.test(t)) return true;
  if (/^(结婚|有孩子|多大|几岁|做多久|多久|去过哪里|喜欢吗)/.test(t)) return true;
  return false;
}

/**
 * Returns true when the learner explicitly signals they cannot follow — stronger
 * than the generic "我不懂" skip signal. These deserve an empathetic response
 * rather than a silent topic skip.
 * Also normalises common ASR mis-transcriptions (e.g. "1点" → "一点").
 */
function _isStrongConfusionText(text) {
  const t = (text || "").replace(/1点/g, "一点");  // ASR digit normalisation
  return /听不懂|没听懂|一点听不懂|完全不明白|听不清楚|不懂你说|一点不懂|一点都不懂|一点不明白|一点都不明白|有点不懂|不太明白|不明白|听不明白|没明白|不知道什么意思|什么意思/.test(t);
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

// ── Conversational filler normalisation ──────────────────────────────────────
// Strip leading filler particles before content classification so that
// "啊我退休了" / "嗯我是新西兰人" / "ne 你是哪里人" reach the right handlers.
const _LEADING_FILLER_PAT = /^(?:(?:[啊嗯呃哦哎呀唉]+)[，。\s]*|(?:那个|就是|然后|这个|好那|嗯那)[，\s]*|(?:ne|ah|um|uh|er)\s+)+/i;

/**
 * Return text with leading conversational fillers removed.
 * Preserves the original if stripping would leave fewer than 2 characters
 * (standalone filler → keep for confusion/affirmation detection).
 */
function normalizeConversationalFillers(text) {
  const t = (text || "").trim();
  if (!t) return t;
  const stripped = t.replace(_LEADING_FILLER_PAT, "").trim();
  return stripped.length >= 2 ? stripped : t;
}

function semanticSoftMatch(transcript, frameId) {
  const t = _normalizeSpokenRegister((transcript || "").trim());
  const fid = (frameId || "").trim();
  if (!t) return false;
  // Plain affirmation after a paraphrase question ("你是说：...") — route to server as confirmation.
  // Run this check on RAW text so standalone "对/嗯" still confirms correctly.
  const _prevWasParaphrase =
    (window._lastSemanticClarifyText || "").includes("你是说") ||
    (window._lastPartnerTurnText || "").includes("你是说") ||
    (window._lastPartnerFrameText || "").includes("你是说");
  if (_prevWasParaphrase && /^(对|是|嗯|好|对的|是的|没错|对啊|嗯嗯|对对|嗯呢)$/.test(
    t.replace(/[。！？,，\s]/g, ""))) return true;
  // Normalise leading fillers for all subsequent content matching.
  // (Affirmation check above already handled the raw-text case.)
  const tn = normalizeConversationalFillers(t);
  // Turn-around / reciprocity phrases — always accept regardless of the current frame.
  // ASR rarely captures the trailing "？" so match without it.
  // Matches: standalone "你呢", leading "你呢…", AND trailing "[answer]，你呢" compound answers.
  // Use raw t so "你呢" is never stripped by filler normalisation.
  if (/^(那?你呢|你怎么想|为什么这么问|为什么这样问|换我问|那你|你来问)/.test(t) || t === "你呢") return true;
  if (/[，。！]?(那?你呢|你怎么想|为什么这么问)[？?]?$/.test(t)) return true;
  // Direct questions aimed at the partner — user turns the conversation around.
  // Use tn (normalised) so "ne 你是哪里人" / "啊你是哪里人" route here.
  if (/你(是哪里人|从哪里来|老家在哪|住(在哪|哪里|的地方)|做什么工作|的工作|是做什么|喜欢(什么|做什么)|有什么爱好|有家人|有没有家人)/.test(tn)) return true;
  // Distance / travel-time answers on place-distance frames — accept immediately, no strikes needed.
  const _DIST_FRAMES = new Set(["p2_pl_far", "f_place_distance_time", "f_place_distance_ref"]);
  if (_DIST_FRAMES.has(fid)) {
    if (/远|近|飞机|火车|走路|小时|分钟|公里|里路|很远|超远|好远|不远/.test(tn)) return true;
  }
  // Scenery / place-quality free answers (often unmatched to word tiles)
  if (/(风景|山水|漂亮|好看|很美|美|空气|环境|舒服|安静|不错|挺好|海|湖|山|树|绿)/.test(tn)) return true;
  // Travel destination answers — scoped to frames where "going somewhere" is the actual question.
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
    if (/会去|要去|去过|打算去|计划去/.test(tn)) return true;
    if (/(中国|日本|英国|美国|法国|德国|澳大利亚|加拿大|欧洲|亚洲|新西兰|香港|台湾|韩国|东南亚|泰国|印度|新加坡|越南|意大利|西班牙)/.test(tn)) return true;
  }
  // Foreign city / region names in Latin — use tn so filler-prefixed answers still match.
  if (_MIXED_SCRIPT_PLACE_FRAMES.has(fid) && /[\u4e00-\u9fff]/.test(tn) && /[A-Za-z]/.test(tn)) return true;
  // Identity: how people call you — tolerate ASR / mixed-script name answers.
  if (_NICKNAME_CALL_FRAMES.has(fid)) {
    if (looksLikeNicknameCallAnswer(tn, fid)) return true;
    if (tn.includes("叫我") || tn.includes("大家叫")) return true;
    const hasZh = /[\u4e00-\u9fff]/.test(tn);
    const hasLatin = /[A-Za-z]/.test(tn);
    if (hasZh && hasLatin) return true;
  }
  // Food frames: accept food nouns combined with any evaluator, and standalone good/bad evaluators.
  const _FOOD_FRAMES = new Set(["f_food_what_good", "f_food_tasty", "f_food_famous_dish", "f_food_like_spicy", "f_food_expensive"]);
  if (_FOOD_FRAMES.has(fid)) {
    if (/羊肉|牛肉|猪肉|鸡肉|鱼|面|饺子|火锅|米饭|汤|菜|包子|烤|粥|寿司|蛋糕|海鲜|蔬菜|水果/.test(tn)) return true;
    if (/不错|好吃|很好|好香|很香|挺好|非常好|很棒|好喝|很甜|很辣|很鲜|好吃的/.test(tn)) return true;
    if (/不知道|没有|不清楚|都行|随便/.test(tn)) return true;
  }
  // Family frequency: accept natural free responses about seeing family.
  if (fid === "p2_fa_2") {
    if (/(家人|妈妈|爸爸|父母)/.test(tn) && /(天|周|月|常|每天|经常|周末)/.test(tn)) return true;
  }
  // Family member / living-with frames.
  const _FAMILY_MEMBER_FRAMES = new Set([
    "f_live_with_who", "p2_fa_live_with", "f_probe_family_closest", "f_probe_family_together",
    "f_probe_family_influence", "f_have_children",
  ]);
  if (_FAMILY_MEMBER_FRAMES.has(fid)) {
    if (/(老婆|妻子|老公|丈夫|先生|爱人|妈妈|爸爸|母亲|父亲|父母|哥哥|弟弟|姐姐|妹妹|儿子|女儿|孩子|家人|家里|爷爷|奶奶|外公|外婆)/.test(tn)) return true;
    if (/(一个人|自己住|单独住|独居|和.*一起住|跟.*住)/.test(tn)) return true;
  }
  // Family activity frames.
  const _FAMILY_ACTIVITY_FRAMES = new Set(["p2_fa_activity", "f_probe_family_together"]);
  if (_FAMILY_ACTIVITY_FRAMES.has(fid)) {
    if (/[\u4e00-\u9fff]{2,}/.test(tn)) return true;
  }
  // Work "why like this job": accept reason-like content.
  if (fid === "p2_wk_1") {
    if (/(因为|为了|可以|能|学|帮助|工资|时间|喜欢)/.test(tn)) return true;
  }
  // Work/retirement: accept clearly work-status answers so filler-prefixed inputs
  // ("啊我退休了", "就是我以前是老师") don't require a "你是说..." confirmation round-trip.
  if (/^(f_what_work|p2_wk)/.test(fid) || fid === "f_what_work") {
    if (/退休/.test(tn)) return true;
    if (/老师|教书|教学|讲课|在学校|在大学/.test(tn)) return true;
  }
  // Origin/nationality: nationality statements are unambiguous regardless of frame.
  if (/(新西兰人|澳大利亚人|中国人|英国人|美国人|加拿大人|日本人|韩国人)/.test(tn)) return true;
  // Duration tenure: "20年", "5年", "很多年" for work or hobby duration frames.
  const _DURATION_FRAMES = new Set(["f_work_tenure", "p2_hb_5"]);
  if (_DURATION_FRAMES.has(fid) && (_DURATION_ANSWER_PAT.test(tn) || /很多年|几年|很久|多年/.test(tn))) return true;
  // Family health / emotional check-in.
  if (fid === "f_probe_emotional_checkin") {
    if (/身体|健康|好多了|好很多|好一点|不好|生病|康复|恢复|没事了|好转|现在好/.test(tn)) return true;
    if (/[\u4e00-\u9fff]{3,}/.test(tn)) return true;
  }
  // Name-statement frames: "我叫X" / "英文名" / Latin name in frames asking the learner's name.
  const _NAME_STATEMENT_FRAMES = new Set(["f_ask_you_name", "p2_id_4", "p2_id_5", "f_name_story", "f_name_story_elicit"]);
  if (_NAME_STATEMENT_FRAMES.has(fid)) {
    if (/我叫|名字是|英文名|[A-Za-z]{2,}/.test(tn)) return true;
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
  if (/(有什么特别|有什么好吃|有什么好玩|有什么特色|有什么有意思)/.test(s)) return true;
  if (/(怎么样啊|怎么样呢)/.test(s)) return true;
  if (/喜欢吗|远吗|好吗/.test(s) && s.length <= 12) return true;
  return false;
}

/**
 * Classify a rejection as SOFT (partial meaning, partial Chinese) or HARD (no signal, noise).
 * Used to weight unmatched responses in the stability scorecard.
 *   HARD → counts fully in scorecard stability denominator
 *   SOFT → counts at 0.5 weight (tracked separately; same UI display text)
 */
function _unmatchedFailLevel(transcript) {
  const zhChars = ((transcript || "").match(/[\u4e00-\u9fff]/g) || []).length;
  if (zhChars < 1) return "hard";                        // no Chinese at all — noise
  if (zhChars <= 2 && !_detectSemanticCategory(transcript)) return "hard"; // minimal + no meaning
  return "soft";                                         // partial meaning, understandable but not routable
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
  // Learner counter-question to persona: contains 你+吗 = direct question regardless of frame.
  // E.g. "孩子呢你有孩子吗", "你结婚了吗", "你在哪里工作吗".  Always send to server.
  if (/你/.test(transcript || "") && /吗/.test(transcript || ""))
    return { accept: true, reason: "learner_counter_question" };
  // Family-member question: learner asking about persona's family member (no 你/吗 required).
  // E.g. "女儿做什么工作啊", "孩子多大了", "儿子在哪里上班".
  const _hasFamilyMemberQ = (
    /(女儿|儿子|孩子|太太|老婆|先生|老公|爸爸|妈妈|父母)/.test(transcript || "") &&
    /(做什么|工作|在哪|哪里|上班|上学|多大|几岁|结婚|有没有|怎么样)/.test(transcript || "")
  );
  if (_hasFamilyMemberQ) return { accept: true, reason: "family_member_question" };
  // Linguistic confusion signal: learner echoes the frame's question word + "什么" to express
  // confusion ("哪里什么" = "what do you mean by 'where'?"). Reject so the not-understood path
  // fires with a targeted clarification rather than accepting and sending to the server.
  // Always soft — learner clearly heard the frame, just didn't understand it.
  const _isLinguisticConfusion = /^(哪里什么|哪儿什么|什么哪里|什么哪儿|哪里啊什么|哪里啊)/i.test((transcript || "").trim());
  if (_isLinguisticConfusion) return { accept: false, reason: "linguistic_confusion_signal", fail_level: "soft" };
  if (!_isSufficientLinguisticSignal(transcript, frameId)) {
    return { accept: false, reason: "insufficient_linguistic_signal", fail_level: "hard" };
  }
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
  // For explicit rejections, classify as soft or hard based on Chinese signal strength.
  const _fl = _unmatchedFailLevel(transcript);
  if (openEnded && !understandable) return { accept: false, reason: "open_ended_low_confidence", fail_level: _fl };
  if (hasStructuredSlots && !understandable) return { accept: false, reason: "slot_frame_low_confidence", fail_level: _fl };
  return { accept: false, reason: "closed_options_unmatched", fail_level: _fl };
}

/**
 * Listen for speech (zh-CN) and try to match to current options. Resolves with { transcript, matchedOption }.
 * Uses Web Speech API; if unavailable or error, resolves with transcript "" and matchedOption null.
 */
// Milliseconds of silence after the last detected speech before the turn ends.
// Increase this to give learners more time to construct sentences.
const SPEECH_SILENCE_MS = 3000;
// Longer silence budget before the learner has spoken (iOS WebKit — Safari, Chrome, etc.).
const SPEECH_PRE_SPEECH_SILENCE_MS_MOBILE = 4000;
const SPEECH_PRE_SPEECH_SILENCE_MS_DESKTOP = 4500;
// Ignore immediate onend-with-no-speech within this window (iOS WebKit quirk).
const SPEECH_MIN_LISTEN_GRACE_MS_MOBILE = 1800;
const SPEECH_MIN_LISTEN_GRACE_MS_DESKTOP = 1000;
// One-shot patience window when silence ends on pure filler (e.g. mmmm → 嗯嗯).
const SPEECH_FILLER_EXTEND_MS = 2000;

// ── Listening state indicator ────────────────────────────────────────────────
// Subtle line below the mic: hidden while opening; appears once speech is detected.
function _setListenState(state, message) {
  const el = document.getElementById("listenStatus");
  const armsMic = state === "preparing" || state === "listening" || state === "waiting"
    || state === "processing" || state === "reconnect";
  document.body.classList.toggle("is-listening", armsMic);
  if (window._listenNoticeTimer) {
    clearTimeout(window._listenNoticeTimer);
    window._listenNoticeTimer = null;
  }
  if (!el) return;

  // Opening / reconnect — arm mic without showing a banner.
  if (state === "preparing") {
    el.dataset.state = "idle";
    el.innerHTML = "";
    return;
  }
  if (state === "reconnect") return;

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
    case "notice":
      el.innerHTML = `<span>${message || "Tap the mic and speak"}</span>`;
      document.body.classList.remove("is-listening");
      break;
    default:
      el.innerHTML = "";
      break;
  }
}

function _showListenNotice(message, autoClearMs = 3500) {
  _setListenState("notice", message);
  if (autoClearMs > 0) {
    window._listenNoticeTimer = setTimeout(() => _setListenState("idle"), autoClearMs);
  }
}

function listenForResponse(options, timeoutMs) {
  _setListenState("preparing");
  return new Promise((resolve) => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      emitUITrace({ type: "SPEECH_NOT_AVAILABLE", timestamp: new Date().toISOString(), payload: { message: "SpeechRecognition not supported" } });
      _showListenNotice("Speech recognition is not available in this browser.");
      resolve({ transcript: "", matchedOption: null, asr_confidence: null, finishReason: "not_available" });
      return;
    }
    // Mic requires HTTPS on iOS/Chrome (except localhost). Detect early and give a clear message.
    if (_isMobileLayout() && location.protocol === "http:" &&
        location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
      emitUITrace({ type: "SPEECH_INSECURE_ORIGIN", timestamp: new Date().toISOString(), payload: { host: location.hostname } });
      _showListenNotice("Mic needs HTTPS — open this app via https:// or use Safari on this device.", 6000);
      resolve({ transcript: "", matchedOption: null, asr_confidence: null, finishReason: "insecure_origin" });
      return;
    }
    // Stop partner TTS before opening the mic — prevents ASR from transcribing speaker output
    // (echo loop: app "talking to itself" / user line duplicating partner line).
    try {
      if (window.speechSynthesis) window.speechSynthesis.cancel();
    } catch (_) {}
    const isMobileListen = _isMobileLayout();
    const rec = new SpeechRecognition();
    // iOS WebKit: continuous mode is unreliable — use single-utterance + manual restart on onend.
    rec.continuous = !isMobileListen;
    rec.lang = "zh-CN";
    rec.interimResults = true;
    AsrDiag.begin({
      is_mobile: isMobileListen,
      user_agent: (typeof navigator !== "undefined" && navigator.userAgent) || "",
      lang: rec.lang,
      continuous: rec.continuous,
      interim_results: rec.interimResults,
    });
    let finalTranscript = "";
    let interimTranscript = "";
    let lastConf = null;
    let resolved = false;
    let silenceTid = null;
    let wallClockTid = null;
    let waitingTid = null;   // transitions indicator to "waiting" ~800ms after last speech event
    let speechStarted = false;
    let fillerExtendFired = false;
    let micStarted = false;   // set in rec.onstart — used to distinguish "never opened" from "no speech"
    let listenStartedAt = 0;
    let onendRetryCount = 0;
    const preSpeechSilenceMs = _isMobileLayout()
      ? SPEECH_PRE_SPEECH_SILENCE_MS_MOBILE
      : SPEECH_PRE_SPEECH_SILENCE_MS_DESKTOP;
    const minListenGraceMs = _isMobileLayout()
      ? SPEECH_MIN_LISTEN_GRACE_MS_MOBILE
      : SPEECH_MIN_LISTEN_GRACE_MS_DESKTOP;
    // Wall-clock budget once speech has begun — gives slow learners time to complete sentences.
    const SPEECH_ACTIVE_MAX_MS = 13000;

    function getBestTranscript() {
      return (finalTranscript || interimTranscript || "").trim();
    }

    function noteSpeechActivity() {
      if (speechStarted) return;
      speechStarted = true;
      if (wallClockTid) { clearTimeout(wallClockTid); wallClockTid = null; }
      wallClockTid = setTimeout(() => {
        console.log("[ASR] active-speech wall-clock fired");
        finish("wall_clock_active");
      }, SPEECH_ACTIVE_MAX_MS);
      console.log(`[ASR] speech started — active wall-clock set to ${SPEECH_ACTIVE_MAX_MS}ms`);
    }

    // ── finish(reason): single guarded submission point ─────────────────────
    // Called by the silence timer, wall-clock timer, or onend (backup).
    // Whichever fires first wins; all subsequent calls are no-ops.
    function finish(reason) {
      if (resolved) return;
      resolved = true;
      // Expose whether the mic actually opened (onstart fired) for the caller's error message
      window._lastMicStarted = micStarted;
      console.log(`[ASR] finish: reason=${reason}, transcript="${getBestTranscript()}", micStarted=${micStarted}`);
      if (silenceTid)  { clearTimeout(silenceTid);  silenceTid  = null; }
      if (wallClockTid){ clearTimeout(wallClockTid); wallClockTid = null; }
      if (waitingTid)  { clearTimeout(waitingTid);  waitingTid  = null; }
      _setListenState("processing");

      const finalize = () => {
        const _selSource = finalTranscript ? "final" : (interimTranscript ? "interim" : "none");
        AsrDiag.ev("finish", { reason, selected_source: _selSource, final: finalTranscript || "", interim: interimTranscript || "" });
        AsrDiag.set("finish_reason", reason);
        AsrDiag.set("selected_source", _selSource);
        AsrDiag.set("selected_transcript", getBestTranscript());
        finalTranscript = getBestTranscript();
        interimTranscript = "";
        const matched = matchTranscriptToOption(finalTranscript, options || []);
        AsrDiag.set("matched_option", matched ? (matched.hanzi || "") : null);
        const ac = typeof lastConf === "number" && !Number.isNaN(lastConf) ? lastConf : null;
        resolve({
          transcript: finalTranscript,
          matchedOption: matched ?? null,
          asr_confidence: ac,
          finishReason: reason,
        });
      };

      // iOS: stop (not abort) so final results can arrive before we read the transcript.
      if (isMobileListen) {
        try { rec.stop(); } catch (_) { try { rec.abort(); } catch (_2) {} }
        setTimeout(finalize, 250);
      } else {
        try { rec.abort(); } catch (_) {}
        finalize();
      }
    }

    function absorbResults(e) {
      noteSpeechActivity();
      let chunkFinal = "";
      let chunkInterim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const seg = e.results[i][0];
        if (e.results[i].isFinal) {
          chunkFinal += seg.transcript;
          if (typeof seg.confidence === "number") lastConf = seg.confidence;
        } else {
          chunkInterim += seg.transcript;
        }
      }
      if (isMobileListen) {
        let latestFinal = "";
        let latestAny = "";
        for (let i = 0; i < e.results.length; i++) {
          const t = (e.results[i][0].transcript || "").trim();
          if (!t) continue;
          latestAny = t;
          if (e.results[i].isFinal) latestFinal = t;
        }
        if (latestFinal) {
          finalTranscript = latestFinal;
          interimTranscript = "";
        } else if (latestAny) {
          interimTranscript = latestAny;
        }
      } else {
        if (chunkFinal) {
          finalTranscript = (finalTranscript + chunkFinal).trim();
          interimTranscript = "";
        }
        if (chunkInterim) interimTranscript = chunkInterim.trim();
      }
      if (chunkFinal || chunkInterim) {
        AsrDiag.ev("asr_result", {
          is_final: !!chunkFinal,
          chunk_final: chunkFinal || "",
          chunk_interim: chunkInterim || "",
          final_so_far: finalTranscript || "",
          interim_so_far: interimTranscript || "",
          conf: typeof lastConf === "number" ? lastConf : null,
        });
      }
      if (finalTranscript) {
        console.log(`[ASR] onresult final: "${finalTranscript}"`);
      } else if (interimTranscript) {
        console.log(`[ASR] onresult interim: "${interimTranscript}"`);
      }
      _setListenState("listening");
      if (waitingTid) clearTimeout(waitingTid);
      waitingTid = setTimeout(() => {
        if (!resolved) _setListenState("waiting");
      }, 1400);
      resetSilenceTimer();
    }

    function resetSilenceTimer() {
      if (resolved) return;
      if (silenceTid) clearTimeout(silenceTid);
      const silenceDelay = speechStarted ? SPEECH_SILENCE_MS : preSpeechSilenceMs;
      silenceTid = setTimeout(() => {
        if (resolved) return;
        const fillerOnly = isIncompleteLearnerUtterance(getBestTranscript());
        if (!fillerExtendFired && fillerOnly) {
          fillerExtendFired = true;
          console.log(`[ASR] filler-only silence — extending listen ${SPEECH_FILLER_EXTEND_MS}ms`);
          _setListenState("waiting");
          silenceTid = setTimeout(() => {
            console.log(`[ASR] filler extend timeout fired, transcript="${finalTranscript}"`);
            finish("silence_filler_extended");
          }, SPEECH_FILLER_EXTEND_MS);
          return;
        }
        console.log(`[ASR] silence timeout fired, transcript="${finalTranscript}"`);
        finish("silence");
      }, silenceDelay);
    }

    rec.onresult = (e) => absorbResults(e);

    // onend: iOS fires early/often — restart while empty; finish when we have a transcript.
    rec.onend = () => {
      const txt = getBestTranscript();
      console.log(`[ASR] onend fired, transcript="${txt}"`);
      if (resolved) return;
      if (txt) {
        finish("onend");
        return;
      }
      const elapsed = listenStartedAt ? Date.now() - listenStartedAt : 0;
      if (onendRetryCount < 5 && elapsed < timeoutMs - 500) {
        onendRetryCount += 1;
        console.log(`[ASR] onend empty (${elapsed}ms) — restart attempt ${onendRetryCount}`);
        _setListenState("reconnect");
        try {
          rec.start();
          listenStartedAt = Date.now();
          resetSilenceTimer();
          return;
        } catch (err) {
          console.log(`[ASR] onend restart failed: ${err}`);
        }
      }
      finish("onend");
    };

    rec.onstart = () => {
      micStarted = true;
      AsrDiag.ev("onstart");
      _setListenState("listening");
    };

    rec.onerror = (e) => {
      console.log(`[ASR] onerror: ${e.error}`);
      if (e.error === "aborted") return;    // expected when finish() calls rec.abort()
      if (e.error === "no-speech") return;  // let silence/onend handle the empty-speech case
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        finish("permission_denied");
        return;
      }
      finish("error");
    };

    function beginListening() {
      if (resolved) return;
      wallClockTid = setTimeout(() => {
        console.log("[ASR] wall-clock timeout fired");
        finish("wall_clock");
      }, timeoutMs);
      resetSilenceTimer();
      try {
        rec.start();
        listenStartedAt = Date.now();
        emitUITrace({
          type: "SPEECH_LISTEN_START",
          timestamp: new Date().toISOString(),
          payload: {
            lang: "zh-CN",
            continuous: rec.continuous,
            silence_ms: preSpeechSilenceMs,
            min_listen_grace_ms: minListenGraceMs,
            mobile_listen: isMobileListen,
          },
        });
      } catch (err) {
        console.log(`[ASR] rec.start() error: ${err}`);
        finish("start_error");
      }
    }

    // Mobile: start synchronously in the user-gesture turn (setTimeout breaks iOS permission chain).
    if (isMobileListen) {
      beginListening();
    } else {
      setTimeout(beginListening, 380);
    }
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

/** Keep #frameEnglish vs ?-hint rows from doubling the same English line. */
function _syncActiveEnglishDisplay() {
  const fe = document.getElementById("frameEnglish");
  const hintMeaning = document.getElementById("hintMeaning");
  const hintPinyin = document.getElementById("hintPinyin");
  if (!fe) return;
  if (_challenge.active) {
    fe.style.display = "none";
    return;
  }
  const enText = (fe.textContent || "").trim();
  const hintEnVisible =
    hintMeaning &&
    hintMeaning.style.display !== "none" &&
    (hintMeaning.textContent || "").trim();
  const hintPyVisible =
    hintPinyin &&
    hintPinyin.style.display !== "none" &&
    (hintPinyin.textContent || "").trim();
  if (hintEnVisible) {
    fe.style.display = "none";
    return;
  }
  fe.style.display = enText ? "block" : "none";
  if (hintPyVisible && enText) {
    fe.style.marginBottom = "4px";
  }
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
  _syncActiveEnglishDisplay();
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
    // On mobile the card is a fixed bottom sheet — scrollIntoView fights the layout.
    if (wasHidden && !_isMobileLayout()) {
      setTimeout(() => cardPanel.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    }
    _syncMobileCardSheet(true);
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
    _syncMobileCardSheet(false);
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
        _dismissOnboardingGuideIfActive();
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
  // Partner is already shown in the top persona bar — keep active panel for the utterance only.
  nameLabel.textContent = partnerName ? `${partnerName}:` : "";
  prefixLine.textContent = partnerPrefix || "";
  header.style.display = "none";
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
  if (!opt) return false;

  const scrollWrap = document.createElement("div");
  scrollWrap.className = "recovery-phrases-scroll";

  // Each phrase uses the same flat flex-wrap structure as discovery panels:
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

    panel.addEventListener("click", async (ev) => {
      if (ev.target.closest(".op-icon-btn")) return;
      if (document.body.classList.contains("is-listening")) return;
      if (Date.now() - (window._micListenArmedAt || 0) < 450) return;
      _tracker.recovery_uses++;
      _tracker._pendingRecovery = true;
      _siLogEvent("recovery_use", { frame_id: frameId, kind: phrase.id || "recovery" });
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
      _refreshActiveEnglishFromSentenceHint();
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

  if (_isMobileLayout()) {
    const details = document.createElement("details");
    details.className = "recovery-panel-collapsible";
    const summary = document.createElement("summary");
    summary.className = "recovery-panel-label recovery-panel-toggle";
    summary.textContent = "Need help? Tap for emergency phrases";
    details.appendChild(summary);
    details.appendChild(scrollWrap);
    targetContainer.appendChild(details);
  } else {
    const header = document.createElement("div");
    header.className = "recovery-panel-label";
    header.textContent = "Need help?";
    targetContainer.appendChild(header);
    targetContainer.appendChild(scrollWrap);
  }
  return true;
}

function _scrollRecoveryPanelIntoView() {
  if (_isMobileLayout()) {
    const host = document.querySelector(".current-turn-options");
    if (host) host.scrollTop = 0;
    return;
  }
  const target = _challenge.active
    ? document.getElementById("challengeRecoveryZone")
    : document.getElementById("sentenceOptionsContainer");
  if (!target || !target.querySelector('[data-recovery="true"]')) return;
  requestAnimationFrame(() => {
    target.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
}

function _scrollOptionsIntoViewIfDesktop(el) {
  if (_isMobileLayout() || !el) return;
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
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
        // Do NOT hide the discovery panel here — keep it visible while the next turn loads.
        // runTurn will update the panel with fresh questions or restore the cache.
        window._pendingFrameText = null;   // consumed: learner answered, not deferring
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
        addTranscriptEntry("partner", partnerLine, transcriptExtrasForRecoveryPartnerRepeat(action));
        renderTranscript();
        setActivePartnerStatement(partnerLine, "recovery_repeat", segments);
        _refreshActiveEnglishFromSentenceHint();
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

      if (opt.card_id && opt.kind !== "FRAME_WITH_SLOTS" && _shouldAlsoOpenCardPanel()) {
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
  const hasRecoveryPanel = !!getRecoveryPanelOption();
  if (!answers.length && !hasRecoveryPanel) {
    container.style.display = "none";
    return;
  }

  if (_challenge.active) {
    const zone = document.getElementById("challengeRecoveryZone");
    if (zone) zone.innerHTML = "";
  }

  // Build suggested answers first — keeps yellow recovery cards away from the mic strip on mobile.
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
        // Priority gate: if the tapped sentence is a learner question to the persona,
        // clear confusion state so the server won't route it as a repair turn.
        if (_isUserDirectedQuestion(hanziStr)) {
          window._recentConfusionCount = 0;
          window._lastRepairKind = null;
        }
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

  if (_challenge.active) {
    const zone = document.getElementById("challengeRecoveryZone");
    if (zone) renderRecoveryPanelInto(zone, frameId);
  } else {
    renderRecoveryPanelInto(container, frameId);
  }

  // Keep the reverseActionsRow clear
  const reverseActionsRow = document.getElementById("reverseActionsRow");
  if (reverseActionsRow) reverseActionsRow.innerHTML = "";

  container.style.display = "flex";
  if (hasRecoveryPanel || container.querySelector('[data-recovery="true"]')) {
    _scrollRecoveryPanelIntoView();
  } else if (_isMobileLayout()) {
    const host = document.querySelector(".current-turn-options");
    if (host) host.scrollTop = 0;
  }
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
  _initActiveTurnRecord(
    t,
    data?.frame_text_en != null ? String(data.frame_text_en).trim() : "",
    data?.frame_pinyin || "",
    uid,
  );
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
    addTranscriptEntry("partner", stub, partnerTranscriptExtrasFromData(data, stub));
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

  // Update engine state from the server response so subsequent runTurn calls
  // continue from the correct engine rather than restarting from identity.
  // This is especially important when the mirror question is the FIRST user action
  // (e.g. user opens with "你是哪里人？" before any app-led question).
  if (data.engine_id && data.engine_id !== "unknown") {
    const _prevEng = window._currentEngineId || "";
    window._currentEngineId = data.engine_id;
    // Stale semantic clarification must not survive an engine change.
    if (_prevEng && _prevEng !== data.engine_id) window._lastSemanticClarifyText = "";
  }
  if (data.state_update && typeof data.state_update.current_engine === "string" && data.state_update.current_engine) {
    const _prevEng2 = window._currentEngineId || "";
    window._currentEngineId = data.state_update.current_engine;
    if (_prevEng2 && _prevEng2 !== data.state_update.current_engine) window._lastSemanticClarifyText = "";
  }

  if (stub) {
    addTranscriptEntry("partner", stub, partnerTranscriptExtrasFromData(data, stub));
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
    addTranscriptEntry("partner", stub, partnerTranscriptExtrasFromData(data, stub));
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
    el.textContent = "Memory — No saved learner memory yet.";
    el.style.display = "";
  }
}

/** Fetch current learner memory from the server and update the banner immediately. */
async function _refreshMemoryBanner() {
  try {
    const res = await fetch(`/api/memory?learner_id=${encodeURIComponent(window._learnerId || "default_learner")}`);
    if (res.ok) {
      const data = await res.json();
      _renderMemoryBanner(data.memory || {});
    }
  } catch (_) {}
}

/**
 * Reset current-session UI, counters, and transient state for a clean new conversation.
 * Preserves: selected persona, selected frame, learner memory, progress history, card data.
 * Does not call the server or clear long-term localStorage progress records.
 */
function _resetCurrentSessionState() {
  _cancelProbeAutoAdvance();
  hideSentenceOptions();
  window._runTurnInFlight = false;

  window._sessionId = "session_" + Date.now();
  window._sessionStartedAt = Date.now();
  window._recentFrameIds = [];
  window._lastAnswer = null;
  window._probeDepth = 0;
  window._userQuestionChain = 0;
  window._lastProbeOptions = [];
  window._revealedVoiceLines = {};
  window._revealedPartnerFacts = {};
  window._exchangeCount = 0;
  window._curiosityDepth = 0;
  window._askChainCount = 0;
  window._lastPartnerTurnType = "question";
  window._sameEngineChainCount = 0;
  window._sameSlotChainCount = 0;
  window._lastFocusSlot = "";
  window._pendingListeningMove = false;
  window._listeningWaitTurns = 0;
  window._lastInterestLevel = "low";
  window._lastUserText = "";
  window._lastTurnWasNoisyOrConfusion = false;
  window._confusionFrameText = null;
  window._learnerWorkContext = null;
  window._unmatchedByFrame = {};
  window._recoveryPromptsByFrame = {};
  window._consecutiveNotUnderstood = 0;
  window._lastRepairKind = null;
  window._prevRepairKind = null;
  window._lastPartnerFrameId = null;
  window._isPostClosingMove = false;
  window._loopCountInEngine = 0;
  window._enginesVisited = ["identity"];
  window._recentConfusionCount = 0;
  window._seededBridgeEngines = [];
  window._mediumProbeFiredEngines = [];
  window._repairAttemptCount = 0;
  window._efcEntity = null;
  window._efcDepth = 0;
  window._lastRecoveryPhraseId = null;
  window._pendingRepairPrompt = false;
  window._lastRepairSubmittedText = "";
  window._discoveryShownLastTurn  = false;
  window._consecutiveAppQuestions = 0;
  window._lastPersonaReveal = false;
  window._recentlySeenDiscTopics = [];
  window._lastPartnerFrameText = "";
  window._lastSemanticClarifyText = "";
  window._lastBlueQuestions = [];
  window._lastDiscoveryEngineId = "";
  hideDiscoveryPanel();

  window._learnerObs = {
    turns_observed: 0, hint_clicks: 0, word_clicks: 0,
    recovery_uses: 0, successful_answers: 0, asr_rejections: 0,
    mirror_uses: 0, question_count: 0, extended_answer_count: 0,
    recovery_resilience_count: 0, soft_unmatched_count: 0,
  };

  conversationTranscript = [];
  transcriptLineUiState = {};
  transcriptReplayToken += 1;
  // Reset SI event log and session-start timestamp for the new session.
  window._siEventLog = [];
  window._siSessionStart = Date.now();
  transcriptReplayState = { active: false, activeLineId: null, queue: [] };
  transcriptSelectedLineIds = [];
  renderTranscript();

  const frameSentenceEl = document.getElementById("frameSentence");
  if (frameSentenceEl) frameSentenceEl.textContent = "";
  const optC = document.getElementById("optionsContainer");
  if (optC) { optC.innerHTML = ""; optC.style.display = "none"; }
  const challengeZone = document.getElementById("challengeRecoveryZone");
  if (challengeZone) challengeZone.innerHTML = "";

  window._sentenceHint = { pinyin: "", text_en: "" };
  window._activeTurnRecord = null;
  window._currentHintAffordance = { visible: false };
  window._currentTurnUid = null;
  hint_cascade_state = { level: 0, turn_uid: null };
  if (_challenge.active) _resetChallengeHelpState();

  const scoreOverlay = document.getElementById("scorecardOverlay");
  if (scoreOverlay) scoreOverlay.remove();
  const progressSaved = document.getElementById("progressSavedMsg");
  if (progressSaved) progressSaved.remove();

  // Reset the End Session button so it is active for the new session.
  // The button is left disabled + "Saved ✓" after a successful end-session;
  // that state must not leak into a subsequent session.
  const _endBtn = document.getElementById("endSessionBtn");
  if (_endBtn) {
    _endBtn.disabled = false;
    _endBtn.textContent = "End Session";
    _endBtn.title = "End this session and see your scorecard";
  }

  document.body.classList.remove("conversation-active", "session-ended", "mobile-panel-open", "card-sheet-open", "mobile-guide-collapsed");
  _syncMobileBackdrop();
  _updateMobileFabLabel();

  _tracker.total_turns = 0;
  _tracker.recovery_uses = 0;
  _tracker.successful_recoveries = 0;
  _tracker.conversational_recoveries = 0;
  _tracker.successful_conversational_recoveries = 0;
  _tracker.suggestion_clicks = 0;
  _tracker.card_opens = 0;
  _tracker.display_en_clicks = 0;
  _tracker.display_py_clicks = 0;
  _tracker.translation_help_uses = 0;
  _tracker.questions_asked = 0;
  _tracker.depth_responses = 0;
  _tracker.unmatched_responses = 0;
  _tracker.soft_unmatched_responses = 0;
  _tracker._pendingNaturalRecovery = false;
  _tracker.engines_used = new Set();
  _tracker._pendingRecovery = false;
  _tracker.mode = _challenge.active ? "challenge" : "normal";

  renderSessionObjective();
}

/**
 * Clear current conversation memory (persona facts) for the current learner.
 * Does NOT rotate learner_id, does NOT wipe progress history, does NOT delete
 * saved sessions. Only clears per-session conversation facts on the server and
 * resets the current in-flight session state.
 */
async function startFreshLearner() {
  const currentId = window._learnerId;

  // Clear persona facts on the server for the current learner — progress snapshots untouched.
  try {
    if (currentId) {
      await fetch("/api/reset_memory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ learner_id: currentId }),
      });
    }
  } catch (_) {}

  // Reset in-flight session state (tracker, transcript, frame counters).
  // This does NOT touch localStorage["manos_progress_history"].
  _resetCurrentSessionState();

  // Clear within-session place anchor so it cannot re-fill templates after reset.
  window._lastMentionedPlace = null;

  // Clear the "Remembered:" facts banner immediately, then re-fetch from server
  // to confirm the reset actually persisted (catches server-side failures).
  _renderMemoryBanner({});
  await _refreshMemoryBanner();

  // Log what happened — confirm learner_id is preserved, progress untouched.
  console.info(
    "[clearMemory] persona/conversation facts cleared for learner_id=" + (currentId || "(none)") +
    "; learner_id preserved; manos_progress_history NOT touched; server progress snapshots NOT touched."
  );

  // Show a brief status message — do NOT auto-start a turn.
  const statusEl = document.getElementById("statusMsg") || document.createElement("div");
  statusEl.textContent = "Conversation facts cleared — your progress history is kept.";
  statusEl.style.cssText = "color:#0891b2;font-size:0.85rem;padding:6px 14px;";
  if (!document.getElementById("statusMsg")) {
    statusEl.id = "statusMsg";
    document.getElementById("actionLadder")?.prepend(statusEl);
  }
  setTimeout(() => { statusEl.textContent = ""; }, 4000);

  // Refresh the session objective panel — do NOT call _applyFirstTimeBetaHygiene()
  // (that would wipe progress cache); just re-initialise the profile read-only.
  await initBetaProfile();
  renderSessionObjective();
}

/**
 * Run a turn: either "Run Turn" (frame from dropdown) or "Next" (selector-driven next frame).
 * @param {boolean} [isNext=false] When true, send next_question + conversation_state; server chooses frame.
 * @param {{ prefer_bridge?: boolean, force_bridge?: boolean, last_turn_was_answer?: boolean, learner_skip_confusion?: boolean }} [opts] When isNext: prefer_bridge tries bridge first; learner_skip_confusion clears bridge intent after "我不明白" advance.
 */
async function runTurn(isNext = false, opts = {}) {
  _dismissOnboardingGuideIfActive();
  _setConversationActive(true);
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
  _closeExploreWordPanelIfMobile();
  _closeMicroGloss();
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
      // Discovery/blue-panel state — round-tripped so proactive trigger can accumulate
      discovery_shown_last_turn:  window._discoveryShownLastTurn === true,
      consecutive_app_questions:  window._consecutiveAppQuestions || 0,
      last_persona_reveal:        window._lastPersonaReveal === true,
      recently_seen_disc_topics:  Array.isArray(window._recentlySeenDiscTopics) ? window._recentlySeenDiscTopics : [],
      last_partner_frame_text:    window._lastPartnerFrameText || "",
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
        // Diagnostics: mint/detach a trace id for this submission so the server
        // captures raw input, routing text, intent, and response for BOTH the
        // spoken and typed/translated paths (behaviour-free; diag-gated).
        try {
          if (AsrDiag.enabled()) {
            const _sub = window._lastAnswer.submitted_text || window._lastAnswer.selected_option_hanzi || "";
            const _wasMic = !!AsrDiag.id();
            if (!_wasMic) {
              AsrDiag.beginSynthetic({
                input_path: "typed_or_translated",
                user_agent: (typeof navigator !== "undefined" && navigator.userAgent) || "",
              });
            }
            const _tid = AsrDiag.submit({
              submitted_transcript: _sub,
              request_payload_text: _sub,
              input_path: _wasMic ? "microphone" : "typed_or_translated",
            });
            if (_tid) window._diagTurnTraceId = _tid;
          }
        } catch (_) {}
        window._lastAnswer = null; // send once only
      }
    }
    payload = {
      env: "dev",
      turn_uid: "ui_" + Date.now(),
      next_question: true,
      conversation_state
    };
    if (window._diagTurnTraceId) payload.diag_trace_id = window._diagTurnTraceId;
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

  // Diagnostics: join the server-side trace to the client bundle and flush it.
  try {
    if (window._diagTurnTraceId) {
      AsrDiag.complete(window._diagTurnTraceId, data && data.diag);
      window._diagTurnTraceId = null;
    }
  } catch (_) {}

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
    _tracker._pendingRecovery = false;
  }
  // Natural recovery: learner re-attempted after a rejection (not via recovery panel).
  // Credit when the re-attempt was routed to a real frame.
  if (_tracker._pendingNaturalRecovery) {
    if (data.frame_id) {
      _tracker.successful_recoveries++;
      _tracker.successful_conversational_recoveries++;
    }
    _tracker._pendingNaturalRecovery = false;
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
    if (data.state_update.repair_attempt_count !== undefined) {
      const _prevRepair = window._repairAttemptCount || 0;
      window._repairAttemptCount = data.state_update.repair_attempt_count;
      // Turbulence signal: repair loop entered or deepened — informational only.
      if (window._repairAttemptCount >= 2 && window._repairAttemptCount > _prevRepair) {
        _tracker.turbulence_events++;
        _siLogEvent("turbulence_moment", { kind: "repair_loop", frame_id: frameId });
      }
    }
    // Discovery/blue-panel state — must be round-tripped so server accumulates correctly
    if (data.state_update.discovery_shown_last_turn !== undefined)
      window._discoveryShownLastTurn = !!data.state_update.discovery_shown_last_turn;
    if (typeof data.state_update.consecutive_app_questions === "number")
      window._consecutiveAppQuestions = data.state_update.consecutive_app_questions;
    if (data.state_update.last_persona_reveal !== undefined)
      window._lastPersonaReveal = !!data.state_update.last_persona_reveal;
    if (Array.isArray(data.state_update.recently_seen_disc_topics))
      window._recentlySeenDiscTopics = data.state_update.recently_seen_disc_topics;
    if (typeof data.state_update.last_partner_frame_text === "string")
      window._lastPartnerFrameText = data.state_update.last_partner_frame_text;
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

  // Fix 1: Work-context company-question suppression
  // If the server wants to ask a company follow-up but the learner has established an
  // education / retirement context, substitute a more appropriate question.
  if (window._learnerWorkContext && data.frame_text) {
    const _COMPANY_Q_PAT = /你在哪个公司上班|你在哪家公司工作|你在什么公司|哪家公司|什么公司工作/;
    if (_COMPANY_Q_PAT.test(data.frame_text)) {
      data.frame_text = (window._learnerWorkContext === "retired")
        ? "你退休多久了？"
        : "你以前在哪个学校教书？";
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
  // ── Issue 3: Generic filler blocker ──────────────────────────────────────────
  // If the last input was noisy / rejected / strong confusion, suppress well-known
  // generic fillers that the server sometimes uses in low-confidence fallback slots.
  // We check and RESET the flag here so exactly one response is affected per noisy turn.
  const _lastWasNoisyOrConfusion = window._lastTurnWasNoisyOrConfusion === true;
  window._lastTurnWasNoisyOrConfusion = false;
  if (_lastWasNoisyOrConfusion && data.counter_reply) {
    const _crCheck = (data.counter_reply || "").trim();
    const _BLOCKED_FILLERS = ["这样挺好", "这个先不说吧", "我觉得都挺有意思的", "明白了。", "明白了！"];
    if (_BLOCKED_FILLERS.some(f => _crCheck.startsWith(f))) {
      data.counter_reply = "我没听清楚，你可以再说一遍吗？";
    }
  }

  // Fix 4: After strong confusion, append a simplified rephrase of the last app question
  // so the learner hears: "我说得不清楚吗？…" + "我问：{question}" as a concrete anchor.
  // _confusionFrameText is only set in the strong-confusion path (not plain hard-fail),
  // so its presence is the discriminator — hard-fail rejections get no rephrase appended.
  const _confusionFrameQ = (window._confusionFrameText || "").trim();
  window._confusionFrameText = null;  // consume once
  if (_confusionFrameQ && data.counter_reply) {
    const _crExisting = (data.counter_reply || "").trim();
    // Never stack clarification wrappers: if counter_reply already contains a
    // clarification prefix ("我是问：", "我问："), skip the append entirely.
    const _hasClarifyWrapper = /我是问|我问：/.test(_crExisting);
    if (!_hasClarifyWrapper) {
      const _simpleQ = _confusionFrameQ.includes("，")
        ? _confusionFrameQ.split(/[，。！？]/)[0]
        : _confusionFrameQ;
      // Strip any wrapper from the appended text itself (defensive).
      const _cleanQ = _simpleQ.replace(/^(我是问：|我问：|我在问：|我的意思是：|我刚刚问的是：)/, "").trim();
      if (_cleanQ.length >= 3) {
        data.counter_reply = _crExisting + `\n我问：${_cleanQ}`;
      }
    }
  }

  // ── Clarification-wrapper dedup (final pass) ──────────────────────────────────
  // Guarantee: the learner never sees two "我是问：" / "我问：" wrappers in one turn.
  // This catches any remaining path that stacks wrappers (server + confusion-rephrase).
  const _CLARIFY_WRAP_RE = /我是问[：:]/g;
  if (data.counter_reply && (_CLARIFY_WRAP_RE.lastIndex = 0, (data.counter_reply.match(_CLARIFY_WRAP_RE) || []).length > 1)) {
    // Remove all but first occurrence
    let _first = true;
    data.counter_reply = data.counter_reply.replace(/我是问[：:]/g, (m) => {
      if (_first) { _first = false; return m; }
      return "";
    });
  }
  if (data.counter_reply && data.frame_text) {
    const _crHasClarify = /我是问[：:]|我问[：:]/.test(data.counter_reply);
    const _ftHasClarify = /^(我是问[：:]|我问[：:])/.test((data.frame_text || "").trim());
    if (_crHasClarify && _ftHasClarify) {
      // Both have wrappers — strip the wrapper from frame_text
      data.frame_text = (data.frame_text || "").replace(/^(我是问[：:]|我问[：:])\s*/, "").trim();
    }
  }

  // ── Echo prevention ────────────────────────────────────────────────────────────
  // Persona sometimes echoes the learner's own first-person statements as its own.
  // Rewrite "哦，我…" → "哦，你…" when the reply closely mirrors the learner's last input.
  // Also covers desire/travel forms: 哦，我想… / 哦，我很想… / 哦，我就想… / 哦，我要…
  // Preserves genuine persona self-statements that include "也" (agreement marker) or
  // "觉得" (opinion marker) without overlapping the learner's exact content.
  if (data.counter_reply) {
    const _crRaw   = (data.counter_reply || "").trim();
    // Use submitted_text first; fall back to selected_option_hanzi for sentence-card taps
    const _lastSub = (
      window._lastAnswer?.submitted_text ||
      window._lastAnswer?.selected_option_hanzi ||
      ""
    ).trim();
    // Match "哦，我…" at start — catches 我想、我很想、我就想、我要、我喜欢、etc.
    if (/^哦[，,]\s*我/.test(_crRaw) && _lastSub.startsWith("我")) {
      const _crBody  = _crRaw.replace(/^哦[，,]\s*我/, "").replace(/[！。？]$/, "");
      const _subBody = _lastSub.replace(/^我/, "");
      // "也" / "觉得" = genuine persona statement — do not rewrite
      const _isPersonaSelfStatement = _crRaw.includes("也") || _crRaw.startsWith("哦，我觉得");
      if (
        !_isPersonaSelfStatement &&
        _crBody.length >= 2 &&
        _subBody.length >= 3 &&
        (_subBody.includes(_crBody.slice(0, 3)) || _crBody.includes(_subBody.slice(0, 3)))
      ) {
        data.counter_reply = _crRaw
          .replace(/^(哦[，,]\s*)我/, "$1你")
          .replace(/！/, "。");   // soften first exclamation in the echoed segment
      }
    }
  }

  // ── Issue 6: Beginner output cap ──────────────────────────────────────────────
  // Simplify over-long or structurally complex persona answers so beginners see
  // 1–2 short sentences rather than multi-clause elaborations.
  if (data.counter_reply) {
    data.counter_reply = _simplifySentenceForBeginner(data.counter_reply.trim());
  }

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
    _initActiveTurnRecord(
      _counterReply,
      _counterReplyEn,
      _counterReplyPinyin,
      payload.turn_uid || "counter_reply",
    );
    window._lastPartnerTurnText = _counterReply;
  } else {
    // No counter_reply — render the app's next question into the main frame as normal.
    window._lastPartnerTurnText = fallbackText;
    renderFrameSentence({ id: frameId, text: fallbackText });
    _initActiveTurnRecord(
      fallbackText,
      data.frame_text_en ?? "",
      data.frame_pinyin || "",
      frameId,
    );
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
  // Answer-reactive augmentation: probes from learner's latest line and persona's latest line.
  const _learnerForAugment = (
    payload?.conversation_state?.last_answer?.submitted_text
    || payload?.conversation_state?.last_answer?.selected_option_hanzi
    || ""
  ).trim();
  const _partnerForAugment = (
    _counterReply
    || (window._lastPartnerSpokenText || "").trim()
    || (window._lastPartnerTurnText || "").trim()
    || (fallbackText || "").trim()
  );
  const _extraQs = _dedupeQuestions([
    ..._augmentQuestionsFromAnswer(_learnerForAugment),
    ..._augmentQuestionsFromAnswer(_partnerForAugment),
  ], 5);

  // Frame-stage awareness: determine whether the current frame is an early place stage.
  // Use the answered frame (payload last_answer) as primary signal; fall back to frameId.
  const _answeredFrameId = (
    payload?.conversation_state?.last_answer?.frame_id || ""
  );
  const _activeFrameId = _answeredFrameId || frameId || "";
  const _frameFallbackQs = _getFrameFallbackQuestions(_activeFrameId);
  const _earlyPlace      = _isEarlyPlaceFrame(_activeFrameId);

  if (_isUserLed) {
    window._pendingFrameMeta = {
      text: fallbackText.trim(),
      text_en: data.frame_text_en || "",
      pinyin: fillSentenceHintPinyin(fallbackText.trim(), data.frame_pinyin || ""),
      frame_id: frameId,
    };
    // For early place frames, server discovery_questions may be too advanced
    // (e.g. "那里有什么特别的？" arriving on the very first origin/location turn).
    // Filter those out and lead with frame-specific simple questions instead.
    const _advancedPlacePattern = /好吃|特别|为什么喜欢|喜欢那里/;
    const _filteredDq = _earlyPlace
      ? _dq.filter(q => !_advancedPlacePattern.test(q.zh || ""))
      : _dq;
    const _serverQs = _filteredDq.slice(0, 4);
    // Priority: frame-specific (2) → server-discovery (up to 4) → answer-reactive (up to 4).
    // If this is an early place frame, lead with frame questions and cap server at 2.
    const _assembled = _earlyPlace
      ? [..._frameFallbackQs.slice(0, 2), ..._extraQs, ..._serverQs.slice(0, 2)]
      : [..._extraQs, ..._serverQs];
    // For user-led turns (persona revealed content / user asking questions), allow up to 5
    // questions so rich reveals surface multiple relevant exploration options.
    // Relevance ranking (server-side) ensures only strong matches appear.
    const _hasRichReply = _extraQs.length >= 3 || _serverQs.length >= 3;
    renderDiscoveryPanel(_dedupeQuestions(_assembled, _hasRichReply ? 5 : 3), fallbackText);
  } else {
    // Non-user-led turn: the server didn't send new blue questions this time.
    // Keep the last useful question set visible so the learner can still ask.
    // Only hide if we have never shown any questions (empty cache).
    window._pendingFrameText = null;
    window._pendingFrameMeta = null;
    const _cached = window._lastBlueQuestions || [];

    // Engine staleness: if the engine has changed since the last blue panel was shown,
    // stale cached questions from the old engine are irrelevant — prefer topic fallback.
    const _currentEng   = (window._currentEngineId || engineId || "").toLowerCase();
    const _cachedEng    = (window._lastDiscoveryEngineId || "").toLowerCase();
    const _engineChanged = _cachedEng && _cachedEng !== _currentEng;

    const _topicFallback = _getTopicFallbackQuestions(_currentEng);

    if (_frameFallbackQs.length > 0) {
      // Frame-specific questions take priority — directly relevant to the active question.
      const _supplement = (!_engineChanged && _cached.length > 0)
        ? _cached.filter(q => !_isEarlyPlaceFrame(_activeFrameId) ||
            !(/好吃|特别|为什么喜欢|喜欢那里/).test(q.zh || ""))
        : [];
      renderDiscoveryPanel(
        _dedupeQuestions([..._frameFallbackQs, ..._extraQs, ..._supplement]),
        null
      );
    } else if (!_engineChanged && _cached.length > 0) {
      // Same engine: cached questions are still relevant.
      renderDiscoveryPanel(_dedupeQuestions([..._extraQs, ..._cached]), null);
    } else {
      // Engine changed or no cache — use topic-based fallback for the current engine.
      if (_topicFallback.length > 0) {
        renderDiscoveryPanel(_dedupeQuestions([..._extraQs, ..._topicFallback]), null);
      } else if (_extraQs.length > 0) {
        renderDiscoveryPanel(_extraQs, null);
      } else {
        hideDiscoveryPanel();
      }
    }
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

  // If server returned a card_id, open the card panel (desktop side panel only)
  if (data.card_id && _shouldAlsoOpenCardPanel()) {
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
  await initBetaProfile();
  if (window._isFirstTimeBetaUser) {
    _applyFirstTimeBetaHygiene();
  } else {
    _refreshMemoryBanner();
  }

  // Show onboarding guide or "Today's focus" in the scorecard panel before any session begins.
  renderSessionObjective();
  initRightPanelTabs();
  initMobileLayout();

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
  if (frameSelect) {
    frameSelect.addEventListener("change", () => {
      _dismissOnboardingGuideIfActive();
    });
  }
  // Phase 7.4: Speak-first — Web Speech API; on mobile use touchstart (iOS gesture chain).
  const LISTEN_BEFORE_RECOVERY_MS = 7000;
  let _micListenInFlight = false;
  let _micLastTouchListenAt = 0;

  async function _runChineseMicListen(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (_micListenInFlight) return;
    _micListenInFlight = true;
    window._micListenArmedAt = Date.now();
    _closeMicroGloss();
    _closeExploreWordPanelIfMobile();
    ttsUnlock();
    const btn = document.getElementById("tryRespondingBtn");
    const frameId = window._lastPartnerFrameId || null;
    const optionsFromFrame = frameId && window._frameOptionsRuntime?.frames?.[frameId]?.options;
    const options = (window._tapOptions && window._tapOptions.length > 0)
      ? window._tapOptions
      : (Array.isArray(optionsFromFrame) ? optionsFromFrame : []);
    if (btn) btn.textContent = "Listening…";
    try {
    if (options.length === 0) {
      emitUITrace({ type: "SPEECH_LISTEN_OPTIONS", timestamp: new Date().toISOString(), payload: { frame_id: frameId, option_count: 0, warning: "No options to match against; use Run Turn first or check frame_options" } });
    } else {
      emitUITrace({ type: "SPEECH_LISTEN_OPTIONS", timestamp: new Date().toISOString(), payload: { frame_id: frameId, option_count: options.length } });
    }
    const { transcript, matchedOption, asr_confidence, finishReason } = await listenForResponse(options, LISTEN_BEFORE_RECOVERY_MS);
    emitUITrace({
      type: "SPEECH_RESULT",
      timestamp: new Date().toISOString(),
      payload: {
        transcript: transcript || "",
        transcript_length: (transcript || "").length,
        matched: !!matchedOption,
        asr_confidence: asr_confidence != null ? asr_confidence : null,
        finish_reason: finishReason || null,
      },
    });
    const saidTrimmed = (transcript && typeof transcript === "string") ? transcript.trim() : "";
    // Empty mic session: stay in RESPOND — do not fire partner recovery or increment repair count.
    if (!saidTrimmed) {
      const _isActionableError = finishReason === "insecure_origin" || finishReason === "permission_denied"
        || finishReason === "start_error" || (finishReason === "onend" && !window._lastMicStarted);
      const _noSpeechMsg = finishReason === "insecure_origin"
        ? "Mic needs HTTPS — open this app via https:// or use Safari on this device."
        : finishReason === "permission_denied"
          ? "Microphone access denied — allow mic in browser settings"
          : finishReason === "start_error"
            ? "Mic could not start — check browser mic permission"
            : finishReason === "error"
              ? "Speech recognition error — try again"
              : (finishReason === "onend" && !window._lastMicStarted)
                ? "Microphone did not open — check browser mic permission"
                : "No speech heard — tap the mic and try again";
      _showListenNotice(_noSpeechMsg, _isActionableError ? 6000 : 3500);
      emitUITrace({
        type: "SPEECH_EMPTY_NO_RECOVERY",
        timestamp: new Date().toISOString(),
        payload: { frame_id: frameId, finish_reason: finishReason || "unknown" },
      });
      // Diagnostics: flush the (no-speech) mic cycle record — no submission occurs.
      try {
        if (AsrDiag.id()) {
          const _tid = AsrDiag.submit({ input_path: "microphone", submitted_transcript: "", empty: true, finish_reason: finishReason || "unknown" });
          if (_tid) AsrDiag.complete(_tid, null);
        }
      } catch (_) {}
      setUiMode("RESPOND");
      return;
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
      if (matchedOption.card_id && matchedOption.kind !== "FRAME_WITH_SLOTS" && _shouldAlsoOpenCardPanel()) {
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
        // Priority gate: any 你…吗 question or short spoken question ending in 呢/啊
        || (/你/.test(_spokenRaw) && /吗[？?]?$/.test(_spokenRaw))
        || (_isUserDirectedQuestion(_spokenRaw))
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

    // Spoken recovery intercept: if the learner speaks a recovery phrase (再说一遍, 慢一点说,
    // 我不明白, 什么意思 etc.), simulate the same action as a recovery panel tap — before the
    // normal accept/reject ASR path — so it never falls through to the rejected-speech partner
    // repair prompt (which feels like "generic uncertainty" instead of repeating the question).
    const _spokenRecoveryPhrase = matchTranscriptToLearnerPhrase(
        saidTrimmed,
        learnerRecoveryPhrases(recoveryPhrasesRuntime || window._recoveryPhrases)
    );
    if (_spokenRecoveryPhrase) {
        const _srpAction = getRecoveryAction(_spokenRecoveryPhrase);
        if (_srpAction === "repeat" || _srpAction === "slower" || _srpAction === "meaning") {
            addTranscriptEntry("user", saidTrimmed, { text_en: _spokenRecoveryPhrase.meaning || "" });
            renderTranscript();
            _tracker.recovery_uses++;
            _siLogEvent("recovery_use", { frame_id: frameId, kind: (_spokenRecoveryPhrase.id || "spoken_recovery") });
            if (_challenge.active) {
                _challenge.recoveryCount++;
                _challenge.helpLevel = Math.max(_challenge.helpLevel, _srpAction === "slower" ? 2 : 1);
                if (_challenge.recoveryCount >= 2) _challengeRevealText();
            }
            const _srpQ = (window._lastPartnerSpokenText || window._currentFrameText || "").trim();
            const _srpLine = _srpAction === "slower"
                ? (_srpQ ? "好的，慢一点：" + _srpQ : "好的，慢一点。")
                : (_srpQ || "好。");
            addTranscriptEntry("partner", _srpLine, transcriptExtrasForRecoveryPartnerRepeat(_srpAction));
            renderTranscript();
            setActivePartnerStatement(_srpLine, "recovery_repeat",
                (_srpQ || "").split("").map((c) => ({ t: c })));
            ttsSpeak({
                text: saidTrimmed, lang: "zh-CN",
                onEvent: (e) => {
                    if (e?.payload?.completed)
                        ttsSpeak({ text: _srpLine, lang: "zh-CN",
                            rate: _srpAction === "slower" ? 0.82 : undefined, queue: true });
                },
            });
            lastClickedWordId = null;
            window.lastClickedWordId = null;
            setUiMode("READ");
            return;
        }
        // next_turn phrases (好吧 / 换个话题): fall through to normal runTurn flow
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
      window._lastSemanticClarifyText = "";  // stale paraphrase context cleared on real answer
      emitUITrace({
        type: "SPEECH_ACCEPTED_AS_ANSWER",
        timestamp: new Date().toISOString(),
        payload: { transcript: saidTrimmed, matched: false, unmatched_decision_reason: unmatchedDecision.reason, frame_id: frameId }
      });
      window._lastAcceptedFreeTranscript = saidTrimmed;
      window._lastAcceptedFreeTranscriptAt = Date.now();
      window._lastAcceptedFreeFrameId = frameId || "";
      // Learner skip signal ("我不懂"): advance without saving as scored answer.
      // Sub-case: STRONG confusion ("听不懂", "一点听不懂") — escalate repair count and
      // submit as a proper answer so the server can generate an empathetic clarification
      // ("我说得太快了吗？") rather than silently skipping to the next topic.
      if (unmatchedDecision.reason === "learner_skip_signal") {
        addTranscriptEntry("user", saidTrimmed);
        renderTranscript();
        lastClickedWordId = null;
        window.lastClickedWordId = null;
        setUiMode("READ");
        if (_isStrongConfusionText(saidTrimmed)) {
          window._recentConfusionCount = Math.max((window._recentConfusionCount || 0) + 1, 1);
          window._lastTurnWasNoisyOrConfusion = true;
          // Turbulence signal: explicit strong confusion — informational only.
          _tracker.turbulence_events++;
          _siLogEvent("turbulence_moment", { kind: "confusion_signal", frame_id: frameId });
          // Save the current app question so _runTurnInner can append a simplified rephrase.
          window._confusionFrameText = (window._currentFrameText || "").trim();
          // Submit only the bare confusion signal so the server focuses on clarification
          // and doesn't latch onto any semantic content (food, travel, etc.) that may
          // appear in the same noisy utterance after the confusion phrase.
          window._lastAnswer = { frame_id: frameId, submitted_text: "我听不懂" };
          runTurn(true, { last_turn_was_answer: true });
        } else {
          runTurn(true, { learner_skip_confusion: true });
        }
        return;
      }
      // Normalise turn-around phrases: ensure trailing "？" so the server reliably
      // detects them as counter-questions (ASR often strips punctuation).
      const _isTurnAround = /^(那?你呢|你怎么想|为什么这么问|为什么这样问|换我问|那你|你来问)/.test(saidTrimmed)
        || saidTrimmed === "你呢"
        || /[，。！]?(那?你呢|你怎么想|为什么这么问)[？?]?$/.test(saidTrimmed)
        || /你(是哪里人|从哪里来|老家在哪|住(在哪|哪里|的地方)|做什么工作|的工作|是做什么|喜欢(什么|做什么)|有什么爱好|有家人|有没有家人)/.test(saidTrimmed)
        // Priority gate: any 你…吗 and broader spoken question forms
        || (/你/.test(saidTrimmed) && /吗[？?]?$/.test(saidTrimmed))
        || _isUserDirectedQuestion(saidTrimmed);
      // Priority gate: clear confusion state before submitting a user question so the server
      // does not mistake it for a repair signal and return "我是问：…" clarification.
      if (_isTurnAround) {
        window._recentConfusionCount = 0;
        window._consecutiveNotUnderstood = 0;
        window._lastRepairKind   = null;
        window._prevRepairKind   = null;
        window._lastTurnWasNoisyOrConfusion = false;
      }
      // Ensure trailing "？" so server _is_user_question reliably fires
      const submittedForServer = _isTurnAround && !/[？?]$/.test(saidTrimmed) ? saidTrimmed + "？" : saidTrimmed;
      _trackUserTextSignals(saidTrimmed);
      // Track the most recently mentioned place for vague-reference anchoring in partner text.
      // e.g. "甘肃" → later frame "那儿生活" becomes "甘肃那边生活".
      const _PLACE_ANCHOR_LIST = ['甘肃', '中国', '美国', '英国', '法国', '日本', '韩国', '新西兰', '台湾', '香港', '澳大利亚', '北京', '上海', '广州', '成都', '欧洲', '泰国', '新加坡', '越南', '意大利', '西班牙', '德国', '加拿大'];
      const _newAnchorPlace = _PLACE_ANCHOR_LIST.find(p => saidTrimmed.includes(p));
      if (_newAnchorPlace) window._lastMentionedPlace = _newAnchorPlace;
      _updateLearnerWorkContext(saidTrimmed);  // track education/retirement for company-Q guard
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
    // Route to hard-fail or soft-fail counter based on Chinese signal strength.
    if ((unmatchedDecision.fail_level || "hard") === "soft") {
      _tracker.soft_unmatched_responses++;
      window._learnerObs.soft_unmatched_count++;
      _tracker.turbulence_events++;
      _siLogEvent("turbulence_moment", { kind: "asr_soft_reject", frame_id: frameId });
    } else {
      _tracker.unmatched_responses++;
      _tracker.turbulence_events++;
      _siLogEvent("turbulence_moment", { kind: "asr_hard_reject", frame_id: frameId });
    }
    window._learnerObs.asr_rejections++;        // Phase L1 observation (all rejections, regardless of level)
    window._lastTurnWasNoisyOrConfusion = true; // filler-blocker: suppress generic filler on next server response
    _updateLearnerWorkContext(saidTrimmed);      // noisy input may still reveal work context
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

    // Semantic clarification override: try partial-confirmation first (most specific),
    // then category-level clarification, then generic repair (啊？).
    // This applies from the very first rejection so "啊？" only fires when there is
    // genuinely no detectable signal.
    const _semCategory    = _detectSemanticCategory(saidTrimmed, window._currentEngineId || "");
    // Context-anchored confusion recovery: if the learner echoes back our location probe
    // ("哪里什么") AND our immediately previous turn was itself a 哪里？ clarification,
    // rephrase with their previous answer as context so the intent is unambiguous.
    // e.g. "我是问：你说「这里羊肉牛肉都很好吃」，是在哪里？"
    const _prevWasWherePrompt = /哪里[?？]/.test(window._lastPartnerTurnText || "");
    const _isEchoConfusion    = /^(哪里|哪儿)/.test(saidTrimmed.trim()) && /什么|不懂|不明白/.test(saidTrimmed);
    // Skip partial-confirmation for well-formed short sentences — they should get a
    // normal acknowledgement, not an echo-back that feels robotic for clean input.
    const _partialConf = _isLikelyCleanSentence(saidTrimmed)
      ? null
      : _buildPartialConfirmation(saidTrimmed);
    const _semClarifyData = (_prevWasWherePrompt && _isEchoConfusion)
      ? _buildWhereRestatement(window._lastAcceptedFreeTranscript)
      : (_partialConf || (_semCategory ? _getSemanticClarification(_semCategory) : null));
    let _displayPhrase  = _semClarifyData
      ? Object.assign({}, phrase, {
          hanzi:           _semClarifyData.hanzi,
          pinyin:          _semClarifyData.pinyin,
          text_en:         _semClarifyData.text_en,
          recovery_action: "soft",   // stay in RESPOND; do not auto-advance turn
          id:              "sem_clarify_" + (_partialConf ? "partial" : _semCategory),
        })
      : phrase;

    // Track the last semantic clarification shown so semanticSoftMatch can route
    // a subsequent "对/是的" plain affirmation to the server as a confirmed answer.
    window._lastSemanticClarifyText = _semClarifyData ? (_semClarifyData.hanzi || "") : "";
    // Also update _lastPartnerFrameText so the server's _confirmed_re_ask logic fires
    // when the client-generated paraphrase is confirmed with a plain affirmation.
    if (_semClarifyData) window._lastPartnerFrameText = _semClarifyData.hanzi;

    // After 2+ consecutive failures with no semantic signal and no clarification available:
    // use the current frame question as a soft re-ask so the learner hears a concrete,
    // topic-preserving anchor — never prescribe answer templates (Design Constitution).
    const _escalationSemanticSignal =
      _detectSemanticCategory(saidTrimmed, window._currentEngineId || "") !== null ||
      (typeof semanticSoftMatch === "function" && semanticSoftMatch(saidTrimmed, frameId));
    if ((window._consecutiveNotUnderstood || 0) >= 2 && !_escalationSemanticSignal && !_semClarifyData) {
      // Prefer the current pending question as a topic anchor; fall back to generic soothing.
      const _pendingQ = (window._currentFrameText || "").trim()
        .replace(/^(没关系[，。]?|我是问：|我没听清楚[，。]?)\s*/u, "")
        .replace(/[。！,，\s]+$/u, "");
      const _reaskHanzi = (_pendingQ.length >= 3 && _pendingQ.length <= 25)
        ? `没关系。${_pendingQ}？`
        : "没关系，你能再说一遍吗？";
      _displayPhrase = Object.assign({}, _displayPhrase, {
        hanzi:           _reaskHanzi,
        pinyin:          "",
        text_en:         "No problem, let me ask again.",
        recovery_action: "soft",
        id:              "contextual_reask",
      });
    }

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
      // Same-topic repair hold: if the rejected speech had detectable semantic content
      // (location, family, work, food, …) stay in the same engine rather than bridging.
      // Only bridge when the input was pure noise with no recoverable signal.
      const _hasSemanticSignal = _detectSemanticCategory(saidTrimmed) !== null
        || semanticSoftMatch(saidTrimmed, frameId);
      ttsSpeak({
        text: _displayPhrase.hanzi,
        lang: "zh-CN",
        onEvent: (e) => {
          if (e?.payload?.completed) {
            runTurn(true, _hasSemanticSignal ? {} : { prefer_bridge: true });
          }
        },
      });
    } else {
      ttsSpeak({ text: _displayPhrase.hanzi, lang: "zh-CN" });
      setUiMode("RESPOND");
    }
    } finally {
      if (btn) {
        btn.textContent = "\uD83C\uDFA4";
        btn.title = "Speak your answer";
      }
      const st = document.getElementById("listenStatus")?.dataset?.state;
      if (st !== "notice") _setListenState("idle");
      _micListenInFlight = false;
    }
  }

  const tryRespondingBtnEl = document.getElementById("tryRespondingBtn");
  if (tryRespondingBtnEl) {
    tryRespondingBtnEl.addEventListener("touchstart", (e) => {
      e.stopPropagation();
      window._micListenArmedAt = Date.now();
      if (_isMobileLayout()) {
        e.preventDefault();
        _micLastTouchListenAt = Date.now();
        _runChineseMicListen(e);
      }
    }, { passive: false });
    tryRespondingBtnEl.addEventListener("click", (e) => {
      if (_isMobileLayout() && Date.now() - _micLastTouchListenAt < 600) return;
      _runChineseMicListen(e);
    });
  }
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

runBtn.addEventListener("click", () => {
  ttsUnlock();
  _resetCurrentSessionState();
  runTurn(false);
});
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
  // Turbulence signal: challenge text had to be revealed — informational only, not used for promotion/demotion.
  _tracker.turbulence_events++;
  _siLogEvent("turbulence_moment", { kind: "challenge_text_revealed", frame_id: window._lastPartnerFrameId || undefined });
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

const practiceLevelBtn = document.getElementById("practiceLevelBtn");
if (practiceLevelBtn) {
  practiceLevelBtn.addEventListener("click", () => _showLevelGateOverlay(true));
}

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
    if (!isVisible) _scrollOptionsIntoViewIfDesktop(sentenceContainer);
    return;
  }
  if (hasLegacy && legacyContainer) {
    const isVisible = legacyContainer.style.display !== "none";
    legacyContainer.style.display = isVisible ? "none" : "flex";
    setUiMode("RESPOND");
    if (!isVisible) _scrollOptionsIntoViewIfDesktop(legacyContainer);
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
function _buildAbilitySummary(metrics) {
  const obs = window._learnerObs || {};
  const cap = (metrics && metrics.conversation_capability) || {};

  // ── Map to spec signal variables ──────────────────────────────────────────
  const turnCount     = _tracker.total_turns           || 0;
  const answerCount   = obs.successful_answers         || 0;
  const questionCount = (obs.question_count || 0) + (obs.mirror_uses || 0);
  const recoveryCount = _tracker.recovery_uses         || 0;
  const resilCount    = obs.recovery_resilience_count  || 0;
  const hintCount     = obs.hint_clicks                || 0;
  const acceptedCount = obs.successful_answers         || 0;
  const extendedCount = obs.extended_answer_count      || 0;
  const unmatchedHard = _tracker.unmatched_responses   || 0;
  const questionsTracked = _tracker.questions_asked    || 0;
  const strongInitiative = !!cap.strong_initiative;

  // ── 1. Headline — product-aligned when session shows sustained dialogue ───
  let headline = cap.headline || null;
  if (!headline) {
    if (resilCount >= 2 && turnCount >= 4) {
      headline = `You kept the conversation going — ${turnCount} turn${turnCount === 1 ? "" : "s"} and worked through misunderstandings naturally.`;
    } else if (turnCount >= 6) {
      headline = `You completed ${turnCount} turns in Chinese.`;
    } else if (turnCount > 0) {
      headline = `You completed ${turnCount} turn${turnCount === 1 ? "" : "s"} — good start.`;
    } else {
      headline = "You started a conversation — that's the first step.";
    }
  }

  // ── 2. "What you can do now" — capability interpretation first ───────────
  const capability_lines = [];
  const _capFromServer = Array.isArray(cap.capability_lines) ? cap.capability_lines : [];
  _capFromServer.forEach((line) => {
    if (line && !capability_lines.includes(line)) capability_lines.push(line);
  });
  const _serverCapRich = _capFromServer.length >= 2;

  if (answerCount > 0 && !strongInitiative && !_serverCapRich)
    capability_lines.push(`You responded ${answerCount} time${answerCount === 1 ? "" : "s"}.`);

  const qDisplay = Math.max(questionCount, questionsTracked);
  if (
    qDisplay > 0
    && !strongInitiative
    && !_serverCapRich
    && !capability_lines.some((l) => l.includes("question") || l.includes("curiosity"))
  ) {
    capability_lines.push(`You asked ${qDisplay} question${qDisplay === 1 ? "" : "s"} back.`);
  }

  if (
    !strongInitiative
    && !_serverCapRich
    && !(Array.isArray(cap.progress_lines) && cap.progress_lines.some(
      (l) => l && (l.includes("difficult") || l.includes("unclear")),
    ))
  ) {
    if (resilCount >= 2) {
      capability_lines.push("You worked through misunderstandings and kept going.");
    } else if (resilCount === 1) {
      capability_lines.push("You kept going after a misunderstanding.");
    } else if (recoveryCount > 0) {
      capability_lines.push(`You kept going after not understanding ${recoveryCount} time${recoveryCount === 1 ? "" : "s"}.`);
    }
  }

  if (extendedCount >= 2 && !strongInitiative && !_serverCapRich) {
    capability_lines.push("You gave more detailed answers as the conversation continued.");
  } else if (extendedCount === 1 && !strongInitiative && !_serverCapRich) {
    capability_lines.push("You started adding more detail to your answers.");
  }

  // Hints: keep as a metric, but do not dominate when initiative was strong.
  if (!strongInitiative) {
    if (hintCount === 0 && answerCount > 0) {
      capability_lines.push("You answered without using hints.");
    } else if (hintCount > 0) {
      capability_lines.push(`You used hints ${hintCount} time${hintCount === 1 ? "" : "s"} to support your answers.`);
    }
  }

  // ── 3. "Recent progress" — evidence-bound lines only ─────────────────────
  const progress_lines = [];
  const _progFromServer = Array.isArray(cap.progress_lines) ? cap.progress_lines : [];
  _progFromServer.forEach((line) => {
    if (line && !progress_lines.includes(line)) progress_lines.push(line);
  });

  if (
    recoveryCount > 0
    && !progress_lines.some((l) => l.includes("difficult") || l.includes("communicating"))
  ) {
    progress_lines.push("You recovered after confusion instead of stopping.");
  }
  if (acceptedCount >= 2 && !strongInitiative)
    progress_lines.push(`You completed ${acceptedCount} accepted response turn${acceptedCount === 1 ? "" : "s"}.`);
  if (qDisplay > 0 && answerCount > 0 && !progress_lines.some((l) => l.includes("asked")))
    progress_lines.push("You both answered and asked questions.");
  if (hintCount === 0 && turnCount >= 3 && !strongInitiative)
    progress_lines.push("You completed this conversation without hints.");
  if (unmatchedHard > 0 && turnCount >= 20 && unmatchedHard <= 5
      && !progress_lines.some((l) => l.includes("unclear")))
    progress_lines.push("A few unclear turns did not stop the conversation.");

  // ── 4. "Next step" — single practical suggestion ─────────────────────────
  let nextStep;
  if (questionCount === 0) {
    nextStep = "Next time, try asking one question back, like \u201c\u4f60\u5462\uff1f\u201d";  // 你呢？
  } else if (recoveryCount > 0) {
    nextStep = "Next time, try one turn again after the recovery phrase.";
  } else if (answerCount > 0) {
    nextStep = "Next time, try making one answer slightly longer.";
  } else {
    nextStep = "Next time, complete one more turn.";
  }
  const next_steps = [nextStep];

  // ── 5. Global fallback ────────────────────────────────────────────────────
  if (capability_lines.length === 0 && progress_lines.length === 0) {
    capability_lines.push(
      `You completed ${turnCount} turn${turnCount === 1 ? "" : "s"} — keep going.`
    );
  }

  const summary = {
    headline,
    capability_lines,
    progress_lines,
    next_steps,
    internal_state: {
      turn_count:     turnCount,
      answer_count:   answerCount,
      question_count: questionCount,
      recovery_count: recoveryCount,
      hint_count:     hintCount,
      extended_count: extendedCount,
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
    _scrollOptionsIntoViewIfDesktop(soc);
  }
}
// Expose on window so browser console validation and test scripts can call it directly.
// app.js is an ES module — module-scope functions are not automatically on window.
window._showPostCloseMirrorOptions = _showPostCloseMirrorOptions;

// ── Frame-stage blue-question fallback ───────────────────────────────────────
/** Per-frame questions shown during early stages of a topic before the persona has
 *  revealed their own details.  These win over broad topic fallbacks and over
 *  advanced server discovery questions that arrive too early (e.g. "那里有什么好吃的？"
 *  during the very first place frame).
 *  Keys must match server frame_id strings. */
const _FRAME_FALLBACK_QUESTIONS = {
  // ── Identity / name ──────────────────────────────────────────────────────
  f_ask_you_name: [
    { zh: "你叫什么名字？",         py: "nǐ jiào shénme míngzi?",                en: "What is your name?",              topic: "name_what" },
    { zh: "你的名字是什么意思？",   py: "nǐ de míngzi shì shénme yìsi?",         en: "What does your name mean?",       topic: "name_meaning" },
    { zh: "谁给你取的名字？",       py: "shéi gěi nǐ qǔ de míngzi?",             en: "Who gave you your name?",         topic: "name_giver" },
  ],
  // ── Place / origin ───────────────────────────────────────────────────────
  f_from_where: [
    { zh: "你呢？你是哪里人？",     py: "nǐ ne? nǐ shì nǎlǐ rén?",             en: "How about you — where are you from?", topic: "place_from" },
    { zh: "你来自哪里？",           py: "nǐ láizì nǎlǐ?",                        en: "Where do you come from?",         topic: "place_from" },
    { zh: "你现在住哪里？",         py: "nǐ xiànzài zhù nǎlǐ?",                  en: "Where do you live now?",          topic: "place_live_now" },
    { zh: "你老家在哪里？",         py: "nǐ lǎojiā zài nǎlǐ?",                   en: "Where is your hometown?",         topic: "place_hometown" },
  ],
  // normalised canonical id for f_live_where (server uses frame.location.live_question)
  "frame.location.live_question": [
    { zh: "你呢？你住哪里？",       py: "nǐ ne? nǐ zhù nǎlǐ?",                  en: "How about you — where do you live?", topic: "place_live_now" },
    { zh: "你住在哪里？",           py: "nǐ zhù zài nǎlǐ?",                      en: "Where do you live?",              topic: "place_live_now" },
    { zh: "那里远吗？",             py: "nàlǐ yuǎn ma?",                          en: "Is it far?",                      topic: "place_far_or_not" },
    { zh: "你住在城市还是农村？",   py: "nǐ zhù zài chéngshì háishi nóngcūn?",   en: "City or countryside?",            topic: "place_special" },
  ],
  f_live_where: [
    { zh: "你呢？你住哪里？",       py: "nǐ ne? nǐ zhù nǎlǐ?",                  en: "How about you — where do you live?", topic: "place_live_now" },
    { zh: "你住在哪里？",           py: "nǐ zhù zài nǎlǐ?",                      en: "Where do you live?",              topic: "place_live_now" },
    { zh: "那里远吗？",             py: "nàlǐ yuǎn ma?",                          en: "Is it far?",                      topic: "place_far_or_not" },
    { zh: "你住在城市还是农村？",   py: "nǐ zhù zài chéngshì háishi nóngcūn?",   en: "City or countryside?",            topic: "place_special" },
  ],
  // Distance / far
  p2_pl_far: [
    { zh: "离那儿远吗？",           py: "lí nàr yuǎn ma?",                        en: "Is it far from there?",           topic: "place_far_or_not" },
    { zh: "一般怎么去？",           py: "yìbān zěnme qù?",                        en: "How do you usually get there?",   topic: "place_distance_transport" },
    { zh: "从你那儿到那边要多久？", py: "cóng nǐ nàr dào nàbiān yào duō jiǔ?",  en: "How long does it take?",          topic: "place_distance_time" },
  ],
  // ── Work ─────────────────────────────────────────────────────────────────
  f_what_work: [
    { zh: "你呢？你做什么工作？",   py: "nǐ ne? nǐ zuò shénme gōngzuò?",        en: "How about you — what do you do?", topic: "work_what" },
    { zh: "你喜欢你的工作吗？",     py: "nǐ xǐhuān nǐ de gōngzuò ma?",           en: "Do you like your work?",          topic: "work_like" },
    { zh: "你做这份工作多久了？",   py: "nǐ zuò zhèfèn gōngzuò duōjiǔ le?",     en: "How long have you been doing this?", topic: "work_duration" },
  ],
  f_like_work: [
    { zh: "你为什么喜欢这份工作？", py: "nǐ wèishénme xǐhuān zhèfèn gōngzuò?",  en: "Why do you like this work?",      topic: "work_like" },
    { zh: "工作中最有趣的是什么？", py: "gōngzuò zhōng zuì yǒuqù de shì shénme?", en: "What's most interesting about your work?", topic: "work_like" },
    { zh: "你做这份工作多久了？",   py: "nǐ zuò zhèfèn gōngzuò duōjiǔ le?",     en: "How long have you done this?",    topic: "work_duration" },
  ],
  // ── Family ───────────────────────────────────────────────────────────────
  f_married: [
    { zh: "你结婚了吗？",           py: "nǐ jiéhūn le ma?",                       en: "Are you married?",                topic: "family_marital" },
    { zh: "你有孩子吗？",           py: "nǐ yǒu háizi ma?",                       en: "Do you have children?",           topic: "family_children" },
    { zh: "你家里有几个人？",       py: "nǐ jiālǐ yǒu jǐ gè rén?",               en: "How many people are in your family?", topic: "family_parents" },
  ],
  f_have_children: [
    { zh: "你有孩子吗？",           py: "nǐ yǒu háizi ma?",                       en: "Do you have children?",           topic: "family_children" },
    { zh: "你家里有几个人？",       py: "nǐ jiālǐ yǒu jǐ gè rén?",               en: "How many in your family?",        topic: "family_parents" },
    { zh: "你有兄弟姐妹吗？",       py: "nǐ yǒu xiōngdì jiěmèi ma?",              en: "Do you have siblings?",           topic: "family_parents" },
  ],
  f_live_with_who: [
    { zh: "你和谁一起住？",         py: "nǐ hé shéi yīqǐ zhù?",                  en: "Who do you live with?",           topic: "family_live_with" },
    { zh: "你家里有几个人？",       py: "nǐ jiālǐ yǒu jǐ gè rén?",               en: "How many people in your family?", topic: "family_parents" },
    { zh: "你跟父母住在一起吗？",   py: "nǐ gēn fùmǔ zhù zài yīqǐ ma?",          en: "Do you live with your parents?",  topic: "family_live_with" },
  ],
  // ── Food ─────────────────────────────────────────────────────────────────
  f_place_food: [
    { zh: "你最喜欢吃什么？",       py: "nǐ zuì xǐhuān chī shénme?",              en: "What do you like eating most?",   topic: "food_fav" },
    { zh: "你喜欢吃辣吗？",         py: "nǐ xǐhuān chī là ma?",                   en: "Do you like spicy food?",         topic: "food_spicy" },
    { zh: "你会自己做吗？",         py: "nǐ huì zìjǐ zuò ma?",                    en: "Can you cook that yourself?",     topic: "food_fav" },
  ],
  // ── Place depth ──────────────────────────────────────────────────────────
  f_place_special: [
    { zh: "那里有什么特别的？",     py: "nàlǐ yǒu shénme tèbié de?",              en: "What's special about that place?", topic: "place_special" },
    { zh: "你为什么喜欢那里？",     py: "nǐ wèishénme xǐhuān nàlǐ?",             en: "Why do you like it there?",       topic: "place_like" },
    { zh: "那里有什么好吃的？",     py: "nàlǐ yǒu shénme hǎochī de?",             en: "What's good to eat there?",       topic: "food_local" },
  ],
  f_place_like_there: [
    { zh: "你喜欢那里吗？",         py: "nǐ xǐhuān nàlǐ ma?",                     en: "Do you like it there?",           topic: "place_like" },
    { zh: "那里有什么特别的？",     py: "nàlǐ yǒu shénme tèbié de?",              en: "What's special about that place?", topic: "place_special" },
    { zh: "你为什么喜欢那里？",     py: "nǐ wèishénme xǐhuān nàlǐ?",             en: "Why do you like it there?",       topic: "place_like" },
  ],
};

/** Intermediate place-depth questions: shown after persona has named a city/region
 *  but before the learner has asked about specifics.  Less advanced than the full
 *  topic fallback ("那里有什么好吃的？" etc.). */
const _PLACE_DEPTH_EARLY_QUESTIONS = [
  { zh: "那是哪里？",               py: "nà shì nǎlǐ?",                          en: "Where is that?",              topic: "place_from" },
  { zh: "那里远吗？",               py: "nàlǐ yuǎn ma?",                          en: "Is it far from here?",        topic: "place_far_or_not" },
  { zh: "那里大吗？",               py: "nàlǐ dà ma?",                            en: "Is it a big place?",          topic: "place_special" },
  { zh: "那里好吗？",               py: "nàlǐ hǎo ma?",                           en: "Is it nice there?",           topic: "place_like" },
];

/** Return frame-stage fallback questions for `frameId`, or [] if not an early-stage frame. */
function _getFrameFallbackQuestions(frameId) {
  return _FRAME_FALLBACK_QUESTIONS[frameId || ""] || [];
}

/** Return true when `frameId` is an early-stage place frame where advanced place-depth
 *  questions (food / why-like / what's-special) would be premature. */
function _isEarlyPlaceFrame(frameId) {
  return !!(frameId && (
    frameId === "f_from_where" ||
    frameId === "f_live_where" ||
    frameId === "frame.location.live_question"
  ));
}

// ── Topic-based blue-question fallback ────────────────────────────────────────
/** Minimum useful blue questions per broad topic.  Served when the server doesn't
 *  send discovery_questions and the client cache is empty.  Server-provided questions
 *  always take priority (cache is populated before this path is reached). */
const _TOPIC_FALLBACK_QUESTIONS = {
  work:    [
    { zh: "你做这个工作多久了？", py: "nǐ zuò zhège gōngzuò duō jiǔ le?",    en: "How long have you done this job?",    topic: "work_duration" },
    { zh: "你喜欢这个工作吗？",   py: "nǐ xǐhuān zhège gōngzuò ma?",           en: "Do you enjoy this job?",               topic: "work_like" },
    { zh: "你在哪里工作？",       py: "nǐ zài nǎlǐ gōngzuò?",                  en: "Where do you work?",                   topic: "work_platform" },
  ],
  travel:  [
    { zh: "你去过哪里？",         py: "nǐ qù guò nǎlǐ?",                        en: "Where have you been?",                 topic: "travel_where" },
    { zh: "你喜欢哪里？",         py: "nǐ xǐhuān nǎlǐ?",                        en: "Which place do you like?",             topic: "travel_fav" },
    { zh: "你想去哪里？",         py: "nǐ xiǎng qù nǎlǐ?",                      en: "Where would you like to go?",          topic: "travel_where" },
  ],
  place:   [
    { zh: "你喜欢那里吗？",       py: "nǐ xǐhuān nàlǐ ma?",                     en: "Do you like it there?",               topic: "place_like" },
    { zh: "那里有什么好吃的？",   py: "nàlǐ yǒu shénme hào chī de?",           en: "What good food is there?",             topic: "food_local" },
    { zh: "那里有什么特别？",     py: "nàlǐ yǒu shénme tèbié?",                 en: "What's special about that place?",     topic: "place_special" },
  ],
  family:  [
    { zh: "你和谁一起住？",       py: "nǐ hé shéi yīqǐ zhù?",                   en: "Who do you live with?",               topic: "family_live_with" },
    { zh: "你有兄弟姐妹吗？",     py: "nǐ yǒu xiōngdì jiěmèi ma?",              en: "Do you have siblings?",               topic: "family_parents" },
    { zh: "家里谁最重要？",       py: "jiālǐ shéi zuì zhòngyào?",                en: "Who is most important at home?",       topic: "family_parents" },
  ],
  food:    [
    { zh: "你最喜欢什么菜？",     py: "nǐ zuì xǐhuān shénme cài?",              en: "What dish do you like most?",          topic: "food_fav" },
    { zh: "你会做饭吗？",         py: "nǐ huì zuò fàn ma?",                      en: "Can you cook?",                       topic: "food_fav" },
    { zh: "那里有什么好吃的？",   py: "nàlǐ yǒu shénme hào chī de?",           en: "What good food is there?",             topic: "food_local" },
  ],
  identity:[
    { zh: "你叫什么名字？",       py: "nǐ jiào shénme míngzi?",                  en: "What's your name?",                   topic: "name_what" },
    { zh: "你多大？",             py: "nǐ duō dà?",                               en: "How old are you?",                    topic: "age" },
    { zh: "你是哪里人？",         py: "nǐ shì nǎlǐ rén?",                       en: "Where are you from?",                 topic: "place_from" },
  ],
};

/**
 * Returns answer-reactive probe questions anchored to keywords in the persona's counter_reply.
 * For rich reveals (multi-city, work+place, food mentions), returns up to 4 questions so the
 * blue panel can show genuinely relevant exploration options rather than generic fillers.
 *
 * Caller is responsible for the final cap via _dedupeQuestions.
 */
function _augmentQuestionsFromAnswer(counterReply) {
  if (!counterReply) return [];
  const t = counterReply;
  const extra = [];

  // ── Two-city / work-in-different-city reveal ──────────────────────────────
  // e.g. "我是成都人，不过在北京工作已经好几年了。"
  // Detect two distinct place mentions to surface richer place+work exploration.
  const _bigCities = ["北京", "上海", "成都", "西安", "广州", "深圳", "重庆", "杭州", "南京", "天津",
                      "武汉", "沈阳", "青岛", "厦门", "苏州", "长沙", "郑州", "济南"];
  const _citiesInReply = _bigCities.filter(c => t.includes(c));
  const _twoCities = _citiesInReply.length >= 2;

  if (_twoCities) {
    const [c1, c2] = _citiesInReply;
    extra.push({ zh: `你更喜欢${c1}还是${c2}？`, py: "", en: `Do you prefer ${c1} or ${c2}?` });
    extra.push({ zh: `你为什么去${c2}？`,         py: "", en: `Why did you go to ${c2}?` });
    extra.push({ zh: `${c2}的生活怎么样？`,       py: "", en: `What is life like in ${c2}?` });
    extra.push({ zh: `${c1}远吗？`,               py: "", en: `Is ${c1} far?` });
    return extra;  // Two-city reveal: return these 4 directly, no need to scan more
  }

  // ── Single city mention ───────────────────────────────────────────────────
  const _singleCity = _citiesInReply.length === 1 ? _citiesInReply[0] : null;
  if (_singleCity) {
    extra.push({ zh: `你喜欢${_singleCity}吗？`,       py: "", en: `Do you like ${_singleCity}?` });
    extra.push({ zh: `${_singleCity}有什么特别的？`,   py: "", en: `What's special about ${_singleCity}?` });
  }

  // ── Work / occupation ─────────────────────────────────────────────────────
  const _workOcc = /工作|上班|老师|教书|退休|公司|开发|软件|程序员|工程师|从事/;
  if (_workOcc.test(t)) {
    extra.push({ zh: "你喜欢这个工作吗？",       py: "nǐ xǐhuān zhège gōngzuò ma?",       en: "Do you enjoy this work?" });
    if (!/多久|几年|年|做了/.test(t))
      extra.push({ zh: "你做这个工作多久了？",     py: "nǐ zuò zhège gōngzuò duō jiǔ le?",  en: "How long have you done this work?" });
  }
  if (/工作.*年|做了.*年|几年了/.test(t))
    extra.push({ zh: "你做这份工作多久了？",     py: "nǐ zuò zhèfèn gōngzuò duōjiǔ le?",  en: "How long have you done this work?" });
  if (/为什么.*工作|为什么.*当|为什么.*做|开发|软件|程序员/.test(t))
    extra.push({ zh: "你为什么做这个？",         py: "nǐ wèishénme zuò zhège?",            en: "Why do you do this?" });
  if (/老师|教书|教学/.test(t))
    extra.push({ zh: "学生怎么样？",             py: "xuéshēng zěnmeyàng?",                en: "What are the students like?" });
  if (/做.{2,14}的/.test(t) && !/地方|那里|吃的|菜|饭|好吃/.test(t)) {
    if (!extra.some((q) => /多久/.test(q.zh || "")))
      extra.push({ zh: "你做这个多久了？",       py: "nǐ zuò zhège duō jiǔ le?",          en: "How long have you been doing this?" });
    if (!extra.some((q) => /喜欢/.test(q.zh || "")))
      extra.push({ zh: "你喜欢这个吗？",         py: "nǐ xǐhuān zhège ma?",               en: "Do you like it?" });
  }

  // ── Place / generic location ──────────────────────────────────────────────
  if (!_singleCity && /地方|那里|那边|城市|家乡|老家/.test(t))
    extra.push({ zh: "那里有什么特别的？",       py: "nàlǐ yǒu shénme tèbié de?",         en: "What's special about that place?" });
  if (/喜欢.*那里|喜欢.*那边|喜欢.*那个/.test(t))
    extra.push({ zh: "你为什么喜欢那里？",       py: "nǐ wèishénme xǐhuān nàlǐ?",        en: "Why do you like it there?" });

  // ── Food / eating ─────────────────────────────────────────────────────────
  if (/吃|美食|火锅|菜|好吃|回锅肉|饺子|面|饭/.test(t))
    extra.push({ zh: "你最喜欢吃什么？",         py: "nǐ zuì xǐhuān chī shénme?",         en: "What do you like eating most?" });
  if (/辣|川菜|麻辣/.test(t))
    extra.push({ zh: "你喜欢吃辣吗？",           py: "nǐ xǐhuān chī là ma?",               en: "Do you like spicy food?" });
  if (/妈妈.*做|做的.*菜|自己做|会做/.test(t))
    extra.push({ zh: "你会自己做吗？",           py: "nǐ huì zìjǐ zuò ma?",                en: "Can you make it yourself?" });

  // ── Family ────────────────────────────────────────────────────────────────
  if (/太太|老婆|爱人|丈夫|结婚|成家/.test(t))
    extra.push({ zh: "你结婚了吗？",             py: "nǐ jiéhūn le ma?",                   en: "Are you married?" });
  if (/孩子|儿子|女儿|小孩|宝宝/.test(t))
    extra.push({ zh: "你有孩子吗？",             py: "nǐ yǒu háizi ma?",                   en: "Do you have children?" });
  if (/妈妈|爸爸|父母|家人|家里/.test(t))
    extra.push({ zh: "你家里有几个人？",         py: "nǐ jiālǐ yǒu jǐ gè rén?",           en: "How many in your family?" });

  // ── Travel / hobbies ──────────────────────────────────────────────────────
  if (/去过|旅行|旅游/.test(t))
    extra.push({ zh: "你去过哪里？",             py: "nǐ qùguò nǎlǐ?",                    en: "Where have you been?" });
  if (/喜欢.*做|爱好|兴趣/.test(t))
    extra.push({ zh: "你平时喜欢做什么？",       py: "nǐ píngshí xǐhuān zuò shénme?",     en: "What do you enjoy doing?" });

  // ── Generic why-like fallback (only if nothing else matched) ─────────────
  if (/喜欢/.test(t) && extra.length === 0)
    extra.push({ zh: "你为什么喜欢这个？",       py: "nǐ wèishénme xǐhuān zhège?",         en: "Why do you like this?" });

  return extra;
}

/**
 * Deduplicates a question list by the question's Chinese text (q.zh).
 * Preserves order (first occurrence wins) and caps to maxLen items.
 * Default cap is 3 (Phase 1: relevance > variety).
 */
function _dedupeQuestions(qs, maxLen = 3) {
  const seen = new Set();
  return qs.filter(q => {
    const key = (q.zh || "").trim();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, maxLen);
}

/** Returns topic-based fallback questions for the given engine ID, or [] if unknown. */
function _getTopicFallbackQuestions(engineId) {
  const e = (engineId || "").toLowerCase();
  if (/work|job|career|retire|teach/.test(e)) return _TOPIC_FALLBACK_QUESTIONS.work;
  if (/travel|trip|visit|tour/.test(e))       return _TOPIC_FALLBACK_QUESTIONS.travel;
  if (/place|city|country|origin|from|where/.test(e)) return _TOPIC_FALLBACK_QUESTIONS.place;
  if (/family|spouse|parent|child|live/.test(e))   return _TOPIC_FALLBACK_QUESTIONS.family;
  if (/food|eat|restaurant|cook/.test(e))      return _TOPIC_FALLBACK_QUESTIONS.food;
  if (/name|identity|age|how_old/.test(e))     return _TOPIC_FALLBACK_QUESTIONS.identity;
  return [];
}

// ── Discovery panel: "You interview the persona" mode ───────────────────────
/**
 * Render clickable "Ask them:" cards so the learner can interview the persona
 * instead of being relentlessly asked questions themselves.
 * questions: array of { zh, py, en, topic }
 */
function renderDiscoveryPanel(questions, pendingFrameText) {
  // Store the queued frame question so "Continue" can speak it later.
  if (pendingFrameText) window._pendingFrameText = pendingFrameText.trim();

  // Update the persistent cache whenever fresh questions arrive.
  // Also track engine so staleness guard can detect engine changes.
  if (Array.isArray(questions) && questions.length > 0) {
    window._lastBlueQuestions     = questions.slice();
    window._lastDiscoveryEngineId = (window._currentEngineId || "").toLowerCase();
  }

  let panel = document.getElementById("discoveryPanel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "discoveryPanel";
    // Insert after sentence options so blue mirror questions sit below suggested responses
    const anchor = document.getElementById("optionsContainerParent")
                || document.querySelector(".current-turn-options")
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
    ? `<div class="discovery-header">你想了解什么？ <span class="discovery-sub">Questions you can ask:</span></div>`
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
    // iOS: touchstart on divs isn't always forwarded as a click; handle explicitly on mobile.
    if (_isMobileLayout()) {
      let _discTouchMoved = false;
      card.addEventListener("touchstart", () => { _discTouchMoved = false; }, { passive: true });
      card.addEventListener("touchmove",  () => { _discTouchMoved = true;  }, { passive: true });
      card.addEventListener("touchend", (ev) => {
        if (_discTouchMoved) return;
        if (ev.target.closest(".op-icon-btn")) return;
        ev.preventDefault();
        ttsUnlock();
        submitDiscoveryQuestion(q);
      }, { passive: false });
    }
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
              _initActiveTurnRecord(pending, meta.text_en || "", meta.pinyin || "", meta.frame_id || "");
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
      _initActiveTurnRecord(pending, meta.text_en || "", meta.pinyin || "", meta.frame_id || "");
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
    addTranscriptEntry("partner", stub, partnerTranscriptExtrasFromData(data, stub));
    renderTranscript();
    applyPartnerStubToActiveSentence(stub, data, payload.turn_uid);
    ttsSpeak({ text: stub, lang: "zh-CN", queue: true });
  }

  // Re-render discovery panel with remaining questions (server already excluded the asked one).
  // Pass null so _pendingFrameText is preserved (Continue button still works).
  const remaining = (data.mirror_options || []).filter(m => (m.zh || "") !== zh);
  if (remaining.length > 0) {
    renderDiscoveryPanel(remaining, null);
  } else {
    // Mirror bank exhausted for this turn — restore the last cached set so the panel
    // stays useful rather than flipping into deflect / empty mode.
    const _cached = window._lastBlueQuestions || [];
    renderDiscoveryPanel(_cached, null);
  }
}

// ── MandarinOS-style ZH naturalizer ─────────────────────────────────────────
// Shared post-processor applied to every EN→ZH translation output.
// Converts formal/written vocabulary to spoken/learner-friendly equivalents
// and fixes structural patterns that are misleading in context.
//
// Add new entries to _ZH_VOCAB_PAIRS as they are discovered.
// Longer / more-specific patterns MUST appear before shorter ones.
const _ZH_VOCAB_PAIRS = [
  ..._SPOKEN_REGISTER_PAIRS,
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
  // ── Common conversational questions (spoken-first) ────────────────────────
  "do you live with your parents":     "你跟爸妈一起住吗？",
  "do you live with your family":      "你跟家人一起住吗？",
  "do you live alone":                 "你一个人住吗？",
  "are you married":                   "你结婚了吗？",
  "do you have children":              "你有孩子吗？",
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
      _tracker.translation_help_uses++;
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
        _tracker.translation_help_uses++;
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
    if (_isMobileLayout()) return;
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

      engMicBtn.addEventListener("touchstart", (e) => {
        e.stopPropagation();
        window._micListenArmedAt = Date.now();
      }, { passive: true });
      engMicBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        window._micListenArmedAt = Date.now();
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
          window._micListenArmedAt = Date.now();
          document.body.classList.add("is-listening");
          engMicBtn.classList.add("recording");
          engMicBtn.title = "Listening… (click to stop)";
        };
        _engRec.onend = () => {
          _engRecording = false;
          engMicBtn.classList.remove("recording");
          engMicBtn.title = "Speak in English";
          _engRec = null;
          const st = document.getElementById("listenStatus")?.dataset?.state;
          if (!st || st === "idle") document.body.classList.remove("is-listening");
        };
        _engRec.onerror = () => {
          _engRecording = false;
          engMicBtn.classList.remove("recording");
          engMicBtn.title = "Speak in English";
          _engRec = null;
          const st = document.getElementById("listenStatus")?.dataset?.state;
          if (!st || st === "idle") document.body.classList.remove("is-listening");
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
  const interp = response.session_interpretation || {};

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

  // ── Session objective card (very top of scorecard) ──────────────────────
  // Evaluate whether the session objective was met, then render a short
  // "Today's focus" card with aligned reflection text above everything else.
  {
    const obj = window._sessionObjective || buildSessionObjective(_loadLastSessionStats());
    const endStats = {
      total_turns:     _tracker.total_turns     || 0,
      questions_asked: _tracker.questions_asked || 0,
      recovery_uses:   _tracker.recovery_uses   || 0,
      depth_responses: _tracker.depth_responses || 0,
    };
    const met = typeof obj.check === "function" ? obj.check(endStats) : false;

    const objCard = document.createElement("div");
    objCard.className = "sc-objective sc-objective--post";
    objCard.dataset.objId = obj.id;

    const objLbl = document.createElement("div");
    objLbl.className = "sc-obj-label";
    objLbl.textContent = "Today\u2019s focus";
    objCard.appendChild(objLbl);

    const objTxt = document.createElement("p");
    objTxt.className = "sc-obj-text";
    objTxt.textContent = obj.text;
    objCard.appendChild(objTxt);

    const reflTxt = document.createElement("p");
    reflTxt.className = met ? "sc-obj-reflection sc-obj-met" : "sc-obj-reflection sc-obj-not-met";
    reflTxt.textContent = met ? obj.reflection_met : obj.reflection_not_met;
    objCard.appendChild(reflTxt);

    content.appendChild(objCard);

    const objDivider = document.createElement("hr");
    objDivider.className = "sc-divider";
    content.appendChild(objDivider);
  }

  // ── Reflection section (top of scorecard) ──────────────────────────────
  // Render headline + capability / progress / next-step lines above metrics.
  // Data comes from _buildAbilitySummary() — the same source previously used
  // by _renderAbilityDashboard(). Only the render location has changed.
  const summary = _buildAbilitySummary(m);
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
      m.recovery.display_summary || `${m.recovery.raw_uses} recoveries (${m.recovery.raw_successes} successful)`,
      interp.recovery || m.recovery.label,
      "How well you got unstuck",
    ],
    [
      `${m.support.raw_uses} support uses`,
      interp.support || m.support.label,
      "How much help you used — support is part of learning, not failure",
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
      `${m.stability.raw_unmatched} unclear turn${m.stability.raw_unmatched === 1 ? "" : "s"}`,
      interp.flow || m.stability.label,
      "How smooth the conversation felt — messy sessions can still show real progress",
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
// ── Session Objective System ──────────────────────────────────────────────────
// Lightweight "Today's focus" guidance shown before and after each session.
// Uses only simple session-level data; no server changes required.
// Persistence: stores last-session stats in localStorage (key: manos_last_session)
// so returning users get a contextual objective rather than the default.

/** Load last-session stats from localStorage. Returns null if none exist. */
function _loadLastSessionStats() {
  try {
    const raw = localStorage.getItem("manos_last_session");
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

/** Save this session's stats so the NEXT session can pick an appropriate objective. */
function _saveLastSessionStats(stats) {
  try {
    localStorage.setItem("manos_last_session", JSON.stringify(stats));
  } catch (_) {
    // localStorage unavailable (private browsing, etc.) — silently ignore
  }
}

/**
 * Choose one small conversational objective based on the previous session.
 * Returns an object: { id, text, check(stats) → bool, reflection_met, reflection_not_met }
 */
function buildSessionObjective(lastStats) {
  const OBJECTIVES = {
    default: {
      id: "default",
      text: "Try having a short conversation. Choose one persona and one conversation frame, then click Start.",
      check: (s) => (s.total_turns || 0) >= 2,
      reflection_met:     "You had a conversation \u2014 great start!",
      reflection_not_met: "Next time, try having a short conversation with one persona.",
    },
    more_turns: {
      id: "more_turns",
      text: "Try to keep the conversation going for a few more turns.",
      check: (s) => (s.total_turns || 0) >= 5,
      reflection_met:     "You kept the conversation going \u2014 well done!",
      reflection_not_met: "The conversation was brief this time. Next time, try keeping it going a little longer.",
    },
    ask_question: {
      id: "ask_question",
      text: "Try asking the persona one question back.",
      check: (s) => (s.questions_asked || 0) >= 1,
      reflection_met:     "You asked a question back \u2014 that helped keep the conversation going.",
      reflection_not_met: "You didn\u2019t ask a question back this time. Next time, try asking \u201c\u4f60\u5462\uff1f\u201d once.",
    },
    recovery_phrase: {
      id: "recovery_phrase",
      text: "Try using a recovery phrase when you get stuck.",
      check: (s) => (s.recovery_uses || 0) >= 1,
      reflection_met:     "You used a recovery phrase \u2014 that\u2019s a real conversation skill.",
      reflection_not_met: "Next time, try tapping a recovery phrase when you feel stuck.",
    },
    longer_answer: {
      id: "longer_answer",
      text: "Try giving one slightly longer answer.",
      check: (s) => (s.depth_responses || 0) >= 1,
      reflection_met:     "You gave a more detailed answer \u2014 that\u2019s great for conversation practice.",
      reflection_not_met: "Next time, try adding one extra detail to your answer.",
    },
  };

  if (!lastStats) return OBJECTIVES.default;

  const { total_turns = 0, questions_asked = 0, recovery_uses = 0, depth_responses = 0 } = lastStats;

  // Prioritise the weakest signal from the last session
  if (total_turns < 4)                        return OBJECTIVES.more_turns;
  if (questions_asked === 0)                  return OBJECTIVES.ask_question;
  if (recovery_uses >= 3 && depth_responses === 0) return OBJECTIVES.longer_answer;
  if (recovery_uses >= 1 && depth_responses === 0) return OBJECTIVES.longer_answer;
  if (questions_asked >= 1 && total_turns >= 4)    return OBJECTIVES.default;
  return OBJECTIVES.default;
}

/**
 * Render the "Today's focus" block into #scorecardContent.
 * Called on page load (before a session starts) and after startFreshLearner().
 * Stores the chosen objective in window._sessionObjective so renderScorecard
 * can evaluate it at session end without re-computing.
 */
function renderSessionObjective() {
  const el = document.getElementById("scorecardContent");
  if (!el) return;

  const showFirstTimeGuide =
    window._isFirstTimeBetaUser && !window._onboardingGuideDismissed;
  const lastStats = showFirstTimeGuide ? null : _loadLastSessionStats();
  const obj = showFirstTimeGuide
    ? {
        id: "first_time_onboarding",
        text: _FIRST_TIME_ONBOARDING_TEXT,
        check: () => true,
        reflection_met: "",
        reflection_not_met: "",
      }
    : buildSessionObjective(lastStats);
  window._sessionObjective = obj;

  el.innerHTML = "";
  el.classList.remove("scorecard-placeholder");

  const block = document.createElement("div");
  block.className = "sc-objective";
  block.dataset.objId = obj.id;

  const lbl = document.createElement("div");
  lbl.className = "sc-obj-label";
  lbl.textContent = showFirstTimeGuide ? "Getting started" : "Today\u2019s focus";
  block.appendChild(lbl);

  const txt = document.createElement("p");
  txt.className = "sc-obj-text";
  txt.textContent = obj.text;
  block.appendChild(txt);

  el.appendChild(block);

  if (!showFirstTimeGuide) {
    const hint = document.createElement("p");
    hint.className = "sc-obj-hint";
    hint.textContent = "Complete the session to see your reflection.";
    el.appendChild(hint);
  }
}

window.buildSessionObjective   = buildSessionObjective;
window.renderSessionObjective  = renderSessionObjective;

// ── Progress history (Phase 1: snapshot persistence only — no graph UI yet) ───

const _PROGRESS_HISTORY_KEY = "manos_progress_history";
const _USER_TIER_KEY        = "manos_user_tier";

/** @returns {"standard"|"premium"} */
function getUserTier() {
  try {
    const t = (localStorage.getItem(_USER_TIER_KEY) || "standard").trim().toLowerCase();
    return t === "premium" ? "premium" : "standard";
  } catch (_) {
    return "standard";
  }
}

/** @returns {object[]} */
function loadProgressHistory() {
  try {
    const raw = localStorage.getItem(_PROGRESS_HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

/**
 * Standard: latest 10 snapshots. Premium: unlimited.
 * @param {object[]} history
 * @param {string} [tier]
 */
function applyRetention(history, tier) {
  if (!Array.isArray(history)) return [];
  const t = (tier || getUserTier() || "standard").toLowerCase();
  if (t === "premium") return history.slice();
  return history.slice(-10);
}

/**
 * Deduplicate an array of progress snapshots by session_id (or created_at fallback).
 * When duplicates exist, the LAST occurrence wins (most recent stats).
 * @param {object[]} snapshots
 * @returns {object[]}
 */
function _dedupeProgressSnapshots(snapshots) {
  if (!Array.isArray(snapshots)) return [];
  const seen = new Map();
  for (const snap of snapshots) {
    if (!snap || typeof snap !== "object") continue;
    const key = snap.session_id || snap.created_at || JSON.stringify(snap);
    seen.set(key, snap); // last write wins
  }
  return Array.from(seen.values());
}

/** Append one snapshot and persist with tier retention + session_id deduplication. */
function saveProgressSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return;
  const history = _dedupeProgressSnapshots([...loadProgressHistory(), snapshot]);
  const trimmed = applyRetention(history, getUserTier());
  try {
    localStorage.setItem(_PROGRESS_HISTORY_KEY, JSON.stringify(trimmed));
  } catch (_) {
    // localStorage unavailable — silently ignore
  }
  _persistProgressSnapshotToServer(snapshot);
}

/** Fire-and-forget server persistence for beta multi-user history. */
function _persistProgressSnapshotToServer(snapshot) {
  const lid = window._learnerId;
  if (!lid || !snapshot) return;
  fetch("/api/save_progress", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ learner_id: lid, snapshot }),
  }).catch(() => {});
}

function _renderProgressSavedMessage() {
  const content = document.getElementById("scorecardContent");
  if (!content) return;
  let el = document.getElementById("progressSavedMsg");
  if (!el) {
    el = document.createElement("div");
    el.id = "progressSavedMsg";
    el.className = "progress-saved-msg";
    content.appendChild(el);
  }
  el.textContent = "Saved to Progress";
}

// Guard: fetch at most once per page load to avoid hammering the server.
let _serverProgressSyncDone = false;

/**
 * Merge server progress history into localStorage (additive, deduplicated by session_id).
 * Called when the Progress tab opens with an empty localStorage, but also merges safely
 * when localStorage already has local-only sessions not yet on the server.
 * Fire-and-forget: re-renders the progress view when new data arrives.
 */
async function _syncServerProgressIfEmpty() {
  const learnerId = window._learnerId;
  if (!learnerId) return;
  if (_serverProgressSyncDone) return; // already synced this page load
  _serverProgressSyncDone = true;
  try {
    const r = await fetch("/api/progress?learner_id=" + encodeURIComponent(learnerId));
    if (!r.ok) return;
    const data = await r.json();
    if (data.ok && Array.isArray(data.snapshots) && data.snapshots.length > 0) {
      // MERGE server snapshots with local; deduplicate by session_id so neither
      // local-only sessions nor server-only sessions are lost.
      const local = loadProgressHistory();
      const merged = _dedupeProgressSnapshots([...data.snapshots, ...local]);
      // local entries take precedence (appear last in merged, win the deduplication)
      if (merged.length > local.length) {
        try {
          localStorage.setItem(
            _PROGRESS_HISTORY_KEY,
            JSON.stringify(applyRetention(merged, getUserTier()))
          );
        } catch (_) {}
        renderProgressView();
      } else {
        // No new server data — just update the status note
        const note = document.getElementById("_progressServerNote");
        if (note) note.remove();
      }
    } else {
      const note = document.getElementById("_progressServerNote");
      if (note) note.textContent = "No saved sessions found on server (" + learnerId + ").";
    }
  } catch (_) {
    const note = document.getElementById("_progressServerNote");
    if (note) note.remove();
  }
}

// ── Progress view (Phase 2: UI only — reads manos_progress_history) ───────────

const _PROGRESS_CHART_MAX_STANDARD = 10;
const _PROGRESS_CHART_MAX_PREMIUM  = 30;
const _PROGRESS_EMPTY_HEADLINE =
  "No progress record yet.";
const _PROGRESS_EMPTY_BODY =
  "Finish a conversation session and MandarinOS will begin building your speaking progress history.";

/**
 * Sessions to show in graph/table (display slice only — storage unchanged).
 * @param {object[]} history
 * @param {string} [tier]
 */
function getProgressSessionsForDisplay(history, tier) {
  const h = Array.isArray(history) ? history.slice() : [];
  const t = (tier || getUserTier() || "standard").toLowerCase();
  if (t === "premium") return h.slice(-_PROGRESS_CHART_MAX_PREMIUM);
  return h.slice(-_PROGRESS_CHART_MAX_STANDARD);
}

function _formatProgressDate(createdAt) {
  if (!createdAt) return "—";
  try {
    const d = new Date(createdAt);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch (_) {
    return "—";
  }
}

function _formatFlowCell(snap) {
  if (snap?.flow_display_label) return snap.flow_display_label;
  if (snap?.stability_display_label) {
    const s = snap.stability_display_label;
    if (s.includes(" · ")) return s.split(" · ").slice(1).join(" · ");
    return s;
  }
  const score = snap?.conversation_stability_score;
  const unclear = snap?.unclear_turns || 0;
  const softUnclear = snap?.soft_unclear_turns || 0;
  const repairMoments = (snap?.recovery_uses || 0) + (snap?.conversational_recoveries || 0);
  const hasTurbulence = unclear > 0 || softUnclear > 0 || repairMoments > 0;
  if (score == null || typeof score !== "number") return "—";
  if (hasTurbulence) {
    if (repairMoments >= 3 || unclear >= 4) return "Worked through turbulence";
    if (snap?.progress_signals?.turbulence_survived || (snap?.total_turns || 0) >= 15) {
      return "Messy but sustained";
    }
    return "Stayed on track";
  }
  if (score >= 95) return "Smooth";
  if (score >= 80) return "Stable";
  return "Difficult but continued";
}

function _formatSupportCell(snap) {
  if (snap?.support_display_label) return snap.support_display_label;
  const n =
    (snap?.suggestion_clicks || 0) +
    (snap?.hint_clicks || 0) +
    (snap?.display_en_clicks || 0) +
    (snap?.display_py_clicks || 0) +
    (snap?.translation_help_uses || 0);
  if (n === 0) return "None";
  if (n <= 2) return "Light";
  if (n <= 5) return "Moderate";
  return "Heavy";
}

function _formatSupportDetail(snap) {
  const parts = [];
  const en = snap?.display_en_clicks || 0;
  const py = snap?.display_py_clicks || 0;
  const hints = snap?.hint_clicks || 0;
  const options = snap?.suggestion_clicks || 0;
  const cards = snap?.card_opens || snap?.card_exploration_count || 0;
  const translate = snap?.translation_help_uses || 0;
  if (options > 0) parts.push(`Options ${options}`);
  if (hints > 0) parts.push(`Hints ${hints}`);
  if (en > 0) parts.push(`EN ${en}`);
  if (py > 0) parts.push(`PY ${py}`);
  if (translate > 0) parts.push(`Translate ${translate}`);
  if (cards > 0) parts.push(`Exploration ${cards}`);
  return parts.length ? parts.join(" · ") : "";
}

function _formatRecoveryCell(snap) {
  if (snap?.recovery_display_label) return snap.recovery_display_label;
  const unclear = snap?.unclear_turns || 0;
  const recoveryUses = snap?.recovery_uses || 0;
  const convSuccess = snap?.successful_conversational_recoveries || 0;
  const convAttempts = snap?.conversational_recoveries || 0;
  const continued = snap?.progress_signals?.continued_after_ambiguity;
  const totalTurns = snap?.total_turns || 0;
  const rate = snap?.recovery_success_rate;
  if (unclear > 0 && convSuccess >= 2) return "Self-recovered often";
  if (unclear > 0 && convSuccess > 0) return "Self-recovered";
  if (recoveryUses > 0 && convSuccess > 0) return "Used support + self-recovered";
  if (recoveryUses > 0) {
    if (rate != null) {
      const pct = Math.round(Number(rate) * 100);
      return Number.isNaN(pct) ? "App-assisted" : `App-assisted (${pct}%)`;
    }
    return "App-assisted";
  }
  if (unclear > 0 && convAttempts > 0) return "Kept going";
  if (unclear > 0 && (continued || totalTurns >= 8)) {
    if ((snap?.questions_asked || 0) >= 2 && totalTurns >= 12) return "Kept going";
    return "Stayed on track";
  }
  if (unclear === 0 && recoveryUses === 0) return "Smooth";
  if (unclear > 0) return "Stayed on track";
  return "No system help";
}

function _formatStabilityCell(snap) {
  if (snap?.stability_display_label) return snap.stability_display_label;
  const score = snap?.conversation_stability_score;
  if (score == null || typeof score !== "number") return "—";
  const unclear = snap?.unclear_turns || 0;
  const repairMoments = (snap?.recovery_uses || 0) + (snap?.conversational_recoveries || 0);
  const hasTurbulence = unclear > 0 || repairMoments > 0;
  if (score >= 95 && !hasTurbulence) return `${score} · Smooth`;
  if (score >= 80) return `${score} · ${hasTurbulence ? "Stayed on track" : "Stable"}`;
  if (score >= 65) return `${score} · Messy but sustained`;
  if (score >= 45) return `${score} · Worked through turbulence`;
  return `${score} · Difficult but continued`;
}

function _formatSupportUsed(snap) {
  const parts = [];
  const options = snap?.suggestion_clicks || 0;
  const cards = snap?.card_opens || 0;
  const hints = snap?.hint_clicks || 0;
  const en = snap?.display_en_clicks || 0;
  const py = snap?.display_py_clicks || 0;
  if (options > 0) parts.push(`Options ${options}`);
  if (cards > 0) parts.push(`Cards ${cards}`);
  if (hints > 0) parts.push(`Hints ${hints}`);
  if (en > 0) parts.push(`EN ${en}`);
  if (py > 0) parts.push(`PY ${py}`);
  return parts.length === 0 ? "None" : parts.join(" · ");
}

/**
 * Simple trend headline from recent stability scores (no analytics engine).
 * @param {object[]} sessions
 */
function buildProgressHeadline(sessions) {
  if (!sessions || sessions.length === 0) return "";

  const recent = sessions.slice(-3);
  if (recent.length < 2) return "Building your conversational history";

  const scores = recent
    .map((s) => s.conversation_stability_score)
    .filter((v) => v != null && typeof v === "number");

  const recentTurns = recent.map((s) => s.total_turns || 0);
  const recentQuestions = recent.map((s) => s.questions_asked || 0);
  const turbulenceCount = recent.filter(
    (s) => s.progress_signals && s.progress_signals.turbulence_survived,
  ).length;
  const persistenceCount = recent.filter(
    (s) => s.progress_signals && s.progress_signals.conversational_persistence,
  ).length;

  const recentSupport = recent.map((s) => _formatSupportCell(s));
  const heavySupportCount = recentSupport.filter((l) => l === "Moderate" || l === "Heavy").length;
  const messyFlowCount = recent.filter((s) => {
    const flow = s.flow_display_label || s.stability_display_label || "";
    return /Messy|turbulence|Difficult/i.test(flow);
  }).length;

  if (turbulenceCount >= 2 || persistenceCount >= 2 || messyFlowCount >= 2) {
    return "You are staying engaged through turbulence";
  }

  if (heavySupportCount >= 2) {
    return "You are using support to keep conversations alive";
  }

  if (recentTurns.length >= 2 && recentTurns[recentTurns.length - 1] >= recentTurns[0] + 4) {
    if (messyFlowCount >= 1 || turbulenceCount >= 1) {
      return "You are becoming more resilient in conversation";
    }
    return "You are sustaining longer conversations";
  }

  if (recentQuestions.length >= 2 && recentQuestions[recentQuestions.length - 1] > recentQuestions[0]) {
    return "You are asking more questions back";
  }

  if (turbulenceCount >= 1 || persistenceCount >= 1) {
    return "You are staying engaged even when conversations get messy";
  }

  if (scores.length >= 2) {
    const delta = scores[scores.length - 1] - scores[0];
    if (delta >= 8) return "Your conversational steadiness is improving";
    if (delta <= -10) return "Your conversations are staying on track";
    return "Your conversations are staying on track";
  }

  return "Building your conversational history";
}

/**
 * Inline SVG line chart — Conversation Stability (0–100), no external libs.
 * @param {HTMLElement} container
 * @param {object[]} sessions
 */
function renderStabilityChart(container, sessions) {
  if (!container) return;
  container.innerHTML = "";

  const title = document.createElement("div");
  title.className = "progress-chart-title";
  title.textContent = "Conversation Stability";
  container.appendChild(title);

  if (!sessions || sessions.length === 0) return;

  const W = 300;
  const H = 150;
  const padL = 34;
  const padR = 10;
  const padT = 12;
  const padB = 26;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "progress-stability-chart");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Conversation Stability over recent sessions");

  const n = sessions.length;
  const xAt = (i) => padL + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const yAt = (score) => padT + plotH - (score / 100) * plotH;

  // Grid lines at 0, 50, 100
  [0, 50, 100].forEach((tick) => {
    const y = yAt(tick);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(padL));
    line.setAttribute("x2", String(W - padR));
    line.setAttribute("y1", String(y));
    line.setAttribute("y2", String(y));
    line.setAttribute("class", "progress-chart-grid");
    svg.appendChild(line);

    const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lbl.setAttribute("x", "4");
    lbl.setAttribute("y", String(y + 3));
    lbl.setAttribute("class", "progress-chart-axis-label");
    lbl.textContent = String(tick);
    svg.appendChild(lbl);
  });

  const validPts = [];
  sessions.forEach((s, i) => {
    const score = s.conversation_stability_score;
    const x = xAt(i);
    if (score != null && typeof score === "number") {
      validPts.push({ x, y: yAt(score), score, i });
    } else {
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", String(x));
      dot.setAttribute("cy", String(padT + plotH));
      dot.setAttribute("r", "3");
      dot.setAttribute("class", "progress-chart-dot progress-chart-dot--dim");
      svg.appendChild(dot);
    }
  });

  if (validPts.length >= 2) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    path.setAttribute(
      "points",
      validPts.map((p) => `${p.x},${p.y}`).join(" "),
    );
    path.setAttribute("class", "progress-chart-line");
    svg.appendChild(path);
  }

  validPts.forEach((p) => {
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", String(p.x));
    dot.setAttribute("cy", String(p.y));
    dot.setAttribute("r", "4");
    dot.setAttribute("class", "progress-chart-dot");
    svg.appendChild(dot);
  });

  const xLbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
  xLbl.setAttribute("x", String(padL + plotW / 2));
  xLbl.setAttribute("y", String(H - 4));
  xLbl.setAttribute("text-anchor", "middle");
  xLbl.setAttribute("class", "progress-chart-axis-caption");
  xLbl.textContent = "Recent sessions";
  svg.appendChild(xLbl);

  container.appendChild(svg);
}

function renderProgressView() {
  const root = document.getElementById("progressView");
  if (!root) return;

  const history = loadProgressHistory();
  const tier = getUserTier();
  const sessions = getProgressSessionsForDisplay(history, tier);

  root.innerHTML = "";

  if (history.length === 0) {
    const empty = document.createElement("div");
    empty.className = "progress-empty";

    const h = document.createElement("p");
    h.className = "progress-empty-headline";
    h.textContent = _PROGRESS_EMPTY_HEADLINE;
    empty.appendChild(h);

    const b = document.createElement("p");
    b.className = "progress-empty-body";
    b.textContent = _PROGRESS_EMPTY_BODY;
    empty.appendChild(b);

    // Beta clarity: show which learner_id is being checked and attempt a server fetch.
    const lid = window._learnerId;
    if (lid) {
      const note = document.createElement("p");
      note.id = "_progressServerNote";
      note.className = "progress-server-note";
      note.textContent = "Checking server for saved sessions\u2026 (" + lid + ")";
      empty.appendChild(note);
      _syncServerProgressIfEmpty(); // async — re-renders if server has data
    }

    root.appendChild(empty);
    return;
  }

  const headline = document.createElement("p");
  headline.className = "progress-headline";
  headline.textContent = buildProgressHeadline(sessions);
  root.appendChild(headline);

  const chartWrap = document.createElement("div");
  chartWrap.className = "progress-chart-wrap";
  renderStabilityChart(chartWrap, sessions);
  root.appendChild(chartWrap);

  const tableWrap = document.createElement("div");
  tableWrap.className = "progress-table-wrap";
  const table = document.createElement("table");
  table.className = "progress-table";

  const thead = document.createElement("thead");
  thead.innerHTML =
    "<tr><th>Date</th><th>Turns</th><th>Flow</th><th>Questions back</th><th>Recovery</th><th>Support</th></tr>";
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  sessions
    .slice()
    .reverse()
    .forEach((snap) => {
      const tr = document.createElement("tr");
      const supportLabel = _formatSupportCell(snap);
      const supportDetail = _formatSupportDetail(snap);
      const cells = [
        _formatProgressDate(snap.created_at),
        String(snap.total_turns ?? "—"),
        _formatFlowCell(snap),
        String(snap.questions_asked ?? 0),
        _formatRecoveryCell(snap),
        supportLabel,
      ];
      cells.forEach((text, idx) => {
        const td = document.createElement("td");
        td.textContent = text;
        if (idx === 5 && supportDetail && supportLabel !== "None") {
          td.title = supportDetail;
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  table.appendChild(tbody);
  tableWrap.appendChild(table);
  root.appendChild(tableWrap);

  if (tier === "premium" && history.length > sessions.length) {
    const note = document.createElement("p");
    note.className = "progress-tier-note";
    note.textContent = `Showing your latest ${sessions.length} sessions. Full history is saved on Premium.`;
    root.appendChild(note);
  }
}

function switchRightPanel(view) {
  const sessionPanel = document.getElementById("rightPanelSession");
  const progressPanel = document.getElementById("rightPanelProgress");
  const tabSession = document.getElementById("rightTabSession");
  const tabProgress = document.getElementById("rightTabProgress");
  if (!sessionPanel || !progressPanel) return;

  const showProgress = view === "progress";
  sessionPanel.classList.toggle("right-panel-view--hidden", showProgress);
  sessionPanel.hidden = showProgress;
  progressPanel.classList.toggle("right-panel-view--hidden", !showProgress);
  progressPanel.hidden = !showProgress;

  if (tabSession) {
    tabSession.classList.toggle("right-panel-tab--active", !showProgress);
    tabSession.setAttribute("aria-selected", showProgress ? "false" : "true");
  }
  if (tabProgress) {
    tabProgress.classList.toggle("right-panel-tab--active", showProgress);
    tabProgress.setAttribute("aria-selected", showProgress ? "true" : "false");
  }

  if (showProgress) {
    renderProgressView();
    renderCapabilityCard();
  }
  _updateMobileFabLabel();
}

function _isMobileLayout() {
  return window.matchMedia("(max-width: 768px)").matches;
}

function _syncMobileBackdrop() {
  const bd = document.getElementById("mobileSheetBackdrop");
  if (!bd) return;
  if (!_isMobileLayout()) {
    bd.classList.add("hidden");
    bd.setAttribute("aria-hidden", "true");
    return;
  }
  const show =
    document.body.classList.contains("mobile-panel-open") ||
    document.body.classList.contains("card-sheet-open");
  bd.classList.toggle("hidden", !show);
  bd.setAttribute("aria-hidden", show ? "false" : "true");
}

function _syncMobileCardSheet(isOpen) {
  if (!_isMobileLayout()) {
    document.body.classList.remove("card-sheet-open");
    _syncMobileBackdrop();
    return;
  }
  document.body.classList.toggle("card-sheet-open", !!isOpen);
  _syncMobileBackdrop();
}

function _setConversationActive(active) {
  document.body.classList.toggle("conversation-active", !!active);
  if (active && !document.body.classList.contains("session-ended")) {
    document.body.classList.remove("mobile-panel-open");
    _syncMobileBackdrop();
  }
  _updateMobileFabLabel();
}

function _isMobileGuidePeekVisible() {
  return (
    _isMobileLayout() &&
    !document.body.classList.contains("conversation-active") &&
    !document.body.classList.contains("session-ended") &&
    !document.body.classList.contains("mobile-panel-open") &&
    !document.body.classList.contains("mobile-guide-collapsed")
  );
}

function _dismissMobileGuidePeek() {
  if (!_isMobileLayout()) return;
  document.body.classList.add("mobile-guide-collapsed");
  _dismissOnboardingGuideIfActive();
  _closeMobilePanel();
  _updateMobileFabLabel();
}

function _openMobilePanel() {
  if (!_isMobileLayout()) return;
  document.body.classList.add("mobile-panel-open");
  const sheet = document.getElementById("mobileRightSheet");
  if (sheet) sheet.setAttribute("aria-hidden", "false");
  const fab = document.getElementById("mobilePanelFab");
  if (fab) fab.setAttribute("aria-expanded", "true");
  _syncMobileBackdrop();
  _updateMobileFabLabel();
}

function _closeMobilePanel() {
  document.body.classList.remove("mobile-panel-open");
  const sheet = document.getElementById("mobileRightSheet");
  if (sheet) sheet.setAttribute("aria-hidden", "true");
  const fab = document.getElementById("mobilePanelFab");
  if (fab) fab.setAttribute("aria-expanded", "false");
  _syncMobileBackdrop();
  _updateMobileFabLabel();
}

function _toggleMobilePanel() {
  if (document.body.classList.contains("mobile-panel-open")) _closeMobilePanel();
  else _openMobilePanel();
}

function _updateMobileFabLabel() {
  const fab = document.getElementById("mobilePanelFab");
  const title = document.getElementById("mobileSheetTitle");
  if (!fab) return;
  const progressPanel = document.getElementById("rightPanelProgress");
  const progressVisible = progressPanel && !progressPanel.hidden;
  const open = document.body.classList.contains("mobile-panel-open");
  const ended = document.body.classList.contains("session-ended");
  const collapsed = document.body.classList.contains("mobile-guide-collapsed");
  if (open) {
    fab.textContent = "Close";
    if (title) title.textContent = progressVisible ? "Progress" : (ended ? "Session Scorecard" : "Session Guide");
  } else if (ended) {
    fab.textContent = progressVisible ? "View Progress" : "View Scorecard";
    if (title) title.textContent = progressVisible ? "Progress" : "Session Scorecard";
  } else if (collapsed) {
    fab.textContent = "Today's Focus";
    if (title) title.textContent = "Today's Focus";
  } else {
    fab.textContent = progressVisible ? "View Progress" : "Session Guide";
    if (title) title.textContent = progressVisible ? "Progress" : "Session Guide";
  }
}

function initMobileLayout() {
  const fab = document.getElementById("mobilePanelFab");
  const closeBtn = document.getElementById("mobileSheetClose");
  const backdrop = document.getElementById("mobileSheetBackdrop");
  if (!fab) return;

  if (!fab.dataset.wired) {
    fab.dataset.wired = "1";
    fab.addEventListener("click", () => _toggleMobilePanel());
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        if (document.body.classList.contains("mobile-panel-open")) {
          _closeMobilePanel();
        } else if (_isMobileGuidePeekVisible()) {
          _dismissMobileGuidePeek();
        } else {
          _closeMobilePanel();
        }
      });
    }
    if (backdrop) {
      backdrop.addEventListener("click", () => {
        _closeMobilePanel();
        if (state && state.isOpen) dispatch({ type: "CARD_PANEL_CLOSED" });
      });
    }
    window.matchMedia("(max-width: 768px)").addEventListener("change", () => {
      if (!_isMobileLayout()) {
        document.body.classList.remove("mobile-panel-open", "card-sheet-open", "mobile-guide-collapsed");
        _syncMobileBackdrop();
      }
      _updateMobileFabLabel();
    });
  }

  _syncMobileBackdrop();
  _updateMobileFabLabel();
}

// ---------------------------------------------------------------------------
// Longitudinal capability card — additive; does not touch session scorecard
// ---------------------------------------------------------------------------

const _BAND_LABELS = {
  "Emerging":      { label: "Emerging",      note: "Building foundations" },
  "Developing":    { label: "Developing",     note: "Growing steadily" },
  "Consolidating": { label: "Consolidating",  note: "Becoming reliable" },
  "Steady":        { label: "Steady",         note: "Consistently capable" },
};

const _DIM_DISPLAY = {
  sustained_conversation:    "Sustained conversation",
  recovery_resilience:       "Recovery resilience",
  conversational_initiative: "Conversational initiative",
  independence:              "Independence",
  conversational_stability:  "Conversational stability",
};

const _BAND_ORDER = ["Emerging", "Developing", "Consolidating", "Steady"];

function _capabilityBandBar(band) {
  const idx = _BAND_ORDER.indexOf(band);
  const html = _BAND_ORDER.map((b, i) => {
    const active = i === idx ? " capability-band-pip--active" : "";
    const past   = i < idx  ? " capability-band-pip--past"   : "";
    return `<span class="capability-band-pip${active}${past}" title="${b}"></span>`;
  }).join("");
  return `<span class="capability-band-bar">${html}</span>`;
}

async function renderCapabilityCard() {
  const card = document.getElementById("capabilityCard");
  if (!card) return;

  const learnerId = window._learnerId || "";
  if (!learnerId) {
    card.style.display = "none";
    return;
  }

  card.style.display = "block";
  card.innerHTML = `<div class="capability-card__loading">Loading capability history…</div>`;

  let capability;
  try {
    const res = await fetch(`/api/capability?learner_id=${encodeURIComponent(learnerId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    capability = json.capability;
  } catch (e) {
    card.innerHTML = `<div class="capability-card__error">Capability history unavailable.</div>`;
    return;
  }

  const nSessions = capability.qualifying_session_count || 0;
  if (nSessions === 0) {
    card.innerHTML = `
      <div class="capability-card__empty">
        <p class="capability-card__empty-title">Your capability trend will appear here.</p>
        <p class="capability-card__empty-body">Complete a few sessions to start building your history. Trends take time to form — that's what makes them meaningful.</p>
      </div>`;
    return;
  }

  const dims = capability.dimensions || {};
  const notes = capability.trend_notes || [];
  const inactive = capability.inactive;
  const obsLocked = capability.observation_locked;

  let inactivityHtml = "";
  if (inactive) {
    const days = capability.inactivity_days || 0;
    inactivityHtml = `<p class="capability-card__inactive-note">No sessions in ${days} days — trends paused until you return.</p>`;
  } else if (obsLocked) {
    inactivityHtml = `<p class="capability-card__inactive-note">Welcome back! Your first few sessions after a break are observation-only. Trends will update soon.</p>`;
  }

  const dimRows = Object.entries(_DIM_DISPLAY).map(([key, label]) => {
    const d = dims[key] || {};
    const band = d.band || "Emerging";
    const bl = _BAND_LABELS[band] || _BAND_LABELS["Emerging"];
    return `
      <div class="capability-dim-row">
        <span class="capability-dim-name">${label}</span>
        <span class="capability-dim-band">${bl.label}</span>
        ${_capabilityBandBar(band)}
      </div>`;
  }).join("");

  const notesHtml = notes.length
    ? `<ul class="capability-card__notes">${notes.map(n => `<li>${n}</li>`).join("")}</ul>`
    : "";

  card.innerHTML = `
    <div class="capability-card__inner">
      <h3 class="capability-card__title">Capability trend</h3>
      <p class="capability-card__subtitle">Based on ${nSessions} qualifying session${nSessions === 1 ? "" : "s"} · conservative estimates</p>
      ${inactivityHtml}
      <div class="capability-dims">${dimRows}</div>
      ${notesHtml}
      <p class="capability-card__disclaimer">Trends move slowly by design. Progress here reflects sustained patterns, not any single session.</p>
    </div>`;
}

function initRightPanelTabs() {
  const tabSession = document.getElementById("rightTabSession");
  const tabProgress = document.getElementById("rightTabProgress");
  if (tabSession) {
    tabSession.addEventListener("click", () => switchRightPanel("session"));
  }
  if (tabProgress) {
    tabProgress.addEventListener("click", () => switchRightPanel("progress"));
  }
}

window.getUserTier                    = getUserTier;
window.loadProgressHistory            = loadProgressHistory;
window._syncServerProgressIfEmpty     = _syncServerProgressIfEmpty;
window.applyRetention                 = applyRetention;
window.saveProgressSnapshot           = saveProgressSnapshot;
window.getProgressSessionsForDisplay  = getProgressSessionsForDisplay;
window.buildProgressHeadline          = buildProgressHeadline;
window.renderStabilityChart           = renderStabilityChart;
window.renderProgressView             = renderProgressView;
window.switchRightPanel               = switchRightPanel;
window.initRightPanelTabs             = initRightPanelTabs;
window.renderCapabilityCard           = renderCapabilityCard;

async function endSession() {
  // Prevent double-submission (e.g. double-tap on iOS)
  const _btn = document.getElementById("endSessionBtn");
  if (_btn && _btn.disabled) return;
  if (_btn) {
    _btn.disabled = true;
    _btn.textContent = "Saving\u2026";
  }

  const t = _tracker;
  const _startedAt = window._sessionStartedAt || Date.now();
  const payload = {
    session_id:            window._sessionId || "",
    learner_id:            window._learnerId || "",
    mode:                  t.mode,
    tier:                  getUserTier(),
    persona_id:            window._partnerId || window._personaId || "",
    duration_seconds:      Math.max(0, Math.round((Date.now() - _startedAt) / 1000)),
    total_turns:           t.total_turns,
    recovery_uses:         t.recovery_uses,
    successful_recoveries: t.successful_recoveries,
    conversational_recoveries: t.conversational_recoveries,
    successful_conversational_recoveries: t.successful_conversational_recoveries,
    suggestion_clicks:     t.suggestion_clicks,
    card_opens:            t.card_opens,
    display_en_clicks:     t.display_en_clicks,
    display_py_clicks:     t.display_py_clicks,
    hint_clicks:           (window._learnerObs && window._learnerObs.hint_clicks) || 0,
    translation_help_uses: t.translation_help_uses,
    questions_asked:       t.questions_asked,
    depth_responses:       t.depth_responses,
    unmatched_responses:        t.unmatched_responses,
    soft_unmatched_responses:   t.soft_unmatched_responses,
    turbulence_events:          t.turbulence_events || 0,
    engines_used:               Array.from(t.engines_used),

    // ── Session Intelligence capture fields (Phase 0 Slice 1) ─────────────
    // These are optional: the server ignores them when MANDARINOS_SESSION_CAPTURE
    // is not set, and the endpoint must still succeed if they are absent.
    // We send a sanitised copy — only the fields defined in session_record_v1.
    transcript: (conversationTranscript || []).map(function(e) {
      return {
        idx:        e._idx !== undefined ? e._idx : undefined,
        id:         e.id         || undefined,
        role:       e.role       || undefined,
        text_zh:    e.text_zh    || undefined,
        text_en:    e.text_en    || undefined,
        pinyin:     e.pinyin     || undefined,
        frame_id:   e.frame_id   || undefined,
        turn_uid:   e.turn_uid   || undefined,
        created_at: e.created_at || undefined,
      };
    }),
    event_log: (window._siEventLog || []).slice(),
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
    if (_btn) {
      _btn.disabled = false;
      _btn.textContent = "End Session";
      _btn.title = "Save failed — tap to retry";
    }
    return null;
  }

  console.log("[endSession] scorecard result:", result);
  // renderScorecard now includes the ability reflection section at the top.
  // _renderAbilityDashboard() is intentionally NOT called here.
  if (result?.ok) {
    if (_btn) {
      _btn.textContent = "Saved \u2713";
      // Keep disabled — session is over; re-enable is handled by startFresh / page load
    }
    renderScorecard(result);
    // Remove conversation-active so the Start/Frame controls re-surface on both
    // mobile and desktop, and the header becomes visible again on mobile.
    document.body.classList.remove("conversation-active");
    if (_isMobileLayout()) {
      document.body.classList.add("session-ended");
      document.body.classList.add("mobile-panel-open");
      switchRightPanel("session");
      _syncMobileBackdrop();
      _updateMobileFabLabel();
    }
    if (result.progress_snapshot) {
      saveProgressSnapshot(result.progress_snapshot);
      _renderProgressSavedMessage();
      const progressPanel = document.getElementById("rightPanelProgress");
      if (progressPanel && !progressPanel.hidden) renderProgressView();
    }
    // Persist a minimal snapshot so the NEXT session can choose an appropriate objective.
    _saveLastSessionStats({
      total_turns:     _tracker.total_turns     || 0,
      questions_asked: _tracker.questions_asked || 0,
      recovery_uses:   _tracker.recovery_uses   || 0,
      depth_responses: _tracker.depth_responses || 0,
    });
  }
  return result;
}

window.endSession    = endSession;
window.renderScorecard = renderScorecard;
window._resetCurrentSessionState = _resetCurrentSessionState;

// ── iOS / mobile: warn before page unload during active session ───────────────
// Prevents accidental pull-to-refresh or browser-back from discarding an unsaved session.
// Only fires when the body has conversation-active class (set by the conversation start flow).
window.addEventListener("beforeunload", function (e) {
  if (document.body.classList.contains("conversation-active")) {
    e.preventDefault();
    // Chrome requires returnValue to be set; other browsers use the return value.
    e.returnValue = "Your session is in progress. Leaving now will lose your unsaved progress.";
    return e.returnValue;
  }
});


















