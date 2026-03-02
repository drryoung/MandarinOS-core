from __future__ import annotations
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
P1_FRAMES = REPO_ROOT / "p1_frames.json"

def extract_frames(obj):
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for k in ("frames", "items", "data"):
            v = obj.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    raise SystemExit("Unexpected p1_frames.json structure")

data = json.loads(P1_FRAMES.read_text(encoding="utf-8"))
frames = extract_frames(data)

missing = []
for fr in frames:
    fid = fr.get("id")
    txt = fr.get("text")
    if not isinstance(fid, str):
        continue
    if "option_tokens" in fr:
        continue
    # report only frames that look “real”
    if isinstance(txt, str) and txt.strip():
        missing.append((fid, txt))

print(f"[report_missing_option_tokens_p1] missing_count={len(missing)}")
for fid, txt in missing:
    print(f"- {fid} :: {txt}")