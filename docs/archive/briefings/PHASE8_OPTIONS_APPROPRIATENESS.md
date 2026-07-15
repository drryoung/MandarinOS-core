# Phase 8 — Option appropriateness: now vs Phase 9

**Question:** Can we make response options appropriate to the question now, or should we wait for Phase 9 (engine integration)?

---

## Current behaviour

- **Gold option:** Comes from `option_tokens[0]` in each frame (e.g. in `p1_frames.json`). That’s the intended “correct” answer for the frame.
- **Distractors:** The builder (`tools/build_runtime_artifacts.py`) picks **two random cards** from the whole deck (excluding the gold). So for “你叫什么名字？” you might get the gold plus two unrelated words (e.g. 北京, 喜欢) — not plausible answers to “What’s your name?”.

So “inappropriate” is mainly: **distractors are random**, and sometimes the **gold** is a single word that’s part of an answer (e.g. 叫) rather than a full answer (e.g. 我叫小明).

---

## Option 1: Resolve in Phase 8 (recommended)

**No engine needed.** We can make options more appropriate by changing only **data** and **builder**:

1. **Builder: optional `distractor_tokens` per frame**  
   In `p1_frames.json` / `p2_frames.json`, allow an optional list, e.g. `distractor_tokens: ["w_mingzi", "w_shenme"]`. If present, the builder uses those two as the distractors instead of random. Curators then define two *plausible wrong answers* per frame (e.g. for “What’s your name?” → “什么”, “名字” or other name-related wrong answers).

2. **Data: improve gold where needed**  
   For question frames, set `option_tokens[0]` to a card that is a **plausible full answer** (e.g. a “我叫X” style card if it exists), or at least a word that reads as an answer. That’s a content/curation pass on the frame files.

**Pros:** Appropriate options without the engine; transcript and conversation feel coherent in Phase 8.  
**Cons:** Builder and frame data are touched; curation effort per frame.

---

## Option 2: Delay to Phase 9

**Engine supplies or selects options.** In Phase 9 the conversation engine (Next Question Selector, etc.) can return for each turn not only the next question but also the set of options (e.g. one gold + two plausible distractors). The UI would then show whatever the engine returns instead of (or on top of) the static runtime options.

**Pros:** No builder change now; option quality becomes the engine’s job; can be adaptive (e.g. by user level).  
**Cons:** In Phase 8 the conversation can still feel broken (random distractors); engine work is required before options improve.

---

## Recommendation

- **Resolve in Phase 8** with the minimal builder + data change above:
  - Add optional `distractor_tokens` and use it in the builder when present.
  - Optionally curate `option_tokens` (gold) for question frames so the gold is a proper answer.
- **Phase 9** can later add engine-driven option selection (e.g. engine returns options per turn) and optionally override or replace the static set.

That way options become appropriate as soon as we add and fill `distractor_tokens` (and fix gold where needed), without blocking on engine integration.

---

*Next step:* If you want to do it now, the programmer can add `distractor_tokens` support in the builder and document the frame schema so curators can start filling plausible distractors per frame.
