#!/usr/bin/env python3
"""
Phase 1 + 4: Component glyph frequency + Form-line gloss coverage audit.

- Scans characters_1200.json decomposition_tree / components_flat (CJK only).
- Resolves gloss like ui/app.js resolveGlyphGlossEn (no word-card hint):
  corpus gloss_en → radical_variant_gloss_en → teaching_supplement_en → GLYPH_TEACHING_GLOSS_EN (parsed from ui/app.js).

Run from repo root:
  python scripts/audit_component_gloss_coverage.py

Writes: docs/reports/component_gloss_coverage.md
"""
from __future__ import annotations

import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs" / "reports" / "component_gloss_coverage.md"
APP_JS = ROOT / "ui" / "app.js"


def resolve_component_gloss_maps_path() -> Path | None:
    for p in (ROOT / "component_gloss_maps.json", ROOT / "data" / "component_gloss_maps.json"):
        if p.is_file():
            return p
    return None


def is_cjk_grapheme(ch: str) -> bool:
    if len(ch) != 1:
        return False
    o = ord(ch)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF


def load_characters_1200():
    best = None
    best_rel = None
    best_n = -1
    for rel in ("characters_1200.json", "data/characters_1200.json"):
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            cd = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(cd, dict):
            continue
        n = len(cd.get("characters") or [])
        if n > best_n:
            best_n = n
            best = cd
            best_rel = rel
    return best, best_rel


def parse_glyph_teaching_gloss_en() -> dict[str, str]:
    text = APP_JS.read_text(encoding="utf-8")
    start = text.find("const GLYPH_TEACHING_GLOSS_EN = {")
    if start < 0:
        return {}
    i = text.find("{", start)
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                blob = text[i + 1 : j]
                break
        j += 1
    else:
        return {}
    out: dict[str, str] = {}
    for line in blob.splitlines():
        line = line.strip().rstrip(",")
        if not line:
            continue
        m = re.match(r'^(\S+)\s*:\s*"((?:[^"\\]|\\.)*)"\s*$', line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if not is_cjk_grapheme(key):
            continue
        out[key] = val.replace("\\n", "\n")
    return out


def first_gloss_segment(ge: str) -> str:
    s = (ge or "").strip()
    if not s:
        return ""
    seg = re.split(r"[;/]", s, maxsplit=1)[0].strip()
    return seg[:56] + "…" if len(seg) > 56 else seg


def resolve_glyph_gloss_en(
    g: str,
    char_by_hanzi: dict,
    radical_variant: dict[str, str],
    teaching_supplement: dict[str, str],
    glyph_teaching: dict[str, str],
) -> str:
    if not g or not is_cjk_grapheme(g):
        return ""
    row = char_by_hanzi.get(g)
    if row:
        ge = row.get("gloss_en")
        if ge is not None and str(ge).strip():
            return first_gloss_segment(str(ge))
    if g in radical_variant and str(radical_variant[g]).strip():
        s = str(radical_variant[g]).strip()
        return s[:56] + "…" if len(s) > 56 else s
    if g in teaching_supplement and str(teaching_supplement[g]).strip():
        s = str(teaching_supplement[g]).strip()
        return s[:56] + "…" if len(s) > 56 else s
    return glyph_teaching.get(g, "")


def iter_component_glyphs(row: dict) -> list[str]:
    seen: list[str] = []
    tree = row.get("decomposition_tree")
    if tree and isinstance(tree.get("args"), list):
        for a in tree["args"]:
            c = (a or {}).get("char")
            if isinstance(c, str) and c.strip():
                ch = c.strip()
                if is_cjk_grapheme(ch):
                    seen.append(ch)
        if seen:
            return seen
    for c in row.get("components_flat") or []:
        if isinstance(c, str) and c.strip():
            ch = c.strip()
            if is_cjk_grapheme(ch):
                seen.append(ch)
    return seen


def main() -> int:
    cd, chars_rel = load_characters_1200()
    if not cd:
        print("MISSING: characters_1200.json", file=sys.stderr)
        return 1

    maps_path = resolve_component_gloss_maps_path()
    maps = {}
    if maps_path:
        maps = json.loads(maps_path.read_text(encoding="utf-8"))
    radical_variant = maps.get("radical_variant_gloss_en") or {}
    teaching_supplement = maps.get("teaching_supplement_en") or {}
    if not isinstance(radical_variant, dict):
        radical_variant = {}
    if not isinstance(teaching_supplement, dict):
        teaching_supplement = {}

    glyph_teaching = parse_glyph_teaching_gloss_en()

    rows = cd.get("characters") or []
    char_by_hanzi: dict[str, dict] = {}
    for row in rows:
        hz = row.get("hanzi")
        if hz is None:
            continue
        h = str(hz).strip()
        if h and h not in char_by_hanzi:
            char_by_hanzi[h] = row

    comp_freq: Counter[str] = Counter()
    for row in rows:
        for ch in iter_component_glyphs(row):
            comp_freq[ch] += 1

    total_with_tree = 0
    full_gloss = 0
    partial = 0
    none_gloss = 0
    examples_missing: list[tuple[str, list[str]]] = []

    for row in rows:
        pieces = iter_component_glyphs(row)
        if not pieces:
            continue
        total_with_tree += 1
        glosses = [
            resolve_glyph_gloss_en(p, char_by_hanzi, radical_variant, teaching_supplement, glyph_teaching)
            for p in pieces
        ]
        n_ok = sum(1 for x in glosses if x)
        if n_ok == len(pieces):
            full_gloss += 1
        elif n_ok == 0:
            none_gloss += 1
            hz = str(row.get("hanzi") or "").strip()
            if len(examples_missing) < 40:
                examples_missing.append((hz, pieces))
        else:
            partial += 1

    top_n = 80
    top_list = comp_freq.most_common(top_n)

    lines: list[str] = [
        "# Component gloss coverage audit",
        "",
        f"Generated by `scripts/audit_component_gloss_coverage.py`.",
        "",
        "## Inputs",
        "",
        f"- **characters_1200:** `{chars_rel}` ({len(rows)} row(s))",
        f"- **component_gloss_maps:** `{maps_path.relative_to(ROOT) if maps_path else '(missing)'}`",
        f"- **GLYPH_TEACHING_GLOSS_EN:** parsed from `ui/app.js` ({len(glyph_teaching)} key(s))",
        "",
        "## Phase 1 — Top component glyphs (CJK only, by frequency)",
        "",
        "| Rank | Glyph | Count | Resolved gloss |",
        "|------|-------|------:|----------------|",
    ]
    for i, (g, cnt) in enumerate(top_list, start=1):
        gloss = resolve_glyph_gloss_en(g, char_by_hanzi, radical_variant, teaching_supplement, glyph_teaching)
        g_esc = g.replace("|", "\\|")
        gl_esc = (gloss or "—").replace("|", "\\|")
        lines.append(f"| {i} | {g_esc} | {cnt} | {gl_esc} |")

    pct_full = (100.0 * full_gloss / total_with_tree) if total_with_tree else 0.0
    lines.extend(
        [
            "",
            "## Phase 4 — Form-line resolution (all tree/flat pieces have gloss)",
            "",
            f"- Character rows with at least one CJK component: **{total_with_tree}**",
            f"- All components glossed: **{full_gloss}** ({pct_full:.1f}%)",
            f"- Some glossed: **{partial}**",
            f"- None glossed: **{none_gloss}**",
            "",
            "### Sample rows still missing every component gloss (up to 40)",
            "",
        ]
    )
    for hz, pieces in examples_missing:
        lines.append(f"- **{hz}** → `{', '.join(pieces)}`")
    lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}")
    print(f"  All components glossed: {full_gloss}/{total_with_tree} ({pct_full:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
