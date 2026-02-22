import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_FILE = ROOT / "tools/cards/out/characters_from_words.json"

PUNCT = set([" ", "\t", "\n", "\r", "/", "·", "（", "）", "(", ")", "，", "。", "！", "？", "、", "“", "”", "‘", "’", "-", "—", "…", ":", "：", ",", ".", "!", "?"])

def load_json(name: str):
    p = ROOT / name
    return json.loads(p.read_text(encoding="utf-8"))

def extract_words(words_json):
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

def main():
    p1 = load_json("p1_words.json")
    p2 = load_json("p2_words.json")
    words = extract_words(p1) + extract_words(p2)

    chars = {}
    for _, hanzi in words:
        for variant in [v.strip() for v in hanzi.split("/") if v.strip()]:
            for ch in variant:
                if ch in PUNCT:
                    continue
                if ch:
                    chars[ch] = f"c_{ch}"

    out_list = [{"id": cid, "hanzi": hanzi} for hanzi, cid in sorted(chars.items(), key=lambda x: x[0])]

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(out_list, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Words seen:", len(words))
    print("Unique characters found:", len(out_list))
    print("Wrote:", str(OUT_FILE))

if __name__ == "__main__":
    main()
