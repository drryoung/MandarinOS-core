# Phase 6 — Runtime Architecture Lock (Canonical)

Status: STRICT RUNTIME MODE ENABLED  
Scope: Runtime layer only (no UI)  
Intent: Deterministic execution, fail-fast integrity  

---

## 1. Runtime Data Flow (Authoritative)

Top-level injection occurs in:

- scripts/run_turn.py
- scripts/ui_server.py

Runtime layer does NOT load files directly.

Data is injected into engine.process_turn():

process_turn(
    turn_uid,
    frame,
    engine_affordances,
    cards_index,
    cards,
    emit,
    env
)

---

## 2. Canonical Runtime Inputs (Phase 6)

cards_index:
- Loaded from JSON before runtime
- Must be dict
- Must contain key: "by_word_id"
- by_word_id must be dict
- by_word_id must be non-empty

cards:
- Must be dict
- Must be non-empty
- Every value referenced by by_word_id must exist in cards

These are validated by:
tests/test_fixture_contract.py

Fixtures are canonical for Phase 6.

---

## 3. What Runtime Does NOT Do

Runtime:
- Does NOT read runtime_indexes.json
- Does NOT read runtime/out/*
- Does NOT compute indexes
- Does NOT load files internally
- Does NOT fallback silently in strict_runtime mode

All data must be injected.

---

## 4. runtime_indexes.json Status

runtime_indexes.json:
- Contains index DEFINITIONS only
- Is not currently consumed by runtime code
- Has no materialization builder wired
- Is architectural intent, not implemented behavior

Any attempt to "rebuild runtime indexes" must first implement
a materialization builder and wire it explicitly.

---

## 5. Phase 6 Decision (Locked)

Fixtures are canonical.
We defer index materialization to Phase 7+.

Strict runtime contract is enforced.
Determinism > sophistication.

---

## 6. Strict Runtime Invariants

Resolver requires:

- cards_index is dict
- cards_index["by_word_id"] exists
- cards_index["by_word_id"] non-empty
- cards dict non-empty
- resolved card_id must exist in cards

If violated:
- dev/test: raise
- prod: controlled behavior

No hidden fallbacks allowed.

---

## 7. Architectural Principle

Runtime is pure.
All IO happens outside runtime layer.

Engine is deterministic given injected inputs.

---

END OF LOCK FILE
