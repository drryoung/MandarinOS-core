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

// Mirrors production _detectSemanticCategory (stub — expand in sync with app.js).
function normalizeConversationalFillers(t) {
  // Minimal stub: strip leading filler words.
  return (t || "").replace(/^(啊|嗯|哦|呃|哎|诶|好|对|那|那个|这个|就是|然后|反正)\s*/g, "").trim();
}

function _detectSemanticCategory(text) {
  const t = normalizeConversationalFillers((text || "").trim());
  if (!t) return null;
  if (/我叫|名字|英文名/.test(t)) return "name";
  if (/吃|喜欢吃|牛肉|羊肉|好吃|食物/.test(t)) return "food";
  if (/身体|健康|好多了|好一点|不好|生病|康复/.test(t)) return "family_health";
  if (/爸爸|妈妈|太太|家人|老婆|父母|家里|女儿|儿子|孩子/.test(t)) return "family";
  if (/退休|以前.*工作|做.*工作/.test(t)) return "work_status";
  if (/是老师|教书|教学|在学校.*工作/.test(t)) return "work_teacher";
  if (/是(工程师|医生|护士|会计|律师|程序员|厨师|警察|翻译|教授)/.test(t)) return "work_occupation";
  if (/去过|没去过|曾经去|以前去/.test(t)) return "travel_experience";
  if (/很远|超远|坐飞机|乘飞机|小时.*飞机|飞机.*小时/.test(t)) return "distance";
  if (/大学|学院|学校/.test(t)) return "education";
  if (/住在|搬到|来自/.test(t)) return "location";
  if (/北京|上海|香港|成都|西安|重庆|广州|深圳|奥克兰|惠灵顿|新西兰|澳大利亚/.test(t)) return "location";
  if (/新西兰人|澳大利亚人|中国人|英国人|美国人|加拿大人|日本人|韩国人|法国人|德国人|新加坡人|南非人|意大利人|西班牙人|台湾人|香港人/.test(t)) return "nationality";
  if (/我(来自|老家在|出生在|是从|从小在)/.test(t)) return "nationality";
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

function isOpenEnded(frameId) {
  return new Set([
    "f_from_where", "frame.location.live_question", "f_live_where", "f_home_where",
    "f_place_why_like", "f_place_like_there", "f_probe_place_miss",
  ]).has(frameId);
}

/**
 * Mirrors the post-0d2b423 + threshold-adjustment classifyUnmatchedFreeAnswerDecision.
 * Options deliberately kept as a simple closed set so the semantic-category-match path
 * is exercised for the closed-frame case.
 */
function classifyFillerDecision(transcript, opts = [{ hanzi: "北京" }], frameId = "f_from_where", unmatchedCount = 0) {
  if (/不懂|不明白/.test(transcript || "")) return { accept: true, reason: "learner_skip_signal" };
  if (/你/.test(transcript || "") && /吗/.test(transcript || "")) {
    return { accept: true, reason: "learner_counter_question" };
  }
  if (!_isSufficientLinguisticSignal(transcript)) {
    return { accept: false, reason: "insufficient_linguistic_signal", fail_level: "hard" };
  }
  if (opts.length === 0) return { accept: true, reason: "no_options" };
  // semantic_category_match: accept first-attempt categorized answers on any frame.
  if (_detectSemanticCategory(transcript)) return { accept: true, reason: "semantic_category_match" };
  if (isOpenEnded(frameId)) return { accept: true, reason: "open_ended_understandable" };
  if (unmatchedCount >= 1) return { accept: true, reason: "one_strike_substantive_fallback" };
  return { accept: false, reason: "closed_options_unmatched", fail_level: "soft" };
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

// ── Regression: filler still rejected after threshold adjustment ──────────────
console.log("FILLER STILL REJECTED AFTER THRESHOLD ADJUSTMENT");
for (const t of ["嗯嗯", "啊啊", "嗯嗯嗯", "哦哦", "嗯啊", "就是", "这个", "那个"]) {
  const d = classifyFillerDecision(t, [{ hanzi: "北京" }], "f_from_where");
  assert(`${t} still rejected`, !d.accept);
  assert(`${t} fail_level hard`, d.fail_level === "hard");
}
// Pure filler on closed non-open-ended frame also rejected
for (const t of ["嗯嗯", "啊啊"]) {
  const d = classifyFillerDecision(t, [{ hanzi: "北京" }], "f_what_work");
  assert(`${t} rejected on closed work frame`, !d.accept);
}

// ── Regression: substantive imperfect spoken Mandarin accepted first attempt ──
console.log("SUBSTANTIVE SPOKEN ACCEPTED ON FIRST ATTEMPT");

// Location / origin statements — now caught by semantic_category_match
for (const t of [
  "我来自新西兰",
  "我老家在成都",
  "我出生在北京",
  "我从小在上海",
  "我住在奥克兰",
]) {
  const d = classifyFillerDecision(t, [{ hanzi: "北京" }], "f_what_work", 0);
  assert(`${t} accepted on closed frame first attempt`, d.accept);
  assert(`${t} reason semantic_category_match`, d.reason === "semantic_category_match");
}

// Extended nationality list
for (const t of [
  "我是法国人",
  "我是德国人",
  "我是新加坡人",
  "我是南非人",
  "我是意大利人",
  "我是台湾人",
]) {
  assert(`${t} has semantic category`, !!_detectSemanticCategory(t));
  const d = classifyFillerDecision(t, [{ hanzi: "北京" }], "f_what_work", 0);
  assert(`${t} accepted on closed frame`, d.accept);
}

// Work occupation answers
for (const t of ["我是工程师", "我是医生", "我是护士", "我是翻译", "我是教授"]) {
  assert(`${t} category work_occupation`, _detectSemanticCategory(t) === "work_occupation");
  const d = classifyFillerDecision(t, [{ hanzi: "老师" }], "f_what_work", 0);
  assert(`${t} accepted on work frame first attempt`, d.accept);
}

// Travel experience answers
for (const t of ["我去过北京", "我没去过日本", "以前去过成都"]) {
  assert(`${t} category travel_experience`, _detectSemanticCategory(t) === "travel_experience");
  const d = classifyFillerDecision(t, [{ hanzi: "是的" }], "f_travel_where", 0);
  assert(`${t} accepted on travel frame first attempt`, d.accept);
}

// Filler-prefixed substantive answers accepted (fillers normalised before category check)
for (const t of ["啊我来自新西兰", "嗯我是工程师", "就是我去过成都"]) {
  assert(`${t} passes gate`, _isSufficientLinguisticSignal(t));
  assert(`${t} has semantic category`, !!_detectSemanticCategory(t));
  const d = classifyFillerDecision(t, [{ hanzi: "北京" }], "f_from_where", 0);
  assert(`${t} accepted`, d.accept);
}

// ── Edge: 嗯嗯 still rejected even after filler normalisation ─────────────────
console.log("FILLER STILL REJECTED AFTER CATEGORY NORMALISATION");
assert("嗯嗯 category null", _detectSemanticCategory("嗯嗯") === null);
assert("啊啊 category null", _detectSemanticCategory("啊啊") === null);
assert("就是 category null", _detectSemanticCategory("就是") === null);

// ── Confirm original boundary: open-ended frame, understandable, first attempt ──
console.log("OPEN-ENDED FRAME FIRST-ATTEMPT STILL ACCEPTED");
for (const t of ["重庆有什么好吃的", "我不喜欢那里", "成都的生活很好"]) {
  const d = classifyFillerDecision(t, [{ hanzi: "是的" }], "f_from_where", 0);
  assert(`${t} accepted on open-ended frame`, d.accept);
}

// ── Confirm no false positives: on closed frame, non-categorized answer still goes to repair ──
console.log("NON-CATEGORIZED ON CLOSED FRAME GOES TO REPAIR THEN ACCEPT");
{
  const t = "哦对";  // real-ish but no semantic category, 2 chars, non-filler
  const d0 = classifyFillerDecision(t, [{ hanzi: "北京" }], "f_what_work", 0);
  assert("哦对 first attempt closed frame rejected", !d0.accept);
  const d1 = classifyFillerDecision(t, [{ hanzi: "北京" }], "f_what_work", 1);
  assert("哦对 second attempt accepted", d1.accept);
}

console.log("SILENCE EXTENSION WIRING");
const src = require("fs").readFileSync(require("path").join(__dirname, "..", "ui", "app.js"), "utf8");
assert("fillerExtendFired guard", src.includes("fillerExtendFired"));
assert("SPEECH_FILLER_EXTEND_MS", src.includes("SPEECH_FILLER_EXTEND_MS"));
// "Still listening" log was removed in 8be3aee; check the filler-extend timeout log instead.
assert("filler extend timeout log", src.includes("filler extend timeout fired"));

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
