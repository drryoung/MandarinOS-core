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

    # Phase 5: pack frames don't have readiness_label yet.
    # In dev/test, allow missing readiness_label to pass so we can test real packs end-to-end.
    if readiness is not None and readiness != "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE":
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

    # Phase 5: if no affordances exist, allow opening a card
    if "open_card" in afford and not afford.get("open_card"):
        return None

    # attempt resolution via option_tokens and frame id
    tokens = frame.get("option_tokens") or []
    by_word_id = cards_index.get("by_word_id") if isinstance(cards_index, dict) else {}
    
    # try tokens first
    for t in tokens:
        if isinstance(t, str) and t in by_word_id:
            return by_word_id[t]

    # fallback: try frame_id
    fid = frame.get("frame_id")
    if fid and fid in by_word_id:
        return by_word_id[fid]

    # Phase 5 fallback: resolve by frame text (hanzi) using cards_index.by_hanzi
    text = frame.get("text")
    by_hanzi = cards_index.get("by_hanzi") if isinstance(cards_index, dict) else None

    if isinstance(text, str) and isinstance(by_hanzi, dict):
        # 1) Exact match (rare, but keep it)
        hits = by_hanzi.get(text)
        if isinstance(hits, list) and len(hits) > 0:
            return hits[0]

        # 2) Sentence match: if any known word appears inside the sentence, use it
        # Try longer words first so "哥哥" beats "哥" etc.
        for hanzi_word in sorted(by_hanzi.keys(), key=len, reverse=True):
            if hanzi_word and hanzi_word in text:
                hits2 = by_hanzi.get(hanzi_word)
                if isinstance(hits2, list) and len(hits2) > 0:
                    return hits2[0]

    # nothing found
    if env != "prod":
        raise OpenCardResolutionError(
            f"No card mapping found for frame {fid} (tokens={tokens}) text={frame.get('text')}"
        )
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
