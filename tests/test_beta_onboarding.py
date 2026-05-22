#!/usr/bin/env python3
"""Beta onboarding — first-time user detection and client wiring."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
_UI = ROOT / "ui"


def _load_ui_server():
    spec = importlib.util.spec_from_file_location("ui_server_onboarding", _SCRIPTS / "ui_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_onboarding"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_is_first_time_true_when_no_progress_or_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("MANDARINOS_DATA_DIR", str(tmp_path))
    srv = _load_ui_server()
    assert srv._is_first_time_beta_user("beta_newuser") is True


def test_is_first_time_false_when_memory_populated(tmp_path, monkeypatch):
    monkeypatch.setenv("MANDARINOS_DATA_DIR", str(tmp_path))
    srv = _load_ui_server()
    srv._lm_save("beta_alice", {
        "learner_name": "Alice",
        "hometown": None,
        "lives_in": None,
        "job_or_study": None,
        "family": None,
        "favourite_food": None,
    })
    assert srv._is_first_time_beta_user("beta_alice") is False


def test_is_first_time_false_when_progress_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("MANDARINOS_DATA_DIR", str(tmp_path))
    srv = _load_ui_server()
    srv._ps_save_snapshot("beta_bob", {"session_id": "s1", "total_turns": 3})
    assert srv._is_first_time_beta_user("beta_bob") is False


def test_learner_memory_is_empty_helper():
    srv = _load_ui_server()
    assert srv._learner_memory_is_empty({}) is True
    assert srv._learner_memory_is_empty({"learner_name": None, "hometown": ""}) is True
    assert srv._learner_memory_is_empty({"learner_name": "Ming"}) is False


def test_api_payloads_include_first_time_flag():
    src = (_SCRIPTS / "ui_server.py").read_text(encoding="utf-8")
    assert "is_first_time_beta_user" in src
    assert '_is_first_time_beta_user(learner_id)' in src


def test_client_first_time_wiring():
    src = (_UI / "app.js").read_text(encoding="utf-8")
    assert "is_first_time_beta_user" in src
    assert "_applyFirstTimeBetaHygiene" in src
    assert "_dismissOnboardingGuideIfActive" in src
    assert "Choose persona and conversation frame, then try to have a conversation." in src
    assert "Getting started" in src


def test_starting_point_label_updated():
    html = (_UI / "index.html").read_text(encoding="utf-8")
    assert "Choose Your Starting Point" in html
    assert "Starting point</span>" not in html


def test_memory_empty_copy_updated():
    src = (_UI / "app.js").read_text(encoding="utf-8")
    assert "No saved learner memory yet." in src
    assert "Memory — empty" not in src
