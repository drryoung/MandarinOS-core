#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import List, Optional
from urllib.parse import urlparse, parse_qs
import mimetypes
import os

# Ensure stdout can handle non-ASCII (Chinese) characters on Windows cp1252 terminals.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT   = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = Path(__file__).resolve().parent
UI_DIR      = REPO_ROOT / "ui"
RUNTIME_DIR = REPO_ROOT / "runtime"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Phase 10: learner memory (fact-capture applied after a response turn)
try:
    from learner_memory import load as _lm_load, save as _lm_save, apply_updates as _lm_apply_updates
    from learner_memory_capture import capture_from_turn as _capture_from_turn, get_memory_field_for_frame as _get_memory_field_for_frame
except ImportError:
    _lm_load = _lm_save = _lm_apply_updates = _capture_from_turn = None
    _get_memory_field_for_frame = None
# Phase 10 Step 6: persona for persona-consistent stubs
try:
    from persona_data import get_persona as _get_persona
except ImportError:
    _get_persona = None

# Phase 10 Step 5: suppress re-asking a fact when we already have it (keep conversation moving).
# Re-asking (recall/drill) can be enabled later via e.g. drill_mode in request.
RECALL_INTERVAL_TURNS = 5  # reserved for future drill mode

# Phase 10.5 (behaviour tuning, revised): reaction micro-layer, contextual curiosity gating, blended reciprocity,
# slot/topic-follow-up preference, weak-loop avoidance. No schema changes required.
P_REACTION_AFTER_MEANINGFUL = 0.7
P_LOOP_WHEN_TRIGGERED = 0.75  # prefer loop/curiosity on same topic before bridging
MAX_CURIOSITY_DEPTH = 2
EARLY_EXCHANGES = 3
# Interest-driven responsiveness tuning (10.5 refinement)
INTEREST_MEDIUM_THRESHOLD = 1
INTEREST_HIGH_THRESHOLD = 3
P_CURIOUS_WHEN_INTEREST_MED = 0.60
P_CURIOUS_WHEN_INTEREST_HIGH = 0.80
P_BRIDGE_WHEN_INTEREST_HIGH = 0.70
MAX_SAME_ENGINE_AFTER_INTEREST = 4    # stay in same engine for up to 4 turns after an interesting answer
MAX_SAME_SLOT_CHAIN_AFTER_INTEREST = 2
INTEREST_FORCE_WINDOW_TURNS = 1
MIN_SAME_ENGINE_CHAIN_BEFORE_BRIDGE = 4  # require at least 4 turns in an engine before allowing a bridge
ENGINE_DEPTH_GUARD_TURNS = 5          # Phase 11.1: block bridge if too few same-engine turns and fresh frames remain
ENGINE_DEPTH_GUARD_MIN_REMAINING = 2  # Phase 11.1: bridge blocked when ≥ this many unseen frames still available
FACT_REVEAL_DEPTH = 3                 # Phase 11C: min same_engine_chain_count before discoverable_fact surfaces
MAX_PROBE_CHAIN = 2                   # Phase 12B: max consecutive probe follow-ups before probe row is suppressed
MIN_TURNS_FOR_LIFE_ENGINE = 16        # Difficulty ramp: "life" engine is all difficulty-3; block it early in session
# Phase 12C: session arc tuning
LOOP_COUNT_IN_ENGINE_SOFT_CAP = 2    # reduce LOOP when partner has asked ≥ this many LOOPs in current engine
OVERLOAD_CONFUSION_THRESHOLD  = 2    # recent_confusion_count ≥ this → overload: prefer bridge / simpler frames
CLOSURE_EXCHANGE_THRESHOLD    = 12   # after this many total exchanges push toward bridge / close
CLOSURE_BRIDGE_GATE           = 600  # out of 1000: hash-gate probability for bridge push in closure zone

print("[ui_server] REPO_ROOT =", REPO_ROOT)
print("[ui_server] UI_DIR    =", UI_DIR)
print("[ui_server] RUNTIME_DIR =", RUNTIME_DIR)

# Windows console can be cp1252; avoid crashing on printing Hanzi in payload logs.
try:
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── Load runtime indexes at startup ──────────────────────────────────────────
_frt_path = RUNTIME_DIR / "out_phase7" / "frame_render_tokens.runtime.json"
_ci_path  = RUNTIME_DIR / "out_phase7" / "cards_index.runtime.json"
_fo_path  = RUNTIME_DIR / "out_phase7" / "frame_options.runtime.json"

_frame_tokens  = {}
_cards_by_word_id = {}
_frame_options = {}
_frames_by_id  = {}

if _frt_path.is_file():
    _frt_raw = json.loads(_frt_path.read_text(encoding="utf-8")).get("frames", [])
    if isinstance(_frt_raw, list):
        _frame_tokens = { item["frame_id"]: item.get("tokens", []) for item in _frt_raw if isinstance(item, dict) and "frame_id" in item }
    else:
        _frame_tokens = _frt_raw if isinstance(_frt_raw, dict) else {}
    print(f"[ui_server] frame_render_tokens loaded ({len(_frame_tokens)} frames)")
else:
    print(f"[ui_server] WARNING: frame_render_tokens not found at {_frt_path}")

if _ci_path.is_file():
    _cards_by_word_id = json.loads(_ci_path.read_text(encoding="utf-8")).get("by_word_id", {})
    print(f"[ui_server] cards_index loaded ({len(_cards_by_word_id)} entries)")
else:
    print(f"[ui_server] WARNING: cards_index not found at {_ci_path}")

if _fo_path.is_file():
    _frame_options = json.loads(_fo_path.read_text(encoding="utf-8")).get("frames", {})
    print(f"[ui_server] frame_options loaded ({len(_frame_options)} frames)")
else:
    print(f"[ui_server] WARNING: frame_options not found at {_fo_path}")

def _reload_frames_by_id():
    """Load frames from p1/p2 JSON (so frame_text_en etc. are always up to date)."""
    out = {}
    for _fname in ["p1_frames.json", "p2_frames.json"]:
        _fp = REPO_ROOT / _fname
        if _fp.is_file():
            _fdata = json.loads(_fp.read_text(encoding="utf-8"))
            for _fr in _fdata.get("frames", []):
                out[_fr["id"]] = _fr
    return out

_frames_by_id = _reload_frames_by_id()
print(f"[ui_server] frames_by_id loaded ({len(_frames_by_id)} frames)")

# Phase 10.7: optional declarative move_type transition table
_move_type_transitions: Optional[dict] = None
_mt_path = REPO_ROOT / "data" / "move_type_transitions.json"
try:
    if _mt_path.is_file():
        _raw_mt = json.loads(_mt_path.read_text(encoding="utf-8"))
        if isinstance(_raw_mt, dict):
            _move_type_transitions = {k: set(v) for k, v in _raw_mt.items() if isinstance(v, list)}
            print(f"[ui_server] move_type_transitions loaded ({len(_move_type_transitions)} move types)")
        else:
            print("[ui_server] WARNING: move_type_transitions.json is not a dict — skipping")
    else:
        print(f"[ui_server] INFO: move_type_transitions.json not found at {_mt_path} — move_type filter disabled")
except Exception as _e:
    print(f"[ui_server] WARNING: move_type_transitions load failed: {_e} — move_type filter disabled")


# ── Phase 11C: Persona layer ──────────────────────────────────────────────────
# Architecture: one JSON file per persona in personas/. No code changes needed to add personas.
# Server discovers all *.json files (excluding _*.json) at startup; loads each on demand.
PERSONAS_DIR: Path = REPO_ROOT / "personas"
_personas_index: list = []     # lightweight list for /api/personas (loaded from _index.json)
_personas_cache: dict = {}     # id -> full persona data (lazy-loaded on first use)

def _load_personas_index() -> None:
    global _personas_index
    index_path = PERSONAS_DIR / "_index.json"
    if index_path.exists():
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            _personas_index = raw.get("personas", [])
            print(f"[ui_server] personas index loaded ({len(_personas_index)} entries)")
        except Exception as _e:
            print(f"[ui_server] WARNING: personas _index.json load failed: {_e}")
    # Auto-fill any personas on disk not listed in the index (supports drop-in additions)
    listed_ids = {p["id"] for p in _personas_index}
    if PERSONAS_DIR.is_dir():
        for fp in sorted(PERSONAS_DIR.glob("*.json")):
            if fp.stem.startswith("_"):
                continue
            if fp.stem not in listed_ids:
                _personas_index.append({"id": fp.stem, "display_name": fp.stem})
                print(f"[ui_server] personas: auto-discovered unlisted persona '{fp.stem}'")

def _resolve_persona(persona_id: str) -> Optional[dict]:
    """Lazy-load and cache a persona by id. Returns None if not found."""
    if not persona_id:
        return None
    if persona_id in _personas_cache:
        return _personas_cache[persona_id]
    fp = PERSONAS_DIR / f"{persona_id}.json"
    if not fp.exists():
        return None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        _personas_cache[persona_id] = data
        return data
    except Exception as _e:
        print(f"[ui_server] WARNING: could not load persona '{persona_id}': {_e}")
        return None

_load_personas_index()
# ─────────────────────────────────────────────────────────────────────────────


def _engine_frame_ids(engine_norm: str) -> List[str]:
    """All frame_ids for the given engine (normalized), in stable sorted order."""
    return sorted(
        fid for fid, fr in _frames_by_id.items()
        if (fr.get("engine") or "").strip().lower() == engine_norm
    )


# Preferred order for partner-question frames per engine (sensible conversation flow).
# Order follows spec: core → treasure (follow-ups) → loop so we use treasure/loop questions, not just core.
# P2 question frames (大家一般怎么叫你？, 你觉得{CITY}生活怎么样？, etc.) are included so we don't exhaust after 2–3 questions.
_FRAME_ORDER: dict = {
    # Identity flow: name → how people call you → meaning → EXTEND break → evaluations → age.
    "identity": ["f_ask_you_name", "p2_id_2", "f_ask_name_meaning", "p2_id_ext1", "f_name_story_elicit", "p2_id_4", "p2_id_5", "f_how_old"],
    # Place flow: origin → like it → live where → EXTEND break → life quality → food → leisure → convenient.
    "place": ["f_from_where", "f_place_like_there", "frame.location.live_question", "p2_pl_1", "p2_pl_ext1", "p2_pl_2", "p2_pl_3", "p2_pl_4"],
    # Family flow: have family → live together → siblings → married → children → EXTEND break → how often → weekend.
    # p2_fa_1 ("你跟家人住在一起吗？") is more natural after the user reveals family members.
    "family": ["f_have_family", "p2_fa_1", "f_have_siblings", "f_married", "f_have_children", "p2_fa_ext1", "p2_fa_2", "p2_fa_5"],
    # Work: compact high-interest sequence with EXTEND break after difficulty questions.
    "work": ["f_what_work", "f_like_work", "p2_wk_1", "p2_wk_2", "p2_wk_ext1", "p2_wk_3", "p2_wk_4", "p2_wk_5"],
    # Hobby: opening → frequency → difficulty → like what → EXTEND break → recommend → weekend → etc.  Phase 11.1: f_like_do_what moved to pos 3 to avoid consecutive duplicate opener.
    "hobby": ["f_what_hobby", "f_often_do", "f_difficult_ma", "f_like_do_what", "p2_hb_ext1", "f_recommend_ma", "f_weekend_do", "f_like_chinese_culture", "f_like_what", "f_collect_what", "p2_hb_1", "p2_hb_2", "p2_hb_4", "p2_hb_5"],
    # Travel: been where → want to go → countries → best place → EXTEND break → fun things → how was it.
    "travel": ["f_travel_where", "f_want_go_where", "p2_tr_1", "p2_tr_2", "p2_tr_ext1", "p2_tr_3", "p2_tr_4"],
    # Food: what's good → famous dish → tasty → EXTEND break → spicy → expensive.
    "food": ["f_food_what_good", "f_food_famous_dish", "f_food_tasty", "p2_fd_ext1", "f_food_like_spicy", "f_food_expensive"],
    "life": [],
}
# A frame id may only be chosen if all of its "after" frames are in recent_frame_ids (already asked).
_FRAME_AFTER: dict = {
    "f_ask_name_meaning": ["f_ask_you_name"],  # don't ask name meaning before asking name
    # Identity follow-up assumes a name exists
    "p2_id_2": ["f_ask_you_name"],
    # Story elicitation only makes sense after the story question was asked
    "f_name_story_elicit": ["p2_id_ext1"],
}

# Phase 11.1: OPEN frames that must not be re-entered once the session is established (exchange_count ≥ 2).
# These are opening gambits — re-asking them after real conversation has begun feels unnatural.
_IDENTITY_OPEN_FRAMES: frozenset = frozenset({"f_ask_you_name"})

# "OR" dependencies: any one prerequisite is sufficient.
# Place follow-ups need an established referent ("there"/CITY) first; prevents out-of-context “那里”.
_FRAME_AFTER_ANY: dict = {
    "f_place_like_there": ["f_from_where", "frame.location.live_question"],
    "p2_pl_1": ["f_from_where", "frame.location.live_question"],
    "p2_pl_2": ["f_from_where", "frame.location.live_question"],
    "p2_pl_3": ["f_from_where", "frame.location.live_question"],
    "p2_pl_4": ["f_from_where", "frame.location.live_question"],
    # Phase 12: EXTEND frame references "where you live" so needs place context first.
    "p2_pl_ext1": ["f_from_where", "frame.location.live_question"],
    # "Why do you like it there?" presupposes "do you like it there?" was already asked.
    "f_place_why_like": ["f_place_like_there"],
}


def _deictic_context_fresh(fid: str, recent_frame_ids: list, window: int = 4) -> bool:
    """
    Extra recency guard for deictic/place-referential questions like "那里".
    Even if a place anchor exists somewhere in history, require it to be recent.
    """
    anchors = {
        "f_place_like_there": ["f_from_where", "frame.location.live_question", "p2_pl_4", "p2_pl_2"],
        # "Why do you like it there?" also uses "那儿" — needs a recent place anchor AND like question
        "f_place_why_like":   ["f_place_like_there"],
    }.get(fid)
    if not anchors:
        return True
    recent_tail = list(recent_frame_ids or [])[-max(1, int(window)):]
    return any(a in recent_tail for a in anchors)


def _frame_deps_satisfied(fid: str, recent: set, recent_frame_ids: Optional[list] = None) -> bool:
    """True if frame fid's AFTER/AFTER_ANY prerequisites are satisfied given recent frame ids."""
    after_all = _FRAME_AFTER.get(fid) or []
    if after_all and not all(dep in recent for dep in after_all):
        return False
    after_any = _FRAME_AFTER_ANY.get(fid) or []
    if after_any and not any(dep in recent for dep in after_any):
        return False
    if not _deictic_context_fresh(fid, recent_frame_ids or []):
        return False
    return True


# ── Phase 10.7: move_type helpers ────────────────────────────────────────────

def _get_frame_move_type(frame_id: str) -> Optional[str]:
    """Return the move_type string for a frame, or None if unset."""
    fr = _frames_by_id.get(frame_id) or {}
    mt = fr.get("move_type")
    return str(mt).strip() or None if mt else None


def _get_allowed_next_move_types(current_move_type: Optional[str]) -> Optional[set]:
    """
    Phase 10.7: look up allowed next move types from the declarative transition table.
    Returns None (meaning: do not filter) when:
    - transition table not loaded
    - current_move_type is None / empty
    - current_move_type not found in table
    """
    if _move_type_transitions is None:
        return None
    if not current_move_type:
        return None
    allowed = _move_type_transitions.get(current_move_type)
    return allowed if allowed is not None else None


# ── Phase 11.0: candidate scoring scaffold ───────────────────────────────────
# Scoring weights: kept conservative so signals nudge rather than dominate.
# Legacy rank step = 0.10 → each rank position is worth this much.
# move_type bonus = 0.30  → compatible move_type can overcome ~3 legacy rank positions.
# capability/energy = ±0.08 → each can overcome ~1 legacy rank position.
_P11_LEGACY_RANK_STEP  = 0.10
_P11_MT_BONUS_VALID    = 0.30
_P11_MT_PENALTY_MISS   = 0.10
_P11_CAP_BONUS         = 0.08
_P11_CAP_PENALTY       = 0.08
_P11_ENERGY_PENALTY    = 0.08


def _phase11_score_candidate(
    frame_id: str,
    legacy_rank: int,
    allowed_move_types: Optional[set],
    exchange_count: int,
    same_engine_chain_count: int,
) -> tuple:
    """
    Phase 11.0: additive score for one candidate frame.  Higher = more preferred.
    Returns (score: float, trace: dict).

    Signals:
      legacy_rank            – 0-based position in Phase 10.5 preferred order (lower = better)
      allowed_move_types     – set from transition table; None → skip move_type signal
      exchange_count         – total session exchanges (coarse capability proxy)
      same_engine_chain_count – consecutive same-engine turns (coarse energy proxy)
    """
    fr = _frames_by_id.get(frame_id) or {}

    # 1. Legacy baseline — preserves Phase 10.5 preference order as default.
    legacy_score = max(0.0, 1.0 - legacy_rank * _P11_LEGACY_RANK_STEP)

    # 2. move_type compatibility bonus.
    cand_mt = _get_frame_move_type(frame_id)
    mt_contribution = 0.0
    if allowed_move_types is not None:
        if cand_mt and cand_mt in allowed_move_types:
            mt_contribution = _P11_MT_BONUS_VALID
        elif cand_mt:
            # In candidates_after all are already valid; this handles edge cases.
            mt_contribution = -_P11_MT_PENALTY_MISS

    # 3. Capability: corrective signal only — penalise clear mismatches, neutral otherwise.
    difficulty = int(fr.get("difficulty") or 2)
    cap_contribution = 0.0
    if difficulty == 1 and exchange_count >= 8:
        cap_contribution = -_P11_CAP_PENALTY   # very basic frame, late in session
    elif difficulty == 3 and exchange_count < 3:
        cap_contribution = -_P11_CAP_PENALTY   # complex frame, too early
    # else: neutral (0.0) — no default boost

    # 4. Energy: slight anti-repetition nudge for deep same-engine chains.
    energy_contribution = 0.0
    if same_engine_chain_count >= 4:
        energy_contribution = -_P11_ENERGY_PENALTY

    total = legacy_score + mt_contribution + cap_contribution + energy_contribution
    trace = {
        "frame_id":                frame_id,
        "legacy_rank":             legacy_rank,
        "move_type":               cand_mt,
        "mt_contribution":         round(mt_contribution, 3),
        "capability_contribution": round(cap_contribution, 3),
        "energy_contribution":     round(energy_contribution, 3),
        "total_score":             round(total, 3),
    }
    return total, trace


def _phase11_rank_shortlist(
    candidates: list,
    allowed_move_types: Optional[set],
    exchange_count: int,
    same_engine_chain_count: int,
) -> tuple:
    """
    Phase 11.0: score and rank a shortlist of candidate frame IDs.
    Returns (best_id, scored_list, selection_source).

    selection_source values:
      "scored_preferred"  – scoring changed the ordering (best != candidates[0])
      "legacy"            – scoring confirmed the legacy first choice
      "fallback_after_empty" – no candidates supplied
    """
    if not candidates:
        return None, [], "fallback_after_empty"

    scored = []
    for rank, fid in enumerate(candidates):
        score, trace = _phase11_score_candidate(
            fid, rank, allowed_move_types, exchange_count, same_engine_chain_count
        )
        scored.append((score, rank, fid, trace))

    # Sort: highest score first; legacy rank as stable tie-breaker.
    scored.sort(key=lambda x: (-x[0], x[1]))

    best_id = scored[0][2]
    traces  = [s[3] for s in scored]
    source  = "scored_preferred" if best_id != candidates[0] else "legacy"
    return best_id, traces, source


def _apply_move_type_filter(
    chosen: Optional[str],
    last_frame_id: str,
    engine_norm: str,
    recent: list,
    memory: Optional[dict],
    exchange_count: int = 0,           # Phase 11.0: capability / energy scoring inputs
    same_engine_chain_count: int = 0,
) -> dict:
    """
    Phase 10.7-C + Phase 11.0: move_type soft-preference filter with additive scoring.

    Caller contract:
    - filtered_chosen is None  → keep original chosen (all fallback paths).
    - filtered_chosen == chosen → no change.
    - filtered_chosen != chosen → use filtered_chosen.

    Fallback conditions (any one → skip, filtered_chosen=None):
    - transition table not loaded                        → fallback_after_missing_tags
    - last_frame_id has no move_type tag                 → fallback_after_missing_tags
    - current move_type not in transition table          → fallback_after_missing_tags
    - no valid same-engine alternatives found            → fallback_after_empty

    Phase 11.0 scoring (runs whenever candidates_after has ≥ 1 entry):
    - Legacy rank as baseline
    - move_type compatibility as structural preference
    - Difficulty / session-depth as coarse capability signal
    - same_engine_chain_count as coarse energy signal
    """
    result: dict = {
        "current_move_type":               None,
        "move_type_filter_applied":        False,
        "allowed_next_move_types":         None,
        "candidates_before_move_filter":   None,
        "candidates_after_move_filter":    None,
        "move_type_filter_skipped_reason": None,
        "fallback_occurred":               False,
        "selection_source":                "legacy",
        "filtered_chosen":                 None,
        "phase11_scoring":                 [],
        "phase11_selection_source":        "legacy",
    }

    # ── Guard: transition table ──────────────────────────────────────────
    if _move_type_transitions is None:
        result["move_type_filter_skipped_reason"] = "table_not_loaded"
        result["fallback_occurred"] = True
        result["selection_source"] = "fallback_after_missing_tags"
        return result

    # ── Guard: last partner frame must be tagged ─────────────────────────
    current_mt = _get_frame_move_type(last_frame_id)
    result["current_move_type"] = current_mt
    if not current_mt:
        result["move_type_filter_skipped_reason"] = "last_frame_has_no_move_type"
        result["fallback_occurred"] = True
        result["selection_source"] = "fallback_after_missing_tags"
        return result

    # ── Guard: transition rule must exist ────────────────────────────────
    allowed_list = _get_allowed_next_move_types(current_mt)
    if allowed_list is None:
        result["move_type_filter_skipped_reason"] = "move_type_not_in_table"
        result["fallback_occurred"] = True
        result["selection_source"] = "fallback_after_missing_tags"
        return result
    allowed = set(allowed_list)
    result["allowed_next_move_types"] = sorted(allowed)

    # ── Build full candidate pool (Phase 11: always built for proper scoring) ──
    recent_set  = set(recent or [])
    recent_list = list(recent or [])
    same_engine = _engine_partner_question_frame_ids(engine_norm) or _engine_frame_ids(engine_norm)

    candidates_before = [
        fid for fid in same_engine
        if fid not in recent_set
        and _frame_deps_satisfied(fid, recent_set, recent_list)
        and (memory is None or not _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS))
        and _get_frame_move_type(fid) is not None
    ]
    result["candidates_before_move_filter"] = len(candidates_before)

    # Valid same-engine candidates (move_type in allowed set).
    candidates_after = [fid for fid in candidates_before if _get_frame_move_type(fid) in allowed]

    # If chosen is already valid, insert it at the front to preserve Phase 10.5 priority.
    # This works whether chosen is same-engine or cross-engine (bridge).
    chosen_mt = _get_frame_move_type(chosen) if chosen else None
    chosen_valid = bool(chosen_mt and chosen_mt in allowed)
    if chosen_valid:
        candidates_after = [chosen] + [f for f in candidates_after if f != chosen]

    result["candidates_after_move_filter"] = len(candidates_after)

    if not candidates_after:
        result["move_type_filter_skipped_reason"] = "no_tagged_candidates_in_allowed_set"
        result["fallback_occurred"] = True
        result["selection_source"]  = "fallback_after_empty"
        return result

    # ── Phase 11.0: score and rank candidates ────────────────────────────
    best, p11_traces, p11_source = _phase11_rank_shortlist(
        candidates_after, allowed, exchange_count, same_engine_chain_count
    )

    result["move_type_filter_applied"] = True
    result["fallback_occurred"]        = False
    result["phase11_scoring"]          = p11_traces
    result["phase11_selection_source"] = p11_source

    if best and best != chosen:
        result["selection_source"] = p11_source   # "scored_preferred" or "legacy"
    else:
        result["selection_source"] = "legacy"
    result["filtered_chosen"] = best or chosen
    return result


def _engine_partner_question_frame_ids(engine_norm: str) -> List[str]:
    """
    Partner frames that are questions (app asks the user). Includes P1 (speaker==partner) and P2 frames
    (no speaker; treat question frames as partner) so treasure/loop questions like 大家一般怎么叫你？ are used.
    Order: preferred list first, then any others sorted.
    """
    raw = [
        fid for fid, fr in _frames_by_id.items()
        if (fr.get("engine") or "").strip().lower() == engine_norm
        and "？" in (fr.get("text") or "")
        and ((fr.get("speaker") or "").strip().lower() == "partner" or (fr.get("speaker") or "").strip() == "")
    ]
    order = _FRAME_ORDER.get(engine_norm) or []
    ordered = [f for f in order if f in raw]
    rest = sorted(f for f in raw if f not in order)
    return ordered + rest


# Phase 9.2: which engines we can bridge to from each engine (deterministic order; from conversation specs)
_BRIDGE_TARGETS: dict = {
    "identity": ["place", "family", "work", "hobby"],
    "place":    ["food", "family", "work", "travel", "hobby", "identity"],
    "family":   ["identity", "work", "hobby", "place"],
    "work":     ["family", "identity", "hobby", "place"],
    "hobby":    ["family", "work", "identity", "travel", "food"],   # family/work first: most natural after hobbies
    "travel":   ["family", "work", "identity", "place", "hobby", "food"],
    "food":     ["family", "work", "place", "travel", "hobby", "life"],
    "life":     ["identity", "family", "work", "place"],
}

# When prefer_bridge (recovery / change topic): try engines in this order so the next question feels like a natural switch (place/identity/family first), not a jump to food/travel.
_RECOVERY_BRIDGE_ENGINE_ORDER: list = ["place", "identity", "family", "work", "hobby", "travel", "food", "life"]
_BRIDGE_PREFIXES: list = ["顺便问一下，"]

# Frames that ask essentially the same question in different engines.
# If any frame in a set has been shown, all others in that set are skipped.
_MUTUAL_EXCLUSION_FRAMES: dict = {
    # Food-place cluster: all ask "what food is there / what's famous / is it tasty?"
    # They all require the same place-food context. If any place-food frame was shown, skip
    # the others so the bridge doesn't return to food territory after it was already covered.
    "f_food_what_good":   {"p2_pl_2", "f_food_famous_dish", "f_food_tasty"},
    "f_food_famous_dish": {"p2_pl_2", "f_food_what_good",   "f_food_tasty"},
    "f_food_tasty":       {"p2_pl_2", "f_food_what_good",   "f_food_famous_dish"},
    "p2_pl_2":            {"f_food_what_good", "f_food_famous_dish", "f_food_tasty"},
    "f_travel_where": {"p2_tr_1"},     # "你去过哪里？" ↔ "你去过哪些国家？"
    "p2_tr_1": {"f_travel_where"},
    "f_ask_you_name": {"p2_id_2"},     # "你叫什么名字？" ↔ "大家一般怎么叫你？" (both ask for name)
    "p2_id_2": {"f_ask_you_name"},
    "p2_id_4": {"p2_id_5"},           # "你觉得你的名字怎么样？" ↔ "这个名字对你有什么意义？" (both ask about name significance)
    "p2_id_5": {"p2_id_4"},
}

# Oxygen loop questions (canonical list from MandarinOS_conversation_ladders_full_draft_v2.md) — offered as "Ask back" when user gave an interesting answer.
_OXYGEN_LOOP_PROBES: list = [
    {"id": "weishenme", "hanzi": "为什么？", "pinyin": "wèishénme", "meaning": "Why?"},
    {"id": "shei", "hanzi": "谁？", "pinyin": "shéi", "meaning": "Who?"},
    {"id": "shenme_shihou", "hanzi": "什么时候？", "pinyin": "shénme shíhou", "meaning": "When?"},
    {"id": "nali", "hanzi": "哪里？", "pinyin": "nǎlǐ", "meaning": "Where?"},
    {"id": "zenmeyang", "hanzi": "怎么样？", "pinyin": "zěnmeyàng", "meaning": "How is it?"},
    {"id": "xihuan_ma", "hanzi": "喜欢吗？", "pinyin": "xǐhuan ma", "meaning": "Do you like it?"},
    {"id": "gen_shei_yiqi", "hanzi": "跟谁一起？", "pinyin": "gēn shéi yìqǐ", "meaning": "With whom?"},
    {"id": "shenme_shihou_kaishi", "hanzi": "什么时候开始？", "pinyin": "shénme shíhou kāishǐ", "meaning": "When did it start?"},
]
# Short partner stub when learner asks a probe (Phase 10: persona-consistent when _get_persona available).
_PROBE_STUB_BY_ID: dict = {
    "weishenme": "嗯，因为我很喜欢。",
    "shei": "我跟家人一起。",
    "nali": "在那里。",
    "zenmeyang": "挺好的。",
    "xihuan_ma": "喜欢。",
    "gen_shei_yiqi": "跟朋友一起。",
    "shenme_shihou": "去年。",
    "shenme_shihou_kaishi": "很久以前。",
}
_PROBE_STUB_DEFAULT: str = "嗯，好问题！"

_WEAK_LOOP_FRAME_IDS: set = {
    # From docs/specs/PHASE_10_5_BEHAVIOUR_IMPLEMENTATION_PLAN.md §6
    "p2_pl_1", "p2_pl_3",
    "p2_tr_1", "p2_tr_2", "p2_tr_3", "p2_tr_4",
}

# Topic-specific reaction fallbacks (used only when no suitable reaction frame exists).
# Keep short; vary per topic to avoid overusing generic reactions.
_REACTION_FALLBACKS_BY_ENGINE: dict = {
    "identity": ["哦。", "是吗。", "不错。"],
    "place":    ["不错！", "挺好！", "很好！"],
    "work":     ["哦。", "不错。", "挺好的。"],
    "food":     ["听起来不错！", "好吃！", "不错！"],
    "hobby":    ["不错！", "有意思！", "挺好！"],
    "travel":   ["不错！", "听起来很好！", "真好！"],
    "family":   ["哦。", "明白了。", "不错。"],
    "life":     ["嗯。", "挺好。", "不错。"],
}
_REACTION_FALLBACKS_GENERIC: list = ["哦。", "是吗。", "不错。", "很好。"]

# High-interest curiosity reactions: used INSTEAD of plain acknowledgments when interest == "high".
# These are short question-style reactions that invite the user to explain further.
_CURIOSITY_REACTIONS_BY_ENGINE: dict = {
    "food":   ["为什么好吃？", "怎么好吃？", "哦？最喜欢哪个？"],
    "travel": ["为什么想去那里？", "哪个地方最有意思？", "真的吗？"],
    "place":  ["为什么喜欢那儿？", "怎么样？", "是吗？"],
    "work":   ["为什么喜欢这份工作？", "怎么难？", "是吗？"],
    "hobby":  ["为什么喜欢？", "怎么开始的？", "是吗？"],
    "family": ["怎么说？", "是吗？", "真的吗？"],
    "identity": ["为什么呢？", "是吗？", "怎么说？"],
}
_CURIOSITY_REACTIONS_GENERIC: list = ["为什么呢？", "真的吗？", "怎么说？", "是吗？"]

# Oxygen selection by context (engine or slot). Only surface 1–2 when gating conditions fire.
_OXYGEN_IDS_BY_ENGINE: dict = {
    "place": ["zenmeyang", "nali"],
    "work":  ["zenmeyang", "shenme_shihou"],  # busy? not available; keep lightweight
    "food":  ["weishenme", "xihuan_ma"],
}
_OXYGEN_IDS_BY_SLOT: dict = {
    "CITY": ["zenmeyang", "nali"],
    "JOB":  ["zenmeyang"],
    "DISH": ["weishenme", "xihuan_ma"],
    "NAME": ["weishenme"],
}

# Slot/topic-specific follow-up preferences (attempt before generic engine ladder).
_SLOT_FOLLOWUP_PREFERENCES: dict = {
    # CITY: ask "do you like it there?" before "why do you like it there?" — avoid presupposition failure.
    "CITY": ["f_place_like_there", "f_place_why_like", "p2_pl_4", "p2_pl_2", "p2_pl_1"],
    # JOB: compact high-interest sequence approved by user.
    "JOB":  ["f_like_work", "p2_wk_1", "p2_wk_2", "p2_wk_3", "p2_wk_4", "p2_wk_5"],
    # DISH: ask WHY first, then variety questions.
    "DISH": ["f_food_why_good", "f_food_like_spicy", "f_food_famous_dish", "f_food_expensive"],
    "NAME": ["f_name_who_named", "p2_id_4"],
    # FAMILY: after user reveals family info, probe deeper — live together? siblings? married? children? how often?
    "FAMILY": ["p2_fa_1", "f_have_siblings", "f_married", "f_have_children", "p2_fa_2", "p2_fa_5", "p2_fa_ext1"],
    # STORY: after user answers a story-elicitation frame — probe with "why" or "tell me more"
    "STORY": ["f_generic_why"],
    # TRAVEL: which is best? then why, then continuation.
    "TRAVEL": ["f_travel_which_best", "f_travel_why_interesting", "f_want_go_where", "p2_tr_2", "p2_tr_3", "p2_tr_4"],
}


def _stable_pick(seq: list, seed: str) -> Optional[str]:
    """Deterministic pick from seq based on seed string."""
    if not seq:
        return None
    s = (seed or "").encode("utf-8", errors="ignore")
    h = 0
    for b in s:
        h = (h * 131 + b) % 2_147_483_647
    return seq[h % len(seq)]


def _looks_food_related_answer(text: str) -> bool:
    if not text:
        return False
    cues = (
        "好吃", "吃", "饺子", "火锅", "牛肉", "羊肉", "鸡肉", "鱼", "面", "米饭",
        "菜", "辣", "甜", "咸", "酸", "汤", "烧烤", "奶茶", "咖啡"
    )
    return any(c in text for c in cues)


def _looks_travel_related_answer(text: str) -> bool:
    if not text:
        return False
    cues = ("去过", "想去", "旅行", "旅游", "国家", "城市", "地方", "机票", "景点", "出国")
    return any(c in text for c in cues)


def _is_unscripted_substantive_answer(last_answer: Optional[dict], slot_names: List[str]) -> bool:
    """
    Generic probe-first rule:
    If user gives non-trivial free text but we failed to infer slots, try one curiosity probe
    before skipping/bridging away.
    """
    if slot_names:
        return False
    if not isinstance(last_answer, dict):
        return False
    # Prefer free-typed content.
    submitted = (last_answer.get("submitted_text") or "").strip()
    if not submitted:
        return False
    if len(submitted) < 4:
        return False
    # Obvious low-information fillers.
    if submitted in ("不知道", "还好", "一般", "好", "嗯", "可以"):
        return False
    return True


def _infer_slot_names_from_answer(last_answer: Optional[dict]) -> List[str]:
    """Best-effort: infer slot names from the user's answer frame (question frame_id in last_answer)."""
    if not last_answer or not isinstance(last_answer, dict):
        return []
    # last_answer.frame_id is the partner ask frame the user answered (e.g. f_from_where)
    # selected option's card_id often points to a user frame with slots; try to infer via that mapping when possible.
    # We only have selected_option_hanzi/meaning here; so use memory capture triggers + known ask frame ids.
    fid = (last_answer.get("frame_id") or "").strip()
    txt = _answer_text_from_last_answer(last_answer)

    slots: List[str] = []
    if fid in ("f_ask_you_name", "p2_id_2", "f_ask_name_meaning"):
        slots.append("NAME")
    if fid in ("f_what_work", "f_like_work", "p2_wk_1", "p2_wk_2", "p2_wk_3", "p2_wk_4", "p2_wk_5"):
        slots.append("JOB")
    if fid in ("f_food_what_good", "f_food_tasty", "f_food_like_spicy", "f_food_famous_dish", "f_food_expensive"):
        slots.append("DISH")
    if fid in ("f_travel_where", "f_want_go_where", "p2_tr_1", "p2_tr_2", "p2_tr_3", "p2_tr_4"):
        slots.append("TRAVEL")
    if fid in ("f_from_where", "frame.location.live_question", "p2_pl_1", "p2_pl_2", "p2_pl_3", "p2_pl_4", "f_place_like_there"):
        slots.append("CITY")
    # Family: answered a family opener, siblings, marriage or children question — probe deeper
    if fid in ("f_have_family", "f_have_siblings", "f_married", "f_have_children", "p2_fa_1", "p2_fa_2", "p2_fa_5", "p2_fa_ext1"):
        slots.append("FAMILY")
    # Story context: user answered a story-elicitation frame — probe for more
    if fid == "f_name_story_elicit":
        slots.append("STORY")

    # Soft-chaining: if user answer itself names food while in place thread, prioritize DISH.
    # Guard: do NOT soft-chain food/travel when the answer came from an identity/greeting frame —
    # ASR often garbles name answers into words that superficially look food-related (e.g. "好吃").
    _identity_frame_ids = frozenset({
        "f_ask_you_name", "p2_id_2", "f_ask_name_meaning", "p2_id_ext1",
        "p2_id_4", "p2_id_5", "f_name_who_named", "f_name_story_elicit",
        "frame.greeting.hello", "frame.greeting.hello_reply", "f_nice_to_meet",
    })
    _is_identity_frame = fid in _identity_frame_ids
    if _looks_food_related_answer(txt) and "DISH" not in slots and not _is_identity_frame:
        slots.insert(0, "DISH")
    elif fid == "p2_pl_2" and "DISH" not in slots:
        # p2_pl_2 asks about food in {CITY}; treat answers as dish/topic-bearing by default.
        slots.insert(0, "DISH")
    if _looks_travel_related_answer(txt) and "TRAVEL" not in slots and not _is_identity_frame:
        slots.insert(0, "TRAVEL")

    # Deduplicate preserving order.
    dedup: List[str] = []
    for s in slots:
        if s not in dedup:
            dedup.append(s)
    return dedup


def _norm_text(s: Optional[str]) -> str:
    return (s or "").strip()


def _answer_text_from_last_answer(last_answer: Optional[dict]) -> str:
    if not isinstance(last_answer, dict):
        return ""
    return _norm_text(
        last_answer.get("submitted_text")
        or last_answer.get("selected_option_hanzi")
        or ""
    )


def _stable_gate(seed: str) -> int:
    gate = 0
    for ch in (seed or ""):
        gate = (gate * 131 + ord(ch)) % 1000
    return gate


def _score_answer_interest(
    last_answer: Optional[dict],
    slot_names: List[str],
    new_memory_written: bool,
    cs: dict,
) -> int:
    text = _answer_text_from_last_answer(last_answer)
    score = 0
    if slot_names:
        score += 2
    if new_memory_written:
        score += 1
    if len(text) >= 4:
        score += 1
    # Reasoning / depth words
    if any(k in text for k in ("因为", "所以", "觉得", "但是", "最", "其实")):
        score += 1
    # Evaluative / expressive words — short but semantically rich
    _EVALUATIVE = (
        "有意思", "有趣", "好玩", "不错", "很棒", "真的", "当然", "喜欢",
        "好吃", "好看", "好听", "很好", "太好", "太有", "有故事",
    )
    if any(k in text for k in _EVALUATIVE):
        score += 1
    # Short affirmatives after a yes/no question suggest the user has more to say.
    # Detect by looking up the last partner frame from recent_frame_ids.
    _SHORT_AFFIRM = {"有", "是", "要", "对", "有的", "是的", "是啊", "当然", "有啊"}
    if text in _SHORT_AFFIRM:
        recent = cs.get("recent_frame_ids") or []
        last_fid = recent[-1] if recent else ""
        last_frame_text = (_frames_by_id.get(last_fid) or {}).get("text", "").strip()
        if "吗" in last_frame_text:
            score += 1  # "yes" to a yes/no question — probe for more
    prev = _norm_text(cs.get("last_user_text") if isinstance(cs, dict) else "")
    if text and prev and text == prev:
        score -= 1
    if text in ("好", "嗯", "不知道"):
        score -= 1
    return max(0, score)


def _classify_interest(score: int) -> str:
    if score >= INTEREST_HIGH_THRESHOLD:
        return "high"
    if score >= INTEREST_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _topic_chain_exceeded(cs: dict, slot_names: List[str]) -> bool:
    same_engine_chain = int(cs.get("same_engine_chain_count") or 0)
    same_slot_chain = int(cs.get("same_slot_chain_count") or 0)
    if same_engine_chain > MAX_SAME_ENGINE_AFTER_INTEREST:
        return True
    if slot_names and same_slot_chain > MAX_SAME_SLOT_CHAIN_AFTER_INTEREST:
        return True
    return False


def _should_force_listening_move(cs: dict, interest_level: str) -> bool:
    if interest_level == "high":
        return True
    if interest_level == "medium":
        pending = cs.get("pending_listening_move") is True
        turns_waited = int(cs.get("listening_wait_turns") or 0)
        return pending and turns_waited >= INTEREST_FORCE_WINDOW_TURNS
    return False


def _is_user_question(last_answer: Optional[dict]) -> bool:
    """
    Best-effort detection for when the user's turn is a question (counter-question / repair).
    This is important for early reciprocity: if the user asks “怎么叫你呢？”, we should answer that
    before continuing the engine ladder.
    """
    if not last_answer or not isinstance(last_answer, dict):
        return False
    # Prefer submitted free text; fall back to selected option hanzi.
    text = (last_answer.get("submitted_text") or "").strip()
    if not text:
        text = (last_answer.get("selected_option_hanzi") or "").strip()
    if not text:
        return False
    # Check for any question mark (fullwidth U+FF1F or ASCII U+003F)
    if any(ord(c) in (0xFF1F, 0x003F) for c in text):
        return True
    # Turn-around markers AS SUBSTRINGS — catches "我叫X，你呢" / "喜欢你呢" etc.
    _turn_around_markers = ("你呢", "那你呢", "你怎么想", "为什么这么问", "为什么这样问", "换我问", "你来问")
    if any(m in text for m in _turn_around_markers):
        return True
    # Direct questions about the persona (no explicit "？" needed)
    _direct_starts = (
        "你叫什么", "你的名字", "你是哪里人", "你从哪里来", "你老家在哪",
        "你住在哪", "你住哪里", "你做什么工作", "你的工作", "你是做什么",
        "你喜欢什么", "你有什么爱好", "你有家人", "你有没有家人",
        "你结婚了吗", "你有孩子", "你多大", "你几岁",
    )
    if any(text.startswith(p) for p in _direct_starts):
        return True
    # Common interrogative markers without explicit punctuation
    starters = ("怎么", "为什么", "哪里", "谁", "什么时候", "多少", "几", "哪儿", "哪裡")
    if text.startswith(starters):
        return True
    if text.endswith("吗") or ("吗" in text and len(text) <= 8):
        return True
    return False


def _assistant_name_from_persona(persona: Optional[dict]) -> str:
    """Return the persona's display name, checking all known key variants across both
    the new personas/*.json format (display_name) and the legacy persona_data.py format (persona_name)."""
    if persona and isinstance(persona, dict):
        n = (
            persona.get("display_name")
            or persona.get("persona_name")
            or persona.get("name")
            or persona.get("assistant_name")
            or ""
        ).strip()
        if n:
            return n
    return "MandarinOS"


def _persona_reply_for_ni_ne(frame_id: str, persona: Optional[dict]) -> Optional[str]:
    """
    Generate a short, natural first-person answer from the persona when the user says 你呢？
    after answering a particular frame. Uses voice_lines first, then profile fields.
    """
    if not persona:
        return None
    fid = (frame_id or "").strip()
    profile     = persona.get("profile") or {}
    voice_lines = persona.get("voice_lines") or {}
    name = _assistant_name_from_persona(persona)

    # Name questions
    if fid in ("f_ask_you_name", "p2_id_2"):
        return voice_lines.get("identity") or (f"我叫{name}。" if name else None)

    # Name meaning / name significance
    if fid in ("f_ask_name_meaning", "p2_id_ext1", "p2_id_4", "p2_id_5"):
        return voice_lines.get("identity") or "我的名字也有一个特别的意思。"

    # Where from
    if fid in ("f_from_where",):
        hometown = (profile.get("hometown") or "").strip()
        return f"我是{hometown}人。" if hometown else "我是中国人。"

    # Current location / where living
    if fid in ("frame.location.live_question", "p2_pl_ext1", "p2_pl_1"):
        city = (profile.get("city") or "").strip()
        if city:
            return f"我现在住在{city}。"
        return voice_lines.get("place") or "我现在住在中国。"

    # Work / job
    if fid in ("f_what_work", "f_like_work", "p2_wk_1", "p2_wk_2"):
        occ = (profile.get("occupation") or "").strip()
        return voice_lines.get("work") or (f"我是{occ}。" if occ else "我也有工作。")

    # Hobbies
    if fid in ("f_what_hobby", "f_often_do", "f_like_do_what", "f_weekend_do",
               "f_difficult_ma", "f_recommend_ma", "p2_hb_1", "p2_hb_2"):
        interests = profile.get("interests") or []
        if voice_lines.get("hobby"):
            return voice_lines["hobby"]
        if interests:
            return f"我喜欢{interests[0]}。"
        return "我也有爱好。"

    # Travel
    if fid in ("f_travel_where", "f_want_go_where", "p2_tr_1", "p2_tr_2"):
        return voice_lines.get("travel") or "我也喜欢旅行。"

    # Food
    if fid in ("f_food_what_good", "f_food_famous_dish", "f_food_tasty",
               "p2_pl_2", "f_food_like_spicy", "f_food_expensive"):
        return voice_lines.get("food") or "我觉得好吃的食物很重要。"

    # Family
    if fid in ("f_have_family", "f_have_siblings", "f_married", "f_have_children", "p2_fa_1", "p2_fa_2", "p2_fa_5"):
        return voice_lines.get("family") or "我也有家人。"

    # Place / life quality fallbacks
    if fid in ("f_place_like_there", "f_place_why_like", "p2_pl_3", "p2_pl_4"):
        return voice_lines.get("place") or "我觉得住的地方很重要。"

    # Engine-level fallback: use voice_line for the frame's engine
    frame_rec = _frames_by_id.get(fid) or {}
    engine = (frame_rec.get("engine") or "").strip().lower()
    if engine and engine in voice_lines:
        return voice_lines[engine]

    return None


def _direct_persona_answer(t: str, persona: Optional[dict]) -> Optional[str]:
    """
    Detect direct questions aimed at the partner persona (你是哪里人？ 你住哪里？ etc.)
    and return a short first-person answer from persona profile/voice_lines.
    Returns None when no pattern matches.
    """
    profile     = (persona or {}).get("profile") or {}
    voice_lines = (persona or {}).get("voice_lines") or {}
    name        = _assistant_name_from_persona(persona)

    # Origin / hometown
    if any(p in t for p in ("你是哪里人", "你从哪里来", "你老家", "你哪里人")):
        hometown = (profile.get("hometown") or "").strip()
        if hometown:
            return f"我是{hometown}人。"
        return voice_lines.get("place") or "我是中国人。"

    # Current city / where partner lives
    if any(p in t for p in ("你住在哪", "你住哪", "你现在住", "你住的地方")):
        city = (profile.get("city") or "").strip()
        if city:
            return f"我住在{city}。"
        hometown = (profile.get("hometown") or "").strip()
        return voice_lines.get("place") or (f"我住在{hometown}附近。" if hometown else "我在中国住。")

    # Name meaning / story — must be checked BEFORE the generic name pattern
    # because "你的名字有什么意思" ALSO contains "你的名字".
    _facts = (persona or {}).get("discoverable_facts") or {}
    if any(p in t for p in ("你的名字是什么意思", "你的名字有什么意思", "名字什么意思",
                             "名字的意思", "名字有什么意思", "名字是什么意思")):
        fact = (_facts.get("identity") or "").strip()
        return fact if fact else f"我叫{name}，这个名字有一点特别的意思，是家人给取的。"
    if any(p in t for p in ("名字有什么故事", "名字的故事", "名字怎么来", "名字怎么取")):
        fact = (_facts.get("identity") or "").strip()
        return fact if fact else "我的名字有一个小故事，家里人取的，有机会再说给你听。"

    # Name / how to address (who-are-you / what-should-I-call-you)
    if any(p in t for p in ("你叫什么", "你叫啥", "怎么叫你", "你叫什么名字",
                             "你的名字叫", "你名字叫")):
        return (f"你可以叫我{name}。" if name else None)

    # Job / work
    if any(p in t for p in ("你做什么工作", "你的工作", "你是做什么", "你工作")):
        occ = (profile.get("occupation") or "").strip()
        return voice_lines.get("work") or (f"我是{occ}。" if occ else "我也有工作。")

    # Hobbies / interests
    if any(p in t for p in ("你喜欢什么", "你有什么爱好", "你喜欢做什么", "你的爱好")):
        interests = profile.get("interests") or []
        return voice_lines.get("hobby") or (f"我喜欢{interests[0]}。" if interests else "我也有很多爱好。")

    # Family — has family / siblings
    if any(p in t for p in ("你有家人", "你有没有家人", "你的家人")):
        return voice_lines.get("family") or "我也有家人。"

    # Married / partner status
    if any(p in t for p in ("你结婚", "你有没有结婚", "你有对象", "你有伴侣",
                             "你有男朋友", "你有女朋友", "你成家了")):
        return voice_lines.get("family") or "这个嘛……不好说！"

    # Children
    if any(p in t for p in ("你有孩子", "你有小孩", "你有儿子", "你有女儿", "你有宝宝")):
        return voice_lines.get("family") or "这个……还没有！"

    # Age
    if any(p in t for p in ("你多大", "你几岁", "你的年龄", "你今年多大")):
        return "哈，年龄这种事……说多少都不准！反正我不老就是了。"

    return None


def _answer_user_question_prefix(last_answer: Optional[dict], persona: Optional[dict]) -> Optional[str]:
    """
    Return a short prefix that answers common counter-questions without adding new API turns.
    Handles: direct persona questions (你是哪里人？ 你住哪里？ etc.),
             generic 你呢 (alone or at end of a compound answer),
             and direct name questions.
    """
    if not _is_user_question(last_answer):
        return None
    t = (last_answer.get("submitted_text") or last_answer.get("selected_option_hanzi") or "").strip()
    if not t:
        return None

    # Mirror questions (richest answers — use discoverable_facts / profile via _mirror_persona_stub)
    _mirror = _find_mirror_answer(t, "", persona)
    if _mirror:
        return _mirror

    # Direct questions aimed at the partner (你是哪里人？ 你住哪里？ etc.)
    _direct = _direct_persona_answer(t, persona)
    if _direct:
        return f"我呢，{_direct}" if not _direct.startswith("我") else _direct

    # Generic 你呢 — whether standalone or at end of a compound answer
    _ni_ne_markers = ("你呢", "那你呢", "你怎么想", "为什么这么问", "为什么这样问", "换我问", "你来问")
    _has_ni_ne = any(m in t for m in _ni_ne_markers)
    if _has_ni_ne:
        fid = (last_answer.get("frame_id") or "").strip()
        reply = _persona_reply_for_ni_ne(fid, persona)
        if reply:
            return f"我呢，{reply}" if not reply.startswith("我呢") else reply
        # No persona or no frame-specific reply — prefer engine-specific generic over the name
        _frame_eng = (_frames_by_id.get(fid) or {}).get("engine") or ""
        _generics: dict = {
            "identity": None,           # handled by name below
            "place":    "我也住在中国，挺喜欢的。",
            "work":     "我也有工作，还挺有意思的。",
            "hobby":    "我也有几个爱好，有空会聊。",
            "family":   "我也有家人，关系挺好的。",
            "food":     "我也很喜欢吃东西，尤其是家乡菜。",
            "travel":   "我也旅行过几个地方，很有意思。",
        }
        _gen = _generics.get(_frame_eng.lower())
        if _gen:
            return f"我呢，{_gen}"
        # Identity / unknown engine: use name as a natural reply
        an = _assistant_name_from_persona(persona)
        if an and an != "MandarinOS":
            return f"我呢，你可以叫我{an}。"
        return "我呢，这是个好问题。"

    # Catch-all: user asked a question we don't have a specific answer for.
    # Phrases should complete the thought — not trail off — so the persona sounds natural,
    # not evasive. The conversation pauses client-side so the user stays in control.
    _graceful = [
        "哎，这个嘛……说来话长，有空再聊！",   # That's a long story — let's talk another time!
        "嗯，好问题！我得好好想想。",            # Good question — I need to really think about it.
        "这个……我不太好说，不好意思！",         # That's hard to say, sorry!
        "哈，你问到点子上了！我还没想好怎么回答。",  # You've hit the nail on the head — I haven't figured out how to answer yet.
        "嗯，有意思的问题！下次一定好好说。",    # Interesting question — I'll definitely tell you next time.
    ]
    return _stable_pick(_graceful, t) or "这个嘛……说来话长，有空再聊！"


# ---------------------------------------------------------------------------
# Sentence-level response options
# ---------------------------------------------------------------------------
# Ordered list of (pattern_substring, [{"zh", "py", "en"}, ...])
# First matching pattern wins. Options are trimmed to 3 max.
_SENTENCE_OPTION_PATTERNS: list = [
    # — Identity —
    ("叫什么名字",   [
        {"zh": "我叫___。",        "py": "Wǒ jiào ___.",          "en": "My name is ___."},
        {"zh": "大家叫我___。",    "py": "Dàjiā jiào wǒ ___.",    "en": "People call me ___."},
        {"zh": "我的名字是___。",  "py": "Wǒ de míngzì shì ___.", "en": "My name is ___."},
    ]),
    ("怎么叫",       [
        {"zh": "大家叫我___。",    "py": "Dàjiā jiào wǒ ___.",    "en": "People call me ___."},
        {"zh": "叫我___就好了。",  "py": "Jiào wǒ ___ jiù hǎo le.", "en": "Just call me ___."},
    ]),
    ("名字是什么意思", [
        {"zh": "有一点复杂。",     "py": "Yǒu yīdiǎn fùzá.",     "en": "It's a bit complicated."},
        {"zh": "有好的意思。",     "py": "Yǒu hǎo de yìsi.",      "en": "It has a good meaning."},
        {"zh": "我不太清楚。",     "py": "Wǒ bù tài qīngchǔ.",   "en": "I'm not quite sure."},
    ]),
    ("觉得你的名字怎么样", [
        {"zh": "我觉得还不错。",   "py": "Wǒ juéde hái búcuò.",   "en": "I think it's pretty good."},
        {"zh": "我很喜欢。",       "py": "Wǒ hěn xǐhuān.",        "en": "I really like it."},
        {"zh": "有一点特别。",     "py": "Yǒu yīdiǎn tèbié.",     "en": "It's a bit special."},
    ]),
    ("谁给你取",     [
        {"zh": "是我妈妈取的。",   "py": "Shì wǒ māma qǔ de.",    "en": "My mum chose it."},
        {"zh": "是我爸爸取的。",   "py": "Shì wǒ bàba qǔ de.",    "en": "My dad chose it."},
        {"zh": "家人给我取的。",   "py": "Jiārén gěi wǒ qǔ de.",  "en": "My family chose it."},
    ]),
    ("有什么故事",   [
        {"zh": "有！",             "py": "Yǒu!",                   "en": "Yes there is!"},
        {"zh": "有一个小故事。",   "py": "Yǒu yīgè xiǎo gùshi.",  "en": "There's a little story."},
        {"zh": "没有特别的故事。", "py": "Méiyǒu tèbié de gùshi.", "en": "Nothing special."},
    ]),
    ("是什么故事",   [
        {"zh": "是关于家人的。",   "py": "Shì guānyú jiārén de.", "en": "It's about my family."},
        {"zh": "是个有意思的故事。","py": "Shì gè yǒuyìsi de gùshi.", "en": "It's an interesting story."},
        {"zh": "说来话长。",       "py": "Shuō lái huà cháng.",   "en": "It's a long story."},
    ]),
    # — Place / Origin —
    ("哪里人",       [
        {"zh": "我是新西兰人。",   "py": "Wǒ shì Xīnxīlán rén.",  "en": "I'm from New Zealand."},
        {"zh": "我是外国人。",     "py": "Wǒ shì wàiguórén.",      "en": "I'm a foreigner."},
        {"zh": "我从英国来。",     "py": "Wǒ cóng Yīngguó lái.",   "en": "I'm from the UK."},
    ]),
    ("住哪里",       [
        {"zh": "我住在___。",      "py": "Wǒ zhù zài ___.",        "en": "I live in ___."},
        {"zh": "我现在住___。",    "py": "Wǒ xiànzài zhù ___.",    "en": "I currently live in ___."},
        {"zh": "我一个人住。",     "py": "Wǒ yīgè rén zhù.",       "en": "I live alone."},
    ]),
    ("现在住",       [
        {"zh": "我住在___。",      "py": "Wǒ zhù zài ___.",        "en": "I live in ___."},
        {"zh": "我现在住___。",    "py": "Wǒ xiànzài zhù ___.",    "en": "I currently live in ___."},
    ]),
    ("生活怎么样",   [
        {"zh": "生活不错。",       "py": "Shēnghuó búcuò.",        "en": "Life is pretty good."},
        {"zh": "生活很好。",       "py": "Shēnghuó hěn hǎo.",      "en": "Life is great."},
        {"zh": "还可以。",         "py": "Hái kěyǐ.",              "en": "It's alright."},
    ]),
    ("住的地方有什么特色", [
        {"zh": "风景很好看。",     "py": "Fēngjǐng hěn hǎokàn.",  "en": "The scenery is beautiful."},
        {"zh": "天气不错。",       "py": "Tiānqì búcuò.",          "en": "The weather is nice."},
        {"zh": "有很多好吃的。",   "py": "Yǒu hěn duō hǎochī de.", "en": "There's lots of great food."},
    ]),
    ("喜欢那儿吗",   [
        {"zh": "喜欢！很好。",     "py": "Xǐhuān! Hěn hǎo.",      "en": "Yes! It's great."},
        {"zh": "还不错。",         "py": "Hái búcuò.",             "en": "It's pretty good."},
        {"zh": "一般般。",         "py": "Yībān bān.",             "en": "Just so-so."},
    ]),
    # — Food —
    ("好吃吗",       [
        {"zh": "很好吃！",         "py": "Hěn hǎochī!",           "en": "Very delicious!"},
        {"zh": "还可以。",         "py": "Hái kěyǐ.",             "en": "It's alright."},
        {"zh": "一般般。",         "py": "Yībān bān.",            "en": "So-so."},
    ]),
    ("好吃的",       [
        {"zh": "___很好吃。",      "py": "___ hěn hǎochī.",        "en": "___ is very good."},
        {"zh": "有很多好吃的！",   "py": "Yǒu hěn duō hǎochī de!", "en": "There's lots of good food!"},
        {"zh": "我喜欢___。",      "py": "Wǒ xǐhuān ___.",         "en": "I like ___."},
    ]),
    ("最有名的菜",   [
        {"zh": "___最有名。",      "py": "___ zuì yǒumíng.",       "en": "___ is most famous."},
        {"zh": "很难说。",         "py": "Hěn nán shuō.",          "en": "It's hard to say."},
        {"zh": "有很多有名的菜。", "py": "Yǒu hěn duō yǒumíng de cài.", "en": "There are many famous dishes."},
    ]),
    ("吃东西是一种享受", [
        {"zh": "当然是！",         "py": "Dāngrán shì!",           "en": "Of course it is!"},
        {"zh": "我觉得是。",       "py": "Wǒ juéde shì.",          "en": "I think so."},
        {"zh": "有时候是。",       "py": "Yǒushíhou shì.",         "en": "Sometimes yes."},
    ]),
    ("贵不贵",       [
        {"zh": "不贵。",           "py": "Bù guì.",                "en": "Not expensive."},
        {"zh": "有一点贵。",       "py": "Yǒu yīdiǎn guì.",        "en": "A little expensive."},
        {"zh": "还可以。",         "py": "Hái kěyǐ.",              "en": "Reasonable."},
    ]),
    ("喜欢吃什么",   [
        {"zh": "我最喜欢吃___。",  "py": "Wǒ zuì xǐhuān chī ___.", "en": "I like eating ___ most."},
        {"zh": "我喜欢很多东西。", "py": "Wǒ xǐhuān hěn duō dōngxi.", "en": "I like lots of things."},
        {"zh": "不太确定。",       "py": "Bù tài quèdìng.",        "en": "Not sure."},
    ]),
    # — Travel —
    ("去过哪",       [
        {"zh": "我去过很多地方。", "py": "Wǒ qùguò hěn duō dìfāng.", "en": "I've been to many places."},
        {"zh": "我去过___。",      "py": "Wǒ qùguò ___.",           "en": "I've been to ___."},
        {"zh": "我没去过太多地方。","py": "Wǒ méi qùguò tài duō dìfāng.", "en": "I haven't been many places."},
    ]),
    ("哪些国家",     [
        {"zh": "我去过法国、英国。","py": "Wǒ qùguò Fǎguó, Yīngguó.", "en": "I've been to France, the UK."},
        {"zh": "我去过___。",      "py": "Wǒ qùguò ___.",           "en": "I've been to ___."},
        {"zh": "很多国家。",       "py": "Hěn duō guójiā.",         "en": "Many countries."},
    ]),
    ("想去哪",       [
        {"zh": "我想去中国。",     "py": "Wǒ xiǎng qù Zhōngguó.", "en": "I want to go to China."},
        {"zh": "我想去日本。",     "py": "Wǒ xiǎng qù Rìběn.",    "en": "I want to go to Japan."},
        {"zh": "我想去很多地方。", "py": "Wǒ xiǎng qù hěn duō dìfāng.", "en": "I want to go many places."},
    ]),
    ("最喜欢哪里",   [
        {"zh": "我最喜欢___。",    "py": "Wǒ zuì xǐhuān ___.",     "en": "I like ___ best."},
        {"zh": "都很有意思。",     "py": "Dōu hěn yǒuyìsi.",       "en": "All interesting."},
        {"zh": "很难说。",         "py": "Hěn nán shuō.",          "en": "Hard to say."},
    ]),
    ("旅行的时候",   [
        {"zh": "我喜欢看风景。",   "py": "Wǒ xǐhuān kàn fēngjǐng.", "en": "I like sightseeing."},
        {"zh": "我喜欢吃东西。",   "py": "Wǒ xǐhuān chī dōngxi.",   "en": "I like trying the food."},
        {"zh": "我喜欢走路。",     "py": "Wǒ xǐhuān zǒulù.",        "en": "I like walking around."},
    ]),
    ("好玩的",       [
        {"zh": "有很多好玩的地方。","py": "Yǒu hěn duō hǎowán de dìfāng.", "en": "There are many fun places."},
        {"zh": "文化很丰富。",     "py": "Wénhuà hěn fēngfù.",     "en": "The culture is very rich."},
        {"zh": "风景很美。",       "py": "Fēngjǐng hěn měi.",      "en": "The scenery is beautiful."},
    ]),
    # — Family —
    ("跟家人住在一起", [
        {"zh": "是的，住在一起。", "py": "Shì de, zhù zài yīqǐ.",  "en": "Yes, we live together."},
        {"zh": "不，我一个人住。", "py": "Bù, wǒ yīgè rén zhù.",   "en": "No, I live alone."},
        {"zh": "有时候住在一起。", "py": "Yǒushíhou zhù zài yīqǐ.", "en": "Sometimes together."},
    ]),
    ("多久见一次家人", [
        {"zh": "每天都见。",       "py": "Měitiān dōu jiàn.",      "en": "Every day."},
        {"zh": "每周见一次。",     "py": "Měi zhōu jiàn yīcì.",    "en": "Once a week."},
        {"zh": "不太常见。",       "py": "Bù tài cháng jiàn.",     "en": "Not very often."},
    ]),
    ("和家人一起做",  [
        {"zh": "一起吃饭。",       "py": "Yīqǐ chīfàn.",           "en": "Eat together."},
        {"zh": "一起看电影。",     "py": "Yīqǐ kàn diànyǐng.",     "en": "Watch movies together."},
        {"zh": "一起出去玩。",     "py": "Yīqǐ chūqù wán.",        "en": "Go out together."},
    ]),
    # — Work / Study —
    ("喜欢你的工作",  [
        {"zh": "很喜欢！",         "py": "Hěn xǐhuān!",            "en": "I love it!"},
        {"zh": "还可以。",         "py": "Hái kěyǐ.",              "en": "It's alright."},
        {"zh": "有时候不太喜欢。", "py": "Yǒushíhou bù tài xǐhuān.", "en": "Sometimes not so much."},
    ]),
    ("为什么喜欢这份工作", [
        {"zh": "因为很有意思。",   "py": "Yīnwèi hěn yǒuyìsi.",    "en": "Because it's interesting."},
        {"zh": "因为可以帮助别人。","py": "Yīnwèi kěyǐ bāngzhù biérén.", "en": "Because I help people."},
        {"zh": "说不太清楚。",     "py": "Shuō bù tài qīngchǔ.",  "en": "Hard to explain."},
    ]),
    ("工作难吗",      [
        {"zh": "有一点难。",       "py": "Yǒu yīdiǎn nán.",        "en": "A little difficult."},
        {"zh": "还好，不太难。",   "py": "Hái hǎo, bù tài nán.",   "en": "OK, not too hard."},
        {"zh": "很难！",           "py": "Hěn nán!",               "en": "Very hard!"},
    ]),
    ("做什么工作",    [
        {"zh": "我是老师。",       "py": "Wǒ shì lǎoshī.",         "en": "I'm a teacher."},
        {"zh": "我在公司工作。",   "py": "Wǒ zài gōngsī gōngzuò.", "en": "I work for a company."},
        {"zh": "我还在学习。",     "py": "Wǒ hái zài xuéxí.",      "en": "I'm still studying."},
    ]),
    ("工作的时候",    [
        {"zh": "跟同事合作很开心。","py": "Gēn tóngshì hézuò hěn kāixīn.", "en": "Working with colleagues is fun."},
        {"zh": "完成工作很有成就感。","py": "Wánchéng gōngzuò hěn yǒu chéngjiùgǎn.", "en": "Finishing tasks feels rewarding."},
        {"zh": "没有特别的事。",   "py": "Méiyǒu tèbié de shì.",   "en": "Nothing special."},
    ]),
    # — Hobbies —
    ("什么爱好",      [
        {"zh": "我喜欢喝茶。",     "py": "Wǒ xǐhuān hē chá.",      "en": "I like drinking tea."},
        {"zh": "我喜欢看书。",     "py": "Wǒ xǐhuān kàn shū.",     "en": "I like reading."},
        {"zh": "我喜欢运动。",     "py": "Wǒ xǐhuān yùndòng.",     "en": "I like sport."},
    ]),
    ("喜欢做什么",    [
        {"zh": "我喜欢喝茶。",     "py": "Wǒ xǐhuān hē chá.",      "en": "I like drinking tea."},
        {"zh": "我喜欢看书。",     "py": "Wǒ xǐhuān kàn shū.",     "en": "I like reading."},
        {"zh": "我喜欢和朋友出去。","py": "Wǒ xǐhuān hé péngyǒu chūqù.", "en": "I like going out with friends."},
    ]),
    # — Generic patterns (must be LAST) —
    ("吗",            [
        {"zh": "是的！",           "py": "Shì de!",                "en": "Yes!"},
        {"zh": "对。",             "py": "Duì.",                   "en": "That's right."},
        {"zh": "不太。",           "py": "Bù tài.",                "en": "Not really."},
    ]),
    ("怎么样",        [
        {"zh": "很好！",           "py": "Hěn hǎo!",              "en": "Very good!"},
        {"zh": "还不错。",         "py": "Hái búcuò.",             "en": "Pretty good."},
        {"zh": "一般般。",         "py": "Yībān bān.",             "en": "So-so."},
    ]),
    ("为什么",        [
        {"zh": "因为很有意思。",   "py": "Yīnwèi hěn yǒuyìsi.",   "en": "Because it's interesting."},
        {"zh": "因为我喜欢。",     "py": "Yīnwèi wǒ xǐhuān.",     "en": "Because I like it."},
        {"zh": "说不太清楚。",     "py": "Shuō bù tài qīngchǔ.",  "en": "Hard to explain."},
    ]),
    ("什么",          [
        {"zh": "有很多。",         "py": "Yǒu hěn duō.",           "en": "There are many."},
        {"zh": "不太确定。",       "py": "Bù tài quèdìng.",        "en": "Not sure."},
        {"zh": "有意思。",         "py": "Yǒuyìsi.",               "en": "Interesting."},
    ]),
]

# Generic fallback options for any unmatched question
_SENTENCE_OPTIONS_GENERIC = [
    {"zh": "是的！",     "py": "Shì de!",      "en": "Yes!"},
    {"zh": "不太。",     "py": "Bù tài.",      "en": "Not really."},
    {"zh": "还不错。",   "py": "Hái búcuò.",   "en": "Pretty good."},
]


def _build_sentence_options(frame_rec: dict, memory: Optional[dict]) -> list:
    """
    Generate 2-3 full sentence options appropriate for the given frame question.
    Returns list of {"zh", "py", "en", "id"} dicts with kind="SENTENCE".
    """
    text = (frame_rec.get("text") or "").strip()
    if not text:
        return []

    # Memory slots for filling in known facts
    mem = memory or {}
    city = (mem.get("lives_in") or mem.get("from_city") or "").strip()
    name = (mem.get("learner_name") or "").strip()
    food = (mem.get("favourite_food") or "").strip()

    # Find matching template pool
    chosen = None
    for pattern, templates in _SENTENCE_OPTION_PATTERNS:
        if pattern in text:
            chosen = templates
            break
    if chosen is None:
        chosen = _SENTENCE_OPTIONS_GENERIC

    result = []
    for i, t in enumerate(chosen[:3]):
        zh = t["zh"]
        # Fill known memory facts into placeholders
        if "___" in zh:
            if name and ("叫" in zh or "名字" in zh):
                zh = zh.replace("___", name)
            elif city and ("住" in zh or "人" in zh):
                zh = zh.replace("___", city)
            elif food and "吃" in zh:
                zh = zh.replace("___", food)
            # else leave ___ as visual hint that user should fill in their own detail
        result.append({
            "id":   f"__sent_{i}",
            "zh":   zh,
            "py":   t["py"],
            "en":   t["en"],
            "kind": "SENTENCE",
        })
    return result


def _should_surface_curiosity(
    cs: dict,
    *,
    meaningful: bool,
    last_partner_was_loop: bool,
    last_partner_had_reaction: bool,
    interest_level: str = "low",
) -> bool:
    """Visibility gating for probe row (curiosity options).
    interest_level is now the primary trigger: medium/high always surfaces probes.
    """
    # Phase 12B: suppress if probe depth limit reached
    if int(cs.get("probe_depth") or 0) >= MAX_PROBE_CHAIN:
        return False
    # Only suppress on the very first exchange (no conversation history yet)
    recent = cs.get("recent_frame_ids") or []
    if not recent:
        return False
    if cs.get("prefer_bridge") is True or cs.get("force_bridge") is True:
        return False
    # Primary trigger: medium or high interest always earns probe buttons
    if interest_level in ("medium", "high"):
        return True
    if last_partner_was_loop:
        return True
    if meaningful:
        return True
    # Interview drift: 2 consecutive asks without loop or reaction
    drift = int(cs.get("ask_chain_count") or 0)
    if drift >= 2 and not last_partner_had_reaction:
        return True
    return False


def _select_probe_options(engine_id: str, slot_names: List[str]) -> list:
    """Return 1–2 probe option dicts from _OXYGEN_LOOP_PROBES based on context."""
    engine_norm = (engine_id or "").strip().lower()
    desired_ids: List[str] = []
    for s in slot_names or []:
        desired_ids.extend(_OXYGEN_IDS_BY_SLOT.get(s, []))
    if not desired_ids:
        desired_ids = _OXYGEN_IDS_BY_ENGINE.get(engine_norm, ["weishenme", "zenmeyang"])
    # Deduplicate, preserve order, cap 2
    seen = set()
    desired = []
    for pid in desired_ids:
        if pid in seen:
            continue
        seen.add(pid)
        desired.append(pid)
        if len(desired) >= 2:
            break
    by_id = {p.get("id"): p for p in _OXYGEN_LOOP_PROBES if isinstance(p, dict)}
    return [by_id[i] for i in desired if i in by_id]


def _pick_reaction_text(engine_id: str, seed: str, *, interest_level: str = "low", exchange_count: int = 0) -> str:
    """Return a short reaction phrase. When interest is high AND we're past the opening
    exchanges, use curiosity questions so the partner sounds genuinely engaged."""
    engine_norm = (engine_id or "").strip().lower()
    # Only swap to curiosity reactions after the conversation is established (exchange ≥ 3)
    # so the greeting / name exchange doesn't trigger "为什么呢？"
    if interest_level == "high" and exchange_count >= 3:
        seq = _CURIOSITY_REACTIONS_BY_ENGINE.get(engine_norm) or _CURIOSITY_REACTIONS_GENERIC
    else:
        seq = _REACTION_FALLBACKS_BY_ENGINE.get(engine_norm) or _REACTION_FALLBACKS_GENERIC
    return _stable_pick(seq, seed) or "嗯。"


def _pick_reaction_frame_id(engine_id: str) -> Optional[str]:
    """Prefer existing topic-specific reaction frames where they exist."""
    engine_norm = (engine_id or "").strip().lower()
    # Currently only a few explicit reaction frames exist; keep this conservative.
    if engine_norm == "place" and "f_place_reaction" in _frames_by_id:
        return "f_place_reaction"
    if engine_norm == "identity" and "f_nice_to_meet" in _frames_by_id:
        return "f_nice_to_meet"
    return None


def _pick_slot_followup_frame_id(
    engine_id: str,
    slot_names: List[str],
    recent_frame_ids: list,
    memory: Optional[dict],
    exchange_count: int = 0,
) -> Optional[str]:
    """Try slot/topic follow-up frames before generic ladder; avoid weak loop frames if possible."""
    recent = set(recent_frame_ids or [])
    # NAME deep-followups (who named you, meaning, etc.) need a few exchanges of context first
    # so they don't land as the very first reply to the user introducing themselves.
    _NAME_DEEP_FOLLOWUP_MIN_EXCHANGES = 3
    _name_deep_followups = frozenset({"f_name_who_named", "p2_id_4", "p2_id_5", "f_name_story_elicit"})

    for s in slot_names or []:
        prefs = _SLOT_FOLLOWUP_PREFERENCES.get(s) or []
        # Prefer non-weak frames first
        ordered = [f for f in prefs if f not in _WEAK_LOOP_FRAME_IDS] + [f for f in prefs if f in _WEAK_LOOP_FRAME_IDS]
        for fid in ordered:
            if fid in recent:
                continue
            # Guard: name deep-followups only after conversation is established
            if fid in _name_deep_followups and exchange_count < _NAME_DEEP_FOLLOWUP_MIN_EXCHANGES:
                continue
            if memory is not None and _should_suppress_ask_frame(fid, memory, recent_frame_ids or [], RECALL_INTERVAL_TURNS):
                continue
            # Only allow partner questions
            fr = _frames_by_id.get(fid) or {}
            if "？" not in (fr.get("text") or ""):
                continue
            return fid
    return None


def _is_loop_candidate(frame_id: str) -> bool:
    """Heuristic: treat selected P2 follow-ups and some engine follow-ups as loop-capable."""
    if not frame_id:
        return False
    return frame_id.startswith("p2_") or frame_id in ("f_food_like_spicy", "f_food_tasty", "p2_pl_4")


def _probe_stub_for_persona(probe_id: str, persona: Optional[dict]) -> str:
    """
    Phase 10 Step 6: return persona-consistent stub for probe_id where it fits.
    Uses persona's favourite_food, occupation, hometown, etc. when available.
    """
    base = _PROBE_STUB_BY_ID.get(probe_id) or _PROBE_STUB_DEFAULT
    if not persona or not isinstance(persona, dict):
        return base
    food = (persona.get("favourite_food") or "").strip()
    occupation = (persona.get("occupation") or "").strip()
    hometown = (persona.get("hometown") or "").strip()
    if probe_id == "weishenme" and food:
        return f"嗯，因为我很喜欢{food}。"
    if probe_id == "nali" and hometown:
        return f"在{hometown}。"
    if probe_id == "zenmeyang" and occupation:
        return f"挺好的，我是{occupation}。"
    return base


# Mirror questions the learner can ask the persona after a direction turn — keyed by engine.
_MIRROR_QUESTIONS_BY_ENGINE: dict = {
    "identity": [
        {"zh": "你的名字是什么意思？", "py": "nǐ de míngzi shì shénme yìsi?",     "en": "What does your name mean?",              "kind": "SENTENCE", "topic": "name_meaning"},
        {"zh": "谁给你取的名字？",     "py": "shéi gěi nǐ qǔ de míngzi?",          "en": "Who gave you your name?",                "kind": "SENTENCE", "topic": "name_giver"},
        {"zh": "名字背后有什么故事吗？","py": "míngzi bèihòu yǒu shénme gùshi ma?", "en": "Is there a story behind your name?",     "kind": "SENTENCE", "topic": "name_story"},
    ],
    "food": [
        {"zh": "你最喜欢吃什么？",     "py": "nǐ zuì xǐhuān chī shénme?",           "en": "What do you like to eat most?",          "kind": "SENTENCE", "topic": "food_fav"},
        {"zh": "你家乡有什么好吃的？", "py": "nǐ jiāxiāng yǒu shénme hǎochī de?",   "en": "What good food does your hometown have?", "kind": "SENTENCE", "topic": "food_local"},
        {"zh": "你喜欢吃辣吗？",       "py": "nǐ xǐhuān chī là ma?",                "en": "Do you like spicy food?",                "kind": "SENTENCE", "topic": "food_spicy"},
    ],
    "place": [
        {"zh": "你是哪里人？",         "py": "nǐ shì nǎlǐ rén?",                    "en": "Where are you from?",                    "kind": "SENTENCE", "topic": "place_from"},
        {"zh": "那里有什么特别的？",   "py": "nàlǐ yǒu shénme tèbié de?",           "en": "What's special about that place?",       "kind": "SENTENCE", "topic": "place_special"},
        {"zh": "你喜欢在那里生活吗？", "py": "nǐ xǐhuān zài nàlǐ shēnghuó ma?",    "en": "Do you enjoy living there?",             "kind": "SENTENCE", "topic": "place_like"},
    ],
    "travel": [
        {"zh": "你去过哪里？",         "py": "nǐ qùguò nǎlǐ?",                      "en": "Where have you been?",                   "kind": "SENTENCE", "topic": "travel_where"},
        {"zh": "最难忘的旅行是哪次？", "py": "zuì nánwàng de lǚxíng shì nǎ cì?",   "en": "What's your most memorable trip?",       "kind": "SENTENCE", "topic": "travel_memorable"},
        {"zh": "你最喜欢哪个地方？",   "py": "nǐ zuì xǐhuān nǎ ge dìfāng?",         "en": "Which place do you like most?",          "kind": "SENTENCE", "topic": "travel_fav"},
    ],
    "work": [
        {"zh": "你做什么工作？",       "py": "nǐ zuò shénme gōngzuò?",              "en": "What do you do for work?",               "kind": "SENTENCE", "topic": "work_what"},
        {"zh": "你做这份工作多久了？", "py": "nǐ zuò zhèfèn gōngzuò duōjiǔ le?",   "en": "How long have you been doing this?",     "kind": "SENTENCE", "topic": "work_duration"},
        {"zh": "你在哪里分享你的作品？","py": "nǐ zài nǎlǐ fēnxiǎng nǐ de zuòpǐn?", "en": "Where do you share your work?",         "kind": "SENTENCE", "topic": "work_platform"},
        {"zh": "你喜欢你的工作吗？",   "py": "nǐ xǐhuān nǐ de gōngzuò ma?",         "en": "Do you like your work?",                 "kind": "SENTENCE", "topic": "work_like"},
    ],
    "family": [
        {"zh": "你家里有几个人？",     "py": "nǐ jiālǐ yǒu jǐ gè rén?",             "en": "How many people are in your family?",    "kind": "SENTENCE", "topic": "family_size"},
        {"zh": "你有兄弟姐妹吗？",     "py": "nǐ yǒu xiōngdì jiěmèi ma?",           "en": "Do you have siblings?",                  "kind": "SENTENCE", "topic": "family_siblings"},
        {"zh": "你们住在一起吗？",     "py": "nǐmen zhù zài yīqǐ ma?",              "en": "Do you all live together?",              "kind": "SENTENCE", "topic": "family_live"},
    ],
    "hobby": [
        {"zh": "你喜欢做什么？",       "py": "nǐ xǐhuān zuò shénme?",               "en": "What do you like to do?",                "kind": "SENTENCE", "topic": "hobby_what"},
        {"zh": "你玩这个多久了？",     "py": "nǐ wán zhège duōjiǔ le?",              "en": "How long have you been doing that?",     "kind": "SENTENCE", "topic": "hobby_duration"},
    ],
}


def _first_clause(text: str) -> str:
    """Return the first natural clause of a Chinese sentence (up to the first 、，or ,).
    Appends 。 so the fragment sounds complete. Used for progressive disclosure: the learner
    gets a teaser on first ask, then pulls depth with follow-up questions."""
    if not text:
        return text
    m = re.search(r'[，、,]', text)
    if m and m.start() >= 4:          # at least 4 chars before the comma — avoid trivial splits
        return text[:m.start()].rstrip() + "。"
    return text  # already short, or no natural split — return as-is


def _nth_clause(text: str, n: int) -> str:
    """Return the n-th clause (0-indexed) of a Chinese sentence split on commas.
    Used to reveal depth on follow-up questions."""
    parts = re.split(r'[，、,]', text)
    parts = [p.strip().rstrip("。.") for p in parts if p.strip()]
    if n < len(parts):
        tail = parts[n]
        return tail + ("。" if not tail.endswith("。") else "")
    return ""


def _mirror_persona_stub(topic: str, engine_id: str, persona: Optional[dict]) -> str:
    """Persona's answer to a learner's mirror question about the persona."""
    if not persona:
        return "我觉得都挺有意思的。"
    facts   = persona.get("discoverable_facts") or {}
    profile = persona.get("profile") or {}
    name    = _assistant_name_from_persona(persona)

    # ── Identity / name ─────────────────────────────────────────────────────────
    if topic in ("name_meaning", "name_story", "name_giver"):
        fact = (facts.get("identity") or "").strip()
        if topic == "name_giver":
            # Depth: who gave the name — second clause usually names the person
            depth = _nth_clause(fact, 1) if fact else ""
            return depth or "是我父母给我取的名字。"
        if topic == "name_story":
            # Depth: story/meaning behind the name — third clause usually explains symbolism
            depth = _nth_clause(fact, 2) if fact else ""
            return depth or "我的名字有一点意思，是家里人取的，有机会再跟你说。"
        # name_meaning: first clause (teaser)
        return _first_clause(fact) if fact else f"我叫{name}，这个名字是家人给取的，我觉得挺好的。"

    # ── Food ────────────────────────────────────────────────────────────────────
    if topic in ("food_fav", "food_local", "food_spicy"):
        fact = (facts.get("food") or "").strip()
        if topic == "food_local":
            depth = _nth_clause(fact, 1) if fact else ""
            return depth or "我家乡的菜也很有特色，有机会试试。"
        if fact:
            return _first_clause(fact)
        fav = profile.get("favourite_food") or ""
        return f"我最喜欢吃{fav}。" if fav else "我喜欢吃各种东西，很难只选一个。"

    # ── Place ────────────────────────────────────────────────────────────────────
    if topic in ("place_from", "place_like", "place_special"):
        fact = (facts.get("place") or "").strip()
        if topic == "place_special":
            depth = _nth_clause(fact, 1) if fact else ""
            return depth or "那里有一些很有意思的地方，有机会去看看。"
        if fact:
            return _first_clause(fact)
        city = profile.get("city") or profile.get("hometown") or ""
        return f"我是{city}人，从小在那里长大。" if city else "我觉得我住的地方挺好的。"

    # ── Travel ───────────────────────────────────────────────────────────────────
    if topic in ("travel_where", "travel_fav", "travel_memorable"):
        fact = (facts.get("travel") or "").strip()
        if topic == "travel_memorable":
            # Last clause often contains the memorable detail
            parts = re.split(r'[，、,]', fact)
            depth = parts[-1].strip().rstrip("。.") + "。" if parts and len(parts) > 1 else ""
            return depth or "最难忘的是在一个很偏远的地方看星星那一晚。"
        if fact:
            return _first_clause(fact)
        return "我去过几个城市，最喜欢有美食的地方。"

    # ── Work ─────────────────────────────────────────────────────────────────────
    if topic in ("work_what", "work_like", "work_duration", "work_platform"):
        fact = (facts.get("work") or "").strip()
        if topic == "work_duration":
            depth = _nth_clause(fact, 0) if fact else ""   # first clause often has duration
            return depth or "已经做了几年了，越做越有意思。"
        if topic == "work_platform":
            depth = _nth_clause(fact, 1) if fact else ""   # second clause often has platform
            return depth or "我在网上分享，有一些人关注。"
        if fact:
            return _first_clause(fact)
        job = profile.get("occupation") or ""
        return f"我做{job}，还挺有意思的。" if job else "我的工作挺有意思，可以学很多东西。"

    # ── Family ───────────────────────────────────────────────────────────────────
    if topic in ("family_size", "family_siblings", "family_live"):
        fact = (facts.get("family") or "").strip()
        if topic == "family_live":
            depth = _nth_clause(fact, 1) if fact else ""
            return depth or "我们不住在一起，但经常联系。"
        if fact:
            return _first_clause(fact)
        return "我家里有几口人，大家关系都挺好的。"

    # ── Hobby ────────────────────────────────────────────────────────────────────
    if topic in ("hobby_what", "hobby_duration"):
        fact = (facts.get("hobby") or "").strip()
        if topic == "hobby_duration":
            depth = _nth_clause(fact, 1) if fact else ""
            return depth or "已经玩了好几年了，越来越喜欢。"
        if fact:
            return _first_clause(fact)
        interests = profile.get("interests") or []
        if interests:
            return f"我喜欢{interests[0]}，有空就去。"
        return "我有几个爱好，平时很忙，但一有时间就会去做。"

    return "我觉得都挺有意思的。"


def _find_mirror_answer(text: str, engine_id: str, persona: Optional[dict]) -> Optional[str]:
    """
    Check if the user's submitted text closely matches one of the mirror discovery questions.
    If so, return a rich persona-specific answer via _mirror_persona_stub.
    Falls through to None so callers can chain with _direct_persona_answer.
    """
    t_norm = (text or "").strip().rstrip("？?！!。，, ")
    for eng, questions in _MIRROR_QUESTIONS_BY_ENGINE.items():
        for q in questions:
            zh_norm = (q.get("zh") or "").rstrip("？?！!。，, ")
            if not zh_norm:
                continue
            # Match if submitted text contains or equals the canonical question
            if zh_norm in t_norm or t_norm == zh_norm:
                topic = q.get("topic") or ""
                return _mirror_persona_stub(topic, eng or engine_id, persona)

    # Fuzzy-match common paraphrase variants that canonical substring check misses
    _fuzzy: list = [
        # name meaning variants: 是什么意思 vs 有什么意思 vs 啥意思
        (("你的名字", "意思"), "name_meaning", "identity"),
        (("名字", "意思"),     "name_meaning", "identity"),
        # name story variants
        (("名字", "故事"),     "name_story",   "identity"),
        (("名字", "来历"),     "name_story",   "identity"),
        (("名字", "怎么取"),   "name_story",   "identity"),
        # food
        (("你", "吃", "什么"), "food_fav",     "food"),
        (("你", "喜欢吃"),     "food_fav",     "food"),
        # place
        (("你", "哪里人"),     "place_from",   "place"),
        (("你", "从哪"),       "place_from",   "place"),
        # work
        (("你", "工作"),         "work_what",        "work"),
        (("做", "多久"),         "work_duration",    "work"),
        (("做了多久"),           "work_duration",    "work"),
        (("多久了"),             "work_duration",    "work"),
        (("哪里", "分享"),       "work_platform",    "work"),
        (("哪个", "平台"),       "work_platform",    "work"),
        # travel depth
        (("最难忘",),            "travel_memorable", "travel"),
        (("难忘", "旅行"),       "travel_memorable", "travel"),
        # place depth
        (("那里", "特别"),       "place_special",    "place"),
        (("有什么特色"),         "place_special",    "place"),
        # food local
        (("家乡", "好吃"),       "food_local",       "food"),
        (("家乡", "吃"),         "food_local",       "food"),
        # family together
        (("住在一起"),           "family_live",      "family"),
        (("一起住"),             "family_live",      "family"),
        # hobby duration
        (("多久", "爱好"),       "hobby_duration",   "hobby"),
        (("玩", "多久"),         "hobby_duration",   "hobby"),
        # hobby
        (("你", "爱好"),         "hobby_what",       "hobby"),
        (("你", "喜欢做"),       "hobby_what",       "hobby"),
    ]
    for keywords, topic, eng in _fuzzy:
        if all(kw in t_norm for kw in keywords):
            return _mirror_persona_stub(topic, eng, persona)

    return None


def _direction_stub(intent: str, engine_id: str, last_partner_frame_id: str, persona: Optional[dict]) -> str:
    """Short partner stub for direction actions (reverse/why), then client resumes thread."""
    eng = (engine_id or "").strip().lower()
    fid = (last_partner_frame_id or "").strip()
    if intent == "reverse":
        if eng == "identity":
            return f"我呢，我叫{_assistant_name_from_persona(persona)}。"
        if eng == "work":
            return "我呢，我挺喜欢我的工作。"
        if eng == "place":
            return "我呢，我觉得这里挺方便。"
        if eng == "family":
            return "我呢，我常跟家人联系。"
        return "我呢，也差不多。"
    if intent == "why":
        if fid in ("p2_wk_1",):
            return "因为我可以帮助别人。"
        if fid in ("p2_wk_2",):
            return "刚开始有点难。"
        if fid in ("p2_wk_3",):
            return "因为时间不够。"
        if fid in ("p2_wk_4",):
            return "还可以，比较稳定。"
        if fid in ("p2_wk_5",):
            return "推荐，可以学很多。"
        return "因为我觉得很有意思。"
    return "嗯。"


def _should_suppress_ask_frame(
    frame_id: str,
    memory: Optional[dict],
    recent_frame_ids: list,
    interval_turns: int,
    *,
    drill_mode: bool = False,
) -> bool:
    """
    Phase 10 Step 5: suppress a frame that asks for fact F when we already have F (keep conversation going).
    Returns True = suppress (do not choose this frame).
    If drill_mode is True, do not suppress (allows re-asking for practice); for future use.
    """
    if drill_mode or not memory or not _get_memory_field_for_frame:
        return False
    field = _get_memory_field_for_frame(frame_id)
    if not field:
        return False
    # Suppress when we already have this fact (no re-ask in normal conversation)
    return bool((memory.get(field) or "").strip())


def _has_learner_name(memory: Optional[dict]) -> bool:
    if not memory or not isinstance(memory, dict):
        return False
    return bool((memory.get("learner_name") or "").strip())


def _is_greeting_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    # Keep simple + conservative; treat very short greetings as greeting turns.
    greetings = {"你好", "您好", "嗨", "哈喽", "哈囉", "hi", "hello", "hey"}
    if t.lower() in greetings:
        return True
    if len(t) <= 4 and any(g in t for g in ("你好", "您好", "嗨", "哈喽", "哈囉")):
        return True
    return False


def _is_greeting_answer(last_answer: Optional[dict]) -> bool:
    if not last_answer or not isinstance(last_answer, dict):
        return False
    # Any answer to the opening greeting frame counts as a greeting exchange
    if (last_answer.get("frame_id") or "").strip() == "frame.greeting.hello":
        return True
    text = (last_answer.get("submitted_text") or "").strip()
    if not text:
        text = (last_answer.get("selected_option_hanzi") or "").strip()
    return _is_greeting_text(text)


def _select_next_frame_bridge(
    current_engine: str,
    recent_frame_ids: list,
    use_recovery_order: bool = False,
    memory: Optional[dict] = None,
    exchange_count: int = 0,
    engines_visited: Optional[list] = None,
) -> Optional[str]:
    """
    Phase 9.2: bridge to another engine. Only used after MIN_TURNS_BEFORE_BRIDGE turns in current engine.
    Prefers partner-question frames so the next line is a question, not a reactive phrase.
    When use_recovery_order is True (e.g. after 我不懂 or Change topic), try engines in _RECOVERY_BRIDGE_ENGINE_ORDER
    so the next question is a more natural switch (place/identity/family) rather than jumping to food/travel.
    Phase 11.1: skips identity OPEN frames (e.g. f_ask_you_name) once session is established (exchange_count ≥ 2).
    Phase 12C: engines_visited (session-level list) — unvisited engines are tried before already-visited ones.
    """
    recent = set(recent_frame_ids or [])
    engine_norm = (current_engine or "").strip().lower()
    targets = (
        [e for e in _RECOVERY_BRIDGE_ENGINE_ORDER if (e or "").strip().lower() != engine_norm]
        if use_recovery_order
        else _BRIDGE_TARGETS.get(engine_norm) or []
    )
    # Reduce ping-pong: try engines we haven't visited recently first (so we don't jump A->B->A->B).
    recent_list = recent_frame_ids or []
    if recent_list and targets:
        last_index_by_engine = {}
        for i, fid in enumerate(recent_list):
            fr = _frames_by_id.get(fid) or {}
            eng = (fr.get("engine") or "").strip().lower()
            if eng:
                last_index_by_engine[eng] = i
        def _recent_rank(e):
            return last_index_by_engine.get((e or "").strip().lower(), -1)
        targets = sorted(targets, key=_recent_rank)  # least recently used first
    # Phase 12C: prefer engines not yet visited in this session (avoids returning to exhausted topics).
    # Split targets into unvisited-first, then already-visited, preserving LRU order within each group.
    if engines_visited:
        _visited_set = {(e or "").strip().lower() for e in engines_visited}
        _visited_set.discard(engine_norm)  # current engine is already excluded from targets
        targets = (
            [t for t in targets if (t or "").strip().lower() not in _visited_set]
            + [t for t in targets if (t or "").strip().lower() in _visited_set]
        )
    for target_engine in targets:
        target_norm = (target_engine or "").strip().lower()
        if target_norm == engine_norm:
            continue
        # "life" engine is all difficulty-3; keep it off-limits until the session is established
        if target_norm == "life" and exchange_count < MIN_TURNS_FOR_LIFE_ENGINE:
            continue
        # Prefer partner questions, then any frame in target engine
        candidates = _engine_partner_question_frame_ids(target_norm)
        if not candidates:
            candidates = _engine_frame_ids(target_norm)
        # Sort candidates by difficulty so the first unseen frame in this engine is also the simplest
        candidates = sorted(
            candidates,
            key=lambda fid: int((_frames_by_id.get(fid) or {}).get("difficulty") or 2)
        )
        for fid in candidates:
            if fid not in recent:
                if not _frame_deps_satisfied(fid, recent, recent_list):
                    continue
                if memory is not None and _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS):
                    continue
                # Phase 11.1: don't re-open with identity OPEN gambits once conversation is established
                if exchange_count >= 2 and fid in _IDENTITY_OPEN_FRAMES:
                    continue
                # Skip frames whose semantic equivalent was already shown in another engine
                _excl = _MUTUAL_EXCLUSION_FRAMES.get(fid) or set()
                if _excl & recent:
                    continue
                return fid
    return None


def _select_next_frame_ladder(
    current_engine: str,
    recent_frame_ids: list,
    memory: Optional[dict] = None,
    exchange_count: int = 0,
    engines_visited: Optional[list] = None,
) -> Optional[str]:
    """
    Phase 9.1/9.2: deterministic next-frame ladder.
    1. Same engine, excluding recent_frame_ids (no repeat yet).
    2. If all frames in this engine were already used, bridge to another engine (new topic) so we never repeat a question already asked.
    3. Same-engine repeat only if bridge failed (e.g. no other engines).
    4. Safe fallback so we never dead-end.
    Phase 11.1: exchange_count forwarded to bridge to enforce identity OPEN frame guard.
    Phase 12C: engines_visited forwarded to bridge so unvisited engines are preferred.
    """
    recent = set(recent_frame_ids or [])
    engine_norm = (current_engine or "").strip().lower()
    same_engine = _engine_partner_question_frame_ids(engine_norm)
    if not same_engine:
        same_engine = _engine_frame_ids(engine_norm)

    # Tier 1: same engine, exclude recent, and only offer frame if its "after" deps are satisfied
    recent_list = list(recent_frame_ids or [])
    def _deps_satisfied(fid: str) -> bool:
        return _frame_deps_satisfied(fid, recent, recent_list)
    def _not_suppressed(fid: str) -> bool:
        if memory is None:
            return True
        return not _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS)

    # Phase 11.1: exclude OPEN gambits (e.g. f_ask_you_name) once session is established
    _open_excl = _IDENTITY_OPEN_FRAMES if exchange_count >= 2 else frozenset()
    def _not_mutually_excluded(fid: str) -> bool:
        excluded_if_seen = _MUTUAL_EXCLUSION_FRAMES.get(fid) or set()
        return not (excluded_if_seen & recent)
    unseen_same = [
        fid for fid in same_engine
        if fid not in recent
        and fid not in _open_excl
        and _deps_satisfied(fid)
        and _not_suppressed(fid)
        and _not_mutually_excluded(fid)
    ]
    if unseen_same:
        # Prefer lower-difficulty frames so the conversation starts simple and naturally escalates.
        # Stable sort preserves _FRAME_ORDER ordering within the same difficulty tier.
        unseen_same = sorted(
            unseen_same,
            key=lambda fid: int((_frames_by_id.get(fid) or {}).get("difficulty") or 2)
        )
        return unseen_same[0]

    # Tier 2: all frames in this engine were already used — bridge to a new topic instead of repeating
    chosen = _select_next_frame_bridge(current_engine, recent_frame_ids, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited)
    if chosen:
        return chosen

    # Tier 2.5: bridge returned None (all engines exhausted) — pick *newest* question from a different engine so we never repeat the current topic and avoid looping back to the very first question (你是哪里人？)
    if recent_frame_ids:
        for fid in reversed(recent_frame_ids):
            if fid not in _frames_by_id:
                continue
            eng = (_frames_by_id[fid].get("engine") or "").strip().lower()
            if eng != engine_norm:
                return fid
        # fallback: newest in session (may be same engine if only one engine ever used)
        if recent_frame_ids[-1] in _frames_by_id:
            return recent_frame_ids[-1]

    # Tier 3: same engine, allow repeat only as last resort (e.g. no recent_frame_ids yet)
    if same_engine:
        return same_engine[0]

    # Tier 4: safe fallback
    if _frames_by_id:
        return min(_frames_by_id.keys())
    return None


def _select_next_frame_ladder_avoiding(
    current_engine: str,
    recent_frame_ids: list,
    *,
    avoid_frame_ids: set,
    memory: Optional[dict] = None,
    exchange_count: int = 0,
    engines_visited: Optional[list] = None,
) -> Optional[str]:
    """
    Like _select_next_frame_ladder, but will skip avoid_frame_ids when there is any non-avoided candidate available
    in the same engine. This is used to deprioritize known weak loop frames (e.g. p2_pl_1, p2_pl_3) without
    changing the overall selector order.
    Phase 11.1: exchange_count forwarded to bridge/ladder for identity OPEN frame guard.
    Phase 12C: engines_visited forwarded so bridge prefers unvisited engines.
    """
    avoid = avoid_frame_ids or set()
    recent = set(recent_frame_ids or [])
    engine_norm = (current_engine or "").strip().lower()
    same_engine = _engine_partner_question_frame_ids(engine_norm) or _engine_frame_ids(engine_norm)

    recent_list = list(recent_frame_ids or [])
    def _deps_satisfied(fid: str) -> bool:
        return _frame_deps_satisfied(fid, recent, recent_list)

    def _not_suppressed(fid: str) -> bool:
        if memory is None:
            return True
        return not _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS)

    # Phase 11.1: exclude OPEN gambits (e.g. f_ask_you_name) once session is established
    _open_excluded = _IDENTITY_OPEN_FRAMES if exchange_count >= 2 else frozenset()
    def _not_mutually_excluded_av(fid: str) -> bool:
        excl = _MUTUAL_EXCLUSION_FRAMES.get(fid) or set()
        return not (excl & recent)
    unseen = [
        fid for fid in same_engine
        if fid not in recent
        and fid not in _open_excluded
        and _deps_satisfied(fid)
        and _not_suppressed(fid)
        and _not_mutually_excluded_av(fid)
    ]
    if not unseen:
        return _select_next_frame_ladder(current_engine, recent_frame_ids, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited)

    # Prefer lower-difficulty frames (stable sort preserves FRAME_ORDER within same tier)
    def _diff(fid: str) -> int:
        return int((_frames_by_id.get(fid) or {}).get("difficulty") or 2)
    unseen = sorted(unseen, key=_diff)
    non_avoided = [fid for fid in unseen if fid not in avoid]
    if non_avoided:
        return non_avoided[0]

    # Only avoided candidates remain. For the highest-impact weak loop frames, prefer to bridge away
    # rather than forcing a low-quality loop.
    if engine_norm == "place" and avoid.issuperset({"p2_pl_1", "p2_pl_3"}):
        bridged = _select_next_frame_bridge(current_engine, recent_frame_ids, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited)
        if bridged and bridged not in recent:
            return bridged
    return unseen[0]


def _count_remaining_engine_frames(engine: str, recent_list: list, memory: Optional[dict]) -> int:
    """Phase 11.1: count unseen, dep-satisfied, non-suppressed partner frames in this engine."""
    engine_norm = (engine or "").strip().lower()
    recent_set = set(recent_list or [])
    frames = _engine_partner_question_frame_ids(engine_norm)
    if not frames:
        frames = _engine_frame_ids(engine_norm)
    return sum(
        1 for fid in frames
        if fid not in recent_set
        and _frame_deps_satisfied(fid, recent_set, recent_list or [])
        and (memory is None or not _should_suppress_ask_frame(fid, memory, recent_list or [], RECALL_INTERVAL_TURNS))
    )


def _frame_order_priority(
    engine: str,
    chosen_fid: str,
    recent_set: set,
    recent_list: list,
    memory: Optional[dict],
) -> Optional[str]:
    """
    Phase 11.1: soft FRAME_ORDER enforcement.
    If chosen_fid is later in FRAME_ORDER than some unseen, dep-satisfied frame, return that
    earlier frame instead. Returns None when chosen is already optimal or not in FRAME_ORDER.
    """
    order = _FRAME_ORDER.get((engine or "").strip().lower()) or []
    if not order or chosen_fid not in order:
        return None
    chosen_pos = order.index(chosen_fid)
    if chosen_pos == 0:
        return None
    for fid in order[:chosen_pos]:
        if fid in recent_set:
            continue
        if not _frame_deps_satisfied(fid, recent_set, recent_list):
            continue
        if memory and _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS):
            continue
        return fid
    return None


def _stub_card_id(frame_id: str):
    """Return card_id for the first word token in the frame, or None."""
    tokens = _frame_tokens.get(frame_id, [])
    for tok in tokens:
        if tok.get("kind") == "word" or tok.get("t") == "word":
            word_id = tok.get("word_id") or tok.get("id")
            card_id = _cards_by_word_id.get(word_id)
            print(f"[ui_server] _stub_card_id: frame={frame_id} word_id={word_id} card_id={card_id}")
            return card_id
    print(f"[ui_server] _stub_card_id: no word token found for frame={frame_id}")
    return None


# ── HTTP Handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        # Phase 11C: Persona endpoints
        if path == "/api/personas":
            data = json.dumps({"personas": _personas_index}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path.startswith("/api/personas/") and path.count("/") == 3:
            _pid = path.split("/")[-1].strip()
            _p = _resolve_persona(_pid)
            if _p:
                data = json.dumps(_p, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json_error(404, f"persona not found: {_pid}")
            return

        if path == "/api/cards":
            rel = qs.get("path", [None])[0]
            if not rel:
                self._json_error(400, "missing path param")
                return
            self._serve_file(REPO_ROOT / rel, path)
            return

        if path.startswith("/runtime/"):
            file_path = RUNTIME_DIR / path[len("/runtime/"):]
        elif path.startswith("/data/"):
            # Curated datasets at repo root data/ (e.g. characters_1200.json master copy)
            file_path = REPO_ROOT / path.lstrip("/")
        elif path.startswith("/ui/") or path in ("/ui", "/ui/index.html"):
            rel = path[len("/ui/"):] if path.startswith("/ui/") else "index.html"
            file_path = UI_DIR / rel
        elif path.endswith(".json") and "/" not in path.lstrip("/"):
            file_path = REPO_ROOT / path.lstrip("/")
        elif path == "/":
            self.send_response(302)
            self.send_header("Location", "/ui/index.html")
            self.end_headers()
            return
        else:
            file_path = UI_DIR / path.lstrip("/")

        self._serve_file(file_path, path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/api/reset_memory":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except Exception:
                payload = {}
            learner_id = (payload.get("learner_id") or "").strip()
            if learner_id and _lm_save:
                empty = {"learner_name": None, "hometown": None, "lives_in": None,
                         "job_or_study": None, "family": None, "favourite_food": None}
                _lm_save(learner_id, empty)
                print(f"[ui_server] /api/reset_memory: cleared memory for '{learner_id}'")
                result = {"ok": True, "learner_id": learner_id}
            else:
                result = {"ok": False, "error": "missing learner_id or memory module unavailable"}
            data = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/run_turn":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except Exception as e:
                print(f"[ui_server] bad request body: {e}")
                payload = {}

            print(f"[ui_server] /api/run_turn payload keys={list(payload.keys())}", flush=True)

            # Direction actions: learner asks back/why, partner gives short stub, then UI resumes thread.
            direction_intent = (payload.get("direction_intent") or "").strip().lower()
            if direction_intent in ("reverse", "why", "mirror"):
                cs = payload.get("conversation_state") or {}
                persona_id = (payload.get("persona_id") or cs.get("persona_id") or "").strip() or None
                persona = _resolve_persona(persona_id) or (_get_persona(persona_id) if _get_persona else None)
                engine_id = (cs.get("current_engine") or "unknown").strip()
                last_partner_frame_id = (cs.get("last_partner_frame_id") or "").strip()

                if direction_intent == "mirror":
                    # Learner asked a specific mirror question about the persona
                    topic = (payload.get("direction_question_topic") or "").strip()
                    stub  = _mirror_persona_stub(topic, engine_id, persona)
                else:
                    stub = _direction_stub(direction_intent, engine_id, last_partner_frame_id, persona)

                # Build mirror questions the learner can ask next (engine-specific)
                mirror_opts = list(_MIRROR_QUESTIONS_BY_ENGINE.get(engine_id, []))
                # Remove the one just asked (if any) to avoid immediate repetition
                asked_zh = (payload.get("direction_question_zh") or "").strip()
                if asked_zh:
                    mirror_opts = [m for m in mirror_opts if m.get("zh") != asked_zh]

                response = {
                    "turn_uid": payload.get("turn_uid", ""),
                    "engine_id": engine_id,
                    "frame_id": "direction_response",
                    "frame_text": stub,
                    "frame_pinyin": "",
                    "frame_text_en": "",
                    "result": "ok",
                    "options": [],
                    "option_count": 0,
                    "is_direction_response": True,
                    "thread_return": "resume_question",
                    "mirror_options": mirror_opts,
                }
                data = json.dumps(response, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            # Oxygen loop: user asked a probe (为什么？, 谁？, etc.) — return stub partner response (persona-consistent when available)
            probe_id = (payload.get("probe_id") or "").strip()
            if probe_id:
                cs = payload.get("conversation_state") or {}
                persona_id = (payload.get("persona_id") or cs.get("persona_id") or "").strip() or None
                persona = _resolve_persona(persona_id) or (_get_persona(persona_id) if _get_persona else None)
                stub = _probe_stub_for_persona(probe_id, persona)
                probe_hanzi = payload.get("probe_hanzi") or stub
                response = {
                    "turn_uid":       payload.get("turn_uid", ""),
                    "engine_id":      (payload.get("conversation_state") or {}).get("current_engine", "unknown"),
                    "frame_id":       "probe_response",
                    "frame_text":     stub,
                    "frame_pinyin":   "",
                    "frame_text_en":  "",
                    "result":         "ok",
                    "options":        [],
                    "option_count":   0,
                    "is_probe_response": True,
                }
                data = json.dumps(response, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            # Reload frames from disk so frame_text_en is always current (e.g. after populate_frame_text_en.py)
            _frames_by_id.clear()
            _frames_by_id.update(_reload_frames_by_id())

            # Phase 10 Step 7: response extras for cross-session continuity (learner_memory, persona_id, turn_type)
            _phase10_learner_memory = None
            _phase10_persona_id = None
            _phase10_turn_type = None
            # Phase 10.5 behaviour debug/telemetry (optional response fields; UI can ignore)
            reaction_prefix_text = ""
            reaction_used_fallback = False
            bridge_prefix_text = ""
            loop_attempted = False
            chosen_turn_type = "question"
            new_memory_written = False
            memory = None  # loaded in next_question path; used for slot substitution
            interest_score = 0
            interest_level = "low"
            pending_listening_move = False
            listening_wait_turns = 0
            listening_move_selected = "none"
            listening_move_reason = ""
            same_engine_chain_count = 0
            same_slot_chain_count = 0
            last_focus_slot = ""
            last_user_text = ""
            last_interest_level = "low"

            # Phase 9.1/9.2: next_question + conversation_state → selector; prefer_bridge/force_bridge try bridge first
            if payload.get("next_question") and isinstance(payload.get("conversation_state"), dict):
                cs = payload["conversation_state"]
                current_engine = cs.get("current_engine")
                recent = cs.get("recent_frame_ids") or []
                prefer_bridge = cs.get("prefer_bridge") is True
                force_bridge = cs.get("force_bridge") is True
                # Phase 10.5 behaviour state (client-maintained lightweight counters)
                curiosity_depth = int(cs.get("curiosity_depth") or 0)
                exchange_count = int(cs.get("exchange_count") or 0)
                ask_chain_count = int(cs.get("ask_chain_count") or 0)
                same_engine_chain_count = int(cs.get("same_engine_chain_count") or 0)
                same_slot_chain_count = int(cs.get("same_slot_chain_count") or 0)
                last_focus_slot = (cs.get("last_focus_slot") or "").strip()
                pending_listening_move = cs.get("pending_listening_move") is True
                listening_wait_turns = int(cs.get("listening_wait_turns") or 0)
                last_interest_level = (cs.get("last_interest_level") or "low").strip()
                # Phase 12C: session arc state (additive — falls back to 0/[] when absent)
                loop_count_in_engine   = int(cs.get("loop_count_in_current_engine") or 0)
                engines_visited        = list(cs.get("engines_visited") or [])
                recent_confusion_count = int(cs.get("recent_confusion_count") or 0)
                # Arc flags — computed once, reused in soft bias pass
                _12c_loop_capped = loop_count_in_engine >= LOOP_COUNT_IN_ENGINE_SOFT_CAP
                _12c_overload    = recent_confusion_count >= OVERLOAD_CONFUSION_THRESHOLD
                _12c_closing     = exchange_count >= CLOSURE_EXCHANGE_THRESHOLD
                _transition_reason = "normal"

                # Phase 10: after a response turn, capture facts and persist by learner_id
                learner_id = (cs.get("learner_id") or "").strip() or None
                last_answer = cs.get("last_answer") if isinstance(cs.get("last_answer"), dict) else None
                memory = _lm_load(learner_id) if (_lm_load and learner_id) else None
                if _capture_from_turn and _lm_load and _lm_save and _lm_apply_updates and learner_id and last_answer:
                    fid = (last_answer.get("frame_id") or "").strip()
                    if fid:
                        updates = _capture_from_turn(
                            fid,
                            selected_option_hanzi=last_answer.get("selected_option_hanzi"),
                            selected_option_meaning=last_answer.get("selected_option_meaning"),
                            submitted_text=last_answer.get("submitted_text"),
                        )
                        if updates:
                            new_memory_written = True
                            memory = memory or _lm_load(learner_id)
                            memory = _lm_apply_updates(memory, updates)
                            _lm_save(learner_id, memory)

                # Phase 10.5: reaction micro-layer + loop/ask decision (keep selector order as specified)
                last_turn_was_answer = cs.get("last_turn_was_answer") is True
                slot_names = _infer_slot_names_from_answer(last_answer) if last_turn_was_answer else []
                meaningful = bool(slot_names) or bool(new_memory_written)
                user_asked_question = _is_user_question(last_answer) if last_turn_was_answer else False
                last_partner_was_loop = cs.get("last_partner_turn_type") == "loop_question"
                last_partner_had_reaction = cs.get("last_partner_had_reaction") is True
                last_answer_fid = (last_answer.get("frame_id") or "").strip() if last_turn_was_answer and isinstance(last_answer, dict) else ""
                answer_text = _answer_text_from_last_answer(last_answer) if last_turn_was_answer else ""
                force_food_followup = last_turn_was_answer and (not user_asked_question) and (
                    last_answer_fid == "p2_pl_2" or _looks_food_related_answer(answer_text)
                )
                if force_food_followup and "DISH" not in slot_names:
                    slot_names = ["DISH"] + slot_names
                    meaningful = True
                unscripted_probe_first = last_turn_was_answer and (not user_asked_question) and _is_unscripted_substantive_answer(last_answer, slot_names)
                weak_reply = last_turn_was_answer and len(answer_text) <= 2
                interest_score = 0
                interest_level = "low"
                if last_turn_was_answer:
                    interest_score = _score_answer_interest(last_answer, slot_names, new_memory_written, cs)
                    interest_level = _classify_interest(interest_score)
                    # One-turn resilience: if previous turn was interesting but this answer is short,
                    # try one more curiosity move before exiting the topic.
                    if weak_reply and (last_interest_level in ("medium", "high")) and interest_level == "low":
                        interest_level = "medium"
                        interest_score = max(interest_score, INTEREST_MEDIUM_THRESHOLD)
                    last_interest_level = interest_level
                    if interest_level in ("medium", "high") and (not user_asked_question):
                        pending_listening_move = True
                        listening_wait_turns = 0

                # Reaction micro-layer: we cannot emit two separate partner turns without changing API.
                # So when reaction triggers, we optionally prepend a short reaction phrase to the next question's text.
                reaction_prefix_text = ""
                reaction_used_fallback = False
                # Spec §3: after ANY user answer, bias to reaction (not only when "meaningful").
                if last_turn_was_answer:
                    # Vary with session+turn so we don't overuse generic fallbacks
                    seed = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}"
                    # Prefer reaction frame if available, else topic-specific fallback text
                    if _stable_pick([1], seed) is not None:  # cheap deterministic gate: use probability via hash below
                        # Implement probability gate using stable hash (no random module required)
                        gate = 0
                        for ch in seed:
                            gate = (gate * 131 + ord(ch)) % 1000
                        if gate < int(P_REACTION_AFTER_MEANINGFUL * 1000):
                            rid = _pick_reaction_frame_id(current_engine)
                            if rid:
                                # Avoid repeating "nice to meet you" beyond the very start; it feels interrogative.
                                if (current_engine or "").strip().lower() == "identity" and exchange_count >= 1 and rid == "f_nice_to_meet":
                                    reaction_prefix_text = _pick_reaction_text(current_engine, seed, interest_level=interest_level, exchange_count=exchange_count)
                                    reaction_used_fallback = True
                                else:
                                    reaction_prefix_text = (_frames_by_id.get(rid) or {}).get("text") or ""
                            else:
                                reaction_prefix_text = _pick_reaction_text(current_engine, seed, interest_level=interest_level, exchange_count=exchange_count)
                                reaction_used_fallback = True

                # Phase 12C: echo / mirror — when we know the slot value, replace the generic
                # reaction with a short echo so the app sounds like it truly heard the answer.
                # Fires when: (a) the reaction is generic fallback text, OR (b) the reaction
                # text is short/generic (≤4 Chinese chars like "很好！" "哦。") — those are
                # bland acknowledgements that benefit from being replaced by a named echo.
                _zh_chars_in_reaction = len([c for c in (reaction_prefix_text or "") if "\u4e00" <= c <= "\u9fff"])
                _reaction_is_generic = reaction_used_fallback or _zh_chars_in_reaction <= 4
                if last_turn_was_answer and _reaction_is_generic and reaction_prefix_text:
                    _echo_candidate = ""
                    _submitted_raw = (last_answer.get("submitted_text") or "").strip() if isinstance(last_answer, dict) else ""
                    # Strip ALL trailing punctuation (fullwidth and ASCII) so echo never ends with "。！" or "，！"
                    _submitted = _submitted_raw.rstrip("。，！？、…·\u3002\uff0c\uff01\uff1f.!?, ")
                    _mem = memory or {}
                    if "CITY" in slot_names:
                        _city = (_mem.get("lives_in") or _mem.get("hometown") or "").strip()
                        if not _city and _submitted:
                            # Extract city from "我是X人" / "来自X" / "住在X" patterns
                            for _patt_start, _patt_end in [("是", "人"), ("来自", ""), ("住在", "")]:
                                _ps = _submitted.find(_patt_start)
                                if _ps >= 0:
                                    _frag = _submitted[_ps + len(_patt_start):]
                                    if _patt_end:
                                        _pe = _frag.find(_patt_end)
                                        if 0 < _pe <= 6:
                                            _city = _frag[:_pe]
                                            break
                                    elif _frag and len(_frag) <= 6:
                                        _city = _frag.rstrip("。，！？")
                                        break
                        if _city:
                            _echo_candidate = f"哦，{_city}！"
                    elif "NAME" in slot_names and exchange_count <= 3:
                        _name = (_mem.get("learner_name") or "").strip()
                        if _name and len(_name) <= 6:
                            _echo_candidate = f"{_name}！"
                    elif "DISH" in slot_names and _submitted and len(_submitted) <= 8:
                        _echo_candidate = f"哦，{_submitted}！"
                    elif "TRAVEL" in slot_names and _submitted and len(_submitted) <= 8:
                        _echo_candidate = f"哦，{_submitted}！"
                    elif "JOB" in slot_names:
                        _job = (_mem.get("job") or _mem.get("occupation") or "").strip()
                        if _job and len(_job) <= 6:
                            _echo_candidate = f"哦，{_job}！"
                    # Apply echo only when we have a clean value (not too long, not already prefixed)
                    # Final guard: strip any punct that crept into the candidate from slot values
                    if _echo_candidate:
                        _echo_candidate = _echo_candidate.rstrip("。，！？.!?,\u3002\uff0c\uff01\uff1f") + "！"
                    if _echo_candidate and len(_echo_candidate) <= 14:
                        reaction_prefix_text = _echo_candidate

                # User-question override (spec-friendly, no schema changes):
                # if the user asked a question (counter-question), return the persona's answer
                # as a dedicated `counter_reply` field so the client can display/TTS it
                # separately — much more reliable than concatenating into reaction_prefix_text
                # where bridge resets or ordering issues can silently drop it.
                persona_id = (payload.get("persona_id") or cs.get("persona_id") or "").strip() or None
                persona = _resolve_persona(persona_id) or (_get_persona(persona_id) if _get_persona else None)
                _counter_reply = _answer_user_question_prefix(last_answer, persona) if last_turn_was_answer else None
                # DEBUG — remove after diagnosis
                _dbg_la = last_answer or {}
                print(f"[DBG counter_reply] lta={last_turn_was_answer} is_q={_is_user_question(last_answer)} "
                      f"submitted={_dbg_la.get('submitted_text','')!r} "
                      f"hanzi={_dbg_la.get('selected_option_hanzi','')!r} "
                      f"-> counter_reply={_counter_reply!r}", flush=True)

                # Partner curiosity: prefer loop when triggered and depth allows, but avoid weak loop frames if possible
                chosen = None
                chosen_turn_type = "question"
                loop_attempted = False
                listening_move_selected = "none"
                listening_move_reason = ""
                if force_food_followup:
                    chosen = _pick_slot_followup_frame_id(current_engine, ["DISH"], recent, memory, exchange_count=exchange_count)
                    if chosen:
                        chosen = _frame_order_priority(current_engine, chosen, set(recent), recent, memory) or chosen
                        chosen_turn_type = "loop_question" if _is_loop_candidate(chosen) else "question"
                        listening_move_selected = "loop_question" if chosen_turn_type == "loop_question" else "question"
                        listening_move_reason = "food_followup_priority"
                        pending_listening_move = False
                        listening_wait_turns = 0
                # Generic probe-first: when unscripted answer sounds substantive, try one same-topic probe
                # before bridging away. If it misses, normal bridge logic still runs next.
                if chosen is None and unscripted_probe_first:
                    chosen = _select_next_frame_ladder_avoiding(
                        current_engine,
                        recent,
                        avoid_frame_ids=_WEAK_LOOP_FRAME_IDS,
                        memory=memory,
                        exchange_count=exchange_count,
                        engines_visited=engines_visited,
                    )
                    if chosen:
                        chosen_turn_type = "loop_question" if _is_loop_candidate(chosen) else "question"
                        listening_move_selected = "loop_question" if chosen_turn_type == "loop_question" else "question"
                        listening_move_reason = "unscripted_probe_first"
                        pending_listening_move = False
                        listening_wait_turns = 0
                if chosen is None and last_turn_was_answer and (not user_asked_question):
                    force_listening = _should_force_listening_move(cs, interest_level)
                    chain_exceeded = _topic_chain_exceeded(cs, slot_names)
                    # Resilience override: after a short reply that follows a recent interesting turn,
                    # allow one more same-topic probe before chain-cap forces a bridge.
                    if weak_reply and (last_interest_level in ("medium", "high")):
                        chain_exceeded = False
                    # Phase 11.1: depth guard — block bridge if fresh frames remain and depth is shallow
                    _remaining_in_engine = _count_remaining_engine_frames(current_engine, recent, memory)
                    _depth_guard_blocks = (
                        same_engine_chain_count < ENGINE_DEPTH_GUARD_TURNS
                        and _remaining_in_engine >= ENGINE_DEPTH_GUARD_MIN_REMAINING
                    )
                    bridge_allowed = (
                        force_bridge
                        or prefer_bridge
                        or (
                            same_engine_chain_count >= MIN_SAME_ENGINE_CHAIN_BEFORE_BRIDGE
                            and not _depth_guard_blocks
                        )
                    )
                    if pending_listening_move or force_listening or chain_exceeded:
                        seed_base = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}/interest"
                        gate_br = _stable_gate(seed_base + "/br")
                        p_br = P_BRIDGE_WHEN_INTEREST_HIGH if interest_level == "high" else 0.35
                        # Curiosity-first policy: whenever we have meaningful/unscripted signal and depth allows,
                        # attempt a same-topic probe BEFORE considering bridge.
                        has_curiosity_signal = bool(slot_names) or bool(unscripted_probe_first) or bool(meaningful)
                        if curiosity_depth < MAX_CURIOSITY_DEPTH and has_curiosity_signal:
                            chosen = _pick_slot_followup_frame_id(current_engine, slot_names, recent, memory, exchange_count=exchange_count)
                            if chosen is not None:
                                chosen = _frame_order_priority(current_engine, chosen, set(recent), recent, memory) or chosen
                            if chosen is None:
                                chosen = _select_next_frame_ladder_avoiding(
                                    current_engine,
                                    recent,
                                    avoid_frame_ids=_WEAK_LOOP_FRAME_IDS,
                                    memory=memory,
                                    exchange_count=exchange_count,
                                    engines_visited=engines_visited,
                                )
                            if chosen and _is_loop_candidate(chosen):
                                chosen_turn_type = "loop_question"
                                curiosity_depth = min(curiosity_depth + 1, MAX_CURIOSITY_DEPTH)
                                listening_move_selected = "loop_question"
                                listening_move_reason = "interest_policy"
                                pending_listening_move = False
                                listening_wait_turns = 0
                        # Only default to bridge when curiosity had no viable frame.
                        if chosen is None and bridge_allowed and (force_listening or chain_exceeded or gate_br < int(p_br * 1000)):
                            chosen = _select_next_frame_bridge(current_engine, recent, use_recovery_order=prefer_bridge, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited)
                            if chosen:
                                chosen_turn_type = "question"
                                listening_move_selected = "bridge"
                                listening_move_reason = "interest_policy_or_chain_cap"
                                pending_listening_move = False
                                listening_wait_turns = 0
                        if chosen is None and pending_listening_move:
                            listening_wait_turns += 1
                # If user asked a question, do NOT attempt loop-questioning; keep flow simple and reciprocal.
                if chosen is None and last_turn_was_answer and (not user_asked_question) and meaningful and curiosity_depth < MAX_CURIOSITY_DEPTH:
                    # stable probability gate for loop
                    seed = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}/loop"
                    gate = 0
                    for ch in seed:
                        gate = (gate * 131 + ord(ch)) % 1000
                    if gate < int(P_LOOP_WHEN_TRIGGERED * 1000):
                        loop_attempted = True
                        # Prefer slot/topic follow-up first (often loop-like), then fall back to engine ladder
                        chosen = _pick_slot_followup_frame_id(current_engine, slot_names, recent, memory, exchange_count=exchange_count)
                        if chosen is not None:
                            chosen = _frame_order_priority(current_engine, chosen, set(recent), recent, memory) or chosen
                        if chosen is None:
                            # Fall back: next ladder frame, but avoid known weak loop frames if we have alternatives in engine
                            chosen = _select_next_frame_ladder_avoiding(
                                current_engine,
                                recent,
                                avoid_frame_ids=_WEAK_LOOP_FRAME_IDS,
                                memory=memory,
                                exchange_count=exchange_count,
                                engines_visited=engines_visited,
                            )
                        if chosen and _is_loop_candidate(chosen):
                            chosen_turn_type = "loop_question"
                            pending_listening_move = False
                            listening_wait_turns = 0
                # Depth cap enforcement: if reached, force next ask/bridge and reset depth
                if chosen is None:
                    if curiosity_depth >= MAX_CURIOSITY_DEPTH:
                        # Force ask/bridge; reset depth
                        if prefer_bridge or force_bridge:
                            chosen = _select_next_frame_bridge(current_engine, recent, use_recovery_order=prefer_bridge, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited)
                        if chosen is None and not force_bridge:
                            chosen = _select_next_frame_ladder(current_engine, recent, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited)
                        curiosity_depth = 0
                        chosen_turn_type = "question"
                    else:
                        # Soft chaining: slot/topic preference first, then existing bridge/ladder order
                        if last_turn_was_answer and (not user_asked_question) and meaningful:
                            chosen = _pick_slot_followup_frame_id(current_engine, slot_names, recent, memory, exchange_count=exchange_count)
                            if chosen is not None:
                                chosen = _frame_order_priority(current_engine, chosen, set(recent), recent, memory) or chosen
                            if chosen and _is_loop_candidate(chosen):
                                chosen_turn_type = "loop_question"
                                curiosity_depth = min(curiosity_depth + 1, MAX_CURIOSITY_DEPTH)
                                pending_listening_move = False
                                listening_wait_turns = 0
                        if chosen is None:
                            if prefer_bridge or force_bridge:
                                chosen = _select_next_frame_bridge(current_engine, recent, use_recovery_order=prefer_bridge, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited)
                                if chosen:
                                    pending_listening_move = False
                                    listening_wait_turns = 0
                            if chosen is None and not force_bridge:
                                chosen = _select_next_frame_ladder_avoiding(
                                    current_engine,
                                    recent,
                                    avoid_frame_ids=_WEAK_LOOP_FRAME_IDS,
                                    memory=memory,
                                    exchange_count=exchange_count,
                                    engines_visited=engines_visited,
                                )

                # [DEBUG] trace the selection result for rapid-bridge diagnosis
                _dbg_submitted = (last_answer.get("submitted_text") or "") if isinstance(last_answer, dict) else ""
                print(f"[SEL] engine={current_engine} chain={same_engine_chain_count} chosen={chosen} "
                      f"ex={exchange_count} pref_br={prefer_bridge} unscripted={unscripted_probe_first} "
                      f"meaningful={meaningful} submitted={repr(_dbg_submitted[:20])}", flush=True)

                if not chosen:
                    self._json_error(400, "no frame available for next question")
                    return

                # Hard guarantee: if this turn classified as medium/high interest but no explicit
                # listening move was selected, force a probe attempt on the very next turn.
                if interest_level in ("medium", "high") and listening_move_selected == "none":
                    pending_listening_move = True
                    listening_wait_turns = max(int(listening_wait_turns or 0), INTEREST_FORCE_WINDOW_TURNS)

                # Identity coherence gate: don't ask name-meta questions unless "name" is established.
                # This prevents post-greeting jumps like “你觉得你的名字怎么样？” with no context.
                engine_norm = (current_engine or "").strip().lower()
                if engine_norm == "identity":
                    # Greeting reset: after greeting exchange, establish name context before deeper questions.
                    if last_turn_was_answer and _is_greeting_answer(last_answer):
                        if not _has_learner_name(memory):
                            # First-time learner: ask name first
                            chosen = "f_ask_you_name"
                            chosen_turn_type = "question"
                        elif chosen in {"p2_id_ext1", "p2_id_4", "p2_id_5", "f_ask_name_meaning"}:
                            # Returning learner: name known but jumped too deep — use gentler p2_id_2 opener
                            _grt_recent_eff = set(recent or []) | {"f_ask_you_name"}
                            _grt_candidate = "p2_id_2"
                            if _grt_candidate not in set(recent or []) and _frame_deps_satisfied(_grt_candidate, _grt_recent_eff, list(recent or [])):
                                chosen = _grt_candidate
                                chosen_turn_type = "question"
                    else:
                        name_meta_frames = {"p2_id_4", "p2_id_5", "f_ask_name_meaning", "p2_id_2", "p2_id_ext1", "f_name_story_elicit"}
                        # In-session name context: user just answered a name-related question
                        has_name_context_now = ("NAME" in (slot_names or []))
                        has_name_in_memory = _has_learner_name(memory)
                        if chosen in name_meta_frames and (not has_name_context_now) and (not has_name_in_memory):
                            # Phase 11.1: once session is established, don't re-ask the opening name question.
                            # For early turns (exchange < 2) we still force f_ask_you_name; for established sessions bridge away.
                            if exchange_count >= 2:
                                bridged = _select_next_frame_bridge(current_engine, recent, use_recovery_order=True, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited)
                                if bridged:
                                    chosen = bridged
                                    chosen_turn_type = "question"
                            else:
                                # Force the basic name question first (unless suppressed for some reason)
                                fallback = "f_ask_you_name"
                                if fallback not in set(recent or []) and not _should_suppress_ask_frame(fallback, memory, recent or [], RECALL_INTERVAL_TURNS):
                                    chosen = fallback
                                    chosen_turn_type = "question"
                                else:
                                    # If we can't ask name, switch topic to avoid awkward interrogation
                                    bridged = _select_next_frame_bridge(current_engine, recent, use_recovery_order=True, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited)
                                    if bridged:
                                        chosen = bridged
                                        chosen_turn_type = "question"

                # Phase 10.7: optional declarative move_type filter (additive, safe fallback).
                # Runs AFTER all Phase 10.5 logic and identity coherence gate.
                # Only changes `chosen` when a tagged alternative in the allowed transition set exists.
                _mt_filter_debug: dict = {}
                if last_answer_fid and chosen:
                    _engine_for_filter = (current_engine or "").strip().lower()
                    _mt_filter_debug = _apply_move_type_filter(
                        chosen=chosen,
                        last_frame_id=last_answer_fid,
                        engine_norm=_engine_for_filter,
                        recent=list(recent or []),
                        memory=memory,
                        exchange_count=exchange_count,
                        same_engine_chain_count=same_engine_chain_count,
                    )
                    _fc = _mt_filter_debug.get("filtered_chosen")
                    if _fc and _fc != chosen:
                        # Guard: if unscripted_probe_first selected a same-engine follow-up,
                        # don't let the move_type filter pull us into a different engine.
                        # The probe intent must be respected — cross-engine override defeats it.
                        _fc_engine = (_frames_by_id.get(_fc) or {}).get("engine") or ""
                        _orig_engine = (_frames_by_id.get(chosen) or {}).get("engine") or current_engine
                        _cross_engine = bool(
                            _fc_engine and _orig_engine
                            and _fc_engine.strip().lower() != _orig_engine.strip().lower()
                        )
                        if unscripted_probe_first and _cross_engine:
                            pass  # keep the same-engine probe — filter cannot override a probe intent
                        else:
                            chosen = _fc
                        # Note: chosen_turn_type intentionally kept from 10.5 logic; filter is structural only.

                # ── Phase 12C: soft session arc bias pass ─────────────────────────────
                # Runs AFTER all Phase 10.5 / 10.7 selection. Adjusts candidate only
                # when a safe alternative is available; always falls back gracefully.
                if chosen:
                    _chosen_is_loop = _is_loop_candidate(chosen) or chosen_turn_type == "loop_question"

                    # 1. Loop cap — partner asked ≥ LOOP_COUNT_IN_ENGINE_SOFT_CAP LOOPs
                    #    in this engine; try a non-LOOP frame or bridge.
                    if _chosen_is_loop and _12c_loop_capped and not user_asked_question:
                        _arc_alt = _select_next_frame_ladder_avoiding(
                            current_engine, recent,
                            avoid_frame_ids=_WEAK_LOOP_FRAME_IDS,
                            memory=memory, exchange_count=exchange_count,
                            engines_visited=engines_visited,
                        )
                        if _arc_alt and not _is_loop_candidate(_arc_alt):
                            chosen = _arc_alt
                            chosen_turn_type = "question"
                            _transition_reason = "loop_limit"
                        else:
                            _arc_br = _select_next_frame_bridge(
                                current_engine, recent, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited
                            )
                            if _arc_br:
                                chosen = _arc_br
                                chosen_turn_type = "question"
                                _transition_reason = "loop_limit_bridge"

                    # 2. Overload — user confused ≥ OVERLOAD_CONFUSION_THRESHOLD times;
                    #    don't loop further, prefer bridge to lighter material.
                    if _12c_overload and _is_loop_candidate(chosen) and not user_asked_question:
                        _arc_br = _select_next_frame_bridge(
                            current_engine, recent, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited
                        )
                        if _arc_br:
                            chosen = _arc_br
                            chosen_turn_type = "question"
                            _transition_reason = "overload"

                    # 3. Closure — session is long (≥ CLOSURE_EXCHANGE_THRESHOLD);
                    #    probabilistically push toward a new engine ONLY when the current engine
                    #    is sufficiently explored (depth guard) or nearly exhausted.
                    #    Guard: never force a bridge mid-turn when the user just asked us a question —
                    #    the persona should answer first, then continue naturally.
                    if _12c_closing and _transition_reason == "normal" and not user_asked_question:
                        _closure_frame_engine = (_frames_by_id.get(chosen) or {}).get("engine") or current_engine
                        _still_in_engine = (
                            (_closure_frame_engine or "").strip().lower()
                            == (current_engine or "").strip().lower()
                        )
                        _remaining_now = _count_remaining_engine_frames(current_engine, list(recent), memory)
                        # Only push out if we've had enough turns in this engine OR it's nearly empty
                        _close_ready = (
                            _still_in_engine
                            and (
                                same_engine_chain_count >= ENGINE_DEPTH_GUARD_TURNS
                                or _remaining_now < ENGINE_DEPTH_GUARD_MIN_REMAINING
                            )
                        )
                        if _close_ready:
                            _close_seed = f"{cs.get('session_id','')}/close/{len(recent)}"
                            _close_gate = sum(ord(c) for c in _close_seed) % 1000
                            if _close_gate < CLOSURE_BRIDGE_GATE:
                                _arc_br = _select_next_frame_bridge(
                                    current_engine, recent, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited
                                )
                                if _arc_br:
                                    chosen = _arc_br
                                    chosen_turn_type = "question"
                                    _transition_reason = "closure"
                # ── End Phase 12C ─────────────────────────────────────────────────────

                frame_id = chosen
                frame_rec_chosen = _frames_by_id.get(frame_id, {})
                _chosen_engine_raw = (frame_rec_chosen.get("engine") or current_engine or "unknown").strip()
                # slot_followup is an internal routing tag — don't let it overwrite current_engine
                # in the client state, or the next turn will bridge away from the topic immediately.
                engine_id = current_engine if _chosen_engine_raw == "slot_followup" else _chosen_engine_raw
                # Bridge micro-layer: if selector switched engines, prepend a short transition phrase.
                current_engine_norm = (current_engine or "").strip().lower()
                chosen_engine_norm = (engine_id or "").strip().lower()
                if (
                    last_turn_was_answer
                    and chosen_engine_norm
                    and current_engine_norm
                    and chosen_engine_norm != current_engine_norm
                    and exchange_count >= 1
                ):
                    bridge_seed = f"{cs.get('session_id','')}/{len(recent)}/{current_engine_norm}->{chosen_engine_norm}"
                    bridge_prefix_text = _stable_pick(_BRIDGE_PREFIXES, bridge_seed) or "顺便问一下，"
                    # Avoid awkward double prefix like "顺便问一下，哦。"
                    reaction_prefix_text = ""
                # Step 7: include learner_memory and persona in response so client can show continuity
                if memory is not None:
                    _phase10_learner_memory = dict(memory)
                _phase10_persona_id = (cs.get("persona_id") or payload.get("persona_id") or "").strip() or None
                if chosen_turn_type == "loop_question":
                    same_engine_chain_count += 1
                    loop_count_in_engine    += 1      # Phase 12C: track LOOP turns per engine
                    if slot_names:
                        focus = slot_names[0]
                        same_slot_chain_count = same_slot_chain_count + 1 if focus == last_focus_slot else 1
                        last_focus_slot = focus
                else:
                    same_engine_chain_count += 1
                    chosen_engine = (frame_rec_chosen.get("engine") or "").strip().lower()
                    current_engine_norm = (current_engine or "").strip().lower()
                    if chosen_engine and current_engine_norm and chosen_engine != current_engine_norm:
                        same_engine_chain_count = 0
                        same_slot_chain_count = 0
                        last_focus_slot = ""
                        loop_count_in_engine = 0       # Phase 12C: reset LOOP count on engine change
                # Phase 12C: track engine visit list (client maintains primary; server adds current turn's engine)
                _visited_engine = (engine_id or "").strip().lower()
                if _visited_engine and _visited_engine not in engines_visited:
                    engines_visited = engines_visited + [_visited_engine]
                # Soft-visit: if a place-food frame was shown, mark the "food" engine as covered
                # so the bridge won't pick food-engine openers when food territory was already visited.
                _FOOD_COVERING_FRAMES = frozenset({"p2_pl_2", "f_food_what_good"})
                if frame_id in _FOOD_COVERING_FRAMES and "food" not in engines_visited:
                    engines_visited = engines_visited + ["food"]
                last_user_text = _answer_text_from_last_answer(last_answer) if last_turn_was_answer else _norm_text(cs.get("last_user_text"))
                _phase10_turn_type = chosen_turn_type
            else:
                frame_id  = payload.get("frame_id", "unknown")
                engine_id = payload.get("engine_id", "unknown")
                memory    = None   # not loaded in non-next_question path
            fo        = _frame_options.get(frame_id, {})
            options   = fo.get("options", []) if isinstance(fo, dict) else []
            card_id   = _stub_card_id(frame_id)
            gold      = next((o for o in options if o.get("is_gold")), None)
            frame_rec = _frames_by_id.get(frame_id, {})

            response = {
                "turn_uid":            payload.get("turn_uid", ""),
                "engine_id":           engine_id,
                "frame_id":            frame_id,
                "frame_text":          frame_rec.get("text", ""),
                "frame_pinyin":        frame_rec.get("pinyin", ""),
                "frame_text_en":       frame_rec.get("text_en", ""),
                "result":              "ok",
                "options":             options,
                "option_count":        len(options),
                "gold_option_present": gold is not None,
                "card_id":             gold["card_id"] if gold else card_id,
                "system_note":         "phase7.4 static options",
                "sentence_options":    _build_sentence_options(frame_rec, memory),
            }
            # Phase 13A: slot substitution — fill {CITY}/{PLACE}/[CITY] from learner memory
            _needs_city_slot = (
                any(tok in (response.get("frame_text") or "") for tok in ("{CITY}", "{PLACE}"))
                or "{CITY}" in (response.get("frame_pinyin") or "")
            )
            if _needs_city_slot:
                _slot_mem = memory if isinstance(memory, dict) else None
                if _slot_mem is None and _lm_load:
                    _cs_sl = payload.get("conversation_state") if isinstance(payload.get("conversation_state"), dict) else {}
                    _sl_lid = (_cs_sl.get("learner_id") or "").strip()
                    if _sl_lid:
                        _slot_mem = _lm_load(_sl_lid)
                if isinstance(_slot_mem, dict):
                    _city = (_slot_mem.get("lives_in") or _slot_mem.get("hometown") or "").strip()
                    if _city:
                        if "{CITY}" in (response.get("frame_text") or ""):
                            response["frame_text"] = response["frame_text"].replace("{CITY}", _city)
                        if "{PLACE}" in (response.get("frame_text") or ""):
                            response["frame_text"] = response["frame_text"].replace("{PLACE}", _city)
                        if "{CITY}" in (response.get("frame_pinyin") or ""):
                            response["frame_pinyin"] = response["frame_pinyin"].replace("{CITY}", _city)
                        if "[CITY]" in (response.get("frame_text_en") or ""):
                            response["frame_text_en"] = response["frame_text_en"].replace("[CITY]", _city)
                    else:
                        # No city in memory — fill generic so placeholder never reaches the user
                        _frame_text_raw = response.get("frame_text") or ""
                        if "{PLACE}" in _frame_text_raw:
                            response["frame_text"] = _frame_text_raw.replace("{PLACE}", "那儿")
                        if "{CITY}" in (response.get("frame_text") or ""):
                            response["frame_text"] = response["frame_text"].replace("{CITY}", "那儿")
            # Frame-level direction metadata (for UI action buttons)
            supports_reverse = False
            supports_why = False
            if "？" in (response.get("frame_text") or ""):
                supports_reverse = True
                supports_why = True
            if isinstance(fo, dict):
                if fo.get("supports_reverse") is True:
                    supports_reverse = True
                if fo.get("supports_why") is True:
                    supports_why = True
            response["supports_reverse"] = bool(supports_reverse)
            response["supports_why"] = bool(supports_why)
            # Phase 10.5: reaction micro-layer prefix (if generated above)
            if payload.get("next_question") and isinstance(payload.get("conversation_state"), dict):
                if reaction_prefix_text:
                    # Keep it lightweight: prepend only if the next frame is a question (avoid double-reactive turns)
                    if "？" in (frame_rec.get("text") or ""):
                        response["frame_text"] = f"{reaction_prefix_text}{response['frame_text']}"
                        response["system_note"] = "phase10.5 reaction_micro_layer"
                        response["reaction_used_fallback"] = bool(reaction_used_fallback)
                if bridge_prefix_text and "？" in (frame_rec.get("text") or ""):
                    response["frame_text"] = f"{bridge_prefix_text}{response['frame_text']}"
                    response["bridge_prefix_applied"] = True
                # Counter-reply: separate field so client TTS/displays it before the next question.
                if _counter_reply:
                    response["counter_reply"] = _counter_reply

                # Discovery mode: when user asked a question, offer follow-up questions THEY can
                # ask the persona — surfacing the mirror question bank so the learner can
                # interview the persona instead of being relentlessly interrogated.
                if user_asked_question and _counter_reply:
                    _disc_eng = (current_engine or engine_id or "").strip().lower()
                    _disc_pool: list = list(_MIRROR_QUESTIONS_BY_ENGINE.get(_disc_eng) or [])
                    # Supplement with up to 1 question from adjacent engines so there's always variety
                    for _adj in ("place", "work", "family", "hobby", "food", "travel", "identity"):
                        if _adj != _disc_eng and len(_disc_pool) < 3:
                            _adj_qs = _MIRROR_QUESTIONS_BY_ENGINE.get(_adj) or []
                            if _adj_qs:
                                _disc_pool.append(_adj_qs[0])
                    if _disc_pool:
                        response["discovery_questions"] = _disc_pool[:3]
                        response["user_led"] = True

            # Phase 10.5: blended reciprocity injection early (prefer answer + 你呢？)
            if payload.get("next_question") and isinstance(payload.get("conversation_state"), dict):
                cs = payload["conversation_state"]
                exchange_count = int(cs.get("exchange_count") or 0)
                if exchange_count < EARLY_EXCHANGES and isinstance(options, list) and options:
                    # Use the gold (or first) answer option as the base.
                    base_opt = next((o for o in options if isinstance(o, dict) and o.get("is_gold")), None) or (options[0] if isinstance(options[0], dict) else None)
                    if base_opt and base_opt.get("hanzi"):
                        blended = {
                            "card_id": "__blended_reciprocate",
                            "hanzi": f"{base_opt['hanzi']}你呢？",
                            "pinyin": "",
                            "meaning": "Blended reciprocity (answer + and you?)",
                            "is_gold": False,
                            "is_slot": False,
                            "kind": "WORD",
                        }
                        # Insert into top 2 without displacing gold if present.
                        new_opts = []
                        if options and isinstance(options[0], dict) and options[0].get("is_gold"):
                            new_opts.append(options[0])
                            new_opts.append(blended)
                            new_opts.extend(options[1:])
                        else:
                            new_opts.append(blended)
                            new_opts.extend(options)
                        options = new_opts[:]
                        response["options"] = options
                        response["option_count"] = len(options)

            # Phase 10.5: contextual curiosity gating + oxygen selection (probe row)
            if payload.get("next_question") and isinstance(payload.get("conversation_state"), dict):
                cs = payload["conversation_state"]
                last_turn_was_answer = cs.get("last_turn_was_answer") is True
                if last_turn_was_answer:
                    slot_names = _infer_slot_names_from_answer(cs.get("last_answer") if isinstance(cs.get("last_answer"), dict) else None)
                    meaningful = bool(slot_names) or bool(new_memory_written)
                    should = _should_surface_curiosity(
                        cs,
                        meaningful=meaningful,
                        last_partner_was_loop=(chosen_turn_type == "loop_question"),
                        last_partner_had_reaction=bool(reaction_prefix_text),
                        interest_level=interest_level,
                    )
                    if should:
                        response["probe_offer"] = True
                        response["probe_options"] = _select_probe_options(engine_id, slot_names)
                    else:
                        response["probe_offer"] = False

            # Phase 10 Step 7: cross-session continuity — client can show remembered facts
            if _phase10_learner_memory is not None:
                response["learner_memory"] = _phase10_learner_memory
            if _phase10_persona_id:
                response["persona_id"] = _phase10_persona_id
            if _phase10_turn_type:
                response["turn_type"] = _phase10_turn_type
                # Inform client for state tracking (optional; safe extra fields)
                response["curiosity_depth"] = curiosity_depth
                response["loop_attempted"] = bool(loop_attempted)
                response["weak_loop_encountered"] = bool(frame_id in _WEAK_LOOP_FRAME_IDS)
                response["weak_loop_frame_id"] = frame_id if frame_id in _WEAK_LOOP_FRAME_IDS else None
                response["interest_score"] = int(interest_score)
                response["interest_level"] = interest_level
                response["last_interest_level"] = last_interest_level
                response["pending_listening_move"] = bool(pending_listening_move)
                response["listening_wait_turns"] = int(listening_wait_turns)
                response["listening_move_selected"] = listening_move_selected
                response["listening_move_reason"] = listening_move_reason
                response["same_engine_chain_count"] = int(same_engine_chain_count)
                response["same_slot_chain_count"] = int(same_slot_chain_count)
                response["last_focus_slot"] = last_focus_slot
                response["last_user_text"] = last_user_text
                # Phase 12C: session arc trace
                response["loop_count_in_current_engine"] = int(loop_count_in_engine)
                response["arc_state"] = {
                    "turns_in_current_engine": int(same_engine_chain_count),
                    "loop_count":              int(loop_count_in_engine),
                    "engines_visited":         list(engines_visited),
                    "transition_reason":       _transition_reason,
                }
                # Phase 10.7-C: move_type filter trace — always emitted when selector ran.
                if _mt_filter_debug:
                    response["move_type_filter"] = {
                        # Phase 10.7 fields
                        "current_move_type":               _mt_filter_debug.get("current_move_type"),
                        "allowed_next_move_types":         _mt_filter_debug.get("allowed_next_move_types"),
                        "candidates_before_move_filter":   _mt_filter_debug.get("candidates_before_move_filter"),
                        "candidates_after_move_filter":    _mt_filter_debug.get("candidates_after_move_filter"),
                        "fallback_occurred":               _mt_filter_debug.get("fallback_occurred", True),
                        "selection_source":                _mt_filter_debug.get("selection_source", "legacy"),
                        "move_type_filter_applied":        _mt_filter_debug.get("move_type_filter_applied", False),
                        "move_type_filter_skipped_reason": _mt_filter_debug.get("move_type_filter_skipped_reason"),
                        # Phase 11.0 scoring fields
                        "phase11_selection_source":        _mt_filter_debug.get("phase11_selection_source", "legacy"),
                        "phase11_scores":                  _mt_filter_debug.get("phase11_scoring", []),
                        "phase11_candidate_count":         len(_mt_filter_debug.get("phase11_scoring", [])),
                    }

            # Phase 11C: Persona enrichment — voice_line, discoverable_fact, cross-session memory
            # partner_id comes from conversation_state; client tracks which reveals have fired.
            _cs_for_persona = payload.get("conversation_state") if isinstance(payload.get("conversation_state"), dict) else {}
            _partner_id = _cs_for_persona.get("partner_id") or payload.get("partner_id") or ""
            if _partner_id:
                _persona = _resolve_persona(_partner_id)
                if _persona:
                    response["partner_name"] = _persona.get("display_name", "")
                    response["partner_name_pinyin"] = _persona.get("name_pinyin", "")

                    _frame_mt = _get_frame_move_type(frame_id) or ""
                    if _frame_mt == "EXTEND":
                        _engine_key = (engine_id or "").strip().lower()

                        # ── Voice line: first EXTEND per engine per session only ──────────────
                        _revealed_vl = _cs_for_persona.get("revealed_voice_lines") or {}
                        _voice_shown = bool(_revealed_vl.get(_engine_key))
                        if not _voice_shown:
                            _prefix = (_persona.get("voice_lines") or {}).get(_engine_key, "")
                            if _prefix:
                                response["partner_prefix"] = _prefix

                        # ── Discoverable fact: once per engine (session + cross-session gated) ─
                        # Anti-stack: voice_line must have fired first (on a prior EXTEND visit).
                        # Depth gate: partner only discloses deeper facts after enough turns.
                        _revealed_facts = _cs_for_persona.get("revealed_partner_facts") or {}
                        _fact_shown_session = bool(_revealed_facts.get(_engine_key))

                        # Cross-session gate: check learner_memory if not already blocked by session gate
                        _p11c_learner_id = (_cs_for_persona.get("learner_id") or "").strip() or None
                        _fact_shown_cross = False
                        if not _fact_shown_session and _lm_load and _p11c_learner_id:
                            try:
                                _cross_mem = _lm_load(_p11c_learner_id) or {}
                                _fact_shown_cross = bool(
                                    _cross_mem.get("partner_facts_seen", {})
                                    .get(_partner_id, {})
                                    .get(_engine_key)
                                )
                            except Exception:
                                pass

                        _fact_blocked = _fact_shown_session or _fact_shown_cross
                        _engine_depth = int(_cs_for_persona.get("same_engine_chain_count") or 0)

                        if not _fact_blocked and _voice_shown and _engine_depth >= FACT_REVEAL_DEPTH:
                            _disc_fact = (_persona.get("discoverable_facts") or {}).get(_engine_key, "")
                            if _disc_fact:
                                response["partner_fact"] = _disc_fact
                                # Persist to learner_memory for cross-session suppression
                                if _lm_load and _lm_save and _p11c_learner_id:
                                    try:
                                        _pmem = _lm_load(_p11c_learner_id) or {}
                                        _pmem.setdefault("partner_facts_seen", {}) \
                                             .setdefault(_partner_id, {})[_engine_key] = True
                                        _lm_save(_p11c_learner_id, _pmem)
                                    except Exception:
                                        pass

            data = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(f"404 Not Found: {path}".encode())

    def _serve_file(self, file_path: Path, original_path: str):
        if file_path.is_file():
            mime, _ = mimetypes.guess_type(str(file_path))
            mime = mime or "application/octet-stream"
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"404 Not Found: {original_path}\nResolved: {file_path}".encode())

    def _json_error(self, code: int, msg: str):
        data = json.dumps({"error": msg}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print(f"[ui_server] {self.address_string()} - {format % args}")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Serve multiple parallel GETs (browser Promise.all on load). Single-threaded server can stall or reset on Windows."""

    daemon_threads = True


def _kill_stale_server_processes(port: int) -> None:
    """Kill any OTHER Python processes already listening on *port* (Windows + Unix)."""
    my_pid = os.getpid()
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True, text=True, timeout=5,
            )
            pids_seen: set = set()
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        try:
                            pid = int(parts[-1])
                        except ValueError:
                            continue
                        if pid != my_pid and pid not in pids_seen:
                            pids_seen.add(pid)
                            subprocess.run(
                                ["taskkill", "/F", "/PID", str(pid)],
                                capture_output=True, timeout=5,
                            )
                            print(f"[ui_server] Killed stale server PID={pid} on port {port}", flush=True)
        else:
            # Unix: use lsof or ss
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True, text=True, timeout=5,
            )
            for pid_str in result.stdout.strip().splitlines():
                try:
                    pid = int(pid_str.strip())
                except ValueError:
                    continue
                if pid != my_pid:
                    os.kill(pid, 9)
                    print(f"[ui_server] Killed stale server PID={pid} on port {port}", flush=True)
    except Exception as exc:
        print(f"[ui_server] Warning: could not clean stale processes on port {port}: {exc}", flush=True)


if __name__ == "__main__":
    port = 8765
    _kill_stale_server_processes(port)
    print(f"[ui_server] Listening on http://localhost:{port}", flush=True)
    ThreadedHTTPServer(("", port), Handler).serve_forever()
