# Phase 10.5 — Full Conversation Simulation: BEFORE vs AFTER

**Purpose:** Simulate one MandarinOS conversation with **current** frames/options, then the **same** conversation with Phase 10.5 structure (move_type, option_role, curiosity activation, skeletons). Mark missing content; then analyse gaps.

**Sources:** `p1_frames.json`, `p2_frames.json`, `frame_options.runtime.json`, `ui_server.py` (_FRAME_ORDER, _BRIDGE_TARGETS, _OXYGEN_LOOP_PROBES). All frame IDs and option texts below exist in the repo unless marked `[MISSING]`.

---

# BEFORE (current system)

**Assumptions:** Selector uses identity → place (bridge from identity after name); options are exactly as in frame_options.runtime.json; no move_type/option_role; probe row appears only when `last_turn_was_answer` and server returns `probe_offer` (after a turn where user answered). Memory: empty at start; after name → learner_name set; after 我是新西兰人 → hometown set; after 我现在住在北京 → lives_in set; after 我是老师 → job_or_study set; after 有很多火锅 → favourite_food set.

---

**Turn 1 — Partner (ASK)**  
Frame: `f_ask_you_name`  
Text: 你叫什么名字？  
*Selector: first in identity order.*

**Turn 2 — User (answer)**  
Options shown: [ 我叫小明。, 我叫丽丽。, 我叫小红。 ]  
User selects: **我叫小明。**  
*Memory: learner_name = "小明".*

**Turn 3 — Partner (ASK)**  
Frame: `f_ask_name_meaning` (next in identity; dependency satisfied).  
Text: 你的名字是什么意思？  
*No “很高兴认识你” or “你呢？” in flow; selector goes to next ASK.*

**Turn 4 — User (answer)**  
Options: (frame_options for f_ask_name_meaning — typically word options or meaning slot).  
User selects: e.g. **我的名字意思是光明。** (if available) or a word option.  
*[Content may be word-level only; sentence option for “meaning” may be slot or missing.]*

**Turn 5 — Partner (ASK)**  
Selector: next identity = `p2_id_2` (大家一般怎么叫你？) or bridge. Assume **bridge to place** (identity has more frames but we simulate variety).  
Frame: `f_from_where`  
Text: 你是哪里人？

**Turn 6 — User (answer)**  
Options: [ 我是澳大利亚人。, 我是中国人。, 我是新西兰人。 ]  
User selects: **我是新西兰人。**  
*Memory: hometown = "新西兰".*

**Turn 7 — Partner (ASK)**  
Frame: `frame.location.live_question` (next in place order).  
Text: 你现在住哪里？  
*No partner REACTION (“新西兰很好”) or LOOP_QUESTION; direct next ASK.*

**Turn 8 — User (answer)**  
Options: [ 我现在住在广州。, 我现在住在北京。, 我现在住在上海。 ]  
User selects: **我现在住在北京。**  
*Memory: lives_in = "北京".*

**Turn 9 — Partner (ASK)**  
Frame: `f_place_like_there` (你喜欢那儿吗？) or next in place.  
Text: 你喜欢那儿吗？  
*Again no reaction to “北京”; straight to next question.*

**Turn 10 — User (answer)**  
Options: (e.g. 喜欢，很喜欢. or word options).  
User selects: **喜欢，很喜欢。**

**Turn 11 — Partner (ASK)**  
Selector: next place or bridge. Assume **bridge to work**.  
Frame: `f_what_work`  
Text: 你做什么工作？

**Turn 12 — User (answer)**  
Options: [ 我是工程师。, 我是老师。, 我是学生。 ]  
User selects: **我是老师。**  
*Memory: job_or_study = "老师".*

**Turn 13 — Partner (ASK)**  
Frame: `f_like_work` (你喜欢你的工作吗？).  
Text: 你喜欢你的工作吗？  
*No “老师很好” or loop; next ASK.*

**Turn 14 — User (answer)**  
User: **喜欢，我很喜欢。**

**Turn 15 — Partner (ASK)**  
Selector: bridge to food.  
Frame: `f_food_what_good`  
Text: 那儿有什么好吃的？ (or 有很多{DISH} question per frame text).

**Turn 16 — User (answer)**  
Options: [ 有很多包子。, 有很多饺子。, 有很多火锅。 ]  
User selects: **有很多火锅。**  
*Memory: favourite_food = "火锅".*

**Turn 17 — Partner (ASK)**  
Frame: `f_food_famous_dish` or next food.  
Text: (e.g. 最有名的菜是什么？)  
*No “火锅很好！” or “你喜欢辣吗？”; no probe row unless server sent probe_offer (implementation-dependent).*

---

**BEFORE summary:**  
~17 turns. Flow is strictly **ASK → user answer → next ASK** (or bridge). No REACTION, no RECIPROCITY (“你呢？”), no partner LOOP_QUESTION. Options are **all minimal** (no extend, no reciprocate, no repair in list). Probe row (为什么？, 哪里？, 怎么样？) may appear after some answers but is **not** structurally guaranteed; no engine/slot-specific curiosity set. Transitions feel mechanical: answer → next question with no acknowledgment or follow-up on what was said.

---

# AFTER (Phase 10.5 structure)

**Same conversational intent:** name → name meaning → place (from → live → like) → work (what → like) → food (what’s good). Now with move_type, option_role, curiosity triggers, skeletons, max_curiosity_depth = 2, oxygen selection.

---

**Turn 1 — Partner (ASK, core)**  
Frame: `f_ask_you_name`  
move_type: ASK | question_type: core  
Text: 你叫什么名字？  
Skeleton: ASK → ANSWER.

**Turn 2 — User (answer)**  
Options (with option_role):  
- 我叫小明。 (minimal)  
- [MISSING] 我叫小明，我来自上海。 (extend)  
- [MISSING] 我叫小明，你呢？ (reciprocate)  
- [MISSING] 不好意思，可以再说一次吗？ (repair)  
- [MISSING] 为什么？ / 怎么样？ (curiosity — identity context)  
User selects: **我叫小明。** (minimal).  
*Memory: learner_name = "小明". Trigger: new info in memory → curiosity_triggered = true. curiosity_depth = 0.*

**Turn 3 — Partner (REACTION preferred; then ASK if no reaction frame)**  
Skeleton: ASK → ANSWER_MIN → [REACTION | RECIPROCITY] or next ASK.  
Existing frame: `f_nice_to_meet` (很高兴认识你。) — can serve as REACTION.  
Partner: **很高兴认识你。**  
move_type: REACTION.  
*curiosity_depth still 0 (REACTION doesn’t count).*  
User curiosity options (oxygen selection, identity): [MISSING] e.g. 怎么样？, 为什么？ (1–2 options). If present, user could tap 怎么样？ → stub.

**Turn 4 — Partner (ASK, treasure)**  
Skeleton continues: next ASK.  
Frame: `f_ask_name_meaning`  
move_type: ASK | question_type: treasure  
Text: 你的名字是什么意思？

**Turn 5 — User (answer)**  
Options: [existing word/slot options] + [MISSING] extend/reciprocate/repair/curiosity.  
User selects: e.g. **我的名字意思是光明。** (minimal/slot).

**Turn 6 — Partner (bridge)**  
Skeleton: transition to new topic.  
Frame: `f_from_where`  
move_type: ASK | question_type: core (place)  
Text: 你是哪里人？

**Turn 7 — User (answer)**  
Options:  
- 我是新西兰人。 (minimal)  
- [MISSING] 我是新西兰人，我住在北京。 (extend)  
- [MISSING] 新西兰。你呢？ (reciprocate)  
- [MISSING] repair / curiosity (place: 怎么样？, 哪里？)  
User selects: **我是新西兰人。**  
*Trigger: slot NATIONALITY + memory hometown updated. curiosity_triggered = true. curiosity_depth = 0.*

**Turn 8 — Partner (curiosity move or REACTION)**  
Prefer: LOOP_QUESTION or REACTION.  
[MISSING] Partner LOOP_QUESTION frame for “新西兰” (e.g. “你喜欢新西兰吗？”).  
Existing: `f_place_reaction` (很好！) — REACTION.  
Partner: **很好！**  
move_type: REACTION.  
User curiosity options (place, nationality): [MISSING] 怎么样？, 哪里？ (oxygen selection).  
*If user taps curiosity (e.g. 怎么样？), curiosity_depth = 1; partner stub.*

**Turn 9 — Partner (ASK, core)**  
Frame: `frame.location.live_question`  
move_type: ASK | question_type: core  
Text: 你现在住哪里？

**Turn 10 — User (answer)**  
Options: [ 我现在住在广州。, 我现在住在北京。, 我现在住在上海。 ] (all minimal) + [MISSING] extend/reciprocate/repair/curiosity.  
User selects: **我现在住在北京。**  
*Trigger: slot CITY + lives_in updated. curiosity_triggered = true. curiosity_depth = 0.*

**Turn 11 — Partner (curiosity move)**  
Prefer: LOOP_QUESTION or REACTION.  
Existing: `p2_pl_1` (你觉得{CITY}生活怎么样？) — can be LOOP_QUESTION if filled with 北京.  
Partner: **你觉得北京生活怎么样？**  
move_type: LOOP_QUESTION.  
*curiosity_depth = 1.*  
User curiosity options (place, CITY): 怎么样？, 方便吗？ [MISSING — need engine/slot→oxygen map].  
User does not tap curiosity.

**Turn 12 — User (answer)**  
Options for p2_pl_1: [sentence or word options]. User: **挺好的。**

**Turn 13 — Partner (curiosity move or transition)**  
curiosity_depth = 1; max = 2 → one more curiosity move allowed.  
Option A: REACTION (“北京很好”) then transition.  
Option B: Next ASK (你喜欢那儿吗？).  
Partner: **你喜欢那儿吗？** (f_place_like_there) — ASK, not LOOP.  
*Skeleton: transition back to ASK. curiosity_depth reset when new ASK sent.*

**Turn 14 — User:** **喜欢，很喜欢。**

**Turn 15 — Partner (bridge)**  
Frame: `f_what_work`  
Text: 你做什么工作？

**Turn 16 — User (answer)**  
Options: [ 我是工程师。, 我是老师。, 我是学生。 ] + [MISSING] extend/reciprocate/repair/curiosity.  
User selects: **我是老师。**  
*Trigger: slot JOB + job_or_study updated. curiosity_triggered = true.*

**Turn 17 — Partner (REACTION or LOOP_QUESTION)**  
[MISSING] “老师很好！” or “忙吗？” (LOOP).  
Existing: `f_like_work` (你喜欢你的工作吗？) — ASK.  
Partner: **你喜欢你的工作吗？** (fallback ASK).  
*curiosity_depth = 0 (we treat this as new ASK).*  
User curiosity options (work): [MISSING] 怎么样？, 忙吗？

**Turn 18 — User:** **喜欢，我很喜欢。**

**Turn 19 — Partner (bridge)**  
Frame: `f_food_what_good`  
Text: 那儿有什么好吃的？

**Turn 20 — User (answer)**  
Options: [ 有很多包子。, 有很多饺子。, 有很多火锅。 ] + [MISSING] extend/reciprocate/repair/curiosity.  
User selects: **有很多火锅。**  
*Trigger: slot DISH + favourite_food. curiosity_triggered = true. curiosity_depth = 0.*

**Turn 21 — Partner (curiosity move)**  
Prefer: LOOP_QUESTION or REACTION.  
[MISSING] “火锅很好！” (REACTION) or “你喜欢辣吗？” (LOOP_QUESTION).  
Existing: persona stub for 为什么？ (e.g. “嗯，因为我很喜欢火锅。”) only if **user** taps 为什么？.  
Partner: [MISSING] REACTION frame for food. Fallback: next ASK **f_food_famous_dish**.  
Partner: (e.g. 最有名的菜是什么？) — ASK.  
*With Phase 10.5 content: partner would say “火锅很好！” or “你喜欢辣吗？”; then offer user curiosity (为什么？, 喜欢辣吗？); after 1–2 curiosity moves, force next ASK.*

---

**AFTER summary:**  
Same ~17–21 turns in intent. **Improvements:** REACTION after name (很高兴认识你); REACTION after 新西兰 (很好！); LOOP_QUESTION after 北京 (你觉得北京生活怎么样？); option_roles would add minimal + extend + reciprocate + repair + curiosity per question. **Missing content:** extend/reciprocate/repair/curiosity options for most frames; partner REACTION/LOOP_QUESTION frames for many topics; engine/slot→oxygen curiosity list; so some “AFTER” steps fall back to current behaviour or show [MISSING].

---

# GAP ANALYSIS

## 1) Unnatural transitions (BEFORE)

| Where | Issue |
|-------|--------|
| After “我叫小明。” | No “很高兴认识你” or “你呢？”; system goes straight to “你的名字是什么意思？”. Feels like an interview, not a greeting. |
| After “我是新西兰人。” | No “新西兰很好” or “你喜欢新西兰吗？”; next is “你现在住哪里？”. No acknowledgment of origin. |
| After “我现在住在北京。” | No “北京很好” or “你觉得北京怎么样？”; next is “你喜欢那儿吗？”. Slight link but no explicit reaction to “北京”. |
| After “我是老师。” | No “老师很好” or “忙吗？”; next is “你喜欢你的工作吗？”. Again no reaction to the fact. |
| After “有很多火锅。” | No “火锅很好！” or “你喜欢辣吗？”; next is next food question. No loop on the dish. |

**AFTER (with Phase 10.5):** REACTION or LOOP_QUESTION inserted after these answers when curiosity_triggered; skeleton ASK → ANSWER → [REACTION | LOOP_QUESTION] then next ASK. Transitions become: answer → acknowledge/loop → then new question or bridge.

---

## 2) Missing option roles (BEFORE)

| Frame | Current options | Missing option_role |
|-------|----------------|---------------------|
| f_ask_you_name | 我叫小明。/丽丽/小红 | extend (我叫小明，我来自X); reciprocate (我叫小明，你呢？); repair (再说一次); curiosity (为什么？/怎么样？) |
| f_from_where | 我是澳大利亚/中国/新西兰人 | extend, reciprocate, repair, curiosity |
| frame.location.live_question | 广州/北京/上海 | extend (住北京，工作也在); reciprocate, repair, curiosity |
| f_what_work | 工程师/老师/学生 | extend, reciprocate, repair, curiosity |
| f_food_what_good | 包子/饺子/火锅 | extend, reciprocate, repair, curiosity |

**BEFORE:** Every question has only **minimal** (and sometimes one slot variant). No way to “add a bit more” (extend), “turn it back” (reciprocate), “ask for help” (repair), or “ask back” (curiosity) from the same screen.

**AFTER:** Each question would offer ≥3 strategies (minimal, extend, reciprocate or repair or curiosity). Content for extend/reciprocate/repair/curiosity is largely [MISSING] in current frames; schema and behaviour are defined, options need to be added or generated from templates.

---

## 3) Lack of loop questions (BEFORE)

| After user said | Desired partner loop | Current |
|-----------------|----------------------|---------|
| 我叫小明 | (你的名字) 怎么样？/ 为什么叫这个？ | Next is f_ask_name_meaning (different question). |
| 我是新西兰人 | 你喜欢新西兰吗？/ 新西兰怎么样？ | Next is frame.location.live_question. |
| 我现在住在北京 | 你觉得北京生活怎么样？ | Next is f_place_like_there (generic “那儿”). |
| 我是老师 | 忙吗？/ 工作怎么样？ | Next is f_like_work. |
| 有很多火锅 | 你喜欢辣吗？/ 为什么喜欢火锅？ | Next is f_food_famous_dish. |

**BEFORE:** Selector has no notion of “loop on what user just said.” It only picks the **next frame in _FRAME_ORDER** or bridge. So loop-style questions (你觉得北京生活怎么样？, 你喜欢辣吗？) exist as frames but are **not** chosen as immediate follow-ups to the relevant answer; they appear later or in a different order.

**AFTER:** When curiosity_triggered and depth &lt; max, selector **prefers** move_type = LOOP_QUESTION (or REACTION). Frames tagged LOOP_QUESTION and filled with current topic (e.g. 北京, 火锅) would be selected. **Gap:** Many such frames need to exist and be tagged; some (e.g. “你喜欢辣吗？”) exist in food, but “北京生活怎么样？” is p2_pl_1 (slot CITY) — needs to be used as LOOP_QUESTION after “住在北京.”

---

## 4) Oxygen vocabulary gaps (BEFORE)

| Need | Current |
|------|--------|
| User can say 为什么？, 怎么样？, 哪里？ after answer | Probe row (oxygen probes) appears only when server sends probe_offer (after “interesting” answer); not guaranteed; same set for all contexts. |
| Context-specific curiosity | No engine/slot→oxygen mapping. So 为什么？, 哪里？, 怎么样？ are generic. |
| Repair in flow | 什么？, 再说一次, 慢一点 are in recovery UI, not in main option list. |
| Connection words (所以, 因为, 但是) | In content but not tagged as oxygen; no prioritisation or reuse. |

**BEFORE:** Oxygen exists in content and in _OXYGEN_LOOP_PROBES, but (1) not structurally offered after every “interesting” answer, (2) not filtered by engine/slot, (3) repair is separate from answer options.

**AFTER:** option_role curiosity + oxygen selection rules (engine/slot → subset) give context-appropriate “ask back” options (e.g. food → 为什么？, 喜欢辣吗？; place → 怎么样？, 方便吗？). Repair can be one of the option_roles in the same list. **Gap:** Oxygen list and engine/slot→option mapping need to be defined and wired; current frames don’t expose option_role.

---

# Summary table

| Gap type | BEFORE | AFTER (structure) | Content status |
|----------|--------|--------------------|----------------|
| Unnatural transitions | ASK → answer → next ASK only | Skeleton: ASK → ANSWER → [REACTION \| LOOP_QUESTION] → ASK | REACTION/LOOP frames exist for some topics; need tagging and selector preference. |
| Missing option roles | All options minimal | minimal + extend + reciprocate + repair + curiosity per question | extend/reciprocate/repair/curiosity options mostly [MISSING]. |
| Lack of loop questions | Next frame by order only | Prefer LOOP_QUESTION when curiosity_triggered; max_curiosity_depth cap | Some loop-like frames exist (p2_pl_1, f_food_like_spicy); need move_type and slot fill. |
| Oxygen gaps | Generic probes when offered; repair separate | engine/slot→curiosity options; repair in option list | Oxygen list exists; mapping and option_role tagging [MISSING]. |

---

**Conclusion:** The BEFORE simulation shows a strictly linear question–answer chain with no acknowledgment or follow-up. The AFTER simulation uses the same existing frames where possible but structures them with move_type, option_role, curiosity triggers, and skeletons; it exposes **where content is missing** (extend/reciprocate/repair/curiosity options; some REACTION/LOOP frames; engine/slot→oxygen map). Implementing Phase 10.5 behaviour will make conversations more natural; filling the [MISSING] content will require adding options and tagging frames.
