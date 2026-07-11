"""
Regression tests for the contextual ASR place-name repair fix.

Root cause (confirmed live session):

    App:    我老家在西安。
    Learner intended: 西安有什么特别的
    Visible ASR transcript: 需要有什么特别的

`_is_place_feature_question("需要有什么特别的")` already returns True (the marker
"有什么特别" matches regardless of the leading token), so the question WAS being
routed to `_direct_persona_answer`. The real bug was inside the city-resolution
fallback: `_place_from_question_context` could not find "需要" as a place (correctly
— it isn't one) and no deixis marker (那里/那边/…) was present, so the code fell
through to the persona's OWN hometown/city as a last resort. For personas whose
hometown happens to equal the just-discussed city (e.g. meiling / Xi'an) this
*looked* correct by coincidence. But whenever the discussed city differs from the
persona's own hometown (e.g. jianguo, hometown 重庆, discussing 北京), the same
fallback silently invents the WRONG city — proven below with the jianguo/背景 case,
which failed on the pre-fix code.

The fix adds `_repair_contextual_place_question`, a narrow contextual repair that:
  - only fires on a short, fully-matched "<token><feature/food marker>" utterance
    (never on longer sentences merely containing the marker substring);
  - never fires when the token is already a recognised place or a deixis marker;
  - substitutes the token with the SINGLE unambiguous recent city (from the tracked
    `last_place_subject` state and/or the immediately preceding app reply) for
    ROUTING purposes only;
  - asks a clarification instead of guessing when two or more recent cities are
    plausible;
  - makes no change at all when no recent city is available (no invented repair).

These tests drive the real HTTP `/api/run_turn` path (in-process server) for the
end-to-end cases, and call the repair helper directly for the narrow unit-level
guarantees (matching this project's established test style).
"""

import importlib.util
import json
import pathlib
import sys
import threading
import time
import urllib.request

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_UI_SERVER_PATH = _REPO / "scripts" / "ui_server.py"

_cache: dict = {}


def _load(name: str, path: pathlib.Path):
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
    return _load("ui_server_ctx_place_repair_tests", _UI_SERVER_PATH)


@pytest.fixture(scope="module")
def server_url(srv):
    port = 8996 + (id(srv) % 500)
    httpd = srv.ThreadedHTTPServer(("127.0.0.1", port), srv.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    url = f"http://127.0.0.1:{port}"
    yield url
    httpd.shutdown()


def _post(server_url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{server_url}/api/run_turn",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _run_turn(server_url: str, cs: dict, persona_id: str) -> dict:
    return _post(server_url, {
        "persona_id": persona_id,
        "next_question": True,
        "conversation_state": cs,
    })


def _merge_state_update(cs: dict, response: dict) -> dict:
    su = response.get("state_update") or {}
    merged = dict(cs)
    merged.update(su)
    return merged


# ── A: Unit-level guarantees on _repair_contextual_place_question ───────────


class TestRepairFunctionUnit:
    def test_single_recent_city_from_last_place_subject_repairs(self, srv):
        repaired, clarify = srv._repair_contextual_place_question(
            "需要有什么特别的", {"last_place_subject": "西安"}, "我老家在西安。",
        )
        assert repaired == "西安有什么特别的"
        assert clarify is None

    def test_single_recent_city_from_prev_reply_repairs(self, srv):
        repaired, clarify = srv._repair_contextual_place_question(
            "背景有什么特别的", {}, "我在北京工作。",
        )
        assert repaired == "北京有什么特别的"
        assert clarify is None

    def test_food_marker_repairs_too(self, srv):
        repaired, clarify = srv._repair_contextual_place_question(
            "背景有什么好吃的", {}, "我在北京工作。",
        )
        assert repaired == "北京有什么好吃的"
        assert clarify is None

    def test_valid_explicit_city_never_repaired(self, srv):
        """A genuinely recognised place must always win — no repair applied."""
        repaired, clarify = srv._repair_contextual_place_question(
            "重庆有什么特别的", {"last_place_subject": "西安"}, "我老家在西安。",
        )
        assert repaired is None
        assert clarify is None

    def test_two_recent_cities_yields_clarification_not_silent_repair(self, srv):
        repaired, clarify = srv._repair_contextual_place_question(
            "需要有什么特别的", {"last_place_subject": "西安"}, "我在北京工作。",
        )
        assert repaired is None
        assert clarify is not None
        assert "吗" in clarify
        assert ("西安" in clarify) or ("北京" in clarify)

    def test_no_recent_city_does_not_invent_a_destination(self, srv):
        repaired, clarify = srv._repair_contextual_place_question(
            "需要有什么特别的", {}, "",
        )
        assert repaired is None
        assert clarify is None

    def test_deixis_marker_left_untouched(self, srv):
        """'那里' is deixis, already resolved elsewhere — must not be treated as a
        malformed token needing repair."""
        repaired, clarify = srv._repair_contextual_place_question(
            "那里有什么特别的", {"last_place_subject": "西安"}, "我老家在西安。",
        )
        assert repaired is None
        assert clarify is None

    @pytest.mark.parametrize("text", [
        "我需要一点时间",
        "你需要什么",
        "需要有什么特别的条件",
    ])
    def test_ordinary_sentences_with_xuyao_are_never_rewritten(self, srv, text):
        """'需要' is a common valid word; ordinary sentences using it must be
        completely unaffected by the repair (no false positives)."""
        repaired, clarify = srv._repair_contextual_place_question(
            text, {"last_place_subject": "西安"}, "我老家在西安。",
        )
        assert repaired is None
        assert clarify is None


# ── B: End-to-end reported regression — 需要有什么特别的 after 我老家在西安。 ──


class TestReportedSessionEndToEnd:
    def test_malformed_xian_question_does_not_repeat_hometown_answer(self, server_url):
        cs = {
            "persona_id": "meiling",
            "current_engine": "identity",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_answer": {"submitted_text": "我想去甘肃，我没去过。那你呢，你是哪里人？"},
        }
        d1 = _run_turn(server_url, cs, "meiling")
        cs2 = _merge_state_update(cs, d1)
        cs2["last_answer"] = {"submitted_text": "需要有什么特别的"}
        cs2["last_turn_was_answer"] = True
        d2 = _run_turn(server_url, cs2, "meiling")
        reply = (d2.get("counter_reply") or "").strip()
        assert reply, "Expected a non-empty counter_reply"
        assert reply != "我老家在西安。"
        assert "西安" in reply or "问" in reply  # feature answer OR clarification

    def test_forced_stale_hometown_state_with_malformed_token_still_repairs(self, server_url):
        cs = {
            "persona_id": "meiling",
            "current_engine": "identity",
            "last_turn_was_answer": True,
            "last_counter_reply": "我老家在西安。",
            "recent_persona_replies": ["我老家在西安。"],
            "last_place_subject": "西安",
            "last_answer": {"submitted_text": "需要有什么特别的"},
        }
        d = _run_turn(server_url, cs, "meiling")
        reply = (d.get("counter_reply") or "").strip()
        assert reply != "我老家在西安。"
        assert "西安" in reply


# ── C: Mismatched-hometown case — proves the fix is CONTEXTUAL, not coincidence ──


class TestMismatchedHometownProvesContextualFix:
    """jianguo's hometown/city is 重庆, not 北京 — so this scenario can only pass if
    the repair genuinely uses the recent-city CONTEXT rather than silently falling
    back to the persona's own hometown (the exact failure mode this fix targets)."""

    def test_beijing_context_not_confused_with_persona_hometown(self, server_url):
        cs = {
            "persona_id": "jianguo",
            "current_engine": "work",
            "last_turn_was_answer": True,
            "last_counter_reply": "我在北京工作。",
            "recent_persona_replies": ["我在北京工作。"],
            "last_place_subject": "北京",
            "last_answer": {"submitted_text": "背景有什么特别的"},
        }
        d = _run_turn(server_url, cs, "jianguo")
        reply = (d.get("counter_reply") or "").strip()
        assert reply, "Expected a non-empty counter_reply"
        assert "北京" in reply
        assert "重庆" not in reply


# ── D: Negative tests — ordinary "需要" usage must never be rewritten ────────


class TestNegativeCasesPreserved:
    @pytest.mark.parametrize("text", [
        "我需要一点时间",
        "你需要什么",
        "需要有什么特别的条件",
    ])
    def test_ordinary_xuyao_sentences_unaffected_end_to_end(self, server_url, text):
        cs = {
            "persona_id": "meiling",
            "current_engine": "identity",
            "last_turn_was_answer": True,
            "last_counter_reply": "我老家在西安。",
            "recent_persona_replies": ["我老家在西安。"],
            "last_place_subject": "西安",
            "last_answer": {"submitted_text": text},
        }
        d = _run_turn(server_url, cs, "meiling")
        reply = (d.get("counter_reply") or "") + (d.get("frame_text") or "")
        # Must not be silently rewritten into a Xi'an (or any city) feature answer.
        assert "兵马俑" not in reply
        assert "大雁塔" not in reply
        assert "凉皮" not in reply


# ── E: Ambiguity — two distinct recent cities must trigger clarification ─────


class TestAmbiguousContextClarifies:
    def test_two_recent_cities_ask_instead_of_guessing(self, server_url):
        cs = {
            "persona_id": "meiling",
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "我在北京工作。",
            "recent_persona_replies": ["我在北京工作。"],
            "last_place_subject": "西安",  # deliberately different from prev reply's city
            "last_answer": {"submitted_text": "需要有什么特别的"},
        }
        d = _run_turn(server_url, cs, "meiling")
        reply = (d.get("counter_reply") or "").strip()
        assert reply != "我老家在西安。"
        assert "吗" in reply  # clarification question, not an invented answer


# ── F: No recent city at all — must not invent a repair ──────────────────────


class TestNoRecentCityNoInvention:
    def test_no_recent_city_no_repair_at_unit_level(self, srv):
        """When there is genuinely no recent city in context (no last_place_subject,
        no city mentioned in the preceding reply), the repair helper itself must
        never invent one — it must return (None, None) and let the caller's
        pre-existing (out-of-scope-for-this-fix) fallback chain decide."""
        repaired, clarify = srv._repair_contextual_place_question(
            "需要有什么特别的", {}, "",
        )
        assert repaired is None
        assert clarify is None

    def test_no_recent_city_does_not_repeat_stale_answer_verbatim(self, server_url):
        """Without recent city context, the repair step is a no-op, but the turn
        must still not simply repeat the exact previous persona reply verbatim
        (the "prevent stale-answer repetition" requirement)."""
        cs = {
            "persona_id": "meiling",
            "current_engine": "identity",
            "last_turn_was_answer": True,
            "last_counter_reply": "还没有，一个人也挺自在的。",
            "recent_persona_replies": ["还没有，一个人也挺自在的。"],
            "last_answer": {"submitted_text": "需要有什么特别的"},
        }
        d = _run_turn(server_url, cs, "meiling")
        reply = (d.get("counter_reply") or "").strip()
        assert reply != "还没有，一个人也挺自在的。"


# ── G: Valid explicit city always wins over any repair machinery ────────────


class TestValidExplicitCityWins:
    def test_explicit_named_city_overrides_different_recent_subject(self, server_url):
        cs = {
            "persona_id": "meiling",
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "我老家在西安。",
            "recent_persona_replies": ["我老家在西安。"],
            "last_place_subject": "西安",
            "last_answer": {"submitted_text": "重庆有什么特别的"},
        }
        d = _run_turn(server_url, cs, "meiling")
        reply = (d.get("counter_reply") or "").strip()
        assert "重庆" in reply
        assert "兵马俑" not in reply and "大雁塔" not in reply


# ── H: Typed and ASR text follow the same routing after contextual repair ───


class TestTypedAsrParityAfterRepair:
    def test_repaired_asr_text_matches_directly_typed_equivalent(self, server_url):
        def _answer_for(submitted_text):
            cs = {
                "persona_id": "meiling",
                "current_engine": "identity",
                "last_turn_was_answer": True,
                "last_counter_reply": "我老家在西安。",
                "recent_persona_replies": ["我老家在西安。"],
                "last_place_subject": "西安",
                "last_answer": {"submitted_text": submitted_text},
            }
            d = _run_turn(server_url, cs, "meiling")
            return (d.get("counter_reply") or "").strip()

        asr_reply = _answer_for("需要有什么特别的")
        typed_reply = _answer_for("西安有什么特别的")
        assert asr_reply == typed_reply


# ── I: Second reported equivalent — 背景 (recent-city food question) ─────────


class TestSecondReportedEquivalent:
    def test_beijing_food_question_malformed_asr(self, srv):
        repaired, clarify = srv._repair_contextual_place_question(
            "背景有什么好吃的", {}, "我在北京工作。",
        )
        assert repaired == "北京有什么好吃的"
        assert clarify is None
