<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as the intended Phase 10.5 behaviour implementation plan.
> - **May guide current implementation:** No.
> - **Current authority:** Verified conversation code and the applicable R2 behavioural contracts.
> - **Principal caution:** An implementation plan does not prove that each proposed behaviour was implemented, retained, or reached the R2 baseline. Verify every item against current code and tests.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Phase 10.5 — Behaviour Implementation Plan (Pre-Implementation)

**Status:** planning only — **do not implement yet**.  
**Basis:** `docs/specs/MANDARINOS — PHASE 10.5 BEHAVIOUR TUNING SPEC`  
**Goal:** validate behaviour choices *before* coding.

---

## 1) Selector logic (step-by-step order)

### 1.1 Inputs the selector needs (no schema changes)

- **Conversation state**
  - `recent_frame_ids` (already used)
  - `turn_index` / `exchange_count` (derive from history)
  - `curiosity_depth` (new small state field; default `0`)
  - `last_user_move_was_answer` (derive from history)
  - `last_answer_engine` (engine of last partner ASK frame)
  - `last_answer_slots_filled` (derive if selected option was `FRAME_WITH_SLOTS` or mapped to slot frame)
  - `new_memory_written_this_turn` (Phase 10 memory capture output)
  - `last_user_answer_text` (already in Phase 10 wiring)
- **Content stores**
  - frames: `p1_frames.json`, `p2_frames.json`
  - options: `runtime/out_phase7/frame_options.runtime.json`
- **Tags / classifications**
  - Spec requires: **REACTION** and **LOOP_QUESTION** tags on frames.
  - Pre-implementation: we can approximate candidates by heuristics (see Section 2), but implementation should move toward explicit tagging.

### 1.2 Target turn cadence

Replace the mechanical baseline:

- ASK → ANSWER → NEXT ASK

With the tuned baseline:

- **ASK → ANSWER → [REACTION default] → [OPTIONAL LOOP] → NEXT MOVE**

### 1.3 Reaction insertion (**micro-layer**, mandatory bias)

After **any user ANSWER**:

- Insert a short **REACTION micro-layer** with probability **0.7**
- **REACTION is not terminal**: after emitting a reaction, the selector may still continue to evaluate LOOP_QUESTION (see Section 2).
- Reaction selection:
  - prefer **topic-specific** reactions first (see Section 1.3.1)
  - otherwise use a generic reaction fallback (spec examples): **哦 / 是吗 / 不错 / 很好**

Rules:
- REACTION does **not** increment curiosity depth
- Keep REACTION short (1–3 words preferred)

#### 1.3.1 Reaction fallback preference (topic-specific → generic)

Reaction selection order after a meaningful answer:

1. **Exact match**: a reaction frame explicitly tied to the current engine/topic (future: tag `move_type=REACTION` + engine)
2. **Engine-local generic** (e.g. place has `f_place_reaction` = “很好！”)
3. **General reaction** (fallback list)

**Note:** This keeps “很好！” from being used after everything, while still allowing it for place answers where it already exists.

### 1.4 Curiosity triggering (partner-side, weighted)

Compute `curiosity_triggered` if any condition holds:

- slot filled (CITY, JOB, FOOD)
- extend answer (future: option_role-aware; pre: heuristic)
- new memory value written this turn

If triggered, prefer a **LOOP_QUESTION** with probability **0.6** (subject to depth cap and availability).

### 1.5 Curiosity depth control

- `max_curiosity_depth = 2`
- LOOP_QUESTION increments depth
- REACTION does not
- Once depth reached → force **NEXT ASK or BRIDGE**

### 1.6 Reciprocity bias (early conversation)

For the first **3 exchanges**:

- Prefer **blended reciprocity** as the default early behaviour:
  - 我叫小明。**你呢？**
  - 我是新西兰人。**你呢？**
  - 我现在住在北京。**你呢？**
- If blended reciprocity is not available, fall back to a standalone reciprocate option:
  - **你呢？**
  - **你叫什么名字？**

Ranking rule (early window): ensure *some* reciprocate option (blended preferred) appears in the **top 2** options.

### 1.7 Oxygen selection (user curiosity, always-available but **context-gated**)

Curiosity options must be **always available** to the learner, but should not be **forced visible** on every turn if that feels socially unnatural.

#### 1.7.1 Visibility gating (when to visibly surface curiosity)

Curiosity affordance has two modes:

- **Available (not surfaced):** an “Ask back” affordance exists but does not take a slot in the primary option list.
- **Surfaced (visible 1–2 options):** 1–2 curiosity options appear as visible buttons/cards.

Surface curiosity options when **any** of the following holds:

1. **After a meaningful user answer** (slot filled OR new memory written OR user chose extend/blended reciprocity)
2. **After a LOOP_QUESTION** (because the dialogue is already in curiosity mode)
3. **Stalled rhythm**: after 2 consecutive partner ASK turns without any LOOP or REACTION micro-layer (interview drift)
4. **User hesitation** signals (recovery-light): user taps hint repeatedly or times out (if tracked)

Do **not** surface curiosity options:

- On the very first greeting turn (socially odd)
- Immediately after a repair/recovery move (keep it simple)

Mapping (from spec):

- **PLACE / CITY**: 怎么样？ / 方便吗？ / 哪里？
- **JOB / WORK**: 忙吗？ / 怎么样？
- **FOOD**: 好吃吗？ / 喜欢吗？ / 为什么？
- **Fallback**: 为什么？ / 怎么样？

Rules:
- When surfaced, show **1–2** options
- Must be **context relevant** (engine_id OR slot type)

### 1.8 Soft chaining (topic-follow)

If the user answer introduces a new topic, allow the next ASK to follow user content rather than fixed order.

#### 1.8.1 Slot/topic follow-up preference (stronger than engine-only)

Prefer slot/topic-specific follow-ups *before* generic engine flow:

- **CITY** → prefer “city-life” follow-ups (生活怎么样？ / 方便吗？) before generic place questions
- **JOB** → prefer “work experience” follow-ups (忙不忙？ / 下班时间？) before generic “喜欢吗？”
- **DISH** → prefer “taste/spicy/preference” follow-ups (好吃吗？ / 喜欢辣吗？ / 为什么？) before generic food questions

Pre-implementation heuristic (no NLP, no schema changes):

- If the answer filled a **DISH/FOOD** slot → next engine can be **food**
- If the answer filled a **CITY** slot → next engine can be **place**
- If the answer filled a **JOB** slot → next engine can be **work**

Additionally, if the last answer contains one of these slot types, attempt a **slot-priority follow-up list** first (future: via tags; pre: a curated mapping from slot→preferred frame IDs).

---

## 2) Priority resolution (exact order of evaluation)

### 2.1 Next partner move selection order

When selecting the **next partner move**, evaluate rules in this order:

1. **Recovery / repair / safety** (existing behaviour unchanged)
2. **After user ANSWER → compute meaningfulness + topic context**
   - meaningful if slot filled OR new memory written OR extend/blended reciprocity selected
   - capture `topic_context` (engine + most-recent slot type)
3. **After user ANSWER → REACTION micro-layer (0.7)**
   - if meaningful and roll succeeds:
     - emit REACTION (prefer topic-specific; then generic)
     - **continue evaluation** (do not stop here)
4. **After user ANSWER → partner curiosity**
   - if `curiosity_triggered` and `curiosity_depth < 2`
   - roll LOOP 0.6
   - if LOOP exists → emit LOOP_QUESTION, increment depth, stop
5. **Depth cap enforcement**
   - if `curiosity_depth >= 2` → force NEXT ASK or BRIDGE (reset depth to 0)
6. **Soft chaining (slot/topic preference first, then engine)**
   - if last answer had slot/topic → try slot-priority follow-up frames first
   - else if user-introduced engine is detectable → prefer next ASK from that engine
7. **Default next ASK**
   - fallback to existing `_FRAME_ORDER` and bridge logic (`_BRIDGE_TARGETS`)

### 2.2 Option set construction order

When building options for a partner ASK frame, apply in this order:

1. **minimal** options (existing runtime options)
2. **extend** options (if present; keep at most 1)
3. **reciprocate** option (force into top 2 if `exchange_count < 3`)
4. **repair** option (optional)
5. **curiosity** options (oxygen mapping; **surface only when gating conditions fire**, otherwise keep as non-intrusive affordance)

If the set exceeds UI capacity, drop in this order:

- repair first
- then extra extend (keep 0–1)
- never drop minimal
- when curiosity is surfaced: never drop it below 1

---

## 3) Pseudocode

```python
MAX_CURIOSITY_DEPTH = 2
P_REACTION = 0.7
P_LOOP = 0.6
EARLY_EXCHANGES = 3

def select_next_partner_move(state, frames_db, options_db, rng):
    # 1) recovery (unchanged)
    if state.recovery_needed:
        return select_recovery_move(state)

    last = state.last_turn
    if last.speaker == "user" and last.is_answer:
        meaningful = (
            last.slot_filled
            or last.new_memory_written
            or last.was_extend_answer
            or last.was_blended_reciprocate
        )
        topic = infer_topic_context(last)  # engine + slot_type if present

        reaction_emitted = False
        # 3) REACTION micro-layer (not terminal)
        if meaningful and rng.random() < P_REACTION:
            fr = pick_reaction_frame(topic, state, frames_db)  # may be None
            if fr:
                emit_micro_layer(Move(kind="REACTION", frame_id=fr.id,
                                      curiosity_depth=state.curiosity_depth))
                reaction_emitted = True
            else:
                emit_micro_layer(Move(kind="REACTION_FALLBACK", text=pick_topic_reaction_text(topic)))
                reaction_emitted = True

        curiosity_triggered = (
            last.slot_filled
            or last.new_memory_written
            or last.was_extend_answer
            or last.was_blended_reciprocate
        )

        # 4) partner LOOP (curiosity)
        if curiosity_triggered and state.curiosity_depth < MAX_CURIOSITY_DEPTH:
            if rng.random() < P_LOOP:
                fr = pick_loop_question_frame(state, frames_db)  # may be None
                if fr:
                    return Move(kind="LOOP_QUESTION", frame_id=fr.id,
                                curiosity_depth=state.curiosity_depth + 1)

        # 5) depth cap
        if state.curiosity_depth >= MAX_CURIOSITY_DEPTH:
            return select_next_ask_or_bridge(state, reset_depth=True)

        # 6) soft chaining: slot/topic follow-up preference
        slot_followup = pick_slot_priority_followup(topic, state, frames_db)
        if slot_followup:
            return Move(kind="ASK", frame_id=slot_followup.id, curiosity_depth=0)

        chained_engine = infer_engine_from_last_answer(last)
        if chained_engine:
            fr = pick_next_ask_in_engine(chained_engine, state, frames_db)
            if fr:
                return Move(kind="ASK", frame_id=fr.id, curiosity_depth=0)

        # 7) default
        return select_next_ask_or_bridge(state, reset_depth=False)

    # Not after user answer: default
    return select_next_ask_or_bridge(state, reset_depth=False)


def build_option_set_for_partner_ask(frame_id, state, options_db):
    base = options_db.get(frame_id, {}).get("options", [])
    option_set = list(base)  # minimal

    # extend
    option_set.extend(maybe_get_extend_options(frame_id, state)[:1])

    # reciprocity early (prefer blended reciprocity)
    if state.exchange_count < EARLY_EXCHANGES:
        blended = maybe_get_blended_reciprocate_option(frame_id, state)  # e.g. “我叫X。你呢？”
        if blended:
            option_set = force_into_top2(option_set, blended)
        else:
            recip = maybe_get_reciprocate_option(frame_id, state)  # e.g. “你呢？”
            if recip:
                option_set = force_into_top2(option_set, recip)

    # repair
    repair = maybe_get_repair_option(frame_id, state)
    if repair:
        option_set.append(repair)

    # curiosity always-available; surfaced only when gating conditions fire
    if should_surface_curiosity(state):
        oxygen = select_oxygen_options(state.context_engine_or_slot, k=2)
        option_set = append_or_merge(option_set, oxygen)

    return trim_to_ui_limit(option_set)
```

---

## 4) Full conversation simulation (real frames/options + tuned behaviour)

**Constraint:** use real frames and real options where possible. Any item that requires option injection or new cards is marked **[MISSING]**.

**Fixed RNG outcomes for review:**
- REACTION inserted after user answers on Turn 3 and Turn 8 (consistent with 0.7 bias)
- LOOP chosen on Turn 11 (consistent with 0.6 when triggered)
- `curiosity_depth` starts at 0

### Exchange 1 (early blended reciprocity)

**Turn 1 — Partner [ASK]** `f_ask_you_name`  
你叫什么名字？

**User options (real, from runtime options):**
- 我叫小明。
- 我叫丽丽。
- 我叫小红。

**Reciprocate (preferred, blended):**
- 我叫小明。你呢？ **[MISSING blended option injection]**

**Curiosity affordance:** available but **not surfaced** on the first greeting turn (visibility gating).

**Turn 2 — User:** 我叫小明。

**Turn 3 — Partner [REACTION micro-layer]** `f_nice_to_meet`  
很高兴认识你。  
Then continue evaluation (non-terminal); no loop candidate chosen here → proceed to next ASK.

### Exchange 2

**Turn 4 — Partner [ASK]** `f_ask_name_meaning`  
你的名字是什么意思？

**Curiosity affordance:** available; still **not surfaced** (answer is likely not “topic-expanding” yet).

**Turn 5 — User:** answers minimally using available options  
**[CONTENT NOTE]** This question’s runtime options may be word-heavy; sentence-level answer should exist or be added later.

### Exchange 3

**Turn 6 — Partner [ASK]** `f_from_where`  
你是哪里人？

**User options (real):**
- 我是澳大利亚人。
- 我是中国人。
- 我是新西兰人。

**Reciprocate (preferred, blended):**
- 我是新西兰人。你呢？ **[MISSING blended option injection]**

**Curiosity affordance:** available but not surfaced yet (still early, keep primary options clean).

**Turn 7 — User:** 我是新西兰人。

**Turn 8 — Partner [REACTION micro-layer]** `f_place_reaction`  
很好！  
Continue evaluation: no strong loop for NATIONALITY exists → proceed to next ASK.

### Curiosity-triggered LOOP (CITY)

**Turn 9 — Partner [ASK]** `frame.location.live_question`  
你现在住哪里？

**User options (real):**
- 我现在住在广州。
- 我现在住在北京。
- 我现在住在上海。

**Curiosity affordance:** available; not surfaced until a meaningful slot is filled (next turn).

**Turn 10 — User:** 我现在住在北京。  
Trigger: slot CITY / new memory written.

**Turn 11 — Partner [REACTION micro-layer]** `f_place_reaction` *(or another city-specific reaction if tagged later)*  
很好！  
Continue evaluation.

**Turn 12 — Partner [LOOP_QUESTION]** `p2_pl_1` (depth 0→1)  
你觉得北京生活怎么样？

**Curiosity options (surfaced; PLACE/CITY):**
- 怎么样？ **[MISSING CARD]**
- 方便吗？ **[MISSING CARD]**

**Turn 13 — User:** answers using available runtime options for `p2_pl_1`  
**[CONTENT GAP]** Runtime options for `p2_pl_1` appear to be mostly vocabulary fragments, not natural sentence answers.

### Continue with next ASK

**Turn 14 — Partner [ASK]** `f_place_like_there`  
你喜欢那儿吗？

**Turn 15 — User:** 喜欢，很喜欢。 (`f_place_like_yes`)

### Work

**Turn 16 — Partner [ASK]** `f_what_work`  
你做什么工作？

**User options (real):**
- 我是工程师。
- 我是老师。
- 我是学生。

**Curiosity affordance:** available; will surface after JOB is provided.

**Turn 17 — User:** 我是老师。  
Trigger: slot JOB / new memory written.

**Turn 18 — Partner [REACTION micro-layer]** *(topic-specific preferred; currently [MISSING])*  
**[MISSING WORK REACTION FRAME]** e.g. “不错！” / “哦，老师！”  
Fallback (generic): “不错！”

**Turn 19 — Partner [LOOP_QUESTION preferred, slot/topic follow-up]** *(currently weak inventory)*  
Preferred: a work-experience follow-up like “忙吗？” / “几点下班？”  
**[MISSING LOOP FRAME for work-follow-up OR missing tagging to select p2_wk_* appropriately]**

Fallback to existing ASK:
**Turn 19 — Partner [ASK]** `f_like_work`  
你喜欢你的工作吗？  
**[BEHAVIOUR NOTE]** Spec would often prefer a work LOOP here (“忙吗？”), but we currently lack a reliable tagged LOOP frame for work follow-ups; fallback to existing ASK.

**Turn 20 — User:** 喜欢，我很喜欢。 (`frame.opinion.like`)

### Food

**Turn 21 — Partner [ASK]** `f_food_what_good`  
那儿有什么好吃的？

**User options (real):**
- 有很多包子。
- 有很多饺子。
- 有很多火锅。

**Curiosity affordance:** available; will surface after DISH is provided.

**Turn 22 — User:** 有很多火锅。  
Trigger: slot DISH / new memory written.

**Turn 23 — Partner [REACTION micro-layer]** *(topic-specific preferred; currently [MISSING])*  
Preferred: “好吃！” / “火锅不错！”  
**[MISSING FOOD REACTION FRAME]** → fallback generic: “不错！”

**Turn 24 — Partner [LOOP_QUESTION preferred, slot/topic follow-up]** `f_food_like_spicy` *(if available and tagged)*  
你喜欢吃辣吗？ *(example; depends on existing food frame text)*  

**Curiosity options (surfaced; FOOD):**
- 喜欢吗？ **[MISSING CARD]**
- 为什么？ **[MISSING CARD]**

**Turn 25 — User:** answers via available options (likely minimal/word-level).  

**Turn 26 — Partner [ASK]** `f_food_famous_dish`  
你们那儿最有名的菜是什么？  
**[BEHAVIOUR NOTE]** Spec would prefer REACTION + LOOP (“你喜欢辣吗？”) before continuing the chain; depends on REACTION/LOOP inventory.

---

## 5) Remaining awkwardness + missing content inventory

### 5.1 Where behaviour can still feel unnatural (even if logic is correct)

- **P2 loop questions with word-only answers** (e.g. `p2_pl_1`): the loop is good, but answering via vocabulary fragments breaks conversational flow.
- **Work follow-ups after job**: without a consistent work LOOP inventory, the system falls back to interview-like questions.
- **Food follow-ups after dish**: without strong REACTION/LOOP frames, food can become a rigid chain.

### 5.2 Missing content required to satisfy the spec

- **Curiosity option cards** (oxygen always-on) mapped by engine/slot:
  - PLACE: 怎么样？ / 方便吗？ / 哪里？
  - WORK: 忙吗？ / 怎么样？
  - FOOD: 好吃吗？ / 喜欢吗？ / 为什么？
  - fallback: 为什么？ / 怎么样？
- **Reciprocate options** injected into early exchanges (e.g. `f_you_ne`) across ASK frames.
- **Repair options** inside the main option set (not only in separate recovery UI).
- **REACTION / LOOP_QUESTION tagging (or a stable heuristic)**:
  - identity reactions beyond `f_nice_to_meet`
  - work loop questions (“忙吗？” / “几点下班？” / “工作怎么样？”) as reliable follow-ups
  - food reactions and loops (“不错/很好”, “你喜欢辣吗？”, “为什么？” follow-ups)
- **Sentence-level answers** for key P2 loop frames (not just vocabulary cards), especially:
  - `p2_pl_1` (生活怎么样？)

---

## 6) Prioritized weak-content list (loop frames with fragmentary answer options)

These frames are **excellent LOOP_QUESTION candidates**, but their current option sets are too fragmentary (mostly isolated vocabulary items) to support natural conversation.

Top priority (5–10):

1. `p2_pl_1` — 你觉得{CITY}生活怎么样？  
   - Options include “有点”, “上海”, plus the question slot card itself → lacks answer sentences.
2. `p2_pl_3` — 你平时喜欢去{PLACE}吗？  
   - Options include unrelated words like “等会儿”, “你好” → missing “喜欢/不喜欢/常去” sentence answers.
3. `p2_wk_1` — (work follow-up)  
   - Options are “下班 / 最 / 不” → missing answer sentences or guided patterns.
4. `p2_wk_2` — (work follow-up)  
   - Options are “意义 / 我的 / 最近” → missing sentence-level replies.
5. `p2_wk_4` — (work follow-up)  
   - Options are “安排 / 姐姐 / 和” → missing usable reply patterns.
6. `p2_wk_5` — (work follow-up)  
   - Options are “喜欢 / 会 / 解决” → missing usable reply patterns.
7. `p2_tr_1` — (travel follow-up)  
   - Options are “去过 / 你 / 现在” → missing “我去过X / 没去过 / 想去” sentences.
8. `p2_tr_2` — (travel follow-up)  
   - Options are “喜欢 / 等会儿 / 新西兰” → missing natural replies.
9. `p2_tr_3` — (travel follow-up)  
   - Options are “好玩 / 跟 / 住” → missing reply patterns.
10. `p2_tr_4` — (travel follow-up)  
   - Options are “怎么样 / 是 / 开始” → missing replies; “怎么样” belongs as oxygen, not as the only usable answer.


