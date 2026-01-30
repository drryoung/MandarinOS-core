from typing import Any, Callable, Dict, Optional

from . import open_card_resolver as resolver


def process_frame_and_emit_open_card(
    frame: Dict[str, Any],
    engine_affordances: Dict[str, Any],
    cards_index: Dict[str, str],
    cards: Dict[str, Any],
    emit: Callable[[Dict[str, Any]], None],
    env: str = "dev",
) -> Optional[Dict[str, Any]]:
    """
    Try to resolve a card for `frame`. If resolved, build an OPEN_CARD event
    and emit it using the provided `emit` callable. Returns the event or None.
    """
    try:
        card_id = resolver.resolve_card_for_frame(frame, engine_affordances, cards_index, cards, env=env)
    except Exception:
        # propagate errors to caller in dev; resolver raises OpenCardResolutionError in dev
        raise

    if not card_id:
        return None

    ev = resolver.build_open_card_event(frame.get("engine_id"), frame.get("frame_id"), card_id)
    emit(ev)
    return ev
