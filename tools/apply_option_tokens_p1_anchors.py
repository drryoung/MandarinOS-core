from __future__ import annotations
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
P1_FRAMES = REPO_ROOT / "p1_frames.json"
P1_WORDS = REPO_ROOT / "p1_words.json"

TARGET_FRAME_IDS = [
    "frame.identity.nationality",
    "frame.location.live",
    "f_have_siblings",
    "f_what_work",
    "f_i_am_job",
    "f_like_work",
    "f_what_hobby",
    "f_i_like_hobby",
    "f_travel_where",
    "f_been_to_place",
    "f_want_go_place",
]

# Preferred anchors (by hanzi). Script will resolve to real w_* ids from p1_words.json.
ANCHOR_BY_FRAME_ID = {
    "frame.identity.nationality": ["我"],
    "f_i_am_job": ["我"],
    "frame.location.live": ["住", "我"],
    "f_have_siblings": ["有"],
    "f_what_work": ["工作"],
    "f_like_work": ["喜欢"],
    "f_what_hobby": ["爱好"],
    "f_i_like_hobby": ["喜欢"],
    "f_travel_where": ["去过"],
    "f_been_to_place": ["去过"],
    "f_want_go_place": ["去过"],  # fallback anchor; "想" not in lexicon
}

def fail(msg: str) -> None:
    raise SystemExit(f"[apply_option_tokens_p1_anchors] ERROR: {msg}")

def extract_list(obj, keys=("frames", "items", "data")):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, list):
                return v
    fail("Unexpected JSON structure")

def load_words():
    data = json.loads(P1_WORDS.read_text(encoding="utf-8"))
    words = extract_list(data, keys=("words", "items", "data"))
    hanzi_to_id = {}
    for w in words:
        if not isinstance(w, dict):
            continue
        wid = w.get("id")
        hz = w.get("hanzi")
        if isinstance(wid, str) and wid.startswith("w_") and isinstance(hz, str) and hz:
            hanzi_to_id[hz] = wid
    return hanzi_to_id

def main() -> None:
    hanzi_to_id = load_words()

    data = json.loads(P1_FRAMES.read_text(encoding="utf-8"))
    frames = extract_list(data, keys=("frames", "items", "data"))

    if not isinstance(frames, list):
        fail("frames not a list")

    # index frames
    by_id = {}
    for fr in frames:
        if isinstance(fr, dict) and isinstance(fr.get("id"), str):
            by_id[fr["id"]] = fr

    missing_frames = [fid for fid in TARGET_FRAME_IDS if fid not in by_id]
    if missing_frames:
        fail(f"Target frames not found in p1_frames.json: {missing_frames}")

    changed = 0
    for fid in TARGET_FRAME_IDS:
        fr = by_id[fid]
        if "option_tokens" in fr:
            continue  # leave existing

        anchor_candidates = ANCHOR_BY_FRAME_ID.get(fid)
        if not anchor_candidates:
            fail(f"No anchor rule for frame_id={fid}")

        resolved = None
        for hz in anchor_candidates:
            wid = hanzi_to_id.get(hz)
            if wid:
                resolved = wid
                break

        if not resolved:
            fail(f"Could not resolve anchor for frame_id={fid}. Tried: {anchor_candidates}")

        fr["option_tokens"] = [resolved]
        changed += 1

    # Write back preserving top-level structure
    out_obj = data
    if isinstance(data, list):
        out_obj = frames
    elif isinstance(data, dict):
        # keep same container key if present
        if "frames" in data and isinstance(data["frames"], list):
            data["frames"] = frames
            out_obj = data
        elif "items" in data and isinstance(data["items"], list):
            data["items"] = frames
            out_obj = data
        elif "data" in data and isinstance(data["data"], list):
            data["data"] = frames
            out_obj = data
        else:
            # if dict but unknown keying, just overwrite with original object updated in-place
            out_obj = data

    P1_FRAMES.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("[apply_option_tokens_p1_anchors] OK")
    print(f"  frames_updated: {changed}")

if __name__ == "__main__":
    main()