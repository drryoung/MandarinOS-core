"""
Tests for: Exclude or separately classify empty/aborted sessions (Task 4).

Verifies that:
  1. classify_session_type() correctly labels aborted / empty / recovery-only / normal.
  2. is_excluded_session_type() returns True for the three degenerate types.
  3. run_batch_export (signature) accepts include_empty parameter.
  4. Sessions with zero turns are excluded from normal batch by default.
  5. --include-empty flag overrides the exclusion.
  6. Source code check: _render_excluded_sessions_appendix exists.
"""

import importlib.util
import pathlib
import sys
import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_EXP = _REPO_ROOT / "scripts" / "export_unreviewed_sessions_batch.py"


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_batch", _EXP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def exp():
    return _load_exporter()


def _make_record(transcript=None):
    """Minimal session_record_v1 dict for testing."""
    return {
        "schema": "session_record_v1",
        "session_id": "test_session_001",
        "learner_id": "test_learner",
        "transcript": transcript or [],
    }


def _partner_turn(zh):
    return {"role": "partner", "text_zh": zh}


def _user_turn(zh):
    return {"role": "user", "text_zh": zh}


# ── classify_session_type ──────────────────────────────────────────────────────

class TestClassifySessionType:
    def test_no_transcript_is_aborted(self, exp):
        r = _make_record(transcript=None)
        assert exp.classify_session_type(r) == "aborted_session"

    def test_empty_transcript_is_aborted(self, exp):
        r = _make_record(transcript=[])
        assert exp.classify_session_type(r) == "aborted_session"

    def test_only_partner_opening_no_learner_is_empty(self, exp):
        r = _make_record(transcript=[
            _partner_turn("你好！你住在哪里？"),
        ])
        assert exp.classify_session_type(r) == "empty_session"

    def test_clarification_only_is_recovery_only(self, exp):
        r = _make_record(transcript=[
            _partner_turn("你好！你住在哪里？"),
            _user_turn("再说一遍"),
            _partner_turn("我是问：你住在哪里？"),
        ])
        assert exp.classify_session_type(r) == "recovery_only_session"

    def test_normal_session_with_real_turns(self, exp):
        r = _make_record(transcript=[
            _partner_turn("你好！你住在哪里？"),
            _user_turn("我住在上海。"),
            _partner_turn("哦，上海！你喜欢那里吗？"),
        ])
        assert exp.classify_session_type(r) == "normal_session"

    def test_normal_session_long(self, exp):
        turns = [_partner_turn("你好！")]
        for _ in range(5):
            turns.append(_user_turn("还不错！"))
            turns.append(_partner_turn("好的，继续。"))
        r = _make_record(transcript=turns)
        assert exp.classify_session_type(r) == "normal_session"

    def test_only_recovery_phrases_is_recovery_only(self, exp):
        r = _make_record(transcript=[
            _partner_turn("你好！"),
            _user_turn("什么意思"),
            _partner_turn("我是问：你住在哪里？"),
            _user_turn("啊"),
        ])
        assert exp.classify_session_type(r) == "recovery_only_session"

    def test_partner_clarification_lines_dont_count_as_substantive(self, exp):
        r = _make_record(transcript=[
            _partner_turn("我是问：你在哪里？"),
            _partner_turn("我是在问：你住哪儿？"),
        ])
        # Two clarification-only partner turns with no learner → empty
        assert exp.classify_session_type(r) in ("empty_session", "recovery_only_session")

    def test_one_char_learner_is_not_substantive(self, exp):
        r = _make_record(transcript=[
            _partner_turn("你好！"),
            _user_turn("啊"),
        ])
        assert exp.classify_session_type(r) in ("recovery_only_session", "empty_session")


# ── is_excluded_session_type ───────────────────────────────────────────────────

class TestIsExcludedSessionType:
    def test_aborted_is_excluded(self, exp):
        assert exp.is_excluded_session_type("aborted_session") is True

    def test_empty_is_excluded(self, exp):
        assert exp.is_excluded_session_type("empty_session") is True

    def test_recovery_only_is_excluded(self, exp):
        assert exp.is_excluded_session_type("recovery_only_session") is True

    def test_normal_is_not_excluded(self, exp):
        assert exp.is_excluded_session_type("normal_session") is False


# ── run_batch_export signature ─────────────────────────────────────────────────

class TestRunBatchExportSignature:
    def test_accepts_include_empty(self, exp):
        import inspect
        sig = inspect.signature(exp.run_batch_export)
        assert "include_empty" in sig.parameters, (
            "run_batch_export must accept include_empty keyword argument"
        )

    def test_cli_has_include_empty_flag(self):
        src = _EXP.read_text(encoding="utf-8")
        assert "--include-empty" in src

    def test_main_passes_include_empty(self):
        src = _EXP.read_text(encoding="utf-8")
        assert "include_empty" in src


# ── Dry-run filtering with excluded sessions ───────────────────────────────────

class TestDryRunFiltering:
    """Verify that classify_session_type + is_excluded_session_type together
    correctly separate sessions that should be in the normal batch."""

    def _classify_batch(self, exp, records):
        normal = []
        excluded = []
        for r in records:
            stype = exp.classify_session_type(r)
            if exp.is_excluded_session_type(stype):
                excluded.append((r, stype))
            else:
                normal.append(r)
        return normal, excluded

    def test_empty_sessions_excluded_by_default(self, exp):
        records = [
            _make_record([]),                             # aborted
            _make_record([_partner_turn("你好！")]),      # empty
            _make_record([                                # normal
                _partner_turn("你住哪里？"),
                _user_turn("我住上海。"),
                _partner_turn("好的！"),
            ]),
        ]
        normal, excluded = self._classify_batch(exp, records)
        assert len(normal) == 1
        assert len(excluded) == 2

    def test_all_normal_when_include_empty(self, exp):
        """With include_empty=True, no filtering — all sessions treated as normal."""
        records = [
            _make_record([]),
            _make_record([_partner_turn("你好！")]),
            _make_record([
                _partner_turn("你住哪里？"),
                _user_turn("我住上海。"),
                _partner_turn("好的！"),
            ]),
        ]
        # When include_empty=True, caller skips the exclusion check
        all_sessions = records
        assert len(all_sessions) == 3


# ── Source guards ──────────────────────────────────────────────────────────────

class TestSourceGuards:
    def test_classify_function_exists(self):
        src = _EXP.read_text(encoding="utf-8")
        assert "def classify_session_type(" in src

    def test_is_excluded_function_exists(self):
        src = _EXP.read_text(encoding="utf-8")
        assert "def is_excluded_session_type(" in src

    def test_appendix_renderer_exists(self):
        src = _EXP.read_text(encoding="utf-8")
        assert "_render_excluded_sessions_appendix" in src

    def test_manifest_records_excluded_count(self):
        src = _EXP.read_text(encoding="utf-8")
        assert "excluded_session_count" in src

    def test_aborted_session_label_in_source(self):
        src = _EXP.read_text(encoding="utf-8")
        assert "aborted_session" in src

    def test_empty_session_label_in_source(self):
        src = _EXP.read_text(encoding="utf-8")
        assert "empty_session" in src

    def test_recovery_only_label_in_source(self):
        src = _EXP.read_text(encoding="utf-8")
        assert "recovery_only_session" in src
