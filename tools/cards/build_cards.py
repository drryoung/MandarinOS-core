#!/usr/bin/env python3
"""
Build cards.json and cards_index.json according to directive.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Warning: failed to parse JSON {p}: {e}")
        return {}


def resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_config(repo_root: Path) -> Dict[str, Any]:
    return {
        "words_files": ["p1_words.json", "p2_words.json"],
        "links_file": "word_character_links.json",
        "characters_file": "characters_1200.json",
        "output_dir": "tools/cards/out",
        "card_id_strategy": "word_id",
        "include_pack": True,
    }


def build_char_index(chars_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    idx = {}
    for c in chars_data.get("characters", []):
        cid = c.get("id")
        if not cid:
            continue
        idx[cid] = c
    # components index optional
    comp_idx = {}
    for comp in chars_data.get("components_index", []):
        if comp.get("id"):
            comp_idx[comp["id"]] = comp
    return {"chars": idx, "components": comp_idx}


def load_links(links_data: Dict[str, Any]) -> Dict[str, Any]:
    mapping = {}
    for l in links_data.get("links", []):
        wid = l.get("word_id")
        if not wid:
            continue
        mapping[wid] = l
    return mapping


def collect_words(repo_root: Path, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    words = []
    for wf in cfg.get("words_files", []):
        p = repo_root / wf
        if not p.exists():
            print(f"Warning: words file missing: {wf}")
            continue
        data = load_json(p)
        # support top-level "words" or list
        if isinstance(data, dict) and isinstance(data.get("words"), list):
            src = data.get("words")
        elif isinstance(data, list):
            src = data
        else:
            src = []
        # attach pack info if requested
        pack_label = None
        if cfg.get("include_pack"):
            # infer from filename
            if "p1" in wf.lower():
                pack_label = "p1"
            elif "p2" in wf.lower():
                pack_label = "p2"
        for w in src:
            w = dict(w)
            if pack_label:
                w.setdefault("pack", pack_label)
            words.append(w)
    return words


def build_card_for_word(word: Dict[str, Any], links_map: Dict[str, Any], char_index: Dict[str, Any]) -> Dict[str, Any]:
    # Determine card id
    word_id = word.get("id") or word.get("word_id")
    if not word_id:
        raise RuntimeError("Word missing id")
    card_id = word_id

    hanzi = word.get("hanzi") or word.get("headword")
    meaning = word.get("gloss_en") or word.get("meaning") or ""
    pinyin = word.get("pinyin")

    card: Dict[str, Any] = {
        "card_id": card_id,
        "content": {},
        "state": {
            "reveal_level": 0,
            "revealed": {
                "pinyin": False,
                "word_composition": False,
                "character_breakdown": False,
                "trace_mode": False,
            },
        },
        "actions": [],
    }

    # content.headword
    card["content"]["headword"] = {"hanzi": hanzi}
    if pinyin:
        card["content"]["headword"]["pinyin"] = pinyin
    card["content"]["headword"]["audio"] = {"tts": True}

    card["content"]["meaning"] = meaning

    # composition if present
    composition = word.get("composition") or word.get("word_composition")
    if composition:
        card["content"]["word_composition"] = composition

    # characters from links
    link = links_map.get(word_id)
    chars_list = []
    cards_missing_links = False
    if link:
        for ch in link.get("characters", []):
            cid = ch.get("character_id")
            han = ch.get("hanzi")
            role = ch.get("role")
            strength = ch.get("strength")
            char_entry = {"char": han, "role": role, "strength": strength}
            cinfo = None
            if cid and cid in char_index["chars"]:
                cinfo = char_index["chars"][cid]
            else:
                # try find by hanzi
                for k, v in char_index["chars"].items():
                    if v.get("hanzi") == han:
                        cinfo = v
                        break

            if cinfo:
                char_entry["pinyin"] = cinfo.get("pinyin")
                char_entry["meaning"] = cinfo.get("gloss_en")
                decomp = cinfo.get("decomposition") or {}
                components = decomp.get("components") if isinstance(decomp, dict) else None
                if components:
                    enriched = []
                    for comp in components:
                        comp_obj = {"glyph": comp}
                        # try map to component id meaning if present
                        # components_index maps ids to meaning, but our char data stores component ids separately
                        enriched.append(comp_obj)
                    char_entry["components"] = enriched
                # mnemonics
                if cinfo.get("mnemonic"):
                    # keep short
                    m = cinfo.get("mnemonic")
                    if isinstance(m, dict):
                        story = m.get("story") or ""
                        char_entry["mnemonic"] = (story[:200] + "...") if len(story) > 200 else story
                # handwriting
                hw = cinfo.get("handwriting") or {}
                char_entry["handwriting_support"] = {
                    "supports_drawing_input": bool(hw.get("supports_drawing_input")),
                    "stroke_order_hint_available": bool(hw.get("stroke_order_hint_available")),
                }
            else:
                char_entry["pinyin"] = None
                char_entry["meaning"] = None
                char_entry["components"] = []
                char_entry["warning_missing_in_1200"] = True
                cards_missing_links = True
            chars_list.append(char_entry)
    else:
        # no explicit link; attempt to split hanzi into chars
        cards_missing_links = True
        if hanzi:
            for ch in list(hanzi):
                cobj = {"char": ch, "role": None, "strength": None}
                # best-effort lookup
                found = None
                for k, v in char_index["chars"].items():
                    if v.get("hanzi") == ch:
                        found = v
                        break
                if found:
                    cobj["pinyin"] = found.get("pinyin")
                    cobj["meaning"] = found.get("gloss_en")
                    hw = found.get("handwriting") or {}
                    cobj["handwriting_support"] = {
                        "supports_drawing_input": bool(hw.get("supports_drawing_input")),
                        "stroke_order_hint_available": bool(hw.get("stroke_order_hint_available")),
                    }
                else:
                    cobj["warning_missing_in_1200"] = True
                chars_list.append(cobj)

    if chars_list:
        card["content"]["characters"] = chars_list

    # trace refs
    trace_mode_available = any(
        c.get("handwriting_support", {}).get("supports_drawing_input") and c.get("handwriting_support", {}).get("stroke_order_hint_available")
        for c in chars_list
    )
    if trace_mode_available:
        card["content"]["trace_refs"] = {"trace_mode_available": True, "provider_ref": "stroke_provider:pending"}

    # Build actions ensuring monotonic reveal_level
    actions = []
    current_level = 0

    def add_action_if(condition: bool, action_id: str, label: str, target_level: int, state_key: Optional[str]):
        nonlocal current_level
        if not condition:
            return
        if target_level <= current_level:
            # ensure monotonic strictly increasing
            target_level = current_level + 1
        effects = {"reveal_level": target_level}
        if state_key:
            effects.setdefault("revealed", {})[state_key] = True
        action = {"action_id": action_id, "label": label, "effects": effects}
        actions.append(action)
        current_level = target_level

    # reveal pinyin
    add_action_if(bool(pinyin), "reveal_pinyin", "Reveal pinyin", 1, "pinyin")
    # reveal composition
    add_action_if(bool(composition), "reveal_word_composition", "Reveal composition", 2, "word_composition")
    # reveal characters
    add_action_if(bool(chars_list), "reveal_characters", "Reveal characters", 3, "character_breakdown")
    # open trace
    add_action_if(trace_mode_available, "open_trace_mode", "Open trace mode", 4, "trace_mode")

    card["actions"] = actions

    # validation per contract
    validate_card(card)

    return card, cards_missing_links


def validate_card(card: Dict[str, Any]):
    # Required fields
    if not card.get("card_id"):
        raise RuntimeError("card missing card_id")
    head = card.get("content", {}).get("headword")
    if not head or not head.get("hanzi"):
        raise RuntimeError(f"card {card.get('card_id')} missing headword.hanzi")
    if not card.get("content", {}).get("meaning"):
        raise RuntimeError(f"card {card.get('card_id')} missing meaning")

    # Actions must cause state change and monotonic reveal_level
    prev_level = 0
    for a in card.get("actions", []):
        effects = a.get("effects", {})
        if "reveal_level" not in effects:
            raise RuntimeError(f"action {a.get('action_id')} has no reveal_level effect")
        rl = effects["reveal_level"]
        if rl <= prev_level:
            raise RuntimeError(f"action {a.get('action_id')} does not increase reveal_level monotonically")
        # ensure effects set revealed flag if applicable
        if any(k in effects.get("revealed", {}) for k in ("pinyin", "word_composition", "character_breakdown", "trace_mode")):
            pass
        prev_level = rl


def build_index(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_word_id = {}
    by_hanzi = {}
    for c in cards:
        cid = c.get("card_id")
        head = c.get("content", {}).get("headword", {})
        hanzi = head.get("hanzi")
        by_word_id[cid] = cid
        if hanzi:
            by_hanzi.setdefault(hanzi, []).append(cid)
    return {"by_word_id": by_word_id, "by_hanzi": by_hanzi}


def main(argv: Optional[List[str]] = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", "-c", help="path to config JSON", default=None)
    args = ap.parse_args(argv)

    repo_root = resolve_repo_root()
    cfg_path = (repo_root / "tools" / "cards" / "cards_config.json") if not args.config else Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = repo_root / cfg_path

    if cfg_path.exists():
        cfg = load_json(cfg_path)
    else:
        cfg = default_config(repo_root)

    words = collect_words(repo_root, cfg)
    links = load_links(load_json(repo_root / cfg.get("links_file")))
    chars = build_char_index(load_json(repo_root / cfg.get("characters_file")))

    out_dir = repo_root / cfg.get("output_dir", "tools/cards/out")
    out_dir.mkdir(parents=True, exist_ok=True)

    cards = []
    missing_links_count = 0
    chars_missing = 0
    trace_enabled_count = 0
    composition_count = 0

    for w in words:
        try:
            card, missing_links = build_card_for_word(w, links, chars)
        except Exception as e:
            print(f"Warning: failed to build card for word {w.get('id')}: {e}")
            continue
        cards.append(card)
        if missing_links:
            missing_links_count += 1
        if any(c.get("handwriting_support", {}).get("supports_drawing_input") for c in card.get("content", {}).get("characters", [])):
            trace_enabled_count += 1
        if card.get("content", {}).get("word_composition"):
            composition_count += 1

    # count chars missing in 1200
    for c in cards:
        for ch in c.get("content", {}).get("characters", []):
            if ch.get("warning_missing_in_1200"):
                chars_missing += 1

    cards_obj = {
        "version": "1.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "cards": cards,
    }

    cards_path = out_dir / "cards.json"
    cards_index_path = out_dir / "cards_index.json"
    cards_path.write_text(json.dumps(cards_obj, indent=2, ensure_ascii=False), encoding="utf-8")

    index = build_index(cards)
    cards_index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "total_cards": len(cards),
        "cards_missing_links": missing_links_count,
        "chars_missing_in_1200": chars_missing,
        "cards_trace_enabled_count": trace_enabled_count,
        "cards_with_composition_count": composition_count,
    }

    print("Build complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
