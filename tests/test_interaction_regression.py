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
        "T3b — output contains a relevant persona response (秘密 / 结婚 / 成家 / 单身 / 婚)",
        any(p in combined for p in ["秘密", "结婚", "成家", "单身", "婚", "结"]),
        f"combined: {combined[:100]!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# T4 — No generic filler after noisy semantic input
# ══════════════════════════════════════════════════════════════════════════════

def test_t4_no_filler_after_noisy_semantic() -> None:
    """[T4] Noisy input containing 新西兰 must not produce generic filler."""
    print("\n[T4] No filler after noisy semantic input — 我现在住新西兰等你等")
    # frame_id="f_from_where" so CITY slot is detected from frame_id mapping
    turn = simulate_turn("我现在住新西兰等你等", frame_id="f_from_where", engine="place")
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
    # "你可以说" / "简单句" are added by the client-side escalation in app.js.
    # At the server level, accept any supportive / clarifying response.
    check(
        "T5b — final output contains supportive or clarifying language",
        any(p in combined for p in [
            "你可以说", "简单句", "我可以", "说简单", "再说", "不清楚", "明白",
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
    Level 1 (retry_count=1): scaffold model      — 我没听清楚。你可以说：我住在新西兰。
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


if __name__ == "__main__":
    main()
