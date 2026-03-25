# Learner etymology hints — “happy medium” (deferred)

**Status:** Proposal only — **not implemented**. Saved for a future iteration when product is ready to add lighter, pedagogy-first copy between “Form only” and full etymology.

**Context:** Form / decomposition (and IDS in the Form line) help structure but can feel thin; full etymology + narratives can feel heavy. This doc describes a middle layer: short **memory bridges** (meaning hint, optional sound hint, optional bridge to modern use) with honest uncertainty and deeper text behind “more.”

---

## Goal

Deliver a **default “memory bridge”** (structure → meaning, sometimes sound) that is **more helpful than Form alone** but **lighter than full etymology**, with **honest uncertainty** and **clear opt-in** for deeper text.

## Non-goals (v1)

- Animated diagrams, stroke order, pixel-perfect component coloring.
- Historically definitive claims in the default layer.
- Perfect coverage on day one — ship a **high-value subset + graceful fallbacks**.

---

## Learner-facing content model (three tiers)

### Tier A — Always try to show (short, structural)

- **Form:** decomposition + optional IDS (with a tiny, consistent legend in UI — raw IDS alone is opaque to beginners).
- **Meaning hint** (1 line): what the **semantic component / radical field** suggests (learner English).
- **Sound hint** (0–1 line): only when rules say it is **useful** (see gating below).

### Tier B — Optional “bridge” (still short)

- **Link to modern sense** (1 line): connects Tier A to how the character behaves in **common words** (not a history essay).

### Tier C — “More detail”

- Current heavier etymology / narrative — keep, but **collapsed** behind a control or a later progressive step.

**Rule of thumb for defaults:** *Form + ≤2 hint lines + one short uncertainty clause* (not a long disclaimer paragraph).

---

## Data: derivable vs authored

### Mostly derivable (rules / heuristics)

- IDS / decomposition → already feeds “Form.”
- Radical / primary semantic category → “Meaning hint” templates.
- Phonetic component identity → candidate for “Sound hint” *when similarity is acceptable*.

### Usually needs authoring or reviewed generation

- **High-quality one-liners** that avoid misleading learners (especially sound hints).
- **Word-sense bridges** — often better **curated** or **human-reviewed**.

### Proposed explicit fields (conceptual)

Per **character** (optional later: per **character-in-word**):

| Field | Tier |
|--------|------|
| `learner_semantic_hint_en` | A |
| `learner_phonetic_hint_en` | A (optional) |
| `learner_bridge_en` | B (optional) |
| `learner_hints_source` | `manual` \| `rule` \| `generated_reviewed` |
| `learner_hints_version` | for QA / cache busting |

Start with **only** `learner_semantic_hint_en` + rules; add others when quality allows.

---

## Sound-hint gating (avoid nonsense)

Show a phonetic hint only if **all** are true (thresholds tunable):

- Character is **形声-style** in decomposition metadata (or high-confidence tag).
- Phonetic component is identifiable.
- **Pinyin similarity** is above a threshold *or* there is an explicit curated line.

Otherwise: **omit** (silence beats a forced rhyme story).

---

## Implementation phases (when you pick this up)

1. **Spec + templates + fallbacks** — template families for semantic fields; on-screen order; single short uncertainty phrase.
2. **Rule-based fill (subset)** — auto-compose Tier A from existing radical/component metadata; `source=rule`.
3. **Human curation queue** — top-N characters by frequency in product corpus; fill/approve where rules are weak.
4. **Optional assisted drafting** — LLM output only as draft → lint + review → `generated_reviewed`.
5. **UI integration** — default shows Tier A (+B if present) in existing progressive flow; long text in Tier C.
6. **QA metrics** — coverage %, % with sound hint, optional “confusing hint” feedback, periodic audits.

---

## Pipeline placement

- **Preferred:** bake `learner_*` into runtime JSON (e.g. alongside `word_etymology` / character merge) at build time.
- **Prototype OK:** compose at runtime from `characters_1200` + templates; materialize once stable.

---

## Quality guardrails

- Default copy uses **“memory aid / grouping”** language, not **“because in ancient China…”** unless Tier C is explicitly historical and sourced.
- If structure is **unclear** in data: show **Form + generic scaffolding** rather than inventing.
- **Word-level override (later):** if the glyph’s role in *this headword* is special, allow per-word override; don’t force global char hints to carry all word semantics.

---

## Success criteria

- Learners routinely get **one clear reason to remember** without reading a paragraph.
- Phonetic hints can be **turned down globally** via thresholds without redesign.
- Editors can improve hints **without code** (data-only).

## Design choice: where hints live

**Character-first + optional word override** usually scales best: reusable corpus-level hints, with word_etymology overrides only when context matters.

---

## Related repo context

- Character / etymology sources and UI resolution: **`AI_CONTEXT.md` §2.4**.
- Card UI helpers (today): `formatWordEtymologyCharRecordHtml`, `buildCharDeepHintHTML`, `buildComponentEnglishGlossLine`, etc. in `ui/app.js`.
