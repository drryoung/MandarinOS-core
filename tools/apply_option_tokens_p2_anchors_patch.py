from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

P2_FRAMES = REPO_ROOT / "p2_frames.json"
P2_WORDS = REPO_ROOT / "p2_words.json"
OUT_PATCH = REPO_ROOT / "tools" / "out" / "p2_option_tokens_anchors.patch"

# The 40 frame ids you pasted (authoritative list for this batch)
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
TEXT_RE = re.compile(r'"text"\s*:\s*"([^"]*)"')
ID_RE = re.compile(r'"id"\s*:\s*"([^"]+)"')

def fail(msg: str) -> None:
    raise SystemExit(f"[apply_option_tokens_p2_anchors_patch] ERROR: {msg}")

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        fail(f"Failed to read JSON: {path} ({e})")

def extract_list(obj, keys=("words", "frames", "items", "data")) -> List[dict]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    fail("Unexpected JSON structure (expected list or dict containing a list).")

def load_hanzi_to_id() -> Dict[str, str]:
    data = read_json(P2_WORDS)
    words = extract_list(data, keys=("words", "items", "data"))
    out: Dict[str, str] = {}
    for w in words:
        wid = w.get("id")
        hz = w.get("hanzi")
        if isinstance(wid, str) and wid.startswith("w_") and isinstance(hz, str) and hz:
            out[hz] = wid
    if not out:
        fail("No words loaded from p2_words.json.")
    return out

def choose_anchor_word_id(frame_text: str, hanzi_to_id: Dict[str, str]) -> Optional[str]:
    # Remove {SLOT} placeholders and punctuation-ish whitespace
    cleaned = SLOT_RE.sub("", frame_text)
    cleaned = cleaned.replace("。", "").replace("？", "").replace("！", "").replace("，", "").replace(" ", "").strip()
    if not cleaned:
        return None

    # Longest-unique substring match against hanzi entries
    hits: List[Tuple[int, str]] = []
    for hz, wid in hanzi_to_id.items():
        if hz and hz in cleaned:
            hits.append((len(hz), wid))

    if hits:
        hits.sort(key=lambda x: (-x[0], x[1]))  # longest first, then wid
        best_len = hits[0][0]
        best = [wid for L, wid in hits if L == best_len]
        if len(best) == 1:
            return best[0]  # unique longest
        # ambiguous tie -> fall through to fallback

    # Conservative fallback words (only if present)
    fallback_hanzi = ["觉得", "喜欢", "名字", "家人", "工作", "计划", "我们", "哪里", "地方", "开始", "为什么", "问题", "解决", "昨天", "后来", "一起", "见面", "住", "去过", "我", "你"]
    for hz in fallback_hanzi:
        wid = hanzi_to_id.get(hz)
        if wid:
            return wid
    return None

def find_frame_blocks(lines: List[str]) -> List[Tuple[int, int]]:
    # crude block detection: '{' ... line containing '}'
    blocks: List[Tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("{"):
            start = i
            j = i + 1
            while j < len(lines) and "}" not in lines[j]:
                j += 1
            if j < len(lines):
                blocks.append((start, j))
                i = j + 1
            else:
                i += 1
        else:
            i += 1
    return blocks

def block_get_id_text(block_lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
    fid = None
    txt = None
    for ln in block_lines:
        if fid is None:
            m = ID_RE.search(ln)
            if m:
                fid = m.group(1)
        if txt is None and '"text"' in ln:
            m = TEXT_RE.search(ln)
            if m:
                txt = m.group(1)
        if fid and txt is not None:
            break
    return fid, txt

def block_has_option_tokens(block_lines: List[str]) -> bool:
    return any('"option_tokens"' in ln for ln in block_lines)

def find_insert_line_index(block_lines: List[str]) -> Optional[int]:
    """
    Prefer inserting after 'speaker' if present, else after 'slots'.
    This keeps diffs minimal and avoids assuming speaker exists.
    """
    for i, ln in enumerate(block_lines):
        if '"speaker"' in ln:
            return i
    for i, ln in enumerate(block_lines):
        if '"slots"' in ln:
            return i
    return None

def patch_block(block_lines: List[str], wid: str) -> Tuple[List[str], List[str]]:
    # Insert option_tokens immediately after a stable line, preserving indent
    idx = find_insert_line_index(block_lines)
    if idx is None:
        fail("Frame block missing both 'speaker' and 'slots' line; cannot insert option_tokens safely.")

    new_lines = block_lines[:]
    base = new_lines[idx].rstrip("\n")
    indent = re.match(r"^(\s*)", base).group(1)

    # Ensure the insertion anchor line ends with comma
    if not base.rstrip().endswith(","):
        new_lines[idx] = base + ",\n"

    new_lines.insert(idx + 1, f'{indent}"option_tokens": ["{wid}"]\n')
    return (block_lines, new_lines)

def main() -> None:
    if not P2_FRAMES.exists():
        fail(f"Missing {P2_FRAMES}")
    if not P2_WORDS.exists():
        fail(f"Missing {P2_WORDS}")

    hanzi_to_id = load_hanzi_to_id()
    original_lines = P2_FRAMES.read_text(encoding="utf-8").splitlines(keepends=True)
    blocks = find_frame_blocks(original_lines)

    # Build patches only for target frame ids that are missing option_tokens
    edits: List[Tuple[str, str]] = []  # (frame_id, chosen_word_id)
    patches: List[Tuple[List[str], List[str]]] = []

    target_set = set(TARGET_FRAME_IDS)

    # First pass: locate target blocks
    found_targets = set()
    for start, end in blocks:
        block_lines = original_lines[start : end + 1]
        fid, txt = block_get_id_text(block_lines)
        if not fid or fid not in target_set:
            continue
        found_targets.add(fid)

        if block_has_option_tokens(block_lines):
            continue  # already done

        if txt is None:
            fail(f"Frame {fid}: missing text")

        wid = choose_anchor_word_id(txt, hanzi_to_id)
        if not wid:
            fail(f"Frame {fid}: could not resolve an anchor word_id from p2_words.json for text: {txt}")

        old_block, new_block = patch_block(block_lines, wid)
        patches.append((old_block, new_block))
        edits.append((fid, wid))

    missing_targets = sorted(target_set - found_targets)
    if missing_targets:
        fail(f"Some target frame ids were not found in p2_frames.json: {missing_targets}")

    if not patches:
        fail("No patches to apply (all targets may already have option_tokens).")

    # Apply textual replacements (first occurrence only) to preserve formatting
    original_text = "".join(original_lines)
    edited_text = original_text
    for old_block, new_block in patches:
        old_s = "".join(old_block)
        new_s = "".join(new_block)
        if old_s in edited_text:
            edited_text = edited_text.replace(old_s, new_s, 1)
        else:
            fail("Internal error: could not locate block text for replacement.")

    # Write unified diff patch
    import difflib
    OUT_PATCH.parent.mkdir(parents=True, exist_ok=True)
    diff = difflib.unified_diff(
        original_text.splitlines(keepends=True),
        edited_text.splitlines(keepends=True),
        fromfile="a/p2_frames.json",
        tofile="b/p2_frames.json",
        n=3,
    )
    OUT_PATCH.write_text("".join(diff), encoding="utf-8")

    print("[apply_option_tokens_p2_anchors_patch] OK")
    print(f"  patch_file: {OUT_PATCH}")
    print(f"  frames_patched: {len(edits)}")
    print("  sample (first 15):")
    for fid, wid in edits[:15]:
        print(f"    {fid} -> {wid}")

if __name__ == "__main__":
    main()