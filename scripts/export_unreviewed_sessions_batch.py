"""
Session Intelligence — Phase 0 Slice 3: batch export of unreviewed sessions.

Scans data/sessions/ for session_record_v1 files that have not yet been
included in any previous batch manifest, then produces:
  - data/review_exports/batches/batch_<YYYY-MM-DD>_<seq>.md   (prompt)
  - data/review_exports/batches/batch_<YYYY-MM-DD>_<seq>_manifest.json

Usage
-----
# Dry run (report which sessions would be included, write nothing):
python scripts/export_unreviewed_sessions_batch.py --dry-run

# Write batch prompt + manifest:
python scripts/export_unreviewed_sessions_batch.py --write

# Custom roots:
python scripts/export_unreviewed_sessions_batch.py \\
    --sessions-root data/sessions \\
    --out-dir data/review_exports/batches \\
    --max-sessions 20 \\
    --write

# Include sessions already in previous batches:
python scripts/export_unreviewed_sessions_batch.py --include-reviewed --write

# Suppress stdout:
python scripts/export_unreviewed_sessions_batch.py --write --no-stdout

Architecture reference: docs/session_intelligence_architecture.md §Phase 3
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ── Paths ─────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
BASE_DATA_DIR = Path(os.environ.get("MANDARINOS_DATA_DIR", str(_DEFAULT_DATA_DIR)))

_DEFAULT_SESSIONS_ROOT = BASE_DATA_DIR / "sessions"
_DEFAULT_OUT_DIR = BASE_DATA_DIR / "review_exports" / "batches"

_MISSING = "*(not recorded)*"
_SECTION_SEP = "\n---\n"

# Maximum sessions per batch (caller can override with --max-sessions)
_DEFAULT_MAX_SESSIONS = 20

SCHEMA_VERSION = "session_record_v1"
MANIFEST_SCHEMA = "batch_manifest_v1"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return default


def _val(d: Dict, *keys, default: str = _MISSING) -> str:
    obj = d
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k)
        if obj is None:
            return default
    s = str(obj).strip()
    return s if s else default


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        shutil.move(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Session discovery ─────────────────────────────────────────────────────────

def _load_session(path: Path) -> Optional[Dict]:
    """Return parsed session dict if valid session_record_v1, else None."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        if raw.get("schema") != SCHEMA_VERSION:
            return None
        return raw
    except Exception:
        return None


def _session_timestamp(record: Dict, path: Path) -> str:
    """Best-effort ISO timestamp for sorting; falls back to file mtime."""
    ts = (record.get("created_at") or "").strip()
    if ts:
        return ts
    mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=datetime.timezone.utc)
    return mtime.isoformat(timespec="seconds")


def find_all_sessions(sessions_root: Path) -> List[Tuple[Path, Dict]]:
    """Return list of (path, record) for every valid session_record_v1 file."""
    results = []
    if not sessions_root.is_dir():
        return results
    for p in sorted(sessions_root.rglob("*.json")):
        record = _load_session(p)
        if record is not None:
            results.append((p, record))
    # Sort by timestamp oldest-first
    results.sort(key=lambda pr: _session_timestamp(pr[1], pr[0]))
    return results


# ── Session type classification ───────────────────────────────────────────────

def classify_session_type(record: Dict) -> str:
    """Return a session-type label based on conversational content.

    Labels (mutually exclusive, ordered from most-degenerate to normal):

    aborted_session       — No transcript at all (capture started, immediately ended).
    empty_session         — Transcript present but zero conversational turns (both
                            partner and user roles absent, or only the opening frame).
    recovery_only_session — Only recovery/repair moves, no genuine learner answer
                            and no substantive partner reply.
    normal_session        — At least one real learner answer and one partner reply.

    Empty / aborted / recovery-only sessions are excluded from normal session-health
    averages in review exports unless --include-empty is passed.
    """
    transcript = record.get("transcript") or []
    if not transcript:
        return "aborted_session"

    partner_turns = [t for t in transcript if t.get("role") == "partner"]
    learner_turns  = [t for t in transcript if t.get("role") == "user"]

    if not partner_turns and not learner_turns:
        return "empty_session"

    # Count substantive turns:
    # - partner: must have text_zh with more than a single clarification/rephrase prefix
    # - learner: must have text_zh (not empty)
    _REPHRASE_PREFIXES = ("我是问：", "我是在问：", "我刚刚问的是：", "我的意思是：")
    _RECOVERY_ONLY_TEXT = frozenset({
        "再说一遍", "再说一次", "慢一点", "说慢", "啊", "嗯", "什么意思",
    })

    def _is_substantive_partner(turn: dict) -> bool:
        zh = (turn.get("text_zh") or "").strip()
        if not zh:
            return False
        # Opening frame with no learner context counts as substantive.
        # Clarification-only lines (我是问：…) are NOT substantive on their own.
        return not any(zh.startswith(p) for p in _REPHRASE_PREFIXES)

    def _is_substantive_learner(turn: dict) -> bool:
        zh = (turn.get("text_zh") or "").strip()
        return bool(zh) and zh not in _RECOVERY_ONLY_TEXT and len(zh) >= 2

    substantive_partner = sum(1 for t in partner_turns if _is_substantive_partner(t))
    substantive_learner = sum(1 for t in learner_turns  if _is_substantive_learner(t))

    if substantive_learner == 0:
        # Learner never gave a substantive response.
        if len(learner_turns) == 0:
            # No learner turns at all — only an opening frame (or nothing).
            return "empty_session"
        # Learner turns exist but are all recovery phrases (再说一遍, 啊, etc.)
        return "recovery_only_session"

    return "normal_session"


def is_excluded_session_type(session_type: str) -> bool:
    """True for session types that should be excluded from normal health averages."""
    return session_type in ("aborted_session", "empty_session", "recovery_only_session")


# ── Manifest tracking ─────────────────────────────────────────────────────────

def _load_reviewed_session_ids(out_dir: Path) -> Set[str]:
    """Return the set of session_ids already included in any previous manifest."""
    seen: Set[str] = set()
    if not out_dir.is_dir():
        return seen
    for p in sorted(out_dir.glob("*_manifest.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for entry in (data.get("included_sessions") or []):
                sid = (entry.get("session_id") or "").strip()
                if sid:
                    seen.add(sid)
        except Exception:
            continue
    return seen


def _next_batch_path(out_dir: Path, today: str) -> Tuple[Path, Path, str]:
    """Determine the next available batch paths for today (seq 01, 02, …)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    seq = 1
    while True:
        batch_id = f"batch_{today}_{seq:02d}"
        prompt_path = out_dir / f"{batch_id}.md"
        manifest_path = out_dir / f"{batch_id}_manifest.json"
        if not prompt_path.exists() and not manifest_path.exists():
            return prompt_path, manifest_path, batch_id
        seq += 1


# ── Prompt rendering ──────────────────────────────────────────────────────────

def _render_batch_header(sessions: List[Tuple[Path, Dict]], batch_id: str) -> str:
    n = len(sessions)
    learner_ids = sorted({(r.get("learner_id") or "unknown") for _, r in sessions})
    timestamps = [
        _session_timestamp(r, p) for p, r in sessions
        if _session_timestamp(r, p) != _MISSING
    ]
    date_range = (
        f"{min(timestamps)[:10]} → {max(timestamps)[:10]}"
        if timestamps else _MISSING
    )
    total_turns = sum(len(r.get("transcript") or []) for _, r in sessions)

    lines = [
        f"# MandarinOS — Batch Review Prompt",
        "",
        f"> **Batch ID:** `{batch_id}`  ",
        f"> **Sessions in batch:** {n}  ",
        f"> **Learner IDs:** {', '.join(learner_ids)}  ",
        f"> **Date range:** {date_range}  ",
        f"> **Total transcript turns:** {total_turns}",
        "",
        "> **Instructions for the reviewing AI:**",
        "> This batch contains evidence from {n} MandarinOS Mandarin-learning sessions.".format(n=n),
        "> Read all sessions carefully before producing analysis.",
        "> Return all sections requested in **Part 4 — Cross-Session Review Instructions** below.",
        ">",
        "> **Important constraints for your analysis:**",
        "> - Do not overgeneralise from a small number of sessions.",
        "> - Separate learner-specific issues from app/product issues clearly.",
        "> - Cite evidence by session_id and turn index (e.g. `session_X / turn 4`).",
        "> - Do not recommend large architecture changes unless strongly justified by repeated evidence.",
        "> - Prefer small, testable Cursor implementation tasks.",
        "> - Classify each finding as `confirmed` (seen ≥3 times), `suspected` (seen 2 times), or `observe-only` (seen once).",
    ]
    return "\n".join(lines)


def _render_inventory_table(sessions: List[Tuple[Path, Dict]]) -> str:
    lines = [
        "## Part 1 — Session Inventory",
        "",
        "| # | Session ID | Learner ID | Persona | Mode | Timestamp | Turns |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, (p, r) in enumerate(sessions, 1):
        sid     = (r.get("session_id") or "").strip() or _MISSING
        lid     = (r.get("learner_id") or "").strip() or _MISSING
        persona = (r.get("persona_id") or "").strip() or _MISSING
        mode    = (r.get("mode") or "").strip() or _MISSING
        ts      = _session_timestamp(r, p)[:19] if _session_timestamp(r, p) != _MISSING else _MISSING
        turns   = str(len(r.get("transcript") or []))
        lines.append(f"| {i} | `{sid}` | `{lid}` | {persona} | {mode} | {ts} | {turns} |")
    return "\n".join(lines)


def _render_counters_inline(r: Dict) -> str:
    c = r.get("counters") or {}
    if not c:
        return _MISSING
    parts = []
    for k in ("total_turns", "recovery_uses", "unmatched_responses",
              "card_opens", "display_en_clicks", "hint_clicks"):
        v = c.get(k)
        if v is not None:
            parts.append(f"{k}: {_safe_int(v)}")
    engines = c.get("engines_used")
    if isinstance(engines, list) and engines:
        parts.append("engines: " + ", ".join(engines))
    return " | ".join(parts) if parts else _MISSING


def _render_event_log_summary(r: Dict) -> str:
    events = r.get("event_log") or []
    if not events:
        return _MISSING
    counts = Counter(e.get("type", "?") for e in events)
    return ", ".join(f"{k}: {v}" for k, v in counts.most_common())


def _render_transcript_table(r: Dict) -> str:
    transcript = r.get("transcript") or []
    if not transcript:
        return _MISSING

    lines = [
        "| # | Role | Chinese | Pinyin | English | Frame | Engine | UID |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for entry in transcript:
        idx    = str(entry.get("idx", "?"))
        role   = (entry.get("role") or "?").lower()
        lbl    = "👤" if role == "user" else "🤖"
        zh     = (entry.get("text_zh")  or "").replace("|", "｜").replace("\n", " ") or "—"
        py     = (entry.get("pinyin")   or "").replace("|", "｜").replace("\n", " ") or ("—" if role == "user" else _MISSING)
        en     = (entry.get("text_en")  or "").replace("|", "｜").replace("\n", " ") or "—"
        frame  = (entry.get("frame_id") or "").replace("|", "｜") or "—"
        engine = (entry.get("engine")   or "").replace("|", "｜") or "—"
        uid    = (entry.get("turn_uid") or "").replace("|", "｜") or "—"
        lines.append(f"| {idx} | {lbl} | {zh} | {py} | {en} | {frame} | {engine} | {uid} |")
    return "\n".join(lines)


def _render_session_block(idx: int, path: Path, record: Dict) -> str:
    sid     = (record.get("session_id") or "").strip() or _MISSING
    lid     = (record.get("learner_id") or "").strip() or _MISSING
    persona = (record.get("persona_id") or "").strip() or _MISSING
    mode    = (record.get("mode") or "normal").strip()
    ts      = _session_timestamp(record, path)
    dur     = _safe_int(record.get("duration_seconds"))
    dur_str = f"{dur // 60}m {dur % 60}s" if dur else _MISSING

    flags = record.get("capture_flags") or {}
    truncated = flags.get("transcript_truncated", False)

    lines = [
        f"### Session {idx}: `{sid}`",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Learner ID | `{lid}` |",
        f"| Persona | {persona} |",
        f"| Mode | {mode} |",
        f"| Timestamp | {ts} |",
        f"| Duration | {dur_str} |",
        f"| Transcript truncated | {'**Yes — analysis may be incomplete**' if truncated else 'No'} |",
        "",
        f"**Counters:** {_render_counters_inline(record)}",
        "",
        f"**UX Event Log Summary:** {_render_event_log_summary(record)}",
        "",
        "**Transcript:**",
        "",
        _render_transcript_table(record),
    ]
    return "\n".join(lines)


def _render_per_session_evidence(sessions: List[Tuple[Path, Dict]]) -> str:
    header = ["## Part 2 — Per-Session Transcripts and Evidence", ""]
    blocks = [_render_session_block(i, p, r) for i, (p, r) in enumerate(sessions, 1)]
    return "\n".join(header) + "\n" + _SECTION_SEP.join(blocks)


def _render_scorecard_section(sessions: List[Tuple[Path, Dict]]) -> str:
    lines = ["## Part 3 — Scorecards", ""]
    for i, (p, r) in enumerate(sessions, 1):
        sid = (r.get("session_id") or "").strip() or f"session_{i}"
        m = r.get("metrics") or {}
        lines.append(f"**Session {i} (`{sid}`):**")
        if m:
            for k, v in m.items():
                if isinstance(v, dict):
                    lines.append(f"  - {k}: " + ", ".join(f"{k2}={v2}" for k2, v2 in v.items()))
                else:
                    lines.append(f"  - {k}: {v}")
        else:
            lines.append(f"  {_MISSING}")
        lines.append("")
    return "\n".join(lines)


def _render_cross_session_review_tasks(n_sessions: int) -> str:
    return f"""\
## Part 4 — Cross-Session Review Instructions

You have reviewed **{n_sessions} session(s)** above.
Please produce all sections below, clearly labelled, in the order shown.
Use the exact section headers.

---

### A. Learner Feedback Patterns

What patterns did you observe across learners?
- What did learners do well?
- What did learners consistently struggle with?
- What 2–3 sentence feedback could be given to a typical learner?

Frame suggestions as options ("You could also have said…"), not corrections.

---

### B. Better Mandarin Response Patterns

List the most common opportunities for richer responses across all sessions.

| Session | Turn # | Learner said | Could also say | Why more natural |
|---|---|---|---|---|

Include pinyin and English gloss for each Chinese suggestion.

---

### C. Repeated Recovery Phrase Opportunities

List situations where the app repeatedly failed to detect confusion or where
learners repeatedly gave minimal/mismatched responses.

| Session | Turn # | Situation | Suggested recovery phrase | Pinyin |
|---|---|---|---|---|

---

### D. Suspected Bugs

List each potential bug with classification.

```json
[
  {{
    "classification": "confirmed|suspected|observe-only",
    "category": "bug",
    "severity": "low|medium|high",
    "title": "...",
    "evidence": [{{"session_id": "...", "turn_idx": 0}}],
    "observation": "...",
    "hypothesis": "...",
    "recommendation": "..."
  }}
]
```

Classification rules:
- `confirmed`: seen independently in ≥3 sessions or turns
- `suspected`: seen in 2 sessions/turns
- `observe-only`: seen once; flag but do not act yet

---

### E. UX Issues

```json
[
  {{
    "classification": "confirmed|suspected|observe-only",
    "category": "ux",
    "severity": "low|medium|high",
    "title": "...",
    "evidence": "which sessions/event types",
    "recommendation": "..."
  }}
]
```

---

### F. Conversation-Design Findings

```json
[
  {{
    "classification": "confirmed|suspected|observe-only",
    "category": "conversation_design",
    "severity": "low|medium|high",
    "title": "...",
    "observation": "...",
    "recommendation": "..."
  }}
]
```

---

### G. Product Intelligence Rollup (product_intel_rollup_v1 shape)

Synthesise findings D–F into a single structured JSON rollup:

```json
{{
  "schema": "product_intel_rollup_v1",
  "batch_id": "<batch_id>",
  "sessions_analysed": {n_sessions},
  "generator": "manual_ai_review",
  "top_findings": [
    {{
      "category": "bug|ux|conversation_design|content|enhancement",
      "classification": "confirmed|suspected|observe-only",
      "severity": "low|medium|high",
      "title": "...",
      "count": 1,
      "recommendation": "..."
    }}
  ],
  "trends": {{
    "avg_turns": 0,
    "avg_unmatched_ratio": 0.0,
    "recovery_use_rate": 0.0,
    "notes": "..."
  }},
  "session_health_summary": "good|fair|poor",
  "recommended_focus": []
}}
```

---

### H. Prioritised Cursor Task List

List implementation tasks grouped by priority.
Copy each task directly into a Cursor prompt.

**P0 — Critical bugs (block sessions or lose data):**
- [ ] …

**P1 — High-impact fixes (frequent friction or clear bug):**
- [ ] …

**P2 — Conversation-design and UX improvements:**
- [ ] …

**Observe — Monitor in next batch before acting:**
- [ ] …
"""


def render_batch_prompt(
    sessions: List[Tuple[Path, Dict]],
    batch_id: str,
) -> str:
    """Render the full Markdown batch review prompt."""
    parts = [
        _render_batch_header(sessions, batch_id),
        _render_inventory_table(sessions),
        _render_per_session_evidence(sessions),
        _render_scorecard_section(sessions),
        _render_cross_session_review_tasks(len(sessions)),
    ]
    return _SECTION_SEP.join(parts)


# ── Manifest ──────────────────────────────────────────────────────────────────

def build_manifest(
    batch_id: str,
    sessions: List[Tuple[Path, Dict]],
    sessions_root: Path,
    out_dir: Path,
    prompt_path: Path,
) -> Dict:
    try:
        created_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        created_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    included = []
    for p, r in sessions:
        included.append({
            "learner_id":            (r.get("learner_id") or "").strip() or None,
            "session_id":            (r.get("session_id") or "").strip() or None,
            "source_path":           str(p),
            "timestamp":             _session_timestamp(r, p),
            "transcript_turn_count": len(r.get("transcript") or []),
        })

    return {
        "schema":              MANIFEST_SCHEMA,
        "batch_id":            batch_id,
        "created_at":          created_at,
        "sessions_root":       str(sessions_root),
        "output_prompt_path":  str(prompt_path),
        "session_count":       len(sessions),
        "included_sessions":   included,
        "status":              "exported_for_manual_ai_review",
    }


def _render_excluded_sessions_appendix(
    excluded: List[Tuple[Path, Dict, str]],
) -> str:
    """Render a Markdown appendix listing excluded sessions without including them
    in session-health averages.  Excluded sessions are classified but not analysed."""
    lines = [
        "",
        "---",
        "",
        "## Appendix — Excluded Sessions (not in health averages)",
        "",
        "> These sessions were **not** included in the analysis above because they contain",
        "> zero conversational turns, were aborted before the learner responded, or consist",
        "> only of recovery/repair moves.  They are recorded here for completeness.",
        "> Use `--include-empty` to include them in a future normal batch.",
        "",
        "| Session ID | Learner | Timestamp | Type | Transcript turns |",
        "|---|---|---|---|---|",
    ]
    for p, r, stype in excluded:
        sid   = (r.get("session_id") or "").strip() or "*(unknown)*"
        lid   = (r.get("learner_id") or "").strip() or "*(unknown)*"
        ts    = _session_timestamp(r, p)[:19]
        turns = len(r.get("transcript") or [])
        lines.append(f"| `{sid}` | {lid} | {ts} | `{stype}` | {turns} |")
    return "\n".join(lines) + "\n"


# ── Main logic ────────────────────────────────────────────────────────────────

def run_batch_export(
    *,
    sessions_root: Path,
    out_dir: Path,
    max_sessions: int,
    include_reviewed: bool,
    include_empty: bool,
    dry_run: bool,
    stdout: bool,
) -> int:
    """
    Core logic. Returns exit code (0 = ok, 1 = nothing to do).

    Unless include_empty=True, aborted / empty / recovery-only sessions are
    excluded from the normal batch and listed in a separate side-section of the
    batch prompt so reviewers are aware of them without skewing health averages.
    """
    # 1. Find all valid session files
    all_sessions = find_all_sessions(sessions_root)
    if not all_sessions:
        msg = f"No session_record_v1 files found under {sessions_root}"
        print(msg, file=sys.stderr)
        return 1

    # 2. Determine which session IDs are already reviewed
    if include_reviewed:
        reviewed_ids: Set[str] = set()
    else:
        reviewed_ids = _load_reviewed_session_ids(out_dir)

    # 3. Filter to unreviewed
    unreviewed = [
        (p, r) for p, r in all_sessions
        if (r.get("session_id") or "").strip() not in reviewed_ids
    ]

    if not unreviewed:
        print("No unreviewed sessions found. All sessions are already included in previous batches.", file=sys.stderr)
        return 1

    # 3b. Separate excluded (empty/aborted/recovery-only) from normal sessions.
    normal_candidates: List[Tuple[Path, Dict]] = []
    excluded_sessions: List[Tuple[Path, Dict, str]] = []  # (path, record, session_type)
    for p, r in unreviewed:
        stype = classify_session_type(r)
        if not include_empty and is_excluded_session_type(stype):
            excluded_sessions.append((p, r, stype))
        else:
            normal_candidates.append((p, r))

    candidates = normal_candidates

    # 4. Cap to max_sessions
    selected = candidates[:max_sessions]
    skipped = len(candidates) - len(selected)

    # 5. Dry run: report and exit
    if dry_run:
        print(f"[dry-run] {len(selected)} normal session(s) would be included in next batch:")
        for p, r in selected:
            sid = (r.get("session_id") or "?").strip()
            lid = (r.get("learner_id") or "?").strip()
            ts  = _session_timestamp(r, p)[:19]
            turns = len(r.get("transcript") or [])
            print(f"  {sid}  learner={lid}  ts={ts}  turns={turns}  path={p}")
        if skipped:
            print(f"  (+{skipped} more would be deferred to subsequent batches)")
        if excluded_sessions:
            print(f"  ({len(excluded_sessions)} excluded: aborted/empty/recovery-only — use --include-empty to include)")
            for p, r, stype in excluded_sessions:
                sid = (r.get("session_id") or "?").strip()
                turns = len(r.get("transcript") or [])
                print(f"    [excluded:{stype}]  {sid}  turns={turns}")
        return 0

    if not selected and not excluded_sessions:
        print("No sessions to export.", file=sys.stderr)
        return 1

    # 6. Determine batch paths
    today = datetime.date.today().isoformat()
    prompt_path, manifest_path, batch_id = _next_batch_path(out_dir, today)

    # 7. Render and write prompt (normal sessions + excluded appendix)
    if selected:
        prompt = render_batch_prompt(selected, batch_id)
    else:
        prompt = f"# MandarinOS — Batch Review Prompt\n\n> **Batch ID:** `{batch_id}`\n\n*(No normal sessions in this batch.)*\n"

    if excluded_sessions:
        prompt += _render_excluded_sessions_appendix(excluded_sessions)

    _atomic_write(prompt_path, prompt)

    # 8. Build and write manifest (includes both normal and excluded for tracking)
    all_selected_for_manifest = [(p, r) for p, r in selected] + [
        (p, r) for p, r, _ in excluded_sessions
    ]
    manifest = build_manifest(batch_id, all_selected_for_manifest, sessions_root, out_dir, prompt_path)
    # Annotate excluded sessions in manifest
    manifest["excluded_session_count"] = len(excluded_sessions)
    manifest["excluded_session_ids"] = [
        {"session_id": (r.get("session_id") or "").strip(), "type": stype}
        for _, r, stype in excluded_sessions
    ]
    _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

    # 9. Report
    summary = (
        f"[batch export] {len(selected)} session(s) → {prompt_path}\n"
        f"[batch export] manifest  → {manifest_path}\n"
        f"[batch export] batch_id  = {batch_id}"
    )
    if skipped:
        summary += f"\n[batch export] {skipped} additional session(s) deferred (--max-sessions={max_sessions})"
    if excluded_sessions:
        summary += f"\n[batch export] {len(excluded_sessions)} excluded (aborted/empty/recovery-only — not in health averages)"
    print(summary, file=sys.stderr)

    if stdout:
        print(prompt)

    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Find unreviewed session_record_v1 files and export them as a "
            "batch Markdown prompt for manual AI review."
        )
    )
    p.add_argument(
        "--sessions-root",
        type=Path,
        default=_DEFAULT_SESSIONS_ROOT,
        metavar="DIR",
        help=f"Root directory to scan for session_record_v1 files. Default: {_DEFAULT_SESSIONS_ROOT}",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=_DEFAULT_OUT_DIR,
        metavar="DIR",
        help=f"Directory for batch prompt + manifest output. Default: {_DEFAULT_OUT_DIR}",
    )
    p.add_argument(
        "--max-sessions",
        type=int,
        default=_DEFAULT_MAX_SESSIONS,
        metavar="N",
        help=f"Maximum sessions per batch. Default: {_DEFAULT_MAX_SESSIONS}",
    )
    p.add_argument(
        "--include-reviewed",
        action="store_true",
        default=False,
        help="Include sessions already present in previous batch manifests.",
    )
    p.add_argument(
        "--write",
        action="store_true",
        default=False,
        help="Write batch prompt and manifest to --out-dir.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report which sessions would be included without writing any files.",
    )
    p.add_argument(
        "--no-stdout",
        action="store_true",
        default=False,
        help="Suppress stdout output of the batch prompt (useful with --write).",
    )
    p.add_argument(
        "--include-empty",
        action="store_true",
        default=False,
        help=(
            "Include aborted / empty / recovery-only sessions in normal health averages. "
            "By default these are listed in a separate appendix and excluded from analysis."
        ),
    )
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if not args.write and not args.dry_run:
        print(
            "Nothing to do: pass --write to produce files or --dry-run to preview.",
            file=sys.stderr,
        )
        sys.exit(0)

    if args.dry_run and args.write:
        print("--dry-run and --write are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    code = run_batch_export(
        sessions_root=args.sessions_root.resolve(),
        out_dir=args.out_dir.resolve(),
        max_sessions=max(1, args.max_sessions),
        include_reviewed=args.include_reviewed,
        include_empty=args.include_empty,
        dry_run=args.dry_run,
        stdout=(not args.no_stdout) and args.write,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
