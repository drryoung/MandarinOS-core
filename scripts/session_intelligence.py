"""
Session Intelligence — Phase 0 Slice 1: raw session capture.

Writes one session_record_v1 JSON file per completed session under:
    data/sessions/{learner_id}/{session_id}.json

Behaviour is entirely gated by the MANDARINOS_SESSION_CAPTURE environment
variable.  When the variable is absent or not "1", every public function
is a no-op and the caller receives False / None.

Architecture reference: docs/session_intelligence_architecture.md
"""

import datetime
import json
import os
import re
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Configuration ─────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"

BASE_DATA_DIR = Path(os.environ.get("MANDARINOS_DATA_DIR", str(_DEFAULT_DATA_DIR)))
_SESSIONS_DIR = BASE_DATA_DIR / "sessions"

# Gate: capture is disabled unless MANDARINOS_SESSION_CAPTURE=1
_CAPTURE_ENABLED: bool = os.environ.get("MANDARINOS_SESSION_CAPTURE", "").strip() == "1"

SCHEMA_VERSION = "session_record_v1"

_SAFE_LEARNER_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_SAFE_SESSION_ID = re.compile(r"^[a-zA-Z0-9_\-.]{1,128}$")

# Maximum transcript entries stored (guard against runaway payload size)
_MAX_TRANSCRIPT_ENTRIES = 200


# ── Internal helpers ──────────────────────────────────────────────────────────

def _validate_learner_id(learner_id: str) -> Optional[str]:
    if not learner_id or not isinstance(learner_id, str):
        return None
    lid = learner_id.strip()
    return lid if (lid and _SAFE_LEARNER_ID.match(lid)) else None


def _validate_session_id(session_id: str) -> Optional[str]:
    if not session_id or not isinstance(session_id, str):
        return None
    sid = session_id.strip()
    return sid if (sid and _SAFE_SESSION_ID.match(sid)) else None


def _session_path(learner_id: str, session_id: str) -> Path:
    return _SESSIONS_DIR / learner_id / f"{session_id}.json"


def _atomic_write(path: Path, data: str) -> None:
    """Write `data` to `path` atomically using a sibling temp file + rename.

    Mirrors the safe-write pattern recommended in the architecture doc:
    prevents a partial write from corrupting an existing file on failure.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        shutil.move(tmp_path_str, str(path))
    except Exception:
        # Clean up temp file on failure; re-raise so caller can log.
        try:
            os.unlink(tmp_path_str)
        except OSError:
            pass
        raise


def _sanitise_transcript(raw: Any) -> List[Dict[str, Any]]:
    """Return a cleaned, capped list of transcript entries from the raw payload.

    Keeps only the allowed keys to prevent arbitrary client-supplied data
    from bloating or injecting unexpected fields.
    """
    if not isinstance(raw, list):
        return []
    allowed_keys = {
        "idx", "id", "role", "text_zh", "text_en", "pinyin",
        "frame_id", "engine", "turn_uid", "created_at",
        "matched", "asr_raw",
    }
    cleaned = []
    for i, entry in enumerate(raw[:_MAX_TRANSCRIPT_ENTRIES]):
        if not isinstance(entry, dict):
            continue
        safe_entry = {k: v for k, v in entry.items() if k in allowed_keys}
        if "idx" not in safe_entry:
            safe_entry["idx"] = i
        cleaned.append(safe_entry)
    return cleaned


def _sanitise_event_log(raw: Any) -> List[Dict[str, Any]]:
    """Return a cleaned list of UI event entries."""
    if not isinstance(raw, list):
        return []
    allowed_keys = {"t_offset_ms", "type", "frame_id", "kind", "engine"}
    return [
        {k: v for k, v in entry.items() if k in allowed_keys}
        for entry in raw[:500]
        if isinstance(entry, dict)
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    """Return True when session capture is active."""
    return _CAPTURE_ENABLED


def build_session_record(
    sess: Dict[str, Any],
    metrics: Dict[str, Any],
    progress_snapshot: Dict[str, Any],
    *,
    transcript: Optional[List[Any]] = None,
    event_log: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Assemble a session_record_v1 from the /api/end_session inputs.

    Args:
        sess:               The raw session payload sent by the client.
        metrics:            Output of _compute_scorecard(sess).
        progress_snapshot:  Output of _build_progress_snapshot(...).
        transcript:         Optional conversationTranscript[] from the client.
        event_log:          Optional lightweight UI event timeline from the client.

    Returns:
        A dict conforming to the session_record_v1 schema.
    """
    session_id = (sess.get("session_id") or "").strip()
    learner_id = (sess.get("learner_id") or "").strip() or None
    persona_id = (sess.get("persona_id") or "").strip() or None
    mode = (sess.get("mode") or "normal").strip().lower()

    try:
        created_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        created_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    # Derive the progress file reference for cross-system correlation.
    progress_ref: Dict[str, Any] = {
        "session_id": session_id,
        "stored_in": f"data/progress/{learner_id}.json" if learner_id else None,
    }

    clean_transcript = _sanitise_transcript(transcript)
    clean_event_log = _sanitise_event_log(event_log)

    return {
        "schema": SCHEMA_VERSION,
        "capture_source": "end_session_payload",
        "session_id": session_id,
        "learner_id": learner_id,
        "created_at": created_at,
        "persona_id": persona_id,
        "mode": mode,
        "tier": (sess.get("tier") or "standard").strip().lower(),
        "duration_seconds": max(0, int(sess.get("duration_seconds", 0) or 0)),

        # Aggregate counters — same values used by the progress snapshot.
        # Stored here for context; the progress snapshot is still authoritative.
        "counters": {
            "total_turns":                         max(0, int(sess.get("total_turns", 0) or 0)),
            "questions_asked":                     max(0, int(sess.get("questions_asked", 0) or 0)),
            "recovery_uses":                       max(0, int(sess.get("recovery_uses", 0) or 0)),
            "successful_recoveries":               max(0, int(sess.get("successful_recoveries", 0) or 0)),
            "conversational_recoveries":           max(0, int(sess.get("conversational_recoveries", 0) or 0)),
            "successful_conversational_recoveries": max(0, int(sess.get("successful_conversational_recoveries", 0) or 0)),
            "suggestion_clicks":                   max(0, int(sess.get("suggestion_clicks", 0) or 0)),
            "card_opens":                          max(0, int(sess.get("card_opens", 0) or 0)),
            "display_en_clicks":                   max(0, int(sess.get("display_en_clicks", 0) or 0)),
            "display_py_clicks":                   max(0, int(sess.get("display_py_clicks", 0) or 0)),
            "hint_clicks":                         max(0, int(sess.get("hint_clicks", 0) or 0)),
            "translation_help_uses":               max(0, int(sess.get("translation_help_uses", 0) or 0)),
            "depth_responses":                     max(0, int(sess.get("depth_responses", 0) or 0)),
            "unmatched_responses":                 max(0, int(sess.get("unmatched_responses", 0) or 0)),
            "soft_unmatched_responses":            max(0, int(sess.get("soft_unmatched_responses", 0) or 0)),
            "engines_used": (
                list(sess.get("engines_used") or [])
                if isinstance(sess.get("engines_used"), (list, set))
                else []
            ),
        },

        # Scorecard metrics — same dict returned to the client.
        "metrics": dict(metrics) if isinstance(metrics, dict) else {},

        # Reference only — the progress file is the authoritative source of truth.
        "progress_snapshot_ref": progress_ref,

        # Transcript (may be absent for old clients or if capture is partial)
        "transcript": clean_transcript,

        # Lightweight UX event timeline
        "event_log": clean_event_log,

        "capture_flags": {
            "transcript_present": bool(clean_transcript),
            "event_log_present":  bool(clean_event_log),
            "transcript_truncated": (
                isinstance(transcript, list)
                and len(transcript) > _MAX_TRANSCRIPT_ENTRIES
            ),
        },
    }


def save_session_record(
    learner_id: str,
    session_id: str,
    record: Dict[str, Any],
) -> bool:
    """Write record to data/sessions/{learner_id}/{session_id}.json atomically.

    Returns True on success, False on any error (never raises).
    No-op (returns False) when capture is disabled.
    """
    if not _CAPTURE_ENABLED:
        return False

    lid = _validate_learner_id(learner_id)
    sid = _validate_session_id(session_id)
    if not lid or not sid:
        return False

    try:
        path = _session_path(lid, sid)
        _atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2))
        return True
    except Exception as exc:
        # Safe: log but never propagate into /api/end_session.
        print(f"[session_intelligence] save failed for {learner_id}/{session_id}: {exc}", flush=True)
        return False


def load_session_record(
    learner_id: str,
    session_id: str,
) -> Optional[Dict[str, Any]]:
    """Return the parsed session_record for (learner_id, session_id), or None."""
    if not _CAPTURE_ENABLED:
        return None

    lid = _validate_learner_id(learner_id)
    sid = _validate_session_id(session_id)
    if not lid or not sid:
        return None

    try:
        path = _session_path(lid, sid)
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        return raw
    except Exception:
        return None
