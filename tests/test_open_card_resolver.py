import unittest

from runtime import open_card_resolver as resolver


class TestOpenCardResolver(unittest.TestCase):
    # Shared valid fixtures satisfying strict_runtime=True requirements.
    CARDS_INDEX = {"by_word_id": {"你好": "card_nihao", "frame_1": "card_frame1"}}
    CARDS = {"card_nihao": {}, "card_frame1": {}}

    def test_resolve_card_success_token(self):
        engine_affordances = {"eng1": {"open_card": True}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["你好"],
            "frame_id": "frame_1",
        }

        card_id = resolver.resolve_card_for_frame(frame, engine_affordances, self.CARDS_INDEX, self.CARDS, env="dev")
        self.assertEqual(card_id, "card_nihao")

    def test_resolve_card_raises_in_dev_when_missing(self):
        # Valid index that satisfies strict_runtime, but no mapping for the requested token.
        cards_index = {"by_word_id": {"other_token": "other_card"}}
        cards = {"other_card": {}}
        engine_affordances = {"eng1": {"open_card": True}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["不存在"],
            "frame_id": "frame_missing",
        }

        with self.assertRaises(resolver.OpenCardResolutionError):
            resolver.resolve_card_for_frame(frame, engine_affordances, cards_index, cards, env="dev")

    def test_resolve_card_returns_none_in_prod_when_missing(self):
        # Valid index with no mapping for the requested token: prod path returns None.
        cards_index = {"by_word_id": {"other_token": "other_card"}}
        cards = {"other_card": {}}
        engine_affordances = {"eng1": {"open_card": True}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["不存在"],
            "frame_id": "frame_missing",
        }

        card_id = resolver.resolve_card_for_frame(frame, engine_affordances, cards_index, cards, env="prod")
        self.assertIsNone(card_id)

    def test_affordance_disabled_returns_none(self):
        # Valid data but open_card affordance is False: resolver returns None after strict checks.
        engine_affordances = {"eng1": {"open_card": False}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["你好"],
            "frame_id": "frame_1",
        }

        card_id = resolver.resolve_card_for_frame(frame, engine_affordances, self.CARDS_INDEX, self.CARDS, env="dev")
        self.assertIsNone(card_id)

    def test_build_open_card_event_structure(self):
        ev = resolver.build_open_card_event("eng1", "frame_1", "card_1", reason="test")
        self.assertIsInstance(ev, dict)
        self.assertEqual(ev.get("type"), "OPEN_CARD")
        payload = ev.get("payload")
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload.get("engine_id"), "eng1")
        self.assertEqual(payload.get("frame_id"), "frame_1")
        self.assertEqual(payload.get("card_id"), "card_1")


if __name__ == "__main__":
    unittest.main()
