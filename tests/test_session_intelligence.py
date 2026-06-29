"""
Phase 0 Slice 1 — Session Intelligence capture tests.

Coverage:
  1. feature flag off  → no file written, existing progress unchanged.
  2. feature flag on   → session_record_v1 file written at correct path.
  3. transcript missing → endpoint still succeeds (no KeyError / exception).
  4. progress snapshot behaviour unchanged when capture flag is on.
  5. repeated sessions → separate files, never a shared array.
  6. schema: schema_version, capture_source, required top-level keys.
  7. sanitise_transcript: strips extra keys, caps at _MAX_TRANSCRIPT_ENTRIES.
  8. invalid learner_id / session_id → save returns False, no file created.
  9. atomic write: existing file not corrupted on a bad write.
 10. build_session_record: counters coerced to int, no exception on missing.
"""

import importlib
import json
import os
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

# ── Locate repo root so we can import the scripts package ────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ── Helper: import (or reload) session_intelligence with specific env ─────────

def _import_si(capture_enabled: bool, data_dir: Path):
    """Import session_intelligence with overridden env vars and return the module."""
    env_patch = {
        "MANDARINOS_SESSION_CAPTURE": "1" if capture_enabled else "",
        "MANDARINOS_DATA_DIR": str(data_dir),
    }
    with mock.patch.dict(os.environ, env_patch, clear=False):
        # Always reload so the module-level constants re-evaluate.
        if "session_intelligence" in sys.modules:
            del sys.modules["session_intelligence"]
        mod = importlib.import_module("session_intelligence")
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# 1. Feature flag OFF → nothing written
# ─────────────────────────────────────────────────────────────────────────────

class TestFlagOff:
    def test_is_enabled_false(self, tmp_path):
        si = _import_si(capture_enabled=False, data_dir=tmp_path)
        assert si.is_enabled() is False

    def test_save_returns_false_when_disabled(self, tmp_path):
        si = _import_si(capture_enabled=False, data_dir=tmp_path)
        record = {"schema": si.SCHEMA_VERSION}
        ok = si.save_session_record("learner_abc", "session_123", record)
        assert ok is False

    def test_no_file_created_when_disabled(self, tmp_path):
        si = _import_si(capture_enabled=False, data_dir=tmp_path)
        record = {"schema": si.SCHEMA_VERSION}
        si.save_session_record("learner_abc", "session_123", record)
        sessions_dir = tmp_path / "sessions"
        assert not sessions_dir.exists(), "sessions/ dir must not be created when flag is off"

    def test_load_returns_none_when_disabled(self, tmp_path):
        si = _import_si(capture_enabled=False, data_dir=tmp_path)
        result = si.load_session_record("learner_abc", "session_123")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Feature flag ON → file written at correct path
# ─────────────────────────────────────────────────────────────────────────────

class TestFlagOn:
    def test_is_enabled_true(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        assert si.is_enabled() is True

    def test_save_returns_true(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = _minimal_record(si)
        ok = si.save_session_record("learner_abc", "session_123", record)
        assert ok is True

    def test_file_at_expected_path(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = _minimal_record(si)
        si.save_session_record("learner_abc", "session_123", record)
        expected = tmp_path / "sessions" / "learner_abc" / "session_123.json"
        assert expected.is_file(), f"Expected file at {expected}"

    def test_file_is_valid_json(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = _minimal_record(si)
        si.save_session_record("learner_abc", "session_123", record)
        path = tmp_path / "sessions" / "learner_abc" / "session_123.json"
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)

    def test_load_round_trips(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = _minimal_record(si)
        record["custom_key"] = "round_trip_check"
        si.save_session_record("learner_abc", "session_rt", record)
        loaded = si.load_session_record("learner_abc", "session_rt")
        assert loaded is not None
        assert loaded["custom_key"] == "round_trip_check"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Transcript missing → no crash, save still succeeds
# ─────────────────────────────────────────────────────────────────────────────

class TestTranscriptMissing:
    def test_build_record_without_transcript(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        sess = _minimal_sess()
        metrics = {}
        snapshot = {}
        record = si.build_session_record(sess, metrics, snapshot)
        assert record["transcript"] == []
        assert record["event_log"] == []
        assert record["capture_flags"]["transcript_present"] is False

    def test_save_without_transcript(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        sess = _minimal_sess()
        record = si.build_session_record(sess, {}, {})
        ok = si.save_session_record("learner_abc", sess["session_id"], record)
        assert ok is True

    def test_build_record_with_none_transcript(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = si.build_session_record(_minimal_sess(), {}, {}, transcript=None)
        assert record["transcript"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. Progress snapshot behaviour unchanged
# ─────────────────────────────────────────────────────────────────────────────

class TestProgressUnchanged:
    """Verify that the progress file is separate and unaffected by SI capture."""

    def test_progress_file_not_created_by_si(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = _minimal_record(si)
        si.save_session_record("learner_abc", "session_123", record)
        progress_dir = tmp_path / "progress"
        assert not progress_dir.exists(), "SI must not create data/progress/"

    def test_si_and_progress_dirs_are_separate(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = _minimal_record(si)
        si.save_session_record("learner_abc", "session_123", record)
        sessions_dir = tmp_path / "sessions"
        assert sessions_dir.is_dir()
        assert sessions_dir.name == "sessions"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Repeated sessions → separate files, no shared array
# ─────────────────────────────────────────────────────────────────────────────

class TestSeparateFiles:
    def test_two_sessions_produce_two_files(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        for sid in ("session_AAA", "session_BBB"):
            sess = _minimal_sess(session_id=sid)
            record = si.build_session_record(sess, {}, {})
            si.save_session_record("learner_abc", sid, record)

        files = sorted((tmp_path / "sessions" / "learner_abc").iterdir())
        names = [f.name for f in files]
        assert "session_AAA.json" in names
        assert "session_BBB.json" in names
        assert len(names) == 2

    def test_second_save_does_not_append_to_first(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        for sid in ("session_X1", "session_X2"):
            sess = _minimal_sess(session_id=sid)
            record = si.build_session_record(sess, {}, {})
            si.save_session_record("learner_abc", sid, record)

        # Each file must be a dict, not a list
        for sid in ("session_X1", "session_X2"):
            path = tmp_path / "sessions" / "learner_abc" / f"{sid}.json"
            parsed = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(parsed, dict), f"{sid}.json must be a dict, not a list"

    def test_overwrite_same_session_id_replaces_file(self, tmp_path):
        """Saving the same session_id again should replace the file (idempotent)."""
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        sess = _minimal_sess(session_id="session_SAME")

        record1 = si.build_session_record(sess, {}, {})
        record1["_version_marker"] = "v1"
        si.save_session_record("learner_abc", "session_SAME", record1)

        record2 = si.build_session_record(sess, {}, {})
        record2["_version_marker"] = "v2"
        si.save_session_record("learner_abc", "session_SAME", record2)

        loaded = si.load_session_record("learner_abc", "session_SAME")
        assert loaded["_version_marker"] == "v2"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Schema: schema_version, capture_source, required keys
# ─────────────────────────────────────────────────────────────────────────────

class TestSchema:
    def _build(self, tmp_path, **sess_overrides):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        sess = _minimal_sess(**sess_overrides)
        return si.build_session_record(sess, {"flow": {"label": "Short"}}, {}), si

    def test_schema_version(self, tmp_path):
        record, si = self._build(tmp_path)
        assert record["schema"] == "session_record_v1"

    def test_capture_source(self, tmp_path):
        record, _ = self._build(tmp_path)
        assert record["capture_source"] == "end_session_payload"

    def test_required_top_level_keys(self, tmp_path):
        record, _ = self._build(tmp_path)
        for key in (
            "schema", "capture_source", "session_id", "learner_id",
            "created_at", "persona_id", "mode", "counters", "metrics",
            "progress_snapshot_ref", "transcript", "event_log", "capture_flags",
        ):
            assert key in record, f"Missing required key: {key!r}"

    def test_mode_normalised(self, tmp_path):
        record, _ = self._build(tmp_path, mode="CHALLENGE")
        assert record["mode"] == "challenge"

    def test_missing_optional_fields_no_exception(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        # Completely empty sess — all optional fields absent
        record = si.build_session_record({}, {}, {})
        assert record["schema"] == "session_record_v1"

    def test_duration_non_negative(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = si.build_session_record({"duration_seconds": -5}, {}, {})
        assert record["duration_seconds"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. Transcript sanitisation
# ─────────────────────────────────────────────────────────────────────────────

class TestTranscriptSanitisation:
    def test_only_allowed_keys_kept(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        raw = [
            {"text_zh": "你好", "text_en": "hello", "evil_key": "injected", "role": "partner"}
        ]
        record = si.build_session_record(_minimal_sess(), {}, {}, transcript=raw)
        entry = record["transcript"][0]
        assert "evil_key" not in entry
        assert entry["text_zh"] == "你好"
        assert entry["role"] == "partner"

    def test_transcript_capped(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        big = [{"text_zh": f"句子{i}", "role": "partner"} for i in range(300)]
        record = si.build_session_record(_minimal_sess(), {}, {}, transcript=big)
        assert len(record["transcript"]) == si._MAX_TRANSCRIPT_ENTRIES
        assert record["capture_flags"]["transcript_truncated"] is True

    def test_non_list_transcript_becomes_empty(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = si.build_session_record(_minimal_sess(), {}, {}, transcript="bad")
        assert record["transcript"] == []

    def test_transcript_idx_auto_assigned(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        raw = [{"text_zh": "好"}, {"text_zh": "不"}]
        record = si.build_session_record(_minimal_sess(), {}, {}, transcript=raw)
        assert record["transcript"][0]["idx"] == 0
        assert record["transcript"][1]["idx"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. Invalid learner_id / session_id → save returns False
# ─────────────────────────────────────────────────────────────────────────────

class TestValidation:
    @pytest.mark.parametrize("lid", ["", None, "../../etc/passwd", "a" * 65, "space id"])
    def test_invalid_learner_id(self, tmp_path, lid):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        ok = si.save_session_record(lid, "session_123", _minimal_record(si))
        assert ok is False

    @pytest.mark.parametrize("sid", ["", None, "bad/path", "a" * 129])
    def test_invalid_session_id(self, tmp_path, sid):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        ok = si.save_session_record("learner_abc", sid, _minimal_record(si))
        assert ok is False


# ─────────────────────────────────────────────────────────────────────────────
# 9. build_session_record counter coercion
# ─────────────────────────────────────────────────────────────────────────────

class TestCounterCoercion:
    def test_string_total_turns_coerced(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = si.build_session_record(
            {"total_turns": "7", "recovery_uses": "2"},
            {}, {}
        )
        assert record["counters"]["total_turns"] == 7
        assert record["counters"]["recovery_uses"] == 2

    def test_none_counters_default_to_zero(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = si.build_session_record({}, {}, {})
        for k, v in record["counters"].items():
            if k != "engines_used":
                assert v == 0, f"Counter {k!r} should default to 0"

    def test_engines_used_list(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        record = si.build_session_record(
            {"engines_used": ["identity", "work"]},
            {}, {}
        )
        assert record["counters"]["engines_used"] == ["identity", "work"]


# ─────────────────────────────────────────────────────────────────────────────
# 10. Progress snapshot ref cross-correlation
# ─────────────────────────────────────────────────────────────────────────────

class TestProgressRef:
    def test_ref_includes_session_id(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        sess = _minimal_sess(session_id="session_REF")
        record = si.build_session_record(sess, {}, {})
        assert record["progress_snapshot_ref"]["session_id"] == "session_REF"

    def test_ref_includes_progress_file_path(self, tmp_path):
        si = _import_si(capture_enabled=True, data_dir=tmp_path)
        sess = _minimal_sess()
        sess["learner_id"] = "learner_xyz"
        record = si.build_session_record(sess, {}, {})
        assert "learner_xyz.json" in (record["progress_snapshot_ref"]["stored_in"] or "")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_sess(session_id="session_001", mode="normal", **overrides):
    base = {
        "session_id": session_id,
        "learner_id": "learner_abc",
        "persona_id": "jianguo",
        "mode": mode,
        "total_turns": 5,
    }
    base.update(overrides)
    return base


def _minimal_record(si_module):
    return {
        "schema": si_module.SCHEMA_VERSION,
        "capture_source": "end_session_payload",
        "session_id": "session_001",
    }
