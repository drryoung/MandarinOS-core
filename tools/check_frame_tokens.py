#!/usr/bin/env python3
"""Check which frames are missing runtime token arrays (fall back to plain unclickable text)."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RT = REPO / "runtime" / "out_phase7" / "frame_render_tokens.runtime.json"

if not RT.exists():
    print("frame_render_tokens.runtime.json NOT FOUND at", RT)
    raise SystemExit(1)

data = json.loads(RT.read_text(encoding="utf-8"))
frames_list = data.get("frames", [])
rt_ids = {f["frame_id"] for f in frames_list if isinstance(f, dict)}

all_frames = []
for fname in ["p1_frames.json", "p2_frames.json"]:
    fdata = json.loads((REPO / fname).read_text(encoding="utf-8"))
    frames = fdata if isinstance(fdata, list) else fdata.get("frames", fdata)
    for f in frames:
        if isinstance(f, dict) and f.get("id"):
            all_frames.append(f)

missing = [f for f in all_frames if f["id"] not in rt_ids]
present = [f for f in all_frames if f["id"] in rt_ids]

print(f"Runtime token coverage: {len(present)}/{len(all_frames)} frames")
if missing:
    print(f"\nMISSING from runtime ({len(missing)} frames — fall back to plain text):")
    for f in missing:
        text = f.get('text', '').encode('ascii', 'replace').decode()
        print(f"  {f['id']:35s}  {text}")
else:
    print("\nAll frames have runtime token arrays.")
