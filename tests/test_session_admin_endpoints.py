"""
Phase 0 Slice 4 — Session admin export endpoint tests.

Two layers:
  A. Static source checks (no server needed) — verify the handler code is
     correct at the source level: admin-token gate, path-traversal regex,
     schema validation, endpoint routing.
  B. Handler unit tests — mock the HTTP machinery and drive the actual
     Handler.do_GET() methods with a fake request/response pair.

Coverage:
  1.  Source: /api/sessions/list present in do_GET handler.
  2.  Source: /api/sessions/get present in do_GET handler.
  3.  Source: admin_token check appears before any file read.
  4.  Source: path-traversal regex applied to both learner_id and session_id.
  5.  Source: schema check `session_record_v1` present in both handlers.
  6.  Source: no write / delete / modification of session files.
  7.  Source: /api/progress/all still present (regression guard).
  8.  Handler: /api/sessions/list unauthorized → 403.
  9.  Handler: /api/sessions/list authorized empty dir → 200, sessions=[].
  10. Handler: /api/sessions/list returns valid session entries only.
  11. Handler: /api/sessions/list ignores invalid JSON files.
  12. Handler: /api/sessions/list ignores wrong-schema files.
  13. Handler: /api/sessions/get unauthorized → 403.
  14. Handler: /api/sessions/get missing learner_id → 400.
  15. Handler: /api/sessions/get missing session_id → 400.
  16. Handler: /api/sessions/get path-traversal learner_id → 400.
  17. Handler: /api/sessions/get path-traversal session_id → 400.
  18. Handler: /api/sessions/get non-existent session → 404.
  19. Handler: /api/sessions/get valid request → 200 with exact JSON.
  20. Handler: /api/sessions/get wrong-schema file → 422.
  21. Handler: original session files not modified after list.
  22. Handler: original session files not modified after get.
  23. Handler: /api/progress/all still returns 200 (no regression).
"""

import importlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ── Shared fixtures ───────────────────────────────────────────────────────────

SAMPLE_RECORD = {
    "schema": "session_record_v1",
    "capture_source": "end_session_payload",
    "session_id": "session_T001",
    "learner_id": "learner_test",
    "created_at": "2026-06-29T10:00:00+12:00",
    "persona_id": "jianguo",
    "mode": "normal",
    "tier": "standard",
    "duration_seconds": 300,
    "counters": {"total_turns": 8, "engines_used": ["identity"]},
    "metrics": {"flow": {"raw": 8, "label": "Holding"}},
    "transcript": [
        {"idx": 0, "role": "partner", "text_zh": "你好！", "turn_uid": "t_0"},
        {"idx": 1, "role": "user",    "text_zh": "你好。", "turn_uid": "t_0", "matched": True},
    ],
    "event_log": [],
    "capture_flags": {"transcript_present": True, "event_log_present": False},
}

WRONG_SCHEMA_RECORD = {
    "schema": "something_else_v1",
    "session_id": "session_WRONG",
}

ADMIN_TOKEN = "test_admin_token_xyz"


# ── Part A: static source checks ──────────────────────────────────────────────

def _server_src() -> str:
    return (ROOT / "scripts" / "ui_server.py").read_text(encoding="utf-8")


class TestSourceStructure:
    def test_list_endpoint_present(self):
        assert '"/api/sessions/list"' in _server_src()

    def test_get_endpoint_present(self):
        assert '"/api/sessions/get"' in _server_src()

    def test_admin_token_gate_on_list(self):
        src = _server_src()
        list_block_start = src.index('"/api/sessions/list"')
        list_block = src[list_block_start: list_block_start + 600]
        assert "admin_token" in list_block
        assert "_BETA_ADMIN_TOKEN" in list_block
        # Gate check appears before any file read
        gate_pos = list_block.index("_BETA_ADMIN_TOKEN")
        assert gate_pos < list_block.index("rglob")

    def test_admin_token_gate_on_get(self):
        src = _server_src()
        get_block_start = src.index('"/api/sessions/get"')
        get_block = src[get_block_start: get_block_start + 2000]
        assert "admin_token" in get_block
        assert "_BETA_ADMIN_TOKEN" in get_block
        # Gate before any file access
        gate_pos = get_block.index("_BETA_ADMIN_TOKEN")
        assert gate_pos < get_block.index("session_file")

    def test_path_traversal_regex_on_learner_id(self):
        src = _server_src()
        get_block_start = src.index('"/api/sessions/get"')
        get_block = src[get_block_start: get_block_start + 1200]
        # The safe-id regex must be applied to learner_id
        assert "learner_id" in get_block
        assert "_re.match" in get_block

    def test_path_traversal_regex_on_session_id(self):
        src = _server_src()
        get_block_start = src.index('"/api/sessions/get"')
        get_block = src[get_block_start: get_block_start + 1200]
        assert "session_id" in get_block
        # Both learner_id and session_id validated
        assert get_block.count("_re.match") >= 2

    def test_schema_check_in_list(self):
        src = _server_src()
        list_block_start = src.index('"/api/sessions/list"')
        list_block = src[list_block_start: list_block_start + 1200]
        assert "session_record_v1" in list_block

    def test_schema_check_in_get(self):
        src = _server_src()
        get_block_start = src.index('"/api/sessions/get"')
        get_block = src[get_block_start: get_block_start + 2500]
        assert "session_record_v1" in get_block

    def test_no_write_or_delete_in_session_handlers(self):
        src = _server_src()
        # Extract just the two new handler blocks
        list_start = src.index('"/api/sessions/list"')
        end_marker = "# ── end Session Intelligence admin export"
        end_pos = src.index(end_marker)
        session_handlers = src[list_start:end_pos]
        # No file-write calls
        assert ".write_text(" not in session_handlers
        assert ".open(" not in session_handlers
        assert "shutil" not in session_handlers
        assert "os.unlink" not in session_handlers
        assert "os.remove" not in session_handlers

    def test_progress_all_still_present(self):
        assert '"/api/progress/all"' in _server_src()


# ── Part B: handler unit tests ───────────────────────────────────────────────
#
# We test the handler by constructing a minimal fake HTTP environment and
# calling do_GET() directly — no sockets, no threads.

def _make_handler(tmp_path: Path, url_path: str):
    """
    Build a Handler instance wired to a fake request socket, with
    BASE_DATA_DIR pointing at tmp_path and BETA_ADMIN_TOKEN = ADMIN_TOKEN.
    Returns (handler, response_buffer) where response_buffer is a BytesIO
    containing everything the handler wrote.
    """
    # Reload ui_server with patched env so module-level constants pick up
    # the temp dir and token.
    env_patch = {
        "MANDARINOS_DATA_DIR": str(tmp_path),
        "MANDARINOS_BETA_ADMIN_TOKEN": ADMIN_TOKEN,
    }

    with mock.patch.dict(os.environ, env_patch):
        if "ui_server" in sys.modules:
            del sys.modules["ui_server"]
        uiserver = importlib.import_module("ui_server")

    # Patch module-level _DATA_DIR_EFFECTIVE so the handler uses tmp_path.
    # (The module reads env at import time; patching the attribute is safer.)
    uiserver._DATA_DIR_EFFECTIVE = str(tmp_path)
    uiserver._BETA_ADMIN_TOKEN = ADMIN_TOKEN

    response_buf = io.BytesIO()

    class FakeSocket:
        def makefile(self, mode, **kw):
            return io.BytesIO(f"GET {url_path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())

    handler = uiserver.Handler.__new__(uiserver.Handler)
    handler.server = mock.MagicMock()
    handler.connection = FakeSocket()
    handler.client_address = ("127.0.0.1", 9999)
    handler.request = FakeSocket()

    # Patch wfile so all response bytes land in response_buf
    handler.wfile = response_buf
    handler.rfile = io.BytesIO(b"")

    # Make send_response / send_header / end_headers write HTTP preamble too
    _status = []
    _headers = []

    def fake_send_response(code, msg=None):
        _status.append(code)
        response_buf.write(f"HTTP/1.1 {code}\r\n".encode())

    def fake_send_header(k, v):
        _headers.append((k, v))
        response_buf.write(f"{k}: {v}\r\n".encode())

    def fake_end_headers():
        response_buf.write(b"\r\n")

    def fake_log_message(fmt, *a):
        pass

    handler.send_response = fake_send_response
    handler.send_header = fake_send_header
    handler.end_headers = fake_end_headers
    handler.log_message = fake_log_message
    handler.path = url_path

    return handler, response_buf, _status, uiserver


def _parse_response(response_buf: io.BytesIO):
    """Extract the HTTP status codes list and the last JSON body from the buffer."""
    response_buf.seek(0)
    raw = response_buf.read().decode("utf-8", errors="replace")
    # Find the JSON body (after the blank line)
    parts = raw.split("\r\n\r\n", 1)
    body = parts[1] if len(parts) > 1 else raw
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def _write_session(sessions_root: Path, record: dict) -> Path:
    lid = record.get("learner_id", "unknown")
    sid = record.get("session_id", "unknown")
    p = sessions_root / lid / f"{sid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return p


class TestListEndpoint:
    def test_unauthorized_returns_403(self, tmp_path):
        h, buf, status, _ = _make_handler(tmp_path, "/api/sessions/list?admin_token=WRONG")
        h.do_GET()
        body = _parse_response(buf)
        assert 403 in status
        assert body.get("ok") is not True

    def test_authorized_empty_dir_returns_200_empty(self, tmp_path):
        h, buf, status, _ = _make_handler(
            tmp_path, f"/api/sessions/list?admin_token={ADMIN_TOKEN}"
        )
        h.do_GET()
        body = _parse_response(buf)
        assert 200 in status
        assert body["ok"] is True
        assert body["sessions"] == []
        assert body["total_sessions"] == 0

    def test_authorized_returns_valid_sessions(self, tmp_path):
        sessions_root = tmp_path / "sessions"
        _write_session(sessions_root, SAMPLE_RECORD)
        h, buf, status, _ = _make_handler(
            tmp_path, f"/api/sessions/list?admin_token={ADMIN_TOKEN}"
        )
        h.do_GET()
        body = _parse_response(buf)
        assert 200 in status
        assert body["total_sessions"] == 1
        entry = body["sessions"][0]
        assert entry["session_id"] == "session_T001"
        assert entry["learner_id"] == "learner_test"
        assert entry["transcript_turn_count"] == 2
        assert entry["schema_version"] == "session_record_v1"

    def test_ignores_invalid_json(self, tmp_path):
        sessions_root = tmp_path / "sessions" / "learner_x"
        sessions_root.mkdir(parents=True)
        (sessions_root / "bad.json").write_text("{ not json", encoding="utf-8")
        h, buf, status, _ = _make_handler(
            tmp_path, f"/api/sessions/list?admin_token={ADMIN_TOKEN}"
        )
        h.do_GET()
        body = _parse_response(buf)
        assert 200 in status
        assert body["total_sessions"] == 0

    def test_ignores_wrong_schema(self, tmp_path):
        sessions_root = tmp_path / "sessions"
        _write_session(sessions_root, {**WRONG_SCHEMA_RECORD, "learner_id": "learner_x"})
        h, buf, status, _ = _make_handler(
            tmp_path, f"/api/sessions/list?admin_token={ADMIN_TOKEN}"
        )
        h.do_GET()
        body = _parse_response(buf)
        assert body["total_sessions"] == 0

    def test_missing_token_returns_403(self, tmp_path):
        h, buf, status, _ = _make_handler(tmp_path, "/api/sessions/list")
        h.do_GET()
        assert 403 in status


class TestGetEndpoint:
    def test_unauthorized_returns_403(self, tmp_path):
        h, buf, status, _ = _make_handler(
            tmp_path,
            "/api/sessions/get?learner_id=learner_test&session_id=session_T001&admin_token=WRONG",
        )
        h.do_GET()
        assert 403 in status

    def test_missing_learner_id_returns_400(self, tmp_path):
        h, buf, status, _ = _make_handler(
            tmp_path,
            f"/api/sessions/get?session_id=session_T001&admin_token={ADMIN_TOKEN}",
        )
        h.do_GET()
        assert 400 in status

    def test_missing_session_id_returns_400(self, tmp_path):
        h, buf, status, _ = _make_handler(
            tmp_path,
            f"/api/sessions/get?learner_id=learner_test&admin_token={ADMIN_TOKEN}",
        )
        h.do_GET()
        assert 400 in status

    @pytest.mark.parametrize("bad_lid", [
        "../etc/passwd",
        "learner/../../secret",
        "C:\\Windows\\System32",
        "learner id with spaces",
        "a" * 65,
    ])
    def test_path_traversal_learner_id_rejected(self, tmp_path, bad_lid):
        h, buf, status, _ = _make_handler(
            tmp_path,
            f"/api/sessions/get?learner_id={bad_lid}&session_id=session_T001&admin_token={ADMIN_TOKEN}",
        )
        h.do_GET()
        assert 400 in status

    @pytest.mark.parametrize("bad_sid", [
        "../session",
        "session/../../secret",
        "session id",
        "a" * 129,
    ])
    def test_path_traversal_session_id_rejected(self, tmp_path, bad_sid):
        h, buf, status, _ = _make_handler(
            tmp_path,
            f"/api/sessions/get?learner_id=learner_test&session_id={bad_sid}&admin_token={ADMIN_TOKEN}",
        )
        h.do_GET()
        assert 400 in status

    def test_nonexistent_session_returns_404(self, tmp_path):
        h, buf, status, _ = _make_handler(
            tmp_path,
            f"/api/sessions/get?learner_id=learner_test&session_id=session_MISSING&admin_token={ADMIN_TOKEN}",
        )
        h.do_GET()
        assert 404 in status

    def test_valid_request_returns_exact_json(self, tmp_path):
        sessions_root = tmp_path / "sessions"
        _write_session(sessions_root, SAMPLE_RECORD)
        h, buf, status, _ = _make_handler(
            tmp_path,
            f"/api/sessions/get?learner_id=learner_test&session_id=session_T001&admin_token={ADMIN_TOKEN}",
        )
        h.do_GET()
        body = _parse_response(buf)
        assert 200 in status
        assert body["schema"] == "session_record_v1"
        assert body["session_id"] == "session_T001"
        assert len(body["transcript"]) == 2

    def test_wrong_schema_file_returns_422(self, tmp_path):
        sessions_root = tmp_path / "sessions" / "learner_test"
        sessions_root.mkdir(parents=True)
        bad = sessions_root / "session_T001.json"
        bad.write_text(json.dumps(WRONG_SCHEMA_RECORD), encoding="utf-8")
        h, buf, status, _ = _make_handler(
            tmp_path,
            f"/api/sessions/get?learner_id=learner_test&session_id=session_T001&admin_token={ADMIN_TOKEN}",
        )
        h.do_GET()
        assert 422 in status


class TestNoMutation:
    def test_list_does_not_modify_session_files(self, tmp_path):
        sessions_root = tmp_path / "sessions"
        path = _write_session(sessions_root, SAMPLE_RECORD)
        mtime_before = path.stat().st_mtime
        size_before = path.stat().st_size
        h, buf, _, _ = _make_handler(
            tmp_path, f"/api/sessions/list?admin_token={ADMIN_TOKEN}"
        )
        h.do_GET()
        assert path.stat().st_mtime == mtime_before
        assert path.stat().st_size == size_before
        assert json.loads(path.read_text(encoding="utf-8")) == SAMPLE_RECORD

    def test_get_does_not_modify_session_files(self, tmp_path):
        sessions_root = tmp_path / "sessions"
        path = _write_session(sessions_root, SAMPLE_RECORD)
        mtime_before = path.stat().st_mtime
        h, buf, _, _ = _make_handler(
            tmp_path,
            f"/api/sessions/get?learner_id=learner_test&session_id=session_T001&admin_token={ADMIN_TOKEN}",
        )
        h.do_GET()
        assert path.stat().st_mtime == mtime_before
        assert json.loads(path.read_text(encoding="utf-8")) == SAMPLE_RECORD


class TestProgressAllRegression:
    def test_progress_all_still_returns_200(self, tmp_path):
        """Confirm /api/progress/all is unaffected by the new endpoints."""
        h, buf, status, uiserver = _make_handler(
            tmp_path, f"/api/progress/all?admin_token={ADMIN_TOKEN}"
        )
        # Patch the progress loader to avoid needing real progress files
        with mock.patch.object(uiserver, "_ps_load_all", return_value={}):
            h.do_GET()
        body = _parse_response(buf)
        assert 200 in status
        assert body.get("ok") is True
        assert "learners" in body
