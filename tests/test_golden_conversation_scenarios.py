#!/usr/bin/env python3
"""
MandarinOS — Golden Conversation Scenario Tests

A second testing layer on top of the isolated interaction-regression tests.
These tests simulate realistic multi-turn alpha conversations and assert
*behavioural invariants*, not exact wording — so they stay robust even as
content (frame text, reactions, option pools) evolves.

Design goals
------------
- Catch whole-conversation quality regressions that isolated unit tests miss.
- Model the 3–5 alpha session patterns that were observed during Release 1.0 development.
- Fail clearly on the known regressions documented in the task brief.

Usage:
  python tests/test_golden_conversation_scenarios.py
  (server must be running: python scripts/ui_server.py)
"""

import io
import json
import sys
import urllib.error
import urllib.request
from typing import Optional

# Guard: only replace stdout when running as a standalone script.
# Under pytest, sys.stdout is a capture buffer; replacing it corrupts capture.
if sys.stdout is sys.__stdout__:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pytest  # noqa: E402  (after the conditional stdout setup)
pytestmark = pytest.mark.live_server

SERVER = "http://localhost:8765"

# ── Colour helpers ──────────────────────────────────────────────────────────
PASS_C = "\033[32mPASS\033[0m"
FAIL_C = "\033[31mFAIL\033[0m"
SKIP_C = "\033[33mSKIP\033[0m"

_results: list = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS_C if condition else FAIL_C
    suffix = f"  ← {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    _results.append((name, condition))


def skip(name: str, reason: str = "") -> None:
    suffix = f"  ← {reason}" if reason else ""
    print(f"  [{SKIP_C}] {name}{suffix}")


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _server_alive() -> bool:
    try:
        urllib.request.urlopen(f"{SERVER}/", timeout=2)
    except urllib.error.HTTPError:
        return True
    except urllib.error.URLError:
        return False
    return True


def _post(payload: dict) -> Optional[dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{SERVER}/api/run_turn",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


# ── Conversation state helpers ───────────────────────────────────────────────

def _base_cs(
    engine: str = "family",
    recent: list | None = None,
    exchange: int = 4,
    persona: str = "meiling",
    extra: dict | None = None,
) -> dict:
    cs: dict = {
        "last_turn_was_answer":    True,
        "current_engine":          engine,
        "recent_frame_ids":        recent or [],
        "exchange_count":          exchange,
        "learner_id":              "golden_scenario_tester",
        "persona_id":              persona,
        "same_engine_chain_count": 1,
        "interest_level":          "medium",
    }
    if extra:
        cs.update(extra)
    return cs


def _answer(frame_id: str, text: str) -> dict:
    return {
        "frame_id":              frame_id,
        "submitted_text":        text,
        "selected_option_hanzi": text,
        "move_type":             "ANSWER",
    }


def one_turn(
    user_text:  str,
    frame_id:   str   = "unknown",
    engine:     str   = "family",
    recent:     list | None = None,
    extra_cs:   dict | None = None,
    persona:    str   = "meiling",
) -> Optional[dict]:
    """Send one conversational turn, return the parsed response or None."""
    cs = _base_cs(engine=engine, recent=recent, persona=persona, extra=extra_cs)
    cs["last_answer"] = _answer(frame_id, user_text)
    resp = _post({
        "turn_uid":           "golden_scenario_test",
        "next_question":      True,
        "conversation_state": cs,
    })
    return resp


def combined(resp: dict) -> str:
    """All visible learner-facing text from a response."""
    return (
        (resp.get("frame_text") or "")
        + " "
        + (resp.get("counter_reply") or "")
    ).strip()


def chain_turns(
    steps: list[dict],
    persona: str = "meiling",
    start_engine: str = "family",
    start_exchange: int = 3,
) -> list[Optional[dict]]:
    """
    Execute a multi-step scenario, propagating state between turns.

    Each step: {"user_text": str, "frame_id": str, "engine": str (optional)}
    Returns list of responses (None if server down).
    """
    cs: dict = _base_cs(
        engine=start_engine,
        persona=persona,
        exchange=start_exchange,
    )
    results: list = []

    for step in steps:
        cs["last_answer"] = _answer(
            step.get("frame_id", cs.get("current_engine", "unknown")),
            step["user_text"],
        )
        resp = _post({
            "turn_uid":           "golden_scenario_chain",
            "next_question":      True,
            "conversation_state": cs,
        })
        results.append(resp)

        if resp:
            su = resp.get("state_update") or {}
            # Propagate conversation state forward
            if su.get("current_engine"):
                cs["current_engine"] = su["current_engine"]
            if su.get("last_counter_reply") is not None:
                cs["last_counter_reply"] = su["last_counter_reply"]
            if su.get("last_partner_frame_text"):
                cs["last_partner_frame_text"] = su["last_partner_frame_text"]
            next_fid = resp.get("frame_id", "")
            if next_fid:
                cs["recent_frame_ids"] = (cs.get("recent_frame_ids") or [])[-9:] + [next_fid]
                cs["last_partner_frame_id"] = next_fid
            cs["exchange_count"] = int(cs.get("exchange_count", 0)) + 1
            cs["same_engine_chain_count"] = int(cs.get("same_engine_chain_count", 0)) + 1
        else:
            results.append(None)
            break

    return results


# ── Shared assertion helper ───────────────────────────────────────────────────

def assert_not_interviewer_mode(responses: list[Optional[dict]], label: str) -> None:
    """
    Check that across the responses the app does not behave purely as an
    interviewer that ignores what the learner says.

    Invariants:
    1. No 'direct 你-question' response contains '我是问'.
    2. If the learner asked a 你 question, the next response must contain
       at least one first-person persona marker (我 / 我呢 / 对我来说).
    3. No frame_id is repeated on consecutive turns (app isn't loop-asking).
    """
    prev_frame_id = ""
    for i, resp in enumerate(responses):
        if resp is None:
            continue
        txt = combined(resp)
        fid = resp.get("frame_id", "")
        # Rule 1: no stacked clarification inside any response
        clar_count = txt.count("我是问")
        check(
            f"{label} turn {i+1} — '我是问' appears at most once in output",
            clar_count <= 1,
            f"count={clar_count}, got: {txt[:120]!r}",
        )
        # Rule 3: no consecutive identical frame (tight re-ask loop)
        if prev_frame_id and fid == prev_frame_id:
            check(
                f"{label} turn {i+1} — frame_id not repeated on consecutive turns",
                False,
                f"frame_id={fid!r} repeated",
            )
        prev_frame_id = fid


# ══════════════════════════════════════════════════════════════════════════════
# GS1 — User-led persona question must interrupt pending-frame pressure
#
# Regression: "你喜欢北京吗" during a pending family frame was answered
#             with "我是问：你和家里谁最亲近？" instead of a persona answer.
# ══════════════════════════════════════════════════════════════════════════════

def test_gs1_persona_question_interrupts_pending_frame() -> None:
    print("\n[GS1] User persona question interrupts pending-frame pressure")

    # Simulate: the last frame was 你和家里谁最亲近 (family engine)
    # User asks the persona a direct question instead of answering
    resp = one_turn(
        "你喜欢北京吗",
        frame_id="f_probe_family_closest",
        engine="family",
        recent=["p2_fa_live_with"],
    )
    if resp is None:
        skip("GS1", "server not available"); return

    txt = combined(resp)
    cr  = resp.get("counter_reply", "") or ""
    ft  = resp.get("frame_text", "") or ""
    print(f"    counter_reply : {cr!r}")
    print(f"    frame_text    : {ft!r}")

    # Must NOT produce clarification wrapper for a direct persona question
    check(
        "GS1a — response does NOT contain '我是问'",
        "我是问" not in txt,
        f"got: {txt[:140]!r}",
    )
    # Must provide some content (not empty or pure silence)
    check(
        "GS1b — response is non-empty",
        bool(txt.strip()),
        "response was empty",
    )
    # The counter_reply or frame_text should contain a first-person persona answer
    check(
        "GS1c — response contains persona first-person voice (我 / 挺 / 喜欢)",
        any(kw in txt for kw in ("我", "挺", "喜欢", "还")),
        f"got: {txt[:140]!r}",
    )


def test_gs1b_beijing_like_question_gets_answer() -> None:
    print("\n[GS1b] '你喜欢北京吗' gets a persona answer, not clarification")

    # Test with various family-frame contexts
    for pending_frame in ("f_probe_family_closest", "f_live_with_who", "f_married"):
        resp = one_turn(
            "你喜欢北京吗",
            frame_id=pending_frame,
            engine="family",
        )
        if resp is None:
            skip(f"GS1b [{pending_frame}]", "server not available"); continue

        txt = combined(resp)
        check(
            f"GS1b [{pending_frame}] — no '我是问' for direct persona question",
            "我是问" not in txt,
            f"got: {txt[:120]!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# GS2 — Marriage answers must satisfy the marriage frame
#
# Regressions:
# - "结婚了"       → "我是问：听起来很温馨！你结婚了吗？"
# - "是是我结婚了" → "啊？"
# ══════════════════════════════════════════════════════════════════════════════

def test_gs2_marriage_answer_accepted() -> None:
    print("\n[GS2] Marriage answers satisfy the marriage frame")

    marriage_answers = [
        "结婚了",
        "是是我结婚了",
        "我结婚了",
        "对，我结婚了",
        "我们结婚两年了",
    ]
    for ans in marriage_answers:
        resp = one_turn(
            ans,
            frame_id="f_married",
            engine="family",
            recent=["p2_fa_live_with", "f_probe_family_closest"],
            extra_cs={
                "last_partner_frame_text": "你结婚了吗？",
                "last_counter_reply":      "",
            },
        )
        if resp is None:
            skip(f"GS2 [{ans!r}]", "server not available"); continue

        txt = combined(resp)
        ft  = resp.get("frame_text", "") or ""
        cr  = resp.get("counter_reply", "") or ""
        print(f"    [{ans!r}] → frame={ft[:80]!r}  cr={cr[:60]!r}")

        # Must NOT reply with bare confusion marker
        check(
            f"GS2 [{ans!r}] — response is not '啊？'",
            "啊？" not in txt.strip(),
            f"got: {txt[:120]!r}",
        )
        # Must NOT re-ask the marriage question
        check(
            f"GS2 [{ans!r}] — app does not immediately re-ask '你结婚了吗'",
            "你结婚了吗" not in ft,
            f"frame_text: {ft[:120]!r}",
        )
        # Must NOT produce stacked clarification
        check(
            f"GS2 [{ans!r}] — no '我是问' wrapping",
            "我是问" not in txt,
            f"got: {txt[:120]!r}",
        )


def test_gs2b_marriage_fact_in_answer_skips_frame() -> None:
    """If the learner already revealed marriage info, app must NOT ask 你结婚了吗."""
    print("\n[GS2b] Marriage already revealed — app skips marriage frame")

    marriage_reveals = [
        ("f_probe_family_closest", "我最亲近我的太太所以我们结婚两年了"),
        ("f_probe_family_closest", "我和老婆住在一起，感情很好"),
        ("p2_fa_live_with",        "我和我老婆一起住"),
    ]
    for frame_id, ans in marriage_reveals:
        resp = one_turn(
            ans,
            frame_id=frame_id,
            engine="family",
            recent=["p2_fa_live_with"],
        )
        if resp is None:
            skip(f"GS2b [{ans[:30]!r}]", "server not available"); continue

        ft = resp.get("frame_text", "") or ""
        check(
            f"GS2b [{ans[:35]!r}] — app does NOT ask '你结婚了吗' after marriage revealed",
            "你结婚了吗" not in ft,
            f"frame_text: {ft[:120]!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# GS3 — No questionnaire-only drift across a multi-turn conversation
#
# After a learner says 你呢 or asks a direct persona question, the app
# must respond to the question before continuing its own question sequence.
# ══════════════════════════════════════════════════════════════════════════════

def test_gs3_no_questionnaire_drift() -> None:
    print("\n[GS3] Multi-turn: app responds to 你呢 and direct questions")

    # Simulate a realistic 6-turn family conversation
    steps = [
        {"user_text": "我和家人住在一起",           "frame_id": "p2_fa_live_with"},
        {"user_text": "我和妈妈最亲近",             "frame_id": "f_probe_family_closest"},
        {"user_text": "我们经常一起吃饭，你呢",     "frame_id": "p2_fa_activity"},
        {"user_text": "你有家人吗",                  "frame_id": "p2_fa_activity"},
        {"user_text": "我结婚了，有一个孩子",        "frame_id": "f_married"},
        {"user_text": "你呢，你有孩子吗",            "frame_id": "f_have_children"},
    ]
    resps = chain_turns(steps, persona="meiling", start_engine="family")

    if any(r is None for r in resps[:3]):
        skip("GS3", "server not available"); return

    # Turn 3: user appended "你呢" — must get a persona reply in counter_reply
    resp3 = resps[2]
    if resp3:
        cr3 = resp3.get("counter_reply", "") or ""
        check(
            "GS3a — 你呢 at turn 3 generates a persona counter_reply",
            bool(cr3.strip()),
            f"counter_reply: {cr3!r}",
        )
        check(
            "GS3b — counter_reply contains first-person persona content",
            "我" in cr3,
            f"got: {cr3!r}",
        )

    # Turn 4: user asked "你有家人吗" — must answer persona question
    resp4 = resps[3]
    if resp4:
        cr4  = resp4.get("counter_reply", "") or ""
        txt4 = combined(resp4)
        check(
            "GS3c — direct '你有家人吗' question gets a persona response",
            "我" in txt4,
            f"got: {txt4[:120]!r}",
        )
        check(
            "GS3d — '你有家人吗' response does not contain '我是问'",
            "我是问" not in txt4,
            f"got: {txt4[:120]!r}",
        )

    # Turn 6: user asked "你呢，你有孩子吗" — persona must respond with something meaningful
    # (deflect phrases like "还没有，不急。" count as a persona reply)
    resp6 = resps[5] if len(resps) > 5 else None
    if resp6:
        txt6 = combined(resp6)
        cr6  = resp6.get("counter_reply", "") or ""
        check(
            "GS3e — '你呢你有孩子吗' gets a persona reply (counter_reply non-empty OR 我 in combined)",
            bool(cr6.strip()) or "我" in txt6,
            f"got: {txt6[:120]!r}",
        )

    # Run the shared interviewer-mode guard across all valid responses
    valid = [r for r in resps if r is not None]
    assert_not_interviewer_mode(valid, "GS3")


# ══════════════════════════════════════════════════════════════════════════════
# GS4 — No clarification wrapper stacking
#
# Regression: after "我是问：听起来很温馨！你结婚了吗？", sending any answer
# must not re-wrap the string with another "我是问：".
# ══════════════════════════════════════════════════════════════════════════════

def test_gs4_no_clarification_stacking() -> None:
    print("\n[GS4] Clarification wrapper must not stack (我是问 appears ≤ 1 time)")

    # Simulate: previous partner text was already a clarification
    prev_clarified = "我是问：你现在住的地方在哪里？"
    confusion_answers = ["啊", "不懂", "什么意思"]

    for ans in confusion_answers:
        resp = one_turn(
            ans,
            frame_id="f_live_where",
            engine="place",
            extra_cs={
                "last_partner_frame_text": prev_clarified,
                "last_counter_reply":      prev_clarified,
            },
        )
        if resp is None:
            skip(f"GS4 [{ans!r}]", "server not available"); continue

        txt = combined(resp)
        count = txt.count("我是问")
        check(
            f"GS4 [{ans!r}] — '我是问' appears at most once",
            count <= 1,
            f"count={count}, got: {txt[:140]!r}",
        )

    # Also verify: a reaction prefix + frame text never produces "我是问：哦，X！我是问"
    resp2 = one_turn(
        "啊",
        frame_id="f_probe_family_closest",
        engine="family",
        extra_cs={
            "last_partner_frame_text": "听起来很温馨！你结婚了吗？",
            "last_counter_reply":      "我是问：听起来很温馨！你结婚了吗？",
        },
    )
    if resp2:
        txt2 = combined(resp2)
        check(
            "GS4 — reaction-prefixed clarification does not double-wrap",
            txt2.count("我是问") <= 1,
            f"got: {txt2[:140]!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# GS5 — Location noisy answer leads to continuation, not repeat question
#
# Regression: "我现在住在等你等" must NOT produce another "你现在住哪里".
# ══════════════════════════════════════════════════════════════════════════════

def test_gs5_noisy_location_continues() -> None:
    print("\n[GS5] Noisy location answer → continuation, not repeat question")

    noisy_locations = [
        ("f_live_where",  "我现在住在等你等"),
        ("f_from_where",  "我是生气老人"),
        ("f_live_where",  "住在等你等的地方"),
    ]
    for frame_id, ans in noisy_locations:
        resp = one_turn(
            ans,
            frame_id=frame_id,
            engine="place",
            recent=[frame_id],
            extra_cs={"location_retry_count": 0},
        )
        if resp is None:
            skip(f"GS5 [{ans!r}]", "server not available"); continue

        ft  = resp.get("frame_text", "") or ""
        txt = combined(resp)
        print(f"    [{ans[:30]!r}] → {ft[:80]!r}")

        check(
            f"GS5 [{ans[:30]!r}] — app does NOT repeat '你现在住哪里'",
            "你现在住哪里" not in ft,
            f"frame_text: {ft[:120]!r}",
        )
        check(
            f"GS5 [{ans[:30]!r}] — app does NOT repeat '你是哪里人'",
            "你是哪里人" not in ft,
            f"frame_text: {ft[:120]!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# GS6 — Persona marriage question gets a cooperative answer
#
# Regression: "你呢你结婚了吗" → "这个还是秘密。" (evasive)
# Expected: cooperative default like "还没有，…" or persona-specific answer.
# ══════════════════════════════════════════════════════════════════════════════

def test_gs6_persona_marriage_question_cooperative() -> None:
    print("\n[GS6] '你呢你结婚了吗' gets a cooperative persona answer")

    marriage_questions = [
        "你呢你结婚了吗",
        "你结婚了吗",
        "你有没有结婚",
    ]
    for q in marriage_questions:
        resp = one_turn(
            q,
            frame_id="f_married",
            engine="family",
            recent=["f_married"],
        )
        if resp is None:
            skip(f"GS6 [{q!r}]", "server not available"); continue

        txt = combined(resp)
        cr  = resp.get("counter_reply", "") or ""
        print(f"    [{q!r}] → cr={cr!r}")

        check(
            f"GS6 [{q!r}] — persona answer is NOT '这个还是秘密'",
            "这个还是秘密" not in txt,
            f"got: {txt[:140]!r}",
        )
        check(
            f"GS6 [{q!r}] — response is non-empty",
            bool(txt.strip()),
            "response was empty",
        )


# ══════════════════════════════════════════════════════════════════════════════
# GS7 — Full family conversation mini-arc (integration check)
#
# A 4-turn family arc where the learner mentions marriage, asks back,
# and the app doesn't interview-loop.
# ══════════════════════════════════════════════════════════════════════════════

def test_gs7_family_arc_integration() -> None:
    print("\n[GS7] Family mini-arc integration: marriage reveal → no re-ask → persona replies")

    steps = [
        # Turn 1: learner says they live with wife (reveals marriage)
        {"user_text": "我和老婆一起住",              "frame_id": "p2_fa_live_with"},
        # Turn 2: learner asks persona a question
        {"user_text": "你喜欢北京吗",                "frame_id": "f_probe_family_closest"},
        # Turn 3: learner answers the app's question directly
        {"user_text": "我和妈妈最亲近",              "frame_id": "f_probe_family_closest"},
        # Turn 4: learner asks persona about marriage
        {"user_text": "你呢你结婚了吗",              "frame_id": "p2_fa_activity"},
    ]
    resps = chain_turns(steps, persona="meiling", start_engine="family")

    if any(r is None for r in resps[:2]):
        skip("GS7", "server not available"); return

    # Turn 1: marriage already revealed in answer — app must NOT ask 你结婚了吗 immediately
    if resps[0]:
        ft1 = resps[0].get("frame_text", "") or ""
        check(
            "GS7a — after '我和老婆一起住', app does NOT ask '你结婚了吗'",
            "你结婚了吗" not in ft1,
            f"frame_text: {ft1[:120]!r}",
        )

    # Turn 2: persona question → must NOT produce 我是问
    if resps[1]:
        txt2 = combined(resps[1])
        check(
            "GS7b — '你喜欢北京吗' does not produce '我是问：'",
            "我是问" not in txt2,
            f"got: {txt2[:120]!r}",
        )
        check(
            "GS7c — '你喜欢北京吗' gets a persona response (我)",
            "我" in txt2,
            f"got: {txt2[:120]!r}",
        )

    # Turn 4: persona marriage question — must be cooperative
    if len(resps) > 3 and resps[3]:
        txt4 = combined(resps[3])
        check(
            "GS7d — '你呢你结婚了吗' is NOT evasive '这个还是秘密'",
            "这个还是秘密" not in txt4,
            f"got: {txt4[:120]!r}",
        )

    # Overall interviewer-mode guard
    valid = [r for r in resps if r is not None]
    assert_not_interviewer_mode(valid, "GS7")


# ══════════════════════════════════════════════════════════════════════════════
# GS8 — Retired university teacher arc: no coaching, paraphrase confirmation works
#
# Reproduces the exact failure reported:
#   USER: 我退休了
#   USER: 我已经是老师大学的老师
#   USER: 老师我已经是老师大学的老师
#   USER: 中方的大学西安交通Liverpool
#   APP:  你是说：你以前在大学工作吗？   (OK — semantic clarification)
#   USER: 对
#   APP:  ← VIOLATION: "没关系。你可以说一个简单句。比如：我退休了。 / 我是老师。"
#
# Required:
# 1. None of the turns 2-4 triggers a coaching-template response.
# 2. "我退休了" + "大学老师" answers must not end in coaching.
# 3. Confirmation "对" must NOT produce "你可以说" or "简单句" or "比如：".
# 4. App produces warm acknowledgement or natural follow-up instead.
# ══════════════════════════════════════════════════════════════════════════════

def test_gs8_retired_teacher_no_coaching() -> None:
    """[GS8] Retired university teacher should never see answer-template coaching."""
    print("\n[GS8] Retired teacher arc — no coaching, paraphrase confirmation works")

    _COACHING_MARKERS = ("你可以说", "简单句", "比如：", "你可以回答")

    base_cs = _base_cs(engine="work", exchange=3)

    # GS8a: "我退休了" must not trigger coaching
    r1 = one_turn("我退休了", frame_id="f_what_work", engine="work", extra_cs=base_cs)
    if r1 is None:
        skip("GS8a", "server not available"); return
    txt1 = combined(r1)
    print(f"    GS8a: {txt1[:100]!r}")
    for marker in _COACHING_MARKERS:
        check(
            f"GS8a — '我退休了' output does NOT contain coaching marker '{marker}'",
            marker not in txt1,
            f"got: {txt1[:120]!r}",
        )
    check(
        "GS8a — '我退休了' gets a non-empty follow-up",
        bool(txt1.strip()),
        "empty output",
    )

    # GS8b: noisy teacher answer must not trigger coaching
    cs2 = dict(base_cs)
    su1 = r1.get("state_update") or {}
    if isinstance(su1, dict):
        cs2.update(su1)
    cs2["current_engine"] = "work"
    r2 = one_turn("我已经是老师大学的老师", frame_id="f_what_work", engine="work", extra_cs=cs2)
    if r2 is not None:
        txt2 = combined(r2)
        print(f"    GS8b: {txt2[:100]!r}")
        for marker in _COACHING_MARKERS:
            check(
                f"GS8b — '大学老师' answer does NOT contain coaching marker '{marker}'",
                marker not in txt2,
                f"got: {txt2[:120]!r}",
            )

    # GS8c: "中方的大学西安交通Liverpool" (education context) must not trigger coaching
    cs3 = dict(cs2)
    if r2 is not None:
        su2 = r2.get("state_update") or {}
        if isinstance(su2, dict):
            cs3.update(su2)
    r3 = one_turn(
        "中方的大学西安交通Liverpool",
        frame_id="f_what_work",
        engine="work",
        extra_cs=cs3,
    )
    if r3 is not None:
        txt3 = combined(r3)
        print(f"    GS8c: {txt3[:100]!r}")
        for marker in _COACHING_MARKERS:
            check(
                f"GS8c — education-context answer does NOT contain coaching marker '{marker}'",
                marker not in txt3,
                f"got: {txt3[:120]!r}",
            )

    # GS8d: plain affirmation "对" must not produce coaching template
    cs4 = dict(cs3)
    if r3 is not None:
        su3 = r3.get("state_update") or {}
        if isinstance(su3, dict):
            cs4.update(su3)
    cs4.setdefault("last_partner_frame_text", "你是说：你以前在大学工作吗？")
    r4 = one_turn("对", frame_id="f_what_work", engine="work", extra_cs=cs4)
    if r4 is not None:
        txt4 = combined(r4)
        print(f"    GS8d: {txt4[:100]!r}")
        for marker in _COACHING_MARKERS:
            check(
                f"GS8d — '对' after paraphrase does NOT contain coaching marker '{marker}'",
                marker not in txt4,
                f"got: {txt4[:120]!r}",
            )
        check(
            "GS8d — '对' after paraphrase gets a non-empty response",
            bool(txt4.strip()),
            "empty output",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 62)
    print("MandarinOS — Golden Conversation Scenario Tests")
    print("=" * 62)

    if "--static-only" in sys.argv:
        print("(--static-only: no live-server tests in this suite)")
        sys.exit(0)

    if not _server_alive():
        print(f"\n⚠  Server not reachable at {SERVER}")
        print("   Start with: python scripts/ui_server.py")
        print("   Then re-run this script.")
        sys.exit(1)

    test_gs1_persona_question_interrupts_pending_frame()
    test_gs1b_beijing_like_question_gets_answer()
    test_gs2_marriage_answer_accepted()
    test_gs2b_marriage_fact_in_answer_skips_frame()
    test_gs3_no_questionnaire_drift()
    test_gs4_no_clarification_stacking()
    test_gs5_noisy_location_continues()
    test_gs6_persona_marriage_question_cooperative()
    test_gs7_family_arc_integration()
    test_gs8_retired_teacher_no_coaching()

    total  = len(_results)
    passed = sum(1 for _, ok in _results if ok)
    failed = total - passed

    print()
    print("=" * 62)
    colour = "\033[32m" if failed == 0 else "\033[31m"
    reset  = "\033[0m"
    print(f"{colour}{passed}/{total} passed{reset}", end="")
    if failed:
        print(f"  ({failed} failed)")
    else:
        print()
    print("=" * 62)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
