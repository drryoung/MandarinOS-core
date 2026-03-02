# tools/build_runtime_artifacts.py
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[1]  # tools/.. -> repo root

# -------------------------
# Phase 7.2: Explicit tokens
# -------------------------

import re

_WID_RE = re.compile(r"^w_[A-Za-z0-9_]+$")

# Start small: require explicit tokens ONLY for the MVP frame(s) you want to make work.
# Add more frame_ids later in tiny batches.
REQUIRE_EXPLICIT_OPTION_TOKENS_FOR_FRAMES = {
    "frame.greeting.hello",
    "f_thanks",
    "f_from_where",
    "frame.location.live_question",
}
def _validate_option_tokens(frame_id: str, option_tokens, known_word_ids: set[str]) -> list[str]:
    """
    Fail-fast validation for frame.option_tokens.

    Rules:
      - must be a non-empty list of strings
      - each token must look like w_*
      - each token must exist in known_word_ids
      - duplicates are NOT allowed (no silent coercion)
    """
    if option_tokens is None:
        raise ValueError(f"[BUILD] frame {frame_id}: option_tokens is None (missing).")

    if not isinstance(option_tokens, list):
        raise TypeError(f"[BUILD] frame {frame_id}: option_tokens must be a list, got {type(option_tokens).__name__}.")

    if len(option_tokens) == 0:
        raise ValueError(f"[BUILD] frame {frame_id}: option_tokens must be non-empty.")

    seen = set()
    out: list[str] = []
    for tok in option_tokens:
        if not isinstance(tok, str):
            raise TypeError(f"[BUILD] frame {frame_id}: option_tokens entries must be strings, got {type(tok).__name__}.")
        if not _WID_RE.match(tok):
            raise ValueError(f"[BUILD] frame {frame_id}: invalid token '{tok}' (expected word_id like 'w_*').")
        if tok not in known_word_ids:
            raise ValueError(f"[BUILD] frame {frame_id}: unknown word_id token '{tok}' (not found in lexicon).")
        if tok in seen:
            raise ValueError(f"[BUILD] frame {frame_id}: duplicate token '{tok}' (no silent dedupe).")
        seen.add(tok)
        out.append(tok)

    return out

def _resolve_frame_option_word_ids(frame: dict, known_word_ids: set[str]) -> list[str] | None:
    frame_id = frame.get("id")
    if not frame_id:
        raise ValueError("[BUILD] frame missing required 'id' field.")
    if "option_tokens" not in frame:
        return None
    return _validate_option_tokens(frame_id, frame.get("option_tokens"), known_word_ids)

def _enforce_required_explicit_tokens(frame: dict) -> None:
    frame_id = frame.get("id")
    if not frame_id:
        raise ValueError("[BUILD] frame missing required 'id' field.")
    if frame_id in REQUIRE_EXPLICIT_OPTION_TOKENS_FOR_FRAMES and "option_tokens" not in frame:
        raise ValueError(
            f"[BUILD] frame {frame_id}: option_tokens REQUIRED for this frame (migration gate)."
        )

# Inputs
CARDS_BY_ID_IN = REPO_ROOT / "tools" / "cards" / "out" / "cards_by_id.json"
P1_FRAMES_IN = REPO_ROOT / "p1_frames.json"
P2_FRAMES_IN = REPO_ROOT / "p2_frames.json"
P1_WORDS_IN = REPO_ROOT / "p1_words.json"
P2_WORDS_IN = REPO_ROOT / "p2_words.json"

# Outputs
RUNTIME_OUT_DIR = REPO_ROOT / "runtime" / "out_phase7"
CARDS_OUT = RUNTIME_OUT_DIR / "cards.runtime.json"
CARDS_INDEX_OUT = RUNTIME_OUT_DIR / "cards_index.runtime.json"
MANIFEST_OUT = RUNTIME_OUT_DIR / "build_manifest.json"
FRAME_RENDER_TOKENS_OUT = RUNTIME_OUT_DIR / "frame_render_tokens.runtime.json"


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_deterministic(path: Path, obj: Any) -> bytes:
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    b = (s + "\n").encode("utf-8")
    path.write_bytes(b)
    return b


def _fail(msg: str) -> None:
    raise SystemExit(f"[build_runtime_artifacts] ERROR: {msg}")

def _load_word_hanzi_map(words_path: Path) -> dict[str, str]:
    if not words_path.exists():
        return {}
    data = _read_json(words_path)
    if not isinstance(data, dict):
        _fail(f"{words_path} must be a JSON object (dict)")
    words = data.get("words")
    if not isinstance(words, list):
        _fail(f"{words_path} must contain a top-level 'words' list")
    out: dict[str, str] = {}
    for w in words:
        if not isinstance(w, dict):
            continue
        wid = w.get("word_id") or w.get("id")
        hz = w.get("hanzi")
        if isinstance(wid, str) and wid.startswith("w_") and isinstance(hz, str) and hz:
            out[wid] = hz
    return out

def _extract_frames(pack_obj: Any) -> list[dict]:
    if isinstance(pack_obj, list):
        frames = pack_obj
    elif isinstance(pack_obj, dict):
        for k in ("frames", "items", "data"):
            v = pack_obj.get(k)
            if isinstance(v, list):
                frames = v
                break
        else:
            frames = None
    else:
        frames = None
    if not isinstance(frames, list):
        _fail("Frame pack structure unexpected (expected a list or dict containing a list).")
    out = []
    for x in frames:
        if isinstance(x, dict) and isinstance(x.get("id"), str):
            out.append(x)
    return out

def _build_frame_to_word_map(frames: list[dict], word_hanzi_map: dict[str, str]) -> dict[str, str]:
    known_word_ids = set(word_hanzi_map.keys())
    candidates = sorted(word_hanzi_map.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out: dict[str, str] = {}
    for fr in frames:
        fid = fr.get("id")
        if not isinstance(fid, str) or not fid:
            continue
        if "option_tokens" in fr:
            tokens = _validate_option_tokens(fid, fr.get("option_tokens"), known_word_ids)
            out[fid] = tokens[0]
            continue
        text = fr.get("text")
        if not (isinstance(text, str) and text):
            continue
        hits = []
        for wid, hz in candidates:
            if hz in text:
                hits.append((wid, hz))
        if not hits:
            continue
        best_len = max(len(hz) for _, hz in hits)
        best = sorted([wid for wid, hz in hits if len(hz) == best_len])[0]
        out[fid] = best
    return out


# -------------------------
# Phase 7.3: Frame render tokens
# -------------------------

def _build_frame_render_tokens(
    frames: list[dict],
    word_hanzi_map: dict[str, str],
    known_word_ids: set[str],
) -> dict[str, list[dict]]:
    """
    For each frame that has option_tokens, walk through the tokens in order,
    align each hanzi surface in frame.text, and emit alternating word/lit tokens.
    Fails loudly if alignment is impossible.
    """
    result: dict[str, list[dict]] = {}

    for frame in frames:
        fid = frame.get("id")
        option_tokens = frame.get("option_tokens")
        if not option_tokens:
            continue

        # Validate tokens first (fail-fast, no silent coercion)
        validated = _validate_option_tokens(fid, option_tokens, known_word_ids)

        text: str = frame.get("text", "")
        tokens: list[dict] = []
        cursor = 0

        for word_id in validated:
            surface = word_hanzi_map.get(word_id)
            if surface is None:
                raise SystemExit(
                    f"[BUILD] frame {fid}: word_id '{word_id}' has no hanzi in lexicon"
                )

            idx = text.find(surface, cursor)
            if idx == -1:
                raise SystemExit(
                    f"[BUILD] frame {fid}: cannot align {word_id} "
                    f"(hanzi={surface}) in text '{text}'"
                )

            if idx > cursor:
                tokens.append({"t": "lit", "s": text[cursor:idx]})

            tokens.append({"t": "word", "id": word_id, "s": surface})
            cursor = idx + len(surface)

        if cursor < len(text):
            tokens.append({"t": "lit", "s": text[cursor:]})

        result[fid] = tokens

    return result


def main() -> None:
    if not CARDS_BY_ID_IN.exists():
        _fail(f"Missing input file: {CARDS_BY_ID_IN}")

    data = _read_json(CARDS_BY_ID_IN)

    if isinstance(data, dict) and "cards" in data and isinstance(data["cards"], dict):
        cards: Dict[str, Any] = data["cards"]
    elif isinstance(data, dict):
        cards = data
    else:
        _fail("cards_by_id.json must be a JSON object (dict)")

    if not isinstance(cards, dict):
        _fail("cards must be a dict")
    if not cards:
        _fail("cards dict is empty")

    bad_keys = [k for k in cards.keys() if not isinstance(k, str) or not k.startswith("w_")]
    if bad_keys:
        _fail(
            f"cards contains non word-id keys (expected all keys start with 'w_'). "
            f"Example bad keys: {bad_keys[:10]}"
        )

    by_word_id = {wid: wid for wid in sorted(cards.keys())}

    word_hanzi_map: dict[str, str] = {}
    word_hanzi_map.update(_load_word_hanzi_map(P1_WORDS_IN))
    word_hanzi_map.update(_load_word_hanzi_map(P2_WORDS_IN))

    known_word_ids = set(word_hanzi_map.keys())

    extra_frame_maps: dict[str, str] = {}
    all_frames: list[dict] = []

    for frames_path in (P1_FRAMES_IN, P2_FRAMES_IN):
        if frames_path.exists():
            pack = _read_json(frames_path)
            frames = _extract_frames(pack)
            all_frames.extend(frames)
            frame_map = _build_frame_to_word_map(frames, word_hanzi_map)
            extra_frame_maps.update(frame_map)

    for fid, wid in sorted(extra_frame_maps.items()):
        by_word_id[fid] = wid

    print(f"[build_runtime_artifacts] frame_id mappings added: {len(extra_frame_maps)}")

    if not by_word_id:
        _fail("by_word_id is empty (unexpected: cards was non-empty)")

    missing = [cid for cid in by_word_id.values() if cid not in cards]
    if missing:
        _fail(f"cards_index refers to missing card_ids. Example missing: {missing[:10]}")

    cards_index = {"by_word_id": by_word_id}

    RUNTIME_OUT_DIR.mkdir(parents=True, exist_ok=True)

    cards_bytes = _write_json_deterministic(CARDS_OUT, cards)
    index_bytes = _write_json_deterministic(CARDS_INDEX_OUT, cards_index)

    # Phase 7.3: generate frame_render_tokens.runtime.json
    render_tokens = _build_frame_render_tokens(all_frames, word_hanzi_map, known_word_ids)
    render_payload = {
        "schema_version": "1.0",
        "name": "Frame Render Tokens (UI)",
        "frames": render_tokens,
    }
    render_bytes = _write_json_deterministic(FRAME_RENDER_TOKENS_OUT, render_payload)

    in_bytes = CARDS_BY_ID_IN.read_bytes()
    manifest = {
        "builder": "tools/build_runtime_artifacts.py",
        "inputs": {
            "cards_by_id_path": str(CARDS_BY_ID_IN.relative_to(REPO_ROOT)),
            "cards_by_id_sha256": _sha256_bytes(in_bytes),
            "card_count": len(cards),
        },
        "outputs": {
            "cards_runtime_path": str(CARDS_OUT.relative_to(REPO_ROOT)),
            "cards_runtime_sha256": _sha256_bytes(cards_bytes),
            "cards_index_runtime_path": str(CARDS_INDEX_OUT.relative_to(REPO_ROOT)),
            "cards_index_runtime_sha256": _sha256_bytes(index_bytes),
            "frame_render_tokens_path": str(FRAME_RENDER_TOKENS_OUT.relative_to(REPO_ROOT)),
            "frame_render_tokens_sha256": _sha256_bytes(render_bytes),
            "frame_render_tokens_count": len(render_tokens),
            "by_word_id_count": len(by_word_id),
        },
    }
    _write_json_deterministic(MANIFEST_OUT, manifest)

    print("[build_runtime_artifacts] OK")
    print(f"  cards:              {CARDS_OUT}")
    print(f"  cards_index:        {CARDS_INDEX_OUT}")
    print(f"  frame_render_tokens:{FRAME_RENDER_TOKENS_OUT}  ({len(render_tokens)} frames)")
    print(f"  manifest:           {MANIFEST_OUT}")
    print(f"  card_count:         {len(cards)}")


if __name__ == "__main__":
    main()