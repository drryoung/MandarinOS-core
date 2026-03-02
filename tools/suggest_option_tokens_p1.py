# tools/suggest_option_tokens_p1.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

P1_FRAMES = REPO_ROOT / "p1_frames.json"
P1_WORDS = REPO_ROOT / "p1_words.json"
OUT_PATCH = REPO_ROOT / "tools" / "out" / "p1_option_tokens.patch"

PUNCT_RE = re.compile(r"[。．\.，,！!？\?\s]+")
TEXT_HAS_BRACES_RE = re.compile(r"[{}]")

def _fail(msg: str) -> None:
    raise SystemExit(f"[suggest_option_tokens_p1] ERROR: {msg}")

def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        _fail(f"Failed to read JSON: {path} ({e})")

def _extract_list(pack_obj, keys=("words", "frames", "items", "data")) -> List[dict]:
    if isinstance(pack_obj, list):
        return [x for x in pack_obj if isinstance(x, dict)]
    if isinstance(pack_obj, dict):
        for k in keys:
            v = pack_obj.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    _fail("Unexpected JSON structure (expected list or dict containing a list).")

def _load_word_hanzi_map(words_path: Path) -> Dict[str, str]:
    data = _read_json(words_path)
    words = _extract_list(data, keys=("words", "items", "data"))
    out: Dict[str, str] = {}
    for w in words:
        wid = w.get("id")
        hz = w.get("hanzi")
        if isinstance(wid, str) and wid.startswith("w_") and isinstance(hz, str) and hz:
            out[wid] = hz
    if not out:
        _fail("No words loaded from p1_words.json (word_hanzi_map is empty).")
    return out

def _normalize_text(s: str) -> str:
    # remove common punctuation + whitespace
    return PUNCT_RE.sub("", s).strip()

def _choose_token(frame_text: str, word_hanzi_map: Dict[str, str]) -> Optional[str]:
    """
    Deterministic & conservative:
      1) exact match after normalization
      2) else longest-substring match; if tie on length, skip (ambiguous)
    """
    t = _normalize_text(frame_text)
    if not t:
        return None

    # 1) exact match
    exact = [wid for wid, hz in word_hanzi_map.items() if _normalize_text(hz) == t]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None  # ambiguous exact

    # 2) longest substring match
    hits: List[Tuple[int, str]] = []
    for wid, hz in word_hanzi_map.items():
        h = _normalize_text(hz)
        if not h:
            continue
        if h in t:
            hits.append((len(h), wid))

    if not hits:
        return None

    hits.sort(key=lambda x: (-x[0], x[1]))  # longest first, then wid
    best_len = hits[0][0]
    best = [wid for L, wid in hits if L == best_len]
    if len(best) != 1:
        return None  # tie => ambiguous
    return best[0]

def _eligible_simple_frame_block(block_lines: List[str]) -> bool:
    # Must contain: "slots": []
    if not any('"slots"' in ln and "[]" in ln for ln in block_lines):
        return False
    # Must NOT already contain option_tokens
    if any('"option_tokens"' in ln for ln in block_lines):
        return False
    # Must have text and it must not contain { or }
    text_line = next((ln for ln in block_lines if '"text"' in ln), None)
    if not text_line:
        return False
    m = re.search(r'"text"\s*:\s*"([^"]*)"', text_line)
    if not m:
        return False
    txt = m.group(1)
    if TEXT_HAS_BRACES_RE.search(txt):
        return False
    return True

def _get_id_and_text(block_lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
    fid = None
    txt = None
    for ln in block_lines:
        if fid is None:
            m = re.search(r'"id"\s*:\s*"([^"]+)"', ln)
            if m:
                fid = m.group(1)
        if txt is None and '"text"' in ln:
            m = re.search(r'"text"\s*:\s*"([^"]*)"', ln)
            if m:
                txt = m.group(1)
        if fid and txt:
            break
    return fid, txt

def _find_speaker_line_index(block_lines: List[str]) -> Optional[int]:
    for i, ln in enumerate(block_lines):
        if '"speaker"' in ln:
            return i
    return None

def _make_block_patch(block_lines: List[str], wid: str) -> Optional[Tuple[List[str], List[str]]]:
    """
    Returns (old_block_lines, new_block_lines) for a minimal, safe change:
    - add option_tokens after speaker line
    - ensure speaker line ends with a comma
    """
    speaker_i = _find_speaker_line_index(block_lines)
    if speaker_i is None:
        return None

    new_lines = block_lines[:]
    sp = new_lines[speaker_i].rstrip("\n")

    # Determine indentation from speaker line
    indent = re.match(r"^(\s*)", sp).group(1)

    # Ensure speaker line ends with comma
    if not sp.rstrip().endswith(","):
        sp = sp + ","
        new_lines[speaker_i] = sp + "\n"

    # Insert option_tokens line immediately after speaker line
    option_line = f'{indent}"option_tokens": ["{wid}"]\n'
    new_lines.insert(speaker_i + 1, option_line)

    return (block_lines, new_lines)

def main() -> None:
    if not P1_FRAMES.exists():
        _fail(f"Missing {P1_FRAMES}")
    if not P1_WORDS.exists():
        _fail(f"Missing {P1_WORDS}")

    word_hanzi_map = _load_word_hanzi_map(P1_WORDS)

    # Work on raw text to preserve formatting / minimal diff
    lines = P1_FRAMES.read_text(encoding="utf-8").splitlines(keepends=True)

    # Find frame blocks naively by scanning for '{' ... '},'
    # Conservative: only patch blocks that match our eligibility rules.
    blocks: List[Tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("{"):
            start = i
            j = i + 1
            while j < len(lines) and "}" not in lines[j]:
                j += 1
            if j < len(lines) and "}" in lines[j]:
                end = j
                blocks.append((start, end))
                i = end + 1
            else:
                i += 1
        else:
            i += 1

    patches: List[Tuple[List[str], List[str]]] = []
    suggestions: List[Tuple[str, str]] = []  # (frame_id, word_id)

    for start, end in blocks:
        block_lines = lines[start : end + 1]
        if not _eligible_simple_frame_block(block_lines):
            continue

        fid, txt = _get_id_and_text(block_lines)
        if not fid or not txt:
            continue

        wid = _choose_token(txt, word_hanzi_map)
        if not wid:
            continue  # skip uncertain

        block_patch = _make_block_patch(block_lines, wid)
        if not block_patch:
            continue

        old_block, new_block = block_patch
        patches.append((old_block, new_block))
        suggestions.append((fid, wid))

    # Write patch file in a simple "replace old block with new block" format as a unified diff.
    OUT_PATCH.parent.mkdir(parents=True, exist_ok=True)

    if not patches:
        _fail("No eligible frames found to patch (or all were ambiguous).")

    # Apply patches in-memory (from top to bottom) so we can generate accurate diffs
    new_lines_all = lines[:]
    # We must patch from bottom to top to keep indexes stable
    for (start, end), (old_block, new_block) in zip(
        [b for b in blocks if True],  # not used for indexing now
        []
    ):
        pass

    # Instead of trying to re-index, we generate a patch file using difflib
    import difflib
    # Create the final edited file content by performing textual replacements (first occurrence only)
    edited_text = "".join(lines)
    for old_block, new_block in patches:
        old_s = "".join(old_block)
        new_s = "".join(new_block)
        if old_s in edited_text:
            edited_text = edited_text.replace(old_s, new_s, 1)

    original_text = "".join(lines)
    diff = difflib.unified_diff(
        original_text.splitlines(keepends=True),
        edited_text.splitlines(keepends=True),
        fromfile="a/p1_frames.json",
        tofile="b/p1_frames.json",
        n=3,
    )

    OUT_PATCH.write_text("".join(diff), encoding="utf-8")

    print("[suggest_option_tokens_p1] OK")
    print(f"  patched_frames: {len(suggestions)}")
    print(f"  patch_file: {OUT_PATCH}")
    print("  sample (first 10):")
    for fid, wid in suggestions[:10]:
        print(f"    {fid} -> {wid}")

if __name__ == "__main__":
    main()