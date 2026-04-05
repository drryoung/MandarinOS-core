"""
One-shot audit of ui_server.py for conversation architecture violations.
Run: python scripts/_audit_violations.py
"""
import re, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

src = open("scripts/ui_server.py", encoding="utf-8").read()
lines = src.splitlines()
CJK = re.compile(r"[\u4e00-\u9fff]")

# ── AP-1: alternative preference lists (runtime list-switching based on context) ──
# Look for any list/tuple assignment whose name is NOT an established constant
AP1_RE = re.compile(r"prefs\s*=\s*list\(|prefs\s*=\s*\[")
hits_ap1 = [(i+1, l.strip()) for i, l in enumerate(lines) if AP1_RE.search(l)]

# ── AP-2: bypass of _frame_order_priority ──
AP2_RE = re.compile(r"skip.*frame.*order|bypass.*frame|frame.*bypass", re.I)
hits_ap2 = [(i+1, l.strip()) for i, l in enumerate(lines)
            if AP2_RE.search(l) and not l.strip().startswith("#")]

# ── AP-3: "guard" / "swap" / "override" functions on specific frame IDs ──
AP3_RE = re.compile(r"def\s+_swap_|def\s+_guard_|def\s+_override_|if.*chosen.*==.*[\"']f_")
hits_ap3 = [(i+1, l.strip()) for i, l in enumerate(lines) if AP3_RE.search(l)]

# ── AP-4: inline Chinese sentence strings in return/pool/assignment statements ──
# True violation = Chinese appears inside a string that is returned or pooled, not a constant/comment
POOL_RE = re.compile(r'^\s*(return|zh\s*=|en\s*=|zh_out\s*=|pool\s*=|pool\.append|\(\"|\(f\")')
hits_ap4 = []
for i, line in enumerate(lines):
    if not CJK.search(line): continue
    stripped = line.strip()
    if stripped.startswith("#"): continue
    if POOL_RE.match(line):
        hits_ap4.append((i+1, stripped[:110]))

# ── AP-5: frame-ID normalisation outside _normalize_frame_id ──
AP5_RE = re.compile(r'f_live_where|live_where|live_question.*f_|f_.*live_question')
hits_ap5 = [(i+1, l.strip()) for i, l in enumerate(lines)
            if AP5_RE.search(l) and "def _normalize" not in l and not l.strip().startswith("#")]

# ── Frame-ID hard-code in conditionals (selector independence violation) ──
HARD_RE = re.compile(r'(chosen|fid|frame_id)\s*(==|!=|in)\s*["\']f_|["\']p2_[^"\']+["\']')
# Only flag inside function bodies (not data structure definitions)
hits_hard = [(i+1, l.strip()) for i, l in enumerate(lines)
             if HARD_RE.search(l)
             and not l.strip().startswith("#")
             and not re.search(r"frozenset|^\s*['\"]|_FRAME_ORDER|_SLOT_FOLLOWUP|_MUTUAL|_WEAK|_BRIDGE|_OXYGEN|_PLACE|_IDENTITY|_CURIOSITY|_SUPPRESS|_ENERGY|_AFTER_ANY|_EFC", l)]

# Report
def section(title, hits, limit=20):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"  {len(hits)} hits")
    print(f"{'='*60}")
    for ln, txt in hits[:limit]:
        print(f"  L{ln:4d}: {txt}")
    if len(hits) > limit:
        print(f"  ... and {len(hits)-limit} more")

section("AP-1: runtime list-switching (prefs = list(...))", hits_ap1)
section("AP-2: frame_order bypass references", hits_ap2)
section("AP-3: swap/guard/override functions or chosen==frame_id checks", hits_ap3)
section("AP-4: inline Chinese sentence strings (return/pool)", hits_ap4)
section("AP-5: f_live_where normalisation outside _normalize_frame_id", hits_ap5)
section("Selector independence: frame-ID hard-code in conditionals", hits_hard, limit=30)
