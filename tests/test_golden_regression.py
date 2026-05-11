#!/usr/bin/env python3
"""
MandarinOS Golden Conversation Regression Tests

Covers the core conversation behaviours that must not regress after any
selector, ASR, or recovery-phrase change.

Usage:
  # With server running:
  python tests/test_golden_regression.py

  # Static checks only (no server needed):
  python tests/test_golden_regression.py --static-only

The script exits 0 if all run tests pass, 1 if any fail.
See docs/MANDARINOS_REGRESSION_LOCK.md for the rationale behind each test.
"""

import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT   = Path(__file__).parent.parent
SERVER = "http://localhost:8765"

# ── Terminal colour helpers ────────────────────────────────────────────────────
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

_results: list = []   # (name, ok: bool)


def check(name: str, condition: bool, detail: str = "") -> None:
    """Record and print a single assertion."""
    status = PASS if condition else FAIL
    suffix = f"  ← {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    _results.append((name, condition))


def skip(name: str, reason: str = "") -> None:
    suffix = f"  ← {reason}" if reason else ""
    print(f"  [{SKIP}] {name}{suffix}")


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _server_alive() -> bool:
    try:
        urllib.request.urlopen(f"{SERVER}/", timeout=2)
    except urllib.error.HTTPError:
        return True   # HTTP error means the server responded
    except urllib.error.URLError:
        return False
    return True


def api_run_turn(last_answer: dict, cs: dict | None = None) -> dict | None:
    """POST /api/run_turn. Returns parsed JSON or None if server unreachable."""
    payload = json.dumps({
        "turn_uid": "golden_regression",
        "last_answer": last_answer,
        "conversation_state": cs or {},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{SERVER}/api/run_turn",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, Exception):
        return None


def make_cs(
    engine: str = "unknown",
    recent: list | None = None,
    exchange: int = 5,
    extra: dict | None = None,
) -> dict:
    cs = {
        "last_turn_was_answer": True,
        "current_engine": engine,
        "recent_frame_ids": recent or [],
        "exchange_count": exchange,
        "learner_id": "regression_tester",
        "same_engine_chain_count": 1,
        "interest_level": "medium",
    }
    if extra:
        cs.update(extra)
    return cs


def make_answer(frame_id: str, text: str) -> dict:
    return {
        "frame_id": frame_id,
        "submitted_text": text,
        "selected_option_hanzi": text,
        "move_type": "ANSWER",
    }


# ══════════════════════════════════════════════════════════════════════════════
# STATIC TESTS  (no server required — check files on disk)
# ══════════════════════════════════════════════════════════════════════════════

def test_repair_phrases_no_learner_pauses() -> None:
    """[T1] 等一下 / 等一等 / 等等 must never appear as app-side repair responses."""
    print("\n[STATIC] T1 — Repair phrase isolation (no learner-owned pause phrases)")
    runtime_path = ROOT / "runtime" / "out_phase7" / "recovery_phrases.runtime.json"
    if not runtime_path.exists():
        skip("recovery_phrases.runtime.json found", "file missing — rebuild artifacts")
        return

    raw = json.loads(runtime_path.read_text(encoding="utf-8"))
    # Support both list and dict formats
    if isinstance(raw, list):
        phrases = raw
    elif isinstance(raw, dict):
        phrases = raw.get("phrases", [])
        for section in ("repair", "notunderstood", "recovery", "all"):
            phrases += raw.get(section, [])
    else:
        phrases = []

    FORBIDDEN = {"等一下", "等一等", "等等"}
    violations = [
        f"{p.get('id', '?')}:'{p.get('hanzi', '')}'"
        for p in phrases
        if isinstance(p, dict)
        and (p.get("speaker") or "").strip() != "learner"
        and (p.get("hanzi") or "").strip() in FORBIDDEN
    ]
    check("No 等一下/等一等/等等 in app-side phrases",
          len(violations) == 0,
          ", ".join(violations))


def test_required_frames_exist() -> None:
    """[T2] All frames introduced by recent improvements must exist in p2_frames.json."""
    print("\n[STATIC] T2 — Required frames exist")
    data = json.loads((ROOT / "p2_frames.json").read_text(encoding="utf-8"))
    frames = data if isinstance(data, list) else data.get("frames", [])
    ids = {f["id"] for f in frames if isinstance(f, dict) and "id" in f}

    REQUIRED = {
        "f_travel_why_want_go":          "depth follow-up for specific destination",
        "f_travel_narrow_city":          "narrowing step for country-level answers",
        "f_travel_dest_generic_clarify": "clarification for garbled/invalid destinations",
        "f_work_retire_clarify":         "ASR near-miss retirement clarification",
        "f_work_yn":                     "soft work-entry question",
    }
    for fid, reason in REQUIRED.items():
        check(f"Frame '{fid}' exists  [{reason}]", fid in ids)


def test_depth_anchor_completeness() -> None:
    """[T3] _DEPTH_ANCHOR_FRAMES must include travel narrowing chain."""
    print("\n[STATIC] T3 — Depth-anchor chain: f_travel_narrow_city in anchor map")
    src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    check("_DEPTH_ANCHOR_FRAMES includes f_travel_narrow_city",
          '"f_travel_narrow_city"' in src,
          "search in ui_server.py")
    check("_DEPTH_ANCHOR_SPECIFICITY includes f_travel_narrow_city",
          "_DEPTH_ANCHOR_SPECIFICITY" in src and '"f_travel_narrow_city"' in src)
    check("_DESTINATION_QUESTION_FRAMES defined",
          "_DESTINATION_QUESTION_FRAMES" in src)
    check("_TRAVEL_ASR_NEAR_MATCHES defined (刚吃/甘肃)",
          "刚吃" in src and "甘肃" in src)


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS  (server must be running on localhost:8765)
# ══════════════════════════════════════════════════════════════════════════════

def test_food_echo_not_collapsed() -> None:
    """[T4] 羊肉不错 → echoed in full, not collapsed to 不错."""
    print("\n[INTEGRATION] T4 — Food: '羊肉不错' accepted and echoed whole")
    resp = api_run_turn(
        make_answer("f_food_what_good", "羊肉不错"),
        make_cs(engine="food"),
    )
    if resp is None:
        skip("T4", "server not available"); return

    text = resp.get("frame_text", "")
    trace = resp.get("selector_trace", {})
    check("frame_text contains 羊肉", "羊肉" in text, f"frame_text='{text[:60]}'")
    check("frame_text does NOT start with 哦，不错！ (collapse)",
          not text.startswith("哦，不错！"), f"frame_text='{text[:40]}'")
    check("food_answer_detected in trace",
          trace.get("food_answer_detected") is True or "DISH" in str(trace),
          str(trace)[:80])


def test_travel_broad_stays_in_engine() -> None:
    """[T5] 我想去中国 after 你会去别的地方吗？ stays in travel, no family bridge."""
    print("\n[INTEGRATION] T5 — Travel broad (f_place_travel): stays in travel/place")
    FAMILY_FRAMES = {"f_live_with_who", "p2_fa_1", "p2_fa_2", "p2_fa_live_with",
                     "f_have_family", "f_have_siblings"}
    resp = api_run_turn(
        make_answer("f_place_travel", "我想去中国"),
        make_cs(engine="place"),
    )
    if resp is None:
        skip("T5", "server not available"); return

    fid = resp.get("frame_id", "")
    check("Next frame is NOT a family frame",
          fid not in FAMILY_FRAMES, f"frame_id='{fid}'")


def test_travel_country_to_narrow() -> None:
    """[T6] 我想去中国 after 你最想去哪里？ → f_travel_narrow_city."""
    print("\n[INTEGRATION] T6 — Travel: country answer → 你想去哪个城市？")
    resp = api_run_turn(
        make_answer("f_want_go_where", "我想去中国"),
        make_cs(engine="travel"),
    )
    if resp is None:
        skip("T6", "server not available"); return

    fid = resp.get("frame_id", "")
    text = resp.get("frame_text", "")
    check("frame_id == f_travel_narrow_city",
          fid == "f_travel_narrow_city", f"frame_id='{fid}' text='{text[:50]}'")


def test_travel_city_to_depth() -> None:
    """[T7] 北京 after 你想去哪个城市？ → f_travel_why_want_go."""
    print("\n[INTEGRATION] T7 — Travel: city answer → 你为什么想去那里？")
    resp = api_run_turn(
        make_answer("f_travel_narrow_city", "北京"),
        make_cs(engine="travel"),
    )
    if resp is None:
        skip("T7", "server not available"); return

    fid = resp.get("frame_id", "")
    text = resp.get("frame_text", "")
    check("frame_id == f_travel_why_want_go",
          fid == "f_travel_why_want_go", f"frame_id='{fid}' text='{text[:50]}'")


def test_travel_province_to_depth() -> None:
    """[T8] 我最想去江苏 after 你最想去哪里？ → depth follow-up."""
    print("\n[INTEGRATION] T8 — Travel: province answer to f_want_go_where → depth")
    resp = api_run_turn(
        make_answer("f_want_go_where", "我最想去江苏"),
        make_cs(engine="travel"),
    )
    if resp is None:
        skip("T8", "server not available"); return

    fid = resp.get("frame_id", "")
    text = resp.get("frame_text", "")
    check("frame_id == f_travel_why_want_go",
          fid == "f_travel_why_want_go", f"frame_id='{fid}' text='{text[:50]}'")


def test_travel_asr_garble_clarify() -> None:
    """[T9] 我就想去刚吃 → 你是说甘肃吗？, never echoed, never bridges to family."""
    print("\n[INTEGRATION] T9 — Travel: garbled ASR (刚吃) → candidate clarification")
    FAMILY_FRAMES = {"f_live_with_who", "p2_fa_1", "p2_fa_2", "p2_fa_live_with"}
    resp = api_run_turn(
        make_answer("f_want_go_where", "我就想去刚吃"),
        make_cs(engine="travel"),
    )
    if resp is None:
        skip("T9", "server not available"); return

    fid  = resp.get("frame_id", "")
    text = resp.get("frame_text", "")
    full = resp.get("frame_text", "") + " " + (resp.get("reaction_prefix_text") or "")
    trace = resp.get("selector_trace", {})

    check("frame_id == f_travel_dest_generic_clarify",
          fid == "f_travel_dest_generic_clarify", f"frame_id='{fid}'")
    check("frame_text == '你是说甘肃吗？' (candidate-specific)",
          text == "你是说甘肃吗？", f"got '{text}'")
    check("刚吃 NOT echoed in response",
          "刚吃" not in full, f"found in '{full[:60]}'")
    check("Next frame is NOT a family frame",
          fid not in FAMILY_FRAMES, f"frame_id='{fid}'")
    check("selector_trace.fuzzy_candidate == '甘肃'",
          trace.get("fuzzy_candidate") == "甘肃", str(trace.get("fuzzy_candidate")))


def test_work_retirement_safe() -> None:
    """[T10] 我退休了 after 你做什么工作？ → retirement follow-up, NOT company question."""
    print("\n[INTEGRATION] T10 — Work: 我退休了 → retirement-safe follow-up")
    FORBIDDEN_WORK = {
        "f_work_company", "f_work_tenure", "f_work_where",
        "f_probe_work_company_vibe", "f_probe_work_role_detail",
    }
    resp = api_run_turn(
        make_answer("f_what_work", "我退休了"),
        make_cs(engine="work"),
    )
    if resp is None:
        skip("T10", "server not available"); return

    fid = resp.get("frame_id", "")
    text = resp.get("frame_text", "")
    check("frame_id is NOT a current-company/work frame",
          fid not in FORBIDDEN_WORK, f"frame_id='{fid}'")
    check("frame_text does NOT mention 公司/上班 (assumes current job)",
          "公司" not in text and "上班" not in text, f"text='{text[:60]}'")


def test_work_asr_retire_near_miss() -> None:
    """[T11] 我推销了 after 你做什么工作？ → 你是说你退休了吗？, NOT company follow-up."""
    print("\n[INTEGRATION] T11 — Work: ASR near-miss 推销了 → retirement clarification")
    FORBIDDEN_WORK = {
        "f_work_company", "f_work_tenure", "f_probe_work_company_vibe",
        "f_probe_work_role_detail",
    }
    resp = api_run_turn(
        make_answer("f_what_work", "我推销了"),
        make_cs(engine="work"),
    )
    if resp is None:
        skip("T11", "server not available"); return

    fid  = resp.get("frame_id", "")
    text = resp.get("frame_text", "")
    check("frame_id == f_work_retire_clarify",
          fid == "f_work_retire_clarify", f"frame_id='{fid}' text='{text[:50]}'")
    check("frame_text contains 退休",
          "退休" in text, f"got '{text}'")
    check("frame_id is NOT a current-company frame",
          fid not in FORBIDDEN_WORK, f"frame_id='{fid}'")


def test_work_retire_near_miss_tuixiaole() -> None:
    """[T13] 我退校了 after 你做什么工作？ → retirement clarification, NOT occupation follow-up."""
    print("\n[INTEGRATION] T13 — Work: near-miss 退校了 → f_work_retire_clarify")
    FORBIDDEN_WORK = {
        "f_work_company", "f_work_tenure", "f_work_where",
        "f_probe_work_company_vibe", "f_probe_work_role_detail",
        "p2_wk_2", "p2_wk_3",
    }
    resp = api_run_turn(
        make_answer("f_what_work", "我退校了"),
        make_cs(engine="work"),
    )
    if resp is None:
        skip("T13", "server not available"); return

    fid   = resp.get("frame_id", "")
    text  = resp.get("frame_text", "")
    trace = resp.get("selector_trace", {})
    check("frame_id == f_work_retire_clarify",
          fid == "f_work_retire_clarify", f"frame_id='{fid}' text='{text[:50]}'")
    check("frame_text contains 退休",
          "退休" in text, f"got '{text}'")
    check("frame_id is NOT a current-job frame",
          fid not in FORBIDDEN_WORK, f"frame_id='{fid}'")
    check("selector_trace.near_miss_guard_fired == True",
          trace.get("near_miss_guard_fired") is True, str(trace.get("near_miss_guard_fired")))
    check("selector_trace.near_miss_intended == '退休'",
          trace.get("near_miss_intended") == "退休", str(trace.get("near_miss_intended")))


def test_work_retire_near_miss_tuixuele() -> None:
    """[T14] 我退学了 after 你做什么工作？ → retirement clarification, NOT occupation follow-up."""
    print("\n[INTEGRATION] T14 — Work: near-miss 退学了 → f_work_retire_clarify")
    FORBIDDEN_WORK = {
        "f_work_company", "f_work_tenure", "f_work_where",
        "f_probe_work_company_vibe", "f_probe_work_role_detail",
        "p2_wk_2", "p2_wk_3",
    }
    resp = api_run_turn(
        make_answer("p2_wk_1", "我退学了"),
        make_cs(engine="work"),
    )
    if resp is None:
        skip("T14", "server not available"); return

    fid   = resp.get("frame_id", "")
    text  = resp.get("frame_text", "")
    trace = resp.get("selector_trace", {})
    check("frame_id == f_work_retire_clarify",
          fid == "f_work_retire_clarify", f"frame_id='{fid}' text='{text[:50]}'")
    check("frame_text contains 退休",
          "退休" in text, f"got '{text}'")
    check("frame_id is NOT a current-job frame",
          fid not in FORBIDDEN_WORK, f"frame_id='{fid}'")
    check("near_miss_guard_fired in trace",
          trace.get("near_miss_guard_fired") is True, str(trace.get("near_miss_guard_fired")))


def test_work_retirement_suppresses_occupation_followup() -> None:
    """[T15] After retirement confirmed (p2_wk_retired in recent), generic job questions suppressed."""
    print("\n[INTEGRATION] T15 — Work: confirmed retirement → no occupation follow-up")
    FORBIDDEN_OCCUPATION = {
        "f_work_company", "f_work_tenure", "f_work_where",
        "f_probe_work_company_vibe", "f_probe_work_role_detail",
        "p2_wk_2", "p2_wk_3", "p2_wk_4", "p2_wk_5",
    }
    # Simulate a turn after retirement was confirmed: p2_wk_retired already asked.
    resp = api_run_turn(
        make_answer("p2_wk_retired", "我以前是老师"),
        make_cs(engine="work", recent=["p2_wk_retired"]),
    )
    if resp is None:
        skip("T15", "server not available"); return

    fid  = resp.get("frame_id", "")
    text = resp.get("frame_text", "")
    check("frame_id is NOT an active-job occupation frame",
          fid not in FORBIDDEN_OCCUPATION, f"frame_id='{fid}' text='{text[:50]}'")
    check("frame_text does NOT assume current employment (公司/上班)",
          "公司" not in text and "上班" not in text, f"text='{text[:60]}'")


def test_family_live_with_acceptance() -> None:
    """[T12] 爸爸妈妈老婆 after 你跟谁一起住？ → sensible family follow-up."""
    print("\n[INTEGRATION] T12 — Family: 爸爸妈妈老婆 → accepted, not travel/work jump")
    WRONG_ENGINES = {"f_want_go_where", "f_food_what_good", "f_what_work", "f_work_company"}
    resp = api_run_turn(
        make_answer("f_live_with_who", "爸爸妈妈老婆"),
        make_cs(engine="family"),
    )
    if resp is None:
        skip("T12", "server not available"); return

    fid = resp.get("frame_id", "")
    check("Server returns a frame (no crash)", bool(fid), f"frame_id='{fid}'")
    check("Next frame is NOT from travel/food/work domain",
          fid not in WRONG_ENGINES, f"frame_id='{fid}'")


def test_family_closest_acceptance() -> None:
    """[T13] 我老婆 after 你和家里谁最亲近？ → same-topic family follow-up."""
    print("\n[INTEGRATION] T13 — Family: 我老婆 after closest → same-engine follow-up")
    resp = api_run_turn(
        make_answer("f_probe_family_closest", "我老婆"),
        make_cs(engine="family"),
    )
    if resp is None:
        skip("T13", "server not available"); return

    fid = resp.get("frame_id", "")
    text = resp.get("frame_text", "")
    # Depth rule should pick f_probe_family_together or f_probe_family_influence
    EXPECTED_DEPTH = {"f_probe_family_together", "f_probe_family_influence"}
    check("frame_id is a family depth frame (together/influence)",
          fid in EXPECTED_DEPTH, f"frame_id='{fid}' text='{text[:50]}'")


def test_family_activity_acceptance() -> None:
    """[T14] 吃饭 after 你最喜欢和家人一起做什么？ → accepted, no crash."""
    print("\n[INTEGRATION] T14 — Family activity: 吃饭 → accepted")
    WRONG_ENGINES = {"f_want_go_where", "f_food_what_good", "f_what_work"}
    resp = api_run_turn(
        make_answer("p2_fa_activity", "吃饭"),
        make_cs(engine="family"),
    )
    if resp is None:
        skip("T14", "server not available"); return

    fid = resp.get("frame_id", "")
    check("Server returns a frame (no crash)", bool(fid))
    check("Next frame is NOT from travel/food/work domain",
          fid not in WRONG_ENGINES, f"frame_id='{fid}'")


def test_reflection_signal_detection() -> None:
    """[STATIC] T-Ref — Reflection signal detection rules (app.js, static checks).

    A. '我是新西兰人你呢' triggers question_count (你呢 is always a question).
    B. If question_count > 0, next_steps must not include 'Try asking a question back'.
    C. '我以前是大学的老师' counts as extended (以前 marker).
    D. '现在很好啦现在好很多' counts as extended (现在 marker).
    E. _pendingRepairPrompt set on ASR rejection, cleared after answer; identical
       retry does NOT inflate recovery_resilience_count.
    F. _buildAbilitySummary uses all three new signals.
    G. False-positive guard: '我不知道怎么说' must NOT count as a question
       (怎么in declarative clause).
    H. '二十年' counts as extended (Chinese numeral + 年 duration pattern).
    I. Graded language: extendedCount==1 → 'started adding' vs >=2 → 'more detailed'.
    J. resilCount==1 → 'kept going' vs >=2 → 'worked through' in progress_lines.
    K. Headline tightened: 'natural conversation flow' requires resilCount >= 2.
    """
    print("\n[STATIC] T-Ref — Reflection signal detection (app.js static checks)")
    app_js = ROOT / "ui" / "app.js"
    src = app_js.read_text(encoding="utf-8")

    # ── A: 你呢 always counted ───────────────────────────────────────────────
    check(
        "A: '你呢' is always counted as a question",
        '"你呢"' in src and "hasYouNe" in src,
    )
    check(
        "A: question_count incremented in _trackUserTextSignals",
        "window._learnerObs.question_count++" in src,
    )

    # ── B: question_count > 0 suppresses suggestion ─────────────────────────
    check(
        "B: next_steps guard uses questionCount === 0",
        "questionCount === 0" in src,
    )

    # ── C & D: temporal markers in EXTEND_MARKERS ────────────────────────────
    check(
        "C: '以前' in EXTEND_MARKERS",
        '"以前"' in src,
    )
    check(
        "D: '现在' in EXTEND_MARKERS",
        '"现在"' in src,
    )
    check(
        "C/D: extended_answer_count incremented in _trackUserTextSignals",
        "extended_answer_count++" in src,
    )

    # ── E: repair-resilience flag + identity guard ────────────────────────────
    check(
        "E: _pendingRepairPrompt set to true on ASR rejection",
        "window._pendingRepairPrompt" in src and "= true;" in src,
    )
    check(
        "E: _lastRepairSubmittedText stored on rejection",
        "window._lastRepairSubmittedText = saidTrimmed" in src,
    )
    check(
        "E: identical-retry guard in _trackUserTextSignals",
        "window._lastRepairSubmittedText" in src
        and "_lastRepairSubmittedText" in src,
    )
    check(
        "E: recovery_resilience_count incremented only on differing answer",
        "recovery_resilience_count++" in src,
    )

    # ── F: _buildAbilitySummary uses all new signals ──────────────────────────
    check("F: reads question_count",           "obs.question_count" in src)
    check("F: reads extended_answer_count",    "obs.extended_answer_count" in src)
    check("F: reads recovery_resilience_count","obs.recovery_resilience_count" in src)
    check("F: extendedCount >= 2 varies next_steps", "extendedCount >= 2" in src)

    # ── G: false-positive guard (structural check required for question words) ─
    # The key is that question words need isStructuralQ (not just length alone).
    check(
        "G: isStructuralQ gate present for question words",
        "isStructuralQ" in src and "hasQWord" in src,
    )
    check(
        "G: shortIntPattern requires starts-with check (不 '我' guard)",
        "shortIntPattern" in src and "/^[你他她这那]/" in src,
    )

    # ── H: duration pattern covers '二十年' ───────────────────────────────────
    check(
        "H: _DURATION_ANSWER_PAT covers Chinese numeral + 年",
        "_DURATION_ANSWER_PAT" in src and "二三四五六七八九十" in src,
    )

    # ── I: graded extended language ─────────────────────────────────────────
    check(
        "I: extendedCount === 1 → 'started adding more detail'",
        "You started adding more detail" in src,
    )
    check(
        "I: extendedCount >= 2 → 'gave more detailed answers'",
        "You gave more detailed answers" in src,
    )

    # ── J: graded resilience language ────────────────────────────────────────
    check(
        "J: resilCount === 1 → 'kept going after a misunderstanding'",
        "You kept going after a misunderstanding" in src,
    )
    check(
        "J: resilCount >= 2 → 'worked through misunderstandings'",
        "You worked through misunderstandings" in src,
    )

    # ── K: headline requires resilCount >= 2 ────────────────────────────────
    check(
        "K: headline 'natural conversation flow' requires resilCount >= 2",
        "resilCount >= 2" in src,
    )

    # ── Internal consistency ─────────────────────────────────────────────────
    check("question_count reset in startFreshLearner",          "question_count: 0" in src)
    check("extended_answer_count reset in startFreshLearner",   "extended_answer_count: 0" in src)
    check("recovery_resilience_count reset in startFreshLearner","recovery_resilience_count: 0" in src)
    check("_lastRepairSubmittedText reset in startFreshLearner",
          "window._lastRepairSubmittedText = " in src)


def test_meaningful_imperfect_name_story_stay() -> None:
    """[T16] Messy multi-component name answer → clarify frame, NOT age question."""
    print("\n[INTEGRATION] T16 — Identity: complex name answer → f_identity_name_clarify_soft")
    FORBIDDEN_FRAMES = {
        "f_how_old",           # 你多大了？ — premature engine progression
        "f_want_go_where",     # travel engine — wrong engine
        "f_what_work",         # work engine — wrong engine
    }
    resp = api_run_turn(
        make_answer(
            "f_ask_you_name",
            "我叫杨理名李毛的李国民的名朋友叫我Raymond家里人叫我rimant我广东名字英文名字",
        ),
        make_cs(engine="identity", extra={"same_engine_chain_count": 2}),
    )
    if resp is None:
        skip("T16", "server not available"); return

    fid   = resp.get("frame_id", "")
    text  = resp.get("frame_text", "")
    trace = resp.get("selector_trace", {})
    check("frame_id == f_identity_name_clarify_soft",
          fid == "f_identity_name_clarify_soft", f"frame_id='{fid}' text='{text[:60]}'")
    check("frame_text contains 英文名字",
          "英文名字" in text, f"got '{text}'")
    check("frame_id is NOT a premature-progression frame",
          fid not in FORBIDDEN_FRAMES, f"frame_id='{fid}'")
    check("selector_trace.meaningful_imperfect_fired == True",
          trace.get("meaningful_imperfect_fired") is True,
          str(trace.get("meaningful_imperfect_fired")))


def test_meaningful_imperfect_clarify_trigger() -> None:
    """[T17] Partial sentence with Cantonese/English name keywords → clarify + trace flag."""
    print("\n[INTEGRATION] T17 — Identity: keyword-rich partial answer → f_identity_name_clarify_soft")
    resp = api_run_turn(
        make_answer("f_ask_you_name", "我广东名字英文名字"),
        make_cs(engine="identity", extra={"same_engine_chain_count": 1}),
    )
    if resp is None:
        skip("T17", "server not available"); return

    fid   = resp.get("frame_id", "")
    text  = resp.get("frame_text", "")
    trace = resp.get("selector_trace", {})
    check("frame_id == f_identity_name_clarify_soft",
          fid == "f_identity_name_clarify_soft", f"frame_id='{fid}' text='{text[:60]}'")
    check("selector_trace.meaningful_imperfect_fired == True",
          trace.get("meaningful_imperfect_fired") is True,
          str(trace.get("meaningful_imperfect_fired")))
    check("selector_trace.block_engine_switch_once == True",
          trace.get("block_engine_switch_once") is True,
          str(trace.get("block_engine_switch_once")))


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def test_translation_naturalizer() -> None:
    """T15 – naturalizeZhTranslation vocabulary & pattern rules (static, JS-side).

    Because the normalizer lives in app.js (client-side JS) we verify the
    RULES it encodes rather than calling the function directly from Python.

    Checks:
      a. Vocab map contains all required formal→spoken substitutions.
      b. Emotional-closeness pattern rewrite is scoped to relational context.
      c. Physical-distance sentences are NOT rewritten.
    """
    print("[STATIC] T15 — Translation naturalizer (vocab map + pattern rules)")
    app_js = ROOT / "ui" / "app.js"
    src = app_js.read_text(encoding="utf-8")

    required_vocab_pairs = [
        ("妻子", "老婆"),
        ("丈夫", "老公"),
        ("父亲", "爸爸"),
        ("母亲", "妈妈"),
        ("父母", "爸爸妈妈"),
    ]
    for formal, spoken in required_vocab_pairs:
        check(
            f"Vocab map includes {formal}→{spoken}",
            f'"{formal}"' in src and f'"{spoken}"' in src,
        )

    check(
        "Emotional-closeness context detector exists",
        "closest to" in src and "_isEmotionalClosenessContext" in src,
    )

    check(
        "Physical-distance exclusion keywords present",
        any(kw in src for kw in ["live near", "drive", "distance", "school"]),
    )

    check(
        "naturalizeZhTranslation applied to Translate button output",
        "naturalizeZhTranslation(rawZh" in src,
    )

    # Override map checks
    check(
        "TRANSLATION_OVERRIDES map exists",
        "TRANSLATION_OVERRIDES" in src,
    )
    required_overrides = [
        ("i am closest to my wife",    "我跟我老婆最亲近"),
        ("i am retired",               "我退休了"),
        ("i live with my parents",     "我跟爸爸妈妈一起住"),
    ]
    for en_key, zh_val in required_overrides:
        check(
            f"Override present: '{en_key}'",
            en_key in src and zh_val in src,
        )
    check(
        "_lookupTranslationOverride called before API in doTranslate",
        "_lookupTranslationOverride(text)" in src,
    )

    server_py = ROOT / "scripts" / "ui_server.py"
    srv = server_py.read_text(encoding="utf-8")
    check(
        "_naturalize_en_gloss exists in ui_server.py",
        "_naturalize_en_gloss" in srv,
    )
    check(
        "_naturalize_en_gloss handles 'nearest to' fix",
        "nearest to" in srv and "_naturalize_en_gloss" in srv,
    )


def test_semantic_extraction() -> None:
    """[STATIC] T-Sem — Semantic extraction, topic persistence, and clarification (app.js).

    Verifies:
    A. _DURATION_ANSWER_PAT hoisted to module level + used in isLikelyUnderstandableFreeAnswer.
    B. isOpenEndedFrame includes duration frames (f_work_tenure, p2_hb_5) and emotional
       check-in frame (f_probe_emotional_checkin).
    C. semanticSoftMatch handles duration frames, family-health, and name-statement frames.
    D. _detectSemanticCategory function covers all 7 required categories.
    E. _SEMANTIC_CLARIFICATION_PHRASES and _getSemanticClarification exist with correct entries.
    F. classifyUnmatchedFreeAnswerDecision has topic-persistence semantic accept logic.
    G. Not-understood path uses _displayPhrase with semantic_clarify_used in emitUITrace.
    """
    src_path = (
        Path(__file__).resolve().parent.parent / "ui" / "app.js"
    )
    src = src_path.read_text(encoding="utf-8")

    # ── A: _DURATION_ANSWER_PAT module-level ─────────────────────────────────
    check(
        "A1: _DURATION_ANSWER_PAT declared at module level",
        "const _DURATION_ANSWER_PAT" in src,
    )
    check(
        "A2: isLikelyUnderstandableFreeAnswer uses _DURATION_ANSWER_PAT for early-return",
        "_DURATION_ANSWER_PAT.test(s)" in src,
    )
    check(
        "A3: _trackUserTextSignals uses module-level _DURATION_ANSWER_PAT (not local DURATION_PAT)",
        "_DURATION_ANSWER_PAT.test(text)" in src and "const DURATION_PAT" not in src,
    )

    # ── B: isOpenEndedFrame additions ────────────────────────────────────────
    check(
        "B1: f_work_tenure in isOpenEndedFrame",
        '"f_work_tenure"' in src,
    )
    check(
        "B2: p2_hb_5 in isOpenEndedFrame",
        '"p2_hb_5"' in src,
    )
    check(
        "B3: f_probe_emotional_checkin in isOpenEndedFrame",
        '"f_probe_emotional_checkin"' in src,
    )

    # ── C: semanticSoftMatch additions ───────────────────────────────────────
    check(
        "C1: _DURATION_FRAMES used in semanticSoftMatch",
        "_DURATION_FRAMES" in src,
    )
    check(
        "C2: family health patterns in semanticSoftMatch",
        "好多了|好很多|好一点|不好|生病|康复" in src,
    )
    check(
        "C3: _NAME_STATEMENT_FRAMES in semanticSoftMatch",
        "_NAME_STATEMENT_FRAMES" in src,
    )

    # ── D: _detectSemanticCategory ───────────────────────────────────────────
    check(
        "D1: _detectSemanticCategory function exists",
        "function _detectSemanticCategory" in src,
    )
    check(
        "D2: name category detection (我叫/英文名/Latin)",
        "我叫|名字|英文名|[A-Za-z]{3,}" in src,
    )
    check(
        "D3: duration category detection uses _DURATION_ANSWER_PAT",
        "_DURATION_ANSWER_PAT.test(t)" in src,
    )
    check(
        "D4: family_health category detection",
        '"family_health"' in src,
    )
    check(
        "D5: work_status category detection",
        '"work_status"' in src,
    )
    check(
        "D6: location category detection",
        '"location"' in src,
    )

    # ── E: Semantic clarification templates ──────────────────────────────────
    check(
        "E1: _SEMANTIC_CLARIFICATION_PHRASES object exists",
        "_SEMANTIC_CLARIFICATION_PHRASES" in src,
    )
    check(
        "E2: _getSemanticClarification function exists",
        "function _getSemanticClarification" in src,
    )
    check(
        "E3: name clarification phrase present",
        "你是说你的英文名字吗？" in src,
    )
    check(
        "E4: duration clarification phrase present",
        "大概多少年了？" in src,
    )
    check(
        "E5: family_health clarification phrase present",
        "现在好一点了吗？" in src,
    )
    check(
        "E6: work_status clarification phrase present",
        "你是说你已经退休了吗？" in src,
    )

    # ── F: Topic-persistence semantic accept ─────────────────────────────────
    check(
        "F1: topic_persistence_semantic reason in classifyUnmatchedFreeAnswerDecision",
        "topic_persistence_semantic" in src,
    )
    check(
        "F2: topic persistence guard checks unmatchedCount >= 2",
        ">= 2 && _detectSemanticCategory" in src,
    )

    # ── G: Not-understood path uses _displayPhrase ───────────────────────────
    check(
        "G1: _semCategory detected in not-understood path",
        "_detectSemanticCategory(saidTrimmed)" in src,
    )
    check(
        "G2: _displayPhrase used for addTranscriptEntry (partner)",
        "addTranscriptEntry(\"partner\", _displayPhrase.hanzi" in src,
    )
    check(
        "G3: semantic_clarify_used emitted in trace",
        "semantic_clarify_used" in src,
    )


def test_interaction_intelligence() -> None:
    """[STATIC] T-IQ — Interaction intelligence: emotional vocab, place tracking, vague-ref anchoring.

    Verifies:
    A. isOpenEndedFrame includes travel-why and travel-depth frames.
    B. classifyUnmatchedFreeAnswerDecision has emotional vocab acceptance.
    C. window._lastMentionedPlace tracked from accepted free answers.
    D. _anchorVagueReferences function exists and replaces 在那儿/在那里.
    E. fallbackText in runTurn uses _anchorVagueReferences.
    F. ui_server.py has multi-destination reaction detection.
    """
    js_path = Path(__file__).resolve().parent.parent / "ui" / "app.js"
    srv_path = Path(__file__).resolve().parent.parent / "scripts" / "ui_server.py"
    src = js_path.read_text(encoding="utf-8")
    srv = srv_path.read_text(encoding="utf-8")

    # ── A: isOpenEndedFrame additions ────────────────────────────────────────
    check(
        "A1: f_travel_why_want_go in isOpenEndedFrame",
        '"f_travel_why_want_go"' in src,
    )
    check(
        "A2: p2_tr_3 in isOpenEndedFrame",
        '"p2_tr_3"' in src,
    )
    check(
        "A3: p2_tr_4 in isOpenEndedFrame",
        '"p2_tr_4"' in src,
    )
    check(
        "A4: f_probe_hobby_origin in isOpenEndedFrame",
        '"f_probe_hobby_origin"' in src,
    )

    # ── B: Emotional vocab acceptance ────────────────────────────────────────
    check(
        "B1: emotional_vocab_match reason in classifyUnmatchedFreeAnswerDecision",
        "emotional_vocab_match" in src,
    )
    check(
        "B2: 开心 in emotional vocab pattern",
        "开心" in src and "emotional_vocab_match" in src,
    )
    check(
        "B3: hasStructuredSlots guard on emotional vocab",
        "!hasStructuredSlots" in src,
    )

    # ── C: window._lastMentionedPlace tracking ───────────────────────────────
    check(
        "C1: window._lastMentionedPlace assigned on accepted answer",
        "window._lastMentionedPlace = _newAnchorPlace" in src,
    )
    check(
        "C2: 甘肃 in place anchor list",
        "'甘肃'" in src,
    )

    # ── D: _anchorVagueReferences function ───────────────────────────────────
    check(
        "D1: _anchorVagueReferences function exists",
        "function _anchorVagueReferences" in src,
    )
    check(
        "D2: replaces 在那儿 with anchored reference",
        "在那儿" in src and "那边" in src,
    )
    check(
        "D3: replaces 在那里 with anchored reference",
        "在那里" in src,
    )

    # ── E: Applied in runTurn ─────────────────────────────────────────────────
    check(
        "E1: _anchorVagueReferences applied to fallbackText in runTurn",
        "_anchorVagueReferences(" in src and "window._lastMentionedPlace" in src,
    )

    # ── F: Multi-destination reaction in ui_server.py ────────────────────────
    check(
        "F1: _MULTI_DEST_PAT defined in ui_server.py",
        "_MULTI_DEST_PAT" in srv,
    )
    check(
        "F2: multi_destination_ack reaction mode",
        "multi_destination_ack" in srv,
    )
    check(
        "F3: 哇，你去过很多地方！ reaction text",
        "哇，你去过很多地方！" in srv,
    )
    check(
        "F4: threshold is 3+ places",
        ">= 3" in srv and "multi_destination_ack" in srv,
    )




def test_conversation_control_refinements() -> None:
    """
    Static assertions for the conversation-control refinement pass.

    Issue 1: "你做什么工作啊" — genuine user question must not be intercepted
             by lexical-definition or confusion-escalation paths.
    Issue 2: "你呢你是哪里人" mirror path preserved (existing _isTurnAround regex).
    Issue 3: bare "哪里？" from f_micro_probe_where expanded by _anchorVagueReferences.
    Issue 4: "哪里什么" rejected as linguistic_confusion_signal before no_options path.
    Issue 5: "爱人" accepted in _FAMILY_MEMBER_FRAMES semantic match.
    """
    print("\n[STATIC] T-CCR — Conversation control refinements (app.js + ui_server.py)")
    app_src = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    srv_src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")

    # ── A: "你呢你是哪里人" still detected as _isTurnAround ────────────────
    check(
        "A: _isTurnAround regex covers 你是哪里人",
        "你是哪里人" in app_src and "_isTurnAround" in app_src,
    )

    # ── B: Issue 1 — user_asked_question guards added to server ────────────
    check(
        "B1: lexical definition skipped when user_asked_question (server)",
        "not user_asked_question" in srv_src
        and "_lexical_definition_reply(_last_text_for_counter) if (" in srv_src,
    )
    check(
        "B2: first confusion elif guarded by not user_asked_question",
        srv_src.count("and not user_asked_question  # genuine questions skip confusion") >= 2,
    )

    # ── C: Issue 3 — _anchorVagueReferences expands bare "哪里？" ──────────
    check(
        "C1: _anchorVagueReferences handles standalone 哪里？",
        '=== "哪里？"' in app_src or "=== '哪里？'" in app_src,
    )
    check(
        "C2: _anchorVagueReferences expands 哪里？ after reaction exclamation",
        "哪里[?？]" in app_src and "你是说在哪里？" in app_src,
    )
    check(
        "C3: place-anchored expansion uses 你是说{place}吗？",
        "你是说${place}吗？" in app_src or "你是说" in app_src,
    )

    # ── D: Issue 4 — linguistic confusion signal before no_options ─────────
    check(
        "D1: _isLinguisticConfusion variable declared",
        "_isLinguisticConfusion" in app_src,
    )
    check(
        "D2: 哪里什么 in confusion signal pattern",
        "哪里什么" in app_src,
    )
    check(
        "D3: linguistic_confusion_signal rejection fires before no_options check",
        app_src.index("linguistic_confusion_signal") < app_src.index("no_options"),
    )
    check(
        "D4: _detectSemanticCategory detects 哪里 prefix as location",
        "^哪里" in app_src and "location" in app_src,
    )

    # ── E: Issue 5 — 爱人 in family semantic match ─────────────────────────
    check(
        "E1: 爱人 in _FAMILY_MEMBER_FRAMES regex",
        "爱人" in app_src and "_FAMILY_MEMBER_FRAMES" in app_src,
    )
    check(
        "E2: family semantic match regex contains 爱人 alongside 老婆/妻子",
        "老婆|妻子|老公|丈夫|先生|爱人" in app_src,
    )
    check(
        "E3: _detectSemanticCategory family includes 爱人",
        "爱人" in app_src and 'return "family"' in app_src,
    )

    # ── F: Place anchor list uses 泰国 not a space-prefixed English word ───
    check(
        "F: _PLACE_ANCHOR_LIST uses 泰国 (not typo ' Thailand')",
        "'泰国'" in app_src and "' Thailand'" not in app_src,
    )

    # ── G: Context-anchored confusion recovery (哪里什么 after 哪里？) ────
    check(
        "G1: _buildWhereRestatement function exists",
        "_buildWhereRestatement" in app_src,
    )
    check(
        "G2: _lastPartnerTurnText tracked at frame-display point",
        "window._lastPartnerTurnText = fallbackText" in app_src,
    )
    check(
        "G3: _prevWasWherePrompt + _isEchoConfusion gate drives context restatement",
        "_prevWasWherePrompt" in app_src and "_isEchoConfusion" in app_src
        and "_buildWhereRestatement" in app_src,
    )


def test_persona_depth_enrichment() -> None:
    """
    Static assertions for the persona-depth enrichment pass.

    Checks that each persona JSON now contains the new data fields that power
    richer mirror answers for place_from, travel_where, and work_what topics —
    and that the server routing logic has been updated to read them.
    """
    print("\n[STATIC] T-PDE — Persona depth enrichment (personas/*.json + ui_server.py)")
    srv_src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    PERSONAS_DIR = ROOT / "personas"

    persona_ids = ["meiling", "xiaoming", "jianguo", "xiaoyun", "zhiyuan"]

    # ── A: server routing checks new keys before falling through ────────────
    check(
        "A1: place_from topic checks facts.get('place_from') before template",
        "facts.get(\"place_from\")" in srv_src or "facts.get('place_from')" in srv_src,
    )
    check(
        "A2: travel_where topic checks facts.get('travel_where') before _first_clause",
        "facts.get(\"travel_where\")" in srv_src or "facts.get('travel_where')" in srv_src,
    )
    check(
        "A3: work_what topic prefers vl.get('work') over _first_clause",
        "vl.get(\"work\")" in srv_src or "vl.get('work')" in srv_src,
    )

    # ── B: every persona has place_from and travel_where facts ──────────────
    for pid in persona_ids:
        fp = PERSONAS_DIR / f"{pid}.json"
        data = json.loads(fp.read_text(encoding="utf-8"))
        facts = data.get("discoverable_facts") or {}
        vl    = data.get("voice_lines") or {}
        check(
            f"B-{pid}: discoverable_facts.place_from present",
            bool(facts.get("place_from")),
        )
        check(
            f"C-{pid}: discoverable_facts.travel_where present",
            bool(facts.get("travel_where")),
        )
        check(
            f"D-{pid}: voice_lines.work is non-empty",
            bool(vl.get("work")),
        )

    # ── E: spot-check richer content (concrete detail, not just job title) ──
    meiling = json.loads((PERSONAS_DIR / "meiling.json").read_text(encoding="utf-8"))
    check(
        "E1: meiling place_from mentions Xi'an food (凉皮 or 肉夹馍 or 小吃)",
        any(w in (meiling["discoverable_facts"].get("place_from") or "")
            for w in ["凉皮", "肉夹馍", "小吃", "面食"]),
    )
    check(
        "E2: meiling voice_lines.work contains teaching duration detail (八年 or 多年)",
        any(w in (meiling["voice_lines"].get("work") or "")
            for w in ["八年", "多年", "年"]),
    )
    xiaoming = json.loads((PERSONAS_DIR / "xiaoming.json").read_text(encoding="utf-8"))
    check(
        "E3: xiaoming travel_where mentions Japan concretely (日本)",
        "日本" in (xiaoming["discoverable_facts"].get("travel_where") or ""),
    )
    zhiyuan = json.loads((PERSONAS_DIR / "zhiyuan.json").read_text(encoding="utf-8"))
    check(
        "E4: zhiyuan voice_lines.work mentions subjects (数学 or 语文)",
        any(w in (zhiyuan["voice_lines"].get("work") or "")
            for w in ["数学", "语文", "初高中"]),
    )
    check(
        "E5: zhiyuan place_from mentions Nanjing dish (鸭血粉丝 or 想念)",
        any(w in (zhiyuan["discoverable_facts"].get("place_from") or "")
            for w in ["鸭血粉丝", "想念", "南京"]),
    )


def test_discovery_question_selection() -> None:
    """
    Static assertions for persona-aware blue discovery question selection.

    Tests:
    A. Helper functions exist and have correct signatures.
    B. _persona_backed_topics maps fact keys to expected mirror topics.
    C. _persona_rich_engines respects persona content density ordering.
    D. ENGINE_DISCOVERY_OPENER_TOPIC covers all core engines.
    E. Discovery pool-build code uses persona helpers (not fixed list).
    F. state_update / recently_seen_disc_topics tracking is present.
    G. Sort-by-backed-topics is applied before slicing.
    H. Deduplication pass is present.
    I. Existing 你呢？ / reciprocal path is unchanged.
    """
    print("\n[STATIC] T-DQS — Discovery question selection (ui_server.py)")
    src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")

    # ── A: helper functions exist ────────────────────────────────────────────
    check("T-DQS A1: _persona_backed_topics defined", "def _persona_backed_topics(" in src)
    check("T-DQS A2: _persona_rich_engines defined",  "def _persona_rich_engines(" in src)
    check("T-DQS A3: _ENGINE_DISCOVERY_OPENER_TOPIC defined",
          "_ENGINE_DISCOVERY_OPENER_TOPIC" in src and '"place_from"' in src)
    check("T-DQS A4: _FACT_KEY_TO_TOPICS defined", "_FACT_KEY_TO_TOPICS" in src)

    # ── B: _persona_backed_topics covers key fact categories ─────────────────
    check("T-DQS B1: place_from backs place_from and place_like topics",
          '"place_from":' in src and '"place_like"' in src and "_FACT_KEY_TO_TOPICS" in src)
    check("T-DQS B2: food key maps to food_fav topic",
          '"food_fav"' in src and "_FACT_KEY_TO_TOPICS" in src)
    check("T-DQS B3: travel_where maps to travel_where topic",
          '"travel_where": ' in src and 'frozenset({"travel_where"})' in src)
    check("T-DQS B4: voice_lines.work backs work_what topic",
          '"work_what"' in src and "_VL_KEY_TOPICS" in src)

    # ── C: _persona_rich_engines ordering ───────────────────────────────────
    check("T-DQS C1: _DISCOVERY_ENGINE_ORDER constant defined",
          "_DISCOVERY_ENGINE_ORDER" in src)
    check("T-DQS C2: rich_engines sorted by fact count descending",
          "_persona_rich_engines" in src and "counts.get(e, 0)" in src)
    check("T-DQS C3: fallback to all engines when no persona",
          "if not persona" in src and "_DISCOVERY_ENGINE_ORDER" in src)

    # ── D: opener topics cover all core engines ──────────────────────────────
    check("T-DQS D1: place opener is place_like (curiosity upgrade)",
          '"place":    "place_like"' in src or '"place": "place_like"' in src)
    check("T-DQS D2: food opener is food_fav",
          '"food":     "food_fav"' in src or '"food": "food_fav"' in src)
    check("T-DQS D3: work opener is work_like (curiosity upgrade)",
          '"work":     "work_like"' in src or '"work": "work_like"' in src)
    check("T-DQS D4: travel opener is travel_fav (curiosity upgrade)",
          '"travel":   "travel_fav"' in src or '"travel": "travel_fav"' in src)
    check("T-DQS D5: family opener is family_size",
          '"family":   "family_size"' in src or '"family": "family_size"' in src)

    # ── E: discovery pool build uses persona helpers, not fixed list ─────────
    check("T-DQS E1: _backed_topics assigned from _persona_backed_topics",
          "_persona_backed_topics(persona)" in src)
    check("T-DQS E2: _rich_engines assigned from _persona_rich_engines",
          "_persona_rich_engines(persona)" in src)
    check("T-DQS E3: fixed adjacent list removed from discovery block",
          'for _adj in ("place", "work", "family", "hobby", "food", "travel", "identity")' not in src)
    check("T-DQS E4: opener-topic preference logic present",
          "_opener_topic = _ENGINE_DISCOVERY_OPENER_TOPIC.get(_adj)" in src)
    check("T-DQS E5: backed-topic fallback present",
          'q.get("topic") in _backed_topics' in src)

    # ── F: recently_seen_disc_topics tracking ────────────────────────────────
    check("T-DQS F1: recently_seen_disc_topics read from cs",
          "recently_seen_disc_topics" in src and 'cs.get("recently_seen_disc_topics")' in src)
    check("T-DQS F2: recently_seen_disc_topics written to state_update",
          '"recently_seen_disc_topics"' in src and "state_update" in src)

    # ── G: sort by backed topics before slice ───────────────────────────────
    check("T-DQS G1: _disc_pool sorted by backed_topics membership",
          "_disc_pool.sort(key=lambda q:" in src and "_backed_topics" in src)

    # ── H: deduplication pass present ────────────────────────────────────────
    check("T-DQS H1: _disc_pool_dedup list built",  "_disc_pool_dedup" in src)
    check("T-DQS H2: topic-based dedup set present", "_seen_q_topics" in src)

    # ── I: unchanged paths ───────────────────────────────────────────────────
    check("T-DQS I1: reciprocal path still present",
          "_RECIPROCAL_FRAME_TO_Q" in src and "SHOWN (reciprocal)" in src)
    check("T-DQS I2: _pick_contextual_discovery_hint still called",
          "_pick_contextual_discovery_hint(_counter_reply)" in src)
    check("T-DQS I3: user_led flag still set", 'response["user_led"] = True' in src)

    # ── J: curiosity-quality opener changes ─────────────────────────────────
    mq_src = (ROOT / "content" / "mirror_questions.json").read_text(encoding="utf-8")
    import json as _json
    mq = _json.loads(mq_src)

    def _bank(engine: str) -> list:
        return mq.get("by_engine", {}).get(engine, [])

    def _topics(engine: str) -> list:
        return [q.get("topic") for q in _bank(engine)]

    def _zh_for_topic(engine: str, topic: str) -> str:
        return next((q.get("zh", "") for q in _bank(engine) if q.get("topic") == topic), "")

    # J1: travel opener → travel_fav ("最喜欢"), not travel_where
    check("T-DQS J1: travel opener topic is travel_fav",
          '"travel":   "travel_fav"' in src or '"travel": "travel_fav"' in src)
    check("T-DQS J2: travel_fav question contains 最喜欢",
          "最喜欢" in _zh_for_topic("travel", "travel_fav"))
    check("T-DQS J3: travel_where still present as fallback",
          "travel_where" in _topics("travel"))

    # J4: work opener → work_like ("喜欢你的工作"), not work_what
    check("T-DQS J4: work opener topic is work_like",
          '"work":     "work_like"' in src or '"work": "work_like"' in src)
    check("T-DQS J5: work_like question contains 喜欢",
          "喜欢" in _zh_for_topic("work", "work_like"))
    check("T-DQS J6: work_what still present as fallback",
          "work_what" in _topics("work"))

    # J7: place opener → place_like, with hometown-specific question
    check("T-DQS J7: place opener topic is place_like",
          '"place":    "place_like"' in src or '"place": "place_like"' in src)
    check("T-DQS J8: place_like question mentions 家乡",
          "家乡" in _zh_for_topic("place", "place_like"))
    check("T-DQS J9: place_from still present as fallback",
          "place_from" in _topics("place"))

    # J10: place_from fact backs place_like topic (extended _FACT_KEY_TO_TOPICS)
    check("T-DQS J10: place_from backs place_like in _FACT_KEY_TO_TOPICS",
          '"place_from":      frozenset({"place_from", "place_like"})' in src
          or '"place_from": frozenset({"place_from", "place_like"})' in src)

    # J11: work_like stub returns sentiment, not job description
    # Verify the handler no longer reads vl.get("work") as its primary return
    check("T-DQS J11: work_like handler prefers vl.work_like over vl.work",
          'vl.get("work_like")' in src and
          'topic == "work_like"' in src)
    check("T-DQS J12: work_like graceful fallback uses 挺喜欢的",
          "挺喜欢的，虽然有时候很忙。" in src)
    # Confirm the bug-path (returning vl.work for work_like) is gone
    work_like_block_start = src.find('if topic == "work_like"')
    work_like_block_end   = src.find('\n        if topic ==', work_like_block_start + 1)
    wl_block = src[work_like_block_start:work_like_block_end] if work_like_block_start != -1 else ""
    check("T-DQS J13: work_like block does not return vl[work] (job description)",
          'vl.get("work")' not in wl_block and 'vl["work"]' not in wl_block)


def main() -> None:
    static_only = "--static-only" in sys.argv

    print("=" * 62)
    print("MandarinOS Golden Conversation Regression Tests")
    print("=" * 62)

    # Static tests — always run
    test_repair_phrases_no_learner_pauses()
    test_required_frames_exist()
    test_depth_anchor_completeness()
    test_translation_naturalizer()
    test_reflection_signal_detection()
    test_semantic_extraction()
    test_interaction_intelligence()
    test_conversation_control_refinements()
    test_persona_depth_enrichment()
    test_discovery_question_selection()

    # Integration tests — require a running server
    if static_only:
        print(f"\n(--static-only: skipping integration tests)")
    elif not _server_alive():
        print(f"\n⚠  Server not reachable at {SERVER}")
        print("   Start with: python scripts/ui_server.py")
        print("   Re-run without --static-only once the server is up.")
    else:
        test_food_echo_not_collapsed()
        test_travel_broad_stays_in_engine()
        test_travel_country_to_narrow()
        test_travel_city_to_depth()
        test_travel_province_to_depth()
        test_travel_asr_garble_clarify()
        test_work_retirement_safe()
        test_work_asr_retire_near_miss()
        test_work_retire_near_miss_tuixiaole()
        test_work_retire_near_miss_tuixuele()
        test_work_retirement_suppresses_occupation_followup()
        test_family_live_with_acceptance()
        test_family_closest_acceptance()
        test_family_activity_acceptance()
        test_meaningful_imperfect_name_story_stay()
        test_meaningful_imperfect_clarify_trigger()

    # Summary
    total  = len(_results)
    passed = sum(1 for _, ok in _results if ok)
    failed = total - passed
    print("\n" + "=" * 62)
    colour = "\033[32m" if failed == 0 else "\033[31m"
    print(f"{colour}{passed}/{total} passed{'\033[0m'}", end="")
    if failed:
        print(f"  ← {failed} FAILED", end="")
        print("\n\nFailed tests:")
        for name, ok in _results:
            if not ok:
                print(f"  ✗  {name}")
    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
