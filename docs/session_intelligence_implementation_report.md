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

### Next steps

1. Phase 2: structured findings writer — save the AI's Section G output as a `product_intel_v1` JSON file via a tiny CLI/helper.
2. Phase 3: aggregation rollup — aggregate `product_intel_v1` files into `product_intel_rollup_v1`.
