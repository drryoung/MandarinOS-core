# MandarinOS Phase C1 Historical-Document Dependency Audit and Archival Plan

Assessment date: 2026-07-14
Repository branch: docs/architecture-v1
Documentation baseline: b8ccfd7bc6c32989ebc0b942abe3776194373f65
Application baseline: 3be0315b2c9f7316b03ac2183a887f602ae9a297
Status: Approved archival audit and relocation plan — 2026-07-14

## 1. Purpose

Phase B established **which** documents are authoritative, supporting, historical, obsolete, evidential, proposed, or generated, and controlled the risk of the historical population with 79 status notices, 8 generated-output headers, 3 family guides, and a 46-file onboarding-integration mapping. Phase B did **not** change where any document physically lives.

Phase C will make the repository's physical structure reflect that authority hierarchy. This document is the **first, diagnostic-only pass**. It:

* identifies which of the 230 pre-existing inventoried documents are reasonable candidates for eventual relocation;
* identifies every repository dependency — operational, AI/bootstrap, and documentary — on their current paths;
* distinguishes safe archival candidates from mixed or operationally significant locations;
* proposes exact source and destination paths for every candidate;
* produces a bounded, batched relocation programme (Phase C2A–onwards) for future, separately approved execution.

**No file has been moved, renamed, deleted, or rewritten by this pass.** No archive directory has been created. No link has been changed. No classification or secondary flag on any of the 230 pre-existing rows has changed.

## 2. Scope and method

**In scope:** all 230 pre-existing `docs/DOCUMENT_AUTHORITY_INDEX.md` §17 inventory rows (classes A, B, C, D, E, F, G; H is confirmed empty).

**Method:**

1. Extracted all 230 §17 rows programmatically (path, class, secondary flags, replacement/authority, note) into a working table.
2. Grouped rows by directory and by primary class to establish directory-level and class-level defaults (§5, §6).
3. For every row **not** defaulted to "remain in place" under the classification rules in §5, ran a repository-wide dependency search (`git grep`, case-insensitive, both basename and full relative path) across all tracked files, then manually inspected every hit that fell in a code, test, CI, or AI-bootstrap file to confirm whether it is a genuine runtime/CI dependency or a source-comment/docstring mention (§7, §8).
4. Classified every reference using the six-way taxonomy in §8 and assigned a relocation-risk rating using the four-way scale in §9.
5. Built a proposed destination path for every relocation candidate under the structural principles in §4, checked for destination collisions (none found), and grouped candidates into reviewable batches of ≤20 files unless the whole batch is uniformly low-risk and mechanically identical (§18).
6. Cross-checked the 46-file Phase B5D onboarding-mapping set and the eight Phase B5C generated-output files against this audit's recommendations to confirm no contradiction with approved Phase B outcomes.

**Model:** Claude Sonnet performed all diagnosis, directory-mix judgment, AI-bootstrap conflict analysis, and target-structure evaluation in this document. Auto-equivalent mechanical scripts (temporary, deleted before commit) performed inventory extraction, `git grep` reference searches, count reconciliation, and destination-collision checking. No Opus escalation was required: no unresolved architecture or runtime-dependency conflict was found — the two genuine operational hard dependencies identified (§8.1) have an unambiguous "do not move" resolution, and the AI-bootstrap findings (§9, §12) are documentation-consistency corrections, not architecture contradictions.

## 3. Current repository structure

Documentation-relevant tracked paths fall into these top-level locations (see §6 for full directory audit):

```text
.                          (root: README, AI_CONTEXT, config manifests, 6 generated captures)
.cursor/rules/             (2 active Cursor rules)
.github/                   (1 retired-Copilot instructions file, 1 CI workflow)
conformance/               (1 README + live conformance harness code)
docs/
  ARCHITECTURE.md, CONVERSATION_ARCHITECTURE.md, STATE_CONTRACT.md,
  ANSWER_SOURCE_CONTRACT.md, ASR_PIPELINE.md, TEST_STRATEGY.md,
  CHANGE_CHECKLIST.md, ARCHITECTURAL_DECISIONS.md, DOCUMENT_AUTHORITY_INDEX.md  (9 class-A)
  DEVELOPER_ONBOARDING.md, MANDARINOS_REGRESSION_LOCK.md, RESPONSE_OPTION_STYLE_GUIDE.md,
  PHASE_B5_SCOPE_ASSESSMENT.md (E), REPO_STRUCTURE_PROPOSAL.md (F), SCHEMA_SYNC_RECOMMENDATION.md (F),
  session_intelligence_architecture.md (F), session_intelligence_implementation_report.md (E)
  Social_Media/             (10 authored marketing/social files, class G)
  briefings/                (36: 28 C historical + 8 E dated evidence)
  design/                   (12: 3 B current, 1 D superseded, 6 C historical, 2 F proposals)
  directives/               (18: 1 B family README + 17 C historical directives)
  phases/                   (15: 1 B family README + 11 C historical + 3 F proposals)
  plans/                    (3 F proposals)
  project/                  (25: 4 F, 1 D, 6 C, 12 E, 2 G)
  reports/                  (10 E dated evidence)
  specs/                    (60: 3 B, 8 D, 4 E, 7 F, 38 C — the largest single family)
  state/                    (1 E dated evidence)
integration_kit/            (1 C README + 3 C examples + 1 C schema README)
runtime/                    (1 B README, co-located with runtime index artefacts)
scripts/                    (1 G generated audit capture; otherwise live code)
tools/coverage/              (1 G generated coverage report; otherwise live code)
```

## 4. Desired structural principles

Evaluating the proposed target structure in the directive against the evidence gathered:

1. **`docs/supporting/` is not recommended.** Only 20 class-B files exist, and the great majority are anchored to their current location for an operational or AI-bootstrap reason: 5 at the repository root (conventional entry points), 2 under `.cursor/rules/` (fixed by Cursor's own rule-discovery convention), 3 under `docs/design/` and 3 under `docs/specs/` (actively cited by `AI_CONTEXT.md` and `.cursor/rules/mandarinos-architecture.mdc` as mandatory reading), 1 under `conformance/` and 1 under `runtime/` (co-located with the code/artefacts they document), and 2 family-guide READMEs that must stay at their directory entry point under the Phase B5B redirect policy. Consolidating these into `docs/supporting/` would require touching the Cursor rule and `AI_CONTEXT.md` for negligible onboarding benefit — this fails the "no structural complexity without clear onboarding value" test in §4 of the directive. **Recommendation: class-B files remain at their current, already-discoverable locations.**
2. **A single `docs/archive/` tree is sufficient**, subdivided by family (`directives/`, `phases/`, `briefings/`, `design-history/`, `specs/`, `project/`, `superseded/`). One tree with family subdirectories gives the same clarity as multiple archive roots with less structural overhead.
3. **Evidence (class E) belongs under a separate, top-level `docs/evidence/` tree, not `docs/archive/evidence/`.** Phase B deliberately distinguished class E ("dated evidence — retains standing as a factual record of what was observed at a point in time") from class D/C ("superseded" / "historical, no longer authoritative"). Filing dated evidence under the same `archive/` root as obsolete and superseded material would blur a distinction Phase B spent 36 approved notices establishing. A sibling `docs/evidence/` tree (mirroring the source family: `evidence/reports/`, `evidence/briefings/`, `evidence/project/`, `evidence/specs/`, `evidence/state/`) preserves that distinction physically.
4. **Class-F proposals should remain visible under a top-level `docs/proposals/`, not buried in `docs/archive/`.** Unimplemented proposals retain live planning value; archiving them beside obsolete material would discourage the "check whether a proposal has since been implemented" step Phase B's class-F notices already require.
5. **A `docs/generated/` tree, as sketched in the directive, does not match reality and is not recommended.** None of the 20 class-G files actually live under `docs/` except the 10 authored (not generated) `docs/Social_Media/` marketing files and 2 authored (not generated) `docs/project/` workflow templates. The genuinely generated/captured outputs live at the repository root (6 files), in `scripts/` (1 file), and in `tools/coverage/` (1 file) — each co-located with its producing script or consumer. Introducing a `docs/generated/` tree would require moving files *into* `docs/` from outside it, adding confusion rather than removing it. **Recommendation: no `docs/generated/` tree; instead formalise the existing decentralised pattern (output stays next to its producer) and relocate only the 6 dependency-free root-level captures to a small `generated/captures/` directory at the repository root (§14, §18 batch C2F).**
6. **Generated outputs should remain tracked for now.** `tools/coverage/coverage_report.md` is read by CI (`.github/workflows/coverage_scan.yml`) and must stay tracked and at its current path; the same applies to its sibling `.json`. The other 7 generated/captured files have no producing-workflow or CI dependency found; they are candidates for a lighter-weight `.gitignore` policy in a future phase, but this audit does not recommend untracking them now (the directive's §2 forbids deleting or ignoring files in this phase in any case).
7. **`integration_kit/` should remain in place in its entirety**, including its 3 historical examples and schema README. No code or test path dependency was found, but the family is small (5 files), already governed end-to-end by the Phase B5B `integration_kit/README.md` guide, and splitting 3 of 5 files into an archive subdirectory would fragment a family that already reads coherently as a single historical unit.

## 5. Classification-based treatment

| Class | Count | Default treatment applied | Outcome of this audit |
| ----- | ----- | -------------------------- | ---------------------- |
| A | 9 | Remain in stable, prominent locations; no archive; no rename | All 9 confirmed **remain in place** directly under `docs/`. No exception found. |
| B | 20 | Remain visible; may move to `docs/supporting/` only with clear benefit; never archived merely for not being class A | All 20 confirmed **remain in place** at current paths (§4.1). None proposed for `docs/supporting/`. |
| C | 112 | Principal archival-candidate population; assess whether current folder/filename falsely implies current authority | 106 proposed for relocation (archive or evidence, depending on sub-role); 6 recommended to remain (3 family READMEs, 3 `integration_kit/` files) — see §11–§13. |
| D | 10 | Archive under a clearly superseded location; preserve notices; confirm no active bootstrap/script/CI dependency | All 10 have zero operational/CI dependency. 10 of 10 proposed for relocation to `docs/archive/superseded/`; 2 flagged medium-risk for an `AI_CONTEXT.md` "mandatory read" reference that should be corrected alongside the move (§9, §12). |
| E | 37 | Retain as dated evidence; move to a clearly labelled evidence structure where safe | 36 proposed for relocation to `docs/evidence/<family>/`; 1 (`docs/PHASE_B5_SCOPE_ASSESSMENT.md`) recommended to remain in place for now because it is an actively cited approved scope authority for the whole Phase B5/B5D/C1 programme. |
| F | 22 | Move to a proposals/unimplemented-specifications archive; preserve notices; keep separate from active contracts | All 22 proposed for relocation to `docs/proposals/` (visible, not archived — §4.4). 8 flagged medium-risk for code-comment or `AI_CONTEXT.md` references. |
| G | 20 | Move to generated-output/captured-output locations where safe; assess tracking; do not delete/ignore | 6 root-level captures proposed for relocation to `generated/captures/`; 14 recommended to remain in place (1 CI-dependent generated report, 1 unreferenced generated capture, 10 authored `Social_Media/` collateral, 2 authored `project/` templates already covered by Phase B5D). |
| H | 0 | — | Confirmed zero class-H rows exist in §17. |

## 6. Directory audit

| Directory | Inventoried docs | Class distribution | Character | Confusion risk | Dependency risk | Recommended future treatment |
| --------- | ---------------- | ------------------- | --------- | --------------- | ----------------- | ------------------------------ |
| repository root (`.`) | 11 | B 5, G 6 | Mixed (current entry points + ad hoc generated captures) | Low for the 5 B files (all conventional); Low for the 6 G captures (obviously informal dump filenames) | None found | Keep the 5 B files at root; relocate the 6 captures to `generated/captures/` (C2F) |
| `.cursor/rules/` | 2 | B 2 | Current, active | None | High (Cursor rule-discovery convention fixes the path) | Remain in place |
| `.github/` | 1 (+1 workflow, not inventoried) | C 1 | Historical, retired tooling | Low | None operational; only comment mentions | Remain in place this round; candidate for a future small dedicated batch |
| `conformance/` | 1 | B 1 | Current, operational | None | Medium (documents the live `run_conformance.py` entry point) | Remain in place |
| `docs/` (top level) | 17 | A 9, B 3, E 2, F 3 | Mixed by design — the 9 class-A anchors plus a small set of actively cited class-B/E/F files | Low (already governed by §17/§13) | Low–Medium (`session_intelligence_architecture.md` has 5 code-comment references) | Class-A/B remain; E/F proposed to `docs/evidence/`/`docs/proposals/` per §5, with `PHASE_B5_SCOPE_ASSESSMENT.md` remaining for now |
| `docs/Social_Media/` | 10 | G 10 | Authored marketing/social collateral, not generated | None | None | Remain in place |
| `docs/briefings/` | 36 | C 28, E 8 | Mixed — historical strategist correspondence (C) cleanly separable from dated audits (E) | Medium — 9 of the 28 C files are cited as "mandatory"/"read-first" in `AI_CONTEXT.md` (§9, §12) | Low operational; Medium AI-bootstrap | Split: C → `docs/archive/briefings/` (28, two sub-batches by risk); E → `docs/evidence/briefings/` (8) |
| `docs/design/` | 12 | B 3, D 1, C 6, F 2 | Genuinely mixed — must not move wholesale | Medium (constitution/governance-model B files sit beside historical C and superseded D files with similar naming) | Medium (`TRACE_CONTRACT_v1.md` and `MandarinOS Developer Handoff.txt` are AI_CONTEXT-cited; `CURSOR_STARTUP_PROTOCOL.md` is a known, previously documented AI-bootstrap conflict — §18 line "onboarding order is superseded") | B remains; D → `docs/archive/superseded/`; C → `docs/archive/design-history/`; F → `docs/proposals/` |
| `docs/directives/` | 18 | B 1 (README), C 17 | Historical family with an existing family guide | Low (already B5B-guided) | Low; 4 of 17 have a single code-comment reference each | README remains; 17 historical directives → `docs/archive/directives/` (C2A) |
| `docs/phases/` | 15 | B 1 (README), C 11, F 3 | Historical family with an existing family guide, plus 3 still-unimplemented proposals | Low–Medium (`PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` is `AI_CONTEXT.md`-cited as read-first) | Low | README remains; 11 historical phase files → `docs/archive/phases/` (C2B); 3 F files → `docs/proposals/` |
| `docs/project/` | 25 | F 4, D 1, C 6, E 12, G 2 | Genuinely mixed procedural/evidence directory | Low–Medium | Low | D → superseded; C → `docs/archive/project/`; E → `docs/evidence/project/`; F → `docs/proposals/`; G (2 active templates) remain |
| `docs/reports/` | 10 | E 10 | Uniform dated-evidence family, each file produced by a matching `scripts/audit_*.py` | Low | Medium (each file has exactly one code-comment "writes docs/reports/X.md" reference; not a runtime dependency) | All 10 → `docs/evidence/reports/` (C2E4); update the 10 producing-script comments in the same batch |
| `docs/specs/` | 60 | B 3, D 8, E 4, F 7, C 38 | Largest single family; genuinely mixed | Medium (many similarly named `mandarinos_*_engine_v*` files) | Low for the 38 C files; Medium for 6 of them with code-comment/`AI_CONTEXT.md` references | B remains (AI-bootstrap cited); D → superseded; E → `docs/evidence/specs/`; F → `docs/proposals/`; C → `docs/archive/specs/` (two sub-batches by risk) |
| `docs/state/` | 1 | E 1 | Single dated-evidence file | Low | None | → `docs/evidence/state/` (C2E5) |
| `integration_kit/` | 1 | C 1 (README) | Family entry point, already B5B-guided | Low | None | Remains in place |
| `integration_kit/examples/` | 3 | C 3 | Small historical example set | Low | None | Remains in place (§4.7) |
| `integration_kit/schemas/` | 1 | C 1 (README) | Schema index co-located with schemas | Low | None | Remains in place |
| `runtime/` | 1 | B 1 | Co-located with runtime index artefacts | None | Low | Remains in place |
| `scripts/` | 1 | G 1 (`_engine_audit.txt`) | Isolated capture file among live code | Low | None found (no producing script identified) | Remains in place pending a future low-priority review |
| `tools/coverage/` | 1 | G 1 (`coverage_report.md`) | Generated report co-located with its generator | None | **High** — confirmed CI dependency | Remains in place; do not move without a coordinated CI/script path change |

## 7. Dependency-search results

The dependency search covered all 230 inventoried paths, using both exact relative-path and filename-only, case-insensitive `git grep` across every tracked file (code, tests, CI, shell/PowerShell, Python, JS, HTML, JSON, YAML, Markdown, text directives, Cursor rules, `.github/copilot-instructions.md`, `AI_CONTEXT.md`, onboarding documents, and README files). Every hit inside a `.py`/`.js`/`.sh`/`.ps1`/CI-workflow file was individually opened and inspected to distinguish a genuine runtime/CI dependency from a source-comment or docstring mention.

Totals across all 230 rows:

* Files carrying at least one code/test/CI-file hit: 27 (of which only **2** are confirmed genuine runtime/CI hard dependencies — §8.1; the remaining 25 are comment/docstring mentions — §8.3/§8.4).
* Files carrying at least one AI-bootstrap reference (`AI_CONTEXT.md`, `.cursor/rules/*.mdc`, or `.github/copilot-instructions.md`): 35, totalling 43 individual references.
* Files carrying at least one Markdown/text ("documentation-type") reference: effectively all 230 — this figure is dominated by `docs/DOCUMENT_AUTHORITY_INDEX.md` and `docs/PHASE_B5_SCOPE_ASSESSMENT.md`, which by design list every inventoried path, plus the dense historical cross-linking among the `docs/briefings/`, `docs/design/`, `docs/phases/`, and `docs/specs/` families themselves.

**A reference count is not a document count**, and it does not by itself indicate risk: a single historical briefing that cross-references six other historical briefings contributes six "documentation" references without creating any dependency that could break. The risk-relevant signal is confined to §8.1 (operational) and §9 (AI-bootstrap), both reported precisely below.

## 8. Operational hard dependencies

Two, and only two, of the 230 inventoried files are genuine operational hard dependencies — confirmed by reading the consuming code, not by comment co-occurrence:

### 8.1 Confirmed hard dependencies

| Path | Class | Consumer | Nature of dependency |
| ---- | ----- | -------- | --------------------- |
| `requirements.txt` | B | `tests/test_deployment_hygiene.py` | `(ROOT / "requirements.txt").read_text(...)`; the test reads and asserts on file content. Moving this file would break the test. |
| `tools/coverage/coverage_report.md` | G | `.github/workflows/coverage_scan.yml` (existence check `if [ ! -f tools/coverage/coverage_report.md ]`) and `tools/coverage/coverage_scan.py` (`md_path = out_dir / "coverage_report.md"`, the writer) | CI fails the build if the file is missing at this exact path; the generator writes to this exact path. Moving this file requires a coordinated CI-workflow and script change, not a documentation-only move. |

Both are rated **"do not move"** in this audit (§9, §13) and are not part of any Phase C2 batch.

### 8.2 No other CI/build dependency found

`git ls-files ".github/workflows/*"` returns exactly one workflow (`coverage_scan.yml`), and it references no other inventoried document path. No other `.yml`/`.yaml` file references any candidate path.

### 8.3 Code-comment / docstring references (not hard dependencies)

25 files carry a code- or docstring-level mention of their own path (e.g. `Authoritative: docs/phases/PHASE10_TECHNICAL_PROPOSAL.md §3.` in `scripts/persona_data.py`, or `Architecture reference: docs/session_intelligence_architecture.md` in five `scripts/*.py` files). None of these reads the file at runtime; each is a source comment that documents intent for a human reader. Moving the referenced document does not break the script, but the comment becomes a stale pointer. These are treated as **Medium** relocation risk (comment-currency, not runtime risk) and listed for a mechanical comment update in the same batch as the move (§18).

### 8.4 requirements-tools.txt

`requirements-tools.txt` appears only inside a docstring usage example (`pip install -r requirements-tools.txt`) in `tools/enrich_characters_1200_pinyin_gloss.py` — an example shell command, not a code dependency. It remains at the root regardless (class B, active tooling manifest); this is noted for completeness, not as a risk driver.

## 9. AI and bootstrap dependencies

`AI_CONTEXT.md` §11 ("Read-first files for any AI assistant") and its "Extensibility strategy" / "Phase alignment" subsections describe several documents as **"mandatory"** or **"read-first"** for any AI assistant. Cross-checking these citations against the Phase B classification in `docs/DOCUMENT_AUTHORITY_INDEX.md` finds:

* Two citations were **already identified and recorded** as conflicts in the authority index's existing §18 "Principal conflicts identified" list: the "Authoritative" headings on `AI_CONTEXT.md`/`MANDARINOS_SYSTEM_MAP.md`, and `docs/design/CURSOR_STARTUP_PROTOCOL.md`'s onboarding order being superseded by `docs/ARCHITECTURE.md` §21. This audit confirms both remain live in the current file content.
* This audit additionally finds **nine class-C historical briefings** and **one class-C design document** described as "mandatory ... read before proposing any change" or "mandatory for conversation-layer work" in `AI_CONTEXT.md`, despite Phase B5D's approved onboarding guidance stating explicitly that class-C material "does not independently authorise changes":
  * `docs/briefings/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` — described as the "authoritative copy" of the extensibility directive, with the canonical class-B copy under `docs/specs/` characterised as merely "a parallel copy" — this is **the reverse of the Phase B5D authority determination**, which treats the `docs/specs/` copy as the governed class-B document and the `docs/briefings/` copy as a class-C historical duplicate.
  * `docs/briefings/MandarinOS_Phase_12C_Alignment_Brief.md`, `docs/briefings/MandarinOS_Phase12D_Cursor_Implementation_Brief.md`, `docs/briefings/USER_LED_DISCOVERY_STRATEGIST_BRIEF.md` — each described as "mandatory" reading for current conversation-layer/12C/12D work.
  * `docs/briefings/MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt`, `docs/briefings/MANDARINOS_PHASE_10_7_PHASE_11_BRIEFING.txt`, `docs/briefings/PHASE10_STRATEGIST_BRIEFING_SPECS_GAP_AND_PATH.md`, `docs/briefings/PHASE_10_5_10_6_ALPHA_STRATEGIST_BRIEFING.md`, `docs/briefings/PHASE7_COMPLETION_REVIEW_AND_TEST.md` — each cited as background/context for current work.
  * `docs/design/TRACE_CONTRACT_v1.md` — described as "the trace contract" to read before architectural suggestions (this file already carries an approved Phase B5A class-C individual notice).
* Two class-D superseded files are also `AI_CONTEXT.md`-cited: `docs/design/CURSOR_STARTUP_PROTOCOL.md` (already a known conflict, above) and `docs/project/MANDARINOS_PROJECT_PLAN_v1.md` (cited as "the current development roadmap," though it is superseded by the v2 roadmap per the index's own §18 conflict list).

**Finding, not an unresolved architectural contradiction:** this is a documentation-consistency gap between `AI_CONTEXT.md`'s self-declared "mandatory"/"read-first" language and the R2 hierarchy Phase B approved (where `AI_CONTEXT.md` itself is class B, subordinate to the nine-document class-A package, and class-C briefings are historical/contextual only). It does not involve a runtime dependency, a competing archive structure, or class-B/class-C ambiguity that code enforces — it is confined to prose in one file. It is recorded here as a **relocation-risk driver** (these 11 files are rated Medium, not Low, and their proposed batches are separated from the low-risk core so an `AI_CONTEXT.md` wording correction can be scheduled alongside or before the move) rather than escalated to Opus. A future Phase C batch (or an Auto/Composer housekeeping pass) should update `AI_CONTEXT.md` §11 and the "Extensibility strategy"/"Phase alignment" subsections to point to the nine-document R2 package and the Phase B5D 46-file mapping instead of naming individual class-C briefings as "mandatory."

Total AI-bootstrap dependency footprint: **35 distinct files**, **43 references**, of which 12 files are already in the "remain in place" set (§13) and 23 are relocation candidates carrying a Medium-risk rating for this reason (§12, §18).

## 10. Documentation-link dependencies

Ordinary Markdown/text cross-references dominate the reference count (§7) and fall into two sub-patterns:

1. **Structural self-listing** — `docs/DOCUMENT_AUTHORITY_INDEX.md` and `docs/PHASE_B5_SCOPE_ASSESSMENT.md` reference nearly every one of the 230 paths by design (they are the classification registers). These references require a mechanical path update if and when a Phase C2 batch executes, but they carry no judgment risk — the update is a simple find-and-replace verified by the existing verification scripts used in every prior Phase B batch.
2. **Genuine historical cross-links** — briefings that reference other briefings, specs that reference other specs, design documents that reference the trace contract, and so on. These are true "documentation link" dependencies in the sense used by the directive: mechanically updatable, and normally left unless a document is actually moved.

No documentation link was found that, if left un-updated after a future move, would silently point to a non-existent file without warning — Git history preserves the old path, and a `git mv` in a future batch would be paired with the standard link-verification step already used throughout Phase B.

## 11. Safe archival candidates

The following families are rated **uniformly Low risk** and are the safest starting point for a future Phase C2:

* `docs/directives/` — 13 of 17 historical directive files (Low risk; 4 have a single code-comment reference and are Medium).
* `docs/phases/` — 10 of 11 historical phase files (Low; 1 — `PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` — is `AI_CONTEXT.md`-cited and Medium).
* `docs/briefings/` — 20 of 28 historical briefings (Low; the remaining 8 are the `AI_CONTEXT.md`-cited Medium set from §9).
* `docs/specs/` — 32 of 38 historical specs (Low; 6 have a code-comment or `AI_CONTEXT.md` reference and are Medium).
* `docs/project/` — all 6 historical project notes (Low).
* All 10 class-D superseded documents (Low except the 2 `AI_CONTEXT.md`-cited files, which are Medium).
* All 36 class-E evidence files except `docs/PHASE_B5_SCOPE_ASSESSMENT.md` (mostly Low; 6 `docs/reports/` files and 1 `docs/briefings/` file carry a single code-comment or AI-bootstrap reference and are Medium).
* 14 of 22 class-F proposals (Low; 8 have a code-comment or `AI_CONTEXT.md` reference and are Medium).
* 6 root-level generated captures (Low; no dependency of any kind found).

The full per-file table is in §17.

## 12. Mixed or high-risk candidates

**No relocation candidate is rated High risk in this audit.** The only two genuine hard dependencies found (§8.1) are resolved as "do not move" rather than as a high-risk relocation, because moving either would require a coordinated code/CI change that is out of scope for a documentation-relocation batch.

41 relocation candidates are rated **Medium risk**, all for one of two reasons:

* **23 files** carry an `AI_CONTEXT.md` "mandatory"/"read-first" citation (§9) — recommend correcting the `AI_CONTEXT.md` wording in the same or an immediately preceding batch.
* **19 files** carry one or more code-comment/docstring mentions of their own path (§8.3) — recommend a mechanical comment update (e.g. `scripts/audit_*.py` docstrings, `scripts/persona_data.py`/`scripts/learner_memory*.py` "Authoritative:" lines, `scripts/ui_server.py` inline comment) in the same batch as the move.

(1 file — `docs/briefings/MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt` — carries both a code-comment and an AI-bootstrap reference and is counted once in the 41.)

No mixed directory (`docs/design/`, `docs/specs/`, `docs/project/`, `docs/briefings/`) is recommended for a wholesale move; each is split by class per §5/§6.

## 13. Documents that should remain in place

50 of the 230 pre-existing inventoried documents are recommended to remain at their current path. Reasons cluster into: class-A governance (9), AI-bootstrap/onboarding entry points (8), Phase B5B family-guide entry points (3), operationally significant class-B files actively cited by the Cursor rule or `AI_CONTEXT.md` (8), confirmed hard dependencies (2), narrowly scoped low-benefit-to-move families (`integration_kit/` — 5; authored `docs/Social_Media/` collateral — 10; 2 active B5D-mapped project templates), 1 actively cited dated-evidence scope assessment, and 2 files with no dependency evidence but no clear relocation benefit either (`.github/copilot-instructions.md`, `scripts/_engine_audit.txt`).

Full "remain in place" table:

| Path | Class | Authority | Reason to remain |
| ---- | ----- | --------- | ----------------- |
| `.cursor/rules/mandarinos-architecture.mdc` | B | `docs/ARCHITECTURAL_DECISIONS.md` | active Cursor coding rule; path is fixed by Cursor's rule-discovery convention |
| `.cursor/rules/mandarinos-ui-objects.mdc` | B | `docs/ARCHITECTURE.md` | active Cursor coding rule; path is fixed by Cursor's rule-discovery convention |
| `.github/copilot-instructions.md` | C | `AI_CONTEXT.md`, `.cursor/rules/*`, `docs/CHANGE_CHECKLIST.md` §23 | conventional `.github/` location; only comment-level mentions found; deferred to a future dedicated small batch |
| `AI_CONTEXT.md` | B | `docs/ARCHITECTURE.md` | AI/bootstrap entry point; read-first file for AI assistants |
| `MANDARINOS_SYSTEM_MAP.md` | B | `docs/ARCHITECTURE.md` | root-level orientation map; B1-noticed but still an expected root entry point |
| `README.md` | B | — | repository entry point; conventional root location expected by GitHub and new contributors |
| `conformance/README.md` | B | `docs/TEST_STRATEGY.md` | operationally significant; documents the live `conformance/run_conformance.py` entry point |
| `docs/ANSWER_SOURCE_CONTRACT.md` | A | — | class-A R2 governance document |
| `docs/ARCHITECTURAL_DECISIONS.md` | A | — | class-A R2 governance document |
| `docs/ARCHITECTURE.md` | A | — | class-A R2 governance document |
| `docs/ASR_PIPELINE.md` | A | — | class-A R2 governance document |
| `docs/CHANGE_CHECKLIST.md` | A | — | class-A R2 governance document |
| `docs/CONVERSATION_ARCHITECTURE.md` | A | — | class-A R2 governance document |
| `docs/DEVELOPER_ONBOARDING.md` | B | `docs/ARCHITECTURE.md` | top-level onboarding entry point; part of the approved developer entry path |
| `docs/DOCUMENT_AUTHORITY_INDEX.md` | A | — | class-A R2 governance document |
| `docs/MANDARINOS_REGRESSION_LOCK.md` | B | `docs/TEST_STRATEGY.md` | referenced by `tests/test_golden_regression.py` docstring as the rationale record for the golden-regression suite |
| `docs/PHASE_B5_SCOPE_ASSESSMENT.md` | E | dated evidence only | actively cited approved scope authority for the whole Phase B5/B5D/C1 programme; premature to archive while still an active reference |
| `docs/RESPONSE_OPTION_STYLE_GUIDE.md` | B | `docs/ANSWER_SOURCE_CONTRACT.md` | current class-B option style rules; no archival value |
| `docs/STATE_CONTRACT.md` | A | — | class-A R2 governance document |
| `docs/Social_Media/*` (10 files) | G | — | authored marketing/social collateral, not generated output; no confusion or dependency risk identified |
| `docs/TEST_STRATEGY.md` | A | — | class-A R2 governance document |
| `docs/design/LICENSE.md` | B | — | legal notice; conventional co-location with other design-root material |
| `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md` | B | nine-document R2 package | actively cited in `AI_CONTEXT.md` and `docs/design/CURSOR_STARTUP_PROTOCOL.md` |
| `docs/design/mandarinos_design_constitution.txt` | B | nine-document R2 package | actively cited as a mandatory read-first file in `AI_CONTEXT.md` §11 |
| `docs/directives/README.md` | B | `docs/CHANGE_CHECKLIST.md`; relevant R2 contracts | Phase B5B family-authority guide; must remain at the directory entry point per redirect policy |
| `docs/phases/README.md` | B | `docs/ARCHITECTURE.md`; `docs/ARCHITECTURAL_DECISIONS.md` | Phase B5B family-authority guide; must remain at the directory entry point per redirect policy |
| `docs/project/CHATGPT_BRANCH_START_TEMPLATE.md` | G | — | active authored workflow template; part of the Phase B5D 46-file onboarding integration set |
| `docs/project/COMMIT_INSTRUCTIONS.md` | G | — | active authored procedural instructions; part of the Phase B5D 46-file onboarding integration set |
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | B | ADR record | canonical copy cited by `.cursor/rules/mandarinos-architecture.mdc` as the full directive |
| `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md` | B | `docs/CONVERSATION_ARCHITECTURE.md` | cited by `.cursor/rules/mandarinos-architecture.mdc` and `AI_CONTEXT.md` as mandatory read for flow changes |
| `docs/specs/MandarinOS_Extensibility_Strategy.md` | B | ADR record | cited by `.cursor/rules/mandarinos-architecture.mdc` and `AI_CONTEXT.md` as the strategy doc |
| `integration_kit/README.md` | C | `docs/ARCHITECTURE.md` | Phase B5B family-authority guide; must remain at the directory entry point per redirect policy |
| `integration_kit/examples/*` (3 files) | C | `docs/ARCHITECTURE.md` | narrowly scoped example set already governed by the B5B `integration_kit/README.md` guide; low benefit to relocate |
| `integration_kit/schemas/README.md` | C | `docs/ARCHITECTURE.md` | kit schema index co-located with the schemas it documents; no dependency evidence found |
| `requirements-tools.txt` | B | repo config | optional-tooling manifest; conventional root location |
| `requirements.txt` | B | repo config | confirmed operational hard dependency: read via `Path.read_text()` in `tests/test_deployment_hygiene.py` |
| `runtime/README_runtime_indexes.txt` | B | `docs/ARCHITECTURE.md` §14 | explains `runtime/` index outputs in place; co-located with the artefacts it documents |
| `scripts/_engine_audit.txt` | G | — | no producing script or dependency identified; conservatively retained pending a future low-priority review |
| `tools/coverage/coverage_report.md` | G | — | confirmed operational hard dependency: path checked by `.github/workflows/coverage_scan.yml` and written by `tools/coverage/coverage_scan.py` |

(Count check: 9 class-A + 5 root class-B + 2 `.cursor/rules` + 1 `conformance` + 3 `docs/` top-level B + 3 `docs/design` B + 2 family READMEs + 1 `runtime` B + 3 `docs/specs` B = 29 class-B/A "current" rows, + 1 `.github` C + 5 `integration_kit` C + 1 `docs/PHASE_B5_SCOPE_ASSESSMENT.md` E + 10 `Social_Media` G + 2 `docs/project` G + 2 hard-dependency G = 50 total.)

## 14. Generated-output treatment

The eight Phase B5C generated/captured outputs and remaining class-G population were assessed individually:

| Path | Producing workflow found? | CI dependency? | Recommendation |
| ---- | -------------------------- | ---------------- | ---------------- |
| `tools/coverage/coverage_report.md` | Yes — `tools/coverage/coverage_scan.py` | Yes — `.github/workflows/coverage_scan.yml` | **Do not move.** Remains tracked at current path. |
| `scripts/_engine_audit.txt` | Not identified | No | Remains tracked at current path pending future review; low-risk to move if a producer is later identified. |
| `fo_check.txt`, `frame_dump.txt`, `frame_texts.txt`, `server_out.txt`, `server_err.txt`, `server_startup_err.txt` (root-level) | Ad hoc manual/debug captures; no producing script found | No | Low risk to relocate to `generated/captures/` (Phase C2F); remain tracked (directive §2/§7 forbid deletion or ignoring in this phase). |
| `docs/Social_Media/*` (10 files) | Authored, not generated | No | Remain in place; out of scope for generated-output treatment. |
| `docs/project/CHATGPT_BRANCH_START_TEMPLATE.md`, `docs/project/COMMIT_INSTRUCTIONS.md` | Authored, not generated | No | Remain in place; already part of the Phase B5D 46-file onboarding set. |

No generated output is recommended to move outside version control in this phase. A future phase may consider a `.gitignore` policy for *newly created* debug captures (not the six already-tracked files) once a stable naming convention for such captures is agreed — that decision is deferred, not made here.

## 15. Redirect and compatibility policy

Applying the directive's four preferred compatibility mechanisms in priority order:

1. **Retain a family README at the original directory** — already in place and sufficient for `docs/directives/README.md`, `docs/phases/README.md`, and `integration_kit/README.md` (all three Phase B5B guides). No new redirect stub is needed for any file inside a directory that keeps its family README.
2. **Update tracked internal links** — deferred to the execution phase (Composer 2.5) for each approved batch; not performed here.
3. **A short relocation pointer for a small number of high-value entry points** — recommended for exactly one case beyond the three existing READMEs: **`AI_CONTEXT.md`** should gain a brief correction (not a new stub file) replacing its "mandatory"/"read-first" citations of class-C briefings and the class-D `CURSOR_STARTUP_PROTOCOL.md` with pointers to the nine-document R2 package and the Phase B5D mapping (§9). This is a wording correction to an existing file, not a new redirect stub, and is **not implemented in this phase**.
4. **Rely on Git history for low-risk individual files** — the default for all 180 relocation candidates; no per-file redirect stub is proposed.

**No redirect stub is proposed for creation in Phase C1**, consistent with the directive's §10 instruction. Exactly **3** existing compatibility entry points (the three B5B family READMEs) are identified as sufficient, plus 1 recommended future wording correction (`AI_CONTEXT.md`) that is not a redirect stub.

## 16. Proposed target structure

```text
docs/
├── ARCHITECTURE.md
├── CONVERSATION_ARCHITECTURE.md
├── STATE_CONTRACT.md
├── ANSWER_SOURCE_CONTRACT.md
├── ASR_PIPELINE.md
├── TEST_STRATEGY.md
├── CHANGE_CHECKLIST.md
├── ARCHITECTURAL_DECISIONS.md
├── DOCUMENT_AUTHORITY_INDEX.md
├── DEVELOPER_ONBOARDING.md
├── MANDARINOS_REGRESSION_LOCK.md
├── RESPONSE_OPTION_STYLE_GUIDE.md
│
├── design/            (unchanged: 3 class-B files remain; historical/superseded/proposal files extracted below)
├── specs/              (unchanged: 3 class-B files remain; historical/superseded/proposal files extracted below)
├── directives/README.md   (family guide remains at entry point)
├── phases/README.md       (family guide remains at entry point)
│
├── archive/
│   ├── directives/      (17 historical directives)
│   ├── phases/          (11 historical phase documents)
│   ├── briefings/       (28 historical briefings)
│   ├── design-history/  (6 historical design documents)
│   ├── specs/           (38 historical specs)
│   ├── project/         (6 historical project notes)
│   └── superseded/      (10 class-D documents, cross-directory)
│
├── evidence/
│   ├── briefings/       (8 briefing audits)
│   ├── specs/           (4 spec audits)
│   ├── project/         (12 project status/commit records)
│   ├── reports/         (10 reports-directory audits)
│   └── state/           (1 state snapshot)
│
├── proposals/           (22 class-F proposals, flat — small enough not to need subdirectories)
│
├── Social_Media/        (unchanged — authored collateral)
├── briefings/README.md  → superseded by archive/evidence split above; family README relocates or is retired once all 36 members have moved (Phase C2 closeout decision)
├── project/              (2 active templates remain; historical/evidence/proposal members extracted above)
└── (unchanged) PHASE_B5_SCOPE_ASSESSMENT.md, session_intelligence_architecture.md*, session_intelligence_implementation_report.md*, REPO_STRUCTURE_PROPOSAL.md*, SCHEMA_SYNC_RECOMMENDATION.md*
    (* candidates for docs/proposals/ or docs/evidence/ per §5 — not yet moved)

generated/
└── captures/            (6 root-level debug/session captures)

integration_kit/          (unchanged, all 5 files remain)
runtime/                   (unchanged)
```

This differs from the directive's sketch in three respects, each justified in §4: no `docs/supporting/` tree (class-B files stay where they already are); `docs/evidence/` is a sibling of `docs/archive/`, not nested under it; there is no `docs/generated/` tree (generated outputs stay decentralised, co-located with their producers, except for the 6 dependency-free root captures which move to a repository-root `generated/captures/`).

## 17. Proposed relocation map

180 of the 230 pre-existing inventoried documents are proposed for relocation. Grouped by proposed Phase C2 batch (see §18 for batch rationale); every row below is a distinct candidate with a unique proposed destination (no two candidates share a destination path — verified programmatically).

#### C2A — historical directives (docs/directives/, class C) — 17 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/directives/MANDARINOS_ARCHITECT_COPILOT_HANDOFF_DIRECTIVE_PHASE7.txt` | C | `docs/archive/directives/MANDARINOS_ARCHITECT_COPILOT_HANDOFF_DIRECTIVE_PHASE7.txt` | Low | 0 | 0 | 6 |
| `docs/directives/MANDARINOS_COPILOT_STARTUP_INSTRUCTIONS.txt` | C | `docs/archive/directives/MANDARINOS_COPILOT_STARTUP_INSTRUCTIONS.txt` | Low | 0 | 0 | 5 |
| `docs/directives/MandarinOS_OPEN_CARD_Trace_Wiring_Directive.txt` | C | `docs/archive/directives/MandarinOS_OPEN_CARD_Trace_Wiring_Directive.txt` | Low | 0 | 0 | 3 |
| `docs/directives/MandarinOS_OPEN_CARD_Unit_Test_Directive.txt` | C | `docs/archive/directives/MandarinOS_OPEN_CARD_Unit_Test_Directive.txt` | Low | 0 | 0 | 3 |
| `docs/directives/MandarinOS_Phase_Boundaries_v1.0.txt` | C | `docs/archive/directives/MandarinOS_Phase_Boundaries_v1.0.txt` | Low | 0 | 0 | 4 |
| `docs/directives/MandarinOS_Runtime_Card_Integration_Directive.txt` | C | `docs/archive/directives/MandarinOS_Runtime_Card_Integration_Directive.txt` | Low | 0 | 0 | 3 |
| `docs/directives/MandarinOS_Simulator_Entrypoint_Copilot_Directive.txt` | C | `docs/archive/directives/MandarinOS_Simulator_Entrypoint_Copilot_Directive.txt` | Low | 0 | 0 | 3 |
| `docs/directives/MandarinOS_TurnState_Trace_Contract_v1_directive.txt` | C | `docs/archive/directives/MandarinOS_TurnState_Trace_Contract_v1_directive.txt` | Low | 0 | 0 | 3 |
| `docs/directives/MandarinOS_UI_Shell_Copilot_Directive.txt` | C | `docs/archive/directives/MandarinOS_UI_Shell_Copilot_Directive.txt` | Low | 0 | 0 | 4 |
| `docs/directives/MandarinOS_card_contract_v1_directive.txt` | C | `docs/archive/directives/MandarinOS_card_contract_v1_directive.txt` | Low | 0 | 0 | 4 |
| `docs/directives/MandarinOS_conformance_harness_directive.txt` | C | `docs/archive/directives/MandarinOS_conformance_harness_directive.txt` | Medium | 1 | 0 | 4 |
| `docs/directives/MandarinOS_content_coverage_scanner_v1_directive.txt` | C | `docs/archive/directives/MandarinOS_content_coverage_scanner_v1_directive.txt` | Medium | 1 | 0 | 3 |
| `docs/directives/MandarinOS_hint_cascade_directive.txt` | C | `docs/archive/directives/MandarinOS_hint_cascade_directive.txt` | Medium | 1 | 0 | 3 |
| `docs/directives/MandarinOS_integration_kit_scenarios_v1_directive.txt` | C | `docs/archive/directives/MandarinOS_integration_kit_scenarios_v1_directive.txt` | Low | 0 | 0 | 4 |
| `docs/directives/MandarinOS_scaffolding_transition_harness_v1_directive.txt` | C | `docs/archive/directives/MandarinOS_scaffolding_transition_harness_v1_directive.txt` | Medium | 1 | 0 | 3 |
| `docs/directives/MandarinOS_universal_cards_builder_v1_directive.txt` | C | `docs/archive/directives/MandarinOS_universal_cards_builder_v1_directive.txt` | Low | 0 | 0 | 3 |
| `docs/directives/mandarinos_copilot_architecture_update.txt` | C | `docs/archive/directives/mandarinos_copilot_architecture_update.txt` | Low | 0 | 0 | 5 |

#### C2B — historical phase documents (docs/phases/, class C) — 11 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/phases/MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md` | C | `docs/archive/phases/MANDARINOS_PHASE9_1_ACCEPTANCE_CRITERIA.md` | Low | 0 | 0 | 3 |
| `docs/phases/MANDARINOS_PHASE_10_5_STABILISATION_BRIEF.md` | C | `docs/archive/phases/MANDARINOS_PHASE_10_5_STABILISATION_BRIEF.md` | Low | 0 | 0 | 5 |
| `docs/phases/MandarinOS_Phase9_Signoff.md` | C | `docs/archive/phases/MandarinOS_Phase9_Signoff.md` | Low | 0 | 0 | 4 |
| `docs/phases/PHASE6_FREEZE.md` | C | `docs/archive/phases/PHASE6_FREEZE.md` | Low | 0 | 0 | 4 |
| `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` | C | `docs/archive/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` | Medium | 0 | 1 | 12 |
| `docs/phases/PHASE6_RUNTIME_INDEXES_NOTES.md` | C | `docs/archive/phases/PHASE6_RUNTIME_INDEXES_NOTES.md` | Low | 0 | 0 | 5 |
| `docs/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md` | C | `docs/archive/phases/PHASE9_1_ACCEPTANCE_CRITERIA.md` | Low | 0 | 0 | 5 |
| `docs/phases/PHASE9_2_BRIDGE_TIER.md` | C | `docs/archive/phases/PHASE9_2_BRIDGE_TIER.md` | Low | 0 | 0 | 4 |
| `docs/phases/PHASE_10_5_CONVERSATION_SIMULATION.md` | C | `docs/archive/phases/PHASE_10_5_CONVERSATION_SIMULATION.md` | Low | 0 | 0 | 3 |
| `docs/phases/Phase 3 Step 1 Audio-first UI.md` | C | `docs/archive/phases/Phase 3 Step 1 Audio-first UI.md` | Low | 0 | 0 | 4 |
| `docs/phases/ROLLBACK_POINT_v1.md` | C | `docs/archive/phases/ROLLBACK_POINT_v1.md` | Low | 0 | 0 | 6 |

#### C2C-core — historical briefings, low-risk core (docs/briefings/, class C) — 20 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/briefings/BRIEFING_CHANGES_FOR_CHATGPT_REVIEW.md` | C | `docs/archive/briefings/BRIEFING_CHANGES_FOR_CHATGPT_REVIEW.md` | Low | 0 | 0 | 1 |
| `docs/briefings/CHATGPT_STRATEGIST_CONVERSATION_DESIGN_BRIEFING.md` | C | `docs/archive/briefings/CHATGPT_STRATEGIST_CONVERSATION_DESIGN_BRIEFING.md` | Low | 0 | 0 | 2 |
| `docs/briefings/MandarinOS_Phase12E_CuriosityProbe_Brief.md` | C | `docs/archive/briefings/MandarinOS_Phase12E_CuriosityProbe_Brief.md` | Low | 0 | 0 | 1 |
| `docs/briefings/MandarinOS_laptop_handoff_UI_cascading_help_briefing.md` | C | `docs/archive/briefings/MandarinOS_laptop_handoff_UI_cascading_help_briefing.md` | Low | 0 | 0 | 2 |
| `docs/briefings/NEXT_PHASE_ADVICE_CURSOR.md` | C | `docs/archive/briefings/NEXT_PHASE_ADVICE_CURSOR.md` | Low | 0 | 0 | 1 |
| `docs/briefings/PHASE7_4_UI_POLISH_STRATEGIST_BRIEFING.md` | C | `docs/archive/briefings/PHASE7_4_UI_POLISH_STRATEGIST_BRIEFING.md` | Low | 0 | 0 | 1 |
| `docs/briefings/PHASE7_COMPLETE_STRATEGIST_BRIEFING.md` | C | `docs/archive/briefings/PHASE7_COMPLETE_STRATEGIST_BRIEFING.md` | Low | 0 | 0 | 2 |
| `docs/briefings/PHASE8_OPTIONS_APPROPRIATENESS.md` | C | `docs/archive/briefings/PHASE8_OPTIONS_APPROPRIATENESS.md` | Low | 0 | 0 | 1 |
| `docs/briefings/PHASE8_STEP1_TRANSCRIPT_ARCHITECTURE.md` | C | `docs/archive/briefings/PHASE8_STEP1_TRANSCRIPT_ARCHITECTURE.md` | Low | 0 | 0 | 1 |
| `docs/briefings/PHASE9_SIGNOFF_STRATEGIST_BRIEFING.md` | C | `docs/archive/briefings/PHASE9_SIGNOFF_STRATEGIST_BRIEFING.md` | Low | 0 | 0 | 1 |
| `docs/briefings/PHASE_12B_STABILIZATION_AND_UI_FLOW_STRATEGIST_BRIEFING.md` | C | `docs/archive/briefings/PHASE_12B_STABILIZATION_AND_UI_FLOW_STRATEGIST_BRIEFING.md` | Low | 0 | 0 | 1 |
| `docs/briefings/PHASE_12C_EXECUTIVE_STRATEGIST_BRIEF.md` | C | `docs/archive/briefings/PHASE_12C_EXECUTIVE_STRATEGIST_BRIEF.md` | Low | 0 | 0 | 1 |
| `docs/briefings/PHASE_12C_STRATEGIST_PROPOSAL_CURIOSITY_PERSONA_SESSION_ARC.md` | C | `docs/archive/briefings/PHASE_12C_STRATEGIST_PROPOSAL_CURIOSITY_PERSONA_SESSION_ARC.md` | Low | 0 | 0 | 1 |
| `docs/briefings/STRATEGIST_BRIEFING_MAY2026_UI_POLISH_AND_DISTANCE_THREAD.md` | C | `docs/archive/briefings/STRATEGIST_BRIEFING_MAY2026_UI_POLISH_AND_DISTANCE_THREAD.md` | Low | 0 | 0 | 2 |
| `docs/briefings/UI_SHELL_STRATEGIST_BRIEFING_APR2026.md` | C | `docs/archive/briefings/UI_SHELL_STRATEGIST_BRIEFING_APR2026.md` | Low | 0 | 0 | 1 |
| `docs/briefings/architecture_briefing_apr2026.md` | C | `docs/archive/briefings/architecture_briefing_apr2026.md` | Low | 0 | 0 | 1 |
| `docs/briefings/mandarinos_chatgpt_session_briefing.md` | C | `docs/archive/briefings/mandarinos_chatgpt_session_briefing.md` | Low | 0 | 0 | 2 |
| `docs/briefings/mandarinos_recovery_phrases_v1_2_cursor_briefing.txt` | C | `docs/archive/briefings/mandarinos_recovery_phrases_v1_2_cursor_briefing.txt` | Low | 0 | 0 | 1 |
| `docs/briefings/phase12c_recovery_trigger_briefing.txt` | C | `docs/archive/briefings/phase12c_recovery_trigger_briefing.txt` | Low | 0 | 0 | 1 |
| `docs/briefings/phase7_3_senior_architect_briefing.md` | C | `docs/archive/briefings/phase7_3_senior_architect_briefing.md` | Low | 0 | 0 | 2 |

#### C2C-review — historical briefings cited as "mandatory"/"read-first" in AI_CONTEXT.md (docs/briefings/, class C) — 8 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/briefings/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | C | `docs/archive/briefings/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | Medium | 0 | 2 | 5 |
| `docs/briefings/MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt` | C | `docs/archive/briefings/MANDARINOS_MOVE_TYPE_TAGGING_BRIEF.txt` | Medium | 1 | 1 | 2 |
| `docs/briefings/MANDARINOS_PHASE_10_7_PHASE_11_BRIEFING.txt` | C | `docs/archive/briefings/MANDARINOS_PHASE_10_7_PHASE_11_BRIEFING.txt` | Medium | 0 | 1 | 2 |
| `docs/briefings/MandarinOS_Phase12D_Cursor_Implementation_Brief.md` | C | `docs/archive/briefings/MandarinOS_Phase12D_Cursor_Implementation_Brief.md` | Medium | 0 | 1 | 1 |
| `docs/briefings/MandarinOS_Phase_12C_Alignment_Brief.md` | C | `docs/archive/briefings/MandarinOS_Phase_12C_Alignment_Brief.md` | Medium | 0 | 1 | 1 |
| `docs/briefings/PHASE10_STRATEGIST_BRIEFING_SPECS_GAP_AND_PATH.md` | C | `docs/archive/briefings/PHASE10_STRATEGIST_BRIEFING_SPECS_GAP_AND_PATH.md` | Medium | 0 | 1 | 2 |
| `docs/briefings/PHASE_10_5_10_6_ALPHA_STRATEGIST_BRIEFING.md` | C | `docs/archive/briefings/PHASE_10_5_10_6_ALPHA_STRATEGIST_BRIEFING.md` | Medium | 0 | 1 | 2 |
| `docs/briefings/USER_LED_DISCOVERY_STRATEGIST_BRIEF.md` | C | `docs/archive/briefings/USER_LED_DISCOVERY_STRATEGIST_BRIEF.md` | Medium | 0 | 1 | 2 |

#### C2D1 — design-history extraction (docs/design/, class C) — 6 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/design/CARDS_BUILD_v1.md` | C | `docs/archive/design-history/CARDS_BUILD_v1.md` | Low | 0 | 0 | 4 |
| `docs/design/MandarinOS Developer Handoff.txt` | C | `docs/archive/design-history/MandarinOS Developer Handoff.txt` | Medium | 0 | 1 | 3 |
| `docs/design/MandarinOS_brief.md` | C | `docs/archive/design-history/MandarinOS_brief.md` | Low | 0 | 0 | 4 |
| `docs/design/TRACE_CONTRACT_v1.md` | C | `docs/archive/design-history/TRACE_CONTRACT_v1.md` | Medium | 0 | 1 | 14 |
| `docs/design/p3_architecture.md` | C | `docs/archive/design-history/p3_architecture.md` | Low | 0 | 0 | 3 |
| `docs/design/ux_flow.txt` | C | `docs/archive/design-history/ux_flow.txt` | Low | 0 | 0 | 3 |

#### C2D2 — superseded documents (class D, cross-directory) — 10 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/design/CURSOR_STARTUP_PROTOCOL.md` | D | `docs/archive/superseded/CURSOR_STARTUP_PROTOCOL.md` | Medium | 0 | 1 | 2 |
| `docs/project/MANDARINOS_PROJECT_PLAN_v1.md` | D | `docs/archive/superseded/MANDARINOS_PROJECT_PLAN_v1.md` | Medium | 0 | 1 | 8 |
| `docs/specs/MandarinOS_conversation_memory_model_v1.md` | D | `docs/archive/superseded/MandarinOS_conversation_memory_model_v1.md` | Low | 0 | 0 | 3 |
| `docs/specs/MandarinOS_conversation_runtime_model_v1.md` | D | `docs/archive/superseded/MandarinOS_conversation_runtime_model_v1.md` | Low | 0 | 0 | 3 |
| `docs/specs/MandarinOS_conversation_state_diagram_v1.md` | D | `docs/archive/superseded/MandarinOS_conversation_state_diagram_v1.md` | Low | 0 | 0 | 3 |
| `docs/specs/MandarinOS_master_AI_bootstrap_context.md` | D | `docs/archive/superseded/MandarinOS_master_AI_bootstrap_context.md` | Low | 0 | 0 | 4 |
| `docs/specs/MandarinOS_runtime_conversation_state_engine_v1.md` | D | `docs/archive/superseded/MandarinOS_runtime_conversation_state_engine_v1.md` | Low | 0 | 0 | 4 |
| `docs/specs/MandarinOS_turn_data_contract_v1.md` | D | `docs/archive/superseded/MandarinOS_turn_data_contract_v1.md` | Low | 0 | 0 | 4 |
| `docs/specs/mandarinos_conversation_architecture_v1.md` | D | `docs/archive/superseded/mandarinos_conversation_architecture_v1.md` | Low | 0 | 0 | 3 |
| `docs/specs/mandarinos_family_conversation_ladder.md` | D | `docs/archive/superseded/mandarinos_family_conversation_ladder.md` | Low | 0 | 0 | 2 |

#### C2D3-core — historical specs extraction, low-risk core (docs/specs/, class C) — 32 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/specs/Live_Beginner_Ability_Model.md` | C | `docs/archive/specs/Live_Beginner_Ability_Model.md` | Low | 0 | 0 | 3 |
| `docs/specs/MandarinOS_Conversation_UX_Protocol_v1.md` | C | `docs/archive/specs/MandarinOS_Conversation_UX_Protocol_v1.md` | Low | 0 | 0 | 7 |
| `docs/specs/MandarinOS_Progress_Tracking_Cursor_Spec_v2.md` | C | `docs/archive/specs/MandarinOS_Progress_Tracking_Cursor_Spec_v2.md` | Low | 0 | 0 | 2 |
| `docs/specs/MandarinOS_Repair_Curiosity_Loop.md` | C | `docs/archive/specs/MandarinOS_Repair_Curiosity_Loop.md` | Low | 0 | 0 | 3 |
| `docs/specs/MandarinOS_capability_update_rules_v1.md` | C | `docs/archive/specs/MandarinOS_capability_update_rules_v1.md` | Low | 0 | 0 | 5 |
| `docs/specs/MandarinOS_conversation_capability_map_v1.md` | C | `docs/archive/specs/MandarinOS_conversation_capability_map_v1.md` | Low | 0 | 0 | 7 |
| `docs/specs/MandarinOS_conversation_memory_model_v2.md` | C | `docs/archive/specs/MandarinOS_conversation_memory_model_v2.md` | Low | 0 | 0 | 8 |
| `docs/specs/MandarinOS_conversation_system_blueprint_v1.md` | C | `docs/archive/specs/MandarinOS_conversation_system_blueprint_v1.md` | Low | 0 | 0 | 7 |
| `docs/specs/MandarinOS_marketing_positioning_v1.md` | C | `docs/archive/specs/MandarinOS_marketing_positioning_v1.md` | Low | 0 | 0 | 4 |
| `docs/specs/PHASE_10_6_ASR_STABILIZATION_MINI_SPEC.md` | C | `docs/archive/specs/PHASE_10_6_ASR_STABILIZATION_MINI_SPEC.md` | Low | 0 | 0 | 3 |
| `docs/specs/Progress_Scorecard_Alignment.md` | C | `docs/archive/specs/Progress_Scorecard_Alignment.md` | Low | 0 | 0 | 2 |
| `docs/specs/RELEASE_1_BOUNDARY.md` | C | `docs/archive/specs/RELEASE_1_BOUNDARY.md` | Low | 0 | 0 | 2 |
| `docs/specs/mandarinos_adjective_pack_v1.md` | C | `docs/archive/specs/mandarinos_adjective_pack_v1.md` | Low | 0 | 0 | 2 |
| `docs/specs/mandarinos_conversation_energy_model_v1.md` | C | `docs/archive/specs/mandarinos_conversation_energy_model_v1.md` | Low | 0 | 0 | 6 |
| `docs/specs/mandarinos_conversation_steering_engine_v1.md` | C | `docs/archive/specs/mandarinos_conversation_steering_engine_v1.md` | Low | 0 | 0 | 6 |
| `docs/specs/mandarinos_curiosity_engine_v1.md` | C | `docs/archive/specs/mandarinos_curiosity_engine_v1.md` | Low | 0 | 0 | 5 |
| `docs/specs/mandarinos_emergency_curiosity_pack_v1.md` | C | `docs/archive/specs/mandarinos_emergency_curiosity_pack_v1.md` | Low | 0 | 0 | 7 |
| `docs/specs/mandarinos_family_conversation_ladder_v2.md` | C | `docs/archive/specs/mandarinos_family_conversation_ladder_v2.md` | Low | 0 | 0 | 4 |
| `docs/specs/mandarinos_family_engine_v4.md` | C | `docs/archive/specs/mandarinos_family_engine_v4.md` | Low | 0 | 0 | 5 |
| `docs/specs/mandarinos_family_memory_rules_v1.md` | C | `docs/archive/specs/mandarinos_family_memory_rules_v1.md` | Low | 0 | 0 | 2 |
| `docs/specs/mandarinos_family_vocab_pack_p1.md` | C | `docs/archive/specs/mandarinos_family_vocab_pack_p1.md` | Low | 0 | 0 | 2 |
| `docs/specs/mandarinos_food_engine_v1.md` | C | `docs/archive/specs/mandarinos_food_engine_v1.md` | Low | 0 | 0 | 5 |
| `docs/specs/mandarinos_identity_engine_v4.md` | C | `docs/archive/specs/mandarinos_identity_engine_v4.md` | Low | 0 | 0 | 4 |
| `docs/specs/mandarinos_interests_engine_v1.md` | C | `docs/archive/specs/mandarinos_interests_engine_v1.md` | Low | 0 | 0 | 6 |
| `docs/specs/mandarinos_orientation_pack_v1.md` | C | `docs/archive/specs/mandarinos_orientation_pack_v1.md` | Low | 0 | 0 | 2 |
| `docs/specs/mandarinos_persona_network_relationship_pack_v1.md` | C | `docs/archive/specs/mandarinos_persona_network_relationship_pack_v1.md` | Low | 0 | 0 | 6 |
| `docs/specs/mandarinos_place_engine_v1.md` | C | `docs/archive/specs/mandarinos_place_engine_v1.md` | Low | 0 | 0 | 4 |
| `docs/specs/mandarinos_study_work_engine_v10.md` | C | `docs/archive/specs/mandarinos_study_work_engine_v10.md` | Low | 0 | 0 | 5 |
| `docs/specs/mandarinos_study_work_ladder.md` | C | `docs/archive/specs/mandarinos_study_work_ladder.md` | Low | 0 | 0 | 2 |
| `docs/specs/mandarinos_study_work_memory_rules.md` | C | `docs/archive/specs/mandarinos_study_work_memory_rules.md` | Low | 0 | 0 | 2 |
| `docs/specs/mandarinos_study_work_vocab_pack.md` | C | `docs/archive/specs/mandarinos_study_work_vocab_pack.md` | Low | 0 | 0 | 2 |
| `docs/specs/mandarinos_travel_engine_v4.md` | C | `docs/archive/specs/mandarinos_travel_engine_v4.md` | Low | 0 | 0 | 5 |

#### C2D3-review — historical specs with code-comment or AI_CONTEXT references (docs/specs/, class C) — 6 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` | C | `docs/archive/specs/CONVERSATION_ARCHITECTURE_INDEX.md` | Medium | 0 | 1 | 12 |
| `docs/specs/MandarinOS_conversation_ladders_full_draft_v2.md` | C | `docs/archive/specs/MandarinOS_conversation_ladders_full_draft_v2.md` | Medium | 1 | 0 | 7 |
| `docs/specs/MandarinOS_engine_specs_v1.md` | C | `docs/archive/specs/MandarinOS_engine_specs_v1.md` | Medium | 0 | 0 | 9 |
| `docs/specs/MandarinOS_next_question_selector_v1.md` | C | `docs/archive/specs/MandarinOS_next_question_selector_v1.md` | Medium | 0 | 0 | 12 |
| `docs/specs/MandarinOS_support_packs_v1.md` | C | `docs/archive/specs/MandarinOS_support_packs_v1.md` | Medium | 3 | 0 | 6 |
| `docs/specs/mandarinos_emergency_phrases_p1_p2_v2.md` | C | `docs/archive/specs/mandarinos_emergency_phrases_p1_p2_v2.md` | Medium | 3 | 0 | 5 |

#### C2D4 — historical project notes (docs/project/, class C) — 6 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/project/DIRECTIVE_PHASE_1_CARD_PANEL_STATE.md` | C | `docs/archive/project/DIRECTIVE_PHASE_1_CARD_PANEL_STATE.md` | Low | 0 | 0 | 3 |
| `docs/project/ENGINES_P1_P2_AND_SRS_REFERENCE.md` | C | `docs/archive/project/ENGINES_P1_P2_AND_SRS_REFERENCE.md` | Low | 0 | 0 | 3 |
| `docs/project/NEXT_QUESTION_SELECTOR_AND_LEVEL_TIE_IN.md` | C | `docs/archive/project/NEXT_QUESTION_SELECTOR_AND_LEVEL_TIE_IN.md` | Low | 0 | 0 | 3 |
| `docs/project/PROBE_QUESTIONS_RESPONSE_OPTIONS_NOTE.md` | C | `docs/archive/project/PROBE_QUESTIONS_RESPONSE_OPTIONS_NOTE.md` | Low | 0 | 0 | 2 |
| `docs/project/TEST_DIAGNOSTIC_P1_MANUAL.md` | C | `docs/archive/project/TEST_DIAGNOSTIC_P1_MANUAL.md` | Low | 0 | 0 | 4 |
| `docs/project/USER_TURN_AND_PERSONA_QUESTIONS_NOTE.md` | C | `docs/archive/project/USER_TURN_AND_PERSONA_QUESTIONS_NOTE.md` | Low | 0 | 0 | 2 |

#### C2E1 — briefing audits and dated evidence (docs/briefings/, class E) — 8 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/briefings/CONVERSATION_ARCHITECTURE_ASSESSMENT.md` | E | `docs/evidence/briefings/CONVERSATION_ARCHITECTURE_ASSESSMENT.md` | Low | 0 | 0 | 1 |
| `docs/briefings/PHASE10_STRATEGIST_REVIEW.md` | E | `docs/evidence/briefings/PHASE10_STRATEGIST_REVIEW.md` | Low | 0 | 0 | 1 |
| `docs/briefings/PHASE7_COMPLETION_REVIEW_AND_TEST.md` | E | `docs/evidence/briefings/PHASE7_COMPLETION_REVIEW_AND_TEST.md` | Medium | 0 | 1 | 2 |
| `docs/briefings/PHASE7_SCHEMA_DISCOVERIES.md` | E | `docs/evidence/briefings/PHASE7_SCHEMA_DISCOVERIES.md` | Low | 0 | 0 | 2 |
| `docs/briefings/UI_CONVERSATION_LOOP_ASSESSMENT.md` | E | `docs/evidence/briefings/UI_CONVERSATION_LOOP_ASSESSMENT.md` | Low | 0 | 0 | 2 |
| `docs/briefings/bridge_audit_apr2026.md` | E | `docs/evidence/briefings/bridge_audit_apr2026.md` | Low | 0 | 0 | 1 |
| `docs/briefings/engine_audit_apr2026.md` | E | `docs/evidence/briefings/engine_audit_apr2026.md` | Low | 0 | 0 | 1 |
| `docs/briefings/implementation_report_apr2026.md` | E | `docs/evidence/briefings/implementation_report_apr2026.md` | Low | 0 | 0 | 1 |

#### C2E2 — spec audits and dated evidence (docs/specs/, class E) — 4 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/specs/MANDARINOS_CONVERSATION_ARCHITECTURE_AUDIT_v1.md` | E | `docs/evidence/specs/MANDARINOS_CONVERSATION_ARCHITECTURE_AUDIT_v1.md` | Low | 0 | 0 | 2 |
| `docs/specs/MandarinOS_conversation_expansion_audit_v2.md` | E | `docs/evidence/specs/MandarinOS_conversation_expansion_audit_v2.md` | Low | 0 | 0 | 2 |
| `docs/specs/Translation_Surface_Consistency_Audit.md` | E | `docs/evidence/specs/Translation_Surface_Consistency_Audit.md` | Low | 0 | 0 | 1 |
| `docs/specs/mandarinos_conversation_architecture_audit_request_v2.txt` | E | `docs/evidence/specs/mandarinos_conversation_architecture_audit_request_v2.txt` | Low | 0 | 0 | 1 |

#### C2E3 — project status/commit evidence (docs/project/, class E) — 12 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/project/ARCHITECTURE_ALIGNMENT_OPTIONS_AND_GOLD.md` | E | `docs/evidence/project/ARCHITECTURE_ALIGNMENT_OPTIONS_AND_GOLD.md` | Low | 0 | 0 | 3 |
| `docs/project/AUDIT_OPTION_GENERATION.md` | E | `docs/evidence/project/AUDIT_OPTION_GENERATION.md` | Low | 0 | 0 | 3 |
| `docs/project/COMMIT_RECORD.md` | E | `docs/evidence/project/COMMIT_RECORD.md` | Low | 0 | 0 | 4 |
| `docs/project/COMMIT_SUMMARY.md` | E | `docs/evidence/project/COMMIT_SUMMARY.md` | Low | 0 | 0 | 5 |
| `docs/project/COMMIT_SUMMARY_v1.md` | E | `docs/evidence/project/COMMIT_SUMMARY_v1.md` | Low | 0 | 0 | 3 |
| `docs/project/CORE_TREASURE_BRIDGE_STATUS.md` | E | `docs/evidence/project/CORE_TREASURE_BRIDGE_STATUS.md` | Low | 0 | 0 | 2 |
| `docs/project/DIAGNOSTIC_P1_VALIDATION_RESULTS.md` | E | `docs/evidence/project/DIAGNOSTIC_P1_VALIDATION_RESULTS.md` | Low | 0 | 0 | 2 |
| `docs/project/EXECUTIVE_SUMMARY_v1.md` | E | `docs/evidence/project/EXECUTIVE_SUMMARY_v1.md` | Low | 0 | 0 | 2 |
| `docs/project/OPTION_GENERATION_FIX_COMPLETE.md` | E | `docs/evidence/project/OPTION_GENERATION_FIX_COMPLETE.md` | Low | 0 | 0 | 3 |
| `docs/project/PHASE9_STATUS_AND_RESPONSE_QUALITY.md` | E | `docs/evidence/project/PHASE9_STATUS_AND_RESPONSE_QUALITY.md` | Low | 0 | 0 | 2 |
| `docs/project/SPECS_TO_IMPLEMENTATION_GAP.md` | E | `docs/evidence/project/SPECS_TO_IMPLEMENTATION_GAP.md` | Low | 0 | 0 | 2 |
| `docs/project/TEST_SUMMARY.md` | E | `docs/evidence/project/TEST_SUMMARY.md` | Low | 0 | 0 | 3 |

#### C2E4 — reports-directory evidence (docs/reports/, class E) — 10 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/reports/CORPUS_RECOVERY_NOTES.md` | E | `docs/evidence/reports/CORPUS_RECOVERY_NOTES.md` | Medium | 0 | 1 | 1 |
| `docs/reports/PHASE_11_1_1_OBSERVATION_REPORT.md` | E | `docs/evidence/reports/PHASE_11_1_1_OBSERVATION_REPORT.md` | Low | 0 | 0 | 1 |
| `docs/reports/alpha_conversation_observation.md` | E | `docs/evidence/reports/alpha_conversation_observation.md` | Medium | 1 | 0 | 1 |
| `docs/reports/capability_mismatch_observation.md` | E | `docs/evidence/reports/capability_mismatch_observation.md` | Medium | 1 | 0 | 1 |
| `docs/reports/component_gloss_coverage.md` | E | `docs/evidence/reports/component_gloss_coverage.md` | Medium | 1 | 1 | 2 |
| `docs/reports/counter_reply_matrix_report.md` | E | `docs/evidence/reports/counter_reply_matrix_report.md` | Medium | 1 | 0 | 2 |
| `docs/reports/move_type_tagging_audit.md` | E | `docs/evidence/reports/move_type_tagging_audit.md` | Medium | 1 | 0 | 2 |
| `docs/reports/move_type_tagging_coverage.md` | E | `docs/evidence/reports/move_type_tagging_coverage.md` | Medium | 1 | 0 | 1 |
| `docs/reports/move_type_transition_calibration.md` | E | `docs/evidence/reports/move_type_transition_calibration.md` | Medium | 1 | 0 | 1 |
| `docs/reports/vocab_character_coverage_audit.md` | E | `docs/evidence/reports/vocab_character_coverage_audit.md` | Medium | 1 | 1 | 1 |

#### C2E5 — remaining dated evidence (docs/state/, session-intelligence report, class E) — 2 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/session_intelligence_implementation_report.md` | E | `docs/evidence/session_intelligence_implementation_report.md` | Low | 0 | 0 | 3 |
| `docs/state/MANDARINOS_SYSTEM_STATE_PHASE_12B.md` | E | `docs/evidence/state/MANDARINOS_SYSTEM_STATE_PHASE_12B.md` | Low | 0 | 0 | 1 |

#### C2F — root-level generated captures (class G) — 6 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `fo_check.txt` | G | `generated/captures/fo_check.txt` | Low | 0 | 0 | 2 |
| `frame_dump.txt` | G | `generated/captures/frame_dump.txt` | Low | 0 | 0 | 2 |
| `frame_texts.txt` | G | `generated/captures/frame_texts.txt` | Low | 0 | 0 | 2 |
| `server_err.txt` | G | `generated/captures/server_err.txt` | Low | 0 | 0 | 2 |
| `server_out.txt` | G | `generated/captures/server_out.txt` | Low | 0 | 0 | 2 |
| `server_startup_err.txt` | G | `generated/captures/server_startup_err.txt` | Low | 0 | 0 | 2 |

#### C2G-core — proposals and unimplemented specifications, low-risk core (class F) — 14 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/REPO_STRUCTURE_PROPOSAL.md` | F | `docs/proposals/REPO_STRUCTURE_PROPOSAL.md` | Low | 0 | 0 | 3 |
| `docs/SCHEMA_SYNC_RECOMMENDATION.md` | F | `docs/proposals/SCHEMA_SYNC_RECOMMENDATION.md` | Low | 0 | 0 | 3 |
| `docs/design/SCENARIOS_REQUIRED_v1.md` | F | `docs/proposals/SCENARIOS_REQUIRED_v1.md` | Low | 0 | 0 | 7 |
| `docs/phases/PHASE9_CONTENT_AND_ENGINES_PLAN.md` | F | `docs/proposals/PHASE9_CONTENT_AND_ENGINES_PLAN.md` | Low | 0 | 0 | 1 |
| `docs/phases/PHASE_10_5_MAPPING_AND_SCHEMA_PROPOSAL.md` | F | `docs/proposals/PHASE_10_5_MAPPING_AND_SCHEMA_PROPOSAL.md` | Low | 0 | 0 | 1 |
| `docs/project/MandarinOS_project_plan_v2_CORRECTED.md` | F | `docs/proposals/MandarinOS_project_plan_v2_CORRECTED.md` | Low | 0 | 0 | 1 |
| `docs/project/MandarinOS_project_plan_v2_UPDATED.md` | F | `docs/proposals/MandarinOS_project_plan_v2_UPDATED.md` | Low | 0 | 0 | 1 |
| `docs/project/RECOVERY_AND_CONVERSATION_FUTURE_NOTES.md` | F | `docs/proposals/RECOVERY_AND_CONVERSATION_FUTURE_NOTES.md` | Low | 0 | 0 | 1 |
| `docs/specs/MOBILE_WORD_INSIGHT_UI_SPEC.md` | F | `docs/proposals/MOBILE_WORD_INSIGHT_UI_SPEC.md` | Low | 0 | 0 | 1 |
| `docs/specs/MandarinOS_Hybrid_Speech_and_Persona_Voice_Architecture.md` | F | `docs/proposals/MandarinOS_Hybrid_Speech_and_Persona_Voice_Architecture.md` | Low | 0 | 0 | 1 |
| `docs/specs/PHASE_10_5_INTEREST_RESPONSIVENESS_REFINEMENT_PLAN.md` | F | `docs/proposals/PHASE_10_5_INTEREST_RESPONSIVENESS_REFINEMENT_PLAN.md` | Low | 0 | 0 | 2 |
| `docs/specs/PHASE_12C_IMPLEMENTATION_BRIEF.md` | F | `docs/proposals/PHASE_12C_IMPLEMENTATION_BRIEF.md` | Low | 0 | 0 | 1 |
| `docs/specs/PHASE_12C_INVARIANTS.md` | F | `docs/proposals/PHASE_12C_INVARIANTS.md` | Low | 0 | 0 | 1 |
| `docs/specs/TRANSCRIPT_REPLAY_TRANSLATION_UI_SPEC.md` | F | `docs/proposals/TRANSCRIPT_REPLAY_TRANSLATION_UI_SPEC.md` | Low | 0 | 0 | 2 |

#### C2G-review — proposals with code-comment or AI_CONTEXT references (class F) — 8 files

| Current path | Class | Proposed path | Risk | Op refs | AI/bootstrap refs | Doc refs |
| ------------ | ----- | -------------- | ---- | ------- | ------------------ | -------- |
| `docs/design/MANDARINOS_PHASE_12_HYBRID_AI_CONCEPT_BRIEFING.txt` | F | `docs/proposals/MANDARINOS_PHASE_12_HYBRID_AI_CONCEPT_BRIEFING.txt` | Medium | 0 | 1 | 1 |
| `docs/phases/PHASE10_TECHNICAL_PROPOSAL.md` | F | `docs/proposals/PHASE10_TECHNICAL_PROPOSAL.md` | Medium | 3 | 0 | 2 |
| `docs/plans/PHASE_10_7_MINIMAL_IMPLEMENTATION_PLAN.md` | F | `docs/proposals/PHASE_10_7_MINIMAL_IMPLEMENTATION_PLAN.md` | Medium | 0 | 1 | 1 |
| `docs/plans/component_radical_gloss_plan.md` | F | `docs/proposals/component_radical_gloss_plan.md` | Medium | 0 | 1 | 1 |
| `docs/plans/learner_etymology_hints_plan.md` | F | `docs/proposals/learner_etymology_hints_plan.md` | Medium | 0 | 1 | 2 |
| `docs/project/MandarinOS_project_plan_v2.md` | F | `docs/proposals/MandarinOS_project_plan_v2.md` | Medium | 0 | 1 | 5 |
| `docs/session_intelligence_architecture.md` | F | `docs/proposals/session_intelligence_architecture.md` | Medium | 5 | 0 | 4 |
| `docs/specs/PHASE_10_5_BEHAVIOUR_IMPLEMENTATION_PLAN.md` | F | `docs/proposals/PHASE_10_5_BEHAVIOUR_IMPLEMENTATION_PLAN.md` | Medium | 1 | 0 | 2 |

The "documents assessed but recommended to remain in place" table is in §13.

## 18. Proposed Phase C2 batches

17 batches plus a closeout step. Every batch's exact source/destination paths are in §17; this table adds rationale, dependency counts, required changes, compatibility treatment, model, approval, and rollback.

| Batch | Files | Rationale | Dependency profile | Required link/comment updates | Redirect/compatibility treatment | Recommended model | Approval requirement | Rollback |
| ----- | ----- | --------- | -------------------- | -------------------------------- | ----------------------------------- | -------------------- | ---------------------- | -------- |
| **C2A** | 17 | Historical directives family, already governed by an approved B5B README | 4 Medium (comment mentions in `conformance/run_conformance.py`, `tools/coverage/coverage_scan.py`, `tests/test_hint_cascade.py`, `tests/test_scaffolding_transitions_v1.py`) | Update 4 comment references; verify README-family cross-links | `docs/directives/README.md` stays in place, unchanged path | Composer 2.5 | Separate reviewed directive | `git mv` is reversible; revert commit restores paths |
| **C2B** | 11 | Historical phase family, already governed by an approved B5B README | 1 Medium (`AI_CONTEXT.md` "read-first" citation) | Correct `AI_CONTEXT.md` §11 line in same or preceding batch | `docs/phases/README.md` stays in place | Composer 2.5 | Separate reviewed directive | Same as above |
| **C2C-core** | 20 | Low-risk majority of historical briefings | All Low | Historical cross-links only (mechanical) | None beyond existing family posture | Auto (once approved; purely mechanical) | Separate reviewed directive | Same as above |
| **C2C-review** | 8 | Briefings `AI_CONTEXT.md` calls "mandatory" (§9) | All Medium (AI-bootstrap) | Requires an `AI_CONTEXT.md` §11/"Extensibility strategy"/"Phase alignment" wording correction first | None beyond existing family posture | Sonnet diagnosis first (to draft the `AI_CONTEXT.md` correction), then Composer 2.5 to execute | Separate reviewed directive, sequenced after the `AI_CONTEXT.md` correction | Same as above |
| **C2D1** | 6 | Design-history extraction from the mixed `docs/design/` directory | 2 Medium (AI-bootstrap: `TRACE_CONTRACT_v1.md`, `MandarinOS Developer Handoff.txt`) | Update `AI_CONTEXT.md` §11 trace-contract citation | None | Sonnet diagnosis first (mixed-directory judgment already made here; execution needs care not to touch the 3 remaining class-B design files) | Separate reviewed directive | Same as above |
| **C2D2** | 10 | All class-D superseded documents, cross-directory | 2 Medium (AI-bootstrap: `CURSOR_STARTUP_PROTOCOL.md`, `MANDARINOS_PROJECT_PLAN_v1.md` — both already flagged in the index's own §18 conflict list) | Update the 2 `AI_CONTEXT.md` citations; this is the highest-value correction in the whole programme since it resolves an already-documented conflict | None | Sonnet diagnosis first, then Composer 2.5 | Separate reviewed directive | Same as above |
| **C2D3-core** | 32 | Low-risk majority of historical specs, the largest single low-risk batch | All Low | Historical cross-links only | None | Auto (mechanical; batch exceeds 20 but is uniformly low-risk per the directive's exception) | Separate reviewed directive | Same as above |
| **C2D3-review** | 6 | Historical specs with a code-comment or AI-bootstrap reference | All Medium | Update `ui_server.py` comment (1 file), verify remaining comment mentions | None | Composer 2.5 | Separate reviewed directive | Same as above |
| **C2D4** | 6 | Historical project notes | All Low | Historical cross-links only | None | Auto | Separate reviewed directive | Same as above |
| **C2E1** | 8 | Briefing-directory dated evidence, split from the C2C historical briefings | 1 Medium (AI-bootstrap) | Update 1 `AI_CONTEXT.md` citation (`PHASE7_COMPLETION_REVIEW_AND_TEST.md`, mobile/LAN-testing pointer) | None | Composer 2.5 | Separate reviewed directive | Same as above |
| **C2E2** | 4 | Spec-directory dated evidence | All Low | None | None | Auto | Separate reviewed directive | Same as above |
| **C2E3** | 12 | Project-directory dated evidence | All Low | None | None | Auto | Separate reviewed directive | Same as above |
| **C2E4** | 10 | Reports-directory dated evidence, each produced by a matching `scripts/audit_*.py`/`scripts/*.py` | 6 Medium (single code-comment "writes docs/reports/X.md" line each) | Update the 6-10 producing-script docstring/comment lines in the same batch | None | Composer 2.5 (needs to touch both the doc move and the matching script comment together) | Separate reviewed directive | Same as above |
| **C2E5** | 2 | Remaining dated evidence (state snapshot, session-intelligence report) | All Low | None | None | Auto | Separate reviewed directive | Same as above |
| **C2F** | 6 | Root-level generated/captured debug dumps with zero dependency | All Low | None | None | Auto | Separate reviewed directive | Same as above |
| **C2G-core** | 14 | Low-risk majority of class-F proposals | All Low | None | None | Auto | Separate reviewed directive | Same as above |
| **C2G-review** | 8 | Proposals with a code-comment or `AI_CONTEXT.md` reference | All Medium | Update `AI_CONTEXT.md` §11a/§12 pointers and the 5 producing-script "Authoritative:"/"Architecture reference:" comments | None | Composer 2.5 (semantic: must verify each pointer still makes sense after the move) | Separate reviewed directive | Same as above |
| **C2 closeout** | 0 (verification only) | Final reconciliation once all prior batches are approved and merged: re-run the §17/§18 count-verification scripts, confirm no destination collision, confirm inventory total still reconciles, update `docs/DOCUMENT_AUTHORITY_INDEX.md` with final paths | — | — | Retire the `docs/directives/README.md`/`docs/phases/README.md`/`docs/briefings/`-family redirect wording once every member has moved, if still appropriate | Sonnet diagnosis first (final reconciliation judgment), Auto for the verification scripts | Separate reviewed directive; requires Phase C2A–C2G-review all approved | Each batch's rollback remains independent |

**Phase C2 implementation status** (execution record; approved move plan unchanged):

| Batch | Implementation status | Verified deviations |
| ----- | ---------------------- | ------------------- |
| **C2A** | Approved and implemented — 2026-07-14 | Four module-docstring filename mentions in `conformance/run_conformance.py`, `tools/coverage/coverage_scan.py`, `tests/test_hint_cascade.py`, and `tests/test_scaffolding_transitions_v1.py` preserved as historical, non-operational provenance notes (filename only; no path construction, file open, or assertion). C2A scope excluded application code and tests. |
| **C2B** | Approved and implemented — 2026-07-14 | `AI_CONTEXT.md` §1.2 and §11 updated: removed mandatory read-first citation of `PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`; replaced with `docs/phases/README.md` and archive pointer. Historical references in dated briefings, Phase B5 scope records, class-F proposals, and `MANDARINOS_SYSTEM_MAP.md` preserved. |
| **C2C-core** | Approved and implemented — 2026-07-14 | Twenty byte-identical Low-risk class-C briefings relocated; no compatibility README; no AI/bootstrap changes (deferred to C2C-review). Eight C2C-review class-C briefings and eight class-E evidence files remain in `docs/briefings/`. Historical cross-links preserved. Implementation-model deviation: Composer 2.5 used where Auto was approved. No scope, content, authority, or repository-integrity impact found; higher-cost model use only. |
| **C2C-review** | Approved and implemented — 2026-07-15 | Sonnet diagnosis (2026-07-15): all eight briefings confirmed historical class-C narrative (`docs/DOCUMENT_AUTHORITY_INDEX.md` §17.4/§13.1, "historical context ... does not authorise changes"); no active AI workflow, code, or test reads any of the eight files (zero operational dependencies located by repo-wide code search); the substantive 12C/12C.1/12D layering framework and the extensibility decision-priority rules are already restated in `AI_CONTEXT.md`'s own class-B prose, so removing mandatory/read-first treatment of the eight briefings loses no necessary startup instruction. `AI_CONTEXT.md` corrected in four bounded spots: §5.0 "Strategist handoffs" paragraph (7 of 8 paths repointed to archive, framed as historical background), §11 "Read-first" list (3 mandatory bullets removed, `Cursor_Directive...` bullet repointed to its canonical `docs/specs/` copy), §"Extensibility strategy" (authority-reversal correction: `docs/specs/` copy is now stated as canonical, archived `docs/briefings/`→`docs/archive/briefings/` copy stated as optional non-authoritative duplicate), §"Phase alignment" and the Current-phase-status table (3 bullets/cells demoted from mandatory citation to "historical background" pointer at the archive path, framework prose retained verbatim). One invalidated active link repaired in `docs/DEVELOPER_ONBOARDING.md` §10 Documentation Index. Eight byte-identical Medium-risk class-C briefings relocated via `git mv`; classes and flags unchanged; no reclassification. Class-E evidence and all 20 C2C-core files untouched. Implementation model used: Composer 2.5 (orchestration and edits), matching the approved "Sonnet diagnosis first → Composer 2.5" allocation; no Opus escalation required (no unresolved architecture/runtime conflict found). Approval-pass review (2026-07-15, Sonnet): confirmed all eight briefings genuinely historical, `AI_CONTEXT.md` edits correctly bounded, canonical extensibility directive correctly identified at `docs/specs/`, `docs/DEVELOPER_ONBOARDING.md` change bounded to one row, no active AI/bootstrap dependency remains on an old path, no archived material promoted into a new authority list. Rollback: `git revert` the candidate and approval commits, or restore the eight files via `git mv` back to `docs/briefings/` and revert the four governance-file edits; all moves are 100% renames so history is preserved either way. |
| **C2D3-core** | Candidate implemented — pending review and approval | Reconciliation (2026-07-15): the approved audit table lists exactly 32 files (all Low risk, historical cross-links only, zero operational or AI/bootstrap references); the six-file C2D3-review population (`CONVERSATION_ARCHITECTURE_INDEX.md` plus five specifications with a code-comment or AI-bootstrap reference) is disjoint from the 32 and was left untouched; three current class-B specifications (`Cursor_Directive_MandarinOS_Extensibility_Strategy.md`, `MANDARINOS_CONVERSATION_FLOW_DESIGN.md`, `MandarinOS_Extensibility_Strategy.md`) confirmed unmoved and unaffected; the audit table and authority index agree on class (all C), flags, and current-authority field for every one of the 32 sources (no disagreement found). Zero operational code/test/CI dependencies (repo-wide search of `*.py`, `*.js`, `*.json`, `*.yml`, `*.yaml`, `*.sh`, `*.ps1` found none). Dependency search found 20 documentation files with plain-text or historical mentions of the 32 filenames (Phase B/C1 historical records, dated evidence, archived briefings, project notes); of these, two required a bounded active-reference correction because they are current navigation/authority documents, not historical records: `docs/DEVELOPER_ONBOARDING.md` §10 Documentation Index repointed its `Live_Beginner_Ability_Model.md` row to the archive path with an added historical-background label; `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md` (class B, current authority) §8 "Related documents" repointed its `MandarinOS_Repair_Curiosity_Loop.md` row to the archive path with an added historical label — both corrections bounded to the single affected table row, no other content changed, and neither file's other rows (including references to C2D3-review-deferred files) were touched. `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` (class C, live navigation index, itself deferred to C2D3-review) contained 18 relative Markdown links (`./filename.md`) to files among the 32 that would have broken on relocation — bounded administrative path corrections to `../archive/specs/filename.md` for all 18, verified against the full 32-file set with no over- or under-correction (the remaining links to the 5 C2D3-review specifications and 1 non-batch class-E audit file were left as `./filename.md`, correctly deferred); status notice and all other index content preserved byte-identically. No compatibility redirect stub created: no operational dependency and the two active citations were corrected at their source. Thirty-two 100% renames to `docs/archive/specs/`; all 32 destination blobs verified byte-identical to baseline `34e1372d49f5cc7fa8bd9293e89f8f604c1eb504`; the one pre-existing notice (`MandarinOS_capability_update_rules_v1.md`, class D flags `misleading-filename, status-header-added`) verified byte-identical, and its sibling C2D3-review file `MandarinOS_next_question_selector_v1.md` (also notice-bearing) confirmed untouched at `docs/specs/`. Implementation model: Auto (approved model: mechanical, uniformly Low-risk batch per the directive's batch-size exception), with Sonnet used for the population-reconciliation and reference-classification diagnosis described above; no Composer or Opus escalation required (no unresolved architecture/runtime conflict found). Rollback: `git revert` the candidate commit, or reverse the 32 `git mv` operations back to `docs/specs/` and revert the `docs/DEVELOPER_ONBOARDING.md`, `docs/specs/MANDARINOS_CONVERSATION_FLOW_DESIGN.md`, and `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` edits; all moves are 100% renames so history is preserved either way. |
| **C2D2** | Approved and implemented — 2026-07-15 | Sonnet diagnosis (2026-07-15, candidate pass): all ten sources confirmed class-D superseded documents; audit table and authority index agree on class, flags, and current-authority field for every source (no disagreement found). Zero operational code/test/CI dependencies (repo-wide search of `*.py`, `*.js`, `*.json`, `*.yml`, `*.yaml`, `*.sh`, `*.ps1` found none). Two AI-bootstrap citations found in `AI_CONTEXT.md`, matching the audit's predicted 2 Medium-risk files exactly: (1) "See docs/project/MANDARINOS_PROJECT_PLAN_v1.md for the current development roadmap" incorrectly asserted the superseded v1 plan as current, directly contradicted by the file's own later "Project Plan" section (already correctly stating v2 supersedes v1) — corrected to point to that existing section plus an explicit archive-path/class-D note; (2) "Cursor must read docs/design/CURSOR_STARTUP_PROTOCOL.md before performing any analysis or code changes" was the mandatory-onboarding conflict already flagged in the authority index's own §18 conflict list ("onboarding order superseded by docs/ARCHITECTURE.md §21") — corrected to point to the current onboarding sequence (`docs/ARCHITECTURE.md` §21, `docs/DOCUMENT_AUTHORITY_INDEX.md` §13), archive path retained as optional non-authoritative historical context. No `.cursor/rules/*`, `.github/copilot-instructions.md`, `docs/DEVELOPER_ONBOARDING.md`, or `MANDARINOS_SYSTEM_MAP.md` references to any of the 10 sources were found. Additionally found and repaired: `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` (class C, live navigation index in the same directory as 8 of the 10 sources) contained 8 relative Markdown links (`./filename.md`) that would have broken on relocation — bounded administrative path corrections to `../archive/superseded/filename.md` for all eight, status notice and all other index content preserved byte-identically; this is the same treatment pattern approved for `SCENARIOS_REQUIRED_v1.md` in C2D1. Remaining old-path mentions (Phase B1/B2/C1 historical records, dated project-gap-analysis and repo-structure-proposal documents, archived briefings) are non-clickable historical text outside the changed-file scope and were left unchanged. No compatibility redirect stub created: no operational dependency and the two active citations were corrected at their source. Ten 100% renames to `docs/archive/superseded/` from three source directories. Implementation model: Composer 2.5 after Sonnet diagnosis (approved model: "Sonnet diagnosis first → Composer 2.5"). Approval-pass review (2026-07-15, Sonnet): reconciled the approved 10-file cross-directory table against the audit and confirmed it exactly matches the candidate's changed-file scope (10 renames, 4 modified files); verified all 10 destination blobs byte-identical to baseline `de9758b442cde24c39e5ce5c9262017a6692260c` with all 10 class-D notices (single BEGIN/END sentinel pair each) byte-identical; verified all 10 replacement/current-authority fields cite existing class-A documents (`docs/ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, `docs/CONVERSATION_ARCHITECTURE.md`, `docs/ANSWER_SOURCE_CONTRACT.md`, `docs/CHANGE_CHECKLIST.md`) or `AI_CONTEXT.md` (class B, itself subordinate to the R2 package), with named `_v2` successors correctly identified as historical/proposal rather than authority; confirmed the `AI_CONTEXT.md` roadmap and startup-protocol corrections are bounded to the two affected sentences, preserve the file's status notice, and lose no necessary current guidance (the current onboarding sequence in `docs/ARCHITECTURE.md` §21 and this index's §13 fully replaces the superseded protocol's substantive safeguards); confirmed the eight `CONVERSATION_ARCHITECTURE_INDEX.md` link repairs are purely administrative path corrections with no label, role, or authority-language changes, and its status notice, class, and flags remain byte-identical; confirmed zero remaining active operational, bootstrap, onboarding, or navigation dependency on any of the 10 old paths (all remaining occurrences are Phase B1/B2/C1 historical records, dated evidence, or archived briefing narrative). Rollback: `git revert` the candidate and approval commits, or reverse the ten `git mv` operations plus revert the `AI_CONTEXT.md` and `CONVERSATION_ARCHITECTURE_INDEX.md` edits; all moves are 100% renames so history is preserved either way. |
| **C2D1** | Approved and implemented — 2026-07-15 | Sonnet diagnosis (2026-07-15, candidate pass): all six sources confirmed class-C historical early-design material; three class-B design-governance files (`mandarinos_design_constitution.txt`, `MANDARINOS_AI_GOVERNANCE_MODEL_v1.md`, `LICENSE.md`) remain in place; class-D `CURSOR_STARTUP_PROTOCOL.md` and two class-F proposals deferred. Authority-overlap: `TRACE_CONTRACT_v1.md` title sounds current but Phase B5A notice and index already class it C with authority `docs/ARCHITECTURE.md`; `MandarinOS Developer Handoff.txt` was incorrectly labelled "authoritative" in `.github/copilot-instructions.md`. Zero operational code/test/CI dependencies. Active corrections: `AI_CONTEXT.md` §1.2/§11 (remove always-consult/read-first TRACE_CONTRACT; archive path optional historical only); `.github/copilot-instructions.md` (Handoff demoted; point to `docs/DEVELOPER_ONBOARDING.md`); `integration_kit/README.md` (TRACE path to archive). Six 100% renames to `docs/archive/design-history/`; all six blobs verified byte-identical to baseline `26aa0d72acd5b5313378d35c1312c83bddd4cdd0`; `TRACE_CONTRACT_v1.md` Phase B5A notice sentinels (exactly one BEGIN/END pair) verified byte-identical. Approval-pass Sonnet diagnosis (2026-07-15) resolved the three deferred TRACE-reference questions: (1) `MANDARINOS_SYSTEM_MAP.md` §2.5 "Trace = contracted signals" and §9 "Read-first references (authoritative)" both cited `docs/design/TRACE_CONTRACT_v1.md` as an active/mandatory current reference in a class-B document — classified as live navigational/authority citations requiring repair; both redirected to current authority `docs/ARCHITECTURE.md` and the applicable R2 contract, with the archive path retained only as explicitly non-authoritative class-C historical background; no other system-map content changed, and the file's own pre-existing unrelated stale `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` reference was left untouched as out of C2D1 scope. (2) `docs/design/MANDARINOS_AI_GOVERNANCE_MODEL_v1.md` §3 "Non-Negotiable Authority" listed `docs/design/TRACE_CONTRACT_v1.md` under "documents [that] override AI decisions" — classified as an incorrect current-authority statement requiring repair; redirected to `docs/ARCHITECTURE.md` and the applicable R2 trace/state contract, with the archive path retained as optional non-authoritative historical background; no other governance-model content changed, and the file's unrelated Phase Architecture Locks subsection was left untouched. (3) `docs/design/SCENARIOS_REQUIRED_v1.md` §"References" contained a live Markdown link `[TurnState Trace Contract v1](./TRACE_CONTRACT_v1.md)` — classified as a live navigational link whose target remains relevant historical context, so an administrative path-only correction was made to `../archive/design-history/TRACE_CONTRACT_v1.md`; the Phase B3B status notice and all other proposal text were preserved byte-identically; this bounded path correction does not alter the file's deferred class-F relocation status. All three diagnosed files' status notices verified byte-identical before and after. Repo-wide old-path search after all corrections found no remaining active/unexplained broken current link; remaining occurrences are Phase B5/C1 historical records, the approved source-to-destination map (§12 above, unaltered), and historical mentions in unrelated dated/archived documents outside the C2D1 changed-file scope (`docs/SCHEMA_SYNC_RECOMMENDATION.md`, `docs/phases/PHASE10_TECHNICAL_PROPOSAL.md`, `docs/REPO_STRUCTURE_PROPOSAL.md`, `docs/project/*`, `docs/archive/*`), all left unchanged. Deferred population verified unmoved: `CURSOR_STARTUP_PROTOCOL.md` (C2D2), `SCENARIOS_REQUIRED_v1.md` and `MANDARINOS_PHASE_12_HYBRID_AI_CONCEPT_BRIEFING.txt` (class-F later batch), plus the non-inventory `MandarinOS Developer Handoff.rtf` and `MANDARINOS_ARCHITECTURE_MAP.png`. Compatibility treatment: none (per approved plan). Implementation: Composer 2.5 after Sonnet diagnosis (approved model) for both the candidate and approval passes. Rollback: `git revert` the candidate and approval commits, or reverse the six `git mv` operations back to `docs/design/` and revert the bootstrap and three reference-repair edits; all moves are 100% renames so history is preserved either way. |

**On batch-size exceptions:** C2C-core (20) is at the limit; C2D3-core (32) exceeds the ~20 guideline but is uniformly Low-risk and mechanically identical (a `git mv` plus a handful of historical cross-link updates, no AI-bootstrap or code-comment correction required for any of its 32 members) — this matches the directive's explicit exception for batches where "all dependencies are low risk and mechanically identical." No other batch exceeds 20.

**Ordering:** the directive's suggested C2A–C2G sequence is followed at the family level, refined into 17 sub-batches by evidence (§9, §12) rather than forced into exactly 7 groups, because 3 of the suggested families (briefings, specs, proposals) contain a materially different risk profile within the family that the evidence does not support merging.

**Batch reconciliation table** (verified at approval; source and destination totals are equal per batch):

| Batch | File count | Risk mix | Dependency profile | Model | Source total | Destination total |
| ----- | ---------: | -------- | ------------------ | ----- | -----------: | ----------------: |
| C2A | 17 | 13 Low, 4 Medium | 4 code-comment mentions | Composer 2.5 | 17 | 17 |
| C2B | 11 | 10 Low, 1 Medium | 1 AI/bootstrap citation | Composer 2.5 | 11 | 11 |
| C2C-core | 20 | All Low | Historical cross-links only | Auto | 20 | 20 |
| C2C-review | 8 | All Medium | AI/bootstrap citations | Sonnet diagnosis first → Composer 2.5 | 8 | 8 |
| C2D1 | 6 | 4 Low, 2 Medium | 2 AI/bootstrap citations | Sonnet diagnosis first → Composer 2.5 | 6 | 6 |
| C2D2 | 10 | 8 Low, 2 Medium | 2 AI/bootstrap citations | Sonnet diagnosis first → Composer 2.5 | 10 | 10 |
| C2D3-core | 32 | All Low | Historical cross-links only | Auto | 32 | 32 |
| C2D3-review | 6 | All Medium | Code-comment and AI/bootstrap | Composer 2.5 | 6 | 6 |
| C2D4 | 6 | All Low | Historical cross-links only | Auto | 6 | 6 |
| C2E1 | 8 | 7 Low, 1 Medium | 1 AI/bootstrap citation | Composer 2.5 | 8 | 8 |
| C2E2 | 4 | All Low | None | Auto | 4 | 4 |
| C2E3 | 12 | All Low | None | Auto | 12 | 12 |
| C2E4 | 10 | 4 Low, 6 Medium | 6 code-comment mentions | Composer 2.5 | 10 | 10 |
| C2E5 | 2 | All Low | None | Auto | 2 | 2 |
| C2F | 6 | All Low | None | Auto | 6 | 6 |
| C2G-core | 14 | All Low | None | Auto | 14 | 14 |
| C2G-review | 8 | All Medium | Code-comment and AI/bootstrap | Composer 2.5 | 8 | 8 |
| **Total relocation programme** | **180** | **139 Low, 41 Medium, 0 High** | — | — | **180** | **180** |
| C2 closeout | 0 | — | Verification only | Sonnet closeout review | 0 | 0 |

## 19. Model and cost recommendations

Applied per §12 of the directive and reconciled against the per-batch "Recommended model" column of §18 at approval. The candidate completion report's executive model summary contained a **15-file arithmetic gap** (`92 + 41 + 32 = 165` vs the correct `180`). Cause, determined from the exact per-batch source lists in §18:

1. **Composer file total understated by 11** — the stated total of 41 files counted only C2A (17), C2D3-review (6), C2E1 (8), and C2E4 (10), omitting **C2B (11 files)** even though C2B was named in the batch list.
2. **Auto file total understated by 4** — the stated total of 92 files was a summation error across the eight Auto batches; the correct sum is **96** (20+32+6+4+12+2+6+14).
3. **C2G-review miscategorised in the executive summary** — the completion report assigned C2G-review (8 files) to the Sonnet category, but §18's per-batch table assigns it to **Composer 2.5** because the required work is semantic pointer verification after move, not drafting a new `AI_CONTEXT.md` correction. This miscategorisation did not change the relocation total but inflated the Sonnet file count by 8 and deflated the Composer file count by 8.

Corrected model allocation (verified at approval):

| Model recommendation | Relocation batches | Files |
| -------------------- | -----------------: | ----: |
| Auto | 8 | 96 |
| Composer 2.5 | 6 | 60 |
| Sonnet diagnosis first → Composer 2.5 | 3 | 24 |
| **Total relocation programme** | **17** | **180** |
| Sonnet closeout review | 1 closeout | 0 moved files |

Per-batch assignment:

* **Auto** — C2C-core, C2D3-core, C2D4, C2E2, C2E3, C2E5, C2F, C2G-core (8 batches, 96 files): exact moves are uniform, dependencies are simple historical cross-links only, no mixed-authority judgment remains once this audit's classification is approved.
* **Composer 2.5** — C2A, C2B, C2D3-review, C2E1, C2E4, C2G-review (6 batches, 60 files): multiple files and comment/link updates must be changed together, and body preservation must be verified across the move.
* **Sonnet diagnosis first, then Composer 2.5 to execute** — C2C-review, C2D1, C2D2 (3 batches, 24 files): each requires drafting the specific `AI_CONTEXT.md` wording correction (which sentence to remove/replace, and what it should point to instead) before a mechanical move is safe, because these are the batches where AI-bootstrap behaviour could visibly change for an AI assistant reading `AI_CONTEXT.md` after the move.
* **Sonnet diagnosis first (closeout judgment)** — C2 closeout: final reconciliation and the decision on whether to retire any family-README redirect wording.
* **Opus** — not recommended for any batch. No batch involves an unresolved architecture or runtime-dependency conflict; the two genuine hard dependencies (§8.1) are excluded from all batches rather than requiring Opus-level resolution.

## 20. Explicit exclusions

This phase explicitly did **not**:

* move, rename, or delete any file (`git mv`, `git rm`, or otherwise);
* create any archive, evidence, proposals, or generated-captures directory;
* create any redirect stub;
* update any internal link or code comment;
* rewrite any historical document body;
* alter, add, or remove any status notice or generated-output header;
* change any primary classification or existing secondary flag on any of the 230 pre-existing rows;
* change any code, test, CI, configuration, Cursor rule, or AI startup file;
* authorise any Phase C2 batch for execution — every batch in §18 requires a separate reviewed directive before any `git mv` is issued.

## 21. Verification results

Verification was performed with temporary scripts (`_c1_extract.py`, `_c1_deps.py`, `_c1_relocation_synth.py`, `_c1_gen_tables.py`, and their intermediate `.tsv`/`.md` outputs), all deleted before the candidate commit. Results:

1. Exactly two tracked files are changed by this candidate: `docs/PHASE_C1_ARCHIVAL_AUDIT.md` (new) and `docs/DOCUMENT_AUTHORITY_INDEX.md` (modified) — confirmed by `git status --short` and `git diff --stat` before commit (§19 of the working session).
2. `docs/PHASE_C1_ARCHIVAL_AUDIT.md` is new (did not exist before this pass).
3. `docs/DOCUMENT_AUTHORITY_INDEX.md` is the only modified tracked file besides the new document.
4. No other file changed: confirmed by `git status --short` showing only the two paths above plus the pre-existing untracked `_phase_b_closeout_verify.py` (unrelated, pre-existing, not part of this candidate).
5. No file was moved, renamed, or deleted: confirmed — no `git mv`/`git rm` was issued at any point in this session.
6. No archive directory was created: confirmed — `docs/archive/`, `docs/evidence/`, `docs/proposals/`, and `generated/captures/` do not exist on disk; they appear only as proposed paths inside this document.
7. No existing §17 row changed class or flags: confirmed by diffing the pre-amendment and post-amendment §17 block outside the single new row.
8. All 231 documentation paths (230 pre-existing + 1 new) appear exactly once in the post-amendment §17: confirmed programmatically (no duplicate paths, no missing paths).
9. Every §17 row, including the new row, retains the standard five-field format (path, class, secondary flags, replacement/authority, note).
10. Class E increases from 37 to 38 solely because of the one new audit document; no pre-existing row's class changed.
11. Primary total increases from 230 to 231 solely because of the one new document.
12. `dated-snapshot` increases from 39 to 40 solely because of the one new document's secondary flag.
13. All other secondary totals (`phase-specific` 107, `implementation-not-verified` 39, `duplicate-or-near-duplicate` 13, `misleading-filename` 12, `status-header-added` 79, `contains-current-material` 13, `generated` 8, `generated-guidance-added` 8, `mixed-current-and-historical` 3, `partially-implemented` 3, `contains-obsolete-material` 2, `branch-specific` 1) are unchanged: confirmed by diff.
14. Phase B remains recorded as `Complete — approved 2026-07-14` in §15: unchanged by this pass.
15. Phase C1 is recorded as candidate/pending approval (§15 new paragraph, §22 below): confirmed.
16. No Phase C2 batch is authorised: confirmed — §16, §18, and the new §15 paragraph all state explicitly that execution requires a separate directive.
17. This assessment covers all 230 pre-existing inventory paths: confirmed — §5 classification table and §6 directory table jointly account for all 230; §13 (50) + §17 (180) = 230.
18. Every proposed relocation path in §17 is unique: confirmed programmatically — zero destination collisions across all 180 candidates.
19. No two files are proposed to move to the same destination: same check as above, confirmed.
20. All reference counts cited in §7–§12 and the §17 tables are reproducible from the temporary `git grep`-based scripts described above; the two confirmed operational hard dependencies (§8.1) were additionally verified by direct inspection of the consuming code (`tests/test_deployment_hygiene.py`, `.github/workflows/coverage_scan.yml`, `tools/coverage/coverage_scan.py`).
21. No temporary file remains in the repository as of the candidate commit (all `_c1_*.py`, `_c1_*.tsv`, `_c1_*.md` working files were deleted before committing).

## 22. Approval status

**Approved archival audit and relocation plan — 2026-07-14.**

Phase C1 is approved. It is an audit and relocation plan only — not relocation authority and not implementation authority. Two hundred and thirty pre-existing documents were assessed. One hundred and eighty are proposed relocation candidates (Low 139, Medium 41, High 0). Fifty remain in place. Two operational hard dependencies (`requirements.txt`; `tools/coverage/coverage_report.md`) are excluded from relocation by design — a risk-control decision, not a claim that those dependencies do not exist. The 17 future relocation batches reconcile to exactly 180 files with zero destination collisions; model-allocation totals reconcile to 96 + 60 + 24 = 180. No document was moved, renamed, deleted, reclassified, or reflagged during Phase C1. No Phase C2 batch has begun. Every Phase C2 batch requires a separate candidate, review, approval, and push before any `git mv` is issued. Phase B remains `Complete — approved 2026-07-14`.
