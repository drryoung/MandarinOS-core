"""
MandarinOS — Longitudinal Capability Estimator
===============================================

Derives a conservative, trend-based capability profile from a learner's
historical progress snapshots.  Deliberately separate from the session-level
scorecard, which remains warm and per-session.

Design principles:
  - No aggregate score.  Five independent dimensions only.
  - Bands: Emerging → Developing → Consolidating → Steady.
  - Promotion is slow (median over a rolling window, fraction gate).
  - Demotion is allowed but also slow (hysteresis).
  - One excellent session cannot inflate longitudinal bands.
  - Engine-breadth gate blocks Consolidating/Steady on narrow topic exposure.
  - Inactivity (>21 days) sets an observation window: no promotion for 2 sessions after break.
  - heuristic_version is stamped on every output for future replayability.

Input:  list of progress snapshot dicts (from progress_store.load_snapshots)
Output: CapabilityState dict — suitable for /api/capability response

No I/O here.  Pure computation.  All thresholds live in
content/capability_band_thresholds.json (loaded once at module import).
"""

from __future__ import annotations

import datetime
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Load thresholds from canonical JSON
# ---------------------------------------------------------------------------

_THRESHOLDS_PATH = Path(__file__).resolve().parents[1] / "content" / "capability_band_thresholds.json"

try:
    _T = json.loads(_THRESHOLDS_PATH.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as _e:
    raise RuntimeError(f"capability_estimator: cannot load band thresholds: {_e}") from _e

HEURISTIC_VERSION: int = _T["heuristic_version"]

_QUAL_MIN_TURNS: int = _T["qualifying_session_min_turns"]

_PROMO_GATES: Dict[str, dict] = _T["promotion_gates"]
_PROMO_FRAC:  float = _T["promotion_fraction"]
_DEMO_FRAC:   float = _T["demotion_fraction"]

_WIN_FAST: int = _T["rolling_window_fast"]
_WIN_SLOW: int = _T["rolling_window_slow"]

_INACTIVITY_DAYS:     int = _T["inactivity_days"]
_OBSERVATION_SESSIONS: int = _T["observation_sessions_after_break"]

_BREADTH_CONSOLIDATING: int = _T["engine_breadth_min_for_consolidating"]
_BREADTH_STEADY:        int = _T["engine_breadth_min_for_steady"]

_DIM_CFG: Dict[str, dict] = _T["dimensions"]

BANDS = ("Emerging", "Developing", "Consolidating", "Steady")
_BAND_IDX = {b: i for i, b in enumerate(BANDS)}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return default


def _parse_dt(ts: str) -> Optional[datetime.datetime]:
    """Parse ISO 8601 timestamp strings (with or without timezone)."""
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    return None


def _median_or(values: List[float], fallback: float = 0.0) -> float:
    if not values:
        return fallback
    if len(values) == 1:
        return values[0]
    return statistics.median(values)


def _fraction_meeting(values: List[bool]) -> float:
    if not values:
        return 0.0
    return sum(1 for v in values if v) / len(values)


# ---------------------------------------------------------------------------
# Session classification
# ---------------------------------------------------------------------------

def _is_qualifying(snap: dict) -> bool:
    return _safe_int(snap.get("total_turns")) >= _QUAL_MIN_TURNS


def _support_rate(snap: dict) -> float:
    """Support events per turn (per-turn rate, not raw count)."""
    turns = _safe_int(snap.get("total_turns"), 1)
    if turns == 0:
        turns = 1
    raw = (
        _safe_int(snap.get("suggestion_clicks"))
        + _safe_int(snap.get("hint_clicks"))
        + _safe_int(snap.get("display_en_clicks"))
        + _safe_int(snap.get("display_py_clicks"))
        + _safe_int(snap.get("translation_help_uses"))
    )
    return raw / turns


def _unclear_rate(snap: dict) -> float:
    turns = _safe_int(snap.get("total_turns"), 1)
    if turns == 0:
        turns = 1
    # Prefer the canonical snapshot field (unclear_turns); fall back to the raw
    # session field (unmatched_responses).  Do NOT sum both — they are the same
    # underlying count stored under different keys in different contexts.
    if snap.get("unclear_turns") is not None:
        unclear = _safe_int(snap.get("unclear_turns"))
    else:
        unclear = _safe_int(snap.get("unmatched_responses"))
    return unclear / turns


def _engines_seen(snapshots: List[dict]) -> set:
    seen: set = set()
    for s in snapshots:
        engines = s.get("engines_used") or []
        if isinstance(engines, list):
            seen.update(str(e) for e in engines if e)
    return seen


# ---------------------------------------------------------------------------
# Inactivity and observation window
# ---------------------------------------------------------------------------

def _compute_inactivity(qualifying: List[dict]) -> tuple[bool, int]:
    """Return (inactive: bool, days_since_last: int)."""
    if not qualifying:
        return False, 0
    last_snap = qualifying[-1]
    ts = _parse_dt(last_snap.get("created_at") or "")
    if ts is None:
        return False, 0
    now = datetime.datetime.now()
    delta = (now - ts).days
    return delta >= _INACTIVITY_DAYS, delta


def _observation_lock(qualifying: List[dict]) -> bool:
    """
    True when the learner just returned from a break and is in the observation
    window (first N sessions after the gap should not trigger promotion).
    Looks for the most-recent inactivity gap and counts sessions since.
    """
    if len(qualifying) < 2:
        return False
    for i in range(len(qualifying) - 1, 0, -1):
        ts_curr = _parse_dt(qualifying[i].get("created_at") or "")
        ts_prev = _parse_dt(qualifying[i - 1].get("created_at") or "")
        if ts_curr is None or ts_prev is None:
            continue
        gap = (ts_curr - ts_prev).days
        if gap >= _INACTIVITY_DAYS:
            # found the break; count sessions since it
            sessions_since = len(qualifying) - i
            return sessions_since <= _OBSERVATION_SESSIONS
    return False


# ---------------------------------------------------------------------------
# Band arithmetic
# ---------------------------------------------------------------------------

def _gate_met(current_band: str, target_band: str, n_qualifying: int, lifetime_turns: int) -> bool:
    """Check promotion count+turns gates before applying the fraction test."""
    key = f"{current_band}_to_{target_band}"
    gate = _PROMO_GATES.get(key)
    if gate is None:
        return False
    return (n_qualifying >= gate["min_qualifying_sessions"]
            and lifetime_turns >= gate["min_lifetime_turns"])


def _apply_hysteresis(
    current_band: str,
    fast_window: List[dict],
    slow_window: List[dict],
    meets_next: bool,
    below_floor: bool,
    breadth: int,
    observation_locked: bool,
) -> str:
    """
    Given the current band and evidence, return the new band.
    Promotion: requires fraction gate + NOT in observation window.
    Demotion: uses a longer window and a higher fraction.
    """
    idx = _BAND_IDX[current_band]

    # Try promotion (cannot jump more than one band per call)
    if idx < len(BANDS) - 1 and meets_next and not observation_locked:
        candidate = BANDS[idx + 1]
        # Engine breadth gate
        if candidate in ("Consolidating", "Steady"):
            req = _BREADTH_STEADY if candidate == "Steady" else _BREADTH_CONSOLIDATING
            if breadth < req:
                return current_band
        return candidate

    # Try demotion
    if idx > 0 and below_floor:
        return BANDS[idx - 1]

    return current_band


# ---------------------------------------------------------------------------
# Per-dimension band computators
# ---------------------------------------------------------------------------

def _band_sustained_conversation(qualifying: List[dict], n_qual: int, lifetime_turns: int,
                                  observation_locked: bool, breadth: int,
                                  current_band: str = "Emerging") -> str:
    cfg = _DIM_CFG["sustained_conversation"]
    win = _WIN_SLOW
    window = qualifying[-win:]
    fast_win = qualifying[-_WIN_FAST:]

    floor_dev  = cfg["band_floors"]["Developing"]["median_turns_per_session"]
    floor_cons = cfg["band_floors"]["Consolidating"]["median_turns_per_session"]
    floor_ste  = cfg["band_floors"]["Steady"]["median_turns_per_session"]

    turns_seq = [_safe_int(s.get("total_turns")) for s in window]
    median_turns = _median_or([float(t) for t in turns_seq])

    if current_band == "Emerging":
        if not _gate_met("Emerging", "Developing", n_qual, lifetime_turns):
            return "Emerging"
        meets = _fraction_meeting([t >= floor_dev for t in turns_seq]) >= _PROMO_FRAC
        return _apply_hysteresis("Emerging", fast_win, window, meets, False, breadth, observation_locked)

    if current_band == "Developing":
        if not _gate_met("Developing", "Consolidating", n_qual, lifetime_turns):
            # Check demotion: last (win+3) sessions mostly below floor
            dwin = qualifying[-(win + 3):]
            below = _fraction_meeting([_safe_int(s.get("total_turns")) < floor_dev for s in dwin]) >= _DEMO_FRAC
            return "Emerging" if below else "Developing"
        meets = _fraction_meeting([t >= floor_cons for t in turns_seq]) >= _PROMO_FRAC
        dwin = qualifying[-(win + 3):]
        below = _fraction_meeting([_safe_int(s.get("total_turns")) < floor_dev for s in dwin]) >= _DEMO_FRAC
        return _apply_hysteresis("Developing", fast_win, window, meets, below, breadth, observation_locked)

    if current_band == "Consolidating":
        if not _gate_met("Consolidating", "Steady", n_qual, lifetime_turns):
            dwin = qualifying[-(win + 3):]
            below = _fraction_meeting([_safe_int(s.get("total_turns")) < floor_cons for s in dwin]) >= _DEMO_FRAC
            return "Developing" if below else "Consolidating"
        meets = _fraction_meeting([t >= floor_ste for t in turns_seq]) >= _PROMO_FRAC
        dwin = qualifying[-(win + 3):]
        below = _fraction_meeting([_safe_int(s.get("total_turns")) < floor_cons for s in dwin]) >= _DEMO_FRAC
        return _apply_hysteresis("Consolidating", fast_win, window, meets, below, breadth, observation_locked)

    # Steady — only demotion possible
    dwin = qualifying[-(win + 3):]
    below = _fraction_meeting([_safe_int(s.get("total_turns")) < floor_ste for s in dwin]) >= _DEMO_FRAC
    return "Consolidating" if below else "Steady"


def _band_recovery_resilience(qualifying: List[dict], n_qual: int, lifetime_turns: int,
                               observation_locked: bool, breadth: int,
                               current_band: str = "Emerging") -> str:
    cfg = _DIM_CFG["recovery_resilience"]
    win = _WIN_FAST
    window = qualifying[-win:]

    floor_dev  = cfg["band_floors"]["Developing"]["unclear_rate_max"]
    floor_cons = cfg["band_floors"]["Consolidating"]["unclear_rate_max"]
    floor_ste  = cfg["band_floors"]["Steady"]["unclear_rate_max"]

    rates = [_unclear_rate(s) for s in window]

    if current_band == "Emerging":
        if not _gate_met("Emerging", "Developing", n_qual, lifetime_turns):
            return "Emerging"
        # Developing: session that had any unclear but did not quit (total_turns >= 6 already)
        meets = _fraction_meeting([r <= floor_dev for r in rates]) >= _PROMO_FRAC
        return _apply_hysteresis("Emerging", window, window, meets, False, breadth, observation_locked)

    if current_band == "Developing":
        if not _gate_met("Developing", "Consolidating", n_qual, lifetime_turns):
            dwin = qualifying[-(win + 3):]
            below = _fraction_meeting([_unclear_rate(s) > floor_dev for s in dwin]) >= _DEMO_FRAC
            return "Emerging" if below else "Developing"
        meets = _fraction_meeting([r <= floor_cons for r in rates]) >= _PROMO_FRAC
        dwin = qualifying[-(win + 3):]
        below = _fraction_meeting([_unclear_rate(s) > floor_dev for s in dwin]) >= _DEMO_FRAC
        return _apply_hysteresis("Developing", window, window, meets, below, breadth, observation_locked)

    if current_band == "Consolidating":
        if not _gate_met("Consolidating", "Steady", n_qual, lifetime_turns):
            dwin = qualifying[-(win + 3):]
            below = _fraction_meeting([_unclear_rate(s) > floor_cons for s in dwin]) >= _DEMO_FRAC
            return "Developing" if below else "Consolidating"
        meets = _fraction_meeting([r <= floor_ste for r in rates]) >= _PROMO_FRAC
        dwin = qualifying[-(win + 3):]
        below = _fraction_meeting([_unclear_rate(s) > floor_cons for s in dwin]) >= _DEMO_FRAC
        return _apply_hysteresis("Consolidating", window, window, meets, below, breadth, observation_locked)

    dwin = qualifying[-(win + 3):]
    below = _fraction_meeting([_unclear_rate(s) > floor_ste for s in dwin]) >= _DEMO_FRAC
    return "Consolidating" if below else "Steady"


def _band_conversational_initiative(qualifying: List[dict], n_qual: int, lifetime_turns: int,
                                     observation_locked: bool, breadth: int,
                                     current_band: str = "Emerging") -> str:
    cfg = _DIM_CFG["conversational_initiative"]
    win = _WIN_SLOW
    window = qualifying[-win:]

    floor_dev  = cfg["band_floors"]["Developing"]["min_questions_asked_median"]
    floor_cons = cfg["band_floors"]["Consolidating"]["min_questions_asked_median"]
    floor_ste  = cfg["band_floors"]["Steady"]["min_questions_asked_median"]

    q_counts = [float(_safe_int(s.get("questions_asked"))) for s in window]
    median_q = _median_or(q_counts)

    def _meets(floor: float) -> bool:
        return _fraction_meeting([q >= floor for q in q_counts]) >= _PROMO_FRAC

    def _below(floor: float) -> bool:
        dwin = qualifying[-(win + 3):]
        d_counts = [float(_safe_int(s.get("questions_asked"))) for s in dwin]
        return _fraction_meeting([q < floor for q in d_counts]) >= _DEMO_FRAC

    if current_band == "Emerging":
        if not _gate_met("Emerging", "Developing", n_qual, lifetime_turns):
            return "Emerging"
        return _apply_hysteresis("Emerging", window, window, _meets(floor_dev), False, breadth, observation_locked)

    if current_band == "Developing":
        if not _gate_met("Developing", "Consolidating", n_qual, lifetime_turns):
            return "Emerging" if _below(floor_dev) else "Developing"
        return _apply_hysteresis("Developing", window, window, _meets(floor_cons), _below(floor_dev), breadth, observation_locked)

    if current_band == "Consolidating":
        if not _gate_met("Consolidating", "Steady", n_qual, lifetime_turns):
            return "Developing" if _below(floor_cons) else "Consolidating"
        return _apply_hysteresis("Consolidating", window, window, _meets(floor_ste), _below(floor_cons), breadth, observation_locked)

    return "Consolidating" if _below(floor_ste) else "Steady"


def _band_independence(qualifying: List[dict], n_qual: int, lifetime_turns: int,
                        observation_locked: bool, breadth: int,
                        current_band: str = "Emerging") -> str:
    cfg = _DIM_CFG["independence"]
    win = _WIN_SLOW
    window = qualifying[-win:]

    ceil_dev  = cfg["band_floors"]["Developing"]["support_rate_per_turn_max"]
    ceil_cons = cfg["band_floors"]["Consolidating"]["support_rate_per_turn_max"]
    ceil_ste  = cfg["band_floors"]["Steady"]["support_rate_per_turn_max"]

    rates = [_support_rate(s) for s in window]

    def _meets(ceil: float) -> bool:
        return _fraction_meeting([r <= ceil for r in rates]) >= _PROMO_FRAC

    def _below(ceil: float) -> bool:
        dwin = qualifying[-(win + 3):]
        d_rates = [_support_rate(s) for s in dwin]
        return _fraction_meeting([r > ceil for r in d_rates]) >= _DEMO_FRAC

    if current_band == "Emerging":
        if not _gate_met("Emerging", "Developing", n_qual, lifetime_turns):
            return "Emerging"
        return _apply_hysteresis("Emerging", window, window, _meets(ceil_dev), False, breadth, observation_locked)

    if current_band == "Developing":
        if not _gate_met("Developing", "Consolidating", n_qual, lifetime_turns):
            return "Emerging" if _below(ceil_dev) else "Developing"
        return _apply_hysteresis("Developing", window, window, _meets(ceil_cons), _below(ceil_dev), breadth, observation_locked)

    if current_band == "Consolidating":
        if not _gate_met("Consolidating", "Steady", n_qual, lifetime_turns):
            return "Developing" if _below(ceil_cons) else "Consolidating"
        return _apply_hysteresis("Consolidating", window, window, _meets(ceil_ste), _below(ceil_cons), breadth, observation_locked)

    return "Consolidating" if _below(ceil_ste) else "Steady"


def _band_conversational_stability(qualifying: List[dict], n_qual: int, lifetime_turns: int,
                                    observation_locked: bool, breadth: int,
                                    current_band: str = "Emerging") -> str:
    cfg = _DIM_CFG["conversational_stability"]
    win = _WIN_FAST
    window = qualifying[-win:]

    floor_dev  = cfg["band_floors"]["Developing"]["min_stability_score"]
    floor_cons = cfg["band_floors"]["Consolidating"]["min_stability_score"]
    floor_ste  = cfg["band_floors"]["Steady"]["min_stability_score"]

    scores = [
        _safe_float(s.get("conversation_stability_score"))
        for s in window
        if s.get("conversation_stability_score") is not None
    ]

    def _meets(floor: float) -> bool:
        return bool(scores) and _fraction_meeting([sc >= floor for sc in scores]) >= _PROMO_FRAC

    def _below(floor: float) -> bool:
        dwin = qualifying[-(win + 3):]
        d_scores = [
            _safe_float(s.get("conversation_stability_score"))
            for s in dwin
            if s.get("conversation_stability_score") is not None
        ]
        if not d_scores:
            return False
        return _fraction_meeting([sc < floor for sc in d_scores]) >= _DEMO_FRAC

    if current_band == "Emerging":
        if not _gate_met("Emerging", "Developing", n_qual, lifetime_turns):
            return "Emerging"
        return _apply_hysteresis("Emerging", window, window, _meets(floor_dev), False, breadth, observation_locked)

    if current_band == "Developing":
        if not _gate_met("Developing", "Consolidating", n_qual, lifetime_turns):
            return "Emerging" if _below(floor_dev) else "Developing"
        return _apply_hysteresis("Developing", window, window, _meets(floor_cons), _below(floor_dev), breadth, observation_locked)

    if current_band == "Consolidating":
        if not _gate_met("Consolidating", "Steady", n_qual, lifetime_turns):
            return "Developing" if _below(floor_cons) else "Consolidating"
        return _apply_hysteresis("Consolidating", window, window, _meets(floor_ste), _below(floor_cons), breadth, observation_locked)

    return "Consolidating" if _below(floor_ste) else "Steady"


# ---------------------------------------------------------------------------
# Trend notes (human-readable; conservative)
# ---------------------------------------------------------------------------

def _trend_notes(qualifying: List[dict], dimensions: Dict[str, str]) -> List[str]:
    notes: List[str] = []
    if not qualifying:
        return notes

    # Initiative trend
    q_counts = [_safe_int(s.get("questions_asked")) for s in qualifying[-5:]]
    if len(q_counts) >= 3 and q_counts[-1] > q_counts[0]:
        notes.append("You've been asking more questions back — initiative is growing.")
    elif dimensions["conversational_initiative"] == "Emerging" and len(qualifying) >= 3:
        notes.append("Asking a question back each session will build initiative faster.")

    # Independence trend
    r_recent = [_support_rate(s) for s in qualifying[-3:]]
    r_older  = [_support_rate(s) for s in qualifying[-8:-3]] if len(qualifying) >= 8 else []
    if r_recent and r_older and _median_or(r_recent) < _median_or(r_older) * 0.8:
        notes.append("Support use is trending down — independence is improving.")
    elif dimensions["independence"] == "Emerging":
        notes.append("Trying to answer without hints will strengthen independence.")

    # Recovery
    if dimensions["recovery_resilience"] in ("Consolidating", "Steady"):
        notes.append("Recovery resilience is solid — you keep going through difficult moments.")

    # Stability plateau warning
    if dimensions["conversational_stability"] == "Emerging" and len(qualifying) >= 5:
        notes.append("Stability is still emerging — shorter, clearer sessions can help.")

    return notes[:3]


# ---------------------------------------------------------------------------
# Progress-toward-next-band (0.0 – 1.0 float, informational)
# ---------------------------------------------------------------------------

def _next_band_progress(current_band: str, n_qual: int, lifetime_turns: int) -> float:
    """Fraction of the way to the next band's count gate, 0–1. Informational only."""
    if current_band == "Steady":
        return 1.0
    idx = _BAND_IDX[current_band]
    next_band = BANDS[idx + 1]
    key = f"{current_band}_to_{next_band}"
    gate = _PROMO_GATES.get(key, {})
    req_sess = gate.get("min_qualifying_sessions", 1)
    req_turns = gate.get("min_lifetime_turns", 1)
    sess_frac  = min(1.0, n_qual / req_sess)
    turns_frac = min(1.0, lifetime_turns / req_turns)
    return round(min(sess_frac, turns_frac), 2)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute(snapshots: List[dict]) -> Dict[str, Any]:
    """
    Derive a CapabilityState from the learner's full snapshot history.

    Parameters
    ----------
    snapshots : list of dict
        All historical progress snapshots for one learner (oldest first),
        as returned by progress_store.load_snapshots().

    Returns
    -------
    dict
        CapabilityState — safe to serialise as JSON.
        Never contains an aggregate capability score.
    """
    qualifying = [s for s in snapshots if _is_qualifying(s)]
    n_qual = len(qualifying)
    lifetime_turns = sum(_safe_int(s.get("total_turns")) for s in qualifying)
    breadth = len(_engines_seen(qualifying))

    inactive, inactivity_days = _compute_inactivity(qualifying)
    obs_locked = _observation_lock(qualifying)

    # Derive bands for each dimension independently
    # All start at Emerging and advance through the evidence in qualifying sessions.
    # (In a future version with persistent CapabilityState cache, we would load the
    # previous bands from storage. For v1, recompute from scratch — cheap and correct.)

    dims: Dict[str, str] = {
        "sustained_conversation":    "Emerging",
        "recovery_resilience":       "Emerging",
        "conversational_initiative": "Emerging",
        "independence":              "Emerging",
        "conversational_stability":  "Emerging",
    }

    if qualifying:
        dims["sustained_conversation"]    = _band_sustained_conversation(
            qualifying, n_qual, lifetime_turns, obs_locked, breadth)
        dims["recovery_resilience"]       = _band_recovery_resilience(
            qualifying, n_qual, lifetime_turns, obs_locked, breadth)
        dims["conversational_initiative"] = _band_conversational_initiative(
            qualifying, n_qual, lifetime_turns, obs_locked, breadth)
        dims["independence"]              = _band_independence(
            qualifying, n_qual, lifetime_turns, obs_locked, breadth)
        dims["conversational_stability"]  = _band_conversational_stability(
            qualifying, n_qual, lifetime_turns, obs_locked, breadth)

    notes = _trend_notes(qualifying, dims)

    try:
        computed_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        computed_at = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    dimensions_out = {}
    for dim_name, band in dims.items():
        dimensions_out[dim_name] = {
            "band": band,
            "evidence_sessions": n_qual,
            "next_band_progress": _next_band_progress(band, n_qual, lifetime_turns),
        }

    return {
        "computed_at":              computed_at,
        "heuristic_version":        HEURISTIC_VERSION,
        "qualifying_session_count": n_qual,
        "lifetime_turn_count":      lifetime_turns,
        "engine_breadth":           breadth,
        "inactive":                 inactive,
        "inactivity_days":          inactivity_days,
        "observation_locked":       obs_locked,
        "dimensions":               dimensions_out,
        "trend_notes":              notes,
    }
