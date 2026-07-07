"""Regression tests for the persona conversation controller.

The fixture below is the failing MandarinOS transcript that motivated the
fixes. Acceptance tests A-F assert each required behaviour.
"""

import unittest

from runtime import conversation_controller as cc
from runtime.conversation_controller import (
    ConversationController,
    ControllerState,
    GENERIC_FALLBACK,
    PLACE_SOUTH_NZ_QUESTION,
    detect_direct_question,
    detect_travel,
    is_recovery,
)


# Regression fixture: the transcript that was failing (APP/USER turns).
REGRESSION_TRANSCRIPT = [
    ("APP", "你是哪里人？"),
    ("USER", "我是新西兰人"),
    ("USER", "很远啊很远乘飞机啊是12小时"),
    ("APP", "很好！等你等新西兰的南方有什么特别的？"),
    ("USER", "等你等很漂亮啊很安静很干净啊有很多动物"),
    ("USER", "冰淇淋很好吃羊肉牛肉的都好很都很吃"),
    ("APP", "哦，冰淇淋很好吃羊肉牛肉的都好很都很吃！你是说新西兰吗？"),
    ("USER", "呃可以再刷一起吗"),
    ("APP", "我真的不太了解这个，不好说。"),
    ("USER", "听不懂"),
    ("APP", "我真的不太了解这个，不好说。"),
    ("USER", "会九月我想去中国商丘甘肃"),
    ("APP", "哦，会九月我想去中国商丘甘肃！你跟谁一起住？"),
    ("USER", "我爸爸妈妈和和爱人"),
    ("USER", "我妈妈的身体不好"),
    ("APP", "你和家里谁最亲近？"),
    ("USER", "最亲近是我的爱人我们我们结婚两年了"),
    ("APP", "真不错啊！"),
    ("USER", "你呢你结婚了吗"),
    ("APP", "还没有，一个人也挺自在的。"),
    ("USER", "哦你做什么工作"),
    ("APP", "还没有，一个人也挺自在的。"),
    ("USER", "你做什么工作"),
    ("APP", "还没有，一个人也挺自在的。"),
]


def _place_nz_state():
    return ControllerState(
        engine="place",
        topic="southern_new_zealand",
        last_app_reply=PLACE_SOUTH_NZ_QUESTION,
        last_app_question=PLACE_SOUTH_NZ_QUESTION,
    )


class TestRecoveryDetection(unittest.TestCase):
    def test_detects_explicit_and_fuzzy_forms(self):
        for phrase in [
            "听不懂",
            "不懂",
            "什么意思",
            "再说一次",
            "再说一遍",
            "慢一点",
            "可以再说一次吗",
            # ASR corruptions
            "再刷一次",
            "再刷一起",
            "再说一起",
            "再说一",
        ]:
            self.assertTrue(is_recovery(phrase), f"expected recovery for {phrase!r}")

    def test_non_recovery_not_flagged(self):
        for phrase in ["我是新西兰人", "你做什么工作", "九月我想去中国甘肃"]:
            self.assertFalse(is_recovery(phrase), f"unexpected recovery for {phrase!r}")


class TestAcceptanceA(unittest.TestCase):
    """USER: 听不懂 -> repeat/simplify last question, not generic fallback."""

    def test_recovery_repeats_last_question(self):
        ctrl = ConversationController(_place_nz_state())
        reply = ctrl.handle_user_turn("听不懂")
        self.assertNotEqual(reply, GENERIC_FALLBACK)
        self.assertEqual(reply, f"没关系。我再说一次。{PLACE_SOUTH_NZ_QUESTION}")


class TestAcceptanceB(unittest.TestCase):
    """USER: 可以再刷一起吗 -> treated as 可以再说一次吗 (recovery)."""

    def test_asr_corruption_is_recovery(self):
        self.assertTrue(is_recovery("可以再刷一起吗"))
        ctrl = ConversationController(_place_nz_state())
        reply = ctrl.handle_user_turn("呃可以再刷一起吗")
        self.assertNotEqual(reply, GENERIC_FALLBACK)
        self.assertTrue(reply.startswith("没关系。我再说一次。"))


class TestAcceptanceC(unittest.TestCase):
    """USER: 你做什么工作 -> persona work facts."""

    def test_answers_work(self):
        ctrl = ConversationController(ControllerState(engine="family"))
        reply = ctrl.handle_user_turn("你做什么工作")
        self.assertEqual(reply, cc.DEFAULT_PERSONA["work"])
        self.assertNotEqual(reply, cc.DEFAULT_PERSONA["marital"])

    def test_detect_direct_question_variants(self):
        self.assertEqual(detect_direct_question("你做什么工作"), "work")
        self.assertEqual(detect_direct_question("你在哪里工作"), "work")
        self.assertEqual(detect_direct_question("你结婚了吗"), "marital")
        self.assertEqual(detect_direct_question("你有孩子吗"), "kids")
        self.assertEqual(detect_direct_question("你住在哪里"), "residence")
        self.assertEqual(detect_direct_question("你是哪里人"), "origin")
        self.assertEqual(detect_direct_question("你叫什么名字"), "name")
        self.assertEqual(detect_direct_question("你喜欢什么"), "likes")
        self.assertEqual(detect_direct_question("你呢"), "bounce")

    def test_compound_question_resolves_to_real_question(self):
        # "你呢你结婚了吗" must resolve to the marriage question, not the bounce.
        self.assertEqual(detect_direct_question("你呢你结婚了吗"), "marital")


class TestAcceptanceD(unittest.TestCase):
    """APP must not repeat marital answer after user asks about work."""

    def test_no_stale_marital_loop(self):
        state = ControllerState(
            engine="family",
            last_app_reply=cc.DEFAULT_PERSONA["marital"],
            last_app_question="",
        )
        ctrl = ConversationController(state)
        reply = ctrl.handle_user_turn("你做什么工作")
        self.assertNotEqual(reply, cc.DEFAULT_PERSONA["marital"])
        self.assertEqual(reply, cc.DEFAULT_PERSONA["work"])

    def test_stale_guard_blocks_identical_reply(self):
        # Even a non-question, non-recovery turn must not echo the previous
        # reply verbatim.
        state = ControllerState(
            engine="family",
            last_app_reply="你和家里谁最亲近？",
            last_app_question="你和家里谁最亲近？",
        )
        ctrl = ConversationController(state)
        reply = ctrl.handle_user_turn("我妈妈的身体不好")
        self.assertNotEqual(reply, GENERIC_FALLBACK)


class TestAcceptanceE(unittest.TestCase):
    """USER: 九月我想去中国甘肃 -> TRAVEL intent, not FAMILY."""

    def test_travel_intent_routes_to_travel(self):
        state = ControllerState(engine="family")
        ctrl = ConversationController(state)
        reply = ctrl.handle_user_turn("九月我想去中国甘肃")
        self.assertEqual(ctrl.state.engine, "travel")
        self.assertIn("想去", reply)
        self.assertIn("甘肃", reply)
        self.assertEqual(reply, "哦，你九月想去中国甘肃。你想去甘肃哪里？")

    def test_detect_travel_variants(self):
        self.assertIsNotNone(detect_travel("我想去中国"))
        self.assertIsNotNone(detect_travel("九月我想去中国"))
        self.assertIsNotNone(detect_travel("我想去甘肃"))
        self.assertIsNotNone(detect_travel("想去北京"))
        self.assertIsNone(detect_travel("我是新西兰人"))

    def test_travel_picks_most_specific_place(self):
        intent = detect_travel("会九月我想去中国商丘甘肃")
        self.assertEqual(intent.specific_place, "甘肃")
        self.assertEqual(intent.time_phrase, "九月")


class TestAcceptanceF(unittest.TestCase):
    """PLACE topic anchoring: food is a speciality of the current place."""

    def test_food_anchored_to_new_zealand(self):
        ctrl = ConversationController(_place_nz_state())
        reply = ctrl.handle_user_turn("冰淇淋很好吃，羊肉牛肉都很好吃")
        self.assertNotIn("你是说新西兰吗", reply)
        self.assertNotEqual(reply, GENERIC_FALLBACK)
        self.assertIn("新西兰", reply)


class TestTemplateHygiene(unittest.TestCase):
    """Fix #7: corrupted template text must never be produced."""

    def test_place_template_is_clean(self):
        self.assertEqual(PLACE_SOUTH_NZ_QUESTION, "新西兰南方有什么特别的地方？")

    def test_controller_never_emits_corrupted_template(self):
        corrupted = "等你等新西兰的南方有什么特别的？"
        # Drive a variety of turns and make sure the corrupted template never
        # appears as a reply.
        for user_turn in [role_text for role, role_text in REGRESSION_TRANSCRIPT if role == "USER"]:
            ctrl = ConversationController(_place_nz_state())
            reply = ctrl.handle_user_turn(user_turn)
            self.assertNotIn("等你等", reply)
            self.assertNotEqual(reply, corrupted)


class TestPipelineOrdering(unittest.TestCase):
    """Recovery must be evaluated before semantic intent classification."""

    def test_recovery_beats_direct_question_and_travel(self):
        # A recovery signal wins even if other tokens are present.
        ctrl = ConversationController(_place_nz_state())
        reply = ctrl.handle_user_turn("听不懂")
        self.assertTrue(reply.startswith("没关系。我再说一次。"))


if __name__ == "__main__":
    unittest.main()
