/**
 * Verifies the MandarinOS.app beta-code handoff logic in ui/app.js:
 * fragment capture + removal, migration query-string reader, the
 * none/validating/active/invalid/temporarily-unavailable state machine,
 * bounded 24h revalidation, manual entry/removal, and session-identity
 * snapshot stability (a mid-session code swap must not retroactively
 * change an already-started session's attributed beta_code).
 *
 * Also verifies the tri-state {"status": "valid"|"invalid"|
 * "temporarily_unavailable"} wire contract with /api/beta_code/validate:
 * an explicit "temporarily_unavailable" response, a network failure, and
 * an unrecognised response shape must ALL be treated identically
 * (never as "valid") — this is the outage/validity conflation this pass
 * corrected.
 *
 * Loads the REAL, verbatim source block from ui/app.js (not a mirror) so
 * this test can never silently drift from what actually ships.
 *
 * Run: node tests/verify_beta_code_handoff.js
 */

const fs = require("fs");
const path = require("path");
const assert = require("assert");

const APP_JS_PATH = path.join(__dirname, "..", "ui", "app.js");
const APP_JS = fs.readFileSync(APP_JS_PATH, "utf8");

const START_MARKER = 'const _BETA_CODE_STORAGE_KEY = "manos_beta_code";';
const END_MARKER = "window.removeBetaCode = removeBetaCode;";

function extractBlock() {
  const startIdx = APP_JS.indexOf(START_MARKER);
  const endIdx = APP_JS.indexOf(END_MARKER);
  if (startIdx === -1) throw new Error(`verify_beta_code_handoff: start marker not found in ${APP_JS_PATH}`);
  if (endIdx === -1) throw new Error(`verify_beta_code_handoff: end marker not found in ${APP_JS_PATH}`);
  return APP_JS.slice(startIdx, endIdx + END_MARKER.length);
}

/** Builds one isolated sandbox instance, simulating a single page load. */
function makeSandbox({ fetchImpl, initialHash = "", initialSearch = "", initialStore = {} } = {}) {
  const store = Object.assign({}, initialStore);
  const localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => {
      store[k] = String(v);
    },
    removeItem: (k) => {
      delete store[k];
    },
  };
  const locationObj = { hash: initialHash, search: initialSearch, pathname: "/ui/index.html" };
  const history = {
    replaceState: (_state, _title, url) => {
      const hashIdx = url.indexOf("#");
      const searchIdx = url.indexOf("?");
      locationObj.hash = hashIdx !== -1 ? url.slice(hashIdx) : "";
      if (searchIdx !== -1 && (hashIdx === -1 || searchIdx < hashIdx)) {
        locationObj.search = url.slice(searchIdx, hashIdx !== -1 ? hashIdx : url.length);
      } else {
        locationObj.search = "";
      }
    },
  };
  const document = {
    readyState: "complete",
    getElementById: () => null,
    addEventListener: () => {},
    removeEventListener: () => {},
    activeElement: null,
  };
  const windowObj = { location: locationObj };
  const fetchFn = fetchImpl || (() => Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) }));

  const factoryBody =
    extractBlock() +
    "\nreturn { initBetaCode, _validateBetaCode, setBetaCodeManually, removeBetaCode, " +
    "_snapshotSessionBetaCode, _consumeFragmentBetaCode, _consumeQueryStringBetaCodeForMigration, " +
    "BETA_CODE_REVALIDATION_INTERVAL_MS };";
  // eslint-disable-next-line no-new-func
  const factory = new Function("window", "document", "localStorage", "history", "fetch", factoryBody);
  const api = factory(windowObj, document, localStorage, history, fetchFn);
  return { api, windowObj, store, locationObj };
}

let passed = 0;
let failed = 0;
function check(label, cond) {
  if (cond) {
    passed += 1;
    console.log(`  PASS ${label}`);
  } else {
    failed += 1;
    console.log(`  FAIL ${label}`);
  }
}

async function main() {
  // ── Fragment capture + removal ─────────────────────────────────────────
  console.log("FRAGMENT CAPTURE AND REMOVAL");
  {
    const { windowObj, locationObj } = makeSandbox({
      initialHash: "#beta_code=MOS-BETA-234789",
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) }),
    });
    await Promise.resolve(); // let the validate promise chain settle
    await new Promise((r) => setTimeout(r, 0));
    check("fragment code is picked up", windowObj._betaCodeState.code === "MOS-BETA-234789");
    check("fragment is stripped from the URL", locationObj.hash === "");
    check("beta code does not enter the query string", locationObj.search === "");
  }

  // URL-decoding safety
  {
    const encoded = encodeURIComponent("MOS-BETA-234789");
    const { windowObj } = makeSandbox({
      initialHash: `#beta_code=${encoded}`,
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) }),
    });
    await new Promise((r) => setTimeout(r, 0));
    check("URL-encoded fragment value decodes correctly", windowObj._betaCodeState.code === "MOS-BETA-234789");
  }

  // ── Migration-compatible query-string reader ───────────────────────────
  console.log("MIGRATION QUERY-STRING READER");
  {
    const { windowObj, locationObj } = makeSandbox({
      initialSearch: "?beta_code=MOS-BETA-234789",
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) }),
    });
    await new Promise((r) => setTimeout(r, 0));
    check("query-string code is still picked up (migration compat)", windowObj._betaCodeState.code === "MOS-BETA-234789");
    check("query param is stripped immediately", locationObj.search === "");
  }
  {
    // Fragment takes priority over a simultaneously-present query string
    // (the migration reader is only ever consulted when no fragment was
    // found — the website itself never generates both at once).
    const { windowObj } = makeSandbox({
      initialHash: "#beta_code=MOS-BETA-234789",
      initialSearch: "?beta_code=MOS-BETA-BADBAD",
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) }),
    });
    await new Promise((r) => setTimeout(r, 0));
    check("fragment wins over query-string when both present", windowObj._betaCodeState.code === "MOS-BETA-234789");
  }

  // ── Malformed code: rejected locally, no network call ──────────────────
  console.log("MALFORMED CODE");
  {
    let called = false;
    const { windowObj } = makeSandbox({
      initialHash: "#beta_code=not-a-real-code",
      fetchImpl: () => {
        called = true;
        return Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) });
      },
    });
    await new Promise((r) => setTimeout(r, 0));
    check("malformed code is rejected without a network call", called === false);
    check("state is none for malformed code", windowObj._betaCodeState.status === "none");
  }

  // ── Definitive states from the website ──────────────────────────────────
  console.log("DEFINITIVE VALID / INVALID");
  {
    const { windowObj, store } = makeSandbox({
      initialHash: "#beta_code=MOS-BETA-234789",
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) }),
    });
    await new Promise((r) => setTimeout(r, 0));
    check("definitive valid -> status active", windowObj._betaCodeState.status === "active");
    check("active state is persisted to storage", store["manos_beta_code"] === "MOS-BETA-234789");
    check("validatedAt timestamp recorded", typeof windowObj._betaCodeState.validatedAt === "number");
  }
  {
    const { windowObj, store } = makeSandbox({
      initialHash: "#beta_code=MOS-BETA-234789",
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "invalid" }) }),
    });
    await new Promise((r) => setTimeout(r, 0));
    check("definitive invalid -> code removed (not attached)", windowObj._betaCodeState.code === null);
    check("nothing left in storage after definitive invalid", !store["manos_beta_code"]);
  }

  // ── Rule A: brand-new code + outage -> NOT attached ─────────────────────
  console.log("NEW CODE + TEMPORARY OUTAGE (rule A)");
  {
    const { windowObj, api } = makeSandbox({
      initialHash: "#beta_code=MOS-BETA-234789",
      fetchImpl: () => Promise.reject(new Error("network down")),
    });
    await new Promise((r) => setTimeout(r, 0));
    check("outage on brand-new code -> temporarily-unavailable", windowObj._betaCodeState.status === "temporarily-unavailable");
    api._snapshotSessionBetaCode();
    check("never-confirmed code is NOT attached to a new session", windowObj._sessionBetaCode === null);
  }
  {
    // Server reachable but explicitly reports {"status":
    // "temporarily_unavailable"} (Railway's own tri-state contract) —
    // must be treated identically to a network-level failure, never as
    // "valid" merely because a response was received.
    const { windowObj, api } = makeSandbox({
      initialHash: "#beta_code=MOS-BETA-234789",
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "temporarily_unavailable" }) }),
    });
    await new Promise((r) => setTimeout(r, 0));
    check(
      "explicit temporarily_unavailable status is not treated as active",
      windowObj._betaCodeState.status === "temporarily-unavailable"
    );
    api._snapshotSessionBetaCode();
    check("new code with explicit unavailable status is NOT attached", windowObj._sessionBetaCode === null);
  }
  {
    // Malformed/unrecognised server response shape must also fail closed
    // to "unavailable", never silently become "active".
    const { windowObj } = makeSandbox({
      initialHash: "#beta_code=MOS-BETA-234789",
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ unexpected: "shape" }) }),
    });
    await new Promise((r) => setTimeout(r, 0));
    check(
      "unrecognised response shape is treated as unavailable, not active",
      windowObj._betaCodeState.status === "temporarily-unavailable"
    );
  }

  // ── Rule B: previously-active code survives an outage ──────────────────
  console.log("STORED ACTIVE CODE + STALE + OUTAGE (rule B)");
  {
    const staleTs = Date.now() - 25 * 60 * 60 * 1000; // 25h ago (>24h interval)
    const { windowObj, api } = makeSandbox({
      initialStore: { manos_beta_code: "MOS-BETA-234789", manos_beta_code_validated_at: String(staleTs) },
      fetchImpl: () => Promise.reject(new Error("network down")),
    });
    await new Promise((r) => setTimeout(r, 0));
    check("stale + outage -> temporarily-unavailable (not invalid)", windowObj._betaCodeState.status === "temporarily-unavailable");
    check("prior validatedAt is retained, not reset", windowObj._betaCodeState.validatedAt === staleTs);
    api._snapshotSessionBetaCode();
    check("previously-active code IS attached during an outage", windowObj._sessionBetaCode === "MOS-BETA-234789");
  }

  // ── Fresh stored code: no network call at all ───────────────────────────
  console.log("FRESH STORED CODE (no revalidation call)");
  {
    let called = false;
    const freshTs = Date.now() - 60 * 1000; // 1 minute ago
    const { windowObj } = makeSandbox({
      initialStore: { manos_beta_code: "MOS-BETA-234789", manos_beta_code_validated_at: String(freshTs) },
      fetchImpl: () => {
        called = true;
        return Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) });
      },
    });
    await new Promise((r) => setTimeout(r, 0));
    check("fresh code used directly, no network call", called === false);
    check("status is active", windowObj._betaCodeState.status === "active");
  }

  // ── Stale stored code: revalidates and succeeds ─────────────────────────
  console.log("STALE STORED CODE -> REVALIDATES");
  {
    let called = false;
    const staleTs = Date.now() - 25 * 60 * 60 * 1000;
    const { windowObj, store } = makeSandbox({
      initialStore: { manos_beta_code: "MOS-BETA-234789", manos_beta_code_validated_at: String(staleTs) },
      fetchImpl: () => {
        called = true;
        return Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) });
      },
    });
    await new Promise((r) => setTimeout(r, 0));
    check("stale code triggers a revalidation call", called === true);
    check("successful revalidation refreshes validatedAt", windowObj._betaCodeState.validatedAt > staleTs);
    check("storage timestamp refreshed too", Number(store["manos_beta_code_validated_at"]) > staleTs);
  }

  // ── Stale stored code, definitively revoked -> removed ──────────────────
  console.log("STALE STORED CODE, DEFINITIVELY REVOKED");
  {
    const staleTs = Date.now() - 25 * 60 * 60 * 1000;
    const { windowObj, store } = makeSandbox({
      initialStore: { manos_beta_code: "MOS-BETA-234789", manos_beta_code_validated_at: String(staleTs) },
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "invalid" }) }),
    });
    await new Promise((r) => setTimeout(r, 0));
    check("revoked stale code is removed", windowObj._betaCodeState.code === null);
    check("removed from storage", !store["manos_beta_code"]);
  }

  // ── Manual entry ─────────────────────────────────────────────────────────
  console.log("MANUAL ENTRY");
  {
    const { windowObj, api } = makeSandbox({
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) }),
    });
    await new Promise((r) => setTimeout(r, 0)); // let the initial (empty) init settle
    await api.setBetaCodeManually("mos-beta-234789"); // lowercase input
    check("manual entry is case-normalised and validated", windowObj._betaCodeState.code === "MOS-BETA-234789");
    check("manual entry results in active state", windowObj._betaCodeState.status === "active");
  }
  {
    const { windowObj, api } = makeSandbox({
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "invalid" }) }),
    });
    await new Promise((r) => setTimeout(r, 0));
    const result = await api.setBetaCodeManually("MOS-BETA-234789");
    check("manual entry of an invalid code returns false", result === false);
    check("manual entry of an invalid code is not stored", windowObj._betaCodeState.code === null);
  }

  // ── Removal ──────────────────────────────────────────────────────────────
  console.log("REMOVAL");
  {
    const { windowObj, api, store } = makeSandbox({
      initialStore: { manos_beta_code: "MOS-BETA-234789", manos_beta_code_validated_at: String(Date.now()) },
      fetchImpl: () => Promise.resolve({ json: () => Promise.resolve({ status: "valid" }) }),
    });
    await new Promise((r) => setTimeout(r, 0));
    api.removeBetaCode();
    check("removal clears in-memory state", windowObj._betaCodeState.code === null && windowObj._betaCodeState.status === "none");
    check("removal clears storage", !store["manos_beta_code"] && !store["manos_beta_code_validated_at"]);
  }

  // ── Session-identity snapshot stability (regression, item #7) ──────────
  console.log("SESSION IDENTITY SNAPSHOT STABILITY (regression)");
  {
    const { windowObj, api } = makeSandbox({
      fetchImpl: (_url, opts) => {
        const body = JSON.parse(opts.body);
        // Both code A and code B validate as active in this scenario.
        return Promise.resolve({ json: () => Promise.resolve({ status: "valid", code: body.beta_code }) });
      },
    });
    await new Promise((r) => setTimeout(r, 0));

    // 1. Start a session with code A.
    await api.setBetaCodeManually("MOS-BETA-AAAAAA".replace(/[01AI]/g, "2")); // ensure alphabet-legal
    const codeA = windowObj._betaCodeState.code;
    api._snapshotSessionBetaCode();
    const sessionSnapshotAtStart = windowObj._sessionBetaCode;
    check("session snapshot captured code A at session start", sessionSnapshotAtStart === codeA);

    // 2. Replace the stored code with code B mid-session (e.g. user opens
    //    the manual panel and connects a different code without starting
    //    a new session).
    await api.setBetaCodeManually("MOS-BETA-234788");
    const codeB = windowObj._betaCodeState.code;
    check("stored code did change to B", codeB !== codeA && codeB === "MOS-BETA-234788");

    // 3. "End session" — read window._sessionBetaCode, exactly as
    //    endSession() does in ui/app.js, NOT window._betaCodeState.
    const attributedAtEndSession = windowObj._sessionBetaCode;

    // 4. The record must still be attributed to code A, not B.
    check("ended session is still attributed to code A, not B", attributedAtEndSession === codeA);
    check("attributed value is definitely not code B", attributedAtEndSession !== codeB);
  }

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
