import unittest

from runtime import open_card_wiring as wiring


class DummyEmitter:
    def __init__(self):
        self.events = []

    def __call__(self, ev):
        self.events.append(ev)


class TestOpenCardWiring(unittest.TestCase):
    def test_emits_event_when_resolved(self):
        cards_index = {"hello": "card_hello"}
        engine_affordances = {"eng1": {"open_card": True}}
        frame = {
            "readiness_label": "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE",
            "affordances": {},
            "engine_id": "eng1",
            "option_tokens": ["hello"],
            "frame_id": "frame_1",
        }

        emitter = DummyEmitter()
        ev = wiring.process_frame_and_emit_open_card(frame, engine_affordances, cards_index, {}, emitter, env="dev")
        self.assertIsNotNone(ev)
        self.assertEqual(len(emitter.events), 1)
        self.assertEqual(emitter.events[0]["type"], "OPEN_CARD")

    def test_no_emit_when_no_card(self):
        cards_index = {}
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
            # in dev resolver raises; wiring re-raises
            wiring.process_frame_and_emit_open_card(frame, engine_affordances, cards_index, {}, emitter, env="dev")
        # in case of dev exception, no events emitted
        self.assertEqual(len(emitter.events), 0)


if __name__ == "__main__":
    unittest.main()
