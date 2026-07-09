#!/usr/bin/env python3
"""
Regression: stale marriage counter_reply must not loop when the learner asks
a different direct persona question (e.g. 你做什么工作).

Scenario:
  1. USER: 你呢你结婚了吗  →  APP: 还没有，一个人也挺自在的。
  2. USER: 你做什么工作     →  APP: work facts (NOT the marriage line again)
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
_UI_SERVER = _SCRIPTS / "ui_server.py"

_srv_cache: dict = {}

MARRIAGE_REPLY = "还没有，一个人也挺自在的。"
WORK_QUESTION = "你做什么工作"
MARRIAGE_QUESTION = "你呢你结婚了吗"

_WORK_KEYWORDS = ("老师", "工作", "美术", "教", "职业", "上班")


def _load_server():
    if "srv" in _srv_cache:
        return _srv_cache["srv"]
    spec = importlib.util.spec_from_file_location("ui_server_scrl", _UI_SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_scrl"] = mod
    spec.loader.exec_module(mod)
    _srv_cache["srv"] = mod
    return mod


def _meiling():
    srv = _load_server()
    return srv._resolve_persona("meiling")


def _simulate_stale_counter_reply(
    user_text: str,
    *,
    prev_counter_reply: str,
    last_mirror_topic: str = "marriage",
    last_mirror_engine: str = "family",
    mirror_confusion_count: int = 0,
    frame_id: str = "f_what_work",
) -> tuple[str, str] | None:
    """
    Mirror the live counter-reply routing path for a turn with stale
    last_counter_reply from the previous persona answer.
    """
    srv = _load_server()
    persona = _meiling()
    last_answer = {
        "submitted_text": user_text,
        "selected_option_hanzi": user_text,
        "frame_id": frame_id,
    }
    user_asked_question = srv._is_user_question(last_answer)
    _last_text_for_counter = user_text
    _prev_counter_reply = prev_counter_reply
    _recent_persona_replies = [prev_counter_reply]
    _cs_mirror_topic = last_mirror_topic
    _cs_mirror_engine = last_mirror_engine
    _cs_mirror_conf = mirror_confusion_count

    _counter_result = None
    _counter_is_new_mirror = False

    if srv._is_direct_persona_question(_last_text_for_counter) and not srv._is_confusion_signal(
        _last_text_for_counter
    ):
        _stale_override = srv._answer_user_question_prefix(
            last_answer,
            persona,
            recent_replies=_recent_persona_replies,
            context_reply="",
        )
        if (
            _stale_override
            and (_stale_override[0] or "").strip()
            and (_stale_override[0] or "").strip() != _prev_counter_reply.strip()
        ):
            _counter_result = _stale_override
            _raw_m = srv._find_mirror_answer(_last_text_for_counter, "", persona)
            if _raw_m and len(_raw_m) == 4:
                _counter_is_new_mirror = True

    if _counter_result is None and (
        _prev_counter_reply
        and _last_text_for_counter
        and srv._is_confusion_signal(_last_text_for_counter)
        and not user_asked_question
        and not srv._is_direct_persona_question(_last_text_for_counter)
        and _cs_mirror_topic
    ):
        if _cs_mirror_conf == 0:
            _counter_result = srv._mirror_restate_naturally(
                _prev_counter_reply, _cs_mirror_topic
            )

    if _counter_result is None and user_asked_question:
        _raw_mirror = srv._find_mirror_answer(_last_text_for_counter, "", persona)
        if _raw_mirror and len(_raw_mirror) == 4:
            _counter_result = (_raw_mirror[0], _raw_mirror[1])
        else:
            _prefix_context = (
                "" if srv._is_direct_persona_question(_last_text_for_counter or "")
                else _prev_counter_reply
            )
            _counter_result = srv._answer_user_question_prefix(
                last_answer,
                persona,
                recent_replies=_recent_persona_replies,
                context_reply=_prefix_context,
            )

    if _counter_result is None:
        return None

    zh = (_counter_result[0] or "").strip()
    if zh == _prev_counter_reply:
        zh = srv._persona_deflect("generic", zh)
    return (zh, _counter_result[1] or "")


# ── Marriage setup ─────────────────────────────────────────────────────────────

def test_marriage_question_produces_expected_reply():
    srv = _load_server()
    persona = _meiling()
    result = srv._answer_user_question_prefix(
        {"submitted_text": MARRIAGE_QUESTION, "frame_id": "f_married"},
        persona,
    )
    assert result is not None
    zh, _en = result
    assert MARRIAGE_REPLY in zh


# ── Stale-state override ─────────────────────────────────────────────────────

def test_work_question_after_marriage_not_stale_loop():
    result = _simulate_stale_counter_reply(
        WORK_QUESTION,
        prev_counter_reply=MARRIAGE_REPLY,
        last_mirror_topic="marriage",
        last_mirror_engine="family",
    )
    assert result is not None, "expected a counter_reply for work question"
    zh, _en = result
    assert MARRIAGE_REPLY not in zh, f"stale marriage answer leaked: {zh!r}"
    assert any(kw in zh for kw in _WORK_KEYWORDS), f"expected work facts, got: {zh!r}"


def test_work_question_detected_as_direct_persona_question():
    srv = _load_server()
    assert srv._is_direct_persona_question(WORK_QUESTION) is True


def test_mirror_restate_blocked_for_direct_work_question():
    """Without override, mirror stage-1 would prepend to the marriage answer."""
    srv = _load_server()
    restated = srv._mirror_restate_naturally(MARRIAGE_REPLY, "marriage")
    assert MARRIAGE_REPLY in restated[0]

    result = _simulate_stale_counter_reply(
        WORK_QUESTION,
        prev_counter_reply=MARRIAGE_REPLY,
        last_mirror_topic="marriage",
        mirror_confusion_count=0,
    )
    assert result is not None
    assert result[0] != restated[0]
    assert MARRIAGE_REPLY not in result[0]


@pytest.mark.parametrize("work_q", [
    "你做什么工作",
    "你做什么工作啊",
])
def test_work_question_variants_not_stale(work_q: str):
    result = _simulate_stale_counter_reply(
        work_q,
        prev_counter_reply=MARRIAGE_REPLY,
    )
    assert result is not None
    assert MARRIAGE_REPLY not in result[0]
    assert any(kw in result[0] for kw in _WORK_KEYWORDS)


# ── Static guard in live routing path ────────────────────────────────────────

def test_server_has_stale_counter_reply_override():
    src = _UI_SERVER.read_text(encoding="utf-8")
    assert "def _is_direct_persona_question" in src
    assert "Stale counter_reply override" in src
    # Fix (post-ffc806c): stale override now calls _direct_persona_answer directly
    # instead of routing through _answer_user_question_prefix, so context_reply=""
    # is no longer present in this block.  Check for the corrected direct call instead.
    assert "_so_raw = _direct_persona_answer(" in src, (
        "Stale override must call _direct_persona_answer directly, not _answer_user_question_prefix"
    )
    assert "not _is_direct_persona_question(_last_text_for_counter)" in src
