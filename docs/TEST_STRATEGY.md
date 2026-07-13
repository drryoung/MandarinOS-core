# MandarinOS Test Strategy

## 1. Purpose and audience

This document is the **test and verification contract** for MandarinOS R2 maintenance. It explains what each existing test category actually proves, what it does not prove, which suites are mandatory for which change types, and how to add regression coverage without creating false confidence.

Audience: maintainers; technical reviewers; AI coding agents (Cursor and others) operating on this repository; the project owner; anyone approving a production deployment.

This document is subordinate to verified code and actual test behaviour — if a claim here disagrees with what a test file actually does, the code is correct and this document is stale. It is authoritative for: test-category definitions; required validation by change type; evidentiary weight; and regression-test expectations, subject to that same correction rule.

Application baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Application baseline tag: `architecture-baseline-2026-07-12-r2`

This document describes the actual R2 test system as verified by direct inspection of `tests/`, `scripts/`, `tools/`, `tests/conftest.py`, `README.md`, `AI_CONTEXT.md`, and `.github/workflows/coverage_scan.yml` — it is not a proposal for how testing should ideally work.

**Scope.** This document covers `tests/*.py`, `tests/*.js`, `scripts/test_counter_reply_matrix.py`, `tests/conftest.py`, and the CI workflow that executes a subset of them. It does not cover manual exploratory testing procedures, non-repository monitoring/alerting, or the diagnostic HTML pages under `ui/` that are opened by hand (e.g. `ui/replay_test.html`) — those are mentioned only where relevant to explain why no automated equivalent exists. It complements, and does not duplicate, the four approved R2 contracts and `docs/ARCHITECTURE.md`: those documents describe what the system does; this document describes how — and how well — that behaviour is currently verified.

**How to use this document.** Before making a change, read §13 to find the row matching the change type and identify the minimum required verification. While writing a regression test, read §14 for design rules and §3 to classify what kind of test is being written and what claim it can honestly support. Before reporting a change as complete, use the §20 template and disclose any skipped, static-only, or mirrored tests using the vocabulary defined in §3 and §15. Before approving a production deployment, follow §19 in full — a passing local suite alone is never sufficient evidence for a production claim.

## 2. Core testing principles

1. Tests are classified by **what they execute**, not by filename — a file named `verify_*.js` or `test_*regression*.py` is not evidence of execution type by itself.
2. Executing real production logic is stronger evidence than mirrored logic that reimplements the same algorithm inside the test.
3. Server-unit success does not prove client behaviour, and vice versa.
4. Client-helper success (an extracted real function running under Node) does not prove the server behaves correctly, or that the client's *calling* code wires that helper correctly.
5. Client success and server success measured separately do not prove their transport contract (`conversation_state`/`state_update`) is honoured end-to-end.
6. Local round-trip success (even a real HTTP call to a local server) does not prove deployed-production correctness — the deployed commit, environment variables, and persistent volume can all differ.
7. A static source assertion proves only that particular text exists at a particular location in a file at the time the test ran — it says nothing about runtime behaviour.
8. A mirrored test can detect drift in its *own* reimplementation while completely missing a defect introduced into the real production function it was written to approximate.
9. Production verification requires confirming the deployed commit via `/api/version` — a successful Railway build does not by itself prove the expected commit is running.
10. Every regression fix should preserve the failure as a test at the lowest layer capable of reproducing it accurately — do not add a live-server integration test for a defect a pure-function unit test could catch.

> Test confidence is determined by execution path and scope, not by the number of passing files.

## 3. Test taxonomy

| Category | What executes | What it proves | What it does not prove | Typical files |
| -------- | ------------- | -------------- | ----------------------- | -------------- |
| A. Real Python unit/behavioural | Production Python imported/executed via `importlib` or direct `import` | The named function/module behaves correctly for the given inputs | HTTP wiring, client behaviour, deployed behaviour | `test_progress_store.py`, `test_spoken_chinese_routing.py`, `test_scorecard_interpretation.py`, most of `test_zh_en_synchronisation.py` (§9) |
| B. Extracted real-JavaScript helper | A single function sliced verbatim from `ui/app.js` and run under Node | That one extracted function behaves correctly in isolation | That the surrounding client code calls it correctly, that a browser executes it identically, DOM/event wiring | `tests/e4_resolve_next_engine_id_cli.js`, parts of `tests/verify_e4_client_handoff.js` |
| C. Mirrored JavaScript | A hand-copied reimplementation of production logic, run under Node | Internal consistency of the mirror's own logic | Whether the *shipped* `ui/app.js` function still matches the mirror | `tests/verify_asr_filler.js` (body), `tests/verify_spoken_recovery_exact_match.js` (body), `tests/verify_phase12c.js` |
| D. Static source-verification | A `read_text()`/regex/substring check against a source file | That specific text/symbols exist at the current baseline | Runtime behaviour, correctness of the logic that text implements | `tests/test_asr_thinking_grace.py`, parts of `tests/test_deployment_hygiene.py` |
| E. Local live-server (`live_server`-marked) | Real HTTP requests to a pre-started server on `localhost:8765` | Full server-side request/response behaviour for one process | Deployed-production behaviour, browser client behaviour | `tests/test_golden_regression.py`, `tests/test_interaction_regression.py` |
| F. Browser/DOM | True browser automation | — | **None exist in this repository** (see §7) | — |
| G. Build/generated-artifact | Builder functions imported and called directly | Builder function correctness for given inputs | That the committed/deployed `runtime/out_phase7/*.runtime.json` reflects current source (no such test exists) | `tests/test_build_frame_tokens_runtime.py` |
| H. Persistence/filesystem | Real persistence modules against a temp directory | Module read/write/isolation behaviour under a redirected data dir | Railway volume behaviour, real `MANDARINOS_DATA_DIR` misconfiguration | `tests/test_progress_store.py`, `tests/test_beta_profile.py`, `tests/test_session_intelligence.py` |
| I. Deployment/configuration | Mix of static asserts on config files and behavioural env-override tests | Config files contain expected strings; env-var override works for one process | That Railway is actually configured this way, that a deploy succeeded | `tests/test_deployment_hygiene.py` |
| J. Production smoke verification | Manual operational check against the deployed Railway URL | The deployed commit and one smoke scenario | Anything not exercised by that scenario | Manual `/api/version` + smoke check (no automated production test exists) |

### A. Real Python unit/behavioural tests

- **Pure helper tests** — e.g. `tests/test_spoken_chinese_routing.py` imports `scripts/ui_server.py` via `importlib` and calls `_normalize_zh_for_routing`, `_direct_persona_answer` directly; no HTTP, no reimplementation.
- **Turn-engine tests** — e.g. `tests/test_e4_topic_handoff.py` calls real `_infer_question_topic_engine`, `_direct_persona_answer`, though it also uses a mirrored helper (`_simulate_dp_e4`) for setup — see §9.
- **State/persistence tests** — e.g. `tests/test_progress_store.py`, `tests/test_beta_profile.py` (see §11).
- **Content/build tests** — e.g. `tests/test_build_frame_tokens_runtime.py` calls `tokenize`/`build_hanzi_lookup` from `tools/builders/build_frame_tokens_runtime.py` directly.

### B. Extracted real-JavaScript helper tests

Mechanism: `tests/_load_app_js_helper.js` locates `function <name>(` or `async function <name>(` in `ui/app.js`, slices to the next bare `\n}` (or to an explicit `untilMarker` string when the naive brace search is unreliable — e.g. because the function body contains regex literals with `{n,m}` quantifiers), and executes the sliced text via `new Function(...)`.

**Scope and limitations:**
- Only works for top-level `function`/`async function` declarations — not arrow functions or `const fn = ...`.
- Finds the **first** occurrence of the name only.
- The default (no `untilMarker`) closing-brace search is a `\n}` line match, not real brace-depth counting — it can mis-slice a large function containing an early bare `}` on its own line, which is why some call sites (e.g. slicing `_runTurnInner`) pass an explicit `untilMarker`.
- `loadRealFunction()` itself never passes `untilMarker`, so it is only reliable for short, self-contained helpers (its only production consumer, `_resolveNextEngineId`, is 5 lines at `ui/app.js:6617–6621`).
- The extracted function runs with no access to `ui/app.js` module-scope variables unless they are defined inside its own body — it cannot exercise anything that depends on client global state.
- `tests/e4_resolve_next_engine_id_cli.js` is the only CLI built on this mechanism, invoked by `tests/test_e4_client_handoff_regression.py` via `subprocess` + `node` (skipped with `pytest.skip` if Node is not on `PATH`).

### C. Mirrored JavaScript tests

`tests/verify_asr_filler.js`, `tests/verify_spoken_recovery_exact_match.js`, and `tests/verify_phase12c.js` all hand-copy logic from `ui/app.js` into the test file itself, then assert against the copy. **These do not execute the shipped `ui/app.js` function** — a defect introduced into the real function while the mirror is left unchanged will not be caught by these tests. `verify_asr_filler.js` and `verify_spoken_recovery_exact_match.js` also each contain a small static-assertion tail (see category D) that checks a handful of symbol names still exist in `ui/app.js`, which provides weak drift detection but does not validate behaviour.

### D. Static source-verification tests

Legitimate uses verified in this repository: wiring checks (does `ui/app.js` still call a named function from the expected place?); forbidden-symbol checks; deployment-config checks (`tests/test_deployment_hygiene.py` asserting the exact `PORT` line and `Procfile` contents); guardrail checks (e.g. `tests/test_closing_move_suppression.py`, self-documented as "static source-analysis checks").

**Limits:** a static check can pass while the referenced code path is unreachable, disabled, or behaviourally broken; it proves textual presence, not execution correctness.

### E. Local live-server tests

Exactly **4 files, 120 test functions** carry the module-level `pytestmark = pytest.mark.live_server`: `tests/test_golden_regression.py` (35), `tests/test_golden_conversation_scenarios.py` (10), `tests/test_interaction_regression.py` (68), `tests/test_blue_question_relevance.py` (7).

- They **assume** a server is already running on `localhost:8765` — none of them launch it themselves.
- They make real HTTP requests via `urllib.request` to `/api/run_turn` (server-side only; no browser/client code executes).
- `tests/conftest.py`'s `pytest_runtest_setup` auto-skips any `live_server`-marked test if a TCP connect to `localhost:8765` fails (0.5s timeout) — this is a socket probe, not an HTTP health check.
- Separately, several other files (`tests/test_spoken_question_routing_regression.py`, `tests/test_e4_client_handoff_regression.py`, `tests/test_contextual_place_asr_repair.py`, `tests/test_open_world_food_and_location_fixes.py`, `tests/test_stale_answer_loop_regression.py`) start their **own** in-process `ThreadedHTTPServer` on an ephemeral `127.0.0.1` port and are **not** `live_server`-marked — they always run under the core suite and do not require a pre-started server.
- `tests/test_zh_en_synchronisation.py` has its own bare `pytest.skip`-based live check against `MANDARINOS_SERVER_URL` or a default of **`http://localhost:8080`** (not 8765) — a separate, non-`live_server` mechanism.
- `scripts/test_counter_reply_matrix.py` also targets `http://localhost:8765/api/run_turn` but is a standalone script, not a pytest test — it hard-fails (`sys.exit(1)`) rather than skipping when the server is unreachable.

### F. Browser/DOM tests

**No true browser or DOM automation framework exists in this repository.** Verified by searching for Playwright, Puppeteer, Selenium, Cypress, Jest, Karma, Vitest, and jsdom configuration across the whole repo, and confirming no `package.json` exists at the R2 baseline commit. `ui/replay_test.html` is a manual browser page (opened by a human, not driven by an automation tool). `tests/verify_phase12c.js` contains fake DOM node stubs (plain objects with a `style.display` property and a `querySelector` stub) for one scenario — this is not real DOM and must not be described as browser testing. Node-based extraction/execution of a single function (category B) is not browser testing either, since it never loads `ui/app.js` as a whole or runs inside a DOM.

### G. Build and generated-artifact tests

`tests/test_build_frame_tokens_runtime.py` imports `tokenize`/`build_hanzi_lookup` from `tools/builders/build_frame_tokens_runtime.py` and tests those functions directly, including one duplicate-hanzi case using a temp JSON file. **No test imports or runs `tools/build_runtime_artifacts.py` itself**, validates a schema for any `runtime/out_phase7/*.runtime.json` file, or compares `p1_frames.json`/`p2_frames.json` content against `frame_options.runtime.json` for consistency. `tests/test_golden_regression.py` optionally reads `runtime/out_phase7/recovery_phrases.runtime.json` in one static test and **skips** (does not fail, does not regenerate) if the file is absent.

### H. Persistence and filesystem tests

See §11 for the full inventory. Summary: `tests/test_progress_store.py` (7 tests) and `tests/test_beta_profile.py` (8 tests) redirect the module's private directory constant to `tmp_path` and exercise the real save/load/dedupe/isolation logic on disk. `tests/test_session_intelligence.py` reloads `scripts/session_intelligence.py` with `MANDARINOS_SESSION_CAPTURE` explicitly set to `""` or `"1"` and `MANDARINOS_DATA_DIR` pointed at `tmp_path`, covering both the disabled and enabled paths behaviourally. `tests/test_clear_memory_regression.py` and `tests/test_learner_memory_migration.py` cover `scripts/learner_memory.py` the same way. No diagnostics (`diag/asr_traces.jsonl`, `MANDARINOS_DIAG_TOKEN`) test exists.

### I. Deployment/configuration tests

`tests/test_deployment_hygiene.py` is the only dedicated file: two of its six tests are pure static asserts (`PORT` env-read line, exact `Procfile`/`requirements.txt` text); the other four are real behavioural tests that load `progress_store.py` / `beta_profile.py` / `learner_memory.py` with `MANDARINOS_DATA_DIR` overridden to a temp directory and confirm the module's private path constants follow it (see §13 for the full source-string inventory).

### J. Production smoke verification

**No automated production test exists.** Verification against the deployed Railway URL is currently manual only: read `/api/version`, compare the SHA, and manually exercise the affected behaviour. See §19.

## 4. Test execution map

| Command | Tests included | Tests excluded/skipped | Prerequisites | Evidence level |
| ------- | -------------- | ------------------------ | -------------- | ---------------- |
| `python -m pytest tests/ -m "not live_server"` | All collected `tests/test_*.py` except the 4 `live_server`-marked files; includes in-process-HTTP files (they are not `live_server`-marked) | The 4 `live_server` files (120 functions); the 6 files in `collect_ignore` | No pre-started external server is required for this tier's *intended* scope; no external internet access is required. Precisely: (a) several tests in this tier start their **own** local `ThreadedHTTPServer` on `127.0.0.1` and communicate with it over real loopback HTTP — a server process does exist during those tests, it is simply not externally pre-started; (b) Node is optional — only two individual tests `subprocess`-invoke `node` and self-skip via `pytest.skip` if it is absent from `PATH`; (c) two of the in-process-HTTP files import `ui_server` at module scope without redirecting `MANDARINOS_DATA_DIR`, carrying the risk (not confirmed as occurring) of writing to the real repo `data/` directory — see §16 | Mixed A–D, H, I; some in-process E |
| `python -m pytest tests/ -m "live_server"` | Only the 4 `live_server`-marked files | Everything else | A server must already be running: `python scripts/ui_server.py` on port 8765 | E (real server-side HTTP) |
| `python -m pytest tests/test_deployment_hygiene.py` | 6 tests in that file only | Everything else | None — no server | D + H (mixed) |
| `node tests/verify_asr_filler.js` | 82+ assertions per the file's own header comment | Everything else | Node on `PATH`; no server | C + D (mirrored-primary, with a static drift-guard tail) |
| `python tests/test_golden_regression.py --static-only` | ~19 static functions inside that one file, run via its own `main()`, not pytest collection | All integration (HTTP) tests in the same file | None — no server; reads repository files directly (optionally `runtime/out_phase7/recovery_phrases.runtime.json`, skipped if absent) | D (static only) |
| `python tests/test_golden_regression.py` (no flag) | Static tests + integration tests | Nothing, but integration block silently reports unavailable if `_server_alive()` is false | Best exercised with a server running on 8765 | D + E |
| `python -m unittest -v` (repository root, bare — textually identical to the literal `unit-tests` job command in `.github/workflows/coverage_scan.yml`) | Local exact-command result (A, below): **0 tests**. Do **not** assume this executes the pytest-style core/`live_server` tiers described above; `collect_ignore` has no effect on this command regardless | Everything — the local exact-command result discovered nothing | None declared, but see the CI-scope note below — actual CI result not verified | Local exact-command result only; see §5 and the CI-scope note |
| `python -m unittest discover -s tests -p "test_*.py" -v` (**not** a workflow command — explicit discovery root) | Local explicit-discovery audit (B, below): 88 accounted cases, 6 modules, 14 `unittest.TestCase` classes, 80 real executions, 8 local-sandbox import errors | Every pytest-style file lacking a `unittest.TestCase` subclass (contributes silently to neither list) | None declared | Narrow — only `unittest.TestCase`-derived tests actually run; see §5 |
| `python -m unittest -v tests/test_coverage_affordance.py tests/test_open_card_trace_integration.py` (the `coverage_scan` job's second, file-path-qualified command) | Exactly the `unittest.TestCase` classes in those two named files — 4 tests, locally verified as exit 0/`OK`; actual CI result not verified from a workflow log | Every other file in the repository (not passed as an argument) | None | A (real Python, `unittest.TestCase`-based) |
| `python scripts/test_counter_reply_matrix.py` | Its own POST-based scenario matrix | N/A (standalone) | A server running on 8765 — **hard exits (`sys.exit(1)`)**, does not skip, if unreachable | E, writes `docs/reports/counter_reply_matrix_report.md` |

For each pytest-based command: none of them write to disk outside `tmp_path` fixtures except `test_open_world_food_and_location_fixes.py`/`test_stale_answer_loop_regression.py`'s in-process server, which imports `ui_server` at module scope without an env override and could touch the real repo `data/` directory if a turn triggers persistence (flagged in §16 and §17 — not confirmed to actually write, but not excluded either). The `live_server` suite writes to whatever `MANDARINOS_DATA_DIR`/`data/` the already-running server process was started with. No pytest command regenerates `runtime/out_phase7/` artifacts. Tests are skipped silently only for the `live_server` marker (via `pytest.skip`, visible in verbose output, not silent in the sense of hidden) and for two individual Node-`subprocess` tests that self-skip if `node` is absent from `PATH`.

**CI-scope note — three separate facts that must never be conflated.** Read this before relying on "CI is green" as evidence of anything beyond exactly what was executed. Retained principles, unconditionally true regardless of any experiment below: `collect_ignore` in `tests/conftest.py` controls **pytest collection only** — `python -m unittest` never reads `conftest.py` at all, so it honours no `collect_ignore` entry, no pytest marker, fixture, or `pytest_configure`/`pytest_runtest_setup` hook; `unittest`'s test loader only recognises `unittest.TestCase` subclasses, so a `test_*.py` file consisting entirely of plain pytest-style `def test_foo(fixture):` functions or fixture-parametrised plain classes (e.g. `tests/test_progress_store.py`, `tests/test_zh_en_synchronisation.py` — see §9) can still be `__import__`-ed by `unittest`'s discovery (a file being importable does not mean its pytest-style functions ran) while contributing **zero** test cases, with no error and no visible indication that it was skipped; green CI proves only the exact cases shown as executed in that CI's own log, nothing about files that were merely importable, and nothing about the pytest-style `-m "not live_server"`/`-m "live_server"` tiers — those tiers are not invoked by `.github/workflows/coverage_scan.yml` at all.

**(A) Local exact-command result.** `python -m unittest -v`, executed from the repository root with no arguments — textually identical to the `unit-tests` job's step — was run in a local Windows/Python 3.14 environment (CI's `coverage_scan.yml` pins `ubuntu-latest`/Python `3.10`, a disclosed environment difference not independently re-verified against that exact combination). Result: **0 tests** (`Ran 0 tests in 0.000s`, `NO TESTS RAN`), because `tests/` has no `__init__.py` and `unittest`'s default discovery, started from `.`, did not recurse into it. This was confirmed twice against this repository and independently reproduced with a minimal, repository-external two-file case (a bare `test_*.py` in a subdirectory lacking `__init__.py`, invisible to `python -m unittest -v` run from the parent directory). **This is the locally observed result of the command that textually matches the workflow step. It is not proof of what GitHub Actions ran on Ubuntu/Python 3.10.**

**(B) Local explicit-discovery audit.** `python -m unittest discover -s tests -p "test_*.py" -v` — **this is not the workflow command**; it points discovery explicitly at `tests/`, which the bare command in (A) does not do. Locally, it enumerated: 88 accounted cases; 6 modules; 14 `unittest.TestCase` classes (`tests/test_conversation_fixes.py`, `tests/test_coverage_affordance.py`, `tests/test_open_card_resolver.py`, `tests/test_open_card_trace_integration.py`, `tests/test_open_card_wiring.py`, `tests/test_report_asr_traces.py`); 80 real assertion executions ("ok"); 8 `unittest.loader._FailedTest` import-error entries reported as `ERROR` (overlapping several `collect_ignore` files plus two non-ignored files that `import ui_server` at module scope), all 8 failing locally with the identical `ValueError: I/O operation on closed file` pattern traced to a module-level `print()` colliding with this specific sandbox's own stdout redirection — disclosed as a **local sandbox artifact, not a certified CI behaviour**. **This experiment identifies the maximum directly discovered `unittest.TestCase` surface under explicit `tests/` discovery, subject to its disclosed import errors. It does not establish CI execution.**

**(C) Actual GitHub Actions execution.** No authenticated GitHub Actions log access was available in this environment (`gh` is not installed/authenticated here). **The actual GitHub Actions test count has not been verified from workflow logs.** Do not infer the CI count from either (A) or (B) above — a maintainer with CI log access should record the actual command output, the `Ran N tests` total, and the pass/fail result directly from the latest relevant `coverage_scan` run, and update this note accordingly.

**What this means, stated without overclaiming:** because the `unit-tests` job's literal command is textually identical to the local exact-command result in (A), there is a real, unresolved possibility that the same job also discovers and runs zero tests on `ubuntu-latest`/Python `3.10` — but this is a possibility raised by (A), not a confirmed CI fact, since (C) is unverified. Do not describe (A)'s zero-test result as confirmed GitHub Actions behaviour, do not describe (B)'s 88-case result as the CI-executed count, and do not describe either local experiment as "what CI runs." The `coverage_scan` job's second command (`python -m unittest -v tests/test_coverage_affordance.py tests/test_open_card_trace_integration.py`) is described in this document only as **locally verified to execute four tests** (exit 0, `OK`); its actual CI behaviour is likewise unverified from a workflow log and is very likely, but not confirmed, to match, since it does not depend on the discovery-root ambiguity in (A)/(B) at all.

Additional verified commands, all quoted from `tests/conftest.py`'s docstring, `README.md`, or `AI_CONTEXT.md` (do not invent others):

```bash
# Core unit/contract suite (default) — tests/conftest.py
python -m pytest tests/ -m "not live_server"

# Local integration suite — tests/conftest.py (requires server on localhost:8765)
python -m pytest tests/ -m "live_server"

# Deployment / operational tests — tests/conftest.py
python -m pytest tests/test_deployment_hygiene.py

# Manual JavaScript verification — tests/conftest.py
node tests/verify_asr_filler.js

# Static-only golden regression check — README.md, AI_CONTEXT.md
python tests/test_golden_regression.py --static-only

# Full golden regression, integration block active if server is up — README.md
python tests/test_golden_regression.py

# CI unit-tests job — .github/workflows/coverage_scan.yml (local exact-command result: 0 tests; actual CI result not verified — see CI-scope note above)
python -m unittest -v

# Local explicit-discovery audit only — NOT a workflow command (result: 88 cases / 6 modules / 14 classes, 8 local-sandbox import errors)
python -m unittest discover -s tests -p "test_*.py" -v

# CI coverage_scan job's second command — .github/workflows/coverage_scan.yml (file-path-qualified; locally verified: 4 tests, OK; actual CI result not verified)
python -m unittest -v tests/test_coverage_affordance.py tests/test_open_card_trace_integration.py
```

## 5. Current suite composition

Verified counts (best-effort where classification depends on file contents, not filename):

- **72** files under `tests/test_*.py`, plus **1** (`scripts/test_counter_reply_matrix.py`) outside `tests/`.
- **6** of the 72 are excluded from pytest collection via `collect_ignore` in `tests/conftest.py` (`test_p1_to_p2_transition.py`, `test_hint_cascade.py`, `test_scaffolding_transitions_v1.py`, `test_diagnostic_engine.py`, `test_diagnostic_integration.py`, `test_diagnostic_p1.py`) — these are standalone scripts with module-level side effects, not pytest test suites; a 7th file, `tests/test_diagnostic_p1.ts`, is a parallel TypeScript-language validator outside pytest's scope entirely.
- **6** files under `tests/*.js`: `_load_app_js_helper.js` (utility, not a test itself), `tests/verify_asr_filler.js`, `tests/verify_e4_client_handoff.js`, `tests/verify_spoken_recovery_exact_match.js`, `tests/verify_phase12c.js` (all category C/hybrid), and `tests/e4_resolve_next_engine_id_cli.js` (category B CLI wrapper).
- **4** files / **120** functions carry `@pytest.mark.live_server` (counting rule: grepped for the exact marker string across `tests/`; all 4 apply it once at module level via `pytestmark =`, so every `def test_*` in that file inherits it).
- **2** JS files are invoked automatically from Python via `subprocess`: `verify_asr_filler.js` (from `tests/test_asr_filler_suppression.py`) and `e4_resolve_next_engine_id_cli.js` (from `tests/test_e4_client_handoff_regression.py`). The other two verify scripts (`verify_e4_client_handoff.js`, `verify_spoken_recovery_exact_match.js`) and `verify_phase12c.js` are manual-only — not run by pytest or CI.
- Mirrored/static-primary ASR files (best-effort, counting a file as "mirrored/static" only when no real production import/execution is its primary mechanism): `tests/verify_asr_filler.js`, `tests/verify_spoken_recovery_exact_match.js`, `tests/verify_phase12c.js`, `tests/test_asr_thinking_grace.py`, `tests/test_asr_interim_latency.py` — **5** files.
- Persistence-behavioural files confirmed real-module: `tests/test_progress_store.py` (7 tests), `tests/test_beta_profile.py` (8 tests), `tests/test_session_intelligence.py`, `tests/test_clear_memory_regression.py` (mixed, partly behavioural), `tests/test_learner_memory_migration.py`.
- Deployment-config files: **1** dedicated (`tests/test_deployment_hygiene.py`, 6 tests).
- Skipped/xfailed tests: **no `@pytest.mark.skip`, `skipif`, or `xfail` decorators exist anywhere** in `tests/`; all skipping is done at runtime via `pytest.skip(...)` calls (the `live_server` auto-skip in `conftest.py`, plus a handful of individual `pytest.skip` calls for missing Node or missing server, e.g. in `tests/test_e4_client_handoff_regression.py` and `tests/test_zh_en_synchronisation.py`).
- Local explicit-discovery audit (see §4's CI-scope note (B) for the full disclosure and environment caveat — this is **not** the CI-executed count): pointing `unittest` discovery explicitly at `tests/` locally enumerated **88** accounted test cases across **6** modules / **14** `TestCase` classes (`tests/test_conversation_fixes.py`, `tests/test_coverage_affordance.py`, `tests/test_open_card_resolver.py`, `tests/test_open_card_trace_integration.py`, `tests/test_open_card_wiring.py`, `tests/test_report_asr_traces.py`); **80** ran as real assertions and **8** were import-failure `_FailedTest` entries (a local-sandbox-specific error signature, not certified against CI). The remaining ~66 of the 72 `tests/test_*.py` files contain **no** `unittest.TestCase` subclass at all — they are pytest-style (plain functions and/or fixture-parametrised plain classes) and, if `unittest` attempts to import them, contribute **zero** test cases silently, with no error and no visible skip notice. Separately, the local exact-command result for the literal, unmodified CI step (bare `python -m unittest -v` from the repository root) was **zero tests** (§4's CI-scope note (A)). Whether the actual CI job reaches the 88-case enumeration, the zero-test result, or something else entirely is an open, unresolved question — **actual CI result not verified from a workflow log** — see §4.

Where exact counting was ambiguous (e.g. "how many files are purely mirrored"), the rule applied was: a file counts in a category only if that category is its **primary** verification mechanism for the majority of its assertions — files that mix a small static tail onto a mostly-mirrored body (like `verify_asr_filler.js`) are labelled hybrid in per-file tables (§10) but counted once, under their dominant mechanism, in aggregate counts here.

## 6. Server-side testing

Production server behaviour (`scripts/ui_server.py` and its collaborators) is tested through three distinct mechanisms, each bypassing a different part of the real request path:

1. **Direct private-function calls** (most common) — a test loads `ui_server.py` via `importlib` and calls a private helper directly (e.g. `_normalize_zh_for_routing`, `_direct_persona_answer`, `_infer_question_topic_engine`, `_scorecard_conversation_capability`). This bypasses JSON parsing, HTTP status handling, request-field construction, and response serialisation entirely — it tests the helper's logic in isolation from the HTTP layer.
2. **In-process real HTTP** — a test starts its own `ThreadedHTTPServer` on an ephemeral `127.0.0.1` port (e.g. `tests/test_spoken_question_routing_regression.py`, `tests/test_e4_client_handoff_regression.py`, `tests/test_contextual_place_asr_repair.py`, `tests/test_open_world_food_and_location_fixes.py`, `tests/test_stale_answer_loop_regression.py`) and POSTs to `/api/run_turn` via `urllib`. This exercises the full HTTP → JSON → handler → response pipeline for one process, without a browser client.
3. **External live server** — the 4 `live_server`-marked files and `scripts/test_counter_reply_matrix.py` assume `python scripts/ui_server.py` is already running on `localhost:8765` and POST to it exactly as a real client would, but still via `urllib`, not the browser.

A fourth, narrower mechanism exists in `tests/test_session_admin_endpoints.py`: it constructs a `Handler` instance with a **fake socket and `wfile`** and calls `do_GET()` directly — this bypasses real TCP entirely while still exercising the handler's routing and response-writing code for GET-only admin endpoints. No test calls `do_POST` this way.

None of these mechanisms exercise client-side JSON construction, `state_update` application, or DOM rendering — see §7 and §8. Link: `docs/CONVERSATION_ARCHITECTURE.md` (turn lifecycle), `docs/ANSWER_SOURCE_CONTRACT.md` (`counter_reply` production), `docs/STATE_CONTRACT.md` (state fields).

## 7. Client-side testing

`ui/app.js` coverage is limited to Node-executable mechanisms; there is no browser environment anywhere in the test system (§3.F).

- **Extracted real-helper tests**: only `_resolveNextEngineId` is extracted and executed as real code (via `_load_app_js_helper.js`), in `tests/e4_resolve_next_engine_id_cli.js` and directly in `tests/verify_e4_client_handoff.js`.
- **Mirrored JavaScript logic**: `tests/verify_asr_filler.js`, `tests/verify_spoken_recovery_exact_match.js`, and `tests/verify_phase12c.js` reimplement filler classification, spoken-recovery matching, and several unmatched-free-answer decision helpers respectively.
- **Static source assertions**: numerous Python tests (`tests/test_asr_thinking_grace.py`, `tests/test_asr_interim_latency.py`, `tests/test_mobile_layout.py`, `tests/test_translation_surfaces.py`, and others) read `ui/app.js`/`ui/styles.css` as text and assert on symbol names, constant values, or block ordering.
- **Node limitations**: category B/C tests never load `ui/app.js` as a whole module — only individually sliced or hand-copied functions run, so nothing that depends on `window`, `document`, `fetch`, or other module-scope state can be executed this way.
- **Event-handler testing, request-construction testing, state-update application testing**: **not executed anywhere** — these live inside `ui/app.js`'s DOM event listeners and `runTurn()`/`_runTurnInner()` bodies, which are only reachable through static source assertions on their text (e.g. `tests/verify_e4_client_handoff.js`'s static slice-and-assert section on `_runTurnInner`), never through execution.
- **ASR lifecycle testing**: entirely static/mirrored — no `SpeechRecognition` object is instantiated in any test.
- **Challenge Mode CSS/DOM testing**: static source checks only (e.g. `tests/test_challenge_recovery.py`'s client section asserts substrings like `"_spokenRecoveryPhrase"` in `app.js` text); no rendered DOM or CSS computed-style is ever inspected.
- **Fetch-error behaviour**: not exercised by any test — the client's `fetch` error handling in `ui/app.js` is only checked, if at all, via static text presence.

**Explicit statement:** the full `_runTurnInner()` client lifecycle is **not** executed in any automated browser environment, and is not fully executed even under Node — only the small number of functions extractable by `_load_app_js_helper.js` run as real code; the rest of the client turn lifecycle is verified, at best, by static source assertions about its shape.

**Why the extraction mechanism cannot cover more of `ui/app.js` today:** `_load_app_js_helper.js`'s slicing approach only works safely for short, self-contained top-level function declarations with no meaningful reliance on outer closures or module-scope globals (`window`, `document`, cached DOM references, in-flight fetch state). Most of the client turn lifecycle — `runTurn`, `_runTurnInner`, `listenForResponse`, the recognizer `onresult`/`onerror` handlers — either spans hundreds of lines, closes over module-scope mutable state, or both, which is why they are only referenced through static text checks rather than sliced and executed. Extending coverage here would require either a real browser/DOM harness (§3.F, currently absent) or a deliberate refactor of `ui/app.js` to expose more logic as pure, extractable functions — the latter is a code-architecture decision outside this document's scope, and any such refactor should be proposed against `docs/ARCHITECTURE.md`'s extensibility rules, not driven by test convenience alone.

## 8. Client/server contract testing

- **Request payload shape / `conversation_state.last_answer`**: constructed directly by Python test code in every in-process and live-server HTTP test (e.g. `tests/test_interaction_regression.py`, `tests/test_e4_client_handoff_regression.py`) — these tests build the JSON payload themselves rather than using the real browser client to build it, so they verify the **server's** acceptance of a given shape, not that `ui/app.js` actually produces that shape.
- **`state_update` consumption**: no automated test applies a real `state_update` response back into a real client and observes the next request — `tests/test_e4_client_handoff_regression.py` is the strongest cross-boundary approximation available (see below) by combining a real in-process `/api/run_turn` request with a call to the real extracted `_resolveNextEngineId()` helper to compute what the client *would* set `window._currentEngineId` to, but it does not exercise the DOM/state-object merge that `_runTurnInner()` performs around that helper call.
- **`data.engine_id` versus future `state_update.current_engine`**: covered on the server side by direct assertions on the HTTP response body in the E4 test files; the client-side consumption of `current_engine` for the *following* request is only covered via the extracted-helper mechanism above, not end-to-end.
- **English/pinyin fields**: covered by static/behavioural server-side tests (e.g. `docs/ANSWER_SOURCE_CONTRACT.md`'s own inventory); no client-side rendering of these fields is tested.
- **Reset semantics, current-response versus following-turn behaviour, persistence across requests**: covered server-side by tests that issue multiple sequential requests against the same in-process or live server and inspect the returned `state_update` across turns (e.g. `tests/test_stale_answer_loop_regression.py`, `tests/test_e4_client_handoff_regression.py`).

**Separation:** tests that construct payloads directly (the large majority) versus tests that use the real browser client (**none exist**) versus tests that make real HTTP calls (the in-process and live-server files) versus tests that simulate only one side of the contract (most direct-private-function tests, and the mirrored JS tests).

**Strongest current automated cross-boundary approximation:** `tests/test_e4_client_handoff_regression.py`, which combines an in-process real HTTP request to `/api/run_turn` with the extracted-real-JavaScript-helper mechanism (§3.B) calling the real `_resolveNextEngineId()`.

**What this exactly proves:**
- A test-built `/api/run_turn` request reaches real server code.
- The server returns `state_update.current_engine` for that request.
- The real, extracted `_resolveNextEngineId()` helper — sliced verbatim from `ui/app.js`, not reimplemented — resolves that field correctly given the server's actual response.

**What this does not prove:**
- That a real browser constructs the originating request correctly.
- That `_runTurnInner()` performs the real state merge correctly around its call to `_resolveNextEngineId()`.
- That `window._currentEngineId` is actually updated in a live page.
- That the following request, built by the real client, carries the resolved value forward.
- Any DOM, event-listener, or `fetch`-lifecycle behaviour.

**No automated full client/server round-trip test exists at the R2 baseline.** This is the strongest cross-boundary approximation currently available, on one specific field, and it is real production code on both sides of that one field — but "cross-boundary approximation" and "full round trip" are not interchangeable claims, and this document uses only the former.

## 9. Conversation-regression testing

- **Answer-source priority**: `scripts/test_counter_reply_matrix.py` (live server, writes a report), plus direct private-function tests scattered across many files (e.g. `tests/test_spoken_chinese_routing.py`, `tests/test_meaning_recovery.py`).
- **Direct-persona questions / E3 (working memory)**: `tests/test_conversation_first_wave.py` calls real `_answer_from_working_memory` and separately checks a static flag string; `tests/test_learner_led_followup_questions.py` calls real working-memory extraction helpers.
- **Mirror questions**: covered by `tests/test_interaction_regression.py` (live_server, `direction_intent: "mirror"` payloads) and by a static content check in `tests/test_golden_regression.py` against `content/mirror_questions.json`.
- **E4**: `tests/test_e4_topic_handoff.py` mixes real `_infer_question_topic_engine`/`_direct_persona_answer` calls with a mirrored setup helper (`_simulate_dp_e4`) that reproduces the branch conditions before calling the real answer function; `tests/test_e4_client_handoff_regression.py` combines in-process HTTP with the extracted real client helper (§7, §8).
- **Deduplication / stale-answer loops**: `tests/test_stale_answer_loop_regression.py` is a real in-process HTTP test asserting adjacent turns don't return an identical reply; `tests/test_stale_counter_reply_loop.py` and `tests/test_stale_override_multiturn.py` are **mirrored-logic** tests that reimplement the routing decision (calling some real helper functions from within the mirror) rather than exercising the real `run_turn` control flow directly.
- **Recovery**: see §10.
- **Frustration/disclosure/challenge overrides**: `tests/test_friction_signals.py` calls real `session_intelligence.compute_friction_signals`; `tests/test_conversation_fixes.py` mixes real private-function calls with static guard checks; `tests/test_regression_surgical_transcript.py` mixes real calls (`_is_frustration_or_insult`, `_frustration_repair_reply`) with a mirrored routing helper; `tests/test_closing_move_suppression.py` is purely static.
- **Frame progression / engine handoff**: `tests/test_e4_topic_handoff.py`'s `test_next_frame_engine_place_is_in_frame_order` is a real check against the live `_FRAME_ORDER` structure.
- **Persona switching**: no test file name or content matched `persona_switch` in this audit — treat persona-switch behaviour as **not separately regression-tested** at this baseline; verify against `docs/STATE_CONTRACT.md`'s reset section by manual/live-server testing until a dedicated test exists.
- **English and pinyin alignment**: `tests/test_zh_en_synchronisation.py` is a **dedicated** file for this, not incidental coverage — see below. Repeated-turn behaviour more generally is still covered only incidentally inside the live-server golden/interaction files rather than by a dedicated isolated test.

**`tests/test_zh_en_synchronisation.py` — dedicated Chinese/English/pinyin-alignment file.** Its own docstring states the governing invariant directly: "the final Chinese `counter_reply` is the source of truth; English must correspond to the exact final Chinese sentence." Classification by section, verified by reading the file in full:

- `TestHometownSpecialNoCrossCity`, `TestAgeNoCrossSubject`, `TestWorkDurationNoCrossContent`, `TestMirrorBankTranslationsPreserved`, `TestDeduplicationEnglishSync`, `TestServerEmptyEnSignal`, `TestPinyinEnglishSameSource` — **real Python direct-function tests (category A)**. All load `scripts/ui_server.py` via a module-scoped `srv` fixture (`importlib.util.spec_from_file_location`, executed lazily inside the fixture, not at import time) and call real functions directly: `_reverse_fact_answer_en`, `_persona_answer_en`, `_find_mirror_answer`, `_dedupe_persona_answer`, `_detect_reverse_fact_intent`, `_resolve_counter_reply_pinyin`. These test exactly the three historically-broken cross-subject/cross-city English-substitution defects the file's docstring names, plus the pinyin/English same-source invariant.
- `TestClientGlossPathContract` — **static source-verification (category D)**. Its own class docstring states the reason precisely: the client-side gloss routine "is implemented in JavaScript (`ui/app.js`) and runs in the browser; we validate the contract by reading the shipped source" — this is an explicit, self-disclosed acknowledgement that no client execution occurs here.
- `TestLiveServerSynchronisation` — **live HTTP, but not through the `live_server` marker mechanism.** It defaults to `http://localhost:8080` (not 8765) via a `server_url` fixture reading `MANDARINOS_SERVER_URL`, and each test wraps its request in `try/except` with `pytest.skip("Server unavailable")` on failure — a per-test ad hoc skip, not `pytest.mark.live_server`/`skipif`. The file also defines a module-level `pytest_configure(config)` function, but pytest only invokes `pytest_configure` hooks discovered in plugins/`conftest.py`, not in ordinary test modules — this function is dead code with no effect; its `"live"` marker registration never actually happens. Because this file carries no `pytestmark = pytest.mark.live_server`, its tests **are** collected and attempted under `python -m pytest tests/ -m "not live_server"`, and degrade to a skip (not a failure, not a silent pass) if nothing is listening on port 8080.
- **`python -m unittest -v` does not execute any of this file's content, under any discovery root.** Its test classes (e.g. `class TestHometownSpecialNoCrossCity:`) are plain classes with no `unittest.TestCase` base — pytest fixture-injected style — so `unittest`'s loader does not recognise them as containing tests at all. The module itself imports cleanly under `unittest` (no module-level `ui_server` import, no problematic side effect), so it contributes **zero** test cases silently with no error reported — a concrete, verified instance of the general rule stated in §4's CI-scope note.

**Scope, stated precisely:** this file provides dedicated, real, production-code coverage of **server-side** Chinese/English/pinyin generation and pairing invariants. It does not test HTTP serialisation of those fields beyond the three `TestLiveServerSynchronisation` scenarios (which are best-effort and self-skip), and it does not test client rendering of English/pinyin at all — `TestClientGlossPathContract` explicitly substitutes source inspection for client execution because none exists. Do not describe this file as covering client-side gloss rendering or as a `live_server`-tier file.

**Limitations by style:**
- **Matrix-style** (`scripts/test_counter_reply_matrix.py`) exercises many scenarios against a live server but is a standalone reporting script, not a pass/fail pytest suite gating CI.
- **Golden scenarios** (`tests/test_golden_regression.py`, `tests/test_golden_conversation_scenarios.py`) are **not** snapshot/diff tests against a fixed expected-output file — they assert behavioural invariants (e.g. a particular phrase must not appear, a particular field must be set) over live HTTP responses. The only true golden-JSON diff test found anywhere in the suite is `tests/test_open_card_trace_integration.py` against `tests/fixtures/traces/open_card_fired.golden.json`, and it runs in-process against `runtime.engine.process_turn`, not through HTTP.
- **Isolated regression tests** (single-file, direct-function) are fast and precise but, by construction, cannot catch a defect in the HTTP/response-assembly layer around the function they call.
- **Live-server scenarios** are the broadest coverage available but require a manually started server, are excluded from CI (§4), and cannot run unattended.

## 10. ASR and recovery testing

| Test | Classification | Evidence |
| ---- | -------------- | -------- |
| `tests/verify_asr_filler.js` | Hybrid — mirrored body + static tail | Header states "mirrors ui/app.js logic"; hand-copies `normalizeForMatch`, `_isSufficientLinguisticSignal`, `classifyFillerDecision`; final section reads `ui/app.js` text and asserts wiring strings (`fillerExtendFired`, `SPEECH_FILLER_EXTEND_MS`) |
| `tests/test_asr_filler_suppression.py` | Hybrid — static + subprocess to the mirrored JS above | Asserts substrings in `app.js`; splits server source text; separately runs `subprocess.run(["node", verify_asr_filler.js])` |
| `tests/verify_spoken_recovery_exact_match.js` | Hybrid — mirrored logic + static drift guard + real JSON fixture | Mirrors `matchTranscriptToLearnerPhrase`/`matchSpokenRecoveryPhraseExact`; static guard on `app.js`; loads real `content/recovery_phrases.json` as input data (not as an expected-output diff) |
| Thinking-grace tests (`tests/test_asr_thinking_grace.py`) | Static source-text | Self-described "static regression checks"; asserts ordering/presence of `_startThinkingGrace`, `ASR_THINKING_GRACE_MS`, etc. in `ui/app.js` text |
| Interim-latency tests (`tests/test_asr_interim_latency.py`) | Static source-text | Self-described static checks on `ui/app.js`/`ui/styles.css` |
| Contextual-place repair tests (`tests/test_contextual_place_asr_repair.py`) | Hybrid — real production Python + in-process HTTP | Loads `ui_server.py` via `importlib`; unit-calls `_repair_contextual_place_question` directly; also spins its own `ThreadedHTTPServer` and POSTs `/api/run_turn` |
| Spoken-question routing tests (`tests/test_spoken_question_routing_regression.py`) | Hybrid — in-process HTTP + direct helper calls | Docstring states it drives the real `/api/run_turn` path in-process; also calls `_is_place_feature_question`/`_extract_travel_destination` directly |
| `tests/test_challenge_recovery.py` | Hybrid — static + real module import + mirrored `_is_rr_simulate` | Loads real `ui_server` module for constant checks; greps `server_src`/`app_js_src` for wiring; `_is_rr_simulate` reimplements the server's `_is_rr` check for parametrised cases |
| `tests/test_report_asr_traces.py` | Real production Python | Loads `scripts/report_asr_traces.py` via `importlib`; calls `build_rows`/`summarize`/`main` against temp JSONL fixtures |

**Current known gap** (unresolved at this baseline):

> Most browser SpeechRecognition lifecycle behaviour is not exercised in a real browser automation environment.

This is consistent with §3.F: no browser exists in the test system at all, so this gap applies to the entire ASR client lifecycle, not just SpeechRecognition specifically.

## 11. State and persistence testing

| Area | Coverage | Type |
| ---- | -------- | ---- |
| Same-tab new-session reset / page reload assumptions | `tests/test_session_start_reset.py` — static-only, reads `ui/app.js` for `_resetCurrentSessionState`/`startFreshLearner` wiring | Static source assertion |
| Persona switch | No dedicated test file found (see §9) | Operational assumption, not proved by any current test |
| `conversation_state` merge | Covered incidentally by live-server/in-process HTTP multi-turn tests, not by a dedicated merge-semantics test | Behavioural, indirect |
| Unconsumed `state_update` fields | Not directly tested — `docs/STATE_CONTRACT.md` is the authority for which fields exist; no test enumerates consumed-vs-emitted fields | Documentation-only fact, not test-proved |
| Learner memory clear/save | `tests/test_clear_memory_regression.py` (real `learner_memory.py` on `tmp_path` via an env-restoring fixture, plus static wiring checks for `/api/reset_memory` and client `startFreshLearner`); `tests/test_learner_memory_migration.py` (real module, `tmp_path`) | Behavioural (real module) + static (wiring) |
| Progress snapshots | `tests/test_progress_store.py` — 7 real behavioural tests (`test_save_and_load_snapshot`, `test_unknown_learner_returns_empty`, `test_two_learners_isolated`, `test_dedupe_by_session_id`, `test_invalid_learner_id_rejected`, `test_load_all`, `test_persists_to_disk`) redirecting `progress_store._PROGRESS_DIR` to `tmp_path` | Behavioural (real module) |
| Session capture gating | `tests/test_session_intelligence.py` — reloads `session_intelligence` with `MANDARINOS_SESSION_CAPTURE` explicitly `""` (off) or `"1"` (on) and `MANDARINOS_DATA_DIR` pointed at `tmp_path`; covers schema, sanitisation, validation, and the disabled path | Behavioural (real module), both flag states |
| Beta profiles | `tests/test_beta_profile.py` — 8 real behavioural tests, same `tmp_path`-redirect pattern as progress store | Behavioural (real module) |
| Diagnostics | No test references `MANDARINOS_DIAG_TOKEN` or exercises `diag/asr_traces.jsonl` writing | Untested |
| Railway volume behaviour | Not testable by any local unit test — this is an operational configuration fact (Railway dashboard Volume + `MANDARINOS_DATA_DIR=/data`), not code | Operational assumption |

**Distinguishing:** behavioural filesystem tests (progress, beta profile, session intelligence, learner memory) actually write to and read from `tmp_path`, giving real evidence of module I/O correctness. Source assertions (session-start reset, `/api/reset_memory` wiring) only confirm text presence. Railway volume behaviour is an operational fact not provable by any repository-local test as currently written, but is verifiable operationally (Railway dashboard inspection, or a direct check of the mounted volume's contents); persona-switch state clearing is a coverage gap, not an operational fact — it is a missing regression test, addable with current tooling. See §17 for this distinction applied consistently.

## 12. Generated-artifact testing

- `tools/build_runtime_artifacts.py` itself is **not** imported or executed by any test.
- `tools/builders/build_frame_tokens_runtime.py`'s `tokenize`/`build_hanzi_lookup` functions **are** tested directly by `tests/test_build_frame_tokens_runtime.py`, including one temp-file-based duplicate-hanzi case.
- No test validates the schema of any file under `runtime/out_phase7/`.
- No test compares source content (`p1_frames.json`/`p2_frames.json`, `content/recovery_phrases.json`) against the corresponding generated artifact for consistency.
- `tests/test_golden_regression.py` optionally reads `runtime/out_phase7/recovery_phrases.runtime.json` in exactly one static test and **skips** (does not fail, does not trigger a rebuild) if the file is missing.
- No test regenerates artifacts automatically as part of setup; `tests/conftest.py` has no fixture that calls the builder.
- As established in `docs/ARCHITECTURE.md` §14: `scripts/ui_server.py` does not regenerate artifacts at startup, and Railway's configured build/start process does not run the builder either — regeneration is manual-only (`python tools/build_runtime_artifacts.py`) both for local runs and for tests.

> A test passing against stale generated artifacts does not prove the edited source content is active.

Concretely: editing `p2_frames.json` and re-running `tests/test_golden_regression.py --static-only` will not detect that `runtime/out_phase7/frame_options.runtime.json` still reflects the old content, because no test in this repository checks that relationship.

**Deployment obligation for a builder or generated-input change.** Reconciling this section with `docs/ARCHITECTURE.md`'s approved findings: `runtime/out_phase7/*.runtime.json` is gitignored (not committed to source control); regeneration is explicit-only (`python tools/build_runtime_artifacts.py`); `scripts/ui_server.py` does not regenerate artifacts at its own startup; and Railway's current build/start configuration does not run the builder either. This means a code commit that changes a builder or a generated-input JSON file does **not**, by itself, guarantee the deployed environment is serving the corresponding output — the required steps are:

1. Run `python tools/build_runtime_artifacts.py`.
2. Inspect or diff the generated output locally against the pre-change version.
3. Run the relevant builder/content test(s) (§12, §3.G) against the regenerated output.
4. Verify the local application is actually reading the regenerated output (e.g. restart `scripts/ui_server.py` and confirm its own startup log — see `docs/ARCHITECTURE.md` — reflects the new counts/content).
5. Identify the current mechanism, if any, that provisions those generated files into Railway's deployed environment, and verify that it will correctly provide the regenerated files. Regeneration is explicit-only; there is no discovered mechanism by which committing a gitignored output would become part of this repository's normal deployment path, and this document does not introduce one. If no such provisioning mechanism is found to exist, the builder/generated-input change is **not production-ready** — even if its code commit deploys successfully — until one is identified, implemented, and verified. Selecting or changing the packaging/provisioning architecture is outside this document's scope; this document only states that step 5 must be answered, with a verified mechanism, before the change can be considered deployable.

**`/api/version` cannot verify any of this.** State explicitly: `/api/version` verifies **code identity only** — the deployed git commit SHA and branch; it cannot verify generated-artifact identity or freshness, because the artifacts are not part of the versioned code path it reports on. A builder-only or source-input change does not become production-effective merely because its code commit was deployed, if the required generated output is absent or stale in that deployment. Deployment verification for this change type must include an artifact-dependent functional smoke scenario (a behaviour that would visibly differ between old and new generated content) or another direct check of the deployed artifact state — `/api/version` alone is not sufficient evidence, and must not be treated as sufficient evidence, for this change type. This is a description of the current limitation and the resulting verification obligation, not a proposal for a new packaging or deployment architecture.

## 13. Change-to-test matrix

**How to select a minimal test set.** Do not default to running the entire repository for every change — identify the minimal set using this procedure, then widen only if evidence suggests shared code was touched:

1. Identify which file(s) changed and map each to the "Change type" rows below; a single commit touching multiple areas requires the union of their rows, not just the most obvious one.
2. Check whether the changed code is on the answer-source priority chain, the frame-selection path, or the state-transport boundary (`docs/ARCHITECTURE.md` §16's high-risk list) — if so, always widen to the full core suite regardless of how small the diff looks, because these are shared control-flow paths where an isolated-looking change can alter unrelated outcomes.
3. If the change is confined to content-only files (a single persona fact, a single frame's text) with no code change, the minimum is the specific test(s) that already exercise that fact or frame, plus a static/golden check if one exists for that content family — do not require the live-server suite unless the content is reachable through a scenario already covered there.
4. If the change touches a generated-artifact builder or its inputs, always regenerate artifacts (`python tools/build_runtime_artifacts.py`) before running any test that reads a runtime file, and say so explicitly in the test report (§20) — a green result against stale artifacts is not evidence of anything (§12).
5. Known regression exposures — areas that have broken before and are not fully closed by a hard test gate — are the answer-source priority chain (§9, §17 item 1) and E4 cross-turn timing (§9); treat any change anywhere near these paths as requiring the full core suite even if the diff itself looks small.
6. When in doubt about whether a change is "small," prefer running the full core non-live suite — it does not require a server or Node availability beyond the two individual `subprocess`-invoked Node tests (which self-skip if Node is absent), so its cost is low relative to the risk of missing a shared-path regression.

| Change type | Minimum targeted tests | Mandatory broader suite | Live/deployment verification | Documentation to review |
| ----------- | ---------------------- | -------------------------- | -------------------------------- | -------------------------- |
| Documentation-only change | None | None | None | The document being changed |
| Persona JSON change (`personas/*.json`) | Any test directly exercising the changed fact (e.g. add/extend an answer-source test) | `pytest tests/ -m "not live_server"` | Local `live_server` suite recommended if the persona is reachable via a live scenario; no deployment required unless shipping | `docs/ANSWER_SOURCE_CONTRACT.md` |
| Recovery phrase-bank change (`content/recovery_phrases.json`) | See the expanded requirements immediately below this table | Core suite; regenerate artifacts (`python tools/build_runtime_artifacts.py`) before any test that reads the runtime file | Real-browser verification required before shipping — see below; this is a generated-artifact-dependent change, so §12's 5-step deployment obligation (regenerate, inspect, verify locally, identify/verify deployed provisioning, deployed artifact-dependent smoke) applies in full, and `/api/version` alone is not sufficient | `docs/ASR_PIPELINE.md` §7–§8 |
| Frame-content change (`p1_frames.json`/`p2_frames.json`) | `python tests/test_golden_regression.py --static-only`; regenerate artifacts first | Core suite; `live_server` suite | `live_server` suite required before deploy if frame ordering/content is deploy-bound; this is a generated-artifact-dependent change (`frame_options.runtime.json`), so §12's 5-step deployment obligation applies in full, and `/api/version` alone is not sufficient | `docs/CONVERSATION_ARCHITECTURE.md` |
| Generated-artifact builder change (`tools/build_runtime_artifacts.py`, `tools/builders/*`) | `tests/test_build_frame_tokens_runtime.py`; manually diff generated output before/after | Core suite; regenerate and re-run `test_golden_regression.py --static-only` | Follow §12's 5-step deployment obligation in full; `/api/version` alone is **not** sufficient (it verifies code identity only, not artifact freshness) — an artifact-dependent functional smoke check or direct artifact-state check is also required | `docs/ARCHITECTURE.md` §14; this document §12 |
| Answer-source priority change (`scripts/ui_server.py` priority chain) | The specific producer's direct-function test (e.g. `tests/test_spoken_chinese_routing.py`, `tests/test_e4_topic_handoff.py`); `scripts/test_counter_reply_matrix.py` against a local server | Full core suite (this is shared, high-risk code — §16) | `live_server` suite; deployed `/api/version` + smoke check | `docs/ANSWER_SOURCE_CONTRACT.md` |
| Frame-selection change | `tests/test_e4_topic_handoff.py`'s `_FRAME_ORDER` check; any test touching the changed engine | Core suite; `live_server` suite | Deployed smoke check | `docs/CONVERSATION_ARCHITECTURE.md` |
| State-field addition/change (`conversation_state`/`state_update`) | Add a targeted test in the relevant contract-boundary file; extend `tests/test_e4_client_handoff_regression.py`-style coverage if the field affects E4 | Core suite | `live_server` suite; deployed smoke check | `docs/STATE_CONTRACT.md` |
| Reset-logic change | `tests/test_session_start_reset.py`; `tests/test_clear_memory_regression.py` | Core suite | `live_server` suite recommended (no automated reset-across-live-turns test exists) | `docs/STATE_CONTRACT.md` reset section |
| E4 change | `tests/test_e4_topic_handoff.py`; `tests/test_e4_client_handoff_regression.py` (requires Node) | Core suite | `live_server` suite; deployed smoke check | `docs/CONVERSATION_ARCHITECTURE.md` E4 section |
| ASR client change (`ui/app.js` recognizer/recovery code) | The relevant mirrored/extracted JS test(s) from §10, updated to match; `node tests/verify_asr_filler.js` and/or `node tests/verify_spoken_recovery_exact_match.js` as applicable | Core suite | No automated production ASR check exists; manual smoke test in a real browser after deploy | `docs/ASR_PIPELINE.md` |
| Challenge Mode UI change | `tests/test_challenge_recovery.py` | Core suite | Manual browser smoke check (no DOM automation exists) | `docs/ASR_PIPELINE.md` §14 |
| English/pinyin change | The relevant answer-source test; check `_repair_asr_junk_text` call sites if repair logic changes | Core suite | `live_server` suite | `docs/ANSWER_SOURCE_CONTRACT.md` |
| Learner-memory change | `tests/test_clear_memory_regression.py`; `tests/test_learner_memory_migration.py` | Core suite | `live_server` suite recommended | `docs/STATE_CONTRACT.md` |
| Progress/session-capture change | `tests/test_progress_store.py`; `tests/test_session_intelligence.py` | Core suite | `live_server` suite recommended | `docs/ARCHITECTURE.md` §6.4 |
| API endpoint change (`scripts/ui_server.py` `/api/*`) | Direct handler test if one exists for that endpoint (e.g. `tests/test_session_admin_endpoints.py` for admin GET routes); otherwise a new in-process HTTP test | Core suite | `live_server` suite; deployed `/api/version` + smoke check | `docs/ARCHITECTURE.md` §12 |
| Deployment configuration change (`railway.toml`, `Procfile`, `nixpacks.toml`) | `tests/test_deployment_hygiene.py` | Core suite | **Required**: push to Railway-watched branch, verify `/api/version`, smoke check | `docs/ARCHITECTURE.md` §13 |

Do not require Railway deployment for documentation-only changes (per §17 of `docs/ARCHITECTURE.md` and §19 below). For high-risk changes (answer-source priority, frame selection, state-field, E4, deployment configuration) all of: targeted regression test; core non-live suite; relevant Node/client verification where applicable; local `live_server` tests; deployed `/api/version` verification if production code is deployed; and a direct production behaviour check are required together, not as alternatives.

**Expanded requirements for a recovery phrase-bank change (`content/recovery_phrases.json`).** This row needs more than the table cell can hold, because the change's most important effect — client-side spoken interception — is the one area no local test can verify.

*Required local verification:*
1. Regenerate runtime artifacts (`python tools/build_runtime_artifacts.py`) — the recovery runtime file is generated, not hand-maintained (§12).
2. Inspect the regenerated `runtime/out_phase7/recovery_phrases.runtime.json` directly and confirm the intended phrase/action actually appears in it — do not assume the builder mapped the source content as expected.
3. Run `node tests/verify_spoken_recovery_exact_match.js`, and add or update phrase-specific test cases as needed. Do **not** modify the mirrored matching algorithm merely to make new phrase data pass — change the mirrored algorithm only when the production matching algorithm itself has intentionally changed. Always disclose that this verifier does not execute the shipped client matcher, and label it explicitly as **hybrid/mirrored evidence**, not behavioural proof that the real shipped client would intercept the phrase (§3.C).
4. Run the core suite (`pytest tests/ -m "not live_server"`).

*Required browser verification when the change is shipped* (no automated substitute exists for any of the following, per §3.F):
1. Load the real application in a supported browser.
2. Speak the new/changed phrase and verify it is intercepted client-side.
3. Verify no `/api/run_turn` request occurs for an intercepting action (inspect the network panel) — this is the behaviour the interception branch exists to produce.
4. Speak a genuine longer utterance that merely contains similar words and verify it is **not** falsely intercepted.
5. Verify `"next_turn"` or other non-intercepting actions still reach the server as intended (i.e. the change did not overbroaden interception).

**Server `live_server` tests cannot prove client interception, structurally, not just by omission.** The client-intercepted recovery branch (`docs/ASR_PIPELINE.md`) is defined by never reaching `/api/run_turn` in the first place — by construction, any test that observes only server-side HTTP traffic (the entire `live_server` tier and every in-process HTTP test) cannot see, and therefore cannot verify, an interception that succeeded. A green `live_server` suite after a recovery phrase-bank change says nothing about whether the new phrase is actually intercepted client-side; only the manual browser verification above can establish that.

## 14. Regression-test design rules

1. Reproduce the original failure before writing the fix — confirm the new test fails against the pre-fix code.
2. Assert the user-visible or contract-level outcome (a response field, a returned string, a persisted file's content), not only an internal implementation detail that could pass while the real defect remains.
3. Use real production code where practical — import and call the actual function rather than reimplementing its logic in the test.
4. Avoid copying the production algorithm into the test; where a mirror is unavoidable (e.g. no extraction mechanism exists for the language/scope involved), label it explicitly as mirrored in the test's own docstring/header, following the existing convention in `tests/verify_*.js`.
5. Test both positive and negative cases — that the new behaviour fires when it should, and does not fire when it should not.
6. Test ordering when priority chains are involved (answer-source, frame selection) — a new producer inserted in the wrong position can silently change unrelated outcomes (`docs/ARCHITECTURE.md` §16).
7. Test current-turn and following-turn behaviour separately when state transport is involved — many defects are a one-turn timing confusion (e.g. E4's one-response handoff delay).
8. Test reset and persona-switch implications when state is involved, even though no dedicated persona-switch test currently exists (§9) — new state fields should not assume this gap will be filled by an unrelated test.
9. Test English/pinyin pairing whenever Chinese text is replaced or repaired — `_repair_asr_junk_text()`'s final call sites are a known place where pairing can silently drift (`docs/ASR_PIPELINE.md` §11).
10. Test client and server separately only when the contract boundary between them is also covered elsewhere (§8) — otherwise a client-only or server-only test can create false confidence about the round trip.
11. Name the regression or historical defect where useful (several existing files already do this, e.g. `tests/test_stale_answer_loop_regression.py`, `tests/test_e4_client_handoff_regression.py`) — this preserves institutional memory of why the test exists.
12. Keep fixtures minimal and deterministic — prefer `tmp_path` and explicit dict/JSON fixtures over shared mutable module state; avoid the kind of unguarded module-level `import ui_server` seen in `tests/test_open_world_food_and_location_fixes.py` (§16) for any new test that touches persistence.

**When static assertions are justified:** wiring/guardrail checks where the thing being verified genuinely is the text itself (a Procfile string, a forbidden-symbol absence, a required constant name existing) — not as a substitute for behavioural coverage of logic that has a real execution path available (real Python import, or the JS extraction mechanism in §3.B).

## 15. Evidentiary weight

| Evidence | Relative strength | Appropriate claim |
| -------- | ------------------ | -------------------- |
| Deployed production reproduction at the expected commit | Strongest | "This works in production as of commit X" |
| Real browser/client + real server automated test | Would be strongest for client claims — **does not currently exist** in this repository | N/A at this baseline |
| Local real HTTP client/server test (in-process or `live_server`) | Strong for server-side round-trip claims | "The server correctly handles this HTTP request/response shape locally" |
| Real production server function/handler test (direct import, no HTTP) | Strong for the specific function's logic | "This function behaves correctly for these inputs" |
| Extracted real-JavaScript helper execution | Strong for that one function only | "This specific extracted client helper behaves correctly in isolation" |
| Generated-artifact behavioural test | Moderate | "This builder function produces the expected structure for these inputs" |
| Static source assertion | Weak, but legitimate for its narrow purpose | "This exact text/symbol is present in the file at this commit" |
| Mirrored-logic test | Weak for production-correctness claims, useful for internal consistency of the mirror | "This reimplementation's own logic is internally consistent" — never "the shipped function is correct" |
| Comment, filename, or historical document | Weakest | Context/intent only — never behavioural evidence (see `docs/ARCHITECTURE.md` §3) |

Strength depends on the claim being made, not an absolute ranking: a real-module unit test is the *strongest available* evidence for a pure function's correctness (nothing stronger is needed or exists for that claim); a production smoke test is *necessary*, not merely nice-to-have, for any claim about deployed behaviour, no matter how thorough the local suite is; a real browser test would be *necessary* for any claim about DOM/event behaviour, and since none exists, no such claim can currently be made with automated evidence — only manual verification can support it.

## 16. Test isolation and determinism

- **Temporary data directories**: the standard, safe pattern used by `tests/test_progress_store.py`, `tests/test_beta_profile.py`, `tests/test_session_intelligence.py`, `tests/test_clear_memory_regression.py`, `tests/test_learner_memory_migration.py`, and the behavioural half of `tests/test_deployment_hygiene.py` is either patching the module's private path constant (e.g. `mod._PROGRESS_DIR = tmp_path / "progress"`) or setting `MANDARINOS_DATA_DIR` to `tmp_path` before/during import.
- **Monkeypatching environment variables**: `tests/test_deployment_hygiene.py` uses both a manual save/restore dict and pytest's `monkeypatch.delenv`; `tests/test_clear_memory_regression.py` and `tests/test_learner_memory_migration.py` manually save and restore `os.environ["MANDARINOS_DATA_DIR"]` in a `finally` block or fixture teardown; `tests/test_session_intelligence.py` and `tests/test_session_admin_endpoints.py` use `unittest.mock.patch.dict`, which restores automatically.
- **Global state reset / module import side effects**: many tests `del sys.modules["<module>"]` before re-importing with different env vars (e.g. `session_intelligence` in `tests/test_session_intelligence.py`) — this is necessary because Python caches modules, and a stale cached module would silently ignore a changed environment variable on a second `import`.
- **Fixed ports**: the in-process HTTP test files each pick their own literal ephemeral port numbers in the 8990s range (e.g. `127.0.0.1:8991`, `8993`, `8996`) to avoid colliding with the real `localhost:8765` server or each other; these are hardcoded, not dynamically allocated, so two of these test files running concurrently on the same port would collide (not verified as currently occurring, since pytest runs test files sequentially within one process by default).
- **Server-process lifecycle**: in-process servers are started and torn down per test/module via `ThreadedHTTPServer` `shutdown()`/thread-join patterns local to each file; the `live_server` suite has no lifecycle management at all — the server is external and outlives the test run.
- **Generated files**: `tests/test_progress_store.py`'s `test_persists_to_disk` and similar tests write real files under `tmp_path`, which pytest cleans up automatically; no test writes generated `runtime/out_phase7/` artifacts.
- **Time-based ASR/dedup windows**: not independently verified in this audit; treat any time-window-dependent test (e.g. involving `SPEECH_FILLER_EXTEND_MS` or dedup timing) as a candidate for flakiness until specifically re-audited — no evidence either way was gathered.
- **Randomisation**: no test file was found to use non-deterministic randomisation without a fixed seed in the areas audited; not exhaustively verified across all 72 files.
- **Test ordering assumptions**: no `@pytest.mark.order` or explicit ordering dependency was found. However, module-scoped fixtures that load `ui_server`/`learner_memory`/other modules once per file (e.g. `lm` in `tests/test_clear_memory_regression.py`, `srv`/`lmc` in `tests/test_regression_surgical_transcript.py`) could carry stale state into later tests within the same file if a test mutates rather than only reads that shared module object — not confirmed as an actual defect, flagged as a risk pattern.
- **Shared files under `data/`**: `tests/test_open_world_food_and_location_fixes.py` and `tests/test_stale_answer_loop_regression.py` `import ui_server as srv` at module level **without** overriding `MANDARINOS_DATA_DIR` first — since `ui_server.py` binds its base data directory from the environment at import time, these two files' in-process HTTP turns run against whatever data directory the environment specifies (the real repo `data/` directory by default). This is a genuine identified contamination risk: if a turn triggers persistence (e.g. learner-memory capture), it could write into the real `data/` directory rather than a temp one. This was not confirmed to actually write during a normal test run (that would require tracing which specific turns in those files trigger a capture), but the absence of an env override is a fact, not a speculation.
- **Cleanup requirements**: `tmp_path`-based tests require no manual cleanup (pytest handles it); the two files above have no cleanup mechanism for the risk described, because they are not writing to a directory they control.

Do not speculate beyond what was verified above — the ASR/dedup timing-window and full-repository randomisation checks are explicitly marked as not independently re-verified in this pass.

**Determinism expectation for the core suite.** `tests/conftest.py`'s own docstring states the core (`-m "not live_server"`) tier should have "zero failures expected" and requires no pre-started external server, no external internet access, and no credentials; some tests start local loopback HTTP servers within the test process (§4, §6) — that qualification does not weaken the determinism expectation, since those servers are self-contained and torn down per test/module. Treat any nondeterministic failure in that tier as a genuine defect (in the test or in the isolation pattern it uses) rather than as expected flakiness, and fix the isolation pattern rather than re-running until green.

## 17. Known coverage gaps

Evidenced at this baseline:

- **No full browser automation** — confirmed absence of any browser/DOM test framework (§3.F).
- **No real microphone/SpeechRecognition automation** — a consequence of the above; all ASR-lifecycle coverage is mirrored or static (§10).
- **No full client/server round-trip test exists** — the strongest current automated evidence for the client/server contract is a cross-boundary approximation covering exactly one field (`current_engine`) via one combined mechanism (§8); no test exercises a full `conversation_state`/`state_update` round trip through real client code, and none should be described as doing so.
- **Mirrored/static ASR tests** — `tests/verify_asr_filler.js`, `tests/verify_spoken_recovery_exact_match.js`, `tests/verify_phase12c.js` do not execute the shipped `ui/app.js` functions they approximate (§10).
- **Partial duplicate-submission coverage** — per `docs/ASR_PIPELINE.md`, the client-side duplicate-submission guard (`_lastAcceptedAsrKey`/`_lastAcceptedAsrTime`) is scoped to one specific sub-branch; no test file in this audit was found dedicated to that guard specifically.
- **No automated guarantee against TTS self-capture** — `docs/ARCHITECTURE.md` §6.1 already documents this as a mitigation, not a guarantee, at the production-code level; no test could prove an absolute guarantee that doesn't exist in the implementation.
- **No reliable spoken-versus-typed server marker** — `_sel_trace.input_mode`'s known-inaccurate heuristic (documented in `docs/ASR_PIPELINE.md`) is not something a test can "fix"; any test relying on that field to distinguish spoken from typed input would itself be unreliable.
- **Production session capture disabled by default** — `MANDARINOS_SESSION_CAPTURE` defaults to unset; `tests/test_session_intelligence.py` tests both states but cannot prove what the deployed environment variable is actually set to.
- **Fixed-path Challenge history durability not testable through normal data-dir tests** — `data/progress_history.json` ignores `MANDARINOS_DATA_DIR` entirely (`docs/ARCHITECTURE.md` §6.4), so none of the `MANDARINOS_DATA_DIR`-override tests in §11/§13 exercise it; no dedicated test for this fixed path was found.
- **Generated artifacts not automatically rebuilt** — confirmed in §12; a stale-artifact class of bug is not caught by any current test.
- **Deployment branch configuration exists outside the repository** — which branch Railway watches is a dashboard setting, not a repo file (`docs/ARCHITECTURE.md` §13); no test can verify it.
- **Some historical regressions may have tests that prove only server behaviour, not client application** — e.g. the E4 handoff fix has direct server-side and extracted-client-helper coverage, but no test proves the browser actually applies the handoff during a real page session (§8).

**Distinguishing:**
- **Missing coverage** (could be added with current tooling): dedicated persona-switch test; dedicated duplicate-submission-guard test; source/generated-artifact consistency test; Challenge-history-path-specific persistence test.
- **Intentionally manual verification** (by design, given current tooling limits): browser/DOM behaviour, production smoke checks, TTS self-capture guarantee (none exists to test).
- **Operational facts not provable by repository-local unit or integration tests**: which branch Railway watches; whether the production `MANDARINOS_SESSION_CAPTURE`/`MANDARINOS_DATA_DIR` variables are actually set as documented; whether a Railway volume is actually mounted; whether deployed generated artifacts (§12) are current. A repository-local test cannot prove any of these — but they are not unverifiable in an absolute sense: deployment tooling and direct operational inspection (the Railway dashboard, `/api/version` combined with an artifact-dependent smoke check, direct inspection of the mounted volume's contents) can and should verify them. The correct response to this category is an operational check outside the test suite, not an assumption that the documented configuration is in effect.

**Additional gaps worth flagging for future maintainers, in priority order of risk:**

1. The answer-source priority chain (`docs/ANSWER_SOURCE_CONTRACT.md`) is the single highest-traffic piece of shared logic in the codebase, yet its regression coverage is spread across many independent single-scenario files rather than one maintained matrix with an enforced pass/fail gate — `scripts/test_counter_reply_matrix.py` is the closest thing to a comprehensive matrix, but it is a reporting script outside pytest and outside CI, so a regression there does not fail a build.
2. CI's `unit-tests` job (`python -m unittest -v` in `.github/workflows/coverage_scan.yml`) exercises, at most, the small subset of `tests/test_*.py` files containing `unittest.TestCase` subclasses. Three separate facts, per §4's CI-scope note, must not be conflated: the local exact-command result for the textually identical command was **zero** tests (A); a local explicit-discovery audit pointed at `tests/` (not the workflow command) found 6 files/88 cases (B); the actual CI result has **not** been verified from a workflow log (C). Which of (A) or (B) — or neither — the real CI job experiences is unresolved. In no scenario does it run the curated pytest tiers described in `tests/conftest.py` (`-m "not live_server"`, `-m "live_server"`) — those are **not** invoked by CI at all. A maintainer relying on "CI is green" as evidence for the pytest tiers, or for any pytest-style file CI merely happened to import, would be mistaken.
3. No test enumerates which `state_update` fields the client actually reads versus which the server actually emits, so a server-side field could be silently unused, or a client-side read could silently target a field the server no longer emits, without any test failing.
4. No test exists for the fixed-path Challenge history file (`data/progress_history.json`) at all — neither its write behaviour nor its documented non-portability under `MANDARINOS_DATA_DIR`.

## 18. Failure interpretation

**Targeted test fails.** Likely a localised defect in the specific function/module under test, or a stale expectation in the test itself (e.g. after an intentional behaviour change). Check whether the test asserts the *contract-level* outcome or an internal detail that legitimately changed.

**Core non-live suite fails.** Possible shared-contract regression — `pytest tests/ -m "not live_server"` includes the in-process HTTP tests and most direct-function tests, so a failure here can indicate a change to shared priority-chain, state-transport, or normalisation code (`docs/ARCHITECTURE.md` §16's high-risk list) rather than an isolated bug.

**Live-server suite fails while unit suite passes.** Likely an HTTP-layer, serialisation, persistence, or cross-request issue that only manifests against the real `ui_server.py` process — e.g. an environment variable set differently for the manually started server, a stale generated artifact the running process loaded at its own startup, or genuine cross-request state (dedup, session) that in-process tests don't reproduce identically.

**Client helper passes but application fails.** Likely a wiring, event-lifecycle, DOM, or state-integration issue — the extracted-helper mechanism (§3.B, §7) only proves the sliced function's internal logic, not that `ui/app.js`'s surrounding code calls it correctly or applies its result to the right variable.

**Local passes, production fails.** Investigate, in order: the deployed commit (`/api/version` — code identity only, not a generated-artifact check); which branch Railway is actually watching; environment variables (`MANDARINOS_DATA_DIR`, `MANDARINOS_SESSION_CAPTURE`, `MANDARINOS_DIAG_TOKEN`); whether the persistent volume is mounted as expected; whether `runtime/out_phase7/` artifacts were regenerated and made available to the deployed environment before the deploy that introduced the change (§12's 5-step obligation — a correct code deploy with stale/absent generated artifacts will pass `/api/version` while still behaving incorrectly); browser differences (if the failure is client-side, since no automated browser test exists to have caught it earlier); and stale static assets served by the same process.

**Static/mirrored test passes but behavioural test fails.** Treat the behavioural result as authoritative (§2, principle 2/8) — a passing static or mirrored test does not override a failing test that executes real production code.

## 19. Production verification

Sequence for runtime changes:

1. Push to the Railway-watched branch (not a documentation branch — `docs/architecture-v1` is not Railway's deployment branch, per `docs/ARCHITECTURE.md` §17).
2. Wait for the deployment to complete.
3. Read `/api/version`.
4. Confirm the expected full commit SHA is returned.
5. Perform the affected smoke scenario manually against the deployed URL.
6. Inspect persistent data only if the change affects persistence (and only through the configured `MANDARINOS_DATA_DIR`/volume, not by assumption).
7. Record the production result in the change report (§20 template).

State explicitly:
- Documentation-branch pushes do not require this sequence.
- A local commit is not production — it is not deployed until pushed to the Railway-watched branch.
- A successful Railway build does not prove the expected commit is running — only `/api/version` does.
- `/api/version` verifies code identity, not functional correctness — it must be paired with a smoke scenario, not treated as sufficient by itself.
- `/api/version` cannot verify generated-artifact identity or freshness at all — code identity and generated-artifact state are two separate facts, and a deploy can have the expected commit while serving stale or absent `runtime/out_phase7/` output (§12). A builder-only or generated-input-only change does not become production-effective merely because its code commit was deployed, if the required generated output is absent or stale in that deployment.
- For any change touching a generated artifact, deployment verification must include an artifact-dependent functional smoke scenario or another direct check of the deployed artifact state, in addition to the `/api/version` check — not as a substitute for it.

## 20. Test reporting template

```text
Targeted tests:
- command:
- result:

Core suite:
- command:
- result:

Client/Node verification:
- command:
- result:

Live-server tests:
- command:
- result:

CI verification:
- workflow/command:
- environment:
- executed test count:
- result:
- actual CI log inspected: yes/no

Generated artifacts:
- generation command:
- outputs inspected:
- local artifact-dependent smoke:
- deployed provisioning mechanism:
- deployed artifact-dependent smoke:

Production verification:
- deployed SHA:
- /api/version result:
- smoke scenario:
- result:

Known untested areas:
- ...
```

The `CI verification` section must distinguish a local reproduction of a CI command from explicit local discovery from an actual GitHub Actions result — use the exact labels `local exact-command result`, `local explicit-discovery audit`, and `actual CI result not verified` (or the real observed count, if `actual CI log inspected: yes`) rather than conflating them (§4). The `Generated artifacts` section must be filled in with `not applicable` in every field, rather than omitted, when the change does not involve any generated file — silent omission is not acceptable disclosure.

Require explicit disclosure when a test was: skipped (state the skip reason, e.g. `live_server` auto-skip or missing Node); static only (name the file and note it did not execute production code); mirrored (name the file and note it reimplements rather than executes production code); not run at all; or unavailable because a live server or browser was not present (state which — no browser is ever present, per §3.F).

## 21. Extension rules

When adding:

- **A new pytest marker** — register it in `tests/conftest.py`'s `pytest_configure`, following the existing `live_server` pattern; document its skip condition (if any) in the module docstring at the top of `conftest.py`.
- **A new test category** — add a row to §3's taxonomy table in this document, including what it proves and does not prove.
- **A browser automation framework** — this would be the single biggest change to this document's conclusions; update §3.F, §7, §8, §10, and §17 together, since all currently state no such framework exists.
- **A new live-server suite** — add the module-level `pytestmark = pytest.mark.live_server`; update §5's file/function counts and §4's execution map.
- **A new generated artifact** — update `docs/ARCHITECTURE.md` §14's mapping table and this document's §12; add a source/generated consistency test if practical, since none currently exist for any artifact.
- **A new persistent store** — follow the `tmp_path`/private-constant-override pattern in §11 and §16 for its test; update §11's coverage table.
- **A new deployment smoke check** — update §19; if it becomes automated, update §3.J and §17 (removing "no automated production test exists" once one exists).
- **A new mirrored/static verifier** — label it explicitly as mirrored or static in its own header/docstring (following the convention already used in `tests/verify_*.js`); update §5's counts and the relevant §9/§10 table.
- **A new test command** — verify it actually exists and runs before adding it to §4; do not add a command that is only aspirational.

This document must be updated whenever the evidentiary meaning of an existing suite changes — for example, if `tests/verify_asr_filler.js` is ever rewritten to use `_load_app_js_helper.js` instead of mirroring, its classification in §3.C/§10/§22 changes from mirrored to extracted-real-helper, and every table referencing it must be updated together.

**Maintenance cadence.** Re-verify this document's counts (§5) and execution-map commands (§4) whenever a new test file is added under `tests/`, whenever `tests/conftest.py` is edited, or whenever the CI workflow file changes — these are the three places most likely to silently drift from this document's claims. A count or command that has not been re-verified against the current tree should not be trusted merely because it was correct at a prior baseline. To re-verify: re-run repository file counts (e.g. count `tests/test_*.py` and `tests/*.js` files), re-run marker searches (e.g. search for `pytest.mark.live_server` and `pytestmark =` across `tests/`), and re-run every command documented in §4 against the current tree before relying on a specific number in a review or an incident investigation.

## 22. Traceability appendix

| Test area | Main files | Execution type | Primary contract protected |
| --------- | ---------- | ---------------- | ----------------------------- |
| Answer source | `tests/test_spoken_chinese_routing.py`, `tests/test_e4_topic_handoff.py`, `scripts/test_counter_reply_matrix.py` | Real Python (direct + live HTTP) | `docs/ANSWER_SOURCE_CONTRACT.md` |
| Frame selection | `tests/test_e4_topic_handoff.py` (`_FRAME_ORDER` check), `tests/test_golden_regression.py` (static frame-existence checks) | Real Python + static | `docs/CONVERSATION_ARCHITECTURE.md` |
| E4 | `tests/test_e4_topic_handoff.py`, `tests/test_e4_client_handoff_regression.py`, `tests/verify_e4_client_handoff.js`, `tests/e4_resolve_next_engine_id_cli.js` | Real Python + in-process HTTP + extracted-real-JS-helper | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md` |
| State | `tests/test_session_start_reset.py`, `tests/test_e4_client_handoff_regression.py` | Static + (in-process real HTTP + extracted-real-JavaScript helper) | `docs/STATE_CONTRACT.md` |
| ASR | `tests/verify_asr_filler.js`, `tests/test_asr_filler_suppression.py`, `tests/verify_spoken_recovery_exact_match.js`, `tests/test_asr_thinking_grace.py`, `tests/test_asr_interim_latency.py`, `tests/test_contextual_place_asr_repair.py` | Mirrored/static (dominant) + some real Python + in-process HTTP | `docs/ASR_PIPELINE.md` |
| Challenge Mode | `tests/test_challenge_recovery.py` | Hybrid — static + real module + mirrored `_is_rr_simulate` | `docs/ASR_PIPELINE.md` §14 |
| Learner memory | `tests/test_clear_memory_regression.py`, `tests/test_learner_memory_migration.py` | Real Python (behavioural, `tmp_path`) + static | `docs/STATE_CONTRACT.md` |
| Progress | `tests/test_progress_store.py` | Real Python (behavioural, `tmp_path`) | This document §11; `docs/ARCHITECTURE.md` §6.4 |
| Session capture | `tests/test_session_intelligence.py`, `tests/test_session_admin_endpoints.py` | Real Python (behavioural) + hybrid handler-unit | `docs/ASR_PIPELINE.md` §16; `docs/ARCHITECTURE.md` §6.4 |
| Generated artifacts | `tests/test_build_frame_tokens_runtime.py` | Real Python (builder functions only) | `docs/ARCHITECTURE.md` §14 |
| Deployment | `tests/test_deployment_hygiene.py` | Static + real Python (env-override behavioural) | `docs/ARCHITECTURE.md` §13 |
| Production verification | *(none automated)* — manual `/api/version` + smoke check | Manual | `docs/ARCHITECTURE.md` §13; this document §19 |
| Mirrored/static ASR verifiers | `tests/verify_asr_filler.js`, `tests/verify_spoken_recovery_exact_match.js`, `tests/verify_phase12c.js` | Mirrored + static (no real `ui/app.js` execution) | `docs/ASR_PIPELINE.md`; this document §3.C, §10 |
| Client/server contract (E4 field only) | `tests/test_e4_client_handoff_regression.py`, `tests/e4_resolve_next_engine_id_cli.js` | In-process HTTP + extracted-real-JS-helper | `docs/STATE_CONTRACT.md`; this document §8 |
| Deployment configuration | `tests/test_deployment_hygiene.py` | Static + real Python (behavioural env-override) | `docs/ARCHITECTURE.md` §13, §17 |

**Reading this table:** "Execution type" is drawn directly from §3's taxonomy — do not infer a stronger or weaker claim than the type warrants (§15). Rows without a dedicated file (e.g. persona switching in §9, production verification here) are listed to make the absence explicit, not to imply hidden coverage exists elsewhere.

This document's claims are grounded in direct repository evidence: file contents under `tests/`, `scripts/`, `tools/`, and `.github/workflows/`; literal execution of the commands documented in §4; and cross-checks against `docs/ARCHITECTURE.md` and the other approved R2 contracts. Two findings recur throughout this document and are treated as settled facts rather than claims requiring further hedging: the absence of any browser/DOM automation framework anywhere in the repository (§3.F), and the fact that CI (`.github/workflows/coverage_scan.yml`) does not execute the `pytest`-based `live_server`/core tiers described in `tests/conftest.py` at all (§4). To reproduce or re-verify any specific claim in this document, re-run the exact command or inspection referenced at that claim's location against the current tree — this document does not rely on any evidence that cannot be reproduced this way.

Baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Baseline tag: `architecture-baseline-2026-07-12-r2`
Documentation branch: `docs/architecture-v1`
Document status: `Approved v1 — R2 baseline`
Last verified date: `2026-07-13`
