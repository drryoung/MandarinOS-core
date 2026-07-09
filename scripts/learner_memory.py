"""
Phase 10 — Learner memory schema and store.

Authoritative: docs/phases/PHASE10_TECHNICAL_PROPOSAL.md
Persistence key: learner_id (not session_id).
Server is authoritative; client never sends learner_memory.

Step 3: File persistence at data/learner_memory.json (keyed by learner_id).
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
BASE_DATA_DIR = Path(os.environ.get("MANDARINOS_DATA_DIR", str(_DEFAULT_DATA_DIR)))
_PERSISTENCE_PATH = BASE_DATA_DIR / "learner_memory.json"

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
    """Save learner memory for learner_id. Updates cache and writes persistence file.

    Uses merge semantics: a field present in *memory* with a non-None value overwrites
    the stored value; a None value leaves the stored value unchanged.  Use `clear()`
    when you need to erase all fields unconditionally (e.g. user-initiated reset).
    """
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


def clear(learner_id: str) -> None:
    """Erase all learner memory for learner_id — unconditional, no merge.

    Use this for user-initiated "clear previous-session memory" flows.
    Unlike save(), passing all-None values here genuinely resets every field to None
    and writes the result to the persistence file.
    """
    if not learner_id or not isinstance(learner_id, str):
        return
    lid = learner_id.strip()
    _store[lid] = empty_memory()
    _save_file()


# ── Learner-memory migration (one-time cleanup for pre-fix ASR junk) ──────────

# Fields that hold place names and should be validated via normalize_place_name.
_PLACE_FIELDS: tuple = ("hometown", "lives_in")

# ASR-junk fragments mirrored here so the migration function is self-contained
# even when learner_memory_capture is not importable.
_MIGRATION_JUNK: tuple = (
    "等你等", "等一等", "等等你", "等你", "那个那个", "就是就是", "呃呃", "嗯嗯",
)


def _clean_field_value(field: str, value: Optional[str]) -> Optional[str]:
    """Return a sanitised version of *value* for the given memory *field*.

    Place fields (hometown, lives_in) are validated through normalize_place_name;
    if the value is unrecognisable, None is returned so the field is cleared.

    For other fields a lightweight junk-fragment strip is applied; if nothing
    meaningful remains after stripping, None is returned.
    """
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None

    if field in _PLACE_FIELDS:
        # Lazy import to avoid circular dependency at module load.
        try:
            from learner_memory_capture import normalize_place_name  # type: ignore
        except ImportError:
            try:
                from scripts.learner_memory_capture import normalize_place_name  # type: ignore
            except ImportError:
                normalize_place_name = None  # type: ignore

        if normalize_place_name is not None:
            return normalize_place_name(v)
        # Fallback when normalize_place_name is unavailable: strip known junk.
        for junk in _MIGRATION_JUNK:
            v = v.replace(junk, "")
        v = v.strip("的 ，,。.、").strip()
        return v or None
    else:
        # Non-place field: only strip obvious ASR-junk prefixes/suffixes.
        for junk in _MIGRATION_JUNK:
            v = v.replace(junk, "")
        v = v.strip()
        return v or None


def migrate_corrupted_memory(
    path: Optional[Path] = None,
    *,
    dry_run: bool = False,
) -> Tuple[int, int, List[str]]:
    """Scan the persistence file and sanitise corrupted learner-memory fields.

    Applies normalize_place_name to place fields (hometown, lives_in) and strips
    known ASR-junk fragments from all other string fields.  Fields that are
    unrecoverable (pure junk, empty after cleaning) are set to None.

    Args:
        path:    Path to learner_memory.json.  Defaults to the standard location.
        dry_run: If True, compute changes but do not write the file.

    Returns:
        (learners_changed, fields_changed, log_lines)
        where log_lines is a human-readable summary of every change made.
    """
    target = path or _PERSISTENCE_PATH
    if not target.is_file():
        return 0, 0, ["[migrate] learner_memory.json not found — nothing to do."]

    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return 0, 0, [f"[migrate] failed to read file: {exc}"]

    if not isinstance(raw, dict):
        return 0, 0, ["[migrate] unexpected file format — skipping."]

    cleaned: Dict[str, Dict] = {}
    learners_changed = 0
    fields_changed = 0
    log: List[str] = []

    for lid, mem in raw.items():
        if not isinstance(lid, str) or not isinstance(mem, dict):
            cleaned[lid] = mem
            continue

        new_mem: Dict[str, Optional[str]] = {}
        learner_dirty = False

        for key in LEARNER_MEMORY_KEYS:
            original = mem.get(key)
            if not isinstance(original, str):
                new_mem[key] = None if original is not None else None
                continue

            sanitised = _clean_field_value(key, original)
            new_mem[key] = sanitised

            if sanitised != original:
                learner_dirty = True
                fields_changed += 1
                log.append(
                    f"  [{lid}] {key}: {original!r} → {sanitised!r}"
                )

        # Preserve any extra keys that may exist in the file (forward compat).
        merged = dict(mem)
        merged.update(new_mem)
        cleaned[lid] = merged

        if learner_dirty:
            learners_changed += 1

    action = "dry-run" if dry_run else "migrated"
    log.insert(0, f"[migrate] {action}: {learners_changed} learner(s), {fields_changed} field(s) changed.")

    if not dry_run and (learners_changed > 0):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
            # Invalidate in-memory cache so next load picks up the cleaned file.
            _store.clear()
        except OSError as exc:
            log.append(f"[migrate] ERROR writing file: {exc}")

    return learners_changed, fields_changed, log
