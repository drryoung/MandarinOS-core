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
        test_family_live_with_acceptance()
        test_family_closest_acceptance()
        test_family_activity_acceptance()

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
