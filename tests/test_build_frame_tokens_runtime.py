"""
Phase 7.3 — Golden tests for build_frame_tokens_runtime.
Builder-only tests. No runtime/resolver/SRS changes.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from builders.build_frame_tokens_runtime import tokenize, build_hanzi_lookup


def test_golden_tokenize_known_word():
    """Known word + punct tokenises correctly."""
    lookup = {"你好": "w_nihao"}
    tokens = tokenize("你好！", lookup)
    assert tokens[0] == {"t": "你好", "kind": "word", "word_id": "w_nihao"}
    assert tokens[1] == {"t": "！", "kind": "punct"}
    assert len(tokens) == 2


def test_unknown_token_no_crash():
    """Unknown CJK emits word token without word_id — no crash."""
    lookup = {}
    tokens = tokenize("你好", lookup)
    assert len(tokens) == 2
    for t in tokens:
        assert t["kind"] == "word"
        assert "word_id" not in t


def test_slot_placeholder():
    """Slot placeholder emits slot token."""
    lookup = {}
    tokens = tokenize("我叫{NAME}。", lookup)
    slot_tokens = [t for t in tokens if t.get("kind") == "slot"]
    assert len(slot_tokens) == 1
    assert slot_tokens[0]["slot_name"] == "NAME"
    assert slot_tokens[0]["t"] == "{NAME}"


def test_longest_match_greedy():
    """Greedy longest match preferred over shorter match."""
    lookup = {"你好": "w_nihao", "你": "w_ni"}
    tokens = tokenize("你好", lookup)
    assert len(tokens) == 1
    assert tokens[0]["word_id"] == "w_nihao"


def test_duplicate_hanzi_smallest_word_id():
    """Duplicate hanzi: lexicographically smallest word_id wins."""
    import json, tempfile, os
    from builders.build_frame_tokens_runtime import build_hanzi_lookup
    from pathlib import Path

    data = {"words": [
        {"id": "w_z_second", "hanzi": "你好"},
        {"id": "w_a_first",  "hanzi": "你好"},
    ]}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f)
        tmp = Path(f.name)
    try:
        lookup = build_hanzi_lookup([tmp])
        assert lookup["你好"] == "w_a_first"
    finally:
        tmp.unlink()


def test_deterministic_repeated_runs():
    """Same input produces identical output on repeated calls."""
    lookup = {"你好": "w_nihao", "再见": "w_zaijian"}
    text   = "你好！再见。"
    assert tokenize(text, lookup) == tokenize(text, lookup)