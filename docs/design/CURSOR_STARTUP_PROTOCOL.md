<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class D: Superseded**
>
> - **Current use:** Retained for traceability of the earlier Cursor onboarding sequence.
> - **May guide current implementation:** No.
> - **Current authority:** `docs/ARCHITECTURE.md` §21, `docs/DOCUMENT_AUTHORITY_INDEX.md` §13, and `docs/CHANGE_CHECKLIST.md`.
> - **Principal caution:** Its internal `ACTIVE` status and read-first sequence have been superseded by the R2 onboarding and authority hierarchy.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# CURSOR_STARTUP_PROTOCOL.md

MandarinOS -- Cursor Mandatory Startup Instructions

Version: 1.0 Status: ACTIVE

Cursor must read this file before making any code changes in this
repository.

------------------------------------------------------------------------

## Step 1 --- Load Core Context

Before analysing or modifying any code, Cursor must read the following
files in order:

1.  AI_CONTEXT.md
2.  docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md
3.  docs/design/mandarinos_design_constitution.txt
4.  MANDARINOS_SYSTEM_MAP.md

These files define:

-   system architecture
-   governance rules
-   design invariants
-   AI role boundaries

Cursor must treat them as authoritative.

------------------------------------------------------------------------

## Step 2 --- Determine Operating Mode

Cursor must decide which mode it is operating in:

### Architect Mode

Used when: - analysing architecture - planning changes - reviewing
design - identifying risks

Rules: - no code edits - analysis only

### Programmer Mode

Used when implementing changes.

Rules: - one concern per change - minimal number of files - preserve
existing behaviour - stop after each change for review - never perform
large refactors automatically

------------------------------------------------------------------------

## Step 3 --- Check Phase Locks

Before modifying runtime behaviour, check:

docs/phases/

If a phase lock exists (for example Phase 6 runtime lock):

Runtime architecture must not be modified.

Allowed work: - builders - UI rendering - content packs - tests -
documentation

------------------------------------------------------------------------

## Step 4 --- Respect Determinism

MandarinOS requires deterministic outputs.

Builders must: - produce reproducible artifacts - avoid randomness -
maintain stable ordering

------------------------------------------------------------------------

## Step 5 --- Safe Implementation Workflow

Standard development flow:

ChatGPT (strategy) ↓ Cursor Architect Mode (analysis) ↓ Implementation
plan ↓ Cursor Programmer Mode (single step) ↓ Stop and review

**Reminder:** One feature per step; architect (plan) before programmer (code); stop for user and ChatGPT review after each step. Cursor must never skip steps in this process.

------------------------------------------------------------------------

## Step 6 --- Emergency Stop Conditions

Cursor must stop and report immediately if a change would:

-   break runtime architecture
-   violate the Design Constitution
-   modify schema contracts
-   change TRACE contract
-   bypass phase locks

Do not attempt automatic fixes.

------------------------------------------------------------------------

## Summary

Cursor must always:

1.  Read the governance documents first
2.  Follow small-step implementation
3.  Protect runtime stability
4.  Respect architectural boundaries

Failure to follow these rules risks destabilising the MandarinOS system.

END OF FILE
