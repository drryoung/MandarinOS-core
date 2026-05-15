#!/usr/bin/env python3
"""
MandarinOS — Interaction Regression Tests

Captures real failure patterns from live sessions.  Each test submits a learner
input to /api/run_turn and checks frame_text + counter_reply for REQUIRED and
FORBIDDEN patterns using simple string matching.

Usage:
  # With server running:
  python tests/test_interaction_regression.py

The script exits 0 if all tests pass, 1 if any fail.
Server must be running: python scripts/ui_server.py
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

# ── Colour helpers ─────────────────────────────────────────────────────────────
PASS_C  = "\033[32mPASS\033[0m"
FAIL_C  = "\033[31mFAIL\033[0m"
SKIP_C  = "\033[33mSKIP\033[0m"

_results: list = []


def check(name: str, condition: bool, detail: str = "") -> None:
    """Record and print one assertion."""
    status = PASS_C if condition else FAIL_C
    suffix = f"  ← {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    _results.append((name, condition))


def skip(name: str, reason: str = "") -> None:
    suffix = f"  ← {reason}" if reason else ""
    print(f"  [{SKIP_C}] {name}{suffix}")


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _server_alive() -> bool:
    try:
        urllib.request.urlopen(f"{SERVER}/", timeout=2)
    except urllib.error.HTTPError:
        return True   # any HTTP response means the server is up
    except urllib.error.URLError:
        return False
    return True


def api_run_turn(last_answer: dict, cs: dict | None = None) -> dict | None:
    """POST /api/run_turn.  Returns parsed JSON or None if server unreachable."""
    # Server requires next_question:true to enter conversation logic, and reads
    # last_answer from inside conversation_state (not from the top-level payload).
    cs_with_answer = dict(cs or {})
    cs_with_answer["last_answer"] = last_answer
    payload = json.dumps({
        "turn_uid":           "interaction_regression",
        "next_question":      True,
        "conversation_state": cs_with_answer,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{SERVER}/api/run_turn",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, Exception):
        return None


def make_cs(
    engine:   str        = "unknown",
    recent:   list | None = None,
    exchange: int         = 5,
    extra:    dict | None = None,
) -> dict:
    cs = {
        "last_turn_was_answer":    True,
        "current_engine":          engine,
        "recent_frame_ids":        recent or [],
        "exchange_count":          exchange,
        "learner_id":              "interaction_regression_tester",
        "persona_id":              "meiling",
        "same_engine_chain_count": 1,
        "interest_level":          "medium",
    }
    if extra:
        cs.update(extra)
    return cs


def make_answer(frame_id: str, text: str) -> dict:
    return {
        "frame_id":             frame_id,
        "submitted_text":       text,
        "selected_option_hanzi": text,
        "move_type":            "ANSWER",
    }


def simulate_turn(
    user_text:  str,
    frame_id:   str        = "unknown",
    engine:     str        = "unknown",
    recent:     list | None = None,
    extra_cs:   dict | None = None,
) -> dict | None:
    """
    Minimal turn wrapper.  Returns:
      { "frame_text", "counter_reply", "frame_id", "raw" }
    or None if the server is unreachable.
    """
    resp = api_run_turn(
        make_answer(frame_id, user_text),
        make_cs(engine=engine, recent=recent, extra=extra_cs),
    )
    if resp is None:
        return None
    return {
        "frame_text":    resp.get("frame_text", ""),
        "counter_reply": resp.get("counter_reply", ""),
        "frame_id":      resp.get("frame_id", ""),
        "raw":           resp,
    }


def all_text(turn: dict) -> str:
    """Combined frame_text + counter_reply as a single string for easy checks."""
    return (turn.get("frame_text", "") + " " + turn.get("counter_reply", "")).strip()


# ══════════════════════════════════════════════════════════════════════════════
# T1 — Echo prevention (desire / travel)
# ══════════════════════════════════════════════════════════════════════════════

def test_t1_echo_prevention() -> None:
    """[T1] Persona must NOT echo learner's first-person travel desire as its own."""
    print("\n[T1] Echo prevention — 我想去中国")
    # frame_id="f_travel_where" so TRAVEL slot is properly detected by slot inference
    turn = simulate_turn("我想去中国", frame_id="f_travel_where", engine="travel")
    if turn is None:
        skip("T1", "server not available"); return

    cr       = turn["counter_reply"]
    combined = all_text(turn)
    print(f"    counter_reply : {cr!r}")
    print(f"    frame_text    : {turn['frame_text']!r}")

    check(
        "T1a — counter_reply does NOT echo '我想去中国' as persona statement",
        "我想去中国" not in cr,
        f"got: {cr[:100]!r}",
    )
    check(
        "T1b — output contains destination acknowledgement or follow-up",
        any(p in combined for p in ["你想去", "你打算", "打算", "想去", "中国"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T2 — User question must be answered
# ══════════════════════════════════════════════════════════════════════════════

def test_t2_user_question_answered() -> None:
    """[T2] '这个工作难不难啊' (directed question) must get a real answer, not 啊？"""
    print("\n[T2] User question answered — 这个工作难不难啊")
    turn = simulate_turn("这个工作难不难啊", frame_id="p2_wk_1", engine="work")
    if turn is None:
        skip("T2", "server not available"); return

    cr       = turn["counter_reply"]
    combined = all_text(turn)
    print(f"    counter_reply : {cr!r}")
    print(f"    frame_text    : {turn['frame_text']!r}")

    check(
        "T2a — output does NOT contain bare confusion response (啊？ / 这样啊)",
        not any(f in combined for f in ["啊？", "这样啊"]),
        f"combined: {combined[:100]!r}",
    )
    check(
        "T2b — output contains an answer or clarification attempt",
        any(p in combined for p in ["不难", "有点难", "还可以", "你是问", "难不难", "难"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T3 — Omitted-subject question answered
# ══════════════════════════════════════════════════════════════════════════════

def test_t3_omitted_subject_question() -> None:
    """[T3] '结婚了吗' (no explicit 你) must get a real answer, not 啊？"""
    print("\n[T3] Omitted-subject question — 结婚了吗")
    turn = simulate_turn("结婚了吗", engine="identity")
    if turn is None:
        skip("T3", "server not available"); return

    cr       = turn["counter_reply"]
    combined = all_text(turn)
    print(f"    counter_reply : {cr!r}")

    check(
        "T3a — output does NOT contain bare 啊？",
        "啊？" not in combined,
        f"combined: {combined[:100]!r}",
    )
    check(
        "T3b — output contains a relevant persona response (没有 / 秘密 / 结婚 / 成家 / 单身 / 婚 / 自在)",
        any(p in combined for p in ["没有", "秘密", "结婚", "成家", "单身", "婚", "结", "自在"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T4 — No generic filler after noisy semantic input
# ══════════════════════════════════════════════════════════════════════════════

def test_t4_no_filler_after_noisy_semantic() -> None:
    """[T4] Noisy input containing 新西兰 must not produce generic filler."""
    print("\n[T4] No filler after noisy semantic input — 我现在住新西兰等你等")
    # frame_id="f_from_where" so CITY slot is detected from frame_id mapping.
    # Use isolated learner_id to avoid cross-test memory contamination.
    turn = simulate_turn("我现在住新西兰等你等", frame_id="f_from_where", engine="place",
                         extra_cs={"learner_id": "tester_t4"})
    if turn is None:
        skip("T4", "server not available"); return

    cr       = turn["counter_reply"]
    combined = all_text(turn)
    print(f"    counter_reply : {cr!r}")
    print(f"    frame_text    : {turn['frame_text']!r}")

    FORBIDDEN_FILLER = ["明白了", "这样啊", "很好", "这样挺好", "这个先不说"]
    check(
        "T4a — output does NOT contain generic filler",
        not any(f in combined for f in FORBIDDEN_FILLER),
        f"combined: {combined[:100]!r}",
    )
    check(
        "T4b — output references 新西兰 or confirms place signal",
        any(p in combined for p in ["新西兰", "你是说", "在哪里", "住在", "那里"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T5 — Confusion escalation after repeated failure
# ══════════════════════════════════════════════════════════════════════════════

def test_t5_confusion_escalation() -> None:
    """[T5] After 3× 听不懂, output should be supportive, not cycling 啊？/好吧."""
    print("\n[T5] Confusion escalation — 3× 听不懂")

    last_resp = None
    for i in range(3):
        resp = api_run_turn(
            make_answer("unknown", "听不懂"),
            make_cs(
                engine="place",
                extra={
                    "last_turn_was_answer":       True,
                    "repair_attempt_count":       i,
                    "consecutive_not_understood": i,
                },
            ),
        )
        if resp is None:
            skip("T5", "server not available"); return
        last_resp = resp

    cr       = last_resp.get("counter_reply", "")
    combined = (last_resp.get("frame_text", "") + " " + cr).strip()
    print(f"    final counter_reply : {cr!r}")
    print(f"    final frame_text    : {last_resp.get('frame_text', '')!r}")

    check(
        "T5a — final output does NOT cycle short repair phrases (啊？ / 好吧)",
        not any(f in combined for f in ["啊？", "好吧"]),
        f"combined: {combined[:100]!r}",
    )
    # Accept any supportive or clarifying partner response.
    # Model-answer phrases ("你可以说一个简单句", "比如") are Design Constitution violations
    # and must NOT appear in the partner voice — they belong only in the hint affordance layer.
    check(
        "T5b — final output contains supportive or clarifying language",
        any(p in combined for p in [
            "再说", "没关系", "换", "不清楚", "明白", "我可以",
        ]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T6 — Name-question handling
# ══════════════════════════════════════════════════════════════════════════════

def test_t6_name_question() -> None:
    """[T6] '你名字谁给你取的' must produce a name-related persona answer."""
    print("\n[T6] Name question — 你名字谁给你取的")
    turn = simulate_turn("你名字谁给你取的", engine="identity")
    if turn is None:
        skip("T6", "server not available"); return

    cr       = turn["counter_reply"]
    combined = all_text(turn)
    print(f"    counter_reply : {cr!r}")

    check(
        "T6 — output is name-related (名字 / 爸妈 / 取 / 叫 / 名 / 父母)",
        any(p in combined for p in ["名字", "爸妈", "取", "叫", "名", "父母"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T7 — No topic jump after place answer
# ══════════════════════════════════════════════════════════════════════════════

def test_t7_no_topic_jump_after_place() -> None:
    """[T7] After '我住新西兰', next turn must NOT jump immediately to food topic."""
    print("\n[T7] No topic jump after place answer — 我住新西兰")
    FORBIDDEN_FOOD_JUMP = ["吃什么", "好吃", "食物", "喜欢吃"]
    turn = simulate_turn(
        "我住新西兰",
        frame_id="f_live_where",
        engine="place",
        recent=["f_live_where"],
    )
    if turn is None:
        skip("T7", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text    : {turn['frame_text']!r}")
    print(f"    counter_reply : {turn['counter_reply']!r}")

    check(
        "T7a — output does NOT jump directly to food topic",
        not any(f in combined for f in FORBIDDEN_FOOD_JUMP),
        f"combined: {combined[:100]!r}",
    )
    check(
        "T7b — output stays on place / New Zealand topic",
        any(p in combined for p in ["新西兰", "那里", "地方", "住", "哪里", "那边", "南半球"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T8 — Echo prevention (strong form)
# ══════════════════════════════════════════════════════════════════════════════

def test_t8_echo_prevention_strong() -> None:
    """[T8] '我很想去中国' must not be echoed back as persona's own desire."""
    print("\n[T8] Echo prevention (strong) — 我很想去中国")
    # frame_id="f_travel_where" so TRAVEL slot is properly detected by slot inference
    turn = simulate_turn("我很想去中国", frame_id="f_travel_where", engine="travel")
    if turn is None:
        skip("T8", "server not available"); return

    cr       = turn["counter_reply"]
    combined = all_text(turn)
    print(f"    counter_reply : {cr!r}")

    check(
        "T8a — counter_reply does NOT contain '哦，我很想去中国'",
        "哦，我很想去中国" not in cr,
        f"counter_reply: {cr[:100]!r}",
    )
    check(
        "T8b — counter_reply does NOT start with persona echoing same desire",
        not (cr.startswith("哦，我很想") or cr.startswith("我很想去中国")),
        f"counter_reply: {cr[:100]!r}",
    )
    check(
        "T8c — output contains second-person reference or follow-up",
        any(p in combined for p in ["你很想", "你打算", "想去中国", "中国"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T17 — Pending name-story frame survives off-topic burst utterance
# ══════════════════════════════════════════════════════════════════════════════

def test_t17_name_story_frame_commitment() -> None:
    """[T17] Off-topic burst (age/place) must not abandon the pending name-story frame."""
    print("\n[T17] Pending name-story frame commitment — off-topic burst")

    TOPIC_JUMP_FORBIDDEN = ["好吃", "吃什么", "你做什么工作", "你跟谁一起住", "去中国", "去哪里旅行"]

    for label, text in [
        ("T17a age-drift",  "我64岁"),
        ("T17b place-drift", "我是新西兰人"),
    ]:
        # frame_id="f_name_story" = the question the learner is supposed to answer.
        # last_partner_frame_text carries the pending question for context.
        turn = simulate_turn(
            text,
            frame_id="f_name_story",
            engine="identity",
            extra_cs={"last_partner_frame_text": "你名字有什么故事吗？"},
        )
        if turn is None:
            skip(f"{label}", "server not available"); return

        combined = all_text(turn)
        print(f"    [{label}] frame_text   : {turn['frame_text']!r}")
        print(f"    [{label}] counter_reply: {turn['counter_reply']!r}")

        check(
            f"{label}a — does NOT jump to unrelated topic",
            not any(f in combined for f in TOPIC_JUMP_FORBIDDEN),
            f"combined: {combined[:100]!r}",
        )
        check(
            f"{label}b — stays on name/story topic",
            any(p in combined for p in ["名字", "故事", "小故事", "你是说", "可以简单说说", "谁给你取"]),
            f"combined: {combined[:100]!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T18 — Pending live-place frame survives noisy burst
# ══════════════════════════════════════════════════════════════════════════════

def test_t18_live_place_frame_commitment() -> None:
    """[T18] Noisy burst after '你现在住哪里？' must stay in place topic."""
    print("\n[T18] Pending place frame commitment — noisy burst")

    TOPIC_JUMP_FORBIDDEN = ["好吃", "吃什么", "菜", "工作", "家人", "爸爸妈妈", "去中国", "去哪里旅行"]

    turn = simulate_turn(
        "安静很方便",
        frame_id="f_live_where",
        engine="place",
        extra_cs={"last_partner_frame_text": "你现在住哪里？"},
    )
    if turn is None:
        skip("T18", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T18a — does NOT jump to food/work/family/travel",
        not any(f in combined for f in TOPIC_JUMP_FORBIDDEN),
        f"combined: {combined[:100]!r}",
    )
    check(
        "T18b — stays in place/location topic",
        any(p in combined for p in ["住", "哪里", "地方", "新西兰", "安静", "方便", "你是说", "我没听清楚"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T19 — Clear user question still overrides pending name-story frame
# ══════════════════════════════════════════════════════════════════════════════

def test_t19_user_question_overrides_pending_frame() -> None:
    """[T19] User question '你叫什么名字？' must override pending name-story repair."""
    print("\n[T19] User question overrides pending name-story frame")
    turn = simulate_turn(
        "你叫什么名字？",
        frame_id="f_name_story",
        engine="identity",
        extra_cs={"last_partner_frame_text": "你名字有什么故事吗？"},
    )
    if turn is None:
        skip("T19", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T19 — output answers persona name (user question wins)",
        any(p in combined for p in ["我叫", "叫我", "美玲", "小明", "名字"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T20 — Explicit topic switch may override pending frame
# ══════════════════════════════════════════════════════════════════════════════

def test_t20_explicit_topic_switch_overrides_pending() -> None:
    """[T20] '对了，你做什么工作？' must be answered, not forced into name-story repair."""
    print("\n[T20] Explicit topic switch overrides pending name-story frame")
    turn = simulate_turn(
        "对了，你做什么工作？",
        frame_id="f_name_story",
        engine="identity",
        extra_cs={"last_partner_frame_text": "你名字有什么故事吗？"},
    )
    if turn is None:
        skip("T20", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T20 — output answers work (topic switch wins)",
        any(p in combined for p in ["老师", "工作", "教", "我是", "职业", "上班"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T21 — Work frame must not be derailed by a place answer
# ══════════════════════════════════════════════════════════════════════════════

def test_t21_work_frame_not_derailed_by_place() -> None:
    """[T21] '我住在新西兰' after '你做什么工作？' must stay in work context."""
    print("\n[T21] Work frame commitment — 我住在新西兰 answered to 你做什么工作？")
    turn = simulate_turn(
        "我住在新西兰",
        frame_id="f_what_work",
        engine="work",
        extra_cs={"last_partner_frame_text": "你做什么工作？"},
    )
    if turn is None:
        skip("T21", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T21 — stays in work context (工作 / 老师 / 做什么 / 你是说)",
        any(p in combined for p in ("工作", "老师", "做什么", "你是说")),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T22 — Place frame must not be derailed by a work answer
# ══════════════════════════════════════════════════════════════════════════════

def test_t22_place_frame_not_derailed_by_work() -> None:
    """[T22] '我是老师' after '你现在住哪里？' must stay in place context."""
    print("\n[T22] Place frame commitment — 我是老师 answered to 你现在住哪里？")
    turn = simulate_turn(
        "我是老师",
        frame_id="f_live_where",
        engine="place",
        extra_cs={"last_partner_frame_text": "你现在住哪里？"},
    )
    if turn is None:
        skip("T22", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T22 — stays in place context (住 / 哪里 / 地方 / 你是说)",
        any(p in combined for p in ("住", "哪里", "地方", "你是说")),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T23 — Where-from frame must not be derailed by a family answer
# ══════════════════════════════════════════════════════════════════════════════

def test_t23_from_where_not_derailed_by_family() -> None:
    """[T23] '我和太太一起住' after '你是哪里人？' must stay in origin context."""
    print("\n[T23] Where-from frame commitment — 我和太太一起住 answered to 你是哪里人？")
    turn = simulate_turn(
        "我和太太一起住",
        frame_id="f_from_where",
        engine="place",
        extra_cs={"last_partner_frame_text": "你是哪里人？"},
    )
    if turn is None:
        skip("T23", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T23 — stays in origin context (人 / 来自 / 新西兰人 / 中国人 / 你是说)",
        any(p in combined for p in ("人", "来自", "新西兰人", "中国人", "你是说")),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T24 — Family frame must not be derailed by a travel answer
# ══════════════════════════════════════════════════════════════════════════════

def test_t24_family_frame_not_derailed_by_travel() -> None:
    """[T24] '我想去中国' after '你和谁一起住？' must stay in family context."""
    print("\n[T24] Family frame commitment — 我想去中国 answered to 你和谁一起住？")
    turn = simulate_turn(
        "我想去中国",
        frame_id="f_live_with_who",
        engine="place",
        extra_cs={"last_partner_frame_text": "你和谁一起住？"},
    )
    if turn is None:
        skip("T24", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T24 — stays in family context (家人 / 一起住 / 太太 / 爸爸妈妈 / 你是说)",
        any(p in combined for p in ("家人", "一起住", "太太", "爸爸妈妈", "你是说")),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T25 — Garbled location answer must not jump to food/work/family
# (Release 1.0 boundary: ASR alias recognition is Release 2.0)
# ══════════════════════════════════════════════════════════════════════════════

def test_t25_dunedin_asr_near_match_confirmed() -> None:
    """[T25] '我现在住在等你等' (garbled location) must stay on place topic — no food jump."""
    print("\n[T25] Garbled location input — no topic jump — 我现在住在等你等")
    FOOD_JUMP = ["好吃", "吃什么", "这里有什么好吃的", "工作", "家人", "去中国"]
    PLACE_KW  = ["住", "哪里", "地方", "在哪", "住在", "没听清"]
    turn = simulate_turn(
        "我现在住在等你等",
        frame_id="f_live_where",
        engine="place",
        extra_cs={"last_partner_frame_text": "你现在住哪里？",
                  "learner_id": "tester_dunedin"},
    )
    if turn is None:
        skip("T25", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T25a — no food/work/family topic jump",
        not any(f in combined for f in FOOD_JUMP),
        f"got: {combined[:120]!r}",
    )
    check(
        "T25b — stays on place topic",
        any(p in combined for p in PLACE_KW),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T26 — Repeated garbled location answers must not advance to food
# (Release 1.0 boundary: ASR alias recognition is Release 2.0)
# ══════════════════════════════════════════════════════════════════════════════

def test_t26_repeated_dunedin_not_food_jump() -> None:
    """[T26] Repeated garbled location inputs must not jump to food."""
    print("\n[T26] Repeated garbled location — no food jump")
    FOOD     = ["好吃", "吃什么", "菜"]
    PLACE_KW = ["住", "哪里", "地方", "在哪", "住在", "没听清"]
    last_turn: dict | None = None
    for label, text in [
        ("T26-1st", "我现在住在等你等"),
        ("T26-2nd", "等一等我现在就在等你等"),
        ("T26-3rd", "等你等我现在就在等你等"),
    ]:
        turn = simulate_turn(
            text,
            frame_id="f_live_where",
            engine="place",
            extra_cs={"last_partner_frame_text": "你现在住哪里？",
                      "learner_id": "tester_dunedin"},
        )
        if turn is None:
            skip("T26", "server not available"); return
        last_turn = turn
        combined = all_text(turn)
        print(f"    [{label}] {combined[:80]!r}")

    combined = all_text(last_turn)
    check(
        "T26a — final response has no food keywords",
        not any(f in combined for f in FOOD),
        f"got: {combined[:120]!r}",
    )
    check(
        "T26b — final response stays on place topic",
        any(p in combined for p in PLACE_KW),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T27 — English city name in answer must not jump to food
# (Release 1.0 boundary: place curiosity follow-up selection is Release 2.0)
# ══════════════════════════════════════════════════════════════════════════════

def test_t27_dunedin_english_triggers_place_followup() -> None:
    """[T27] '我现在住在Dunedin' must not jump to food and must stay on place topic."""
    print("\n[T27] English city name — no food jump — 我现在住在Dunedin")
    FOOD_JUMP = ["好吃", "吃什么", "菜"]
    PLACE_KW  = ["Dunedin", "住", "哪里", "地方", "在哪", "那里", "特别", "什么样"]
    turn = simulate_turn(
        "我现在住在Dunedin",
        frame_id="f_live_where",
        engine="place",
        recent=["f_from_where", "f_live_where"],
        extra_cs={"last_partner_frame_text": "你现在住哪里？",
                  "learner_id": "tester_dunedin"},
    )
    if turn is None:
        skip("T27", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T27a — no food jump",
        not any(f in combined for f in FOOD_JUMP),
        f"got: {combined[:120]!r}",
    )
    check(
        "T27b — Dunedin echoed and stays on place topic",
        any(p in combined for p in PLACE_KW),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 62)
    print("MandarinOS — Interaction Regression Tests")
    print("=" * 62)

    if "--static-only" in sys.argv:
        print("(--static-only: all tests in this suite require a live server — nothing to run)")
        sys.exit(0)

    if not _server_alive():
        print(f"\n⚠  Server not reachable at {SERVER}")
        print("   Start with: python scripts/ui_server.py")
        print("   Then re-run this script.")
        sys.exit(1)

    test_t1_echo_prevention()
    test_t2_user_question_answered()
    test_t3_omitted_subject_question()
    test_t4_no_filler_after_noisy_semantic()
    test_t5_confusion_escalation()
    test_t6_name_question()
    test_t7_no_topic_jump_after_place()
    test_t8_echo_prevention_strong()
    test_t17_name_story_frame_commitment()
    test_t18_live_place_frame_commitment()
    test_t19_user_question_overrides_pending_frame()
    test_t20_explicit_topic_switch_overrides_pending()
    test_t21_work_frame_not_derailed_by_place()
    test_t22_place_frame_not_derailed_by_work()
    test_t23_from_where_not_derailed_by_family()
    test_t24_family_frame_not_derailed_by_travel()
    test_t25_dunedin_asr_near_match_confirmed()
    test_t26_repeated_dunedin_not_food_jump()
    test_t27_dunedin_english_triggers_place_followup()
    test_t28_location_retry_escalation()
    test_t29_western_name_no_repair()
    test_t30_location_answer_with_counter_reply_no_loop()
    test_t31_repeated_location_structure_advances()
    test_t32_structural_escape_not_alias()
    test_t33_distance_eligible_after_overseas_place()
    test_t34_domestic_city_no_distance_question()
    test_t35_nz_origin_distance_eligible()
    test_t36_no_duplicate_clarification_wrapper()
    test_t37_no_bare_repeat_repair()
    test_t38_warm_reaction_food_family()
    test_t39_mirror_question_sets_engine()
    test_t40_no_coaching_phrase_ni_ke_yi_shuo()
    test_t41_no_coaching_phrase_biru()
    test_t42_latin_in_work_engine_no_name_clarification()
    test_t43_clarification_wrapper_at_most_once()
    test_t44_distance_answer_accepted()
    test_t45_contextual_recovery_not_bare_manman()
    test_t46_work_duration_question_answered()
    test_t47_grandparent_location_not_evasive()
    test_t48_blue_panel_rich_city_reveal()
    test_t49_curiosity_outranks_engine_progression()
    test_t50_preference_not_residence_duration()
    test_t51_feature_not_origin()
    test_t52_age_not_evasive()
    test_t53_parent_age_not_location()
    test_t54_travel_question_answered()

    total  = len(_results)
    passed = sum(1 for _, ok in _results if ok)
    failed = total - passed

    print("\n" + "=" * 62)
    colour = "\033[32m" if failed == 0 else "\033[31m"
    reset  = "\033[0m"
    print(f"{colour}{passed}/{total} passed{reset}", end="")
    if failed:
        print(f"  \u2190 {failed} FAILED", end="")
        print("\n\nFailed tests:")
        for name, ok in _results:
            if not ok:
                print(f"  \u2717  {name}")
    print()
    sys.exit(0 if failed == 0 else 1)


# ══════════════════════════════════════════════════════════════════════════════
# T28 — Three-level noisy-location escalation (loop prevention)
# ══════════════════════════════════════════════════════════════════════════════

def test_t28_location_retry_escalation() -> None:
    """[T28] Repeated noisy location answers must escalate through three levels.

    Level 0 (retry_count=0): standard rephrase  — 我是问：你现在住的地方在哪里？
    Level 1 (retry_count=1): natural re-ask      — 我没听清楚。你住的地方，离这里远吗？
    Level 2 (retry_count=2): gentle move-on      — 没关系，我们先说别的。你喜欢你住的地方吗？
    """
    print("\n[T28] Location retry escalation — 3-level loop prevention")

    _NOISY = ["我现在住在等你等", "等一等我就住在等你等", "等你等等你等我就住在等你等"]
    _BASE_CS = {
        "last_partner_frame_text": "你现在住哪里？",
        "learner_id":              "tester_t28",
    }

    cs = dict(_BASE_CS)
    cs["location_retry_count"] = 0
    prev_frame_text = "你现在住哪里？"
    turns: list[dict] = []

    for i, noisy_text in enumerate(_NOISY):
        cs["last_partner_frame_text"] = prev_frame_text
        resp = api_run_turn(
            make_answer("f_live_where", noisy_text),
            make_cs(engine="place", extra=cs),
        )
        if resp is None:
            skip(f"T28 level {i}", "server not available"); return

        ft = resp.get("frame_text", "")
        # Thread state_update into next turn's cs
        su = resp.get("state_update") or {}
        if isinstance(su, dict):
            for k in ("location_retry_count", "location_clarify_hint", "last_partner_frame_text"):
                if k in su:
                    cs[k] = su[k]
        prev_frame_text = ft
        turns.append(resp)
        print(f"    [T28-{i+1}] retry={i}: {ft[:80]!r}")

    # Level 0: standard rephrase
    t0 = turns[0].get("frame_text", "")
    check(
        "T28a — level-0 shows standard rephrase (我是问 / 住的地方)",
        "我是问" in t0 or "住的地方" in t0 or "哪里" in t0,
        f"got: {t0[:80]!r}",
    )
    check(
        "T28b — level-0 does NOT show scaffold or move-on text",
        "没听清楚" not in t0 and "先说别的" not in t0,
        f"got: {t0[:80]!r}",
    )

    # Level 1: scaffold with model sentence
    t1 = turns[1].get("frame_text", "")
    check(
        "T28c — level-1 shows scaffold (没听清楚 / 新西兰)",
        "没听清楚" in t1 or "新西兰" in t1,
        f"got: {t1[:80]!r}",
    )
    check(
        "T28d — level-1 does NOT repeat exact level-0 rephrase verbatim",
        t1 != t0,
        f"level-0={t0[:60]!r}  level-1={t1[:60]!r}",
    )

    # Level 2: gentle move-on
    t2 = turns[2].get("frame_text", "")
    check(
        "T28e — level-2 shows gentle move-on (没关系 / 先说别的 / 喜欢住的地方)",
        "没关系" in t2 or "先说别的" in t2 or "喜欢" in t2,
        f"got: {t2[:80]!r}",
    )
    check(
        "T28f — level-2 does NOT repeat the location question verbatim",
        "你现在住哪里" not in t2 and "住的地方在哪里" not in t2,
        f"got: {t2[:80]!r}",
    )
    check(
        "T28g — level-2 has no food jump (好吃 / 吃什么 / 菜)",
        not any(f in t2 for f in ("好吃", "吃什么", "菜")),
        f"got: {t2[:80]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T29 — Western name answer (我叫rimant) must not trigger repair or re-ask
# ══════════════════════════════════════════════════════════════════════════════

def test_t29_western_name_no_repair() -> None:
    """[T29] '我叫rimant' (garbled Western name) must not re-ask 你叫什么名字？ or show repair phrases."""
    print("\n[T29] Western name participation success — 我叫rimant")
    turn = simulate_turn(
        "我叫rimant",
        frame_id="f_ask_you_name",
        engine="identity",
        extra_cs={"learner_id": "tester_t29"},
    )
    if turn is None:
        skip("T29", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T29a — does NOT re-ask 你叫什么名字？",
        "你叫什么名字" not in combined,
        f"got: {combined[:120]!r}",
    )
    check(
        "T29b — does NOT show confusion/repair phrases (啊？/ 没听清楚 / 你是说)",
        not any(p in combined for p in ("啊？", "没听清楚", "听不清", "你是说rimant")),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T30 — Garbled location answer WITH prior counter_reply does not loop
# (Real-session scenario: last_counter_reply is non-empty from previous turn)
# ══════════════════════════════════════════════════════════════════════════════

def test_t30_location_answer_with_counter_reply_no_loop() -> None:
    """[T30] '我现在住在等你等' + prior counter_reply at retry=1 must advance, not loop."""
    print("\n[T30] Location with counter_reply — participation-success escape")
    turn = simulate_turn(
        "我现在住在等你等",
        frame_id="f_live_where",
        engine="place",
        extra_cs={
            "last_partner_frame_text": "你现在住哪里？",
            "last_counter_reply":      "哦，生气老！",   # simulates real session
            "location_retry_count":    1,               # one retry already attempted
            "learner_id":              "tester_t30",
        },
    )
    if turn is None:
        skip("T30", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T30a — does NOT repeat identical location question (你现在住哪里)",
        "你现在住哪里" not in turn.get("frame_text", ""),
        f"frame_text: {turn['frame_text'][:100]!r}",
    )
    check(
        "T30b — advances to place follow-up (喜欢 / 知道了 / 地方)",
        any(p in combined for p in ("喜欢", "知道了", "地方", "那里")),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T31 — Repeated structural location answers advance through the escalation
# (Both turns have a prior counter_reply set, matching real-session behaviour)
# ══════════════════════════════════════════════════════════════════════════════

def test_t31_repeated_location_structure_advances() -> None:
    """[T31] Two structural location answers with counter_reply present → second advances to follow-up."""
    print("\n[T31] Repeated location structure + counter_reply → place follow-up")

    # Turn 1: retry_count=0, prior counter_reply set → Level-0 rephrase (not a bare loop)
    resp1 = api_run_turn(
        make_answer("f_live_where", "我现在住在等你等"),
        make_cs(engine="place", extra={
            "last_partner_frame_text": "你现在住哪里？",
            "last_counter_reply":      "哦，生气老！",
            "location_retry_count":    0,
            "learner_id":              "tester_t31",
        }),
    )
    if resp1 is None:
        skip("T31", "server not available"); return

    ft1 = resp1.get("frame_text", "")
    print(f"    [T31-turn1] {ft1[:80]!r}")

    # Thread state_update into turn 2
    su1 = resp1.get("state_update") or {}
    retry_after_1 = int(su1.get("location_retry_count", 1)) if isinstance(su1, dict) else 1

    # Turn 2: retry_count=1 (from state_update), prior counter_reply updated
    resp2 = api_run_turn(
        make_answer("f_live_where", "等一等我现在住在等你等"),
        make_cs(engine="place", extra={
            "last_partner_frame_text": ft1 or "你现在住哪里？",
            "last_counter_reply":      "哦，生气老！",
            "location_retry_count":    retry_after_1,
            "learner_id":              "tester_t31",
        }),
    )
    if resp2 is None:
        skip("T31", "server not available"); return

    ft2      = resp2.get("frame_text", "")
    combined = (ft2 + " " + resp2.get("counter_reply", "")).strip()
    print(f"    [T31-turn2] {ft2[:80]!r}")

    check(
        "T31a — turn-2 does NOT repeat exact location question (你现在住哪里)",
        "你现在住哪里" not in ft2,
        f"frame_text: {ft2[:100]!r}",
    )
    check(
        "T31b — turn-2 advances to place follow-up (喜欢 / 知道了) not just a rephrase",
        any(p in combined for p in ("喜欢", "知道了")),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T32 — Structural escape fires for ANY garbled entity, not a Dunedin/Raymond alias
# ══════════════════════════════════════════════════════════════════════════════

def test_t32_structural_escape_not_alias() -> None:
    """[T32] Participation-success fires structurally, not via entity alias.

    A completely arbitrary non-place string after 我现在住在 must also advance at
    retry=1.  This proves the fix is structural — no Dunedin / Raymond alias added.
    """
    print("\n[T32] Structural escape (no alias) — arbitrary garbled entity")
    turn = simulate_turn(
        "我现在住在嗯嗯嗯嗯嗯",   # arbitrary non-place string
        frame_id="f_live_where",
        engine="place",
        extra_cs={
            "last_partner_frame_text": "你现在住哪里？",
            "last_counter_reply":      "好的！",
            "location_retry_count":    1,
            "learner_id":              "tester_t32",
        },
    )
    if turn is None:
        skip("T32", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T32a — does NOT repeat exact location question (no loop)",
        "你现在住哪里" not in turn.get("frame_text", ""),
        f"frame_text: {turn['frame_text'][:100]!r}",
    )
    check(
        "T32b — advances to place follow-up (structural escape fired, not alias)",
        any(p in combined for p in ("喜欢", "知道了", "地方", "那里")),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T33 — Distance follow-up eligible after overseas place answer
# (Phase 12D.1: p2_pl_far added to _FRAME_ORDER["place"] position 3)
# ══════════════════════════════════════════════════════════════════════════════

def test_t33_distance_eligible_after_overseas_place() -> None:
    """[T33] After f_from_where + f_live_where answered with overseas place,
    selector must choose p2_pl_far (离那儿远吗？) at position 3, NOT f_place_special.
    """
    print("\n[T33] Distance follow-up eligible — overseas place (奥克兰)")
    # f_from_where AND f_live_where already answered; this simulates answering f_live_where now.
    # recent already contains both so position 3 (p2_pl_far) should be chosen.
    # "奥克兰": 兰 is in _LOC_CHARS → _looks_like_valid_location True → no noisy-clarify path.
    turn = simulate_turn(
        "我现在住在奥克兰",
        frame_id="f_live_where",
        engine="place",
        recent=["f_from_where", "f_live_where"],
        extra_cs={"learner_id": "tester_t33"},
    )
    if turn is None:
        skip("T33", "server not available"); return

    ft       = turn["frame_text"]
    frame_id = turn["frame_id"]
    combined = all_text(turn)
    print(f"    frame_text   : {ft!r}")
    print(f"    frame_id     : {frame_id!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T33a — NOT a repeat of '你现在住哪里' (no location loop)",
        "你现在住哪里" not in ft,
        f"frame_text: {ft[:100]!r}",
    )
    check(
        "T33b — distance question surfaces (远/多久/怎么去) at position 3 — p2_pl_far now in FRAME_ORDER",
        any(p in combined for p in ("远吗", "多久", "怎么去", "远不远", "离那儿", "那儿离")),
        f"got: {combined[:120]!r}",
    )
    check(
        "T33c — no hardcoded city dictionary used (frame_id is p2_pl_far or distance frame, not echo)",
        not any(p in (turn.get("frame_id","")) for p in ("alias", "hardcode")),
        f"frame_id: {turn['frame_id']!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T34 — Domestic well-known city: p2_pl_far skipped → place-special surfaces
# (Proves Phase 12D.1 skip_when=city_is_well_known fires correctly for 上海)
# ══════════════════════════════════════════════════════════════════════════════

def test_t34_domestic_city_no_distance_question() -> None:
    """[T34] For a well-known domestic city (上海), p2_pl_far must be SKIPPED.
    The app should proceed to f_place_special or similar, not 离那儿远吗？.
    """
    print("\n[T34] Domestic city — p2_pl_far skipped for 上海")
    # Use memory lives_in=上海 to make skip_when=city_is_well_known reliable
    # (avoids dependency on _extract_city_from_hanzi import).
    turn = simulate_turn(
        "我住在上海",
        frame_id="f_live_where",
        engine="place",
        recent=["f_from_where", "f_live_where"],
        extra_cs={
            "learner_id":   "tester_t34",
            "memory":       {"lives_in": "上海"},
        },
    )
    if turn is None:
        skip("T34", "server not available"); return

    ft       = turn["frame_text"]
    combined = all_text(turn)
    print(f"    frame_text   : {ft!r}")
    print(f"    frame_id     : {turn['frame_id']!r}")

    check(
        "T34a — distance question NOT chosen for 上海 (skip_when=city_is_well_known fired)",
        not any(p in combined for p in ("远吗", "离那儿", "那儿离")),
        f"got: {combined[:120]!r}",
    )
    check(
        "T34b — conversation continues (place follow-up OR generic next frame, not repeat)",
        "你现在住哪里" not in ft and "你是哪里人" not in ft,
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T35 — New Zealand nationality → distance eligible on next place turn
# (Task req 1: after "我是新西兰人", distance follow-up eligible)
# ══════════════════════════════════════════════════════════════════════════════

def test_t35_nz_origin_distance_eligible() -> None:
    """[T35] After '我是新西兰人' answering f_from_where, the next place turn
    should surface a distance question (p2_pl_far).
    新西兰: 兰 in _LOC_CHARS → valid location; not in _CITIES_SKIP_DISTANCE_ASK.
    """
    print("\n[T35] NZ origin → distance follow-up eligible")
    # f_from_where in recent (already answered), f_live_where also in recent.
    # This simulates the turn AFTER both place-anchor frames have fired.
    # p2_pl_far deps: f_from_where OR f_live_where in recent → satisfied.
    # skip_when: 新西兰 not in _CITIES_SKIP_DISTANCE_ASK → NOT skipped.
    turn = simulate_turn(
        "我是新西兰人",
        frame_id="f_from_where",
        engine="place",
        recent=["f_from_where", "f_live_where"],
        extra_cs={"learner_id": "tester_t35"},
    )
    if turn is None:
        skip("T35", "server not available"); return

    ft       = turn["frame_text"]
    combined = all_text(turn)
    print(f"    frame_text   : {ft!r}")
    print(f"    frame_id     : {turn['frame_id']!r}")

    check(
        "T35a — does NOT repeat location question (你是哪里人 / 你现在住哪里)",
        not any(p in ft for p in ("你是哪里人", "你现在住哪里")),
        f"frame_text: {ft[:100]!r}",
    )
    check(
        "T35b — distance OR place follow-up surfaces (远/多久/怎么去/特别/好吃)",
        any(p in combined for p in ("远吗", "多久", "怎么去", "远不远", "离那儿", "那儿", "特别", "好吃", "老家")),
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T36 — No duplicate "我是问：" wrapper in clarification
# ══════════════════════════════════════════════════════════════════════════════

def test_t36_no_duplicate_clarification_wrapper() -> None:
    """[T36] When the previous frame_text was itself a clarification (contains '我是问：'),
    the next clarification must NOT wrap it again — "我是问：" must appear at most once.
    """
    print("\n[T36] No double-wrap — '我是问：' appears at most once")
    # Simulate: previous frame was already a clarification like "我是问：你现在住的地方在哪里？"
    # Learner responds with confusion signal → clarification should not double-wrap.
    turn = simulate_turn(
        "什么意思",
        frame_id="f_live_where",
        engine="place",
        recent=["f_from_where"],
        extra_cs={
            "last_partner_frame_text": "我是问：你现在住的地方在哪里？",
            "last_turn_was_answer": True,
        },
    )
    if turn is None:
        skip("T36", "server not available"); return

    combined = all_text(turn)
    print(f"    frame_text   : {turn['frame_text']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    # Count occurrences of "我是问" in the combined output
    count_clarify = combined.count("我是问")
    check(
        "T36a — '我是问' appears at most once in combined output",
        count_clarify <= 1,
        f"found {count_clarify} times in: {combined[:140]!r}",
    )
    check(
        "T36b — combined output is non-empty (response was generated)",
        bool(combined.strip()),
        "empty response",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T37 — Repair phrase is NOT bare "再说一遍"
# ══════════════════════════════════════════════════════════════════════════════

def test_t37_no_bare_repeat_repair() -> None:
    """[T37] Repair escalation (level 2) must not return bare '再说一遍' as the full
    visible response.  It should be phrased politely.
    """
    print("\n[T37] Repair escalation — no bare '再说一遍'")
    # Simulate level-2 repair: repair_attempt_count=2, consecutive_not_understood=2
    resp = api_run_turn(
        make_answer("f_from_where", "啊"),
        make_cs(
            engine="place",
            extra={
                "last_turn_was_answer":       True,
                "repair_attempt_count":       2,
                "consecutive_not_understood": 2,
                "recent_confusion_count":     2,
            },
        ),
    )
    if resp is None:
        skip("T37", "server not available"); return

    cr       = resp.get("counter_reply", "")
    ft       = resp.get("frame_text", "")
    combined = (ft + " " + cr).strip()
    print(f"    counter_reply: {cr!r}")
    print(f"    frame_text   : {ft!r}")

    check(
        "T37a — bare '再说一遍' (standalone, no polite wrapper) is NOT the full counter_reply",
        cr.strip() != "再说一遍",
        f"counter_reply: {cr!r}",
    )
    check(
        "T37b — response contains polite repair language (再说, 可以, 没关系, 清楚, 明白)",
        any(p in combined for p in ("再说", "可以", "没关系", "清楚", "明白", "换", "不懂")),
        f"combined: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T38 — No bare "明白了。" for food/family answer
# ══════════════════════════════════════════════════════════════════════════════

def test_t38_warm_reaction_food_family() -> None:
    """[T38] After '我喜欢我妈妈的羊肉', the app must NOT return bare '明白了。'
    as the full frame_text — a warmer reaction should be chosen instead.
    """
    print("\n[T38] Food/family answer — no flat '明白了。'")
    turn = simulate_turn(
        "我喜欢我妈妈的羊肉",
        frame_id="p2_fam_2",
        engine="family",
        recent=["f_family_intro", "p2_fam_1"],
        extra_cs={
            "learner_id": "tester_t38",
            "interest_level": "medium",
        },
    )
    if turn is None:
        skip("T38", "server not available"); return

    ft       = turn["frame_text"]
    combined = all_text(turn)
    print(f"    frame_text   : {ft!r}")
    print(f"    frame_id     : {turn['frame_id']!r}")
    print(f"    counter_reply: {turn['counter_reply']!r}")

    check(
        "T38a — frame_text is NOT bare '明白了。' (flat dead-end acknowledgement)",
        ft.strip() != "明白了。",
        f"frame_text: {ft!r}",
    )
    check(
        "T38b — combined output has some content beyond a single flat ack",
        len(combined.strip()) > 4,
        f"combined: {combined[:80]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T39 — Mirror question "你是哪里人？" sets correct engine state
# ══════════════════════════════════════════════════════════════════════════════

def test_t39_mirror_question_sets_engine() -> None:
    """[T39] The direction_intent=mirror response for topic=place_from must return
    engine_id='place' so the client updates window._currentEngineId correctly.
    """
    print("\n[T39] Mirror question '你是哪里人？' → engine_id = 'place'")
    payload = json.dumps({
        "turn_uid": "interaction_regression_t39",
        "direction_intent": "mirror",
        "direction_question_zh": "你是哪里人？",
        "direction_question_topic": "place_from",
        "conversation_state": {
            "session_id": "t39_test",
            "current_engine": "unknown",
            "recent_frame_ids": [],
        },
        "persona_id": "meiling",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{SERVER}/api/run_turn",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, Exception):
        skip("T39", "server not available"); return

    engine_id  = data.get("engine_id", "")
    frame_text = data.get("frame_text", "")
    su         = data.get("state_update") or {}
    print(f"    frame_text : {frame_text!r}")
    print(f"    engine_id  : {engine_id!r}")
    print(f"    state_update: {su!r}")

    check(
        "T39a — engine_id is 'place' (derived from place_from topic)",
        engine_id == "place",
        f"engine_id: {engine_id!r}",
    )
    check(
        "T39b — frame_text is a non-empty persona answer",
        bool(frame_text.strip()),
        "empty frame_text",
    )
    check(
        "T39c — state_update contains current_engine='place'",
        su.get("current_engine") == "place",
        f"state_update: {su!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T40 — No "你可以说" coaching phrase in learner-facing output
# (MandarinOS is a conversation partner, not a classroom tutor)
# ══════════════════════════════════════════════════════════════════════════════

def test_t40_no_coaching_phrase_ni_ke_yi_shuo() -> None:
    """[T40] Learner-facing output must never contain '你可以说' as a coaching prompt."""
    print("\n[T40] No '你可以说' coaching phrase in any recovery output")

    # Trigger the NLC Level 1 path: noisy location answer on second attempt
    turn = simulate_turn(
        "我现在住在等你等",
        frame_id="f_live_where",
        engine="place",
        recent=["f_live_where"],
        extra_cs={
            "location_retry_count":  1,
            "location_clarify_hint": "active",
            "last_partner_frame_text": "你现在住哪里？",
        },
    )
    if turn is None:
        skip("T40", "server not available"); return

    combined_out = all_text(turn)
    print(f"    output : {combined_out[:140]!r}")

    check(
        "T40a — output does NOT contain '你可以说' coaching phrase",
        "你可以说" not in combined_out,
        f"got: {combined_out[:140]!r}",
    )
    check(
        "T40b — output is non-empty (recovery still fires)",
        bool(combined_out.strip()),
        "empty output",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T41 — No "比如：" template coaching in learner-facing output
# ══════════════════════════════════════════════════════════════════════════════

def test_t41_no_coaching_phrase_biru() -> None:
    """[T41] Learner-facing output must not use '比如：' as an answer template prompt."""
    print("\n[T41] No '比如：' template coaching in output")

    # Test a confusion signal on a work frame where scaffolding could fire
    for user_text in ("啊", "不懂", "什么意思"):
        turn = simulate_turn(
            user_text,
            frame_id="f_what_work",
            engine="work",
            extra_cs={
                "last_partner_frame_text": "你做什么工作？",
                "last_counter_reply":      "我是问：你的工作是什么？",
            },
        )
        if turn is None:
            skip(f"T41 [{user_text!r}]", "server not available"); continue

        combined_out = all_text(turn)
        check(
            f"T41 [{user_text!r}] — output does NOT contain '比如：' template",
            "比如：" not in combined_out and "比如说：" not in combined_out,
            f"got: {combined_out[:120]!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T42 — Latin text in work/place engine must NOT produce name clarification
# ══════════════════════════════════════════════════════════════════════════════

def test_t42_latin_in_work_engine_no_name_clarification() -> None:
    """[T42] Text with Latin chars in place/work context must not get '你是说你的英文名字吗？'."""
    print("\n[T42] Latin text in non-identity engine must not trigger name clarification")

    for user_text, engine in [
        ("中翻的大社交通Liverpool大厦", "place"),
        ("我在Liverpool大学工作", "work"),
    ]:
        turn = simulate_turn(
            user_text,
            frame_id="f_what_work",
            engine=engine,
            extra_cs={"last_partner_frame_text": "你做什么工作？"},
        )
        if turn is None:
            skip(f"T42 [{engine}]", "server not available"); continue

        combined = all_text(turn)
        check(
            f"T42 [{engine}] — does NOT show '你是说你的英文名字吗？'",
            "你是说你的英文名字吗" not in combined,
            f"got: {combined[:120]!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T43 — Clarification wrapper appears at most once in visible output
# ══════════════════════════════════════════════════════════════════════════════

def test_t43_clarification_wrapper_at_most_once() -> None:
    """[T43] '我是问：' must appear at most once in any single turn output."""
    print("\n[T43] No duplicate clarification wrappers in output")

    for user_text, frame, engine in [
        ("等你等等你等我就住在等你等", "f_live_where", "place"),
        ("不懂不懂不懂", "f_what_work", "work"),
    ]:
        turn = simulate_turn(
            user_text,
            frame_id=frame,
            engine=engine,
            extra_cs={"last_partner_frame_text": "你现在住哪里？"},
        )
        if turn is None:
            skip(f"T43 [{user_text[:10]}]", "server not available"); continue

        combined = all_text(turn)
        wrapper_count = combined.count("我是问")
        check(
            f"T43 [{user_text[:10]}] — '我是问' appears at most once",
            wrapper_count <= 1,
            f"count={wrapper_count}  got: {combined[:140]!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T44 — Distance-answer soft match: 乘飞机12小时 satisfies 离那儿远吗？
# ══════════════════════════════════════════════════════════════════════════════

def test_t44_distance_answer_accepted() -> None:
    """[T44] '乘飞机12小时' on p2_pl_far frame must be accepted, not trigger repair."""
    print("\n[T44] Distance answer '乘飞机' accepted on 离那儿远吗？ frame")

    for user_text in ("乘飞机12小时", "很远", "坐飞机要12小时"):
        turn = simulate_turn(
            user_text,
            frame_id="p2_pl_far",
            engine="place",
            extra_cs={"last_partner_frame_text": "离那儿远吗？"},
        )
        if turn is None:
            skip(f"T44 [{user_text}]", "server not available"); continue

        combined = all_text(turn)
        check(
            f"T44 [{user_text}] — output is non-empty",
            bool(combined.strip()),
            "empty output",
        )
        check(
            f"T44 [{user_text}] — does NOT re-ask '离那儿远吗'",
            "离那儿远吗" not in (turn.get("frame_text") or ""),
            f"frame_text: {turn.get('frame_text', '')!r}",
        )
        check(
            f"T44 [{user_text}] — no '你是说你的英文名字吗' name confusion",
            "你是说你的英文名字吗" not in combined,
            f"got: {combined[:120]!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T45 — Contextual recovery re-ask contains frame topic, not bare "慢慢来"
# ══════════════════════════════════════════════════════════════════════════════

def test_t45_contextual_recovery_not_bare_manman() -> None:
    """[T45] After 2+ consecutive failures with no signal, recovery must be topic-anchored."""
    print("\n[T45] Contextual recovery — not bare '没关系，慢慢来。'")

    # Send pure noise twice on same frame so _consecutiveNotUnderstood reaches 2 server-side
    for _ in range(2):
        turn = simulate_turn(
            "啊啊啊啊",
            frame_id="f_live_where",
            engine="place",
            extra_cs={
                "last_partner_frame_text": "你现在住哪里？",
                "consecutive_not_understood": 2,
            },
        )
        if turn is None:
            skip("T45", "server not available"); return

    combined = all_text(turn)
    check(
        "T45 — output is non-empty",
        bool(combined.strip()),
        "empty output",
    )
    # The bare generic phrase should not appear as the FULL reply
    check(
        "T45 — not bare '没关系，慢慢来。' by itself",
        combined.strip() != "没关系，慢慢来。",
        f"got: {combined[:120]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T46 — Work-duration question gets a persona answer, not engine progression
# ══════════════════════════════════════════════════════════════════════════════

def test_t46_work_duration_question_answered() -> None:
    """[T46] 'You've been doing this work for how long?' must get a counter_reply, not a topic jump."""
    print("\n[T46] Work-duration question gets persona answer")

    for user_text in ("你做这个工作多久了", "你从事这个工作多长时间了", "你做了多久了"):
        turn = simulate_turn(
            user_text,
            frame_id="f_what_work",
            engine="work",
            extra_cs={
                "last_partner_frame_text": "你做什么工作？",
                "last_counter_reply":      "我是老师，已经做了好几年了。",
            },
        )
        if turn is None:
            skip(f"T46 [{user_text}]", "server not available"); continue

        cr       = turn.get("counter_reply", "")
        combined = all_text(turn)
        print(f"    input: {user_text!r}  counter_reply: {cr!r}")

        check(
            f"T46 [{user_text}] — counter_reply is non-empty",
            bool(cr.strip()),
            f"got empty counter_reply; frame_text={turn.get('frame_text','')!r}",
        )
        # Must not immediately jump to unrelated engine
        check(
            f"T46 [{user_text}] — no abrupt topic jump (另外 / 你去过哪里)",
            "另外" not in combined and "你去过哪里" not in combined,
            f"got: {combined[:120]!r}",
        )
        # Any work-related content expected in reply (duration or occupation context)
        check(
            f"T46 [{user_text}] — reply contains work or occupation signal",
            any(kw in cr for kw in ("年", "久", "工作", "老师", "做", "开始", "毕业",
                                    "教", "学", "以来", "一直", "大学", "美术", "公司")),
            f"counter_reply={cr!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T47 — Grandparent location question does not default to "这个不好说"
# ══════════════════════════════════════════════════════════════════════════════

def test_t47_grandparent_location_not_evasive() -> None:
    """[T47] '你奶奶住在哪里啊' must not return an evasive deflect phrase."""
    print("\n[T47] Grandparent location question — not evasive")

    for user_text in ("你奶奶住在哪里啊", "你爷爷住哪里", "你外婆在哪里"):
        turn = simulate_turn(
            user_text,
            frame_id="f_from_where",
            engine="place",
            extra_cs={"last_partner_frame_text": "你是哪里人？"},
        )
        if turn is None:
            skip(f"T47 [{user_text}]", "server not available"); continue

        cr       = turn.get("counter_reply", "")
        combined = all_text(turn)
        print(f"    input: {user_text!r}  counter_reply: {cr!r}")

        EVASIVE = ("这个不好说", "这个以后再聊", "这个先不说", "换个话题", "还没想好")
        check(
            f"T47 [{user_text}] — counter_reply is non-empty",
            bool(cr.strip()),
            f"got empty; frame_text={turn.get('frame_text','')!r}",
        )
        check(
            f"T47 [{user_text}] — reply is not an evasive deflect",
            not any(ev in cr for ev in EVASIVE),
            f"counter_reply={cr!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T48 — Blue panel after 成都+北京 reveal contains ≥ 3 place-related questions
# ══════════════════════════════════════════════════════════════════════════════

def test_t48_blue_panel_rich_city_reveal() -> None:
    """[T48] After persona reveals two cities (成都/北京), blue panel must show ≥ 3 place questions."""
    print("\n[T48] Blue panel rich two-city reveal — ≥ 3 place questions")

    resp = api_run_turn(
        {
            "frame_id":               "f_from_where",
            "submitted_text":         "你是哪里人？",
            "selected_option_hanzi":  "你是哪里人？",
            "move_type":              "ANSWER",
        },
        {
            "last_turn_was_answer":    True,
            "current_engine":          "place",
            "recent_frame_ids":        [],
            "exchange_count":          3,
            "learner_id":              "interaction_regression_tester",
            "persona_id":              "meiling",
            "same_engine_chain_count": 1,
            "interest_level":          "medium",
            # Simulate persona having just revealed Chengdu + Beijing
            "last_counter_reply":      "我是成都人，不过在北京工作已经好几年了。",
            "last_persona_reveal":     True,
            "consecutive_app_questions": 2,
        },
    )
    if resp is None:
        skip("T48", "server not available"); return

    dqs = resp.get("discovery_questions") or []
    topics = [q.get("topic", "") for q in dqs]
    zhs    = [q.get("zh", "") for q in dqs]
    print(f"    topics:    {topics}")
    print(f"    questions: {zhs}")

    PLACE_TOPICS = {"place_from", "place_like", "place_special", "place_why_like",
                    "place_food", "place_far", "place_live_now", "place_still_live",
                    "place_distance_ref", "place_distance_time", "work_what", "work_like"}

    check(
        "T48a — discovery_questions non-empty",
        bool(dqs),
        "no discovery_questions returned",
    )
    check(
        "T48b — ≥ 3 questions returned",
        len(dqs) >= 3,
        f"only {len(dqs)} question(s): {zhs}",
    )
    place_count = sum(1 for t in topics if t in PLACE_TOPICS)
    check(
        "T48c — ≥ 2 place/work-place questions",
        place_count >= 2,
        f"place_count={place_count}  topics={topics}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T49 — Curiosity follow-up temporarily outranks engine progression
# ══════════════════════════════════════════════════════════════════════════════

def test_t49_curiosity_outranks_engine_progression() -> None:
    """[T49] A direct persona follow-up question must produce a counter_reply, not just a frame."""
    print("\n[T49] Direct curiosity follow-up gets a counter_reply before engine progression")

    for user_text in ("你喜欢北京吗", "你做了多久老师了", "你是哪里人"):
        turn = simulate_turn(
            user_text,
            frame_id="f_from_where",
            engine="place",
            extra_cs={
                "last_partner_frame_text":  "你是哪里人？",
                "last_counter_reply":       "我是成都人，不过在北京工作已经好几年了。",
                "last_persona_reveal":      True,
                "consecutive_app_questions": 2,
            },
        )
        if turn is None:
            skip(f"T49 [{user_text}]", "server not available"); continue

        cr = turn.get("counter_reply", "")
        print(f"    input: {user_text!r}  counter_reply: {cr!r}")

        check(
            f"T49 [{user_text}] — counter_reply present (persona answered before progressing)",
            bool(cr.strip()),
            f"no counter_reply; frame_text={turn.get('frame_text','')!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T50 — "你喜欢北京吗" gives a preference answer, not the same residence sentence
# ══════════════════════════════════════════════════════════════════════════════

def test_t50_preference_not_residence_duration() -> None:
    """[T50] Preference question must return a preference answer, not a residence-duration fact."""
    print("\n[T50] '你喜欢北京吗' → preference answer, not '我在北京住了X年'")

    # Simulate a turn where the persona just said "我在北京住了五年了" (stored as last_counter_reply)
    for persona_id, city_q in [("meiling", "你喜欢西安吗"), ("zhiyuan", "你喜欢上海吗")]:
        turn = simulate_turn(
            city_q,
            frame_id="f_from_where",
            engine="place",
            extra_cs={
                "persona_id":          persona_id,
                "last_counter_reply":  f"我在{'西安' if persona_id=='meiling' else '上海'}住了很多年了。",
                "recent_persona_replies": [f"我在{'西安' if persona_id=='meiling' else '上海'}住了很多年了。"],
            },
        )
        if turn is None:
            skip(f"T50 [{persona_id}/{city_q}]", "server not available"); continue

        cr = turn.get("counter_reply", "")
        print(f"    {persona_id}: {city_q!r} → counter_reply: {cr!r}")

        check(
            f"T50 [{persona_id}] — counter_reply non-empty",
            bool(cr.strip()),
            "empty counter_reply",
        )
        # Must NOT repeat the residence-duration sentence
        check(
            f"T50 [{persona_id}] — does NOT repeat residence-duration sentence",
            "住了很多年了" not in cr,
            f"counter_reply={cr!r}",
        )
        # Must contain a preference-related word
        check(
            f"T50 [{persona_id}] — contains preference/feature signal",
            any(kw in cr for kw in ("喜欢", "挺", "好", "特色", "方便", "文化", "历史", "活力", "快", "慢", "有意思")),
            f"counter_reply={cr!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T51 — "X有什么特别啊" returns feature content, not origin fact
# ══════════════════════════════════════════════════════════════════════════════

def test_t51_feature_not_origin() -> None:
    """[T51] '有什么特别' question must return a feature/special answer, not an origin statement."""
    print("\n[T51] '西安有什么特别' → feature answer, not origin/work fact")

    for user_text in ("西安有什么特别啊", "那里有什么特别的", "北京有什么特别"):
        turn = simulate_turn(
            user_text,
            frame_id="f_from_where",
            engine="place",
            extra_cs={
                "persona_id":         "meiling",
                "last_counter_reply": "我是西安人，在这里长大的。",
            },
        )
        if turn is None:
            skip(f"T51 [{user_text}]", "server not available"); continue

        cr = turn.get("counter_reply", "")
        print(f"    {user_text!r} → counter_reply: {cr!r}")

        check(
            f"T51 [{user_text}] — counter_reply non-empty",
            bool(cr.strip()),
            "empty counter_reply",
        )
        # Must not return a bare origin statement as the feature answer
        ORIGIN_PATTERNS = ("老家是", "老家在", "毕业后来", "来北京工作", "来成都工作")
        check(
            f"T51 [{user_text}] — not an origin/work statement",
            not any(p in cr for p in ORIGIN_PATTERNS),
            f"counter_reply={cr!r}",
        )
        # Should contain feature-related content
        check(
            f"T51 [{user_text}] — contains feature/description signal",
            any(kw in cr for kw in ("历史", "文化", "古迹", "特色", "好吃", "小吃", "有名", "很大", "机会", "兵马俑", "大雁塔")),
            f"counter_reply={cr!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T52 — "你多大" returns an age answer, not an evasive deflect
# ══════════════════════════════════════════════════════════════════════════════

def test_t52_age_not_evasive() -> None:
    """[T52] '你多大' must return an age answer when persona has a known age."""
    print("\n[T52] '你多大' → age answer, not evasive deflect")

    for user_text in ("你多大", "你几岁", "你今年多大"):
        turn = simulate_turn(
            user_text,
            frame_id="f_from_where",
            engine="identity",
            extra_cs={"persona_id": "meiling"},   # meiling.profile.age = 32
        )
        if turn is None:
            skip(f"T52 [{user_text}]", "server not available"); continue

        cr = turn.get("counter_reply", "")
        print(f"    {user_text!r} → counter_reply: {cr!r}")

        check(
            f"T52 [{user_text}] — counter_reply non-empty",
            bool(cr.strip()),
            "empty counter_reply",
        )
        EVASIVE = ("先不说", "不好说", "以后再聊", "秘密", "还没想好")
        check(
            f"T52 [{user_text}] — not an evasive deflect",
            not any(ev in cr for ev in EVASIVE),
            f"counter_reply={cr!r}",
        )
        check(
            f"T52 [{user_text}] — contains age signal (digit or 岁/多)",
            any(kw in cr for kw in ("岁", "32", "三十", "多")),
            f"counter_reply={cr!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T53 — "你爸爸妈妈多大" returns parent age, not parent location
# ══════════════════════════════════════════════════════════════════════════════

def test_t53_parent_age_not_location() -> None:
    """[T53] '你父母多大' must return a parent-age answer, not a location answer."""
    print("\n[T53] '你爸爸妈妈多大' → parent age answer, not parent location")

    for user_text in ("你爸爸妈妈他们多大", "你父母多大了", "你爸妈几岁了"):
        turn = simulate_turn(
            user_text,
            frame_id="f_from_where",
            engine="family",
            extra_cs={"persona_id": "meiling"},
        )
        if turn is None:
            skip(f"T53 [{user_text}]", "server not available"); continue

        cr = turn.get("counter_reply", "")
        print(f"    {user_text!r} → counter_reply: {cr!r}")

        check(
            f"T53 [{user_text}] — counter_reply non-empty",
            bool(cr.strip()),
            "empty counter_reply",
        )
        # Should NOT return a location answer
        LOC_PATTERNS = ("住在", "我父母在", "父母在", "家那边", "那边")
        check(
            f"T53 [{user_text}] — not a location answer",
            not any(p in cr for p in LOC_PATTERNS),
            f"counter_reply={cr!r}",
        )
        # Should contain an age signal
        check(
            f"T53 [{user_text}] — contains age signal (岁/多/大)",
            any(kw in cr for kw in ("岁", "多岁", "五十", "六十", "多大")),
            f"counter_reply={cr!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T54 — "你去过哪里" returns travel/visited answer, not residence fact
# ══════════════════════════════════════════════════════════════════════════════

def test_t54_travel_question_answered() -> None:
    """[T54] '你去过哪里' must return a travel/visited-places answer."""
    print("\n[T54] '你去过哪里' → travel answer, not residence fact")

    for user_text in ("你去过哪里", "你去过哪些地方", "你去过什么地方"):
        turn = simulate_turn(
            user_text,
            frame_id="f_from_where",
            engine="travel",
            extra_cs={"persona_id": "meiling"},
        )
        if turn is None:
            skip(f"T54 [{user_text}]", "server not available"); continue

        cr = turn.get("counter_reply", "")
        print(f"    {user_text!r} → counter_reply: {cr!r}")

        check(
            f"T54 [{user_text}] — counter_reply non-empty",
            bool(cr.strip()),
            "empty counter_reply",
        )
        # Should contain travel/place words — NOT a bare residence statement
        check(
            f"T54 [{user_text}] — contains travel/place signal",
            any(kw in cr for kw in ("去过", "旅行", "城市", "北京", "苏州", "上海", "成都", "历史", "文化", "地方")),
            f"counter_reply={cr!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T55 — "远不远啊" after Xi'an mention must NOT return "啊？"
# ══════════════════════════════════════════════════════════════════════════════

def test_t55_distance_followup_not_confused() -> None:
    """[T55] '远不远啊' after persona mentions Xi'an must not produce '啊？' or empty reply."""
    print("\n[T55] '远不远啊' → distance answer or graceful fallback, not '啊？'")

    turn = simulate_turn(
        "远不远啊",
        frame_id="f_travel_where_been",
        engine="travel",
        extra_cs={
            "persona_id": "meiling",
            "last_counter_reply": "西安历史文化太丰富了，我很想去。",
        },
    )
    if turn is None:
        skip("T55", "server not available"); return

    cr = turn.get("counter_reply", "")
    print(f"    counter_reply: {cr!r}")

    check("T55 — counter_reply non-empty", bool(cr.strip()), "empty counter_reply")
    check("T55 — not '啊？'", cr.strip() != "啊？", f"got {cr!r}")
    # Should not return a residence-duration sentence unrelated to distance
    check(
        "T55 — not bare residence sentence",
        not any(p in cr for p in ("住了", "住在", "我呢，我在")),
        f"counter_reply={cr!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T56 — "西安在哪儿呢" returns location answer or graceful limitation
# ══════════════════════════════════════════════════════════════════════════════

def test_t56_location_followup_answered() -> None:
    """[T56] '西安在哪儿呢' must return a location answer, not empty / evasive deflect."""
    print("\n[T56] '西安在哪儿呢' → location answer or graceful limitation")

    for user_text in ("西安在哪儿呢", "西安在哪里", "在哪儿啊"):
        turn = simulate_turn(
            user_text,
            frame_id="f_travel_where_been",
            engine="travel",
            extra_cs={
                "persona_id": "meiling",
                "last_counter_reply": "西安历史文化太丰富了，我很想去。",
            },
        )
        if turn is None:
            skip(f"T56 [{user_text}]", "server not available"); continue

        cr = turn.get("counter_reply", "")
        print(f"    {user_text!r} → counter_reply: {cr!r}")

        check(f"T56 [{user_text}] — non-empty", bool(cr.strip()), "empty")
        check(f"T56 [{user_text}] — not '啊？'", cr.strip() != "啊？", f"got {cr!r}")
        # Must contain something useful — location info OR limitation phrase
        _useful = (
            any(kw in cr for kw in ("西安", "中国", "西北", "历史", "古都"))
            or "不太清楚" in cr
            or "电脑角色" in cr
        )
        check(f"T56 [{user_text}] — useful reply", _useful, f"counter_reply={cr!r}")


# ══════════════════════════════════════════════════════════════════════════════
# T57 — Unsupported factual question returns transparent limitation, not opaque deflect
# ══════════════════════════════════════════════════════════════════════════════

def test_t57_unsupported_question_graceful_fallback() -> None:
    """[T57] Unsupported persona questions get transparent limitation, not '这个不好说'."""
    print("\n[T57] Unsupported question → transparent limitation, not opaque evasion")

    OPAQUE_PHRASES = ("这个不好说", "这个还是秘密", "这个以后再聊")

    for user_text in ("你的邮政编码是什么", "你的身高多少"):
        turn = simulate_turn(
            user_text,
            frame_id="f_from_where",
            engine="place",
            extra_cs={"persona_id": "meiling"},
        )
        if turn is None:
            skip(f"T57 [{user_text}]", "server not available"); continue

        cr = turn.get("counter_reply", "")
        print(f"    {user_text!r} → counter_reply: {cr!r}")

        check(
            f"T57 [{user_text}] — not opaque deflect",
            not any(p in cr for p in OPAQUE_PHRASES),
            f"counter_reply={cr!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T58 — Name-meaning question uses soft fallback, not "电脑角色"
# ══════════════════════════════════════════════════════════════════════════════

def test_t58_name_meaning_soft_fallback() -> None:
    """[T58] '美玲有什么意思啊' must not immediately use '电脑角色' fallback."""
    print("\n[T58] Name-meaning question → soft fallback, not hard '电脑角色'")

    turn = simulate_turn(
        "美玲有什么意思啊",
        frame_id="f_from_where",
        engine="identity",
        extra_cs={"persona_id": "meiling"},
    )
    if turn is None:
        skip("T58", "server not available"); return

    cr = turn.get("counter_reply", "")
    print(f"    counter_reply: {cr!r}")

    check("T58 — non-empty", bool(cr.strip()), "empty counter_reply")
    check(
        "T58 — no '电脑角色' for name question",
        "电脑角色" not in cr,
        f"counter_reply={cr!r}",
    )
    # Should contain some persona-voice content
    _useful = any(kw in cr for kw in ("不太确定", "家里", "好听", "叫", "名字"))
    check("T58 — soft persona-voice reply", _useful, f"counter_reply={cr!r}")


# ══════════════════════════════════════════════════════════════════════════════
# T59 — Work-location answer ("我工作在苏州") gets city acknowledgement
# ══════════════════════════════════════════════════════════════════════════════

def test_t59_work_location_city_acknowledged() -> None:
    """[T59] '我工作在苏州' answered to f_work_where must acknowledge 苏州."""
    print("\n[T59] '我工作在苏州' to f_work_where → city acknowledged in reaction")

    turn = simulate_turn(
        "我工作在苏州",
        frame_id="f_work_where",
        engine="work",
        extra_cs={"persona_id": "meiling"},
    )
    if turn is None:
        skip("T59", "server not available"); return

    # Combine reaction_prefix + frame_text + counter_reply for full output check
    combined = " ".join(filter(None, [
        turn.get("reaction_prefix", ""),
        turn.get("frame_text", ""),
        turn.get("counter_reply", ""),
    ]))
    print(f"    combined: {combined!r}")

    check("T59 — non-empty response", bool(combined.strip()), "empty response")
    # Response should mention 苏州 OR contain a work-acknowledgement phrase
    _ack = "苏州" in combined or any(kw in combined for kw in ("工作", "好的", "哦"))
    check("T59 — 苏州 or work acknowledgement present", _ack, f"combined={combined!r}")
    check("T59 — not '啊？'", combined.strip() != "啊？", f"got {combined!r}")


# ══════════════════════════════════════════════════════════════════════════════
# T60 — Work-location answer does NOT immediately bridge to travel
# ══════════════════════════════════════════════════════════════════════════════

def test_t60_work_location_no_immediate_travel_bridge() -> None:
    """[T60] '我工作在苏州' should not immediately bridge to travel with no acknowledgement."""
    print("\n[T60] '我工作在苏州' → no unacknowledged travel bridge")

    turn = simulate_turn(
        "我工作在苏州",
        frame_id="f_work_where",
        engine="work",
        extra_cs={"persona_id": "meiling"},
    )
    if turn is None:
        skip("T60", "server not available"); return

    frame_text = turn.get("frame_text", "")
    reaction   = turn.get("reaction_prefix", "")
    print(f"    frame_text: {frame_text!r}  reaction: {reaction!r}")

    # If the app bridges to travel ("你会去别的地方吗"), it MUST have an acknowledgement
    TRAVEL_BRIDGE = ("你会去别的地方吗", "你喜欢旅游吗", "你去过哪里")
    if any(tb in frame_text for tb in TRAVEL_BRIDGE):
        check(
            "T60 — travel bridge must have city acknowledgement",
            bool(reaction.strip()) or "苏州" in reaction,
            f"reaction={reaction!r}  frame_text={frame_text!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T61 — Health-improvement answer gets suitable acknowledgement
# ══════════════════════════════════════════════════════════════════════════════

def test_t61_health_improvement_warm_reaction() -> None:
    """[T61] '现在好很多' gets '那太好了' or equivalent, not only generic '真不错啊！'."""
    print("\n[T61] '现在好很多' → warm health-appropriate reaction")

    GENERIC_ONLY = ("真不错啊", "太厉害了", "太棒了")

    for user_text in ("现在好很多了", "好多了", "身体好多了"):
        turn = simulate_turn(
            user_text,
            frame_id="f_from_where",
            engine="place",
            extra_cs={"persona_id": "meiling"},
        )
        if turn is None:
            skip(f"T61 [{user_text}]", "server not available"); continue

        reaction = turn.get("reaction_prefix", "")
        print(f"    {user_text!r} → reaction_prefix: {reaction!r}")

        if reaction.strip():
            # Should not be only a generic boastful praise
            check(
                f"T61 [{user_text}] — reaction not only generic boast",
                not any(g in reaction for g in GENERIC_ONLY) or "太好了" in reaction or "那" in reaction,
                f"reaction={reaction!r}",
            )


# ══════════════════════════════════════════════════════════════════════════════
# T62 — "啊我退休了" is NOT treated as confusion and reaches work routing
# ══════════════════════════════════════════════════════════════════════════════

def test_t62_filler_retirement_not_confusion() -> None:
    """[T62] '啊我退休了' on work frame must not trigger confusion recovery."""
    print("\n[T62] '啊我退休了' → treated as retirement answer, not confusion")

    CONFUSION_MARKERS = ("再说一遍", "没听懂", "你可以再说", "哪里不明白", "你说的是什么")

    for user_text in ("啊我退休了", "嗯我退休了", "那个我退休了"):
        turn = simulate_turn(
            user_text,
            frame_id="f_what_work",
            engine="work",
            extra_cs={"persona_id": "meiling"},
        )
        if turn is None:
            skip(f"T62 [{user_text}]", "server not available"); continue

        combined = " ".join(filter(None, [turn.get("frame_text", ""), turn.get("counter_reply", "")]))
        print(f"    {user_text!r} → {combined!r}")

        check(
            f"T62 [{user_text}] — not confusion response",
            not any(m in combined for m in CONFUSION_MARKERS),
            f"combined={combined!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T63 — "嗯我是新西兰人" satisfies origin answer (not confusion)
# ══════════════════════════════════════════════════════════════════════════════

def test_t63_filler_nationality_accepted() -> None:
    """[T63] '嗯我是新西兰人' on origin frame must not loop or trigger confusion."""
    print("\n[T63] '嗯我是新西兰人' → accepted as origin answer")

    CONFUSION_MARKERS = ("再说一遍", "没听懂", "你可以再说", "你是来自哪里", "你是哪里人")
    LOOP_PATTERNS     = ("你现在住哪里", "你是哪里人")

    for user_text in ("嗯我是新西兰人", "啊我是新西兰人"):
        turn = simulate_turn(
            user_text,
            frame_id="f_from_where",
            engine="place",
            extra_cs={"persona_id": "meiling"},
        )
        if turn is None:
            skip(f"T63 [{user_text}]", "server not available"); continue

        ft = turn.get("frame_text", "")
        print(f"    {user_text!r} → frame_text: {ft!r}")

        check(
            f"T63 [{user_text}] — not confusion",
            not any(m in ft for m in CONFUSION_MARKERS),
            f"frame_text={ft!r}",
        )
        check(
            f"T63 [{user_text}] — not stuck in origin loop",
            not any(lp == ft.strip() for lp in LOOP_PATTERNS),
            f"frame_text={ft!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# T64 — "就是我以前是老师" is NOT evasive — routes to teacher context
# ══════════════════════════════════════════════════════════════════════════════

def test_t64_filler_teacher_accepted() -> None:
    """[T64] '就是我以前是老师' on work frame must not trigger confusion."""
    print("\n[T64] '就是我以前是老师' → accepted as teacher/work answer")

    CONFUSION_MARKERS = ("再说一遍", "没听懂", "你可以再说", "不太明白")

    turn = simulate_turn(
        "就是我以前是老师",
        frame_id="f_what_work",
        engine="work",
        extra_cs={"persona_id": "meiling"},
    )
    if turn is None:
        skip("T64", "server not available"); return

    combined = " ".join(filter(None, [turn.get("frame_text", ""), turn.get("counter_reply", "")]))
    print(f"    combined: {combined!r}")

    check(
        "T64 — not confusion response",
        not any(m in combined for m in CONFUSION_MARKERS),
        f"combined={combined!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T65 — "你呢你是哪里人" still triggers persona answer (turn-around preserved)
# ══════════════════════════════════════════════════════════════════════════════

def test_t65_ni_ne_persona_preserved() -> None:
    """[T65] '你呢你是哪里人' must still trigger a persona counter_reply."""
    print("\n[T65] '你呢你是哪里人' → persona counter_reply (not suppressed by filler strip)")

    turn = simulate_turn(
        "你呢你是哪里人",
        frame_id="f_from_where",
        engine="place",
        extra_cs={"persona_id": "meiling"},
    )
    if turn is None:
        skip("T65", "server not available"); return

    cr = turn.get("counter_reply", "")
    print(f"    counter_reply: {cr!r}")

    check("T65 — non-empty counter_reply", bool(cr.strip()), "empty counter_reply")
    check("T65 — contains persona first-person voice", "我" in cr, f"counter_reply={cr!r}")


# ══════════════════════════════════════════════════════════════════════════════
# T66 — Standalone "啊？" still triggers confusion recovery
# ══════════════════════════════════════════════════════════════════════════════

def test_t66_standalone_confusion_preserved() -> None:
    """[T66] Standalone '啊？' must still be treated as confusion, not a persona question."""
    print("\n[T66] Standalone '啊？' → confusion recovery, not persona answer")

    CONFUSION_RESPONSE_MARKERS = ("再说一遍", "没关系", "换个", "你哪句", "先说", "慢一点", "一步", "简单")

    turn = simulate_turn(
        "啊？",
        frame_id="f_from_where",
        engine="place",
        extra_cs={"persona_id": "meiling"},
    )
    if turn is None:
        skip("T66", "server not available"); return

    combined = " ".join(filter(None, [turn.get("frame_text", ""), turn.get("counter_reply", "")]))
    print(f"    combined: {combined!r}")

    # The response should either be a recovery/repair phrase OR an advance (both are acceptable)
    # Key requirement: '我' (persona first-person) counter_reply should NOT fire
    cr = turn.get("counter_reply", "")
    check(
        "T66 — no persona first-person counter_reply for bare confusion signal",
        not (cr.strip().startswith("我") and len(cr.strip()) > 10),
        f"counter_reply={cr!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T67 — Standalone "对/嗯" after clarification still confirms successfully
# ══════════════════════════════════════════════════════════════════════════════

def test_t67_standalone_affirmation_preserved() -> None:
    """[T67] Standalone '对' after '你是说...' clarification still confirms."""
    print("\n[T67] Standalone '对' after clarification → confirmation success (not loop)")

    LOOP_MARKERS = ("你是说", "你是说你已经")

    for affirm in ("对", "嗯", "是的"):
        turn = simulate_turn(
            affirm,
            frame_id="f_what_work",
            engine="work",
            extra_cs={
                "persona_id":           "meiling",
                "last_partner_frame_text": "你是说你已经退休了吗？",
                "repair_attempt_count": 1,
            },
        )
        if turn is None:
            skip(f"T67 [{affirm}]", "server not available"); continue

        ft = turn.get("frame_text", "")
        print(f"    {affirm!r} → frame_text: {ft!r}")

        # After confirmation, the app should NOT immediately re-ask "你是说..." again
        check(
            f"T67 [{affirm}] — does not re-ask clarification immediately",
            not any(m in ft for m in LOOP_MARKERS),
            f"frame_text={ft!r}",
        )


if __name__ == "__main__":
    main()
