from typing import Any, Callable, Dict, List

from . import open_card_wiring as wiring

def _validate_strict_runtime_inputs(cards_index: Dict[str, Any], cards: Dict[str, Any]) -> None:
    """
    Phase 6 strict runtime: fail fast on malformed injected maps.
    This duplicates resolver expectations so the pipeline fails at the boundary.
    """
    if not isinstance(cards_index, dict):
        raise TypeError("Strict runtime: cards_index must be a dict")

    by_word_id = cards_index.get("by_word_id")
    if not isinstance(by_word_id, dict):
        raise TypeError("Strict runtime: cards_index['by_word_id'] must be a dict")

    if not by_word_id:
        raise ValueError("Strict runtime: cards_index['by_word_id'] is empty")

    if not isinstance(cards, dict):
        raise TypeError("Strict runtime: cards must be a dict")

    if not cards:
        raise ValueError("Strict runtime: cards dict is empty")


def process_turn(turn_uid: str, frame: Dict[str, Any], engine_affordances: Dict[str, Any], cards_index: Dict[str, str], cards: Dict[str, Any], emit: Callable[[Dict[str, Any]], None], env: str = "dev") -> List[Dict[str, Any]]:
    """
    Minimal engine pipeline that emits TURN_START, delegates to wiring for OPEN_CARD,
    and emits TURN_END. Returns the list of emitted steps for convenience.
    """
    steps = []
    _validate_strict_runtime_inputs(cards_index, cards)

    start = {
        "type": "TURN_START",
        "timestamp": None,
        "payload": {"turn_uid": turn_uid, "engine_id": frame.get("engine_id"), "frame_id": frame.get("frame_id")},
    }
    emit(start)
    steps.append(start)

    ev = None
    try:
        ev = wiring.process_frame_and_emit_open_card(frame, engine_affordances, cards_index, cards, emit, env=env)
    except Exception:
        # re-raise to allow dev tests to detect failures
        raise

    if ev:
        steps.append(ev)

    end = {
        "type": "TURN_END",
        "timestamp": None,
        "payload": {"turn_uid": turn_uid, "result": "OPEN_CARD_FIRED" if ev else "NO_CARD"},
    }
    emit(end)
    steps.append(end)

    return steps
