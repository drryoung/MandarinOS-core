import json
import unittest
from pathlib import Path

from runtime import open_card_wiring as wiring


class DummyEmitter:
    def __init__(self):
        self.events = []

    def __call__(self, ev):
        self.events.append(ev)


class TestOpenCardTraceIntegration(unittest.TestCase):
    def test_runtime_emits_open_card_matches_golden(self):
        # prepare inputs
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

        # build a minimal trace: TURN_START, OPEN_CARD (emitted), TURN_END
        trace_steps = []
        trace_steps.append({
            "type": "TURN_START",
            "timestamp": "2026-01-31T00:00:00Z",
            "payload": {"turn_uid": "turn_0001", "engine_id": "eng1", "frame_id": "frame_1"},
        })

        # invoke wiring which should emit an OPEN_CARD event
        try:
            wiring.process_frame_and_emit_open_card(frame, engine_affordances, cards_index, {}, emitter, env="dev")
        except Exception as e:
            self.fail(f"Resolver/wiring raised unexpectedly: {e}")

        # append emitted events into trace steps
        for ev in emitter.events:
            trace_steps.append(ev)

        trace_steps.append({
            "type": "TURN_END",
            "timestamp": "2026-01-31T00:00:02Z",
            "payload": {"turn_uid": "turn_0001", "result": "OPEN_CARD_FIRED"},
        })

        # load golden
        golden_path = Path("tests/fixtures/traces/open_card_fired.golden.json")
        golden = json.loads(golden_path.read_text(encoding="utf-8"))

        # Compare sequence length
        self.assertEqual(len(trace_steps), len(golden["steps"]))

        # Compare each step by type and payload (ignore timestamps)
        for produced, expected in zip(trace_steps, golden["steps"]):
            self.assertEqual(produced.get("type"), expected.get("type"))
            self.assertEqual(produced.get("payload"), expected.get("payload"))


if __name__ == "__main__":
    unittest.main()
