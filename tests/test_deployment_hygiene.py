#!/usr/bin/env python3
"""Deployment hygiene — PORT and MANDARINOS_DATA_DIR for Railway beta hosting."""

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"


def _load_module(name: str, filename: str, *, env: dict | None = None):
    """Load a scripts module with optional env overrides applied before exec."""
    saved = {k: os.environ.get(k) for k in (env or {})}
    try:
        if env:
            for k, v in env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        spec = importlib.util.spec_from_file_location(name, _SCRIPTS / filename)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_ui_server_reads_port_from_environment():
    src = (_SCRIPTS / "ui_server.py").read_text(encoding="utf-8")
    assert 'port = int(os.environ.get("PORT", 8765))' in src
    assert "http://0.0.0.0:{port}" in src
    assert 'ThreadedHTTPServer(("", port), Handler)' in src


def test_requirements_and_procfile_present():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "deep-translator>=1.11.4" in req
    proc = (ROOT / "Procfile").read_text(encoding="utf-8").strip()
    assert proc == "web: python scripts/ui_server.py"


def test_mandarinos_data_dir_overrides_progress_store(tmp_path, monkeypatch):
    monkeypatch.delenv("MANDARINOS_DATA_DIR", raising=False)
    data_root = tmp_path / "railway_data"
    mod = _load_module(
        "progress_store_deploy",
        "progress_store.py",
        env={"MANDARINOS_DATA_DIR": str(data_root)},
    )
    mod._cache.clear()
    assert mod.BASE_DATA_DIR == data_root
    assert mod._PROGRESS_DIR == data_root / "progress"
    mod.save_snapshot("beta_alice", {"session_id": "s1", "total_turns": 4})
    assert (data_root / "progress" / "beta_alice.json").is_file()


def test_mandarinos_data_dir_overrides_beta_profile(tmp_path, monkeypatch):
    monkeypatch.delenv("MANDARINOS_DATA_DIR", raising=False)
    data_root = tmp_path / "railway_data"
    mod = _load_module(
        "beta_profile_deploy",
        "beta_profile.py",
        env={"MANDARINOS_DATA_DIR": str(data_root)},
    )
    mod._cache.clear()
    assert mod.BASE_DATA_DIR == data_root
    assert mod._PROFILES_DIR == data_root / "beta_profiles"
    mod.save_profile("beta_alice", {"learner_level": "beginner"})
    assert (data_root / "beta_profiles" / "beta_alice.json").is_file()


def test_mandarinos_data_dir_overrides_learner_memory(tmp_path, monkeypatch):
    monkeypatch.delenv("MANDARINOS_DATA_DIR", raising=False)
    data_root = tmp_path / "railway_data"
    mod = _load_module(
        "learner_memory_deploy",
        "learner_memory.py",
        env={"MANDARINOS_DATA_DIR": str(data_root)},
    )
    mod._store.clear()
    assert mod.BASE_DATA_DIR == data_root
    assert mod._PERSISTENCE_PATH == data_root / "learner_memory.json"
    mod.save("beta_alice", {"learner_name": "Alice"})
    assert (data_root / "learner_memory.json").is_file()
    loaded = mod.load("beta_alice")
    assert loaded.get("learner_name") == "Alice"


def test_default_data_dir_when_env_absent(monkeypatch):
    monkeypatch.delenv("MANDARINOS_DATA_DIR", raising=False)
    mod = _load_module("progress_store_default", "progress_store.py", env={})
    expected = ROOT / "data" / "progress"
    assert mod._PROGRESS_DIR == expected
