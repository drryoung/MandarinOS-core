import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    p = ROOT / "characters_1200.json"
    data = load_json(p)

    # try common shapes
    chars = None
    if isinstance(data, dict) and "characters" in data:
        chars = data["characters"]
    elif isinstance(data, list):
        chars = data
    else:
        # if it's a dict with some other key, just show keys
        print("Top-level keys in characters_1200.json:", list(data.keys()) if isinstance(data, dict) else type(data))
        return

    print("Total character entries:", len(chars))
    print("\nFirst 5 raw entries (exactly as stored):\n")
    for i, c in enumerate(chars[:5], start=1):
        print("---- CHAR", i, "----")
        print(json.dumps(c, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
