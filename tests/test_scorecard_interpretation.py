#!/usr/bin/env python3
"""
Scorecard + progress interpretation alignment tests.

Messy sustained sessions should interpret more strongly than short passive clean ones.
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


MESSY_SUSTAINED = {
    "total_turns": 28,
    "questions_asked": 5,
    "unmatched_responses": 6,
    "soft_unmatched_responses": 4,
    "depth_responses": 5,
    "recovery_uses": 4,
    "successful_recoveries": 3,
    "suggestion_clicks": 3,
    "card_opens": 2,
}

SHORT_PASSIVE_CLEAN = {
    "total_turns": 8,
    "questions_asked": 0,
    "unmatched_responses": 0,
    "soft_unmatched_responses": 0,
    "depth_responses": 0,
    "recovery_uses": 0,
    "successful_recoveries": 0,
}


def _cap_strength(cap: dict) -> int:
    """Rough strength: headline + line count."""
    n = len(cap.get("capability_lines") or []) + len(cap.get("progress_lines") or [])
    if cap.get("headline"):
        n += 3
    if cap.get("strong_initiative"):
        n += 2
    return n


def test_messy_sustained_stronger_than_short_passive():
    srv = _load_ui_server()
    messy = srv._scorecard_conversation_capability(MESSY_SUSTAINED)
    clean = srv._scorecard_conversation_capability(SHORT_PASSIVE_CLEAN)
    assert _cap_strength(messy) > _cap_strength(clean)
    assert messy["strong_initiative"] is True
    assert clean["strong_initiative"] is False


def test_turbulence_survived_signals():
    srv = _load_ui_server()
    sig = srv._derive_conversation_signals(MESSY_SUSTAINED)
    assert sig["turbulence_survived"] is True
    assert sig["continued_after_ambiguity"] is True
    assert sig["extended_imperfect"] is True


def test_continued_after_ambiguity_without_formal_recovery_only():
    srv = _load_ui_server()
    sess = {
        "total_turns": 14,
        "questions_asked": 2,
        "unmatched_responses": 3,
        "soft_unmatched_responses": 0,
        "depth_responses": 2,
        "recovery_uses": 0,
        "successful_recoveries": 0,
    }
    sig = srv._derive_conversation_signals(sess)
    assert sig["continued_after_ambiguity"] is True


def test_progress_stability_bonus_for_messy_sustained():
    srv = _load_ui_server()
    metrics_messy = srv._compute_scorecard(MESSY_SUSTAINED)
    snap_messy = srv._build_progress_snapshot(MESSY_SUSTAINED, metrics_messy)
    base_only = srv._conversation_stability_score(
        metrics_messy["stability"], MESSY_SUSTAINED["total_turns"], None,
    )
    assert snap_messy["conversation_stability_score"] is not None
    assert base_only is not None
    # Engagement bonus raises progress score above raw unclear-rate alone.
    assert snap_messy["conversation_stability_score"] > base_only
    assert snap_messy["progress_signals"]["turbulence_survived"] is True


def test_messy_beats_collapsed_short_session_on_interpretation():
    """High-noise but sustained beats brief collapse — via capability, not raw 100% stability."""
    srv = _load_ui_server()
    collapsed = {
        "total_turns": 10,
        "questions_asked": 0,
        "unmatched_responses": 7,
        "soft_unmatched_responses": 0,
        "depth_responses": 0,
        "recovery_uses": 0,
        "successful_recoveries": 0,
    }
    messy = srv._scorecard_conversation_capability(MESSY_SUSTAINED)
    collapsed_cap = srv._scorecard_conversation_capability(collapsed)
    assert _cap_strength(messy) > _cap_strength(collapsed_cap)


def test_messy_session_human_facing_lines():
    srv = _load_ui_server()
    cap = srv._scorecard_conversation_capability(MESSY_SUSTAINED)
    joined = " ".join(cap["capability_lines"] + cap["progress_lines"]).lower()
    assert "unclear" in joined or "difficult" in joined or "imperfect" in joined
    assert cap["headline"]


def test_communicative_ambition_signal_and_copy():
    srv = _load_ui_server()
    sess = {
        "total_turns": 14,
        "questions_asked": 1,
        "unmatched_responses": 2,
        "soft_unmatched_responses": 4,
        "depth_responses": 0,
        "recovery_uses": 0,
        "successful_recoveries": 0,
    }
    sig = srv._derive_conversation_signals(sess)
    assert sig["communicative_ambition"] is True
    cap = srv._scorecard_conversation_capability(sess)
    joined = " ".join(cap["capability_lines"]).lower()
    assert "courage" in joined or "messy" in joined


def test_progress_snapshot_includes_communicative_ambition():
    srv = _load_ui_server()
    sess = {
        "total_turns": 14,
        "questions_asked": 1,
        "unmatched_responses": 2,
        "soft_unmatched_responses": 4,
        "depth_responses": 0,
        "recovery_uses": 0,
        "successful_recoveries": 0,
    }
    metrics = srv._compute_scorecard(sess)
    snap = srv._build_progress_snapshot(sess, metrics)
    assert snap["progress_signals"].get("communicative_ambition") is True


def test_scorecard_stability_labels_unchanged():
    """Raw stability labels still come from rate — interpretation layer is separate."""
    srv = _load_ui_server()
    m = srv._compute_scorecard(MESSY_SUSTAINED)
    assert "label" in m["stability"]
    assert m["stability"]["raw_unmatched"] == 6
