"""
Phase 10 — Persona schema and built-in persona profiles.

Authoritative: docs/phases/PHASE10_TECHNICAL_PROPOSAL.md §3.
Read-only data; no persistence. Used by selector and persona-consistent stubs (Step 6).
"""

from typing import Any, Dict, List, Optional

# Canonical keys for a persona profile (Phase 10 minimal)
PERSONA_KEYS = (
    "persona_id",
    "persona_name",
    "hometown",
    "lives_in",
    "occupation",
    "interests",
    "favourite_food",
)

# 1–2 flat profiles (no network, no relationships)
PERSONAS: List[Dict[str, Any]] = [
    {
        "persona_id": "zhang_wei",
        "persona_name": "张伟",
        "hometown": "苏州",
        "lives_in": "上海",
        "occupation": "老师",
        "interests": "看书、旅游",
        "favourite_food": "小笼包",
    },
    {
        "persona_id": "li_ming",
        "persona_name": "李明",
        "hometown": "西安",
        "lives_in": "北京",
        "occupation": "工程师",
        "interests": "跑步、摄影",
        "favourite_food": "羊肉泡馍",
    },
]


def get_persona(persona_id: Optional[str]) -> Dict[str, Any]:
    """
    Return the persona profile for persona_id, or the first persona if missing/invalid.
    Always returns a dict with all PERSONA_KEYS; missing keys are None.
    """
    pid = (persona_id or "").strip()
    for p in PERSONAS:
        if (p.get("persona_id") or "").strip() == pid:
            return _normalize_persona(p)
    if PERSONAS:
        return _normalize_persona(PERSONAS[0])
    return {k: None for k in PERSONA_KEYS}


def _normalize_persona(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all PERSONA_KEYS exist; values are str or None."""
    out: Dict[str, Any] = {}
    for k in PERSONA_KEYS:
        v = raw.get(k)
        if v is None:
            out[k] = None
        elif isinstance(v, str):
            out[k] = v.strip() or None
        else:
            out[k] = str(v).strip() or None
    return out


def list_persona_ids() -> List[str]:
    """Return list of persona_id values for UI or config."""
    return [(p.get("persona_id") or "").strip() for p in PERSONAS if (p.get("persona_id") or "").strip()]
