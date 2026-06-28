#!/usr/bin/env python3
"""
Transcript-based regression tests — conversation quality wave 2.

Covers:
  P1 — recovery phrases (再说一遍/再说一起 etc.) not routed to persona limitation
  P2 — personal location questions prepend personal answer before city description
  P3 — family presence questions (你有姐妹吗？ etc.) use grounded facts
  P4 — hobby follow-up questions (duration, origin, best, why) use discoverable_facts

Based on latest beta_drryoung session (June 2026).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"

_srv_cache: dict = {}


def _load_server():
    if "srv" in _srv_cache:
        return _srv_cache["srv"]
    spec = importlib.util.spec_from_file_location("ui_server_cq2", _SCRIPTS / "ui_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_cq2"] = mod
    spec.loader.exec_module(mod)
    _srv_cache["srv"] = mod
    return mod


# Jianguo persona — includes rich hobby, family, and location facts.
_PERSONA = {
    "display_name": "建国",
    "profile": {
        "name": "建国",
        "age": 38,
        "hometown": "重庆",
        "city": "北京",
        "occupation": "主厨",
    },
    "discoverable_facts": {
        "identity":       "建国这个名字听起来很老派，但其实我爸爸就是因为喜欢这个名字才给我取的。",
        "family":         "我家里有四个兄弟姐妹，我是老二，我妈妈做菜一绝，我学厨师也是受她影响。",
        "family_size":    "我家人可多了，一大家子加起来十几口，每次聚餐特别热闹！",
        "family_siblings":"我家有四个兄弟姐妹，我是老二！",
        "family_live":    "我们各自住，但大家都在重庆，平时也经常走动。",
        "hobby":          "我打羽毛球打了快二十年了，以前代表学校参加过比赛，现在每周至少打两次。",
        "hobby_best":     "打羽毛球最好玩的是遇到一个势均力敌的对手，每一球都很紧张，打完很爽！",
        "hobby_origin":   "小学加入了学校的羽毛球队，教练很严格，打了几年就越来越喜欢了，现在停不下来。",
        "work":           "我在重庆一家川菜馆做主厨，已经做了七年了。",
        "work_origin":    "小时候看妈妈做菜觉得很神奇，后来去了厨师学校，出来就进餐厅工作了。",
        "work_like":      "很喜欢，每次客人吃完说好吃，我就特别满足。",
    },
    "voice_lines": {
        "family": "我们各自住，但大家都在重庆，平时也经常走动。",
        "hobby":  "我喜欢打羽毛球，下班后常常去打。",
        "work_like": "很喜欢，每次客人吃完说好吃，我就特别满足。",
    },
    "voice_lines_en": {},
}

META = "电脑角色"
BAD_PHRASES = (META, "你可以问问别人", "这个我不太清楚。\n", "我不太了解这个，不好说")


def _direct(text: str):
    return _load_server()._direct_persona_answer(text, _PERSONA)


def _is_confusion(text: str) -> bool:
    return _load_server()._is_confusion_signal(text)


# ── P1 — Recovery / confusion signal detection ────────────────────────────────

@pytest.mark.parametrize("text", [
    "再说一遍",
    "再说一次",
    "再说一起",
    "再说一下",
    "再说一起可以吗",
    "再说一次可以吗",
    "请再说一遍",
    "我听不懂",
    "听不懂",
    "我不明白",
])
def test_confusion_signal_detected(text):
    """`_is_confusion_signal` must return True for all recovery/repeat phrasings."""
    assert _is_confusion(text), f"Expected confusion signal for {text!r}"


def test_confusion_signal_not_detected_for_real_question():
    """Genuine content questions must NOT be flagged as confusion."""
    assert not _is_confusion("你是哪里人？")
    assert not _is_confusion("你有什么爱好？")
    assert not _is_confusion("你老家在哪里？")


def test_confusion_signal_early_exit_in_answer_prefix():
    """_answer_user_question_prefix must return None (not persona limitation) for confusion signals."""
    srv = _load_server()
    answer = {"submitted_text": "再说一起可以吗？", "frame_id": "f_what_work", "selected_option_hanzi": ""}
    result = srv._answer_user_question_prefix(answer, _PERSONA)
    # Must return None so run_turn routes to _clarify_app_question instead.
    assert result is None, f"Expected None for confusion signal, got {result!r}"


@pytest.mark.parametrize("confusion_text", [
    "再说一遍？",
    "再说一次可以吗？",
    "再说一起？",
    "什么意思？",
])
def test_confusion_with_question_mark_not_hitting_limitation(confusion_text):
    """Confusion signals WITH ? must not return persona limitation from _answer_user_question_prefix."""
    srv = _load_server()
    answer = {"submitted_text": confusion_text, "frame_id": "f_what_work", "selected_option_hanzi": ""}
    result = srv._answer_user_question_prefix(answer, _PERSONA)
    assert result is None, f"Expected None for {confusion_text!r}, got {result!r}"


# ── P2 — Personal location answer shape ───────────────────────────────────────

@pytest.mark.parametrize("text,persona_marker,desc", [
    ("你住在哪里啊",  "我住在",  "current city question"),
    ("你住在哪儿",   "我住在",  "你住在哪儿 variant"),
    ("你老家在哪儿",  "我老家在", "hometown question"),
    ("你的老家在哪儿", "我老家在", "你的老家 phrasing"),
])
def test_personal_location_answer_starts_with_personal(text, persona_marker, desc):
    """Location answers must start with a personal statement, not just a city description."""
    srv = _load_server()
    # _place_followup_reply is called inside _answer_user_question_prefix so test via that.
    answer = {"submitted_text": text, "frame_id": "f_live_where", "selected_option_hanzi": ""}
    result = srv._answer_user_question_prefix(answer, _PERSONA)
    assert result is not None, f"[{desc}] got None for {text!r}"
    zh = result[0]
    assert zh.startswith(persona_marker) or persona_marker in zh[:15], (
        f"[{desc}] Expected answer to start with '{persona_marker}', got: {zh!r}"
    )


def test_location_no_bare_city_description():
    """'你住在哪里' must not return a bare city description without personal prefix."""
    srv = _load_server()
    answer = {"submitted_text": "你住在哪里啊", "frame_id": "f_live_where", "selected_option_hanzi": ""}
    result = srv._answer_user_question_prefix(answer, _PERSONA)
    if result:
        zh = result[0]
        # Must not START with a city description (no "X在中国" without preceding 我住在/我老家在)
        import re
        bare_city_pattern = re.compile(r"^[^\u4e00-\u9fff]*[\u4e00-\u9fff]{2,4}在中国")
        assert not bare_city_pattern.match(zh), f"Bare city description without personal prefix: {zh!r}"


# ── P3 — Family presence questions ────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_contains,desc", [
    ("你有姐妹吗",     "兄弟姐妹",  "has siblings — should mention 兄弟姐妹"),
    ("你有没有姐妹",   "兄弟姐妹",  "有没有 variant"),
    ("你有兄弟吗",     "兄弟姐妹",  "asking about brothers"),
    ("你有没有兄弟",   "兄弟姐妹",  "有没有 brothers variant"),
    ("你有爸爸妈妈吗", "爸妈",      "asking about parents — should answer 有的/爸妈/父母"),
])
def test_family_presence_question_uses_facts(text, expected_contains, desc):
    ans = _direct(text)
    assert ans is not None, f"[{desc}] got None for {text!r}"
    assert META not in ans, f"[{desc}] meta fallback for {text!r}"
    # "你有爸爸妈妈吗" may say "爸妈" or "他们大概X多岁"
    if "爸爸妈妈" in text:
        assert any(kw in ans for kw in ("有", "爸", "妈", "父母")), (
            f"[{desc}] Expected acknowledgment of parents, got {ans!r}"
        )
    else:
        assert expected_contains in ans or any(kw in ans for kw in ("兄弟", "姐妹", "老二", "兄弟姐妹")), (
            f"[{desc}] Expected sibling fact in {ans!r}"
        )


def test_family_members_location():
    ans = _direct("你的家人在哪里？")
    assert ans is not None
    assert META not in ans
    assert any(kw in ans for kw in ("重庆", "北京", "家人", "住"))


# ── P4 — Hobby follow-up handling ─────────────────────────────────────────────

def test_hobby_duration_play_variant():
    ans = _direct("你玩这个多久了？")
    assert ans is not None
    assert META not in ans
    # Jianguo's hobby fact mentions 二十年
    assert any(kw in ans for kw in ("二十年", "年", "多久", "喜欢"))


def test_hobby_duration_practice_variant():
    ans = _direct("你练这个多久了？")
    assert ans is not None
    assert META not in ans


def test_hobby_how_started():
    ans = _direct("你是怎么开始这个爱好的？")
    assert ans is not None
    assert META not in ans
    # Jianguo's hobby_origin mentions 小学
    assert any(kw in ans for kw in ("小学", "教练", "学校", "小时候", "接触", "喜欢上"))


def test_hobby_best_part():
    ans = _direct("你最喜欢这个爱好的哪一点？")
    assert ans is not None
    assert META not in ans
    # Jianguo's hobby_best mentions 对手/紧张/爽
    assert any(kw in ans for kw in ("对手", "紧张", "爽", "好玩", "放松", "感觉"))


def test_hobby_why_like():
    ans = _direct("你为什么喜欢这个爱好？")
    assert ans is not None
    assert META not in ans


def test_hobby_what_existing():
    """Existing 你平时喜欢做什么 handler still works."""
    ans = _direct("你平时喜欢做什么？")
    assert ans is not None
    assert META not in ans
    # Should mention hobby (羽毛球 or 喜欢)
    assert any(kw in ans for kw in ("羽毛球", "爱好", "喜欢"))


# ── P1 static check — source contains all required confusion markers ───────────

def test_confusion_markers_in_source():
    src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    for marker in ("再说一次", "再说一起", "再说一下", "请再说"):
        assert marker in src, f"Missing confusion marker: {marker!r}"


def test_answer_prefix_early_exit_in_source():
    src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    assert "_is_confusion_signal(t)" in src
    # The early-exit must appear before _place_followup_reply call
    prefix_fn = src.split("def _answer_user_question_prefix")[1].split("def _place_followup_reply")[0]
    assert "_is_confusion_signal(t)" in prefix_fn


def test_confusion_question_mark_branch_in_source():
    src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    assert "_confusion_about_app_q = True" in src
    # The new branch must be in run_turn (after _answer_user_question_prefix call)
    assert "_caq_c" in src


def test_personal_location_prepend_in_source():
    src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    assert "_PERSONA_LOC_MARKERS" in src
    assert "_is_persona_loc_q" in src
    assert "_personal_prefix" in src
