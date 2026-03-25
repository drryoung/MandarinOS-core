"""
Phase 11 — Alpha observation: simulate multi-turn conversations across all engines
and capture qualitative patterns for the conversational quality review.

Usage:
    python scripts/alpha_conversation_observer.py
Output:
    docs/reports/alpha_conversation_observation.md
"""

import json
import urllib.request
import urllib.error
from pathlib import Path
from collections import defaultdict

API = "http://localhost:8765/api/run_turn"
REPO = Path(__file__).resolve().parents[1]

# Simulated user answers keyed by frame id — realistic but minimal.
ANSWERS = {
    # identity
    "f_ask_you_name":             {"hanzi": "我叫李明", "meaning": "My name is Li Ming"},
    "f_ask_name_meaning":         {"hanzi": "我不太清楚", "meaning": "I'm not sure"},
    "p2_id_2":                    {"hanzi": "我觉得还不错", "meaning": "I think it's fine"},
    "p2_id_4":                    {"hanzi": "我喜欢我的名字", "meaning": "I like my name"},
    "p2_id_5":                    {"hanzi": "我的名字很普通", "meaning": "My name is quite common"},
    # place
    "f_from_where":               {"hanzi": "我是上海人", "meaning": "I'm from Shanghai"},
    "frame.location.live_question": {"hanzi": "我住在北京", "meaning": "I live in Beijing"},
    "f_place_like_there":         {"hanzi": "我很喜欢那里", "meaning": "I really like it there"},
    "p2_pl_1":                    {"hanzi": "我觉得生活很方便", "meaning": "I think life is convenient"},
    "p2_pl_2":                    {"hanzi": "有很多好吃的", "meaning": "There's lots of good food"},
    "p2_pl_3":                    {"hanzi": "我喜欢去公园", "meaning": "I like going to the park"},
    "p2_pl_4":                    {"hanzi": "还可以吧", "meaning": "It's alright I suppose"},
    # family
    "f_have_family":              {"hanzi": "有，我有家人", "meaning": "Yes, I have family"},
    "f_have_siblings":            {"hanzi": "我有一个弟弟", "meaning": "I have a younger brother"},
    "p2_fa_1":                    {"hanzi": "我们感情很好", "meaning": "We get along well"},
    "p2_fa_2":                    {"hanzi": "我每个月回家一次", "meaning": "I go home once a month"},
    "p2_fa_5":                    {"hanzi": "周末我们一起吃饭", "meaning": "We eat together on weekends"},
    # work
    "f_what_work":                {"hanzi": "我是老师", "meaning": "I'm a teacher"},
    "f_like_work":                {"hanzi": "我很喜欢我的工作", "meaning": "I really like my job"},
    "p2_wk_1":                    {"hanzi": "工作很忙但很有意思", "meaning": "It's busy but interesting"},
    "p2_wk_2":                    {"hanzi": "我每天工作八个小时", "meaning": "I work 8 hours a day"},
    "p2_wk_3":                    {"hanzi": "同事很友好", "meaning": "My colleagues are friendly"},
    "p2_wk_4":                    {"hanzi": "有时候有点累", "meaning": "Sometimes it's a bit tiring"},
    "p2_wk_5":                    {"hanzi": "我觉得很充实", "meaning": "I find it fulfilling"},
    # hobby
    "f_what_hobby":               {"hanzi": "我喜欢爬山", "meaning": "I like hiking"},
    "f_like_do_what":             {"hanzi": "我喜欢听音乐", "meaning": "I like listening to music"},
    "f_often_do":                 {"hanzi": "我经常去健身房", "meaning": "I often go to the gym"},
    "f_difficult_ma":             {"hanzi": "不太难", "meaning": "Not too difficult"},
    "f_recommend_ma":             {"hanzi": "当然，很推荐", "meaning": "Of course, I recommend it"},
    "f_weekend_do":               {"hanzi": "我周末出去走走", "meaning": "I go out for walks on weekends"},
    "f_like_chinese_culture":     {"hanzi": "我很喜欢中国文化", "meaning": "I really like Chinese culture"},
    "f_like_what":                {"hanzi": "我喜欢传统音乐", "meaning": "I like traditional music"},
    "f_collect_what":             {"hanzi": "我收集邮票", "meaning": "I collect stamps"},
    "p2_hb_1":                    {"hanzi": "我每周爬山", "meaning": "I hike every week"},
    "p2_hb_2":                    {"hanzi": "已经爬了两年了", "meaning": "For two years already"},
    "p2_hb_4":                    {"hanzi": "非常放松", "meaning": "Very relaxing"},
    "p2_hb_5":                    {"hanzi": "我会推荐给朋友", "meaning": "I'd recommend it to friends"},
    # travel
    "f_travel_where":             {"hanzi": "我去过日本", "meaning": "I've been to Japan"},
    "f_want_go_where":            {"hanzi": "我想去欧洲", "meaning": "I want to go to Europe"},
    "p2_tr_1":                    {"hanzi": "我去过很多地方", "meaning": "I've been to many places"},
    "p2_tr_2":                    {"hanzi": "日本是我最喜欢的", "meaning": "Japan is my favourite"},
    "p2_tr_3":                    {"hanzi": "那里很好玩", "meaning": "It was a lot of fun"},
    "p2_tr_4":                    {"hanzi": "旅行让我放松", "meaning": "Travel helps me relax"},
    # food
    "f_food_what_good":           {"hanzi": "有很多好吃的", "meaning": "Lots of good food"},
    "f_food_famous_dish":         {"hanzi": "小笼包很有名", "meaning": "Xiaolongbao are famous"},
    "f_food_tasty":               {"hanzi": "非常好吃", "meaning": "Very tasty"},
    "f_food_like_spicy":          {"hanzi": "我不太喜欢辣的", "meaning": "I don't like spicy food much"},
    "f_food_expensive":           {"hanzi": "还好，不太贵", "meaning": "OK, not too expensive"},
    # fallback
    "DEFAULT":                    {"hanzi": "还可以", "meaning": "It's alright"},
}


def post(payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req  = urllib.request.Request(API, data=data,
                                  headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def simulate_engine(engine: str, max_turns: int = 6) -> list:
    """
    Simulate up to max_turns in a single engine and return turn records.
    Each record captures: frame_id, frame_text_en, move_type, selection_source,
    phase11_source, turn_type, reaction_prefix, same_engine_chain.
    """
    cs = {
        "current_engine":         engine,
        "recent_frame_ids":       [],
        "exchange_count":         0,
        "same_engine_chain_count":0,
        "curiosity_depth":        0,
        "ask_chain_count":        0,
        "same_slot_chain_count":  0,
        "last_focus_slot":        "",
        "pending_listening_move": False,
        "listening_wait_turns":   0,
        "last_interest_level":    "low",
        "last_turn_was_answer":   False,
        "prefer_bridge":          False,
        "force_bridge":           False,
    }
    turns = []
    last_frame_id = None

    for t in range(max_turns):
        payload = {"next_question": True, "conversation_state": cs}
        try:
            r = post(payload)
        except Exception as e:
            turns.append({"error": str(e), "turn": t})
            break

        fid       = r.get("frame_id", "unknown")
        text_en   = r.get("frame_text_en", "")
        text      = r.get("frame_text", "")
        tt        = r.get("turn_type", "")
        chain     = r.get("same_engine_chain_count", 0)
        reaction  = "frame_text" in r and (
            r.get("system_note","") == "phase10.5 reaction_micro_layer"
        )
        mf        = r.get("move_type_filter", {})
        sel_src   = mf.get("selection_source", "")
        p11_src   = mf.get("phase11_selection_source", "")
        cur_mt    = mf.get("current_move_type", "")
        options   = [o.get("hanzi","") for o in r.get("options", [])
                     if isinstance(o, dict) and o.get("hanzi")]

        # Identify which engine the chosen frame belongs to
        r_engine = r.get("engine_id", engine)

        turns.append({
            "turn":       t + 1,
            "frame_id":   fid,
            "text":       text,
            "text_en":    text_en,
            "engine":     r_engine,
            "move_type":  cur_mt,    # last frame's move_type (for filter)
            "turn_type":  tt,
            "chain":      chain,
            "reaction":   reaction,
            "sel_src":    sel_src,
            "p11_src":    p11_src,
            "options":    options[:3],
            "bridged":    r_engine.lower() != engine.lower() if r_engine else False,
        })

        # Build next state (simulate user answer)
        answer_hanzi = (ANSWERS.get(fid) or ANSWERS["DEFAULT"])["hanzi"]
        answer_meaning = (ANSWERS.get(fid) or ANSWERS["DEFAULT"])["meaning"]

        cs = {
            "current_engine":          r_engine,
            "recent_frame_ids":        (cs["recent_frame_ids"] + [fid])[-12:],
            "exchange_count":          cs["exchange_count"] + 1,
            "same_engine_chain_count": chain,
            "curiosity_depth":         r.get("curiosity_depth", 0),
            "ask_chain_count":         cs.get("ask_chain_count", 0) + 1,
            "same_slot_chain_count":   r.get("same_slot_chain_count", 0),
            "last_focus_slot":         r.get("last_focus_slot", ""),
            "pending_listening_move":  r.get("pending_listening_move", False),
            "listening_wait_turns":    r.get("listening_wait_turns", 0),
            "last_interest_level":     r.get("interest_level", "low"),
            "last_turn_was_answer":    True,
            "prefer_bridge":           False,
            "force_bridge":            False,
            "last_answer": {
                "frame_id": fid,
                "hanzi":    answer_hanzi,
                "meaning":  answer_meaning,
            },
        }
        last_frame_id = fid

    return turns


def fmt_turn(t: dict) -> str:
    if "error" in t:
        return f"  turn {t['turn']}: ERROR — {t['error']}"
    bridge_tag = " [BRIDGE]" if t.get("bridged") else ""
    react_tag  = " [REACTION]" if t.get("reaction") else ""
    opts_str   = " / ".join(t["options"]) if t["options"] else "—"
    return (
        f"  T{t['turn']:02d} [{t['engine']:8}] {t['frame_id']:40} "
        f"mt={t['move_type']:12} tt={t['turn_type']:16} chain={t['chain']}"
        f"{bridge_tag}{react_tag}\n"
        f"         EN: {t['text_en']}\n"
        f"         opts: {opts_str}"
    )


def main():
    engines = ["identity", "place", "family", "work", "hobby", "travel", "food"]
    all_traces = {}

    print("Simulating conversation traces…")
    for eng in engines:
        print(f"  {eng}…", end=" ", flush=True)
        turns = simulate_engine(eng, max_turns=7)
        all_traces[eng] = turns
        print(f"{len(turns)} turns")

    # ── Analysis ─────────────────────────────────────────────────────────────

    issues = defaultdict(list)  # issue_type → list of (engine, turn_desc)

    for eng, turns in all_traces.items():
        q_turns   = [t for t in turns if "？" in t.get("text","") or "question" in t.get("turn_type","")]
        non_q_turns = [t for t in turns if t not in q_turns]
        bridge_turns = [t for t in turns if t.get("bridged")]
        react_turns  = [t for t in turns if t.get("reaction")]

        # 1. Unnatural loop chains — ≥3 consecutive question turns, no bridge/reaction between
        streak = 0
        max_streak = 0
        streak_start = None
        for t in turns:
            if "question" in t.get("turn_type","") or t.get("move_type") in ("LOOP","ASK","OPEN"):
                streak += 1
                if streak == 1:
                    streak_start = t
                if streak > max_streak:
                    max_streak = streak
            else:
                streak = 0
        if max_streak >= 3:
            issues["unnatural_loop_chain"].append(
                (eng, f"streak={max_streak} questions in a row (T{streak_start['turn'] if streak_start else '?'})")
            )

        # 2. Over-questioning — ratio of question turns to total turns
        q_ratio = len(q_turns) / len(turns) if turns else 0
        if q_ratio >= 0.85:
            issues["over_questioning"].append(
                (eng, f"{len(q_turns)}/{len(turns)} turns are questions ({q_ratio:.0%})")
            )

        # 3. Weak / absent reactions — no reaction in a sequence of ≥4 turns
        if len(turns) >= 4 and not react_turns:
            issues["absent_reaction"].append(
                (eng, f"0 reactions in {len(turns)} turns")
            )

        # 4. Reciprocity — check if blended 你呢 option appears
        rec_turns = [t for t in turns if any("你呢" in o for o in t.get("options", []))]
        if not rec_turns and len(turns) >= 3:
            issues["no_reciprocity"].append(
                (eng, "no 你呢 option appeared in any turn")
            )

        # 5. Abrupt bridge — bridge on turn ≤ 2 (moved away from engine too soon)
        for bt in bridge_turns:
            if bt["turn"] <= 2:
                issues["early_bridge"].append(
                    (eng, f"T{bt['turn']}: bridged to {bt['engine']} after only {bt['turn']-1} turns")
                )

        # 6. Flat / thin engine — few distinct move_types
        mts = {t.get("move_type") for t in turns if t.get("move_type")}
        if len(mts) <= 1 and len(turns) >= 3:
            issues["flat_engine"].append(
                (eng, f"only 1 distinct move_type seen across {len(turns)} turns: {mts}")
            )

    # ── Write report ─────────────────────────────────────────────────────────
    out = REPO / "docs" / "reports" / "alpha_conversation_observation.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Phase 11 — Alpha conversation quality observation",
        "",
        "Generated by `scripts/alpha_conversation_observer.py`.",
        "",
        "## Simulation method",
        "",
        "Seven engines simulated for up to 7 turns each, using realistic canned answers.",
        "State is correctly threaded turn-to-turn (recent, exchange_count, chain_count, etc.).",
        "Observations are classified into structural issue types.",
        "",
        "---",
        "",
        "## Turn-by-turn traces",
        "",
    ]

    for eng, turns in all_traces.items():
        lines.append(f"### {eng.capitalize()} engine")
        lines.append("")
        for t in turns:
            lines.append(fmt_turn(t))
            lines.append("")
        lines.append("---")
        lines.append("")

    # Issue summary
    ISSUE_LABELS = {
        "unnatural_loop_chain": "Structural grammar — Unnatural loop chain",
        "over_questioning":     "Structural grammar — Over-questioning (question ratio too high)",
        "absent_reaction":      "Selector — Absent reaction moments",
        "no_reciprocity":       "Selector — No reciprocity opportunity surfaced",
        "early_bridge":         "Selector — Early bridge (topic abandoned too quickly)",
        "flat_engine":          "Content sparsity — Flat/thin engine (single move_type dominates)",
    }

    lines += [
        "## Issue summary by type",
        "",
    ]

    total_issues = sum(len(v) for v in issues.values())
    if total_issues == 0:
        lines.append("No issues detected across all engines.")
    else:
        for itype, label in ISSUE_LABELS.items():
            cases = issues.get(itype, [])
            if not cases:
                continue
            lines += [
                f"### {label}",
                "",
            ]
            for eng, desc in cases:
                lines.append(f"- **{eng}**: {desc}")
            lines.append("")

    # Print to console too
    print()
    for itype, cases in issues.items():
        if cases:
            print(f"[{itype}]")
            for eng, desc in cases:
                print(f"  {eng}: {desc}")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()
