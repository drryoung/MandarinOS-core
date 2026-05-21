#!/usr/bin/env python3
"""
Phase 1 progress tracking — snapshot helpers and retention rules.

Pure unit tests on ui_server progress helpers; retention mirrors client applyRetention.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"

_REQUIRED_SNAPSHOT_KEYS = {
    "session_id",
    "created_at",
    "tier",
    "persona_id",
    "mode",
    "duration_seconds",
    "total_turns",
    "questions_asked",
    "recovery_uses",
    "successful_recoveries",
    "unclear_turns",
    "depth_responses",
    "engines_used",
    "suggestion_clicks",
    "card_opens",
    "conversation_stability_score",
    "recovery_success_rate",
}


def _load_ui_server():
    spec = importlib.util.spec_from_file_location("ui_server", _SCRIPTS / "ui_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server"] = mod
    spec.loader.exec_module(mod)
    return mod


def _apply_retention(history: list, tier: str) -> list:
    """Mirror of ui/app.js applyRetention — keep in sync for Phase 1."""
    if tier == "premium":
        return list(history)
    return list(history)[-10:]


def _make_snapshot(srv, sess_overrides=None):
    sess = {
        "session_id": "test_session_1",
        "mode": "normal",
        "total_turns": 10,
        "recovery_uses": 0,
        "successful_recoveries": 0,
        "suggestion_clicks": 0,
        "card_opens": 0,
        "questions_asked": 2,
        "depth_responses": 1,
        "unmatched_responses": 0,
        "soft_unmatched_responses": 0,
        "engines_used": ["place"],
    }
    if sess_overrides:
        sess.update(sess_overrides)
    metrics = srv._compute_scorecard(sess)
    return srv._build_progress_snapshot(
        sess,
        metrics,
        tier="standard",
        persona_id="founder_raymond_v1",
        duration_seconds=120,
    )


def test_snapshot_structure():
    srv = _load_ui_server()
    snap = _make_snapshot(srv)
    assert _REQUIRED_SNAPSHOT_KEYS <= set(snap.keys())
    assert snap["session_id"] == "test_session_1"
    assert snap["tier"] == "standard"
    assert snap["persona_id"] == "founder_raymond_v1"
    assert snap["mode"] == "normal"
    assert snap["total_turns"] == 10
    assert snap["engines_used"] == ["place"]


def test_stability_score_forty_turns_two_unclear():
    """40 turns, 2 hard unclear — turbulence-aware score, not inflated to ~100."""
    srv = _load_ui_server()
    sess = {
        "total_turns": 40,
        "unmatched_responses": 2,
        "soft_unmatched_responses": 0,
    }
    metrics = srv._compute_scorecard(sess)
    assert metrics["stability"]["rate"] == 0.05
    score = srv._conversation_stability_score(metrics["stability"], 40, sess)
    assert score is not None
    assert score < 100
    assert 80 <= score <= 94
    snap = srv._build_progress_snapshot(sess, metrics)
    assert snap["conversation_stability_score"] == score
    assert snap["unclear_turns"] == 2
    assert "Messy but sustained" in snap["stability_display_label"] or "Stayed on track" in snap["stability_display_label"] or "Stable" in snap["stability_display_label"]


def test_stability_score_none_for_short_session():
    srv = _load_ui_server()
    sess = {"total_turns": 1, "unmatched_responses": 0}
    metrics = srv._compute_scorecard(sess)
    assert srv._conversation_stability_score(metrics["stability"], 1) is None
    snap = srv._build_progress_snapshot(sess, metrics)
    assert snap["conversation_stability_score"] is None


def test_standard_retention_keeps_latest_ten():
    history = [{"session_id": f"s{i}"} for i in range(15)]
    kept = _apply_retention(history, "standard")
    assert len(kept) == 10
    assert kept[0]["session_id"] == "s5"
    assert kept[-1]["session_id"] == "s14"


def test_premium_retention_keeps_all():
    history = [{"session_id": f"s{i}"} for i in range(15)]
    kept = _apply_retention(history, "premium")
    assert len(kept) == 15


def test_no_recoveries_recovery_rate_not_zero():
    srv = _load_ui_server()
    snap = _make_snapshot(srv, {"recovery_uses": 0, "successful_recoveries": 0})
    assert snap["recovery_success_rate"] is None
    assert snap["recovery_uses"] == 0


def test_recoveries_set_recovery_rate():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {"recovery_uses": 4, "successful_recoveries": 3},
    )
    assert snap["recovery_success_rate"] == 0.75


def test_end_session_response_includes_progress_fields():
    """Static check: /api/end_session builds progress_snapshot in handler."""
    src = (_SCRIPTS / "ui_server.py").read_text(encoding="utf-8")
    assert "progress_snapshot" in src
    assert '"progress_saved"' in src or "'progress_saved'" in src
    assert "_build_progress_snapshot" in src


def _get_progress_sessions_for_display(history: list, tier: str) -> list:
    """Mirror of ui/app.js getProgressSessionsForDisplay — keep in sync."""
    max_standard = 10
    max_premium = 30
    h = list(history)
    if tier == "premium":
        return h[-max_premium:]
    return h[-max_standard:]


def _load_app_js():
    return (ROOT / "ui" / "app.js").read_text(encoding="utf-8")


def _load_index_html():
    return (ROOT / "ui" / "index.html").read_text(encoding="utf-8")


def test_phase2_progress_view_functions_present():
    src = _load_app_js()
    assert "function renderProgressView" in src
    assert "function renderStabilityChart" in src
    assert "function buildProgressHeadline" in src
    assert "function getProgressSessionsForDisplay" in src
    assert "function initRightPanelTabs" in src


def test_phase2_no_external_chart_libraries():
    src = _load_app_js()
    for lib in ("chart.js", "Chart.js", "recharts", "d3", "plotly"):
        assert lib.lower() not in src.lower()


def test_phase2_svg_chart_uses_create_element_ns():
    src = _load_app_js()
    assert 'createElementNS("http://www.w3.org/2000/svg"' in src
    assert "progress-stability-chart" in src


def test_phase2_index_has_session_progress_tabs():
    html = _load_index_html()
    assert "rightTabSession" in html
    assert "rightTabProgress" in html
    assert 'id="progressView"' in html
    assert "rightPanelProgress" in html


def test_phase2_standard_display_max_ten():
    history = [{"session_id": f"s{i}", "conversation_stability_score": 80} for i in range(15)]
    shown = _get_progress_sessions_for_display(history, "standard")
    assert len(shown) == 10
    assert shown[0]["session_id"] == "s5"


def test_phase2_premium_display_capped_at_thirty():
    history = [{"session_id": f"s{i}"} for i in range(40)]
    shown = _get_progress_sessions_for_display(history, "premium")
    assert len(shown) == 30
    assert shown[0]["session_id"] == "s10"


def test_phase2_premium_retention_still_keeps_all_in_storage_mirror():
    """Premium storage retention (Phase 1) is separate from display cap (Phase 2)."""
    history = [{"session_id": f"s{i}"} for i in range(15)]
    stored = _apply_retention(history, "premium")
    assert len(stored) == 15


def test_phase2_build_headline_low_history():
    """Headline helper is in JS; mirror minimal logic for null-safe scores."""
    sessions = [
        {"conversation_stability_score": None, "total_turns": 1},
        {"conversation_stability_score": 90, "total_turns": 8},
    ]
    scores = [
        s["conversation_stability_score"]
        for s in sessions
        if s["conversation_stability_score"] is not None
    ]
    assert len(scores) < 2
    # renderProgressView must not throw on null scores — static guard
    src = _load_app_js()
    assert "conversation_stability_score" in src
    assert "progress-chart-dot--dim" in src


def test_phase2_empty_state_copy_in_app():
    src = _load_app_js()
    assert "No progress record yet" in src
    assert "building your speaking progress history" in src.lower()


def _format_learning_support(snap: dict) -> str:
    """Mirror of ui/app.js _formatSupportCell — tier label for tests."""
    if snap.get("support_display_label"):
        return snap["support_display_label"]
    n = sum(
        snap.get(k) or 0
        for k in (
            "suggestion_clicks", "hint_clicks", "display_en_clicks",
            "display_py_clicks", "translation_help_uses",
        )
    )
    if n == 0:
        return "None"
    if n <= 2:
        return "Light"
    if n <= 5:
        return "Moderate"
    return "Heavy"


def _format_flow_cell(snap: dict) -> str:
    """Mirror of ui/app.js _formatFlowCell."""
    if snap.get("flow_display_label"):
        return snap["flow_display_label"]
    label = snap.get("stability_display_label") or ""
    if " · " in label:
        return label.split(" · ", 1)[1]
    return label or "—"


def test_snapshot_includes_display_and_hint_support_fields():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {
            "display_en_clicks": 4,
            "display_py_clicks": 3,
            "hint_clicks": 2,
        },
    )
    assert snap["display_en_clicks"] == 4
    assert snap["display_py_clicks"] == 3
    assert snap["hint_clicks"] == 2


def test_snapshot_support_fields_default_zero_when_absent():
    srv = _load_ui_server()
    snap = _make_snapshot(srv)
    assert snap.get("display_en_clicks", 0) == 0
    assert snap.get("display_py_clicks", 0) == 0
    assert snap.get("hint_clicks", 0) == 0


def test_format_support_legacy_snapshot():
    assert _format_learning_support({"suggestion_clicks": 2, "card_opens": 1}) == "Light"


def test_format_support_en_only():
    assert _format_learning_support({"display_en_clicks": 4}) == "Moderate"


def test_format_support_py_only():
    assert _format_learning_support({"display_py_clicks": 3}) == "Moderate"


def test_format_support_mixed():
    assert _format_learning_support(
        {
            "hint_clicks": 2,
            "display_en_clicks": 5,
            "card_opens": 1,
        },
    ) == "Heavy"


def test_format_support_none_when_all_zero():
    assert _format_learning_support({}) == "None"
    assert _format_learning_support(
        {
            "suggestion_clicks": 0,
            "card_opens": 0,
            "hint_clicks": 0,
            "display_en_clicks": 0,
            "display_py_clicks": 0,
        },
    ) == "None"


def test_scorecard_support_unchanged_by_display_fields():
    """Display/hint telemetry must not alter scorecard support metric."""
    srv = _load_ui_server()
    base = {
        "total_turns": 20,
        "suggestion_clicks": 2,
        "card_opens": 1,
    }
    with_display = {
        **base,
        "display_en_clicks": 10,
        "display_py_clicks": 8,
        "hint_clicks": 5,
    }
    m_base = srv._compute_scorecard(base)
    m_disp = srv._compute_scorecard(with_display)
    assert m_base["support"] == m_disp["support"]


def test_progress_ui_flow_and_support_columns():
    src = _load_app_js()
    assert "Flow" in src
    assert "Support" in src
    assert "function _formatFlowCell" in src
    assert "function _formatSupportCell" in src
    assert "flow_display_label" in src
    assert "support_display_label" in src
    assert "session_interpretation" in src


def test_progress_ui_learning_support_column_and_tracking():
    src = _load_app_js()
    assert "translation_help_uses" in src
    assert "display_en_clicks" in src
    assert "display_py_clicks" in src
    assert "hint_clicks:" in src
    assert "function toggleLinePinyin" in src
    assert "!st.showEn) _tracker.display_en_clicks" in src
    assert "!st.showPy) _tracker.display_py_clicks" in src


def test_progress_recovery_not_needed_removed():
    src = _load_app_js()
    assert "Not needed" not in src
    assert "recovery_display_label" in src
    assert "function _formatRecoveryCell" in src


def test_progress_recovery_self_recovered_after_confusion():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {
            "total_turns": 18,
            "unmatched_responses": 2,
            "conversational_recoveries": 2,
            "successful_conversational_recoveries": 2,
            "recovery_uses": 0,
            "questions_asked": 1,
        },
    )
    assert snap["recovery_display_label"] in ("Self-recovered", "Self-recovered often")
    assert "Not needed" not in snap["recovery_display_label"]


def test_progress_recovery_stayed_on_track_without_formal_recovery():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {
            "total_turns": 15,
            "unmatched_responses": 2,
            "recovery_uses": 0,
            "conversational_recoveries": 0,
            "successful_conversational_recoveries": 0,
            "questions_asked": 2,
            "depth_responses": 1,
        },
    )
    assert snap["recovery_display_label"] in ("Stayed on track", "Kept going")


def test_progress_recovery_smooth_clean_session():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {"unmatched_responses": 0, "recovery_uses": 0},
    )
    assert snap["recovery_display_label"] == "Smooth"


def test_progress_recovery_used_support_when_phrase_cards():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {
            "recovery_uses": 4,
            "successful_recoveries": 3,
            "unmatched_responses": 1,
        },
    )
    assert snap["recovery_display_label"].startswith("App-assisted")


def test_progress_stability_clean_session_can_score_100():
    srv = _load_ui_server()
    snap = _make_snapshot(srv, {"total_turns": 20, "unmatched_responses": 0, "recovery_uses": 0})
    assert snap["conversation_stability_score"] == 100
    assert "Smooth" in snap["stability_display_label"]


def test_progress_stability_one_unclear_cannot_be_100():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {
            "total_turns": 18,
            "unmatched_responses": 1,
            "questions_asked": 4,
            "depth_responses": 10,
            "recovery_uses": 0,
        },
    )
    assert snap["conversation_stability_score"] < 100
    assert 85 <= snap["conversation_stability_score"] <= 92
    assert "Stayed on track" in snap["stability_display_label"] or "Stable" in snap["stability_display_label"]
    assert "Smooth" not in snap["stability_display_label"]


def test_progress_stability_two_unclear_short_session_messy_band():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {
            "total_turns": 8,
            "unmatched_responses": 2,
            "questions_asked": 2,
            "recovery_uses": 0,
        },
    )
    assert snap["conversation_stability_score"] < 80
    assert 65 <= snap["conversation_stability_score"] <= 79
    assert "Messy but sustained" in snap["stability_display_label"]


def test_progress_stability_one_unclear_short_session_stable_band():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {"total_turns": 8, "unmatched_responses": 1, "questions_asked": 1},
    )
    assert snap["conversation_stability_score"] < 100
    assert 80 <= snap["conversation_stability_score"] <= 92
    assert "Smooth" not in snap["stability_display_label"]


def test_progress_stability_messy_sustained_not_perfect():
    srv = _load_ui_server()
    sess = {
        "total_turns": 28,
        "questions_asked": 5,
        "unmatched_responses": 6,
        "soft_unmatched_responses": 4,
        "depth_responses": 5,
        "recovery_uses": 4,
        "successful_recoveries": 3,
    }
    metrics = srv._compute_scorecard(sess)
    snap = srv._build_progress_snapshot(sess, metrics)
    assert snap["conversation_stability_score"] < 80
    assert snap["progress_signals"]["turbulence_survived"] is True
    cap = srv._scorecard_conversation_capability(sess)
    assert cap["headline"]


def test_progress_stability_label_messy_but_sustained():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {
            "total_turns": 40,
            "unmatched_responses": 2,
            "questions_asked": 2,
            "depth_responses": 2,
        },
    )
    assert snap["conversation_stability_score"] < 100
    assert "Smooth" not in snap["stability_display_label"]


def test_progress_stability_smooth_when_no_unclear():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {"total_turns": 20, "unmatched_responses": 0},
    )
    assert "Smooth" in snap["stability_display_label"]


def test_learning_support_separate_from_recovery_display():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {
            "unmatched_responses": 2,
            "conversational_recoveries": 1,
            "successful_conversational_recoveries": 1,
            "display_en_clicks": 6,
            "card_opens": 3,
        },
    )
    assert snap["recovery_display_label"] in ("Self-recovered", "Self-recovered often")
    assert _format_learning_support(snap) == "Heavy"
    assert snap.get("card_exploration_count") == 3


def test_card_opens_do_not_change_stability_score():
    srv = _load_ui_server()
    base = {"total_turns": 20, "unmatched_responses": 0}
    with_cards = {**base, "card_opens": 12, "display_en_clicks": 8, "hint_clicks": 5}
    snap_base = _make_snapshot(srv, base)
    snap_cards = _make_snapshot(srv, with_cards)
    assert snap_base["conversation_stability_score"] == snap_cards["conversation_stability_score"]
    assert snap_base["flow_display_label"] == snap_cards["flow_display_label"]


def test_card_opens_do_not_inflate_support_tier():
    srv = _load_ui_server()
    snap = _make_snapshot(srv, {"card_opens": 10, "suggestion_clicks": 0})
    assert snap["support_display_label"] == "None"
    assert snap["card_exploration_count"] == 10


def test_turbulent_28_turn_session_display_labels():
    """Alpha-style messy sustained session — not near-perfect smooth."""
    srv = _load_ui_server()
    sess = {
        "total_turns": 28,
        "questions_asked": 7,
        "unmatched_responses": 4,
        "soft_unmatched_responses": 3,
        "depth_responses": 5,
        "recovery_uses": 2,
        "successful_recoveries": 2,
        "conversational_recoveries": 3,
        "successful_conversational_recoveries": 2,
        "display_en_clicks": 2,
        "hint_clicks": 1,
        "suggestion_clicks": 1,
    }
    metrics = srv._compute_scorecard(sess)
    snap = srv._build_progress_snapshot(sess, metrics)
    assert snap["flow_display_label"] in (
        "Messy but sustained", "Worked through turbulence", "Stayed on track",
    )
    assert snap["flow_display_label"] != "Smooth"
    assert "Smooth" not in snap["flow_display_label"]
    assert snap["recovery_display_label"] in (
        "Self-recovered often", "Used support + self-recovered", "Self-recovered",
    )
    assert snap["support_display_label"] in ("Light", "Moderate")
    assert snap["support_display_label"] != "None"


def test_flow_label_never_smooth_with_unclear_turns():
    srv = _load_ui_server()
    snap = _make_snapshot(
        srv,
        {"total_turns": 28, "unmatched_responses": 3, "questions_asked": 5},
    )
    assert snap["flow_display_label"] != "Smooth"
    assert _format_flow_cell(snap) != "Smooth"


def test_support_tier_thresholds():
    srv = _load_ui_server()
    assert _format_learning_support({"hint_clicks": 1}) == "Light"
    assert _format_learning_support({"hint_clicks": 3, "display_en_clicks": 1}) == "Moderate"
    assert _format_learning_support({"hint_clicks": 4, "display_en_clicks": 3}) == "Heavy"


def test_end_session_includes_session_interpretation():
    src = (_SCRIPTS / "ui_server.py").read_text(encoding="utf-8")
    assert "session_interpretation" in src
    assert "flow_display_label" in src
    assert "support_display_label" in src


def test_beta_progress_api_endpoints_present():
    src = (_SCRIPTS / "ui_server.py").read_text(encoding="utf-8")
    assert "/api/save_progress" in src
    assert "/api/progress" in src
    assert "_ps_save_snapshot" in src
    assert "learner_id" in src


def test_beta_progress_client_wiring():
    src = _load_app_js()
    assert "manos_learner_id" in src
    assert "function setLearnerId" in src
    assert "initLearnerId" in src
    assert "/api/save_progress" in src
    assert "_persistProgressSnapshotToServer" in src
    assert "learner_id:" in src


def test_beta_profile_api_endpoints_present():
    src = (_SCRIPTS / "ui_server.py").read_text(encoding="utf-8")
    assert "/api/beta_profile" in src
    assert "_bp_load_profile" in src
    assert "_bp_save_profile" in src


def test_beta_profile_client_wiring():
    src = _load_app_js()
    assert "initBetaProfile" in src
    assert "saveBetaProfile" in src
    assert "/api/beta_profile" in src
    assert "startingPointBar" in (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert "starting-point-btn" in (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert "practiceLevelBtn" in src
    assert "_comfortMode" in src
    assert "_updateChallengeModeVisibility" in src


def test_snapshot_includes_flow_and_support_display_labels():
    srv = _load_ui_server()
    snap = _make_snapshot(srv)
    assert "flow_display_label" in snap
    assert "support_display_label" in snap
    assert snap["stability_display_label"] == snap["flow_display_label"]


def test_legacy_stability_display_without_score_prefix():
    srv = _load_ui_server()
    snap = _make_snapshot(srv, {"total_turns": 20, "unmatched_responses": 0})
    assert " · " not in snap["stability_display_label"]
    assert snap["flow_display_label"] == snap["stability_display_label"]
