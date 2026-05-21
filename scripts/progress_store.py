"""
Beta progress persistence — append-only snapshots per learner_id.

Mirrors learner_memory.py pattern: one JSON file per learner under data/progress/.
Server is source of truth for beta analysis; client localStorage remains a UI cache.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
BASE_DATA_DIR = Path(os.environ.get("MANDARINOS_DATA_DIR", str(_DEFAULT_DATA_DIR)))
_PROGRESS_DIR = BASE_DATA_DIR / "progress"

_SAFE_LEARNER_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# In-memory cache: learner_id -> list of snapshot dicts
_cache: Dict[str, List[dict]] = {}


def _normalize_learner_id(learner_id: str) -> Optional[str]:
    if not learner_id or not isinstance(learner_id, str):
        return None
    lid = learner_id.strip()
    if not lid or not _SAFE_LEARNER_ID.match(lid):
        return None
    return lid


def _learner_path(learner_id: str) -> Path:
    return _PROGRESS_DIR / f"{learner_id}.json"


def _read_file(learner_id: str) -> List[dict]:
    path = _learner_path(learner_id)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [s for s in raw if isinstance(s, dict)]
    except (OSError, json.JSONDecodeError):
        return []


def _write_file(learner_id: str, snapshots: List[dict]) -> None:
    _PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    path = _learner_path(learner_id)
    path.write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_snapshots(learner_id: str) -> List[dict]:
    """Return all progress snapshots for learner_id (oldest first)."""
    lid = _normalize_learner_id(learner_id)
    if not lid:
        return []
    if lid not in _cache:
        _cache[lid] = _read_file(lid)
    return [dict(s) for s in _cache[lid]]


def save_snapshot(learner_id: str, snapshot: dict) -> bool:
    """Append snapshot for learner_id; dedupe by session_id when present."""
    lid = _normalize_learner_id(learner_id)
    if not lid or not isinstance(snapshot, dict):
        return False

    record = dict(snapshot)
    record["learner_id"] = lid
    sid = (record.get("session_id") or "").strip()

    existing = load_snapshots(lid)
    if sid:
        existing = [s for s in existing if (s.get("session_id") or "").strip() != sid]
    existing.append(record)
    _cache[lid] = existing
    try:
        _write_file(lid, existing)
        return True
    except OSError:
        return False


def load_all() -> Dict[str, List[dict]]:
    """Return {learner_id: [snapshots]} for every file in data/progress/."""
    out: Dict[str, List[dict]] = {}
    if not _PROGRESS_DIR.is_dir():
        return out
    for path in sorted(_PROGRESS_DIR.glob("*.json")):
        lid = path.stem
        if not _SAFE_LEARNER_ID.match(lid):
            continue
        out[lid] = load_snapshots(lid)
    return out
