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
    """40 turns, 2 hard unclear → 5% effective rate → stability score 95."""
    srv = _load_ui_server()
    sess = {
        "total_turns": 40,
        "unmatched_responses": 2,
        "soft_unmatched_responses": 0,
    }
    metrics = srv._compute_scorecard(sess)
    assert metrics["stability"]["rate"] == 0.05
    score_base = srv._conversation_stability_score(metrics["stability"], 40)
    assert score_base == 95
    snap = srv._build_progress_snapshot(sess, metrics)
    assert snap["conversation_stability_score"] >= 95
    assert snap["unclear_turns"] == 2


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
    """Mirror of ui/app.js _formatSupportUsed — keep in sync."""
    parts = []
    options = snap.get("suggestion_clicks") or 0
    cards = snap.get("card_opens") or 0
    hints = snap.get("hint_clicks") or 0
    en = snap.get("display_en_clicks") or 0
    py = snap.get("display_py_clicks") or 0
    if options > 0:
        parts.append(f"Options {options}")
    if cards > 0:
        parts.append(f"Cards {cards}")
    if hints > 0:
        parts.append(f"Hints {hints}")
    if en > 0:
        parts.append(f"EN {en}")
    if py > 0:
        parts.append(f"PY {py}")
    return " · ".join(parts) if parts else "None"


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
    assert _format_learning_support({"suggestion_clicks": 2, "card_opens": 1}) == "Options 2 · Cards 1"


def test_format_support_en_only():
    assert _format_learning_support({"display_en_clicks": 4}) == "EN 4"


def test_format_support_py_only():
    assert _format_learning_support({"display_py_clicks": 3}) == "PY 3"


def test_format_support_mixed():
    assert (
        _format_learning_support(
            {
                "hint_clicks": 2,
                "display_en_clicks": 5,
                "card_opens": 1,
            },
        )
        == "Cards 1 · Hints 2 · EN 5"
    )


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


def test_progress_ui_learning_support_column_and_tracking():
    src = _load_app_js()
    assert "Learning support" in src
    assert "display_en_clicks" in src
    assert "display_py_clicks" in src
    assert "hint_clicks:" in src
    assert "function toggleLinePinyin" in src
    assert "!st.showEn) _tracker.display_en_clicks" in src
    assert "!st.showPy) _tracker.display_py_clicks" in src
