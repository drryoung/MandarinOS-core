import json
from pathlib import Path

links = json.loads(Path('word_character_links.json').read_text(encoding='utf-8'))
chars = json.loads(Path('characters_1200.json').read_text(encoding='utf-8'))

char_by_id = { c['id']: c for c in chars['characters'] }

for link in links['links'][:3]:
    word_id = link['word_id']
    print('word_id:', word_id, ' hanzi:', link.get('word_hanzi','?'))
    for c in link.get('characters', []):
        cid = c['character_id']
        entry = char_by_id.get(cid, {})
        print('  char:', c.get('hanzi','?'))
        print('    etymology:', entry.get('etymology', ''))
        print('    mnemonic:', entry.get('mnemonic', ''))
    print()
