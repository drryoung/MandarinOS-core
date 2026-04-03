#!/usr/bin/env python3
"""
Scan free-text phrase sources (personas, frames, mirror/recovery JSON) and report Hanzi
graphemes missing from characters_1200.json (same resolution as audit_vocab_character_coverage).

Run from repo root: python scripts/audit_phrase_character_coverage.py
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

PHRASE_SOURCES: list[tuple[str, Path]] = [
    ("personas/*.json", ROOT / "personas"),
    ("p1_frames.json", ROOT / "p1_frames.json"),
    ("p2_frames.json", ROOT / "p2_frames.json"),
    ("content/mirror_questions.json", ROOT / "content" / "mirror_questions.json"),
    ("content/recovery_phrases.json", ROOT / "content" / "recovery_phrases.json"),
]


def graphemes_cjk(hz: str) -> list[str]:
    out = []
    for ch in hz:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            out.append(ch)
    return out


def walk_strings(obj, acc: list[str]) -> None:
    if isinstance(obj, str):
        acc.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            walk_strings(v, acc)
    elif isinstance(obj, list):
        for x in obj:
            walk_strings(x, acc)


def load_characters_1200():
    best = None
    best_rel = None
    best_n = -1
    for rel in ("characters_1200.json", "data/characters_1200.json"):
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            cd = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(cd, dict):
            continue
        n = len(cd.get("characters") or [])
        if n > best_n:
            best_n = n
            best = cd
            best_rel = rel
    return best, best_rel


def main() -> int:
    cd, chars_rel = load_characters_1200()
    if not cd:
        print("MISSING: characters_1200.json (tried repo root and data/)", file=sys.stderr)
        return 1
    char_list = cd.get("characters", [])
    by_hanzi: set[str] = set()
    for c in char_list:
        hz = (c.get("hanzi") or "").strip()
        if hz:
            by_hanzi.add(hz)

    print(f"=== characters_1200 ({chars_rel}) ===")
    print(f"  indexed graphemes: {len(by_hanzi)}")
    print()

    all_missing: set[str] = set()
    per_label: dict[str, set[str]] = {}

    for label, path in PHRASE_SOURCES:
        strings: list[str] = []
        if label.startswith("personas/") and path.is_dir():
            for fp in sorted(path.glob("*.json")):
                try:
                    walk_strings(json.loads(fp.read_text(encoding="utf-8")), strings)
                except (json.JSONDecodeError, OSError) as e:
                    print(f"  SKIP {fp.relative_to(ROOT)}: {e}", file=sys.stderr)
            eff_label = f"personas/*.json ({path})"
        else:
            if not path.is_file():
                print(f"  SKIP missing: {label}", file=sys.stderr)
                continue
            try:
                walk_strings(json.loads(path.read_text(encoding="utf-8")), strings)
            except (json.JSONDecodeError, OSError) as e:
                print(f"  SKIP {label}: {e}", file=sys.stderr)
                continue
            eff_label = label

        miss: set[str] = set()
        seen_cjk: set[str] = set()
        for s in strings:
            for g in graphemes_cjk(s):
                seen_cjk.add(g)
                if g not in by_hanzi:
                    miss.add(g)
        per_label[eff_label] = miss
        all_missing |= miss
        print(f"=== {eff_label} ===")
        print(f"  unique CJK graphemes in text: {len(seen_cjk)}")
        print(f"  NOT in characters_1200: {len(miss)}")
        if miss:
            sample = "".join(sorted(miss))[:120]
            print(f"    sample: {sample}{'…' if len(miss) > 40 else ''}")
        print()

    print("=== ALL PHRASE SOURCES (union) ===")
    print(f"  unique missing graphemes: {len(all_missing)}")
    if all_missing:
        ordered = sorted(all_missing)
        # printable one per line for easy grep / spreadsheet
        for ch in ordered:
            print(f"    {ch}  U+{ord(ch):04X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
