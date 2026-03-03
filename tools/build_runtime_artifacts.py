# tools/build_runtime_artifacts.py
from __future__ import annotations

import json
import random
from pathlib import Path
from datetime import datetime, timezone

def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


REPO_ROOT    = Path(__file__).resolve().parents[1]
RUNTIME_OUT  = REPO_ROOT / "runtime" / "out_phase7"
CARDS_PATH   = REPO_ROOT / "tools" / "cards" / "out" / "cards_by_id.json"
FRAME_WITH_SLOTS_TOKEN = "FRAME_WITH_SLOTS"

random.seed(42)  # deterministic distractor selection


def load_all_frames() -> list:
    all_frames = []
    for fname in ["p1_frames.json", "p2_frames.json"]:
        p = REPO_ROOT / fname
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            frames = data.get("frames", [])
            all_frames.extend(frames)
            print(f"[build] loaded {len(frames)} frames from {fname}")
        else:
            print(f"[build] WARNING: {fname} not found")
    return all_frames


def load_cards() -> dict:
    if not CARDS_PATH.is_file():
        raise SystemExit(f"[build] FATAL: cards not found at {CARDS_PATH}")
    cards = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    print(f"[build] loaded {len(cards)} cards")
    return cards


def card_to_option(card_id: str, card: dict, is_gold: bool, is_slot: bool = False) -> dict:
    content = card.get("content", {})
    headword = content.get("headword", {})
    return {
        "card_id":  card_id,
        "hanzi":    headword.get("hanzi", card_id),
        "pinyin":   headword.get("pinyin", ""),
        "meaning":  content.get("meaning", ""),
        "is_gold":  is_gold,
        "is_slot":  is_slot,
        "kind":     "FRAME_WITH_SLOTS" if is_slot else "WORD"
    }


def build_frame_options(all_frames: list, cards: dict) -> dict:
    all_card_ids = list(cards.keys())
    frame_options = {}
    violations = []

    for f in all_frames:
        frame_id     = f["id"]
        is_slotted   = bool(f.get("slots"))
        option_tokens = f.get("option_tokens") or []

        options = []

        if is_slotted:
            # Gold option for slotted frame = FRAME_WITH_SLOTS button
            gold_token = option_tokens[0] if option_tokens else None
            gold_card  = cards.get(gold_token) if gold_token else None

            slot_option = {
                "card_id":  gold_token or "unknown",
                "hanzi":    f["text"],   # full template e.g. 我叫{NAME}。
                "pinyin":   "",
                "meaning":  f"Fill in: {', '.join(s['name'] for s in f.get('slots', []))}",
                "is_gold":  True,
                "is_slot":  True,
                "kind":     "FRAME_WITH_SLOTS",
                "slots":    f.get("slots", [])
            }
            options.append(slot_option)

            # Add 2 distractors from non-slotted cards
            distractor_pool = [
                cid for cid in all_card_ids
                if cid != gold_token
            ]
            random.shuffle(distractor_pool)
            for cid in distractor_pool[:2]:
                options.append(card_to_option(cid, cards[cid], is_gold=False, is_slot=False))

        else:
            # Non-slotted: gold = option_tokens[0]
            gold_token = option_tokens[0] if option_tokens else None
            if gold_token and gold_token in cards:
                options.append(card_to_option(gold_token, cards[gold_token], is_gold=True))
            else:
                print(f"[build] WARNING: gold token {gold_token!r} not in cards for frame {frame_id}")

            # 2 distractors — exclude gold
            distractor_pool = [
                cid for cid in all_card_ids
                if cid != gold_token
            ]
            random.shuffle(distractor_pool)
            for cid in distractor_pool[:2]:
                options.append(card_to_option(cid, cards[cid], is_gold=False))

        # Shuffle so gold is not always first
        gold_items       = [o for o in options if o["is_gold"]]
        non_gold_items   = [o for o in options if not o["is_gold"]]
        random.shuffle(non_gold_items)
        combined = non_gold_items + gold_items
        random.shuffle(combined)

        frame_options[frame_id] = combined

        # Invariant check
        gold_count = sum(1 for o in combined if o["is_gold"])
        if len(combined) < 3 or gold_count == 0:
            violations.append({
                "frame_id":       frame_id,
                "option_count":   len(combined),
                "gold_present":   gold_count > 0,
                "failure_reason": "insufficient_options" if len(combined) < 3 else "no_gold"
            })

    return frame_options, violations


def check_frame_slot_invariant(all_frames: list) -> list:
    violations = []
    for f in all_frames:
        slots = f.get("slots")
        if not slots:
            continue
        option_tokens = f.get("option_tokens") or []
        has_slot_token = any(t == FRAME_WITH_SLOTS_TOKEN for t in option_tokens)
        if not has_slot_token:
            violations.append({
                "frame_id":       f["id"],
                "frame_text":     f.get("text", ""),
                "slots":          slots,
                "option_tokens":  option_tokens,
                "failure_reason": "no_FRAME_WITH_SLOTS_option_token"
            })
    return violations


def main():
    print(f"[build] Phase 7.4 runtime artifact builder — {datetime.now(timezone.utc).isoformat().replace("+00:00","Z")}")
    RUNTIME_OUT.mkdir(parents=True, exist_ok=True)

    all_frames = load_all_frames()
    cards      = load_cards()

    # ── 1. Frame-slot invariant check (builder-side, fail loud) ───────────────
    slot_violations = check_frame_slot_invariant(all_frames)
    slot_viol_path  = RUNTIME_OUT / "slot_invariant_violations.runtime.json"
    slot_viol_path.write_text(
        json.dumps({
            "schema":          "slot_invariant_violations_v1",
            "generated_at":    _now_iso(),
            "violation_count": len(slot_violations),
            "violations":      slot_violations
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    if slot_violations:
        print(f"\n[build] INVARIANT VIOLATION — frame_slot_invariant_failed")
        print(f"[build] {len(slot_violations)} slotted frame(s) missing FRAME_WITH_SLOTS token:")
        for v in slot_violations:
            print(f"  {v['frame_id']}: {v['option_tokens']} — {v['failure_reason']}")
        print(f"[build] violations written to {slot_viol_path}")
        print(f"[build] NOTE: builder continues in Phase 7.4 — FRAME_WITH_SLOTS is synthetic")
    else:
        print(f"[build] frame-slot invariant OK")

    # ── 2. Build frame options ────────────────────────────────────────────────
    frame_options, option_violations = build_frame_options(all_frames, cards)

    options_path = RUNTIME_OUT / "frame_options.runtime.json"
    options_path.write_text(
        json.dumps({
            "schema":       "frame_options_v1",
            "generated_at": _now_iso(),
            "frame_count":  len(frame_options),
            "frames":       frame_options
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[build] frame_options written: {len(frame_options)} frames → {options_path}")

    # ── 3. Frame render tokens (existing) ─────────────────────────────────────
    frt = build_frame_render_tokens(all_frames, cards)
    frt_path = RUNTIME_OUT / "frame_render_tokens.runtime.json"
    frt_path.write_text(
        json.dumps(frt, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[build] frame_render_tokens written: {len(frt['frames'])} frames → {frt_path}")

    # ── 4. Cards index (existing) ─────────────────────────────────────────────
    ci = build_cards_index(all_frames)
    ci_path = RUNTIME_OUT / "cards_index.runtime.json"
    ci_path.write_text(
        json.dumps(ci, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[build] cards_index written → {ci_path}")

    if option_violations:
        print(f"\n[build] WARNING: {len(option_violations)} frame(s) have option invariant issues:")
        for v in option_violations:
            print(f"  {v['frame_id']}: count={v['option_count']} gold={v['gold_present']}")

    print(f"\n[build] Phase 7.4 build complete.")


def build_frame_render_tokens(all_frames, cards):
    """Phase 7.3 — mark the character matching the gold card hanzi as word token."""
    import re
    frames_out = {}

    for f in all_frames:
        frame_id      = f["id"]
        text          = f.get("text", "")
        option_tokens = f.get("option_tokens") or []
        gold_token    = option_tokens[0] if option_tokens else None
        slots         = f.get("slots") or []

        # Find the gold card's hanzi so we can mark the right character
        gold_hanzi = None
        if gold_token and gold_token in cards:
            gold_hanzi = (
                cards[gold_token]
                .get("content", {})
                .get("headword", {})
                .get("hanzi", "")
            )

        final_tokens = []
        word_assigned = False
        parts = re.split(r'(\{[A-Z_]+\})', text)

        for part in parts:
            m = re.match(r'\{([A-Z_]+)\}', part)
            if m:
                final_tokens.append({"t": "slot", "id": m.group(1), "text": part})
            else:
                for ch in part:
                    if not ch.strip():
                        final_tokens.append({"t": "lit", "id": None, "text": ch})
                        continue

                    # Mark as word token if this char matches gold hanzi
                    # and we haven't assigned a word token yet
                    is_gold_char = (
                        gold_hanzi
                        and not word_assigned
                        and ch in gold_hanzi
                    )

                    if is_gold_char:
                        final_tokens.append({"t": "word", "id": gold_token, "text": ch})
                        word_assigned = True
                    else:
                        final_tokens.append({"t": "lit", "id": None, "text": ch})

        frames_out[frame_id] = final_tokens
        if not word_assigned and gold_token:
            print(f"[build] WARNING: no word token assigned for frame {frame_id} (gold={gold_token}, hanzi={gold_hanzi!r})")

    return {"schema": "frame_render_tokens_v1", "frames": frames_out}


def build_cards_index(all_frames):
    """Map word_id -> card_id for every option token across all frames."""
    by_word_id = {}
    for f in all_frames:
        for word_id in (f.get("option_tokens") or []):
            by_word_id[word_id] = word_id
    return {"by_word_id": by_word_id}


if __name__ == "__main__":
    main()



