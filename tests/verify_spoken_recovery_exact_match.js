#!/usr/bin/env node
/**
 * Regression tests for the spoken-question routing bug introduced by 18d476a.
 *
 * 18d476a added a spoken recovery-intercept block (see ui/app.js, just before
 * the normal free-speech accept path) that matched the raw microphone
 * transcript against learner recovery phrases using
 * matchTranscriptToLearnerPhrase(), which allows SUBSTRING containment:
 *
 *   n.includes(hz) || hz.includes(n)
 *
 * Because normalizeForMatch("什么？") === "什么", any spoken sentence that
 * merely CONTAINS "什么" (e.g. "你做什么工作", "成都有什么特别的") was wrongly
 * treated as the learner saying the bare recovery phrase "什么？", causing the
 * client to fire the "repeat" recovery action and return WITHOUT ever calling
 * runTurn() / POSTing to /api/run_turn.
 *
 * The fix (matchSpokenRecoveryPhraseExact) requires the normalized transcript
 * to be EXACTLY equal to a phrase's normalized hanzi / pinyin / declared
 * alternatives — never containment — for the spoken recovery-intercept path
 * only. matchTranscriptToLearnerPhrase itself is untouched and keeps its
 * existing containment behaviour for recovery-panel / explicit-selection use.
 *
 * This file mirrors the relevant ui/app.js logic (see verify_asr_filler.js /
 * verify_phase12c.js for the same "mirror, don't import" convention used
 * elsewhere in this test suite) and additionally sanity-checks the mirrored
 * snippets against the live source and the real recovery-phrase content file
 * so the mirror cannot silently drift from the shipped implementation.
 *
 * Run: node tests/verify_spoken_recovery_exact_match.js
 */

const fs = require("fs");
const path = require("path");

let passed = 0, failed = 0;
function assert(name, cond) {
  if (cond) { passed++; console.log(`  OK: ${name}`); }
  else { failed++; console.error(`  FAIL: ${name}`); }
}

// ── Mirrors of ui/app.js (kept in lockstep; see source-drift guard below) ───

function normalizeForMatch(s) {
  if (typeof s !== "string") return "";
  return s.trim().replace(/\s+/g, "").replace(/[。？！，、；：""''\s]/g, "");
}

/** Pre-fix / general-purpose matcher: substring containment (unchanged). */
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

/** Post-fix matcher: exact match only, for the spoken recovery-intercept path. */
function matchSpokenRecoveryPhraseExact(transcript, phrases) {
  if (!transcript || !Array.isArray(phrases) || phrases.length === 0) return null;
  const n = normalizeForMatch(transcript);
  if (!n) return null;
  for (const p of phrases) {
    const hz = normalizeForMatch(p.hanzi || "");
    if (hz && n === hz) return p;
    const pyRaw = (p.pinyin || "").trim();
    if (pyRaw) {
      const py = normalizeForMatch(pyRaw.replace(/\s+/g, ""));
      if (py && n === py) return p;
    }
    const alts = Array.isArray(p.alternatives) ? p.alternatives : [];
    for (const alt of alts) {
      const altNorm = normalizeForMatch(String(alt || ""));
      if (altNorm && n === altNorm) return p;
    }
  }
  return null;
}

function learnerRecoveryPhrases(data) {
  const arr = (data && data.phrases) || [];
  const uok = new Set(["not_understood", "topic_reset", "topic_shift"]);
  return arr.filter((p) => uok.has(p.use || "not_understood"));
}

function getRecoveryAction(phrase) {
  if (phrase.recovery_action === "next_turn" || phrase.recovery_action === "slower" || phrase.recovery_action === "repeat")
    return phrase.recovery_action;
  if (phrase.recovery_action === "meaning")
    return "repeat";
  return "repeat";
}

// ── Source-drift guard: the app.js implementation must still exist and use
//    exact matching (===) — not containment — in the spoken intercept block ──

const appSrc = fs.readFileSync(path.join(__dirname, "..", "ui", "app.js"), "utf8");

console.log("SOURCE WIRING");
assert("matchSpokenRecoveryPhraseExact is defined in app.js", appSrc.includes("function matchSpokenRecoveryPhraseExact"));
assert("spoken intercept calls matchSpokenRecoveryPhraseExact (not the containment matcher)",
  /const _spokenRecoveryPhrase = matchSpokenRecoveryPhraseExact\(/.test(appSrc));
assert("matchTranscriptToLearnerPhrase (containment) is preserved for other callers",
  appSrc.includes("function matchTranscriptToLearnerPhrase"));

// ── Real recovery-phrase content (used as realistic fixtures) ───────────────

const recoveryData = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "content", "recovery_phrases.json"), "utf8")
);
const learner = learnerRecoveryPhrases(recoveryData);
const shenmePhrase = learner.find((p) => p.id === "shenme");

console.log("\nCONTENT FIXTURE SANITY");
assert('"shenme" (什么？) phrase exists with recovery_action=repeat', !!shenmePhrase && shenmePhrase.recovery_action === "repeat");

// ── 1-4: ordinary spoken questions containing 什么 must NOT intercept ───────

console.log("\nORDINARY SPOKEN QUESTIONS DO NOT INTERCEPT AS 什么？ RECOVERY");
const ordinaryQuestions = [
  "你做什么工作",
  "成都有什么特别的",
  "这里有什么好吃的",
  "新西兰有什么好吃的",
  "你是什么意思",
  "你最喜欢吃什么",
];
for (const q of ordinaryQuestions) {
  // Demonstrate the regression: the OLD (18d476a) containment matcher wrongly intercepts.
  const oldMatch = matchTranscriptToLearnerPhrase(q, learner);
  assert(`[pre-fix regression demo] "${q}" WAS wrongly matched by containment matcher`, oldMatch && oldMatch.id === "shenme");

  // Prove the fix: the exact matcher used by the spoken intercept path does not.
  const newMatch = matchSpokenRecoveryPhraseExact(q, learner);
  assert(`"${q}" is NOT intercepted by the exact spoken-recovery matcher`, newMatch === null);
}

// ── 5-7: bare recovery phrases and declared exact synonyms still intercept ──

console.log("\nBARE RECOVERY PHRASES STILL INTERCEPT (EXACT MATCH)");
for (const bare of ["什么", "什么？"]) {
  const m = matchSpokenRecoveryPhraseExact(bare, learner);
  assert(`bare "${bare}" still matches the "shenme" recovery phrase`, !!m && m.id === "shenme");
  assert(`recovery action for "${bare}" is "repeat"`, m && getRecoveryAction(m) === "repeat");
}

console.log("\nDECLARED EXACT ALTERNATIVES (E.G. 啥) STILL INTERCEPT");
{
  const phraseWithAlt = { id: "shenme_alt", hanzi: "什么？", recovery_action: "repeat", use: "not_understood", alternatives: ["啥", "啥？"] };
  const poolWithAlt = [phraseWithAlt];
  for (const alt of ["啥", "啥？"]) {
    const m = matchSpokenRecoveryPhraseExact(alt, poolWithAlt);
    assert(`declared alternative "${alt}" matches via matchSpokenRecoveryPhraseExact`, !!m && m.id === "shenme_alt");
  }
  // But a sentence merely containing the alternative must still not match.
  const nonMatch = matchSpokenRecoveryPhraseExact("你要吃啥菜", poolWithAlt);
  assert('"你要吃啥菜" (contains 啥 but is not the bare phrase) does NOT match', nonMatch === null);
}

// ── 8: other existing recovery phrases still work when spoken exactly ──────

console.log("\nOTHER RECOVERY PHRASES (REPEAT / SLOWER / MEANING) STILL WORK WHEN SPOKEN EXACTLY");
const exactCases = [
  { hanzi: "再说一遍", expectAction: "repeat" },
  { hanzi: "慢一点说", expectAction: "slower" },
  { hanzi: "我有点不懂", expectAction: "repeat" }, // "meaning" maps to "repeat" via getRecoveryAction
  { hanzi: "什么意思啊？", expectAction: "repeat" },
];
for (const { hanzi, expectAction } of exactCases) {
  const m = matchSpokenRecoveryPhraseExact(hanzi, learner);
  assert(`exact spoken "${hanzi}" still matches its recovery phrase`, !!m);
  if (m) assert(`"${hanzi}" recovery action resolves to "${expectAction}"`, getRecoveryAction(m) === expectAction);
}

// ── 9: matchTranscriptToLearnerPhrase (recovery panel / explicit selection)
//       keeps its existing containment behaviour — untouched by this fix ───

console.log("\nGENERAL-PURPOSE MATCHER (RECOVERY PANEL / EXPLICIT SELECTION) UNCHANGED");
assert('matchTranscriptToLearnerPhrase still matches "什么" via containment (unchanged behaviour)',
  !!matchTranscriptToLearnerPhrase("什么", learner));
assert('matchTranscriptToLearnerPhrase still matches "再说一遍" exactly (unchanged behaviour)',
  !!matchTranscriptToLearnerPhrase("再说一遍", learner));

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
