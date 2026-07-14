<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class C: Historical context**
>
> - **Current use:** Retained as a Phase 6 freeze record.
> - **May guide current implementation:** No.
> - **Current authority:** `docs/ARCHITECTURE.md` and the applicable current R2 contracts.
> - **Principal caution:** The historical `FREEZE` label does not freeze or define current R2 behaviour.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# PHASE 6 FREEZE — Runtime Integrity (Frozen)

Date: 2026-02-27 (local)

## Scope
Runtime layer only. No UI changes.

## Frozen outcomes
- Strict runtime boundary validation at engine boundary (fail-fast on malformed injected maps).
- Canonical fixtures aligned with strict runtime contract (cards_index uses by_word_id).
- Fixture Contract validator added (guards fixture structure + referential integrity).
- Determinism regression test added (OPEN_CARD semantics stable; timestamps normalized).
- Architecture knowledge externalized into canonical repo docs (prevents rediscovery).
- UTC timestamp warning removed (timezone-aware timestamp).

## Regression gates
Run:
- `python -m pytest -q -s`

## Tooling note
If pytest capture crashes on Windows/Python 3.14:
- `python -m pytest -q -s`
(or `--capture=no`)
