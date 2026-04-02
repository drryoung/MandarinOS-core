# MandarinOS Cursor Implementation Brief  
## Phase 12D — Meaning + Move Overlay (Alpha Overlay)

**Purpose:**  
Implement a thin overlay that helps the learner interpret ambiguous Chinese responses and choose a safe next move, **without changing the Phase 6 runtime architecture** and **without rewriting the selector or conversation engine**.

This is a **small strategic overlay**, not a major product rewrite.

---

# 1. Phase placement

## Implement this in:
**Phase 12D — Meaning + Move Overlay**

## Position relative to other work
- **If Phase 12C is not finished:** finish Phase 12C first.
- **If Phase 12C is already done or mostly stable:** implement this next as **Phase 12D**.
- **Do not wait for P3 expansion.**
- **Do not treat this as a Phase 13 or later rewrite.**

## Why now
This overlay changes what alpha testers experience the product to be.

Without it, alpha testers mainly experience MandarinOS as:
- a conversation-first language app

With it, alpha testers begin to experience MandarinOS as:
- a system that helps them **interpret meaning**
- reduce interaction risk
- choose a safe next move in ambiguous situations

That is strategically important and can be tested now with low engineering risk.

---

# 2. Strategic rule

## Do not change:
- Phase 6 runtime behavior
- selector logic
- conversation engine core flow
- move_type transition logic
- repair loop architecture unless already planned separately

## Do add:
A **content + UI overlay** that attaches to selected frames or phrases and shows:

1. **Meaning**
   - likely interpretation
   - optional alternative interpretations
   - uncertainty where relevant

2. **Move**
   - 2–3 safe next moves the learner can make

This must be:
- lightweight
- optional
- non-intrusive
- easy to expand later

---

# 3. Product goal

When a learner encounters an ambiguous phrase such as:

> 我们可以考虑一下  
> 以后再说吧  
> 还行吧  
> 不一定  
> 看情况  

MandarinOS should help them understand:

- what this may really mean in context
- what safe response options exist
- how to keep the interaction alive without forcing clarity too early

This is **not** full cultural explanation.
This is a practical **Meaning + Move** support layer.

---

# 4. Scope for first implementation

## First release scope
Implement the overlay for approximately **20–30 high-value items** only.

Do **not** try to cover the full pack.

## Prioritize phrases/frames that involve:
- hesitation
- polite refusal
- weak agreement
- uncertainty
- deferral
- ambiguity
- soft non-commitment
- clarification pressure
- face-saving language
- indirect response patterns

## Examples of suitable items
These are examples only. Cursor should confirm exact coverage based on existing content.

- 我们可以考虑一下
- 以后再说
- 看情况
- 可能吧
- 不一定
- 还可以
- 还行
- 有机会的话
- 再看看
- 我想想
- 这个有点难说
- 不太方便
- 最近比较忙
- 可以吧
- 没问题 (when possibly formulaic)
- 嗯嗯
- 行吧
- 好啊 (with possible weak enthusiasm)
- 先这样吧
- 改天吧

If the current pack does not yet contain enough of these, start with the best available subset and keep the data structure extensible.

---

# 5. Architectural decision

## Recommended implementation model
Use a **separate overlay artifact** loaded by the UI.

### Recommended new runtime-facing artifact
`runtime/out_phase7/meaning_move_overlay.runtime.json`

### Recommended source file
Place the human-editable source in a content or tools area, for example one of these patterns:

- `content/meaning_move_overlay.json`
- or `tools/meaning_move_overlay/meaning_move_overlay.source.json`

Cursor may choose the exact source location, but it must follow the project’s existing artifact-generation style.

## Why separate
This should remain:
- isolated from runtime logic
- easy to expand by content work
- easy to test
- easy to remove or hide in UI if needed

Do **not** embed this into selector logic or frame_options.runtime.json unless there is a compelling architecture reason.

---

# 6. Data model (recommended)

Use a structure keyed by `frame_id` first.

If later needed, it can be expanded to support phrase-level keys, move_type keys, or response_role keys.

## Recommended JSON shape

```json
{
  "version": "phase12d_v1",
  "by_frame_id": {
    "p2_work_07": {
      "label": "soft hesitation",
      "meaning": {
        "primary": "This is probably not a firm yes.",
        "alternatives": [
          "The speaker may need more time.",
          "The speaker may be avoiding direct refusal.",
          "The speaker may need approval from someone else."
        ],
        "confidence": "medium"
      },
      "moves": [
        {
          "id": "clarify_gently",
          "title": "Clarify gently",
          "description": "Ask a small follow-up question without pressuring them."
        },
        {
          "id": "reduce_scope",
          "title": "Suggest a smaller next step",
          "description": "Make the request easier to accept."
        },
        {
          "id": "leave_space",
          "title": "Leave space and return later",
          "description": "Do not force a decision immediately."
        }
      ],
      "notes": "Keep this practical and low-load. Do not over-explain."
    }
  }
}
```

## Field guidance
- `label`: short human-readable category
- `meaning.primary`: most likely interpretation
- `meaning.alternatives`: possible alternative readings
- `meaning.confidence`: `low`, `medium`, or `high`
- `moves`: 2–3 items only for v1
- `notes`: optional internal note

## Important
Do not present interpretation as absolute fact.
Use soft phrasing:
- likely
- may mean
- could indicate
- not always

That matters because the product is helping with ambiguity, not pretending certainty.

---

# 7. UI behavior

## Goal
Show Meaning + Move only when relevant and only when data exists.

## Recommended UI pattern
Add a small expandable help section below the main frame/response area.

Possible label:
- **Meaning + Move**
- or **What this may mean**
- or **Interpretation**

Preferred wording for the button:
- **Meaning + Move**

## UX requirements
- hidden by default is acceptable
- lightweight
- one tap to expand
- should not overwhelm the learner
- should not compete visually with the main learning loop

## Minimum UI content
When expanded, show:

### Meaning
- primary interpretation
- 1–3 alternative interpretations if present
- optional confidence marker in subtle form

### What you can do next
- 2–3 next move suggestions
- plain English
- short and practical

## Do not
- add long cultural essays
- add academic explanations
- add too many move choices
- interrupt the main flow automatically on every turn

---

# 8. Loading model

## Recommended loading behavior
At UI startup, load:

`/runtime/out_phase7/meaning_move_overlay.runtime.json`

Store it in the UI state as read-only content data.

## If file missing
Fail softly:
- log a trace event
- do not break the session
- simply hide the Meaning + Move section

## Recommended trace events
Examples:
- `MEANING_MOVE_OVERLAY_LOADED`
- `MEANING_MOVE_OVERLAY_MISSING`
- `MEANING_MOVE_RENDERED`
- `MEANING_MOVE_EXPANDED`
- `MEANING_MOVE_NO_ENTRY`

Do not overbuild tracing, but enough to verify behavior.

---

# 9. Mapping logic

## For v1
Map overlay entries by **current frame_id**.

That is enough for the first pass.

## Why this is acceptable
- simplest implementation
- no selector changes
- aligns with existing frame-based architecture
- easiest to test

## Later expansion (not for now)
Possible future support:
- by card_id
- by move_type
- by response_role
- by phrase pattern
- by scenario tag
- by relationship/power-distance tag

But do not add these now unless there is a strong need during implementation.

---

# 10. Suggested files likely involved

Cursor should inspect and confirm exact file names before editing, but likely files include:

- `ui/app.js`
- `ui/index.html`
- `ui/styles.css`
- existing runtime artifact build script area
- a new content JSON source file
- runtime manifest update if relevant
- optional tests

If build manifest is used for runtime artifacts, update it consistently.

---

# 11. Step-by-step implementation plan for Cursor

## Step 1 — Read the governing docs first
Before writing code, read:

- `MandarinOS AI Interaction Protocol v1.0`
- `PHASE6_RUNTIME_ARCHITECTURE_LOCK.md`
- relevant project plan file
- current UI loading pattern for `runtime/out_phase7/*.json`

Do not proceed until these are understood.

---

## Step 2 — Create a source JSON file
Create a small source data file containing approximately 20–30 Meaning + Move entries.

Rules:
- use clear plain English
- keep each entry short
- prefer practical guidance
- use uncertainty language
- do not write essays

---

## Step 3 — Add or extend a builder step
Generate:

`runtime/out_phase7/meaning_move_overlay.runtime.json`

This should be deterministic and compatible with the project’s current artifact pipeline style.

If no formal builder is necessary for v1, a minimal deterministic copy/build step is acceptable, but keep the pattern clean and consistent with project conventions.

---

## Step 4 — Load the runtime artifact in the UI
Update the UI initialization logic to fetch:

`/runtime/out_phase7/meaning_move_overlay.runtime.json`

Store the result in an in-memory structure keyed by `frame_id`.

Fail softly if unavailable.

---

## Step 5 — Render a lightweight Meaning + Move section
In the UI, add an expandable section that appears only if the active frame has an overlay entry.

Display:
- short label
- primary meaning
- alternatives if available
- 2–3 suggested next moves

Keep the layout plain and readable.

---

## Step 6 — Add minimal trace events
Emit trace events for:
- overlay loaded
- overlay missing
- entry rendered
- section expanded

This is to support alpha testing and troubleshooting.

---

## Step 7 — Test with a small known set of frames
Choose several frames with overlay entries and confirm:
- correct load
- correct render
- no breakage if no entry exists
- no runtime changes
- no selector changes
- no regression to main learning loop

---

# 12. Acceptance criteria

The implementation is accepted when all of the following are true.

## Functional
1. A new overlay artifact exists and loads from `runtime/out_phase7/`.
2. The UI displays a Meaning + Move section only when the active frame has an entry.
3. The section shows:
   - a primary meaning
   - optional alternatives
   - 2–3 next move suggestions
4. If the overlay file is missing or a frame has no entry, the app still works normally.

## Architecture
5. No changes to Phase 6 runtime behavior.
6. No selector rewrite.
7. No engine flow rewrite.
8. No dependency on hidden runtime side effects.

## Product
9. At least 20 high-value entries exist in v1.
10. The guidance is practical, short, and uncertainty-aware.
11. The experience makes MandarinOS feel more like an interaction-support tool, not just a sentence trainer.

---

# 13. Non-goals for this phase

Do **not** do the following in Phase 12D:

- no live meeting assistant
- no ASR interpretation engine rewrite
- no personalization logic
- no automatic cultural coaching on every turn
- no deep scenario engine
- no move_type scoring changes
- no new conversation selector architecture
- no major schema redesign

This phase is only:
> a thin strategic overlay that changes perceived value and enables better alpha learning.

---

# 14. Recommended branch name

Suggested branch name:

`phase12d_meaning_move_overlay`

If branch naming must follow another convention, keep the wording close.

---

# 15. Recommended commit message

Suggested commit message:

`Phase 12D: add Meaning + Move overlay for ambiguous interaction support`

---

# 16. Suggested alpha test prompts

After implementation, test with prompts or frame paths that produce:
- hesitation
- soft refusal
- deferral
- weak agreement
- uncertainty

Observe:
- whether the overlay appears at the right time
- whether the user better understands the phrase
- whether the suggested next moves feel useful
- whether it reduces freeze / confusion

---

# 17. What success looks like

A successful Phase 12D does **not** mean MandarinOS has become a full cross-cultural operating system overnight.

It means alpha testers begin to feel:

- “This helps me interpret ambiguous responses”
- “This helps me decide what to do next”
- “This is helping me survive real interaction, not just learn sentences”

That is enough for this phase.

---

# 18. Cursor execution note

Please implement this as a **minimal-diff overlay**.

Use the existing MandarinOS governance rules:
- preserve Phase 6 runtime boundaries
- avoid rewriting stable architecture
- prefer additive content/UI changes
- keep changes easy to inspect and reversible

If there is architectural ambiguity, prefer:
- separate data artifact
- UI-level rendering
- fail-soft behavior

Do not expand scope beyond Phase 12D without explicit approval.
