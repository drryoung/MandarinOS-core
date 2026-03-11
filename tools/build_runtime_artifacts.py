# tools/build_runtime_artifacts.py
from __future__ import annotations

import json
import random
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import sys
sys.path.insert(0, str(Path(__file__).parent))
from builders.build_frame_tokens_runtime import write_frame_tokens

def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


REPO_ROOT    = Path(__file__).resolve().parents[1]
RUNTIME_OUT  = REPO_ROOT / "runtime" / "out_phase7"
CARDS_PATH   = REPO_ROOT / "tools" / "cards" / "out" / "cards_by_id.json"
FRAME_WITH_SLOTS_TOKEN = "FRAME_WITH_SLOTS"
BUILDER_VERSION = "7.7.0"

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

            # Add 2 distractors: use frame distractor_tokens if present, else random
            explicit = [c for c in (f.get("distractor_tokens") or []) if c in cards and c != gold_token][:2]
            distractor_pool = [
                cid for cid in all_card_ids
                if cid != gold_token and cid not in explicit
            ]
            random.shuffle(distractor_pool)
            for cid in explicit:
                options.append(card_to_option(cid, cards[cid], is_gold=False, is_slot=False))
            for cid in distractor_pool[: 2 - len(explicit)]:
                options.append(card_to_option(cid, cards[cid], is_gold=False, is_slot=False))

        else:
            # Non-slotted: gold = option_tokens[0]
            gold_token = option_tokens[0] if option_tokens else None
            if gold_token and gold_token in cards:
                options.append(card_to_option(gold_token, cards[gold_token], is_gold=True))
            else:
                print(f"[build] WARNING: gold token {gold_token!r} not in cards for frame {frame_id}")

            # 2 distractors: use frame distractor_tokens if present, else random
            explicit = [c for c in (f.get("distractor_tokens") or []) if c in cards and c != gold_token][:2]
            distractor_pool = [
                cid for cid in all_card_ids
                if cid != gold_token and cid not in explicit
            ]
            random.shuffle(distractor_pool)
            for cid in explicit:
                options.append(card_to_option(cid, cards[cid], is_gold=False))
            for cid in distractor_pool[: 2 - len(explicit)]:
                options.append(card_to_option(cid, cards[cid], is_gold=False))

        # Shuffle so gold is not always first
        gold_items       = [o for o in options if o["is_gold"]]
        non_gold_items   = [o for o in options if not o["is_gold"]]
        random.shuffle(non_gold_items)
        combined = non_gold_items + gold_items
        random.shuffle(combined)

        frame_options[frame_id] = {
            "options":          combined,
            "hint_affordance":  { "visible": True }   # §2.4 — always visible in tap mode
        }

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


def check_frame_slot_invariant(all_frames: list, built_options: dict) -> list:
    """§3.2 — verify every slotted frame has a FRAME_WITH_SLOTS option in built output."""
    violations = []
    for f in all_frames:
        if not f.get("slots"):
            continue
        frame_id = f["id"]
        frame_data = built_options.get(frame_id, {})
        options    = frame_data.get("options", []) if isinstance(frame_data, dict) else frame_data
        has_slot_option = any(o.get("kind") == FRAME_WITH_SLOTS_TOKEN for o in options)
        if not has_slot_option:
            violations.append({
                "frame_id":        frame_id,
                "frame_text":      f.get("text", ""),
                "slots":           f.get("slots", []),
                "option_tokens":   f.get("option_tokens") or [],
                "options_snapshot": options,
                "failure_reason":  "no_FRAME_WITH_SLOTS_option_in_built_output"
            })
    return violations



def build_frame_render_tokens(all_frames: list, cards: dict) -> dict:
    """Build per-frame token lists for sentence rendering.

    Patch A: lit tokens carry id=null; word tokens carry the correct word_id.
    Patch B: gold is NOT encoded here — gold lives only in frame_options.runtime.json.
    Tokenisation is about reading & lookup, not answer selection.
    """
    hanzi_to_word_id = {}
    for word_id, card in cards.items():
        hanzi = card.get("content", {}).get("headword", {}).get("hanzi", "")
        if hanzi:
            hanzi_to_word_id[hanzi] = word_id

    sorted_hanzi = sorted(hanzi_to_word_id.keys(), key=len, reverse=True)

    result = {}
    for f in all_frames:
        frame_id = f["id"]
        text     = f.get("text", "")
        tokens   = []

        i = 0
        while i < len(text):
            matched = False
            for hanzi in sorted_hanzi:
                if text[i:i+len(hanzi)] == hanzi:
                    tokens.append({"t": "word", "id": hanzi_to_word_id[hanzi], "text": hanzi})
                    i += len(hanzi)
                    matched = True
                    break
            if not matched:
                tokens.append({"t": "lit", "id": None, "text": text[i]})
                i += 1

        word_count = sum(1 for t in tokens if t["t"] == "word")
        lit_with_id = [t for t in tokens if t["t"] == "lit" and t["id"] is not None]
        if word_count == 0 and text and not f.get("slots"):
            print(f"[build][sanity] WARNING: no word tokens in frame {frame_id!r} — text={text!r}")
        if lit_with_id:
            print(f"[build][sanity] ERROR: lit tokens with id in frame {frame_id!r}: {lit_with_id}")

        result[frame_id] = tokens

    return result


def build_cards_index(all_frames: list, render_tokens: dict) -> dict:
    """Map word_id -> card_id for every word token across all rendered frames.
    Indexes option_tokens AND all word tokens from render_tokens (e.g. w_ma, w_ni).
    """
    by_word_id = {}
    # Index option_tokens
    for f in all_frames:
        for word_id in (f.get("option_tokens") or []):
            by_word_id[word_id] = word_id
    # Index all word tokens from render output
    for frame_id, tokens in render_tokens.items():
        for tok in tokens:
            if tok.get("t") == "word" and tok.get("id"):
                by_word_id[tok["id"]] = tok["id"]
    return {"by_word_id": by_word_id}


def build_word_etymology(cards: dict, char_links: list, char_by_id: dict) -> tuple[dict, dict]:
    """
    Phase 7.7 — build word_etymology.runtime.json keyed by word_id.
    Option C: silently skip character_ids missing from characters_1200.json.
    Missing etymology/mnemonic fields → omit key entirely.
    Returns (result, build_report).
    """
    result       = {}
    missing_cids = {}  # word_id -> [character_id, ...]

    for link in char_links:
        word_id   = link["word_id"]
        chars_out = []

        for c in link.get("characters", []):
            cid   = c["character_id"]
            entry = char_by_id.get(cid)
            if entry is None:
                # Option C — skip silently, record for build report only
                missing_cids.setdefault(word_id, []).append(cid)
                continue

            char_record = {
                "char":         entry["hanzi"],
                "character_id": cid,
            }

            decomp = entry.get("decomposition", "")
            if decomp:
                char_record["decomposition"] = decomp

            radical = entry.get("primary_radical", "")
            if radical:
                char_record["radical"] = radical

            etym = entry.get("etymology", "")
            if etym and isinstance(etym, dict) and any(v for v in etym.values()):
                char_record["etymology"] = etym

            mnem = entry.get("mnemonic", "")
            if mnem and isinstance(mnem, dict) and any(v for v in mnem.values()):
                char_record["mnemonic"] = mnem

            chars_out.append(char_record)

        # Always include word_id even if zero valid characters after filtering
        result[word_id] = {
            "hanzi":      link.get("word_hanzi", "").strip(),
            "characters": chars_out
        }

    build_report = {
        "missing_character_id_count": sum(len(v) for v in missing_cids.values()),
        "affected_word_ids":          list(missing_cids.keys()),
        "missing_by_word":            missing_cids
    }
    return result, build_report


def main():
    import subprocess
    git_commit = "unknown"
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        pass

    print(f"[build] Phase 7.7 runtime artifact builder v{BUILDER_VERSION} — {_now_iso()} — commit {git_commit}")
    RUNTIME_OUT.mkdir(parents=True, exist_ok=True)

    all_frames = load_all_frames()
    cards      = load_cards()

    # ── 1. Build frame options (must come first) ──────────────────────────────
    frame_options, option_violations = build_frame_options(all_frames, cards)

    # ── 2. Frame-slot invariant check §3.2 (uses built options) ──────────────
    slot_violations = check_frame_slot_invariant(all_frames, frame_options)
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
            print(f"  {v['frame_id']}: {v.get('option_tokens',[])} — {v['failure_reason']}")
        print(f"[build] violations written to {slot_viol_path}")
        print(f"[build] NOTE: builder continues in Phase 7.4 — FRAME_WITH_SLOTS is synthetic")
    else:
        print(f"[build] frame-slot invariant OK")

    # ── 3. Write frame_options ────────────────────────────────────────────────
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
    print(f"[build] frame_options written: {len(frame_options)} frames -> {options_path}")

    # ── 4. Build and write frame_render_tokens ────────────────────────────────
    render_tokens = build_frame_render_tokens(all_frames, cards)
    tokens_path   = RUNTIME_OUT / "frame_render_tokens.runtime.json"
    tokens_path.write_text(
        json.dumps({
            "schema":       "frame_render_tokens_v1",
            "generated_at": _now_iso(),
            "frame_count":  len(render_tokens),
            "frames":       render_tokens
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[build] frame_render_tokens written: {len(render_tokens)} frames -> {tokens_path}")

    # ── 4b. Phase 7.3 — Build frame_tokens (canonical) + frame_render_tokens (compat alias) ──
    _words_paths  = [REPO_ROOT / "p1_words.json", REPO_ROOT / "p2_words.json"]
    _frames_paths = [REPO_ROOT / "p1_frames.json", REPO_ROOT / "p2_frames.json"]
    _ft_serialised, _ft_unknown, _ft_frame_count = write_frame_tokens(
        frames_paths=_frames_paths,
        words_paths=_words_paths,
        out_dir=RUNTIME_OUT,
    )
    _ft_sha = hashlib.sha256(_ft_serialised.encode("utf-8")).hexdigest()

    # ── 5. Build and write cards_index ────────────────────────────────────────
    cards_index = build_cards_index(all_frames, render_tokens)
    index_path  = RUNTIME_OUT / "cards_index.runtime.json"
    index_path.write_text(
        json.dumps({
            "schema":       "cards_index_v1",
            "generated_at": _now_iso(),
            "entry_count":  len(cards_index["by_word_id"]),
            "by_word_id":   cards_index["by_word_id"]
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[build] cards_index written -> {index_path}")

    # ── 6. Load etymology source data ─────────────────────────────────────────
    char_links_path = REPO_ROOT / "word_character_links.json"
    chars_path      = REPO_ROOT / "characters_1200.json"

    if not char_links_path.is_file():
        print(f"[build] WARNING: word_character_links.json not found — skipping etymology build")
    elif not chars_path.is_file():
        print(f"[build] WARNING: characters_1200.json not found — skipping etymology build")
    else:
        char_links_data = json.loads(char_links_path.read_text(encoding="utf-8"))
        chars_data      = json.loads(chars_path.read_text(encoding="utf-8"))
        char_by_id      = { c["id"]: c for c in chars_data.get("characters", []) }
        char_links      = char_links_data.get("links", [])

        print(f"[build] etymology source: {len(char_links)} word links, {len(char_by_id)} characters")

        # ── 7. Build and write word_etymology ─────────────────────────────────
        word_etymology, build_report = build_word_etymology(cards, char_links, char_by_id)

        missing_count = build_report["missing_character_id_count"]
        if missing_count:
            print(f"[build] Missing character_ids filtered (Option C): {missing_count}")
            print(f"[build] Affected word_ids: {build_report['affected_word_ids']}")
        else:
            print(f"[build] etymology: all character_ids resolved OK")

        etym_path = RUNTIME_OUT / "word_etymology.runtime.json"
        etym_path.write_text(
            json.dumps({
                "schema":        "word_etymology_v1",
                "build_version": BUILDER_VERSION,
                "build_date":    _now_iso(),
                "git_commit":    git_commit,
                "word_count":    len(word_etymology),
                "build_report":  build_report,
                "words":         word_etymology
            }, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"[build] word_etymology written: {len(word_etymology)} words -> {etym_path}")

    print(f"\n[build] Phase 7.7 build complete. v{BUILDER_VERSION} commit={git_commit}")

    # ── Manifest update ───────────────────────────────────────────────────────
    manifest_path = RUNTIME_OUT / "build_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"builder": str(Path(__file__).name), "inputs": {}, "outputs": {}}

    manifest["outputs"]["frame_tokens_runtime_path"]         = str(RUNTIME_OUT / "frame_tokens.runtime.json")
    manifest["outputs"]["frame_tokens_runtime_sha256"]       = _ft_sha
    manifest["outputs"]["frame_tokens_runtime_count"]        = _ft_frame_count
    manifest["outputs"]["frame_render_tokens_runtime_path"]  = str(RUNTIME_OUT / "frame_render_tokens.runtime.json")
    manifest["outputs"]["frame_render_tokens_runtime_sha256"] = _ft_sha
    manifest["outputs"]["frame_render_tokens_runtime_count"] = _ft_frame_count

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8"
    )
    print(f"[build] manifest updated -> {manifest_path}")


if __name__ == "__main__":
    main()











