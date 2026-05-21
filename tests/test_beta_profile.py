#!/usr/bin/env python3
"""Unit tests for scripts/beta_profile.py (beta learner practice level persistence)."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"


def _load_beta_profile(tmp_path: Path):
    spec = importlib.util.spec_from_file_location("beta_profile", _SCRIPTS / "beta_profile.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["beta_profile"] = mod
    spec.loader.exec_module(mod)
    mod._PROFILES_DIR = tmp_path / "beta_profiles"
    mod._cache.clear()
    return mod


def test_save_and_load_profile(tmp_path):
    bp = _load_beta_profile(tmp_path)
    assert bp.save_profile("beta_alice", {"learner_level": "beginner"}) is True
    profile = bp.load_profile("beta_alice")
    assert profile["learner_level"] == "beginner"
    assert profile["level_source"] == "self_selected"
    assert profile["comfort_mode"] is True
    assert profile["level_selected_at"]


def test_unknown_learner_returns_empty(tmp_path):
    bp = _load_beta_profile(tmp_path)
    profile = bp.load_profile("beta_nobody")
    assert profile["learner_level"] is None
    assert profile["comfort_mode"] is None


def test_two_learners_isolated(tmp_path):
    bp = _load_beta_profile(tmp_path)
    bp.save_profile("beta_alice", {"learner_level": "beginner"})
    bp.save_profile("beta_bob", {"learner_level": "intermediate"})
    assert bp.load_profile("beta_alice")["learner_level"] == "beginner"
    assert bp.load_profile("beta_bob")["learner_level"] == "intermediate"
    assert bp.load_profile("beta_bob")["comfort_mode"] is False


def test_comfort_mode_derived_by_level(tmp_path):
    bp = _load_beta_profile(tmp_path)
    bp.save_profile("beta_a", {"learner_level": "lower_intermediate"})
    bp.save_profile("beta_b", {"learner_level": "intermediate"})
    assert bp.load_profile("beta_a")["comfort_mode"] is False
    assert bp.load_profile("beta_b")["comfort_mode"] is False


def test_invalid_learner_id_rejected(tmp_path):
    bp = _load_beta_profile(tmp_path)
    assert bp.save_profile("../evil", {"learner_level": "beginner"}) is False
    assert bp.save_profile("", {"learner_level": "beginner"}) is False


def test_invalid_level_rejected(tmp_path):
    bp = _load_beta_profile(tmp_path)
    assert bp.save_profile("beta_alice", {"learner_level": "expert"}) is False
    assert bp.load_profile("beta_alice")["learner_level"] is None


def test_operator_set_source(tmp_path):
    bp = _load_beta_profile(tmp_path)
    bp.save_profile(
        "default_learner",
        {"learner_level": "lower_intermediate", "level_source": "operator_set"},
    )
    profile = bp.load_profile("default_learner")
    assert profile["level_source"] == "operator_set"


def test_persists_to_disk(tmp_path):
    bp = _load_beta_profile(tmp_path)
    bp.save_profile("beta_alice", {"learner_level": "beginner"})
    bp._cache.clear()
    profile = bp.load_profile("beta_alice")
    assert profile["learner_level"] == "beginner"
    file_path = tmp_path / "beta_profiles" / "beta_alice.json"
    assert file_path.is_file()
    on_disk = json.loads(file_path.read_text(encoding="utf-8"))
    assert on_disk["learner_level"] == "beginner"
