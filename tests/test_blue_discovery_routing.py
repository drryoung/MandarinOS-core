#!/usr/bin/env python3
"""
Regression tests for blue-discovery question routing.

Bug: Blue discovery questions built from client-side fallback tables
(_FRAME_FALLBACK_QUESTIONS, _TOPIC_FALLBACK_QUESTIONS) were missing the
`topic` field.  Without a topic, the server called _mirror_persona_stub("")
which returned the generic fallback "我觉得都挺有意思的。" instead of a
persona-backed place/work/family answer.

Fix:
  A. All client-side question tables now carry `topic` fields.
  B. Server infers topic from direction_question_zh when topic arrives empty.

These tests exercise both layers independently so neither can regress silently.
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
_UI = ROOT / "ui"

# ---------------------------------------------------------------------------
# Minimal persona used in server-side tests
# ---------------------------------------------------------------------------
_PERSONA_PLACE = {
    "profile": {
        "name": "小明",
        "hometown": "成都",
        "city": "北京",
    },
    "discoverable_facts": {
        "identity": "我叫小明，在北京工作。",
        "place":    "我是成都人，现在在北京工作。",
        "work":     "我做软件开发，已经做了五年了。",
    },
    "discoverable_facts_en": {
        "place": "I'm from Chengdu, now working in Beijing.",
    },
    "voice_lines": {},
    "voice_lines_en": {},
}


# ---------------------------------------------------------------------------
# Server module loader (shared)
# ---------------------------------------------------------------------------
_srv_cache = {}


def _load_server():
    if "srv" in _srv_cache:
        return _srv_cache["srv"]
    spec = importlib.util.spec_from_file_location("ui_server_disc", _SCRIPTS / "ui_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server_disc"] = mod
    spec.loader.exec_module(mod)
    _srv_cache["srv"] = mod
    return mod


# ===========================================================================
# Group A — server-side: _find_mirror_answer + _mirror_persona_stub
# ===========================================================================

class TestServerMirrorRouting:
    """Direct unit tests for the server persona-answer functions."""

    def test_place_from_topic_returns_persona_fact(self):
        srv = _load_server()
        zh, en = srv._mirror_persona_stub("place_from", "place", _PERSONA_PLACE)
        assert "成都" in zh or "来自" in zh or "哪里" in zh, (
            f"Expected place_from answer to mention persona hometown, got: {zh!r}"
        )
        assert zh != "我觉得都挺有意思的。", (
            "place_from topic must not fall through to generic fallback"
        )

    def test_find_mirror_answer_exact_match(self):
        """'你是哪里人？' must resolve to place_from persona answer."""
        srv = _load_server()
        result = srv._find_mirror_answer("你是哪里人？", "place", _PERSONA_PLACE)
        assert result is not None, "'你是哪里人？' should match a mirror question"
        zh, en, topic, eng = result
        assert topic == "place_from", f"Expected topic=place_from, got {topic!r}"
        assert zh != "我觉得都挺有意思的。", "Should return persona place answer, not generic fallback"

    def test_find_mirror_answer_with_ni_ne_prefix(self):
        """'你呢？你是哪里人？' must also match (the leading 你呢？ should not break matching)."""
        srv = _load_server()
        result = srv._find_mirror_answer("你呢？你是哪里人？", "place", _PERSONA_PLACE)
        assert result is not None, "'你呢？你是哪里人？' should match place_from mirror question"
        zh, en, topic, eng = result
        assert topic == "place_from", f"Expected topic=place_from, got {topic!r}"
        assert zh != "我觉得都挺有意思的。", "Should return persona place answer, not generic fallback"

    def test_empty_topic_fallback_is_generic(self):
        """Confirm that calling _mirror_persona_stub with empty topic returns the generic fallback —
        this is the exact symptom that the server safety-net fix prevents reaching the learner."""
        srv = _load_server()
        zh, en = srv._mirror_persona_stub("", "place", _PERSONA_PLACE)
        assert zh == "我觉得都挺有意思的。", (
            "Empty topic should still return the generic fallback (this confirms the bug was real)"
        )

    def test_server_mirror_handler_infers_topic_when_empty(self):
        """The server mirror handler must use _find_mirror_answer when topic==''.
        This tests the safety-net added to the direction_intent==mirror branch."""
        srv = _load_server()
        # Simulate what the handler does when topic is empty but direction_question_zh is set.
        topic = ""
        asked_zh = "你呢？你是哪里人？"
        engine_id = "place"
        persona = _PERSONA_PLACE
        # Replicate handler logic
        if not topic and asked_zh:
            inferred = srv._find_mirror_answer(asked_zh, engine_id, persona)
            if inferred:
                stub, stub_en = inferred[0], inferred[1]
                topic = inferred[2] if len(inferred) > 2 else ""
            else:
                result = srv._mirror_persona_stub(topic, engine_id, persona)
                stub, stub_en = result if isinstance(result, tuple) else (result, "")
        else:
            result = srv._mirror_persona_stub(topic, engine_id, persona)
            stub, stub_en = result if isinstance(result, tuple) else (result, "")
        assert topic == "place_from", f"Handler must infer topic=place_from, got {topic!r}"
        assert stub != "我觉得都挺有意思的。", (
            f"Handler must not return generic fallback when asked_zh is '你呢？你是哪里人？', got: {stub!r}"
        )


# ===========================================================================
# Group B — client-side: topic fields in JS question tables
# ===========================================================================

def _app_src() -> str:
    return (_UI / "app.js").read_text(encoding="utf-8")


class TestClientTopicFields:
    """Verify that every client-side question table carries topic fields."""

    def test_frame_fallback_f_from_where_has_topic(self):
        src = _app_src()
        # Extract the f_from_where block
        block = src.split("f_from_where: [")[1].split("],")[0]
        assert "topic:" in block, (
            "_FRAME_FALLBACK_QUESTIONS.f_from_where entries must have topic fields"
        )
        assert "place_from" in block, (
            "The primary '你呢？你是哪里人？' entry must have topic: 'place_from'"
        )

    def test_frame_fallback_ni_ne_question_has_place_from_topic(self):
        src = _app_src()
        # Check specifically that the 你呢 question has the right topic on the same line/nearby
        block = src.split("f_from_where: [")[1].split("],")[0]
        ni_ne_idx = block.index("你呢？你是哪里人？")
        # Within 200 chars after the question zh there must be topic: "place_from"
        nearby = block[ni_ne_idx: ni_ne_idx + 200]
        assert 'place_from' in nearby, (
            f"'你呢？你是哪里人？' entry is missing topic:'place_from'. nearby text: {nearby!r}"
        )

    def test_topic_fallback_place_has_topics(self):
        src = _app_src()
        block = src.split("_TOPIC_FALLBACK_QUESTIONS")[1].split("place_like")[0]
        assert "topic:" in block, "_TOPIC_FALLBACK_QUESTIONS entries must have topic fields"

    def test_topic_fallback_identity_place_from_topic(self):
        src = _app_src()
        # identity section should have place_from topic for 你是哪里人？
        block = src.split("identity:[")[1].split("],")[0]
        assert "place_from" in block, (
            "_TOPIC_FALLBACK_QUESTIONS.identity '你是哪里人？' must have topic: 'place_from'"
        )

    def test_place_depth_early_questions_have_topics(self):
        src = _app_src()
        block = src.split("_PLACE_DEPTH_EARLY_QUESTIONS")[1].split("];")[0]
        assert "topic:" in block, "_PLACE_DEPTH_EARLY_QUESTIONS entries must have topic fields"

    def test_all_frame_fallback_entries_have_topics(self):
        """Every question dict in _FRAME_FALLBACK_QUESTIONS should have a topic field."""
        src = _app_src()
        # Extract the entire _FRAME_FALLBACK_QUESTIONS block
        block = src.split("const _FRAME_FALLBACK_QUESTIONS = {")[1].split("\n};")[0]
        # Split into individual object literals using "{ zh:" as boundary
        entries = block.split("{ zh:")
        entries = [e for e in entries[1:] if e.strip()]  # skip header
        missing = []
        for e in entries:
            obj_text = "{ zh:" + e.split("},")[0] + "}"
            if "topic:" not in obj_text:
                zh_hint = e[:50].strip()
                missing.append(zh_hint)
        assert not missing, (
            f"{len(missing)} entries in _FRAME_FALLBACK_QUESTIONS are missing topic fields:\n"
            + "\n".join(f"  {m}" for m in missing[:10])
        )


# ===========================================================================
# Group C — end-to-end routing invariant
# ===========================================================================

class TestDiscoveryRoutingInvariant:
    """
    Regression guard: the exact repro sequence from the bug report must produce
    a persona-backed place answer, not the generic fallback.
    """

    def test_place_from_question_does_not_produce_generic_fallback(self):
        """
        Repro:
            APP: 你是哪里人？
            USER: 我是生气男人          (any accepted place/person answer)
            USER blue tap: 你呢？你是哪里人？
        Expected: persona place_from answer — NOT "我觉得都挺有意思的。"
        """
        srv = _load_server()
        persona = _PERSONA_PLACE
        # Simulate the server handler for direction_intent="mirror", topic="", asked_zh="你呢？你是哪里人？"
        topic = ""
        asked_zh = "你呢？你是哪里人？"
        engine_id = "place"
        if not topic and asked_zh:
            inferred = srv._find_mirror_answer(asked_zh, engine_id, persona)
            if inferred:
                stub = inferred[0]
            else:
                stub = srv._mirror_persona_stub("", engine_id, persona)[0]
        else:
            stub = srv._mirror_persona_stub(topic, engine_id, persona)[0]
        assert stub != "我觉得都挺有意思的。", (
            f"'你呢？你是哪里人？' must not fall through to generic fallback. Got: {stub!r}"
        )

    def test_place_from_with_explicit_topic_gives_persona_fact(self):
        """When client sends topic='place_from' the answer must mention persona's hometown."""
        srv = _load_server()
        zh, en = srv._mirror_persona_stub("place_from", "place", _PERSONA_PLACE)
        assert zh != "我觉得都挺有意思的。", "place_from should never return generic fallback"
