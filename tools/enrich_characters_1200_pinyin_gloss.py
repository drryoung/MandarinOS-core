#!/usr/bin/env python3
"""
Backfill characters_1200.json with:
  - pinyin: tone-marked reading via pypinyin (Style.TONE), when missing/null/empty.
  - gloss_en: first CC-CEDICT sense for single-character entries, when missing/null/empty.

CC-CEDICT (CC BY-SA 4.0) is downloaded on first use unless --cedict-path points to an existing
cedict_1_0_ts_utf-8_mdbg.txt (plain) or .gz file.

Does not overwrite non-empty pinyin or gloss_en unless --force.

Usage (repo root):
  pip install -r requirements-tools.txt
  python tools/enrich_characters_1200_pinyin_gloss.py --dry-run
  python tools/enrich_characters_1200_pinyin_gloss.py

See also: tools/backfill_component_gloss_en.py (fills remaining gloss gaps from component_gloss_maps.json).
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"

# Cache path (scratch/ is gitignored in this repo)
DEFAULT_CEDICT_CACHE = ROOT / "scratch" / "cedict_1_0_ts_utf-8_mdbg.txt.gz"

# Rare glyphs missing a single-character CC-CEDICT line (trad-only / variant); learner-safe gloss.
MANUAL_GLOSS_SUPPLEMENT: dict[str, str] = {
    "妳": "you (female; dialectal)",
    "後": "after; behind (traditional form of 后)",
}


def load_best_characters_path() -> tuple[Path, dict]:
    best_p = None
    best_data = None
    best_n = -1
    for rel in ("characters_1200.json", "data/characters_1200.json"):
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        n = len((data.get("characters") or []))
        if n > best_n:
            best_n = n
            best_p = p
            best_data = data
    if not best_p:
        raise SystemExit("No characters_1200.json found at repo root or data/")
    return best_p, best_data


def _parse_cedict_line(line: str) -> tuple[str, str, list[str]] | None:
    """Return (traditional, simplified, gloss_segments) or None."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    idx = line.find("] /")
    if idx < 0:
        return None
    head = line[: idx + 1]
    tail = line[idx + 3 :].rstrip()
    if not tail.endswith("/"):
        return None
    inner = tail[:-1]
    glosses = [g.strip() for g in inner.split("/") if g.strip()]
    m = re.match(r"^(\S+)\s+(\S+)\s+\[([^\]]+)\]$", head)
    if not m:
        return None
    trad, simp, _pin = m.group(1), m.group(2), m.group(3)
    return trad, simp, glosses


def _clean_gloss(g: str, max_len: int = 120) -> str:
    g = re.sub(r"\s+", " ", g).strip()
    # Drop parenthetical variant markers that are very long
    if len(g) > max_len:
        g = g[: max_len - 1].rstrip() + "…"
    return g


# Skip dictionary-only / meta senses when a plain gloss appears later for the same character.
_GLOSS_SKIP_PREFIXES = (
    "abbr. for ",
    "abbr. of ",
    "surname ",
    "variant of ",
    "old variant of ",
    "same as ",
    "see ",
)


def _pick_preferred_gloss(candidates: list[str]) -> str | None:
    if not candidates:
        return None
    for g in candidates:
        g = _clean_gloss(g)
        if not g:
            continue
        low = g.lower()
        if any(low.startswith(p) for p in _GLOSS_SKIP_PREFIXES):
            continue
        return g
    return _clean_gloss(candidates[0])


def build_cedict_single_char_gloss_map(
    lines_iter,
) -> dict[str, str]:
    """Best CC-CEDICT sense per simplified single character (file order, skip meta-only first lines)."""
    buckets: dict[str, list[str]] = {}
    for line in lines_iter:
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        parsed = _parse_cedict_line(line)
        if not parsed:
            continue
        trad, simp, glosses = parsed
        if len(simp) != 1:
            continue
        if not glosses:
            continue
        g0 = glosses[0].strip()
        if not g0:
            continue
        buckets.setdefault(simp, []).append(g0)
    out: dict[str, str] = {}
    for simp, cands in buckets.items():
        chosen = _pick_preferred_gloss(cands)
        if chosen:
            out[simp] = chosen
    return out


def iter_cedict_lines(path: Path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            yield from f
    else:
        yield from path.read_text(encoding="utf-8", errors="replace").splitlines()


def ensure_cedict_gz(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        return dest
    print(f"Downloading CC-CEDICT to {dest.relative_to(ROOT)} …", file=sys.stderr)
    req = urllib.request.Request(
        CEDICT_URL,
        headers={"User-Agent": "MandarinOS-enrich-characters/1.0"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    print("Done.", file=sys.stderr)
    return dest


def load_cedict_gloss_map(cedict_path: Path | None) -> dict[str, str]:
    if cedict_path and cedict_path.is_file():
        p = cedict_path
        print(f"Using CC-CEDICT: {p.relative_to(ROOT)}", file=sys.stderr)
    else:
        p = ensure_cedict_gz(DEFAULT_CEDICT_CACHE)
    return build_cedict_single_char_gloss_map(iter_cedict_lines(p))


def pinyin_for_char(ch: str) -> str:
    from pypinyin import Style, pinyin

    if not ch or len(ch) != 1:
        return ""
    # pinyin() returns nested list; heteronym=False = most common reading
    arr = pinyin(ch, style=Style.TONE, heteronym=False)
    if not arr or not arr[0]:
        return ""
    return str(arr[0][0]).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill pinyin + gloss_en in characters_1200.json")
    ap.add_argument("--dry-run", action="store_true", help="Print stats only; do not write")
    ap.add_argument(
        "--cedict-path",
        type=Path,
        default=None,
        help="Path to cedict .txt or .gz (optional; else download to scratch/)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing non-empty pinyin / gloss_en",
    )
    ap.add_argument(
        "--skip-cedict",
        action="store_true",
        help="Only fill pinyin (no English from CC-CEDICT)",
    )
    args = ap.parse_args()

    path, data = load_best_characters_path()
    rows = data.get("characters") or []

    cedict_map: dict[str, str] = {}
    if not args.skip_cedict:
        try:
            cedict_map = load_cedict_gloss_map(args.cedict_path)
            print(f"CC-CEDICT single-char gloss entries: {len(cedict_map)}", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: CC-CEDICT load failed ({e}); gloss_en fill skipped.", file=sys.stderr)

    filled_py = filled_gl = 0
    skipped_py_existing = skipped_gl_existing = 0
    for row in rows:
        hz = row.get("hanzi")
        if hz is None:
            continue
        ch = str(hz).strip()
        if len(ch) != 1:
            continue

        cur_py = row.get("pinyin")
        has_py = cur_py is not None and str(cur_py).strip() != ""
        if not has_py or args.force:
            py = pinyin_for_char(ch)
            if py:
                row["pinyin"] = py
                filled_py += 1
        else:
            skipped_py_existing += 1

        if not args.skip_cedict and cedict_map:
            cur_gl = row.get("gloss_en")
            has_gl = cur_gl is not None and str(cur_gl).strip() != ""
            if not has_gl or args.force:
                g = cedict_map.get(ch) or MANUAL_GLOSS_SUPPLEMENT.get(ch)
                if g:
                    row["gloss_en"] = g
                    filled_gl += 1
            else:
                skipped_gl_existing += 1

    print(f"File: {path.relative_to(ROOT)}")
    print(f"Rows: {len(rows)}")
    print(f"Filled pinyin: {filled_py}  (kept existing: {skipped_py_existing})")
    print(f"Filled gloss_en: {filled_gl}  (kept existing gloss: {skipped_gl_existing})")

    if args.dry_run:
        print("Dry run — no write.")
        return 0

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
