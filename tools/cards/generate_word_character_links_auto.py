import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OUT_FILE = ROOT / "tools/cards/out/word_character_links_auto.json"

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def get_words():
    # We already know your words files are in the repo root based on your earlier test.
    p1_path = ROOT / "p1_words.json"
    p2_path = ROOT / "p2_words.json"

    p1 = load_json(p1_path)
    p2 = load_json(p2_path)

    def extract(words_json):
        words = words_json.get("words") if isinstance(words_json, dict) else words_json
        out = []
        for w in words:
            if not isinstance(w, dict):
                continue
            wid = w.get("id") or w.get("word_id")
            hanzi = w.get("hanzi") or w.get("text") or w.get("word_hanzi")
            if wid and hanzi:
                out.append((wid, hanzi))
        return out

    return extract(p1) + extract(p2)

def get_char_map():
    # Try the most common locations. We stop at the first one that exists.
    candidates = [
        ROOT / "tools/cards/out/characters_from_words.json",
        ROOT / "tools/cards/characters_1200.json",
        ROOT / "tools/cards/data/characters_1200.json",
        ROOT / "characters_1200.json",
    ]

    for p in candidates:
        if p.exists():
            data = load_json(p)

            if isinstance(data, dict) and "characters" in data:
                chars = data["characters"]
            elif isinstance(data, list):
                chars = data
            else:
                continue

            m = {}
            for c in chars:
                if isinstance(c, dict):
                    cid = c.get("id") or c.get("character_id")
                    hanzi = c.get("hanzi") or c.get("char")
                    if cid and hanzi:
                        m[hanzi] = cid

            return m, p

    raise FileNotFoundError("Could not find a usable character list.")

def main():
    words = get_words()
    char_map, char_file = get_char_map()

    out = {}
    skipped_no_chars = 0
    skipped_unknown_char = 0

    for wid, hanzi in words:
        # Split variants like "他/她" into ["他", "她"]
        variants = [v.strip() for v in str(hanzi).split("/") if v.strip()]
        if not variants:
            continue

        best_char_ids = []
        best_unknown = False
        best_found_count = 0

        for variant in variants:
            char_ids = []
            unknown = False

            for ch in variant:
                # ignore common punctuation / separators
                if ch in [" ", "\t", "\n", "\r", "/", "·", "（", "）", "(", ")", "，", "。", "！", "？", "、", "“", "”", "‘", "’", "-", "—", "…", ":", "：", ",", ".", "!", "?"]:
                    continue

                cid = char_map.get(ch)
                if not cid:
                    unknown = True
                    continue
                char_ids.append(cid)

            found_count = len(char_ids)
            if found_count > best_found_count:
                best_found_count = found_count
                best_char_ids = char_ids
                best_unknown = unknown

        if not best_char_ids:
            skipped_no_chars += 1
            continue

        if best_unknown:
            skipped_unknown_char += 1

        out[wid] = best_char_ids

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Character file used:", str(char_file))
    print("Words seen:", len(words))
    print("Links written:", len(out))
    print("Skipped (no characters found):", skipped_no_chars)
    print("Words with some unknown chars (partial links):", skipped_unknown_char)
    print("Wrote:", str(OUT_FILE))

if __name__ == "__main__":
    main()
