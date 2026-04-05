"""Quick P2 HSK level audit. Run: python scripts/_p2_audit.py"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

p2 = json.load(open("p2_frames.json", encoding="utf-8"))["frames"]

# Vocabulary items that suggest HSK4+ complexity
HSK4_MARKERS = [
    "容易", "开心的事", "享受", "特色", "特点", "有趣", "不容易",
    "有没有", "所以", "因为.*所以", "让你", "尝试", "各种",
    "方面", "影响", "压力", "程度", "情况", "经历", "感受", "变化",
    "理想", "目标", "机会", "条件", "效果", "原因", "结果",
]

import re
print("=== ALL P2 FRAMES (difficulty / id / text) ===\n")
for f in p2:
    d = f.get("difficulty", "?")
    text = f["text"]
    fid = f["id"]
    # flag if any HSK4+ marker found
    flags = [m for m in HSK4_MARKERS if re.search(m, text)]
    flag_str = "  ⚠ HSK4+: " + ", ".join(flags) if flags else ""
    print(f"  d{d}  [{fid}]  {text}{flag_str}")

print()
print("=== P2 FRAMES FLAGGED AS LIKELY HSK4+ ===\n")
count = 0
for f in p2:
    text = f["text"]
    flags = [m for m in HSK4_MARKERS if re.search(m, text)]
    if flags:
        count += 1
        print(f"  d{f.get('difficulty','?')}  [{f['id']}]  {text}")
        print(f"      markers: {flags}")
print(f"\n{count} frames flagged")
