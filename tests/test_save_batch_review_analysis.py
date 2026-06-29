"""
tests/test_save_batch_review_analysis.py

Regression tests for scripts/save_batch_review_analysis.py
(Phase 0 Slice 6: saving manual AI batch analysis output).

Covers:
  - valid analysis saves full analysis, rollup JSON, task list, and manifest
  - invalid JSON in Section G is rejected
  - missing Section G is rejected
  - wrong schema is rejected
  - missing Section H warns but still saves rollup
  - existing outputs are not overwritten unless --overwrite
  - dry-run writes nothing
  - extracted batch_id matches rollup batch_id
  - original input file is not modified
  - fallback batch_id detection from filename
  - manifest schema and required fields
  - section extraction helpers
  - JSON block extraction helper
  - save_analysis.ps1 and script exist with no hardcoded secrets
"""

import json
import pathlib
import sys
import pytest
from pathlib import Path

REPO = pathlib.Path(__file__).parent.parent
SCRIPTS = REPO / "scripts"
TOOLS = REPO / "tools"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import save_batch_review_analysis as saver  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_ROLLUP = {
    "schema": "product_intel_rollup_v1",
    "batch_id": "batch_2026-06-29_01",
    "sessions_analysed": 3,
    "generator": "manual_ai_review",
    "top_findings": [
        {
            "category": "bug",
            "classification": "suspected",
            "severity": "medium",
            "title": "Recovery phrase not detected in challenge mode",
            "count": 2,
            "recommendation": "Add 再说一遍 to server-side repeat markers.",
        }
    ],
    "trends": {"avg_turns": 12, "avg_unmatched_ratio": 0.05, "notes": ""},
    "session_health_summary": "fair",
    "recommended_focus": ["challenge_mode_recovery"],
}


def _make_analysis(batch_id: str = "batch_2026-06-29_01", include_h: bool = True, bad_json: bool = False) -> str:
    rollup_json = json.dumps(VALID_ROLLUP, indent=2) if not bad_json else '{ bad json !!!'
    section_h = ""
    if include_h:
        section_h = f"""
### H. Prioritised Cursor Task List

**P0 — Critical bugs:**
- [ ] Fix challenge mode recovery routing

**P1 — High-impact:**
- [ ] Improve 再说一遍 detection
"""
    return f"""# MandarinOS — Batch Review Analysis

## Summary
This is the AI analysis of {batch_id}.

### A. Learner Feedback Patterns

Learners struggled with tone marking.

### B. Better Mandarin Response Patterns

| Session | Turn # | Learner said | Could also say | Why |
|---|---|---|---|---|
| batch_01 / turn 3 | 3 | 好 | 好的，我明白了。| More natural |

### C. Repeated Recovery Phrase Opportunities

No repeated recovery.

### D. Suspected Bugs

No confirmed bugs.

### E. UX Issues

No UX issues.

### F. Conversation-Design Findings

Good flow overall.

### G. Product Intelligence Rollup (product_intel_rollup_v1 shape)

```json
{rollup_json}
```
{section_h}"""


def _write_analysis(tmp_path: Path, content: str, filename: str = "batch_2026-06-29_01_analysis.md") -> Path:
    f = tmp_path / filename
    f.write_text(content, encoding="utf-8")
    return f


@pytest.fixture
def tmp_dirs(tmp_path):
    return {
        "analysis_root": tmp_path / "analyses",
        "rollup_root":   tmp_path / "rollups",
        "tasks_root":    tmp_path / "tasks",
        "manifest_root": tmp_path / "manifests",
    }


def _run(source: Path, dirs: dict, **kwargs):
    return saver.save_analysis(
        source_path=source,
        analysis_root=dirs["analysis_root"],
        rollup_root=dirs["rollup_root"],
        tasks_root=dirs["tasks_root"],
        manifest_root=dirs["manifest_root"],
        **kwargs,
    )


# ── 1. Valid analysis saves all outputs ───────────────────────────────────────

def test_valid_analysis_saves_analysis_file(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    result = _run(src, tmp_dirs)
    assert result.analysis_path.exists()
    assert result.analysis_path.read_text(encoding="utf-8") == _make_analysis()


def test_valid_analysis_saves_rollup_json(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    result = _run(src, tmp_dirs)
    assert result.rollup_path.exists()
    data = json.loads(result.rollup_path.read_text(encoding="utf-8"))
    assert data["schema"] == "product_intel_rollup_v1"
    assert data["batch_id"] == "batch_2026-06-29_01"


def test_valid_analysis_saves_cursor_tasks(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    result = _run(src, tmp_dirs)
    assert result.tasks_path is not None
    assert result.tasks_path.exists()
    tasks_text = result.tasks_path.read_text(encoding="utf-8")
    assert "H." in tasks_text or "Cursor Task" in tasks_text


def test_valid_analysis_saves_manifest(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    result = _run(src, tmp_dirs)
    assert result.manifest_path.exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "analysis_manifest_v1"
    assert manifest["batch_id"] == "batch_2026-06-29_01"
    assert manifest["status"] == "manual_ai_analysis_saved"


def test_valid_analysis_manifest_has_required_fields(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    result = _run(src, tmp_dirs)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    for field in (
        "schema", "batch_id", "created_at", "source_analysis_path",
        "saved_analysis_path", "rollup_path", "cursor_tasks_path",
        "sessions_analysed", "top_findings_count", "status",
    ):
        assert field in manifest, f"manifest missing field: {field}"


def test_valid_analysis_manifest_top_findings_count(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    result = _run(src, tmp_dirs)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["top_findings_count"] == len(VALID_ROLLUP["top_findings"])


def test_valid_analysis_result_batch_id_correct(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    result = _run(src, tmp_dirs)
    assert result.batch_id == "batch_2026-06-29_01"


# ── 2. Invalid JSON in Section G is rejected ──────────────────────────────────

def test_invalid_json_in_section_g_raises(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis(bad_json=True))
    with pytest.raises(saver.ValidationError, match="valid JSON"):
        _run(src, tmp_dirs)


def test_invalid_json_writes_no_files(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis(bad_json=True))
    try:
        _run(src, tmp_dirs)
    except saver.ValidationError:
        pass
    assert not list(tmp_dirs["rollup_root"].rglob("*.json")) if tmp_dirs["rollup_root"].exists() else True
    assert not list(tmp_dirs["manifest_root"].rglob("*.json")) if tmp_dirs["manifest_root"].exists() else True


# ── 3. Missing Section G is rejected ─────────────────────────────────────────

def test_missing_section_g_raises(tmp_path, tmp_dirs):
    text = "# Analysis\n\n### A. Learner Feedback\n\nSome feedback.\n"
    src = _write_analysis(tmp_path, text)
    with pytest.raises(saver.ValidationError, match="Section G"):
        _run(src, tmp_dirs)


def test_section_g_without_json_block_raises(tmp_path, tmp_dirs):
    text = (
        "# Analysis\n\n"
        "### G. Product Intelligence Rollup\n\n"
        "Here is the rollup: (no JSON block provided)\n"
    )
    src = _write_analysis(tmp_path, text)
    with pytest.raises(saver.ValidationError, match="json"):
        _run(src, tmp_dirs)


# ── 4. Wrong schema is rejected ────────────────────────────────────────────────

def test_wrong_schema_raises(tmp_path, tmp_dirs):
    wrong_rollup = dict(VALID_ROLLUP, schema="session_record_v1")
    text = (
        "### G. Product Intelligence Rollup\n\n"
        f"```json\n{json.dumps(wrong_rollup)}\n```\n"
    )
    src = _write_analysis(tmp_path, text)
    with pytest.raises(saver.ValidationError, match="schema"):
        _run(src, tmp_dirs)


def test_missing_batch_id_in_rollup_and_filename_raises(tmp_path, tmp_dirs):
    """batch_id missing from rollup AND from filename → ValidationError."""
    bad = dict(VALID_ROLLUP)
    del bad["batch_id"]
    text = (
        "### G. Product Intelligence Rollup\n\n"
        f"```json\n{json.dumps(bad)}\n```\n"
    )
    # filename has no batch_id pattern either
    src = _write_analysis(tmp_path, text, filename="no_batch_id_here.md")
    with pytest.raises(saver.ValidationError, match="batch_id"):
        _run(src, tmp_dirs)


def test_missing_batch_id_in_rollup_falls_back_to_filename(tmp_path, tmp_dirs):
    """batch_id missing from rollup but present in filename → uses filename."""
    bad = dict(VALID_ROLLUP)
    del bad["batch_id"]
    text = (
        "### G. Product Intelligence Rollup\n\n"
        f"```json\n{json.dumps(bad)}\n```\n"
        "### H. Tasks\n\n- [ ] Fix something\n"
    )
    src = _write_analysis(tmp_path, text, filename="batch_2026-07-01_05_analysis.md")
    result = _run(src, tmp_dirs)
    assert result.batch_id == "batch_2026-07-01_05"


def test_missing_top_findings_raises(tmp_path, tmp_dirs):
    bad = dict(VALID_ROLLUP)
    del bad["top_findings"]
    text = (
        "### G. Product Intelligence Rollup\n\n"
        f"```json\n{json.dumps(bad)}\n```\n"
    )
    src = _write_analysis(tmp_path, text)
    with pytest.raises(saver.ValidationError, match="top_findings"):
        _run(src, tmp_dirs)


# ── 5. Missing Section H warns but saves rollup ───────────────────────────────

def test_missing_section_h_warns(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis(include_h=False))
    result = _run(src, tmp_dirs)
    assert result.warnings, "Should have a warning about missing Section H"
    assert any("H" in w or "task" in w.lower() for w in result.warnings)


def test_missing_section_h_still_saves_rollup(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis(include_h=False))
    result = _run(src, tmp_dirs)
    assert result.rollup_path.exists()


def test_missing_section_h_tasks_path_is_none(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis(include_h=False))
    result = _run(src, tmp_dirs)
    assert result.tasks_path is None


def test_missing_section_h_still_saves_manifest(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis(include_h=False))
    result = _run(src, tmp_dirs)
    assert result.manifest_path.exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["cursor_tasks_path"] is None


# ── 6. Existing outputs not overwritten without --overwrite ───────────────────

def test_existing_outputs_raise_without_overwrite(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    _run(src, tmp_dirs)  # first run
    with pytest.raises(FileExistsError):
        _run(src, tmp_dirs)  # second run without overwrite


def test_overwrite_flag_replaces_existing_files(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    _run(src, tmp_dirs)
    result = _run(src, tmp_dirs, overwrite=True)
    assert result.rollup_path.exists()


# ── 7. Dry-run writes nothing ─────────────────────────────────────────────────

def test_dry_run_writes_no_files(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    result = _run(src, tmp_dirs, dry_run=True)
    # All output paths are set but nothing written
    assert not result.analysis_path.exists()
    assert not result.rollup_path.exists()
    assert not result.manifest_path.exists()


def test_dry_run_still_returns_batch_id(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis())
    result = _run(src, tmp_dirs, dry_run=True)
    assert result.batch_id == "batch_2026-06-29_01"


# ── 8. batch_id from rollup matches expected ──────────────────────────────────

def test_batch_id_taken_from_rollup_json(tmp_path, tmp_dirs):
    src = _write_analysis(tmp_path, _make_analysis(batch_id="batch_2026-06-29_01"))
    result = _run(src, tmp_dirs)
    assert result.batch_id == "batch_2026-06-29_01"


def test_batch_id_falls_back_to_filename(tmp_path, tmp_dirs):
    """When rollup JSON has no batch_id, filename is used."""
    no_id_rollup = dict(VALID_ROLLUP)
    no_id_rollup["batch_id"] = ""  # blank
    text = (
        "### G. Product Intelligence Rollup\n\n"
        f"```json\n{json.dumps(no_id_rollup)}\n```\n"
        "### H. Tasks\n\n- [ ] Fix something\n"
    )
    # Filename contains the fallback batch_id
    src = _write_analysis(tmp_path, text, filename="batch_2026-07-01_03_analysis.md")
    result = _run(src, tmp_dirs)
    assert result.batch_id == "batch_2026-07-01_03"


# ── 9. Original input file is not modified ────────────────────────────────────

def test_original_input_not_modified(tmp_path, tmp_dirs):
    content = _make_analysis()
    src = _write_analysis(tmp_path, content)
    original_mtime = src.stat().st_mtime
    _run(src, tmp_dirs)
    assert src.stat().st_mtime == original_mtime
    assert src.read_text(encoding="utf-8") == content


# ── 10. Section extraction helpers ────────────────────────────────────────────

def test_extract_section_g():
    text = (
        "### A. Learner Feedback\nFeedback text.\n"
        "### G. Product Intelligence Rollup\nRollup text.\n"
        "### H. Tasks\nTask text.\n"
    )
    result = saver.extract_section(text, "G")
    assert result is not None
    assert "Rollup text." in result
    assert "Task text." not in result


def test_extract_section_returns_none_when_missing():
    text = "### A. Learner Feedback\nFeedback text.\n"
    assert saver.extract_section(text, "G") is None


def test_extract_section_case_insensitive():
    text = "### g. product intelligence rollup\n\nSome content.\n"
    result = saver.extract_section(text, "G")
    assert result is not None


# ── 11. JSON block extraction ─────────────────────────────────────────────────

def test_find_json_block_basic():
    text = 'Some text.\n```json\n{"key": "value"}\n```\nMore text.'
    block = saver.find_json_block(text)
    assert block == '{"key": "value"}'


def test_find_json_block_returns_none_when_absent():
    text = "Some text without a code block."
    assert saver.find_json_block(text) is None


def test_find_json_block_handles_backtick_only():
    text = 'Text.\n```\n{"key": 1}\n```\nEnd.'
    block = saver.find_json_block(text)
    assert block == '{"key": 1}'


# ── 12. batch_id detection from filename ──────────────────────────────────────

@pytest.mark.parametrize("filename,expected", [
    ("batch_2026-06-29_01_analysis.md", "batch_2026-06-29_01"),
    ("batch_2026-07-15_12_analysis.md", "batch_2026-07-15_12"),
    ("my_batch_2026-06-29_01_review.md", "batch_2026-06-29_01"),
    ("no_batch_here.md", None),
])
def test_detect_batch_id_from_filename(filename, expected):
    from pathlib import Path
    result = saver.detect_batch_id_from_filename(Path(filename))
    assert result == expected


# ── 13. File-not-found raises correctly ───────────────────────────────────────

def test_missing_source_file_raises(tmp_dirs):
    with pytest.raises(FileNotFoundError):
        _run(Path("/nonexistent/file.md"), tmp_dirs)


# ── 14. Source checks ─────────────────────────────────────────────────────────

def test_script_exists():
    assert (SCRIPTS / "save_batch_review_analysis.py").exists()


def test_ps1_wrapper_exists():
    assert (TOOLS / "save_analysis.ps1").exists()


def test_script_has_no_hardcoded_tokens():
    src = (SCRIPTS / "save_batch_review_analysis.py").read_text(encoding="utf-8")
    assert "beta_export_local" not in src
    assert "replace_me" not in src


def test_ps1_wrapper_calls_python_script():
    src = (TOOLS / "save_analysis.ps1").read_text(encoding="utf-8")
    assert "save_batch_review_analysis.py" in src


def test_script_references_product_intel():
    src = (SCRIPTS / "save_batch_review_analysis.py").read_text(encoding="utf-8")
    assert "product_intel" in src


def test_script_defines_validation_error():
    src = (SCRIPTS / "save_batch_review_analysis.py").read_text(encoding="utf-8")
    assert "class ValidationError" in src


def test_script_uses_atomic_write():
    src = (SCRIPTS / "save_batch_review_analysis.py").read_text(encoding="utf-8")
    assert "_atomic_write" in src


# ── 15. Integration: full round-trip ─────────────────────────────────────────

def test_full_round_trip(tmp_path, tmp_dirs):
    """Full round-trip: write → validate → all four files present and correct."""
    content = _make_analysis()
    src = _write_analysis(tmp_path, content)
    result = _run(src, tmp_dirs)

    # All four files exist
    assert result.analysis_path.exists()
    assert result.rollup_path.exists()
    assert result.tasks_path.exists()
    assert result.manifest_path.exists()

    # Rollup is valid JSON with correct schema
    rollup = json.loads(result.rollup_path.read_text(encoding="utf-8"))
    assert rollup["schema"] == "product_intel_rollup_v1"

    # Manifest references the correct paths
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["batch_id"] == result.batch_id
    assert Path(manifest["rollup_path"]) == result.rollup_path
    assert Path(manifest["saved_analysis_path"]) == result.analysis_path

    # No warnings
    assert not result.warnings
