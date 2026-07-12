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

**Baseline:** commit `53584cee9e8c892ff77f12741d1fc89d9d09c7e7`, tag `architecture-baseline-2026-07-12`.

---

## 2. State-domain overview

| # | Domain | Owner | Storage | Lifetime | Source of truth | Crosses API? |
|---|--------|-------|---------|----------|------------------|---------------|
| 1 | Turn-local server variables | Server | Python locals inside the `/api/run_turn` handler (e.g. `_counter_result`, `_e4_engine_handoff`) | Single request only | Server (computed fresh each call) | No — never leave the handler except through fields explicitly copied into `response` |
| 2 | Client conversation state | Client (transport), Server (interpretation) | `window._*` globals, assembled into `conversation_state` | One browser session (rebuilt from globals each turn; lost on reload) | Mixed — see Section 3 | Yes — sent every `/api/run_turn` call |
| 3 | Server-generated state updates | Server | `response["state_update"]` | Written once per response; applied once by client | Server | Yes — returned every response, applied before the next request |
| 4 | Working memory | Client (transport), Server (read/derive) | `cs["recent_persona_replies"]`, `last_counter_reply`, `last_partner_frame_text` | One session; capped history | Client-held, server-interpreted | Yes |
| 5 | Persistent learner memory | Server | `data/learner_memory.json` (path via `MANDARINOS_DATA_DIR`), keyed by `learner_id` | Survives sessions, browser reloads, and server restarts | Server exclusively | No — client never sends `learner_memory` as input; server may return it for display |
| 6 | Persona data | Content (static) | `personas/<id>.json`, loaded and cached in `scripts/ui_server.py` | Immutable for the process lifetime (cached) | Content file | No — never sent by client; server reads by `persona_id` |
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
 client applies state_update, top-level
 telemetry fields, and (if present)
 learner_memory display fields to
 window._* — becomes next conversation_state
```

Learner-memory persistence and session capture are **not** part of the `conversation_state` round trip; they are separate subsystems reached through separate endpoints and only surfaced into the `/api/run_turn` response as read-only display data (`response["learner_memory"]`).

---

## 3. State ownership model

**Authoritative owner** — may establish or change the semantic meaning of a value. Example: the server is the authoritative owner of `current_engine` after the first turn (via E4 and other handoffs); the server is the sole authoritative owner of persistent learner memory.

**Transport owner** — holds and round-trips a value on behalf of another party but must not reinterpret it. The client is the transport owner of most of `conversation_state`: it stores counters like `exchange_count`, `same_engine_chain_count`, and `recent_frame_ids` in `window._*` globals and sends them back verbatim each turn, but the server — not the client — decides what those counters mean and how they gate behaviour.

**Derived state** — recomputed from authoritative values rather than stored independently. Example: `_12c_loop_capped`, `_12c_overload`, `_12c_closing` (Section 10, `scripts/ui_server.py` lines 9168–9170) are recomputed every request from `loop_count_in_current_engine`, `recent_confusion_count`, and `exchange_count`; they are never stored or sent anywhere.

**UI state** — controls presentation but carries no semantic conversation meaning. Example: `window._sentenceHint`, `window._currentHintAffordance`, `hint_cascade_state`, DOM element visibility. These never appear in `conversation_state` or `state_update`.

**Persistent state** — survives a normal session boundary. Only persistent learner memory (`data/learner_memory.json`), progress snapshots (`data/progress/<learner_id>.json`), and `localStorage["manos_progress_history"]` qualify. `conversation_state` itself is **not** persistent — it is rebuilt from `window._*` globals on each turn and lost entirely on a browser reload.

**Ephemeral state** — valid only during one request or one browser tab session. Turn-local server variables are request-ephemeral. Most `window._*` counters are session-ephemeral: they exist until `_resetCurrentSessionState()` runs or the tab is closed/reloaded.

**The mixed-ownership pattern.** The client stores and transports the majority of `conversation_state` (counters, history lists, mode flags) but does not have final authority over what those values *mean*. The server reads the client's copy, may derive a corrected or advanced value, and returns that correction through `state_update`. The client is contractually obligated to apply every `state_update` field it receives before assembling the next request; it must not independently recompute values that the server is authoritative for (notably `current_engine` once E4 has fired).

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
9. **Client applies response fields** — merges `data.state_update` into the corresponding `window._*` globals (`ui/app.js:6882–6919`) and separately applies certain top-level response fields (`turn_type`, `same_engine_chain_count`, `arc_state.*`, etc., `ui/app.js:6797–6833`).
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

**E4 as the canonical example of a deferred state update:**

1. Server computes `_e4_engine_handoff` at `scripts/ui_server.py:10296–10313`, *before* frame selection runs.
2. The response's `frame_text`/`frame_id` are selected using the *incoming* `current_engine` (frame selection happens after step 1 but does not consult `_e4_engine_handoff`).
3. Server writes `response["state_update"]["current_engine"] = _e4_engine_handoff` at line **11835**, *after* frame selection and most of payload assembly.
4. Client applies `state_update.current_engine` to `window._currentEngineId` (`ui/app.js:6246–6248`).
5. The *next* request's `conversation_state.current_engine` carries the redirected engine, so the frame selector on the following turn operates in the new engine.

This produces exactly one transitional response (the one carrying the direct answer) whose accompanying frame still belongs to the old engine — an accepted, evidenced baseline characteristic, not a bug (see `CONVERSATION_ARCHITECTURE.md` Section 8).

---

## 5. `conversation_state` contract

The client does not send one fixed shape. There are **four distinct payload patterns** depending on which client function assembles the request:

| Pattern | Call site | `conversation_state` shape |
|---|---|---|
| **A — Full selector state** | `_runTurnInner(true, opts)` → `POST /api/run_turn` with `next_question: true` (`ui/app.js:6628–6717`) | **45 fields** (34 always-present + 11 conditional) — the only pattern the server's main selector block fully consumes |
| **B — Minimal direction/mirror/discovery stub** | `runDirectionTurn`, `runMirrorTurn`, `submitDiscoveryQuestion`, `_showPostCloseMirrorOptions` (`ui/app.js:6137, 6208, 8459, 8971`) | 4 fields: `current_engine`, `recent_frame_ids`, `learner_id`(cond.), `persona_id`(cond.) |
| **C — Probe stub** | `runProbeTurn` (`ui/app.js:6291`) | 5 fields: adds `probe_depth` to pattern B |
| **D — No conversation state** | `_runTurnInner(false, ...)` — initial dropdown-driven frame load | none — sends `frame_id`/`engine_id` directly on the payload root |

Only **Pattern A** is the authoritative full contract. The server's main selector block (`scripts/ui_server.py:9137–9139`) only activates when `next_question: true` **and** `conversation_state` is a dict; Patterns B/C/D route through the direction/probe early-return branches or the frame-dropdown fallback and never touch most of the fields below. Any future change to a field's default **must** account for the fact that patterns B–D will not supply it.

### 5.1 Full field inventory (Pattern A — 45 fields)

| Field | Type | Default (client) | Client source | Server consumer | Mutation rule | Lifetime | Reset behaviour | Representative tests |
|---|---|---|---|---|---|---|---|---|
| `session_id` | string | `"session_" + Date.now()` | `window._sessionId` | Randomness seed for probabilistic gates (e.g. bridge/closing rolls) | Replace at session reset | Session | New value on `_resetCurrentSessionState()` | `test_session_start_reset.py` |
| `current_engine` | string | `"identity"` (first turn only, via fallback chain) | `window._currentEngineId` | Active topic engine for routing/frame selection | Server-authoritative after turn 1 (via `state_update`); client-initialised on turn 1 | Session | Reset to fallback default at session reset | `test_e4_topic_handoff.py` |
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
| `recent_reactions` | array\<string\> | `[]` (no explicit init; `undefined` until first server value) | `window._recentReactions` | Reaction-line dedup | Replace | Session | Not explicitly reset (no assignment in `_resetCurrentSessionState`) | — |
| `medium_probe_fired_engines` | array\<string\> | `[]` | `window._mediumProbeFiredEngines` | At-most-one-medium-probe-per-engine cap | Replace | Session | `[]` on reset | — |
| `pending_listening_move` | bool | `false` | `window._pendingListeningMove` | Listening-move gate | Replace | Session | `false` on reset | — |
| `listening_wait_turns` | int | `0` | `window._listeningWaitTurns` | Listening-move gate | Increment | Session | `0` on reset | — |
| `last_interest_level` | string | `"low"` | `window._lastInterestLevel` | Weak-reply resilience, interest decay | Replace | Session | `"low"` on reset | — |
| `last_user_text` | string | `""` | `window._lastUserText` | Interest/repetition heuristics | Replace | Session | `""` on reset | — |
| `loop_count_in_current_engine` | int | `0` | `window._loopCountInEngine` | LOOP-frame soft-cap arc correction (Section 10) | Increment | Session | `0` on reset | — |
| `engines_visited` | array\<string\> | `["identity"]` | `window._enginesVisited` | Bridge target selection, arc completion | Append | Session | `["identity"]` on reset (not `[]`) | — |
| `recent_confusion_count` | int | `0` | `window._recentConfusionCount` | Overload threshold (`_12c_overload`) | Increment (client); reset by server via `state_update` on repair success | Session | `0` on reset | `test_challenge_recovery.py` |
| `last_counter_reply` | string | `""` (undefined until first `state_update`) | `window._lastCounterReply` | Reply-deduplication guard | Replace (server echoes via `state_update`) | Session | Not explicitly reset (persists as `""`/undefined until next server write) | `test_stale_answer_loop_regression.py` |
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

The server writes **20 distinct fields** into `response["state_update"]`, scattered across the `/api/run_turn` handler rather than assembled in one place. `state_update` itself is initialised lazily (`response["state_update"] = response.get("state_update") or {}`) at the first write site, so its presence in the response is conditional on at least one field being set.

| Field | Set at (approx. line) | Condition | Merge semantics | Client must apply before |
|---|---|---|---|---|
| `current_engine` | 11835 (E4); 9067 (direction-stub) | E4: `_e4_engine_handoff` truthy. Direction: resolved `engine_id` not `"unknown"`/`""` | Replace | Next request |
| `last_counter_reply` | 11824 | `_counter_reply` truthy | Replace | Next request (dedup) |
| `recent_persona_replies` | 11827 | `_counter_reply` truthy | Replace with `(_recent + [reply])[-3:]` (append-then-truncate, computed server-side) | Next request |
| `last_partner_frame_text` | 12091 | Always, in post-trigger assembly block | Replace with stripped `frame_text` | Next request (recovery rephrase source) |
| `last_place_subject` | 12153 | When a place is detected this turn | Replace if new subject found, else keep previous value (merge-like conditional) | Next request |
| `learner_stated_location` | 12135 | Always in post-trigger block | Replace with new extraction, or keep previous | Next request |
| `learner_food_note` | 12147 | Responsive food answer, or keep previous | Replace or keep | Next request |
| `consecutive_app_questions` | 12156 | Only if key not already set earlier in the same response | Replace: `0` if user-led this turn, else incremented value | Next request |
| `discovery_shown_last_turn` | 12089 | Always in post-trigger block | Replace with `bool(user_led)` | Next request |
| `last_persona_reveal` | 12088 | Always when the persona-reveal block runs | Replace | Next request |
| `recently_seen_disc_topics` | 11941, 11981, 12020, 12069 | Discovery path shown this turn | Replace with updated topic pool | Next request |
| `pending_dest_candidate` | 11564 (set), 11568 (clear) | ASR near-match destination clarify frame sets it; otherwise cleared to `None` | Replace (string or explicit `None`) | Next request; **client does not currently merge this field back** (documented gap, Section 11) |
| `location_retry_count` | 11659 (increment), 11612 (reset), 12174 (reset on valid echo) | Noisy-location clarify always increments; participation-escape/valid-echo resets to `0` | Replace (increment or reset) | Next request; **client does not currently merge this field back** |
| `location_clarify_hint` | 11637/11646 (`"active"`), 11657 (`""`), 12164 (`""` on confirmed re-ask) | Escalation-level dependent | Replace (`"active"` or `""` — not boolean) | Next request; **client does not currently merge this field back** |
| `efc_entity` | 11751, 11766 | `{ENTITY}` slot filled or carried forward | Replace (dict) | Next request |
| `efc_depth` | 11752, 11767 | Same as above | Replace: `prior + 1` or carried value | Next request |
| `repair_attempt_count` | 12160 | `_confirmed_re_ask` only | Replace with `0` (reset-only; the escalation value itself is never echoed back) | Next request |
| `mirror_confusion_count` | 12161 | `_confirmed_re_ask` only | Replace with `0` (reset-only) | Next request; **client never sends this field, so the reset has no effect on future requests** (documented gap, Section 11) |
| `recent_confusion_count` | 12162 | `_confirmed_re_ask` only | Replace with `0` | Next request |
| `consecutive_not_understood` | 12163 | `_confirmed_re_ask` only | Replace with `0` | Next request; **client never sends this field** (documented gap) |

**Omission semantics.** For every field in this table, omission from `state_update` means **leave the client's own value unchanged** — the client does not clear a field simply because the server did not mention it that turn. There is no field in this contract where omission is defined to mean "clear."

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
- **What clears working memory:** `_resetCurrentSessionState()` sets `window._recentPersonaReplies = []` and `window._lastCounterReply` is implicitly cleared (no explicit re-init line — it remains `undefined` until first written). Clearing persistent learner memory (`/api/reset_memory`) does **not** clear working memory; they are independent operations (Section 13).

**Why working memory must not persist as learner biography.** Working memory answers *"what did the partner just say?"* for at most three recent turns and is deliberately volatile — it exists to make follow-up questions feel coherent within a conversational arc, not to remember who the learner is across sessions. Persistent learner memory (Section 8) answers *"who is this learner?"* and is the only subsystem intended to survive session boundaries. Conflating the two would mean a transient in-conversation remark (e.g. a passing mention while working memory was populated) could leak into long-term biography, or conversely that genuine biographical facts could be lost the moment the 3-entry window rolls over. The two subsystems are implemented with entirely separate storage, separate clear operations, and separate consumers, and this document treats any code path that blurs them as a defect, not a feature.

---

## 8. Persistent learner-memory contract

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

**Migration rules.** `migrate_corrupted_memory()` (`scripts/learner_memory.py:189–269`) is a one-time cleanup for pre-fix ASR-junk values: place fields are re-normalised via `normalize_place_name()` (unrecoverable values become `None`); non-place fields have known junk fragments stripped. It preserves unrecognised extra keys already present in the file (forward-compatibility) and supports `dry_run=True` for inspection without writing. There is no other version-tagged schema-migration mechanism in the baseline.

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

**Immutable content vs. session-derived state.** Persona profile/voice-lines/discoverable-facts JSON is immutable content, loaded once and cached for the process lifetime. What varies per session is only the *reveal tracking* (`revealed_voice_lines`, `revealed_partner_facts`) and, separately and independently, cross-session "has this fact been shown to this learner" flags stored inside learner memory itself (`_pmem.setdefault("partner_facts_seen", {})...`, `scripts/ui_server.py:12378–12383`) — meaning persona-fact reveal state has **two separate tracking mechanisms**: one session-scoped (client `conversation_state`) and one persisted per learner (inside the learner-memory JSON, outside the six canonical keys).

---

## 10. Frame and engine state

**Three distinct "engine" values that must not be confused:**

| Value | Where | Meaning |
|---|---|---|
| Incoming `conversation_state.current_engine` | Request | The engine the client believes is active *before* this turn's selection runs |
| Response `engine_id` | Response, top level | The engine the frame actually returned in *this* response belongs to (computed from the incoming engine, before any E4 write) |
| `state_update.current_engine` | Response | The engine that should be active *starting next turn* (only present if E4 or a direction-stub handoff fired) |

**Timeline example — deferred E4 handoff across two requests:**

```
Turn N   (learner asks a direct question about travel, while current_engine = "identity")
  request:  conversation_state.current_engine = "identity"
  server:   frame selected from "identity"           → response.engine_id = "identity"
            E4 computes handoff                        → _e4_engine_handoff = "travel"
            E4 writes (after frame selection)          → response.state_update.current_engine = "travel"
  client:   renders an "identity" frame text alongside the direct travel answer;
            applies state_update.current_engine → window._currentEngineId = "travel"

Turn N+1 (any learner input)
  request:  conversation_state.current_engine = "travel"   (now updated)
  server:   frame selected from "travel"              → response.engine_id = "travel"
  client:   sees a "travel" frame — the redirect is now visibly in effect
```

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
| Learner facts (`learner_memory.json`) | Not touched | **Cleared** (`/api/reset_memory` → `_lm_clear`) | Not touched | Not touched (persisted) | Preserved (file survives) |
| Progress snapshots | Not touched | **Explicitly preserved** (tested negatively — no `localStorage.removeItem`, no snapshot deletion call) | Not touched | Preserved | Preserved (file survives) |
| Session identifiers (`session_id`, `_sessionStartedAt`) | Regenerated | Regenerated (calls session reset) | Not touched | Regenerated | N/A |
| Challenge mode (`_challenge.active`) | Not reset (independent toggle) | Not reset | Not touched | Reset to `false` (script default) | N/A |
| Selected persona (`window._partnerId`) | Not touched | Not touched | **Changed** (that is the operation) | Cleared, then re-auto-selected on persona list load | N/A |
| `_revealedVoiceLines` / `_revealedPartnerFacts` | Cleared (`{}`) | Cleared (calls session reset) | **Cleared** (persona-switch handler explicitly resets these) | Cleared (re-init) | N/A |
| `_tracker` counters | Cleared (all zeroed) | Cleared (calls session reset) | Not touched | Cleared (re-init) | N/A |
| `learner_id` | Not touched | **Explicitly preserved** (no ID rotation) | Not touched | Preserved (from `localStorage`) | N/A (server-side key, not process state) |

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

**SINV-2: Learner memory contains only the six allowed keys.**
Enforced by `validate_updates()`, which drops any key not in `LEARNER_MEMORY_KEYS` before it reaches `apply_updates()` or `save()`.
*Enforcement:* `scripts/learner_memory.py:37–46`.
*Known related gap:* `job_company` extraction exists but is silently dropped (Section 8, Section 19) — this is the invariant working as designed, applied to a field that was never added to the allowed set.

**SINV-3: The server is authoritative for persistent learner memory; the client never supplies it as trusted input.**
Enforced structurally: no code path in `/api/run_turn` reads a `learner_memory` key from the incoming request payload; the field only appears in the *response*.
*Tests:* `test_clear_memory_regression.py::TestFactsDoNotSurviveClear`, `TestPersonaFactsUnaffected`.

**SINV-4: The E4 handoff is transported exclusively through `state_update.current_engine`, written after frame selection.**
Enforced by the fixed line ordering: computation at `scripts/ui_server.py:10296–10313`, write at line 11835, after all frame-selection code paths.
*Tests:* `test_e4_topic_handoff.py::TestE4DirectPersonaHandoff`.

**SINV-5: `recent_frame_ids` prevents immediate frame reuse.**
Enforced by `fid not in recent` membership checks in `_select_next_frame_ladder`, `_select_next_frame_ladder_avoiding`, and related selector functions.
*Tests:* `test_conversation_first_wave.py` (frame-selection coverage).

**SINV-6: The first-turn engine may be client-initialised, but later semantic engine changes come from server responses only.**
Enforced by the fallback chain (`window._currentEngineId ?? ... ?? "identity"`) being consulted *only* when no server-set value exists yet; every subsequent read of `current_engine` for routing purposes uses the value most recently written by a server `state_update`.
*Tests:* `test_conversation_first_wave.py::test_active_turn_record_single_source_of_truth`.

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

Every invariant and intended contract above is backed by the line-level evidence cited; none are speculative.

---

## 17. State transition examples

**1. Ordinary answer and ladder advance.**
Incoming: `current_engine="identity"`, `recent_frame_ids=["f_ask_you_name"]`, `last_answer={frame_id:"f_ask_you_name", submitted_text:"我叫小明"}`. Turn-local: answer captured into `learner_memory["learner_name"]="小明"` via `capture_from_turn`; no question asked, so E4 does not fire. Response: `frame_id="f_id_friends_call"`, `state_update={}` (no engine change). Client: appends new frame_id to `recent_frame_ids`, sends the updated list next turn.

**2. Direct persona question with deferred E4 handoff.**
Incoming: `current_engine="identity"`. Learner asks "你去过成都吗？" (a travel question). Turn-local: `user_asked_question=True`; `_direct_persona_answer()` produces a confident answer; `_infer_question_topic_engine()` classifies it as `"travel"`; `_e4_engine_handoff="travel"`. Response: `frame_text` still selected from `"identity"` (frame selection ran before the E4 write); `state_update.current_engine="travel"`. Client: renders the identity-engine frame alongside the travel answer; sets `window._currentEngineId="travel"`. Next request: `conversation_state.current_engine="travel"` — the following frame comes from the travel engine.

**3. Stale-answer deduplication using recent persona replies.**
Incoming: `recent_persona_replies=["我去过成都，很好玩"]`. Learner re-asks essentially the same question. Turn-local: the candidate answer text matches an entry in `recent_persona_replies`; `_dedupe_persona_answer()` re-picks an alternative from the same-intent pool (a different Chengdu fact) rather than repeating the stale line. Response: `counter_reply` is the alternative; `state_update.recent_persona_replies` becomes the old list plus the new reply, capped to the last 3.

**4. Client-intercepted spoken recovery.**
Learner says "再说一遍" via microphone. Client: `matchSpokenRecoveryPhraseExact()` matches action `repeat`; the client replays the current frame's TTS locally. **No `/api/run_turn` request is sent.** No client or server state changes at all — `frame_id`, `recent_frame_ids`, and every counter remain exactly as they were.

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

**Adding a field only to the server or only to the client is incomplete** — a server-only field that is never read from `cs` has no effect; a client-only field that is never read server-side is dead weight and risks being confused with a field that *is* consumed. Every new field requires evidence of both a producer and a consumer before it is considered complete.

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

No speculative risks are included above; every item is backed by the evidence already cited in Sections 5–16.

---

## 20. Regression diagnosis guide

**Engine unexpectedly reverting to a previous topic.**
Check: is E4 actually firing for the question in play? `_infer_question_topic_engine()` returns `None` for unclassifiable questions, and E4 does not fire if `_counter_result` is `None` or the answer is a generic deflection (`CONVERSATION_ARCHITECTURE.md` §8.3). Verify `response.state_update.current_engine` is present in the network response for the turn that should have redirected, and verify the client actually applied it (`window._currentEngineId` after the response, in devtools).

**E4 handoff not appearing on the next request.**
Confirm the *following* request's `conversation_state.current_engine` matches what was written to `state_update` on the prior turn — if it does not, the bug is in the client's apply step (`ui/app.js:6246–6248` region), not in the server's E4 computation.

**Persona answer repeating despite deduplication.**
Check whether `recent_persona_replies` in the request actually contains the prior reply — if the client failed to replace its copy from the previous `state_update`, the server has no way to know the reply was already given. Also check whether the same-intent answer pool for that fact is exhausted (in which case a fallback clarification, not a repeat, should appear — if a literal repeat appears instead, the pool-exhaustion fallback path itself may be broken).

**Learner fact missing after restart.**
Confirm `MANDARINOS_DATA_DIR` resolves to the same path before and after restart (a misconfigured environment variable pointing at an ephemeral volume would explain data loss that looks like a code regression). Separately, confirm the fact was ever actually in `LEARNER_MEMORY_KEYS` — a fact that only ever populated a non-canonical key (like the `job_company` gap in Section 8) was never persisted in the first place.

**Cleared fact reappearing.**
Check whether the "clear" was implemented via `save()` with `None` values instead of `clear()` — per Section 8, `save()`'s merge semantics mean a `None` value never overwrites an existing non-`None` value on disk, so a from-scratch "clear" that uses `save()` instead of `clear()` will silently fail to erase anything.

**New session retaining old conversation context.**
Confirm `_resetCurrentSessionState()` was actually invoked (check for the "Start" button handler or `startFreshLearner()` call in the code path that led to the new session) rather than the page simply continuing to run with stale `window._*` values from a previous conversation that was never formally reset.

**Persona switch using the previous persona's reply history.**
This is expected baseline behaviour per SIC-4 (Section 16.2), not a bug — `recent_persona_replies` and `current_engine` are not cleared on persona switch. If this is undesirable for a given feature, it requires an explicit product decision and code change, not a "fix" to existing behaviour.

**Client state differing from server response.**
Diff the fields in `response.state_update` against what `window._*` shows immediately after the response resolves. If a field is present in `state_update` but not reflected client-side, check the client's merge block for a missing case — Section 6 lists three fields (`pending_dest_candidate`, `location_retry_count`, `location_clarify_hint`) that are *known* not to be merged back by the production client; a missing-merge bug for any *other* field is a genuine regression, not an expected gap.

**Recent frame unexpectedly repeating.**
Check whether `recent_frame_ids` client-side actually contains the frame in question — remember the cap is 50, so a very long session could have rolled the offending frame out of the window entirely, which is expected, not a bug. If the frame is still within the last 50 and still got re-selected, the bug is in the ladder-selection exclusion logic, not in state transport.

**Progress reset when learner memory is cleared.**
This should never happen per SINV enforcement and the negative tests in `test_clear_memory_regression.py`/`test_session_start_reset.py` — if observed, check whether a code change accidentally added a progress-clearing call inside `startFreshLearner()` or `/api/reset_memory`, since neither is supposed to touch progress state.

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
| `state_update` | `scripts/ui_server.py`, scattered write sites | Returned every response | `ui/app.js` state-update merge block (6882–6919) | Overwritten each turn | `test_e4_topic_handoff.py` |
| E4 engine handoff | `scripts/ui_server.py:10296–10313` (compute), `:11835` (write) | `state_update.current_engine` | `ui/app.js` (`window._currentEngineId`) | N/A — recomputed each qualifying turn | `test_e4_topic_handoff.py::TestE4DirectPersonaHandoff` |
| Working memory (`recent_persona_replies`) | `scripts/ui_server.py:11826` | `conversation_state` / `state_update` | `_answer_from_working_memory`, `_dedupe_persona_answer` | `_resetCurrentSessionState()` (`[]`) | `test_stale_answer_loop_regression.py` |
| Persistent learner memory | `scripts/learner_memory.py` (`save`, `apply_updates`, `clear`) | `data/learner_memory.json` (path via `MANDARINOS_DATA_DIR`) | Slot substitution, `_answer_from_working_memory` fallback, response echo | `/api/reset_memory` → `clear()` | `test_clear_memory_regression.py`, `test_learner_memory_migration.py` |
| Persona identity/state | `ui/app.js` persona-button handler; `scripts/ui_server.py:_resolve_persona` | `conversation_state.persona_id`/`partner_id`; `personas/<id>.json` (content) | Answer-generation, discoverable-fact reveal, partner header | Persona switch clears reveal-tracking only | — |
| Frame/engine state | `ui/app.js` (`window._currentEngineId`, `window._recentFrameIds`); `scripts/ui_server.py` selector | `conversation_state`; `state_update` | Frame selector, bridge logic | `_resetCurrentSessionState()` | `test_conversation_first_wave.py::test_active_turn_record_single_source_of_truth` |
| Recovery/confusion state | `scripts/ui_server.py` (`recent_confusion_count`, `repair_attempt_count`, mirror ladder); `ui/app.js` (challenge mode, spoken interception) | Partial — see Section 11 for round-trip gaps | Repair-escalation reply selection, mirror ladder | `_resetCurrentSessionState()`; `_confirmed_re_ask` resets via `state_update` | `test_challenge_recovery.py`, `test_stale_counter_reply_loop.py` |
| Session/progress/analytics | `ui/app.js` (`_tracker`); `scripts/ui_server.py` (`_build_progress_snapshot`, `capability_estimator`) | `/api/end_session`, `data/progress/<learner_id>.json`, `localStorage` | Progress display, capability bands (reporting only) | `_resetCurrentSessionState()` zeroes `_tracker`; progress history explicitly preserved | `test_progress_tracking.py`, `test_progress_store.py` |

**Application baseline commit:** `53584cee9e8c892ff77f12741d1fc89d9d09c7e7`
**Baseline tag:** `architecture-baseline-2026-07-12`
**Source documentation branch:** `docs/architecture-v1`
**Document status:** Draft v1
**Last verified date:** 2026-07-12
