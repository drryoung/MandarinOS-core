# MandarinOS Phase B5 Remaining-Document Scope Assessment

Assessment date: 2026-07-14
Repository branch: docs/architecture-v1
Documentation baseline: 3e1611b7173e6fead6f2285600ad00065932c8d9
Application baseline: 3be0315b2c9f7316b03ac2183a887f602ae9a297
Status: Approved scope assessment — 2026-07-14

## 1. Purpose

Phase B5 assesses **all 150** class-B, class-C, and class-G inventory documents to determine which require further governance action beyond the completed Phase B4 class-E programme. Of these, **141 lacked notices** at the Phase B5 baseline; **nine** had already received approved notices in Phase B1 and were reviewed for complete category context only.

This assessment does **not** add notices, reclassify files, or authorise remediation. It produces a bounded remediation scope for later Phase B5A–B5D batches.

## 2. Scope and method

**In scope:** all 18 class-B, 112 class-C, and 20 class-G inventory rows (150 documents).

**Out of scope:** nine class-A authoritative R2 documents (acknowledged; no remediation proposed).

**Method:**

1. Extracted all §17 rows and verified counts against `docs/DOCUMENT_AUTHORITY_INDEX.md`.
2. Grouped unnotified files by directory, filename pattern, and secondary flags.
3. Read file openings and applied the risk criteria in §4 against the approved nine-document R2 governance package and index conflicts recorded in §18.
4. Preferred directory- or family-level guidance over per-file notices where files form a coherent historical family.
5. No Sonnet escalation was required; ambiguous cases were resolved from index authority fields and §11–§12 registers.

**Model:** Composer 2.5 (assessment); Auto (inventory extraction scripts).

## 3. Verified inventory

**Assessment population (class B/C/G only):**

| Population | Count |
| ---------- | ----- |
| Total class-B/C/G documents reviewed | 150 |
| Previously unnotified at Phase B5 baseline | 141 |
| Previously noticed in Phase B1 (contextual review) | 9 |

**Pre-assessment repository inventory (all classes):**

| Metric | Count |
| ------ | ----- |
| Total §17 inventory (pre-Phase B5) | 227 |
| Notice-bearing (`status-header-added`) | 77 |
| Lacking notices (all classes) | 150 |

**Pre-assessment unnotified by primary class (all classes):**

| Class | Unnotified | Expected | Match |
| ----- | ---------- | -------- | ----- |
| A | 9 | 9 | yes |
| B | 15 | 15 | yes |
| C | 106 | 106 | yes |
| G | 20 | 20 | yes |

The **141 previously unnotified** documents are the population considered for **new** Phase B5 remediation. The nine Phase B1-noticed documents are included in risk totals and disposition accounting as contextual review items with disposition **already noticed**; they are not candidates for new file-level intervention.

**Nine Phase B1-noticed documents (3 class B; 6 class C; 0 class G):**

- `AI_CONTEXT.md`
- `MANDARINOS_SYSTEM_MAP.md`
- `docs/MANDARINOS_REGRESSION_LOCK.md`
- `.github/copilot-instructions.md`
- `docs/phases/PHASE6_FREEZE.md`
- `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`
- `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`
- `docs/specs/MandarinOS_capability_update_rules_v1.md`
- `docs/specs/MandarinOS_next_question_selector_v1.md`

**Class A (nine files):** acknowledged outside remediation scope; governed by §4 of the authority index.

## 4. Risk criteria

Four risk levels applied:

- **Critical:** likely damaging change if followed (obsolete ops, false architectural authority, direct edit of generated runtime input).
- **High:** plausible regression, incorrect implementation, or authority confusion.
- **Medium:** onboarding friction or uncertainty; approved hierarchy should prevent direct damage.
- **Low:** clearly contextual, historical, descriptive, or generated with little misuse risk.

Seven assessment dimensions: authority risk, operational risk, discoverability risk, generated-file risk, duplication risk, onboarding value, remediation proportionality (see programme directive).

Individual notices are recommended only at **Critical** or **High** unless specifically documented otherwise.

## 5. Executive findings

| Finding | Count | Denominator |
| ------- | ----- | ----------- |
| Documents reviewed (B+C+G) | 150 | full assessment population |
| Critical risk | 0 | 150 |
| High risk | 14 | 150 |
| Medium risk | 77 | 150 |
| Low risk | 59 | 150 |
| Proposed individual notices (new) | 2 | 141 previously unnotified |
| Proposed directory/family guidance | 31 | 141 |
| Proposed generated-output interventions | 8 | 141 |
| Onboarding/index integration | 46 | 141 |
| No further action (new) | 54 | 141 |
| Already addressed (Phase B1 notices) | 9 | contextual within 150 |

**By class — proposed individual notices (new):**

- Class B: 1
- Class C: 1
- Class G: 0

**Disposition reconciliation (150-document population):** 2 + 31 + 8 + 46 + 54 + 9 = **150**.

**New-remediation reconciliation (141 previously unnotified):** 2 + 31 + 8 + 46 + 54 = **141**.

**No new file-level intervention:** A total of **63** documents require no new Phase B5 file-level intervention: **54** assessed as no further action plus **9** already protected by approved Phase B1 notices. This is not 63 no-action documents.

**Key conclusion:** The assessment reviewed all **150** class-B, class-C, and class-G documents. Of these, **141** lacked notices at the Phase B5 baseline and **nine** had already received notices in Phase B1. The 141 previously unnotified documents do **not** warrant 141 individual notices. A bounded programme of **2** high-value individual notices, **3** family authority READMEs covering **31** files, **8** generated-file headers, and **onboarding/index integration** for **46** files adequately controls risk for the remediation population.

### 5.1 Risk by disposition (reconciliation matrix)

Risk ratings use the full **150**-document B/C/G population. Disposition categories are mutually exclusive.

| Risk | Individual | Family/dir | Generated | Onboarding/index | No action | Already noticed | Total |
| ---- | ---------: | ---------: | --------: | ---------------: | --------: | --------------: | ----: |
| Critical | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| High | 2 | 0 | 3 | 0 | 0 | 9 | 14 |
| Medium | 0 | 31 | 0 | 46 | 0 | 0 | 77 |
| Low | 0 | 0 | 5 | 0 | 54 | 0 | 59 |
| **Total** | **2** | **31** | **8** | **46** | **54** | **9** | **150** |

**Cross-check notes:**

- Both individual-notice targets are **High** risk.
- The other **12** High-risk documents comprise **nine** Phase B1-noticed files (contextual; disposition **already noticed**) and **three** root `server_*.txt` captures (disposition **generated**; B5C headers, not individual notices).
- No Critical-risk document is assigned **no further action**.
- Column totals equal disposition totals; row totals equal risk totals.

## 6. Class-B assessment

All **18** class-B documents reviewed (three already carry Phase B1 notices).

| Recommendation | Count |
| -------------- | ----- |
| B5 individual notice | 1 |
| no further action | 3 |
| no further action (approved notice in Phase B1–B4) | 3 |
| onboarding/index reference only | 11 |

### 6.1 Unnotified class-B files (15)

| Path | Risk | Governing authority | Misuse scenario | Recommendation | Priority |
| ---- | ---- | ------------------- | --------------- | -------------- | -------- |
| `.cursor/rules/mandarinos-architecture.mdc` | Medium | `docs/ARCHITECTURAL_DECISIONS.md` | Supporting doc mistaken for behavioural contract | onboarding/index reference only | Medium |
| `.cursor/rules/mandarinos-ui-objects.mdc` | Medium | `docs/ARCHITECTURE.md` | Supporting doc mistaken for behavioural contract | onboarding/index reference only | Medium |
| `README.md` | Medium | `docs/ARCHITECTURE.md` | Repo entry may be taken as full architecture authority | onboarding/index reference only | Medium |
| `conformance/README.md` | Medium | `docs/TEST_STRATEGY.md` | Supporting doc mistaken for behavioural contract | onboarding/index reference only | Medium |
| `docs/DEVELOPER_ONBOARDING.md` | High | `docs/ARCHITECTURE.md` | Dated 2026-05-11 hosting/startup steps may contradict `docs/ARCHITECTURE.md` §21 | B5 individual notice | High |
| `docs/RESPONSE_OPTION_STYLE_GUIDE.md` | Medium | `docs/ANSWER_SOURCE_CONTRACT.md` | Supporting doc mistaken for behavioural contract | onboarding/index reference only | Medium |
| `docs/design/LICENSE.md` | Low | §5 table | Supporting doc mistaken for behavioural contract | no further action | Low |
| `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md` | Medium | R2 governance package | v1 governance model may compete with R2 package | onboarding/index reference only | Medium |
| `docs/design/mandarinos_design_constitution.txt` | Medium | R2 governance package | Supporting doc mistaken for behavioural contract | onboarding/index reference only | Medium |
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | Medium | `docs/ARCHITECTURAL_DECISIONS.md` | Supporting doc mistaken for behavioural contract | onboarding/index reference only | Medium |
| `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md` | Medium | `docs/CONVERSATION_ARCHITECTURE.md` | Supporting doc mistaken for behavioural contract | onboarding/index reference only | Medium |
| `docs/specs/MandarinOS_Extensibility_Strategy.md` | Medium | `docs/ARCHITECTURAL_DECISIONS.md` | Supporting doc mistaken for behavioural contract | onboarding/index reference only | Medium |
| `requirements-tools.txt` | Low | §5 table | Supporting doc mistaken for behavioural contract | no further action | Low |
| `requirements.txt` | Low | §5 table | Supporting doc mistaken for behavioural contract | no further action | Low |
| `runtime/README_runtime_indexes.txt` | Medium | `docs/ARCHITECTURE.md` §14 | Supporting doc mistaken for behavioural contract | onboarding/index reference only | Medium |

### 6.2 Already-noticed class-B (Phase B1)

`AI_CONTEXT.md`, `MANDARINOS_SYSTEM_MAP.md`, `docs/MANDARINOS_REGRESSION_LOCK.md` — approved notices; no further action.

## 7. Class-C assessment

All **112** class-C documents reviewed (six Phase B1 notices). Unnotified: **106**.

### 7.1 Family summary

| Family | Risk | Failure mode | Recommendation | Batch | Files |
| ------ | ---- | ------------ | -------------- | ----- | ----- |
| `docs/directives/` (17 files) | Medium | Phase 2–7 Copilot/trace/card directives; not wired to conversation runtime (index §18) | medium-risk directory guidance | B5B | 17 |
| `docs/phases/` (9 unnotified class-C files) | Medium | Phase milestones/freezes; two additional class-C files already noticed in B1 | medium-risk directory guidance | B5B | 9 |
| `integration_kit/` (5 files) | Medium | Legacy trace/conformance kit; side tool per index §18 | medium-risk directory guidance | B5B | 5 |
| `docs/briefings/` (28 class-C files) | Low | Historical strategist briefings; E audits separately noticed in B4C | onboarding/index hierarchy | B5D | 28 |
| `docs/specs/` (35 unnotified class-C) | Low | Design-phase specs; behaviour authority is code + contracts | no further action | — | 35 |
| `docs/design/` (6 unnotified class-C) | Low–High | Early design artefacts; one trace-contract outlier | see §7.2 | B5A/B5D | 6 |
| `docs/project/` (6 class-C) | Low | Historical project notes; F/G siblings separately governed | no further action | — | 6 |

### 7.2 High-risk class-C individual notice

| Path | Risk | Reason | Recommendation |
| ---- | ---- | ------ | -------------- |
| `docs/design/TRACE_CONTRACT_v1.md` | High | Trace contract referenced historically but not wired to conversation runtime; authority-sounding title | high-risk individual notice (B5A) |

### 7.3 Already-noticed class-C (Phase B1)

Six files with approved notices: `.github/copilot-instructions.md`, `docs/phases/PHASE6_FREEZE.md`, `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`, `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`, `docs/specs/MandarinOS_capability_update_rules_v1.md`, `docs/specs/MandarinOS_next_question_selector_v1.md`.

### 7.4 No-action class-C rationale

Thirty-five unnotified `docs/specs/` class-C design specifications require no individual notice because: filenames include version/phase context; index §17 assigns `phase-specific`; behaviour authority is `docs/CONVERSATION_ARCHITECTURE.md` and verified code; misleading-title cases already received Phase B1 notices.

## 8. Class-G assessment

All **20** class-G documents reviewed.

| Path | Generator/source | Consumption | Edit risk | Recommendation | Priority |
| ---- | ---------------- | ----------- | --------- | -------------- | -------- |
| `docs/Social_Media/README.txt` | Marp/marketing collateral (manual) | reference only | Low | no further action | Low |
| `docs/Social_Media/deck1-first-video.marp.md` | Marp/marketing collateral (manual) | reference only | Low | no further action | Low |
| `docs/Social_Media/deck2-vocabulary-trap.marp.md` | Marp/marketing collateral (manual) | reference only | Low | no further action | Low |
| `docs/Social_Media/deck3-apps-dont-teach-speaking.marp.md` | Marp/marketing collateral (manual) | reference only | Low | no further action | Low |
| `docs/Social_Media/deck4-immersion-not-enough.marp.md` | Marp/marketing collateral (manual) | reference only | Low | no further action | Low |
| `docs/Social_Media/deck5-missing-skill.marp.md` | Marp/marketing collateral (manual) | reference only | Low | no further action | Low |
| `docs/Social_Media/mandarinos-first-video.marp.md` | Marp/marketing collateral (manual) | reference only | Low | no further action | Low |
| `docs/Social_Media/mandarinos-marp-template 1.md` | Marp/marketing collateral (manual) | reference only | Low | no further action | Low |
| `docs/Social_Media/mandarinos-marp-template.md` | Marp/marketing collateral (manual) | reference only | Low | no further action | Low |
| `docs/Social_Media/mandarinos_prelaunch_scripts.txt` | Marp/marketing collateral (manual) | reference only | Low | no further action | Low |
| `docs/project/CHATGPT_BRANCH_START_TEMPLATE.md` | manual procedural template | branch-start reference | Medium | index-only clarification | Medium |
| `docs/project/COMMIT_INSTRUCTIONS.md` | manual procedural template | branch-start reference | Medium | index-only clarification | Medium |
| `fo_check.txt` | generator/source not verified | debug reference | Medium | generated-file header required | Medium |
| `frame_dump.txt` | generator/source not verified | debug reference | Medium | generated-file header required | Medium |
| `frame_texts.txt` | generator/source not verified | debug reference | Medium | generated-file header required | Medium |
| `scripts/_engine_audit.txt` | audit tooling (not verified) | test/debug | Medium | generated-file header required | Medium |
| `server_err.txt` | runtime capture (not verified) | debug | High | generated-file header required | High |
| `server_out.txt` | runtime capture (not verified) | debug | High | generated-file header required | High |
| `server_startup_err.txt` | runtime capture (not verified) | debug | High | generated-file header required | High |
| `tools/coverage/coverage_report.md` | coverage tooling (not verified) | test/coverage | High | generated-file header required | Medium |

## 9. Recommended remediation programme

Smallest adequate programme — four batches plus closeout:

### Phase B5A — Critical and High individual notices

- **Purpose:** Address the two remaining files where individual authority clarification is proportionate.
- **Files (2):** `docs/DEVELOPER_ONBOARDING.md`, `docs/design/TRACE_CONTRACT_v1.md`
- **Model:** Composer 2.5
- **Scope:** 2 target files + `docs/DOCUMENT_AUTHORITY_INDEX.md`
- **Approval:** Separate candidate and approval pass
- **Exclusions:** No class-C mass notice rollout

### Phase B5B — Directory and family authority guidance

- **Purpose:** Single README/authority note per historical family instead of 31 duplicate notices.
- **Families (3):** `docs/directives/` (17 files), `docs/phases/` (9 unnotified class-C), `integration_kit/` (5 files)
- **Model:** Composer 2.5
- **Scope:** 3 new guidance files + index §15/§17 notes
- **Approval:** Separate review
- **Exclusions:** No per-directive notices

### Phase B5C — Generated-output guidance

- **Purpose:** Prevent direct edit of generated/captured outputs.
- **Files (8):** root `*.txt` captures, `scripts/_engine_audit.txt`, `tools/coverage/coverage_report.md`
- **Model:** Auto (header insertion) with Composer 2.5 review if generator linkage unclear
- **Scope:** 8 files + optional `tools/coverage/README` + index
- **Approval:** Separate review
- **Exclusions:** No historical-authority notices on generated files

### Phase B5D — Onboarding and authority-path integration

- **Purpose:** Link supporting docs to canonical R2 entry path (`docs/ARCHITECTURE.md` §21, authority index §13).
- **Files (46):** class-B supporting docs, class-C briefing/design subsets, class-G index clarifications
- **Model:** Composer 2.5
- **Scope:** `docs/DEVELOPER_ONBOARDING.md` cross-links, `AI_CONTEXT.md` pointer updates, index §13 onboarding table — not 46 separate notices
- **Approval:** Separate review
- **Exclusions:** No reclassification

### Phase B closeout

After B5A–B5D: verify no remaining Critical/High unmitigated files; confirm Phase B complete.

## 10. Files requiring individual notices

- `docs/DEVELOPER_ONBOARDING.md` (B, High)
- `docs/design/TRACE_CONTRACT_v1.md` (C, High)

## 11. Files covered by directory or family guidance

- `docs/directives/MANDARINOS_ARCHITECT_COPILOT_HANDOFF_DIRECTIVE_PHASE7.txt` → B5B:docs/directives/
- `docs/directives/MANDARINOS_COPILOT_STARTUP_INSTRUCTIONS.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_OPEN_CARD_Trace_Wiring_Directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_OPEN_CARD_Unit_Test_Directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_Phase_Boundaries_v1.0.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_Runtime_Card_Integration_Directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_Simulator_Entrypoint_Copilot_Directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_TurnState_Trace_Contract_v1_directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_UI_Shell_Copilot_Directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_card_contract_v1_directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_conformance_harness_directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_content_coverage_scanner_v1_directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_hint_cascade_directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_integration_kit_scenarios_v1_directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_scaffolding_transition_harness_v1_directive.txt` → B5B:docs/directives/
- `docs/directives/MandarinOS_universal_cards_builder_v1_directive.txt` → B5B:docs/directives/
- `docs/directives/mandarinos_copilot_architecture_update.txt` → B5B:docs/directives/
- `docs/phases/MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md` → B5B:docs/phases/
- `docs/phases/MANDARINOS_PHASE_10_5_STABILISATION_BRIEF.md` → B5B:docs/phases/
- `docs/phases/MandarinOS_Phase9_Signoff.md` → B5B:docs/phases/
- `docs/phases/PHASE6_RUNTIME_INDEXES_NOTES.md` → B5B:docs/phases/
- `docs/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md` → B5B:docs/phases/
- `docs/phases/PHASE9_2_BRIDGE_TIER.md` → B5B:docs/phases/
- `docs/phases/PHASE_10_5_CONVERSATION_SIMULATION.md` → B5B:docs/phases/
- `docs/phases/Phase 3 Step 1 Audio-first UI.md` → B5B:docs/phases/
- `docs/phases/ROLLBACK_POINT_v1.md` → B5B:docs/phases/
- `integration_kit/README.md` → B5B:integration_kit/
- `integration_kit/examples/PHASE_2B_DIRECTIVE_CARD_RESOLVED_RACE_GUARD.txt` → B5B:integration_kit/
- `integration_kit/examples/PHASE_2C_DIRECTIVE_CARD_PANEL_HISTORY_BACK.md` → B5B:integration_kit/
- `integration_kit/examples/PHASE_2_DIRECTIVE_2A_WIRE_REDUCER_INTO_LIVE_UI.md` → B5B:integration_kit/
- `integration_kit/schemas/README.md` → B5B:integration_kit/

## 12. Files requiring generated-output guidance

- `fo_check.txt`
- `frame_dump.txt`
- `frame_texts.txt`
- `server_out.txt`
- `server_err.txt`
- `server_startup_err.txt`
- `scripts/_engine_audit.txt`
- `tools/coverage/coverage_report.md`

## 13. Files requiring no further action (54)

These **54** previously unnotified documents require no new Phase B5 file-level intervention. They are distinct from the **nine** Phase B1-noticed documents in §13.1.

**Grouped rationale:**

- **`docs/specs/` class-C design specifications (35):** versioned phase-specific filenames; behaviour authority is verified code plus `docs/CONVERSATION_ARCHITECTURE.md`; misleading-title cases already noticed in Phase B1.
- **`docs/project/` class-C notes (6):** historical project context; not operational entry points.
- **`docs/Social_Media/` class-G collateral (10):** marketing/reference artefacts; not consumed by runtime.
- **Dependency manifests (2):** `requirements.txt`, `requirements-tools.txt` — operative configuration, not governance prose.
- **`docs/design/LICENSE.md` (1):** legal statement outside implementation hierarchy.

**Complete list (54):**

- `docs/Social_Media/README.txt`
- `docs/Social_Media/deck1-first-video.marp.md`
- `docs/Social_Media/deck2-vocabulary-trap.marp.md`
- `docs/Social_Media/deck3-apps-dont-teach-speaking.marp.md`
- `docs/Social_Media/deck4-immersion-not-enough.marp.md`
- `docs/Social_Media/deck5-missing-skill.marp.md`
- `docs/Social_Media/mandarinos-first-video.marp.md`
- `docs/Social_Media/mandarinos-marp-template 1.md`
- `docs/Social_Media/mandarinos-marp-template.md`
- `docs/Social_Media/mandarinos_prelaunch_scripts.txt`
- `docs/design/LICENSE.md`
- `docs/project/DIRECTIVE_PHASE_1_CARD_PANEL_STATE.md`
- `docs/project/ENGINES_P1_P2_AND_SRS_REFERENCE.md`
- `docs/project/NEXT_QUESTION_SELECTOR_AND_LEVEL_TIE_IN.md`
- `docs/project/PROBE_QUESTIONS_RESPONSE_OPTIONS_NOTE.md`
- `docs/project/TEST_DIAGNOSTIC_P1_MANUAL.md`
- `docs/project/USER_TURN_AND_PERSONA_QUESTIONS_NOTE.md`
- `docs/specs/Live_Beginner_Ability_Model.md`
- `docs/specs/MandarinOS_Conversation_UX_Protocol_v1.md`
- `docs/specs/MandarinOS_Progress_Tracking_Cursor_Spec_v2.md`
- `docs/specs/MandarinOS_Repair_Curiosity_Loop.md`
- `docs/specs/MandarinOS_conversation_capability_map_v1.md`
- `docs/specs/MandarinOS_conversation_ladders_full_draft_v2.md`
- `docs/specs/MandarinOS_conversation_memory_model_v2.md`
- `docs/specs/MandarinOS_conversation_system_blueprint_v1.md`
- `docs/specs/MandarinOS_engine_specs_v1.md`
- `docs/specs/MandarinOS_marketing_positioning_v1.md`
- `docs/specs/MandarinOS_support_packs_v1.md`
- `docs/specs/PHASE_10_6_ASR_STABILIZATION_MINI_SPEC.md`
- `docs/specs/Progress_Scorecard_Alignment.md`
- `docs/specs/RELEASE_1_BOUNDARY.md`
- `docs/specs/mandarinos_adjective_pack_v1.md`
- `docs/specs/mandarinos_conversation_energy_model_v1.md`
- `docs/specs/mandarinos_conversation_steering_engine_v1.md`
- `docs/specs/mandarinos_curiosity_engine_v1.md`
- `docs/specs/mandarinos_emergency_curiosity_pack_v1.md`
- `docs/specs/mandarinos_emergency_phrases_p1_p2_v2.md`
- `docs/specs/mandarinos_family_conversation_ladder_v2.md`
- `docs/specs/mandarinos_family_engine_v4.md`
- `docs/specs/mandarinos_family_memory_rules_v1.md`
- `docs/specs/mandarinos_family_vocab_pack_p1.md`
- `docs/specs/mandarinos_food_engine_v1.md`
- `docs/specs/mandarinos_identity_engine_v4.md`
- `docs/specs/mandarinos_interests_engine_v1.md`
- `docs/specs/mandarinos_orientation_pack_v1.md`
- `docs/specs/mandarinos_persona_network_relationship_pack_v1.md`
- `docs/specs/mandarinos_place_engine_v1.md`
- `docs/specs/mandarinos_study_work_engine_v10.md`
- `docs/specs/mandarinos_study_work_ladder.md`
- `docs/specs/mandarinos_study_work_memory_rules.md`
- `docs/specs/mandarinos_study_work_vocab_pack.md`
- `docs/specs/mandarinos_travel_engine_v4.md`
- `requirements-tools.txt`
- `requirements.txt`

## 13.1 Already noticed in Phase B1 (9) — no new intervention

These nine documents were reviewed for complete class-B/C context. They already carry approved Phase B1 notices and are **not** counted among the 54 no-action files.

- `AI_CONTEXT.md` (B)
- `MANDARINOS_SYSTEM_MAP.md` (B)
- `docs/MANDARINOS_REGRESSION_LOCK.md` (B)
- `.github/copilot-instructions.md` (C)
- `docs/phases/PHASE6_FREEZE.md` (C)
- `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` (C)
- `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` (C)
- `docs/specs/MandarinOS_capability_update_rules_v1.md` (C)
- `docs/specs/MandarinOS_next_question_selector_v1.md` (C)

## 13.2 Onboarding and index integration (46)

These **46** previously unnotified documents are covered by bounded B5D onboarding and authority-path integration — not individual notices. Paths are grouped by family; none overlap other disposition categories.

**Class-B supporting (11):** `.cursor/rules/mandarinos-architecture.mdc`; `.cursor/rules/mandarinos-ui-objects.mdc`; `README.md`; `conformance/README.md`; `docs/RESPONSE_OPTION_STYLE_GUIDE.md`; `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md`; `docs/design/mandarinos_design_constitution.txt`; `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md`; `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md`; `docs/specs/MandarinOS_Extensibility_Strategy.md`; `runtime/README_runtime_indexes.txt`.

**`docs/briefings/` class-C (28):** all unnotified class-C briefing files under `docs/briefings/` (strategist and phase briefings; class-E audits in the same directory are separately governed by Phase B4C).

**`docs/design/` historical (5):** `docs/design/CARDS_BUILD_v1.md`; `docs/design/MandarinOS Developer Handoff.txt`; `docs/design/MandarinOS_brief.md`; `docs/design/p3_architecture.md`; `docs/design/ux_flow.txt`.

**Class-G procedural templates (2):** `docs/project/CHATGPT_BRANCH_START_TEMPLATE.md`; `docs/project/COMMIT_INSTRUCTIONS.md`.

**B5D scope (bounded):** update `docs/ARCHITECTURE.md` §21 onboarding table, authority-index §13 cross-references, and targeted pointers in `AI_CONTEXT.md` / `docs/DEVELOPER_ONBOARDING.md` — not 46 separate notices.

## 14. Proposed Phase B5 batches

| Batch | Files | Model |
| ----- | ----- | ----- |
| B5A individual notices | 2 | Composer 2.5 |
| B5B family guidance | 31 (via 3 READMEs) | Composer 2.5 |
| B5C generated headers | 8 | Auto / Composer 2.5 |
| B5D onboarding integration | 46 (integration, not 46 notices) | Composer 2.5 |
| B closeout | verification | Auto |

## 15. Explicitly excluded work

- Class-A positive authority markers (separate concern)
- Physical archive (Phase C)
- Duplicate consolidation (Phase D)
- Mass class-C individual notices (106 files)
- Reclassification or secondary-flag changes
- Implementation of historical recommendations
- Production code, tests, content, or Cursor-rule changes

## 16. Verification results

- Pre-Phase B5 inventory: 227 paths; 77 noticed; 150 lacking notices (A9 B15 C106 G20).
- Assessment population: 150 class-B/C/G documents reviewed; 141 previously unnotified; nine Phase B1-noticed.
- Risk totals sum to 150 (Critical 0; High 14; Medium 77; Low 59).
- Disposition categories are mutually exclusive and sum to 150.
- New-remediation dispositions sum to 141 (2 + 31 + 8 + 46 + 54).
- Risk-by-disposition matrix reconciles (§5.1).
- Post-Phase B5 inventory: 228 paths; class E 37; `dated-snapshot` 39; `status-header-added` remains 77.
- No existing §17 classification or flag altered except the new assessment row.
- No status notices added.
- No remediation batch begun.

## 17. Approval status

Phase B5 scope assessment: **approved 2026-07-14.**

- The assessment is approved and defines the maximum authorised scope for proposed B5A–B5D work.
- Every remediation batch still requires a separate directive, candidate review, approval, and push.
- Approved denominator: **150** total B/C/G documents reviewed; **141** previously unnotified; **nine** previously noticed in Phase B1.
- No remediation batch has begun.
- Phase B remains incomplete.

Recorded in `docs/DOCUMENT_AUTHORITY_INDEX.md` §15.
