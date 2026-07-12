#!/usr/bin/env node
/**
 * Regression coverage for the E4 client-merge defect fixed in ui/app.js:
 *
 *   The server correctly writes response["state_update"]["current_engine"]
 *   (an E4/direction-stub handoff), but the primary Pattern-A response
 *   handler `_runTurnInner()` previously set window._currentEngineId only
 *   from top-level data.engine_id — the engine of the CURRENT frame — and
 *   never consumed the handoff. So the next ordinary ("Next") request kept
 *   sending the OLD engine, and E4 had no end-to-end effect on the primary
 *   conversation path (runMirrorTurn's separate Pattern-B merge already
 *   consumed the field, but does not repair the ordinary path).
 *
 * The fix introduces a small pure helper, `_resolveNextEngineId(frameEngineId,
 * stateUpdate)`, used by `_runTurnInner()` AFTER all current-response
 * bookkeeping/rendering/diagnostics, to decide what window._currentEngineId
 * should become for the NEXT request. It never changes what engine the
 * CURRENT frame is attributed to.
 *
 * Test mechanism
 * ──────────────
 * This repository has no browser/DOM/Jest harness (ui/app.js is a single
 * top-level script with module-scope DOM/window side effects, not an
 * importable module), so per the "mirror, don't import" convention used by
 * the other tests in this file's family (see verify_asr_filler.js,
 * verify_spoken_recovery_exact_match.js), the strongest available mechanism
 * is used instead: `tests/_load_app_js_helper.js` slices the REAL,
 * VERBATIM `_resolveNextEngineId` source out of ui/app.js and executes those
 * literal characters — it is not a hand-written mirror of the merge logic,
 * so it cannot silently drift from what ships. Wiring/position within
 * `_runTurnInner()` is proven with static source-position assertions (no
 * DOM/fetch stubbing available to actually execute the surrounding
 * multi-thousand-line function from plain Node).
 *
 * Run: node tests/verify_e4_client_handoff.js
 */

const { readAppJsSource, extractFunctionSource, loadRealFunction } = require("./_load_app_js_helper");

let passed = 0, failed = 0;
function assert(name, cond) {
  if (cond) { passed++; console.log(`  OK: ${name}`); }
  else { failed++; console.error(`  FAIL: ${name}`); }
}

const appSrc = readAppJsSource();

// ── 1. Load the REAL helper (verbatim source, not a mirror) ─────────────────

console.log("HELPER SOURCE LOCATION");
const helperSrc = extractFunctionSource(appSrc, "_resolveNextEngineId");
assert("_resolveNextEngineId is defined in ui/app.js", !!helperSrc);

const _resolveNextEngineId = loadRealFunction("_resolveNextEngineId", { src: appSrc });
assert("_resolveNextEngineId loaded from real source is callable", typeof _resolveNextEngineId === "function");

// ── 2. Essential scenario: engine_id="identity", state_update.current_engine="place" ─

console.log("\nESSENTIAL SCENARIO — engine_id=\"identity\", state_update.current_engine=\"place\"");
{
  const frameEngineId = "identity"; // data.engine_id — the CURRENT frame's engine
  const stateUpdate = { current_engine: "place" };
  const nextEngine = _resolveNextEngineId(frameEngineId, stateUpdate);
  assert('resolves next-request engine to "place"', nextEngine === "place");
  assert('does NOT mutate/relabel the current-frame engine value passed in',
    frameEngineId === "identity");
}

// ── 3. No handoff present → existing data.engine_id behaviour retained ─────

console.log("\nNO HANDOFF PRESENT — falls back to data.engine_id");
assert("state_update = {} → returns frameEngineId unchanged",
  _resolveNextEngineId("identity", {}) === "identity");
assert("state_update = undefined → returns frameEngineId unchanged",
  _resolveNextEngineId("identity", undefined) === "identity");
assert("state_update = null → returns frameEngineId unchanged",
  _resolveNextEngineId("identity", null) === "identity");

// ── 4. Empty / invalid handoff values are ignored ───────────────────────────

console.log("\nEMPTY / INVALID HANDOFF VALUES IGNORED");
assert('current_engine = "" ignored',
  _resolveNextEngineId("identity", { current_engine: "" }) === "identity");
assert('current_engine = "   " (whitespace only) ignored',
  _resolveNextEngineId("identity", { current_engine: "   " }) === "identity");
assert("current_engine = null ignored",
  _resolveNextEngineId("identity", { current_engine: null }) === "identity");
assert("current_engine = 123 (non-string) ignored",
  _resolveNextEngineId("identity", { current_engine: 123 }) === "identity");
assert("current_engine = [] (non-string) ignored",
  _resolveNextEngineId("identity", { current_engine: [] }) === "identity");

// ── 5. Valid handoff for a different pair (travel) also works generically ──

console.log("\nGENERIC HANDOFF (NOT SPECIAL-CASED TO \"place\")");
assert('engine_id="work", current_engine="travel" → resolves to "travel"',
  _resolveNextEngineId("work", { current_engine: "travel" }) === "travel");

// ── 6. Wiring: _runTurnInner must call the real helper ──────────────────────

console.log("\nWIRING — _runTurnInner() USES THE REAL HELPER");
const runTurnInnerSrc = extractFunctionSource(appSrc, "_runTurnInner", {
  untilMarker: "// allow clicking the card panel to close it",
});
assert("_runTurnInner is defined in ui/app.js", !!runTurnInnerSrc);

const callPattern = /window\._currentEngineId\s*=\s*_resolveNextEngineId\(\s*engineId\s*,\s*data\.state_update\s*\)/;
assert("_runTurnInner assigns window._currentEngineId = _resolveNextEngineId(engineId, data.state_update)",
  callPattern.test(runTurnInnerSrc));

// ── 7. Position: the helper call must come AFTER current-frame bookkeeping,
//      rendering, and diagnostics — never before — so the CURRENT response's
//      frame is never relabelled as the future handoff engine. ─────────────

console.log("\nPOSITION — HELPER CALL RUNS AFTER CURRENT-FRAME USES OF engineId/window._currentEngineId");
const idxCall = runTurnInnerSrc.search(callPattern);
assert("helper call site was found inside _runTurnInner", idxCall !== -1);

const idxInitialAssign = runTurnInnerSrc.indexOf("window._currentEngineId = engineId;");
assert("initial `window._currentEngineId = engineId` (current-frame bookkeeping) is present",
  idxInitialAssign !== -1);
assert("helper call happens strictly after the initial current-frame assignment",
  idxInitialAssign !== -1 && idxCall > idxInitialAssign);

const idxMergeBlockStart = runTurnInnerSrc.indexOf("// Merge state_update fields");
assert('"Merge state_update fields" block marker is present', idxMergeBlockStart !== -1);
assert("helper call happens strictly after the state_update merge block",
  idxMergeBlockStart !== -1 && idxCall > idxMergeBlockStart);

// This is the discovery/blue-panel "engine staleness" read — real current-turn
// RENDERING logic that must see the CURRENT frame's engine, not the future one.
const idxDiscoveryStalenessRead = runTurnInnerSrc.indexOf(
  '(window._currentEngineId || engineId || "").toLowerCase()'
);
assert("discovery-panel engine-staleness read (current-turn rendering) is present",
  idxDiscoveryStalenessRead !== -1);
assert("helper call happens strictly after the discovery-panel rendering read",
  idxDiscoveryStalenessRead !== -1 && idxCall > idxDiscoveryStalenessRead);

// emitUITrace TURN_START/TURN_END (diagnostics) use the local `engineId` const
// directly, not window._currentEngineId, so they are structurally unaffected
// regardless of call-site position — but assert they still exist and still
// key off `engineId`, not window._currentEngineId, as an extra safety net.
assert('TURN_START diagnostics keys off local `engineId`, not window._currentEngineId',
  /type:\s*"TURN_START"[\s\S]{0,200}engine_id:\s*engineId/.test(runTurnInnerSrc));

// Structural proof that current-frame bookkeeping cannot be affected by the
// later window._currentEngineId reassignment: `engineId` is declared exactly
// once (as the assignment target) and never reassigned anywhere in the
// function body.
const engineIdAssignments = runTurnInnerSrc.match(/\bengineId\s*=[^=]/g) || [];
assert("`engineId` (current-frame engine) is assigned exactly once — never reassigned",
  engineIdAssignments.length === 1);

// ── 8. runMirrorTurn (Pattern B) must remain completely unchanged ──────────

console.log("\nrunMirrorTurn() (PATTERN B) REMAINS UNCHANGED");
const runMirrorTurnSrc = extractFunctionSource(appSrc, "runMirrorTurn", {
  untilMarker: "async function runProbeTurn(",
});
assert("runMirrorTurn is defined in ui/app.js", !!runMirrorTurnSrc);
assert("runMirrorTurn does NOT call the new _resolveNextEngineId helper (untouched path)",
  !runMirrorTurnSrc.includes("_resolveNextEngineId"));
assert("runMirrorTurn still consumes data.engine_id directly (pre-existing behaviour)",
  /if \(data\.engine_id && data\.engine_id !== "unknown"\) \{\s*const _prevEng = window\._currentEngineId/.test(runMirrorTurnSrc));
assert("runMirrorTurn still consumes state_update.current_engine directly (pre-existing behaviour)",
  /data\.state_update\.current_engine[\s\S]{0,80}window\._currentEngineId = data\.state_update\.current_engine/.test(runMirrorTurnSrc));

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
