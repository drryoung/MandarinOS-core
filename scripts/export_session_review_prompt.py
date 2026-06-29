"""
Session Intelligence — Phase 0 Slice 2: manual review export.

Converts one session_record_v1 JSON file into a Markdown prompt suitable
for manual AI review in ChatGPT / Claude.

Usage
-----
# Print to stdout:
python scripts/export_session_review_prompt.py data/sessions/<lid>/<sid>.json

# Write to file (auto-named under data/review_exports/):
python scripts/export_session_review_prompt.py data/sessions/<lid>/<sid>.json --write

# Explicit output path:
python scripts/export_session_review_prompt.py <input.json> --out path/to/out.md

Architecture reference: docs/session_intelligence_architecture.md §Phase 1
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
BASE_DATA_DIR = Path(os.environ.get("MANDARINOS_DATA_DIR", str(_DEFAULT_DATA_DIR)))
_REVIEW_EXPORTS_DIR = BASE_DATA_DIR / "review_exports"

_MISSING = "*(not recorded)*"
_SECTION_SEP = "\n---\n"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _val(record: Dict, *keys, default: str = _MISSING) -> str:
    """Safely navigate nested keys, returning a formatted string."""
    obj = record
    for k in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(k)
        if obj is None:
            return default
    return str(obj) if obj != "" else default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return default


def _atomic_write_md(path: Path, text: str) -> None:
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


def _default_output_path(record: Dict, input_path: Path) -> Path:
    lid = (record.get("learner_id") or "unknown").strip()
    sid = (record.get("session_id") or input_path.stem).strip()
    # Sanitise to safe filename characters
    lid = re.sub(r"[^\w\-]", "_", lid)[:64]
    sid = re.sub(r"[^\w\-]", "_", sid)[:128]
    return _REVIEW_EXPORTS_DIR / lid / f"{sid}_review_prompt.md"


# ── Prompt sections ───────────────────────────────────────────────────────────

def _render_header(record: Dict) -> str:
    lines = [
        "# MandarinOS — Session Review Prompt",
        "",
        "> **Instructions for the reviewing AI:**",
        "> Read the session data below carefully, then produce the structured analysis",
        "> requested in the **Review Tasks** section at the bottom of this document.",
        "> Respond in English unless a Chinese example is required for a suggestion.",
        "",
    ]
    return "\n".join(lines)


def _render_metadata(record: Dict) -> str:
    schema     = _val(record, "schema")
    session_id = _val(record, "session_id")
    learner_id = _val(record, "learner_id")
    created_at = _val(record, "created_at")
    persona_id = _val(record, "persona_id")
    mode       = _val(record, "mode")
    tier       = _val(record, "tier")
    duration   = _safe_int(record.get("duration_seconds"))
    dur_str    = f"{duration // 60}m {duration % 60}s" if duration else _MISSING

    flags = record.get("capture_flags") or {}
    transcript_present  = flags.get("transcript_present",  False)
    event_log_present   = flags.get("event_log_present",   False)
    transcript_truncated = flags.get("transcript_truncated", False)

    lines = [
        "## 1. Session Metadata",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Schema | `{schema}` |",
        f"| Session ID | `{session_id}` |",
        f"| Learner ID | `{learner_id}` |",
        f"| Created at | {created_at} |",
        f"| Persona | {persona_id} |",
        f"| Mode | {mode} |",
        f"| Tier | {tier} |",
        f"| Duration | {dur_str} |",
        f"| Transcript captured | {'Yes' if transcript_present else 'No'} |",
        f"| Event log captured | {'Yes' if event_log_present else 'No'} |",
        f"| Transcript truncated | {'**Yes — analysis may be incomplete**' if transcript_truncated else 'No'} |",
    ]
    return "\n".join(lines)


def _render_counters(record: Dict) -> str:
    c = record.get("counters") or {}

    def ci(key: str) -> str:
        v = c.get(key)
        return str(_safe_int(v)) if v is not None else _MISSING

    engines = c.get("engines_used")
    engines_str = ", ".join(engines) if isinstance(engines, list) and engines else _MISSING

    lines = [
        "## 2. Session Counters",
        "",
        f"| Counter | Value |",
        f"|---|---|",
        f"| Total turns | {ci('total_turns')} |",
        f"| Questions asked | {ci('questions_asked')} |",
        f"| Depth responses | {ci('depth_responses')} |",
        f"| Unmatched responses (hard) | {ci('unmatched_responses')} |",
        f"| Unmatched responses (soft) | {ci('soft_unmatched_responses')} |",
        f"| Recovery uses | {ci('recovery_uses')} |",
        f"| Successful recoveries | {ci('successful_recoveries')} |",
        f"| Conversational recoveries | {ci('conversational_recoveries')} |",
        f"| Successful conv. recoveries | {ci('successful_conversational_recoveries')} |",
        f"| Suggestion clicks | {ci('suggestion_clicks')} |",
        f"| Card opens | {ci('card_opens')} |",
        f"| Translation help uses | {ci('translation_help_uses')} |",
        f"| English reveal clicks | {ci('display_en_clicks')} |",
        f"| Pinyin reveal clicks | {ci('display_py_clicks')} |",
        f"| Hint clicks | {ci('hint_clicks')} |",
        f"| Engines used | {engines_str} |",
    ]
    return "\n".join(lines)


def _render_scorecard(record: Dict) -> str:
    m = record.get("metrics") or {}
    if not m:
        return "## 3. Scorecard\n\n" + _MISSING

    lines = ["## 3. Scorecard", ""]
    for key, value in m.items():
        if isinstance(value, dict):
            lines.append(f"**{key}:**")
            for k2, v2 in value.items():
                lines.append(f"  - {k2}: {v2}")
        else:
            lines.append(f"- **{key}:** {value}")

    return "\n".join(lines)


def _render_transcript(record: Dict) -> str:
    transcript: List[Dict] = record.get("transcript") or []

    header = ["## 4. Conversation Transcript", ""]

    if not transcript:
        return "\n".join(header) + "\n" + _MISSING

    lines = list(header)
    lines.append(
        "Turn | Role | Chinese | Pinyin | English | Frame | Engine | Turn UID"
    )
    lines.append("|---|---|---|---|---|---|---|---|")

    for entry in transcript:
        idx      = str(entry.get("idx", "?"))
        role     = (entry.get("role") or "?").lower()
        role_lbl = "👤 Learner" if role == "user" else "🤖 Persona"
        zh       = (entry.get("text_zh")  or "").replace("|", "｜").replace("\n", " ")
        py       = (entry.get("pinyin")   or "").replace("|", "｜").replace("\n", " ")
        en       = (entry.get("text_en")  or "").replace("|", "｜").replace("\n", " ")
        frame    = (entry.get("frame_id") or "").replace("|", "｜")
        engine   = (entry.get("engine")   or "").replace("|", "｜")
        uid      = (entry.get("turn_uid") or "").replace("|", "｜")

        # Flag empty fields so they are visible during review
        zh     = zh     if zh     else _MISSING
        py     = py     if py     else ("—" if role == "user" else _MISSING)
        en     = en     if en     else _MISSING
        frame  = frame  if frame  else _MISSING
        engine = engine if engine else "—"
        uid    = uid    if uid    else _MISSING

        lines.append(f"| {idx} | {role_lbl} | {zh} | {py} | {en} | {frame} | {engine} | {uid} |")

    # Count matched/unmatched learner turns for the reviewer
    learner_turns  = [e for e in transcript if (e.get("role") or "").lower() == "user"]
    matched_turns  = [e for e in learner_turns if e.get("matched") is True]
    unmatched_turns = [e for e in learner_turns if e.get("matched") is False]
    if learner_turns:
        lines.append("")
        lines.append(
            f"*{len(learner_turns)} learner turns — "
            f"{len(matched_turns)} matched, {len(unmatched_turns)} unmatched, "
            f"{len(learner_turns) - len(matched_turns) - len(unmatched_turns)} classification unknown.*"
        )

    return "\n".join(lines)


def _render_event_log(record: Dict) -> str:
    events: List[Dict] = record.get("event_log") or []

    header = ["## 5. UX Event Log", ""]
    if not events:
        return "\n".join(header) + "\n" + _MISSING

    lines = list(header)
    lines.append("| t_offset_ms | Event type | Frame | Kind / Engine |")
    lines.append("|---|---|---|---|")
    for ev in events:
        t      = str(ev.get("t_offset_ms", "?"))
        etype  = (ev.get("type")     or "?").replace("|", "｜")
        frame  = (ev.get("frame_id") or "—").replace("|", "｜")
        kind   = (ev.get("kind") or ev.get("engine") or "—").replace("|", "｜")
        lines.append(f"| {t} | {etype} | {frame} | {kind} |")

    # Brief event-type summary
    from collections import Counter
    type_counts = Counter(ev.get("type", "?") for ev in events)
    lines.append("")
    lines.append("**Event summary:** " + ", ".join(f"{k}: {v}" for k, v in type_counts.most_common()))

    return "\n".join(lines)


def _render_review_tasks() -> str:
    return """\
## 6. Review Tasks

Please analyse the session above and return **all** of the following sections.
Keep each section clearly labelled. Use the exact section headers shown.

---

### A. Learner Feedback (learner-facing, supportive tone)

Write 2–4 sentences the learner could read directly after the session:
- What they did well.
- One or two specific moments where a richer or more natural response was possible.
- An encouraging closing line.

Do **not** use a teacher-voice ("The correct answer is…"). Frame suggestions as options:
"You could also have said…" or "Another natural way to express this is…"

---

### B. Better Mandarin Responses

For each learner turn where a richer response was possible, provide a table:

| Turn # | Learner said | Could also say | Why it is more natural |
|---|---|---|---|

Include pinyin and English gloss for each suggested Chinese response.

---

### C. Recovery Phrase Opportunities

List any turn where the learner appeared confused, repeated themselves, or gave a
minimal/mismatched response, and suggest a recovery phrase they could have used:

| Turn # | Situation | Suggested recovery phrase | Pinyin | English |
|---|---|---|---|---|

---

### D. Suspected Bugs

For each turn where the app appeared to respond incorrectly, misunderstand the learner,
or fall back when it should not have:

```json
[
  {
    "turn_idx": 5,
    "category": "bug",
    "severity": "high",
    "title": "Short title of the problem",
    "observation": "What the learner said and what the app did.",
    "hypothesis": "Why this may have happened.",
    "recommendation": "Suggested code/content fix."
  }
]
```

Severity: `low` | `medium` | `high`

---

### E. UX Issues

List any friction points visible in the transcript or event log (e.g. repeated card opens,
back-to-back EN reveals, recovery uses clustered around one frame):

```json
[
  {
    "category": "ux",
    "severity": "medium",
    "title": "Short title",
    "evidence": "Which event types / turn indices support this.",
    "recommendation": "Suggested UX change."
  }
]
```

---

### F. Conversation-Design Improvements

List any frame sequencing, topic-transition, pacing, or naturalness issues:

```json
[
  {
    "category": "conversation_design",
    "severity": "low",
    "title": "Short title",
    "observation": "What felt unnatural or repetitive.",
    "recommendation": "Suggested frame/response/ordering improvement."
  }
]
```

---

### G. Product Intelligence Summary (product_intel_v1 shape)

Consolidate findings D–F into a single structured JSON block using the canonical schema:

```json
{
  "schema": "product_intel_v1",
  "session_id": "<session_id>",
  "generator": "manual_ai_review",
  "findings": [
    {
      "category": "bug|ux|conversation_design|content|enhancement",
      "severity": "low|medium|high",
      "title": "...",
      "evidence_turn_idx": [],
      "observation": "...",
      "hypothesis": "...",
      "recommendation": "..."
    }
  ],
  "session_health": {
    "flow": "good|fair|poor",
    "friction_score": 0,
    "notes": "..."
  }
}
```

---

### H. Recommended Next Cursor Tasks

List implementation tasks grouped by priority.
Format each task as a one-line directive a developer can copy directly into a Cursor prompt:

**Priority 1 — Critical bugs:**
- [ ] …

**Priority 2 — UX fixes:**
- [ ] …

**Priority 3 — Conversation-design improvements:**
- [ ] …

**Priority 4 — Enhancements / low priority:**
- [ ] …
"""


# ── Main renderer ─────────────────────────────────────────────────────────────

def render_review_prompt(record: Dict) -> str:
    """Convert a session_record_v1 dict into a Markdown review prompt string."""
    sections = [
        _render_header(record),
        _render_metadata(record),
        _render_counters(record),
        _render_scorecard(record),
        _render_transcript(record),
        _render_event_log(record),
        _render_review_tasks(),
    ]
    return _SECTION_SEP.join(sections)


# ── Public API ────────────────────────────────────────────────────────────────

def export_from_path(
    input_path: Path,
    output_path: Optional[Path] = None,
    *,
    write: bool = False,
) -> str:
    """
    Load a session_record_v1 JSON file and render a Markdown review prompt.

    Args:
        input_path:  Path to the session_record_v1 JSON file.
        output_path: Explicit output path. When None and write=True, auto-derived.
        write:       If True, write the prompt to a file in addition to returning it.

    Returns:
        The rendered Markdown string.

    Raises:
        FileNotFoundError: input_path does not exist.
        ValueError: file is not a valid session_record_v1 dict.
    """
    raw = input_path.read_text(encoding="utf-8")
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise ValueError(f"Expected a JSON object, got {type(record).__name__}")

    prompt = render_review_prompt(record)

    if write:
        out = output_path or _default_output_path(record, input_path)
        _atomic_write_md(out, prompt)
        print(f"[export_session_review_prompt] Written to: {out}", file=sys.stderr, flush=True)

    return prompt


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Export a session_record_v1 file as a Markdown review prompt "
            "for manual AI analysis."
        )
    )
    p.add_argument(
        "input",
        type=Path,
        help="Path to a session_record_v1 JSON file.",
    )
    p.add_argument(
        "--write",
        action="store_true",
        default=False,
        help=(
            "Write the prompt to data/review_exports/{learner_id}/{session_id}_review_prompt.md "
            "(in addition to printing to stdout)."
        ),
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar="PATH",
        help="Explicit output path. Implies --write.",
    )
    p.add_argument(
        "--no-stdout",
        action="store_true",
        default=False,
        help="Suppress stdout output (useful when --write or --out is set).",
    )
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)

    input_path: Path = args.input.resolve()
    if not input_path.is_file():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    write = args.write or (args.out is not None)
    try:
        prompt = export_from_path(input_path, output_path=args.out, write=write)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not args.no_stdout:
        print(prompt)


if __name__ == "__main__":
    main()
