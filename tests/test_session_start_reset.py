#!/usr/bin/env python3
"""Start-button session reset — UI/state only; no conversation behavior changes."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _app_src() -> str:
    return (ROOT / "ui" / "app.js").read_text(encoding="utf-8")


def test_start_button_resets_before_run_turn():
    src = _app_src()
    assert "runBtn.addEventListener" in src
    assert "_resetCurrentSessionState();" in src
    idx = src.index("runBtn.addEventListener")
    block = src[idx : idx + 200]
    assert block.index("_resetCurrentSessionState") < block.index("runTurn(false)")


def test_reset_clears_transcript_and_scorecard():
    src = _app_src()
    assert "function _resetCurrentSessionState" in src
    assert "conversationTranscript = []" in src
    assert "renderTranscript();" in src
    assert "renderSessionObjective();" in src
    assert 'getElementById("scorecardOverlay")' in src


def test_reset_clears_session_counters():
    src = _app_src()
    reset_block = src.split("function _resetCurrentSessionState")[1].split("async function startFreshLearner")[0]
    for field in (
        "_tracker.total_turns = 0",
        "_tracker.display_en_clicks = 0",
        "_tracker.card_opens = 0",
        "_tracker.conversational_recoveries = 0",
        "_pendingNaturalRecovery = false",
        "_pendingRepairPrompt = false",
        "_consecutiveNotUnderstood = 0",
    ):
        assert field in reset_block


def test_reset_does_not_clear_progress_history():
    src = _app_src()
    reset_block = src.split("function _resetCurrentSessionState")[1].split("async function startFreshLearner")[0]
    assert "_PROGRESS_HISTORY_KEY" not in reset_block
    assert "localStorage.removeItem" not in reset_block
    assert "manos_progress_history" not in reset_block


def test_reset_preserves_persona_and_frame_selection():
    src = _app_src()
    reset_block = src.split("function _resetCurrentSessionState")[1].split("async function startFreshLearner")[0]
    assert "frameSelect" not in reset_block
    assert "_partnerId" not in reset_block
    assert "_personaId" not in reset_block
    assert "_learnerId" not in reset_block


def test_clear_memory_still_changes_learner_id():
    src = _app_src()
    fresh_block = src.split("async function startFreshLearner")[1].split("async function runTurn")[0]
    assert 'window._learnerId = "learner_"' in fresh_block
    assert "_resetCurrentSessionState();" in fresh_block


def test_start_fresh_uses_shared_reset():
    src = _app_src()
    assert "startFreshLearner" in src
    assert src.count("_resetCurrentSessionState();") >= 2
