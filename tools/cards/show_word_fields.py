import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def load_json(name: str):
    p = ROOT / name
    return json.loads(p.read_text(encoding="utf-8"))

def main():
    p1 = load_json("p1_words.json")
    words = p1.get("words") if isinstance(p1, dict) else p1

    print("Total words in p1_words.json:", len(words))
    print("\nFirst 5 raw entries (exactly as stored):\n")

    for i, w in enumerate(words[:5], start=1):
        print("---- WORD", i, "----")
        print(json.dumps(w, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
