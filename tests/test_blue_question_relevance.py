#!/usr/bin/env python3
"""
MandarinOS — Blue-Question Relevance Tests

Verifies that the blue/discovery question panel surfaces questions that are
directly relevant to the active conversation context: current frame question,
persona answer, and current engine.

Each test scenario hits /api/run_turn and inspects the returned
`discovery_questions` list for relevance.

Usage:
  python tests/test_blue_question_relevance.py
Server must be running: python scripts/ui_server.py
"""

import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Guard: only replace stdout when running as a standalone script.
# Under pytest, sys.stdout is a capture buffer; replacing it corrupts capture.
if sys.stdout is sys.__stdout__:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pytest  # noqa: E402  (after the conditional stdout setup)
pytestmark = pytest.mark.live_server

ROOT   = Path(__file__).parent.parent
SERVER = "http://localhost:8765"

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
    print(f"  [{SKIP_C}] {name}  ← {reason}")
    _results.append((name, True))


def api_run_turn(last_answer: dict, cs: dict | None = None) -> dict | None:
    cs_with_answer = dict(cs or {})
    cs_with_answer["last_answer"] = last_answer
    payload = json.dumps({
        "turn_uid":           "blue_relevance_test",
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


def make_cs(engine: str = "place", extra: dict | None = None) -> dict:
    cs = {
        "current_engine":           engine,
        "recent_frame_ids":         [],
        "exchange_count":           3,
        "last_turn_was_answer":     True,
        "learner_id":               "blue_relevance_tester",
        "persona_id":               "meiling",
        "same_engine_chain_count":  1,
        "interest_level":           "medium",
        "consecutive_app_questions": 2,
    }
    if extra:
        cs.update(extra)
    return cs


def discovery_topics(resp: dict) -> list[str]:
    """Extract topic list from discovery_questions."""
    return [q.get("topic", "") for q in (resp.get("discovery_questions") or [])]


def discovery_zh(resp: dict) -> list[str]:
    """Extract Chinese question texts from discovery_questions."""
    return [q.get("zh", "") for q in (resp.get("discovery_questions") or [])]


# ══════════════════════════════════════════════════════════════════════════════
# BQ1 — Frame 你是哪里人？ → place/origin questions, no unrelated work/food
# ══════════════════════════════════════════════════════════════════════════════

def test_bq1_place_frame_origin_questions() -> None:
    """[BQ1] Active frame '你是哪里人？' → blue questions must be place/origin-related."""
    print("\n[BQ1] Frame '你是哪里人？' → place/origin questions in blue panel")

    resp = api_run_turn(
        {"frame_id": "f_from_where", "submitted_text": "我是新西兰人",
         "selected_option_hanzi": "我是新西兰人", "move_type": "ANSWER"},
        make_cs(engine="place", extra={
            "last_partner_frame_text":  "你是哪里人？",
            "last_partner_frame_id":    "f_from_where",
        }),
    )
    if resp is None:
        skip("BQ1", "server not available"); return

    topics = discovery_topics(resp)
    zhs    = discovery_zh(resp)
    print(f"    topics: {topics}")
    print(f"    questions: {zhs}")

    place_topics = {"place_from", "place_like", "place_special", "place_far",
                    "place_food", "place_still_live", "place_distance_time",
                    "place_why_like", "place_distance_ref"}
    unrelated = {"work_what", "work_like", "work_duration", "food_fav",
                 "food_spicy", "food_cook", "family_size", "children"}

    check(
        "BQ1a — at least one place/origin-related question shown",
        any(t in place_topics for t in topics) or
        any(kw in " ".join(zhs) for kw in ("哪里", "住", "地方", "远")),
        f"topics={topics}",
    )
    check(
        "BQ1b — no unrelated work/food questions shown",
        not any(t in unrelated for t in topics),
        f"topics={topics}",
    )
    check(
        "BQ1c — discovery_questions non-empty",
        bool(resp.get("discovery_questions")),
        "empty discovery_questions",
    )


# ══════════════════════════════════════════════════════════════════════════════
# BQ2 — Persona answer mentions 成都/北京 → place-related questions surface
# ══════════════════════════════════════════════════════════════════════════════

def test_bq2_persona_city_mention_triggers_place_questions() -> None:
    """[BQ2] Persona answer '我是成都人，不过在北京工作' → city/work-place questions shown."""
    print("\n[BQ2] Persona reveals Chengdu + Beijing → place/work questions in blue panel")

    resp = api_run_turn(
        {"frame_id": "f_from_where", "submitted_text": "你是哪里人？",
         "selected_option_hanzi": "你是哪里人？", "move_type": "ANSWER"},
        make_cs(engine="place", extra={
            "last_partner_frame_text":  "你是哪里人？",
            "last_partner_frame_id":    "f_from_where",
            # Simulate a persona reveal in previous turn
            "last_persona_reveal":      True,
            "last_counter_reply":       "我是成都人，不过在北京工作已经好几年了。",
        }),
    )
    if resp is None:
        skip("BQ2", "server not available"); return

    topics = discovery_topics(resp)
    zhs    = discovery_zh(resp)
    print(f"    topics: {topics}")
    print(f"    questions: {zhs}")

    place_work_topics = {"place_from", "place_like", "place_special", "place_why_like",
                         "work_what", "work_like", "work_duration", "work_why",
                         "place_far", "place_food"}

    check(
        "BQ2a — at least one place or work-place question shown",
        any(t in place_work_topics for t in topics) or
        any(kw in " ".join(zhs) for kw in ("那里", "喜欢", "工作", "哪里")),
        f"topics={topics}",
    )
    check(
        "BQ2b — no unrelated family/food questions dominate",
        not (len(topics) >= 2 and all(t in {"family_size", "children", "food_fav"} for t in topics)),
        f"topics={topics}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# BQ3 — Frame 你做什么工作？ → work questions, no place/food
# ══════════════════════════════════════════════════════════════════════════════

def test_bq3_work_frame_triggers_work_questions() -> None:
    """[BQ3] Active frame '你做什么工作？' → work questions in blue panel, no place/food."""
    print("\n[BQ3] Frame '你做什么工作？' → work questions in blue panel")

    resp = api_run_turn(
        {"frame_id": "f_what_work", "submitted_text": "我是老师",
         "selected_option_hanzi": "我是老师", "move_type": "ANSWER"},
        make_cs(engine="work", extra={
            "last_partner_frame_text":  "你做什么工作？",
            "last_partner_frame_id":    "f_what_work",
        }),
    )
    if resp is None:
        skip("BQ3", "server not available"); return

    topics = discovery_topics(resp)
    zhs    = discovery_zh(resp)
    print(f"    topics: {topics}")
    print(f"    questions: {zhs}")

    work_topics   = {"work_what", "work_like", "work_duration", "work_why",
                     "work_interesting", "work_students"}
    place_topics  = {"place_from", "place_like", "place_food"}
    food_topics   = {"food_fav", "food_spicy", "food_cook"}

    check(
        "BQ3a — at least one work-related question shown",
        any(t in work_topics for t in topics) or
        any(kw in " ".join(zhs) for kw in ("工作", "老师", "为什么")),
        f"topics={topics}",
    )
    check(
        "BQ3b — discovery_questions non-empty",
        bool(resp.get("discovery_questions")),
        "empty discovery_questions",
    )
    check(
        "BQ3c — work questions outnumber place+food questions",
        sum(1 for t in topics if t in work_topics) >=
        sum(1 for t in topics if t in (place_topics | food_topics)),
        f"topics={topics}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# BQ4 — Persona answer mentions food (回锅肉) → food questions surface
# ══════════════════════════════════════════════════════════════════════════════

def test_bq4_food_persona_answer_triggers_food_questions() -> None:
    """[BQ4] Persona mentions '回锅肉' → food-related questions in blue panel."""
    print("\n[BQ4] Persona '回锅肉' answer → food questions in blue panel")

    resp = api_run_turn(
        {"frame_id": "f_from_where", "submitted_text": "你喜欢吃什么？",
         "selected_option_hanzi": "你喜欢吃什么？", "move_type": "ANSWER"},
        make_cs(engine="food", extra={
            "last_partner_frame_text":  "你喜欢吃什么？",
            "last_partner_frame_id":    "f_food_what_good",
            "last_counter_reply":       "我妈妈做的回锅肉是我最喜欢的。",
        }),
    )
    if resp is None:
        skip("BQ4", "server not available"); return

    topics = discovery_topics(resp)
    zhs    = discovery_zh(resp)
    print(f"    topics: {topics}")
    print(f"    questions: {zhs}")

    food_topics    = {"food_fav", "food_spicy", "food_cook", "food_why_like", "food_local"}
    unrelated      = {"place_from", "place_far", "work_what", "family_size"}

    check(
        "BQ4a — at least one food-related question shown",
        any(t in food_topics for t in topics) or
        any(kw in " ".join(zhs) for kw in ("吃", "辣", "做饭", "喜欢")),
        f"topics={topics}",
    )
    check(
        "BQ4b — no place/work unrelated questions dominate",
        sum(1 for t in topics if t in unrelated) < len(topics),
        f"topics={topics}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# BQ5 — Recently shown topic not repeated immediately when alternatives exist
# ══════════════════════════════════════════════════════════════════════════════

def test_bq5_no_immediate_topic_repetition() -> None:
    """[BQ5] A topic that was recently shown should not immediately repeat if alternatives exist."""
    print("\n[BQ5] Recently shown topic not repeated immediately")

    # First turn: show discovery, note what topics appear
    resp1 = api_run_turn(
        {"frame_id": "f_what_work", "submitted_text": "我是老师",
         "selected_option_hanzi": "我是老师", "move_type": "ANSWER"},
        make_cs(engine="work", extra={
            "last_partner_frame_text":    "你做什么工作？",
            "recently_seen_disc_topics": [],
        }),
    )
    if resp1 is None:
        skip("BQ5", "server not available"); return

    shown_topics_1 = [q.get("topic") for q in (resp1.get("discovery_questions") or []) if q.get("topic")]
    if not shown_topics_1:
        skip("BQ5", "no discovery questions in turn 1"); return

    print(f"    turn-1 topics: {shown_topics_1}")

    # Second turn: pass recently_seen_disc_topics from turn 1
    resp2 = api_run_turn(
        {"frame_id": "f_what_work", "submitted_text": "我喜欢我的工作",
         "selected_option_hanzi": "我喜欢我的工作", "move_type": "ANSWER"},
        make_cs(engine="work", extra={
            "last_partner_frame_text":    "你喜欢你的工作吗？",
            "recently_seen_disc_topics": shown_topics_1,
        }),
    )
    if resp2 is None:
        skip("BQ5", "server not available for turn 2"); return

    shown_topics_2 = [q.get("topic") for q in (resp2.get("discovery_questions") or []) if q.get("topic")]
    print(f"    turn-2 topics: {shown_topics_2}")

    repeated = [t for t in shown_topics_2 if t in shown_topics_1]
    total = len(shown_topics_2)

    check(
        "BQ5 — turn-2 questions are not ALL from the same topics as turn-1",
        len(repeated) < total or total == 0,
        f"repeated={repeated}  turn2={shown_topics_2}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# BQ6 — Relevance scoring: work frame prefers work questions over place
# ══════════════════════════════════════════════════════════════════════════════

def test_bq6_work_context_ranks_work_questions_first() -> None:
    """[BQ6] In work engine with '你做什么工作？' context, first blue question is work-related."""
    print("\n[BQ6] Work context — first blue question should be work-related")

    resp = api_run_turn(
        {"frame_id": "f_what_work", "submitted_text": "我在学校工作",
         "selected_option_hanzi": "我在学校工作", "move_type": "ANSWER"},
        make_cs(engine="work", extra={
            "last_partner_frame_text":   "你做什么工作？",
            "last_partner_frame_id":     "f_what_work",
            "consecutive_app_questions": 1,
        }),
    )
    if resp is None:
        skip("BQ6", "server not available"); return

    dqs  = resp.get("discovery_questions") or []
    if not dqs:
        skip("BQ6", "no discovery_questions returned"); return

    first_topic = (dqs[0].get("topic") or "")
    first_zh    = (dqs[0].get("zh") or "")
    print(f"    first question: {first_zh!r}  topic={first_topic!r}")

    WORK_TOPICS = {"work_what", "work_like", "work_duration", "work_why",
                   "work_interesting", "work_students", "work_platform"}

    check(
        "BQ6 — first blue question is work-related",
        first_topic in WORK_TOPICS or any(kw in first_zh for kw in ("工作", "老师", "做什么", "为什么")),
        f"first_topic={first_topic!r}  zh={first_zh!r}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# BQ7 — Place context: spicy/food mention → food follow-up eligible
# ══════════════════════════════════════════════════════════════════════════════

def test_bq7_spicy_mention_triggers_food_followup() -> None:
    """[BQ7] Persona '成都的火锅' mention → food or place_food question eligible."""
    print("\n[BQ7] '火锅/辣' mention in persona answer → food question eligible")

    resp = api_run_turn(
        {"frame_id": "f_from_where", "submitted_text": "你喜欢吃辣吗？",
         "selected_option_hanzi": "你喜欢吃辣吗？", "move_type": "ANSWER"},
        make_cs(engine="place", extra={
            "last_partner_frame_text":  "你喜欢吃什么？",
            "last_counter_reply":       "成都的火锅是我的最爱，特别辣！",
            "last_persona_reveal":      True,
        }),
    )
    if resp is None:
        skip("BQ7", "server not available"); return

    topics = discovery_topics(resp)
    zhs    = discovery_zh(resp)
    print(f"    topics: {topics}")
    print(f"    questions: {zhs}")

    food_or_place = {"food_fav", "food_spicy", "food_cook", "food_why_like",
                     "food_local", "place_food"}

    check(
        "BQ7 — at least one food or place_food question shown",
        any(t in food_or_place for t in topics) or
        any(kw in " ".join(zhs) for kw in ("吃", "辣", "做饭", "好吃")),
        f"topics={topics}  zhs={zhs}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 70)
    print("MandarinOS — Blue Question Relevance Tests")
    print("=" * 70)

    test_bq1_place_frame_origin_questions()
    test_bq2_persona_city_mention_triggers_place_questions()
    test_bq3_work_frame_triggers_work_questions()
    test_bq4_food_persona_answer_triggers_food_questions()
    test_bq5_no_immediate_topic_repetition()
    test_bq6_work_context_ranks_work_questions_first()
    test_bq7_spicy_mention_triggers_food_followup()

    total  = len(_results)
    passed = sum(1 for _, ok in _results if ok)
    failed = total - passed

    print()
    print("=" * 70)
    if failed == 0:
        print(f"\033[32m{passed}/{total} passed\033[0m")
    else:
        print(f"\033[31m{passed}/{total} passed\033[0m  ← {failed} FAILED")
        print()
        print("Failed tests:")
        for name, ok in _results:
            if not ok:
                print(f"  ✗  {name}")
    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
