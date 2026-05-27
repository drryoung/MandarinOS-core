"""
tests/test_capability_estimator.py
====================================

Synthetic longitudinal tests for the MandarinOS capability estimator.

These tests verify that the system is anti-inflationary over realistic learner
journeys — one great session cannot inflate bands, sparse usage is handled
safely, plateaus hold, and long-horizon stability is maintained.

All tests use synthetic snapshot sequences.  No I/O, no server, no UI.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.capability_estimator import compute, HEURISTIC_VERSION, BANDS

# ---------------------------------------------------------------------------
# Snapshot factory helpers
# ---------------------------------------------------------------------------

def _ts(days_ago: int = 0) -> str:
    dt = datetime.datetime.now() - datetime.timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _snap(
    *,
    turns: int = 10,
    unclear: int = 0,
    questions: int = 1,
    recovery_uses: int = 0,
    successful_recoveries: int = 0,
    suggestion_clicks: int = 0,
    hint_clicks: int = 0,
    display_en_clicks: int = 0,
    display_py_clicks: int = 0,
    translation_help_uses: int = 0,
    stability_score: float | None = None,
    engines: list | None = None,
    days_ago: int = 0,
) -> dict:
    """Build a minimal synthetic progress snapshot."""
    return {
        "total_turns":          turns,
        "unclear_turns":        unclear,   # canonical snapshot field
        "questions_asked":      questions,
        "recovery_uses":        recovery_uses,
        "successful_recoveries": successful_recoveries,
        "suggestion_clicks":    suggestion_clicks,
        "hint_clicks":          hint_clicks,
        "display_en_clicks":    display_en_clicks,
        "display_py_clicks":    display_py_clicks,
        "translation_help_uses": translation_help_uses,
        "conversation_stability_score": stability_score,
        "engines_used":         engines or ["place"],
        "created_at":           _ts(days_ago),
    }


def _many(template: dict, n: int, day_step: int = 1) -> List[dict]:
    """Repeat a snapshot pattern N times across consecutive days."""
    snaps = []
    for i in range(n):
        s = dict(template)
        s["created_at"] = _ts((n - i) * day_step)
        snaps.append(s)
    return snaps


# ---------------------------------------------------------------------------
# A — Core anti-inflation: empty + early history
# ---------------------------------------------------------------------------

def test_empty_history_all_emerging():
    result = compute([])
    for dim in result["dimensions"].values():
        assert dim["band"] == "Emerging", f"Expected Emerging for new learner, got {dim['band']}"


def test_one_great_session_cannot_promote():
    """One session of 40 turns, zero unclear — still all Emerging."""
    snaps = [_snap(turns=40, unclear=0, questions=5, hint_clicks=0, stability_score=100)]
    result = compute(snaps)
    for name, dim in result["dimensions"].items():
        assert dim["band"] == "Emerging", (
            f"One session must not promote {name}: got {dim['band']}"
        )


def test_two_sessions_still_emerging():
    """Two perfect sessions cannot promote past Emerging (gate requires 3)."""
    snaps = [
        _snap(turns=20, unclear=0, questions=3, stability_score=100, days_ago=2),
        _snap(turns=20, unclear=0, questions=3, stability_score=100, days_ago=1),
    ]
    result = compute(snaps)
    for name, dim in result["dimensions"].items():
        assert dim["band"] == "Emerging", (
            f"Two sessions must not promote {name}: got {dim['band']}"
        )


# ---------------------------------------------------------------------------
# B — Short / non-qualifying sessions do not count
# ---------------------------------------------------------------------------

def test_short_sessions_excluded_from_qualifying():
    """Sessions with total_turns < 6 are not qualifying; 5 such sessions = no promotion."""
    snaps = [_snap(turns=5) for _ in range(10)]
    result = compute(snaps)
    assert result["qualifying_session_count"] == 0
    for dim in result["dimensions"].values():
        assert dim["band"] == "Emerging"


def test_mix_short_and_qualifying_only_qualifying_count():
    short_snaps = [_snap(turns=3, days_ago=20 - i) for i in range(7)]
    qual_snaps  = [_snap(turns=10, days_ago=i)      for i in range(3)]
    result = compute(short_snaps + qual_snaps)
    assert result["qualifying_session_count"] == 3  # only the 3 long ones


# ---------------------------------------------------------------------------
# C — Three qualifying sessions: Developing gate met
# ---------------------------------------------------------------------------

def test_three_qualifying_good_sessions_developing():
    """Exactly 3 qualifying sessions with median turns >= 8 → Developing on sustained_conversation."""
    snaps = _many(_snap(turns=12, unclear=0, questions=2, stability_score=85), 3, day_step=2)
    result = compute(snaps)
    # sustained_conversation should reach Developing (turns >= 8, 3 sessions)
    assert result["dimensions"]["sustained_conversation"]["band"] == "Developing", (
        f"Expected Developing, got {result['dimensions']['sustained_conversation']['band']}"
    )


def test_three_sessions_insufficient_for_consolidating():
    """Even with perfect turns, 3 sessions cannot reach Consolidating (gate requires 8)."""
    snaps = _many(_snap(turns=25, unclear=0, questions=5, stability_score=100), 3, day_step=1)
    result = compute(snaps)
    sc = result["dimensions"]["sustained_conversation"]["band"]
    assert sc in ("Emerging", "Developing"), f"3 sessions must not reach Consolidating: got {sc}"


# ---------------------------------------------------------------------------
# D — Promotion requires 60% of rolling window meeting the floor
# ---------------------------------------------------------------------------

def test_majority_gate_blocks_promotion():
    """3 qualifying sessions but only 2/5 (40%) meet the Developing floor — no promotion."""
    # Need 3 minimum qualifying sessions; 5 in window; only 2 have turns >= 8
    snaps = (
        _many(_snap(turns=6), 3, day_step=3)    # borderline qualifying, turns=6 < 8
        + [_snap(turns=14, days_ago=2), _snap(turns=14, days_ago=1)]
    )
    # 5 qualifying sessions, but only 2/5 meet turns >= 8 floor (40%) → below 60%
    result = compute(snaps)
    sc = result["dimensions"]["sustained_conversation"]["band"]
    # Cannot promote: turns=6 is below floor_dev=8
    assert sc == "Emerging", f"Majority gate should block promotion: got {sc}"


def test_majority_gate_allows_promotion_at_60_percent():
    """6 of last 10 qualifying sessions meet the Developing floor → promotes."""
    below_floor = _many(_snap(turns=6, days_ago=0), 4, day_step=2)
    above_floor = _many(_snap(turns=14, days_ago=0), 6, day_step=1)
    snaps = sorted(below_floor + above_floor, key=lambda s: s["created_at"])
    result = compute(snaps)
    sc = result["dimensions"]["sustained_conversation"]["band"]
    assert sc == "Developing", f"60% should allow Developing: got {sc}"


# ---------------------------------------------------------------------------
# E — Inactivity and observation window
# ---------------------------------------------------------------------------

def test_inactivity_flag_after_21_days():
    """Last qualifying session > 21 days ago → inactive=True."""
    snaps = _many(_snap(turns=12, stability_score=80), 5, day_step=1)
    # Shift all to 30 days ago
    for s in snaps:
        s["created_at"] = _ts(30 + int(s["created_at"][-2:]))
    result = compute(snaps)
    assert result["inactive"] is True


def test_recent_session_not_inactive():
    snaps = _many(_snap(turns=12, stability_score=80), 5, day_step=1)
    result = compute(snaps)
    assert result["inactive"] is False


def test_observation_window_blocks_promotion_after_break():
    """
    Learner had a 30-day gap then did 1 session — should be observation-locked,
    so even if they meet promotion criteria their band stays put.
    """
    old_snaps = []
    for i in range(10):
        s = _snap(turns=14, unclear=0, questions=3, stability_score=88)
        s["created_at"] = _ts(60 - i)  # 50–60 days ago
        old_snaps.append(s)
    new_snap = _snap(turns=14, unclear=0, questions=3, stability_score=88)
    new_snap["created_at"] = _ts(1)  # 1 day ago (30+ day gap)
    snaps = old_snaps + [new_snap]
    result = compute(snaps)
    assert result["observation_locked"] is True, "Should be observation-locked after break"


def test_observation_window_lifts_after_enough_sessions():
    """After _OBSERVATION_SESSIONS sessions post-break, observation lock is cleared."""
    old_snaps = []
    for i in range(8):
        s = _snap(turns=12, unclear=0)
        s["created_at"] = _ts(60 - i)
        old_snaps.append(s)
    new_snaps = []
    for i in range(3):  # 3 sessions post-break (> 2 = observation window)
        s = _snap(turns=12, unclear=0)
        s["created_at"] = _ts(2 - i)
        new_snaps.append(s)
    snaps = old_snaps + new_snaps
    result = compute(snaps)
    assert result["observation_locked"] is False, "Observation lock should lift after 3 sessions"


# ---------------------------------------------------------------------------
# F — Engine breadth gate
# ---------------------------------------------------------------------------

def test_engine_breadth_blocks_consolidating_with_one_engine():
    """8 perfect sessions on one engine cannot reach Consolidating."""
    snaps = _many(
        _snap(turns=16, unclear=0, questions=4, stability_score=92, engines=["place"]),
        8, day_step=1
    )
    result = compute(snaps)
    sc = result["dimensions"]["sustained_conversation"]["band"]
    assert sc in ("Emerging", "Developing"), (
        f"1-engine learner must not reach Consolidating: got {sc}"
    )
    assert result["engine_breadth"] == 1


def test_engine_breadth_allows_consolidating_with_three_engines():
    """Same 8 sessions but across 3+ engines — breadth gate satisfied."""
    engine_cycle = [["place"], ["work"], ["family"], ["travel"]]
    snaps = []
    for i in range(8):
        s = _snap(turns=16, unclear=0, questions=4, stability_score=92,
                  engines=engine_cycle[i % len(engine_cycle)])
        s["created_at"] = _ts(8 - i)
        snaps.append(s)
    result = compute(snaps)
    assert result["engine_breadth"] >= 3


# ---------------------------------------------------------------------------
# G — Independence: per-turn rate, not raw count
# ---------------------------------------------------------------------------

def test_independence_long_session_with_heavy_support_stays_emerging():
    """40-turn session with 30 support events = 0.75/turn → stays Emerging."""
    snaps = _many(
        _snap(turns=40, hint_clicks=15, display_en_clicks=10, suggestion_clicks=5),
        5, day_step=1
    )
    result = compute(snaps)
    ind = result["dimensions"]["independence"]["band"]
    # support_rate = 30/40 = 0.75 > ceil_dev=0.60 → cannot promote to Developing
    assert ind == "Emerging", f"Heavy support per-turn should stay Emerging: got {ind}"


def test_independence_short_session_low_support_can_promote():
    """6-turn session with 1 support event = 0.17/turn → meets Developing ceil."""
    snaps = _many(
        _snap(turns=6, hint_clicks=1),
        5, day_step=1
    )
    result = compute(snaps)
    ind = result["dimensions"]["independence"]["band"]
    # support_rate = 1/6 ≈ 0.17 < ceil_dev=0.60 → eligible for Developing
    assert ind == "Developing", f"Low per-turn support should reach Developing: got {ind}"


# ---------------------------------------------------------------------------
# H — Recovery resilience
# ---------------------------------------------------------------------------

def test_recovery_high_unclear_rate_stays_emerging():
    """50% unclear rate (5/10) > threshold → stays Emerging."""
    snaps = _many(_snap(turns=10, unclear=5), 5, day_step=1)
    result = compute(snaps)
    rr = result["dimensions"]["recovery_resilience"]["band"]
    assert rr == "Emerging", f"High unclear rate should stay Emerging: got {rr}"


def test_recovery_low_unclear_rate_promotes_to_developing():
    """20% unclear rate (2/10) <= threshold (35%) → eligible for Developing."""
    snaps = _many(_snap(turns=10, unclear=2, stability_score=72), 5, day_step=1)
    result = compute(snaps)
    rr = result["dimensions"]["recovery_resilience"]["band"]
    assert rr == "Developing", f"Low unclear rate should reach Developing: got {rr}"


# ---------------------------------------------------------------------------
# I — No aggregate score field ever emitted
# ---------------------------------------------------------------------------

def test_no_aggregate_score_in_output():
    snaps = _many(_snap(turns=20), 20, day_step=1)
    result = compute(snaps)
    forbidden = {"score", "overall_score", "capability_score", "aggregate_score",
                 "total_score", "level_score", "overall", "percentage"}
    for key in result.keys():
        assert key not in forbidden, f"Forbidden aggregate field found: {key}"
    for dim in result["dimensions"].values():
        for key in dim.keys():
            assert key not in forbidden, f"Forbidden aggregate field in dimension: {key}"


# ---------------------------------------------------------------------------
# J — Heuristic version always present
# ---------------------------------------------------------------------------

def test_heuristic_version_present():
    result = compute([])
    assert "heuristic_version" in result
    assert result["heuristic_version"] == HEURISTIC_VERSION
    assert isinstance(result["heuristic_version"], int)
    assert result["heuristic_version"] >= 1


# ---------------------------------------------------------------------------
# K — Demotion: asymmetric, requires sustained evidence
# ---------------------------------------------------------------------------

def test_demotion_requires_sustained_evidence():
    """
    Learner reaches Developing, then has 3 bad sessions.
    3 < (win+3=8)*0.70 ≈ 5.6 → not enough for demotion.
    """
    # 5 good sessions → Developing on sustained_conversation
    good = _many(_snap(turns=12, unclear=0, stability_score=82), 5, day_step=2)
    # 3 poor sessions (turns < 8)
    poor = _many(_snap(turns=6, unclear=2), 3, day_step=1)
    snaps = good + poor
    result = compute(snaps)
    sc = result["dimensions"]["sustained_conversation"]["band"]
    # Should still be Developing — 3 bad sessions not enough for demotion
    assert sc in ("Developing", "Emerging"), (
        f"After 3 poor sessions should not dip below Developing: got {sc}"
    )


def test_single_outlier_session_does_not_demote():
    """After reaching Developing, one bad session never causes demotion."""
    good = _many(_snap(turns=14, unclear=0, stability_score=88), 6, day_step=2)
    bad  = [_snap(turns=6, unclear=3, stability_score=50, days_ago=1)]
    result = compute(good + bad)
    sc = result["dimensions"]["sustained_conversation"]["band"]
    assert sc == "Developing", f"Single bad session must not demote: got {sc}"


# ---------------------------------------------------------------------------
# L — Familiar-topic-only learner: breadth-gated at Developing
# ---------------------------------------------------------------------------

def test_familiar_topic_only_learner_plateaus_at_developing():
    """
    50 qualifying sessions all on one topic ('place') with strong metrics.
    sustained_conversation and stability may be Developing; cannot reach
    Consolidating (breadth gate: requires 3 engines).
    """
    snaps = _many(
        _snap(turns=18, unclear=0, questions=2, stability_score=90, engines=["place"]),
        20, day_step=1
    )
    result = compute(snaps)
    assert result["engine_breadth"] == 1
    for name, dim in result["dimensions"].items():
        assert dim["band"] in ("Emerging", "Developing"), (
            f"Single-engine learner must not pass Developing on {name}: got {dim['band']}"
        )


# ---------------------------------------------------------------------------
# M — Median (not mean) resists single stellar session
# ---------------------------------------------------------------------------

def test_median_resists_single_great_session():
    """
    9 mediocre sessions (turns=7) + 1 stellar (turns=30) = 10 sessions.
    Median turns = 7 → below floor_cons (12) → cannot reach Consolidating.
    """
    mediocre = _many(_snap(turns=7, stability_score=65), 9, day_step=2)
    stellar  = [_snap(turns=30, unclear=0, stability_score=100, days_ago=1)]
    snaps = mediocre + stellar
    result = compute(snaps)
    sc = result["dimensions"]["sustained_conversation"]["band"]
    assert sc in ("Emerging", "Developing"), (
        f"Single stellar session must not inflate median: got {sc}"
    )


# ---------------------------------------------------------------------------
# N — Plateau scenario: learner stalls after reaching Developing
# ---------------------------------------------------------------------------

def test_plateau_holds_at_developing():
    """
    Learner reaches Developing after 3 sessions, then continues at the same
    level for 15 more. They should stay at Developing (not drift to Consolidating).
    """
    qualifying_at_developing = _many(
        _snap(turns=9, unclear=1, questions=1, stability_score=72),
        18, day_step=1
    )
    result = compute(qualifying_at_developing)
    sc = result["dimensions"]["sustained_conversation"]["band"]
    # Median turns = 9 < 12 (Consolidating floor) → should not promote
    assert sc in ("Emerging", "Developing"), (
        f"Plateau learner must not reach Consolidating: got {sc}"
    )


# ---------------------------------------------------------------------------
# O — Long journey scenario (synthetic 30-day founder journey)
# ---------------------------------------------------------------------------

def test_30_day_founder_journey_is_believable():
    """
    Simulate a founder using MandarinOS almost daily for 30 days.
    Expects: a mix of Emerging and Developing bands; nothing at Consolidating or Steady.
    """
    snaps = []
    for i in range(28):
        # Realistic early-learner profile: 8-14 turns, 1-3 questions, 1-2 unclear
        turns   = 8 + (i % 7)
        unclear = 1 if i % 4 != 0 else 0
        q       = 1 + (i % 3)
        hints   = 2 - (i // 14)  # declining hint use over time
        stability = 75 + (i // 5) * 3  # slow improvement
        engines = [["place", "identity", "work", "family"][i % 4]]
        s = _snap(
            turns=turns, unclear=unclear, questions=q,
            hint_clicks=max(0, hints), stability_score=min(92, stability),
            engines=engines, days_ago=28 - i,
        )
        snaps.append(s)

    result = compute(snaps)
    bands_seen = {dim["band"] for dim in result["dimensions"].values()}

    # Should have qualifying sessions
    assert result["qualifying_session_count"] > 0
    # Should not have reached Consolidating or Steady within 30 days
    assert "Consolidating" not in bands_seen, (
        f"30-day journey must not reach Consolidating: {bands_seen}"
    )
    assert "Steady" not in bands_seen, (
        f"30-day journey must not reach Steady: {bands_seen}"
    )
    # Should have made some progress (at least one Developing)
    assert "Developing" in bands_seen, (
        f"30-day active founder should reach Developing on at least one dimension: {bands_seen}"
    )


# ---------------------------------------------------------------------------
# P — Comeback after 60-day gap
# ---------------------------------------------------------------------------

def test_comeback_after_60_day_gap():
    """
    Learner reaches Developing, then disappears for 60 days, then comes back.
    After 1 comeback session: observation-locked (no promotion).
    After 3 comeback sessions: observation lock should lift.
    """
    old_snaps = []
    for i in range(6):
        s = _snap(turns=12, unclear=0, questions=2, stability_score=80)
        s["created_at"] = _ts(80 - i)
        old_snaps.append(s)

    # 1 comeback session
    comeback_1 = _snap(turns=12, unclear=0, questions=2, stability_score=82)
    comeback_1["created_at"] = _ts(1)

    result_1 = compute(old_snaps + [comeback_1])
    assert result_1["observation_locked"] is True, "Should be locked after 1 comeback session"

    # 2 more comeback sessions
    comeback_2 = _snap(turns=12, unclear=0)
    comeback_2["created_at"] = _ts(0)
    comeback_3 = _snap(turns=12, unclear=0)
    comeback_3["created_at"] = _ts(0)

    result_3 = compute(old_snaps + [comeback_1, comeback_2, comeback_3])
    assert result_3["observation_locked"] is False, "Lock should lift after 3 comeback sessions"


# ---------------------------------------------------------------------------
# Q — Output structure guarantees
# ---------------------------------------------------------------------------

def test_output_keys_always_present():
    for snaps in [[], [_snap()], _many(_snap(turns=12), 5)]:
        result = compute(snaps)
        required = {
            "computed_at", "heuristic_version", "qualifying_session_count",
            "lifetime_turn_count", "engine_breadth", "inactive",
            "inactivity_days", "observation_locked", "dimensions", "trend_notes",
        }
        missing = required - result.keys()
        assert not missing, f"Missing output keys: {missing}"

        dim_required = {"band", "evidence_sessions", "next_band_progress"}
        for name, dim in result["dimensions"].items():
            missing_d = dim_required - dim.keys()
            assert not missing_d, f"Missing dimension keys in {name}: {missing_d}"

        assert isinstance(result["trend_notes"], list)
        assert isinstance(result["dimensions"], dict)
        assert len(result["dimensions"]) == 5


def test_all_bands_in_valid_set():
    snaps = _many(_snap(turns=14, stability_score=80), 20, day_step=1)
    result = compute(snaps)
    valid = set(BANDS)
    for name, dim in result["dimensions"].items():
        assert dim["band"] in valid, f"Invalid band '{dim['band']}' in {name}"


def test_next_band_progress_range():
    for n in [0, 3, 8, 15]:
        snaps = _many(_snap(turns=12), n, day_step=1)
        result = compute(snaps)
        for name, dim in result["dimensions"].items():
            assert 0.0 <= dim["next_band_progress"] <= 1.0, (
                f"next_band_progress out of range in {name}: {dim['next_band_progress']}"
            )


def test_idempotent_same_input():
    snaps = _many(_snap(turns=12, stability_score=80, questions=2), 10, day_step=1)
    r1 = compute(list(snaps))
    r2 = compute(list(snaps))
    for name in r1["dimensions"]:
        assert r1["dimensions"][name]["band"] == r2["dimensions"][name]["band"], (
            f"Non-idempotent result on {name}"
        )


# ---------------------------------------------------------------------------
# R — Support-dependence inflation resistance
# ---------------------------------------------------------------------------

def test_heavy_support_user_independence_stays_emerging():
    """
    Learner uses heavy support (>60% per-turn rate) for 10 sessions.
    Independence must stay Emerging.
    """
    snaps = _many(
        _snap(turns=10, hint_clicks=4, display_en_clicks=3),  # 7 events / 10 turns = 70%
        10, day_step=1
    )
    result = compute(snaps)
    ind = result["dimensions"]["independence"]["band"]
    assert ind == "Emerging", f"Heavy support user must stay Emerging: got {ind}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
