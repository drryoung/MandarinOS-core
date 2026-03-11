# MandarinOS-core — Proposed directory & file structure

This document suggests a logical layout to reduce root clutter and make files easier to find. Apply in phases; paths that scripts depend on are called out.

---

## Current problems

- **~100+ files at repo root**: specs (`.md`), directives (`.txt`), config (`.json`), test scripts (`test_*.py`), results (`.txt`/`.json`), and one-off docs.
- **Schemas in two places**: both `schemas/` and `integration_kit/schemas/` with overlapping content.
- **Tests split**: some in `tests/`, some at root (`test_diagnostic_*.py`, `test_scaffolding_*.py`, etc.).
- **Config paths hardcoded**: many tools assume `p1_frames.json`, `p2_frames.json`, `srs_config.json` at repo root — moving them would require updating those references.

---

## Proposed structure (high level)

```text
MandarinOS-core/
├── README.md
├── .gitignore
├── AI_CONTEXT.md                    # Keep at root (AI entry point)
├── MANDARINOS_SYSTEM_MAP.md         # Keep at root (authoritative pipeline map)
│
├── docs/                            # All documentation (expand subdirs below)
├── config/                          # Optional: content/config JSON (see caveat)
├── schemas/                         # Single source for JSON schemas
├── integration_kit/                 # Examples + TS snippets; schemas → point here or merge
├── runtime/                         # Engine + build output (unchanged)
├── ui/                              # Frontend (unchanged)
├── scripts/                         # Run scripts (unchanged)
├── tools/                           # Build & analysis (unchanged)
├── tests/                           # All tests + fixtures (move root test_*.py here)
├── golden/                          # Golden turns/traces/transitions (unchanged)
├── policy/                          # Policy JSON (unchanged)
├── conformance/                     # Conformance harness (unchanged)
├── scratch/                         # Local/scratch output (already in .gitignore)
└── .github/                         # Workflows, copilot instructions
```

**Root:** Only README, .gitignore, AI_CONTEXT.md, MANDARINOS_SYSTEM_MAP.md, and **package/ts/build config** (package.json, tsconfig.json, components.json). Everything else moves into the folders below.

---

## 1. Documentation: `docs/`

Move all spec, directive, and project docs from root into `docs/` with subfolders so type and topic are obvious.

### 1.1 `docs/design/` — Design & constitution

- `mandarinos_design_constitution.txt` (from docs/)
- `MandarinOS_brief.md` (from docs/)
- `p3_architecture.md`, `ux_flow.txt`
- `TRACE_CONTRACT_v1.md` (from docs/)
- `CARDS_BUILD_v1.md`, `SCENARIOS_REQUIRED_v1.md`
- `MandarinOS Developer Handoff.rtf` / `.txt`
- `LICENSE.md`

### 1.2 `docs/specs/` — Versioned specs (engines, models, contracts)

**Conversation & runtime:**

- `MandarinOS_conversation_*.md`, `MandarinOS_conversation_*.pdf`
- `mandarinos_conversation_*.md`, `mandarinos_*_engine_*.md`, `mandarinos_*_model_*.md`
- `MandarinOS_runtime_conversation_state_engine_v1.md`, `MandarinOS_turn_data_contract_v1.md`
- `MandarinOS_engine_specs_v1.md`, `MandarinOS_conversation_system_blueprint_v1.md`
- `MandarinOS_next_question_selector_v1.md`, `MandarinOS_capability_update_rules_v1.md`
- `MandarinOS_Conversation_UX_Protocol_v1.md`, `MandarinOS_conversation_*_audit_*.md`

**Content packs & ladders:**

- `mandarinos_*_pack_*.md`, `mandarinos_*_ladder*.md`, `mandarinos_*_vocab_*.md`
- `mandarinos_*_memory_rules*.md`, `mandarinos_*_emergency_*.md`
- `MandarinOS_support_packs_v1.md`

**Other specs:**

- `MandarinOS_marketing_positioning_v1.md`, `MandarinOS_master_AI_bootstrap_context.md`

### 1.3 `docs/directives/` — Implementation / Copilot directives (`.txt`)

- All `*_directive.txt`, `*_DIRECTIVE*.txt` from root (e.g. `MandarinOS_card_contract_v1_directive.txt`, `MandarinOS_conformance_harness_directive.txt`, `MandarinOS_OPEN_CARD_*.txt`, `MandarinOS_UI_Shell_Copilot_Directive.txt`, etc.)
- `MANDARINOS_COPILOT_STARTUP_INSTRUCTIONS.txt`, `MANDARINOS_ARCHITECT_COPILOT_HANDOFF_DIRECTIVE_PHASE7.txt`
- `mandarinos_copilot_architecture_update.txt`
- `MandarinOS_Phase_Boundaries_v1.0.txt`, `MandarinOS_integration_kit_scenarios_v1_directive.txt`

### 1.4 `docs/briefings/` — Handoffs & session briefings

- `MandarinOS_laptop_handoff_UI_cascading_help_briefing.md`
- `mandarinos_chatgpt_session_briefing.md`
- `phase7_3_senior_architect_briefing.md` (from docs/)
- `docs/PHASE7_SCHEMA_DISCOVERIES.md`

### 1.5 `docs/phases/` — Phase freezes, checklists, rollback

- `PHASE6_FREEZE.md`, `PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`, `PHASE6_RUNTIME_INDEXES_NOTES.md`
- `MandarinOS-Phase 3 Acceptance checklist.MD`, `Phase 3 Step 1 Audio-first UI.md`
- `ROLLBACK_POINT_v1.md`

### 1.6 `docs/project/` — Commit, audit, summaries

- `COMMIT_INSTRUCTIONS.md`, `COMMIT_SUMMARY.md`, `COMMIT_SUMMARY_v1.md`, `COMMIT_RECORD.md`
- `AUDIT_OPTION_GENERATION.md`, `OPTION_GENERATION_FIX_COMPLETE.md`
- `EXECUTIVE_SUMMARY_v1.md`, `CHATGPT_BRANCH_START_TEMPLATE.md`
- `DIRECTIVE_PHASE_1_CARD_PANEL_STATE.md`
- `TEST_SUMMARY.md`, `TEST_DIAGNOSTIC_P1_MANUAL.md`, `DIAGNOSTIC_P1_VALIDATION_RESULTS.md`

---

## 2. Config & data (optional; path-sensitive)

Many scripts and configs assume **repo root** for:

- `p1_frames.json`, `p2_frames.json`
- `p1_words.json`, `p2_words.json`, `p1_fillers.json`, `p2_fillers.json`
- `p1_engines.json`, `p2_engines.json`
- `srs_config.json`
- `content_manifest.json`, `manifest.json`, `pack_meta.json`, `runtime_indexes.json`
- `id_map.json`, `report.json`, `import_order.json`, `import_validation_rules.json`

**Recommendation:** Keep these at **root** for now to avoid a large refactor. If you later introduce a `config/` (or `data/`) directory, add a single constant (e.g. `CONFIG_ROOT` or `REPO_ROOT`) and update all tools that reference these files (see grep results for `p1_frames.json`, `srs_config.json`, etc.).

Optional root cleanup that is **low risk** if nothing references them by path:

- Move **diagnostic/result artifacts** into `scratch/` or `tests/out/`: e.g. `diagnostic_p1.json`, `diagnostic_p2.json`, `engine_test_results.txt`, `test_results.txt`, `p1p2_test_results.txt`, `results.txt`, `report.json` (if it’s generated). Ensure `.gitignore` or test scripts don’t assume root.

---

## 3. Schemas: single source of truth ✅ Done

- **Option A:** Keep `schemas/` at root as canonical; have `integration_kit` reference `../schemas` or copy/symlink so there’s one place to edit.
- **Option B:** Keep only `integration_kit/schemas/` and remove root `schemas/` after updating any references (e.g. in tools, runtime, or CI).

**Applied:** Option A — root `schemas/` is canonical; `integration_kit/schemas/` now only has a README pointing to `../../schemas/`. See `docs/SCHEMA_SYNC_RECOMMENDATION.md`.

---

## 4. Tests: consolidate under `tests/`

Move root-level test scripts into `tests/` so all tests live in one place:

- `test_diagnostic_engine.py` → `tests/test_diagnostic_engine.py`
- `test_diagnostic_integration.py` → `tests/test_diagnostic_integration.py`
- `test_diagnostic_p1.py` → `tests/test_diagnostic_p1.py`
- `test_diagnostic_p1.ts` → `tests/test_diagnostic_p1.ts` (if you run TS tests from repo root, adjust script paths)
- `test_hint_cascade.py` → `tests/test_hint_cascade.py`
- `test_p1_to_p2_transition.py` → `tests/test_p1_to_p2_transition.py`
- `test_scaffolding_transitions_v1.py` → `tests/test_scaffolding_transitions_v1.py`

**Note:** These scripts often load `p1_frames.json`, `srs_config.json` from current working directory. Either:

- Run pytest from repo root with `tests/` as test path (e.g. `pytest tests/`), so `cwd` stays root and paths still work, or
- Change each test to use `REPO_ROOT` / `Path(__file__).resolve().parent.parent` and then load from root (or from `config/` if you move config later).

---

## 5. Root files to remove or relocate

After moves above, **delete or relocate** from root (only if not referenced by path):

- **Patches/backups:** `appjs_backup.patch` → move to `scratch/` or drop if obsolete.
- **One-off JSON** (if generated or local): e.g. `report.json`, `results.txt`, `p1p2_test_fixed.txt` → `scratch/` or `tests/out/`.
- **Copilot/context:** e.g. `MANDARINOS_COPILOT_STARTUP_INSTRUCTIONS.txt` → `docs/directives/` or `.github/` if it’s for GitHub Copilot.

Keep at root only:

- `README.md`, `.gitignore`
- `AI_CONTEXT.md`, `MANDARINOS_SYSTEM_MAP.md`
- `package.json`, `package-lock.json`, `tsconfig.json`, `components.json`
- Content/config JSON that scripts expect at root (until you refactor to `config/`)
- Any file that your CI or local scripts explicitly reference by path (e.g. `manifest.json` if used by tooling).

---

## 6. Quick reference: where things go

| Type | Destination |
|------|-------------|
| Design, constitution, architecture | `docs/design/` |
| Versioned specs (engines, models, contracts) | `docs/specs/` |
| Copilot/implementation directives (.txt) | `docs/directives/` |
| Handoffs, briefings | `docs/briefings/` |
| Phase freezes, checklists, rollback | `docs/phases/` |
| Commit instructions, audits, summaries | `docs/project/` |
| Content/config JSON (optional later) | `config/` (only after updating all path references) |
| Generated/diagnostic outputs | `scratch/` or `tests/out/` |
| All test scripts | `tests/` |
| JSON schemas | `schemas/` (canonical) or `integration_kit/schemas/` (pick one) |

---

## 7. Suggested order of operations

1. Create `docs/` subdirs: `design`, `specs`, `directives`, `briefings`, `phases`, `project`.
2. Move existing `docs/*` into `docs/design/` (or the right subdir) and move root `.md`/`.txt` into the appropriate `docs/` subdirs. Update any links (e.g. in README, AI_CONTEXT.md, MANDARINOS_SYSTEM_MAP.md) that point to moved files.
3. Move root `test_*.py` (and if desired `test_*.ts`) into `tests/`; fix cwd or use REPO_ROOT so frame/config paths still work.
4. Move result/scratch files to `scratch/` or `tests/out/` and adjust .gitignore if needed.
5. Decide canonical schema location; update `integration_kit` and any tooling that references schemas.
6. (Optional) Introduce `config/` and refactor all references to content/config JSON in one pass.

If you want, the next step can be a concrete checklist (file-by-file move list) for step 2, or a small script that only creates the new `docs/` folders and leaves the moves to you.
