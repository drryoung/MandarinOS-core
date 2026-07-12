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
import datetime

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
    from learner_memory import clear as _lm_clear
    from learner_memory_capture import capture_from_turn as _capture_from_turn, get_memory_field_for_frame as _get_memory_field_for_frame
    from learner_memory_capture import normalize_place_name as _normalize_place_name
except ImportError:
    _lm_load = _lm_save = _lm_apply_updates = _capture_from_turn = None
    _lm_clear = None
    _get_memory_field_for_frame = None
    _normalize_place_name = None
# Beta progress persistence (per-learner snapshot files)
try:
    from progress_store import load_snapshots as _ps_load_snapshots
    from progress_store import save_snapshot as _ps_save_snapshot
    from progress_store import load_all as _ps_load_all
except ImportError:
    _ps_load_snapshots = _ps_save_snapshot = _ps_load_all = None
# Longitudinal capability estimator (additive — no scorecard/selector deps)
try:
    from capability_estimator import compute as _ce_compute
except ImportError:
    _ce_compute = None
# Beta learner profile (practice comfort level per learner_id)
try:
    from beta_profile import load_profile as _bp_load_profile
    from beta_profile import save_profile as _bp_save_profile
except ImportError:
    _bp_load_profile = _bp_save_profile = None
# Session Intelligence — Phase 0 capture layer (additive, flag-gated)
try:
    from session_intelligence import (
        is_enabled        as _si_is_enabled,
        build_session_record as _si_build_record,
        save_session_record  as _si_save_record,
    )
except ImportError:
    _si_is_enabled = _si_build_record = _si_save_record = None

_LEARNER_MEMORY_FIELD_KEYS = (
    "learner_name",
    "hometown",
    "lives_in",
    "job_or_study",
    "family",
    "favourite_food",
)


def _learner_memory_is_empty(mem: Optional[dict]) -> bool:
    """True when no factual learner memory fields are populated."""
    if not isinstance(mem, dict):
        return True
    return all(not (mem.get(k) or "").strip() for k in _LEARNER_MEMORY_FIELD_KEYS)


def _is_first_time_beta_user(learner_id: str) -> bool:
    """Server truth: no progress snapshots and no saved learner memory for this learner_id."""
    lid = (learner_id or "").strip()
    if not lid:
        return False
    if _ps_load_snapshots and _ps_load_snapshots(lid):
        return False
    mem = _lm_load(lid) if _lm_load else {}
    return _learner_memory_is_empty(mem)

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

# Emit deployed git commit + branch so Railway logs make the running version obvious.
#
# NOTE: this is captured once at process startup, so /api/version reports the
# commit the running process was LAUNCHED from — it will not change if you commit
# while the server keeps running (restart to pick up a new HEAD). Precedence:
#   1. live `git rev-parse HEAD` (authoritative for the checked-out tree);
#   2. RAILWAY_GIT_COMMIT_SHA (build metadata) when git is unavailable;
#   3. "unknown" — never a blank or truncated/misleading value.
def _resolve_version():
    try:
        import subprocess as _sp
        _sha_full = _sp.check_output(["git", "rev-parse", "HEAD"],
                                     cwd=str(REPO_ROOT), text=True, stderr=_sp.DEVNULL).strip()
        _branch = _sp.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                   cwd=str(REPO_ROOT), text=True, stderr=_sp.DEVNULL).strip()
        if _sha_full:
            return _sha_full[:7], _sha_full, (_branch or "unknown"), "git"
    except Exception:
        pass
    _env_sha = (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "").strip()
    _env_branch = (os.environ.get("RAILWAY_GIT_BRANCH") or "").strip()
    if _env_sha:
        return _env_sha[:7], _env_sha, (_env_branch or "unknown"), "railway_env"
    return "unknown", "unknown", (_env_branch or "unknown"), "unknown"


_git_sha, _git_sha_full, _git_branch, _git_sha_source = _resolve_version()
print(f"[ui_server] version   = {_git_sha}  branch={_git_branch}  (source={_git_sha_source})")

# ── Data directory — log effective path so Railway logs make storage issues obvious ──
_DATA_DIR_ENV = os.environ.get("MANDARINOS_DATA_DIR", "")
_DATA_DIR_EFFECTIVE = _DATA_DIR_ENV if _DATA_DIR_ENV else str(REPO_ROOT / "data")
print(f"[ui_server] DATA_DIR  = {_DATA_DIR_EFFECTIVE}  "
      f"{'(from MANDARINOS_DATA_DIR env)' if _DATA_DIR_ENV else '(default — ephemeral on Railway; set MANDARINOS_DATA_DIR to a persistent volume path)'}")

# ── ASR diagnostic tracing (branch: diagnostics/asr-trace) ────────────────────
# Additive, behaviour-free instrumentation to trace spoken-vs-typed pipeline
# divergence. It MUST NOT change ASR selection, submitted text, transcript
# display, normalization, intent routing, or the response the learner sees.
# Records are only captured/returned/stored when MANDARINOS_DIAG_TOKEN is set,
# so production behaviour and payloads are byte-identical when it is unset.
# Raw speech transcripts may contain PII, so the collection endpoint is
# token-gated and the store lives under the (non-web-served) data dir.
_DIAG_TOKEN = (os.environ.get("MANDARINOS_DIAG_TOKEN") or "").strip()
_DIAG_DIR = Path(_DATA_DIR_EFFECTIVE) / "diag"
_DIAG_TRACE_FILE = _DIAG_DIR / "asr_traces.jsonl"


def _diag_enabled() -> bool:
    return bool(_DIAG_TOKEN)


def _diag_normalizer_name() -> str:
    """Report the normalization path actually present in THIS build.

    Do not assume _normalize_zh_for_routing exists (it is absent on older
    deployed branches); report 'none' when no routing normalizer is defined.
    """
    return "_normalize_zh_for_routing" if "_normalize_zh_for_routing" in globals() else "none"


def _diag_append(kind: str, rec: dict) -> None:
    """Append one diagnostic record as JSONL. Never raises into the request path."""
    if not _diag_enabled():
        return
    try:
        _DIAG_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": kind,
            "logged_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds"),
            "server_sha": _git_sha,
            "server_branch": _git_branch,
        }
        payload.update(rec or {})
        with open(_DIAG_TRACE_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _diag_finalize_response(response: dict, cap: Optional[dict]) -> None:
    """Attach server-side response fields to the diag record and persist it.

    No-op when cap is None (diagnostics off or no trace id). Never alters the
    learner-facing content of `response` beyond adding a `diag` metadata field
    that the client ignores unless diagnostics are enabled.
    """
    if cap is None or not isinstance(response, dict):
        return
    try:
        _cr = response.get("counter_reply")
        _cr_txt = _cr.get("zh") if isinstance(_cr, dict) else (_cr if isinstance(_cr, str) else "")
        cap["response_source"] = "counter_reply" if _cr_txt else "frame_text"
        cap["final_response_text"] = _cr_txt or response.get("frame_text") or ""
        cap["frame_id"] = response.get("frame_id") or ""
        cap["engine_id"] = response.get("engine_id") or ""
        cap["turn_type"] = response.get("turn_type") or ""
        cap["intent"] = "user_question" if cap.get("user_asked_question") else (response.get("turn_type") or "")
        response["diag"] = cap
        _diag_append("server_turn", cap)
    except Exception:
        pass


if _diag_enabled():
    print(f"[ui_server] DIAG      = ENABLED (asr-trace store: {_DIAG_TRACE_FILE})")
else:
    print("[ui_server] DIAG      = disabled (set MANDARINOS_DIAG_TOKEN to enable ASR tracing)")

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


def _recovery_phrases_runtime_payload() -> Optional[dict]:
    """Build recovery_phrases.runtime.json from content/recovery_phrases.json when artifact is missing."""
    path = CONTENT_DIR / "recovery_phrases.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        phrases = _flatten_recovery_phrases_for_maps(raw)
        if not phrases:
            return None
        out: dict = {
            "schema": "recovery_phrases_v1",
            "phrases": phrases,
            "default_for_not_understood": raw.get("default_for_not_understood"),
        }
        if raw.get("schema_version"):
            out["schema_version"] = raw["schema_version"]
        if raw.get("core_set_ids"):
            out["core_set_ids"] = raw["core_set_ids"]
        return out
    except (OSError, json.JSONDecodeError):
        return None


# Persona deflect phrases: loaded from content/recovery_phrases.json (use=persona_deflect).
# Adding/editing a phrase only requires editing that file — no server code change.
_persona_deflect_phrases: dict = {}     # topic -> [hanzi_str, ...]  (for _persona_deflect picker)
_persona_deflect_en_map: dict = {}      # hanzi_str -> text_en       (for hint lookup)
_persona_deflect_pinyin_map: dict = {}  # hanzi_str -> pinyin      (for counter_reply_pinyin)
_frustration_repair_phrases: list = []  # [(hanzi, text_en), ...]  (use=frustration_repair)
_travel_intent_followup_templates: dict = {}  # "dest" -> (zh_tpl, en_tpl), "generic" -> (zh, en)
_disclosure_empathy_phrases: list = []  # [(hanzi, text_en), ...]  (use=learner_disclosure_empathy)
_persona_challenge_phrases: list = []   # [(hanzi, text_en), ...]  (use=persona_challenge)
_persona_cooking_phrases: list = []     # [(hanzi, text_en), ...]  (use=persona_cooking_reply)
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
            if _p.get("use") == "frustration_repair":
                _hz = (_p.get("hanzi") or "").strip()
                if _hz:
                    _frustration_repair_phrases.append((_hz, (_p.get("text_en") or "").strip()))
                    _en = (_p.get("text_en") or "").strip()
                    if _en:
                        _persona_deflect_en_map[_hz] = _en
                    _py = (_p.get("pinyin") or "").strip()
                    if _py:
                        _persona_deflect_pinyin_map[_hz] = _py
            if _p.get("use") == "travel_intent_followup":
                _pid_ti = (_p.get("id") or "").strip()
                _hz_ti  = (_p.get("hanzi") or "").strip()
                _en_ti  = (_p.get("text_en") or "").strip()
                if _pid_ti == "travel_intent_dest_followup" and _hz_ti:
                    _travel_intent_followup_templates["dest"] = (_hz_ti, _en_ti)
                elif _pid_ti == "travel_intent_generic_followup" and _hz_ti:
                    _travel_intent_followup_templates["generic"] = (_hz_ti, _en_ti)
            if _p.get("use") == "learner_disclosure_empathy":
                _hz = (_p.get("hanzi") or "").strip()
                if _hz:
                    _disclosure_empathy_phrases.append((_hz, (_p.get("text_en") or "").strip()))
            if _p.get("use") == "persona_challenge":
                _hz = (_p.get("hanzi") or "").strip()
                if _hz:
                    _persona_challenge_phrases.append((_hz, (_p.get("text_en") or "").strip()))
            if _p.get("use") == "persona_cooking_reply":
                _hz = (_p.get("hanzi") or "").strip()
                if _hz:
                    _persona_cooking_phrases.append((_hz, (_p.get("text_en") or "").strip()))
                    _en = (_p.get("text_en") or "").strip()
                    if _en:
                        _persona_deflect_en_map[_hz] = _en
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


def _frustration_repair_reply(seed: str = "") -> tuple:
    """Return (zh, en) apology/repair for a frustrated or insulting learner turn.
    Loaded from content/recovery_phrases.json (use=frustration_repair).
    Returns ("", "") when the phrase bank has not been loaded (fail-safe — no inline Chinese)."""
    if not _frustration_repair_phrases:
        return ("", "")
    zh = _stable_pick([p[0] for p in _frustration_repair_phrases], seed or "frustration") \
         or _frustration_repair_phrases[0][0]
    en = next((e for (z, e) in _frustration_repair_phrases if z == zh), "")
    return (zh, en)


_DISCLOSURE_FAMILY_WORDS: frozenset = frozenset({
    "妈妈", "妈", "爸爸", "爸", "家人", "家里", "爷爷", "奶奶", "爱人",
    "老婆", "丈夫", "孩子", "儿子", "女儿", "弟弟", "妹妹", "哥哥", "姐姐",
})
_DISCLOSURE_HEALTH_WORDS: frozenset = frozenset({
    "身体", "生病", "不好", "住院", "手术", "很担心", "不舒服", "出事", "病了",
    "出了事", "有点问题", "不太好", "不大好", "去世", "走了",
})


def _is_learner_disclosure(text: str) -> bool:
    """True when the learner discloses a family health/concern situation.

    Matches: 我(妈妈|爸爸|家人…)(身体不好|生病|很担心…) / 我最近很担心 / etc.
    Deliberately NOT gated on user_asked_question — disclosures are statements.
    """
    t = (text or "").strip()
    if not t:
        return False
    # Bare worry expression without a specific family member:
    # only "我最近很担心" is narrow enough to be a disclosure; bare "我很担心" alone is ambiguous.
    if "我最近很担心" in t:
        return True
    # First-person + family word present
    if "我" not in t:
        return False
    has_family = any(fw in t for fw in _DISCLOSURE_FAMILY_WORDS)
    has_health = any(hw in t for hw in _DISCLOSURE_HEALTH_WORDS)
    return has_family and has_health


def _disclosure_empathy_reply(seed: str = "") -> tuple:
    """Return (zh, en) empathy response for a learner family/health disclosure.
    Loaded from content/recovery_phrases.json (use=learner_disclosure_empathy).
    Returns ("", "") when the phrase bank has not been loaded (fail-safe)."""
    if not _disclosure_empathy_phrases:
        return ("", "")
    zh = _stable_pick([p[0] for p in _disclosure_empathy_phrases], seed or "disclosure") \
         or _disclosure_empathy_phrases[0][0]
    en = next((e for (z, e) in _disclosure_empathy_phrases if z == zh), "")
    return (zh, en)


_PERSONA_CHALLENGE_PATTERNS: tuple = (
    r"你是中国人.*应该知道",
    r"你应该知道(吧|啊|啦)",
    r"中国人.*应该知道",
    r"你知道.{0,6}(中国|历史|文化).{0,6}(吗|吧|啦)",
)
_PERSONA_CHALLENGE_RE = re.compile("|".join(_PERSONA_CHALLENGE_PATTERNS))


def _is_persona_challenge(text: str) -> bool:
    """True when the learner issues a playful challenge to the persona's Chinese knowledge."""
    t = (text or "").strip()
    if not t:
        return False
    return bool(_PERSONA_CHALLENGE_RE.search(t))


def _persona_challenge_reply(seed: str = "") -> tuple:
    """Return (zh, en) response for a persona challenge / common-knowledge prompt.
    Loaded from content/recovery_phrases.json (use=persona_challenge).
    Returns ("", "") when the phrase bank has not been loaded (fail-safe)."""
    if not _persona_challenge_phrases:
        return ("", "")
    zh = _stable_pick([p[0] for p in _persona_challenge_phrases], seed or "challenge") \
         or _persona_challenge_phrases[0][0]
    en = next((e for (z, e) in _persona_challenge_phrases if z == zh), "")
    return (zh, en)


# ASR-junk fragments that must never surface inside a rendered learner-facing line
# (e.g. a corrupted stored place "等你等新西兰的南方" filling a "…有什么特别的？" frame).
_ASR_JUNK_OUTPUT_FRAGMENTS: tuple = (
    "等你等", "等一等", "等等你", "等你", "那个那个", "就是就是", "呃呃", "嗯嗯",
)


def _repair_asr_junk_text(text: Optional[str]) -> str:
    """Strip known ASR-junk fragments from learner-facing Chinese so corrupted
    stored/echoed values never reach the learner (regression: '等你等…')."""
    if not text:
        return text or ""
    out = text
    for junk in _ASR_JUNK_OUTPUT_FRAGMENTS:
        if junk in out:
            out = out.replace(junk, "")
    # Collapse a leftover leading connective particle from the removed junk.
    out = out.lstrip("的，,。.、 ")
    return out


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
    # Place flow (Phase 12C final + Phase 12D.1 distance follow-ups):
    # origin → current city → distance? → special → food → travel time? → hometown → travel bridge → who with → why.
    # p2_pl_far  (离那儿远吗？)      — skip_when=city_is_well_known → only fires for unusual/overseas places.
    # f_place_distance_time (多久？) — natural after distance question; no skip_when so fires broadly.
    "place": [
        "f_from_where",           # 1. 你是哪里人？
        "f_live_where",           # 2. 你现在住哪里？
        "p2_pl_far",              # 3. 离那儿远吗？  (skipped for 北京/上海/广州; surfaces for overseas/unusual)
        "f_place_special",        # 4. 这里有什么特别的？
        "f_place_food",           # 5. 这里有什么好吃的？
        "f_place_distance_time",  # 6. 从你那儿到那边要多久？ (depth follow-up after distance confirmed)
        "f_home_where",           # 7. 你老家在哪儿？
        "f_place_travel",         # 8. 你会去别的地方吗？
        "f_live_with_who",        # 9. 你跟谁一起住？
        "f_place_why_live",       # 10. 你为什么住在这里？
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
    # Story elicitation only after the name-story question (not p2_id_ext1 — that blocked the elicit in identity ladder).
    "f_name_story_elicit": ["f_name_story"],
    # "Why's that?" only makes sense after the future-plans question has been asked
    "f_probe_work_why_quit": ["f_probe_work_future"],
}

# Phase 11.1: OPEN frames that must not be re-entered once the session is established (exchange_count ≥ 2).
# These are opening gambits — re-asking them after real conversation has begun feels unnatural.
_IDENTITY_OPEN_FRAMES: frozenset = frozenset({"f_ask_you_name"})

# "OR" dependencies: any one prerequisite is sufficient.
# Place follow-ups need an established referent ("there"/CITY) first; prevents out-of-context “那里”.
_FRAME_AFTER_ANY: dict = {
    # Note: recent_frame_ids stores the un-normalised server frame_id ("f_live_where"), NOT
    # the canonical alias "frame.location.live_question". Both forms are listed so deps pass.
    "f_place_like_there": ["f_from_where", "f_live_where", "frame.location.live_question"],
    "p2_pl_1": ["f_from_where", "f_live_where", "frame.location.live_question"],
    "p2_pl_2": ["f_from_where", "f_live_where", "frame.location.live_question"],
    "p2_pl_3": ["f_from_where", "f_live_where", "frame.location.live_question"],
    "p2_pl_4": ["f_from_where", "f_live_where", "frame.location.live_question"],
    "p2_pl_far": ["f_from_where", "f_live_where", "frame.location.live_question"],
    # Phase 12D.1: distance depth frames -- place anchor required before asking how long / how to get there.
    "f_place_distance_time":      ["f_from_where", "f_live_where", "frame.location.live_question"],
    "f_place_distance_ref":       ["f_from_where", "f_live_where", "frame.location.live_question"],
    "f_place_distance_transport": ["f_from_where", "f_live_where", "frame.location.live_question"],
    # Phase 12: EXTEND frame references "where you live" so needs place context first.
    "p2_pl_ext1": ["f_from_where", "f_live_where", "frame.location.live_question"],
    # "Why do you like it there?" presupposes "do you like it there?" was already asked.
    "f_place_why_like": ["f_place_like_there"],
}


def _deictic_context_fresh(fid: str, recent_frame_ids: list, window: int = 4) -> bool:
    """
    Extra recency guard for deictic/place-referential questions like "那里".
    Even if a place anchor exists somewhere in history, require it to be recent.
    """
    anchors = {
        "f_place_like_there": ["f_from_where", "f_live_where", "frame.location.live_question", "p2_pl_far", "p2_pl_4", "p2_pl_2"],
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
    "family":   ["哦。", "真不错！", "不错啊！"],
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

# Recovery-request markers — split by recovery type so each gets a tailored response.
# _REPEAT_REQUEST_MARKERS : explicit "say it again" → _clarify_app_question (re-read Chinese)
# _SLOWER_REQUEST_MARKERS : "say it slower"       → _clarify_app_question (client slows TTS)
# _MEANING_REQUEST_MARKERS: "what does this mean" → _meaning_recovery_reply (English + simpler)
# _EXAMPLE_REQUEST_MARKERS: "give me an example"  → _example_recovery_reply
_REPEAT_REQUEST_MARKERS: tuple = (
    "再说一遍", "再说一次", "再说一起", "再说一下", "请再说",
)
_SLOWER_REQUEST_MARKERS: tuple = (
    "慢一点", "说慢", "慢慢说", "慢一些", "慢点说",
)
_MEANING_REQUEST_MARKERS: tuple = (
    "什么意思", "意思是什么", "是什么意思",
)
_EXAMPLE_REQUEST_MARKERS: tuple = (
    "给我一个例子", "举个例子",
)
# Very short bare-repeat utterances (≤ 2 CJK chars + optional punct).
_BARE_REPEAT_UTTERANCES: frozenset = frozenset({"啊", "啊？", "嗯？", "哦？", "啥", "啥？"})

# Soft closing reactions: emitted when late-session + topic completion suppress bridge
# and no next move (probe or ladder frame) is available. Terminal / pause move — no follow-up.
# Format: (hanzi, pinyin, english)
_CLOSING_REACTIONS: list = [
    ("这样啊。", "Zhèyàng a.", "I see / so that's how it is."),
    ("这样挺好。", "Zhèyàng tǐng hǎo.", "That sounds good."),
    ("真不错啊！", "Zhēn bùcuò a!", "That's really nice!"),
]

# Food-keyword closing reactions: warmer responses when the learner's final answer
# contains food/family-food mentions (e.g. 妈妈 + 羊肉 / 好吃 / 做).
# Used to avoid a flat "明白了。" after a food-emotional disclosure.
_CLOSING_REACTIONS_FOOD: list = [
    ("听起来很好吃！", "Tīng qǐlái hěn hǎo chī!", "That sounds delicious!"),
    ("真的很好吃吧！", "Zhēn de hěn hǎo chī ba!", "That must be so tasty!"),
    ("真不错啊！", "Zhēn bùcuò a!", "That's really nice!"),
]

# Used instead of _CLOSING_REACTIONS when the learner's answer has emotional / health signals
# (不好, 生病, 累, 重要…). Appends a short spoken follow-up so the conversation doesn't end
# on an acknowledgement-only line after a personal disclosure.
_CLOSING_REACTIONS_EMOTIONAL: list = [
    ("这样啊。现在怎么样？", "Zhèyàng a. Xiànzài zěnmeyàng?", "I see. How is it now?"),
    ("这样啊。还好吗？", "Zhèyàng a. Hái hǎo ma?", "I see. Are you okay?"),
    ("这样啊。严重吗？", "Zhèyàng a. Yánzhòng ma?", "I see. Is it serious?"),
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

# ── Depth-before-bridge anchor map ───────────────────────────────────────────────────────────────
# Maps open-ended "opener" frame IDs to a priority list of same-engine depth follow-up frames.
# When the learner gives a substantive answer to an anchor frame (destination, dish, hobby, etc.)
# the selector forces ONE same-engine follow-up before allowing ladder advancement or bridging.
# First available unseen frame in the list wins. Deduplication uses the `recent` turn log.
_DEPTH_ANCHOR_FRAMES: dict = {
    # Travel: depth anchors only fire after specific destination questions.
    # f_place_travel ("你会去别的地方吗？") is a broad-intent frame — its answer should route to
    # f_want_go_where ("你最想去哪里？"), not directly to a depth question.
    # Depth fires only after f_want_go_where / f_want_go_place / f_travel_where (city/province),
    # and after f_travel_narrow_city which is the Tier-2 narrowing step.
    "f_want_go_where":        ["f_travel_why_want_go", "f_travel_special", "f_travel_why_interesting"],
    "f_travel_where":         ["f_travel_special", "f_probe_travel_why_fav", "f_travel_why_interesting"],
    "f_want_go_place":        ["f_travel_why_want_go", "f_travel_special", "f_travel_why_interesting"],
    "f_travel_narrow_city":   ["f_travel_why_want_go", "f_travel_special"],
    # Food: named dish answers → why-good or how-made
    "f_food_what_good":       ["f_food_why_good", "f_probe_food_make"],
    "f_food_famous_dish":     ["f_food_why_good"],
    # Hobby: named hobby → best part / origin
    "f_what_hobby":           ["f_hobby_best_part", "f_probe_hobby_origin"],
    "f_like_do_what":         ["f_hobby_best_part", "f_probe_hobby_origin"],
    # Family: named closest person → together / influence
    "f_probe_family_closest": ["f_probe_family_together", "f_probe_family_influence"],
    # Place: distance answer ("很远"/"不远") → distance-detail follow-up (Fix 4).
    # "离那儿远吗？" and "大概要多久？"/"坐飞机要多久？" are one naturally connected
    # exchange; the ladder must not jump to food/special/family in between.
    # Neither target frame is itself a key here, so answering the distance-detail
    # question does not re-trigger another depth follow-up (no loop).
    "p2_pl_far":              ["f_place_distance_time", "f_place_distance_transport"],
}

# Distance/transport info the learner may have already volunteered in the SAME reply
# that answered "离那儿远吗？" (e.g. "坐飞机要十二个小时").  When present, the depth
# follow-up asking "大概要多久？" would be redundant — skip it and let the normal
# ladder acknowledge and continue instead of re-asking for information already given.
_DISTANCE_ALREADY_ANSWERED_RE = re.compile(r"(小时|分钟|飞机|火车|高铁|坐.{0,4}(去|要|需要))")

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
    "青岛", "厦门", "天津", "昆明", "兰州", "新西兰", "澳大利亚", "美国", "英国", "加拿大", "法国",
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

# Marriage-fact markers: if the learner's answer already contains one of these, skip f_married.
# Referenced by skip_when="answer_contains_marriage_fact" in p2_frames.json.
_MARRIAGE_FACT_WORDS: frozenset = frozenset({
    "太太", "老婆", "老公", "丈夫", "妻子", "先生", "结婚", "成家",
    "我们结婚", "婚了", "已婚", "爱人",
})

# Curriculum + common countries (p1_fillers): used only to detect "familiar" place tokens in answers.
# Referenced by skip_when="city_is_familiar" in p2_frames.json → evaluated via _check_skip_condition.
_FAMILIAR_PLACE_NAMES: frozenset = frozenset(
    {
        "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉", "西安", "青岛", "厦门", "天津", "昆明",
        "中国", "新西兰", "澳大利亚", "美国", "英国", "加拿大", "日本", "韩国", "法国", "德国", "新加坡", "马来西亚", "泰国",
    }
)

# Domestic Chinese cities/provinces — asking "离中国远吗？" is meaningless for these.
# Used by _learner_place_is_overseas() to suppress the distance-question boost.
_CHINA_DOMESTIC_PLACE_NAMES: frozenset = frozenset({
    "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆",
    "武汉", "西安", "青岛", "厦门", "天津", "昆明", "中国", "大陆", "内地",
    "台湾", "香港", "澳门",
})

# Discovery topics that describe place orientation/distance — valuable after overseas mentions.
# Sorted to the front of the blue panel when _learner_place_is_overseas() fires.
_PLACE_DISTANCE_TOPICS: frozenset = frozenset({
    "place_far", "place_far_or_not", "place_distance_ref",
    "place_distance_time", "place_distance_transport",
})


def _learner_place_is_overseas(answer_text: str) -> bool:
    """True when the learner's answer mentions an overseas or unfamiliar non-Chinese location.

    Used to elevate place-distance/orientation questions in the blue discovery panel.
    Returns False for well-known domestic Chinese cities so distance questions are
    suppressed where they would feel redundant (e.g. 我住在上海).
    """
    if not answer_text:
        return False
    t = answer_text.strip()
    # Latin script almost certainly indicates a non-Chinese place name (Dunedin, Auckland, etc.)
    if re.search(r"[A-Za-z]", t):
        return True
    # Known domestic city/province → no distance boost
    if any(p in t for p in _CHINA_DOMESTIC_PLACE_NAMES):
        return False
    # Foreign country names: compute overseas = FAMILIAR - DOMESTIC
    _overseas_subset = _FAMILIAR_PLACE_NAMES - _CHINA_DOMESTIC_PLACE_NAMES
    if any(p in t for p in _overseas_subset):
        return True
    return False


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

    if predicate == "answer_contains_marriage_fact":
        # Skip "你结婚了吗？" when the learner's recent answer already reveals marriage status
        # (contains 太太 / 老婆 / 结婚 etc.) — asking again would feel like the app wasn't listening.
        return any(w in answer_text for w in _MARRIAGE_FACT_WORDS)

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

# Micro-probe pool: very short curiosity probes (为什么？哪里？怎么样？什么时候？).
# Fire occasionally after valid slot-name answers even when interest is not "high" and chain < 2.
# Engine mapping determines which probe fits best; "why" is the universal fallback.
_MICRO_PROBE_BY_ENGINE: dict = {
    "identity": ["f_micro_probe_why"],
    "place":    ["f_micro_probe_where", "f_micro_probe_why"],
    "work":     ["f_micro_probe_how", "f_micro_probe_why"],
    "hobby":    ["f_micro_probe_how", "f_micro_probe_why"],
    "travel":   ["f_micro_probe_when", "f_micro_probe_why"],
    "family":   ["f_micro_probe_why"],
    "food":     ["f_micro_probe_how", "f_micro_probe_why"],
}
_MICRO_PROBE_FRAME_IDS: frozenset = frozenset({
    "f_micro_probe_why", "f_micro_probe_where", "f_micro_probe_how", "f_micro_probe_when"
})

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


def _strip_discourse_prefix(s: str) -> str:
    """Strip leading discourse markers that wrap pool items before storing them
    in recent_persona_replies, so exclude-set membership can compare the bare
    pool string against its 我呢-prefixed stored form (RC-C fix)."""
    for _pfx in ("我呢，", "我呢,", "我，", "我,"):
        if s.startswith(_pfx):
            return s[len(_pfx):]
    return s


def _pick_not_in(pool: list, seed: str, exclude: set) -> Optional[str]:
    """Deterministic pick from pool, avoiding items in exclude.

    exclude items are compared both verbatim AND after stripping the leading
    discourse marker ('我呢，' etc.) that run_turn prepends before storing the
    reply in recent_persona_replies, so a pool item that has already been given
    in prefixed form is still correctly treated as used (RC-C).

    Falls back to the normal stable pick when all pool items are excluded."""
    if not pool:
        return None
    # Normalise the exclude set to bare forms for comparison.
    _bare_exclude: set = set(exclude) | {_strip_discourse_prefix(e) for e in exclude}
    candidate = _stable_pick(pool, seed)
    if candidate not in _bare_exclude:
        return candidate
    for item in pool:
        if item not in _bare_exclude:
            return item
    return candidate  # all excluded — no choice


def _looks_food_related_answer(text: str) -> bool:
    if not text:
        return False
    cues = (
        "好吃", "吃", "饺子", "火锅", "牛肉", "羊肉", "鸡肉", "鱼", "面", "米饭",
        "菜", "辣", "甜", "咸", "酸", "汤", "烧烤", "奶茶", "咖啡"
    )
    return any(c in text for c in cues)


# ── Open-world responsive food answer (Fix 1) ────────────────────────────────────────────────────
# Frame IDs where the partner asked "what's good to eat" somewhere.  When the previous
# turn was one of these, a DECLARATIVE learner reply is a responsive food answer —
# regardless of whether the specific food terms are in any internal vocabulary.  The
# preceding frame supplies the semantic context; no fixed food list is required or checked.
_PLACE_FOOD_QUESTION_FRAMES: frozenset = frozenset({
    "p2_pl_2", "f_place_food", "f_food_available", "f_travel_food",
    "f_food_what_good", "f_food_famous_dish", "f_food_tasty",
})


def _is_responsive_food_answer(text: str, last_answer_fid: str, prev_partner_text: str) -> bool:
    """True when the previous partner turn asked what food is good somewhere and the
    learner's current reply is a declarative (non-interrogative) response.

    Open-world invariant: does NOT require the reply to contain any recognised food
    noun — the food-question CONTEXT (frame id or preceding question text) is the
    deciding signal, not vocabulary.  Genuine questions (？, sentence-final 吗/呢, or an
    explicit "what do you like" turn-around) are excluded so they still route as
    questions.
    """
    t = (text or "").strip()
    if not t:
        return False
    if _is_confusion_signal(t):
        return False  # filler / recovery phrases still go through the confusion ladder
    if any(ord(c) in (0xFF1F, 0x003F) for c in t):
        return False  # contains ？ or ? — a genuine question, not a declarative answer
    if t.rstrip("。！").endswith(("吗", "呢")):
        return False
    if any(m in t for m in ("你喜欢吃什么", "你最喜欢吃", "你呢")):
        return False  # turn-around back to the persona — let normal question routing handle it
    fid = (last_answer_fid or "").strip()
    if fid in _PLACE_FOOD_QUESTION_FRAMES:
        return True
    if _is_place_food_question(prev_partner_text or ""):
        return True
    return False


# Particles/evaluative suffixes stripped from the edges of a split food-answer segment.
# Purely structural (list connectives + generic praise words) — no food-specific vocabulary.
_FOOD_ITEM_TRAILING_STRIP: tuple = ("都很好吃", "都好吃", "也很好吃", "很好吃", "最好吃", "最好", "好吃")
_FOOD_ITEM_LEADING_STRIP: tuple = ("这里的", "那里的", "这儿的", "那儿的", "我们那里的", "我们这里的")
_FOOD_ITEM_STOPWORDS: frozenset = frozenset({
    "都", "很", "也", "是", "的", "有", "还", "最", "最好", "最好吃",
    "好吃", "好吃的", "那里", "这里", "那儿", "这儿", "我们", "你们",
    "一种", "叫", "东西", "地方", "特别", "特色", "小吃",
})


def _extract_food_items(text: str) -> list:
    """Best-effort OPEN-WORLD extraction of food-noun-phrases from a declarative
    food-list answer, for a natural acknowledgement — never a closed vocabulary
    lookup.  Splits on common Chinese list connectives/punctuation and trims
    generic leading/trailing evaluative particles; unknown food names pass through
    unchanged (extraction never rejects a food name for being unrecognised)."""
    t = (text or "").strip()
    if not t:
        return []
    parts = re.split(r"[，,、和与跟]|还有|并且|以及", t)
    items: list = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        for lw in _FOOD_ITEM_LEADING_STRIP:
            if p.startswith(lw):
                p = p[len(lw):].strip()
                break
        for sw in _FOOD_ITEM_TRAILING_STRIP:
            if p.endswith(sw):
                p = p[: -len(sw)].strip()
                break
        if p and 2 <= len(p) <= 8 and re.search(r"[\u4e00-\u9fff]", p) and p not in _FOOD_ITEM_STOPWORDS:
            items.append(p)
    seen: set = set()
    out: list = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


# Generic acknowledgement pool for a responsive food answer with no cleanly
# extractable item list — never asserts factual knowledge about the food itself.
_FOOD_RESPONSE_ACK_POOL: list = [
    ("听起来很好吃！你最喜欢哪一个？", "That sounds delicious! Which one do you like best?"),
    ("这个名字很特别，是什么味道的？", "That's an interesting name — what does it taste like?"),
    ("听起来不错，你经常吃吗？", "Sounds good — do you eat it often?"),
    ("你最常吃哪一种？", "Which one do you eat most often?"),
]


def _food_responsive_reply(text: str, seed: str = "") -> tuple:
    """Acknowledge an open-world food-list answer and ask a natural follow-up.

    Never claims factual knowledge about foods unfamiliar to MandarinOS — the
    learner supplied the facts; the persona simply reacts to them.
    """
    items = _extract_food_items(text)
    if len(items) >= 2:
        joined = "、".join(items[:3])
        zh = f"你说的{joined}听起来都很好吃！你最喜欢哪一个？"
        en = f"The {', '.join(items[:3])} you mentioned all sound delicious! Which one do you like best?"
        return (zh, en)
    if len(items) == 1:
        zh = f"{items[0]}听起来很不错，是什么味道的？"
        en = f"{items[0]} sounds great — what does it taste like?"
        return (zh, en)
    zh = _stable_pick([p[0] for p in _FOOD_RESPONSE_ACK_POOL], seed or "food_ack") or _FOOD_RESPONSE_ACK_POOL[0][0]
    en = next((e for (z, e) in _FOOD_RESPONSE_ACK_POOL if z == zh), "")
    return (zh, en)


def _looks_travel_related_answer(text: str) -> bool:
    if not text:
        return False
    cues = (
        # Explicit travel vocabulary — these carry travel intent in any context
        "去过", "想去", "旅行", "旅游", "国家", "机票", "景点", "出国",
        # Travel-verb patterns specific enough not to fire on school/errands:
        # "会去" alone is too generic ("我会去学校"); require it in travel frame context.
        # "去过" above already catches past-tense travel.
        "打算去", "计划去",
        # NOTE: country/city names intentionally OMITTED — "中国" in "我是中国人" is origin,
        # not travel. Only the explicit travel frames list triggers TRAVEL slot for destination
        # answers (handled via _infer_slot_names_from_answer explicit frame check).
    )
    return any(c in text for c in cues)


# High-confidence travel-enthusiasm signals — used to override engine dwell when the
# learner explicitly expresses a preference or habit for travel (not just a mention).
# Only fires when the TRAVEL slot is ALSO detected (double-gated for precision).
_STRONG_TRAVEL_SIGNALS: frozenset = frozenset([
    "很喜欢旅行", "很喜欢旅游",
    "爱旅行", "爱旅游",
    "常常旅行", "常常旅游",
    "经常旅行", "经常旅游",
    "喜欢旅行", "喜欢旅游",
    "喜欢去别的地方", "喜欢去其他地方", "喜欢去不同的地方",
    "常旅行", "常旅游",
])


def _has_strong_travel_signal(text: str) -> bool:
    """Return True when the learner's answer contains an explicit travel-enthusiasm phrase."""
    if not text:
        return False
    return any(kw in text for kw in _STRONG_TRAVEL_SIGNALS)


# ── Travel destination answer validation ──────────────────────────────────────────────────────────
# Used to catch ASR-garbled destination answers (e.g. "刚吃" instead of "甘肃") so they are
# never echoed as valid content and always route to a clarification question.

# Frame IDs that expect the learner to name a specific destination.
_DESTINATION_QUESTION_FRAMES: frozenset = frozenset({
    "f_want_go_where", "f_travel_where", "f_want_go_place", "f_travel_narrow_city",
})

# (confused_string, likely_intended) pairs — scoped to travel destination context only.
# Ordered longest-first so more specific patterns match before substrings do.
_TRAVEL_ASR_NEAR_MATCHES: list = [
    ("刚刚出", "甘肃"), ("刚吃", "甘肃"), ("刚出", "甘肃"), ("干肃", "甘肃"), ("甘书", "甘肃"), ("甘树", "甘肃"),
    ("吃中国", "去中国"), ("出中国", "去中国"), ("会出中国", "会去中国"),
]

# Cross-engine "eat + country" near-miss: "我最想吃中国" → "去中国".
# Fires regardless of the active frame because learners frequently say "吃X国" (eat X)
# instead of "去X国" (go to X) even outside the travel engine, and the reaction must
# never echo the impossible phrase back approvingly.
_EAT_COUNTRY_RE = re.compile(
    r"(?:想|最想|要|想要)吃"
    r"(中国|日本|韩国|泰国|法国|美国|英国|意大利|德国|欧洲|亚洲|澳大利亚|新西兰|印度|越南|西班牙)"
)


def _is_valid_destination_answer(text: str) -> bool:
    """True if text contains a recognised place entity or a clear non-destination travel phrase."""
    if not text:
        return False
    return (
        any(e in text for e in _TRAVEL_SUBREGIONS | _TRAVEL_COUNTRIES)
        or any(c in text for c in ("旅行", "旅游", "出国", "想去旅"))
    )


def _detect_travel_asr_near_match(text: str) -> Optional[str]:
    """Return the likely intended destination string when text contains a known ASR confusion."""
    if not text:
        return None
    for confused, intended in _TRAVEL_ASR_NEAR_MATCHES:
        if confused in text:
            return intended
    return None


# ── Cross-engine near-miss answer guard ──────────────────────────────────────────────────────────
#
# Before the selector picks a normal follow-up it checks whether the learner's answer is a
# known near-miss (ASR transcription error or semantically incompatible answer) for the current
# question type.  If so, it prefers clarification over continuation.
#
# To extend: add a new dict to _NEAR_MISS_GUARD_TABLE.  No selector changes needed.
# Travel destination near-misses are handled separately by _TRAVEL_ASR_NEAR_MATCHES because they
# generate dynamic clarification text; entries here use a fixed clarify frame.
_NEAR_MISS_GUARD_TABLE: list = [
    {
        # Work engine: 退休 (tuìxiū) is commonly transcribed as phonetically similar strings.
        # Any of these in response to a work-entry question should trigger retirement clarification
        # rather than an occupation follow-up.
        "near_miss_strings": [
            # NEW — phonetically close to 退休:
            "退校了", "退校",           # tuìxiào — "withdrew from school"
            "退学了", "退学",           # tuìxué  — "dropped out of school"
            # Pre-existing homophones (migrated from inline selector):
            "推销了", "推休了",
            "退修了", "推消了", "退消了",
            "退烧了", "退烧",           # tuìshāo — "fever broke" — not a job
        ],
        "eligible_frames": frozenset({
            "f_what_work", "p2_wk_1", "p2_wk_2",
            "p2_wk_3", "p2_wk_4", "p2_wk_5",
        }),
        "clarify_frame_id": "f_work_retire_clarify",
        "intended":          "退休",
        "exclude_if":        ["在推销"],   # unambiguously active sales phrasing → not retirement
        "max_answer_length": 12,           # longer answers are unlikely to be pure near-misses
    },
    # ── Future entries ────────────────────────────────────────────────────────────────────────────
    # Family: semantic incompatibility detection (e.g. place name as answer to family question)
    #   needs separate design — reserved for Phase 2.
    # Hobby: no strong ASR near-misses identified yet; extend when examples are collected.
]


def _detect_near_miss_answer(
    answer_text: str,
    last_fid: str,
    recent_frames: list,
) -> "tuple[str, str] | None":
    """
    Check answer_text against _NEAR_MISS_GUARD_TABLE.

    Returns (clarify_frame_id, intended_display_string) when a guard fires,
    or None when the answer passes all registered guards.

    Design: add entries to _NEAR_MISS_GUARD_TABLE for new engines/cases.
    The selector calls this once; no per-engine inline checks are needed.
    """
    stripped = answer_text.strip("。！？")
    for guard in _NEAR_MISS_GUARD_TABLE:
        if last_fid not in guard.get("eligible_frames", frozenset()):
            continue
        ml = guard.get("max_answer_length")
        if ml and len(answer_text) > ml:
            continue
        if guard.get("clarify_frame_id") in recent_frames:
            continue
        if any(ex in answer_text for ex in guard.get("exclude_if", [])):
            continue
        if any(nm in stripped for nm in guard.get("near_miss_strings", [])):
            return (guard["clarify_frame_id"], guard["intended"])
    return None


# ── Meaningful-imperfect answer guard ────────────────────────────────────────────────────────────
#
# Fires when the learner gives a rich, complex, or multi-component answer that is NOT a known
# ASR near-miss and NOT broken (so repair doesn't fire), but IS messy enough that normal
# topic progression would skip over useful clarification.
#
# Canonical example:
#   Q: 你叫什么名字？
#   A: "我叫杨理名李毛的李国民的名 朋友叫我Raymond 我广东名字英文名字"
#   → system should clarify 你是说你的中文名字听起来像英文名字吗？
#     instead of progressing to 你多大了？
#
# Design: add a dict per engine to _MEANINGFUL_IMPERFECT_GUARDS.
# Each entry defines: eligible_frames, engine-specific keywords, min_answer_length,
# min_same_engine_chain, and the clarify_frame_id to select.
# No selector edits needed for new entries — only extend this table.

_MEANINGFUL_IMPERFECT_GUARDS: list = [
    {
        # Identity/name engine: answers mentioning Cantonese, English-name complexity, or
        # dialect-name ambiguity.  These are valid but need soft clarification before advancing.
        "eligible_frames": frozenset({
            "f_ask_you_name",          # p1 — primary name question
            "p2_id_2",                 # 大家一般怎么叫你？
            "p2_id_4",                 # 你觉得你的名字怎么样？
            "p2_id_5",                 # 这个名字有故事吗？
            "f_name_story",            # 你名字有什么故事吗？
            "f_id_friends_call",       # 朋友一般怎么叫你？
            "f_probe_id_nickname",     # 家里人怎么叫你？
        }),
        "keywords": ["广东", "英文名字", "英文名", "粤语", "方言", "中文名", "外国名字"],
        "clarify_frame_id": "f_identity_name_clarify_soft",
        "min_answer_length": 8,       # rich/complex answers tend to be longer
        "min_keywords_present": 1,    # one keyword is sufficient
        "min_same_engine_chain": 1,   # must already be inside identity engine
    },
    # ── Future entries ───────────────────────────────────────────────────────────────────────────
    # Work engine: messy job descriptions mentioning multiple roles or place-only answers
    #   reserved for Phase 2 — need cleaner heuristics.
    # Place engine: partial addresses or multi-city answers
    #   reserved for Phase 2.
]


def _detect_meaningful_imperfect_answer(
    answer_text: str,
    last_fid: str,
    recent_frames: list,
    same_engine_chain_count: int = 0,
) -> dict:
    """
    Check answer_text against _MEANINGFUL_IMPERFECT_GUARDS.

    Returns {"should_clarify": True, "clarify_frame_id": <str>} when a guard fires,
    or {"should_clarify": False, "clarify_frame_id": None} otherwise.

    Fires only for rich, meaningful answers that contain engine-specific keywords
    but are complex enough to warrant soft clarification before topic progression.
    Does NOT fire for: ASR near-misses (handled by _detect_near_miss_answer),
    broken/repair answers (handled by discourse coherence guard).

    Design: add entries to _MEANINGFUL_IMPERFECT_GUARDS for new engines/cases.
    """
    for guard in _MEANINGFUL_IMPERFECT_GUARDS:
        if last_fid not in guard.get("eligible_frames", frozenset()):
            continue
        if len(answer_text) < guard.get("min_answer_length", 8):
            continue
        if same_engine_chain_count < guard.get("min_same_engine_chain", 1):
            continue
        if guard.get("clarify_frame_id") in recent_frames:
            continue   # already showed this clarification
        keywords = guard.get("keywords", [])
        hits = sum(1 for kw in keywords if kw in answer_text)
        if hits < guard.get("min_keywords_present", 1):
            continue
        return {"should_clarify": True, "clarify_frame_id": guard["clarify_frame_id"]}
    return {"should_clarify": False, "clarify_frame_id": None}


# ── Answer-specificity detectors (used by depth-before-bridge rule) ───────────────────────────────
# Each detector returns True when the answer names a CONCRETE entity — a destination, dish,
# activity, or family member — specific enough to warrant a depth follow-up ("why / tell me more").
# A broad answer ("有很多好吃的", "我喜欢运动") returns False → normal ladder handles narrowing.
#
# Travel uses a three-tier system:
#   Tier 1 — Depth-ready  : province / city / specific region  → "你为什么想去那里？"
#   Tier 2 — Country-level: 中国 / 日本 / 美国 etc.            → "你想去哪个城市？" (narrowing)
#   Tier 3 — Broad        : 我想旅行 / 我会去别的地方           → normal ladder

# Tier 1: provinces, autonomous regions, and cities → depth-ready
_TRAVEL_SUBREGIONS: frozenset = frozenset({
    # Provinces / autonomous regions / SARs
    "北京", "上海", "广东", "江苏", "浙江", "四川", "重庆", "云南", "西藏", "新疆",
    "甘肃", "青海", "福建", "山东", "广西", "贵州", "湖南", "湖北", "陕西", "山西",
    "河南", "河北", "内蒙古", "辽宁", "吉林", "黑龙江", "安徽", "江西", "海南", "宁夏",
    "台湾", "香港", "澳门",
    # Cities
    "苏州", "杭州", "成都", "深圳", "广州", "南京", "西安", "青岛", "厦门",
    "武汉", "昆明", "天津", "大连", "哈尔滨", "长沙", "郑州", "沈阳", "兰州",
})

# Tier 2: country-level destinations → narrowing ("which city?") rather than depth ("why?")
_TRAVEL_COUNTRIES: frozenset = frozenset({
    "中国", "日本", "法国", "英国", "美国", "德国", "澳大利亚", "新西兰", "韩国", "泰国",
    "新加坡", "意大利", "西班牙", "加拿大", "越南", "印度",
    "欧洲", "亚洲", "东南亚",
})

_FOOD_SPECIFIC_ENTITIES: frozenset = frozenset({
    "羊肉", "牛肉", "猪肉", "鸡肉", "鱼", "饺子", "包子", "面条", "米饭",
    "火锅", "烤鸭", "汤", "粥", "海鲜", "蔬菜", "水果", "寿司", "烧烤",
    "蛋糕", "面包", "炒饭", "拌面", "螺蛳粉", "臭豆腐", "小笼包",
    "豆腐", "排骨", "虾", "螃蟹", "烤串", "手抓饭", "煎饼",
})

_HOBBY_SPECIFIC_ENTITIES: frozenset = frozenset({
    "网球", "游泳", "跑步", "画画", "唱歌", "跳舞", "读书", "看书",
    "爬山", "钓鱼", "下棋", "写字", "摄影", "烹饪", "做饭", "旅行",
    "健身", "瑜伽", "打球", "踢球", "骑车", "滑雪", "登山", "羽毛球",
    "乒乓球", "篮球", "足球", "排球", "高尔夫", "冲浪", "编织", "园艺",
})

_FAMILY_SPECIFIC_MEMBERS: frozenset = frozenset({
    "老婆", "妻子", "老公", "丈夫", "先生", "妈妈", "爸爸", "母亲", "父亲",
    "哥哥", "弟弟", "姐姐", "妹妹", "儿子", "女儿", "孩子", "爷爷", "奶奶",
    "外公", "外婆", "祖父", "祖母",
})


def _is_depth_ready_travel_answer(text: str) -> bool:
    """Tier 1: True when answer names a province, city, or sub-country region (depth-ready)."""
    return bool(text) and any(e in text for e in _TRAVEL_SUBREGIONS)


def _is_country_level_travel_answer(text: str) -> bool:
    """Tier 2: True when answer names a country but NOT a more specific sub-region."""
    if not text:
        return False
    return any(c in text for c in _TRAVEL_COUNTRIES) and not _is_depth_ready_travel_answer(text)


def _is_specific_food_entity(text: str) -> bool:
    """True if answer names a concrete dish or food item."""
    return bool(text) and any(e in text for e in _FOOD_SPECIFIC_ENTITIES)


def _is_specific_hobby_entity(text: str) -> bool:
    """True if answer names a specific activity (not just 运动/玩/爱好 generically)."""
    return bool(text) and any(e in text for e in _HOBBY_SPECIFIC_ENTITIES)


def _is_specific_family_entity(text: str) -> bool:
    """True if answer names a specific family member (not just 家人/家里人 generically)."""
    return bool(text) and any(e in text for e in _FAMILY_SPECIFIC_MEMBERS)


# Maps each depth-anchor frame to its Tier-1 (depth-ready) specificity detector.
# Depth follow-up fires ONLY when this detector returns True.
_DEPTH_ANCHOR_SPECIFICITY: dict = {
    "f_want_go_where":        _is_depth_ready_travel_answer,
    "f_travel_where":         _is_depth_ready_travel_answer,
    "f_want_go_place":        _is_depth_ready_travel_answer,
    "f_travel_narrow_city":   _is_depth_ready_travel_answer,  # city/province → depth; country → broad
    "f_food_what_good":       _is_specific_food_entity,
    "f_food_famous_dish":     _is_specific_food_entity,
    "f_what_hobby":           _is_specific_hobby_entity,
    "f_like_do_what":         _is_specific_hobby_entity,
    "f_probe_family_closest": _is_specific_family_entity,
}

# Maps each depth-anchor frame to its Tier-2 (country-level / mid-specific) detector.
# When Tier-2 fires, the selector picks from _DEPTH_NARROWING_FRAMES instead of depth candidates.
_DEPTH_NARROW_SPECIFICITY: dict = {
    "f_want_go_where":  _is_country_level_travel_answer,
    "f_travel_where":   _is_country_level_travel_answer,
    "f_want_go_place":  _is_country_level_travel_answer,
}

# Narrowing candidates for Tier-2 answers (country-level).
# Frame f_travel_narrow_city asks "你想去哪个城市？" to draw out a sub-country destination.
_DEPTH_NARROWING_FRAMES: dict = {
    "f_want_go_where":  ["f_travel_narrow_city", "f_travel_which_best"],
    "f_travel_where":   ["f_travel_narrow_city", "f_travel_which_best"],
    "f_want_go_place":  ["f_travel_narrow_city", "f_travel_which_best"],
}


# ── Depth-trigger follow-up ───────────────────────────────────────────────────────────────────
# Detects emotional, planning, and relationship signals in learner answers.
# When triggered and no entity-level anchor (force_depth_followup_frame) applies, the selector
# stays in the same engine and asks one short follow-up instead of switching topics.
# Budget: at most 2 consecutive depth-trigger follow-ups per topic (tracked via cs state).
_DEPTH_TRIGGER_EMOTIONAL: frozenset = frozenset(["不好", "累", "生病", "开心", "喜欢", "重要"])
_DEPTH_TRIGGER_PLANS:     frozenset = frozenset(["想去", "会去", "打算"])
_DEPTH_TRIGGER_RELATIONS: frozenset = frozenset(["老婆", "家人", "最亲近"])


def _detect_depth_trigger(text: str) -> Optional[str]:
    """Return trigger category ('emotional', 'plan', 'relationship') or None."""
    if not text:
        return None
    if any(s in text for s in _DEPTH_TRIGGER_EMOTIONAL):
        return "emotional"
    if any(s in text for s in _DEPTH_TRIGGER_PLANS):
        return "plan"
    if any(s in text for s in _DEPTH_TRIGGER_RELATIONS):
        return "relationship"
    return None


# (trigger_category, engine) → ordered list of candidate frame IDs.
# Only frames confirmed present in p2_frames.json are listed.
# First unseen frame wins; if none available, falls through to normal ladder.
_DEPTH_TRIGGER_ENGINE_FRAMES: dict = {
    ("emotional", "work"):       ["f_probe_work_best", "f_probe_work_why_quit", "f_probe_work_dream"],
    ("emotional", "hobby"):      ["f_probe_hobby_origin", "f_probe_hobby_social"],
    ("emotional", "travel"):     ["f_probe_travel_why_fav", "f_travel_why_want_go"],
    ("emotional", "family"):     ["f_probe_family_influence", "f_probe_family_together"],
    ("emotional", "food"):       ["f_probe_food_childhood", "f_probe_food_make"],
    ("emotional", "place"):      ["f_probe_emotional_checkin", "f_probe_place_miss", "f_probe_place_stay"],
    ("plan",      "travel"):     ["f_travel_why_want_go", "f_probe_travel_why_fav"],
    ("plan",      "work"):       ["f_probe_work_future", "f_probe_work_dream"],
    ("plan",      "hobby"):      ["f_probe_hobby_origin"],
    ("plan",      "family"):     ["f_probe_family_together"],
    ("plan",      "place"):      ["f_probe_place_stay"],
    ("relationship", "family"):  ["f_probe_family_together", "f_probe_family_influence"],
    ("relationship", "work"):    ["f_probe_family_together"],
    ("relationship", "hobby"):   ["f_probe_family_together"],
    ("relationship", "place"):   ["f_probe_family_together"],
}


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


def _is_name_story_teaser_answer(text: str) -> bool:
    """True when the learner only hedges that a story exists without telling it (identity f_name_story)."""
    raw = (text or "").strip()
    if not raw:
        return False
    t = raw.replace(" ", "").rstrip("。.").strip()
    if not t:
        return False
    if len(t) > 16:
        return False
    depth_markers = (
        "因为", "所以", "爷爷", "奶奶", "父母", "爸爸", "妈妈", "给我", "起的", "取的",
        "小名", "学名", "出生", "时候", "那年",
    )
    if any(m in t for m in depth_markers):
        return False
    if t in (
        "有一个小故事", "有一个故事", "有一点故事", "有小故事", "有故事", "有一点儿故事",
        "有点儿故事", "有个故事", "有个小故事", "有一点小故事", "有", "有有",
    ):
        return True
    if "故事" in t and t.startswith("有") and len(t) <= 12:
        return True
    return False


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
    if fid in ("f_ask_you_name", "p2_id_2", "f_ask_name_meaning", "f_id_friends_call", "f_probe_id_nickname", "f_name_story"):
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
    if fid in (
        "f_travel_where", "f_want_go_where",
        "f_place_travel",   # 你会去别的地方吗？ — place-engine but travel-destination answer expected
        "p2_tr_1", "p2_tr_2", "p2_tr_3", "p2_tr_4",
    ):
        slots.append("TRAVEL")
    if fid in (
        "f_from_where",
        "frame.location.live_question",
        "f_live_where",   # modern ID for "你现在住在哪里？" (legacy alias above kept for compat)
        "p2_pl_1",
        "p2_pl_2",
        "p2_pl_3",
        "p2_pl_4",
        # p2_pl_far intentionally excluded: it asks "离那儿远吗？" — the expected answer is
        # distance/travel-time (飞机, 小时, 很远), NOT a new city name.  Including it here
        # caused the NLC (noisy-location clarification) path to fire for valid distance
        # answers like "乘飞机12小时", generating a spurious "我是问：离那儿远吗？" re-ask.
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
        "f_id_friends_call", "f_probe_id_nickname", "f_name_story",
        "frame.greeting.hello", "frame.greeting.hello_reply", "f_nice_to_meet",
    })
    _is_identity_frame = fid in _identity_frame_ids
    if _looks_food_related_answer(txt) and "DISH" not in slots and not _is_identity_frame:
        slots.insert(0, "DISH")
    elif fid == "p2_pl_2" and "DISH" not in slots:
        # p2_pl_2 asks about food in {CITY}; treat answers as dish/topic-bearing by default.
        slots.insert(0, "DISH")
    # Soft-chain TRAVEL only when the learner is already in a travel/place context.
    # Prevents "我喜欢中国" on "你是哪里人？" from injecting a TRAVEL slot and causing
    # a premature bridge to the travel engine.
    _TRAVEL_SOFT_CHAIN_FRAMES = frozenset({
        "f_place_travel", "f_travel_where", "f_want_go_where", "f_want_go_place",
        "f_from_where", "frame.location.live_question",
        "p2_pl_1", "p2_pl_2", "p2_pl_3", "p2_pl_4", "p2_pl_ext1",
        "p2_tr_1", "p2_tr_2", "p2_tr_3", "p2_tr_4",
    })
    _in_travel_context = (
        fid in _TRAVEL_SOFT_CHAIN_FRAMES
        or (fid or "").startswith("f_travel")
        or (fid or "").startswith("p2_tr")
    )
    if _looks_travel_related_answer(txt) and "TRAVEL" not in slots and not _is_identity_frame and _in_travel_context:
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

# Work place-only signals: institution / location names that, WITHOUT a role marker,
# indicate the learner named a place rather than a job role.
# Used to suppress the enthusiastic work reaction before clarification is established.
_WORK_PLACE_ONLY_SIGNALS: tuple = (
    "大学", "学校", "公司", "医院", "银行", "政府", "研究所",
)
# Role markers that make a work answer semantically clear — even alongside a place name.
# "我在医院工作" is clear; "医院" alone is not.
_WORK_ROLE_MARKERS: tuple = (
    "老师", "教授", "讲师", "工程师", "医生", "护士", "经理", "研究员",
    "职员", "员工", "主任", "主管", "总裁", "导师", "工作",
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
    _raw_for_qmark = text
    text = _normalize_zh_for_routing(text)
    # Question-mark check on the raw submitted text (before trailing-filler strip).
    if any(ord(c) in (0xFF1F, 0x003F) for c in _raw_for_qmark):
        return True
    # Strip leading fillers so "ne 你是哪里人" / "啊你住哪里" classify correctly.
    text = _strip_leading_fillers(text)
    # Semantic place-food / place-feature / cooking questions (ASR-tolerant).
    if _is_place_food_question(text) or _is_place_feature_question(text) or _is_cooking_question(text):
        return True
    # Content-based interrogatives without explicit ？ — e.g. "西安有什么特别啊", "这里有什么好吃的",
    # "你们那儿怎么样". Checked early so short utterances like "有什么好吃" are caught quickly.
    _content_q_markers = ("有什么", "什么特别", "什么好", "什么特色", "怎么样", "叫什么")
    if any(m in text for m in _content_q_markers):
        return True
    # Turn-around markers AS SUBSTRINGS — catches "我叫X，你呢" / "喜欢你呢" etc.
    _turn_around_markers = ("你呢", "那你呢", "你怎么想", "为什么这么问", "为什么这样问", "换我问", "你来问")
    if any(m in text for m in _turn_around_markers):
        return True
    # Repeated / clarification re-asks — often no explicit ？ (ASR or typed follow-up).
    _repeat_q_markers = ("我问你", "我是说", "我是问你", "那我问你")
    if any(m in text for m in _repeat_q_markers):
        return True
    # Favourite-place questions — common learner initiative, sometimes without ？
    if "最喜欢" in text and any(k in text for k in ("地方", "哪里", "哪儿", "哪个", "什么")):
        return True
    # Spicy-food preference — short 吗-questions without other food keywords
    if "喜欢辣" in text or ("辣" in text and "喜欢" in text and ("吗" in text or len(text) <= 8)):
        return True
    # Direct questions about the persona (no explicit "？" needed)
    _direct_starts = (
        "你叫什么", "你的名字", "你名字", "你是哪里人", "你从哪里来", "你老家在哪",
        "你老家", "你的老家", "你家乡",
        "你住在哪", "你住哪里", "你做什么工作", "你的工作", "你是做什么",
        "你最喜欢", "你喜欢辣",
        "你喜欢什么", "你有什么爱好", "你有家人", "你有没有家人",
        "你结婚了吗", "你有孩子", "你多大", "你几岁", "你今年多大",
        # Travel
        "你去过哪里", "你去过哪些", "你去过什么地方", "你旅游过",
        # Persona's family members
        "你女儿", "你儿子", "你的孩子", "你的女儿", "你的儿子",
        "你老婆", "你太太", "你先生", "你老公", "你的老婆", "你的太太",
        "你父母", "你爸爸", "你妈妈", "你爸妈", "你的爸爸", "你的妈妈", "你家人",
    )
    if any(text.startswith(p) for p in _direct_starts):
        return True
    # Family-member questions without explicit 你 prefix:
    # "女儿做什么工作啊", "孩子多大了", "儿子在哪里工作", "奶奶住哪里" etc.
    # Extended to cover grandparents and other close relatives.
    _family_words = ("女儿", "儿子", "孩子", "太太", "老婆", "先生", "老公",
                     "爸爸", "妈妈", "爸妈", "父母", "奶奶", "爷爷", "外婆", "外公", "姥姥", "姥爷")
    _action_words = ("做什么工作", "在哪工作", "在哪里工作", "上班", "上学", "多大", "几岁",
                     "工作是什么", "做什么", "住哪", "住在哪", "在哪里", "哪里")
    if any(fw in text for fw in _family_words) and any(aw in text for aw in _action_words):
        return True
    # Common interrogative markers without explicit punctuation
    starters = ("怎么", "为什么", "哪里", "谁", "什么时候", "多少", "几", "哪儿", "哪裡")
    if text.startswith(starters):
        return True
    if text.endswith("吗") or ("吗" in text and len(text) <= 8):
        return True
    # Duration interrogatives without ？ — e.g. "你从事这个工作多久了", "工作多长时间了"
    if "多长时间" in text:
        return True
    if "多久" in text and any(kw in text for kw in ("工作", "做", "学", "住", "用", "从事")):
        return True
    # Elliptical question with sentence-final particles: "喜欢吗", "好吗", "远吗"
    # (already caught by "吗" check above if 吗 present); also cover "啊", "呢" as
    # question markers when the utterance is short enough to be a follow-up question.
    if text.endswith(("呢", "啊", "啦")) and len(text) <= 10 and any(kw in text for kw in ("喜欢", "远", "好", "特别", "有趣")):
        return True
    # Short bare-location follow-ups: "在哪儿" / "在哪里" / "在哪" — learner asking where
    # a city/place just mentioned is located.  These carry no "？" and no 你 prefix.
    if any(text.strip() == kw or text.endswith(kw) for kw in ("在哪儿", "在哪里", "在哪儿啊", "在哪里啊", "在哪啊", "在哪呢", "在哪儿呢", "在哪里呢")):
        return True
    if len(text) <= 12 and any(kw in text for kw in ("哪儿啊", "哪里啊", "在哪儿", "在哪里")) and text.endswith(("啊", "呢", "啊？", "呢？")):
        return True
    # Definition / paraphrase (火锅是什么 / 这个词什么意思)
    if "是什么" in text or "什么意思" in text or text.startswith("什么叫") or "指的是什么" in text:
        return True
    # Learner home country — follow-up interest (NZ most interesting place, etc.).
    # Tightened: bare "最好"/"好玩"/"有趣"/"特别" in a DECLARATIVE sentence is not
    # sufficient evidence of a question (e.g. "新西兰冰淇淋最好还有牛扒...都很好吃"
    # is a food-list answer, not a question).  Require actual interrogative
    # structure — a question mark, sentence-final 吗, or an explicit "which
    # place/where" word — alongside 新西兰.
    if "新西兰" in text and (
        any(ord(c) in (0xFF1F, 0x003F) for c in text)
        or text.rstrip("。！").endswith("吗")
        or any(k in text for k in ("哪里", "哪儿", "哪个", "什么地方"))
    ):
        return True
    # Place distance / never been — often no ？ (e.g. 从来没去过)
    if _looks_like_place_distance_question(text):
        return True
    # 谁 anywhere in a short utterance almost always signals a question
    # e.g. "你名字谁给你取的", "这个谁做的", "谁知道"
    if "谁" in text and len(text) <= 15:
        return True
    # Verb-not-verb pattern (A-not-A) — a standard Chinese question form with no ？
    # e.g. "这个工作难不难啊", "来不来", "好不好", "是不是你"
    _verb_not_verb_re = re.compile(
        r"([\u4e00-\u9fff]{1,3})不\1"
    )
    if _verb_not_verb_re.search(text):
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


def _is_direct_persona_question(t: str) -> bool:
    """
    True when learner text is a direct question about the partner persona's own facts.
    Used to override stale last_counter_reply / mirror-confusion state on topic switches
    (e.g. marriage answer → learner asks about work).
    """
    if not (t or "").strip():
        return False
    t = _normalize_zh_for_routing((t or "").strip()).replace("您", "你")
    if _is_confusion_signal(t):
        return False
    if _is_place_food_question(t) or _is_place_feature_question(t) or _is_cooking_question(t):
        return True
    if _find_mirror_answer(t, "", None):
        return True
    if _direct_persona_answer(t, None):
        return True
    _bare_work_q = ("做什么工作", "干什么工作", "什么工作", "做啥工作")
    if any(p in t for p in _bare_work_q):
        return True
    return _is_user_question({"submitted_text": t, "selected_option_hanzi": t})


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


def _direct_persona_answer(t: str, persona: Optional[dict],
                           recent_replies: Optional[list] = None) -> Optional[str]:
    """
    Detect direct questions aimed at the partner persona (你是哪里人？ 你住哪里？ etc.)
    and return a short first-person answer from persona profile/voice_lines.
    Returns None when no pattern matches.
    recent_replies: list of recent persona counter_replies used to suppress exact repeats.
    """
    t = _normalize_zh_for_routing(t or "")
    profile     = (persona or {}).get("profile") or {}
    voice_lines = (persona or {}).get("voice_lines") or {}
    name        = _assistant_name_from_persona(persona)
    _recent_set: set = set(recent_replies or [])

    # "你那里叫什么名字？" / "你那儿叫什么名字？" — learner asking for the name of where the
    # persona lives. Return city (current residence) before hometown as the primary answer.
    if any(p in t for p in ("那里叫什么", "那儿叫什么", "你那里叫", "你那儿叫")):
        city = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        loc = city or hometown
        if loc:
            return f"我住的地方叫{loc}。"
        return voice_lines.get("place") or "我住在中国，你有没有来过？"

    # Persona-self hometown precedence — always answer in first person; never let these
    # fall through to _CITY_LOCATION_BRIEF or encyclopedic place-fact tables.
    _PERSONA_HOMETOWN_MARKERS = (
        "你老家", "你的老家", "你家乡", "你的家乡", "家乡在哪", "家乡是哪",
        "你是哪里人", "你从哪里来", "你哪里人",
    )
    if any(m in t for m in _PERSONA_HOMETOWN_MARKERS):
        hometown = (profile.get("hometown") or "").strip()
        if hometown:
            return f"我老家在{hometown}。"
        return voice_lines.get("place") or "我老家在中国。"

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
    if any(p in t for p in ("名字有什么故事", "名字的故事", "名字怎么来", "名字怎么取",
                             "名字谁给", "谁给你取", "谁取的", "谁起的名字", "名字是谁")):
        fact = (_facts.get("identity") or "").strip()
        return fact if fact else "我的名字有一个小故事，家里人取的，有机会再说给你听。"
    # Name story / meaning via persona's actual name — catches:
    #   "建国有一个故事吗？" / "为什么叫建国？" / "建国这个名字有什么意思？"
    if name and (
        (name in t and any(k in t for k in ("故事", "意思", "这个名字", "名字怎么", "来历", "为什么叫", "为什么起")))
        or (any(t.startswith(p) for p in ("为什么叫", "为什么起")) and name in t)
    ):
        fact = (_facts.get("identity") or "").strip()
        return fact if fact else f"我的名字{name}，背后有一点故事，是家里人取的。"

    # Name / how to address (who-are-you / what-should-I-call-you)
    if any(p in t for p in ("你叫什么", "你叫啥", "怎么叫你", "你叫什么名字",
                             "你的名字叫", "你名字叫")):
        return (f"你可以叫我{name}。" if name else None)

    # "你现在还住在那里吗？" / "你还住在那里吗" — still-live-there question
    if any(p in t for p in ("还住在那里", "还住在那儿", "还在那里住", "还在那儿住",
                             "现在还住", "还是住在")):
        city_now = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        if city_now and hometown and city_now == hometown:
            return f"是的，我一直住在{city_now}，没有搬过。"
        if city_now and hometown and city_now != hometown:
            return f"现在主要住在{city_now}，不过老家还是{hometown}。"
        if city_now:
            return f"是的，我现在还住在{city_now}。"
        return "是的，我还在这边，没什么特别的变动。"

    # Cooking / dish questions — must precede the generic work handler.
    if _is_cooking_question(t):
        return _cooking_persona_answer(persona, seed=t)

    # Job / work — include "什么类型/什么样的工作" so work-type questions answer job.
    if any(p in t for p in ("你做什么工作", "你的工作", "你是做什么", "你工作",
                             "什么类型的工作", "类型的工作", "什么样的工作", "哪种工作",
                             "什么工作", "干什么工作")):
        occ = (profile.get("occupation") or "").strip()
        return voice_lines.get("work") or (f"我是{occ}。" if occ else "我也有工作。")

    # Travel / visited-places — "你去过哪里", "你去过哪些地方", "你旅游过哪里"
    # Must come BEFORE the generic place-preference handler to prevent travel questions
    # being answered with a residence fact.
    if any(p in t for p in ("你去过哪里", "你去过哪些", "你去过什么地方", "你旅游过", "你去过哪个")):
        travel_fact = (_facts.get("travel_where") or _facts.get("travel") or "").strip()
        if travel_fact:
            return travel_fact
        return voice_lines.get("travel") or "我去过几个城市，很有意思。"

    # Favourite place — "你最喜欢哪个地方/哪里" (mirror bank may also handle; this is backup).
    if "最喜欢" in t and any(k in t for k in ("地方", "哪里", "哪儿", "哪个", "什么")):
        travel_fav = (_facts.get("travel_where") or _facts.get("travel") or "").strip()
        if travel_fav:
            return travel_fav
        return voice_lines.get("travel") or "我去过几个地方，各有特色。"

    # Food-preference comparison — "你喜欢A菜还是B菜" / "你最喜欢成都菜和上海菜" /
    # "A菜好还是B菜". Intent is a preference between named cuisines; answer with a simple
    # persona preference rather than a location/uncertainty fallback.
    if ("菜" in t or "吃" in t) and any(m in t for m in ("还是", "和", "跟")) \
            and any(k in t for k in ("喜欢", "最喜欢", "爱吃", "好吃", "更")):
        _seg = re.sub(r'(最喜欢|喜欢|爱吃|好吃|更)', " ", t)
        _dishes = list(dict.fromkeys(re.findall(r'([\u4e00-\u9fff]{2,3}菜)', _seg)))
        if len(_dishes) >= 2:
            _a, _b = _dishes[0], _dishes[1]
            return f"两个我都挺喜欢的，不过{_a}更合我的口味，比较有味道。"
        if len(_dishes) == 1:
            return f"我挺喜欢{_dishes[0]}的，很有味道。"
        return "两个我都喜欢，各有各的味道。"

    # "你喜欢[place/city/hobby/food]吗" — intent is PREFERENCE, not place description.
    # IMPORTANT: never return voice_lines["place"] (a location/residence description)
    # as the answer to a preference question — that answers "where" not "do you like it".
    if t.startswith("你喜欢") and ("吗" in t or t.endswith("呢") or t.endswith("啊")):
        city     = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        # City-specific grounded preference pools — keyed by city name
        _CITY_LIKE_POOL: dict = {
            "北京": ["喜欢，北京生活很方便，机会也多。", "挺喜欢的，不过北京有时候节奏很快。",
                     "喜欢，北京很有历史文化，住在这里挺有意思的。"],
            "上海": ["挺喜欢的，上海很有活力，生活很方便。", "喜欢，上海很国际化，选择很多。",
                     "喜欢，上海节奏快，但也很有魅力。"],
            "成都": ["非常喜欢，成都生活很舒服，吃的也特别好。", "挺喜欢的，成都节奏慢，压力小。",
                     "喜欢，成都的美食和文化都很有特色。"],
            "西安": ["非常喜欢，西安历史文化太丰富了。", "挺喜欢的，西安的小吃和古迹都很有特色。",
                     "喜欢，西安有很多历史古迹，住在这里很有历史感。"],
            "重庆": ["非常喜欢，重庆的火锅是一绝！", "挺喜欢的，重庆山城的感觉很特别。",
                     "喜欢，重庆很有活力，吃的也很好。"],
            "南京": ["挺喜欢的，南京有很多历史，文化底蕴深。", "喜欢，南京生活节奏比较舒适。"],
            "杭州": ["挺喜欢的，杭州很美，西湖那边特别好。", "喜欢，杭州的自然风景和文化都很好。"],
        }
        # If the question mentions the persona's own city/hometown, return a preference answer
        for _pl in [city, hometown]:
            if _pl and _pl in t:
                _pool = _CITY_LIKE_POOL.get(_pl)
                if _pool:
                    return _pick_not_in(_pool, f"like|{_pl}|{t}", _recent_set)
                return f"挺喜欢的，{_pl}很有特色，住在这里挺好的。"
        # Asking about a city that's NOT the persona's city — generic positive
        for _city_name, _pool in _CITY_LIKE_POOL.items():
            if _city_name in t:
                return _pick_not_in(_pool, f"like|{_city_name}|{t}", _recent_set)
        # Generic hobby/food preference — route to the right voice_line
        if any(kw in t for kw in ("书法", "绘画", "音乐", "运动", "旅行", "下棋", "羽毛球")):
            return voice_lines.get("hobby") or "挺喜欢的，这是我的爱好。"
        if any(kw in t for kw in ("吃", "食物", "菜", "火锅", "饺子", "面", "辣")):
            return voice_lines.get("food") or "挺喜欢的，我对吃的很感兴趣。"
        return "还挺喜欢的，你呢？"

    # Hobbies / interests — "你喜欢什么" alone is too broad (catches "你喜欢什么颜色？" etc.)
    # Require either 爱好 / 做什么 / 玩什么 to confirm it's asking about hobbies.
    if any(p in t for p in ("你有什么爱好", "你喜欢做什么", "你喜欢玩什么", "你的爱好", "你平时喜欢")):
        interests = profile.get("interests") or []
        return voice_lines.get("hobby") or (f"我喜欢{interests[0]}。" if interests else "我也有很多爱好。")

    # Who partner lives with — expanded to include "跟谁一起住" / "和谁一起住" / "一起住" forms.
    if any(p in t for p in ("与谁住", "跟谁住", "和谁住", "与谁同住", "跟谁同住", "和谁同住",
                             "跟谁一起住", "和谁一起住", "跟谁一起", "一起住")):
        return voice_lines.get("family") or "我现在自己住，但和家人经常联系。"

    # Sibling presence questions: "你有姐妹吗？" / "你有兄弟吗？" / "你有没有姐？"
    # Distinct from sibling-detail questions (those carry the sibling word + action word).
    _SIB_PRESENCE_MARKERS = ("你有姐妹", "你有没有姐妹", "你有兄弟", "你有没有兄弟",
                              "你有没有哥", "你有没有弟", "你有没有姐", "你有没有妹",
                              "你有哥", "你有弟", "你有姐", "你有妹")
    if any(p in t for p in _SIB_PRESENCE_MARKERS):
        sib_fact = (_facts.get("family_siblings") or "").strip()
        if sib_fact:
            # First clause is usually the most direct answer
            _sib_short = re.split(r"[。！？，]", sib_fact)[0].strip()
            return _sib_short or sib_fact
        fam_fact = (_facts.get("family") or "").strip()
        if fam_fact and any(kw in fam_fact for kw in ("独生", "没有兄弟", "没有姐妹")):
            return fam_fact
        return "我有几个兄弟姐妹，大家关系挺好的。"

    # Parents: "你有爸爸妈妈吗？" / basic acknowledgment
    if any(p in t for p in ("你有爸爸妈妈", "你有没有爸爸", "你有没有妈妈")):
        _my_age = profile.get("age")
        if _my_age and isinstance(_my_age, (int, float)):
            _p_age = int(_my_age) + _stable_pick([22, 25, 28], f"parent_age_offset|{_my_age}")
            return f"有的，他们大概{int(_p_age)}多岁了，住在老家。"
        return "有的，我爸妈都在，住在老家。"

    # Family location: "你的家人在哪里？"
    if any(p in t for p in ("你的家人在哪", "你家人在哪", "家人住在哪", "家人在哪里")):
        fam_live = (_facts.get("family_live") or "").strip()
        if fam_live:
            return fam_live
        ht = (profile.get("hometown") or "").strip()
        city = (profile.get("city") or "").strip()
        if ht and city and ht != city:
            return f"我现在住在{city}，家人大多在{ht}那边。"
        loc = ht or city
        return f"家人在{loc}那边。" if loc else "家人住得不太远。"

    # Family — has family / siblings
    if any(p in t for p in ("你有家人", "你有没有家人", "你的家人")):
        return voice_lines.get("family") or "我也有家人。"

    # Parent / family member — check intent first: age vs location vs relationship.
    if any(p in t for p in ("你妈妈", "你爸爸", "你父母", "你爸妈", "你家人住", "你爸", "你妈",
                             "爸妈几岁", "父母几岁", "父母多大")):
        # Age intent: "你爸爸妈妈多大了" → return parent age, not location
        if any(aw in t for aw in ("多大", "几岁", "年龄")):
            _my_age = profile.get("age")
            if _my_age and isinstance(_my_age, (int, float)):
                _parent_age = int(_my_age) + _stable_pick([22, 25, 28], f"parent_age_offset|{_my_age}")
                _parent_age = int(_parent_age)
                return f"他们大概{_parent_age}多岁了。"
            return "他们五十多岁了。"
        # Location intent: "你妈妈在哪里住？" → return where parents live
        city = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        lives_with_family = voice_lines.get("family") or ""
        if "住在一起" in lives_with_family or "同一" in lives_with_family:
            loc = city or hometown or "这里"
            return f"我和父母住在{loc}附近，很近。"
        fam_live = (_facts.get("family_live") or "").strip()
        if fam_live:
            return fam_live
        if city:
            return f"我父母住在{city}。"
        if hometown:
            return f"我父母在{hometown}。"
        return "我父母住得不太远。"

    # Sibling (姐姐/哥哥/弟弟/妹妹) — age, work, or location questions.
    # Mirrors the parent block: derive plausible age; use city for work location; stay in-character.
    _SIBLING_WORDS = ("姐姐", "哥哥", "弟弟", "妹妹")
    _sib = next((s for s in _SIBLING_WORDS if s in t), None)
    if _sib:
        city = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        _my_age = profile.get("age")
        # Age intent: "你姐姐多大" / "你哥哥几岁"
        if any(aw in t for aw in ("多大", "几岁", "年龄")):
            if _my_age and isinstance(_my_age, (int, float)):
                _offset = _stable_pick([2, 3, 5], f"sib_age_offset|{_my_age}|{_sib}")
                _sib_age_approx = int(_my_age) + (_offset if _sib in ("姐姐", "哥哥") else -_offset)
                return f"我{_sib}大概{max(18, _sib_age_approx)}岁左右。"
            return f"我{_sib}比我大几岁，具体我记不太清了。" if _sib in ("姐姐", "哥哥") else f"我{_sib}比我小几岁。"
        # Work intent: "你姐姐做什么工作" / "你姐姐的工作"
        if any(aw in t for aw in ("做什么工作", "工作", "做什么", "职业", "上班")):
            if city:
                return f"她在{city}工作，具体做什么我不太清楚。"
            if hometown:
                return f"她在{hometown}那边，具体做什么我不太清楚。"
            return f"我{_sib}有工作，但具体做什么我没问过她。"
        # Location / default: "你姐姐在哪里" / bare mention
        if any(aw in t for aw in ("在哪", "住哪", "哪里", "哪儿")):
            loc = city or hometown
            if loc:
                return f"我{_sib}住在{loc}。"
            return f"我{_sib}住得不太远。"
        # Bare mention with no recognised sub-intent — return something helpful
        if city:
            return f"我有一个{_sib}，她在{city}那边。"
        return f"我有一个{_sib}，我们偶尔联系。"

    # Work like / enjoyment — "你喜欢这个工作吗？" / "你喜欢你的工作吗？"
    # Must fire BEFORE the generic hobby/interest handler to avoid mismatch.
    if "喜欢" in t and any(k in t for k in ("工作", "这份", "这个工作", "你的工作")):
        _work_like = voice_lines.get("work_like") or (_facts.get("work") or "").strip()
        if _work_like:
            return _work_like
        _occ = (profile.get("occupation") or "").strip()
        if _occ:
            return f"还挺喜欢的，做{_occ}可以学到很多。"
        return "还挺喜欢的，慢慢就越来越有意思了。"

    # ── Hobby follow-up handlers ──────────────────────────────────────────────────
    # These use hobby-specific keywords (玩, 练, 学, 爱好) to avoid collisions with
    # the work-duration block (which uses 做, 工作, 这份工作 etc.).

    # How long doing the hobby: "你玩这个多久了？" / "你练这个多久了？" / "这个爱好多长时间了？"
    _HOBBY_DUR_MARKERS = ("玩这个多久", "练这个多久", "学这个多久", "打这个多久",
                           "玩多久了", "练多久了", "学多久了",
                           "爱好多久", "爱好多长时间", "爱好多少年")
    if any(m in t for m in _HOBBY_DUR_MARKERS):
        _hobby_fact = (_facts.get("hobby") or "").strip()
        if _hobby_fact:
            # hobby fact often starts with the duration ("我打羽毛球打了快二十年了，…")
            return _hobby_fact
        return "已经玩了好几年了，越来越喜欢。"

    # How the hobby started: "你是怎么开始这个爱好的？" / "你怎么学会的？" / "怎么接触到的？"
    _HOBBY_ORIGIN_MARKERS = ("怎么开始这个爱好", "怎么开始这个", "怎么学会", "怎么接触", "怎么喜欢上",
                              "怎么开始打", "怎么开始玩", "怎么开始练", "怎么开始学",
                              "为什么学", "为什么练", "为什么开始")
    if any(m in t for m in _HOBBY_ORIGIN_MARKERS):
        _origin_fact = (_facts.get("hobby_origin") or "").strip()
        if _origin_fact:
            return _origin_fact
        return "小时候接触到，慢慢就喜欢上了，一直坚持到现在。"

    # Favourite aspect: "你最喜欢这个爱好的哪一点？" / "这个爱好哪里好？"
    _HOBBY_BEST_MARKERS = ("最喜欢这个爱好的哪一点", "爱好哪里好", "爱好最喜欢", "这个爱好有什么好",
                            "你喜欢这个爱好的什么", "最喜欢哪一点", "你最喜欢这个爱好")
    if any(m in t for m in _HOBBY_BEST_MARKERS):
        _best_fact = (_facts.get("hobby_best") or "").strip()
        if _best_fact:
            return _best_fact
        return "让我放松的那种感觉，做完以后心情很好。"

    # Why like the hobby: "你为什么喜欢这个？" / "为什么喜欢这个爱好？"
    _HOBBY_WHY_MARKERS = ("为什么喜欢这个爱好", "为什么喜欢打", "为什么喜欢玩", "为什么喜欢练",
                           "为什么喜欢这个", "喜欢这个的原因")
    if any(m in t for m in _HOBBY_WHY_MARKERS):
        _best_fact = (_facts.get("hobby_best") or "").strip()
        if _best_fact:
            return _best_fact
        _origin_fact = (_facts.get("hobby_origin") or "").strip()
        if _origin_fact:
            return _origin_fact
        return "很难说具体原因，就是喜欢那种感觉，做了就停不下来。"

    # ── Food-specific place questions — "X有什么好吃的？" / "X好吃的" / "那里有什么好吃的" ──
    # Separated from the general feature block so food questions always get food answers,
    # not history/culture facts (the generic pool has both and random selection was the bug).
    if _is_place_food_question(t):
        _CITY_FOOD_POOL: dict = {
            "西安": ["西安的小吃非常有名！凉皮和肉夹馍是我最喜欢的，特别好吃。",
                     "西安有很多特色小吃，凉皮、肉夹馍、羊肉泡馍，每一样都很值得尝试。"],
            "成都": ["成都美食太丰富了，火锅最有名，但担担面、龙抄手也很好吃。",
                     "成都的火锅和串串香都很出名，小吃种类也非常多。"],
            "重庆": ["重庆的小面和火锅都很有名，喜欢辣的话一定要去试试！",
                     "重庆的火锅比成都的还辣，小面的汤底也特别香。"],
            "上海": ["上海的本帮菜很有特色，红烧肉和清蒸鱼都非常好吃，还有生煎包。",
                     "上海有很多本地小吃，生煎包、小笼包都是经典，值得一试。"],
            "南京": ["南京的鸭血粉丝汤特别有名，还有各种鸭肉做的菜，非常有特色。"],
            "北京": ["北京的烤鸭最有名，炸酱面也很有特色，还有豆汁这种老北京独特的饮品。"],
            "杭州": ["杭州有东坡肉、西湖醋鱼，还有龙井虾仁，都非常好吃。"],
        }
        city = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        _resolved_food_place = _place_from_question_context(t, recent_replies)
        if _resolved_food_place and _resolved_food_place in _CITY_FOOD_POOL:
            _fpool = _CITY_FOOD_POOL[_resolved_food_place]
            _food_personal = (_facts.get("food") or "").strip()
            # RC-B: Only prefer the persona's personal food fact when it actually
            # describes the asked place.  A persona whose city=上海 and fact mentions
            # 上海 must not have that fact returned for a 南京 (hometown) food question
            # — use the pool entry for 南京 instead.
            _personal_matches_place = (
                _food_personal and _resolved_food_place in _food_personal
            )
            if _resolved_food_place in (hometown, city) and _personal_matches_place:
                return _food_personal
            return _pick_not_in(_fpool, f"food_q|{_resolved_food_place}|{t}", _recent_set)
        for _loc, _fpool in _CITY_FOOD_POOL.items():
            if _loc in t:
                _food_personal = (_facts.get("food") or "").strip()
                _personal_matches_place = (
                    _food_personal and _loc in _food_personal
                )
                if _loc in (hometown, city) and _personal_matches_place:
                    return _food_personal
                return _pick_not_in(_fpool, f"food_q|{_loc}|{t}", _recent_set)
        # No specific place named — use persona's own food fact
        _pf = (_facts.get("food") or "").strip()
        if _pf:
            return _pf
        # Fall through to general feature handler

    # City/place feature questions — e.g. "北京有什么特别啊", "重庆特别的", "重庆怎么样"
    # Intent: "what's special/interesting about this place?" — must answer WITH FEATURES, not origin facts.
    if _is_place_feature_question(t):
        city = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        # City-specific feature pools — grounded and beginner-friendly
        _CITY_FEATURE_POOL: dict = {
            "北京": ["北京很大，历史文化非常丰富，长城和故宫都在这里。", "北京机会很多，是个很有活力的城市。",
                     "北京有很多历史古迹，还有很多好吃的小吃。"],
            "上海": ["上海很国际化，外滩的夜景特别漂亮。", "上海很繁华，购物和美食选择都很多。",
                     "上海节奏快，但也很有魅力，老弄堂和新高楼都很有特色。"],
            "成都": ["成都的节奏比较慢，大家都很悠闲，火锅也是一绝！", "成都的美食特别有名，火锅、串串都很好吃。",
                     "成都生活很舒服，茶馆文化很有特色，大家喜欢坐在茶馆聊天。"],
            "西安": ["西安历史文化太丰富了，兵马俑、大雁塔都在那里。", "西安的小吃很有名，凉皮、肉夹馍都很好吃。",
                     "西安是古都，到处都有历史遗迹，很有文化感。"],
            "重庆": ["重庆是山城，到处都是坡路，风景很特别。", "重庆的火锅是全国最有名的，很辣很好吃！",
                     "重庆的夜景非常漂亮，尤其是洪崖洞那一带。"],
            "南京": ["南京历史很悠久，有很多历史遗迹。", "南京的鸭血粉丝汤很有名，小吃也很多。"],
            "杭州": ["杭州的西湖非常漂亮，是个很出名的景点。", "杭州自然风景很美，还有很多茶文化。"],
            "苏州": ["苏州的园林很有名，特别有诗意。", "苏州的古镇和水乡很有特色，景色很美。"],
            "中关村": ["中关村是北京的科技中心，很多科技公司都在这里。", "中关村非常现代，科技氛围很浓。"],
        }
        # 1. Extract the question clause (segment nearest the feature marker) so that
        #    the focus city of the question wins over background mentions.
        _feature_clause_markers = (
            "有什么特别", "特别之处", "有什么特色", "有什么好玩", "有什么有意思", "怎么样",
        )
        _question_clause = t
        for _fmk in _feature_clause_markers:
            if _fmk in t:
                _fidx = t.rfind(_fmk)
                for _bnd in ("。", "！", "？", "，"):
                    _bidx = t.rfind(_bnd, 0, _fidx)
                    if _bidx >= 0:
                        _question_clause = t[_bidx + 1:].strip()
                        break
                break

        _resolved_feature_place = _place_from_question_context(t, recent_replies)
        if _resolved_feature_place and _resolved_feature_place in _CITY_FEATURE_POOL:
            return _pick_not_in(
                _CITY_FEATURE_POOL[_resolved_feature_place],
                f"feature|{_resolved_feature_place}|{t}",
                _recent_set,
            )

        # 1a. Persona travel-fact lookup for foreign/overseas places not in the pool.
        #     e.g. "日本有什么特别的？" → xiaoming's travel_where: "…最喜欢日本，拉面和温泉印象特别深"
        #          "法国有什么特别的？" → zhiyuan's travel_where: "…最喜欢法国，觉得他们对历史和艺术的态度很有意思"
        _tf_where = (_facts.get("travel_where") or _facts.get("travel") or "").strip()
        if _tf_where:
            # Extract 2–4 char place-name tokens from the question clause
            _qplace_candidates = re.findall(r'([\u4e00-\u9fff]{2,4})(?=有什么|有啥|怎么样|好玩|特别|特色)', _question_clause or t)
            for _qp in _qplace_candidates:
                if _qp in _CITY_FEATURE_POOL:
                    break  # handled by pool below; don't intercept
                if _qp in _tf_where:
                    # Persona has travelled there — find the clause that mentions it
                    _tf_clauses = [c.strip() for c in re.split(r'[，。！？、,]', _tf_where) if c.strip()]
                    _best = next((c for c in _tf_clauses if _qp in c and len(c) > 4), None)
                    if _best:
                        _suffix = "。" if _best[-1] not in "。！？" else ""
                        return _best + _suffix
                    # Fallback: the full travel fact (first clause)
                    return _first_clause(_tf_where)

        # Check question clause first; then full text as fallback.
        for _loc, _pool in _CITY_FEATURE_POOL.items():
            if _loc in _question_clause:
                return _pick_not_in(_pool, f"feature|{_loc}|{t}", _recent_set)
        for _loc, _pool in _CITY_FEATURE_POOL.items():
            if _loc in t:
                return _pick_not_in(_pool, f"feature|{_loc}|{t}", _recent_set)
        # 2. Check if question is about the persona's city or hometown
        for _pl in [city, hometown]:
            if _pl:
                _pool = _CITY_FEATURE_POOL.get(_pl)
                if _pool:
                    return _pick_not_in(_pool, f"feature|{_pl}|{t}", _recent_set)
        # 3. Use discoverable_facts["place"] ONLY if it sounds like a feature (not an origin statement).
        fact_place = (_facts.get("place") or "").strip()
        _origin_markers = ("老家是", "老家在", "来自", "毕业后", "工作后", "住在", "来北京", "来上海", "来成都")
        _fact_is_feature = fact_place and not any(m in fact_place for m in _origin_markers)
        if _fact_is_feature:
            return fact_place
        # 4. Generic place feature fallback
        loc = city or hometown
        if loc:
            return f"哎，{loc}太有特色了，说也说不完！"
        return "那个地方很有特色，有机会可以去看看！"

    # Married / partner status — check persona discoverable_facts first, then cooperative default.
    # Covers both 你-prefixed forms and bare omitted-subject question forms (结婚了吗 / 结婚没有).
    if any(p in t for p in ("你结婚", "你有没有结婚", "你有对象", "你有伴侣",
                             "你有男朋友", "你有女朋友", "你成家了",
                             "结婚了吗", "结婚了没", "结婚没有", "结婚没", "成家了吗",
                             "结婚了嘛", "有没有结婚", "有对象吗", "单身吗")):
        _marriage_fact = (_facts.get("marriage") or "").strip()
        if _marriage_fact:
            return _marriage_fact
        return _persona_deflect("marriage", t)

    # Children — phrase from recovery_phrases.json (use=persona_deflect, topic=children)
    if any(p in t for p in ("你有孩子", "你有小孩", "你有儿子", "你有女儿", "你有宝宝")):
        return _persona_deflect("children", t)

    # Work difficulty / quality — e.g. "这个工作难不难啊", "工作累不累", "工作怎么样"
    if any(p in t for p in ("难不难", "累不累", "辛不辛苦", "工作怎么样", "工作累吗",
                             "工作有没有意思", "工作有趣吗", "工作好不好")):
        occ = (profile.get("occupation") or "").strip()
        work_line = voice_lines.get("work") or ""
        if work_line:
            return work_line
        if occ:
            return f"{occ}嘛，有挑战，但还可以，挺有意思的。"
        return "工作嘛，有时候忙，但还可以，挺有意思的。"

    # Age — use profile.age if available; only deflect when explicitly absent.
    # "年龄啊，先不说吧。" is annoying when the persona has a known age.
    if any(p in t for p in ("你多大", "你几岁", "你的年龄", "你今年多大")):
        _age = profile.get("age")
        if _age and isinstance(_age, (int, float)):
            _age_i = int(_age)
            return f"我今年{_age_i}岁。"
        return _persona_deflect("age", t)

    # Family closeness — e.g. "你和爸爸妈妈近吗？" / "你跟爸爸妈妈亲近吗？" / "你和父母近吗？"
    _FAM_CLOSE_MARKERS = ("和爸爸妈妈近", "跟爸爸妈妈近", "和父母近", "跟父母近",
                           "和爸妈近", "跟爸妈近", "爸妈近吗", "父母亲近", "和家人近",
                           "跟家人近", "家人亲近")
    if any(m in t for m in _FAM_CLOSE_MARKERS):
        _fam_live = (_facts.get("family_live") or "").strip()
        if _fam_live:
            return _fam_live
        _fam_fact = (_facts.get("family") or "").strip()
        if _fam_fact:
            return _first_clause(_fam_fact)
        return "挺近的，虽然不住在一起，但经常打电话联系。"

    # Why like a place — "你为什么喜欢那里？" / "你为什么喜欢那个地方？" / "为什么觉得那里好？"
    # Companion to travel_why_fav in _mirror_persona_stub; handles 你-prefixed and informal phrasings.
    _WHY_LIKE_PLACE_MARKERS = ("为什么喜欢那里", "为什么喜欢那个地方", "为什么觉得那里", "为什么那里好",
                                "为什么那么喜欢", "你为什么喜欢", "喜欢那里的原因")
    if any(m in t for m in _WHY_LIKE_PLACE_MARKERS):
        _travel_fact = (_facts.get("travel") or _facts.get("travel_where") or "").strip()
        _why_markers = ("觉得", "因为", "喜欢", "特别", "最", "印象", "历史", "文化", "艺术", "诗意", "有意思")
        _clauses = [c.strip() for c in re.split(r'[，。！？,]', _travel_fact) if c.strip()] if _travel_fact else []
        _why = next((c for c in _clauses if any(m in c for m in _why_markers)), None)
        if _why:
            return _why + "。"
        if _travel_fact:
            return _first_clause(_travel_fact)
        _place_fact = (_facts.get("place") or "").strip()
        if _place_fact:
            return _first_clause(_place_fact)
        city = (profile.get("city") or profile.get("hometown") or "").strip()
        return f"感觉那里很有特色，生活节奏和文化都挺吸引人的。"

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

    # Work duration — must come BEFORE the travel-time handler which also matches 多长时间.
    # e.g. "你做这个工作多久了", "你从事软件开发工作多长时间了", "工作多少年了", bare "做多久了"
    # Bare "做多久了" / "做多久" is included; gated to work context by surrounding conversation
    # but safe here because the work block fires only after identity/place/hobby are ruled out.
    if any(p in t for p in ("工作多久", "做这个多久", "做了多久", "从事", "工作多长时间", "这份工作多久",
                             "这个工作多久", "工作了多久", "做了多长时间", "工作多少年",
                             "做多久了", "做多久", "做多长时间")):
        _work_fact    = (_facts.get("work") or "").strip()
        _occ          = (profile.get("occupation") or "").strip()
        # Duration must answer "how long" — prefer a clause that actually contains a
        # duration marker (年/久/教了/做了/开始/以来/毕业).  Never return work_origin
        # here: that is the *reason* the persona took the job, not its duration.
        _dur_markers = ("年", "久", "教了", "做了", "开始", "以来", "毕业", "一直")
        if _work_fact:
            _clauses = [c.strip() for c in re.split(r"[，。！？,]", _work_fact) if c.strip()]
            _dur_clause = next((c for c in _clauses if any(m in c for m in _dur_markers)), "")
            if _dur_clause:
                return _dur_clause + ("。" if not _dur_clause.endswith("。") else "")
        if _occ:
            return f"做{_occ}已经好几年了，越来越有经验了。"
        return "已经做了几年了，越做越有意思。"

    # Extended family member location — e.g. "你奶奶住在哪里啊", "你爷爷在哪里"
    # Give a grounded but simple answer rather than evasive deflect.
    _ext_fam = ("奶奶", "爷爷", "外婆", "外公", "姥姥", "姥爷")
    if any(fw in t for fw in _ext_fam):
        ht = (profile.get("hometown") or "").strip()
        city = (profile.get("city") or "").strip()
        rel  = next((fw for fw in _ext_fam if fw in t), "老人")
        if ht:
            return f"我{rel}住在{ht}那边，离我有点远。"
        if city:
            return f"我{rel}在{city}附近。"
        return f"我{rel}住在老家，我们不常见面，但会联系。"

    # Distance / travel time / transport questions
    if any(p in t for p in ("离那边远吗", "离那边", "离那里远", "离北京远", "离上海远", "离成都远", "离广州远")):
        dp = (persona or {}).get("distance_profile") or {}
        zh_pre = (dp.get("zh") or "").strip()
        if zh_pre:
            return zh_pre
        far = (dp.get("far_level") or "不算太远").strip()
        ref = (dp.get("reference") or "那边").strip()
        ht = ((persona or {}).get("profile") or {}).get("hometown") or ""
        return f"{ht}离{ref}{far}。" if ht else "不算太远。"

    if any(p in t for p in ("要多久", "多久到", "需要多长时间", "多长时间")):
        dp = (persona or {}).get("distance_profile") or {}
        time_val = (dp.get("time") or "几个小时").strip()
        transport = (dp.get("transport") or "交通工具").strip()
        return f"坐{transport}要{time_val}左右。"

    if any(p in t for p in ("怎么去", "坐什么去", "怎样去")):
        dp = (persona or {}).get("distance_profile") or {}
        transport = (dp.get("transport") or "高铁").strip()
        return f"一般坐{transport}去。"

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


# ── Conversational filler normalisation ──────────────────────────────────────
# Leading fillers (啊, 嗯, 那个, 就是, ne…) should not prevent content
# classification.  Strip them before pattern matching — but only when
# meaningful content remains afterwards.
_FILLER_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:[啊嗯呃哦哎呀唉]+)[，。\s]*"   # single-character filler particles
    r"|(?:那个|就是|然后|这个|好那|嗯那)[，\s]*"  # discourse markers
    r"|(?:ne|ah|um|uh|er)\s+"            # Latin fillers (need trailing space)
    r")+",
    re.IGNORECASE,
)


def _strip_leading_fillers(text: str) -> str:
    """Return text with leading conversational fillers removed.

    Preserves the original when:
    - No filler prefix is found, OR
    - Stripping would leave fewer than 2 characters (standalone filler → keep for
      confusion / affirmation detection).
    """
    s = (text or "").strip()
    if not s:
        return s
    stripped = _FILLER_PREFIX_RE.sub("", s).strip()
    return stripped if len(stripped) >= 2 else s


# Collapse ASR-inserted spaces between CJK characters: "重 庆 有 什么" → "重庆有什么".
_CJK_SPACING_RE = re.compile(
    r"(?<=[\u4e00-\u9fff\u3400-\u4dbf])\s+(?=[\u4e00-\u9fff\u3400-\u4dbf])"
)
# Safe trailing particles stripped from the routing copy only (not the raw transcript).
_TRAILING_ROUTING_FILLER_RE = re.compile(r"[啊呢吧嗯哈啦]+[？?！!。.]*$")

_PLACE_DEIXIS_MARKERS: tuple = (
    "那里", "那儿", "这边", "那边", "这里", "这儿", "你那儿", "你那",
)


def _normalize_zh_for_routing(text: str) -> str:
    """Return a routing-normalized copy of learner Chinese for intent matching.

    Does not mutate the input.  Preserves the original submitted text separately
    for transcript display and memory capture.
    """
    s = (text or "").strip()
    if not s:
        return s
    s = _strip_leading_fillers(s)
    s = _CJK_SPACING_RE.sub("", s)
    s = s.strip()
    s = _TRAILING_ROUTING_FILLER_RE.sub("", s).strip()
    return s


def _is_place_food_question(t: str) -> bool:
    """True when the learner asks what is good to eat at a named place or deictic 'there'."""
    if not (t or "").strip():
        return False
    if any(m in t for m in (
        "有什么好吃", "有什么吃的", "有什么美食", "有什么特色小吃", "好吃的有什么",
    )):
        return True
    if re.search(r"(?:那里|那儿|这边|那边|这里|这儿).{0,4}好吃的", t):
        return True
    if re.search(r"[\u4e00-\u9fff]{2,4}好吃的", t):
        return True
    if "什么" in t and "好吃" in t:
        return True
    return False


# Nouns that make "特别的X" a question about something OTHER than a place — either
# the PERSONA's own possession (hobby, tradition, habit, story, etc. — "你有什么特别的
# 爱好？" / "你家有什么特别的传统？") or an abstract requirement/condition ("需要有什么
# 特别的条件" — asking about requirements, not a city). Kept narrow and explicit so
# genuine place questions like "有什么特别的地方" are unaffected.
_PLACE_FEATURE_NON_PLACE_NOUNS: tuple = (
    "爱好", "传统", "习惯", "经历", "才能", "技能", "本事", "手艺", "故事", "回忆",
    "条件", "要求", "规定", "限制",
)


def _is_place_feature_question(t: str) -> bool:
    """True when the learner asks what is special/interesting about a place.

    Food questions take precedence — returns False when _is_place_food_question is True.
    Guards against personal-possession questions ("你有什么特别的爱好？") which must
    never be mistaken for a city-feature question even though they share "特别的".
    """
    if not (t or "").strip() or _is_place_food_question(t):
        return False
    if any(("特别的" + n) in t for n in _PLACE_FEATURE_NON_PLACE_NOUNS):
        return False
    if any(m in t for m in (
        "有什么特别", "特别之处", "有什么特色", "有什么好玩", "有什么有意思",
    )):
        return True
    if re.search(r"[\u4e00-\u9fff]{2,4}特别的", t):
        return True
    if re.search(r"[\u4e00-\u9fff]{2,4}怎么样", t):
        return True
    if "怎么样" in t and len(t) <= 12:
        return True
    return False


def _is_cooking_question(t: str) -> bool:
    """True when the learner asks what dishes the persona cooks."""
    if not (t or "").strip() or "菜" not in t:
        return False
    if any(m in t for m in (
        "你做什么菜", "你会做什么菜", "你最拿手什么菜", "你最喜欢做什么菜",
        "做什么菜", "会做什么菜", "拿手什么菜", "最喜欢做什么菜",
    )):
        return True
  # Require an explicit cook verb — not bare 喜欢 (food-preference comparisons use 喜欢 too).
    return (
        "你" in t
        and any(v in t for v in ("做", "会", "拿手"))
        and "工作" not in t
    )


def _is_confusion_signal(t: str) -> bool:
    """Learner signals they did not understand — not a new content question."""
    if not (t or "").strip():
        return False
    s = t.strip()
    # Exact-match short confusion utterances (safe — specific enough to not false-positive)
    if s in ("啊", "嗯", "呃", "哎", "噢", "哦", "什么", "不懂", "哪里啊"):
        return True
    # Avoid matching genuine content questions (哪里好玩 = real question, not confusion)
    if "是什么" in s or re.search(r"新西兰|哪里.*好玩|哪里.*有趣|哪里.*特别", s):
        return False
    # Genuine second-person persona questions ("你住在哪里啊", "你去过哪里啊") merely
    # *contain* a confusion substring ("哪里啊"); they are real questions directed at the
    # persona, not the learner's own non-understanding signal.  "我问你…" is an explicit
    # persona-question opener and must never be read as confusion.
    if "我问你" in s:
        return False
    if re.search(r"你.{0,6}(住|去过|去|喜欢|老家|家乡|工作|做什么|叫什么|多大|结婚|有什么|最)", s):
        return False
    markers = (
        "哪里啊", "不懂",  # confusion about which place / general incomprehension
        "啊？", "啊！", "我不懂", "有点不懂", "听不懂", "没听懂", "没懂", "不明白",
        "看不懂", "什么意思", "没太懂", "再说一遍", "再说一次", "再说一起", "再说一下",
        "请再说", "慢一点", "慢一",
        "不知道", "等一下", "我听不懂",
    )
    return any(m in s for m in markers)


_CLOSING_BLOCK_FRUSTRATION: tuple = (
    "太难了", "太难", "好难啊", "好难", "这太难了",
    "算了", "算了吧",
    "你说得太快", "太快了", "说太快", "讲太快",
    "跟不上", "我跟不上",
    "放弃",
)

# Frustration / insult markers directed at the persona.  These require a social
# repair (apology) — never a generic positive acknowledgement ("这样挺好").
_FRUSTRATION_INSULT_MARKERS: tuple = (
    "傻瓜", "笨蛋", "白痴", "蠢货", "神经病",
    "不喜欢跟你说话", "不喜欢跟你说", "不想跟你说", "不想跟你聊", "不想跟你讲",
    "你听不懂", "你不懂", "你不明白", "你没用", "你真没用",
    "讨厌你", "烦死了", "不说了", "没意思",
)


def _is_frustration_or_insult(text: str) -> bool:
    """Learner is frustrated or insulting the persona — needs an apology / repair,
    not a positive acknowledgement.  Covers both explicit give-up frustration and
    persona-directed insults."""
    t = (text or "").strip()
    if not t:
        return False
    if any(m in t for m in _FRUSTRATION_INSULT_MARKERS):
        return True
    if any(m in t for m in _CLOSING_BLOCK_FRUSTRATION):
        return True
    return False

_CLOSING_BLOCK_CONTINUATION: tuple = (
    "继续", "继续说", "请继续",
    "然后呢", "然后", "那然后",
    "接着", "接着说", "接着讲",
    "下面", "接下来",
    "还有吗", "还有呢", "然后怎么样", "还有什么",
)

_CLOSING_BLOCK_POST_FALLBACK: tuple = (
    "电脑角色",
    "这个我不太清楚",
    "这个我不太确定",
    "不好说",
    "不太了解这个",
    "我真的不太了解",
    "不太清楚，不过我们可以聊聊",
)


def _is_closing_blocked_by_learner_signal(
    answer_text: str,
    prev_partner_text: str = "",
) -> tuple:
    """Return (blocked: bool, reason: str) for closing-move gate.

    Blocks closing_move when the conversation is visibly broken or the learner
    is seeking more content rather than wrapping up.  Reasons:

    confusion_or_recovery  — learner signalled non-understanding (再说一遍, 什么意思…)
    frustration            — explicit difficulty / give-up signal (太难了, 算了…)
    continuation_request   — learner asked for more (继续, 然后呢…)
    low_asr_confidence     — very short / non-CJK input; likely ASR junk
    post_generic_fallback  — last partner turn was a generic limitation reply
    """
    t = (answer_text or "").strip()

    if _is_confusion_signal(t):
        return (True, "confusion_or_recovery")

    if any(m in t for m in _CLOSING_BLOCK_FRUSTRATION) or any(m in t for m in _FRUSTRATION_INSULT_MARKERS):
        return (True, "frustration")

    if any(m in t for m in _CLOSING_BLOCK_CONTINUATION):
        return (True, "continuation_request")

    # Low-confidence ASR: single visible character, or entirely non-CJK text
    # (Latin, numerals, punctuation alone) when a real learner answer is expected.
    _cjk_chars = [c for c in t if "\u4e00" <= c <= "\u9fff"]
    _visible = t.strip("。！？，,.!? \t\n")
    if _visible and len(_visible) == 1 and not _cjk_chars:
        return (True, "low_asr_confidence")
    if _visible and not _cjk_chars and len(_visible) >= 1:
        # Entirely non-CJK input of any length — ASR junk or accidentally tapped
        return (True, "low_asr_confidence")

    if prev_partner_text and any(m in prev_partner_text for m in _CLOSING_BLOCK_POST_FALLBACK):
        return (True, "post_generic_fallback")

    return (False, "")


def _is_explicit_topic_switch(text: str) -> bool:
    """
    Return True when the learner uses an explicit discourse marker to signal
    they are voluntarily switching topics (e.g. "对了", "还有", "我想问你").
    Used to allow the learner to break out of a pending-frame commitment.
    """
    t = (text or "").strip()
    if not t:
        return False
    _markers = ("对了", "还有", "我想问你", "顺便问一下", "另外", "说起来", "话说")
    return any(m in t for m in _markers)


def _is_plain_affirmation(text: str) -> bool:
    """Return True when `text` is a short, standalone affirmation with no additional content.

    Matches 对 / 对对 / 是的 / 没错 / 嗯 / 嗯嗯 / 好的 / 就是 / 对啊 / 是啊 / 对的.
    Deliberately strict: only fires when the entire response is essentially
    'yes / correct / right' so that longer answers containing 对 are not swallowed
    (e.g. "对，我住在北京" is NOT a plain affirmation — the learner is giving information).
    """
    t = (text or "").strip().rstrip("。！，.!,～~")
    if not t:
        return False
    _AFF = {"对", "对对", "是的", "没错", "嗯", "嗯嗯", "好的", "就是", "对啊",
            "是啊", "对的", "是", "嗯对", "对对对", "没错的", "是是", "嗯嗯嗯"}
    return t in _AFF


_PLACE_DESC_WORDS: frozenset = frozenset({
    "安静", "方便", "热闹", "繁华", "冷清", "漂亮", "风景", "好看", "景色",
    "美丽", "城市", "市区", "郊区", "农村", "海边", "山边", "湖边",
    # Broadened semantic content so descriptive place answers advance (see
    # place_special regression): scenery, nature, food, cleanliness, ports.
    "山", "水", "动物", "牛肉", "羊肉", "冰淇淋", "干净", "海", "港口", "食物",
})

# Extra content words accepted specifically for the "有什么特别的？" place-special
# question.  Superset of _PLACE_DESC_WORDS plus a few single-char tokens that are
# too broad for generic location validation but valid as place-special content.
_PLACE_SPECIAL_CONTENT_WORDS: frozenset = _PLACE_DESC_WORDS | frozenset({
    "羊", "小",
})


def _is_place_special_answer(text: str) -> bool:
    """Return True when `text` contains broad place-special semantic content.

    Used to mark a "这里/那里/你的家乡/…有什么特别的？" question as answered so the
    conversation advances instead of re-asking. Accepts scenery, nature, animals,
    food, and quality descriptors (风景/山/水/动物/羊/牛肉/港口/干净/…).
    """
    t = (text or "").strip()
    return bool(t) and any(w in t for w in _PLACE_SPECIAL_CONTENT_WORDS)


def _is_place_description(text: str) -> bool:
    """Return True when `text` contains place-quality descriptors rather than a place name.

    Recognises partial but meaningful location answers like "安静风景很好看" so that
    noisy-location re-ask and model-answer escalation are suppressed — the learner
    is communicating real content even if no city name was detected.
    Deliberately excludes generic positive words (好, 很好) that appear in non-place turns.
    """
    t = (text or "").strip()
    return bool(t) and any(w in t for w in _PLACE_DESC_WORDS)


_WHY_LIKE_MARKERS: tuple = (
    "为什么喜欢", "为啥喜欢", "怎么喜欢上的", "为什么喜欢这个", "为什么喜欢那个",
    "喜欢的原因", "为什么觉得好",
)


def _is_why_like_follow_up(user_text: str) -> bool:
    """True when the learner asks why the partner likes something (adjacency guard for F2)."""
    if not user_text:
        return False
    return any(m in user_text for m in _WHY_LIKE_MARKERS)


def _is_relevant_to_frame(text: str, frame_id: str) -> bool:
    """Return True when `text` is topically relevant to the question `frame_id` asked.

    Used by the pending-frame commitment guard to decide whether an off-topic
    learner answer should trigger a clarification re-ask.  Lightweight keyword
    check only — no embeddings, deterministic lookup table.
    """
    if not text:
        return False
    if frame_id == "f_name_story":
        return any(k in text for k in ("故事", "名字", "叫", "取"))
    if frame_id == "f_what_work":
        return any(k in text for k in ("工作", "老师", "公司", "上班", "退休", "大学", "教"))
    if frame_id == "f_live_where":
        return any(k in text for k in ("住", "在", "哪里", "地方", "新西兰", "奥克兰"))
    if frame_id == "f_from_where":
        return any(k in text for k in ("人", "来自", "新西兰人", "中国人", "老家"))
    if frame_id == "f_live_with_who":
        return any(k in text for k in ("太太", "老婆", "家人", "爸爸", "妈妈", "儿子", "女儿", "一起住"))
    if frame_id in ("p2_pl_far", "f_place_distance_time", "f_place_distance_ref"):
        return any(k in text for k in ("远", "近", "飞机", "火车", "走路", "小时", "分钟", "公里", "地方"))
    return False


# Frames protected by the pending-frame commitment guard (counter-reply and
# frame-selection levels).  Extend this set — not the guard logic itself —
# when new frames need protecting.
_COMMITMENT_GUARD_FRAMES: frozenset = frozenset({
    "f_what_work",
    "f_live_where",
    "f_from_where",
    "f_live_with_who",
    "p2_pl_far",
    "f_place_distance_time",
})


def _looks_like_valid_location(text: str) -> bool:
    """Heuristic: return True when text plausibly contains a real location / place name.

    Used to detect garbled ASR answers to location frames (e.g. "我住在等你等")
    vs genuine place answers ("我住在北京", "Auckland").  False-negative rate is
    acceptable — better to ask once more than to silently advance on garbage input.
    """
    t = (text or "").strip()
    if not t:
        return False
    # Latin script ≥ 3 consecutive chars → likely an English/foreign city name
    if re.search(r'[A-Za-z]{3,}', t):
        return True
    # Strip common location-answer structural prefixes to isolate the place token
    for _pfx in ("我现在住在", "我住在", "我在", "我来自", "住在", "在"):
        if t.startswith(_pfx):
            t = t[len(_pfx):].strip()
            break
    if not t:
        return False
    # Characters that commonly appear in Chinese city / region / country names.
    # Deliberately narrow to reduce false-positives from functional words.
    _LOC_CHARS = frozenset(
        "市省州区县岛镇港京沪津渝穗榕蓉汉庆海山川江宁福厦昆贵哈沈长春银拉兰顿威"
    )
    if any(c in t for c in _LOC_CHARS):
        return True
    # Valid non-location answers (deflection / uncertainty)
    if any(x in t for x in ("不知道", "不确定", "没想好", "这里", "那里", "这边", "那边")):
        return True
    # Place-quality descriptions ("安静风景很好看") count as meaningful place content.
    if _is_place_description(t):
        return True
    return False


# ── Open-world residence-location acceptance (Fix 2) ─────────────────────────────────────────────
# Frame IDs where the partner is directly asking where the learner lives/is from.  A bare
# place-name answer (no "我住在..." structure) is only accepted as a residence answer while
# one of these frames is active — elsewhere a bare "达尼丁" would be ambiguous.
_RESIDENCE_QUESTION_FRAME_IDS: frozenset = frozenset({
    "f_from_where", "f_live_where", "frame.location.live_question",
})

_RESIDENCE_ANSWER_PREFIXES: tuple = (
    "我现在住在", "我现在在", "我住在", "我家在", "我来自", "我在", "住在", "现在住在", "现在在", "在",
)


def _extract_open_world_location(text: str, frame_is_residence: bool = False) -> Optional[str]:
    """Open-world residence-location extraction (Fix 2).

    The learner is the source of truth for their own residence: ANY plausible
    location-bearing answer is accepted and returned verbatim (minus the
    structural prefix) — no known-city lookup, no `_LOC_CHARS` membership check,
    no Latin-script requirement, no travel-destination alias table.

    Returns the extracted location string, or None when there is no usable
    location content: the text is empty, is a recognised confusion/recovery
    signal ("嗯……", "再说一遍", "不知道"), or reduces to nothing once known
    ASR-junk fragments ("等你等") are stripped out.

    `frame_is_residence` gates the BARE-answer case (no "我住在..." structure) —
    a bare place name like "达尼丁" is only accepted while the active frame is
    genuinely asking for the learner's residence; a structured answer
    ("我住在达尼丁") is accepted unconditionally since the sentence itself makes
    the intent unambiguous.
    """
    t = (text or "").strip()
    if not t:
        return None
    if _is_confusion_signal(t):
        return None
    for pfx in _RESIDENCE_ANSWER_PREFIXES:
        if t.startswith(pfx):
            tail = t[len(pfx):].strip("。！， ,.?？")
            tail = _repair_asr_junk_text(tail).strip()
            if tail:
                return tail
            return None  # residence structure present but no usable token followed
    if frame_is_residence:
        bare = _repair_asr_junk_text(t).strip()
        return bare or None
    return None


# ── Participation-success structural matchers ─────────────────────────────────
# For certain frames, intent/structure confidence is sufficient to advance the
# conversation even when the entity cannot be extracted.  These matchers check
# the STRUCTURAL pattern of the answer, not the entity value.
# Rule: entity confidence may remain low; unresolved entity must not block progress.

def _looks_like_location_answer_structure(text: str) -> bool:
    """Return True when text has a location-answer structural pattern —
    我现在住在X / 我住在X / 现在住在X / 住在X — regardless of whether the
    extracted entity is recognisable (e.g. '我现在住在等你等' matches).
    Intent confidence can be high even when entity confidence is low."""
    t = (text or "").strip()
    _LOC_ANS_PREFIXES = ("我现在住在", "我住在", "现在住在", "住在")
    return any(t.startswith(pfx) or pfx in t for pfx in _LOC_ANS_PREFIXES)


def _looks_like_name_answer_structure(text: str) -> bool:
    """Return True when text has a name-answer structural pattern —
    我叫X / 我是X (where X is not a verb phrase start) — regardless of
    whether the name entity is a known or extractable Chinese/Western name."""
    t = (text or "").strip()
    if t.startswith("我叫") and len(t) > 2:
        return True
    if t.startswith("我是") and len(t) > 2:
        # Exclude verb-phrase continuations: 我是说/想/在/做/问/对/不/很/太
        _verb_starts = ("说", "想", "在", "做", "因", "问", "对", "不", "真", "很", "太", "从", "去")
        return not any(t[2:].startswith(c) for c in _verb_starts)
    return False


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
            "嗯，我慢一点。刚才说的是我家那边的事情，不用担心，慢慢来。",
            "Let me slow down — I was talking about things back home. No rush.",
        ),
        (
            "哦，我换个说法：不着急，我们一步一步来。你先告诉我，你哪一句没听懂？",
            "Let me rephrase — no rush. Which sentence was unclear?",
        ),
        (
            "好，没关系。我们换个简单一点的话题，你来问我。",
            "That's okay — let's try something simpler. You can ask me.",
        ),
    ]
    idx = sum(ord(c) for c in (seed + prev_zh + t)) % len(pool)
    return pool[idx]


# Meaning-recovery lookup table: (keywords_in_frame_text) → (simpler_zh, en_gloss, example_answer)
# Matched longest / most-specific first. Each entry covers one common frame pattern.
_MEANING_RECOVERY_TABLE: list = [
    # Distance
    (("远", "多远"),     "多远？",           "How far is it?",              "大概两个小时。"),
    (("远",),            "远不远？",          "Is it far?",                  "不太远。"),
    # Location / where
    (("住", "哪里"),     "你住哪儿？",        "Where do you live?",          "我住在上海。"),
    (("住", "在哪"),     "你住哪儿？",        "Where do you live?",          "我在北京。"),
    (("在哪里",),        "你在哪里？",        "Where are you?",              "我在中国。"),
    # Food
    (("好吃", "什么"),   "那儿有什么好吃的？","What good food is there?",    "有很多好吃的！"),
    (("有什么", "吃"),   "好吃的有什么？",    "What's good to eat?",         "很多！"),
    # Work
    (("做什么", "工作"), "你做什么工作？",    "What's your job?",            "我是老师。"),
    (("工作", "怎么样"), "工作好不好？",      "How's your work?",            "还不错！"),
    (("工作",),          "你做什么工作？",    "What work do you do?",        "我在公司上班。"),
    # Travel
    (("想去", "哪"),     "你想去哪里？",      "Where do you want to go?",    "我想去日本！"),
    (("去过", "哪"),     "你去过哪里？",      "Where have you been?",        "我去过北京。"),
    # Special / features
    (("特别", "什么"),   "那有什么特别的？",  "What's special there?",       "风景很好看。"),
    (("特色",),          "有什么特色？",      "What's unique about it?",     "当地食物很有名。"),
    # Duration
    (("多久",),          "要多长时间？",      "How long does it take?",      "大概两个小时。"),
    (("多大",),          "多大了？",          "How old?",                    "快三十了。"),
    # Family
    (("家人",),          "家人怎么样？",      "How's your family?",          "都还好。"),
    (("孩子",),          "你有孩子吗？",      "Do you have children?",       "有一个孩子。"),
    # Feelings / preference
    (("喜欢", "为什么"), "你为什么喜欢？",    "Why do you like it?",         "因为很方便。"),
    (("喜欢",),          "你喜欢吗？",        "Do you like it?",             "很喜欢！"),
]


def _meaning_recovery_reply(prev_frame_text: str) -> Optional[tuple]:
    """Return (zh, en) counter_reply for 什么意思啊 / meaning requests.

    Instead of repeating the same Chinese, surfaces:
      • A short English gloss of the question
      • A simpler Chinese paraphrase
      • One example learner answer

    Regression: session_1782907566569 turn 8 must not repeat 离那儿远吗.
    """
    ft = (prev_frame_text or "").strip().rstrip("？?").strip()
    if not ft:
        return None
    # Strip existing clarification wrappers so we never re-wrap the wrapper.
    for pfx in ("我是问：", "我是在问：", "我刚刚问的是：", "我的意思是："):
        if ft.startswith(pfx):
            ft = ft[len(pfx):].strip().rstrip("？?").strip()
            break
    # Strip leading echo acknowledgement (e.g. "哦，美玲！") before the question.
    ft = re.sub(r'^哦，[^！]{1,25}！\s*', '', ft).strip().rstrip("？?").strip()
    if not ft:
        return None
    # Match keywords longest-first; sort by tuple length descending on each call
    # (table is already ordered specific → general within each semantic group).
    for keywords, simpler_zh, en_gloss, example in _MEANING_RECOVERY_TABLE:
        if all(kw in ft for kw in keywords):
            zh = f"\uff08{en_gloss}\uff09\u7b80\u5355\u8bf4\uff1a\u300c{simpler_zh}\u300d \u6bd4\u5982\u4f60\u53ef\u4ee5\u8bf4\uff1a\u300c{example}\u300d"
            en = f"({en_gloss}) Simpler: \u300c{simpler_zh}\u300d \u2014 e.g. \u300c{example}\u300d"
            return (zh, en)
    # Generic fallback: at least give the English translation of the frame text.
    zh = (
        "\u610f\u601d\u662f\uff1a\u300c" + ft + "\uff1f\u300d "
        "\u6bd4\u5982\u4f60\u53ef\u4ee5\u8bf4\uff1a"
        "\u300c\u4e0d\u77e5\u9053\u300d\u3001\u300c\u8fd8\u6ca1\u6709\u300d\u3001\u300c\u6709\u4e00\u70b9\u300d\u3002"
    )
    en = "Meaning: \u300c" + ft + "?\u300d \u2014 e.g. \u300c\u4e0d\u77e5\u9053\u300d (don't know), \u300c\u8fd8\u6ca1\u6709\u300d (not yet)."
    return (zh, en)


def _clarify_app_question(prev_frame_text: str) -> Optional[tuple]:
    """Return a (zh, en) counter_reply that rephrases the last partner-frame question.
    Uses keyword pattern matching on prev_frame_text to produce contextual semantic
    restatements rather than a generic "换个说法" prefix.
    Lightweight: no embeddings, deterministic lookup table."""
    ft = (prev_frame_text or "").strip().rstrip("？?").strip()
    if not ft:
        return None
    # Guard: strip existing clarification wrapper so we never double-wrap.
    # last_partner_frame_text may already contain "我是问：..." if a previous turn
    # was itself a clarification — strip the prefix before re-wrapping.
    for _clar_pfx in ("我是问：", "我是在问：", "我刚刚问的是：", "我的意思是："):
        if ft.startswith(_clar_pfx):
            ft = ft[len(_clar_pfx):].strip().rstrip("？?").strip()
            break
    # Guard: strip leading echo acknowledgement "哦，X！" that may have been prepended
    # as a reaction prefix (e.g. "哦，等你等！离那儿远吗") before the question arrived.
    # This prevents the echo from being embedded inside the clarification wrapper.
    ft = re.sub(r'^哦，[^！]{1,25}！\s*', '', ft).strip().rstrip("？?").strip()
    if not ft:
        return None
    # Contextual restatements — matched longest-first so specific patterns win.
    # Each entry: (keywords_that_must_all_appear_in_ft, zh_restatement, en_restatement)
    _patterns: list = [
        # Location / residence
        (("住", "哪里"),        "我是问：你现在住的地方在哪里？",             "I'm asking: where do you live right now?"),
        (("住", "在哪"),        "我是问：你现在住的地方在哪里？",             "I'm asking: where do you live right now?"),
        (("住哪",),             "我是问：你住在哪个地方？",                   "I'm asking: what place do you live in?"),
        (("在哪里", "住"),      "我是问：你住在哪里？",                       "I'm asking: where do you live?"),
        # Why like / what's special about a place
        (("喜欢", "这里"),      "我刚刚问的是：你觉得这里有什么好？",         "I was asking: what do you like about here?"),
        (("喜欢", "地方"),      "我刚刚问的是：你为什么喜欢这个地方？",       "I was asking: why do you like this place?"),
        (("特别",),             "我的意思是：这个地方有什么特别的地方？",     "I mean: what's special about this place?"),
        (("特色",),             "我的意思是：这里有什么特色？",               "I mean: what's unique about here?"),
        # Food
        (("好吃", "什么"),      "我是问：你在那里最喜欢吃什么？",             "I'm asking: what do you like eating there?"),
        (("有什么", "吃"),      "我是问：这里有什么好吃的？",                 "I'm asking: what's good to eat here?"),
        # Work
        (("工作", "怎么样"),    "我的意思是：你觉得这份工作怎么样？",         "I mean: how do you find your work?"),
        (("做什么", "工作"),    "我是问：你做什么工作？",                     "I'm asking: what kind of work do you do?"),
        (("工作",),             "我是问：你的工作是什么？",                   "I'm asking: what is your work?"),
        # Travel / where want to go
        (("想去", "哪"),        "我是问：你最想去哪里旅游？",                 "I'm asking: where would you most like to travel?"),
        (("去", "哪里"),        "我是问：你最想去哪个地方？",                 "I'm asking: which place would you most like to go?"),
        # Family health
        (("身体", "怎么样"),    "我是问：你家人现在身体还好吗？",             "I'm asking: is your family doing okay health-wise?"),
        (("家人",),             "我是问：你的家人情况怎么样？",               "I'm asking: how are your family members doing?"),
        # Children
        (("孩子",),             "我是问：你有孩子吗？",                       "I'm asking: do you have children?"),
        # Hobby
        (("爱好",),             "我是问：你平时有什么爱好？",                 "I'm asking: what hobbies do you have?"),
        (("喜欢做",),           "我是问：你平时喜欢做什么？",                 "I'm asking: what do you enjoy doing?"),
    ]
    for keywords, zh_restate, en_restate in _patterns:
        if all(kw in ft for kw in keywords):
            return (zh_restate, en_restate)
    # Fallback: reframe with "我是问：" prefix — more natural than "换个说法".
    zh = f"我是问：{ft}？"
    en  = f"I was asking: {ft}?"
    return (zh, en)


# Brief, factual location descriptions for common cities — used for "X在哪儿" follow-ups.
_CITY_LOCATION_BRIEF: dict = {
    "北京": "北京在中国北边，是首都，很大。",
    "上海": "上海在中国东边，是个很大的港口城市。",
    "成都": "成都在中国西南，四川省的省会，节奏比较慢。",
    "西安": "西安在中国西北，是个历史很悠久的古都。",
    "重庆": "重庆在中国西南，是个山城，山路多，火锅很出名。",
    "南京": "南京在中国东边，江苏省的省会，历史也挺长的。",
    "杭州": "杭州在中国东边，浙江省的省会，西湖很有名。",
    "苏州": "苏州在中国东边，离上海不远，园林很有名。",
    "武汉": "武汉在中国中部，是个大城市，夏天很热。",
    "广州": "广州在中国南边，广东省的省会，饮食很有特色。",
    "深圳": "深圳在中国南边，广东省，是个很现代的城市。",
}


def _persona_limitation_reply(topic_hint: str = "") -> str:
    """In-character uncertainty for questions the persona cannot specifically answer.
    Uses natural uncertainty phrasing; reserves '电脑角色' for genuinely off-domain / meta questions."""
    # Rotate through natural in-character phrases rather than always exposing the meta disclaimer.
    _natural_pool = [
        "这个我不太清楚。",
        "这个我不太确定，你可以问问别人。",
        "我没问过具体的，不太清楚。",
        "我真的不太了解这个，不好说。",
    ]
    if topic_hint:
        return f"这个我不太清楚，不过我们可以聊聊{topic_hint}。"
    import hashlib as _hlib
    import time as _time
    _slot = int(_time.time() // 600) % len(_natural_pool)
    return _natural_pool[_slot]


def _soft_persona_fallback(t: str, persona: Optional[dict]) -> Optional[str]:
    """Try a natural soft deflection before the hard '电脑角色' phrase.

    Returns a conversational non-answer when the question is harmless but unsupported,
    so the learner hears a persona voice rather than a system disclaimer.
    Returns None if no soft fallback applies; caller then uses _persona_limitation_reply.
    """
    if not t:
        return None
    profile = (persona or {}).get("profile") or {}
    name    = (profile.get("name") or profile.get("display_name") or "").strip()

    # Name/meaning questions: "美玲有什么意思" / "你的名字是什么意思" / "名字怎么来的"
    if any(kw in t for kw in ("意思", "名字怎么", "名字是什么意思", "名字来的", "名字从哪", "名字好听", "取名")):
        if name:
            return f"这个我不太确定，应该是家里人觉得好听，就叫{name}了。"
        return "这个我不太确定，名字是家里人取的，具体意思不太清楚。"

    # Duration/routine questions that are harmless but undefined
    if any(kw in t for kw in ("多长时间了", "多久了", "平时怎么", "一般怎么", "每天怎么")):
        return "这个我不太确定，看情况吧。"

    # Generic "what do you think / how do you feel" directed at persona facts
    if any(kw in t for kw in ("你觉得怎么样", "你的感觉", "你觉得好吗")):
        return "还行，挺好的。"

    return None


def _context_city_from_text(text: str) -> Optional[str]:
    """Extract the first known city name from a text string (used for context-aware replies)."""
    for _c in _CITY_LOCATION_BRIEF:
        if _c in (text or ""):
            return _c
    return None


# Matches a city token immediately followed by a feature/food question marker anywhere in
# the utterance (non-anchored).  Captures only the Chinese character sequence so we can
# verify membership in _CITY_LOCATION_BRIEF separately.
_CITY_BEFORE_QUESTION_MARKER_RE = re.compile(
    r"([\u4e00-\u9fff]{2,4})"
    r"(?:有什么特别的?(?:之处)?|有什么特色|有什么好玩|有什么有意思|"
    r"有什么好吃的?|有什么吃的|好吃的|特别之处)"
)


def _place_from_question_context(t: str, recent_replies: Optional[list] = None) -> Optional[str]:
    """Named place in the question, or deictic '那里/这儿' resolved from recent persona replies.

    Priority:
    1. A city that immediately precedes a feature/food question marker — this is the
       grammatical subject of the question (e.g. '成都有什么特别' in
       '我不喜欢上海，成都有什么特别？' → '成都', not '上海').
    2. The first known city anywhere in the text.
    3. Deictic '那里/这儿/那边' resolved from recent persona replies.
    """
    m = _CITY_BEFORE_QUESTION_MARKER_RE.search(t or "")
    if m:
        candidate = m.group(1)
        if candidate in _CITY_LOCATION_BRIEF:
            return candidate
    place = _context_city_from_text(t)
    if place:
        return place
    if any(d in (t or "") for d in _PLACE_DEIXIS_MARKERS):
        for reply in reversed(recent_replies or []):
            p = _context_city_from_text(reply)
            if p:
                return p
    return None


# Broad plausibility set for the contextual place-repair guard below — a superset of
# _CITY_LOCATION_BRIEF (which only has feature/food answer pools) so genuinely named
# places (e.g. "甘肃", "新西兰") are never mistaken for ASR mis-recognition and repaired.
_KNOWN_PLACE_NAMES: frozenset = (
    frozenset(_TRAVEL_SUBREGIONS) | frozenset(_TRAVEL_COUNTRIES) | frozenset(_CITY_LOCATION_BRIEF.keys())
)

# Matches a SHORT, self-contained "<token><feature/food marker>" question with nothing
# else around it — e.g. "需要有什么特别的" / "背景有什么特别的". Deliberately narrow
# (fullmatch-style, anchored at both ends) so longer or unrelated sentences containing
# the same marker substring (e.g. "需要有什么特别的条件") never match.
_PLACE_QUESTION_HEAD_RE = re.compile(
    r"^([\u4e00-\u9fff]{1,4})"
    r"(有什么特别的|有什么特别之处|有什么特别|特别之处|有什么特色|有什么好玩|有什么有意思|"
    r"有什么好吃的|有什么好吃|有什么吃的|好吃的|特别的)"
    r"[吗呢啊？?！!]*$"
)


def _repair_contextual_place_question(
    t: str, cs: Optional[dict], prev_reply: str = "",
) -> tuple:
    """Narrow contextual repair for a malformed place token in a short place-feature/
    food question (e.g. ASR mis-recognising "西安" as "需要").

    Returns a (repaired_text, clarification_zh) pair:
      - (None, None)            → no repair applies; caller must use the ORIGINAL text.
      - (repaired_text, None)   → exactly one unambiguous recent city found; the
                                   invalid place token was swapped for ROUTING purposes
                                   only (the raw learner transcript is never touched).
      - (None, clarification_zh)→ two or more recent cities are plausible; caller
                                   should ask rather than silently invent a destination.

    Guardrails (do not weaken without re-reading the regression tests):
      - Only fires on a short, fully-matched "<token><marker>" utterance — never on
        longer sentences that merely contain the marker substring.
      - Never fires when the token is already a recognised/plausible place, or a
        deixis marker (那里/那边/…) — those are resolved elsewhere.
      - Only consults the immediately tracked place subject (cs.last_place_subject)
        and the SINGLE immediately preceding app reply — never older history.
    """
    s = (t or "").strip()
    m = _PLACE_QUESTION_HEAD_RE.match(s)
    if not m:
        return (None, None)
    token, marker = m.group(1), m.group(2)
    if token in _KNOWN_PLACE_NAMES or token in _PLACE_DEIXIS_MARKERS:
        return (None, None)  # already a real place (or deixis) — nothing to repair

    candidates: list = []
    _lps = ((cs or {}).get("last_place_subject") or "").strip() if isinstance(cs, dict) else ""
    if _lps and _lps in _KNOWN_PLACE_NAMES:
        candidates.append(_lps)
    for _c in sorted(_KNOWN_PLACE_NAMES):
        if _c in (prev_reply or "") and _c not in candidates:
            candidates.append(_c)

    if not candidates:
        return (None, None)  # no recent city — do not invent a destination
    if len(candidates) > 1:
        return (None, f"你是问{candidates[0]}{marker}吗？")

    city = candidates[0]
    repaired = s[: m.start(1)] + city + s[m.end(1):]
    return (repaired, None)


def _cooking_persona_answer(persona: Optional[dict], seed: str = "") -> Optional[str]:
    """Return a cooking/dish answer from persona food facts or the phrase bank."""
    facts = (persona or {}).get("discoverable_facts") or {}
    voice_lines = (persona or {}).get("voice_lines") or {}
    food_fact = (facts.get("food") or "").strip()
    if food_fact:
        return food_fact
    food_vl = (voice_lines.get("food") or "").strip()
    if food_vl:
        return food_vl
    if not _persona_cooking_phrases:
        return None
    zh = _stable_pick([p[0] for p in _persona_cooking_phrases], seed or "cooking") \
         or _persona_cooking_phrases[0][0]
    return zh


def _place_followup_reply(t: str, persona: Optional[dict],
                           context_reply: str = "") -> Optional[tuple]:
    """
    Handle short distance/location follow-up questions that arise after a city mention:
      - "远不远啊" / "远吗" → answer from persona's perspective (it's their hometown → not far)
      - "在哪儿" / "在哪里" / "在哪" → brief location fact for the city in context

    context_reply: the persona's immediately preceding counter_reply, used to detect
    which city was just mentioned.
    """
    if not any(m in t for m in ("远不远", "远吗", "有多远", "在哪儿", "在哪里", "在哪", "哪里啊", "哪儿啊")):
        return None
    profile   = (persona or {}).get("profile") or {}
    city      = (profile.get("city") or "").strip()
    hometown  = (profile.get("hometown") or "").strip()
    _own_city = city or hometown

    # Detect the city being asked about: prefer explicit city name in question,
    # then look in recent context_reply for a city mention.
    _asked_city = _context_city_from_text(t) or _context_city_from_text(context_reply)

    # "在哪儿" / "在哪里" — location question
    if any(m in t for m in ("在哪儿", "在哪里", "在哪", "哪里啊", "哪儿啊")):
        loc_desc = _CITY_LOCATION_BRIEF.get(_asked_city or "") or _CITY_LOCATION_BRIEF.get(_own_city or "")
        # Persona-directed location question: "你住在哪里？" / "你老家在哪儿？" / "你在哪里工作？"
        # Must answer personally first ("我住在X") then optionally add city description.
        # Only personalise when no specific city is named in the question itself.
        _PERSONA_LOC_MARKERS = ("你住", "你老家", "你的老家", "你家乡", "你的家乡", "你现在在", "你在哪里工作", "你在哪工作", "你工作在哪")
        _is_persona_loc_q = any(m in t for m in _PERSONA_LOC_MARKERS) and not _asked_city
        if _is_persona_loc_q:
            # Determine which kind of location is being asked about.
            _is_hometown_q = any(m in t for m in ("老家", "家乡", "是哪里人", "哪里人"))
            _is_work_loc_q = any(m in t for m in ("工作在哪", "在哪里工作", "在哪工作", "工作的地方"))
            if _is_hometown_q:
                _personal_loc = hometown or city
                _personal_prefix = f"我老家在{_personal_loc}。" if _personal_loc else ""
            elif _is_work_loc_q:
                _personal_loc = city or hometown
                _personal_prefix = f"我在{_personal_loc}工作。" if _personal_loc else ""
            else:
                _personal_loc = city or hometown
                _personal_prefix = f"我住在{_personal_loc}。" if _personal_loc else ""
            if loc_desc and _personal_prefix:
                return (f"{_personal_prefix}{loc_desc}", "")
            if _personal_prefix:
                return (_personal_prefix, "")
        if loc_desc:
            return (loc_desc, "")
        if _asked_city:
            return (f"{_asked_city}在中国，是个很有特色的城市。", "")
        return None  # Let the caller handle with limitation fallback

    # "远不远" / "远吗" — distance question
    if any(m in t for m in ("远不远", "远吗", "有多远")):
        # If asking about persona's own city/hometown → persona has direct knowledge
        if _asked_city and _own_city and _asked_city == _own_city:
            return (f"对我来说一点都不远，{_asked_city}就是我家！", "")
        if _asked_city and _own_city:
            # Asking about a city the persona is from but it's different from current city
            dp = (persona or {}).get("distance_profile") or {}
            dp_ref = (dp.get("reference") or "").strip()
            if dp_ref and dp_ref == _asked_city:
                zh = (dp.get("zh") or "").strip()
                if zh:
                    return (zh, dp.get("en") or "")
            # Fallback: check the city location pool for general knowledge
            loc_desc = _CITY_LOCATION_BRIEF.get(_asked_city)
            if loc_desc:
                return (f"我不太确定距离，不过{_asked_city}在中国是挺有名的城市。", "")
        # Generic — persona can't know the learner's distance
        if _own_city:
            return (f"要看你从哪里出发，不过{_own_city}还挺好找的。", "")
        return None
    return None


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


# ── Reverse fact map ──────────────────────────────────────────────────────────
# Distinct persona answers per direct-question intent, derived from persona data
# (no hardcoded persona strings — extensible across personas).  Restores clear
# separation so hometown/work questions don't collapse into one generic answer.

def _detect_reverse_fact_intent(text: str) -> Optional[str]:
    """Classify a direct persona question into a reverse-fact intent, or None."""
    t = _strip_leading_fillers((text or "").strip()).replace("您", "你")
    if not t:
        return None
    if any(p in t for p in ("结婚", "对象", "成家", "单身", "男朋友", "女朋友")):
        return "marriage"
    if any(p in t for p in ("多大", "几岁", "年龄", "今年多大")):
        return "age"
    if any(p in t for p in ("好吃", "美食")) or ("有什么" in t and "吃" in t):
        return "hometown_food"
    if any(p in t for p in ("特别", "特色", "有名")):
        return "hometown_special"
    if any(p in t for p in ("工作多久", "做多久", "做多长时间", "工作多长时间",
                             "工作多少年", "这个工作多久", "这份工作多久")):
        return "work_duration"
    if any(p in t for p in ("为什么当", "为什么做", "为什么选", "为什么想当", "怎么会当")):
        return "work_reason"
    if any(p in t for p in ("做什么工作", "什么工作", "类型的工作", "什么样的工作",
                             "你的工作", "你是做什么")):
        return "job"
    if any(p in t for p in ("家乡", "老家", "哪里人", "从哪里来")):
        # location vs identity: "家乡在哪" asks where → hometown_where
        return "hometown_where"
    return None


def _reverse_fact_answer(intent: str, persona: Optional[dict]) -> str:
    """Return a distinct persona answer for a reverse-fact intent, derived from
    persona profile / voice_lines / discoverable_facts.  Returns "" when unknown."""
    profile = (persona or {}).get("profile") or {}
    facts   = (persona or {}).get("discoverable_facts") or {}
    vl      = (persona or {}).get("voice_lines") or {}
    ht      = (profile.get("hometown") or "").strip()
    city    = (profile.get("city") or "").strip()
    occ     = (profile.get("occupation") or "").strip()
    age     = profile.get("age")

    if intent == "hometown_where":
        if ht:
            return f"我老家在{ht}。"
        return (vl.get("place") or "").strip()
    if intent == "hometown_location":
        brief = _CITY_LOCATION_BRIEF.get(ht) or _CITY_LOCATION_BRIEF.get(city)
        if brief:
            return brief
        return f"{ht}在中国。" if ht else ""
    if intent == "hometown_special":
        return (facts.get("place") or "").strip()
    if intent == "hometown_food":
        return (facts.get("food") or "").strip()
    if intent == "job":
        return (vl.get("work") or facts.get("work") or (f"我是{occ}。" if occ else "")).strip()
    if intent == "work_duration":
        _work_fact = (facts.get("work") or "").strip()
        if _work_fact:
            _markers = ("年", "久", "教了", "做了", "开始", "以来", "毕业", "一直")
            _clauses = [c.strip() for c in re.split(r"[，。！？,]", _work_fact) if c.strip()]
            _dur = next((c for c in _clauses if any(m in c for m in _markers)), "")
            if _dur:
                return _dur + ("。" if not _dur.endswith("。") else "")
        return "已经做了几年了。"
    if intent == "work_reason":
        return (facts.get("work_origin") or "").strip()
    if intent == "age":
        if age and isinstance(age, (int, float)):
            return f"我今年{int(age)}岁。"
        return ""
    if intent == "marriage":
        _m = (facts.get("marriage") or "").strip()
        if _m:
            return _m
        return _persona_deflect("marriage", "")
    return ""


def _reverse_fact_answer_en(intent: str, persona: Optional[dict]) -> str:
    """English for dynamically-constructed reverse-fact answers.

    Invariant (RC-EN): the English returned here must plausibly correspond to
    ANY Chinese sentence the caller might pair with this intent.  When the
    mapping is coarse — i.e. the same intent is triggered by questions about
    different subjects (e.g. "age" fires for both persona-own-age AND
    parent-age questions) — return "" so the client gloss routine translates
    the exact final Chinese reply instead.

    Narrowed branches vs first introduction (commit 0177994):
      • hometown_special  – city-feature pool strings are not individually
        translated; facts_en["place"] is the persona's *current-city* blurb
        and is unrelated to the feature city asked about → always "".
      • age               – "你爸妈多大" also maps to intent "age"; the
        persona's own-age answer is always resolved by the mirror bank before
        this function is reached, so returning the persona's age here only
        produces wrong English for parent-age replies → always "".
      • work_duration     – only return an English clause when the available
        English source explicitly contains duration information; the job-
        description fallback ("I teach at …") must not stand in for a duration
        answer like "做这行十年了" → scan all work-English sources for a
        duration clause; return "" when none is found.
    """
    profile  = (persona or {}).get("profile") or {}
    facts_en = (persona or {}).get("discoverable_facts_en") or {}
    vl_en    = (persona or {}).get("voice_lines_en") or {}
    ht       = (profile.get("hometown") or "").strip()

    if intent == "hometown_where":
        return (vl_en.get("place") or facts_en.get("place_from")
                or (f"My hometown is {ht}." if ht else "")).strip()
    if intent == "hometown_location":
        return (facts_en.get("place") or vl_en.get("place") or "").strip()
    if intent == "hometown_special":
        # City-feature pool strings have no individual English translations.
        # facts_en["place"] is the persona's current-city description and may
        # refer to a different city than the one asked about.  Return "" so the
        # gloss path translates the exact final Chinese reply.
        return ""
    if intent == "hometown_food":
        return (facts_en.get("food") or "").strip()
    if intent == "job":
        return (vl_en.get("work") or facts_en.get("work") or "").strip()
    if intent == "work_duration":
        # Only return English when the source explicitly contains duration
        # information (e.g. "eight years", "for ten years").  A bare job
        # description must not stand in for a duration clause.
        _dur_markers_en = (
            "year", "years", " for ", "since", "decade",
            "been doing", "taught for", "worked for", "doing this for",
        )
        for _src in (
            facts_en.get("work"),
            vl_en.get("work"),
            facts_en.get("work_company"),
        ):
            _en_src = (_src or "").strip()
            if not _en_src:
                continue
            _clauses_en = [
                c.strip()
                for c in re.split(r"[,\.!?\u2014]", _en_src)
                if c.strip()
            ]
            _dur_en = next(
                (c for c in _clauses_en if any(m in c.lower() for m in _dur_markers_en)),
                "",
            )
            if _dur_en:
                return _dur_en.rstrip(".,\u2014") + "."
        return ""
    if intent == "work_reason":
        return (facts_en.get("work_origin") or "").strip()
    if intent == "age":
        # "年龄" / "多大" / "几岁" questions also fire for parent-age ("你爸妈多大"),
        # so a coarse f"I'm {age} years old." would be incorrect for those replies.
        # The persona's own-age question ("你几岁") is always answered via the mirror
        # bank before reaching this function.  Return "" to delegate to gloss.
        return ""
    if intent == "marriage":
        return (facts_en.get("marriage") or "").strip()
    return ""


def _persona_answer_en(persona: Optional[dict], zh: str,
                       intent: Optional[str] = None) -> str:
    """Single translation path for Chinese persona answers.

    Resolution order (same precedence used by _direct_persona_answer):
      1. persona voice_line → _voice_line_en_for_zh
      2. predefined deflection phrase → _en_for_counter_reply (handles 我呢， wrapper)
      3. dynamic reverse-fact answer (given `intent`) → _reverse_fact_answer_en

    Returns "" only when no English source exists at all.
    """
    d = (zh or "").strip()
    if not d:
        return ""
    inner = d[len("我呢，"):].strip() if d.startswith("我呢，") else d
    # 1) deflection phrase (fixed) — mirrors the direct-answer path precedence.
    en = _en_for_counter_reply(d, inner)
    if en:
        return en
    # 2) persona voice line (match full string or inner phrase).
    en = _voice_line_en_for_zh(persona, d) or _voice_line_en_for_zh(persona, inner)
    if en:
        return en
    # 3) dynamic reverse-fact answer, keyed by intent.
    if intent:
        en = _reverse_fact_answer_en(intent, persona)
        if en:
            return en
    # 4) discoverable_facts — dynamic persona answers (e.g. cooking from food fact).
    _facts = (persona or {}).get("discoverable_facts") or {}
    _facts_en = (persona or {}).get("discoverable_facts_en") or {}
    for _fk, _fv in _facts.items():
        _fv_s = (_fv or "").strip()
        if _fv_s and (_fv_s == d or _fv_s == inner or _fv_s in d):
            _en_f = (_facts_en.get(_fk) or "").strip()
            if _en_f:
                return _en_f
    # 5) phrase-bank replies loaded into _persona_deflect_en_map (cooking fallback, etc.).
    en = _persona_deflect_en(d) or _persona_deflect_en(inner)
    if en:
        return en
    return ""


def _dedupe_persona_answer(candidate: str, recent_replies: Optional[list],
                            text: str, persona: Optional[dict]) -> str:
    """Anti-repetition guard: if `candidate` was already given recently, return
    a distinct answer for the SAME intent rather than falling back cross-intent.

    Priority order (RC-A invariant):
      1. Re-pick from the same-intent answer pool (feature or food pool for the
         asked place) — guarantees the reply remains topically correct.
      2. Only if the same-intent pool is exhausted, use a topically appropriate
         clarification phrase ("我刚说过了，你想了解其他的吗？") rather than an
         unrelated fact from _reverse_fact_answer.
      3. Never use _reverse_fact_answer(intent) as the first alternative —
         intents like "hometown_special" resolve to facts["place"] which can be
         for a different city than the one actually asked about.
    """
    cand = (candidate or "").strip()
    # Normalise recent for both bare and prefixed comparisons (matches RC-C).
    bare_cand = _strip_discourse_prefix(cand)
    recent_bare: list = [_strip_discourse_prefix(r) for r in (recent_replies or []) if r]
    if not cand or (bare_cand not in recent_bare and cand not in (recent_replies or [])):
        return candidate

    _recent_set: set = set(recent_replies or []) | set(recent_bare)

    # --- Step 1: try re-picking from the SAME intent pool ----
    # Place-feature pool repick
    if _is_place_feature_question(text):
        _resolved = _place_from_question_context(text, list(recent_replies or []))
        _FEAT_POOL_INLINE: dict = {
            "北京": ["北京很大，历史文化非常丰富，长城和故宫都在这里。",
                     "北京机会很多，是个很有活力的城市。",
                     "北京有很多历史古迹，还有很多好吃的小吃。"],
            "上海": ["上海很国际化，外滩的夜景特别漂亮。",
                     "上海很繁华，购物和美食选择都很多。",
                     "上海节奏快，但也很有魅力，老弄堂和新高楼都很有特色。"],
            "成都": ["成都的节奏比较慢，大家都很悠闲，火锅也是一绝！",
                     "成都的美食特别有名，火锅、串串都很好吃。",
                     "成都生活很舒服，茶馆文化很有特色，大家喜欢坐在茶馆聊天。"],
            "西安": ["西安历史文化太丰富了，兵马俑、大雁塔都在那里。",
                     "西安的小吃很有名，凉皮、肉夹馍都很好吃。",
                     "西安是古都，到处都有历史遗迹，很有文化感。"],
            "重庆": ["重庆是山城，到处都是坡路，风景很特别。",
                     "重庆的火锅是全国最有名的，很辣很好吃！",
                     "重庆的夜景非常漂亮，尤其是洪崖洞那一带。"],
            "南京": ["南京历史很悠久，有很多历史遗迹。",
                     "南京的鸭血粉丝汤很有名，小吃也很多。"],
            "杭州": ["杭州的西湖非常漂亮，是个很出名的景点。",
                     "杭州自然风景很美，还有很多茶文化。"],
            "苏州": ["苏州的园林很有名，特别有诗意。",
                     "苏州的古镇和水乡很有特色，景色很美。"],
        }
        _pool = _FEAT_POOL_INLINE.get(_resolved or "") if _resolved else None
        if _pool:
            alt = _pick_not_in(_pool, f"dedup|feat|{_resolved}|{text}", _recent_set)
            if alt and _strip_discourse_prefix(alt) not in recent_bare:
                return alt

    # Place-food pool repick
    if _is_place_food_question(text):
        _resolved = _place_from_question_context(text, list(recent_replies or []))
        _FOOD_POOL_INLINE: dict = {
            "西安": ["西安的小吃非常有名！凉皮和肉夹馍是我最喜欢的，特别好吃。",
                     "西安有很多特色小吃，凉皮、肉夹馍、羊肉泡馍，每一样都很值得尝试。"],
            "成都": ["成都美食太丰富了，火锅最有名，但担担面、龙抄手也很好吃。",
                     "成都的火锅和串串香都很出名，小吃种类也非常多。"],
            "重庆": ["重庆的小面和火锅都很有名，喜欢辣的话一定要去试试！",
                     "重庆的火锅比成都的还辣，小面的汤底也特别香。"],
            "上海": ["上海的本帮菜很有特色，红烧肉和清蒸鱼都非常好吃，还有生煎包。",
                     "上海有很多本地小吃，生煎包、小笼包都是经典，值得一试。"],
            "南京": ["南京的鸭血粉丝汤特别有名，还有各种鸭肉做的菜，非常有特色。"],
            "北京": ["北京的烤鸭最有名，炸酱面也很有特色，还有豆汁这种老北京独特的饮品。"],
            "杭州": ["杭州有东坡肉、西湖醋鱼，还有龙井虾仁，都非常好吃。"],
        }
        _pool = _FOOD_POOL_INLINE.get(_resolved or "") if _resolved else None
        if _pool:
            alt = _pick_not_in(_pool, f"dedup|food|{_resolved}|{text}", _recent_set)
            if alt and _strip_discourse_prefix(alt) not in recent_bare:
                return alt

    # --- Step 2: topically appropriate clarification ----
    # Never cross-intent via _reverse_fact_answer — that can return a fact for a
    # different city/topic than what the learner asked (the RC-A failure mode).
    return _persona_deflect("generic", cand)


def _answer_user_question_prefix(last_answer: Optional[dict], persona: Optional[dict],
                                  recent_replies: Optional[list] = None,
                                  context_reply: str = "") -> Optional[tuple]:
    """
    Return (zh, en) answering common counter-questions without adding new API turns.
    Handles: mirror questions (richest), direct persona questions, generic 你呢, catch-all deflection.
    Returns None if last answer was not a question.
    Lexical definition and confusion-after-counter are resolved in the run_turn caller first.
    recent_replies: list of recent persona counter_replies for exact-repeat suppression.
    context_reply: the persona's preceding counter_reply (used for context-aware place follow-ups).
    """
    t = (last_answer.get("submitted_text") or last_answer.get("selected_option_hanzi") or "").strip()
    if not t:
        return None
    # Routing-only normalization — raw submitted text is preserved in last_answer.
    t = _normalize_zh_for_routing(t)
    t = t.replace("您", "你")
    if not _is_user_question(last_answer) and not _is_direct_persona_question(t):
        return None

    # Confusion / repeat signal (e.g. "再说一遍？", "再说一起可以吗？") — do NOT route to
    # _persona_limitation_reply.  Return None so run_turn's clarify_app_question path handles it.
    # Guard: genuine persona-directed questions that happen to contain a confusion substring
    # (e.g. "你住在哪里啊" contains "哪里啊") must NOT be early-exited here.
    _PERSONA_Q_STARTS = (
        "你住", "你老家", "你的老家", "你在哪", "你有", "你喜欢", "你做", "你叫",
        "你是", "你从", "你多大", "你几岁", "你最", "你平时", "你跟", "你和",
        "你今年", "你去过", "你结婚", "你父母", "你爸", "你妈",
    )
    if _is_confusion_signal(t) and not any(t.startswith(p) for p in _PERSONA_Q_STARTS):
        return None

    # Context-aware place follow-ups ("远不远啊" / "在哪儿" etc.) — must come BEFORE
    # the generic _place_distance_counter_reply which doesn't use city context.
    _pf = _place_followup_reply(t, persona, context_reply=context_reply)
    if _pf:
        return _pf

    # Mirror questions (richest answers — use discoverable_facts / profile via _mirror_persona_stub)
    _mirror = _find_mirror_answer(t, "", persona)
    if _mirror:
        return (_mirror[0], _mirror[1])   # return (zh, en); topic/engine handled by caller state-write

    _dist = _place_distance_counter_reply(t, persona)
    if _dist:
        return _dist

    # Direct questions aimed at the partner (你是哪里人？ 你住哪里？ etc.)
    _direct = _direct_persona_answer(t, persona, recent_replies=recent_replies)
    if _direct:
        zh = f"我呢，{_direct}" if not _direct.startswith("我") else _direct
        en = _persona_answer_en(persona, zh, _detect_reverse_fact_intent(t))
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

    # Family-member questions: "女儿做什么工作啊" / "孩子多大" / "儿子在哪里工作" etc.
    # The persona may or may not have children — use available facts or a safe deflect.
    _fam_words  = ("女儿", "儿子", "孩子", "宝宝")
    _fam_action = ("做什么工作", "上班", "上学", "工作", "多大", "几岁", "在哪")
    if any(fw in t for fw in _fam_words) and any(aw in t for aw in _fam_action):
        facts    = (persona or {}).get("discoverable_facts") or {} if persona else {}
        children = (facts.get("children") or "").strip()
        if children:
            # Return only the first sentence so answers stay concise
            _cs = re.split(r'[。！？]', children)[0].strip()
            return (_cs or children, "")
        # Safe persona-agnostic fallback — does not assert or deny children
        return ("这个嘛……我暂时保密好了。", "I'll keep that to myself for now.")

    # Extended-family location — e.g. "你奶奶在哪里？" "你爷爷住哪里"
    # Already handled in _direct_persona_answer; this catches any that slipped through.
    _ext_fam2 = ("奶奶", "爷爷", "外婆", "外公", "姥姥", "姥爷")
    if any(fw in t for fw in _ext_fam2):
        _persona_profile = (persona or {}).get("profile") or {}
        ht = (_persona_profile.get("hometown") or "").strip()
        rel = next((fw for fw in _ext_fam2 if fw in t), "老人")
        if ht:
            return (f"我{rel}住在{ht}那边，离我有点远。", "")
        return (f"我{rel}住在老家，不常见面，但保持联系。", "")

    # Catch-all: user asked a question we don't have a specific answer for.
    # Prefer a simple topic-bridge instead of a flat evasive phrase wherever possible.
    _profile_catch = (persona or {}).get("profile") or {}
    _city_catch    = (_profile_catch.get("city") or "").strip()
    _ht_catch      = (_profile_catch.get("hometown") or "").strip()
    if any(kw in t for kw in ("哪里", "哪儿", "住", "在哪")) and (_city_catch or _ht_catch):
        loc = _city_catch or _ht_catch
        return (f"我在{loc}这边，你呢？", "")
    if not _is_cooking_question(t) and any(kw in t for kw in ("工作", "做什么", "职业", "上班")):
        _vl_catch = (persona or {}).get("voice_lines") or {}
        work_line = _vl_catch.get("work") or ""
        if work_line:
            return (work_line, "")
        _occ_catch = (_profile_catch.get("occupation") or "").strip()
        if _occ_catch:
            return (f"我是做{_occ_catch}的，还挺有意思的。", "")

    # Try soft persona fallback first (name meaning, routine, etc.) before hard limitation.
    _soft = _soft_persona_fallback(t, persona)
    if _soft:
        return (_soft, "")
    # E2: Topic-aware honest fallback — fires before the generic '电脑角色' disclaimer.
    # When the learner asked a recognisable question about travel, food, or work preference
    # but no specific persona data matched, return a conversational on-topic response.
    _topic_honest = _topic_aware_honest_fallback(t, persona)
    if _topic_honest:
        return _topic_honest
    # Transparent limitation fallback: the learner asked a clear question we can't
    # specifically answer.  "这个不好说" / "这个还是秘密" is opaque and frustrating;
    # a brief honest acknowledgment is better UX.
    _topic_hint = _context_city_from_text(context_reply) or ""
    zh = _persona_limitation_reply(_topic_hint)
    return (zh, "I'm not sure about that. I'm just a practice computer persona.")


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
    for t in chosen:
        if len(result) >= 3:
            break
        zh = t["zh"]
        # Fill known memory facts into placeholders
        if "___" in zh:
            if name and ("叫" in zh or "名字" in zh):
                zh = zh.replace("___", name)
            elif city and ("住" in zh or "人" in zh or "去过" in zh):
                zh = zh.replace("___", city)
            elif food and "吃" in zh:
                zh = zh.replace("___", food)
        # Skip any option that still has an unfilled slot — never emit raw ___ to learner.
        if "___" in zh:
            continue
        result.append({
            "id":   f"__sent_{len(result)}",
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
    # TRAVEL disclosed while in PLACE engine (e.g. "我想去中国") →
    # ask where they most want to go (place-engine frame) rather than falling
    # through to f_live_with_who, which is topically unrelated.
    ("TRAVEL", "place"): ["f_place_want_visit"],
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


def _pick_micro_probe(engine: str, recent: list) -> Optional[str]:
    """Return a short micro-probe frame id (为什么？哪里？etc.) or None if rate-limited.

    Rate limit: no probe if one fired in the last 2 frames (prevents chaining).
    Falls back to 'f_micro_probe_why' (universal) if engine has no specific pool entry.
    """
    recent_list = recent or []
    # Rate limit: don't fire if any micro-probe was used in last 2 turns
    for fid in recent_list[-2:]:
        if fid in _MICRO_PROBE_FRAME_IDS:
            return None
    engine_norm = (engine or "").strip().lower()
    pool = _MICRO_PROBE_BY_ENGINE.get(engine_norm, ["f_micro_probe_why"])
    recent_set = set(recent_list)
    for candidate in pool:
        if candidate not in recent_set:
            return candidate
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

# Work frames that assume the learner disclosed a job — must not fire when the learner expressed
# confusion (no job was actually named) because JOB slot is inferred from frame-id alone,
# not from answer content.  The guard swaps any of these to f_work_yn on a typed confusion turn.
_CURRENT_WORK_PROGRESSION_FRAMES: frozenset = frozenset({
    "f_probe_work_role_detail",   # 那是什么样的工作？  — FIRST in JOB slot chain; assumes job named
    "f_work_company",             # 你在哪个公司上班？
    "f_probe_work_company_vibe",  # 那家公司怎么样？
    "f_work_tenure",              # 你做这个工作多久了？
    "f_work_where",               # 你工作在哪儿？
    "f_probe_work_origin",        # 你怎么进入这个行业的？  — assumes entered a field
    "f_probe_work_future",        # 以后想继续做这份工作吗？ — assumes current job
    "f_probe_work_why_quit",      # 你为什么离开那份工作？  — assumes named job was left
})


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
    typed_confusion: bool = False,
    memory: Optional[dict],
) -> Optional[str]:
    """Swap incoherent next-frame picks (food probe after place emotion; food after learner skip).

    typed_confusion: True when the learner submitted a typed answer that is a confusion signal
    (e.g. '我不明白').  Treated like learner_skip_confusion for the work-progression guard.
    """
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

    # 1b) Typed confusion signal on a work-progression frame — swap to the soft yes/no entry.
    # Covers typed answers ("我不明白") that never set the client-side learner_skip_confusion flag.
    # Only fires for frames that explicitly assume current employment; leaves other work frames alone.
    if (learner_skip_confusion or typed_confusion) and chosen in _CURRENT_WORK_PROGRESSION_FRAMES:
        if "f_work_yn" in _frames_by_id and "f_work_yn" not in recent_set:
            return "f_work_yn"

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


# ── Persona-aware discovery question selection ─────────────────────────────
# Maps discoverable_facts / voice_lines field keys → mirror topic keys they support.
# Only maps a fact key to topics where _mirror_persona_stub actually reads that key
# — so every entry is guaranteed to produce a persona answer the learner can unlock.
_FACT_KEY_TO_TOPICS: dict = {
    "place_from":      frozenset({"place_from", "place_like"}),  # place_from backs place_like too
    "place":           frozenset({"place_special", "place_like"}),
    "food":            frozenset({"food_fav", "food_local"}),
    "work":            frozenset({"work_what", "work_like", "work_duration"}),
    "work_company":    frozenset({"work_company"}),
    "work_origin":     frozenset({"work_origin", "work_duration"}),
    "travel_where":    frozenset({"travel_where"}),
    "travel":          frozenset({"travel_memorable"}),
    "travel_with":     frozenset({"travel_with"}),
    "family":          frozenset({"family_size", "family_siblings"}),
    "family_size":     frozenset({"family_size"}),
    "family_siblings": frozenset({"family_siblings"}),
    "family_live":     frozenset({"family_live"}),
    "hobby":           frozenset({"hobby_what", "hobby_duration"}),
    "hobby_best":      frozenset({"hobby_best"}),
    "hobby_origin":    frozenset({"hobby_origin"}),
    "identity":        frozenset({"name_meaning", "name_story", "name_giver"}),
}

# Per-engine: the single mirror topic that most directly unlocks a concrete persona fact.
# Used to prefer a specific question from the engine bank over whichever happens to be first.
_ENGINE_DISCOVERY_OPENER_TOPIC: dict = {
    "place":    "place_like",     # "你喜欢你的家乡吗？" → vl["place"] / profile.hometown
    "food":     "food_fav",       # "你最喜欢吃什么？"   → discoverable_facts["food"]
    "work":     "work_like",      # "你喜欢你的工作吗？" → vl["work_like"] / graceful fallback
    "travel":   "travel_fav",     # "你最喜欢哪个地方？" → discoverable_facts["travel_where"]
    "family":   "family_size",    # "你家里有几个人？"   → discoverable_facts["family_size"]
    "hobby":    "hobby_what",     # "你喜欢做什么？"     → discoverable_facts["hobby"]
    "identity": "name_meaning",   # "你的名字有什么意思？" → discoverable_facts["identity"]
}

# Maps fact keys → engine names (for richness counting)
_FACT_KEY_ENGINE: dict = {
    "place_from": "place",  "place": "place",
    "food": "food",
    "work": "work",         "work_company": "work",    "work_origin": "work",
    "travel_where": "travel", "travel": "travel",     "travel_with": "travel",
    "family": "family",     "family_size": "family",   "family_siblings": "family",
                            "family_live": "family",
    "hobby": "hobby",       "hobby_best": "hobby",     "hobby_origin": "hobby",
    "identity": "identity",
}

_DISCOVERY_ENGINE_ORDER = ["place", "work", "food", "travel", "family", "hobby", "identity"]


def _persona_backed_topics(persona: Optional[dict]) -> frozenset:
    """Return mirror topic keys that the persona can answer with concrete content.
    Used to bias discovery question ordering toward questions that unlock real facts.
    """
    if not persona:
        return frozenset()
    facts = persona.get("discoverable_facts") or {}
    vl    = persona.get("voice_lines") or {}
    backed: set = set()
    for key, topics in _FACT_KEY_TO_TOPICS.items():
        if (facts.get(key) or "").strip():
            backed.update(topics)
    # voice_lines back their natural topics too
    _VL_KEY_TOPICS = {
        "work":   {"work_what", "work_like"},
        "food":   {"food_fav"},
        "travel": {"travel_where"},
        "hobby":  {"hobby_what"},
        "place":  {"place_like"},
    }
    for vk, topics in _VL_KEY_TOPICS.items():
        if (vl.get(vk) or "").strip():
            backed.update(topics)
    return frozenset(backed)


def _persona_rich_engines(persona: Optional[dict]) -> list:
    """Return engine names sorted by how many non-empty discoverable_facts keys they have.
    Biases cross-engine supplement questions toward engines the persona can answer most fully.
    """
    if not persona:
        return list(_DISCOVERY_ENGINE_ORDER)
    facts  = persona.get("discoverable_facts") or {}
    counts: dict = {}
    for k, v in facts.items():
        if v:
            eng = _FACT_KEY_ENGINE.get(k)
            if eng:
                counts[eng] = counts.get(eng, 0) + 1
    return sorted(_DISCOVERY_ENGINE_ORDER, key=lambda e: -counts.get(e, 0))


# Keywords that indicate the persona has shared concrete personal content.
# Used to set last_persona_reveal in state_update so the next turn can trigger
# proactive discovery (the learner should be invited to ask follow-ups).
_PERSONA_REVEAL_KEYWORDS: tuple = (
    # Place names (major cities/regions)
    "成都", "西安", "北京", "上海", "广州", "杭州", "南京", "苏州", "重庆", "武汉",
    "深圳", "厦门", "青岛", "大连", "长沙",
    # Food
    "火锅", "面条", "饺子", "小吃", "包子", "烤鸭", "豆腐", "家常菜",
    # Place/origin sentiment
    "老家", "家乡", "从小", "长大", "小时候",
    # Preference
    "最喜欢", "特别喜欢", "喜欢",
    # Activity / work detail
    "教书", "爬山", "旅行", "退休", "多年", "几年",
    # Occupation / tech work (software dev etc.)
    "开发", "软件", "程序员", "工程师", "从事",
)

# Occupation signals for discovery engine override and relevance boost (not routing).
_WORK_OCCUPATION_KEYWORDS: tuple = (
    "开发", "软件", "程序员", "工程师", "从事",
    "教书", "教学", "老师", "工作", "退休", "上班", "公司",
)


def _text_signals_work_occupation(text: str) -> bool:
    """True when text mentions work/occupation (incl. 软件开发-style disclosures)."""
    if not text:
        return False
    return any(kw in text for kw in _WORK_OCCUPATION_KEYWORDS)


# ── Local conversational probing: learner-answer affordance signals ──────────
_META_PLACE_NAMES: frozenset = frozenset({"中国", "大陆", "内地", "台湾", "香港", "澳门"})

_FAMILY_PERSON_KEYWORDS: tuple = (
    "爸爸", "妈妈", "父母", "家人", "老婆", "太太", "爱人", "丈夫",
    "孩子", "儿子", "女儿", "哥哥", "姐姐", "弟弟", "妹妹", "爷爷", "奶奶",
)

_TRAVEL_INTENT_KEYWORDS: tuple = ("想去", "打算去", "计划去", "要去", "希望去")

_FOOD_AFFORDANCE_KEYWORDS: tuple = (
    "吃", "好吃", "美食", "菜", "饭", "火锅", "肉", "羊肉", "牛肉", "面", "饺子",
)

_DURATION_AFFORDANCE_KEYWORDS: tuple = (
    "以前", "之前", "多久", "几年", "年了", "做了", "已经", "住了",
)


def _text_mentions_domestic_city(text: str) -> bool:
    """True when text names a domestic city/province (excl. meta region tokens)."""
    if not text:
        return False
    return any(c in text for c in _CHINA_DOMESTIC_PLACE_NAMES if c not in _META_PLACE_NAMES)


def _text_signals_travel_intent(text: str) -> bool:
    if not text:
        return False
    if any(k in text for k in _TRAVEL_INTENT_KEYWORDS):
        return True
    return any(k in text for k in ("旅行", "旅游", "去过"))


# Volunteered travel intent — an explicit "I want/plan to go to X" statement, or a
# future-time marker + 去 X.  Distinct from _has_strong_travel_signal (enthusiasm
# phrases like 很喜欢旅行) so a plain "我想去甘肃" also routes to travel.
_TRAVEL_INTENT_VERBS: tuple = ("想去", "要去", "打算去", "计划去", "希望去", "准备去")
_TRAVEL_TIME_MARKERS: tuple = (
    "明年", "下个月", "下周", "下星期", "明天", "后天", "以后", "将来", "过几天",
    "一月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "十月", "十一月", "十二月",
)


def _has_volunteered_travel_intent(text: str) -> bool:
    """True when the learner volunteers a concrete travel plan.

    Matches: 我想去 X / 我要去 X / 我打算去 X / …, or a time marker (九月/明年/…) + 去 X.
    """
    t = (text or "").strip()
    if not t:
        return False
    if any(v in t for v in _TRAVEL_INTENT_VERBS):
        return True
    if "去" in t and any(m in t for m in _TRAVEL_TIME_MARKERS):
        return True
    return False


# ASR sometimes prefixes a recognised country name with an implausible noun that does
# not belong in a destination (e.g. "公司中国" instead of "中国"). These are the specific
# non-place nouns known to leak in front of a country name via mis-segmented ASR — kept
# narrow and explicit so legitimate multi-word destinations are never touched.
_TRAVEL_DEST_IMPLAUSIBLE_PREFIXES: tuple = (
    "公司", "工作", "学校", "老师", "医院", "银行", "政府", "研究所",
)


def _recover_malformed_travel_destination(dest: str) -> str:
    """Recover a recognised country from a malformed extraction like "公司中国".

    Only fires when the destination is EXACTLY <implausible_prefix><known_country>
    (nothing else). Never strips words from destinations that are not built this way,
    so genuine multi-word or province+city destinations are left untouched.
    """
    if not dest:
        return dest
    for country in _TRAVEL_COUNTRIES:
        if dest == country:
            return dest
        if dest.endswith(country):
            prefix = dest[: -len(country)]
            if prefix in _TRAVEL_DEST_IMPLAUSIBLE_PREFIXES:
                return country
    return dest


def _extract_travel_destination(text: str) -> str:
    """Extract the destination from a volunteered travel-intent statement.

    Prefers the destination after an intent verb (想去/要去/…); falls back to the
    place after a time-marker + 去.  Returns "" when nothing plausible is found.
    """
    t = (text or "").strip()
    if not t:
        return ""
    # Prefer the intent-verb destination (want to go > will go somewhere).
    for verb in _TRAVEL_INTENT_VERBS:
        idx = t.rfind(verb)
        if idx != -1:
            tail = t[idx + len(verb):]
            # Strip leading filler characters that ASR inserts between verb and destination.
            tail = tail.lstrip("啊哦呢吧嗯哈")
            # Strip leading time marker (e.g. "九月上去中国" → "上去中国").
            for _tm in _TRAVEL_TIME_MARKERS:
                if tail.startswith(_tm):
                    tail = tail[len(_tm):]
                    break
            # Strip leading directional complements from ASR noise (e.g. "上去中国" → "中国").
            for _dc in ("上去", "下去", "过去", "回去", "进去", "出去"):
                if tail.startswith(_dc):
                    tail = tail[len(_dc):]
                    break
            dest = re.split(r"[，,。.！!？?、\s]", tail, maxsplit=1)[0].strip()
            dest = dest.strip("的了吧呢啊")
            if dest and re.fullmatch(r"[\u4e00-\u9fffA-Za-z]+", dest):
                return _recover_malformed_travel_destination(dest[:6])
    # Fall back to the place after a bare 去 (first occurrence).
    m = re.search(r"去([\u4e00-\u9fff]{2,6})", t)
    if m:
        return _recover_malformed_travel_destination(m.group(1).strip("的了吧呢啊"))
    return ""


def _travel_intent_followup(text: str) -> tuple:
    """Return (zh, en) travel follow-up for a volunteered travel intent.

    Templates are loaded from content/recovery_phrases.json (use=travel_intent_followup).
    The destination-specific template has a {DEST} slot that is filled at runtime.
    Falls back to the generic template when no destination is extractable, and to
    empty strings if the phrase bank has not been loaded (fail-safe, no inline Chinese).
    """
    dest = _extract_travel_destination(text)
    if dest:
        tpl_zh, tpl_en = _travel_intent_followup_templates.get("dest", ("", ""))
        if tpl_zh:
            return (tpl_zh.replace("{DEST}", dest), tpl_en.replace("{DEST}", dest))
        # phrase bank not loaded — return empty so caller falls through safely
        return ("", "")
    zh, en = _travel_intent_followup_templates.get("generic", ("", ""))
    return (zh, en)


def _should_route_to_travel(
    answer_text: str,
    current_engine: str,
    user_asked_question: bool,
    slot_names: Optional[list] = None,
) -> bool:
    """Whether a learner turn should bridge the conversation to the travel engine.

    Fires on volunteered travel intent (我想去 X / 九月…去 X) regardless of the
    current frame's slot, OR on an enthusiasm phrase while a TRAVEL slot is active.
    """
    if user_asked_question:
        return False
    if (current_engine or "").strip().lower() == "travel":
        return False
    if _has_volunteered_travel_intent(answer_text):
        return True
    _slots = slot_names or []
    if "TRAVEL" in _slots and _has_strong_travel_signal(answer_text):
        return True
    return False


def _text_signals_family_disclosure(text: str) -> bool:
    if not text:
        return False
    if any(k in text for k in ("一起住", "住在一起", "同住")):
        return True
    family_hits = sum(1 for k in _FAMILY_PERSON_KEYWORDS if k in text)
    return family_hits >= 2 or (family_hits >= 1 and "住" in text)


def _text_signals_food_disclosure(text: str) -> bool:
    if not text:
        return False
    return any(k in text for k in _FOOD_AFFORDANCE_KEYWORDS)


def _infer_local_probe_boost_topics(text: str) -> frozenset:
    """Map recent learner/partner text to mirror topics for local follow-up probes."""
    if not text:
        return frozenset()
    t = text.strip()
    boost: set = set()

    has_city = _text_mentions_domestic_city(t)
    has_place = has_city or any(k in t for k in ("地方", "那里", "那边", "城市", "家乡", "老家"))
    has_work = _text_signals_work_occupation(t)

    if has_place:
        boost.update((
            "place_like", "place_why_like", "place_food", "place_special", "place_still_live",
        ))

    if has_work:
        boost.update(("work_duration", "work_like", "work_why", "work_interesting"))
        if "老师" in t or "教书" in t:
            boost.add("work_students")

    if _text_signals_family_disclosure(t):
        boost.update((
            "family_live", "family_weekend", "marriage", "children", "family_size",
        ))

    if _text_signals_travel_intent(t):
        boost.update((
            "travel_why_fav", "travel_next", "place_never_been", "travel_fav",
        ))

    if _text_signals_food_disclosure(t):
        boost.update(("food_fav", "food_why_like", "food_cook", "food_spicy"))

    if any(k in t for k in _DURATION_AFFORDANCE_KEYWORDS):
        if has_work:
            boost.add("work_duration")
        elif "玩" in t or "爱好" in t or "学" in t:
            boost.add("hobby_duration")
        elif has_place:
            boost.update(("place_like", "place_why_like"))

    return frozenset(boost)


def _local_affordance_relevance_bonus(topic: str, combined: str) -> int:
    """Extra relevance when a question topic matches a local disclosure affordance."""
    if not combined or not topic:
        return 0
    bonus = 0
    if topic.startswith("place_") and (
        _text_mentions_domestic_city(combined)
        or any(k in combined for k in ("那里", "老家", "家乡", "城市"))
    ):
        bonus += 8
    if topic.startswith("work_") and _text_signals_work_occupation(combined):
        bonus += 8
    if (topic.startswith("family_") or topic in ("marriage", "children")) and (
        any(k in combined for k in _FAMILY_PERSON_KEYWORDS)
        or "一起住" in combined
        or "住在一起" in combined
    ):
        bonus += 8
    if (topic.startswith("travel_") or topic == "place_never_been") and _text_signals_travel_intent(combined):
        bonus += 8
    if topic.startswith("food_") and _text_signals_food_disclosure(combined):
        bonus += 8
    if topic.endswith("_duration") and any(k in combined for k in _DURATION_AFFORDANCE_KEYWORDS):
        bonus += 6
    return bonus


def _resolve_discovery_engine_for_context(
    disc_eng: str,
    ctx_text: str,
    *,
    overseas_detected: bool = False,
    reply_for_eng: str = "",
) -> str:
    """Pick discovery pool engine from recent disclosure context (ranking only)."""
    eng = (disc_eng or "").strip().lower()
    if overseas_detected and eng in ("identity",):
        return "place"

    probe = _discovery_context_merge(ctx_text, reply_for_eng)
    if not probe:
        return eng

    if _text_signals_travel_intent(probe):
        return "travel"
    if _text_signals_family_disclosure(probe):
        return "family"
    if _text_signals_food_disclosure(probe) and not _text_signals_work_occupation(probe):
        return "food"
    if _text_signals_work_occupation(probe):
        return "work"
    if _text_mentions_domestic_city(probe) or any(k in probe for k in ("老家", "家乡", "城市")):
        return "place"

    if reply_for_eng and any(kw in reply_for_eng for kw in _PERSONA_REVEAL_KEYWORDS[:15]):
        return "place"
    if eng in ("identity",) and _text_signals_work_occupation(probe):
        return "work"

    return eng


def _discovery_context_merge(*parts: str) -> str:
    """Join non-empty discovery context fragments (same-turn + prior-turn)."""
    return " ".join(p.strip() for p in parts if p and p.strip())


def _has_persona_reveal(text: str) -> bool:
    """Return True when text contains concrete persona details that should invite follow-up questions.

    Used to set last_persona_reveal in state_update.  A positive result on THIS turn's
    counter_reply or reaction causes proactive discovery to fire on the NEXT turn.
    """
    if not text or len(text) < 8:
        return False
    return any(kw in text for kw in _PERSONA_REVEAL_KEYWORDS)


# ── Context keyword map: topic → signals that should appear in frame/context text ──────────────────
# Used by _discovery_relevance_score to rank questions closer to the active sentence/topic.
# Keywords are Chinese bigrams or short phrases that reliably co-occur with the topic.
_TOPIC_CONTEXT_KEYWORDS: dict = {
    "place_from":              ["哪里人", "是哪里", "来自", "家乡", "老家", "故乡"],
    "place_special":           ["特别", "特色", "好玩", "有意思", "景点"],
    "place_why_like":          ["为什么", "喜欢那里", "喜欢这里", "为啥"],
    "place_like":              ["喜欢", "生活", "住"],
    "place_food":              ["好吃", "吃什么", "美食", "菜", "食物", "火锅", "辣", "最爱"],
    "place_far":               ["远", "多久", "飞机", "火车", "离这里"],
    "place_still_live":        ["还住", "住在", "现在住"],
    "place_distance_time":     ["多久", "小时", "飞机", "坐飞机"],
    "place_distance_transport":["怎么去", "坐飞机", "坐火车", "交通"],
    "place_distance_ref":      ["远不远", "离", "远"],
    "work_what":               ["工作", "做什么", "上班", "职业", "当", "开发", "软件", "程序员", "工程师", "从事"],
    "work_like":               ["喜欢", "工作", "觉得"],
    "work_why":                ["为什么", "当老师", "选择", "怎么"],
    "work_duration":           ["多久", "几年", "年", "做了", "开发", "软件", "工作"],
    "work_interesting":        ["有趣", "好玩", "好奇"],
    "work_students":           ["学生", "教学", "老师", "教书"],
    "work_platform":           ["分享", "平台", "作品"],
    "food_fav":                ["好吃", "喜欢吃", "最爱", "吃什么", "最喜欢吃"],
    "food_local":              ["家乡", "当地", "本地"],
    "food_spicy":              ["辣", "川菜", "火锅", "麻辣"],
    "food_cook":               ["自己做", "会做", "做饭", "厨艺"],
    "food_why_like":           ["为什么喜欢", "为什么", "好吃"],
    "family_size":             ["家里", "几个人", "家人", "几口"],
    "family_siblings":         ["兄弟", "姐妹", "哥", "弟", "姐", "妹"],
    "family_live":             ["住在一起", "一起住", "住哪", "父母"],
    "marriage":                ["结婚", "太太", "老婆", "爱人", "丈夫", "成家"],
    "children":                ["孩子", "儿子", "女儿", "小孩"],
    "family_weekend":          ["周末", "一起", "活动", "休息"],
    "name_meaning":            ["名字", "意思", "含义"],
    "name_giver":              ["名字", "谁", "取"],
    "name_story":              ["名字", "故事", "来历"],
    "age":                     ["多大", "几岁", "年龄"],
    "travel_where":            ["去过", "旅行", "旅游", "哪里"],
    "travel_memorable":        ["难忘", "印象", "旅行", "经历"],
    "travel_fav":              ["最喜欢", "地方", "喜欢哪里"],
    "travel_why_fav":          ["为什么", "喜欢那个", "那个地方"],
    "travel_next":             ["下次", "想去", "计划"],
    "hobby_what":              ["爱好", "喜欢做", "平时"],
    "hobby_duration":          ["多久", "几年", "学了"],
    "hobby_why":               ["为什么", "喜欢", "兴趣"],
    "hobby_how_started":       ["怎么开始", "怎么学", "为什么学"],
}


def _discovery_relevance_score(q: dict, frame_text: str, context_text: str) -> int:
    """Return relevance score 0–20 for a discovery question given active conversation context.

    frame_text:   the current app question or most recent partner frame text.
    context_text: persona counter-reply or recent learner answer — whichever is richer.

    Scoring:
      +10  topic keyword found in frame_text (strongest: directly about the active question)
      + 7  topic keyword found in context_text (persona answer or learner answer)
      + 5  2-gram from question zh found in frame_text (broad text overlap)
      + 3  2-gram from question zh found in context_text
    Scores are additive (capped at 20).
    """
    if not frame_text and not context_text:
        return 0
    topic     = q.get("topic") or ""
    zh        = q.get("zh") or ""
    score     = 0
    ft_lower  = frame_text
    ctx_lower = context_text

    # Topic-keyword hits
    for sig in _TOPIC_CONTEXT_KEYWORDS.get(topic, []):
        if sig in ft_lower:
            score += 10
            break
    for sig in _TOPIC_CONTEXT_KEYWORDS.get(topic, []):
        if sig in ctx_lower:
            score += 7
            break

    # Bigram overlap: any 2-char substring of the question in context
    _matched_ft = False
    for i in range(len(zh) - 1):
        gram = zh[i:i+2]
        if len(gram) == 2 and gram in ft_lower:
            score += 5
            _matched_ft = True
            break
    if not _matched_ft:
        for i in range(len(zh) - 1):
            gram = zh[i:i+2]
            if len(gram) == 2 and gram in ctx_lower:
                score += 3
                break

    # Immediate adjacency: occupation disclosure boosts work follow-up topics.
    _combined = (frame_text or "") + (context_text or "")
    if _combined and topic.startswith("work_"):
        if any(k in _combined for k in ("开发", "软件", "程序员", "工程师", "从事")):
            score += 8

    score += _local_affordance_relevance_bonus(topic, _combined)

    return min(score, 20)


def _build_discovery_pool(disc_eng: str,
                           backed_topics: frozenset,
                           rich_engines: list,
                           seen_topics: set,
                           boost_topics: frozenset = frozenset(),
                           frame_text: str = "",
                           context_text: str = "") -> list:
    """Build and rank the discovery question pool for the blue panel.

    Shared by counter-reply discovery and proactive discovery to avoid code duplication.
    Returns a deduped list sorted so context-relevant questions come first, then
    backed-topic questions, then curiosity questions, then the rest.

    boost_topics:  optional set of topics to sort to the very front (distance after overseas mention).
    frame_text:    current partner frame question — used to rank by relevance to active sentence.
    context_text:  persona counter-reply or learner answer — secondary relevance signal.
    """
    disc_pool: list = list(_MIRROR_QUESTIONS_BY_ENGINE.get(disc_eng) or [])
    for adj in rich_engines:
        if len(disc_pool) >= 4:
            break
        if adj == disc_eng:
            continue
        adj_qs = _MIRROR_QUESTIONS_BY_ENGINE.get(adj) or []
        opener_topic = _ENGINE_DISCOVERY_OPENER_TOPIC.get(adj)
        best_q: Optional[dict] = None
        if opener_topic:
            best_q = next(
                (q for q in adj_qs
                 if q.get("topic") == opener_topic and q.get("topic") not in seen_topics),
                None,
            )
        if not best_q:
            best_q = next(
                (q for q in adj_qs
                 if q.get("topic") in backed_topics and q.get("topic") not in seen_topics),
                None,
            )
        if not best_q:
            best_q = next(
                (q for q in adj_qs if q.get("topic") not in seen_topics),
                adj_qs[0] if adj_qs else None,
            )
        if best_q and len(disc_pool) < 4:
            disc_pool.append(best_q)

    def _sort_key(q: dict) -> tuple:
        """Sort key: boost > high-relevance+curious+backed > relevance tiers > curiosity+backed."""
        if q.get("topic") in boost_topics:
            return (0, 0, 0)
        rel     = _discovery_relevance_score(q, frame_text, context_text)
        backed  = q.get("topic") in backed_topics
        curious = bool(q.get("curiosity"))
        # Tier by relevance band: >= 10 = strong, >= 5 = moderate, < 5 = weak
        if rel >= 10:
            tier = 1
        elif rel >= 5:
            tier = 2
        else:
            tier = 3
        # Within tier: curious+backed > curious > backed > neither
        sub = 0 if (curious and backed) else (1 if curious else (2 if backed else 3))
        return (tier, sub, -rel)  # -rel so higher scores sort first within same tier

    disc_pool.sort(key=_sort_key)

    seen_q_topics: set = set()
    deduped: list = []
    for q in disc_pool:
        qt = q.get("topic") or q.get("zh", "")
        if qt not in seen_q_topics:
            seen_q_topics.add(qt)
            deduped.append(q)
    return deduped


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
        # Reciprocal frame lookup: frame_id → mirror question entry.
        # Built here while _cm_raw and _MIRROR_QUESTIONS_BY_ENGINE are both in scope.
        # Covers all core_entries so adding new reciprocal frames only requires a JSON edit.
        _RECIPROCAL_FRAME_TO_Q: dict = {}
        for _rce in (_cm_raw.get("core_entries") or []):
            _rce_fid, _rce_topic = _rce.get("frame_id", ""), _rce.get("topic", "")
            if not _rce_fid or not _rce_topic:
                continue
            for _rce_qs in _MIRROR_QUESTIONS_BY_ENGINE.values():
                for _rce_q in _rce_qs:
                    if _rce_q.get("topic") == _rce_topic:
                        _RECIPROCAL_FRAME_TO_Q[_rce_fid] = _rce_q
                        break

        # reciprocal_aliases: slotted frames explicitly declared safe for reciprocal
        # card lookup. Slot filling only affects question text shown to learner, not
        # which mirror question we surface — so aliases are safe without slot checks.
        for _ra in (_cm_raw.get("reciprocal_aliases") or []):
            _ra_fid, _ra_topic = _ra.get("frame_id", ""), _ra.get("topic", "")
            if not _ra_fid or not _ra_topic:
                continue
            if _ra_fid in _RECIPROCAL_FRAME_TO_Q:
                continue  # core_entries wins if both declare same frame_id
            for _ra_qs in _MIRROR_QUESTIONS_BY_ENGINE.values():
                for _ra_q in _ra_qs:
                    if _ra_q.get("topic") == _ra_topic:
                        _RECIPROCAL_FRAME_TO_Q[_ra_fid] = _ra_q
                        break

        _cm_n = sum(len(v) for v in _core_by_engine.values())
        _cm_alias_n = len(_cm_raw.get("reciprocal_aliases") or [])
        print(f"[ui_server] mirror_core_map loaded ({_cm_n} core entries across {len(_core_by_engine)} engines); {_cm_alias_n} alias(es); reciprocal frame map: {len(_RECIPROCAL_FRAME_TO_Q)} frames")
    else:
        _RECIPROCAL_FRAME_TO_Q = {}
        print(f"[ui_server] INFO: mirror_core_map.json not found at {_core_mirror_map_path} — using discovery bank only")
except RuntimeError:
    raise
except Exception as _cm_e:
    raise RuntimeError(f"[MandarinOS] mirror_core_map load failed: {_cm_e}") from _cm_e

# E4: deterministic topic-to-engine mapping used by the initiative-follow handoff.
# When the learner's question is answered confidently from the mirror bank or working memory,
# cs["current_engine"] is updated to the mapped engine so the next frame stays on-topic.
_QUESTION_TOPIC_TO_ENGINE: dict = {
    # Travel
    "travel_where": "travel", "travel_memorable": "travel",
    "travel_fav": "travel", "travel_why_fav": "travel", "travel_next": "travel",
    # Food
    "food_fav": "food", "food_local": "food", "food_spicy": "food",
    "food_why_like": "food", "food_cook": "food",
    # Place
    "place_from": "place", "place_special": "place", "place_why_like": "place",
    "place_like": "place", "place_food": "place", "place_still_live": "place",
    "place_far": "place", "place_never_been": "place", "place_far_or_not": "place",
    "place_distance_ref": "place", "place_distance_time": "place",
    "place_distance_transport": "place",
    # Work
    "work_what": "work", "work_like": "work", "work_why": "work",
    "work_duration": "work", "work_interesting": "work",
    "work_students": "work", "work_platform": "work",
    # Family
    "family_size": "family", "family_siblings": "family", "family_live": "family",
    "family_weekend": "family", "marriage": "family", "children": "family",
    # Hobby
    "hobby_what": "hobby", "hobby_duration": "hobby",
    "hobby_why": "hobby", "hobby_how_started": "hobby",
    # Identity
    "name_meaning": "identity", "name_giver": "identity",
    "name_story": "identity", "age": "identity",
}

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


def _first_sentence(text: str) -> str:
    """Return the first complete sentence (up to the first 。！？).
    If no sentence-ending punctuation is found, returns the full text unchanged.
    Preferred over _first_clause for multi-sentence facts where the first sentence
    is already a natural, complete answer and the remainder is follow-up detail."""
    if not text:
        return text
    m = re.search(r'[。！？]', text)
    if m:
        return text[:m.end()]
    return text


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

    if topic in ("place_distance_ref", "place_distance_time", "place_distance_transport"):
        dp = persona.get("distance_profile") or {}
        zh_pre = (dp.get("zh") or "").strip()
        en_pre = (dp.get("en") or "").strip()
        if topic == "place_distance_ref":
            if zh_pre:
                return (zh_pre, en_pre)
            far = (dp.get("far_level") or "不算太远").strip()
            ref = (dp.get("reference") or city_home or "那边").strip()
            zh = f"{city_home}离{ref}{far}。" if city_home else "不算太远。"
            return (zh, f"It's {far} from {ref}." if ref else "Not too far.")
        if topic == "place_distance_time":
            t_val = (dp.get("time") or "几个小时").strip()
            transport = (dp.get("transport") or "交通工具").strip()
            zh = f"坐{transport}要{t_val}左右。"
            en = f"About {t_val} by {transport}."
            return (zh, en)
        if topic == "place_distance_transport":
            transport = (dp.get("transport") or "高铁").strip()
            zh = f"一般坐{transport}去。"
            en = f"Usually by {transport}."
            return (zh, en)

    if topic == "place_food":
        # "那里有什么好吃的？" — answer from persona's food facts, grounded in hometown knowledge.
        food_fact = (facts.get("food") or "").strip()
        if food_fact:
            return (food_fact, _fact_en("food"))
        if city_home:
            return (f"{city_home}的食物很有特色，我很喜欢当地的味道。", "")
        return ("我觉得当地的食物非常有特色，有机会试试！", "")

    if topic == "place_still_live":
        # "你现在还住在那里吗？" — confirm current residence as a standalone branch
        # (must be outside the place_from/like/special block whose outer guard excluded it).
        city_now = (profile.get("city") or "").strip()
        hometown = (profile.get("hometown") or "").strip()
        if city_now and hometown and city_now == hometown:
            zh = f"是的，我一直住在{city_now}，没有搬过。"
            en = f"Yes, I've always lived in {city_now}."
        elif city_now and hometown and city_now != hometown:
            zh = f"现在主要住在{city_now}，不过老家还是{hometown}。"
            en = f"I mainly live in {city_now} now — but my hometown is still {hometown}."
        elif city_now:
            zh = f"是的，我现在还住在{city_now}。"
            en = f"Yes, I still live in {city_now}."
        else:
            zh = "是的，我还在这边，没什么特别的变动。"
            en = "Yes, still here — nothing much has changed."
        return (zh, en)

    if topic == "place_why_like":
        # "你为什么喜欢那里？" — explain why the persona likes their city/hometown.
        fact = (facts.get("place") or "").strip()
        zh_vl = vl.get("place") or ""
        _why_markers = ("觉得", "因为", "喜欢", "特别", "最", "历史", "文化", "自豪", "有趣", "方便")
        _clauses = [c.strip() for c in re.split(r'[，。！？,]', fact) if c.strip()] if fact else []
        _why = next((c for c in _clauses if any(m in c for m in _why_markers)), None)
        if _why:
            return (_why + "。", _fact_en("place"))
        if zh_vl:
            return (zh_vl, _vl_en("place"))
        if city_home:
            return (f"因为我从小就在{city_home}长大，有感情，喜欢这里的生活节奏。", "")
        return ("因为已经习惯了，感觉挺有感情的，生活也比较方便。", "")

    if topic in ("place_from", "place_like", "place_special", "place_far", "place_far_or_not", "place_never_been"):
        fact = (facts.get("place") or "").strip()
        if topic == "place_special":
            zh = _first_clause(fact) if fact else "那里有一些很有意思的地方，有机会去看看。"
            return (zh, _fact_en("place"))
        if topic == "place_from":
            # Prefer a persona-supplied place_from fact over the generic template.
            # Apply _first_sentence() so the second sentence (local flavour detail)
            # is not pushed immediately — it surfaces naturally via place_like /
            # food_local follow-up questions and the blue discovery panel.
            specific = (facts.get("place_from") or "").strip()
            if specific:
                return (_first_sentence(specific), facts_en.get("place_from") or "")
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
        # travel_where / travel_fav: prefer explicit fact key (avoids 、-list truncation)
        specific_tw = (facts.get("travel_where") or "").strip()
        if specific_tw:
            return (specific_tw, facts_en.get("travel_where") or _fact_en("travel"))
        zh = _first_clause(fact) if fact else "我去过几个城市，最喜欢有美食的地方。"
        return (zh, _fact_en("travel"))

    if topic == "travel_why_fav":
        # "为什么喜欢那个地方？" / "你为什么喜欢那里？" — explain why the persona likes the fav destination.
        fact = (facts.get("travel") or "").strip()
        fav_key = (facts.get("travel_where") or "").strip()
        # Look for clauses containing evaluative/reason markers.
        _why_markers = ("觉得", "因为", "喜欢", "特别", "最", "印象", "历史", "文化", "艺术", "诗意")
        _clauses = [c.strip() for c in re.split(r'[，。！？,]', fact) if c.strip()] if fact else []
        _why = next((c for c in _clauses if any(m in c for m in _why_markers)), None)
        if _why:
            return (_why + "。", "")
        if fav_key:
            # Extract a why-flavoured clause from the travel_where line
            _tw_clauses = [c.strip() for c in re.split(r'[，。！？,]', fav_key) if c.strip()]
            _tw_why = next((c for c in _tw_clauses if any(m in c for m in _why_markers)), None)
            if _tw_why:
                return (_tw_why + "。", "")
        if fact:
            return (_first_clause(fact), _fact_en("travel"))
        return ("感觉很有意思，文化和风景都让我印象深刻。", "")

    if topic == "travel_next":
        # "下次想去哪里？" — future travel intent; most personas don't have this fact explicitly.
        fact = (facts.get("travel_next") or "").strip()
        if fact:
            return (fact, _fact_en("travel_next") or "")
        # Derive a plausible answer from existing travel data
        traveled = (facts.get("travel_where") or facts.get("travel") or "").strip()
        _clauses = [c.strip() for c in re.split(r'[，。！？,]', traveled) if c.strip()] if traveled else []
        # Pick a place the persona has mentioned or give a natural deflect
        if city_home:
            return (f"还没定好，不过一直想多了解一些新地方，也许去没去过的城市看看。", "")
        return ("还没想好，想找一个自然风景比较好的地方去放松一下。", "")

    # ── Work ─────────────────────────────────────────────────────────────────────
    if topic == "work_interesting":
        # "工作中最有趣的是什么？" — extract the most engaging aspect from the work fact.
        fact = (facts.get("work") or "").strip()
        occ  = (profile.get("occupation") or "").strip()
        # Look for clauses containing positive sentiment or student/project/result markers.
        _interesting_markers = ("学生", "进步", "有趣", "最喜欢", "最棒", "成就", "作品", "有意思", "好玩")
        _clauses = [c.strip() for c in re.split(r'[，。！？,]', fact) if c.strip()] if fact else []
        _best = next((c for c in _clauses if any(m in c for m in _interesting_markers)), None)
        if _best:
            return (_best + "。", "")
        if fact:
            return (_first_clause(fact), _fact_en("work"))
        if occ:
            return (f"我觉得{occ}这个工作每天都有新的挑战，挺有意思的。", "")
        return ("每天都在做不一样的事，感觉很有意思，一直学新东西。", "")

    if topic in ("work_what", "work_like", "work_duration", "work_platform", "work_company", "work_origin", "work_students", "work_why"):
        fact = (facts.get("work") or "").strip()
        if topic == "work_like":
            # Prefer a dedicated sentiment line; never return the job-description line
            # (voice_lines.work) since that answers "what" not "do you enjoy it".
            zh_vl = (vl.get("work_like") or "").strip()
            en_vl = (vl_en.get("work_like") or "").strip()
            return (zh_vl or "挺喜欢的，虽然有时候很忙。", en_vl or "I quite like it, though it can get busy.")
        if topic == "work_duration":
            # Prefer a clause that actually contains duration markers (年/久/开始/以来/毕业)
            _dur_markers = ("年", "久", "开始", "以来", "毕业", "多久", "一直")
            _clauses = [c.strip() for c in re.split(r'[，。！？,]', fact) if c.strip()] if fact else []
            _dur_clause = next((c for c in _clauses if any(m in c for m in _dur_markers)), None)
            if _dur_clause:
                return (_dur_clause + "。", "")
            # Do NOT fall back to a non-duration work clause (_nth_clause) — it would surface
            # role/project descriptions that don't answer "how long". Use a safe generic instead.
            return ("已经做了几年了，越做越有意思。", "")
        if topic == "work_platform":
            depth = _nth_clause(fact, 1) if fact else ""
            return (depth or "我在网上分享，有一些人关注。", "")
        if topic == "work_company":
            specific = (facts.get("work_company") or "").strip()
            return (specific or "我在一家挺不错的公司工作。", _fact_en("work_company"))
        if topic == "work_origin":
            specific = (facts.get("work_origin") or "").strip()
            return (specific or "大学毕业后就开始做这个，慢慢越来越喜欢。", _fact_en("work_origin"))
        if topic == "work_students":
            specific = (facts.get("work_students") or "").strip()
            occ = (profile.get("occupation") or "").strip()
            if specific:
                return (specific, _fact_en("work_students"))
            if occ and "老师" in occ:
                return ("学生都挺不错的，各有各的特点，也让我学到很多。", "")
            return ("大家都挺好的，合作很愉快。", "")
        if topic == "work_why":
            specific = (facts.get("work_origin") or "").strip()
            if specific:
                return (specific, _fact_en("work_origin"))
            occ = (profile.get("occupation") or "").strip()
            if occ:
                return (f"从小就对{occ}感兴趣，慢慢就走上了这条路。", "")
            return ("因为觉得很有意思，慢慢就越来越喜欢了。", "")
        # work_what: prefer voice_lines.work (the persona's "what do you do" line) over
        # _first_clause, which truncates rich facts at the first comma and loses the detail.
        if vl.get("work"):
            return (vl["work"], _vl_en("work"))
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
        "place_distance_ref":       "place",
        "place_distance_time":      "place",
        "place_distance_transport": "place",
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
    "我换一个方式说——",
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


# ── E3: Persona Working Memory ───────────────────────────────────────────────────────────────
# Known place names for bounded extraction (major travel destinations + Chinese cities).
_WM_KNOWN_PLACES: tuple = (
    "西藏", "云南", "北京", "上海", "成都", "重庆", "广州", "深圳",
    "苏州", "杭州", "西安", "南京", "武汉", "厦门", "青岛", "兰州",
    "丽江", "桂林", "三亚", "哈尔滨", "乌鲁木齐", "九寨沟",
    "黄山", "张家界", "敦煌", "西双版纳", "大理", "香港", "澳门",
    # Overseas / foreign travel destinations mentioned by personas
    "日本", "法国", "泰国", "韩国", "台湾", "欧洲", "越南", "新加坡",
)


def _extract_persona_facts_from_recent(recent_replies: list) -> dict:
    """
    Bounded, deterministic extraction of structured facts from recent persona replies.
    Scans the last 5 entries only. Pure read — does not write to cs or disk.

    Returns a dict that may contain:
        travel_visited: list[str]   — known place names mentioned
        travel_fav:     str          — place explicitly stated as favourite/most memorable
        city_now:       str          — stated current city
        hometown:       str          — stated hometown
        food_spicy:     bool         — True=likes spicy, False=doesn't
        family_members: list[str]    — family members mentioned
        work_desc:      str          — brief work description fragment
    """
    facts: dict = {}
    if not recent_replies:
        return facts
    window = list(recent_replies)[-5:]
    combined = " ".join(window)

    # ── Travel: places mentioned ─────────────────────────────────────────────────
    _tv: list = []
    for _place in _WM_KNOWN_PLACES:
        if _place in combined and _place not in _tv:
            _tv.append(_place)
    if _tv:
        facts["travel_visited"] = _tv

    # Travel: explicitly stated favourite / most memorable
    for _reply in window:
        for _place in _WM_KNOWN_PLACES:
            if (
                f"最喜欢{_place}" in _reply
                or f"最难忘的是在{_place}" in _reply
                or f"最难忘的是{_place}" in _reply
                or f"觉得{_place}最" in _reply
            ):
                facts["travel_fav"] = _place
                break

    # ── Place / home ─────────────────────────────────────────────────────────────
    for _reply in window:
        for _place in _WM_KNOWN_PLACES:
            if f"我住在{_place}" in _reply or f"住在{_place}" in _reply:
                facts["city_now"] = _place
            if f"我是{_place}人" in _reply or f"我老家在{_place}" in _reply:
                facts["hometown"] = _place

    # ── Food / spicy ─────────────────────────────────────────────────────────────
    # Check negation first — "不太能吃辣" contains "能吃辣" so order matters.
    if any(m in combined for m in ("不太能吃辣", "不能吃辣", "不喜欢辣", "有点怕辣")):
        facts["food_spicy"] = False
    elif any(m in combined for m in ("能吃辣", "挺能吃辣", "很能吃辣", "喜欢吃辣", "很喜欢辣")):
        facts["food_spicy"] = True

    # ── Family ───────────────────────────────────────────────────────────────────
    _fam_members = ("姐姐", "哥哥", "妹妹", "弟弟", "女儿", "儿子", "孩子")
    for _reply in window:
        for _member in _fam_members:
            if f"有{_member}" in _reply or f"我{_member}" in _reply:
                if "family_members" not in facts:
                    facts["family_members"] = []
                if _member not in facts["family_members"]:
                    facts["family_members"].append(_member)

    # ── Work ─────────────────────────────────────────────────────────────────────
    import re as _re_wm
    for _reply in window:
        _wm_match = _re_wm.search(r"我(?:是做|做)([\u4e00-\u9fff]{2,10})(?:的|工作|，|。)", _reply)
        if _wm_match:
            facts["work_desc"] = _wm_match.group(0).rstrip("，。") + "。"
            break

    return facts


def _answer_from_working_memory(text: str, facts: dict, persona: Optional[dict]) -> Optional[tuple]:
    """
    Derive a persona answer from working-memory facts extracted from recent replies.
    Returns (zh, en) tuple or None if no relevant fact is found.
    Pure function — does not modify facts or cs.

    Sourcing priority: travel_fav > travel_visited > food_spicy > hometown > city_now > family.
    """
    if not facts or not text:
        return None
    t = text.strip().rstrip("？?！!。，, ")

    # ── Travel: favourite place ───────────────────────────────────────────────────
    if "最喜欢" in t and any(k in t for k in ("地方", "哪里", "哪儿", "哪个")):
        fav = facts.get("travel_fav")
        visited = facts.get("travel_visited") or []
        if fav:
            return (f"我觉得{fav}最难忘，那里真的很特别。", f"I think {fav} is the most memorable — it's really special.")
        if len(visited) >= 2:
            return (f"我去过{visited[0]}和{visited[1]}，最喜欢{visited[0]}。", "")
        if len(visited) == 1:
            return (f"我去过的地方里，最喜欢{visited[0]}。", "")

    # ── Travel: visited places ────────────────────────────────────────────────────
    if any(m in t for m in ("去过哪里", "去过哪些", "去过哪", "旅游过")):
        visited = facts.get("travel_visited") or []
        if visited:
            return (f"我去过{'和'.join(visited[:3])}，都挺有意思的。", "")

    # ── Food: spicy preference ────────────────────────────────────────────────────
    if "喜欢辣" in t or ("辣" in t and "喜欢" in t):
        spicy = facts.get("food_spicy")
        if spicy is True:
            return ("我挺能吃辣的，还挺喜欢。", "I can handle spicy food pretty well — I like it.")
        if spicy is False:
            return ("我不太能吃辣，有点怕辣。", "I can't really handle spicy food.")

    # ── Place: hometown ───────────────────────────────────────────────────────────
    if any(m in t for m in ("老家", "家乡", "是哪里人")):
        hometown = facts.get("hometown")
        if hometown:
            return (f"我老家在{hometown}。", f"My hometown is {hometown}.")

    # ── Place: current city ───────────────────────────────────────────────────────
    if any(m in t for m in ("住在哪", "住哪", "现在住")):
        city = facts.get("city_now")
        if city:
            return (f"我住在{city}。", f"I live in {city}.")

    # ── Family ────────────────────────────────────────────────────────────────────
    if any(m in t for m in ("有没有孩子", "有孩子", "有没有姐", "有没有哥", "有没有妹", "有没有弟")):
        members = facts.get("family_members") or []
        if members:
            return (f"我家里有{members[0]}。", "")

    return None


def _infer_question_topic_engine(text: str) -> Optional[str]:
    """
    Infer which engine a learner's question belongs to, based on the question text.
    Used by E4 Initiative Follow for all answer-source tiers: mirror (via working memory),
    and direct-persona (static facts).  Returns an engine string or None when the
    question cannot be reliably classified.
    Pure function — no side effects.
    """
    import re as _re_iqte
    # Collapse whitespace between CJK characters so spaced ASR forms like
    # "重 庆 有 什么 特别" are treated the same as "重庆有什么特别".
    t = _re_iqte.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", (text or ""))
    t = t.strip().rstrip("？?！!。，, ")
    if not t:
        return None
    # Place-feature / place-food questions: asked about a place, keep in place engine.
    # Checked before food so "成都有什么好吃的" routes to place, not food.
    if _is_place_feature_question(t) or _is_place_food_question(t):
        return "place"
    # Cooking questions: "你做什么菜" routes to food, not work.
    # Checked before work so the "做什么" keyword below does not capture it.
    if _is_cooking_question(t):
        return "food"
    # Travel
    if any(k in t for k in ("最喜欢", "去过哪", "旅游过", "旅行", "哪个地方", "哪里好玩")):
        return "travel"
    # Generic food (not about a specific place)
    if any(k in t for k in ("喜欢辣", "辣", "吃什么", "喜欢吃", "食物")):
        return "food"
    # Place / hometown
    if any(k in t for k in ("老家", "家乡", "住哪", "住在哪", "现在住", "是哪里人")):
        return "place"
    # Work
    if any(k in t for k in ("工作", "做什么", "职业", "上班")):
        return "work"
    # Family
    if any(k in t for k in ("家里有", "几口人", "家人", "兄弟", "姐妹", "父母", "孩子", "结婚", "兄弟姐妹")):
        return "family"
    # Hobby
    if any(k in t for k in ("爱好", "兴趣", "喜欢做什么")):
        return "hobby"
    return None


# Backward-compatible alias: existing tests and call sites that reference the old name
# continue to work while new code uses the neutral name.
_infer_wm_topic_engine = _infer_question_topic_engine


def _topic_aware_honest_fallback(t: str, persona: Optional[dict]) -> Optional[tuple]:
    """
    Topic-aware honest acknowledgment for questions the persona cannot specifically answer.
    Returns (zh, en) or None. Placed BEFORE the generic '电脑角色' limitation disclaimer so the
    learner receives a conversational response that stays in topic domain.
    """
    if not t:
        return None
    _vl  = (persona or {}).get("voice_lines") or {}
    _fcts = (persona or {}).get("discoverable_facts") or {}

    # Travel / place: favourite preference
    if "最喜欢" in t and any(k in t for k in ("地方", "哪里", "哪儿", "哪个")):
        _tvl = (_vl.get("travel") or "").rstrip("。，")
        _suffix = f"，{_tvl[:20]}。" if _tvl else "，每个地方都有自己的特点。"
        return (f"这个问题不好说{_suffix}", "That's hard to say… but I enjoy travelling.")

    # Food: spicy
    if "喜欢辣" in t or ("辣" in t and "喜欢" in t):
        _fvl = _vl.get("food") or ""
        if _fvl:
            return (f"我呢，{_fvl}", "")
        return ("我能吃一点辣，但不是特别能吃。", "I can eat a little spicy food, but not too much.")

    # Food: general preference
    if any(k in t for k in ("喜欢吃", "最爱吃", "爱吃什么")):
        _ff = _fcts.get("food") or ""
        if _ff:
            return (_ff[:40].rstrip("，") + "。", "")
        return ("我挺喜欢吃东西的，各种口味都能接受。", "I quite enjoy food.")

    # Work preference
    if "工作" in t and any(k in t for k in ("喜欢", "怎么样", "好不好")):
        return ("这个工作还挺有意思，学到了不少东西。", "The work is pretty interesting — I've learned a lot.")

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


# MandarinOS-style EN gloss normalizer (ZH → EN direction).
# Fixes misleading literal translations produced by machine engines
# (e.g. physical-distance idioms glossed as emotional closeness).
_EN_GLOSS_FIXES: list[tuple] = [
    # "nearest / closest" in physical-distance phrasing when it means emotional
    (re.compile(r"\bnearest to (my |the )?(wife|husband|mom|dad|mother|father|parents|family)\b", re.I),
     lambda m: f"closest to {m.group(1) or ''}{m.group(2)}"),
    (re.compile(r"\bclosest to (my |the )?(wife|spouse)\b", re.I),
     lambda m: f"closest to {m.group(1) or ''}wife"),
    # Formal family-member words that machine translators may not convert
    (re.compile(r"\bspouse\b", re.I), "wife/husband"),
]


def _naturalize_en_gloss(en: str) -> str:
    """Apply MandarinOS-style post-processing to a ZH→EN machine gloss."""
    s = (en or "").strip()
    for fix in _EN_GLOSS_FIXES:
        pattern, replacement = fix
        if callable(replacement):
            s = pattern.sub(replacement, s)
        else:
            s = pattern.sub(replacement, s)
    return s


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
            s = _naturalize_en_gloss(str(out).strip())
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


# ── Scorecard helpers (session summary only — not runtime scoring) ──────────
# These functions are called only by /api/end_session and never touch the
# conversation selector, frame engine, or any turn-level runtime logic.

_PROGRESS_HISTORY_PATH = REPO_ROOT / "data" / "progress_history.json"
_BETA_ADMIN_TOKEN = (os.environ.get("MANDARINOS_BETA_ADMIN_TOKEN") or "beta_export_local").strip()


def _scorecard_flow(total_turns: int) -> dict:
    n = total_turns
    if n <= 5:
        label = "Short"
    elif n <= 10:
        label = "Holding"
    elif n <= 18:
        label = "Sustained"
    else:
        label = "Natural"
    return {"raw": n, "label": label}


def _scorecard_recovery(
    recovery_uses: int,
    successful_recoveries: int,
    conversational_recoveries: int = 0,
    successful_conversational_recoveries: int = 0,
) -> dict:
    uses = recovery_uses
    phrase_successes = min(successful_recoveries, uses) if uses > 0 else 0
    conv = max(0, conversational_recoveries)
    conv_success = (
        min(successful_conversational_recoveries, conv)
        if conv > 0
        else max(0, successful_conversational_recoveries)
    )
    rate = round(phrase_successes / uses, 3) if uses > 0 else None
    total_moments = uses + conv
    total_success = phrase_successes + conv_success

    if total_moments == 0:
        label = "Smooth"
    elif conv > 0 and uses == 0:
        if conv_success >= conv:
            label = "Got back on track"
        elif conv_success >= 1:
            label = "Kept going after confusion"
        else:
            label = "Tried to recover"
    elif uses <= 3 and rate is not None and rate >= 0.70 and conv_success >= 1:
        label = "Recovered smoothly"
    elif uses <= 3 and rate is not None and rate >= 0.70:
        label = "Recovered smoothly"
    elif total_moments <= 7 and total_success >= max(1, total_moments // 2):
        label = "Recovered with effort"
    elif uses <= 7 and rate is not None and rate >= 0.50:
        label = "Recovered with effort"
    else:
        label = "Struggling to recover"

    display_summary = _recovery_display_summary(
        uses, phrase_successes, conv, conv_success,
    )

    return {
        "raw_uses": uses,
        "raw_successes": phrase_successes,
        "conversational_recoveries": conv,
        "successful_conversational_recoveries": conv_success,
        "display_summary": display_summary,
        "rate": rate,
        "label": label,
    }


def _recovery_display_summary(
    phrase_uses: int,
    phrase_successes: int,
    conv: int,
    conv_success: int,
) -> str:
    """User-facing recovery line — phrase recoveries vs learner self-repair."""
    if phrase_uses == 0 and conv == 0:
        return "0 recovery moments"
    parts: list = []
    if phrase_uses > 0:
        parts.append(
            f"{phrase_uses} phrase recover{'y' if phrase_uses == 1 else 'ies'}"
            f" ({phrase_successes} successful)"
        )
    if conv > 0:
        if conv_success >= conv:
            parts.append(
                f"{conv} time{'s' if conv != 1 else ''} you got back on track"
            )
        else:
            parts.append(
                f"{conv} self-repair moment{'s' if conv != 1 else ''}"
                f" ({conv_success} continued)"
            )
    return " · ".join(parts)


def _scorecard_support(suggestion_clicks: int, card_opens: int, total_turns: int) -> dict:
    support_uses = suggestion_clicks + card_opens
    per_turn = round(support_uses / total_turns, 3) if total_turns > 0 else 0.0
    if per_turn <= 0.15:
        label = "Independent"
    elif per_turn <= 0.40:
        label = "Lightly supported"
    elif per_turn <= 0.80:
        label = "Assisted"
    else:
        label = "Heavily guided"
    return {"raw_uses": support_uses, "per_turn": per_turn, "label": label}


def _scorecard_participation(questions_asked: int) -> dict:
    n = questions_asked
    if n == 0:
        label = "Responding only"
    elif n <= 2:
        label = "Occasional questions"
    elif n <= 5:
        label = "Active participant"
    else:
        label = "Leading the conversation"
    return {"raw": n, "label": label}


def _scorecard_depth(depth_responses: int) -> dict:
    n = depth_responses
    if n == 0:
        label = "Basic answers"
    elif n <= 2:
        label = "Some extension"
    elif n <= 5:
        label = "Explaining ideas"
    else:
        label = "Expressive speaker"
    return {"raw": n, "label": label}


def _scorecard_stability(unmatched_responses: int, total_turns: int,
                          soft_unmatched: int = 0) -> dict:
    # Effective unmatched = hard fails (full weight) + soft fails (0.5 weight).
    # Soft fails carry partial meaning and are a much weaker signal of breakdown.
    effective = unmatched_responses + round(soft_unmatched * 0.5)
    n    = unmatched_responses
    soft = soft_unmatched
    rate = round(effective / total_turns, 3) if total_turns > 0 else 0.0
    if rate <= 0.10:
        label = "Stable"
    elif rate <= 0.25:
        # A few unclear turns in a long session — conversation held together.
        label = "Conversation stayed on track"
    elif rate <= 0.45:
        label = "Some friction"
    elif rate <= 0.60:
        label = "Unstable"
    else:
        label = "Breaking down"
    return {"raw_unmatched": n, "raw_soft_unmatched": soft, "effective_unmatched": effective,
            "rate": rate, "label": label}


def _derive_conversation_signals(sess: dict) -> dict:
    """
    Shared interpretive heuristics for scorecard + progress (not routing).
    Measures survivability, persistence, and initiative — not linguistic perfection.
    """
    total_turns           = max(0, int(sess.get("total_turns",             0) or 0))
    questions_asked       = max(0, int(sess.get("questions_asked",         0) or 0))
    depth_responses       = max(0, int(sess.get("depth_responses",         0) or 0))
    unmatched_responses   = max(0, int(sess.get("unmatched_responses",     0) or 0))
    soft_unmatched        = max(0, int(sess.get("soft_unmatched_responses", 0) or 0))
    recovery_uses         = max(0, int(sess.get("recovery_uses",           0) or 0))
    successful_recoveries = max(0, int(sess.get("successful_recoveries",   0) or 0))
    conversational_recoveries = max(0, int(sess.get("conversational_recoveries", 0) or 0))
    successful_conversational_recoveries = max(
        0, int(sess.get("successful_conversational_recoveries", 0) or 0),
    )

    effective_unclear = unmatched_responses + round(soft_unmatched * 0.5)

    turbulence_survived = (
        total_turns >= 12
        and effective_unclear >= 2
        and total_turns > effective_unclear * 3
    )

    continued_after_ambiguity = (
        successful_recoveries >= 1
        or successful_conversational_recoveries >= 1
        or conversational_recoveries >= 1
        or (recovery_uses >= 1 and successful_recoveries > 0)
        or (
            effective_unclear >= 1
            and total_turns >= 10
            and (questions_asked >= 1 or depth_responses >= 1)
        )
    )

    reciprocity = questions_asked >= 2
    strong_reciprocity = (
        questions_asked >= 3
        or (questions_asked >= 2 and depth_responses >= 2)
    )

    extended_imperfect = depth_responses >= 2 and effective_unclear >= 1

    conversational_persistence = (
        total_turns >= 15
        and (turbulence_survived or continued_after_ambiguity)
    )

    sustained_strict = (
        total_turns >= 20
        and questions_asked >= 3
        and unmatched_responses <= 5
    )

    sustained_messy = (
        total_turns >= 16
        and (questions_asked >= 2 or depth_responses >= 3)
        and (turbulence_survived or continued_after_ambiguity)
    )

    sustained = sustained_strict or sustained_messy

    led_conversation = questions_asked >= 2 and total_turns >= 4

    strong_initiative = (
        sustained
        or strong_reciprocity
        or (total_turns >= 12 and questions_asked >= 2)
        or (total_turns >= 14 and depth_responses >= 3)
        or (conversational_persistence and questions_asked >= 1)
    )

    communicative_ambition = (
        total_turns >= 10
        and effective_unclear >= 3
        and (
            questions_asked >= 1
            or depth_responses >= 1
            or soft_unmatched >= 3
        )
    )

    return {
        "total_turns":                 total_turns,
        "questions_asked":             questions_asked,
        "depth_responses":             depth_responses,
        "effective_unclear":           effective_unclear,
        "turbulence_survived":           turbulence_survived,
        "continued_after_ambiguity":   continued_after_ambiguity,
        "reciprocity":                 reciprocity,
        "strong_reciprocity":          strong_reciprocity,
        "extended_imperfect":          extended_imperfect,
        "conversational_persistence":  conversational_persistence,
        "sustained":                   sustained,
        "sustained_strict":            sustained_strict,
        "sustained_messy":             sustained_messy,
        "led_conversation":            led_conversation,
        "strong_initiative":           strong_initiative,
        "communicative_ambition":      communicative_ambition,
    }


def _scorecard_conversation_capability(sess: dict) -> dict:
    """
    Lightweight interpretation layer: product-aligned capability lines and headline
    from session counters.  Does not affect conversation routing.
    """
    sig = _derive_conversation_signals(sess)
    suggestion_clicks = max(0, int(sess.get("suggestion_clicks", 0) or 0))
    card_opens        = max(0, int(sess.get("card_opens",        0) or 0))
    support_uses      = suggestion_clicks + card_opens

    capability_lines: list = []
    progress_lines: list = []

    if sig["sustained"]:
        capability_lines.append(
            "You kept a real conversation going, even when some turns were messy."
        )
    elif sig["conversational_persistence"]:
        capability_lines.append(
            "You stayed engaged through a longer conversation, even with unclear moments."
        )

    if sig["led_conversation"]:
        capability_lines.append(
            "You didn\u2019t just answer \u2014 you helped drive the conversation forward."
        )
    elif sig["strong_reciprocity"]:
        capability_lines.append(
            "You brought curiosity back into the conversation with questions of your own."
        )

    if sig["turbulence_survived"]:
        capability_lines.append(
            "You kept the conversation alive even when things became unclear."
        )

    if sig["continued_after_ambiguity"]:
        progress_lines.append(
            "You continued communicating through difficult moments instead of stopping."
        )
    elif sig["effective_unclear"] > 0 and sig["total_turns"] >= 12:
        progress_lines.append(
            "A few unclear turns did not stop the conversation."
        )

    if sig["extended_imperfect"]:
        capability_lines.append(
            "You stayed engaged through several imperfect exchanges and kept trying to express yourself."
        )
    elif sig.get("communicative_ambition"):
        capability_lines.append(
            "You kept pushing to communicate even when your wording was messy \u2014 that takes real conversational courage."
        )
    elif sig["depth_responses"] >= 2:
        capability_lines.append(
            f"You gave {sig['depth_responses']} extended answer"
            f"{'' if sig['depth_responses'] == 1 else 's'} with more detail."
        )

    headline = None
    if sig["sustained"] and sig["strong_reciprocity"] and sig["turbulence_survived"]:
        headline = (
            "You stayed inside a real conversation \u2014 through noise, questions, and recovery."
        )
    elif sig["sustained"] and sig["questions_asked"] >= 5:
        headline = (
            "You had a sustained, socially active conversation with initiative and resilience."
        )
    elif sig["sustained"]:
        headline = "You kept a sustained conversation going and asked questions back."
    elif sig["conversational_persistence"] and sig["led_conversation"]:
        headline = (
            "You helped move the conversation forward and stayed in it through imperfect turns."
        )
    elif sig["total_turns"] >= 12 and sig["led_conversation"]:
        headline = "You kept the conversation going and helped move it forward."
    elif sig["turbulence_survived"] and sig["total_turns"] >= 10:
        headline = "You stayed in the conversation even when it got turbulent."

    return {
        "headline":           headline,
        "capability_lines":   capability_lines,
        "progress_lines":     progress_lines,
        "strong_initiative":  sig["strong_initiative"],
        "support_uses":       support_uses,
        "signals":            {
            "turbulence_survived":          sig["turbulence_survived"],
            "continued_after_ambiguity":    sig["continued_after_ambiguity"],
            "conversational_persistence":   sig["conversational_persistence"],
        },
    }


def _compute_scorecard(sess: dict) -> dict:
    """Compute all six scorecard metrics from a raw session object.
    All fields default to 0 if absent; total_turns=0 does not crash."""
    total_turns           = max(0, int(sess.get("total_turns",             0) or 0))
    recovery_uses         = max(0, int(sess.get("recovery_uses",           0) or 0))
    successful_recoveries = max(0, int(sess.get("successful_recoveries",   0) or 0))
    conversational_recoveries = max(0, int(sess.get("conversational_recoveries", 0) or 0))
    successful_conversational_recoveries = max(
        0, int(sess.get("successful_conversational_recoveries", 0) or 0),
    )
    suggestion_clicks     = max(0, int(sess.get("suggestion_clicks",       0) or 0))
    card_opens            = max(0, int(sess.get("card_opens",              0) or 0))
    questions_asked       = max(0, int(sess.get("questions_asked",         0) or 0))
    depth_responses       = max(0, int(sess.get("depth_responses",         0) or 0))
    unmatched_responses   = max(0, int(sess.get("unmatched_responses",     0) or 0))
    soft_unmatched        = max(0, int(sess.get("soft_unmatched_responses", 0) or 0))
    turbulence_events     = max(0, int(sess.get("turbulence_events",        0) or 0))
    return {
        "flow":          _scorecard_flow(total_turns),
        "recovery":      _scorecard_recovery(
            recovery_uses,
            successful_recoveries,
            conversational_recoveries,
            successful_conversational_recoveries,
        ),
        "support":       _scorecard_support(suggestion_clicks, card_opens, total_turns),
        "participation": _scorecard_participation(questions_asked),
        "depth":         _scorecard_depth(depth_responses),
        "stability":     _scorecard_stability(unmatched_responses, total_turns, soft_unmatched),
        "conversation_capability": _scorecard_conversation_capability(sess),
        # Informational turbulence signal — not used for promotion/demotion.
        # Sources: ASR hard/soft rejects, strong confusion signals, repair loops, challenge text reveals.
        "turbulence": {
            "raw_events":  turbulence_events,
            "per_turn":    round(turbulence_events / max(1, total_turns), 3),
            "label":       "informational",
        },
    }


def _conversation_stability_score(
    stability: dict,
    total_turns: int,
    sess: Optional[dict] = None,
) -> Optional[int]:
    """
    Return 0–100 progress stability score for the Progress tab graph/table.
    Reflects conversational turbulence (unclear/repair moments), not collapse alone.
    Does not alter _scorecard_stability row labels on the session scorecard.
    """
    if total_turns < 2:
        return None

    # Bare rate-only path (no session counters) — used in a few unit comparisons.
    if not sess:
        rate = stability.get("rate")
        if rate is None:
            return None
        try:
            rate_f = float(rate)
        except (TypeError, ValueError):
            return None
        return round(100 * (1 - min(max(rate_f, 0.0), 1.0)))

    hard = max(0, int(sess.get("unmatched_responses", 0) or 0))
    soft = max(0, int(sess.get("soft_unmatched_responses", 0) or 0))
    recovery_uses = max(0, int(sess.get("recovery_uses", 0) or 0))
    conv_rec = max(0, int(sess.get("conversational_recoveries", 0) or 0))
    effective_unclear = hard + round(soft * 0.5)
    repair_moments = recovery_uses + conv_rec

    # Check friction signals before the perfect-score early-return so friction
    # penalties are applied even when unmatched_responses and repair_moments are 0.
    _friction_early = (sess.get("friction_signals") or {}) if isinstance(sess, dict) else {}
    _has_friction_early = isinstance(_friction_early, dict) and (
        _friction_early.get("repeated_generic_fallback", 0) >= 2
        or _friction_early.get("near_duplicate_persona_replies", 0) >= 2
        or _friction_early.get("premature_closing_after_confusion", 0) >= 1
        or _friction_early.get("learner_frustration_count", 0) >= 2
        or _friction_early.get("has_significant_friction", False)
    )

    if effective_unclear == 0 and repair_moments == 0 and not _has_friction_early:
        return 100

    per_event = hard * 8 + round(soft * 0.5) * 5
    if total_turns >= 20:
        per_event = round(per_event * 0.85)
    if total_turns >= 30:
        per_event = round(per_event * 0.85)

    rate_penalty = round(
        50 * min(effective_unclear / max(total_turns, 1), 0.5),
    )
    repair_penalty = recovery_uses * 4 + conv_rec * 2
    short_penalty = 6 if total_turns < 12 and effective_unclear >= 1 else 0
    deduction = per_event + rate_penalty + repair_penalty + short_penalty

    credit = 0
    sig = _derive_conversation_signals(sess)
    if effective_unclear >= 1 and sig["continued_after_ambiguity"]:
        credit += 4
    if sig["turbulence_survived"]:
        credit += 4
    credit = min(8, credit)

    score = 100 - deduction + credit

    if effective_unclear >= 1:
        score = min(score, 92)
    if effective_unclear >= 2:
        score = min(score, 88 if total_turns >= 15 else 79)
    if effective_unclear >= 4:
        score = min(score, 72)
    if repair_moments >= 3:
        score = min(score, 75)

    # Qualitative friction penalty: repeated misunderstanding not captured by
    # unmatched_responses alone (e.g. repeated generic fallback, premature closing).
    friction = (sess.get("friction_signals") or {}) if isinstance(sess, dict) else {}
    if isinstance(friction, dict):
        if friction.get("repeated_generic_fallback", 0) >= 2:
            score = min(score, 70)
        if friction.get("near_duplicate_persona_replies", 0) >= 2:
            score = min(score, 75)
        if friction.get("premature_closing_after_confusion", 0) >= 1:
            score = min(score, 80)
        if friction.get("learner_frustration_count", 0) >= 2:
            score = min(score, 78)
        if friction.get("has_significant_friction", False):
            score = min(score, 75)

    return max(0, min(100, round(score)))


def _count_learning_support_actions(sess: dict) -> int:
    """Support actions for Progress Support tier — excludes card exploration and phrase recovery."""
    return sum(
        max(0, int(sess.get(k, 0) or 0))
        for k in (
            "suggestion_clicks",
            "hint_clicks",
            "display_en_clicks",
            "display_py_clicks",
            "translation_help_uses",
        )
    )


def _format_progress_support_label(sess: dict) -> str:
    """Progress-table Support tier — encouraging, not punitive."""
    n = _count_learning_support_actions(sess)
    if n == 0:
        return "None"
    if n <= 2:
        return "Light"
    if n <= 5:
        return "Moderate"
    return "Heavy"


def _format_progress_flow_label(
    *,
    score: Optional[int],
    unclear_turns: int,
    total_turns: int,
    turbulence_survived: bool,
    continued_after_ambiguity: bool,
    recovery_uses: int = 0,
    conversational_recoveries: int = 0,
    soft_unclear_turns: int = 0,
    friction_signals: Optional[dict] = None,
) -> str:
    """Progress-table Flow label — turbulence signals first, not inflated score.

    friction_signals (optional): output of compute_friction_signals() stored on the
    session record.  When significant friction is detected, prevents "Smooth" or
    "Stable" from being assigned even if unmatched_responses count is low.
    """
    repair_moments = recovery_uses + conversational_recoveries
    effective_unclear = unclear_turns + round(soft_unclear_turns * 0.5)
    has_turbulence = effective_unclear > 0 or repair_moments > 0

    # Qualitative friction check — prevents over-optimistic labels.
    _friction = friction_signals or {}
    _has_significant_friction = bool(_friction.get("has_significant_friction", False))
    _repeated_generic = int(_friction.get("repeated_generic_fallback", 0))
    _premature_closing = int(_friction.get("premature_closing_after_confusion", 0))

    if not has_turbulence and not _has_significant_friction:
        if score is None:
            return "—"
        # Reserve "Smooth" for sessions long enough that a clean run is meaningful.
        if score >= 95 and total_turns >= 8:
            return "Smooth"
        if score >= 95 and total_turns < 8:
            return "Clean short session"
        if score >= 80:
            return "Stable"
        return "Difficult but continued"

    # Friction pushes the session toward turbulence even if counters look OK.
    if _repeated_generic >= 2 or _premature_closing >= 2:
        return "Repeated misunderstanding"
    if _has_significant_friction and not has_turbulence:
        return "Friction detected"

    if repair_moments >= 3 or effective_unclear >= 4:
        return "Worked through turbulence"
    if turbulence_survived or (total_turns >= 15 and effective_unclear >= 2):
        return "Messy but sustained"
    if effective_unclear >= 2 or repair_moments >= 2:
        return "Messy but sustained"
    if continued_after_ambiguity or total_turns >= 8:
        return "Stayed on track"
    return "Difficult but continued"


def _format_progress_recovery_label(
    *,
    unclear_turns: int,
    recovery_uses: int,
    recovery_success_rate: Optional[float],
    conversational_recoveries: int,
    successful_conversational_recoveries: int,
    continued_after_ambiguity: bool,
    total_turns: int,
    questions_asked: int = 0,
) -> str:
    """Progress-table Recovery cell — aligned with scorecard self-repair story."""
    has_self_repair = successful_conversational_recoveries > 0
    has_conv_attempts = conversational_recoveries > 0
    has_phrase_support = recovery_uses > 0

    if has_phrase_support and has_self_repair:
        return "Used support + self-recovered"
    if has_phrase_support:
        if recovery_success_rate is not None:
            pct = round(float(recovery_success_rate) * 100)
            return f"App-assisted ({pct}%)" if pct < 100 else "App-assisted"
        return "App-assisted"
    if has_self_repair:
        if successful_conversational_recoveries >= 2:
            return "Self-recovered often"
        return "Self-recovered"
    if has_conv_attempts:
        return "Kept going"
    if unclear_turns > 0 and continued_after_ambiguity:
        if questions_asked >= 2 and total_turns >= 12:
            return "Kept going"
        return "Stayed on track"
    if unclear_turns == 0 and recovery_uses == 0:
        return "No repairs needed"
    if unclear_turns > 0:
        return "Stayed on track"
    return "No system help"


def _format_progress_stability_label(
    *,
    score: Optional[int],
    unclear_turns: int,
    total_turns: int,
    turbulence_survived: bool,
    continued_after_ambiguity: bool,
    recovery_uses: int = 0,
    conversational_recoveries: int = 0,
    soft_unclear_turns: int = 0,
) -> str:
    """Legacy alias — label-only flow (no numeric prefix). Prefer flow_display_label."""
    return _format_progress_flow_label(
        score=score,
        unclear_turns=unclear_turns,
        total_turns=total_turns,
        turbulence_survived=turbulence_survived,
        continued_after_ambiguity=continued_after_ambiguity,
        recovery_uses=recovery_uses,
        conversational_recoveries=conversational_recoveries,
        soft_unclear_turns=soft_unclear_turns,
    )


def _build_progress_snapshot(
    sess: dict,
    metrics: dict,
    *,
    tier: str = "standard",
    persona_id: Optional[str] = None,
    duration_seconds: int = 0,
) -> dict:
    """Compact progress record from existing session counters and scorecard metrics."""
    total_turns           = max(0, int(sess.get("total_turns",             0) or 0))
    recovery_uses         = max(0, int(sess.get("recovery_uses",           0) or 0))
    successful_recoveries = max(0, int(sess.get("successful_recoveries",   0) or 0))
    suggestion_clicks     = max(0, int(sess.get("suggestion_clicks",       0) or 0))
    card_opens            = max(0, int(sess.get("card_opens",              0) or 0))
    conversational_recoveries = max(0, int(sess.get("conversational_recoveries", 0) or 0))
    successful_conversational_recoveries = max(
        0, int(sess.get("successful_conversational_recoveries", 0) or 0),
    )
    display_en_clicks     = max(0, int(sess.get("display_en_clicks",     0) or 0))
    display_py_clicks     = max(0, int(sess.get("display_py_clicks",     0) or 0))
    hint_clicks           = max(0, int(sess.get("hint_clicks",           0) or 0))
    translation_help_uses = max(0, int(sess.get("translation_help_uses", 0) or 0))
    questions_asked       = max(0, int(sess.get("questions_asked",         0) or 0))
    depth_responses       = max(0, int(sess.get("depth_responses",         0) or 0))
    unmatched_responses   = max(0, int(sess.get("unmatched_responses",     0) or 0))
    soft_unmatched        = max(0, int(sess.get("soft_unmatched_responses", 0) or 0))
    mode                  = (sess.get("mode") or "normal").strip().lower()
    session_id            = (sess.get("session_id") or "").strip()
    learner_id            = (sess.get("learner_id") or "").strip() or None

    engines = sess.get("engines_used")
    if not isinstance(engines, list):
        engines = []

    stability = metrics.get("stability") or {}
    recovery  = metrics.get("recovery") or {}

    if recovery_uses > 0:
        recovery_success_rate = recovery.get("rate")
    else:
        recovery_success_rate = None

    try:
        created_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        created_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    tier_norm = (tier or "standard").strip().lower()
    if tier_norm not in ("standard", "premium"):
        tier_norm = "standard"

    prog_sig = _derive_conversation_signals(sess)

    stability_score = _conversation_stability_score(
        stability, total_turns, sess,
    )
    recovery_display_label = _format_progress_recovery_label(
        unclear_turns=unmatched_responses,
        recovery_uses=recovery_uses,
        recovery_success_rate=recovery_success_rate,
        conversational_recoveries=conversational_recoveries,
        successful_conversational_recoveries=successful_conversational_recoveries,
        continued_after_ambiguity=prog_sig["continued_after_ambiguity"],
        total_turns=total_turns,
        questions_asked=questions_asked,
    )
    _sess_friction = sess.get("friction_signals") or {}
    flow_display_label = _format_progress_flow_label(
        score=stability_score,
        unclear_turns=unmatched_responses,
        total_turns=total_turns,
        turbulence_survived=prog_sig["turbulence_survived"],
        continued_after_ambiguity=prog_sig["continued_after_ambiguity"],
        recovery_uses=recovery_uses,
        conversational_recoveries=conversational_recoveries,
        soft_unclear_turns=soft_unmatched,
        friction_signals=_sess_friction if isinstance(_sess_friction, dict) else None,
    )
    support_display_label = _format_progress_support_label(sess)
    stability_display_label = flow_display_label

    return {
        "session_id":                    session_id,
        "learner_id":                    learner_id,
        "created_at":                    created_at,
        "tier":                          tier_norm,
        "persona_id":                    (persona_id or sess.get("persona_id") or "").strip() or None,
        "mode":                          mode,
        "duration_seconds":              max(0, int(duration_seconds or 0)),
        "total_turns":                   total_turns,
        "questions_asked":               questions_asked,
        "recovery_uses":                 recovery_uses,
        "successful_recoveries":         successful_recoveries,
        "conversational_recoveries":     conversational_recoveries,
        "successful_conversational_recoveries": successful_conversational_recoveries,
        "unclear_turns":                 unmatched_responses,
        "depth_responses":               depth_responses,
        "engines_used":                  engines,
        "suggestion_clicks":             suggestion_clicks,
        "card_opens":                    card_opens,
        "display_en_clicks":             display_en_clicks,
        "display_py_clicks":             display_py_clicks,
        "hint_clicks":                   hint_clicks,
        "translation_help_uses":         translation_help_uses,
        "conversation_stability_score":  stability_score,
        "recovery_success_rate":         recovery_success_rate,
        "recovery_display_label":        recovery_display_label,
        "flow_display_label":            flow_display_label,
        "support_display_label":         support_display_label,
        "stability_display_label":       stability_display_label,
        "card_exploration_count":        card_opens,
        "progress_signals": {
            "turbulence_survived":         prog_sig["turbulence_survived"],
            "continued_after_ambiguity":   prog_sig["continued_after_ambiguity"],
            "conversational_persistence":  prog_sig["conversational_persistence"],
            "communicative_ambition":      prog_sig.get("communicative_ambition", False),
        },
    }


def _append_progress_history(record: dict) -> None:
    """Append a challenge-mode session record to data/progress_history.json.
    Creates the file if absent; never overwrites existing records."""
    path = _PROGRESS_HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    history: list = []
    if path.is_file():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, list):
                history = parsed
        except Exception:
            history = []
    history.append(record)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


# ── HTTP Handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        # Lightweight version/health endpoint — returns deployed git SHA and branch.
        if path in ("/api/version", "/api/health"):
            _v: dict = {
                "branch": _git_branch,
                "sha": _git_sha,
                "sha_full": _git_sha_full,
                "sha_source": _git_sha_source,
                "status": "ok",
                "diag_enabled": _diag_enabled(),
                "normalizer": _diag_normalizer_name(),
            }
            data = json.dumps(_v, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

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

        if path == "/api/memory":
            learner_id = (qs.get("learner_id", ["default_learner"])[0] or "default_learner").strip()
            mem = (_lm_load(learner_id) if _lm_load and learner_id else None) or {}
            payload = {
                "ok": True,
                "learner_id": learner_id,
                "memory": mem,
                "is_first_time_beta_user": _is_first_time_beta_user(learner_id),
            }
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/progress/all":
            token = (qs.get("admin_token", [""])[0] or "").strip()
            if not _BETA_ADMIN_TOKEN or token != _BETA_ADMIN_TOKEN:
                self._json_error(403, "invalid or missing admin_token")
                return
            if not _ps_load_all:
                self._json_error(503, "progress store unavailable")
                return
            all_data = _ps_load_all()
            data = json.dumps({"ok": True, "learners": all_data}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # ── Session Intelligence admin export (Phase 0 Slice 4, read-only) ─────
        # Same admin_token gate as /api/progress/all.  Read-only: these
        # endpoints never write, modify, or delete any file.

        if path == "/api/sessions/list":
            token = (qs.get("admin_token", [""])[0] or "").strip()
            if not _BETA_ADMIN_TOKEN or token != _BETA_ADMIN_TOKEN:
                self._json_error(403, "invalid or missing admin_token")
                return
            sessions_root = Path(_DATA_DIR_EFFECTIVE) / "sessions"
            listing = []
            if sessions_root.is_dir():
                for p in sorted(sessions_root.rglob("*.json")):
                    try:
                        raw = p.read_text(encoding="utf-8")
                        rec = json.loads(raw)
                        if not isinstance(rec, dict):
                            continue
                        if rec.get("schema") != "session_record_v1":
                            continue
                        # relative path under sessions root only — no absolute FS paths
                        rel = p.relative_to(sessions_root)
                        listing.append({
                            "learner_id":            rec.get("learner_id"),
                            "session_id":            rec.get("session_id"),
                            "path_relative":         str(rel).replace("\\", "/"),
                            "schema_version":        rec.get("schema"),
                            "created_at":            rec.get("created_at"),
                            "persona_id":            rec.get("persona_id"),
                            "mode":                  rec.get("mode"),
                            "transcript_turn_count": len(rec.get("transcript") or []),
                            "file_size_bytes":       p.stat().st_size,
                            "modified_time":         datetime.datetime.fromtimestamp(
                                p.stat().st_mtime, tz=datetime.timezone.utc
                            ).isoformat(timespec="seconds"),
                        })
                    except Exception:
                        continue
            data = json.dumps(
                {"ok": True, "sessions_root": "data/sessions", "total_sessions": len(listing), "sessions": listing},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/sessions/get":
            token = (qs.get("admin_token", [""])[0] or "").strip()
            if not _BETA_ADMIN_TOKEN or token != _BETA_ADMIN_TOKEN:
                self._json_error(403, "invalid or missing admin_token")
                return
            learner_id = (qs.get("learner_id", [""])[0] or "").strip()
            session_id = (qs.get("session_id", [""])[0] or "").strip()
            if not learner_id:
                self._json_error(400, "missing learner_id")
                return
            if not session_id:
                self._json_error(400, "missing session_id")
                return
            # Security: reject IDs containing path-traversal or unsafe characters.
            # Only alphanumerics, hyphens, and underscores are allowed —
            # the same regex as session_intelligence._SAFE_LEARNER_ID / _SAFE_SESSION_ID.
            import re as _re
            if not _re.match(r'^[a-zA-Z0-9_\-]{1,64}$', learner_id):
                self._json_error(400, "invalid learner_id")
                return
            if not _re.match(r'^[a-zA-Z0-9_\-\.]{1,128}$', session_id):
                self._json_error(400, "invalid session_id")
                return
            session_file = Path(_DATA_DIR_EFFECTIVE) / "sessions" / learner_id / f"{session_id}.json"
            # Confirm the resolved path is still inside data/sessions/ (defence-in-depth)
            sessions_root = Path(_DATA_DIR_EFFECTIVE) / "sessions"
            try:
                session_file.resolve().relative_to(sessions_root.resolve())
            except ValueError:
                self._json_error(400, "invalid path")
                return
            if not session_file.is_file():
                self._json_error(404, "session not found")
                return
            try:
                raw = session_file.read_text(encoding="utf-8")
                rec = json.loads(raw)
            except Exception:
                self._json_error(500, "failed to read session file")
                return
            if not isinstance(rec, dict) or rec.get("schema") != "session_record_v1":
                self._json_error(422, "file exists but is not a valid session_record_v1")
                return
            data = json.dumps(rec, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        # ── end Session Intelligence admin export ─────────────────────────────

        if path == "/api/progress":
            learner_id = (qs.get("learner_id", [""])[0] or "").strip()
            if not learner_id:
                self._json_error(400, "missing learner_id")
                return
            if not _ps_load_snapshots:
                self._json_error(503, "progress store unavailable")
                return
            snapshots = _ps_load_snapshots(learner_id)
            data = json.dumps(
                {
                    "ok": True,
                    "learner_id": learner_id,
                    "snapshots": snapshots,
                    "is_first_time_beta_user": _is_first_time_beta_user(learner_id),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/capability":
            learner_id = (qs.get("learner_id", [""])[0] or "").strip()
            if not learner_id:
                self._json_error(400, "missing learner_id")
                return
            if not _ps_load_snapshots or not _ce_compute:
                self._json_error(503, "capability estimator unavailable")
                return
            snapshots = _ps_load_snapshots(learner_id)
            capability = _ce_compute(snapshots)
            data = json.dumps(
                {"ok": True, "learner_id": learner_id, "capability": capability},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/beta_profile":
            learner_id = (qs.get("learner_id", [""])[0] or "").strip()
            if not learner_id:
                self._json_error(400, "missing learner_id")
                return
            if not _bp_load_profile:
                self._json_error(503, "beta profile unavailable")
                return
            profile = _bp_load_profile(learner_id)
            data = json.dumps(
                {
                    "ok": True,
                    "learner_id": learner_id,
                    "profile": profile,
                    "is_first_time_beta_user": _is_first_time_beta_user(learner_id),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path.startswith("/runtime/"):
            file_path = RUNTIME_DIR / path[len("/runtime/"):]
            if (
                file_path.name == "recovery_phrases.runtime.json"
                and not file_path.is_file()
            ):
                payload = _recovery_phrases_runtime_payload()
                if payload:
                    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
        elif path.startswith("/data/"):
            # Curated datasets at repo root data/ (e.g. characters_1200.json master copy)
            file_path = REPO_ROOT / path.lstrip("/")
        elif path.startswith("/ui/") or path in ("/ui", "/ui/index.html"):
            rel = path[len("/ui/"):] if path.startswith("/ui/") else "index.html"
            file_path = UI_DIR / rel
        elif path.endswith(".json") and "/" not in path.lstrip("/"):
            file_path = REPO_ROOT / path.lstrip("/")
        elif path == "/":
            # Preserve the query string across the redirect so params like
            # ?diag=TOKEN survive (dropping it here disabled diagnostics: the
            # loaded page saw an empty location.search and never enabled AsrDiag).
            _loc = "/ui/index.html"
            if parsed.query:
                _loc += "?" + parsed.query
            self.send_response(302)
            self.send_header("Location", _loc)
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

        # ── ASR diagnostic trace collection (token-protected; not public) ─────
        # Receives a per-listen-cycle client bundle and appends it to the diag
        # store. Disabled (403) unless MANDARINOS_DIAG_TOKEN is set and matches
        # the X-Diag-Token header — raw speech transcripts may contain PII.
        if path == "/api/diag/asr-trace":
            if not _diag_enabled():
                self._json_error(404, "diagnostics disabled")
                return
            tok = (self.headers.get("X-Diag-Token") or "").strip()
            if tok != _DIAG_TOKEN:
                self._json_error(403, "invalid or missing diag token")
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                rec = json.loads(body)
            except Exception:
                rec = None
            if not isinstance(rec, dict):
                self._json_error(400, "invalid trace record")
                return
            _diag_append("client_bundle", rec)
            out = {"ok": True, "trace_id": rec.get("trace_id")}
            data = json.dumps(out, ensure_ascii=False).encode("utf-8")
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
            if learner_id and _lm_clear:
                _lm_clear(learner_id)
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

        if path == "/api/save_progress":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except Exception:
                payload = {}
            learner_id = (payload.get("learner_id") or "").strip()
            snapshot = payload.get("snapshot") or payload.get("progress_snapshot")
            if not learner_id:
                self._json_error(400, "missing learner_id")
                return
            if not isinstance(snapshot, dict):
                self._json_error(400, "missing snapshot")
                return
            if not _ps_save_snapshot:
                self._json_error(503, "progress store unavailable")
                return
            ok = _ps_save_snapshot(learner_id, snapshot)
            sid = (snapshot.get("session_id") or "").strip()
            result = {
                "ok": ok,
                "learner_id": learner_id,
                "session_id": sid or None,
            }
            data = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/beta_profile":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(body)
            except Exception:
                payload = {}
            learner_id = (payload.get("learner_id") or "").strip()
            learner_level = (payload.get("learner_level") or "").strip()
            if not learner_id:
                self._json_error(400, "missing learner_id")
                return
            if not learner_level:
                self._json_error(400, "missing learner_level")
                return
            if not _bp_save_profile:
                self._json_error(503, "beta profile unavailable")
                return
            updates = {
                "learner_level": learner_level,
                "level_source": (payload.get("level_source") or "self_selected").strip(),
            }
            if isinstance(payload.get("comfort_mode"), bool):
                updates["comfort_mode"] = payload["comfort_mode"]
            ok = _bp_save_profile(learner_id, updates)
            profile = _bp_load_profile(learner_id) if ok and _bp_load_profile else {}
            result = {"ok": ok, "learner_id": learner_id, "profile": profile}
            data = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200 if ok else 400)
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

            # ── Diagnostic capture (behaviour-free) ───────────────────────────
            # Populated only when diagnostics are enabled AND the client threaded
            # a diag_trace_id. Filled incrementally below and attached to the
            # response + diag store just before the response is sent.
            _diag_cap = None
            if _diag_enabled() and isinstance(payload, dict):
                _diag_tid = str(payload.get("diag_trace_id") or "").strip()
                if _diag_tid:
                    _diag_cap = {
                        "trace_id": _diag_tid,
                        "server_received_at": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(timespec="milliseconds"),
                        "normalizer": _diag_normalizer_name(),
                    }

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
                    asked_zh = (payload.get("direction_question_zh") or "").strip()
                    # Safety net: if the client sent no topic (e.g. from a client-side fallback
                    # question that was missing the topic field), infer it from the question text
                    # using the same fuzzy matching the counter-question path uses.
                    if not topic and asked_zh:
                        _inferred = _find_mirror_answer(asked_zh, engine_id, persona)
                        if _inferred:
                            # _find_mirror_answer already called _mirror_persona_stub internally
                            stub, stub_en = _inferred[0], _inferred[1]
                            topic = _inferred[2] if len(_inferred) > 2 else ""
                            if len(_inferred) > 3 and _inferred[3] not in ("unknown", ""):
                                engine_id = _inferred[3]
                        else:
                            stub_result = _mirror_persona_stub(topic, engine_id, persona)
                            stub, stub_en = stub_result if isinstance(stub_result, tuple) else (stub_result, "")
                    else:
                        stub_result = _mirror_persona_stub(topic, engine_id, persona)
                        stub, stub_en = stub_result if isinstance(stub_result, tuple) else (stub_result, "")
                    # Derive the engine from the topic so the client can update its engine state
                    # correctly after a user-led question (prevents identity-engine restart after mirror).
                    _TOPIC_TO_ENG: dict = {
                        "name_what": "identity",   "name_nickname": "identity",
                        "name_meaning": "identity","name_story": "identity",
                        "name_giver": "identity",
                        "food_fav": "food",        "food_local": "food",   "food_spicy": "food",
                        "place_from": "place",     "place_like": "place",  "place_special": "place",
                        "place_far": "place",      "place_far_or_not": "place",
                        "place_never_been": "place","place_live_now": "place","place_hometown": "place",
                        "place_distance_ref": "place","place_distance_time": "place",
                        "place_distance_transport": "place",
                        "travel_where": "travel",  "travel_fav": "travel", "travel_memorable": "travel",
                        "travel_with": "travel",
                        "work_what": "work",       "work_like": "work",    "work_duration": "work",
                        "work_platform": "work",   "work_company": "work",
                        "hobby_what": "hobby",     "hobby_fav": "hobby",
                        "family_marital": "family","family_children": "family",
                        "family_parents": "family","family_live_with": "family",
                    }
                    if engine_id in ("unknown", "") and topic:
                        engine_id = _TOPIC_TO_ENG.get(topic, engine_id)
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
                    # state_update carries the derived engine so the client can update
                    # window._currentEngineId — critical when this is the very first turn
                    # and the user opened with a mirror question (e.g. "你是哪里人？").
                    "state_update": {"current_engine": engine_id} if engine_id not in ("unknown", "") else {},
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
                last_partner_was_loop = cs.get("last_partner_turn_type") == "loop_question"
                last_partner_had_reaction = cs.get("last_partner_had_reaction") is True
                last_answer_fid = (
                    _normalize_frame_id((last_answer.get("frame_id") or "").strip())
                    if last_turn_was_answer and isinstance(last_answer, dict)
                    else ""
                )
                answer_text = _answer_text_from_last_answer(last_answer) if last_turn_was_answer else ""
                raw_answer_text = answer_text
                routing_answer_text = (
                    _normalize_zh_for_routing(raw_answer_text) if raw_answer_text else ""
                )
                _routing_last_answer = last_answer
                if (
                    last_turn_was_answer
                    and isinstance(last_answer, dict)
                    and routing_answer_text
                ):
                    _routing_last_answer = dict(last_answer)
                    _routing_last_answer["submitted_text"] = routing_answer_text
                    if (last_answer.get("selected_option_hanzi") or "").strip():
                        _routing_last_answer["selected_option_hanzi"] = routing_answer_text
                user_asked_question = (
                    _is_user_question(_routing_last_answer) if last_turn_was_answer else False
                )

                # ── Fix 1 override: open-world responsive food answer ──────────────────────
                # A declarative food-list reply to a preceding place-food question must never
                # be treated as a learner question, even if a keyword heuristic elsewhere would
                # flag it (e.g. bare "最好" inside "新西兰...最好...都很好吃").  The food-question
                # frame context — not vocabulary — is the deciding signal here.
                _responsive_food_answer = False
                if last_turn_was_answer and answer_text:
                    _pft_for_food = (cs.get("last_partner_frame_text") or "").strip() if isinstance(cs, dict) else ""
                    _responsive_food_answer = _is_responsive_food_answer(
                        routing_answer_text or answer_text, last_answer_fid, _pft_for_food,
                    )
                    if _responsive_food_answer and user_asked_question:
                        user_asked_question = False

                if _diag_cap is not None:
                    # ── TEMP DIAGNOSTICS (spoken-input divergence) — REMOVE AFTER DIAGNOSIS ──
                    # Behaviour-free: only populates the diag record; never alters routing.
                    # Captures which last_answer field was selected and the routing signals so a
                    # real-browser trace can be compared field-by-field with a typed turn.
                    _la_diag = last_answer if isinstance(last_answer, dict) else {}
                    _sub_diag = (_la_diag.get("submitted_text") or "").strip()
                    _soh_diag = (_la_diag.get("selected_option_hanzi") or "").strip()
                    _diag_cap["la_submitted_text"] = _sub_diag
                    _diag_cap["la_selected_option_hanzi"] = _soh_diag
                    _diag_cap["la_has_both_fields"] = bool(_sub_diag and _soh_diag)
                    _diag_cap["effective_field"] = (
                        "submitted_text" if _sub_diag else ("selected_option_hanzi" if _soh_diag else "none")
                    )
                    _diag_cap["server_raw_input"] = _sub_diag or _soh_diag or ""
                    _diag_cap["server_raw_answer_text"] = raw_answer_text
                    _diag_cap["routing_text"] = routing_answer_text
                    _diag_cap["last_turn_was_answer"] = bool(last_turn_was_answer)
                    _diag_cap["last_answer_frame_id"] = last_answer_fid
                    _diag_cap["user_asked_question"] = bool(user_asked_question)
                    try:
                        _rt_diag = routing_answer_text or raw_answer_text or ""
                        _diag_cap["direct_persona_intent"] = bool(_is_direct_persona_question(_rt_diag))
                        _diag_cap["place_feature_match"] = bool(_is_place_feature_question(_rt_diag))
                        _diag_cap["place_food_match"] = bool(_is_place_food_question(_rt_diag))
                        _diag_cap["cooking_match"] = bool(_is_cooking_question(_rt_diag))
                    except Exception:
                        pass
                    if isinstance(cs, dict):
                        _diag_cap["cs_current_engine"] = (cs.get("current_engine") or "")
                        _diag_cap["cs_last_partner_frame_text"] = (cs.get("last_partner_frame_text") or "")
                        _diag_cap["cs_last_counter_reply"] = (cs.get("last_counter_reply") or "")
                        _diag_cap["cs_last_place_subject"] = (cs.get("last_place_subject") or "")
                        _diag_cap["cs_learner_stated_location"] = (cs.get("learner_stated_location") or "")
                        _rpr_diag = cs.get("recent_persona_replies")
                        _diag_cap["cs_recent_persona_replies_count"] = (
                            len(_rpr_diag) if isinstance(_rpr_diag, list) else 0
                        )
                        _diag_cap["cs_location_retry_count"] = int(cs.get("location_retry_count") or 0)
                    _diag_cap["slot_names"] = list(slot_names) if isinstance(slot_names, list) else []

                # ── Affirmation-after-re-ask: clear confusion counters ──────────────────
                # When the app issued a clarification re-ask last turn (noisy location,
                # pending-frame commitment, or general confusion rephrase) and the learner
                # responds with a plain affirmation (对/是的/没错/嗯 etc.), treat this as
                # "I understood — continue" rather than escalating repair counters.
                # Conditions:
                #   1. Learner answer is a plain standalone affirmation (strict check).
                #   2. Previous partner turn was a re-ask: contains "我是问：" or "你是说"
                #      or the location_clarify_hint flag is set in conversation state.
                _prev_partner_text = (cs.get("last_partner_frame_text") or "").strip() if isinstance(cs, dict) else ""
                _had_re_ask = (
                    "我是问" in _prev_partner_text
                    or "你是说" in _prev_partner_text
                    or bool(cs.get("location_clarify_hint") if isinstance(cs, dict) else False)
                )
                _confirmed_re_ask = (
                    last_turn_was_answer
                    and not user_asked_question
                    and _had_re_ask
                    and _is_plain_affirmation(answer_text)
                )
                if _confirmed_re_ask and isinstance(cs, dict):
                    cs["recent_confusion_count"]      = 0
                    cs["repair_attempt_count"]         = 0
                    cs["mirror_confusion_count"]       = 0
                    cs["consecutive_not_understood"]   = 0
                    cs["location_clarify_hint"]        = ""
                    cs["location_retry_count"]         = 0
                    recent_confusion_count             = 0

                # Pending destination confirmation: check if last turn offered a near-match
                # clarification ("你是说甘肃吗？") and this turn is an affirmation.
                _pending_dest = (cs.get("pending_dest_candidate") or "").strip() if isinstance(cs, dict) else ""
                _is_dest_confirmation = (
                    bool(_pending_dest)
                    and last_turn_was_answer
                    and not user_asked_question
                    and last_answer_fid == "f_travel_dest_generic_clarify"
                    and any(c in (answer_text or "") for c in ("是", "对", "嗯", "好", "对的", "是的", "对啊"))
                )
                force_food_followup = last_turn_was_answer and (not user_asked_question) and (
                    last_answer_fid == "p2_pl_2" or _looks_food_related_answer(answer_text)
                )
                if force_food_followup and "DISH" not in slot_names:
                    slot_names = ["DISH"] + slot_names
                    meaningful = True
                unscripted_probe_first = last_turn_was_answer and (not user_asked_question) and _is_unscripted_substantive_answer(last_answer, slot_names)
                weak_reply = last_turn_was_answer and len(answer_text) <= 2
                # Strong travel intent override: if the learner explicitly expresses travel
                # enthusiasm (e.g. "我很喜欢旅行") AND the TRAVEL slot is detected, bridge
                # immediately to the travel engine rather than continuing the current engine's
                # ladder. Fires only when not already in travel engine and the answer is not
                # a question. Double-gated (slot + strong signal) for precision.
                force_travel_bridge = (
                    last_turn_was_answer
                    and _should_route_to_travel(
                        answer_text, current_engine, user_asked_question, slot_names,
                    )
                )
                # Early sentinel: some code below writes to _sel_trace before the full init.
                # Initialize empty here; the full dict replaces it a few lines later.
                _sel_trace: dict = {}
                # Destination answer validation: detect garbled/invalid destination answers
                # (e.g. ASR "刚吃" instead of "甘肃") BEFORE the echo slot and depth-rule run,
                # so invalid text is never echoed and never depth-followed.
                _invalid_dest_answer = False
                _travel_asr_candidate = None
                if last_turn_was_answer and last_answer_fid in _DESTINATION_QUESTION_FRAMES and answer_text:
                    _travel_asr_candidate = _detect_travel_asr_near_match(answer_text)
                    if not _travel_asr_candidate and not _is_valid_destination_answer(answer_text):
                        _invalid_dest_answer = True
                    pass  # trace fields set in _sel_trace init below
                # Cross-engine: "想吃+country" is impossible (can't eat a country) — always detect
                # and redirect to travel clarification regardless of the active frame.
                if last_turn_was_answer and not _travel_asr_candidate and answer_text:
                    _ec_m = _EAT_COUNTRY_RE.search(answer_text)
                    if _ec_m:
                        _travel_asr_candidate = f"去{_ec_m.group(1)}"

                # Depth-before-bridge: three-tier specificity check.
                # Tier 1 (depth-ready — province/city/named dish/specific hobby/named person):
                #   → pick from _DEPTH_ANCHOR_FRAMES  ("你为什么想去那里？")
                # Tier 2 (country-level — 中国/日本/美国):
                #   → pick from _DEPTH_NARROWING_FRAMES ("你想去哪个城市？")
                # Tier 3 (broad — 我想旅行 / 有很多好吃的):
                #   → fall through to normal ladder/slot narrowing
                _recent_fid_set = set(recent or [])
                force_depth_followup_frame = None
                # Fix 4: if the learner already volunteered the travel time/transport in the
                # SAME reply that answered "离那儿远吗？", the "大概要多久？" depth follow-up
                # would just re-ask for information already given — skip it and let the normal
                # ladder acknowledge and continue instead of looping on distance.
                _distance_already_answered = bool(
                    last_answer_fid == "p2_pl_far"
                    and answer_text
                    and _DISTANCE_ALREADY_ANSWERED_RE.search(answer_text)
                )
                if (last_turn_was_answer
                        and not user_asked_question
                        and last_answer_fid in _DEPTH_ANCHOR_FRAMES
                        and answer_text
                        and len(answer_text.replace(" ", "")) >= 2
                        and not _distance_already_answered):
                    _depth_fn  = _DEPTH_ANCHOR_SPECIFICITY.get(last_answer_fid)
                    _narrow_fn = _DEPTH_NARROW_SPECIFICITY.get(last_answer_fid)
                    if (_depth_fn is None) or _depth_fn(answer_text):
                        # Tier 1: specific entity → depth follow-up
                        _candidates = _DEPTH_ANCHOR_FRAMES[last_answer_fid]
                        _sel_trace["depth_followup_tier"] = "depth"
                    elif _narrow_fn and _narrow_fn(answer_text):
                        # Tier 2: country-level → narrowing follow-up
                        _candidates = _DEPTH_NARROWING_FRAMES.get(last_answer_fid, [])
                        _sel_trace["depth_followup_tier"] = "narrow"
                    else:
                        # Tier 3: broad answer → normal ladder
                        _candidates = []
                        _sel_trace["depth_followup_skipped"] = "broad_answer"
                    for _dfc in _candidates:
                        if _dfc in _frames_by_id and _dfc not in _recent_fid_set:
                            force_depth_followup_frame = _dfc
                            break

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

                # Depth-trigger follow-up: detect emotional / plan / relationship signals.
                # Does not fire when: entity-level anchor already applies, or the 2-follow-up
                # per-topic budget is exhausted.
                # EFC guard: only suppress when we are IN the family engine (where EFC can
                # actually run). In other engines, a family mention alongside an emotional signal
                # (e.g. "我妈妈的身体不好") still deserves a depth follow-up.
                _depth_trigger_category = None
                depth_trigger_followup_frame = None
                _depth_trigger_budget = int(cs.get("depth_trigger_followup_count") or 0) if isinstance(cs, dict) else 0
                _efc_blocks_depth_trigger = _efc_active and (current_engine or "").strip().lower() == "family"
                if (last_turn_was_answer
                        and not user_asked_question
                        and force_depth_followup_frame is None
                        and not _efc_blocks_depth_trigger
                        and answer_text
                        and _depth_trigger_budget < 2):
                    _depth_trigger_category = _detect_depth_trigger(answer_text)
                    if _depth_trigger_category:
                        _engine_key_dt = (current_engine or "").strip().lower()
                        _dt_candidates = _DEPTH_TRIGGER_ENGINE_FRAMES.get((_depth_trigger_category, _engine_key_dt), [])
                        for _dtf in _dt_candidates:
                            if _dtf in _frames_by_id and _dtf not in _recent_fid_set:
                                depth_trigger_followup_frame = _dtf
                                break
                        print(
                            f"[depth_trigger] cat={_depth_trigger_category} engine={_engine_key_dt}"
                            f" budget={_depth_trigger_budget} → {depth_trigger_followup_frame}",
                            flush=True,
                        )

                # Micro-probe eligibility: short follow-up probe (为什么？哪里？etc.) for slot-based answers.
                # Fires in two later gates (Step 3b in main block, and fallback loop gate).
                # Eligibility: slot_names present, answer ≥ 4 chars, no depth trigger, no confusion.
                _micro_probe_eligible: bool = (
                    last_turn_was_answer
                    and not user_asked_question
                    and bool(slot_names)
                    and len(answer_text or "") >= 4
                    and not _depth_trigger_category
                    and not force_depth_followup_frame
                    and not _is_confusion_signal(answer_text)
                    and answer_text not in ("不知道", "还好", "一般", "好", "嗯", "可以")
                )
                _micro_probe_candidate: Optional[str] = None
                _micro_probe_block_reason: Optional[str] = None
                if _micro_probe_eligible:
                    _micro_probe_candidate = _pick_micro_probe(current_engine, list(recent or []))
                    if _micro_probe_candidate is None:
                        _micro_probe_eligible = False
                        _micro_probe_block_reason = "micro_probe_rate_limited"
                    elif (
                        _micro_probe_candidate == "f_micro_probe_where"
                        and last_answer_fid in (
                            "f_live_where", "frame.location.live_question", "f_from_where"
                        )
                        and (
                            re.search(r"[A-Za-z]{3,}", answer_text or "")  # Latin-script city (Dunedin, Auckland)
                            or "CITY" in (slot_names or set())              # Chinese-character city extracted (奥克兰, 北京)
                        )
                    ):
                        # Don't ask bare "哪里？" when the learner has already named a city —
                        # either as Latin script (e.g. "Dunedin") or a Chinese-character place
                        # (e.g. "奥克兰", "新西兰") that was extracted as a CITY slot.  The city
                        # is already known; let normal frame selection advance to the distance
                        # follow-up (p2_pl_far, f_place_special, etc.) instead.
                        _micro_probe_candidate = None
                        _micro_probe_eligible = False
                        _micro_probe_block_reason = "city_already_given"
                elif not last_turn_was_answer:
                    _micro_probe_block_reason = "not_last_turn_answer"
                elif not slot_names:
                    _micro_probe_block_reason = "no_slot_names"
                elif len(answer_text or "") < 4:
                    _micro_probe_block_reason = "answer_too_short"
                elif _depth_trigger_category:
                    _micro_probe_block_reason = "depth_trigger_active"
                elif force_depth_followup_frame:
                    _micro_probe_block_reason = "force_depth_followup_active"
                elif _is_confusion_signal(answer_text):
                    _micro_probe_block_reason = "confusion_signal"

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
                _repair_attempt_count   = 0  # updated in repair escalation block below
                _repair_escalation_level = 0
                _has_submitted_text = isinstance(last_answer, dict) and bool((last_answer.get("submitted_text") or "").strip())
                _has_selected_hanzi = isinstance(last_answer, dict) and bool((last_answer.get("selected_option_hanzi") or "").strip())
                _sel_trace: dict = {
                    "final_frame_source": "not_computed",
                    # Answer-path diagnostics — compare these to spot client-side collapse.
                    "input_mode": (
                        "asr" if _has_submitted_text and _has_selected_hanzi
                        else ("typed" if _has_submitted_text else ("option_tap" if _has_selected_hanzi else "none"))
                    ) if last_turn_was_answer else "none",
                    "asr_raw_text": (
                        (last_answer.get("submitted_text") or "") if isinstance(last_answer, dict) else ""
                    ) if last_turn_was_answer else "",
                    "accepted_text": answer_text,
                    "current_frame_id": (last_answer.get("frame_id") or "") if isinstance(last_answer, dict) else "",
                    "food_answer_detected": _looks_food_related_answer(answer_text) if answer_text else False,
                    "food_answer_rejected_reason": None,  # filled in below if food slot rejected
                    "travel_answer_detected": _looks_travel_related_answer(answer_text) if answer_text else False,
                    "normalized_answer": answer_text,
                    # Work-retirement detection fields (set to True in the relevant paths below).
                    "work_retirement_detected": False,
                    "work_retirement_asr_correction": False,
                    "work_retirement_followup_used": False,
                    # Travel destination validation fields (computed above, now safely referenced here).
                    "entity_validation_failed": _invalid_dest_answer,
                    "fuzzy_candidate": _travel_asr_candidate,
                    "travel_asr_near_miss": bool(_travel_asr_candidate),
                    "travel_asr_target": _travel_asr_candidate,
                    # Repair escalation (updated after counter_reply block)
                    "repair_attempt_count": 0,
                    "repair_escalation_level": 0,
                }
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
                # Exception: suppress reaction prefix when learner asked us a question — the
                # counter_reply IS the response; a 挺好/真不错 prefix would feel like an
                # acknowledgement instead of an answer.
                if last_turn_was_answer and not user_asked_question:
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
                                        if 0 < _pe <= 20:
                                            _city = _frag[:_pe]
                                            break
                                    elif _frag and len(_frag) <= 20:
                                        _city = _frag.rstrip("。，！？")
                                        break
                        # Fallback: scan for known prominent place names in the submitted text.
                        # Covers noisy inputs like "我现在住新西兰等你等" where prefix patterns fail.
                        if not _city and _submitted:
                            _KNOWN_PLACES = (
                                "新西兰", "澳大利亚", "澳洲", "美国", "英国", "日本", "韩国",
                                "德国", "法国", "加拿大", "新加坡", "马来西亚", "泰国", "越南",
                                "印度", "台湾", "香港", "中国",
                                "北京", "上海", "广州", "深圳", "成都", "重庆", "西安",
                                "杭州", "南京", "武汉", "苏州", "天津", "青岛",
                            )
                            for _kp in _KNOWN_PLACES:
                                if _kp in _submitted:
                                    _city = _kp
                                    break
                        if _city:
                            _echo_candidate = f"哦，{_city}！"
                            _echo_triggered_by = "CITY"
                        elif _is_place_description(_submitted):
                            # Learner gave descriptive content ("安静风景很好看") without a city name.
                            # Echo the strongest descriptor so the reply feels acknowledging.
                            _desc_kw_echo = [
                                ("风景", "风景很好"), ("好看", "风景好看"), ("安静", "很安静"),
                                ("漂亮", "很漂亮"), ("方便", "很方便"), ("热闹", "很热闹"),
                                ("繁华", "很繁华"), ("冷清", "比较冷清"), ("美丽", "很美"),
                            ]
                            _matched = [v for k, v in _desc_kw_echo if k in _submitted]
                            _echo_candidate = (
                                f"哦，{'，'.join(_matched[:2])}！" if _matched else "哦，听起来不错！"
                            )
                            _echo_triggered_by = "PLACE_DESC"
                    elif "NAME" in slot_names and exchange_count <= 3:
                        _name = (_mem.get("learner_name") or "").strip()
                        if _name and len(_name) <= 6 and "___" not in _name:
                            _echo_candidate = f"{_name}！"
                            _echo_triggered_by = "NAME"
                    elif "DISH" in slot_names:
                        # Prefer submitted_text (full ASR sentence); fall back to selected_option_hanzi
                        # so the echo works even when only a tap/option value was sent.
                        _dish_text = _submitted
                        if not _dish_text and isinstance(last_answer, dict):
                            _dish_text = (last_answer.get("selected_option_hanzi") or "").strip().rstrip(
                                "。，！？、…·\u3002\uff0c\uff01\uff1f.!?, "
                            )
                        if _dish_text and len(_dish_text) <= 20:
                            _echo_candidate = f"哦，{_dish_text}！"
                            _echo_triggered_by = "DISH"
                    elif "TRAVEL" in slot_names and not _invalid_dest_answer:
                        # Guard: suppress echo when destination answer was flagged as invalid/garbled.
                        _travel_text = _submitted
                        if not _travel_text and isinstance(last_answer, dict):
                            _travel_text = (last_answer.get("selected_option_hanzi") or "").strip().rstrip(
                                "。，！？、…·\u3002\uff0c\uff01\uff1f.!?, "
                            )
                        if _travel_text and len(_travel_text) <= 20:
                            # Strip first-person desire prefix so the persona never echoes
                            # "我想去中国" as its own statement ("哦，我想去中国！").
                            # Extract only the destination: "我想去中国" → "中国".
                            _fp_travel_re = re.compile(
                                r"^我[很最也]?[想要][去到]?|^我[很最也]?非常想[去到]?"
                            )
                            _dest_only = _fp_travel_re.sub("", _travel_text).strip()
                            if _dest_only and len(_dest_only) < len(_travel_text):
                                _travel_text = _dest_only
                            _echo_candidate = f"哦，{_travel_text}！"
                            _echo_triggered_by = "TRAVEL"
                    elif "COMPANY" in slot_names:
                        _co = (_mem.get("job_company") or _mem.get("company") or "").strip()
                        if not _co and _submitted and 2 <= len(_submitted) <= 12:
                            _co = _submitted
                        if _co and len(_co) <= 12:
                            _echo_candidate = f"哦，{_co}！"
                            _echo_triggered_by = "COMPANY"
                        elif not _echo_candidate and _submitted:
                            # Long institution names (大学, 学校…): extract institution type
                            # so the learner gets an acknowledgement even for long names.
                            _inst_type = next(
                                (w for w in ("大学", "学院", "学校", "研究所", "医院", "银行", "公司")
                                 if w in _submitted),
                                None,
                            )
                            if _inst_type:
                                _echo_candidate = f"哦，{_inst_type}工作！"
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

                # Work-location frame (no formal slot): echo work city or institution type
                # so learner gets a direct acknowledgement before the next question.
                if not _echo_candidate and last_turn_was_answer and last_answer_fid in ("f_work_where",):
                    _wl_submitted = (last_answer.get("submitted_text") or "").strip() if isinstance(last_answer, dict) else ""
                    _wl_submitted = _wl_submitted.rstrip("。，！？.!?, ")
                    _wl_cities = ("北京", "上海", "广州", "深圳", "成都", "重庆", "西安",
                                  "杭州", "南京", "武汉", "苏州", "天津", "青岛",
                                  "新西兰", "澳大利亚", "英国", "美国", "日本", "新加坡")
                    _wl_city = next((c for c in _wl_cities if c in _wl_submitted), None)
                    if _wl_city:
                        _echo_candidate = f"哦，{_wl_city}工作！"
                        _echo_triggered_by = "CITY"
                    elif any(w in _wl_submitted for w in ("大学", "学院", "学校")):
                        _echo_candidate = "哦，大学工作！"
                        _echo_triggered_by = "JOB"
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

                # Work place-only reaction guard: suppress praise when the learner named an
                # institution (大学, 医院…) without a role marker (老师, 医生…).
                # Replace over-enthusiastic praise with a neutral acknowledgement so the
                # learner still gets some echo rather than a bare follow-up question.
                if (
                    reaction_prefix_text
                    and (current_engine or "").strip().lower() == "work"
                    and last_turn_was_answer
                    and answer_text
                    and any(m in answer_text for m in _WORK_PLACE_ONLY_SIGNALS)
                    and not any(m in answer_text for m in _WORK_ROLE_MARKERS)
                ):
                    reaction_prefix_text = "哦，好的。"
                    _rxn_trace["composition_mode"] = "softened_work_place_only"

                # Emotional depth trigger: suppress the generic stance reaction entirely so
                # tonally wrong praise (很好！) never precedes empathetic follow-ups like 现在怎么样？
                # The follow-up question itself carries the empathy.
                if (
                    reaction_prefix_text
                    and _depth_trigger_category == "emotional"
                    and last_turn_was_answer
                ):
                    reaction_prefix_text = ""
                    _rxn_trace["composition_mode"] = "suppressed_emotional_depth_trigger"

                # Content-aware warm acknowledgement overrides.
                # These fire AFTER the engine-based stance so they only replace generic
                # stance phrases — never override echoes or emotional-depth suppression.
                if (
                    last_turn_was_answer
                    and answer_text
                    and not _echo_candidate          # echo takes priority
                    and _depth_trigger_category != "emotional"
                    and reaction_prefix_text         # only replace existing stance
                    and reaction_used_fallback       # only replace generic pool picks
                ):
                    _at = answer_text
                    if any(kw in _at for kw in ("好多了", "好很多", "好了很多", "好转", "恢复", "改善", "身体好")):
                        reaction_prefix_text = "那太好了。"
                        _rxn_trace["composition_mode"] = "content_aware_health"
                    elif any(kw in _at for kw in ("一起住", "住在一起", "跟家人住", "和家人住", "跟父母住", "和父母住")):
                        reaction_prefix_text = "这样挺好。"
                        _rxn_trace["composition_mode"] = "content_aware_family_together"
                    elif (current_engine or "").strip().lower() in ("food",) and any(kw in _at for kw in ("好吃", "很香", "味道好", "喜欢吃", "爱吃")):
                        reaction_prefix_text = "听起来很好吃。"
                        _rxn_trace["composition_mode"] = "content_aware_food"
                    elif (current_engine or "").strip().lower() == "work" and any(kw in _at for kw in ("老师", "教书", "教学", "讲课", "大学老师", "教授")):
                        reaction_prefix_text = "听起来很有意思。"
                        _rxn_trace["composition_mode"] = "content_aware_teaching"
                    elif "结婚" in _at and any(kw in _at for kw in ("年", "月", "多年", "好几年")):
                        # Marriage-duration answer: "我结婚两年了" / "结婚了两年了" / "已经结婚两年了"
                        # Echo the duration back so the learner feels heard.
                        _dur_m = re.search(r"结婚[了]?\s*([一两三四五六七八九十百半\d]+(?:年|个月|月))", _at)
                        if _dur_m:
                            reaction_prefix_text = f"结婚{_dur_m.group(1)}了，挺好的。"
                        else:
                            reaction_prefix_text = "结婚了，挺好的。"
                        _rxn_trace["composition_mode"] = "content_aware_marriage_duration"

                # Multi-destination reaction: learner listed 3+ places in a single travel/place answer.
                # Override whatever stance was generated with an enthusiastic acknowledgment.
                _MULTI_DEST_PAT = re.compile(
                    r'美国|英国|法国|中国|日本|韩国|新西兰|澳大利亚|欧洲|泰国|印度|新加坡|越南|'
                    r'意大利|西班牙|德国|加拿大|台湾|香港|北京|上海|广州|成都|巴黎|伦敦|纽约'
                )
                if (
                    last_turn_was_answer and answer_text
                    and (current_engine or "").strip().lower() in ("travel", "place")
                    and len(set(_MULTI_DEST_PAT.findall(answer_text))) >= 3
                ):
                    reaction_prefix_text = "哇，你去过很多地方！"
                    reaction_used_fallback = False
                    _rxn_trace["composition_mode"] = "multi_destination_ack"

                # User-question override (spec-friendly, no schema changes):
                # if the user asked a question (counter-question), return the persona's answer
                # as a dedicated `counter_reply` field so the client can display/TTS it
                # separately — much more reliable than concatenating into reaction_prefix_text
                # where bridge resets or ordering issues can silently drop it.
                persona_id = (payload.get("persona_id") or cs.get("persona_id") or "").strip() or None
                persona = _resolve_persona(persona_id) or (_get_persona(persona_id) if _get_persona else None)
                # Read prev counter_reply FIRST — needed for confusion recovery and dedup.
                _prev_counter_reply = (cs.get("last_counter_reply") or "").strip() if isinstance(cs, dict) else ""
                # Recent persona replies (last 3) — used to suppress exact-repeat answers.
                _recent_persona_replies: list = list(cs.get("recent_persona_replies") or []) if isinstance(cs, dict) else []
                _last_text_for_counter = ""
                if last_turn_was_answer and isinstance(last_answer, dict):
                    _last_text_for_counter = routing_answer_text or (
                        (last_answer.get("submitted_text") or last_answer.get("selected_option_hanzi") or "").strip()
                    )
                _counter_seed = f"{cs.get('session_id', '')}/{len(recent or [])}" if isinstance(cs, dict) else ""

                # Mirror confusion escalation state — read before branching.
                # Cleared whenever a fresh (non-confusion) mirror answer is generated.
                _cs_mirror_topic  = (cs.get("last_mirror_topic")  or "") if isinstance(cs, dict) else ""
                _cs_mirror_engine = (cs.get("last_mirror_engine") or "") if isinstance(cs, dict) else ""
                _cs_mirror_conf   = int(cs.get("mirror_confusion_count") or 0) if isinstance(cs, dict) else 0

                _counter_result = None
                _counter_is_new_mirror = False    # set True when a fresh mirror answer is generated this turn
                _counter_is_working_memory = False # set True when working memory produced the answer (E3)
                _new_mirror_topic = ""
                _new_mirror_engine = ""
                _confusion_about_app_q = False  # set True when learner confused about frame question (not mirror)
                _noisy_location_clarify  = False  # set True when location answer looks garbled → frame override below

                if last_turn_was_answer:
                    # ── User-initiative overrides (highest priority) ───────────────
                    # A clear learner initiative must be honoured before the recovery /
                    # mirror ladder buries it under a generic ack or a re-ask.
                    #   (I) Frustration / insult  → social repair (apology), never "这样挺好".
                    #   (C) Volunteered travel plan → travel follow-up, never a topic jump.
                    if _counter_result is None and answer_text:
                        if _is_frustration_or_insult(answer_text):
                            _fr = _frustration_repair_reply(seed=_counter_seed)
                            if _fr and _fr[0]:
                                _counter_result = _fr
                                reaction_prefix_text = ""   # suppress positive acknowledgement
                                _rxn_trace["composition_mode"] = "frustration_repair"
                        elif _is_learner_disclosure(answer_text):
                            # Learner discloses a family health/concern situation.
                            # Reply with empathy before any persona-question routing fires.
                            _de = _disclosure_empathy_reply(seed=_counter_seed)
                            if _de and _de[0]:
                                _counter_result = _de
                                reaction_prefix_text = ""   # suppress positive acknowledgement
                                _rxn_trace["composition_mode"] = "learner_disclosure_empathy"
                        elif _is_persona_challenge(answer_text):
                            # Learner challenges the persona's Chinese knowledge.
                            # Play along rather than giving generic praise.
                            _ch = _persona_challenge_reply(seed=_counter_seed)
                            if _ch and _ch[0]:
                                _counter_result = _ch
                                reaction_prefix_text = ""
                                _rxn_trace["composition_mode"] = "persona_challenge_reply"
                        elif _responsive_food_answer:
                            # Open-world responsive food answer (Fix 1) — the previous partner
                            # frame asked what food is good somewhere, and this reply is a
                            # declarative food-list response.  Acknowledge it and ask a natural
                            # follow-up; never route through question classification, direct-
                            # persona answering, the mirror bank, or the limitation fallback.
                            # No fixed food vocabulary is required — unknown foods pass through.
                            _fa = _food_responsive_reply(answer_text, seed=_counter_seed)
                            if _fa and _fa[0]:
                                _counter_result = _fa
                                _rxn_trace["composition_mode"] = "responsive_food_answer"
                        elif (not user_asked_question) and _has_volunteered_travel_intent(answer_text):
                            _ti = _travel_intent_followup(answer_text)
                            if _ti and _ti[0]:
                                _counter_result = _ti
                                _rxn_trace["composition_mode"] = "volunteered_travel_followup"

                    # ── Classify the recovery signal type before routing ───────────
                    # Order: meaning > example > repeat/slower > lexical > confusion.
                    # Lexical definition check first (needed to guard meaning detection).
                    _lex_ct = _lexical_definition_reply(_last_text_for_counter) if (
                        _last_text_for_counter and not user_asked_question
                    ) else None

                    # Meaning request: 什么意思啊 / 是什么意思 → English gloss + simpler Chinese.
                    # Guard: not a genuine persona question and not a vocab lookup (那个字是什么意思).
                    _is_meaning = bool(
                        _last_text_for_counter
                        and not _lex_ct
                        and not user_asked_question
                        and any(m in _last_text_for_counter for m in _MEANING_REQUEST_MARKERS)
                    )
                    # Example request: 给我一个例子 / 举个例子
                    _is_example = bool(
                        _last_text_for_counter
                        and not _lex_ct
                        and not user_asked_question
                        and any(m in _last_text_for_counter for m in _EXAMPLE_REQUEST_MARKERS)
                    )
                    # Repeat / slower request: explicit re-read signals or very short confused
                    # sound bites (啊？ / 嗯？).  Meaning requests already handled above.
                    _is_rr = bool(
                        _last_text_for_counter
                        and not _is_meaning
                        and not _is_example
                        and (
                            any(m in _last_text_for_counter for m in _REPEAT_REQUEST_MARKERS)
                            or any(m in _last_text_for_counter for m in _SLOWER_REQUEST_MARKERS)
                            or _last_text_for_counter.strip() in _BARE_REPEAT_UTTERANCES
                        )
                    )

                    # ── Explicit place-topic priority ────────────────────────────────────
                    # A feature/food question about a place (named city or resolved deixis)
                    # must win immediately — before hometown/origin intent, previous-answer
                    # reuse, stale override, or any conversational fallback. This turn's
                    # explicit topic overrides prior topic and prior reply state, generically
                    # for every recognised city (no per-city special-casing). Computed here
                    # (rather than as a bare elif) so that when no answer is resolvable
                    # (e.g. bare place-food question with no city/deixis/persona fact), the
                    # ladder naturally falls through to the existing recovery/mirror logic
                    # below instead of dead-ending on an empty branch.
                    #
                    # Contextual place-name repair (narrow): ASR can mis-hear the place
                    # token itself (e.g. "西安" → "需要", "北京" → "背景") while the
                    # feature/food MARKER still matches correctly. When that happens,
                    # _direct_persona_answer silently falls back to the persona's OWN
                    # hometown/city — which is wrong whenever the discussed place differs
                    # from the persona's hometown. Repair the invalid token to the single
                    # unambiguous recently-discussed city (routing text only; the raw
                    # learner transcript is untouched), or ask a clarification when two or
                    # more recent cities are plausible. Never fires on a recognised place.
                    _explicit_place_topic_result: Optional[tuple] = None
                    _place_q_repaired, _place_q_clarify = (
                        _repair_contextual_place_question(_last_text_for_counter, cs, _prev_counter_reply)
                        if _last_text_for_counter else (None, None)
                    )
                    _routing_text_for_place_q = _place_q_repaired or _last_text_for_counter
                    if _place_q_clarify:
                        _explicit_place_topic_result = (_place_q_clarify, "")
                    elif (
                        _routing_text_for_place_q
                        and not _is_confusion_signal(_routing_text_for_place_q)
                        and (
                            _is_place_feature_question(_routing_text_for_place_q)
                            or _is_place_food_question(_routing_text_for_place_q)
                        )
                    ):
                        _pt_raw = _direct_persona_answer(
                            _routing_text_for_place_q, persona,
                            recent_replies=_recent_persona_replies,
                        )
                        if _pt_raw:
                            _pt_zh = (
                                f"我呢，{_pt_raw}" if not _pt_raw.startswith("我") else _pt_raw
                            )
                            _pt_en = _persona_answer_en(
                                persona, _pt_zh,
                                _detect_reverse_fact_intent(_routing_text_for_place_q),
                            )
                            _explicit_place_topic_result = (_pt_zh, _pt_en)

                    if _counter_result is not None:
                        # A user-initiative override (frustration repair / volunteered travel
                        # follow-up) already produced the answer — keep it.
                        pass
                    elif _explicit_place_topic_result is not None:
                        _counter_result = _explicit_place_topic_result
                    elif _is_meaning:
                        _mr_frame_text = (cs.get("last_partner_frame_text") or "").strip() if isinstance(cs, dict) else ""
                        if _mr_frame_text:
                            _counter_result = _meaning_recovery_reply(_mr_frame_text)
                            _confusion_about_app_q = True
                    elif _is_example:
                        # Give a clarified version of the question + a concrete example.
                        # Full example-reply engine deferred; for now reuse _clarify_app_question
                        # which at least avoids repeating the raw Chinese unchanged.
                        _ex_frame_text = (cs.get("last_partner_frame_text") or "").strip() if isinstance(cs, dict) else ""
                        if _ex_frame_text:
                            _counter_result = _clarify_app_question(_ex_frame_text)
                            _confusion_about_app_q = True
                    elif _is_rr:
                        _rr_frame_text = (cs.get("last_partner_frame_text") or "").strip() if isinstance(cs, dict) else ""
                        if _rr_frame_text:
                            _counter_result = _clarify_app_question(_rr_frame_text)
                            _confusion_about_app_q = True
                    elif _lex_ct:
                        _counter_result = _lex_ct
                    elif (
                        _prev_counter_reply
                        and _last_text_for_counter
                        and _is_direct_persona_question(_last_text_for_counter)
                        and not _is_confusion_signal(_last_text_for_counter)
                    ):
                        # Stale counter_reply override: a fresh direct persona question
                        # (e.g. 你做什么工作 after a city-like answer, or 成都有什么好吃 after
                        # a hometown answer) must not be routed through _answer_user_question_prefix
                        # which prioritises _find_mirror_answer before _direct_persona_answer.
                        # The mirror bank can recycle a previous city/place answer as the
                        # "stale override" result — exactly the bug this block is meant to prevent.
                        # Fix: call _direct_persona_answer directly. If it returns None, do not
                        # manufacture a mirror answer here — fall through to standard routing.
                        _so_raw = _direct_persona_answer(
                            _last_text_for_counter, persona,
                            recent_replies=_recent_persona_replies,
                        )
                        if _so_raw:
                            _so_zh = (
                                f"我呢，{_so_raw}" if not _so_raw.startswith("我") else _so_raw
                            )
                            _so_en = _persona_answer_en(
                                persona, _so_zh,
                                _detect_reverse_fact_intent(_last_text_for_counter),
                            )
                            _stale_override = (_so_zh, _so_en)
                        else:
                            _stale_override = None
                        if (
                            _stale_override
                            and (_stale_override[0] or "").strip()
                            and (_stale_override[0] or "").strip() != _prev_counter_reply.strip()
                        ):
                            _counter_result = _stale_override
                    elif (
                        _prev_counter_reply
                        and _last_text_for_counter
                        and _is_confusion_signal(_last_text_for_counter)
                        and not user_asked_question  # genuine questions skip confusion escalation
                        and not _is_direct_persona_question(_last_text_for_counter)
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
                        and not user_asked_question  # genuine questions skip confusion escalation
                        and not _is_direct_persona_question(_last_text_for_counter)
                        and not _cs_mirror_topic  # no active mirror — use existing generic path
                    ):
                        _counter_result = _confusion_recovery_reply(
                            _last_text_for_counter, _prev_counter_reply, seed=_counter_seed
                        )
                    elif (
                        not _prev_counter_reply
                        and _last_text_for_counter
                        and _is_confusion_signal(_last_text_for_counter)
                        and not user_asked_question
                        and not _confirmed_re_ask
                    ):
                        # ── App-question clarification ───────────────────────────────────────
                        # Learner confused about the partner's frame question (no active persona voice).
                        # Rephrase the last question and keep the topic alive.
                        # Discovery panel will also be shown (Path 0 in blue-panel block below).
                        _prev_frame_text = (cs.get("last_partner_frame_text") or "").strip() if isinstance(cs, dict) else ""
                        if _prev_frame_text:
                            _counter_result = _clarify_app_question(_prev_frame_text)
                            _confusion_about_app_q = True
                    elif (
                        not _prev_counter_reply
                        and _last_text_for_counter
                        and not _is_confusion_signal(_last_text_for_counter)
                        and not user_asked_question
                        and not _confirmed_re_ask
                        and "CITY" in slot_names
                        and _extract_open_world_location(_last_text_for_counter, frame_is_residence=True) is None
                    ):
                        # ── Noisy location-answer clarification ───────────────────────────
                        # Learner tried to answer a location question but the place token
                        # looks garbled (e.g. "我住在等你等").  Set the confusion flag so
                        # Path 0 shows blue questions.  A frame-text override (below, after
                        # response is built) will replace the next question with a rephrased
                        # version of the original location question and restore its options —
                        # keeping the learner on the same topic instead of jumping to food.
                        # Uses the OPEN-WORLD extractor (Fix 2) — an unknown place name such
                        # as "达尼丁" is accepted here; only genuinely unusable content
                        # (empty, filler/recovery phrase, ASR-junk-only) reaches this branch.
                        _confusion_about_app_q  = True
                        _noisy_location_clarify = True
                    elif (
                        not _prev_counter_reply
                        and _last_text_for_counter
                        and not _is_confusion_signal(_last_text_for_counter)
                        and not user_asked_question
                        and not _confirmed_re_ask
                        and "CITY" not in slot_names   # CITY frames use _noisy_location_clarify above
                        and last_answer_fid in _COMMITMENT_GUARD_FRAMES
                        and not _is_explicit_topic_switch(_last_text_for_counter)
                        and not _is_relevant_to_frame(_last_text_for_counter, last_answer_fid)
                    ):
                        # ── Pending-frame commitment clarification ────────────────────────
                        # Learner gave an off-topic statement to a protected question frame
                        # (e.g. answered '你和谁一起住？' with '我想去中国').  Rephrase the
                        # original question so the learner understands what was being asked.
                        _pfx_pc = (cs.get("last_partner_frame_text") or "").strip() if isinstance(cs, dict) else ""
                        if _pfx_pc:
                            _caq_pc = _clarify_app_question(_pfx_pc)
                            if _caq_pc:
                                _counter_result        = _caq_pc
                                _confusion_about_app_q = True
                    # ── F2: Adjacency guard ─────────────────────────────────────────────────
                    # If the learner asks "why do you like X?" and the most recent mirror
                    # answer was work/hobby/place/food, reply with the relevant voice_line
                    # rather than letting the selector pick an unrelated frame.
                    if _counter_result is None:
                        _submitted_for_why = (
                            (last_answer.get("submitted_text") or "").strip()
                            if isinstance(last_answer, dict) else ""
                        )
                        _why_like_engines = ("work", "hobby", "place", "food", "travel")
                        if (
                            _is_why_like_follow_up(_submitted_for_why)
                            and _cs_mirror_engine in _why_like_engines
                            and persona
                        ):
                            _wl = (persona.get("voice_lines") or {}).get(_cs_mirror_engine, "")
                            if _wl:
                                _counter_result = (
                                    f"因为{_wl[:30].rstrip('。，！')}，所以觉得挺有意思的。",
                                    "",
                                )
                            else:
                                _counter_result = (
                                    "因为觉得很有意思，慢慢就越来越喜欢了。",
                                    "Because I find it really interesting — I grew to like it more and more.",
                                )

                    # ── E3: Persona working memory ──────────────────────────────────────────
                    # Consult recent persona replies before the mirror bank.
                    # Gives conversational continuity: "I said I went to Tibet — now you're
                    # asking which place I like most → I can answer from what I just said."
                    # Bounded to last 5 replies. Read-only — does not write to cs.
                    if _counter_result is None and user_asked_question and _recent_persona_replies:
                        _wm_facts  = _extract_persona_facts_from_recent(_recent_persona_replies)
                        _wm_answer = _answer_from_working_memory(
                            _last_text_for_counter or "", _wm_facts, persona
                        )
                        if _wm_answer:
                            _counter_result          = _wm_answer
                            _counter_is_working_memory = True

                    # ── Mirror bank + general answer ────────────────────────────────────────
                    # Mirror answers only fire when the user genuinely asked a question.
                    # Statements (e.g. "我跟家人一起住。") must never match the mirror bank —
                    # the fuzzy keyword pass would otherwise match topic keywords in any answer.
                    if _counter_result is None:
                        _mirror_la = (
                            _routing_last_answer if isinstance(_routing_last_answer, dict) else last_answer
                        )
                        _raw_mirror = _find_mirror_answer(
                            (_mirror_la.get("submitted_text") or _mirror_la.get("selected_option_hanzi") or "")
                            if isinstance(_mirror_la, dict) else "",
                            "", persona
                        ) if isinstance(_mirror_la, dict) and user_asked_question else None
                        if _raw_mirror and len(_raw_mirror) == 4:
                            _counter_result      = (_raw_mirror[0], _raw_mirror[1])
                            _counter_is_new_mirror = True
                            _new_mirror_topic    = _raw_mirror[2]
                            _new_mirror_engine   = _raw_mirror[3]
                        else:
                            _prefix_context_reply = (
                                "" if _is_direct_persona_question(_last_text_for_counter or "")
                                else _prev_counter_reply
                            )
                            _counter_result = _answer_user_question_prefix(
                                _mirror_la, persona,
                                recent_replies=_recent_persona_replies,
                                context_reply=_prefix_context_reply,
                            )
                            # If _answer_user_question_prefix fell through to a generic deflection
                            # (no specific answer found), replace it with a clarification of the
                            # app's last question — gives the learner better recovery guidance
                            # than "这个不好说" or "这个以后再聊".
                            _generic_deflects = set(_persona_deflect_phrases.get("generic") or [])
                            if (
                                _counter_result
                                and _generic_deflects
                                and _counter_result[0] in _generic_deflects
                                and not user_asked_question  # genuine 你-questions keep the persona deflect
                            ):
                                _pfx_aq = (cs.get("last_partner_frame_text") or "").strip() if isinstance(cs, dict) else ""
                                if _pfx_aq:
                                    _caq = _clarify_app_question(_pfx_aq)
                                    if _caq:
                                        _counter_result = _caq
                                        _confusion_about_app_q = True
                            # Confusion signal that arrived WITH a question mark
                            # (e.g. "再说一起可以吗？", "什么意思？").
                            # _answer_user_question_prefix returned None for it; route here
                            # the same way as the non-question confusion path.
                            if (
                                user_asked_question
                                and not _counter_result
                                and _is_confusion_signal(answer_text)
                            ):
                                _pfx_aq_c = (cs.get("last_partner_frame_text") or "").strip() if isinstance(cs, dict) else ""
                                if _pfx_aq_c:
                                    _caq_c = _clarify_app_question(_pfx_aq_c)
                                    if _caq_c:
                                        _counter_result = _caq_c
                                        _confusion_about_app_q = True

                _counter_reply    = _counter_result[0] if _counter_result else None
                _counter_reply_en = _counter_result[1] if _counter_result else ""

                # ── E4: Initiative Follow — resolve engine handoff ────────────────────────
                # Performed when: user asked a question AND an answer was produced via any of:
                #   • mirror bank (new mirror answer)
                #   • working memory (E3)
                #   • direct-persona / static-fact path (was not previously covered)
                # Generic deflections are excluded — they do not reveal a clear new topic.
                # If gated conditions pass, the resolved engine is written to state_update
                # so the next frame stays on the learner's redirected topic.
                _e4_engine_handoff: Optional[str] = None
                if user_asked_question and _counter_result:
                    if _counter_is_new_mirror and _new_mirror_topic:
                        _e4_engine_handoff = _QUESTION_TOPIC_TO_ENGINE.get(_new_mirror_topic)
                    elif _counter_is_working_memory:
                        _e4_q_text = (
                            (last_answer.get("submitted_text") or "") if isinstance(last_answer, dict) else ""
                        ).strip()
                        _e4_engine_handoff = _infer_question_topic_engine(_e4_q_text)
                    elif _last_text_for_counter:
                        # Direct-persona / static-fact path: extend E4 to cover confident
                        # persona answers that are not generic deflections.
                        # Uses the same question-text-to-engine classifier as the WM branch.
                        _e4_dp_deflects = set(_persona_deflect_phrases.get("generic") or [])
                        if _counter_result[0] not in _e4_dp_deflects:
                            _e4_engine_handoff = _infer_question_topic_engine(
                                _last_text_for_counter
                            )

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

                # Repair state hygiene (F4) — clear stale repair counters after a successful
                # non-confusion turn so they don't keep dominating selection on future turns.
                if isinstance(cs, dict):
                    _g4_text = (_last_text_for_counter or "").strip()
                    if (
                        _g4_text
                        and not _is_confusion_signal(_g4_text)
                        and not _is_plain_affirmation(_g4_text)
                    ):
                        cs["repair_attempt_count"]   = 0
                        cs["recent_confusion_count"] = 0

                # Dedup guard: if this counter_reply repeats the previous one OR any of the
                # last few persona replies, re-run intent matching (reverse_fact_map) so a
                # different-intent question gets its own distinct answer instead of a repeat.
                _dedup_pool = ([_prev_counter_reply] if _prev_counter_reply else []) + list(_recent_persona_replies or [])
                if _counter_reply and _counter_reply.strip() in _dedup_pool:
                    _deduped = _dedupe_persona_answer(
                        _counter_reply, _dedup_pool, _last_text_for_counter, persona,
                    )
                    if _deduped and _deduped.strip() != _counter_reply.strip():
                        _counter_reply = _deduped
                        # Translate via the shared persona-answer path so dynamic
                        # reverse-fact answers (e.g. "我老家在西安。") get a real English
                        # gloss instead of an empty string.
                        _counter_reply_en = _persona_answer_en(
                            persona, _counter_reply,
                            _detect_reverse_fact_intent(_last_text_for_counter),
                        )
                    else:
                        _counter_reply = _persona_deflect("generic", _counter_reply)
                        _counter_reply_en = _persona_answer_en(persona, _counter_reply)

                # Belt-and-suspenders exact-repeat guard (restored from pre-ffc806c baseline).
                # Catches any exact duplicate that slipped past _dedupe_persona_answer above
                # (e.g. when _dedup_pool membership check missed a normalised variant).
                if _counter_reply and _counter_reply.strip() == (_prev_counter_reply or "").strip():
                    _counter_reply = _persona_deflect("generic", _counter_reply)
                    _counter_reply_en = _persona_answer_en(persona, _counter_reply)

                # ── Repair escalation ───────────────────────────────────────────
                # When the learner repeatedly signals confusion (啊？ / 我不懂 / etc.),
                # escalate the partner's repair phrase rather than looping the same response.
                # Counter sources: session-level recent_confusion_count (updated by selector),
                # client-tracked repair_attempt_count, and consecutive_not_understood —
                # take the maximum so any client counter can drive escalation.
                # Level 1 (count==1): short acknowledgment — let existing flow handle naturally.
                # Level 2 (count==2): explicit repeat request "再说一遍可以吗？"
                # Level 3+ (count>=3): supportive model-answer hint.
                _repair_attempt_count = max(
                    recent_confusion_count,                             # session-level (from selector)
                    int(cs.get("repair_attempt_count") or 0),           # client-tracked
                    int(cs.get("consecutive_not_understood") or 0),     # client-tracked
                )
                _repair_escalation_level = min(_repair_attempt_count, 3) if _repair_attempt_count else 0
                # Persona-self-question short-circuit: if the learner's text is a direct
                # question about the partner's residence or hometown, never escalate to
                # "换个话题吧" even when repair counters are stale from earlier turns.
                _PERSONA_SELF_Q_MARKERS = (
                    "你现在住", "你住在哪", "你住哪", "你住的地方",
                    "你老家", "你的老家", "你是哪里人", "你哪里人",
                    "你家在哪",
                )
                _suppress_change_topic_deflect = bool(
                    answer_text and any(m in answer_text for m in _PERSONA_SELF_Q_MARKERS)
                )
                if (
                    last_turn_was_answer
                    and _is_confusion_signal(answer_text)
                    and _repair_attempt_count >= 2
                    and not _confirmed_re_ask
                    and not _is_plain_affirmation(answer_text)   # 对/是的/嗯 = success, never escalate
                    and not _is_place_description(answer_text)
                ):
                    if _repair_attempt_count == 2:
                        _counter_reply    = "你可以再说一遍吗？"
                        _counter_reply_en = "Could you say that again?"
                    else:
                        # Level 3+: the partner acknowledges and moves on — no model answers
                        # in the partner voice (Design Constitution: no "correct answer" reveals,
                        # no teacher voice). ASR near-match confirmation is still appropriate.
                        _repair_cand = locals().get("_travel_asr_candidate") or None
                        if _repair_cand:
                            _counter_reply    = f"你是说\u201c{_repair_cand}\u201d吗？"
                            _counter_reply_en = f"Did you mean \u201c{_repair_cand}\u201d?"
                        elif _suppress_change_topic_deflect:
                            _counter_reply    = "你可以再说一遍吗？"
                            _counter_reply_en = "Could you say that again?"
                        else:
                            _counter_reply    = "没关系，我们换个话题吧。"
                            _counter_reply_en = "No worries, let's talk about something else."

                _counter_reply_pinyin = _resolve_counter_reply_pinyin(_counter_reply) if _counter_reply else ""
                # Sync repair trace into first _sel_trace (used when priority branches set chosen).
                _sel_trace["repair_attempt_count"]   = _repair_attempt_count
                _sel_trace["repair_escalation_level"] = _repair_escalation_level

                # ── Work-state detection ─────────────────────────────────────────
                # Uses submitted_text; answer_text (which also covers selected options) was
                # already computed above, but retirement/confusion checks are text-only signals.
                _last_user_text = (last_answer or {}).get("submitted_text", "") if last_turn_was_answer else ""

                # Retired / not currently working: extended set beyond just "退休".
                # Routes to p2_wk_retired ("你以前做什么工作？") which is safe for all cases.
                _RETIRED_OR_NONWORKING_SIGNALS = (
                    "退休", "不工作了", "不上班了", "没有工作", "现在不工作", "不上班",
                )
                _user_is_retired = (
                    any(sig in _last_user_text for sig in _RETIRED_OR_NONWORKING_SIGNALS)
                    and "p2_wk_retired" not in recent
                )

                # Near-miss answer guard — delegates to _NEAR_MISS_GUARD_TABLE +
                # _detect_near_miss_answer() defined near _TRAVEL_ASR_NEAR_MATCHES.
                # Covers all registered near-miss cases across engines (currently: work retirement).
                # To add new near-miss types, extend _NEAR_MISS_GUARD_TABLE; no selector edit needed.
                _near_miss_result = (
                    _detect_near_miss_answer(answer_text, last_answer_fid, recent)
                    if (last_turn_was_answer and not user_asked_question and not _user_is_retired)
                    else None
                )
                _needs_retire_clarify    = _near_miss_result is not None
                _near_miss_clarify_frame = _near_miss_result[0] if _near_miss_result else None
                _near_miss_intended      = _near_miss_result[1] if _near_miss_result else None

                # Meaningful-imperfect answer guard — fires for rich, multi-component answers
                # that contain engine-specific keywords but are too complex for normal progression.
                # Only runs when near-miss guard did NOT fire (avoids double-processing).
                _meaningful_imperfect = (
                    _detect_meaningful_imperfect_answer(
                        answer_text, last_answer_fid, recent, same_engine_chain_count
                    )
                    if (last_turn_was_answer and not user_asked_question and not _needs_retire_clarify)
                    else {"should_clarify": False, "clarify_frame_id": None}
                )

                # After clarification frame: user confirms they are retired.
                _RETIREMENT_CONFIRMATION = ("是", "对", "没错", "退休", "我退")
                _retire_confirmed_after_clarify = (
                    last_turn_was_answer and not user_asked_question
                    and last_answer_fid == "f_work_retire_clarify"
                    and any(sig in answer_text for sig in _RETIREMENT_CONFIRMATION)
                    and "p2_wk_retired" not in recent
                )

                # Note: work-confusion routing (typed "我不明白" after a work question) is handled by
                # _apply_discourse_coherence_guard (branch 1b) rather than here, keeping selector-level
                # work-state detection limited to retirement/employment status signals only.

                # Partner curiosity: prefer loop when triggered and depth allows, but avoid weak loop frames if possible
                chosen = None
                chosen_turn_type = "question"
                loop_attempted = False
                listening_move_selected = "none"
                listening_move_reason = ""
                depth_trigger_detected = bool(_depth_trigger_category)
                depth_trigger_followup_used = False
                if _retire_confirmed_after_clarify:
                    chosen = "p2_wk_retired"
                    chosen_turn_type = "question"
                    listening_move_selected = "retired_pivot"
                    listening_move_reason = "user confirmed retirement after homophone clarify"
                    _sel_trace["retired_signal_detected"] = True
                    _sel_trace["retire_confirmed_via_clarify"] = True
                    _sel_trace["work_eligible"] = False
                    _sel_trace["work_followup_suppressed_reason"] = "user_confirmed_retired"
                    _sel_trace["work_retirement_detected"] = True
                    _sel_trace["work_retirement_followup_used"] = True
                elif _needs_retire_clarify:
                    chosen = _near_miss_clarify_frame   # from _NEAR_MISS_GUARD_TABLE
                    chosen_turn_type = "question"
                    listening_move_selected = "near_miss_clarify"
                    listening_move_reason = f"near-miss guard fired: intended={_near_miss_intended!r}"
                    _sel_trace["near_miss_guard_fired"]    = True
                    _sel_trace["near_miss_intended"]       = _near_miss_intended
                    _sel_trace["near_miss_clarify_frame"]  = chosen
                    _sel_trace["retire_homophone_guard"]   = True   # backward-compat for existing tests
                    _sel_trace["work_followup_suppressed_reason"] = "near_miss_guard"
                    _sel_trace["work_retirement_detected"]        = True
                    _sel_trace["work_retirement_asr_correction"]  = True
                    _sel_trace["work_retirement_followup_used"]   = True
                elif _user_is_retired:
                    chosen = "p2_wk_retired"
                    chosen_turn_type = "question"
                    listening_move_selected = "retired_pivot"
                    listening_move_reason = "user non-working or retired"
                    _sel_trace["retired_signal_detected"] = True
                    _sel_trace["work_eligible"] = False
                    _sel_trace["work_followup_suppressed_reason"] = "user_not_working"
                    _sel_trace["work_retirement_detected"] = True
                    _sel_trace["work_retirement_followup_used"] = True
                elif _is_dest_confirmation:
                    # User confirmed the fuzzy near-match ("你是说甘肃吗？" → "对") —
                    # proceed to depth follow-up as if they had named that destination.
                    chosen = "f_travel_why_want_go"
                    chosen_turn_type = "loop_question"
                    listening_move_selected = "loop_question"
                    listening_move_reason = f"dest_confirmed_{_pending_dest}"
                    pending_listening_move = False
                    listening_wait_turns = 0
                    _sel_trace["fuzzy_candidate_confirmed"] = _pending_dest
                    print(f"[dest_confirm] '{_pending_dest}' confirmed → depth follow-up", flush=True)
                elif _travel_asr_candidate or _invalid_dest_answer:
                    # Invalid or garbled destination answer: route to clarification instead
                    # of echoing bad text or jumping to depth/bridge.
                    chosen = "f_travel_dest_generic_clarify"
                    chosen_turn_type = "question"
                    listening_move_selected = "travel_dest_clarify"
                    listening_move_reason = "travel_asr_near_match" if _travel_asr_candidate else "invalid_dest_answer"
                    pending_listening_move = False
                    listening_wait_turns = 0
                    _sel_trace["fuzzy_clarification_prompted"] = bool(_travel_asr_candidate)
                    _sel_trace["bridge_suppressed_reason"] = "dest_validation_failed"
                    if _travel_asr_candidate:
                        print(f"[dest_validate] ASR near-match '{_travel_asr_candidate}' in '{answer_text[:20]}' → clarify", flush=True)
                    else:
                        print(f"[dest_validate] no valid entity in '{answer_text[:20]}' → clarify", flush=True)
                elif force_depth_followup_frame:
                    chosen = force_depth_followup_frame
                    chosen_turn_type = "loop_question"
                    listening_move_selected = "loop_question"
                    listening_move_reason = f"depth_before_bridge_{last_answer_fid}"
                    pending_listening_move = False
                    listening_wait_turns = 0
                    _sel_trace["depth_followup_forced"] = True
                    _sel_trace["depth_followup_anchor"] = last_answer_fid
                    print(f"[depth_followup] anchor={last_answer_fid} → {chosen}", flush=True)
                elif depth_trigger_followup_frame:
                    # Emotional / plan / relationship signal detected — stay on topic with one
                    # short follow-up question rather than switching engines.
                    chosen = depth_trigger_followup_frame
                    chosen_turn_type = "loop_question"
                    listening_move_selected = "loop_question"
                    listening_move_reason = f"depth_trigger_{_depth_trigger_category}"
                    pending_listening_move = False
                    listening_wait_turns = 0
                    depth_trigger_followup_used = True
                    _sel_trace["depth_trigger_followup_used"] = True
                    _sel_trace["depth_trigger_category"] = _depth_trigger_category
                    print(f"[depth_trigger] {_depth_trigger_category} → {chosen} (budget={_depth_trigger_budget + 1})", flush=True)
                elif _meaningful_imperfect["should_clarify"]:
                    # Rich, multi-component answer with engine-specific keywords:
                    # prefer soft clarification over normal topic progression or engine switch.
                    chosen = _meaningful_imperfect["clarify_frame_id"]
                    chosen_turn_type = "question"
                    listening_move_selected = "meaningful_imperfect_clarify"
                    listening_move_reason = f"meaningful_imperfect: complex answer → {chosen}"
                    pending_listening_move = False
                    listening_wait_turns = 0
                    _sel_trace["meaningful_imperfect_fired"] = True
                    _sel_trace["meaningful_imperfect_clarify_frame"] = chosen
                    _sel_trace["block_engine_switch_once"] = True
                    print(f"[meaningful_imperfect] complex answer in '{last_answer_fid}' → {chosen}", flush=True)
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
                elif force_travel_bridge:
                    _ftb_frame = _select_next_frame_bridge(
                        current_engine, recent,
                        memory=memory, exchange_count=exchange_count,
                        engines_visited=engines_visited,
                        seeded_bridge_engines=["travel"],
                    )
                    if _ftb_frame:
                        chosen = _ftb_frame
                        chosen_turn_type = "question"
                        listening_move_selected = "bridge"
                        listening_move_reason = "strong_travel_intent"
                        pending_listening_move = False
                        listening_wait_turns = 0
                        print(f"[travel_override] strong_travel_intent → bridging to {chosen} (from {current_engine})", flush=True)
                    else:
                        print(f"[travel_override] strong_travel_intent fired but no travel frame available (engine={current_engine})", flush=True)
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

                # Name-story teaser → one elicit ("什么故事？") before age / ladder advance.
                if chosen is None and last_turn_was_answer and (not user_asked_question):
                    if last_answer_fid == "f_name_story" and _is_name_story_teaser_answer(answer_text):
                        _recent_eff = set(recent or [])
                        _elicit = "f_name_story_elicit"
                        if _elicit not in _recent_eff and _frame_deps_satisfied(_elicit, _recent_eff, list(recent or [])):
                            chosen = _elicit
                            chosen_turn_type = "question"
                            listening_move_selected = "name_story_teaser"
                            listening_move_reason = "teaser_answer_needs_elicit"
                            pending_listening_move = False
                            listening_wait_turns = 0

                # Pending-frame commitment (name-story burst): if the learner gave an
                # off-topic answer to the name-story question (e.g. age or place during
                # a burst), re-elicit the story once rather than silently advancing.
                # Does NOT fire when the learner asked a question or signalled a topic switch.
                if chosen is None and last_turn_was_answer and not user_asked_question:
                    if (
                        last_answer_fid == "f_name_story"
                        and not _is_explicit_topic_switch(answer_text)
                        and not _is_name_story_teaser_answer(answer_text)
                    ):
                        _ns_relevant_kw = (
                            "故事", "名字", "叫", "取", "英文", "家里", "意思",
                            "广东", "来自", "妈妈", "爸爸", "父母", "起的",
                        )
                        if not any(kw in answer_text for kw in _ns_relevant_kw):
                            _elicit_ns = "f_name_story_elicit"
                            # Treat the just-answered frame as already-seen so its dep is met
                            _recent_eff_ns = set(recent or []) | {last_answer_fid}
                            if _elicit_ns not in set(recent or []) and _frame_deps_satisfied(
                                _elicit_ns, _recent_eff_ns, list(_recent_eff_ns)
                            ):
                                chosen = _elicit_ns
                                chosen_turn_type = "question"
                                listening_move_selected = "name_story_offtopic"
                                listening_move_reason = "offtopic_pending_name_story"
                                pending_listening_move = False
                                listening_wait_turns = 0

                # Pending-frame commitment (work / place / family frames): if the learner
                # gave an off-topic answer to a protected question frame, stay in the same
                # engine rather than bridging to a cross-topic engine.  The counter-reply
                # section (above) already adds a "我是问：…" rephrase; this guard keeps
                # the next frame on-topic too.
                if chosen is None and last_turn_was_answer and not user_asked_question:
                    if (
                        last_answer_fid in _COMMITMENT_GUARD_FRAMES
                        and not _is_explicit_topic_switch(answer_text)
                        and not _is_relevant_to_frame(answer_text, last_answer_fid)
                    ):
                        _recent_eff_cg = set(recent or []) | {last_answer_fid}
                        _chosen_cg = _select_next_frame_ladder_avoiding(
                            current_engine,
                            list(_recent_eff_cg),
                            avoid_frame_ids=_WEAK_LOOP_FRAME_IDS,
                            memory=memory,
                            exchange_count=exchange_count,
                            engines_visited=engines_visited,
                        )
                        if _chosen_cg:
                            chosen = _chosen_cg
                            chosen_turn_type = (
                                "loop_question" if _is_loop_candidate(chosen) else "question"
                            )
                            listening_move_selected = "frame_commitment"
                            listening_move_reason   = "offtopic_pending_frame"
                            pending_listening_move  = False
                            listening_wait_turns    = 0

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
                        "probe_used": False,
                        "probe_suppressed_reason": None,
                        "probe_block_reason": _micro_probe_block_reason,
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
                        "depth_trigger_detected": depth_trigger_detected,
                        "depth_trigger_category": _depth_trigger_category,
                        "depth_trigger_followup_used": depth_trigger_followup_used,
                        "repair_attempt_count": _repair_attempt_count,
                        "repair_escalation_level": _repair_escalation_level,
                        "micro_probe_eligible": _micro_probe_eligible,
                        "micro_probe_candidate": _micro_probe_candidate,
                    }
                    if pending_listening_move or force_listening or chain_exceeded:
                        # Guard: don't ask bare "哪里？" when the learner's answer already contains
                        # an explicit Latin-script city name (e.g. "Dunedin").  The city is already
                        # known — the probe is redundant and blocks a more useful place follow-up.
                        if (
                            _micro_probe_candidate == "f_micro_probe_where"
                            and last_answer_fid in (
                                "f_live_where", "frame.location.live_question", "f_from_where"
                            )
                            and re.search(r"[A-Za-z]{3,}", answer_text or "")
                        ):
                            _micro_probe_candidate = None
                            _micro_probe_eligible = False
                            _micro_probe_block_reason = "city_already_given_latin"
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
                            # Step 0b: micro-probe probabilistic gate (~30% of eligible turns).
                            # Fires before slot-followup so short probes (为什么？哪里？etc.) appear
                            # occasionally even when slot-followup frames are available.
                            # Rate limited to 1 probe per 2 turns via _pick_micro_probe().
                            if (
                                _micro_probe_candidate
                                and not depth_trigger_followup_used
                                and not depth_trigger_detected
                            ):
                                _mp_gate_seed = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}/mp"
                                if _stable_gate(_mp_gate_seed) < 300:  # ~30% probability
                                    chosen = _micro_probe_candidate
                                    chosen_turn_type = "loop_question"
                                    listening_move_selected = "loop_question"
                                    listening_move_reason = "micro_probe"
                                    pending_listening_move = False
                                    listening_wait_turns = 0
                                    _sel_trace["probe_eligible"] = True
                                    _sel_trace["probe_used"] = True
                                    _sel_trace["probe_chosen"] = chosen
                                    _sel_trace["probe_path"] = "micro_probe_gate"
                            # Step 1: slot followup — strongest local signal (skipped if micro-probe fired)
                            if chosen is None:
                                chosen = _pick_slot_followup_frame_id(
                                    current_engine, slot_names, recent, memory, exchange_count=exchange_count,
                                    answer_text=answer_text, last_answer_fid=last_answer_fid,
                                    same_engine_chain_count=same_engine_chain_count,
                                    _trace=_sel_trace,
                                )
                            if chosen is not None and _sel_trace.get("probe_path") != "micro_probe_gate":
                                chosen = _maybe_frame_order_priority(
                                    current_engine, chosen, recent, memory, answer_text, last_answer_fid,
                                )
                            _sel_trace["slot_followup"] = chosen if _sel_trace.get("probe_path") != "micro_probe_gate" else None
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
                            # Only overwrite probe_eligible if a micro-probe hasn't already claimed it.
                            if not _sel_trace.get("probe_used"):
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
                        # Step 3b: micro-probe — short follow-up (为什么？哪里？etc.) for slot-based answers.
                        # Fires when: slot_names present, no depth trigger, no existing probe chosen, not rate-limited.
                        # Priority: lower than existing probes (Step 3), higher than bridge (Step 4).
                        if (
                            chosen is None
                            and _micro_probe_candidate
                            and not depth_trigger_followup_used
                            and not depth_trigger_detected
                        ):
                            chosen = _micro_probe_candidate
                            chosen_turn_type = "loop_question"
                            listening_move_selected = "loop_question"
                            listening_move_reason = "micro_probe"
                            pending_listening_move = False
                            listening_wait_turns = 0
                            _sel_trace["probe_eligible"] = True
                            _sel_trace["probe_used"] = True
                            _sel_trace["probe_chosen"] = chosen
                            _sel_trace["probe_path"] = "micro_probe_main"
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
                        # Micro-probe fallback: short curiosity probe (为什么？哪里？etc.) when slot_names present.
                        # Fires here (inside loop block) when no existing probe was selected.
                        if (
                            chosen is None
                            and _micro_probe_candidate
                            and not depth_trigger_followup_used
                            and not depth_trigger_detected
                        ):
                            chosen = _micro_probe_candidate
                            chosen_turn_type = "loop_question"
                            pending_listening_move = False
                            listening_wait_turns = 0
                            listening_move_selected = "loop_question"
                            listening_move_reason = "micro_probe"
                            _sel_trace["probe_eligible"] = True
                            _sel_trace["probe_used"] = True
                            _sel_trace["probe_chosen"] = chosen
                            _sel_trace["probe_path"] = "micro_probe_loop"
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

                # Additional closing-move block: confusion, frustration, continuation, ASR junk,
                # and turns immediately after a generic fallback.
                _cm_blocked_signal, _cm_blocked_reason = _is_closing_blocked_by_learner_signal(
                    answer_text, _prev_partner_text
                )

                # Suppressed-reason trace — always populated so every turn is auditable.
                if user_asked_question:
                    _closing_suppressed_reason = "user_asked_question"
                elif _cm_blocked_signal:
                    _closing_suppressed_reason = _cm_blocked_reason
                elif not _cm_late_session:
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
                    and not user_asked_question
                )
                _cm_extended = (
                    _cm_late_session
                    and _cm_substantive
                    and _cm_no_probe
                    and _cm_bridge_not_forced
                    and _cm_remaining_weak
                    and last_turn_was_answer
                    and (not user_asked_question)
                    # Depth trigger guard: if the answer contained emotional / plan /
                    # relationship signals, keep the conversation alive — don't close
                    # mid-disclosure just because the engine is nearly exhausted.
                    and not depth_trigger_detected
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
                if (_cm_original or _cm_extended or _cm_preemptible) and not user_asked_question and not _counter_reply and not _cm_blocked_signal:
                    _closing_move_fired = True
                    _closing_reason = "meaningful_answer_no_next_move"
                    _cl_trigger = "preemptible" if _cm_preemptible else ("extended" if _cm_extended else "original")
                    _cl_seed = f"{cs.get('session_id','')}/{len(recent)}/{current_engine}/closing"
                    # When the answer had emotional / health signals, use a warmer closing that
                    # includes a spoken follow-up question rather than a bare acknowledgement.
                    if _depth_trigger_category == "emotional":
                        _cl_zh, _cl_py, _cl_en = (
                            _stable_pick(_CLOSING_REACTIONS_EMOTIONAL, _cl_seed)
                            or _CLOSING_REACTIONS_EMOTIONAL[0]
                        )
                    elif (
                        # Food-warmth closing: when the answer contains food/family-food keywords,
                        # use a warmer closing instead of a flat acknowledgement.
                        answer_text
                        and any(kw in answer_text for kw in ("好吃", "羊肉", "饺子", "做饭", "妈妈的", "好味", "美食"))
                    ):
                        _cl_zh, _cl_py, _cl_en = (
                            _stable_pick(_CLOSING_REACTIONS_FOOD, _cl_seed)
                            or _CLOSING_REACTIONS_FOOD[0]
                        )
                    else:
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
                    _diag_finalize_response(_closing_response, _diag_cap)
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
                # High-priority selector choices (retirement clarification, travel dest
                # clarification, depth anchors) must never be overridden by the move_type
                # filter — their structural purpose overrides transition preferences.
                _mt_filter_exempt = (
                    listening_move_selected in (
                        "retire_clarify", "retired_pivot",
                        "travel_dest_clarify", "dest_confirmed",
                        "depth_anchor", "efc",
                    )
                    or listening_move_reason == "micro_probe"
                    or (chosen in _MICRO_PROBE_FRAME_IDS)
                )
                if last_answer_fid and chosen and not _mt_filter_exempt:
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
                    _typed_confusion = (
                        last_turn_was_answer
                        and not user_asked_question
                        and _is_confusion_signal(answer_text)
                    )
                    chosen = _apply_discourse_coherence_guard(
                        chosen,
                        cs=cs,
                        recent=recent,
                        last_answer=last_answer,
                        last_turn_was_answer=last_turn_was_answer,
                        learner_skip_confusion=(cs.get("learner_skip_confusion") is True),
                        typed_confusion=_typed_confusion,
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

                # Block-engine-switch-once guard: when meaningful_imperfect_fired, any bridge
                # that snuck through the dwell guard is also suppressed for this single turn.
                # Ensures the clarify frame is actually delivered before the engine exits.
                if chosen and listening_move_selected == "bridge" and _sel_trace.get("block_engine_switch_once"):
                    chosen = None
                    listening_move_selected = "none"
                    _sel_trace["bridge_rejected_reason"] = "block_engine_switch_once"

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
                    and not depth_trigger_followup_used  # depth-trigger empathy frames are not bridges
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
            # Travel ASR near-match: override frame_text with candidate-specific question
            # ("你是说甘肃吗？") when a near-match was detected, and persist/clear the
            # pending_dest_candidate in state so the next turn can detect a confirmation.
            _trav_cand  = locals().get("_travel_asr_candidate")   # may be None if not in selector path
            _dest_conf  = locals().get("_is_dest_confirmation", False)
            _pend_dest  = locals().get("_pending_dest", "")
            if _trav_cand and frame_id == "f_travel_dest_generic_clarify":
                response["frame_text"]    = f"你是说\u201c{_trav_cand}\u201d吗？"
                response["frame_pinyin"]  = f"nǐ shì shuō {_trav_cand} ma?"
                response["frame_text_en"] = f"Did you mean \u201c{_trav_cand}\u201d?"
                response.setdefault("state_update", {})
                response["state_update"]["pending_dest_candidate"] = _trav_cand
            elif _pend_dest:
                # Candidate existed but we're on a different frame — clear it.
                response.setdefault("state_update", {})
                response["state_update"]["pending_dest_candidate"] = None

            # ── Noisy location clarification: stay on the same location frame ─────
            # Escalates through three levels so the same question never repeats verbatim:
            #   retry 0 → standard rephrase   "我是问：你现在住的地方在哪里？"
            #   retry 1 → natural re-ask      "我没听清楚。你住的地方，离这里远吗？"
            #   retry 2+ → gentle move-on     "没关系，我们先说别的。你喜欢你住的地方吗？"
            # Counter is stored in conversation_state["location_retry_count"] (client-side).
            # Resets when learner gives a valid location, place-description, or confirmed re-ask.
            _nlc = locals().get("_noisy_location_clarify", False)

            # ── Participation-success escape: location-answer structure ───────────
            # The _noisy_location_clarify condition requires not _prev_counter_reply,
            # which is often non-empty in real sessions (the previous turn's persona
            # acknowledgement is stored as last_counter_reply).  When the learner
            # uses a structural location-answer pattern (我现在住在X / 我住在X / etc.)
            # on a location frame but the entity is unextractable, apply a two-level
            # intent escape so the conversation advances rather than looping:
            #   • retry_count = 0 → set _nlc=True so Level-0 rephrase fires (no bare loop)
            #   • retry_count ≥ 1 → advance directly to "哦，我知道了。你喜欢你现在住的地方吗？"
            # Conceptual rule: intent confidence can be high even when entity confidence is low.
            if not _nlc and isinstance(locals().get("last_answer"), dict):
                _la_fid_ps = (last_answer.get("frame_id") or "").strip()
                if _la_fid_ps in {"f_live_where", "f_from_where", "frame.location.live_question"}:
                    _t_ps = (_last_text_for_counter or "").strip()
                    if (
                        _t_ps
                        and _looks_like_location_answer_structure(_t_ps)
                        and _extract_open_world_location(_t_ps, frame_is_residence=True) is None
                    ):
                        _cs_ps    = payload.get("conversation_state") if isinstance(payload.get("conversation_state"), dict) else {}
                        _retry_ps = int(_cs_ps.get("location_retry_count") or 0)
                        if _retry_ps >= 1:
                            # Learner has already tried once with the right structure.
                            # Treat as conversational success — advance to place follow-up.
                            _like_frame_ps = _frames_by_id.get("f_place_like_there") or {}
                            _like_opts_ps  = _like_frame_ps.get("options", []) if _like_frame_ps else []
                            response["frame_text"]    = "哦，我知道了。你喜欢你现在住的地方吗？"
                            response["frame_text_en"] = "Oh, I see. Do you like where you live now?"
                            response["frame_pinyin"]  = "ó, wǒ zhīdào le. nǐ xǐhuān nǐ xiànzài zhù de dìfāng ma?"
                            response["frame_id"]      = "f_place_like_there"
                            if _like_opts_ps:
                                response["options"]   = _like_opts_ps
                            _su_ps = response.setdefault("state_update", {})
                            _su_ps["location_retry_count"]  = 0
                            _su_ps["location_clarify_hint"] = ""
                        else:
                            # retry_count = 0: fire the standard rephrase path, not a bare loop
                            _nlc = True

            if _nlc and isinstance(last_answer, dict):
                _orig_loc_fid  = (last_answer.get("frame_id") or "").strip()
                _cs_nlc        = payload.get("conversation_state") if isinstance(payload.get("conversation_state"), dict) else {}
                _prev_ft_nlc   = (_cs_nlc.get("last_partner_frame_text") or "").strip()
                _loc_retry     = int(_cs_nlc.get("location_retry_count") or 0)
                _rephrase_nlc  = _clarify_app_question(_prev_ft_nlc) if _prev_ft_nlc else None
                # Restore original frame's options (shared by levels 0 and 1)
                _orig_loc_opts: list = []
                if _orig_loc_fid:
                    _orig_loc_fo   = _frame_options.get(_orig_loc_fid) or {}
                    _orig_loc_opts = (_orig_loc_fo.get("options", []) if isinstance(_orig_loc_fo, dict) else [])
                if _loc_retry == 0 and _rephrase_nlc:
                    # Level 0 — first noisy attempt: standard rephrase of original question
                    response["frame_text"]    = _rephrase_nlc[0]
                    response["frame_text_en"] = _rephrase_nlc[1]
                    response["frame_pinyin"]  = ""
                    if _orig_loc_opts:
                        response["options"]  = _orig_loc_opts
                        response["frame_id"] = _orig_loc_fid
                    response.setdefault("state_update", {})["location_clarify_hint"] = "active"
                elif _loc_retry == 1:
                    # Level 1 — second noisy attempt: natural re-ask (no template coaching)
                    response["frame_text"]    = "我没听清楚。你住的地方，离这里远吗？"
                    response["frame_text_en"] = "I didn't quite catch that. Is where you live far from here?"
                    response["frame_pinyin"]  = "wǒ méi tīng qīngchǔ. nǐ zhù de dìfāng, lí zhèlǐ yuǎn ma?"
                    if _orig_loc_opts:
                        response["options"]  = _orig_loc_opts
                        response["frame_id"] = _orig_loc_fid
                    response.setdefault("state_update", {})["location_clarify_hint"] = "active"
                else:
                    # Level 2+ — third+ noisy attempt: gentle pivot to an adjacent softer question
                    _like_frame = _frames_by_id.get("f_place_like_there") or {}
                    _like_opts  = _like_frame.get("options", []) if _like_frame else []
                    response["frame_text"]    = "没关系，我们先说别的。你喜欢你住的地方吗？"
                    response["frame_text_en"] = "That's okay, let's talk about something else. Do you like where you live?"
                    response["frame_pinyin"]  = "méiguānxi, wǒmen xiān shuō biéde. nǐ xǐhuān nǐ zhù de dìfāng ma?"
                    response["frame_id"]      = "f_place_like_there"
                    if _like_opts:
                        response["options"] = _like_opts
                    response.setdefault("state_update", {})["location_clarify_hint"] = ""
                # Always advance the retry counter so the next noisy attempt moves to the next level.
                response.setdefault("state_update", {})["location_retry_count"] = _loc_retry + 1

            # Phase 13A: slot substitution — fill {CITY}/{PLACE}/{HOMETOWN}/[CITY]/[HOMETOWN] from learner memory
            _needs_city_slot = (
                any(tok in (response.get("frame_text") or "") for tok in ("{CITY}", "{PLACE}", "{HOMETOWN}"))
                or any(tok in (response.get("frame_pinyin") or "") for tok in ("{CITY}", "{HOMETOWN}"))
            )
            if _needs_city_slot:
                _slot_mem = memory if isinstance(memory, dict) else None
                if _slot_mem is None and _lm_load:
                    _cs_sl = payload.get("conversation_state") if isinstance(payload.get("conversation_state"), dict) else {}
                    _sl_lid = (_cs_sl.get("learner_id") or "").strip()
                    if _sl_lid:
                        _slot_mem = _lm_load(_sl_lid)
                if isinstance(_slot_mem, dict):
                    # {CITY}/{PLACE}: current residence (lives_in → hometown fallback)
                    _city = (_slot_mem.get("lives_in") or _slot_mem.get("hometown") or "").strip()
                    # Repair/normalise before it reaches a template: a corrupted stored
                    # value ("等你等新西兰的南方") must never fill a learner-facing frame.
                    if _city:
                        _city = _repair_asr_junk_text(_city)
                        if _normalize_place_name:
                            _city = _normalize_place_name(_city) or _city
                    if _city:
                        for _tok in ("{CITY}", "{PLACE}"):
                            if _tok in (response.get("frame_text") or ""):
                                response["frame_text"] = response["frame_text"].replace(_tok, _city)
                        if "{CITY}" in (response.get("frame_pinyin") or ""):
                            response["frame_pinyin"] = response["frame_pinyin"].replace("{CITY}", _city)
                        if "[CITY]" in (response.get("frame_text_en") or ""):
                            response["frame_text_en"] = response["frame_text_en"].replace("[CITY]", _city)
                    # {HOMETOWN}: specifically the origin/hometown place
                    _hometown = (_slot_mem.get("hometown") or "").strip()
                    if _hometown:
                        _hometown = _repair_asr_junk_text(_hometown)
                        if _normalize_place_name:
                            _hometown = _normalize_place_name(_hometown) or _hometown
                    if _hometown:
                        if "{HOMETOWN}" in (response.get("frame_text") or ""):
                            response["frame_text"] = response["frame_text"].replace("{HOMETOWN}", _hometown)
                        if "{HOMETOWN}" in (response.get("frame_pinyin") or ""):
                            response["frame_pinyin"] = response["frame_pinyin"].replace("{HOMETOWN}", _hometown)
                        if "[HOMETOWN]" in (response.get("frame_text_en") or ""):
                            response["frame_text_en"] = response["frame_text_en"].replace("[HOMETOWN]", _hometown)
                # Safety net: if any slot token survived (no memory or memory load failed),
                # prefer last_place_subject if the frame question is about a known place;
                # otherwise use a context-aware generic so the raw placeholder never leaks.
                # Context rules: food → 你那儿; special/features → 你住的地方;
                # travel/been-to → 那里; default → 那儿.
                _cs_lps_fallback = (cs.get("last_place_subject") or "") if isinstance(cs, dict) else ""
                for _tok in ("{CITY}", "{PLACE}", "{HOMETOWN}"):
                    _ft_cur = response.get("frame_text") or ""
                    if _tok in _ft_cur:
                        if _cs_lps_fallback:
                            _city_fb = _cs_lps_fallback
                        elif "好吃" in _ft_cur:
                            _city_fb = "你那儿"
                        elif "特别" in _ft_cur:
                            _city_fb = "你住的地方"
                        elif "去过" in _ft_cur or "想去" in _ft_cur:
                            _city_fb = "那里"
                        else:
                            _city_fb = "那儿"
                        response["frame_text"] = _ft_cur.replace(_tok, _city_fb)
                    if _tok in (response.get("frame_pinyin") or ""):
                        response["frame_pinyin"] = response["frame_pinyin"].replace(_tok, "nàr")
                for _en_tok, _en_fb in (("[CITY]", "there"), ("[HOMETOWN]", "there")):
                    if _en_tok in (response.get("frame_text_en") or ""):
                        response["frame_text_en"] = response["frame_text_en"].replace(_en_tok, _en_fb)
            # Safety net: {NAME} slot — fill from persona display_name; never reach the learner as raw token.
            if "{NAME}" in (response.get("frame_text") or ""):
                _name_fill = _assistant_name_from_persona(persona) if persona else ""
                response["frame_text"] = response["frame_text"].replace("{NAME}", _name_fill or "我")
            # Safety net: {TIME} slot — no resolver exists yet; fall back to 最近 so it never leaks raw.
            for _tf in ("frame_text", "frame_pinyin", "frame_text_en"):
                _tv = response.get(_tf) or ""
                if "{TIME}" in _tv:
                    response[_tf] = _tv.replace("{TIME}", "最近")
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
                    # Clarification moves (retire_clarify, etc.) must not be prefixed with enthusiasm — it sounds wrong.
                    _reaction_is_question = "？" in reaction_prefix_text
                    _clarify_move = listening_move_selected in ("retire_clarify", "retired_pivot", "travel_dest_clarify")
                    # Guard: never prepend a reaction prefix when the frame_text is itself a clarification
                    # (generated by the NLC or pending-frame clarification paths).  Prepending "哦，X！"
                    # in front of "我是问：…" would embed the echo inside the clarification — producing
                    # "哦，等你等！我是问：哦，等你等！离那儿远吗？".
                    _ft_now = response.get("frame_text") or ""
                    _is_clarify_frame = any(_ft_now.startswith(p) for p in (
                        "我是问：", "我是在问：", "我刚刚问的是：", "我的意思是：",
                        "我没听清楚", "没关系，我们先说别的",
                    ))
                    if "？" in (frame_rec.get("text") or "") and not _reaction_is_question and not _clarify_move and not _is_clarify_frame:
                        _ft = response["frame_text"]
                        # Dedup: strip leading discourse marker from frame_text when reaction already has one.
                        # Prevents "哦，真有意思！哦，是什么故事？" → "哦，真有意思！是什么故事？"
                        _DM_PREFIXES = ("哦，", "哦！", "啊，", "啊！", "嗯，", "嗯！", "呀，", "呀！", "唉，")
                        _rxn_has_dm = any(dm[:1] in reaction_prefix_text for dm in _DM_PREFIXES)
                        if _rxn_has_dm:
                            for _dm in _DM_PREFIXES:
                                if _ft.startswith(_dm):
                                    _ft = _ft[len(_dm):]
                                    break
                        response["frame_text"] = f"{reaction_prefix_text}{_ft}"
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
                    # Track recent persona replies for exact-repeat suppression (keep last 3).
                    _updated_recent = (_recent_persona_replies + [_counter_reply])[-3:]
                    response["state_update"]["recent_persona_replies"] = _updated_recent

                # E4: emit topic handoff engine when a confident answer was produced.
                # Writing current_engine into state_update causes the client to track this
                # engine for the next /api/next_question call, keeping the conversation on
                # the learner's redirected topic instead of snapping back to the old ladder.
                if _e4_engine_handoff:
                    response["state_update"] = response.get("state_update") or {}
                    response["state_update"]["current_engine"] = _e4_engine_handoff

                # ── Blue panel — pre-computation (trigger flags) ───────────────
                # Consecutive app questions: how many back-to-back app questions the
                # learner has answered without asking one themselves.
                # Reset when: learner asked, OR discovery panel is shown this turn.
                _prev_consec_q     = int((cs.get("consecutive_app_questions") or 0) if isinstance(cs, dict) else 0)
                _consec_q_next     = 0 if user_asked_question else _prev_consec_q + 1

                # Was there a persona reveal in the PREVIOUS turn?
                # (set in state_update last turn via _this_persona_reveal below)
                _prev_persona_reveal = bool((cs.get("last_persona_reveal") or False) if isinstance(cs, dict) else False)

                # Rate-limit: was discovery shown last turn? Avoid back-to-back panels.
                _discovery_recent  = bool((cs.get("discovery_shown_last_turn") or False) if isinstance(cs, dict) else False)

                # Does THIS turn's counter_reply or reaction carry concrete persona content?
                # Stored so next turn's trigger knows to show proactive discovery.
                _this_persona_reveal = (
                    _has_persona_reveal(_counter_reply or "")
                    or _has_persona_reveal(reaction_prefix_text or "")
                )

                # Proactive discovery fires when:
                #   Trigger 2: persona revealed rich content last turn, OR
                #   Trigger 3: app has asked 1+ consecutive questions without learner asking back
                #              (lowered from 2 so discovery appears after the first unanswered
                #               question — the previous >=2 kept the panel silent for 3+ turns)
                # Guards: not shown recently, persona has facts, user didn't ask (handled separately)
                _trigger_proactive = (
                    last_turn_was_answer
                    and not user_asked_question
                    and not _counter_reply
                    and bool(_persona_backed_topics(persona))
                    and (_prev_persona_reveal or _prev_consec_q >= 1)
                )

                # Shared state: topics seen in recent turns (dedup / deprioritisation)
                _seen_topics_disc: set = set(cs.get("recently_seen_disc_topics") or []) if isinstance(cs, dict) else set()

                # Distance/orientation boost: when learner mentioned an overseas or unfamiliar
                # place, promote place-distance topics to the front of the discovery pool so
                # questions like "离那儿远吗？" / "从你那儿到那边要多久？" appear in the top 3.
                # Also switch the pool engine to "place" if current engine is identity (since
                # identity engine's pool otherwise lacks enough distance questions).
                _overseas_detected  = _learner_place_is_overseas(answer_text)
                _dist_boost: frozenset = _PLACE_DISTANCE_TOPICS if _overseas_detected else frozenset()

                # ── Blue panel shared context (used for relevance-ranked discovery) ──
                # frame_text:    current/last app frame question — strongest relevance signal.
                # context_prev:  previous turn's persona counter_reply — carries topic signal
                #                into the next turn when proactive discovery fires.
                # context_text per path:
                #   Path 0 (confusion):  last frame text is already in frame_text; no extra answer
                #   Path 1 (user asked): persona's counter_reply is the richest context
                #   Path 2 (proactive):  learner answer + previous persona reveal if available
                #   Path 4 (fallback):   same as Path 2
                _disc_frame_text  = (cs.get("last_partner_frame_text") or "").strip() if isinstance(cs, dict) else ""
                _disc_context_prev = (cs.get("last_counter_reply") or "").strip() if isinstance(cs, dict) else ""
                # Same-turn partner line (frame or counter_reply) for immediate adjacency ranking.
                _disc_same_turn = _discovery_context_merge(
                    (response.get("frame_text") or "").strip(),
                    (_counter_reply or "").strip(),
                )

                # Local probe boost: recent learner answer (+ prior context) surfaces
                # place/work/family/travel/food follow-ups before generic fallbacks.
                _probe_ctx_base = _discovery_context_merge(
                    answer_text, _disc_context_prev,
                )
                _local_boost = _infer_local_probe_boost_topics(_probe_ctx_base)
                _all_boost: frozenset = _dist_boost | _local_boost

                # ── Blue panel debug trace ─────────────────────────────────────
                _dbg_last_pf_pre = (cs.get("last_partner_frame_id") or "").strip()
                _dbg_in_recip    = _dbg_last_pf_pre in _RECIPROCAL_FRAME_TO_Q
                print(
                    f"[blue_panel_debug] "
                    f"user_asked_question={user_asked_question} | "
                    f"counter_reply={'YES' if _counter_reply else 'NO'} | "
                    f"last_turn_was_answer={last_turn_was_answer} | "
                    f"consec_q={_prev_consec_q} | prev_reveal={_prev_persona_reveal} | "
                    f"proactive={_trigger_proactive} | recent={_discovery_recent} | "
                    f"last_partner_frame_id={_dbg_last_pf_pre!r} | in_reciprocal_map={_dbg_in_recip}"
                )
                # ──────────────────────────────────────────────────────────────

                # ── Path 0: Learner confused about app question → clarify + discovery ──
                # The counter_reply already holds the rephrase (_clarify_app_question).
                # Show discovery cards so the learner has agency — they can choose a question
                # they understand instead of being stuck on a confusing frame.
                if _confusion_about_app_q and bool(_persona_backed_topics(persona)):
                    _disc_eng    = (current_engine or engine_id or "").strip().lower()
                    _backed_tpcs = _persona_backed_topics(persona)
                    _rich_engs   = _persona_rich_engines(persona)
                    # Overseas: switch to place engine so full distance pool is available
                    _disc_eng_p0 = "place" if (_overseas_detected and _disc_eng in ("identity",)) else _disc_eng
                    _disc_pool   = _build_discovery_pool(
                        _disc_eng_p0, _backed_tpcs, _rich_engs, _seen_topics_disc,
                        boost_topics=_all_boost,
                        frame_text=_disc_frame_text, context_text=answer_text or "",
                    )
                    if _disc_pool:
                        response["discovery_questions"] = _disc_pool[:3]
                        response["user_led"] = True
                        _shown_topics = [q.get("topic") for q in _disc_pool[:3] if q.get("topic")]
                        response.setdefault("state_update", {})["recently_seen_disc_topics"] = _shown_topics
                        print(
                            f"[blue_panel_debug] SHOWN (confusion_clarification) | engine={_disc_eng!r} | "
                            f"{len(_disc_pool[:3])} card(s)"
                        )
                    else:
                        print(f"[blue_panel_debug] NOT SHOWN (confusion_clarification) | reason=no_questions_for_engine")

                # ── Path 1: User asked a question AND persona replied ──────────
                # Show the full discovery pool so the learner can keep interviewing.
                # Engine override: match the follow-up engine to what the persona just revealed.
                elif user_asked_question and _counter_reply:
                    _disc_eng    = (current_engine or engine_id or "").strip().lower()
                    _backed_tpcs = _persona_backed_topics(persona)
                    _rich_engs   = _persona_rich_engines(persona)
                    _reply_for_eng = (_counter_reply or "")
                    _disc_eng_p1 = _resolve_discovery_engine_for_context(
                        _disc_eng,
                        _discovery_context_merge(answer_text, _reply_for_eng),
                        overseas_detected=_overseas_detected,
                        reply_for_eng=_reply_for_eng,
                    )
                    # Path 1: user's own question is the "frame"; persona reply is rich context
                    _disc_pool   = _build_discovery_pool(
                        _disc_eng_p1, _backed_tpcs, _rich_engs, _seen_topics_disc,
                        boost_topics=_all_boost,
                        frame_text=answer_text or _disc_frame_text,
                        context_text=_discovery_context_merge(
                            answer_text, _counter_reply, _disc_same_turn,
                        ),
                    )

                    if _disc_pool:
                        # Path 1 (user asked + persona replied) is the richest context: allow up
                        # to 4 discovery questions so the client can build a 5-question panel when
                        # combined with answer-reactive extras from _augmentQuestionsFromAnswer.
                        _dq_slice = _disc_pool[:4]
                        response["discovery_questions"] = _dq_slice
                        response["user_led"] = True
                        _shown_topics = [q.get("topic") for q in _dq_slice if q.get("topic")]
                        response.setdefault("state_update", {})["recently_seen_disc_topics"] = _shown_topics
                        _backed_count = sum(1 for q in _dq_slice if q.get("topic") in _backed_tpcs)
                        print(
                            f"[blue_panel_debug] SHOWN (discovery/learner-asked) | engine={_disc_eng!r} | "
                            f"backed={_backed_count}/{len(_dq_slice)} | {len(_dq_slice)} card(s)"
                        )
                    else:
                        print(f"[blue_panel_debug] NOT SHOWN | reason=no_questions_for_engine | engine={_disc_eng!r}")
                    # Phase 12E: targeted follow-up hint from persona's reply keywords
                    _disc_hint = _pick_contextual_discovery_hint(_counter_reply)
                    if _disc_hint:
                        response["discovery_hint"] = _disc_hint

                # ── Path 2: Proactive trigger (persona-reveal or question-count) ──
                # Fires when the persona revealed rich content last turn (learner should
                # be curious), or the app has dominated the last 2+ turns (give learner agency).
                elif _trigger_proactive:
                    _disc_eng    = (current_engine or engine_id or "").strip().lower()
                    _backed_tpcs = _persona_backed_topics(persona)
                    _rich_engs   = _persona_rich_engines(persona)
                    # Path 2: combine current answer + previous persona reveal so that
                    # food/place/work keywords from the persona's previous turn carry forward.
                    _ctx_p2 = _discovery_context_merge(
                        answer_text, _counter_reply, _disc_context_prev, _disc_same_turn,
                    )
                    _disc_eng_p2 = _resolve_discovery_engine_for_context(
                        _disc_eng, _ctx_p2, overseas_detected=_overseas_detected,
                    )
                    _disc_pool   = _build_discovery_pool(
                        _disc_eng_p2, _backed_tpcs, _rich_engs, _seen_topics_disc,
                        boost_topics=_all_boost,
                        frame_text=_disc_frame_text or _disc_same_turn,
                        context_text=_ctx_p2,
                    )

                    if _disc_pool:
                        response["discovery_questions"] = _disc_pool[:3]
                        response["user_led"] = True
                        _shown_topics = [q.get("topic") for q in _disc_pool[:3] if q.get("topic")]
                        response.setdefault("state_update", {})["recently_seen_disc_topics"] = _shown_topics
                        _trigger_reason = "persona_reveal" if _prev_persona_reveal else "question_suppression"
                        print(
                            f"[blue_panel_debug] SHOWN (proactive/{_trigger_reason}) | engine={_disc_eng!r} | "
                            f"consec_q={_prev_consec_q} | {len(_disc_pool[:3])} card(s)"
                        )
                    else:
                        print(f"[blue_panel_debug] NOT SHOWN (proactive) | reason=no_questions_for_engine")

                # ── Path 3: Reciprocal fallback (existing single-card path) ──────
                # Only fires when proactive didn't trigger — specific frames that
                # naturally invite a "and you?" follow-up.
                elif last_turn_was_answer and not user_asked_question and not _counter_reply:
                    _last_pf = (cs.get("last_partner_frame_id") or "").strip()
                    _rec_q   = _RECIPROCAL_FRAME_TO_Q.get(_last_pf)
                    if _rec_q:
                        response["discovery_questions"] = [_rec_q]
                        response["user_led"] = True
                        print(f"[blue_panel_debug] SHOWN (reciprocal) | frame={_last_pf!r} | q={_rec_q.get('zh','?')!r}")
                    else:
                        _reason = "no_reciprocal_mapping" if _last_pf else "no_last_partner_frame"
                        print(f"[blue_panel_debug] NOT SHOWN | reason={_reason} | frame={_last_pf!r}")

                # ── Path 4: Persistent fallback — always-available learner agency ──
                # Blue questions are not an occasional bonus; they are the primary
                # learner-agency layer. If none of the specialised paths above fired,
                # still generate a small set of relevant questions.
                else:
                    _has_backed = bool(_persona_backed_topics(persona))
                    if _has_backed and not user_asked_question:
                        _disc_eng    = (current_engine or engine_id or "").strip().lower()
                        _backed_tpcs = _persona_backed_topics(persona)
                        _rich_engs   = _persona_rich_engines(persona)
                        _ctx_p4 = _discovery_context_merge(
                            answer_text, _disc_context_prev, _disc_same_turn,
                        )
                        _disc_eng_p4 = _resolve_discovery_engine_for_context(
                            _disc_eng, _ctx_p4, overseas_detected=_overseas_detected,
                        )
                        _disc_pool   = _build_discovery_pool(
                            _disc_eng_p4, _backed_tpcs, _rich_engs, _seen_topics_disc,
                            boost_topics=_all_boost,
                            frame_text=_disc_frame_text or _disc_same_turn,
                            context_text=_ctx_p4,
                        )
                        if _disc_pool:
                            response["discovery_questions"] = _disc_pool[:3]
                            response["user_led"] = True
                            _shown_topics = [q.get("topic") for q in _disc_pool[:3] if q.get("topic")]
                            response.setdefault("state_update", {})["recently_seen_disc_topics"] = _shown_topics
                            _dbg_reason = "persistent_fallback"
                            print(f"[blue_panel_debug] SHOWN ({_dbg_reason}) | engine={_disc_eng!r} | {len(_disc_pool[:3])} card(s)")
                        else:
                            print(f"[blue_panel_debug] NOT SHOWN (persistent_fallback) | reason=empty_pool")
                    else:
                        if not last_turn_was_answer:
                            _dbg_reason = "not_an_answer_turn"
                        elif user_asked_question and not _counter_reply:
                            _dbg_reason = "user_asked_question_but_no_counter_reply"
                        elif not _has_backed:
                            _dbg_reason = "no_persona_backed_topics"
                        else:
                            _dbg_reason = "no_trigger_condition_met"
                        print(f"[blue_panel_debug] NOT SHOWN | reason={_dbg_reason}")

                # ── Post-trigger state tracking ────────────────────────────────
                # Always record for next turn, regardless of which path fired.
                _su = response.setdefault("state_update", {})
                _su["last_persona_reveal"]       = _this_persona_reveal
                _su["discovery_shown_last_turn"] = bool(response.get("user_led"))
                # Persist frame question text so next turn can rephrase it if learner is confused.
                _su["last_partner_frame_text"]   = (response.get("frame_text") or "").strip()

                # ── last_place_subject anchoring ─────────────────────────────
                # Track the active place subject so deictic 那里/那边 references can
                # be resolved on the next turn without ambiguity.
                # Scan counter_reply zh + frame_text for known place names.
                _lps_text = " ".join(filter(None, [
                    (response.get("counter_reply") or {}).get("zh", "") if isinstance(response.get("counter_reply"), dict) else "",
                    response.get("frame_text") or "",
                    (response.get("counter_reply") or "") if isinstance(response.get("counter_reply"), str) else "",
                ]))
                _prev_lps = (cs.get("last_place_subject") or "") if isinstance(cs, dict) else ""
                _new_lps = ""
                # Extended place list: NZ + NZ regions explicitly for the tests.
                _LPS_PLACES: tuple = (
                    "南新西兰", "新西兰南部", "新西兰",
                    "西藏", "云南", "成都", "重庆", "广州", "深圳",
                    "苏州", "杭州", "西安", "南京", "武汉", "厦门", "青岛",
                    "丽江", "桂林", "三亚", "哈尔滨", "乌鲁木齐", "九寨沟",
                    "黄山", "张家界", "敦煌", "西双版纳", "大理",
                    "香港", "澳门", "台湾",
                    "北京", "上海",
                    "日本", "法国", "泰国", "韩国", "欧洲", "越南", "新加坡",
                    "澳大利亚", "澳洲", "美国", "英国", "德国", "加拿大",
                )
                for _lps_p in _LPS_PLACES:
                    if _lps_p in _lps_text:
                        _new_lps = _lps_p
                        break

                # ── Fix 3: preserve learner-provided facts (open-world) ────────────────
                # A residence the learner stated (even an unknown place like "达尼丁") is a
                # conversational fact distinct from app-generated knowledge — store it
                # verbatim so it: (a) is not re-requested, (b) remains available for later
                # deictic reference ("那儿"/"那边" in "离那儿远吗？"), and (c) is never
                # overwritten just because it isn't in any internal place database.
                _prev_learner_loc = (cs.get("learner_stated_location") or "") if isinstance(cs, dict) else ""
                _learner_loc_this_turn = ""
                if last_turn_was_answer and answer_text and (
                    last_answer_fid in _RESIDENCE_QUESTION_FRAME_IDS
                ):
                    _learner_loc_this_turn = (
                        _extract_open_world_location(answer_text, frame_is_residence=True) or ""
                    )
                _su["learner_stated_location"] = _learner_loc_this_turn or _prev_learner_loc

                # A learner-supplied unknown/open-world location takes priority as the
                # active deictic place subject over the fixed known-place scan above —
                # it is the most recently learner-stated place and the ladder's next
                # questions (离那儿远吗？ etc.) refer back to it.
                if _learner_loc_this_turn:
                    _new_lps = _learner_loc_this_turn

                # Learner-provided food facts (Fix 3) — preserved verbatim regardless of
                # whether the mentioned foods are in any internal vocabulary.
                _prev_learner_food = (cs.get("learner_food_note") or "") if isinstance(cs, dict) else ""
                _su["learner_food_note"] = (
                    answer_text if (last_turn_was_answer and _responsive_food_answer and answer_text)
                    else _prev_learner_food
                )

                # Only update last_place_subject when a place is actually mentioned.
                _su["last_place_subject"] = _new_lps if _new_lps else _prev_lps
                # Reset consecutive question count when learner asked or discovery shown
                if "consecutive_app_questions" not in _su:
                    _su["consecutive_app_questions"] = 0 if bool(response.get("user_led")) else _consec_q_next
                # Confirmed re-ask: propagate counter resets to client state so next turn
                # starts with a clean repair/confusion ladder.
                if _confirmed_re_ask:
                    _su["repair_attempt_count"]        = 0
                    _su["mirror_confusion_count"]       = 0
                    _su["recent_confusion_count"]       = 0
                    _su["consecutive_not_understood"]   = 0
                    _su["location_clarify_hint"]        = ""
                    _su["location_retry_count"]         = 0
                # Clear location retry when learner supplied a genuine place name or description.
                # Guard with `not _nlc` so a garbled echo ("等你等" extracted as CITY) doesn't
                # accidentally reset the counter we just incremented in the noisy-location block.
                # `_nlc` is the resolved flag (may be True from the participation-success escape even
                # when the original _noisy_location_clarify variable was never set) so we use it here
                # to ensure the escape-fired path is also guarded correctly.
                _echo_trig = locals().get("_echo_triggered_by")
                if _echo_trig in ("CITY", "PLACE_DESC") and not _nlc:
                    _su["location_retry_count"] = 0

                # ── Blue-question debug trace (exposed in response) ──────────
                _dq_rendered = response.get("discovery_questions") or []
                response["blue_question_trace"] = {
                    "blue_questions_rendered":          len(_dq_rendered),
                    "blue_questions_topics":            [q.get("topic", "") for q in _dq_rendered],
                    "blue_questions_source":            (
                        "confusion_clarification" if (_confusion_about_app_q and bool(_dq_rendered)) else
                        "learner_asked" if (user_asked_question and _counter_reply and bool(_dq_rendered)) else
                        "proactive" if (_trigger_proactive and bool(_dq_rendered)) else
                        "persistent_fallback" if bool(_dq_rendered) else
                        "none"
                    ),
                    "blue_questions_suppressed_reason": (
                        None if bool(_dq_rendered) else
                        "no_persona_backed_topics" if not bool(_persona_backed_topics(persona)) else
                        "empty_pool"
                    ),
                    "persona_followup_available":       bool(_this_persona_reveal),
                    "consecutive_app_questions":        _consec_q_next,
                    "overseas_detected":                _overseas_detected,
                }

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
                # Depth-trigger follow-up budget: increment when a trigger follow-up was used this
                # turn; reset to 0 otherwise (no trigger, or trigger fired but no frame found).
                response["depth_trigger_followup_count"] = (
                    _depth_trigger_budget + 1 if depth_trigger_followup_used else 0
                )
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

            # ── Session-end blue questions ─────────────────────────────────
            # When the session is complete (no next_question), still generate
            # discovery questions so the learner has agency prompts for "next time."
            if not payload.get("next_question") and not response.get("discovery_questions"):
                _cs_end = payload.get("conversation_state") if isinstance(payload.get("conversation_state"), dict) else {}
                _partner_id_end = _cs_end.get("partner_id") or payload.get("partner_id") or ""
                _persona_end = _resolve_persona(_partner_id_end) if _partner_id_end else None
                if _persona_end and _persona_backed_topics(_persona_end):
                    _backed_end = _persona_backed_topics(_persona_end)
                    _rich_end   = _persona_rich_engines(_persona_end)
                    _seen_end: set = set(_cs_end.get("recently_seen_disc_topics") or [])
                    _disc_pool_end = _build_discovery_pool("place", _backed_end, _rich_end, _seen_end)
                    if _disc_pool_end:
                        response["discovery_questions"] = _disc_pool_end[:3]
                        response["user_led"] = True
                        response["session_end_questions"] = True
                        print(f"[blue_panel_debug] SHOWN (session_end) | {len(_disc_pool_end[:3])} card(s)")
                    else:
                        print("[blue_panel_debug] NOT SHOWN (session_end) | reason=empty_pool")

            # ── Final repair guard: no ASR-junk fragment (等你等 …) may reach the ───
            # learner in any rendered Chinese line, whatever path produced it.
            if isinstance(response.get("frame_text"), str):
                response["frame_text"] = _repair_asr_junk_text(response["frame_text"])
            _cr_final = response.get("counter_reply")
            if isinstance(_cr_final, str):
                response["counter_reply"] = _repair_asr_junk_text(_cr_final)
            elif isinstance(_cr_final, dict) and isinstance(_cr_final.get("zh"), str):
                _cr_final["zh"] = _repair_asr_junk_text(_cr_final["zh"])

            _diag_finalize_response(response, _diag_cap)
            data = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/end_session":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                sess = json.loads(body)
            except Exception:
                sess = {}

            # engines_used arrives as a JSON array (Set serialised by the frontend)
            engines = sess.get("engines_used")
            if not isinstance(engines, list):
                engines = []

            mode       = (sess.get("mode") or "normal").strip().lower()
            session_id = (sess.get("session_id") or "").strip()
            tier       = (sess.get("tier") or "standard").strip().lower()
            if tier not in ("standard", "premium"):
                tier = "standard"
            persona_id = (sess.get("persona_id") or "").strip() or None
            try:
                duration_seconds = max(0, int(sess.get("duration_seconds", 0) or 0))
            except (TypeError, ValueError):
                duration_seconds = 0

            metrics = _compute_scorecard(sess)
            progress_snapshot = _build_progress_snapshot(
                sess,
                metrics,
                tier=tier,
                persona_id=persona_id,
                duration_seconds=duration_seconds,
            )
            learner_id = (sess.get("learner_id") or progress_snapshot.get("learner_id") or "").strip()
            if learner_id and _ps_save_snapshot:
                try:
                    _ps_save_snapshot(learner_id, progress_snapshot)
                    print(
                        f"[ui_server] /api/end_session: progress saved for learner_id={learner_id!r}",
                        flush=True,
                    )
                except Exception as exc:
                    print(
                        f"[ui_server] /api/end_session: progress save failed: {exc}",
                        flush=True,
                    )
            print(
                f"[ui_server] /api/end_session session_id={session_id!r} mode={mode!r} "
                f"turns={sess.get('total_turns', 0)} flow={metrics['flow']['label']!r}",
                flush=True,
            )
            _turb_raw = metrics.get("turbulence", {}).get("raw_events", 0)
            _turb_per = metrics.get("turbulence", {}).get("per_turn", 0.0)
            print(
                f"[TURBULENCE] session_id={session_id!r} events={_turb_raw} "
                f"per_turn={_turb_per:.3f} "
                f"(asr_rejects={int(sess.get('unmatched_responses',0))+int(sess.get('soft_unmatched_responses',0))} "
                f"stability={metrics['stability']['label']!r})",
                flush=True,
            )

            saved = False
            if mode == "challenge":
                record = {
                    "session_id": session_id,
                    "mode":       mode,
                    "timestamp":  datetime.datetime.utcnow().isoformat() + "Z",
                    "session":    sess,
                    "metrics":    metrics,
                }
                try:
                    _append_progress_history(record)
                    saved = True
                    print(f"[ui_server] /api/end_session: saved to {_PROGRESS_HISTORY_PATH}", flush=True)
                except Exception as exc:
                    print(f"[ui_server] /api/end_session: failed to save progress history: {exc}", flush=True)

            # ── Session Intelligence capture (Phase 0 Slice 1, flag-gated) ──────
            # Runs AFTER the existing progress save so a capture failure can never
            # affect progress persistence.  Wrapped in try/except; any error is
            # logged and silently discarded — it must not alter the response.
            if _si_is_enabled and _si_is_enabled() and _si_build_record and _si_save_record:
                try:
                    _si_transcript = sess.get("transcript")
                    _si_event_log  = sess.get("event_log")
                    _si_record = _si_build_record(
                        sess,
                        metrics,
                        progress_snapshot,
                        transcript=_si_transcript,
                        event_log=_si_event_log,
                    )
                    _si_ok = _si_save_record(learner_id, session_id, _si_record)
                    print(
                        f"[session_intelligence] capture {'saved' if _si_ok else 'skipped/failed'}"
                        f" for {learner_id!r}/{session_id!r}",
                        flush=True,
                    )
                except Exception as _si_exc:
                    print(f"[session_intelligence] capture error (non-fatal): {_si_exc}", flush=True)

            result = {
                "ok":                True,
                "session_id":        session_id,
                "mode":              mode,
                "saved":             saved,
                "metrics":           metrics,
                "progress_snapshot": progress_snapshot,
                "progress_saved":    True,
                "session_interpretation": {
                    "flow":     progress_snapshot.get("flow_display_label"),
                    "recovery": progress_snapshot.get("recovery_display_label"),
                    "support":  progress_snapshot.get("support_display_label"),
                },
            }
            data = json.dumps(result, ensure_ascii=False).encode("utf-8")
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
    port = int(os.environ.get("PORT", 8765))
    _kill_stale_server_processes(port)
    print(f"[ui_server] Listening on http://0.0.0.0:{port}", flush=True)
    ThreadedHTTPServer(("", port), Handler).serve_forever()
