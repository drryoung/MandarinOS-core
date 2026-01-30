import json
from datetime import datetime
from typing import Any, Dict, Optional


class OpenCardResolutionError(Exception):
    pass


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_card_for_frame(frame: Dict[str, Any], engine_affordances: Dict[str, Any], cards_index: Dict[str, str], cards: Dict[str, Any], env: str = "dev") -> Optional[str]:
    """
    Resolve a card_id for the given frame using the provided cards_index map.

    Rules (per directive):
    - Only resolve when frame.readiness_label == 'READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE'
      and affordances.open_card == True (frame-level overrides engine-level)
    - cards_index is expected to map tokens/hanzi to card_id
    - In dev/test (env!='prod'), raise OpenCardResolutionError if claim exists but no mapping found
    - In prod, return None when missing
    """
    if not frame:
        return None

    readiness = frame.get("readiness_label")
    if readiness != "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE":
        return None

    # affordances: frame overrides engine
    fr_aff = frame.get("affordances") or {}
    eng_aff = {}
    eng_id = frame.get("engine_id")
    if engine_affordances and eng_id in engine_affordances:
        eng_aff = engine_affordances.get(eng_id) or {}

    afford = dict(eng_aff)
    if isinstance(fr_aff, dict):
        afford.update(fr_aff)

    if not afford.get("open_card"):
        return None

    # attempt resolution via option_tokens and frame id
    tokens = frame.get("option_tokens") or []
    # try tokens first
    for t in tokens:
        if not isinstance(t, str):
            continue
        if t in cards_index:
            return cards_index[t]

    # fallback: try frame_id
    fid = frame.get("frame_id")
    if fid and fid in cards_index:
        return cards_index[fid]

    # nothing found
    if env != "prod":
        raise OpenCardResolutionError(f"No card mapping found for frame {fid} (tokens={tokens})")
    return None


def build_open_card_event(engine_id: str, frame_id: str, card_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    return {
        "type": "OPEN_CARD",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "payload": {
            "engine_id": engine_id,
            "frame_id": frame_id,
            "card_id": card_id,
            "reason": reason,
        },
    }
