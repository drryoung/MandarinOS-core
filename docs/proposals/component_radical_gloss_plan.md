<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as a proposal for component and radical gloss functionality.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current content, UI, and tooling code together with the applicable R2 governance documents.
> - **Principal caution:** This plan does not establish that component or radical gloss behaviour exists in the current application. Implementation and user-visible behaviour must be verified independently.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Component & radical glosses for the Form line (deferred)

**Status:** Phases **1–4 implemented** (2026-03): **`component_gloss_maps.json`** at repo root (served like `characters_1200.json`; optional copy under `data/`), `loadComponentGlossMaps()` in `ui/app.js`, `scripts/audit_component_gloss_coverage.py` → `docs/reports/component_gloss_coverage.md`, `tools/backfill_component_gloss_en.py` + corpus `gloss_en` backfill. Phase **5 (QA)** remains manual.

**Problem:** Learners often see `Form: 亻 + 乍` with **no parenthetical English** because `resolveGlyphGlossEn()` returns empty for those glyphs. The UI already supports `Form: 亻 (…) + 乍 (…)` when gloss data exists (`ui/app.js`: `buildComponentEnglishGlossLine`).

**Goal:** Add a **small, reliable layer** of learner-facing glosses for **frequent components and radical forms** so the Form line becomes self-explanatory without turning into full etymology.

---

## Non-goals (initial scope)

- Historical etymology claims or long narratives (see **`docs/plans/learner_etymology_hints_plan.md`** for that).
- Perfect coverage for every rare component on day one.
- Changing decomposition source data (IDS/tree) — only **enrich gloss resolution**.

---

## Strategy: three complementary sources (precedence)

Keep a **single resolution function** conceptually; extend what it can see. Suggested **lookup order** (first hit wins, or merge rules as noted):

1. **Radical / component variant map (new)**  
   High-priority labels for **graphical variants** that rarely appear as standalone vocabulary words, e.g.  
   `亻` → “person (human radical)”, `氵` → “water”, `扌` → “hand”, `讠` → “speech”, `钅` → “metal”, `阝` (which side?) → disambiguate if you store two keys.  
   *Rationale:* `GLYPH_TEACHING_GLOSS_EN` already has `人` but not `亻`; learners meet `亻` constantly.

2. **Existing teaching fallback map (`GLYPH_TEACHING_GLOSS_EN`)**  
   Continue curating common **whole-character** components that are also words (木, 口, …).

3. **Corpus `gloss_en` (`characters_1200.json`)**  
   For any component that **is** a row in the corpus (e.g. **乍**), prefer or merge with a **short** `gloss_en` suitable for parentheses (≤ ~40–60 chars; one clause).

**Optional refinement (v2):** If decomposition metadata tags **semantic_component** vs phonetic hint, append a **role suffix** in the UI only when confident, e.g. `乍 (sound hint)` vs bare gloss — avoid debate-heavy “definitions” for phonetics.

---

## Content guidelines

- **Tone:** mnemonic / grouping language, not faux history.  
- **Radical variants:** name the **semantic family** (“person”, “water”) not a mini essay.  
- **Phonetic pieces:** prefer **“sound component”** or a very short gloss + “(sound)” when pinyin alignment is weak — **omit** rather than guess wildly.  
- **Consistency:** one style guide (e.g. always “X (human radical)” vs “person radical”) across the map.

---

## Phased rollout

| Phase | Work | Outcome |
|--------|------|--------|
| **1 — Spec** | List ~40–80 most frequent **component/radical glyphs** in your product corpus (from `decomposition_tree` / `components_flat` frequency scan). | Prioritized backlog. |
| **2 — Variant map v1** | Add curated entries for top variants (`亻`, `氵`, …). | Immediate uplift on Form lines like 作. |
| **3 — Corpus backfill** | For high-frequency **second components** (乍, 青, …), add/trim `gloss_en` in source JSON (or a small overlay file merged at build time if you avoid hand-editing a huge file). | Better coverage without bloating JS. |
| **4 — Builder / tests** | Optional: script that reports “Form lines with N/M components lacking gloss” per character or per vocab list. | Regression visibility. |
| **5 — QA** | Spot-check 20–30 characters across frames; verify no misleading phonetic claims. | Safe learner copy. |

---

## Success metrics

- **Coverage:** % of in-corpus character decompositions where **all** displayed components have a non-empty gloss (target: raise steadily, e.g. 60% → 85% for **curriculum subset**).  
- **UX:** Form line rarely shows “bare” `亻` / `氵` for top-500 components.  
- **Maintenance:** New components can be added in **one place** (variant map or corpus) with a short CHANGELOG note.

---

## Related

- **`AI_CONTEXT.md` §2.4** — character / etymology sources of truth.  
- **`docs/plans/learner_etymology_hints_plan.md`** — optional extra “memory bridge” lines beyond parentheses.  
- **Implementation touchpoint (when ready):** `resolveGlyphGlossEn`, `GLYPH_TEACHING_GLOSS_EN`, and/or new `RADICAL_VARIANT_GLOSS_EN` (name TBD) in `ui/app.js`; optionally generate a merged JSON artifact in the builder if the map grows large.
