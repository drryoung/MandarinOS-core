/**
 * Shared utility: extract and execute the VERBATIM source of a single named
 * top-level function from the real ui/app.js, without loading the rest of the
 * file (which has module-scope DOM/window side effects and cannot run under
 * plain Node).
 *
 * This is intentionally NOT a "mirror" of production logic — it slices the
 * literal function source text out of ui/app.js at test time and executes
 * those exact characters via `new Function`. If the production helper is
 * edited, renamed, or removed, callers automatically pick up the real
 * behaviour (or fail loudly if the function can no longer be found), so the
 * test can never silently drift from what actually ships.
 *
 * Usage:
 *   const { loadRealFunction } = require("./_load_app_js_helper");
 *   const _resolveNextEngineId = loadRealFunction("_resolveNextEngineId");
 */

const fs = require("fs");
const path = require("path");

const APP_JS_PATH = path.join(__dirname, "..", "ui", "app.js");

function readAppJsSource() {
  return fs.readFileSync(APP_JS_PATH, "utf8");
}

/**
 * Slice out the full source text of `function <fnName>(...) { ... }` (or
 * `async function <fnName>(...) { ... }`) from `src`.
 *
 * Naive brace-depth counting is NOT reliable here: this file contains regex
 * literals and strings with unbalanced `{`/`}` characters (e.g. `{2,4}`
 * quantifiers), which throw off a plain counter on large functions. Instead,
 * `untilMarker` — an exact, literal string known to start the next top-level
 * statement immediately after the target function — must be supplied for
 * functions where a plain top-level `\n}` line-anchored close is ambiguous or
 * unreliable; when omitted, a line-anchored `\n}` (a `}` alone on its own
 * line, i.e. a top-level function close, since this codebase never leaves a
 * nested block closer dedented to column 0) is used.
 *
 * Returns null if the function (or, when given, the marker) cannot be found.
 */
function extractFunctionSource(src, fnName, { untilMarker } = {}) {
  const patterns = [`function ${fnName}(`, `async function ${fnName}(`];
  let start = -1;
  for (const p of patterns) {
    const idx = src.indexOf(p);
    if (idx !== -1) { start = idx; break; }
  }
  if (start === -1) return null;

  if (untilMarker) {
    const markerIdx = src.indexOf(untilMarker, start);
    if (markerIdx === -1) return null;
    return src.slice(start, markerIdx);
  }

  const closeRe = /\n\}/g;
  closeRe.lastIndex = start;
  const m = closeRe.exec(src);
  if (!m) return null;
  return src.slice(start, m.index + 2);
}

/**
 * Load and execute the real, verbatim `fnName` function from ui/app.js and
 * return the live function object. Throws if the function cannot be located
 * (e.g. it was renamed or removed), so the test fails loudly instead of
 * silently falling back to a stub.
 */
function loadRealFunction(fnName, { src } = {}) {
  const source = src || readAppJsSource();
  const fnSrc = extractFunctionSource(source, fnName);
  if (!fnSrc) {
    throw new Error(`loadRealFunction: could not locate "${fnName}" in ui/app.js`);
  }
  // eslint-disable-next-line no-new-func
  const factory = new Function(`${fnSrc}\nreturn ${fnName};`);
  return factory();
}

module.exports = { readAppJsSource, extractFunctionSource, loadRealFunction, APP_JS_PATH };
