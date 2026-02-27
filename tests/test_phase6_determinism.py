# tests/test_phase6_determinism.py
"""
Phase 6 — Determinism regression test (canonical fixtures)

Asserts that given the same injected inputs (frame + cards_index + cards),
runtime.engine.process_turn emits the same semantic trace every time.

We ignore timestamps because OPEN_CARD uses utcnow() for event timestamp.
"""

from __future__ import annotations

import json
from pathlib import Path


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(events):
    """Remove non-deterministic fields (timestamps) so we can compare structure + payloads."""
    norm = []
    for ev in events:
        if not isinstance(ev, dict):
            norm.append(ev)
            continue
        ev2 = dict(ev)
        # timestamp varies run-to-run
        if "timestamp" in ev2:
            ev2["timestamp"] = None
        # payload should be stable; keep it
        norm.append(ev2)
    return norm


def test_phase6_determinism_open_card_fires():
    repo_root = Path(__file__).resolve().parents[1]
    fixtures = repo_root / "tests" / "fixtures"

    frame = _load_json(fixtures / "frame_open_card.json")
    cards_index = _load_json(fixtures / "cards_index.fixture.json")
    cards = _load_json(fixtures / "cards.fixture.json")

    # Import runtime engine
    from runtime import engine

    def run_once():
        emitted = []

        def emitter(ev):
            emitted.append(ev)

        engine.process_turn(
            "turn_det_1",
            frame,
            engine_affordances={},
            cards_index=cards_index,
            cards=cards,
            emit=emitter,
            env="dev",
        )
        return emitted

    out1 = run_once()
    out2 = run_once()

    n1 = _normalize(out1)
    n2 = _normalize(out2)

    # 1) Must contain OPEN_CARD
    types = [e.get("type") for e in n1 if isinstance(e, dict)]
    assert "OPEN_CARD" in types, f"Expected OPEN_CARD in emitted types, got: {types}"

    # 2) Must be deterministic (ignoring timestamps)
    assert n1 == n2, "Determinism check failed: normalized traces differ run-to-run"
