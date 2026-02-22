import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

IN_FILE = ROOT / "word_character_links.json"
OUT_FILE = ROOT / "tools/cards/out/word_character_links_map.json"

def main():
    data = json.loads(IN_FILE.read_text(encoding="utf-8"))

    links = data.get("links", [])
    out = {}

    for item in links:
        word_id = item.get("word_id")
        chars = item.get("characters", [])
        if not word_id:
            continue
        char_ids = []
        for c in chars:
            cid = c.get("character_id")
            if cid:
                char_ids.append(cid)
        if char_ids:
            out[word_id] = char_ids

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Wrote:", OUT_FILE)
    print("word_ids_written:", len(out))

if __name__ == "__main__":
    main()
