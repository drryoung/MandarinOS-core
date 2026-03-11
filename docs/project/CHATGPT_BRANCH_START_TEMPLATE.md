# CHATGPT Branch Start Template — MandarinOS

## Project
MandarinOS

## Phase
Phase 6 — Runtime Integrity

## Mode
strict_runtime = True  
resolver strict checks enabled  
runtime/out guardrail active  

## Working Rules
- Runtime layer only
- No UI changes
- Minimal diffs
- One task per response
- Plain English instructions
- Do not guess missing wiring — inspect before acting

## Known-Good Baseline (must confirm at start)
- Frames load: PASS
- Resolver sample: PASS
- Guardrail blocks runtime/out loading
- Working tree clean

## Canonical Runtime Facts (Do Not Re-discover)
1. `runtime_indexes.json` = DEFINITIONS only (not materialized maps)
2. `runtime/out/runtime_indexes_computed_v1.json` = legacy snapshot (never load at runtime)
3. `tools/cards/build_cards.py` rebuilds cards artifacts only (not runtime indexes)
4. `OpenCardResolver` requires:
   - cards_index['by_word_id'] present & non-empty
   - cards dict non-empty
   - Does NOT load files itself
5. `runtime/registry_config.py` defines future paths but runtime_cards_by_id_index is not currently wired

## Critical Constraint
There is currently no confirmed standalone runtime index materialization builder wired into execution.
Do not assume one exists without code evidence.

## When Starting a New ChatGPT Branch
Paste:
- This entire file
- PHASE6_RUNTIME_INDEXES_NOTES.md
- Current git status
- The single next objective

## Current Objective (Fill Before Starting Branch)
<WRITE ONE CLEAR OBJECTIVE HERE>

## Stop Conditions
- If task touches UI → stop
- If task modifies more than one runtime file → stop
- If working tree becomes dirty unintentionally → revert before continuing
