# MandarinOS Answer Source Contract

**Baseline commit:** `3be0315b2c9f7316b03ac2183a887f602ae9a297`
**Baseline tag:** `architecture-baseline-2026-07-12-r2`
**Source documentation branch:** `docs/architecture-v1`
**Approved contracts referenced:** `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md` (approval commit `0b6738f6da381f2969d79a3c5e0bd1e39d1d09e4`)
**Prior draft:** v1, commit `6443eb1468c1dc60dd62b36672422424e5bced1e` — this revision corrects control-flow, ordering, English-finalisation, and reachability findings identified on re-audit (see revision notes inline).
**Document status:** Draft v2
**Last verified date:** 2026-07-12

All line-number citations refer to `scripts/ui_server.py` at the baseline commit above unless another file is named. Code excerpts use repository-relative paths only; no local filesystem path appears in this document.

---

## 1. Purpose and scope

An **answer source** is any production code path capable of assigning the persona's Chinese answer to the learner (`counter_reply`, ultimately `response["counter_reply"]`) inside the `/api/run_turn` handler in `scripts/ui_server.py`. This document enumerates every such path, its priority relative to the others, the data it reads, how it produces English and pinyin, and how it interacts with deduplication, working memory, and E4.

This document governs **`counter_reply`** — the persona's answer to something the learner said on the *previous* turn. It does **not** govern **`frame_text`**, which is the partner's *next* question or conversational move, selected independently by frame selection (from `chosen = None`, line ~10485). `counter_reply` and `frame_text` are computed by separate mechanisms in the same handler and are combined in the same response; a turn can carry either, both, or neither.

This document describes the **R2-baseline production implementation**, not an idealised conversational model. Observed gaps, duplications, and incomplete cross-turn state paths are documented at the point in the descriptive sections (§§2–17) where the mechanism responsible for them is described, not deferred to a separate section. Sections 19–20 (Extension rules, Known risks) confine themselves to forward-looking implementation guidance and risk framing; they do not introduce new factual claims not already established in §§2–17. The document remains descriptive rather than prescriptive throughout — it does not redesign the answer system.

Responsibilities that remain in other documents:

* **`docs/CONVERSATION_ARCHITECTURE.md`** — overall turn lifecycle, frame selection, E4 transport contract end-to-end, engine/ladder mechanics, `state_update` field emission sequencing.
* **`docs/STATE_CONTRACT.md`** — authoritative schema and consumption status of every `conversation_state` / `state_update` field, including `last_counter_reply`, `recent_persona_replies`, mirror-topic fields, and confusion counters. SIC-1 through SIC-7 (Section 16.2) and the resolved-defect record in Section 16.3 are defined there and only cross-referenced here.
* **`docs/ASR_PIPELINE.md`** *(not yet created in this repository — referenced for future ASR-normalisation scope only; not begun as part of this revision)* — how raw learner speech becomes `answer_text` / `submitted_text` before any answer-source logic in this document runs.

---

## 2. Response-field boundary

| Field | Represents | Produced by |
|---|---|---|
| `counter_reply` | Persona's Chinese answer to the learner's *previous* turn | Priority chain in this document (§4) |
| `counter_reply_en` | English gloss associated with `counter_reply` | §13 |
| `counter_reply_pinyin` | Curated pinyin associated with `counter_reply` | §14 |
| `frame_text` | Partner's next question/statement (forward-looking) | Frame selection (`chosen = None` onward), independent of this document |
| `frame_text_en` | English gloss of `frame_text` | Frame-selection assembly, independent of this document |
| `frame_pinyin` | Pinyin of `frame_text` | Frame content (`p2_frames.json` `pinyin` field), independent of this document |
| `turn_type` | Server-classified nature of the turn | Frame/turn classification, independent of this document |
| `state_update` | Server→client state deltas | Written by both answer-source logic (`last_counter_reply`, `recent_persona_replies`, `current_engine`) and frame selection |

`counter_reply` and `frame_text` are produced **independently** in the handler: the priority chain in §4 runs first, then frame selection runs afterward using the pre-turn `current_engine` (read separately from answer generation — see §17). E4 is the one mechanism that coordinates them indirectly across turns: an eligible answer-source result can write `response["state_update"]["current_engine"]`, which influences **frame selection on the following turn**, not the current turn's `frame_text`.

```text
learner text
→ classification (last_turn_was_answer, user_asked_question, confusion/example/meaning/rr signals)
→ priority-ordered answer-source resolution (candidate Chinese, and usually a source-provided English)
→ E4 eligibility assessed from the candidate (before any post-chain replacement)
→ post-chain replacement: deduplication → exact-repeat guard → repair escalation → final ASR-junk text repair
→ each replacement step that changes the Chinese also replaces/recomputes the English for that step
→ pinyin derived from the Chinese as it stood after repair escalation (not after the final ASR-junk pass)
→ response fields (counter_reply, counter_reply_en, counter_reply_pinyin, state_update)
```

---

## 3. Audit of all production `counter_reply` producers

This section satisfies the mandatory producer audit: every occurrence and assignment of `counter_reply`, `_counter_reply`, `_counter_result`, `response["counter_reply"]`, and `response.get("counter_reply")` in `scripts/ui_server.py` was traced. The universe of answer sources is **not** defined solely by `_counter_result`; two additional assignment sites exist outside that variable, both recorded below.

### 3.1 Main-chain answer producers

The 21 concrete answer-producing branches enumerated in §4's priority table. These assign `_counter_result` (a `(zh, en)` tuple, or occasionally a zh-only value later wrapped into a tuple by the same branch) inside the `/api/run_turn` handler's `if last_turn_was_answer:` block.

### 3.2 Main-chain control-only branches

Two branches within the same structural chain that can never themselves populate `_counter_result` with new content:

* **Retain user-initiative answer** (line 10027, `if _counter_result is not None: pass`) — a no-op that preserves whatever Group 1 already produced; it does not itself decide the answer.
* **Noisy-location clarification** (lines 10141–10161) — sets `_confusion_about_app_q` and `_noisy_location_clarify` flags only; `_counter_result` remains `None` through this branch. The learner-visible effect is a later `frame_text` override (outside this document's producer set), not a `counter_reply`.

### 3.3 Post-chain answer replacement mechanisms

Four mechanisms, all running strictly after the priority chain has produced (or failed to produce) `_counter_result`, each capable of **replacing** the Chinese text already assigned to `_counter_reply`:

1. **Deduplication substitution** — `_dedupe_persona_answer()`, called from the handler at lines 10352–10367 (§8/§12).
2. **Exact-repeat belt-and-suspenders guard** — lines 10372–10374, immediately after (1).
3. **Repair escalation override** — lines 10402–10426, gated on `_repair_attempt_count >= 2`, independent of `_prev_counter_reply`/mirror-topic state and independent of `user_asked_question`.
4. **Final ASR-junk text repair** — lines 12407–12415, `response["counter_reply"] = _repair_asr_junk_text(_cr_final)` (string case) or `_cr_final["zh"] = _repair_asr_junk_text(...)` (dict case). This is the **second and last** direct assignment site to `response["counter_reply"]` found anywhere in the file (the first is the initial assembly at line 11817). It runs after frame selection, discovery-panel assembly, and session-end handling — immediately before the response is serialised and sent (line 12418). It strips known ASR-junk fragments (e.g. `"等你等…"`) from whatever Chinese text is already in `response["counter_reply"]`, whatever path produced it.

   **Evidenced gap:** mechanism (4) rewrites only the Chinese text field of the response. It does not recompute `response["counter_reply_en"]` or `response["counter_reply_pinyin"]`, both of which were already fixed at their pre-existing values (from §13/§14, computed at lines ≤10428, long before line 12413 runs). If a junk fragment is actually stripped by this pass, the resulting Chinese can diverge from the English/pinyin already attached to the same turn's response. This is recorded as an evidenced ordering characteristic of mechanism (4), not a demonstrated production failure — no test was found asserting English/pinyin re-synchronisation after this specific repair pass.

### 3.4 Early-return answer producers outside the main chain

**None found.** An exhaustive search of `response["counter_reply"] =`, `response.get("counter_reply")`, `_counter_reply`, and `_counter_result` across `scripts/ui_server.py` locates exactly two direct-assignment sites to `response["counter_reply"]` (line 11817, the main-chain result; line 12413, mechanism (4) above) and zero occurrences in any other request handler, early-return branch, or error path. There is no early-return producer to document as a separate answer-source category at R2.

### 3.5 Response-assembly-only assignments that transport an already-final answer

* Line 11817 — `response["counter_reply"] = _counter_reply` — the primary transport of the fully-finalised value (post-priority-chain, post-dedup, post-repair-escalation) into the response payload.
* `_diag_finalize_response()` (lines 217–238) — reads `response.get("counter_reply")` purely to populate a diagnostics record (`cap["response_source"]`, `cap["final_response_text"]`); it is a **consumer**, not a producer, and never mutates `response["counter_reply"]`.

---

## 4. Priority-chain inventory

The chain is **not** a single flat `if/elif`. It is five separate structural groups, in this exact top-to-bottom execution order. Precision on empty-result semantics (verified directly against the Python source, not inferred): in Groups 1 and 2, each is a single `if`/`elif` chain keyed on the **trigger condition itself**, not on whether the callee inside the matched branch returns a usable result. Consequently, once a condition evaluates `True` and its `elif` branch is entered, **no lower `elif` in the same group is ever evaluated**, even if the code inside the matched branch itself decides not to assign `_counter_result` (e.g. because the branch's own helper returned an empty/`None` result). This is a genuine dead-end for that turn's chain, not a fallthrough — this correction applies equally to Group 1 (§4.1) and Group 2 (§4.2); an earlier draft of this document incorrectly stated that an empty Group-1 result falls through to the next priority.

* **Group 1** (lines 9902–9940): `if _counter_result is None and answer_text:` guarding a nested `if`/`elif`/`elif`/`elif`/`elif` — five mutually exclusive user-initiative branches, keyed on the boolean trigger, not on the helper's return value.
* **Group 2** (lines 10027–10182): a single flat `if`/`elif` chain of twelve branches (one `pass`, eleven condition/answer pairs), keyed the same way as Group 1.
* **Group 3** (lines 10187–10208): an independent `if _counter_result is None:` — the F2 "why do you like X" adjacency guard.
* **Group 4** (lines 10215–10222): an independent `if _counter_result is None and user_asked_question and _recent_persona_replies:` — E3 working memory.
* **Group 5** (lines 10228–10283): an independent `if _counter_result is None:` containing the mirror bank / `_answer_user_question_prefix` call, and, nested inside its `else` branch, two **sequential** (not `elif`) guarded `if` statements — the generic-deflection bypass and the confusion-with-question-mark fallback — the second of which explicitly re-checks `not _counter_result`, making the two mutually exclusive in practice despite not being written as `elif`.

### 4.1 Reconciled priority and branch counts

| Metric | Count |
|---|---|
| Aggregate priority slots (1–21 individually numbered, plus one aggregate slot 22 covering 22a/22b) | 22 |
| Concrete conditional branches (every distinct `if`/`elif` arm actually present in the source, including the two sub-arms of slot 22) | 23 |
| Control-only branches (§3.2) | 2 |
| Concrete answer-producing branches (23 − 2) | 21 |
| Post-chain answer replacement mechanisms (§3.3) | 4 |
| Early-return answer producers outside the main chain (§3.4) | 0 |

Per-group concrete-branch breakdown: Group 1 = 5 (Priorities 1–5); Group 2 = 12 (Priority 6 pass-through + Priorities 7–17); Group 3 = 1 (Priority 18); Group 4 = 1 (Priority 19); Group 5 = 4 (Priorities 20, 21, 22a, 22b). Total = 5 + 12 + 1 + 1 + 4 = 23, matching the table above.

### 4.2 Ordered inventory

| Priority | Answer source | Trigger | Function(s) | Chinese source | English source | Empty-result behaviour |
|---|---|---|---|---|---|---|
| 1 | Frustration/insult repair | `_is_frustration_or_insult(answer_text)` (line 9903) | `_frustration_repair_reply()` | `content/recovery_phrases.json` (`use=frustration_repair`) | Same tuple | If the callee returns empty, **no lower Group-1 branch runs this turn** — the trigger condition, not the return value, drives the `elif` chain |
| 2 | Learner disclosure empathy | `_is_learner_disclosure(answer_text)` (line 9909) | `_disclosure_empathy_reply()` | `content/recovery_phrases.json` (`use=learner_disclosure_empathy`) | Same tuple | Same dead-end semantics as Priority 1 |
| 3 | Persona challenge reply | `_is_persona_challenge(answer_text)` (line 9917) | `_persona_challenge_reply()` | `content/recovery_phrases.json` (`use=persona_challenge`) | Same tuple | Same dead-end semantics |
| 4 | Responsive food answer | `_responsive_food_answer` flag (line 9925; computed lines 9227–9234) | `_food_responsive_reply()` | Extracted food items / inline pool | Same tuple | Same dead-end semantics |
| 5 | Volunteered travel intent | `not user_asked_question and _has_volunteered_travel_intent(answer_text)` (line 9936) | `_travel_intent_followup()` | `content/recovery_phrases.json` (`use=travel_intent_followup`) | Same tuple | Same dead-end semantics |
| 6 | Retain user-initiative answer (control-only) | `_counter_result is not None` (line 10027) | — (pass-through) | n/a | n/a | n/a |
| 7 | Explicit place-topic answer | Precomputed `_explicit_place_topic_result` (lines 9997–10025); consumed line 10031 | `_repair_contextual_place_question()` + `_direct_persona_answer()` + `_persona_answer_en()` | `_direct_persona_answer()` intent families (§5) | `_persona_answer_en()` | If `_explicit_place_topic_result is None`, falls to Priority 8 (this precomputation, unlike the elif branches below it, is evaluated once before the chain and stored, so its "miss" case is a normal `elif` fallthrough to the next condition in the chain, not a dead end) |
| 8 | Meaning recovery | `_is_meaning` (line 10033) | `_meaning_recovery_reply()` | `_MEANING_RECOVERY_TABLE` (inline) | Same tuple | If `last_partner_frame_text` is empty, no lower Group-2 branch runs this turn |
| 9 | Example request → clarify | `_is_example` (line 10038) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | Same dead-end semantics |
| 10 | Repeat/slower request → clarify | `_is_rr` (line 10046) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | Same dead-end semantics |
| 11 | Lexical definition | `_lex_ct` precomputed (lines 9945–9947), consumed line 10051 | `_lexical_definition_reply()` | Inline keyword table | Same tuple | If `None`, falls to Priority 12 (precomputed, same reasoning as Priority 7) |
| 12 | Stale-counter-reply override (direct persona) | `_prev_counter_reply` + `_is_direct_persona_question` + not confusion (lines 10053–10058) | `_direct_persona_answer()` + `_persona_answer_en()` | §5 intent families | `_persona_answer_en()` | If `_direct_persona_answer()` returns `None` or the result equals `_prev_counter_reply`, no lower Group-2 branch runs this turn |
| 13 | Mirror confusion escalation ladder | Confusion signal + active `_cs_mirror_topic`, not a question, not direct-persona (lines 10088–10094) | `_mirror_restate_naturally()` / `_mirror_persona_stub_simple()` / `_confusion_recovery_reply()` (staged by `_cs_mirror_conf`) | Prior mirror answer / `discoverable_facts_simple` / voice_lines / generic pool | Same tuple | Every internal stage unconditionally assigns `_counter_result`; no dead-end case within this branch |
| 14 | Generic confusion recovery (no mirror topic) | Same confusion guard, `not _cs_mirror_topic` (lines 10115–10121) | `_confusion_recovery_reply()` | 4-entry inline pool | Same tuple | Unconditional assignment |
| 15 | App-question clarification (no prior counter_reply) | `not _prev_counter_reply` + confusion signal + `not user_asked_question` + `not _confirmed_re_ask` (lines 10126–10131) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | If frame text empty, no lower Group-2 branch runs this turn |
| 16 | Noisy location (control-only, §3.2) | `"CITY" in slot_names` + no resolvable location + other guards (lines 10141–10148) | *(none — flag-only)* | n/a | n/a | Always a dead end for this turn's `counter_reply` (by design — the intended effect is a later `frame_text` override) |
| 17 | Pending-frame commitment clarification | `not _prev_counter_reply` + `last_answer_fid in _COMMITMENT_GUARD_FRAMES` + off-topic (lines 10162–10171) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | If frame text empty or `_clarify_app_question()` returns `None`, this is the last Group-2 branch, so the chain simply proceeds to Groups 3–5 |
| 18 | F2 "why do you like X" adjacency | `_is_why_like_follow_up()` + `_cs_mirror_engine` in work/hobby/place/food/travel + persona (lines 10193–10197) | Inline construction from `voice_lines[engine]` | `voice_lines[engine]` or inline template | Inline template (empty when voice_line used) | Independent `if _counter_result is None:` gate (Group 3) — a miss here proceeds normally to Group 4 |
| 19 | E3 working-memory answer | `user_asked_question and _recent_persona_replies` (line 10215) | `_extract_persona_facts_from_recent()` + `_answer_from_working_memory()` | Facts extracted from `recent_persona_replies` | Same tuple (often `""`) | Independent gate (Group 4) — a miss proceeds normally to Group 5 |
| 20 | Mirror bank | `user_asked_question` (line 10236) | `_find_mirror_answer()` → `_mirror_persona_stub()` | `content/mirror_questions.json` topic → persona facts | `_mirror_persona_stub()` (often `""`) | If no match, the same `if/else` (line 10237/10242) falls to Priority 21 within the same statement — not a dead end |
| 21 | General answer prefix (`_answer_user_question_prefix`) | Mirror miss or `not user_asked_question` (line 10242); internal sub-chain (§5–§7, §16) | `_answer_user_question_prefix()` | Varies by sub-step | Varies | `_persona_limitation_reply()` is an unconditional final fallback inside this function, so Priority 21 always assigns *some* result once reached |
| 22a | Generic-deflection bypass | Result ∈ `_persona_deflect_phrases["generic"]` and `not user_asked_question` (lines 10256–10261) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | Sequential `if` (not `elif`) nested inside Priority 21's `else` branch; if the bypass condition or `_clarify_app_question()` fails, `_counter_result` retains Priority 21's original value |
| 22b | Confusion signal with question mark (post-prefix fallback) | `user_asked_question and not _counter_result and _is_confusion_signal(answer_text)` (lines 10273–10276) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | Sequential `if`, explicitly guarded on `not _counter_result` so it never overwrites 22a's result; if this also fails, `_counter_result` remains whatever Priority 21 (possibly `None`, if `_persona_limitation_reply` itself was bypassed by an earlier `return` inside the prefix function) left it as |

### 4.3 Post-priority-chain mechanisms (not priority-numbered)

Listed here in their exact execution order, all running after Priority 22b and after E4 eligibility has already been computed (§15):

1. **Deduplication** (`_dedupe_persona_answer`, lines 10352–10367) — §8, §12.
2. **Exact-repeat belt-and-suspenders guard** (lines 10372–10374) — §12.
3. **Repair escalation** (lines 10402–10426) — §9.
4. **Final ASR-junk text repair** (lines 12407–12415) — §3.3(4).

---

## 5. Direct persona-answer contract

`_direct_persona_answer(t, persona, recent_replies=None)` (defined starting at `scripts/ui_server.py:3057`) returns `Optional[str]` (**Chinese only**); the caller always wraps the result with a `我呢，` prefix (unless it already starts with `我`) and calls `_persona_answer_en()` for English. This function is a **single, strictly first-match sequence** of 42 recognised intent families.

| # | Intent family | Recognition patterns | Persona data source | Chinese construction | Fallback | English resolution | Topic engine |
|---|---|---|---|---|---|---|---|
| 1 | Place name where persona lives | `"那里叫什么"`, `"那儿叫什么"`, `"你那里叫"`, `"你那儿叫"` | `profile.city`/`.hometown`, `voice_lines.place` | `"我住的地方叫{loc}。"` | `voice_lines.place` → `"我住在中国，你有没有来过？"` | Deferred | `place` |
| 2 | Hometown/origin | `"你老家"`, `"你的老家"`, `"你家乡"`, `"你的家乡"`, `"家乡在哪"`, `"家乡是哪"`, `"你是哪里人"`, `"你从哪里来"`, `"你哪里人"` | `profile.hometown`, `voice_lines.place` | `"我老家在{hometown}。"` | `voice_lines.place` → `"我老家在中国。"` | Deferred; intent `hometown_where` | `place` |
| 3 | Current residence | `"你住在哪"`, `"你住哪"`, `"你现在住"`, `"你住的地方"` | `profile.city/.hometown`, `voice_lines.place` | `"我住在{city}。"` | `voice_lines.place` chain → `"我在中国住。"` | Deferred | `place` |
| 4 | Name meaning | `"你的名字是什么意思"` + variants | `discoverable_facts.identity` | Fact verbatim | Inline template with `name` | Deferred; `discoverable_facts_en.identity` | `identity` |
| 5 | Name story/origin | `"名字有什么故事"` + variants | `discoverable_facts.identity` | Fact verbatim | Inline template | Deferred | `identity` |
| 6 | Name story via persona's actual name | `name in t` + story markers | `discoverable_facts.identity` | Fact verbatim | Inline template with `name` | Deferred | `identity` |
| 7 | Name / how to address | `"你叫什么"`, `"怎么叫你"` + variants | `display_name` | `"你可以叫我{name}。"` | Returns `None` if `name` empty | Deferred | `identity` |
| 8 | Still live there? | `"还住在那里"` + variants | `profile.city/.hometown` | Branch on city==hometown vs different | Inline template | Deferred | `place` |
| 9 | Cooking / dishes | `_is_cooking_question` (lines 3821–3835) | `discoverable_facts.food`, `voice_lines.food`, cooking phrase bank (`content/recovery_phrases.json`, `use=persona_cooking_reply`) | Fact → voice_line → bank pick | `None` if bank empty | Deferred; `discoverable_facts_en.food` or phrase `text_en` | `food` |
| 10 | Job/occupation | `"你做什么工作"` + variants | `voice_lines.work` checked before `profile.occupation` construction | voice_line preferred, else `"我是{occ}。"` | `"我也有工作。"` | Deferred; intent `job` | `work` |
| 11 | Travel — visited | `"你去过哪里"` + variants | `discoverable_facts.travel_where/.travel`, `voice_lines.travel` | Fact verbatim | `voice_lines.travel` → `"我去过几个城市，很有意思。"` | Deferred | `travel` |
| 12 | Favourite place | `"最喜欢"` + place marker | Same as #11 | Fact verbatim | `voice_lines.travel` → `"我去过几个地方，各有特色。"` | Deferred | `travel` |
| 13 | Food-preference comparison (A vs B) | `"菜/吃"` + comparator + preference marker | None (inline logic) | Inline template with extracted dish names | `"两个我都喜欢，各有各的味道。"` | Deferred (no persona source) | `food` |
| 14 | 你喜欢…吗 (city/hobby/food) | `t.startswith("你喜欢")` + `吗/呢/啊` | `profile.city/.hometown`, `voice_lines.hobby/.food`, inline `_CITY_LIKE_POOL` | Keyword-dependent branch | `"还挺喜欢的，你呢？"` | Deferred | `place`/`hobby`/`food` (keyword-dependent) |
| 15 | Hobbies/interests | `"你有什么爱好"` + variants | `profile.interests[0]`, `voice_lines.hobby` | voice_line or `"我喜欢{interests[0]}。"` | `"我也有很多爱好。"` | Deferred; `voice_lines_en.hobby` | `hobby` |
| 16 | Who partner lives with | `"跟谁住"` + variants | `voice_lines.family` | voice_line verbatim | `"我现在自己住，但和家人经常联系。"` | Deferred | `family` |
| 17 | Sibling presence | `"你有姐妹/兄弟/哥/弟/姐/妹"` + variants | `discoverable_facts.family_siblings/.family` | First clause / negation check | `"我有几个兄弟姐妹，大家关系挺好的。"` | Deferred; `discoverable_facts_en.family_siblings` | `family` |
| 18 | Parents presence | `"你有爸爸妈妈"` + variants | `profile.age` (computed parent-age offset) | `"有的，他们大概{p_age}多岁了，住在老家。"` | `"有的，我爸妈都在，住在老家。"` | Deferred | `family` |
| 19 | Family location | `"家人在哪"` + variants | `discoverable_facts.family_live`, `profile.hometown/.city` | Fact or comparison template | `"家人在{loc}那边。"` / `"家人住得不太远。"` | Deferred; `discoverable_facts_en.family_live` | `family` |
| 20 | Has family (generic) | `"你有家人"` + variants | `voice_lines.family` | voice_line | `"我也有家人。"` | Deferred | `family` |
| 21 | Parent detail (age vs location) | `"你妈妈/爸爸/父母/爸妈"` + variants | `profile.age` (offset) or `voice_lines.family`/`discoverable_facts.family_live` | Age or location sub-branch | `"他们五十多岁了。"` / `"我父母住得不太远。"` | Deferred (age intent may misfire for parent age — see §13's narrowed-branch note) | `family` |
| 22 | Sibling detail (age/work/location) | `"姐姐/哥哥/弟弟/妹妹"` present | `profile.age/.city/.hometown` (computed) | Sub-intent-dependent template | `"我有一个{sib}，我们偶尔联系。"` | Deferred | `family` |
| 23 | Work enjoyment | `"喜欢"` + `"工作"` marker | `voice_lines.work_like` *(schema-optional, absent in current personas)*, `discoverable_facts.work`, `profile.occupation` | Chain of the above | `"还挺喜欢的，慢慢就越来越有意思了。"` | Deferred | `work` |
| 24 | Hobby duration | `"玩这个多久"` + variants | `discoverable_facts.hobby` | Full fact (often contains duration) | `"已经玩了好几年了，越来越喜欢。"` | Deferred | `hobby` |
| 25 | Hobby origin | `"怎么开始这个爱好"` + variants | `discoverable_facts.hobby_origin` | Fact verbatim | `"小时候接触到，慢慢就喜欢上了，一直坚持到现在。"` | Deferred; `discoverable_facts_en.hobby_origin` | `hobby` |
| 26 | Hobby best aspect | `"最喜欢这个爱好的哪一点"` + variants | `discoverable_facts.hobby_best` | Fact verbatim | `"让我放松的那种感觉，做完以后心情很好。"` | Deferred | `hobby` |
| 27 | Why like hobby | `"为什么喜欢这个爱好"` + variants | `discoverable_facts.hobby_best/.hobby_origin` | Best-fact or origin-fact | `"很难说具体原因，就是喜欢那种感觉，做了就停不下来。"` | Deferred | `hobby` |
| 28 | Place food — what's good to eat | `_is_place_food_question` (lines 3769–3783) | `discoverable_facts.food` (place-matched), inline `_CITY_FOOD_POOL`, `_place_from_question_context()` | Personal fact if place==persona city/hometown, else pool pick | Falls through to feature handler (#29) if no pool/fact match | Deferred; intent `hometown_food` | `food`/`place` |
| 29 | Place features — what's special | `_is_place_feature_question` (lines 3797–3818) | Inline `_CITY_FEATURE_POOL`, `discoverable_facts.travel_where/.travel/.place`, `profile.city/.hometown` | Pool pick → travel-fact clause → city pool → place fact | `"哎，{loc}太有特色了，说也说不完！"` / `"那个地方很有特色，有机会可以去看看！"` | Deferred; intent `hometown_special` (EN deliberately `""` — see §13) | `place`/`travel` |
| 30 | Marriage/relationship status | `"你结婚"` + variants | `discoverable_facts.marriage` *(optional; absent in current sample personas)* | Fact verbatim | `_persona_deflect("marriage", t)` | Deferred via deflect EN map | `family` |
| 31 | Children | `"你有孩子/小孩/儿子/女儿/宝宝"` | **None read** — always deflects | n/a | `_persona_deflect("children", t)` only | Deferred via deflect EN map | `family` |
| 32 | Work difficulty/quality | `"难不难/累不累/辛不辛苦"` + variants | `profile.occupation`, `voice_lines.work` | voice_line or inline template | `"工作嘛，有时候忙，但还可以，挺有意思的。"` | Deferred | `work` |
| 33 | Age (persona's own) | `"你多大/几岁/年龄"` | `profile.age` | `"我今年{age}岁。"` | `_persona_deflect("age", t)` | Deferred; intent `age` | `identity` |
| 34 | Family closeness | `"和爸爸妈妈近"` + variants | `discoverable_facts.family_live/.family` | Fact or first-clause extraction | `"挺近的，虽然不住在一起，但经常打电话联系。"` | Deferred | `family` |
| 35 | Why like a place | `"为什么喜欢那里"` + variants | `discoverable_facts.travel/.travel_where/.place`, `profile.city/.hometown` | Extracted why-clause | `"感觉那里很有特色，生活节奏和文化都挺吸引人的。"` | Deferred | `travel`/`place` |
| 36 | Bare 为什么/为啥 follow-up | Exact strings `"为什么"`, `"为啥"`, `"为啥呢"`, `"为什么呢"` | `profile.hometown`, `voice_lines.place/.work/.food` | Stable pool pick | `"因为习惯了，也比较熟悉。"` / `"因为我觉得挺合适的，慢慢就更喜欢了。"` | Deferred | *(no frame; generic follow-up)* |
| 37 | Where has long history | `"历史"` + place marker | `profile.hometown` | `"像{ht}这样的地方，历史就很长。你慢慢会发现很多细节。"` | `"很多地方都有很长的历史，你慢慢看会发现很多细节。"` | Deferred | `place` |
| 38 | Work duration | `"工作多久/做了多久"` + variants | `discoverable_facts.work`, `profile.occupation` | Duration clause extraction | `"做{occ}已经好几年了，越来越有经验了。"` / `"已经做了几年了，越做越有意思。"` | Deferred; intent `work_duration` | `work` |
| 39 | Extended family location | `"奶奶/爷爷/外婆/外公/姥姥/姥爷"` present | `profile.hometown/.city` | `"我{rel}住在{ht}那边，离我有点远。"` etc. | `"我{rel}住在老家，我们不常见面，但会联系。"` | Deferred | `family` |
| 40 | Distance — far or not | `"离那边/北京/上海/成都/广州远"` | `distance_profile.zh/.far_level/.reference`, `profile.hometown` | `distance_profile.zh` verbatim or template | `"不算太远。"` | Deferred; `distance_profile.en` | `place`/`travel` |
| 41 | Travel time to place | `"要多久/多久到/多长时间"` | `distance_profile.time/.transport` | `"坐{transport}要{time}左右。"` | Default `"几个小时"`/`"交通工具"` | Deferred | `place`/`travel` |
| 42 | How to get there | `"怎么去/坐什么去/怎样去"` | `distance_profile.transport` | `"一般坐{transport}去。"` | Default `"高铁"` | Deferred | `place`/`travel` |

**Precedence rules enforced by code order and comments:** #1 before #2 before #3; #4–#7 before #10; #9 before #10 (explicit comment); #28 before #29 (explicit comment); #17 before #22; #38 before #41.

**Inline Chinese fallback content:** a large volume of hardcoded Chinese exists directly in `_direct_persona_answer` and is **not** sourced from persona JSON — every per-branch fallback template listed above, and three large encyclopedic pools: `_CITY_LIKE_POOL` (#14), `_CITY_FOOD_POOL` (#28), and `_CITY_FEATURE_POOL` (#29). These pools are covered further in §10 and §18.

**`_answer_user_question_prefix` integration:** before reaching `_direct_persona_answer` (as one internal sub-step, §16), the prefix function first tries a confusion guard, `_place_followup_reply`, `_find_mirror_answer` (a **second** mirror attempt distinct from Priority 20 in §4), and `_place_distance_counter_reply`. `_is_direct_persona_question(t)` is a separate **pattern probe** that calls `_direct_persona_answer(t, None)` with `persona=None` — it only tests whether *any* branch would structurally match, not whether persona data exists to answer it.

---

## 6. Persona-data precedence

Precedence is **not uniform** across intent families; it is decided per family by the order fields are checked inside `_direct_persona_answer`. Recurring patterns:

* **Structured fact before generic template** for most families (e.g. #4 name meaning: `discoverable_facts.identity` → inline template).
* **`voice_lines` outranking a raw `profile` field for some families but not others** — e.g. #10 job checks `voice_lines.work` before constructing from `profile.occupation`; this precedence is family-specific and must not be assumed uniform.
* **`distance_profile` is authoritative and exclusive** for #40–#42; no fallback to `discoverable_facts`/`voice_lines` exists there.
* **Inline city pools outrank persona `discoverable_facts.food`/`.place` when the question names a city that is not the persona's own** (#28, #29), because persona JSON has no data about third-party places.
* **`_persona_deflect("<topic>", t)` overrides absent facts** for `marriage` (#30), `children` (#31, always), and `age` (#33, when `profile.age` is falsy).

**Duplicate/competing sources of the same fact:** hometown location can be answered by `profile.hometown` (families #2, #3, #37) **or** by `_CITY_LOCATION_BRIEF` (used only by `_place_followup_reply`, not by `_direct_persona_answer`); place "features" content exists in two independent pools depending on call path (`_CITY_FEATURE_POOL` inside `_direct_persona_answer`, `_FEAT_POOL_INLINE` inside `_dedupe_persona_answer`); place "food" content similarly exists in `_CITY_FOOD_POOL` and `_FOOD_POOL_INLINE`. These are separately maintained literals that can diverge.

---

## 7. Mirror and reverse-fact answers

### 7.1 Mirror bank

`_find_mirror_answer(text, engine_id, persona)` is invoked from two call sites: Priority 20 in the main chain (gated on `user_asked_question`) and again as an internal sub-step inside `_answer_user_question_prefix` (a **second, independent attempt** using potentially different input text).

Mirror topic records are loaded from `content/mirror_questions.json` into `_MIRROR_QUESTIONS_BY_ENGINE`. Each record contains at minimum `zh` (canonical question text, matched by substring/exact match), `topic` (consumed by `_mirror_persona_stub` and by `_QUESTION_TOPIC_TO_ENGINE` for E4), and an optional `paraphrases` array compiled at startup into `_MIRROR_FUZZY` for fuzzy all-keywords-present matching. Chinese and English are both produced by `_mirror_persona_stub(topic, engine_id, persona)`, which reads `discoverable_facts`, `discoverable_facts_en`, `voice_lines`, `voice_lines_en`, `profile`, and `distance_profile` keyed by `topic`. Many branches return `""` for English.

**E4 participation:** mirror topic metadata feeds E4 through a dedicated lookup table, `_QUESTION_TOPIC_TO_ENGINE`, keyed on `_new_mirror_topic` — a different mechanism from the text classifier (`_infer_question_topic_engine()`) used by E3/direct-persona answers (§15). If `_new_mirror_topic` is not a key in that table, `_e4_engine_handoff` stays `None` even though a mirror answer was produced.

**When mirror content is stale or unavailable:** `_find_mirror_answer` returns `None` when no exact/fuzzy match is found; the caller falls through to `_answer_user_question_prefix`, which retries the mirror bank internally before trying place-distance, direct-persona, and fallback paths. Staleness of a **previously given** mirror answer is a separate mechanism entirely — the mirror-confusion escalation ladder (Priority 13, §9).

### 7.2 Reverse-fact answers

`_detect_reverse_fact_intent(text)` classifies a direct-question text into one of eight intents: `marriage`, `age`, `hometown_food`, `hometown_special`, `work_duration`, `work_reason`, `job`, `hometown_where`.

`_reverse_fact_answer(intent, persona)` returns a **Chinese** string derived from `profile`/`discoverable_facts`/`voice_lines` for that intent, plus a ninth intent (`hometown_location`) that `_reverse_fact_answer` handles but `_detect_reverse_fact_intent` never returns.

`_reverse_fact_answer_en(intent, persona)` returns the paired **English**, with an explicit code comment (the RC-EN invariant) documenting that branches must return `""` rather than an incorrect gloss whenever the same intent string is triggered by structurally different questions (e.g. `age` fires for both the persona's own age and a parent's age).

**`_reverse_fact_answer()` (Chinese) production reachability — conclusively resolved.** A repository-wide search for every call site of `_reverse_fact_answer(` finds exactly:

* its own definition;
* one comment inside `_dedupe_persona_answer()`'s docstring and body explicitly **prohibiting** its use (quoted below);
* two call sites in `tests/test_regression_place_travel_reverse.py` (direct unit-test invocation only).

There is **no production call site** anywhere in `scripts/ui_server.py`'s request handlers. `_reverse_fact_answer()` (Chinese) is unreachable from `/api/run_turn` at the R2 baseline. This is not merely absence of evidence — the code contains an explicit, currently-in-force guard against reintroducing the call:

```text
scripts/ui_server.py, _dedupe_persona_answer() docstring and body (paraphrased, not verbatim):
  "... Only if the same-intent pool is exhausted, use a topically appropriate
  clarification phrase rather than an unrelated fact from _reverse_fact_answer.
  Never use _reverse_fact_answer(intent) as the first alternative — intents like
  'hometown_special' resolve to facts['place'] which can be for a different city
  than the one actually asked about. ... Never cross-intent via
  _reverse_fact_answer — that can return a fact for a different city/topic than
  what the learner asked (the RC-A failure mode)."
```

**Historical origin of the conflict, resolved:** `_reverse_fact_answer()` **was** production-reachable prior to commit `657529a` ("fix: resolve stale-answer loop via RC-A / RC-B / RC-C", 2026-07-11). That commit's own message documents the regression directly: `_dedupe_persona_answer()` previously called `_reverse_fact_answer` as its cross-intent fallback when a candidate repeated, and this could "return a fact for a different city/intent" than the one the learner actually asked about (the RC-A failure mode). Commit `657529a` removed that call and replaced it with the current two-step mechanism — same-intent pool re-pick (§12 Step 1), then generic deflection (§12 Step 2) — and left the quoted guard comment in place specifically to prevent the call from being reintroduced. This commit is verifiable via `git log -S "_reverse_fact_answer(intent)" -- scripts/ui_server.py`, which returns exactly one match: `657529a`.

**Distinguishing the two historical regressions (they are not the same defect):** the RC-A regression above concerns the **Chinese** dedup fallback (fixed by removing the `_reverse_fact_answer` call entirely). The separately-documented RC-EN regression (§13; `tests/test_zh_en_synchronisation.py`, first-bad commit `0177994`) concerns the **English** gloss returned by `_reverse_fact_answer_en()` for dynamically-constructed Chinese, and was fixed by narrowing specific branches to return `""` rather than by removing any call — `_reverse_fact_answer_en()` **is** production-reachable (§13, stage 3) even though `_reverse_fact_answer()` (Chinese) is not. The apparent conflict the prior draft of this document did not resolve is exactly this: two distinctly-named but easily-conflated functions, one dead in production, one live.

**Practical consequence for production Chinese:** Chinese answers always come from `_direct_persona_answer` or the mirror bank; `_reverse_fact_answer_en(intent, ...)` is the only reverse-fact function actually reachable in production, called from `_persona_answer_en()` using the intent computed from the **question text**, independent of which function produced the Chinese candidate.

### 7.3 Answering from persona facts vs. recent conversational context

`_direct_persona_answer` and the reverse-fact functions answer strictly from **persona JSON**, regardless of conversation history. Answering from **recent conversational context** instead is the distinct responsibility of E3 working memory (§8), which reads `recent_persona_replies`, not persona JSON directly.

---

## 8. E3 working-memory answers

`_extract_persona_facts_from_recent(recent_replies)` is a bounded, deterministic scan of the **last 5 entries** of the `recent_persona_replies` list, returning a dict that may contain `travel_visited`, `travel_fav`, `city_now`, `hometown`, `food_spicy`, `family_members`, and `work_desc`. This is a **pure read**; it does not write to conversation state.

`_answer_from_working_memory(text, facts, persona)` matches the current question text against a fixed sequence of category checks — travel favourite, travel visited, food-spicy preference, hometown, current city, family — in that documented priority order, returning `Optional[(zh, en)]`. Several branches return `""` for English. `work_desc` is extracted but **never read** by `_answer_from_working_memory` — a dead extraction.

**Confidence:** no numeric score. E3 is used when (a) `_counter_result is None`, (b) `user_asked_question` is true, (c) `_recent_persona_replies` is non-empty, and (d) both extraction and answer-matching succeed for the specific question-text pattern. Any pattern miss returns `None`.

**Priority relative to direct-answer and mirror:** E3 (Priority 19) runs **after** the F2 adjacency guard (Priority 18) and **before** the mirror bank/prefix (Priority 20–21), so a matching E3 fact pre-empts both.

**E4 participation:** E3 answers can trigger E4 — `_counter_is_working_memory` is set `True`, and E4 computation (§15) uses `_infer_question_topic_engine()` on the raw `submitted_text` of the last answer, the same classifier used by the direct-persona E4 path but a different mechanism from the mirror bank's topic-map lookup.

**Three-entry cap effect:** `recent_persona_replies` is capped to the **last 3** entries when written back to `state_update`, but `_extract_persona_facts_from_recent` scans up to 5. Under normal round-trip operation the effective window is 3.

**Not persistent learner memory:** E3 operates strictly on `recent_persona_replies`, a short rolling window of the **persona's own** recent answers; it is unrelated to persistent learner-fact storage (§10, §17).

---

## 9. Recovery and repair answers

All recovery paths below run inside the `last_turn_was_answer` gate. Producing a `counter_reply` here does **not** guarantee the frame ladder "advances" in the sense of moving to a new topic — the precise, evidenced statement is: **normal server frame selection still runs afterward in the same turn; depending on the frame-selection guards in effect (e.g. the pending-frame commitment guard, or a mirror-topic same-engine preference), the next frame may advance to a new topic, remain within the same engine, or be explicitly repeated/rephrased.** Separately, **client-intercepted spoken recovery** (a client-side mechanism outside the scope of this server-side document, described in `docs/CONVERSATION_ARCHITECTURE.md`) makes no server request at all for certain recovery utterances, and by construction preserves whatever semantic frame state already existed client-side, since no turn is submitted to the server.

| Recovery path | Trigger | Answer function | Produces new `counter_reply`? | Frame selection in the same turn |
|---|---|---|---|---|
| Meaning request | `_is_meaning` | `_meaning_recovery_reply(last_partner_frame_text)` | Yes, only if `last_partner_frame_text` non-empty | Runs normally; sets `_confusion_about_app_q` flag, read by later frame/discovery-panel logic |
| Example request | `_is_example` | `_clarify_app_question(last_partner_frame_text)` | Yes, when frame text present | Runs normally |
| Repeat/slower request | `_is_rr` | `_clarify_app_question(last_partner_frame_text)` | Yes, when frame text present | Runs normally |
| App-question confusion (no prior counter_reply) | Confusion signal, no `_prev_counter_reply`, `not user_asked_question`, not confirmed-re-ask | `_clarify_app_question(last_partner_frame_text)` | Yes, when frame text present | Runs normally |
| Mirror confusion (Stage 1: restate) | Confusion signal + active `_cs_mirror_topic`, `mirror_confusion_count == 0` | `_mirror_restate_naturally(prev_counter_reply, mirror_topic)` | Yes | Runs normally, subject to same-engine preference tied to the active mirror topic where applicable |
| Mirror confusion (Stage 2: simplify) | Same guard, `mirror_confusion_count == 1` | `_mirror_persona_stub_simple(mirror_topic, mirror_engine, persona)` | Yes | Same as above |
| Mirror confusion (Stage 3+: generic recovery) | Same guard, `mirror_confusion_count >= 2` | `_confusion_recovery_reply(text, prev_counter_reply, seed)` | Yes | Runs normally |
| Generic confusion (no active mirror topic) | Confusion signal, `_prev_counter_reply` present, no mirror topic | `_confusion_recovery_reply(text, prev_counter_reply, seed)` | Yes | Runs normally |
| Frustration/insult repair | `_is_frustration_or_insult(answer_text)` (highest priority) | `_frustration_repair_reply(seed)` | Yes, unless phrase bank unloaded | Runs normally; suppresses `reaction_prefix_text` |
| Learner-disclosure empathy | `_is_learner_disclosure(answer_text)` | `_disclosure_empathy_reply(seed)` | Yes | Runs normally |
| Persona challenge | `_is_persona_challenge(answer_text)` | `_persona_challenge_reply(seed)` | Yes | Runs normally |
| Pending-frame commitment clarification | Off-topic answer to a `_COMMITMENT_GUARD_FRAMES` frame, no explicit topic switch, no relevance match | `_clarify_app_question(last_partner_frame_text)` | Yes, when frame text present | Frame selection is explicitly guarded to remain in the same engine for this specific path (`listening_move_reason = "offtopic_pending_frame"`) |
| Noisy-location clarification | `"CITY" in slot_names`, no resolvable location, other guards | *(none — flag-only, §3.2/§4 Priority 16)* | **No** — this is a `frame_text` override, not a `counter_reply` producer | A dedicated post-response frame-text rewrite escalates by retry count |

**Cross-turn state completeness — exact `STATE_CONTRACT.md` references:** the mirror-confusion escalation ladder's cross-turn persistence gap is documented in `docs/STATE_CONTRACT.md` as **SIC-1** ("Mirror-confusion escalation should persist across turns"). The noisy-location/destination-clarify cross-turn round-trip gap (`location_retry_count`, `location_clarify_hint`, `pending_dest_candidate`) is documented there as **SIC-2**. The now-resolved E4 client-consumption defect is documented there as **historical SIC-6** (Section 16.3, a resolved defect record, not an open gap). SIC-1 and SIC-2 both remain open gaps as of the R2 baseline; SIC-6 is closed and is cited here only to avoid conflating it with SIC-2 — an earlier draft of this document incorrectly attributed the noisy-location gap to SIC-6.

**Repair escalation (post-chain, not in the priority table, §4.3):** lines 10402–10426. Trigger: `last_turn_was_answer`, `_is_confusion_signal(answer_text)`, `_repair_attempt_count >= 2`, plus additional guards (`not _confirmed_re_ask`, `not _is_plain_affirmation`, `not _is_place_description`). Notably, this trigger has **no explicit `user_asked_question` check at all** in either direction (§15). This directly overwrites `_counter_reply`/`_counter_reply_en` with one of three fixed escalation phrases. It runs after E4 eligibility (§15) has already been computed, and after deduplication.

---

## 10. Place and food answer pools

Three encyclopedic sources exist for **place** answers, not unified into one lookup:

* **`_CITY_LOCATION_BRIEF`** — one-line location descriptions for 11 Chinese cities. Used by `_context_city_from_text()` and `_place_followup_reply()` (在哪儿 questions inside `_answer_user_question_prefix`). **Not** used by `_direct_persona_answer` and not used by `_reverse_fact_answer` in production (§7.2).
* **`_CITY_FOOD_POOL`** (inside `_direct_persona_answer`) — per-city food descriptions for family #28.
* **`_CITY_FEATURE_POOL`** (inside `_direct_persona_answer`) — per-city feature descriptions for family #29.

A **separate pair** of pools exists inside the deduplication substitution function (§12): `_FEAT_POOL_INLINE` and `_FOOD_POOL_INLINE`, independently defined and able to diverge in content from the pair above.

**Question-focus place resolution when multiple city names occur in one utterance:** `_place_from_question_context(t, recent_replies)` implements a three-level priority: (1) a city that immediately precedes a feature/food question marker, matched via `_CITY_BEFORE_QUESTION_MARKER_RE` and validated as a key in `_CITY_LOCATION_BRIEF`; (2) the first known city found anywhere in the text; (3) a deictic reference (那里/这儿/那边) resolved from the **`recent_replies` list the caller passed in as an explicit argument**. This function reads **only its two explicit parameters** — the text `t` and `recent_replies` — and nothing else; it does not itself read `learner_stated_location`, `learner_memory["lives_in"]`, or any global conversation-state dict (see §17 for the distinction between this function's direct inputs and its callers' indirect inputs).

**Fallback when no system knowledge entry exists for a place:** for feature questions, the handler falls back to `"哎，{loc}太有特色了，说也说不完！"` if any location string is available, else `"那个地方很有特色，有机会可以去看看！"`. For a 在哪儿 question about an unknown city, `_place_followup_reply` returns a generic templated sentence if a city name was extracted at all, or `None` to let the caller apply `_persona_limitation_reply`.

**Learner-supplied location fact vs. system knowledge about a place — distinct data sources:**

| Data | Storage | Written by | Read by |
|---|---|---|---|
| System encyclopedic knowledge | `_CITY_LOCATION_BRIEF`, `_CITY_FEATURE_POOL`, `_CITY_FOOD_POOL` (hardcoded module-level dicts) | Never — static at code load | Answer-source functions for questions about *known* Chinese cities |
| Learner-stated open-world location | `learner_stated_location` in `conversation_state` | Set when the learner volunteers/confirms a residence location, including places with **no** entry in the encyclopedic pools | Frame slot fill (`learner_memory["lives_in"]`); **not** read by `_place_from_question_context` itself (§17) |

A place the learner mentions can be **stored** as `learner_stated_location` regardless of encyclopedic coverage; the system cannot **describe** that place beyond the generic fallback templates above unless it is a persona's own city/hometown or a key in one of the three hardcoded pools.

---

## 11. Volunteered information and empathetic follow-ups

| Source | Trigger | Acknowledgement | Empathetic follow-up | Direct answer | Engine redirection | Question location |
|---|---|---|---|---|---|---|
| Volunteered travel intent | `not user_asked_question and _has_volunteered_travel_intent(answer_text)` | Implicit in the templated reply | Yes — template includes a follow-up question | No | Separate: `force_travel_bridge` via `_should_route_to_travel()` can bridge to travel-engine frames on the **next** frame, independent of this `counter_reply` | Follow-up question is inside `counter_reply`; `frame_text` on the same turn is unaffected |
| Health/concern disclosure | `_is_learner_disclosure(answer_text)` | Empathy phrase from bank | Yes, the phrase itself | No | None | Empathy statement is the `counter_reply` |
| Frustration/insult | `_is_frustration_or_insult(answer_text)` | Repair phrase from bank; suppresses `reaction_prefix_text` | Yes — repair framing | No | None | Repair statement is the `counter_reply` |
| Responsive food statement (declarative, not a question) | `_responsive_food_answer` precomputed flag: prior frame was a place-food question and the reply is declarative | Yes — acknowledges extracted food items or a pool pick | Yes — all branches ask a natural follow-up question | No | None observed | Follow-up question is inside `counter_reply` |
| Explicit topic switch | `_is_explicit_topic_switch()`, consumed by the pending-frame commitment guard rather than being an answer source itself | n/a | n/a | n/a | Escapes the commitment guard so normal frame selection resumes | Not an answer-producing source; a guard-bypass signal |

---

## 12. Deduplication and answer substitution

**Outer gate (decides whether `_dedupe_persona_answer()` runs at all):** line 10352 — `if _counter_reply and _counter_reply.strip() in _dedup_pool:`, where `_dedup_pool = ([_prev_counter_reply] if _prev_counter_reply else []) + list(_recent_persona_replies or [])`. This is a **raw exact-string** membership test against the raw pool contents. **No discourse-prefix normalisation is applied at this outer gate.**

**Helper's internal comparisons (once called):** inside `_dedupe_persona_answer()`, `bare_cand = _strip_discourse_prefix(cand)` and `recent_bare = [_strip_discourse_prefix(r) for r in recent_replies]` are computed, and the helper returns the candidate **unchanged** unless either `bare_cand in recent_bare` or `cand in recent_replies`. Because the `recent_replies` argument the handler passes in is the **same** `_dedup_pool` already used by the outer raw gate, and the outer gate already required raw membership, the helper's own raw check is redundant with the outer gate on this call path; the helper's bare-normalised check adds coverage only for candidates whose bare form matches a pool entry that its raw form did not (which — given the outer gate already required a raw match to reach the helper at all — cannot occur via this call path either). The discourse-prefix-normalised comparison's actual load-bearing use is downstream, in building `_recent_set` (raw ∪ bare) for pool-reselection exclusion (below), not in the initial "should I substitute" decision.

**Consequence of the outer gate being raw-only:** a candidate whose **bare** form matches a recent reply, but whose **raw/prefixed** form does not exactly match any `_dedup_pool` entry, fails the outer gate and `_dedupe_persona_answer()` is **never invoked** for that candidate — the helper's own bare-match fallback logic for the initial substitution decision is unreachable via this specific call path, precisely because the outer gate is stricter (raw-only) than the helper's internal check (raw or bare).

**Same-intent pool reselection (Step 1 inside the helper):** if the question is a place-feature question, re-pick from `_FEAT_POOL_INLINE`; if place-food, from `_FOOD_POOL_INLINE`; selection uses `_pick_not_in(pool, seed, recent_set)`, where `recent_set` is the raw-∪-bare union described above.

**Reverse-fact reselection:** **does not exist** in this call path. Confirmed absent per §7.2 — the code explicitly forbids using `_reverse_fact_answer` here (the RC-A guard comment).

**Generic-deflection fallback (Step 2):** `_persona_deflect("generic", cand)` — used only when Step 1's same-intent pool is either not applicable (question is not place-feature/place-food) or exhausted.

**English regeneration tied to Chinese substitution — exact sequence:** `_persona_answer_en()` is called **after** `_counter_reply` is reassigned to the deduped value, using the **final** substituted Chinese, not the discarded original candidate (lines 10352–10367). The immediately following belt-and-suspenders exact-repeat guard (lines 10372–10374) repeats the same pattern: if `_counter_reply` still equals `_prev_counter_reply` after dedup, it is forcibly replaced again, and English is regenerated again via `_persona_answer_en()`. **Behavioural test coverage:** `tests/test_zh_en_synchronisation.py::TestDeduplicationEnglishSync` specifically asserts this ordering for the dedup-substitution path. No equivalent test was found asserting the same guarantee for the repair-escalation override (§9) or the final ASR-junk repair pass (§3.3(4)) — the repair-escalation override does set both `_counter_reply` and `_counter_reply_en` together as literal pairs in the same assignment (so it is self-consistent by construction, not by a recomputation step), while the final ASR-junk repair pass explicitly does **not** recompute English/pinyin at all (§3.3(4)).

**Working-memory update after the final answer:** `response["state_update"]["last_counter_reply"]` and `["recent_persona_replies"]` are written using the value of `_counter_reply` after dedup, the exact-repeat guard, and repair escalation have all run — but **before** the final ASR-junk repair pass (§3.3(4)), since that pass runs later in the handler (line 12413) than the working-memory write (line ~11826). This means a junk fragment stripped by the final repair pass would not be reflected in `recent_persona_replies` for the *next* turn's dedup pool — an evidenced ordering characteristic, not a demonstrated failure, since the fragment being present in the stored value versus absent in the transmitted value only matters if the fragment recurs verbatim in a later dedup comparison.

---

## 13. Chinese-to-English contract

**Source-provided English vs. regenerated English — distinguished explicitly.** Many answer sources (mirror bank, §7.1; E3 working memory, §8; every recovery/repair function, §9; the food/travel volunteered-info functions, §11) return their **own** `(zh, en)` tuple directly — this English is never passed through `_persona_answer_en()` at all. By contrast, `_direct_persona_answer()` (§5) returns Chinese only, and every one of its call sites explicitly calls `_persona_answer_en()` afterward to obtain the paired English. `_persona_answer_en(persona, zh, intent=None)` is therefore the single translation path only for **that specific set of callers** — the explicit-place-topic branch, the stale-override branch, the internal direct-persona sub-step of `_answer_user_question_prefix`, and the two post-chain re-translation call sites in §12 — not a universal translator applied to every answer source's output.

**Actual resolution order inside `_persona_answer_en()`:**

| Resolution stage | Function/data source | Applicable answer types | Failure behaviour |
|---|---|---|---|
| 1 | `_en_for_counter_reply(d, inner)` — fixed deflection/recovery phrase map, with `"As for me — "` prefix logic when `zh` starts with `我呢，` | Any candidate matching a phrase in `_persona_deflect_en_map` | Falls to stage 2 |
| 2 | `_voice_line_en_for_zh(persona, d)` / `(persona, inner)` — matches `voice_lines` values against `voice_lines_en` by key | Any candidate that is exactly a persona `voice_lines` string | Falls to stage 3 |
| 3 | `_reverse_fact_answer_en(intent, persona)` — only if caller supplied a non-`None` `intent` | Reverse-fact-classifiable direct questions | Falls to stage 4; several intents unconditionally or conditionally return `""` per the RC-EN invariant (§7.2) |
| 4 | Scan of `discoverable_facts` for a value equal to or contained in `d`/`inner`, paired lookup in `discoverable_facts_en` | Dynamic persona answers sourced from `discoverable_facts` | Falls to stage 5 |
| 5 | `_persona_deflect_en(d)` / `_persona_deflect_en(inner)` — phrase-bank lookup | Phrase-bank-sourced replies not already caught by stage 1 | Returns `""` (final) |

**Fixed deflection/recovery translation maps:** `_persona_deflect_en_map` (Chinese phrase → English) is built at startup from `content/recovery_phrases.json` entries where `use == "persona_deflect"`.

**Can a source-provided English value be replaced later?** Yes, but only for the subset of sources that pass through `_persona_answer_en()`-driven call sites, and only via the §12 substitution mechanisms — dedup, the exact-repeat guard, and repair escalation (the last of which supplies its own literal English pair rather than calling `_persona_answer_en()` again). Mirror-bank and E3 English (source-provided, not `_persona_answer_en()`-derived) can *also* be replaced if the Chinese they produced happens to match the `_dedup_pool` and triggers dedup — in that case, the replacement Chinese's English **is** computed via `_persona_answer_en()`, even though the *original* mirror/E3 English was not.

**Answer paths where final English can legitimately be empty (`""`):** `_persona_answer_en()`'s own final fallthrough; `_voice_line_en_for_zh()`/`_en_for_counter_reply()` no-match cases; `_reverse_fact_answer_en()`'s narrowed branches (`hometown_special`, `age`, conditionally `work_duration`); mirror-bank (`_mirror_persona_stub`) and E3 (`_answer_from_working_memory`) tuples with an empty second element for many topic branches; `_soft_persona_fallback`'s wrap, which always returns `(zh, "")`; response assembly omits the field entirely when empty.

**No global final validator exists** that checks whether an untouched source-provided English string actually corresponds to its paired Chinese — the correctness of source-provided `(zh, en)` tuples (mirror, E3, all §9 recovery functions, §11 volunteered-info functions) depends entirely on each function's own internal construction being correct; there is no cross-checking mechanism. This is why the enforced invariant in §18 is scoped narrowly to the **substitution** paths, not to a blanket Chinese–English synchronisation guarantee across every answer source.

**Enforced invariant (narrowed, replacing any broader "always synchronised" claim):** *When a post-chain mechanism substitutes the Chinese answer, the same substitution path also replaces or recomputes the English associated with that replacement* — demonstrated for dedup and the exact-repeat guard (test-covered by `tests/test_zh_en_synchronisation.py::TestDeduplicationEnglishSync`) and for repair escalation (self-consistent literal pairs, not independently test-asserted for the "recompute" property since no recomputation call occurs — the pair is simply assigned together). This invariant explicitly does **not** extend to the final ASR-junk repair pass (§3.3(4)), which is documented as a gap, not a covered case.

---

## 14. Chinese-to-pinyin contract

There is **no programmatic romanisation library** in `scripts/ui_server.py`. `counter_reply_pinyin` is produced exclusively by `_resolve_counter_reply_pinyin(zh)` — a curated exact-string map lookup against `_persona_deflect_pinyin_map`, itself populated at startup from the `pinyin` field of entries in `content/recovery_phrases.json`.

```text
scripts/ui_server.py, _resolve_counter_reply_pinyin (paraphrased structure):
  if zh in map: return map[zh]
  if zh starts with "我呢，": strip prefix, look up inner text, prepend "wǒ ne，" if found
  otherwise: return ""
```

**Timing:** pinyin is derived from `_counter_reply` **after** the priority chain, dedup, the exact-repeat guard, and repair escalation have all run (line 10428) — but **before** the final ASR-junk text repair pass (§3.3(4), line 12413). Consequently, if the final repair pass actually strips a junk fragment from the Chinese text, the already-computed pinyin is **not** recomputed and can reference text that no longer matches the transmitted Chinese exactly. This mirrors the same evidenced gap noted for English in §13.

**Handling of punctuation, Latin text, digits, names, unknown characters:** none — the function performs only an exact string key lookup; anything not an exact (or `我呢，`-stripped) match returns `""`.

**Pinyin supplied directly by content, not derived programmatically:** yes, from `content/recovery_phrases.json`'s `pinyin` field — the only source that feeds `counter_reply_pinyin`. `personas/*.json`'s `name_pinyin` feeds a different response field (`partner_name_pinyin`); `p2_frames.json`'s `pinyin` feeds `frame_pinyin`, not `counter_reply_pinyin`; `content/mirror_questions.json`'s `py` field is not read by any counter_reply-producing function at all.

**Fallback on conversion failure:** there is no conversion step; a lookup miss returns `""`, and the response omits `counter_reply_pinyin` entirely when empty.

**Practical consequence:** the great majority of `counter_reply` values — all 42 `_direct_persona_answer` intent families, all mirror-bank answers, all E3 answers — receive **no server-side pinyin** unless the exact final string happens to equal a phrase in the recovery-phrases pinyin map. `tests/test_zh_en_synchronisation.py` acknowledges that the client may independently build pinyin from a client-side lexicon when the server returns `""`, but that client-side mechanism is out of scope for this document.

---

## 15. E4 eligibility and answer confidence

E4 eligibility is computed once (lines 10296–10313), **after** the entire priority chain — including Priorities 22a and 22b — has produced its final `_counter_result` for this turn, and **before** any post-chain replacement mechanism (§4.3) runs.

```text
scripts/ui_server.py, E4 handoff computation (paraphrased structure, lines 10296-10313):
  if user_asked_question and _counter_result:
      if _counter_is_new_mirror and _new_mirror_topic:
          e4_engine = QUESTION_TOPIC_TO_ENGINE.get(_new_mirror_topic)
      elif _counter_is_working_memory:
          e4_engine = infer_question_topic_engine(submitted_text)
      elif _last_text_for_counter:
          if _counter_result[0] not in generic_deflect_set:
              e4_engine = infer_question_topic_engine(_last_text_for_counter)
```

**Corrected ordering statement (replacing any prior claim that a post-chain replacement happens before E4, or that E4 is recomputed afterward):** E4 sees the result exactly as it stood after Priorities 22a and 22b (both of which execute inside the same `if _counter_result is None:` block as Priorities 20–21, entirely before line 10285's extraction of `_counter_reply`/`_counter_reply_en` and therefore entirely before line 10296's E4 computation). E4 is then computed from that value. Deduplication, the exact-repeat guard, repair escalation, and the final ASR-junk repair pass all run **afterward** and **do not cause `_e4_engine_handoff` to be recomputed** — whatever engine value (or `None`) was decided at lines 10296–10313 is what gets written to `response["state_update"]["current_engine"]` at line 11833, regardless of any later replacement of the learner-visible `counter_reply` text.

**Evidenced ordering characteristic, recorded as an intended-contract gap (not a demonstrated production failure):** *E4 may remain based on the priority-chain candidate even when deduplication or repair escalation later replaces the learner-visible answer.* No test was found that specifically exercises a turn where (a) the priority chain produces an E4-eligible answer, (b) that exact Chinese answer is a repeat requiring dedup or repair-escalation substitution, and (c) asserts what `current_engine` value is emitted in that combined scenario. This is recorded here as an evidenced ordering characteristic of the code as read, not as a bug reproduced by a failing test.

### 15.1 E4 eligibility matrix

Four labels are used, matching the branch's actual trigger semantics as read from the source (not inferred from the branch's typical/expected usage):

* **Structurally ineligible** — the branch's own trigger condition explicitly requires `not user_asked_question` (or, for Priority 4, is forced into that state by a separate override before the branch runs), which is incompatible with E4's master gate (`user_asked_question` must be `True`).
* **Conditionally eligible** — the branch's own trigger condition has no explicit requirement on `user_asked_question` in either direction; whether E4's master gate is satisfied depends on the turn-level value of `user_asked_question` (a single boolean computed once per turn, not per branch), which this branch's trigger neither guarantees nor excludes.
* **Eligible through mirror-topic mapping** — the branch's trigger explicitly requires `user_asked_question = True`, and its E4 contribution is decided via `_QUESTION_TOPIC_TO_ENGINE`, not the text classifier.
* **Eligible through question-text inference** — the branch's trigger explicitly requires `user_asked_question = True` (or, when reached via the shared `elif _last_text_for_counter:` fallback, the turn-level flag happens to be `True`), and its E4 contribution is decided via `_infer_question_topic_engine()`.

| Priority / source | Trigger's own `user_asked_question` requirement | Classification | Subject to generic-deflection exclusion? | Engine-inference mechanism if eligible |
|---|---|---|---|---|
| 1 — Frustration repair | None stated | Conditionally eligible | Yes, via the shared fallback branch, if reached | `_infer_question_topic_engine` |
| 2 — Disclosure empathy | None stated | Conditionally eligible | Yes, if reached | `_infer_question_topic_engine` |
| 3 — Persona challenge | None stated | Conditionally eligible | Yes, if reached | `_infer_question_topic_engine` |
| 4 — Responsive food answer | Forced to `False` by an explicit override at lines 9233–9234 whenever this branch's own flag is `True` | **Structurally ineligible** (guaranteed, not merely typical) | n/a | n/a |
| 5 — Volunteered travel intent | Explicitly requires `not user_asked_question` | Structurally ineligible | n/a | n/a |
| 7 — Explicit place-topic | None stated | Conditionally eligible | Yes, if reached | `_infer_question_topic_engine` |
| 8 — Meaning recovery | Explicitly requires `not user_asked_question` (in `_is_meaning`'s own definition) | Structurally ineligible | n/a | n/a |
| 9 — Example request | Explicitly requires `not user_asked_question` (in `_is_example`'s own definition) | Structurally ineligible | n/a | n/a |
| 10 — Repeat/slower request | **None stated** in `_is_rr`'s own definition (verified — no `user_asked_question` reference) | Conditionally eligible | Yes, if reached | `_infer_question_topic_engine` |
| 11 — Lexical definition | Explicitly requires `not user_asked_question` (in `_lex_ct`'s precomputation) | Structurally ineligible | n/a | n/a |
| 12 — Stale-override direct persona | None stated (only `_is_direct_persona_question`, a distinct classifier from `_is_user_question`) | Conditionally eligible | Yes, if reached | `_infer_question_topic_engine` |
| 13 — Mirror confusion ladder | Explicitly requires `not user_asked_question` | Structurally ineligible | n/a | n/a |
| 14 — Generic confusion recovery | Explicitly requires `not user_asked_question` | Structurally ineligible | n/a | n/a |
| 15 — App-question clarification | Explicitly requires `not user_asked_question` | Structurally ineligible | n/a | n/a |
| 17 — Pending-frame commitment | Explicitly requires `not user_asked_question` | Structurally ineligible | n/a | n/a |
| 18 — F2 "why do you like X" adjacency | **None stated** (verified — no `user_asked_question` reference in the trigger) | Conditionally eligible | Yes, if reached | `_infer_question_topic_engine` |
| 19 — E3 working memory | Explicitly requires `user_asked_question = True` | **Eligible through question-text inference** | **No** — this exclusion is applied only in the `elif _last_text_for_counter:` fallback branch, not to the E3 branch | `_infer_question_topic_engine(submitted_text)` |
| 20 — Mirror bank | Explicitly requires `user_asked_question = True` | **Eligible through mirror-topic mapping** | **No** — same reasoning as Priority 19 | `_QUESTION_TOPIC_TO_ENGINE.get(topic)`, conditional on the topic being a key in that table |
| 21 — `_answer_user_question_prefix` fallback (including `_soft_persona_fallback`, `_topic_aware_honest_fallback`, `_persona_limitation_reply`) | None stated — this branch is reached whenever mirror missed or `user_asked_question` was `False`; none of its internal sub-steps re-check the flag | Conditionally eligible | Yes, if the returned zh happens to be a member of the generic-deflect set | `_infer_question_topic_engine`, only if `user_asked_question` happened to be `True` for the turn |
| 22a — Generic-deflection bypass | Explicitly requires `not user_asked_question` | Structurally ineligible (guaranteed, since the whole turn's flag must be `False` for this branch to fire at all) | n/a | n/a |
| 22b — Confusion-with-question-mark fallback | Explicitly requires `user_asked_question = True` | **Eligible through question-text inference** — noted as a specific point of attention: a *confusion-signal clarification* reaching this branch is not excluded from E4 by any dedicated guard, only by whichever engine `_infer_question_topic_engine()` happens to infer from the confused text, and by whether the resulting `_clarify_app_question()` output coincidentally matches the generic-deflect set | Yes, via the shared fallback branch | `_infer_question_topic_engine(_last_text_for_counter)` |

**Cross-reference:** the complete client-side E4 transport contract (`state_update.current_engine` application on the following request) is documented in `docs/CONVERSATION_ARCHITECTURE.md` §5.5/§8 and `docs/STATE_CONTRACT.md`; this document covers only the server-side eligibility decision.

---

## 16. Unsupported and out-of-scope questions

Three distinct fallback mechanisms exist, reachable only inside `_answer_user_question_prefix`'s tail, in this order: `_soft_persona_fallback(t, persona)` → `_topic_aware_honest_fallback(t, persona)` → `_persona_limitation_reply(topic_hint)` (the unconditional final fallback).

* **`_soft_persona_fallback`** returns `Optional[str]` (Chinese only) for harmless unsupported questions; the caller always wraps it as `(_soft, "")` — English is always empty for this path by construction.
* **`_topic_aware_honest_fallback`** returns `Optional[(zh, en)]`, staying within the question's topic domain; some branches return `en=""`.
* **`_persona_limitation_reply`** returns `str` only; it always returns a non-empty string, and its call site supplies a single fixed English literal regardless of the Chinese topic hint used.

**Difference from a generic deflection:** the generic-deflection phrase bank (`_persona_deflect_phrases["generic"]`) is a separate mechanism used by (a) `_dedupe_persona_answer()`'s pool-exhausted fallback and (b) Priority 22a — it is not one of the three functions above.

**How unsupported questions differ from failed classification:** an unsupported question reaches this tail *because* it was classified as `user_asked_question` (or `_is_direct_persona_question`) but no mirror, place-distance, or `_direct_persona_answer` branch matched. A confusion signal that is not a genuine question is filtered out earlier, by the prefix function's own entry-point confusion guard.

**E4 eligibility of the three fallbacks:** see §15.1 — all three fall under Priority 21's "conditionally eligible" classification, since none of the three re-check `user_asked_question` internally, and none is specifically excluded from the generic-deflection check other than by coincidental phrase overlap.

**MandarinOS is not a general knowledge chatbot:** by design, all three fallbacks operate strictly within persona-adjacent topic domains rather than attempting to answer arbitrary world-knowledge questions.

---

## 17. Answer-source state interactions

| State field | Read by answer generation? | Written by answer generation? | Notes |
|---|---|---|---|
| `last_counter_reply` | Yes — read into `_prev_counter_reply` at the start of the turn | Yes — written unconditionally from the final `_counter_reply` (post-dedup/repair-escalation, pre-final-ASR-junk-repair) | See §3.3(4)/§12 for the ASR-junk-repair timing caveat |
| `recent_persona_replies` | Yes — read into `_recent_persona_replies`; consumed by E3 (§8), the dedup pool (§12), and same-intent pool exclusion sets | Yes — appended with the final `_counter_reply` and capped to last 3 | Cap (3) and extraction window (5, §8) differ |
| `last_partner_frame_text` | Yes — read by meaning/example/repeat-slower/app-question-confusion/pending-frame-commitment paths (§9) | No — written by frame selection, not by answer generation | Cross-referenced fully in `docs/STATE_CONTRACT.md` |
| Mirror-topic state (`_cs_mirror_topic`, `_cs_mirror_engine`, `_cs_mirror_conf`/`mirror_confusion_count`) | Yes — read to select the mirror-confusion escalation stage (Priority 13) and the F2 adjacency guard (Priority 18) | Yes — updated on confusion increment/clear, and set when a fresh mirror answer is produced (Priority 20) | Cross-turn round-trip completeness is `STATE_CONTRACT.md` SIC-1 |
| Confusion counters (`_repair_attempt_count`) | Yes — read to gate repair escalation (§9) | Not by the answer-source functions themselves within this document's scope | See `docs/STATE_CONTRACT.md` for full schema |
| Incoming `current_engine` | **No** — none of the answer-source functions or the E4 eligibility computation (§15) read the turn's incoming `current_engine` value; the E4 decision is derived purely from `user_asked_question`, mirror/E3 flags, and question text | Not applicable (this row concerns reading) | **Frame selection reads the incoming `current_engine` separately**, for a different purpose (selecting the next frame within the currently-active engine); answer generation and frame selection consult this field independently, not through shared mutation |
| Outgoing E4 handoff (`_e4_engine_handoff` / `state_update.current_engine`) | n/a | Yes — answer generation computes `_e4_engine_handoff` (§15) and writes it to `response["state_update"]["current_engine"]` for **transport to the following turn**; it does not affect the current turn's frame selection | Full end-to-end client transport is `docs/CONVERSATION_ARCHITECTURE.md`/`docs/STATE_CONTRACT.md` scope |
| Place-subject context (`learner_stated_location`, `learner_memory["lives_in"]`) | **Indirect only** — `_place_from_question_context()` itself reads neither field; it reads only its own `text`/`recent_replies` parameters (§10). `learner_memory["lives_in"]` is read elsewhere, by frame slot-fill logic, a mechanism outside this document's answer-source scope | Not by any answer-source function traced in this document | The distinction between direct-argument inputs and a caller's own indirect state reads is preserved deliberately, per §10 |
| Learner memory (general) | Indirect only, via `learner_memory["lives_in"]` above, which is not read by any function this document treats as an answer source | No | Out of scope beyond the one field cited |
| Persona reveal tracking | Not read or written by any function traced in this document | — | No evidence found of answer-source interaction |

This table states only whether answer generation reads/writes each field on the **current** turn; full round-trip correctness on the **following** turn is `docs/STATE_CONTRACT.md` scope.

---

## 18. Enforced answer invariants

### Enforced invariants

* **Within Groups 1 and 2, the first branch whose trigger condition evaluates `True` commits the chain to that branch for the remainder of the group, whether or not the branch's own callee ultimately assigns `_counter_result`.** Verified directly from the Python source (§4). Groups 3, 4, and 5 are independent gates, each only entered if `_counter_result is None`.
* **When a post-chain mechanism substitutes the Chinese answer, the same substitution path also replaces or recomputes the English associated with that replacement** — demonstrated for dedup/exact-repeat (test-covered, §13) and self-consistent by construction for repair escalation; **not** extended to the final ASR-junk repair pass (§3.3(4), a documented gap).
* **`_reverse_fact_answer()` (Chinese) is not invoked by any production request handler**, and is guarded against reintroduction by an explicit in-code comment (§7.2).
* **E4 eligibility is computed once, from the priority-chain's final candidate, before any post-chain replacement runs, and is never recomputed afterward** (§15).
* **Direct persona answers appear in `counter_reply`, not `frame_text`.** `_direct_persona_answer()`'s result only ever flows into `_counter_result`/`_counter_reply`.
* **`recent_persona_replies` is updated from the final post-dedup/repair-escalation answer**, not any earlier candidate (though see §12 for the final-ASR-junk-repair timing caveat).
* **Current-frame selection and answer generation read `current_engine`-related state independently, not through shared mutation** (§17) — answer generation never reads the incoming `current_engine`; it only writes the outgoing handoff value.
* **Question-focus precedence protects the named place being asked about.** `_place_from_question_context()`'s three-level priority (§10) ensures a city immediately preceding a feature/food question marker outranks an earlier-mentioned city in the same utterance.

### Intended contracts with known gaps

* **Every Chinese answer should have non-empty English.** Not enforced — §13 identifies multiple structurally-guaranteed empty-English paths, and no global validator exists to catch a source-provided mismatch.
* **Every answer should have correct pinyin.** Not enforced — §14 shows pinyin is a curated map lookup covering only recovery/deflection phrases.
* **E4 should reflect the answer actually shown to the learner, not merely the priority-chain candidate.** Not enforced when a post-chain replacement occurs — §15's documented ordering gap.
* **The final ASR-junk repair pass should keep English/pinyin synchronised with any Chinese it modifies.** Not enforced — §3.3(4) shows this pass rewrites only the Chinese field.
* **Substantial persona-specific content should be data-driven.** Contradicted by evidence in §5/§10/§16: `_CITY_LIKE_POOL`, `_CITY_FOOD_POOL`, `_CITY_FEATURE_POOL`, `_FEAT_POOL_INLINE`/`_FOOD_POOL_INLINE`, and dozens of per-branch inline Chinese fallback templates are hardcoded directly in `scripts/ui_server.py`, not in persona JSON or `content/*.json`.
* **Equivalent answer content should not be maintained in competing literal pools.** (Renamed from a prior "duplicated translation logic" framing — the actual evidence in §6/§10 is duplicated *Chinese answer-content* pools, e.g. `_CITY_FEATURE_POOL` vs. `_FEAT_POOL_INLINE`, `_CITY_FOOD_POOL` vs. `_FOOD_POOL_INLINE`, and `_CITY_LOCATION_BRIEF` vs. inline templates in `_direct_persona_answer` — not a duplicated *translation-resolution implementation*. No second, independently-implemented English-resolution pipeline was found; `_persona_answer_en()` is the single implementation for the callers that use it (§13). Content duplication and translation-logic duplication are therefore recorded as two separate concerns; only the former is evidenced.)
* **Unsupported questions should be honest and topic-aware.** Partially met: `_topic_aware_honest_fallback` exists and is tried before `_persona_limitation_reply`, but `_soft_persona_fallback` (tried first) can return a plausible-sounding generic answer for a question the persona cannot actually verify.
* **Mirror-confusion escalation should work across turns.** Known incomplete — `docs/STATE_CONTRACT.md` SIC-1 (§9).
* **Noisy-location/destination-clarify state should round-trip across turns.** Known incomplete — `docs/STATE_CONTRACT.md` SIC-2 (§9).
* **Answer pools should not cross topics during deduplication.** Met for the place-feature/place-food repick paths in `_dedupe_persona_answer` (§12), which are gated by the matching question-type check before selecting the matching pool; the Step-2 fallback (generic deflection) when neither guard matches is a deliberate cross-topic-safe choice (a topically-neutral clarification), not a violation, since it does not attempt a same-topic pool for other answer types at all.

---

## 19. Extension rules

| Adding a... | Priority position | Chinese source | English source | Pinyin | Deduplication | E4 eligibility | Tests | Documentation |
|---|---|---|---|---|---|---|---|---|
| Direct persona-answer intent | Insert into `_direct_persona_answer`'s flat sequence (§5) at the correct precedence position | Prefer `discoverable_facts`/`voice_lines`/`profile`; avoid a new inline pool unless genuinely encyclopedic | Add to `discoverable_facts_en`/`voice_lines_en` so `_persona_answer_en()` stages 2/4 can resolve it | Accept no pinyin unless the fallback text should equal a recovery-phrase-bank entry | Add to §12's same-intent pool tables only if it is a place-feature/place-food fact | Decide per §15.1's four-label scheme, matching the new branch's actual `user_asked_question` requirement (or lack of one) — do not assume exclusion without an explicit trigger check | Add a test exercising the new pattern and its precedence relative to neighbours | Add a row to §5's table |
| New answer source (new function) | Decide which of the five structural groups (§4) it belongs in and its exact position | State whether it returns `(zh, en)`, `zh`-only, or sets a flag only — flag-only sources must not be documented as answer sources (§3.2) | State the English mechanism explicitly; do not assume `_persona_answer_en()` applies unless routed through one of its actual call sites (§13) | State whether it should populate `_persona_deflect_pinyin_map` | Decide explicitly whether §12's exact-match dedup guard should apply, and whether same-intent repick needs a new pool | Classify per §15.1's four labels from the new trigger's actual code, not from its intended purpose | Add a unit test and an ordering/precedence test proving it does not fire ahead of higher-priority sources | Add a row to §4.2's table |
| New persona fact | n/a (data-only) | Add to `profile`/`discoverable_facts`/`voice_lines`/`distance_profile` | Add matching `*_en` entry | n/a | n/a | n/a | Add persona-JSON-schema test coverage if one exists | Update §6 if the new fact competes with an existing source |
| New mirror topic | Add record to `content/mirror_questions.json` | `_mirror_persona_stub()` must handle the new `topic` key | Add the paired `*_en` field(s), or accept `""` | Not read from `mirror_questions.json`'s `py` field via the current mechanism (§14) | Not automatic — only place-feature/place-food dedup repick exists | Add the new `topic` to `_QUESTION_TOPIC_TO_ENGINE` if E4 handoff should fire for it | Add a mirror-match test and, if escalation-relevant, a confusion-ladder test | Update §7.1 |
| Reverse-fact category | Add to `_detect_reverse_fact_intent` and `_reverse_fact_answer`/`_reverse_fact_answer_en` | `_reverse_fact_answer` remains **unreachable in production** unless a new call site is deliberately added — and doing so would need to reconcile with the explicit RC-A guard comment forbidding it in the dedup path (§7.2) | Apply the RC-EN invariant: if the same intent can be triggered by structurally different questions, return `""` | n/a unless routed through the deflect pinyin map | n/a | `_persona_answer_en()`'s stage 3 picks this up automatically once `intent` is passed | Add a unit test analogous to `tests/test_regression_place_travel_reverse.py` | Update §7.2 |
| Recovery reply | Add function + trigger condition in the appropriate priority slot (§4/§9) | Prefer `content/recovery_phrases.json` phrase-bank sourcing over inline strings | Add `text_en` to the phrase-bank entry | Add `pinyin` to the phrase-bank entry if desired | Already subject to post-hoc dedup if it repeats | Determine the new trigger's actual `user_asked_question` relationship and classify per §15.1 — do not assume structural exclusion | Add a trigger-detection test and a phrase-bank-sourcing test | Add a row to §9's table |
| Place-feature answer | Add to `_CITY_FEATURE_POOL` and, if same-intent dedup reselection should also offer it, `_FEAT_POOL_INLINE` (§10/§12) — both must be updated to stay consistent | Pool string itself | Decide explicitly whether to add a paired English string reachable by `_persona_answer_en()` (the RC-EN convention makes `""` acceptable for this content type) | n/a | Already covered automatically if the question-type check matches | Falls under the direct-persona E4 branch automatically if reached via `_direct_persona_answer` | Add a same-intent-dedup test if `_FEAT_POOL_INLINE` was also updated | Update §5 family #29 and §10 |
| Phrase-bank entry | Add to `content/recovery_phrases.json` under the correct `use` key | `text`/`zh` field | `text_en` field | `pinyin` field | Automatic via existing pickers if the `use` key is one already consumed by them | n/a beyond whatever the consuming trigger already implies | Add a phrase-bank loading/sourcing test | Document a new `use` key if introduced |
| English mapping | Add to the relevant `*_en` field | n/a | The mapping itself | n/a | n/a | n/a | Extend `tests/test_zh_en_synchronisation.py`-style coverage | Update §13's stage table if a new resolution stage is introduced |
| Pinyin exception | Add to `content/recovery_phrases.json`'s `pinyin` field | n/a | n/a | The mapping itself, consumed automatically by `_resolve_counter_reply_pinyin()` | n/a | n/a | Add a pinyin-resolution test | Update §14 only if the mechanism itself changes |

---

## 20. Known risks

* **One very large priority chain** spanning roughly 500 lines across five structurally distinct groupings (§4), making full-chain reasoning difficult without the ordered inventory in this document. *Observed.*
* **Overlapping pattern matches** across `_direct_persona_answer` intent families (e.g. `"喜欢"` appears as a discriminator in families #13, #14, #23, #27, #35); no automated test enumerates all pairwise ordering interactions. *Observed* ordering-sensitivity; pairwise-safety across all 42×41 combinations is *unverified*, not confirmed unsafe.
* **Equivalent answer content maintained in competing literal pools** (§18) — at least four concrete duplication points: city-food, city-feature, city-location-brief vs. inline templates, and work info spread across three fields with per-family precedence. *Observed.*
* **Inline Chinese answer content** — a large volume of hardcoded Chinese directly in `scripts/ui_server.py` (§5, §10). *Observed.*
* **Incomplete English mappings** (§13, §18). *Observed.*
* **Dynamic replies that bypass data files** — the F2 why-like adjacency guard constructs its answer inline from a truncated `voice_lines` slice rather than a dedicated data field. *Observed.*
* **Stale-answer pool exhaustion** — `_dedupe_persona_answer`'s Step 1 can itself be exhausted, forcing Step 2's generic deflection even when a genuinely new fact might exist via a different mechanism not attempted here. *Observed.*
* **Source-order changes altering unrelated behaviour** — because Groups 1 and 2 are single flat `elif` chains where a matching-but-empty branch dead-ends the whole group for that turn (§4), reordering or adding a new condition anywhere in those groups risks silently suppressing an existing lower-priority answer source. *Observed* as a structural property, not a specific historical incident.
* **E4 eligibility can outlive the answer it was computed from** — §15's documented ordering gap: a post-chain replacement of `counter_reply` does not trigger recomputation of `_e4_engine_handoff`. *Observed* ordering characteristic; no failing test reproduces a concrete user-facing symptom.
* **The final ASR-junk repair pass can desynchronise Chinese from already-fixed English/pinyin** (§3.3(4), §12, §14). *Observed* ordering characteristic; no test asserts re-synchronisation.
* **Answer sources returning different tuple shapes or assumptions** — `_direct_persona_answer` returns `zh`-only, requiring every call site to independently wrap it and call `_persona_answer_en()` (four distinct call sites, not centralised once), whereas most other sources return `(zh, en)` directly. *Observed.*
* **Tests that prove only individual functions rather than full priority ordering** — most cited tests exercise a single function or a single trigger condition; no single test file asserts the complete 22-slot/23-branch ordering end-to-end. *Observed* as an absence, not a specific defect.

---

## 21. Regression diagnosis guide

* **Learner question receives no answer:** confirm `last_turn_was_answer` was true and check whether the question text matched a Group 1 or Group 2 trigger with an *empty* callee result — per §4's corrected semantics, this is a dead end for the turn, not a fallthrough, and is a legitimate but easily-mistaken-for-a-bug outcome.
* **Wrong persona fact returned:** check `_direct_persona_answer`'s family-order table (§5) for a higher-priority family whose pattern unexpectedly matched first.
* **Wrong place answered:** check `_place_from_question_context()`'s three-level priority (§10).
* **Stale answer repeats:** confirm the repeated string is exactly present in `_dedup_pool` (the outer raw gate, §12) before assuming the helper's bare-normalised logic should have caught it — a bare-only match never reaches the helper at all.
* **Chinese and English disagree:** confirm which §13 resolution stage produced the English, whether the Chinese was subsequently changed by a §12/§9/§3.3(4) mechanism *after* that English was computed, and specifically check whether the final ASR-junk repair pass (§3.3(4)) is the culprit, since that pass never recomputes English.
* **English is blank:** check the specific answer-source class against §13's "legitimately empty" list before assuming a defect.
* **Pinyin does not match Chinese:** confirm whether `counter_reply_pinyin` was populated at all (§14); also check whether the final ASR-junk repair pass altered the Chinese after pinyin was already computed.
* **Recovery reply overrides a direct answer:** check Group 1 (§4 Priorities 1–5) and the repair-escalation override (§9) — the latter has no `user_asked_question` gate at all.
* **Direct answer appears but E4 does not fire:** confirm `user_asked_question` was true, `_counter_result[0]` is not a member of `_persona_deflect_phrases["generic"]`, and `_infer_question_topic_engine()` actually classifies the question text — per §15.1, this exclusion only applies to the shared `elif _last_text_for_counter:` fallback branch, not to mirror or E3.
* **E4 fires from what looks like a generic/confusion response:** check §15.1's classification for Priority 22b specifically — a confusion-signal clarification reaching that branch is not specially excluded from E4.
* **E4's `current_engine` seems to correspond to a different answer than what the learner actually saw:** check whether a post-chain replacement mechanism (§4.3) ran after E4 was computed (§15) — this is an evidenced, not-recomputed characteristic, not necessarily a new defect.
* **Wrong answer source wins:** re-derive the exact five-group structure and priority order from §4.
* **Unsupported question produces an overconfident answer:** check whether `_soft_persona_fallback` (§16) — the first-tried, least-strict of the three fallbacks — produced a plausible-sounding but unverifiable answer.
* **Working-memory answer uses an unrelated recent fact:** check `_answer_from_working_memory`'s documented sourcing priority (§8).

---

## 22. Related documents

* `docs/CONVERSATION_ARCHITECTURE.md` — overall turn lifecycle, frame selection, E4 end-to-end transport contract, invariants.
* `docs/STATE_CONTRACT.md` — authoritative `conversation_state`/`state_update` field schema, SIC-1 through SIC-7, and the Section 16.3 resolved-defect record (SIC-6).
* `docs/ASR_PIPELINE.md` — *not yet created in this repository; not begun as part of this revision.*
* `docs/ARCHITECTURE.md`, `docs/TEST_STRATEGY.md`, `docs/CHANGE_CHECKLIST.md`, `docs/ARCHITECTURAL_DECISIONS.md`, `docs/PRODUCT_PHILOSOPHY.md` — *not present in this repository under these exact names; see the repository-root `AI_CONTEXT.md` for the current orientation map.*
* Repository-root `AGENTS.md` — *not present in this repository under this exact name; see the repository-root `AI_CONTEXT.md` and `.cursor/rules/*.mdc` for equivalent standing guidance.*

---

## 23. Traceability appendix

| Answer area | Producer | Primary data source | Finalisation/translation | State interactions | Representative tests |
|---|---|---|---|---|---|
| User-initiative repair (frustration/disclosure/challenge) | `_frustration_repair_reply`, `_disclosure_empathy_reply`, `_persona_challenge_reply` | `content/recovery_phrases.json` | Tuple's own `en`; pinyin via map if phrase matches | Suppresses `reaction_prefix_text`; recent-replies write | `tests/test_regression_surgical_transcript.py`, `tests/test_conversation_fixes.py` |
| Responsive food / travel intent | `_food_responsive_reply`, `_travel_intent_followup` | Extracted text / `content/recovery_phrases.json` | Tuple's own `en` | May feed `force_travel_bridge` on next frame | `tests/test_open_world_food_and_location_fixes.py`, `tests/test_regression_place_travel_reverse.py` |
| Explicit place-topic / stale-override direct persona | `_direct_persona_answer` via §4 Priorities 7/12 | `profile`/`discoverable_facts`/`voice_lines`/inline pools | `_persona_answer_en` | E4-eligible (conditionally); dedup-eligible | `tests/test_contextual_place_asr_repair.py`, `tests/test_stale_answer_loop_regression.py` |
| Meaning/example/repeat-slower/lexical recovery | `_meaning_recovery_reply`, `_clarify_app_question`, `_lexical_definition_reply` | `last_partner_frame_text` / inline tables | Tuple's own `en` | Sets `_confusion_about_app_q` | `tests/test_meaning_recovery.py`, `tests/test_golden_regression.py` |
| Mirror confusion escalation ladder | `_mirror_restate_naturally`, `_mirror_persona_stub_simple`, `_confusion_recovery_reply` | Prior mirror answer / persona facts / inline pool | Tuple's own `en` | Reads/writes mirror-confusion counters (`STATE_CONTRACT.md` SIC-1) | `tests/test_stale_counter_reply_loop.py` |
| Pending-frame commitment / app-question confusion | `_clarify_app_question` | `last_partner_frame_text` | Tuple's own `en` | Same-engine frame-selection guard | `tests/test_interaction_regression.py`, `tests/test_golden_conversation_scenarios.py` |
| Noisy-location clarification | *(flag-only; frame-text override, not a producer, §3.2)* | n/a | n/a | `_confusion_about_app_q`, `_noisy_location_clarify` flags (`STATE_CONTRACT.md` SIC-2) | `tests/test_golden_conversation_scenarios.py::test_gs5_noisy_location_continues` |
| F2 why-like adjacency | Inline construction | `voice_lines[engine]` | Inline (English often empty) | E4-eligible (conditionally, §15.1) | *(no dedicated file identified)* |
| E3 working memory | `_extract_persona_facts_from_recent`, `_answer_from_working_memory` | `recent_persona_replies` | Tuple's own `en` (often empty) | Sets `_counter_is_working_memory`; E4-eligible through question-text inference | *(direct code citations in §8)* |
| Mirror bank | `_find_mirror_answer`, `_mirror_persona_stub` | `content/mirror_questions.json` + persona facts | `_mirror_persona_stub`'s own `en` | Sets `_counter_is_new_mirror`; E4-eligible through mirror-topic mapping | `tests/test_blue_discovery_routing.py` |
| General prefix / unsupported fallback | `_answer_user_question_prefix`, `_soft_persona_fallback`, `_topic_aware_honest_fallback`, `_persona_limitation_reply` | Varies; persona facts where available | Varies; limitation reply has fixed literal `en` | E4-eligible (conditionally, §15.1) | `tests/test_learner_led_followup_questions.py`, `tests/test_conversation_first_wave.py`, `tests/test_transcript_reverse_questions.py` |
| Deduplication / substitution | `_dedupe_persona_answer` | `_FEAT_POOL_INLINE`/`_FOOD_POOL_INLINE`; `_persona_deflect("generic")` | Re-invokes `_persona_answer_en` on final Chinese | Reads `_prev_counter_reply`/`recent_persona_replies`; writes final `_counter_reply` | `tests/test_zh_en_synchronisation.py`, `tests/test_stale_answer_loop_regression.py` |
| Repair escalation | Inline literal `(zh, en)` pairs | Hardcoded escalation phrases | Assigned together, not recomputed | Reads `_repair_attempt_count` and related counters | *(covered by the same confusion-signal suites as §9)* |
| Final ASR-junk text repair | `_repair_asr_junk_text` | `_ASR_JUNK_OUTPUT_FRAGMENTS` | **Does not** recompute English/pinyin (§3.3(4), documented gap) | Runs after the working-memory write; not reflected in `recent_persona_replies` for that turn | *(no dedicated test file identified)* |
| English resolution | `_persona_answer_en`, `_en_for_counter_reply`, `_voice_line_en_for_zh`, `_reverse_fact_answer_en` | Deflect map / `voice_lines_en` / intent lookup / `discoverable_facts_en` | Five-stage precedence (§13) | n/a beyond translation | `tests/test_zh_en_synchronisation.py` |
| Pinyin resolution | `_resolve_counter_reply_pinyin` | `content/recovery_phrases.json` `pinyin` field | Exact-match lookup only | n/a | *(map-lookup mechanism; acknowledged client-side fallback noted in `tests/test_zh_en_synchronisation.py`)* |
| E4 eligibility | Inline computation, lines 10296–10313 | `_QUESTION_TOPIC_TO_ENGINE` / `_infer_question_topic_engine` | Computed once, before all post-chain replacements (§15) | Writes `state_update.current_engine`; does not read incoming `current_engine` | `tests/test_e4_topic_handoff.py` |

**Baseline commit:** `3be0315b2c9f7316b03ac2183a887f602ae9a297`
**Baseline tag:** `architecture-baseline-2026-07-12-r2`
**Source documentation branch:** `docs/architecture-v1`
**Document status:** Draft v2
**Last verified date:** 2026-07-12
