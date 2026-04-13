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
OVERLOAD_CONFUSION_THRESHOLD  = 5    # recent_confusion_count ≥ this → overload: same-engine non-loop first, else bridge
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


# ── Content: mirror questions + persona deflect phrases (data-driven, no hardcoding) ────────────
CONTENT_DIR: Path = REPO_ROOT / "content"

# Mirror questions: loaded from content/mirror_questions.json.
# Adding a new question only requires editing that file — no server code change.
_mirror_questions_raw: dict = {}
_mq_path = CONTENT_DIR / "mirror_questions.json"
try:
    if _mq_path.is_file():
        _mq_data = json.loads(_mq_path.read_text(encoding="utf-8"))
        _mirror_questions_raw = _mq_data.get("by_engine") or {}
        print(f"[ui_server] mirror_questions loaded ({sum(len(v) for v in _mirror_questions_raw.values())} questions across {len(_mirror_questions_raw)} engines)")
    else:
        print(f"[ui_server] WARNING: mirror_questions.json not found at {_mq_path}")
except Exception as _e:
    print(f"[ui_server] WARNING: mirror_questions load failed: {_e}")

def _flatten_recovery_phrases_for_maps(raw: dict) -> list:
    """Same shape as tools/build_runtime_artifacts._flatten_recovery_phrases_content (keep in sync)."""
    legacy = raw.get("phrases")
    if isinstance(legacy, list) and len(legacy) > 0:
        return legacy
    out: list = []

    def _one(row: dict, use: str, level_default: str, topic: Optional[str] = None) -> None:
        if not isinstance(row, dict):
            return
        gloss = (row.get("text_en") or row.get("meaning") or "").strip()
        item = {
            "id": row.get("id"),
            "hanzi": row.get("hanzi") or "",
            "pinyin": row.get("pinyin") or "",
            "text_en": gloss,
            "level": row.get("level") or level_default,
            "use": use,
            "recovery_action": row.get("recovery_action") or "",
        }
        for k in ("move_type", "response_role", "etymology", "repair_kind", "priority", "legacy_ids",
                   "core_set", "routing_group", "always_surface", "surface_when_repair_count_gte"):
            if row.get(k) is not None:
                item[k] = row[k]
        if topic:
            item["topic"] = topic
        out.append(item)

    for row in raw.get("not_understood") or []:
        _one(row, "not_understood", "P1")
    for row in raw.get("deflections") or []:
        _one(row, "persona_deflect", "P2", topic="generic")
    for row in raw.get("acknowledgements") or []:
        _one(row, "deflection_ack", "P1")
    return out


# Persona deflect phrases: loaded from content/recovery_phrases.json (use=persona_deflect).
# Adding/editing a phrase only requires editing that file — no server code change.
_persona_deflect_phrases: dict = {}     # topic -> [hanzi_str, ...]  (for _persona_deflect picker)
_persona_deflect_en_map: dict = {}      # hanzi_str -> text_en       (for hint lookup)
_persona_deflect_pinyin_map: dict = {}  # hanzi_str -> pinyin      (for counter_reply_pinyin)
_recovery_phrase_legacy_id_alias: dict[str, str] = {}  # legacy phrase id -> canonical id (v1.2)
_rp_path = CONTENT_DIR / "recovery_phrases.json"
try:
    if _rp_path.is_file():
        _rp_data = json.loads(_rp_path.read_text(encoding="utf-8"))
        _rp_flat = _flatten_recovery_phrases_for_maps(_rp_data)
        for _p in _rp_flat:
            if _p.get("use") == "persona_deflect":
                _topic = _p.get("topic") or "generic"
                _hz = (_p.get("hanzi") or "").strip()
                if _hz:
                    _persona_deflect_phrases.setdefault(_topic, []).append(_hz)
                    _persona_deflect_en_map[_hz] = (_p.get("text_en") or "").strip()
                    _py = (_p.get("pinyin") or "").strip()
                    if _py:
                        _persona_deflect_pinyin_map[_hz] = _py
            _pid = (_p.get("id") or "").strip()
            if _pid:
                for _lid in _p.get("legacy_ids") or []:
                    if isinstance(_lid, str) and _lid.strip():
                        _recovery_phrase_legacy_id_alias[_lid.strip()] = _pid
        _nd = len(_persona_deflect_phrases)
        _np = sum(len(v) for v in _persona_deflect_phrases.values())
        _na = len(_recovery_phrase_legacy_id_alias)
        print(f"[ui_server] persona_deflect phrases loaded ({_np} phrases across {_nd} topics); recovery legacy id aliases: {_na}")
    else:
        print(f"[ui_server] WARNING: recovery_phrases.json not found at {_rp_path}")
except Exception as _e:
    print(f"[ui_server] WARNING: persona_deflect phrases load failed: {_e}")


def _persona_deflect_en(zh: str) -> str:
    """Look up the English translation for a deflection phrase. Returns empty string if not found."""
    return _persona_deflect_en_map.get((zh or "").strip(), "")


def _voice_line_en_for_zh(persona: Optional[dict], line_zh: str) -> str:
    """When _direct_persona_answer returns a line from voice_lines, pair it with voice_lines_en."""
    if not persona or not (line_zh or "").strip():
        return ""
    d = (line_zh or "").strip()
    vl = (persona.get("voice_lines") or {})
    vl_en = (persona.get("voice_lines_en") or {})
    for key, line in vl.items():
        if (line or "").strip() == d:
            return (vl_en.get(key) or "").strip()
    return ""


def _resolve_counter_reply_pinyin(zh: str) -> str:
    """Curated pinyin when counter_reply matches a persona_deflect phrase (full line or 我呢，+inner)."""
    s = (zh or "").strip()
    if not s:
        return ""
    if s in _persona_deflect_pinyin_map:
        return _persona_deflect_pinyin_map[s]
    _prefix = "我呢，"
    if s.startswith(_prefix):
        inner = s[len(_prefix) :].strip()
        if inner and inner in _persona_deflect_pinyin_map:
            py = _persona_deflect_pinyin_map[inner]
            if py:
                return f"wǒ ne，{py}"
    return ""


def _en_for_counter_reply(zh: str, inner: Optional[str] = None) -> str:
    """English for counter_reply when zh wraps an inner phrase (e.g. 我呢， + deflection).

    Looks up `inner` in the deflection map first; if zh starts with 我呢， prefix the EN gloss.
    """
    if inner:
        en = _persona_deflect_en(inner.strip())
        if en:
            if (zh or "").startswith("我呢，") and not (inner.strip()).startswith("我呢"):
                return f"As for me — {en}"
            return en
    return _persona_deflect_en(zh or "") or ""


def _persona_deflect(topic: str, seed: str = "") -> str:
    """Return a persona deflection phrase for the given topic, loaded from recovery_phrases.json.
    Falls back to 'generic' topic, then a hardcoded last-resort string."""
    pool = _persona_deflect_phrases.get(topic) or _persona_deflect_phrases.get("generic") or []
    if pool:
        return _stable_pick(pool, seed or topic) or pool[0]
    return "这个嘛……说来话长，有空再聊！"   # absolute last resort only


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
    # Identity flow (Phase 12C): name → friends call → family call → name story → age.
    "identity": [
        "f_ask_you_name",        # 1. 你叫什么名字？
        "f_id_friends_call",     # 2. 朋友一般怎么叫你？
        "f_probe_id_nickname",   # 3. 家里人怎么叫你？
        "f_name_story",          # 4. 你名字有什么故事吗？
        "f_how_old",             # 5. 你多大了？
    ],
    # Place flow (Phase 12C final): origin → current city → special → food → hometown → travel bridge → who with → why.
    "place": [
        "f_from_where",       # 1. 你是哪里人？
        "f_live_where",       # 2. 你现在住哪里？
        "f_place_special",    # 3. 这里有什么特别的？
        "f_place_food",       # 4. 这里有什么好吃的？
        "f_home_where",       # 5. 你老家在哪儿？
        "f_place_travel",     # 6. 你会去别的地方吗？
        "f_live_with_who",    # 7. 你跟谁一起住？
        "f_place_why_live",   # 8. 你为什么住在这里？
    ],
    # Family flow (Phase 12C): live together → closest → activity → married → children.
    # Screening questions (siblings, have_family) removed; warmth-first ordering.
    "family": [
        "p2_fa_live_with",          # 1. 你跟家人住在一起吗？
        "f_probe_family_closest",   # 2. 你和家里谁最亲近？
        "p2_fa_activity",           # 3. 你最喜欢和家人一起做什么？
        "f_married",                # 4. 你结婚了吗？
        "f_have_children",          # 5. 你有孩子吗？
    ],
    # Work (Phase 12C): what → company → tenure → location → origin story → future → why?.
    "work": [
        "f_what_work",           # 1. 你做什么工作？
        "f_work_company",        # 2. 你在哪个公司上班？
        "f_work_tenure",         # 3. 你做这个工作多久了？
        "f_work_where",          # 4. 你工作在哪儿？
        "f_probe_work_origin",   # 5. 你怎么开始做这个工作的？
        "f_probe_work_future",   # 6. 你以后还想做这个工作吗？
        "f_probe_work_why_quit", # 7. 为什么呢？ — reacts to any answer about future plans
    ],
    # Hobby (Phase 12C): open → location → best part → origin → social → travel.
    "hobby": [
        "f_hobby_special",       # 1. 你喜欢做什么？有什么特别的爱好？
        "f_hobby_where",         # 2. 你在哪儿做？
        "f_hobby_best_part",     # 3. 你最喜欢这个爱好的哪一点？
        "f_probe_hobby_origin",  # 4. 你是怎么开始这个爱好的？
        "f_probe_hobby_social",  # 5. 你一般自己做还是跟朋友一起？
        "f_hobby_travel",        # 6. 你会去别的地方做吗？
    ],
    # Travel: where → best trip → special → food → who with → purpose.
    # Travel (Phase 12C): start with WHERE (establishes context) → then depth questions.
    # f_travel_been ("你去过吗？") removed — it has no referent as a cold opener.
    "travel": [
        "f_travel_where",     # 1. 你去过哪里？
        "f_travel_best_trip", # 2. 哪次旅行最难忘？
        "f_travel_special",   # 3. 那里有什么特别的？
        "f_travel_food",      # 4. 那里有什么好吃的？
        "f_travel_with_who",  # 5. 你是跟谁一起去的？
        "f_travel_purpose",   # 6. 这是工作还是玩？
    ],
    # Food: what's good → famous dish → tasty → EXTEND break → spicy → expensive.
    # Food (Phase 12C): short vivid branch — available → famous → taste. Exits quickly to PLACE/TRAVEL.
    "food": [
        "f_food_available",  # 1. 那里有什么好吃的？
        "f_food_famous",     # 2. 最有名的菜是什么？
        "f_food_taste",      # 3. 是什么味道？
    ],
    "life": [],
}
# A frame id may only be chosen if all of its "after" frames are in recent_frame_ids (already asked).
_FRAME_AFTER: dict = {
    "f_ask_name_meaning": ["f_ask_you_name"],  # don't ask name meaning before asking name
    # Identity follow-up assumes a name exists
    "p2_id_2": ["f_ask_you_name"],
    # Story elicitation only makes sense after the story question was asked
    "f_name_story_elicit": ["p2_id_ext1"],
    # "Why's that?" only makes sense after the future-plans question has been asked
    "f_probe_work_why_quit": ["f_probe_work_future"],
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
    "p2_pl_far": ["f_from_where", "frame.location.live_question"],
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
        "f_place_like_there": ["f_from_where", "frame.location.live_question", "p2_pl_far", "p2_pl_4", "p2_pl_2"],
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
        # Entity follow-up chain frames (efc_type) need a resolved family entity — selected only
        # via _pick_efc_frame. Do not let the generic ladder pick them (would hit {ENTITY} fallback).
        and not (fr.get("efc_type") or "").strip()
    ]
    # Phase 12D: return only frames in _FRAME_ORDER — orphaned frames (removed from order but
    # still in JSON) must not be reachable via the ladder. This prevents stale frames from
    # appearing after engine content stabilisation.
    order = _FRAME_ORDER.get(engine_norm) or []
    ordered = [f for f in order if f in raw]
    return ordered


# Until this frame has been shown, bridging *out* of place should not land in food — otherwise
# "顺便问一下，你会自己做吗？" appears without any "有什么好吃的？"-style setup (user request: Phase 12C).
_PLACE_FOOD_TOPIC_PRIMED_FRAMES: frozenset = frozenset({"p2_pl_2"})


def _place_food_topic_primed(recent_frame_ids: list) -> bool:
    r = {(x or "").strip() for x in (recent_frame_ids or [])}
    return bool(r & _PLACE_FOOD_TOPIC_PRIMED_FRAMES)


# Phase 9.2: which engines we can bridge to from each engine (deterministic order; from conversation specs)
_BRIDGE_TARGETS: dict = {
    "identity": ["place", "family", "work", "hobby"],
    "place":    ["food", "family", "work", "travel", "hobby", "identity"],
    "family":   ["identity", "work", "hobby", "place"],
    "work":     ["family", "identity", "place", "hobby"],
    "hobby":    ["family", "work", "identity", "travel", "food"],   # family/work first: most natural after hobbies
    "travel":   ["family", "work", "identity", "place", "hobby", "food"],
    "food":     ["family", "work", "place", "travel", "hobby", "life"],
    "life":     ["identity", "family", "work", "place"],
}

# When prefer_bridge (recovery / change topic): try engines in this order so the next question feels like a natural switch (place/identity/family first), not a jump to food/travel.
_RECOVERY_BRIDGE_ENGINE_ORDER: list = ["place", "identity", "family", "work", "hobby", "travel", "food", "life"]
_BRIDGE_PREFIXES: list = [
    # Natural topic shifts — varied so the same opener doesn't repeat every transition.
    # All entries end with "，" to be concatenated with the frame text.
    "对了，",
    "那，",
    "说起来，",
    "另外，",
    "顺便问一下，",
]

# Frames that ask essentially the same question in different engines.
# If any frame in a set has been shown, all others in that set are skipped.
_MUTUAL_EXCLUSION_FRAMES: dict = {
    # Phase 12D: food engine opener — skip if mid-engine food frames already shown.
    # Happens when DISH bridge asks f_food_famous before the engine is entered directly;
    # the ladder must not then circle back to the opener (那里有什么好吃的？).
    "f_food_available": {"f_food_famous", "f_food_taste"},
    # Cross-topic deduplication: travel "where have you been" vs place "where from/live"
    "f_travel_where": {"p2_tr_1"},     # "你去过哪里？" ↔ "你去过哪些国家？"
    "p2_tr_1": {"f_travel_where"},
    "f_ask_you_name": {"p2_id_2"},     # "你叫什么名字？" ↔ "大家一般怎么叫你？" (both ask for name)
    "p2_id_2": {"f_ask_you_name"},
    # Cross-topic deduplication: "who do you do X with?" — hobby social ↔ travel companion ↔ travel alone probe
    # User answered once; don't repeat the same social question across engine boundary.
    "f_travel_with_who":    {"f_probe_hobby_social", "f_probe_travel_alone"},
    "f_probe_hobby_social": {"f_travel_with_who", "f_probe_travel_alone"},
    "f_probe_travel_alone": {"f_travel_with_who", "f_probe_hobby_social"},
    # Cross-topic deduplication: "你是哪里人？" — identity engine f_from_where and place engine
    # f_home_where ask an identical question. Once either is answered, suppress the other.
    "f_from_where": {"f_home_where"},
    "f_home_where": {"f_from_where"},
    # Semantic group: living_arrangement — "do you live with family?"
    # f_live_with_who (place engine) and p2_fa_live_with (family engine) are semantically identical.
    # Once either is answered, the other is suppressed.
    "f_live_with_who":  {"p2_fa_live_with"},
    "p2_fa_live_with":  {"f_live_with_who"},
    # Semantic group: location_origin — "where are you from / where is home?"
    # f_home_where and f_from_where already suppress each other (above).
    # f_place_origin is a variant that should be treated as equivalent if it exists.
    "f_place_origin":   {"f_from_where", "f_home_where"},
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

# Frames acceptable early in a session but weak as late-session continuations.
# When late_session_mode is active and a meaningful answer was just given,
# these frames are preempted by the soft closing move instead of being asked.
# Add frames here declaratively; no selector logic change required.
_LATE_SESSION_PREEMPTIBLE_FRAMES: frozenset = frozenset({
    # EFC family secondary details — spouse/relative work, age, location micro-probes
    "f_efc_family_work",
    "f_efc_family_age",
    "f_efc_family_where",
    "f_efc_family_married",
    "f_efc_family_child",
    # Food drill expansions — repetitive "what's good to eat there?" chains
    "f_travel_food",
    "f_food_available",
    "f_food_what_good",
    "f_food_famous",
    "f_food_famous_dish",
    "f_food_taste",
    "f_food_tasty",
    "f_food_expensive",
    "f_food_like_spicy",
    # Travel secondary details — logistical follow-ups with low personal value late-session
    "f_travel_with_who",
    "f_travel_purpose",
})

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
# Rule: keep each item semantically distinct — no two should be near-synonyms.
_CURIOSITY_REACTIONS_BY_ENGINE: dict = {
    # Phase 13C: reactions must NOT contain '？' — the prepend guard blocks any reaction
    # that itself ends in a question from being prepended to the next question frame,
    # making high-interest turns invisible. Use short exclamations instead.
    # All entries must be ≥5 Chinese characters so the ≤4-char blandness gate
    # does not treat curiosity reactions as generic and override them with echoes.
    # Each pool has ≥5 entries to reduce same-session repetition.
    "food":     ["哇，听起来很好吃！", "真的吗，太有意思了！", "哦，真没想到！", "听起来很特别！", "哇，这很有特色！"],
    "travel":   ["听起来太厉害了！", "哇，去过这么多地方！", "真的好羡慕！", "哇，太开眼界了！", "听起来很精彩！"],
    "place":    ["哇，听起来不错！", "真的吗，很有意思！", "真不简单啊！", "听起来很有特色！", "真是太好了！"],
    "work":     ["哇，真不简单！", "真的吗，太厉害了！", "听起来很有意思！", "哦，真了不起！", "太出乎意料了！"],
    "hobby":    ["哇，太厉害了！", "听起来真有意思！", "真的吗，太棒了！", "哦，很特别啊！", "听起来很好玩！"],
    "family":   ["听起来很幸福！", "哦，真有意思！", "感情很好啊！", "听起来很温馨！", "真的很好啊！"],
    "identity": ["名字很好听！", "是吗，很有意思！", "哦，真有意思！", "很特别的名字！", "听起来不错！"],
}
_CURIOSITY_REACTIONS_GENERIC: list = ["真是不简单！", "听起来很有意思！", "是吗，很好啊！", "哦，真没想到！", "真是特别啊！"]

# Soft closing reactions: emitted when late-session + topic completion suppress bridge
# and no next move (probe or ladder frame) is available. Terminal / pause move — no follow-up.
# Format: (hanzi, pinyin, english)
_CLOSING_REACTIONS: list = [
    ("明白了。", "Míngbai le.", "Got it."),
    ("这样啊。", "Zhèyàng a.", "I see / so that's how it is."),
    ("这样挺好。", "Zhèyàng tǐng hǎo.", "That sounds good."),
]

# Oxygen selection by context (engine or slot). Only surface 1–2 when gating conditions fire.
_OXYGEN_IDS_BY_ENGINE: dict = {
    "place":  ["zenmeyang", "nali"],
    "work":   ["weishenme", "zenmeyang"],  # "why?" is most natural for work disclosures
    "food":   ["weishenme", "xihuan_ma"],
    # Phase 12D Step 2: add oxygen coverage for engines previously without probes.
    "hobby":  ["zenmeyang", "weishenme"],
    "family": ["weishenme", "xihuan_ma"],
    "travel": ["nali", "zenmeyang"],
}
_OXYGEN_IDS_BY_SLOT: dict = {
    "CITY":   ["zenmeyang", "nali"],
    "JOB":    ["zenmeyang"],
    "DISH":   ["weishenme", "xihuan_ma"],
    "NAME":   ["weishenme"],
    # Phase 12D Step 2: slot-level oxygen coverage for HOBBY and TRAVEL bridges.
    "HOBBY":  ["zenmeyang", "weishenme"],
    "TRAVEL": ["nali", "zenmeyang"],
}

# Slot/topic-specific follow-up preferences (attempt before generic engine ladder).
_SLOT_FOLLOWUP_PREFERENCES: dict = {
    # CITY: distance → special? → probe → like → why → …
    # Frames with skip_when in p2_frames.json are skipped by _check_skip_condition inside _pick_slot_followup_frame_id.
    # p2_pl_far   skip_when=city_is_well_known  (北京/上海/广州)
    # p2_pl_ext1  skip_when=city_is_familiar    (all curriculum cities/countries)
    # CITY/PLACE: aligned with place engine Phase 12C final order (skip opener — city already disclosed).
    "CITY": ["f_live_where", "f_place_special", "f_place_food", "f_home_where", "f_place_travel", "f_live_with_who", "f_place_why_live"],
    # JOB: f_probe_work_role_detail fires first when interest is medium/high (slot followup is
    # interest-gated), so the first follow-up naturally asks "what kind of work is that?" for
    # any unusual job (CIO, blogger, chef, teacher, etc.) before continuing the standard chain.
    "JOB":  ["f_probe_work_role_detail", "f_work_company", "f_work_tenure", "f_work_where",
             "f_probe_work_origin", "f_probe_work_future", "f_probe_work_why_quit"],
    # DISH: ask WHY first, then variety questions.
    # DISH/FOOD: aligned with food engine Phase 12C order (skip opener — dish already disclosed).
    "DISH": ["f_food_famous", "f_food_taste"],
    "NAME": ["f_id_friends_call", "f_probe_id_nickname", "f_name_story", "f_how_old"],
    # FAMILY: after user reveals family info, probe deeper — live together? siblings? married? children? how often?
    "FAMILY": ["p2_fa_live_with", "f_probe_family_closest", "p2_fa_activity", "f_married", "f_have_children"],
    # STORY: after user answers a story-elicitation frame — probe with "why" or "tell me more"
    "STORY": ["f_generic_why"],
    # TRAVEL: which is best? then why, then continuation.
    # TRAVEL: aligned with travel engine Phase 12C order (skip opener — context already established).
    "TRAVEL": ["f_travel_where", "f_travel_best_trip", "f_travel_special", "f_travel_food", "f_travel_with_who", "f_travel_purpose"],
    # HOBBY: aligned with hobby engine Phase 12C order (skip opener — learner already disclosed hobby).
    "HOBBY": ["f_hobby_where", "f_hobby_best_part", "f_probe_hobby_origin", "f_probe_hobby_social", "f_hobby_travel"],
    # COMPANY: after the learner names any company (Alibaba, Fujitsu, a university, etc.),
    # probe what it's like there before continuing the standard work sequence.
    "COMPANY": ["f_probe_work_company_vibe", "f_work_tenure", "f_work_where",
                "f_probe_work_origin", "f_probe_work_future", "f_probe_work_why_quit"],
}

# ── Response-seeded bridge engine queue ──────────────────────────────────────────────────────────
# Maps a disclosed slot to the engine that should be seeded for future bridging.
# When the learner mentions content that belongs to another engine, that engine is queued
# as a preferred bridge target — conversation follows the learner's narrative thread.
_SLOT_TO_BRIDGE_ENGINE: dict = {
    "CITY":   "place",
    "JOB":    "work",
    "DISH":   "food",
    "TRAVEL": "travel",
    "FAMILY": "family",
    "HOBBY":  "hobby",
    "NAME":   "identity",
}

# Frame-id-based bridge seeds: when a specific partner frame is answered, seed the target engine
# WITHOUT tagging a slot (avoids triggering slot-followup chains that jump engines prematurely).
# e.g. f_work_where discloses a work city → seeds place for a future bridge, but must NOT
# fire the CITY slot-followup chain which would ask f_live_where before work probe frames finish.
_FRAME_ID_TO_SEED: dict = {
    "f_work_where": "place",
}

# Content keywords that can seed an engine even when the frame_id doesn't trigger slot detection.
_SEED_FAMILY_KEYWORDS: frozenset = frozenset({
    "妻子", "老婆", "丈夫", "先生", "孩子", "父母", "父亲", "母亲", "妈妈", "爸爸",
    "哥哥", "弟弟", "姐姐", "妹妹", "兄弟", "儿子", "女儿",
})
_SEED_PLACE_KEYWORDS: frozenset = frozenset({
    "苏州", "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "重庆", "武汉", "西安",
    "青岛", "厦门", "天津", "昆明", "新西兰", "澳大利亚", "美国", "英国", "加拿大", "法国",
    "德国", "日本", "韩国", "新加坡",
})


def _infer_cross_engine_seeds(
    slot_names: List[str],
    answer_text: str,
    current_engine: str,
    last_fid: str = "",
) -> List[str]:
    """Return a deduplicated list of engine names that should be seeded for future bridging,
    based on slot disclosures, frame_id, and content keywords in the learner's answer.

    New seeds are placed first (most recent = highest priority).
    Only engines different from current_engine are included — the current engine is already active.
    """
    norm = (current_engine or "").strip().lower()
    seeds: List[str] = []
    seen: set = set()

    def _add(engine: str) -> None:
        if engine and engine != norm and engine not in seen:
            seeds.append(engine)
            seen.add(engine)

    # Frame-id-based seeds: most precise, no slot-followup side effects.
    # Use this for frames that disclose cross-engine content but must NOT trigger the
    # slot-followup chain for that slot (e.g. f_work_where discloses a city but the
    # CITY slot-followup chain would jump to place engine before work probes finish).
    fid_seed = _FRAME_ID_TO_SEED.get((last_fid or "").strip())
    if fid_seed:
        _add(fid_seed)

    # Slot-based seeds (high reliability — frame_id triggered slot detection)
    for slot in slot_names:
        target = _SLOT_TO_BRIDGE_ENGINE.get(slot)
        if target:
            _add(target)

    # Content-based seeds (for answers whose frame_id doesn't tag a slot).
    # NOTE: place seeding is intentionally omitted here — city names appear inside institution
    # and company names (e.g. "西安交通大学") which are NOT genuine place disclosures.
    # Place seeds are reliably inferred via frame_id (_FRAME_ID_TO_SEED or CITY slot).
    if answer_text:
        if _looks_travel_related_answer(answer_text):
            _add("travel")
        if any(kw in answer_text for kw in _SEED_FAMILY_KEYWORDS):
            _add("family")
        if _looks_food_related_answer(answer_text):
            _add("food")

    return seeds


def _merge_seeded_engines(
    new_seeds: List[str],
    existing: List[str],
    current_engine: str,
) -> List[str]:
    """Merge new seeds (highest priority) with existing seeds, deduplicating.
    Current engine is always excluded — it is being visited now.
    """
    norm = (current_engine or "").strip().lower()
    result: List[str] = []
    seen: set = set()
    for e in new_seeds + (existing or []):
        if e and e != norm and e not in seen:
            result.append(e)
            seen.add(e)
    return result


# Very well-known cities: skip "离那儿远吗？" — partner can assume distance is obvious.
# Referenced by skip_when="city_is_well_known" in p2_frames.json → evaluated via _check_skip_condition.
_CITIES_SKIP_DISTANCE_ASK: frozenset = frozenset({"北京", "上海", "广州"})

# Curriculum + common countries (p1_fillers): used only to detect "familiar" place tokens in answers.
# Referenced by skip_when="city_is_familiar" in p2_frames.json → evaluated via _check_skip_condition.
_FAMILIAR_PLACE_NAMES: frozenset = frozenset(
    {
        "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉", "西安", "青岛", "厦门", "天津", "昆明",
        "中国", "新西兰", "澳大利亚", "美国", "英国", "加拿大", "日本", "韩国", "法国", "德国", "新加坡", "马来西亚", "泰国",
    }
)


# Declarative coherence-avoid conditions.
# Maps coherence_avoid_if predicate name → (avoid_markers, allow_markers).
# A frame is suppressed when ANY avoid marker is present AND NO allow marker is present in last_text.
# Add new predicates here; no other code needs to change.
_COHERENCE_MARKERS: dict = {
    "sightseeing_context": {
        "avoid": (
            "花园", "风景", "园林", "古老", "历史", "博物馆", "建筑", "参观", "名胜古迹",
            "很漂亮", "很美", "美丽", "文化", "特色", "湖水", "公园", "寺庙", "桥", "运河",
        ),
        "allow": ("想家", "想念", "老家", "父母", "回国", "家乡", "亲人"),
    },
}


def _check_coherence_condition(frame_id: str, last_text: str) -> bool:
    """
    Evaluate the declarative coherence_avoid_if predicate on a frame.
    Returns True → the frame is incoherent in the current last_text context and should be replaced.
    """
    fr = _frames_by_id.get(frame_id) or {}
    predicate = (fr.get("coherence_avoid_if") or "").strip()
    if not predicate:
        return False
    entry = _COHERENCE_MARKERS.get(predicate)
    if not entry:
        return False
    t = last_text or ""
    avoid_hit = any(m in t for m in entry["avoid"])
    allow_hit = any(m in t for m in entry["allow"])
    return avoid_hit and not allow_hit


_HOBBY_TRAVEL_KEYWORDS: frozenset = frozenset([
    "旅行", "旅游", "环游", "出游", "游览", "出行", "旅程", "旅", "游玩", "背包",
    "travel", "travelling", "traveling",
])


def _hobby_is_travel(answer_text: str, memory: Optional[dict]) -> bool:
    """Return True if the disclosed hobby appears to be travel-related."""
    mem = memory or {}
    blob = f"{answer_text} {mem.get('hobby') or ''}".lower()
    return any(kw in blob for kw in _HOBBY_TRAVEL_KEYWORDS)


def _check_skip_condition(frame_id: str, context: dict) -> bool:
    """
    Evaluate the declarative skip_when predicate attached to a frame (from p2_frames.json).
    Returns True → the frame should be skipped in the current context.

    Supported predicates
    --------------------
    city_is_well_known  — city in {北京,上海,广州}  (skip "is it far?")
    city_is_familiar    — city in _FAMILIAR_PLACE_NAMES  (skip "what's special?")
    hobby_is_travel     — hobby answer contains travel keywords (skip location/travel sub-questions)
    """
    fr = _frames_by_id.get(frame_id) or {}
    predicate = (fr.get("skip_when") or "").strip()
    if not predicate:
        return False

    answer_text: str = context.get("answer_text") or ""
    memory: Optional[dict] = context.get("memory")

    if predicate == "city_is_well_known":
        return _should_skip_place_distance_question(answer_text, memory)

    if predicate == "city_is_familiar":
        mem = memory or {}
        blob = f"{answer_text} {mem.get('lives_in') or ''} {mem.get('hometown') or ''}"
        for fam in _FAMILIAR_PLACE_NAMES:
            if fam in blob:
                return True
        return False

    if predicate == "hobby_is_travel":
        return _hobby_is_travel(answer_text, memory)

    return False


def _should_skip_place_distance_question(answer_text: str, memory: Optional[dict]) -> bool:
    """Skip p2_pl_far when current living city is Beijing/Shanghai/Guangzhou."""
    mem = memory or {}
    city = (mem.get("lives_in") or "").strip()
    if not city:
        try:
            from learner_memory_capture import _extract_city_from_hanzi

            city = (_extract_city_from_hanzi(answer_text or "") or "").strip()
        except Exception:
            city = ""
    return bool(city) and city in _CITIES_SKIP_DISTANCE_ASK


def _city_seems_unfamiliar(answer_text: str, memory: Optional[dict]) -> bool:
    """True when the named place is likely unknown to a Chinese interlocutor (e.g. Dunedin, 丽江)."""
    mem = memory or {}
    blob = f"{answer_text or ''} {mem.get('lives_in') or ''} {mem.get('hometown') or ''}"
    if re.search(r"[A-Za-z]", blob):
        return True
    for fam in _FAMILIAR_PLACE_NAMES:
        if fam in blob:
            return False
    if re.search(r"住|在", answer_text or "") and len((answer_text or "").strip()) >= 2:
        return True
    return False


def _maybe_frame_order_priority(
    engine_id: str,
    chosen: Optional[str],
    recent: list,
    memory: Optional[dict],
    answer_text: str,
    last_answer_fid: str,
) -> Optional[str]:
    """Apply soft FRAME_ORDER, honouring declarative skip_when conditions from frame definitions."""
    if not chosen:
        return None
    skip_ctx = {"answer_text": answer_text, "memory": memory}
    return _frame_order_priority(engine_id, chosen, set(recent), recent, memory, skip_context=skip_ctx) or chosen


def _swap_place_like_if_unfamiliar_live_city(
    chosen: Optional[str],
    *,
    last_answer: Optional[dict],
    last_turn_was_answer: bool,
    memory: Optional[dict],
    recent: list,
) -> Optional[str]:
    """
    Safety-net final guard: if we still chose f_place_like_there right after 你现在住哪里？,
    prefer earlier frames that have not been skipped by their skip_when condition.
    This catches paths that do not pass through _maybe_frame_order_priority (e.g. _select_next_frame_ladder).
    """
    if not chosen or chosen != "f_place_like_there":
        return chosen
    if not last_turn_was_answer or not isinstance(last_answer, dict):
        return chosen
    lf = _normalize_frame_id((last_answer.get("frame_id") or "").strip())
    if lf != "frame.location.live_question":
        return chosen
    at = _answer_text_from_last_answer(last_answer) or ""
    recent_set = set(recent or [])
    recent_list = list(recent or [])
    skip_ctx = {"answer_text": at, "memory": memory}
    for candidate in ("p2_pl_far", "p2_pl_ext1"):
        if candidate in recent_set:
            continue
        if _check_skip_condition(candidate, skip_ctx):
            continue
        if not _frame_deps_satisfied(candidate, recent_set, recent_list):
            continue
        if memory is not None and _should_suppress_ask_frame(candidate, memory, recent_list, RECALL_INTERVAL_TURNS):
            continue
        return candidate
    return chosen


# ── Entity Follow-Up Chains (EFC) ──────────────────────────────────────────────
# When a user mentions a specific family member, the EFC chain asks follow-up
# questions about that specific person using a {ENTITY} slot filled at runtime.
# efc_order determines the sequence; efc_gate="prev_answer_affirmative" gates
# f_efc_family_child so it only fires after a "yes married" answer.
#
# Extensible: add hobby/food/place chains here later with no selector changes.

# Family member vocabulary for entity detection — ordered longest-first to avoid
# "妹" matching before "妹妹".
_FAMILY_MEMBER_VOCAB: list = [
    "哥哥", "弟弟", "姐姐", "妹妹",
    "爸爸", "妈妈", "爷爷", "奶奶", "外公", "外婆",
    "儿子", "女儿", "丈夫", "老公", "妻子", "老婆",
    "叔叔", "阿姨", "舅舅", "姑姑",
    "哥", "弟", "姐", "妹",
    "爸", "妈",
]

# Affirmative markers: used to gate f_efc_family_child after f_efc_family_married.
_AFFIRMATIVE_MARKERS: frozenset = frozenset({
    "结婚了", "结婚", "有", "是", "对", "是的", "是啊", "有啊", "有的",
    "当然", "嗯", "已经结婚", "成家了",
})

# EFC chain for family — ordered by efc_order.
_FAMILY_EFC_CHAIN: list = [
    "f_efc_family_work",
    "f_efc_family_age",
    "f_efc_family_where",
    "f_efc_family_married",
    "f_efc_family_child",   # gated: only after affirmative marriage answer
]
# Maximum EFC depth per entity before returning to the normal engine ladder.
MAX_EFC_DEPTH = 3

# When {ENTITY} must be substituted but efc_entity state is missing (should be rare after
# ladder excludes EFC frames). Use a kinship noun so templates like 你{ENTITY}多大了？ stay grammatical.
# ("他们" produced 你他们多大了？ — invalid.)
_ENTITY_SLOT_FALLBACK_ZH = "孩子"
_ENTITY_SLOT_FALLBACK_EN = "child"
_ENTITY_SLOT_FALLBACK_PY = "háizi"


def _detect_family_entity(text: str) -> Optional[str]:
    """Return the first family member term found in text, or None.

    Uses _FAMILY_MEMBER_VOCAB ordered longest-first so compound terms
    (哥哥) are matched before single characters (哥).
    """
    if not text:
        return None
    for term in _FAMILY_MEMBER_VOCAB:
        if term in text:
            return term
    return None


def _pick_efc_frame(
    entity_type: str,
    entity_value: str,
    recent_frame_ids: list,
    cs: dict,
) -> Optional[str]:
    """Select the next unseen EFC frame for the given entity.

    Returns the frame_id only; the caller fills {ENTITY} in the frame text.
    Returns None when chain is exhausted, depth cap reached, or entity missing.
    """
    if not entity_value or entity_type != "family":
        return None
    efc_depth = int(cs.get("efc_depth") or 0)
    if efc_depth >= MAX_EFC_DEPTH:
        return None
    recent = set(recent_frame_ids or [])
    last_answer_text = _norm_text(
        (cs.get("last_answer") or {}).get("submitted_text")
        or (cs.get("last_answer") or {}).get("selected_option_hanzi")
        or ""
    ) if isinstance(cs.get("last_answer"), dict) else ""
    last_frame_id = ((cs.get("last_answer") or {}).get("frame_id") or "").strip()

    for fid in _FAMILY_EFC_CHAIN:
        if fid in recent:
            continue
        fr = _frames_by_id.get(fid) or {}
        # Gate: f_efc_family_child only fires after an affirmative marriage answer.
        if fr.get("efc_gate") == "prev_answer_affirmative":
            if last_frame_id != "f_efc_family_married":
                continue
            if not any(m in last_answer_text for m in _AFFIRMATIVE_MARKERS):
                continue
        return fid
    return None


def _fill_efc_entity(frame_id: str, entity_value: str) -> Optional[str]:
    """Return the frame text with {ENTITY} replaced by entity_value.

    Returns None if the frame doesn't exist or has no {ENTITY} slot.
    """
    fr = _frames_by_id.get(frame_id) or {}
    text = (fr.get("text") or "").strip()
    if not text or "{ENTITY}" not in text:
        return None
    return text.replace("{ENTITY}", entity_value)


# Phase 12E: Curiosity probe frames — selected when interest_level is medium/high and
# slot followup preferences are exhausted. Ordered medium-interest first, high-interest last.
# interest_min: "medium" = fires on medium or high; "high" = fires only on high.
_CURIOSITY_PROBE_FRAMES: dict = {
    # Phase 12D Step 1: frames already in FRAME_ORDER removed — curiosity layer must be true extension.
    # Removed: f_probe_id_nickname (identity), f_probe_work_origin + f_probe_work_future (work),
    #          f_probe_family_closest (family), f_probe_hobby_origin + f_probe_hobby_social (hobby).
    "identity": [
        {"id": "f_probe_id_like_name",    "interest_min": "medium"},
        {"id": "f_probe_id_character",    "interest_min": "high"},
    ],
    "place": [
        {"id": "f_probe_place_moved",     "interest_min": "medium"},
        {"id": "f_probe_place_why_move",  "interest_min": "medium"},
        {"id": "f_probe_place_miss",      "interest_min": "medium"},
        {"id": "f_probe_place_stay",      "interest_min": "high"},
    ],
    "work": [
        # f_probe_work_role_detail fires on any interesting job disclosure ("what kind of work is that?")
        # before the linear frame sequence continues — works for any unusual role.
        {"id": "f_probe_work_role_detail", "interest_min": "medium"},
        {"id": "f_probe_work_dream",       "interest_min": "medium"},
        {"id": "f_probe_work_best",        "interest_min": "medium"},
    ],
    "food": [
        {"id": "f_probe_food_make",       "interest_min": "medium"},
        {"id": "f_probe_food_childhood",  "interest_min": "medium"},
        {"id": "f_probe_food_teach",      "interest_min": "high"},
    ],
    "family": [
        {"id": "f_probe_family_together", "interest_min": "medium"},
        {"id": "f_probe_family_influence","interest_min": "high"},
    ],
    "hobby": [
        {"id": "f_probe_hobby_change",    "interest_min": "medium"},
    ],
    "travel": [
        # f_probe_travel_alone removed: "你旅行的时候喜欢自己去还是跟人一起？" duplicates
        # f_travel_with_who ("你是跟谁一起去的？") in the core FRAME_ORDER.
        {"id": "f_probe_travel_why_fav",  "interest_min": "medium"},
        {"id": "f_probe_travel_meaning",  "interest_min": "high"},
    ],
}

# Phase 12E: keyword → targeted discovery question shown at the top of the discovery panel
# when the persona's counter_reply contains a recognisable topic keyword.
# Each entry: (keywords_tuple, zh_question, en_hint)
_DISCOVERY_KEYWORD_HINTS: list = [
    (("教书", "老师", "教学"),                       "你最喜欢教什么年级？",        "What grade do you most enjoy teaching?"),
    (("主厨", "厨师", "烹饪"),                       "你最擅长做什么菜？",          "What dish are you best at making?"),
    (("书法", "楷书", "毛笔"),                       "你练了多久了？",              "How long have you been practising?"),
    (("独生", "没有兄弟", "没有姐妹"),               "那你小时候怎么过的？",        "What was childhood like for you?"),
    (("兄弟", "哥哥", "弟弟", "姐姐", "妹妹"),      "你们感情好吗？",              "Are you close to your siblings?"),
    (("退休",),                                      "退休以后你最喜欢做什么？",    "What do you enjoy most since retiring?"),
    (("爬山", "登山"),                               "你经常去爬吗？",              "Do you go hiking often?"),
    (("羽毛球", "乒乓球", "网球"),                   "你打了多久了？",              "How long have you been playing?"),
    (("吉他", "钢琴", "小提琴"),                     "你是自学的还是拜师学的？",    "Did you teach yourself or take lessons?"),
    (("农村", "乡下", "村子"),                       "你怀念农村的生活吗？",        "Do you miss life in the countryside?"),
    (("外国", "海外", "国外", "出国"),               "你在那边住了多久？",          "How long did you live there?"),
    (("北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "西安", "武汉"),
                                                     "你最喜欢那里的什么？",        "What do you like most about there?"),
]


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


def _normalize_frame_id(fid: str) -> str:
    """Map legacy ids (word cards / old clients) to canonical p1 frame ids."""
    f = (fid or "").strip()
    if f == "f_live_where":
        return "frame.location.live_question"
    return f


def _infer_slot_names_from_answer(last_answer: Optional[dict]) -> List[str]:
    """Best-effort: infer slot names from the user's answer frame (question frame_id in last_answer)."""
    if not last_answer or not isinstance(last_answer, dict):
        return []
    # last_answer.frame_id is the partner ask frame the user answered (e.g. f_from_where)
    # selected option's card_id often points to a user frame with slots; try to infer via that mapping when possible.
    # We only have selected_option_hanzi/meaning here; so use memory capture triggers + known ask frame ids.
    fid = _normalize_frame_id((last_answer.get("frame_id") or "").strip())
    txt = _answer_text_from_last_answer(last_answer)

    slots: List[str] = []
    if fid in ("f_ask_you_name", "p2_id_2", "f_ask_name_meaning"):
        slots.append("NAME")
    if fid in ("f_what_work", "f_like_work", "p2_wk_1", "p2_wk_2", "p2_wk_3", "p2_wk_4", "p2_wk_5"):
        slots.append("JOB")
    # COMPANY: after the learner answers "which company do you work for?" with substantive content,
    # trigger the company-probe followup ("那家公司怎么样？"). Works for any org — Alibaba, Fujitsu,
    # a university, a school — not limited to foreign or well-known companies.
    if fid == "f_work_company" and txt and len(txt) >= 2:
        slots.append("COMPANY")
    if fid in ("f_food_what_good", "f_food_tasty", "f_food_like_spicy", "f_food_famous_dish", "f_food_expensive"):
        slots.append("DISH")
    if fid in ("f_travel_where", "f_want_go_where", "p2_tr_1", "p2_tr_2", "p2_tr_3", "p2_tr_4"):
        slots.append("TRAVEL")
    if fid in (
        "f_from_where",
        "frame.location.live_question",
        "p2_pl_1",
        "p2_pl_2",
        "p2_pl_3",
        "p2_pl_4",
        "p2_pl_far",
        "f_place_like_there",
        # NOTE: f_work_where is intentionally excluded. It used to tag CITY here but that
        # triggered the CITY slot-followup chain (_SLOT_FOLLOWUP_PREFERENCES["CITY"]),
        # which pulled in f_live_where (place engine) before work probe frames finished.
        # f_work_where now seeds "place" via _FRAME_ID_TO_SEED in _infer_cross_engine_seeds.
    ):
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


# Phase 12E refinement 1: novelty markers — simple rule-based, no AI.
# These indicate a genuinely new personal detail in the user's answer.
# Story/context connectors signal the user is sharing something personal, not just naming a fact.
_NOVELTY_STORY_MARKERS = (
    "以前", "从小", "记得", "那时候", "有一次", "小时候", "当时", "后来", "长大", "曾经",
)

# Notable job/role keywords: if a JOB slot answer contains any of these,
# award a novelty bonus so that unusual roles score HIGH interest instead of medium.
_JOB_NOTABLE_ROLE_MARKERS = (
    "首席", "总裁", "总经理", "副总", "总监", "经理", "主任", "主管",   # management
    "博主", "设计师", "艺术家", "创作者", "作家", "记者", "摄影师",       # creative
    "工程师", "程序员", "医生", "律师", "教授", "科学家", "研究员",         # professional
    "CEO", "CIO", "CTO", "CFO", "COO",                                   # C-suite
)
# Personal ownership + quantity markers: "我有", "我们有", plus any digit character.
_NOVELTY_OWNERSHIP_MARKERS = ("我有", "我们有", "我没有")
_DIGITS = set("0123456789零一二三四五六七八九十百千万")


def _score_answer_interest(
    last_answer: Optional[dict],
    slot_names: List[str],
    new_memory_written: bool,
    cs: dict,
) -> tuple:
    """Return (score: int, novelty_hit: bool) for interest classification.

    novelty_hit is True when the answer contains first-person story markers,
    ownership declarations, or specific numbers — signals of new personal detail.
    Kept as an explicit boolean for trace visibility.
    """
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
        recent_fids = cs.get("recent_frame_ids") or []
        last_fid = recent_fids[-1] if recent_fids else ""
        last_frame_text = (_frames_by_id.get(last_fid) or {}).get("text", "").strip()
        if "吗" in last_frame_text:
            score += 1  # "yes" to a yes/no question — probe for more
    prev = _norm_text(cs.get("last_user_text") if isinstance(cs, dict) else "")
    if text and prev and text == prev:
        score -= 1
    if text in ("好", "嗯", "不知道"):
        score -= 1

    # Phase 12E refinement 1: novelty signal.
    # A story/context connector or a specific quantity/ownership claim suggests the user
    # is sharing new personal information, not just repeating or confirming.
    # Rule: +1 if any novelty marker is present AND the answer is not identical to last turn.
    novelty_hit = False
    if text and text != prev:
        if any(m in text for m in _NOVELTY_STORY_MARKERS):
            novelty_hit = True
        elif any(m in text for m in _NOVELTY_OWNERSHIP_MARKERS):
            novelty_hit = True
        elif any(ch in _DIGITS for ch in text):
            novelty_hit = True
    if novelty_hit:
        score += 1

    # Notable job/role bonus: when the answer contains a specific, unusual job title
    # (CIO, blogger, designer, engineer…), award +1 so the role scores HIGH interest
    # instead of staying at medium. Only applied when JOB slot is already detected to
    # avoid false positives from keyword coincidences in other engines.
    if "JOB" in slot_names and text and any(m in text for m in _JOB_NOTABLE_ROLE_MARKERS):
        score += 1

    return max(0, score), novelty_hit


# Reasoning/meaning markers — if ANY of these appear in a HIGH-interest answer,
# the topic completion guard suppresses immediate bridge entry for that turn.
# The learner just said something substantial; let the conversation breathe.
_REASONING_DEPTH_MARKERS: tuple = (
    "因为", "所以", "觉得", "但是", "其实", "虽然", "不过", "而且",
    "对我来说", "最重要", "最喜欢", "从小", "以前", "那时候",
)


def _answer_has_reasoning_depth(answer_text: str) -> bool:
    """Return True if the answer contains explicit reasoning or personal meaning.

    Used by the topic completion guard: when the learner gives a deep, meaningful
    answer, suppress immediate new-engine bridge entry so the conversation can react
    and stay with the topic rather than jumping away.
    """
    t = (answer_text or "").strip()
    if not t or len(t) < 6:
        return False
    return any(m in t for m in _REASONING_DEPTH_MARKERS)


def _classify_interest(score: int) -> str:
    if score >= INTEREST_HIGH_THRESHOLD:
        return "high"
    if score >= INTEREST_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _decay_interest(interest_level: str, loop_count_in_engine: int) -> str:
    """Phase 12E refinement 2: decay interest by one level if the conversation has been
    looping in the same engine for >= LOOP_COUNT_IN_ENGINE_SOFT_CAP turns.

    This creates natural exit pressure without touching the global selector.
    Only used for curiosity decisions; raw interest_level is still used for
    listening moves and reaction selection.
    """
    if loop_count_in_engine < LOOP_COUNT_IN_ENGINE_SOFT_CAP:
        return interest_level
    if interest_level == "high":
        return "medium"
    if interest_level == "medium":
        return "low"
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


def _looks_like_place_distance_question(t: str) -> bool:
    """
    Learner small-talk about distance / never having been to a place
    (e.g. 远吗？ 离这儿远吗？ 从来没去过).
    """
    s = (t or "").strip()
    if not s:
        return False
    if "远吗" in s or "远不远" in s or "有多远" in s:
        return True
    if "多远" in s and len(s) <= 20:
        return True
    if "离" in s and "远" in s:
        return True
    if "从来没" in s and "去" in s:
        return True
    if "从没去过" in s:
        return True
    if "没去过" in s and len(s) < 40:
        return True
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
    # Definition / paraphrase (火锅是什么 / 这个词什么意思)
    if "是什么" in text or "什么意思" in text or text.startswith("什么叫") or "指的是什么" in text:
        return True
    # Learner home country — follow-up interest (NZ most interesting place, etc.)
    if "新西兰" in text and any(k in text for k in ("哪里", "最有", "最好", "好玩", "有趣", "特别")):
        return True
    # Place distance / never been — often no ？ (e.g. 从来没去过)
    if _looks_like_place_distance_question(text):
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

    # Age question — deflect gracefully rather than answering with name
    if fid in ("f_how_old",):
        return _persona_deflect("age", fid)

    # Marriage / children — always deflect
    if fid in ("f_married",):
        return _persona_deflect("marriage", fid)
    if fid in ("f_have_children",):
        return _persona_deflect("children", fid)

    # Name questions — build from profile when voice_line missing
    if fid in ("f_ask_you_name", "p2_id_2"):
        return voice_lines.get("identity") or (f"我叫{name}。" if name else None)

    # Where from — always built from profile hometown
    if fid in ("f_from_where",):
        hometown = (profile.get("hometown") or "").strip()
        return f"我是{hometown}人。" if hometown else voice_lines.get("place") or "我是中国人。"

    # Current location — built from profile city
    if fid in ("frame.location.live_question", "p2_pl_ext1", "p2_pl_1"):
        city = (profile.get("city") or "").strip()
        if city:
            return f"我现在住在{city}。"
        return voice_lines.get("place") or "我现在住在中国。"

    # Work — prefer occupation from profile
    if fid in ("f_what_work", "f_like_work"):
        occ = (profile.get("occupation") or "").strip()
        return voice_lines.get("work") or (f"我是{occ}。" if occ else None)

    # Hobbies — prefer interests list from profile
    if fid in ("f_what_hobby", "f_often_do", "f_like_do_what", "f_weekend_do"):
        interests = profile.get("interests") or []
        if voice_lines.get("hobby"):
            return voice_lines["hobby"]
        if interests:
            return f"我喜欢{interests[0]}。"

    # Food cross-topic frame (place engine, food topic) — use food voice_line
    if fid == "p2_pl_2":
        return voice_lines.get("food") or voice_lines.get("place")

    # Engine-level fallback: use the frame's own engine to pick the right voice_line.
    # Covers identity, work, place, food, family, travel, hobby, and any future engine.
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

    # Hobbies / interests — "你喜欢什么" alone is too broad (catches "你喜欢什么颜色？" etc.)
    # Require either 爱好 / 做什么 / 玩什么 to confirm it's asking about hobbies.
    if any(p in t for p in ("你有什么爱好", "你喜欢做什么", "你喜欢玩什么", "你的爱好", "你平时喜欢")):
        interests = profile.get("interests") or []
        return voice_lines.get("hobby") or (f"我喜欢{interests[0]}。" if interests else "我也有很多爱好。")

    # Who partner lives with (与谁住 / 跟谁住 phrasings — no 吗, no 你们住在一起 needed)
    if any(p in t for p in ("与谁住", "跟谁住", "和谁住", "与谁同住", "跟谁同住", "和谁同住")):
        return voice_lines.get("family") or "我现在自己住，但和家人经常联系。"

    # Family — has family / siblings
    if any(p in t for p in ("你有家人", "你有没有家人", "你的家人")):
        return voice_lines.get("family") or "我也有家人。"

    # Parent / family member location — e.g. "你妈妈在哪儿？" "你父母住哪里？"
    if any(p in t for p in ("你妈妈", "你爸爸", "你父母", "你爸妈", "你家人住", "你爸", "你妈")):
        city = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        lives_with_family = voice_lines.get("family") or ""
        if "住在一起" in lives_with_family or "同一" in lives_with_family:
            loc = city or hometown or "这里"
            return f"我和父母住在{loc}附近，很近。"
        if city:
            return f"我父母住在{city}。"
        if hometown:
            return f"我父母在{hometown}。"
        return "我父母住得不太远。"

    # City/place feature questions — e.g. "重庆有什么特别？" "西安有什么好玩？"
    # Detected when the user asks what's special/good about a city that matches the persona's city or hometown.
    _feature_markers = ("有什么特别", "有什么好玩", "有什么有意思", "有什么特色", "有什么好", "怎么样啊", "怎么样呢")
    if any(m in t for m in _feature_markers):
        fact_place = (_facts.get("place") or "").strip()
        if fact_place:
            return fact_place
        city = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        place_line = voice_lines.get("place") or ""
        loc = city or hometown
        if loc and loc in t:
            return f"哎，{loc}太有特色了，说也说不完！" if not place_line else place_line
        if place_line:
            return place_line
        return "哎，这个嘛……说来话长，有空再聊！"

    # Married / partner status — phrase from recovery_phrases.json (use=persona_deflect, topic=marriage)
    if any(p in t for p in ("你结婚", "你有没有结婚", "你有对象", "你有伴侣",
                             "你有男朋友", "你有女朋友", "你成家了")):
        return _persona_deflect("marriage", t)

    # Children — phrase from recovery_phrases.json (use=persona_deflect, topic=children)
    if any(p in t for p in ("你有孩子", "你有小孩", "你有儿子", "你有女儿", "你有宝宝")):
        return _persona_deflect("children", t)

    # Age — phrase from recovery_phrases.json (use=persona_deflect, topic=age)
    if any(p in t for p in ("你多大", "你几岁", "你的年龄", "你今年多大")):
        return _persona_deflect("age", t)

    # Bare 为什么 / 为啥 — follow-up to the partner's last statement (city, life, preference).
    # Without this, _answer_user_question_prefix falls through to _persona_deflect("generic")
    # and can surface 换个话题吧 mid-conversation (unnatural bridge).
    _ts = t.strip().rstrip("？?！!。，, ")
    if _ts in ("为什么", "为啥", "为啥呢", "为什么呢"):
        pool: list = []
        ht = (profile.get("hometown") or "").strip()
        if ht:
            pool.append(f"因为我在{ht}长大的，比较熟悉，也比较有感情。")
        if voice_lines.get("place"):
            pool.extend(
                [
                    "因为习惯了，也比较有感情。",
                    "因为节奏和生活方式都挺适合我。",
                ]
            )
        if voice_lines.get("work"):
            pool.append("因为我觉得很有意思，也比较适合我。")
        if voice_lines.get("food"):
            pool.append("因为口味很合我，吃惯了。")
        if not pool:
            pool = [
                "因为习惯了，也比较熟悉。",
                "因为我觉得挺合适的，慢慢就更喜欢了。",
            ]
        return _stable_pick(pool, f"why_bare|{_ts}|{ht}") or pool[0]

    # "Where has (long) history?" — rhetorical / place-culture; avoid generic deflect before EXTEND follow-ups.
    if "历史" in t and any(k in t for k in ("哪里", "哪儿", "什么地方")):
        ht = (profile.get("hometown") or "").strip()
        if ht:
            return f"像{ht}这样的地方，历史就很长。你慢慢会发现很多细节。"
        return "很多地方都有很长的历史，你慢慢看会发现很多细节。"

    return None


def _lexical_definition_reply(t: str) -> Optional[tuple]:
    """
    Short answers for vocabulary / place-interest questions so we don't fall through to
    _persona_deflect('generic') (which can surface 换个话题吧 mid-interest).
    """
    if not t:
        return None
    if "火锅" in t and ("是什么" in t or "什么意思" in t):
        return (
            "我呢，火锅就是一边煮一边吃的那种锅，重庆的很辣，很香。",
            "Hot pot is a simmering pot meal — spicy and fragrant in Chongqing.",
        )
    if "新西兰" in t and any(k in t for k in ("哪里", "最有", "最好", "好玩", "有趣", "特别")):
        return (
            "我呢，新西兰很美，每个地方都有自己的特点。你最喜欢哪一块？",
            "New Zealand is beautiful — which part do you like most?",
        )
    if "是什么" in t and len(t) <= 28:
        return (
            "我呢，我用简单一点说：你问的是哪一个词？",
            "Let me put it simply — which word do you mean?",
        )
    return None


def _is_confusion_signal(t: str) -> bool:
    """Learner signals they did not understand — not a new content question."""
    if not (t or "").strip():
        return False
    s = t.strip()
    if len(s) <= 2 and s in ("啊", "嗯", "呃", "哎", "噢", "哦"):
        return True
    # Avoid matching 是什么 / 哪里好玩 (genuine questions)
    if "是什么" in s or re.search(r"新西兰|哪里.*好玩|哪里.*有趣|哪里.*特别", s):
        return False
    markers = (
        "啊？", "啊！", "我不懂", "有点不懂", "听不懂", "没听懂", "没懂", "不明白",
        "看不懂", "什么意思", "没太懂", "再说一遍", "慢一点", "慢一",
    )
    return any(m in s for m in markers)


def _confusion_recovery_reply(t: str, prev_zh: str, seed: str = "") -> Optional[tuple]:
    """
    After we already gave a counter_reply, learner still confused — give a shorter repair line
    instead of repeating the same voice-line paragraph or returning None (which let the frame loop).
    """
    if not (t or "").strip() or not (prev_zh or "").strip():
        return None
    if not _is_confusion_signal(t):
        return None
    pool = [
        (
            "好呢，我可能说得太快了。我再说短一点：重点是吃的和路——你想先听哪一个？",
            "I may have been too fast. Shorter version: food or the place — which first?",
        ),
        (
            "嗯，我慢一点。刚才那句话，你可以理解成：我说的是家乡的地形和吃的东西。",
            "Let me slow down — I was talking about the landscape and the food back home.",
        ),
        (
            "哦，我换个说法：不着急，我们一步一步来。你先告诉我，你哪一句没听懂？",
            "Let me rephrase — no rush. Which sentence was unclear?",
        ),
        (
            "好呢，我用更简单的词：山城就是很多坡；火锅是一种很辣的锅子。",
            "Simpler words: mountain city means lots of hills; hot pot is a spicy pot meal.",
        ),
    ]
    idx = sum(ord(c) for c in (seed + prev_zh + t)) % len(pool)
    return pool[idx]


def _place_distance_counter_reply(t: str, persona: Optional[dict]) -> Optional[tuple]:
    """
    Acknowledge distance / never-been and pivot to 特色 or 喜欢那儿 — natural small talk
    when discussing new countries or cities.
    """
    if not _looks_like_place_distance_question(t):
        return None
    profile = (persona or {}).get("profile") or {}
    ht = (profile.get("hometown") or "").strip()
    pool = [
        (
            "嗯，是挺远的。不过每个地方都有自己的特点。你觉得那儿有什么特色？",
            "Yeah, it's quite far. But every place has its own character. What do you think is special about it?",
        ),
        (
            "听起来不近。那你喜欢在那儿生活吗？",
            "Sounds far. Do you enjoy living there?",
        ),
        (
            "地理上确实挺远的。不过你最喜欢那儿什么？",
            "Geographically it's rather far. What do you like most about it?",
        ),
    ]
    seed = f"pd|{t}|{ht}"
    i = _stable_gate(seed) % len(pool)
    zh, en = pool[i]
    zh_out = f"我呢，{zh}" if not zh.startswith(("我", "嗯")) else zh
    return (zh_out, en)


def _answer_user_question_prefix(last_answer: Optional[dict], persona: Optional[dict]) -> Optional[tuple]:
    """
    Return (zh, en) answering common counter-questions without adding new API turns.
    Handles: mirror questions (richest), direct persona questions, generic 你呢, catch-all deflection.
    Returns None if last answer was not a question.
    Lexical definition and confusion-after-counter are resolved in the run_turn caller first.
    """
    if not _is_user_question(last_answer):
        return None
    t = (last_answer.get("submitted_text") or last_answer.get("selected_option_hanzi") or "").strip()
    if not t:
        return None
    # Normalise formal 您 → informal 你 so all downstream pattern checks (mirror bank,
    # _direct_persona_answer substrings, etc.) work without duplicating every entry.
    t = t.replace("您", "你")

    # Mirror questions (richest answers — use discoverable_facts / profile via _mirror_persona_stub)
    _mirror = _find_mirror_answer(t, "", persona)
    if _mirror:
        return (_mirror[0], _mirror[1])   # return (zh, en); topic/engine handled by caller state-write

    _dist = _place_distance_counter_reply(t, persona)
    if _dist:
        return _dist

    # Direct questions aimed at the partner (你是哪里人？ 你住哪里？ etc.)
    _direct = _direct_persona_answer(t, persona)
    if _direct:
        zh = f"我呢，{_direct}" if not _direct.startswith("我") else _direct
        en = _en_for_counter_reply(zh, _direct) or _voice_line_en_for_zh(persona, _direct)
        return (zh, en)

    # Generic 你呢 — whether standalone or at end of a compound answer
    _ni_ne_markers = ("你呢", "那你呢", "你怎么想", "为什么这么问", "为什么这样问", "换我问", "你来问")
    _has_ni_ne = any(m in t for m in _ni_ne_markers)
    if _has_ni_ne:
        fid = _normalize_frame_id((last_answer.get("frame_id") or "").strip())
        reply = _persona_reply_for_ni_ne(fid, persona)
        if reply:
            zh = f"我呢，{reply}" if not reply.startswith("我呢") else reply
            return (zh, _en_for_counter_reply(zh, reply))
        _frame_eng = (_frames_by_id.get(fid) or {}).get("engine") or ""
        _generics: dict = {
            "identity": None,
            "place":    "我也住在中国，挺喜欢的。",
            "work":     "我也有工作，还挺有意思的。",
            "hobby":    "我也有几个爱好，有空会聊。",
            "family":   "我也有家人，关系挺好的。",
            "food":     "我也很喜欢吃东西，尤其是家乡菜。",
            "travel":   "我也旅行过几个地方，很有意思。",
        }
        _gen = _generics.get(_frame_eng.lower())
        if _gen:
            return (f"我呢，{_gen}", "")
        an = _assistant_name_from_persona(persona)
        if an and an != "MandarinOS":
            return (f"我呢，你可以叫我{an}。", "")
        return ("我呢，这是个好问题。", "")

    # Catch-all: user asked a question we don't have a specific answer for.
    zh = _persona_deflect("generic", t)
    return (zh, _persona_deflect_en(zh))


# ---------------------------------------------------------------------------
# Sentence-level response options — loaded from content/response_patterns.json
# Ordering is preserved by array position in the JSON file.
# ---------------------------------------------------------------------------
def _load_sentence_option_patterns():
    import pathlib as _pl, json as _json
    _data_path = _pl.Path(__file__).resolve().parent.parent / "content" / "response_patterns.json"
    try:
        _raw = _json.loads(_data_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(
            f"[MandarinOS] response_patterns.json not found at {_data_path}. "
            "Re-run extraction or restore from version control."
        )
    except _json.JSONDecodeError as exc:
        raise RuntimeError(
            f"[MandarinOS] response_patterns.json is malformed: {exc}"
        )
    # Minimal schema sanity check
    if not isinstance(_raw.get("patterns"), list):
        raise RuntimeError("[MandarinOS] response_patterns.json: 'patterns' must be a list")
    if not isinstance(_raw.get("generic_fallback"), list):
        raise RuntimeError("[MandarinOS] response_patterns.json: 'generic_fallback' must be a list")
    for idx, entry in enumerate(_raw["patterns"]):
        if "key" not in entry or "options" not in entry:
            raise RuntimeError(
                f"[MandarinOS] response_patterns.json: pattern[{idx}] missing 'key' or 'options'"
            )
    _patterns = [(e["key"], e["options"]) for e in _raw["patterns"]]
    _generic  = _raw["generic_fallback"]
    return _patterns, _generic


_SENTENCE_OPTION_PATTERNS, _SENTENCE_OPTIONS_GENERIC = _load_sentence_option_patterns()



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
    Phase 12E: chain cap is now interest-sensitive (high=4, medium=2, low=0).
    """
    # Phase 12B/12E: suppress if probe depth limit reached (cap scales with interest)
    _chain_cap = _max_curiosity_cap_for_interest(interest_level)
    if _chain_cap == 0 or int(cs.get("probe_depth") or 0) >= _chain_cap:
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


def _pick_reaction_text(
    engine_id: str,
    seed: str,
    *,
    interest_level: str = "low",
    exchange_count: int = 0,
    recent_reactions: Optional[List[str]] = None,
    _trace: Optional[dict] = None,
) -> str:
    """Return a short stance/reaction phrase for the given interest level.

    Strategic review (Apr 2026): this is the STANCE slot only — acknowledgment/echo
    is now handled separately. Deduplication via recent_reactions exclusion prevents
    the same phrase repeating within a session.

    When _trace is provided (a mutable dict), populates:
      pool_before, pool_after, filter_applied, interest_class
    """
    engine_norm = (engine_id or "").strip().lower()
    _cx_min = 3 if engine_norm == "identity" else 0
    _use_curiosity = interest_level in ("medium", "high") and exchange_count >= _cx_min
    if _use_curiosity:
        seq = list(_CURIOSITY_REACTIONS_BY_ENGINE.get(engine_norm) or _CURIOSITY_REACTIONS_GENERIC)
    else:
        seq = list(_REACTION_FALLBACKS_BY_ENGINE.get(engine_norm) or _REACTION_FALLBACKS_GENERIC)
    _pool_before = len(seq)
    # Deduplication: remove recently used reactions from the pool so the same phrase
    # doesn't repeat. Relax gracefully if exclusion would empty the pool.
    _filter_applied = False
    if recent_reactions and len(seq) > len(recent_reactions):
        _filtered = [r for r in seq if r not in recent_reactions]
        if _filtered:
            seq = _filtered
            _filter_applied = True
    _pool_after = len(seq)
    if _trace is not None:
        _trace["pool_before"] = _pool_before
        _trace["pool_after"] = _pool_after
        _trace["filter_applied"] = _filter_applied
        _trace["interest_class"] = "curiosity" if _use_curiosity else "fallback"
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


def _pick_closing_reaction(seed: str) -> tuple:
    """Deterministically pick a closing reaction tuple (hanzi, pinyin, english) from the pool."""
    return _stable_pick(_CLOSING_REACTIONS, seed) or _CLOSING_REACTIONS[0]


# Cross-engine slot-within-engine followup:
# When a slot from another engine is detected in the current engine, try these
# within-current-engine frames instead of jumping to the foreign engine's frames.
# This keeps the conversation in-engine while still being responsive to what the
# learner just said. The cross-engine slot is also seeded for future bridging.
#
# Structure: { (slot_name, current_engine_norm): [frame_id, ...] }
_CROSS_ENGINE_SLOT_WITHIN_ENGINE: dict = {
    # CITY disclosed while in WORK engine (e.g. "I work in Sydney") →
    # ask where work is based, not where the learner lives (place engine).
    ("CITY", "work"):    ["f_work_where"],
    # TRAVEL disclosed while in HOBBY engine (e.g. "my hobby is travel") →
    # use the hobby-travel frame rather than jumping to the travel engine.
    ("TRAVEL", "hobby"): ["f_hobby_travel"],
    # CITY disclosed while in TRAVEL engine (e.g. "I've been to Paris") →
    # ask about travel destination via travel engine frame, not place engine.
    ("CITY", "travel"):  ["f_travel_special"],
    # FAMILY disclosed while in WORK engine (e.g. "my wife works there too") →
    # no within-engine alternative exists; ladder takes over.
}

# Engines that should observe a minimum dwell count before accepting a transition
# from a given source engine via ANY route (slot followup or bridge).
# Format: { (from_engine, to_engine): min_same_engine_chain_count }
_ENGINE_TRANSITION_MIN_DWELL: dict = {
    ("work", "place"):   3,   # must have 3+ work turns before transitioning to place
    ("family", "place"): 2,
}


def _cross_engine_transition_blocked(
    from_engine: str,
    to_engine: str,
    same_engine_chain_count: int,
) -> bool:
    """Return True if transitioning from from_engine to to_engine is not yet allowed
    because the minimum dwell count in from_engine has not been reached.

    Only applies when the two engines differ. Used as a narrow post-selection guard
    after bridge or slot-followup returns a candidate — does NOT change bridge internals.
    """
    from_n = (from_engine or "").strip().lower()
    to_n   = (to_engine   or "").strip().lower()
    if from_n == to_n or not from_n or not to_n:
        return False
    min_dwell = _ENGINE_TRANSITION_MIN_DWELL.get((from_n, to_n))
    if min_dwell is None:
        return False
    return same_engine_chain_count < min_dwell


def _pick_slot_followup_frame_id(
    engine_id: str,
    slot_names: List[str],
    recent_frame_ids: list,
    memory: Optional[dict],
    exchange_count: int = 0,
    answer_text: str = "",
    last_answer_fid: str = "",
    same_engine_chain_count: int = 0,
    _trace: Optional[dict] = None,
) -> Optional[str]:
    """Try slot/topic follow-up frames before generic ladder; avoid weak loop frames if possible.

    Engine lock (Apr 2026): only frames whose 'engine' field matches current engine_id are
    returned. Cross-engine slots are handled via _CROSS_ENGINE_SLOT_WITHIN_ENGINE (same-engine
    alternative) or silently deferred to the bridge queue. This prevents slot detection from
    causing implicit engine switches outside bridge control.

    When _trace is provided (mutable dict), increments _trace['engine_lock_blocked'] for
    each cross-engine frame that was rejected.
    """
    recent = set(recent_frame_ids or [])
    engine_norm = (engine_id or "").strip().lower()
    _NAME_DEEP_FOLLOWUP_MIN_EXCHANGES = 3
    _name_deep_followups = frozenset({"f_name_who_named", "p2_id_4", "p2_id_5", "f_name_story_elicit"})

    skip_ctx = {"answer_text": answer_text or "", "memory": memory}

    def _candidate_ok(fid: str, count_cross_engine_block: bool = False) -> bool:
        """Shared eligibility checks for any candidate frame."""
        if fid in recent:
            return False
        if _check_skip_condition(fid, skip_ctx):
            return False
        if fid in _name_deep_followups and exchange_count < _NAME_DEEP_FOLLOWUP_MIN_EXCHANGES:
            return False
        if memory is not None and _should_suppress_ask_frame(fid, memory, recent_frame_ids or [], RECALL_INTERVAL_TURNS):
            return False
        fr = _frames_by_id.get(fid) or {}
        if "？" not in (fr.get("text") or ""):
            return False
        # Engine lock: only return frames that belong to the current engine.
        # Frames with no 'engine' field (e.g. generic probes) are always allowed.
        frame_engine = (fr.get("engine") or "").strip().lower()
        if frame_engine and frame_engine != engine_norm:
            if count_cross_engine_block and _trace is not None:
                _trace["engine_lock_blocked"] = _trace.get("engine_lock_blocked", 0) + 1
            return False
        return True

    for s in slot_names or []:
        # Step A: within-engine override for cross-engine slots (e.g. CITY in WORK → f_work_where)
        # Dedup rules: same as _candidate_ok — already_asked (in recent), recent_frame
        # (_should_suppress_ask_frame), and all other eligibility checks all apply.
        # The trace records why each alt was blocked so the conversation can be audited.
        within_engine_alts = _CROSS_ENGINE_SLOT_WITHIN_ENGINE.get((s, engine_norm)) or []
        if within_engine_alts and _trace is not None:
            _trace["cross_engine_alt_considered"] = True
        for fid in within_engine_alts:
            # Dedup check 1: frame was already shown to the learner at any point this session.
            if fid in recent:
                if _trace is not None and _trace.get("cross_engine_alt_blocked_reason") is None:
                    _trace["cross_engine_alt_blocked_reason"] = "already_asked"
                continue
            # Dedup check 2: memory-based recall suppression (asked too recently).
            if memory is not None and _should_suppress_ask_frame(fid, memory, recent_frame_ids or [], RECALL_INTERVAL_TURNS):
                if _trace is not None and _trace.get("cross_engine_alt_blocked_reason") is None:
                    _trace["cross_engine_alt_blocked_reason"] = "recent_frame"
                continue
            # All remaining eligibility checks (skip_when, question guard, engine check).
            if not _candidate_ok(fid):
                if _trace is not None and _trace.get("cross_engine_alt_blocked_reason") is None:
                    _trace["cross_engine_alt_blocked_reason"] = "no_candidate"
                continue
            # Alt is eligible — use it.
            if _trace is not None:
                _trace["cross_engine_alt_used"] = fid
                _trace["cross_engine_alt_blocked_reason"] = None
            return fid
        # If alts existed but all were blocked, record no_candidate if nothing more specific was set.
        if within_engine_alts and _trace is not None and _trace.get("cross_engine_alt_blocked_reason") is None:
            _trace["cross_engine_alt_blocked_reason"] = "no_candidate"

        # Step B: standard slot preferences — engine-locked to current engine
        prefs = _SLOT_FOLLOWUP_PREFERENCES.get(s) or []
        ordered = [f for f in prefs if f not in _WEAK_LOOP_FRAME_IDS] + [f for f in prefs if f in _WEAK_LOOP_FRAME_IDS]
        for fid in ordered:
            if _candidate_ok(fid, count_cross_engine_block=True):
                return fid
    return None


def _pick_curiosity_probe_frame(
    engine_id: str,
    interest_level: str,
    memory: Optional[dict],
    recent_frame_ids: list,
) -> Optional[str]:
    """Phase 12E: select a curiosity-deepening probe frame for the current engine.

    Returns the first unseen probe frame whose interest_min requirement is met.
    Falls back to None if no viable frame exists, so normal ladder logic still runs.
    """
    if interest_level not in ("medium", "high"):
        return None
    recent = set(recent_frame_ids or [])
    engine_norm = (engine_id or "").strip().lower()
    candidates = _CURIOSITY_PROBE_FRAMES.get(engine_norm) or []
    for entry in candidates:
        fid = entry["id"]
        if fid in recent:
            continue
        if entry.get("interest_min") == "high" and interest_level != "high":
            continue
        return fid
    return None


# Food curiosity probes — incoherent right after place/affect turns (homesickness, scenery) without food in the answer.
_FOOD_COHERENCE_PROBES: frozenset = frozenset({"f_probe_food_make", "f_probe_food_childhood", "f_probe_food_teach"})
# Place turns where a food "自己做 / 小时候吃吗" probe feels like a non sequitur.
_PLACE_AFFECT_CONTEXT_FRAMES: frozenset = frozenset(
    {
        "f_probe_place_miss",
        "f_probe_place_why_move",
        "f_probe_place_moved",
        "p2_pl_ext1",
        "f_place_why_like",
        "f_place_like_there",
        "f_from_where",
        "frame.location.live_question",
        "f_live_where",
    }
)
# After learner signals confusion/skip, avoid jumping to food-heavy place loops.
_LEARNER_SKIP_AVOID_FRAMES: frozenset = frozenset({"p2_pl_2", *tuple(_FOOD_COHERENCE_PROBES)})
_LEARNER_SKIP_PREFER_PLACE: tuple = ("p2_pl_1", "p2_pl_4", "f_probe_place_moved", "f_probe_place_stay", "p2_pl_3")


def _place_thread_for_food_guard(cs: dict, last_fid: str) -> bool:
    """True if the user was answering a place/affect frame — even when last_answer.frame_id is empty."""
    if last_fid in _PLACE_AFFECT_CONTEXT_FRAMES:
        return True
    lpf = (cs.get("last_partner_frame_id") or "").strip()
    if lpf in _PLACE_AFFECT_CONTEXT_FRAMES:
        return True
    recent = cs.get("recent_frame_ids") or []
    if recent:
        tail = (recent[-1] or "").strip()
        if tail in _PLACE_AFFECT_CONTEXT_FRAMES:
            return True
    return False


def _apply_discourse_coherence_guard(
    chosen: Optional[str],
    *,
    cs: dict,
    recent: list,
    last_answer: Optional[dict],
    last_turn_was_answer: bool,
    learner_skip_confusion: bool,
    memory: Optional[dict],
) -> Optional[str]:
    """Swap incoherent next-frame picks (food probe after place emotion; food after learner skip)."""
    if not chosen or not _frames_by_id:
        return chosen
    recent_set = set(recent or [])
    recent_list = list(recent or [])

    def _deps_ok(fid: str) -> bool:
        return _frame_deps_satisfied(fid, recent_set, recent_list) and (
            memory is None or not _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS)
        )

    last_fid = ""
    last_text = ""
    if last_turn_was_answer and isinstance(last_answer, dict):
        last_fid = _normalize_frame_id((last_answer.get("frame_id") or "").strip())
        last_text = _answer_text_from_last_answer(last_answer) or ""
    if not last_fid:
        last_fid = (cs.get("last_partner_frame_id") or "").strip()

    # 1) Learner pressed "我不明白" skip — stay in place; don't open with {CITY}有什么好吃的 or cooking probes.
    if learner_skip_confusion and chosen in _LEARNER_SKIP_AVOID_FRAMES:
        eng = (cs.get("current_engine") or "").strip().lower()
        if eng == "place":
            for alt in _LEARNER_SKIP_PREFER_PLACE:
                if alt == chosen:
                    continue
                if alt not in recent_set and alt in _frames_by_id and _deps_ok(alt):
                    return alt
        for alt in ("p2_pl_1", "p2_pl_4"):
            if alt not in recent_set and alt in _frames_by_id and _deps_ok(alt):
                return alt

    # 2) Food probe after place/affect context — user wasn't talking about food.
    if chosen in _FOOD_COHERENCE_PROBES and _place_thread_for_food_guard(cs, last_fid):
        if _looks_food_related_answer(last_text) or ("吃" in last_text and len(last_text) <= 24):
            return chosen
        for alt in (
            "f_probe_place_stay",
            "f_probe_place_moved",
            "f_probe_place_why_move",
            "f_probe_place_miss",
            "p2_pl_1",
            "p2_pl_4",
        ):
            if alt in recent_set or alt not in _frames_by_id:
                continue
            if _deps_ok(alt):
                return alt
        # First list exhausted (long place threads) — any unseen place curiosity probe
        for entry in _CURIOSITY_PROBE_FRAMES.get("place", []):
            alt = (entry.get("id") or "").strip()
            if not alt or alt in recent_set or alt not in _frames_by_id:
                continue
            if _deps_ok(alt):
                return alt
        # Still on a cooking probe after pure place/history talk — advance in place (or bridge non-food)
        # instead of "你会自己做吗？" non sequiturs.
        _ex = int(cs.get("exchange_count") or 0)
        _ev = list(cs.get("engines_visited") or [])
        cand = _select_next_frame_ladder_avoiding(
            "place",
            recent_list,
            avoid_frame_ids=_WEAK_LOOP_FRAME_IDS | _FOOD_COHERENCE_PROBES,
            memory=memory,
            exchange_count=_ex,
            engines_visited=_ev,
        )
        if cand:
            _eng = ((_frames_by_id.get(cand) or {}).get("engine") or "").strip().lower()
            if _eng != "food" and cand not in _FOOD_COHERENCE_PROBES:
                return cand
        # Place ladder often bridges to food first (place→food in _BRIDGE_TARGETS). Skip food here.
        cand_br = _select_next_frame_bridge(
            "place",
            recent_list,
            memory=memory,
            exchange_count=_ex,
            engines_visited=_ev,
            exclude_engine_norms=frozenset({"food"}),
        )
        if cand_br and cand_br not in _FOOD_COHERENCE_PROBES:
            _eng2 = ((_frames_by_id.get(cand_br) or {}).get("engine") or "").strip().lower()
            if _eng2 != "food":
                return cand_br

    # 3) Declarative coherence_avoid_if check — works for any frame that declares one in p2_frames.json.
    if last_text and _check_coherence_condition(chosen, last_text):
        _coh_eng = ((_frames_by_id.get(chosen) or {}).get("engine") or "place")
        alt = _select_next_frame_ladder_avoiding(
            _coh_eng, recent_list,
            avoid_frame_ids=_WEAK_LOOP_FRAME_IDS | {chosen},
            memory=memory,
            exchange_count=cs.get("exchange_count") or 0,
        )
        if alt and _deps_ok(alt):
            return alt

    return chosen


def _pick_contextual_discovery_hint(counter_reply: str) -> Optional[dict]:
    """Phase 12E: return one targeted follow-up question based on keywords in the persona's reply.

    Used to prepend a specific question to the discovery panel rather than only showing
    generic engine mirror questions. Returns None if no keyword matches.
    """
    if not counter_reply:
        return None
    for keywords, zh_q, en_hint in _DISCOVERY_KEYWORD_HINTS:
        if any(kw in counter_reply for kw in keywords):
            return {"zh": zh_q, "en": en_hint, "targeted": True}
    return None


def _max_curiosity_cap_for_interest(interest_level: str) -> int:
    """Phase 12E: return max consecutive curiosity depth allowed for this interest level.

    high   → up to 4 consecutive probe turns before forcing a bridge
    medium → 2 (matches existing MAX_CURIOSITY_DEPTH baseline)
    low    → 0, suppress probes even if depth counter is below cap
    """
    if interest_level == "high":
        return 4
    if interest_level == "medium":
        return MAX_CURIOSITY_DEPTH
    return 0


def _is_loop_candidate(frame_id: str) -> bool:
    """Heuristic: treat selected P2 follow-ups and some engine follow-ups as loop-capable."""
    if not frame_id:
        return False
    return frame_id.startswith("p2_") or frame_id.startswith("f_probe_") or frame_id in ("f_food_like_spicy", "f_food_tasty", "p2_pl_4")


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


# Mirror questions bank — loaded from content/mirror_questions.json at startup.
# This alias keeps all downstream code unchanged; add/edit questions in the JSON file only.
_MIRROR_QUESTIONS_BY_ENGINE: dict = _mirror_questions_raw

# ── Core mirror entries: derived from partner frames via content/mirror_core_map.json ────────────
# Prepended before discovery entries so pedagogically-aligned core questions appear first.
# Fails loudly if a mapped frame_id is missing or slotted — no silent drift.
_core_mirror_map_path = CONTENT_DIR / "mirror_core_map.json"
try:
    if _core_mirror_map_path.is_file():
        _cm_raw = json.loads(_core_mirror_map_path.read_text(encoding="utf-8"))
        _core_by_engine: dict = {}
        for _cm_entry in (_cm_raw.get("core_entries") or []):
            _cm_fid   = _cm_entry.get("frame_id", "")
            _cm_topic = _cm_entry.get("topic", "")
            if not _cm_fid or not _cm_topic:
                continue
            _cm_fr = _frames_by_id.get(_cm_fid)
            if not _cm_fr:
                raise RuntimeError(
                    f"[MandarinOS] mirror_core_map: frame_id '{_cm_fid}' not found in frames_by_id. "
                    "Update mirror_core_map.json or restore the frame."
                )
            if _cm_fr.get("slots"):
                raise RuntimeError(
                    f"[MandarinOS] mirror_core_map: frame_id '{_cm_fid}' has slots — "
                    "slotted frames cannot be used as core mirror entries."
                )
            _cm_eng = (_cm_fr.get("engine") or "").strip().lower()
            if not _cm_eng:
                continue
            _core_by_engine.setdefault(_cm_eng, []).append({
                "zh":    _cm_fr["text"],
                "py":    _cm_fr.get("pinyin", ""),
                "en":    _cm_fr.get("text_en", ""),
                "topic": _cm_topic,
                "kind":  "SENTENCE",
            })
        # Merge: core first, then discovery. Deduplicate by topic (core wins).
        # Paraphrases on removed discovery entries are inherited onto the matching core entry
        # so _MIRROR_FUZZY continues to resolve legacy fuzzy inputs unchanged.
        for _cm_eng, _cm_core_qs in _core_by_engine.items():
            _cm_discovery = _MIRROR_QUESTIONS_BY_ENGINE.get(_cm_eng) or []
            _cm_core_idx: dict = {q["topic"]: q for q in _cm_core_qs if q.get("topic")}
            _cm_deduped_discovery = []
            _cm_removed = 0
            for _cm_q in _cm_discovery:
                _cm_t = _cm_q.get("topic")
                if _cm_t and _cm_t in _cm_core_idx:
                    # Inherit any paraphrases from the removed discovery entry
                    for _ph in (_cm_q.get("paraphrases") or []):
                        _cm_core_idx[_cm_t].setdefault("paraphrases", [])
                        if _ph not in _cm_core_idx[_cm_t]["paraphrases"]:
                            _cm_core_idx[_cm_t]["paraphrases"].append(_ph)
                    _cm_removed += 1
                else:
                    _cm_deduped_discovery.append(_cm_q)
            if _cm_removed:
                print(f"[ui_server] mirror_core_map: removed {_cm_removed} duplicate discovery "
                      f"entry/entries from engine '{_cm_eng}' (topic overlap with core; paraphrases inherited)")
            _MIRROR_QUESTIONS_BY_ENGINE[_cm_eng] = _cm_core_qs + _cm_deduped_discovery
        _cm_n = sum(len(v) for v in _core_by_engine.values())
        print(f"[ui_server] mirror_core_map loaded ({_cm_n} core entries across {len(_core_by_engine)} engines)")
    else:
        print(f"[ui_server] INFO: mirror_core_map.json not found at {_core_mirror_map_path} — using discovery bank only")
except RuntimeError:
    raise
except Exception as _cm_e:
    raise RuntimeError(f"[MandarinOS] mirror_core_map load failed: {_cm_e}") from _cm_e

# Fuzzy-match table built from optional 'paraphrases' arrays in the JSON bank.
# Each entry: (keyword_tuple, topic, engine). Matching: all keywords must be present in input.
# To add a paraphrase variant, add it to the JSON entry — no Python edit required.
_MIRROR_FUZZY: list = [
    (tuple(kw_group), q["topic"], eng)
    for eng, qs in _MIRROR_QUESTIONS_BY_ENGINE.items()
    for q in qs
    for kw_group in (q.get("paraphrases") or [])
    if q.get("topic")
]


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


def _mirror_persona_stub(topic: str, engine_id: str, persona: Optional[dict]) -> tuple:
    """Persona's answer to a learner's mirror question. Returns (zh, en) tuple."""
    if not persona:
        return ("我觉得都挺有意思的。", "")
    facts      = persona.get("discoverable_facts") or {}
    facts_en   = persona.get("discoverable_facts_en") or {}
    vl         = persona.get("voice_lines") or {}
    vl_en      = persona.get("voice_lines_en") or {}
    profile    = persona.get("profile") or {}
    name       = _assistant_name_from_persona(persona)
    city_home  = (profile.get("hometown") or profile.get("city") or "").strip()

    def _fact_en(engine_key: str) -> str:
        return (facts_en.get(engine_key) or "").strip()

    def _vl_en(engine_key: str) -> str:
        return (vl_en.get(engine_key) or "").strip()

    # ── Identity / name ─────────────────────────────────────────────────────────
    if topic in ("name_what", "name_nickname", "name_meaning", "name_story", "name_giver"):
        fact = (facts.get("identity") or "").strip()
        if topic == "name_what":
            # Direct answer to "你叫什么名字？" — return the persona's name sentence
            zh = vl.get("identity") or f"我叫{name}。"
            return (zh, _vl_en("identity") or f"My name is {name}.")
        if topic == "name_nickname":
            # Answer to "朋友一般怎么叫你？" — how friends address the persona
            zh = f"大家都叫我{name}，没有什么特别的外号。"
            en  = f"Everyone calls me {name} — no special nickname."
            return (zh, en)
        if topic == "name_giver":
            depth = _nth_clause(fact, 1) if fact else ""
            return (depth or "是我父母给我取的名字。", "")
        if topic == "name_story":
            depth = _nth_clause(fact, 2) if fact else ""
            return (depth or "我的名字有一点意思，是家里人取的，有机会再跟你说。", "")
        zh = _first_clause(fact) if fact else f"我叫{name}，这个名字是家人给取的，我觉得挺好的。"
        return (zh, _fact_en("identity"))

    # ── Food ────────────────────────────────────────────────────────────────────
    if topic in ("food_fav", "food_local", "food_spicy"):
        fact = (facts.get("food") or "").strip()
        if topic == "food_local":
            depth = _nth_clause(fact, 1) if fact else ""
            return (depth or "我家乡的菜也很有特色，有机会试试。", "")
        if fact:
            return (_first_clause(fact), _fact_en("food"))
        fav = profile.get("favourite_food") or ""
        zh = f"我最喜欢吃{fav}。" if fav else "我喜欢吃各种东西，很难只选一个。"
        return (zh, _fact_en("food"))

    # ── Place ────────────────────────────────────────────────────────────────────
    if topic == "place_live_now":
        city_now = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        if city_now and hometown and city_now != hometown:
            zh = f"我现在住在{city_now}，不是我老家，是来这里工作的。"
            en = f"I live in {city_now} now — not my hometown, I came here for work."
        elif city_now:
            zh = f"我现在住在{city_now}。"
            en = f"I live in {city_now} now."
        else:
            zh = vl.get("place") or "我住在这里已经好几年了。"
            en = _vl_en("place")
        return (zh, en)

    if topic == "place_hometown":
        city_home2 = (profile.get("hometown") or "").strip()
        city_now2  = (profile.get("city") or "").strip()
        if city_home2 and city_now2 and city_home2 != city_now2:
            zh = f"我老家是{city_home2}，不过现在在{city_now2}工作。"
            en = f"My hometown is {city_home2} — but I work in {city_now2} now."
        elif city_home2:
            zh = f"我老家就是{city_home2}，从小在那里长大。"
            en = f"My hometown is {city_home2} — I grew up there."
        else:
            zh = vl.get("place") or "我老家在中国，有机会去看看！"
            en = _vl_en("place")
        return (zh, en)

    if topic in ("place_from", "place_like", "place_special", "place_far", "place_far_or_not", "place_never_been"):
        fact = (facts.get("place") or "").strip()
        if topic == "place_special":
            zh = _first_clause(fact) if fact else "那里有一些很有意思的地方，有机会去看看。"
            return (zh, _fact_en("place"))
        if topic == "place_from":
            zh = f"我是{city_home}人，从小在那里长大。" if city_home else (vl.get("place") or "我是中国人。")
            en = f"I'm from {city_home} — I grew up there." if city_home else _vl_en("place")
            return (zh, en)
        if topic == "place_like":
            zh_vl = vl.get("place") or ""
            if zh_vl:
                return (zh_vl, _vl_en("place"))
            zh = f"挺喜欢的，{city_home}有很多有意思的地方。" if city_home else "挺喜欢的，有很多有意思的地方。"
            en = f"I quite like it — there's a lot to see in {city_home}." if city_home else "I quite like it — there's a lot to see."
            return (zh, en)
        if topic in ("place_far", "place_far_or_not", "place_never_been"):
            zh = f"从这里到{city_home}不算远，交通也方便。" if city_home else "不算太远，我去过几次。"
            en = f"Not too far from here to {city_home} — easy enough to get there." if city_home else "Not too far — I've been there a few times."
            return (zh, en)
        zh = _first_clause(fact) if fact else (f"我是{city_home}人，从小在那里长大。" if city_home else "我觉得我住的地方挺好的。")
        return (zh, _fact_en("place"))

    # ── Travel ───────────────────────────────────────────────────────────────────
    if topic in ("travel_where", "travel_fav", "travel_memorable", "travel_with"):
        fact = (facts.get("travel") or "").strip()
        if topic == "travel_memorable":
            parts = re.split(r'[，、,]', fact)
            depth = parts[-1].strip().rstrip("。.") + "。" if parts and len(parts) > 1 else ""
            return (depth or "最难忘的是在一个很偏远的地方看星星那一晚。", "")
        if topic == "travel_with":
            specific = (facts.get("travel_with") or "").strip()
            return (specific or "一般跟朋友或者家人一起。", _fact_en("travel_with"))
        zh = _first_clause(fact) if fact else "我去过几个城市，最喜欢有美食的地方。"
        return (zh, _fact_en("travel"))

    # ── Work ─────────────────────────────────────────────────────────────────────
    if topic in ("work_what", "work_like", "work_duration", "work_platform", "work_company", "work_origin"):
        fact = (facts.get("work") or "").strip()
        if topic == "work_like":
            zh_vl = vl.get("work") or ""
            return (zh_vl or "挺喜欢的，虽然有时候很忙。", _vl_en("work"))
        if topic == "work_duration":
            depth = _nth_clause(fact, 1) if fact else ""
            return (depth or "已经做了几年了，越做越有意思。", "")
        if topic == "work_platform":
            depth = _nth_clause(fact, 1) if fact else ""
            return (depth or "我在网上分享，有一些人关注。", "")
        if topic == "work_company":
            specific = (facts.get("work_company") or "").strip()
            return (specific or "我在一家挺不错的公司工作。", _fact_en("work_company"))
        if topic == "work_origin":
            specific = (facts.get("work_origin") or "").strip()
            return (specific or "大学毕业后就开始做这个，慢慢越来越喜欢。", _fact_en("work_origin"))
        if fact:
            return (_first_clause(fact), _fact_en("work"))
        job = profile.get("occupation") or ""
        zh = f"我做{job}，还挺有意思的。" if job else "我的工作挺有意思，可以学很多东西。"
        return (zh, _fact_en("work"))

    # ── Family ───────────────────────────────────────────────────────────────────
    if topic in ("family_size", "family_siblings", "family_live"):
        # Per-topic key first — authoritative, avoids fragile clause-index extraction.
        # Fallback to clause-extraction only for personas that don't have the specific key yet.
        if topic == "family_siblings":
            specific = (facts.get("family_siblings") or "").strip()
            if specific:
                return (specific, _fact_en("family_siblings"))
            fact = (facts.get("family") or "").strip()
            depth = _nth_clause(fact, 1) if fact else ""
            return (depth or "我家里就我一个，是独生子女。", "")
        if topic == "family_live":
            specific = (facts.get("family_live") or "").strip()
            if specific:
                return (specific, _fact_en("family_live"))
            fact = (facts.get("family") or "").strip()
            depth = _nth_clause(fact, 0) if fact else ""
            return (depth or "我们不住在一起，但经常联系。", _fact_en("family"))
        # family_size
        specific = (facts.get("family_size") or "").strip()
        if specific:
            return (specific, _fact_en("family_size"))
        fact = (facts.get("family") or "").strip()
        zh = _first_clause(fact) if fact else "我家里有几口人，大家关系都挺好的。"
        return (zh, _fact_en("family"))

    # ── Hobby ────────────────────────────────────────────────────────────────────
    if topic in ("hobby_what", "hobby_duration", "hobby_best", "hobby_origin"):
        fact = (facts.get("hobby") or "").strip()
        if topic == "hobby_duration":
            depth = _nth_clause(fact, 1) if fact else ""
            return (depth or "已经玩了好几年了，越来越喜欢。", "")
        if topic == "hobby_best":
            specific = (facts.get("hobby_best") or "").strip()
            return (specific or "最喜欢的感觉是完全投入进去，什么都不用想。", _fact_en("hobby_best"))
        if topic == "hobby_origin":
            specific = (facts.get("hobby_origin") or "").strip()
            return (specific or "从小就开始喜欢了，一直坚持到现在。", _fact_en("hobby_origin"))
        if fact:
            return (_first_clause(fact), _fact_en("hobby"))
        interests = profile.get("interests") or []
        zh = f"我喜欢{interests[0]}，有空就去。" if interests else "我有几个爱好，平时很忙，但一有时间就会去做。"
        return (zh, _fact_en("hobby"))

    # ── Topics that are always graceful deflections (no discoverable fact) ────────
    if topic in ("age", "marriage", "children"):
        zh = _persona_deflect(topic, engine_id)
        return (zh, _persona_deflect_en(zh))

    return ("我觉得都挺有意思的。", "")


def _topic_to_fact_key(topic: str) -> str:
    """Map a mirror topic string to its discoverable_facts key.
    Topics that share a parent fact key (e.g. name_what / name_meaning → 'identity') are mapped here.
    Topics that have their own dedicated key return that key directly.
    """
    _map: dict[str, str] = {
        "name_what":       "identity",
        "name_nickname":   "identity",
        "name_meaning":    "identity",
        "name_story":      "identity",
        "name_giver":      "identity",
        "food_fav":        "food",
        "food_local":      "food",
        "food_spicy":      "food",
        "place_from":      "place",
        "place_like":      "place",
        "place_special":   "place",
        "place_far":       "place",
        "place_far_or_not":"place",
        "place_never_been":"place",
        "place_live_now":  "place",
        "place_hometown":  "place",
        "travel_where":    "travel",
        "travel_fav":      "travel",
        "travel_memorable":"travel",
        "travel_with":     "travel_with",
        "work_what":       "work",
        "work_like":       "work",
        "work_duration":   "work",
        "work_platform":   "work",
        "work_company":    "work_company",
        "work_origin":     "work_origin",
        "hobby_what":      "hobby",
        "hobby_duration":  "hobby",
        "hobby_best":      "hobby_best",
        "hobby_origin":    "hobby_origin",
        "family_size":     "family_size",
        "family_siblings": "family_siblings",
        "family_live":     "family_live",
    }
    return _map.get(topic, topic)


# Restatement prefixes used in Stage 1 (natural restatement, not simplification).
# Picked deterministically by topic hash so the same persona doesn't always use the same prefix.
_RESTATE_PREFIXES = [
    "我再说一遍——",
    "换个说法——",
    "我的意思是——",
    "我再说清楚一点——",
    "简单来说——",
]


def _mirror_persona_stub_simple(topic: str, engine_id: str, persona: Optional[dict]) -> tuple:
    """
    Shorter/simpler restatement of a persona mirror answer — for Stage 2 confusion repair only.
    Priority:
      1. discoverable_facts_simple[fact_key] — author-written simplified version
      2. voice_lines[engine] — already short, persona-specific
      3. Generic per-engine fallback
    """
    if not persona:
        return ("我的意思很简单——都挺好的。", "Simply put — it's all pretty good.")
    facts_simple    = persona.get("discoverable_facts_simple") or {}
    facts_simple_en = persona.get("discoverable_facts_simple_en") or {}
    vl              = persona.get("voice_lines") or {}
    vl_en           = persona.get("voice_lines_en") or {}
    eng             = (engine_id or "").strip().lower()
    key             = _topic_to_fact_key(topic)

    if facts_simple.get(key):
        return (facts_simple[key], facts_simple_en.get(key, ""))

    # Voice line is already short — use as simplified fallback
    if vl.get(eng):
        return (vl[eng], vl_en.get(eng, ""))

    # Generic per-engine fallback
    _generic: dict[str, tuple] = {
        "work":     ("我的工作很简单——上班、做事。", "My work is simple — just show up and do it."),
        "hobby":    ("我喜欢一件事，每天都做。", "I enjoy one thing and do it every day."),
        "travel":   ("我去过几个地方，很喜欢旅行。", "I've been to a few places — I enjoy travelling."),
        "place":    ("我住在中国，喜欢我住的地方。", "I live in China and like where I am."),
        "identity": ("我的名字很简单。", "My name is simple."),
        "food":     ("我喜欢吃好吃的。", "I enjoy good food."),
        "family":   ("我家里有几个人。", "There are a few people in my family."),
    }
    return _generic.get(eng, ("我的意思很简单。", "Simply put."))


def _mirror_restate_naturally(prev_zh: str, topic: str) -> tuple:
    """
    Stage 1 repair: restate the original mirror answer with a natural lead-in prefix.
    Preserves listening practice value — does NOT simplify the content.
    """
    if not prev_zh:
        return ("我刚才说的是——请再听一遍。", "Let me say that again.")
    prefix_idx = sum(ord(c) for c in topic) % len(_RESTATE_PREFIXES)
    prefix = _RESTATE_PREFIXES[prefix_idx]
    return (f"{prefix}{prev_zh}", f"Let me rephrase — {prev_zh}")


def _find_mirror_answer(text: str, engine_id: str, persona: Optional[dict]) -> Optional[tuple]:
    """
    Check if the user's submitted text closely matches one of the mirror discovery questions.
    Returns (zh, en, topic, engine) 4-tuple so callers can track state for repair escalation.
    Falls through to None so callers can chain with _direct_persona_answer.
    """
    t_norm = (text or "").strip().rstrip("？?！!。，, ").replace("您", "你")
    for eng, questions in _MIRROR_QUESTIONS_BY_ENGINE.items():
        for q in questions:
            zh_norm = (q.get("zh") or "").rstrip("？?！!。，, ")
            if not zh_norm:
                continue
            # Match if submitted text contains or equals the canonical question
            if zh_norm in t_norm or t_norm == zh_norm:
                topic = q.get("topic") or ""
                resolved_eng = eng or engine_id
                zh, en = _mirror_persona_stub(topic, resolved_eng, persona)
                return (zh, en, topic, resolved_eng)

    # Fuzzy-match paraphrase variants registered in mirror_questions.json ('paraphrases' arrays).
    # Table is built at startup into _MIRROR_FUZZY — no Python edit required to add new variants.
    for keywords, topic, eng in _MIRROR_FUZZY:
        if all(kw in t_norm for kw in keywords):
            zh, en = _mirror_persona_stub(topic, eng, persona)
            return (zh, en, topic, eng)

    return None


def _direction_stub(intent: str, engine_id: str, last_partner_frame_id: str, persona: Optional[dict]) -> str:
    """Short partner stub for direction actions (reverse/why), then client resumes thread."""
    eng = (engine_id or "").strip().lower()
    fid = (last_partner_frame_id or "").strip()
    if intent == "reverse":
        # Use the persona's voice_line for the current engine — no hard-coded per-engine strings.
        vl = ((persona or {}).get("voice_lines") or {})
        base = vl.get(eng) or None
        if base:
            return base if base.startswith("我呢") else f"我呢，{base}"
        if eng == "identity":
            name = _assistant_name_from_persona(persona)
            return f"我呢，我叫{name}。" if name else "我呢，也差不多。"
        return "我呢，也差不多。"
    if intent == "why":
        # Read partner_why_answer from the frame definition — no hard-coded frame-ID checks.
        fr = _frames_by_id.get(fid) or {}
        why = (fr.get("partner_why_answer") or "").strip()
        if why:
            return why
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
    exclude_engine_norms: Optional[set] = None,
    seeded_bridge_engines: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Phase 9.2: bridge to another engine. Only used after MIN_TURNS_BEFORE_BRIDGE turns in current engine.
    Prefers partner-question frames so the next line is a question, not a reactive phrase.
    When use_recovery_order is True (e.g. after 我不懂 or Change topic), try engines in _RECOVERY_BRIDGE_ENGINE_ORDER
    so the next question is a more natural switch (place/identity/family) rather than jumping to food/travel.
    Phase 11.1: skips identity OPEN frames (e.g. f_ask_you_name) once session is established (exchange_count ≥ 2).
    Phase 12C: engines_visited (session-level list) — unvisited engines are tried before already-visited ones.
    Phase 13B: seeded_bridge_engines — engines seeded by learner disclosures are tried first, making
    bridges follow the conversational thread rather than a fixed priority list.
    exclude_engine_norms: optional set of engine ids (e.g. {"food"}) to skip when bridging (discourse coherence).
    """
    recent = set(recent_frame_ids or [])
    engine_norm = (current_engine or "").strip().lower()

    if use_recovery_order:
        base_targets = [e for e in _RECOVERY_BRIDGE_ENGINE_ORDER if (e or "").strip().lower() != engine_norm]
    else:
        base_targets = _BRIDGE_TARGETS.get(engine_norm) or []

    # Phase 13B: seeded engines (from learner disclosures) take priority over the static list.
    # A seed that is also in base_targets keeps its seeded position; others are appended after.
    if seeded_bridge_engines and not use_recovery_order:
        _seeded_norm = [e for e in seeded_bridge_engines if e and e != engine_norm]
        _base_set = set(_seeded_norm)
        targets = _seeded_norm + [e for e in base_targets if e not in _base_set]
    else:
        targets = base_targets

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
        # Only apply LRU sort to unseeded portion — preserve seeded order.
        if seeded_bridge_engines and not use_recovery_order:
            _seeded_set = {e for e in seeded_bridge_engines if e and e != engine_norm}
            _unseeded = [e for e in targets if e not in _seeded_set]
            _unseeded_sorted = sorted(_unseeded, key=_recent_rank)
            targets = [e for e in targets if e in _seeded_set] + _unseeded_sorted
        else:
            targets = sorted(targets, key=_recent_rank)  # least recently used first
    # Phase 12C: prefer engines not yet visited in this session (avoids returning to exhausted topics).
    # Split targets into unvisited-first, then already-visited, preserving LRU order within each group.
    # Phase 13B: seeded engines keep their position regardless of visited status — the learner
    # explicitly disclosed a topic that deserves follow-up, even if that engine was visited before.
    if engines_visited:
        _visited_set = {(e or "").strip().lower() for e in engines_visited}
        _visited_set.discard(engine_norm)  # current engine is already excluded from targets
        _seeded_set_v12c = (
            {e for e in seeded_bridge_engines if e and e != engine_norm}
            if (seeded_bridge_engines and not use_recovery_order)
            else set()
        )
        _seeded_portion   = [t for t in targets if (t or "").strip().lower() in _seeded_set_v12c]
        _unseeded_portion = [t for t in targets if (t or "").strip().lower() not in _seeded_set_v12c]
        _unvisited_unseeded = [t for t in _unseeded_portion if (t or "").strip().lower() not in _visited_set]
        _visited_unseeded   = [t for t in _unseeded_portion if (t or "").strip().lower() in _visited_set]
        targets = _seeded_portion + _unvisited_unseeded + _visited_unseeded
    exclude = set(exclude_engine_norms or ())
    # De-emphasise food until the place-food opener (p2_pl_2) has been asked — place→food was first in bridge order.
    if engine_norm == "place" and not _place_food_topic_primed(recent_list):
        exclude.add("food")
    for target_engine in targets:
        target_norm = (target_engine or "").strip().lower()
        if target_norm == engine_norm:
            continue
        if target_norm in exclude:
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


def _select_non_loop_unseen_same_engine(
    current_engine: str,
    recent_frame_ids: list,
    *,
    memory: Optional[dict] = None,
    exchange_count: int = 0,
) -> Optional[str]:
    """
    Phase 12C overload: prefer a fresh same-engine question that is not a LOOP-style follow-up
    before bridging away — reduces surprise topic jumps while the learner is still confused.
    """
    recent = set(recent_frame_ids or [])
    engine_norm = (current_engine or "").strip().lower()
    same_engine = _engine_partner_question_frame_ids(engine_norm) or _engine_frame_ids(engine_norm)
    if not same_engine:
        return None
    recent_list = list(recent_frame_ids or [])

    def _deps_satisfied(fid: str) -> bool:
        return _frame_deps_satisfied(fid, recent, recent_list)

    def _not_suppressed(fid: str) -> bool:
        if memory is None:
            return True
        return not _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS)

    _open_excl = _IDENTITY_OPEN_FRAMES if exchange_count >= 2 else frozenset()

    def _not_mutually_excluded(fid: str) -> bool:
        excl = _MUTUAL_EXCLUSION_FRAMES.get(fid) or set()
        return not (excl & recent)

    unseen_non_loop = [
        fid for fid in same_engine
        if fid not in recent
        and fid not in _open_excl
        and _deps_satisfied(fid)
        and _not_suppressed(fid)
        and _not_mutually_excluded(fid)
        and not _is_loop_candidate(fid)
    ]
    if not unseen_non_loop:
        return None
    unseen_non_loop = sorted(
        unseen_non_loop,
        key=lambda fid: int((_frames_by_id.get(fid) or {}).get("difficulty") or 2),
    )
    return unseen_non_loop[0]


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
    skip_context: Optional[dict] = None,
) -> Optional[str]:
    """
    Phase 11.1: soft FRAME_ORDER enforcement.
    If chosen_fid is later in FRAME_ORDER than some unseen, dep-satisfied frame, return that
    earlier frame instead. Returns None when chosen is already optimal or not in FRAME_ORDER.

    skip_context: optional dict passed to _check_skip_condition for declarative skip_when logic.
    """
    order = _FRAME_ORDER.get((engine or "").strip().lower()) or []
    if not order or chosen_fid not in order:
        return None
    chosen_pos = order.index(chosen_fid)
    if chosen_pos == 0:
        return None
    ctx = skip_context or {}
    for fid in order[:chosen_pos]:
        if fid in recent_set:
            continue
        if not _frame_deps_satisfied(fid, recent_set, recent_list):
            continue
        if memory and _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS):
            continue
        if _check_skip_condition(fid, ctx):
            continue
        # Phase 12D: respect mutual exclusion — don't reinstate an earlier frame if its
        # semantic equivalent has already been shown (e.g. don't reopen f_food_available
        # after f_food_famous was chosen via slot followup).
        _excl = _MUTUAL_EXCLUSION_FRAMES.get(fid) or set()
        if _excl & recent_set:
            continue
        return fid
    return None


# ── Optional: line gloss (zh→en) for transcript when frame/cards omit text_en ─────────────
_GLOSS_CACHE: dict = {}
_GLOSS_CACHE_MAX = 600


def _gloss_translate_zh_to_en(text: str) -> Optional[str]:
    """Best-effort machine translation for transcript lines. Requires `deep-translator` (pip)."""
    t = (text or "").strip()
    if not t or len(t) > 900:
        return None
    if t in _GLOSS_CACHE:
        return _GLOSS_CACHE[t]
    if not re.search(r"[\u4e00-\u9fff]", t):
        return t
    try:
        from deep_translator import GoogleTranslator

        out = GoogleTranslator(source="zh-CN", target="en").translate(t)
        if out and str(out).strip():
            s = str(out).strip()
            if len(_GLOSS_CACHE) >= _GLOSS_CACHE_MAX:
                _GLOSS_CACHE.clear()
            _GLOSS_CACHE[t] = s
            return s
    except Exception as e:
        print(f"[ui_server] gloss: deep_translator unavailable or failed: {e}", flush=True)
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

        if path == "/api/gloss":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(body)
            except Exception:
                payload = {}
            q = (payload.get("q") or payload.get("text") or "").strip()
            en = _gloss_translate_zh_to_en(q) if q else None
            result = {"ok": bool(en), "en": en or ""}
            data = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

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
                    stub_result = _mirror_persona_stub(topic, engine_id, persona)
                    stub, stub_en = stub_result if isinstance(stub_result, tuple) else (stub_result, "")
                else:
                    stub = _direction_stub(direction_intent, engine_id, last_partner_frame_id, persona)
                    stub_en = ""

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
                    "frame_text_en": stub_en,
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
            # EFC: defaults so response assembly never references undefined names when
            # next_question is false (e.g. frame loaded from dropdown only).
            cs = None
            _efc_entity_state: dict = {}

            # Phase 9.1/9.2: next_question + conversation_state → selector; prefer_bridge/force_bridge try bridge first
            if payload.get("next_question") and isinstance(payload.get("conversation_state"), dict):
                cs = payload["conversation_state"]
                current_engine = cs.get("current_engine")
                recent = cs.get("recent_frame_ids") or []
                prefer_bridge = cs.get("prefer_bridge") is True
                force_bridge = cs.get("force_bridge") is True
                # Learner said e.g. "我不明白" and advanced — don't treat as bridge intent.
                if cs.get("learner_skip_confusion") is True:
                    prefer_bridge = False
                    force_bridge = False
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
                # Phase 13B: response-seeded bridge queue — accumulated from learner disclosures.
                seeded_bridge_engines: List[str] = list(cs.get("seeded_bridge_engines") or [])
                # Medium-path probe control: engines where a medium-triggered probe already fired.
                # At most 1 medium probe per engine; tracked across turns via client round-trip.
                medium_probe_fired_engines: List[str] = list(cs.get("medium_probe_fired_engines") or [])
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
                    fid = _normalize_frame_id((last_answer.get("frame_id") or "").strip())
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
                last_answer_fid = (
                    _normalize_frame_id((last_answer.get("frame_id") or "").strip())
                    if last_turn_was_answer and isinstance(last_answer, dict)
                    else ""
                )
                answer_text = _answer_text_from_last_answer(last_answer) if last_turn_was_answer else ""
                force_food_followup = last_turn_was_answer and (not user_asked_question) and (
                    last_answer_fid == "p2_pl_2" or _looks_food_related_answer(answer_text)
                )
                if force_food_followup and "DISH" not in slot_names:
                    slot_names = ["DISH"] + slot_names
                    meaningful = True
                unscripted_probe_first = last_turn_was_answer and (not user_asked_question) and _is_unscripted_substantive_answer(last_answer, slot_names)
                weak_reply = last_turn_was_answer and len(answer_text) <= 2
                # Phase 13B: accumulate seeded bridge engines from this turn's disclosures.
                if last_turn_was_answer and answer_text:
                    _new_seeds = _infer_cross_engine_seeds(slot_names, answer_text, current_engine, last_fid=last_answer_fid)
                    if _new_seeds:
                        seeded_bridge_engines = _merge_seeded_engines(
                            _new_seeds, seeded_bridge_engines, current_engine
                        )
                # EFC: detect family entity from current answer; persist across turns via state.
                _efc_entity_value = _detect_family_entity(answer_text) if last_turn_was_answer else None
                # If no new entity detected, carry the one from previous turns.
                _efc_entity_state = cs.get("efc_entity") or {} if isinstance(cs, dict) else {}
                if _efc_entity_value:
                    _efc_entity_state = {"type": "family", "value": _efc_entity_value}
                _efc_active = bool(_efc_entity_state.get("value"))
                interest_score = 0
                interest_level = "low"
                _interest_novelty_hit = False
                _interest_initial_level = "low"
                _interest_decayed_level = "low"
                if last_turn_was_answer:
                    interest_score, _interest_novelty_hit = _score_answer_interest(last_answer, slot_names, new_memory_written, cs)
                    interest_level = _classify_interest(interest_score)
                    _interest_initial_level = interest_level
                    # One-turn resilience: if previous turn was interesting but this answer is short,
                    # try one more curiosity move before exiting the topic.
                    if weak_reply and (last_interest_level in ("medium", "high")) and interest_level == "low":
                        interest_level = "medium"
                        interest_score = max(interest_score, INTEREST_MEDIUM_THRESHOLD)
                        _interest_initial_level = interest_level
                    # Phase 12E refinement 2: decay interest if looping in same engine too long.
                    # Decayed level is used only for curiosity decisions; raw level drives everything else.
                    _loop_count_in_engine = int(cs.get("same_engine_chain_count") or 0)
                    _interest_decayed_level = _decay_interest(interest_level, _loop_count_in_engine)
                    last_interest_level = interest_level
                    if interest_level in ("medium", "high") and (not user_asked_question):
                        pending_listening_move = True
                        listening_wait_turns = 0

                # Reaction micro-layer: we cannot emit two separate partner turns without changing API.
                # So when reaction triggers, we optionally prepend a short reaction phrase to the next question's text.
                reaction_prefix_text = ""
                reaction_used_fallback = False
                # Load deduplication state: last 2 reaction texts used this session.
                _recent_reactions: List[str] = list(cs.get("recent_reactions") or [])
                # Default traces — overwritten if their respective code paths run this turn.
                _sel_trace: dict = {"final_frame_source": "not_computed"}
                # Closing move guards — set inside the selection block; defaulted here so the
                # closing-move check at the end of selection is always safe to reference.
                _late_session_mode = False
                _topic_completion_suppresses_bridge = False
                # Reaction trace — captures both slots and composition decision.
                _rxn_trace: dict = {
                    "ack_slot": False,
                    "ack_slot_trigger": None,
                    "stance_slot": False,
                    "stance_slot_reason": None,
                    "pool_before": None,
                    "pool_after": None,
                    "filter_applied": False,
                    "composition_mode": "none",
                }
                # Spec §3: after ANY user answer, bias to reaction (not only when "meaningful").
                if last_turn_was_answer:
                    # Include last_answer_fid in seed for more entropy — avoids hash collision
                    # when the same engine is active across consecutive turns with similar exchange counts.
                    seed = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}/{last_answer_fid}"
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
                                    reaction_prefix_text = _pick_reaction_text(current_engine, seed, interest_level=interest_level, exchange_count=exchange_count, recent_reactions=_recent_reactions, _trace=_rxn_trace)
                                    reaction_used_fallback = True
                                else:
                                    reaction_prefix_text = (_frames_by_id.get(rid) or {}).get("text") or ""
                            else:
                                reaction_prefix_text = _pick_reaction_text(current_engine, seed, interest_level=interest_level, exchange_count=exchange_count, recent_reactions=_recent_reactions, _trace=_rxn_trace)
                                reaction_used_fallback = True
                            if reaction_prefix_text and interest_level in ("medium", "high"):
                                _rxn_trace["stance_slot"] = True
                                _rxn_trace["stance_slot_reason"] = f"interest={interest_level}"

                # ── Two-slot reaction model (Strategic review Apr 2026) ────────────────────────
                # Slot 1 — Acknowledgment (ECHO): fires when a salient named entity is disclosed.
                # Slot 2 — Stance (REACTION): fires when the answer is interesting (medium/high).
                # Composition policy:
                #   salient slot + HIGH interest + fallback stance → echo + stance (combined)
                #   salient slot + other cases             → echo only
                #   no salient slot                        → stance only (kept from above)
                # ─────────────────────────────────────────────────────────────────────────────
                _echo_candidate = ""
                _salient_slots_for_echo = {"CITY", "JOB", "COMPANY", "DISH", "TRAVEL", "NAME"}
                _echo_triggered_by: Optional[str] = None
                if last_turn_was_answer and any(s in slot_names for s in _salient_slots_for_echo):
                    _submitted_raw = (last_answer.get("submitted_text") or "").strip() if isinstance(last_answer, dict) else ""
                    # Strip ALL trailing punctuation so echo never ends with "。！" or "，！"
                    _submitted = _submitted_raw.rstrip("。，！？、…·\u3002\uff0c\uff01\uff1f.!?, ")
                    _mem = memory or {}
                    if "CITY" in slot_names:
                        # Echo must match what the user *just* said. Origin answers (f_from_where)
                        # update hometown; lives_in may still be the earlier city — prefer hometown
                        # so "我是新西兰人" echoes 新西兰, not 苏州 from 我现在住在苏州。
                        if last_answer_fid == "f_from_where":
                            _city = (_mem.get("hometown") or _mem.get("lives_in") or "").strip()
                        else:
                            _city = (_mem.get("lives_in") or _mem.get("hometown") or "").strip()
                        if not _city and _submitted:
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
                            _echo_triggered_by = "CITY"
                    elif "NAME" in slot_names and exchange_count <= 3:
                        _name = (_mem.get("learner_name") or "").strip()
                        if _name and len(_name) <= 6:
                            _echo_candidate = f"{_name}！"
                            _echo_triggered_by = "NAME"
                    elif "DISH" in slot_names and _submitted and len(_submitted) <= 8:
                        _echo_candidate = f"哦，{_submitted}！"
                        _echo_triggered_by = "DISH"
                    elif "TRAVEL" in slot_names and _submitted and len(_submitted) <= 8:
                        _echo_candidate = f"哦，{_submitted}！"
                        _echo_triggered_by = "TRAVEL"
                    elif "COMPANY" in slot_names:
                        _co = (_mem.get("job_company") or _mem.get("company") or "").strip()
                        if not _co and _submitted and 2 <= len(_submitted) <= 12:
                            _co = _submitted
                        if _co and len(_co) <= 12:
                            _echo_candidate = f"哦，{_co}！"
                            _echo_triggered_by = "COMPANY"
                    elif "JOB" in slot_names:
                        _job = (_mem.get("job") or _mem.get("occupation") or "").strip()
                        if not _job and _submitted:
                            for _patt in ("是一名", "当一名", "是个", "当个", "做", "当"):
                                _pi = _submitted.find(_patt)
                                if _pi >= 0:
                                    _frag = _submitted[_pi + len(_patt):].rstrip("。，！？的 ")
                                    if 2 <= len(_frag) <= 8:
                                        _job = _frag
                                        break
                            if not _job and 2 <= len(_submitted) <= 8:
                                _job = _submitted
                        if _job and len(_job) <= 10:
                            _echo_candidate = f"哦，{_job}！"
                            _echo_triggered_by = "JOB"
                    # Normalise: strip stray punctuation then ensure closing ！
                    if _echo_candidate:
                        _echo_candidate = _echo_candidate.rstrip("。，！？.!?,\u3002\uff0c\uff01\uff1f") + "！"

                # Compose the final reaction_prefix_text using the two-slot policy.
                if _echo_candidate:
                    _rxn_trace["ack_slot"] = True
                    _rxn_trace["ack_slot_trigger"] = _echo_triggered_by
                    # For HIGH interest with a fallback stance reaction, combine both.
                    # Brevity guard (B): cap combined prefix at 16 Chinese chars.
                    # If exceeded, fall back to echo only to keep the opening short.
                    if (
                        interest_level == "high"
                        and reaction_prefix_text
                        and reaction_used_fallback
                    ):
                        _combined = _echo_candidate + reaction_prefix_text
                        _combined_zh_len = len([c for c in _combined if "\u4e00" <= c <= "\u9fff"])
                        if _combined_zh_len <= 16:
                            reaction_prefix_text = _combined
                            _rxn_trace["composition_mode"] = "echo+stance"
                        else:
                            reaction_prefix_text = _echo_candidate
                            _rxn_trace["composition_mode"] = "echo_only (brevity_guard)"
                    else:
                        reaction_prefix_text = _echo_candidate
                        _rxn_trace["composition_mode"] = "echo_only"
                else:
                    if reaction_prefix_text:
                        _rxn_trace["composition_mode"] = "stance_only"
                # ─────────────────────────────────────────────────────────────────────────────

                # User-question override (spec-friendly, no schema changes):
                # if the user asked a question (counter-question), return the persona's answer
                # as a dedicated `counter_reply` field so the client can display/TTS it
                # separately — much more reliable than concatenating into reaction_prefix_text
                # where bridge resets or ordering issues can silently drop it.
                persona_id = (payload.get("persona_id") or cs.get("persona_id") or "").strip() or None
                persona = _resolve_persona(persona_id) or (_get_persona(persona_id) if _get_persona else None)
                # Read prev counter_reply FIRST — needed for confusion recovery and dedup.
                _prev_counter_reply = (cs.get("last_counter_reply") or "").strip() if isinstance(cs, dict) else ""
                _last_text_for_counter = ""
                if last_turn_was_answer and isinstance(last_answer, dict):
                    _last_text_for_counter = (
                        (last_answer.get("submitted_text") or last_answer.get("selected_option_hanzi") or "").strip()
                    )
                _counter_seed = f"{cs.get('session_id', '')}/{len(recent or [])}" if isinstance(cs, dict) else ""

                # Mirror confusion escalation state — read before branching.
                # Cleared whenever a fresh (non-confusion) mirror answer is generated.
                _cs_mirror_topic  = (cs.get("last_mirror_topic")  or "") if isinstance(cs, dict) else ""
                _cs_mirror_engine = (cs.get("last_mirror_engine") or "") if isinstance(cs, dict) else ""
                _cs_mirror_conf   = int(cs.get("mirror_confusion_count") or 0) if isinstance(cs, dict) else 0

                _counter_result = None
                _counter_is_new_mirror = False  # set True when a fresh mirror answer is generated this turn
                _new_mirror_topic = ""
                _new_mirror_engine = ""

                if last_turn_was_answer:
                    _lex_ct = _lexical_definition_reply(_last_text_for_counter) if _last_text_for_counter else None
                    if _lex_ct:
                        _counter_result = _lex_ct
                    elif (
                        _prev_counter_reply
                        and _last_text_for_counter
                        and _is_confusion_signal(_last_text_for_counter)
                        and _cs_mirror_topic  # only escalate if a mirror answer was active
                    ):
                        # ── Mirror confusion escalation ladder ───────────────────────────────
                        # Stage 1 (first confusion): restate original answer naturally.
                        # Stage 2 (second confusion): simplified restatement.
                        # Stage 3+ (further confusion): generic recovery / move on.
                        if _cs_mirror_conf == 0:
                            # Stage 1 — natural restatement, preserve listening practice value
                            _counter_result = _mirror_restate_naturally(
                                _prev_counter_reply, _cs_mirror_topic
                            )
                        elif _cs_mirror_conf == 1:
                            # Stage 2 — simplified version (discoverable_facts_simple or voice_line)
                            _counter_result = _mirror_persona_stub_simple(
                                _cs_mirror_topic, _cs_mirror_engine, persona
                            )
                        else:
                            # Stage 3 — generic confusion recovery, then conversation moves on
                            _counter_result = _confusion_recovery_reply(
                                _last_text_for_counter, _prev_counter_reply, seed=_counter_seed
                            )
                    elif (
                        _prev_counter_reply
                        and _last_text_for_counter
                        and _is_confusion_signal(_last_text_for_counter)
                        and not _cs_mirror_topic  # no active mirror — use existing generic path
                    ):
                        _counter_result = _confusion_recovery_reply(
                            _last_text_for_counter, _prev_counter_reply, seed=_counter_seed
                        )
                    if _counter_result is None:
                        # Mirror answers only fire when the user genuinely asked a question.
                        # Statements (e.g. "我跟家人一起住。") must never match the mirror bank —
                        # the fuzzy keyword pass would otherwise match topic keywords in any answer.
                        _raw_mirror = _find_mirror_answer(
                            (last_answer.get("submitted_text") or last_answer.get("selected_option_hanzi") or ""),
                            "", persona
                        ) if isinstance(last_answer, dict) and user_asked_question else None
                        if _raw_mirror and len(_raw_mirror) == 4:
                            _counter_result      = (_raw_mirror[0], _raw_mirror[1])
                            _counter_is_new_mirror = True
                            _new_mirror_topic    = _raw_mirror[2]
                            _new_mirror_engine   = _raw_mirror[3]
                        else:
                            _counter_result = _answer_user_question_prefix(last_answer, persona)

                _counter_reply    = _counter_result[0] if _counter_result else None
                _counter_reply_en = _counter_result[1] if _counter_result else ""

                # ── Mirror confusion state update ────────────────────────────────────────
                # Write to cs so the next turn's escalation ladder has correct context.
                if isinstance(cs, dict):
                    if _counter_is_new_mirror and _new_mirror_topic:
                        # Fresh mirror answer — reset ladder
                        cs["last_mirror_topic"]    = _new_mirror_topic
                        cs["last_mirror_engine"]   = _new_mirror_engine
                        cs["mirror_confusion_count"] = 0
                    elif (
                        _cs_mirror_topic
                        and _last_text_for_counter
                        and _is_confusion_signal(_last_text_for_counter)
                    ):
                        # Confusion on an active mirror answer — advance the ladder
                        cs["mirror_confusion_count"] = _cs_mirror_conf + 1
                    elif not _is_confusion_signal(_last_text_for_counter or ""):
                        # Non-confusion turn — clear mirror escalation state
                        cs["last_mirror_topic"]      = ""
                        cs["last_mirror_engine"]     = ""
                        cs["mirror_confusion_count"] = 0

                # Dedup guard: if this counter_reply is identical to the one we gave last turn,
                # replace it with a gentle variation so the persona doesn't sound stuck.
                if _counter_reply and _counter_reply.strip() == _prev_counter_reply:
                    _counter_reply = _persona_deflect("generic", _counter_reply)
                    _counter_reply_en = _persona_deflect_en(_counter_reply)

                _counter_reply_pinyin = _resolve_counter_reply_pinyin(_counter_reply) if _counter_reply else ""

                # Retired pivot: if the user just said they are retired, ask what they used to do.
                _last_user_text = (last_answer or {}).get("submitted_text", "") if last_turn_was_answer else ""
                _user_is_retired = "退休" in _last_user_text and "p2_wk_retired" not in recent

                # Partner curiosity: prefer loop when triggered and depth allows, but avoid weak loop frames if possible
                chosen = None
                chosen_turn_type = "question"
                loop_attempted = False
                listening_move_selected = "none"
                listening_move_reason = ""
                if _user_is_retired:
                    chosen = "p2_wk_retired"
                    chosen_turn_type = "question"
                    listening_move_selected = "retired_pivot"
                    listening_move_reason = "user said retired"
                elif force_food_followup:
                    chosen = _pick_slot_followup_frame_id(
                        current_engine, ["DISH"], recent, memory, exchange_count=exchange_count,
                        answer_text=answer_text, last_answer_fid=last_answer_fid,
                        same_engine_chain_count=same_engine_chain_count,
                    )
                    if chosen:
                        chosen = _maybe_frame_order_priority(
                            current_engine, chosen, recent, memory, answer_text, last_answer_fid,
                        )
                        chosen_turn_type = "loop_question" if _is_loop_candidate(chosen) else "question"
                        listening_move_selected = "loop_question" if chosen_turn_type == "loop_question" else "question"
                        listening_move_reason = "food_followup_priority"
                        pending_listening_move = False
                        listening_wait_turns = 0
                # EFC: Entity Follow-Up Chain — ask targeted questions about a specific family member.
                # Fires when: family engine, entity detected/carried, not user question, depth allows.
                if (chosen is None and last_turn_was_answer and (not user_asked_question)
                        and _efc_active and current_engine == "family"):
                    _efc_candidate = _pick_efc_frame(
                        _efc_entity_state.get("type", ""),
                        _efc_entity_state.get("value", ""),
                        recent,
                        cs,
                    )
                    if _efc_candidate:
                        chosen = _efc_candidate
                        chosen_turn_type = "loop_question"
                        listening_move_selected = "efc"
                        listening_move_reason = f"efc_family_{_efc_entity_state.get('value','')}"
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
                    # Phase 11.1 / Phase 13C: depth guard — block bridge whenever content frames
                    # remain, regardless of time in engine. The old chain-count expiry caused
                    # ASR-repair turns to inflate same_engine_chain_count, disabling the guard
                    # before all content frames were shown (e.g. f_probe_work_why_quit skipped).
                    _remaining_in_engine = _count_remaining_engine_frames(current_engine, recent, memory)
                    _depth_guard_blocks = _remaining_in_engine >= ENGINE_DEPTH_GUARD_MIN_REMAINING
                    # Phase 12D Step 4: minimum dwell invariant — never bridge before 2 turns in engine.
                    _dwell_ok = same_engine_chain_count >= 2
                    # Late-session anti-fragmentation: after ≥8 turns or ≥3 engines visited,
                    # raise the dwell requirement to 3 turns so we don't race through engines.
                    # This is NOT a change to _ENGINE_TRANSITION_MIN_DWELL — it's a session-stage
                    # bias that keeps each new engine grounded longer before the next hop.
                    _visited_engine_count = len(engines_visited) if engines_visited else 0
                    _late_session_mode = (exchange_count >= 8) or (_visited_engine_count >= 3)
                    _late_session_cross_engine_penalty_applied = False
                    if _late_session_mode and not force_bridge and not prefer_bridge:
                        if same_engine_chain_count < 3:
                            _dwell_ok = False
                            _late_session_cross_engine_penalty_applied = True
                    # Phase 12D Step 3 (revised): bridge eligible only when engine is truly exhausted
                    # OR explicitly forced/preferred (recovery / change-topic).
                    # Low interest alone is NOT a bridge trigger — the engine must be done first.
                    # Rationale: low interest + remaining frames caused premature engine exits
                    # (e.g. skipping age after 好吧 fired in identity engine).
                    _engine_exhausted = _remaining_in_engine == 0
                    # Topic completion guard: when the learner just gave a HIGH-interest answer
                    # containing explicit reasoning or personal meaning (因为/所以/觉得/其实…),
                    # suppress spontaneous bridge entry for this turn.  The conversation should
                    # react and stay on topic rather than immediately jumping to a new engine.
                    # force_bridge / prefer_bridge (recovery / change-topic requests) still work.
                    _topic_completion_suppresses_bridge = (
                        not force_bridge
                        and not prefer_bridge
                        and interest_level == "high"
                        and _answer_has_reasoning_depth(answer_text)
                    )
                    bridge_allowed = (
                        force_bridge
                        or prefer_bridge
                        or (_engine_exhausted and _dwell_ok and not _topic_completion_suppresses_bridge)
                    )
                    # Selector trace — populated throughout selection, emitted in response.
                    _sel_trace: dict = {
                        "slot_followup": None,
                        "ladder": None,
                        "probe_eligible": False,
                        "probe_chosen": None,
                        "probe_suppressed_reason": None,
                        "bridge_considered": False,
                        "bridge_rejected_reason": None,
                        "final_frame_source": None,
                        "engine_lock_blocked": 0,
                        "cross_engine_alt_considered": False,
                        "cross_engine_alt_used": None,
                        "cross_engine_alt_blocked_reason": None,
                        "topic_completion_suppressed_bridge": _topic_completion_suppresses_bridge,
                        "probe_path": None,
                        "late_session_mode": _late_session_mode,
                        "late_session_cross_engine_penalty_applied": _late_session_cross_engine_penalty_applied,
                        "visited_engine_count": _visited_engine_count,
                    }
                    if pending_listening_move or force_listening or chain_exceeded:
                        seed_base = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}/interest"
                        gate_br = _stable_gate(seed_base + "/br")
                        p_br = P_BRIDGE_WHEN_INTEREST_HIGH if interest_level == "high" else 0.35
                        # Strategic review (Apr 2026): selection order should be:
                        #   1. Slot followup   — responds directly to what the learner just said
                        #   2. Frame ladder    — default topic spine; keeps conversation grounded
                        #   3. Curiosity probe — depth/significance questions; only when HIGH interest
                        #                        AND engine is grounded (≥2 turns in current engine)
                        #   4. Bridge          — topic transfer (handled after this block)
                        has_curiosity_signal = bool(slot_names) or bool(unscripted_probe_first) or bool(meaningful)
                        # Phase 12E: use decayed interest for curiosity depth cap (raw level still drives listening/reaction)
                        _curiosity_cap = _max_curiosity_cap_for_interest(_interest_decayed_level)
                        if curiosity_depth < _curiosity_cap and has_curiosity_signal:
                            # Step 1: slot followup — strongest local signal
                            chosen = _pick_slot_followup_frame_id(
                                current_engine, slot_names, recent, memory, exchange_count=exchange_count,
                                answer_text=answer_text, last_answer_fid=last_answer_fid,
                                same_engine_chain_count=same_engine_chain_count,
                                _trace=_sel_trace,
                            )
                            if chosen is not None:
                                chosen = _maybe_frame_order_priority(
                                    current_engine, chosen, recent, memory, answer_text, last_answer_fid,
                                )
                            _sel_trace["slot_followup"] = chosen
                            # Step 2: frame ladder — default spine when no slot followup
                            _ladder_chosen = None
                            if chosen is None:
                                _ladder_chosen = _select_next_frame_ladder_avoiding(
                                    current_engine,
                                    recent,
                                    avoid_frame_ids=_WEAK_LOOP_FRAME_IDS,
                                    memory=memory,
                                    exchange_count=exchange_count,
                                    engines_visited=engines_visited,
                                )
                                chosen = _ladder_chosen
                            _sel_trace["ladder"] = _ladder_chosen
                            # Step 3: curiosity probe — two eligibility paths, both require chain ≥ 2.
                            #
                            # HIGH path:   interest_decayed == "high" AND chain ≥ 2
                            #              → full probe inventory; up to curiosity_cap probes
                            #
                            # MEDIUM path: interest_decayed == "medium"
                            #              AND answer contains reasoning/depth markers
                            #              AND chain ≥ 2
                            #              AND this engine has not had a medium probe this session
                            #              → only medium-min frames (high-min skipped automatically)
                            #              → at most 1 medium probe per engine per session
                            _engine_norm_for_probe = (current_engine or "").strip().lower()
                            _high_probe_eligible = (
                                _interest_decayed_level == "high"
                                and same_engine_chain_count >= 2
                            )
                            _medium_probe_eligible = (
                                not _high_probe_eligible
                                and _interest_decayed_level == "medium"
                                and same_engine_chain_count >= 2
                                and _answer_has_reasoning_depth(answer_text)
                                and _engine_norm_for_probe not in medium_probe_fired_engines
                            )
                            _probe_eligible = _high_probe_eligible or _medium_probe_eligible
                            _sel_trace["probe_eligible"] = _probe_eligible
                            if _probe_eligible:
                                _probe_interest = _interest_decayed_level if _high_probe_eligible else "medium"
                                _probe = _pick_curiosity_probe_frame(current_engine, _probe_interest, memory, recent)
                                if _probe is not None:
                                    chosen = _probe
                                    _sel_trace["probe_chosen"] = _probe
                                    _sel_trace["probe_path"] = "high" if _high_probe_eligible else "medium_reasoning"
                                    if _medium_probe_eligible:
                                        if _engine_norm_for_probe not in medium_probe_fired_engines:
                                            medium_probe_fired_engines = medium_probe_fired_engines + [_engine_norm_for_probe]
                                else:
                                    _sel_trace["probe_suppressed_reason"] = "no_eligible_probe_frame"
                            else:
                                if same_engine_chain_count < 2:
                                    _sel_trace["probe_suppressed_reason"] = "engine_not_grounded_lt2_turns"
                                elif _interest_decayed_level == "medium" and _engine_norm_for_probe in medium_probe_fired_engines:
                                    _sel_trace["probe_suppressed_reason"] = "medium_probe_already_used_this_engine"
                                elif _interest_decayed_level == "medium" and not _answer_has_reasoning_depth(answer_text):
                                    _sel_trace["probe_suppressed_reason"] = "medium_no_reasoning_depth"
                                else:
                                    _sel_trace["probe_suppressed_reason"] = "interest_not_high_or_medium_reasoning"
                            if chosen and _is_loop_candidate(chosen):
                                chosen_turn_type = "loop_question"
                                curiosity_depth = min(curiosity_depth + 1, _curiosity_cap)
                                listening_move_selected = "loop_question"
                                listening_move_reason = "interest_policy"
                                pending_listening_move = False
                                listening_wait_turns = 0
                        # Only default to bridge when curiosity had no viable frame.
                        # Depth guard: never fire a chain_exceeded bridge when we just entered a
                        # fresh engine and frames remain — the high chain count is from the
                        # previous engine, not the current one.
                        _sel_trace["bridge_considered"] = bool(
                            chosen is None and bridge_allowed and (force_listening or chain_exceeded or gate_br < int(p_br * 1000))
                        )
                        if _sel_trace["bridge_considered"] and _depth_guard_blocks:
                            _sel_trace["bridge_rejected_reason"] = "depth_guard_blocks"
                        elif _sel_trace["bridge_considered"] and not bridge_allowed:
                            _sel_trace["bridge_rejected_reason"] = "bridge_not_allowed"
                        if chosen is None and bridge_allowed and (force_listening or chain_exceeded or gate_br < int(p_br * 1000)) and not _depth_guard_blocks:
                            chosen = _select_next_frame_bridge(current_engine, recent, use_recovery_order=prefer_bridge, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited, seeded_bridge_engines=seeded_bridge_engines)
                            if chosen:
                                chosen_turn_type = "question"
                                listening_move_selected = "bridge"
                                listening_move_reason = "interest_policy_or_chain_cap"
                                pending_listening_move = False
                                listening_wait_turns = 0
                        if chosen is None and pending_listening_move:
                            listening_wait_turns += 1
                # If user asked a question, do NOT attempt loop-questioning; keep flow simple and reciprocal.
                _curiosity_cap = _max_curiosity_cap_for_interest(_interest_decayed_level)
                if chosen is None and last_turn_was_answer and (not user_asked_question) and meaningful and curiosity_depth < _curiosity_cap:
                    # stable probability gate for loop
                    seed = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}/loop"
                    gate = 0
                    for ch in seed:
                        gate = (gate * 131 + ord(ch)) % 1000
                    if gate < int(P_LOOP_WHEN_TRIGGERED * 1000):
                        loop_attempted = True
                        # Prefer slot/topic follow-up first (often loop-like), then fall back to engine ladder
                        chosen = _pick_slot_followup_frame_id(
                            current_engine, slot_names, recent, memory, exchange_count=exchange_count,
                            answer_text=answer_text, last_answer_fid=last_answer_fid,
                            same_engine_chain_count=same_engine_chain_count,
                        )
                        if chosen is not None:
                            chosen = _maybe_frame_order_priority(
                                current_engine, chosen, recent, memory, answer_text, last_answer_fid,
                            )
                        # Phase 12E: probe frame before falling back to generic ladder
                        if chosen is None and _interest_decayed_level in ("medium", "high"):
                            chosen = _pick_curiosity_probe_frame(current_engine, _interest_decayed_level, memory, recent)
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
                    if curiosity_depth >= _max_curiosity_cap_for_interest(_interest_decayed_level):
                        # Force ask/bridge; reset depth
                        if prefer_bridge or force_bridge:
                            chosen = _select_next_frame_bridge(current_engine, recent, use_recovery_order=prefer_bridge, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited, seeded_bridge_engines=seeded_bridge_engines)
                        if chosen is None and not force_bridge:
                            chosen = _select_next_frame_ladder(current_engine, recent, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited)
                        curiosity_depth = 0
                        chosen_turn_type = "question"
                    else:
                        # Soft chaining: slot/topic preference first, then existing bridge/ladder order
                        if last_turn_was_answer and (not user_asked_question) and meaningful:
                            chosen = _pick_slot_followup_frame_id(
                                current_engine, slot_names, recent, memory, exchange_count=exchange_count,
                                answer_text=answer_text, last_answer_fid=last_answer_fid,
                                same_engine_chain_count=same_engine_chain_count,
                            )
                            if chosen is not None:
                                chosen = _maybe_frame_order_priority(
                                    current_engine, chosen, recent, memory, answer_text, last_answer_fid,
                                )
                            if chosen and _is_loop_candidate(chosen):
                                chosen_turn_type = "loop_question"
                                curiosity_depth = min(curiosity_depth + 1, _max_curiosity_cap_for_interest(_interest_decayed_level))
                                pending_listening_move = False
                                listening_wait_turns = 0
                        if chosen is None:
                            if prefer_bridge or force_bridge:
                                chosen = _select_next_frame_bridge(current_engine, recent, use_recovery_order=prefer_bridge, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited, seeded_bridge_engines=seeded_bridge_engines)
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

                # Soft closing move: emit a reflective closing line instead of asking another question
                # when the conversation has reached a natural pause point.
                #
                # Two triggers:
                #   Original — chosen is still None (no frame available at all):
                #              late_session + topic_completion_suppressed_bridge + no probe
                #   Extended — chosen WAS set (e.g. by unscripted_probe_first) but the session
                #              is late, the answer is substantive, no probe fired, bridge is not
                #              forced, and the engine is nearly exhausted.  In this case a ladder
                #              frame surviving does not justify interrupting a meaningful close.
                _cm_late_session = _late_session_mode or (exchange_count >= 8) or (len(engines_visited or []) >= 3)
                _cm_substantive = last_turn_was_answer and (not user_asked_question) and (
                    unscripted_probe_first or _answer_has_reasoning_depth(answer_text)
                )
                # Preemptible trigger uses a lighter substantive check: any real (non-trivial) answer
                # is enough when the session is late and the chosen frame is declared weak.
                _cm_real_answer = last_turn_was_answer and (not user_asked_question) and (not weak_reply)
                _cm_no_probe = not _sel_trace.get("probe_chosen")
                _cm_bridge_not_forced = not force_bridge and not prefer_bridge
                _cm_remaining_weak = (
                    _count_remaining_engine_frames(current_engine, list(recent or []), memory) <= 1
                )
                _cm_chosen_preemptible = bool(chosen and chosen in _LATE_SESSION_PREEMPTIBLE_FRAMES)

                # Suppressed-reason trace — always populated so every turn is auditable.
                if not _cm_late_session:
                    _closing_suppressed_reason = "not_late_session"
                elif not _cm_no_probe:
                    _closing_suppressed_reason = "probe_already_chosen"
                elif not _cm_real_answer and not _cm_substantive:
                    _closing_suppressed_reason = "no_reasoning_depth"
                elif not _cm_bridge_not_forced:
                    _closing_suppressed_reason = "bridge_not_suppressed"
                elif chosen and not _cm_remaining_weak and not _cm_chosen_preemptible:
                    _closing_suppressed_reason = "chosen_still_available"
                else:
                    _closing_suppressed_reason = ""
                _sel_trace["closing_move_suppressed_reason"] = _closing_suppressed_reason

                _cm_original = (
                    not chosen
                    and _cm_late_session
                    and _topic_completion_suppresses_bridge
                    and _cm_no_probe
                )
                _cm_extended = (
                    _cm_late_session
                    and _cm_substantive
                    and _cm_no_probe
                    and _cm_bridge_not_forced
                    and _cm_remaining_weak
                    and last_turn_was_answer
                    and (not user_asked_question)
                )
                # Preemptible trigger: chosen frame is declared weak for late session;
                # suppress it and close instead. No engine-exhaustion requirement.
                _cm_preemptible = (
                    _cm_late_session
                    and _cm_real_answer
                    and _cm_no_probe
                    and _cm_bridge_not_forced
                    and _cm_chosen_preemptible
                )
                _closing_preempted_frame = chosen if _cm_preemptible else None
                _closing_move_fired = False
                _closing_reason = ""
                if _cm_original or _cm_extended or _cm_preemptible:
                    _closing_move_fired = True
                    _closing_reason = "meaningful_answer_no_next_move"
                    _cl_trigger = "preemptible" if _cm_preemptible else ("extended" if _cm_extended else "original")
                    _cl_seed = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}/closing"
                    _cl_zh, _cl_py, _cl_en = _pick_closing_reaction(_cl_seed)
                    print(f"[CLOSING] trigger={_cl_trigger} late_session={_cm_late_session} "
                          f"preempted={_closing_preempted_frame!r} engine={current_engine} text={_cl_zh!r}", flush=True)
                    _closing_response = {
                        "turn_uid":     payload.get("turn_uid", ""),
                        "engine_id":    current_engine or "unknown",
                        "frame_id":     "closing_move",
                        "frame_text":   _cl_zh,
                        "frame_pinyin": _cl_py,
                        "frame_text_en": _cl_en,
                        "result":       "ok",
                        "options":      [],
                        "option_count": 0,
                        "gold_option_present": False,
                        "card_id":      None,
                        "system_note":  "closing_move",
                        "sentence_options": [],
                        "closing_move": True,
                        "closing_reason": _closing_reason,
                        "closing_preempted_frame": _closing_preempted_frame,
                        "selector_trace": dict(_sel_trace, closing_move_fired=True, closing_reason=_closing_reason,
                                               closing_preempted_frame=_closing_preempted_frame),
                        "interest_level": interest_level,
                        "same_engine_chain_count": int(same_engine_chain_count),
                        "seeded_bridge_engines": list(seeded_bridge_engines),
                        "recent_reactions": list(_recent_reactions),
                        "medium_probe_fired_engines": list(medium_probe_fired_engines),
                    }
                    if _phase10_learner_memory is not None:
                        _closing_response["learner_memory"] = _phase10_learner_memory
                    if _phase10_persona_id:
                        _closing_response["persona_id"] = _phase10_persona_id
                    _cl_data = json.dumps(_closing_response, ensure_ascii=False).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(_cl_data)))
                    self.end_headers()
                    self.wfile.write(_cl_data)
                    return

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
                                current_engine, recent, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited, seeded_bridge_engines=seeded_bridge_engines
                            )
                            if _arc_br:
                                chosen = _arc_br
                                chosen_turn_type = "question"
                                _transition_reason = "loop_limit_bridge"

                    # 2. Overload — user confused ≥ OVERLOAD_CONFUSION_THRESHOLD times;
                    #    if selector picked a LOOP follow-up, try a same-engine non-LOOP question first,
                    #    then bridge (avoids abrupt topic jumps during repair).
                    if _12c_overload and _is_loop_candidate(chosen) and not user_asked_question:
                        _arc_nl = _select_non_loop_unseen_same_engine(
                            current_engine, recent, memory=memory, exchange_count=exchange_count
                        )
                        if _arc_nl:
                            chosen = _arc_nl
                            chosen_turn_type = "question"
                            _transition_reason = "overload_same_engine"
                        else:
                            _arc_br = _select_next_frame_bridge(
                                current_engine, recent, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited, seeded_bridge_engines=seeded_bridge_engines
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
                        # Only push out if we've had enough turns in this engine OR it's nearly empty.
                        # Late-session mode: require full exhaustion (_remaining_now == 0) instead of
                        # "nearly empty" (< 2). This prevents closure from hopping engines too eagerly
                        # when the session is already deep and many engines have been visited.
                        _closure_nearly_empty_threshold = 0 if _late_session_mode else ENGINE_DEPTH_GUARD_MIN_REMAINING
                        _close_ready = (
                            _still_in_engine
                            and (
                                same_engine_chain_count >= ENGINE_DEPTH_GUARD_TURNS
                                or _remaining_now <= _closure_nearly_empty_threshold
                            )
                        )
                        if _close_ready:
                            _close_seed = f"{cs.get('session_id','')}/close/{len(recent)}"
                            _close_gate = sum(ord(c) for c in _close_seed) % 1000
                            if _close_gate < CLOSURE_BRIDGE_GATE:
                                _arc_br = _select_next_frame_bridge(
                                    current_engine, recent, memory=memory, exchange_count=exchange_count, engines_visited=engines_visited, seeded_bridge_engines=seeded_bridge_engines
                                )
                                if _arc_br:
                                    chosen = _arc_br
                                    chosen_turn_type = "question"
                                    _transition_reason = "closure"
                # ── End Phase 12C ─────────────────────────────────────────────────────
                # Discourse coherence must run *after* move_type filter + Phase 12C — those passes can
                # bridge to food (place→food is first in _BRIDGE_TARGETS) and undo an earlier fix.
                if chosen:
                    chosen = _apply_discourse_coherence_guard(
                        chosen,
                        cs=cs,
                        recent=recent,
                        last_answer=last_answer,
                        last_turn_was_answer=last_turn_was_answer,
                        learner_skip_confusion=(cs.get("learner_skip_confusion") is True),
                        memory=memory,
                    )
                if chosen:
                    _before_place_swap = chosen
                    chosen = _swap_place_like_if_unfamiliar_live_city(
                        chosen,
                        last_answer=last_answer,
                        last_turn_was_answer=last_turn_was_answer,
                        memory=memory,
                        recent=recent,
                    )
                    if chosen != _before_place_swap and chosen == "p2_pl_ext1" and _is_loop_candidate("p2_pl_ext1"):
                        chosen_turn_type = "loop_question"
                if _transition_reason == "overload_same_engine":
                    print(
                        "[ARC] overload_same_engine "
                        f"engine={current_engine!r} chosen_frame={chosen!r} "
                        f"recent_confusion_count={recent_confusion_count} "
                        f"threshold={OVERLOAD_CONFUSION_THRESHOLD}",
                        flush=True,
                    )

                # Post-selection dwell guard: block any cross-engine transition that requires
                # more dwell in the current engine (e.g. WORK→PLACE needs ≥3 turns in work).
                # This applies to bridge-selected frames; slot followup already filters them
                # out via the engine lock in _pick_slot_followup_frame_id.
                if chosen and listening_move_selected == "bridge":
                    _chosen_fr_eng = (_frames_by_id.get(chosen) or {}).get("engine", "").strip().lower()
                    if _cross_engine_transition_blocked(current_engine, _chosen_fr_eng, same_engine_chain_count):
                        chosen = None
                        listening_move_selected = "none"
                        _sel_trace["bridge_rejected_reason"] = (
                            f"dwell_guard:{current_engine}->{_chosen_fr_eng} "
                            f"(need {_ENGINE_TRANSITION_MIN_DWELL.get((current_engine, _chosen_fr_eng), '?')},"
                            f" have {same_engine_chain_count})"
                        )

                frame_id = chosen
                frame_rec_chosen = _frames_by_id.get(frame_id, {})
                # Populate final_frame_source in selector trace.
                if chosen:
                    if _sel_trace.get("slot_followup") == chosen:
                        _sel_trace["final_frame_source"] = "slot_followup"
                    elif _sel_trace.get("probe_chosen") == chosen:
                        _sel_trace["final_frame_source"] = "curiosity_probe"
                    elif listening_move_selected == "bridge":
                        _sel_trace["final_frame_source"] = "bridge"
                    elif _sel_trace.get("ladder") == chosen:
                        _sel_trace["final_frame_source"] = "ladder"
                    else:
                        _sel_trace["final_frame_source"] = "other"
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
                # Safety net: if any {CITY}/{PLACE} token survived (no memory, or memory load failed),
                # replace with 那儿 so the raw placeholder never reaches the learner UI.
                for _tok, _fb in (("{CITY}", "那儿"), ("{PLACE}", "那儿")):
                    if _tok in (response.get("frame_text") or ""):
                        response["frame_text"] = response["frame_text"].replace(_tok, _fb)
                    if _tok in (response.get("frame_pinyin") or ""):
                        response["frame_pinyin"] = response["frame_pinyin"].replace(_tok, "nàr")
                if "[CITY]" in (response.get("frame_text_en") or ""):
                    response["frame_text_en"] = response["frame_text_en"].replace("[CITY]", "there")
            # Safety net: {NAME} slot — fill from persona display_name; never reach the learner as raw token.
            if "{NAME}" in (response.get("frame_text") or ""):
                _name_fill = _assistant_name_from_persona(persona) if persona else ""
                response["frame_text"] = response["frame_text"].replace("{NAME}", _name_fill or "我")
            # EFC: {ENTITY} slot — fill from current efc_entity; update efc_depth in state_update.
            if "{ENTITY}" in (response.get("frame_text") or ""):
                _entity_val = (_efc_entity_state.get("value") or "").strip()
                if _entity_val:
                    response["frame_text"] = response["frame_text"].replace("{ENTITY}", _entity_val)
                    _en = response.get("frame_text_en") or ""
                    if "{ENTITY}" in _en:
                        response["frame_text_en"] = _en.replace("{ENTITY}", _entity_val)
                    _py = response.get("frame_pinyin") or ""
                    if "{ENTITY}" in _py:
                        response["frame_pinyin"] = _py.replace("{ENTITY}", _entity_val)
                    # Increment efc_depth so the chain doesn't overshoot MAX_EFC_DEPTH.
                    _new_efc_depth = int((cs or {}).get("efc_depth") or 0) + 1
                    response.setdefault("state_update", {})
                    response["state_update"]["efc_entity"] = _efc_entity_state
                    response["state_update"]["efc_depth"] = _new_efc_depth
                else:
                    # No entity in state — kinship noun + sync EN/PY (avoid 你他们… and stale {ENTITY} in gloss).
                    _fbz, _fbe, _fbp = _ENTITY_SLOT_FALLBACK_ZH, _ENTITY_SLOT_FALLBACK_EN, _ENTITY_SLOT_FALLBACK_PY
                    response["frame_text"] = response["frame_text"].replace("{ENTITY}", _fbz)
                    _en = response.get("frame_text_en") or ""
                    if "{ENTITY}" in _en:
                        response["frame_text_en"] = _en.replace("{ENTITY}", _fbe)
                    _py = response.get("frame_pinyin") or ""
                    if "{ENTITY}" in _py:
                        response["frame_pinyin"] = _py.replace("{ENTITY}", _fbp)
            elif _efc_entity_state and cs is not None:
                # Carry entity forward even when this frame has no ENTITY slot.
                response.setdefault("state_update", {})
                response["state_update"]["efc_entity"] = _efc_entity_state
                response["state_update"]["efc_depth"] = int((cs or {}).get("efc_depth") or 0)
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
                    # Phase 12D: also block if reaction_prefix_text is itself a question — producing "Q1？Q2？" is confusing.
                    _reaction_is_question = "？" in reaction_prefix_text
                    if "？" in (frame_rec.get("text") or "") and not _reaction_is_question:
                        response["frame_text"] = f"{reaction_prefix_text}{response['frame_text']}"
                        response["system_note"] = "phase10.5 reaction_micro_layer"
                        response["reaction_used_fallback"] = bool(reaction_used_fallback)
                if bridge_prefix_text and "？" in (frame_rec.get("text") or ""):
                    response["frame_text"] = f"{bridge_prefix_text}{response['frame_text']}"
                    response["bridge_prefix_applied"] = True
                # Counter-reply: separate field so client TTS/displays it before the next question.
                if _counter_reply:
                    response["counter_reply"] = _counter_reply
                    if _counter_reply_en:
                        response["counter_reply_en"] = _counter_reply_en
                    if _counter_reply_pinyin:
                        response["counter_reply_pinyin"] = _counter_reply_pinyin
                    # Store so next turn can dedup (client echoes conversation_state back).
                    response["state_update"] = response.get("state_update") or {}
                    response["state_update"]["last_counter_reply"] = _counter_reply

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
                    # Phase 12E: prepend one targeted hint based on keywords in the persona's reply
                    _disc_hint = _pick_contextual_discovery_hint(_counter_reply)
                    if _disc_hint:
                        response["discovery_hint"] = _disc_hint

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
                        interest_level=_interest_decayed_level,
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
                # Phase 12E: interest trace — inspect raw inputs, initial level, decay, and final curiosity level
                response["interest_trace"] = {
                    "raw_score":        int(interest_score),
                    "novelty_hit":      bool(_interest_novelty_hit),
                    "initial_level":    _interest_initial_level,
                    "loop_count_in_engine": int(cs.get("same_engine_chain_count") or 0),
                    "decayed_level":    _interest_decayed_level,
                    "final_curiosity_level": _interest_decayed_level,
                }
                response["pending_listening_move"] = bool(pending_listening_move)
                response["listening_wait_turns"] = int(listening_wait_turns)
                response["listening_move_selected"] = listening_move_selected
                response["listening_move_reason"] = listening_move_reason
                response["same_engine_chain_count"] = int(same_engine_chain_count)
                response["same_slot_chain_count"] = int(same_slot_chain_count)
                response["last_focus_slot"] = last_focus_slot
                response["last_user_text"] = last_user_text
                # Phase 13B: return updated seeded bridge queue for client round-trip.
                # Remove the engine just visited so it doesn't loop back immediately.
                _chosen_engine_for_seed = (frame_rec_chosen.get("engine") or "").strip().lower()
                response["seeded_bridge_engines"] = [
                    e for e in seeded_bridge_engines if e != _chosen_engine_for_seed
                ]
                # Reaction deduplication: persist last 2 reaction texts for next turn.
                if reaction_prefix_text:
                    _updated_recent_reactions = ([reaction_prefix_text] + _recent_reactions)[:2]
                    response["recent_reactions"] = _updated_recent_reactions
                else:
                    response["recent_reactions"] = _recent_reactions
                # Medium probe tracking: persist engine list so cap is enforced across turns.
                response["medium_probe_fired_engines"] = medium_probe_fired_engines
                # Emit diagnostic traces so the conversation can be audited turn-by-turn.
                response["selector_trace"] = _sel_trace
                response["reaction_trace"] = _rxn_trace
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
