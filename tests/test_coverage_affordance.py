import unittest

from tools.coverage.coverage_scan import reclassify_frames_with_cards


class TestCoverageAffordanceReclassification(unittest.TestCase):
    def test_engine_open_card_and_card_L0_reclassifies(self):
        per_frame = {
            "f1": {
                "readiness_label": "READY_NO_HINTS",
                "option_tokens": [],
                "engine_id": "eng1",
                "affordances": [],
                "blockers": [],
            }
        }
        engines_affordances = {"eng1": ["open_card"]}
        # one card c1 with level 0 (L0+)
        card_readiness_map = {"c1": 0}
        cards_by_word_id = {}
        cards_by_hanzi = {}

        reclassify_frames_with_cards(per_frame, engines_affordances, card_readiness_map, cards_by_word_id, cards_by_hanzi)

        self.assertEqual(per_frame["f1"]["readiness_label"], "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE")
        self.assertIn("conv_hint_missing_but_card_available", per_frame["f1"]["blockers"])

    def test_no_open_card_stays_READY_NO_HINTS(self):
        per_frame = {
            "f2": {
                "readiness_label": "READY_NO_HINTS",
                "option_tokens": [],
                "engine_id": "eng2",
                "affordances": [],
                "blockers": [],
            }
        }
        engines_affordances = {"eng2": []}
        card_readiness_map = {"c1": 0}
        cards_by_word_id = {}
        cards_by_hanzi = {}

        reclassify_frames_with_cards(per_frame, engines_affordances, card_readiness_map, cards_by_word_id, cards_by_hanzi)

        self.assertEqual(per_frame["f2"]["readiness_label"], "READY_NO_HINTS")
        self.assertNotIn("conv_hint_missing_but_card_available", per_frame["f2"]["blockers"])

    def test_open_card_but_no_L0_cards_stays_READY_NO_HINTS(self):
        per_frame = {
            "f3": {
                "readiness_label": "READY_NO_HINTS",
                "option_tokens": [],
                "engine_id": "eng3",
                "affordances": [],
                "blockers": [],
            }
        }
        engines_affordances = {"eng3": ["open_card"]}
        # no L0+ cards (levels are negative or absent)
        card_readiness_map = {"c1": -1}
        cards_by_word_id = {}
        cards_by_hanzi = {}

        reclassify_frames_with_cards(per_frame, engines_affordances, card_readiness_map, cards_by_word_id, cards_by_hanzi)

        self.assertEqual(per_frame["f3"]["readiness_label"], "READY_NO_HINTS")
        self.assertNotIn("conv_hint_missing_but_card_available", per_frame["f3"]["blockers"])


if __name__ == "__main__":
    unittest.main()
