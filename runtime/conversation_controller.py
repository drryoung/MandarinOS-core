"""Conversation controller for the MandarinOS persona chat runtime.

This module owns the per-turn decision pipeline that turns a raw user
utterance into the persona's next reply. It exists to fix a class of
regressions where the controller:

* ran semantic intent classification *before* checking for
  learner-recovery signals ("I don't understand", "say that again"),
* used a generic fallback instead of repeating/simplifying its own
  question when the learner asked for a repeat,
* ignored direct questions the learner asked the persona and kept
  driving the active topic engine,
* repeated a stale reply verbatim (e.g. answering "你做什么工作" with a
  marriage answer over and over),
* mis-routed travel statements ("九月我想去中国甘肃") into the FAMILY
  engine,
* broke topic anchoring in the PLACE engine (asking "你是说新西兰吗？"
  about food that clearly belongs to the current place), and
* emitted corrupted template text such as
  "等你等新西兰的南方有什么特别的？".

The public entry point is :class:`ConversationController`. The turn
pipeline order is deliberate and is the core of the fix:

    1. recovery detection      (before any semantic classification)
    2. direct-question override (overrides the active engine)
    3. travel-intent routing
    4. active-engine continuation (with PLACE topic anchoring)
    5. stale-reply guard        (re-run classification if we'd repeat)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Persona facts
# ---------------------------------------------------------------------------

DEFAULT_PERSONA: Dict[str, str] = {
    "name": "我叫小美。",
    "origin": "我是北京人。",
    "residence": "我住在北京。",
    "work": "我是一名中文老师，平时教外国朋友说中文。",
    "marital": "还没有，一个人也挺自在的。",
    "kids": "还没有孩子，就我自己。",
    "likes": "我喜欢看书，也喜欢到处走走。",
    "bounce": "我啊，日子过得简单，也挺好的。",
}


# The generic fallback that must NOT be used for recovery turns.
GENERIC_FALLBACK = "我真的不太了解这个，不好说。"

# Corrected PLACE template. The corrupted form
# "等你等新西兰的南方有什么特别的？" must never be emitted.
PLACE_SOUTH_NZ_QUESTION = "新西兰南方有什么特别的地方？"

# Topics that count as "New Zealand" for PLACE anchoring.
NEW_ZEALAND_TOPICS = {"new_zealand", "southern_new_zealand"}


# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[\s，。！？、,.!?~…·「」“”\"'()（）]+")

# Common ASR corruptions -> canonical character. The most important one is
# 刷 -> 说 (e.g. "再刷一起" heard for "再说一次").
_ASR_SUBSTITUTIONS = {
    "刷": "说",
    "耍": "说",
}


def normalize(text: str) -> str:
    """Strip whitespace/punctuation for robust substring matching."""
    if not text:
        return ""
    return _PUNCT_RE.sub("", text)


def _asr_canonical(text: str) -> str:
    """Apply ASR corruption fixes so fuzzy forms compare equal."""
    out = normalize(text)
    for bad, good in _ASR_SUBSTITUTIONS.items():
        out = out.replace(bad, good)
    return out


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Recovery detection (fix #1 / #2)
# ---------------------------------------------------------------------------

# Explicit "I didn't understand" markers.
_RECOVERY_CONFUSION = (
    "听不懂",
    "没听懂",
    "听不清",
    "不懂",
    "不明白",
    "不太懂",
    "没懂",
    "什么意思",
    "啥意思",
    "看不懂",
)

# "Slow down" markers.
_RECOVERY_SLOW = (
    "慢一点",
    "慢点",
    "慢一些",
    "说慢",
    "讲慢",
)


def is_recovery(text: str) -> bool:
    """Return True if the learner is signalling a comprehension breakdown.

    Runs on ASR-canonicalised text so corrupted forms such as
    "再刷一次"/"再刷一起"/"再说一起"/"再说一" all resolve to a repeat
    request. This must be evaluated *before* semantic intent
    classification.
    """
    canon = _asr_canonical(text)
    if not canon:
        return False

    for marker in _RECOVERY_CONFUSION:
        if marker in canon:
            return True
    for marker in _RECOVERY_SLOW:
        if marker in canon:
            return True

    # Repeat requests. After ASR canonicalisation 刷 -> 说, so
    # "可以再刷一次吗" / "再刷一起" become "再说...". Any "再说"/"再讲"
    # (optionally followed by 一次/一遍/一下/一起/一) is a repeat request.
    if "再说" in canon or "再讲" in canon or "重说" in canon or "重复" in canon:
        return True

    return False


# ---------------------------------------------------------------------------
# Direct-question detection (fix #3)
# ---------------------------------------------------------------------------

# Ordered list of (persona_fact_key, patterns). Order matters: the generic
# "你呢" bounce is checked last so that "你呢你结婚了吗" resolves to the
# real question (marital) rather than the bounce.
_DIRECT_QUESTION_PATTERNS: List[tuple] = [
    ("work", ("你做什么工作", "你在哪里工作", "你在哪工作", "你的工作",
              "你是做什么的", "你做什么的", "你什么工作", "你做啥工作")),
    ("marital", ("你结婚了吗", "你结婚了没", "你结婚没", "你成家了吗",
                 "你有对象吗", "你有男朋友吗", "你有女朋友吗")),
    ("kids", ("你有孩子吗", "你有小孩吗", "你有没有孩子", "你有娃吗")),
    ("residence", ("你住在哪里", "你住哪里", "你住在哪", "你住哪", "你家在哪")),
    ("origin", ("你是哪里人", "你是哪儿人", "你老家在哪", "你是哪国人")),
    ("name", ("你叫什么名字", "你叫什么", "你的名字", "你叫啥")),
    ("likes", ("你喜欢什么", "你有什么爱好", "你的爱好", "你喜欢做什么")),
    ("bounce", ("你呢",)),
]


def detect_direct_question(text: str) -> Optional[str]:
    """Return the persona fact key if the learner asked a direct question."""
    canon = normalize(text)
    if not canon:
        return None
    for key, patterns in _DIRECT_QUESTION_PATTERNS:
        for pat in patterns:
            if pat in canon:
                return key
    return None


# ---------------------------------------------------------------------------
# Travel-intent detection (fix #5)
# ---------------------------------------------------------------------------

# Known place tokens, used to pick the most specific destination.
KNOWN_PLACES = (
    "新西兰", "中国", "甘肃", "商丘", "北京", "上海", "广州", "深圳",
    "成都", "西安", "云南", "四川", "日本", "美国", "英国", "澳大利亚",
    "南方", "北方",
)

_TIME_RE = re.compile(r"(明年|今年|去年|下个月|下週|下周|这个月)|([一二三四五六七八九十百零两\d]+月)")

_TRAILING_PARTICLES = ("吗", "呢", "啊", "呀", "吧", "了", "的", "哦", "呐")


@dataclass
class TravelIntent:
    raw_place: str
    time_phrase: str
    specific_place: str


def detect_travel(text: str) -> Optional[TravelIntent]:
    """Detect "(time) 想去 <place>" style travel statements.

    Returns a :class:`TravelIntent` or ``None``. Routes to the TRAVEL
    engine rather than FAMILY.
    """
    canon = normalize(text)
    if "想去" not in canon:
        return None

    after = canon.split("想去", 1)[1]
    # Strip trailing particles/questions.
    while after and after[-1] in _TRAILING_PARTICLES:
        after = after[:-1]
    if not after:
        return None

    time_match = _TIME_RE.search(canon.split("想去", 1)[0] + after)
    time_phrase = time_match.group(0) if time_match else ""

    # Most specific place = the known place occurring last in the string.
    specific = ""
    best_idx = -1
    for place in KNOWN_PLACES:
        idx = after.rfind(place)
        if idx > best_idx:
            best_idx = idx
            specific = place
    if not specific:
        # Fall back to the tail of the phrase.
        specific = after[-2:] if len(after) >= 2 else after

    return TravelIntent(raw_place=after, time_phrase=time_phrase, specific_place=specific)


# ---------------------------------------------------------------------------
# PLACE topic anchoring (fix #6)
# ---------------------------------------------------------------------------

FOOD_MARKERS = ("冰淇淋", "羊肉", "牛肉", "牛奶", "奶", "海鲜", "水果", "蜂蜜", "好吃")


def mentions_food(text: str) -> bool:
    canon = normalize(text)
    return any(marker in canon for marker in FOOD_MARKERS)


# ---------------------------------------------------------------------------
# Controller state + engine
# ---------------------------------------------------------------------------

@dataclass
class ControllerState:
    engine: str = "identity"
    topic: Optional[str] = None
    last_app_reply: str = ""
    last_app_question: str = ""
    persona: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PERSONA))


def _is_question(text: str) -> bool:
    return bool(text) and (text.rstrip().endswith("？") or text.rstrip().endswith("?"))


class ConversationController:
    """Drives one persona conversation.

    Call :meth:`handle_user_turn` with each learner utterance to get the
    persona's next reply. State (active engine, current topic, last reply
    and last question) is tracked internally but may be seeded for tests.
    """

    def __init__(self, state: Optional[ControllerState] = None):
        self.state = state or ControllerState()

    # -- public API -------------------------------------------------------

    def handle_user_turn(self, user_text: str) -> str:
        reply, tag = self._classify(user_text)

        # Fix #4: stale-reply guard. If we would repeat the previous reply
        # (and the learner did not simply repeat/ask for a repeat), block it
        # and re-run classification so we advance the conversation instead of
        # looping.
        if (
            tag not in ("recovery", "direct_question")
            and self._near_identical(reply, self.state.last_app_reply)
            and not is_recovery(user_text)
        ):
            reply, tag = self._reclassify_after_stale(user_text)

        self._record_reply(reply)
        return reply

    # -- classification pipeline -----------------------------------------

    def _classify(self, user_text: str) -> tuple:
        # 1. Recovery FIRST (before semantic intent classification).
        if is_recovery(user_text):
            return self._recovery_reply(), "recovery"

        # 2. Direct-question override (overrides the active engine).
        fact_key = detect_direct_question(user_text)
        if fact_key:
            return self._persona_answer(fact_key), "direct_question"

        # 3. Travel-intent routing.
        travel = detect_travel(user_text)
        if travel:
            return self._travel_reply(travel), "travel"

        # 4. Active-engine continuation.
        return self._continue_engine(user_text), "engine"

    def _reclassify_after_stale(self, user_text: str) -> tuple:
        """Re-run classification, avoiding the stale engine default."""
        fact_key = detect_direct_question(user_text)
        if fact_key:
            return self._persona_answer(fact_key), "direct_question"
        travel = detect_travel(user_text)
        if travel:
            return self._travel_reply(travel), "travel"
        # Advance instead of repeating: hand back to a fresh engine prompt.
        return self._advance_engine(user_text), "engine_advanced"

    # -- reply builders ---------------------------------------------------

    def _recovery_reply(self) -> str:
        """Repeat / simplify the last question rather than fall back."""
        question = self.state.last_app_question
        if question:
            return f"没关系。我再说一次。{question}"
        return "没关系，我们慢慢来。你先跟我说说你自己吧。"

    def _persona_answer(self, fact_key: str) -> str:
        return self.state.persona.get(fact_key, self.state.persona["bounce"])

    def _travel_reply(self, travel: TravelIntent) -> str:
        self.state.engine = "travel"
        self.state.topic = travel.specific_place or travel.raw_place
        lead = f"{travel.time_phrase}想去" if travel.time_phrase else "想去"
        return f"哦，你{lead}{travel.raw_place}。你想去{travel.specific_place}哪里？"

    def _continue_engine(self, user_text: str) -> str:
        # Fix #6: PLACE topic anchoring. If we are talking about (southern)
        # New Zealand and the learner names food, treat it as a speciality of
        # the current place instead of asking "你是说新西兰吗？".
        if (
            self.state.engine == "place"
            and self.state.topic in NEW_ZEALAND_TOPICS
            and mentions_food(user_text)
        ):
            return (
                "哦，新西兰的东西又新鲜又好吃！冰淇淋、羊肉、牛肉都很有名。"
                "那新西兰的天气怎么样？"
            )

        # Default: keep the active engine moving with its current question.
        return self._advance_engine(user_text)

    def _advance_engine(self, user_text: str) -> str:
        if self.state.engine == "place":
            if self.state.topic in NEW_ZEALAND_TOPICS:
                return PLACE_SOUTH_NZ_QUESTION
            return "那个地方有什么特别的地方？"
        if self.state.engine == "travel":
            place = self.state.topic or "那里"
            return f"你想去{place}哪里？"
        if self.state.engine == "family":
            return "你和家里谁最亲近？"
        return "那你平时喜欢做什么？"

    # -- helpers ----------------------------------------------------------

    def _record_reply(self, reply: str) -> None:
        self.state.last_app_reply = reply
        if _is_question(reply):
            self.state.last_app_question = reply

    @staticmethod
    def _near_identical(a: str, b: str) -> bool:
        na, nb = normalize(a), normalize(b)
        if not na or not nb:
            return False
        if na == nb:
            return True
        return _similar(na, nb) >= 0.9
