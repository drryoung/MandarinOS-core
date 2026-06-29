# Session Intelligence — Implementation Report

**Architecture ref:** `docs/session_intelligence_architecture.md`

---

## Phase 0 Slice 1 — Canonical session capture

**Date:** 2026-06-29  
**Directive:** MandarinOS Phase 0 Slice 1 — Implement canonical session capture only

### Summary

Phase 0 Slice 1 is complete. A fully flag-gated session capture layer has been added. When the feature is disabled (default), zero code paths change. When enabled, each completed session writes one `session_record_v1` JSON file per session at `data/sessions/{learner_id}/{session_id}.json`.

---

## Files changed

| File | Change type | Notes |
|---|---|---|
| `scripts/session_intelligence.py` | **New** | Core module: schema builder, atomic write, load/save. |
| `scripts/ui_server.py` | **Extended** | Import + capture block added in `/api/end_session`, after existing progress save. |
| `ui/app.js` | **Extended** | `endSession()` payload extended with `transcript` + `event_log`; `_siEventLog` accumulator + `_siLogEvent()` added; `_resetCurrentSessionState()` resets log. |
| `tests/test_session_intelligence.py` | **New** | 41 focused acceptance tests (all passing). |
| `docs/session_intelligence_implementation_report.md` | **New** | This file. |

---

## How to enable / disable

### Enable (Railway)

Set an environment variable in your Railway service:

```
MANDARINOS_SESSION_CAPTURE=1
```

### Disable (default)

Remove the variable, or set it to any value other than `"1"`:

```
MANDARINOS_SESSION_CAPTURE=   # blank → disabled
```

When disabled, the import still succeeds, `is_enabled()` returns `False`, and all capture code is a no-op with zero performance cost.

### Local development

```powershell
$env:MANDARINOS_SESSION_CAPTURE = "1"
python scripts/ui_server.py
```

---

## Schema and file path

**Path:** `data/sessions/{learner_id}/{session_id}.json`  
(under `MANDARINOS_DATA_DIR` when set, else `data/` relative to repo root)

**Top-level schema:**

```json
{
  "schema": "session_record_v1",
  "capture_source": "end_session_payload",
  "session_id": "session_1749123456789",
  "learner_id": "learner_abc",
  "created_at": "2026-06-29T14:00:00+12:00",
  "persona_id": "jianguo",
  "mode": "normal",
  "tier": "standard",
  "duration_seconds": 420,
  "counters": {
    "total_turns": 12,
    "recovery_uses": 1,
    "engines_used": ["identity", "work"],
    "..."
  },
  "metrics": { "..." },
  "progress_snapshot_ref": {
    "session_id": "session_1749123456789",
    "stored_in": "data/progress/learner_abc.json"
  },
  "transcript": [
    { "idx": 0, "role": "partner", "text_zh": "你好！...", "..." }
  ],
  "event_log": [
    { "t_offset_ms": 1234, "type": "recovery_use", "frame_id": "fr_id_xyz" }
  ],
  "capture_flags": {
    "transcript_present": true,
    "event_log_present": true,
    "transcript_truncated": false
  }
}
```

The `progress_snapshot_ref` is a lightweight pointer only — the two systems are not merged.

---

## Tests added

File: `tests/test_session_intelligence.py` — **41 tests, 41 passing**

| Class | Coverage |
|---|---|
| `TestFlagOff` | Flag disabled → no file, `is_enabled()` false, `save` returns False |
| `TestFlagOn` | Flag enabled → file at correct path, valid JSON, round-trip load |
| `TestTranscriptMissing` | No transcript in payload → endpoint succeeds, empty list |
| `TestProgressUnchanged` | `data/progress/` not touched by SI capture |
| `TestSeparateFiles` | Two sessions → two files; no shared array; same session_id → replace |
| `TestSchema` | `schema_version`, `capture_source`, all required keys, mode normalised |
| `TestTranscriptSanitisation` | Extra keys stripped; capped at `_MAX_TRANSCRIPT_ENTRIES`; idx auto-assigned |
| `TestValidation` | Invalid `learner_id` / `session_id` → safe False, no file created |
| `TestCounterCoercion` | String counters coerced to int; missing defaults to 0 |
| `TestProgressRef` | `progress_snapshot_ref` includes session_id and file path |

---

## What was not changed

Per the directive's explicit constraints:

- `progress_store.save_snapshot` — **not touched**
- `scripts/progress_store.py` — **not touched**
- The conversation engine, selector, or any frame/response logic — **not touched**
- No LLM calls added
- No learner-facing feedback surfaces added
- No product intelligence generation added
- No aggregation added
- No old sessions backfilled
- No new UI surfaces

---

## Deviations from the architecture document

None. The implementation follows the architecture document exactly:

- One file per session (per-session, not per-learner append).
- Atomic write via `tempfile.mkstemp` + `shutil.move`.
- Gated by `MANDARINOS_SESSION_CAPTURE`.
- Runs after existing progress save so capture failure cannot affect progress.
- `progress_snapshot_ref` provides cross-system correlation without merging.
- Transcript sanitisation: allowed-keys whitelist + cap at 200 entries.

---

## Risks

| Risk | Mitigation |
|---|---|
| Railway ephemeral storage | `MANDARINOS_DATA_DIR` must point to a mounted Volume (same requirement as progress files). |
| Payload size (long sessions) | Transcript capped at 200 entries client-side; `_MAX_TRANSCRIPT_ENTRIES` enforced server-side too. |
| PII in transcripts | All data is pseudonymous by `learner_id`. No ASR raw audio stored. Redaction for Phase 1+. |
| Capture failure blocking end_session | All capture code is in a `try/except`; errors are logged, not re-raised. Existing behavior is unchanged. |
| `data/sessions/` not in `.gitignore` | **Action required:** add `data/sessions/` to `.gitignore` (same as `data/progress/`) before first production enable. |

---

## Next steps after Slice 1

See `docs/session_intelligence_architecture.md` for the full roadmap. The immediate follow-on:

1. ~~Phase 1: export / manual AI review tool (read `session_record_v1`, produce readable Markdown summary).~~ → **Complete (Slice 2 below)**
2. Phase 2: structured manual findings writer (`learner_feedback_v1`, `product_intel_v1`).
3. Phase 3: aggregation rollup tool.

---

## Phase 0 Slice 2 — Manual review export

**Date:** 2026-06-29  
**Directive:** MandarinOS Phase 0 Slice 2 — Export captured session for manual AI review

### Summary

Phase 0 Slice 2 is complete. A standalone export script converts one `session_record_v1` JSON file into a Markdown prompt ready to paste into ChatGPT or Claude for manual analysis. No LLM API calls are added; the script is a pure read-and-render tool.

### Files changed

| File | Change type | Notes |
|---|---|---|
| `scripts/export_session_review_prompt.py` | **New** | Renderer + atomic file writer + CLI (`argparse`). |
| `tests/test_export_session_review_prompt.py` | **New** | 53 tests using a representative `session_record_v1` fixture. |
| `docs/session_intelligence_implementation_report.md` | Updated | Added this Slice 2 section. |

### How to use

```powershell
# Print prompt to stdout (inspect/copy):
python scripts/export_session_review_prompt.py data/sessions/<lid>/<sid>.json

# Write to data/review_exports/<lid>/<sid>_review_prompt.md:
python scripts/export_session_review_prompt.py data/sessions/<lid>/<sid>.json --write

# Write to an explicit path and suppress stdout:
python scripts/export_session_review_prompt.py <input.json> --out my_review.md --no-stdout
```

Output path when `--write` is used (auto-derived):

```
data/review_exports/{learner_id}/{session_id}_review_prompt.md
```

(under `MANDARINOS_DATA_DIR` when set, else `data/` relative to repo root.)

### Prompt structure

The generated Markdown contains six data sections followed by eight structured review tasks:

| Section | Content |
|---|---|
| 1. Session Metadata | Schema, IDs, persona, mode, duration, capture flags |
| 2. Session Counters | All aggregate counters from `counters` dict |
| 3. Scorecard | All `metrics` fields from `_compute_scorecard` |
| 4. Conversation Transcript | Per-turn table: Chinese / Pinyin / English / frame_id / engine / turn_uid |
| 5. UX Event Log | Per-event table + type-frequency summary |
| 6. Review Tasks | Structured instructions for the reviewing AI |

**Review tasks requested from the AI (sections A–H):**

| Task | Output format |
|---|---|
| A. Learner Feedback | 2–4 sentences, supportive tone, in English |
| B. Better Mandarin Responses | Table: turn / learner said / could say / why |
| C. Recovery Phrase Opportunities | Table: situation / suggested phrase / pinyin / gloss |
| D. Suspected Bugs | JSON array of `product_intel_v1`-shaped findings |
| E. UX Issues | JSON array of findings |
| F. Conversation-Design Improvements | JSON array of findings |
| G. Product Intelligence Summary | Complete `product_intel_v1` JSON block |
| H. Recommended Next Cursor Tasks | Prioritised task list ready to copy into Cursor |

### Robustness

- Missing or empty fields are shown as `*(not recorded)*` rather than crashing.
- Transcript rows with no pinyin/English show `—` rather than blank cells.
- Truncated transcript flag triggers a visible warning in the metadata table.
- Matched/unmatched learner-turn counts are summarised below the transcript.
- Invalid `learner_id` characters are sanitised to `_` in the output filename.
- Atomic write (temp + rename) — same pattern as `session_intelligence.py`.
- `export_from_path` is importable as a library function; the CLI is a thin wrapper.

### Tests added

File: `tests/test_export_session_review_prompt.py` — **53 tests, 53 passing**

| Class | Coverage |
|---|---|
| `TestSectionsPresent` | All 6 expected `##` sections present |
| `TestMetadata` | session_id, learner_id, persona, mode, duration, schema |
| `TestTranscriptContent` | Chinese text, pinyin, English, frame_id, role labels |
| `TestMissingFields` | `_MISSING` sentinel, empty record, absent counters |
| `TestEventLog` | Table rendered, summary line, `_MISSING` when absent |
| `TestReviewTasks` | All 8 sub-sections (A–H), `product_intel_v1` schema string |
| `TestExportFromPath` | Round-trip, auto path, explicit path, error cases |
| `TestEdgeCases` | Empty transcript/metrics, truncation flag, match counts |
| `TestCLI` | stdout, `--no-stdout`, missing file exit code |
| `TestDefaultOutputPath` | Directory structure, special-char sanitisation |
| `TestUtf8` | Chinese characters preserved in string and on disk |

### Deviations from the architecture document

None. The tool writes to `data/review_exports/` exactly as specified in §4 of the architecture document. No application code was modified.

### Risks

| Risk | Mitigation |
|---|---|
| PII in exported file | Export is a local file, not transmitted anywhere. Founder controls distribution. Future: add redaction option to the exporter. |
| `data/review_exports/` not gitignored | Covered by the existing `data/` gitignore rule — no additional change needed. |
| Long transcripts → large prompt | Transcript already capped at 200 entries by `session_intelligence.py`; no additional cap needed here. Reviewer can further trim manually. |

### Next steps after Slice 2

1. ~~Slice 3: batch export of unreviewed sessions.~~ → **Complete (below)**
2. Slice 4: structured findings writer — save AI Section G output as `product_intel_v1`.
3. Slice 5: aggregation rollup — aggregate findings into `product_intel_rollup_v1`.

---

## Phase 0 Slice 3 — Batch export of unreviewed sessions

**Date:** 2026-06-29  
**Directive:** MandarinOS Phase 0 Slice 3 — Batch export unreviewed sessions for manual AI analysis

### Summary

Slice 3 is complete. A standalone script scans `data/sessions/` for `session_record_v1` files not yet included in any previous batch, then produces a combined Markdown prompt and a manifest JSON. Running the same script again picks up only new sessions. The system is idempotent and additive.

### Files changed

| File | Change type | Notes |
|---|---|---|
| `scripts/export_unreviewed_sessions_batch.py` | **New** | Full batch export logic + CLI |
| `tests/test_export_unreviewed_sessions_batch.py` | **New** | 40 tests |
| `docs/session_intelligence_implementation_report.md` | Updated | Added this Slice 3 section |

### How to use

```powershell
# Preview which sessions would be included (no files written):
python scripts/export_unreviewed_sessions_batch.py --dry-run

# Export unreviewed sessions to batch prompt + manifest:
python scripts/export_unreviewed_sessions_batch.py --write

# Custom paths:
python scripts/export_unreviewed_sessions_batch.py \
    --sessions-root data/sessions \
    --out-dir data/review_exports/batches \
    --max-sessions 20 \
    --write

# Re-export everything (including already-batched sessions):
python scripts/export_unreviewed_sessions_batch.py --include-reviewed --write

# Write without printing the prompt to stdout:
python scripts/export_unreviewed_sessions_batch.py --write --no-stdout
```

### Output files

```
data/review_exports/batches/
├── batch_2026-06-29_01.md                    ← batch prompt (paste into ChatGPT/Claude)
├── batch_2026-06-29_01_manifest.json         ← manifest (tracks what was included)
├── batch_2026-06-29_02.md                    ← next batch same day
└── batch_2026-06-29_02_manifest.json
```

Batch filename: `batch_<YYYY-MM-DD>_<seq>.md` — sequence number increments automatically so re-running the same day never overwrites a previous batch.

### Manifest schema (`batch_manifest_v1`)

```json
{
  "schema": "batch_manifest_v1",
  "batch_id": "batch_2026-06-29_01",
  "created_at": "2026-06-29T16:10:00+12:00",
  "sessions_root": "/data/sessions",
  "output_prompt_path": "/data/review_exports/batches/batch_2026-06-29_01.md",
  "session_count": 3,
  "included_sessions": [
    {
      "learner_id": "learner_abc",
      "session_id": "session_001",
      "source_path": "/data/sessions/learner_abc/session_001.json",
      "timestamp": "2026-06-29T14:00:00+12:00",
      "transcript_turn_count": 12
    }
  ],
  "status": "exported_for_manual_ai_review"
}
```

### Batch prompt structure

| Part | Content |
|---|---|
| Header | Batch ID, session count, learner IDs, date range, total turns, AI constraint warnings |
| Part 1 — Inventory | Table: session_id / learner_id / persona / mode / timestamp / turns |
| Part 2 — Evidence | Per-session blocks: counters, event log summary, full transcript table |
| Part 3 — Scorecards | All scorecard metrics per session |
| Part 4 — Review tasks | Cross-session instructions for sections A–H |

**Review tasks (A–H) asked of the AI:**

| Task | Output |
|---|---|
| A. Learner feedback patterns | Prose (2–3 sentences per learner type) |
| B. Better Mandarin response patterns | Cross-session table |
| C. Repeated recovery phrase opportunities | Cross-session table |
| D. Suspected bugs | JSON array, classified `confirmed`/`suspected`/`observe-only` |
| E. UX issues | JSON array with classification |
| F. Conversation-design findings | JSON array with classification |
| G. Product intel rollup | Complete `product_intel_rollup_v1` JSON block |
| H. Prioritised Cursor task list | P0/P1/P2/Observe groups |

**AI constraint warnings embedded in every prompt:**
- Do not overgeneralise from a small number of sessions.
- Separate learner-specific issues from app/product issues.
- Cite evidence by session_id and turn index.
- Do not recommend large architecture changes unless strongly justified.
- Classify findings: `confirmed` (≥3 occurrences) / `suspected` (2) / `observe-only` (1).
- Prefer small, testable Cursor tasks.

### Tests added

File: `tests/test_export_unreviewed_sessions_batch.py` — **40 tests, 40 passing**

| Class | Coverage |
|---|---|
| `TestFindAllSessions` | Recursive discovery; ignores invalid JSON, wrong schema, arrays, missing dir |
| `TestReviewedIds` | Reads previous manifests; handles missing dir and malformed files |
| `TestReviewedExclusion` | Excludes reviewed; `--include-reviewed` overrides |
| `TestFileOutput` | Prompt and manifest created; schema/fields; included_sessions; originals unmodified |
| `TestDryRunAndEmpty` | `--dry-run` writes nothing; no-sessions exits 1; all-reviewed exits 1 |
| `TestMaxSessions` | Caps at `--max-sessions` |
| `TestBatchFilename` | Date in filename; sequence increments on second call |
| `TestRenderBatchPrompt` | All 4 Parts; inventory table; Chinese text; tasks A–H; rollup schema; warnings; UTF-8 |
| `TestCLI` | `--dry-run` no files; no-flags exits 0; `--dry-run --write` exits 1 |
| `TestSorting` | Sessions sorted oldest-first |
| `TestNextBatchPath` | Creates dir; increments when files exist |

### Deviations from the architecture document

None. Files written to `data/review_exports/batches/` as specified in §4. No application code modified.

### Risks

| Risk | Mitigation |
|---|---|
| Large batch prompt overwhelming the AI context window | `--max-sessions` flag caps sessions per batch (default 20). Split into smaller batches if needed. |
| PII in batch prompt | Same as Slice 2 — local file, not transmitted. |
| Manifest drift (session file moved/deleted after batching) | Manifest records `source_path` at time of export; a missing file on re-run is silently skipped. |
| False "already reviewed" exclusion | Manifest tracks by `session_id` not path, so moved files are still correctly excluded. |

### Next steps after Slice 3

1. ~~Slice 4: read-only admin endpoints to retrieve session files from Railway.~~ → **Complete (below)**
2. Slice 5: structured findings writer — save AI Section G (`product_intel_rollup_v1`) output.
3. Slice 6: daily/weekly scheduled batch.

---

## Phase 0 Slice 4 — Read-only admin session export endpoints

**Date:** 2026-06-29  
**Directive:** MandarinOS Phase 0 Slice 4 — Add read-only admin session export endpoints

### Summary

Two read-only admin-gated endpoints added to `ui_server.py`, following exactly the same `MANDARINOS_BETA_ADMIN_TOKEN` pattern as the existing `/api/progress/all` endpoint. They allow listing and downloading `session_record_v1` files from the Railway volume without shell access.

### Files changed

| File | Change type | Notes |
|---|---|---|
| `scripts/ui_server.py` | **Extended** | +~90 lines: `/api/sessions/list` and `/api/sessions/get` inside `do_GET()` |
| `tests/test_session_admin_endpoints.py` | **New** | 34 tests (static source + handler unit tests) |
| `docs/session_intelligence_implementation_report.md` | Updated | This Slice 4 section |

### Endpoints

#### `GET /api/sessions/list?admin_token=TOKEN`

Returns a JSON listing of all valid `session_record_v1` files on the server.

```json
{
  "ok": true,
  "sessions_root": "data/sessions",
  "total_sessions": 4,
  "sessions": [
    {
      "learner_id": "learner_1779441865679",
      "session_id": "session_1780000000000",
      "path_relative": "learner_1779441865679/session_1780000000000.json",
      "schema_version": "session_record_v1",
      "created_at": "2026-06-29T14:00:00+12:00",
      "persona_id": "jianguo",
      "mode": "normal",
      "transcript_turn_count": 12,
      "file_size_bytes": 8421,
      "modified_time": "2026-06-29T02:00:00+00:00"
    }
  ]
}
```

**Security:** Invalid JSON files and files with wrong schema are silently skipped. No absolute filesystem paths are returned.

#### `GET /api/sessions/get?learner_id=LID&session_id=SID&admin_token=TOKEN`

Returns the exact `session_record_v1` JSON for one session.

**Security:** `learner_id` and `session_id` are validated against `^[a-zA-Z0-9_\-]{1,64}$` and `^[a-zA-Z0-9_\-\.]{1,128}$` respectively. A second defence-in-depth check confirms the resolved path is inside `data/sessions/`. Returns 400 for invalid IDs, 404 for missing files, 422 if the file exists but has the wrong schema.

### PowerShell commands: list → download → batch export

Set your app URL and token once:

```powershell
$APP = "https://YOUR-APP.up.railway.app"
$TOKEN = "beta_export_local"   # or your MANDARINOS_BETA_ADMIN_TOKEN
```

**Step 1 — List all captured sessions:**

```powershell
curl "$APP/api/sessions/list?admin_token=$TOKEN" | python -m json.tool
```

**Step 2 — Download one session:**

```powershell
$LID = "learner_1779441865679"
$SID = "session_1780000000000"

New-Item -ItemType Directory -Force -Path "data\sessions\$LID" | Out-Null
curl "$APP/api/sessions/get?learner_id=$LID&session_id=$SID&admin_token=$TOKEN" `
     -o "data\sessions\$LID\$SID.json"
```

**Step 3 — Download ALL sessions in one loop:**

```powershell
$APP = "https://YOUR-APP.up.railway.app"
$TOKEN = "beta_export_local"

$list = curl "$APP/api/sessions/list?admin_token=$TOKEN" | ConvertFrom-Json
foreach ($s in $list.sessions) {
    $lid = $s.learner_id
    $sid = $s.session_id
    New-Item -ItemType Directory -Force -Path "data\sessions\$lid" | Out-Null
    $out = "data\sessions\$lid\$sid.json"
    if (-not (Test-Path $out)) {
        curl "$APP/api/sessions/get?learner_id=$lid&session_id=$sid&admin_token=$TOKEN" -o $out
        Write-Host "Downloaded: $out"
    } else {
        Write-Host "Already exists: $out"
    }
}
```

**Step 4 — Run the batch exporter:**

```powershell
python scripts/export_unreviewed_sessions_batch.py --dry-run
python scripts/export_unreviewed_sessions_batch.py --write --no-stdout
```

Batch prompt written to: `data/review_exports/batches/batch_<date>_01.md`

### Security design

| Threat | Mitigation |
|---|---|
| Unauthorized access | `MANDARINOS_BETA_ADMIN_TOKEN` required; 403 on mismatch or absent |
| Path traversal via `learner_id` / `session_id` | Strict alphanumeric+hyphen+underscore regex (64/128 char max) |
| Symlink or path-escape attack | `Path.resolve().relative_to()` check after regex (defence-in-depth) |
| Returning non-session files | Schema check: only `session_record_v1` returned; all others → 404/422 |
| Mutation | No write/delete operations in either handler |

### Tests added

File: `tests/test_session_admin_endpoints.py` — **34 tests, 34 passing**

| Class | Coverage |
|---|---|
| `TestSourceStructure` | Endpoint routing, admin-token gate position, regex present, schema check, no-write guard, progress/all regression |
| `TestListEndpoint` | 403 on wrong/missing token; 200 empty; valid sessions returned; invalid JSON ignored; wrong schema ignored |
| `TestGetEndpoint` | 403 unauthorized; 400 missing params; path-traversal rejection (5 learner_id × 4 session_id variants); 404 not found; 200 exact JSON; 422 wrong schema |
| `TestNoMutation` | File mtime and content unchanged after list; unchanged after get |
| `TestProgressAllRegression` | `/api/progress/all` still returns 200 + `learners` key |

### Deviations from the architecture document

None. Read-only export endpoints are exactly the kind of additive tooling described in §Phase 1 of the architecture document.

---

## Phase 0 Slice 5 — One-command local review pipeline

**Date:** 2026-06-29  
**Directive:** MandarinOS Session Intelligence — Add one-command local review pipeline

### Summary

Phase 0 Slice 5 is complete. Three new files automate the full operational
workflow — from downloading Railway session files to producing a batch review
prompt — in a single command.

---

### Files added

| File | Purpose |
|---|---|
| `scripts/import_sessions_from_server.py` | Download missing `session_record_v1` files from Railway via the Slice 4 admin endpoints. Safe to run repeatedly; skips existing files by default. |
| `scripts/run_session_review_pipeline.py` | Orchestrates import → batch export → print/open in one command. |
| `tools/session_review.ps1` | PowerShell wrapper — reads env vars, calls the pipeline, prints next-step instructions. |
| `tools/session_review_sample_env.ps1` | Placeholder env file (no real secrets) for first-time setup reference. |
| `tests/test_session_review_pipeline.py` | 41 tests (all passing). |

---

### Normal user workflow

**First-time setup** — copy the example local config and fill in real values
(this file is `.gitignore`d and never committed):

```powershell
Copy-Item tools\session_review.local.example.ps1 tools\session_review.local.ps1
# Then edit tools\session_review.local.ps1 with real URL and token.
```

**Every review run** — from the repo root:

```powershell
.\review.ps1
```

The script automatically dot-sources `tools\session_review.local.ps1` (if
present) before reading environment variables, so no manual `$env:` setup is
needed once the local config file exists.

**Expected output:**

```
MandarinOS Session Review Pipeline
===================================
App URL    : https://...railway.app
Token      : beta****

[pipeline] Step 1: Importing sessions from Railway…
[import] 4 session(s) listed on server
[import] [local] sess_abc  (learner_xyz)
[import] [ok] sess_def  learner=learner_xyz  turns=12  → data/sessions/...

[pipeline] Step 2: Exporting unreviewed sessions…

[pipeline] Done.

  Batch prompt : data\review_exports\batches\batch_2026-06-29_01.md
  Manifest     : data\review_exports\batches\batch_2026-06-29_01_manifest.json

  Next steps:
  1. Open the batch prompt file above.
  2. Copy the entire contents.
  3. Paste into ChatGPT or Claude (Projects recommended).
  4. Save the AI response as a product_intel_v1 document.
```

---

### Script reference

#### `import_sessions_from_server.py`

```powershell
# Preview (no files written):
python scripts/import_sessions_from_server.py --dry-run

# Download missing sessions:
python scripts/import_sessions_from_server.py `
    --app-url $env:MANDARINOS_APP_URL `
    --admin-token $env:MANDARINOS_BETA_ADMIN_TOKEN

# Force re-download of existing files:
python scripts/import_sessions_from_server.py `
    --app-url $env:MANDARINOS_APP_URL `
    --admin-token $env:MANDARINOS_BETA_ADMIN_TOKEN `
    --overwrite
```

Flags: `--app-url`, `--admin-token`, `--out-root`, `--dry-run`, `--overwrite`, `--quiet`

#### `run_session_review_pipeline.py`

```powershell
# Full pipeline:
python scripts/run_session_review_pipeline.py `
    --app-url $env:MANDARINOS_APP_URL `
    --admin-token $env:MANDARINOS_BETA_ADMIN_TOKEN `
    --open

# Skip import, use only local sessions:
python scripts/run_session_review_pipeline.py --skip-import

# Dry-run (shows what would happen):
python scripts/run_session_review_pipeline.py --dry-run
```

Flags: `--app-url`, `--admin-token`, `--skip-import`, `--dry-run`, `--open`,
`--max-sessions`, `--include-reviewed`, `--sessions-root`, `--out-dir`

---

### Security design

| Concern | Mitigation |
|---|---|
| No hardcoded tokens | `--admin-token` from flag or `$MANDARINOS_BETA_ADMIN_TOKEN` env var only |
| Path traversal via `learner_id` / `session_id` | `_is_valid_path_component()` rejects `/`, `\`, `..`, empty, and other unsafe chars |
| Wrong schema written to disk | Schema check before `_atomic_write_json()`; failed sessions counted in `result.failed` |
| Existing files overwritten silently | Default: skip; `--overwrite` required explicitly |
| Multiple simultaneous runs | Atomic temp-file write (`tempfile.mkstemp` + `shutil.move`) |

---

### Tests added

File: `tests/test_session_review_pipeline.py` — **41 tests, 41 passing**

| Category | Tests |
|---|---|
| HTTP fetch: list endpoint | success, 403, 401, 500, connection error |
| Import: download | downloads missing, writes valid JSON, creates subdirectory |
| Import: skip | skips already-local, --overwrite re-downloads |
| Import: schema guard | rejects wrong schema, does not write bad file |
| Import: dry-run | skips all, writes nothing |
| Import: auth | 403 raises PermissionError |
| Import: path safety | path traversal in learner_id, session_id, empty IDs, parametrized path component tests |
| Pipeline: full flow | creates batch + manifest after import |
| Pipeline: clean exit | exits 1 cleanly when all sessions already reviewed |
| Pipeline: skip-import | runs batch export against local sessions only |
| PowerShell wrapper | file exists, no real tokens, reads env vars, calls pipeline script |
| Sample env file | file exists, placeholder-only content |
| ImportResult | summary lines, ok() true/false |
| Source checks | scripts exist, no hardcoded tokens, correct imports |

---

### Deviations from the architecture document

None. This slice automates the manual download steps already described in the
Slice 4 "PowerShell download commands" section, without adding any new data
structures or LLM calls.
