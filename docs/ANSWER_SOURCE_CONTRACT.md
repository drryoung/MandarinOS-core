# MandarinOS Answer Source Contract

**Baseline commit:** `3be0315b2c9f7316b03ac2183a887f602ae9a297`
**Baseline tag:** `architecture-baseline-2026-07-12-r2`
**Source documentation branch:** `docs/architecture-v1`
**Approved contracts referenced:** `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md` (approval commit `0b6738f6da381f2969d79a3c5e0bd1e39d1d09e4`)
**Document status:** Draft v1
**Last verified date:** 2026-07-12

All line-number citations refer to `scripts/ui_server.py` at the baseline commit above unless another file is named.

---

## 1. Purpose and scope

An **answer source** is any production code path in `scripts/ui_server.py` capable of assigning the persona's Chinese answer to the learner (`_counter_result`, later `_counter_reply`) inside the `/api/run_turn` handler. This document enumerates every such path, its priority relative to the others, the data it reads, how it produces English and pinyin, and how it interacts with deduplication, working memory, and E4.

This document governs **`counter_reply`** — the persona's answer to something the learner said on the *previous* turn. It does **not** govern **`frame_text`**, which is the partner's *next* question or conversational move, selected independently by frame selection (`chosen = None` onward, from line ~10485). `counter_reply` and `frame_text` are computed by separate mechanisms in the same handler and are combined in the same response; a turn can carry either, both, or neither.

This document describes the **R2-baseline production implementation**, not an idealised conversational model. Where the code contains overlapping mechanisms, duplicated logic, or incomplete cross-turn state paths, this document records that fact rather than the intended design.

Responsibilities that remain in other documents:

* **`docs/CONVERSATION_ARCHITECTURE.md`** — overall turn lifecycle, frame selection, E4 transport contract end-to-end, engine/ladder mechanics, `state_update` field emission sequencing.
* **`docs/STATE_CONTRACT.md`** — authoritative schema and consumption status of every `conversation_state` / `state_update` field, including `last_counter_reply`, `recent_persona_replies`, mirror-topic fields, and confusion counters.
* **`docs/ASR_PIPELINE.md`** *(not yet created in this repository — referenced for future ASR-normalisation scope only)* — how raw learner speech becomes `answer_text` / `submitted_text` before any answer-source logic in this document runs.

This document does **not** redesign the answer system and does not recommend implementation changes in its descriptive sections (§§1–18). Known gaps and proposed extension discipline are confined to §§19–21.

---

## 2. Response-field boundary

| Field | Represents | Produced by |
|---|---|---|
| `counter_reply` | Persona's Chinese answer to the learner's *previous* turn | Priority chain in this document (§4) |
| `counter_reply_en` | English gloss of the **final** `counter_reply` | `_persona_answer_en()` and related resolution (§13) |
| `counter_reply_pinyin` | Curated pinyin for the **final** `counter_reply` | `_resolve_counter_reply_pinyin()` map lookup (§14) |
| `frame_text` | Partner's next question/statement (forward-looking) | Frame selection (`chosen = None` onward), independent of this document |
| `frame_text_en` | English gloss of `frame_text` | Frame-selection assembly, independent of this document |
| `frame_pinyin` | Pinyin of `frame_text` | Frame content (`p2_frames.json` `pinyin` field), independent of this document |
| `turn_type` | Server-classified nature of the turn | Frame/turn classification, independent of this document |
| `state_update` | Server→client state deltas | Written by both answer-source logic (`last_counter_reply`, `recent_persona_replies`, `current_engine`) and frame selection |

`counter_reply` and `frame_text` are produced **independently** in the handler: the priority chain in §4 runs first (lines 9896–10428), then frame selection runs afterward (from line ~10485) using the pre-turn `current_engine`, not knowing which `counter_reply` was chosen except where a recovery function also mutates flags read later (e.g. `_confusion_about_app_q`, `_noisy_location_clarify` — see §9–§10). E4 (`docs/CONVERSATION_ARCHITECTURE.md` §5.5, §8) is the one mechanism that coordinates them indirectly: an eligible answer-source result can set `response["state_update"]["current_engine"]` (line 11833–11835), which influences **frame selection on the following turn**, not the current turn's `frame_text`.

```text
learner text
→ classification (last_turn_was_answer, user_asked_question, confusion/example/meaning/rr signals)
→ priority-ordered answer-source resolution (_counter_result)
→ Chinese candidate (_counter_reply)
→ deduplication/final substitution (_dedupe_persona_answer, exact-repeat guard, repair escalation)
→ English resolution from final Chinese (_persona_answer_en)
→ pinyin derivation from final Chinese (_resolve_counter_reply_pinyin)
→ response fields (counter_reply, counter_reply_en, counter_reply_pinyin, state_update)
```

---

## 3. Answer-source lifecycle

The actual implementation ordering (line numbers from `scripts/ui_server.py`):

1. **Raw learner answer arrives** as `last_answer` / `answer_text` on the incoming `conversation_state`.
2. **Routing normalisation** — `_last_text_for_counter` is derived from `_routing_last_answer` / routing text (lines 9875–9879); `_normalize_zh_for_routing()` is applied inside individual answer functions (e.g. line 3065).
3. **Intent and signal classification** — `user_asked_question`, `_responsive_food_answer`, `_confirmed_re_ask`, `_is_meaning`, `_is_example`, `_is_rr`, `_lex_ct`, `_explicit_place_topic_result` are computed (lines 9218–9297, 9942–10025) **before** the elif chain that consumes them.
4. **Answer-source priority chain** — the 22-stage ordered chain in §4 runs (lines 9896–10283). The first stage whose trigger matches **and** whose callee returns a non-empty result assigns `_counter_result`; matching-but-empty-result stages can still block lower elif branches without producing an answer (see §4's flag-only/blocking distinction).
5. **First non-`None` candidate selected** — technically the first stage that both matches its condition and receives a non-empty return terminates the relevant elif chain; note the chain is not a single flat elif — see §4's structural notes on the five separate `if`/`elif` groupings.
6. **Chinese/English extraction** — `_counter_reply = _counter_result[0]`, `_counter_reply_en = _counter_result[1]` (lines 10285–10286).
7. **E4 eligibility assessed** — `_e4_engine_handoff` is computed at lines 10296–10313, **before** deduplication and before repair escalation, using the just-extracted `_counter_result` and `_last_text_for_counter`.
8. **Stale-answer/deduplication substitution** — `_dedupe_persona_answer()` runs at lines 10348–10367, followed by a belt-and-suspenders exact-repeat guard (10372–10374). Both can **replace** `_counter_reply` and force a **new** `_counter_reply_en` call **after** E4 eligibility was already computed from the pre-dedup candidate.
9. **Repair escalation override** — lines 10402–10426 can replace `_counter_reply`/`_counter_reply_en` again, still before frame selection, for confusion signals with `_repair_attempt_count >= 2`.
10. **Pinyin derived** — `_counter_reply_pinyin = _resolve_counter_reply_pinyin(_counter_reply)` at line 10428, computed from the **final** post-dedup, post-repair-escalation Chinese text.
11. **Frame selection** — `chosen = None` onward, from line ~10485, runs independently of the above.
12. **Working-memory state updated** — `response["state_update"]["last_counter_reply"]` and `["recent_persona_replies"]` are written from the **final** `_counter_reply` at response-assembly time (lines 11816–11827), not from any intermediate candidate.
13. **Response assembled** — `response["counter_reply"]`, `["counter_reply_en"]`, `["counter_reply_pinyin"]` are conditionally attached only if non-empty (lines 11816–11821).

**Exact E4 timing (per user instruction to be precise on ordering):** E4 eligibility (`_e4_engine_handoff`) is computed at lines 10296–10313, which is **after** the priority chain and the raw `_counter_reply`/`_counter_reply_en` extraction (10285–10286), but **before** deduplication (10348+), the exact-repeat guard (10372+), and repair escalation (10402+). This means E4's eligibility decision is made from the answer the priority chain originally selected, not from any text that dedup or repair escalation may substitute afterward. `docs/CONVERSATION_ARCHITECTURE.md` §5.5/§8 describes the client-side consumption of the resulting `state_update.current_engine`; this document only describes how the server decides whether to emit it.

---

## 4. Priority-chain inventory

The chain is **not** a single flat `if/elif`. It is five separate structural groups, in this exact top-to-bottom execution order:

* **Group 1** (lines 9902–9940): nested `if/elif` — user-initiative overrides. First match among these wins; a match with an empty callee return falls through to the next `elif` in this same group (not to Group 2 directly — the `elif` chain continues).
* **Group 2** (lines 9942–10182, plus 10027 no-op passthrough): flat `if/elif` — pre-computed signals and main recovery/confusion/stale-answer chain. The **first matching condition blocks all lower branches in this group**, even if its own callee returns `None` (e.g. `_is_meaning` matching with no `last_partner_frame_text` leaves `_counter_result` unset but still prevents `_is_example`/`_is_rr`/etc. from running).
* **Group 3** (lines 10187–10208): separate `if _counter_result is None:` — F2 "why do you like X" adjacency guard. Independent of Group 2's blocking.
* **Group 4** (lines 10215–10222): separate `if _counter_result is None and user_asked_question and _recent_persona_replies:` — E3 working memory.
* **Group 5** (lines 10228–10283): separate `if _counter_result is None:` — mirror bank / `_answer_user_question_prefix`, plus two post-prefix sub-steps (generic-deflection bypass, confusion-with-question-mark fallback).

| Priority | Answer source | Trigger | Function(s) | Chinese source | English source | Can trigger E4? | Can be deduplicated? | Representative tests |
|---|---|---|---|---|---|---|---|---|
| 1 | Frustration/insult repair | `_is_frustration_or_insult(answer_text)` (9903–9908) | `_frustration_repair_reply()` | `recovery_phrases.json` (`use=frustration_repair`) | Same tuple | No | Yes (post-hoc, if it repeats) | `tests/test_regression_surgical_transcript.py` |
| 2 | Learner disclosure empathy | `_is_learner_disclosure(answer_text)` (9909–9916) | `_disclosure_empathy_reply()` | `recovery_phrases.json` (`use=learner_disclosure_empathy`) | Same tuple | No | Yes (post-hoc) | `tests/test_conversation_fixes.py` |
| 3 | Persona challenge reply | `_is_persona_challenge(answer_text)` (9917–9924) | `_persona_challenge_reply()` | `recovery_phrases.json` (`use=persona_challenge`) | Same tuple | No | Yes (post-hoc) | `tests/test_conversation_fixes.py` |
| 4 | Responsive food answer | `_responsive_food_answer` flag (9925–9935, precomputed 9227–9234) | `_food_responsive_reply()` | Extracted food items / inline pool | Same tuple | No | Yes (post-hoc) | `tests/test_open_world_food_and_location_fixes.py` |
| 5 | Volunteered travel intent | `not user_asked_question and _has_volunteered_travel_intent(answer_text)` (9936–9940) | `_travel_intent_followup()` | `recovery_phrases.json` (`use=travel_intent_followup`) | Same tuple | No | Yes (post-hoc) | `tests/test_regression_place_travel_reverse.py` |
| 6 | Retain user-initiative answer | `_counter_result is not None` (10027–10030) | — (pass-through, no-op) | n/a | n/a | n/a | n/a | n/a |
| 7 | Explicit place-topic answer | Precomputed `_explicit_place_topic_result` (9997–10025); assigned 10031–10032 | `_repair_contextual_place_question()` + `_direct_persona_answer()` + `_persona_answer_en()` | `_direct_persona_answer()` intent families (§5) | `_persona_answer_en()` | Yes (direct-persona path, 10305–10313) | Yes (post-hoc) | `tests/test_contextual_place_asr_repair.py` |
| 8 | Meaning recovery | `_is_meaning` (10033–10037); blocks Group 2 even if `last_partner_frame_text` empty | `_meaning_recovery_reply()` | `_MEANING_RECOVERY_TABLE` (inline) | Same tuple | No (`not user_asked_question` required) | Yes (post-hoc) | `tests/test_meaning_recovery.py` |
| 9 | Example request → clarify | `_is_example` (10038–10045) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | No | Yes (post-hoc) | `tests/test_meaning_recovery.py` |
| 10 | Repeat/slower request → clarify | `_is_rr` (10046–10050) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | No | Yes (post-hoc) | `tests/test_challenge_recovery.py` |
| 11 | Lexical definition | `_lex_ct` precomputed (9945–9947), assigned 10051–10052 | `_lexical_definition_reply()` | Inline keyword table | Same tuple | No | Yes (post-hoc) | `tests/test_golden_regression.py` |
| 12 | Stale-counter-reply override (direct persona) | `_prev_counter_reply` + `_is_direct_persona_question(_last_text_for_counter)` + not confusion (10053–10087) | `_direct_persona_answer()` + `_persona_answer_en()` | §5 intent families | `_persona_answer_en()` | Yes (direct-persona path) | Yes (post-hoc) | `tests/test_stale_answer_loop_regression.py` |
| 13 | Mirror confusion escalation ladder | `_is_confusion_signal` + active `_cs_mirror_topic`, not a question, not direct-persona (10088–10114) | `_mirror_restate_naturally()` / `_mirror_persona_stub_simple()` / `_confusion_recovery_reply()` (staged by `_cs_mirror_conf`) | Prior mirror answer / `discoverable_facts_simple` / voice_lines / generic pool | Same tuple | No | Yes (post-hoc) | `tests/test_stale_counter_reply_loop.py` |
| 14 | Generic confusion recovery (no mirror topic) | Same confusion guard, but `not _cs_mirror_topic` (10115–10125) | `_confusion_recovery_reply()` | 4-entry inline pool | Same tuple | No | Yes (post-hoc) | `tests/test_challenge_recovery.py` |
| 15 | App-question clarification (no prior counter_reply) | `not _prev_counter_reply` + confusion signal + `not user_asked_question` + `not _confirmed_re_ask` (10126–10140) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | No | Yes (post-hoc) | `tests/test_golden_conversation_scenarios.py` |
| 16 | Noisy location — **flag only** | `"CITY" in slot_names` + no resolvable location + other guards (10141–10161) | *(none — sets `_confusion_about_app_q`, `_noisy_location_clarify` flags only)* | n/a — `_counter_result` stays `None` | n/a | No | n/a | `tests/test_golden_conversation_scenarios.py::test_gs5_noisy_location_continues` |
| 17 | Pending-frame commitment clarification | `not _prev_counter_reply` + `last_answer_fid in _COMMITMENT_GUARD_FRAMES` + off-topic (10162–10182) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | No | Yes (post-hoc) | `tests/test_interaction_regression.py::test_t19_*` |
| 18 | F2 "why do you like X" adjacency | `_is_why_like_follow_up()` + `_cs_mirror_engine` in work/hobby/place/food/travel (10187–10208) | Inline construction from `voice_lines[engine]` | `voice_lines[engine]` or inline template | Inline template (empty when voice_line used) | Possible (direct-persona path) | Yes (post-hoc) | *(no dedicated file identified — covered indirectly by mirror-adjacency scenario tests)* |
| 19 | E3 working-memory answer | `user_asked_question and _recent_persona_replies` (10215–10222) | `_extract_persona_facts_from_recent()` + `_answer_from_working_memory()` | Facts extracted from `recent_persona_replies` | Same tuple (often `""`) | Yes — sets `_counter_is_working_memory` (10222, 10300–10304) | Yes (post-hoc) | *(no dedicated file identified — see §8 for direct code citations)* |
| 20 | Mirror bank | `user_asked_question` (10228–10241) | `_find_mirror_answer()` → `_mirror_persona_stub()` | `content/mirror_questions.json` topic → persona facts | `_mirror_persona_stub()` (often `""`) | Yes — sets `_counter_is_new_mirror` (10241, 10298–10299) | Yes (post-hoc) | `tests/test_blue_discovery_routing.py` |
| 21 | General answer prefix (`_answer_user_question_prefix`) | Mirror miss or `not user_asked_question` (10242–10251); internal sub-chain (21a–21l, see §5–§7, §16) | `_answer_user_question_prefix()` (place follow-up → mirror retry → distance → `_direct_persona_answer` → generics → `_soft_persona_fallback` → `_topic_aware_honest_fallback` → `_persona_limitation_reply`) | Varies by sub-step | Varies (limitation reply has fixed EN at call site) | Yes (direct-persona sub-step) | Yes (post-hoc) | `tests/test_learner_led_followup_questions.py`, `tests/test_transcript_reverse_questions.py` |
| 22a | Generic-deflection bypass | Post-prefix: result ∈ `_persona_deflect_phrases["generic"]` and `not user_asked_question` (10256–10268) | `_clarify_app_question()` (replaces the deflection) | `last_partner_frame_text` restated | Same tuple | No (replacement removes E4 eligibility for this turn) | n/a (already a replacement) | `tests/test_golden_regression.py` (T-TPR E2) |
| 22b | Confusion signal with question mark (post-prefix fallback) | `user_asked_question and not _counter_result and _is_confusion_signal(answer_text)` (10273–10283) | `_clarify_app_question()` | `last_partner_frame_text` restated | Same tuple | No | n/a | *(covered by same confusion-signal test suites as priorities 13–15)* |

Post-chain, non-priority-numbered overrides that can still replace `_counter_result`/`_counter_reply` before frame selection:

* **Deduplication** (`_dedupe_persona_answer`, 10348–10367) — §12.
* **Exact-repeat belt-and-suspenders guard** (10372–10374) — §12.
* **Repair escalation** (10402–10426) — §9.

### Branch-type classification

| Source | Tuple shape | Terminates chain? | Notes |
|---|---|---|---|
| Priorities 1–5, 7–15, 17–22 | `(zh, en)` tuple, `en` frequently `""` | Yes, when non-empty | Standard answer producers |
| Priority 6 | n/a | n/a | Pure passthrough — not an answer source |
| Priority 16 | n/a | **No** | Flag-only (`_confusion_about_app_q`, `_noisy_location_clarify`); `_counter_result` remains `None`; this is **not** an answer source and must not be labelled as one |
| Priority 18 | `(zh, en)` | Yes | Inline construction, not a named reply helper |
| Priority 19 | `Optional[(zh, en)]` | Yes when non-`None` | Also sets `_counter_is_working_memory` for E4 |
| Priority 20 | 4-tuple sliced to `(zh, en)` | Yes when match found | Also sets `_counter_is_new_mirror`, `_new_mirror_topic`, `_new_mirror_engine` for E4 |
| Priority 21 | `(zh, en)` (final catch-all `_persona_limitation_reply` always returns) | Yes — unconditional fallback inside prefix | See §16 |

---

## 5. Direct persona-answer contract

`_direct_persona_answer(t, persona, recent_replies=None)` — lines **3057–3684**. Returns `Optional[str]` (**Chinese only**); the caller (`_answer_user_question_prefix`, lines 4999–5004, or the explicit-place/stale-override call sites at 10005–10025 and 10062–10080) always wraps the result with a `我呢，` prefix (unless it already starts with `我`) and calls `_persona_answer_en()` for English.

The function is a **single, strictly first-match sequence** of 42 recognised intent families (not `elif` throughout, but effectively exclusive because each branch returns immediately). Family order and boundaries are load-bearing: several comments in the code explicitly document precedence requirements (e.g. "cooking before work" at line 3139, "place-food before place-features" at 3387–3389).

| # | Intent family | Recognition patterns | Persona data source | Chinese construction | Fallback | English resolution | Topic engine |
|---|---|---|---|---|---|---|---|
| 1 | Place name where persona lives | `"那里叫什么"`, `"那儿叫什么"`, `"你那里叫"`, `"你那儿叫"` | `profile.city`/`.hometown`, `voice_lines.place` | `f"我住的地方叫{loc}。"` | `voice_lines.place` → `"我住在中国，你有没有来过？"` | Deferred | `place` |
| 2 | Hometown/origin | `"你老家"`, `"你的老家"`, `"你家乡"`, `"你的家乡"`, `"家乡在哪"`, `"家乡是哪"`, `"你是哪里人"`, `"你从哪里来"`, `"你哪里人"` | `profile.hometown`, `voice_lines.place` | `f"我老家在{hometown}。"` | `voice_lines.place` → `"我老家在中国。"` | Deferred; intent `hometown_where` | `place` |
| 3 | Current residence | `"你住在哪"`, `"你住哪"`, `"你现在住"`, `"你住的地方"` | `profile.city/.hometown`, `voice_lines.place` | `f"我住在{city}。"` | `voice_lines.place` chain → `"我在中国住。"` | Deferred | `place` |
| 4 | Name meaning | `"你的名字是什么意思"` + variants | `discoverable_facts.identity` | Fact verbatim | Inline template with `name` | Deferred; `discoverable_facts_en.identity` | `identity` |
| 5 | Name story/origin | `"名字有什么故事"` + variants | `discoverable_facts.identity` | Fact verbatim | Inline template | Deferred | `identity` |
| 6 | Name story via persona's actual name | `name in t` + story markers | `discoverable_facts.identity` | Fact verbatim | Inline template with `name` | Deferred | `identity` |
| 7 | Name / how to address | `"你叫什么"`, `"怎么叫你"` + variants | `display_name` | `f"你可以叫我{name}。"` | **`None`** if `name` empty | Deferred | `identity` |
| 8 | Still live there? | `"还住在那里"` + variants | `profile.city/.hometown` | Branch on city==hometown vs different | Inline template | Deferred | `place` |
| 9 | Cooking / dishes | `_is_cooking_question` (3821–3835) | `discoverable_facts.food`, `voice_lines.food`, cooking phrase bank (`recovery_phrases.json`, `use=persona_cooking_reply`) | Fact → voice_line → bank pick | `None` if bank empty | Deferred; `discoverable_facts_en.food` or phrase `text_en` | `food` |
| 10 | Job/occupation | `"你做什么工作"` + variants | `profile.occupation`, `voice_lines.work` | voice_line preferred, else `f"我是{occ}。"` | `"我也有工作。"` | Deferred; intent `job` | `work` |
| 11 | Travel — visited | `"你去过哪里"` + variants | `discoverable_facts.travel_where/.travel`, `voice_lines.travel` | Fact verbatim | `voice_lines.travel` → `"我去过几个城市，很有意思。"` | Deferred | `travel` |
| 12 | Favourite place | `"最喜欢"` + place marker | Same as #11 | Fact verbatim | `voice_lines.travel` → `"我去过几个地方，各有特色。"` | Deferred | `travel` |
| 13 | Food-preference comparison (A vs B) | `"菜/吃"` + comparator + preference marker | None (inline logic) | Inline template with extracted dish names | `"两个我都喜欢，各有各的味道。"` | Deferred (no persona source) | `food` |
| 14 | 你喜欢…吗 (city/hobby/food) | `t.startswith("你喜欢")` + `吗/呢/啊` | `profile.city/.hometown`, `voice_lines.hobby/.food`, inline `_CITY_LIKE_POOL` | Keyword-dependent branch | `"还挺喜欢的，你呢？"` | Deferred | `place`/`hobby`/`food` (keyword-dependent) |
| 15 | Hobbies/interests | `"你有什么爱好"` + variants | `profile.interests[0]`, `voice_lines.hobby` | voice_line or `f"我喜欢{interests[0]}。"` | `"我也有很多爱好。"` | Deferred; `voice_lines_en.hobby` | `hobby` |
| 16 | Who partner lives with | `"跟谁住"` + variants | `voice_lines.family` | voice_line verbatim | `"我现在自己住，但和家人经常联系。"` | Deferred | `family` |
| 17 | Sibling presence | `"你有姐妹/兄弟/哥/弟/姐/妹"` + variants | `discoverable_facts.family_siblings/.family` | First clause / negation check | `"我有几个兄弟姐妹，大家关系挺好的。"` | Deferred; `discoverable_facts_en.family_siblings` | `family` |
| 18 | Parents presence | `"你有爸爸妈妈"` + variants | `profile.age` (computed parent-age offset) | `f"有的，他们大概{p_age}多岁了，住在老家。"` | `"有的，我爸妈都在，住在老家。"` | Deferred | `family` |
| 19 | Family location | `"家人在哪"` + variants | `discoverable_facts.family_live`, `profile.hometown/.city` | Fact or comparison template | `f"家人在{loc}那边。"` / `"家人住得不太远。"` | Deferred; `discoverable_facts_en.family_live` | `family` |
| 20 | Has family (generic) | `"你有家人"` + variants | `voice_lines.family` | voice_line | `"我也有家人。"` | Deferred | `family` |
| 21 | Parent detail (age vs location) | `"你妈妈/爸爸/父母/爸妈"` + variants | `profile.age` (offset) or `voice_lines.family`/`discoverable_facts.family_live` | Age or location sub-branch | `"他们五十多岁了。"` / `"我父母住得不太远。"` | Deferred (age intent may misfire for parent age — see §13 RC-EN) | `family` |
| 22 | Sibling detail (age/work/location) | `"姐姐/哥哥/弟弟/妹妹"` present | `profile.age/.city/.hometown` (computed) | Sub-intent-dependent template | `f"我有一个{sib}，我们偶尔联系。"` | Deferred | `family` |
| 23 | Work enjoyment | `"喜欢"` + `"工作"` marker | `voice_lines.work_like` *(schema-optional, absent in current personas)*, `discoverable_facts.work`, `profile.occupation` | Chain of the above | `"还挺喜欢的，慢慢就越来越有意思了。"` | Deferred | `work` |
| 24 | Hobby duration | `"玩这个多久"` + variants | `discoverable_facts.hobby` | Full fact (often contains duration) | `"已经玩了好几年了，越来越喜欢。"` | Deferred | `hobby` |
| 25 | Hobby origin | `"怎么开始这个爱好"` + variants | `discoverable_facts.hobby_origin` | Fact verbatim | `"小时候接触到，慢慢就喜欢上了，一直坚持到现在。"` | Deferred; `discoverable_facts_en.hobby_origin` | `hobby` |
| 26 | Hobby best aspect | `"最喜欢这个爱好的哪一点"` + variants | `discoverable_facts.hobby_best` | Fact verbatim | `"让我放松的那种感觉，做完以后心情很好。"` | Deferred | `hobby` |
| 27 | Why like hobby | `"为什么喜欢这个爱好"` + variants | `discoverable_facts.hobby_best/.hobby_origin` | Best-fact or origin-fact | `"很难说具体原因，就是喜欢那种感觉，做了就停不下来。"` | Deferred | `hobby` |
| 28 | Place food — what's good to eat | `_is_place_food_question` (3769–3783) | `discoverable_facts.food` (place-matched), inline `_CITY_FOOD_POOL`, `_place_from_question_context()` | Personal fact if place==persona city/hometown, else pool pick | Falls through to feature handler (#29) if no pool/fact match | Deferred; intent `hometown_food` | `food`/`place` |
| 29 | Place features — what's special | `_is_place_feature_question` (3797–3818) | Inline `_CITY_FEATURE_POOL`, `discoverable_facts.travel_where/.travel/.place`, `profile.city/.hometown` | Pool pick → travel-fact clause → city pool → place fact | `f"哎，{loc}太有特色了，说也说不完！"` / `"那个地方很有特色，有机会可以去看看！"` | Deferred; intent `hometown_special` (EN deliberately `""` — see §13 RC-EN) | `place`/`travel` |
| 30 | Marriage/relationship status | `"你结婚"` + variants | `discoverable_facts.marriage` *(optional; absent in meiling/xiaoming)* | Fact verbatim | `_persona_deflect("marriage", t)` | Deferred via deflect EN map | `family` |
| 31 | Children | `"你有孩子/小孩/儿子/女儿/宝宝"` | **None read** — always deflects | n/a | `_persona_deflect("children", t)` only | Deferred via deflect EN map | `family` |
| 32 | Work difficulty/quality | `"难不难/累不累/辛不辛苦"` + variants | `profile.occupation`, `voice_lines.work` | voice_line or inline template | `"工作嘛，有时候忙，但还可以，挺有意思的。"` | Deferred | `work` |
| 33 | Age (persona's own) | `"你多大/几岁/年龄"` | `profile.age` | `f"我今年{age}岁。"` | `_persona_deflect("age", t)` | Deferred; intent `age` | `identity` |
| 34 | Family closeness | `"和爸爸妈妈近"` + variants | `discoverable_facts.family_live/.family` | Fact or first-clause extraction | `"挺近的，虽然不住在一起，但经常打电话联系。"` | Deferred | `family` |
| 35 | Why like a place | `"为什么喜欢那里"` + variants | `discoverable_facts.travel/.travel_where/.place`, `profile.city/.hometown` | Extracted why-clause | `"感觉那里很有特色，生活节奏和文化都挺吸引人的。"` | Deferred | `travel`/`place` |
| 36 | Bare 为什么/为啥 follow-up | Exact strings `"为什么"`, `"为啥"`, `"为啥呢"`, `"为什么呢"` | `profile.hometown`, `voice_lines.place/.work/.food` | Stable pool pick | `"因为习惯了，也比较熟悉。"` / `"因为我觉得挺合适的，慢慢就更喜欢了。"` | Deferred | *(no frame; generic follow-up)* |
| 37 | Where has long history | `"历史"` + place marker | `profile.hometown` | `f"像{ht}这样的地方，历史就很长。你慢慢会发现很多细节。"` | `"很多地方都有很长的历史，你慢慢看会发现很多细节。"` | Deferred | `place` |
| 38 | Work duration | `"工作多久/做了多久"` + variants | `discoverable_facts.work`, `profile.occupation` | Duration clause extraction | `f"做{occ}已经好几年了，越来越有经验了。"` / `"已经做了几年了，越做越有意思。"` | Deferred; intent `work_duration` | `work` |
| 39 | Extended family location | `"奶奶/爷爷/外婆/外公/姥姥/姥爷"` present | `profile.hometown/.city` | `f"我{rel}住在{ht}那边，离我有点远。"` etc. | `f"我{rel}住在老家，我们不常见面，但会联系。"` | Deferred | `family` |
| 40 | Distance — far or not | `"离那边/北京/上海/成都/广州远"` | `distance_profile.zh/.far_level/.reference`, `profile.hometown` | `distance_profile.zh` verbatim or template | `"不算太远。"` | Deferred; `distance_profile.en` | `place`/`travel` |
| 41 | Travel time to place | `"要多久/多久到/多长时间"` | `distance_profile.time/.transport` | `f"坐{transport}要{time}左右。"` | Default `"几个小时"`/`"交通工具"` | Deferred | `place`/`travel` |
| 42 | How to get there | `"怎么去/坐什么去/怎样去"` | `distance_profile.transport` | `f"一般坐{transport}去。"` | Default `"高铁"` | Deferred | `place`/`travel` |

**Precedence rules enforced by code order and comments:**

* #1 (place-name-of-residence) before #2 (hometown) before #3 (residence) — location questions are checked in a specific order (lines 3071–3072, 3081–3082).
* #4–#7 (name meaning/story/how-to-address) precede #10 (generic work), so name questions are never misrouted to occupation handling.
* #9 (cooking) precedes #10 (work) explicitly (comment at line 3139) so "你做什么菜" is not answered as a job question.
* #11–#12 (travel/favourite place) precede the later distance/residence facts.
* #28 (place-food) precedes #29 (place-features) explicitly (comment at lines 3387–3389) so food questions about a city are not answered as generic feature questions.
* #17 (sibling presence) precedes #22 (sibling detail) so a yes/no question is not misrouted to age/work/location sub-parsing.
* #38 (work duration) precedes the later `多长时间` travel-time check (#41) so a work-duration question phrased with `多长时间` is not misclassified as travel time.

**Inline Chinese fallback content**: a large volume of hardcoded Chinese exists directly in `_direct_persona_answer` and is **not** sourced from persona JSON — including all per-branch fallback templates listed above, and three large encyclopedic pools: `_CITY_LIKE_POOL` (#14), `_CITY_FOOD_POOL` (#28), and `_CITY_FEATURE_POOL` (#29). These pools are covered in §10 and flagged as an inline-content risk in §20.

**Missing-fact behaviour**: most families fall back to a generic inline sentence rather than returning `None`; only #7 (name/how-to-address, when `display_name` is empty) returns `None` outright, which allows the flat sequence to fall through to line 3684's terminal `return None`.

**Persona-specific vs generic**: families sourced from `profile`/`discoverable_facts`/`voice_lines`/`distance_profile` (majority of the 42) are persona-specific; families relying on inline city pools (#14, #28, #29) or fixed templates with no persona field read (#13, #31, #36 in the no-hometown case) are generic and identical across personas that share a hometown/city name.

**`_answer_user_question_prefix` integration** (lines 4952–5090): before reaching `_direct_persona_answer` (sub-step 21e per §4), the prefix function first tries a confusion guard, `_place_followup_reply`, `_find_mirror_answer` (a **second** mirror attempt distinct from Priority 20 in §4), and `_place_distance_counter_reply`. `_is_direct_persona_question(t)` (lines 2969–2989) is a separate **pattern probe** that calls `_direct_persona_answer(t, None)` with `persona=None` — it only tests whether *any* branch would structurally match, not whether persona data exists to answer it.

---

## 6. Persona-data precedence

Precedence is **not uniform** across intent families; it is decided per family by the order fields are checked inside `_direct_persona_answer` and inside `_persona_answer_en`. The following patterns recur:

* **Structured fact before generic template.** Most families check `discoverable_facts.<key>` or a computed `profile` field first, and only fall back to an inline Chinese template if the field is absent (e.g. #4 name meaning: `discoverable_facts.identity` → inline template; #11 travel: `discoverable_facts.travel_where`/`.travel` → `voice_lines.travel` → inline template).
* **`voice_lines` as a secondary source, not primary**, for most families — used when the more specific `discoverable_facts` key is empty (e.g. #10 job: `voice_lines.work` is actually checked **before** `f"我是{occ}。"`, i.e. `voice_lines` outranks the raw `profile.occupation` construction for this one family — precedence differs by family and must not be assumed uniform).
* **`distance_profile` is authoritative and exclusive** for families #40–#42; no fallback to `discoverable_facts` or `voice_lines` exists for distance/transport/travel-time — only inline numeric/string defaults.
* **Inline city pools (`_CITY_LIKE_POOL`, `_CITY_FOOD_POOL`, `_CITY_FEATURE_POOL`) take precedence over persona `discoverable_facts.food`/`.place` when the question names a city that is *not* the persona's own city/hometown** (#28, #29) — i.e. the persona answers about a third-party place from the encyclopedic pool, not from persona data, because persona JSON has no data about places other than its own hometown/city.
* **`_persona_deflect("<topic>", t)` overrides absent facts** for `marriage` (#30), `children` (#31, always), and `age` (#33, when `profile.age` is falsy) — these three families are the only ones that route to the shared deflection phrase bank (`content/recovery_phrases.json`) rather than an inline Chinese sentence when data is absent.

**Duplicate/competing sources of the same fact:**

* Hometown location can be answered by `profile.hometown` (families #2, #3, #37) **or** by `_CITY_LOCATION_BRIEF` (used only by `_reverse_fact_answer`'s `hometown_location` intent and `_place_followup_reply`, not by `_direct_persona_answer` directly) — two independent encyclopedic sources for the same city, one embedded in `_direct_persona_answer`'s templates, one in a separate module-level dict (§10).
* Place "features" content exists in **two** separate inline pools depending on call path: `_CITY_FEATURE_POOL` inside `_direct_persona_answer` (#29) and `_FEAT_POOL_INLINE` inside `_dedupe_persona_answer` (§12) — these are separately defined dicts, not a shared source, and can diverge.
* Place "food" content similarly exists in both `_CITY_FOOD_POOL` (#28) and `_FOOD_POOL_INLINE` (§12).
* Work information exists in `profile.occupation`, `voice_lines.work`, and `discoverable_facts.work` simultaneously; different families (#10, #23, #32, #38) each pick a different subset/order of these three fields.

---

## 7. Mirror and reverse-fact answers

### Mirror bank

`_find_mirror_answer(text, engine_id, persona)` — lines **6963–6989**. Invoked from two call sites: Priority 20 in the main chain (line 10232, gated on `user_asked_question`) and again as sub-step 21c inside `_answer_user_question_prefix` (a **second, independent attempt** using potentially different input text).

Mirror topic records are loaded from `content/mirror_questions.json` into `_MIRROR_QUESTIONS_BY_ENGINE` (module-level, built at startup). Each record contains at minimum: `zh` (canonical question text used for substring/exact match), `topic` (a string key consumed by `_mirror_persona_stub` and by `_QUESTION_TOPIC_TO_ENGINE` for E4), and an optional `paraphrases` array of keyword-group lists compiled at startup into `_MIRROR_FUZZY` for fuzzy all-keywords-present matching. Other fields present in the JSON (`py`, `en`, `kind`, `mirror_frame`, `curiosity`) are **not** read by `_find_mirror_answer` or `_mirror_persona_stub` for Chinese/English answer construction.

Chinese and English are both produced by `_mirror_persona_stub(topic, engine_id, persona)` (lines 6509+), which reads `discoverable_facts`, `discoverable_facts_en`, `voice_lines`, `voice_lines_en`, `profile`, and `distance_profile` keyed by the `topic` string. Many branches return `""` for English (no paired translation source exists for that topic).

**E4 participation:** mirror topic metadata feeds E4 through a **dedicated lookup table**, `_QUESTION_TOPIC_TO_ENGINE` (lines 6433–6459), keyed on the mirror's `topic` string — this is a **different mechanism** from the one used for E3/direct-persona answers (`_infer_question_topic_engine()`, a text classifier). If `_new_mirror_topic` is not a key in `_QUESTION_TOPIC_TO_ENGINE`, `_e4_engine_handoff` stays `None` even though a mirror answer was produced.

**When mirror content is stale or unavailable:** `_find_mirror_answer` returns `None` when no exact/fuzzy match is found (line 6989). The caller falls through to `_answer_user_question_prefix` (Priority 21), which retries the mirror bank internally (sub-step 21c) before trying place-distance, direct-persona, and fallback paths. There is no separate "stale mirror" detection inside the mirror bank itself; staleness of a **previously given** mirror answer is handled by the separate mirror-confusion escalation ladder (Priority 13, §9), which is a different code path entirely.

### Reverse-fact answers

`_detect_reverse_fact_intent(text)` (lines 4662–4686) classifies a direct-question text into one of eight intents: `marriage`, `age`, `hometown_food`, `hometown_special`, `work_duration`, `work_reason`, `job`, `hometown_where`.

`_reverse_fact_answer(intent, persona)` (lines 4689–4735) returns a **Chinese** string derived from `profile`/`discoverable_facts`/`voice_lines` for that intent, plus a ninth intent (`hometown_location`) that `_reverse_fact_answer` handles but `_detect_reverse_fact_intent` never returns (dead branch reachable only if called with a hardcoded intent string).

`_reverse_fact_answer_en(intent, persona)` (lines 4738–4820) returns the paired **English**, with an explicit code comment (RC-EN invariant, lines 4738–4760) stating that branches must return `""` rather than an incorrect gloss whenever the same intent string is triggered by structurally different questions (e.g. `age` fires for both the persona's own age and a parent's age — the function cannot tell which, so it returns `""` for `age` unconditionally rather than risk mismatched English).

**Dynamic facts supported** by the reverse-fact mechanism are the same eight/nine intents above — these are **persona self-facts** (job, age, hometown, marriage, work duration/reason, hometown food/features), not facts inferred about the learner. "Reverse-fact" in this codebase means "persona answers a direct question about itself via an intent→data lookup," as distinct from `_direct_persona_answer`'s pattern-matching-over-question-text approach.

**Mechanical difference from `_direct_persona_answer`:** `_reverse_fact_answer` (Chinese) is defined but has **no call site in `scripts/ui_server.py` outside its own definition and comments** — it is exercised only by `tests/test_regression_place_travel_reverse.py` directly, not by the production `/api/run_turn` handler. In production, Chinese answers always come from `_direct_persona_answer` or the mirror bank; `_reverse_fact_answer_en(intent, ...)` is the only reverse-fact function actually reachable in production, called from `_persona_answer_en()` (§13) using the intent computed from the **question text**, independent of which function produced the Chinese candidate.

**Translation regression that motivated the centralised path:** `tests/test_zh_en_synchronisation.py` documents (lines 7–16) that first-bad commit `0177994` ("fix: restore English gloss for deduped reverse-fact answers") introduced `_reverse_fact_answer_en` branches that returned unrelated English for dynamically-constructed Chinese (e.g. `hometown_special` returning the persona's current-city blurb instead of the actually-selected feature-pool sentence; `age` returning the persona's own age instead of a parent's age; `work_duration` returning a job description instead of a duration clause). The fix narrowed those three branches to return `""` (documented in the function's own docstring, lines 4738–4760) and is also enforced by `TestDeduplicationEnglishSync` in `tests/test_zh_en_synchronisation.py`, which asserts that `_persona_answer_en` is called with the final deduped Chinese, not the discarded candidate.

**Answering from persona facts vs. recent conversational context:** `_direct_persona_answer` and `_reverse_fact_answer`/`_reverse_fact_answer_en` answer strictly from **persona JSON** (`profile`, `discoverable_facts`, `voice_lines`, `distance_profile`) regardless of conversation history. Answering from **recent conversational context** instead is the distinct responsibility of E3 working memory (§8), which reads `recent_persona_replies`, not persona JSON directly.

---

## 8. E3 working-memory answers

`_extract_persona_facts_from_recent(recent_replies)` (lines 7004–7077) is a bounded, deterministic scan of the **last 5 entries** of the `recent_persona_replies` list, returning a dict that may contain `travel_visited`, `travel_fav`, `city_now`, `hometown`, `food_spicy`, `family_members`, and `work_desc` — extracted via keyword/regex matching over the concatenated recent-reply text. This is a **pure read**; it does not write to conversation state.

`_answer_from_working_memory(text, facts, persona)` (lines 7080–7135) matches the current question text against a fixed sequence of category checks — travel favourite, travel visited, food-spicy preference, hometown, current city, family — in that priority order (documented in the function's own docstring: "Sourcing priority: travel_fav > travel_visited > food_spicy > hometown > city_now > family"), returning `Optional[(zh, en)]`. Several branches return `""` for English. `work_desc` is extracted by `_extract_persona_facts_from_recent` but is **never read** by `_answer_from_working_memory` — a dead extraction.

**Confidence:** there is no numeric confidence score. E3 is considered usable when (a) `_counter_result is None`, (b) `user_asked_question` is true, (c) `_recent_persona_replies` is non-empty, and (d) both extraction and answer-matching functions succeed with a non-`None` result for the specific question-text pattern checked. Any pattern miss returns `None` and E3 contributes nothing.

**Priority relative to direct-answer and mirror:** E3 (Priority 19, §4) runs **after** the F2 adjacency guard (Priority 18) and **before** the mirror bank / prefix (Priority 20–21). This means E3 can pre-empt both the mirror bank and `_direct_persona_answer` (via the prefix) for a given question, provided a matching fact was extracted from recent replies.

**E4 participation:** E3 answers **can** trigger E4 — `_counter_is_working_memory` is set `True` at line 10222, and the E4 computation (lines 10300–10304) uses `_infer_question_topic_engine()` on the raw `submitted_text` of the last answer — the **same classifier function** used by the direct-persona E4 path (§15), but a **different** mechanism from the mirror bank's topic-map lookup.

**Three-entry cap effect on availability:** `recent_persona_replies` is capped to the **last 3** entries when written back to `response["state_update"]` (line 11826), but `_extract_persona_facts_from_recent` scans the **last 5** entries of whatever list is passed in. Under normal round-trip operation (client echoes back exactly what the server sent), E3 can only ever see at most 3 stored replies per turn; the 5-entry scan window only matters if a client sends a longer list than the server's own cap, which the production client is not observed to do.

**Not persistent learner memory:** E3 operates strictly on `recent_persona_replies`, a short rolling window of the **persona's own** recent answers, reset per the same-tab/cross-tab semantics documented in `docs/STATE_CONTRACT.md`. It is unrelated to any persistent learner-fact storage (e.g. `learner_stated_location`, `learner_memory`) described in §10 and §17.

---

## 9. Recovery and repair answers

All recovery paths below run inside the `last_turn_was_answer` gate (line 9896). Every function returning a tuple advances the frame ladder in the same turn — a recovery `counter_reply` does not itself skip frame selection.

| Recovery path | Trigger | Answer function | Produces new `counter_reply`? | Frame selection continues? | Can advance frame? | Cross-turn state completeness |
|---|---|---|---|---|---|---|
| Meaning request | `_is_meaning` (9951–9956): meaning markers, not `_lex_ct`, not `user_asked_question` | `_meaning_recovery_reply(last_partner_frame_text)` | Yes, `(zh, en)` — only if `last_partner_frame_text` non-empty | Yes | Yes | Sets `_confusion_about_app_q` flag only; fully server-local per turn |
| Example request | `_is_example` (9958–9963) | `_clarify_app_question(last_partner_frame_text)` | Yes, when frame text present | Yes | Yes | Same as above |
| Repeat/slower request | `_is_rr` (9966–9975): markers or bare repeat utterance | `_clarify_app_question(last_partner_frame_text)` | Yes, when frame text present | Yes | Yes | Same as above |
| App-question confusion (no prior counter_reply) | Confusion signal, no `_prev_counter_reply`, `not user_asked_question`, not confirmed-re-ask (10126–10140) | `_clarify_app_question(last_partner_frame_text)` | Yes, when frame text present | Yes | Yes | Server-local |
| Mirror confusion (Stage 1: restate) | Confusion signal + active `_cs_mirror_topic`, `mirror_confusion_count == 0` (10088–10108) | `_mirror_restate_naturally(prev_counter_reply, mirror_topic)` | Yes, `(zh, en)` | Yes | Yes | **Incomplete** — see note below |
| Mirror confusion (Stage 2: simplify) | Same guard, `mirror_confusion_count == 1` | `_mirror_persona_stub_simple(mirror_topic, mirror_engine, persona)` | Yes | Yes | Yes | **Incomplete** — see note below |
| Mirror confusion (Stage 3+: generic recovery) | Same guard, `mirror_confusion_count >= 2` | `_confusion_recovery_reply(text, prev_counter_reply, seed)` | Yes | Yes | Yes | **Incomplete** — see note below |
| Generic confusion (no active mirror topic) | Confusion signal, `_prev_counter_reply` present, no mirror topic (10115–10125) | `_confusion_recovery_reply(text, prev_counter_reply, seed)` | Yes | Yes | Yes | Server-local |
| Frustration/insult repair | `_is_frustration_or_insult(answer_text)` (highest priority, 9902–9908) | `_frustration_repair_reply(seed)` | Yes, unless phrase bank unloaded | Yes | Yes | Server-local; suppresses `reaction_prefix_text` |
| Learner-disclosure empathy | `_is_learner_disclosure(answer_text)` (9909–9916) | `_disclosure_empathy_reply(seed)` | Yes | Yes | Yes | Server-local |
| Persona challenge | `_is_persona_challenge(answer_text)` (9917–9924) | `_persona_challenge_reply(seed)` | Yes | Yes | Yes | Server-local |
| Pending-frame commitment clarification | Off-topic answer to a `_COMMITMENT_GUARD_FRAMES` frame, no explicit topic switch, no relevance match (10162–10182) | `_clarify_app_question(last_partner_frame_text)` | Yes, when frame text present | Yes | Yes, but frame selection is guarded to stay in the same engine (line 10680–10708, `listening_move_reason = "offtopic_pending_frame"`) | Server-local within the same turn's frame-selection guard |
| Noisy-location clarification | `"CITY" in slot_names`, no resolvable location, other guards (10141–10161) | *(none — flag-only; see §4 Priority 16)* | **No** — this is a `frame_text` override, not a `counter_reply` producer | Yes | Yes, via a dedicated post-response frame-text rewrite (lines ~11570–11659) that escalates by retry count | **Incomplete** — client does not transport `location_retry_count`/`location_clarify_hint` across turns, per `docs/STATE_CONTRACT.md` §16.3 (SIC-6, resolved for E4 only; noisy-location remains open) and `docs/CONVERSATION_ARCHITECTURE.md` §12.3 |

**Preserved finding on mirror-confusion and noisy-location escalation:** per the already-approved `docs/CONVERSATION_ARCHITECTURE.md` §12.2–§12.3 and `docs/STATE_CONTRACT.md` §16 (open state-interaction concerns list), the **server-side functions** for mirror-confusion escalation (`_mirror_restate_naturally`, `_mirror_persona_stub_simple`, `_confusion_recovery_reply`, staged by `mirror_confusion_count`) and for noisy-location retry escalation are exercised directly by server-side unit/integration tests using function calls or state injection, but the **client does not transport** `mirror_confusion_count` (partially — see `docs/STATE_CONTRACT.md` for the exact consumed/unconsumed field list) or `location_retry_count`/`location_clarify_hint` reliably across turns in the same way E4's `current_engine` now does after the R2 fix. This document does not re-derive that finding; it is recorded here only as it pertains to whether these recovery paths' escalation state fully round-trips — it does not.

**Repair escalation (post-chain, not in the priority table):** lines 10402–10426. Trigger: `last_turn_was_answer`, `_is_confusion_signal(answer_text)`, and `_repair_attempt_count >= 2` plus additional guards. This directly overwrites `_counter_reply`/`_counter_reply_en` with one of three fixed escalation phrases ("你可以再说一遍吗？", an ASR near-match acknowledgement, or "没关系，我们换个话题吧。"). It runs **after** deduplication (§12) and can replace whatever the priority chain plus dedup already produced — this is the **last** point in the handler at which `_counter_reply` can change before pinyin derivation and frame selection.

---

## 10. Place and food answer pools

Three encyclopedic sources exist for **place** answers, and they are **not** unified into one lookup:

* **`_CITY_LOCATION_BRIEF`** (lines 4361–4373) — one-line location descriptions for 11 Chinese cities. Used by `_context_city_from_text()`, `_place_followup_reply()` (在哪儿 questions inside `_answer_user_question_prefix`), and `_reverse_fact_answer`'s `hometown_location` intent (a code path with no production caller — §7). **Not** used by `_direct_persona_answer`.
* **`_CITY_FOOD_POOL`** (lines 3391–3403, inside `_direct_persona_answer`) — per-city food descriptions for family #28 (place-food).
* **`_CITY_FEATURE_POOL`** (lines 3441–3456, inside `_direct_persona_answer`) — per-city feature descriptions for family #29 (place-features).

A **separate pair** of pools exists inside the deduplication substitution function (§12), used only when a same-intent reselection is needed after a repeat is detected: `_FEAT_POOL_INLINE` (lines 4895–4917) and `_FOOD_POOL_INLINE` (lines 4927–4944). These are independently defined dicts from `_CITY_FOOD_POOL`/`_CITY_FEATURE_POOL` and can diverge in content.

**Question-focus place resolution when multiple city names occur in one utterance:** `_place_from_question_context(t, recent_replies)` (lines 4441–4464) documents and implements a three-level priority: (1) a city that immediately precedes a feature/food question marker, matched via `_CITY_BEFORE_QUESTION_MARKER_RE` (lines 4434–4438) and validated as a key in `_CITY_LOCATION_BRIEF`; (2) the first known city found anywhere in the text (`_context_city_from_text`); (3) a deictic reference (那里/这儿/那边) resolved from `recent_persona_replies`. Example: in `"我不喜欢上海，成都有什么特别？"`, 成都 wins because it is the city immediately preceding the feature-question marker, not 上海 which appears earlier in the sentence.

**Fallback when no system knowledge entry exists for a place:** for feature questions, if the resolved place is neither a persona city/hometown nor in the encyclopedic pools, the handler falls back to a generic template — `f"哎，{loc}太有特色了，说也说不完！"` if any location string is available, else `"那个地方很有特色，有机会可以去看看！"` (lines 3520–3524). For a 在哪儿 (where-is) question about an unknown city, `_place_followup_reply` returns `(f"{city}在中国，是个很有特色的城市。", "")` if a city name was extracted at all, or `None` to let the caller apply `_persona_limitation_reply` (lines ~4599–4601).

**Learner-supplied location fact vs. system knowledge about a place — distinct data sources:**

| Data | Storage | Written by | Read by |
|---|---|---|---|
| System encyclopedic knowledge | `_CITY_LOCATION_BRIEF`, `_CITY_FEATURE_POOL`, `_CITY_FOOD_POOL` (hardcoded module-level dicts) | Never — static at code load | Answer-source functions for questions about *known* Chinese cities |
| Learner-stated open-world location | `learner_stated_location` in `conversation_state` | Set when the learner volunteers or confirms a residence location, including places (e.g. 达尼丁) with **no** entry in the encyclopedic pools | Frame slot fill (`learner_memory["lives_in"]`), deictic resolution in `_place_from_question_context` |

A place the learner mentions can be **stored** as `learner_stated_location` regardless of whether the system has any encyclopedic knowledge about it; the system cannot **describe** that place beyond the generic fallback templates above unless it happens to be a persona's own city/hometown or a key in one of the three hardcoded pools. This distinction is the basis of the open-world food/location test coverage in `tests/test_open_world_food_and_location_fixes.py`.

---

## 11. Volunteered information and empathetic follow-ups

| Source | Trigger | Acknowledgement | Empathetic follow-up | Direct answer | Engine redirection | Question inside `counter_reply` vs. `frame_text` |
|---|---|---|---|---|---|---|
| Volunteered travel intent | `not user_asked_question and _has_volunteered_travel_intent(answer_text)` (9936–9940) — travel verbs or time-marker + 去 | Implicit in the templated reply | Yes — template includes a follow-up question | No (no persona fact retrieved) | Separate: `force_travel_bridge` via `_should_route_to_travel()` (lines 9330–9335, 10604–10618) can bridge to travel-engine frames on the **next** frame, independent of this `counter_reply` | Question is inside `counter_reply` (`{DEST}`-slotted template from `recovery_phrases.json`, `use=travel_intent_followup`); `frame_text` on the same turn is unaffected by this path |
| Health/concern disclosure | `_is_learner_disclosure(answer_text)` (549–567) | Empathy phrase from bank | Yes, phrase itself is the empathetic acknowledgement | No | None | Empathy statement is the `counter_reply`; no forced follow-up question observed in the bank content itself |
| Frustration/insult | `_is_frustration_or_insult(answer_text)` (3885–3896) | Repair phrase from bank; suppresses `reaction_prefix_text` | Yes — repair framing | No | None | Repair statement is the `counter_reply` |
| Responsive food statement (declarative, not a question) | `_responsive_food_answer` precomputed flag (9227–9234, from `_is_responsive_food_answer`, 1975–2001): prior frame was a place-food question and the reply is declarative | Yes — acknowledges extracted food items or a pool pick | Yes — all `_food_responsive_reply` branches ask a natural follow-up question | No | None observed | Follow-up question is inside `counter_reply`; no `frame_text` involvement |
| Explicit topic switch | Detected via `_is_explicit_topic_switch()`, consumed by the pending-frame commitment guard (§9) rather than being an answer source itself | n/a | n/a | n/a | Escapes the commitment guard so normal frame selection resumes on the next frame | Not an answer-producing source; it is a guard-bypass signal |

---

## 12. Deduplication and answer substitution

**Pool composition:** `_dedup_pool = ([_prev_counter_reply] if _prev_counter_reply else []) + list(_recent_persona_replies or [])` (line 10350).

**Gate:** dedup logic runs only `if _counter_reply and _counter_reply.strip() in _dedup_pool:` (line 10352) — an **exact string** membership test. This means dedup is **not applied uniformly to every answer source**; it is a single post-chain guard that fires only when the just-produced `_counter_reply` happens to exactly match something already in the pool. There is exactly **one** call site for `_dedupe_persona_answer()` in the handler (line 10353).

**Discourse-prefix stripping:** `_strip_discourse_prefix(s)` (lines 1922–1929) strips leading `"我呢，"`, `"我呢,"`, `"我，"`, `"我,"` so that a pool item's bare form can be compared against its `我呢，`-prefixed stored form. Both `_dedupe_persona_answer`'s membership test and `_dedup_pool` construction apply this via `bare_cand`/`recent_bare` normalisation (lines 4874–4877).

**Exact-match detection:** a candidate is treated as stale if either its bare form is in the bare-normalised recent set, or the raw candidate string is in the raw `recent_replies` list (lines 4886–4887).

**Same-intent pool reselection:** `_dedupe_persona_answer()` (lines 4867–4949) — Step 1 attempts to re-pick from the **same-intent** pool: if the question was a place-feature question, it uses `_FEAT_POOL_INLINE`; if place-food, `_FOOD_POOL_INLINE`; selection uses `_pick_not_in(pool, seed, recent_set)` to avoid re-selecting something already in the recent/dedup set. Note these are the pools described in §10, **separate** from `_CITY_FEATURE_POOL`/`_CITY_FOOD_POOL` used by `_direct_persona_answer`.

**Fallback when the pool is exhausted (or the question is not a recognised place-feature/place-food question):** Step 2 returns `_persona_deflect("generic", cand)` (line 4949) — explicitly **not** a call to `_reverse_fact_answer` or any other answer function. This is a topically generic clarification/deflection phrase from `content/recovery_phrases.json`, not a fresh fact.

**Scope — applies to selected sources only, via exact-match, not by source identity:** dedup is source-agnostic in the sense that it operates purely on the string value of `_counter_reply`, regardless of which of the 22 priorities produced it. It is limited in practice to **place-feature/place-food repick logic**, meaning any other answer source (e.g. a hobby fact, a family fact) that happens to repeat gets no same-intent reselection — it falls straight to the generic-deflection fallback in Step 2.

**Final English regeneration after substitution — exact call sequence (lines 10348–10367):**

```10348:10367:c:\Users\Surface Pro7\OneDrive\Documents\GitHub\MandarinOS-core\scripts\ui_server.py
 _dedup_pool = ([_prev_counter_reply] if _prev_counter_reply else []) + list(_recent_persona_replies or [])
 if _counter_reply and _counter_reply.strip() in _dedup_pool:
 _deduped = _dedupe_persona_answer(
 _counter_reply, _dedup_pool, _last_text_for_counter, persona,
 )
 if _deduped and _deduped.strip() != _counter_reply.strip():
 _counter_reply = _deduped
 _counter_reply_en = _persona_answer_en(
 persona, _counter_reply,
 _detect_reverse_fact_intent(_last_text_for_counter),
 )
 else:
 _counter_reply = _persona_deflect("generic", _counter_reply)
 _counter_reply_en = _persona_answer_en(persona, _counter_reply)
```

`_persona_answer_en()` is called **after** `_counter_reply` is reassigned to `_deduped` — English is derived from the **final substituted Chinese**, not the discarded original candidate. This exact ordering is asserted by `TestDeduplicationEnglishSync` in `tests/test_zh_en_synchronisation.py`.

**Belt-and-suspenders exact-repeat guard** (lines 10372–10374) runs immediately after: if `_counter_reply` (post-dedup) still exactly equals `_prev_counter_reply`, it is forcibly replaced with `_persona_deflect("generic", ...)` and English is regenerated again via `_persona_answer_en()`.

**Working-memory update after the final answer:** `response["state_update"]["last_counter_reply"]` and `["recent_persona_replies"]` are written at lines 11816–11827, using the value of `_counter_reply` **after** dedup, the exact-repeat guard, and repair escalation have all had a chance to run — i.e. strictly the final answer that goes to the learner, never an intermediate candidate.

**State explicitly stated:** English and pinyin must correspond to the final substituted Chinese, not the discarded candidate — this is enforced code behaviour (as shown above), not merely an intended contract.

**Same-tab reset gap for `last_counter_reply`:** cross-referencing `docs/STATE_CONTRACT.md` (working-memory reset semantics for `last_counter_reply` vs. `recent_persona_replies` vs. `last_partner_frame_text`), the exact reset/clearing behaviour of `last_counter_reply` across tab/session boundaries is authoritatively defined there; this document only asserts that answer generation **writes** `last_counter_reply` unconditionally from the final `_counter_reply` each turn (line 11822) and **reads** `_prev_counter_reply` from `cs["last_counter_reply"]` at the start of the same turn (line 9872) — see §17 for the full read/write table.

---

## 13. Chinese-to-English contract

`_persona_answer_en(persona, zh, intent=None)` (lines 4823–4864) is the **single translation path** for Chinese persona answers reachable from the main handler's own English-regeneration call sites (dedup at 10361–10364, exact-repeat guard at 10374, explicit-place-topic at 10021–10024, stale-override at 10075–10078, and the `_answer_user_question_prefix` direct-persona sub-step at 5003). It is not the only English source overall — mirror-bank and E3 answers produce their own English directly as part of their `(zh, en)` tuples (§7, §8) and are **not** routed through `_persona_answer_en()`.

**Actual resolution order inside `_persona_answer_en()` (verified from code, which differs from its own docstring's stated order):**

| Resolution stage | Function/data source | Applicable answer types | Failure behaviour |
|---|---|---|---|
| 1 | `_en_for_counter_reply(d, inner)` — fixed deflection/recovery phrase map, with `"As for me — "` prefix logic when `zh` starts with `我呢，` | Any candidate matching a phrase in `_persona_deflect_en_map` | Falls to stage 2 if no match |
| 2 | `_voice_line_en_for_zh(persona, d)` / `(persona, inner)` — matches `voice_lines` values against `voice_lines_en` by key | Any candidate that is exactly a persona `voice_lines` string (full or `我呢，`-stripped) | Falls to stage 3 |
| 3 | `_reverse_fact_answer_en(intent, persona)` — only if caller supplied a non-`None` `intent` (from `_detect_reverse_fact_intent`) | Reverse-fact-classifiable direct questions | Falls to stage 4; several intents (`hometown_special`, `age`, sometimes `work_duration`) unconditionally return `""` per the RC-EN invariant (§7) |
| 4 | Scan of `discoverable_facts` for a value equal to or contained in `d`/`inner`, then paired lookup in `discoverable_facts_en` by the same key | Dynamic persona answers sourced from `discoverable_facts` (e.g. cooking replies) | Falls to stage 5 if no key's value matches |
| 5 | `_persona_deflect_en(d)` / `_persona_deflect_en(inner)` — phrase-bank lookup for cooking-fallback and other deflect-style replies | Phrase-bank-sourced replies not already caught by stage 1 | Returns `""` (final) |

**Fixed deflection/recovery translation maps:** `_persona_deflect_en_map` (Chinese phrase → English) is built at startup from `content/recovery_phrases.json` entries where `use == "persona_deflect"` (lines ~395–420), read via `_persona_deflect_en()` (lines 469–471) and `_en_for_counter_reply()` (lines 504–515).

**Can an answer-source-provided English value be replaced later?** Yes. Any `(zh, en)` tuple's `en` value can be overwritten if the answer subsequently passes through §12's dedup/exact-repeat/repair-escalation overrides, because those call sites recompute `_counter_reply_en` from the new `_counter_reply` via `_persona_answer_en()` rather than preserving the original tuple's English.

**Answer paths where final English can legitimately be empty (`""`):**

* `_persona_answer_en()`'s own final fallthrough (line 4864) when no stage matches.
* `_voice_line_en_for_zh()` returning `""` when no `voice_lines` key matches (line 484).
* `_en_for_counter_reply()` returning `""` when no deflect-map entry matches (line 515).
* `_reverse_fact_answer_en()`'s deliberately narrowed branches — `hometown_special`, `age`, and `work_duration` (when no duration clause is extractable) always or conditionally return `""` (§7 RC-EN invariant).
* Mirror-bank (`_mirror_persona_stub`) and E3 (`_answer_from_working_memory`) tuples with an empty second element for many topic branches (both functions return `""` when no paired `*_en` field exists for that topic/fact).
* `_answer_user_question_prefix`'s `_soft_persona_fallback` wrap, which always returns `(zh, "")` (line ~5080).
* The initial `_counter_result[1]` extraction (line 10286) simply propagates whatever the source function returned, including `""`.
* Response assembly omits the field entirely when empty (`if _counter_reply_en: response["counter_reply_en"] = ...`, lines 11818–11819) — an empty English is **not** distinguishable in the response payload from a field that was never computed.

**Gap labelling:**

* The RC-EN narrowing (hometown_special/age/work_duration returning `""`) is **structurally prevented** from being wrong (by design, per the code comment) but **known missing mapping** in the sense that no correct per-question English is ever supplied for these three intents via this path — it relies entirely on stage 1/2/4 catching the actual phrase first, or the field remaining empty in the response.
* Mirror-bank/E3 empty-English branches are **known missing mapping** — **partially covered**: some topics have `*_en` counterparts in persona JSON and some do not, and no test enumerates full coverage across all mirror topics or all E3 fact categories.
* The dedup/exact-repeat-guard re-translation call sequence (§12) is **test-covered** by `TestDeduplicationEnglishSync` in `tests/test_zh_en_synchronisation.py`.
* Coverage of `_persona_answer_en()`'s five-stage precedence as a whole is **unverified** beyond the specific regression scenarios in `tests/test_zh_en_synchronisation.py` — no test iterates all 42 `_direct_persona_answer` intent families to confirm each produces non-empty English through this path.

---

## 14. Chinese-to-pinyin contract

There is **no programmatic romanisation library** in `scripts/ui_server.py` (no `pypinyin` or equivalent import). `counter_reply_pinyin` is produced exclusively by `_resolve_counter_reply_pinyin(zh)` (lines 487–501), a **curated map lookup**:

```487:501:c:\Users\Surface Pro7\OneDrive\Documents\GitHub\MandarinOS-core\scripts\ui_server.py
def _resolve_counter_reply_pinyin(zh: str) -> str:
    """Curated pinyin when counter_reply matches a persona_deflect phrase (full line or 我呢，+inner)."""
    s = (zh or "").strip()
    if not s:
        return ""
    if s in _persona_deflect_pinyin_map:
        return _persona_deflect_pinyin_map[s]
    _prefix = "我呢，"
    if s.startswith(_prefix):
        inner = s[len(_prefix) :].strip()
        if inner and inner in _persona_deflect_pinyin_map:
            py = _persona_deflect_pinyin_map[inner]
            if py:
                return f"wǒ ne，{py}"
    return ""
```

`_persona_deflect_pinyin_map` is populated at startup from the `pinyin` field of entries in `content/recovery_phrases.json` (the same phrase bank used for `_persona_deflect_en_map`).

**Timing relative to deduplication and Chinese finalisation:** pinyin is computed at line 10428, **after** the priority chain, dedup (§12), the exact-repeat guard, and repair escalation have all run — i.e. from the **final** `_counter_reply` value, the same guarantee documented for English in §12/§13.

**Handling of punctuation, Latin text, digits, names, or unknown characters:** none. The function performs only an **exact string key lookup** (full string, then `我呢，`-stripped inner string) in `_persona_deflect_pinyin_map`; there is no character-by-character conversion, so punctuation, Latin text, digits, and unknown characters have no special handling — a non-matching string of any composition simply falls through to `return ""`.

**Pinyin supplied directly by content, not derived programmatically:** yes, in three unrelated places, none of which feed `counter_reply_pinyin`:

| Source | Field | Feeds `counter_reply_pinyin`? |
|---|---|---|
| `content/recovery_phrases.json` | `pinyin` per phrase | **Yes** — via `_persona_deflect_pinyin_map`, the only source |
| `personas/*.json` | `name_pinyin` | No — used for `partner_name_pinyin` (a different response field) |
| `p2_frames.json` | `pinyin` per frame | No — used for `frame_pinyin`, not `counter_reply_pinyin` |
| `content/mirror_questions.json` | `py` per question | No — not read by `_find_mirror_answer` or `_mirror_persona_stub` at all |

**Fallback on conversion failure:** there is no conversion step to fail; a lookup miss returns `""`, and the response omits `counter_reply_pinyin` entirely when it is empty (`if _counter_reply_pinyin: response["counter_reply_pinyin"] = ...`, lines 11820–11821).

**Practical consequence:** the great majority of `counter_reply` values — all 42 `_direct_persona_answer` intent families, all mirror-bank answers, all E3 answers, all reverse-fact-sourced Chinese — receive **no server-side pinyin** unless the exact final string happens to equal a phrase in the recovery-phrases pinyin map (chiefly deflection/recovery-style replies). `tests/test_zh_en_synchronisation.py` (lines ~404–408) acknowledges that the client may independently build pinyin from a client-side lexicon when the server returns `""`, but that client-side mechanism is out of scope for this document (it is not part of `scripts/ui_server.py`'s answer generation).

---

## 15. E4 eligibility and answer confidence

E4 eligibility is computed once, at lines 10296–10313, immediately after the priority chain produces `_counter_result` and before dedup/repair escalation can alter it (§3).

```10296:10313:c:\Users\Surface Pro7\OneDrive\Documents\GitHub\MandarinOS-core\scripts\ui_server.py
    _e4_engine_handoff: Optional[str] = None
    if user_asked_question and _counter_result:
        if _counter_is_new_mirror and _new_mirror_topic:
            _e4_engine_handoff = _QUESTION_TOPIC_TO_ENGINE.get(_new_mirror_topic)
        elif _counter_is_working_memory:
            _e4_q_text = (
                (last_answer.get("submitted_text") or "") if isinstance(last_answer, dict) else ""
            ).strip()
            _e4_engine_handoff = _infer_question_topic_engine(_e4_q_text)
        elif _last_text_for_counter:
            _e4_dp_deflects = set(_persona_deflect_phrases.get("generic") or [])
            if _counter_result[0] not in _e4_dp_deflects:
                _e4_engine_handoff = _infer_question_topic_engine(
                    _last_text_for_counter
                )
```

**`user_asked_question`** is the master gate: no answer source produces an E4 handoff unless the learner's utterance was classified as a genuine question (`_is_user_question()`, computed at lines 9218–9220, and forced `False` by `_responsive_food_answer` at 9227–9234 even if it otherwise looked like a question).

**`_counter_result`** must be non-`None` — a flag-only branch (Priority 16, noisy location) or an unmatched Group 2 elif (e.g. `_is_meaning` matching but with no frame text) never reaches this block with a usable result.

**`_counter_is_new_mirror` / `_counter_is_working_memory`** are mutually-exclusive-in-practice booleans set earlier in the chain (Priority 20 and Priority 19 respectively) that select which of two different topic-classification mechanisms is used: the mirror bank's static `_QUESTION_TOPIC_TO_ENGINE` map keyed by `_new_mirror_topic`, versus the text classifier `_infer_question_topic_engine()` for both E3 and the direct-persona/default `elif` branch.

**Generic-deflection exclusion:** there is no function named `_is_generic_deflection`. The exclusion is an inline set-membership check, `_counter_result[0] not in set(_persona_deflect_phrases.get("generic") or [])` (lines 10309–10310), applied only in the `elif _last_text_for_counter:` (direct-persona/default) branch. Note this exclusion is **not** applied to the mirror or working-memory branches — those are gated only by `user_asked_question` and their respective flags, not by generic-deflection membership, because mirror/E3 answers are not expected to ever equal a generic deflection phrase.

**Topic inference** for the working-memory and direct-persona paths is delegated to `_infer_question_topic_engine()`, a text classifier over the raw question text (`submitted_text` for E3, `_last_text_for_counter` for direct-persona) — this function's own internal logic is not re-derived here; it is documented as the general question→engine classifier in `docs/CONVERSATION_ARCHITECTURE.md`.

**Cases where a valid answer does not trigger E4:**

* Any answer produced while `user_asked_question` is `False` (all of Priorities 1–5, 8–18, and the mirror-confusion ladder) — these are never eligible regardless of answer quality, because they are direct-persona-question-independent by construction (recovery/repair/volunteered-info responses).
* A direct-persona/default-branch answer that happens to equal a generic deflection phrase (explicitly excluded, 10309–10310).
* A mirror answer whose `_new_mirror_topic` is absent from `_QUESTION_TOPIC_TO_ENGINE` (falls through to `_e4_engine_handoff = None` with no further attempt).
* Priority 22a's generic-deflection bypass, which **replaces** the answer with a `_clarify_app_question()` result after E4 was already computed from the original deflected answer — the E4 decision made at line 10296–10313 is **not recomputed** after this replacement, so if the original deflection happened to be eligible (it structurally cannot be, per the exclusion above) the point would be moot; but more importantly, dedup/repair-escalation replacements (§12, §9) that happen **after** line 10313 never get a chance to revise `_e4_engine_handoff` even though they change `_counter_reply`.

**Cases where a recovery or empathetic reply must not trigger E4:** by construction, every recovery/repair function in §9 (meaning, example, repeat/slower, confusion recovery, mirror-confusion ladder, frustration repair, disclosure empathy, persona challenge, pending-frame clarification) either sets `_counter_result` while `user_asked_question` is required to be `False` for its trigger condition, or — for frustration/disclosure/challenge, which are **not** gated on `user_asked_question` in their own trigger conditions — simply never reaches an E4-eligible branch because E4's `elif _last_text_for_counter:` fallback only activates when none of the mirror/working-memory flags are set, and the generic-deflection check does not specifically special-case these three reply types; their *practical* exclusion from E4 depends on `user_asked_question` being `False` in the same turn (the master gate), which is the normal circumstance for a frustration/disclosure/challenge utterance but is not independently enforced by a dedicated code guard for these three specific functions.

| Answer-source class | Question required? | Considered confident? | Generic-deflection check? | E4 eligible? | Engine source |
|---|---|---|---|---|---|
| Frustration/disclosure/persona-challenge repair | No (own trigger) | n/a | No | Practically no — relies on `user_asked_question` master gate | n/a |
| Responsive food / volunteered travel | No (`not user_asked_question` in trigger) | n/a | No | No — trigger itself requires `user_asked_question` false | n/a |
| Explicit place-topic / stale-override (direct persona) | Implicitly, via reaching the `elif _last_text_for_counter:` branch when `user_asked_question` is true | Yes, if not a generic deflection | Yes | Yes | `_infer_question_topic_engine(_last_text_for_counter)` |
| Meaning/example/repeat-slower/lexical/confusion recovery | No (`not user_asked_question` in trigger) | n/a | No | No | n/a |
| Mirror confusion ladder | No (`not user_asked_question` in trigger) | n/a | No | No | n/a |
| F2 why-like adjacency | Not required by its own trigger | n/a | Implicitly, via the same `elif _last_text_for_counter:` fallback if it is the branch reached | Possible, via the direct-persona fallback path | `_infer_question_topic_engine` |
| E3 working memory | Yes (`user_asked_question` required in trigger, 10215) | Yes, if `_answer_from_working_memory` returned non-`None` | No (not applied to this branch) | Yes | `_infer_question_topic_engine(submitted_text)` |
| Mirror bank | Yes (`user_asked_question` required, 10232) | Yes, if a match was found | No (not applied to this branch) | Yes, if `_new_mirror_topic` is in `_QUESTION_TOPIC_TO_ENGINE` | `_QUESTION_TOPIC_TO_ENGINE.get(topic)` |
| `_answer_user_question_prefix` direct-persona sub-step (21e) | Falls under the same `elif _last_text_for_counter:` E4 branch | Yes, if not a generic deflection | Yes | Yes | `_infer_question_topic_engine` |
| `_soft_persona_fallback` / `_topic_aware_honest_fallback` / `_persona_limitation_reply` (prefix catch-all) | Reachable when `user_asked_question` is true and mirror/direct paths all missed | Not specifically excluded by generic-deflection check unless the returned zh happens to equal a generic-deflect phrase | Only incidentally | Possible — no dedicated exclusion beyond the shared generic-deflect set | `_infer_question_topic_engine` |

**Cross-reference:** the complete client-side E4 transport contract (how `state_update.current_engine` is applied on the following request, `_resolveNextEngineId()`, and the two-turn handoff sequence) is documented in `docs/CONVERSATION_ARCHITECTURE.md` §5.5/§8 and `docs/STATE_CONTRACT.md` (current_engine semantics section); this document only covers the **server-side eligibility decision**, not client consumption.

---

## 16. Unsupported and out-of-scope questions

Three distinct fallback mechanisms exist, reachable only inside `_answer_user_question_prefix`'s tail (sub-steps 21j–21l per §4), in this order:

```5075:5090:c:\Users\Surface Pro7\OneDrive\Documents\GitHub\MandarinOS-core\scripts\ui_server.py
    _soft = _soft_persona_fallback(t, persona)
    if _soft:
        return (_soft, "")
    _topic_honest = _topic_aware_honest_fallback(t, persona)
    if _topic_honest:
        return _topic_honest
    _topic_hint = _context_city_from_text(context_reply) or ""
    zh = _persona_limitation_reply(_topic_hint)
    return (zh, "I'm not sure about that. I'm just a practice computer persona.")
```

* **`_soft_persona_fallback(t, persona)`** (lines 4394–4420) — returns `Optional[str]` (Chinese only) for harmless unsupported questions (name meaning trivia, routine, generic-feeling questions) where the persona can give a plausible generic answer using its own voice without claiming a specific unsupported fact. Caller always wraps it as `(_soft, "")` — **English is always empty** for this path by construction.
* **`_topic_aware_honest_fallback(t, persona)`** (lines 7187–7222) — returns `Optional[(zh, en)]`, staying within the question's topic domain (using persona `voice_lines`/facts where available) while being honest that the persona cannot fully answer. Some branches return `en=""`.
* **`_persona_limitation_reply(topic_hint)`** (lines 4376–4391) — returns `str` only (Chinese); this is the **unconditional final fallback** — it always returns a non-empty string. English is supplied at the call site as a fixed literal, `"I'm not sure about that. I'm just a practice computer persona."` (line 5090), not by the function itself.

**Difference from a generic deflection:** the generic-deflection phrase bank (`_persona_deflect_phrases["generic"]`, from `content/recovery_phrases.json`) is a **separate** mechanism used by (a) `_dedupe_persona_answer()`'s pool-exhausted fallback (§12) and (b) the post-prefix generic-deflection bypass (Priority 22a, §4) — it is not one of the three functions above, and its phrases are a fixed small set rather than the topic-aware/limitation logic described here.

**How unsupported questions differ from failed classification:** an unsupported question **reaches** `_answer_user_question_prefix`'s tail because it *was* classified as `user_asked_question` (or `_is_direct_persona_question`) but no mirror, place-distance, or `_direct_persona_answer` branch matched it. A **failed-classification** case (e.g. a confusion signal that is not a genuine question) is filtered out earlier — the prefix function's own confusion guard at its entry returns `None` for non-persona-start confusion signals before reaching any of these three fallbacks.

**English/pinyin coverage:** incomplete by construction — `_soft_persona_fallback` always yields `en=""`; `_topic_aware_honest_fallback` yields `en=""` in specific branches; `_persona_limitation_reply`'s English is a single fixed literal regardless of the Chinese topic hint used. Pinyin coverage for all three is governed solely by §14's map-lookup mechanism — none of these three functions' typical outputs are recovery-phrase-bank strings, so they typically receive **no** `counter_reply_pinyin`.

**E4 eligibility:** all three fallbacks are reachable only when the prefix function was invoked (i.e., `user_asked_question` was true or `_is_direct_persona_question` matched), which places their result inside the `elif _last_text_for_counter:` E4 branch (§15) — they are **not** specifically excluded from E4 unless their returned Chinese happens to be a member of `_persona_deflect_phrases["generic"]`. `_persona_limitation_reply`'s typical output is a bespoke "I'm not sure" sentence, not necessarily in the generic-deflect set, so it is **possible** (not structurally prevented) for a limitation reply to trigger E4 if `_infer_question_topic_engine()` classifies the original question text as belonging to a known engine.

**MandarinOS is not a general knowledge chatbot:** by design, all three fallbacks operate strictly within persona-adjacent topic domains (using the persona's own `voice_lines`/`discoverable_facts`/`profile` where relevant, or a generic uncertainty phrase) rather than attempting to answer arbitrary world-knowledge questions.

---

## 17. Answer-source state interactions

| State field | Read by answer generation? | Written by answer generation? | Notes |
|---|---|---|---|
| `last_counter_reply` | Yes — read into `_prev_counter_reply` at line 9872 | Yes — written unconditionally from final `_counter_reply` at line 11822 | Read/write both occur inside answer generation's own turn |
| `recent_persona_replies` | Yes — read into `_recent_persona_replies` at line 9874; consumed by E3 (§8), dedup pool (§12), and same-intent pool exclusion sets | Yes — appended with final `_counter_reply` and capped to last 3 at lines 11825–11827 | Cap (3) and extraction window (5, §8) differ |
| `last_partner_frame_text` | Yes — read by meaning/example/repeat-slower/app-question-confusion/pending-frame-commitment paths (§9) to know what to restate | No — not written by answer generation; written by frame selection | Cross-referenced fully in `docs/STATE_CONTRACT.md` |
| Mirror-topic state (`_cs_mirror_topic`, `_cs_mirror_engine`, `_cs_mirror_conf`/`mirror_confusion_count`) | Yes — read to select the mirror-confusion escalation stage (Priority 13, §9) and the F2 adjacency guard (Priority 18) | Yes — updated at lines 10323–10334 (increment on confusion, clear on non-confusion) and set when a fresh mirror answer is produced (`_new_mirror_topic`/`_new_mirror_engine`, Priority 20) | Cross-turn round-trip completeness is a `STATE_CONTRACT.md` concern; this document only states that answer generation both reads and writes this state |
| Confusion counters (`_repair_attempt_count`) | Yes — read to gate repair escalation (§9, lines 10402–10426) | Implied increment is part of the broader turn-processing logic outside the answer-source functions themselves; not asserted here beyond the read | See `docs/STATE_CONTRACT.md` for full schema |
| Place-subject context (`learner_stated_location`, `learner_memory["lives_in"]`) | Yes — read by `_place_from_question_context()` deictic resolution (§10) and by frame slot-fill logic | Not by answer-source functions themselves; written elsewhere in the turn-processing pipeline when the learner volunteers/confirms a location | See §10 for the distinction from system encyclopedic knowledge |
| Learner memory (general) | Indirectly, via `learner_memory["lives_in"]` above | No | Out of scope beyond the one field cited |
| Persona reveal tracking | Not read or written by any function traced in this document | — | No evidence found of answer-source interaction; not claimed |
| E4 local state (`current_engine` incoming, `_e4_engine_handoff` outgoing) | Yes — `_infer_question_topic_engine`/`_QUESTION_TOPIC_TO_ENGINE` decisions in §15 do not read the **incoming** `current_engine`; frame selection reads it separately | Yes — `_e4_engine_handoff` is written into `response["state_update"]["current_engine"]` at lines 11833–11835 | Full end-to-end client transport is `docs/CONVERSATION_ARCHITECTURE.md`/`docs/STATE_CONTRACT.md` scope |

This table states only whether answer generation reads/writes each field on the **current** turn; whether the field is required (and correctly supplied) on the **following** turn for full round-trip correctness is authoritatively covered by `docs/STATE_CONTRACT.md`'s consumption tables and is not re-derived here.

---

## 18. Enforced answer invariants

### Enforced invariants

* **First non-`None`/non-empty answer source wins**, subject to the five-group structure documented in §4 (a matching-but-empty Group 2 branch blocks lower Group 2 branches without producing an answer; Groups 3–5 are independent `if _counter_result is None:` gates). Verified structurally by reading the exact `if`/`elif` nesting at lines 9896–10283.
* **The final deduplicated Chinese is the text translated.** `_persona_answer_en()` is called with the post-substitution `_counter_reply` at every re-translation call site (lines 10361–10364, 10374, and the equivalent explicit-place/stale-override call sites) — never with a discarded candidate. Enforced by code structure and asserted by `TestDeduplicationEnglishSync` in `tests/test_zh_en_synchronisation.py`.
* **Direct persona answers appear in `counter_reply`, not `frame_text`.** `_direct_persona_answer()`'s result only ever flows into `_counter_result`/`_counter_reply` (§4–§5); it has no call site that writes to any frame-text-producing structure.
* **A generic deflection does not trigger E4 via the direct-persona/default branch.** Enforced by the explicit set-exclusion check at lines 10309–10310. (This enforcement is scoped to that one branch — see the caveat in §15 regarding mirror/E3 branches, which are not separately checked against the generic-deflect set because their outputs are not expected to equal those phrases.)
* **`recent_persona_replies` is updated from the final answer.** Lines 11825–11827 append `_counter_reply` (the fully-finalised value) — not any earlier candidate.
* **Current-frame selection remains separate from answer generation.** Frame selection (`chosen = None` onward, from line ~10485) executes strictly after the entire answer-source/dedup/repair-escalation sequence (lines 9896–10428) and reads different inputs (incoming `current_engine`, ladder state) — confirmed structurally by the line-number ordering.
* **Question-focus precedence protects the named place being asked about.** `_place_from_question_context()`'s documented and implemented three-level priority (§10) ensures a city immediately preceding a feature/food question marker outranks an earlier-mentioned city in the same utterance.
* **English resolution uses the final Chinese answer.** Demonstrated identically to the deduplication point above; this is the same enforced mechanism, restated for emphasis per the requested document structure.

### Intended contracts with known gaps

* **Every Chinese answer should have non-empty English.** Not enforced. §13 identifies multiple structurally-guaranteed empty-English paths (RC-EN narrowed reverse-fact branches, `_soft_persona_fallback`, many mirror/E3 topic branches, `_persona_answer_en()`'s final fallthrough). Evidence: `docs/CONVERSATION_ARCHITECTURE.md`/code comments explicitly document the RC-EN trade-off as deliberate, not accidental — this is a known, accepted gap rather than a bug, but it means the "every answer has English" contract is **not** structurally guaranteed. Representative test: `tests/test_zh_en_synchronisation.py` covers only the dedup-substitution regression, not exhaustive English coverage across all 42 direct-persona families or all mirror/E3 topics.
* **Every answer should have correct pinyin.** Not enforced. §14 shows pinyin is a curated map lookup covering only recovery/deflection phrases — the large majority of `_direct_persona_answer`, mirror-bank, and E3 answers receive no server pinyin at all. No test asserts pinyin presence for these paths; `tests/test_zh_en_synchronisation.py` (lines ~404–408) merely acknowledges a client-side fallback exists, which is outside this document's scope.
* **Substantial persona-specific content should be data-driven.** Contradicted by evidence in §5, §10, §16: `_CITY_LIKE_POOL`, `_CITY_FOOD_POOL`, `_CITY_FEATURE_POOL` (inside `_direct_persona_answer`), `_FEAT_POOL_INLINE`/`_FOOD_POOL_INLINE` (inside `_dedupe_persona_answer`), and dozens of per-branch inline Chinese fallback templates are hardcoded directly in `scripts/ui_server.py`, not in persona JSON or `content/*.json`. This is a known, extensive gap, not an isolated exception.
* **Unsupported questions should be honest and topic-aware.** Partially met: `_topic_aware_honest_fallback` exists and is tried before the harder `_persona_limitation_reply` fallback (§16), but `_soft_persona_fallback` (tried first) can return a plausible-sounding generic answer for a question the persona cannot actually verify, which is a softer standard than "honest." Representative test: `tests/test_conversation_first_wave.py` covers `_topic_aware_honest_fallback` tuple-shape and topic-relevance behaviour; `tests/test_transcript_reverse_questions.py` covers absence of the literal 电脑角色 phrase in the normal path. No test enumerates all `_soft_persona_fallback` branches for factual honesty.
* **Mirror-confusion escalation should work across turns.** Known incomplete per §9 and the already-approved `docs/CONVERSATION_ARCHITECTURE.md`/`docs/STATE_CONTRACT.md` findings — the server-side staged functions exist and are individually test-covered (`tests/test_stale_counter_reply_loop.py`), but full cross-turn client round-trip of the relevant counters is not established with the same rigor as the E4 fix.
* **No answer source should contain duplicated translation logic.** Contradicted: §7 and §12 identify at least two independent city-content pool pairs (`_CITY_FOOD_POOL`/`_FOOD_POOL_INLINE`, `_CITY_FEATURE_POOL`/`_FEAT_POOL_INLINE`) and two independent location-brief sources (`_CITY_LOCATION_BRIEF` vs. inline templates in `_direct_persona_answer`) that can diverge in content since they are maintained as separate literals.
* **Answer pools should not cross topics during deduplication.** Met for the specific place-feature/place-food repick paths in `_dedupe_persona_answer` (§12), which are gated by `_is_place_feature_question`/`_is_place_food_question` before selecting the matching pool — but the fallback (`_persona_deflect("generic", cand)`) when neither guard matches is a cross-topic generic deflection by design, which is an accepted limitation rather than a violation, since no attempt is made to find a same-topic pool for non-place answer types at all.

---

## 19. Extension rules

| Adding a... | Priority position | Trigger exclusions | Chinese source | English source | Pinyin | Deduplication | Working memory | E4 eligibility | State interactions | Tests | Documentation |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Direct persona-answer intent | Insert into `_direct_persona_answer`'s flat sequence (§5) at the correct precedence position — check for overlap with existing patterns, especially longer/more-specific-must-precede-shorter rules already documented | Must not match any higher-priority family's pattern; check §5's ordering-comment list for the nearest analogous precedence rule | Prefer `discoverable_facts`/`voice_lines`/`profile` field; avoid a new inline pool unless the fact is genuinely encyclopedic (city-level) rather than persona-specific | Add the fact to `discoverable_facts_en`/`voice_lines_en` so stage 2/4 of `_persona_answer_en()` (§13) can resolve it without a new intent branch | Only if the new fallback text should ever equal a recovery-phrase-bank entry; otherwise accept no pinyin (§14) | Add the new fact key to §12's same-intent pool tables only if it is a place-feature/place-food fact; otherwise it falls to the generic deflect fallback by default | None required unless the fact should also be extractable by E3 (§8) — that requires a separate addition to `_extract_persona_facts_from_recent`/`_answer_from_working_memory` | Decide whether the intent should map through `_infer_question_topic_engine()` (likely automatic if the question text matches an existing engine-classification pattern) or needs a new entry | None unless the fact should also be readable from `recent_persona_replies` via E3 | Add/extend a test exercising the new pattern and its precedence relative to neighbours | Add a new row to §5's table in this document |
| New answer source (new function) | Decide which of the five structural groups (§4) it belongs in and its exact position relative to existing sources — document precedence explicitly, mirroring the existing inline comments | Must state, in code, what higher-priority sources it must not fire after | State whether it returns `(zh, en)`, `zh`-only, or sets a flag only — flag-only sources must not be documented as answer sources (§4's Priority 16 caution) | State the English resolution mechanism explicitly; do not assume `_persona_answer_en()` applies unless the source is routed through one of its actual call sites | State whether it should ever populate `_persona_deflect_pinyin_map` | Decide explicitly whether §12's exact-match dedup guard should apply (it will, automatically, if the output happens to repeat — but same-intent repick will not unless added) | Decide whether this source should read `recent_persona_replies` or write anything new | Decide explicitly whether `user_asked_question` should gate it, and whether it should be added to `_QUESTION_TOPIC_TO_ENGINE` or rely on `_infer_question_topic_engine()` | Enumerate every state field read/written per §17's table format | Add unit test for the function and an ordering/precedence test proving it does not fire ahead of higher-priority sources | Add a new row to §4's table and, if relevant, new subsections |
| New persona fact | n/a (data-only) | n/a | Add to `profile`/`discoverable_facts`/`voice_lines`/`distance_profile` per the schema patterns in §5/§6 | Add matching `discoverable_facts_en`/`voice_lines_en` entry | n/a | n/a | Consider whether E3's keyword extraction should also recognise it | n/a | n/a | Add persona-JSON-schema test coverage if one exists | Update §6's precedence description if the new fact competes with an existing source |
| New mirror topic | Add record to `content/mirror_questions.json` with `zh`/`topic`/optional `paraphrases` | Must not collide (exact or fuzzy) with an existing question's `zh`/paraphrase set | `_mirror_persona_stub()` must handle the new `topic` key | Add the paired `*_en` field(s) the stub function will read for that topic, or accept `""` | Not applicable via current mechanism (§14) — mirror pinyin is not read from `mirror_questions.json`'s `py` field | Not automatically; only place-feature/place-food dedup repick exists (§12) | Consider whether the topic should also be recognisable by `_extract_persona_facts_from_recent`/`_answer_from_working_memory` | Add the new `topic` to `_QUESTION_TOPIC_TO_ENGINE` if E4 handoff should fire for it | None beyond mirror-topic state already tracked | Add a mirror-match test and, if escalation-relevant, a confusion-ladder test | Update §7's mirror-bank description if the mechanism changes |
| Reverse-fact category | Add to `_detect_reverse_fact_intent`'s pattern list and `_reverse_fact_answer`/`_reverse_fact_answer_en` | Must not collide with an existing intent's patterns | `_reverse_fact_answer` remains dead code in production unless a new call site is added — clarify whether the new category is meant to be production-reachable | Apply the RC-EN invariant (§7): if the same intent can be triggered by structurally different questions, return `""` rather than a possibly-wrong gloss | n/a unless routed through the deflect pinyin map | n/a directly; only relevant if the Chinese answer is also produced by `_direct_persona_answer` and can repeat | n/a | `_persona_answer_en()`'s stage 3 will pick this up automatically once `intent` is passed by a caller | None beyond existing reverse-fact scope | Add a unit test analogous to `tests/test_regression_place_travel_reverse.py` | Update §7's intent table |
| Recovery reply | Add function + trigger condition in the appropriate priority slot in Group 1 or Group 2 (§4/§9) | Must state explicit precedence relative to the existing recovery/confusion/repair ladder | Prefer `content/recovery_phrases.json` phrase-bank sourcing (per AP-4-style no-inline-Chinese discipline referenced by existing tests) over inline strings | Add `text_en` to the phrase-bank entry so `_en_for_counter_reply`/`_persona_deflect_en` can resolve it automatically | Add `pinyin` to the phrase-bank entry if desired | Recovery replies are already subject to post-hoc dedup if they repeat (§4's "Yes (post-hoc)" column) | n/a | Recovery replies are structurally excluded from E4 only via the `user_asked_question` master gate — verify the new trigger condition does not accidentally allow `user_asked_question` to be true | Confirm whether the new reply should set `_confusion_about_app_q` or similar flags read later in frame-text override logic | Add a trigger-detection test and a phrase-bank-sourcing test (no inline Chinese) | Add a row to §9's table |
| Place-feature answer | Add to `_CITY_FEATURE_POOL` (production path) and, if same-intent dedup reselection should also offer it, `_FEAT_POOL_INLINE` (§10/§12) — these are separate literals and must both be updated to stay consistent | Must not collide with an existing city key in either pool | Pool string itself | Per §13's RC-EN convention, place-feature English is typically `""` — decide explicitly whether to add a paired English string somewhere reachable by `_persona_answer_en()` | n/a via current mechanism | Already covered automatically if `_is_place_feature_question()` matches | n/a | Falls under the direct-persona E4 branch automatically if reached via `_direct_persona_answer` | None new | Add a same-intent-dedup test if `_FEAT_POOL_INLINE` was also updated | Update §5 family #29 and §10's pool description |
| Phrase-bank entry | Add to `content/recovery_phrases.json` under the correct `use` key | Must not unintentionally match an existing trigger's marker set | `text`/`zh` field | `text_en` field | `pinyin` field | Automatic via existing `_persona_deflect`/pool-picker mechanisms if the `use` key is one already consumed by those pickers | n/a | n/a beyond whatever the consuming trigger already implies | n/a | Add a phrase-bank loading/sourcing test | None unless it introduces a new `use` key, in which case document it in the relevant section |
| English mapping | Add to the relevant `*_en` field (`discoverable_facts_en`, `voice_lines_en`, `_persona_deflect_en_map` source, or `_reverse_fact_answer_en`) | Must respect the RC-EN invariant if the mapping is intent-keyed rather than fact-keyed | n/a | The mapping itself | n/a | n/a | n/a | n/a | n/a | Add/extend `tests/test_zh_en_synchronisation.py`-style coverage | Update §13's stage table if a new resolution stage is introduced |
| Pinyin exception | Add to `content/recovery_phrases.json`'s `pinyin` field for the relevant phrase | n/a | n/a | n/a | The mapping itself, consumed automatically by `_resolve_counter_reply_pinyin()` | n/a | n/a | n/a | n/a | Add a pinyin-resolution test | Update §14 only if the mechanism itself changes |

---

## 20. Known risks

* **One very large priority chain.** The combined answer-source logic spans roughly 500 lines (9896–10428) across five structurally distinct groupings (§4), making full-chain reasoning difficult without the ordered inventory in this document. *Observed* (directly read from code), not inferred.
* **Overlapping pattern matches.** Multiple `_direct_persona_answer` intent families use broad substring checks (e.g. `"喜欢"` appears as a discriminator in families #13, #14, #23, #27, #35) that rely on precise ordering to avoid misclassification; the ordering-comment list in §5 confirms the authors were aware of and actively managing this risk, but no automated test enumerates all 42×41 pairwise ordering interactions. *Observed* ordering-sensitivity; *inferred* (not directly tested) that all pairwise interactions are safe.
* **Duplicated facts across profile, voice lines, discoverable facts, and inline maps.** §6 and §10 document at least four concrete duplication points (city-food, city-feature, city-location-brief vs. inline templates, and work info spread across three fields with per-family precedence). *Observed.*
* **Inline Chinese answer content.** §5's fallback-string table and §10's pool definitions show a large volume of hardcoded Chinese directly in `scripts/ui_server.py`, contrary to the "no inline Chinese strings" discipline referenced in this repository's architecture rules for *partner-side* content elsewhere. *Observed* — whether this specific inline content is in-scope for that rule is not adjudicated here; it is recorded as a risk for future review.
* **Incomplete English mappings.** §13 and §18 document multiple structurally-empty-English paths. *Observed.*
* **Dynamic replies that bypass data files.** The F2 why-like adjacency guard (§4 Priority 18) constructs its answer inline from a truncated `voice_lines` slice (`_wl[:30].rstrip(...)`) rather than a dedicated data field, meaning the answer's exact wording is sensitive to `voice_lines` content length and punctuation in a way not true of the other 20+ priorities. *Observed.*
* **Stale-answer pool exhaustion.** §12 shows `_dedupe_persona_answer`'s Step 1 (same-intent repick) can itself be exhausted (all pool entries already in the recent set), forcing Step 2's generic deflection regardless of whether a genuinely new fact could have been supplied by a different mechanism (e.g. `_direct_persona_answer` re-invocation, which is not attempted here). *Observed.*
* **Source-order changes altering unrelated behaviour.** Because Group 2 (§4) is a single flat `elif` chain where a matching-but-empty branch blocks all lower branches, reordering or adding a new condition anywhere in lines 9942–10182 risks silently suppressing an existing lower-priority answer source even when the new/reordered condition itself produces no answer. *Observed* as a structural property of the code, not a specific historical incident.
* **Answer sources returning different tuple shapes or assumptions.** §4's branch-type classification shows most sources return `(zh, en)`, but `_direct_persona_answer` itself returns `zh`-only (str or `None`), requiring every call site to independently wrap it and call `_persona_answer_en()` — a pattern repeated at four distinct call sites (10021–10024, 10075–10078, 5003, and inside `_dedupe_persona_answer`'s English-regeneration path) rather than centralised once. *Observed.*
* **Tests that prove only individual functions rather than full priority ordering.** Per the "representative tests" columns throughout §4 and §9, most cited tests exercise a single function or a single trigger condition; no single test file is observed to assert the complete 22-stage ordering end-to-end (the priority-chain trace underlying this document required direct code reading, not a single authoritative test). *Observed* as an absence, not a specific defect.

---

## 21. Regression diagnosis guide

* **Learner question receives no answer:** confirm `last_turn_was_answer` was true for the turn and `user_asked_question`/`_is_direct_persona_question` classification succeeded; check whether the question text matched a Group 2 (§4) trigger with an *empty* callee result (e.g. `_is_meaning` true but `last_partner_frame_text` empty) — this blocks all lower branches including mirror/direct/E3 without producing an answer, which is a legitimate but easily-mistaken-for-a-bug outcome.
* **Wrong persona fact returned:** check `_direct_persona_answer`'s family-order table (§5) for a higher-priority family whose pattern unexpectedly matched the question text before the intended family's pattern was reached.
* **Wrong place answered:** check `_place_from_question_context()`'s three-level priority (§10) — confirm which city preceded the question marker per `_CITY_BEFORE_QUESTION_MARKER_RE`, and whether the intended city is actually a key in `_CITY_LOCATION_BRIEF`/`_CITY_FEATURE_POOL`/`_CITY_FOOD_POOL`.
* **Stale answer repeats:** confirm the repeated string is exactly present (after `_strip_discourse_prefix` normalisation) in `_dedup_pool` (§12); if the repick still returns the same value, check whether the relevant same-intent pool (`_FEAT_POOL_INLINE`/`_FOOD_POOL_INLINE`) is exhausted relative to `_recent_set`, forcing the generic-deflection fallback.
* **Chinese and English disagree:** confirm which of §13's five resolution stages produced the English, and whether the Chinese was subsequently changed by dedup/repair-escalation (§12/§9) **after** that English was computed — if so, re-verify the call sequence at lines 10348–10426 to confirm English was regenerated from the *final* Chinese, not the pre-substitution candidate.
* **English is blank:** check the specific answer-source class against §13's "legitimately empty" list before assuming a defect — many mirror/E3/reverse-fact branches are deliberately `""` per the RC-EN invariant (§7).
* **Pinyin does not match Chinese:** confirm whether `counter_reply_pinyin` was populated at all — per §14, only exact matches (or `我呢，`-stripped matches) against `_persona_deflect_pinyin_map` produce pinyin; any other answer source is expected to have empty server-side pinyin, which is normal, not a mismatch.
* **Recovery reply overrides a direct answer:** check Group 1 (§4 Priorities 1–5) and the repair-escalation override (§9, lines 10402–10426) — both can supersede an otherwise-correct direct-persona answer; confirm whether the recovery trigger condition (frustration/disclosure/challenge/confirmed-re-ask/confusion-signal-with-repair-count) was legitimately met.
* **Direct answer appears but E4 does not fire:** confirm `user_asked_question` was true, `_counter_result[0]` is not a member of `_persona_deflect_phrases["generic"]` (§15), and `_infer_question_topic_engine(_last_text_for_counter)` actually classifies the question into a known engine — an unrecognised question phrasing yields `None` with no further attempt.
* **E4 fires from a generic response:** should not occur via the direct-persona branch (explicit exclusion, §15) — if observed, check whether the mirror or E3 branch produced the answer instead, since those two branches are **not** subject to the generic-deflection exclusion check.
* **Wrong answer source wins:** re-derive the exact five-group structure and priority order from §4; confirm which group and which numbered priority the winning source belongs to, and whether a higher-numbered-but-actually-higher-priority source (per the group structure, not raw line order) was bypassed.
* **Unsupported question produces an overconfident answer:** check whether `_soft_persona_fallback` (§16) — the first-tried, least-strict of the three fallbacks — produced a plausible-sounding but unverifiable answer; this is a known partial gap (§18), not necessarily a new defect.
* **Working-memory answer uses an unrelated recent fact:** check `_answer_from_working_memory`'s documented sourcing priority (travel_fav > travel_visited > food_spicy > hometown > city_now > family, §8) and confirm which category's keyword pattern in the current question text matched first — a higher-priority category can pre-empt a lower-priority but more contextually relevant one if both patterns happen to be present in the question text.

---

## 22. Related documents

* [`docs/CONVERSATION_ARCHITECTURE.md`](CONVERSATION_ARCHITECTURE.md) — overall turn lifecycle, frame selection, E4 end-to-end transport contract, invariants.
* [`docs/STATE_CONTRACT.md`](STATE_CONTRACT.md) — authoritative `conversation_state`/`state_update` field schema and consumption status.
* `docs/ASR_PIPELINE.md` — *not yet created in this repository; referenced for future ASR-normalisation scope only.*
* `docs/ARCHITECTURE.md` — *not present in this repository under this exact name; see `AI_CONTEXT.md` at the repository root for the current orientation map.*
* `docs/TEST_STRATEGY.md` — *not present in this repository under this exact name.*
* `docs/CHANGE_CHECKLIST.md` — *not present in this repository under this exact name.*
* `docs/ARCHITECTURAL_DECISIONS.md` — *not present in this repository under this exact name.*
* `docs/PRODUCT_PHILOSOPHY.md` — *not present in this repository under this exact name.*
* Repository-root `AGENTS.md` — *not present in this repository under this exact name; see repository-root `AI_CONTEXT.md` and `.cursor/rules/*.mdc` for equivalent standing guidance.*

---

## 23. Traceability appendix

| Answer area | Producer | Primary data source | Finalisation/translation | State interactions | Representative tests |
|---|---|---|---|---|---|
| User-initiative repair (frustration/disclosure/challenge) | `_frustration_repair_reply`, `_disclosure_empathy_reply`, `_persona_challenge_reply` | `content/recovery_phrases.json` | Tuple's own `en`; pinyin via `_persona_deflect_pinyin_map` if phrase matches | Suppresses `reaction_prefix_text`; recent-replies write | `tests/test_regression_surgical_transcript.py`, `tests/test_conversation_fixes.py` |
| Responsive food / travel intent | `_food_responsive_reply`, `_travel_intent_followup` | Extracted text / `content/recovery_phrases.json` | Tuple's own `en` | May feed `force_travel_bridge` on next frame | `tests/test_open_world_food_and_location_fixes.py`, `tests/test_regression_place_travel_reverse.py` |
| Explicit place-topic / stale-override direct persona | `_direct_persona_answer` via §4 Priorities 7/12 | `profile`/`discoverable_facts`/`voice_lines`/inline pools | `_persona_answer_en` | E4-eligible; dedup-eligible | `tests/test_contextual_place_asr_repair.py`, `tests/test_stale_answer_loop_regression.py` |
| Meaning/example/repeat-slower/lexical recovery | `_meaning_recovery_reply`, `_clarify_app_question`, `_lexical_definition_reply` | `last_partner_frame_text` / inline tables | Tuple's own `en` | Sets `_confusion_about_app_q` | `tests/test_meaning_recovery.py`, `tests/test_golden_regression.py` |
| Mirror confusion escalation ladder | `_mirror_restate_naturally`, `_mirror_persona_stub_simple`, `_confusion_recovery_reply` | Prior mirror answer / persona facts / inline pool | Tuple's own `en` | Reads/writes mirror-confusion counters | `tests/test_stale_counter_reply_loop.py` |
| Pending-frame commitment / app-question confusion | `_clarify_app_question` | `last_partner_frame_text` | Tuple's own `en` | Same-engine frame-selection guard | `tests/test_interaction_regression.py`, `tests/test_golden_conversation_scenarios.py` |
| Noisy-location clarification | *(flag-only; frame-text override, not this document's producer set)* | n/a | n/a | `_confusion_about_app_q`, `_noisy_location_clarify` flags | `tests/test_golden_conversation_scenarios.py::test_gs5_noisy_location_continues` |
| F2 why-like adjacency | Inline construction | `voice_lines[engine]` | Inline (English often empty) | E4-eligible via default branch | *(no dedicated file identified)* |
| E3 working memory | `_extract_persona_facts_from_recent`, `_answer_from_working_memory` | `recent_persona_replies` | Tuple's own `en` (often empty) | Sets `_counter_is_working_memory`; E4-eligible | *(no dedicated file identified — direct code citations in §8)* |
| Mirror bank | `_find_mirror_answer`, `_mirror_persona_stub` | `content/mirror_questions.json` + persona facts | `_mirror_persona_stub`'s own `en` | Sets `_counter_is_new_mirror`; E4-eligible via topic map | `tests/test_blue_discovery_routing.py` |
| General prefix / unsupported fallback | `_answer_user_question_prefix`, `_soft_persona_fallback`, `_topic_aware_honest_fallback`, `_persona_limitation_reply` | Varies; persona facts where available | Varies; limitation reply has fixed literal `en` | E4-eligible (not specially excluded) | `tests/test_learner_led_followup_questions.py`, `tests/test_conversation_first_wave.py`, `tests/test_transcript_reverse_questions.py` |
| Deduplication / substitution | `_dedupe_persona_answer` | `_FEAT_POOL_INLINE`/`_FOOD_POOL_INLINE`; `_persona_deflect("generic")` | Re-invokes `_persona_answer_en` on final Chinese | Reads `_prev_counter_reply`/`recent_persona_replies`; writes final `_counter_reply` | `tests/test_zh_en_synchronisation.py`, `tests/test_stale_answer_loop_regression.py` |
| English resolution | `_persona_answer_en`, `_en_for_counter_reply`, `_voice_line_en_for_zh`, `_reverse_fact_answer_en` | Deflect map / `voice_lines_en` / intent lookup / `discoverable_facts_en` | Five-stage precedence (§13) | n/a beyond translation | `tests/test_zh_en_synchronisation.py` |
| Pinyin resolution | `_resolve_counter_reply_pinyin` | `content/recovery_phrases.json` `pinyin` field | Exact-match lookup only | n/a | *(map-lookup mechanism; no dedicated pinyin-specific test file identified beyond synchronisation acknowledgement in `tests/test_zh_en_synchronisation.py`)* |
| E4 eligibility | Inline computation at lines 10296–10313 | `_QUESTION_TOPIC_TO_ENGINE` / `_infer_question_topic_engine` | n/a | Writes `state_update.current_engine` | `tests/test_e4_topic_handoff.py` |

**Baseline commit:** `3be0315b2c9f7316b03ac2183a887f602ae9a297`
**Baseline tag:** `architecture-baseline-2026-07-12-r2`
**Source documentation branch:** `docs/architecture-v1`
**Document status:** Draft v1
**Last verified date:** 2026-07-12
