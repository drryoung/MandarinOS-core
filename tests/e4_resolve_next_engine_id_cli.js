#!/usr/bin/env node
/**
 * Tiny CLI wrapper so non-JS test runners (e.g. the Python integration
 * regression in tests/test_e4_client_handoff_regression.py) can invoke the
 * REAL, verbatim `_resolveNextEngineId` helper from ui/app.js — the exact
 * client merge rule now used by `_runTurnInner()` — instead of reimplementing
 * that rule in another language.
 *
 * Usage:
 *   node tests/e4_resolve_next_engine_id_cli.js '"identity"' '{"current_engine":"place"}'
 *
 * Prints {"result": <string>} to stdout on success.
 */
const { loadRealFunction } = require("./_load_app_js_helper");

function main() {
  const [frameEngineIdJson, stateUpdateJson] = process.argv.slice(2);
  const frameEngineId = JSON.parse(frameEngineIdJson);
  const stateUpdate = stateUpdateJson !== undefined ? JSON.parse(stateUpdateJson) : undefined;

  const _resolveNextEngineId = loadRealFunction("_resolveNextEngineId");
  const result = _resolveNextEngineId(frameEngineId, stateUpdate);
  process.stdout.write(JSON.stringify({ result }));
}

main();
