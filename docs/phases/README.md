# MandarinOS Historical Phase Documents

## Relocation notice

Eleven historical class-C phase documents that were formerly in this directory were **relocated in approved Phase C2B** to [`docs/archive/phases/`](../archive/phases/). This README remains the family entry point at `docs/phases/`.

The three class-F proposal files that once remained in this directory pending a later relocation batch were subsequently **relocated to [`docs/proposals/`](../proposals/) in approved Phase C2G-core and Phase C2G-review**: `PHASE10_TECHNICAL_PROPOSAL.md`, `PHASE9_CONTENT_AND_ENGINES_PLAN.md`, and `PHASE_10_5_MAPPING_AND_SCHEMA_PROPOSAL.md`. No class-F proposal remains physically in this directory.

This directory now physically holds only this family guide and one class-C document, `MandarinOS-Phase 3 Acceptance checklist.MD` (a prospective pre-acceptance gating checklist, not a completion record; added to inventory during approved Phase D1). Archived documents are **not** current implementation authority. For classifications and replacement authority, see `docs/DOCUMENT_AUTHORITY_INDEX.md` §17.6.

## Authority and maintenance status

This file is **class B** supporting documentation: a family-level authority guide for the historical-phase family. It is **not** a primary architecture contract and does not reclassify or endorse any covered phase file.

The exact covered historical file list is recorded in `docs/PHASE_B5_SCOPE_ASSESSMENT.md` §11 and `docs/DOCUMENT_AUTHORITY_INDEX.md` §17.

When guidance conflicts, use this order:

1. verified current code and tests;
2. class-A R2 documents;
3. class-B supporting documents;
4. historical phase material only after explicit verification.

## What this directory contains

This directory now holds **this family guide** and **one class-C document**, a Phase 3 pre-acceptance gating checklist (`MandarinOS-Phase 3 Acceptance checklist.MD`; Phase D1 approved addition to inventory). Eleven historical class-C phase documents from Phase 3–10.5 live in [`docs/archive/phases/`](../archive/phases/) (relocated in approved Phase C2B). The three class-F proposals formerly in this directory now live in [`docs/proposals/`](../proposals/) (relocated in approved Phase C2G-core/C2G-review).

Phase documents are historical records of milestones, decisions, acceptance criteria, stabilisation briefs, simulation notes, rollback points, and similar programme artefacts.

They explain **what was planned, claimed, or accepted at a phase boundary** — not what the conversation runtime does today.

## How to interpret phase labels

A **phase number** or filename does **not** prove that its behaviour, architecture, or completion status remains current.

Words such as **phase**, **lock**, **freeze**, **complete**, **final**, **signoff**, or **acceptance** describe historical programme language. They do **not** override the R2 baseline or verified code.

Any document that already carries an individual `MANDARINOS-DOCUMENT-STATUS` notice remains governed by that notice in addition to this family guide.

## Locks, freezes, completion claims, and baselines

`LOCK`, `FREEZE`, `COMPLETE`, `FINAL`, or similar wording in a phase document does **not** establish current maintenance authority.

Historical locks and freezes (including archived Phase 6 documents) may still carry individual notices from earlier Phase B work. Those notices and the R2 architecture package govern how to treat them.

Completion claims, acceptance criteria, and rollback points must be checked against Git, tests, ADRs, and live code before they inform maintenance decisions. Phase documents may explain rationale but must **not** independently authorise changes.

## Current governing documents

- `docs/DOCUMENT_AUTHORITY_INDEX.md`
- `docs/ARCHITECTURE.md`
- `docs/ARCHITECTURAL_DECISIONS.md`
- `docs/CHANGE_CHECKLIST.md`
- relevant detailed R2 contracts (`docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, `docs/ASR_PIPELINE.md`, and others as applicable)
- verified current code and tests

## Covered files

The following eleven archived paths are covered by this family guide (Phase B5B; relocated in approved Phase C2B):

- `docs/archive/phases/MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md`
- `docs/archive/phases/MANDARINOS_PHASE_10_5_STABILISATION_BRIEF.md`
- `docs/archive/phases/MandarinOS_Phase9_Signoff.md`
- `docs/archive/phases/PHASE6_FREEZE.md`
- `docs/archive/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`
- `docs/archive/phases/PHASE6_RUNTIME_INDEXES_NOTES.md`
- `docs/archive/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md`
- `docs/archive/phases/PHASE9_2_BRIDGE_TIER.md`
- `docs/archive/phases/PHASE_10_5_CONVERSATION_SIMULATION.md`
- `docs/archive/phases/Phase 3 Step 1 Audio-first UI.md`
- `docs/archive/phases/ROLLBACK_POINT_v1.md`

### Phase 9.1 acceptance-criteria pair note (Phase D4C, 2026-07-18)

`PHASE9_1_ACCEPTANCE_CRITERIA.md` and `MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md` are both archived class-C history; neither is current authority — current architecture and code (see `docs/DOCUMENT_AUTHORITY_INDEX.md` §17.6a) control current behaviour. `PHASE9_1_ACCEPTANCE_CRITERIA.md` is the preferred historical implementation-reference copy; `MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md` is a complementary QA/outcome record. Both are retained because each contains unique material — see `docs/DOCUMENT_AUTHORITY_INDEX.md` §12 Group 6.

## Maintenance rule

Do not edit covered phase documents to refresh claims or criteria. Current behaviour belongs in code, tests, and approved R2 contracts. Update this README only when the approved B5B family set or authority relationships change through governance review.
