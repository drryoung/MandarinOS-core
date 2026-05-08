"""
Validate content/response_patterns.json against the MandarinOS Response Option Style Guide.

Logs warnings only — does not block builds or raise errors.
Run: python scripts/validate_response_options.py

Rules checked:
  L  - Chinese character count > 10
  BV - Banned vocabulary word present
  BP - Banned grammatical pattern (regex)
  MC - Multi-clause: ideographic comma, or clause-linking conjunction
"""

import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
PATTERNS_FILE = REPO_ROOT / "content" / "response_patterns.json"

MAX_HANZI = 10

# Vocabulary that signals formal/abstract register — never appropriate in learner options.
BANNED_VOCAB: list[str] = [
    "成就感",  # abstract: "sense of achievement"
    "通勤",    # formal: "commute" → 去上班
    "游览",    # formal: "tour/sightsee" → 到处玩/走走
    "代表",    # abstract: "represents/symbolises"
    "方向",    # abstract: "direction" (career sense)
    "外资",    # jargon: "foreign capital" → 外国公司
    "稍后",    # formal: "shortly" → 以后/之后
    "妻子",    # formal: "wife" → 老婆
    "父母",    # formal: "parents" → 爸爸妈妈
    "非常",    # formal: "very" → 很
]

# Regex patterns that violate style regardless of individual words.
BANNED_PATTERNS: list[tuple[str, str]] = [
    (r"对.{1,6}来说",  "对…来说 (formal framing)"),
    (r"越.{1,6}越",    "越…越 (fine in isolation but often overwrites simple answers)"),
    (r"我很推荐",       "我很推荐 (unnatural — prefer 你也试试 or 值得去)"),
]

# Signals that a second clause has been joined onto the first.
# A single ideographic comma is the primary signal.
# Clause-linking conjunctions are secondary (they always introduce a new clause).
CLAUSE_CONJUNCTIONS: list[str] = [
    "但是", "不过", "所以", "因此", "然后", "而且", "并且",
]

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def count_hanzi(s: str) -> int:
    """Return number of CJK characters (punctuation and ASCII excluded)."""
    return sum(1 for c in s if "\u4e00" <= c <= "\u9fff")


def check_option(zh: str, key: str, idx: int) -> list[str]:
    warnings: list[str] = []
    label = f"[{key}] opt {idx + 1}"

    # L — length
    n = count_hanzi(zh)
    if n > MAX_HANZI:
        warnings.append(f"{label}  L   {n} chars (>{MAX_HANZI}): {zh}")

    # BV — banned vocabulary
    for word in BANNED_VOCAB:
        if word in zh:
            warnings.append(f"{label}  BV  '{word}' in: {zh}")

    # BP — banned patterns
    for pattern, desc in BANNED_PATTERNS:
        if re.search(pattern, zh):
            warnings.append(f"{label}  BP  {desc}: {zh}")

    # MC — multi-clause
    # Flag ideographic comma (，) OR a clause-linking conjunction.
    # Slash enumeration (、) is explicitly excluded — that is a list, not clause joining.
    has_comma = "，" in zh
    has_conjunction = any(c in zh for c in CLAUSE_CONJUNCTIONS)
    if has_comma or has_conjunction:
        signal = "，" if has_comma else next(c for c in CLAUSE_CONJUNCTIONS if c in zh)
        warnings.append(f"{label}  MC  '{signal}' in: {zh}")

    return warnings


def main() -> int:
    if not PATTERNS_FILE.exists():
        print(f"ERROR: {PATTERNS_FILE} not found.")
        return 1

    data = json.loads(PATTERNS_FILE.read_text(encoding="utf-8"))
    patterns = data.get("patterns", [])
    fallbacks = data.get("generic_fallback", [])

    all_warnings: list[str] = []

    for block in patterns:
        key = block.get("key", "?")
        for i, opt in enumerate(block.get("options", [])):
            zh = opt.get("zh", "")
            all_warnings.extend(check_option(zh, key, i))

    for i, opt in enumerate(fallbacks):
        zh = opt.get("zh", "")
        all_warnings.extend(check_option(zh, "generic_fallback", i))

    total = len(all_warnings)
    by_rule: dict[str, int] = {"L": 0, "BV": 0, "BP": 0, "MC": 0}
    for w in all_warnings:
        for rule in by_rule:
            if f"  {rule}  " in w:
                by_rule[rule] += 1
                break

    if total == 0:
        print("OK  No style violations found in response_patterns.json.")
        return 0

    print(f"WARN  {total} violation(s) in response_patterns.json\n")
    print(f"      L={by_rule['L']}  BV={by_rule['BV']}  BP={by_rule['BP']}  MC={by_rule['MC']}\n")

    current_key = None
    for w in all_warnings:
        key_part = w.split("]")[0].lstrip("[")
        if key_part != current_key:
            current_key = key_part
            print(f"  ── {current_key}")
        print(f"    {w.split('] ', 1)[-1]}")

    print()
    return 0  # warnings only — never a build-blocking exit code


if __name__ == "__main__":
    sys.exit(main())
