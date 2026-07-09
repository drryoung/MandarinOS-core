#!/usr/bin/env python3
"""
Regression: no learner-facing Chinese text should contain the raw placeholder ___.

Covers three leak paths:
  1. Sentence options built by _build_sentence_options() when memory slots
     (name, city, food) are blank — the option must be skipped, not emitted
     as '我叫___。'.
  2. NAME echo reaction prefix when learner_name in memory is '___' — must not
     produce '___！你名字有什么故事吗？'.
  3. {CITY}/{PLACE}/{HOMETOWN} frame-text safety net — verified via static source
     check that the net uses context-aware generics, not bare '___'.

Also checks that response_patterns.json templates with ___ are skipped (not
emitted) when memory is empty, and that all slot tokens have guards.
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
_UI_SERVER = ROOT / "scripts" / "ui_server.py"
_RESPONSE_PATTERNS = ROOT / "content" / "response_patterns.json"

_srv_cache: dict = {}


# ─────────────────────────────────────────────────────────────────────────────
# Module loader (cached)
# ─────────────────────────────────────────────────────────────────────────────


def _load_server():
    if "srv" in _srv_cache:
        return _srv_cache["srv"]
    spec = importlib.util.spec_from_file_location("ui_server_bsg", _UI_SERVER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_bsg"] = mod
    spec.loader.exec_module(mod)
    _srv_cache["srv"] = mod
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests: _build_sentence_options()
# ─────────────────────────────────────────────────────────────────────────────


class TestSentenceOptionsNoBlank:
    """_build_sentence_options() must not emit ___ when memory is empty."""

    def _call(self, text: str, memory: Optional[dict] = None):
        srv = _load_server()
        return srv._build_sentence_options({"text": text}, memory=memory)

    def test_name_question_empty_memory(self):
        """叫什么名字 pattern — no ___ when learner_name not in memory."""
        opts = self._call("你叫什么名字？", memory={})
        for o in opts:
            assert "___" not in o["zh"], f"___ in option: {o['zh']!r}"

    def test_name_question_none_memory(self):
        """叫什么名字 pattern — no ___ when memory is None."""
        opts = self._call("你叫什么名字？", memory=None)
        for o in opts:
            assert "___" not in o["zh"], f"___ in option: {o['zh']!r}"

    def test_city_question_empty_memory(self):
        """住哪里 pattern — no ___ when lives_in not in memory."""
        opts = self._call("你住哪里？", memory={})
        for o in opts:
            assert "___" not in o["zh"], f"___ in option: {o['zh']!r}"

    def test_food_question_empty_memory(self):
        """喜欢吃什么 pattern — no ___ when favourite_food not in memory."""
        opts = self._call("你喜欢吃什么？", memory={})
        for o in opts:
            assert "___" not in o["zh"], f"___ in option: {o['zh']!r}"

    def test_famous_dish_question_empty_memory(self):
        """最有名的菜 pattern — no ___ when no food memory (___最有名。 must be skipped)."""
        opts = self._call("你们那里最有名的菜是什么？", memory={})
        for o in opts:
            assert "___" not in o["zh"], f"___ in option: {o['zh']!r}"

    def test_travel_question_empty_memory(self):
        """去过哪 pattern — no ___ when no city memory."""
        opts = self._call("你去过哪些地方？", memory={})
        for o in opts:
            assert "___" not in o["zh"], f"___ in option: {o['zh']!r}"

    def test_name_filled_when_memory_present(self):
        """When learner_name is known, ___ in name template is replaced correctly."""
        opts = self._call("你叫什么名字？", memory={"learner_name": "王芳"})
        zh_list = [o["zh"] for o in opts]
        assert any("王芳" in zh for zh in zh_list), (
            f"Expected 王芳 in at least one option; got {zh_list}"
        )
        for zh in zh_list:
            assert "___" not in zh, f"___ survived despite name in memory: {zh!r}"

    def test_city_filled_when_memory_present(self):
        """When lives_in is known, city slot is replaced correctly."""
        opts = self._call("你住哪里？", memory={"lives_in": "上海"})
        zh_list = [o["zh"] for o in opts]
        assert any("上海" in zh for zh in zh_list), (
            f"Expected 上海 in at least one option; got {zh_list}"
        )
        for zh in zh_list:
            assert "___" not in zh

    def test_food_filled_when_memory_present(self):
        """When favourite_food is known, food slot is replaced correctly."""
        opts = self._call("你喜欢吃什么？", memory={"favourite_food": "火锅"})
        zh_list = [o["zh"] for o in opts]
        assert any("火锅" in zh for zh in zh_list), (
            f"Expected 火锅 in at least one option; got {zh_list}"
        )
        for zh in zh_list:
            assert "___" not in zh

    def test_returns_list_with_no_blanks_even_when_templates_unfillable(self):
        """Even when pool templates have ___ but memory is empty, results are blank-free."""
        opts = self._call("你叫什么名字？", memory={})
        for o in opts:
            assert "___" not in o["zh"]

    def test_all_returned_options_have_no_blank(self):
        """Exhaustive: all commonly triggered patterns must produce blank-free options."""
        patterns = [
            ("你叫什么名字？", {}),
            ("怎么叫？", {}),
            ("你住哪里？", {}),
            ("你现在住哪儿？", {}),
            ("你喜欢吃什么？", {}),
            ("你们那里最有名的菜？", {}),
            ("你去过哪些地方旅游？", {}),
            ("你去过哪些国家？", {}),
        ]
        srv = _load_server()
        for text, mem in patterns:
            opts = srv._build_sentence_options({"text": text}, memory=mem)
            for o in opts:
                assert "___" not in o["zh"], (
                    f"pattern={text!r}: blank slot in option {o['zh']!r}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Static source checks
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def src():
    return _UI_SERVER.read_text(encoding="utf-8")


def test_sentence_options_skip_unfillable(src):
    """_build_sentence_options must skip ___ options rather than emitting them."""
    # The guard iterates all templates and skips those still containing ___
    assert 'if "___" in zh:' in src, (
        "Missing ___ check in _build_sentence_options"
    )
    # After substitution attempt, unfillable ones must be skipped
    assert "continue" in src, "Missing continue to skip unfillable options"


def test_no_leave_blank_comment(src):
    """The old 'leave ___ as visual hint' comment must be removed."""
    assert "leave ___ as visual hint" not in src, (
        "Old 'leave ___ as visual hint' comment still present — slot guard not applied"
    )


def test_name_echo_guard_present(src):
    """NAME echo must guard against learner_name containing ___."""
    assert '"___" not in _name' in src, (
        "Missing ___ guard in NAME echo block — "
        "'___！你名字有什么故事吗？' regression not fixed"
    )


def test_city_safety_net_uses_context_aware_generic_food(src):
    """City safety net must use 你那儿 for food frames."""
    assert "你那儿" in src, "Missing 你那儿 in city slot safety net"


def test_city_safety_net_uses_context_aware_generic_special(src):
    """City safety net must use 你住的地方 for special-features frames."""
    assert "你住的地方" in src, "Missing 你住的地方 in city slot safety net"


def test_city_safety_net_comment_present(src):
    """Safety net comment must explain context-aware logic."""
    assert "context-aware" in src or "Context-aware" in src, (
        "Missing context-aware safety net description"
    )


def test_build_sentence_options_iterates_all_templates(src):
    """
    _build_sentence_options must iterate all templates (not just first 3)
    so that blank-slot options can be skipped and still yield up to 3 results.
    """
    # The guard changes the iteration from chosen[:3] to 'for t in chosen'
    # with a len(result) >= 3 break guard.
    idx = src.find("def _build_sentence_options(")
    assert idx != -1, "_build_sentence_options not found"
    # Use a larger window (2000 chars) to span the full function body
    body = src[idx: idx + 2000]
    assert "for t in chosen:" in body, (
        "_build_sentence_options must iterate all chosen templates (not chosen[:3])"
    )
    assert "len(result) >= 3" in body, (
        "_build_sentence_options must break when 3 results collected"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Content file checks: response_patterns.json templates
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def patterns_data():
    return json.loads(_RESPONSE_PATTERNS.read_text(encoding="utf-8"))


def _all_blank_templates(data) -> list[tuple[str, str]]:
    """Return (key, zh) pairs for all templates that contain ___."""
    result = []
    for pat in data.get("patterns") or []:
        key = pat.get("key", "?")
        for opt in pat.get("options") or []:
            zh = opt.get("zh") or ""
            if "___" in zh:
                result.append((key, zh))
    return result


def test_no_template_emits_raw_blank_when_memory_empty(patterns_data):
    """
    For every ___ template in response_patterns.json, calling
    _build_sentence_options with empty memory must not produce any option
    containing ___.
    """
    srv = _load_server()
    for pat in patterns_data.get("patterns") or []:
        key = pat.get("key") or ""
        has_blank = any("___" in (o.get("zh") or "") for o in pat.get("options") or [])
        if not has_blank:
            continue
        # Use the pattern key as the frame text to trigger the pool selection
        opts = srv._build_sentence_options({"text": key}, memory={})
        for o in opts:
            zh = o.get("zh") or ""
            assert "___" not in zh, (
                f"Pattern key={key!r}: ___ in option {zh!r} with empty memory"
            )


def test_all_blank_templates_handled(patterns_data):
    """
    Every ___ template in response_patterns.json must either:
    a) be fillable when memory has the right key, OR
    b) be safely skipped (no ___ in output) when memory is empty.

    This test documents all templates that use ___ and verifies behavior.
    """
    srv = _load_server()
    blanks = _all_blank_templates(patterns_data)
    assert blanks, "No ___ templates found — test data may have changed"

    for key, zh_template in blanks:
        # With empty memory, output must be blank-free
        opts = srv._build_sentence_options({"text": key}, memory={})
        for o in opts:
            assert "___" not in o["zh"], (
                f"Template '{zh_template}' (key={key!r}) still emits ___ "
                f"with empty memory: {o['zh']!r}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Regression: exact session examples from the bug report
# ─────────────────────────────────────────────────────────────────────────────


def test_regression_name_echo_source_guard(src):
    """
    Static regression: '___！你名字有什么故事吗？' pattern.

    The NAME echo guard '\"___\" not in _name' must be in the source so that
    when memory has learner_name='___', the echo is suppressed and frame_text
    remains just '你名字有什么故事吗？'.
    """
    assert '"___" not in _name' in src, (
        "NAME echo guard missing — '___！你名字有什么故事吗？' regression not fixed"
    )


def test_regression_city_food_frame_source_guard(src):
    """
    Static regression: '___有什么好吃的？' pattern.

    The city safety net must replace {CITY} with 你那儿 for food frames.
    """
    # Find the safety net block
    idx = src.find("Safety net: if any slot token survived")
    assert idx != -1, "City slot safety net comment not found"
    block = src[idx: idx + 500]
    assert "你那儿" in block, (
        "Safety net must use 你那儿 for food frames — "
        "'___有什么好吃的？' regression not fixed"
    )


def test_regression_city_special_frame_source_guard(src):
    """
    Static regression: '那，___有什么特别的？' pattern.

    The city safety net must replace {CITY} with 你住的地方 for special frames.
    """
    idx = src.find("Safety net: if any slot token survived")
    assert idx != -1, "City slot safety net comment not found"
    block = src[idx: idx + 500]
    assert "你住的地方" in block, (
        "Safety net must use 你住的地方 for special frames — "
        "'那，___有什么特别的？' regression not fixed"
    )


def test_regression_name_option_not_emitted_blank(patterns_data):
    """
    Regression: '我叫___。' from session_1782907963223.json line 104.

    When learner_name is unknown, the sentence option pool for 叫什么名字 must
    not include '我叫___。'.
    """
    srv = _load_server()
    opts = srv._build_sentence_options({"text": "叫什么名字"}, memory={})
    for o in opts:
        assert "___" not in o["zh"], (
            f"'我叫___。' regression: ___ in option {o['zh']!r} with empty memory"
        )
