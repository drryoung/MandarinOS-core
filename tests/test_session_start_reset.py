#!/usr/bin/env python3
"""Start-button session reset — UI/state only; no conversation behavior changes.

Updated: clear-memory no longer rotates learner_id or wipes progress history.
"""

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


# ── P1: "Forget current conversation facts" safety guarantees ─────────────────

def test_clear_memory_preserves_learner_id():
    """startFreshLearner must NOT rotate learner_id to a new timestamp-based value."""
    src = _app_src()
    fresh_block = src.split("async function startFreshLearner")[1].split("async function runTurn")[0]
    # Must NOT call setLearnerId with a generated timestamp id
    assert 'setLearnerId("learner_" + Date.now())' not in fresh_block
    assert 'setLearnerId("learner_"' not in fresh_block


def test_clear_memory_does_not_remove_progress_history():
    """startFreshLearner must NOT call removeItem on manos_progress_history."""
    src = _app_src()
    fresh_block = src.split("async function startFreshLearner")[1].split("async function runTurn")[0]
    # Must not call removeItem at all — progress snapshots are never deleted.
    assert "removeItem" not in fresh_block
    # _PROGRESS_HISTORY_KEY must not appear as a call target.
    assert "_PROGRESS_HISTORY_KEY" not in fresh_block


def test_clear_memory_does_not_call_first_time_hygiene():
    """startFreshLearner must NOT invoke _applyFirstTimeBetaHygiene() (which wipes progress cache)."""
    src = _app_src()
    fresh_block = src.split("async function startFreshLearner")[1].split("async function runTurn")[0]
    # The call form must not appear; the function name may appear in comments/log strings — that is fine.
    assert "_applyFirstTimeBetaHygiene();" not in fresh_block


def test_clear_memory_posts_to_reset_memory_with_current_id():
    """startFreshLearner must POST /api/reset_memory using the current (unchanged) learner_id."""
    src = _app_src()
    fresh_block = src.split("async function startFreshLearner")[1].split("async function runTurn")[0]
    assert '"/api/reset_memory"' in fresh_block
    # The id sent must be currentId (not oldId — there is no id rotation any more)
    assert "currentId" in fresh_block
    assert "oldId" not in fresh_block


def test_clear_memory_calls_reset_session_state():
    """startFreshLearner must still call _resetCurrentSessionState for in-flight session."""
    src = _app_src()
    fresh_block = src.split("async function startFreshLearner")[1].split("async function runTurn")[0]
    assert "_resetCurrentSessionState();" in fresh_block


def test_clear_memory_logs_preservation():
    """startFreshLearner must emit a console.info confirming progress is untouched."""
    src = _app_src()
    fresh_block = src.split("async function startFreshLearner")[1].split("async function runTurn")[0]
    assert "console.info" in fresh_block
    assert "manos_progress_history NOT touched" in fresh_block


def test_button_label_is_forget_conversation():
    """UI button label must be the updated safer wording."""
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert "Forget current conversation facts" in html
    assert "Clears remembered facts from this conversation only" in html
    # The old alarming tooltip must be gone
    assert "start as a new learner" not in html


def test_start_fresh_uses_shared_reset():
    src = _app_src()
    assert "startFreshLearner" in src
    assert src.count("_resetCurrentSessionState();") >= 2
