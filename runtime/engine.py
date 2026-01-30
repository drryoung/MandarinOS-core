from typing import Any, Callable, Dict, List

from . import open_card_wiring as wiring


def process_turn(turn_uid: str, frame: Dict[str, Any], engine_affordances: Dict[str, Any], cards_index: Dict[str, str], cards: Dict[str, Any], emit: Callable[[Dict[str, Any]], None], env: str = "dev") -> List[Dict[str, Any]]:
    """
    Minimal engine pipeline that emits TURN_START, delegates to wiring for OPEN_CARD,
    and emits TURN_END. Returns the list of emitted steps for convenience.
    """
    steps = []

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
