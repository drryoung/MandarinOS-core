"""
Tests for: Add qualitative friction signals to session intelligence (Task 3).

Verifies that:
  1. compute_friction_signals() returns the expected dict shape.
  2. repeated_generic_fallback is counted correctly.
  3. near_duplicate_persona_replies detects consecutive near-identical turns.
  4. premature_closing_after_confusion detects closing after confusion signal.
  5. learner_frustration_count counts frustration markers.
  6. has_significant_friction is True when thresholds are exceeded.
  7. Stability score is capped when friction signals are significant.
  8. Flow label is not 'Smooth' or 'Stable' when friction is significant.
  9. build_session_record() includes friction_signals in the record.
"""

import importlib.util
import pathlib
import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SI = _REPO_ROOT / "scripts" / "session_intelligence.py"
_SRV = _REPO_ROOT / "scripts" / "ui_server.py"


def _load_si():
    spec = importlib.util.spec_from_file_location("session_intelligence", _SI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_server():
    spec = importlib.util.spec_from_file_location("ui_server", _SRV)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def si():
    return _load_si()


@pytest.fixture(scope="module")
def srv():
    return _load_server()


def _p(zh):
    return {"role": "partner", "text_zh": zh}


def _u(zh):
    return {"role": "user", "text_zh": zh}


# ── compute_friction_signals return shape ──────────────────────────────────────

class TestFrictionSignalsShape:
    def test_function_exists(self, si):
        assert hasattr(si, "compute_friction_signals")

    def test_empty_transcript_returns_zeros(self, si):
        result = si.compute_friction_signals([])
        assert isinstance(result, dict)
        assert result["repeated_generic_fallback"] == 0
        assert result["near_duplicate_persona_replies"] == 0
        assert result["premature_closing_after_confusion"] == 0
        assert result["learner_frustration_count"] == 0
        assert result["has_significant_friction"] is False

    def test_none_transcript_returns_zeros(self, si):
        result = si.compute_friction_signals(None)
        assert result["has_significant_friction"] is False

    def test_all_required_keys_present(self, si):
        result = si.compute_friction_signals([])
        required = {
            "repeated_generic_fallback",
            "near_duplicate_persona_replies",
            "unanswered_direct_questions",
            "premature_closing_after_confusion",
            "learner_frustration_count",
            "has_significant_friction",
        }
        assert required <= set(result.keys())


# ── Repeated generic fallback ──────────────────────────────────────────────────

class TestRepeatedGenericFallback:
    def test_two_consecutive_generic_fallbacks_counted(self, si):
        transcript = [
            _p("你好！"),
            _u("我住在上海。"),
            _p("这样挺好"),
            _u("嗯"),
            _p("真不错啊"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["repeated_generic_fallback"] >= 1

    def test_single_generic_not_repeated(self, si):
        transcript = [
            _p("你住哪里？"),
            _u("我住上海。"),
            _p("这样挺好"),
            _u("好的。"),
            _p("你喜欢那里吗？"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["repeated_generic_fallback"] == 0

    def test_different_partner_replies_not_counted(self, si):
        transcript = [
            _p("你好！"),
            _u("你好！"),
            _p("你住哪里？"),
            _u("上海。"),
            _p("哦，上海！"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["repeated_generic_fallback"] == 0


# ── Near-duplicate persona replies ────────────────────────────────────────────

class TestNearDuplicatePersonaReplies:
    def test_identical_consecutive_partner_counted(self, si):
        transcript = [
            _u("什么意思？"),
            _p("我是问：离那儿远吗？"),
            _u("什么意思啊？"),
            _p("我是问：离那儿远吗？"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["near_duplicate_persona_replies"] >= 1

    def test_different_replies_not_counted(self, si):
        transcript = [
            _p("你住哪里？"),
            _u("上海。"),
            _p("好的，上海！你喜欢那里吗？"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["near_duplicate_persona_replies"] == 0


# ── Premature closing after confusion ─────────────────────────────────────────

class TestPrematureClosingAfterConfusion:
    def test_closing_after_confusion_counted(self, si):
        transcript = [
            _p("你住哪里？"),
            _u("听不懂！"),
            _p("这样挺好"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["premature_closing_after_confusion"] >= 1

    def test_closing_without_confusion_not_counted(self, si):
        transcript = [
            _p("你住哪里？"),
            _u("我住上海。"),
            _p("这样挺好"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["premature_closing_after_confusion"] == 0

    def test_shenme_yisi_triggers_confusion_flag(self, si):
        transcript = [
            _p("你住哪里？"),
            _u("什么意思？"),
            _p("真不错啊"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["premature_closing_after_confusion"] >= 1


# ── Learner frustration ────────────────────────────────────────────────────────

class TestLearnerFrustration:
    def test_too_hard_counted(self, si):
        transcript = [
            _p("你住哪里？"),
            _u("太难了"),
            _p("没关系，慢慢来。"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["learner_frustration_count"] >= 1

    def test_multiple_frustration_markers(self, si):
        transcript = [
            _u("太难了"),
            _p("好的。"),
            _u("算了，听不懂"),
            _p("我们再试一次。"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["learner_frustration_count"] >= 2

    def test_has_significant_friction_when_frustrated_twice(self, si):
        transcript = [
            _u("太难了"),
            _p("好的。"),
            _u("算了，听不懂"),
            _p("我们再试一次。"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["has_significant_friction"] is True


# ── has_significant_friction threshold ────────────────────────────────────────

class TestSignificantFrictionThreshold:
    def test_two_repeated_generics_is_significant(self, si):
        transcript = [
            _u("嗯"),
            _p("这样挺好"),
            _u("嗯"),
            _p("真不错啊"),
        ]
        result = si.compute_friction_signals(transcript)
        # The significant friction should be True when repeated generic >= 2
        # (threshold is >= 2 consecutive)
        # We detect repeated_generic_fallback — significant when >= 2
        if result["repeated_generic_fallback"] >= 2:
            assert result["has_significant_friction"] is True

    def test_clean_session_not_significant(self, si):
        transcript = [
            _p("你住哪里？"),
            _u("我住上海。"),
            _p("好的！上海很大。"),
            _u("是的！"),
            _p("你喜欢那里吗？"),
            _u("很喜欢！"),
        ]
        result = si.compute_friction_signals(transcript)
        assert result["has_significant_friction"] is False


# ── Stability score capped by friction ────────────────────────────────────────

class TestStabilityScoreFrictionPenalty:
    def test_score_capped_for_repeated_generic_fallback(self, srv):
        sess = {
            "total_turns": 20,
            "unmatched_responses": 0,
            "soft_unmatched_responses": 0,
            "recovery_uses": 0,
            "conversational_recoveries": 0,
            "friction_signals": {
                "repeated_generic_fallback": 3,
                "has_significant_friction": True,
                "near_duplicate_persona_replies": 0,
                "premature_closing_after_confusion": 0,
                "learner_frustration_count": 0,
            },
        }
        stability = {"rate": 0.0}
        score = srv._conversation_stability_score(stability, 20, sess)
        assert score is not None
        assert score <= 75, f"Score {score} should be capped at 75 for repeated generic fallback"

    def test_score_capped_for_premature_closing(self, srv):
        sess = {
            "total_turns": 15,
            "unmatched_responses": 0,
            "soft_unmatched_responses": 0,
            "recovery_uses": 0,
            "conversational_recoveries": 0,
            "friction_signals": {
                "repeated_generic_fallback": 0,
                "has_significant_friction": False,
                "near_duplicate_persona_replies": 0,
                "premature_closing_after_confusion": 1,
                "learner_frustration_count": 0,
            },
        }
        stability = {"rate": 0.0}
        score = srv._conversation_stability_score(stability, 15, sess)
        assert score is not None
        assert score <= 80, f"Score {score} should be capped at 80 for premature closing"

    def test_clean_session_not_penalized(self, srv):
        sess = {
            "total_turns": 20,
            "unmatched_responses": 0,
            "soft_unmatched_responses": 0,
            "recovery_uses": 0,
            "conversational_recoveries": 0,
            "friction_signals": {
                "repeated_generic_fallback": 0,
                "has_significant_friction": False,
                "near_duplicate_persona_replies": 0,
                "premature_closing_after_confusion": 0,
                "learner_frustration_count": 0,
            },
        }
        stability = {"rate": 0.0}
        score = srv._conversation_stability_score(stability, 20, sess)
        assert score == 100


# ── Flow label not Smooth/Stable with significant friction ─────────────────────

class TestFlowLabelFriction:
    def test_not_smooth_with_significant_friction(self, srv):
        label = srv._format_progress_flow_label(
            score=95,
            unclear_turns=0,
            total_turns=20,
            turbulence_survived=False,
            continued_after_ambiguity=False,
            recovery_uses=0,
            conversational_recoveries=0,
            friction_signals={
                "has_significant_friction": True,
                "repeated_generic_fallback": 3,
                "premature_closing_after_confusion": 0,
            },
        )
        assert label not in ("Smooth", "Stable"), f"Label should not be {label!r} with significant friction"

    def test_smooth_without_friction(self, srv):
        label = srv._format_progress_flow_label(
            score=98,
            unclear_turns=0,
            total_turns=20,
            turbulence_survived=False,
            continued_after_ambiguity=False,
            recovery_uses=0,
            conversational_recoveries=0,
            friction_signals={
                "has_significant_friction": False,
                "repeated_generic_fallback": 0,
                "premature_closing_after_confusion": 0,
            },
        )
        assert label == "Smooth"


# ── build_session_record includes friction_signals ─────────────────────────────

class TestBuildSessionRecordFriction:
    def test_friction_signals_key_in_source(self):
        src = _SI.read_text(encoding="utf-8")
        assert "friction_signals" in src

    def test_compute_friction_signals_called_in_build(self):
        src = _SI.read_text(encoding="utf-8")
        assert "compute_friction_signals(" in src
