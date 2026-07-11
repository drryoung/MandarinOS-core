#!/usr/bin/env python3
"""Static regression checks for the ASR thinking-grace period (segment joining)."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
_APP = ROOT / "ui" / "app.js"


def _src():
    return _APP.read_text(encoding="utf-8")


# ── Helper: extract named blocks ────────────────────────────────────────────

def _listen_block():
    """Source of listenForResponse up to (not including) the first function after it."""
    s = _src()
    return s.split("function listenForResponse")[1].split("}\n\n// Segments for")[0]


def _onend_block():
    s = _src()
    # rec.onend = () => { ... };
    return s.split("rec.onend = () => {")[1].split("rec.onstart = () => {")[0]


def _finish_block():
    s = _src()
    return s.split("function finish(reason) {")[1].split("function _startThinkingGrace")[0]


def _grace_block():
    s = _src()
    return s.split("function _startThinkingGrace")[1].split("function absorbResults")[0]


def _absorb_block():
    s = _src()
    return s.split("function absorbResults(e, {")[1].split("function resetSilenceTimer")[0]


# ── 1. First segment does not immediately submit ─────────────────────────────

def test_onend_with_text_does_not_call_finish_immediately():
    """On desktop, onend with text enters thinking grace, not finish()."""
    block = _onend_block()
    # The block must branch on isMobileListen before calling finish
    assert "_startThinkingGrace" in block
    # finish("onend") on the text-present branch should be inside the mobile/cap else
    lines = block.split("\n")
    grace_line = next(i for i, l in enumerate(lines) if "_startThinkingGrace" in l)
    finish_onend_line = next(
        (i for i, l in enumerate(lines) if 'finish("onend")' in l and i > grace_line - 5),
        None,
    )
    # finish("onend") must not appear BEFORE the isMobileListen branch
    assert grace_line < (finish_onend_line or len(lines))


def test_thinking_grace_constant_exists():
    s = _src()
    assert "const ASR_THINKING_GRACE_MS = " in s


def test_segment_cap_constant_exists():
    s = _src()
    assert "const ASR_MAX_SEGMENTS = " in s


def test_thinking_grace_ms_reasonable():
    s = _src()
    m = re.search(r"const ASR_THINKING_GRACE_MS\s*=\s*(\d+)", s)
    assert m, "ASR_THINKING_GRACE_MS not found"
    val = int(m.group(1))
    assert 1000 <= val <= 3000, f"ASR_THINKING_GRACE_MS={val} outside 1–3 s range"


def test_segment_cap_reasonable():
    s = _src()
    m = re.search(r"const ASR_MAX_SEGMENTS\s*=\s*(\d+)", s)
    assert m, "ASR_MAX_SEGMENTS not found"
    val = int(m.group(1))
    assert 2 <= val <= 6, f"ASR_MAX_SEGMENTS={val} outside 2–6 range"


# ── 2. Second segment appended, not replacing ────────────────────────────────

def test_join_segments_helper_exists():
    s = _src()
    assert "function _joinSegments" in s


def test_join_segments_called_for_grace_continuation():
    block = _absorb_block()
    assert "_joinSegments(finalTranscript, latestFinal)" in block
    assert "isGraceContinuation" in block


def test_join_strips_overlap_prefix():
    """_joinSegments must attempt to remove repeated chars at the join boundary."""
    s = _src()
    join_block = s.split("function _joinSegments")[1].split("// ── finish(reason)")[0]
    assert "endsWith" in join_block or "slice" in join_block


# ── 3 & 4. One transcript entry, one runTurn call ────────────────────────────

def test_no_add_transcript_entry_inside_listen_for_response():
    block = _listen_block()
    assert "addTranscriptEntry" not in block


def test_no_run_turn_inside_listen_for_response():
    block = _listen_block()
    # Comments mentioning runTurn are OK; actual calls are not.
    assert "runTurn(" not in block


# ── 5. Grace expiry finalizes ────────────────────────────────────────────────

def test_thinking_grace_timer_calls_finish_on_expiry():
    block = _grace_block()
    assert "thinking_grace_expired" in block
    assert "finish(" in block.split("thinking_grace_expired")[0].split("thinkingGraceTid = setTimeout")[1]


# ── 6. Explicit stop finalizes promptly ─────────────────────────────────────

def test_finish_clears_thinking_grace_timer():
    block = _finish_block()
    assert "thinkingGraceTid" in block
    assert "clearTimeout(thinkingGraceTid)" in block


def test_finish_sets_inThinkingGrace_false():
    block = _finish_block()
    assert "inThinkingGrace = false" in block


# ── 7. Empty restart does not erase recognised text and does not finalize early ─

def test_grace_empty_onend_does_not_finalize_before_deadline():
    """Empty grace recognizer ending before the deadline must NOT call finish()."""
    block = _grace_block()
    # The empty-onend handler must check remaining time before deciding to finalize.
    assert "remaining" in block
    assert "thinkingGraceDeadline" in block
    # It must NOT call finish("grace_onend_empty") or any other finish immediately.
    assert "grace_onend_empty" not in block


def test_grace_empty_onend_restarts_if_time_remains():
    """When empty onend fires with time left, recognition is restarted."""
    block = _grace_block()
    onend_section = block.split("nextRec.onend")[1]
    # Must call _startThinkingGrace or equivalent restart when remaining > 0.
    assert "_startThinkingGrace" in onend_section
    assert "remaining" in onend_section


def test_grace_deadline_is_absolute_set_once():
    """thinkingGraceDeadline is set once on first entry and not pushed forward by empty restarts."""
    block = _grace_block()
    # Deadline is only set inside the !thinkingGraceDeadline guard.
    assert "if (!thinkingGraceDeadline)" in block
    # The empty-onend sub-path (no new text) must not reassign thinkingGraceDeadline.
    # Split on the empty-text branch: "if (remaining > 50" is in the empty path.
    onend_section = block.split("nextRec.onend")[1]
    empty_branch = onend_section.split("if (remaining > 50")[1] if "if (remaining > 50" in onend_section else ""
    assert "thinkingGraceDeadline =" not in empty_branch, (
        "Empty-onend path must not reset thinkingGraceDeadline"
    )


def test_grace_restart_cap_enforced():
    """graceRestartCount is tracked and GRACE_MAX_RESTARTS caps empty-restart loops."""
    s = _src()
    assert "GRACE_MAX_RESTARTS" in s
    assert "graceRestartCount" in s
    block = _grace_block()
    assert "GRACE_MAX_RESTARTS" in block
    assert "graceRestartCount <" in block or "graceRestartCount++" in block


# ── 8. Segment joining does not duplicate overlapping words ──────────────────

def test_join_segments_overlap_logic_present():
    s = _src()
    join_fn = s.split("function _joinSegments")[1].split("// ── finish(reason)")[0]
    assert "maxOverlap" in join_fn or "endsWith" in join_fn


# ── 9. Restart count and duration bounded ────────────────────────────────────

def test_segment_count_checked_before_grace_restart():
    block = _onend_block()
    assert "ASR_MAX_SEGMENTS" in block
    assert "segmentCount < ASR_MAX_SEGMENTS" in block


def test_wall_clock_covers_joined_segments():
    """SPEECH_ACTIVE_MAX_MS must be large enough to accommodate joined segments."""
    s = _src()
    m = re.search(r"const SPEECH_ACTIVE_MAX_MS\s*=\s*(\d+)", s)
    assert m, "SPEECH_ACTIVE_MAX_MS not found"
    val = int(m.group(1))
    assert val >= 15000, f"SPEECH_ACTIVE_MAX_MS={val} too short for multi-segment turns"


# ── 10. iPhone behaviour preserved ──────────────────────────────────────────

def test_mobile_path_skips_thinking_grace():
    block = _onend_block()
    # Thinking grace must be conditional on NOT isMobileListen
    grace_line = next(i for i, l in enumerate(block.split("\n")) if "_startThinkingGrace" in l)
    mobile_check_lines = [
        i for i, l in enumerate(block.split("\n"))
        if "isMobileListen" in l and i < grace_line
    ]
    assert mobile_check_lines, "isMobileListen check must guard _startThinkingGrace"


def test_mobile_listen_variable_still_present():
    s = _src()
    assert "const isMobileListen = _isMobileLayout()" in s


def test_rec_continuous_false_still_set():
    s = _src()
    assert "rec.continuous = false" in s
    assert "rec.continuous = !isMobileListen" not in s


# ── Misc structural checks ───────────────────────────────────────────────────

def test_active_rec_variable_exists_and_used_in_finish():
    s = _src()
    assert "let activeRec = rec" in s
    block = _finish_block()
    assert "activeRec.stop()" in block or "activeRec" in block


def test_segment_count_incremented_in_join():
    block = _absorb_block()
    assert "segmentCount++" in block


def test_inThinkingGrace_guards_duplicate_grace_start():
    block = _grace_block()
    assert "if (inThinkingGrace) return" in block
