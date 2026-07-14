<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as the broader Session Intelligence architecture proposal; a limited implementation slice exists, while the remaining architecture is unverified or proposed.
> - **May guide current implementation:** No.
> - **Current authority:** Verified Session Intelligence code and endpoints, current tests, applicable R2 contracts, and `docs/session_intelligence_implementation_report.md` only as dated implementation evidence.
> - **Principal caution:** Partial implementation does not elevate the complete architecture document into current authority. Each claimed component, workflow, storage location, and later slice must be verified individually.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS — Session Intelligence Architecture

**Status:** Phase 0 Slice 1 implemented (`scripts/session_intelligence.py`, `MANDARINOS_SESSION_CAPTURE` flag)
**Author:** Architecture review
**Scope:** Strategy for turning every completed session into (a) learner-facing feedback, (b) founder-facing product intelligence, and (c) aggregated daily/weekly findings.

**Hard constraints honoured by this document:**
- No application code modified.
- No change to the existing progress persistence system.
- No LLM API calls introduced.

> Read alongside `.cursor/rules/mandarinos-architecture.mdc` (additive growth, stable extensible base) and `AI_CONTEXT.md`. This feature must be a **new, parallel capture layer** — it never rewrites the conversation engine, the scorecard, or `progress_store`.

---

## 1. Current state summary

### 1.1 Session lifecycle (today)

```
Client (ui/app.js)                         Server (scripts/ui_server.py)
──────────────────                         ─────────────────────────────
runTurn() ──POST /api/run_turn──────────▶  run_turn(): selects frame, builds reply,
   │                                          emits rich per-turn diagnostics
   │  ◀── response (incl. selector_trace,
   │       reaction_trace, arc_state,
   │       move_type_filter, counter_reply)
   │
addTranscriptEntry()  ── stored ONLY in
   conversationTranscript[] (client memory)
   │
endSession() ──POST /api/end_session────▶  _compute_scorecard(sess)
   (sends AGGREGATE COUNTERS ONLY)            _build_progress_snapshot(sess, metrics)
                                              progress_store.save_snapshot(learner_id, snapshot)
                                          ──▶ data/progress/{learner_id}.json
```

### 1.2 Where completed session data is currently stored

| Store | Path | Written by | Content | Granularity |
|---|---|---|---|---|
| Per-learner progress | `data/progress/{learner_id}.json` | `progress_store.save_snapshot` via `/api/end_session` | Append-only list of compact snapshots, **deduped by `session_id`** | One record per session, **aggregate metrics only** |
| Challenge history | `data/progress_history.json` | `_append_progress_history` (challenge mode only) | Full `sess` payload + `metrics` | One record per challenge session |
| Learner memory | `data/learner_memory.json` | `learner_memory` store | 6 fields: name, hometown, lives_in, job_or_study, family, favourite_food | Per learner (overwrites) |
| Beta profiles | `data/beta_profiles/{learner_id}.json` | beta profile flow | Level/onboarding profile | Per learner |
| Client cache | `localStorage["manos_progress_history"]` | client | Mirror of snapshots for the Progress tab | UI cache only |

### 1.3 What data is already available

**Already persisted server-side at `/api/end_session`** (aggregate session counters in `sess`):
`total_turns`, `recovery_uses`, `successful_recoveries`, `conversational_recoveries`, `successful_conversational_recoveries`, `suggestion_clicks`, `card_opens`, `display_en_clicks`, `display_py_clicks`, `hint_clicks`, `translation_help_uses`, `questions_asked`, `depth_responses`, `unmatched_responses`, `soft_unmatched_responses`, `engines_used[]`, `duration_seconds`, `mode`, `tier`, `persona_id`, `session_id`, `learner_id`.

**Computed server-side and returned per turn, but NOT persisted** (this is the high-value, currently-discarded data):
- `selector_trace` — why each frame was chosen (ranks, guards fired, suppression reasons).
- `reaction_trace` — reaction composition mode (e.g. `content_aware_marriage_duration`, `multi_destination_ack`).
- `arc_state` — `turns_in_current_engine`, `loop_count`, `engines_visited`, `transition_reason`.
- `move_type_filter` — candidates before/after move-type filtering.
- `counter_reply` (+ `_en`, `_pinyin`) — the persona's answer to a learner question.
- Per-turn `frame_id`, `engine`, slot names, `move_type`.

**Held client-side only, never transmitted** (`ui/app.js`):
- `conversationTranscript[]` — ordered turns: `{ id, role, text_zh, text_en, pinyin, frame_id, turn_uid, created_at }`.
- `_tracker` — live counters, `engines_used` Set, recovery/observation events.
- UI events: card opens, hint/translation clicks, EN/PY reveals, suggestion clicks, ASR accept/reject.

### 1.4 Key gaps

1. **No turn-level record survives the session.** The richest signal (the actual transcript + per-turn traces) is computed and then thrown away. Only six-ish aggregate numbers reach disk.
2. **No raw learner utterance log.** ASR text, matched/unmatched classification, and recovery sequences are not stored, so we cannot later say "the learner said X and the app misread it as Y."
3. **No event timeline.** We know `card_opens = 3` but not *when* or *around which frame*, so UX friction is invisible.
4. **`data/` is fully `.gitignored`** and ephemeral on Railway unless `MANDARINOS_DATA_DIR` points at a mounted volume — the same durability caveat that affects progress applies here.

---

## 2. Proposed architecture

### 2.1 Design principles

1. **Parallel capture, never coupling.** Session Intelligence reads the same `sess` payload and (new) transcript, but writes to its **own directory tree**. It must be removable without touching the engine or progress.
2. **Capture first, interpret later.** The foundation is a faithful, append-only **raw session record**. Feedback and product intelligence are *derived views* produced by separate, optional processors.
3. **Two audiences, two artifacts, two trust levels.** Learner feedback and founder product-intelligence are generated and stored separately, with different redaction and access rules.
4. **Manual-AI now, built-in-AI later, same substrate.** A manual reviewer (a human pasting a session bundle into an LLM) and a future automated reviewer both consume the *same* `session_record` JSON. We build the substrate now; the automated layer is a later plug-in.
5. **Additive and declarative.** New capture is gated behind a single feature flag and degrades to a no-op on any error — it can never break a session save.

### 2.2 Layered model

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 0 — Capture (build first)                                   │
│   Persist a complete per-session record: transcript + turn        │
│   traces + aggregate metrics + event timeline.                    │
│   Output: data/sessions/{learner_id}/{session_id}.json            │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1 — Export / Review bundle (manual AI now)                  │
│   A read-only tool that packages a session (or a day) into a      │
│   redacted, prompt-ready bundle for manual LLM review.            │
│   Output: data/review_exports/*.md / *.json                       │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2 — Derived intelligence (built-in AI later)                │
│   2a Learner feedback  → data/feedback/{learner_id}/{session}.json│
│   2b Product intel     → data/product_intel/{session_id}.json     │
│   (manual-authored now; LLM-authored later — same schema)         │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3 — Aggregation                                             │
│   Daily/weekly rollups of product_intel + metrics.               │
│   Output: data/product_intel/rollups/{period}.json               │
└─────────────────────────────────────────────────────────────────┘
```

Each layer depends only on the layer below it and is independently shippable.

### 2.3 Capture mechanism (Layer 0)

Two viable capture points; recommend **both eventually, transcript-on-end first**:

- **Primary (slice 1):** Extend the `/api/end_session` payload so the client also sends `conversationTranscript[]` and a lightweight `event_log[]`. The server writes a `session_record` to `data/sessions/`. This is the smallest change that yields the highest-value artifact, and it touches **only the end-of-session path**, not `run_turn` or `progress_store`.
- **Secondary (later):** Server-side per-turn append of `selector_trace`/`reaction_trace`/`arc_state` into a turn log keyed by `session_id`. Higher fidelity (survives a client crash) but touches the hot path, so defer.

A new module `scripts/session_intelligence.py` owns all reads/writes for this feature, mirroring the `progress_store.py` pattern (env-driven base dir, `learner_id` validation, safe no-op on error). **It is imported lazily and wrapped in try/except at the call site**, exactly like `_ps_save_snapshot` is today.

---

## 3. Data model

### 3.1 `session_record` (Layer 0 — the substrate)

```jsonc
{
  "schema": "session_record_v1",
  "session_id": "s_1779441865679",
  "learner_id": "learner_1779441865679",
  "created_at": "2026-06-29T01:20:00+12:00",
  "persona_id": "jianguo",
  "mode": "normal",
  "tier": "standard",
  "duration_seconds": 412,
  "app_version": "phase11.x",            // optional build/commit marker

  "metrics": { /* exact copy of _compute_scorecard output */ },
  "progress_snapshot_ref": {             // reference, NOT a second copy of truth
    "session_id": "s_1779441865679",
    "stored_in": "data/progress/learner_1779441865679.json"
  },

  "transcript": [
    {
      "idx": 0,
      "role": "partner",                 // "partner" | "user"
      "text_zh": "你家里谁对你最重要？",
      "text_en": "Who in your family matters most to you?",
      "pinyin": "nǐ jiālǐ shéi duì nǐ zuì zhòngyào?",
      "frame_id": "f_family_important",
      "engine": "family",
      "turn_uid": "t_0",
      "created_at": "2026-06-29T01:13:11+12:00"
    },
    {
      "idx": 1,
      "role": "user",
      "text_zh": "我妈妈。",
      "asr_raw": "我妈妈",                // raw ASR before any matching (if available)
      "matched": true,                   // classified understandable?
      "frame_id": "f_family_important",
      "turn_uid": "t_0"
    }
  ],

  "turn_traces": [                        // optional; present when client forwards them
    {
      "idx": 0,
      "frame_id": "f_family_important",
      "engine": "family",
      "move_type": "probe",
      "selector_trace": { /* as returned by run_turn */ },
      "reaction_trace": { "composition_mode": "content_aware_family_together" },
      "arc_state": { "turns_in_current_engine": 2, "loop_count": 0 }
    }
  ],

  "event_log": [                          // UX friction timeline
    { "t_offset_ms": 14200, "type": "card_open",        "frame_id": "f_family_important" },
    { "t_offset_ms": 15900, "type": "display_en_click", "frame_id": "f_family_important" },
    { "t_offset_ms": 30100, "type": "recovery_use",     "frame_id": "f_family_important", "kind": "repeat" }
  ],

  "capture_flags": {
    "transcript_present": true,
    "turn_traces_present": false,
    "truncated": false
  }
}
```

Notes:
- `metrics` is copied verbatim from the existing scorecard computation — we do **not** recompute or reinterpret it, avoiding drift with the progress system.
- `progress_snapshot_ref` is a *pointer*, not a duplicate source of truth. The progress file remains authoritative for progress.

### 3.2 `learner_feedback` (Layer 2a — learner-facing)

```jsonc
{
  "schema": "learner_feedback_v1",
  "session_id": "s_1779441865679",
  "learner_id": "learner_1779441865679",
  "created_at": "2026-06-29T02:00:00+12:00",
  "generator": "manual",                 // "manual" | "llm:<model>" (later)
  "summary": "You kept the conversation going well and asked two good questions.",
  "highlights": [
    "You recovered naturally after a misunderstanding about your sister's job."
  ],
  "could_have_said_better": [
    {
      "your_turn": "我妈妈。",
      "context": "Asked who matters most in your family.",
      "suggestion": "我妈妈对我最重要，因为她很关心我。",
      "why": "Adding a reason makes your answer feel more natural and complete.",
      "skill_tag": "elaboration"
    }
  ],
  "encouragement": "Great persistence — you stayed in Chinese the whole time."
}
```

Tone rules (from existing Design Constitution): supportive, no teacher-voice "correct answer" reveals during a session; this is **post-session** reflection, so concrete rephrasings are allowed but framed as options, not corrections.

### 3.3 `product_intel` (Layer 2b — founder-facing, internal)

```jsonc
{
  "schema": "product_intel_v1",
  "session_id": "s_1779441865679",
  "learner_id_hash": "9f2c…",            // pseudonymised, not raw id
  "created_at": "2026-06-29T02:00:00+12:00",
  "generator": "manual",
  "findings": [
    {
      "category": "bug",                 // bug | ux | conversation_design | content | enhancement
      "severity": "high",                // low | medium | high
      "title": "Recovery phrase fell into generic uncertainty",
      "evidence_turn_idx": [12, 13],
      "observation": "Learner said '再说一遍' but persona replied '这个我不太清楚'.",
      "hypothesis": "Confusion signal not routed to clarify-app-question path.",
      "recommendation": "Ensure recovery phrases bypass persona limitation reply.",
      "linked_engine": "family"
    }
  ],
  "session_health": {
    "flow": "good",
    "friction_score": 2,                 // derived from event_log density
    "unmatched_turn_ratio": 0.08
  }
}
```

### 3.4 `rollup` (Layer 3 — aggregated)

```jsonc
{
  "schema": "product_intel_rollup_v1",
  "period": "2026-06-29",                // ISO date or ISO week "2026-W26"
  "sessions_analysed": 14,
  "top_findings": [
    { "category": "ux", "title": "Pull-to-refresh wiped session on iOS", "count": 3, "severity": "high" }
  ],
  "trends": {
    "avg_turns": 18.2,
    "avg_unmatched_ratio": 0.07,
    "recovery_use_rate": 0.21
  },
  "recommended_focus": ["confusion routing", "iOS save robustness"]
}
```

---

## 4. File structure

All new data lives under the already-`.gitignored` `data/` tree (and therefore under `MANDARINOS_DATA_DIR` in production). **No existing path is modified.**

```
data/
├── progress/                      # UNCHANGED — authoritative progress (do not touch)
│   └── {learner_id}.json
├── progress_history.json          # UNCHANGED — challenge mode
├── learner_memory.json            # UNCHANGED
├── beta_profiles/                 # UNCHANGED
│
├── sessions/                      # NEW — Layer 0 raw substrate
│   └── {learner_id}/
│       └── {session_id}.json      # one session_record per file
│
├── review_exports/                # NEW — Layer 1 manual-review bundles
│   ├── {session_id}.md            # prompt-ready, redacted
│   └── daily_{date}.md
│
├── feedback/                      # NEW — Layer 2a learner-facing
│   └── {learner_id}/
│       └── {session_id}.json
│
└── product_intel/                 # NEW — Layer 2b founder-facing (internal)
    ├── {session_id}.json
    └── rollups/
        └── {period}.json
```

Rationale:
- **Per-file, per-session** (not one giant array) avoids the read-modify-write contention and dedupe complexity that already bit the progress system. Each session is an independent, append-only artifact.
- **`learner_id` sharding** mirrors `data/progress/` and keeps per-learner export/delete trivial (important for privacy requests).
- **`product_intel` is a sibling, not a child, of `feedback`** — a hard directory boundary between learner-facing and internal data, so access controls and redaction differ cleanly.

---

## 5. Phased implementation plan

> Each phase is independently shippable and reversible. Phases 0–1 contain **no AI** and **no progress changes**.

### Phase 0 — Capture substrate (the foundation)
- New module `scripts/session_intelligence.py` (env-driven base dir, `learner_id` validation, safe no-op on error — copy `progress_store.py` ergonomics).
- Extend `/api/end_session` to optionally accept `transcript[]` + `event_log[]` from the client and write a `session_record_v1` to `data/sessions/{learner_id}/{session_id}.json`.
- Client: include `conversationTranscript` and a minimal event log in the `endSession()` payload.
- **Gated behind a feature flag** (`MANDARINOS_SESSION_CAPTURE=1`); default off until validated.
- Acceptance: a completed session produces a faithful `session_record`; progress save is byte-for-byte unchanged; capture failure never blocks `/api/end_session`.

### Phase 1 — Manual review export (manual AI now)
- Read-only CLI/tool (e.g. `tools/export_session_review.py`) that turns one `session_record` (or a day's worth) into a redacted, prompt-ready Markdown bundle in `data/review_exports/`.
- Founder pastes the bundle into any LLM manually to produce feedback + product findings. No API calls in the repo.
- Acceptance: a reviewer can read a clean transcript + metrics + event timeline for any captured session.

### Phase 2 — Structured manual findings
- Define and validate the `learner_feedback_v1` and `product_intel_v1` schemas.
- Provide a tiny writer so manually-authored findings can be saved into `data/feedback/` and `data/product_intel/` in the canonical shape.
- Acceptance: findings are queryable and aggregatable later regardless of who/what authored them.

### Phase 3 — Aggregation
- `tools/aggregate_product_intel.py` produces `rollups/{period}.json` from `product_intel/*.json` + session metrics.
- Acceptance: daily/weekly rollup lists top findings and trends.

### Phase 4 — Built-in AI review (future; explicitly deferred)
- A reviewer module that reads `session_record` and emits `learner_feedback` + `product_intel` automatically, writing through the *same* writers from Phase 2.
- This is the **only** phase that introduces LLM API calls, behind its own flag and config. Not in scope now.

### Phase 5 — Surfacing (future)
- Learner feedback shown in-app (respecting the canonical `.option-panel` UI rules — no parallel render paths).
- Internal dashboard for rollups.

---

## 6. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Corrupting the progress system** | Session Intelligence never imports or writes `progress_store`; it only reads a *copy* of `sess`/`metrics`. Separate directories. Capture wrapped in try/except so it cannot raise into `/api/end_session`. |
| R2 | **Hot-path performance / coupling** | Slice 1 captures only at end-of-session, not per turn. Per-turn server capture (Phase 2+ secondary) deferred and flag-gated. |
| R3 | **Payload bloat / mobile data** | Transcript is text-only and already in client memory; cap turns (e.g. last N) and set `capture_flags.truncated`. Compress server-side if needed. |
| R4 | **Ephemeral storage on Railway** | Same caveat as progress: requires `MANDARINOS_DATA_DIR` on a mounted volume. Document loudly; do not assume durability. |
| R5 | **PII exposure** (transcripts contain name, hometown, family, job) | See §privacy below: pseudonymise in `product_intel`, redact in export bundles, retention limits, per-learner delete. |
| R6 | **Schema drift between manual and AI generators** | Both write through one schema + one validator from Phase 2; `generator` field records provenance. |
| R7 | **Dedupe / double-save** (the bug we already hit) | Per-session file keyed by `session_id`; a re-save overwrites the same file idempotently rather than appending. |
| R8 | **Feature creep into the engine** | Architecture rule: this layer is read-only w.r.t. conversation logic. Any need to change engine behaviour is a separate, explicitly-approved change. |
| R9 | **Leaking internal findings to learners** | Hard directory boundary; learner-facing surfaces only ever read `data/feedback/`, never `data/product_intel/`. |

### Privacy & data minimisation
- **Pseudonymity:** `product_intel` uses `learner_id_hash`, not the raw id. `learner_id` is already a synthetic timestamp id, not real identity — keep it that way.
- **Minimise:** store only what review needs. Do not capture device fingerprints, IP, or precise geolocation. Event log stores *types and offsets*, not free-form data.
- **Redaction in exports:** the Phase 1 exporter masks obvious PII tokens (learner name from `learner_memory`, etc.) in review bundles by default.
- **Retention:** define a TTL (e.g. raw `sessions/` kept 90 days, then pruned or down-sampled to metrics-only). Rollups are PII-free and can persist.
- **Right to delete:** per-`learner_id` sharding makes "delete everything for this learner" a directory removal across `sessions/`, `feedback/`, `product_intel` index — script this in Phase 2.
- **Consent surface:** beta users should be told sessions are recorded for product improvement (out of scope to implement, but flag it before any production rollout).

---

## 7. Recommended first implementation task

**Build Phase 0, slice 1: persist a `session_record_v1` at end-of-session.**

Concretely, the first task is:

1. Add `scripts/session_intelligence.py` with `save_session_record(learner_id, record) -> bool` and `load_session_record(learner_id, session_id)` — modelled exactly on `progress_store.py` (env base dir, `_SAFE_LEARNER_ID`, per-file write, safe failure).
2. In `endSession()` (`ui/app.js`), add `transcript: conversationTranscript` and a minimal `event_log` to the existing `/api/end_session` payload — **no other client change**.
3. In the `/api/end_session` handler, **after** the existing progress save, build a `session_record` from the already-computed `sess` + `metrics` + the new transcript/event fields, and call `save_session_record(...)` inside a try/except. Gate the whole block behind `MANDARINOS_SESSION_CAPTURE`.

Why this first: it is the smallest change that captures the single highest-value, currently-discarded asset (the transcript + metrics together), it touches only the end-of-session path, it cannot affect progress or the engine, and **every later layer depends on it**. Everything else (export, feedback, product intel, rollups, automated AI) is a pure consumer of this file.

Suggested acceptance tests (static + behavioural):
- A completed session writes exactly one file at `data/sessions/{learner_id}/{session_id}.json` whose `transcript` length matches turns shown.
- `data/progress/{learner_id}.json` is unchanged when capture is on vs off (progress isolation).
- With `MANDARINOS_SESSION_CAPTURE` unset, no `sessions/` file is written and the response is identical to today.
- A capture exception is swallowed and `/api/end_session` still returns `ok: true`.

---

## 8. Explicit list of things NOT to build yet

- ❌ **No LLM API calls** anywhere in the repo (Phase 4 only, future).
- ❌ **No changes to `progress_store.py`, `_compute_scorecard`, `_build_progress_snapshot`, or the progress files.**
- ❌ **No per-turn server-side capture** in `run_turn` yet (defer the hot-path change; end-of-session capture first).
- ❌ **No new conversation-engine behaviour, selector changes, or frame changes** — this feature is read-only w.r.t. the engine.
- ❌ **No in-app learner-feedback UI** yet (Phase 5). Do not add a parallel render path; when built it must use the canonical `.option-panel`/existing surfaces.
- ❌ **No internal dashboard / web view** for product intel yet.
- ❌ **No automatic aggregation cron/scheduler** — Phase 3 is a manually-run tool first.
- ❌ **No real-identity capture** (emails, device IDs, IP, geolocation).
- ❌ **No migration/backfill** of historical sessions (we only have aggregate snapshots for those; transcripts weren't captured and cannot be reconstructed).
- ❌ **No second source of truth for progress** — `session_record.metrics` is a copy for context, never read back into the progress system.

---

## 9. Long-term product learning loop

This section makes the full strategic path explicit so every implementation decision — from the file schema chosen today to the tooling built next — serves the same end goal.

### 9.1 The four stages

```
Stage 1 ─ Capture (now)
    │  Persist session_record_v1 after every completed session.
    │  Preserve transcript, prompts, pinyin, translation, engine,
    │  recovery, scorecard, and UX-event evidence in a single file.
    │  Nothing is lost. Nothing is interpreted yet.
    ▼
Stage 2 ─ Manual / external AI review (interim)
    │  Export selected session_record_v1 files (one session or a
    │  day's worth) as redacted, prompt-ready bundles.
    │  Paste the bundle into ChatGPT/Claude manually.
    │  Record the output as:
    │    • learner_feedback_v1  (what the learner could improve)
    │    • product_intel_v1     (bugs, UX issues, conversation-design
    │                            weaknesses, enhancement priorities)
    │  No API keys in the repo; the LLM is a human-operated tool.
    ▼
Stage 3 ─ Batch synthesis (periodic)
    │  Aggregate many product_intel_v1 records into a
    │  product_intel_rollup_v1 for a day, week, or month.
    │  Surface repeated bugs, UX friction, and conversation-design
    │  weaknesses ranked by frequency and severity.
    │  Rollup findings become input to human-reviewed Cursor
    │  implementation directives — the same format already used to
    │  drive all MandarinOS improvements.
    ▼
Stage 4 ─ Built-in AI review (future)
       Add LLM integration so that learner_feedback_v1 and
       product_intel_v1 are generated automatically from
       session_record_v1, without manual paste-and-review.
       The artifact shapes are identical to Stages 2 and 3 —
       only the generator field changes ("manual" → "llm:<model>").
       Daily/weekly synthesis from many sessions is then automated.
       This is the only stage that introduces LLM API calls, and it
       is gated behind its own flag and remains explicitly deferred.
```

Each stage is **independently shippable and additive**. Stages 2–4 are pure consumers of the `session_record_v1` substrate built in Stage 1. None of them modifies the conversation engine, the progress store, or any per-turn runtime logic.

### 9.2 What "the app improves itself" means — and does not mean

The four stages together create a **product learning loop**:

> Session evidence → analysis → ranked recommendations → approved implementation directive → code change → better session evidence.

**What this means:**

- MandarinOS captures every session's evidence automatically (Stage 1).
- That evidence is analysed to surface concrete recommendations — conversation-design gaps, routing bugs, UX friction, frame weaknesses.
- Recommendations accumulate and are ranked by frequency and severity (Stage 3 rollups).
- The ranked recommendations feed a human-readable implementation directive, structured identically to the directives already driving MandarinOS development.

**What this does not mean:**

MandarinOS does not autonomously modify its own code. There is a mandatory human approval gate between "the system proposes a fix" and "code changes". The governor is always a founder/developer who reads the recommendation, decides it is correct and safe, and approves a Cursor implementation directive. Only then does code change. This is not a limitation to work around — it is the correct boundary for a language-learning product where a subtle behaviour change in the conversation engine can silently degrade the learner experience.

```
Automated (Stage 1–4)              │   Human gate    │   Cursor agent
────────────────────────────────── │ ─────────────── │ ───────────────
Capture → analyse → aggregate   ──▶│ review/approve ▶│ implement
session_record_v1                  │ directive       │ (code changes)
product_intel_rollup_v1            │                 │
```

### 9.3 Alignment with core architecture principles

| Principle | How the learning loop honours it |
|---|---|
| **Capture first, interpret later** | Stage 1 makes no judgements. Raw evidence is preserved; interpretation is a later, optional layer. |
| **Additive growth** | Each stage adds new files and tools; none rewrites the engine, scorecard, or progress system. |
| **Stable extensible base** | The `session_record_v1` schema is a stable substrate. Stages 2–4 are plug-in consumers, not architecture changes. |
| **Declarative, not imperative** | Product intel surfaces *what* to improve and *why*, backed by evidence. The *how* is always a separate approved directive. |
| **Two audiences, two artifacts** | `learner_feedback_v1` (supportive, learner-visible) and `product_intel_v1` (internal, pseudonymised) remain permanently separated by schema, directory, and access control. |

---

### Appendix A — Source references (current behaviour)

- End-session handler: `scripts/ui_server.py` `/api/end_session` (~line 10137).
- Scorecard: `_compute_scorecard` (~line 6464); snapshot: `_build_progress_snapshot` (~line 6694).
- Progress persistence: `scripts/progress_store.py` (`save_snapshot`, per-`learner_id` file, dedupe by `session_id`).
- Per-turn diagnostics emitted but discarded: `response["selector_trace"|"reaction_trace"|"arc_state"|"move_type_filter"]` (~line 10022).
- Client transcript model: `addTranscriptEntry` (`ui/app.js` ~line 175); end-session payload (~line 9958).
- Storage root: `MANDARINOS_DATA_DIR` (defaults to `./data`, fully `.gitignored`, ephemeral on Railway without a volume).
