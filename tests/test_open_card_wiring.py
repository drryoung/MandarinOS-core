import unittest

from runtime import open_card_wiring as wiring


class DummyEmitter:
    def __init__(self):
        self.events = []

    def __call__(self, ev):
        self.events.append(ev)


class TestOpenCardWiring(unittest.TestCase):
    # Fixtures satisfying strict_runtime=True
    CARDS_INDEX = {"by_word_id": {"hello": "card_hello"}}
    CARDS = {"card_hello": {}}
    # Separate index with no mapping for "missing" but valid structure
    CARDS_INDEX_NO_MATCH = {"by_word_id": {"other": "card_other"}}
    CARDS_NO_MATCH = {"card_other": {}}

    def test_emits_event_when_resolved(self):
        engine_affordances = {"eng1": {"open_card": True}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["hello"],
            "frame_id": "frame_1",
        }

        emitter = DummyEmitter()
        ev = wiring.process_frame_and_emit_open_card(frame, engine_affordances, self.CARDS_INDEX, self.CARDS, emitter, env="dev")
        self.assertIsNotNone(ev)
        self.assertEqual(len(emitter.events), 1)
        self.assertEqual(emitter.events[0]["type"], "OPEN_CARD")

    def test_no_emit_when_no_card(self):
        engine_affordances = {"eng1": {"open_card": True}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["missing"],
            "frame_id": "frame_1",
        }

        emitter = DummyEmitter()
        with self.assertRaises(Exception):
            # in dev resolver raises when no mapping found; wiring re-raises
            wiring.process_frame_and_emit_open_card(frame, engine_affordances, self.CARDS_INDEX_NO_MATCH, self.CARDS_NO_MATCH, emitter, env="dev")
        # in case of dev exception, no events emitted
        self.assertEqual(len(emitter.events), 0)


if __name__ == "__main__":
    unittest.main()
