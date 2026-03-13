"""
Phase 10 — Learner memory schema and store.

Authoritative: docs/phases/PHASE10_TECHNICAL_PROPOSAL.md
Persistence key: learner_id (not session_id).
Server is authoritative; client never sends learner_memory.

Step 3: File persistence at data/learner_memory.json (keyed by learner_id).
"""

import json
from pathlib import Path
from typing import Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PERSISTENCE_PATH = _REPO_ROOT / "data" / "learner_memory.json"

# Canonical six fields (all optional string or None)
LEARNER_MEMORY_KEYS = (
    "learner_name",
    "hometown",
    "lives_in",
    "job_or_study",
    "family",
    "favourite_food",
)


def empty_memory() -> Dict[str, Optional[str]]:
    """Return a fresh learner memory dict with all keys set to None."""
    return {k: None for k in LEARNER_MEMORY_KEYS}


def validate_updates(updates: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
    """Return only updates whose keys are in LEARNER_MEMORY_KEYS; values must be str or None."""
    out = {}
    for k, v in (updates or {}).items():
        if k not in LEARNER_MEMORY_KEYS:
            continue
        if v is not None and not isinstance(v, str):
            continue
        out[k] = (v.strip() or None) if isinstance(v, str) else None
    return out


def apply_updates(
    memory: Dict[str, Optional[str]],
    updates: Dict[str, Optional[str]],
) -> Dict[str, Optional[str]]:
    """Return a new memory dict with updates applied. Does not mutate memory."""
    result = dict(memory) if memory else empty_memory()
    for k, v in validate_updates(updates).items():
        result[k] = v
    return result


# In-memory cache: learner_id -> memory dict (synced with file on load/save)
_store: Dict[str, Dict[str, Optional[str]]] = {}


def _load_file() -> None:
    """Read persistence file into _store. Idempotent; merges with existing _store."""
    if not _PERSISTENCE_PATH.is_file():
        return
    try:
        raw = json.loads(_PERSISTENCE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
        for lid, mem in raw.items():
            if not isinstance(lid, str) or not isinstance(mem, dict):
                continue
            normalized = {k: (mem.get(k) if isinstance(mem.get(k), str) else None) for k in LEARNER_MEMORY_KEYS}
            _store[lid.strip()] = normalized
    except (OSError, json.JSONDecodeError):
        pass


def _save_file() -> None:
    """Write _store to persistence file. Creates data/ dir if needed."""
    try:
        _PERSISTENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        blob = {lid: mem for lid, mem in _store.items() if isinstance(mem, dict)}
        _PERSISTENCE_PATH.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def load(learner_id: str) -> Dict[str, Optional[str]]:
    """Load learner memory for learner_id. Reads from file on cache miss."""
    if not learner_id or not isinstance(learner_id, str):
        return empty_memory()
    lid = learner_id.strip()
    if lid not in _store:
        _load_file()
    if lid in _store:
        return dict(_store[lid])
    return empty_memory()


def save(learner_id: str, memory: Dict[str, Optional[str]]) -> None:
    """Save learner memory for learner_id. Updates cache and writes persistence file."""
    if not learner_id or not isinstance(learner_id, str):
        return
    lid = learner_id.strip()
    if not memory:
        return
    if lid not in _store:
        _load_file()
    existing = _store.get(lid) or empty_memory()
    merged = {k: memory.get(k) if memory.get(k) is not None else existing.get(k) for k in LEARNER_MEMORY_KEYS}
    _store[lid] = merged
    _save_file()
