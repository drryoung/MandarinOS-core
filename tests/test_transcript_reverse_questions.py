#!/usr/bin/env python3
"""
Transcript-based regression tests for learner-led reverse questions.

Asserts that _direct_persona_answer (and the broader _answer_user_question_prefix
path) returns:
  - non-None
  - non-empty
  - does not contain the meta-disclaimer '电脑角色'

Based on utterances observed in the beta_drryoung June 2026 session.
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
    spec = importlib.util.spec_from_file_location("ui_server_trq", _SCRIPTS / "ui_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_trq"] = mod
    spec.loader.exec_module(mod)
    _srv_cache["srv"] = mod
    return mod


# Persona fixture representing Jianguo (similar to the live session persona).
_PERSONA_JIANGUO = {
    "display_name": "建国",
    "profile": {
        "name": "建国",
        "age": 38,
        "hometown": "成都",
        "city": "北京",
        "occupation": "软件工程师",
    },
    "discoverable_facts": {
        "identity":    "我叫建国，是因为我出生在建国后不久，家里人觉得这个名字有历史感。",
        "work":        "我做软件工程师，主要做后端开发。",
        "work_origin": "做这份工作已经八年了，越做越有挑战。",
        "work_like":   "还挺喜欢的，每天都在解决新问题，很有成就感。",
        "family_live": "我和太太一起住，我爸妈在成都。",
        "family_siblings": "我有一个妹妹，在成都那边工作。",
    },
    "voice_lines": {
        "family": "我和太太一起住，我爸妈在成都。",
        "work_like": "还挺喜欢的，每天都在解决新问题。",
    },
    "voice_lines_en": {},
}


def _direct(text: str) -> str | None:
    srv = _load_server()
    return srv._direct_persona_answer(text, _PERSONA_JIANGUO)


def _prefix(text: str) -> tuple | None:
    srv = _load_server()
    ans = {"submitted_text": text, "frame_id": "f_what_work", "selected_option_hanzi": ""}
    return srv._answer_user_question_prefix(ans, _PERSONA_JIANGUO)


META = "电脑角色"


# ── Direct-answer assertions ───────────────────────────────────────────────────

@pytest.mark.parametrize("text,desc", [
    ("你做这个工作多久了？",  "work duration with 你 prefix"),
    ("做多久了？",            "bare work duration"),
    ("你做多久了？",          "你 + bare duration"),
    ("你做这份工作多久了？",  "这份工作 phrasing"),
])
def test_work_duration_direct_answer(text, desc):
    ans = _direct(text)
    assert ans is not None, f"[{desc}] got None for {text!r}"
    assert ans.strip(), f"[{desc}] empty string for {text!r}"
    assert META not in ans, f"[{desc}] meta fallback leaked into {ans!r}"


@pytest.mark.parametrize("text,desc", [
    ("你跟谁一起住？",  "跟谁一起住"),
    ("你和谁一起住？",  "和谁一起住"),
    ("你跟谁住？",      "跟谁住"),
])
def test_live_with_direct_answer(text, desc):
    ans = _direct(text)
    assert ans is not None, f"[{desc}] got None for {text!r}"
    assert META not in ans, f"[{desc}] meta fallback leaked"


@pytest.mark.parametrize("text,desc", [
    ("你姐姐多大？",        "sibling age"),
    ("你姐姐做什么工作？",  "sibling work"),
    ("你姐姐在哪里？",      "sibling location"),
])
def test_sibling_direct_answer(text, desc):
    ans = _direct(text)
    assert ans is not None, f"[{desc}] got None for {text!r}"
    assert ans.strip(), f"[{desc}] empty string for {text!r}"
    assert META not in ans, f"[{desc}] meta fallback leaked into {ans!r}"


@pytest.mark.parametrize("text,desc", [
    ("你喜欢这个工作吗？",  "like this work"),
    ("你喜欢你的工作吗？",  "like your work"),
])
def test_work_like_direct_answer(text, desc):
    ans = _direct(text)
    assert ans is not None, f"[{desc}] got None for {text!r}"
    assert META not in ans, f"[{desc}] meta fallback leaked"


def test_grandparent_location_direct_answer():
    ans = _direct("你奶奶住在哪儿？")
    assert ans is not None
    assert META not in ans


def test_name_meaning_direct_answer():
    ans = _direct("你的名字是什么意思？")
    assert ans is not None
    assert META not in ans
    # Should reference the identity fact
    assert "建国" in ans or "历史" in ans or "家里" in ans


# ── Prefix-path (full question pipeline) assertions ───────────────────────────

@pytest.mark.parametrize("text", [
    "你做这个工作多久了？",
    "你跟谁一起住？",
    "你姐姐多大？",
    "你奶奶住在哪儿？",
    "你的名字是什么意思？",
])
def test_full_prefix_path_returns_answer(text):
    result = _prefix(text)
    assert result is not None, f"No answer via prefix path for {text!r}"
    zh, _en = result
    assert zh and zh.strip(), f"Empty answer for {text!r}"
    assert META not in zh, f"Meta fallback leaked for {text!r}: {zh!r}"


# ── _persona_limitation_reply no longer contains 电脑角色 in normal path ──────

def test_limitation_reply_soft():
    srv = _load_server()
    reply = srv._persona_limitation_reply()
    assert META not in reply, f"Meta string should not appear in default reply: {reply!r}"


def test_limitation_reply_with_hint_soft():
    srv = _load_server()
    reply = srv._persona_limitation_reply("工作")
    assert META not in reply, f"Meta string should not appear in hinted reply: {reply!r}"
