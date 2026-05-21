#!/usr/bin/env python3
"""
Blue-panel local conversational probing — learner-answer adjacency heuristics.

Verifies that recent learner disclosures boost locally relevant follow-up topics
(place/work/family/travel/food) before generic discovery fallbacks.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"


def _load_ui_server():
    spec = importlib.util.spec_from_file_location("ui_server", _SCRIPTS / "ui_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ui_server"] = mod
    spec.loader.exec_module(mod)
    return mod


def _pool_top3(srv, engine, context_text, boost=None):
    backed = frozenset({
        "place_like", "place_why_like", "place_food", "place_special",
        "work_duration", "work_like", "work_why", "work_interesting",
        "family_live", "family_weekend", "marriage", "children", "family_size",
        "travel_why_fav", "travel_next", "place_never_been", "travel_fav",
        "food_fav", "food_why_like", "food_cook", "food_spicy",
        "place_from", "name_meaning",
    })
    local_boost = srv._infer_local_probe_boost_topics(context_text)
    boost_topics = (boost or frozenset()) | local_boost
    resolved = srv._resolve_discovery_engine_for_context(
        engine, context_text, overseas_detected=False,
    )
    pool = srv._build_discovery_pool(
        resolved, backed, ["place", "work", "family", "travel", "food", "identity"],
        set(),
        boost_topics=boost_topics,
        frame_text="",
        context_text=context_text,
    )
    return resolved, [(q.get("topic") or "", q.get("zh") or "") for q in pool[:3]]


def test_infer_local_probe_suzhou_work():
    srv = _load_ui_server()
    topics = srv._infer_local_probe_boost_topics("我以前在苏州工作")
    assert "place_like" in topics
    assert "work_duration" in topics
    assert "work_like" in topics


def test_infer_local_probe_family_living():
    srv = _load_ui_server()
    topics = srv._infer_local_probe_boost_topics("我跟爸爸妈妈和老婆住在一起")
    assert "family_live" in topics
    assert "family_weekend" in topics or "marriage" in topics


def test_infer_local_probe_travel_intent():
    srv = _load_ui_server()
    topics = srv._infer_local_probe_boost_topics("我想去甘肃")
    assert "travel_next" in topics or "travel_why_fav" in topics


def test_infer_local_probe_food():
    srv = _load_ui_server()
    topics = srv._infer_local_probe_boost_topics("这里牛肉羊肉很好吃")
    assert "food_fav" in topics
    assert "food_why_like" in topics


def test_infer_local_probe_empty_is_generic():
    srv = _load_ui_server()
    assert srv._infer_local_probe_boost_topics("") == frozenset()
    assert srv._infer_local_probe_boost_topics("你好") == frozenset()


def test_suzhou_work_pool_prefers_place_and_work_probes():
    srv = _load_ui_server()
    eng, top3 = _pool_top3(srv, "identity", "我以前在苏州工作")
    assert eng == "work", f"expected work engine, got {eng!r}"
    topics = {t for t, _ in top3}
    assert topics & {"work_duration", "work_like", "place_like", "place_food", "place_why_like"}, (
        f"expected place/work probes in top 3, got {top3!r}"
    )
    assert "name_meaning" not in topics and "place_from" not in topics, (
        f"generic identity drift: {top3!r}"
    )


def test_family_living_pool_prefers_family_probes():
    srv = _load_ui_server()
    eng, top3 = _pool_top3(srv, "identity", "我跟爸爸妈妈和老婆住在一起")
    assert eng == "family", f"expected family engine, got {eng!r}"
    topics = {t for t, _ in top3}
    assert topics & {"family_live", "family_weekend", "marriage", "family_size"}, (
        f"expected family probes in top 3, got {top3!r}"
    )


def test_travel_intent_pool_prefers_destination_probes():
    srv = _load_ui_server()
    eng, top3 = _pool_top3(srv, "place", "我想去甘肃")
    assert eng == "travel", f"expected travel engine, got {eng!r}"
    topics = {t for t, _ in top3}
    assert topics & {"travel_next", "travel_why_fav", "place_never_been", "travel_fav"}, (
        f"expected travel probes in top 3, got {top3!r}"
    )


def test_food_mention_pool_prefers_food_probes():
    srv = _load_ui_server()
    eng, top3 = _pool_top3(srv, "place", "这里牛肉羊肉很好吃")
    assert eng == "food", f"expected food engine, got {eng!r}"
    topics = {t for t, _ in top3}
    assert topics & {"food_fav", "food_why_like", "food_cook"}, (
        f"expected food probes in top 3, got {top3!r}"
    )


def test_generic_fallback_when_no_affordance():
    srv = _load_ui_server()
    eng, top3 = _pool_top3(srv, "identity", "好的")
    assert eng == "identity"
    assert len(top3) >= 1, "expected non-empty generic pool"


def test_work_momentum_regression():
    """Prior work-adjacency behavior must remain intact."""
    srv = _load_ui_server()
    _, top3 = _pool_top3(srv, "work", "我是做软件开发的。")
    topics = {t for t, _ in top3}
    assert topics & {"work_duration", "work_like", "work_why"}, (
        f"work regression: {top3!r}"
    )
