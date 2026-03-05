"""
Phase 7.3 — Frame Tokens Runtime Builder
Generates tokenized frame text artifact for clickable word-level rendering.
Consumed by UI only. No runtime/resolver/SRS changes.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
RUNTIME_OUT = REPO_ROOT / "runtime" / "out_phase7"

SCHEMA_VERSION = "1.0"
NAME = "Frame Tokens Runtime"
DESCRIPTION = (
    "Tokenized frame text for clickable word-level rendering. "
    "Unknown tokens allowed."
)

# ── CJK unicode ranges ────────────────────────────────────────────────────────
_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+')
_SLOT_RE = re.compile(r'\{([A-Z0-9_]+)\}')
_PUNCT   = set('。，？！、；：…—～·「」『』【】《》〈〉""''')


def build_hanzi_lookup(words_paths: list[Path]) -> dict[str, str]:
    """
    Build deterministic hanzi -> word_id map from word pack files.
    Rules:
    - Only entries where id starts with "w_" and hanzi is non-empty string.
    - Duplicate hanzi: keep lexicographically smallest word_id.
    """
    lookup: dict[str, str] = {}
    for path in words_paths:
        if not path.exists():
            raise FileNotFoundError(f"Word file missing: {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        words = data.get("words", [])
        if not isinstance(words, list):
            raise ValueError(f"Expected 'words' list in {path}")
        for entry in words:
            word_id = entry.get("id", "")
            hanzi   = entry.get("hanzi", "")
            if (
                isinstance(word_id, str) and word_id.startswith("w_")
                and isinstance(hanzi, str) and hanzi
            ):
                if hanzi not in lookup or word_id < lookup[hanzi]:
                    lookup[hanzi] = word_id
    return lookup


def tokenize(text: str, hanzi_lookup: dict[str, str]) -> list[dict]:
    """
    Deterministic greedy longest-match tokenizer.
    Priority: slot placeholders > CJK chunks > punct > other.
    Never crashes on unknown characters. Never skips characters.
    """
    tokens: list[dict] = []
    i = 0
    while i < len(text):
        # 1) Slot placeholder {SLOT_NAME}
        slot_match = _SLOT_RE.match(text, i)
        if slot_match:
            tokens.append({"t": slot_match.group(0), "kind": "slot",
                           "slot_name": slot_match.group(1)})
            i = slot_match.end()
            continue

        # 2) CJK chunk — greedy longest match against lookup
        cjk_match = _CJK_RE.match(text, i)
        if cjk_match:
            chunk = cjk_match.group(0)
            # Greedy longest match from position 0 of chunk
            j = 0
            while j < len(chunk):
                best_len = 0
                best_wid = None
                # Try all lengths from longest to shortest
                for length in range(len(chunk) - j, 0, -1):
                    substr = chunk[j:j + length]
                    if substr in hanzi_lookup:
                        if length > best_len or (
                            length == best_len
                            and hanzi_lookup[substr] < best_wid
                        ):
                            best_len = length
                            best_wid = hanzi_lookup[substr]
                if best_wid:
                    tokens.append({"t": chunk[j:j + best_len],
                                   "kind": "word", "word_id": best_wid})
                    j += best_len
                else:
                    tokens.append({"t": chunk[j], "kind": "word"})
                    j += 1
            i = cjk_match.end()
            continue

        # 3) Punctuation
        ch = text[i]
        if ch in _PUNCT:
            tokens.append({"t": ch, "kind": "punct"})
            i += 1
            continue

        # 4) Space
        if ch == " ":
            tokens.append({"t": ch, "kind": "space"})
            i += 1
            continue

        # 5) Everything else (ASCII, digits, etc.)
        tokens.append({"t": ch, "kind": "other"})
        i += 1

    return tokens


def build_frame_tokens(
    frames_paths: list[Path],
    words_paths: list[Path],
) -> tuple[dict, int]:
    """
    Build the frame_tokens artifact.
    Returns (artifact_dict, unknown_token_count).
    """
    # Validate inputs exist
    for path in frames_paths + words_paths:
        if not path.exists():
            raise FileNotFoundError(f"Required input missing: {path}")

    hanzi_lookup = build_hanzi_lookup(words_paths)

    # Load all frames
    all_frames: list[dict] = []
    for path in frames_paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        frames = data.get("frames", [])
        if not isinstance(frames, list):
            raise ValueError(f"Expected 'frames' list in {path}")
        all_frames.extend(frames)

    # Build output — sort by frame_id
    frames_out: list[dict] = []
    unknown_count = 0

    for frame in sorted(all_frames, key=lambda f: f.get("id", "")):
        frame_id = frame.get("id", "")
        text     = frame.get("text", "")
        if not frame_id or not isinstance(text, str):
            continue

        tokens = tokenize(text, hanzi_lookup)
        unknown_count += sum(
            1 for t in tokens if t["kind"] == "word" and "word_id" not in t
        )

        frames_out.append({
            "frame_id": frame_id,
            "text":     text,
            "tokens":   tokens,
        })

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "name":           NAME,
        "description":    DESCRIPTION,
        "frames":         frames_out,
    }
    return artifact, unknown_count


def serialise(artifact: dict) -> str:
    """Canonical serialisation — deterministic across runs."""
    return json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_frame_tokens(
    frames_paths: list[Path],
    words_paths: list[Path],
    out_dir: Path,
) -> tuple[str, int]:
    """
    Build, serialise, and write both output files.
    Returns (serialised_string, unknown_token_count) for manifest use.
    """
    artifact, unknown_count = build_frame_tokens(frames_paths, words_paths)
    serialised = serialise(artifact)

    out_dir.mkdir(parents=True, exist_ok=True)

    canonical_path = out_dir / "frame_tokens.runtime.json"
    compat_path    = out_dir / "frame_render_tokens.runtime.json"

    # Write canonical
    canonical_path.write_text(serialised, encoding="utf-8")
    # Write compat alias — same bytes
    compat_path.write_text(serialised, encoding="utf-8")

    frame_count = len(artifact["frames"])
    print(
        f"[build_runtime_artifacts] frame_tokens frames: {frame_count}, "
        f"unknown_tokens: {unknown_count}"
    )
    return serialised, unknown_count, frame_count