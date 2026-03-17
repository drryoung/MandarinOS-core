import json
import time
import urllib.request
import sys
import os


URL = "http://localhost:8765/api/run_turn"

try:
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def post(payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def pick_best_answer_option(turn: dict) -> dict:
    """
    Trace harness selection priority (stabilized for realism):
    1) blended reciprocity (answer + 你呢？) when present
    2) full-sentence answers (contains 。 or ！ and is not a question)
    3) semantically valid minimal answers for common asks (heuristics per frame)
    Avoid: single-word fragments when sentence options exist; avoid picking questions as answers.
    """
    opts = turn.get("options") or []
    if not isinstance(opts, list) or not opts:
        return {"hanzi": "", "meaning": ""}

    frame_id = (turn.get("frame_id") or "").strip()

    _INTERROGATIVES = {"怎么样", "哪里", "哪些", "为什么", "谁", "什么时候", "怎么"}
    _TIME_WORDS = {"多久", "去年", "最近", "现在"}
    _GOOD_SHORT_ANSWERS = {"喜欢", "不太喜欢", "挺好的。", "有点忙。", "好吃", "好玩", "方便"}

    # Harness-only: hard-block legacy fragments for frames that have valid sentence/short options.
    _FRAME_BLOCKED_FRAGMENTS = {
        "p2_id_2": {"怎么叫", "爱好", "哪些"},
        "p2_pl_2": {"好玩", "哪些"},
        "p2_pl_4": {"开始", "多久"},
        "p2_fa_2": {"多久", "一般", "什么"},
    }

    def is_question(s: str) -> bool:
        return "？" in s or s.endswith("?")

    def is_sentence(s: str) -> bool:
        return ("。" in s) or ("！" in s) or (s.endswith(".") or s.endswith("!"))

    def is_valid_answer(hanzi: str) -> bool:
        return is_sentence(hanzi) or (hanzi in _GOOD_SHORT_ANSWERS) or ("喜欢" in hanzi and len(hanzi) <= 6)

    # For blocklist frames: hard-block legacy fragments so trace never selects them.
    blocked_for_frame = _FRAME_BLOCKED_FRAGMENTS.get(frame_id) or set()
    has_valid_option = any(
        isinstance(o, dict) and is_valid_answer((o.get("hanzi") or "").strip()) and not is_question((o.get("hanzi") or ""))
        for o in opts
    ) if blocked_for_frame else False

    def score(opt: dict) -> int:
        if not isinstance(opt, dict):
            return -10_000
        hanzi = (opt.get("hanzi") or "").strip()
        if not hanzi:
            return -10_000
        # never choose the question itself as an answer
        if is_question(hanzi):
            # For blocklist frames with valid options, never pick question text as answer.
            if has_valid_option and blocked_for_frame:
                return -10_000
            return -9_000

        # Harness-only: hard-block legacy fragments for p2_id_2, p2_pl_2, p2_pl_4, p2_fa_2 when valid options exist.
        if has_valid_option and hanzi in blocked_for_frame:
            return -10_000

        # Filter: interrogatives/time fragments should not answer declarative questions.
        # Allow them only when the question explicitly calls for them.
        question_text = (turn.get("frame_text") or "").strip()
        expects_time = any(k in question_text for k in ("多久", "几点", "什么时候"))
        expects_where = any(k in question_text for k in ("哪里",))
        expects_which = any(k in question_text for k in ("哪些", "什么"))
        # Interrogatives as standalone answers are almost always wrong.
        if hanzi in _INTERROGATIVES and not (expects_where or expects_which):
            return -8_000
        if hanzi in _TIME_WORDS and not expects_time:
            return -8_000
        if hanzi in {"哪些"} and not expects_which:
            return -8_000

        sc = 0
        if opt.get("card_id") == "__blended_reciprocate":
            sc += 10_000
        if is_sentence(hanzi):
            sc += 3_000
        # prefer gold if it is a sentence/minimal answer
        if opt.get("is_gold"):
            sc += 300
        # penalize fragmentary single-token-ish answers
        if len(hanzi) <= 2 and not is_sentence(hanzi):
            sc -= 500
            if hanzi not in _GOOD_SHORT_ANSWERS and ("喜欢" not in hanzi):
                sc -= 700

        # frame-specific semantic heuristics
        if frame_id == "f_ask_you_name":
            if hanzi.startswith("我叫"):
                sc += 2_000
        elif frame_id == "f_from_where":
            if hanzi.startswith("我是") and "人" in hanzi:
                sc += 2_000
        elif frame_id == "frame.location.live_question":
            if "住在" in hanzi:
                sc += 2_000
        elif frame_id == "f_what_work":
            if hanzi.startswith("我是"):
                sc += 1_500
        elif frame_id == "f_food_what_good":
            if hanzi.startswith("有很多"):
                sc += 1_500
        elif frame_id == "f_place_like_there":
            if "喜欢" in hanzi:
                sc += 1_500
        elif frame_id == "f_like_work":
            if "喜欢" in hanzi:
                sc += 1_500
        elif frame_id in ("p2_pl_1",):
            # city-life: prefer sentence-like assessments
            if is_sentence(hanzi):
                sc += 1_000
        elif frame_id in ("p2_pl_3",):
            if "喜欢" in hanzi:
                sc += 1_000
        # Blocklist frames: prefer the sentence-level options we added.
        if frame_id == "p2_id_2" and ("叫我" in hanzi or "叫" in hanzi) and is_sentence(hanzi):
            sc += 1_500
        elif frame_id == "p2_pl_2" and (is_sentence(hanzi) or "火锅" in hanzi or "饺子" in hanzi or "包子" in hanzi):
            sc += 1_500
        elif frame_id == "p2_pl_4" and ("方便" in hanzi and is_sentence(hanzi)):
            sc += 1_500
        elif frame_id == "p2_fa_2" and is_sentence(hanzi):
            sc += 1_500
        return sc

    # Harness-only: for blocklist frames, exclude blocked fragments and question-as-answer so trace is a clean realism signal.
    if blocked_for_frame:
        def allowed(o: dict) -> bool:
            h = (o.get("hanzi") or "").strip()
            if is_question(h):
                return False
            if h in blocked_for_frame:
                return False
            return True
        opts = [o for o in opts if isinstance(o, dict) and allowed(o)]
    if not opts and blocked_for_frame:
        return {"hanzi": "我不知道。", "meaning": "I don't know."}
    if not opts:
        opts = turn.get("options") or []

    # If any sentence answers exist, strongly avoid fragments.
    has_sentence = any(isinstance(o, dict) and is_sentence((o.get("hanzi") or "")) and not is_question((o.get("hanzi") or "")) for o in opts)
    best = None
    best_sc = -10_000
    for o in opts:
        if not isinstance(o, dict):
            continue
        s = score(o)
        hanzi = (o.get("hanzi") or "").strip()
        if has_sentence and hanzi and (len(hanzi) <= 2) and not ("喜欢" in hanzi) and not is_sentence(hanzi):
            s -= 2_000
        if s > best_sc:
            best_sc = s
            best = o
    return best if isinstance(best, dict) else {"hanzi": "", "meaning": ""}


def main():
    session_id = f"trace_{int(time.time())}"
    cs = {
        "session_id": session_id,
        "current_engine": "identity",
        "last_partner_frame_id": None,
        "recent_frame_ids": [],
        "learner_id": "trace_learner",
        "persona_id": "zhang_wei",
        "exchange_count": 0,
        "curiosity_depth": 0,
        "ask_chain_count": 0,
        "last_partner_turn_type": "question",
    }

    trace = []
    fallback_heavy = []
    weak_loops = []

    def next_question(last_turn_was_answer: bool = False, last_answer: dict | None = None) -> dict:
        if last_turn_was_answer:
            cs["last_turn_was_answer"] = True
            cs["last_answer"] = last_answer or {}
        else:
            cs.pop("last_turn_was_answer", None)
            cs.pop("last_answer", None)
        payload = {
            "env": "dev",
            "turn_uid": f"py_{int(time.time() * 1000)}",
            "next_question": True,
            "conversation_state": cs,
        }
        data = post(payload)
        # update cs
        cs["current_engine"] = data.get("engine_id", cs["current_engine"])
        cs["last_partner_frame_id"] = data.get("frame_id")
        cs["recent_frame_ids"] = (cs.get("recent_frame_ids") or []) + [data.get("frame_id")]
        cs["last_partner_turn_type"] = data.get("turn_type", "question")
        # Counters: mimic ui/app.js roughly
        if cs["last_partner_turn_type"] == "loop_question":
            cs["curiosity_depth"] = min(int(cs.get("curiosity_depth") or 0) + 1, 2)
            cs["ask_chain_count"] = 0
        elif cs["last_partner_turn_type"] == "question":
            cs["ask_chain_count"] = int(cs.get("ask_chain_count") or 0) + 1
            cs["curiosity_depth"] = 0
        else:
            cs["ask_chain_count"] = 0
        return data

    # Run N partner questions (each followed by one user answer).
    N = 10
    q = next_question()
    for _ in range(N):
        # partner turn
        trace.append(
            {
                "role": "partner",
                "turn_type": q.get("turn_type"),
                "frame_id": q.get("frame_id"),
                "text": q.get("frame_text"),
                "probe_offer": bool(q.get("probe_offer")),
                "probe_options": [p.get("hanzi") for p in (q.get("probe_options") or []) if isinstance(p, dict)],
            }
        )
        if q.get("reaction_used_fallback"):
            fallback_heavy.append({"frame_id": q.get("frame_id"), "text": q.get("frame_text")})
        if q.get("weak_loop_encountered"):
            weak_loops.append({"frame_id": q.get("weak_loop_frame_id"), "text": q.get("frame_text")})

        # user answer
        opt = pick_best_answer_option(q)
        user_text = (opt.get("hanzi") or "").strip() or "我不知道。"
        trace.append({"role": "user", "answered_frame_id": q.get("frame_id"), "text": user_text})
        cs["exchange_count"] = int(cs.get("exchange_count") or 0) + 1

        last_answer = {
            "frame_id": q.get("frame_id"),
            "selected_option_hanzi": user_text,
            "selected_option_meaning": opt.get("meaning"),
        }

        # next partner question (after user answer)
        q = next_question(True, last_answer)

    print("=== POST-IMPLEMENTATION TRACE ===")
    for item in trace:
        if item["role"] == "partner":
            line = f"[partner] ({item.get('turn_type')}) {item.get('frame_id')}: {item.get('text')}"
            print(line)
            if item.get("probe_offer"):
                print("  probes:", item.get("probe_options"))
        else:
            print(f"[user] (answer to {item.get('answered_frame_id')}): {item.get('text')}")

    print("\n=== FALLBACK-HEAVY MOMENTS ===")
    if not fallback_heavy:
        print("(none)")
    else:
        for f in fallback_heavy:
            print("-", f["frame_id"], "→", f["text"])

    print("\n=== WEAK LOOP FRAMES ENCOUNTERED ===")
    if not weak_loops:
        print("(none)")
    else:
        for w in weak_loops:
            print("-", w["frame_id"], "→", w["text"])


if __name__ == "__main__":
    main()

