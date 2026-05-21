#!/usr/bin/env python3
"""Unit tests for scripts/progress_store.py (beta per-learner progress persistence)."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"


def _load_progress_store(tmp_path: Path):
    """Load progress_store with PROGRESS_DIR redirected to tmp_path."""
    spec = importlib.util.spec_from_file_location("progress_store", _SCRIPTS / "progress_store.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["progress_store"] = mod
    spec.loader.exec_module(mod)
    mod._PROGRESS_DIR = tmp_path / "progress"
    mod._cache.clear()
    return mod


def test_save_and_load_snapshot(tmp_path):
    ps = _load_progress_store(tmp_path)
    snap = {"session_id": "s1", "total_turns": 10, "flow_display_label": "Stable"}
    assert ps.save_snapshot("beta_alice", snap) is True
    loaded = ps.load_snapshots("beta_alice")
    assert len(loaded) == 1
    assert loaded[0]["session_id"] == "s1"
    assert loaded[0]["learner_id"] == "beta_alice"


def test_unknown_learner_returns_empty(tmp_path):
    ps = _load_progress_store(tmp_path)
    assert ps.load_snapshots("beta_nobody") == []


def test_two_learners_isolated(tmp_path):
    ps = _load_progress_store(tmp_path)
    ps.save_snapshot("beta_alice", {"session_id": "a1", "total_turns": 5})
    ps.save_snapshot("beta_bob", {"session_id": "b1", "total_turns": 8})
    assert len(ps.load_snapshots("beta_alice")) == 1
    assert len(ps.load_snapshots("beta_bob")) == 1
    assert ps.load_snapshots("beta_alice")[0]["session_id"] == "a1"


def test_dedupe_by_session_id(tmp_path):
    ps = _load_progress_store(tmp_path)
    ps.save_snapshot("beta_alice", {"session_id": "s1", "total_turns": 10})
    ps.save_snapshot("beta_alice", {"session_id": "s1", "total_turns": 12})
    loaded = ps.load_snapshots("beta_alice")
    assert len(loaded) == 1
    assert loaded[0]["total_turns"] == 12


def test_invalid_learner_id_rejected(tmp_path):
    ps = _load_progress_store(tmp_path)
    assert ps.save_snapshot("../evil", {"session_id": "x"}) is False
    assert ps.save_snapshot("", {"session_id": "x"}) is False


def test_load_all(tmp_path):
    ps = _load_progress_store(tmp_path)
    ps.save_snapshot("beta_alice", {"session_id": "a1"})
    ps.save_snapshot("beta_bob", {"session_id": "b1"})
    all_data = ps.load_all()
    assert set(all_data.keys()) == {"beta_alice", "beta_bob"}
    assert len(all_data["beta_alice"]) == 1


def test_persists_to_disk(tmp_path):
    ps = _load_progress_store(tmp_path)
    ps.save_snapshot("beta_alice", {"session_id": "s1", "total_turns": 3})
    ps._cache.clear()
    loaded = ps.load_snapshots("beta_alice")
    assert len(loaded) == 1
    file_path = tmp_path / "progress" / "beta_alice.json"
    assert file_path.is_file()
    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert isinstance(on_disk, list)
    assert on_disk[0]["session_id"] == "s1"
