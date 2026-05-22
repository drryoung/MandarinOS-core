#!/usr/bin/env python3
"""Recovery phrase deployment — runtime fallback and client render wiring."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
_UI = ROOT / "ui"


def _load_ui_server():
    spec = importlib.util.spec_from_file_location("ui_server_recovery", _SCRIPTS / "ui_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_recovery"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_recovery_runtime_payload_from_content():
    srv = _load_ui_server()
    payload = srv._recovery_phrases_runtime_payload()
    assert payload is not None
    assert payload.get("schema") == "recovery_phrases_v1"
    phrases = payload.get("phrases") or []
    assert len(phrases) > 0
    learner = [
        p for p in phrases
        if (p.get("use") or "not_understood") in ("not_understood", "topic_reset", "topic_shift")
    ]
    assert len(learner) > 0
    core = [p for p in learner if p.get("always_surface") is True]
    assert len(core) > 0


def test_recovery_runtime_fallback_wired_in_ui_server():
    src = (_SCRIPTS / "ui_server.py").read_text(encoding="utf-8")
    assert "_recovery_phrases_runtime_payload" in src
    assert "recovery_phrases.runtime.json" in src
    assert "not file_path.is_file()" in src


def test_client_recovery_render_wiring():
    src = (_UI / "app.js").read_text(encoding="utf-8")
    assert "function renderRecoveryPanelInto" in src
    assert "function getRecoveryPanelOption" in src
    assert "recovery-card" in src
    assert "_scrollRecoveryPanelIntoView" in src
    assert "loadRecoveryPhrases" in src


def test_comfort_mode_does_not_hide_recovery_css():
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    assert ".option-panel.recovery-card" in css
    for line in css.splitlines():
        if "comfort-mode" in line and "recovery" in line and "display: none" in line:
            raise AssertionError(f"comfort-mode hides recovery: {line}")


def test_recovery_phrases_content_committed():
    path = ROOT / "content" / "recovery_phrases.json"
    assert path.is_file(), "content/recovery_phrases.json must be in repo for Railway fallback"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
