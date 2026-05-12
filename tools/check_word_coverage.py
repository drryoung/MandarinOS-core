#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit word coverage for new distance/place mirror questions."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parents[1]
cards = json.loads((REPO / "tools" / "cards" / "out" / "cards_by_id.json").read_text(encoding="utf-8"))

hz_map = {}
for wid, card in cards.items():
    if not isinstance(wid, str) or not wid.startswith("w_"):
        continue
    hz = (card.get("content") or {}).get("headword", {}).get("hanzi", "")
    if hz:
        hz_map[hz] = wid

# Key words from new distance/place questions
targets = ["离", "远", "飞机", "多久", "怎么", "去", "从", "到", "一般", "坐", "坐飞机", "远不远", "多远", "要多久"]
print("=== Word coverage for distance/place questions ===")
missing = []
for w in targets:
    found = hz_map.get(w)
    status = found if found else "NOT IN CARDS (character fallback)"
    print(f"  {w:6s}: {status}")
    if not found:
        missing.append(w)

print(f"\nSummary: {len(targets) - len(missing)}/{len(targets)} words have dedicated card entries.")
if missing:
    print(f"Words using character-level fallback: {missing}")
    print("(These still get click-to-explore via character corpus, just no word-level insight.)")
