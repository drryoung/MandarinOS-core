#!/usr/bin/env python3
"""
Blue-panel conversational momentum — additive adjacency heuristics.

Ensures occupation disclosures (e.g. 软件开发) rank work follow-ups, not identity drift.
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


def test_text_signals_work_occupation_software_dev():
    srv = _load_ui_server()
    assert srv._text_signals_work_occupation("我是做软件开发的。") is True
    assert srv._text_signals_work_occupation("你好") is False


def test_work_disclosure_pool_prefers_work_followups():
    """Context 我是做软件开发的 should surface work topics, not 你是哪里人."""
    srv = _load_ui_server()
    backed = frozenset(
        {"work_duration", "work_like", "work_why", "work_what", "place_from"},
    )
    pool = srv._build_discovery_pool(
        "work",
        backed,
        ["work", "identity"],
        set(),
        frame_text="",
        context_text="我是做软件开发的。",
    )
    assert pool, "expected non-empty discovery pool"
    top3_zh = [(q.get("zh") or "") for q in pool[:3]]
    workish = any(
        any(tok in zh for tok in ("工作", "多久", "喜欢", "为什么"))
        for zh in top3_zh
    )
    assert workish, f"expected work follow-ups in top 3, got {top3_zh!r}"
    assert not any("哪里人" in zh for zh in top3_zh), f"identity drift: {top3_zh!r}"


def test_discovery_relevance_boosts_work_on_software_context():
    srv = _load_ui_server()
    ctx = "我是做软件开发的。"
    dur = {"zh": "你做这份工作多久了？", "topic": "work_duration", "curiosity": True}
    place = {"zh": "你是哪里人？", "topic": "place_from", "curiosity": True}
    assert srv._discovery_relevance_score(dur, "", ctx) >= srv._discovery_relevance_score(
        place, "", ctx,
    )


def test_persona_reveal_keywords_include_software_work():
    srv = _load_ui_server()
    assert srv._has_persona_reveal("我是做软件开发的，已经五年了。") is True
