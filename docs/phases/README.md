# MandarinOS Historical Phase Documents

## Authority and maintenance status

This file is **class B** supporting documentation: a family-level authority guide for selected historical phase documents in `docs/phases/`. It is **not** a primary architecture contract and does not reclassify or endorse any covered phase file.

This guide covers **exactly nine** B5B-assigned files — not every file in the directory. Other phase documents (for example Phase 6 lock/freeze files with individual notices, or class-F proposals) retain their separate §17 classifications and notices.

The exact covered file list is recorded in `docs/PHASE_B5_SCOPE_ASSESSMENT.md` §11 and `docs/DOCUMENT_AUTHORITY_INDEX.md` §17.

When guidance conflicts, use this order:

1. verified current code and tests;
2. class-A R2 documents;
3. class-B supporting documents;
4. historical phase material only after explicit verification.

## What this directory contains

Phase documents are historical records of milestones, decisions, proposals, acceptance criteria, stabilisation briefs, simulation notes, rollback points, and similar programme artefacts.

They explain **what was planned, claimed, or accepted at a phase boundary** — not what the conversation runtime does today.

## How to interpret phase labels

A **phase number** or filename does **not** prove that its behaviour, architecture, or completion status remains current.

Words such as **phase**, **lock**, **freeze**, **complete**, **final**, **signoff**, or **acceptance** describe historical programme language. They do **not** override the R2 baseline or verified code.

Any document that already carries an individual `MANDARINOS-DOCUMENT-STATUS` notice remains governed by that notice in addition to this family guide.

## Locks, freezes, completion claims, and baselines

`LOCK`, `FREEZE`, `COMPLETE`, `FINAL`, or similar wording in a phase document does **not** establish current maintenance authority.

Historical locks and freezes (including Phase 6 documents outside this nine-file B5B set) may still carry individual notices from earlier Phase B work. Those notices and the R2 architecture package govern how to treat them.

Completion claims, acceptance criteria, and rollback points must be checked against Git, tests, ADRs, and live code before they inform maintenance decisions. Phase documents may explain rationale but must **not** independently authorise changes.

## Current governing documents

- `docs/DOCUMENT_AUTHORITY_INDEX.md`
- `docs/ARCHITECTURE.md`
- `docs/ARCHITECTURAL_DECISIONS.md`
- `docs/CHANGE_CHECKLIST.md`
- relevant detailed R2 contracts (`docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, `docs/ASR_PIPELINE.md`, and others as applicable)
- verified current code and tests

## Covered files

The following nine paths are covered by this family guide (Phase B5B):

- `docs/phases/MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md`
- `docs/phases/MANDARINOS_PHASE_10_5_STABILISATION_BRIEF.md`
- `docs/phases/MandarinOS_Phase9_Signoff.md`
- `docs/phases/PHASE6_RUNTIME_INDEXES_NOTES.md`
- `docs/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md`
- `docs/phases/PHASE9_2_BRIDGE_TIER.md`
- `docs/phases/PHASE_10_5_CONVERSATION_SIMULATION.md`
- `docs/phases/Phase 3 Step 1 Audio-first UI.md`
- `docs/phases/ROLLBACK_POINT_v1.md`

## Maintenance rule

Do not edit covered phase documents to refresh claims or criteria. Current behaviour belongs in code, tests, and approved R2 contracts. Update this README only when the approved B5B family set or authority relationships change through governance review.
