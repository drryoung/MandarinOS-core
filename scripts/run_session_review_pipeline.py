"""
Session Intelligence — Phase 0 Slice 5: one-command local review pipeline.

Runs the full local workflow in a single command:
  1. Import missing session_record_v1 files from Railway.
  2. Run the unreviewed batch exporter.
  3. Print (and optionally open) the generated batch prompt.

Usage
-----
# Full pipeline (token from env vars):
python scripts/run_session_review_pipeline.py \\
    --app-url %MANDARINOS_APP_URL% \\
    --admin-token %MANDARINOS_BETA_ADMIN_TOKEN%

# Dry run (no files written):
python scripts/run_session_review_pipeline.py --dry-run

# Open the batch prompt in the default editor after creation:
python scripts/run_session_review_pipeline.py \\
    --app-url %MANDARINOS_APP_URL% \\
    --admin-token %MANDARINOS_BETA_ADMIN_TOKEN% \\
    --open

# Skip the import step (use only locally available sessions):
python scripts/run_session_review_pipeline.py --skip-import

Architecture reference: docs/session_intelligence_architecture.md
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Ensure scripts/ is importable
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

# Lazy imports so each module is only loaded when needed
from import_sessions_from_server import import_sessions, ImportResult  # noqa: E402
from export_unreviewed_sessions_batch import (    # noqa: E402
    BASE_DATA_DIR as _BATCH_BASE,
    _DEFAULT_SESSIONS_ROOT,
    _DEFAULT_OUT_DIR,
    _DEFAULT_MAX_SESSIONS,
    run_batch_export,
)

_DEFAULT_SESSIONS_ROOT_PIPELINE = _DEFAULT_SESSIONS_ROOT
_DEFAULT_OUT_DIR_PIPELINE = _DEFAULT_OUT_DIR


# ── helpers ───────────────────────────────────────────────────────────────────

def _open_file(path: Path) -> None:
    """Open a file in the default OS application (best-effort)."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))          # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as exc:
        print(f"[pipeline] Could not open file automatically: {exc}", file=sys.stderr)


def _print_separator(char: str = "─", width: int = 60) -> None:
    print(char * width)


# ── pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(
    *,
    app_url: str = "",
    admin_token: str = "",
    sessions_root: Path,
    out_dir: Path,
    max_sessions: int = _DEFAULT_MAX_SESSIONS,
    include_reviewed: bool = False,
    dry_run: bool = False,
    skip_import: bool = False,
    open_result: bool = False,
    no_stdout: bool = True,
    quiet_import: bool = False,
) -> int:
    """
    Run the full import → batch export pipeline.

    Returns exit code: 0 = success, 1 = nothing to export, 2 = error.
    """
    # ── Step 1: Import ────────────────────────────────────────────────────────
    if skip_import or dry_run:
        if not skip_import:
            print("[pipeline] Step 1: Import — skipped (dry-run mode)")
        else:
            print("[pipeline] Step 1: Import — skipped (--skip-import)")
        import_result = None
    elif not app_url or not admin_token:
        print(
            "[pipeline] Step 1: Import — skipped (no --app-url / --admin-token provided).\n"
            "           Use --skip-import to suppress this warning, or provide credentials.",
            file=sys.stderr,
        )
        import_result = None
    else:
        _print_separator()
        print("[pipeline] Step 1: Importing sessions from Railway…")
        _print_separator()
        try:
            import_result = import_sessions(
                app_url=app_url.rstrip("/"),
                admin_token=admin_token,
                out_root=sessions_root,
                dry_run=False,         # real import here; dry-run is handled above
                overwrite=False,
                quiet=quiet_import,
            )
        except (ConnectionError, PermissionError, RuntimeError) as exc:
            print(f"[pipeline] Import failed: {exc}", file=sys.stderr)
            return 2
        print()
        print("[pipeline] Import summary:")
        for line in import_result.summary_lines():
            print(line)

    # ── Step 2: Batch export ──────────────────────────────────────────────────
    _print_separator()
    print("[pipeline] Step 2: Exporting unreviewed sessions…")
    _print_separator()

    code = run_batch_export(
        sessions_root=sessions_root,
        out_dir=out_dir,
        max_sessions=max_sessions,
        include_reviewed=include_reviewed,
        dry_run=dry_run,
        stdout=False,   # never dump the full prompt to stdout in pipeline mode
    )

    if code != 0:
        # run_batch_export prints its own message to stderr
        print(
            "\n[pipeline] No batch prompt created — nothing to review.",
            file=sys.stderr,
        )
        return 1

    # ── Step 3: Report path and next steps ────────────────────────────────────
    _print_separator()
    print("[pipeline] Done.")
    _print_separator()

    # Find the most-recently modified .md file in out_dir
    prompt_path: Path | None = None
    manifest_path: Path | None = None
    if out_dir.is_dir():
        md_files = sorted(out_dir.glob("batch_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if md_files:
            prompt_path = md_files[0]
        json_files = sorted(out_dir.glob("batch_*_manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if json_files:
            manifest_path = json_files[0]

    if prompt_path:
        print(f"\n  Batch prompt : {prompt_path}")
    if manifest_path:
        print(f"  Manifest     : {manifest_path}")

    print()
    print("  Next steps:")
    print("  1. Open the batch prompt file above.")
    print("  2. Copy the entire contents.")
    print("  3. Paste into ChatGPT or Claude (Projects recommended).")
    print("  4. Save the AI response as a product_intel_v1 document.")
    print()

    if open_result and prompt_path:
        print(f"[pipeline] Opening: {prompt_path}")
        _open_file(prompt_path)

    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Run the full local session review pipeline: "
            "import from Railway → batch export → open or print path."
        )
    )
    p.add_argument(
        "--app-url",
        default=os.environ.get("MANDARINOS_APP_URL", ""),
        metavar="URL",
        help="Base URL of the Railway app. Defaults to $MANDARINOS_APP_URL.",
    )
    p.add_argument(
        "--admin-token",
        default=os.environ.get("MANDARINOS_BETA_ADMIN_TOKEN", ""),
        metavar="TOKEN",
        help="Admin token. Defaults to $MANDARINOS_BETA_ADMIN_TOKEN.",
    )
    p.add_argument(
        "--sessions-root",
        type=Path,
        default=_DEFAULT_SESSIONS_ROOT_PIPELINE,
        metavar="DIR",
        help=f"Local sessions root. Default: {_DEFAULT_SESSIONS_ROOT_PIPELINE}",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=_DEFAULT_OUT_DIR_PIPELINE,
        metavar="DIR",
        help=f"Batch output directory. Default: {_DEFAULT_OUT_DIR_PIPELINE}",
    )
    p.add_argument(
        "--max-sessions",
        type=int,
        default=_DEFAULT_MAX_SESSIONS,
        metavar="N",
        help=f"Maximum sessions per batch. Default: {_DEFAULT_MAX_SESSIONS}",
    )
    p.add_argument(
        "--include-reviewed",
        action="store_true",
        default=False,
        help="Include sessions already in previous batches.",
    )
    p.add_argument(
        "--skip-import",
        action="store_true",
        default=False,
        help="Skip the Railway import step; use only sessions already local.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would happen without writing any files.",
    )
    p.add_argument(
        "--open",
        dest="open_result",
        action="store_true",
        default=False,
        help="Open the batch prompt in the default OS application when done.",
    )
    p.add_argument(
        "--no-stdout",
        action="store_true",
        default=False,
        help="Suppress the full batch prompt on stdout (already default in pipeline mode).",
    )
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)

    code = run_pipeline(
        app_url=args.app_url,
        admin_token=args.admin_token,
        sessions_root=args.sessions_root.resolve(),
        out_dir=args.out_dir.resolve(),
        max_sessions=max(1, args.max_sessions),
        include_reviewed=args.include_reviewed,
        dry_run=args.dry_run,
        skip_import=args.skip_import,
        open_result=args.open_result,
        no_stdout=args.no_stdout,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
