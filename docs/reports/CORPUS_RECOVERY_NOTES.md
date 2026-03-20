# Character / word corpus — recovery notes (Step 1)

This document records what was **actually found** in this repo and git history when looking for the large compiled character database.

## What we searched

- Repo tree for `**/characters*.json` → only **`characters_1200.json`** at repo root (plus `tools/cards/out/characters_from_words.json`, which is a small id+hanzi list from p1/p2 words, not full etymology).
- **`tools/cards/generate_word_character_links_auto.py`** also looks for (these paths are **not** present in the repo today):
  - `tools/cards/characters_1200.json`
  - `tools/cards/data/characters_1200.json`
- Git blob size for `characters_1200.json` at **`87ff091`** (“Phase 6: Expand character corpus and rebuild cards”) and **`HEAD`**: **same object** `17f75133…`, **12 894 bytes** (~13 KB). So in git, this file has **not** historically been a multi‑MB / ~5k-entry corpus.
- Sibling paths under `Documents/GitHub` for `*character*.json` → no other large character master file beside this repo’s `characters_1200.json`.

## Conclusion for *this* clone

The **very large** database you remember is **not** stored inside the current MandarinOS-core git history as a big `characters_1200.json`. What is here is a **small sample** (on the order of **12 character records** in the `characters` array — see `scripts/audit_vocab_character_coverage.py`).

That does **not** prove the corpus is gone forever; it strongly suggests it lives **outside** this tree (or was never committed), for example:

- Another folder (Desktop, Downloads, an older clone, a backup drive, a different repo).
- OneDrive **version history** on `characters_1200.json` (right-click file → Version history) if it was ever replaced locally.
- A name other than `characters_1200.json` (e.g. export as `.jsonl`, `.csv`, or inside a zip).
- Git **LFS** or a second remote (unlikely here if blob is 13 KB everywhere).

## What you can do next (manual, high yield)

1. **OneDrive / File Explorer**  
   Search your PC for files that are **large** (e.g. > 500 KB) and contain `"Characters 1200"` or `"character_id"` + `"primary_radical"` in the first lines (open in editor and search).

2. **OneDrive version history**  
   On `MandarinOS-core/characters_1200.json` → restore an older version if a larger file appears.

3. **Other git remotes / machines**  
   `git remote -v` and pull or clone elsewhere; check `characters_1200.json` size there.

4. **Email / cloud exports**  
   If the compile was saved as an attachment or export, re-download and place at **repo root** `characters_1200.json` (same JSON schema as current sample).

5. **After recovery**  
   Run `python scripts/audit_vocab_character_coverage.py` — you should see `characters_1200.json` record count in the **thousands**, not ~12.

## Canonical path once found

Per **`AI_CONTEXT.md` §2.4**, the builder expects the full corpus at:

**`<repo-root>/characters_1200.json`**

Same schema as the sample (`characters` array, `id`, `hanzi`, etc.). Then run **`python tools/build_runtime_artifacts.py`** to regenerate `runtime/out_phase7/word_etymology.runtime.json`.

---

*Last updated: forensic step after user request to locate the real corpus.*
