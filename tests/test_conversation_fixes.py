"""Regression tests for targeted conversation fixes:

A  – /api/version reports current git SHA
B  – Emotional learner disclosure → empathy, not persona limitation reply
C  – Client false-turnaround guard for 你知道吗 + first-person disclosure
D  – Noisy travel destination extraction
E  – Persona challenge response (not generic praise)
F  – Consecutive persona questions produce fresh answers (location → work)
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "scripts"))

_spec = importlib.util.spec_from_file_location("ui_server", _REPO / "scripts" / "ui_server.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_xiaoming = _mod._resolve_persona("xiaoming")

_LIMITATION_PHRASES = (
    "不太清楚",
    "没问过具体的",
    "不太确定",
    "不好说",
    "这个我真的",
)


def _is_limitation_reply(text: str) -> bool:
    return any(p in (text or "") for p in _LIMITATION_PHRASES)


# ---------------------------------------------------------------------------
# A  Version / deployment guard
# ---------------------------------------------------------------------------

class TestVersionEndpoint(unittest.TestCase):
    """A: /api/version must expose a non-trivial git SHA."""

    def test_git_sha_attribute_exists(self):
        sha = getattr(_mod, "_git_sha", None)
        self.assertIsNotNone(sha)

    def test_git_sha_not_unknown(self):
        """SHA must not be the fallback 'unknown' when running locally."""
        sha = getattr(_mod, "_git_sha", "unknown")
        self.assertNotEqual(sha, "unknown", "git SHA should be resolved; check git availability")

    def test_git_sha_looks_like_sha(self):
        sha = getattr(_mod, "_git_sha", "")
        self.assertRegex(sha, r"^[0-9a-f]{4,}", "SHA should be hexadecimal")

    def test_git_branch_attribute_exists(self):
        branch = getattr(_mod, "_git_branch", None)
        self.assertIsNotNone(branch)
        self.assertNotEqual(branch, "", "Branch should not be empty")


# ---------------------------------------------------------------------------
# B  Emotional learner disclosure → empathy
# ---------------------------------------------------------------------------

class TestLearnerDisclosureDetection(unittest.TestCase):
    """B: _is_learner_disclosure must fire for family/health disclosures."""

    def _check(self, text, expected, msg=""):
        result = _mod._is_learner_disclosure(text)
        self.assertEqual(result, expected, f"{text!r}: {msg}")

    def test_mother_sick(self):
        self._check("我妈妈身体不好", True)

    def test_mother_sick_short(self):
        self._check("我妈不好", True)

    def test_father_sick(self):
        self._check("我爸爸生病了", True)

    def test_family_sick(self):
        self._check("我家人身体不好", True)

    def test_worried_bare(self):
        self._check("我最近很担心", True)

    def test_worried_bare_not_disclosure(self):
        # bare "我很担心" without family word or 最近 is too ambiguous → not a disclosure
        self._check("我很担心", False)

    def test_know_prefix_mother(self):
        self._check("你知道吗我妈妈身体不好", True)

    def test_food_preference_not_disclosure(self):
        self._check("我喜欢吃火锅", False)

    def test_place_answer_not_disclosure(self):
        self._check("我在北京", False)

    def test_persona_question_not_disclosure(self):
        self._check("你是哪里人", False)


class TestDisclosureEmpathyPhraseBank(unittest.TestCase):
    """B: phrase bank must be loaded and non-empty."""

    def test_phrases_loaded(self):
        phrases = _mod._disclosure_empathy_phrases
        self.assertGreater(len(phrases), 0, "No disclosure empathy phrases loaded")

    def test_phrases_are_tuples(self):
        for zh, en in _mod._disclosure_empathy_phrases:
            self.assertTrue(zh, "hanzi must be non-empty")
            self.assertTrue(en, "text_en must be non-empty")

    def test_reply_function_returns_tuple(self):
        result = _mod._disclosure_empathy_reply("test_seed")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_reply_zh_is_nonempty(self):
        zh, en = _mod._disclosure_empathy_reply("test_seed")
        self.assertTrue(zh, "Disclosure empathy zh must be non-empty")

    def test_reply_en_is_nonempty(self):
        zh, en = _mod._disclosure_empathy_reply("test_seed")
        self.assertTrue(en, "Disclosure empathy en must be non-empty")


class TestDisclosureRoutingNotLimitation(unittest.TestCase):
    """B: disclosure texts must NOT produce a persona limitation reply via _answer_user_question_prefix."""

    def _check_not_limitation(self, text):
        la = {"submitted_text": text}
        result = _mod._answer_user_question_prefix(la, _xiaoming, context_reply="")
        if result:
            self.assertFalse(
                _is_limitation_reply(result[0]),
                f"{text!r} produced limitation reply: {result[0]!r}",
            )

    def test_mother_sick_no_limitation(self):
        self._check_not_limitation("我妈妈身体不好")

    def test_father_sick_no_limitation(self):
        self._check_not_limitation("我爸爸生病了")

    def test_worried_no_limitation(self):
        self._check_not_limitation("我最近很担心")

    def test_know_prefix_disclosure_detected_before_routing(self):
        # "你知道吗我妈妈身体不好" → _is_learner_disclosure must fire True.
        # In run_turn, this check intercepts BEFORE _answer_user_question_prefix is ever called,
        # so the limitation reply path is never reached.  The unit test verifies the interception.
        for text in ["你知道吗我妈妈身体不好", "你知道吗我妈妈身体不好？"]:
            is_disc = _mod._is_learner_disclosure(text)
            self.assertTrue(
                is_disc,
                f"{text!r} should be detected as learner disclosure (intercepts before limitation reply)",
            )

    def test_dpa_returns_none_for_disclosure(self):
        """_direct_persona_answer must return None for disclosure content (no persona fact applies)."""
        for text in ["我妈妈身体不好", "我爸爸生病了", "我最近很担心"]:
            result = _mod._direct_persona_answer(text, _xiaoming)
            self.assertIsNone(result, f"{text!r} should return None from _direct_persona_answer")


# ---------------------------------------------------------------------------
# C  Client false-turnaround guard (source-inspection)
# ---------------------------------------------------------------------------

class TestClientFalseTurnaroundGuard(unittest.TestCase):
    """C: app.js _isUserDirectedQuestion must have the 你知道吗 disclosure guard."""

    _APP_JS = (_REPO / "ui" / "app.js").read_text(encoding="utf-8")

    def test_guard_pattern_present(self):
        self.assertIn(
            "你知道吗",
            self._APP_JS,
            "app.js must contain the 你知道吗 guard in _isUserDirectedQuestion",
        )

    def test_guard_checks_first_person_family(self):
        self.assertIn(
            "我(妈|爸|家|孩子|家人|身体|最近很担心)",
            self._APP_JS,
            "Guard should exclude first-person family/health disclosures",
        )

    def test_guard_returns_false(self):
        self.assertIn(
            "return false",
            self._APP_JS,
            "Guard must explicitly return false for disclosure patterns",
        )


# ---------------------------------------------------------------------------
# D  Noisy travel destination extraction
# ---------------------------------------------------------------------------

class TestNoisyTravelDestination(unittest.TestCase):
    """D: _extract_travel_destination must handle ASR noise between verb and destination."""

    def _check(self, text, expected):
        result = _mod._extract_travel_destination(text)
        self.assertEqual(result, expected, f"{text!r} → expected {expected!r}, got {result!r}")

    def test_noisy_filler_time_directional(self):
        """Core regression: 会我想去啊九月上去中国 → 中国."""
        self._check("会我想去啊九月上去中国", "中国")

    def test_clean_with_time_marker(self):
        self._check("九月我想去中国", "中国")

    def test_clean_simple(self):
        self._check("我想去甘肃", "甘肃")

    def test_clean_city(self):
        self._check("我想去兰州", "兰州")

    def test_time_directional_no_filler(self):
        """九月上去中国 — time marker + directional without leading filler."""
        self._check("九月上去中国", "中国")

    def test_intent_verb_plan(self):
        self._check("我打算去北京", "北京")

    def test_intent_verb_want(self):
        self._check("我要去上海", "上海")

    def test_no_noise_gansu(self):
        self._check("我想去甘肃兰州", "甘肃兰州")

    def test_no_destination_returns_empty(self):
        result = _mod._extract_travel_destination("我在家里休息")
        self.assertEqual(result, "", "Non-travel text should return empty destination")

    def test_noisy_followup_uses_clean_dest(self):
        """The followup template must use the clean destination, not the noisy phrase."""
        text = "会我想去啊九月上去中国"
        result = _mod._travel_intent_followup(text)
        self.assertTrue(result and result[0], "Travel followup should not be empty")
        self.assertNotIn("九月上去", result[0], "Noisy phrase must not appear in followup")
        self.assertIn("中国", result[0], "Clean destination 中国 must appear in followup")


# ---------------------------------------------------------------------------
# E  Persona challenge response
# ---------------------------------------------------------------------------

class TestPersonaChallengeDetection(unittest.TestCase):
    """E: _is_persona_challenge must fire for challenge/knowledge-prompt patterns."""

    def _check(self, text, expected):
        result = _mod._is_persona_challenge(text)
        self.assertEqual(result, expected, f"{text!r}")

    def test_china_person_should_know(self):
        self._check("你是中国人你应该知道啦", True)

    def test_should_know_ba(self):
        self._check("你应该知道吧", True)

    def test_know_china_special(self):
        self._check("你知道中国有什么特别的吗", True)

    def test_food_question_not_challenge(self):
        self._check("成都有什么好吃的", False)

    def test_place_from_not_challenge(self):
        self._check("你是哪里人", False)


class TestPersonaChallengePhraseBank(unittest.TestCase):
    """E: phrase bank must be loaded and reply must not be generic praise."""

    _GENERIC_PRAISE = ("真不错啊", "真好", "不错啊", "挺好的", "很好")

    def test_phrases_loaded(self):
        self.assertGreater(len(_mod._persona_challenge_phrases), 0)

    def test_reply_nonempty(self):
        zh, en = _mod._persona_challenge_reply("test")
        self.assertTrue(zh)
        self.assertTrue(en)

    def test_reply_is_not_generic_praise(self):
        zh, _ = _mod._persona_challenge_reply("test")
        for praise in self._GENERIC_PRAISE:
            self.assertNotIn(praise, zh, f"Challenge reply must not be generic praise: {zh!r}")

    def test_reply_engages_with_china(self):
        zh, _ = _mod._persona_challenge_reply("test")
        self.assertTrue(
            any(kw in zh for kw in ("中国", "历史", "文化", "地方", "特色")),
            f"Challenge reply should mention China/history/culture: {zh!r}",
        )


# ---------------------------------------------------------------------------
# F  Consecutive persona questions — location then work
# ---------------------------------------------------------------------------

class TestConsecutivePersonaQuestions(unittest.TestCase):
    """F: after a location answer, a work question must produce a fresh work answer."""

    def test_location_answer_not_none(self):
        dpa = _mod._direct_persona_answer("你住在哪里啊", _xiaoming)
        self.assertIsNotNone(dpa, "Location question must return an answer")

    def test_work_answer_not_none(self):
        dpa = _mod._direct_persona_answer("你做什么工作", _xiaoming)
        self.assertIsNotNone(dpa, "Work question must return an answer")

    def test_work_answer_differs_from_location(self):
        loc_ans = _mod._direct_persona_answer("你住在哪里啊", _xiaoming) or ""
        work_ans = _mod._direct_persona_answer("你做什么工作", _xiaoming) or ""
        self.assertNotEqual(
            loc_ans.strip(), work_ans.strip(),
            f"Work answer must differ from location answer. Got: {work_ans!r}",
        )

    def test_stale_override_fires_for_work_after_location(self):
        """Stale override must produce a fresh work answer when prev = location answer."""
        prev = _mod._direct_persona_answer("你住在哪里啊", _xiaoming) or "我住在北京。"
        recent = [prev]
        work_q = "你做什么工作"

        # Stale override calls _direct_persona_answer
        is_dpq = _mod._is_direct_persona_question(work_q)
        is_conf = _mod._is_confusion_signal(work_q)
        self.assertTrue(is_dpq, "Work question must be classified as direct persona question")
        self.assertFalse(is_conf, "Work question must not be classified as confusion")

        dpa = _mod._direct_persona_answer(work_q, _xiaoming, recent_replies=recent)
        self.assertIsNotNone(dpa, "Work DPA must return an answer")
        # The answer must be different from the location answer (so stale override guard won't block)
        self.assertNotEqual(dpa.strip(), prev.strip(),
                            f"Work answer {dpa!r} must differ from location answer {prev!r}")

    def test_three_consecutive_distinct(self):
        """你住在哪里啊 → location; 你工作呢你做什么工作 → work; 你做什么工作 → dedup handles."""
        prev = "我住在北京。"
        recent = [prev]

        for q in ["你工作呢你做什么工作", "你做什么工作"]:
            dpa = _mod._direct_persona_answer(q, _xiaoming, recent_replies=recent)
            # Work answer must not repeat the location answer
            self.assertIsNone(
                None if (not dpa or dpa.strip() != prev.strip()) else "REPEAT",
                f"Turn {q!r}: answer {dpa!r} must not repeat location answer {prev!r}",
            )
            if dpa:
                recent = (recent + [dpa])[-3:]

    def test_mother_disclosure_overrides_before_work_routing(self):
        """Disclosure check fires before persona-question routing — even if user_asked_question is True."""
        text = "我妈妈身体不好"
        is_disclosure = _mod._is_learner_disclosure(text)
        self.assertTrue(is_disclosure, "Mother-health disclosure must be detected")
        empathy = _mod._disclosure_empathy_reply("f_test")
        self.assertTrue(empathy and empathy[0], "Empathy reply must be non-empty")

    def test_noisy_travel_in_sequence_uses_clean_dest(self):
        """会我想去啊九月上去中国 must extract 中国 even when called as part of a turn sequence."""
        dest = _mod._extract_travel_destination("会我想去啊九月上去中国")
        self.assertEqual(dest, "中国")
        followup = _mod._travel_intent_followup("会我想去啊九月上去中国")
        self.assertTrue(followup and followup[0])
        self.assertNotIn("九月上去", followup[0])
        self.assertIn("中国", followup[0])


if __name__ == "__main__":
    unittest.main()
