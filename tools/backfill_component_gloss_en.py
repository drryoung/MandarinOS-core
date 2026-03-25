#!/usr/bin/env python3
"""
Phase 3: Set characters_1200.json gloss_en where null/empty, using component_gloss_maps.json
(repo root or data/) — radical_variant_gloss_en + teaching_supplement_en — so corpus and UI stay aligned.

Does not overwrite existing non-empty gloss_en.

Usage (repo root):
  python tools/backfill_component_gloss_en.py
  python tools/backfill_component_gloss_en.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resolve_component_gloss_maps_path() -> Path:
    for p in (ROOT / "component_gloss_maps.json", ROOT / "data" / "component_gloss_maps.json"):
        if p.is_file():
            return p
    raise SystemExit("Missing component_gloss_maps.json (repo root or data/)")


def load_characters_path() -> tuple[Path, dict]:
    best_p = None
    best_data = None
    best_n = -1
    for rel in ("characters_1200.json", "data/characters_1200.json"):
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        n = len((data.get("characters") or []))
        if n > best_n:
            best_n = n
            best_p = p
            best_data = data
    if not best_p:
        raise SystemExit("No characters_1200.json found at repo root or data/")
    return best_p, best_data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Print counts only; do not write")
    args = ap.parse_args()

    maps = json.loads(resolve_component_gloss_maps_path().read_text(encoding="utf-8"))
    merged: dict[str, str] = {}
    for k, v in (maps.get("radical_variant_gloss_en") or {}).items():
        if isinstance(v, str) and v.strip():
            merged[str(k).strip()] = v.strip()
    for k, v in (maps.get("teaching_supplement_en") or {}).items():
        if isinstance(v, str) and v.strip():
            merged[str(k).strip()] = v.strip()

    path, data = load_characters_path()
    rows = data.get("characters") or []
    updated = 0
    for row in rows:
        hz = row.get("hanzi")
        if hz is None:
            continue
        h = str(hz).strip()
        if not h or h not in merged:
            continue
        cur = row.get("gloss_en")
        if cur is not None and str(cur).strip():
            continue
        row["gloss_en"] = merged[h]
        updated += 1

    print(f"File: {path.relative_to(ROOT)}")
    print(f"Rows updated (gloss_en was empty): {updated}")
    if args.dry_run:
        print("Dry run — no write.")
        return 0

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
