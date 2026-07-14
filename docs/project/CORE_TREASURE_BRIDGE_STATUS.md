<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class E: Dated report or historical evidence**
>
> - **Current use:** Retained as a dated status report for the Core Treasure bridge work.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current bridge-related code, applicable tests, and the relevant R2 contracts.
> - **Principal caution:** The report describes status at a past point in development. It does not prove that the bridge, its interfaces, or its reported limitations remain unchanged.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Core → treasure → bridge: current behaviour vs later stage

**Question:** Is a conversation now able to start with a core question, try a few treasure questions, and then bridge to another topic? Or is this feature to be implemented at a later stage?

**Update:** Bridge is now (1) **available as an option** whenever the user wants it (“Change topic” button), (2) **automatic** when the user exhausts the current topic (no more unseen questions in that engine), and (3) **automatic** when the user uses recovery phrases that indicate difficulty (e.g. “next_turn” / 我们聊点简单的吧) — in that case the next turn prefers bridging to another topic.

---

## What works today

1. **Start with a core-like question**  
   The first question in each engine is the first in `_FRAME_ORDER` (e.g. 你叫什么名字？ for identity, 你是哪里人？ for place, 那儿有什么好吃的？ for food). So the conversation does start with what the specs call a “core” question.

2. **Ask several questions in the same engine**  
   The selector stays in the same engine and picks the next **unseen** question in the fixed order (Tier 1). So you get a sequence like: core → next in order → next → … Those later ones effectively play the role of “treasure” and “loop” in the spec, but they are **not** tagged as core/treasure/loop.

3. **Bridge to another topic**  
   When there are **no more unseen partner-question frames** in the current engine (all have been used), the selector **bridges** to another engine (Tier 2) and chooses the first unseen question there. So the conversation does move to a new topic after using up the current one.

So in practice: **yes**, a conversation can start with a core-like question, go through several more in that engine (including treasure-like ones), and **then** bridge. Bridge happens in three ways:

1. **User option:** The user can click **“Change topic”** at any time (e.g. after an interesting answer). The server then tries to bridge first (`prefer_bridge`); if a bridge target exists, the next question is from another topic.
2. **Exhaustion:** When every partner-question frame in the current engine has been used, the selector automatically bridges to another engine.
3. **Recovery (too hard):** When the user selects a recovery phrase with `recovery_action: "next_turn"` (e.g. 我们聊点简单的吧, or after several “not understood” moves), the next request sends `prefer_bridge: true`, so the next question is from another topic instead of continuing in the same (hard) one.

---

## What is not implemented yet (later stage)

- **Explicit core / treasure / loop**  
  Frames do not have a `question_type` (or similar) field. The Phase 9 Content & Engines Plan (“3. Richer engine logic”) calls for:
  - Adding `question_type` (e.g. `"core"`, `"treasure"`, `"loop"`, `"bridge"`) to the frame schema.
  - Tagging frames from the engine specs/ladders.
  - Ordering in the selector by type: core → treasure → loop (and optionally treating bridge as transition).

- **Bridge after “a few” treasure questions**  
  Right now we **only** bridge when the current engine is **exhausted**. We do **not**:
  - Bridge after a fixed number of turns (e.g. “after 3–5 questions”).
  - Bridge based on energy, stall, or “natural bridge” (those are in the full Next Question Selector spec for later).

So the **richer** behaviour — explicit core/treasure/loop and the option to bridge *before* exhausting the engine — is the “question type and selector ordering” work planned for a **later stage** (Phase 9 Content & Engines Plan, step 3).

---

## Summary

| Feature | Status |
|--------|--------|
| Start with a core-like question | ✅ Yes (first in engine order) |
| Ask several questions in same engine (treasure-like) | ✅ Yes (ordered list, no type tags) |
| Bridge to another topic | ✅ Yes, but **only when current engine is exhausted** |
| Explicit core/treasure/loop tags and ordering | ❌ Later (question_type + selector) |
| Bridge after a few treasure questions (before exhausting) | ❌ Later (richer engine logic / full selector) |

So: the flow “core → a few more (treasure-like) → then bridge” works **if** “then” means “after we’ve asked every question in that engine”. Doing “a few treasure then bridge” *without* exhausting the engine is planned for a later stage.
