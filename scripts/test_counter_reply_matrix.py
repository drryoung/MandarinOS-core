#!/usr/bin/env python3
"""
Pass 1: Question × Persona Coverage Matrix
Sends each test question to the live server as a `last_answer` payload and
records whether a counter_reply came back, what it says, and any gaps.

Usage:
  python scripts/test_counter_reply_matrix.py
  python scripts/test_counter_reply_matrix.py --persona xiaoming
  python scripts/test_counter_reply_matrix.py --all-personas

Server must be running at http://localhost:8765
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

# Force UTF-8 output on Windows terminals that default to cp1252.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

URL = "http://localhost:8765/api/run_turn"

# ── Test cases ──────────────────────────────────────────────────────────────
# Each entry: (group, id, question, engine_hint, expect_reply, note)
#   expect_reply: True  = should get counter_reply
#                 False = should NOT (plain answer, no question detected)
#                 None  = graceful deflect expected (reply but generic)
TEST_CASES = [
    # Group A — Detection boundary
    # Use real frame IDs so _persona_reply_for_ni_ne can look up the engine correctly.
    ("A", "A1", "你呢？",               "identity", True,  "bare 你呢 | frame: f_ask_you_name"),
    ("A", "A2", "我是新西兰人，你呢？", "place",    True,  "embedded 你呢 | frame: f_from_where"),
    ("A", "A3", "你做什么工作？",       "work",     True,  "direct question with？"),
    ("A", "A4", "你是做什么的",         "work",     True,  "no ？ — should still detect"),
    ("A", "A5", "有意思，你呢",         "work",     True,  "embedded 你呢 | frame: f_what_work"),
    ("A", "A6", "生活不错",             "place",    False, "plain answer — must NOT fire"),

    # Group B — Canonical mirror questions (exact match to bank)
    ("B", "B1",  "你叫什么名字？",         "identity", True, "identity/name direct"),
    ("B", "B2",  "你的名字是什么意思？",   "identity", True, "name_meaning → first clause"),
    ("B", "B3",  "谁给你取的名字？",       "identity", True, "name_giver → nth clause"),
    ("B", "B4",  "你是哪里人？",           "place",    True, "place_from → first clause"),
    ("B", "B5",  "你做什么工作？",         "work",     True, "work_what → first clause"),
    ("B", "B6",  "你做这份工作多久了？",   "work",     True, "work_duration → nth clause"),
    ("B", "B7",  "你家里有几个人？",       "family",   True, "family_size → first clause"),
    ("B", "B8",  "你有兄弟姐妹吗？",       "family",   True, "family_siblings → nth clause"),
    ("B", "B9",  "你喜欢做什么？",         "hobby",    True, "hobby_what → first clause"),
    ("B", "B10", "你去过哪里？",           "travel",   True, "travel_where → first clause"),
    ("B", "B11", "你最喜欢吃什么？",       "food",     True, "food_fav → first clause"),

    # Group C — Paraphrases (fuzzy match)
    ("C", "C1", "你是做什么的？",            "work",   True, "work paraphrase"),
    ("C", "C2", "你老家在哪儿？",            "place",  True, "place paraphrase"),
    ("C", "C3", "你妈妈在哪儿？",            "family", True, "family depth — may deflect"),
    ("C", "C4", "你在哪个平台发内容？",      "work",   True, "work_platform paraphrase"),
    ("C", "C5", "你最难忘的旅行是哪次？",    "travel", True, "travel_memorable paraphrase"),
    ("C", "C6", "你吉他学多久了？",          "hobby",  True, "hobby_duration paraphrase"),

    # Group D — Out of scope (should deflect gracefully, not crash)
    ("D", "D1", "你喜欢什么颜色？",         "identity", None, "out-of-scope → graceful"),
    ("D", "D2", "你有没有宠物？",           "identity", None, "out-of-scope → graceful"),
    ("D", "D3", "你多大了？",              "identity", None, "age → specific deflect"),
    ("D", "D4", "你结婚了吗？",            "family",   None, "marriage → graceful"),
    ("D", "D5", "你的电话号码是什么？",     "identity", None, "private info → graceful"),
]

# Group E handled separately — same questions, different persona
GROUP_E = [
    ("E", "E1", "你做什么工作？",   "work",   True, "work_what — xiaoming"),
    ("E", "E2", "你家里有几个人？", "family", True, "family_size — xiaoming"),
    ("E", "E3", "你妈妈在哪儿？",  "family", True, "family depth — xiaoming"),
]


_ENGINE_TO_FRAME = {
    "identity": "f_ask_you_name",
    "place":    "f_from_where",
    "work":     "f_what_work",
    "family":   "f_have_family",
    "hobby":    "f_what_hobby",
    "travel":   "f_travel_where",
    "food":     "f_food_what_good",
}


def call_server(question: str, engine: str, persona_id: str) -> dict:
    # Note: server reads last_answer from conversation_state, not top-level payload.
    # Use real frame IDs so _persona_reply_for_ni_ne can look up the engine correctly.
    frame_id = _ENGINE_TO_FRAME.get(engine, f"f_{engine}_frame")
    payload = {
        "env": "dev",
        "turn_uid": "matrix_test_" + question[:8],
        "next_question": True,
        "persona_id": persona_id,
        "conversation_state": {
            "session_id": "matrix_test",
            "current_engine": engine,
            "last_partner_frame_id": frame_id,
            "recent_frame_ids": [],
            "last_turn_was_answer": True,
            "last_answer": {
                "submitted_text": question,
                "frame_id": frame_id,
                "selected_option_hanzi": "",
            },
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"_error": str(e)}


def assess(expect_reply, got_reply: str) -> str:
    """Return a status symbol for the result."""
    has = bool(got_reply)
    if expect_reply is True:
        return "✓" if has else "✗ MISSING"
    if expect_reply is False:
        return "✓" if not has else "✗ SPURIOUS"
    # None = deflect expected — just check it's non-empty
    return "✓ (deflect)" if has else "✗ EMPTY"


def run_matrix(cases, persona_id: str):
    sep = "-" * 100
    print(sep)
    print(f"{'ID':<5} {'Q':<32} {'Expect':<10} {'Status':<16} {'counter_reply'}")
    print(sep)
    gaps = []
    for group, qid, question, engine, expect, note in cases:
        data = call_server(question, engine, persona_id)
        if "_error" in data:
            print(f"{'':>5} SERVER ERROR: {data['_error']}")
            sys.exit(1)
        reply = (data.get("counter_reply") or "").strip()
        status = assess(expect, reply)
        expect_label = {True: "reply", False: "silent", None: "deflect"}.get(expect, "?")
        # Truncate reply for display
        display_reply = (reply[:60] + "…") if len(reply) > 60 else reply
        flag = "  ← GAP" if "✗" in status else ""
        print(f"{qid:<5} {question:<32} {expect_label:<10} {status:<16} {display_reply}{flag}")
        if note:
            print(f"{'':>5} [{note}]")
        if "✗" in status:
            gaps.append((qid, question, expect_label, reply, note))
    print(sep)
    return gaps


REPORT_PATH = "docs/reports/counter_reply_matrix_report.md"


def run_matrix_to_report(cases, persona_id: str, out_lines: list):
    out_lines.append(f"\n### Persona: {persona_id}\n")
    out_lines.append(f"| ID | Question | Expect | Status | counter_reply |")
    out_lines.append(f"|---|---|---|---|---|")
    gaps = []
    for group, qid, question, engine, expect, note in cases:
        data = call_server(question, engine, persona_id)
        if "_error" in data:
            out_lines.append(f"**SERVER ERROR**: {data['_error']}")
            sys.exit(1)
        reply = (data.get("counter_reply") or "").strip()
        status = assess(expect, reply)
        expect_label = {True: "reply", False: "silent", None: "deflect"}.get(expect, "?")
        flag = " ← GAP" if "✗" in status else ""
        out_lines.append(f"| {qid} | {question} | {expect_label} | {status}{flag} | {reply} |")
        if "✗" in status:
            gaps.append((qid, question, expect_label, reply, note))
    return gaps


def main():
    parser = argparse.ArgumentParser(description="Run question coverage matrix against live server.")
    parser.add_argument("--persona", default="xiaoyun", help="Primary persona ID (default: xiaoyun)")
    parser.add_argument("--all-personas", action="store_true", help="Also run Group E against xiaoming")
    parser.add_argument("--report", action="store_true", help="Write UTF-8 markdown report to docs/reports/")
    args = parser.parse_args()

    total = len(TEST_CASES) + (len(GROUP_E) if args.all_personas else 0)
    all_gaps = []
    out_lines = [
        f"# Pass 1 — Counter-Reply Coverage Matrix",
        f"",
        f"Persona: **{args.persona}**  |  Server: {URL}",
        f"",
    ]

    # ── Primary run ─────────────────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  PASS 1 - QUESTION x PERSONA COVERAGE MATRIX")
    print(f"  Persona: {args.persona}   Server: {URL}")
    print(f"{'='*100}\n")

    all_gaps += run_matrix(TEST_CASES, args.persona)
    all_gaps_report = run_matrix_to_report(TEST_CASES, args.persona, out_lines)

    # ── Group E — cross-persona ──────────────────────────────────────────────
    if args.all_personas:
        print(f"\n  Group E - cross-persona check (xiaoming)\n")
        all_gaps += run_matrix(GROUP_E, "xiaoming")
        all_gaps_report += run_matrix_to_report(GROUP_E, "xiaoming", out_lines)

    # ── Gap summary ─────────────────────────────────────────────────────────
    print(f"\n  SUMMARY: {total} tests run, {len(all_gaps)} gap(s)\n")
    if all_gaps:
        print("  GAPS TO FIX:")
        for qid, q, expect, got, note in all_gaps:
            got_display = f'got: "{got[:50]}"' if got else "got: (empty)"
            print(f"    {qid:<5} [{expect}] {q}  - {note}  {got_display}")
    else:
        print("  All tests passed.")
    print()

    out_lines.append(f"\n## Summary\n\n{total} tests, {len(all_gaps_report)} gap(s).")
    if all_gaps_report:
        out_lines.append("\n## Gaps\n")
        for qid, q, expect, got, note in all_gaps_report:
            out_lines.append(f"- **{qid}** `{q}` [{expect}] — {note} — got: `{got[:60] if got else '(empty)'}`")

    # ── Write report ─────────────────────────────────────────────────────────
    import pathlib
    report_path = pathlib.Path(REPORT_PATH)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"  Report written to: {report_path.resolve()}")


if __name__ == "__main__":
    main()
