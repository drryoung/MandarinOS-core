# tests/test_fixture_contract.py
"""
Phase 6 — Fixture Contract (canonical fixtures)

Validates that the simulator/runtime fixtures are internally consistent:
- cards_index.fixture.json has by_word_id and it's non-empty
- cards.fixture.json is non-empty
- every card_id referenced by by_word_id exists in cards
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

CARDS_INDEX_PATH = FIXTURES / "cards_index.fixture.json"
CARDS_PATH = FIXTURES / "cards.fixture.json"


def _load_json(p: Path):
    if not p.exists():
        raise SystemExit(f"Fixture missing: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"Failed to parse JSON: {p} ({e})")


def main() -> int:
    cards_index = _load_json(CARDS_INDEX_PATH)
    cards = _load_json(CARDS_PATH)

    # 1) Basic type checks
    if not isinstance(cards_index, dict):
        print("FAIL: cards_index must be a JSON object (dict).")
        return 2
    if not isinstance(cards, dict):
        print("FAIL: cards must be a JSON object (dict).")
        return 2

    # 2) Required key: by_word_id
    by_word_id = cards_index.get("by_word_id")
    if not isinstance(by_word_id, dict):
        print("FAIL: cards_index['by_word_id'] must be a dict.")
        return 3
    if not by_word_id:
        print("FAIL: cards_index['by_word_id'] must be non-empty.")
        return 3

    # 3) Cards must be non-empty
    if not cards:
        print("FAIL: cards fixture must be non-empty.")
        return 4

    # 4) Referential integrity: every mapped card_id must exist in cards
    missing = []
    for token, card_id in by_word_id.items():
        if not isinstance(token, str) or not token:
            missing.append(f"INVALID_TOKEN<{repr(token)}>")
            continue
        if not isinstance(card_id, str) or not card_id:
            missing.append(f"{token} -> INVALID_CARD_ID<{repr(card_id)}>")
            continue
        if card_id not in cards:
            missing.append(f"{token} -> {card_id}")

    if missing:
        print("FAIL: cards_index.by_word_id contains card_ids missing from cards fixture:")
        for m in missing[:50]:
            print("  -", m)
        if len(missing) > 50:
            print(f"  ... and {len(missing) - 50} more")
        return 5

    print("PASS: Fixture Contract OK")
    print(f"  by_word_id entries: {len(by_word_id)}")
    print(f"  cards entries:      {len(cards)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
