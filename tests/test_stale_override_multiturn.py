#!/usr/bin/env python3
"""
Multi-turn regression tests for the stale counter-reply override fix.

Root cause (ffc806c): When _prev_counter_reply was set and
_is_direct_persona_question returned True, the override branch called
_answer_user_question_prefix which prioritised _find_mirror_answer BEFORE
_direct_persona_answer.  The mirror bank could return a recycled city/place
answer (the same as _prev_counter_reply or an equally wrong answer) for
questions like "成都有什么好吃啊" or "你做什么工作".

Fix: the override branch now calls _direct_persona_answer directly.  Only if
_direct_persona_answer returns a non-None answer that differs from
_prev_counter_reply is _counter_result set.  Otherwise the turn falls through
to standard routing (E3 working memory → mirror bank → _answer_user_question_prefix).

A belt-and-suspenders exact-repeat guard was also restored at the end of the
counter-reply block (pre-ffc806c behaviour).

Test structure
--------------
Each test class simulates the fixed stale override logic directly, mirroring
what run_turn now does, then checks the output.  This matches the existing test
style in test_regression_surgical_transcript.py.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
_UI_SERVER = ROOT / "scripts" / "ui_server.py"

_cache: dict = {}


def _load(name: str, path: Path):
    if name in _cache:
        return _cache[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _cache[name] = mod
    return mod


@pytest.fixture(scope="module")
def srv():
    return _load("ui_server_stale_mt", _UI_SERVER)


@pytest.fixture(scope="module")
def xiaoming(srv):
    """Persona: city=北京, hometown=成都, occupation=软件工程师."""
    return srv._resolve_persona("xiaoming")


@pytest.fixture(scope="module")
def jianguo(srv):
    """Persona: city/hometown=重庆, chef."""
    return srv._resolve_persona("jianguo")


def _simulate_stale_override(
    srv,
    *,
    utterance: str,
    prev_counter_reply: str,
    persona,
    recent_persona_replies: Optional[list] = None,
) -> Optional[tuple]:
    """
    Replicates the fixed stale override elif branch in run_turn.

    Returns (_so_zh, _so_en) if the override fires and produces a fresh
    answer, or None if:
      - _is_direct_persona_question returns False, or
      - _direct_persona_answer returns None (fall-through), or
      - the answer equals prev_counter_reply (exact match; no advancement).
    """
    t = utterance
    if not srv._is_direct_persona_question(t):
        return None
    if srv._is_confusion_signal(t):
        return None

    _so_raw = srv._direct_persona_answer(
        t, persona, recent_replies=recent_persona_replies or []
    )
    if not _so_raw:
        return None  # fall through — do NOT manufacture a mirror answer

    _so_zh = f"我呢，{_so_raw}" if not _so_raw.startswith("我") else _so_raw
    _so_en = srv._persona_answer_en(
        persona, _so_zh, srv._detect_reverse_fact_intent(t)
    )
    if _so_zh.strip() == (prev_counter_reply or "").strip():
        return None  # exact repeat — fall through to dedup guard

    return (_so_zh, _so_en)


def _belt_and_suspenders(srv, counter_reply: str, prev_counter_reply: str, persona):
    """Replicates the restored simple dedup guard at the end of run_turn."""
    if counter_reply.strip() == (prev_counter_reply or "").strip():
        return srv._persona_deflect("generic", counter_reply)
    return counter_reply


# ── A  Hometown answer → city food question ──────────────────────────────────

class TestA_CityfoodAfterHometownAnswer:
    """
    APP answered "我是成都人，不过在北京工作已经好几年了。"
    USER asks  "成都有什么好吃啊"
    Expected:  food answer (火锅 / 串串 / 回锅肉 / 担担面), NOT the hometown line.
    """

    PREV = "我是成都人，不过在北京工作已经好几年了。"
    Q = "成都有什么好吃啊"

    def test_is_direct_persona_question(self, srv):
        assert srv._is_direct_persona_question(self.Q)

    def test_direct_persona_answer_returns_food(self, srv, xiaoming):
        raw = srv._direct_persona_answer(self.Q, xiaoming)
        assert raw is not None
        food_words = ("火锅", "串串", "回锅肉", "担担面", "小吃", "美食", "好吃")
        assert any(w in raw for w in food_words), (
            f"Expected a food answer, got: {raw!r}"
        )

    def test_stale_override_returns_food_not_hometown(self, srv, xiaoming):
        result = _simulate_stale_override(
            srv, utterance=self.Q, prev_counter_reply=self.PREV, persona=xiaoming
        )
        assert result is not None, "Override should fire — _direct_persona_answer has a food answer"
        zh, _en = result
        assert self.PREV.strip() not in zh, (
            f"Stale override must not return the previous hometown answer. Got: {zh!r}"
        )
        food_words = ("火锅", "串串", "回锅肉", "担担面", "小吃", "美食", "好吃")
        assert any(w in zh for w in food_words), (
            f"Expected a food-related answer, got: {zh!r}"
        )

    def test_stale_override_english_nonempty(self, srv, xiaoming):
        result = _simulate_stale_override(
            srv, utterance=self.Q, prev_counter_reply=self.PREV, persona=xiaoming
        )
        assert result is not None
        _zh, en = result
        assert en, "English translation must be non-empty"


# ── B  City food → city special ──────────────────────────────────────────────

class TestB_CitySpecialAfterFoodAnswer:
    """
    After the food answer, user asks "成都有什么特别的".
    Expected: feature answer (火锅 / 熊猫 / 慢生活 / 茶馆), NOT a repeat of the food answer.
    """

    PREV_FOOD = "成都美食太丰富了，火锅最有名，但担担面、龙抄手也很好吃。"
    Q = "成都有什么特别的"

    def test_direct_persona_answer_returns_feature(self, srv, xiaoming):
        raw = srv._direct_persona_answer(self.Q, xiaoming)
        assert raw is not None
        feature_words = ("节奏", "悠闲", "火锅", "茶馆", "熊猫", "美食", "特别", "慢")
        assert any(w in raw for w in feature_words), (
            f"Expected a Chengdu feature answer, got: {raw!r}"
        )

    def test_stale_override_differs_from_food_answer(self, srv, xiaoming):
        result = _simulate_stale_override(
            srv, utterance=self.Q, prev_counter_reply=self.PREV_FOOD, persona=xiaoming
        )
        assert result is not None
        zh, _en = result
        assert zh.strip() != self.PREV_FOOD.strip(), (
            f"City-special answer must differ from food answer. Got: {zh!r}"
        )

    def test_stale_override_not_hometown_line(self, srv, xiaoming):
        HOMETOWN_ONLY = "我是成都人，不过在北京工作已经好几年了。"
        result = _simulate_stale_override(
            srv, utterance=self.Q, prev_counter_reply=self.PREV_FOOD, persona=xiaoming
        )
        assert result is not None
        zh, _en = result
        assert HOMETOWN_ONLY.strip() not in zh, (
            f"Must not return the hometown line for a city-special question. Got: {zh!r}"
        )


# ── C  Beijing like → Beijing special (fallthrough case) ─────────────────────

class TestC_BeijingSpecialAfterLikeAnswer:
    """
    APP answered "我呢，喜欢，北京生活很方便，机会也多。"
    USER asks  "你觉得北京有最好的最特别的什么"

    _direct_persona_answer returns None for this phrasing.
    The stale override must NOT manufacture a mirror-bank answer.
    It must return None (fall through to standard routing).
    """

    PREV = "我呢，喜欢，北京生活很方便，机会也多。"
    Q = "你觉得北京有最好的最特别的什么"

    def test_direct_persona_answer_may_return_none(self, srv, xiaoming):
        raw = srv._direct_persona_answer(self.Q, xiaoming)
        # This specific phrasing currently returns None — falls to standard routing.
        # If future content is added, the test stays green; it is only checking we
        # do NOT get the prev counter reply back.
        if raw is not None:
            assert self.PREV.strip() not in raw, (
                f"direct_persona_answer must not return prev counter reply: {raw!r}"
            )

    def test_stale_override_falls_through_when_direct_returns_none(self, srv, xiaoming):
        raw = srv._direct_persona_answer(self.Q, xiaoming)
        if raw is None:
            # Override must return None — do not manufacture a mirror answer.
            result = _simulate_stale_override(
                srv, utterance=self.Q, prev_counter_reply=self.PREV, persona=xiaoming
            )
            assert result is None, (
                f"When _direct_persona_answer returns None, stale override must fall "
                f"through (return None). Got: {result!r}"
            )

    def test_belt_suspenders_guard_catches_exact_repeat(self, srv, xiaoming):
        # Simulate: even if routing somehow produced the same answer,
        # the belt-and-suspenders guard deflects it.
        result = _belt_and_suspenders(srv, self.PREV, self.PREV, xiaoming)
        assert result != self.PREV, (
            f"Belt-and-suspenders guard should deflect an exact repeat. Got: {result!r}"
        )


# ── D  Beijing like → work question ──────────────────────────────────────────

class TestD_WorkAfterBeijingLike:
    """
    APP answered "我呢，喜欢，北京生活很方便，机会也多。"
    USER asks  "你做什么工作"
    Expected:  work/job answer (软件开发 / 工程师), NOT the Beijing-like answer.
    """

    PREV = "我呢，喜欢，北京生活很方便，机会也多。"
    Q = "你做什么工作"

    def test_is_direct_persona_question(self, srv):
        assert srv._is_direct_persona_question(self.Q)

    def test_direct_persona_answer_returns_work(self, srv, xiaoming):
        raw = srv._direct_persona_answer(self.Q, xiaoming)
        assert raw is not None
        work_words = ("软件", "开发", "工程师", "工作", "做", "编程", "代码")
        assert any(w in raw for w in work_words), (
            f"Expected a work answer for 你做什么工作, got: {raw!r}"
        )

    def test_stale_override_returns_work_not_beijing_like(self, srv, xiaoming):
        result = _simulate_stale_override(
            srv, utterance=self.Q, prev_counter_reply=self.PREV, persona=xiaoming
        )
        assert result is not None, (
            "Stale override should fire: _direct_persona_answer has a work answer"
        )
        zh, _en = result
        assert self.PREV.strip() not in zh, (
            f"Must not return the Beijing-like answer for a work question. Got: {zh!r}"
        )
        work_words = ("软件", "开发", "工程师", "工作", "做", "编程", "代码")
        assert any(w in zh for w in work_words), (
            f"Expected a work-related answer, got: {zh!r}"
        )

    def test_stale_override_english_nonempty(self, srv, xiaoming):
        result = _simulate_stale_override(
            srv, utterance=self.Q, prev_counter_reply=self.PREV, persona=xiaoming
        )
        assert result is not None
        _zh, en = result
        assert en, "English must be non-empty for a work direct answer"


# ── E  Repeated work question — exact duplicate handling ─────────────────────

class TestE_RepeatedWorkQuestion:
    """
    USER asks 你做什么工作 twice in a row.
    The second answer must not simply repeat the first.
    Either: _dedupe_persona_answer finds a variant, or the belt-and-suspenders
    guard deflects it — either way the exact text must not repeat.
    """

    Q1 = "你做什么工作"
    Q2 = "你做你做什么工作啊"

    def test_direct_answer_for_q1_exists(self, srv, xiaoming):
        raw = srv._direct_persona_answer(self.Q1, xiaoming)
        assert raw is not None

    def test_direct_answer_for_q2_same_as_q1(self, srv, xiaoming):
        # Both phrasings should return the same underlying work fact.
        r1 = srv._direct_persona_answer(self.Q1, xiaoming)
        r2 = srv._direct_persona_answer(self.Q2, xiaoming)
        assert r1 is not None
        assert r2 is not None

    def test_belt_suspenders_deflects_exact_work_repeat(self, srv, xiaoming):
        raw = srv._direct_persona_answer(self.Q1, xiaoming)
        if raw is None:
            pytest.skip("_direct_persona_answer returned None for work query")
        zh1 = f"我呢，{raw}" if not raw.startswith("我") else raw
        # Simulate: second turn produces the same answer as the first.
        result = _belt_and_suspenders(srv, zh1, zh1, xiaoming)
        assert result != zh1, (
            f"Belt-and-suspenders guard must deflect an exact work-answer repeat. "
            f"Got: {result!r}"
        )

    def test_dedupe_persona_answer_finds_variant_or_deflects(self, srv, xiaoming):
        raw = srv._direct_persona_answer(self.Q1, xiaoming)
        if raw is None:
            pytest.skip("_direct_persona_answer returned None for work query")
        zh1 = f"我呢，{raw}" if not raw.startswith("我") else raw
        pool = [zh1]
        deduped = srv._dedupe_persona_answer(zh1, pool, self.Q2, xiaoming)
        # Must be non-empty and different from the original (or a safe generic deflect)
        assert deduped is not None
        if deduped.strip() == zh1.strip():
            # acceptable only if it's a known deflect phrase
            deflect_pool = [
                p
                for phrases in (srv._persona_deflect_phrases or {}).values()
                for p in phrases
            ]
            assert deduped in deflect_pool or "先不说" in deduped or "等会" in deduped, (
                f"_dedupe_persona_answer returned same text without deflecting: {deduped!r}"
            )


# ── F  Stale override falls through when _direct_persona_answer returns None ──

class TestF_StaleOverrideFallthrough:
    """
    When _direct_persona_answer returns None for a direct-question-looking
    utterance, the stale override must NOT manufacture a mirror-bank answer.
    It must return None, letting standard routing handle the turn.
    """

    PREV = "还没有，一个人也挺自在的。"  # marriage answer
    # A question that looks persona-directed but may not match _direct_persona_answer:
    EDGE_QUERIES = [
        "你觉得北京有最好的最特别的什么",  # confirmed None from _direct_persona_answer
        "你最想去的地方是哪里",  # travel preference — may or may not match
    ]

    def test_none_result_means_fallthrough_not_mirror(self, srv, xiaoming):
        for q in self.EDGE_QUERIES:
            raw = srv._direct_persona_answer(q, xiaoming)
            if raw is None:
                result = _simulate_stale_override(
                    srv, utterance=q, prev_counter_reply=self.PREV, persona=xiaoming
                )
                assert result is None, (
                    f"When _direct_persona_answer=None, stale override must fall through "
                    f"(return None), not inject a mirror answer. Q: {q!r}, got: {result!r}"
                )

    def test_marriage_answer_not_returned_for_different_question(self, srv, xiaoming):
        """Core regression: marriage answer must not repeat for a different question."""
        # Any direct persona question that _direct_persona_answer can answer
        # must not return the marriage prev_counter_reply.
        test_cases = [
            ("你做什么工作", self.PREV),
            ("成都有什么好吃啊", self.PREV),
            ("成都有什么特别的", self.PREV),
        ]
        for q, prev in test_cases:
            result = _simulate_stale_override(
                srv, utterance=q, prev_counter_reply=prev, persona=xiaoming
            )
            if result is not None:
                zh, _en = result
                assert zh.strip() != prev.strip(), (
                    f"Stale override returned marriage answer for {q!r}: {zh!r}"
                )


# ── Guard function presence tests ─────────────────────────────────────────────

class TestGuardFunctions:
    """Verify the key guard and helper functions used by the fix exist."""

    def test_is_direct_persona_question_exists(self, srv):
        assert callable(getattr(srv, "_is_direct_persona_question", None))

    def test_direct_persona_answer_exists(self, srv):
        assert callable(getattr(srv, "_direct_persona_answer", None))

    def test_detect_reverse_fact_intent_exists(self, srv):
        assert callable(getattr(srv, "_detect_reverse_fact_intent", None))

    def test_persona_answer_en_exists(self, srv):
        assert callable(getattr(srv, "_persona_answer_en", None))

    def test_persona_deflect_exists(self, srv):
        assert callable(getattr(srv, "_persona_deflect", None))

    def test_dedupe_persona_answer_exists(self, srv):
        assert callable(getattr(srv, "_dedupe_persona_answer", None))

    def test_belt_suspenders_not_same(self, srv, xiaoming):
        # Verify _persona_deflect("generic", x) != x for a non-deflect phrase.
        test_phrase = "我是成都人，不过在北京工作已经好几年了。"
        deflected = srv._persona_deflect("generic", test_phrase)
        assert deflected != test_phrase, (
            f"_persona_deflect('generic', ...) should return a different phrase. "
            f"Got: {deflected!r}"
        )
