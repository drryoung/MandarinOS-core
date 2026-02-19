# runtime/registry_config.py
from dataclasses import dataclass

@dataclass(frozen=True)
class RegistryConfig:
    # Frame packs (source of truth for frame content)
    frame_pack_files: tuple[str, ...] = ("p1_frames.json", "p2_frames.json")

    # Cards source of truth (raw cards content)
    cards_file: str = "cards.json"

    # Generated runtime indexes (Phase 5 target)
    runtime_cards_by_id_index: str = "runtime/cards_by_id.json"

    # Temporary dev escape hatch (Phase 5 transition)
    fixture_cards_index: str = "cards_index.json"

    # If True, do NOT fall back to fixture files
    strict_runtime: bool = False
