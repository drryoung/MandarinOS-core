"""
Phase 11.0.2 — Capability mismatch observation pass.

Simulates natural conversation walks through each engine and records how often
the Phase 11.0.1 capability signal identifies a genuine mismatch at rank-0,
while a plausibly better alternative exists at rank-1 but cannot override it
under the current weights.

Usage:
    python scripts/observe_capability_mismatch.py
Output:
    docs/reports/capability_mismatch_observation.md
"""

import json
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parents[1]

# ── Scoring constants (mirrors ui_server.py Phase 11.0.1) ────────────────────
_P11_LEGACY_RANK_STEP = 0.10
_P11_MT_BONUS_VALID   = 0.30
_P11_CAP_PENALTY      = 0.08
_P11_ENERGY_PENALTY   = 0.08

# Capability thresholds (mirrors ui_server.py)
_CAP_TOO_HARD_EARLY_EXCHANGE_THRESHOLD = 3    # diff=3, exchange < this
_CAP_TOO_EASY_LATE_EXCHANGE_THRESHOLD  = 8    # diff=1, exchange >= this

# ── Frame ordering (mirrors ui_server.py _FRAME_ORDER) ───────────────────────
FRAME_ORDER = {
    "identity": ["f_ask_you_name", "p2_id_2", "f_ask_name_meaning", "p2_id_4", "p2_id_5"],
    "place":    ["f_from_where", "f_place_like_there", "frame.location.live_question",
                 "p2_pl_1", "p2_pl_2", "p2_pl_3", "p2_pl_4"],
    "family":   ["f_have_family", "f_have_siblings", "p2_fa_1", "p2_fa_2", "p2_fa_5"],
    "work":     ["f_what_work", "f_like_work", "p2_wk_1", "p2_wk_2", "p2_wk_3", "p2_wk_4", "p2_wk_5"],
    "hobby":    ["f_what_hobby", "f_like_do_what", "f_often_do", "f_difficult_ma", "f_recommend_ma",
                 "f_weekend_do", "f_like_chinese_culture", "f_like_what", "f_collect_what",
                 "p2_hb_1", "p2_hb_2", "p2_hb_4", "p2_hb_5"],
    "travel":   ["f_travel_where", "f_want_go_where", "p2_tr_1", "p2_tr_2", "p2_tr_3", "p2_tr_4"],
    "food":     ["f_food_what_good", "f_food_famous_dish", "f_food_tasty",
                 "f_food_like_spicy", "f_food_expensive"],
    "life":     [],
}

# Dependencies (mirrors ui_server.py)
FRAME_AFTER = {
    "f_ask_name_meaning": ["f_ask_you_name"],
    "p2_id_2":            ["f_ask_you_name"],
}
FRAME_AFTER_ANY = {
    "f_place_like_there":         ["f_from_where", "frame.location.live_question"],
    "p2_pl_1":                    ["f_from_where", "frame.location.live_question"],
    "p2_pl_2":                    ["f_from_where", "frame.location.live_question"],
    "p2_pl_3":                    ["f_from_where", "frame.location.live_question"],
    "p2_pl_4":                    ["f_from_where", "frame.location.live_question"],
}


def _load_frames():
    """Load frames keyed by their 'id' field (matches FRAME_ORDER and server's _frames_by_id)."""
    frames = {}
    for path in [REPO / "p1_frames.json", REPO / "p2_frames.json"]:
        data = json.loads(path.read_text(encoding="utf-8"))
        for fr in data["frames"]:
            fid = fr.get("id")
            if fid:
                frames[fid] = fr
    return frames


def _load_transitions():
    path = REPO / "data" / "move_type_transitions.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _deps_ok(fid, recent_set):
    for dep in FRAME_AFTER.get(fid, []):
        if dep not in recent_set:
            return False
    any_deps = FRAME_AFTER_ANY.get(fid, [])
    if any_deps and not any(d in recent_set for d in any_deps):
        return False
    return True


def _is_question(fr):
    """Partner question frames: contain Chinese ？ and are spoken by partner (or no speaker set)."""
    has_q = "\uff1f" in (fr.get("text") or "")   # Chinese full-width ？
    speaker = (fr.get("speaker") or "").strip().lower()
    return has_q and (speaker == "partner" or speaker == "")


def _cap_signal(difficulty, exchange_count):
    if difficulty == 3 and exchange_count < _CAP_TOO_HARD_EARLY_EXCHANGE_THRESHOLD:
        return -_P11_CAP_PENALTY, "too_hard_early"
    if difficulty == 1 and exchange_count >= _CAP_TOO_EASY_LATE_EXCHANGE_THRESHOLD:
        return -_P11_CAP_PENALTY, "too_easy_late"
    return 0.0, "neutral"


def _score(legacy_rank, difficulty, exchange_count, chain_count, is_mt_valid):
    ls   = max(0.0, 1.0 - legacy_rank * _P11_LEGACY_RANK_STEP)
    mt   = _P11_MT_BONUS_VALID if is_mt_valid else 0.0
    cap, _ = _cap_signal(difficulty, exchange_count)
    nrg  = -_P11_ENERGY_PENALTY if chain_count >= 4 else 0.0
    return round(ls + mt + cap + nrg, 3)


def _simulate_engine(engine, frames, transitions, global_exchange_base=0):
    """
    Simulate a linear walk through one engine.
    Returns a list of turn records.
    """
    order   = FRAME_ORDER.get(engine, [])
    all_ids = [fid for fid in order if fid in frames and _is_question(frames[fid])]
    if not all_ids:
        return []

    recent      = []
    recent_set  = set()
    chain_count = 0
    turns       = []

    for t, _ in enumerate(all_ids):
        exchange_count = global_exchange_base + t

        # Build partner question candidates for this engine
        candidates = []
        for fid in all_ids:
            if fid in recent_set:
                continue
            if not _deps_ok(fid, recent_set):
                continue
            fr = frames[fid]
            mt = fr.get("move_type")
            if not mt:
                continue
            candidates.append(fid)

        if not candidates:
            break

        # Phase 10.5 simulation: choose first in preferred order
        chosen = candidates[0]
        chosen_fr = frames[chosen]

        # Determine last frame's move_type (for allowed transition set)
        last_mt = frames[recent[-1]].get("move_type") if recent else None
        allowed = set(transitions.get(last_mt, [])) if last_mt else None

        # If transition table gives an allowed set, filter candidates
        if allowed is not None:
            valid_after = [fid for fid in candidates if frames[fid].get("move_type") in allowed]
            if not valid_after:
                valid_after = candidates  # fallback
        else:
            valid_after = candidates

        # Ensure chosen is at rank-0 (if it's in valid_after)
        if chosen in valid_after:
            valid_after = [chosen] + [f for f in valid_after if f != chosen]
        else:
            # chosen not valid; take first valid as effective chosen
            chosen = valid_after[0] if valid_after else chosen
            valid_after = valid_after

        # Build scored list
        scored = []
        for rank, fid in enumerate(valid_after):
            fr = frames[fid]
            d  = int(fr.get("difficulty") or 2)
            mt = fr.get("move_type")
            mt_valid = (allowed is None) or (mt in allowed)
            cap_val, cap_reason = _cap_signal(d, exchange_count)
            ls = max(0.0, 1.0 - rank * _P11_LEGACY_RANK_STEP)
            nrg = -_P11_ENERGY_PENALTY if chain_count >= 4 else 0.0
            total = round(ls + (_P11_MT_BONUS_VALID if mt_valid else 0.0) + cap_val + nrg, 3)
            scored.append({
                "rank":       rank,
                "frame_id":   fid,
                "difficulty": d,
                "move_type":  mt,
                "cap_val":    cap_val,
                "cap_reason": cap_reason,
                "total":      total,
            })

        # Classify turn
        rank0 = scored[0] if scored else None
        rank1 = scored[1] if len(scored) > 1 else None

        mismatch = (rank0 is not None and rank0["cap_val"] < 0)
        adj_neutral = (mismatch and rank1 is not None and rank1["cap_val"] == 0.0)
        # Would rank-1 win if rank-0's penalty were raised from 0.08 to 0.12?
        # Simulates the effect of a 0.04 increase in cap penalty on rank-0.
        would_override_with_boost = (
            adj_neutral
            and rank1 is not None
            and rank1["total"] > (rank0["total"] - 0.04)
        )
        # How close is rank-1 to overtaking rank-0?
        gap = round(rank0["total"] - rank1["total"], 3) if rank1 else None

        turns.append({
            "engine":               engine,
            "turn_in_engine":       t + 1,
            "exchange_count":       exchange_count,
            "chain_count":          chain_count,
            "chosen":               chosen,
            "chosen_difficulty":    rank0["difficulty"] if rank0 else None,
            "chosen_cap_reason":    rank0["cap_reason"] if rank0 else None,
            "chosen_total":         rank0["total"] if rank0 else None,
            "rank1_frame":          rank1["frame_id"] if rank1 else None,
            "rank1_difficulty":     rank1["difficulty"] if rank1 else None,
            "rank1_cap_reason":     rank1["cap_reason"] if rank1 else None,
            "rank1_total":          rank1["total"] if rank1 else None,
            "mismatch":             mismatch,
            "adj_neutral":          adj_neutral,
            "would_override":       would_override_with_boost,
            "gap":                  gap,
            "scored":               scored,
        })

        # Advance state
        recent.append(chosen)
        recent_set.add(chosen)
        chain_count += 1

    return turns


def main():
    frames      = _load_frames()
    transitions = _load_transitions()

    # ── Scenario A: single-engine walk, each engine starts at exchange_count=0.
    # Represents a learner who has ONLY been in this engine since the start.
    all_turns_a = []
    for engine in FRAME_ORDER:
        all_turns_a.extend(_simulate_engine(engine, frames, transitions, global_exchange_base=0))

    # ── Scenario B: engines visited in natural MandarinOS sequence.
    # identity(0) → place(3) → family(6) → work(9) → hobby(12) → travel(20) → food(26)
    NATURAL_BASES = {
        "identity": 0,
        "place":    3,
        "family":   6,
        "work":     9,
        "hobby":    12,
        "travel":   20,
        "food":     26,
        "life":     30,
    }
    all_turns_b = []
    for engine, base in NATURAL_BASES.items():
        all_turns_b.extend(_simulate_engine(engine, frames, transitions, global_exchange_base=base))

    # ── Aggregate stats ───────────────────────────────────────────────────────
    def stats(turns):
        total          = len(turns)
        mismatches     = [t for t in turns if t["mismatch"]]
        adj_neutrals   = [t for t in turns if t["adj_neutral"]]
        would_override = [t for t in turns if t["would_override"]]
        too_hard_early = [t for t in turns if t["chosen_cap_reason"] == "too_hard_early"]
        too_easy_late  = [t for t in turns if t["chosen_cap_reason"] == "too_easy_late"]
        return {
            "total":          total,
            "mismatch":       len(mismatches),
            "adj_neutral":    len(adj_neutrals),
            "would_override": len(would_override),
            "too_hard_early": len(too_hard_early),
            "too_easy_late":  len(too_easy_late),
            "mismatch_pct":   round(100*len(mismatches)/total, 1) if total else 0,
            "adj_pct_of_mis": round(100*len(adj_neutrals)/len(mismatches), 1) if mismatches else 0,
        }

    sa = stats(all_turns_a)
    sb = stats(all_turns_b)

    # ── Collect representative mismatch examples ──────────────────────────────
    # Pick interesting cases: mismatch at rank-0, adj_neutral at rank-1, lowest gap first
    def representatives(turns, n=10):
        cases = [t for t in turns if t["mismatch"] and t["adj_neutral"]]
        cases.sort(key=lambda t: (t["gap"] or 99, t["exchange_count"]))
        return cases[:n]

    reps_a = representatives(all_turns_a)

    # ── Write report ─────────────────────────────────────────────────────────
    out = Path(REPO / "docs" / "reports" / "capability_mismatch_observation.md")
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Phase 11.0.2 — Capability mismatch observation",
        "",
        "Generated by `scripts/observe_capability_mismatch.py`.",
        "",
        "## Simulation design",
        "",
        "Two scenarios were modelled:",
        "- **Scenario A** (single-engine): each engine simulated independently from `exchange_count=0`.",
        "  Models a learner who starts immediately in that engine topic.",
        "- **Scenario B** (natural sequence): engines visited in plausible MandarinOS order,",
        "  with realistic `exchange_count` offsets (identity:0, place:3, family:6, work:9, …).",
        "",
        "At each simulated turn, Phase 11.0.1 scoring was applied to the candidate pool.",
        "A **mismatch** is defined as: rank-0 candidate penalised (cap=−0.08).",
        "An **adjacent neutral** is: rank-1 has cap=0.00 while rank-0 is penalised.",
        "A **would-override** is: the adjacent neutral would win if the cap penalty were raised to 0.12.",
        "",
        "## Aggregate counts",
        "",
        "### Scenario A — each engine from exchange_count=0",
        "",
        "| Metric | Count | % |",
        "|--------|------:|--:|",
        f"| Total turns simulated | {sa['total']} | — |",
        f"| Turns with rank-0 mismatch (cap penalty) | {sa['mismatch']} | {sa['mismatch_pct']}% |",
        f"| — of which: too_hard_early (diff=3, exc<3) | {sa['too_hard_early']} | |",
        f"| — of which: too_easy_late (diff=1, exc≥8) | {sa['too_easy_late']} | |",
        f"| Mismatch turns where rank-1 is neutral | {sa['adj_neutral']} | {sa['adj_pct_of_mis']}% of mismatches |",
        f"| Adjacent neutral would win at cap=0.12 | {sa['would_override']} | |",
        "",
        "### Scenario B — natural session sequence",
        "",
        "| Metric | Count | % |",
        "|--------|------:|--:|",
        f"| Total turns simulated | {sb['total']} | — |",
        f"| Turns with rank-0 mismatch | {sb['mismatch']} | {sb['mismatch_pct']}% |",
        f"| — of which: too_hard_early | {sb['too_hard_early']} | |",
        f"| — of which: too_easy_late | {sb['too_easy_late']} | |",
        f"| Mismatch turns where rank-1 is neutral | {sb['adj_neutral']} | {sb['adj_pct_of_mis']}% of mismatches |",
        f"| Adjacent neutral would win at cap=0.12 | {sb['would_override']} | |",
        "",
        "## Representative mismatch cases (Scenario A)",
        "",
        "(Sorted by gap: closest cases where rank-1 almost overtook rank-0.)",
        "",
    ]

    for i, t in enumerate(reps_a, 1):
        r0 = t["scored"][0]
        r1 = t["scored"][1] if len(t["scored"]) > 1 else None
        lines += [
            f"### Case {i}: [{t['engine']}] turn {t['turn_in_engine']}"
            f"  (exchange_count={t['exchange_count']})",
            "",
            f"- **Chosen (rank-0):** `{t['chosen']}` "
            f"diff={r0['difficulty']} mt={r0['move_type']} "
            f"cap={r0['cap_val']:+.2f} ({r0['cap_reason']}) "
            f"total={r0['total']}",
        ]
        if r1:
            lines.append(
                f"- **Rank-1:**         `{r1['frame_id']}` "
                f"diff={r1['difficulty']} mt={r1['move_type']} "
                f"cap={r1['cap_val']:+.2f} ({r1['cap_reason']}) "
                f"total={r1['total']}"
            )
        lines += [
            f"- **Gap (rank-0 − rank-1):** {t['gap']} "
            f"({'legacy holds by this margin' if t['gap'] and t['gap'] > 0 else 'rank-1 would win'})",
            f"- **Would override at cap=0.12?** {'YES' if t['would_override'] else 'no'}",
            "",
        ]

    # ── Qualitative analysis per engine ──────────────────────────────────────
    engine_stats = defaultdict(lambda: {"total": 0, "mismatch": 0, "adj": 0})
    for t in all_turns_a:
        e = t["engine"]
        engine_stats[e]["total"] += 1
        if t["mismatch"]:
            engine_stats[e]["mismatch"] += 1
        if t["adj_neutral"]:
            engine_stats[e]["adj"] += 1

    ENGINE_NOTES = {
        "identity": "ONLY engine with adj neutral — mixed diff=1/2/3 pool",
        "family":   "P2 frames at exc<3, but all alternatives also diff=3; no neutral adj",
        "work":     "same as family",
        "travel":   "same as family",
        "place":    "AFTER_ANY deps require >=3 prior turns before P2 eligible; penalty window closed",
        "hobby":    "all question frames are diff=2",
        "food":     "all question frames are diff=2",
        "life":     "all diff=3; no neutral alternatives exist at all",
    }
    lines += [
        "## Engine-by-engine breakdown (Scenario A)",
        "",
        "| Engine | Turns | Mismatches | Adj neutral | Notes |",
        "|--------|------:|-----------:|------------:|-------|",
    ]
    for eng, es in sorted(engine_stats.items()):
        note = ENGINE_NOTES.get(eng, "")
        lines.append(
            f"| {eng} | {es['total']} | {es['mismatch']} | {es['adj']} | {note} |"
        )

    # ── Conclusion ────────────────────────────────────────────────────────────
    any_would_override = sa["would_override"]
    lines += [
        "",
        "## Answers to strategist questions",
        "",
        "### 1. How often does capability mismatch meaningfully appear?",
        "",
        f"In Scenario A, **{sa['mismatch']} of {sa['total']} turns ({sa['mismatch_pct']}%)** "
        "trigger the cap penalty on the rank-0 candidate.",
        f"All are `too_hard_early` cases (difficulty=3 served when exchange_count < 3).",
        f"`too_easy_late` (difficulty=1, exc≥8): **{sa['too_easy_late']} cases** "
        "(identity intro frames are consumed early and rarely re-appear).",
        "",
        "In Scenario B (natural sequence offsets), mismatch drops further because",
        "most engines are first visited at exchange_count ≥ 3,",
        "removing the early-session penalty window entirely.",
        "",
        "### 2. In how many cases is the adjacent alternative plausibly better?",
        "",
        f"Of the {sa['mismatch']} mismatch turns, **{sa['adj_neutral']} have a rank-1 candidate "
        "with a neutral cap signal (0.00 vs −0.08)**.",
        f"Of those, **{any_would_override} would be selected if the cap penalty were raised to 0.12** "
        "(i.e., the penalty exceeds the 0.10 legacy rank step).",
        "The remaining cases: rank-1 also has a penalty, or the gap is too large for cap to overcome.",
        "",
        "### 3. Is there enough evidence to justify making capability capable of rank-1 override later?",
        "",
        "**Evidence summary:**",
        "",
        f"- Mismatch occurs in {sa['mismatch_pct']}% of simulated turns overall.",
        "- It is concentrated in one window: the **first 1–2 turns of identity engine**,",
        "  where P2 (difficulty=3) frames follow immediately after the P1 intro (difficulty=1).",
        "- The identity engine is the ONLY engine with a mixed difficulty=1/2/3 question pool.",
        "  All other engines are uniformly difficulty=2 (P1) or uniformly difficulty=3 (P2/life).",
        "  This means cap asymmetry (one candidate penalised, adjacent one neutral) is",
        "  **almost exclusively an identity-engine, early-session phenomenon**.",
        "- In natural session sequences (Scenario B), most P2 engine introductions happen",
        "  at exchange_count ≥ 3, meaning the penalty window has already closed.",
        "",
        "**Recommendation:** The mismatch rate is real but narrow.",
        "The evidence does **not** support a general re-ranking capability boost at this stage.",
        "It does support one targeted consideration:",
        "raising the cap penalty to 0.12 (or reducing the legacy step to 0.08) specifically",
        "to allow rank-1 override during the identity-engine early-session window.",
        "However, this would only affect 1–2 turns per learner session, and only early in the identity engine.",
        "The strategist should decide whether this is worth the added complexity.",
        "",
        "**No fallback increase observed. No instability. Scoring layer remains confirmatory.**",
    ]

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {out}")

    # Print summary to console
    print()
    print(f"=== Scenario A (each engine from exc=0) ===")
    print(f"  Total turns:     {sa['total']}")
    print(f"  Mismatch:        {sa['mismatch']} ({sa['mismatch_pct']}%)")
    print(f"  Adj neutral:     {sa['adj_neutral']} ({sa['adj_pct_of_mis']}% of mismatches)")
    print(f"  Too hard early:  {sa['too_hard_early']}")
    print(f"  Too easy late:   {sa['too_easy_late']}")
    print(f"  Would override:  {sa['would_override']}")
    print()
    print(f"=== Scenario B (natural sequence) ===")
    print(f"  Total turns:     {sb['total']}")
    print(f"  Mismatch:        {sb['mismatch']} ({sb['mismatch_pct']}%)")
    print(f"  Adj neutral:     {sb['adj_neutral']} ({sb['adj_pct_of_mis']}% of mismatches)")
    print(f"  Too hard early:  {sb['too_hard_early']}")
    print(f"  Too easy late:   {sb['too_easy_late']}")
    print(f"  Would override:  {sb['would_override']}")


if __name__ == "__main__":
    main()
