# Phase 10.5 — Mapping, Gaps, Minimal Schema, and Before/After Examples

**Purpose:** Map current system to Phase 10.5 concepts; identify gaps; propose minimal schema extension; illustrate BEFORE vs AFTER with example conversations.  
**Status:** Pre-implementation (structure only — no code).  
**References:** `MANDARINOS_PHASE_10_5_STABILISATION_BRIEF.md`, `MANDARINOS_CONVERSATION_ARCHITECTURE_AUDIT_v1.md`.

---

## 1. Map current system to move_type, option_role, question_type

### 1.1 move_type (conversation role of a frame)

**Current state:** Frames have `speaker` (`"partner"` | `"user"`) and `text`. There is **no** `move_type` field. Role is inferred only from who speaks and sentence shape.

**Inferred mapping (current behaviour → Phase 10.5 move_type):**

| Current signal | Inferred move_type | Example frame(s) |
|----------------|--------------------|------------------|
| partner, text ends with ？ | **ASK** | `f_ask_you_name`, `f_from_where`, `f_what_work`, `p2_id_2`, `p2_pl_1`, … |
| user, short answer pattern (我叫X, 我是X人, 我是X。) | **ANSWER_MIN** | `frame.identity.name`, options for `f_from_where` / `f_what_work` (sentence options) |
| user, “你呢？” | **RECIPROCITY** | `f_you_ne` |
| partner, statement (no ？) | **REACTION** or filler | `f_nice_to_meet`, `f_partner_name`, `f_no_problem` |
| partner, greeting | (could be ASK or REACTION) | `frame.greeting.hello` |
| user, greeting reply | **ANSWER_MIN** (or REACTION) | `frame.greeting.hello_reply` |
| Recovery phrases (什么？, 再说一次, 慢一点) | **REPAIR** | In UI as options with `kind: "RECOVERY"`; **not** first-class frames in P1/P2 |
| Oxygen probes (为什么？, 谁？, 哪里？) | **LOOP_QUESTION** (user asks) | `_OXYGEN_LOOP_PROBES` in ui_server; server returns stub → no frame_id, `probe_response` |
| Bridge (topic change) | **BRIDGE_QUESTION** | No dedicated frame; next frame is chosen from another engine; first question of that engine is effectively “bridge” |

**Not present in current frames:**

- **ANSWER_EXTEND** — No frame or option that is explicitly “short answer + extra detail” (e.g. “我叫Raymond，我来自新西兰”).
- **CLARIFY** — No partner frame that explicitly checks understanding (“你的意思是……？”).
- **LOOP_QUESTION** as **partner** move — Loop is currently user-initiated (probes); partner “follow-up” is just the next ASK in `_FRAME_ORDER` (treasure/loop order), not tagged.

**Summary:**  
Current system can be **mapped** to ASK, ANSWER_MIN, RECIPROCITY, REACTION, and implicitly REPAIR (recovery) and BRIDGE (selector). ANSWER_EXTEND and CLARIFY are absent; LOOP_QUESTION exists only as user probes, not as a tagged partner move type.

---

### 1.2 option_role (conversation strategy of an option)

**Current state:** Options in `frame_options.runtime.json` have `hanzi`, `pinyin`, `meaning`, `is_gold`, `is_slot`, `kind` (WORD | FRAME_WITH_SLOTS). There is **no** `option_role` field.

**Inferred mapping:**

| Current option shape | Inferred option_role | Notes |
|----------------------|----------------------|--------|
| Short sentence answer (我叫小明。, 我是新西兰人。, 我现在住在北京。) | **minimal** | Only strategy currently expressed; no distinction between minimal vs extend |
| “你呢？” as an option (if present in options for a frame) | **reciprocate** | Only `f_you_ne` is a full frame; not typically offered as one of several options under another question |
| Recovery options (什么？, 再说一次, 慢一点, 我不懂) | **repair** | Injected in UI; not in frame_options as tagged options |
| No option that adds detail after a short answer | **(missing) extend** | e.g. “我叫小明，我来自上海。” |
| No option that explicitly checks understanding | **(missing) clarify** | e.g. “你的意思是……？” |
| No option that is purely emotional/backchannel | **(missing) react** | e.g. “真的吗？” “哦！” |
| User asks follow-up (为什么？, 哪里？, 怎么样？) | **(missing) curiosity** | Phase 10.5 extension: option_role **curiosity** for user-driven curiosity (see §4). |

**Summary:**  
All current answer options behave as **minimal** (one factual answer per tap). Repair exists only as a separate recovery UI layer. **extend**, **reciprocate**, **clarify**, **react**, and **curiosity** are not represented as option roles today.

---

### 1.3 question_type (curiosity engine: core / treasure / loop / bridge)

**Current state:** No `question_type` field in frame data. Order and “depth” are encoded only in **selector logic** in `scripts/ui_server.py` via `_FRAME_ORDER` and `_FRAME_AFTER`.

**Inferred mapping (from _FRAME_ORDER and frame position):**

| question_type | Current expression | Example frames |
|---------------|--------------------|----------------|
| **core** | First 1–2 partner-question frames per engine in `_FRAME_ORDER` | `f_ask_you_name`, `f_ask_name_meaning` (identity); `f_from_where`, `f_place_like_there`, `frame.location.live_question` (place); `f_what_work`, `f_like_work` (work); `f_food_what_good` (food); etc. |
| **treasure** | Later entries in `_FRAME_ORDER` (deeper / more interesting) | `p2_id_2`, `p2_id_4`, `p2_id_5` (identity); `p2_pl_1`–`p2_pl_4` (place); `f_food_famous_dish`, `f_food_tasty` (food); etc. |
| **loop** | Not a frame tag; user-initiated only | User asks “为什么？” / “谁？” etc. → server returns stub. No partner frame tagged “loop” that follows up on user’s answer. |
| **bridge** | Not a frame tag; selector behaviour | When bridging, selector picks the next frame from another engine; that frame is still stored as a normal ASK (core or treasure) in its own engine. |

**Summary:**  
**core** and **treasure** can be inferred from position in `_FRAME_ORDER` but are **not** in the frame schema. **loop** and **bridge** are not first-class in frame data; they are behaviour (user probes + selector bridge).

---

## 2. Gaps in current frames and options

### 2.1 Frame-level gaps

- **No move_type:** Cannot select “next move type” (e.g. REACTION vs LOOP_QUESTION) then fill with a frame; selector only picks “next frame” by engine + order.
- **No question_type:** Core/treasure/loop/bridge are implicit in code, not queryable from frame data (e.g. “give me a loop question for this topic”).
- **Reciprocity:** Only one explicit reciprocity frame (`f_you_ne` “你呢？”). Not offered as a **choice** after an answer (e.g. “answer only” vs “answer + 你呢？”).
- **Reaction:** Partner reactions (“真的吗？” “太好了。”) exist as occasional frames but are not systematically used after ANSWER_MIN; flow is usually ASK → user answer → next ASK.
- **Loop (partner):** No partner frame tagged as “follow-up on what user just said”; only user-initiated probes get a stub.
- **Repair:** Recovery phrases live in UI/recovery list, not as frames with move_type REPAIR.
- **Clarify:** No partner frame that checks understanding.
- **Answer-extend:** No user frame or option that models “minimal + extend” in one move.

### 2.2 Option-level gaps

- **Single strategy per question:** Each question’s options are 2–3 **minimal** answers (e.g. three names, three cities, three foods). No **extend** or **reciprocate** option alongside.
- **No option_role:** Runtime cannot “prefer extend” or “offer reciprocate” as a strategy; cannot filter options by role.
- **Repair not in options:** Repair is a separate panel/list; not one of the options under the current question (so “answer vs repair” is not a single, structured choice).
- **Mismatch (noted in Phase 10):** Some frames have options that feel mismatched to the question (wrong or generic options); fixing that is content/schema alignment, not just adding a role.

### 2.3 Structural gaps (no skeletons)

- **No conversation skeletons:** Flow is “next frame by engine + order,” not “pick skeleton (e.g. ASK → ANSWER_MIN → REACTION) then fill slots with frames.”
- **No explicit rhythm:** Reciprocity and reaction are not guaranteed steps; they are not part of a selectable pattern.

### 2.4 Oxygen vocabulary

- **Not tagged:** Words like 什么, 哪里, 怎么, 为什么, 呢, 吗, 真的, 什么？, 再说一次 are in content but not tagged as `oxygen_tags`; system does not “prioritise their visibility” or “reuse them across engines” in a structured way.

---

## 3. Minimal schema extension

Goal: add the minimum fields so that **structure** exists for move_type, option_role, question_type, and (optionally) oxygen and skeletons, **without** changing existing APIs or card/token/memory systems.

### 3.1 Frames (p1_frames.json / p2_frames.json or equivalent)

Add **optional** fields (existing frames remain valid without them):

| Field | Type | Allowed values | Purpose |
|-------|------|----------------|---------|
| `move_type` | string | `ASK` \| `ANSWER_MIN` \| `ANSWER_EXTEND` \| `REACTION` \| `LOOP_QUESTION` \| `BRIDGE_QUESTION` \| `RECIPROCITY` \| `REPAIR` \| `CLARIFY` | Conversation role of this frame so runtime can select by move. |
| `question_type` | string | `core` \| `treasure` \| `loop` \| `bridge` | For ASK frames only; makes curiosity structure explicit. Omit for non-ASK. |

**Defaulting:** If `move_type` is omitted, infer from existing `speaker` + heuristics (e.g. partner + ？ → ASK; `f_you_ne` → RECIPROCITY). If `question_type` is omitted, infer from position in `_FRAME_ORDER` for backward compatibility.

### 3.2 Options (frame_options.runtime.json or source that generates it)

Add **optional** field to each option object:

| Field | Type | Allowed values | Purpose |
|-------|------|----------------|---------|
| `option_role` | string | `minimal` \| `extend` \| `reciprocate` \| `repair` \| `clarify` \| `react` \| **`curiosity`** | Strategy this option represents. **curiosity** = user asks a follow-up (为什么？/ 哪里？/ 怎么样？/ etc.). |

**Defaulting:** If omitted, treat as `minimal` so existing options remain valid.

### 3.3 Oxygen (light tagging)

**Option A — In frame/option data:**  
Add optional `oxygen_tags: string[]` to frames or to tokens (e.g. `["question_what", "connection_so"]`). Values can be a small closed list (question / connection / interaction / repair oxygen).

**Option B — Separate index:**  
One small JSON (e.g. `oxygen_vocabulary.json`) listing word_ids or hanzi that are “oxygen”; runtime or UI can tag tokens when rendering. No change to frame schema.

**Recommendation:** Option B (separate index) is minimal and keeps frame schema smaller; Option A ties oxygen to specific frames and supports “this frame uses these oxygen words.”

### 3.4 Conversation skeletons

**New artifact (no change to frames/options):**  
e.g. `conversation_skeletons.json` or a section in an existing design doc:

- List of skeleton ids and their **move sequences** (e.g. `["ASK", "ANSWER_MIN", "REACTION"]`).
- Runtime can choose a skeleton per turn or per topic, then choose a frame per move_type (and optionally question_type), then options by option_role.

No new fields in frame/option schema; skeletons reference move_types only.

---

## 4. Curiosity Activation (extension)

**Principle:** After an “interesting” answer, the system should prefer follow-up that deepens the topic (curiosity moves) or reacts, then transition back to a new question or bridge. No heavy AI; simple structural rules only.

### 4.1 Conceptual unification: “curiosity move”

Treat **LOOP_QUESTION** (partner) and **option_role: curiosity** (user) as the **same underlying concept: curiosity move**.

- **Curiosity move** = one turn that deepens or follows up on what was just said (e.g. “为什么？” “你喜欢辣吗？” “怎么样？”).
- **Partner-initiated:** System chooses a frame with `move_type: LOOP_QUESTION` → partner asks the follow-up.
- **User-initiated:** User selects an option with `option_role: curiosity` (e.g. 为什么？, 哪里？, 怎么样？) → partner gives short reply (stub).
- Both consume the same **curiosity budget** (see §4.4). Schema keeps distinct fields (`move_type` on frame, `option_role` on option) for implementation; behaviour treats them as one family for depth control.

### 4.2 When curiosity is triggered (structural rules)

Curiosity mode is triggered when **any** of the following is true (simple booleans, no ML):

1. **After ANSWER_EXTEND**  
   Last user move was an option with `option_role: extend` (e.g. “我叫小明，我来自上海.”).  
   → Treat as “interesting answer”; next prefer LOOP_QUESTION / REACTION and offer user curiosity options.

2. **After slot-filled answers**  
   Last user move came from an option that fills a **slot** (e.g. CITY, JOB, NAME, DISH) — i.e. `is_slot: true` or option is tied to a frame with slots (e.g. 我现在住在{CITY}。, 我是{JOB}。, 有很多{DISH}。).  
   → Treat as “concrete new info”; trigger curiosity (partner follow-up + offer user curiosity options).

3. **After new information (not yet in memory)**  
   The last turn wrote to **learner_memory** a field that was previously empty (e.g. first time we learned hometown, job, or favourite_food).  
   → Treat as “new info”; trigger curiosity.

**Rule summary:**  
`curiosity_triggered = (last_option_role == extend) OR (last_option_was_slot_filled) OR (last_turn_updated_memory_from_empty)`.

### 4.3 Oxygen integration: curiosity-option selection (no generic always-on)

**Avoid** showing the same generic curiosity set (为什么？, 哪里？, 怎么样？, …) after every answer. Use **simple oxygen selection rules** so curiosity options are **context-appropriate**.

- **Map engine → curiosity options**  
  - e.g. **place** → 怎么样？, 哪里？ (how is it, where); **food** → 为什么？, 喜欢吗？ (why, do you like it); **work** → 怎么样？, 忙吗？; **identity** → 怎么样？, 为什么？.
- **Map slot (or memory field just set) → curiosity options**  
  - e.g. slot **CITY** / field `lives_in` → 怎么样？, 方便吗？; slot **DISH** / field `favourite_food` → 为什么？, 喜欢辣吗？; slot **JOB** → 忙吗？, 怎么样？.
- **Rule:** Offer only **1–3** curiosity options per turn, chosen by (current_engine, last_filled_slot_or_updated_memory_field). No “always-on” full probe list; select subset by context.
- **Data:** Small mapping table or rules (engine_id + optional slot/field → list of oxygen probe ids or option_role: curiosity option ids). Same oxygen vocabulary, different subsets per context.

### 4.4 Behaviour after interesting answer (simple rules)

When `curiosity_triggered` is true **and** curiosity depth has not reached the cap (see §4.5):

1. **Partner move preference (partner curiosity move or REACTION)**  
   Next partner move **prefer** (in order):
   - **LOOP_QUESTION** (partner curiosity move) — follow-up that builds on what user said.
   - **REACTION** — short reaction (e.g. “真的吗？” “火锅很好.”).
   - If none available, fall back to next ASK (core/treasure) or bridge.

2. **User curiosity options (user curiosity move)**  
   Offer **context-appropriate** curiosity options only (per §4.3: engine/slot → subset).  
   When user selects one (option_role: curiosity), partner gives short reply (stub), then flow continues.  
   **Do not** offer a generic always-on list; use oxygen selection rules.

3. **No heavy AI**  
   Triggers and preferences use only move_type, option_role, slot, memory delta, and engine/slot→oxygen map.

### 4.5 Curiosity control: max depth and forced transition

- **max_curiosity_depth** = 1 or 2 (configurable; recommend 1–2).
- **Curiosity depth** = number of **curiosity moves** since the last **ASK** (core/treasure).  
  - A **curiosity move** is either: (a) partner’s turn was LOOP_QUESTION, or (b) user selected an option with option_role: curiosity.
- **Rule:** When `curiosity_depth >= max_curiosity_depth`, **do not** allow another curiosity move. Force transition to:
  - **new ASK** (next core/treasure question in same or other engine), or
  - **bridge** (new topic).
- **Reset:** When the partner sends an ASK (new question), set `curiosity_depth = 0`.
- Effect: Short, natural curiosity loops (1–2 follow-ups) then the conversation moves on; no endless “为什么？” “怎么样？” chains.

### 4.6 Partner-initiated vs user-initiated (same concept: curiosity move)

| Initiator | How | Counts toward depth |
|-----------|-----|---------------------|
| **Partner** | Selector chooses frame with move_type = LOOP_QUESTION | Yes |
| **User** | User selects option with option_role = curiosity | Yes |

Both are **curiosity moves**; both increment depth. After max_curiosity_depth, next turn must be ASK or bridge (no further LOOP_QUESTION, no further user curiosity options until after the next ASK).

### 4.7 Schema / runtime (unchanged from earlier)

- **Trigger conditions:** unchanged (§4.2).
- **Next-move preference when triggered and depth &lt; max:** LOOP_QUESTION > REACTION > ASK > bridge.
- **Curiosity options:** Selected by engine/slot (oxygen selection rules); not generic always-on.
- **Cap:** max_curiosity_depth = 1–2; when depth ≥ max, force ASK or bridge. No new content fields; depth is runtime state.

---

## 5. Example conversations: BEFORE vs AFTER Phase 10.5 (with curiosity loops)

Below are short flows; the last two focus on **curiosity loops**. **BEFORE** = current behaviour (frame → options → next frame by selector). **AFTER** = same content but structured with move_type, option_role, question_type, skeletons, and **curiosity activation** (trigger → prefer LOOP_QUESTION/REACTION, offer user curiosity options). Content (sentences) is unchanged; only structure and choice of move/option differ.

---

### Example 1 — Name exchange (identity)

**BEFORE (current)**  
- Partner: “你叫什么名字？” (ASK, core — implicit).  
- Options: [ 我叫小明。, 我叫丽丽。, 我叫小红。 ] (all minimal; no 你呢？, no repair).  
- User taps “我叫小明。”  
- Next: selector picks next identity question (e.g. “大家一般怎么叫你？” or “你的名字是什么意思？”) or bridges.  
- No “你呢？” or “真的吗？” as a structured next step.

**AFTER (Phase 10.5)**  
- Partner: “你叫什么名字？” — frame tagged `move_type: ASK`, `question_type: core`.  
- Options (with option_role):  
  - 我叫小明。 (minimal)  
  - 我叫小明，我来自上海。 (extend)  
  - 我叫小明，你呢？ (reciprocate)  
  - 不好意思，可以再说一次吗？ (repair)  
- User taps “我叫小明，你呢？” (reciprocate).  
- Skeleton: ASK → ANSWER → RECIPROCITY. Next move_type = RECIPROCITY.  
- Partner: “我叫李明。” (existing frame `f_partner_name`, tagged REACTION or used as reciprocity response).  
- Then next ASK (e.g. treasure question) or REACTION (“很高兴认识你。”).

**Difference:** Same sentences available, but options express **strategies** (minimal / extend / reciprocate / repair), and next move can be **reciprocity** instead of jumping to another question.

---

### Example 2 — Place (where you live)

**BEFORE (current)**  
- Partner: “你现在住在哪儿？” / “你现在住在{CITY}。” (ASK).  
- Options: [ 我现在住在广州。, 我现在住在北京。, 我现在住在上海。 ] (all minimal).  
- User taps “我现在住在北京.”  
- Next: selector picks next place or bridge question (e.g. “你觉得北京生活怎么样？”).  
- No “你呢？” or “真的吗？北京很好。” as structured choices.

**AFTER (Phase 10.5)**  
- Partner: “你现在住在哪儿？” — `move_type: ASK`, `question_type: core`.  
- Options:  
  - 我现在住在北京。 (minimal)  
  - 我现在住在北京，工作也在那里。 (extend)  
  - 在北京。你呢？ (reciprocate)  
  - 什么？ (repair)  
- User taps “我现在住在北京，工作也在那里。” (extend).  
- **Curiosity triggered** (ANSWER_EXTEND). Skeleton: ASK → ANSWER_EXTEND → [LOOP_QUESTION | REACTION].  
- Partner: “北京很好。” or “你做什么工作？” (REACTION or LOOP_QUESTION) — selected by move_type.  
- **User curiosity options offered:** 为什么？, 哪里？, 怎么样？ (option_role: curiosity). User can ask back instead of only proceeding.  
- Next: treasure or loop question in place, or bridge to work/food.

**Difference:** Options include extend/reciprocate; **curiosity trigger** makes partner do REACTION/LOOP_QUESTION and **user-driven curiosity** options appear (为什么？ etc.).

---

### Example 3 — Repair and continue

**BEFORE (current)**  
- Partner: “那儿有什么好吃的？” (ASK).  
- User doesn’t understand; recovery options appear in a **separate** area (什么？, 再说一次, 慢一点).  
- User taps “再说一次.”  
- Partner repeats the same question (or “好的，慢一点：……”).  
- Then user picks a food option.  
- Repair is **outside** the main option set; flow is “question → [answer options]” plus “[recovery options]” on the side.

**AFTER (Phase 10.5)**  
- Partner: “那儿有什么好吃的？” — ASK.  
- Options (unified list):  
  - 有很多火锅。 (minimal)  
  - 有很多饺子，我也喜欢小笼包。 (extend)  
  - 你呢？你觉得呢？ (reciprocate)  
  - 不好意思，可以再说一次吗？ (repair)  
- User taps “不好意思，可以再说一次吗？” (repair).  
- move_type = REPAIR; skeleton: ASK → REPAIR → (REPEAT or CLARIFY) → then continue.  
- Partner: “好的，慢一点：那儿有什么好吃的？” (existing repeat/slow frame).  
- Same question is shown again with same option set (including repair).  
- User then picks “有很多火锅。” (minimal).  
- Next: REACTION or LOOP_QUESTION (“火锅很好。” or “你喜欢辣吗？”).

**Difference:** **Repair is one of the option_roles** for the same question; no separate “recovery panel” conceptually—one option set, multiple strategies. Flow is ASK → REPAIR → REPEAT → ANSWER → REACTION/LOOP.

---

### Example 4 — Curiosity loop (slot-filled + new memory)

**BEFORE (current)**  
- Partner: “那儿有什么好吃的？” (ASK).  
- Options: [ 有很多包子。, 有很多饺子。, 有很多火锅。 ] (all minimal).  
- User taps “有很多火锅.”  
- Memory: `favourite_food` = “火锅” (new info).  
- Next: selector picks next food question (e.g. “喜欢吃辣吗？”) or bridges.  
- No partner reaction (“火锅很好！”); no option for user to ask “为什么？” or “你喜欢吗？”.

**AFTER (Phase 10.5 + Curiosity Activation)**  
- Partner: “那儿有什么好吃的？” — ASK, `question_type: core`.  
- Options:  
  - 有很多火锅。 (minimal; slot DISH filled)  
  - 有很多火锅，我很喜欢辣。 (extend)  
  - 火锅。你呢？ (reciprocate)  
  - 为什么？ (curiosity)  
  - 不好意思，可以再说一次吗？ (repair)  
- User taps “有很多火锅。” (minimal, but **slot-filled** and **memory updated** from empty → “火锅”).  
- **Curiosity triggered** (slot_filled + new info in memory).  
- **Partner-driven:** Next move prefers LOOP_QUESTION or REACTION. Partner: “火锅很好！” (REACTION) or “你喜欢辣吗？” (LOOP_QUESTION).  
- **User-driven:** UI shows curiosity options: 为什么？, 怎么样？, 喜欢吗？ (option_role: curiosity).  
- User taps “为什么？” (curiosity). Partner: “嗯，因为我很喜欢火锅。” (persona stub).  
- Next: ASK (treasure) in food or bridge.

**Difference:** **Dual curiosity:** (1) Partner reacts or loops on “火锅” instead of jumping to next question. (2) User can ask 为什么？/ 怎么样？ as first-class options; selecting one gets a short reply, then flow continues.

---

### Example 5 — User-driven curiosity only (minimal answer, no trigger)

**BEFORE (current)**  
- Partner: “你叫什么名字？” Options: [ 我叫小明。, 我叫丽丽。, 我叫小红。 ].  
- User taps “我叫小明.”  
- Next: next identity question. User cannot ask “为什么？” unless probe row is shown (and currently that’s after “interesting” answer heuristics).

**AFTER (Phase 10.5 + Curiosity Activation)**  
- Partner: “你叫什么名字？” Options: minimal / extend / reciprocate / repair + **curiosity** (为什么？, 怎么样？).  
- User taps “我叫小明.” (minimal). **No** curiosity trigger (no extend, no slot in this frame, memory already had name or first time is “new info” — designer choice: can treat first-time name as trigger or not).  
- **Even without trigger:** User curiosity options can still be offered (e.g. always show 为什么？, 怎么样？ after any answer) so **user-driven curiosity** is always available.  
- User taps “怎么样？” (curiosity). Partner: “挺好的，我是老师。” (persona stub). Next: ASK or REACTION.

**Difference:** **User-driven curiosity** does not depend on trigger; learner can always choose to ask back (为什么？, 怎么样？, etc.) if those options are present. Trigger only changes **partner** behaviour (prefer LOOP_QUESTION/REACTION).

---

### Example 6 — Controlled curiosity loop (max_curiosity_depth = 2)

**Setup:** max_curiosity_depth = 2. Curiosity moves (partner LOOP_QUESTION or user curiosity option) count toward depth; after 2, force new ASK or bridge.

**Flow:**

1. **Partner:** “那儿有什么好吃的？” (ASK, core).  
   **User:** “有很多火锅。” (minimal; slot DISH, memory updated).  
   → curiosity_triggered = true, curiosity_depth = 0.

2. **Partner:** “火锅很好！” (REACTION). No depth increment (REACTION is not a curiosity move).  
   **User curiosity options (food context):** 为什么？, 喜欢辣吗？ (oxygen selection: food → this subset).  
   **User taps** “为什么？” (curiosity).  
   → **curiosity_depth = 1.** Partner: “嗯，因为我很喜欢火锅。” (stub).

3. **Still in curiosity window (depth 1 &lt; 2).**  
   **Partner** can do one more curiosity move: e.g. “你喜欢辣吗？” (LOOP_QUESTION).  
   → **curiosity_depth = 2.**  
   **User:** “喜欢。” (minimal).

4. **curiosity_depth >= max_curiosity_depth (2).**  
   **Forced transition:** Next move must be **new ASK** or **bridge**. No further LOOP_QUESTION, no further user curiosity options until after the next ASK.  
   **Partner:** “你喜欢中国菜吗？” (new ASK, treasure) or bridge to place/travel.  
   → curiosity_depth reset to 0 when this ASK is sent.

**Summary:** Two curiosity moves (user “为什么？” + partner “你喜欢辣吗？”), then conversation moves on. No endless loop; structure enforces a short, natural follow-up then transition.
---

## 6. Summary table (mapping + gaps + extension)

| Concept | Current | Gap | Minimal extension |
|--------|---------|-----|--------------------|
| **move_type** | Inferred from speaker + text | Not in data; REACTION/LOOP/reciprocity underused | Optional `move_type` on frame |
| **question_type** | Implicit in _FRAME_ORDER | Not in data; loop/bridge not first-class | Optional `question_type` on frame (ASK only) |
| **option_role** | All effectively minimal | No extend/reciprocate/repair/curiosity | Optional `option_role` (incl. **curiosity**) on each option |
| **Skeletons** | None | Next = next frame only | New artifact: list of move sequences |
| **Oxygen** | In content, untagged | Not prioritised or reused by structure | Optional oxygen index or frame/token tags |
| **Curiosity** | Probes after “interesting” (heuristic) | No structural trigger; no depth cap; generic probes | Trigger rules; **curiosity move** (LOOP_QUESTION + option_role curiosity unified); oxygen selection (engine/slot→options); **max_curiosity_depth** 1–2 → force ASK/bridge |

---

## 7. Updated schema summary (with Curiosity Activation)

**Frames:** optional `move_type`, optional `question_type` (ASK only). Unchanged.

**Options:** optional `option_role` = `minimal` | `extend` | `reciprocate` | `repair` | `clarify` | `react` | **`curiosity`**. Unchanged.

**Runtime/selector rules (no new content schema):**  
- **Curiosity trigger:** unchanged — `(last option_role == extend) OR (last option was slot-filled) OR (last turn wrote memory field that was null)`.  
- **Curiosity move (unified):** Partner LOOP_QUESTION and user option_role curiosity are the same concept for depth control.  
- **When triggered and depth &lt; max:** Next partner move prefer LOOP_QUESTION > REACTION > ASK > bridge.  
- **User curiosity options:** Not generic always-on. **Oxygen selection:** map (engine, slot or updated memory field) → subset of curiosity options (1–3 per turn).  
- **Curiosity control:** **max_curiosity_depth** = 1–2. When curiosity_depth ≥ max, force next move to **new ASK** or **bridge**; reset depth when partner sends ASK.  

**No heavy AI:** Triggers, preferences, oxygen selection, and depth use only structure (move_type, option_role, slot, memory delta, engine/slot→oxygen map).

---

**Next step (per brief):** Strategist review of this mapping, gap list, minimal schema, and curiosity activation; then decide implementation order.
