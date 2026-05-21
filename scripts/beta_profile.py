"""
Beta learner profile — practice comfort level per learner_id.

Separate from factual learner_memory (Phase 10). One JSON file per learner under data/beta_profiles/.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
BASE_DATA_DIR = Path(os.environ.get("MANDARINOS_DATA_DIR", str(_DEFAULT_DATA_DIR)))
_PROFILES_DIR = BASE_DATA_DIR / "beta_profiles"

_SAFE_LEARNER_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

VALID_LEVELS = frozenset({"beginner", "lower_intermediate", "intermediate"})
VALID_SOURCES = frozenset({"self_selected", "operator_set"})

_cache: Dict[str, dict] = {}


def _normalize_learner_id(learner_id: str) -> Optional[str]:
    if not learner_id or not isinstance(learner_id, str):
        return None
    lid = learner_id.strip()
    if not lid or not _SAFE_LEARNER_ID.match(lid):
        return None
    return lid


def _comfort_mode_for_level(level: str) -> bool:
    return level == "beginner"


def empty_profile() -> dict:
    return {
        "learner_level": None,
        "level_source": None,
        "level_selected_at": None,
        "comfort_mode": None,
    }


def _learner_path(learner_id: str) -> Path:
    return _PROFILES_DIR / f"{learner_id}.json"


def _read_file(learner_id: str) -> dict:
    path = _learner_path(learner_id)
    if not path.is_file():
        return empty_profile()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return empty_profile()
        return _normalize_profile(raw)
    except (OSError, json.JSONDecodeError):
        return empty_profile()


def _write_file(learner_id: str, profile: dict) -> None:
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = _learner_path(learner_id)
    path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _normalize_profile(raw: dict) -> dict:
    out = empty_profile()
    if not isinstance(raw, dict):
        return out
    level = (raw.get("learner_level") or "").strip()
    if level not in VALID_LEVELS:
        return out
    out["learner_level"] = level
    src = (raw.get("level_source") or "").strip()
    out["level_source"] = src if src in VALID_SOURCES else "self_selected"
    ts = raw.get("level_selected_at")
    out["level_selected_at"] = ts.strip() if isinstance(ts, str) and ts.strip() else None
    cm = raw.get("comfort_mode")
    out["comfort_mode"] = cm if isinstance(cm, bool) else _comfort_mode_for_level(level)
    return out


def load_profile(learner_id: str) -> dict:
    """Return profile for learner_id; empty profile when unset."""
    lid = _normalize_learner_id(learner_id)
    if not lid:
        return empty_profile()
    if lid not in _cache:
        _cache[lid] = _read_file(lid)
    return dict(_cache[lid])


def save_profile(learner_id: str, updates: dict) -> bool:
    """Persist learner_level and derived comfort_mode for learner_id."""
    lid = _normalize_learner_id(learner_id)
    if not lid or not isinstance(updates, dict):
        return False
    level = (updates.get("learner_level") or "").strip()
    if level not in VALID_LEVELS:
        return False
    src = (updates.get("level_source") or "self_selected").strip()
    if src not in VALID_SOURCES:
        src = "self_selected"
    ts = updates.get("level_selected_at")
    if isinstance(ts, str) and ts.strip():
        selected_at = ts.strip()
    else:
        selected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cm = updates.get("comfort_mode")
    profile = {
        "learner_level": level,
        "level_source": src,
        "level_selected_at": selected_at,
        "comfort_mode": cm if isinstance(cm, bool) else _comfort_mode_for_level(level),
    }
    _cache[lid] = profile
    try:
        _write_file(lid, profile)
        return True
    except OSError:
        return False
