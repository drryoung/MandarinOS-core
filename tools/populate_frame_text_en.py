#!/usr/bin/env python3
"""
Populate text_en for frames in p1_frames.json and p2_frames.json.

- By default: only sets text_en when the frame does not already have a
  non-empty text_en (preserves manual/curated proper translations; word-for-word
  from cards_by_id is used only as fallback for empty or new frames).
- Use --force to overwrite all frames with word-for-word translations.
"""
import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = REPO_ROOT / "runtime" / "out_phase7"
CARDS_PATH = REPO_ROOT / "tools" / "cards" / "out" / "cards_by_id.json"
PACKS = ["p1_frames.json", "p2_frames.json"]


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Populate frame text_en (word-for-word fallback unless --force).")
    parser.add_argument("--force", action="store_true", help="Overwrite all text_en with word-for-word; default is to fill only when missing.")
    args = parser.parse_args()

    # Build frame_id -> list of tokens (from runtime)
    frt_path = RUNTIME / "frame_render_tokens.runtime.json"
    if not frt_path.is_file():
        print(f"[ERROR] Not found: {frt_path}")
        return 1
    frt = load_json(frt_path)
    frames_list = frt.get("frames", [])
    if isinstance(frames_list, list):
        tokens_by_frame = {item["frame_id"]: item.get("tokens", []) for item in frames_list if isinstance(item, dict) and "frame_id" in item}
    else:
        tokens_by_frame = {}

    # Build word_id -> meaning from cards_by_id
    if not CARDS_PATH.is_file():
        print(f"[ERROR] Not found: {CARDS_PATH}")
        return 1
    cards = load_json(CARDS_PATH)
    def meaning_for(word_id: str) -> str:
        entry = cards.get(word_id)
        if not entry or not isinstance(entry, dict):
            return ""
        content = entry.get("content") or {}
        return (content.get("meaning") or "").strip()

    # For each frame, build word-for-word English
    def build_text_en(frame_id: str) -> str:
        tokens = tokens_by_frame.get(frame_id, [])
        parts = []
        for tok in tokens:
            kind = (tok.get("kind") or tok.get("t") or "").lower()
            if kind == "word" and tok.get("word_id"):
                meaning = meaning_for(tok["word_id"])
                if meaning:
                    parts.append(meaning)
            elif kind == "slot" and tok.get("slot_name"):
                parts.append(f"[{tok['slot_name']}]")
        return " ".join(parts).strip()

    filled = 0
    preserved = 0
    for pack_name in PACKS:
        pack_path = REPO_ROOT / pack_name
        if not pack_path.is_file():
            print(f"[SKIP] Not found: {pack_path}")
            continue
        data = load_json(pack_path)
        frames = data.get("frames", [])
        if not isinstance(frames, list):
            continue
        for fr in frames:
            if not isinstance(fr, dict) or "id" not in fr:
                continue
            frame_id = fr["id"]
            existing = (fr.get("text_en") or "").strip()
            if existing and not args.force:
                preserved += 1
                continue
            text_en = build_text_en(frame_id)
            fr["text_en"] = text_en
            if text_en:
                filled += 1
        with open(pack_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[OK] Wrote {pack_name} ({len(frames)} frames)")
    print(f"[DONE] Filled text_en for {filled} frames; preserved existing for {preserved} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
