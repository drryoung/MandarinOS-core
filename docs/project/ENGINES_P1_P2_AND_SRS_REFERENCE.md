# Conversation engines, P1/P2, and how SRS fits

**Purpose:** Clarify the full set of conversation engines from the design, what is implemented today, how P1/P2 relate to engines, and where SRS ties in.  
**References:** CONVERSATION_ARCHITECTURE_INDEX.md, MandarinOS_engine_specs_v1.md, mandarinos_food_engine_v1.md, p1_frames.json, p2_frames.json, scripts/ui_server.py.

---

## 1. The seven engines (from the design)

The conversation architecture defines **seven topic engines**:

| # | Engine       | Spec / notes |
|---|--------------|--------------|
| 1 | **Identity** | Name, 你呢？, name meaning; entry engine; bridges to Place, Family, Study/Work |
| 2 | **Place**    | 哪里人, 住哪儿, 喜欢那儿吗； entry + hub; bridges to Food, Travel, Family |
| 3 | **Food**     | 那儿有什么好吃的？, 喜欢辣吗？, famous dish, taste; secondary; bridges to Place, Travel |
| 4 | **Family**   | 家人吗？, 兄弟姐妹； secondary; bridges to Place, Study/Work |
| 5 | **Study/Work** | 你做什么工作？, 喜欢工作吗？; secondary; bridges to Place, Family |
| 6 | **Travel**   | 你去过哪里？, 你想去哪里？; secondary; bridges to Place, Food |
| 7 | **Interests**| 你有什么爱好？, 周末做什么？; secondary; bridges to Travel, Food, Family, Work |

**Sources:** CONVERSATION_ARCHITECTURE_INDEX.md (§2), MandarinOS_engine_specs_v1.md, mandarinos_food_engine_v1.md, mandarinos_interests_engine_v1.md.

---

## 2. What is in the repo today (frames + selector)

**Frame data** (p1_frames.json, p2_frames.json) tags each frame with an **engine** string. The values used in data are:

| Design engine | In data (frame tag) | Implemented? |
|---------------|---------------------|--------------|
| Identity      | `identity`          | Yes |
| Place         | `place`             | Yes |
| **Food**      | `food`              | Yes (P1: 那儿有什么好吃的？, 最有名的菜, 喜欢吃辣吗？, 好吃吗？, 贵不贵？) |
| Family        | `family`            | Yes |
| Study/Work    | `work`              | Yes (as `work`) |
| Travel        | `travel`            | Yes |
| Interests     | `hobby`             | Yes (as `hobby`) |
| —             | `life`              | Yes (P2-only; daily life / planning) |

So the **core six** plus **Food** are present: **Interests** is implemented as **hobby** (with P1 follow-ups, cultural 你喜欢中国文化吗？/你喜欢什么？, and collecting 你收藏什么吗？). **Food** is implemented with P1 frames and is in `_BRIDGE_TARGETS` and `_FRAME_ORDER`.

**Selector (scripts/ui_server.py):**  
`_BRIDGE_TARGETS` and `_FRAME_ORDER` list: identity, place, family, work, hobby, travel, **food**, life.

---

## 3. P1 and P2: content phases, not engines

**P1** and **P2** are **content phases** (vocabulary/sentence sets), not engines:

- **P1** = survival sentence frames (p1_frames.json, p1_fillers.json). Example: 你叫什么名字？, 你是哪里人？, 你有家人吗？, 你做什么工作？, 你有什么爱好？, 你去过哪里？.
- **P2** = daily life / deeper frames (p2_frames.json, p2_fillers.json). Example: 你平时喜欢去{PLACE}吗？, 你周末做什么？, planning/story frames.

Each **frame** has both:

- A **phase** (which file it lives in: P1 or P2), and  
- An **engine** (topic tag: identity, place, family, work, hobby, travel, life).

The **Next Question Selector** and bridge logic use the **engine** tag to group frames and decide “same engine” vs “bridge to another engine”. P1/P2 are only relevant for **which frames exist** and for **builders** that merge or separate content by phase; they do not change how the selector chooses the next question.

So: **engines** = topic modules for conversation flow; **P1/P2** = where the frames and fillers live and how “survival” vs “daily life” is organised.

---

## 4. Adding the Food engine (and any other engines)

To add **Food** (or another specified engine):

1. **Frames:** Add frames with `"engine": "food"` to p1_frames.json (and/or p2_frames.json). Use the Food spec for Core/Treasure/Loop questions (e.g. 那儿有什么好吃的？, 你们那儿最有名的菜是什么？, 你喜欢吃辣吗？).
2. **Fillers:** Add any needed fillers (e.g. dish names, taste words) to p1_fillers.json / p2_fillers.json.
3. **Bridge map:** In `scripts/ui_server.py`, add `"food"` to `_BRIDGE_TARGETS` (e.g. place → food, travel → food, identity → food) and to `_FRAME_ORDER` for a sensible question order within the food engine.
4. **Sentence options:** If a question frame has a slotted answer frame (e.g. “我喜欢吃{DISH}。”), add the question→answer mapping in `QUESTION_FRAME_SENTENCE_OPTIONS` in `tools/build_runtime_artifacts.py` and ensure fillers exist.
5. **Build:** Run the runtime builder and verify frame_options and tokens for the new frames.

The same pattern applies for any other engine that is specified but not yet in frame data (e.g. a future “Daily life” or “Planning” engine beyond the current `life` tag).

---

## 5. How SRS ties in (high level)

- **SRS** (spaced repetition) operates on **words/phrases** (cards, vocabulary). It does not “know” about engines directly; the link is:
  - **Frames** use **words** (option_tokens, distractor_tokens, slotted fillers). When we run a conversation, we are effectively “using” vocabulary that could be scheduled by the SRS.
  - The **Next Question Selector** spec includes **learning constraints** (e.g. “anchor phrases due”, “vocabulary budget”). When we implement that, the selector could take **SRS “due” data** as input and prefer questions that surface due items (or avoid overloading with too many due items at once).

- **P1/P2** affect SRS only in the sense that they define **which sentences and words** exist; SRS might schedule those words. Engine tags affect SRS only when we add **engine-aware learning constraints** (e.g. “today we want to reinforce Place vocabulary” or “due items in the current engine”).

So: **SRS** ↔ **vocabulary/phrases**; **engines** ↔ **conversation topics**; **P1/P2** ↔ **content sets**. They tie together when we feed SRS due data into the selector (Phase 10 or later).

---

## 6. Summary

| Question | Answer |
|----------|--------|
| **How many engines in the design?** | **Seven:** Identity, Place, Food, Family, Study/Work, Travel, Interests. |
| **What’s in frame data today?** | Identity, place, family, work, hobby (= Interests), travel, life. **Food** is **not** in frames or in the selector. |
| **P1 vs P2?** | **Content phases:** P1 = survival frames, P2 = daily life frames. Both supply frames; each frame has an **engine** tag. Selector uses engine, not P1/P2. |
| **SRS and engines / P1–P2?** | SRS schedules **vocabulary**; engines are **topics**. They tie in when we pass SRS “due” data into the selector as **learning constraints** (Phase 10+). |

---

*Created 2026-03-12. Update when Food (or other engines) are added to frames and bridge map.*
