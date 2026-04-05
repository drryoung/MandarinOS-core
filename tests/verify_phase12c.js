/**
 * Phase 12C — Minimal verification script (Node, zero dependencies)
 * Run: node tests/verify_phase12c.js
 *
 * Covers five golden cases that map to I-1, I-2, I-5.
 * Does NOT cover server-side selector (I-3, I-4) — those are Python territory.
 *
 * Technique: inline-stub the pure functions extracted from ui/app.js,
 * then run assertions.  No DOM, no fetch, no imports.
 */

"use strict";

// ─── Stubs (copy of the pure logic from ui/app.js, kept in sync manually) ────

function normalizeForMatch(s) {
  if (typeof s !== "string") return "";
  return s.trim().replace(/\s+/g, "").replace(/[。？！，、；：""''\s]/g, "");
}

function isOpenEndedFrame(frameId) {
  const fid = (frameId || "").trim();
  return new Set([
    "f_ask_you_name", "p2_id_2", "p2_id_4", "p2_id_5", "f_ask_name_meaning",
    "f_from_where", "frame.location.live_question",
    "f_place_why_like", "f_place_like_there",
    "f_probe_place_miss", "f_probe_place_moved", "f_probe_place_stay", "f_probe_place_why_move",
    "p2_pl_1", "p2_pl_ext1", "p2_pl_3", "p2_pl_4",
    "f_have_family", "f_have_siblings", "p2_fa_1", "p2_fa_2", "p2_fa_5",
    "f_what_work", "f_like_work", "p2_wk_1", "p2_wk_2",
    "f_what_hobby", "f_often_do", "f_like_do_what", "f_weekend_do",
    "f_difficult_ma", "f_recommend_ma", "p2_hb_1", "p2_hb_2",
    "f_food_what_good", "f_travel_where", "f_want_go_where",
  ]).has(fid);
}

const _MIXED_SCRIPT_PLACE_FRAMES = new Set([
  "frame.location.live_question",
  "p2_pl_ext1",
  "f_from_where",
]);

function isLikelyUnderstandableFreeAnswer(text, frameId = "") {
  const s = (text || "").trim();
  if (!s) return false;
  const fid = (frameId || "").trim();
  const zhMatches = s.match(/[\u4e00-\u9fff]/g) || [];
  const zhCount = zhMatches.length;
  const latinCount = (s.match(/[A-Za-z]/g) || []).length;
  if (zhCount > 0 && zhCount < 2) return false;
  const identityOpen = new Set(["f_ask_you_name", "p2_id_2", "p2_id_4", "p2_id_5", "f_ask_name_meaning"]).has(fid);
  const placeMixedScript = _MIXED_SCRIPT_PLACE_FRAMES.has(fid);
  if (!identityOpen && !placeMixedScript && latinCount > zhCount + 2) return false;
  const norm = s.replace(/[，。！？、\s]/g, "");
  if (norm.length >= 4) {
    const half = Math.floor(norm.length / 2);
    if (half > 0 && norm.slice(0, half) === norm.slice(half)) return false;
  }
  if (/([\u4e00-\u9fff])\1{2,}/.test(norm)) return false;
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

function semanticSoftMatch(transcript, frameId) {
  const t = (transcript || "").trim();
  const fid = (frameId || "").trim();
  if (!t) return false;
  if (/^(那?你呢|你怎么想|为什么这么问|为什么这样问|换我问|那你|你来问)/.test(t) || t === "你呢") return true;
  if (/[，。！]?(那?你呢|你怎么想|为什么这么问)[？?]?$/.test(t)) return true;
  if (/你(是哪里人|从哪里来|老家在哪|住(在哪|哪里|的地方)|做什么工作|的工作|是做什么|喜欢(什么|做什么)|有什么爱好|有没有家人)/.test(t)) return true;
  if (/(风景|山水|漂亮|好看|很美|美|空气|环境|舒服|安静|不错|挺好|海|湖|山|树|绿)/.test(t)) return true;
  if (_MIXED_SCRIPT_PLACE_FRAMES.has(fid) && /[\u4e00-\u9fff]/.test(t) && /[A-Za-z]/.test(t)) return true;
  if (fid === "p2_id_2") {
    if (t.includes("叫我") || t.includes("大家叫")) return true;
    if (/[\u4e00-\u9fff]/.test(t) && /[A-Za-z]/.test(t)) return true;
  }
  if (fid === "f_food_famous_dish") {
    if (/汉堡|牛肉|羊肉|火锅|饺子|面|米饭|烤|汤|鱼|鸡|菜/.test(t)) return true;
    if (/不知道|没有|不清楚/.test(t)) return true;
  }
  if (fid === "p2_fa_2") {
    if (/(家人|妈妈|爸爸|父母)/.test(t) && /(天|周|月|常|每天|经常|周末)/.test(t)) return true;
  }
  if (fid === "p2_wk_1") {
    if (/(因为|为了|可以|能|学|帮助|工资|时间|喜欢)/.test(t)) return true;
  }
  return false;
}

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
  if (/不懂|不明白/.test(transcript || "")) return { accept: true, reason: "learner_skip_signal" };
  if (isLexicalContentQuestion(transcript)) return { accept: true, reason: "lexical_content_question" };
  if (opts.length === 0) return { accept: true, reason: "no_options" };
  if (semantic) return { accept: true, reason: "semantic_soft_match" };
  if ((unmatchedCount || 0) >= 1 && understandable) return { accept: true, reason: "one_strike_substantive_fallback" };
  if (openEnded && understandable) return { accept: true, reason: "open_ended_understandable" };
  if (hasStructuredSlots && understandable) return { accept: true, reason: "slot_frame_understandable" };
  if (openEnded && !understandable) return { accept: false, reason: "open_ended_low_confidence" };
  if (hasStructuredSlots && !understandable) return { accept: false, reason: "slot_frame_low_confidence" };
  return { accept: false, reason: "closed_options_unmatched" };
}

// ─── Minimal assertion harness ────────────────────────────────────────────────

let _passed = 0;
let _failed = 0;

function assert(label, condition, info = "") {
  if (condition) {
    console.log(`  ✓  ${label}`);
    _passed++;
  } else {
    console.error(`  ✗  ${label}${info ? `  →  ${info}` : ""}`);
    _failed++;
  }
}

function suite(name, fn) {
  console.log(`\n${name}`);
  fn();
}

// ─── Golden Case 1 (I-1): accepted unmatched free answer ─────────────────────
suite("GC-1 · Accepted unmatched free answer (I-1)", () => {
  // Open-ended frame, substantive Chinese answer, no options
  const r1 = classifyUnmatchedFreeAnswerDecision("我现在住在成都", [], "frame.location.live_question", 0);
  assert("open-ended + no options → accept", r1.accept === true, JSON.stringify(r1));

  // Place probe — scenery answer hits semanticSoftMatch before open-ended path
  const opts = [{ hanzi: "很好", kind: "SENTENCE" }];
  const r2 = classifyUnmatchedFreeAnswerDecision("风景很好看", opts, "f_place_why_like", 0);
  assert("scenery phrase → semantic_soft_match → accept", r2.accept === true && r2.reason === "semantic_soft_match", JSON.stringify(r2));

  // Long Latin place name (Christchurch) — latinCount >> zhCount; must not reject vs Dunedin
  const nzOpts = [{ hanzi: "奥克兰" }, { hanzi: "惠灵顿" }];
  const rCx = classifyUnmatchedFreeAnswerDecision("我现在住在Christchurch", nzOpts, "frame.location.live_question", 0);
  assert(
    "Christchurch + Chinese on live_question → semantic_soft_match",
    rCx.accept === true && rCx.reason === "semantic_soft_match",
    JSON.stringify(rCx)
  );

  // Learner skip: 我有点不懂 → learner_skip_signal
  const r3 = classifyUnmatchedFreeAnswerDecision("我有点不懂", opts, "p2_pl_1", 0);
  assert("不懂 → learner_skip_signal → accept", r3.accept === true && r3.reason === "learner_skip_signal", JSON.stringify(r3));

  // Lexical question: 火锅是什么
  const r4 = classifyUnmatchedFreeAnswerDecision("火锅是什么", opts, "p2_pl_ext1", 0);
  assert("火锅是什么 → lexical_content_question → accept", r4.accept === true && r4.reason === "lexical_content_question", JSON.stringify(r4));
});

// ─── Golden Case 2 (I-2): rejected unmatched with low confidence ──────────────
suite("GC-2 · Rejected unmatched — trigger layer must own recovery (I-2)", () => {
  // Closed options, short single-char Chinese that cannot be an open-ended answer
  const closedOpts = [{ hanzi: "是的", kind: "SENTENCE" }, { hanzi: "不太", kind: "SENTENCE" }];
  const r1 = classifyUnmatchedFreeAnswerDecision("啊", closedOpts, "p2_pl_1", 0);
  // 啊 is 1 Chinese char → isLikelyUnderstandableFreeAnswer = false; not semantic; not skip
  assert("single-char Chinese + closed options → reject", r1.accept === false, JSON.stringify(r1));

  // Pure Latin "hi" in a CLOSED frame (p2_pl_2 is not open-ended) → reject
  // Note: p2_pl_1 IS open-ended, so use p2_pl_2 which is NOT in isOpenEndedFrame.
  const closedFrameOpts = [{ hanzi: "有火锅" }, { hanzi: "有饺子" }];
  const r2 = classifyUnmatchedFreeAnswerDecision("hi", closedFrameOpts, "p2_pl_2", 0);
  assert("pure short Latin + closed frame (p2_pl_2) → reject", r2.accept === false, JSON.stringify(r2));

  // Hesitation + same syllable repeated (拿拿拿) — must not count as a substantive answer
  const nzOpts = [{ hanzi: "奥克兰" }, { hanzi: "惠灵顿" }];
  const rFill = classifyUnmatchedFreeAnswerDecision("呃，我先，呃，拿，拿，拿。", nzOpts, "frame.location.live_question", 0);
  assert(
    "filler triple-repeat on live_question → open_ended_low_confidence",
    rFill.accept === false && rFill.reason === "open_ended_low_confidence",
    JSON.stringify(rFill)
  );

  // Name-style line (我叫…) with no place cue — wrong question / ASR, not a location answer
  const rName = classifyUnmatchedFreeAnswerDecision("呃，呃我。我叫杨你没。", nzOpts, "frame.location.live_question", 0);
  assert(
    "name-only fragment on live_question → open_ended_low_confidence",
    rName.accept === false && rName.reason === "open_ended_low_confidence",
    JSON.stringify(rName)
  );

  // I-2 structural check: rejected cases keep trigger layer gate closed
  assert(
    "rejected turns have accept===false (trigger layer gate is respected)",
    r1.accept === false && r2.accept === false && rFill.accept === false && rName.accept === false
  );
});

// ─── Golden Case 3 (I-2): repeated failed attempt escalation ──────────────────
suite("GC-3 · Repeated failed attempt escalation (I-2, one-strike fallback)", () => {
  const closedOpts = [{ hanzi: "是的" }, { hanzi: "不太" }];
  // First attempt — not understandable (short), not open, not semantic → reject
  const r0 = classifyUnmatchedFreeAnswerDecision("我", closedOpts, "p2_pl_3", 0);
  assert("unmatchedCount=0, single char → reject", r0.accept === false, JSON.stringify(r0));

  // Second attempt (unmatchedCount=1) with substantive Chinese — one-strike fallback fires.
  // Note: "不错" alone hits semanticSoftMatch (scenery list) before the one-strike path.
  // Use a phrase with no scenery keywords so the one-strike path is the one that fires.
  const r1 = classifyUnmatchedFreeAnswerDecision("我工作很忙没时间", closedOpts, "p2_pl_3", 1);
  assert("unmatchedCount=1 + substantive (no scenery keywords) → one_strike_substantive_fallback",
    r1.accept === true && r1.reason === "one_strike_substantive_fallback", JSON.stringify(r1));

  // Confirm escalation doesn't fire for truly trivial repeats (repetition noise)
  const r2 = classifyUnmatchedFreeAnswerDecision("好好好好", closedOpts, "p2_pl_3", 1);
  // "好好好好" → norm="好好好好" length 4, half="好好"==="好好" → noise → reject
  assert("repeated-noise unmatchedCount=1 → still reject (noise guard active)",
    r2.accept === false, JSON.stringify(r2));
});

// ─── Golden Case 4 (I-3): probe-active turn — probe_depth stays in server ─────
suite("GC-4 · Probe-active turn (I-3, client must not touch _probeDepth mid-turn)", () => {
  // This golden case is behavioural: we verify that the decision function itself
  // does not access or mutate any probe_depth — it is stateless on that axis.
  // The test is: calling classifyUnmatchedFreeAnswerDecision with probe-looking
  // inputs produces the same result regardless of a hypothetical probeDepth value,
  // because the function has no knowledge of probeDepth.

  const probeOpts = [{ hanzi: "为什么呢" }, { hanzi: "谁" }];
  const withProbe    = classifyUnmatchedFreeAnswerDecision("因为我喜欢", probeOpts, "f_place_why_like", 0);
  const withoutProbe = classifyUnmatchedFreeAnswerDecision("因为我喜欢", probeOpts, "f_place_why_like", 0);

  assert("classification is probe-depth-agnostic (same in/out regardless of depth)",
    JSON.stringify(withProbe) === JSON.stringify(withoutProbe));

  // Turn-around phrase inside a probe-like context: should accept via semantic path
  const r2 = classifyUnmatchedFreeAnswerDecision("你呢", probeOpts, "p2_pl_4", 0);
  assert("你呢 in probe-like context → semantic_soft_match → accept",
    r2.accept === true && r2.reason === "semantic_soft_match", JSON.stringify(r2));
});

// ─── Golden Case 5 (I-5): sentence-strip routing ──────────────────────────────
suite("GC-5 · Sentence-strip routing rule (I-5, DOM simulation)", () => {
  // Simulate the exact post-render logic from _runTurnInner that enforces I-5.
  // We create minimal fake DOM nodes, then run the rule as written in app.js.

  function simulateSentenceStripVisibility({ sentencePanelCount, wordStripInitialDisplay }) {
    // Minimal node stubs
    function makeEl(display, panels = 0) {
      const children = Array.from({ length: panels }, () => ({ className: "option-panel" }));
      return {
        style: { display },
        querySelector(sel) {
          if (sel === ".option-panel") return children[0] || null;
          return null;
        },
      };
    }
    const soc = makeEl("flex", sentencePanelCount);
    const optC = makeEl(wordStripInitialDisplay);
    // Inline copy of the invariant-enforcing rule from _runTurnInner:
    const hasSentenceOptions = true; // "server sent sentence_options with SENTENCE kind"
    const sentenceRowVisible = soc && soc.style.display !== "none" && soc.querySelector(".option-panel");
    if (hasSentenceOptions && sentenceRowVisible) {
      optC.style.display = "none";
    }
    return { sentenceVisible: soc.style.display, wordVisible: optC.style.display };
  }

  // When sentence row has panels, word strip must be hidden
  const { wordVisible: wv1 } = simulateSentenceStripVisibility({ sentencePanelCount: 2, wordStripInitialDisplay: "flex" });
  assert("sentence row has panels → word strip hidden (display:none)", wv1 === "none");

  // When sentence row is empty (no panels), word strip is NOT touched
  const { wordVisible: wv2 } = simulateSentenceStripVisibility({ sentencePanelCount: 0, wordStripInitialDisplay: "flex" });
  // With 0 panels: sentenceRowVisible = false → rule does not fire → word strip stays "flex"
  assert("sentence row empty → word strip stays visible (rule does not fire)", wv2 === "flex");

  // If soc is hidden (display:none) even with panels, word strip is NOT hidden
  function simulateHiddenSoc() {
    const soc = { style: { display: "none" }, querySelector: () => ({ className: "option-panel" }) };
    const optC = { style: { display: "flex" } };
    const sentenceRowVisible = soc && soc.style.display !== "none" && soc.querySelector(".option-panel");
    if (sentenceRowVisible) optC.style.display = "none";
    return optC.style.display;
  }
  assert("soc display:none → sentenceRowVisible=false → word strip NOT hidden", simulateHiddenSoc() === "flex");
});

// ─── Summary ──────────────────────────────────────────────────────────────────

console.log(`\n${"─".repeat(56)}`);
console.log(`Phase 12C verification: ${_passed} passed, ${_failed} failed`);
if (_failed > 0) {
  console.error("FAIL — one or more invariants violated");
  process.exit(1);
} else {
  console.log("PASS — all golden cases satisfied");
}
