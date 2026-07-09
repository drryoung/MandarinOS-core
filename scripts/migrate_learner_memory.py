"""
One-time migration script: clean ASR-junk from data/learner_memory.json.

Old versions of MandarinOS captured raw STT output (e.g. "等你等新西兰的南方")
directly into learner memory fields before the normalize_place_name guard was
added.  This script applies the current sanitisation rules to every stored
value and removes unrecoverable junk.

Usage
-----
Run from the repository root:

    python scripts/migrate_learner_memory.py

Flags
-----
--dry-run   Print what would change without writing the file.
--path      Override the learner_memory.json path.

The script is idempotent — running it twice produces no further changes.
"""

import argparse
import sys
from pathlib import Path

# Allow both `python scripts/migrate_learner_memory.py` (repo root) and
# `python migrate_learner_memory.py` (from inside scripts/).
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from learner_memory import migrate_corrupted_memory, BASE_DATA_DIR  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Clean ASR junk from data/learner_memory.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print changes without writing the file.",
    )
    p.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Path to learner_memory.json (default: data/learner_memory.json).",
    )
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    target = args.path or (BASE_DATA_DIR / "learner_memory.json")

    learners_changed, fields_changed, log = migrate_corrupted_memory(
        path=target,
        dry_run=args.dry_run,
    )

    import sys as _sys
    for line in log:
        try:
            print(line)
        except UnicodeEncodeError:
            # Windows terminals may not support all Unicode; fall back to ASCII-safe.
            print(line.encode("ascii", errors="replace").decode("ascii"))

    if args.dry_run and fields_changed > 0:
        print("\nRe-run without --dry-run to apply these changes.")
    elif fields_changed == 0:
        print("No corrupted values found. File is already clean.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
