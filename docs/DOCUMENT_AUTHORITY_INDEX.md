# MandarinOS Document Authority Index

## 1. Purpose and authority

This document classifies every tracked documentation file in the repository so that maintainers and AI coding agents can tell current authority from historical, supporting, evidentiary, proposed, or generated material.

This document:

- **is** the authority for **classifying** project documentation — the ninth authoritative R2 maintenance document (see §4);
- does **not** override verified code or the applicable detailed behavioural contracts — it ranks documents, it does not restate their behaviour;
- prevents historical and supporting documents from being mistaken for current authority merely because a filename sounds authoritative;
- governs document classification and staged documentation cleanup.

Application baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Application baseline tag: `architecture-baseline-2026-07-12-r2`

> A document's filename records what someone once called it. Its classification records what maintainers may rely on now.

## 2. Authority hierarchy

Highest to lowest:

1. verified production code and executable behaviour at the relevant baseline;
2. the nine-document approved R2 governance package (§4);
3. current repository configuration and content actually consumed by the application;
4. executable behavioural tests, interpreted according to `docs/TEST_STRATEGY.md`;
5. current supporting operational documentation that agrees with the above (§5);
6. dated reports, reviews, analyses, and recovery records (§7);
7. historical plans, phase documents, locks, briefings, and handoffs (§6, §8);
8. filenames, labels, comments, and unsupported statements of intent.

Explicit cautions:

- `LOCKED`, `FINAL`, `MASTER`, `APPROVED`, or `CURRENT` in a filename or heading is **not** proof of authority.
- A recently modified file may still describe an obsolete phase.
- A historical document may explain **why** a decision was once made without describing current behaviour.
- A passing static or mirrored test does not elevate the document it references.
- An implementation plan is not evidence that the plan was implemented.
- A report is evidence about a particular audit or date, not a permanent behavioural contract.
- Git history, modification dates, and commit messages are supporting evidence, not substitutes for code and approved contracts.

### Conflict rule

When two documents disagree:

1. verify the relevant code and executable behaviour;
2. consult the applicable approved R2 document (§4);
3. use this index to determine the other document's status;
4. treat unresolved conflict as a stop condition under `docs/CHANGE_CHECKLIST.md`.

## 3. Classification definitions

| Code | Classification | May guide current implementation? | May override an R2 document? | Normal maintenance action |
| ---- | -------------- | --------------------------------- | ---------------------------- | ------------------------- |
| A | Authoritative — approved R2 governance | Yes | No (subordinate only to verified code on factual drift) | Update/supersede via approved governance process |
| B | Current supporting guidance | Yes, within its narrow scope | No | Keep accurate; disclose partial obsolescence |
| C | Historical context — retained for rationale | No | No | Read with date/phase context; later candidate for header/archive |
| D | Superseded — replaced by identified authority | No | No | Preserve for traceability; later cleanup only with approval |
| E | Archival evidence or dated report | No | No | Do not rewrite to stay "current"; retain as dated evidence |
| F | Proposal, plan, or unimplemented specification | No as authority; verified-implemented portions may provide historical or design context only after confirmation against code and current R2 documents | No | Track implementation status; cross-reference ADR deferred register |
| G | Generated or procedural artefact | No | No | Regenerate or delete per its workflow |
| H | Unresolved — authority cannot yet be established | No | No | Investigate; do not rely on until resolved |

## 4. Approved R2 authority set

Nine documents — and only these nine — are approved class-A R2 governance documents. This index (`docs/DOCUMENT_AUTHORITY_INDEX.md`) is the ninth; the eight preceding behavioural and maintenance documents are unchanged. Together they form the approved nine-document R2 architecture-governance package.

The status strings below are copied from each document's own status line and were verified as identical (`Approved v1 — R2 baseline`), not assumed. All nine share application baseline commit `3be0315` and tag `architecture-baseline-2026-07-12-r2`.

| Document | Role | Status | Baseline / tag | Update trigger |
| -------- | ---- | ------ | -------------- | -------------- |
| `docs/ARCHITECTURE.md` | orientation map | `Approved v1 — R2 baseline` | `3be0315` / `architecture-baseline-2026-07-12-r2` | Any onboarding/system-orientation change |
| `docs/CONVERSATION_ARCHITECTURE.md` | conversation behavioural contract | `Approved v1 — R2 baseline` | `3be0315` / `architecture-baseline-2026-07-12-r2` | Selector/frame/engine/ordering change |
| `docs/STATE_CONTRACT.md` | state behavioural contract | `Approved v1 — R2 baseline` | `3be0315` / `architecture-baseline-2026-07-12-r2` | Any state field/transport/reset/persistence change |
| `docs/ANSWER_SOURCE_CONTRACT.md` | answer-source behavioural contract | `Approved v1 — R2 baseline` | `3be0315` / `architecture-baseline-2026-07-12-r2` | Priority chain/producer/finalisation change |
| `docs/ASR_PIPELINE.md` | ASR/input behavioural contract | `Approved v1 — R2 baseline` | `3be0315` / `architecture-baseline-2026-07-12-r2` | ASR/TTS/recovery-interception change |
| `docs/TEST_STRATEGY.md` | evidence contract | `Approved v1 — R2 baseline` | `3be0315` / `architecture-baseline-2026-07-12-r2` | Test architecture/evidence-ranking change |
| `docs/CHANGE_CHECKLIST.md` | operational change-control checklist | `Approved v1 — R2 baseline` | `3be0315` / `architecture-baseline-2026-07-12-r2` | Workflow/deployment/verification change |
| `docs/ARCHITECTURAL_DECISIONS.md` | architectural-decision record | `Approved v1 — R2 baseline` | `3be0315` / `architecture-baseline-2026-07-12-r2` | New/changed/superseded architectural decision |
| `docs/DOCUMENT_AUTHORITY_INDEX.md` | document-classification and cleanup authority | `Approved v1 — R2 baseline` | `3be0315` / `architecture-baseline-2026-07-12-r2` | New durable document; reclassification; supersession; archive move; duplicate consolidation; authority-set change |

ADR-017 was amended in the same approval change to recognise the nine-document R2 architecture-governance package.

## 5. Current supporting guidance (B)

Subordinate to the nine-document approved R2 governance package. None of these may override a behavioural contract or ADR.

| Path | Purpose | Why still current | Subordinate to | Known limitations | Secondary flags |
| ---- | ------- | ----------------- | -------------- | ----------------- | --------------- |
| `README.md` | Repo entry/quick-start | Start command, tech stack, key files still accurate | `docs/ARCHITECTURE.md` | Points to golden-regression test as primary; incomplete vs contracts | contains-current-material |
| `AI_CONTEXT.md` | AI orientation map | Project goal, guardrails, repo map still broadly valid | Nine-document R2 governance package | Header says "Authoritative"; "Phase 11" era; references superseded plan paths | mixed-current-and-historical, misleading-filename |
| `MANDARINOS_SYSTEM_MAP.md` | Pipeline mental model | Lexicon→builder→runtime→UI framing still useful | `docs/ARCHITECTURE.md` | "Authoritative" label; trace-contract framing is legacy (not wired to conversation runtime) | mixed-current-and-historical, misleading-filename |
| `docs/DEVELOPER_ONBOARDING.md` | Developer/hosting guide | Architecture, hosting, API overview broadly current | `docs/ARCHITECTURE.md`, `docs/CHANGE_CHECKLIST.md` | Dated 2026-05-11; specific test counts/line counts drift | contains-obsolete-material |
| `docs/MANDARINOS_REGRESSION_LOCK.md` | Protected-behaviour register | Records real regression guards + golden-regression suite | `docs/TEST_STRATEGY.md` | "LOCK" is not authority; interpret evidence per TEST_STRATEGY | misleading-filename, contains-current-material |
| `docs/RESPONSE_OPTION_STYLE_GUIDE.md` | Learner-option style rules | Current rules for response options | `docs/ANSWER_SOURCE_CONTRACT.md` | References a 2026-05 audit for open violations | contains-current-material |
| `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md` | Flow/anti-pattern design | Cited by `.cursor/rules` as read-first for flow changes | `docs/CONVERSATION_ARCHITECTURE.md` | Dated 2026-04-05; behaviour authority is the contract | contains-current-material |
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | Extensibility directive | Cited by `.cursor/rules` as full directive | `docs/ARCHITECTURAL_DECISIONS.md` | Canonical copy (a duplicate exists under `docs/briefings/`) | duplicate-or-near-duplicate |
| `docs/specs/MandarinOS_Extensibility_Strategy.md` | Extensibility strategy | Cited by `.cursor/rules` as strategy doc | `docs/ARCHITECTURAL_DECISIONS.md` | Strategy, not behavioural authority | contains-current-material |
| `docs/design/mandarinos_design_constitution.txt` | Product design constitution | Referenced as non-negotiable product philosophy | Nine-document R2 governance package | Older phrasing; philosophy retained, specifics may drift | mixed-current-and-historical |
| `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md` | AI governance model | Referenced by `AI_CONTEXT.md`/startup docs | Nine-document R2 governance package | v1; predates R2 governance package | contains-current-material |
| `docs/design/LICENSE.md` | Copyright/licence | Current legal statement | — | — | — |
| `runtime/README_runtime_indexes.txt` | Runtime-index definitions | Explains index defs vs computed outputs | `docs/ARCHITECTURE.md` §14 | Notes a legacy computed snapshot | contains-current-material |
| `conformance/README.md` | Conformance-runner usage | `conformance/run_trace_conformance.py` exists and runs | `docs/TEST_STRATEGY.md` | Trace conformance is a side tool, not wired into the conversation turn path | branch-specific |
| `requirements.txt` | Runtime dependency manifest | Consumed by install/deploy | repo configuration | Manifest, not governance prose | contains-current-material |
| `requirements-tools.txt` | Optional-tooling deps | Consumed for translation/pinyin tooling | repo configuration | Optional-only | contains-current-material |
| `.cursor/rules/mandarinos-architecture.mdc` | Standing architectural coding rules | Standing Cursor coding guidance, applied within its configured scope; agrees with contracts | `docs/ARCHITECTURAL_DECISIONS.md`, `docs/CONVERSATION_ARCHITECTURE.md` | Supporting agent guidance, subordinate to approved R2 documents; not proof of enforcement | contains-current-material |
| `.cursor/rules/mandarinos-ui-objects.mdc` | UI standard-object coding rules | Standing Cursor coding guidance, applied within its configured scope; matches `ui/app.js` render path | `docs/ARCHITECTURE.md` | Narrow UI-render scope; not proof of enforcement | contains-current-material |

Clarifications on non-prose entries in this table:

- `requirements.txt` and `requirements-tools.txt` are operative dependency manifests. Their runtime relevance derives from their status as current repository **configuration** consumed by install/deploy, not from class-B prose authority. Their B classification only reflects their inclusion in the documentation-like inventory and their current supporting role.
- `docs/design/LICENSE.md` governs legal use and distribution within its **legal scope** and sits outside the behavioural-implementation authority hierarchy. Classifying it B does not subordinate legal obligations to any architecture document; the authority hierarchy in §2 ranks implementation guidance and does not imply that application code overrides a licence.

## 6. Historical and superseded documents

Enumerated exhaustively in §17. This section states the classification basis and, for superseded files, the named replacement.

### 6.1 Historical context (C)

Retained for rationale; not current implementation guidance. Read with date/phase context.

| Family (see §17 for every path) | Members | Classification reason | Current authority | Secondary flags |
| ------------------------------- | ------- | --------------------- | ----------------- | --------------- |
| `docs/archive/briefings/*` strategist briefings (28; all class-C briefings relocated — C2C-core and C2C-review both approved) | 28 | Phase-era strategy/hand-off narratives | Nine-document R2 governance package | phase-specific, implementation-not-verified, duplicate-or-near-duplicate |
| `docs/archive/directives/*` cards/trace/harness directives (entry: `docs/directives/README.md`) | 17 | Phase 2–7 implementation directives | `docs/CHANGE_CHECKLIST.md`; code | phase-specific, implementation-not-verified |
| `docs/specs/*` engine/ladder/pack/model design specs | 38 | Design-phase specs; engines now live in code + contracts | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/ANSWER_SOURCE_CONTRACT.md` | phase-specific, misleading-filename |
| `docs/archive/phases/*` phase notes/freezes/locks (entry: `docs/phases/README.md`) | 11 | Phase milestones/locks | `docs/ARCHITECTURE.md`; ADRs | phase-specific, misleading-filename |
| `docs/archive/design-history/*` early design docs (C2D1 approved) | 6 | Cards/trace/UX design era | `docs/ARCHITECTURE.md` | phase-specific |
| `docs/project/*` notes/references/directive | 6 | Phase notes and reference material | Nine-document R2 governance package | phase-specific |
| `integration_kit/*` trace-export kit + examples | 5 | Trace/card kit not wired to current conversation runtime | `docs/ARCHITECTURE.md` | implementation-not-verified, phase-specific |
| `.github/copilot-instructions.md` | 1 | Copilot retired; Cursor operating instructions moved | `AI_CONTEXT.md`, `.cursor/rules/*`, `docs/CHANGE_CHECKLIST.md` §23 | contains-obsolete-material, misleading-filename |

### 6.2 Superseded documents (D)

Principal guidance replaced by a specific later authority.

| Path | Original purpose/phase | Classification reason | Current replacement/authority | Principal obsolete assumptions | Secondary flags |
| ---- | ---------------------- | --------------------- | ----------------------------- | ------------------------------ | --------------- |
| `docs/design/CURSOR_STARTUP_PROTOCOL.md` | Mandatory Cursor onboarding order | Onboarding sequence replaced | `docs/ARCHITECTURE.md` §21 + this index (§13) | Old read-first ordering (system map/constitution first) | misleading-filename |
| `docs/project/MANDARINOS_PROJECT_PLAN_v1.md` | Roadmap v1 | Explicitly superseded | `docs/project/MandarinOS_project_plan_v2.md` (F) | v1 phase plan | duplicate-or-near-duplicate |
| `docs/specs/MandarinOS_master_AI_bootstrap_context.md` | Master AI bootstrap briefing | Bootstrap role replaced | `AI_CONTEXT.md` | Copilot active; pre-R2 roadmap | misleading-filename |
| `docs/specs/mandarinos_conversation_architecture_v1.md` | Conversation architecture v1 | Conceptual spine superseded | `docs/CONVERSATION_ARCHITECTURE.md` | Pre-implementation engine template | — |
| `docs/specs/MandarinOS_conversation_runtime_model_v1.md` | Runtime conversation model | Runtime model superseded | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md` | Early runtime model | — |
| `docs/specs/MandarinOS_runtime_conversation_state_engine_v1.md` | Runtime state engine spec | State model superseded | `docs/STATE_CONTRACT.md` | Single-state-engine assumption | — |
| `docs/specs/MandarinOS_conversation_state_diagram_v1.md` | State diagram v1 | State model superseded | `docs/STATE_CONTRACT.md` | Early state diagram | — |
| `docs/specs/MandarinOS_turn_data_contract_v1.md` | Turn data contract v1 | Data/answer contract superseded | `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md` | Early turn payload shape | — |
| `docs/specs/MandarinOS_conversation_memory_model_v1.md` | Memory model v1 | Superseded by later version + contract | `docs/specs/MandarinOS_conversation_memory_model_v2.md` (C); authority `docs/STATE_CONTRACT.md` | Early memory schema | duplicate-or-near-duplicate |
| `docs/specs/mandarinos_family_conversation_ladder.md` | Family ladder v1 | Replaced by v2 | `docs/specs/mandarinos_family_conversation_ladder_v2.md` (C) | Early ladder ordering | duplicate-or-near-duplicate |

## 7. Reports and dated evidence (E)

Valid for their date and stated scope. **Not** rewritten to reflect later behaviour.

| Family (see §17 for every path) | Members | What it can support | What it cannot support | Retention value | Secondary flags |
| ------------------------------- | ------- | ------------------- | ---------------------- | --------------- | --------------- |
| `docs/reports/*` observations/audits/coverage | 10 | State of a named audit at its date | Current behavioural authority | Trend/coverage history | dated-snapshot |
| `docs/project/*` status/results/summaries/commit records | 12 | What a past fix/test/commit reported | Current behaviour or test pass state | Recovery/commit traceability | dated-snapshot |
| `docs/briefings/*` audits/reviews/assessments | 8 | Findings at review date | Current design authority | Rationale for later changes | dated-snapshot |
| `docs/specs/*audit*` architecture/translation audits | 4 | Audit findings at their date | Current contract wording | Pre-R2 audit trail | dated-snapshot |
| `docs/state/MANDARINOS_SYSTEM_STATE_PHASE_12B.md` | 1 | System state at Phase 12B | Current state model | Historical snapshot | dated-snapshot, misleading-filename |
| `docs/session_intelligence_implementation_report.md` | 1 | Session-intelligence slice implementation report | Current session behaviour | Implementation record | dated-snapshot |

## 8. Proposals and unimplemented specifications (F)

A proposal is not current guidance, even when part of it was implemented. A verified-implemented portion may provide historical or design context only after confirmation against code and the approved R2 documents. Implementation is not inferred from status language.

| Family (see §17 for every path) | Members | Implementation status | Current decision/ADR | Secondary flags |
| -------------------------------- | ------- | --------------------- | -------------------- | --------------- |
| `docs/plans/*` implementation plans | 3 | Unable to verify from docs; treat as planned | `docs/ARCHITECTURAL_DECISIONS.md` §6 register | implementation-not-verified |
| `docs/project/MandarinOS_project_plan_v2*.md` roadmaps | 3 | v2 is the latest named roadmap version in that family; not implementation authority; implemented status must be verified against code and the approved R2 documents; `_CORRECTED`/`_UPDATED` are variants | ADR record for decisions | duplicate-or-near-duplicate, implementation-not-verified |
| `docs/specs/PHASE_10_5_*`, `PHASE_12C_*` plans/briefs/invariants | 4 | Partially implemented across phases; not verified per item | Contracts; ADR deferred register | partially-implemented, implementation-not-verified |
| `docs/specs/*UI_SPEC*`, `*Hybrid_Speech*` specs | 3 | Hybrid speech deferred (ADR-014/ADR-009); UI specs partial | `docs/ASR_PIPELINE.md`; ADR-014 | implementation-not-verified |
| `docs/phases/*PROPOSAL*/*PLAN*/*MAPPING*` | 3 | Planning artefacts; subset implemented | Contracts; ADRs | implementation-not-verified |
| `docs/design/SCENARIOS_REQUIRED_v1.md`, `MANDARINOS_PHASE_12_HYBRID_AI_CONCEPT_BRIEFING.txt` | 2 | Scenarios/hybrid concept; hybrid unimplemented | ADR-014 (deferred) | implementation-not-verified |
| `docs/REPO_STRUCTURE_PROPOSAL.md`, `docs/SCHEMA_SYNC_RECOMMENDATION.md`, `docs/session_intelligence_architecture.md` | 3 | Not executed / partially (session slice 1) | — | implementation-not-verified, partially-implemented |
| `docs/project/RECOVERY_AND_CONVERSATION_FUTURE_NOTES.md` | 1 | Forward-looking notes | ADR deferred register | implementation-not-verified |

Family totals: 3 + 3 + 4 + 3 + 3 + 2 + 3 + 1 = **22**, equal to the class-F total in §18.

## 9. Generated and procedural artefacts (G)

Useful only for their producing workflow; never authority.

| Path or file family | Producing workflow | Intended lifespan | Regeneration/source | Maintenance treatment |
| ------------------- | ------------------ | ----------------- | ------------------- | --------------------- |
| `server_out.txt`, `server_err.txt`, `server_startup_err.txt` | Captured server stdout/stderr | Ephemeral | Re-run server | Ignore; safe to delete/regenerate |
| `fo_check.txt` | Captured shell/python run output | Ephemeral | Re-run the command | Ignore; safe to delete |
| `frame_dump.txt`, `frame_texts.txt` | Frame-order/text dump scripts | Ephemeral | Re-run dump | Regenerate on demand |
| `scripts/_engine_audit.txt` | Engine/frame audit script output | Ephemeral | Re-run audit | Regenerate on demand |
| `tools/coverage/coverage_report.md` | Content coverage scanner | Per-scan | Re-run scanner | Regenerate; not authority |
| `docs/project/CHATGPT_BRANCH_START_TEMPLATE.md`, `docs/project/COMMIT_INSTRUCTIONS.md` | Workflow templates | Procedural | Edit as workflow changes | Procedural only |
| `docs/Social_Media/*` marketing decks/scripts/templates | Marketing collateral workflow | Campaign-scoped | Marketing process | Not governance; out of maintenance scope |

## 10. Unresolved register (H)

`No unresolved document-authority classifications remained after the R2 audit.`

Every tracked file in scope received a primary classification supported by repository evidence. Where evidence was mixed, a `Classification inference:` note is recorded in the relevant §17 row rather than deferring the file to H.

## 11. Misleading-title register

Tracked files whose name or prominent heading implies authority that the file does not hold.

| Path | Misleading label | Actual classification | Why the label is insufficient | Current authority |
| ---- | ---------------- | --------------------- | ----------------------------- | ----------------- |
| `AI_CONTEXT.md` | "Authoritative" (heading) | B | Orientation map, subordinate to the approved R2 governance documents | `docs/ARCHITECTURE.md` |
| `MANDARINOS_SYSTEM_MAP.md` | "Authoritative" (heading) | B | Pipeline map; trace framing legacy | `docs/ARCHITECTURE.md` |
| `docs/MANDARINOS_REGRESSION_LOCK.md` | `LOCK` | B | Behaviour register, not authority; evidence per TEST_STRATEGY | `docs/TEST_STRATEGY.md` |
| `docs/archive/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` | `LOCK` | C | Phase 6 lock, superseded by R2 architecture | `docs/ARCHITECTURE.md` |
| `docs/archive/phases/PHASE6_FREEZE.md` | `FREEZE` | C | Phase 6 freeze snapshot | `docs/ARCHITECTURE.md` |
| `docs/specs/MandarinOS_master_AI_bootstrap_context.md` | `master` | D | Bootstrap role replaced | `AI_CONTEXT.md` |
| `docs/specs/MandarinOS_next_question_selector_v1.md` | `LOCKED` (heading) | C | Design spec; selector logic lives in code + contract | `docs/CONVERSATION_ARCHITECTURE.md` |
| `docs/specs/MandarinOS_capability_update_rules_v1.md` | `LOCKED` (heading) | C | Design spec; behaviour authority is code + contract | `docs/CONVERSATION_ARCHITECTURE.md` |
| `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` | Marks specs `LOCKED` | C | Index of design specs, not current authority | `docs/ARCHITECTURE.md` |
| `docs/design/CURSOR_STARTUP_PROTOCOL.md` | "Status: ACTIVE" | D | Onboarding order superseded | `docs/ARCHITECTURE.md` §21 |
| `docs/state/MANDARINOS_SYSTEM_STATE_PHASE_12B.md` | "Constraints (LOCKED)" | E | Dated state snapshot | `docs/STATE_CONTRACT.md` |
| `.github/copilot-instructions.md` | Filename presents current-looking instructions | C | Instructions for a retired tool (Copilot); not current operating authority | `docs/CHANGE_CHECKLIST.md` §23; `AI_CONTEXT.md`; `.cursor/rules/` within their supporting scope |

## 12. Duplicate and overlap register

No file is deleted or merged in this phase.

| Documents | Relationship | Canonical/current file | Classification of others | Future cleanup action |
| --------- | ------------ | ---------------------- | ------------------------ | --------------------- |
| `docs/project/MANDARINOS_PROJECT_PLAN_v1.md`, `MandarinOS_project_plan_v2.md`, `_v2_CORRECTED.md`, `_v2_UPDATED.md` | Roadmap versions/variants | `MandarinOS_project_plan_v2.md` (latest named version in the family; class F, not R2 authority; does not supersede the R2 governance package) | v1 = D; CORRECTED/UPDATED = F | Consolidate to one roadmap after owner review |
| `docs/project/COMMIT_SUMMARY.md`, `COMMIT_SUMMARY_v1.md` | Dated commit summaries | Neither (both dated) | Both E | Retain as dated evidence |
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md`, `docs/briefings/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | Identical copies | `docs/specs/…` (cited by `.cursor/rules`) | specs = B; briefings copy = C | Remove/redirect duplicate after link check |
| `docs/specs/MandarinOS_conversation_memory_model_v1.md`, `_v2.md` | Version pair | v2 | v1 = D; v2 = C | Authority is `docs/STATE_CONTRACT.md` |
| `docs/specs/mandarinos_family_conversation_ladder.md`, `_v2.md` | Version pair | v2 | v1 = D; v2 = C | — |
| `docs/archive/phases/MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md`, `docs/archive/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md` | Near-duplicate | Neither current | Both C | De-duplicate after review |
| `docs/Social_Media/mandarinos-marp-template.md`, `mandarinos-marp-template 1.md` | Duplicate template | `mandarinos-marp-template.md` | Both G | Remove the " 1" copy |
| `docs/specs/mandarinos_conversation_architecture_v1.md`, `MandarinOS_conversation_system_blueprint_v1.md`, `MandarinOS_conversation_runtime_model_v1.md` | Overlap current conversation contract | `docs/CONVERSATION_ARCHITECTURE.md` | v1/blueprint/runtime = D/C | Archive after R2 stability |
| `AI_CONTEXT.md`, `MANDARINOS_SYSTEM_MAP.md`, `docs/specs/MandarinOS_master_AI_bootstrap_context.md` | Overlapping orientation maps | `docs/ARCHITECTURE.md` | AI_CONTEXT/SYSTEM_MAP = B; bootstrap = D | Point orientation maps at ARCHITECTURE |

## 13. Developer entry path

This section is the operational entry path for maintainers and AI coding agents. It does not create a second authority hierarchy — see §2.

### Starting sequence (nine class-A documents)

1. `docs/DOCUMENT_AUTHORITY_INDEX.md` (this document) — classify before relying.
2. `docs/ARCHITECTURE.md` — system orientation map.
3. `docs/CONVERSATION_ARCHITECTURE.md` — conversation behavioural contract.
4. The detailed behavioural contracts for your subsystem: `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md`, `docs/ASR_PIPELINE.md`.
5. `docs/TEST_STRATEGY.md` — evidence contract.
6. `docs/CHANGE_CHECKLIST.md` — change-control checklist.
7. `docs/ARCHITECTURAL_DECISIONS.md` — architectural decision record.

Steps 1–7 are the nine-document approved R2 governance package (§4). Read class-B supporting guidance (§5) only after this sequence, and only when subordinate to verified code and the applicable class-A document.

### Maintenance decision table

| Maintenance question | Start with | Then verify |
| -------------------- | ---------- | ----------- |
| Overall system structure | `docs/ARCHITECTURE.md` | current code and ADRs |
| Conversation routing and engine behaviour | `docs/CONVERSATION_ARCHITECTURE.md` | server/UI code and tests |
| State and memory behaviour | `docs/STATE_CONTRACT.md` | persistence and turn-state code |
| Answer source and persona behaviour | `docs/ANSWER_SOURCE_CONTRACT.md` | content, persona, and routing code |
| ASR behaviour | `docs/ASR_PIPELINE.md` | ASR code and tests |
| Regression and test requirements | `docs/TEST_STRATEGY.md` | test suite |
| Making a change safely | `docs/CHANGE_CHECKLIST.md` | relevant subsystem contracts |
| Why an architectural choice exists | `docs/ARCHITECTURAL_DECISIONS.md` | current code |
| Documentation status or authority | `docs/DOCUMENT_AUTHORITY_INDEX.md` | §17 inventory |

### Family guidance (Phase B5B)

Before opening individual files in these historical families, read the approved family guides:

- [`docs/directives/README.md`](directives/README.md) — 17 phase directives (archived at `docs/archive/directives/`).
- [`docs/phases/README.md`](phases/README.md) — 11 phase milestone documents (archived at `docs/archive/phases/`).
- [`integration_kit/README.md`](../integration_kit/README.md) — 5 trace-kit files.

These guides control directory entry without reclassifying underlying documents.

### Generated-output warning

Files with the `generated-guidance-added` secondary flag (§17) are captured or tool-generated outputs. Regenerate through the producing workflow (Phase B5C). Do not treat them as behavioural authority or edit them as primary sources.

### Phase B5D integration set (46 documents)

Forty-six previously unnotified documents are covered by bounded onboarding and authority-path integration (approved `docs/PHASE_B5_SCOPE_ASSESSMENT.md` §13.2). **They were not modified, reclassified, or given individual notices.** Linking here does not grant class-A or class-B authority.

| Subsystem / family | Files | Class mix | Principal caution |
| ------------------ | ----- | --------- | ----------------- |
| Repo entry, Cursor rules, specs supporting, runtime indexes | 11 | B | Subordinate to §4 contracts and verified code |
| `docs/briefings/` + `docs/archive/briefings/` strategist briefings | 28 | C | Historical context; E audits remain in `docs/briefings/`; all 28 C briefings now relocated to `docs/archive/briefings/` (20 + 8, both batches approved) |
| `docs/archive/design-history/` early design | 5 | C | Pre-R2 design era; relocated in approved Phase C2D1 (`TRACE_CONTRACT_v1.md` is the sixth C2D1 class-C file, with Phase B5A notice — see §17.3a) |
| `docs/project/` procedural templates | 2 | G | Workflow templates, not generated dumps |

### 13.1 Phase B5D onboarding integration set (46)

Each path appears exactly once. Full disposition authority: `docs/PHASE_B5_SCOPE_ASSESSMENT.md` §13.2.

| Path | Class | Family | Governing authority | Onboarding use | Principal caution |
| ---- | ----- | ------ | ------------------- | -------------- | ----------------- |
| `.cursor/rules/mandarinos-architecture.mdc` | B | repo entry / Cursor / specs supporting | `docs/ARCHITECTURAL_DECISIONS.md` | supporting reference | Subordinate to class-A and verified code |
| `.cursor/rules/mandarinos-ui-objects.mdc` | B | repo entry / Cursor / specs supporting | `docs/ARCHITECTURE.md` | supporting reference | Subordinate to class-A and verified code |
| `README.md` | B | repo entry / Cursor / specs supporting | — | supporting reference | Subordinate to class-A and verified code |
| `conformance/README.md` | B | repo entry / Cursor / specs supporting | `docs/TEST_STRATEGY.md` | supporting reference | Subordinate to class-A and verified code |
| `docs/RESPONSE_OPTION_STYLE_GUIDE.md` | B | repo entry / Cursor / specs supporting | `docs/ANSWER_SOURCE_CONTRACT.md` | supporting reference | Subordinate to class-A and verified code |
| `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md` | B | repo entry / Cursor / specs supporting | Nine-document R2 governance package | supporting reference | Subordinate to class-A and verified code |
| `docs/design/mandarinos_design_constitution.txt` | B | repo entry / Cursor / specs supporting | Nine-document R2 governance package | supporting reference | Subordinate to class-A and verified code |
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | B | repo entry / Cursor / specs supporting | ADR record | supporting reference | Subordinate to class-A and verified code |
| `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md` | B | repo entry / Cursor / specs supporting | `docs/CONVERSATION_ARCHITECTURE.md` | supporting reference | Subordinate to class-A and verified code |
| `docs/specs/MandarinOS_Extensibility_Strategy.md` | B | repo entry / Cursor / specs supporting | ADR record | supporting reference | Subordinate to class-A and verified code |
| `runtime/README_runtime_indexes.txt` | B | repo entry / Cursor / specs supporting | `docs/ARCHITECTURE.md` §14 | supporting reference | Subordinate to class-A and verified code |
| `docs/archive/briefings/BRIEFING_CHANGES_FOR_CHATGPT_REVIEW.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/CHATGPT_STRATEGIST_CONVERSATION_DESIGN_BRIEFING.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | C | docs/archive/briefings/ strategist briefing | `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/MANDARINOS_PHASE_10_7_PHASE_11_BRIEFING.txt` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/MandarinOS_Phase12D_Cursor_Implementation_Brief.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/MandarinOS_Phase12E_CuriosityProbe_Brief.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/MandarinOS_Phase_12C_Alignment_Brief.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/MandarinOS_laptop_handoff_UI_cascading_help_briefing.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/NEXT_PHASE_ADVICE_CURSOR.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/PHASE10_STRATEGIST_BRIEFING_SPECS_GAP_AND_PATH.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/PHASE7_4_UI_POLISH_STRATEGIST_BRIEFING.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/PHASE7_COMPLETE_STRATEGIST_BRIEFING.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/PHASE8_OPTIONS_APPROPRIATENESS.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/PHASE8_STEP1_TRANSCRIPT_ARCHITECTURE.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/PHASE9_SIGNOFF_STRATEGIST_BRIEFING.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/PHASE_10_5_10_6_ALPHA_STRATEGIST_BRIEFING.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/PHASE_12B_STABILIZATION_AND_UI_FLOW_STRATEGIST_BRIEFING.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/PHASE_12C_EXECUTIVE_STRATEGIST_BRIEF.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/PHASE_12C_STRATEGIST_PROPOSAL_CURIOSITY_PERSONA_SESSION_ARC.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/STRATEGIST_BRIEFING_MAY2026_UI_POLISH_AND_DISTANCE_THREAD.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/UI_SHELL_STRATEGIST_BRIEFING_APR2026.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/USER_LED_DISCOVERY_STRATEGIST_BRIEF.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/architecture_briefing_apr2026.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/mandarinos_chatgpt_session_briefing.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/mandarinos_recovery_phrases_v1_2_cursor_briefing.txt` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/phase12c_recovery_trigger_briefing.txt` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/briefings/phase7_3_senior_architect_briefing.md` | C | docs/archive/briefings/ strategist briefing | R2 governance set | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/design-history/CARDS_BUILD_v1.md` | C | docs/archive/design-history/ early design | `docs/ARCHITECTURE.md` | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/design-history/MandarinOS Developer Handoff.txt` | C | docs/archive/design-history/ early design | `docs/DEVELOPER_ONBOARDING.md` | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/design-history/MandarinOS_brief.md` | C | docs/archive/design-history/ early design | `docs/ARCHITECTURE.md` | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/design-history/p3_architecture.md` | C | docs/archive/design-history/ early design | `docs/ARCHITECTURE.md` | historical context | Phase-era narrative; does not authorise changes |
| `docs/archive/design-history/ux_flow.txt` | C | docs/archive/design-history/ early design | `docs/ARCHITECTURE.md` | historical context | Phase-era narrative; does not authorise changes |
| `docs/project/CHATGPT_BRANCH_START_TEMPLATE.md` | G | docs/project/ procedural | — | procedural template | Authored template; not behavioural authority |
| `docs/project/COMMIT_INSTRUCTIONS.md` | G | docs/project/ procedural | — | procedural template | Authored template; not behavioural authority |

An AI coding agent must **not** begin from a historical phase lock, briefing, or recovery report. It must diagnose against verified code and the nine-document approved R2 governance package, and treat everything in §6–§9 as context or evidence, never as behavioural authority.

Supporting walkthrough: `docs/DEVELOPER_ONBOARDING.md` §Documentation authority and safe starting path.

## 14. Rules for creating future documents

Every future durable document must declare:

- title;
- purpose;
- owner or responsible role;
- status;
- behavioural/application baseline;
- last verified date;
- relationship to the nine-document R2 governance package;
- supersedes/superseded-by links where applicable;
- whether it is prescriptive, evidentiary, historical, or a proposal.

Rules:

- new behavioural authority should normally **update an existing contract** rather than create a competing one;
- a new ADR is required for a changed architectural decision;
- reports must include their evidence date and scope;
- proposals must state whether implementation is verified;
- generated artefacts must identify their source and regeneration process;
- a document must not claim authority merely through its filename or a `LOCKED`/`FINAL`/`MASTER` label.

## 15. Future cleanup plan

Defined here; **not** executed by this draft.

### Phase A — authority index
This task: create the classification authority and inventory.

### Phase B — status headers

**Phase B — documentation authority and risk-control programme: Complete — approved 2026-07-14.**

Add standard headers to historical (C), superseded (D), proposal (F), and report (E) files, and to high-risk misleading-titled current (B) files.

Standard: notices use the `MANDARINOS-DOCUMENT-STATUS:BEGIN`/`:END` sentinel pair; each notice states the document's classification, current use, whether it may guide current implementation, the current replacement/authority, the principal caution, and the classification source and dates. Original body content must remain unchanged beneath the notice. Notices are placed immediately after required front matter, or otherwise at the very start of the file. No file receives more than one notice. Phase B may be performed in reviewed batches rather than as a single pass.

**Phase B1 — high-risk misleading-title set: 12 files — approved 2026-07-14.** Class breakdown: B 3 (`AI_CONTEXT.md`; `MANDARINOS_SYSTEM_MAP.md`; `docs/MANDARINOS_REGRESSION_LOCK.md`); C 6 (`docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`; `docs/phases/PHASE6_FREEZE.md`; `docs/specs/MandarinOS_next_question_selector_v1.md`; `docs/specs/MandarinOS_capability_update_rules_v1.md`; `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`; `.github/copilot-instructions.md`); D 2 (`docs/specs/MandarinOS_master_AI_bootstrap_context.md`; `docs/design/CURSOR_STARTUP_PROTOCOL.md`); E 1 (`docs/state/MANDARINOS_SYSTEM_STATE_PHASE_12B.md`). Phase B1 is complete: no historical body content was altered, and all 12 notices use the standard sentinel protocol verified against committed Git blobs. Phase B as a whole is **not** complete — later Phase B batches (further C/D/E/F files) remain separately reviewed and controlled.

**Phase B2 — remaining superseded-document set: 8 files — approved 2026-07-14.** Class breakdown: D 8 (`docs/project/MANDARINOS_PROJECT_PLAN_v1.md`; `docs/specs/mandarinos_conversation_architecture_v1.md`; `docs/specs/MandarinOS_conversation_runtime_model_v1.md`; `docs/specs/MandarinOS_runtime_conversation_state_engine_v1.md`; `docs/specs/MandarinOS_conversation_state_diagram_v1.md`; `docs/specs/MandarinOS_turn_data_contract_v1.md`; `docs/specs/MandarinOS_conversation_memory_model_v1.md`; `docs/specs/mandarinos_family_conversation_ladder.md`). Phase B2 is approved and complete: all ten class-D documents now carry approved authority notices, using the standard sentinel protocol, verified against committed Git blobs. No original document body was altered. Phase B1 remains approved. Phase B as a whole remains incomplete — later Phase B batches (class C, E, F, and G files) remain separately reviewed and controlled.

**Phase B3A — roadmap and planning class-F set: 11 files — approved 2026-07-14.** Class breakdown: F 11 (`docs/phases/PHASE10_TECHNICAL_PROPOSAL.md`; `docs/phases/PHASE9_CONTENT_AND_ENGINES_PLAN.md`; `docs/phases/PHASE_10_5_MAPPING_AND_SCHEMA_PROPOSAL.md`; `docs/plans/PHASE_10_7_MINIMAL_IMPLEMENTATION_PLAN.md`; `docs/plans/component_radical_gloss_plan.md`; `docs/plans/learner_etymology_hints_plan.md`; `docs/project/MandarinOS_project_plan_v2.md`; `docs/project/MandarinOS_project_plan_v2_CORRECTED.md`; `docs/project/MandarinOS_project_plan_v2_UPDATED.md`; `docs/project/RECOVERY_AND_CONVERSATION_FUTURE_NOTES.md`; `docs/REPO_STRUCTURE_PROPOSAL.md`). Phase B3A is approved and complete: all 11 Phase B3A roadmap and planning documents now carry approved authority notices, using the standard sentinel protocol, verified against committed Git blobs. No original document body was altered.

**Phase B3B — design and implementation-specification class-F set: 11 files — approved 2026-07-14.** Class breakdown: F 11 (`docs/SCHEMA_SYNC_RECOMMENDATION.md`; `docs/session_intelligence_architecture.md`; `docs/design/SCENARIOS_REQUIRED_v1.md`; `docs/design/MANDARINOS_PHASE_12_HYBRID_AI_CONCEPT_BRIEFING.txt`; `docs/specs/MandarinOS_Hybrid_Speech_and_Persona_Voice_Architecture.md`; `docs/specs/PHASE_10_5_BEHAVIOUR_IMPLEMENTATION_PLAN.md`; `docs/specs/PHASE_10_5_INTEREST_RESPONSIVENESS_REFINEMENT_PLAN.md`; `docs/specs/PHASE_12C_IMPLEMENTATION_BRIEF.md`; `docs/specs/PHASE_12C_INVARIANTS.md`; `docs/specs/MOBILE_WORD_INSIGHT_UI_SPEC.md`; `docs/specs/TRANSCRIPT_REPLAY_TRANSLATION_UI_SPEC.md`). Phase B3B is approved and complete: all 11 Phase B3B documents now carry approved authority notices, using the standard sentinel protocol, verified against committed Git blobs. No original document body was altered. No class-F proposal was implemented, elevated, or reclassified. All 22 class-F documents now carry approved authority notices. Phase B1, Phase B2, and Phase B3A remain approved. Phase B as a whole remains incomplete — later Phase B batches remain separately reviewed and controlled.

**Phase B3 — all class-F proposals, plans, and unimplemented specifications: 22 files — complete and approved through Phase B3A and Phase B3B on 2026-07-14.** Split: Phase B3A 11; Phase B3B 11; total 22. Phase B3 completion changes no primary classification and authorises no proposal implementation. Phase B as a whole remains incomplete.

**Phase B4A — project status, validation, summary, and commit-record class-E set: 12 files — approved 2026-07-14.** Class breakdown: E 12 (`docs/project/ARCHITECTURE_ALIGNMENT_OPTIONS_AND_GOLD.md`; `docs/project/AUDIT_OPTION_GENERATION.md`; `docs/project/COMMIT_RECORD.md`; `docs/project/COMMIT_SUMMARY.md`; `docs/project/COMMIT_SUMMARY_v1.md`; `docs/project/CORE_TREASURE_BRIDGE_STATUS.md`; `docs/project/DIAGNOSTIC_P1_VALIDATION_RESULTS.md`; `docs/project/EXECUTIVE_SUMMARY_v1.md`; `docs/project/OPTION_GENERATION_FIX_COMPLETE.md`; `docs/project/PHASE9_STATUS_AND_RESPONSE_QUALITY.md`; `docs/project/SPECS_TO_IMPLEMENTATION_GAP.md`; `docs/project/TEST_SUMMARY.md`). Phase B4A is approved and complete: all 12 Phase B4A project-evidence documents now carry approved authority notices, using the standard sentinel protocol, verified against committed Git blobs. No original report body was altered. Historical conclusions were neither updated nor endorsed. One additional class-E document was previously approved in Phase B1 (`docs/state/MANDARINOS_SYSTEM_STATE_PHASE_12B.md`). 23 class-E documents remain for Phase B4B–B4D. Phase B1, Phase B2, Phase B3A, Phase B3B, and Phase B3 remain approved/complete as recorded above. Phase B4 remains incomplete. Phase B as a whole remains incomplete — later Phase B batches remain separately reviewed and controlled.

**Phase B4B — reports-directory class-E historical-evidence set: 10 files — approved 2026-07-14.** Class breakdown: E 10 (`docs/reports/CORPUS_RECOVERY_NOTES.md`; `docs/reports/PHASE_11_1_1_OBSERVATION_REPORT.md`; `docs/reports/alpha_conversation_observation.md`; `docs/reports/capability_mismatch_observation.md`; `docs/reports/component_gloss_coverage.md`; `docs/reports/counter_reply_matrix_report.md`; `docs/reports/move_type_tagging_audit.md`; `docs/reports/move_type_tagging_coverage.md`; `docs/reports/move_type_transition_calibration.md`; `docs/reports/vocab_character_coverage_audit.md`). Phase B4B is approved and complete: all 10 class-E files under `docs/reports/` now carry approved authority notices, using the standard sentinel protocol, verified against committed Git blobs. No original report body was altered. Historical findings were neither updated nor endorsed. 23 class-E documents now carry approved notices (one Phase B1; 12 Phase B4A; 10 Phase B4B). 13 class-E documents remain for Phase B4C and Phase B4D. Phase B4 covers all class-E dated reports and historical evidence and remains incomplete. Phase B as a whole remains incomplete.

**Phase B4C — briefing audits, reviews, assessments, and discoveries class-E set: 8 files — approved 2026-07-14.** Class breakdown: E 8 (`docs/briefings/bridge_audit_apr2026.md`; `docs/briefings/engine_audit_apr2026.md`; `docs/briefings/implementation_report_apr2026.md`; `docs/briefings/PHASE7_COMPLETION_REVIEW_AND_TEST.md`; `docs/briefings/PHASE10_STRATEGIST_REVIEW.md`; `docs/briefings/CONVERSATION_ARCHITECTURE_ASSESSMENT.md`; `docs/briefings/UI_CONVERSATION_LOOP_ASSESSMENT.md`; `docs/briefings/PHASE7_SCHEMA_DISCOVERIES.md`). Phase B4C is approved and complete: all eight class-E files under `docs/briefings/` now carry approved authority notices, using the standard sentinel protocol, verified against committed Git blobs. No original briefing body was altered. Historical findings were neither updated nor endorsed. 31 class-E documents now carry approved notices (one Phase B1; 12 Phase B4A; 10 Phase B4B; eight Phase B4C). Five class-E documents remain for Phase B4D. Phase B4 covers all class-E dated reports and historical evidence and remains incomplete. Phase B as a whole remains incomplete.

**Phase B4D — final specification-audit and implementation-report class-E set: 5 files — approved 2026-07-14.** Class breakdown: E 5 (`docs/session_intelligence_implementation_report.md`; `docs/specs/MANDARINOS_CONVERSATION_ARCHITECTURE_AUDIT_v1.md`; `docs/specs/MandarinOS_conversation_expansion_audit_v2.md`; `docs/specs/Translation_Surface_Consistency_Audit.md`; `docs/specs/mandarinos_conversation_architecture_audit_request_v2.txt`). Phase B4D is approved and complete: all five final class-E documents now carry approved authority notices, using the standard sentinel protocol, verified against committed Git blobs. No original historical body was altered. No audit finding, request, recommendation, or implementation claim was updated or endorsed.

**Phase B4 — all class-E dated reports and historical-evidence documents: 36 files — complete and approved through Phase B1 and Phase B4A–B4D on 2026-07-14.** Coverage: Phase B1 class-E file 1; Phase B4A 12; Phase B4B 10; Phase B4C 8; Phase B4D 5; total 36. All 36 class-E documents now carry approved authority notices. Phase B4 is complete. Phase B as a whole remains incomplete. Phase B4 completion changes no primary classification, does not endorse historical findings, and authorises no implementation or remediation work.

**Phase B5 — remaining class-B, class-C, and class-G risk and scope assessment — approved 2026-07-14.** The assessment is approved. No status notices were added. No existing primary classification changed. No existing secondary flag changed. The new assessment file (`docs/PHASE_B5_SCOPE_ASSESSMENT.md`) is class E dated evidence. Remediation has not begun. Approved recommendations are recorded in `docs/PHASE_B5_SCOPE_ASSESSMENT.md`. Phase B remains incomplete.

**Phase B5A — approved-assessment individual-notice set: 2 files — approved 2026-07-14.** Class breakdown: B 1 (`docs/DEVELOPER_ONBOARDING.md`); C 1 (`docs/design/TRACE_CONTRACT_v1.md`). Phase B5A is approved and complete. Both approved high-risk individual notices authorised by the approved Phase B5 scope assessment are in place. `docs/DEVELOPER_ONBOARDING.md` remains class B supporting documentation. `docs/design/TRACE_CONTRACT_v1.md` remains class C historical/contextual documentation. No original document body was altered. No primary classification changed. Phase B5B, B5C, and B5D have not begun. Phase B remains incomplete.

**Phase B5B — approved-assessment family and directory guidance: 3 guides covering 31 files — approved 2026-07-14.** Coverage: `docs/directives/` 17; `docs/phases/` 9; `integration_kit/` 5; total 31. Phase B5B is approved and complete. Two new class-B family guides were created (`docs/directives/README.md`; `docs/phases/README.md`). The existing class-C `integration_kit/README.md` hosts a prepended family-authority wrapper while retaining its class and flags. No covered historical document was reclassified. No individual notice was added. No covered historical body was altered. Phase B5C is approved. Phase B remains incomplete.

**Phase B5C — approved-assessment generated-output guidance: 8 files — approved 2026-07-14.** Phase B5C is approved and complete. All eight approved generated or captured outputs carry maintenance guidance. The headers identify output status, regeneration expectations, freshness risk, and direct-edit risk. No output was regenerated. No original output body was altered. No target was reclassified. `generated-guidance-added` applies to exactly eight files. Phase B5D has not begun. Phase B remains incomplete.

**Phase B5D — approved-assessment onboarding and authority-path integration: 46 files — approved 2026-07-14.** Phase B5D is approved and complete. Forty-six documents (class breakdown: B 11; C 33; G 2) are mapped into the approved authority path via §13 and `docs/DEVELOPER_ONBOARDING.md`. None of the 46 target documents was modified. No individual notice was added. No document was reclassified. No secondary flag changed. The four navigation files (`AI_CONTEXT.md`; `docs/ARCHITECTURE.md`; `docs/DEVELOPER_ONBOARDING.md`; `docs/DOCUMENT_AUTHORITY_INDEX.md`) implement the approved entry route. Phase B5A, B5B, B5C, and B5D are approved. Phase B closeout has not begun. Phase B remains incomplete.

**Phase B5 remediation programme (B5A–B5D) — approved batches complete 2026-07-14.** Approved remediation through the Phase B5 scope assessment consists of: B5A — 2 individual notices; B5B — 3 family guides covering 31 files; B5C — generated-output guidance on 8 files; B5D — authority-path integration covering 46 files. Formal Phase B closeout remains required before Phase B may be marked complete. Phase B remains incomplete.

**Phase B closeout — documentation authority and risk-control programme — approved and complete 2026-07-14.** Phase B1 through Phase B5D are approved. All closeout checks passed. Phase B is complete. Inventory total: 230. Approved status notices: 79. Approved generated-output guidance headers: 8. Family guides: 3 covering 31 files. B5D authority-path integration: 46 files. No-action disposition: 54. Already protected (Phase B1): 9. The documentation authority system is operational: primary authority is defined by the nine class-A documents; high-risk historical and superseded documents are notice-controlled; all class-D and class-F documents carry approved notices; all 36 pre-existing class-E evidence documents carry approved notices; the two remaining high-risk B/C files from B5A are notice-protected; three family guides control entry into 31 historical-family documents; eight generated outputs carry direct-edit and freshness guidance; 46 documents are integrated into the onboarding authority path. No further Phase B file-level remediation is authorised. Future changes must follow `docs/CHANGE_CHECKLIST.md`. Future governance work requires a separately approved phase.

### Phase C — physical archive

**Phase C1 — historical-document dependency audit and archival plan — approved 2026-07-14.** Phase B remains complete. Phase C1 is approved. The approved relocation plan is recorded in `docs/PHASE_C1_ARCHIVAL_AUDIT.md`. The assessment is dated evidence, not standing implementation authority. No file was moved, renamed, deleted, reclassified, or reflagged during Phase C1 itself.

**Phase C2A — historical directives relocation: 17 files — approved 2026-07-14.** Phase C2A is approved and complete. Seventeen class-C directive files moved from `docs/directives/` to `docs/archive/directives/` via `git mv`. `docs/directives/README.md` remains the compatibility and authority entry point. All 17 bodies are byte-identical to the approved baseline (`94dc5ad5a3d09d4c1120505c98d5a56e312a0dbe`). Classes and flags are unchanged. Active documentation links were repaired in the family README and this index. Four code/test comment or docstring mentions remain as historical references; no operational or AI/bootstrap dependency remains on the old paths.

**Phase C2B — historical phase documents relocation: 11 files — approved 2026-07-14.** Phase C2B is approved and complete. Eleven class-C phase documents moved from `docs/phases/` to `docs/archive/phases/` via `git mv`. `docs/phases/README.md` remains the compatibility and authority entry point. Three class-F proposals remain in place for later relocation. All 11 moved bodies are byte-identical to the approved baseline (`462aadfd5b359b1c6cf532e3573cf26c2d1feba6`). Status notices were preserved. Classes, flags, and authority fields remain unchanged. Active documentation and AI/bootstrap references were repaired. No operational dependency remains on an old path. Phase C2A remains approved. Phase C2C and later batches have not begun. Phase C remains incomplete.

**Phase C2C-core — low-risk historical briefings relocation: 20 files — approved 2026-07-14.** Phase C2C-core is approved and complete. Twenty low-risk class-C briefings moved from `docs/briefings/` to `docs/archive/briefings/` via `git mv`. Eight C2C-review class-C files remain for the next review batch. Eight class-E evidence files remain in `docs/briefings/`. All 20 moved bodies are byte-identical to the approved baseline (`e80b660ee5335eff15c885af273ec9e83e4b4015`). No notice-bearing file was moved. Classes, flags, and authority fields remain unchanged. No operational or active AI/bootstrap dependency remains on old paths. Implementation-model deviation: Composer 2.5 was used where Auto was approved; no repository-integrity impact. Phase C2A and C2B remain approved. Phase C2C-review and later batches have not begun. Phase C remains incomplete.

**Phase C2C-review — reviewed historical briefings relocation and AI-bootstrap correction: 8 files — approved 2026-07-15.** C2C-review is approved and complete. Eight Medium-risk class-C strategist briefings (`AI_CONTEXT.md`-cited "mandatory"/"read-first" set) moved from `docs/briefings/` to `docs/archive/briefings/` via `git mv`; all 28 class-C briefings are now archived, and `docs/briefings/` now contains exactly eight class-E evidence files. All eight moved bodies are byte-identical to the approved baseline (`e7ebf53dec0bca384d70081d72cd7f3fe5cc7541`). Classes, flags, and authority fields remain unchanged. Obsolete mandatory/read-first/always-consult treatment of these eight files in `AI_CONTEXT.md` was removed or corrected to point to the canonical R2 entry path (`docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md`, correctly identified as the canonical class-B extensibility directive) or demoted to optional historical-background pointers at the new archive paths; the substantive 12C/12C.1/12D layering framework and extensibility rules remain preserved in `AI_CONTEXT.md`'s own class-B prose, so no necessary startup instruction was lost. One invalidated active link in `docs/DEVELOPER_ONBOARDING.md` §10 was repaired to the archive path. No operational dependency required a code or test change. No compatibility README was required or created. Phase C2A, C2B, and C2C-core remain approved. C2D1 and later Phase C2 batches have not begun. Phase C remains incomplete.

**Phase C2D1 — design-history extraction: 6 files — approved 2026-07-15.** Six class-C design-history documents were relocated from `docs/design/` to `docs/archive/design-history/` via `git mv` (4 Low, 2 Medium); all six bodies are byte-identical to the approved baseline (`26aa0d72acd5b5313378d35c1312c83bddd4cdd0`), and the `TRACE_CONTRACT_v1.md` Phase B5A status notice was preserved byte-identically. Current class-B design guidance (`docs/design/mandarinos_design_constitution.txt`, `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md`, `docs/design/LICENSE.md`) remains in place; class-D `CURSOR_STARTUP_PROTOCOL.md` and class-F proposals remain deferred to later batches. Obsolete bootstrap authority references were corrected: `AI_CONTEXT.md` §1.2/§11 removed always-consult/read-first treatment of `TRACE_CONTRACT_v1.md`, framing the archive path as optional historical context subordinate to `docs/ARCHITECTURE.md` and the R2 package; `.github/copilot-instructions.md` replaced "authoritative" framing of `MandarinOS Developer Handoff.txt` with `docs/DEVELOPER_ONBOARDING.md` plus an archive historical pointer; `integration_kit/README.md` repointed its one active TRACE reference to the archive path. On approval-pass review, three further active current links resolved by Sonnet diagnosis: `MANDARINOS_SYSTEM_MAP.md` §2.5 and §9 (class B, "read-first (authoritative)") redirected TRACE authority to `docs/ARCHITECTURE.md` and the applicable R2 contract, with the archive path retained as optional non-authoritative historical background; `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md` §3 "Non-Negotiable Authority" redirected its TRACE Contract entry to the same current authority, removing the incorrect implication that the archived file overrides AI decisions; `docs/design/SCENARIOS_REQUIRED_v1.md` §"References" received a bounded administrative path-only correction (`./TRACE_CONTRACT_v1.md` → `../archive/design-history/TRACE_CONTRACT_v1.md`) to keep its live navigational Markdown link resolving, with its Phase B3B status notice and all other proposal text preserved byte-identically. All three status notices on the diagnosed files remain byte-identical. Remaining old-path mentions in Phase B5/C1 historical records, the approved source-to-destination map, and unrelated dated/archived documents outside the C2D1 changed-file scope were left unchanged as historical text. Phase C2A through C2C-review remain approved. C2D2 and later batches have not begun. Phase C remains incomplete.

**Phase C2D2 — superseded documents, cross-directory: 10 relocations — approved 2026-07-15.** Ten class-D superseded documents moved via `git mv` from three source directories (`docs/design/` 1, `docs/project/` 1, `docs/specs/` 8) to `docs/archive/superseded/` (8 Low, 2 Medium). All 10 bodies and notices are byte-identical to the approved baseline (`de9758b442cde24c39e5ce5c9262017a6692260c`); classes, flags, and replacement/current-authority fields unchanged. Zero operational code/test/CI dependencies found. Two active `AI_CONTEXT.md` citations corrected — this resolves the conflict already documented in this index's own §18 conflict list: the line asserting `docs/project/MANDARINOS_PROJECT_PLAN_v1.md` as "the current development roadmap" was repointed to the existing "Project Plan" section (which already correctly states v2 supersedes v1) with an explicit archive-path/class-D historical note; the line mandating "Cursor must read `docs/design/CURSOR_STARTUP_PROTOCOL.md` before performing any analysis or code changes" was replaced with a pointer to the current onboarding sequence (`docs/ARCHITECTURE.md` §21, `docs/DOCUMENT_AUTHORITY_INDEX.md` §13), with the archive copy retained only as optional non-authoritative historical context. `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` (class C, live navigation index) had its eight relative links to the moved specs repointed to `docs/archive/superseded/`; its status notice and all other content preserved byte-identically. No compatibility redirect stub was created (none justified: no operational dependency, and the two active citations were corrected at their source rather than requiring a pointer at the old path). Current class-B design guidance and all class-F proposals remain untouched. All 10 replacement/current-authority fields were verified to cite existing class-A (or, for `MandarinOS_master_AI_bootstrap_context.md`, class-B `AI_CONTEXT.md`, itself subordinate to the R2 package) documents. C2D1 remains approved. C2D3-core and later batches have not begun. Phase C remains incomplete.

**Phase C2D3-core — approved low-risk specification-history relocation: 32 relocations — candidate completed 2026-07-15; pending review and approval.** Thirty-two class-C historical specifications moved via `git mv` from `docs/specs/` to `docs/archive/specs/` (all Low risk, historical cross-links only, zero operational or AI/bootstrap references per the approved audit). Bodies and notices are byte-identical to the approved baseline (`34e1372d49f5cc7fa8bd9293e89f8f604c1eb504`); classes, flags, and replacement/current-authority fields unchanged. Three current class-B specifications (`Cursor_Directive_MandarinOS_Extensibility_Strategy.md`, `MANDARINOS_CONVERSATION_FLOW_DESIGN.md`, `MandarinOS_Extensibility_Strategy.md`) remain in place at `docs/specs/`, unmoved. The six-file Phase C2D3-review population (`CONVERSATION_ARCHITECTURE_INDEX.md` plus five specifications with a code-comment or AI-bootstrap reference) remains at `docs/specs/`, deferred and untouched. `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` (class C, live navigation index, itself deferred to C2D3-review) had 18 further relative links to the 32 relocated files repointed to `docs/archive/specs/`; its status notice and all other content preserved byte-identically. Two bounded active-reference corrections made outside the index: `docs/DEVELOPER_ONBOARDING.md` §10 Documentation Index repointed its `Live_Beginner_Ability_Model.md` row to the archive path with a historical-background label; `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md` (class B, current authority) §8 "Related documents" repointed its `MandarinOS_Repair_Curiosity_Loop.md` row to the archive path with a historical label — both bounded to the single affected row, no other content changed. No compatibility redirect stub created: no operational dependency and the two active citations were corrected at their source. C2D2 remains approved. C2D3-review and later batches have not begun. Phase C remains incomplete.

Move selected files into a structured archive, preserving Git history and fixing references.

### Phase D — duplicate reduction
Delete or consolidate files only after owner review and link verification (see §12).

### Phase E — index/onboarding integration
Link this authority index from the onboarding path and supporting guidance.

Constraints:

- no Phase B–E action is authorised by this draft;
- each phase requires a separate reviewed directive;
- deletion requires explicit project-owner approval.

## 16. Classification maintenance rules

Reclassify when:

- an ADR is superseded;
- a behavioural contract is replaced;
- a proposal is implemented;
- a report becomes historically significant;
- a branch or deployment process changes;
- a new authoritative document is approved;
- duplicate documents are consolidated;
- an unresolved item gains sufficient evidence.

Accepted classifications must be updated in the **same change** that changes their authority status.

## 17. Complete file inventory

Every tracked documentation file in audit scope appears exactly once. Paths are repository-relative.

### 17.1 Repository root, `.github`, `conformance`, `runtime`, `scripts`, `tools`

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `AI_CONTEXT.md` | B | mixed-current-and-historical, misleading-filename, status-header-added | `docs/ARCHITECTURE.md` | "Authoritative" label overstated; Phase 11 era. Classification inference: B from valid repo-map/guardrails despite obsolete phase references |
| `MANDARINOS_SYSTEM_MAP.md` | B | mixed-current-and-historical, misleading-filename, status-header-added | `docs/ARCHITECTURE.md` | Pipeline map; trace framing legacy. Classification inference: B from still-useful pipeline framing despite legacy trace concepts |
| `README.md` | B | contains-current-material | — | Current quick-start/tech stack |
| `requirements.txt` | B | contains-current-material | repo config | Runtime dependency manifest |
| `requirements-tools.txt` | B | contains-current-material | repo config | Optional tooling deps |
| `fo_check.txt` | G | generated, dated-snapshot, generated-guidance-added | — | Captured command error output; Phase B5C generated-output guidance approved |
| `frame_dump.txt` | G | generated, generated-guidance-added | — | Frame-order dump; Phase B5C generated-output guidance approved |
| `frame_texts.txt` | G | generated, generated-guidance-added | — | Frame-text dump (encoding artefacts); Phase B5C generated-output guidance approved |
| `server_out.txt` | G | generated, generated-guidance-added | — | Server stdout capture; Phase B5C generated-output guidance approved |
| `server_err.txt` | G | generated, generated-guidance-added | — | Server stderr capture; Phase B5C generated-output guidance approved |
| `server_startup_err.txt` | G | generated, generated-guidance-added | — | Startup stderr capture; Phase B5C generated-output guidance approved |
| `.github/copilot-instructions.md` | C | contains-obsolete-material, misleading-filename, status-header-added | `AI_CONTEXT.md`, `.cursor/rules/*`, `docs/CHANGE_CHECKLIST.md` §23 | Copilot retired; Cursor ops moved |
| `conformance/README.md` | B | branch-specific | `docs/TEST_STRATEGY.md` | Conformance runner exists; side tool |
| `runtime/README_runtime_indexes.txt` | B | contains-current-material | `docs/ARCHITECTURE.md` §14 | Index defs vs computed |
| `scripts/_engine_audit.txt` | G | generated, generated-guidance-added | — | Engine/frame audit output; Phase B5C generated-output guidance approved |
| `tools/coverage/coverage_report.md` | G | generated, generated-guidance-added | — | Content coverage scanner output; Phase B5C generated-output guidance approved |

### 17.2 `docs/` (top level)

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/ARCHITECTURE.md` | A | — | — | Orientation map |
| `docs/CONVERSATION_ARCHITECTURE.md` | A | — | — | Conversation contract |
| `docs/STATE_CONTRACT.md` | A | — | — | State contract |
| `docs/ANSWER_SOURCE_CONTRACT.md` | A | — | — | Answer-source contract |
| `docs/ASR_PIPELINE.md` | A | — | — | ASR/input contract |
| `docs/TEST_STRATEGY.md` | A | — | — | Evidence contract |
| `docs/CHANGE_CHECKLIST.md` | A | — | — | Change-control checklist |
| `docs/ARCHITECTURAL_DECISIONS.md` | A | — | — | ADR record |
| `docs/DOCUMENT_AUTHORITY_INDEX.md` | A | — | — | This document. Approved ninth authoritative R2 document (see §4) |
| `docs/DEVELOPER_ONBOARDING.md` | B | contains-obsolete-material, status-header-added | `docs/ARCHITECTURE.md` | 2026-05-11; counts drift; Phase B5A notice approved |
| `docs/MANDARINOS_REGRESSION_LOCK.md` | B | misleading-filename, contains-current-material, status-header-added | `docs/TEST_STRATEGY.md` | Regression-guard register. Classification inference: B — guards still relevant; evidence weight per TEST_STRATEGY |
| `docs/PHASE_B5_SCOPE_ASSESSMENT.md` | E | dated-snapshot | dated evidence only | Phase B5 approved scope assessment; not implementation authority |
| `docs/PHASE_C1_ARCHIVAL_AUDIT.md` | E | dated-snapshot | dated evidence only | Phase C1 approved archival audit and relocation plan; not relocation authority |
| `docs/RESPONSE_OPTION_STYLE_GUIDE.md` | B | contains-current-material | `docs/ANSWER_SOURCE_CONTRACT.md` | Option style rules |
| `docs/REPO_STRUCTURE_PROPOSAL.md` | F | implementation-not-verified, status-header-added | proposal only — no current authority | Proposed layout; not executed. Phase B3A notice approved |
| `docs/SCHEMA_SYNC_RECOMMENDATION.md` | F | implementation-not-verified, status-header-added | proposal only — no current authority | Recommends consolidating two schema dirs (still separate); no duplicate-document relationship. Phase B3B notice approved |
| `docs/session_intelligence_architecture.md` | F | partially-implemented, status-header-added | proposal only — no current authority | Slice 1 implemented; rest proposal. Classification inference: F — only slice 1 verified implemented. Phase B3B notice approved |
| `docs/session_intelligence_implementation_report.md` | E | dated-snapshot, status-header-added | dated evidence only | Implementation report. Phase B4D notice approved |

### 17.3 `docs/design/`

Mixed design directory remaining after approved Phase C2D1 and approved Phase C2D2: three class-B current design-governance files; two class-F proposals deferred to later proposal batches. Six class-C early-design files relocated to `docs/archive/design-history/` in approved Phase C2D1; the one class-D superseded onboarding protocol relocated to `docs/archive/superseded/` in approved Phase C2D2 (see §17.13).

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/design/mandarinos_design_constitution.txt` | B | mixed-current-and-historical | Nine-document R2 governance package | Product philosophy retained |
| `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md` | B | contains-current-material | Nine-document R2 governance package | AI governance model |
| `docs/design/LICENSE.md` | B | — | — | Copyright statement |
| `docs/design/SCENARIOS_REQUIRED_v1.md` | F | implementation-not-verified, status-header-added | — | Required-scenarios spec. Phase B3B notice approved |
| `docs/design/MANDARINOS_PHASE_12_HYBRID_AI_CONCEPT_BRIEFING.txt` | F | implementation-not-verified, status-header-added | ADR-014 (deferred) | Hybrid-AI concept. Phase B3B notice approved |

### 17.3a `docs/archive/design-history/`

Archived early design documents (class C). Relocated from `docs/design/` in approved Phase C2D1; authority unchanged.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/archive/design-history/CARDS_BUILD_v1.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Cards-build era. Relocated in approved Phase C2D1; authority unchanged. |
| `docs/archive/design-history/MandarinOS Developer Handoff.txt` | C | phase-specific | `docs/DEVELOPER_ONBOARDING.md` | Early handoff. Relocated in approved Phase C2D1; authority unchanged. |
| `docs/archive/design-history/MandarinOS_brief.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Early project brief. Relocated in approved Phase C2D1; authority unchanged. |
| `docs/archive/design-history/TRACE_CONTRACT_v1.md` | C | phase-specific, implementation-not-verified, status-header-added | `docs/ARCHITECTURE.md` | Trace contract not in conversation runtime; Phase B5A notice approved. Relocated in approved Phase C2D1; authority unchanged. |
| `docs/archive/design-history/p3_architecture.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Early architecture. Relocated in approved Phase C2D1; authority unchanged. |
| `docs/archive/design-history/ux_flow.txt` | C | phase-specific | `docs/ARCHITECTURE.md` | Early UX flow. Relocated in approved Phase C2D1; authority unchanged. |

### 17.4 `docs/briefings/`

Briefing directory now holds only eight class-E dated evidence files. All twenty-eight class-C strategist briefings have been relocated to `docs/archive/briefings/`: twenty in approved Phase C2C-core, eight in approved Phase C2C-review.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/briefings/bridge_audit_apr2026.md` | E | dated-snapshot, status-header-added | dated evidence only | Bridge audit (Apr 2026). Phase B4C notice approved |
| `docs/briefings/engine_audit_apr2026.md` | E | dated-snapshot, status-header-added | dated evidence only | Engine audit (Apr 2026). Phase B4C notice approved |
| `docs/briefings/implementation_report_apr2026.md` | E | dated-snapshot, status-header-added | dated evidence only | Implementation report (Apr 2026). Phase B4C notice approved |
| `docs/briefings/PHASE7_COMPLETION_REVIEW_AND_TEST.md` | E | dated-snapshot, status-header-added | dated evidence only | Phase 7 completion review. Phase B4C notice approved |
| `docs/briefings/PHASE10_STRATEGIST_REVIEW.md` | E | dated-snapshot, status-header-added | dated evidence only | Phase 10 review. Phase B4C notice approved |
| `docs/briefings/CONVERSATION_ARCHITECTURE_ASSESSMENT.md` | E | dated-snapshot, status-header-added | dated evidence only | Architecture assessment. Phase B4C notice approved |
| `docs/briefings/UI_CONVERSATION_LOOP_ASSESSMENT.md` | E | dated-snapshot, status-header-added | dated evidence only | UI loop assessment. Phase B4C notice approved |
| `docs/briefings/PHASE7_SCHEMA_DISCOVERIES.md` | E | dated-snapshot, status-header-added | dated evidence only | Schema-discovery findings. Phase B4C notice approved |

### 17.4a `docs/archive/briefings/`

Archived historical strategist/phase briefings (class C). Twenty relocated from `docs/briefings/` in approved Phase C2C-core (authority unchanged); eight relocated in approved Phase C2C-review (authority unchanged).

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/archive/briefings/BRIEFING_CHANGES_FOR_CHATGPT_REVIEW.md` | C | phase-specific | R2 governance set | Review briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | C | duplicate-or-near-duplicate | `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | Duplicate of `docs/specs/` canonical. Relocated in approved Phase C2C-review; authority unchanged. |
| `docs/archive/briefings/MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt` | C | phase-specific | R2 governance set | Move-type brief. Relocated in approved Phase C2C-review; authority unchanged. |
| `docs/archive/briefings/MANDARINOS_PHASE_10_7_PHASE_11_BRIEFING.txt` | C | phase-specific | R2 governance set | Phase 10.7/11 briefing. Relocated in approved Phase C2C-review; authority unchanged. |
| `docs/archive/briefings/MandarinOS_Phase12D_Cursor_Implementation_Brief.md` | C | phase-specific, implementation-not-verified | R2 governance set | Phase 12D brief. Relocated in approved Phase C2C-review; authority unchanged. |
| `docs/archive/briefings/MandarinOS_Phase_12C_Alignment_Brief.md` | C | phase-specific | R2 governance set | Phase 12C alignment. Relocated in approved Phase C2C-review; authority unchanged. |
| `docs/archive/briefings/PHASE10_STRATEGIST_BRIEFING_SPECS_GAP_AND_PATH.md` | C | phase-specific | R2 governance set | Phase 10 briefing. Relocated in approved Phase C2C-review; authority unchanged. |
| `docs/archive/briefings/PHASE_10_5_10_6_ALPHA_STRATEGIST_BRIEFING.md` | C | phase-specific | R2 governance set | Phase 10.5/10.6 briefing. Relocated in approved Phase C2C-review; authority unchanged. |
| `docs/archive/briefings/USER_LED_DISCOVERY_STRATEGIST_BRIEF.md` | C | phase-specific | R2 governance set | Discovery briefing. Relocated in approved Phase C2C-review; authority unchanged. |
| `docs/archive/briefings/CHATGPT_STRATEGIST_CONVERSATION_DESIGN_BRIEFING.md` | C | phase-specific | R2 governance set | Strategist briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/MandarinOS_Phase12E_CuriosityProbe_Brief.md` | C | phase-specific, implementation-not-verified | R2 governance set | Phase 12E brief. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/MandarinOS_laptop_handoff_UI_cascading_help_briefing.md` | C | phase-specific | R2 governance set | Handoff briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/NEXT_PHASE_ADVICE_CURSOR.md` | C | phase-specific | R2 governance set | Next-phase advice. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/PHASE7_4_UI_POLISH_STRATEGIST_BRIEFING.md` | C | phase-specific | R2 governance set | Phase 7.4 briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/PHASE7_COMPLETE_STRATEGIST_BRIEFING.md` | C | phase-specific | R2 governance set | Phase 7 briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/PHASE8_OPTIONS_APPROPRIATENESS.md` | C | phase-specific | R2 governance set | Phase 8 briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/PHASE8_STEP1_TRANSCRIPT_ARCHITECTURE.md` | C | phase-specific | R2 governance set | Phase 8 transcript arch. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/PHASE9_SIGNOFF_STRATEGIST_BRIEFING.md` | C | phase-specific | R2 governance set | Phase 9 sign-off. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/PHASE_12B_STABILIZATION_AND_UI_FLOW_STRATEGIST_BRIEFING.md` | C | phase-specific | R2 governance set | Phase 12B briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/PHASE_12C_EXECUTIVE_STRATEGIST_BRIEF.md` | C | phase-specific | R2 governance set | Phase 12C exec brief. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/PHASE_12C_STRATEGIST_PROPOSAL_CURIOSITY_PERSONA_SESSION_ARC.md` | C | phase-specific, implementation-not-verified | R2 governance set | Phase 12C proposal briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/STRATEGIST_BRIEFING_MAY2026_UI_POLISH_AND_DISTANCE_THREAD.md` | C | phase-specific | R2 governance set | May 2026 briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/UI_SHELL_STRATEGIST_BRIEFING_APR2026.md` | C | phase-specific | R2 governance set | Apr 2026 briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/architecture_briefing_apr2026.md` | C | phase-specific | R2 governance set | Apr 2026 architecture briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/mandarinos_chatgpt_session_briefing.md` | C | phase-specific | R2 governance set | Session briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/mandarinos_recovery_phrases_v1_2_cursor_briefing.txt` | C | phase-specific | R2 governance set | Recovery-phrase briefing. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/phase12c_recovery_trigger_briefing.txt` | C | phase-specific | R2 governance set | Phase 12C recovery trigger. Relocated in approved Phase C2C-core; authority unchanged. |
| `docs/archive/briefings/phase7_3_senior_architect_briefing.md` | C | phase-specific | R2 governance set | Phase 7.3 briefing. Relocated in approved Phase C2C-core; authority unchanged. |

### 17.5 `docs/directives/`

Family entry point for Phase 2–7 cards/trace/harness implementation directives. The seventeen historical directive bodies were relocated to `docs/archive/directives/` in approved Phase C2A; this directory retains the class-B family guide only.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/directives/README.md` | B | contains-current-material | `docs/CHANGE_CHECKLIST.md`; relevant R2 contracts; verified code | Historical-directive family authority guide; Phase B5B approved family guidance; Phase C2A compatibility entry point covering 17 archived paths |

### 17.5a `docs/archive/directives/`

Archived Phase 2–7 cards/trace/harness implementation directives. Classification C; flags `phase-specific, implementation-not-verified`. Relocated from `docs/directives/` in approved Phase C2A; authority unchanged.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/archive/directives/MANDARINOS_ARCHITECT_COPILOT_HANDOFF_DIRECTIVE_PHASE7.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Phase 7 handoff directive. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MANDARINOS_COPILOT_STARTUP_INSTRUCTIONS.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Copilot startup (retired tool). Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_OPEN_CARD_Trace_Wiring_Directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Card trace wiring. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_OPEN_CARD_Unit_Test_Directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Card unit-test directive. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_Phase_Boundaries_v1.0.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Phase boundaries. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_Runtime_Card_Integration_Directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Runtime card integration. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_Simulator_Entrypoint_Copilot_Directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Simulator entrypoint. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_TurnState_Trace_Contract_v1_directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | TurnState trace contract. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_UI_Shell_Copilot_Directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | UI shell directive. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_card_contract_v1_directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Card contract. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_conformance_harness_directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Conformance harness. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_content_coverage_scanner_v1_directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Coverage scanner. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_hint_cascade_directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Hint cascade. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_integration_kit_scenarios_v1_directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Integration-kit scenarios. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_scaffolding_transition_harness_v1_directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Scaffolding transition harness. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/MandarinOS_universal_cards_builder_v1_directive.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Universal cards builder. Relocated in approved Phase C2A; authority unchanged. |
| `docs/archive/directives/mandarinos_copilot_architecture_update.txt` | C | phase-specific, implementation-not-verified | code + `docs/CHANGE_CHECKLIST.md` | Copilot architecture update. Relocated in approved Phase C2A; authority unchanged. |

### 17.6 `docs/phases/`

Family entry point for historical phase documents. Eleven class-C historical bodies were relocated to `docs/archive/phases/` in approved Phase C2B; this directory retains the class-B family guide and three class-F proposals pending a later batch.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/phases/README.md` | B | contains-current-material | `docs/ARCHITECTURE.md`; `docs/ARCHITECTURAL_DECISIONS.md` | Historical-phase family authority guide; Phase B5B approved family guidance; Phase C2B compatibility entry point covering 11 archived paths |
| `docs/phases/PHASE10_TECHNICAL_PROPOSAL.md` | F | implementation-not-verified, status-header-added | proposal only — no current authority | Phase 10 technical proposal. Phase B3A notice approved |
| `docs/phases/PHASE9_CONTENT_AND_ENGINES_PLAN.md` | F | implementation-not-verified, status-header-added | proposal only — no current authority | Phase 9 content/engines plan. Phase B3A notice approved |
| `docs/phases/PHASE_10_5_MAPPING_AND_SCHEMA_PROPOSAL.md` | F | implementation-not-verified, status-header-added | proposal only — no current authority | Phase 10.5 mapping/schema proposal. Phase B3A notice approved |

### 17.6a `docs/archive/phases/`

Archived historical phase documents. Classification C; flags vary per row. Relocated from `docs/phases/` in approved Phase C2B; authority unchanged.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/archive/phases/MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md` | C | phase-specific, duplicate-or-near-duplicate | `docs/ARCHITECTURE.md` | Near-dup of `PHASE9_1_ACCEPTANCE_CRITERIA.md`. Relocated in approved Phase C2B; authority unchanged. |
| `docs/archive/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md` | C | phase-specific, duplicate-or-near-duplicate | `docs/ARCHITECTURE.md` | Near-dup. Relocated in approved Phase C2B; authority unchanged. |
| `docs/archive/phases/MANDARINOS_PHASE_10_5_STABILISATION_BRIEF.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Phase 10.5 stabilisation. Relocated in approved Phase C2B; authority unchanged. |
| `docs/archive/phases/MandarinOS_Phase9_Signoff.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Phase 9 sign-off. Relocated in approved Phase C2B; authority unchanged. |
| `docs/archive/phases/PHASE6_FREEZE.md` | C | phase-specific, misleading-filename, status-header-added | `docs/ARCHITECTURE.md` | Phase 6 freeze. Relocated in approved Phase C2B; authority unchanged. |
| `docs/archive/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` | C | phase-specific, misleading-filename, status-header-added | `docs/ARCHITECTURE.md` | Phase 6 lock. Relocated in approved Phase C2B; authority unchanged. |
| `docs/archive/phases/PHASE6_RUNTIME_INDEXES_NOTES.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Phase 6 runtime-index notes. Relocated in approved Phase C2B; authority unchanged. |
| `docs/archive/phases/PHASE9_2_BRIDGE_TIER.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Phase 9.2 bridge tier. Relocated in approved Phase C2B; authority unchanged. |
| `docs/archive/phases/PHASE_10_5_CONVERSATION_SIMULATION.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Phase 10.5 simulation. Relocated in approved Phase C2B; authority unchanged. |
| `docs/archive/phases/Phase 3 Step 1 Audio-first UI.md` | C | phase-specific | `docs/ASR_PIPELINE.md` | Phase 3 audio-first UI. Relocated in approved Phase C2B; authority unchanged. |
| `docs/archive/phases/ROLLBACK_POINT_v1.md` | C | phase-specific, dated-snapshot | dated evidence only | Rollback point. Relocated in approved Phase C2B; authority unchanged. |

### 17.7 `docs/plans/`

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/plans/PHASE_10_7_MINIMAL_IMPLEMENTATION_PLAN.md` | F | implementation-not-verified, status-header-added | proposal only — no current authority | Phase 10.7 minimal plan. Phase B3A notice approved |
| `docs/plans/component_radical_gloss_plan.md` | F | implementation-not-verified, status-header-added | proposal only — no current authority | Component/radical gloss plan. Phase B3A notice approved |
| `docs/plans/learner_etymology_hints_plan.md` | F | implementation-not-verified, status-header-added | proposal only — no current authority | Etymology-hints plan. Phase B3A notice approved |

### 17.8 `docs/project/`

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/project/MandarinOS_project_plan_v2.md` | F | implementation-not-verified, status-header-added | proposal only — no current authority | Latest named roadmap version in the family; class F, not implementation authority; verify implemented status against code + R2 documents. Phase B3A notice approved |
| `docs/project/MandarinOS_project_plan_v2_CORRECTED.md` | F | duplicate-or-near-duplicate, status-header-added | proposal only — no current authority | Roadmap variant. Phase B3A notice approved |
| `docs/project/MandarinOS_project_plan_v2_UPDATED.md` | F | duplicate-or-near-duplicate, status-header-added | proposal only — no current authority | Roadmap variant. Phase B3A notice approved |
| `docs/project/RECOVERY_AND_CONVERSATION_FUTURE_NOTES.md` | F | implementation-not-verified, status-header-added | proposal only — no current authority | Future notes. Phase B3A notice approved |
| `docs/project/DIRECTIVE_PHASE_1_CARD_PANEL_STATE.md` | C | phase-specific | code + `docs/CHANGE_CHECKLIST.md` | Phase 1 directive |
| `docs/project/ENGINES_P1_P2_AND_SRS_REFERENCE.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Engine/SRS reference |
| `docs/project/NEXT_QUESTION_SELECTOR_AND_LEVEL_TIE_IN.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | References LOCKED selector spec |
| `docs/project/PROBE_QUESTIONS_RESPONSE_OPTIONS_NOTE.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Probe-questions note |
| `docs/project/TEST_DIAGNOSTIC_P1_MANUAL.md` | C | phase-specific | `docs/TEST_STRATEGY.md` | Manual diagnostic procedure |
| `docs/project/USER_TURN_AND_PERSONA_QUESTIONS_NOTE.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Persona-questions note |
| `docs/project/ARCHITECTURE_ALIGNMENT_OPTIONS_AND_GOLD.md` | E | dated-snapshot, status-header-added | dated evidence only | Alignment options analysis. Phase B4A notice approved |
| `docs/project/AUDIT_OPTION_GENERATION.md` | E | dated-snapshot, status-header-added | dated evidence only | Option-generation audit. Phase B4A notice approved |
| `docs/project/COMMIT_RECORD.md` | E | dated-snapshot, status-header-added | dated evidence only | Commit record. Phase B4A notice approved |
| `docs/project/COMMIT_SUMMARY.md` | E | dated-snapshot, duplicate-or-near-duplicate, status-header-added | dated evidence only | Commit summary. Phase B4A notice approved |
| `docs/project/COMMIT_SUMMARY_v1.md` | E | dated-snapshot, duplicate-or-near-duplicate, status-header-added | dated evidence only | Commit summary v1. Phase B4A notice approved |
| `docs/project/CORE_TREASURE_BRIDGE_STATUS.md` | E | dated-snapshot, status-header-added | dated evidence only | Bridge status report. Phase B4A notice approved |
| `docs/project/DIAGNOSTIC_P1_VALIDATION_RESULTS.md` | E | dated-snapshot, status-header-added | dated evidence only | Diagnostic results. Phase B4A notice approved |
| `docs/project/EXECUTIVE_SUMMARY_v1.md` | E | dated-snapshot, status-header-added | dated evidence only | Executive summary. Phase B4A notice approved |
| `docs/project/OPTION_GENERATION_FIX_COMPLETE.md` | E | dated-snapshot, status-header-added | dated evidence only | Fix-complete report. Phase B4A notice approved |
| `docs/project/PHASE9_STATUS_AND_RESPONSE_QUALITY.md` | E | dated-snapshot, status-header-added | dated evidence only | Phase 9 status. Phase B4A notice approved |
| `docs/project/SPECS_TO_IMPLEMENTATION_GAP.md` | E | dated-snapshot, status-header-added | dated evidence only | Gap analysis. Phase B4A notice approved |
| `docs/project/TEST_SUMMARY.md` | E | dated-snapshot, status-header-added | dated evidence only | Test summary. Phase B4A notice approved |
| `docs/project/CHATGPT_BRANCH_START_TEMPLATE.md` | G | — | — | Authored workflow template (procedural, not generated) |
| `docs/project/COMMIT_INSTRUCTIONS.md` | G | — | — | Authored procedural instructions (not generated) |

### 17.9 `docs/reports/`

All classification E, flags `dated-snapshot`; current authority is code + contracts.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/reports/CORPUS_RECOVERY_NOTES.md` | E | dated-snapshot, status-header-added | dated evidence only | Corpus recovery notes. Phase B4B notice approved |
| `docs/reports/PHASE_11_1_1_OBSERVATION_REPORT.md` | E | dated-snapshot, status-header-added | dated evidence only | Phase 11.1.1 observation. Phase B4B notice approved |
| `docs/reports/alpha_conversation_observation.md` | E | dated-snapshot, status-header-added | dated evidence only | Alpha observation. Phase B4B notice approved |
| `docs/reports/capability_mismatch_observation.md` | E | dated-snapshot, status-header-added | dated evidence only | Capability-mismatch observation. Phase B4B notice approved |
| `docs/reports/component_gloss_coverage.md` | E | dated-snapshot, status-header-added | dated evidence only | Gloss coverage report. Phase B4B notice approved |
| `docs/reports/counter_reply_matrix_report.md` | E | dated-snapshot, status-header-added | dated evidence only | Counter-reply matrix. Phase B4B notice approved |
| `docs/reports/move_type_tagging_audit.md` | E | dated-snapshot, status-header-added | dated evidence only | Move-type tagging audit. Phase B4B notice approved |
| `docs/reports/move_type_tagging_coverage.md` | E | dated-snapshot, status-header-added | dated evidence only | Move-type coverage. Phase B4B notice approved |
| `docs/reports/move_type_transition_calibration.md` | E | dated-snapshot, status-header-added | dated evidence only | Transition calibration. Phase B4B notice approved |
| `docs/reports/vocab_character_coverage_audit.md` | E | dated-snapshot, status-header-added | dated evidence only | Vocab/character coverage. Phase B4B notice approved |

### 17.10 `docs/specs/`

Eight class-D superseded documents relocated to `docs/archive/superseded/` in approved Phase C2D2 (see §17.13); `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` retains a live navigation index and its eight relative links to those files were repointed to the new archive path. Thirty-two class-C historical specifications relocated to `docs/archive/specs/` in the Phase C2D3-core candidate (see §17.14); `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` had 18 further relative links repointed to the new archive path, and remains at its current path pending the separately reviewed Phase C2D3-review batch (with five other class-C specifications carrying a code-comment or AI-bootstrap reference). Three current class-B specifications and the remaining class-E/F documents are unaffected.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | B | duplicate-or-near-duplicate | ADR record | Canonical (cited by `.cursor/rules`). Classification inference: B because cited by `.cursor/rules` despite pre-R2 date |
| `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md` | B | contains-current-material | `docs/CONVERSATION_ARCHITECTURE.md` | Cited read-first for flow. Classification inference: B because cited by `.cursor/rules` despite pre-R2 date |
| `docs/specs/MandarinOS_Extensibility_Strategy.md` | B | contains-current-material | ADR record | Cited strategy doc. Classification inference: B because cited by `.cursor/rules` despite pre-R2 date |
| `docs/specs/MANDARINOS_CONVERSATION_ARCHITECTURE_AUDIT_v1.md` | E | dated-snapshot, status-header-added | — | Architecture audit. Phase B4D notice approved |
| `docs/specs/MandarinOS_conversation_expansion_audit_v2.md` | E | dated-snapshot, status-header-added | — | Expansion audit. Phase B4D notice approved |
| `docs/specs/Translation_Surface_Consistency_Audit.md` | E | dated-snapshot, status-header-added | — | Translation audit. Phase B4D notice approved |
| `docs/specs/mandarinos_conversation_architecture_audit_request_v2.txt` | E | dated-snapshot, status-header-added | — | Audit request. Phase B4D notice approved |
| `docs/specs/MandarinOS_Hybrid_Speech_and_Persona_Voice_Architecture.md` | F | implementation-not-verified, status-header-added | ADR-014 (deferred) | Hybrid speech (deferred). Phase B3B notice approved |
| `docs/specs/PHASE_10_5_BEHAVIOUR_IMPLEMENTATION_PLAN.md` | F | implementation-not-verified, status-header-added | Contracts | Behaviour plan. Phase B3B notice approved |
| `docs/specs/PHASE_10_5_INTEREST_RESPONSIVENESS_REFINEMENT_PLAN.md` | F | implementation-not-verified, status-header-added | Contracts | Refinement plan. Phase B3B notice approved |
| `docs/specs/PHASE_12C_IMPLEMENTATION_BRIEF.md` | F | partially-implemented, status-header-added | Contracts | Phase 12C brief. Classification inference: F — partial implementation not verified per item. Phase B3B notice approved |
| `docs/specs/PHASE_12C_INVARIANTS.md` | F | partially-implemented, status-header-added | Contracts | Phase 12C invariants. Classification inference: F — partial implementation not verified per item. Phase B3B notice approved |
| `docs/specs/MOBILE_WORD_INSIGHT_UI_SPEC.md` | F | implementation-not-verified, status-header-added | `docs/ASR_PIPELINE.md` §14 | Word-insight UI spec. Phase B3B notice approved |
| `docs/specs/TRANSCRIPT_REPLAY_TRANSLATION_UI_SPEC.md` | F | implementation-not-verified, status-header-added | — | Transcript-replay UI spec. Phase B3B notice approved |
| `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` | C | misleading-filename, status-header-added | `docs/ARCHITECTURE.md` | Index of design specs. Eight relative links repointed to `docs/archive/superseded/` in approved Phase C2D2; authority unchanged |
| `docs/specs/MandarinOS_conversation_ladders_full_draft_v2.md` | C | phase-specific | Contracts | Ladders draft |
| `docs/specs/MandarinOS_engine_specs_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Engine specs |
| `docs/specs/MandarinOS_next_question_selector_v1.md` | C | misleading-filename, status-header-added | `docs/CONVERSATION_ARCHITECTURE.md` | LOCKED-labelled selector spec |
| `docs/specs/MandarinOS_support_packs_v1.md` | C | phase-specific | — | Support packs |
| `docs/specs/mandarinos_emergency_phrases_p1_p2_v2.md` | C | phase-specific | content JSON | Emergency phrases |

### 17.11 `docs/state/`, `docs/Social_Media/`, `integration_kit/`

Social_Media files are authored marketing collateral (procedural, campaign-scoped): class G without the `generated` flag.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/state/MANDARINOS_SYSTEM_STATE_PHASE_12B.md` | E | dated-snapshot, misleading-filename, status-header-added | dated evidence only | Phase 12B state snapshot |
| `docs/Social_Media/README.txt` | G | — | — | Authored marketing collateral index |
| `docs/Social_Media/deck1-first-video.marp.md` | G | — | — | Authored Marp source deck |
| `docs/Social_Media/deck2-vocabulary-trap.marp.md` | G | — | — | Authored Marp source deck |
| `docs/Social_Media/deck3-apps-dont-teach-speaking.marp.md` | G | — | — | Authored Marp source deck |
| `docs/Social_Media/deck4-immersion-not-enough.marp.md` | G | — | — | Authored Marp source deck |
| `docs/Social_Media/deck5-missing-skill.marp.md` | G | — | — | Authored Marp source deck |
| `docs/Social_Media/mandarinos-first-video.marp.md` | G | — | — | Authored Marp source deck |
| `docs/Social_Media/mandarinos-marp-template.md` | G | duplicate-or-near-duplicate | — | Authored Marp template (canonical) |
| `docs/Social_Media/mandarinos-marp-template 1.md` | G | duplicate-or-near-duplicate | — | Duplicate template copy |
| `docs/Social_Media/mandarinos_prelaunch_scripts.txt` | G | — | — | Authored pre-launch scripts |
| `integration_kit/README.md` | C | phase-specific, implementation-not-verified | `docs/ARCHITECTURE.md` | Trace-export kit (not wired to runtime); Phase B5B approved family guidance prepended; file remains class C and original body remains historical/contextual |
| `integration_kit/schemas/README.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Kit schema index |
| `integration_kit/examples/PHASE_2_DIRECTIVE_2A_WIRE_REDUCER_INTO_LIVE_UI.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Phase 2A example directive |
| `integration_kit/examples/PHASE_2B_DIRECTIVE_CARD_RESOLVED_RACE_GUARD.txt` | C | phase-specific | `docs/ARCHITECTURE.md` | Phase 2B example directive |
| `integration_kit/examples/PHASE_2C_DIRECTIVE_CARD_PANEL_HISTORY_BACK.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Phase 2C example directive |

### 17.12 `.cursor/rules/` coding-rule files

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `.cursor/rules/mandarinos-architecture.mdc` | B | contains-current-material | `docs/ARCHITECTURAL_DECISIONS.md` | Standing Cursor coding guidance, applied within its configured scope; subordinate to approved R2 documents |
| `.cursor/rules/mandarinos-ui-objects.mdc` | B | contains-current-material | `docs/ARCHITECTURE.md` | UI standard-object coding guidance, applied within its configured scope; subordinate to approved R2 documents |

### 17.13 `docs/archive/superseded/`

Ten class-D superseded documents relocated from three source directories (`docs/design/`, `docs/project/`, `docs/specs/`) in approved Phase C2D2; authority unchanged. Two (`CURSOR_STARTUP_PROTOCOL.md`, `MANDARINOS_PROJECT_PLAN_v1.md`) had active `AI_CONTEXT.md` citations, corrected in the same relocation.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/archive/superseded/CURSOR_STARTUP_PROTOCOL.md` | D | misleading-filename, status-header-added | `docs/ARCHITECTURE.md` §21 | Onboarding order superseded. Relocated in approved Phase C2D2; authority unchanged. |
| `docs/archive/superseded/MANDARINOS_PROJECT_PLAN_v1.md` | D | duplicate-or-near-duplicate, status-header-added | `docs/project/MandarinOS_project_plan_v2.md` | Superseded within roadmap lineage by v2; status notice added (Phase B2, approved). Relocated in approved Phase C2D2; authority unchanged. |
| `docs/archive/superseded/mandarinos_conversation_architecture_v1.md` | D | status-header-added | `docs/CONVERSATION_ARCHITECTURE.md` | Conceptual spine superseded; status notice added (Phase B2, approved). Relocated in approved Phase C2D2; authority unchanged. |
| `docs/archive/superseded/MandarinOS_conversation_runtime_model_v1.md` | D | status-header-added | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md` | Runtime model superseded; status notice added (Phase B2, approved). Relocated in approved Phase C2D2; authority unchanged. |
| `docs/archive/superseded/MandarinOS_runtime_conversation_state_engine_v1.md` | D | status-header-added | `docs/STATE_CONTRACT.md` | State engine superseded; status notice added (Phase B2, approved). Relocated in approved Phase C2D2; authority unchanged. |
| `docs/archive/superseded/MandarinOS_conversation_state_diagram_v1.md` | D | status-header-added | `docs/STATE_CONTRACT.md` | State diagram superseded; status notice added (Phase B2, approved). Relocated in approved Phase C2D2; authority unchanged. |
| `docs/archive/superseded/MandarinOS_turn_data_contract_v1.md` | D | status-header-added | `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md` | Turn data contract superseded; status notice added (Phase B2, approved). Relocated in approved Phase C2D2; authority unchanged. |
| `docs/archive/superseded/MandarinOS_conversation_memory_model_v1.md` | D | duplicate-or-near-duplicate, status-header-added | `_v2`; `docs/STATE_CONTRACT.md` | Superseded by v2; status notice added (Phase B2, approved). Relocated in approved Phase C2D2; authority unchanged. |
| `docs/archive/superseded/mandarinos_family_conversation_ladder.md` | D | duplicate-or-near-duplicate, status-header-added | `_v2` | Superseded by v2; status notice added (Phase B2, approved). Relocated in approved Phase C2D2; authority unchanged. |
| `docs/archive/superseded/MandarinOS_master_AI_bootstrap_context.md` | D | misleading-filename, status-header-added | `AI_CONTEXT.md` | Bootstrap role replaced. Relocated in approved Phase C2D2; authority unchanged. |

### 17.14 `docs/archive/specs/`

Thirty-two class-C historical specifications relocated from `docs/specs/` in the Phase C2D3-core candidate; authority unchanged. Six related class-C specifications (including the `CONVERSATION_ARCHITECTURE_INDEX.md` navigation index) with a code-comment or AI-bootstrap reference remain at `docs/specs/`, deferred to the separately reviewed Phase C2D3-review batch. Current class-B specifications (`Cursor_Directive_MandarinOS_Extensibility_Strategy.md`, `MANDARINOS_CONVERSATION_FLOW_DESIGN.md`, `MandarinOS_Extensibility_Strategy.md`) remain at `docs/specs/`, unmoved.

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/archive/specs/Live_Beginner_Ability_Model.md` | C | phase-specific | Contracts | Ability model. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/MandarinOS_Conversation_UX_Protocol_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | UX protocol. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/MandarinOS_Progress_Tracking_Cursor_Spec_v2.md` | C | phase-specific | — | Progress-tracking spec. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/MandarinOS_Repair_Curiosity_Loop.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Repair/curiosity design. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/MandarinOS_capability_update_rules_v1.md` | C | misleading-filename, status-header-added | `docs/CONVERSATION_ARCHITECTURE.md` | LOCKED-labelled design spec. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/MandarinOS_conversation_capability_map_v1.md` | C | phase-specific | — | Capability map. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/MandarinOS_conversation_memory_model_v2.md` | C | phase-specific | `docs/STATE_CONTRACT.md` | Memory model (design). Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/MandarinOS_conversation_system_blueprint_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | System blueprint. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/MandarinOS_marketing_positioning_v1.md` | C | phase-specific | — | Marketing positioning. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/PHASE_10_6_ASR_STABILIZATION_MINI_SPEC.md` | C | phase-specific | `docs/ASR_PIPELINE.md` | ASR stabilisation mini-spec. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/Progress_Scorecard_Alignment.md` | C | phase-specific | — | Scorecard alignment. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/RELEASE_1_BOUNDARY.md` | C | phase-specific | — | Release 1 boundary. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_adjective_pack_v1.md` | C | phase-specific | content JSON | Adjective pack spec. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_conversation_energy_model_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Energy model. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_conversation_steering_engine_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Steering engine. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_curiosity_engine_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Curiosity engine. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_emergency_curiosity_pack_v1.md` | C | phase-specific | content JSON | Curiosity pack. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_family_conversation_ladder_v2.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Family ladder v2. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_family_engine_v4.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Family engine v4. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_family_memory_rules_v1.md` | C | phase-specific | `docs/STATE_CONTRACT.md` | Family memory rules. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_family_vocab_pack_p1.md` | C | phase-specific | content JSON | Family vocab pack. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_food_engine_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Food engine. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_identity_engine_v4.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Identity engine v4. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_interests_engine_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Interests engine. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_orientation_pack_v1.md` | C | phase-specific | content JSON | Orientation pack. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_persona_network_relationship_pack_v1.md` | C | phase-specific | persona JSON | Persona-network pack. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_place_engine_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Place engine. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_study_work_engine_v10.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Study/work engine v10. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_study_work_ladder.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Study/work ladder. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_study_work_memory_rules.md` | C | phase-specific | `docs/STATE_CONTRACT.md` | Study/work memory rules. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_study_work_vocab_pack.md` | C | phase-specific | content JSON | Study/work vocab pack. Relocated in Phase C2D3-core candidate; authority unchanged. |
| `docs/archive/specs/mandarinos_travel_engine_v4.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Travel engine v4. Relocated in Phase C2D3-core candidate; authority unchanged. |

## 18. Audit traceability

Inventory commands:

```bash
git ls-files "*.md" "*.txt" "*.rst"
git ls-files ".cursor/rules/*"
git grep -n "LOCKED"   # and FINAL / MASTER / CURRENT / supersed / Phase
git log --format="%ad %H %s" --date=short -- <path>
```

Counting rule: every file tracked by Git matching `*.md`, `*.txt`, or `*.rst`, plus the two tracked `.cursor/rules/*.mdc` coding-rule files, counted once. This index (`docs/DOCUMENT_AUTHORITY_INDEX.md`) is now itself a tracked Markdown file and is included. Rerunning `git ls-files "*.md" "*.txt" "*.rst"` returned **225** files; the two `.mdc` rule files (classified in §5 and inventoried in §17.12) bring the documentation surface to **227** classified files.

- Total tracked documentation files (glob `*.md`/`*.txt`/`*.rst`): 225
- Plus `.cursor/rules/*.mdc`: 2
- **Total classified: 227**

Counts by primary classification (verified from §17 rows):

| Code | Classification | Count |
| ---- | -------------- | ----- |
| A | Authoritative — approved R2 governance (incl. this index) | 9 |
| B | Current supporting guidance | 20 |
| C | Historical context | 112 |
| D | Superseded | 10 |
| E | Archival evidence / dated report | 38 |
| F | Proposal / plan / unimplemented spec | 22 |
| G | Generated / procedural artefact | 20 |
| H | Unresolved | 0 |
| — | **Total** | **231** |

Secondary flag `status-header-added`: a standard `MANDARINOS-DOCUMENT-STATUS` notice has been inserted into the file without changing its primary classification or original body content. This flag records notice insertion only; it does not elevate authority and does not change the file's A–H classification. If the notice is later removed, this flag must be removed in the same change; it must be updated in the same change as any future notice insertion or removal.

Secondary flag `generated-guidance-added`: a `MANDARINOS-GENERATED-OUTPUT` maintenance header has been prepended to a generated or captured output without changing its primary classification or original body content. This flag records generated-output guidance only; it does not make the output current authority.

Exact counts by secondary flag (generated from the final §17 rows; only used flags are shown):

| Flag | Count |
| ---- | ----- |
| `phase-specific` | 107 |
| `implementation-not-verified` | 39 |
| `dated-snapshot` | 40 |
| `duplicate-or-near-duplicate` | 13 |
| `misleading-filename` | 12 |
| `status-header-added` | 79 |
| `contains-current-material` | 13 |
| `generated` | 8 |
| `generated-guidance-added` | 8 |
| `mixed-current-and-historical` | 3 |
| `partially-implemented` | 3 |
| `contains-obsolete-material` | 2 |
| `branch-specific` | 1 |

Other totals:

- Misleading-title register rows: 12 (§11) — equal to the 12 `misleading-filename` inventory flags.
- Duplicate/overlap groups: 9 (§12) — collectively covering all 13 `duplicate-or-near-duplicate` inventory flags (a group may cover several flagged files).
- `generated` flag count (8) is deliberately lower than the class-G total (20): authored/procedural G artefacts (templates, marketing collateral) are not flagged `generated`.
- `status-header-added` (79) covers the 12-file Phase B1, 8-file Phase B2, 11-file Phase B3A, 11-file Phase B3B, 12-file Phase B4A, 10-file Phase B4B reports-directory, 8-file Phase B4C briefing, 5-file Phase B4D final class-E sets (§15), and the 2-file Phase B5A individual-notice set (§15), all approved; it does not change the 12-file misleading-title register in §11, and no file was removed from that register because a notice was added. Exactly 79 documents carry approved notices. All 36 class-E documents are covered; Phase B4 is complete. Phase B5A is approved. Phase B5B is approved: three guides cover 31 files (two new class-B guides; one existing class-C README hosts prepended family guidance without reclassification). `status-header-added` remains 79. Phase B5C is approved: eight generated rows carry approved guidance; `generated-guidance-added` equals 8. Phase B5D is approved: 46 documents mapped in §13.1 without target modification or reclassification. Phase B closeout is approved and complete (§15). Phase B is complete. All 22 class-F documents carry the flag through completed Phase B3.
- `generated-guidance-added` (8) covers the eight class-G generated/captured output files with Phase B5C approved headers (§15); equal to the eight `generated` inventory flags.
- Phase C1 (§15) adds one new class-E document, `docs/PHASE_C1_ARCHIVAL_AUDIT.md`, taking class E from 37 to 38 and `dated-snapshot` from 39 to 40; total inventory moves from 230 to 231. No pre-existing row's class or flags changed. Phase C1 is approved 2026-07-14. Phase C2A (§15) is approved and complete: 17 class-C directive paths relocated from `docs/directives/` to `docs/archive/directives/`; inventory total remains 231 (path replacement only). Phase C2B (§15) is approved and complete: 11 class-C phase paths relocated from `docs/phases/` to `docs/archive/phases/`; inventory total remains 231. Phase C2C-core (§15) is approved and complete: 20 class-C briefing paths relocated from `docs/briefings/` to `docs/archive/briefings/`; inventory total remains 231. Phase C2C-review (§15) is approved and complete: 8 class-C briefing paths relocated from `docs/briefings/` to `docs/archive/briefings/`; inventory total remains 231 (path replacement only). Phase C2D1 (§15) is approved and complete: 6 class-C early-design paths relocated from `docs/design/` to `docs/archive/design-history/`; inventory total remains 231 (path replacement only). Phase C2D2 (§15) is approved and complete: 10 class-D superseded paths relocated from `docs/design/`, `docs/project/`, and `docs/specs/` to `docs/archive/superseded/`; inventory total remains 231 (path replacement only). Phase C2D3-core (§15) is a **candidate** (not yet approved): 32 class-C historical specification paths relocated from `docs/specs/` to `docs/archive/specs/`; inventory total remains 231 (path replacement only). C2D3-review and later Phase C2 batches have not begun. Phase C remains incomplete.
- Unresolved classifications: 0 (§10).

Principal Git-history range inspected: Phase 6 (2026-03) through the R2 baseline (2026-07-12), including `7ad0e56` (Phase 7 restructure), `083d3c2` (Phase 10 memory/persona), and `3be0315` (R2 baseline).

Principal approved documents used: the nine-document approved R2 governance package (§4), including this index as the ninth authoritative document, plus `.cursor/rules/mandarinos-architecture.mdc` and `.cursor/rules/mandarinos-ui-objects.mdc` for cross-reference verification.

Principal conflicts identified:

- "Authoritative" headings on `AI_CONTEXT.md` and `MANDARINOS_SYSTEM_MAP.md` predate and are subordinate to the approved R2 governance documents;
- `docs/design/CURSOR_STARTUP_PROTOCOL.md` onboarding order is superseded by `docs/ARCHITECTURE.md` §21 and §13 here;
- the Phase 2–7 trace/card/conformance system (directives, TRACE_CONTRACT, integration kit) is not wired into the current conversation turn path (no `TraceBuilder`/`trace_exporter` in `ui/app.js`; no trace-contract references in `*.py`);
- `docs/specs/MandarinOS_master_AI_bootstrap_context.md` is superseded by `AI_CONTEXT.md`; multiple project-plan versions and `conversation_*_v1` models are superseded by the v2 roadmap and the R2 contracts;
- `LOCKED`-labelled selector/capability specs are design-phase; actual behaviour lives in code plus `docs/CONVERSATION_ARCHITECTURE.md`;
- GitHub Copilot is retired, but `.github/copilot-instructions.md` remains tracked.

Classification date: `2026-07-13`

Application baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Application baseline tag: `architecture-baseline-2026-07-12-r2`
Documentation branch: `docs/architecture-v1`
Document status: `Approved v1 — R2 baseline`
Last verified date: `2026-07-13`
