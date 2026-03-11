import json
from pathlib import Path

chars = json.loads(Path('characters_1200.json').read_text(encoding='utf-8'))
links = json.loads(Path('word_character_links.json').read_text(encoding='utf-8'))

# Show top-level keys
print('characters_1200 top-level keys:', list(chars.keys()))
print('word_character_links top-level keys:', list(links.keys()))
print()

# Show first character entry keys
first_char = chars['characters'][0]
print('character entry keys:', list(first_char.keys()))
print('sample id:', first_char.get('id'))
print()

# Show first link entry keys
first_link = links['links'][0]
print('link entry keys:', list(first_link.keys()))
print('sample word_id:', first_link.get('word_id'))
print('sample characters:', first_link.get('characters', [])[:2])
