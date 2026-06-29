"""
tests/test_turbulence_signal.py

Regression tests for the informational turbulence signal (Phase 0.x).

Goals verified:
  1. _tracker.turbulence_events exists in app.js _tracker definition.
  2. turbulence_events is sent in endSession() payload.
  3. Hard ASR reject increments turbulence_events + logs turbulence_moment.
  4. Soft ASR reject increments turbulence_events + logs turbulence_moment.
  5. Strong confusion signal (不明白 path) increments turbulence_events.
  6. Repair escalation (repair_attempt_count >= 2) increments turbulence_events.
  7. _challengeRevealText() increments turbulence_events.
  8. Server _compute_scorecard() returns metrics.turbulence dict.
  9. turbulence in metrics is informational only — stability/capability untouched.
 10. session_intelligence.build_session_record() includes turbulence_events in counters.
 11. turbulence_events missing from sess does not crash _compute_scorecard().
 12. turbulence_events=0 when sess has no turbulence.
 13. Server TURBULENCE log line is emitted in end_session handler.
 14. turbulence metrics are not wired to _conversation_stability_score inputs.
"""
import json
import pathlib
import sys
import pytest

REPO = pathlib.Path(__file__).parent.parent
UI_SERVER_PATH = REPO / "scripts" / "ui_server.py"
APP_JS_PATH = REPO / "ui" / "app.js"
SESSION_INTELLIGENCE_PATH = REPO / "scripts" / "session_intelligence.py"

# ── helpers ───────────────────────────────────────────────────────────────────

def _app_js() -> str:
    return APP_JS_PATH.read_text(encoding="utf-8")

def _ui_server() -> str:
    return UI_SERVER_PATH.read_text(encoding="utf-8")

def _si_py() -> str:
    return SESSION_INTELLIGENCE_PATH.read_text(encoding="utf-8")


# ── 1. _tracker definition contains turbulence_events ─────────────────────────

def test_tracker_has_turbulence_events_field():
    src = _app_js()
    # Find _tracker definition block
    idx = src.find("const _tracker = {")
    assert idx != -1, "_tracker definition not found"
    block = src[idx: idx + 1700]
    assert "turbulence_events" in block, (
        "turbulence_events field missing from _tracker definition"
    )


def test_tracker_turbulence_events_initialised_to_zero():
    src = _app_js()
    idx = src.find("const _tracker = {")
    assert idx != -1
    block = src[idx: idx + 1700]
    # Accept: turbulence_events: 0,
    assert "turbulence_events: 0" in block, (
        "turbulence_events should be initialised to 0 in _tracker"
    )


# ── 2. endSession() payload includes turbulence_events ────────────────────────

def test_end_session_payload_includes_turbulence_events():
    src = _app_js()
    idx = src.find("async function endSession()")
    assert idx != -1, "endSession not found"
    block = src[idx: idx + 2500]
    assert "turbulence_events" in block, (
        "endSession() payload must include turbulence_events"
    )


def test_end_session_turbulence_events_uses_tracker():
    src = _app_js()
    idx = src.find("async function endSession()")
    assert idx != -1
    block = src[idx: idx + 2500]
    # Should reference t.turbulence_events (t = _tracker)
    assert "t.turbulence_events" in block, (
        "endSession() should use t.turbulence_events from _tracker"
    )


# ── 3. Hard ASR reject → turbulence increment ─────────────────────────────────

def test_hard_asr_reject_increments_turbulence_events():
    src = _app_js()
    idx = src.find("_tracker.unmatched_responses++")
    assert idx != -1, "_tracker.unmatched_responses++ not found"
    block = src[idx: idx + 400]
    assert "_tracker.turbulence_events++" in block, (
        "Hard ASR reject block must increment turbulence_events"
    )


def test_hard_asr_reject_logs_turbulence_moment():
    src = _app_js()
    idx = src.find("_tracker.unmatched_responses++")
    assert idx != -1
    block = src[idx: idx + 400]
    assert '"turbulence_moment"' in block or "'turbulence_moment'" in block, (
        "Hard ASR reject must log a turbulence_moment event"
    )
    assert "asr_hard_reject" in block, (
        "Hard ASR reject turbulence log should use kind: asr_hard_reject"
    )


# ── 4. Soft ASR reject → turbulence increment ─────────────────────────────────

def test_soft_asr_reject_increments_turbulence_events():
    src = _app_js()
    idx = src.find("_tracker.soft_unmatched_responses++")
    assert idx != -1, "_tracker.soft_unmatched_responses++ not found"
    block = src[idx: idx + 400]
    assert "_tracker.turbulence_events++" in block, (
        "Soft ASR reject block must increment turbulence_events"
    )


def test_soft_asr_reject_logs_turbulence_moment():
    src = _app_js()
    idx = src.find("_tracker.soft_unmatched_responses++")
    assert idx != -1
    block = src[idx: idx + 400]
    assert "asr_soft_reject" in block, (
        "Soft ASR reject turbulence log should use kind: asr_soft_reject"
    )


# ── 5. Strong confusion signal → turbulence increment ─────────────────────────

def test_strong_confusion_signal_increments_turbulence_events():
    src = _app_js()
    idx = src.find("_isStrongConfusionText(saidTrimmed)")
    assert idx != -1, "_isStrongConfusionText branch not found"
    block = src[idx: idx + 600]
    assert "_tracker.turbulence_events++" in block, (
        "Strong confusion (_isStrongConfusionText) must increment turbulence_events"
    )


def test_strong_confusion_signal_logs_kind():
    src = _app_js()
    idx = src.find("_isStrongConfusionText(saidTrimmed)")
    assert idx != -1
    block = src[idx: idx + 600]
    assert "confusion_signal" in block, (
        "Strong confusion turbulence log should use kind: confusion_signal"
    )


# ── 6. Repair escalation → turbulence increment ───────────────────────────────

def test_repair_escalation_increments_turbulence_events():
    src = _app_js()
    idx = src.find("repair_attempt_count !== undefined")
    assert idx != -1, "repair_attempt_count state_update merge not found"
    block = src[idx: idx + 500]
    assert "_tracker.turbulence_events++" in block, (
        "Repair escalation (repair_attempt_count >= 2) must increment turbulence_events"
    )


def test_repair_escalation_checks_threshold():
    src = _app_js()
    idx = src.find("repair_attempt_count !== undefined")
    assert idx != -1
    block = src[idx: idx + 500]
    assert "repair_attempt_count >= 2" in block or ">= 2" in block, (
        "Repair escalation turbulence should only fire at count >= 2"
    )


def test_repair_escalation_logs_repair_loop():
    src = _app_js()
    idx = src.find("repair_attempt_count !== undefined")
    assert idx != -1
    block = src[idx: idx + 500]
    assert "repair_loop" in block, (
        "Repair escalation turbulence log should use kind: repair_loop"
    )


# ── 7. _challengeRevealText → turbulence increment ────────────────────────────

def test_challenge_reveal_text_increments_turbulence_events():
    src = _app_js()
    idx = src.find("function _challengeRevealText()")
    assert idx != -1, "_challengeRevealText not found"
    block = src[idx: idx + 700]
    assert "_tracker.turbulence_events++" in block, (
        "_challengeRevealText() must increment turbulence_events"
    )


def test_challenge_reveal_text_logs_kind():
    src = _app_js()
    idx = src.find("function _challengeRevealText()")
    assert idx != -1
    block = src[idx: idx + 700]
    assert "challenge_text_revealed" in block, (
        "_challengeRevealText turbulence log should use kind: challenge_text_revealed"
    )


def test_challenge_reveal_text_turbulence_after_guard():
    """turbulence increment must be after the early-return guard to avoid double-count."""
    src = _app_js()
    idx = src.find("function _challengeRevealText()")
    assert idx != -1
    block = src[idx: idx + 700]
    guard_idx = block.find("helpLevel >= 3")
    turb_idx  = block.find("turbulence_events++")
    assert guard_idx != -1, "Early-return guard missing"
    assert turb_idx  != -1, "turbulence_events++ missing"
    assert turb_idx > guard_idx, (
        "turbulence_events++ must come AFTER the helpLevel >= 3 early-return guard"
    )


# ── 8. Server _compute_scorecard() returns metrics.turbulence ─────────────────

def test_compute_scorecard_returns_turbulence_key():
    src = _ui_server()
    idx = src.find("def _compute_scorecard(sess:")
    assert idx != -1, "_compute_scorecard not found"
    block = src[idx: idx + 2500]
    assert '"turbulence"' in block, (
        "_compute_scorecard must return a 'turbulence' key in metrics"
    )


def test_compute_scorecard_turbulence_has_raw_events():
    src = _ui_server()
    idx = src.find("def _compute_scorecard(sess:")
    assert idx != -1
    block = src[idx: idx + 2500]
    assert "raw_events" in block, (
        "_compute_scorecard turbulence dict must include raw_events"
    )


def test_compute_scorecard_turbulence_reads_turbulence_events():
    src = _ui_server()
    idx = src.find("def _compute_scorecard(sess:")
    assert idx != -1
    block = src[idx: idx + 2500]
    assert 'sess.get("turbulence_events"' in block, (
        "_compute_scorecard must read turbulence_events from sess"
    )


# ── 9. turbulence NOT wired to stability/capability ───────────────────────────

def test_turbulence_events_not_passed_to_scorecard_stability():
    src = _ui_server()
    idx = src.find("def _compute_scorecard(sess:")
    assert idx != -1
    block = src[idx: idx + 2500]
    # _scorecard_stability(...) must not reference turbulence_events directly
    stability_call_idx = block.find("_scorecard_stability(")
    assert stability_call_idx != -1, "_scorecard_stability call not found in scorecard"
    stability_call = block[stability_call_idx: stability_call_idx + 120]
    assert "turbulence" not in stability_call, (
        "turbulence_events must NOT be passed into _scorecard_stability()"
    )


def test_turbulence_events_not_passed_to_scorecard_capability():
    src = _ui_server()
    idx = src.find("def _compute_scorecard(sess:")
    assert idx != -1
    block = src[idx: idx + 2500]
    cap_call_idx = block.find("_scorecard_conversation_capability(")
    assert cap_call_idx != -1, "_scorecard_conversation_capability call not found"
    cap_call = block[cap_call_idx: cap_call_idx + 80]
    # Capability function only receives sess — turbulence_events is in sess but
    # the function must not incorporate it in signals.  We just verify that the
    # turbulence metric block appears AFTER (not inside) the capability call.
    turb_key_idx = block.find('"turbulence"')
    assert turb_key_idx > cap_call_idx, (
        "turbulence metric block should appear after the conversation_capability call"
    )


def test_turbulence_label_is_informational():
    src = _ui_server()
    idx = src.find('"turbulence"')
    assert idx != -1, "'turbulence' key not found in ui_server.py"
    block = src[idx: idx + 300]
    assert "informational" in block, (
        "turbulence metrics label should be 'informational'"
    )


# ── 10. session_intelligence includes turbulence_events in counters ───────────

def test_session_record_counters_includes_turbulence_events():
    src = _si_py()
    idx = src.find("def build_session_record(")
    assert idx != -1, "build_session_record not found"
    block = src[idx: idx + 4000]
    assert '"turbulence_events"' in block, (
        "build_session_record must include turbulence_events in counters"
    )


def test_session_record_turbulence_events_uses_sess_get():
    src = _si_py()
    idx = src.find("def build_session_record(")
    assert idx != -1
    block = src[idx: idx + 4000]
    assert 'sess.get("turbulence_events"' in block, (
        "build_session_record must read turbulence_events from sess"
    )


# ── 11–12. _compute_scorecard is robust to missing/zero turbulence ─────────────

def test_compute_scorecard_no_crash_when_turbulence_events_absent():
    """_compute_scorecard must not crash when turbulence_events is missing."""
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        import ui_server as srv
        sess = {
            "total_turns": 5, "recovery_uses": 0, "successful_recoveries": 0,
            "conversational_recoveries": 0, "successful_conversational_recoveries": 0,
            "suggestion_clicks": 0, "card_opens": 0, "questions_asked": 1,
            "depth_responses": 1, "unmatched_responses": 0, "soft_unmatched_responses": 0,
            # turbulence_events intentionally absent
        }
        metrics = srv._compute_scorecard(sess)
        assert "turbulence" in metrics
        assert metrics["turbulence"]["raw_events"] == 0
    finally:
        sys.path.pop(0)


def test_compute_scorecard_turbulence_zero_when_no_events():
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        import ui_server as srv
        sess = {
            "total_turns": 10, "recovery_uses": 0, "successful_recoveries": 0,
            "conversational_recoveries": 0, "successful_conversational_recoveries": 0,
            "suggestion_clicks": 0, "card_opens": 0, "questions_asked": 2,
            "depth_responses": 2, "unmatched_responses": 0, "soft_unmatched_responses": 0,
            "turbulence_events": 0,
        }
        metrics = srv._compute_scorecard(sess)
        assert metrics["turbulence"]["raw_events"] == 0
        assert metrics["turbulence"]["per_turn"] == 0.0
    finally:
        sys.path.pop(0)


def test_compute_scorecard_turbulence_counts_correctly():
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        import ui_server as srv
        sess = {
            "total_turns": 10, "recovery_uses": 2, "successful_recoveries": 1,
            "conversational_recoveries": 0, "successful_conversational_recoveries": 0,
            "suggestion_clicks": 0, "card_opens": 0, "questions_asked": 1,
            "depth_responses": 1, "unmatched_responses": 1, "soft_unmatched_responses": 1,
            "turbulence_events": 4,
        }
        metrics = srv._compute_scorecard(sess)
        assert metrics["turbulence"]["raw_events"] == 4
        assert metrics["turbulence"]["per_turn"] == pytest.approx(0.4, abs=0.001)
    finally:
        sys.path.pop(0)


# ── 13. Server TURBULENCE log line present in end_session handler ─────────────

def test_end_session_handler_has_turbulence_log():
    src = _ui_server()
    assert "[TURBULENCE]" in src, (
        "end_session handler must emit a [TURBULENCE] log line"
    )


def test_end_session_turbulence_log_includes_events_and_per_turn():
    src = _ui_server()
    idx = src.find("[TURBULENCE]")
    assert idx != -1
    block = src[idx: idx + 300]
    assert "events=" in block, "TURBULENCE log should include events="
    assert "per_turn=" in block, "TURBULENCE log should include per_turn="


# ── 14. stability score computation does not reference turbulence_events ───────

def test_conversation_stability_score_does_not_use_turbulence_events():
    src = _ui_server()
    idx = src.find("def _conversation_stability_score(")
    assert idx != -1, "_conversation_stability_score not found"
    block = src[idx: idx + 2000]
    assert "turbulence_events" not in block, (
        "_conversation_stability_score must NOT reference turbulence_events "
        "(turbulence is informational only)"
    )


def test_capability_estimator_does_not_import_turbulence_events():
    estimator = REPO / "scripts" / "capability_estimator.py"
    if not estimator.exists():
        pytest.skip("capability_estimator.py not present")
    src = estimator.read_text(encoding="utf-8")
    assert "turbulence_events" not in src, (
        "capability_estimator.py must NOT reference turbulence_events "
        "(signal is informational only)"
    )
