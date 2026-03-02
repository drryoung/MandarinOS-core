from __future__ import annotations
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
P2_FRAMES = REPO_ROOT / "p2_frames.json"

def extract_frames(obj):
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for k in ("frames", "items", "data"):
            v = obj.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    raise SystemExit("Unexpected p2_frames.json structure")

data = json.loads(P2_FRAMES.read_text(encoding="utf-8"))
frames = extract_frames(data)

missing = []
for fr in frames:
    fid = fr.get("id")
    txt = fr.get("text")
    if not isinstance(fid, str):
        continue
    if "option_tokens" in fr:
        continue
    if isinstance(txt, str) and txt.strip():
        missing.append((fid, txt))

print(f"[report_missing_option_tokens_p2] missing_count={len(missing)}")
for fid, txt in missing:
    print(f"- {fid} :: {txt}")