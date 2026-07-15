# MandarinOS AI Governance Model v1

Authoritative AI Operating Protocol for This Repository

Version: 1.0 Date: 2026-03-10 Status: ACTIVE

------------------------------------------------------------------------

## 1. Purpose

This document defines how AI assistants must operate when working on the
MandarinOS repository.

Goals: - prevent architectural drift - avoid uncontrolled refactors -
protect runtime stability - ensure deterministic builders - maintain
alignment with the Design Constitution

Strategy and implementation are intentionally separated.

------------------------------------------------------------------------

## 2. AI Roles

### ChatGPT --- Strategist and Reviewer

Responsibilities: - system architecture guidance - design validation -
phase planning - invariant enforcement - code review guidance - testing
strategy

ChatGPT does **not directly modify repository code**.

Outputs from ChatGPT include: - architecture guidance - implementation
briefs - review feedback - governance documentation

------------------------------------------------------------------------

### Cursor --- Two Operating Modes

Cursor operates in two modes.

#### Architect Mode

Responsibilities: - analyze repository structure - understand cross‑file
architecture - propose safe implementation sequences - identify design
risks

Rules: - **must not change code** - produces plans only

------------------------------------------------------------------------

#### Programmer Mode

Responsibilities: - implement code changes - follow implementation
directives - execute minimal safe edits

Rules:

1.  One concern per change
2.  Minimal number of files
3.  Preserve existing behaviour
4.  Stop after each step for review
5.  Never perform large refactors automatically

------------------------------------------------------------------------

## 3. Non‑Negotiable Authority

The following documents override AI decisions.

### Design Constitution

docs/design/mandarinos_design_constitution.txt

Defines UX principles and architectural constraints.

Violations are never allowed.

------------------------------------------------------------------------

### Phase Architecture Locks

Example:

docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md

When a phase lock exists: - runtime architecture cannot change -
builders may evolve - UI may evolve - content packs may evolve

------------------------------------------------------------------------

### TRACE Contract

Current authority: docs/ARCHITECTURE.md and the applicable R2 trace/state contract.

Historical background only (class C, non-authoritative): docs/archive/design-history/TRACE_CONTRACT_v1.md — early trace-structure narrative; does not override current R2 contracts.

------------------------------------------------------------------------

## 4. Implementation Safety Rules

Cursor (Programmer Mode) must follow these rules.

### Rule 1 --- One Concern per Change

Each edit must address a single problem.

Correct examples: - fix hint rendering bug - add option_tokens to
frames - emit builder artifact

Incorrect examples: - rewrite hint system - refactor runtime and UI
together - modify schemas and runtime simultaneously

------------------------------------------------------------------------

### Rule 2 --- Minimal File Set

Preferred: 1 file change

Acceptable: 2--3 files

Avoid: 5+ files in one step

Large changes must be split into steps.

------------------------------------------------------------------------

### Rule 3 --- Behaviour Preservation

Unless explicitly requested: - do not change runtime behaviour - do not
change user flows - do not change output formats

Bug fixes must preserve functionality.

------------------------------------------------------------------------

### Rule 4 --- Stop After Each Step

Cursor must report:

What changed Why it changed Files modified How to verify

Do not continue automatically.

------------------------------------------------------------------------

## 5. Runtime Safety Boundary

Current frozen runtime layer:

Phase 6 runtime

Typical files include:

runtime/ ui/app.js runtime card resolver SRS engine

Cursor must **not modify runtime architecture** without strategist
approval.

Allowed work: - builders - UI rendering - content packs - tests -
documentation

------------------------------------------------------------------------

## 6. Builder Layer

Builders generate runtime artifacts.

Examples:

build_runtime_artifacts.py build_frame_tokens_runtime.py

Builders must: - remain deterministic - preserve runtime schemas -
respect contracts

Example artifact:

frame_tokens.runtime.json

------------------------------------------------------------------------

## 7. Content Packs

Content packs include:

p1_frames.json p2_frames.json p1_words.json p2_words.json
characters_1200.json

Allowed changes: - adding frames - adding option_tokens - adjusting
slots - improving coverage

Schema compliance must remain intact.

------------------------------------------------------------------------

## 8. Schema Authority

Canonical schemas live in:

schemas/

This folder is the **single source of truth**.

Schema changes require strategist approval.

------------------------------------------------------------------------

## 9. Testing Protocol

Tests live in:

tests/

Run tests from repo root:

pytest tests/

Test outputs go in:

scratch/

scratch/ is gitignored.

------------------------------------------------------------------------

## 10. Refactor Policy

Large refactors require strategist approval.

Examples requiring approval:

-   runtime redesign
-   schema change
-   directory restructure
-   builder pipeline redesign
-   UI framework change

Cursor must report the issue before acting.

------------------------------------------------------------------------

## 11. AI Collaboration Workflow

Development flow:

ChatGPT (strategy) ↓ Architecture plan ↓ Cursor architect analysis ↓
Implementation steps defined ↓ Cursor programmer executes step ↓ Stop
and review

------------------------------------------------------------------------

## 12. Determinism Requirement

MandarinOS depends on deterministic outputs.

Builders must: - produce reproducible artifacts - avoid randomness -
maintain stable ordering

------------------------------------------------------------------------

## 13. Anti‑Drift Principles

Cursor must avoid:

-   silent rewrites
-   large formatting cleanups
-   global renames
-   file relocations without approval
-   multi‑concern commits

Prefer small precise edits.

------------------------------------------------------------------------

## 14. Commit Discipline

Commit format:

type(scope): description

Examples:

fix(hints): correct card resolution source feat(builder): emit
frame_tokens.runtime.json docs(governance): add AI governance model

Each commit should represent one logical change.

------------------------------------------------------------------------

## 15. Emergency Rule

If a change could:

-   break runtime
-   violate the constitution
-   change schema contracts
-   modify frozen phase architecture

Cursor must stop and report the issue.

------------------------------------------------------------------------

## 16. Summary

MandarinOS governance principles:

-   strategy separated from implementation
-   runtime stability protected
-   deterministic builders
-   small changes prevent drift
-   architecture decisions deliberate

Cursor must follow these rules when modifying the repository.
