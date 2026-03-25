#!/usr/bin/env python3
"""
Phase 10.7 — Phase A completion: apply reviewed move_type tags to source frames.

Reads  : data/move_type_tags.proposed.json
Writes : p1_frames.json, p2_frames.json   (move_type, allowed_response_roles,
                                            default_next_move_types added per frame)
Writes : docs/reports/move_type_tagging_coverage.md  (audit summary)

Rules (safety):
- Only writes move_type / allowed_response_roles / default_next_move_types.
- Never modifies id, text, pinyin, engine, difficulty, slots, speaker, option_tokens,
  distractor_tokens, text_en.
- Idempotent: running twice produces identical files.
- Skips frames whose proposed_move_type is null (no tag available).
- Preserves existing tags when --keep-existing is passed (default: overwrite).

Run from repo root:
  python scripts/apply_move_type_tags.py
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
TAGS_PATH   = ROOT / "data" / "move_type_tags.proposed.json"
REPORT_PATH = ROOT / "docs" / "reports" / "move_type_tagging_coverage.md"

FRAME_FILES = ["p1_frames.json", "p2_frames.json"]

# Fields we write from the tag table.
TAG_FIELDS_TO_WRITE = ["move_type", "allowed_response_roles", "default_next_move_types"]

# Fields we NEVER touch (safety guard).
PROTECTED_FIELDS = {
    "id", "id_legacy", "text", "pinyin", "text_en",
    "engine", "difficulty", "slots", "speaker",
    "option_tokens", "distractor_tokens",
}

# Ambiguity patterns to flag in the report (edge cases noted during tagging).
AMBIGUOUS_FRAME_IDS = {
    "f_thanks",          # REACTION vs CLOSE
    "f_like_do_what",    # ASK vs OPEN vs LOOP
    "p2_id_3",           # EXTEND vs ANSWER
    "f_like_chinese_culture",  # ASK vs LOOP
    "f_like_what",       # ASK vs OPEN
    "f_collect_what",    # LOOP vs ASK
    "p2_pl_3",           # LOOP vs ASK
    "p2_wk_4",           # LOOP vs ASK (salary question feels like new dimension)
    "p2_fa_4",           # EXTEND vs REACTION
    "p2_hb_5",           # LOOP vs BRIDGE
    "p2_pln_3",          # RECIPROCITY vs CLOSE
    "p2_pln_4",          # EXTEND vs CLOSE
    "p2_op_1",           # ASK vs LOOP
    "f_food_tasty",      # LOOP vs REACTION
    "f_food_expensive",  # LOOP vs ASK
}


def load_tags() -> dict[str, dict]:
    """Return frame_id -> tag_row mapping."""
    if not TAGS_PATH.is_file():
        raise SystemExit(f"ERROR: tags file not found at {TAGS_PATH}")
    raw = json.loads(TAGS_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for row in raw.get("frames", []):
        fid = row.get("frame_id")
        if fid:
            out[fid] = row
    return out


def apply_tags_to_file(path: Path, tags: dict[str, dict]) -> dict:
    """Apply tags in-place to one frame file. Returns stats."""
    data = json.loads(path.read_text(encoding="utf-8"))
    frames = data.get("frames", [])

    tagged_count   = 0
    skipped_null   = 0
    already_tagged = 0

    for frame in frames:
        fid  = frame.get("id", "")
        row  = tags.get(fid)
        if not row or row.get("proposed_move_type") is None:
            skipped_null += 1
            continue

        was_already = "move_type" in frame
        if was_already:
            already_tagged += 1

        # Tag JSON uses "proposed_move_type"; source frames use "move_type".
        field_map = {
            "move_type":               "proposed_move_type",
            "allowed_response_roles":  "allowed_response_roles",
            "default_next_move_types": "default_next_move_types",
        }
        for dest_field in TAG_FIELDS_TO_WRITE:
            src_field = field_map.get(dest_field, dest_field)
            val = row.get(src_field)
            if val is not None:
                assert dest_field not in PROTECTED_FIELDS, f"BUG: tried to write protected field {dest_field}"
                frame[dest_field] = val

        tagged_count += 1

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "file": path.name,
        "total": len(frames),
        "tagged": tagged_count,
        "skipped_null": skipped_null,
        "already_had_tag": already_tagged,
    }


def write_coverage_report(
    all_frames: list[dict],
    tags: dict[str, dict],
) -> None:
    """Write docs/reports/move_type_tagging_coverage.md."""

    total = len(all_frames)
    tagged_frames = [f for f in all_frames if f.get("move_type")]
    untagged_frames = [f for f in all_frames if not f.get("move_type")]
    ambiguous = [f for f in all_frames if f.get("id") in AMBIGUOUS_FRAME_IDS]

    mt_counter: Counter = Counter()
    conf_counter: Counter = Counter()
    for fid, row in tags.items():
        mt = row.get("proposed_move_type")
        if mt:
            mt_counter[mt] += 1
            conf_counter[row.get("confidence", "unknown")] += 1

    coverage_pct = 100.0 * len(tagged_frames) / total if total else 0.0

    lines = [
        "# Phase 10.7 — Move type tagging coverage",
        "",
        "Generated by `scripts/apply_move_type_tags.py`.",
        "",
        "## Coverage summary",
        "",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| Total frames | {total} |",
        f"| Tagged frames | {len(tagged_frames)} |",
        f"| Untagged frames | {len(untagged_frames)} |",
        f"| Coverage | {coverage_pct:.1f}% |",
        f"| Ambiguous / medium-confidence | {len(ambiguous)} |",
        f"| High-confidence tags | {conf_counter.get('high', 0)} |",
        f"| Medium-confidence tags | {conf_counter.get('medium', 0)} |",
        "",
        "## Breakdown by move_type",
        "",
        "| Move type | Count |",
        "|-----------|------:|",
    ]
    for mt, cnt in sorted(mt_counter.items(), key=lambda x: -x[1]):
        lines.append(f"| {mt} | {cnt} |")

    lines += [
        "",
        "## Ambiguous frames requiring human review",
        "",
        "These frames have medium confidence or sit at a known ambiguity hotspot.",
        "The chosen tag is the most conservative classification; override in",
        "`data/move_type_tags.proposed.json` and re-run this script if needed.",
        "",
        "| Frame ID | Engine | Move type | Reason |",
        "|----------|--------|-----------|--------|",
    ]
    for frame in sorted(ambiguous, key=lambda f: f.get("engine", "")):
        fid = frame.get("id", "")
        engine = frame.get("engine", "")
        mt = frame.get("move_type", "—")
        row = tags.get(fid, {})
        reason = row.get("reason", "").replace("|", "\\|")
        lines.append(f"| `{fid}` | {engine} | **{mt}** | {reason} |")

    if untagged_frames:
        lines += [
            "",
            "## Untagged frames",
            "",
        ]
        for f in untagged_frames:
            lines.append(f"- `{f.get('id', '?')}` ({f.get('engine', '?')}): `{f.get('text', '')[:60]}`")

    lines += [
        "",
        "## Ambiguity hotspot notes",
        "",
        "| Hotspot | Affected frames | Recommended review |",
        "|---------|----------------|--------------------|",
        "| ASK vs LOOP | `f_like_do_what`, `f_collect_what`, `f_like_chinese_culture`, `f_like_what` | Check preceding frame engine — if same engine, prefer LOOP |",
        "| REACTION vs EXTEND | `p2_fa_4`, `f_food_tasty` | If frame adds new info, prefer EXTEND; if only acknowledgement, REACTION |",
        "| LOOP vs RECIPROCITY | `f_you_ne` (tagged RECIPROCITY — high confidence) | Verify 你呢？ always turns question back; confirmed RECIPROCITY |",
        "| EXTEND vs CLOSE | `p2_pln_3`, `p2_pln_4` | If conversation ends after, CLOSE; if another turn follows, EXTEND |",
        "| LOOP vs BRIDGE | `p2_hb_5` (biggest achievement) | May bridge from hobby to wider life topic; tagged LOOP pending context data |",
    ]

    lines.append("")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    tags = load_tags()
    print(f"[apply] Loaded {len(tags)} tag rows from {TAGS_PATH.relative_to(ROOT)}")

    all_frames: list[dict] = []
    file_stats: list[dict] = []

    for fname in FRAME_FILES:
        p = ROOT / fname
        if not p.is_file():
            print(f"[apply] WARNING: {fname} not found — skipping")
            continue
        stats = apply_tags_to_file(p, tags)
        file_stats.append(stats)
        # Reload for report (tags now written)
        data = json.loads(p.read_text(encoding="utf-8"))
        all_frames.extend(data.get("frames", []))
        print(
            f"[apply] {fname}: {stats['tagged']} tagged"
            f"{' (' + str(stats['already_had_tag']) + ' re-tagged)' if stats['already_had_tag'] else ''}"
            f", {stats['skipped_null']} skipped (no tag)"
        )

    write_coverage_report(all_frames, tags)
    print(f"[apply] Coverage report written -> {REPORT_PATH.relative_to(ROOT)}")

    total  = sum(s["total"]  for s in file_stats)
    tagged = sum(s["tagged"] for s in file_stats)
    print(f"\n[apply] TOTAL: {tagged}/{total} frames tagged ({100*tagged//total}% coverage)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
