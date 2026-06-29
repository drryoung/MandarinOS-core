"""
Phase 0 Slice 2 — Export session review prompt tests.

Coverage:
  1. Fixture: the sample session_record_v1 used across all tests.
  2. render_review_prompt: all required sections present.
  3. render_review_prompt: metadata values appear in output.
  4. render_review_prompt: transcript lines appear with Chinese text.
  5. render_review_prompt: pinyin and English appear for persona turns.
  6. render_review_prompt: frame_id and turn_uid appear in transcript.
  7. render_review_prompt: missing fields shown as *(not recorded)*.
  8. render_review_prompt: UX event log section present when events exist.
  9. render_review_prompt: event log shows _MISSING when events absent.
 10. render_review_prompt: review tasks section includes all eight subsections.
 11. render_review_prompt: product_intel_v1 schema name appears in tasks.
 12. export_from_path: round-trip from temp file.
 13. export_from_path write=True: file created at auto-derived path.
 14. export_from_path write=True, explicit --out: file created at that path.
 15. export_from_path: non-existent file raises FileNotFoundError.
 16. export_from_path: invalid JSON raises json.JSONDecodeError.
 17. export_from_path: JSON array raises ValueError.
 18. Empty transcript: section shows *(not recorded)* gracefully.
 19. Empty metrics: section shows *(not recorded)* gracefully.
 20. Truncated transcript flag: warning appears in metadata.
 21. Matched/unmatched counter row appears in transcript section.
 22. CLI --no-stdout: no stdout output.
 23. CLI stdout: prompt printed to stdout.
 24. Default output path: correct directory structure.
 25. render_review_prompt: output is valid UTF-8 (Chinese characters preserved).
"""

import importlib
import json
import os
import sys
from io import StringIO
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import export_session_review_prompt as exp


# ── Shared fixture ────────────────────────────────────────────────────────────

SAMPLE_RECORD = {
    "schema": "session_record_v1",
    "capture_source": "end_session_payload",
    "session_id": "session_test001",
    "learner_id": "learner_abc",
    "created_at": "2026-06-29T02:00:00+12:00",
    "persona_id": "jianguo",
    "mode": "normal",
    "tier": "standard",
    "duration_seconds": 412,
    "counters": {
        "total_turns": 12,
        "questions_asked": 3,
        "depth_responses": 2,
        "unmatched_responses": 1,
        "soft_unmatched_responses": 0,
        "recovery_uses": 2,
        "successful_recoveries": 1,
        "conversational_recoveries": 1,
        "successful_conversational_recoveries": 1,
        "suggestion_clicks": 0,
        "card_opens": 3,
        "translation_help_uses": 1,
        "display_en_clicks": 2,
        "display_py_clicks": 1,
        "hint_clicks": 0,
        "engines_used": ["identity", "family", "work"],
    },
    "metrics": {
        "flow": {"raw": 12, "label": "Sustained"},
        "recovery": {"score": 0.75, "label": "Good"},
    },
    "progress_snapshot_ref": {
        "session_id": "session_test001",
        "stored_in": "data/progress/learner_abc.json",
    },
    "transcript": [
        {
            "idx": 0,
            "role": "partner",
            "text_zh": "你家里谁对你最重要？",
            "text_en": "Who in your family matters most to you?",
            "pinyin": "nǐ jiālǐ shéi duì nǐ zuì zhòngyào?",
            "frame_id": "f_family_important",
            "engine": "family",
            "turn_uid": "t_0",
            "created_at": "2026-06-29T01:13:11+12:00",
        },
        {
            "idx": 1,
            "role": "user",
            "text_zh": "我妈妈。",
            "frame_id": "f_family_important",
            "turn_uid": "t_0",
            "matched": True,
            "asr_raw": "我妈妈",
        },
        {
            "idx": 2,
            "role": "partner",
            "text_zh": "再说一遍？",
            "text_en": "Could you say that again?",
            "pinyin": "zài shuō yī biàn?",
            "frame_id": "f_recovery",
            "engine": "recovery",
            "turn_uid": "t_1",
        },
        {
            "idx": 3,
            "role": "user",
            "text_zh": "我不懂。",
            "frame_id": "f_family_important",
            "turn_uid": "t_1",
            "matched": False,
        },
    ],
    "event_log": [
        {"t_offset_ms": 14200, "type": "card_open",        "frame_id": "f_family_important"},
        {"t_offset_ms": 15900, "type": "display_en_click", "frame_id": "f_family_important"},
        {"t_offset_ms": 30100, "type": "recovery_use",     "frame_id": "f_family_important", "kind": "repeat"},
    ],
    "capture_flags": {
        "transcript_present": True,
        "event_log_present":  True,
        "transcript_truncated": False,
    },
}


def _make_sample_file(tmp_path: Path, record=None) -> Path:
    record = record or SAMPLE_RECORD
    p = tmp_path / "session_test001.json"
    p.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return p


# ── 2. All required sections present ─────────────────────────────────────────

class TestSectionsPresent:
    def test_section_1_metadata(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        assert "## 1. Session Metadata" in prompt

    def test_section_2_counters(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        assert "## 2. Session Counters" in prompt

    def test_section_3_scorecard(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        assert "## 3. Scorecard" in prompt

    def test_section_4_transcript(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        assert "## 4. Conversation Transcript" in prompt

    def test_section_5_event_log(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        assert "## 5. UX Event Log" in prompt

    def test_section_6_review_tasks(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        assert "## 6. Review Tasks" in prompt


# ── 3. Metadata values appear ─────────────────────────────────────────────────

class TestMetadata:
    def setup_method(self):
        self.prompt = exp.render_review_prompt(SAMPLE_RECORD)

    def test_session_id(self):
        assert "session_test001" in self.prompt

    def test_learner_id(self):
        assert "learner_abc" in self.prompt

    def test_persona_id(self):
        assert "jianguo" in self.prompt

    def test_mode(self):
        assert "normal" in self.prompt

    def test_duration_formatted(self):
        assert "6m" in self.prompt  # 412s = 6m 52s

    def test_schema_version(self):
        assert "session_record_v1" in self.prompt


# ── 4–6. Transcript content ───────────────────────────────────────────────────

class TestTranscriptContent:
    def setup_method(self):
        self.prompt = exp.render_review_prompt(SAMPLE_RECORD)

    def test_chinese_text_present(self):
        assert "你家里谁对你最重要" in self.prompt

    def test_learner_chinese_present(self):
        assert "我妈妈" in self.prompt

    def test_pinyin_present(self):
        assert "nǐ jiālǐ" in self.prompt

    def test_english_present(self):
        assert "Who in your family" in self.prompt

    def test_frame_id_present(self):
        assert "f_family_important" in self.prompt

    def test_turn_uid_present(self):
        assert "t_0" in self.prompt

    def test_persona_role_label(self):
        assert "🤖 Persona" in self.prompt

    def test_learner_role_label(self):
        assert "👤 Learner" in self.prompt


# ── 7. Missing fields → *(not recorded)* ─────────────────────────────────────

class TestMissingFields:
    def test_missing_pinyin_for_user_turn(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        # User turn idx=1 has no pinyin → should show "—" (user pinyin is optional)
        # User turn idx=3 has no pinyin
        assert "—" in prompt

    def test_completely_empty_record(self):
        prompt = exp.render_review_prompt({})
        assert exp._MISSING in prompt

    def test_missing_counters(self):
        record = dict(SAMPLE_RECORD)
        record = {k: v for k, v in record.items() if k != "counters"}
        prompt = exp.render_review_prompt(record)
        assert "## 2. Session Counters" in prompt
        # Should not crash; all counter rows show _MISSING
        assert exp._MISSING in prompt


# ── 8–9. Event log section ────────────────────────────────────────────────────

class TestEventLog:
    def test_event_log_table_when_present(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        assert "card_open" in prompt
        assert "display_en_click" in prompt
        assert "recovery_use" in prompt

    def test_event_log_missing_when_absent(self):
        record = dict(SAMPLE_RECORD)
        record["event_log"] = []
        prompt = exp.render_review_prompt(record)
        assert exp._MISSING in prompt

    def test_event_log_summary_line(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        assert "Event summary" in prompt

    def test_event_log_offset_ms(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        assert "14200" in prompt


# ── 10–11. Review tasks section ───────────────────────────────────────────────

class TestReviewTasks:
    def setup_method(self):
        self.prompt = exp.render_review_prompt(SAMPLE_RECORD)

    def test_section_A_learner_feedback(self):
        assert "### A. Learner Feedback" in self.prompt

    def test_section_B_better_mandarin(self):
        assert "### B. Better Mandarin Responses" in self.prompt

    def test_section_C_recovery_phrases(self):
        assert "### C. Recovery Phrase Opportunities" in self.prompt

    def test_section_D_bugs(self):
        assert "### D. Suspected Bugs" in self.prompt

    def test_section_E_ux(self):
        assert "### E. UX Issues" in self.prompt

    def test_section_F_conversation_design(self):
        assert "### F. Conversation-Design Improvements" in self.prompt

    def test_section_G_product_intel(self):
        assert "### G. Product Intelligence Summary" in self.prompt

    def test_section_H_cursor_tasks(self):
        assert "### H. Recommended Next Cursor Tasks" in self.prompt

    def test_product_intel_v1_schema_in_tasks(self):
        assert "product_intel_v1" in self.prompt


# ── 12–17. export_from_path ───────────────────────────────────────────────────

class TestExportFromPath:
    def test_round_trip_returns_string(self, tmp_path):
        p = _make_sample_file(tmp_path)
        result = exp.export_from_path(p)
        assert isinstance(result, str)
        assert "session_test001" in result

    def test_write_true_creates_file(self, tmp_path):
        p = _make_sample_file(tmp_path)
        with _patch_exports_dir(tmp_path):
            exp.export_from_path(p, write=True)
        # auto-derived path
        expected = tmp_path / "review_exports" / "learner_abc" / "session_test001_review_prompt.md"
        assert expected.is_file()

    def test_explicit_out_path(self, tmp_path):
        p = _make_sample_file(tmp_path)
        out = tmp_path / "custom_output.md"
        exp.export_from_path(p, output_path=out, write=True)
        assert out.is_file()
        content = out.read_text(encoding="utf-8")
        assert "## 1. Session Metadata" in content

    def test_file_not_found(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            exp.export_from_path(missing)

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ not valid json", encoding="utf-8")
        with pytest.raises(Exception):  # json.JSONDecodeError
            exp.export_from_path(p)

    def test_json_array_raises_value_error(self, tmp_path):
        p = tmp_path / "array.json"
        p.write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError):
            exp.export_from_path(p)


# ── 18–21. Edge cases ─────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_transcript_graceful(self):
        record = dict(SAMPLE_RECORD)
        record["transcript"] = []
        prompt = exp.render_review_prompt(record)
        assert "## 4. Conversation Transcript" in prompt
        assert exp._MISSING in prompt

    def test_empty_metrics_graceful(self):
        record = dict(SAMPLE_RECORD)
        record["metrics"] = {}
        prompt = exp.render_review_prompt(record)
        assert "## 3. Scorecard" in prompt
        assert exp._MISSING in prompt

    def test_truncated_flag_warning(self):
        record = dict(SAMPLE_RECORD)
        record["capture_flags"] = {
            "transcript_present": True,
            "event_log_present": False,
            "transcript_truncated": True,
        }
        prompt = exp.render_review_prompt(record)
        assert "analysis may be incomplete" in prompt

    def test_matched_unmatched_summary_row(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        # 2 learner turns: idx=1 matched=True, idx=3 matched=False
        assert "1 matched" in prompt
        assert "1 unmatched" in prompt


# ── 22–23. CLI ────────────────────────────────────────────────────────────────

class TestCLI:
    def test_stdout_output(self, tmp_path, capsys):
        p = _make_sample_file(tmp_path)
        exp.main([str(p)])
        captured = capsys.readouterr()
        assert "## 1. Session Metadata" in captured.out

    def test_no_stdout_suppresses_output(self, tmp_path, capsys):
        p = _make_sample_file(tmp_path)
        out = tmp_path / "out.md"
        exp.main([str(p), "--out", str(out), "--no-stdout"])
        captured = capsys.readouterr()
        assert captured.out.strip() == ""
        assert out.is_file()

    def test_cli_missing_file_exits_nonzero(self, tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            exp.main([str(tmp_path / "does_not_exist.json")])
        assert exc_info.value.code != 0


# ── 24. Default output path ───────────────────────────────────────────────────

class TestDefaultOutputPath:
    def test_path_structure(self, tmp_path):
        with _patch_exports_dir(tmp_path):
            out = exp._default_output_path(SAMPLE_RECORD, Path("session_test001.json"))
        assert out.name == "session_test001_review_prompt.md"
        assert out.parent.name == "learner_abc"
        assert out.parent.parent.name == "review_exports"

    def test_sanitises_special_chars(self, tmp_path):
        record = dict(SAMPLE_RECORD)
        record["learner_id"] = "learner/with/slashes"
        with _patch_exports_dir(tmp_path):
            out = exp._default_output_path(record, Path("sid.json"))
        # slashes replaced
        assert "/" not in out.parent.name


# ── 25. UTF-8 preservation ────────────────────────────────────────────────────

class TestUtf8:
    def test_chinese_characters_in_output(self):
        prompt = exp.render_review_prompt(SAMPLE_RECORD)
        encoded = prompt.encode("utf-8")
        decoded = encoded.decode("utf-8")
        assert "你家里谁对你最重要" in decoded

    def test_no_unicode_escape_in_file(self, tmp_path):
        p = _make_sample_file(tmp_path)
        out = tmp_path / "out.md"
        exp.export_from_path(p, output_path=out, write=True)
        raw = out.read_bytes()
        # Ensure actual Chinese bytes, not \\u escapes
        assert "你家里谁对你最重要".encode("utf-8") in raw


# ── Helpers ───────────────────────────────────────────────────────────────────

from unittest import mock


def _patch_exports_dir(tmp_path: Path):
    """Redirect _REVIEW_EXPORTS_DIR to a temp path for testing."""
    return mock.patch.object(exp, "_REVIEW_EXPORTS_DIR", tmp_path / "review_exports")
