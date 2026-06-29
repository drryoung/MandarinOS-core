#!/usr/bin/env python3
"""
Regression tests for learner-led follow-up question handling.

Covers failures observed in batch_2026-06-29_01:
  - Foreign-place feature questions (日本有什么特别的？, 法国有什么特别的？)
    → persona should answer from travel facts, not Beijing/generic fallback
  - Xi'an food question (西安有什么好吃的？)
    → meiling/Xi'an persona should give food answer, not history repeat
  - Shanghai food question (上海有什么好吃的？)
    → zhiyuan persona should give personal food answer
  - place_food mirror topic stub
    → _mirror_persona_stub("place_food") should return food facts, not generic
  - Working-memory place list includes foreign countries
    → 日本, 法国 appear in _WM_KNOWN_PLACES

Test rule: every answer must be non-None, non-empty, and not trigger
the meta-disclaimer '电脑角色'.  For persona-grounded checks, the answer
must contain persona-specific keywords.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"

_cache: dict = {}


def _load_server():
    if "srv" in _cache:
        return _cache["srv"]
    spec = importlib.util.spec_from_file_location("ui_server_llf", _SCRIPTS / "ui_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_llf"] = mod
    spec.loader.exec_module(mod)
    _cache["srv"] = mod
    return mod


META = "电脑角色"


# ── Persona fixtures ──────────────────────────────────────────────────────────

def _xiaoming():
    """xiaoming — has Japan + Thailand travel facts."""
    return {
        "display_name": "小明",
        "profile": {"age": 28, "city": "北京", "hometown": "成都", "occupation": "AI工程师"},
        "voice_lines": {"identity": "我叫小明。", "work": "我在AI公司做语音识别。"},
        "voice_lines_en": {},
        "discoverable_facts": {
            "identity": "我叫小明，是因为名字简单好记。",
            "work": "我在中关村一家AI公司做语音识别研究，已经三年了。",
            "travel": "我去过日本、泰国和韩国，最喜欢日本的拉面和温泉。",
            "travel_where": "我去过日本和泰国，最喜欢日本，拉面和温泉印象特别深。",
            "food": "我妈妈做的回锅肉是我最喜欢的，每次回成都都要吃。",
            "place_from": "我是成都人，不过在北京工作已经好几年了。",
            "place": "我老家是成都，但毕业后来北京工作，住在中关村附近。",
        },
        "discoverable_facts_en": {
            "travel": "I've been to Japan and Thailand.",
            "travel_where": "I've been to Japan and Thailand — Japan made the strongest impression.",
            "food": "My mum's twice-cooked pork is my favourite.",
        },
    }


def _zhiyuan():
    """zhiyuan — has France travel facts, Shanghai food facts."""
    return {
        "display_name": "志远",
        "profile": {"age": 38, "city": "上海", "hometown": "南京", "occupation": "家教老师"},
        "voice_lines": {"identity": "我叫志远。", "work": "我是家教老师。"},
        "voice_lines_en": {},
        "discoverable_facts": {
            "identity": "我叫志远，志是志向的志，远是远大的远。",
            "work": "我做数学和语文家教，已经十年了，在家里或图书馆上课。",
            "travel": "我去过几个欧洲国家，最喜欢法国，觉得他们对历史和艺术的态度和中国有相似之处。",
            "travel_where": "我去过法国和几个欧洲国家，最喜欢法国，觉得他们对历史和艺术的态度很有意思。",
            "food": "我觉得上海的本帮菜非常有特色，红烧肉和清蒸鱼是我最喜欢的，简单又有味道。",
            "place": "上海节奏很快，但我已经习惯了，周末去外滩或者博物馆走走，心情就会很好。",
            "place_from": "我老家是南京，不过在上海工作已经好几年了。南京的鸭血粉丝汤我很想念。",
        },
        "discoverable_facts_en": {
            "travel_where": "I've been to France and a few European countries — I like France best.",
            "food": "I think Shanghai's local cuisine is very distinctive.",
        },
    }


def _meiling():
    """meiling — native Xi'an, food facts and place facts."""
    return {
        "display_name": "美玲",
        "profile": {"age": 32, "city": "西安", "hometown": "西安", "occupation": "美术老师"},
        "voice_lines": {"identity": "我叫美玲。", "work": "我是美术老师。", "food": "我比较喜欢清淡的食物。"},
        "voice_lines_en": {},
        "discoverable_facts": {
            "identity": "美玲这个名字是我妈妈取的，她很喜欢梅花，所以取了'美'字。",
            "work": "我在西安一所中学教书，教的是初中美术，已经教了八年了。",
            "food": "我最喜欢西安的凉皮和肉夹馍，这是我从小吃到大的味道。",
            "place": "西安有很多历史遗迹，兵马俑、大雁塔都在我家附近，我觉得住在这里很自豪。",
            "place_from": "我是西安人，从小在那里长大。西安有很多有名的小吃，凉皮和肉夹馍是我从小吃到大的味道。",
            "travel": "我去过北京、苏州、成都，最喜欢苏州的园林，感觉非常有诗意。",
            "travel_where": "我去过北京和苏州，最喜欢苏州的园林，感觉非常有诗意。",
        },
        "discoverable_facts_en": {
            "food": "My favourites are Xi'an cold noodles and pork burgers.",
            "place": "Xi'an has many historical sites.",
        },
    }


def _jianguo():
    """jianguo — Chongqing native, chef, no Japan/France travel."""
    return {
        "display_name": "建国",
        "profile": {"age": 35, "city": "成都", "hometown": "重庆", "occupation": "厨师"},
        "voice_lines": {"identity": "我叫建国。", "work": "我是一名厨师。"},
        "voice_lines_en": {},
        "discoverable_facts": {
            "identity": "我叫建国，因为我出生的年份特别，家里取了这个名字。",
            "work": "我是一名川菜厨师，在成都一家餐厅工作，已经七年了。",
            "food": "重庆火锅是我最喜欢的，又辣又香！",
            "place": "重庆是山城，到处都是坡路，风景很特别。",
            "travel": "我去过西安和上海，想多了解各地的饮食文化。",
            "travel_where": "我去过西安和上海，觉得西安的历史文化很深厚。",
        },
        "discoverable_facts_en": {
            "food": "Chongqing hotpot is my favourite — spicy and delicious.",
        },
    }


# ── Helper functions ──────────────────────────────────────────────────────────

def _direct(text: str, persona: dict) -> str | None:
    srv = _load_server()
    return srv._direct_persona_answer(text, persona)


def _stub(topic: str, engine: str, persona: dict) -> tuple:
    srv = _load_server()
    return srv._mirror_persona_stub(topic, engine, persona)


# ── Fix 1: Japan feature question uses xiaoming's travel facts ─────────────────

class TestJapanFeatureQuestion:
    def test_japan_special_returns_non_none(self):
        ans = _direct("日本有什么特别的？", _xiaoming())
        assert ans is not None
        assert ans.strip()

    def test_japan_special_not_meta(self):
        ans = _direct("日本有什么特别的？", _xiaoming())
        assert META not in (ans or "")

    def test_japan_special_contains_travel_keyword(self):
        """Answer must reference Japan's features from travel facts, not Beijing."""
        ans = _direct("日本有什么特别的？", _xiaoming())
        assert ans is not None
        # Must NOT be about Beijing or generic
        assert "北京" not in ans, f"Got Beijing answer for Japan question: {ans!r}"
        # Must contain something Japan-specific from xiaoming's travel_where
        japan_keywords = ("日本", "拉面", "温泉")
        assert any(kw in ans for kw in japan_keywords), (
            f"Expected Japan-related keyword in: {ans!r}"
        )

    def test_japan_interesting_variant(self):
        ans = _direct("日本有什么有意思的？", _xiaoming())
        assert ans is not None
        assert META not in (ans or "")

    def test_japan_question_jianguo_no_travel_fact_graceful(self):
        """Jianguo has no Japan travel fact — should gracefully fall through to pool/fallback."""
        ans = _direct("日本有什么特别的？", _jianguo())
        assert ans is not None
        assert META not in (ans or "")
        assert ans.strip()


# ── Fix 2: France feature question uses zhiyuan's travel facts ────────────────

class TestFranceFeatureQuestion:
    def test_france_special_returns_non_none(self):
        ans = _direct("法国有什么特别的？", _zhiyuan())
        assert ans is not None
        assert ans.strip()

    def test_france_special_not_meta(self):
        ans = _direct("法国有什么特别的？", _zhiyuan())
        assert META not in (ans or "")

    def test_france_special_contains_travel_keyword(self):
        """Answer must come from zhiyuan's France travel facts, not Shanghai."""
        ans = _direct("法国有什么特别的？", _zhiyuan())
        assert ans is not None
        assert "上海" not in ans, f"Got Shanghai answer for France question: {ans!r}"
        france_keywords = ("法国", "历史", "艺术", "欧洲", "文化")
        assert any(kw in ans for kw in france_keywords), (
            f"Expected France-related keyword in: {ans!r}"
        )

    def test_france_interesting_variant(self):
        ans = _direct("法国有什么有意思的地方？", _zhiyuan())
        assert ans is not None
        assert META not in (ans or "")

    def test_france_question_meiling_no_travel_fact_graceful(self):
        """Meiling has no France travel fact — should fall through gracefully."""
        ans = _direct("法国有什么特别的？", _meiling())
        assert ans is not None
        assert META not in (ans or "")


# ── Fix 3: Xi'an food question gives food answer, not history repeat ──────────

class TestXianFoodQuestion:
    def test_xian_food_returns_non_none(self):
        ans = _direct("西安有什么好吃的？", _meiling())
        assert ans is not None
        assert ans.strip()

    def test_xian_food_not_meta(self):
        ans = _direct("西安有什么好吃的？", _meiling())
        assert META not in (ans or "")

    def test_xian_food_contains_food_keyword(self):
        """Meiling (Xi'an native) must give food answer, not history repeat."""
        ans = _direct("西安有什么好吃的？", _meiling())
        assert ans is not None
        food_keywords = ("凉皮", "肉夹馍", "好吃", "小吃", "味道", "泡馍")
        assert any(kw in ans for kw in food_keywords), (
            f"Expected Xi'an food keyword in: {ans!r}"
        )
        # Specifically must NOT repeat 'Xi'an is an ancient capital' as the answer
        ancient_capital_phrases = ("古都", "历史遗迹", "兵马俑", "大雁塔")
        assert not all(phrase in ans for phrase in ["兵马俑", "大雁塔"]), (
            f"Got history answer for food question: {ans!r}"
        )

    def test_xian_food_meiling_personal_answer(self):
        """Meiling's food fact is specifically about Xi'an food — should be used."""
        ans = _direct("西安有什么好吃的？", _meiling())
        assert ans is not None
        # Meiling's food fact mentions 凉皮 and 肉夹馍
        assert "凉皮" in ans or "肉夹馍" in ans or "好吃" in ans, (
            f"Expected meiling personal food fact in: {ans!r}"
        )

    def test_xian_food_variant_what_to_eat(self):
        ans = _direct("西安有什么吃的？", _meiling())
        assert ans is not None
        assert META not in (ans or "")

    def test_xian_food_non_native_persona_still_answers(self):
        """Jianguo (non-Xi'an native) visited Xi'an — should still give food pool answer."""
        ans = _direct("西安有什么好吃的？", _jianguo())
        assert ans is not None
        assert META not in (ans or "")
        food_keywords = ("凉皮", "肉夹馍", "小吃", "好吃", "西安")
        assert any(kw in ans for kw in food_keywords), (
            f"Expected Xi'an food keyword in jianguo answer: {ans!r}"
        )


# ── Fix 4: Shanghai food question uses zhiyuan's personal food fact ───────────

class TestShanghaiFoodQuestion:
    def test_shanghai_food_returns_non_none(self):
        ans = _direct("上海有什么好吃的？", _zhiyuan())
        assert ans is not None
        assert ans.strip()

    def test_shanghai_food_not_meta(self):
        ans = _direct("上海有什么好吃的？", _zhiyuan())
        assert META not in (ans or "")

    def test_shanghai_food_contains_food_keyword(self):
        """Zhiyuan (Shanghai resident) should give personal Shanghai food answer."""
        ans = _direct("上海有什么好吃的？", _zhiyuan())
        assert ans is not None
        food_keywords = ("本帮菜", "红烧肉", "清蒸鱼", "生煎", "小笼包", "好吃")
        assert any(kw in ans for kw in food_keywords), (
            f"Expected Shanghai food keyword in: {ans!r}"
        )


# ── Fix 5: place_food mirror topic stub ──────────────────────────────────────

class TestPlaceFoodMirrorStub:
    def test_place_food_stub_returns_non_generic(self):
        """place_food should no longer return the generic '我觉得都挺有意思的。'"""
        zh, en = _stub("place_food", "place", _meiling())
        assert zh is not None
        assert zh.strip()
        assert "都挺有意思的" not in zh, (
            f"place_food returned generic fallback: {zh!r}"
        )

    def test_place_food_stub_meiling_returns_food_fact(self):
        zh, en = _stub("place_food", "place", _meiling())
        food_keywords = ("凉皮", "肉夹馍", "西安", "好吃", "小吃", "清淡", "味道")
        assert any(kw in zh for kw in food_keywords), (
            f"Expected food keyword in meiling place_food stub: {zh!r}"
        )

    def test_place_food_stub_zhiyuan_returns_food_fact(self):
        zh, en = _stub("place_food", "place", _zhiyuan())
        food_keywords = ("本帮菜", "红烧肉", "清蒸鱼", "上海", "有特色", "好吃", "文化")
        assert any(kw in zh for kw in food_keywords), (
            f"Expected food keyword in zhiyuan place_food stub: {zh!r}"
        )

    def test_place_food_stub_no_persona_returns_graceful(self):
        zh, en = _stub("place_food", "place", None)
        assert zh is not None
        assert zh.strip()
        assert META not in zh


# ── Fix 6: _WM_KNOWN_PLACES includes foreign countries ───────────────────────

class TestWMKnownPlacesIncludesForeign:
    def test_japan_in_known_places(self):
        srv = _load_server()
        assert "日本" in srv._WM_KNOWN_PLACES, "日本 should be in _WM_KNOWN_PLACES"

    def test_france_in_known_places(self):
        srv = _load_server()
        assert "法国" in srv._WM_KNOWN_PLACES, "法国 should be in _WM_KNOWN_PLACES"

    def test_thailand_in_known_places(self):
        srv = _load_server()
        assert "泰国" in srv._WM_KNOWN_PLACES

    def test_working_memory_extracts_japan_mention(self):
        """If recent replies mention Japan, _extract_persona_facts_from_recent should find it."""
        srv = _load_server()
        recent = ["我去过日本，拉面特别好吃！", "温泉也很有意思。"]
        facts = srv._extract_persona_facts_from_recent(recent)
        assert "travel_visited" in facts, "Expected travel_visited in extracted facts"
        assert "日本" in facts["travel_visited"], (
            f"Expected 日本 in travel_visited, got: {facts.get('travel_visited')}"
        )


# ── General: no meta disclaimer in learner-led answers ───────────────────────

class TestNoMetaDisclaimerInFollowups:
    @pytest.mark.parametrize("text,persona_fn,desc", [
        ("日本有什么特别的？",  _xiaoming,  "Japan feature — xiaoming"),
        ("法国有什么特别的？",  _zhiyuan,   "France feature — zhiyuan"),
        ("西安有什么好吃的？",  _meiling,   "Xi'an food — meiling"),
        ("上海有什么好吃的？",  _zhiyuan,   "Shanghai food — zhiyuan"),
        ("你去过日本吗？",       _xiaoming,  "visited Japan question"),
        ("你多大了？",           _meiling,   "age question — meiling"),
        ("你结婚了吗？",         _jianguo,   "marriage question — jianguo"),
        ("你在哪里工作？",       _zhiyuan,   "work location — zhiyuan"),
        ("你喜欢旅行吗？",       _xiaoming,  "likes travel — xiaoming"),
    ])
    def test_no_meta_disclaimer(self, text, persona_fn, desc):
        ans = _direct(text, persona_fn())
        assert META not in (ans or ""), f"[{desc}] meta fallback leaked: {ans!r}"
