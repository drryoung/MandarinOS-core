# Phase 6 — Runtime Integrity — Runtime Indexes Notes (Canonical)

## Context
- strict_runtime = True
- Runtime layer only (no UI)
- Minimal diffs; keep working tree clean unless the task explicitly requires changes.

## Key facts (confirmed)
1) `runtime_indexes.json` (repo root) is **index DEFINITIONS only** (schema, sources, build rules).
2) `runtime/out/` contains **computed artifacts**. These must never be *loaded* at runtime.
   - `runtime/out/runtime_indexes_computed_v1.json` is **legacy** and retained for reference only.
3) The cards builder (`python tools/cards/build_cards.py`) generates:
   - `tools/cards/out/cards.json`
   - `tools/cards/out/cards_index.json`
   - `tools/cards/out/cards_by_id.json`
   This builder **does NOT** rebuild runtime indexes.
4) Current strict runtime `OpenCardResolver` requires:
   - `cards_index` dict with `cards_index['by_word_id']` present and non-empty
   - `cards` dict non-empty
   These are passed in by the caller; resolver does not load files directly.
5) `runtime/registry_config.py` defines future-facing paths (Phase 5 target), but:
   - `runtime_cards_by_id_index = "runtime/cards_by_id.json"` is **not currently referenced** by loader code.
   Therefore, do not add `runtime/cards_by_id.json` unless/until it is actually wired.

## Implication
- There is currently **no implemented “runtime index materialization builder”** that consumes `runtime_indexes.json`
  and writes computed runtime index maps for strict runtime execution.
- Any “rebuild computed runtime indexes” work must first identify or implement the missing builder/wiring step.

## How to start a new ChatGPT branch (copy/paste)
- Project: MandarinOS
- Phase: 6 — Runtime Integrity
- Mode: strict_runtime = True
- Rules: Runtime layer only; No UI; Minimal diffs; One task per response; Plain English instructions
- Known truths: paste the full contents of this file
