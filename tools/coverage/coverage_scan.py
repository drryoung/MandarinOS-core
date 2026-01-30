#!/usr/bin/env python3
"""
MandarinOS Content Coverage Scanner v1

Implements the directive at project root: MandarinOS_content_coverage_scanner_v1_directive.txt

Usage:
  python tools/coverage/coverage_scan.py
  python tools/coverage/coverage_scan.py --config tools/coverage/coverage_config.json

Only uses Python standard library.
"""

import argparse
import fnmatch
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def resolve_repo_root() -> Path:
    # tools/coverage/coverage_scan.py -> repo root is two parents up
    return Path(__file__).resolve().parents[2]


def gather_files(repo_root: Path, cfg: Dict[str, Any]) -> List[Path]:
    files: List[Path] = []

    content_files = cfg.get("content_files", []) or []
    content_globs = cfg.get("content_globs", []) or []
    exclude_globs = cfg.get("exclude_globs", []) or []

    for fn in content_files:
        p = repo_root / fn
        if p.exists():
            files.append(p)
        else:
            print(f"Warning: declared content file not found: {fn}")

    # globs relative to repo root
    for g in content_globs:
        for p in sorted(repo_root.glob(g)):
            files.append(p)

    # if nothing declared, try common files in repo root
    if not files:
        for p in sorted(repo_root.glob("*.json")):
            files.append(p)

    # apply exclude_globs
    if exclude_globs:
        filtered: List[Path] = []
        for p in files:
            rel = str(p.relative_to(repo_root))
            if any(fnmatch.fnmatch(rel, ex) for ex in exclude_globs):
                continue
            filtered.append(p)
        files = filtered

    # unique preserve order
    seen = set()
    out = []
    for p in files:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def detect_file_type(p: Path, data: Any) -> str:
    name = p.name.lower()
    if name.startswith("diagnostic_"):
        return "diagnostic"
    if isinstance(data, dict):
        if "frames" in data:
            return "frames"
        if "fillers" in data:
            return "fillers"
        if "words" in data:
            return "words"
        if "engines" in data:
            return "engines"
        if "tasks" in data or "diagnostic" in data:
            return "diagnostic"
    if isinstance(data, list):
        # peek first item
        if data:
            item = data[0]
            if isinstance(item, dict):
                if "frame_id" in item:
                    return "frames"
                if "filler_id" in item:
                    return "fillers"
                if "word_id" in item:
                    return "words"
                if "engine_id" in item:
                    return "engines"
    if "frames" in name:
        return "frames"
    if "fillers" in name:
        return "fillers"
    if "words" in name:
        return "words"
    if "engines" in name:
        return "engines"
    return "unknown"


def extract_frames_from_file(p: Path, data: Any) -> List[Dict[str, Any]]:
    # Return list of candidate frame dicts
    if isinstance(data, dict):
        if "frames" in data and isinstance(data["frames"], list):
            return data["frames"]
        # some files may store frames at top-level list-like under another key
        # fallback: search for list values containing frame-like items
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "frame_id" in v[0]:
                return v
    if isinstance(data, list):
        # list of frames
        return [i for i in data if isinstance(i, dict) and ("frame_id" in i or "id" in i)]
    return []


def normalize_frame_id(frame: Dict[str, Any]) -> Optional[str]:
    if "frame_id" in frame:
        return str(frame["frame_id"])
    if "id" in frame:
        return str(frame["id"])
    return None


def get_required_slots(frame: Dict[str, Any]) -> List[str]:
    if "required_slots" in frame and isinstance(frame["required_slots"], list):
        return frame["required_slots"]
    slots = frame.get("slots") or {}
    if isinstance(slots, dict):
        req = slots.get("required")
        if isinstance(req, list):
            return req
    return []


def get_selectors_present(frame: Dict[str, Any]) -> List[str]:
    slots = frame.get("slots") or {}
    if isinstance(slots, dict):
        sel = slots.get("selectors_present") or slots.get("selectors")
        if isinstance(sel, list):
            return sel
    # fallback
    sel = frame.get("slot_selectors") or frame.get("selectors")
    if isinstance(sel, list):
        return sel
    return []


def has_tokens_for_slot(frame: Dict[str, Any], slot: str) -> bool:
    # naive: check tokens or examples present
    tokens = frame.get("tokens") or frame.get("templates") or frame.get("options")
    if isinstance(tokens, list):
        # if any token mentions slot name, assume present
        for t in tokens:
            if isinstance(t, str) and ("{" + slot + "}" in t or f"{slot}" in t):
                return True
    return False


def extract_hints(frame: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    # returns coverage: none/partial/full, and effects dict
    hints = frame.get("hints") or frame.get("hint")
    if not hints:
        return "none", {}
    # hints might be dict or list
    effects: Dict[str, Any] = {}
    if isinstance(hints, dict):
        payload = hints.get("payload") or hints
        if isinstance(payload, dict):
            effects = payload.get("effects") or payload.get("hint_effects") or {}
    elif isinstance(hints, list):
        # collect effects from list items
        for h in hints:
            if isinstance(h, dict):
                payload = h.get("payload") or h
                if isinstance(payload, dict):
                    e = payload.get("effects") or payload.get("hint_effects") or {}
                    if isinstance(e, dict):
                        effects.update(e)

    if not effects:
        return "none", {}

    stages = {k for k in ("narrow", "structure", "model") if k in effects}
    if stages == {"narrow", "structure", "model"}:
        # additional rule: if model present must include >=2 options
        model_ok = True
        if "model" in effects and isinstance(effects.get("model"), dict):
            opts = effects["model"].get("options") or []
            model_ok = len(opts) >= 2
        return ("full" if model_ok else "partial"), effects

    return ("partial" if stages else "none"), effects


def analyze_frame(frame: Dict[str, Any], src_file: str) -> Dict[str, Any]:
    fid = normalize_frame_id(frame)
    record: Dict[str, Any] = {
        "frame_id": fid,
        "file": src_file,
        "has_slots": False,
        "slots_executable": True,
        "required_slots": [],
        "selectors_present": [],
        "hint_coverage": "none",
        "hint_effects": {},
        "blockers": [],
        "scenarios": [],
        "option_tokens": [],
        "engine_id": None,
        "affordances": [],
    }

    if not fid:
        record["readiness_label"] = "READY_SCHEMA_ISSUES"
        record["blockers"].append("missing_frame_id")
        return record

    required_slots = get_required_slots(frame)
    record["required_slots"] = required_slots
    record["has_slots"] = bool(required_slots)

    selectors = get_selectors_present(frame)
    record["selectors_present"] = selectors

    # slots_executable: for each required slot, either token exists or selector present
    slots_exec = True
    blockers = []
    for s in required_slots:
        token_ok = has_tokens_for_slot(frame, s)
        selector_ok = s in selectors or bool(selectors)
        if not (token_ok or selector_ok):
            slots_exec = False
            blockers.append(f"slot_unexecutable:{s}")
    record["slots_executable"] = slots_exec

    hint_cov, effects = extract_hints(frame)
    record["hint_coverage"] = hint_cov
    record["hint_effects"] = effects

    # readiness label
    if not record.get("frame_id"):
        label = "READY_SCHEMA_ISSUES"
    elif record["has_slots"] and not record["slots_executable"]:
        label = "READY_NO_SLOTS"
    elif record["hint_coverage"] == "none":
        label = "READY_NO_HINTS"
    elif record["hint_coverage"] == "partial":
        label = "READY_HINTS_PARTIAL"
    else:
        label = "READY_FOR_APP"

    record["readiness_label"] = label

    # blockers
    if record["readiness_label"] == "READY_NO_SLOTS":
        record["blockers"].extend(blockers or ["missing_slot_selectors_or_tokens"])
    if record["readiness_label"] == "READY_NO_HINTS":
        record["blockers"].append("no_hints")
    if record["readiness_label"] == "READY_HINTS_PARTIAL":
        record["blockers"].append("partial_hints")

    # scenario heuristics
    sc = []
    if record["has_slots"]:
        sc.append("S1_basic_slot_fill")
    if record["hint_coverage"] == "full":
        sc.append("S2_hint_narrow_structure_model")
    if record["hint_coverage"] != "none":
        sc.append("S3_toggle_preserves_affordances")
        sc.append("S4_scaffolding_high_to_low")
    if record["has_slots"] and ("narrow" in record["hint_effects"]):
        sc.append("S5_narrow_then_slot_integrity")
    # S6: diagnostics referencing frame_id will be attached later by caller
    record["scenarios"] = sc

    # extract option tokens/text for later cross-referencing with cards
    opts = []
    options = frame.get("options") or frame.get("templates") or frame.get("tokens")
    if isinstance(options, list):
        for o in options:
            if isinstance(o, str):
                opts.append(o)
            elif isinstance(o, dict):
                # common fields: text, tokens, label
                if "text" in o and isinstance(o["text"], str):
                    opts.append(o["text"])
                if "tokens" in o and isinstance(o["tokens"], list):
                    for t in o["tokens"]:
                        if isinstance(t, str):
                            opts.append(t)
                if "label" in o and isinstance(o["label"], str):
                    opts.append(o["label"])
    record["option_tokens"] = opts
    # engine id and affordances from frame
    record["engine_id"] = frame.get("engine_id") or frame.get("engine")
    raw_aff = frame.get("affordances") or frame.get("affordance") or {}
    record["affordances"] = normalize_affordances(raw_aff)

    return record


def run_scan(cfg_path: Path, cards_path_arg: Optional[str] = None, cards_index_arg: Optional[str] = None):
    repo_root = resolve_repo_root()
    try:
        cfg = load_config(cfg_path)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(2)


def normalize_affordances(raw: Any) -> Dict[str, bool]:
    """Normalize affordances into a dict mapping affordance name -> True/False.

    Accepts dict, list, string, or falsy values. Returns {} when none.
    """
    out: Dict[str, bool] = {}
    if not raw:
        return out
    if isinstance(raw, dict):
        # ensure boolean values
        for k, v in raw.items():
            out[str(k)] = bool(v)
        return out
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                out[item] = True
            elif isinstance(item, dict):
                for k, v in item.items():
                    out[str(k)] = bool(v)
        return out
    if isinstance(raw, str):
        out[raw] = True
        return out
    # fallback: try to stringify
    try:
        s = str(raw)
        out[s] = True
    except Exception:
        pass
    return out

    files = gather_files(repo_root, cfg)
    if not files:
        print("No content files found to scan.")
        sys.exit(0)

    per_frame: Dict[str, Dict[str, Any]] = {}
    frames_by_file: Dict[str, List[str]] = defaultdict(list)
    diagnostics_references: Dict[str, List[str]] = defaultdict(list)
    engines_affordances: Dict[str, List[str]] = {}

    for p in files:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Warning: failed to parse {p}: {e}")
            continue

        ftype = detect_file_type(p, raw)
        if ftype == "unknown":
            print(f"Warning: skipping unknown file type: {p.name}")
            continue

        if ftype == "diagnostic":
            # collect references to frame_id in diagnostics
            # heuristic: search JSON for strings matching frame IDs used elsewhere
            txt = json.dumps(raw)
            # we'll attach later
            # store raw for simple search
            diagnostics_references[p.name] = []

        if ftype == "engines":
            # collect engine affordances for later frame->engine checks
            engines = []
            if isinstance(raw, dict) and isinstance(raw.get("engines"), list):
                engines = raw.get("engines")
            elif isinstance(raw, list):
                engines = raw
            for eng in engines:
                eid = eng.get("id") or eng.get("engine_id")
                raw_eng_aff = eng.get("affordances") or eng.get("affordance") or {}
                eng_aff = normalize_affordances(raw_eng_aff)
                if eid:
                    engines_affordances[eid] = eng_aff
            continue

        if ftype != "frames":
            continue

        frames = extract_frames_from_file(p, raw)
        for frame in frames:
            rec = analyze_frame(frame, str(p.relative_to(repo_root)))
            fid = rec.get("frame_id") or f"__MISSING__:{p.name}"
            per_frame[fid] = rec
            frames_by_file[str(p.relative_to(repo_root))].append(fid)

    # Attach S6: check diagnostics files for references to frame ids
    # naive approach: load diagnostics files and search for frame ids
    for p in files:
        if p.name.startswith("diagnostic_"):
            txt = p.read_text(encoding="utf-8")
            for fid in list(per_frame.keys()):
                if fid and fid.startswith("__MISSING__"):
                    continue
                if fid in txt:
                    per_frame[fid]["scenarios"].append("S6_diagnostic_confidence_changes")

    # Merge engine-level affordances into frame affordances (frame overrides engine)
    for fid, rec in per_frame.items():
        eng_id = rec.get("engine_id")
        eng_aff = engines_affordances.get(eng_id) or {}
        fr_aff = rec.get("affordances") or {}
        merged = dict(eng_aff) if isinstance(eng_aff, dict) else {}
        if isinstance(fr_aff, dict):
            merged.update(fr_aff)
        rec["affordances"] = merged

    # Load generated cards if present to compute card readiness and enable frame-card cross-checks
    # Priority: CLI flags (--cards-path / --cards-index-path) -> config file -> default path
    # Track whether cards path was explicitly provided (CLI or config)
    cards_explicitly_provided = False
    if cards_path_arg:
        cards_path = Path(cards_path_arg)
        cards_explicitly_provided = True
        if not cards_path.is_absolute():
            cards_path = repo_root / cards_path_arg
    else:
        cfg_cards_path = cfg.get("cards_path") if isinstance(cfg, dict) else None
        if cfg_cards_path:
            cards_path = Path(cfg_cards_path)
            cards_explicitly_provided = True
            if not cards_path.is_absolute():
                cards_path = repo_root / cfg_cards_path
        else:
            cards_path = repo_root / "tools" / "cards" / "out" / "cards.json"

    # cards index path (optional)
    cards_index_path = None
    if cards_index_arg:
        cards_index_path = Path(cards_index_arg)
        if not cards_index_path.is_absolute():
            cards_index_path = repo_root / cards_index_arg
    else:
        cfg_cards_index = cfg.get("cards_index_path") if isinstance(cfg, dict) else None
        if cfg_cards_index:
            cards_index_path = Path(cfg_cards_index)
            if not cards_index_path.is_absolute():
                cards_index_path = repo_root / cfg_cards_index
    cards_obj = None
    cards_by_id = {}
    cards_by_word_id = {}
    cards_by_hanzi = defaultdict(list)
    card_readiness_map: Dict[str, int] = {}
    # card_readiness_counts: counts of cards that support each level (cards can support multiple levels)
    card_readiness_counts = Counter()
    # distribution of the maximum supported level per card
    card_max_level_counts = Counter()
    # If a cards path was supplied explicitly (CLI or config), loading is mandatory.
    cards_path_used = None
    if cards_path:
        cards_path_used = str(cards_path)
        if not cards_path.exists():
            if cards_explicitly_provided:
                print(f"Error: cards.json specified but not found: {cards_path}")
                sys.exit(2)
            else:
                # no cards file available; leave cards structures empty
                cards_obj = None
        else:
            try:
                cards_obj = json.loads(cards_path.read_text(encoding="utf-8"))
            except Exception as e:
                if cards_explicitly_provided:
                    print(f"Error: failed to parse cards.json: {e}")
                    sys.exit(2)
                else:
                    print(f"Warning: failed to load cards.json: {e}")

    # If we have a cards_obj, populate lookup maps and readiness counts strictly from it.
    if cards_obj and isinstance(cards_obj, dict):
        for c in cards_obj.get("cards", []):
            cid = c.get("card_id")
            if not cid:
                continue
            cards_by_id[cid] = c
            # map by word_id (card_id assumed to be word_id)
            cards_by_word_id[cid] = cid
            han = c.get("content", {}).get("headword", {}).get("hanzi")
            if han:
                cards_by_hanzi[han].append(cid)

            # compute which levels this card supports (cards can support multiple levels)
            supported_levels = set()
            content = c.get("content", {}) or {}
            head = content.get("headword", {}) or {}
            meaning = bool(content.get("meaning"))
            hanzi = head.get("hanzi")
            # L0: has headword hanzi and meaning (support for basic lookup)
            if hanzi and meaning:
                supported_levels.add(0)
                card_readiness_counts[0] += 1

            action_ids = [a.get("action_id") for a in c.get("actions", []) if isinstance(a, dict)]
            # L1: reveal_pinyin action available
            if "reveal_pinyin" in action_ids:
                supported_levels.add(1)
                card_readiness_counts[1] += 1

            # L2: reveal_word_composition (preserve existing detection)
            if "reveal_word_composition" in action_ids:
                supported_levels.add(2)
                card_readiness_counts[2] += 1

            # L3: reveal_characters + non-empty characters content
            if "reveal_characters" in action_ids and content.get("characters"):
                supported_levels.add(3)
                card_readiness_counts[3] += 1

            # L4: open_trace_mode action
            if "open_trace_mode" in action_ids:
                supported_levels.add(4)
                card_readiness_counts[4] += 1

            # record the max supported level for the card (or -1 if none)
            max_level = max(supported_levels) if supported_levels else -1
            card_readiness_map[cid] = max_level
            card_max_level_counts[max_level] += 1

    # number of cards loaded
    cards_loaded = 0
    if cards_obj and isinstance(cards_obj, dict):
        cards_loaded = len(cards_obj.get("cards", []))

    # perform reclassification using a helper so it's testable
    reclassify_frames_with_cards(per_frame, engines_affordances, card_readiness_map, cards_by_word_id, cards_by_hanzi)

    # Mark frames that have no hints but reference cards with readiness L0+
    # Also, if a frame or its engine declares 'open_card' affordance and any card exists at L0+, reclassify
    any_card_L0_plus = any((lvl is not None and lvl >= 0) for lvl in card_readiness_map.values())
    for fid, rec in per_frame.items():
        if rec.get("readiness_label") != "READY_NO_HINTS":
            continue

        tokens = rec.get("option_tokens", []) or []
        found_card_available = False

        # token/hanzi matching as before
        for t in tokens:
            if not isinstance(t, str):
                continue
            if t in cards_by_word_id:
                if card_readiness_map.get(cards_by_word_id[t], -1) >= 0:
                    found_card_available = True
                    break
            if t in cards_by_hanzi:
                for cid in cards_by_hanzi[t]:
                    if card_readiness_map.get(cid, -1) >= 0:
                        found_card_available = True
                        break
            if found_card_available:
                break

        # affordance-triggered availability: open_card on frame or engine + any L0+ card exists
        afford_open = False
        fr_aff = rec.get("affordances") or []
        if isinstance(fr_aff, list) and "open_card" in fr_aff:
            afford_open = True
        eng_id = rec.get("engine_id")
        if not afford_open and eng_id and eng_id in engines_affordances:
            eng_aff = engines_affordances.get(eng_id) or []
            if isinstance(eng_aff, list) and "open_card" in eng_aff:
                afford_open = True

        if found_card_available or (afford_open and any_card_L0_plus):
            rec["readiness_label"] = "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE"
            rec.setdefault("blockers", []).append("conv_hint_missing_but_card_available")


    # aggregate stats
    readiness_counts = Counter()
    scenario_counts = Counter()
    blockers_counter = Counter()

    for fid, rec in per_frame.items():
        readiness_counts[rec["readiness_label"]] += 1
        for s in rec.get("scenarios", []):
            scenario_counts[s] += 1
        for b in rec.get("blockers", []):
            blockers_counter[b] += 1

    summary = {
        "total_frames": len(per_frame),
        "readiness_counts": dict(readiness_counts),
        "scenario_counts": dict(scenario_counts),
        "top_blockers": blockers_counter.most_common(20),
        "card_readiness_counts": dict(card_readiness_counts),
        "card_max_level_counts": dict(card_max_level_counts),
        "cards_path_used": cards_path_used,
        "cards_loaded": cards_loaded,
    }

    out_dir = repo_root / "tools" / "coverage"
    out_dir.mkdir(parents=True, exist_ok=True)

    report_json = {
        "per_frame": per_frame,
        "frames_by_file": frames_by_file,
        "summary": summary,
    }

    json_path = out_dir / "coverage_report.json"
    md_path = out_dir / "coverage_report.md"
    csv_path = out_dir / "coverage_summary.csv"

    json_path.write_text(json.dumps(report_json, indent=2, ensure_ascii=False), encoding="utf-8")

    # markdown
    lines: List[str] = []
    lines.append("# Content Coverage Report")
    lines.append("")
    lines.append("## Readiness Distribution")
    lines.append("")
    lines.append("| Readiness | Count |")
    lines.append("|---:|---:|")
    for k, v in sorted(summary["readiness_counts"].items(), key=lambda x: x[0]):
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("## Card Readiness Distribution (L0-L4)")
    lines.append("")
    lines.append("| Level | Count |")
    lines.append("|---:|---:|")
    # Show support counts for L0-L4 explicitly (0..4) and any other levels present
    crc = summary.get("card_readiness_counts", {}) or {}
    for lvl in range(0, 5):
        cnt = crc.get(str(lvl), crc.get(lvl, 0))
        lines.append(f"| {lvl} | {cnt} |")
    # also include any extra keys present in the summary map
    extra_keys = [k for k in crc.keys() if str(k) not in {str(i) for i in range(0, 5)}]
    for k in sorted(extra_keys):
        lines.append(f"| {k} | {crc.get(k)} |")
    lines.append("")
    # Card max-level distribution
    lines.append("## Card Max-Level Distribution")
    lines.append("")
    lines.append("| Max Level | Count |")
    lines.append("|---:|---:|")
    for lvl, cnt in sorted(summary.get("card_max_level_counts", {}).items(), key=lambda x: (int(x[0]) if (isinstance(x[0], int) or (isinstance(x[0], str) and x[0].lstrip('-').isdigit())) else x[0])):
        lines.append(f"| {lvl} | {cnt} |")
    lines.append("")
    lines.append("## Top Blockers")
    lines.append("")
    lines.append("| Blocker | Count |")
    lines.append("|---|---:|")
    for b, c in summary["top_blockers"]:
        lines.append(f"| {b} | {c} |")
    lines.append("")
    lines.append("## Scenario Coverage Summary")
    lines.append("")
    lines.append("| Scenario | Count |")
    lines.append("|---|---:|")
    for s, c in sorted(summary["scenario_counts"].items(), key=lambda x: x[0]):
        lines.append(f"| {s} | {c} |")
    lines.append("")
    lines.append("## READY_FOR_APP Frames (top 50)")
    lines.append("")
    ready_ids = [fid for fid, r in per_frame.items() if r.get("readiness_label") == "READY_FOR_APP"]
    for fid in ready_ids[:50]:
        f = per_frame[fid]
        lines.append(f"- {fid} — {f.get('file')}")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    # CSV
    import csv

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["frame_id", "file", "readiness_label", "blockers", "scenarios"])
        for fid, r in per_frame.items():
            writer.writerow([
                fid,
                r.get("file"),
                r.get("readiness_label"),
                ";".join(r.get("blockers", [])),
                ";".join(sorted(set(r.get("scenarios", [])))),
            ])

    print(f"Scan complete. Frames: {len(per_frame)}. Reports: {json_path}, {md_path}, {csv_path}")


def main(argv: Optional[List[str]] = None):
    ap = argparse.ArgumentParser(description="MandarinOS Content Coverage Scanner v1")
    ap.add_argument("--config", "-c", help="Path to config JSON (relative to repo root or absolute)", default=None)
    ap.add_argument("--cards-path", help="Path to generated cards.json (overrides config)")
    ap.add_argument("--cards-index-path", help="Path to generated cards_index.json (overrides config)")
    args = ap.parse_args(argv)

    repo_root = resolve_repo_root()
    cfg_path = None
    if args.config:
        cfg_path = Path(args.config)
        if not cfg_path.is_absolute():
            cfg_path = repo_root / args.config
    else:
        cfg_path = repo_root / "tools" / "coverage" / "coverage_config.json"

    run_scan(cfg_path, cards_path_arg=args.cards_path, cards_index_arg=args.cards_index_path)


def reclassify_frames_with_cards(per_frame: Dict[str, Dict[str, Any]],
                                  engines_affordances: Dict[str, List[str]],
                                  card_readiness_map: Dict[str, int],
                                  cards_by_word_id: Dict[str, str],
                                  cards_by_hanzi: Dict[str, List[str]]) -> None:
    """Reclassify frames in-place when cards are available and affordances allow opening cards.

    Rules:
    - For frames labeled READY_NO_HINTS, if any option token directly matches a card (by word id or hanzi)
      and that card has readiness L0+ (level >= 0), reclassify to READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE.
    - Also, if the frame or its engine declares `open_card` affordance and the cards dataset contains any
      L0+ card, reclassify as above.
    """
    any_card_L0_plus = any((lvl is not None and lvl >= 0) for lvl in card_readiness_map.values())

    for fid, rec in list(per_frame.items()):
        if rec.get("readiness_label") != "READY_NO_HINTS":
            continue

        tokens = rec.get("option_tokens", []) or []
        found_card_available = False
        for t in tokens:
            if not isinstance(t, str):
                continue
            if t in cards_by_word_id:
                if card_readiness_map.get(cards_by_word_id[t], -1) >= 0:
                    found_card_available = True
                    break
            if t in cards_by_hanzi:
                for cid in cards_by_hanzi[t]:
                    if card_readiness_map.get(cid, -1) >= 0:
                        found_card_available = True
                        break
            if found_card_available:
                break

        # affordance-triggered availability: open_card on frame or engine + any L0+ card exists
        afford_open = False
        fr_aff = rec.get("affordances") or {}
        if isinstance(fr_aff, dict) and bool(fr_aff.get("open_card")):
            afford_open = True
        eng_id = rec.get("engine_id")
        if not afford_open and eng_id and eng_id in engines_affordances:
            eng_aff = engines_affordances.get(eng_id) or {}
            if isinstance(eng_aff, dict) and bool(eng_aff.get("open_card")):
                afford_open = True

        if found_card_available or (afford_open and any_card_L0_plus):
            rec["readiness_label"] = "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE"
            rec.setdefault("blockers", []).append("conv_hint_missing_but_card_available")


if __name__ == "__main__":
    main()
