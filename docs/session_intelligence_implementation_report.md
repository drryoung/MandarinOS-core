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

### Next steps

1. Slice 4: structured findings writer — CLI to save the AI's Section G (`product_intel_rollup_v1`) output as a JSON file under `data/product_intel/rollups/`.
2. Slice 5: daily/weekly scheduled batch (cron or Railway scheduled task).
