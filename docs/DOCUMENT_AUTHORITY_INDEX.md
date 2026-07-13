# MandarinOS Document Authority Index

## 1. Purpose and authority

This document classifies every tracked documentation file in the repository so that maintainers and AI coding agents can tell current authority from historical, supporting, evidentiary, proposed, or generated material.

This document:

- is the authority for **classifying** project documentation;
- does **not** override verified code or the detailed R2 contracts — it ranks documents, it does not restate their behaviour;
- prevents historical and supporting documents from being mistaken for current authority merely because a filename sounds authoritative;
- governs future document classification and cleanup.

Application baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Application baseline tag: `architecture-baseline-2026-07-12-r2`

> A document's filename records what someone once called it. Its classification records what maintainers may rely on now.

## 2. Authority hierarchy

Highest to lowest:

1. verified production code and executable behaviour at the relevant baseline;
2. the eight approved R2 governance documents (§4);
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
| F | Proposal, plan, or unimplemented specification | Only the verified-implemented subset | No | Track implementation status; cross-reference ADR deferred register |
| G | Generated or procedural artefact | No | No | Regenerate or delete per its workflow |
| H | Unresolved — authority cannot yet be established | No | No | Investigate; do not rely on until resolved |

## 4. Approved R2 authority set

These eight — and only these eight — are classified **A** at this phase.

| Document | Role | Status | Baseline | Update trigger |
| -------- | ---- | ------ | -------- | -------------- |
| `docs/ARCHITECTURE.md` | orientation map | Approved v1 — R2 | `3be0315` | Any onboarding/system-orientation change |
| `docs/CONVERSATION_ARCHITECTURE.md` | conversation behavioural contract | Approved v1 — R2 | `3be0315` | Selector/frame/engine/ordering change |
| `docs/STATE_CONTRACT.md` | state behavioural contract | Approved v1 — R2 | `3be0315` | Any state field/transport/reset/persistence change |
| `docs/ANSWER_SOURCE_CONTRACT.md` | answer-source behavioural contract | Approved v1 — R2 | `3be0315` | Priority chain/producer/finalisation change |
| `docs/ASR_PIPELINE.md` | ASR/input behavioural contract | Approved v1 — R2 | `3be0315` | ASR/TTS/recovery-interception change |
| `docs/TEST_STRATEGY.md` | evidence contract | Approved v1 — R2 | `3be0315` | Test architecture/evidence-ranking change |
| `docs/CHANGE_CHECKLIST.md` | operational change-control checklist | Approved v1 — R2 | `3be0315` | Workflow/deployment/verification change |
| `docs/ARCHITECTURAL_DECISIONS.md` | architectural-decision record | Approved v1 — R2 | `3be0315` | New/changed/superseded architectural decision |

## 5. Current supporting guidance (B)

Subordinate to the eight authoritative documents. None of these may override a behavioural contract or ADR.

| Path | Purpose | Why still current | Subordinate to | Known limitations | Secondary flags |
| ---- | ------- | ----------------- | -------------- | ----------------- | --------------- |
| `README.md` | Repo entry/quick-start | Start command, tech stack, key files still accurate | `docs/ARCHITECTURE.md` | Points to golden-regression test as primary; incomplete vs contracts | contains-current-material |
| `AI_CONTEXT.md` | AI orientation map | Project goal, guardrails, repo map still broadly valid | Eight A documents | Header says "Authoritative"; "Phase 11" era; references superseded plan paths | mixed-current-and-historical, misleading-filename |
| `MANDARINOS_SYSTEM_MAP.md` | Pipeline mental model | Lexicon→builder→runtime→UI framing still useful | `docs/ARCHITECTURE.md` | "Authoritative" label; trace-contract framing is legacy (not wired to conversation runtime) | mixed-current-and-historical, misleading-filename |
| `docs/DEVELOPER_ONBOARDING.md` | Developer/hosting guide | Architecture, hosting, API overview broadly current | `docs/ARCHITECTURE.md`, `docs/CHANGE_CHECKLIST.md` | Dated 2026-05-11; specific test counts/line counts drift | contains-obsolete-material |
| `docs/MANDARINOS_REGRESSION_LOCK.md` | Protected-behaviour register | Records real regression guards + golden-regression suite | `docs/TEST_STRATEGY.md` | "LOCK" is not authority; interpret evidence per TEST_STRATEGY | misleading-filename, contains-current-material |
| `docs/RESPONSE_OPTION_STYLE_GUIDE.md` | Learner-option style rules | Current rules for response options | `docs/ANSWER_SOURCE_CONTRACT.md` | References a 2026-05 audit for open violations | contains-current-material |
| `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md` | Flow/anti-pattern design | Cited by `.cursor/rules` as read-first for flow changes | `docs/CONVERSATION_ARCHITECTURE.md` | Dated 2026-04-05; behaviour authority is the contract | contains-current-material |
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | Extensibility directive | Cited by `.cursor/rules` as full directive | `docs/ARCHITECTURAL_DECISIONS.md` | Canonical copy (a duplicate exists under `docs/briefings/`) | duplicate-or-near-duplicate |
| `docs/specs/MandarinOS_Extensibility_Strategy.md` | Extensibility strategy | Cited by `.cursor/rules` as strategy doc | `docs/ARCHITECTURAL_DECISIONS.md` | Strategy, not behavioural authority | contains-current-material |
| `docs/design/mandarinos_design_constitution.txt` | Product design constitution | Referenced as non-negotiable product philosophy | Eight A documents | Older phrasing; philosophy retained, specifics may drift | mixed-current-and-historical |
| `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md` | AI governance model | Referenced by `AI_CONTEXT.md`/startup docs | Eight A documents | v1; predates R2 governance package | contains-current-material |
| `docs/design/LICENSE.md` | Copyright/licence | Current legal statement | — | — | — |
| `runtime/README_runtime_indexes.txt` | Runtime-index definitions | Explains index defs vs computed outputs | `docs/ARCHITECTURE.md` §14 | Notes a legacy computed snapshot | contains-current-material |
| `conformance/README.md` | Conformance-runner usage | `conformance/run_trace_conformance.py` exists and runs | `docs/TEST_STRATEGY.md` | Trace conformance is a side tool, not wired into the conversation turn path | branch-specific |
| `requirements.txt` | Runtime dependency manifest | Consumed by install/deploy | repo configuration | Manifest, not governance prose | contains-current-material |
| `requirements-tools.txt` | Optional-tooling deps | Consumed for translation/pinyin tooling | repo configuration | Optional-only | contains-current-material |
| `.cursor/rules/mandarinos-architecture.mdc` | Standing architectural coding rules | Enforced for agents; agrees with contracts | `docs/ARCHITECTURAL_DECISIONS.md`, `docs/CONVERSATION_ARCHITECTURE.md` | Rule guidance, not behavioural authority | contains-current-material |
| `.cursor/rules/mandarinos-ui-objects.mdc` | UI standard-object coding rules | Enforced for agents; matches `ui/app.js` render path | `docs/ARCHITECTURE.md` | Narrow UI-render scope | contains-current-material |

## 6. Historical and superseded documents

Enumerated exhaustively in §17. This section states the classification basis and, for superseded files, the named replacement.

### 6.1 Historical context (C)

Retained for rationale; not current implementation guidance. Read with date/phase context.

| Family (see §17 for every path) | Members | Classification reason | Current authority | Secondary flags |
| ------------------------------- | ------- | --------------------- | ----------------- | --------------- |
| `docs/briefings/*` strategist/phase briefings | 28 | Phase-era strategy/hand-off narratives | Eight A documents | phase-specific, contains-obsolete-material |
| `docs/directives/*` cards/trace/harness directives | 17 | Phase 2–7 implementation directives | `docs/CHANGE_CHECKLIST.md`; code | phase-specific, implementation-not-verified |
| `docs/specs/*` engine/ladder/pack/model design specs | 38 | Design-phase specs; engines now live in code + contracts | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/ANSWER_SOURCE_CONTRACT.md` | phase-specific, contains-obsolete-material |
| `docs/phases/*` phase notes/freezes/locks | 11 | Phase milestones/locks | `docs/ARCHITECTURE.md`; ADRs | phase-specific, misleading-filename |
| `docs/design/*` early design docs | 6 | Cards/trace/UX design era | `docs/ARCHITECTURE.md` | phase-specific |
| `docs/project/*` notes/references/directive | 6 | Phase notes and reference material | Eight A documents | phase-specific |
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

Only a verified-implemented subset (if any) may guide current work. Implementation is not inferred from status language.

| Family (see §17 for every path) | Members | Implementation status | Current decision/ADR | Secondary flags |
| -------------------------------- | ------- | --------------------- | -------------------- | --------------- |
| `docs/plans/*` implementation plans | 3 | Unable to verify from docs; treat as planned | `docs/ARCHITECTURAL_DECISIONS.md` §6 register | implementation-not-verified |
| `docs/project/MandarinOS_project_plan_v2*.md` roadmaps | 3 | v2 is the cited current roadmap; `_CORRECTED`/`_UPDATED` are variants | ADR record for decisions | duplicate-or-near-duplicate, implementation-not-verified |
| `docs/specs/PHASE_10_5_*`, `PHASE_12C_*` plans/briefs/invariants | 5 | Partially implemented across phases; not verified per item | Contracts; ADR deferred register | partially-implemented, implementation-not-verified |
| `docs/specs/*UI_SPEC*`, `*Hybrid_Speech*` specs | 3 | Hybrid speech deferred (ADR-014/ADR-009); UI specs partial | `docs/ASR_PIPELINE.md`; ADR-014 | implementation-not-verified |
| `docs/phases/*PROPOSAL*/*PLAN*/*MAPPING*` | 3 | Planning artefacts; subset implemented | Contracts; ADRs | implementation-not-verified |
| `docs/design/SCENARIOS_REQUIRED_v1.md`, `MANDARINOS_PHASE_12_HYBRID_AI_CONCEPT_BRIEFING.txt` | 2 | Scenarios/hybrid concept; hybrid unimplemented | ADR-014 (deferred) | implementation-not-verified |
| `docs/REPO_STRUCTURE_PROPOSAL.md`, `docs/SCHEMA_SYNC_RECOMMENDATION.md`, `docs/session_intelligence_architecture.md` | 3 | Not executed / partially (session slice 1) | — | implementation-not-verified, partially-implemented |
| `docs/project/RECOVERY_AND_CONVERSATION_FUTURE_NOTES.md` | 1 | Forward-looking notes | ADR deferred register | implementation-not-verified |

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
| `AI_CONTEXT.md` | "Authoritative" (heading) | B | Orientation map, subordinate to the eight A documents | `docs/ARCHITECTURE.md` |
| `MANDARINOS_SYSTEM_MAP.md` | "Authoritative" (heading) | B | Pipeline map; trace framing legacy | `docs/ARCHITECTURE.md` |
| `docs/MANDARINOS_REGRESSION_LOCK.md` | `LOCK` | B | Behaviour register, not authority; evidence per TEST_STRATEGY | `docs/TEST_STRATEGY.md` |
| `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` | `LOCK` | C | Phase 6 lock, superseded by R2 architecture | `docs/ARCHITECTURE.md` |
| `docs/phases/PHASE6_FREEZE.md` | `FREEZE` | C | Phase 6 freeze snapshot | `docs/ARCHITECTURE.md` |
| `docs/specs/MandarinOS_master_AI_bootstrap_context.md` | `master` | D | Bootstrap role replaced | `AI_CONTEXT.md` |
| `docs/specs/MandarinOS_next_question_selector_v1.md` | `LOCKED` (heading) | C | Design spec; selector logic lives in code + contract | `docs/CONVERSATION_ARCHITECTURE.md` |
| `docs/specs/MandarinOS_capability_update_rules_v1.md` | `LOCKED` (heading) | C | Design spec; behaviour authority is code + contract | `docs/CONVERSATION_ARCHITECTURE.md` |
| `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` | Marks specs `LOCKED` | C | Index of design specs, not current authority | `docs/ARCHITECTURE.md` |
| `docs/design/CURSOR_STARTUP_PROTOCOL.md` | "Status: ACTIVE" | D | Onboarding order superseded | `docs/ARCHITECTURE.md` §21 |
| `docs/state/MANDARINOS_SYSTEM_STATE_PHASE_12B.md` | "Constraints (LOCKED)" | E | Dated state snapshot | `docs/STATE_CONTRACT.md` |

## 12. Duplicate and overlap register

No file is deleted or merged in this phase.

| Documents | Relationship | Canonical/current file | Classification of others | Future cleanup action |
| --------- | ------------ | ---------------------- | ------------------------ | --------------------- |
| `docs/project/MANDARINOS_PROJECT_PLAN_v1.md`, `MandarinOS_project_plan_v2.md`, `_v2_CORRECTED.md`, `_v2_UPDATED.md` | Roadmap versions/variants | `MandarinOS_project_plan_v2.md` | v1 = D; CORRECTED/UPDATED = F | Consolidate to one roadmap after owner review |
| `docs/project/COMMIT_SUMMARY.md`, `COMMIT_SUMMARY_v1.md` | Dated commit summaries | Neither (both dated) | Both E | Retain as dated evidence |
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md`, `docs/briefings/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | Identical copies | `docs/specs/…` (cited by `.cursor/rules`) | specs = B; briefings copy = C | Remove/redirect duplicate after link check |
| `docs/specs/MandarinOS_conversation_memory_model_v1.md`, `_v2.md` | Version pair | v2 | v1 = D; v2 = C | Authority is `docs/STATE_CONTRACT.md` |
| `docs/specs/mandarinos_family_conversation_ladder.md`, `_v2.md` | Version pair | v2 | v1 = D; v2 = C | — |
| `docs/phases/MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md`, `docs/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md` | Near-duplicate | Neither current | Both C | De-duplicate after review |
| `docs/Social_Media/mandarinos-marp-template.md`, `mandarinos-marp-template 1.md` | Duplicate template | `mandarinos-marp-template.md` | Both G | Remove the " 1" copy |
| `docs/specs/mandarinos_conversation_architecture_v1.md`, `MandarinOS_conversation_system_blueprint_v1.md`, `MandarinOS_conversation_runtime_model_v1.md` | Overlap current conversation contract | `docs/CONVERSATION_ARCHITECTURE.md` | v1/blueprint/runtime = D/C | Archive after R2 stability |
| `AI_CONTEXT.md`, `MANDARINOS_SYSTEM_MAP.md`, `docs/specs/MandarinOS_master_AI_bootstrap_context.md` | Overlapping orientation maps | `docs/ARCHITECTURE.md` | AI_CONTEXT/SYSTEM_MAP = B; bootstrap = D | Point orientation maps at ARCHITECTURE |

## 13. Reading path for a new maintainer

1. `docs/ARCHITECTURE.md`
2. the applicable detailed behavioural contracts (`docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md`, `docs/ASR_PIPELINE.md`);
3. `docs/TEST_STRATEGY.md`;
4. `docs/CHANGE_CHECKLIST.md`;
5. `docs/ARCHITECTURAL_DECISIONS.md`;
6. this document authority index;
7. current supporting guidance (§5) as needed;
8. historical documents (§6) only for context.

An AI coding agent must **not** begin from a historical phase lock, briefing, or recovery report. It must diagnose against verified code and the eight A documents, and treat everything in §6–§9 as context or evidence, never as behavioural authority.

## 14. Rules for creating future documents

Every future durable document must declare:

- title;
- purpose;
- owner or responsible role;
- status;
- behavioural/application baseline;
- last verified date;
- relationship to the eight-document R2 governance package;
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
Potentially add standard headers to historical (C), superseded (D), proposal (F), and report (E) files.

### Phase C — physical archive
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
| `AI_CONTEXT.md` | B | mixed-current-and-historical, misleading-filename | `docs/ARCHITECTURE.md` | "Authoritative" label overstated; Phase 11 era |
| `MANDARINOS_SYSTEM_MAP.md` | B | mixed-current-and-historical, misleading-filename | `docs/ARCHITECTURE.md` | Pipeline map; trace framing legacy |
| `README.md` | B | contains-current-material | — | Current quick-start/tech stack |
| `requirements.txt` | B | contains-current-material | repo config | Runtime dependency manifest |
| `requirements-tools.txt` | B | contains-current-material | repo config | Optional tooling deps |
| `fo_check.txt` | G | generated, dated-snapshot | — | Captured command error output |
| `frame_dump.txt` | G | generated | — | Frame-order dump |
| `frame_texts.txt` | G | generated | — | Frame-text dump (encoding artefacts) |
| `server_out.txt` | G | generated | — | Server stdout capture |
| `server_err.txt` | G | generated | — | Server stderr capture |
| `server_startup_err.txt` | G | generated | — | Startup stderr capture |
| `.github/copilot-instructions.md` | C | contains-obsolete-material, misleading-filename | `AI_CONTEXT.md`, `.cursor/rules/*`, `docs/CHANGE_CHECKLIST.md` §23 | Copilot retired; Cursor ops moved |
| `conformance/README.md` | B | branch-specific | `docs/TEST_STRATEGY.md` | Conformance runner exists; side tool |
| `runtime/README_runtime_indexes.txt` | B | contains-current-material | `docs/ARCHITECTURE.md` §14 | Index defs vs computed |
| `scripts/_engine_audit.txt` | G | generated | — | Engine/frame audit output |
| `tools/coverage/coverage_report.md` | G | generated | — | Content coverage scanner output |

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
| `docs/DEVELOPER_ONBOARDING.md` | B | contains-obsolete-material | `docs/ARCHITECTURE.md` | 2026-05-11; counts drift |
| `docs/MANDARINOS_REGRESSION_LOCK.md` | B | misleading-filename, contains-current-material | `docs/TEST_STRATEGY.md` | Regression-guard register |
| `docs/RESPONSE_OPTION_STYLE_GUIDE.md` | B | contains-current-material | `docs/ANSWER_SOURCE_CONTRACT.md` | Option style rules |
| `docs/REPO_STRUCTURE_PROPOSAL.md` | F | implementation-not-verified | — | Proposed layout; not executed |
| `docs/SCHEMA_SYNC_RECOMMENDATION.md` | F | implementation-not-verified, duplicate-or-near-duplicate | — | Two schema dirs still exist |
| `docs/session_intelligence_architecture.md` | F | partially-implemented | — | Slice 1 implemented; rest proposal |
| `docs/session_intelligence_implementation_report.md` | E | dated-snapshot | — | Implementation report |

### 17.3 `docs/design/`

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/design/mandarinos_design_constitution.txt` | B | mixed-current-and-historical | Eight A docs | Product philosophy retained |
| `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md` | B | contains-current-material | Eight A docs | AI governance model |
| `docs/design/LICENSE.md` | B | — | — | Copyright statement |
| `docs/design/CURSOR_STARTUP_PROTOCOL.md` | D | misleading-filename | `docs/ARCHITECTURE.md` §21 | Onboarding order superseded |
| `docs/design/CARDS_BUILD_v1.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Cards-build era |
| `docs/design/TRACE_CONTRACT_v1.md` | C | phase-specific, implementation-not-verified | `docs/ARCHITECTURE.md` | Trace contract not in conversation runtime |
| `docs/design/p3_architecture.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Early architecture |
| `docs/design/ux_flow.txt` | C | phase-specific | `docs/ARCHITECTURE.md` | Early UX flow |
| `docs/design/MandarinOS_brief.md` | C | phase-specific | `docs/ARCHITECTURE.md` | Early project brief |
| `docs/design/MandarinOS Developer Handoff.txt` | C | phase-specific | `docs/DEVELOPER_ONBOARDING.md` | Early handoff |
| `docs/design/SCENARIOS_REQUIRED_v1.md` | F | implementation-not-verified | — | Required-scenarios spec |
| `docs/design/MANDARINOS_PHASE_12_HYBRID_AI_CONCEPT_BRIEFING.txt` | F | implementation-not-verified | ADR-014 (deferred) | Hybrid-AI concept |

### 17.4 `docs/briefings/`

| Path | Class | Flags | Notes |
| ---- | ----- | ----- | ----- |
| `docs/briefings/BRIEFING_CHANGES_FOR_CHATGPT_REVIEW.md` | C | phase-specific | Review briefing |
| `docs/briefings/CHATGPT_STRATEGIST_CONVERSATION_DESIGN_BRIEFING.md` | C | phase-specific | Strategist briefing |
| `docs/briefings/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | C | duplicate-or-near-duplicate | Duplicate of `docs/specs/` canonical |
| `docs/briefings/MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt` | C | phase-specific | Move-type brief |
| `docs/briefings/MANDARINOS_PHASE_10_7_PHASE_11_BRIEFING.txt` | C | phase-specific | Phase 10.7/11 briefing |
| `docs/briefings/MandarinOS_Phase12D_Cursor_Implementation_Brief.md` | C | phase-specific, implementation-not-verified | Phase 12D brief |
| `docs/briefings/MandarinOS_Phase12E_CuriosityProbe_Brief.md` | C | phase-specific, implementation-not-verified | Phase 12E brief |
| `docs/briefings/MandarinOS_Phase_12C_Alignment_Brief.md` | C | phase-specific | Phase 12C alignment |
| `docs/briefings/MandarinOS_laptop_handoff_UI_cascading_help_briefing.md` | C | phase-specific | Handoff briefing |
| `docs/briefings/NEXT_PHASE_ADVICE_CURSOR.md` | C | phase-specific | Next-phase advice |
| `docs/briefings/PHASE10_STRATEGIST_BRIEFING_SPECS_GAP_AND_PATH.md` | C | phase-specific | Phase 10 briefing |
| `docs/briefings/PHASE7_4_UI_POLISH_STRATEGIST_BRIEFING.md` | C | phase-specific | Phase 7.4 briefing |
| `docs/briefings/PHASE7_COMPLETE_STRATEGIST_BRIEFING.md` | C | phase-specific | Phase 7 briefing |
| `docs/briefings/PHASE8_OPTIONS_APPROPRIATENESS.md` | C | phase-specific | Phase 8 briefing |
| `docs/briefings/PHASE8_STEP1_TRANSCRIPT_ARCHITECTURE.md` | C | phase-specific | Phase 8 transcript arch |
| `docs/briefings/PHASE9_SIGNOFF_STRATEGIST_BRIEFING.md` | C | phase-specific | Phase 9 sign-off |
| `docs/briefings/PHASE_10_5_10_6_ALPHA_STRATEGIST_BRIEFING.md` | C | phase-specific | Phase 10.5/10.6 briefing |
| `docs/briefings/PHASE_12B_STABILIZATION_AND_UI_FLOW_STRATEGIST_BRIEFING.md` | C | phase-specific | Phase 12B briefing |
| `docs/briefings/PHASE_12C_EXECUTIVE_STRATEGIST_BRIEF.md` | C | phase-specific | Phase 12C exec brief |
| `docs/briefings/PHASE_12C_STRATEGIST_PROPOSAL_CURIOSITY_PERSONA_SESSION_ARC.md` | C | phase-specific, implementation-not-verified | Phase 12C proposal briefing |
| `docs/briefings/STRATEGIST_BRIEFING_MAY2026_UI_POLISH_AND_DISTANCE_THREAD.md` | C | phase-specific | May 2026 briefing |
| `docs/briefings/UI_SHELL_STRATEGIST_BRIEFING_APR2026.md` | C | phase-specific | Apr 2026 briefing |
| `docs/briefings/USER_LED_DISCOVERY_STRATEGIST_BRIEF.md` | C | phase-specific | Discovery briefing |
| `docs/briefings/architecture_briefing_apr2026.md` | C | phase-specific | Apr 2026 architecture briefing |
| `docs/briefings/mandarinos_chatgpt_session_briefing.md` | C | phase-specific | Session briefing |
| `docs/briefings/mandarinos_recovery_phrases_v1_2_cursor_briefing.txt` | C | phase-specific | Recovery-phrase briefing |
| `docs/briefings/phase12c_recovery_trigger_briefing.txt` | C | phase-specific | Phase 12C recovery trigger |
| `docs/briefings/phase7_3_senior_architect_briefing.md` | C | phase-specific | Phase 7.3 briefing |
| `docs/briefings/bridge_audit_apr2026.md` | E | dated-snapshot | Bridge audit (Apr 2026) |
| `docs/briefings/engine_audit_apr2026.md` | E | dated-snapshot | Engine audit (Apr 2026) |
| `docs/briefings/implementation_report_apr2026.md` | E | dated-snapshot | Implementation report (Apr 2026) |
| `docs/briefings/PHASE7_COMPLETION_REVIEW_AND_TEST.md` | E | dated-snapshot | Phase 7 completion review |
| `docs/briefings/PHASE10_STRATEGIST_REVIEW.md` | E | dated-snapshot | Phase 10 review |
| `docs/briefings/CONVERSATION_ARCHITECTURE_ASSESSMENT.md` | E | dated-snapshot | Architecture assessment |
| `docs/briefings/UI_CONVERSATION_LOOP_ASSESSMENT.md` | E | dated-snapshot | UI loop assessment |
| `docs/briefings/PHASE7_SCHEMA_DISCOVERIES.md` | E | dated-snapshot | Schema-discovery findings |

### 17.5 `docs/directives/`

All Phase 2–7 cards/trace/harness implementation directives. Classification C; flags `phase-specific, implementation-not-verified`; current authority `docs/CHANGE_CHECKLIST.md` + code.

| Path | Class | Notes |
| ---- | ----- | ----- |
| `docs/directives/MANDARINOS_ARCHITECT_COPILOT_HANDOFF_DIRECTIVE_PHASE7.txt` | C | Phase 7 handoff directive |
| `docs/directives/MANDARINOS_COPILOT_STARTUP_INSTRUCTIONS.txt` | C | Copilot startup (retired tool) |
| `docs/directives/MandarinOS_OPEN_CARD_Trace_Wiring_Directive.txt` | C | Card trace wiring |
| `docs/directives/MandarinOS_OPEN_CARD_Unit_Test_Directive.txt` | C | Card unit-test directive |
| `docs/directives/MandarinOS_Phase_Boundaries_v1.0.txt` | C | Phase boundaries |
| `docs/directives/MandarinOS_Runtime_Card_Integration_Directive.txt` | C | Runtime card integration |
| `docs/directives/MandarinOS_Simulator_Entrypoint_Copilot_Directive.txt` | C | Simulator entrypoint |
| `docs/directives/MandarinOS_TurnState_Trace_Contract_v1_directive.txt` | C | TurnState trace contract |
| `docs/directives/MandarinOS_UI_Shell_Copilot_Directive.txt` | C | UI shell directive |
| `docs/directives/MandarinOS_card_contract_v1_directive.txt` | C | Card contract |
| `docs/directives/MandarinOS_conformance_harness_directive.txt` | C | Conformance harness |
| `docs/directives/MandarinOS_content_coverage_scanner_v1_directive.txt` | C | Coverage scanner |
| `docs/directives/MandarinOS_hint_cascade_directive.txt` | C | Hint cascade |
| `docs/directives/MandarinOS_integration_kit_scenarios_v1_directive.txt` | C | Integration-kit scenarios |
| `docs/directives/MandarinOS_scaffolding_transition_harness_v1_directive.txt` | C | Scaffolding transition harness |
| `docs/directives/MandarinOS_universal_cards_builder_v1_directive.txt` | C | Universal cards builder |
| `docs/directives/mandarinos_copilot_architecture_update.txt` | C | Copilot architecture update |

### 17.6 `docs/phases/`

| Path | Class | Flags | Notes |
| ---- | ----- | ----- | ----- |
| `docs/phases/MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md` | C | phase-specific, duplicate-or-near-duplicate | Near-dup of `PHASE9_1_ACCEPTANCE_CRITERIA.md` |
| `docs/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md` | C | phase-specific, duplicate-or-near-duplicate | Near-dup |
| `docs/phases/MANDARINOS_PHASE_10_5_STABILISATION_BRIEF.md` | C | phase-specific | Phase 10.5 stabilisation |
| `docs/phases/MandarinOS_Phase9_Signoff.md` | C | phase-specific | Phase 9 sign-off |
| `docs/phases/PHASE6_FREEZE.md` | C | phase-specific, misleading-filename | Phase 6 freeze |
| `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` | C | phase-specific, misleading-filename | Phase 6 lock |
| `docs/phases/PHASE6_RUNTIME_INDEXES_NOTES.md` | C | phase-specific | Phase 6 runtime-index notes |
| `docs/phases/PHASE9_2_BRIDGE_TIER.md` | C | phase-specific | Phase 9.2 bridge tier |
| `docs/phases/PHASE_10_5_CONVERSATION_SIMULATION.md` | C | phase-specific | Phase 10.5 simulation |
| `docs/phases/Phase 3 Step 1 Audio-first UI.md` | C | phase-specific | Phase 3 audio-first UI |
| `docs/phases/ROLLBACK_POINT_v1.md` | C | phase-specific, dated-snapshot | Rollback point |
| `docs/phases/PHASE10_TECHNICAL_PROPOSAL.md` | F | implementation-not-verified | Phase 10 technical proposal |
| `docs/phases/PHASE9_CONTENT_AND_ENGINES_PLAN.md` | F | implementation-not-verified | Phase 9 content/engines plan |
| `docs/phases/PHASE_10_5_MAPPING_AND_SCHEMA_PROPOSAL.md` | F | implementation-not-verified | Phase 10.5 mapping/schema proposal |

### 17.7 `docs/plans/`

| Path | Class | Flags | Notes |
| ---- | ----- | ----- | ----- |
| `docs/plans/PHASE_10_7_MINIMAL_IMPLEMENTATION_PLAN.md` | F | implementation-not-verified | Phase 10.7 minimal plan |
| `docs/plans/component_radical_gloss_plan.md` | F | implementation-not-verified | Component/radical gloss plan |
| `docs/plans/learner_etymology_hints_plan.md` | F | implementation-not-verified | Etymology-hints plan |

### 17.8 `docs/project/`

| Path | Class | Flags | Notes |
| ---- | ----- | ----- | ----- |
| `docs/project/MandarinOS_project_plan_v2.md` | F | implementation-not-verified | Cited current roadmap (v2) |
| `docs/project/MandarinOS_project_plan_v2_CORRECTED.md` | F | duplicate-or-near-duplicate | Roadmap variant |
| `docs/project/MandarinOS_project_plan_v2_UPDATED.md` | F | duplicate-or-near-duplicate | Roadmap variant |
| `docs/project/MANDARINOS_PROJECT_PLAN_v1.md` | D | duplicate-or-near-duplicate | Superseded by v2 |
| `docs/project/RECOVERY_AND_CONVERSATION_FUTURE_NOTES.md` | F | implementation-not-verified | Future notes |
| `docs/project/DIRECTIVE_PHASE_1_CARD_PANEL_STATE.md` | C | phase-specific | Phase 1 directive |
| `docs/project/ENGINES_P1_P2_AND_SRS_REFERENCE.md` | C | phase-specific | Engine/SRS reference |
| `docs/project/NEXT_QUESTION_SELECTOR_AND_LEVEL_TIE_IN.md` | C | phase-specific | References LOCKED selector spec |
| `docs/project/PROBE_QUESTIONS_RESPONSE_OPTIONS_NOTE.md` | C | phase-specific | Probe-questions note |
| `docs/project/TEST_DIAGNOSTIC_P1_MANUAL.md` | C | phase-specific | Manual diagnostic procedure |
| `docs/project/USER_TURN_AND_PERSONA_QUESTIONS_NOTE.md` | C | phase-specific | Persona-questions note |
| `docs/project/ARCHITECTURE_ALIGNMENT_OPTIONS_AND_GOLD.md` | E | dated-snapshot | Alignment options analysis |
| `docs/project/AUDIT_OPTION_GENERATION.md` | E | dated-snapshot | Option-generation audit |
| `docs/project/COMMIT_RECORD.md` | E | dated-snapshot | Commit record |
| `docs/project/COMMIT_SUMMARY.md` | E | dated-snapshot, duplicate-or-near-duplicate | Commit summary |
| `docs/project/COMMIT_SUMMARY_v1.md` | E | dated-snapshot, duplicate-or-near-duplicate | Commit summary v1 |
| `docs/project/CORE_TREASURE_BRIDGE_STATUS.md` | E | dated-snapshot | Bridge status report |
| `docs/project/DIAGNOSTIC_P1_VALIDATION_RESULTS.md` | E | dated-snapshot | Diagnostic results |
| `docs/project/EXECUTIVE_SUMMARY_v1.md` | E | dated-snapshot | Executive summary |
| `docs/project/OPTION_GENERATION_FIX_COMPLETE.md` | E | dated-snapshot | Fix-complete report |
| `docs/project/PHASE9_STATUS_AND_RESPONSE_QUALITY.md` | E | dated-snapshot | Phase 9 status |
| `docs/project/SPECS_TO_IMPLEMENTATION_GAP.md` | E | dated-snapshot | Gap analysis |
| `docs/project/TEST_SUMMARY.md` | E | dated-snapshot | Test summary |
| `docs/project/CHATGPT_BRANCH_START_TEMPLATE.md` | G | generated | Workflow template |
| `docs/project/COMMIT_INSTRUCTIONS.md` | G | generated | Procedural instructions |

### 17.9 `docs/reports/`

All classification E, flags `dated-snapshot`; current authority is code + contracts.

| Path | Class | Notes |
| ---- | ----- | ----- |
| `docs/reports/CORPUS_RECOVERY_NOTES.md` | E | Corpus recovery notes |
| `docs/reports/PHASE_11_1_1_OBSERVATION_REPORT.md` | E | Phase 11.1.1 observation |
| `docs/reports/alpha_conversation_observation.md` | E | Alpha observation |
| `docs/reports/capability_mismatch_observation.md` | E | Capability-mismatch observation |
| `docs/reports/component_gloss_coverage.md` | E | Gloss coverage report |
| `docs/reports/counter_reply_matrix_report.md` | E | Counter-reply matrix |
| `docs/reports/move_type_tagging_audit.md` | E | Move-type tagging audit |
| `docs/reports/move_type_tagging_coverage.md` | E | Move-type coverage |
| `docs/reports/move_type_transition_calibration.md` | E | Transition calibration |
| `docs/reports/vocab_character_coverage_audit.md` | E | Vocab/character coverage |

### 17.10 `docs/specs/`

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | B | duplicate-or-near-duplicate | ADR record | Canonical (cited by `.cursor/rules`) |
| `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md` | B | contains-current-material | `docs/CONVERSATION_ARCHITECTURE.md` | Cited read-first for flow |
| `docs/specs/MandarinOS_Extensibility_Strategy.md` | B | contains-current-material | ADR record | Cited strategy doc |
| `docs/specs/mandarinos_conversation_architecture_v1.md` | D | — | `docs/CONVERSATION_ARCHITECTURE.md` | Conceptual spine superseded |
| `docs/specs/MandarinOS_conversation_runtime_model_v1.md` | D | — | `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md` | Runtime model superseded |
| `docs/specs/MandarinOS_runtime_conversation_state_engine_v1.md` | D | — | `docs/STATE_CONTRACT.md` | State engine superseded |
| `docs/specs/MandarinOS_conversation_state_diagram_v1.md` | D | — | `docs/STATE_CONTRACT.md` | State diagram superseded |
| `docs/specs/MandarinOS_turn_data_contract_v1.md` | D | — | `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md` | Turn data contract superseded |
| `docs/specs/MandarinOS_conversation_memory_model_v1.md` | D | duplicate-or-near-duplicate | `_v2`; `docs/STATE_CONTRACT.md` | Superseded by v2 |
| `docs/specs/mandarinos_family_conversation_ladder.md` | D | duplicate-or-near-duplicate | `_v2` | Superseded by v2 |
| `docs/specs/MandarinOS_master_AI_bootstrap_context.md` | D | misleading-filename | `AI_CONTEXT.md` | Bootstrap role replaced |
| `docs/specs/MANDARINOS_CONVERSATION_ARCHITECTURE_AUDIT_v1.md` | E | dated-snapshot | — | Architecture audit |
| `docs/specs/MandarinOS_conversation_expansion_audit_v2.md` | E | dated-snapshot | — | Expansion audit |
| `docs/specs/Translation_Surface_Consistency_Audit.md` | E | dated-snapshot | — | Translation audit |
| `docs/specs/mandarinos_conversation_architecture_audit_request_v2.txt` | E | dated-snapshot | — | Audit request |
| `docs/specs/MandarinOS_Hybrid_Speech_and_Persona_Voice_Architecture.md` | F | implementation-not-verified | ADR-014 (deferred) | Hybrid speech (deferred) |
| `docs/specs/PHASE_10_5_BEHAVIOUR_IMPLEMENTATION_PLAN.md` | F | implementation-not-verified | Contracts | Behaviour plan |
| `docs/specs/PHASE_10_5_INTEREST_RESPONSIVENESS_REFINEMENT_PLAN.md` | F | implementation-not-verified | Contracts | Refinement plan |
| `docs/specs/PHASE_12C_IMPLEMENTATION_BRIEF.md` | F | partially-implemented | Contracts | Phase 12C brief |
| `docs/specs/PHASE_12C_INVARIANTS.md` | F | partially-implemented | Contracts | Phase 12C invariants |
| `docs/specs/MOBILE_WORD_INSIGHT_UI_SPEC.md` | F | implementation-not-verified | `docs/ASR_PIPELINE.md` §14 | Word-insight UI spec |
| `docs/specs/TRANSCRIPT_REPLAY_TRANSLATION_UI_SPEC.md` | F | implementation-not-verified | — | Transcript-replay UI spec |
| `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` | C | misleading-filename | `docs/ARCHITECTURE.md` | Index of design specs |
| `docs/specs/Live_Beginner_Ability_Model.md` | C | phase-specific | Contracts | Ability model |
| `docs/specs/MandarinOS_Conversation_UX_Protocol_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | UX protocol |
| `docs/specs/MandarinOS_Progress_Tracking_Cursor_Spec_v2.md` | C | phase-specific | — | Progress-tracking spec |
| `docs/specs/MandarinOS_Repair_Curiosity_Loop.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Repair/curiosity design |
| `docs/specs/MandarinOS_capability_update_rules_v1.md` | C | misleading-filename | `docs/CONVERSATION_ARCHITECTURE.md` | LOCKED-labelled design spec |
| `docs/specs/MandarinOS_conversation_capability_map_v1.md` | C | phase-specific | — | Capability map |
| `docs/specs/MandarinOS_conversation_ladders_full_draft_v2.md` | C | phase-specific | Contracts | Ladders draft |
| `docs/specs/MandarinOS_conversation_memory_model_v2.md` | C | phase-specific | `docs/STATE_CONTRACT.md` | Memory model (design) |
| `docs/specs/MandarinOS_conversation_system_blueprint_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | System blueprint |
| `docs/specs/MandarinOS_engine_specs_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Engine specs |
| `docs/specs/MandarinOS_marketing_positioning_v1.md` | C | phase-specific | — | Marketing positioning |
| `docs/specs/MandarinOS_next_question_selector_v1.md` | C | misleading-filename | `docs/CONVERSATION_ARCHITECTURE.md` | LOCKED-labelled selector spec |
| `docs/specs/MandarinOS_support_packs_v1.md` | C | phase-specific | — | Support packs |
| `docs/specs/PHASE_10_6_ASR_STABILIZATION_MINI_SPEC.md` | C | phase-specific | `docs/ASR_PIPELINE.md` | ASR stabilisation mini-spec |
| `docs/specs/Progress_Scorecard_Alignment.md` | C | phase-specific | — | Scorecard alignment |
| `docs/specs/RELEASE_1_BOUNDARY.md` | C | phase-specific | — | Release 1 boundary |
| `docs/specs/mandarinos_adjective_pack_v1.md` | C | phase-specific | content JSON | Adjective pack spec |
| `docs/specs/mandarinos_conversation_energy_model_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Energy model |
| `docs/specs/mandarinos_conversation_steering_engine_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Steering engine |
| `docs/specs/mandarinos_curiosity_engine_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Curiosity engine |
| `docs/specs/mandarinos_emergency_curiosity_pack_v1.md` | C | phase-specific | content JSON | Curiosity pack |
| `docs/specs/mandarinos_emergency_phrases_p1_p2_v2.md` | C | phase-specific | content JSON | Emergency phrases |
| `docs/specs/mandarinos_family_conversation_ladder_v2.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Family ladder v2 |
| `docs/specs/mandarinos_family_engine_v4.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Family engine v4 |
| `docs/specs/mandarinos_family_memory_rules_v1.md` | C | phase-specific | `docs/STATE_CONTRACT.md` | Family memory rules |
| `docs/specs/mandarinos_family_vocab_pack_p1.md` | C | phase-specific | content JSON | Family vocab pack |
| `docs/specs/mandarinos_food_engine_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Food engine |
| `docs/specs/mandarinos_identity_engine_v4.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Identity engine v4 |
| `docs/specs/mandarinos_interests_engine_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Interests engine |
| `docs/specs/mandarinos_orientation_pack_v1.md` | C | phase-specific | content JSON | Orientation pack |
| `docs/specs/mandarinos_persona_network_relationship_pack_v1.md` | C | phase-specific | persona JSON | Persona-network pack |
| `docs/specs/mandarinos_place_engine_v1.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Place engine |
| `docs/specs/mandarinos_study_work_engine_v10.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Study/work engine v10 |
| `docs/specs/mandarinos_study_work_ladder.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Study/work ladder |
| `docs/specs/mandarinos_study_work_memory_rules.md` | C | phase-specific | `docs/STATE_CONTRACT.md` | Study/work memory rules |
| `docs/specs/mandarinos_study_work_vocab_pack.md` | C | phase-specific | content JSON | Study/work vocab pack |
| `docs/specs/mandarinos_travel_engine_v4.md` | C | phase-specific | `docs/CONVERSATION_ARCHITECTURE.md` | Travel engine v4 |

### 17.11 `docs/state/`, `docs/Social_Media/`, `integration_kit/`

| Path | Class | Flags | Notes |
| ---- | ----- | ----- | ----- |
| `docs/state/MANDARINOS_SYSTEM_STATE_PHASE_12B.md` | E | dated-snapshot, misleading-filename | Phase 12B state snapshot |
| `docs/Social_Media/README.txt` | G | generated | Marketing collateral index |
| `docs/Social_Media/deck1-first-video.marp.md` | G | generated | Marketing deck |
| `docs/Social_Media/deck2-vocabulary-trap.marp.md` | G | generated | Marketing deck |
| `docs/Social_Media/deck3-apps-dont-teach-speaking.marp.md` | G | generated | Marketing deck |
| `docs/Social_Media/deck4-immersion-not-enough.marp.md` | G | generated | Marketing deck |
| `docs/Social_Media/deck5-missing-skill.marp.md` | G | generated | Marketing deck |
| `docs/Social_Media/mandarinos-first-video.marp.md` | G | generated | Marketing deck |
| `docs/Social_Media/mandarinos-marp-template.md` | G | generated, duplicate-or-near-duplicate | Marp template (canonical) |
| `docs/Social_Media/mandarinos-marp-template 1.md` | G | generated, duplicate-or-near-duplicate | Duplicate template copy |
| `docs/Social_Media/mandarinos_prelaunch_scripts.txt` | G | generated | Pre-launch scripts |
| `integration_kit/README.md` | C | phase-specific, implementation-not-verified | Trace-export kit (not wired to runtime) |
| `integration_kit/schemas/README.md` | C | phase-specific | Kit schema index |
| `integration_kit/examples/PHASE_2_DIRECTIVE_2A_WIRE_REDUCER_INTO_LIVE_UI.md` | C | phase-specific | Phase 2A example directive |
| `integration_kit/examples/PHASE_2B_DIRECTIVE_CARD_RESOLVED_RACE_GUARD.txt` | C | phase-specific | Phase 2B example directive |
| `integration_kit/examples/PHASE_2C_DIRECTIVE_CARD_PANEL_HISTORY_BACK.md` | C | phase-specific | Phase 2C example directive |

### 17.12 `.cursor/rules/` coding-rule files

| Path | Class | Flags | Replacement/authority | Notes |
| ---- | ----- | ----- | --------------------- | ----- |
| `.cursor/rules/mandarinos-architecture.mdc` | B | contains-current-material | `docs/ARCHITECTURAL_DECISIONS.md` | Standing architectural rules (agent-enforced) |
| `.cursor/rules/mandarinos-ui-objects.mdc` | B | contains-current-material | `docs/ARCHITECTURE.md` | UI standard-object rules (agent-enforced) |

## 18. Audit traceability

Inventory commands:

```bash
git ls-files "*.md" "*.txt" "*.rst"
git ls-files ".cursor/rules/*"
git grep -n "LOCKED"   # and FINAL / MASTER / CURRENT / supersed / Phase
git log --format="%ad %H %s" --date=short -- <path>
```

Counting rule: every file tracked by Git matching `*.md`, `*.txt`, or `*.rst`, plus the two tracked `.cursor/rules/*.mdc` coding-rule files, counted once. The `git ls-files` glob returned **224** files; the two `.mdc` rule files are classified in §5 and counted in the B total, giving a documentation-surface total of **226** classified files.

- Total tracked documentation files (glob `*.md`/`*.txt`/`*.rst`): 224
- Plus `.cursor/rules/*.mdc` (classified B): 2
- **Total classified: 226**

Counts by primary classification:

| Code | Classification | Count |
| ---- | -------------- | ----- |
| A | Authoritative — approved R2 governance | 8 |
| B | Current supporting guidance | 18 |
| C | Historical context | 112 |
| D | Superseded | 10 |
| E | Archival evidence / dated report | 36 |
| F | Proposal / plan / unimplemented spec | 22 |
| G | Generated / procedural artefact | 20 |
| H | Unresolved | 0 |
| — | **Total** | **226** |

Counts by secondary flag (approximate; a file may carry several):

- `phase-specific`: ~120
- `dated-snapshot`: ~40
- `generated`: 20
- `implementation-not-verified`: ~25
- `misleading-filename`: 11
- `duplicate-or-near-duplicate`: 14
- `mixed-current-and-historical`: 3
- `partially-implemented`: 4
- `contains-current-material` / `contains-obsolete-material`: ~15

Other totals:

- Misleading-title files: 11 (§11)
- Duplicate/overlap groups: 9 (§12)
- Unresolved classifications: 0 (§10)

Principal Git-history range inspected: Phase 6 (2026-03) through the R2 baseline (2026-07-12), including `7ad0e56` (Phase 7 restructure), `083d3c2` (Phase 10 memory/persona), and `3be0315` (R2 baseline).

Principal approved documents used: the eight A documents (§4), plus `.cursor/rules/mandarinos-architecture.mdc` and `.cursor/rules/mandarinos-ui-objects.mdc` for cross-reference verification.

Principal conflicts identified:

- "Authoritative" headings on `AI_CONTEXT.md` and `MANDARINOS_SYSTEM_MAP.md` predate and are subordinate to the eight A documents;
- `docs/design/CURSOR_STARTUP_PROTOCOL.md` onboarding order is superseded by `docs/ARCHITECTURE.md` §21 and §13 here;
- the Phase 2–7 trace/card/conformance system (directives, TRACE_CONTRACT, integration kit) is not wired into the current conversation turn path (no `TraceBuilder`/`trace_exporter` in `ui/app.js`; no trace-contract references in `*.py`);
- `docs/specs/MandarinOS_master_AI_bootstrap_context.md` is superseded by `AI_CONTEXT.md`; multiple project-plan versions and `conversation_*_v1` models are superseded by the v2 roadmap and the R2 contracts;
- `LOCKED`-labelled selector/capability specs are design-phase; actual behaviour lives in code plus `docs/CONVERSATION_ARCHITECTURE.md`;
- GitHub Copilot is retired, but `.github/copilot-instructions.md` remains tracked.

Classification date: `2026-07-13`

Application baseline commit: `3be0315b2c9f7316b03ac2183a887f602ae9a297`
Application baseline tag: `architecture-baseline-2026-07-12-r2`
Documentation branch: `docs/architecture-v1`
Document status: `Draft v1`
Last verified date: `2026-07-13`
