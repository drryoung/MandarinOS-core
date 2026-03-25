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


def load_best_characters_1200() -> tuple[Path | None, dict | None]:
    """
    Load characters_1200 from repo root and/or data/.
    If both exist (e.g. tiny sample at root + full corpus in data/), prefer the file with more rows.
    """
    best_path: Path | None = None
    best_blob: dict | None = None
    best_n = -1
    for p in (
        REPO_ROOT / "characters_1200.json",
        REPO_ROOT / "data" / "characters_1200.json",
    ):
        if not p.is_file():
            continue
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(blob, dict):
            continue
        n = len(blob.get("characters") or [])
        if n > best_n:
            best_n = n
            best_path = p
            best_blob = blob
    return best_path, best_blob
CARDS_PATH   = REPO_ROOT / "tools" / "cards" / "out" / "cards_by_id.json"
CONTENT_RECOVERY = REPO_ROOT / "content" / "recovery_phrases.json"
P1_FILLERS   = REPO_ROOT / "p1_fillers.json"
P2_FILLERS   = REPO_ROOT / "p2_fillers.json"
FRAME_WITH_SLOTS_TOKEN = "FRAME_WITH_SLOTS"
BUILDER_VERSION = "7.7.1"  # Phase 10.7-A: move_type copy-through added

# Optional: inferred word-level etymology narratives (SUBTLEX-top curated subset).
WORD_NARRATIVE_JSON = REPO_ROOT / "data" / "word_etymology_top1000_curated_v2_inferred_narrative.json"

random.seed(42)  # deterministic distractor selection


def _package_narrative_row(src: dict) -> dict:
    """Subset for runtime JSON (drop heavy subtlex counts)."""
    slim = {
        "hanzi":        src.get("hanzi"),
        "pinyin":       src.get("pinyin"),
        "gloss_en":     src.get("gloss_en"),
        "subtlex_rank": src.get("subtlex_rank"),
        "etymology":    src.get("etymology"),
    }
    return {k: v for k, v in slim.items() if v is not None}


def merge_inferred_word_narratives(words: dict, narrative_path: Path) -> dict:
    """
    Mutates words: adds word_narrative when full headword matches narrative hanzi;
    else adds glyph_narrative on each character row whose char appears in the narrative index.
    First occurrence of each hanzi in the narrative file wins (list is SUBTLEX-ordered).
    """
    stats: dict = {
        "source":             None,
        "words_with_word_narrative": 0,
        "glyph_slots_with_narrative": 0,
        "skipped_no_file":    False,
    }
    if not narrative_path.is_file():
        stats["skipped_no_file"] = True
        return stats
    stats["source"] = str(narrative_path.relative_to(REPO_ROOT))
    try:
        raw = json.loads(narrative_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        stats["error"] = str(e)
        return stats
    if not isinstance(raw, list):
        stats["error"] = "expected JSON array"
        return stats
    by_hz: dict[str, dict] = {}
    for row in raw:
        if not isinstance(row, dict):
            continue
        hz = (row.get("hanzi") or "").strip()
        if hz and hz not in by_hz:
            by_hz[hz] = row

    for entry in words.values():
        wh = (entry.get("hanzi") or "").strip()
        if wh in by_hz:
            entry["word_narrative"] = _package_narrative_row(by_hz[wh])
            stats["words_with_word_narrative"] += 1
            continue
        for ch in entry.get("characters") or []:
            g = (ch.get("char") or "").strip()
            if g in by_hz:
                ch["glyph_narrative"] = _package_narrative_row(by_hz[g])
                stats["glyph_slots_with_narrative"] += 1
    return stats

# Question frames that get full-sentence options from their answer frame (template + fillers)
QUESTION_FRAME_SENTENCE_OPTIONS = {
    "f_ask_you_name": "frame.identity.name",                # 你叫什么名字？ → 我叫小明。 etc.
    "f_ask_name_meaning": "frame.identity.name_meaning",     # 你的名字是什么意思？ → 我的名字意思是光明。 etc.
    "f_from_where": "frame.identity.nationality",            # 你是哪里人？ → 我是中国人。 etc.
    "frame.location.live_question": "frame.location.live",  # 你现在住哪里？ → 我现在住在北京。 etc.
    "f_what_work": "f_i_am_job",                             # 你做什么工作？ → 我是老师。 etc.
    "f_what_hobby": "f_i_like_hobby",                        # 你有什么爱好？ → 我喜欢看书。 etc.
    "f_like_do_what": "f_i_like_hobby",                     # 你喜欢做什么？ → 我喜欢看书。 etc.
    "f_weekend_do": "f_weekend_hobby",                       # 你周末做什么？ → 我周末看书。 etc.
    "f_like_what": "f_i_like_cultural",                     # 你喜欢什么？ → 我喜欢书法。 etc. (cultural)
    "f_collect_what": "f_i_collect",                         # 你收藏什么吗？ → 我收藏茶。 etc.
    "f_travel_where": "f_been_to_place",                     # 你去过哪里？ → 我去过北京。 etc.
    "f_want_go_where": "f_want_go_place",                    # 你想去哪里？ → 我想去上海。 etc.
    "f_food_what_good": "f_food_there_is",                   # 那儿有什么好吃的？ → 有很多火锅。 etc.
    "f_food_famous_dish": "f_food_famous_answer",            # 最有名的菜是什么？ → 最有名的是饺子。 etc.
}


def load_fillers() -> dict:
    """Load filler lists from p1_fillers and p2_fillers. Returns fillers dict (e.g. fillers.nationalities -> list)."""
    out = {}
    for path in [P1_FILLERS, P2_FILLERS]:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            for key, vals in (data.get("fillers") or {}).items():
                if isinstance(vals, list) and key not in out:
                    out[key] = list(vals)
                elif isinstance(vals, list) and key in out:
                    out[key] = list(out[key]) + [v for v in vals if v not in out[key]]
    return out


def _sentence_options_for_question(question_frame_id: str, answer_frame: dict, fillers: dict) -> list:
    """Build 3 full-sentence options from answer frame template + fillers. First is gold. Returns list of option dicts."""
    template = (answer_frame.get("text") or "").strip()
    slots = answer_frame.get("slots") or []
    if not template or not slots:
        return []
    slot_name = slots[0].get("name") or ""
    source = (slots[0].get("source") or "").strip()
    if not slot_name or not source:
        return []
    if source.startswith("fillers."):
        key = source.replace("fillers.", "").strip()
        pool = fillers.get(key) if fillers else None
    else:
        pool = None
    if not pool or not isinstance(pool, list):
        return []
    placeholders = ["{" + slot_name + "}"]
    # Pick 3 fillers deterministically (same seed) so build is reproducible
    indices = [0, 1, 2] if len(pool) >= 3 else list(range(len(pool)))
    if len(pool) < 3:
        indices = indices + [0] * (3 - len(indices))
    chosen = [pool[i % len(pool)] for i in indices[:3]]
    text_en = (answer_frame.get("text_en") or "").strip()
    card_id = answer_frame.get("id") or question_frame_id
    options = []
    for i, filler in enumerate(chosen):
        hanzi = template
        for ph in placeholders:
            hanzi = hanzi.replace(ph, filler)
        options.append({
            "card_id":  card_id,
            "hanzi":    hanzi,
            "pinyin":   "",
            "meaning":  text_en,
            "is_gold":  i == 0,  # One suggested response for this turn (conversation-sustaining); not "correct answer"
            "is_slot":  False,
            "kind":     "WORD",
        })
    return options


def build_recovery_phrases_runtime() -> dict:
    """Load content/recovery_phrases.json and return runtime shape. Fallback if file missing."""
    if CONTENT_RECOVERY.is_file():
        data = json.loads(CONTENT_RECOVERY.read_text(encoding="utf-8"))
        phrases = data.get("phrases", [])
        default_id = data.get("default_for_not_understood")
        return {"phrases": phrases, "default_for_not_understood": default_id}
    # Fallback so build never fails
    return {
        "phrases": [
            {"id": "shenme", "hanzi": "什么？", "pinyin": "shénme", "text_en": "What?", "level": "P1", "use": "not_understood"},
            {"id": "zai_shuo_yi_ci", "hanzi": "再说一次", "pinyin": "zài shuō yí cì", "text_en": "Say it again", "level": "P1"},
        ],
        "default_for_not_understood": "shenme",
    }


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


def build_frame_options(all_frames: list, cards: dict, fillers: dict | None = None) -> tuple:
    all_card_ids = list(cards.keys())
    frame_options = {}
    violations = []
    frames_by_id = {f["id"]: f for f in all_frames}
    fillers = fillers or load_fillers()

    # Phase 11.1: build per-engine card pool so distractors stay domain-relevant.
    # Include both option_tokens and distractor_tokens from all frames in the same engine.
    engine_card_pool: dict[str, list[str]] = {}
    for _f in all_frames:
        _eng = (_f.get("engine") or "").strip().lower()
        if not _eng:
            continue
        _pool = engine_card_pool.setdefault(_eng, [])
        for _tok in (_f.get("option_tokens") or []):
            if _tok in cards and _tok not in _pool:
                _pool.append(_tok)
        for _tok in (_f.get("distractor_tokens") or []):
            if _tok in cards and _tok not in _pool:
                _pool.append(_tok)

    for f in all_frames:
        frame_id     = f["id"]
        is_slotted   = bool(f.get("slots"))
        option_tokens = f.get("option_tokens") or []
        frame_engine  = (f.get("engine") or "").strip().lower()

        # Phase 11.1: prefer same-engine cards as distractors; fall back to global pool.
        _same_engine_pool = [
            cid for cid in (engine_card_pool.get(frame_engine) or [])
        ]
        _fallback_pool = [cid for cid in all_card_ids if cid not in _same_engine_pool]

        def _build_distractor_pool(exclude: set) -> list[str]:
            primary = [c for c in _same_engine_pool if c not in exclude]
            secondary = [c for c in _fallback_pool if c not in exclude]
            random.shuffle(primary)
            random.shuffle(secondary)
            return primary + secondary

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

            # Add 2 distractors: use frame distractor_tokens if present, else same-engine pool
            explicit = [c for c in (f.get("distractor_tokens") or []) if c in cards and c != gold_token][:2]
            distractor_pool = _build_distractor_pool({gold_token} | set(explicit))
            for cid in explicit:
                options.append(card_to_option(cid, cards[cid], is_gold=False, is_slot=False))
            for cid in distractor_pool[: 2 - len(explicit)]:
                options.append(card_to_option(cid, cards[cid], is_gold=False, is_slot=False))

        else:
            # Non-slotted: use sentence options for mapped question frames, else word-card options
            answer_frame_id = QUESTION_FRAME_SENTENCE_OPTIONS.get(frame_id)
            answer_frame = frames_by_id.get(answer_frame_id) if answer_frame_id else None
            sentence_opts = _sentence_options_for_question(frame_id, answer_frame, fillers) if answer_frame else []

            if sentence_opts:
                options = sentence_opts
            else:
                gold_token = option_tokens[0] if option_tokens else None
                if gold_token and gold_token in cards:
                    options.append(card_to_option(gold_token, cards[gold_token], is_gold=True))
                else:
                    print(f"[build] WARNING: gold token {gold_token!r} not in cards for frame {frame_id}")

                explicit = [c for c in (f.get("distractor_tokens") or []) if c in cards and c != gold_token][:2]
                distractor_pool = _build_distractor_pool({gold_token} | set(explicit))
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

        fo_entry: dict = {
            "options":         combined,
            "hint_affordance": {"visible": True},  # §2.4 — always visible in tap mode
        }
        # Phase 10.7 — copy declarative move_type metadata when present on source frame.
        # Selector does NOT use these yet (Phase C is deferred); they are metadata only.
        if f.get("move_type"):
            fo_entry["move_type"] = f["move_type"]
        if f.get("allowed_response_roles"):
            fo_entry["allowed_response_roles"] = list(f["allowed_response_roles"])

        frame_options[frame_id] = fo_entry

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


def build_word_etymology(
    cards: dict, char_links: list, char_by_id: dict, char_by_hanzi: dict
) -> tuple[dict, dict]:
    """
    Phase 7.7 — build word_etymology.runtime.json keyed by word_id.
    Option C: silently skip character_ids missing from characters_1200.json.
    Missing etymology/mnemonic fields → omit key entirely.
    If character_id misses (e.g. c_de vs c_auto_* in a newer master), resolve by link row hanzi.
    Returns (result, build_report).
    """
    result       = {}
    missing_cids = {}  # word_id -> [character_id, ...]

    for link in char_links:
        word_id   = link["word_id"]
        chars_out = []

        for c in link.get("characters", []):
            cid = c.get("character_id")
            hz_link = (c.get("hanzi") or "").strip()
            entry = char_by_id.get(cid) if cid else None
            if entry is None and hz_link:
                entry = char_by_hanzi.get(hz_link)
            if entry is None:
                # Option C — skip silently, record for build report only
                missing_cids.setdefault(word_id, []).append(cid or hz_link or "?")
                continue

            char_record = {
                "char":         entry.get("hanzi") or hz_link,
                "character_id": entry.get("id", cid),
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

    # ── 5b. Build and write recovery_phrases (Phase 9.4) ───────────────────────
    recovery_data = build_recovery_phrases_runtime()
    recovery_path = RUNTIME_OUT / "recovery_phrases.runtime.json"
    recovery_path.write_text(
        json.dumps({
            "schema":         "recovery_phrases_v1",
            "generated_at":   _now_iso(),
            "phrase_count":   len(recovery_data["phrases"]),
            "phrases":        recovery_data["phrases"],
            "default_for_not_understood": recovery_data.get("default_for_not_understood"),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[build] recovery_phrases written: {len(recovery_data['phrases'])} phrases -> {recovery_path}")

    # ── 6. Load etymology source data ─────────────────────────────────────────
    char_links_path = REPO_ROOT / "word_character_links.json"
    chars_path, chars_data = load_best_characters_1200()

    if not char_links_path.is_file():
        print(f"[build] WARNING: word_character_links.json not found — skipping etymology build")
    elif chars_path is None or chars_data is None:
        print(f"[build] WARNING: characters_1200.json not found (tried repo root and data/) — skipping etymology build")
    else:
        char_links_data = json.loads(char_links_path.read_text(encoding="utf-8"))
        characters_list = chars_data.get("characters", []) if isinstance(chars_data, dict) else []
        char_by_id = {c["id"]: c for c in characters_list if c.get("id")}
        char_by_hanzi = {}
        for c in characters_list:
            hz = (c.get("hanzi") or "").strip()
            if hz and hz not in char_by_hanzi:
                char_by_hanzi[hz] = c
        char_links = char_links_data.get("links", [])

        print(f"[build] etymology chars file: {chars_path.relative_to(REPO_ROOT)}")
        print(f"[build] etymology source: {len(char_links)} word links, {len(char_by_id)} characters by id, {len(char_by_hanzi)} by hanzi")

        # ── 7. Build and write word_etymology ─────────────────────────────────
        word_etymology, build_report = build_word_etymology(
            cards, char_links, char_by_id, char_by_hanzi
        )

        narrative_stats = merge_inferred_word_narratives(word_etymology, WORD_NARRATIVE_JSON)
        build_report["narrative_merge"] = narrative_stats
        if narrative_stats.get("skipped_no_file"):
            print(f"[build] word narrative: file not found — {WORD_NARRATIVE_JSON.name} (optional)")
        elif narrative_stats.get("error"):
            print(f"[build] word narrative: skipped — {narrative_stats['error']}")
        else:
            print(
                f"[build] word narrative: {narrative_stats.get('words_with_word_narrative', 0)} word hit(s), "
                f"{narrative_stats.get('glyph_slots_with_narrative', 0)} glyph slot(s) from {narrative_stats.get('source')}"
            )

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











