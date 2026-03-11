# Schema sync: single source of truth

The repo has two copies of the same JSON schemas:

| Location | Purpose |
|----------|--------|
| **`schemas/`** (repo root) | Referenced by TRACE_CONTRACT, system map, and “repo-level” docs |
| **`integration_kit/schemas/`** | Referenced by integration_kit README and linked from that kit |

Both currently contain the same 9 files and (where checked) identical content. To avoid drift and confusion, use **one canonical location** and keep the other in sync (or remove it).

---

## Recommendation: root `schemas/` is canonical

- **Canonical:** keep **`schemas/`** at repo root as the single source of truth.
- **Reason:** `docs/design/TRACE_CONTRACT_v1.md` and other authoritative docs already point at `schemas/`. The trace contract is a repo-level contract, not specific to the integration kit.

Then choose **one** of the following for `integration_kit/schemas/`.

---

## Option A: Remove duplicate, point to root (simplest)

1. **Delete** the files in `integration_kit/schemas/` (all 9 `.schema.json` files).
2. **Update** `integration_kit/README.md`:
   - Replace “JSON Schemas (`schemas/`)” with “JSON Schemas: **`../schemas/`** (repo root)” or “Canonical schemas live at repo root: **`schemas/`** when at MandarinOS-core root.”
   - Update any links like `./schemas/TurnStateTrace.schema.json` to `../schemas/TurnStateTrace.schema.json` (relative to integration_kit).
3. **Optional:** Keep an empty `integration_kit/schemas/` with a README that says “Canonical schemas are in the repo root at `schemas/`. Do not duplicate; link to `../schemas/`.”

**Pros:** No duplication, no sync step, one place to edit.  
**Cons:** External repos that copy only `integration_kit/` must know schemas live in the parent repo (document that clearly).

---

## Option B: Symlink (one source, “self-contained” kit)

1. **Delete** the files in `integration_kit/schemas/` (so the directory is empty or gone).
2. **Create a symlink:**  
   `integration_kit/schemas` → `../schemas`  
   (so `integration_kit/schemas/` resolves to the root `schemas/` directory.)
3. **.git:** Git stores symlinks; on clone, `integration_kit/schemas` will point at `../schemas`. No copy step.
4. **integration_kit/README.md:** You can keep wording like “JSON Schemas (`schemas/`)” since the path still exists under integration_kit.

**Pros:** Single source of truth (root), integration_kit still has a `schemas/` path for tools or docs that assume it.  
**Cons:** On Windows, creating symlinks may need Developer Mode or admin; some CI/editors can be fussy. If the repo is used on Windows without symlink support, the link might not work and Option A or C is safer.

**Commands (Unix/WSL/Git Bash):**
```bash
cd integration_kit
rm -f schemas/*.json   # or remove schemas/* and keep dir
rmdir schemas 2>/dev/null || true
ln -s ../schemas schemas
```

**Windows (PowerShell, run as admin or with Developer Mode):**
```powershell
cd integration_kit
Remove-Item schemas\*.json -Force
New-Item -ItemType SymbolicLink -Path schemas -Target ..\schemas
```

---

## Option C: Sync script (copy root → integration_kit)

Keep root `schemas/` as canonical and **copy** into `integration_kit/schemas/` via a script, run manually or in CI.

1. **Add a script** (e.g. `scripts/sync_schemas.py` or `tools/sync_schemas.py`) that:
   - Copies every `*.schema.json` from `schemas/` to `integration_kit/schemas/`.
   - Optionally checks that both dirs exist and have the same set of filenames.
2. **Run it** after any schema change (or in a pre-commit hook / CI step).
3. **Commit** both `schemas/` and `integration_kit/schemas/` so the kit remains a self-contained copy for anyone who only has integration_kit.

**Pros:** Works everywhere (no symlinks); integration_kit stays self-contained.  
**Cons:** Two copies in git; easy to forget to run the script and get out of sync. Mitigate with a CI check that diffs the two directories or runs the sync in CI and fails if there are uncommitted changes.

---

## Summary

| Option | Canonical | integration_kit/schemas | Best when |
|--------|-----------|--------------------------|-----------|
| **A** | `schemas/` (root) | Removed; docs point to `../schemas` | You want zero duplication and are fine documenting “schemas at repo root”. |
| **B** | `schemas/` (root) | Symlink → `../schemas` | You want one source of truth but keep a `schemas/` path under integration_kit (Unix/WSL/common Windows). |
| **C** | `schemas/` (root) | Copy via script | You need the kit to work as a standalone copy and can run a sync step (and/or CI) to keep copies identical. |

**Suggested default:** **Option A** (remove duplicate, point to root). If you later need the kit to be fully self-contained or to work in environments where symlinks are unreliable, add Option C (sync script) or use Option B where supported.

After you choose, update `docs/REPO_STRUCTURE_PROPOSAL.md` section 3 (“Schemas: single source of truth”) to record the decision and any script/symlink steps.
