#!/usr/bin/env python3
"""
Audit: p1+p2 lexicon vs characters_1200.json vs word_character_links.json vs cards_by_id.
Run from repo root: python scripts/audit_vocab_character_coverage.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
# Windows console often cp1252 — force UTF-8 for Hanzi output
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]

# CJK + basic Latin for hyphenated glosses in hanzi field — skip non-CJK for grapheme check
def graphemes_cjk(hz: str) -> list[str]:
    out = []
    for ch in hz.strip():
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            out.append(ch)
    return out


def load_json(rel: str):
    p = ROOT / rel
    if not p.is_file():
        print(f"MISSING FILE: {rel}", file=sys.stderr)
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_characters_1200():
    """Same as build_runtime_artifacts: try root and data/, prefer file with more `characters[]` rows."""
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


def main():
    words = []
    for name in ("p1_words.json", "p2_words.json"):
        data = load_json(name)
        if not data:
            continue
        for w in data.get("words", []):
            wid = w.get("id") or w.get("word_id")
            hz = w.get("hanzi")
            if wid and hz:
                # first variant before /
                surface = str(hz).split("/")[0].strip()
                words.append((wid, surface))
    lex_ids = {w[0] for w in words}
    print("=== LEXICON (p1_words + p2_words) ===")
    print(f"  word entries: {len(words)}  unique word_id: {len(lex_ids)}")

    cd, chars_rel = load_characters_1200()
    if not cd:
        print("MISSING: characters_1200.json (tried repo root and data/)", file=sys.stderr)
        return 1
    char_list = cd.get("characters", [])
    by_hanzi: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for c in char_list:
        hid = c.get("id")
        hz = (c.get("hanzi") or "").strip()
        if hz:
            by_hanzi[hz] = c
        if hid:
            by_id[hid] = c
    print()
    print(f"=== characters_1200.json ({chars_rel}) ===")
    print(f"  character records: {len(char_list)}")
    print(f"  unique hanzi indexed: {len(by_hanzi)}")

    ld = load_json("word_character_links.json")
    links = (ld or {}).get("links", [])
    linked_wids = {L["word_id"] for L in links if L.get("word_id")}
    print()
    print("=== word_character_links.json ===")
    print(f"  linked words: {len(linked_wids)}")

    missing_link = sorted(lex_ids - linked_wids)
    print(f"  lexicon words WITHOUT link entry: {len(missing_link)}")
    if missing_link:
        for wid in missing_link[:50]:
            hz = next((h for w, h in words if w == wid), "")
            print(f"    - {wid}  {hz}")
        if len(missing_link) > 50:
            print(f"    ... and {len(missing_link) - 50} more")

    extra_links = sorted(linked_wids - lex_ids)
    print(f"  link entries NOT in p1+p2 lexicon: {len(extra_links)}")
    if extra_links[:20]:
        print(f"    sample: {extra_links[:20]}")

    missing_chars_by_word = []
    all_missing_graphemes: set[str] = set()
    for wid, hz in words:
        g = graphemes_cjk(hz)
        miss = [x for x in g if x not in by_hanzi]
        if miss:
            missing_chars_by_word.append((wid, hz, miss))
            all_missing_graphemes.update(miss)

    print()
    print("=== CJK GRAPHEMES not in characters_1200 (by hanzi) ===")
    print(f"  affected words: {len(missing_chars_by_word)}")
    print(f"  distinct missing graphemes: {len(all_missing_graphemes)}")
    if all_missing_graphemes:
        s = "".join(sorted(all_missing_graphemes))
        if len(s) <= 80:
            print(f"  graphemes: {s}")
        else:
            print(f"  sample: {s[:80]}...")

    bad_cid = []
    missing_hanzi_in_link = []
    for L in links:
        wid = L.get("word_id")
        for ch in L.get("characters") or []:
            cid = ch.get("character_id")
            h = (ch.get("hanzi") or "").strip()
            if cid and cid not in by_id:
                bad_cid.append((wid, cid, h))
            if h and h not in by_hanzi:
                missing_hanzi_in_link.append((wid, h, cid))

    print()
    print("=== word_character_links: character_id missing in corpus ===")
    print(f"  rows: {len(bad_cid)}")
    for row in bad_cid[:25]:
        print(f"    {row}")

    print()
    print("=== word_character_links: hanzi field not in corpus ===")
    print(f"  rows: {len(missing_hanzi_in_link)}")
    for row in missing_hanzi_in_link[:25]:
        print(f"    {row}")

    cards_path = ROOT / "tools/cards/out/cards_by_id.json"
    card_wids: set[str] = set()
    no_card: list[str] = []
    if cards_path.is_file():
        cards = json.loads(cards_path.read_text(encoding="utf-8"))
        card_wids = {k for k in cards if str(k).startswith("w_")}
        print()
        print("=== tools/cards/out/cards_by_id.json ===")
        print(f"  w_* cards: {len(card_wids)}")
        no_card = sorted(lex_ids - card_wids)
        print(f"  lexicon words without card: {len(no_card)}")
        for wid in no_card[:40]:
            hz = next((h for w, h in words if w == wid), "")
            print(f"    - {wid}  {hz}")
        if len(no_card) > 40:
            print(f"    ... and {len(no_card) - 40} more")
    else:
        print("\n(no cards_by_id.json)")

    # Runtime etymology file
    et_path = ROOT / "runtime/out_phase7/word_etymology.runtime.json"
    print()
    print("=== runtime/out_phase7/word_etymology.runtime.json ===")
    if et_path.is_file():
        et = json.loads(et_path.read_text(encoding="utf-8"))
        wmap = et.get("words") or {}
        print(f"  present: yes  word keys: {len(wmap)}")
        in_lex = sum(1 for w in lex_ids if w in wmap)
        print(f"  lexicon words covered: {in_lex} / {len(lex_ids)}")
        with_chars = sum(
            1
            for w in lex_ids
            if w in wmap and (wmap[w].get("characters") or [])
        )
        print(f"  lexicon words with non-empty characters[]: {with_chars}")
    else:
        print("  present: NO (run tools/build_runtime_artifacts.py)")

    print()
    print("=== SUMMARY (recommended actions) ===")
    if not et_path.is_file():
        print("  1. Build word_etymology.runtime.json: python tools/build_runtime_artifacts.py")
    if missing_link:
        print(f"  2. Add word_character_links for {len(missing_link)} lexicon words (or trim scope).")
    if all_missing_graphemes:
        print(f"  3. Add {len(all_missing_graphemes)} missing Hanzi to characters_1200.json (or fix word hanzi).")
    if bad_cid or missing_hanzi_in_link:
        print("  4. Fix link rows: character_id / hanzi must exist in characters_1200.json.")

    # Markdown report (UTF-8, safe for sharing)
    report_dir = ROOT / "docs" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "vocab_character_coverage_audit.md"
    lines = [
        "# Vocabulary ↔ character corpus audit",
        "",
        "Generated by `scripts/audit_vocab_character_coverage.py`.",
        "",
        "## Counts",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| p1+p2 unique `word_id` | {len(lex_ids)} |",
        f"| `characters_1200.json` records | {len(char_list)} |",
        f"| Words in `word_character_links.json` | {len(linked_wids)} |",
        f"| Lexicon words **without** link entry | {len(missing_link)} |",
        f"| Lexicon words with CJK grapheme **missing** from corpus | {len(missing_chars_by_word)} |",
        f"| Distinct missing graphemes | {len(all_missing_graphemes)} |",
        f"| Link rows with `character_id` not in corpus | {len(bad_cid)} |",
        "",
    ]
    if cards_path.is_file():
        lines.append(f"| `cards_by_id.json` w_* keys | {len(card_wids)} |")
        lines.append(f"| Lexicon words without card | {len(no_card)} |")
        lines.append("")
    lines.extend([
        "## Interpretation",
        "",
        "- **Etymology UI** reads `runtime/out_phase7/word_etymology.runtime.json`, built from `word_character_links.json` + `characters_1200.json`.",
        "- If `characters_1200.json` in this clone has only a **small sample**, the builder will drop most `character_id`s (see `build_report.missing_character_id_count` in the runtime file).",
        "- If your full corpus (~5k) lives **elsewhere**, copy/symlink it to **repo root `characters_1200.json`** (same schema), then re-run the builder and this audit.",
        "",
        "## Lexicon words missing from `word_character_links.json` (first 80)",
        "",
    ])
    for wid in missing_link[:80]:
        hz = next((h for w, h in words if w == wid), "")
        lines.append(f"- `{wid}` — {hz}")
    if len(missing_link) > 80:
        lines.append(f"- … and {len(missing_link) - 80} more")
    lines.extend(["", "## Distinct graphemes missing from corpus (sorted)", ""])
    if all_missing_graphemes:
        lines.append("```")
        lines.append("".join(sorted(all_missing_graphemes)))
        lines.append("```")
    else:
        lines.append("(none)")
    lines.extend(["", "## Next steps", "", "1. Ensure repo-root `characters_1200.json` is your **full** dataset.", "2. `python scripts/audit_vocab_character_coverage.py` again — missing graphemes should drop to ~0.", "3. Add `links[]` entries for words still missing (or generate from a script).", "4. `python tools/build_runtime_artifacts.py`", "5. Reload UI — `word_etymology.runtime.json` should list many words with non-empty `characters[]`.", ""])
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"Wrote {report_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
