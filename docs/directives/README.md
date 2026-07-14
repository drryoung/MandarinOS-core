# MandarinOS Historical Directives

## Relocation notice

The seventeen historical directive files that were formerly in this directory were **relocated in approved Phase C2A** to [`docs/archive/directives/`](../archive/directives/). This README remains the family entry point at `docs/directives/`.

Archived documents are **not** current implementation authority. For classifications and replacement authority, see `docs/DOCUMENT_AUTHORITY_INDEX.md` §17.

## Authority and maintenance status

This file is **class B** supporting documentation: a family-level authority guide for the historical-directives family. It is **not** a primary architecture contract and does not reclassify or endorse any covered directive.

Individual directives retain their approved §17 classifications (class C, historical/contextual). The exact covered file list is recorded in `docs/PHASE_B5_SCOPE_ASSESSMENT.md` §11 and `docs/DOCUMENT_AUTHORITY_INDEX.md` §17.

When guidance conflicts, use this order:

1. verified current code and tests;
2. class-A R2 documents;
3. class-B supporting documents;
4. historical directives only after explicit verification.

## What this directory contains

This directory now holds **only this family guide**. Seventeen historical implementation directives from Phase 2–7 live in [`docs/archive/directives/`](../archive/directives/). They authorised bounded work for GitHub Copilot, cards, trace wiring, conformance harnesses, simulators, and related tooling at the time they were issued.

They record **what was authorised then**, not what remains present, unchanged, or compatible with the R2 baseline today.

## How to use these documents

Read directives for **historical context** — scope, rationale, and completion criteria from an earlier programme phase. Before acting on any instruction:

- verify the referenced files, branches, commands, and models still exist and match current practice;
- check Git history and the live tree for whether the work was completed, superseded, or removed;
- confirm behaviour against verified code, tests, and the applicable R2 contract.

Do **not** replay a directive verbatim to a coding agent. Current work requires a **new bounded directive** grounded in verified code and approved R2 documentation.

## What these documents do not prove

Words such as **directive**, **implementation**, **integration**, **complete**, or **specification** in filenames do **not** establish current behavioural authority.

A directive does **not** prove that:

- implementation remained in the repository;
- runtime wiring still matches the directive;
- completion criteria remain valid;
- branch, tool, or model assumptions still apply;
- listed file paths or commands are still correct.

Treat old completion criteria, file lists, branch assumptions, commands, and model instructions as **historical evidence only**.

## Current governing documents

- `docs/DOCUMENT_AUTHORITY_INDEX.md`
- `docs/CHANGE_CHECKLIST.md`
- `docs/ARCHITECTURE.md`
- the relevant detailed R2 contract for the subsystem under change
- verified current code and tests

## Covered files

The following seventeen archived paths are covered by this family guide (Phase B5B; relocated Phase C2A):

- `docs/archive/directives/MANDARINOS_ARCHITECT_COPILOT_HANDOFF_DIRECTIVE_PHASE7.txt`
- `docs/archive/directives/MANDARINOS_COPILOT_STARTUP_INSTRUCTIONS.txt`
- `docs/archive/directives/MandarinOS_OPEN_CARD_Trace_Wiring_Directive.txt`
- `docs/archive/directives/MandarinOS_OPEN_CARD_Unit_Test_Directive.txt`
- `docs/archive/directives/MandarinOS_Phase_Boundaries_v1.0.txt`
- `docs/archive/directives/MandarinOS_Runtime_Card_Integration_Directive.txt`
- `docs/archive/directives/MandarinOS_Simulator_Entrypoint_Copilot_Directive.txt`
- `docs/archive/directives/MandarinOS_TurnState_Trace_Contract_v1_directive.txt`
- `docs/archive/directives/MandarinOS_UI_Shell_Copilot_Directive.txt`
- `docs/archive/directives/MandarinOS_card_contract_v1_directive.txt`
- `docs/archive/directives/MandarinOS_conformance_harness_directive.txt`
- `docs/archive/directives/MandarinOS_content_coverage_scanner_v1_directive.txt`
- `docs/archive/directives/MandarinOS_hint_cascade_directive.txt`
- `docs/archive/directives/MandarinOS_integration_kit_scenarios_v1_directive.txt`
- `docs/archive/directives/MandarinOS_scaffolding_transition_harness_v1_directive.txt`
- `docs/archive/directives/MandarinOS_universal_cards_builder_v1_directive.txt`
- `docs/archive/directives/mandarinos_copilot_architecture_update.txt`

## Maintenance rule

Do not edit covered directives to “modernise” them. Changes to current behaviour belong in code, tests, and approved R2 contracts. Update this README only when the approved B5B family set or authority relationships change through governance review.
