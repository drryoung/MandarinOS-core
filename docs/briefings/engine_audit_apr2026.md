<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class E: Dated report or historical evidence**
>
> - **Current use:** Retained as the April 2026 audit of conversation engines and related behaviour.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current engine, frame, selector, and routing code together with `docs/CONVERSATION_ARCHITECTURE.md`.
> - **Principal caution:** Historical engine findings do not establish current engine inventory, routing, progression, or behavioural correctness.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Engine Audit — April 2026

Generated from `_FRAME_ORDER` in `ui_server.py` + `p1_frames.json` + `p2_frames.json`.

Legend: `[OPEN]` = first question in engine · `[ASK]` = factual question · `[LOOP]` = follow-up · `[EXTD]` = partner self-disclosure + question · `d1/d2/d3` = difficulty

---

## ENGINE 1: IDENTITY (8 frames)

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | OPEN d1 | f_ask_you_name | 你叫什么名字？ | What's your name? |
| 2 | LOOP d3 | p2_id_2 | 大家一般怎么叫你？ | What do people usually call you? |
| 3 | LOOP d2 | f_ask_name_meaning | 你的名字是什么意思？ | What does your name mean? |
| 4 | EXTD d2 | p2_id_ext1 | 我觉得名字很有意思。给你取名字的时候有什么故事吗？ | I think names are really interesting. Was there a story when your name was chosen? |
| 5 | LOOP d1 | f_name_story_elicit | 哦，是什么故事？ | Oh, what's the story? ← follow-up to #4 |
| 6 | LOOP d3 | p2_id_4 | 你觉得你的名字怎么样？ | What do you think of your name? |
| 7 | LOOP d3 | p2_id_5 | 这个名字有故事吗？ | Does this name have a story? ← **DUPLICATE of #4** |
| 8 | ASK  d2 | f_how_old | 你多大了？ | How old are you? |

### Warnings
- **#7 duplicates #4** — both ask about a name story. `p2_id_5` was recently rewritten but landed on the same topic as `p2_id_ext1`.
- **Orphans** (in JSON, tagged identity, NOT in FRAME_ORDER):
  - `f_probe_id_like_name`: 你喜欢自己的名字吗？
  - `f_probe_id_nickname`: 家里人是怎么叫你的？
  - `f_probe_id_character`: 你觉得名字好听吗？
  - `p2_id_1`: 我的名字有意思，因为{REASON_POS}。
  - `p2_id_3`: 我平时比较{STYLE}。
- Age (#8) feels like an abrupt topic jump after a name story thread.

### Suggested fix
Replace #7 (`p2_id_5`) with **"你有小名吗？"** (Do you have a nickname? — HSK2). Natural follow-on from the name conversation; pulls in the `f_probe_id_nickname` concept.

---

## ENGINE 2: PLACE (11 frames)

| # | Type | Frame ID | Chinese | English | Skip condition |
|---|------|----------|---------|---------|----------------|
| 1 | OPEN d2 | f_from_where | 你是哪里人？ | Where are you from? | — |
| 2 | ASK  d2 | frame.location.live_question | 你现在住哪里？ | Where do you live now? | — |
| 3 | LOOP d2 | p2_pl_far | 离那儿远吗？ | Is it far from there? | city_is_well_known (BJ/SH/GZ) |
| 4 | EXTD d2 | p2_pl_ext1 | 每个地方都不一样。你觉得你住的地方有什么好的？ | Every place is different. What is good about where you live? | city_is_familiar |
| 5 | LOOP d2 | f_probe_place_moved | 你在那里住了多久了？ | How long have you lived there? | — |
| 6 | LOOP d2 | f_place_like_there | 你喜欢那儿吗？ | Do you like it there? | — |
| 7 | LOOP d1 | f_place_why_like | 为什么喜欢那儿？ | Why do you like it there? | — |
| 8 | LOOP d3 | p2_pl_4 | 住在{CITY}方便吗？ | Is it convenient living in [CITY]? | — |
| 9 | LOOP d3 | p2_pl_1 | 你觉得{CITY}生活怎么样？ | *(broken text_en — word-by-word)* | — |
| 10 | LOOP d3 | p2_pl_2 | {CITY}有什么好吃的？ | *(broken text_en — word-by-word)* | — |
| 11 | LOOP d3 | p2_pl_3 | 你平时喜欢去{PLACE}吗？ | *(broken text_en — word-by-word)* | — |

### Warnings
- Positions 9–11 have broken `text_en` (tokenised word-by-word, not translated). Low priority (not learner-facing) but messy.
- **Orphans:**
  - `f_probe_place_why_move`: 你为什么选择住在那里？
  - `f_probe_place_miss`: 你会想念老家吗？
  - `f_probe_place_stay`: 你打算在那里长期住下去吗？
  - `p2_pl_5`: 我觉得{CITY}{REASON_POS}。

### Assessment
Sequence is otherwise solid. Skip conditions working correctly. No critical fixes needed.

---

## ENGINE 3: FAMILY (8 frames)

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | OPEN d2 | f_have_family | 你有家人吗？ | Do you have family? |
| 2 | ASK  d2 | p2_fa_1 | 你跟家人住在一起吗？ | Do you live with your family? |
| 3 | ASK  d2 | f_have_siblings | 你有兄弟姐妹吗？ | Do you have any siblings? |
| 4 | ASK  d2 | f_married | 你结婚了吗？ | Are you married? |
| 5 | ASK  d2 | f_have_children | 你有孩子吗？ | Do you have children? |
| 6 | EXTD d2 | p2_fa_ext1 | 我觉得家人是最重要的。你最喜欢和家人一起做什么？ | I think family is the most important thing. What do you most enjoy doing with your family? |
| 7 | LOOP d3 | p2_fa_2 | 你多久见一次家人？ | How often do you see your family? |
| 8 | LOOP d3 | p2_fa_5 | 周末一般跟家人一起做什么？ | What do you do with family on weekends? — **near-duplicate of #6** |

### Warnings
- **5 yes/no questions in a row (positions 1–5)** — feels like a form / interrogation, not a conversation. Learner only says 有/没有 five times.
- **#8 near-duplicates #6** — both ask what you do with family.
- **Orphans:**
  - `f_probe_family_closest`: 你和家里谁最亲近？  ← richer than several yes/no questions
  - `f_probe_family_together`: 你们最喜欢一起做什么？
  - `f_probe_family_influence`: 家里谁对你最重要？
  - `f_efc_family_work`, `f_efc_family_age`, `f_efc_family_where`, `f_efc_family_married`, `f_efc_family_child` (slot-based follow-ups)

### Suggested fix
- Move EXTEND (#6) to position 3 to break the binary streak earlier.
- Replace #8 (`p2_fa_5`) with `f_probe_family_closest` ("你和家里谁最亲近？").

---

## ENGINE 4: WORK (8 frames)

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | OPEN d2 | f_what_work | 你做什么工作？ | What do you do for work? |
| 2 | LOOP d2 | f_like_work | 你喜欢你的工作吗？ | Do you like your job? |
| 3 | LOOP d3 | p2_wk_1 | 你为什么喜欢这份工作？ | Why do you like this job? |
| 4 | LOOP d3 | p2_wk_2 | 这份工作难吗？ | Is this job hard? |
| 5 | EXTD d2 | p2_wk_ext1 | 工作有时候挺累的。你喜欢你的工作吗？ | Work can be tiring. Do you like your work? — **EXACT DUPLICATE of #2** |
| 6 | LOOP d3 | p2_wk_3 | 你工作里最难的部分是什么？ | What is the hardest part of your work? |
| 7 | LOOP d3 | p2_wk_4 | 这份工作收入怎么样？ | Is this job well paid? |
| 8 | LOOP d3 | p2_wk_5 | 你推荐年轻人做这份工作吗？为什么？ | Do you recommend this job for young people? Why? |

### Warnings
- **#5 is an exact duplicate of #2** — audit flag confirmed. The `p2_wk_ext1` rewrite created this.
- **`f_work_busy` and `f_work_where`** (new P1 frames added today) are both orphaned — not in `_FRAME_ORDER`.
- **#4 and #6 both ask about difficulty** — consecutive difficulty questions after break.
- **#7 asks about salary** — intrusive early in a conversation.
- **Orphans:**
  - `f_work_busy`: 工作忙吗？  ← new frame, needs adding to FRAME_ORDER
  - `f_work_where`: 你在哪儿工作？  ← new frame, needs adding to FRAME_ORDER
  - `p2_wk_retired`: 你以前做什么工作？
  - `f_probe_work_origin`: 你是怎么开始做这份工作的？
  - `f_probe_work_dream`: 这是你当时想做的工作吗？
  - `f_probe_work_best`: 工作里你最喜欢哪个部分？
  - `f_probe_work_future`: 你以后还想做别的工作吗？

### Suggested fix
Replace #5 (`p2_wk_ext1`) with a new EXTEND that discloses something and asks a genuinely different question — e.g. "工作有时候挺忙的。你平时几点下班？" (What time do you usually finish work? — HSK2). Add `f_work_busy` and `f_work_where` into FRAME_ORDER.

---

## ENGINE 5: HOBBY (14 frames)

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | OPEN d2 | f_what_hobby | 你有什么爱好？ | What are your hobbies? |
| 2 | LOOP d2 | f_often_do | 你常做吗？ | Do you do it often? |
| 3 | LOOP d2 | f_difficult_ma | 难吗？ | Is it difficult? |
| 4 | ASK  d2 | f_like_do_what | 你喜欢做什么？ | What do you like to do? — **RESET: too generic after specific hobby talk** |
| 5 | EXTD d2 | p2_hb_ext1 | 我觉得有爱好很好。你的爱好是怎么开始的？ | I think having hobbies is great. How did your hobby start? |
| 6 | LOOP d2 | f_recommend_ma | 你推荐吗？ | Do you recommend it? — blunt/short |
| 7 | ASK  d2 | f_weekend_do | 你周末做什么？ | What do you do on weekends? |
| 8 | ASK  d2 | f_like_chinese_culture | 你喜欢中国文化吗？ | Do you like Chinese culture? — **topic shift** |
| 9 | ASK  d2 | f_like_what | 你喜欢什么？ | What do you like? — **too generic at this point** |
| 10 | LOOP d2 | f_collect_what | 你收藏什么吗？ | Do you collect anything? |
| 11 | LOOP d3 | p2_hb_1 | 你什么时候开始{HOBBY}的？ | When did you start [HOBBY]? |
| 12 | LOOP d3 | p2_hb_2 | 你为什么喜欢{HOBBY}？ | *(broken text_en)* |
| 13 | LOOP d3 | p2_hb_4 | 你觉得{HOBBY}难不难？ | Do you find [HOBBY] difficult? — **duplicate of #3** |
| 14 | LOOP d2 | p2_hb_5 | 你做了多久了？ | How long have you been doing it? — **should be near #2** |

### Warnings
- **14 frames is too long** — this engine dominates the session.
- **#4 resets** to a generic question mid-conversation.
- **#8 is a topic shift** (Chinese culture) — should not be in hobby FRAME_ORDER.
- **#9 is too generic** at this stage.
- **#13 duplicates #3** — both ask about difficulty.
- **#14 should be near #2** — "how long have you done it?" is a natural follow-up to "do you do it often?".
- **Orphans:**
  - `f_probe_hobby_origin`: 你是怎么开始喜欢这个的？  ← overlaps #5 but more personal
  - `f_probe_hobby_social`: 你一般自己做还是跟朋友一起？  ← excellent social question
  - `f_probe_hobby_change`: 这个爱好对你重要吗？  ← just rewritten, currently unreachable

### Suggested restructure
Trim to ~9 focused frames. Remove #4, #8, #9, #13. Move #14 to position 3. Add `f_probe_hobby_social` in place of a removed frame.

---

## ENGINE 6: TRAVEL (7 frames)

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | OPEN d2 | f_travel_where | 你去过哪里？ | Where have you been? |
| 2 | ASK  d2 | f_want_go_where | 你想去哪里？ | Where do you want to go? |
| 3 | LOOP d3 | p2_tr_1 | 你去过哪些国家？ | Which countries have you been to? — **overlaps #1** |
| 4 | LOOP d3 | p2_tr_2 | 你最喜欢哪里？ | Where do you like best? |
| 5 | EXTD d2 | p2_tr_ext1 | 旅行真的很有意思。旅行的时候你喜欢做什么？ | Travel is really interesting. What do you like to do when travelling? |
| 6 | LOOP d3 | p2_tr_3 | 那个地方有什么好玩的？ | What's fun to do there? — "that place" is vague |
| 7 | LOOP d3 | p2_tr_4 | 你觉得那次旅行怎么样？ | *(broken text_en)* |

### Warnings
- **#1 and #3 overlap** — "where have you been" vs "which countries have you been to" ask the same thing at different scopes.
- **`f_probe_travel_learn`** (just rewritten to "你最喜欢哪次旅行？") is orphaned — similar to #4 but better phrased.
- **`f_probe_travel_alone`** ("你旅行的时候喜欢自己去还是跟人一起？") is orphaned but a rich social question.
- **Orphans:**
  - `f_probe_travel_alone`: 你旅行的时候喜欢自己去还是跟人一起？
  - `f_probe_travel_learn`: 你最喜欢哪次旅行？  ← just rewritten, currently unreachable
  - `p2_tr_5`: 我最难忘的是{PLACE}。

### Suggested fix
Remove or merge #3 (overlaps #1). Replace with `f_probe_travel_alone`.

---

## ENGINE 7: FOOD (6 frames)

| # | Type | Frame ID | Chinese | English |
|---|------|----------|---------|---------|
| 1 | OPEN d2 | f_food_what_good | 那儿有什么好吃的？ | What good food is there? — **"那儿" has no referent** |
| 2 | LOOP d2 | f_food_famous_dish | 你们那儿最有名的菜是什么？ | What dish is your place most famous for? |
| 3 | LOOP d2 | f_food_tasty | 好吃吗？ | Is it tasty? |
| 4 | EXTD d2 | p2_fd_ext1 | 我最喜欢吃好吃的东西。你最喜欢什么食物？ | I love eating delicious food. What is your favourite food? — **weak disclosure** |
| 5 | ASK  d2 | f_food_like_spicy | 你喜欢吃辣吗？ | Do you like spicy food? |
| 6 | LOOP d2 | f_food_expensive | 贵不贵？ | Is it expensive? |

### Warnings
- **#1 opens with "那儿"** — assumes a place referent that may not exist. Works only if place engine ran first.
- **#4 EXTEND disclosure is weak** — "I love eating delicious food" reveals nothing interesting about the partner.
- **Orphans are excellent:**
  - `f_probe_food_make`: 你会自己做吗？  ← more interesting than #6
  - `f_probe_food_childhood`: 你小时候常吃吗？  ← great personalisation
  - `f_probe_food_teach`: 你愿意教我怎么做吗？  ← high-value social question

### Suggested fix
Replace #4 EXTEND disclosure with something more personal. Replace #6 (`贵不贵？`) with `f_probe_food_make` or `f_probe_food_childhood`.

---

## ENGINE 8: LIFE (0 frames)

Not yet defined. No action needed.

---

## Summary table

| Engine | Frames | Critical issues | Nice to have |
|--------|--------|----------------|--------------|
| Identity | 8 | #7 duplicates #4 | Add nickname Q; reorder age |
| Place | 11 | Fix 3 broken text_en | Consider adding f_probe_place_stay |
| Family | 8 | 5 binary Qs in a row; #8 near-dup of #6 | Replace #8 with f_probe_family_closest |
| Work | 8 | #5 exact dup of #2; f_work_busy/f_work_where orphaned | Reorder difficulty Qs |
| Hobby | 14 | Too long; #4/#8/#9 weak/off-topic; #13 dup of #3; #14 wrong position | Add f_probe_hobby_social; trim to ~9 |
| Travel | 7 | #1 and #3 overlap | Add f_probe_travel_alone; fix text_en |
| Food | 6 | Weak EXTEND disclosure; "那儿" opener fragile | Promote orphan food Qs over #6 |
| Life | 0 | Not yet defined | — |
