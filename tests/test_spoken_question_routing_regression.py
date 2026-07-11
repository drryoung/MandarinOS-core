"""
Regression tests for the spoken-question routing bug and the separate ASR
malformed-destination bug reported against a real session:

  Bug 1 — "西安有什么特别的" (spoken) repeated the prior hometown answer
          ("我老家在西安。") instead of answering with a Xi'an feature fact,
          while "西安有什么特别之处" worked correctly. The fix adds an explicit,
          highest-priority "named place-topic" branch in scripts/ui_server.py
          that answers a feature/food question about a place immediately —
          before hometown/origin intent, previous-answer reuse, stale
          override, or any conversational fallback — for every recognised
          city generically (no per-city special-casing). It also fixes a
          genuine false positive in `_is_place_feature_question` where
          "你有什么特别的爱好？" / "你家有什么特别的传统？" (personal-possession
          questions) were being misclassified as place-feature questions.

  Bug 2 — "9月我想去公司中国" had its destination extracted verbatim as the
          malformed "公司中国" and echoed back as if it were a real place.
          The fix adds a narrow `_recover_malformed_travel_destination`
          helper that recovers the recognised country ("中国") when the
          extracted text is exactly <implausible_prefix><known_country>.

These tests drive the real HTTP `/api/run_turn` path (in-process server),
matching the project's convention (see tests/test_e4_topic_handoff.py) of
exercising the live routing code rather than a duplicated stub.
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
    return _load("ui_server_spoken_q_tests", _UI_SERVER_PATH)


@pytest.fixture(scope="module")
def server_url(srv):
    """Spin up the real HTTP handler in-process so tests exercise the live
    /api/run_turn control flow exactly as the deployed server does."""
    port = 8991 + (id(srv) % 500)  # spread across parallel test runs
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


def _run_turn(server_url: str, cs: dict, persona_id: str = "meiling") -> dict:
    return _post(server_url, {
        "persona_id": persona_id,
        "next_question": True,
        "conversation_state": cs,
    })


def _base_cs(persona_id: str = "meiling") -> dict:
    return {
        "persona_id": persona_id,
        "current_engine": "identity",
        "last_turn_was_answer": True,
        "last_counter_reply": "",
        "recent_persona_replies": [],
    }


def _merge_state_update(cs: dict, response: dict) -> dict:
    """Simulate the client's conversation_state round-trip: merge state_update
    into the outgoing conversation_state for the next turn."""
    su = response.get("state_update") or {}
    merged = dict(cs)
    merged.update(su)
    return merged


# ── A: Core regression — place-topic question after hometown answer ─────────


class TestPlaceFeatureAfterHometown:
    """Reproduces the reported session: a hometown answer must never survive
    an explicit place-feature question about the same city."""

    @pytest.mark.parametrize("feature_question", [
        "西安有什么特别的",
        "西安有什么特别",
        "西安有什么特别之处",
        "西安最特别的是什么",
        "西安有什么特色",
    ])
    def test_feature_question_overrides_stale_hometown_reply(self, server_url, feature_question):
        cs = _base_cs()
        d1 = _run_turn(server_url, {
            **cs,
            "last_answer": {"submitted_text": "我想问你是哪里人"},
        })
        cs2 = _merge_state_update(cs, d1)
        cs2["last_answer"] = {"submitted_text": feature_question}
        cs2["last_turn_was_answer"] = True
        d2 = _run_turn(server_url, cs2)
        reply = (d2.get("counter_reply") or "").strip()
        assert reply, f"Expected a counter_reply for {feature_question!r}"
        assert reply != "我老家在西安。"
        assert "西安" in reply

    def test_forced_stale_hometown_state_still_answers_feature(self, server_url):
        """Even when the client's echoed last_counter_reply is EXACTLY the
        literal hometown line from the real failing session, the explicit
        place-topic question must still win."""
        cs = _base_cs()
        cs["last_counter_reply"] = "我老家在西安。"
        cs["recent_persona_replies"] = ["我老家在西安。"]
        cs["last_answer"] = {"submitted_text": "西安有什么特别的"}
        cs["last_turn_was_answer"] = True
        d = _run_turn(server_url, cs)
        reply = (d.get("counter_reply") or "").strip()
        assert reply != "我老家在西安。"
        assert "西安" in reply

    def test_repeated_identical_question_does_not_stick_on_stale_answer(self, server_url):
        """Asking the SAME feature question twice in a row must not regress
        to the stale hometown answer on the second attempt."""
        cs = _base_cs()
        cs["last_answer"] = {"submitted_text": "我想问你是哪里人"}
        d1 = _run_turn(server_url, cs)
        cs2 = _merge_state_update(cs, d1)
        cs2["last_answer"] = {"submitted_text": "西安有什么特别的"}
        d2 = _run_turn(server_url, cs2)
        reply2 = (d2.get("counter_reply") or "").strip()
        assert reply2 != "我老家在西安。"

        cs3 = _merge_state_update(cs2, d2)
        cs3["last_answer"] = {"submitted_text": "西安有什么特别的"}
        d3 = _run_turn(server_url, cs3)
        reply3 = (d3.get("counter_reply") or "").strip()
        assert reply3 != "我老家在西安。"
        assert reply3, "Third identical question must still produce an answer"


# ── B: Generalises across every recognised city, not just Xi'an ─────────────


class TestExplicitCityGeneralization:
    @pytest.mark.parametrize("question,city", [
        ("北京有什么特别的", "北京"),
        ("成都有什么特别的", "成都"),
    ])
    def test_named_city_feature_question_overrides_prior_topic(self, server_url, question, city):
        cs = _base_cs()
        cs["last_counter_reply"] = "我老家在西安。"
        cs["recent_persona_replies"] = ["我老家在西安。"]
        cs["last_answer"] = {"submitted_text": question}
        cs["last_turn_was_answer"] = True
        d = _run_turn(server_url, cs)
        reply = (d.get("counter_reply") or "").strip()
        assert reply != "我老家在西安。"
        assert city in reply

    def test_food_question_takes_precedence_over_feature(self, server_url):
        cs = _base_cs()
        cs["last_answer"] = {"submitted_text": "重庆有什么特别的"}
        cs["last_turn_was_answer"] = True
        d1 = _run_turn(server_url, cs)
        feature_reply = (d1.get("counter_reply") or "").strip()
        assert feature_reply

        cs2 = _merge_state_update(cs, d1)
        cs2["last_answer"] = {"submitted_text": "重庆有什么好吃的"}
        d2 = _run_turn(server_url, cs2)
        food_reply = (d2.get("counter_reply") or "").strip()
        assert food_reply
        assert food_reply != feature_reply


# ── C: Personal-possession guard — must NOT be mistaken for place questions ──


class TestPersonalPossessionGuard:
    """'你有什么特别的爱好？' / '你家有什么特别的传统？' ask about the PERSONA's own
    hobby/tradition, not a place — regression for the false positive found
    while hardening _is_place_feature_question."""

    @pytest.mark.parametrize("text", [
        "你有什么特别的爱好？",
        "你家有什么特别的传统？",
    ])
    def test_personal_possession_not_classified_as_place_feature(self, srv, text):
        assert srv._is_place_feature_question(text) is False

    @pytest.mark.parametrize("text", [
        "西安有什么特别的",
        "西安有什么特别",
        "西安有什么特别之处",
        "西安最特别的是什么",
        "西安有什么特色",
        "北京有什么特别的",
        "成都有什么特别的",
        "重庆特别的",
        "重庆怎么样",
    ])
    def test_genuine_place_feature_questions_still_recognised(self, srv, text):
        assert srv._is_place_feature_question(text) is True

    def test_food_still_takes_precedence_over_feature_detection(self, srv):
        assert srv._is_place_food_question("重庆有什么好吃的") is True
        assert srv._is_place_feature_question("重庆有什么好吃的") is False


# ── D: Spoken (ASR-noisy) vs typed parity ────────────────────────────────────


class TestSpokenTypedParity:
    """The same underlying question must route identically whether it arrives
    as clean typed/translated text or as noisier ASR-shaped text (extra
    spaces between CJK characters), given the same conversation state."""

    @pytest.mark.parametrize("clean,noisy", [
        ("西安有什么特别的", "西 安 有 什 么 特 别 的"),
        ("重庆有什么特别的", "重 庆 有 什么 特别"),
    ])
    def test_spaced_asr_transcript_routes_same_as_clean_text(self, server_url, clean, noisy):
        def _answer_for(text):
            cs = _base_cs()
            cs["last_counter_reply"] = "我老家在西安。"
            cs["recent_persona_replies"] = ["我老家在西安。"]
            cs["last_answer"] = {"submitted_text": text}
            cs["last_turn_was_answer"] = True
            d = _run_turn(server_url, cs)
            return (d.get("counter_reply") or "").strip()

        clean_reply = _answer_for(clean)
        noisy_reply = _answer_for(noisy)
        assert clean_reply, f"No reply for clean text {clean!r}"
        assert noisy_reply, f"No reply for noisy text {noisy!r}"
        assert clean_reply != "我老家在西安。"
        assert noisy_reply != "我老家在西安。"


# ── E: Malformed ASR travel-destination recovery (公司中国 → 中国) ───────────


class TestTravelDestinationRecovery:
    def test_extract_recovers_country_from_implausible_prefix(self, srv):
        assert srv._extract_travel_destination("9月我想去公司中国") == "中国"

    def test_extract_unaffected_for_legitimate_multi_word_destination(self, srv):
        # Existing behaviour for a genuine "want to go to China, [and] to Gansu"
        # statement must be unchanged — the fix must not delete real words.
        assert srv._extract_travel_destination("九月我想去中国我想去甘肃") == "甘肃"

    def test_extract_does_not_touch_destinations_without_implausible_prefix(self, srv):
        assert srv._extract_travel_destination("我想去成都") == "成都"
        assert srv._extract_travel_destination("我想去中国") == "中国"

    def test_bare_company_destination_not_rewritten(self, srv):
        # "我想去公司" (going to "the company") is a real, if mundane,
        # destination phrase — must not be silently rewritten or deleted.
        assert srv._extract_travel_destination("我想去公司") == "公司"

    def test_run_turn_does_not_echo_malformed_destination(self, server_url):
        cs = _base_cs()
        cs["current_engine"] = "work"
        cs["last_answer"] = {"submitted_text": "9月我想去公司中国"}
        cs["last_turn_was_answer"] = True
        d = _run_turn(server_url, cs)
        reply = (d.get("counter_reply") or "") + (d.get("frame_text") or "")
        assert "公司中国" not in reply
