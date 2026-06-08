#!/usr/bin/env python3
"""
Phase 11.x Conversation-First wave — bounded regression tests.

Covers:
  - Learner question recognition (_is_user_question)
  - Mirror/direct answer coverage (travel_fav, food_spicy)
  - Active-window single-source-of-truth (_activeTurnRecord in app.js)
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
_APP = ROOT / "ui" / "app.js"

_srv_cache: dict = {}


def _load_server():
    if "srv" in _srv_cache:
        return _srv_cache["srv"]
    spec = importlib.util.spec_from_file_location("ui_server_cfw", _SCRIPTS / "ui_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_cfw"] = mod
    spec.loader.exec_module(mod)
    _srv_cache["srv"] = mod
    return mod


def _answer(text: str) -> dict:
    return {"submitted_text": text, "frame_id": "p2_tr_1", "selected_option_hanzi": ""}


_PERSONA_TRAVEL = {
    "profile": {"name": "小明", "hometown": "成都", "city": "北京"},
    "discoverable_facts": {
        "travel": "我去过西藏和云南，最喜欢西藏的星空。",
        "travel_where": "我最喜欢西藏，那里的星空特别美。",
        "food": "我很喜欢吃辣，尤其爱川菜和火锅。",
    },
    "discoverable_facts_en": {"travel": "I've been to Tibet and Yunnan."},
    "voice_lines": {"travel": "我很喜欢旅行。", "food": "我很喜欢吃辣。"},
    "voice_lines_en": {},
}


# ── A: Question recognition ───────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "你最喜欢哪个地方？",
    "你最喜欢哪里？",
    "你最喜欢哪儿？",
    "你最喜欢什么？",
    "你喜欢辣吗？",
])
def test_is_user_question_favourite_and_spicy(text):
    srv = _load_server()
    assert srv._is_user_question(_answer(text)) is True


def test_is_user_question_repeated_favourite_place():
    srv = _load_server()
    assert srv._is_user_question(_answer("我问你你最喜欢哪个地方")) is True
    assert srv._is_user_question(_answer("我是说你最喜欢哪里")) is True


# ── B: Mirror / direct answer coverage ────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "你最喜欢哪个地方？",
    "你最喜欢哪里？",
    "你最喜欢哪儿？",
    "我问你你最喜欢哪个地方",
])
def test_find_mirror_travel_fav(text):
    srv = _load_server()
    result = srv._find_mirror_answer(text, "travel", _PERSONA_TRAVEL)
    assert result is not None, f"Expected mirror match for {text!r}"
    zh, _en, topic, eng = result
    assert topic == "travel_fav", f"Expected travel_fav, got {topic!r}"
    assert "你是哪里人" not in zh
    assert "叫我" not in zh


def test_find_mirror_food_spicy():
    srv = _load_server()
    result = srv._find_mirror_answer("你喜欢辣吗？", "food", _PERSONA_TRAVEL)
    assert result is not None
    zh, _en, topic, eng = result
    assert topic == "food_spicy"
    assert "叫我" not in zh


def test_direct_persona_spicy_not_name_fallback():
    srv = _load_server()
    ans = srv._direct_persona_answer("你喜欢辣吗？", _PERSONA_TRAVEL)
    assert ans is not None
    assert "叫我" not in ans
    assert any(k in ans for k in ("辣", "吃", "喜欢", "川", "火"))


def test_answer_prefix_favourite_place_not_identity():
    srv = _load_server()
    result = srv._answer_user_question_prefix(_answer("你最喜欢哪个地方？"), _PERSONA_TRAVEL)
    assert result is not None
    zh, _en = result
    assert "你是哪里人" not in zh
    assert "叫我" not in zh
    assert any(k in zh for k in ("西藏", "云南", "喜欢", "去过", "旅行", "地方"))


# ── C: Active turn record (static app.js checks) ─────────────────────────────

def test_active_turn_record_single_source_of_truth():
    src = _APP.read_text(encoding="utf-8")
    assert "function _initActiveTurnRecord" in src
    assert "function _refreshActiveDisplayFromTurnRecord" in src
    assert "function _updateActiveTurnRecordEn" in src
    assert "_initActiveTurnRecord(" in src
    sync_block = src.split("function _syncActiveEnglishFromGloss")[1].split("function _refreshActiveEnglishFromSentenceHint")[0]
    assert "_updateActiveTurnRecordEn(en)" in sync_block
    assert "window._activeTurnRecord = null" in src


def test_gloss_updates_turn_record_before_display():
    src = _APP.read_text(encoding="utf-8")
    gloss_block = src.split("function maybeRequestGlossForEntry")[1].split("function resolveLineEnglish")[0]
    assert "_syncActiveEnglishFromGloss(entry, entry.text_en)" in gloss_block


# ── D: E3 persona working memory unit tests ────────────────────────────────────

def test_extract_persona_facts_travel_visited():
    srv = _load_server()
    replies = ["我去过西藏和云南，最难忘的是在西藏看到满天的星星。"]
    facts = srv._extract_persona_facts_from_recent(replies)
    assert "travel_visited" in facts
    assert "西藏" in facts["travel_visited"]
    assert "云南" in facts["travel_visited"]


def test_extract_persona_facts_travel_fav():
    srv = _load_server()
    replies = ["我最喜欢西藏，那里的星空很美。"]
    facts = srv._extract_persona_facts_from_recent(replies)
    assert facts.get("travel_fav") == "西藏"


def test_extract_persona_facts_food_spicy_true():
    srv = _load_server()
    replies = ["我挺能吃辣的，非常喜欢川菜。"]
    facts = srv._extract_persona_facts_from_recent(replies)
    assert facts.get("food_spicy") is True


def test_extract_persona_facts_food_spicy_false():
    srv = _load_server()
    replies = ["我不太能吃辣，有点怕辣。"]
    facts = srv._extract_persona_facts_from_recent(replies)
    assert facts.get("food_spicy") is False


def test_extract_persona_facts_hometown():
    srv = _load_server()
    replies = ["我老家在成都，在北京工作。"]
    facts = srv._extract_persona_facts_from_recent(replies)
    assert facts.get("hometown") == "成都"


def test_extract_persona_facts_family():
    srv = _load_server()
    replies = ["我家里有姐姐，我们关系很好。"]
    facts = srv._extract_persona_facts_from_recent(replies)
    assert "family_members" in facts
    assert "姐姐" in facts["family_members"]


def test_extract_persona_facts_empty():
    srv = _load_server()
    assert srv._extract_persona_facts_from_recent([]) == {}
    assert srv._extract_persona_facts_from_recent(None) == {}


def test_extract_persona_facts_window_limit():
    """Working memory must only use the last 5 replies (bounded window)."""
    srv = _load_server()
    old_replies = ["我去过哈尔滨，非常冷。"] * 10  # 10 old replies
    recent = ["我老家在成都。"]
    facts = srv._extract_persona_facts_from_recent(old_replies + recent)
    # 成都 is in the last reply (within window)
    assert facts.get("hometown") == "成都"


def test_extract_persona_facts_does_not_write_cs():
    """_extract_persona_facts_from_recent must not mutate any external state."""
    srv = _load_server()
    sentinel = {}
    replies = ["我去过西藏。"]
    result = srv._extract_persona_facts_from_recent(replies)
    # sentinel still unchanged
    assert sentinel == {}
    assert isinstance(result, dict)


def test_answer_from_working_memory_fav_place():
    srv = _load_server()
    facts = {"travel_fav": "西藏", "travel_visited": ["西藏", "云南"]}
    result = srv._answer_from_working_memory("你最喜欢哪个地方", facts, _PERSONA_TRAVEL)
    assert result is not None
    zh, _en = result
    assert "西藏" in zh


def test_answer_from_working_memory_visited():
    srv = _load_server()
    facts = {"travel_visited": ["西藏", "云南"]}
    result = srv._answer_from_working_memory("你最喜欢哪个地方", facts, _PERSONA_TRAVEL)
    assert result is not None
    zh, _en = result
    assert "西藏" in zh or "云南" in zh


def test_answer_from_working_memory_spicy():
    srv = _load_server()
    facts = {"food_spicy": True}
    result = srv._answer_from_working_memory("你喜欢辣吗", facts, _PERSONA_TRAVEL)
    assert result is not None
    zh, _en = result
    assert "辣" in zh or "能吃" in zh


def test_answer_from_working_memory_none_on_empty():
    srv = _load_server()
    assert srv._answer_from_working_memory("你最喜欢哪里", {}, _PERSONA_TRAVEL) is None
    assert srv._answer_from_working_memory("", {"travel_fav": "西藏"}, _PERSONA_TRAVEL) is None


def test_working_memory_flag_exists_in_server():
    """Static check: _counter_is_working_memory flag is initialised in run_turn."""
    import pathlib as _pl
    src = (_pl.Path(__file__).resolve().parent.parent / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    assert "_counter_is_working_memory = False" in src
    assert "_counter_is_working_memory = True" in src
    assert "_extract_persona_facts_from_recent" in src
    assert "_answer_from_working_memory" in src


# ── E: E2 honest fallback static checks ────────────────────────────────────────

def test_topic_aware_honest_fallback_travel():
    srv = _load_server()
    result = srv._topic_aware_honest_fallback("你最喜欢哪个地方", _PERSONA_TRAVEL)
    assert result is not None
    zh, _en = result
    assert "旅行" in zh or "地方" in zh or "不好说" in zh


def test_topic_aware_honest_fallback_spicy():
    srv = _load_server()
    result = srv._topic_aware_honest_fallback("你喜欢辣吗", _PERSONA_TRAVEL)
    assert result is not None
    zh, _en = result
    assert "辣" in zh or "喜欢" in zh


def test_topic_aware_honest_fallback_irrelevant_returns_none():
    srv = _load_server()
    # Generic unrelated text should return None (caller then uses limitation reply)
    result = srv._topic_aware_honest_fallback("量子计算怎么样", _PERSONA_TRAVEL)
    assert result is None


def test_answer_prefix_uses_topic_aware_fallback():
    """_answer_user_question_prefix must call _topic_aware_honest_fallback before 电脑角色 reply."""
    import pathlib as _pl
    src = (_pl.Path(__file__).resolve().parent.parent / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    apqp_block = src.split("def _answer_user_question_prefix")[1].split("\ndef _")[0]
    assert "_topic_aware_honest_fallback" in apqp_block


# ── F: E4 topic handoff static and unit tests ─────────────────────────────────

def test_question_topic_to_engine_exists():
    """Static check: _QUESTION_TOPIC_TO_ENGINE dict is present in ui_server.py."""
    import pathlib as _pl
    src = (_pl.Path(__file__).resolve().parent.parent / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    assert "_QUESTION_TOPIC_TO_ENGINE" in src
    assert '"travel_fav": "travel"' in src or "'travel_fav': 'travel'" in src
    assert "_infer_wm_topic_engine" in src
    assert "_e4_engine_handoff" in src


@pytest.mark.parametrize("topic,expected_engine", [
    ("travel_fav",      "travel"),
    ("travel_where",    "travel"),
    ("travel_memorable","travel"),
    ("food_spicy",      "food"),
    ("food_fav",        "food"),
    ("place_from",      "place"),
    ("place_like",      "place"),
    ("work_what",       "work"),
    ("work_like",       "work"),
    ("family_size",     "family"),
    ("marriage",        "family"),
    ("hobby_what",      "hobby"),
])
def test_topic_to_engine_mapping(topic, expected_engine):
    srv = _load_server()
    assert srv._QUESTION_TOPIC_TO_ENGINE.get(topic) == expected_engine


@pytest.mark.parametrize("text,expected_engine", [
    ("你最喜欢哪个地方",  "travel"),
    ("你去过哪里旅游过",  "travel"),
    ("你喜欢辣吗",        "food"),
    ("你老家在哪里",      "place"),
    ("你做什么工作",      "work"),
    ("你家里有几口人",    "family"),
])
def test_infer_wm_topic_engine(text, expected_engine):
    srv = _load_server()
    assert srv._infer_wm_topic_engine(text) == expected_engine


def test_infer_wm_topic_engine_unknown_returns_none():
    srv = _load_server()
    assert srv._infer_wm_topic_engine("你多大了") is None
    assert srv._infer_wm_topic_engine("") is None


def test_e4_no_handoff_after_weak_fallback():
    """E4: no engine handoff when _counter_is_new_mirror and _counter_is_working_memory are both False."""
    import pathlib as _pl
    src = (_pl.Path(__file__).resolve().parent.parent / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    # Guard: handoff is conditioned on _counter_is_new_mirror OR _counter_is_working_memory
    e4_block = src.split("_e4_engine_handoff: Optional[str] = None")[1].split("# ── Mirror confusion state update")[0]
    assert "_counter_is_new_mirror" in e4_block
    assert "_counter_is_working_memory" in e4_block


def test_e4_handoff_emitted_to_state_update():
    """Static check: _e4_engine_handoff is written into state_update when set."""
    import pathlib as _pl
    src = (_pl.Path(__file__).resolve().parent.parent / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    # Locate the state_update emission block
    su_block = src.split('response["state_update"]["current_engine"] = _e4_engine_handoff')[0][-200:]
    assert "_e4_engine_handoff" in su_block


# ── G: Phase 11 Final — Fix 1: {TIME} slot safety net ────────────────────────

def test_time_slot_not_in_ui_server_source():
    """Static check: {TIME} fill safety net exists in slot-fill section."""
    import pathlib as _pl
    src = (_pl.Path(__file__).resolve().parent.parent / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    assert '"{TIME}"' in src or "'{TIME}'" in src, "No {TIME} safety net found"
    assert "最近" in src, "Safety net fallback 最近 missing"


# ── H: Phase 11 Final — Fix 2: Work/professor capture ────────────────────────

def _load_capture():
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location(
        "lmc_phase11",
        Path(__file__).resolve().parent.parent / "scripts" / "learner_memory_capture.py",
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("text,expected_job", [
    ("我退休了",                    "退休"),
    ("我退休了啊",                   "退休"),
    ("我以前是教授",                 "教授"),
    ("我以前是大学老师",             "大学老师"),
    ("我以前在大学教书",             "大学老师"),
    ("不是啊，我以前是教授",         "教授"),
    ("啊，我曾经是工程师",           "工程师"),
])
def test_extract_job_retirement_and_former_roles(text, expected_job):
    cap = _load_capture()
    job, _ = cap._extract_job_and_company_from_hanzi(text)
    assert job == expected_job, f"text={text!r}: got {job!r}, want {expected_job!r}"


# ── I: Phase 11 Final — Fix 3: City routing (question-clause priority) ────────

_PERSONA_CHENGDU = {
    "display_name": "建国",
    "profile": {"name": "建国", "hometown": "上海", "city": "上海"},
    "discoverable_facts": {"identity": "我叫建国，是因为我出生在建国后不久，家里人觉得这个名字有历史感。"},
    "discoverable_facts_en": {},
    "voice_lines": {},
    "voice_lines_en": {},
}


def test_city_routing_prefers_question_focus():
    """When question says '成都有什么特别？' after mentioning 上海, answer about 成都."""
    srv = _load_server()
    text = "我不喜欢上海，成都有什么特别？"
    answer = srv._direct_persona_answer(text, _PERSONA_CHENGDU)
    assert answer is not None
    assert "成都" in answer, f"Expected 成都 in answer, got: {answer!r}"
    assert "上海" not in answer or "成都" in answer


def test_city_routing_simple_chengdu_question():
    srv = _load_server()
    answer = srv._direct_persona_answer("成都有什么特别？", _PERSONA_CHENGDU)
    assert answer is not None
    assert "成都" in answer


# ── J: Phase 11 Final — Fix 4: Persona name-story routing ────────────────────

def test_name_story_by_actual_name_with_story():
    """'建国有一个故事吗？' should route to discoverable_facts['identity']."""
    srv = _load_server()
    ans = srv._direct_persona_answer("建国有一个故事吗？", _PERSONA_CHENGDU)
    assert ans is not None
    assert "建国" in ans or "历史" in ans or "家里" in ans


def test_name_story_why_called():
    """'为什么叫建国？' should route to discoverable_facts['identity']."""
    srv = _load_server()
    ans = srv._direct_persona_answer("为什么叫建国？", _PERSONA_CHENGDU)
    assert ans is not None
    assert "建国" in ans or "历史" in ans


def test_name_story_name_meaning_via_actual_name():
    """'建国这个名字有什么意思？' should route to discoverable_facts['identity']."""
    srv = _load_server()
    ans = srv._direct_persona_answer("建国这个名字有什么意思？", _PERSONA_CHENGDU)
    assert ans is not None
    assert "建国" in ans or "历史" in ans


# ── K: Phase 11 Final — Fix 6: Fallback overuse / unmatched question polish ──

@pytest.mark.parametrize("text", [
    "你那里叫什么名字？",
    "你那里叫什么名字",
    "你老家在哪？",
    "你老家在哪",
    "成都有什么特别？",
    "成都有什么特别",
])
def test_item6_questions_are_recognized(text):
    """All three audit example questions must be recognised as user questions."""
    srv = _load_server()
    ans = {"submitted_text": text, "frame_id": "f_home_where", "selected_option_hanzi": ""}
    assert srv._is_user_question(ans) is True, f"Not recognised as question: {text!r}"


@pytest.mark.parametrize("text", [
    "你那里叫什么名字？",
    "你那里叫什么名字",
])
def test_item6_nali_place_name_answered(text):
    """'你那里叫什么名字' must return the persona's city name, not None."""
    srv = _load_server()
    ans = srv._direct_persona_answer(text, _PERSONA_CHENGDU)
    assert ans is not None
    assert "上海" in ans or "住" in ans or "叫" in ans


def test_item6_laojia_answered():
    srv = _load_server()
    ans = srv._direct_persona_answer("你老家在哪", _PERSONA_CHENGDU)
    assert ans is not None
    assert "上海" in ans or "老家" in ans


def test_item6_chengdu_feature_answered():
    srv = _load_server()
    ans = srv._direct_persona_answer("成都有什么特别", _PERSONA_CHENGDU)
    assert ans is not None
    assert "成都" in ans
