import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_FILE = ROOT / "tools/cards/out/word_character_links_auto_rich.json"

PUNCT = set([" ", "\t", "\n", "\r", "/", "·", "（", "）", "(", ")", "，", "。", "！", "？", "、", "“", "”", "‘", "’", "-", "—", "…", ":", "：", ",", ".", "!", "?"])

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def load_words():
    p1 = load_json(ROOT / "p1_words.json")
    p2 = load_json(ROOT / "p2_words.json")

    def extract(words_json):
        words = words_json.get("words") if isinstance(words_json, dict) else words_json
        out = []
        for w in words:
            if not isinstance(w, dict):
                continue
            wid = w.get("id") or w.get("word_id")
            hanzi = w.get("hanzi")
            if wid and hanzi:
                out.append((wid, str(hanzi)))
        return out

    return extract(p1) + extract(p2)

def load_char_map():
    # Use the characters we generated from words
    p = ROOT / "tools/cards/out/characters_from_words.json"
    data = load_json(p)
    # data is a list of {"id": "c_你", "hanzi": "你"}
    m = {}
    for c in data:
        if isinstance(c, dict) and c.get("hanzi") and c.get("id"):
            m[c["hanzi"]] = c["id"]
    return m, p

def main():
    words = load_words()
    char_map, char_file = load_char_map()

    out = {}
    for wid, hanzi in words:
        variants = [v.strip() for v in hanzi.split("/") if v.strip()]
        if not variants:
            continue

        # choose the variant that yields the most known characters
        best = None
        best_count = -1

        for variant in variants:
            chars = []
            for ch in variant:
                if ch in PUNCT:
                    continue
                cid = char_map.get(ch)
                if cid:
                    chars.append({"character_id": cid, "hanzi": ch, "role": None, "strength": None})
            if len(chars) > best_count:
                best = chars
                best_count = len(chars)

        if best and best_count > 0:
            out[wid] = {"characters": best}

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Character file used:", str(char_file))
    print("Words seen:", len(words))
    print("Links written:", len(out))
    print("Wrote:", str(OUT_FILE))

if __name__ == "__main__":
    main()
