from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
P2_FRAMES = REPO_ROOT / "p2_frames.json"
P2_WORDS = REPO_ROOT / "p2_words.json"

TARGET_FRAME_IDS = [
    "p2_id_1","p2_id_2","p2_id_3","p2_id_4","p2_id_5",
    "p2_pl_1","p2_pl_2","p2_pl_3","p2_pl_4","p2_pl_5",
    "p2_fa_1","p2_fa_2","p2_fa_3","p2_fa_4","p2_fa_5",
    "p2_wk_1","p2_wk_2","p2_wk_3","p2_wk_4","p2_wk_5",
    "p2_hb_1","p2_hb_2","p2_hb_3","p2_hb_4","p2_hb_5",
    "p2_tr_1","p2_tr_2","p2_tr_3","p2_tr_4","p2_tr_5",
    "p2_pln_1","p2_pln_2","p2_pln_3","p2_pln_4","p2_pln_5",
    "p2_op_1","p2_op_3","p2_op_4",
    "p2_st_1","p2_st_2",
]

SLOT_RE = re.compile(r"\{[^}]+\}")

FALLBACK_HANZI = [
    "觉得","喜欢","名字","家人","工作","计划","我们","哪里","地方","开始","为什么",
    "问题","解决","昨天","后来","一起","见面","住","去过","我","你"
]

def fail(msg: str) -> None:
    raise SystemExit(f"[apply_option_tokens_p2_anchors_json] ERROR: {msg}")

def extract_list(obj, keys=("words","frames","items","data")) -> List[dict]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    fail("Unexpected JSON structure (expected list or dict containing a list).")

def load_hanzi_to_id(words_path: Path) -> Dict[str,str]:
    data = json.loads(words_path.read_text(encoding="utf-8"))
    words = extract_list(data, keys=("words","items","data"))
    out: Dict[str,str] = {}
    for w in words:
        wid = w.get("id")
        hz = w.get("hanzi")
        if isinstance(wid,str) and wid.startswith("w_") and isinstance(hz,str) and hz:
            out[hz] = wid
    if not out:
        fail("No words loaded from p2_words.json.")
    return out

def choose_anchor(text: str, hanzi_to_id: Dict[str,str]) -> Optional[str]:
    cleaned = SLOT_RE.sub("", text)
    cleaned = cleaned.replace("。","").replace("？","").replace("！","").replace("，","").replace(" ","").strip()
    if not cleaned:
        return None

    hits: List[Tuple[int,str]] = []
    for hz, wid in hanzi_to_id.items():
        if hz and hz in cleaned:
            hits.append((len(hz), wid))

    if hits:
        hits.sort(key=lambda x: (-x[0], x[1]))
        best_len = hits[0][0]
        best = [wid for L,wid in hits if L == best_len]
        if len(best) == 1:
            return best[0]

    for hz in FALLBACK_HANZI:
        wid = hanzi_to_id.get(hz)
        if wid:
            return wid
    return None

def main() -> None:
    if not P2_FRAMES.exists():
        fail(f"Missing {P2_FRAMES}")
    if not P2_WORDS.exists():
        fail(f"Missing {P2_WORDS}")

    hanzi_to_id = load_hanzi_to_id(P2_WORDS)

    data = json.loads(P2_FRAMES.read_text(encoding="utf-8"))
    frames = extract_list(data, keys=("frames","items","data"))

    by_id = {}
    for fr in frames:
        fid = fr.get("id")
        if isinstance(fid, str):
            by_id[fid] = fr

    target_set = set(TARGET_FRAME_IDS)
    missing = sorted(target_set - set(by_id.keys()))
    if missing:
        fail(f"Target frame ids not found in p2_frames.json: {missing}")

    changed = 0
    edits: List[Tuple[str,str]] = []
    for fid in TARGET_FRAME_IDS:
        fr = by_id[fid]
        if "option_tokens" in fr:
            continue
        txt = fr.get("text")
        if not isinstance(txt, str) or not txt.strip():
            fail(f"Frame {fid}: missing/empty text")
        wid = choose_anchor(txt, hanzi_to_id)
        if not wid:
            fail(f"Frame {fid}: could not choose anchor for text: {txt}")
        fr["option_tokens"] = [wid]
        changed += 1
        edits.append((fid, wid))

    # write back, preserving container key
    out_obj = data
    if isinstance(data, list):
        out_obj = frames
    elif isinstance(data, dict):
        if "frames" in data and isinstance(data["frames"], list):
            data["frames"] = frames
        elif "items" in data and isinstance(data["items"], list):
            data["items"] = frames
        elif "data" in data and isinstance(data["data"], list):
            data["data"] = frames

    P2_FRAMES.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("[apply_option_tokens_p2_anchors_json] OK")
    print(f"  frames_updated: {changed}")
    print("  sample (first 15):")
    for fid, wid in edits[:15]:
        print(f"    {fid} -> {wid}")

if __name__ == "__main__":
    main()