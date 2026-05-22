#!/usr/bin/env node
/**
 * Regression checks for ASR filler suppression (mirrors ui/app.js logic).
 * Run: node tests/verify_asr_filler.js
 */

const _DURATION_ANSWER_PAT = /\d+\s*(年|天|个月|月|周|星期|小时|分钟|岁)/;

const _FILLER_CHAR_SET = new Set(["嗯", "啊", "呃", "哦", "喔", "哎", "诶", "呀", "唉"]);
const _DISCOURSE_FRAGMENT_FILLERS = new Set(["这个", "那个", "就是"]);

function normalizeForMatch(s) {
  if (typeof s !== "string") return "";
  return s.trim().replace(/\s+/g, "").replace(/[。？！，、；：""''\s]/g, "");
}

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

const mockWindow = {
  _lastSemanticClarifyText: "",
  _lastPartnerTurnText: "",
  _lastPartnerFrameText: "",
};

function _isAffirmationAfterParaphrase(transcript) {
  const t = (transcript || "").trim();
  if (!t) return false;
  const prevWasParaphrase =
    mockWindow._lastSemanticClarifyText.includes("你是说") ||
    mockWindow._lastPartnerTurnText.includes("你是说") ||
    mockWindow._lastPartnerFrameText.includes("你是说");
  if (!prevWasParaphrase) return false;
  return /^(对|是|嗯|好|对的|是的|没错|对啊|嗯嗯|对对|嗯呢)$/.test(t.replace(/[。！？,，\s]/g, ""));
}

function _isTurnAroundPhrase(transcript) {
  const t = (transcript || "").trim();
  if (!t) return false;
  if (/^(那?你呢|你怎么想)/.test(t) || t === "你呢") return true;
  return false;
}

function _detectSemanticCategory(text) {
  const t = (text || "").trim();
  if (/我叫|名字/.test(t)) return "name";
  if (/退休/.test(t)) return "work_status";
  if (/北京|上海|香港|住在/.test(t)) return "location";
  return null;
}

function _isSufficientLinguisticSignal(transcript) {
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

function classifyFillerDecision(transcript, opts = [{ hanzi: "北京" }], frameId = "f_from_where") {
  if (/不懂|不明白/.test(transcript || "")) return { accept: true, reason: "learner_skip_signal" };
  if (/你/.test(transcript || "") && /吗/.test(transcript || "")) {
    return { accept: true, reason: "learner_counter_question" };
  }
  if (!_isSufficientLinguisticSignal(transcript)) {
    return { accept: false, reason: "insufficient_linguistic_signal", fail_level: "hard" };
  }
  if (opts.length === 0) return { accept: true, reason: "no_options" };
  if (isOpenEnded(frameId)) return { accept: true, reason: "open_ended_understandable" };
  return { accept: true, reason: "semantic_soft_match" };
}

function isOpenEnded(frameId) {
  return frameId === "f_from_where" || frameId === "frame.location.live_question";
}

let passed = 0;
let failed = 0;

function assert(name, cond) {
  if (cond) {
    passed++;
    console.log(`  PASS ${name}`);
  } else {
    failed++;
    console.log(`  FAIL ${name}`);
  }
}

console.log("FILLER REJECTION");
for (const t of ["嗯嗯", "啊啊", "嗯啊", "嗯嗯嗯嗯", "呃"]) {
  assert(`${t} incomplete`, isIncompleteLearnerUtterance(t));
  assert(`${t} insufficient signal`, !_isSufficientLinguisticSignal(t));
  const d = classifyFillerDecision(t);
  assert(`${t} classify reject`, !d.accept && d.reason === "insufficient_linguistic_signal");
}

console.log("VALID SHORT SIGNALS");
for (const t of ["北京", "上海", "香港"]) {
  assert(`${t} not incomplete`, !isIncompleteLearnerUtterance(t));
  assert(`${t} sufficient signal`, _isSufficientLinguisticSignal(t));
  const d = classifyFillerDecision(t);
  assert(`${t} classify accept`, d.accept);
}

console.log("VALID MIXED SIGNALS");
for (const t of ["嗯北京", "嗯我住在北京"]) {
  assert(`${t} not incomplete`, !isIncompleteLearnerUtterance(t));
  assert(`${t} sufficient signal`, _isSufficientLinguisticSignal(t));
  const d = classifyFillerDecision(t);
  assert(`${t} classify accept`, d.accept);
}

console.log("VALID SPECIAL PATHS");
assert("我不懂 skip", classifyFillerDecision("我不懂").accept);
assert("你呢 turn-around", _isSufficientLinguisticSignal("你呢"));
assert("你呢 accept", classifyFillerDecision("你呢").accept);
assert("Raymond latin", _isSufficientLinguisticSignal("Raymond"));
assert("差不多五年了 duration", _isSufficientLinguisticSignal("差不多五年了"));

mockWindow._lastPartnerTurnText = "你是说：北京吗？";
assert("对对对 after paraphrase", _isSufficientLinguisticSignal("对对对"));
assert("嗯嗯 after paraphrase affirm", _isSufficientLinguisticSignal("嗯嗯"));
mockWindow._lastPartnerTurnText = "";

console.log("SILENCE EXTENSION WIRING");
const src = require("fs").readFileSync(require("path").join(__dirname, "..", "ui", "app.js"), "utf8");
assert("fillerExtendFired guard", src.includes("fillerExtendFired"));
assert("SPEECH_FILLER_EXTEND_MS", src.includes("SPEECH_FILLER_EXTEND_MS"));
assert("Still listening", src.includes("Still listening"));

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
