"""
tests/test_session_review_pipeline.py

Regression tests for the one-command local review pipeline
(Phase 0 Slice 5: import_sessions_from_server + run_session_review_pipeline).

Covers:
  - import script: list sessions via mocked HTTP response
  - import script: downloads missing sessions
  - import script: skips already-local sessions
  - import script: rejects wrong schema
  - import script: dry-run writes nothing
  - import script: wrong token / 403 exits clearly
  - import script: server unreachable raises ConnectionError
  - import script: unsafe path components rejected
  - pipeline: creates a batch after import
  - pipeline: exits cleanly when no new sessions exist
  - pipeline: skip-import still runs batch export
  - PowerShell wrapper: file is present and does not contain hardcoded real tokens
  - sample env file: contains only placeholder values
"""

import json
import os
import sys
import pathlib
import tempfile
import shutil
import pytest
from unittest import mock
from pathlib import Path

REPO = pathlib.Path(__file__).parent.parent
SCRIPTS = REPO / "scripts"
TOOLS = REPO / "tools"

# Ensure scripts/ importable
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import import_sessions_from_server as importer  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_session_record(session_id: str, learner_id: str) -> dict:
    return {
        "schema": "session_record_v1",
        "capture_source": "end_session_payload",
        "session_id": session_id,
        "learner_id": learner_id,
        "created_at": "2026-06-29T05:00:00+00:00",
        "persona_id": "meiling",
        "mode": "normal",
        "tier": "standard",
        "duration_seconds": 180,
        "counters": {"total_turns": 5},
        "metrics": {},
        "transcript": [
            {"idx": 0, "role": "partner", "text_zh": "你好！", "pinyin": "nǐ hǎo"},
            {"idx": 1, "role": "user",    "text_zh": "你好。"},
        ],
        "event_log": [],
    }


def _make_list_response(sessions: list) -> dict:
    return {
        "ok": True,
        "sessions_root": "data/sessions",
        "total_sessions": len(sessions),
        "sessions": sessions,
    }


@pytest.fixture
def tmp_sessions(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    return root


@pytest.fixture
def tmp_out_dir(tmp_path):
    out = tmp_path / "batches"
    out.mkdir()
    return out


# ── HTTP mock helper ───────────────────────────────────────────────────────────

class _MockResponse:
    def __init__(self, body: dict, status: int = 200):
        self.status = status
        self._body = json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _mock_urlopen(responses: dict):
    """
    Returns a context manager mock for urllib.request.urlopen.
    `responses` maps URL prefixes to (status, body_dict) or raises an exception.
    """
    def _side_effect(url, timeout=None):
        for prefix, result in responses.items():
            if prefix in url:
                if isinstance(result, Exception):
                    raise result
                status, body = result
                return _MockResponse(body, status)
        raise ValueError(f"Unexpected URL in mock: {url}")

    return mock.patch("urllib.request.urlopen", side_effect=_side_effect)


# ── 1. List sessions via mocked HTTP ──────────────────────────────────────────

def test_fetch_session_list_success(tmp_sessions):
    record = _make_session_record("sess_001", "learner_abc")
    list_body = _make_list_response([
        {"learner_id": "learner_abc", "session_id": "sess_001",
         "schema_version": "session_record_v1"},
    ])
    with _mock_urlopen({"/api/sessions/list": (200, list_body)}):
        sessions = importer.fetch_session_list("https://example.railway.app", "tok123")
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "sess_001"


def test_fetch_session_list_wrong_token_raises():
    error_body = {"ok": False, "error": "invalid or missing admin_token"}
    with _mock_urlopen({"/api/sessions/list": (403, error_body)}):
        with pytest.raises(PermissionError):
            importer.fetch_session_list("https://example.railway.app", "bad_token")


def test_fetch_session_list_401_raises():
    with _mock_urlopen({"/api/sessions/list": (401, {"error": "unauthorized"})}):
        with pytest.raises(PermissionError):
            importer.fetch_session_list("https://example.railway.app", "bad")


def test_fetch_session_list_server_error_raises():
    with _mock_urlopen({"/api/sessions/list": (500, {"error": "internal"})}):
        with pytest.raises(RuntimeError):
            importer.fetch_session_list("https://example.railway.app", "tok")


def test_fetch_session_list_connection_error_raises():
    import urllib.error
    with _mock_urlopen({"/api/sessions/list": urllib.error.URLError("refused")}):
        with pytest.raises(ConnectionError):
            importer.fetch_session_list("https://example.railway.app", "tok")


# ── 2. Download missing sessions ──────────────────────────────────────────────

def test_import_downloads_missing_session(tmp_sessions):
    record = _make_session_record("sess_001", "learner_abc")
    list_body = _make_list_response([
        {"learner_id": "learner_abc", "session_id": "sess_001"},
    ])
    with _mock_urlopen({
        "/api/sessions/list": (200, list_body),
        "/api/sessions/get":  (200, record),
    }):
        result = importer.import_sessions(
            app_url="https://example.railway.app",
            admin_token="tok",
            out_root=tmp_sessions,
            dry_run=False,
            overwrite=False,
            quiet=True,
        )
    assert result.downloaded == 1
    local = tmp_sessions / "learner_abc" / "sess_001.json"
    assert local.exists()
    data = json.loads(local.read_text(encoding="utf-8"))
    assert data["session_id"] == "sess_001"


def test_import_writes_valid_json(tmp_sessions):
    record = _make_session_record("sess_002", "learner_xyz")
    list_body = _make_list_response([
        {"learner_id": "learner_xyz", "session_id": "sess_002"},
    ])
    with _mock_urlopen({
        "/api/sessions/list": (200, list_body),
        "/api/sessions/get":  (200, record),
    }):
        importer.import_sessions(
            app_url="https://example.railway.app",
            admin_token="tok",
            out_root=tmp_sessions,
            dry_run=False,
            quiet=True,
        )
    local = tmp_sessions / "learner_xyz" / "sess_002.json"
    parsed = json.loads(local.read_text(encoding="utf-8"))
    assert parsed["schema"] == "session_record_v1"
    assert parsed["session_id"] == "sess_002"


# ── 3. Skips already-local sessions ───────────────────────────────────────────

def test_import_skips_already_local_session(tmp_sessions):
    record = _make_session_record("sess_existing", "learner_abc")
    local = tmp_sessions / "learner_abc" / "sess_existing.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(record), encoding="utf-8")

    list_body = _make_list_response([
        {"learner_id": "learner_abc", "session_id": "sess_existing"},
    ])
    with _mock_urlopen({
        "/api/sessions/list": (200, list_body),
        "/api/sessions/get":  (200, record),
    }):
        result = importer.import_sessions(
            app_url="https://example.railway.app",
            admin_token="tok",
            out_root=tmp_sessions,
            dry_run=False,
            overwrite=False,
            quiet=True,
        )
    assert result.already_local == 1
    assert result.downloaded == 0


def test_import_overwrite_flag_redownloads(tmp_sessions):
    record = _make_session_record("sess_old", "learner_abc")
    local = tmp_sessions / "learner_abc" / "sess_old.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps({"schema": "session_record_v1", "session_id": "sess_old"}), encoding="utf-8")

    list_body = _make_list_response([
        {"learner_id": "learner_abc", "session_id": "sess_old"},
    ])
    with _mock_urlopen({
        "/api/sessions/list": (200, list_body),
        "/api/sessions/get":  (200, record),
    }):
        result = importer.import_sessions(
            app_url="https://example.railway.app",
            admin_token="tok",
            out_root=tmp_sessions,
            dry_run=False,
            overwrite=True,
            quiet=True,
        )
    assert result.downloaded == 1
    assert result.already_local == 0


# ── 4. Rejects wrong schema ───────────────────────────────────────────────────

def test_import_fails_on_wrong_schema(tmp_sessions):
    bad_record = {"schema": "progress_snapshot_v1", "session_id": "sess_bad"}
    list_body = _make_list_response([
        {"learner_id": "learner_abc", "session_id": "sess_bad"},
    ])
    with _mock_urlopen({
        "/api/sessions/list": (200, list_body),
        "/api/sessions/get":  (200, bad_record),
    }):
        result = importer.import_sessions(
            app_url="https://example.railway.app",
            admin_token="tok",
            out_root=tmp_sessions,
            dry_run=False,
            quiet=True,
        )
    assert result.failed == 1
    assert result.downloaded == 0
    local = tmp_sessions / "learner_abc" / "sess_bad.json"
    assert not local.exists(), "File with wrong schema must NOT be written"


# ── 5. Dry-run writes nothing ──────────────────────────────────────────────────

def test_import_dry_run_writes_nothing(tmp_sessions):
    record = _make_session_record("sess_dry", "learner_abc")
    list_body = _make_list_response([
        {"learner_id": "learner_abc", "session_id": "sess_dry"},
    ])
    with _mock_urlopen({
        "/api/sessions/list": (200, list_body),
        "/api/sessions/get":  (200, record),
    }):
        result = importer.import_sessions(
            app_url="https://example.railway.app",
            admin_token="tok",
            out_root=tmp_sessions,
            dry_run=True,
            quiet=False,  # dry-run always prints
        )
    assert result.skipped == 1
    assert result.downloaded == 0
    local = tmp_sessions / "learner_abc" / "sess_dry.json"
    assert not local.exists(), "dry-run must not write any files"


# ── 6. Wrong token raises PermissionError ─────────────────────────────────────

def test_import_sessions_raises_on_403(tmp_sessions):
    with _mock_urlopen({"/api/sessions/list": (403, {"error": "bad token"})}):
        with pytest.raises(PermissionError):
            importer.import_sessions(
                app_url="https://example.railway.app",
                admin_token="bad",
                out_root=tmp_sessions,
                quiet=True,
            )


# ── 7. Unsafe path components are rejected ─────────────────────────────────────

def test_import_rejects_path_traversal_learner_id(tmp_sessions):
    list_body = _make_list_response([
        {"learner_id": "../evil", "session_id": "sess_hack"},
    ])
    with _mock_urlopen({
        "/api/sessions/list": (200, list_body),
    }):
        result = importer.import_sessions(
            app_url="https://example.railway.app",
            admin_token="tok",
            out_root=tmp_sessions,
            dry_run=False,
            quiet=True,
        )
    assert result.skipped == 1
    assert result.downloaded == 0


def test_import_rejects_path_traversal_session_id(tmp_sessions):
    list_body = _make_list_response([
        {"learner_id": "learner_abc", "session_id": "../../evil"},
    ])
    with _mock_urlopen({
        "/api/sessions/list": (200, list_body),
    }):
        result = importer.import_sessions(
            app_url="https://example.railway.app",
            admin_token="tok",
            out_root=tmp_sessions,
            dry_run=False,
            quiet=True,
        )
    assert result.skipped == 1


def test_import_rejects_blank_ids(tmp_sessions):
    list_body = _make_list_response([
        {"learner_id": "", "session_id": "sess_ok"},
    ])
    with _mock_urlopen({
        "/api/sessions/list": (200, list_body),
    }):
        result = importer.import_sessions(
            app_url="https://example.railway.app",
            admin_token="tok",
            out_root=tmp_sessions,
            dry_run=False,
            quiet=True,
        )
    assert result.skipped == 1


# ── 8. Pipeline creates a batch after import ──────────────────────────────────

def test_pipeline_creates_batch_after_import(tmp_sessions, tmp_out_dir):
    record = _make_session_record("sess_pipe_001", "learner_pipe")
    list_body = _make_list_response([
        {"learner_id": "learner_pipe", "session_id": "sess_pipe_001"},
    ])

    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    from run_session_review_pipeline import run_pipeline  # noqa: E402

    with _mock_urlopen({
        "/api/sessions/list": (200, list_body),
        "/api/sessions/get":  (200, record),
    }):
        code = run_pipeline(
            app_url="https://example.railway.app",
            admin_token="tok",
            sessions_root=tmp_sessions,
            out_dir=tmp_out_dir,
            dry_run=False,
            open_result=False,
        )

    assert code == 0, "pipeline should succeed when new sessions exist"
    md_files = list(tmp_out_dir.glob("batch_*.md"))
    assert md_files, "batch prompt .md file should be created"
    manifest_files = list(tmp_out_dir.glob("batch_*_manifest.json"))
    assert manifest_files, "batch manifest should be created"


# ── 9. Pipeline exits cleanly when no new sessions ────────────────────────────

def test_pipeline_exits_cleanly_no_new_sessions(tmp_sessions, tmp_out_dir):
    # Pre-populate a session and a manifest that marks it as reviewed
    record = _make_session_record("sess_already", "learner_done")
    local = tmp_sessions / "learner_done" / "sess_already.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(record), encoding="utf-8")

    # Write a manifest that lists this session as already reviewed
    import datetime
    manifest = {
        "schema": "batch_manifest_v1",
        "batch_id": "batch_2026-06-29_01",
        "created_at": "2026-06-29T05:00:00+00:00",
        "sessions_root": str(tmp_sessions),
        "output_prompt_path": str(tmp_out_dir / "batch_2026-06-29_01.md"),
        "session_count": 1,
        "included_sessions": [
            {"learner_id": "learner_done", "session_id": "sess_already",
             "source_path": str(local), "timestamp": "2026-06-29T05:00:00+00:00",
             "transcript_turn_count": 2},
        ],
        "status": "exported_for_manual_ai_review",
    }
    (tmp_out_dir / "batch_2026-06-29_01_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    from run_session_review_pipeline import run_pipeline

    code = run_pipeline(
        app_url="",
        admin_token="",
        sessions_root=tmp_sessions,
        out_dir=tmp_out_dir,
        skip_import=True,   # no server call needed
        dry_run=False,
        open_result=False,
    )
    assert code == 1, "pipeline should return 1 (nothing to export) cleanly"


# ── 10. skip-import still runs batch export ───────────────────────────────────

def test_pipeline_skip_import_uses_local_sessions(tmp_sessions, tmp_out_dir):
    record = _make_session_record("sess_local_only", "learner_local")
    local = tmp_sessions / "learner_local" / "sess_local_only.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(record), encoding="utf-8")

    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    from run_session_review_pipeline import run_pipeline

    code = run_pipeline(
        app_url="",
        admin_token="",
        sessions_root=tmp_sessions,
        out_dir=tmp_out_dir,
        skip_import=True,
        dry_run=False,
        open_result=False,
    )
    assert code == 0
    md_files = list(tmp_out_dir.glob("batch_*.md"))
    assert md_files


# ── 11. PowerShell wrapper checks ─────────────────────────────────────────────

def test_ps1_wrapper_exists():
    ps1 = TOOLS / "session_review.ps1"
    assert ps1.exists(), "tools/session_review.ps1 must exist"


def test_ps1_wrapper_no_hardcoded_real_tokens():
    ps1 = TOOLS / "session_review.ps1"
    content = ps1.read_text(encoding="utf-8")
    # Must not contain a hardcoded real production token.
    # NOTE: "replace_me" is legitimately used as a sentinel guard value in the
    # ps1 ($adminToken -eq "replace_me") so we do NOT assert its absence.
    assert "beta_export_local" not in content, (
        "session_review.ps1 must not contain the real admin token value"
    )


def test_ps1_wrapper_reads_env_vars():
    ps1 = TOOLS / "session_review.ps1"
    content = ps1.read_text(encoding="utf-8")
    assert "MANDARINOS_APP_URL" in content
    assert "MANDARINOS_BETA_ADMIN_TOKEN" in content


def test_ps1_wrapper_calls_pipeline_script():
    ps1 = TOOLS / "session_review.ps1"
    content = ps1.read_text(encoding="utf-8")
    assert "run_session_review_pipeline.py" in content


# ── 12. Sample env file contains only placeholders ───────────────────────────

def test_sample_env_exists():
    sample = TOOLS / "session_review_sample_env.ps1"
    assert sample.exists(), "tools/session_review_sample_env.ps1 must exist"


def test_sample_env_no_real_tokens():
    sample = TOOLS / "session_review_sample_env.ps1"
    content = sample.read_text(encoding="utf-8")
    assert "beta_export_local" not in content, (
        "sample env file must not contain a real admin token"
    )
    assert "replace_me" in content, (
        "sample env file must contain placeholder 'replace_me'"
    )
    assert "YOUR-APP.up.railway.app" in content, (
        "sample env file must contain placeholder URL"
    )


# ── 13. ImportResult summary ──────────────────────────────────────────────────

def test_import_result_summary_lines():
    r = importer.ImportResult()
    r.listed = 5
    r.already_local = 2
    r.downloaded = 2
    r.skipped = 0
    r.failed = 1
    r.errors = ["sess_x (learner_y): timeout"]
    lines = r.summary_lines()
    assert any("listed" in l for l in lines)
    assert any("downloaded" in l for l in lines)
    assert any("failed" in l for l in lines)
    assert any("timeout" in l for l in lines)


def test_import_result_ok_true_when_no_failures():
    r = importer.ImportResult()
    r.downloaded = 3
    assert r.ok() is True


def test_import_result_ok_false_when_failures():
    r = importer.ImportResult()
    r.failed = 1
    assert r.ok() is False


# ── 14. Path safety helper ────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("learner_abc123", True),
    ("sess_1234567890", True),
    ("../evil", False),
    ("", False),
    ("  ", False),
    ("learner/abc", False),
    ("learner\\abc", False),
    ("..learner", False),
    ("a..b", False),    # contains ".." as substring — rejected for safety
])
def test_is_valid_path_component(value, expected):
    assert importer._is_valid_path_component(value) == expected


# ── 15. Source-level checks ───────────────────────────────────────────────────

def test_import_script_exists():
    assert (SCRIPTS / "import_sessions_from_server.py").exists()


def test_pipeline_script_exists():
    assert (SCRIPTS / "run_session_review_pipeline.py").exists()


def test_import_script_has_no_hardcoded_tokens():
    src = (SCRIPTS / "import_sessions_from_server.py").read_text(encoding="utf-8")
    assert "beta_export_local" not in src
    assert "replace_me" not in src


def test_pipeline_script_imports_from_import_module():
    src = (SCRIPTS / "run_session_review_pipeline.py").read_text(encoding="utf-8")
    assert "import_sessions_from_server" in src or "import_sessions" in src


def test_pipeline_script_imports_from_batch_module():
    src = (SCRIPTS / "run_session_review_pipeline.py").read_text(encoding="utf-8")
    assert "export_unreviewed_sessions_batch" in src or "run_batch_export" in src
