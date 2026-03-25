#!/usr/bin/env python3
"""
Phase 10.7 — Stage 1–4: propose move_type and allowed_response_roles for every frame.

Rules (from MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt):
- Canonical values: OPEN, ASK, ANSWER, REACTION, EXTEND, LOOP, RECIPROCITY, REPAIR, BRIDGE, CLOSE
- Response roles:   SAFE, EXPAND, REPAIR, RECIPROCITY
- Do NOT rewrite frame text. Surface ambiguity. Use confidence labels.
- ONE primary function only. Conversational role beats grammar.

Run from repo root:
  python scripts/propose_move_type_tags.py

Writes:
  docs/reports/move_type_tagging_audit.md
  data/move_type_tags.proposed.json
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs" / "reports" / "move_type_tagging_audit.md"
JSON_PATH = ROOT / "data" / "move_type_tags.proposed.json"

# ---------------------------------------------------------------------------
# Transition reference (mirrors move_type_transitions.json — for the report).
# ---------------------------------------------------------------------------
TRANSITIONS = {
    "OPEN":        ["ANSWER", "REACTION", "RECIPROCITY"],
    "ASK":         ["ANSWER", "REPAIR"],
    "ANSWER":      ["REACTION", "LOOP", "RECIPROCITY", "BRIDGE", "CLOSE"],
    "REACTION":    ["LOOP", "RECIPROCITY", "BRIDGE", "CLOSE"],
    "EXTEND":      ["REACTION", "LOOP", "RECIPROCITY", "BRIDGE", "CLOSE"],
    "LOOP":        ["ANSWER", "REPAIR"],
    "RECIPROCITY": ["ANSWER", "REPAIR"],
    "REPAIR":      ["ASK", "ANSWER", "REACTION"],
    "BRIDGE":      ["ASK", "OPEN", "REACTION"],
    "CLOSE":       [],
}

# ---------------------------------------------------------------------------
# Per-frame tagging rules (hand-authored, based on text + engine + speaker).
# confidence: high / medium / low
# ---------------------------------------------------------------------------
FRAME_TAGS: dict[str, dict] = {
    # ── IDENTITY ──────────────────────────────────────────────────────────
    "frame.greeting.hello": {
        "move_type": "OPEN",
        "confidence": "high",
        "reason": "Greeting initiates the identity exchange",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["ANSWER", "REACTION"],
    },
    "frame.greeting.hello_reply": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User reply to greeting",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": ["REACTION", "RECIPROCITY"],
    },
    "f_ask_you_name": {
        "move_type": "OPEN",
        "confidence": "high",
        "reason": "First real question; opens identity lane",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "frame.identity.name": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User gives their name in response to OPEN",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "RECIPROCITY"],
    },
    "f_you_ne": {
        "move_type": "RECIPROCITY",
        "confidence": "high",
        "reason": "你呢？ = classic reciprocity move",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["ANSWER", "REPAIR"],
    },
    "f_partner_name": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "Partner gives their name",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "f_thanks": {
        "move_type": "REACTION",
        "confidence": "medium",
        "reason": "Polite acknowledgement; could also be CLOSE",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": ["RECIPROCITY", "BRIDGE", "CLOSE"],
    },
    "f_no_problem": {
        "move_type": "REACTION",
        "confidence": "high",
        "reason": "不客气 = acknowledgement, no new info",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": ["BRIDGE", "CLOSE"],
    },
    "f_nice_to_meet": {
        "move_type": "REACTION",
        "confidence": "high",
        "reason": "Social reaction after name exchange",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": ["BRIDGE", "ASK"],
    },
    "f_ask_name_meaning": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Deeper curiosity about name — LOOP on identity topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "frame.identity.name_meaning": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User answers name-meaning question",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "RECIPROCITY", "BRIDGE"],
    },
    "p2_id_1": {
        "move_type": "EXTEND",
        "confidence": "high",
        "reason": "User extends with explanation about name meaning",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP", "RECIPROCITY"],
    },
    "p2_id_2": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Curiosity follow-up: what do people call you — same identity topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_id_3": {
        "move_type": "EXTEND",
        "confidence": "medium",
        "reason": "User extends identity with personality description",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "RECIPROCITY"],
    },
    "p2_id_4": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Opinion question on name — deeper curiosity on identity topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_id_5": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Meaning/significance of name — loop on identity",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },

    # ── PLACE ─────────────────────────────────────────────────────────────
    "f_from_where": {
        "move_type": "OPEN",
        "confidence": "high",
        "reason": "你是哪里人？ opens the place lane",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "frame.identity.nationality": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User answers where they are from",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "frame.location.live_question": {
        "move_type": "ASK",
        "confidence": "high",
        "reason": "Distinct follow-up: where do you live now (not same as origin)",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "frame.location.live": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states current city",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP", "RECIPROCITY"],
    },
    "f_place_reaction": {
        "move_type": "REACTION",
        "confidence": "high",
        "reason": "很好！ = acknowledgement, no new info",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": ["LOOP", "RECIPROCITY", "BRIDGE"],
    },
    "f_place_like_there": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Curiosity follow-up on place — do you like it there?",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_place_like_yes": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User confirms they like the place",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "p2_pl_1": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Opinion on city life — deeper curiosity on place topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_pl_2": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "What good food is in your city — loop on place",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_pl_3": {
        "move_type": "LOOP",
        "confidence": "medium",
        "reason": "Do you usually go to X — loop on place; could also be ASK if new venue",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_pl_4": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Is it convenient? — loop on city life topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_pl_5": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "Partner or user gives opinion on city — answer/extend",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },

    # ── FAMILY ────────────────────────────────────────────────────────────
    "f_have_family": {
        "move_type": "OPEN",
        "confidence": "high",
        "reason": "你有家人吗？ opens the family lane",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_yes_have_family": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User confirms having family",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "f_have_siblings": {
        "move_type": "ASK",
        "confidence": "high",
        "reason": "Distinct family follow-up: siblings",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_have_brother": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states sibling",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "f_have_sister": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states sibling",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "p2_fa_1": {
        "move_type": "ASK",
        "confidence": "high",
        "reason": "Do you live with family — new family dimension",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_fa_2": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "How often do you see family — deeper loop on family topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_fa_3": {
        "move_type": "EXTEND",
        "confidence": "high",
        "reason": "User extends with relationship detail",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "p2_fa_4": {
        "move_type": "EXTEND",
        "confidence": "medium",
        "reason": "Partner extends with family detail; could also be REACTION",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "p2_fa_5": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Weekends with family — deeper curiosity on family topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },

    # ── WORK ──────────────────────────────────────────────────────────────
    "f_what_work": {
        "move_type": "OPEN",
        "confidence": "high",
        "reason": "你做什么工作？ opens the work lane",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_i_am_job": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states job",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "f_like_work": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Do you like your job — curiosity follow-up on work topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "frame.opinion.like": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User affirms they like it",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP", "RECIPROCITY"],
    },
    "p2_wk_1": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Why do you like this job — deeper loop on work topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_wk_2": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Is the job hard — loop on work topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_wk_3": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Hardest part — deeper loop on work topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_wk_4": {
        "move_type": "LOOP",
        "confidence": "medium",
        "reason": "Pay question — loop on work; could feel like a new dimension",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_wk_5": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Would you recommend it — loop/opinion on work topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },

    # ── HOBBY ─────────────────────────────────────────────────────────────
    "f_what_hobby": {
        "move_type": "OPEN",
        "confidence": "high",
        "reason": "你有什么爱好？ opens the hobby lane",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_i_like_hobby": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states hobby",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP", "RECIPROCITY"],
    },
    "f_weekend_do": {
        "move_type": "ASK",
        "confidence": "high",
        "reason": "Weekend activity — new temporal dimension on hobby/life",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_weekend_rest": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User answers weekend activity",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "f_weekend_hobby": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User extends with weekend activity",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "f_like_do_what": {
        "move_type": "ASK",
        "confidence": "medium",
        "reason": "What do you like to do — could be OPEN or LOOP; classifying as ASK because may bridge from another engine",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_often_do": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "你常做吗？ — curiosity follow-up on same hobby",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_difficult_ma": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "难吗？ — deeper curiosity on same hobby topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_recommend_ma": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "你推荐吗？ — opinion loop on hobby",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_like_chinese_culture": {
        "move_type": "ASK",
        "confidence": "medium",
        "reason": "Chinese culture — new sub-topic within hobby; could be LOOP if following cultural hobby answer",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_like_what": {
        "move_type": "ASK",
        "confidence": "medium",
        "reason": "Generic 你喜欢什么 — broad; could be OPEN if first question",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_i_like_cultural": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User answers cultural hobby",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "f_collect_what": {
        "move_type": "LOOP",
        "confidence": "medium",
        "reason": "Collecting — deeper hobby curiosity; could be ASK if not preceded by hobby topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_i_collect": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states collection",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "p2_hb_1": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "When did you start — deeper curiosity on hobby",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_hb_2": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Why do you like it — deeper loop on hobby",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_hb_3": {
        "move_type": "EXTEND",
        "confidence": "high",
        "reason": "User/partner adds opinion about hobby",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "p2_hb_4": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Is hobby difficult — loop on hobby",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_hb_5": {
        "move_type": "LOOP",
        "confidence": "medium",
        "reason": "Biggest achievement — deeper hobby loop; could be BRIDGE to wider life topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },

    # ── TRAVEL ────────────────────────────────────────────────────────────
    "f_travel_where": {
        "move_type": "OPEN",
        "confidence": "high",
        "reason": "你去过哪里？ opens the travel lane",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_been_to_place": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states places visited",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP", "RECIPROCITY"],
    },
    "f_want_go_where": {
        "move_type": "ASK",
        "confidence": "high",
        "reason": "Future travel dimension — new aspect, not just deeper on same",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_want_go_place": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states travel wish",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "p2_tr_1": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Which countries — deeper travel loop",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_tr_2": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Where do you like best — loop on travel topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_tr_3": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "What is fun there — loop on specific destination",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_tr_4": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Opinion on that trip — loop on travel",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_tr_5": {
        "move_type": "EXTEND",
        "confidence": "high",
        "reason": "Most memorable place — user extends travel narrative",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP", "BRIDGE"],
    },

    # ── FOOD ──────────────────────────────────────────────────────────────
    "f_food_what_good": {
        "move_type": "OPEN",
        "confidence": "high",
        "reason": "那儿有什么好吃的 opens the food lane (often follows place)",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_food_there_is": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states local dish",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "f_food_famous_dish": {
        "move_type": "LOOP",
        "confidence": "high",
        "reason": "Most famous dish — deeper loop on food/place topic",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_food_famous_answer": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states famous dish",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "f_food_like_spicy": {
        "move_type": "ASK",
        "confidence": "high",
        "reason": "New food dimension: spice preference",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_food_tasty": {
        "move_type": "LOOP",
        "confidence": "medium",
        "reason": "Tasty opinion — loop on food; confidence medium because could also be REACTION",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "f_food_expensive": {
        "move_type": "LOOP",
        "confidence": "medium",
        "reason": "Price question — loop on food topic; could be new dimension",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },

    # ── LIFE (plans, opinions, stories) ───────────────────────────────────
    "p2_pln_1": {
        "move_type": "ASK",
        "confidence": "high",
        "reason": "Plans question — new topic dimension",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_pln_2": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User states plan",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "p2_pln_3": {
        "move_type": "RECIPROCITY",
        "confidence": "medium",
        "reason": "When shall we meet — reciprocal / close; could also be CLOSE",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["ANSWER", "CLOSE"],
    },
    "p2_pln_4": {
        "move_type": "EXTEND",
        "confidence": "medium",
        "reason": "Suggest going together — extends plan; could be CLOSE if final",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": ["ANSWER", "CLOSE"],
    },
    "p2_pln_5": {
        "move_type": "CLOSE",
        "confidence": "high",
        "reason": "那我们…见 — schedules farewell, closes exchange",
        "allowed_response_roles": ["SAFE"],
        "default_next_move_types": [],
    },
    "p2_op_1": {
        "move_type": "ASK",
        "confidence": "medium",
        "reason": "Opinion on 'this' — generic; could be LOOP if in context",
        "allowed_response_roles": ["SAFE", "EXPAND", "REPAIR"],
        "default_next_move_types": ["ANSWER"],
    },
    "p2_op_3": {
        "move_type": "ANSWER",
        "confidence": "high",
        "reason": "User gives positive opinion",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "RECIPROCITY"],
    },
    "p2_op_4": {
        "move_type": "EXTEND",
        "confidence": "high",
        "reason": "User explains why they like it",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "p2_st_1": {
        "move_type": "EXTEND",
        "confidence": "high",
        "reason": "Yesterday I … — user extends with story",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP"],
    },
    "p2_st_2": {
        "move_type": "EXTEND",
        "confidence": "high",
        "reason": "Continues story narrative",
        "allowed_response_roles": ["SAFE", "EXPAND"],
        "default_next_move_types": ["REACTION", "LOOP", "BRIDGE"],
    },
}

# ---------------------------------------------------------------------------
# Load all frames
# ---------------------------------------------------------------------------

def load_frames() -> list[dict]:
    frames = []
    for fname in ["p1_frames.json", "p2_frames.json"]:
        p = ROOT / fname
        if not p.is_file():
            print(f"WARNING: {fname} not found", file=sys.stderr)
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for fr in data.get("frames", []):
            fr["_source"] = fname
            frames.append(fr)
    return frames


def main() -> int:
    frames = load_frames()
    print(f"Loaded {len(frames)} frames")

    tagged = []
    low_confidence: list[dict] = []
    missing: list[dict] = []

    for fr in frames:
        fid = fr.get("id", "")
        engine = (fr.get("engine") or "").strip()
        text = (fr.get("text") or "").strip()
        source = fr.get("_source", "?")

        tag = FRAME_TAGS.get(fid)
        if not tag:
            missing.append({"frame_id": fid, "engine": engine, "text": text, "source": source})
            entry = {
                "frame_id": fid,
                "engine": engine,
                "text": text,
                "source": source,
                "proposed_move_type": None,
                "confidence": "low",
                "reason": "NOT IN TAG TABLE — needs manual review",
                "allowed_response_roles": [],
                "default_next_move_types": [],
            }
        else:
            entry = {
                "frame_id": fid,
                "engine": engine,
                "text": text,
                "source": source,
                "proposed_move_type": tag["move_type"],
                "confidence": tag["confidence"],
                "reason": tag["reason"],
                "allowed_response_roles": tag.get("allowed_response_roles", []),
                "default_next_move_types": tag.get("default_next_move_types", []),
            }
            if tag["confidence"] == "low":
                low_confidence.append(entry)

        tagged.append(entry)

    # ── Write JSON artifact ──────────────────────────────────────────────
    json_out = {
        "_note": "Proposed move_type tags — review before applying to p1_frames.json / p2_frames.json.",
        "frames": [
            {k: v for k, v in e.items() if k != "source"} for e in tagged
        ],
    }
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(json_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ── Write markdown report ────────────────────────────────────────────
    lines = [
        "# Phase 10.7 — Move type tagging audit",
        "",
        f"Generated by `scripts/propose_move_type_tags.py`.",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|------:|",
        f"| Total frames | {len(tagged)} |",
        f"| Tagged (in table) | {len(tagged) - len(missing)} |",
        f"| Missing (not in table) | {len(missing)} |",
        f"| Low confidence | {len(low_confidence)} |",
        "",
        "## Frame audit",
        "",
        "| Frame ID | Engine | Move type | Confidence | Text | Reason |",
        "|----------|--------|-----------|------------|------|--------|",
    ]
    for e in tagged:
        mt = e["proposed_move_type"] or "—"
        conf = e["confidence"]
        text_short = e["text"][:48].replace("|", "\\|")
        reason = e["reason"].replace("|", "\\|")
        fid = e["frame_id"].replace("|", "\\|")
        lines.append(f"| `{fid}` | {e['engine']} | **{mt}** | {conf} | {text_short} | {reason} |")

    if missing:
        lines += [
            "",
            "## Frames missing from tag table (manual review required)",
            "",
        ]
        for m in missing:
            lines.append(f"- **`{m['frame_id']}`** ({m['engine']}, `{m['source']}`): `{m['text'][:60]}`")

    lines += [
        "",
        "## Transition reference",
        "",
        "| From | Allowed next |",
        "|------|-------------|",
    ]
    for mt, nexts in TRANSITIONS.items():
        lines.append(f"| {mt} | {', '.join(nexts) if nexts else '(end)'} |")

    lines.append("")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(f"Written: {REPORT_PATH.relative_to(ROOT)}")
    print(f"Written: {JSON_PATH.relative_to(ROOT)}")
    if missing:
        print(f"WARNING: {len(missing)} frame(s) not in tag table — see report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
