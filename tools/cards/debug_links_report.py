import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root

def load_json(rel_path: str):
    p = ROOT / rel_path
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def get_word_ids(words_json):
    # supports either {"words":[...]} or just [...]
    words = words_json.get("words") if isinstance(words_json, dict) else words_json
    out = []
    for w in words:
        # common patterns
        if isinstance(w, dict):
            if "id" in w:
                out.append(w["id"])
            elif "word_id" in w:
                out.append(w["word_id"])
    return out

def main():
    p1 = load_json("p1_words.json")
    p2 = load_json("p2_words.json")
    links = load_json("word_character_links.json")

    word_ids = set(get_word_ids(p1)) | set(get_word_ids(p2))

    # links can be either {"word_id": [...]} or {"links":[{"word_id":...}]} etc.
    link_keys = set()
    if isinstance(links, dict):
        if "links" in links and isinstance(links["links"], list):
            for item in links["links"]:
                if isinstance(item, dict) and "word_id" in item:
                    link_keys.add(item["word_id"])
        else:
            # treat top-level keys as word ids
            for k in links.keys():
                if isinstance(k, str):
                    link_keys.add(k)

    missing_links_for_words = sorted(word_ids - link_keys)
    extra_links_without_words = sorted(link_keys - word_ids)

    print("Report:")
    print("  words_total:", len(word_ids))
    print("  link_keys_total:", len(link_keys))
    print("  missing_links_for_words:", len(missing_links_for_words))
    print("  extra_links_without_words:", len(extra_links_without_words))

    print("\nFirst 25 word ids that have NO link entry:")
    for x in missing_links_for_words[:25]:
        print("  ", x)

    print("\nFirst 25 link keys that do NOT exist in p1/p2 words:")
    for x in extra_links_without_words[:25]:
        print("  ", x)

    # quick “pattern hints”
    def sample_pattern(items):
        s = items[:10]
        return s

    print("\nPattern hints (samples):")
    print("  missing sample:", sample_pattern(missing_links_for_words))
    print("  extra sample:", sample_pattern(extra_links_without_words))

if __name__ == "__main__":
    main()
