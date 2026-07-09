#!/usr/bin/env python3
"""
Regression tests: direct learner questions must receive persona-grounded answers.

Covers the 8 questions listed in the task directive:
  你喜欢北京吗？
  你为什么喜欢那里？
  下次想去哪里？
  你做这个工作多久了？
  你喜欢这个工作吗？
  工作中最有趣的是什么？
  你现在还住在那里吗？
  你和爸爸妈妈近吗？

Required: must NOT produce generic/placeholder lines:
  我觉得都挺有意思的。
  主要负责语音识别项目。
  这个我不太清楚。

If no persona fact exists, a natural safe fallback is allowed.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
_UI_SERVER = _SCRIPTS / "ui_server.py"

_srv_cache: dict = {}

# Lines that must NEVER appear as the complete answer.
_GENERIC_FORBIDDEN: frozenset = frozenset({
    "我觉得都挺有意思的。",
    "主要负责语音识别项目。",
    "这个我不太清楚。",
})


def _load_server():
    if "srv" in _srv_cache:
        return _srv_cache["srv"]
    spec = importlib.util.spec_from_file_location("ui_server_dqc", _UI_SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_dqc"] = mod
    spec.loader.exec_module(mod)
    _srv_cache["srv"] = mod
    return mod


def _answer(question: str, persona_id: str = "meiling") -> str | None:
    srv = _load_server()
    persona = srv._resolve_persona(persona_id)
    last_answer = {
        "submitted_text": question,
        "selected_option_hanzi": question,
        "frame_id": "f_unknown",
    }
    if srv._is_user_question(last_answer):
        result = srv._answer_user_question_prefix(last_answer, persona, recent_replies=[])
        if result:
            return result[0]
    direct = srv._direct_persona_answer(question, persona)
    if direct:
        return direct
    mirror = srv._find_mirror_answer(question, "", persona)
    if mirror:
        return mirror[0]
    return None


def _assert_ok(answer: str | None, question: str, persona_id: str) -> None:
    assert answer is not None, f"[{persona_id}] {question!r} → None"
    assert answer.strip(), f"[{persona_id}] {question!r} → empty string"
    assert answer not in _GENERIC_FORBIDDEN, (
        f"[{persona_id}] {question!r} → forbidden generic: {answer!r}"
    )


# ── 1. 你喜欢北京吗？ — place preference with city match ───────────────────

def test_like_beijing_non_generic():
    answer = _answer("你喜欢北京吗？")
    _assert_ok(answer, "你喜欢北京吗？", "meiling")


def test_like_beijing_contains_preference_signal():
    answer = _answer("你喜欢北京吗？")
    assert answer is not None
    assert any(kw in answer for kw in ("喜欢", "挺好", "很棒", "不错", "有活力", "很大")), (
        f"expected a preference signal in: {answer!r}"
    )


# ── 2. 你为什么喜欢那里？ — place_why_like or travel_why_fav ───────────────

def test_why_like_there_non_generic():
    answer = _answer("你为什么喜欢那里？")
    _assert_ok(answer, "你为什么喜欢那里？", "meiling")


@pytest.mark.parametrize("persona_id", ["meiling", "jianguo", "xiaoming", "zhiyuan"])
def test_why_like_there_all_personas(persona_id: str):
    answer = _answer("你为什么喜欢那里？", persona_id)
    _assert_ok(answer, "你为什么喜欢那里？", persona_id)


# ── 3. 下次想去哪里？ — travel_next ─────────────────────────────────────────

def test_next_trip_non_generic():
    answer = _answer("下次想去哪里？")
    _assert_ok(answer, "下次想去哪里？", "meiling")


def test_next_trip_has_continuation_signal():
    answer = _answer("下次想去哪里？")
    assert answer is not None
    # Must contain a natural-language continuation (not a hard fact claim about a specific city)
    assert any(kw in answer for kw in ("想", "想去", "打算", "计划", "希望", "没定好", "没想好")), (
        f"expected a forward-looking phrase in: {answer!r}"
    )


@pytest.mark.parametrize("persona_id", ["meiling", "jianguo", "xiaoming", "zhiyuan"])
def test_next_trip_all_personas(persona_id: str):
    answer = _answer("下次想去哪里？", persona_id)
    _assert_ok(answer, "下次想去哪里？", persona_id)


# ── 4. 你做这个工作多久了？ — work_duration ──────────────────────────────

def test_work_duration_non_generic():
    answer = _answer("你做这个工作多久了？")
    _assert_ok(answer, "你做这个工作多久了？", "meiling")


def test_work_duration_contains_time_signal():
    answer = _answer("你做这个工作多久了？")
    assert answer is not None
    assert any(kw in answer for kw in ("年", "久", "八", "开始", "以来", "毕业", "一直")), (
        f"expected a duration signal in: {answer!r}"
    )


# ── 5. 你喜欢这个工作吗？ — work_like ───────────────────────────────────────

def test_like_work_non_generic():
    answer = _answer("你喜欢这个工作吗？")
    _assert_ok(answer, "你喜欢这个工作吗？", "meiling")


def test_like_work_contains_sentiment():
    answer = _answer("你喜欢这个工作吗？")
    assert answer is not None
    assert any(kw in answer for kw in ("喜欢", "挺好", "挺喜欢", "有意思", "不错", "喜欢的")), (
        f"expected a sentiment signal in: {answer!r}"
    )


# ── 6. 工作中最有趣的是什么？ — work_interesting ─────────────────────────

def test_work_interesting_non_generic():
    answer = _answer("工作中最有趣的是什么？")
    _assert_ok(answer, "工作中最有趣的是什么？", "meiling")


@pytest.mark.parametrize("persona_id", ["meiling", "jianguo", "xiaoming", "zhiyuan"])
def test_work_interesting_all_personas(persona_id: str):
    answer = _answer("工作中最有趣的是什么？", persona_id)
    _assert_ok(answer, "工作中最有趣的是什么？", persona_id)


# ── 7. 你现在还住在那里吗？ — place_still_live ───────────────────────────

def test_still_live_there_non_generic():
    answer = _answer("你现在还住在那里吗？")
    _assert_ok(answer, "你现在还住在那里吗？", "meiling")


def test_still_live_there_contains_city():
    answer = _answer("你现在还住在那里吗？")
    assert answer is not None
    # meiling's city is Xi'an
    assert "西安" in answer, f"expected 西安 in answer: {answer!r}"


@pytest.mark.parametrize("persona_id", ["meiling", "jianguo", "xiaoming", "zhiyuan"])
def test_still_live_all_personas(persona_id: str):
    answer = _answer("你现在还住在那里吗？", persona_id)
    _assert_ok(answer, "你现在还住在那里吗？", persona_id)
    # Must contain a city name (not a bare generic)
    srv = _load_server()
    persona = srv._resolve_persona(persona_id)
    profile = (persona or {}).get("profile") or {}
    city = (profile.get("city") or "").strip()
    hometown = (profile.get("hometown") or "").strip()
    assert city in answer or hometown in answer, (
        f"[{persona_id}] expected city/hometown in: {answer!r}"
    )


# ── 8. 你和爸爸妈妈近吗？ — family closeness ────────────────────────────

def test_close_to_parents_non_generic():
    answer = _answer("你和爸爸妈妈近吗？")
    _assert_ok(answer, "你和爸爸妈妈近吗？", "meiling")


def test_close_to_parents_natural_response():
    answer = _answer("你和爸爸妈妈近吗？")
    assert answer is not None
    assert any(kw in answer for kw in ("近", "亲", "联系", "一起", "感情", "好")), (
        f"expected a relational signal in: {answer!r}"
    )


# ── Cross-persona sweep ──────────────────────────────────────────────────────

@pytest.mark.parametrize("question,persona_id", [
    (q, pid)
    for q in [
        "你喜欢北京吗？",
        "你为什么喜欢那里？",
        "下次想去哪里？",
        "你做这个工作多久了？",
        "你喜欢这个工作吗？",
        "工作中最有趣的是什么？",
        "你现在还住在那里吗？",
        "你和爸爸妈妈近吗？",
    ]
    for pid in ["meiling", "jianguo", "xiaoming", "zhiyuan"]
])
def test_cross_persona_no_forbidden_generic(question: str, persona_id: str):
    answer = _answer(question, persona_id)
    _assert_ok(answer, question, persona_id)


# ── Static routing coverage ─────────────────────────────────────────────────

def test_stub_handles_work_interesting():
    src = _UI_SERVER.read_text(encoding="utf-8")
    assert "topic == \"work_interesting\"" in src or "topic == 'work_interesting'" in src


def test_stub_handles_travel_why_fav():
    src = _UI_SERVER.read_text(encoding="utf-8")
    assert "travel_why_fav" in src


def test_stub_handles_travel_next():
    src = _UI_SERVER.read_text(encoding="utf-8")
    assert "travel_next" in src


def test_stub_handles_place_still_live():
    src = _UI_SERVER.read_text(encoding="utf-8")
    assert "place_still_live" in src


def test_stub_handles_place_why_like():
    src = _UI_SERVER.read_text(encoding="utf-8")
    assert "place_why_like" in src


def test_direct_handles_family_closeness():
    src = _UI_SERVER.read_text(encoding="utf-8")
    assert "_FAM_CLOSE_MARKERS" in src


def test_direct_handles_why_like_place():
    src = _UI_SERVER.read_text(encoding="utf-8")
    assert "_WHY_LIKE_PLACE_MARKERS" in src
