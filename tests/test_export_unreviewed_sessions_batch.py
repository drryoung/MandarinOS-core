"""
Phase 0 Slice 3 — Batch export of unreviewed sessions: tests.

Coverage:
  1.  find_all_sessions: discovers session_record_v1 files recursively.
  2.  find_all_sessions: ignores invalid JSON files.
  3.  find_all_sessions: ignores JSON that is not session_record_v1 (wrong schema).
  4.  find_all_sessions: ignores JSON that is an array (not a dict).
  5.  find_all_sessions: returns empty list when directory does not exist.
  6.  _load_reviewed_session_ids: reads session_ids from previous manifests.
  7.  _load_reviewed_session_ids: returns empty set when out_dir missing.
  8.  _load_reviewed_session_ids: skips malformed manifest files gracefully.
  9.  run_batch_export --write: excludes sessions already in previous manifests.
  10. run_batch_export --write: includes previously reviewed when --include-reviewed.
  11. run_batch_export --write: creates prompt file at correct path.
  12. run_batch_export --write: creates manifest JSON at correct path.
  13. run_batch_export --write: manifest has correct schema and fields.
  14. run_batch_export --write: manifest included_sessions matches selected sessions.
  15. run_batch_export --write: does NOT modify original session files.
  16. run_batch_export --dry-run: writes NO files.
  17. run_batch_export --dry-run: writes NO manifests.
  18. run_batch_export: no unreviewed sessions → returns 1, no files.
  19. run_batch_export --max-sessions: caps selection, defers remainder.
  20. Batch filename: deterministic YYYY-MM-DD sequence pattern.
  21. Batch filename: sequence increments on second call same day.
  22. render_batch_prompt: contains all four Part headings.
  23. render_batch_prompt: contains inventory table with session_id.
  24. render_batch_prompt: contains transcript Chinese text.
  25. render_batch_prompt: contains cross-session review task sections A–H.
  26. render_batch_prompt: contains product_intel_rollup_v1 in tasks.
  27. render_batch_prompt: contains AI constraint warnings (no over-generalise).
  28. render_batch_prompt: empty transcript shows *(not recorded)*.
  29. render_batch_prompt: multiple sessions all appear.
  30. Batch prompt: UTF-8 Chinese characters preserved on disk.
  31. CLI --dry-run: no file created, prints preview.
  32. CLI no flags: exits 0 with nothing-to-do message.
  33. CLI --dry-run and --write: mutually exclusive → exits 1.
  34. Session discovery: sorted oldest-first by timestamp.
  35. _next_batch_path: uses out_dir, creates parent dir.
"""

import importlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import export_unreviewed_sessions_batch as batch


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_RECORD_A = {
    "schema": "session_record_v1",
    "capture_source": "end_session_payload",
    "session_id": "session_AAA",
    "learner_id": "learner_abc",
    "created_at": "2026-06-29T01:00:00+12:00",
    "persona_id": "jianguo",
    "mode": "normal",
    "tier": "standard",
    "duration_seconds": 300,
    "counters": {
        "total_turns": 8,
        "recovery_uses": 1,
        "unmatched_responses": 0,
        "card_opens": 2,
        "display_en_clicks": 1,
        "hint_clicks": 0,
        "engines_used": ["identity", "family"],
    },
    "metrics": {"flow": {"raw": 8, "label": "Holding"}},
    "transcript": [
        {"idx": 0, "role": "partner", "text_zh": "你好！", "text_en": "Hello!",
         "pinyin": "nǐ hǎo!", "frame_id": "f_greeting", "engine": "identity", "turn_uid": "t_0"},
        {"idx": 1, "role": "user", "text_zh": "你好。", "frame_id": "f_greeting",
         "turn_uid": "t_0", "matched": True},
    ],
    "event_log": [
        {"t_offset_ms": 5000, "type": "card_open", "frame_id": "f_greeting"},
        {"t_offset_ms": 8000, "type": "display_en_click"},
    ],
    "capture_flags": {"transcript_present": True, "event_log_present": True, "transcript_truncated": False},
}

SAMPLE_RECORD_B = {
    "schema": "session_record_v1",
    "capture_source": "end_session_payload",
    "session_id": "session_BBB",
    "learner_id": "learner_xyz",
    "created_at": "2026-06-29T02:00:00+12:00",
    "persona_id": "xiaoming",
    "mode": "challenge",
    "tier": "standard",
    "duration_seconds": 420,
    "counters": {"total_turns": 12, "engines_used": ["work", "travel"]},
    "metrics": {},
    "transcript": [
        {"idx": 0, "role": "partner", "text_zh": "你做什么工作？", "pinyin": "nǐ zuò shénme gōngzuò?",
         "text_en": "What do you do for work?", "frame_id": "f_work", "engine": "work", "turn_uid": "t_0"},
        {"idx": 1, "role": "user", "text_zh": "我是老师。", "frame_id": "f_work",
         "turn_uid": "t_0", "matched": True},
        {"idx": 2, "role": "partner", "text_zh": "你喜欢这个工作吗？",
         "frame_id": "f_work_like", "engine": "work", "turn_uid": "t_1"},
    ],
    "event_log": [],
    "capture_flags": {"transcript_present": True, "event_log_present": False, "transcript_truncated": False},
}


def _write_session(directory: Path, record: dict) -> Path:
    sid = record["session_id"]
    lid = record.get("learner_id", "unknown")
    p = directory / lid / f"{sid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return p


def _write_manifest(out_dir: Path, session_ids: list, batch_id: str = "batch_prev") -> Path:
    manifest = {
        "schema": "batch_manifest_v1",
        "batch_id": batch_id,
        "included_sessions": [{"session_id": sid} for sid in session_ids],
        "status": "exported_for_manual_ai_review",
    }
    p = out_dir / f"{batch_id}_manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest), encoding="utf-8")
    return p


# ── 1–5: Session discovery ────────────────────────────────────────────────────

class TestFindAllSessions:
    def test_finds_valid_sessions_recursively(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _write_session(sessions_dir, SAMPLE_RECORD_A)
        _write_session(sessions_dir, SAMPLE_RECORD_B)
        results = batch.find_all_sessions(sessions_dir)
        assert len(results) == 2

    def test_ignores_invalid_json(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)
        bad = sessions_dir / "bad.json"
        bad.write_text("{ not valid", encoding="utf-8")
        results = batch.find_all_sessions(sessions_dir)
        assert results == []

    def test_ignores_wrong_schema(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)
        wrong = sessions_dir / "wrong.json"
        wrong.write_text(json.dumps({"schema": "progress_snapshot_v1", "session_id": "x"}), encoding="utf-8")
        results = batch.find_all_sessions(sessions_dir)
        assert results == []

    def test_ignores_json_array(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)
        arr = sessions_dir / "array.json"
        arr.write_text("[]", encoding="utf-8")
        results = batch.find_all_sessions(sessions_dir)
        assert results == []

    def test_empty_when_directory_missing(self, tmp_path):
        missing = tmp_path / "no_such_dir"
        assert batch.find_all_sessions(missing) == []


# ── 6–8: Manifest tracking ────────────────────────────────────────────────────

class TestReviewedIds:
    def test_reads_session_ids_from_manifests(self, tmp_path):
        out_dir = tmp_path / "batches"
        _write_manifest(out_dir, ["session_AAA", "session_BBB"])
        ids = batch._load_reviewed_session_ids(out_dir)
        assert "session_AAA" in ids
        assert "session_BBB" in ids

    def test_empty_when_out_dir_missing(self, tmp_path):
        missing = tmp_path / "no_batches"
        ids = batch._load_reviewed_session_ids(missing)
        assert ids == set()

    def test_skips_malformed_manifest(self, tmp_path):
        out_dir = tmp_path / "batches"
        out_dir.mkdir(parents=True)
        bad = out_dir / "broken_manifest.json"
        bad.write_text("{ bad json", encoding="utf-8")
        ids = batch._load_reviewed_session_ids(out_dir)
        assert ids == set()


# ── 9–10: Reviewed exclusion / inclusion ──────────────────────────────────────

class TestReviewedExclusion:
    def test_excludes_previously_reviewed(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _write_session(sessions_dir, SAMPLE_RECORD_A)
        _write_session(sessions_dir, SAMPLE_RECORD_B)
        out_dir = tmp_path / "batches"
        _write_manifest(out_dir, ["session_AAA"])

        code = batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=20,
            include_reviewed=False,
            dry_run=False,
            stdout=False,
        )
        assert code == 0
        manifests = list(out_dir.glob("*_manifest.json"))
        # Only one new manifest (for session_BBB)
        new_manifests = [m for m in manifests if "prev" not in m.name]
        assert len(new_manifests) == 1
        data = json.loads(new_manifests[0].read_text(encoding="utf-8"))
        included_ids = {e["session_id"] for e in data["included_sessions"]}
        assert "session_BBB" in included_ids
        assert "session_AAA" not in included_ids

    def test_include_reviewed_overrides_exclusion(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _write_session(sessions_dir, SAMPLE_RECORD_A)
        out_dir = tmp_path / "batches"
        _write_manifest(out_dir, ["session_AAA"])

        code = batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=20,
            include_reviewed=True,
            dry_run=False,
            stdout=False,
        )
        assert code == 0
        new_manifests = [m for m in out_dir.glob("*_manifest.json") if "prev" not in m.name]
        data = json.loads(new_manifests[0].read_text(encoding="utf-8"))
        included_ids = {e["session_id"] for e in data["included_sessions"]}
        assert "session_AAA" in included_ids


# ── 11–15: File output ────────────────────────────────────────────────────────

class TestFileOutput:
    def _run(self, tmp_path, records=None):
        sessions_dir = tmp_path / "sessions"
        for r in (records or [SAMPLE_RECORD_A, SAMPLE_RECORD_B]):
            _write_session(sessions_dir, r)
        out_dir = tmp_path / "batches"
        batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=20,
            include_reviewed=False,
            dry_run=False,
            stdout=False,
        )
        return sessions_dir, out_dir

    def test_creates_prompt_file(self, tmp_path):
        _, out_dir = self._run(tmp_path)
        prompts = list(out_dir.glob("*.md"))
        assert len(prompts) == 1
        assert prompts[0].stat().st_size > 0

    def test_creates_manifest_file(self, tmp_path):
        _, out_dir = self._run(tmp_path)
        manifests = list(out_dir.glob("*_manifest.json"))
        assert len(manifests) == 1

    def test_manifest_schema_and_fields(self, tmp_path):
        _, out_dir = self._run(tmp_path)
        manifest_path = list(out_dir.glob("*_manifest.json"))[0]
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["schema"] == "batch_manifest_v1"
        assert "batch_id" in data
        assert "created_at" in data
        assert "session_count" in data
        assert "included_sessions" in data
        assert data["status"] == "exported_for_manual_ai_review"

    def test_manifest_included_sessions(self, tmp_path):
        _, out_dir = self._run(tmp_path)
        data = json.loads(list(out_dir.glob("*_manifest.json"))[0].read_text(encoding="utf-8"))
        ids = {e["session_id"] for e in data["included_sessions"]}
        assert "session_AAA" in ids
        assert "session_BBB" in ids

    def test_original_session_files_unmodified(self, tmp_path):
        sessions_dir, _ = self._run(tmp_path)
        for p in sessions_dir.rglob("*.json"):
            raw = json.loads(p.read_text(encoding="utf-8"))
            assert raw.get("schema") == "session_record_v1", "Original file must not be modified"


# ── 16–18: Dry-run and no-new-sessions ───────────────────────────────────────

class TestDryRunAndEmpty:
    def test_dry_run_writes_no_files(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _write_session(sessions_dir, SAMPLE_RECORD_A)
        out_dir = tmp_path / "batches"
        batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=20,
            include_reviewed=False,
            dry_run=True,
            stdout=False,
        )
        assert not out_dir.exists() or list(out_dir.glob("*.md")) == []

    def test_dry_run_writes_no_manifests(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _write_session(sessions_dir, SAMPLE_RECORD_A)
        out_dir = tmp_path / "batches"
        batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=20,
            include_reviewed=False,
            dry_run=True,
            stdout=False,
        )
        assert not out_dir.exists() or list(out_dir.glob("*_manifest.json")) == []

    def test_no_unreviewed_returns_1(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _write_session(sessions_dir, SAMPLE_RECORD_A)
        out_dir = tmp_path / "batches"
        _write_manifest(out_dir, ["session_AAA"])
        code = batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=20,
            include_reviewed=False,
            dry_run=False,
            stdout=False,
        )
        assert code == 1

    def test_no_sessions_at_all_returns_1(self, tmp_path):
        sessions_dir = tmp_path / "empty_sessions"
        out_dir = tmp_path / "batches"
        code = batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=20,
            include_reviewed=False,
            dry_run=False,
            stdout=False,
        )
        assert code == 1


# ── 19: max-sessions cap ─────────────────────────────────────────────────────

class TestMaxSessions:
    def test_caps_at_max_sessions(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        for i in range(5):
            r = dict(SAMPLE_RECORD_A)
            r["session_id"] = f"session_{i:03d}"
            r["created_at"] = f"2026-06-29T0{i}:00:00+12:00"
            _write_session(sessions_dir, r)
        out_dir = tmp_path / "batches"
        batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=3,
            include_reviewed=False,
            dry_run=False,
            stdout=False,
        )
        data = json.loads(list(out_dir.glob("*_manifest.json"))[0].read_text(encoding="utf-8"))
        assert data["session_count"] == 3


# ── 20–21: Batch filename ─────────────────────────────────────────────────────

class TestBatchFilename:
    def test_filename_contains_date(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        _write_session(sessions_dir, SAMPLE_RECORD_A)
        out_dir = tmp_path / "batches"
        batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=20,
            include_reviewed=False,
            dry_run=False,
            stdout=False,
        )
        today = date.today().isoformat()
        prompts = list(out_dir.glob("*.md"))
        assert any(today in p.name for p in prompts)

    def test_sequence_increments_on_second_batch(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        out_dir = tmp_path / "batches"

        # First batch: session_AAA
        _write_session(sessions_dir, SAMPLE_RECORD_A)
        batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=20,
            include_reviewed=False,
            dry_run=False,
            stdout=False,
        )
        # Second batch: session_BBB (session_AAA now in manifest)
        _write_session(sessions_dir, SAMPLE_RECORD_B)
        batch.run_batch_export(
            sessions_root=sessions_dir,
            out_dir=out_dir,
            max_sessions=20,
            include_reviewed=False,
            dry_run=False,
            stdout=False,
        )
        prompts = sorted(out_dir.glob("*.md"))
        assert len(prompts) == 2
        # Sequences: _01 and _02
        names = [p.stem for p in prompts]
        assert any("_01" in n for n in names)
        assert any("_02" in n for n in names)


# ── 22–30: render_batch_prompt ───────────────────────────────────────────────

class TestRenderBatchPrompt:
    @pytest.fixture(autouse=True)
    def prompt(self):
        sessions = [(Path("fake/session_AAA.json"), SAMPLE_RECORD_A),
                    (Path("fake/session_BBB.json"), SAMPLE_RECORD_B)]
        self._prompt = batch.render_batch_prompt(sessions, "batch_2026-06-29_01")

    def test_part_1_inventory(self):
        assert "Part 1" in self._prompt
        assert "Session Inventory" in self._prompt

    def test_part_2_evidence(self):
        assert "Part 2" in self._prompt
        assert "Per-Session" in self._prompt

    def test_part_3_scorecard(self):
        assert "Part 3" in self._prompt
        assert "Scorecard" in self._prompt

    def test_part_4_review_tasks(self):
        assert "Part 4" in self._prompt
        assert "Cross-Session Review" in self._prompt

    def test_inventory_contains_session_id(self):
        assert "session_AAA" in self._prompt
        assert "session_BBB" in self._prompt

    def test_transcript_chinese_text(self):
        assert "你好！" in self._prompt
        assert "你做什么工作？" in self._prompt

    def test_review_tasks_A_through_H(self):
        for letter in "ABCDEFGH":
            assert f"### {letter}." in self._prompt

    def test_product_intel_rollup_v1_in_tasks(self):
        assert "product_intel_rollup_v1" in self._prompt

    def test_ai_constraint_warnings(self):
        assert "overgeneralise" in self._prompt.lower() or "over-generalise" in self._prompt.lower() or "Do not overgeneralise" in self._prompt

    def test_empty_transcript_graceful(self):
        r = dict(SAMPLE_RECORD_A)
        r["transcript"] = []
        sessions = [(Path("x.json"), r)]
        p = batch.render_batch_prompt(sessions, "batch_test")
        assert "*(not recorded)*" in p

    def test_multiple_sessions_both_appear(self):
        assert "Session 1" in self._prompt
        assert "Session 2" in self._prompt

    def test_utf8_preserved(self, tmp_path):
        p = tmp_path / "out.md"
        p.write_bytes(self._prompt.encode("utf-8"))
        assert "你好！".encode("utf-8") in p.read_bytes()


# ── 31–33: CLI ────────────────────────────────────────────────────────────────

class TestCLI:
    def test_dry_run_no_file_created(self, tmp_path, capsys):
        sessions_dir = tmp_path / "sessions"
        _write_session(sessions_dir, SAMPLE_RECORD_A)
        out_dir = tmp_path / "batches"
        with pytest.raises(SystemExit) as exc:
            batch.main(["--sessions-root", str(sessions_dir), "--out-dir", str(out_dir), "--dry-run"])
        assert exc.value.code == 0
        assert not out_dir.exists() or list(out_dir.glob("*.md")) == []

    def test_no_flags_exits_0(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            batch.main(["--sessions-root", str(tmp_path), "--out-dir", str(tmp_path / "out")])
        assert exc.value.code == 0

    def test_dry_run_and_write_mutually_exclusive(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            batch.main(["--dry-run", "--write",
                        "--sessions-root", str(tmp_path), "--out-dir", str(tmp_path / "out")])
        assert exc.value.code != 0


# ── 34: Sorted oldest-first ───────────────────────────────────────────────────

class TestSorting:
    def test_sorted_oldest_first(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        newer = dict(SAMPLE_RECORD_A)
        newer["created_at"] = "2026-06-29T08:00:00+12:00"
        newer["session_id"] = "session_NEWER"

        older = dict(SAMPLE_RECORD_B)
        older["created_at"] = "2026-06-28T01:00:00+12:00"
        older["session_id"] = "session_OLDER"

        _write_session(sessions_dir, newer)
        _write_session(sessions_dir, older)

        results = batch.find_all_sessions(sessions_dir)
        assert results[0][1]["session_id"] == "session_OLDER"
        assert results[1][1]["session_id"] == "session_NEWER"


# ── 35: _next_batch_path ──────────────────────────────────────────────────────

class TestNextBatchPath:
    def test_creates_dir_and_returns_path(self, tmp_path):
        out_dir = tmp_path / "batches"
        prompt_path, manifest_path, batch_id = batch._next_batch_path(out_dir, "2026-06-29")
        assert out_dir.is_dir()
        assert "2026-06-29" in batch_id
        assert prompt_path.suffix == ".md"
        assert "manifest" in manifest_path.name

    def test_increments_when_files_exist(self, tmp_path):
        out_dir = tmp_path / "batches"
        out_dir.mkdir()
        # Simulate existing first batch
        (out_dir / "batch_2026-06-29_01.md").write_text("x")
        (out_dir / "batch_2026-06-29_01_manifest.json").write_text("{}")
        _, _, bid = batch._next_batch_path(out_dir, "2026-06-29")
        assert "_02" in bid
