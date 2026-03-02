import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
P2_FRAMES = REPO_ROOT / "p2_frames.json"
P2_WORDS  = REPO_ROOT / "p2_words.json"
P1_WORDS  = REPO_ROOT / "p1_words.json"

# Load lexicons
p1 = {w["id"]: w["hanzi"] for w in json.loads(P1_WORDS.read_text(encoding="utf-8")).get("words", [])}
p2 = {w["id"]: w["hanzi"] for w in json.loads(P2_WORDS.read_text(encoding="utf-8")).get("words", [])}
lookup = {**p1, **p2}
# reverse: hanzi -> word_id (first match wins, longest hanzi preferred for ties)
reverse = {}
for wid, hz in sorted(lookup.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    if hz not in reverse:
        reverse[hz] = wid

# Explicit overrides: frame_id -> correct option_tokens
# Chosen by picking the most meaningful word present in frame.text
OVERRIDES = {
    "p2_id_3":  ["w_bijiao"],       # 我平时比较{STYLE}。
    "p2_id_5":  ["w_yiyi"],         # 这个名字对你有什么意义？  → 意义
    "p2_pl_2":  ["w_haochi"],       # {CITY}有什么好吃的？
    "p2_pl_3":  ["w_xihuan"],       # 你平时喜欢去{PLACE}吗？
    "p2_pl_4":  ["w_fangbian"],     # 住在{CITY}方便吗？
    "p2_fa_2":  ["w_duojiu"],       # 你多久见一次家人？
    "p2_fa_3":  ["w_guanxi"],       # 我跟{FAMILY_ROLE}关系很好。
    "p2_fa_5":  ["w_yiqi"],         # 周末一般跟家人一起做什么？
    "p2_wk_1":  ["w_xiaban"],       # 你每天几点下班？
    "p2_wk_2":  ["w_zuijin"],       # 你最近工作忙不忙？
    "p2_wk_3":  ["w_zuijin"],       # 我最近工作有点{REASON_NEG}。 → 最近
    "p2_wk_4":  ["w_anpai"],        # 你一般怎么安排一天的工作？
    "p2_wk_5":  ["w_jiejue"],       # 遇到问题你会怎么解决？
    "p2_hb_5":  ["w_zuida"],        # 你最大的成就是什么？
    "p2_tr_1":  ["w_quguo"],        # 你去过哪些国家？
    "p2_tr_3":  ["w_haowan"],       # 那个地方有什么好玩的？
    "p2_pln_1": ["w_jihua"],        # 你{TIME}有什么计划？
    "p2_pln_5": ["w_jian"],         # 那我们{TIME}见。
    "p2_op_4":  ["w_suoyi"],        # 因为{REASON_POS}，所以我很喜欢。
}

# Verify each override anchor is actually in the frame text
pack = json.loads(P2_FRAMES.read_text(encoding="utf-8"))
frames = pack.get("frames", [])
errors = []
fixed  = 0

for frame in frames:
    fid = frame.get("id")
    if fid not in OVERRIDES:
        continue
    new_tokens = OVERRIDES[fid]
    text = frame.get("text", "")
    for tok in new_tokens:
        hz = lookup.get(tok)
        if hz is None:
            errors.append(f"  {fid}: word_id '{tok}' not in any lexicon")
        elif hz not in text:
            errors.append(f"  {fid}: token={tok} hanzi={hz!r} still not in '{text}'")
    if not errors:
        frame["option_tokens"] = new_tokens
        fixed += 1

if errors:
    print(f"ERRORS — fix these before writing:")
    for e in errors:
        print(e)
else:
    P2_FRAMES.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK — fixed {fixed} frames in p2_frames.json")

console.log(document.getElementById('frameSentence').innerHTML)