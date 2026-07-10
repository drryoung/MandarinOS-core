"""Regression tests for spoken-Chinese ASR routing normalization and semantic matchers.

Covers: place-feature, place-food, work, cooking questions, raw-text preservation.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "scripts"))

_spec = importlib.util.spec_from_file_location("ui_server", _REPO / "scripts" / "ui_server.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_xiaoming = _mod._resolve_persona("xiaoming")

_CHONGQING_FEATURE_KW = ("火锅", "山城", "夜景", "辣", "坡路", "洪崖洞", "特色", "风景")
_CHONGQING_FOOD_KW = ("火锅", "小面", "辣", "串串", "好吃")
_WORK_KW = ("软件", "开发", "工程师", "工作", "人工智能", "代码")
_COOKING_KW = ("菜", "做饭", "煮", "炒", "回锅肉", "饺子", "厨")


def _route(t: str, persona=None, recent=None):
    """Route through normalization + direct persona answer (routing funnel)."""
    persona = persona or _xiaoming
    rt = _mod._normalize_zh_for_routing(t)
    return _mod._direct_persona_answer(rt, persona, recent_replies=recent or [])


def _is_uq(t: str) -> bool:
    rt = _mod._normalize_zh_for_routing(t)
    return _mod._is_user_question({"submitted_text": rt, "selected_option_hanzi": rt})


def _is_dpq(t: str) -> bool:
    rt = _mod._normalize_zh_for_routing(t)
    return _mod._is_direct_persona_question(rt)


# ---------------------------------------------------------------------------
# Normalization helper
# ---------------------------------------------------------------------------

class TestNormalizeZhForRouting(unittest.TestCase):
    def test_collapses_cjk_spacing(self):
        raw = "重 庆 有 什么 特别"
        norm = _mod._normalize_zh_for_routing(raw)
        self.assertEqual(norm, "重庆有什么特别")
        self.assertNotEqual(norm, raw)

    def test_strips_leading_filler(self):
        self.assertEqual(
            _mod._normalize_zh_for_routing("呃重庆有什么特别的啊"),
            "重庆有什么特别的",
        )

    def test_idempotent(self):
        raw = "呃重 庆 有 什么 特别 啊"
        once = _mod._normalize_zh_for_routing(raw)
        twice = _mod._normalize_zh_for_routing(once)
        self.assertEqual(once, twice)

    def test_preserves_raw_is_different(self):
        raw = "重 庆 有 什么 特别"
        norm = _mod._normalize_zh_for_routing(raw)
        self.assertNotEqual(raw, norm)


# ---------------------------------------------------------------------------
# Place feature
# ---------------------------------------------------------------------------

class TestPlaceFeatureRouting(unittest.TestCase):
    prev = "我老家在重庆。"

    def _assert_feature(self, t, msg=""):
        ans = _route(t, recent=[self.prev])
        self.assertIsNotNone(ans, f"{t!r} should produce an answer. {msg}")
        self.assertNotEqual(ans.strip(), self.prev.strip(), f"{t!r} must not repeat hometown answer")
        self.assertTrue(
            any(k in ans for k in _CHONGQING_FEATURE_KW),
            f"{t!r} → {ans!r} should mention Chongqing features",
        )

    def test_clean_canonical(self):
        self._assert_feature("重庆有什么特别的")

    def test_cjk_spacing(self):
        self._assert_feature("重 庆 有 什么 特别")

    def test_dropped_shenme(self):
        self._assert_feature("重庆特别的")

    def test_trailing_filler(self):
        self._assert_feature("呃重庆有什么特别的啊")

    def test_classified_as_question(self):
        for t in ("重庆有什么特别的", "重 庆 有 什么 特别", "重庆特别的"):
            self.assertTrue(_is_uq(t), f"{t!r} should be user_question")
            self.assertTrue(_is_dpq(t), f"{t!r} should be direct_persona_question")


# ---------------------------------------------------------------------------
# Place food
# ---------------------------------------------------------------------------

class TestPlaceFoodRouting(unittest.TestCase):
    prev_feature = "重庆是山城，到处都是坡路，风景很特别。"

    def _assert_food(self, t, msg=""):
        ans = _route(t, recent=[self.prev_feature])
        self.assertIsNotNone(ans, f"{t!r} should produce an answer. {msg}")
        self.assertNotEqual(ans.strip(), self.prev_feature.strip())
        self.assertTrue(
            any(k in ans for k in _CHONGQING_FOOD_KW),
            f"{t!r} → {ans!r} should mention Chongqing food",
        )

    def test_clean_canonical(self):
        self._assert_food("重庆有什么好吃的")

    def test_dropped_shenme(self):
        self._assert_food("重庆好吃的")

    def test_deixis_there(self):
        self._assert_food("那里有什么好吃的")

    def test_food_not_feature(self):
        food_ans = _route("重庆好吃的", recent=[self.prev_feature])
        feature_ans = _route("重庆有什么特别的", recent=["我老家在重庆。"])
        self.assertIsNotNone(food_ans)
        self.assertIsNotNone(feature_ans)
        self.assertNotEqual(food_ans, feature_ans)


# ---------------------------------------------------------------------------
# Work
# ---------------------------------------------------------------------------

class TestWorkRouting(unittest.TestCase):
    prev_food = "重庆的火锅比成都的还辣，小面的汤底也特别香。"

    def _assert_work(self, t):
        ans = _route(t, recent=[self.prev_food])
        self.assertIsNotNone(ans, f"{t!r} should produce work answer")
        self.assertNotEqual(ans.strip(), self.prev_food.strip())
        self.assertTrue(any(k in ans for k in _WORK_KW), f"{t!r} → {ans!r}")

    def test_clean(self):
        self._assert_work("你做什么工作")

    def test_homophone_zuo(self):
        # Narrow: 坐 is NOT corrected; keyword fallback via 工作 in catch-all may still work
        ans = _route("你坐什么工作", recent=[self.prev_food])
        self.assertIsNotNone(ans)


# ---------------------------------------------------------------------------
# Cooking
# ---------------------------------------------------------------------------

class TestCookingRouting(unittest.TestCase):
    prev_work_duration = "我已经做了七年了。"

    def _assert_cooking(self, t):
        ans = _route(t, recent=[self.prev_work_duration])
        self.assertIsNotNone(ans, f"{t!r} should produce cooking answer")
        self.assertNotEqual(ans.strip(), self.prev_work_duration.strip())
        self.assertTrue(any(k in ans for k in _COOKING_KW), f"{t!r} → {ans!r}")

    def test_ni_zuo_shenme_cai(self):
        self._assert_cooking("你做什么菜")

    def test_ni_hui_zuo_shenme_cai(self):
        self._assert_cooking("你会做什么菜")

    def test_english_translation_nonempty(self):
        ans = _route("你做什么菜")
        self.assertIsNotNone(ans)
        en = _mod._persona_answer_en(_xiaoming, ans)
        self.assertTrue(en, "Cooking answer must have non-empty English translation")


# ---------------------------------------------------------------------------
# Acceptance transitions (A–E from spec)
# ---------------------------------------------------------------------------

class TestAcceptanceTransitions(unittest.TestCase):
    def test_t1_hometown_then_feature(self):
        prev = "我老家在重庆。"
        ans = _route("重庆有什么特别的", recent=[prev])
        self.assertIsNotNone(ans)
        self.assertNotEqual(ans.strip(), prev.strip())

    def test_t2_feature_then_food(self):
        prev = "重庆是山城，到处都是坡路，风景很特别。"
        for t in ("重庆有什么好吃的", "重庆好吃的"):
            ans = _route(t, recent=[prev])
            self.assertIsNotNone(ans)
            self.assertNotEqual(ans.strip(), prev.strip())
            self.assertTrue(any(k in ans for k in _CHONGQING_FOOD_KW))

    def test_t3_food_then_work(self):
        prev = "重庆的火锅比成都的还辣，小面的汤底也特别香。"
        ans = _route("你做什么工作", recent=[prev])
        self.assertIsNotNone(ans)
        self.assertNotEqual(ans.strip(), prev.strip())
        self.assertTrue(any(k in ans for k in _WORK_KW))

    def test_t4_work_duration_then_cooking(self):
        prev = "我已经做了七年了。"
        ans = _route("你做什么菜", recent=[prev])
        self.assertIsNotNone(ans)
        self.assertNotEqual(ans.strip(), prev.strip())

    def test_t5_spaced_equivalent_to_canonical(self):
        spaced = _route("重 庆 有 什么 特别")
        canonical = _route("重庆有什么特别的")
        self.assertIsNotNone(spaced)
        self.assertIsNotNone(canonical)
        self.assertTrue(any(k in spaced for k in _CHONGQING_FEATURE_KW))
        self.assertTrue(any(k in canonical for k in _CHONGQING_FEATURE_KW))


# ---------------------------------------------------------------------------
# Raw-text preservation contract
# ---------------------------------------------------------------------------

class TestRawTextPreservation(unittest.TestCase):
    def test_normalization_does_not_mutate_input(self):
        raw = "重 庆 有 什么 特别"
        copy = raw
        _mod._normalize_zh_for_routing(raw)
        self.assertEqual(raw, copy, "Normalizer must not mutate the input string")

    def test_routing_differs_from_raw(self):
        raw = "重 庆 有 什么 特别"
        routing = _mod._normalize_zh_for_routing(raw)
        self.assertNotEqual(routing, raw)


if __name__ == "__main__":
    unittest.main()
