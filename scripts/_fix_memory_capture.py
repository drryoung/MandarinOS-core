# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('scripts/learner_memory_capture.py', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 're.split' in line and 'maxsplit=1' in line and 40 < i < 60:
        # Lines 46-50 (indices 45-49): replace the block with turn-around strip + comma-aware split
        indent = '    '
        new_block = [
            indent + '# Strip trailing turn-around phrases before extracting (e.g. "我叫杨利明，你呢？" -> "我叫杨利明")\n',
            indent + 's = re.sub(r"[，,]?\\s*(那?你呢|你怎么想|为什么这么问)[？?！!。]?\\s*$", "", s).strip()\n',
            indent + '# Split on period OR Chinese comma so compound answers are trimmed correctly\n',
            indent + 'first = re.split(r"[。.,，]", s, maxsplit=1)[0].strip()\n',
        ]
        # Replace from 4 lines before this line (the comment block) through this line
        start = i - 4
        lines[start:i+1] = new_block
        print(f"Replaced lines {start+1}-{i+1} successfully")
        break
else:
    print("Target line not found")

with open('scripts/learner_memory_capture.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
