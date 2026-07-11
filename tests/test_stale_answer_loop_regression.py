"""
Regression tests for the stale-answer loop (RC-A / RC-B / RC-C).

Confirmed live sequence (zhiyuan persona):
  你是哪里人                          → 我老家是南京，不过在上海工作已经好几年了。
  你南京有什么特别的                  → clarification or Nanjing feature (NOT the hometown reply)
  南京有什么特别的                    → Nanjing feature
  南京有什么特别之处？                → distinct Nanjing answer
  南京有什么好吃                      → Nanjing food
  上海了上海有什么特别的              → Shanghai feature
  上海有什么好吃                      → Shanghai food
  你做什么工作                        → persona work answer

No two adjacent turns may return the identical reply.
A previous hometown/place answer must never survive as the final answer to a
food or work question.
"""

import sys
import threading
import time
import json
import urllib.request
import unittest

sys.path.insert(0, "scripts")
import ui_server as srv


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


def _run_turn(port: int, cs: dict, user_text: str) -> tuple[dict, str]:
    """Post one turn and return (updated_cs, counter_reply)."""
    cs_t = dict(cs)
    cs_t["last_answer"] = {"submitted_text": user_text}
    cs_t["last_turn_was_answer"] = True
    resp = _post(port, {"persona_id": "zhiyuan", "next_question": True, "conversation_state": cs_t})
    reply = resp.get("counter_reply") or ""
    new_cs = _merge_cs(cs_t, resp)
    return new_cs, reply


_INITIAL_CS = {
    "persona_id": "zhiyuan",
    "current_engine": "identity",
    "last_turn_was_answer": True,
    "last_counter_reply": "",
    "recent_persona_replies": [],
}

_HOMETOWN_REPLY = "我老家是南京，不过在上海工作已经好几年了。"
_NANJING_FEATURE = "南京历史很悠久，有很多历史遗迹。"


class TestStaleAnswerLoopRegression(unittest.TestCase):
    """Full 8-turn stateful HTTP regression for the confirmed live loop."""

    @classmethod
    def setUpClass(cls):
        cls.port = 8991
        cls.server = _start_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _run_sequence(self) -> list[str]:
        """Drive the full confirmed sequence; return list of replies."""
        sequence = [
            "你是哪里人",
            "你南京有什么特别的",
            "南京有什么特别的",
            "南京有什么特别之处？",
            "南京有什么好吃",
            "上海了上海有什么特别的",
            "上海有什么好吃",
            "你做什么工作",
        ]
        cs = dict(_INITIAL_CS)
        replies = []
        for text in sequence:
            cs, reply = _run_turn(self.port, cs, text)
            replies.append(reply)
        return replies

    def test_t1_hometown_answer(self):
        """Turn 1: asks 你是哪里人 → persona's origin answer."""
        replies = self._run_sequence()
        self.assertEqual(replies[0], _HOMETOWN_REPLY)

    def test_t3_nanjing_feature_not_hometown(self):
        """Turn 3: 南京有什么特别的 must answer with a Nanjing feature, NOT the hometown reply."""
        replies = self._run_sequence()
        self.assertNotEqual(replies[2], _HOMETOWN_REPLY,
                            "Nanjing feature question returned the hometown answer verbatim")
        self.assertTrue(
            any(kw in replies[2] for kw in ("南京", "历史", "遗迹", "特别", "有名", "古")),
            f"T3 reply does not mention Nanjing features: {replies[2]!r}"
        )

    def test_t4_nanjing_distinct_from_t3(self):
        """Turn 4 (南京有什么特别之处) must differ from Turn 3."""
        replies = self._run_sequence()
        self.assertNotEqual(replies[3], replies[2],
                            "T4 repeats T3 Nanjing feature answer")

    def test_t5_nanjing_food(self):
        """Turn 5: 南京有什么好吃 → a food answer, not the previous feature answer."""
        replies = self._run_sequence()
        self.assertNotEqual(replies[4], replies[3],
                            "T5 Nanjing food repeats T4 feature answer")
        self.assertNotEqual(replies[4], _HOMETOWN_REPLY,
                            "T5 Nanjing food returned hometown reply")
        self.assertTrue(
            any(kw in replies[4] for kw in ("吃", "食", "鸭", "小吃", "好吃")),
            f"T5 does not look like a food answer: {replies[4]!r}"
        )

    def test_t6_shanghai_feature_not_nanjing(self):
        """Turn 6: Shanghai question must produce a Shanghai or clarification answer."""
        replies = self._run_sequence()
        reply = replies[5]
        self.assertNotIn("南京历史", reply,
                         "T6 returned a Nanjing feature answer for a Shanghai question")
        self.assertNotEqual(reply, _HOMETOWN_REPLY,
                            "T6 returned hometown answer for a Shanghai question")

    def test_t7_shanghai_food(self):
        """Turn 7: 上海有什么好吃 → Shanghai food, not previous answers."""
        replies = self._run_sequence()
        self.assertNotEqual(replies[6], replies[5],
                            "T7 Shanghai food repeats T6 answer")
        self.assertTrue(
            any(kw in replies[6] for kw in ("上海", "本帮", "生煎", "小笼", "吃", "食")),
            f"T7 does not look like a Shanghai food answer: {replies[6]!r}"
        )

    def test_t8_work_answer(self):
        """Turn 8: 你做什么工作 → persona's work answer, not any place reply."""
        replies = self._run_sequence()
        reply = replies[7]
        place_phrases = ["南京历史", "上海", "历史遗迹", "鸭血粉丝", "本帮菜"]
        for phr in place_phrases:
            self.assertNotIn(phr, reply,
                             f"T8 work answer contains place phrase {phr!r}: {reply!r}")
        self.assertTrue(
            any(kw in reply for kw in ("工作", "教", "补习", "老师", "职业", "做", "负责")),
            f"T8 does not look like a work answer: {reply!r}"
        )

    def test_no_adjacent_identical_replies(self):
        """No two adjacent turns may return the identical reply."""
        replies = self._run_sequence()
        for i in range(1, len(replies)):
            self.assertNotEqual(replies[i], replies[i - 1],
                                f"Turn {i+1} repeats Turn {i}: {replies[i]!r}")

    def test_previous_hometown_cannot_survive_food_question(self):
        """A hometown reply must not be the final answer to any food or work question."""
        replies = self._run_sequence()
        for i, text in enumerate(["南京有什么好吃", "上海有什么好吃", "你做什么工作"]):
            idx = [4, 6, 7][i]
            self.assertNotEqual(replies[idx], _HOMETOWN_REPLY,
                                f"T{idx+1} ({text!r}) returned the hometown reply")

    def test_previous_feature_cannot_survive_work_question(self):
        """A place-feature reply must not be the final answer to the work question."""
        replies = self._run_sequence()
        self.assertNotIn("历史遗迹", replies[7],
                         "T8 work answer contains the Nanjing feature phrase")


class TestPoisonedStateUnit(unittest.TestCase):
    """Unit tests where last_counter_reply and recent_persona_replies are
    deliberately poisoned with an unrelated answer, verifying the fix holds."""

    @classmethod
    def setUpClass(cls):
        cls.port = 8992
        cls.server = _start_server(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _post_poisoned(self, user_text: str, poisoned_reply: str) -> str:
        cs = {
            "persona_id": "zhiyuan",
            "current_engine": "place",
            "last_turn_was_answer": True,
            "last_counter_reply": poisoned_reply,
            "recent_persona_replies": [poisoned_reply],
            "last_answer": {"submitted_text": user_text},
        }
        resp = _post(self.port, {"persona_id": "zhiyuan", "next_question": True, "conversation_state": cs})
        return resp.get("counter_reply") or ""

    def test_work_question_ignores_poisoned_place_reply(self):
        """你做什么工作 must produce a work answer even when recent_persona_replies
        is poisoned with a Nanjing feature answer."""
        poisoned = "我呢，南京历史很悠久，有很多历史遗迹。"
        reply = self._post_poisoned("你做什么工作", poisoned)
        self.assertNotEqual(reply, poisoned,
                            "Work question returned the poisoned Nanjing feature answer")
        self.assertNotIn("南京历史", reply,
                         f"Work answer unexpectedly contains place phrase: {reply!r}")
        self.assertTrue(
            any(kw in reply for kw in ("工作", "教", "补习", "老师", "职业", "做", "负责")),
            f"Poisoned reply not overridden with work answer: {reply!r}"
        )

    def test_food_question_not_overridden_by_poisoned_feature_reply(self):
        """南京有什么好吃 must produce a food answer even with a poisoned feature reply."""
        poisoned = "我呢，南京历史很悠久，有很多历史遗迹。"
        reply = self._post_poisoned("南京有什么好吃", poisoned)
        self.assertNotEqual(reply, poisoned,
                            "Food question returned the poisoned Nanjing feature answer")
        self.assertTrue(
            any(kw in reply for kw in ("吃", "食", "鸭", "小吃", "好吃")),
            f"Food question did not return food-like answer: {reply!r}"
        )

    def test_feature_question_not_overridden_by_hometown_answer(self):
        """南京有什么特别的 must produce a feature answer when poisoned with the
        hometown answer."""
        poisoned = "我老家是南京，不过在上海工作已经好几年了。"
        reply = self._post_poisoned("南京有什么特别的", poisoned)
        self.assertNotEqual(reply, poisoned,
                            "Feature question returned the poisoned hometown answer")
        self.assertTrue(
            any(kw in reply for kw in ("历史", "遗迹", "南京", "特别", "古")),
            f"Feature question did not return feature-like answer: {reply!r}"
        )


class TestDedupeUnit(unittest.TestCase):
    """Unit tests for _dedupe_persona_answer, _pick_not_in, and RC-B food guard."""

    def setUp(self):
        self.zhiyuan = srv._resolve_persona("zhiyuan")

    # ── RC-C: _pick_not_in prefix-aware ──────────────────────────────────────

    def test_pick_not_in_strips_discourse_prefix(self):
        """A bare pool item that was stored prefixed must be treated as excluded."""
        pool = ["南京历史很悠久，有很多历史遗迹。", "南京的鸭血粉丝汤很有名，小吃也很多。"]
        prefixed = "我呢，南京历史很悠久，有很多历史遗迹。"
        result = srv._pick_not_in(pool, "seed", {prefixed})
        self.assertNotEqual(result, pool[0],
                            "RC-C: bare pool item returned even though its prefixed form was in exclude set")
        self.assertEqual(result, pool[1])

    def test_pick_not_in_bare_exclude_still_works(self):
        """Plain (unprefixed) exclusion still works after RC-C."""
        pool = ["A", "B", "C"]
        result = srv._pick_not_in(pool, "seed", {"A", "B"})
        self.assertEqual(result, "C")

    def test_pick_not_in_all_excluded_returns_candidate(self):
        """When all items are excluded, fall back to stable pick (no crash)."""
        pool = ["A"]
        result = srv._pick_not_in(pool, "seed", {"A", "我呢，A"})
        self.assertIsNotNone(result)

    # ── RC-B: food personal-fact guard ───────────────────────────────────────

    def test_nanjing_food_uses_pool_not_shanghai_fact(self):
        """RC-B: zhiyuan's personal food fact is about Shanghai; a Nanjing food
        question must use the Nanjing pool entry, not the Shanghai fact."""
        result = srv._direct_persona_answer("南京有什么好吃", self.zhiyuan, recent_replies=[])
        self.assertIsNotNone(result)
        profile = self.zhiyuan.get("profile") or {}
        food_fact = (self.zhiyuan.get("discoverable_facts") or {}).get("food") or ""
        city = profile.get("city", "")
        if city and city not in "南京" and city in (food_fact or ""):
            self.assertNotEqual(result, food_fact,
                                f"RC-B: Nanjing food question returned city ({city}) personal fact: {result!r}")
        self.assertTrue(
            any(kw in (result or "") for kw in ("鸭", "南京", "粉丝", "小吃")),
            f"RC-B: Nanjing food answer does not mention Nanjing food: {result!r}"
        )

    def test_city_food_uses_personal_fact_when_it_mentions_city(self):
        """RC-B: When the asked place IS the persona's city AND the personal fact
        mentions that city, the personal fact is preferred."""
        profile = self.zhiyuan.get("profile") or {}
        city = profile.get("city", "")
        food_fact = (self.zhiyuan.get("discoverable_facts") or {}).get("food") or ""
        if city and city in (food_fact or ""):
            result = srv._direct_persona_answer(f"{city}有什么好吃", self.zhiyuan, recent_replies=[])
            self.assertEqual(result, food_fact,
                             f"RC-B: City food question should have preferred personal fact but got: {result!r}")

    # ── RC-A: dedupe stays within same intent ─────────────────────────────────

    def test_dedup_feature_repick_stays_in_feature_pool(self):
        """RC-A: When the Nanjing feature answer is in recent replies, dedup should
        repick from the Nanjing feature pool, not from hometown_special."""
        cand = "我呢，南京历史很悠久，有很多历史遗迹。"
        recent = [cand]
        result = srv._dedupe_persona_answer(cand, recent, "南京有什么特别之处？", self.zhiyuan)
        self.assertNotEqual(result, cand,
                            "RC-A: dedup returned the same candidate without picking an alternative")
        food_fact = (self.zhiyuan.get("discoverable_facts") or {}).get("food") or ""
        place_fact = (self.zhiyuan.get("discoverable_facts") or {}).get("place") or ""
        for cross_intent_fact in [food_fact, place_fact]:
            if cross_intent_fact:
                self.assertNotEqual(result, cross_intent_fact,
                                    f"RC-A: dedup returned a cross-intent fact {cross_intent_fact!r}: {result!r}")

    def test_dedup_food_repick_stays_in_food_pool(self):
        """RC-A: When Shanghai food answer is in recent replies, dedup repicks
        from the Shanghai food pool."""
        cand = "我觉得上海的本帮菜非常有特色，红烧肉和清蒸鱼是我最喜欢的，简单又有味道。"
        recent = [cand]
        result = srv._dedupe_persona_answer(cand, recent, "上海有什么好吃", self.zhiyuan)
        self.assertNotEqual(result, cand,
                            "RC-A: Shanghai food dedup returned same candidate")
        self.assertTrue(
            any(kw in (result or "") for kw in ("上海", "本帮", "生煎", "小笼", "吃", "食")),
            f"RC-A: food dedup result not food-like: {result!r}"
        )

    def test_dedup_not_triggered_when_candidate_not_in_recent(self):
        """Dedup must not fire when the candidate is not in recent replies."""
        cand = "我是补习老师，主要教初高中的数学和语文。"
        recent = ["我老家是南京，不过在上海工作已经好几年了。"]
        result = srv._dedupe_persona_answer(cand, recent, "你做什么工作", self.zhiyuan)
        self.assertEqual(result, cand,
                         f"Dedup should not have fired but returned: {result!r}")


if __name__ == "__main__":
    unittest.main()
