# MandarinOS Architecture

## 1. Purpose and audience

This document is the **primary technical onboarding map** for MandarinOS. It is the starting point for any maintainer, reviewer, or AI
coding agent who needs to understand what the system is, where responsibilities live, and how a learner turn travels through it, before
touching code.

It is a concise description of the R2 implementation at:

- baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
- baseline tag: `architecture-baseline-2026-07-12-r2`

This document is an **approved R2 orientation map**, subordinate to the four approved detailed contracts for subsystem behaviour
(`docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md`, `docs/ASR_PIPELINE.md`). Where this
document and a detailed contract disagree, the detailed contract is correct and this document is stale.

Audience: new developers joining the project; the maintenance team; technical reviewers auditing a change; AI coding agents (Cursor and
others) operating on this repository; the project owner diagnosing a reported regression. It does not repeat the field-by-field state
tables, the `counter_reply` priority chain, the ASR call-site inventory, or the frame-selection algorithm — those live in the four contracts
linked throughout.

## 2. Product definition

MandarinOS is a **conversation simulator for practising sustained spoken Mandarin interaction**.

It is not primarily: a vocabulary-drill application; a generic AI chatbot; a general-knowledge assistant; a conventional linear lesson
engine.

The main product loop, repeated turn after turn with a persona:

1. **listen** — the learner hears/reads a partner sentence (frame);
2. **respond** — the learner speaks or types an answer, or selects an option;
3. **recover when necessary** — soft repair, clarification, or a recovery phrase when input is unclear or absent (`docs/ASR_PIPELINE.md`, `docs/CONVERSATION_ARCHITECTURE.md`);
4. **receive a persona answer** — the partner produces a Chinese reply, with English and pinyin support **where available** — not every `counter_reply` has non-empty English or pinyin (`docs/ANSWER_SOURCE_CONTRACT.md`);
5. **continue through a conversational topic** — the engine and frame selector choose the next conversational move (`docs/CONVERSATION_ARCHITECTURE.md`);
6. **practise depth, responsiveness, and repair** — not just vocabulary recall.

The unit of learner practice is the conversation itself, not an isolated drill item.

## 3. Authoritative source hierarchy

When evidence conflicts, resolve in this order (highest first):

1. **verified production code** at the named baseline commit;
2. **executable behavioural tests** that exercise the real implementation;
3. **the four approved R2 detailed contracts** (below), each authoritative for its own subsystem;
4. **static-source or mirrored-logic verification tests** (assert on source text or a reimplementation, not the real running function);
5. **current product-intent documents** (e.g. `AI_CONTEXT.md`, phase briefings);
6. **historical, exploratory, or superseded design documents**;
7. **comments or filenames** not supported by current behaviour.

Code and real behavioural tests establish *actual* behaviour; the four approved contracts describe that verified baseline for their
respective subsystems. **This document is an approved orientation map but is not one of the four approved R2 detailed contracts** — it
remains subordinate to them for behavioural detail (Section 1). Historical documents, and any document labelled `LOCKED`, `FINAL`, or
similar, are not authoritative merely by title or intent — they must be checked against code at the current baseline.

The four approved R2 contracts:

- [`docs/CONVERSATION_ARCHITECTURE.md`](CONVERSATION_ARCHITECTURE.md) — the turn lifecycle, engine/frame-selection model, recovery, and the E4 future-engine handoff.
- [`docs/STATE_CONTRACT.md`](STATE_CONTRACT.md) — the complete field-by-field inventory of client, server, and persistent state, with defaults, merge semantics, and consumption status.
- [`docs/ANSWER_SOURCE_CONTRACT.md`](ANSWER_SOURCE_CONTRACT.md) — exactly how `counter_reply`, `counter_reply_en`, and `counter_reply_pinyin` are produced, in priority order, with fallbacks and deduplication.
- [`docs/ASR_PIPELINE.md`](ASR_PIPELINE.md) — the path from microphone/typed input to normalised, routed text, including client-intercepted recovery and late text repair.

## 4. System context

```text
Learner
  ↓
Browser client (ui/)
  - UI rendering (index.html, styles.css)
  - speech recognition (browser SpeechRecognition)
  - transcript and recovery controls
  - client session state (app.js)
  ↓ JSON /api/*
Python application server (scripts/ui_server.py)
  - turn routing
  - answer generation
  - frame selection
  - state updates
  - learner memory
  - progress / session services
  ↓
Source-controlled content (p2_frames.json, personas/, content/)
  + optional persistent data storage (data/, or a mounted volume via MANDARINOS_DATA_DIR)
```

Verified external/browser-provided capabilities: **browser `SpeechRecognition`** — the Chinese answer microphone and the auxiliary English
recognizer are both browser-native; there is no server speech-recognition endpoint (`docs/ASR_PIPELINE.md`); **browser `speechSynthesis`** —
all text-to-speech is client-only via `ui/ttsSpeak.js`, calling `window.speechSynthesis`/`SpeechSynthesisUtterance` directly, with no
`/api/tts` or equivalent server endpoint; **external translation API** — the translate-assisted typing panel's `doTranslate()` calls the
third-party `https://api.mymemory.translated.net/get` endpoint directly from the browser, not a MandarinOS server endpoint; **Railway
deployment** — the production server is deployed via Railway (`railway.toml`, `Procfile`, `nixpacks.toml`, see Section 13); **mounted
persistent storage** — configured only where `MANDARINOS_DATA_DIR` points at a Railway volume (see Section 13).

No external AI-generation call occurs during an ordinary conversation turn at this baseline. `/api/run_turn` is answered entirely by the
structured Python engine; the hybrid-AI layer described in `AI_CONTEXT.md` §12 is a documented future direction, not current behaviour.

## 5. Repository map

| Path | Responsibility | Runtime-critical? | Change risk | Authoritative documentation |
| ---- | --------------- | -----------------: | ----------- | ---------------------------- |
| `scripts/ui_server.py` | HTTP server, routing, turn engine, answer/frame selection, state assembly | Yes | Very high | All four contracts |
| `scripts/learner_memory.py` | Load/save/clear of persistent learner-memory fields | Yes | Medium | `STATE_CONTRACT.md` |
| `scripts/learner_memory_capture.py` | Maps a turn's answers to learner-memory field updates | Yes | Medium | `STATE_CONTRACT.md` |
| `scripts/progress_store.py` | Append-only per-learner progress snapshots | Yes (persistence) | Low–medium | none dedicated (see §11) |
| `scripts/session_intelligence.py` | Opt-in end-of-session capture (`MANDARINOS_SESSION_CAPTURE`) | Conditional | Low | `ASR_PIPELINE.md` §16 (capture semantics) |
| `scripts/beta_profile.py` | Per-learner beta comfort/level profile persistence | Yes (persistence) | Low | none dedicated |
| `ui/app.js` | Client conversation logic: rendering, ASR lifecycle, recovery, request construction, client state | Yes | Very high | All four contracts |
| `ui/index.html` | Browser entry page markup, element IDs the client script binds to | Yes | Medium | `ASR_PIPELINE.md` (Challenge Mode) |
| `ui/styles.css` | Visual presentation, including Challenge Mode visibility rules | Yes | Medium | `ASR_PIPELINE.md` |
| `ui/ttsSpeak.js` | Sole client TTS boundary (`window.speechSynthesis`) | Yes | Medium | `ASR_PIPELINE.md` |
| `p2_frames.json` (and `p1_frames.json`) | Source-of-truth frame/sentence content, engines, difficulty, move types | Yes | High (shared priority/ordering data) | `CONVERSATION_ARCHITECTURE.md` |
| `personas/*.json` + `_index.json` + `_schema.json` | Persona profile, voice lines, discoverable facts (Chinese + English) | Yes | Medium | `ANSWER_SOURCE_CONTRACT.md` |
| `content/*.json` (e.g. `recovery_phrases.json`, `mirror_questions.json`, `response_patterns.json`) | Source content banks for recovery, mirror questions, response templates | Yes | Medium | `ASR_PIPELINE.md`, `ANSWER_SOURCE_CONTRACT.md` |
| `runtime/*.py` (e.g. `runtime/engine.py`) | Committed runtime resolver/engine modules | Yes | High | `CONVERSATION_ARCHITECTURE.md` |
| `runtime/out_phase7/*.runtime.json` | **Generated** runtime artifacts (gitignored) — see §14 | Yes (once built) | Do not hand-edit | `AI_CONTEXT.md` §1.1 |
| `tools/build_runtime_artifacts.py` | Builder that regenerates `runtime/out_phase7/` from source content | Build-time | Medium | `AI_CONTEXT.md` |
| `tests/` | Pytest suite, Node verify scripts, fixtures, `conftest.py` marker/tier config | No (dev-time) | Low (but must stay in sync with contracts) | §15 below |
| `.cursor/rules/mandarinos-architecture.mdc`, `.cursor/rules/mandarinos-ui-objects.mdc` | Standing Cursor rules enforced every session | No | N/A | §20 |
| `AI_CONTEXT.md` | Fast orientation map and non-negotiable guardrails for AI assistants | No | N/A | §20 |
| `docs/` | Architecture contracts, phase briefings, specs, reports | No | N/A | §20 |
| `data/` (gitignored) | Default local persistence: `learner_memory.json`, `progress/`, `sessions/`, `beta_profiles/`, `diag/` | Yes (persistence) | Low (never source-controlled) | `STATE_CONTRACT.md` |

Distinctions: **source files** — `scripts/*.py`, `ui/*`, `p1/p2_frames.json`, `personas/*.json`, `content/*.json`, `runtime/*.py`;
**generated runtime artifacts** — everything under `runtime/out_phase7/` (gitignored; see §14 — must not be hand-edited); **tests** —
`tests/test_*.py`, `tests/verify_*.js`, `tests/conftest.py`; **documentation** — `docs/`, `AI_CONTEXT.md`; **deployment/runtime data** —
`railway.toml`, `Procfile`, `nixpacks.toml`, `requirements.txt`, and everything under `data/` at runtime.

## 6. Runtime components

### 6.1 Browser client (`ui/app.js`, `ui/index.html`, `ui/styles.css`, `ui/ttsSpeak.js`)

Verified responsibilities: rendering partner and learner turns (`#frameSentence`, `#transcriptPanel`, `.option-panel` UI standard); the
browser `SpeechRecognition` lifecycle for the Chinese answer microphone and the auxiliary English-translation microphone
(`docs/ASR_PIPELINE.md`); client-intercepted spoken recovery (exact-phrase matches handled without a server round-trip); request
construction for `/api/run_turn` and the other `/api/*` calls; client-owned counters/session state (e.g. `window._consecutiveNotUnderstood`,
`_lastAcceptedAsrKey`/`_lastAcceptedAsrTime`, `_challenge.recoveryCount` — full inventory in `docs/STATE_CONTRACT.md`); Challenge Mode
visibility (`toggleChallengeMode()` + CSS); consuming server response fields and applying `state_update` (including
`_resolveNextEngineId()`'s use of `state_update.current_engine` for the E4 handoff); TTS playback (`ttsSpeak()`, browser-native
`speechSynthesis` only). Before the Chinese recognizer opens, the client calls `speechSynthesis.cancel()` as a **mitigation** intended to
reduce the chance the recognizer transcribes the app's own audio; the R2 implementation does not provide an absolute self-capture guarantee
(detailed evidence: `docs/ASR_PIPELINE.md`).

The client does **not** own: answer-source selection, frame selection, persistent learner-memory storage, or progress/session persistence —
those are server responsibilities below.

### 6.2 Python server (`scripts/ui_server.py`)

Verified responsibilities: HTTP routing for all `/api/*` endpoints (`Handler.do_GET`, `Handler.do_POST`; there is no shared router table —
dispatch is a sequence of `path ==` checks); text normalisation for routing (`_normalize_zh_for_routing`) and late ASR-junk repair
(`_repair_asr_junk_text`); question/signal classification feeding the answer-source priority chain; answer-source priority resolution
producing `counter_reply` / `counter_reply_en` / `counter_reply_pinyin` (`docs/ANSWER_SOURCE_CONTRACT.md`); frame selection producing the
next conversational move (`docs/CONVERSATION_ARCHITECTURE.md`); response assembly and `state_update` construction
(`docs/STATE_CONTRACT.md`); learner-memory capture/persistence (`scripts/learner_memory.py`, `scripts/learner_memory_capture.py`);
progress/session services (`scripts/progress_store.py`, `scripts/session_intelligence.py`, `scripts/beta_profile.py`); diagnostics where
enabled (`MANDARINOS_DIAG_TOKEN` gate; `_diag_append` writes JSONL).

### 6.3 Conversation content

Distinct roles, verified from content files and `personas/_schema.json`: **frames** (`p2_frames.json`, `p1_frames.json`) are partner
sentence patterns tagged with engine, difficulty, `move_type`, and slot metadata — the backbone of the conversational ladder; **personas**
(`personas/*.json`) hold per-character `profile`, `voice_lines`, and `discoverable_facts` (plus English variants), consulted by
answer-source resolution; **recovery phrase banks** (`content/recovery_phrases.json`) are the active pack read by the builder — an older
`content/recovery_phrases_v1_2.json` and a legacy backup file also exist but are not read by the current builder; **mirror-question
content** (`content/mirror_questions.json`, `content/mirror_core_map.json`) holds learner reverse/mirror questions and their mapping to
partner frames; **inline content still embedded in code** — `docs/ANSWER_SOURCE_CONTRACT.md` documents specific cases where Chinese response
text or logic remains inline in `scripts/ui_server.py` rather than in a content JSON file.

This repository does **not** make all conversation content data-driven; some answer paths remain inline in Python — treat that as current
fact, not a target to imitate.

### 6.4 Persistent services

Distinct, independently gated stores, all defaulting to `{repo}/data` unless `MANDARINOS_DATA_DIR` is set:

| Store | Path (relative to data dir) | Written by | Gate |
| ----- | ---------------------------- | ---------- | ---- |
| Learner memory | `learner_memory.json` | `POST /api/run_turn` (via capture), `POST /api/reset_memory` | always active |
| Progress snapshots | `progress/{learner_id}.json` | `POST /api/end_session`, `POST /api/save_progress` | always active |
| Session capture | `sessions/{learner_id}/{session_id}.json` | `POST /api/end_session` | `MANDARINOS_SESSION_CAPTURE=1` (opt-in; disabled by default) |
| Beta profiles | `beta_profiles/{learner_id}.json` | `POST /api/beta_profile` | always active |
| ASR diagnostics | `diag/asr_traces.jsonl` | `POST /api/run_turn` (server-side), `POST /api/diag/asr-trace` (client bundle) | `MANDARINOS_DIAG_TOKEN` set |
| Challenge-mode history | `data/progress_history.json` (fixed repo-relative path, **not** under `MANDARINOS_DATA_DIR`) | `POST /api/end_session` (Challenge Mode only) | always active |

DOM and JavaScript session state are not automatically or per-turn persisted. `conversationTranscript` remains client-owned for the lifetime
of the browser tab; `/api/end_session` can submit that transcript, and it **may** be persisted when `MANDARINOS_SESSION_CAPTURE=1`.
Consequently, client-intercepted spoken recovery — which never reaches `/api/run_turn` — can still appear as a client-authored transcript
record in opt-in end-session capture (`docs/ASR_PIPELINE.md` §16).

Learner memory, progress, session capture, beta profiles, and diagnostics all use the data directory selected by `MANDARINOS_DATA_DIR`; those
stores survive a Railway restart/redeploy only when that directory points at persistent mounted storage (see Section 13). Challenge history
is written independently to the fixed repo-relative `data/progress_history.json`; it does **not** honour `MANDARINOS_DATA_DIR`, so the normal
`/data` volume configuration does not make it durable — it remains ephemeral on Railway unless that fixed location is preserved separately.

## 7. One-turn lifecycle

1. The current partner frame is presented (`#frameSentence`, TTS where applicable).
2. The learner responds by speaking, by translate-assisted typing, or by selecting an option.
3. The client may intercept an eligible exact spoken recovery phrase locally — this never reaches the server (`docs/ASR_PIPELINE.md`).
4. Otherwise the client constructs the request and `conversation_state.last_answer` (`submitted_text`/`selected_option_hanzi`, engine state, etc.).
5. The server derives raw `answer_text` and routing-normalised text from that submission (`_normalize_zh_for_routing`).
6. Classifiers and answer sources consume the appropriate raw or routing-normalised form, depending on the verified call path, and select an initial Chinese/English answer candidate (`docs/ANSWER_SOURCE_CONTRACT.md`) — some highest-priority initiative/repair branches consume raw `answer_text`, while many recovery/direct-answer paths consume routing-normalised text; the detailed consumer inventory remains in `ASR_PIPELINE.md`. Pinyin is not assumed to exist as part of this initial tuple.
7. E4 (initiative-follow) eligibility is computed from that priority-chain candidate.
8. Deduplication (`last_counter_reply`, `recent_persona_replies`), the exact-repeat guard, and repair escalation may replace the candidate, and may replace or recompute its paired English — all still **before** frame selection.
9. `counter_reply_pinyin` is derived from the resulting pre-response Chinese answer.
10. Frame selection independently produces the current response's next conversational move (`docs/CONVERSATION_ARCHITECTURE.md`).
11. The server assembles response fields (`counter_reply*`, `frame_text*`, `data.engine_id`), slot substitutions, and `state_update` (including `state_update.current_engine` for E4).
12. A **final response-level** `_repair_asr_junk_text()` guard may still alter `frame_text`/`counter_reply` Chinese text immediately before JSON serialisation, after frame selection and response assembly are already complete — its final call sites do not update the already-assembled paired English/pinyin fields to match (`docs/ASR_PIPELINE.md` §11).
13. The client renders the assembled response and appends a transcript entry.
14. The client applies any E4 engine handoff via `_resolveNextEngineId()`, setting `window._currentEngineId` for use on the **following** request — a one-response transition delay, not an immediate same-response effect.

This summary cross-references, and does not replace, the detailed tables in the four approved contracts.

## 8. State model at a glance

Main state categories: **DOM/UI state** (visible text, hidden Challenge Mode content, panel visibility); **client-global session state** (JS
globals such as `window._currentEngineId`, `_lastAcceptedAsrKey`, `_consecutiveNotUnderstood`, `conversationTranscript`); **transported
`conversation_state`** (the object the client sends on every `/api/run_turn` request, carrying forward server-authored fields); **returned
`state_update`** (server-authored fields the client is expected to merge back into its next `conversation_state`); **server-local
per-request variables** (computed and discarded within one request; never transported or persisted); **persistent learner memory**
(`learner_memory.json`, keyed by `learner_id`); **persistent progress data** (append-only snapshots per learner); **optional
session/diagnostic records** (gated by `MANDARINOS_SESSION_CAPTURE` and `MANDARINOS_DIAG_TOKEN` respectively).

Key emphases, all detailed in `docs/STATE_CONTRACT.md`: state is distributed across client, transport payload, and server-local scope —
there is no single state object; ownership is not uniform, some fields are client-owned, some server-owned, some transported both ways;
**not every server-emitted `state_update` field is consumed** by the client — a field existing in a response does not prove it has an
effect; a same-tab "new session" reset is not identical to a full page reload, they clear different scopes; switching personas mid-session
is not the same operation as a full session reset; persistence of any given field depends entirely on which store (if any) it flows into,
per Section 6.4.

`docs/STATE_CONTRACT.md` is the field-level authority; nothing here overrides it.

## 9. Conversation-control model

**Current engine**: a topic engine — the canonical R2 engine identifiers are `identity`, `place`, `work`, `family`, `hobby`, `travel`,
`food`, and `life` (the last gated off until `MIN_TURNS_FOR_LIFE_ENGINE` exchanges) — is active at any time and constrains frame selection. **Frames and ladders**: `p2_frames.json`/`p1_frames.json` content, ordered by `FRAME_ORDER` guidance, difficulty ramp, and
mutual-exclusion/`skip_when` rules. **Answer generation**: a strict priority chain of producers resolves `counter_reply`/EN/pinyin
(`docs/ANSWER_SOURCE_CONTRACT.md`), including mirror answers, direct-persona answers, E3 working-memory reuse, and recovery. **Frame
selection**: a mostly independent process choosing the next partner move. **E4 (initiative-follow)**: when the learner asks a direct
question, E4 can hand off the *following* request's active engine via `state_update.current_engine`; the client applies this with a
one-response delay.

State explicitly:

> The persona answer and the next frame are separate outputs produced by separate mechanisms, although current-turn flags and future-engine handoff can coordinate them.

Links: `docs/CONVERSATION_ARCHITECTURE.md`, `docs/ANSWER_SOURCE_CONTRACT.md`.

## 10. Input and ASR model

**Chinese microphone**: the primary spoken-answer mechanism, using the browser `SpeechRecognition` API configured for Chinese.
**Translate-assisted typed input**: the learner types English into `#engInput` (editable) and `doTranslate()` renders a generated Chinese
candidate as read-only tokens in `#engTranslatedZh` (a `<div>`, not an input and not `contenteditable`); the Use-button handler
(`useBtn`) submits that rendered candidate verbatim — the learner submits the generated Chinese candidate after reviewing it, not an edited
Chinese string; only the English source text is directly editable. **Auxiliary English microphone**: a separate `en-US` recognizer instance
supporting the translate-assist panel; its error handling is less specific than the Chinese recognizer's. **Synthetic test payloads**: test
code can submit `submitted_text`/`selected_option_hanzi` directly, bypassing any recognizer. **Client-intercepted spoken recovery**: exact
matches against recovery phrases are handled entirely client-side and never reach `/api/run_turn`. **Raw versus routing-normalised text**:
the server computes a routing-normalised form (`_normalize_zh_for_routing`) distinct from the raw submitted/answer text; both may appear in
different places downstream. **No reliable spoken-versus-typed server marker**: `_sel_trace.input_mode` is a four-way heuristic over which
submission fields are populated, not a true spoken-versus-typed indicator (Mechanisms 1 and 2 are both labelled `"typed"`). **Challenge
Mode** is a client-side visibility/reveal layer: it does not change the text submitted to `/api/run_turn`, nor server-side routing,
answer-source selection, or frame selection — but it **does** change client recovery presentation, recovery-count-driven reveal behaviour,
and which recovery/options UI is visible; whether any of this becomes persistent remains separately conditional on the session-capture
mechanism (§6.4, `docs/ASR_PIPELINE.md`). **Final Chinese-only ASR-junk repair risk**: `_repair_asr_junk_text()` runs late and only against
Chinese text; some call sites substitute repaired values into placeholder-bearing English/pinyin fields rather than independently
re-translating or re-romanising them.

Full call-site inventory: `docs/ASR_PIPELINE.md`.

## 11. Data and content flow

Where the application gets its content, as verified: **persona facts and voice lines** — `personas/*.json` (`profile`, `voice_lines`,
`discoverable_facts`, plus `_en` variants), loaded at server startup and indexed via `personas/_index.json`; **frames and pinyin** —
`p2_frames.json`/`p1_frames.json`, each frame carrying `text`, `pinyin`, `text_en`, engine, difficulty, and move-type metadata; **recovery
phrases** — `content/recovery_phrases.json` (schema 1.3, the file the builder actually reads); older schema variants exist in `content/` but
are not consumed by the current build; **mirror questions** — `content/mirror_questions.json` plus `content/mirror_core_map.json` for the
frame → mirror-topic mapping; **response templates** — `content/response_patterns.json`; **city/place content** — R2 draws from **multiple
competing sources**, not one pool: frame and slot content in `p1_frames.json`/`p2_frames.json`; persona city/hometown facts; and several
hardcoded Python dictionaries inline in `scripts/ui_server.py` (`_CITY_LOCATION_BRIEF`, `_CITY_FOOD_POOL`, `_CITY_FEATURE_POOL`,
`_FOOD_POOL_INLINE`, `_FEAT_POOL_INLINE`) plus generic inline fallback templates; these sources can diverge and are fully inventoried in
`docs/ANSWER_SOURCE_CONTRACT.md`, not reproduced here; **learner facts** — captured into `learner_memory.json` via
`scripts/learner_memory_capture.py`, restricted to the six canonical keys in `LEARNER_MEMORY_KEYS` (`learner_name`, `hometown`, `lives_in`,
`job_or_study`, `family`, `favourite_food`); other attempted keys (e.g. a company-name field) are computed but filtered out before
persistence; **progress/session data** — written only through `/api/save_progress` and `/api/end_session`, per Section 6.4.

Known duplication/competing sources already verified elsewhere in the R2 contracts: multiple recovery-phrase file variants in `content/`
(only one is builder-active), and documented inline Chinese content in `scripts/ui_server.py` alongside JSON-driven content
(`docs/ANSWER_SOURCE_CONTRACT.md`). This repository does not implement a single unified content schema across frames, personas, and recovery
phrases — do not assume a shared schema when adding new content types.

## 12. API surface

| Endpoint | Method | Purpose | Main caller | Persistence effect |
| -------- | ------ | ------- | ------------ | ------------------- |
| `/api/run_turn` | POST | Main conversation-turn engine: normalisation, answer-source resolution, frame selection, response/state assembly | `ui/app.js` `runTurn()` | Conditionally writes `learner_memory.json` (via capture) and diagnostics JSONL (if `MANDARINOS_DIAG_TOKEN` set and client sends `diag_trace_id`) |
| `/api/version`, `/api/health` | GET | Returns deployed git branch/SHA (+ source), status, diagnostics-enabled flag | Not called from `ui/app.js`; used for deployment verification and by tests | None (stateless) |
| `/api/personas` | GET | Lightweight persona index | `ui/app.js` | None (in-memory index) |
| `/api/personas/{id}` | GET | Full persona JSON for one persona | Not called from `ui/app.js` at this baseline | None |
| `/api/cards` | GET | Serves a runtime card JSON file by path | `ui/app.js` (card panel) | None |
| `/api/memory` | GET | Reads learner memory for a `learner_id` | `ui/app.js` | Read-only |
| `/api/reset_memory` | POST | Clears all learner-memory fields for a `learner_id` | `ui/app.js` | Writes `learner_memory.json` |
| `/api/progress` | GET | Returns progress snapshots for a learner | `ui/app.js` | Read-only |
| `/api/save_progress` | POST | Client fire-and-forget progress snapshot backup | `ui/app.js` | Writes `progress/{learner_id}.json` |
| `/api/end_session` | POST | Computes end-of-session scorecard, saves progress, optionally session capture and Challenge history | `ui/app.js` | Writes progress snapshot; optionally writes session JSON (opt-in); optionally writes Challenge history |
| `/api/capability` | GET | Read-only longitudinal capability trend, derived from progress snapshots | `ui/app.js` | Read-only |
| `/api/beta_profile` | GET/POST | Reads or writes a learner's beta comfort/level profile | `ui/app.js` | Writes `beta_profiles/{learner_id}.json` on POST |
| `/api/gloss` | POST | Server-side Chinese→English gloss for a transcript line | `ui/app.js` | In-memory cache only, no file write |
| `/api/diag/asr-trace` | POST | Appends a client-authored ASR diagnostic bundle | `ui/app.js` (diagnostics build) | Writes `diag/asr_traces.jsonl`, gated by `X-Diag-Token` matching `MANDARINOS_DIAG_TOKEN` |
| `/api/progress/all` | GET | Admin export of all learners' progress | Admin tooling only, gated by `admin_token` | Read-only |
| `/api/sessions/list`, `/api/sessions/get` | GET | Admin listing/fetch of captured session records | Admin tooling only | Read-only |

Not implemented at this baseline: any dedicated `/api/tts` endpoint (TTS is browser-`speechSynthesis`-only); any MandarinOS-hosted
translation endpoint (the translate-assist panel calls the third-party MyMemory API directly); an `/api/next_question` endpoint (referenced
only in a code comment, with no handler). No credentials, tokens, or secret values are reproduced here; the `admin_token` and `X-Diag-Token`
mechanisms are named but their values are not documented.

## 13. Deployment and runtime storage

The browser client is served by the same Python process that implements the API: `/` issues a 302 redirect to `/ui/index.html`, and static
files under `ui/` (including `app.js`, `styles.css`, `ttsSpeak.js`) are served by the same handler.

Production deployment is Railway-based:

- `Procfile`: `web: python scripts/ui_server.py`
- `railway.toml` `[deploy].startCommand`: `"python scripts/ui_server.py"`
- `nixpacks.toml` forces the Python provider.
- The server binds `0.0.0.0:{PORT}`, reading `PORT` from the environment (default `8765` when unset, e.g. for local runs); there is no `--port` CLI flag.

**A local commit alone is not deployed.** It must be pushed to whichever branch the Railway service is configured to watch before Railway
builds and deploys it. This repository's own configuration files do not state which branch Railway watches (that is a Railway dashboard
setting, not a repository file); do not assume a merge to `main` is required unless the Railway project's branch configuration says so.

Persistent storage: `MANDARINOS_DATA_DIR` selects the base directory for learner memory, progress, session capture, beta profiles, and ASR
diagnostics; it defaults to `{repo}/data` when unset. `railway.toml` documents the required manual steps to make this durable on Railway:
add a Volume mounted at `/data`, then set `MANDARINOS_DATA_DIR=/data` in the service's environment variables. Without that volume and
environment variable, those stores are **ephemeral** on Railway and are lost on redeploy or restart. Challenge history is written
independently to the fixed repo-relative `data/progress_history.json`, which does **not** honour `MANDARINOS_DATA_DIR` — the `/data` volume
configuration above does not make it durable, and it remains ephemeral on Railway unless that fixed location is preserved separately (§6.4).

`/api/version` is the deployed-code verification mechanism: it returns the branch, short and full git SHA, and the source of that SHA
(`"git"` if resolved live at process start, `"railway_env"` if taken from `RAILWAY_GIT_COMMIT_SHA`, `"unknown"` otherwise). Compare this
against the expected commit after any deploy.

## 14. Generated artifacts and build boundaries

`tools/build_runtime_artifacts.py` reads source content and writes generated JSON into `runtime/out_phase7/`, which is listed in
`.gitignore` and therefore **not committed** to source control. Verified source → generated mappings:

| Source | Generated artifact |
| ------ | -------------------- |
| `content/recovery_phrases.json` | `recovery_phrases.runtime.json` |
| `p1_frames.json` + `p2_frames.json` + `tools/cards/out/cards_by_id.json` | `frame_options.runtime.json`, `slot_invariant_violations.runtime.json` |
| `p1_frames.json` + `p2_frames.json` + `p1_words.json` + `p2_words.json` | `frame_tokens.runtime.json` and `frame_render_tokens.runtime.json` — both written byte-identical by the same final call (`write_frame_tokens()`); an earlier, differently-computed write of `frame_render_tokens.runtime.json` executes first in the same run but is unconditionally overwritten before the builder finishes, so it never survives to the final artifact |
| `tools/cards/out/cards_by_id.json` | Feeds frame options; also produces `cards_index.runtime.json` |
| `p1_fillers.json` + `p2_fillers.json` | Sentence-level options inside `frame_options.runtime.json` |
| `word_character_links.json` + `characters_1200.json` (root or `data/`) | `word_etymology.runtime.json` |
| Optional narrative file (`data/word_etymology_top1000_curated_v2_inferred_narrative.json`) | Merged into `word_etymology.runtime.json` |
| (build metadata) | `build_manifest.json` |

Verified build invocation: `python tools/build_runtime_artifacts.py` (its `main()` guarded by `if __name__ == "__main__":`). Regeneration is
**not automatic**: `scripts/ui_server.py` does not call this builder at startup, and neither `railway.toml` nor `nixpacks.toml` configures a
build-phase command that runs it — the builder must be run explicitly before a local run or a deploy that depends on updated artifacts.

By contrast, `runtime/*.py` modules (e.g. `runtime/engine.py`) are hand-written source and **are** committed — the gitignore rule applies
only to the `out_phase7/` output subdirectory. Stale generated content can cause apparent code/content mismatches if a source file was
edited but the builder was not re-run.

> Edit the source-of-truth content, then run `python tools/build_runtime_artifacts.py` to regenerate; do not treat a generated runtime file as the primary editable source, and do not assume artifacts refresh automatically on server start or deploy.

## 15. Test architecture at a glance

This is an orientation summary only; a detailed test strategy is deferred to a future `TEST_STRATEGY.md`. Verified tiers present in
`tests/`: **Python behavioural/unit tests** — the majority of `tests/test_*.py` files, run without a live server; **`live_server`-marked
integration tests** — a smaller subset (e.g. `tests/test_golden_regression.py`, `tests/test_golden_conversation_scenarios.py`,
`tests/test_interaction_regression.py`, `tests/test_blue_question_relevance.py`) that exercise a running server on `http://localhost:8765`
and are skipped automatically if no server is listening there (`tests/conftest.py`); **JavaScript tests using extracted real helpers** —
`tests/e4_resolve_next_engine_id_cli.js` combined with `tests/_load_app_js_helper.js`, which extract and execute actual function source from
`ui/app.js` under Node rather than a hand-written reimplementation; **standalone Node verify scripts** — `tests/verify_asr_filler.js`,
`tests/verify_e4_client_handoff.js`, `tests/verify_spoken_recovery_exact_match.js`, `tests/verify_phase12c.js`, run directly with `node`
(several of these are mirrored/static verification rather than execution of the real helper — see `docs/ASR_PIPELINE.md` §12 and Section 22
below); **deployment/operational tests** — `tests/test_deployment_hygiene.py`, which asserts on the contents of
`Procfile`/`requirements.txt` rather than conversation behaviour.

Explicit caveats: **mirrored or static-source tests do not prove the shipped function behaves correctly** — a test that reimplements logic
in the test file, or asserts on source text, can pass while the real function is broken; **tests using real implementation code carry
greater evidentiary weight** than mirrored reimplementations, per the Section 3 hierarchy; **a passing unit test does not establish
client/server round-trip correctness** — that requires a `live_server` test or a manual/production check; **production deployment
verification is a distinct step**, performed via `/api/version` and/or a live smoke test against the deployed URL, not by any local test
run.

Verified test commands, quoted from the repository (do not invent others):

```bash
# Core unit/contract suite (default) — tests/conftest.py
python -m pytest tests/ -m "not live_server"

# Local integration suite — tests/conftest.py (requires server running on localhost:8765)
python -m pytest tests/ -m "live_server"

# Deployment / operational tests — tests/conftest.py
python -m pytest tests/test_deployment_hygiene.py

# Manual JavaScript verification — tests/conftest.py
node tests/verify_asr_filler.js

# Static-only golden regression check — README.md
python tests/test_golden_regression.py --static-only
```

## 16. High-risk files and change zones

**`scripts/ui_server.py`** — one very large file implementing routing, normalisation, the answer-source priority chain, and frame selection;
a local change can shift shared ordering or shared helper behaviour. **`ui/app.js`** — one very large client file implementing rendering,
ASR lifecycle, recovery interception, and state application; similarly prone to shared-behaviour drift. **Answer-source priority ordering**
(`docs/ANSWER_SOURCE_CONTRACT.md`) — reordering or inserting a new producer changes which answer wins for many unrelated inputs.
**Frame-selection ordering** (`FRAME_ORDER`, `skip_when`, mutual exclusion) — changes here affect topic pacing across the whole frame set,
not just one frame. **State transport** (`conversation_state`/`state_update`) — adding, renaming, or changing the merge semantics of a field
can silently break a consumer that reads it by name on either side. **Reset logic** — same-tab new-session reset, page reload, and persona
switch each clear different scopes; conflating them is a common source of "state didn't clear" bugs. **E4 timing** — the one-response
transition delay between `state_update.current_engine` and the client applying it is easy to get wrong when adding new engine-handoff logic.
**ASR recovery interception** — client-intercepted recovery never reaches the server, so a change here is invisible to server-side tests and
per-turn diagnostics. **Translation and pinyin finalisation** — server-side pinyin/English coverage is incomplete in places; late repair
(`_repair_asr_junk_text`) substitutes into placeholder-bearing fields rather than independently retranslating them. **Duplicated inline
content pools** — some Chinese response content lives inline in Python rather than in a content JSON file; editing one copy without checking
for the inline duplicate can produce inconsistent behaviour. **Generated runtime artifacts** — editing `runtime/out_phase7/*.runtime.json`
directly is invisible to the source-of-truth content and will be silently overwritten by the next build.

> A small local change can alter unrelated behaviour when it changes a shared priority chain, shared state field, or shared normalisation function.

## 17. Safe change workflow

1. Identify the authoritative contract for the area being changed (Section 3).
2. Reproduce the problem against the running application, not just by reading code.
3. Trace the actual producers and consumers of the relevant field or behaviour.
4. Distinguish current-frame/current-response behaviour from following-turn behaviour (many bugs are actually a one-turn timing confusion, e.g. E4's transition delay).
5. Identify all state ownership and reset implications (Section 8) before editing.
6. Add a failing regression test using real implementation code where possible (an extracted-helper JS test or a Python test against the real function), not only a mirrored/static assertion.
7. Implement the smallest bounded change that fixes the identified cause.
8. Run the targeted test(s) for the change.
9. Run the appropriate broader suite (Section 15) — at minimum the non-`live_server` suite, plus `live_server` tests if a server is available.
10. Inspect the diff for unintended scope creep.
11. Update the affected architecture documentation (one of the four contracts, or this map, as appropriate).
12. Follow the deployment path that matches the change. **Documentation-only change** — commit on the documentation branch (e.g.
    `docs/architecture-v1`); push that branch; no Railway deployment or `/api/version` check is required unless the documentation is
    deliberately merged into the branch Railway watches. **Production/runtime change** — commit and push to the branch Railway is
    configured to watch; wait for the deployment to complete; verify the expected commit through `/api/version`; verify the affected
    production behaviour. A local commit is never deployed until pushed to Railway's watched branch — `docs/architecture-v1` is a
    documentation branch, not itself Railway's deployment branch (Section 13).

AI coding agents must not implement a change purely from a historical design document (Section 20) without first reconciling it against the
approved R2 contracts and current tests — historical documents can describe intent that was superseded by later, undocumented code changes.

## 18. Regression-diagnosis entry points

| Symptom | Start here | Then inspect |
| ------- | ---------- | -------------- |
| Wrong next question | `docs/CONVERSATION_ARCHITECTURE.md` frame-selection section | `p2_frames.json` ordering/`skip_when`, `FRAME_ORDER` |
| Wrong or repeated persona answer | `docs/ANSWER_SOURCE_CONTRACT.md` priority chain | Deduplication gates (`last_counter_reply`, `recent_persona_replies`), persona content |
| English or pinyin mismatch | `docs/ANSWER_SOURCE_CONTRACT.md` translation-path sections | `_repair_asr_junk_text` call sites, persona `_en` fields |
| Wrong engine on following turn | `docs/CONVERSATION_ARCHITECTURE.md` E4 section | `state_update.current_engine`, `_resolveNextEngineId()` in `ui/app.js` |
| Learner fact not remembered | `docs/STATE_CONTRACT.md` learner-memory section | `scripts/learner_memory_capture.py`, `LEARNER_MEMORY_KEYS`, `MANDARINOS_DATA_DIR` |
| New session fails to clear state | `docs/STATE_CONTRACT.md` reset section | Same-tab reset vs. page reload vs. persona switch in `ui/app.js` |
| Microphone/recovery failure | `docs/ASR_PIPELINE.md` | Browser `SpeechRecognition` error handling, TTS/mic coordination timing |
| Typed works but speech fails | `docs/ASR_PIPELINE.md` input-mode section | Chinese recognizer vs. translate-assisted path, browser permissions |
| Production differs from local | Section 13 of this document | `/api/version`, deployed branch/commit, `MANDARINOS_DATA_DIR` config |
| Railway runs the wrong commit | Section 13 of this document | Railway branch-watch configuration, whether the commit was pushed |
| Session review lacks expected data | `docs/ASR_PIPELINE.md` session-capture section | `MANDARINOS_SESSION_CAPTURE` env var, `scripts/session_intelligence.py` |
| Persona switch causes stale behaviour | `docs/STATE_CONTRACT.md` reset section | Which state is/isn't cleared on persona switch vs. full reset |

## 19. Known architectural constraints

**Distributed client/server state** with non-uniform ownership (Section 8); there is no single canonical state object. **Large central
server and client files** (`scripts/ui_server.py`, `ui/app.js`) — a structural constraint of the current baseline, not something this
document proposes to fix. **Priority-order sensitivity** in both the answer-source chain and frame selection. **Partial `state_update`
consumption** — not every field the server emits is read by the client. **Limited server-side pinyin coverage** and **incomplete English
mappings** in some content paths, requiring placeholder-substitution repair rather than full regeneration. **Inline and duplicated content**
— some Chinese content exists only inline in Python, and some content files have superseded sibling variants still present in `content/`.
**Browser-dependent ASR** — speech recognition quality and error reporting differ between the Chinese and auxiliary English recognizers, and
both depend on browser/OS support. **Opt-in session capture** — `MANDARINOS_SESSION_CAPTURE` defaults to disabled, so session-review data is
absent unless explicitly enabled. **Absence of a web app manifest or service worker** — the repository does not define an installable-PWA
configuration or any installed-mode-specific ASR behaviour. **Historical documents that may conflict with R2 behaviour** — older
design/phase documents under `docs/` were not written against, and have not been reconciled with, the current baseline; treat them per the
Section 3 hierarchy.

These are documented constraints, not defects to be silently "fixed" as a side effect of an unrelated change; any change to one should be
deliberate and follow Section 17.

## 20. Documentation map

| Document | Authority | Purpose | Read when |
| -------- | --------- | -------- | ---------- |
| `docs/ARCHITECTURE.md` (this document) | Approved R2 orientation map | System-wide onboarding and navigation | First, before any other document |
| `docs/CONVERSATION_ARCHITECTURE.md` | Approved R2 contract | Turn lifecycle, engine/frame selection, recovery, E4 handoff | Working on conversation control or selector logic |
| `docs/STATE_CONTRACT.md` | Approved R2 contract | Field-by-field state inventory, defaults, merge/reset semantics | Working on any state field or reset behaviour |
| `docs/ANSWER_SOURCE_CONTRACT.md` | Approved R2 contract | `counter_reply`/EN/pinyin production, priority chain, dedup | Working on persona answers or translation |
| `docs/ASR_PIPELINE.md` | Approved R2 contract | Microphone/typed input to normalised, routed text | Working on speech input, recovery, or text repair |
| `AI_CONTEXT.md` | Product-intent / guardrails | Fast repo map, non-negotiable AI-assistant rules, phase status | Before proposing any architecture or content change |
| `.cursor/rules/mandarinos-architecture.mdc` | Standing Cursor rule | Decision-priority order, additive-growth and selector-independence rules | Automatically enforced every session; re-read when proposing a selector/architecture change |
| `.cursor/rules/mandarinos-ui-objects.mdc` | Standing Cursor rule | Canonical `.option-panel` UI structure requirement | Automatically enforced every session; re-read before building any new response UI |
| `docs/session_intelligence_architecture.md`, `docs/session_intelligence_implementation_report.md` | Existing subsystem documentation (not yet reconciled against this hierarchy) | Session-capture design and enablement notes | Working on session capture/review, alongside `ASR_PIPELINE.md` §16 |

**Warning:** older conversation-design documents under `docs/specs/`, `docs/briefings/`, `docs/phases/`, and `docs/design/` have **not yet
been fully classified** against the R2 baseline and must not override the four approved contracts or this document where they conflict —
classifying or rewriting them is out of scope here (see Section 3).

## 21. Onboarding sequence

Recommended reading and setup sequence for a new maintainer. The **nine-document approved R2 governance package** is listed in `docs/DOCUMENT_AUTHORITY_INDEX.md` §4. Expanded navigation, maintenance decision table, and Phase B5D document map: `docs/DOCUMENT_AUTHORITY_INDEX.md` §13; supporting walkthrough: `docs/DEVELOPER_ONBOARDING.md` §Documentation authority and safe starting path.

**Documentation reading order (nine class-A documents):**

| Step | Document | Role |
| ---- | -------- | ---- |
| 1 | `docs/DOCUMENT_AUTHORITY_INDEX.md` | Classify documents before relying on them |
| 2 | `docs/ARCHITECTURE.md` (this document) | System orientation map |
| 3 | `docs/CONVERSATION_ARCHITECTURE.md` | Conversation behavioural contract |
| 4 | `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md`, `docs/ASR_PIPELINE.md` | Detailed contracts for the subsystem you will touch |
| 5 | `docs/TEST_STRATEGY.md` | Evidence requirements |
| 6 | `docs/CHANGE_CHECKLIST.md` | Change workflow |
| 7 | `docs/ARCHITECTURAL_DECISIONS.md` | Architectural decision record |

**After the class-A sequence** (class B and lower — context only when subordinate to the above):

1. Read `AI_CONTEXT.md` for current phase status and guardrails (class B — not class A).
2. Read the applicable Cursor rules (`.cursor/rules/mandarinos-architecture.mdc`, `.cursor/rules/mandarinos-ui-objects.mdc`).
3. Run the application locally: `python scripts/ui_server.py`, then open `http://localhost:8765/ui/index.html`.
4. Run the targeted, non-`live_server` test suite: `python -m pytest tests/ -m "not live_server"`.
5. Inspect a captured request/response — e.g. run one turn locally and read the `/api/run_turn` request/response bodies, or enable `MANDARINOS_DIAG_TOKEN` locally to inspect a diagnostics trace.
6. Only after understanding the contracts, study the high-risk files (Section 16) in depth.

**First safe change** recommendations, in order of preference: a documentation-only correction (e.g. fixing a stale claim in one of the
contracts); a phrase-bank content change with an accompanying test (e.g. adding a recovery phrase to `content/recovery_phrases.json` plus a
regression test); a narrowly isolated persona-data change (e.g. one `discoverable_facts` entry) verified with a targeted test.

Do not make the first change inside the main routing chain (`scripts/ui_server.py` answer-source priority order or frame-selection ordering,
or `ui/app.js` request/response handling) — those require the full Section 17 workflow and carry the highest blast radius.

## 22. Traceability appendix

| Architecture area | Primary implementation | Authoritative contract | Representative tests or verification |
| ------------------ | ------------------------ | ------------------------ | --------------------------------------- |
| Turn routing / HTTP dispatch | `scripts/ui_server.py` (`do_GET`/`do_POST`) | This document §12 | Direct source audit of `Handler.do_GET`/`Handler.do_POST` at the R2 baseline (no dedicated behavioural dispatch test identified); `tests/test_deployment_hygiene.py` is separate evidence for deployment configuration only, not HTTP dispatch |
| Answer-source priority chain | `scripts/ui_server.py` | `docs/ANSWER_SOURCE_CONTRACT.md` | `scripts/test_counter_reply_matrix.py` |
| Frame selection | `scripts/ui_server.py`, `p1_frames.json`/`p2_frames.json` | `docs/CONVERSATION_ARCHITECTURE.md` | `tests/test_golden_regression.py` (live_server, behavioural) |
| E4 initiative-follow / engine handoff | `scripts/ui_server.py` (server), `ui/app.js` `_resolveNextEngineId()` (client) | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md` | `tests/e4_resolve_next_engine_id_cli.js` + `tests/_load_app_js_helper.js` (executes real `ui/app.js` helper code) |
| State transport (`conversation_state`/`state_update`) | `scripts/ui_server.py`, `ui/app.js` | `docs/STATE_CONTRACT.md` | See `STATE_CONTRACT.md`'s own traceability appendix |
| ASR input and client-intercepted recovery | `ui/app.js` | `docs/ASR_PIPELINE.md` | `tests/verify_asr_filler.js` (mirrored/static — does not execute the real `ui/app.js` filler functions); `tests/verify_spoken_recovery_exact_match.js` (hybrid — mirrored matcher plus static wiring, per `ASR_PIPELINE.md` §12) |
| Late ASR-junk repair | `scripts/ui_server.py` (`_repair_asr_junk_text`) | `docs/ASR_PIPELINE.md` §11 | See the authoritative contract's traceability appendix |
| Learner memory | `scripts/learner_memory.py`, `scripts/learner_memory_capture.py` | `docs/STATE_CONTRACT.md` | See the authoritative contract's traceability appendix |
| Progress snapshots | `scripts/progress_store.py` | Not separately contracted; documented in this map §6.4 | `tests/test_progress_store.py` (behavioural, exercises the real module) |
| Session capture (opt-in) | `scripts/session_intelligence.py` | `docs/ASR_PIPELINE.md` §16 (capture semantics), `docs/session_intelligence_architecture.md` | `docs/session_intelligence_implementation_report.md` |
| Deployment / version verification | `railway.toml`, `Procfile`, `nixpacks.toml`, `scripts/ui_server.py` (`/api/version`) | This document §13 | Manual `/api/version` check per Section 17 step 13 |
| Generated runtime artifacts | `tools/build_runtime_artifacts.py` | `AI_CONTEXT.md` §1.1, this document §14 | Golden/build tests referenced in `AI_CONTEXT.md` §7 |
| Challenge Mode | `ui/app.js`, `ui/styles.css` | `docs/ASR_PIPELINE.md` (visibility/reveal layer) | `tests/test_challenge_recovery.py` (mostly static, per `ASR_PIPELINE.md`) |

Baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Baseline tag: `architecture-baseline-2026-07-12-r2`
Documentation branch: `docs/architecture-v1`
Document status: `Approved v1 — R2 baseline`
Last verified date: `2026-07-13`
