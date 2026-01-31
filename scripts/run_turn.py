#!/usr/bin/env python3
"""
Minimal simulator that calls engine.process_turn() and prints trace events as JSON.

Usage:
  python scripts/run_turn.py --frame tests/fixtures/frame_open_card.json [--pretty]

This script is an adapter only; it imports `engine.process_turn` and does not modify runtime code.
"""
import argparse
import json
import sys
from pathlib import Path


def load_json_path(p: str):
    p = Path(p)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def parse_engine_affordances(arg: str):
    if not arg:
        return {}
    p = Path(arg)
    if p.exists():
        return load_json_path(arg) or {}
    try:
        return json.loads(arg)
    except Exception:
        print("Failed to parse --engine-affordances; must be JSON or a path", file=sys.stderr)
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", required=True, help="path to frame JSON")
    parser.add_argument("--cards-index", default="tests/fixtures/cards_index.fixture.json")
    parser.add_argument("--cards", default="tests/fixtures/cards.fixture.json")
    parser.add_argument("--engine-affordances", default=None, help="JSON string or path to engine affordances")
    parser.add_argument("--env", default="prod", choices=["test", "dev", "prod"])
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    frame = load_json_path(args.frame)
    if frame is None:
        print(f"Failed to load frame JSON: {args.frame}", file=sys.stderr)
        sys.exit(2)

    cards_index = load_json_path(args.cards_index) or {}
    cards = load_json_path(args.cards) or {}
    engine_affordances = parse_engine_affordances(args.engine_affordances)

    # import engine inside main per directive
    # ensure repo root is on sys.path so `runtime` package can be imported
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    try:
        from runtime import engine
    except Exception as e:
        print("Failed to import runtime.engine:", e, file=sys.stderr)
        sys.exit(3)

    emitted = []

    def emitter(ev):
        emitted.append(ev)

    # call process_turn; adapt only in this script if signature differs
    try:
        engine.process_turn("sim_turn_1", frame, engine_affordances, cards_index, cards, emitter, env=args.env)
    except TypeError:
        # try an alternate signature if process_turn differs
        try:
            engine.process_turn(frame, engine_affordances, cards_index, cards, emitter, env=args.env)
        except Exception as e:
            print("process_turn invocation failed:", e, file=sys.stderr)
            sys.exit(4)
    except Exception as e:
        print("process_turn raised:", e, file=sys.stderr)
        sys.exit(5)

    # print JSON array of emitted events
    if args.pretty:
        print(json.dumps(emitted, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(emitted, ensure_ascii=False))


if __name__ == "__main__":
    main()
