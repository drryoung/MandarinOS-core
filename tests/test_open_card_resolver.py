import unittest

from runtime import open_card_resolver as resolver


class TestOpenCardResolver(unittest.TestCase):
    def test_resolve_card_success_token(self):
        cards_index = {"你好": "card_nihao", "frame_1": "card_frame1"}
        engine_affordances = {"eng1": {"open_card": True}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["你好"],
            "frame_id": "frame_1",
        }

        card_id = resolver.resolve_card_for_frame(frame, engine_affordances, cards_index, {}, env="dev")
        self.assertEqual(card_id, "card_nihao")

    def test_resolve_card_raises_in_dev_when_missing(self):
        cards_index = {}
        engine_affordances = {"eng1": {"open_card": True}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["不存在"],
            "frame_id": "frame_missing",
        }

        with self.assertRaises(resolver.OpenCardResolutionError):
            resolver.resolve_card_for_frame(frame, engine_affordances, cards_index, {}, env="dev")

    def test_resolve_card_returns_none_in_prod_when_missing(self):
        cards_index = {}
        engine_affordances = {"eng1": {"open_card": True}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["不存在"],
            "frame_id": "frame_missing",
        }

        card_id = resolver.resolve_card_for_frame(frame, engine_affordances, cards_index, {}, env="prod")
        self.assertIsNone(card_id)

    def test_affordance_disabled_returns_none(self):
        cards_index = {"你好": "card_nihao"}
        engine_affordances = {"eng1": {"open_card": False}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["你好"],
            "frame_id": "frame_1",
        }

        card_id = resolver.resolve_card_for_frame(frame, engine_affordances, cards_index, {}, env="dev")
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
