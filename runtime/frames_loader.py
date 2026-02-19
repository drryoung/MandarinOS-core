import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from runtime.registry_config import RegistryConfig

_FRAMES_BY_KEY: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None


def _resolve_repo_root() -> Path:
    # runtime/frames_loader.py -> runtime -> repo root
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _index_frames_from_pack(data: Any) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Supports either:
      - {"frames":[{...}, ...]}
      - a list: [{...}, ...]
    Each frame must include engine_id and frame_id.
    """
    frames = None
    if isinstance(data, dict) and isinstance(data.get("frames"), list):
        frames = data["frames"]
    elif isinstance(data, list):
        frames = data
    else:
        frames = []

    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for f in frames:
        if not isinstance(f, dict):
            continue
        eid = f.get("engine_id")
        fid = f.get("frame_id")
        if isinstance(eid, str) and isinstance(fid, str) and eid and fid:
            out[(eid, fid)] = f
    return out


def load_all_frames_from_packs(config: Optional[RegistryConfig] = None) -> Dict[Tuple[str, str], Dict[str, Any]]:
    cfg = config or RegistryConfig()
    repo_root = _resolve_repo_root()

    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for filename in cfg.frame_pack_files:
        p = repo_root / filename
        if not p.exists():
            # If a pack file is missing, we just skip it (dev-friendly)
            continue
        data = _load_json(p)
        merged.update(_index_frames_from_pack(data))
    return merged


def load_frame_from_packs(engine_id: str, frame_id: str, config: Optional[RegistryConfig] = None) -> Dict[str, Any]:
    """
    Return a single frame dict given engine_id + frame_id.
    Caches the full frame index in memory for speed.
    """
    global _FRAMES_BY_KEY
    if not engine_id or not frame_id:
        raise ValueError("engine_id and frame_id are required")

    if _FRAMES_BY_KEY is None:
        _FRAMES_BY_KEY = load_all_frames_from_packs(config=config)

    key = (engine_id, frame_id)
    frame = _FRAMES_BY_KEY.get(key)
    if not frame:
        raise KeyError(f"Frame not found for engine_id={engine_id} frame_id={frame_id}")
    return frame
