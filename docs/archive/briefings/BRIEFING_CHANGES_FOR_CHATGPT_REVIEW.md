# Briefing: Changes for ChatGPT Review and Authorization

**Date:** 2026-03-08  
**Purpose:** Summarise all recent repo and process changes so ChatGPT (as strategist and reviewer) can review and authorise them.  
**Your role:** Review the summary below; confirm approval or request corrections. No code changes are required from you—only review and sign-off.

---

## 1. Repo structure: documentation and root cleanup

### What was done

- **New doc folders** under `docs/`:
  - `docs/design/` — Design, constitution, TRACE contract, handoffs
  - `docs/specs/` — Versioned specs (engines, models, content packs, contracts)
  - `docs/directives/` — Implementation/Cursor directives (formerly “Copilot”)
  - `docs/briefings/` — Handoffs and session briefings
  - `docs/phases/` — Phase freezes, checklists, rollback
  - `docs/project/` — Commit instructions, audits, summaries

- **All relevant docs moved** from repo root and from old `docs/` into these folders. Root now has far fewer files.

- **Left at root on purpose:** `README.md`, `AI_CONTEXT.md`, `MANDARINOS_SYSTEM_MAP.md`, and package/config JSON that scripts expect at root (`p1_frames.json`, `srs_config.json`, etc.).

- **Links updated** in `AI_CONTEXT.md` and `MANDARINOS_SYSTEM_MAP.md` to point to the new paths (e.g. `docs/design/TRACE_CONTRACT_v1.md`, `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`).

**Reference:** `docs/REPO_STRUCTURE_PROPOSAL.md` describes the full plan; section 3 (schemas) marked done; section 4 (tests) marked done.

---

## 2. Test outputs and test scripts

### What was done

- **Moved to `scratch/`** (gitignored):  
  `engine_test_results.txt`, `integration_test_results.txt`, `p1p2_test_fixed.txt`, `p1p2_test_results.txt`, `results.txt`, `test_results.txt`, `appjs_backup.patch`.

- **Moved to `tests/`:**  
  All former root test scripts: `test_diagnostic_engine.py`, `test_diagnostic_integration.py`, `test_diagnostic_p1.py`, `test_diagnostic_p1.ts`, `test_hint_cascade.py`, `test_p1_to_p2_transition.py`, `test_scaffolding_transitions_v1.py`.

- **README.md** updated: new “Testing” section states that tests live under `tests/`, must be **run from repo root** (so paths to `p1_frames.json`, `srs_config.json`, etc. resolve), and that test output belongs in `scratch/`.

- **docs/project/TEST_SUMMARY.md** updated: “Command to Run All Tests” now uses `tests/...` and states “run from repo root”.

**No behaviour change:** Tests still load content from repo root when run from root (e.g. `pytest tests/`).

---

## 3. Schema sync (single source of truth)

### What was done

- **Canonical schemas:** Repo root `schemas/` is the only source of truth for trace/contract JSON schemas.

- **integration_kit:** The duplicate copy in `integration_kit/schemas/` was **removed** (all 9 `.schema.json` files deleted). That folder now contains only `integration_kit/schemas/README.md`, which points to `../../schemas/` (repo root).

- **integration_kit/README.md** updated: all references to “schemas” now point to `../schemas/` (repo root). “Files in This Kit” tree updated so `schemas/` is described as a pointer to root, not a duplicate.

**Reference:** `docs/SCHEMA_SYNC_RECOMMENDATION.md` documents the options; Option A (remove duplicate, point to root) was implemented.

---

## 4. AI roles rescope (ChatGPT + Cursor; Copilot retired)

### What was done

**Intent:** ChatGPT remains strategist and testing; Cursor takes both senior architect and programmer roles. GitHub Copilot is no longer used. Cursor, when acting as programmer, must make **small, step-by-step changes only** to avoid drift from the Design Constitution.

#### 4.1 AI_CONTEXT.md (repo root)

- Opening line: “Cursor, Copilot, ChatGPT” → “Cursor, ChatGPT”.
- **New section “AI roles”:**
  - **ChatGPT:** Strategist and testing (no code).
  - **Cursor:** Senior architect and programmer; as programmer, **small step-by-step changes only**—one concern at a time, no large refactors—to avoid drift from the Design Constitution.
  - Note: GitHub Copilot no longer used.
- **§1.3 Minimal change policy:** Tightened and labelled “(Cursor as programmer: strict)”: one concern at a time, one file (or minimal set) per step, no large refactors unless requested, preserve behaviour, stop after each step for review.
- **§9 “If you are asked to implement a feature”:** Reframed for “Cursor as programmer”: one small reviewable change at a time; do not bundle concerns; if the task is large, break into steps; if a change would conflict with Design Constitution or phase locks, do not implement—report and ask.

#### 4.2 docs/design/mandarinos_design_constitution.txt

- Tripwire “Copilot suggests schema refactors” → “Schema refactors for cleanliness”; text now refers to “implementation assistant (e.g. Cursor)”.
- Tripwire “Silent rewrites” → “Silent rewrites / multi-concern changes”; added that the programmer (Cursor) must make small, step-by-step edits to avoid design drift.

#### 4.3 docs/directives/MANDARINOS_ARCHITECT_COPILOT_HANDOFF_DIRECTIVE_PHASE7.txt

- Title: “ARCHITECT + COPILOT” → “AI ROLES HANDOFF DIRECTIVE”.
- New AI roles paragraph: ChatGPT = strategist + testing; Cursor = senior architect + programmer; Cursor must make small step-by-step changes only; Design Constitution non-negotiable.
- “COPILOT WORKFLOW” → “AI WORKFLOW”: ChatGPT (strategist + testing), Cursor (architect + programmer, small steps, no drift).
- “SEARCH the repo (Copilot or ripgrep)” → “Cursor or ripgrep”.

#### 4.4 .github/copilot-instructions.md

- Title/intro: Now “Cursor (Implementation) Operating Instructions”; states Copilot is no longer used; points to AI_CONTEXT.md for roles and step-by-step discipline; reminds that Cursor as programmer makes small, step-by-step changes only and must not drift from the Design Constitution.
- §4 “Copilot guidance” → “Cursor as programmer”.
- §8 references: Updated to `docs/design/` paths for Design Constitution and Developer Handoff.

#### 4.5 docs/specs/MandarinOS_master_AI_bootstrap_context.md

- Purpose: “ChatGPT, Cursor, Copilot” → “ChatGPT, Cursor” plus a short AI roles note (ChatGPT = strategist + testing, Cursor = architect + programmer, small steps; Copilot no longer used).

#### 4.6 docs/directives/MANDARINOS_COPILOT_STARTUP_INSTRUCTIONS.txt

- Deprecation notice added at top: Copilot no longer used; for implementation use AI_CONTEXT.md and .github/copilot-instructions.md; ChatGPT = strategist + testing, Cursor = architect + programmer (small steps). Original content retained below for reference.

#### 4.7 MANDARINOS_SYSTEM_MAP.md

- Read-order line updated to say: read after AI_CONTEXT.md, which defines AI roles (ChatGPT = strategist/testing, Cursor = architect + programmer, small steps only).

---

## 5. What you are being asked to do

1. **Review** the summary above and, if you have access, spot-check any of the listed files.
2. **Confirm** that:
   - The repo structure (docs, tests, scratch, schemas) is acceptable.
   - The AI roles (ChatGPT = strategist + testing, Cursor = architect + programmer, small step-by-step only, no Copilot) and the anti-drift rules (constitution, minimal change, stop for review) are correct and complete.
3. **Authorise** by replying in the affirmative (e.g. “Approved” or “Authorised as described”), or **request changes** by listing what should be adjusted (e.g. wording, missing files, or policy).

No code edits are required from you unless you explicitly request them.

---

## 6. Quick reference: key files to spot-check (optional)

| Topic              | File(s) |
|--------------------|--------|
| AI roles & steps   | `AI_CONTEXT.md` (new “AI roles” section, §1.3, §9) |
| Constitution       | `docs/design/mandarinos_design_constitution.txt` (tripwires) |
| Handoff directive  | `docs/directives/MANDARINOS_ARCHITECT_COPILOT_HANDOFF_DIRECTIVE_PHASE7.txt` |
| Cursor instructions| `.github/copilot-instructions.md` |
| Schema pointer     | `integration_kit/schemas/README.md`, `integration_kit/README.md` |
| Testing            | `README.md` (Testing section), `docs/project/TEST_SUMMARY.md` |

---

**End of briefing.** Please reply with your review and authorisation (or requested corrections).
