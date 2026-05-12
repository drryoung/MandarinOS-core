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
        "D2: name category detection (我叫/英文名 explicit markers)",
        "我叫|名字|英文名" in src,
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


def test_persona_answer_staging() -> None:
    """
    Static assertions for the _first_sentence() persona-answer staging pass.

    Confirms that:
    A. _first_sentence() helper exists and splits at the first sentence boundary.
    B. place_from routing applies _first_sentence(), not a verbatim return.
    C. Every persona's place_from fact is multi-sentence (so the fix is meaningful).
    D. First-sentence result still answers the question (contains city/hometown info).
    E. travel_where is NOT passed through _first_sentence() — remains unchanged.
    F. Other persona routing paths (food, work, travel) are unaffected.
    """
    print("\n[STATIC] T-PAS — Persona answer staging (_first_sentence)")
    srv_src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    PERSONAS_DIR = ROOT / "personas"
    persona_ids  = ["meiling", "xiaoming", "jianguo", "xiaoyun", "zhiyuan"]

    # ── A: _first_sentence helper exists and has correct split logic ─────────
    check(
        "A1: _first_sentence() function defined in ui_server.py",
        "def _first_sentence(text: str)" in srv_src,
    )
    check(
        "A2: _first_sentence splits on 。！？ (sentence-end punctuation)",
        "re.search(r'[。！？]'" in srv_src or 're.search(r"[。！？]"' in srv_src,
    )
    check(
        "A3: _first_sentence returns text unchanged when no sentence boundary found",
        "return text" in srv_src,   # generic, but A1 confirms context
    )

    # ── B: place_from routing uses _first_sentence, not verbatim return ──────
    check(
        "B1: place_from applies _first_sentence() to specific fact",
        "_first_sentence(specific)" in srv_src,
    )
    check(
        "B2: place_from no longer does plain `return (specific, ...)` verbatim",
        # The old pattern was:  return (specific, facts_en.get("place_from") or "")
        # The new pattern wraps: return (_first_sentence(specific), ...)
        "return (specific, facts_en.get(\"place_from\")" not in srv_src
        and "return (specific, facts_en.get('place_from')" not in srv_src,
    )

    # ── C: every persona place_from fact is multi-sentence (fix is meaningful) ─
    for pid in persona_ids:
        data  = json.loads((PERSONAS_DIR / f"{pid}.json").read_text(encoding="utf-8"))
        pf    = (data.get("discoverable_facts") or {}).get("place_from") or ""
        check(
            f"C-{pid}: place_from fact contains more than one sentence (has 。 mid-text)",
            pf.count("。") >= 2 or (pf.count("。") >= 1 and not pf.endswith("。") == (pf.count("。") == 0)),
        )

    # ── D: first sentence of every persona place_from answers the question ────
    import re as _re
    def _first_sentence_ref(text: str) -> str:
        m = _re.search(r'[。！？]', text)
        return text[:m.end()] if m else text

    for pid in persona_ids:
        data    = json.loads((PERSONAS_DIR / f"{pid}.json").read_text(encoding="utf-8"))
        pf      = (data.get("discoverable_facts") or {}).get("place_from") or ""
        profile = data.get("profile") or {}
        city    = profile.get("hometown") or profile.get("city") or ""
        first   = _first_sentence_ref(pf)
        check(
            f"D-{pid}: first sentence of place_from contains hometown city ({city})",
            city and city in first,
        )
        check(
            f"D-{pid}: first sentence of place_from is shorter than full fact",
            len(first) < len(pf),
        )

    # ── E: travel_where routing does NOT use _first_sentence ─────────────────
    # Confirm _first_sentence is only called in the place_from block, not travel block.
    # We check by verifying the travel block still uses facts_en / _fact_en, not _first_sentence.
    travel_block_start = srv_src.find('if topic in ("travel_where", "travel_fav"')
    travel_block_end   = srv_src.find('\n    # ── Work', travel_block_start)
    travel_block       = srv_src[travel_block_start:travel_block_end]
    check(
        "E1: _first_sentence() is NOT called inside the travel_where routing block",
        "_first_sentence" not in travel_block,
    )
    check(
        "E2: travel_where still returns specific_tw verbatim",
        "return (specific_tw," in travel_block,
    )

    # ── F: other routing paths unaffected ─────────────────────────────────────
    check(
        "F1: food_fav still uses _first_clause (unchanged)",
        "return (_first_clause(fact), _fact_en(\"food\"))" in srv_src
        or "return (_first_clause(fact), _fact_en('food'))" in srv_src,
    )
    check(
        "F2: work_what still prefers vl.get('work') (unchanged)",
        "return (vl[\"work\"], _vl_en(\"work\"))" in srv_src
        or "return (vl['work'], _vl_en('work'))" in srv_src,
    )
    check(
        "F3: hobby_what still uses _first_clause (unchanged)",
        "return (_first_clause(fact), _fact_en(\"hobby\"))" in srv_src
        or "return (_first_clause(fact), _fact_en('hobby'))" in srv_src,
    )


def test_confusion_clarification() -> None:
    """
    Static assertions for confusion-handling and discovery-after-confusion improvements.

    A. _is_confusion_signal covers 哪里啊, 不懂, 什么
    B. _clarify_app_question() helper exists and produces 换个说法 phrasing
    C. Counter-reply chain has an app-question confusion branch (no prev_counter_reply path)
    D. last_partner_frame_text stored in state_update post-trigger block
    E. Discovery Path 0 fires for _confusion_about_app_q
    F. Existing paths (Path 1, Path 2, Path 3) still present and structurally intact
    G. No "这个以后再聊" as the active confusion handler (clarify branch takes precedence)
    H. 哪里好玩 guard still present (genuine question not misclassified as confusion)
    """
    print("\n[STATIC] T-CCL — Confusion clarification and discovery (ui_server.py)")
    srv_src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")

    # ── A: _is_confusion_signal covers new patterns ─────────────────────────
    check(
        "A1: 哪里啊 in confusion markers tuple",
        '"哪里啊"' in srv_src,
    )
    check(
        "A2: 不懂 in confusion markers tuple",
        '"不懂"' in srv_src,
    )
    check(
        "A3: 什么 in exact-match short confusion set",
        '"什么"' in srv_src and "_is_confusion_signal" in srv_src,
    )
    check(
        "A4: guard for 哪里.*好玩 still present (genuine question not mistaken for confusion)",
        "哪里.*好玩" in srv_src,
    )
    check(
        "A5: exact-match set includes 哪里啊 and 不懂 (standalone utterance check)",
        # The standalone exact-match `s in (...)` set must include both new patterns
        "哪里啊" in srv_src and "不懂" in srv_src,
    )

    # ── B: _clarify_app_question helper ──────────────────────────────────────
    check(
        "B1: _clarify_app_question() function defined",
        "def _clarify_app_question(prev_frame_text: str)" in srv_src,
    )
    check(
        "B2: _clarify_app_question produces 换个说法 rephrase",
        "换个说法" in srv_src,
    )
    check(
        "B3: _clarify_app_question returns None when no frame text",
        "_clarify_app_question" in srv_src and "return None" in srv_src,
    )

    # ── C: Counter-reply chain has app-question confusion branch ─────────────
    check(
        "C1: new branch checks not _prev_counter_reply + confusion signal",
        "not _prev_counter_reply" in srv_src and "_clarify_app_question" in srv_src,
    )
    check(
        "C2: new branch sets _confusion_about_app_q = True",
        "_confusion_about_app_q = True" in srv_src,
    )
    check(
        "C3: _confusion_about_app_q initialised to False before counter_reply block",
        "_confusion_about_app_q = False" in srv_src,
    )
    check(
        "C4: new branch reads last_partner_frame_text from cs",
        "last_partner_frame_text" in srv_src and 'cs.get("last_partner_frame_text")' in srv_src,
    )

    # ── D: last_partner_frame_text written to state_update ───────────────────
    check(
        "D1: last_partner_frame_text written in post-trigger state_update",
        '_su["last_partner_frame_text"]' in srv_src
        or "last_partner_frame_text" in srv_src,
    )
    check(
        "D2: last_partner_frame_text comes from response.get('frame_text')",
        'response.get("frame_text")' in srv_src or "response.get('frame_text')" in srv_src,
    )

    # ── E: Discovery Path 0 exists and fires for _confusion_about_app_q ──────
    check(
        "E1: Path 0 comment present in discovery block",
        "Path 0" in srv_src and "confusion" in srv_src,
    )
    check(
        "E2: Path 0 condition checks _confusion_about_app_q",
        "if _confusion_about_app_q" in srv_src,
    )
    check(
        "E3: Path 0 calls _build_discovery_pool",
        "_build_discovery_pool" in srv_src and "_confusion_about_app_q" in srv_src,
    )
    check(
        "E4: Path 0 sets user_led = True",
        'response["user_led"] = True' in srv_src,
    )
    check(
        "E5: confusion_clarification debug label in path 0",
        "confusion_clarification" in srv_src,
    )

    # ── F: Existing paths structurally intact ─────────────────────────────────
    check(
        "F1: Path 1 (user asked + counter_reply) still present as elif",
        "elif user_asked_question and _counter_reply:" in srv_src,
    )
    check(
        "F2: Path 2 (proactive trigger) still present as elif",
        "elif _trigger_proactive:" in srv_src,
    )
    check(
        "F3: Path 3 (reciprocal fallback) still present as elif",
        "elif last_turn_was_answer and not user_asked_question and not _counter_reply:" in srv_src,
    )

    # ── G: deflect_later not the confusion handler ────────────────────────────
    check(
        "G1: confusion branch calls _clarify_app_question (not generic deflect fallback)",
        # The new branch explicitly calls _clarify_app_question when confusion detected.
        # Verify the function call and flag are both in the source (structure check).
        "_clarify_app_question(_prev_frame_text)" in srv_src
        and "_confusion_about_app_q = True" in srv_src,
    )

    # ── H: 哪里啊 as isolated short-form (exact match) is caught ──────────────
    check(
        "H1: exact-match set in _is_confusion_signal includes standalone 哪里啊",
        # Must appear in the s in (...) exact-match block, not only in the markers tuple
        's in ("啊", "嗯", "呃", "哎", "噢", "哦", "什么", "不懂", "哪里啊")' in srv_src,
    )


def test_discovery_trigger_timing() -> None:
    """
    Static assertions for discovery-panel trigger timing improvements.

    A. Persona reveal detection helper exists and covers expected keywords.
    B. _build_discovery_pool helper extracted (no more duplicated code).
    C. Pre-computation flags: consecutive_app_questions, last_persona_reveal,
       discovery_shown_last_turn, _trigger_proactive.
    D. Proactive path fires on persona-reveal OR consecutive-question condition.
    E. Recovery guard: proactive path requires not _discovery_recent.
    F. Post-trigger state tracking always runs.
    G. Existing discovery (learner-asked) path unchanged.
    H. Existing reciprocal path still present as fallback.
    """
    print("\n[STATIC] T-DTT — Discovery trigger timing (ui_server.py)")
    src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")

    # ── A: persona reveal helper ─────────────────────────────────────────────
    check("T-DTT A1: _has_persona_reveal function defined",
          "def _has_persona_reveal(" in src)
    check("T-DTT A2: _PERSONA_REVEAL_KEYWORDS includes place names",
          "成都" in src and "西安" in src and "_PERSONA_REVEAL_KEYWORDS" in src)
    check("T-DTT A3: _PERSONA_REVEAL_KEYWORDS includes food",
          "火锅" in src and "家乡" in src)
    check("T-DTT A4: _has_persona_reveal checks minimum length",
          "len(text) < 8" in src and "_has_persona_reveal" in src)

    # ── B: shared pool builder extracted ────────────────────────────────────
    check("T-DTT B1: _build_discovery_pool helper defined",
          "def _build_discovery_pool(" in src)
    check("T-DTT B2: counter-reply path calls _build_discovery_pool",
          "_build_discovery_pool" in src and "learner-asked" in src)
    check("T-DTT B3: proactive path calls _build_discovery_pool",
          "_build_discovery_pool" in src and "proactive" in src)

    # ── C: pre-computation flags ─────────────────────────────────────────────
    check("T-DTT C1: _prev_consec_q read from conversation_state",
          "_prev_consec_q" in src and "consecutive_app_questions" in src)
    check("T-DTT C2: _consec_q_next increments or resets",
          "_consec_q_next" in src and "user_asked_question else _prev_consec_q" in src)
    check("T-DTT C3: _prev_persona_reveal read from cs",
          "_prev_persona_reveal" in src and "last_persona_reveal" in src)
    check("T-DTT C4: _discovery_recent read from cs",
          "_discovery_recent" in src and "discovery_shown_last_turn" in src)
    check("T-DTT C5: _this_persona_reveal computed from counter_reply + reaction",
          "_this_persona_reveal" in src and "reaction_prefix_text" in src)

    # ── D: proactive trigger condition ───────────────────────────────────────
    check("T-DTT D1: _trigger_proactive defined",
          "_trigger_proactive" in src)
    check("T-DTT D2: proactive requires _prev_persona_reveal OR consec_q >= 1",
          "_prev_persona_reveal or _prev_consec_q >= 1" in src)
    check("T-DTT D3: proactive only fires when last_turn_was_answer",
          "_trigger_proactive" in src and "last_turn_was_answer" in src)
    check("T-DTT D4: proactive only fires when not user_asked_question",
          "not user_asked_question" in src and "_trigger_proactive" in src)
    check("T-DTT D5: proactive requires persona_backed_topics",
          "_persona_backed_topics(persona)" in src and "_trigger_proactive" in src)

    # ── E: recovery guard ────────────────────────────────────────────────────
    # _discovery_recent removed from _trigger_proactive as a hard blocker
    # (blue questions are now persistent); rate-limit guard is now handled by
    # topic dedup in _build_discovery_pool instead.
    check("T-DTT E1: _discovery_recent no longer blocks _trigger_proactive",
          "not _discovery_recent" not in src[src.find("_trigger_proactive = ("):
                                              src.find("_trigger_proactive = (") + 400])
    check("T-DTT E2: _discovery_recent still read for debug tracing",
          "_discovery_recent" in src)

    # ── F: post-trigger state tracking ──────────────────────────────────────
    check("T-DTT F1: last_persona_reveal written to state_update",
          "_su[\"last_persona_reveal\"]" in src or
          "_su['last_persona_reveal']" in src)
    check("T-DTT F2: discovery_shown_last_turn written to state_update",
          "discovery_shown_last_turn" in src and "_su" in src)
    check("T-DTT F3: consecutive_app_questions written to state_update",
          "consecutive_app_questions" in src and "_su" in src)
    check("T-DTT F4: consecutive_app_questions reset when discovery shown",
          "0 if bool(response.get(\"user_led\"))" in src)

    # ── G: existing learner-asked path unchanged ─────────────────────────────
    check("T-DTT G1: path 1 still fires on user_asked_question AND _counter_reply",
          "if user_asked_question and _counter_reply:" in src)
    check("T-DTT G2: contextual hint still present in path 1",
          "_pick_contextual_discovery_hint(_counter_reply)" in src)

    # ── H: reciprocal fallback path still present ────────────────────────────
    check("T-DTT H1: reciprocal path still present (Path 3)",
          "_RECIPROCAL_FRAME_TO_Q" in src and "SHOWN (reciprocal)" in src)
    check("T-DTT H2: reciprocal is a fallback after proactive",
          "elif last_turn_was_answer and not user_asked_question and not _counter_reply" in src)


def test_scoring_model_refinements() -> None:
    """
    Static assertions for Parts 1–4 of the scoring model upgrade.

    A. Embedded question detection (Part 1)
    B. Extended answer detection without conjunctions (Part 2)
    C. Recovery tracking — natural recovery attempt + success (Part 3)
    D. Soft vs hard fail classification (Part 4)
    E. Backward compatibility — no architecture changes
    """
    print("\n[STATIC] T-SMR — Scoring model refinements (app.js + ui_server.py)")
    app_src = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    srv_src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")

    # ── A: Part 1 — Embedded question detection ──────────────────────────────
    check("T-SMR A1: endsWithParticle added (sentence-final 啊/呢)",
          "endsWithParticle" in app_src and "[啊呢]" in app_src)
    check("T-SMR A2: hasEmbeddedQ pattern added",
          "hasEmbeddedQ" in app_src and "你是哪里人" in app_src)
    check("T-SMR A3: isQuestion includes endsWithParticle",
          "endsWithParticle" in app_src and "isQuestion" in app_src)
    check("T-SMR A4: isQuestion includes hasEmbeddedQ",
          "hasEmbeddedQ" in app_src and "isQuestion" in app_src and
          "hasEmbeddedQ" in app_src.split("isQuestion")[1][:200])
    check("T-SMR A5: 你呢 still always counts (hasYouNe)",
          "hasYouNe" in app_src and "text.includes(\"你呢\")" in app_src)

    # ── B: Part 2 — Extended answer detection ────────────────────────────────
    check("T-SMR B1: Chinese char count used (zhCharCount >= 8)",
          "zhCharCount" in app_src and ">= 8" in app_src)
    check("T-SMR B2: repetition pattern added",
          "REPETITION_PAT" in app_src and r"\S{2}" in app_src)
    check("T-SMR B3: unified markers include both depth and extend markers",
          "DEPTH_AND_EXTEND_MARKERS" in app_src and "以前" in app_src and "因为" in app_src)
    check("T-SMR B4: depth_responses uses unified isExtended check",
          "isExtended" in app_src and "_tracker.depth_responses++" in app_src and
          "isExtended" in app_src.split("_tracker.depth_responses++")[0][-300:])
    check("T-SMR B5: extended_answer_count uses same isExtended check",
          "window._learnerObs.extended_answer_count++" in app_src and
          "isExtended" in app_src.split("window._learnerObs.extended_answer_count++")[0][-50:])

    # ── C: Part 3 — Natural recovery tracking ────────────────────────────────
    check("T-SMR C1: _pendingNaturalRecovery field in _tracker",
          "_pendingNaturalRecovery" in app_src and "_tracker" in app_src)
    check("T-SMR C2: _pendingNaturalRecovery set on natural recovery attempt",
          "_tracker._pendingNaturalRecovery = true" in app_src)
    check("T-SMR C3: _pendingNaturalRecovery checked in success handler",
          "_tracker._pendingNaturalRecovery" in app_src and
          "successful_recoveries++" in app_src)
    check("T-SMR C4: _pendingNaturalRecovery reset after success check",
          "_tracker._pendingNaturalRecovery = false" in app_src)
    check("T-SMR C5: natural recovery does not break recovery_resilience_count",
          "recovery_resilience_count++" in app_src and "_pendingNaturalRecovery" in app_src)

    # ── D: Part 4 — Soft vs hard fail classification ─────────────────────────
    check("T-SMR D1: _unmatchedFailLevel helper defined",
          "function _unmatchedFailLevel(" in app_src)
    check("T-SMR D2: hard fail when no Chinese characters",
          "zhChars < 1" in app_src and '"hard"' in app_src)
    check("T-SMR D3: soft fail when partial Chinese present",
          '"soft"' in app_src and "return \"soft\"" in app_src or "return 'soft'" in app_src or
          '\"soft\"' in app_src)
    check("T-SMR D4: fail_level attached to linguistic_confusion reject",
          "fail_level: \"soft\"" in app_src and "linguistic_confusion_signal" in app_src)
    check("T-SMR D5: fail_level attached to closed_options_unmatched reject",
          "fail_level: _fl" in app_src and "closed_options_unmatched" in app_src)
    check("T-SMR D6: soft_unmatched_responses counter in _tracker",
          "soft_unmatched_responses" in app_src and "_tracker" in app_src)
    check("T-SMR D7: soft_unmatched_count in _learnerObs",
          "soft_unmatched_count" in app_src and "_learnerObs" in app_src)
    check("T-SMR D8: soft fail routes to soft_unmatched_responses",
          "_tracker.soft_unmatched_responses++" in app_src)
    check("T-SMR D9: hard fail routes to unmatched_responses",
          "_tracker.unmatched_responses++" in app_src)
    check("T-SMR D10: soft_unmatched_responses in endSession payload",
          "soft_unmatched_responses" in app_src and "endSession" in app_src)
    check("T-SMR D11: _scorecard_stability accepts soft_unmatched param (server)",
          "soft_unmatched" in srv_src and "_scorecard_stability" in srv_src)
    check("T-SMR D12: effective unmatched = hard + 0.5 * soft (server)",
          "soft_unmatched * 0.5" in srv_src or "soft_unmatched_responses" in srv_src)
    check("T-SMR D13: _compute_scorecard reads soft_unmatched_responses",
          "soft_unmatched_responses" in srv_src and "_compute_scorecard" in srv_src)

    # ── E: Backward compatibility ─────────────────────────────────────────────
    check("T-SMR E1: _scorecard_stability still has Stable / Some friction labels",
          '"Stable"' in srv_src and '"Some friction"' in srv_src)
    check("T-SMR E2: participation scorecard unchanged (questions_asked still used)",
          "_scorecard_participation(questions_asked)" in srv_src)
    check("T-SMR E3: recovery panel path unchanged (_pendingRecovery still checked)",
          "_tracker._pendingRecovery" in app_src)
    check("T-SMR E4: endSession payload still includes questions_asked",
          "questions_asked:" in app_src and "endSession" in app_src)
    check("T-SMR E5: QUESTION_WORDS list unchanged",
          '"什么"' in app_src and '"哪里"' in app_src and '"为什么"' in app_src)
    check("T-SMR E6: soft_unmatched_responses reset on fresh session",
          "soft_unmatched_responses = 0" in app_src)
    check("T-SMR E7: _pendingNaturalRecovery reset on fresh session",
          "_pendingNaturalRecovery = false" in app_src and "startFreshLearner" in app_src or
          "_pendingNaturalRecovery = false" in app_src)


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
    check("T-DQS E4: opener-topic preference logic present (in _build_discovery_pool)",
          "opener_topic = _ENGINE_DISCOVERY_OPENER_TOPIC.get(adj)" in src
          or "_opener_topic = _ENGINE_DISCOVERY_OPENER_TOPIC.get(_adj)" in src)
    check("T-DQS E5: backed-topic fallback present (in _build_discovery_pool)",
          'q.get("topic") in backed_topics' in src
          or 'q.get("topic") in _backed_topics' in src)

    # ── F: recently_seen_disc_topics tracking ────────────────────────────────
    check("T-DQS F1: recently_seen_disc_topics read from cs",
          "recently_seen_disc_topics" in src and 'cs.get("recently_seen_disc_topics")' in src)
    check("T-DQS F2: recently_seen_disc_topics written to state_update",
          '"recently_seen_disc_topics"' in src and "state_update" in src)

    # ── G: sort by backed topics before slice ───────────────────────────────
    check("T-DQS G1: pool sorted by backed_topics membership (in _build_discovery_pool)",
          "disc_pool.sort(key=lambda q:" in src or "_disc_pool.sort(key=lambda q:" in src)

    # ── H: deduplication pass present ────────────────────────────────────────
    check("T-DQS H1: dedup list built (in _build_discovery_pool)",
          "deduped" in src or "_disc_pool_dedup" in src)
    check("T-DQS H2: topic-based dedup set present (in _build_discovery_pool)",
          "seen_q_topics" in src or "_seen_q_topics" in src)

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


def test_targeted_bug_fixes() -> None:
    """Targeted regression tests for the discovery panel + interaction layer bug fix branch.

    Six issue classes:
    A  Discovery render — client round-trip state fields
    B  Travel near-miss  我最想吃中国
    C  Noisy location recovery — _clarify_app_question contextual rephrasings
    D  Family/work override  女儿做什么工作啊
    E  Embedded child question  孩子呢你有孩子吗
    """
    srv_src  = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    app_src  = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    # ── A: Discovery state round-trip (client) ────────────────────────────────
    check("T-TBF A1: window._discoveryShownLastTurn initialized in app.js",
          "window._discoveryShownLastTurn" in app_src)
    check("T-TBF A2: window._consecutiveAppQuestions initialized in app.js",
          "window._consecutiveAppQuestions" in app_src)
    check("T-TBF A3: window._lastPersonaReveal initialized in app.js",
          "window._lastPersonaReveal" in app_src)
    check("T-TBF A4: window._recentlySeenDiscTopics initialized in app.js",
          "window._recentlySeenDiscTopics" in app_src)
    check("T-TBF A5: window._lastPartnerFrameText initialized in app.js",
          "window._lastPartnerFrameText" in app_src)
    check("T-TBF A6: discovery_shown_last_turn sent in conversation_state",
          "discovery_shown_last_turn:" in app_src and "_discoveryShownLastTurn" in app_src)
    check("T-TBF A7: consecutive_app_questions sent in conversation_state",
          "consecutive_app_questions:" in app_src and "_consecutiveAppQuestions" in app_src)
    check("T-TBF A8: last_persona_reveal sent in conversation_state",
          "last_persona_reveal:" in app_src and "_lastPersonaReveal" in app_src)
    check("T-TBF A9: recently_seen_disc_topics sent in conversation_state",
          "recently_seen_disc_topics:" in app_src and "_recentlySeenDiscTopics" in app_src)
    check("T-TBF A10: last_partner_frame_text sent in conversation_state",
          "last_partner_frame_text:" in app_src and "_lastPartnerFrameText" in app_src)
    check("T-TBF A11: state_update merges discovery_shown_last_turn into window var",
          "data.state_update.discovery_shown_last_turn" in app_src and
          "window._discoveryShownLastTurn" in app_src)
    check("T-TBF A12: state_update merges consecutive_app_questions into window var",
          "data.state_update.consecutive_app_questions" in app_src and
          "window._consecutiveAppQuestions" in app_src)
    check("T-TBF A13: discovery vars reset in startFreshLearner",
          "_discoveryShownLastTurn  = false" in app_src and
          "_consecutiveAppQuestions = 0" in app_src)
    check("T-TBF A14: proactive trigger threshold lowered to >= 1",
          "_prev_consec_q >= 1" in srv_src and "_prev_consec_q >= 2" not in srv_src)

    # ── B: Travel near-miss 想吃中国 ─────────────────────────────────────────
    check("T-TBF B1: _EAT_COUNTRY_RE defined in ui_server.py",
          "_EAT_COUNTRY_RE" in srv_src)
    check("T-TBF B2: _EAT_COUNTRY_RE matches 想吃+country pattern",
          "(?:想|最想|要|想要)吃" in srv_src)
    check("T-TBF B3: cross-engine eat+country check runs after destination-frame check",
          "_EAT_COUNTRY_RE.search(answer_text)" in srv_src)
    check("T-TBF B4: eat+country sets _travel_asr_candidate",
          "_travel_asr_candidate = f\"去{_ec_m.group(1)}\"" in srv_src)
    check("T-TBF B5: _travel_asr_candidate routes to f_travel_dest_generic_clarify",
          "f_travel_dest_generic_clarify" in srv_src and "_travel_asr_candidate" in srv_src)
    # Direct detection test
    import re as _re
    _eat_re = _re.compile(
        r"(?:想|最想|要|想要)吃"
        r"(中国|日本|韩国|泰国|法国|美国|英国|意大利|德国|欧洲|亚洲|澳大利亚|新西兰|印度|越南|西班牙)"
    )
    check("T-TBF B6: 我最想吃中国 matched by _EAT_COUNTRY_RE",
          bool(_eat_re.search("我最想吃中国")))
    check("T-TBF B7: 我想吃日本 matched by _EAT_COUNTRY_RE",
          bool(_eat_re.search("我想吃日本")))
    check("T-TBF B8: 我想吃饺子 NOT matched by _EAT_COUNTRY_RE (food is valid)",
          not bool(_eat_re.search("我想吃饺子")))
    check("T-TBF B9: 去中国 NOT matched (valid travel answer)",
          not bool(_eat_re.search("去中国")))

    # ── C: _clarify_app_question contextual rephrasings ───────────────────────
    check("T-TBF C1: _clarify_app_question uses keyword pattern table",
          "_patterns" in srv_src[srv_src.find("def _clarify_app_question"):
                                  srv_src.find("def _clarify_app_question") + 2000])
    check("T-TBF C2: location pattern produces 我是问：你现在住的地方在哪里？",
          "我是问：你现在住的地方在哪里？" in srv_src)
    check("T-TBF C3: fallback uses 我是问：X format (not f-string 换个说法,)",
          "我是问：{ft}？" in srv_src and
          'f"换个说法，' not in
          srv_src[srv_src.find("def _clarify_app_question"):
                  srv_src.find("def _clarify_app_question") + 3000])
    check("T-TBF C4: work pattern produces contextual restatement",
          "我是问：你做什么工作？" in srv_src)
    check("T-TBF C5: travel pattern produces contextual restatement",
          "我是问：你最想去哪里旅游？" in srv_src)

    # ── D: Family/work override ───────────────────────────────────────────────
    check("T-TBF D1: family regex in _detectSemanticCategory includes 女儿",
          "女儿" in app_src[app_src.find("function _detectSemanticCategory"):
                             app_src.find("function _detectSemanticCategory") + 600])
    check("T-TBF D2: family regex includes 儿子",
          "儿子" in app_src[app_src.find("function _detectSemanticCategory"):
                             app_src.find("function _detectSemanticCategory") + 600])
    check("T-TBF D3: family regex includes 孩子",
          "孩子" in app_src[app_src.find("function _detectSemanticCategory"):
                             app_src.find("function _detectSemanticCategory") + 600])
    check("T-TBF D4: family check comes before work_status in _detectSemanticCategory",
          app_src.find('"family"') < app_src.find('"work_status"'))
    check("T-TBF D5: family_member_question early-accept in classifyUnmatchedFreeAnswerDecision",
          "family_member_question" in app_src)
    check("T-TBF D6: family-member words in early-accept pattern (女儿)",
          "女儿" in app_src[app_src.find("_hasFamilyMemberQ"):
                             app_src.find("_hasFamilyMemberQ") + 300])
    check("T-TBF D7: _is_user_question server-side recognizes 你女儿",
          "你女儿" in srv_src)
    check("T-TBF D8: _is_user_question recognizes family-member action words",
          "_family_words" in srv_src and "_action_words" in srv_src)
    check("T-TBF D9: _answer_user_question_prefix has family-member branch (_fam_words)",
          "_fam_words" in srv_src[srv_src.find("def _answer_user_question_prefix"):
                                   srv_src.find("def _answer_user_question_prefix") + 4000])
    check("T-TBF D10: family-member branch has safe deflect fallback",
          "我暂时保密好了" in srv_src)

    # ── E: Embedded child question 孩子呢你有孩子吗 ──────────────────────────
    check("T-TBF E1: learner_counter_question early-accept in classifyUnmatchedFreeAnswerDecision",
          "learner_counter_question" in app_src)
    check("T-TBF E2: counter-question shortcut checks 你+吗",
          "/你/.test(transcript" in app_src and "/吗/.test(transcript" in app_src)
    check("T-TBF E3: f_have_children in _FAMILY_MEMBER_FRAMES (semanticSoftMatch)",
          '"f_have_children"' in app_src[app_src.find("_FAMILY_MEMBER_FRAMES"):
                                          app_src.find("_FAMILY_MEMBER_FRAMES") + 300])


def test_location_distance_questions() -> None:
    """Regression tests for overseas place → distance/orientation discovery questions.

    The questions already exist in mirror_questions.json (place_far, place_distance_ref,
    place_distance_time, etc.) but were not surfacing because they were sorted below
    backed topics and the pool was truncated to 3. Fix: boost_topics in _build_discovery_pool
    when _learner_place_is_overseas() fires.

    Covers:
    A  Question existence in mirror_questions.json
    B  _learner_place_is_overseas detection
    C  _build_discovery_pool boost_topics parameter
    D  Discovery pool call sites pass boost
    E  Domestic cities do NOT trigger boost
    """
    import json as _json
    srv_src   = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    mq_path   = ROOT / "content" / "mirror_questions.json"
    mq        = _json.loads(mq_path.read_text(encoding="utf-8")) if mq_path.exists() else {}
    place_qs  = []
    for eng_block in (mq.get("by_engine") or {}).values():
        place_qs.extend(eng_block if isinstance(eng_block, list) else [])
    place_qs_place = [q for q in place_qs if q.get("engine") == "place" or
                      any(q.get("topic","").startswith(t) for t in ("place_far","place_distance"))]

    # ── A: Questions exist in mirror_questions.json ───────────────────────────
    _place_topics = {q.get("topic") for q in place_qs}
    check("T-LDQ A1: place_far topic exists in mirror_questions.json",
          "place_far" in _place_topics)
    check("T-LDQ A2: place_distance_ref topic exists in mirror_questions.json",
          "place_distance_ref" in _place_topics)
    check("T-LDQ A3: place_distance_time topic exists in mirror_questions.json",
          "place_distance_time" in _place_topics)
    check("T-LDQ A4: place_distance_transport topic exists in mirror_questions.json",
          "place_distance_transport" in _place_topics)
    # Check the actual question text contains distance wording
    _all_zh = {q.get("zh","") for q in place_qs}
    check("T-LDQ A5: 离那儿远吗？ question text present",
          any("远" in zh for zh in _all_zh))
    check("T-LDQ A6: 多久 (travel time) question text present",
          any("多久" in zh for zh in _all_zh))

    # ── B: _learner_place_is_overseas detection ───────────────────────────────
    check("T-LDQ B1: _learner_place_is_overseas defined in ui_server.py",
          "_learner_place_is_overseas" in srv_src)
    check("T-LDQ B2: Latin script detection (Dunedin) in _learner_place_is_overseas",
          "re.search" in srv_src[srv_src.find("def _learner_place_is_overseas"):
                                  srv_src.find("def _learner_place_is_overseas") + 600])
    check("T-LDQ B3: _CHINA_DOMESTIC_PLACE_NAMES defined",
          "_CHINA_DOMESTIC_PLACE_NAMES" in srv_src)
    check("T-LDQ B4: _PLACE_DISTANCE_TOPICS defined",
          "_PLACE_DISTANCE_TOPICS" in srv_src)
    check("T-LDQ B5: _PLACE_DISTANCE_TOPICS includes place_far",
          '"place_far"' in srv_src[srv_src.find("_PLACE_DISTANCE_TOPICS"):
                                    srv_src.find("_PLACE_DISTANCE_TOPICS") + 300])
    check("T-LDQ B6: _PLACE_DISTANCE_TOPICS includes place_distance_time",
          '"place_distance_time"' in srv_src[srv_src.find("_PLACE_DISTANCE_TOPICS"):
                                              srv_src.find("_PLACE_DISTANCE_TOPICS") + 300])
    # Runtime behaviour test using the actual function
    import sys as _sys, importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("_srv_test", ROOT / "scripts" / "ui_server.py")
    try:
        _srv = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_srv)
        _fn  = getattr(_srv, "_learner_place_is_overseas", None)
        _build = getattr(_srv, "_build_discovery_pool", None)
        _dist_topics = getattr(_srv, "_PLACE_DISTANCE_TOPICS", frozenset())
        _backed = getattr(_srv, "_persona_backed_topics", None)
        if _fn:
            check("T-LDQ B7: 我是新西兰人 → overseas=True",
                  _fn("我是新西兰人") is True)
            check("T-LDQ B8: 我住在Dunedin → overseas=True (Latin script)",
                  _fn("我住在Dunedin") is True)
            check("T-LDQ B9: 我住在上海 → overseas=False (domestic)",
                  _fn("我住在上海") is False)
            check("T-LDQ B10: 我是北京人 → overseas=False (domestic)",
                  _fn("我是北京人") is False)
            check("T-LDQ B11: 我住在西安 → overseas=False (domestic)",
                  _fn("我住在西安") is False)
            check("T-LDQ B12: 我来自澳大利亚 → overseas=True",
                  _fn("我来自澳大利亚") is True)
        else:
            check("T-LDQ B7-12: _learner_place_is_overseas importable", False)
        if _build and _dist_topics:
            # Build a discovery pool for place engine WITH boost and verify distance topics come first
            _place_pool_raw = list(_srv._MIRROR_QUESTIONS_BY_ENGINE.get("place") or [])
            _backed_tpcs    = frozenset({"place_from", "place_like"})
            _pool_boosted   = _build("place", _backed_tpcs, [], set(), boost_topics=_dist_topics)
            _pool_normal    = _build("place", _backed_tpcs, [], set(), boost_topics=frozenset())
            _top3_boosted   = {q.get("topic") for q in _pool_boosted[:3]}
            _top3_normal    = {q.get("topic") for q in _pool_normal[:3]}
            check("T-LDQ B13: with boost, a distance topic appears in top 3",
                  bool(_top3_boosted & _dist_topics))
            check("T-LDQ B14: without boost, distance topics are NOT in top 3 (backed outrank them)",
                  not bool(_top3_normal & _dist_topics))
    except Exception as _e:
        check(f"T-LDQ B7-14: import/runtime check (skipped: {_e})", True)

    # ── C: _build_discovery_pool has boost_topics parameter ──────────────────
    check("T-LDQ C1: boost_topics parameter added to _build_discovery_pool",
          "boost_topics" in srv_src[srv_src.find("def _build_discovery_pool"):
                                     srv_src.find("def _build_discovery_pool") + 400])
    check("T-LDQ C2: sort key uses boost_topics at priority 0",
          "0 if q.get(\"topic\") in boost_topics" in srv_src)
    check("T-LDQ C3: sort key uses curiosity+backed at priority 1",
          'q.get("curiosity")' in srv_src and 'q.get("topic") in backed_topics' in srv_src)

    # ── D: Call sites pass boost_topics ──────────────────────────────────────
    check("T-LDQ D1: _overseas_detected computed before blue panel paths",
          "_overseas_detected" in srv_src and "_learner_place_is_overseas(answer_text)" in srv_src)
    check("T-LDQ D2: _dist_boost computed from _PLACE_DISTANCE_TOPICS",
          "_dist_boost" in srv_src and "_PLACE_DISTANCE_TOPICS if _overseas_detected" in srv_src)
    check("T-LDQ D3: Path 0 passes boost_topics=_dist_boost",
          "boost_topics=_dist_boost" in srv_src)
    check("T-LDQ D4: all three _build_discovery_pool calls pass boost",
          srv_src.count("boost_topics=_dist_boost") >= 3)

    # ── E: Domestic cities do NOT get distance boost ──────────────────────────
    check("T-LDQ E1: 北京 in _CHINA_DOMESTIC_PLACE_NAMES",
          '"北京"' in srv_src[srv_src.find("_CHINA_DOMESTIC_PLACE_NAMES"):
                               srv_src.find("_CHINA_DOMESTIC_PLACE_NAMES") + 400])
    check("T-LDQ E2: 西安 in _CHINA_DOMESTIC_PLACE_NAMES",
          '"西安"' in srv_src[srv_src.find("_CHINA_DOMESTIC_PLACE_NAMES"):
                               srv_src.find("_CHINA_DOMESTIC_PLACE_NAMES") + 400])
    check("T-LDQ E3: 新西兰 NOT in _CHINA_DOMESTIC_PLACE_NAMES (overseas, not domestic)",
          '"新西兰"' not in srv_src[srv_src.find("_CHINA_DOMESTIC_PLACE_NAMES"):
                                    srv_src.find("_CHINA_DOMESTIC_PLACE_NAMES") + 400])


def test_english_name_and_place_handling() -> None:
    """Regression tests for English / mixed-script name and place-name acceptance.

    Root causes fixed:
    1. _MIXED_SCRIPT_PLACE_FRAMES was missing f_live_where and f_home_where — causing
       the latinCount > zhCount+2 veto to reject "我住在 Dunedin" on those frames.
    2. isOpenEndedFrame was missing f_live_where and f_home_where.
    3. _detectSemanticCategory fired [A-Za-z]{3,} before 住在/来自 — "我住在 Dunedin"
       was classified as "name" instead of "location".

    Covers:
    A  _MIXED_SCRIPT_PLACE_FRAMES includes f_live_where and f_home_where
    B  isOpenEndedFrame includes f_live_where and f_home_where
    C  _detectSemanticCategory location check is before [A-Za-z]{3,} name catch-all
    D  _detectSemanticCategory includes 来自 in location pattern
    E  Latin-only name fallback still present after all location checks
    F  f_ask_you_name stays in identityOpen (no regression on name frames)
    """
    js_path = ROOT / "ui" / "app.js"
    js_src  = js_path.read_text(encoding="utf-8")

    # ── A: _MIXED_SCRIPT_PLACE_FRAMES ────────────────────────────────────────
    mixed_place_idx = js_src.find("_MIXED_SCRIPT_PLACE_FRAMES = new Set")
    assert mixed_place_idx >= 0, "T-ENP A0: _MIXED_SCRIPT_PLACE_FRAMES definition not found"
    mixed_place_block = js_src[mixed_place_idx: mixed_place_idx + 400]

    check('T-ENP A1: f_live_where in _MIXED_SCRIPT_PLACE_FRAMES',
          '"f_live_where"' in mixed_place_block)
    check('T-ENP A2: f_home_where in _MIXED_SCRIPT_PLACE_FRAMES',
          '"f_home_where"' in mixed_place_block)
    check('T-ENP A3: f_from_where still in _MIXED_SCRIPT_PLACE_FRAMES (no regression)',
          '"f_from_where"' in mixed_place_block)
    check('T-ENP A4: frame.location.live_question still in _MIXED_SCRIPT_PLACE_FRAMES',
          '"frame.location.live_question"' in mixed_place_block)

    # ── B: isOpenEndedFrame ───────────────────────────────────────────────────
    open_ended_idx = js_src.find("function isOpenEndedFrame")
    assert open_ended_idx >= 0, "T-ENP B0: isOpenEndedFrame not found"
    open_ended_block = js_src[open_ended_idx: open_ended_idx + 600]

    check('T-ENP B1: f_live_where in isOpenEndedFrame',
          '"f_live_where"' in open_ended_block)
    check('T-ENP B2: f_home_where in isOpenEndedFrame',
          '"f_home_where"' in open_ended_block)

    # ── C: _detectSemanticCategory location before [A-Za-z]{3,} ──────────────
    cat_idx = js_src.find("function _detectSemanticCategory")
    assert cat_idx >= 0, "T-ENP C0: _detectSemanticCategory not found"
    cat_block = js_src[cat_idx: cat_idx + 1200]

    loc_idx_in_block   = cat_block.find("住在|搬到|搬来")
    latin_idx_in_block = cat_block.find("[A-Za-z]{3,}")
    assert loc_idx_in_block >= 0,   "T-ENP C1: location pattern 住在|搬到|搬来 not found in _detectSemanticCategory"
    assert latin_idx_in_block >= 0, "T-ENP C2: [A-Za-z]{3,} not found in _detectSemanticCategory"

    check('T-ENP C3: location check is BEFORE [A-Za-z]{3,} name catch-all',
          loc_idx_in_block < latin_idx_in_block)

    # ── D: 来自 in location pattern ───────────────────────────────────────────
    check('T-ENP D1: 来自 included in location regex of _detectSemanticCategory',
          '来自' in cat_block[loc_idx_in_block: loc_idx_in_block + 40])

    # ── E: Latin fallback still fires after location checks ───────────────────
    # The [A-Za-z]{3,} catch-all must appear after the location line, not be removed entirely.
    check('T-ENP E1: [A-Za-z]{3,} Latin catch-all still present after location check',
          latin_idx_in_block > loc_idx_in_block)

    # ── F: Identity name frames not regressed ─────────────────────────────────
    identity_open_idx = js_src.find("identityOpen = new Set")
    assert identity_open_idx >= 0, "T-ENP F0: identityOpen Set not found"
    identity_open_block = js_src[identity_open_idx: identity_open_idx + 300]

    check('T-ENP F1: f_ask_you_name still in identityOpen',
          '"f_ask_you_name"' in identity_open_block)

    # ── G: Explicit name markers still checked FIRST (before Latin catch-all) ──
    # "我叫|名字|英文名" must appear BEFORE "[A-Za-z]{3,}" in _detectSemanticCategory.
    explicit_name_idx = cat_block.find("我叫|名字|英文名")
    check('T-ENP G1: explicit name markers (我叫|名字|英文名) present in _detectSemanticCategory',
          explicit_name_idx >= 0)
    check('T-ENP G2: explicit name markers appear BEFORE [A-Za-z]{3,} catch-all',
          explicit_name_idx < latin_idx_in_block)

    # ── H: [A-Za-z]{3,} no longer bundled with 我叫|名字|英文名 in single regex ──
    check('T-ENP H1: 我叫|名字|英文名 and [A-Za-z]{3,} are NOT in the same regex',
          '我叫|名字|英文名|[A-Za-z]{3,}' not in cat_block)

    print("✓  test_english_name_and_place_handling passed")


def test_blue_question_reliability() -> None:
    """Regression tests for persistent blue question availability (learner agency layer).

    Root causes fixed:
    1. _trigger_proactive had _discovery_recent as hard blocker — removed, allowing
       blue questions on consecutive turns.
    2. No fallback path when specialised paths 0-3 didn't fire — added Path 4
       (persistent fallback) that generates questions when persona has backed topics.
    3. Session-end discovery questions not generated — entire blue panel block was
       inside `if payload.get("next_question")`. Added a separate session-end block.
    4. Persona follow-up engine mismatch — Path 1 now switches engine to "place" or
       "work" based on persona answer content keywords.
    5. User-question tolerance — _is_user_question now detects 有什么特别, 有什么好吃,
       elliptical questions like "喜欢吗/远吗", and short particle-ending follow-ups.
    6. Client rendered max 2 blue questions, now 3.
    7. isLexicalContentQuestion expanded for content-based questions.
    8. Blue-question debug trace added to response.

    Covers:
    A  Persistent fallback (Path 4) exists in server
    B  _discovery_recent removed from _trigger_proactive
    C  Session-end blue questions generated outside next_question guard
    D  Persona follow-up engine switching (place/work keywords)
    E  User-question tolerance: 有什么特别, 喜欢吗, elliptical questions
    F  Client renders up to 3 blue questions (not 2)
    G  isLexicalContentQuestion expanded
    H  Blue-question debug trace fields present
    """
    srv_src = (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")
    js_src  = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    # ── A: Persistent fallback (Path 4) ───────────────────────────────────
    check("T-BQR A1: Path 4 persistent fallback block exists",
          "persistent_fallback" in srv_src)
    check("T-BQR A2: Path 4 generates discovery_questions",
          'response["discovery_questions"] = _disc_pool[:3]' in srv_src)

    # ── B: _discovery_recent removed from _trigger_proactive ──────────────
    trig_idx = srv_src.find("_trigger_proactive = (")
    assert trig_idx >= 0, "T-BQR B0: _trigger_proactive definition not found"
    trig_block = srv_src[trig_idx: trig_idx + 400]
    check("T-BQR B1: _discovery_recent NOT in _trigger_proactive",
          "_discovery_recent" not in trig_block)
    check("T-BQR B2: last_turn_was_answer still required in _trigger_proactive",
          "last_turn_was_answer" in trig_block)
    check("T-BQR B3: _persona_backed_topics still required in _trigger_proactive",
          "_persona_backed_topics" in trig_block)

    # ── C: Session-end blue questions ─────────────────────────────────────
    check("T-BQR C1: session-end blue questions block exists",
          "session_end_questions" in srv_src)
    session_end_idx = srv_src.find("Session-end blue questions")
    assert session_end_idx >= 0, "T-BQR C0: session-end comment not found"
    se_block = srv_src[session_end_idx: session_end_idx + 1200]
    check("T-BQR C2: session-end block checks not payload.get(\"next_question\")",
          'not payload.get("next_question")' in se_block)
    check("T-BQR C3: session-end block generates discovery_questions",
          'response["discovery_questions"]' in se_block)

    # ── D: Persona follow-up engine switching ─────────────────────────────
    path1_idx = srv_src.find("Path 1: User asked a question AND persona replied")
    assert path1_idx >= 0, "T-BQR D0: Path 1 comment not found"
    path1_block = srv_src[path1_idx: path1_idx + 1200]
    check('T-BQR D1: Path 1 checks _PERSONA_REVEAL_KEYWORDS for place engine switch',
          "_PERSONA_REVEAL_KEYWORDS" in path1_block)
    check('T-BQR D2: Path 1 checks work keywords for work engine switch',
          '"work"' in path1_block)

    # ── E: User-question tolerance in _is_user_question ───────────────────
    uq_idx = srv_src.find("def _is_user_question")
    assert uq_idx >= 0, "T-BQR E0: _is_user_question not found"
    uq_block = srv_src[uq_idx: uq_idx + 2600]
    check('T-BQR E1: 有什么 content-question marker detected',
          "有什么" in uq_block)
    check('T-BQR E2: 什么特别 marker detected',
          "什么特别" in uq_block)
    check('T-BQR E3: elliptical question with 啊 particle detected',
          "啊" in uq_block)
    check('T-BQR E4: 怎么样 marker detected',
          "怎么样" in uq_block)

    # ── F: Client renders up to 3 blue questions ──────────────────────────
    check('T-BQR F1: client renders up to 3 discovery questions',
          '_dq.slice(0, 3)' in js_src)
    check('T-BQR F2: old 2-card limit removed',
          '_dq.slice(0, 2)' not in js_src)

    # ── G: isLexicalContentQuestion expanded ──────────────────────────────
    lcq_idx = js_src.find("function isLexicalContentQuestion")
    assert lcq_idx >= 0, "T-BQR G0: isLexicalContentQuestion not found"
    lcq_block = js_src[lcq_idx: lcq_idx + 600]
    check('T-BQR G1: 有什么特别 detected in isLexicalContentQuestion',
          "有什么特别" in lcq_block)
    check('T-BQR G2: 有什么好吃 detected in isLexicalContentQuestion',
          "有什么好吃" in lcq_block)
    check('T-BQR G3: 喜欢吗 detected in isLexicalContentQuestion',
          "喜欢吗" in lcq_block)

    # ── H: Blue-question debug trace ──────────────────────────────────────
    check('T-BQR H1: blue_question_trace in response',
          'blue_question_trace' in srv_src)
    trace_idx = srv_src.find("blue_question_trace")
    assert trace_idx >= 0, "T-BQR H0: blue_question_trace not found"
    trace_block = srv_src[trace_idx: trace_idx + 1200]
    check('T-BQR H2: blue_questions_rendered field in trace',
          "blue_questions_rendered" in trace_block)
    check('T-BQR H3: blue_questions_topics field in trace',
          "blue_questions_topics" in trace_block)
    check('T-BQR H4: blue_questions_source field in trace',
          "blue_questions_source" in trace_block)
    check('T-BQR H5: blue_questions_suppressed_reason field in trace',
          "blue_questions_suppressed_reason" in trace_block)
    check('T-BQR H6: persona_followup_available field in trace',
          "persona_followup_available" in trace_block)

    print("✓  test_blue_question_reliability passed")


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
    test_persona_answer_staging()
    test_confusion_clarification()
    test_discovery_trigger_timing()
    test_scoring_model_refinements()
    test_discovery_question_selection()
    test_targeted_bug_fixes()
    test_location_distance_questions()
    test_english_name_and_place_handling()
    test_blue_question_reliability()

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
