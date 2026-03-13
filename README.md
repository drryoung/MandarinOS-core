# MandarinOS-core
MandarinOS is the adaptive learning infrastructure for Chinese

# MandarinOS (Core)

MandarinOS is a conversation-first Mandarin learning system designed to diagnose and build **usable spoken competence**, not passive vocabulary recognition.

The system is built around:
- Structured dialogue frames
- Adaptive scaffolding
- A multi-layer hint system
- Content packs defined entirely in JSON (portable and migratable

Development roadmap:
docs/project_plan/MandarinOS_project_plan_v2.md

## Guardrails (Read Before Making Changes)

MandarinOS is conversation-first, frame-driven, and learner-centered.
If proposed changes introduce vocabulary-first flows, teacher-style explanations,
or schema refactors “for cleanliness”, stop and re-evaluate.

See `docs/design/mandarinos_design_constitution.txt` for non-negotiable principles.

## Testing

All test scripts live under `tests/`. **Run them from the repo root** so paths to content files (`p1_frames.json`, `srs_config.json`, etc.) resolve correctly.

- **Python:** `pytest tests/` or `python -m pytest tests/`
- **TypeScript:** from repo root, e.g. `npx ts-node tests/test_diagnostic_p1.ts` (or your usual TS test runner)

Test and build outputs (e.g. `engine_test_results.txt`, `test_results.txt`) belong in `scratch/`; that directory is gitignored.
