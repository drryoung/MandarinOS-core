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

  session_1782851680027 turns 31, 33, 40, 56 and session_1782853497708
  turns 45, 47, 54 showed closing replies when conversation was broken:
    - learner sent recovery phrases (再说一遍, 什么意思)
    - learner sent frustration markers (太难了, 算了)
    - learner sent continuation requests (继续)
    - learner sent low-confidence ASR junk (single non-CJK char)
    - last partner turn was a generic fallback (这个我不太清楚)

Fixes applied (scripts/ui_server.py):
  1. _cm_original: added `and not user_asked_question`
  2. Closing fire condition: added `and not user_asked_question and not _counter_reply`
  3. Reaction micro-layer: wrapped gate with `and not user_asked_question`
  4. Suppressed-reason trace: added `user_asked_question` branch
  5. _is_closing_blocked_by_learner_signal(): new helper covering confusion/recovery,
     frustration, continuation requests, low ASR confidence, post-generic-fallback.
  6. Fire condition: added `and not _cm_blocked_signal`
  7. Suppressed-reason trace: added `_cm_blocked_reason` branch

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


# ---------------------------------------------------------------------------
# 8. _is_closing_blocked_by_learner_signal helper exists
# ---------------------------------------------------------------------------

def test_closing_blocked_helper_defined(src):
    """New helper function must be defined in the server."""
    assert "def _is_closing_blocked_by_learner_signal(" in src


def test_closing_blocked_helper_has_confusion_check(src):
    """Helper must delegate to _is_confusion_signal for recovery/meaning phrases."""
    idx = src.find("def _is_closing_blocked_by_learner_signal(")
    assert idx != -1
    body = src[idx: idx + 1200]
    assert "_is_confusion_signal" in body, "helper must call _is_confusion_signal"


def test_closing_blocked_helper_has_frustration_markers(src):
    """Helper must include frustration markers (太难了, 算了…)."""
    idx = src.find("def _is_closing_blocked_by_learner_signal(")
    assert idx != -1
    body = src[idx: idx + 1200]
    assert "frustration" in body, "helper must reference frustration reason"


def test_closing_blocked_helper_has_continuation_markers(src):
    """Helper must include continuation-request markers (继续, 然后呢…)."""
    assert "_CLOSING_BLOCK_CONTINUATION" in src
    assert "继续" in src


def test_closing_blocked_helper_has_low_asr_check(src):
    """Helper must include low-ASR-confidence detection."""
    idx = src.find("def _is_closing_blocked_by_learner_signal(")
    assert idx != -1
    body = src[idx: idx + 1200]
    assert "low_asr_confidence" in body, "helper must return low_asr_confidence reason"


def test_closing_blocked_helper_has_post_fallback_check(src):
    """Helper must block when previous partner turn was a generic fallback."""
    assert "_CLOSING_BLOCK_POST_FALLBACK" in src
    assert "post_generic_fallback" in src


# ---------------------------------------------------------------------------
# 9. Fire condition includes _cm_blocked_signal
# ---------------------------------------------------------------------------

def test_fire_condition_includes_cm_blocked_signal(src):
    """The closing fire condition must include 'not _cm_blocked_signal'."""
    fire_idx = src.find("if (_cm_original or _cm_extended or _cm_preemptible)")
    assert fire_idx != -1, "Closing fire condition not found"
    fire_line_end = src.find("\n", fire_idx)
    fire_line = src[fire_idx:fire_line_end]
    assert "not _cm_blocked_signal" in fire_line, (
        f"Fire condition must include 'not _cm_blocked_signal'; got: {fire_line!r}"
    )


# ---------------------------------------------------------------------------
# 10. Suppressed-reason trace includes new blocked reasons
# ---------------------------------------------------------------------------

def test_suppressed_reason_trace_has_cm_blocked_reason(src):
    """The suppressed-reason trace must emit _cm_blocked_reason when blocked."""
    assert "_cm_blocked_reason" in src, (
        "_cm_blocked_reason must appear in suppressed-reason trace"
    )


def test_suppressed_reason_trace_blocked_before_late_session(src):
    """_cm_blocked_signal check must appear before not_late_session in trace."""
    trace_idx = src.find("Suppressed-reason trace — always populated")
    assert trace_idx != -1
    block = src[trace_idx: trace_idx + 800]
    blocked_pos = block.find("_cm_blocked_signal")
    late_pos = block.find("not_late_session")
    assert blocked_pos != -1, "_cm_blocked_signal not found in trace block"
    assert late_pos != -1, "not_late_session not found in trace block"
    assert blocked_pos < late_pos, (
        "_cm_blocked_signal check must appear before not_late_session in trace"
    )


# ---------------------------------------------------------------------------
# 11. Unit tests for _is_closing_blocked_by_learner_signal (live import)
# ---------------------------------------------------------------------------

import importlib.util
import sys

_srv_cache_cms: dict = {}


def _load_server_cms():
    if "srv" in _srv_cache_cms:
        return _srv_cache_cms["srv"]
    spec = importlib.util.spec_from_file_location("ui_server_cms", UI_SERVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_cms"] = mod
    spec.loader.exec_module(mod)
    _srv_cache_cms["srv"] = mod
    return mod


@pytest.mark.parametrize("text,expected_blocked,expected_reason", [
    ("再说一遍", True, "confusion_or_recovery"),
    ("什么意思", True, "confusion_or_recovery"),
    ("我不懂", True, "confusion_or_recovery"),
    ("不明白", True, "confusion_or_recovery"),
    ("太难了", True, "frustration"),
    ("算了", True, "frustration"),
    ("你说太快了", True, "frustration"),
    ("好难啊", True, "frustration"),
    ("继续", True, "continuation_request"),
    ("然后呢", True, "continuation_request"),
    ("接着说", True, "continuation_request"),
    ("下面", True, "continuation_request"),
    # Normal CJK answers — not blocked
    ("北京", False, ""),
    ("我住在上海", False, ""),
    ("对", False, ""),
])
def test_closing_blocked_signal_text_cases(text, expected_blocked, expected_reason):
    srv = _load_server_cms()
    blocked, reason = srv._is_closing_blocked_by_learner_signal(text, "")
    assert blocked == expected_blocked, (
        f"{text!r}: expected blocked={expected_blocked}, got blocked={blocked} reason={reason!r}"
    )
    if expected_blocked:
        assert reason == expected_reason, (
            f"{text!r}: expected reason={expected_reason!r}, got {reason!r}"
        )


def test_closing_blocked_low_asr_non_cjk():
    srv = _load_server_cms()
    blocked, reason = srv._is_closing_blocked_by_learner_signal("hello", "")
    assert blocked is True
    assert reason == "low_asr_confidence"


def test_closing_blocked_post_generic_fallback():
    srv = _load_server_cms()
    blocked, reason = srv._is_closing_blocked_by_learner_signal(
        "我住在北京", "这个我不太清楚。"
    )
    assert blocked is True
    assert reason == "post_generic_fallback"


def test_closing_not_blocked_normal_answer():
    srv = _load_server_cms()
    blocked, _ = srv._is_closing_blocked_by_learner_signal("我喜欢旅行", "你去过哪里？")
    assert blocked is False


def test_closing_blocked_marker_constants_present():
    srv = _load_server_cms()
    assert hasattr(srv, "_CLOSING_BLOCK_FRUSTRATION")
    assert hasattr(srv, "_CLOSING_BLOCK_CONTINUATION")
    assert hasattr(srv, "_CLOSING_BLOCK_POST_FALLBACK")
    assert "太难了" in srv._CLOSING_BLOCK_FRUSTRATION
    assert "继续" in srv._CLOSING_BLOCK_CONTINUATION
    assert "电脑角色" in srv._CLOSING_BLOCK_POST_FALLBACK
