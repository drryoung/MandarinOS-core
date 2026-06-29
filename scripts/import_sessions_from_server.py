"""
Session Intelligence — Phase 0 Slice 5: import session files from Railway.

Downloads missing session_record_v1 files from the live Railway app using the
read-only admin endpoints added in Phase 0 Slice 4.

Usage
-----
# Dry run (show what would be downloaded, write nothing):
python scripts/import_sessions_from_server.py --dry-run

# Download missing sessions (token from env var):
python scripts/import_sessions_from_server.py \\
    --app-url %MANDARINOS_APP_URL% \\
    --admin-token %MANDARINOS_BETA_ADMIN_TOKEN%

# Force re-download even if file already exists locally:
python scripts/import_sessions_from_server.py \\
    --app-url https://YOUR-APP.up.railway.app \\
    --admin-token YOUR_TOKEN \\
    --overwrite

Endpoints used (read-only)
--------------------------
GET /api/sessions/list?admin_token=TOKEN
GET /api/sessions/get?learner_id=X&session_id=Y&admin_token=TOKEN

Safe to run repeatedly — existing local files are skipped unless --overwrite.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Constants ─────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
BASE_DATA_DIR = Path(os.environ.get("MANDARINOS_DATA_DIR", str(_DEFAULT_DATA_DIR)))
_DEFAULT_OUT_ROOT = BASE_DATA_DIR / "sessions"

SCHEMA_VERSION = "session_record_v1"

# HTTP timeout in seconds
_HTTP_TIMEOUT = 30


# ── ImportResult ──────────────────────────────────────────────────────────────

class ImportResult:
    """Summary of an import run."""

    def __init__(self) -> None:
        self.listed: int = 0
        self.already_local: int = 0
        self.downloaded: int = 0
        self.skipped: int = 0       # dry-run or --no-overwrite skips
        self.failed: int = 0
        self.errors: List[str] = []

    def ok(self) -> bool:
        return self.failed == 0

    def summary_lines(self) -> List[str]:
        lines = [
            f"  sessions listed on server : {self.listed}",
            f"  already local             : {self.already_local}",
            f"  downloaded                : {self.downloaded}",
            f"  skipped (dry-run/exists)  : {self.skipped}",
            f"  failed                    : {self.failed}",
        ]
        for err in self.errors:
            lines.append(f"  [error] {err}")
        return lines


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _build_url(app_url: str, path: str, params: Dict[str, str]) -> str:
    base = app_url.rstrip("/")
    qs = urllib.parse.urlencode(params)
    return f"{base}{path}?{qs}"


def _get_json(url: str, timeout: int = _HTTP_TIMEOUT) -> Tuple[int, Any]:
    """Fetch URL, return (status_code, parsed_json_or_None)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, None
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Cannot reach server: {exc.reason}") from exc
    except Exception as exc:
        raise ConnectionError(f"HTTP error: {exc}") from exc


# ── Local file helpers ────────────────────────────────────────────────────────

def _atomic_write_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        shutil.move(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _local_path(out_root: Path, learner_id: str, session_id: str) -> Path:
    return out_root / learner_id / f"{session_id}.json"


def _is_valid_path_component(value: str) -> bool:
    """Reject path traversal or unsafe characters in learner_id / session_id."""
    if not value or not value.strip():
        return False
    bad = set('/\\:*?"<>|')
    if any(c in bad for c in value):
        return False
    if ".." in value:
        return False
    return True


# ── Core import logic ─────────────────────────────────────────────────────────

def fetch_session_list(app_url: str, admin_token: str) -> List[Dict]:
    """Call /api/sessions/list and return the sessions array."""
    url = _build_url(app_url, "/api/sessions/list", {"admin_token": admin_token})
    status, body = _get_json(url)
    if status == 403:
        raise PermissionError("Admin token rejected (403). Check MANDARINOS_BETA_ADMIN_TOKEN.")
    if status == 401:
        raise PermissionError("Unauthorized (401). Check MANDARINOS_BETA_ADMIN_TOKEN.")
    if status != 200:
        msg = (body or {}).get("error", "") if isinstance(body, dict) else ""
        raise RuntimeError(f"Unexpected status {status} from /api/sessions/list: {msg}")
    if not isinstance(body, dict) or not body.get("ok"):
        raise RuntimeError(f"Unexpected response shape from /api/sessions/list: {body!r}")
    sessions = body.get("sessions")
    if not isinstance(sessions, list):
        raise RuntimeError(f"'sessions' field is not a list: {body!r}")
    return sessions


def fetch_session_record(
    app_url: str, admin_token: str, learner_id: str, session_id: str
) -> Dict:
    """Call /api/sessions/get and return the session_record_v1 dict."""
    url = _build_url(
        app_url,
        "/api/sessions/get",
        {"learner_id": learner_id, "session_id": session_id, "admin_token": admin_token},
    )
    status, body = _get_json(url)
    if status == 403:
        raise PermissionError(f"Admin token rejected (403) for {session_id}.")
    if status == 404:
        raise FileNotFoundError(f"Session not found on server: {session_id}")
    if status == 422:
        msg = (body or {}).get("error", "") if isinstance(body, dict) else ""
        raise ValueError(f"Server returned 422 for {session_id}: {msg}")
    if status != 200:
        msg = (body or {}).get("error", "") if isinstance(body, dict) else ""
        raise RuntimeError(f"Unexpected status {status} for {session_id}: {msg}")
    if not isinstance(body, dict):
        raise ValueError(f"Response for {session_id} is not a JSON object")
    schema = body.get("schema") or body.get("schema_version") or ""
    if schema != SCHEMA_VERSION:
        raise ValueError(
            f"Downloaded file for {session_id} has unexpected schema: {schema!r} "
            f"(expected {SCHEMA_VERSION!r})"
        )
    return body


def import_sessions(
    *,
    app_url: str,
    admin_token: str,
    out_root: Path,
    dry_run: bool = False,
    overwrite: bool = False,
    quiet: bool = False,
) -> ImportResult:
    """
    Download missing session_record_v1 files from the Railway app.

    Returns an ImportResult summary. Never raises for per-session failures —
    those are recorded in result.errors and result.failed.

    Raises:
        ConnectionError  if the server cannot be reached.
        PermissionError  if the admin token is rejected.
        RuntimeError     if the list endpoint returns an unexpected response.
    """
    result = ImportResult()

    # 1. Fetch session list
    sessions = fetch_session_list(app_url, admin_token)
    result.listed = len(sessions)

    if not quiet:
        print(f"[import] {result.listed} session(s) listed on server")

    # 2. For each session, decide whether to download
    for entry in sessions:
        learner_id = (entry.get("learner_id") or "").strip()
        session_id = (entry.get("session_id") or "").strip()

        # Safety: reject unsafe path components
        if not _is_valid_path_component(learner_id) or not _is_valid_path_component(session_id):
            msg = f"Skipping entry with unsafe learner_id={learner_id!r} session_id={session_id!r}"
            if not quiet:
                print(f"[import] [skip] {msg}")
            result.skipped += 1
            result.errors.append(msg)
            continue

        local = _local_path(out_root, learner_id, session_id)

        if local.exists() and not overwrite:
            if not quiet:
                print(f"[import] [local] {session_id}  ({learner_id})")
            result.already_local += 1
            continue

        if dry_run:
            action = "overwrite" if (local.exists() and overwrite) else "download"
            print(f"[import] [dry-run] would {action}: {session_id}  learner={learner_id}  → {local}")
            result.skipped += 1
            continue

        # 3. Download
        try:
            record = fetch_session_record(app_url, admin_token, learner_id, session_id)
            _atomic_write_json(local, record)
            if not quiet:
                turns = len(record.get("transcript") or [])
                print(f"[import] [ok] {session_id}  learner={learner_id}  turns={turns}  → {local}")
            result.downloaded += 1
        except Exception as exc:
            msg = f"{session_id} ({learner_id}): {exc}"
            if not quiet:
                print(f"[import] [fail] {msg}", file=sys.stderr)
            result.failed += 1
            result.errors.append(msg)

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Download missing session_record_v1 files from the Railway app "
            "into local data/sessions/."
        )
    )
    p.add_argument(
        "--app-url",
        default=os.environ.get("MANDARINOS_APP_URL", ""),
        metavar="URL",
        help="Base URL of the Railway app (e.g. https://your-app.up.railway.app). "
             "Defaults to $MANDARINOS_APP_URL.",
    )
    p.add_argument(
        "--admin-token",
        default=os.environ.get("MANDARINOS_BETA_ADMIN_TOKEN", ""),
        metavar="TOKEN",
        help="Admin token for gated endpoints. Defaults to $MANDARINOS_BETA_ADMIN_TOKEN.",
    )
    p.add_argument(
        "--out-root",
        type=Path,
        default=_DEFAULT_OUT_ROOT,
        metavar="DIR",
        help=f"Local root for sessions. Default: {_DEFAULT_OUT_ROOT}",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report what would be downloaded without writing any files.",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Re-download and overwrite files that already exist locally.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress per-session progress output.",
    )
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if not args.app_url:
        print(
            "Error: --app-url is required (or set $MANDARINOS_APP_URL).",
            file=sys.stderr,
        )
        sys.exit(1)
    if not args.admin_token:
        print(
            "Error: --admin-token is required (or set $MANDARINOS_BETA_ADMIN_TOKEN).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        result = import_sessions(
            app_url=args.app_url.rstrip("/"),
            admin_token=args.admin_token,
            out_root=args.out_root.resolve(),
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            quiet=args.quiet,
        )
    except (ConnectionError, PermissionError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    print("\n[import] Summary:")
    for line in result.summary_lines():
        print(line)

    if not result.ok():
        sys.exit(3)


if __name__ == "__main__":
    main()
