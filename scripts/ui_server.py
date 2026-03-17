#!/usr/bin/env python3
import argparse
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse, parse_qs
import mimetypes
import os

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
P_LOOP_WHEN_TRIGGERED = 0.6
MAX_CURIOSITY_DEPTH = 2
EARLY_EXCHANGES = 3

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
    "identity": ["f_ask_you_name", "f_ask_name_meaning", "p2_id_2", "p2_id_4", "p2_id_5"],  # core then treasure/loop (怎么叫你, 名字怎么样, 意义)
    "place": ["f_from_where", "f_place_like_there", "frame.location.live_question", "p2_pl_1", "p2_pl_2", "p2_pl_3", "p2_pl_4"],  # core then treasure/loop (生活怎么样, 好吃的, 喜欢去, 方便吗)
    "family": ["f_have_family", "f_have_siblings", "p2_fa_1", "p2_fa_2", "p2_fa_5"],  # core then treasure/loop (跟家人住, 多久见, 周末做什么)
    "work": ["f_what_work", "f_like_work", "p2_wk_1", "p2_wk_2", "p2_wk_4", "p2_wk_5"],  # core then treasure/loop (几点下班, 忙不忙, 怎么安排, 怎么解决)
    "hobby": ["f_what_hobby", "f_like_do_what", "f_often_do", "f_difficult_ma", "f_recommend_ma", "f_weekend_do", "f_like_chinese_culture", "f_like_what", "f_collect_what", "p2_hb_1", "p2_hb_2", "p2_hb_4", "p2_hb_5"],  # core → treasure → weekend/culture
    "travel": ["f_travel_where", "f_want_go_where", "p2_tr_1", "p2_tr_2", "p2_tr_3", "p2_tr_4"],  # core then treasure/loop (哪些国家, 最喜欢哪里, 好玩的, 旅行怎么样)
    "food": ["f_food_what_good", "f_food_famous_dish", "f_food_tasty", "f_food_like_spicy", "f_food_expensive"],  # core → treasure
    "life": [],
}
# A frame id may only be chosen if all of its "after" frames are in recent_frame_ids (already asked).
_FRAME_AFTER: dict = {
    "f_ask_name_meaning": ["f_ask_you_name"],  # don't ask name meaning before asking name
}


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
    "identity": ["place", "family", "work"],
    "place": ["identity", "family", "travel", "food"],
    "family": ["identity", "place", "work"],
    "work": ["identity", "place", "family"],
    "hobby": ["identity", "travel", "food"],
    "travel": ["place", "hobby", "food"],
    "food": ["place", "travel", "hobby", "life"],
    "life": ["identity", "place", "family"],
}

# When prefer_bridge (recovery / change topic): try engines in this order so the next question feels like a natural switch (place/identity/family first), not a jump to food/travel.
_RECOVERY_BRIDGE_ENGINE_ORDER: list = ["place", "identity", "family", "work", "hobby", "travel", "food", "life"]

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
    "p2_wk_1", "p2_wk_2", "p2_wk_4", "p2_wk_5",
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
}

# Slot/topic-specific follow-up preferences (attempt before generic engine ladder).
_SLOT_FOLLOWUP_PREFERENCES: dict = {
    # CITY: prefer convenience before “life怎么样” because p2_pl_1 is weak
    # Also keep p2_pl_3 out of the slot path (known weak).
    "CITY": ["p2_pl_4", "p2_pl_2", "f_place_like_there", "p2_pl_1"],
    # JOB: prefer work-experience follow-ups (p2_wk_* are often weak; keep as last resort)
    "JOB":  ["p2_wk_3", "p2_wk_1", "f_like_work"],
    # DISH: prefer taste/spicy before generic “famous dish”
    "DISH": ["f_food_tasty", "f_food_like_spicy", "f_food_famous_dish"],
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


def _infer_slot_names_from_answer(last_answer: Optional[dict]) -> List[str]:
    """Best-effort: infer slot names from the user's answer frame (question frame_id in last_answer)."""
    if not last_answer or not isinstance(last_answer, dict):
        return []
    # last_answer.frame_id is the partner ask frame the user answered (e.g. f_from_where)
    # selected option's card_id often points to a user frame with slots; try to infer via that mapping when possible.
    # We only have selected_option_hanzi/meaning here; so use memory capture triggers + known ask frame ids.
    fid = (last_answer.get("frame_id") or "").strip()
    if fid == "frame.location.live_question":
        return ["CITY"]
    if fid == "f_what_work":
        return ["JOB"]
    if fid == "f_food_what_good":
        return ["DISH"]
    return []


def _should_surface_curiosity(cs: dict, *, meaningful: bool, last_partner_was_loop: bool, last_partner_had_reaction: bool) -> bool:
    """Visibility gating for probe row (curiosity options)."""
    # Do not surface on very first greeting-like moment (no history)
    recent = cs.get("recent_frame_ids") or []
    if not recent or len(recent) <= 1:
        return False
    if cs.get("prefer_bridge") is True or cs.get("force_bridge") is True:
        # keep recovery/bridge simple
        return False
    if last_partner_was_loop:
        return True
    if meaningful:
        return True
    # Interview drift: 2 consecutive asks without loop or reaction micro-layer (tracked by counters)
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


def _pick_reaction_text(engine_id: str, seed: str) -> str:
    engine_norm = (engine_id or "").strip().lower()
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


def _pick_slot_followup_frame_id(engine_id: str, slot_names: List[str], recent_frame_ids: list, memory: Optional[dict]) -> Optional[str]:
    """Try slot/topic follow-up frames before generic ladder; avoid weak loop frames if possible."""
    recent = set(recent_frame_ids or [])
    for s in slot_names or []:
        prefs = _SLOT_FOLLOWUP_PREFERENCES.get(s) or []
        # Prefer non-weak frames first
        ordered = [f for f in prefs if f not in _WEAK_LOOP_FRAME_IDS] + [f for f in prefs if f in _WEAK_LOOP_FRAME_IDS]
        for fid in ordered:
            if fid in recent:
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


def _select_next_frame_bridge(current_engine: str, recent_frame_ids: list, use_recovery_order: bool = False, memory: Optional[dict] = None) -> Optional[str]:
    """
    Phase 9.2: bridge to another engine. Only used after MIN_TURNS_BEFORE_BRIDGE turns in current engine.
    Prefers partner-question frames so the next line is a question, not a reactive phrase.
    When use_recovery_order is True (e.g. after 我不懂 or Change topic), try engines in _RECOVERY_BRIDGE_ENGINE_ORDER
    so the next question is a more natural switch (place/identity/family) rather than jumping to food/travel.
    """
    recent = set(recent_frame_ids or [])
    engine_norm = (current_engine or "").strip().lower()
    targets = (
        [e for e in _RECOVERY_BRIDGE_ENGINE_ORDER if (e or "").strip().lower() != engine_norm]
        if use_recovery_order
        else _BRIDGE_TARGETS.get(engine_norm) or []
    )
    recent_list = recent_frame_ids or []
    for target_engine in targets:
        target_norm = (target_engine or "").strip().lower()
        if target_norm == engine_norm:
            continue
        # Prefer partner questions, then any frame in target engine
        candidates = _engine_partner_question_frame_ids(target_norm)
        if not candidates:
            candidates = _engine_frame_ids(target_norm)
        for fid in candidates:
            if fid not in recent:
                if memory is not None and _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS):
                    continue
                return fid
    return None


def _select_next_frame_ladder(current_engine: str, recent_frame_ids: list, memory: Optional[dict] = None) -> Optional[str]:
    """
    Phase 9.1/9.2: deterministic next-frame ladder.
    1. Same engine, excluding recent_frame_ids (no repeat yet).
    2. If all frames in this engine were already used, bridge to another engine (new topic) so we never repeat a question already asked.
    3. Same-engine repeat only if bridge failed (e.g. no other engines).
    4. Safe fallback so we never dead-end.
    """
    recent = set(recent_frame_ids or [])
    engine_norm = (current_engine or "").strip().lower()
    same_engine = _engine_partner_question_frame_ids(engine_norm)
    if not same_engine:
        same_engine = _engine_frame_ids(engine_norm)

    # Tier 1: same engine, exclude recent, and only offer frame if its "after" deps are satisfied
    def _deps_satisfied(fid: str) -> bool:
        after = _FRAME_AFTER.get(fid) or []
        return all(dep in recent for dep in after)

    recent_list = list(recent_frame_ids or [])
    def _not_suppressed(fid: str) -> bool:
        if memory is None:
            return True
        return not _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS)

    unseen_same = [
        fid for fid in same_engine
        if fid not in recent and _deps_satisfied(fid) and _not_suppressed(fid)
    ]
    if unseen_same:
        return unseen_same[0]

    # Tier 2: all frames in this engine were already used — bridge to a new topic instead of repeating
    chosen = _select_next_frame_bridge(current_engine, recent_frame_ids, memory=memory)
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
) -> Optional[str]:
    """
    Like _select_next_frame_ladder, but will skip avoid_frame_ids when there is any non-avoided candidate available
    in the same engine. This is used to deprioritize known weak loop frames (e.g. p2_pl_1, p2_pl_3) without
    changing the overall selector order.
    """
    avoid = avoid_frame_ids or set()
    recent = set(recent_frame_ids or [])
    engine_norm = (current_engine or "").strip().lower()
    same_engine = _engine_partner_question_frame_ids(engine_norm) or _engine_frame_ids(engine_norm)

    def _deps_satisfied(fid: str) -> bool:
        after = _FRAME_AFTER.get(fid) or []
        return all(dep in recent for dep in after)

    recent_list = list(recent_frame_ids or [])

    def _not_suppressed(fid: str) -> bool:
        if memory is None:
            return True
        return not _should_suppress_ask_frame(fid, memory, recent_list, RECALL_INTERVAL_TURNS)

    unseen = [fid for fid in same_engine if fid not in recent and _deps_satisfied(fid) and _not_suppressed(fid)]
    if not unseen:
        return _select_next_frame_ladder(current_engine, recent_frame_ids, memory=memory)

    non_avoided = [fid for fid in unseen if fid not in avoid]
    if non_avoided:
        return non_avoided[0]

    # Only avoided candidates remain. For the highest-impact weak loop frames, prefer to bridge away
    # rather than forcing a low-quality loop.
    if engine_norm == "place" and avoid.issuperset({"p2_pl_1", "p2_pl_3"}):
        bridged = _select_next_frame_bridge(current_engine, recent_frame_ids, memory=memory)
        if bridged and bridged not in recent:
            return bridged
    return unseen[0]


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

        if path == "/api/cards":
            rel = qs.get("path", [None])[0]
            if not rel:
                self._json_error(400, "missing path param")
                return
            self._serve_file(REPO_ROOT / rel, path)
            return

        if path.startswith("/runtime/"):
            file_path = RUNTIME_DIR / path[len("/runtime/"):]
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

        if path == "/api/run_turn":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except Exception as e:
                print(f"[ui_server] bad request body: {e}")
                payload = {}

            print(f"[ui_server] /api/run_turn: {payload}")

            # Oxygen loop: user asked a probe (为什么？, 谁？, etc.) — return stub partner response (persona-consistent when available)
            probe_id = (payload.get("probe_id") or "").strip()
            if probe_id:
                cs = payload.get("conversation_state") or {}
                persona_id = (payload.get("persona_id") or cs.get("persona_id") or "").strip() or None
                persona = _get_persona(persona_id) if _get_persona else None
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
            loop_attempted = False
            chosen_turn_type = "question"
            new_memory_written = False

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
                last_partner_was_loop = cs.get("last_partner_turn_type") == "loop_question"
                last_partner_had_reaction = cs.get("last_partner_had_reaction") is True

                # Reaction micro-layer: we cannot emit two separate partner turns without changing API.
                # So when reaction triggers, we optionally prepend a short reaction phrase to the next question's text.
                reaction_prefix_text = ""
                reaction_used_fallback = False
                if last_turn_was_answer and meaningful:
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
                                reaction_prefix_text = (_frames_by_id.get(rid) or {}).get("text") or ""
                            else:
                                reaction_prefix_text = _pick_reaction_text(current_engine, seed)
                                reaction_used_fallback = True

                # Partner curiosity: prefer loop when triggered and depth allows, but avoid weak loop frames if possible
                chosen = None
                chosen_turn_type = "question"
                loop_attempted = False
                if last_turn_was_answer and meaningful and curiosity_depth < MAX_CURIOSITY_DEPTH:
                    # stable probability gate for loop
                    seed = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}/loop"
                    gate = 0
                    for ch in seed:
                        gate = (gate * 131 + ord(ch)) % 1000
                    if gate < int(P_LOOP_WHEN_TRIGGERED * 1000):
                        loop_attempted = True
                        # Prefer slot/topic follow-up first (often loop-like), then fall back to engine ladder
                        chosen = _pick_slot_followup_frame_id(current_engine, slot_names, recent, memory)
                        if chosen is None:
                            # Fall back: next ladder frame, but avoid known weak loop frames if we have alternatives in engine
                            chosen = _select_next_frame_ladder_avoiding(
                                current_engine,
                                recent,
                                avoid_frame_ids=_WEAK_LOOP_FRAME_IDS,
                                memory=memory,
                            )
                        if chosen and _is_loop_candidate(chosen):
                            chosen_turn_type = "loop_question"
                # Depth cap enforcement: if reached, force next ask/bridge and reset depth
                if chosen is None:
                    if curiosity_depth >= MAX_CURIOSITY_DEPTH:
                        # Force ask/bridge; reset depth
                        if prefer_bridge or force_bridge:
                            chosen = _select_next_frame_bridge(current_engine, recent, use_recovery_order=prefer_bridge, memory=memory)
                        if chosen is None and not force_bridge:
                            chosen = _select_next_frame_ladder(current_engine, recent, memory=memory)
                        curiosity_depth = 0
                        chosen_turn_type = "question"
                    else:
                        # Soft chaining: slot/topic preference first, then existing bridge/ladder order
                        if last_turn_was_answer and meaningful:
                            chosen = _pick_slot_followup_frame_id(current_engine, slot_names, recent, memory)
                            if chosen and _is_loop_candidate(chosen):
                                chosen_turn_type = "loop_question"
                                curiosity_depth = min(curiosity_depth + 1, MAX_CURIOSITY_DEPTH)
                        if chosen is None:
                            if prefer_bridge or force_bridge:
                                chosen = _select_next_frame_bridge(current_engine, recent, use_recovery_order=prefer_bridge, memory=memory)
                            if chosen is None and not force_bridge:
                                chosen = _select_next_frame_ladder_avoiding(
                                    current_engine,
                                    recent,
                                    avoid_frame_ids=_WEAK_LOOP_FRAME_IDS,
                                    memory=memory,
                                )

                if not chosen:
                    self._json_error(400, "no frame available for next question")
                    return
                frame_id = chosen
                frame_rec_chosen = _frames_by_id.get(frame_id, {})
                engine_id = (frame_rec_chosen.get("engine") or current_engine or "unknown").strip()
                # Step 7: include learner_memory and persona in response so client can show continuity
                if memory is not None:
                    _phase10_learner_memory = dict(memory)
                _phase10_persona_id = (cs.get("persona_id") or payload.get("persona_id") or "").strip() or None
                _phase10_turn_type = chosen_turn_type
            else:
                frame_id  = payload.get("frame_id", "unknown")
                engine_id = payload.get("engine_id", "unknown")
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
                "system_note":         "phase7.4 static options"
            }
            # Phase 10.5: reaction micro-layer prefix (if generated above)
            if payload.get("next_question") and isinstance(payload.get("conversation_state"), dict):
                if reaction_prefix_text:
                    # Keep it lightweight: prepend only if the next frame is a question (avoid double-reactive turns)
                    if "？" in (frame_rec.get("text") or ""):
                        response["frame_text"] = f"{reaction_prefix_text}{response['frame_text']}"
                        response["system_note"] = "phase10.5 reaction_micro_layer"
                        response["reaction_used_fallback"] = bool(reaction_used_fallback)

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
                    should = _should_surface_curiosity(cs, meaningful=meaningful, last_partner_was_loop=(chosen_turn_type == "loop_question"), last_partner_had_reaction=bool(reaction_prefix_text))
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


if __name__ == "__main__":
    port = 8765
    print(f"[ui_server] Listening on http://localhost:{port}")
    HTTPServer(("", port), Handler).serve_forever()
