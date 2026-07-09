"""
Tests for: Improve meaning recovery (Task 1).

Verifies that:
  1. 什么意思啊 routes to _meaning_recovery_reply, NOT _clarify_app_question.
  2. The returned reply contains English gloss + simpler Chinese + example answer.
  3. 再说一遍 / 慢一点说 still route to _clarify_app_question (unchanged).
  4. 给我一个例子 routes separately (example request).
  5. Regression: session_1782907566569 turn 8 — partner must NOT simply repeat 离那儿远吗.
  6. Genuine persona questions (你做什么工作) are NOT classified as meaning requests.
  7. New marker constants are defined and split correctly.
"""

import importlib.util
import sys
import pathlib
import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SRV = _REPO_ROOT / "scripts" / "ui_server.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("ui_server", _SRV)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def srv():
    return _load_server()


# ── Constant structure ─────────────────────────────────────────────────────────

class TestRecoveryConstants:
    def test_repeat_markers_defined(self, srv):
        assert hasattr(srv, "_REPEAT_REQUEST_MARKERS")
        assert "再说一遍" in srv._REPEAT_REQUEST_MARKERS

    def test_slower_markers_defined(self, srv):
        assert hasattr(srv, "_SLOWER_REQUEST_MARKERS")
        assert "慢一点" in srv._SLOWER_REQUEST_MARKERS
        assert "慢慢说" in srv._SLOWER_REQUEST_MARKERS

    def test_meaning_markers_defined(self, srv):
        assert hasattr(srv, "_MEANING_REQUEST_MARKERS")
        assert "什么意思" in srv._MEANING_REQUEST_MARKERS

    def test_example_markers_defined(self, srv):
        assert hasattr(srv, "_EXAMPLE_REQUEST_MARKERS")
        assert "给我一个例子" in srv._EXAMPLE_REQUEST_MARKERS

    def test_bare_repeat_utterances_defined(self, srv):
        assert hasattr(srv, "_BARE_REPEAT_UTTERANCES")
        assert "啊？" in srv._BARE_REPEAT_UTTERANCES

    def test_slower_markers_not_in_repeat_markers(self, srv):
        """慢一点 must be in SLOWER, not in REPEAT."""
        assert "慢一点" not in srv._REPEAT_REQUEST_MARKERS

    def test_meaning_markers_not_in_repeat_markers(self, srv):
        """什么意思 must be in MEANING, not in REPEAT."""
        assert "什么意思" not in srv._REPEAT_REQUEST_MARKERS


# ── _meaning_recovery_reply function ──────────────────────────────────────────

class TestMeaningRecoveryReply:
    def test_function_exists(self, srv):
        assert hasattr(srv, "_meaning_recovery_reply")
        assert callable(srv._meaning_recovery_reply)

    def test_returns_tuple_for_distance_frame(self, srv):
        """离那儿远吗 → returns (zh, en) tuple."""
        result = srv._meaning_recovery_reply("离那儿远吗？")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_regression_does_not_repeat_same_chinese(self, srv):
        """session_1782907566569 turn 8 regression: must not return 我是问：离那儿远吗？."""
        result = srv._meaning_recovery_reply("离那儿远吗？")
        zh = result[0]
        # Must NOT simply repeat the Chinese as "我是问：..."
        assert "我是问：离那儿远吗" not in zh
        assert "我是在问：" not in zh

    def test_regression_contains_english_gloss(self, srv):
        """Result for 离那儿远吗 must include an English explanation."""
        result = srv._meaning_recovery_reply("离那儿远吗？")
        combined = " ".join(result)
        # Must contain English text (ASCII letters)
        has_english = any(c.isascii() and c.isalpha() for c in combined)
        assert has_english, f"No English content in: {combined}"

    def test_regression_contains_example_answer(self, srv):
        """Result for 离那儿远吗 must include a Chinese example answer."""
        result = srv._meaning_recovery_reply("离那儿远吗？")
        zh = result[0]
        # Should contain an example answer (looks for 不太远 or 比如)
        assert "比如" in zh or "不太远" in zh or "例" in zh

    def test_strips_clarification_prefix(self, srv):
        """我是问：离那儿远吗？ should be stripped before matching."""
        result = srv._meaning_recovery_reply("我是问：离那儿远吗？")
        zh = result[0]
        assert "我是问：我是问：" not in zh
        assert "我是在问：我是问：" not in zh

    def test_food_frame_contains_english(self, srv):
        result = srv._meaning_recovery_reply("那儿有什么好吃的？")
        zh, en = result
        assert "good food" in en.lower() or "eat" in en.lower() or "食" in zh

    def test_work_frame_contains_english(self, srv):
        result = srv._meaning_recovery_reply("你做什么工作？")
        zh, en = result
        assert "job" in en.lower() or "work" in en.lower()

    def test_empty_input_returns_none(self, srv):
        assert srv._meaning_recovery_reply("") is None
        assert srv._meaning_recovery_reply(None) is None

    def test_generic_fallback_has_english(self, srv):
        """Unknown frame text → generic fallback still has English."""
        result = srv._meaning_recovery_reply("你最喜欢什么颜色？")
        zh, en = result
        has_english = any(c.isascii() and c.isalpha() for c in en)
        assert has_english

    def test_table_defined(self, srv):
        assert hasattr(srv, "_MEANING_RECOVERY_TABLE")
        assert len(srv._MEANING_RECOVERY_TABLE) >= 10


# ── Routing classification helpers ────────────────────────────────────────────

class TestRecoveryRoutingClassification:
    """Verify that the routing variables _is_meaning / _is_rr are classified
    correctly for common inputs. We test indirectly via the constant memberships."""

    def test_shenme_yisi_a_is_meaning(self, srv):
        text = "什么意思啊？"
        is_meaning = any(m in text for m in srv._MEANING_REQUEST_MARKERS)
        is_rr = (
            any(m in text for m in srv._REPEAT_REQUEST_MARKERS)
            or any(m in text for m in srv._SLOWER_REQUEST_MARKERS)
            or text.strip() in srv._BARE_REPEAT_UTTERANCES
        )
        assert is_meaning, "什么意思啊 must be classified as meaning request"
        # is_meaning should be checked first, so is_rr does not override
        assert is_rr is False, "什么意思啊 must NOT also match repeat/slower"

    def test_zai_shuo_yi_bian_is_repeat(self, srv):
        text = "再说一遍"
        is_meaning = any(m in text for m in srv._MEANING_REQUEST_MARKERS)
        is_rr = any(m in text for m in srv._REPEAT_REQUEST_MARKERS)
        assert not is_meaning
        assert is_rr

    def test_man_yi_dian_is_slower(self, srv):
        text = "慢一点说"
        is_meaning = any(m in text for m in srv._MEANING_REQUEST_MARKERS)
        is_slower = any(m in text for m in srv._SLOWER_REQUEST_MARKERS)
        assert not is_meaning
        assert is_slower

    def test_gei_wo_li_zi_is_example(self, srv):
        text = "给我一个例子"
        is_example = any(m in text for m in srv._EXAMPLE_REQUEST_MARKERS)
        is_meaning = any(m in text for m in srv._MEANING_REQUEST_MARKERS)
        assert is_example
        assert not is_meaning

    def test_a_bare_is_repeat_sound(self, srv):
        text = "啊？"
        is_bare = text.strip() in srv._BARE_REPEAT_UTTERANCES
        assert is_bare

    def test_persona_question_not_meaning(self, srv):
        """你做什么工作 must NOT be classified as a meaning request."""
        text = "你做什么工作"
        is_meaning = any(m in text for m in srv._MEANING_REQUEST_MARKERS)
        assert not is_meaning


# ── Source-code guards ────────────────────────────────────────────────────────

class TestSourceGuards:
    def test_routing_uses_is_meaning_branch(self):
        src = _SRV.read_text(encoding="utf-8")
        assert "_is_meaning" in src, "_is_meaning variable must exist in routing block"
        assert "_meaning_recovery_reply(" in src, "must call _meaning_recovery_reply"

    def test_routing_uses_is_example_branch(self):
        src = _SRV.read_text(encoding="utf-8")
        assert "_is_example" in src

    def test_is_rr_no_longer_checks_shenme_yisi(self):
        """The old hack 'len <= 5 and 什么意思 in text' must be removed."""
        src = _SRV.read_text(encoding="utf-8")
        assert 'len(_last_text_for_counter.strip()) <= 5 and "什么意思"' not in src

    def test_meaning_markers_split_from_repeat_markers(self):
        """Ensure the old combined _REPEAT_REQUEST_MARKERS no longer contains 慢一点."""
        src = _SRV.read_text(encoding="utf-8")
        # Find _REPEAT_REQUEST_MARKERS block — extract only the content inside the parens.
        start = src.index("_REPEAT_REQUEST_MARKERS: tuple = (")
        paren_open = src.index("(", start)
        paren_close = src.index(")", paren_open)
        block = src[paren_open:paren_close + 1]
        assert "慢一点" not in block, "慢一点 must be in _SLOWER_REQUEST_MARKERS, not _REPEAT_REQUEST_MARKERS"
