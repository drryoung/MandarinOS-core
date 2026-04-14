#!/usr/bin/env python3
"""
Reciprocal-coverage audit for MandarinOS.

For each frame in mirror_core_map.json core_entries, verifies:
  1. The frame exists in the frame corpus (p1 + p2, p2 wins on duplicate ID).
  2. The frame has no slots (slotted frames crash the server at startup).
  3. The topic resolves to at least one entry in mirror_questions.json.

Additionally scans the full corpus for slot-free partner frames that could
plausibly be reciprocal candidates but are NOT yet mapped, so coverage gaps
surface automatically instead of only via alpha testing.

Run from repo root:
    python scripts/audit_reciprocal_coverage.py

Exit code: 0 = pass, 1 = at least one ERROR, 2 = no errors but gaps found.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Heuristic: partner frames whose text contains these patterns are likely
# reciprocal questions worth mapping. Used only for the "unmapped candidates"
# advisory section — not for pass/fail logic.
# ---------------------------------------------------------------------------
_RECIPROCAL_PATTERNS = [
    "你", "你有", "你是", "你做", "你在", "你喜欢", "你去", "你结", "你跟",
    "你多", "你和", "你会", "你想", "你的", "哪次", "多久",
]


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def build_frame_corpus() -> dict[str, dict]:
    """Load p1 then p2 frames; p2 wins on duplicate ID."""
    corpus: dict[str, dict] = {}
    for rel in ("p1_frames.json", "p2_frames.json"):
        p = ROOT / rel
        if not p.is_file():
            print(f"  WARN: {rel} not found — skipping", file=sys.stderr)
            continue
        data = load_json(p)
        frames = data if isinstance(data, list) else data.get("frames", [])
        for fr in frames:
            fid = fr.get("id", "")
            if fid:
                corpus[fid] = fr
    return corpus


def build_mirror_bank_topics() -> set[str]:
    """Return set of topic values present in mirror_questions.json."""
    path = ROOT / "content" / "mirror_questions.json"
    if not path.is_file():
        return set()
    data = load_json(path)
    topics: set[str] = set()
    # Structure: {"by_engine": {"identity": [...], "work": [...], ...}}
    # Fall back to treating top-level dict values as engine lists if by_engine absent.
    by_engine = data.get("by_engine") if isinstance(data, dict) else None
    if by_engine is None and isinstance(data, dict):
        by_engine = data
    for entries in (by_engine or {}).values():
        if isinstance(entries, list):
            for e in entries:
                t = e.get("topic", "")
                if t:
                    topics.add(t)
    return topics


def is_reciprocal_candidate(fr: dict) -> bool:
    """Heuristic: slot-free, partner-spoken, personal question (must end with ？)."""
    if fr.get("speaker") != "partner":
        return False
    if fr.get("slots"):
        return False
    text = fr.get("text", "")
    # Must be a question — statements and reaction frames are not reciprocal candidates.
    if "？" not in text and "?" not in text:
        return False
    return any(pat in text for pat in _RECIPROCAL_PATTERNS)


def main() -> int:
    # -----------------------------------------------------------------------
    # Load artefacts
    # -----------------------------------------------------------------------
    core_map_path = ROOT / "content" / "mirror_core_map.json"
    if not core_map_path.is_file():
        print("ERROR: content/mirror_core_map.json not found", file=sys.stderr)
        return 1

    core_map = load_json(core_map_path)
    core_entries: list[dict] = core_map.get("core_entries", [])
    reciprocal_aliases: list[dict] = core_map.get("reciprocal_aliases", [])

    frame_corpus = build_frame_corpus()
    bank_topics = build_mirror_bank_topics()

    mapped_frame_ids: set[str] = {e.get("frame_id", "") for e in core_entries}
    aliased_frame_ids: set[str] = {e.get("frame_id", "") for e in reciprocal_aliases}

    errors: list[str] = []
    warnings: list[str] = []

    # -----------------------------------------------------------------------
    # Section 1 — validate every entry already in core_entries
    # -----------------------------------------------------------------------
    print("=" * 68)
    print("SECTION 1 — Validation of existing mirror_core_map entries")
    print("=" * 68)

    for entry in core_entries:
        fid = entry.get("frame_id", "")
        topic = entry.get("topic", "")

        if not fid:
            errors.append("Entry missing frame_id")
            print(f"  ERROR  missing frame_id in entry: {entry}")
            continue

        fr = frame_corpus.get(fid)

        # Check frame exists
        if fr is None:
            errors.append(f"{fid}: frame not found in corpus")
            print(f"  ERROR  {fid}: not found in p1_frames.json or p2_frames.json")
            continue

        # Check frame is slot-free
        slots = fr.get("slots") or []
        if slots:
            slot_names = [s.get("name", "?") for s in slots]
            errors.append(f"{fid}: has slots {slot_names} — server will crash at startup")
            print(f"  ERROR  {fid}: has slots {slot_names} — cannot be in core_entries")
        else:
            pass  # slot-free OK

        # Check topic resolves in mirror bank.
        # A missing topic is a WARN (no reciprocal card fires) not an ERROR (server still starts).
        if not topic:
            warnings.append(f"{fid}: entry has no topic")
            print(f"  WARN   {fid}: entry has no topic key")
        elif topic not in bank_topics:
            warnings.append(f"{fid}: topic '{topic}' not in mirror_questions.json — reciprocal card will not trigger")
            print(f"  WARN   {fid:30s}  topic '{topic}' not in mirror bank — reciprocal card disabled")
        else:
            print(f"  OK     {fid:30s}  topic={topic}")

    if not errors:
        print()
        print(f"  All {len(core_entries)} entries valid.")

    # -----------------------------------------------------------------------
    # Section 1b — validate reciprocal_aliases
    # -----------------------------------------------------------------------
    print()
    print("=" * 68)
    print("SECTION 1b — Validation of reciprocal_aliases entries")
    print("=" * 68)

    if not reciprocal_aliases:
        print("  (none)")
    else:
        for alias in reciprocal_aliases:
            afid = alias.get("frame_id", "")
            atopic = alias.get("topic", "")
            if not afid:
                errors.append("Alias entry missing frame_id")
                print(f"  ERROR  missing frame_id in alias entry: {alias}")
                continue
            afr = frame_corpus.get(afid)
            if afr is None:
                errors.append(f"ALIAS {afid}: frame not found in corpus")
                print(f"  ERROR  ALIAS {afid}: not found in p1_frames.json or p2_frames.json")
                continue
            # Aliases are expected to have slots — just confirm and report
            slots = afr.get("slots") or []
            slot_names = [s.get("name", "?") for s in slots]
            if not atopic:
                warnings.append(f"ALIAS {afid}: no topic key")
                print(f"  WARN   ALIAS {afid}: no topic — reciprocal card will not trigger")
            elif atopic not in bank_topics:
                warnings.append(f"ALIAS {afid}: topic '{atopic}' not in mirror bank")
                print(f"  WARN   ALIAS {afid}: topic '{atopic}' not in mirror bank — reciprocal card disabled")
            else:
                slot_note = f"  slots={slot_names}" if slots else "  (slot-free — consider moving to core_entries)"
                print(f"  ALIASED {afid:28s}  topic={atopic}{slot_note}")

    # -----------------------------------------------------------------------
    # Section 2 — known slotted frames that cannot be mapped yet
    # -----------------------------------------------------------------------
    print()
    print("=" * 68)
    print("SECTION 2 — Slotted frames blocked from reciprocal mapping")
    print("=" * 68)

    slotted_personal: list[tuple[str, list[str], str]] = []
    for fid, fr in sorted(frame_corpus.items()):
        slots = fr.get("slots") or []
        if not slots:
            continue
        if fr.get("speaker") != "partner":
            continue
        text = fr.get("text", "")
        if any(pat in text for pat in _RECIPROCAL_PATTERNS):
            slot_names = [s.get("name", "?") for s in slots]
            slotted_personal.append((fid, slot_names, text))

    if slotted_personal:
        print(f"  These partner frames look reciprocal but have slots — they cannot")
        print(f"  be added to core_entries until a slot-free P2 override is created.")
        print()
        for fid, slot_names, text in slotted_personal:
            if fid in aliased_frame_ids:
                status = "ALIASED"
            elif fid in mapped_frame_ids:
                status = "MAPPED(ERROR)"
            else:
                status = "UNMAPPED"
            print(f"  {status:15s}  {fid:30s}  slots={slot_names}  text={text!r}")
    else:
        print("  None found.")

    # -----------------------------------------------------------------------
    # Section 3 — unmapped slot-free candidates (coverage gap advisory)
    # -----------------------------------------------------------------------
    print()
    print("=" * 68)
    print("SECTION 3 — Slot-free partner frames not yet in reciprocal map")
    print("=" * 68)

    unmapped: list[tuple[str, str]] = []
    for fid, fr in sorted(frame_corpus.items()):
        if fid in mapped_frame_ids:
            continue
        if not is_reciprocal_candidate(fr):
            continue
        unmapped.append((fid, fr.get("text", "")))

    if unmapped:
        print(f"  {len(unmapped)} slot-free partner frames not in core_entries.")
        print(f"  Review and add high-value ones to content/mirror_core_map.json.")
        print()
        for fid, text in unmapped:
            print(f"  GAP    {fid:35s}  text={text!r}")
    else:
        print("  No unmapped candidates found — coverage complete.")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print()
    print("=" * 68)
    print("SUMMARY")
    print("=" * 68)
    aliased_count = len([f for f, _, _ in slotted_personal if f in aliased_frame_ids])
    unresolved_slotted = len(slotted_personal) - aliased_count
    print(f"  core_entries mapped : {len(core_entries)}")
    print(f"  reciprocal aliases  : {len(reciprocal_aliases)}  ({aliased_count} of slotted-blocked resolved)")
    print(f"  errors (crash risk) : {len(errors)}")
    print(f"  warnings (no card)  : {len(warnings)}")
    print(f"  slotted-unresolved  : {unresolved_slotted}")
    print(f"  unmapped candidates : {len(unmapped)}")
    print()

    if errors:
        print("RESULT: FAIL — fix errors above before restarting server")
        return 1
    if warnings:
        print("RESULT: PASS — no crash risk; see WARNs: those frames have no matching bank topic, reciprocal card disabled for them")
        return 0
    if unmapped or slotted_personal:
        print("RESULT: PASS with gaps — review Section 2/3 for coverage improvements")
        return 2
    print("RESULT: PASS — all entries valid, no unmapped candidates detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
