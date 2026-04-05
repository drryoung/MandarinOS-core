# Bridge Audit — Slot Followup Preferences — April 2026

When a learner discloses a slot (e.g. says their JOB, CITY, HOBBY), the selector
consults `_SLOT_FOLLOWUP_PREFERENCES` in `ui_server.py` to pick the next frame.
This is the closest thing the system has to explicit "bridge" logic between topics.

The question to ask for each slot sequence:
**"If the learner just said X, is this the most natural first thing to follow up with?"**

---

## SLOT: CITY
*Triggered when: learner mentions a city (e.g. 我住在Dunedin)*

| # | Type | Frame ID | Chinese | English | Skip condition |
|---|------|----------|---------|---------|----------------|
| 1 | LOOP d2 | p2_pl_far | 离那儿远吗？ | Is it far from there? | city_is_well_known (BJ/SH/GZ) |
| 2 | EXTD d2 | p2_pl_ext1 | 每个地方都不一样。你觉得你住的地方有什么好的？ | What is good about where you live? | city_is_familiar |
| 3 | LOOP d2 | f_probe_place_moved | 你在那里住了多久了？ | How long have you lived there? | — |
| 4 | LOOP d2 | f_place_like_there | 你喜欢那儿吗？ | Do you like it there? | — |
| 5 | LOOP d1 | f_place_why_like | 为什么喜欢那儿？ | Why do you like it there? | — |
| 6 | LOOP d3 | p2_pl_4 | 住在{CITY}方便吗？ | Is it convenient living in [CITY]? | — |
| 7 | LOOP d3 | p2_pl_1 | 你觉得{CITY}生活怎么样？ | *(broken text_en)* | — |
| 8 | LOOP d3 | p2_pl_2 | {CITY}有什么好吃的？ | What good food is there in [CITY]? | — |

**Assessment:** Good sequence. Skip conditions are working correctly. The bridge from CITY slot → place engine questions is natural. #7 has a broken English translation but is otherwise fine.

---

## SLOT: JOB
*Triggered when: learner mentions a job (e.g. 我是老师)*

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | LOOP d2 | f_like_work | 你喜欢你的工作吗？ | Do you like your job? |
| 2 | LOOP d3 | p2_wk_1 | 你为什么喜欢这份工作？ | Why do you like this job? |
| 3 | LOOP d3 | p2_wk_2 | 这份工作难吗？ | Is this job hard? |
| 4 | LOOP d3 | p2_wk_3 | 你工作里最难的部分是什么？ | What is the hardest part of your work? |
| 5 | LOOP d3 | p2_wk_4 | 这份工作收入怎么样？ | Is this job well paid? |
| 6 | LOOP d3 | p2_wk_5 | 你推荐年轻人做这份工作吗？为什么？ | Do you recommend this job for young people? |

**Assessment:**
- Entry question #1 ("Do you like your job?") is the right first question — direct and natural.
- #3 and #4 both focus on difficulty — feels repetitive in sequence.
- #5 (salary) feels premature for small talk — better placed later or skipped.
- Missing: "你是怎么开始做这份工作的？" (`f_probe_work_origin`) — how did you get into it? — a much more interesting bridge into personal story than asking about salary.
- The new P1 frames `f_work_busy` ("工作忙吗？") and `f_work_where` ("你在哪儿工作？") are not in this list at all.

---

## SLOT: DISH
*Triggered when: learner mentions a specific food/dish*

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | LOOP d1 | f_food_why_good | 为什么好吃？ | Why is it good? |
| 2 | ASK  d2 | f_food_like_spicy | 你喜欢吃辣吗？ | Do you like spicy food? |
| 3 | LOOP d2 | f_food_famous_dish | 你们那儿最有名的菜是什么？ | What dish is your place most famous for? |
| 4 | LOOP d2 | f_food_expensive | 贵不贵？ | Is it expensive? |

**Assessment:**
- Entry question #1 ("Why is it good?") is excellent — immediate follow-through on what the learner just shared.
- #2 (spicy) is an odd pivot after asking why a specific dish is good — feels like changing subject.
- #3 asks for a famous dish immediately after the learner mentioned one — potentially redundant.
- #4 (expensive?) is a weak close — orphans `f_probe_food_make` and `f_probe_food_childhood` would be much more engaging.
- Suggested reorder: #1 → #3 → then personal angle (make it yourself? childhood memory?).

---

## SLOT: NAME
*Triggered when: learner reveals their name*

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | ASK  d1 | f_name_who_named | 谁给你取的名字？ | Who gave you your name? |
| 2 | LOOP d3 | p2_id_4 | 你觉得你的名字怎么样？ | What do you think of your name? |

**Assessment:**
- Only 2 frames — very short bridge. After the learner says their name, these two questions are a natural, warm sequence.
- #1 ("Who named you?") is good — personal and low-pressure.
- #2 ("What do you think of your name?") is a good evaluative follow-on.
- This is effectively the same as the identity engine FRAME_ORDER positions 3–6, so the two paths (slot-triggered vs engine-traversal) should not both fire — worth verifying no duplication occurs in practice.

---

## SLOT: FAMILY
*Triggered when: learner mentions a family member*

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | ASK  d2 | p2_fa_1 | 你跟家人住在一起吗？ | Do you live with your family? |
| 2 | ASK  d2 | f_have_siblings | 你有兄弟姐妹吗？ | Do you have any siblings? |
| 3 | ASK  d2 | f_married | 你结婚了吗？ | Are you married? |
| 4 | ASK  d2 | f_have_children | 你有孩子吗？ | Do you have children? |
| 5 | LOOP d3 | p2_fa_2 | 你多久见一次家人？ | How often do you see your family? |
| 6 | LOOP d3 | p2_fa_5 | 周末一般跟家人一起做什么？ | What do you do with family on weekends? |
| 7 | EXTD d2 | p2_fa_ext1 | 我觉得家人是最重要的。你最喜欢和家人一起做什么？ | I think family is the most important thing. What do you most enjoy doing with your family? |

**Assessment:**
- Same problem as in the engine audit: 4 binary yes/no questions in a row (#1–#4) feels like a census form.
- The EXTEND frame (#7) is placed at the END after all the binary questions — it would work much better as position 3 or 4 to break the interrogation streak.
- #5 and #6/7 cover very similar ground (how often do you see them / what do you do with them).
- The slot-triggered FAMILY sequence and the engine FRAME_ORDER for family are essentially identical — this means if the slot fires AND the engine activates, the learner could get the same questions twice.

---

## SLOT: STORY
*Triggered when: learner says something that implies a story*

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | LOOP d1 | f_generic_why | 为什么呢？ | Why is that? |

**Assessment:**
- Just one frame — a minimal generic prompt to continue. Appropriate as a safety net.
- Not really a "bridge" — just an open-ended invitation to elaborate.

---

## SLOT: TRAVEL
*Triggered when: learner mentions a place they've visited or want to visit*

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | LOOP d2 | f_travel_which_best | 哪个地方最有意思？ | Which place is most interesting? |
| 2 | LOOP d1 | f_travel_why_interesting | 为什么有意思？ | Why is it interesting? |
| 3 | ASK  d2 | f_want_go_where | 你想去哪里？ | Where do you want to go? |
| 4 | LOOP d3 | p2_tr_2 | 你最喜欢哪里？ | Where do you like best? |
| 5 | LOOP d3 | p2_tr_3 | 那个地方有什么好玩的？ | What's fun to do there? |
| 6 | LOOP d3 | p2_tr_4 | 你觉得那次旅行怎么样？ | *(broken text_en)* |

**Assessment:**
- Entry (#1/#2) is a good two-step: which place + why — natural and curious.
- #3 ("where do you want to go?") pivots from the past to the future — feels like a topic reset mid-sequence.
- #4 ("where do you like best?") overlaps heavily with #1 ("which is most interesting?") — two very similar ranking questions.
- `f_probe_travel_alone` ("你旅行的时候喜欢自己去还是跟人一起？") is orphaned but would be a much better social bridge than #3 or #4.
- #6 has a broken text_en.

---

## Cross-cutting issues

| Issue | Slots affected |
|-------|---------------|
| Binary question streaks (yes/no census feel) | FAMILY |
| Duplicate/overlapping questions within one slot | TRAVEL (#1 vs #4), DISH (#1 vs #3), FAMILY (#5 vs #6/7) |
| Salary question (too personal for small talk) | JOB (#5) |
| Broken text_en translations | CITY (#7), TRAVEL (#6) |
| Orphaned frames that are better than what's in the list | JOB (f_probe_work_origin), DISH (f_probe_food_make, f_probe_food_childhood), TRAVEL (f_probe_travel_alone) |
| Slot list and engine FRAME_ORDER diverge | FAMILY (same questions appear in both paths — risk of repetition) |
| New P1 frames not registered anywhere | f_work_busy, f_work_where (neither in FRAME_ORDER nor in JOB slot prefs) |

---

## How slot followup relates to engine FRAME_ORDER

The selector can reach the same frames via two different routes:
1. **Slot-triggered** — learner discloses a slot mid-conversation → `_SLOT_FOLLOWUP_PREFERENCES` fires
2. **Engine-traversal** — selector picks an engine topic → walks `_FRAME_ORDER`

If both routes are active, the learner may be asked the same question twice.
The deduplication mechanism is `recent_frame_ids` (already-asked frame tracking) —
but this only works if the frame IDs are identical in both lists, which they currently are
for CITY and FAMILY. Worth verifying this deduplication is reliable before extending.
