<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class B: Current supporting guidance**
>
> - **Current use:** Supporting pipeline and system mental model where it agrees with current code and `docs/ARCHITECTURE.md`.
> - **May guide current implementation:** Yes, within its verified narrow scope.
> - **Current authority:** `docs/ARCHITECTURE.md` and the applicable detailed R2 contract.
> - **Principal caution:** Its internal “Authoritative” label predates the R2 governance package, and some trace-contract framing describes legacy or non-runtime structures.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MANDARINOS_SYSTEM_MAP.md — System Pipeline Map (Authoritative)
Version: 1.0  
Purpose: Give any AI assistant a fast, correct mental model of MandarinOS so it stops making classic architectural mistakes.

Read this file **after** `AI_CONTEXT.md` (which defines AI roles: ChatGPT = strategist/testing, Cursor = architect + programmer with small step-by-step changes only).

---

## 0) One-sentence summary

MandarinOS is a **conversation-first learning system** where **lexicons** feed **builders** that generate **deterministic runtime artifacts**, which drive the **UI loop**, with everything recorded via a **trace contract**.

---

## 1) The canonical pipeline (end-to-end)

### 1.1 High-level flow

```text
Lexicons (source-of-truth language)
        ↓
Builders (deterministic generators)
        ↓
Runtime artifacts (generated JSON used at runtime)
        ↓
Runtime + API (serves data, resolves OPEN_CARD, runs turns)
        ↓
UI (frame display + audio + response + hints + card panel)
        ↓
Trace events (contracted analytics + debugging signals)
```

### 1.2 Key rule
**Never bypass the pipeline.**  
If something is “wrong” in a runtime artifact, fix the **lexicon** or the **builder**, not the artifact.

---

## 2) Data layers: what each layer is allowed to contain

### 2.1 Lexicons = linguistic truth
Lexicons contain the authoritative language content:
- words: hanzi / pinyin / meaning / metadata
- frames: sentence text patterns and IDs
- any curated mappings (if present)

Lexicons are where “what Mandarin is” lives.

### 2.2 Builders = deterministic transformation
Builders convert lexicons (and other sources) into runtime artifacts.

Properties:
- deterministic outputs (same inputs → same outputs)
- versioned rules (builder script is the source of behavior)
- validated by tests (golden tests where possible)

### 2.3 Runtime artifacts = what the UI consumes
Runtime artifacts are generated JSON used by UI/runtime.

Important:
- runtime artifacts are **not** the canonical place to “store language truth”
- they are optimized for runtime usage (lookup speed, stable IDs, UI actions)

### 2.4 UI = interaction and trace emission
UI is where the product loop is executed:
- show + speak a frame sentence
- allow user response (speech and/or option selection)
- provide progressive hints
- open card panel on word clicks
- emit trace events for every meaningful action

### 2.5 Trace = contracted signals
Trace events are structured signals. Current authority for trace structure is `docs/ARCHITECTURE.md` and the applicable R2 contract. Historical background only (class C, non-authoritative): `docs/archive/design-history/TRACE_CONTRACT_v1.md`.

Trace is used for:
- debugging (what happened and why)
- UX verification (did the loop work?)
- diagnostics (how capable is the learner?)

---

## 3) Core entities and IDs (mental model)

### 3.1 Entities
- **Word**: lexicon entry (has hanzi, etc.)
- **Frame**: sentence pattern (text + structure)
- **Card**: UI panel content for a word or frame (display/actions/state)
- **Engine**: grouping of frames/options for a learning mode or phase. Conversation engines (Identity, Place, Food, Family, Study/Work, Travel, Interests) and their design specs are catalogued in **`docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md`** — use that index when implementing or reviewing conversation logic.

### 3.2 ID spaces (do not mix)
Typical ID patterns (examples):
- word IDs: `w_*`
- frame IDs: `frame.*` (or similar)
- card IDs: `card_*` (or similar)

Key invariant:
- The UI should not “guess” relationships between IDs.
- Use indexes/artifacts to map IDs correctly.

---

## 4) The OPEN_CARD path (how card panel should work)

### 4.1 When it happens
OPEN_CARD is triggered when the user:
- clicks a word token
- selects a frame (in some UI modes)
- clicks “more” / “card” affordance

### 4.2 Contract shape
OPEN_CARD payload must preserve the canonical fields:
- `engine_id`
- `frame_id`
- `card_id`
- `reason`

If code changes this shape, it violates the contract.

### 4.3 Mapping responsibility
- UI identifies `word_id` or `frame_id`
- runtime index resolves `*_id → card_id`
- card panel renders card content
- UI emits trace events for open/close actions

---

## 5) Tokenization and clickable text (frame tokens)

### 5.1 Why tokens exist
Frames are tokenized so UI can:
- render word-level clickable tokens
- later support hover / reveal / hint overlays per token

### 5.2 Canonical artifacts
- `frame_tokens.runtime.json` (canonical)
- `frame_render_tokens.runtime.json` (compat alias; byte-identical)

### 5.3 Rule of usage
UI should treat token artifacts as:
- render instructions (not linguistic truth)
- identifiers for clickable elements (which then map to card_id via indexes)

---

## 6) System invariants (things that must remain true)

These invariants prevent architecture drift and silent regressions:

1) **Lexicons are the only authoritative source for hanzi/pinyin/meaning.**
2) **Runtime cards are UI objects, not language truth.** (Do not assume they contain hanzi.)
3) **Generated artifacts are never edited by hand.**
4) **Builders must be deterministic and testable.**
5) **Trace event names and payload shapes must match the trace contract.**
6) **OPEN_CARD payload shape is stable unless explicitly revised with documentation updates.**
7) **Indexes mediate relationships** (word↔frame↔card). The UI should not “infer” mappings.

---

## 7) Typical “where to fix” guide (fast triage)

If you see this problem… | Fix it in… | Not in…
---|---|---
Missing hanzi/pinyin/meaning | Lexicon files | runtime cards JSON
Wrong tokenization / clickable words broken | Token builder + tests | UI hacks to “split on spaces”
Card panel opens wrong content | Index builder / resolver logic | manual edits to card outputs
Trace shows missing events | UI event emission | changing trace contract to fit bugs
Build output differs run-to-run | Builder determinism | ignoring the diff

---

## 8) Recommended AI working pattern (anti-hallucination)

When asked to implement a feature, follow this checklist:

1) Identify relevant contracts: trace + OPEN_CARD shape
2) Identify source-of-truth layer: lexicon vs runtime artifact
3) Identify whether a builder change is required
4) Touch the smallest set of files
5) Run/extend tests
6) Summarize changes with:
   - files touched
   - contract compliance
   - generated artifacts affected
   - tests run

---

## 9) “Read-first” references (authoritative)

- `AI_CONTEXT.md`
- `MandarinOS_AI_Governance_Protocol.md`
- MandarinOS Design Constitution: `docs/design/mandarinos_design_constitution.txt`
- Trace/state current authority: `docs/ARCHITECTURE.md` and the applicable R2 contract (historical background only, class C, non-authoritative: `docs/archive/design-history/TRACE_CONTRACT_v1.md`)
- Phase architecture lock: `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`
- Other phase docs: `docs/phases/` (freezes, checklists, rollback)

---

END
