import json

frames_p1 = json.load(open('p1_frames.json', encoding='utf-8')).get('frames', [])
frames_p2 = json.load(open('p2_frames.json', encoding='utf-8')).get('frames', [])
words_p1 = {w['id']: w['hanzi'] for w in json.load(open('p1_words.json', encoding='utf-8')).get('words', [])}
words_p2 = {w['id']: w['hanzi'] for w in json.load(open('p2_words.json', encoding='utf-8')).get('words', [])}
lookup = {**words_p1, **words_p2}

mismatches = []
for f in frames_p1 + frames_p2:
    toks = f.get('option_tokens', [])
    text = f.get('text', '')
    for t in toks:
        hz = lookup.get(t, '?')
        if hz not in text:
            mismatches.append(f"{f['id']}: token={t} hanzi={hz!r} not in '{text}'")

if mismatches:
    print(f"{len(mismatches)} mismatches found:")
    for m in mismatches:
        print(" ", m)
else:
    print("OK — all option_tokens align to frame text")