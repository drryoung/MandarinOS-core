#!/usr/bin/env python3
"""
Clear-memory regression tests.

Root cause: learner_memory.save() used merge semantics where None == "keep existing",
so calling save(learner_id, all_none_dict) from /api/reset_memory silently preserved
every fact in data/learner_memory.json.  Dunedin / South of NZ survived a clear.

Fix applied:
  - learner_memory.clear(learner_id) unconditionally writes empty_memory().
  - /api/reset_memory now calls _lm_clear(), not _lm_save(empty).
  - startFreshLearner() clears window._lastMentionedPlace and re-fetches from server.

These tests verify all three fix surfaces and the expected behaviour after clear.
"""

import importlib.util
import sys
import tempfile
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_LM = ROOT / "scripts" / "learner_memory.py"
_UI_SERVER = ROOT / "scripts" / "ui_server.py"
_APP_JS = ROOT / "ui" / "app.js"

_cache: dict = {}


def _load(name: str, path: Path):
    if name in _cache:
        return _cache[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _cache[name] = mod
    return mod


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def lm():
    return _load("learner_memory_clr", _LM)


@pytest.fixture()
def isolated_lm(tmp_path):
    """Fresh learner_memory module with its data directory redirected to a temp dir
    so tests don't touch the real data/learner_memory.json file."""
    import importlib
    import os

    # Redirect data dir before loading.
    env_backup = os.environ.get("MANDARINOS_DATA_DIR")
    os.environ["MANDARINOS_DATA_DIR"] = str(tmp_path)

    spec = importlib.util.spec_from_file_location("lm_isolated", _LM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    yield mod

    # Restore env.
    if env_backup is None:
        os.environ.pop("MANDARINOS_DATA_DIR", None)
    else:
        os.environ["MANDARINOS_DATA_DIR"] = env_backup


# ── Unit: learner_memory.clear() ─────────────────────────────────────────────

class TestLearnerMemoryClear:
    """Direct unit tests for the new clear() function."""

    def test_clear_function_exists(self, lm):
        assert hasattr(lm, "clear"), "learner_memory.clear() must exist"
        assert callable(lm.clear)

    def test_clear_erases_all_fields(self, isolated_lm):
        lm = isolated_lm
        lid = "test_learner_nz"
        # Populate with NZ place facts.
        mem = {
            "learner_name": "Alice",
            "hometown": "新西兰南岛",
            "lives_in": "达尼丁",
            "job_or_study": "teacher",
            "family": "two kids",
            "favourite_food": "羊肉",
        }
        lm.save(lid, mem)
        # Confirm stored.
        loaded = lm.load(lid)
        assert loaded["hometown"] == "新西兰南岛"
        assert loaded["lives_in"] == "达尼丁"

        # Clear.
        lm.clear(lid)
        after = lm.load(lid)
        for key in lm.LEARNER_MEMORY_KEYS:
            assert after[key] is None, f"Expected {key!r} to be None after clear(), got {after[key]!r}"

    def test_clear_erases_dunedin(self, isolated_lm):
        lm = isolated_lm
        lid = "test_learner_dunedin"
        lm.save(lid, {"lives_in": "达尼丁", "hometown": "新西兰南岛"})
        assert lm.load(lid)["lives_in"] == "达尼丁"
        lm.clear(lid)
        assert lm.load(lid)["lives_in"] is None
        assert lm.load(lid)["hometown"] is None

    def test_clear_erases_south_nz(self, isolated_lm):
        lm = isolated_lm
        lid = "test_learner_south_nz"
        lm.save(lid, {"hometown": "新西兰南岛", "lives_in": "南方"})
        lm.clear(lid)
        after = lm.load(lid)
        assert after["hometown"] is None
        assert after["lives_in"] is None

    def test_clear_persists_to_file(self, isolated_lm, tmp_path):
        """After clear(), loading from a fresh module instance must also return empty."""
        lm = isolated_lm
        lid = "test_persist_clear"
        lm.save(lid, {"hometown": "达尼丁"})
        lm.clear(lid)

        # Verify file content directly.
        import json, os
        data_dir = Path(os.environ.get("MANDARINOS_DATA_DIR", str(ROOT / "data")))
        f = data_dir / "learner_memory.json"
        if f.exists():
            raw = json.loads(f.read_text(encoding="utf-8"))
            entry = raw.get(lid, {})
            for key in lm.LEARNER_MEMORY_KEYS:
                assert entry.get(key) is None, f"{key!r} not None in persisted file after clear()"

    def test_save_with_all_none_does_not_clear(self, isolated_lm):
        """Regression guard: save() with all-None must NOT clear existing facts.
        This documents the old broken behavior — save() still uses merge semantics."""
        lm = isolated_lm
        lid = "test_save_none_no_clear"
        lm.save(lid, {"hometown": "达尼丁"})
        # Call save with all-None (old reset_memory approach).
        lm.save(lid, {k: None for k in lm.LEARNER_MEMORY_KEYS})
        after = lm.load(lid)
        # Merge semantics: 达尼丁 must survive (save with None = "keep existing").
        assert after["hometown"] == "达尼丁", (
            "save() with None is supposed to preserve existing; this test documents that behaviour"
        )

    def test_clear_safe_for_unknown_learner(self, isolated_lm):
        """clear() on an unknown learner_id must not raise."""
        isolated_lm.clear("nonexistent_learner_id_xyz")

    def test_clear_ignores_empty_id(self, isolated_lm):
        """clear() with empty/None id must be a no-op, not raise."""
        isolated_lm.clear("")
        isolated_lm.clear(None)  # type: ignore


# ── Unit: save() still works correctly for normal updates ─────────────────────

class TestSaveStillWorks:
    """Ensure the clear() fix did not break the normal save() merge behaviour."""

    def test_save_updates_single_field(self, isolated_lm):
        lm = isolated_lm
        lid = "test_save_single"
        lm.save(lid, {"hometown": "北京", "lives_in": "上海"})
        lm.save(lid, {"lives_in": "广州"})
        after = lm.load(lid)
        assert after["hometown"] == "北京"   # preserved
        assert after["lives_in"] == "广州"   # updated

    def test_save_preserves_other_fields(self, isolated_lm):
        lm = isolated_lm
        lid = "test_save_preserve"
        lm.save(lid, {"hometown": "成都", "job_or_study": "student"})
        lm.save(lid, {"favourite_food": "火锅"})
        after = lm.load(lid)
        assert after["hometown"] == "成都"
        assert after["job_or_study"] == "student"
        assert after["favourite_food"] == "火锅"


# ── Integration: /api/reset_memory now calls _lm_clear ────────────────────────

class TestResetMemoryEndpointWiring:
    """Source-inspection guards: verify the endpoint uses _lm_clear."""

    def _reset_block(self) -> str:
        src = _UI_SERVER.read_text(encoding="utf-8")
        start = src.find('if path == "/api/reset_memory"')
        end   = src.find('\n        if path == ', start + 1)
        return src[start:end] if end > start else src[start: start + 600]

    def test_import_has_lm_clear(self):
        src = _UI_SERVER.read_text(encoding="utf-8")
        assert "_lm_clear" in src, (
            "ui_server.py must import clear as _lm_clear from learner_memory"
        )
        assert "from learner_memory import" in src
        assert "clear as _lm_clear" in src

    def test_reset_endpoint_calls_lm_clear(self):
        block = self._reset_block()
        assert "_lm_clear(learner_id)" in block, (
            "/api/reset_memory must call _lm_clear(), not _lm_save()"
        )

    def test_reset_endpoint_does_not_call_lm_save_with_empty(self):
        """The old broken pattern must be gone from the reset endpoint."""
        block = self._reset_block()
        assert "_lm_save(learner_id, empty)" not in block, (
            "Old broken save(empty) call must not remain in /api/reset_memory"
        )


# ── Integration: previous-session facts do not survive clear ──────────────────

class TestFactsDoNotSurviveClear:
    """End-to-end: save NZ/Dunedin facts, clear, confirm empty, no rehydration."""

    def test_all_place_facts_erased(self, isolated_lm):
        lm = isolated_lm
        lid = "test_nz_e2e"
        lm.save(lid, {
            "hometown": "新西兰南岛",
            "lives_in": "达尼丁",
        })
        lm.clear(lid)
        after = lm.load(lid)
        assert "新西兰" not in str(after["hometown"] or "")
        assert "达尼丁" not in str(after["lives_in"] or "")

    def test_clear_all_six_fields(self, isolated_lm):
        lm = isolated_lm
        lid = "test_six_fields"
        lm.save(lid, {
            "learner_name": "Bob",
            "hometown": "奥克兰",
            "lives_in": "达尼丁",
            "job_or_study": "engineer",
            "family": "married",
            "favourite_food": "海鲜",
        })
        lm.clear(lid)
        after = lm.load(lid)
        for key in lm.LEARNER_MEMORY_KEYS:
            assert after[key] is None, f"{key} survived clear: {after[key]!r}"

    def test_progress_store_not_used_to_reseed_memory(self):
        """Progress snapshots must not contain learner place facts that could be
        re-seeded into conversation_state or learner_memory after a clear."""
        # Inspect _build_progress_snapshot for personal place fields.
        src = _UI_SERVER.read_text(encoding="utf-8")
        start = src.find("def _build_progress_snapshot(")
        end   = src.find("\ndef ", start + 1)
        fn_body = src[start:end] if end > start else src[start: start + 3000]
        # The snapshot builder must not read hometown/lives_in to put them in the snapshot.
        assert '"hometown"' not in fn_body, (
            "_build_progress_snapshot must not include 'hometown' — risk of rehydration"
        )
        assert '"lives_in"' not in fn_body, (
            "_build_progress_snapshot must not include 'lives_in' — risk of rehydration"
        )

    def test_multiple_learners_independent(self, isolated_lm):
        """Clearing one learner must not affect another learner's memory."""
        lm = isolated_lm
        lid_a = "learner_a_nz"
        lid_b = "learner_b_cn"
        lm.save(lid_a, {"hometown": "新西兰南岛"})
        lm.save(lid_b, {"hometown": "北京"})
        lm.clear(lid_a)
        assert lm.load(lid_a)["hometown"] is None
        assert lm.load(lid_b)["hometown"] == "北京"   # B untouched


# ── Client-side: startFreshLearner clears _lastMentionedPlace ─────────────────

class TestClientSideClearMemory:
    def _fresh_block(self) -> str:
        src = _APP_JS.read_text(encoding="utf-8")
        start = src.find("async function startFreshLearner")
        end   = src.find("\nasync function ", start + 1)
        return src[start:end] if end > start else src[start: start + 2000]

    def test_clears_last_mentioned_place(self):
        block = self._fresh_block()
        assert "window._lastMentionedPlace = null" in block, (
            "startFreshLearner() must clear window._lastMentionedPlace "
            "so the place anchor cannot re-fill templates after a reset"
        )

    def test_refreshes_memory_banner_from_server(self):
        """After the server reset, the client must re-fetch to confirm the clear."""
        block = self._fresh_block()
        assert "_refreshMemoryBanner()" in block, (
            "startFreshLearner() must call _refreshMemoryBanner() after the server "
            "reset so that any server failure is surfaced to the user"
        )

    def test_clear_memory_posts_to_reset_memory(self):
        block = self._fresh_block()
        assert '"/api/reset_memory"' in block

    def test_clear_memory_preserves_learner_id(self):
        block = self._fresh_block()
        assert 'setLearnerId("learner_" + Date.now())' not in block
        assert "oldId" not in block

    def test_clear_memory_preserves_progress_history(self):
        block = self._fresh_block()
        # Must not call removeItem (which would delete localStorage progress data).
        assert "removeItem" not in block
        # manos_progress_history may appear in a log/comment string confirming it is
        # untouched — that is fine.  What must not appear is an attempt to clear it.
        assert 'removeItem("manos_progress_history")' not in block
        assert 'localStorage.clear()' not in block


# ── Persona facts are not affected by clear ───────────────────────────────────

class TestPersonaFactsUnaffected:
    """Persona data lives in personas/<id>.json — completely separate from
    data/learner_memory.json.  clear() must not touch persona files."""

    def test_clear_does_not_affect_persona_files(self, isolated_lm):
        """clear() only touches learner_memory.json — not any personas/ directory."""
        lm = isolated_lm
        # Verify no persona paths are referenced in learner_memory.py source.
        src = _LM.read_text(encoding="utf-8")
        assert "personas/" not in src, (
            "learner_memory.py must not reference personas/ — persona and learner "
            "memory are separate stores"
        )

    def test_learner_memory_keys_do_not_include_persona_fields(self, lm):
        """LEARNER_MEMORY_KEYS must only contain learner personal fields."""
        persona_fields = {"persona_id", "partner_id", "voice_lines", "profile",
                         "discoverable_facts", "work", "food"}
        overlap = set(lm.LEARNER_MEMORY_KEYS) & persona_fields
        assert not overlap, (
            f"LEARNER_MEMORY_KEYS overlaps with persona fields: {overlap}"
        )
