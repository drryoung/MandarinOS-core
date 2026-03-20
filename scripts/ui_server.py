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
P_LOOP_WHEN_TRIGGERED = 0.75  # prefer loop/curiosity on same topic before bridging
MAX_CURIOSITY_DEPTH = 2
EARLY_EXCHANGES = 3
# Interest-driven responsiveness tuning (10.5 refinement)
INTEREST_MEDIUM_THRESHOLD = 1
INTEREST_HIGH_THRESHOLD = 3
P_CURIOUS_WHEN_INTEREST_MED = 0.60
P_CURIOUS_WHEN_INTEREST_HIGH = 0.80
P_BRIDGE_WHEN_INTEREST_HIGH = 0.70
MAX_SAME_ENGINE_AFTER_INTEREST = 1
MAX_SAME_SLOT_CHAIN_AFTER_INTEREST = 1
INTEREST_FORCE_WINDOW_TURNS = 1
MIN_SAME_ENGINE_CHAIN_BEFORE_BRIDGE = 2

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
    # Identity flow: name → how people call you → meaning → evaluations.
    "identity": ["f_ask_you_name", "p2_id_2", "f_ask_name_meaning", "p2_id_4", "p2_id_5"],  # core then treasure/loop
    "place": ["f_from_where", "f_place_like_there", "frame.location.live_question", "p2_pl_1", "p2_pl_2", "p2_pl_3", "p2_pl_4"],  # core then treasure/loop (生活怎么样, 好吃的, 喜欢去, 方便吗)
    "family": ["f_have_family", "f_have_siblings", "p2_fa_1", "p2_fa_2", "p2_fa_5"],  # core then treasure/loop (跟家人住, 多久见, 周末做什么)
    # Work: compact high-interest sequence approved by user.
    "work": ["f_what_work", "f_like_work", "p2_wk_1", "p2_wk_2", "p2_wk_3", "p2_wk_4", "p2_wk_5"],
    "hobby": ["f_what_hobby", "f_like_do_what", "f_often_do", "f_difficult_ma", "f_recommend_ma", "f_weekend_do", "f_like_chinese_culture", "f_like_what", "f_collect_what", "p2_hb_1", "p2_hb_2", "p2_hb_4", "p2_hb_5"],  # core → treasure → weekend/culture
    "travel": ["f_travel_where", "f_want_go_where", "p2_tr_1", "p2_tr_2", "p2_tr_3", "p2_tr_4"],  # core then treasure/loop (哪些国家, 最喜欢哪里, 好玩的, 旅行怎么样)
    "food": ["f_food_what_good", "f_food_famous_dish", "f_food_tasty", "f_food_like_spicy", "f_food_expensive"],  # core → treasure
    "life": [],
}
# A frame id may only be chosen if all of its "after" frames are in recent_frame_ids (already asked).
_FRAME_AFTER: dict = {
    "f_ask_name_meaning": ["f_ask_you_name"],  # don't ask name meaning before asking name
    # Identity follow-up assumes a name exists
    "p2_id_2": ["f_ask_you_name"],
}

# "OR" dependencies: any one prerequisite is sufficient.
# Place follow-ups need an established referent ("there"/CITY) first; prevents out-of-context “那里”.
_FRAME_AFTER_ANY: dict = {
    "f_place_like_there": ["f_from_where", "frame.location.live_question"],
    "p2_pl_1": ["f_from_where", "frame.location.live_question"],
    "p2_pl_2": ["f_from_where", "frame.location.live_question"],
    "p2_pl_3": ["f_from_where", "frame.location.live_question"],
    "p2_pl_4": ["f_from_where", "frame.location.live_question"],
}


def _deictic_context_fresh(fid: str, recent_frame_ids: list, window: int = 4) -> bool:
    """
    Extra recency guard for deictic/place-referential questions like "那里".
    Even if a place anchor exists somewhere in history, require it to be recent.
    """
    anchors = {
        "f_place_like_there": ["f_from_where", "frame.location.live_question", "p2_pl_4", "p2_pl_2"],
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
    "place": ["food", "family", "work", "travel", "identity"],
    "family": ["identity", "place", "work"],
    "work": ["identity", "place", "family"],
    "hobby": ["identity", "travel", "food"],
    "travel": ["place", "hobby", "food"],
    "food": ["place", "travel", "hobby", "life"],
    "life": ["identity", "place", "family"],
}

# When prefer_bridge (recovery / change topic): try engines in this order so the next question feels like a natural switch (place/identity/family first), not a jump to food/travel.
_RECOVERY_BRIDGE_ENGINE_ORDER: list = ["place", "identity", "family", "work", "hobby", "travel", "food", "life"]
_BRIDGE_PREFIXES: list = ["对了，", "顺便问一下，", "说到这个，"]

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
    # CITY: prefer convenience before “life怎么样” because p2_pl_1 is weak
    # Also keep p2_pl_3 out of the slot path (known weak).
    "CITY": ["p2_pl_4", "p2_pl_2", "f_place_like_there", "p2_pl_1"],
    # JOB: compact high-interest sequence approved by user.
    "JOB":  ["f_like_work", "p2_wk_1", "p2_wk_2", "p2_wk_3", "p2_wk_4", "p2_wk_5"],
    # DISH: prefer taste/spicy before generic “famous dish”
    "DISH": ["f_food_tasty", "f_food_like_spicy", "f_food_famous_dish"],
    "NAME": ["p2_id_4", "p2_id_5"],
    # TRAVEL: deepen on destination/motivation before generic country checklist.
    "TRAVEL": ["f_want_go_where", "p2_tr_2", "p2_tr_3", "p2_tr_4", "p2_tr_1"],
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

    # Soft-chaining: if user answer itself names food while in place thread, prioritize DISH.
    if _looks_food_related_answer(txt) and "DISH" not in slots:
        slots.insert(0, "DISH")
    elif fid == "p2_pl_2" and "DISH" not in slots:
        # p2_pl_2 asks about food in {CITY}; treat answers as dish/topic-bearing by default.
        slots.insert(0, "DISH")
    if _looks_travel_related_answer(txt) and "TRAVEL" not in slots:
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
    if any(k in text for k in ("因为", "所以", "觉得", "但是", "最", "其实")):
        score += 1
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
    if "？" in text or "?" in text:
        return True
    # Common interrogative markers without explicit punctuation
    starters = ("怎么", "为什么", "哪里", "谁", "什么时候", "多少", "几", "哪儿", "哪裡")
    if text.startswith(starters):
        return True
    if text.endswith("吗") or ("吗" in text and len(text) <= 8):
        return True
    return False


def _assistant_name_from_persona(persona: Optional[dict]) -> str:
    # Keep deterministic and short; don't rely on extra schema.
    if persona and isinstance(persona, dict):
        n = (persona.get("name") or persona.get("assistant_name") or "").strip()
        if n:
            return n
    return "MandarinOS"


def _answer_user_question_prefix(last_answer: Optional[dict], persona: Optional[dict]) -> Optional[str]:
    """
    Return a short prefix that answers common counter-questions without adding new API turns.
    We only handle the high-value early case: user asks what to call the app.
    """
    if not _is_user_question(last_answer):
        return None
    t = (last_answer.get("submitted_text") or last_answer.get("selected_option_hanzi") or "").strip()
    if not t:
        return None
    # If user asked how to address the app, answer with app name.
    if ("叫你" in t) or ("怎么叫" in t) or ("你叫什么" in t) or ("你叫啥" in t):
        an = _assistant_name_from_persona(persona)
        return f"你可以叫我{an}。"
    return None


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
    text = (last_answer.get("submitted_text") or "").strip()
    if not text:
        text = (last_answer.get("selected_option_hanzi") or "").strip()
    return _is_greeting_text(text)


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
                if not _frame_deps_satisfied(fid, recent, recent_list):
                    continue
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
    recent_list = list(recent_frame_ids or [])
    def _deps_satisfied(fid: str) -> bool:
        return _frame_deps_satisfied(fid, recent, recent_list)
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

    recent_list = list(recent_frame_ids or [])
    def _deps_satisfied(fid: str) -> bool:
        return _frame_deps_satisfied(fid, recent, recent_list)

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

        if path == "/api/run_turn":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except Exception as e:
                print(f"[ui_server] bad request body: {e}")
                payload = {}

            print(f"[ui_server] /api/run_turn: {payload}")

            # Direction actions: learner asks back/why, partner gives short stub, then UI resumes thread.
            direction_intent = (payload.get("direction_intent") or "").strip().lower()
            if direction_intent in ("reverse", "why"):
                cs = payload.get("conversation_state") or {}
                persona_id = (payload.get("persona_id") or cs.get("persona_id") or "").strip() or None
                persona = _get_persona(persona_id) if _get_persona else None
                engine_id = (cs.get("current_engine") or "unknown").strip()
                last_partner_frame_id = (cs.get("last_partner_frame_id") or "").strip()
                stub = _direction_stub(direction_intent, engine_id, last_partner_frame_id, persona)
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
            bridge_prefix_text = ""
            loop_attempted = False
            chosen_turn_type = "question"
            new_memory_written = False
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
                                    reaction_prefix_text = _pick_reaction_text(current_engine, seed)
                                    reaction_used_fallback = True
                                else:
                                    reaction_prefix_text = (_frames_by_id.get(rid) or {}).get("text") or ""
                            else:
                                reaction_prefix_text = _pick_reaction_text(current_engine, seed)
                                reaction_used_fallback = True

                # User-question override (spec-friendly, no schema changes):
                # if the user asked a question (counter-question), answer it via a short prefix first.
                persona_id = (payload.get("persona_id") or cs.get("persona_id") or "").strip() or None
                persona = _get_persona(persona_id) if _get_persona else None
                uq_prefix = _answer_user_question_prefix(last_answer, persona) if last_turn_was_answer else None
                if uq_prefix:
                    # Put the answer before any reaction so it reads naturally.
                    reaction_prefix_text = f"{uq_prefix}{reaction_prefix_text}"

                # Partner curiosity: prefer loop when triggered and depth allows, but avoid weak loop frames if possible
                chosen = None
                chosen_turn_type = "question"
                loop_attempted = False
                listening_move_selected = "none"
                listening_move_reason = ""
                if force_food_followup:
                    chosen = _pick_slot_followup_frame_id(current_engine, ["DISH"], recent, memory)
                    if chosen:
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
                    bridge_allowed = (
                        force_bridge
                        or prefer_bridge
                        or (same_engine_chain_count >= MIN_SAME_ENGINE_CHAIN_BEFORE_BRIDGE)
                    )
                    if pending_listening_move or force_listening or chain_exceeded:
                        seed_base = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}/interest"
                        gate_br = _stable_gate(seed_base + "/br")
                        p_br = P_BRIDGE_WHEN_INTEREST_HIGH if interest_level == "high" else 0.35
                        # Curiosity-first policy: whenever we have meaningful/unscripted signal and depth allows,
                        # attempt a same-topic probe BEFORE considering bridge.
                        has_curiosity_signal = bool(slot_names) or bool(unscripted_probe_first) or bool(meaningful)
                        if curiosity_depth < MAX_CURIOSITY_DEPTH and has_curiosity_signal:
                            chosen = _pick_slot_followup_frame_id(current_engine, slot_names, recent, memory)
                            if chosen is None:
                                chosen = _select_next_frame_ladder_avoiding(
                                    current_engine,
                                    recent,
                                    avoid_frame_ids=_WEAK_LOOP_FRAME_IDS,
                                    memory=memory,
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
                            chosen = _select_next_frame_bridge(current_engine, recent, use_recovery_order=prefer_bridge, memory=memory)
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
                            pending_listening_move = False
                            listening_wait_turns = 0
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
                        if last_turn_was_answer and (not user_asked_question) and meaningful:
                            chosen = _pick_slot_followup_frame_id(current_engine, slot_names, recent, memory)
                            if chosen and _is_loop_candidate(chosen):
                                chosen_turn_type = "loop_question"
                                curiosity_depth = min(curiosity_depth + 1, MAX_CURIOSITY_DEPTH)
                                pending_listening_move = False
                                listening_wait_turns = 0
                        if chosen is None:
                            if prefer_bridge or force_bridge:
                                chosen = _select_next_frame_bridge(current_engine, recent, use_recovery_order=prefer_bridge, memory=memory)
                                if chosen:
                                    pending_listening_move = False
                                    listening_wait_turns = 0
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

                # Hard guarantee: if this turn classified as medium/high interest but no explicit
                # listening move was selected, force a probe attempt on the very next turn.
                if interest_level in ("medium", "high") and listening_move_selected == "none":
                    pending_listening_move = True
                    listening_wait_turns = max(int(listening_wait_turns or 0), INTEREST_FORCE_WINDOW_TURNS)

                # Identity coherence gate: don't ask name-meta questions unless "name" is established.
                # This prevents post-greeting jumps like “你觉得你的名字怎么样？” with no context.
                engine_norm = (current_engine or "").strip().lower()
                if engine_norm == "identity":
                    # Greeting reset: regardless of remembered name, don't jump into "name evaluation" immediately.
                    # First ask for/confirm the name in-session so the dialogue doesn't feel like an interrogation.
                    if last_turn_was_answer and _is_greeting_answer(last_answer):
                        chosen = "f_ask_you_name"
                        chosen_turn_type = "question"
                    else:
                        name_meta_frames = {"p2_id_4", "p2_id_5", "f_ask_name_meaning", "p2_id_2"}
                        # In-session name context: user just answered a name-related question
                        has_name_context_now = ("NAME" in (slot_names or []))
                        has_name_in_memory = _has_learner_name(memory)
                        if chosen in name_meta_frames and (not has_name_context_now) and (not has_name_in_memory):
                            # Force the basic name question first (unless suppressed for some reason)
                            fallback = "f_ask_you_name"
                            if fallback not in set(recent or []) and not _should_suppress_ask_frame(fallback, memory, recent or [], RECALL_INTERVAL_TURNS):
                                chosen = fallback
                                chosen_turn_type = "question"
                            else:
                                # If we can't ask name, switch topic to avoid awkward interrogation
                                bridged = _select_next_frame_bridge(current_engine, recent, use_recovery_order=True, memory=memory)
                                if bridged:
                                    chosen = bridged
                                    chosen_turn_type = "question"

                frame_id = chosen
                frame_rec_chosen = _frames_by_id.get(frame_id, {})
                engine_id = (frame_rec_chosen.get("engine") or current_engine or "unknown").strip()
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
                    bridge_prefix_text = _stable_pick(_BRIDGE_PREFIXES, bridge_seed) or "对了，"
                    # Avoid awkward double prefix like "顺便问一下，哦。"
                    reaction_prefix_text = ""
                # Step 7: include learner_memory and persona in response so client can show continuity
                if memory is not None:
                    _phase10_learner_memory = dict(memory)
                _phase10_persona_id = (cs.get("persona_id") or payload.get("persona_id") or "").strip() or None
                if chosen_turn_type == "loop_question":
                    same_engine_chain_count += 1
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
                last_user_text = _answer_text_from_last_answer(last_answer) if last_turn_was_answer else _norm_text(cs.get("last_user_text"))
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
