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
    """Messy sustained sessions score below perfect but retain positive interpretation."""
    srv = _load_ui_server()
    metrics_messy = srv._compute_scorecard(MESSY_SUSTAINED)
    snap_messy = srv._build_progress_snapshot(MESSY_SUSTAINED, metrics_messy)
    assert snap_messy["conversation_stability_score"] is not None
    assert snap_messy["conversation_stability_score"] < 80
    assert snap_messy["progress_signals"]["turbulence_survived"] is True
    cap = srv._scorecard_conversation_capability(MESSY_SUSTAINED)
    assert cap["headline"]


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


def test_session_interpretation_aligns_with_progress_snapshot():
    """Scorecard session_interpretation must match progress snapshot labels."""
    srv = _load_ui_server()
    sess = {
        "total_turns": 28,
        "questions_asked": 7,
        "unmatched_responses": 4,
        "soft_unmatched_responses": 3,
        "recovery_uses": 2,
        "successful_recoveries": 2,
        "conversational_recoveries": 3,
        "successful_conversational_recoveries": 2,
        "display_en_clicks": 2,
        "hint_clicks": 1,
    }
    metrics = srv._compute_scorecard(sess)
    snap = srv._build_progress_snapshot(sess, metrics)
    interpretation = {
        "flow": snap["flow_display_label"],
        "recovery": snap["recovery_display_label"],
        "support": snap["support_display_label"],
    }
    assert interpretation["flow"] != "Smooth"
    assert "Independent" not in interpretation["support"]
    assert interpretation["recovery"] != "Smooth"


def test_supported_session_not_labelled_independent():
    srv = _load_ui_server()
    snap = srv._build_progress_snapshot(
        {"total_turns": 20, "display_en_clicks": 4, "hint_clicks": 2},
        srv._compute_scorecard(
            {"total_turns": 20, "display_en_clicks": 4, "hint_clicks": 2},
        ),
    )
    assert snap["support_display_label"] in ("Moderate", "Heavy")
    assert snap["support_display_label"] != "None"


def test_scorecard_stability_labels_unchanged():
    """Raw stability labels still come from rate — interpretation layer is separate."""
    srv = _load_ui_server()
    m = srv._compute_scorecard(MESSY_SUSTAINED)
    assert "label" in m["stability"]
    assert m["stability"]["raw_unmatched"] == 6


def test_conversational_recovery_display_without_phrase_uses():
    srv = _load_ui_server()
    sess = {
        "total_turns": 18,
        "recovery_uses": 0,
        "successful_recoveries": 0,
        "conversational_recoveries": 2,
        "successful_conversational_recoveries": 2,
    }
    m = srv._compute_scorecard(sess)
    rec = m["recovery"]
    assert rec["raw_uses"] == 0
    assert rec["conversational_recoveries"] == 2
    assert "got back on track" in rec["display_summary"].lower()
    assert rec["label"] != "Smooth"


def test_conversational_recovery_zero_unchanged():
    srv = _load_ui_server()
    sess = {"total_turns": 10, "recovery_uses": 0, "successful_recoveries": 0}
    m = srv._compute_scorecard(sess)
    assert m["recovery"]["display_summary"] == "0 recovery moments"
    assert m["recovery"]["label"] == "Smooth"


def test_conversational_recovery_signals_continued_after_ambiguity():
    srv = _load_ui_server()
    sess = {
        "total_turns": 12,
        "recovery_uses": 0,
        "successful_recoveries": 0,
        "conversational_recoveries": 1,
        "successful_conversational_recoveries": 1,
        "unmatched_responses": 2,
        "depth_responses": 0,
        "questions_asked": 0,
    }
    sig = srv._derive_conversation_signals(sess)
    assert sig["continued_after_ambiguity"] is True


def test_display_support_does_not_change_recovery_metric():
    srv = _load_ui_server()
    base = {"total_turns": 15, "recovery_uses": 0, "successful_recoveries": 0}
    with_display = {
        **base,
        "display_en_clicks": 8,
        "display_py_clicks": 5,
        "hint_clicks": 4,
        "conversational_recoveries": 0,
    }
    assert srv._compute_scorecard(base)["recovery"] == srv._compute_scorecard(with_display)["recovery"]


def test_progress_snapshot_includes_conversational_recovery_fields():
    srv = _load_ui_server()
    sess = {
        "total_turns": 14,
        "conversational_recoveries": 2,
        "successful_conversational_recoveries": 1,
    }
    snap = srv._build_progress_snapshot(sess, srv._compute_scorecard(sess))
    assert snap["conversational_recoveries"] == 2
    assert snap["successful_conversational_recoveries"] == 1
