#!/usr/bin/env python3
"""
Scorecard conversation-capability interpretation tests.

Pure unit tests on ui_server scorecard helpers — no running server required.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"


def _load_ui_server():
    spec = importlib.util.spec_from_file_location("ui_server", _SCRIPTS / "ui_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_alpha_session_positive_wording():
    """25 turns, 6 questions, 3 unmatched → resilience + sustained conversation wording."""
    srv = _load_ui_server()
    sess = {
        "total_turns": 25,
        "questions_asked": 6,
        "unmatched_responses": 3,
        "depth_responses": 4,
        "suggestion_clicks": 2,
        "card_opens": 1,
    }
    m = srv._compute_scorecard(sess)
    cap = m["conversation_capability"]
    stab = m["stability"]

    assert stab["label"] == "Conversation stayed on track"
    assert any("real conversation going" in line for line in cap["capability_lines"])
    assert any("drive" in line or "lead" in line for line in cap["capability_lines"])
    assert any(
        "unclear" in line or "difficult" in line
        for line in cap["progress_lines"]
    )
    assert cap["headline"] and (
        "sustained" in cap["headline"].lower()
        or "real conversation" in cap["headline"].lower()
    )
    assert cap["strong_initiative"] is True


def test_high_unmatched_ratio_shows_friction():
    """High unclear-turn ratio → Some friction or worse (not 'stayed on track')."""
    srv = _load_ui_server()
    sess = {
        "total_turns": 12,
        "questions_asked": 1,
        "unmatched_responses": 5,
        "depth_responses": 0,
    }
    m = srv._compute_scorecard(sess)
    assert m["stability"]["label"] in ("Some friction", "Unstable", "Breaking down")
    assert m["stability"]["label"] != "Conversation stayed on track"


def test_low_question_count_no_lead_line():
    """Few questions → no 'helped lead the conversation' line."""
    srv = _load_ui_server()
    sess = {
        "total_turns": 22,
        "questions_asked": 1,
        "unmatched_responses": 2,
        "depth_responses": 1,
    }
    cap = srv._scorecard_conversation_capability(sess)
    assert not any("helped lead" in line for line in cap["capability_lines"])


def test_high_support_does_not_block_strong_initiative_flag():
    """Many hint/support uses still allow strong_initiative when conversation was sustained."""
    srv = _load_ui_server()
    sess = {
        "total_turns": 25,
        "questions_asked": 6,
        "unmatched_responses": 3,
        "suggestion_clicks": 15,
        "card_opens": 10,
    }
    cap = srv._scorecard_conversation_capability(sess)
    assert cap["strong_initiative"] is True
    assert cap["support_uses"] == 25
    assert any("real conversation going" in line for line in cap["capability_lines"])
