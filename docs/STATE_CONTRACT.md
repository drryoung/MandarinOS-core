# MandarinOS State Contract

---

## 1. Purpose and scope

**What counts as state.** In MandarinOS, "state" is any value that persists beyond the single line of code that created it and influences a later decision: a browser global (`window._*`), the `conversation_state` object round-tripped between client and server, the server's per-request local variables that are read from or written back into that object, the persistent learner-memory file, session/progress snapshots, and diagnostic capture structures. It excludes static content (persona JSON, frame definitions, recovery-phrase content) — those are data, not state, because they do not change as a result of the conversation.

**Why this contract exists.** MandarinOS conversation behaviour depends on state distributed across three tiers that are not centrally coordinated by any single schema or class: the browser (`ui/app.js`, dozens of `window._*` globals), the server request lifecycle (`scripts/ui_server.py`, a single very large `/api/run_turn` handler with hundreds of local variables), and on-disk persistence (`scripts/learner_memory.py`, session/progress stores). A change to a default, a merge rule, or a reset path in one tier can silently break another tier weeks later. This document exists so a developer can trace, for any given field, its producer, consumer, default, and reset behaviour without re-deriving it from scratch by reading the entire codebase.

**What this document covers.** The complete inventory of `conversation_state` fields sent by the client, the complete inventory of `state_update` fields returned by the server, the persistent learner-memory schema and its clear/merge semantics, session initialization and reset operations, and the invariants (enforced and intended) that govern all of the above at the frozen baseline.

**What remains in other documents:**
- **`CONVERSATION_ARCHITECTURE.md`** — how routing decisions are made (answer-source priority chain, E4 semantics, recovery-path selection, topic-engine/bridge selection logic). This document assumes that architecture and documents only the state it reads and writes.
- **`ANSWER_SOURCE_CONTRACT.md`** (not yet created) — field-by-field construction of `(zh, en)` tuples within each answer-source function.
- **`ASR_PIPELINE.md`** (not yet created) — browser speech-recognition timing, confidence scoring, and transcript assembly, upstream of the state fields this document describes.

**This document describes the frozen baseline, not an idealised future schema.** Every inconsistency, dead field, and unenforced contract described below is real, evidenced by code, and intentionally not corrected here. Recommendations for closing gaps belong in a future revision after review, not in this document.

**Baseline:** commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`, tag `architecture-baseline-2026-07-12-r2`.

**Historical note.** The original baseline, `architecture-baseline-2026-07-12`
(commit `53584cee9e8c892ff77f12741d1fc89d9d09c7e7`), remains an immutable historical
baseline and is not moved or deleted. This document (previously revised against that
baseline) identified a `current_engine` client-consumption gap: the primary Pattern-A
response handler (`_runTurnInner()`) never read `data.state_update.current_engine`, so an
E4 handoff had no effect on the ordinary conversation path (originally Section 16.2,
SIC-6). Commit `3be0315b2c9f7316b03ac2183a887f602ae9a297` closes that gap by adding
`_resolveNextEngineId()`, called by `_runTurnInner()` after current-frame bookkeeping, with
executable regression coverage (`tests/verify_e4_client_handoff.js`,
`tests/test_e4_client_handoff_regression.py`). This revision (R2) updates every section
below that described the gap as open. The remaining six unconsumed `state_update` fields
documented at the original baseline are unchanged and still open.

---

## 2. State-domain overview

| # | Domain | Owner | Storage | Lifetime | Source of truth | Crosses API? |
|---|--------|-------|---------|----------|------------------|---------------|
| 1 | Turn-local server variables | Server | Python locals inside the `/api/run_turn` handler (e.g. `_counter_result`, `_e4_engine_handoff`) | Single request only | Server (computed fresh each call) | No — never leave the handler except through fields explicitly copied into `response` |
| 2 | Client conversation state | Client (transport), Server (interpretation) | `window._*` globals, assembled into `conversation_state` | One browser session (rebuilt from globals each turn; lost on reload) | Mixed — see Section 3 | Yes — sent every `/api/run_turn` call |
| 3 | Server-generated state updates | Server | `response["state_update"]` | Conditionally present (written only if at least one field is set that turn); the production client applies only the specific fields it has an explicit merge case for | Server | Conditional — present only when the server writes at least one field; of the 20 fields it may contain, 14 are consumed cross-turn as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297` (Section 6) |
| 4 | Working memory | Client (transport), Server (read/derive) | `cs["recent_persona_replies"]`, `last_counter_reply`, `last_partner_frame_text` | One session; capped history | Client-held, server-interpreted | Yes |
| 5 | Persistent learner memory | Server | `data/learner_memory.json` (path via `MANDARINOS_DATA_DIR`), keyed by `learner_id` | Survives sessions and browser reloads unconditionally; survives server restarts only if `MANDARINOS_DATA_DIR` resolves to a storage path that itself persists across restarts (e.g. a mounted volume on Railway) | Server exclusively | No — client never sends `learner_memory` as input; server may return it for display |
| 6 | Persona data — **related immutable input domain, not conversation state** | Content (static) | `personas/<id>.json`, loaded and cached in `scripts/ui_server.py` | Immutable for the process lifetime (cached) | Content file | No — never sent by client; server reads by `persona_id`. Listed here only for traceability; per Section 1 this is data, not state. Active persona *selection* and reveal-tracking (Section 9) are genuine state and are covered separately. |
| 7 | Session/progress state | Client (`_tracker`, `localStorage`), Server (`data/progress/<learner_id>.json`) | Browser `localStorage` + server file | Session-scoped counters reset each session; progress snapshots persist across sessions | Split — see Section 14 | Partially — `/api/save_progress`, `/api/end_session`, not `conversation_state` |
| 8 | Diagnostics state | Server (`_diag_cap`), Client (`AsrDiag`) | In-memory per request; not persisted | Single request/response cycle | Server + client independently | Yes — via `diag` response field and `diag_trace_id` |
| 9 | UI-only state | Client | `window._*` (rendering, DOM, timers) | Session or shorter | Client exclusively | No |

**Principal state flows (frozen baseline):**

```
 browser (window._*)
     │  assembled into conversation_state
     ▼
 POST /api/run_turn  ───────────────►  server coordinator (ui_server.py)
     │                                        │
     │                                        ├─► learner-memory persistence
     │                                        │     (load on read, save/apply_updates on capture)
     │                                        │
     │                                        ├─► session capture / progress
     │                                        │     (separate: /api/save_progress, /api/end_session)
     │                                        │
     │                                        └─► response { frame_text, counter_reply,
     │                                              state_update, learner_memory?, diag }
     ▼
client applies the recognised subset of
state_update, top-level telemetry fields,
and (if present) learner_memory display
fields to window._* — becomes next
conversation_state. Unrecognised or
unimplemented state_update fields have
no cross-turn effect (Section 6).
```

Learner-memory persistence and session capture are **not** part of the `conversation_state` round trip; they are separate subsystems reached through separate endpoints and only surfaced into the `/api/run_turn` response as read-only display data (`response["learner_memory"]`).

**Restart persistence is configuration-dependent, not automatic.** Learner-memory, progress, and session-capture files survive a server restart only if their configured storage path is itself persistent across restarts. On Railway (and any similar ephemeral-filesystem host), this depends on `MANDARINOS_DATA_DIR` pointing at a mounted persistent volume; if it instead resolves to the container's ephemeral local disk, a restart or redeploy would lose these files despite the code itself having no bug. This document does not verify the current Railway volume configuration — it states only that the code's persistence guarantee is conditional on deployment configuration, not unconditional.

---

## 3. State ownership model

**Authoritative owner** — may establish or change the semantic meaning of a value. Example: the server is the authoritative owner of `current_engine` after the first turn (via E4 and other handoffs); the server is the sole authoritative owner of persistent learner memory.

**Transport owner** — holds and round-trips a value on behalf of another party but must not reinterpret it. The client is the transport owner of most of `conversation_state`: it stores counters like `exchange_count`, `same_engine_chain_count`, and `recent_frame_ids` in `window._*` globals and sends them back verbatim each turn, but the server — not the client — decides what those counters mean and how they gate behaviour.

**Derived state** — recomputed from authoritative values rather than stored independently. Example: `_12c_loop_capped`, `_12c_overload`, `_12c_closing` (Section 10, `scripts/ui_server.py` lines 9168–9170) are recomputed every request from `loop_count_in_current_engine`, `recent_confusion_count`, and `exchange_count`; they are never stored or sent anywhere.

**UI state** — controls presentation but carries no semantic conversation meaning. Example: `window._sentenceHint`, `window._currentHintAffordance`, `hint_cascade_state`, DOM element visibility. These never appear in `conversation_state` or `state_update`.

**Persistent state** — survives a normal session boundary. Only persistent learner memory (`data/learner_memory.json`), progress snapshots (`data/progress/<learner_id>.json`), and `localStorage["manos_progress_history"]` qualify. `conversation_state` itself is **not** persistent — it is rebuilt from `window._*` globals on each turn and lost entirely on a browser reload.

**Ephemeral state** — valid only during one request or one browser tab session. Turn-local server variables are request-ephemeral. Most `window._*` counters are session-ephemeral: they exist until `_resetCurrentSessionState()` runs or the tab is closed/reloaded.

**The mixed-ownership pattern.** The client stores and transports the majority of `conversation_state` (counters, history lists, mode flags) but does not have final authority over what those values *mean*. The server reads the client's copy, may derive a corrected or advanced value, and, for a subset of fields, writes that correction into `state_update`. `state_update` is conditionally present — it exists only when at least one write site fired that turn — and even when present, the production client applies only the fields it has an explicit merge case for in `ui/app.js`. A field the server writes but the client has no merge case for (or applies only in a different call path than the one that ran that turn) has no effect on the following request; it is not "contractually" applied, it is applied only to the extent the client code actually implements. Section 6 lists exactly which `state_update` fields are consumed and which are not. The client must not independently *recompute* a value the server is authoritative for (notably `current_engine` once E4 has fired). As of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`, `current_engine` is consumed end-to-end on both client call paths (`_runTurnInner()` via `_resolveNextEngineId()`, and `runMirrorTurn()`); this was not the case at the original baseline, where `_runTurnInner()` had no read site for it at all (Section 6, Section 16.2). Six other `state_update` fields remain unconsumed by either path — see Section 6.

**Legitimate client-side initialisation.** On the very first turn of a session, several fields have no server-provided predecessor because no server response yet exists:
- `current_engine`: client falls back to `window._currentEngineId ?? <dropdown-selected engine> ?? "identity"`.
- `engines_visited`: initialised to `["identity"]` (not empty) both at session-reset time and as the JS array-guard fallback.
- `recent_frame_ids`, `recent_persona_replies`, `seeded_bridge_engines`, `medium_probe_fired_engines`, `recently_seen_disc_topics`: all initialise to `[]`.

This first-turn fallback is a legitimate, evidenced exception to "server is authoritative for `current_engine`" — it only applies before any server response has been received.

---

## 4. API state lifecycle

One `/api/run_turn` turn proceeds as follows:

1. **Client reads local state.** All relevant values are read from `window._*` globals at the moment `_runTurnInner()` runs.
2. **Client assembles `conversation_state`.** Built as a fresh object literal (`ui/app.js:6628`); it is not a persisted structure that gets mutated in place — the entire object is rebuilt every call. The shape sent varies by call site (see Section 5).
3. **Request is sent** to `POST /api/run_turn` as `{ env, turn_uid, next_question, conversation_state, persona_id?, diag_trace_id? }`.
4. **Server validates/defaults fields.** `cs = payload.get("conversation_state") or {}` (direction/probe/mirror stub paths) or `cs = payload["conversation_state"]` guarded by `isinstance(payload.get("conversation_state"), dict)` (main selector path, `scripts/ui_server.py:9138–9139`). If `conversation_state` is missing, not a dict, or `next_question` is falsy, `cs` remains `None` and the entire selector block is skipped — the server falls back to `frame_id`/`engine_id` supplied directly on the request payload.
5. **Server derives turn-local values.** Dozens of local variables (`_counter_result`, `_e4_engine_handoff`, `_12c_loop_capped`, etc.) are computed from `cs` and never stored as-is.
6. **Server selects answer and frame.** The answer-source priority chain and frame selector run (documented in `CONVERSATION_ARCHITECTURE.md` Sections 8–9); this document only tracks the state they read and write.
7. **Server constructs `state_update`.** Written incrementally at scattered points in the handler (Section 6), not assembled in one place.
8. **Response is returned** with `frame_text`/`counter_reply`/`state_update`/top-level telemetry fields.
9. **Client applies response fields** — merges the *recognised subset* of `data.state_update` into the corresponding `window._*` globals. The main turn-advancing path (`_runTurnInner`, response handler at `ui/app.js:6882–6919`) has explicit merge cases for 13 fields (Section 6), plus — as the very last statement of the function, after all current-frame bookkeeping, rendering, and diagnostics — a 14th: `window._currentEngineId = _resolveNextEngineId(engineId, data.state_update)`, which reads `data.state_update.current_engine` when valid and otherwise falls back to `engineId` (`data.engine_id`). This is new as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`; at the original baseline, `_runTurnInner()` had no read site for `data.state_update.current_engine` at all. The client separately applies certain top-level response fields (`data.engine_id`, `turn_type`, `same_engine_chain_count`, `arc_state.*`, etc., `ui/app.js:6797–6833, 6869–6870`).
10. **Client appends or replaces local state.** `recent_frame_ids` is appended and capped at 50 (`ui/app.js:6921–6923`); `recent_persona_replies` is *replaced* wholesale from `state_update` (already capped server-side at 3); most counters are replaced, not appended.
11. **Updated state is sent on the next request** — the cycle repeats from step 1.

**Field mutation classes across this lifecycle:**

| Class | Meaning | Examples |
|---|---|---|
| Copied unchanged | Client sends it; server reads it; server does not return it, so client keeps its own copy for next turn | `exchange_count` (server reads, never returns a corrected value — client's own increment logic stands) |
| Appended | Client-side growth with a cap | `recent_frame_ids` (cap 50, client-side push+slice) |
| Trimmed/replaced wholesale | Server returns the full new list; client replaces its copy | `recent_persona_replies` (server computes `(_recent + [reply])[-3:]`, client replaces) |
| Incremented | A counter goes up by a fixed amount, usually 1 | `location_retry_count` (`_loc_retry + 1`, server-side, in `state_update`) |
| Recomputed | Derived fresh from other state each turn, never stored | `_12c_loop_capped`, `_12c_overload`, `_12c_closing` |
| Conditionally overridden | Only present in `state_update` under specific branches | `pending_dest_candidate` (only for the travel-destination ASR-clarify frame) |

**E4 as the canonical example of a deferred state update — now consumed end-to-end on both client call paths:**

1. Server computes `_e4_engine_handoff` at `scripts/ui_server.py:10296–10313`, *before* frame selection runs.
2. The response's `frame_text`/`frame_id` are selected using the *incoming* `current_engine` (frame selection happens after step 1 but does not consult `_e4_engine_handoff`).
3. Server writes `response["state_update"]["current_engine"] = _e4_engine_handoff` at line **11835**, *after* frame selection and most of payload assembly. This part is enforced by fixed line ordering and is not in question.
4. **Client-side consumption is call-path-dependent; as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297` both paths apply it.** `data.state_update.current_engine` is read in `runMirrorTurn()` (`ui/app.js:6246–6249`), the handler for the mirror-question stub path (Pattern B), exactly as before. The main turn-advancing response handler used for ordinary "Next" turns (`_runTurnInner`'s response handling, Pattern A) now also applies it: as the last statement of the function, `window._currentEngineId = _resolveNextEngineId(engineId, data.state_update)` returns `data.state_update.current_engine` when it is a non-empty string, and otherwise `engineId` (`data.engine_id`) unchanged. Prior to this commit, `_runTurnInner()` set `window._currentEngineId` only from the top-level `data.engine_id` and contained no read of `data.state_update.current_engine` at all — there was, and still is, no generic "apply every `state_update` key" loop anywhere in `ui/app.js`; the fix adds one targeted read site, not a generic merge.
5. Consequently: when a learner's direct question and E4 handoff are produced during an ordinary answer-submission turn (Pattern A, the common case), the server's `state_update.current_engine` write is now applied by the client's main path, and the *next* request's `conversation_state.current_engine` carries the redirected engine rather than the pre-handoff one. This is evidenced by an executable two-turn integration test that drives the real HTTP path and computes the redirected engine using the real, extracted `_resolveNextEngineId()` helper (`tests/test_e4_client_handoff_regression.py`), not merely a static source-string assertion (`test_e4_topic_handoff.py` still performs only the latter, for the *server-side* write).

The "exactly one transitional response whose accompanying frame still belongs to the old engine" framing in `CONVERSATION_ARCHITECTURE.md` Section 8 describes the *server-side* mechanism correctly; the client-side pickup on the following turn is now confirmed to occur for Pattern-A turns as well, closing the gap this document previously surfaced as SIC-6 (Section 16.2 records this as a resolved historical gap for traceability).

---

## 5. `conversation_state` contract

The client does not send one fixed shape. There are **four distinct payload patterns** depending on which client function assembles the request:

| Pattern | Call site | `conversation_state` shape |
|---|---|---|
| **A — Full selector state** | `_runTurnInner(true, opts)` → `POST /api/run_turn` with `next_question: true` (`ui/app.js:6628–6717`) | **45 fields total: 35 always-present, up to 10 conditional** — the only pattern the server's main selector block fully consumes |
| **B — Minimal direction/mirror/discovery stub** | `runDirectionTurn`, `runMirrorTurn`, `submitDiscoveryQuestion`, `_showPostCloseMirrorOptions` (`ui/app.js:6137, 6208, 8459, 8971`) | up to 4 fields: `current_engine`, `recent_frame_ids` (always sent by this pattern), `learner_id` and `persona_id` (each conditional — omitted if falsy) |
| **C — Probe stub** | `runProbeTurn` (`ui/app.js:6291`) | up to 5 fields: pattern B's up-to-4, plus `probe_depth` (always sent by this pattern, unconditionally) |
| **D — No conversation state** | `_runTurnInner(false, ...)` — initial dropdown-driven frame load | none — sends `frame_id`/`engine_id` directly on the payload root |

Only **Pattern A** is the authoritative full contract. The server's main selector block (`scripts/ui_server.py:9137–9139`) only activates when `next_question: true` **and** `conversation_state` is a dict; Patterns B/C/D route through the direction/probe early-return branches or the frame-dropdown fallback and never touch most of the fields below. Any future change to a field's default **must** account for the fact that patterns B–D will not supply it.

**Verified count breakdown (this revision corrects the previously reported 34/11 split).** Reading the Pattern A object-literal construction (`ui/app.js:6628–6717`) line by line: 34 fields are assigned unconditionally inside the base object literal (`session_id` through `learner_food_note` in the table below), and a 35th field, `probe_depth` (`ui/app.js:6683`, `conversation_state.probe_depth = window._probeDepth || 0;`), is also assigned **unconditionally** — it sits after the conditional `learner_id`/`persona_id`/`partner_id`/`revealed_voice_lines`/`revealed_partner_facts` block in the source but carries no `if` guard of its own, so it is always present, not conditional. This gives **35 always-present fields**. The remaining **10 fields** are genuinely conditional, each behind its own `if`: `learner_id`, `persona_id`, `partner_id`, `revealed_voice_lines`, `revealed_partner_facts` (all omitted if their backing global is falsy), and `prefer_bridge`, `force_bridge`, `learner_skip_confusion`, `last_turn_was_answer`, `last_answer` (all omitted unless the corresponding call-site `opts` flag is set). 35 + 10 = 45, matching the total field count; the previously reported 34/11 split miscategorised `probe_depth` as conditional.

### 5.1 Full field inventory (Pattern A — 45 fields: 35 always-present, 10 conditional)

| Field | Type | Default (client) | Client source | Server consumer | Mutation rule | Lifetime | Reset behaviour | Representative tests |
|---|---|---|---|---|---|---|---|---|
| `session_id` | string | `"session_" + Date.now()` | `window._sessionId` | Randomness seed for probabilistic gates (e.g. bridge/closing rolls) | Replace at session reset | Session | New value on `_resetCurrentSessionState()` | `test_session_start_reset.py` |
| `current_engine` | string | `"identity"` (first turn only, via fallback chain) | `window._currentEngineId` | Active topic engine for routing/frame selection | Client-initialised on turn 1 only; thereafter, on every Pattern-A response, `_runTurnInner()` first sets `window._currentEngineId = engineId` (`data.engine_id`, for current-frame bookkeeping) and then, as its last statement, `window._currentEngineId = _resolveNextEngineId(engineId, data.state_update)` — which returns `data.state_update.current_engine` when valid, else `engineId` unchanged (`ui/app.js`, Section 4). `runMirrorTurn`'s separate Pattern-B response handling performs its own equivalent merge from `data.engine_id` and then `data.state_update.current_engine` (`ui/app.js:6240–6249`), unmodified by this fix. Both paths now consume `state_update.current_engine` as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297` (Section 4, Section 6) | Session | Reset to fallback default at session reset | `test_e4_topic_handoff.py` (server-side write); `tests/verify_e4_client_handoff.js`, `tests/test_e4_client_handoff_regression.py` (client-side application, Pattern A; see Section 16.1 SINV-4) |
| `last_partner_frame_id` | string | dropdown-selected frame or `null` | `window._lastPartnerFrameId` | Coherence guard, direction stub engine fallback | Replace | Session | `null` on reset | — |
| `recent_frame_ids` | array\<string\> | `[]` | `window._recentFrameIds` | Anti-repeat frame selection, interest scoring, dependency guards | Append + cap 50 (client-side) | Session | `[]` on reset | `test_conversation_first_wave.py` |
| `exchange_count` | int | `0` | `window._exchangeCount` | Session-length arc gating, closing-move threshold, blended reciprocity | Increment (client) | Session | `0` on reset | — |
| `curiosity_depth` | int | `0` | `window._curiosityDepth` | Curiosity-loop depth gating | Increment (client) | Session | `0` on reset | — |
| `ask_chain_count` | int | `0` | `window._askChainCount` | Interview-drift probe gating | Increment (client) | Session | `0` on reset | — |
| `last_partner_turn_type` | string | `"question"` | `window._lastPartnerTurnType` | Loop detection | Replace | Session | `"question"` on reset | — |
| `same_engine_chain_count` | int | `0` | `window._sameEngineChainCount` | Engine loop cap, interest decay, fact-reveal depth gating | Replace (server-computed value echoed back at top level, not `state_update`) | Session | `0` on reset | — |
| `same_slot_chain_count` | int | `0` | `window._sameSlotChainCount` | Slot loop cap | Replace | Session | `0` on reset | — |
| `last_focus_slot` | string | `""` | `window._lastFocusSlot` | Slot-chain tracking | Replace | Session | `""` on reset | — |
| `seeded_bridge_engines` | array\<string\> | `[]` | `window._seededBridgeEngines` | Response-seeded bridge queue (Phase 13B) | Replace (server echoes at top level) | Session | `[]` on reset | — |
| `recent_reactions` | array\<string\> | `[]` (no explicit init; `undefined` until first server value) | `window._recentReactions` | Reaction-line dedup | Replace | Session, but see reset note | `_resetCurrentSessionState()` contains no assignment to `window._recentReactions` (verified by absence, not by an explicit skip). A browser reload reinitialises it (script-load default). Starting a **new session in the same tab** (via the "Start" button, without a reload) does **not** clear it — it retains whatever value the previous session last set, and that stale value is sent on the new session's first Pattern-A request. It is not implicitly cleared merely because a new session begins. | — |
| `medium_probe_fired_engines` | array\<string\> | `[]` | `window._mediumProbeFiredEngines` | At-most-one-medium-probe-per-engine cap | Replace | Session | `[]` on reset | — |
| `pending_listening_move` | bool | `false` | `window._pendingListeningMove` | Listening-move gate | Replace | Session | `false` on reset | — |
| `listening_wait_turns` | int | `0` | `window._listeningWaitTurns` | Listening-move gate | Increment | Session | `0` on reset | — |
| `last_interest_level` | string | `"low"` | `window._lastInterestLevel` | Weak-reply resilience, interest decay | Replace | Session | `"low"` on reset | — |
| `last_user_text` | string | `""` | `window._lastUserText` | Interest/repetition heuristics | Replace | Session | `""` on reset | — |
| `loop_count_in_current_engine` | int | `0` | `window._loopCountInEngine` | LOOP-frame soft-cap arc correction (Section 10) | Increment | Session | `0` on reset | — |
| `engines_visited` | array\<string\> | `["identity"]` | `window._enginesVisited` | Bridge target selection, arc completion | Append | Session | `["identity"]` on reset (not `[]`) | — |
| `recent_confusion_count` | int | `0` | `window._recentConfusionCount` | Overload threshold (`_12c_overload`) | Increment (client); reset by server via `state_update` on repair success | Session | `0` on reset | `test_challenge_recovery.py` |
| `last_counter_reply` | string | `""` (undefined until first `state_update`) | `window._lastCounterReply` | Reply-deduplication guard | Replace (server echoes via `state_update`) | Session, but see reset note | `_resetCurrentSessionState()` contains no assignment to `window._lastCounterReply`. A browser reload reinitialises it to `undefined`. A **new session started in the same tab** retains whatever value the prior session last wrote via `state_update` — it is not implicitly cleared merely because the new session begins, so the first dedup check of a fresh session can be seeded by the previous session's last counter-reply. | `test_stale_answer_loop_regression.py` |
| `recent_persona_replies` | array\<string\> | `[]` | `window._recentPersonaReplies` | Working-memory (E3) source, dedup pool, mirror confusion context | Replace with server-capped `[-3:]` list | Session | `[]` on reset | `test_stale_answer_loop_regression.py`, `test_e4_topic_handoff.py` |
| `repair_attempt_count` | int | `0` | `window._repairAttemptCount` | Repair-escalation ladder input (`max()` with server-side counters) | Increment (client); reset via `state_update` on confirmed re-ask | Session | `0` on reset | — |
| `efc_entity` | object\|null | `null` | `window._efcEntity` | Entity follow-up chain (family EFC) state | Replace | Session | `null` on reset | — |
| `efc_depth` | int | `0` | `window._efcDepth` | EFC depth cap | Increment via `state_update` | Session | `0` on reset | — |
| `discovery_shown_last_turn` | bool | `false` | `window._discoveryShownLastTurn` | Rate-limits back-to-back discovery panels (read only — not consulted in the trigger guard, a documented gap) | Replace | Session | `false` on reset | — |
| `consecutive_app_questions` | int | `0` | `window._consecutiveAppQuestions` | Proactive-discovery trigger streak | Replace via `state_update` | Session | `0` on reset | — |
| `last_persona_reveal` | bool | `false` | `window._lastPersonaReveal` | Proactive-discovery trigger | Replace via `state_update` | Session | `false` on reset | — |
| `recently_seen_disc_topics` | array\<string\> | `[]` | `window._recentlySeenDiscTopics` | Discovery-topic dedup | Replace via `state_update` | Session | `[]` on reset | — |
| `last_partner_frame_text` | string | `""` | `window._lastPartnerFrameText` | Recovery rephrase source, confusion clarification | Replace via `state_update` | Session | `""` on reset | — |
| `last_place_subject` | string | `""` | `window._lastPlaceSubject` | Deictic place resolution, slot-fill fallback | Replace via `state_update` (merge: keep previous if no new value detected) | Session | `""` on reset | `test_conversation_first_wave.py::test_city_routing_prefers_question_focus` |
| `learner_stated_location` | string | `""` | `window._learnerStatedLocation` | Open-world residence persistence (in-session, distinct from `learner_memory["lives_in"]`) | Replace via `state_update` (merge: keep previous if none extracted) | Session | `""` on reset | — |
| `learner_food_note` | string | `""` | `window._learnerFoodNote` | Open-world food-fact persistence (in-session) | Replace via `state_update` (or kept) | Session | `""` on reset | — |
| `learner_id` *(conditional)* | string | omitted if falsy | `window._learnerId` | Learner-memory load/save key | Replace | Cross-session (backing global persists in `localStorage`) | Not reset by `_resetCurrentSessionState()` | `test_session_start_reset.py` |
| `persona_id` *(conditional)* | string | omitted if both `_partnerId`/`_personaId` falsy | `window._partnerId \|\| window._personaId` | Persona resolution (`_resolve_persona`) | Replace | Session (persists across resets unless explicitly changed) | Not reset by `_resetCurrentSessionState()` | — |
| `partner_id` *(conditional)* | string | omitted if `window._partnerId` null | `window._partnerId` | Phase 11C partner-name/fact enrichment | Replace | Session | Not reset | — |
| `revealed_voice_lines` *(conditional)* | object | `{}` | `window._revealedVoiceLines` | Per-engine voice-line reveal tracking | Replace | Session | `{}` on reset, and also cleared on persona switch | — |
| `revealed_partner_facts` *(conditional)* | object | `{}` | `window._revealedPartnerFacts` | Per-engine fact-reveal tracking | Replace | Session | `{}` on reset, and also cleared on persona switch | — |
| `probe_depth` | int | `0` | `window._probeDepth` | Probe-ladder depth | Increment | Session | `0` on reset | — |
| `prefer_bridge` *(conditional)* | bool | omitted unless `opts.prefer_bridge === true` | call-site option | Bridge-first selector bias (recovery/change-topic) | One-shot, not stored | Request | N/A | — |
| `force_bridge` *(conditional)* | bool | omitted unless `opts.force_bridge === true` | call-site option (no caller currently sets this in `app.js`) | Hard bridge override | One-shot | Request | N/A | — |
| `learner_skip_confusion` *(conditional)* | bool | omitted unless `opts.learner_skip_confusion === true` | call-site option | Suppresses bridge intent for "weak" skip-confusion turns | One-shot | Request | N/A | `test_challenge_recovery.py` |
| `last_turn_was_answer` *(conditional)* | bool | omitted unless `opts.last_turn_was_answer === true` | call-site option | Branches selector vs. free-text answer path | One-shot | Request | N/A | — |
| `last_answer` *(conditional)* | object | omitted unless `last_turn_was_answer` and `window._lastAnswer` has content | `window._lastAnswer` (cleared immediately after send — "send once only") | Answer capture, learner-memory capture, slot routing | Sent once, then cleared client-side | Request | `null` after send and on reset | `test_conversation_first_wave.py` |

**`last_answer` object shape** varies by call site but always contains `frame_id` plus one or more of: `selected_option_hanzi`, `selected_option_meaning`, `submitted_text`.

### 5.2 Field groups (cross-reference into Section 5.1)

- **Engine and ladder position:** `current_engine`, `loop_count_in_current_engine`, `engines_visited`, `seeded_bridge_engines`, `recent_frame_ids`, `exchange_count`, `same_engine_chain_count`.
- **Current/previous turn context:** `last_answer`, `last_partner_frame_id`, `last_partner_frame_text`, `last_counter_reply`, `last_place_subject`, `last_user_text`, `last_partner_turn_type`.
- **Working memory and answer history:** `recent_persona_replies`, `recent_frame_ids`, `recent_confusion_count`; mirror-topic context (`last_mirror_topic`, `last_mirror_engine`, `mirror_confusion_count`) is read by the server but **not present in this list** — see Section 11 for why.
- **Mode and interaction state:** `prefer_bridge`, `force_bridge`, `learner_skip_confusion`, `probe_depth`, `pending_listening_move`, `listening_wait_turns`. Challenge mode (`window._challengeMode`) is **not** in this list at all (Section 9/11).
- **Progress and scorecard state:** none of the 45 fields are progress/scorecard fields. `_tracker` counters travel only through `/api/end_session`, never through `conversation_state` (Section 14).

---

## 6. `state_update` contract

The server writes **20 distinct fields** into `response["state_update"]`, scattered across the `/api/run_turn` handler rather than assembled in one place. `state_update` itself is initialised lazily (`response["state_update"] = response.get("state_update") or {}`) at the first write site, so **its presence in the response is conditional** — it is not returned on every response, only on responses where at least one write site fired that turn (e.g. a turn with no `counter_reply` and no E4 handoff and no discovery/location/EFC activity would return no `state_update` key at all).

**The server writing a field does not mean the client applies it.** The production client (`ui/app.js`) has an explicit merge case for a strict subset of these 20 fields, and only within specific response-handling code paths. A field present in `state_update` with no matching client merge case in the path that handled that response is transported for no purpose — it has no effect on any later request. The table below states, per field, whether and where the client actually consumes it; do not assume "server writes it" implies "next turn reflects it."

| Field | Set at (approx. line) | Condition | Merge semantics | Client consumption |
|---|---|---|---|---|
| `current_engine` | 11835 (E4); 9067 (direction-stub) | E4: `_e4_engine_handoff` truthy. Direction: resolved `engine_id` not `"unknown"`/`""` | Replace | **Consumed on both call paths as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`.** Inside `runMirrorTurn` (Pattern B, `ui/app.js:6246–6249`), unchanged. Inside `_runTurnInner` (Pattern A, used for ordinary "Next" turns), as the last statement of the function: `window._currentEngineId = _resolveNextEngineId(engineId, data.state_update)`. Prior to this commit, the Pattern-A handler set `window._currentEngineId` only from top-level `data.engine_id` and never read `data.state_update.current_engine` — see Section 4 and Section 16.2 (SIC-6, now recorded as a resolved historical gap). |
| `last_counter_reply` | 11824 | `_counter_reply` truthy | Replace | **Consumed** — `ui/app.js:6883–6884` (Pattern A) |
| `recent_persona_replies` | 11827 | `_counter_reply` truthy | Replace with `(_recent + [reply])[-3:]` (append-then-truncate, computed server-side) | **Consumed** — `ui/app.js:6885–6886` |
| `last_partner_frame_text` | 12091 | Always, in post-trigger assembly block | Replace with stripped `frame_text` | **Consumed** — `ui/app.js:6918–6919` (recovery rephrase source) |
| `last_place_subject` | 12153 | When a place is detected this turn | Replace if new subject found, else keep previous value (merge-like conditional) | **Consumed** — `ui/app.js:6889–6890` |
| `learner_stated_location` | 12135 | Always in post-trigger block | Replace with new extraction, or keep previous | **Consumed** — `ui/app.js:6891–6892` |
| `learner_food_note` | 12147 | Responsive food answer, or keep previous | Replace or keep | **Consumed** — `ui/app.js:6893–6894` |
| `consecutive_app_questions` | 12156 | Only if key not already set earlier in the same response | Replace: `0` if user-led this turn, else incremented value | **Consumed** — `ui/app.js:6912–6913` |
| `discovery_shown_last_turn` | 12089 | Always in post-trigger block | Replace with `bool(user_led)` | **Consumed** — `ui/app.js:6910–6911` |
| `last_persona_reveal` | 12088 | Always when the persona-reveal block runs | Replace | **Consumed** — `ui/app.js:6914–6915` |
| `recently_seen_disc_topics` | 11941, 11981, 12020, 12069 | Discovery path shown this turn | Replace with updated topic pool | **Consumed** — `ui/app.js:6916–6917` |
| `pending_dest_candidate` | 11564 (set), 11568 (clear) | ASR near-match destination clarify frame sets it; otherwise cleared to `None` | Replace (string or explicit `None`) | **Not consumed** — no merge case anywhere in `ui/app.js`; the client never reads or resends this field (documented gap, Section 11, Section 16.2 SIC-2) |
| `location_retry_count` | 11659 (increment), 11612 (reset), 12174 (reset on valid echo) | Noisy-location clarify always increments; participation-escape/valid-echo resets to `0` | Replace (increment or reset) | **Not consumed** — no merge case in `ui/app.js` (Section 16.2 SIC-2) |
| `location_clarify_hint` | 11637/11646 (`"active"`), 11657 (`""`), 12164 (`""` on confirmed re-ask) | Escalation-level dependent | Replace (`"active"` or `""` — not boolean) | **Not consumed** — no merge case in `ui/app.js` (Section 16.2 SIC-2) |
| `efc_entity` | 11751, 11766 | `{ENTITY}` slot filled or carried forward | Replace (dict) | **Consumed** — `ui/app.js:6896–6897` |
| `efc_depth` | 11752, 11767 | Same as above | Replace: `prior + 1` or carried value | **Consumed** — `ui/app.js:6898–6899` |
| `repair_attempt_count` | 12160 | `_confirmed_re_ask` only | Replace with `0` (reset-only; the escalation value itself is never echoed back) | **Consumed** — `ui/app.js:6900–6908` |
| `mirror_confusion_count` | 12161 | `_confirmed_re_ask` only | Replace with `0` (reset-only) | **Not consumed** — no merge case in `ui/app.js`; the client also never sends this field in `conversation_state`, so even if the reset were applied it could not round-trip (documented gap, Section 11, Section 16.2 SIC-1) |
| `recent_confusion_count` | 12162 | `_confirmed_re_ask` only | Replace with `0` | **Not consumed via `state_update`** — the field *is* sent by the client in `conversation_state` every turn (Section 5.1), but the client-side merge block has no case for a `state_update.recent_confusion_count` reset; the client's own copy is only ever incremented locally, not reset from this server write |
| `consecutive_not_understood` | 12163 | `_confirmed_re_ask` only | Replace with `0` | **Not consumed** — no merge case in `ui/app.js`; the client also never sends this field in `conversation_state` at all (documented gap, Section 16.2 SIC-3) |

**Client-consumed vs. unconsumed summary (14 of 20 fields have a merge case on the primary Pattern-A path; 6 do not):** consumed — `current_engine` (via `_resolveNextEngineId` as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`; also consumed independently by `runMirrorTurn` for Pattern B), `last_counter_reply`, `recent_persona_replies`, `last_partner_frame_text`, `last_place_subject`, `learner_stated_location`, `learner_food_note`, `consecutive_app_questions`, `discovery_shown_last_turn`, `last_persona_reveal`, `recently_seen_disc_topics`, `efc_entity`, `efc_depth`, `repair_attempt_count`. Still unconsumed by any call path — `pending_dest_candidate`, `location_retry_count`, `location_clarify_hint`, `mirror_confusion_count`, `recent_confusion_count` (no reset merge case), `consecutive_not_understood`. These six are unaffected by this fix and remain open gaps (Section 16.2).

**Historical note (R2).** At the original baseline (commit `53584cee9e8c892ff77f12741d1fc89d9d09c7e7`), this summary read "13 of 20 fields have a merge case; 7 do not," with `current_engine` listed as consumed only in the non-primary `runMirrorTurn` path. That gap is now closed; the count above reflects the current, verified state of the merged code.

**Omission semantics.** For every field in this table, omission from `state_update` means **leave the client's own value unchanged** — the client does not clear a field simply because the server did not mention it that turn. There is no field in this contract where omission is defined to mean "clear." This is distinct from the fields above marked "not consumed": those are never applied regardless of whether the server includes them, because no client code path reads them at all.

**`null` semantics.** Only `pending_dest_candidate` uses an explicit `None`/`null` write, and it means "no pending destination candidate" (an intentional clear), not "unknown." No other `state_update` field is ever explicitly set to `null`.

**Fields mutated in-request but never written to `state_update`.** `last_mirror_topic`, `last_mirror_engine`, and the *escalation increment* of `mirror_confusion_count` (as opposed to its reset) are written into the server's in-request `cs` dict (`scripts/ui_server.py:10317–10334`) but never copied into `response["state_update"]`. Because the client does not send these fields in `conversation_state` at all (Section 5), this in-request mutation has **no effect beyond the current request** — the mirror confusion ladder cannot currently escalate across turns via the production client, even though `_is_confusion_signal` detection and the escalation-stage functions (`_mirror_restate_naturally`, `_mirror_persona_stub_simple`, `_confusion_recovery_reply`) exist and are exercised directly by tests that inject these fields manually (`test_stale_counter_reply_loop.py`).

---

## 7. Working-memory contract

**`recent_persona_replies` is capped at three entries.** Evidenced at `scripts/ui_server.py:11826`:

```python
_updated_recent = (_recent_persona_replies + [_counter_reply])[-3:]
```

The trimming rule is append-then-slice-to-last-3, applied server-side every turn that produces a `counter_reply`; the client replaces its entire local copy from `state_update.recent_persona_replies` rather than appending independently.

**What is semantically working memory vs. mere deduplication history:**

- **Working memory (feeds E3):** `recent_persona_replies` is read by `_extract_persona_facts_from_recent()` to derive facts (favourite travel place, hometown, etc.) that `_answer_from_working_memory()` (E3) can answer follow-up questions from. This is genuine short-term conversational memory.
- **Deduplication history (not working memory in the E3 sense):** `last_counter_reply` and the same `recent_persona_replies` list are *also* checked to suppress an exact-repeat answer before it is spoken again (`_dedupe_persona_answer()`). The same field therefore serves two different purposes.
- **Confusion escalation support:** `last_mirror_topic`, `last_mirror_engine`, `mirror_confusion_count` are intended to support the mirror-confusion ladder (Section 11) but, per Section 6, do not currently round-trip through the production client.
- **Stale-answer prevention:** the pool re-selection logic in `_dedupe_persona_answer()` uses `recent_persona_replies` plus `last_counter_reply` to avoid recycling a just-given answer; if the same-intent pool is exhausted, it falls back to a topically appropriate clarification rather than reaching into an unrelated pool.
- **What clears working memory:** `_resetCurrentSessionState()` sets `window._recentPersonaReplies = []`, but it does **not** assign `window._lastCounterReply` or `window._recentReactions` at all — there is no explicit re-init line for either. This means a browser reload reinitialises both to `undefined` (the script-load default), but starting a new session in the same tab (without reloading) leaves whatever value the previous session last wrote in place; they are not implicitly cleared merely because a new session begins (verified this revision — see Section 5.1 and Section 13 for the same finding applied to the reset matrix). Clearing persistent learner memory (`/api/reset_memory`) does **not** clear working memory either; they are independent operations (Section 13).

**Why working memory must not persist as learner biography.** Working memory answers *"what did the partner just say?"* for at most three recent turns and is deliberately volatile — it exists to make follow-up questions feel coherent within a conversational arc, not to remember who the learner is across sessions. Persistent learner memory (Section 8) answers *"who is this learner?"* and is the only subsystem intended to survive session boundaries. Conflating the two would mean a transient in-conversation remark (e.g. a passing mention while working memory was populated) could leak into long-term biography, or conversely that genuine biographical facts could be lost the moment the 3-entry window rolls over. The two subsystems are implemented with entirely separate storage, separate clear operations, and separate consumers, and this document treats any code path that blurs them as a defect, not a feature.

---

## 8. Persistent learner-memory contract

**Terminology used throughout this section and Section 9.** This document distinguishes two categories of data that both live under the "learner memory" name but are governed by different code paths:

- **Canonical learner-profile facts** — the six keys named in `LEARNER_MEMORY_KEYS`, governed end-to-end by `validate_updates()`, `apply_updates()`, `save()`, and `clear()`. These are what the rest of this section describes.
- **Auxiliary persisted learner metadata** — data some code *attempts* to store keyed by `learner_id` outside the six canonical keys, such as `partner_facts_seen` (`scripts/ui_server.py:12378–12383`). As documented below, this category currently does **not** survive the persistence layer as implemented — it is included here as an evidenced finding, not as a working second storage tier.

**Exact allowed keys** (`scripts/learner_memory.py:22–29`, `LEARNER_MEMORY_KEYS`):

```python
LEARNER_MEMORY_KEYS = (
    "learner_name", "hometown", "lives_in",
    "job_or_study", "family", "favourite_food",
)
```

| Key | Populating frame(s)/extractor | Normalisation | Persistence path |
|---|---|---|---|
| `learner_name` | `f_ask_you_name` → `_extract_name_from_hanzi` | Trim/strip only | `data/learner_memory.json` |
| `hometown` | `f_from_where` → `_extract_origin_from_hanzi` | `normalize_place_name()` (place-alias canonicalisation, ASR-junk stripping) | Same |
| `lives_in` | Live-location frames → residence extractor; also `_extract_open_world_location()` for unscripted answers | `normalize_place_name()` | Same |
| `job_or_study` | Job/study frames | Junk-fragment stripping | Same |
| `family` | Family-situation frames | Junk-fragment stripping | Same |
| `favourite_food` | Food-preference frames | Junk-fragment stripping | Same |

**Known dead-end field.** `job_company` is extracted by `learner_memory_capture.py` and read at `scripts/ui_server.py:9707`, but it is **not** in `LEARNER_MEMORY_KEYS`. `validate_updates()` silently drops any key not in this tuple, so `job_company` extractions are computed but never persisted. This is a real gap, not a documentation omission — flagged in Section 19.

**Auxiliary metadata dead-end, verified this revision: `partner_facts_seen` does not currently persist at all.** `scripts/ui_server.py:12378–12383` attempts to record a cross-session "has this persona fact already been shown to this learner" flag:

```python
_pmem = _lm_load(_p11c_learner_id) or {}
_pmem.setdefault("partner_facts_seen", {}) \
     .setdefault(_partner_id, {})[_engine_key] = True
_lm_save(_p11c_learner_id, _pmem)
```

This looks like it should work, but `save()`'s merge is key-restricted to the six canonical keys (`scripts/learner_memory.py:118`, `merged = {k: memory.get(k) if memory.get(k) is not None else existing.get(k) for k in LEARNER_MEMORY_KEYS}`). Because this dict comprehension iterates only over `LEARNER_MEMORY_KEYS`, the `partner_facts_seen` key set on `_pmem` above is **not included in `merged`** and is therefore never written to `_store` or to disk. `_load_file()` (`scripts/learner_memory.py:75`) independently confirms this: it normalises every loaded record to exactly the six canonical keys, so even a `partner_facts_seen` key present in a hand-edited or externally-written file would be dropped on the next load into `_store`. The practical consequence: every call to `_lm_load(...).get("partner_facts_seen", {})` — including the read at `scripts/ui_server.py:12363` that checks whether a fact was already shown — always evaluates against an empty dict, because the write immediately before it is discarded before it reaches persistent storage. This is a genuine, evidenced dead-end at the *save-merge* layer, one step further down the pipeline than the `job_company` dead-end above (which is caught earlier, at *update-validation* time). Unlike `job_company`, the code's own inline comment and structure strongly suggest cross-session persistence was the intent — this reads as an incomplete feature, not an intentional exclusion (added to Section 19 risks and Section 16.2 as SIC-5b).

**What `clear(learner_id)` does to auxiliary metadata.** `clear()` (`scripts/learner_memory.py:123–134`) unconditionally replaces `_store[lid]` with `empty_memory()` — a plain six-key, all-`None` dict — and writes that to disk. Because `partner_facts_seen` never reaches `_store` in the first place (per the finding above), `clear()` has no *observable* effect on it specifically: there is nothing there to remove. If a future fix changed `save()` to preserve unrecognised extra keys (mirroring the precedent already set by `migrate_corrupted_memory()`, which does preserve extra keys via `merged = dict(mem); merged.update(new_mem)`, `scripts/learner_memory.py:250–252`), then `clear()`'s full-dict replacement would erase such a key too, since `clear()` does not merge — it writes a literal six-key dict, discarding anything else `_store[lid]` may have held. In short: today, `clear()` only ever touches the six canonical keys, both because that is all it writes and because that is all `_store[lid]` can ever contain.

**Overwrite/merge semantics — three distinct operations with different rules:**

| Operation | Behaviour | Evidence |
|---|---|---|
| `apply_updates(memory, updates)` | Pure function; returns a *new* dict. `None` in `updates` explicitly sets that field to `None` in the returned dict; missing keys are left unchanged; unknown keys and non-string/non-`None` values are dropped by `validate_updates()`; empty strings are normalised to `None` | `scripts/learner_memory.py:37–57` |
| `save(learner_id, memory)` | Merge-on-write to disk: a **non-`None`** value in `memory` overwrites the stored value; a **`None`** value *leaves the stored value unchanged* (does **not** erase it) | `scripts/learner_memory.py:103–120` |
| `clear(learner_id)` | Unconditional: sets **all six** keys to `None` and writes the file, bypassing merge entirely | `scripts/learner_memory.py:123–134` |

**The critical distinction, stated explicitly (this previously caused a memory-reset regression):**

- **Missing key** in an updates dict: field is left exactly as it was before — no effect.
- **Key present with `None`**: through `apply_updates()`, the in-memory result dict gets `None` for that key; but if that result is then passed to `save()`, `save()`'s own merge logic treats the `None` as "no new information" and preserves whatever was already on disk. **There is no way to erase a single field through the normal capture→save pipeline** — a `None` value never survives the `save()` merge.
- **Key with empty string `""`**: `validate_updates()` converts `""` to `None` before it reaches either `apply_updates()` or `save()`, so it behaves identically to "missing" for practical purposes — it can never erase a value either.
- **Explicit deletion**: only achievable via `clear(learner_id)`, which erases **all six fields at once** for that learner. There is no per-field delete operation in the baseline.
- **Unchanged value**: any key omitted from an updates dict, or present with `None`/`""`, is unchanged — these three inputs are behaviourally identical from `save()`'s perspective, even though they are semantically distinct at the call site.

The production capture path (`capture_from_turn()` → `_lm_apply_updates()` → `_lm_save()`, `scripts/ui_server.py:9177–9190`) only ever constructs `updates` dicts with truthy extracted values, so this ambiguity has not manifested as a production bug at the baseline — but it means a future author adding a "let the learner correct/clear a single fact" feature cannot simply send `None` for that field and expect it to erase; they would need a new mechanism.

**Accepted open-world behaviour.** `_extract_open_world_location()` accepts any structurally-recognised residence statement (`我住在X`, `我现在住在X`, etc., matched against `_RESIDENCE_ANSWER_PREFIXES`) or, when the active frame is specifically asking about residence, a bare place name. It performs **no lookup, confirmation, or validation** against a known-place list before the value reaches `learner_memory["lives_in"]` or `["hometown"]`. This is intentional baseline behaviour, not a bug: the learner is treated as the source of truth for their own residence.

**Persistence path.** `data/learner_memory.json`, relative to `BASE_DATA_DIR = Path(os.environ.get("MANDARINOS_DATA_DIR", <repo_root>/"data"))`. On Railway, the mounted-volume path supplied via `MANDARINOS_DATA_DIR` is authoritative, not the in-repo `data/` directory.

**Migration rules.** `migrate_corrupted_memory()` (`scripts/learner_memory.py:189–269`) is a one-time cleanup for pre-fix ASR-junk values: place fields are re-normalised via `normalize_place_name()` (unrecoverable values become `None`); non-place fields have known junk fragments stripped. It operates directly on the raw JSON file (not through `save()`), so it preserves unrecognised extra keys **already present in the file** (`merged = dict(mem); merged.update(new_mem)`, forward-compatibility for keys that somehow got into the file by another route) and supports `dry_run=True` for inspection without writing. This is a different code path from `save()`/`_load_file()`, which both strip to the six canonical keys — so a key preserved by migration would still be stripped again the next time `_load_file()` runs. There is no other version-tagged schema-migration mechanism in the baseline.

**Use in frame slot substitution.** `{CITY}`/`{PLACE}` template tokens resolve `lives_in` with fallback to `hometown` (`scripts/ui_server.py:11670–11673` region). This is a read-only consumption path; slot substitution never writes back to learner memory.

**Reset behaviour.** `/api/reset_memory` calls `_lm_clear(learner_id)` only — it does not touch progress snapshots, session-capture files, `conversation_state`, or `localStorage`. See Section 13 for the full reset matrix.

**Server is authoritative; client input is untrusted.** The client never sends a `learner_memory` object in the request payload — the server may *return* one for display (`response["learner_memory"]`), but this is read-only echo, not writable input.

---

## 9. Persona state and identity

**Distinct concepts, frequently conflated in casual discussion:**

| Concept | What it is | Where it lives |
|---|---|---|
| Learner identity (`learner_id`) | Key for persistent learner memory and progress | `window._learnerId`, `localStorage["manos_learner_id"]` |
| Active partner/persona ID (`persona_id` / `partner_id`) | Which partner persona the learner is currently talking to | `window._partnerId` (preferred) or `window._personaId` (legacy fallback) |
| Persona profile data | Immutable content: `profile`, `voice_lines`, `discoverable_facts`, `discoverable_facts_en`, `voice_lines_en`, `distance_profile` | `personas/<id>.json`, cached server-side in `_personas_cache` |
| Discoverable facts | Subset of persona profile data, revealed progressively during conversation | Same file; reveal *tracking* is session state (below) |
| Persona voice lines | Static scripted partner utterances, keyed by engine/topic | Same file |
| Recent persona replies | Session-derived conversational history *about* what the persona has said, not persona content itself | `window._recentPersonaReplies` / `cs["recent_persona_replies"]` (Section 7) |

**How the active persona is selected.** `loadPersonas()` fetches `/api/personas`, renders a button per persona, and on click sets `window._partnerId = p.id` (`ui/app.js:4967–4996`). If no partner is set when the list loads, the first available persona is auto-selected. `window._personaId` is a legacy fallback initialised once to `"zhang_wei"` (`ui/app.js:678`) and is only consulted when `window._partnerId` is falsy.

**Crossing the API.** `persona_id` is placed in `conversation_state.persona_id` (Pattern A, full contract) as `window._partnerId || window._personaId`, but on stub patterns (B/C/D) it is instead placed at the **payload root** (`payload.persona_id`), not inside `conversation_state`. Server-side resolution order is itself inconsistent: most call sites try `payload.get("persona_id") or cs.get("persona_id")` first, but one site (`scripts/ui_server.py:11500`) tries `cs.get("persona_id") or payload.get("persona_id")` — the opposite order. Both would normally agree because the client sends the same value in both places when it sends both at all, but this inconsistency is a maintenance risk (Section 19).

**`_resolve_persona()` behaviour when the ID is absent or invalid** (`scripts/ui_server.py:659–674`): an empty/falsy `persona_id` returns `None` immediately; an unknown ID (no matching `personas/<id>.json` file) returns `None`; a file that exists but fails to parse returns `None` and logs a warning. There is no error response to the client in any of these cases — the caller falls back to `_get_persona(persona_id)` (a separate module) or proceeds with `persona = None`, in which case persona-dependent answer paths simply produce no persona-specific content for that turn rather than raising an error.

**Does changing persona clear other state?** Switching persona (clicking a different persona button) explicitly resets `window._revealedVoiceLines = {}` and `window._revealedPartnerFacts = {}` (per-engine reveal-tracking dictionaries) and clears the partner-header display, but it does **not** reset `conversation_state`, `recent_persona_replies`, `current_engine`, `recent_frame_ids`, or any counter. This means the learner can switch persona mid-conversation and the new persona will inherit the working-memory dedup history and engine position built up while talking to the previous persona — a documented characteristic, not necessarily desirable (Section 19).

**Immutable content vs. session-derived state.** Persona profile/voice-lines/discoverable-facts JSON is immutable content, loaded once and cached for the process lifetime. What varies per session is the *reveal tracking* (`revealed_voice_lines`, `revealed_partner_facts`), which is genuine session-scoped conversation state, round-tripped through `conversation_state` (Section 5.1). The code additionally *attempts* a second, cross-session tracking mechanism — auxiliary metadata keyed as `partner_facts_seen` inside learner memory (`_pmem.setdefault("partner_facts_seen", {})...`, `scripts/ui_server.py:12378–12383`) — intended to remember, across sessions, which persona facts a given learner has already seen. As verified in Section 8, this second mechanism does **not** currently work: `save()`'s key-restricted merge silently discards `partner_facts_seen` before it reaches `_store` or disk, so every read of it evaluates against an empty dict regardless of what was "written" moments earlier. Persona-fact reveal state therefore has, in the current baseline, only **one** functioning tracking mechanism (session-scoped, via `conversation_state`) rather than the two the code structure implies.

---

## 10. Frame and engine state

**Three distinct "engine" values that must not be confused:**

| Value | Where | Meaning |
|---|---|---|
| Incoming `conversation_state.current_engine` | Request | The engine the client believes is active *before* this turn's selection runs |
| Response `engine_id` | Response, top level | The engine the frame actually returned in *this* response belongs to (computed from the incoming engine, before any E4 write) |
| `state_update.current_engine` | Response | The engine that should be active *starting next turn* (only present if E4 or a direction-stub handoff fired) |

**Timeline example — deferred E4 handoff across two requests, updated this revision (R2) to reflect that both call paths now apply the handoff:**

```
Turn N   (learner asks a direct place question, while current_engine = "identity")
  request:  conversation_state.current_engine = "identity"
  server:   frame selected from "identity"           → response.engine_id = "identity"
            E4 computes handoff                        → _e4_engine_handoff = "place"
            E4 writes (after frame selection)          → response.state_update.current_engine = "place"

  client (Pattern A — ordinary "Next" turn, the common case for an in-conversation question):
            current-frame bookkeeping/rendering/diagnostics all use engineId → "identity"
              (this frame is never relabelled — client current-frame attribution: "identity")
            THEN, as the last statement of _runTurnInner():
              window._currentEngineId = _resolveNextEngineId(engineId, data.state_update)
              → client future engine after helper: "place"

  client (Pattern B — runMirrorTurn, only if this question was asked via the dedicated
            mirror-question UI action rather than as an ordinary turn):
            sets window._currentEngineId from data.engine_id, THEN overrides from
            data.state_update.current_engine → "place" (unchanged by this fix)

Turn N+1 (any learner input)
  request:  conversation_state.current_engine = "place"
  server:   frame selected from "place"               → response.engine_id = "place"
  client:   sees a "place" frame — the redirect is now visibly in effect on the primary
            Pattern-A path (previously only visible via Pattern B — see historical note below)
```

**Historical note (R2).** At the original baseline (commit `53584cee9e8c892ff77f12741d1fc89d9d09c7e7`), this example showed two divergent outcomes for Turn N+1 depending on which client call path Turn N used — Pattern A retained the pre-handoff engine (`"identity"`) indefinitely, and only Pattern B (`runMirrorTurn`) picked up the redirect — because `_runTurnInner()` had no read site for `data.state_update.current_engine` at all (documented as SIC-6, now resolved; see Section 16.2). Commit `3be0315b2c9f7316b03ac2183a887f602ae9a297` closed that gap; both call paths now converge on the redirected engine, evidenced by `tests/test_e4_client_handoff_regression.py`, a deterministic two-turn HTTP integration test that reproduces exactly the sequence shown above using the real `_resolveNextEngineId()` helper rather than a hand-inserted engine value.

**Loop and dwell counters, engine visitation, bridge preferences** (see Section 5.1 for full field detail): `loop_count_in_current_engine`, `same_engine_chain_count`, `engines_visited`, `seeded_bridge_engines`, `medium_probe_fired_engines`. These are read by the primary bridge gate and by the post-selection loop-cap correction described in `CONVERSATION_ARCHITECTURE.md` Section 5.6 — this document does not repeat that selection logic, only the state it consumes.

**`recent_frame_ids` cap/trim.** Client-side cap at **50** entries (`ui/app.js:6921–6923`, push then `slice(-50)`). The server does **not** independently trim this list — it trusts and reads the client's list as-is. Immediate-frame-repeat prevention is enforced entirely through selection logic (`fid not in recent_frame_ids` checks inside `_select_next_frame_ladder`, `_select_next_frame_ladder_avoiding`, and `_is_loop_candidate`), not through any additional state field.

**Completion/closing state.** Session-arc "closing" is a derived boolean (`_12c_closing = exchange_count >= CLOSURE_EXCHANGE_THRESHOLD`), recomputed each turn from `exchange_count` — there is no separate persisted "closing" flag.

---

## 11. Recovery and confusion state

| Field/mechanism | Client-only? | Server-derived? | Round-tripped via `conversation_state`? | Preserves current frame, or may advance? |
|---|---|---|---|---|
| Spoken recovery interception (`matchSpokenRecoveryPhraseExact`) | Yes — entirely client-side; no server call is made when it matches | — | N/A (never reaches server) | **Preserves** the current frame exactly (Path A, `CONVERSATION_ARCHITECTURE.md` §12.1) |
| `computeRecoveryTriggerContext` overlay (ASR band, partial-match score, `repeat_repair_count`) | Yes, client-only | — | No | N/A (feeds client-side decision only) |
| Server `_is_rr` / `_is_meaning` / `_is_example` classification | No | Yes, computed fresh per request from the submitted text | N/A (classification is stateless per turn) | **May advance** the ladder (Path B) |
| `recent_confusion_count` | Client-incremented, server-read | Server resets on repair success | **Yes** — sent every turn | Contributes to overload gating, does not itself preserve/advance a frame |
| `repair_attempt_count` | Client-incremented, server-read | Server computes escalation level via `max()` with other counters; resets via `state_update` on confirmed re-ask | **Yes** | Drives which repair-escalation reply is chosen; frame advance depends on the escalation stage reached |
| `consecutive_not_understood` | Read by server | Never sent by the production client (`window._consecutiveNotUnderstood` exists but is not included in `conversation_state`) | **No — documented gap** | Effectively always `0` from the server's perspective in production |
| Mirror confusion ladder (`last_mirror_topic`, `last_mirror_engine`, `mirror_confusion_count`) | Read/mutated server-side, in-request only | Server escalates stage-by-stage while a mirror answer is active | **No — documented gap.** These fields are read from `cs` and written back into the *same-request* `cs` dict, but never appear in the client's `conversation_state` payload nor in `state_update` (except a reset-to-0 on confirmed re-ask) | The escalation ladder (`_mirror_restate_naturally` → `_mirror_persona_stub_simple` → `_confusion_recovery_reply`) advances the frame at each stage, but the *stage itself* cannot persist across turns via the production client |
| Noisy-location clarification (`location_retry_count`, `location_clarify_hint`) | Server-derived and written to `state_update` | Yes | **No — documented gap.** Server writes these to `state_update`; the client does not currently merge them back into `conversation_state` | Frame is explicitly overridden to repeat the location frame at escalating levels; does not advance until accepted |
| Challenge-mode recovery (`_challenge.recoveryCount`, `_challenge.helpLevel`) | Entirely client-side | — | **No** — never sent in `conversation_state` or any payload except a derived `mode` string in `/api/end_session` | Client-only UI escalation (replay → slow → text reveal → suggestion); server recovery routing is unaffected by challenge mode |

**Summary of which recovery paths preserve the current frame vs. advance it:** client-intercepted spoken recovery (Path A) always preserves the frame; server-side typed/unintercepted recovery (Path B) always runs normal frame selection and may advance; mirror-confusion escalation stages 1–2 restate/simplify without necessarily advancing the *frame_id* itself but do progress the escalation *stage*; noisy-location clarification explicitly overrides frame selection to repeat the same location frame across escalation levels.

---

## 12. Session initialization

**Sequence on application load:**

1. `initLearnerId()` runs at script load (`ui/app.js:489–507`): checks a `?beta=` URL parameter first, then `localStorage["manos_learner_id"]`, and falls back to the literal string `"default_learner"` if neither is present. `window._learnerId` is guaranteed to be set to a non-empty string by the time any other initialization code runs.
2. `window._personaId` initialises to `"zhang_wei"` and `window._partnerId` initialises to `null` if not already set (`ui/app.js:678, 680`).
3. `loadPersonas()` fetches `/api/personas` and, if `window._partnerId` is still unset, auto-selects the first persona in the returned list.
4. The first frame is loaded via the dropdown-driven Pattern D path (`_runTurnInner(false, ...)`) — no `conversation_state` is sent for this very first frame request.
5. First-turn engine fallback: the first time a Pattern A (`next_question: true`) request is assembled, `current_engine` falls back through `window._currentEngineId ?? <dropdown-selected engine's data attribute> ?? "identity"`.
6. Empty histories/counters: all list-typed fields initialise to `[]` except `engines_visited`, which initialises to `["identity"]` (not empty — the identity engine is considered "already visited" from the start).
7. Learner memory is **not** loaded proactively at page load by the client — it is loaded server-side, lazily, the first time a request supplies a non-empty `learner_id` and needs it (e.g. for slot substitution or answer capture).
8. Progress state is loaded lazily by explicit UI actions (e.g. opening a progress view), via `/api/progress?learner_id=...`, not at page load.

**Initial-defaults table (selected fields; full inventory in Section 5.1):**

| Field | Initial value | Not `null` — verified as: |
|---|---|---|
| `session_id` | `"session_" + Date.now()` | non-empty string, always unique per load |
| `current_engine` | `"identity"` (via fallback chain) | non-empty string |
| `recent_frame_ids` | `[]` | empty array, not `null` |
| `engines_visited` | `["identity"]` | one-element array, not empty and not `null` |
| `exchange_count`, `curiosity_depth`, `ask_chain_count`, `loop_count_in_current_engine`, `recent_confusion_count`, `repair_attempt_count`, `efc_depth`, `probe_depth` | `0` | integer zero, not `null`/`undefined` |
| `pending_listening_move`, `discovery_shown_last_turn`, `last_persona_reveal` | `false` | boolean, not `null` |
| `last_interest_level` | `"low"` | non-empty string |
| `last_partner_turn_type` | `"question"` | non-empty string |
| `efc_entity` | `null` | genuinely `null` — one of the few fields where `null` is the documented default |
| `learner_id` | `"default_learner"` (fallback) | non-empty string; never `null`/`undefined` after `initLearnerId()` runs |
| `persona_id`/`partner_id` | `null` until persona list loads, then auto-selected | may be transiently `null` between page load and the async `/api/personas` response resolving |

---

## 13. Session reset and clear-memory semantics

**Distinct reset operations in the baseline:**

1. **Start a new conversation/session** — triggered by the "Start" button; calls `_resetCurrentSessionState()` before the first `runTurn`.
2. **"Forget conversation" / clear learner memory** — `startFreshLearner()`: POSTs `/api/reset_memory`, then calls `_resetCurrentSessionState()`, then additionally clears `window._lastMentionedPlace`.
3. **Switch persona** — clicking a different persona button.
4. **Browser reload/reopen** — no explicit reset function runs; all session-ephemeral `window._*` globals are simply re-initialised to their script-load defaults; `localStorage`-backed values (`learner_id`, progress history) survive.
5. **Server restart/redeploy** — in-memory `_store` cache (learner memory) and `_personas_cache` are rebuilt from disk/content files on next access; the persisted `data/learner_memory.json` and `data/progress/*.json` files survive because they are files, not process memory.

**Reset matrix:**

| State category | New session (`_resetCurrentSessionState`) | Clear learner memory (`startFreshLearner`) | Persona switch | Browser reload | Server restart |
|---|---|---|---|---|---|
| `window._lastMentionedPlace` | Not touched by this function itself | **Cleared** (`ui/app.js:6566`, explicit line inside `startFreshLearner`) | Not touched | Cleared (re-init to `null`) | N/A (client-only) |
| `recent_persona_replies` | Cleared (`[]`) | Cleared (calls the session reset) | Not cleared | Cleared (re-init) | N/A |
| `current_engine` | Cleared (fallback default) | Cleared (calls the session reset) | Not cleared | Cleared (re-init) | N/A |
| Canonical learner facts (six `LEARNER_MEMORY_KEYS`, `learner_memory.json`) | Not touched | **Cleared** (`/api/reset_memory` → `_lm_clear`, sets all six to `None`) | Not touched | Not touched (persisted) | Preserved if storage path is persistent (Section 1, Section 2) |
| Auxiliary metadata (`partner_facts_seen`) | Not touched | N/A — nothing to clear; per Section 8, this key never survives `save()`'s merge, so it is never present in `_store`/disk for `clear()` to remove | Not touched | Not touched | N/A |
| Progress snapshots | Not touched | **Explicitly preserved** (tested negatively — no `localStorage.removeItem`, no snapshot deletion call) | Not touched | Preserved | Preserved (file survives) |
| Session identifiers (`session_id`, `_sessionStartedAt`) | Regenerated | Regenerated (calls session reset) | Not touched | Regenerated | N/A |
| Challenge mode (`_challenge.active`) | Not reset (independent toggle) | Not reset | Not touched | Reset to `false` (script default) | N/A |
| Selected persona (`window._partnerId`) | Not touched | Not touched | **Changed** (that is the operation) | Cleared, then re-auto-selected on persona list load | N/A |
| `_revealedVoiceLines` / `_revealedPartnerFacts` | Cleared (`{}`) | Cleared (calls session reset) | **Cleared** (persona-switch handler explicitly resets these) | Cleared (re-init) | N/A |
| `_tracker` counters | Cleared (all zeroed) | Cleared (calls session reset) | Not touched | Cleared (re-init) | N/A |
| `learner_id` | Not touched | **Explicitly preserved** (no ID rotation) | Not touched | Preserved (from `localStorage`) | N/A (server-side key, not process state) |
| `window._lastCounterReply` | **Not touched** — no assignment in `_resetCurrentSessionState()` | Not touched (calls session reset, which also does not touch it) | Not touched | Reinitialised to `undefined` (script-load default) | N/A (client-only) |
| `window._recentReactions` | **Not touched** — no assignment in `_resetCurrentSessionState()` | Not touched (calls session reset, which also does not touch it) | Not touched | Reinitialised to `undefined`/script default | N/A (client-only) |

**Same-tab new-session leakage, verified this revision.** `_resetCurrentSessionState()` — the function invoked by both "Start" and `startFreshLearner()` — contains no assignment to `window._lastCounterReply` or `window._recentReactions`. Consequently: a **browser reload** reinitialises both to their script-load defaults (harmless), but starting a **new session in the same tab without reloading** does not clear either — the new session's first few requests can carry over the previous session's last counter-reply and reaction-dedup history. Neither field is implicitly cleared merely because a new session has begun; only an actual page reload resets them. This is not fixed as part of this document (Section 1 — the frozen baseline is described, not corrected); see also Section 5.1, Section 7, Section 16.2 (SIC-4), and Section 20.

**Evidence for the "does not necessarily reset progress history" contract:** tests `test_reset_does_not_clear_progress_history`, `test_clear_memory_does_not_remove_progress_history`, and `test_clear_memory_does_not_call_first_time_hygiene` (all in `tests/test_session_start_reset.py`) assert the *absence* of any `localStorage.removeItem("manos_progress_history")` call and the absence of any call to `_applyFirstTimeBetaHygiene()` (a separate function that *does* wipe progress and is reserved for first-time-user onboarding, not for the "forget conversation" action).

---

## 14. Session capture, progress, and analytics state

These subsystems relate to conversation state but are **not** part of semantic routing — the frame selector and answer-source chain never read `_tracker`, progress snapshots, or session-capture files.

- **Session ID / learner ID:** `session_id` is used both inside `conversation_state` (for probabilistic-gate seeding, Section 5.1) and as a grouping key for session capture; `learner_id` is the persistence key shared across learner memory, progress, and session capture, but each subsystem stores its own file(s) — there is no single unified per-learner record.
- **Capture files:** transcript/event-log capture writes to `data/sessions/<learner_id>/<session_id>.json` when enabled; entirely separate from `learner_memory.json` and `data/progress/<learner_id>.json`.
- **Scorecard counters (`_tracker`):** an in-memory client object (`total_turns`, `recovery_uses`, `display_en_clicks`, `card_opens`, etc.) zeroed by `_resetCurrentSessionState()` and sent only once, at `/api/end_session`, to be converted into a persisted progress snapshot server-side (`_build_progress_snapshot`, `scripts/ui_server.py:8457–8493`).
- **Lifetime vs. session metrics:** `_tracker` is strictly session-scoped and never persisted directly. `capability_estimator.compute()` separately derives `lifetime_turn_count` and an `inactive`/`inactivity_days` signal (default 21-day threshold from `content/capability_band_thresholds.json`) from the accumulated progress-snapshot history, exposed via `/api/capability` — this is analytics/reporting state, computed after the fact, not conversation state.
- **Progress bands:** there is no field literally named `progress_band`; per-dimension `band` labels (`Emerging`, `Developing`, `Consolidating`, `Steady`) come from `capability_estimator.py` and are reporting output, not input to conversation routing.
- **Do analytics fields influence conversation selection?** No — confirmed by absence of any read of `_tracker`, progress-snapshot, or capability-band fields anywhere in the `/api/run_turn` selector/answer-source code paths. The one exception worth naming precisely: `challenge_active` is read into a debug/console snapshot (`_computeLearnerState`) for observability, not for routing.

This document does not restate the retention/tiering rules or the pipeline mechanics for these subsystems — that is `TEST_STRATEGY.md`/operational-documentation territory. The purpose here is only to state, unambiguously, that these values are **analytics/reporting state**, not semantic conversation-routing state.

---

## 15. State validation and defensive defaults

| Condition | Server behaviour | Evidence |
|---|---|---|
| Missing `conversation_state` key entirely | `cs = payload.get("conversation_state") or {}` (direction/probe stub paths) or `cs` stays `None` (main selector path); the main selector block is skipped and the server falls back to `frame_id`/`engine_id` from the payload root | `scripts/ui_server.py:8991, 9080, 9134–9139` |
| `conversation_state` present but not a dict (string, list, number) | Same as above — `isinstance(..., dict)` check fails; treated identically to "missing" | `scripts/ui_server.py:9138` |
| Missing/malformed individual fields | Field-by-field defensive coercion at each read site: `int(cs.get(x) or 0)`, `(cs.get(x) or "").strip()`, `list(cs.get(x) or [])`, `cs.get(x) is True` | Pervasive throughout the handler (Section 5/6 tables) |
| Unexpected types (e.g. a string where a list is expected) | `list(cs.get("recent_frame_ids") or [])` would raise if given a non-iterable truthy value (e.g. an int) — **not defensively type-checked**, only defended against falsy/missing values | `scripts/ui_server.py:9141` and similar `list(...)` coercions |
| Unknown `current_engine` value | No explicit validation against a known-engine list; an unrecognised engine string would simply fail to match any `_FRAME_ORDER` key and fall through to bridge/fallback selection | Inferred from `_FRAME_ORDER` dict-lookup pattern; no explicit guard found |
| Stale/unknown `frame_id` in `recent_frame_ids` or `last_partner_frame_id` | Treated as opaque strings for membership checks (`fid not in recent`); an unrecognised ID simply never matches anything, which is harmless for exclusion logic | `_select_next_frame_ladder`, `_is_loop_candidate` |
| Absent `persona_id` | `_resolve_persona()` returns `None` immediately; downstream persona-dependent paths degrade to no persona-specific content rather than erroring | `scripts/ui_server.py:659–662` |
| Missing learner-memory file | `load()` returns `empty_memory()` (all six keys `None`) rather than raising | `scripts/learner_memory.py:91–100` |
| Migration of old learner-memory formats | `migrate_corrupted_memory()` is an explicit, separately-invoked cleanup (via `scripts/migrate_learner_memory.py`), not run automatically on every load | `scripts/learner_memory.py:189–269` |
| Client fallback when server response is incomplete | Client only applies fields that are present in `data.state_update` / top-level response (`if (value !== undefined)`-style guards); absent fields are left as the client's own prior values, never nulled | `ui/app.js:6882–6919` |

**Truthiness-dependent interpretation — explicit maintenance-risk labels:**

- `bool(cs.get("location_clarify_hint"))` treats the string `"active"` as truthy and `""` as falsy — this is a deliberate two-value string encoding, not a boolean field, and a future author adding a third state (e.g. `"pending"`) must verify this truthiness check still behaves correctly.
- `discovery_shown_last_turn` and `last_persona_reveal` use `bool(cs.get(x) or False)` in one place and `bool(cs.get(x))` (no explicit `or False`) elsewhere — behaviourally equivalent for the values actually produced today, but inconsistent style that could diverge if a caller ever passed a falsy-but-meaningful value like `0`.
- `int(cs.get("exchange_count") or 0)` is used in most places but a bare `cs.get("exchange_count") or 0` (no `int()` cast) appears at one site (`scripts/ui_server.py:5654`) — equivalent only because the client always sends an integer; a client bug sending a numeric string would behave differently at the two sites.
- `last_counter_reply` is sometimes read with `.strip()` (implying a string) and stored into `state_update` from `_counter_reply`, which is not guaranteed to be a string in every code path (some answer-source functions could theoretically return a non-string first tuple element) — labelled here as a risk, not confirmed as an active bug.

These are documented as **maintenance risks**, per the writing requirements: they have not been shown to cause incorrect production behaviour at the baseline, but a future change to any of the surrounding logic should treat truthiness-dependent fields as fragile.

---

## 16. State invariants

### 16.1 Enforced state invariants

Only rules with structural and/or behavioural test enforcement are listed here.

**SINV-1: `recent_persona_replies` is capped at three entries.**
Enforced by the literal slice `(_recent_persona_replies + [_counter_reply])[-3:]` at the single write site (`scripts/ui_server.py:11826`); there is no other write path for this field.
*Tests:* `test_stale_answer_loop_regression.py`, `test_e4_topic_handoff.py` (round-trip wiring).

**SINV-2 (scoped this revision): normal learner-profile updates routed through `apply_updates()`/`save()` are restricted to the six canonical `LEARNER_MEMORY_KEYS`.**
Enforced by `validate_updates()`, which drops any key not in `LEARNER_MEMORY_KEYS` before it reaches `apply_updates()` or `save()`. This invariant applies specifically to the normal capture→apply_updates→save pipeline for canonical facts; it is not a claim about every code path that touches a `learner_id`-keyed dict. The auxiliary-metadata attempt (`partner_facts_seen`) is affected as a *side effect* of this same restriction inside `save()` — see Section 8 — but SINV-2 is stated here only for its intended scope (canonical learner-profile facts).
*Enforcement:* `scripts/learner_memory.py:37–46` (`validate_updates()`); the same restriction re-appears, not by original design intent but as an evidenced side effect, inside `save()`'s merge comprehension (`scripts/learner_memory.py:118`) and `_load_file()`'s normalisation (`scripts/learner_memory.py:75`).
*Known related gaps:* `job_company` extraction exists but is silently dropped at `validate_updates()` (Section 8, Section 19) — the invariant working as designed, applied to a field never added to the allowed set. `partner_facts_seen` is dropped one layer later, inside `save()`'s merge, which appears to be an unintended consequence of the same key-restriction pattern rather than a deliberate application of SINV-2 to auxiliary metadata (Section 8).

**SINV-3: The server is authoritative for persistent learner memory; the client never supplies it as trusted input.**
Enforced structurally: no code path in `/api/run_turn` reads a `learner_memory` key from the incoming request payload; the field only appears in the *response*.
*Tests:* `test_clear_memory_regression.py::TestFactsDoNotSurviveClear`, `TestPersonaFactsUnaffected`.

**SINV-4 (R2 — now an enforced end-to-end invariant, not server-side only): The E4 handoff *value* is computed and written exclusively through `state_update.current_engine`, after frame selection, on the server, and is applied by the client on both call paths for the following request.**
Server side enforced by the fixed line ordering: computation at `scripts/ui_server.py:10296–10313`, write at line 11835, after all frame-selection code paths. Client side, as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`, the primary Pattern-A path (`_runTurnInner()`) applies it via `window._currentEngineId = _resolveNextEngineId(engineId, data.state_update)` as the function's last statement (Section 4); `runMirrorTurn` (Pattern B) applies it as before. At the original baseline, this invariant was enforced server-side only — the client did not apply this value in the primary turn-advancing path (documented as SIC-6, now resolved; see Section 16.2).
*Tests:* `test_e4_topic_handoff.py::TestE4DirectPersonaHandoff` — a **static source-string assertion** against `scripts/ui_server.py` (`assert 'response["state_update"]["current_engine"] = _e4_engine_handoff' in src`); covers the server-side write only, not client consumption. `tests/verify_e4_client_handoff.js` — executes the real, extracted `_resolveNextEngineId` helper and statically asserts its call-site position inside `_runTurnInner()`. `tests/test_e4_client_handoff_regression.py` — a real two-turn `/api/run_turn` integration test proving the following request carries the redirected engine.

**SINV-5 (narrowed this revision): within ordinary ladder/bridge candidate selection, `recent_frame_ids` excludes recently-shown frames from being re-selected.**
Enforced by `fid not in recent` membership checks in `_select_next_frame_ladder`, `_select_next_frame_ladder_avoiding`, and related selector functions — but only for the *ordinary* candidate-selection code paths these functions cover. This is not an unconditional "a frame in `recent_frame_ids` can never be returned again" guarantee: explicit clarification, retry, override, or direct-frame-selection paths (e.g. the noisy-location clarify override that deliberately repeats the same location frame across escalation levels, Section 11) can and do intentionally reuse a frame that is present in `recent_frame_ids`, because they bypass the ladder/bridge selector entirely rather than being subject to its exclusion check.
*Tests:* `test_conversation_first_wave.py` (frame-selection coverage) — covers the ordinary-selection exclusion, not the intentional-reuse exceptions.

**SINV-6 (R2 — engine-authority wording, now a complete end-to-end state path): the client may only client-initialise `current_engine` before any server response exists; after that, the client must not independently *infer* a semantic engine change, and both server-produced engine fields are now applied on the primary path.**
After the first turn, two server-produced response fields carry engine information with different meanings: the top-level `engine_id` identifies the engine of the frame returned in *this* response; `state_update.current_engine`, when present, identifies the engine that should become active for the *following* request (the E4/direction-stub handoff). Both are produced by the server; the client is not expected to derive either independently. Enforced by the fallback chain (`window._currentEngineId ?? ... ?? "identity"`) being consulted *only* when no server-set value exists yet. As of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`, `current_engine` is a complete end-to-end state path: `data.engine_id` governs current-frame attribution and `data.state_update.current_engine` (via `_resolveNextEngineId`) governs the following request's engine, on both the primary Pattern-A path and Pattern B. At the original baseline, this invariant held only in the narrow sense that the client never computes an engine transition from its own heuristics — the primary Pattern-A path applied only `engine_id`, not `state_update.current_engine` (SIC-6, now resolved).
*Tests:* `tests/verify_e4_client_handoff.js`, `tests/test_e4_client_handoff_regression.py`. Note: `test_conversation_first_wave.py::test_active_turn_record_single_source_of_truth` was previously cited here in error — it covers active English/gloss synchronisation for the transcript's active turn, not engine-state application, and exercises neither `window._currentEngineId` nor `_resolveNextEngineId`.

**SINV-7: Clearing learner memory removes stored facts unconditionally rather than merging `None` values.**
Enforced by `clear()` bypassing `save()`'s merge logic entirely and writing `empty_memory()` (all `None`) directly to `_store` and disk.
*Tests:* `test_clear_memory_regression.py::TestLearnerMemoryClear`, `TestSaveStillWorks`, `TestResetMemoryEndpointWiring`.

### 16.2 Intended contracts with known enforcement gaps

**SIC-1 (Mirror-confusion escalation should persist across turns): the mirror confusion ladder should advance from one turn to the next based on the learner's continued confusion.**
In the baseline, `last_mirror_topic`, `last_mirror_engine`, and `mirror_confusion_count` are mutated only within the current server request's local `cs` dict and are never included in the client's `conversation_state` payload nor written to `state_update` (except a reset-to-0 on confirmed re-ask). The escalation *functions* exist and are individually correct, and are exercised by tests that inject these fields directly — but the production client cannot actually drive multi-turn escalation because it never sends the fields back.
*Partial enforcement:* within a single request, the ladder logic is correct; cross-request persistence is not implemented.
*Tests covering the mechanism in isolation:* `test_stale_counter_reply_loop.py`.

**SIC-2 (Noisy-location and destination-clarify state should round-trip): `location_retry_count`, `location_clarify_hint`, and `pending_dest_candidate` are written by the server to guide the *next* turn's behaviour, but the client does not currently merge any of the three back into `conversation_state`.**
*Partial enforcement:* server-side write and read logic is internally consistent for a single request; the intended cross-request signal does not currently reach the server on the following turn because the client never resends it.
*Known gap, no dedicated regression test found for the round-trip itself* (the noisy-location *within-request* escalation is covered; the cross-request persistence is not).

**SIC-3 (Repair-escalation counters should be visible to the client): `repair_attempt_count`'s computed escalation level, and `consecutive_not_understood`, are read/derived server-side but the client only ever receives a reset-to-zero, never the live value, and the client does not send `consecutive_not_understood` at all.**
*Partial enforcement:* the server-side `max()` combination still works because `recent_confusion_count` (which *is* round-tripped) contributes to the same `max()`, so escalation is not completely broken — but the ladder is less accurate than if all three inputs were genuinely live.

**SIC-4 (Persona switch should have well-defined effects on conversation state): switching personas mid-session currently clears only reveal-tracking dictionaries, leaving `current_engine`, `recent_frame_ids`, `recent_persona_replies`, and all counters untouched.**
Whether this is desired (continuity of conversational arc across a persona swap) or a gap (a new persona inheriting the old persona's dedup/working-memory history) is not resolved by the code — it is documented here as an intended-but-unspecified contract, not a bug, pending a product decision.

**SIC-5 (`job_company` should persist if it is going to be extracted at all): the extraction logic for this field exists and is invoked, but the field is not in `LEARNER_MEMORY_KEYS`, so every extraction is silently discarded.**
*No enforcement; no test found asserting either behaviour deliberately* — this reads as an incomplete feature rather than an intentional exclusion, since the read site at `scripts/ui_server.py:9707` implies the field was expected to be populated.

**SIC-5b (`partner_facts_seen` should persist cross-session if it is going to be written at all, verified this revision): `scripts/ui_server.py:12378–12383` writes a `partner_facts_seen` entry into a locally-loaded memory dict and calls `save()`, but `save()`'s merge comprehension is restricted to `LEARNER_MEMORY_KEYS` and silently discards the extra key before it reaches `_store` or disk (Section 8).**
*No enforcement; no test found asserting either behaviour deliberately.* The inline comment and surrounding structure indicate cross-session persistence was intended, making this an incomplete feature rather than an intentional exclusion — the same classification as SIC-5, but caused one layer later in the pipeline (save-merge time rather than update-validation time).

**SIC-6 — RESOLVED in commit `3be0315b2c9f7316b03ac2183a887f602ae9a297` (retained here for historical traceability only; this is no longer an open gap).** At the original baseline (commit `53584cee9e8c892ff77f12741d1fc89d9d09c7e7`), this entry documented that the server always writes `state_update.current_engine` when the handoff condition is met, but the client's primary Pattern-A response handler (`ui/app.js:6869–6920`, used for ordinary "Next" turns) never read `data.state_update.current_engine` — only `runMirrorTurn` (Pattern B) did. That gap is closed: `_runTurnInner()` now calls `window._currentEngineId = _resolveNextEngineId(engineId, data.state_update)` as its last statement, after all current-frame bookkeeping (Section 4, Section 8.4 of `CONVERSATION_ARCHITECTURE.md`). This is now covered by executable regression tests, not merely a static source-string check: `tests/verify_e4_client_handoff.js` (real-helper unit tests plus static wiring/position assertions) and `tests/test_e4_client_handoff_regression.py` (a real two-turn `/api/run_turn` integration test proving the following request carries the redirected engine). `test_e4_topic_handoff.py` remains a static source-string check covering only the server-side write (SINV-4) and was not changed by this fix. See SINV-4, SINV-6 (Section 16.1) for the corresponding enforced-invariant wording, and Section 10 for the updated transition-timeline example.

**SIC-7 (`window._lastCounterReply` and `window._recentReactions` should be cleared or explicitly retained by design when a new session starts, verified this revision): `_resetCurrentSessionState()` contains no assignment for either global, so a same-tab "Start new session" leaves both at whatever value the previous session last set, while a full browser reload does reset them (to script-load defaults) as an incidental side effect of the page reinitialising, not because any reset function targeted them.**
*No enforcement; no test found asserting either the leak or a deliberate carry-over is intended.* Whether same-tab retention is acceptable (e.g. because these are dedup aids rather than semantically significant counters) or should be added to `_resetCurrentSessionState()` is not resolved by the code — documented here as an intended-but-unspecified contract, in the same category as SIC-4, pending a product decision (Section 5.1, Section 7, Section 13, Section 20).

Every invariant and intended contract above is backed by the line-level evidence cited. Distinguishing what this document treats as speculative from what it treats as evidenced: every SIC above is an *observed* gap between two pieces of code that were directly read (a write site and the corresponding absence of a read site, or a merge restriction directly traced through). Section 19 separately lists broader *structural exposures* — risks inferred from the shape of the system (e.g. lack of schema versioning) rather than from a specific traced code gap — and that distinction is preserved there rather than blurred into this section.

---

## 17. State transition examples

**1. Ordinary answer and ladder advance.**
Incoming: `current_engine="identity"`, `recent_frame_ids=["f_ask_you_name"]`, `last_answer={frame_id:"f_ask_you_name", submitted_text:"我叫小明"}`. Turn-local: answer captured into `learner_memory["learner_name"]="小明"` via `capture_from_turn`; no question asked, so E4 does not fire — no `current_engine` handoff is written to `state_update` this turn. Response: `frame_id="f_id_friends_call"`. Routine `state_update` fields may still be present depending on which write sites fired this turn (e.g. `discovery_shown_last_turn`, `last_persona_reveal`, and similar post-trigger-block fields are written on most turns per Section 6, regardless of whether the turn was an answer or a question) — this example does not claim `state_update` is empty, only that it carries no engine change. Client: appends new frame_id to `recent_frame_ids`, sends the updated list next turn, and merges whichever `state_update` fields (if any) it has a case for (Section 6).

**2. Direct persona question with deferred E4 handoff — server side is well-evidenced; the client now applies the handoff end to end on both call paths (updated this revision, R2).**
Incoming: `current_engine="identity"`. Learner asks "你去过成都吗？" (a travel question), typed or spoken as an ordinary turn — this is a Pattern-A (`_runTurnInner`) request, not a `runMirrorTurn` (Pattern-B) mirror-button action. Turn-local: `user_asked_question=True`; `_direct_persona_answer()` produces a confident answer; `_infer_question_topic_engine()` classifies it as `"travel"`; `_e4_engine_handoff="travel"`. Response: `frame_text` still selected from `"identity"` (frame selection ran before the E4 write); `state_update.current_engine="travel"` is written by the server. **Client (current-frame bookkeeping):** renders the identity-engine frame alongside the travel answer; every use of `engineId`/`window._currentEngineId` for *this* response's rendering, active-turn recording, and diagnostics uses `data.engine_id` (`"identity"`) — client current-frame attribution: `"identity"`, unchanged by this fix. **Client (next-request resolution, last statement of `_runTurnInner()`):** `window._currentEngineId = _resolveNextEngineId("identity", data.state_update)` returns `"travel"` because `state_update.current_engine` is a valid non-empty string — client future engine after helper: `"travel"`. Next request: `conversation_state.current_engine="travel"`; the server selects the following frame from `"travel"`. If the same question were instead asked through the dedicated mirror-question UI action (`runMirrorTurn`, Pattern B), the client applies `state_update.current_engine` via its own separate, pre-existing merge (`ui/app.js:6246–6249`, unmodified by this fix) and reaches the same `"travel"` outcome. **Historical note:** at the original baseline (commit `53584cee9e8c892ff77f12741d1fc89d9d09c7e7`), the Pattern-A response handler had no read site for `data.state_update.current_engine` at all, so the next request retained `"identity"` indefinitely on this call path (documented as SIC-6, now resolved in commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`; see Section 16.2).

**3. Stale-answer deduplication using recent persona replies.**
Incoming: `recent_persona_replies=["我去过成都，很好玩"]`. Learner re-asks essentially the same question. Turn-local: the candidate answer text matches an entry in `recent_persona_replies`; `_dedupe_persona_answer()` re-picks an alternative from the same-intent pool (a different Chengdu fact) rather than repeating the stale line. Response: `counter_reply` is the alternative; `state_update.recent_persona_replies` becomes the old list plus the new reply, capped to the last 3.

**4. Client-intercepted spoken recovery.**
Learner says "再说一遍" via microphone. Client: `matchSpokenRecoveryPhraseExact()` matches action `repeat`; the client replays the current frame's TTS locally. **No `/api/run_turn` request is sent** — this is the scoped, verified claim: there is no server request, and consequently no semantic engine/frame-state progression (`current_engine`, `frame_id`, `recent_frame_ids`, and every `conversation_state` counter remain exactly as they were, since nothing that would change them ran). This does **not** mean nothing on the client changes at all: UI state (e.g. transcript rendering, TTS playback state), transcript entries, challenge-help/recovery-panel display state, and analytics/diagnostic counters (e.g. `_tracker` recovery-use counts, if this path increments one) may still change locally as a direct result of handling the recovery action, even though none of that reaches the server or the next request's semantic routing state.

**5. Server-side typed recovery.**
Learner types "什么意思" instead of speaking it (bypassing client interception). Request: normal `conversation_state`, `last_answer={frame_id: <current>, submitted_text:"什么意思"}`. Turn-local: `_is_meaning=True`; `_meaning_recovery_reply()` produces `counter_reply`; normal frame selection then runs and **does** advance to a new `frame_id`. Response: `counter_reply` is the rephrase; `frame_id` is a new question, not a repeat.

**6. Learner-memory capture of a structurally extracted location.**
Learner answer: "我现在住在达尼丁" on a residence-asking frame. Turn-local: `_extract_open_world_location()` matches the `"我现在住在"` prefix, extracts `"达尼丁"`; `capture_from_turn()` maps this frame to the `lives_in` key; `_lm_apply_updates()` merges `{"lives_in": "达尼丁"}` into the loaded memory dict; `_lm_save()` persists it, preserving all other fields via `save()`'s merge rule. Response: no `conversation_state` field changes as a direct result (`learner_stated_location`, the *session-scoped* echo of this fact, is separately set in `state_update` for in-session slot substitution — distinct storage from the persistent `lives_in` key).

**7. Clear-memory operation.**
Learner clicks "Forget conversation." Client: `startFreshLearner()` — POSTs `/api/reset_memory` with `{learner_id: window._learnerId}`. Server: `_lm_clear(learner_id)` sets all six learner-memory keys to `None` and rewrites `data/learner_memory.json`. Client (regardless of the POST's success/failure being awaited loosely): calls `_resetCurrentSessionState()` (all session counters/history to defaults) and explicitly clears `window._lastMentionedPlace`. Not touched: progress snapshots, `localStorage["manos_progress_history"]`, `learner_id` itself.

**8. Persona switch.**
Learner clicks a different persona button mid-conversation. Client: `window._partnerId` updated to the new persona's ID; `window._revealedVoiceLines={}`; `window._revealedPartnerFacts={}`; partner-header display cleared and repopulated. Not touched: `current_engine`, `recent_frame_ids`, `recent_persona_replies`, any counter, `learner_id`. The next `/api/run_turn` request will carry the new `persona_id` but the *same* engine/history state as before the switch (SIC-4, Section 16.2).

---

## 18. Extension and change rules

**Adding a `conversation_state` field.** Requires: a producer in `ui/app.js` (decide which of Patterns A/B/C/D need it — most new selector-relevant fields belong only in Pattern A); a consumer read in `scripts/ui_server.py` with an explicit default (never assume the field is present, since Patterns B/C/D and any pre-baseline client would omit it); an initialization default in both the relevant `window._*` global and inside `_resetCurrentSessionState()`; a decision on whether `_resetCurrentSessionState()` should clear it; a decision on whether it survives a persona switch; and, if the field should influence routing decisions rather than just be transported, an explicit test asserting the read default and the routing behaviour it gates.

**Adding a `state_update` field.** Requires: a server-side write site with an explicit condition (never write unconditionally unless the field is genuinely always meaningful); a client-side merge handler (`ui/app.js` around the `state_update` application block) that assigns it to the correct `window._*` global; a decision recorded in this document about whether omission means "unchanged" (the default assumption used throughout this contract) or something else, if a genuine exception is intended; and a test asserting the round-trip (server writes it under condition X, client applies it to global Y).

**Changing a default.** Requires updating the default in *every* place it is independently coded — this codebase does not share a single default-definition site between `ui/app.js` initialisation, `_resetCurrentSessionState()`, and `scripts/ui_server.py`'s read-time coercion (`... or <default>`). A change to one without the others reintroduces exactly the kind of inconsistency catalogued in Section 15.

**Changing a field's type.** Requires auditing every read site for type-specific coercions (`int(...)`, `list(...)`, `.strip()`, `is True`) — a type change (e.g. a counter becoming a list of per-category counters) will silently misbehave at any site still using the old coercion rather than raising an error, per the truthiness risks in Section 15.

**Changing persistence semantics** (e.g. adding a new learner-memory field, or changing `save()`'s merge rule). Requires updating `LEARNER_MEMORY_KEYS`, `validate_updates()`, the migration function if old data needs reconciling, and — critically — re-verifying the missing/`None`/empty-string/explicit-deletion distinctions in Section 8 still hold, since they are easy to violate silently.

**Adding a reset operation.** Requires adding it to the reset matrix in Section 13, explicitly deciding what it clears vs. preserves relative to the five existing operations, and adding a negative test (asserting what it does *not* touch) alongside a positive test — the existing test suite for reset operations (`test_session_start_reset.py`, `test_clear_memory_regression.py`) is built almost entirely around negative assertions ("does not clear X"), which is the pattern to follow.

**Moving ownership between client and server** (e.g. making the server authoritative for a counter currently client-owned). Requires: the server must begin writing the field to `state_update` on every turn (not just on change) if the client is to stop independently incrementing it; the client must stop incrementing its own copy and only apply the server's value; and every place that currently reads the client-supplied value server-side must be re-audited, since the server previously trusted the client's copy and may have compensating logic that assumed client-side drift was possible.

**Adding a field only to the server or only to the client is incomplete** — a server-only field that is never read from `cs` may still affect the *current* request wherever else it is read (e.g. a debug echo, or a different in-request use), but it cannot influence any *later* request unless it is both transported (written to `state_update` and, on the following turn, resent in `conversation_state`) and consumed (given a client-side merge case, as Section 6 catalogues field-by-field). A client-only field that is never read server-side is dead weight and risks being confused with a field that *is* consumed. Every new field requires evidence of both a producer and a consumer, for the specific cross-turn direction intended, before it is considered complete.

---

## 19. Known risks

- **Distributed state across dozens of browser globals with no single schema.** `ui/app.js` maintains well over 60 `window._*` globals related to conversation state, spread across at least four different `conversation_state` object-literal construction sites (Section 5). There is no TypeScript interface, JSON Schema, or single factory function that defines "what a valid `conversation_state` looks like" — this document is, at the baseline, the only such artifact, and it is documentation, not enforcement.
- **No single machine-readable schema for `conversation_state`.** Consequently, a typo in a field name on either side (client sends `learer_id`, server reads `learner_id`) would fail silently — the field would simply always appear absent to the server, with no validation error.
- **Implicit merge semantics that differ by field.** Some `state_update` fields replace, some conditionally keep-previous-if-no-new-value, some increment, and omission always means "unchanged" — but this is a convention inferred from reading the code, not an enforced contract (Section 6).
- **Duplicated defaults.** The same default value (e.g. `0`, `""`, `[]`) is independently hard-coded in at least three places per field (client init, client reset, server read-time coercion) with no shared constant, as noted in Section 18.
- **Client-held authoritative-transport state.** The client is the sole holder of most `conversation_state` between requests; if the browser tab is closed or crashes mid-session, that state is unrecoverable — there is no server-side session cache to fall back to.
- **Stale browser state after deployment.** Because `conversation_state` shape is defined by whatever `ui/app.js` build the browser currently has loaded, a mid-session deployment that changes a field's meaning (not just adds a field) could cause an already-open tab to send an old-shaped payload to a new server build. This has not been observed to cause an incident at the baseline but is a structural exposure given the lack of versioning on the `conversation_state` shape.
- **Persistent memory and session reset are genuinely separate operations,** by design (Section 13) — but this means a developer unfamiliar with the distinction could reasonably assume "reset session" also clears learner facts, or vice versa, and introduce a regression by conflating them. This has happened before (the clear-memory regression referenced throughout Section 8 and covered by `test_clear_memory_regression.py`).
- **Large, single coordinator function mutating related state at distant points.** The `/api/run_turn` handler in `scripts/ui_server.py` spans roughly 3,460 lines (8961–12424) with related reads/writes to the same conceptual field (e.g. `location_retry_count`) separated by thousands of lines. This makes it easy to add a new write site for a field without noticing an existing one, or to change a read-time default without finding every other read-time default for the same field.
- **`state_update` field consumption is call-path-dependent in a way that is easy to miss.** `ui/app.js` has more than one response-handling function that merges `state_update` (the Pattern-A handler and `runMirrorTurn`), each with its own independent, hand-written set of field cases. A field added to one path's merge block is not automatically available to the other. This was the direct cause of the `current_engine` gap (SIC-6, resolved in commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`) and remains a structural precondition for the same kind of gap recurring with any future `state_update` field — the fix closed this one instance, not the general risk.
- **A comment describing intended behaviour previously disagreed with the verified implementation; this is now resolved for `current_engine` specifically.** The E4 write site's comment (`scripts/ui_server.py:11830–11832`) states that writing `current_engine` into `state_update` "causes the client to track this engine for the next `/api/next_question` call." At the original baseline, the verified client code did not do this for the Pattern-A call path the comment appears to describe (SIC-6); as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297` it does. The general risk named here — that comments in this codebase describe *intended* behaviour and should not be relied upon as evidence of *verified* behaviour without checking the corresponding client code directly — still stands for any other comment making a similar claim.

The items above are not uniform in kind, and this document distinguishes them deliberately rather than presenting all of Section 19 as equally certain:

- **Observed, directly-evidenced defects/gaps** — traced by reading a specific write site and finding no corresponding read site, or vice versa: the `job_company` and `partner_facts_seen` dead-ends (Section 8), the mirror-confusion and location-clarify round-trip gaps (Section 11, SIC-1/SIC-2), and the `window._lastCounterReply`/`window._recentReactions` same-tab leakage (SIC-7). The `current_engine`/Pattern-A consumption gap (formerly SIC-6) was in this category at the original baseline; it is resolved as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297` (Section 4, Section 6, Section 16.2) and is retained in this list's history only for traceability.
- **Inferred structural exposures** — risks that follow from the *shape* of the system (no schema, no versioning, a single 3,460-line handler) rather than from a traced concrete failure: the "stale browser state after deployment" and "large single coordinator function" items below. These have not been shown to have caused an incident at the baseline; they are named because the structural precondition for one is evidenced, not because an occurrence was observed.

Every item, in either category, is backed by the evidence already cited in Sections 5–16 — none are included on pure speculation with no code-level basis — but "backed by evidence" does not mean "confirmed to have caused a production defect." Treat the first category as things to verify/fix; treat the second as things to keep in mind when making a related change.

---

## 20. Regression diagnosis guide

**Engine unexpectedly reverting to a previous topic (or an E4 handoff appearing to have no effect at all).**
Check, in order: (1) is E4 actually firing for the question in play? `_infer_question_topic_engine()` returns `None` for unclassifiable questions, and E4 does not fire if `_counter_result` is `None` or the answer is a generic deflection (`CONVERSATION_ARCHITECTURE.md` §8.3). Verify `response.state_update.current_engine` is present in the network response for the turn that should have redirected. (2) **Which client call path handled this response?** As of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`, both call paths apply the handoff: for `_runTurnInner`'s Pattern-A flow (ordinary "Next" turns), the last statement of the function is `window._currentEngineId = _resolveNextEngineId(engineId, data.state_update)`, and for `runMirrorTurn` (Pattern B), the merge at `ui/app.js:6246–6249` applies `state_update.current_engine` directly. If the following request still carries the pre-handoff engine on either path, this is now a **regression**, not expected baseline behaviour (unlike at the original baseline, where the Pattern-A absence was a documented, evidenced gap — SIC-6, resolved). Confirm `_resolveNextEngineId` is still called, and still called *last*, in `_runTurnInner()`; run `node tests/verify_e4_client_handoff.js` to check the wiring quickly.

**E4 handoff not appearing on the next request.**
First determine which call path produced the response per the check above. For `runMirrorTurn` (Pattern B) responses: confirm the *following* request's `conversation_state.current_engine` matches what was written to `state_update` on the prior turn — if it does not, the bug is in the client's apply step (`ui/app.js:6246–6249` region), not in the server's E4 computation. For Pattern-A responses (the main "Next" flow): confirm the same for `_resolveNextEngineId(engineId, data.state_update)`'s result — as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`, an absence here is a regression against the E4 mechanism as commented in `scripts/ui_server.py` ("Writing current_engine into state_update causes the client to track this engine for the next /api/next_question call"), which now correctly matches verified client behaviour on both call paths; it should be treated as a bug to fix, not a documented gap. `tests/test_e4_client_handoff_regression.py` reproduces this exact two-turn scenario and is the fastest way to confirm or rule out a regression.

**Persona answer repeating despite deduplication.**
Check whether `recent_persona_replies` in the request actually contains the prior reply — if the client failed to replace its copy from the previous `state_update`, the server has no way to know the reply was already given. Also check whether the same-intent answer pool for that fact is exhausted (in which case a fallback clarification, not a repeat, should appear — if a literal repeat appears instead, the pool-exhaustion fallback path itself may be broken).

**Learner fact missing after restart.**
Confirm `MANDARINOS_DATA_DIR` resolves to the same path before and after restart (a misconfigured environment variable pointing at an ephemeral volume would explain data loss that looks like a code regression). Separately, confirm the fact was ever actually in `LEARNER_MEMORY_KEYS` — a fact that only ever populated a non-canonical key (like the `job_company` gap in Section 8) was never persisted in the first place.

**Cleared fact reappearing.**
Check whether the "clear" was implemented via `save()` with `None` values instead of `clear()` — per Section 8, `save()`'s merge semantics mean a `None` value never overwrites an existing non-`None` value on disk, so a from-scratch "clear" that uses `save()` instead of `clear()` will silently fail to erase anything.

**New session retaining old conversation context.**
Confirm `_resetCurrentSessionState()` was actually invoked (check for the "Start" button handler or `startFreshLearner()` call in the code path that led to the new session) rather than the page simply continuing to run with stale `window._*` values from a previous conversation that was never formally reset. Separately: if the stale value specifically involves `window._lastCounterReply` or `window._recentReactions`, this is **expected** even after a correctly-invoked `_resetCurrentSessionState()` — neither field is assigned by that function (SIC-7, Section 16.2), so a same-tab new session legitimately carries them over from the previous session; only a full page reload clears them. Do not treat this specific pair as evidence that the reset function itself is broken.

**Persona switch using the previous persona's reply history.**
This is expected baseline behaviour per SIC-4 (Section 16.2), not a bug — `recent_persona_replies` and `current_engine` are not cleared on persona switch. If this is undesirable for a given feature, it requires an explicit product decision and code change, not a "fix" to existing behaviour.

**Client state differing from server response.**
Diff the fields in `response.state_update` against what `window._*` shows immediately after the response resolves. If a field is present in `state_update` but not reflected client-side, check the client's merge block for a missing case — Section 6 lists the six fields *known* not to be merged back by the production client at all (`pending_dest_candidate`, `location_retry_count`, `location_clarify_hint`, `mirror_confusion_count`, `consecutive_not_understood`, and `recent_confusion_count`'s reset specifically). `current_engine` is no longer on this list as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297` — it is consumed on both the Pattern-A path (via `_resolveNextEngineId`, applied to the *next* request's `window._currentEngineId`, not the current one) and Pattern B (`runMirrorTurn`). A missing-merge bug for any field not among the six listed above is a genuine regression, not an expected gap.

**Recent frame unexpectedly repeating.**
Check whether `recent_frame_ids` client-side actually contains the frame in question — remember the cap is 50, so a very long session could have rolled the offending frame out of the window entirely, which is expected, not a bug. If the frame is still within the last 50 and still got re-selected, the bug is in the ladder-selection exclusion logic, not in state transport.

**Progress reset when learner memory is cleared.**
There is no dedicated state invariant in Section 16.1 asserting this; the claim is attributable specifically to (a) the current implementation of `startFreshLearner()` and `/api/reset_memory`, neither of which contains a progress-clearing call, and (b) the negative tests in `test_clear_memory_regression.py`/`test_session_start_reset.py` that assert the absence of such a call. If this behaviour is observed to break, check whether a code change accidentally added a progress-clearing call inside either function, since neither is currently supposed to touch progress state — but note this is an implementation characteristic under test coverage, not an enforced architectural invariant that would be violated by construction.

---

## 21. Related documents

- [`CONVERSATION_ARCHITECTURE.md`](./CONVERSATION_ARCHITECTURE.md) — routing, answer-source, and selector architecture that this document's state fields serve.
- `ANSWER_SOURCE_CONTRACT.md` (not yet created)
- `ASR_PIPELINE.md` (not yet created)
- `ARCHITECTURE.md` (referenced; not verified as part of this investigation)
- `TEST_STRATEGY.md` (referenced; not verified as part of this investigation)
- `CHANGE_CHECKLIST.md` (referenced; not verified as part of this investigation)
- `ARCHITECTURAL_DECISIONS.md` (referenced; not verified as part of this investigation)
- `PRODUCT_PHILOSOPHY.md` (referenced; not verified as part of this investigation)
- repository-root `AGENTS.md` (referenced; not verified as part of this investigation)

---

## Appendix A — Traceability

| State area | Producer | Storage/transport | Consumers | Reset path | Representative tests |
|---|---|---|---|---|---|
| Full `conversation_state` (Pattern A) | `ui/app.js:_runTurnInner(true, opts)` | Round-tripped every `/api/run_turn` call | `scripts/ui_server.py` main selector block (8961–12424) | `_resetCurrentSessionState()` | `test_conversation_first_wave.py` |
| `state_update` | `scripts/ui_server.py`, scattered write sites | Conditionally present in response (only when a write site fires); of the 20 possible fields, 14 have a client merge case in the Pattern-A path as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297` (Section 6) | `ui/app.js` state-update merge block (6882–6919) plus `_resolveNextEngineId` call, Pattern A; `runMirrorTurn` (6246–6249), Pattern B, has a separate merge case for `current_engine` | Overwritten each turn for fields that are re-written; unconsumed fields have no client-side lifecycle at all | `test_e4_topic_handoff.py` (server-side static check); `tests/verify_e4_client_handoff.js`, `tests/test_e4_client_handoff_regression.py` (client-side `current_engine` consumption) |
| E4 engine handoff | `scripts/ui_server.py:10296–10313` (compute), `:11835` (write) | `state_update.current_engine` | `ui/app.js` `runMirrorTurn` (`window._currentEngineId`, `:6246–6249`), and, as of commit `3be0315b2c9f7316b03ac2183a887f602ae9a297`, the main Pattern-A response handler via `_resolveNextEngineId`, called as the last statement of `_runTurnInner()` (formerly not consumed there at all — SIC-6, now resolved; Section 4, Section 6, Section 16.2) | N/A — recomputed each qualifying turn on the server; client-side pickup now occurs on both call paths | `test_e4_topic_handoff.py::TestE4DirectPersonaHandoff` (server-side static string check, write only); `tests/verify_e4_client_handoff.js`, `tests/test_e4_client_handoff_regression.py` (client-side application, real two-turn integration) |
| Working memory (`recent_persona_replies`) | `scripts/ui_server.py:11826` | `conversation_state` / `state_update` | `_answer_from_working_memory`, `_dedupe_persona_answer` | `_resetCurrentSessionState()` (`[]`) | `test_stale_answer_loop_regression.py` |
| Persistent learner memory | `scripts/learner_memory.py` (`save`, `apply_updates`, `clear`) | `data/learner_memory.json` (path via `MANDARINOS_DATA_DIR`) | Slot substitution, `_answer_from_working_memory` fallback, response echo | `/api/reset_memory` → `clear()` | `test_clear_memory_regression.py`, `test_learner_memory_migration.py` |
| Persona identity/state | `ui/app.js` persona-button handler; `scripts/ui_server.py:_resolve_persona` | `conversation_state.persona_id`/`partner_id`; `personas/<id>.json` (content) | Answer-generation, discoverable-fact reveal, partner header | Persona switch clears reveal-tracking only | — |
| Frame/engine state | `ui/app.js` (`window._currentEngineId`, `window._recentFrameIds`, `_resolveNextEngineId`); `scripts/ui_server.py` selector | `conversation_state`; `state_update` | Frame selector, bridge logic | `_resetCurrentSessionState()` | `tests/verify_e4_client_handoff.js`, `tests/test_e4_client_handoff_regression.py`. Note: `test_conversation_first_wave.py::test_active_turn_record_single_source_of_truth` was previously cited here in error — it covers active English/gloss synchronisation, not engine-state application. |
| Recovery/confusion state | `scripts/ui_server.py` (`recent_confusion_count`, `repair_attempt_count`, mirror ladder); `ui/app.js` (challenge mode, spoken interception) | Partial — see Section 11 for round-trip gaps | Repair-escalation reply selection, mirror ladder | `_resetCurrentSessionState()`; `_confirmed_re_ask` resets via `state_update` | `test_challenge_recovery.py`, `test_stale_counter_reply_loop.py` |
| Session/progress/analytics | `ui/app.js` (`_tracker`); `scripts/ui_server.py` (`_build_progress_snapshot`, `capability_estimator`) | `/api/end_session`, `data/progress/<learner_id>.json`, `localStorage` | Progress display, capability bands (reporting only) | `_resetCurrentSessionState()` zeroes `_tracker`; progress history explicitly preserved | `test_progress_tracking.py`, `test_progress_store.py` |

**Application baseline commit:** `3be0315b2c9f7316b03ac2183a887f602ae9a297`
**Baseline tag:** `architecture-baseline-2026-07-12-r2`
**Historical baseline (immutable, superseded):** `53584cee9e8c892ff77f12741d1fc89d9d09c7e7` / `architecture-baseline-2026-07-12`
**Source documentation branch:** `docs/architecture-v1`
**Document status:** Candidate v1 — R2 final review — revised against the R2 baseline to close the `current_engine`/Pattern-A client-consumption gap (formerly SIC-6, now resolved: 14 of 20 `state_update` fields consumed, up from 13; six unconsumed fields unchanged), correct the associated invariants (SINV-4, SINV-6) and transition examples, and correct a test misattribution (`test_active_turn_record_single_source_of_truth` was cited for engine-state behaviour in three places; replaced with the new E4 client-handoff regression tests). This is layered on top of the prior revision's corrections to `state_update` ownership/consumption claims, the Pattern-A field count, canonical-vs-auxiliary learner-memory terminology, same-tab reset gaps, persona-domain classification, and restart-persistence qualification, all of which remain unchanged and preserved.
**Last verified date:** 2026-07-12
