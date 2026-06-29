"""
tests/test_closing_move_suppression.py

Regression tests for: closing moves suppressed when learner asks a
reciprocal / direct question.

Evidence:
  batch_2026-06-29_01 showed "这样啊", "这样挺好", "真不错啊" appearing
  instead of a direct persona answer after learner turns like:
    - 你呢？
    - 你做什么工作？
    - 你在哪里住？
    - 你最喜欢哪个地方？

Fixes applied (scripts/ui_server.py):
  1. _cm_original: added `and not user_asked_question`
  2. Closing fire condition: added `and not user_asked_question and not _counter_reply`
  3. Reaction micro-layer: wrapped gate with `and not user_asked_question`
  4. Suppressed-reason trace: added `user_asked_question` branch

These tests are static source-analysis checks — they verify the guard
conditions are present in the server code without running a full server.
"""
import pathlib
import pytest

REPO = pathlib.Path(__file__).parent.parent
UI_SERVER_PATH = REPO / "scripts" / "ui_server.py"


@pytest.fixture(scope="module")
def src():
    return UI_SERVER_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. _cm_original guard
# ---------------------------------------------------------------------------

def test_cm_original_has_user_asked_question_guard(src):
    """_cm_original must include 'not user_asked_question' so it cannot fire
    when the learner has asked a direct question."""
    # The assignment block must contain the guard
    # Search for the _cm_original = ( ... ) block
    idx = src.find("_cm_original = (")
    assert idx != -1, "_cm_original assignment not found"
    # Read the next ~300 chars to capture the full condition
    block = src[idx: idx + 300]
    assert "not user_asked_question" in block, (
        "_cm_original must contain 'not user_asked_question' guard"
    )


def test_cm_original_guard_appears_inside_assignment(src):
    """Guard must be inside the _cm_original parentheses, not after it."""
    idx = src.find("_cm_original = (")
    block_start = idx
    # Find closing paren
    depth = 0
    close_idx = None
    for i, ch in enumerate(src[idx:]):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                close_idx = idx + i
                break
    assert close_idx is not None
    inner = src[block_start:close_idx]
    assert "not user_asked_question" in inner, (
        "Guard must be inside _cm_original = (...), not outside"
    )


# ---------------------------------------------------------------------------
# 2. Closing fire condition belt-and-suspenders
# ---------------------------------------------------------------------------

def test_closing_fire_condition_guards_user_asked_question(src):
    """The closing-move fire `if` must include `not user_asked_question`."""
    # Find the fire line
    fire_idx = src.find("if (_cm_original or _cm_extended or _cm_preemptible)")
    assert fire_idx != -1, "Closing fire condition line not found"
    fire_line_end = src.find("\n", fire_idx)
    fire_line = src[fire_idx:fire_line_end]
    assert "not user_asked_question" in fire_line, (
        "Closing fire condition must include 'not user_asked_question'"
    )


def test_closing_fire_condition_guards_counter_reply(src):
    """The closing-move fire `if` must include `not _counter_reply` so that
    an already-built persona answer is not discarded."""
    fire_idx = src.find("if (_cm_original or _cm_extended or _cm_preemptible)")
    assert fire_idx != -1
    fire_line_end = src.find("\n", fire_idx)
    fire_line = src[fire_idx:fire_line_end]
    assert "not _counter_reply" in fire_line, (
        "Closing fire condition must include 'not _counter_reply'"
    )


# ---------------------------------------------------------------------------
# 3. Reaction micro-layer guard
# ---------------------------------------------------------------------------

def test_reaction_micro_layer_skipped_when_user_asked_question(src):
    """Spec §3 reaction gate must include `not user_asked_question` so that
    挺好/真不错 prefixes are suppressed when learner asked a question."""
    # Find the Spec §3 comment followed by the gate
    spec3_idx = src.find("Spec §3: after ANY user answer")
    assert spec3_idx != -1, "Spec §3 reaction comment not found"
    # The gate line should be within the next ~300 chars
    block = src[spec3_idx: spec3_idx + 400]
    assert "not user_asked_question" in block, (
        "Reaction micro-layer gate must include 'not user_asked_question'"
    )
    # Specifically the `if last_turn_was_answer` must include the guard
    gate_match = "if last_turn_was_answer and not user_asked_question"
    assert gate_match in block, (
        f"Expected '{gate_match}' in reaction gate; got: {block[:200]!r}"
    )


# ---------------------------------------------------------------------------
# 4. Suppressed-reason trace
# ---------------------------------------------------------------------------

def test_closing_suppressed_reason_has_user_asked_question_branch(src):
    """Suppressed-reason trace must emit 'user_asked_question' when that is
    the reason closing was blocked — for auditability."""
    assert '"user_asked_question"' in src or "'user_asked_question'" in src, (
        "Suppressed-reason trace must have user_asked_question branch"
    )
    # Also check it's in the right place — before or adjacent to _closing_suppressed_reason
    idx = src.find("_closing_suppressed_reason = \"user_asked_question\"")
    if idx == -1:
        idx = src.find("_closing_suppressed_reason = 'user_asked_question'")
    assert idx != -1, "_closing_suppressed_reason = 'user_asked_question' assignment not found"


def test_closing_suppressed_reason_user_branch_is_first(src):
    """user_asked_question should be the earliest check in the suppressed-reason
    trace block, so it short-circuits correctly."""
    trace_idx = src.find("Suppressed-reason trace — always populated")
    assert trace_idx != -1
    block = src[trace_idx: trace_idx + 600]
    uaq_pos = block.find("user_asked_question")
    not_late_pos = block.find("not_late_session")
    assert uaq_pos != -1, "user_asked_question not found in trace block"
    assert not_late_pos != -1, "not_late_session not found in trace block"
    assert uaq_pos < not_late_pos, (
        "user_asked_question check must appear before not_late_session check in trace"
    )


# ---------------------------------------------------------------------------
# 5. Ordering invariant: _cm_extended and _cm_preemptible still have their
#    existing user_asked_question guards (no regression)
# ---------------------------------------------------------------------------

def test_cm_extended_still_has_user_asked_question_guard(src):
    """_cm_extended must still include `(not user_asked_question)` — unchanged."""
    idx = src.find("_cm_extended = (")
    assert idx != -1
    block = src[idx: idx + 400]
    assert "not user_asked_question" in block or "(not user_asked_question)" in block, (
        "_cm_extended must retain its user_asked_question guard"
    )


def test_cm_preemptible_uses_cm_real_answer_which_requires_non_question(src):
    """_cm_preemptible uses _cm_real_answer which already requires not user_asked_question."""
    # _cm_real_answer = last_turn_was_answer and (not user_asked_question) and ...
    idx = src.find("_cm_real_answer =")
    assert idx != -1
    line_end = src.find("\n", idx)
    line = src[idx:line_end]
    assert "not user_asked_question" in line, (
        "_cm_real_answer must include 'not user_asked_question'"
    )


# ---------------------------------------------------------------------------
# 6. Closing phrase pool not empty (smoke test — phrases still exist)
# ---------------------------------------------------------------------------

def test_closing_reactions_pool_present(src):
    """_CLOSING_REACTIONS must still be defined after the fix."""
    assert "_CLOSING_REACTIONS" in src
    assert "这样啊" in src


def test_closing_reactions_food_pool_present(src):
    """_CLOSING_REACTIONS_FOOD must still be defined."""
    assert "_CLOSING_REACTIONS_FOOD" in src


def test_closing_reactions_emotional_pool_present(src):
    """_CLOSING_REACTIONS_EMOTIONAL must still be defined."""
    assert "_CLOSING_REACTIONS_EMOTIONAL" in src


# ---------------------------------------------------------------------------
# 7. Sanity: _is_user_question still handles key reciprocal patterns
# ---------------------------------------------------------------------------

def test_is_user_question_recognises_ni_ne(src):
    """_is_user_question must match 你呢 (turn-around marker)."""
    idx = src.find("def _is_user_question")
    assert idx != -1
    # Read next 3000 chars to capture the body
    body = src[idx: idx + 3000]
    assert "你呢" in body, "_is_user_question must check for 你呢 turn-around"


def test_is_user_question_recognises_question_mark(src):
    """_is_user_question must check for ？ marker."""
    idx = src.find("def _is_user_question")
    assert idx != -1
    body = src[idx: idx + 3000]
    assert "？" in body, "_is_user_question must check for ？"


def test_is_user_question_recognises_direct_starts(src):
    """_is_user_question must use _direct_starts for 你做什么工作 style turns."""
    idx = src.find("def _is_user_question")
    assert idx != -1
    body = src[idx: idx + 3000]
    assert "_direct_starts" in body, "_is_user_question must use _direct_starts"
