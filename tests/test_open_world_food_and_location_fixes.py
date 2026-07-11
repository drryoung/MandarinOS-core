"""
Regression tests for the four diagnosed open-world fixes:

  Fix 1: Responsive food answers (regressions ~525e6bf and ~ad711cd).
  Fix 2: Open-world residence-location acceptance (regression 1d78948).
  Fix 3: Learner-provided facts are preserved (state round-trip).
  Fix 4: Distance adjacency (`远吗？` -> `很远` -> `大概要多久？`).

Closes the confirmed regressions:
  - "新西兰冰淇淋最好还有牛扒还有羊肉都很好吃" was misclassified as a question and
    answered with a persona limitation reply.
  - "这里的羊肉和牛排很好吃" was captured by direct-persona question routing and
    answered with the persona's OWN food preference instead of acknowledging the
    learner's answer.
  - "达尼丁" / "但尼丁" / "我住在达尼丁" were rejected as noisy/garbled because they
    are not in the closed `_LOC_CHARS` set.
  - "离那儿远吗？" -> "很远" jumped to an unrelated topic instead of asking a
    distance-detail follow-up.
"""

import sys
import threading
import time
import json
import urllib.request
import unittest

sys.path.insert(0, "scripts")
import ui_server as srv  # noqa: E402


# ── Unit tests: helper functions (fast, no server) ──────────────────────────────────────────────

class TestIsUserQuestionNzHeuristicTightened(unittest.TestCase):
    """Fix 1a: bare 最好/好玩/特别 in a declarative NZ sentence is no longer sufficient
    evidence of a question; genuine NZ questions are still recognised."""

    def test_nz_food_list_statement_is_not_a_question(self):
        t = "新西兰冰淇淋最好还有牛扒还有羊肉都很好吃"
        self.assertFalse(srv._is_user_question({"submitted_text": t}))

    def test_nz_declarative_with_haowan_is_not_a_question(self):
        t = "新西兰南岛风景特别好玩"
        self.assertFalse(srv._is_user_question({"submitted_text": t}))

    def test_nz_question_with_question_mark_still_detected(self):
        self.assertTrue(srv._is_user_question({"submitted_text": "新西兰哪里最好玩？"}))

    def test_nz_question_shenme_still_detected(self):
        self.assertTrue(srv._is_user_question({"submitted_text": "新西兰有什么最好吃的？"}))

    def test_nz_question_with_ma_ending_still_detected(self):
        self.assertTrue(srv._is_user_question({"submitted_text": "新西兰好玩吗？"}))

    def test_generic_preference_question_unaffected(self):
        self.assertTrue(srv._is_user_question({"submitted_text": "你最喜欢吃什么？"}))


class TestResponsiveFoodAnswerDetector(unittest.TestCase):
    """Fix 1b: open-world responsive-food-answer detection."""

    def test_nz_food_list_after_food_frame_is_responsive(self):
        t = "新西兰冰淇淋最好还有牛扒还有羊肉都很好吃"
        self.assertTrue(srv._is_responsive_food_answer(t, "f_place_food", "新西兰有什么好吃的？"))

    def test_generic_food_comparison_after_food_frame_is_responsive(self):
        t = "这里的羊肉和牛排很好吃"
        self.assertTrue(srv._is_responsive_food_answer(t, "f_place_food", "这里有什么好吃的？"))

    def test_unknown_food_name_after_food_frame_is_responsive(self):
        t = "我们那里有一种叫阿布拉卡的东西"
        self.assertTrue(srv._is_responsive_food_answer(t, "p2_pl_2", "南京有什么好吃的？"))

    def test_generic_specialty_statement_after_food_frame_is_responsive(self):
        t = "这个地方有很多特别的小吃"
        self.assertTrue(srv._is_responsive_food_answer(t, "f_food_available", "那里有什么好吃的？"))

    def test_real_question_after_food_frame_is_not_responsive(self):
        # A genuine question turn-around must still route as a question.
        t = "新西兰有什么最好吃的？"
        self.assertFalse(srv._is_responsive_food_answer(t, "f_place_food", "你呢？"))

    def test_declarative_without_food_context_is_not_responsive(self):
        # No preceding food question and an unrecognised frame id — must not fire.
        t = "这里的羊肉和牛排很好吃"
        self.assertFalse(srv._is_responsive_food_answer(t, "f_from_where", "你是哪里人？"))

    def test_filler_after_food_frame_is_not_responsive(self):
        self.assertFalse(srv._is_responsive_food_answer("嗯", "f_place_food", "这里有什么好吃的？"))

    def test_empty_text_is_not_responsive(self):
        self.assertFalse(srv._is_responsive_food_answer("", "f_place_food", "这里有什么好吃的？"))


class TestFoodResponsiveReply(unittest.TestCase):
    """Fix 1c: the acknowledgement + follow-up never claims persona knowledge and
    never emits a persona-limitation phrase."""

    def test_reply_is_never_a_limitation_phrase(self):
        for t in (
            "新西兰冰淇淋最好还有牛扒还有羊肉都很好吃",
            "这里的羊肉和牛排很好吃",
            "成都火锅最好吃",
            "我们那里有一种叫阿布拉卡的东西",
            "这个地方有很多特别的小吃",
        ):
            zh, en = srv._food_responsive_reply(t)
            self.assertTrue(zh)
            self.assertTrue(en)
            self.assertNotIn(zh, (
                "这个我不太清楚。",
                "这个我不太确定，你可以问问别人。",
                "我没问过具体的，不太清楚。",
                "我真的不太了解这个，不好说。",
            ))

    def test_multi_item_answer_acknowledges_items(self):
        zh, _ = srv._food_responsive_reply("新西兰冰淇淋最好还有牛扒还有羊肉都很好吃")
        self.assertIn("牛扒", zh)
        self.assertIn("羊肉", zh)


class TestOpenWorldLocationExtraction(unittest.TestCase):
    """Fix 2: residence acceptance no longer requires known-city / _LOC_CHARS membership."""

    def test_structured_unknown_city_accepted(self):
        self.assertEqual(srv._extract_open_world_location("我住在达尼丁"), "达尼丁")

    def test_structured_unknown_city_variant_accepted(self):
        self.assertEqual(srv._extract_open_world_location("我现在住在奥马鲁"), "奥马鲁")

    def test_structured_latin_city_accepted(self):
        self.assertEqual(srv._extract_open_world_location("我家在Mosgiel"), "Mosgiel")

    def test_structured_generic_description_accepted(self):
        self.assertEqual(srv._extract_open_world_location("我住在一个小镇"), "一个小镇")

    def test_bare_unknown_city_accepted_when_residence_frame_active(self):
        self.assertEqual(
            srv._extract_open_world_location("达尼丁", frame_is_residence=True), "达尼丁"
        )
        self.assertEqual(
            srv._extract_open_world_location("但尼丁", frame_is_residence=True), "但尼丁"
        )
        self.assertEqual(
            srv._extract_open_world_location("Mosgiel", frame_is_residence=True), "Mosgiel"
        )

    def test_bare_answer_rejected_when_frame_not_residence(self):
        # Same bare token, but the active frame is NOT asking for residence — ambiguous.
        self.assertIsNone(srv._extract_open_world_location("达尼丁", frame_is_residence=False))

    def test_known_asr_filler_is_rejected(self):
        for junk in ("嗯", "再说一遍", "不知道", "等你等"):
            self.assertIsNone(
                srv._extract_open_world_location(junk, frame_is_residence=True)
            )

    def test_empty_text_rejected(self):
        self.assertIsNone(srv._extract_open_world_location("", frame_is_residence=True))

    def test_structure_present_but_junk_only_tail_rejected(self):
        self.assertIsNone(srv._extract_open_world_location("我住在等你等"))


# ── Stateful HTTP tests: drive the real /api/run_turn path ──────────────────────────────────────

def _start_server(port: int):
    server = srv.ThreadedHTTPServer(("127.0.0.1", port), srv.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.4)
    return server


def _post(port: int, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/run_turn",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _merge_cs(cs: dict, resp: dict) -> dict:
    su = resp.get("state_update") or {}
    m = dict(cs)
    m.update(su)
    return m


class _StatefulHttpTestBase(unittest.TestCase):
    PORT = 0

    @classmethod
    def setUpClass(cls):
        cls.server = _start_server(cls.PORT)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _run_turn(self, cs: dict, user_text: str, last_answer_fid: str = "") -> tuple:
        cs_t = dict(cs)
        last_answer = {"submitted_text": user_text}
        if last_answer_fid:
            last_answer["frame_id"] = last_answer_fid
        cs_t["last_answer"] = last_answer
        cs_t["last_turn_was_answer"] = True
        resp = _post(self.PORT, {
            "persona_id": "zhiyuan", "next_question": True, "conversation_state": cs_t,
        })
        reply = resp.get("counter_reply") or ""
        new_cs = _merge_cs(cs_t, resp)
        return new_cs, reply, resp


_LIMITATION_PHRASES = (
    "这个我不太清楚。",
    "这个我不太确定，你可以问问别人。",
    "我没问过具体的，不太清楚。",
    "我真的不太了解这个，不好说。",
)


class TestFoodAnswerFullSequenceRegression(_StatefulHttpTestBase):
    """Test 1/3/4/5/14: NZ food-list answer follows the normal answer path, never the
    limitation fallback and never direct-persona's own food preference."""

    PORT = 8994

    def test_nz_food_list_answer_is_acknowledged_not_rejected(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "新西兰有什么好吃的？",
        }
        _, reply, resp = self._run_turn(
            cs, "新西兰冰淇淋最好还有牛扒还有羊肉都很好吃", last_answer_fid="f_place_food",
        )
        self.assertNotIn(reply, _LIMITATION_PHRASES)
        self.assertTrue(reply)

    def test_generic_food_comparison_is_acknowledged_not_persona_preference(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "这里有什么好吃的？",
        }
        _, reply, resp = self._run_turn(
            cs, "这里的羊肉和牛排很好吃", last_answer_fid="f_place_food",
        )
        self.assertNotIn(reply, _LIMITATION_PHRASES)
        # Must not be the persona's own food-preference answer.
        self.assertNotIn("两个我都喜欢", reply)

    def test_unknown_food_name_accepted(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "南京有什么好吃的？",
        }
        _, reply, resp = self._run_turn(
            cs, "我们那里有一种叫阿布拉卡的东西", last_answer_fid="p2_pl_2",
        )
        self.assertNotIn(reply, _LIMITATION_PHRASES)
        self.assertTrue(reply)

    def test_genuine_question_after_food_frame_still_routes_as_question(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "南京有什么好吃的？",
        }
        _, reply, resp = self._run_turn(
            cs, "你最喜欢吃什么？", last_answer_fid="p2_pl_2",
        )
        # A genuine question must still receive a persona answer, not the food-ack pool.
        self.assertNotIn("你最喜欢哪一个", reply)

    def test_direct_persona_question_still_routes_correctly(self):
        cs = {
            "current_engine": "identity",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "",
        }
        _, reply, resp = self._run_turn(cs, "你做什么工作", last_answer_fid="")
        self.assertTrue(reply)
        self.assertNotIn(reply, _LIMITATION_PHRASES)


class TestOpenWorldResidenceAcceptanceRegression(_StatefulHttpTestBase):
    """Tests 6/7/8/9/10: open-world residence acceptance + fact preservation."""

    PORT = 8995

    def test_structured_unknown_residence_accepted_and_stored(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "你现在住哪里？",
        }
        new_cs, reply, resp = self._run_turn(cs, "我住在达尼丁", last_answer_fid="f_live_where")
        self.assertFalse(resp.get("state_update", {}).get("location_clarify_hint"))
        self.assertEqual(new_cs.get("learner_stated_location"), "达尼丁")

    def test_bare_unknown_residence_accepted_while_frame_active(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "你现在住哪里？",
        }
        new_cs, reply, resp = self._run_turn(cs, "达尼丁", last_answer_fid="f_live_where")
        self.assertFalse(resp.get("state_update", {}).get("location_clarify_hint"))
        self.assertEqual(new_cs.get("learner_stated_location"), "达尼丁")

    def test_plausible_unknown_place_retained_across_turns(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "你现在住哪里？",
        }
        cs, _, _ = self._run_turn(cs, "我住在达尼丁", last_answer_fid="f_live_where")
        self.assertEqual(cs.get("learner_stated_location"), "达尼丁")
        # A later unrelated turn must not silently drop the stored fact.
        cs, _, _ = self._run_turn(cs, "还好吧。", last_answer_fid="f_place_like_there")
        self.assertEqual(cs.get("learner_stated_location"), "达尼丁")

    def test_known_asr_filler_still_clarified_not_stored(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "你现在住哪里？",
        }
        new_cs, reply, resp = self._run_turn(cs, "等你等", last_answer_fid="f_live_where")
        su = resp.get("state_update", {})
        self.assertFalse(su.get("learner_stated_location"))

    def test_known_city_residence_still_works(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "你是哪里人？",
        }
        new_cs, reply, resp = self._run_turn(cs, "我住在北京", last_answer_fid="f_live_where")
        self.assertFalse(resp.get("state_update", {}).get("location_clarify_hint"))


class TestDistanceAdjacencyRegression(_StatefulHttpTestBase):
    """Tests 11/12/13: distance-detail follow-up fires immediately after 很远/不远,
    is skipped when the time was already supplied, and the ladder resumes afterward."""

    PORT = 8996

    def test_far_answer_triggers_distance_detail_followup(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "离那儿远吗？",
            "recent_frame_ids": ["p2_pl_far"],
        }
        new_cs, reply, resp = self._run_turn(cs, "很远", last_answer_fid="p2_pl_far")
        self.assertIn(
            resp.get("frame_id"),
            ("f_place_distance_time", "f_place_distance_transport"),
        )

    def test_already_supplied_travel_time_is_not_reasked(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "离那儿远吗？",
            "recent_frame_ids": ["p2_pl_far"],
        }
        new_cs, reply, resp = self._run_turn(
            cs, "坐飞机要十二个小时", last_answer_fid="p2_pl_far",
        )
        self.assertNotEqual(resp.get("frame_id"), "f_place_distance_time")

    def test_ladder_resumes_after_one_distance_exchange(self):
        cs = {
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": "",
            "recent_persona_replies": [],
            "last_partner_frame_text": "大概要多久？",
            "recent_frame_ids": ["p2_pl_far", "f_place_distance_time"],
        }
        new_cs, reply, resp = self._run_turn(
            cs, "大概十二个小时", last_answer_fid="f_place_distance_time",
        )
        # Must not loop back into another distance-detail question.
        self.assertNotIn(
            resp.get("frame_id"), ("f_place_distance_time", "f_place_distance_transport"),
        )


if __name__ == "__main__":
    unittest.main()
