"""
Session Intelligence — Phase 0 Slice 6: save manual AI batch analysis output.

Reads a Markdown analysis file produced by manually pasting a batch review
prompt into ChatGPT/Claude, validates the structured sections, and saves the
validated outputs into the product intelligence directory tree.

Usage
-----
# Save a single analysis file:
python scripts/save_batch_review_analysis.py \\
    data/review_outputs/inbox/batch_2026-06-29_01_analysis.md

# Dry-run (validate only, write nothing):
python scripts/save_batch_review_analysis.py \\
    data/review_outputs/inbox/batch_2026-06-29_01_analysis.md --dry-run

# Force overwrite of existing outputs:
python scripts/save_batch_review_analysis.py \\
    data/review_outputs/inbox/batch_2026-06-29_01_analysis.md --overwrite

Output tree
-----------
data/review_outputs/analyses/<batch_id>_analysis.md    (full original text)
data/product_intel/rollups/<batch_id>_rollup.json      (Section G JSON)
data/product_intel/cursor_tasks/<batch_id>_tasks.md    (Section H Markdown)
data/product_intel/manifests/<batch_id>_analysis_manifest.json

Architecture reference: docs/session_intelligence_architecture.md §Phase 2
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Paths ─────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
_BASE = Path(os.environ.get("MANDARINOS_DATA_DIR", str(_DEFAULT_DATA_DIR)))

_DEFAULT_ANALYSIS_ROOT  = _BASE / "review_outputs" / "analyses"
_DEFAULT_ROLLUP_ROOT    = _BASE / "product_intel"  / "rollups"
_DEFAULT_TASKS_ROOT     = _BASE / "product_intel"  / "cursor_tasks"
_DEFAULT_MANIFEST_ROOT  = _BASE / "product_intel"  / "manifests"

ROLLUP_SCHEMA      = "product_intel_rollup_v1"
MANIFEST_SCHEMA    = "analysis_manifest_v1"

# Section headers — match ### G. / ## G. / # G. in any case
_SECTION_RE = re.compile(
    r"^#{1,4}\s+([A-H])[.\s].*$",
    re.IGNORECASE | re.MULTILINE,
)
# ```json ... ``` code block
_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*\n([\s\S]*?)\n```",
    re.IGNORECASE,
)
# Filename batch_id extraction: batch_YYYY-MM-DD_NN
_BATCH_ID_FROM_FILENAME_RE = re.compile(
    r"(batch_\d{4}-\d{2}-\d{2}_\d+)",
    re.IGNORECASE,
)


# ── IO helpers ────────────────────────────────────────────────────────────────

def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _now_iso() -> str:
    try:
        return datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ── Markdown parsing ──────────────────────────────────────────────────────────

def _section_spans(text: str) -> List[Tuple[str, int, int]]:
    """
    Return list of (letter, start, end) tuples for each section header found.
    `end` is the start of the next section header (or end of text).
    """
    matches = list(_SECTION_RE.finditer(text))
    spans = []
    for i, m in enumerate(matches):
        letter = m.group(1).upper()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        spans.append((letter, start, end))
    return spans


def extract_section(text: str, letter: str) -> Optional[str]:
    """Return the full content of section `letter` (e.g. 'G'), or None."""
    for ltr, start, end in _section_spans(text):
        if ltr == letter.upper():
            return text[start:end].strip()
    return None


def find_json_block(section_text: str) -> Optional[str]:
    """Return the first ```json...``` block content inside section_text."""
    m = _JSON_BLOCK_RE.search(section_text)
    return m.group(1).strip() if m else None


def detect_batch_id_from_filename(path: Path) -> Optional[str]:
    """Extract batch_id from filename pattern batch_YYYY-MM-DD_NN*."""
    m = _BATCH_ID_FROM_FILENAME_RE.search(path.stem)
    return m.group(1) if m else None


# ── Validation ────────────────────────────────────────────────────────────────

class ValidationError(Exception):
    pass


def parse_and_validate_rollup(section_g_text: str) -> Dict[str, Any]:
    """
    Find and validate the product_intel_rollup_v1 JSON block inside section G.

    Returns the parsed dict on success.
    Raises ValidationError with a descriptive message on failure.
    """
    raw_json = find_json_block(section_g_text)
    if raw_json is None:
        raise ValidationError(
            "Section G (Product Intelligence Rollup) does not contain a ```json``` block. "
            "Make sure you pasted the full AI response including the JSON rollup."
        )

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"Section G JSON block is not valid JSON: {exc}\n\n"
            f"Excerpt (first 300 chars):\n{raw_json[:300]}"
        ) from exc

    if not isinstance(data, dict):
        raise ValidationError(
            f"Section G JSON block should be a JSON object, got: {type(data).__name__}"
        )

    schema = data.get("schema") or data.get("schema_version") or ""
    if schema != ROLLUP_SCHEMA:
        raise ValidationError(
            f"Section G JSON schema is {schema!r} — expected {ROLLUP_SCHEMA!r}. "
            "Make sure the AI returned the product_intel_rollup_v1 block."
        )

    # batch_id may be blank here; resolve_batch_id() falls back to the filename.
    # We only hard-fail if both the rollup AND the filename lack a batch_id.

    if data.get("sessions_analysed") is None:
        raise ValidationError(
            "Section G rollup JSON is missing 'sessions_analysed'."
        )

    if not isinstance(data.get("top_findings"), list):
        raise ValidationError(
            f"Section G rollup JSON 'top_findings' must be a list, "
            f"got: {type(data.get('top_findings')).__name__}"
        )

    return data


def resolve_batch_id(
    rollup: Optional[Dict],
    source_path: Path,
) -> str:
    """
    Determine the canonical batch_id.

    Priority:
      1. rollup['batch_id'] (from validated JSON)
      2. filename pattern
    """
    if rollup and rollup.get("batch_id"):
        return rollup["batch_id"].strip()
    from_filename = detect_batch_id_from_filename(source_path)
    if from_filename:
        return from_filename
    raise ValidationError(
        "Cannot determine batch_id: neither the rollup JSON nor the filename "
        "contains a recognisable batch_id. Filename should include e.g. 'batch_2026-06-29_01'."
    )


# ── Main save logic ───────────────────────────────────────────────────────────

class SaveResult:
    """Summary of a save operation."""

    def __init__(self) -> None:
        self.batch_id: str = ""
        self.analysis_path: Optional[Path] = None
        self.rollup_path: Optional[Path] = None
        self.tasks_path: Optional[Path] = None
        self.manifest_path: Optional[Path] = None
        self.warnings: List[str] = []

    def print_summary(self, dry_run: bool = False) -> None:
        prefix = "[dry-run] " if dry_run else ""
        print(f"\n{prefix}Saved analysis for batch_id: {self.batch_id!r}")
        if self.analysis_path:
            print(f"  Full analysis : {self.analysis_path}")
        if self.rollup_path:
            print(f"  Rollup JSON   : {self.rollup_path}")
        if self.tasks_path:
            print(f"  Cursor tasks  : {self.tasks_path}")
        if self.manifest_path:
            print(f"  Manifest      : {self.manifest_path}")
        for w in self.warnings:
            print(f"  [warn] {w}", file=sys.stderr)


def save_analysis(
    source_path: Path,
    *,
    analysis_root: Path,
    rollup_root: Path,
    tasks_root: Path,
    manifest_root: Path,
    dry_run: bool = False,
    overwrite: bool = False,
) -> SaveResult:
    """
    Read, validate, and save a manual AI batch analysis file.

    Raises:
        ValidationError  if the input fails validation.
        FileExistsError  if outputs exist and --overwrite was not passed.
        FileNotFoundError  if source_path does not exist.
    """
    result = SaveResult()

    # 1. Read source file
    if not source_path.exists():
        raise FileNotFoundError(f"Analysis file not found: {source_path}")
    full_text = source_path.read_text(encoding="utf-8")

    # 2. Extract and validate Section G
    section_g = extract_section(full_text, "G")
    if section_g is None:
        raise ValidationError(
            "Section G (Product Intelligence Rollup) not found in the analysis file.\n"
            "Make sure the AI response includes '### G. Product Intelligence Rollup'."
        )

    rollup = parse_and_validate_rollup(section_g)

    # 3. Resolve batch_id
    batch_id = resolve_batch_id(rollup, source_path)
    result.batch_id = batch_id

    # 4. Extract Section H (Cursor tasks)
    section_h = extract_section(full_text, "H")
    if section_h is None:
        result.warnings.append(
            "Section H (Prioritised Cursor Task List) not found. "
            "The cursor_tasks file will not be created."
        )

    # 5. Determine output paths
    analysis_path  = analysis_root  / f"{batch_id}_analysis.md"
    rollup_path    = rollup_root    / f"{batch_id}_rollup.json"
    tasks_path     = (tasks_root    / f"{batch_id}_tasks.md") if section_h else None
    manifest_path  = manifest_root  / f"{batch_id}_analysis_manifest.json"

    result.analysis_path  = analysis_path
    result.rollup_path    = rollup_path
    result.tasks_path     = tasks_path
    result.manifest_path  = manifest_path

    # 6. Check for existing outputs
    existing = [p for p in [analysis_path, rollup_path, tasks_path, manifest_path] if p and p.exists()]
    if existing and not overwrite:
        paths_str = "\n  ".join(str(p) for p in existing)
        raise FileExistsError(
            f"Output files already exist:\n  {paths_str}\n\n"
            "Pass --overwrite to replace them."
        )

    if dry_run:
        return result

    # 7. Write outputs atomically
    _atomic_write(analysis_path, full_text)
    _atomic_write(rollup_path, json.dumps(rollup, ensure_ascii=False, indent=2))
    if section_h and tasks_path:
        _atomic_write(tasks_path, section_h)

    # 8. Build and write manifest
    manifest: Dict[str, Any] = {
        "schema":               MANIFEST_SCHEMA,
        "batch_id":             batch_id,
        "created_at":           _now_iso(),
        "source_analysis_path": str(source_path),
        "saved_analysis_path":  str(analysis_path),
        "rollup_path":          str(rollup_path),
        "cursor_tasks_path":    str(tasks_path) if tasks_path else None,
        "rollup_schema":        rollup.get("schema", ROLLUP_SCHEMA),
        "sessions_analysed":    rollup.get("sessions_analysed"),
        "top_findings_count":   len(rollup.get("top_findings") or []),
        "status":               "manual_ai_analysis_saved",
        "warnings":             result.warnings,
    }
    _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Save and validate a manual AI batch analysis Markdown file into "
            "the product intelligence directory tree."
        )
    )
    p.add_argument(
        "source",
        type=Path,
        metavar="ANALYSIS_FILE",
        help="Path to the Markdown analysis file from ChatGPT/Claude.",
    )
    p.add_argument(
        "--analysis-root",
        type=Path,
        default=_DEFAULT_ANALYSIS_ROOT,
        metavar="DIR",
        help=f"Where to save the full analysis copy. Default: {_DEFAULT_ANALYSIS_ROOT}",
    )
    p.add_argument(
        "--rollup-root",
        type=Path,
        default=_DEFAULT_ROLLUP_ROOT,
        metavar="DIR",
        help=f"Where to save the rollup JSON. Default: {_DEFAULT_ROLLUP_ROOT}",
    )
    p.add_argument(
        "--tasks-root",
        type=Path,
        default=_DEFAULT_TASKS_ROOT,
        metavar="DIR",
        help=f"Where to save the Cursor task list. Default: {_DEFAULT_TASKS_ROOT}",
    )
    p.add_argument(
        "--manifest-root",
        type=Path,
        default=_DEFAULT_MANIFEST_ROOT,
        metavar="DIR",
        help=f"Where to save the manifest. Default: {_DEFAULT_MANIFEST_ROOT}",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing output files.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate the input and show what would be written without writing anything.",
    )
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)

    source = args.source.resolve()

    try:
        result = save_analysis(
            source_path=source,
            analysis_root=args.analysis_root.resolve(),
            rollup_root=args.rollup_root.resolve(),
            tasks_root=args.tasks_root.resolve(),
            manifest_root=args.manifest_root.resolve(),
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValidationError as exc:
        print(f"Validation error:\n{exc}", file=sys.stderr)
        sys.exit(2)
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(3)
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(4)

    result.print_summary(dry_run=args.dry_run)

    if args.dry_run:
        print("\n[dry-run] No files written. Validation passed.")


if __name__ == "__main__":
    main()
