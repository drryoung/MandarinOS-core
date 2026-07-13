# MandarinOS Change Checklist

## 1. Purpose and authority

This document is:

- the **mandatory change-control checklist** for R2 maintenance of MandarinOS;
- the **operational companion** to the six approved architecture and test documents (`docs/ARCHITECTURE.md`, `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md`, `docs/ASR_PIPELINE.md`, `docs/TEST_STRATEGY.md`);
- intended for both human maintainers and AI coding agents (Cursor and others) operating on this repository;
- subordinate to verified code and to the detailed contracts for behavioural truth — where this checklist's summary of a rule and a detailed contract's full statement disagree, the detailed contract governs.

**Completing this checklist does not guarantee correctness. Skipping an applicable step invalidates confidence in the change.** This checklist converts contract knowledge into a repeatable workflow; it does not replace reading the relevant contract for a non-trivial change.

Application baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Application baseline tag: `architecture-baseline-2026-07-12-r2`

> A change is not complete when the code compiles or a targeted test passes. It is complete only when its scope, state effects, tests, documentation, deployment status, and production result are all accounted for.

## 2. Change classification

| Change class | Examples | Default risk | Required workflow |
| ------------ | -------- | ------------- | ------------------ |
| A. Documentation-only | Correcting a contract; adding explanatory documentation; updating this checklist | Low | §17–§18 documentation-only path; no deployment |
| B. Content-only | Persona fact; voice line; recovery phrase; frame wording; translation/pinyin content; response-pattern data | Low–Medium | §12; §13 if a generated artifact is involved |
| C. Isolated helper change | Pure normalisation helper; persistence helper; small response formatter | Medium | §6; targeted test + core suite |
| D. Shared control-flow change | Answer-source priority chain; frame selection; state transport; E4 handoff; reset logic; ASR interception; request/response construction | High | §7–§10 as applicable; full core suite; relevant `live_server` suite for shared **server**-side control-flow changes; real-browser verification for client ASR/DOM/event/Challenge Mode/interception changes; deployed code-identity and functional verification when shipped |
| E. API or persistence change | Endpoint; request field; response field; learner-memory schema; progress/session store; environment-variable behaviour | Medium–High | §7, §14; see the API-versus-persistence distinction below §2's table — the two do **not** share an identical mandatory workflow |
| F. UI/ASR/browser change | Event handler; Challenge Mode visibility; microphone lifecycle; TTS coordination; translated-input flow | Medium–High | §10; core suite; manual browser verification |
| G. Generated-artifact or builder change | `tools/build_runtime_artifacts.py`; builder inputs; generated runtime schema; phrase/frame runtime outputs | Medium–High | §13; full 5-step deployment obligation |
| H. Deployment/configuration change | `railway.toml`; `Procfile`; `nixpacks.toml`; `PORT`; `MANDARINOS_DATA_DIR`; Railway branch or volume configuration | High | §18–§19; deployed SHA + smoke check required |
| I. Emergency production fix | Any of the above, under time pressure | High (by definition) | Union of the relevant class(es) above — urgency waives nothing |

**Multiple classes can apply to one change.** A recovery-phrase edit that also requires regenerating a runtime artifact is class B *and* G; use the union of both rows' requirements, not just the most obvious one.

### A. Documentation-only

- No production deployment is required.
- No `/api/version` verification is required.
- Commit and push to the **current authorised documentation or working branch**; for this R2 documentation package, that branch is `docs/architecture-v1`. Future maintenance work must not assume `docs/architecture-v1` remains the active documentation branch indefinitely — confirm the currently authorised branch before pushing. Pushing that branch is sufficient unless the documentation is deliberately merged into the branch Railway watches (`docs/ARCHITECTURE.md` §17).
- The implementation report (§21) must record the actual branch used.

### B. Content-only

Distinguish, for every content change:

- **Source-controlled content consumed directly** (e.g. `personas/*.json`, which are source-controlled and consumed directly by the server without the runtime-artifact build step; at the R2 baseline, the persona index is loaded into the server's runtime structures at startup, and individual persona files are lazy-loaded from disk on first access and then cached in memory for subsequent requests — do not imply persona JSON is necessarily reread from disk on every request) — no build step required, but a runtime-consumed persona fact, voice line, or other content change still requires the targeted content/answer test **plus the core non-`live_server` suite** (`docs/TEST_STRATEGY.md` §13) — a content change is never "no broader suite required" merely because it is content rather than code.
- **Content requiring generated runtime artifacts** (e.g. `content/recovery_phrases.json` → `recovery_phrases.runtime.json`, `p1_frames.json`/`p2_frames.json` → `frame_options.runtime.json` — see `docs/ARCHITECTURE.md` §14) — §13's full regeneration and provisioning obligation applies, in addition to the targeted test and core suite above.

A **documentation-only** change (class A) requires no test suite at all — that exemption does not extend to class B. Do not classify a runtime-consumed persona/content change as "no broader suite required."

### C. Isolated helper change

**Class C remains medium risk by default.** A pure helper may have a small blast radius, but it still requires a targeted behavioural test and the core non-`live_server` suite, unless `docs/TEST_STRATEGY.md` explicitly provides a narrower rule for that specific test. Being isolated reduces diagnostic scope — it narrows *where* to look for the defect — it does not reduce the obligation to validate the helper's callers. Confirm it is genuinely isolated — not called from the answer-source or frame-selection paths (§8, §9 high-risk list) — before treating it as narrowly scoped within the medium-risk workflow.

### D. Shared control-flow change

Default risk: **high**. Covers the answer-source priority chain, frame selection, state transport, E4 handoff, reset logic, ASR interception, and request/response construction — the exact high-risk list in `docs/ARCHITECTURE.md` §16. Any change touching these paths requires the full core suite regardless of how small the diff looks (`docs/TEST_STRATEGY.md` §13, item 2). Shared **server** control-flow changes (answer-source, frame selection, state transport, E4, reset) require the core suite and the relevant `live_server` suite — those are real server-side evidence. ASR interception is different: it is a **client** behaviour that, by construction, never reaches `/api/run_turn`, so no server `live_server` test can prove it fired or fired correctly (§10; `docs/TEST_STRATEGY.md` §13). Treat ASR-interception changes under this class as requiring the core suite plus mandatory real-browser verification, not as proved by the `live_server` suite.

### E. API or persistence change

Covers `/api/*` endpoints, request/response fields, `conversation_state`/`state_update` fields, learner-memory schema, progress/session store behaviour, and any `MANDARINOS_*` environment-variable behaviour. **API and persistence changes do not share an identical mandatory workflow** — distinguish them:

**API endpoint or transport change:**

- targeted handler or in-process HTTP test (`docs/TEST_STRATEGY.md` §6);
- core non-`live_server` suite — **mandatory**;
- local `live_server` suite — **mandatory before shipping** the endpoint change, not merely recommended;
- `/api/version` and functional production smoke verification — **mandatory when deployed**.

**Persistence-module change** (e.g. `scripts/progress_store.py`, `scripts/beta_profile.py`, `scripts/learner_memory.py`, `scripts/session_intelligence.py`):

- targeted behavioural filesystem test(s) using a temporary directory (`tmp_path`) — §14;
- core non-`live_server` suite — **mandatory**;
- live-server testing — required **only** when the change also affects an endpoint, a cross-request flow, or session lifecycle, not for every isolated persistence helper with no HTTP path involved;
- operational persistence verification when deployed, including the applicable environment variable (`MANDARINOS_DATA_DIR`, `MANDARINOS_SESSION_CAPTURE`, etc.) and mounted-volume configuration (§14, §19).

Do not require the full `live_server` suite for an isolated persistence helper that has no HTTP path — that requirement applies specifically to endpoint/transport changes and to persistence changes that also touch an endpoint or cross-request flow.

### F. UI/ASR/browser change

Covers DOM event handlers, Challenge Mode visibility/reveal logic, microphone lifecycle, TTS coordination, and the translated-input flow. No automated browser/DOM test exists (`docs/TEST_STRATEGY.md` §3.F). Shared server control-flow changes underlying this area (e.g. an endpoint the client calls) require the core and relevant `live_server` suites; but client-side ASR, DOM, event, Challenge Mode, and interception changes require the core suite plus the relevant Node/static/mirrored checks **and** mandatory real-browser verification — server tests cannot prove a client-intercepted action that never reaches `/api/run_turn` (`docs/TEST_STRATEGY.md` §13's recovery phrase-bank requirements). When a change affects both browser and server behaviour, apply the union of both requirement sets, not either alone.

### G. Generated-artifact or builder change

Covers `tools/build_runtime_artifacts.py`, its builder modules under `tools/builders/`, and the JSON inputs it reads. See §13 for the full obligation; `/api/version` cannot verify any part of this class.

### H. Deployment/configuration change

Covers `railway.toml`, `Procfile`, `nixpacks.toml`, the `PORT` environment variable, `MANDARINOS_DATA_DIR`, and any Railway dashboard configuration (branch watch, volumes, other environment variables) that this repository's files cannot themselves verify.

### I. Emergency production fix

Urgency does not waive:

- reproduction against real behaviour, not assumption;
- a bounded diff;
- a regression test protecting the fix;
- deployed-SHA verification via `/api/version` after deploying;
- follow-up documentation of the change and any deferred cleanup.

## 3. Stop conditions before implementation

Stop and resolve the condition before writing code when:

- [ ] the defect cannot be reproduced;
- [ ] the expected behaviour is not defined anywhere in the approved contracts;
- [ ] two approved contracts appear to conflict;
- [ ] the proposed change relies on a historical document rather than current code/contracts (`docs/ARCHITECTURE.md` §3, §20);
- [ ] the relevant state owner is unknown (§7);
- [ ] current-turn versus following-turn effect is unclear (§9);
- [ ] reset and persona-switch behaviour for the affected state is unknown (`docs/STATE_CONTRACT.md`);
- [ ] generated artifacts are involved but their source/provisioning path is unknown (§13);
- [ ] a production change is proposed without knowing which branch Railway watches (`docs/ARCHITECTURE.md` §13);
- [ ] a request refers to a file, endpoint, field, or engine that does not exist at the baseline;
- [ ] a client-side behaviour is being inferred only from server tests (`docs/TEST_STRATEGY.md` §7–§8);
- [ ] a server behaviour is being inferred only from client/static tests;
- [ ] the requested change would silently broaden scope beyond the reported defect.

> When one of these conditions is present, diagnose first. Do not implement from assumption.

## 4. Pre-change diagnosis checklist

- [ ] Record the reported symptom in user-visible terms.
- [ ] Record the exact reproduction steps.
- [ ] Record expected versus actual behaviour.
- [ ] Confirm the deployed/local commit being tested (`/api/version` for deployed; `git rev-parse HEAD` for local).
- [ ] Identify whether the issue is local, deployed, browser-specific, state-specific, persona-specific, or data-specific.
- [ ] Identify the authoritative contract (§20's document map).
- [ ] Trace the real producer and consumer functions — not the first plausible-looking one.
- [ ] Identify all raw, normalised, transported, returned, and persistent forms of the relevant value.
- [ ] Identify priority/order position if answer selection or frame selection is involved (§8, §9).
- [ ] Identify current-response versus following-turn timing.
- [ ] Identify reset semantics: same-tab new session; reload; persona switch; normal carry-forward.
- [ ] Identify English/pinyin implications (§11).
- [ ] Identify generated-artifact implications (§13).
- [ ] Identify persistence/environment implications (§14).
- [ ] Identify whether client-intercepted behaviour bypasses the server (`docs/ASR_PIPELINE.md`).
- [ ] Find existing tests and classify their evidence type using `docs/TEST_STRATEGY.md` §3.
- [ ] State the smallest plausible root cause.
- [ ] State what is explicitly out of scope.

A short written diagnosis is required before implementation for any class C–I change (§2).

## 5. Change proposal template

```text
Problem:
Expected behaviour:
Observed behaviour:
Authoritative contract:
Root cause:
Files to change:
Files deliberately not changing:
State affected:
Current-turn/following-turn effect:
Reset implications:
English/pinyin implications:
Generated-artifact implications:
Persistence/deployment implications:
Targeted regression test:
Broader validation:
Out-of-scope items:
```

AI coding agents must return this diagnosis before implementing any class D–I change (§2). For class A/B/C changes, a shorter statement covering `Problem`, `Root cause`, `Files to change`, and `Targeted regression test` is sufficient.

## 6. Scope-control checklist

- [ ] Change only the minimum necessary files.
- [ ] Do not combine unrelated cleanup with the fix.
- [ ] Do not rename shared helpers unless required by the fix itself.
- [ ] Do not reorder priority chains without documenting every affected branch (§8).
- [ ] Do not broaden matchers or classifiers without adding negative tests.
- [ ] Do not add new state when an existing authoritative field already serves the purpose (`docs/STATE_CONTRACT.md`).
- [ ] Do not add a new duplicate source of content — check for existing inline duplicates first (`docs/ARCHITECTURE.md` §16).
- [ ] Do not edit generated runtime output (`runtime/out_phase7/*.runtime.json`) as the primary source (§13).
- [ ] Do not modify historical documents to make them appear consistent with current code (`docs/ARCHITECTURE.md` §3).
- [ ] Do not refactor large central files (`scripts/ui_server.py`, `ui/app.js`) during a surgical regression fix unless separately approved.
- [ ] Do not change client and server field names independently — both sides of `conversation_state`/`state_update` must agree.
- [ ] Do not claim an issue is fixed because a static or mirrored test passes (`docs/TEST_STRATEGY.md` §2, principle 2/8).

> A bounded fix should reduce the defect without increasing the number of independent rules governing the same behaviour.

## 7. State-change checklist

- [ ] Identify state owner: DOM/UI; client global; `conversation_state`; `state_update`; server-local; learner memory; progress/session storage.
- [ ] Identify producer.
- [ ] Identify every consumer.
- [ ] Identify default value.
- [ ] Identify merge semantics.
- [ ] Identify all reset paths.
- [ ] Identify persistence duration.
- [ ] Identify transport direction.
- [ ] Confirm whether the client actually consumes the server field — a field appearing in a response body is not proof it is read (`docs/TEST_STRATEGY.md` §8).
- [ ] Test current turn.
- [ ] Test following turn.
- [ ] Test new session.
- [ ] Test page reload assumptions.
- [ ] Test persona switch where applicable.
- [ ] Update `docs/STATE_CONTRACT.md` if behaviour changes.

> A field appearing in `state_update` does not prove the client applies it.

## 8. Answer-source checklist

For any `counter_reply` change:

- [ ] Identify the exact priority branch.
- [ ] Identify all higher-priority blockers.
- [ ] Identify group-local blocking semantics.
- [ ] Identify raw versus routing-normalised input.
- [ ] Identify the Chinese producer.
- [ ] Identify the English producer/fallback.
- [ ] Identify pinyin derivation.
- [ ] Identify deduplication behaviour.
- [ ] Identify exact-repeat behaviour.
- [ ] Identify repair escalation.
- [ ] Identify final ASR-junk repair implications (`_repair_asr_junk_text`).
- [ ] Confirm whether E4 eligibility is calculated before replacement.
- [ ] Test a positive case.
- [ ] Test a near-miss negative case.
- [ ] Test a competing higher-priority case.
- [ ] Test repeated-turn behaviour.
- [ ] Test Chinese/English/pinyin alignment.
- [ ] Update `docs/ANSWER_SOURCE_CONTRACT.md` if priority, producer, fallback, or finalisation behaviour changes.

> Changing one answer producer can alter unrelated responses if it changes shared priority or blocking conditions.

## 9. Frame-selection and E4 checklist

- [ ] Identify the current engine.
- [ ] Identify the frame ladder and order (`_FRAME_ORDER`).
- [ ] Identify eligibility and `skip_when` rules.
- [ ] Identify mutual-exclusion rules.
- [ ] Identify current-response frame effects.
- [ ] Identify following-turn engine effects.
- [ ] Confirm whether `force_travel_bridge` or another same-response flag alters frame text.
- [ ] Confirm whether `state_update.current_engine` is emitted.
- [ ] Confirm whether the client consumes it (`_resolveNextEngineId()` in `ui/app.js`).
- [ ] Preserve the one-response transition delay unless intentionally changing the contract.
- [ ] Test direct question → current response.
- [ ] Test direct question → following request.
- [ ] Test non-eligible question.
- [ ] Test repeated/adjacent turns.
- [ ] Test persona switch and reset implications where relevant.
- [ ] Update `docs/CONVERSATION_ARCHITECTURE.md` and `docs/STATE_CONTRACT.md` if the handoff contract changes.

> The persona answer and the next frame are separate outputs. A correct answer does not prove correct frame selection, and a correct frame does not prove correct future-engine handoff.

## 10. ASR and browser checklist

- [ ] Identify which input mechanism is changing: Chinese microphone; translate-assisted typed input; auxiliary English microphone; client-intercepted spoken recovery; synthetic test payload.
- [ ] Confirm whether the change affects visible text, submitted text, comparison-only text, or routing-normalised text.
- [ ] Confirm whether the server receives the interaction at all.
- [ ] Confirm filler handling.
- [ ] Confirm exact-match recovery behaviour.
- [ ] Confirm false-positive risk for longer utterances.
- [ ] Confirm duplicate-submission scope (`_lastAcceptedAsrKey`/`_lastAcceptedAsrTime`).
- [ ] Confirm TTS cancellation/coordination.
- [ ] Confirm Challenge Mode visibility/reveal effects.
- [ ] Confirm fetch-error behaviour.
- [ ] Confirm raw evidence/capture implications (`MANDARINOS_SESSION_CAPTURE`, diagnostics).
- [ ] Run relevant mirrored/static/extracted tests, labelling them accurately per `docs/TEST_STRATEGY.md` §3.
- [ ] Perform real-browser verification when browser behaviour changes.
- [ ] Verify no `/api/run_turn` request occurs for an intercepting recovery action.
- [ ] Verify non-intercepting actions still reach the server.
- [ ] Update `docs/ASR_PIPELINE.md` if the lifecycle, matcher, repair, capture, or visibility contract changes.

> No current automated test proves full browser SpeechRecognition, DOM, event, or fetch behaviour.

## 11. English and pinyin checklist

Whenever Chinese output changes:

- [ ] Identify the final Chinese source of truth.
- [ ] Identify the corresponding English mapping.
- [ ] Identify pinyin derivation.
- [ ] Confirm whether replacement/dedup/repair occurs before or after English generation.
- [ ] Confirm whether final Chinese-only repair can desynchronise paired fields.
- [ ] Test the exact final Chinese sentence against English.
- [ ] Test pinyin against the final Chinese.
- [ ] Test empty-English signalling where relevant.
- [ ] Test dynamic persona facts.
- [ ] Test mirror/reverse answers.
- [ ] Test repeated-answer substitution.
- [ ] Confirm client rendering separately if UI behaviour changes.

`tests/test_zh_en_synchronisation.py` is dedicated, real, server-side evidence for these invariants (`docs/TEST_STRATEGY.md` §9) — but it does not prove client rendering; a UI-visible English/pinyin change still needs separate confirmation.

## 12. Content-change checklist

For persona, frame, recovery, mirror, or response-pattern content:

- [ ] Confirm the source-of-truth file.
- [ ] Check for competing inline content (`docs/ARCHITECTURE.md` §16).
- [ ] Check for superseded sibling files (`docs/ARCHITECTURE.md` §19).
- [ ] Check schema requirements.
- [ ] Check English/pinyin companion fields.
- [ ] Check persona-specific and generic fallback behaviour.
- [ ] Confirm whether a runtime artifact must be regenerated (`docs/ARCHITECTURE.md` §14).
- [ ] Add or update a targeted regression/content test.
- [ ] Test a negative case.
- [ ] Check that the change does not broaden another persona/frame/topic.
- [ ] Update the relevant contract if the content source or precedence changes.

For city/place content, explicitly check: frame/slot content; persona facts; `_CITY_LOCATION_BRIEF`; `_CITY_FOOD_POOL`; `_CITY_FEATURE_POOL`; `_FOOD_POOL_INLINE`; `_FEAT_POOL_INLINE`; generic inline fallbacks. This document does not duplicate the detailed inventory in `docs/ANSWER_SOURCE_CONTRACT.md` — cross-reference it.

## 13. Generated-artifact checklist

- [ ] Identify the source input.
- [ ] Identify the generated output (`docs/ARCHITECTURE.md` §14's source → artifact table).
- [ ] Run: `python tools/build_runtime_artifacts.py`
- [ ] Inspect or diff the generated output against the pre-change version.
- [ ] Confirm the local application loads the regenerated artifact, using evidence appropriate to the actual artifact: restart the local application after regeneration where startup loading is involved; exercise an artifact-dependent scenario whose outcome differs between the old and regenerated artifact; where practical, inspect the exact runtime file or in-memory loaded value the application actually used. Record whichever evidence was used in the implementation report (§21).
- [ ] Run the relevant builder/content test(s) (`docs/TEST_STRATEGY.md` §3.G, §12).
- [ ] Confirm no stale artifact remains.
- [ ] Identify the deployed provisioning mechanism, if any.
- [ ] Verify that mechanism actually places the new artifact in the deployed environment.
- [ ] Perform an artifact-dependent production smoke test (a behaviour that would visibly differ between old and new generated content).
- [ ] Record artifact generation/provisioning in the change report (§21).

State: `A startup log is evidence only when that log explicitly identifies the relevant artifact or changed content; process restart alone does not prove that the intended regenerated data was loaded.`

State, and do not deviate from:

- generated artifacts (`runtime/out_phase7/*.runtime.json`) are gitignored, not committed to source control;
- `scripts/ui_server.py` does not regenerate them at its own startup;
- Railway's current `railway.toml`/`nixpacks.toml` configuration does not run the builder either — regeneration is **explicit-only**;
- `/api/version` verifies code identity only — it cannot prove artifact identity or freshness;
- without a verified deployed provisioning mechanism, the change is **not production-ready**, even if its code commit deploys successfully;
- selecting or changing the packaging/provisioning architecture is outside this checklist's scope — this checklist only requires that the question be answered and verified before the change is treated as deployable.

## 14. Persistence checklist

For learner memory, progress, sessions, beta profiles, diagnostics, or Challenge history:

- [ ] Identify the exact file/path.
- [ ] Identify whether it honours `MANDARINOS_DATA_DIR` (Challenge history, `data/progress_history.json`, does **not** — `docs/ARCHITECTURE.md` §13).
- [ ] Identify enablement environment variables (`MANDARINOS_SESSION_CAPTURE`, `MANDARINOS_DIAG_TOKEN`).
- [ ] Identify default-on versus opt-in behaviour.
- [ ] Use temporary directories (`tmp_path`) in tests, never the real `data/` directory.
- [ ] Verify save.
- [ ] Verify load.
- [ ] Verify isolation by learner/session.
- [ ] Verify clear/reset.
- [ ] Verify invalid input handling.
- [ ] Verify process-restart expectations where possible.
- [ ] Verify Railway mounted-volume configuration operationally (Railway dashboard) — this cannot be verified by a repository-local test.
- [ ] Confirm fixed repo-relative paths are not assumed durable on Railway without a volume covering them.
- [ ] Update architecture/state/test documentation if persistence behaviour changes.

Explicitly distinguish: module I/O correctness (provable by a `tmp_path` test); environment-variable selection (provable by a test that sets/unsets the variable); actual Railway volume configuration (an operational fact, not provable by any repository-local test — `docs/TEST_STRATEGY.md` §17).

## 15. Test-selection checklist

`docs/TEST_STRATEGY.md` is the authority for this section.

- [ ] Classify each selected test: real Python; extracted real JavaScript; mirrored; static; in-process HTTP; external live server; manual browser; operational production.
- [ ] Add a failing targeted regression test before the fix where practical.
- [ ] Run the minimum targeted test.
- [ ] Run the broader suite required by the change matrix (`docs/TEST_STRATEGY.md` §13).
- [ ] Run relevant Node verification.
- [ ] Run local `live_server` tests for high-risk server changes.
- [ ] Perform manual browser checks for ASR/DOM/Challenge changes.
- [ ] Disclose skipped tests.
- [ ] Disclose missing Node/server/browser.
- [ ] Do not present mirrored/static success as behavioural proof.
- [ ] Do not assume CI ran the pytest tiers — CI's `unit-tests` job runs `python -m unittest -v`, which is a materially different, narrower mechanism (`docs/TEST_STRATEGY.md` §4).
- [ ] Distinguish a local reproduction of a CI command from actual GitHub Actions logs — use the exact labels `local exact-command result`, `local explicit-discovery audit`, and `actual CI result not verified` (`docs/TEST_STRATEGY.md` §4).
- [ ] Record generated-artifact verification separately (§13).

Verified core command: `python -m pytest tests/ -m "not live_server"`
Verified live-server command: `python -m pytest tests/ -m "live_server"`

The live-server command requires a server already running on `http://localhost:8765` (start with `python scripts/ui_server.py`); it auto-skips (not fails) if unreachable.

## 16. Diff-review checklist

Before commit, inspect the final diff:

- [ ] Only intended files changed.
- [ ] No debug logging left behind.
- [ ] No credentials, secret values, or authentication tokens added.
- [ ] No unintended hard-coded localhost, deployment, diagnostic, or third-party URLs added; any intentional new URL is part of the authorised scope and has been reviewed for configuration, privacy, security, and deployment implications — this is not a categorical prohibition on legitimate URL changes.
- [ ] No local machine paths added.
- [ ] No generated files edited as primary source.
- [ ] No unrelated formatting churn.
- [ ] No historical document silently elevated (`docs/ARCHITECTURE.md` §3).
- [ ] No priority-order change hidden inside helper cleanup.
- [ ] No state field added without producer/consumer/reset documentation.
- [ ] No client field renamed without a corresponding server update.
- [ ] No server field emitted without a client-consumption review.
- [ ] No English/pinyin field left stale.
- [ ] No test algorithm copied from production without a mirrored label.
- [ ] No test was weakened merely to pass.
- [ ] No expected failure converted to a skip without justification.
- [ ] No deployment claim made without pushed-commit evidence.
- [ ] No generated-artifact change reported complete without provisioning evidence.

Useful, verified commands:

```bash
git status --short
git diff --stat
git diff
git diff --cached
git log -1 --oneline
```

## 17. Commit checklist

- [ ] Working tree reviewed.
- [ ] Tests reported (§21 template).
- [ ] Documentation updated (§20).
- [ ] Commit message describes one bounded change.
- [ ] Commit contains only intended files.
- [ ] Full commit SHA recorded.
- [ ] Branch recorded.
- [ ] Working tree clean after commit.

State: a local commit is not pushed; a pushed documentation branch is not production; a merge is not inherently required unless the target/deployment workflow requires one.

## 18. Push and branch checklist

### Documentation-only

- Push the **current authorised documentation or working branch** — for this R2 documentation package, `docs/architecture-v1`. Do not treat this branch name as a permanent universal rule; future maintenance work must confirm which branch is currently authorised before pushing.
- Confirm the branch is up to date with origin.
- No Railway deployment is required unless deliberately merging to the watched branch.
- Record the actual branch used in the implementation report (§21).

### Runtime change

- Identify the exact Railway-watched branch — this is a Railway dashboard setting, not a file in this repository (`docs/ARCHITECTURE.md` §13); do not assume it without verifying it.
- Push the commit to that branch.
- Do not assume `main` unless verified.
- Record the push result.
- Confirm the remote branch contains the expected SHA using a command that actually queries remote state — `git log -1 --format=%H` reports local `HEAD` and is not remote evidence. Use:

```bash
git rev-parse HEAD
git rev-parse origin/<branch>
```

after `git fetch origin <branch>`, or query the remote directly without fetching:

```bash
git ls-remote origin refs/heads/<branch>
```

- `git rev-parse HEAD` verifies the local checked-out commit.
- `git rev-parse origin/<branch>` verifies the locally cached remote-tracking reference, and is only current after `git fetch origin <branch>`.
- `git ls-remote origin refs/heads/<branch>` queries the remote repository directly, with no local cache involved.
- The reported remote SHA must match the intended pushed commit before treating the push as confirmed.

> Railway cannot deploy a local-only commit.

## 19. Deployment checklist

For runtime changes:

- [ ] Confirm push to the Railway-watched branch.
- [ ] Wait for deployment completion.
- [ ] Read `/api/version`.
- [ ] Confirm the expected full SHA (`sha_full` field).
- [ ] Confirm the `branch`/`sha_source` fields (`"git"` or `"railway_env"`).
- [ ] Perform the affected smoke scenario manually.
- [ ] Verify browser behaviour when applicable.
- [ ] Verify persistence when applicable (through the configured `MANDARINOS_DATA_DIR`/volume, not by assumption).
- [ ] Verify generated artifacts when applicable (§13).
- [ ] Record the result.
- [ ] Record any manual steps or environment changes performed.

State: a successful Railway build is not proof of the correct commit; `/api/version` is code-identity evidence only; `/api/version` is not functional evidence; `/api/version` is not generated-artifact evidence; production smoke testing (this is manual operational verification, per `docs/TEST_STRATEGY.md` §3.J) is mandatory for deployed runtime changes.

## 20. Documentation-update checklist

| Change area | Document to review/update |
| ------------ | --------------------------- |
| System/repository/deployment boundary | `docs/ARCHITECTURE.md` |
| Turn/frame/E4 behaviour | `docs/CONVERSATION_ARCHITECTURE.md` |
| State/reset/persistence field behaviour | `docs/STATE_CONTRACT.md` |
| Persona-answer priority/English/pinyin | `docs/ANSWER_SOURCE_CONTRACT.md` |
| Speech/input/recovery/text repair | `docs/ASR_PIPELINE.md` |
| Test categories/commands/requirements | `docs/TEST_STRATEGY.md` |
| Maintenance workflow itself | `docs/CHANGE_CHECKLIST.md` (this document) |

- [ ] Update documentation in the same change when behaviour changes.
- [ ] Retain and reconcile baseline/status metadata; do not preserve stale values merely for continuity. Concretely: preserve the metadata **fields and structure** (commit, tag, document status, last-verified date); update the verified commit, tag/status, and verification date where the document is being revised to describe a newer behavioural baseline; do not leave the original R2 baseline commit attached to behaviour that was introduced later. If a document intentionally remains a frozen R2 baseline contract, state explicitly that the new change is outside that baseline and record where the newer contract is maintained instead. Never silently change, and never silently retain, baseline metadata.
- [ ] Do not rewrite a historical document as a substitute for updating an approved contract.
- [ ] If no documentation change is required, state why in the implementation report (§21).

## 21. Implementation report template

```text
Change summary:
- problem:
- root cause:
- behaviour changed:
- behaviour deliberately unchanged:

Files:
- changed:
- added:
- not changed:

Architecture impact:
- authoritative contract:
- state:
- current-turn/following-turn:
- reset:
- English/pinyin:
- generated artifacts:
- persistence:

Targeted tests:
- command:
- evidence type:
- result:

Core suite:
- command:
- result:

Client/Node verification:
- command:
- evidence type:
- result:

Live-server tests:
- command:
- result:

Browser verification:
- browser/device:
- scenario:
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

Commit:
- branch:
- SHA:
- push result:

Production verification:
- deployed SHA:
- /api/version:
- smoke scenario:
- persistence/artifact check:
- result:

Documentation:
- updated:
- not updated and reason:

Known untested areas:
- ...
```

Use `not applicable`, `not run`, or `not verified` rather than silently omitting a section — a blank or missing field is not acceptable disclosure.

## 22. Reviewer approval checklist

- [ ] Diagnosis matches evidence.
- [ ] Scope is bounded.
- [ ] Appropriate contract was used.
- [ ] State ownership/reset reviewed.
- [ ] Current-turn/following-turn distinction is correct.
- [ ] Priority/order implications reviewed.
- [ ] English/pinyin pairing reviewed.
- [ ] Generated artifacts addressed.
- [ ] Persistence addressed.
- [ ] Targeted regression test fails before the fix and passes after, where practical.
- [ ] Test evidence labels are accurate.
- [ ] Core/live/browser/deployment requirements are satisfied for the change's class.
- [ ] Diff contains no unrelated changes.
- [ ] Documentation updated.
- [ ] Commit and push status is clear.
- [ ] Production SHA verified when deployed.
- [ ] Known gaps disclosed.

The reviewer should reject:

- "all tests passed" without commands/results;
- static-only evidence presented as runtime proof;
- unverified deployment claims;
- unexplained skipped tests;
- undocumented state fields;
- generated-artifact changes with no provisioning answer;
- broad refactoring inside a regression fix;
- AI-agent summaries not supported by inspected diffs or source.

## 23. AI coding-agent rules

- Diagnose before implementing.
- Use the approved contracts, not memory or historical documents, as behavioural authority.
- Do not infer a fix from filenames.
- Inspect real producer/consumer code before proposing a change.
- Return a bounded plan (§5) before implementing a class D–I change.
- Preserve existing behaviour outside the declared scope.
- Create or update a regression test for every behavioural fix.
- Report test evidence accurately, using the classifications in `docs/TEST_STRATEGY.md` §3.
- Do not call mirrored/static tests "behavioural".
- Do not claim production deployment without both a push and a verified `/api/version` result.
- Do not claim generated artifacts are deployed without provisioning evidence (§13).
- Do not modify more files than authorised by the task.
- Do not push unless instructed.
- Do not start the next documentation phase early.

**Model-use policy** (cost-conscious workflow policy, not vendor promotion):

- Use Claude Opus or Claude Sonnet for diagnosis and review when deeper reasoning is required.
- Use Claude Sonnet, or another cheaper suitable model, for implementation after the diagnosis is settled.
- Do not spend Opus-level tokens on mechanical edits after the root cause and bounded implementation plan are established.

This policy never overrides evidence requirements, review requirements, testing, human approval, or scope controls (§3, §6, §15, §22) — it governs which model performs a step, not whether the step itself is required.

## 24. Quick checklists by risk level

### Low risk

For: documentation-only changes (class A) only.

- Diagnosis: confirm the change is genuinely documentation-only and does not describe or imply a behavioural change.
- Targeted test: none required.
- Broader suite: none required.
- Documentation: update only if the change corrects a claim in an approved contract.
- Commit/push: single bounded commit; push the working branch.
- Deployment/browser: none required.

### Medium risk

For: helper logic (class C, medium risk by default — §2); a persistence module; a persona/content change consumed at runtime (class B); an endpoint with isolated behaviour; content requiring a generated artifact.

- Diagnosis: §4, focused on the helper's/content's producer/consumer and any generated-artifact dependency.
- Targeted test: direct-function test for the helper, or the targeted content/answer test for a content change; a targeted behavioural filesystem test (`tmp_path`) for a persistence module; regenerate and inspect the artifact if involved (§13).
- Broader suite: core non-`live_server` suite — **mandatory**, not optional, for any runtime-consumed content, helper, or persistence change.
- Documentation: update the relevant contract if behaviour changed, per §20.
- Commit/push: single bounded commit; push to the appropriate branch.
- Deployment/browser: for an isolated API endpoint, the local `live_server` suite is **mandatory before shipping** (§2.E); for an isolated persistence helper with no HTTP path, `live_server` is required only if the change also affects an endpoint, cross-request flow, or session lifecycle — otherwise operational persistence verification (environment variable + mounted-volume configuration) is the deployed check, not the `live_server` suite. **When content or helper work involves a generated runtime artifact and is intended for production**, do not stop at "regenerate and inspect": §13's full obligation applies in full — identify and verify the deployed provisioning mechanism, and perform an artifact-dependent deployed smoke test; without a verified provisioning mechanism, the change is not production-ready. Deployed `/api/version` + the applicable smoke check is mandatory whenever any of these is shipped.

### High risk

For: answer-source priority; frame selection; E4; state transport; reset logic; ASR client; Challenge Mode; shared normalisation; deployment configuration.

- Diagnosis: full §4 checklist plus the relevant subsystem checklist (§7–§10).
- Targeted test: new or extended regression test using real implementation code (§6, §15).
- Broader suite: full core suite; the relevant `live_server` suite for shared **server** control-flow paths (§2.D).
- Documentation: update the specific contract(s) in §20's map in the same change.
- Commit/push: single bounded commit; push to the Railway-watched branch if deploying (§18).
- Deployment/browser: every deployed runtime change — server code, client JavaScript, CSS, or runtime content — requires verification that the expected commit is running, via `/api/version`; `/api/version` verifies code identity only. A server-side change then additionally requires the affected production server scenario; a browser/client change then additionally requires the affected real-browser scenario (mandatory for any ASR/DOM/Challenge/client-interception change — a passing `live_server` suite does not prove client-intercepted behaviour, §2.D, §2.F, §10); a change affecting both requires both scenarios; a generated-artifact-dependent change additionally requires §13's provisioning and artifact-dependent verification.

## 25. Traceability appendix

| Checklist area | Primary authority | Main implementation surfaces |
| --------------- | -------------------- | ------------------------------- |
| Architecture/repository | `docs/ARCHITECTURE.md` | `scripts/ui_server.py`, `ui/`, repository root configuration |
| State | `docs/STATE_CONTRACT.md` | `conversation_state`/`state_update` fields, client globals |
| Answer source | `docs/ANSWER_SOURCE_CONTRACT.md` | `scripts/ui_server.py` priority chain, `personas/*.json` |
| Conversation/frame/E4 | `docs/CONVERSATION_ARCHITECTURE.md` | `_FRAME_ORDER`, `skip_when`, `_infer_question_topic_engine`, `_resolveNextEngineId()` |
| ASR/browser | `docs/ASR_PIPELINE.md` | `ui/app.js` recognizer/recovery code, `content/recovery_phrases.json` |
| Tests | `docs/TEST_STRATEGY.md` | `tests/`, `tests/conftest.py`, `.github/workflows/coverage_scan.yml` |
| Generated artifacts | `docs/ARCHITECTURE.md` §14; `docs/TEST_STRATEGY.md` §12–§13 | `tools/build_runtime_artifacts.py`, `runtime/out_phase7/` |
| Persistence | `docs/STATE_CONTRACT.md`; `docs/ARCHITECTURE.md` §6.4, §13 | `scripts/progress_store.py`, `scripts/beta_profile.py`, `scripts/learner_memory.py`, `scripts/session_intelligence.py` |
| Deployment | `docs/ARCHITECTURE.md` §13 | `railway.toml`, `Procfile`, `nixpacks.toml`, `/api/version` |
| Documentation | This document; `docs/ARCHITECTURE.md` §20 | `docs/*.md` |

Application baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Application baseline tag: `architecture-baseline-2026-07-12-r2`
Documentation branch: `docs/architecture-v1`
Document status: `Approved v1 — R2 baseline`
Last verified date: `2026-07-13`
