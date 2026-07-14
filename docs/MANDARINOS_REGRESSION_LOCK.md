<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class B: Current supporting guidance**
>
> - **Current use:** Supporting register of protected behaviours and regression concerns.
> - **May guide current implementation:** Yes, within its verified narrow scope.
> - **Current authority:** `docs/TEST_STRATEGY.md`, `docs/CHANGE_CHECKLIST.md`, and the applicable behavioural contract.
> - **Principal caution:** “LOCK” does not make this document behavioural authority. Every test or regression claim must be interpreted according to the evidence categories in `docs/TEST_STRATEGY.md`.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS — Regression Lock

Behaviours that must not regress. Each entry records **why it exists** and which test in `tests/test_golden_regression.py` guards it.

Run the suite after any selector, ASR, or recovery-phrase change:

```bash
# Static checks only (no server needed):
python tests/test_golden_regression.py --static-only

# Full suite (server must be running):
python tests/test_golden_regression.py
```

---

## T1 — Repair phrases never use learner-owned pause words

| | |
|---|---|
| **Behaviour** | The app must never respond with 等一下 / 等一等 / 等等 when it fails to understand the learner. These are learner pause phrases, not app repair signals. |
| **Why** | Using 等一下 as a repair response models the wrong conversational behaviour and confuses the learner about who is asking for time. |
| **Root fix** | `content/recovery_phrases.json` marks deng_yi_xia / wo_xiang_xiang with `"speaker": "learner"`. The runtime artifact is rebuilt by `tools/build_runtime_artifacts.py`. A hardcoded guard in `getRecoveryPhraseForNotUnderstood` (app.js) blocks these phrases regardless of runtime data state. |
| **Test** | `test_repair_phrases_no_learner_pauses()` — static scan of `recovery_phrases.runtime.json` |

---

## T2 — Required frames exist

| | |
|---|---|
| **Behaviour** | All conversation frames introduced by recent improvements must exist in `p2_frames.json`. |
| **Why** | If a selector constant references a frame ID that does not exist, the server returns a null frame and the conversation breaks silently. |
| **Guarded frames** | `f_travel_why_want_go`, `f_travel_narrow_city`, `f_travel_dest_generic_clarify`, `f_work_retire_clarify`, `f_work_yn` |
| **Test** | `test_required_frames_exist()` — static scan of `p2_frames.json` |

---

## T3 — Depth-anchor constants are wired

| | |
|---|---|
| **Behaviour** | `_DEPTH_ANCHOR_FRAMES`, `_DEPTH_ANCHOR_SPECIFICITY`, `_DESTINATION_QUESTION_FRAMES`, and `_TRAVEL_ASR_NEAR_MATCHES` must be present in `ui_server.py`. |
| **Why** | These constants are the backbone of the three-tier travel depth rule and destination validation. If they are accidentally deleted or renamed, the whole chain silently reverts to the old (bridge-too-early) behaviour. |
| **Test** | `test_depth_anchor_completeness()` — static grep of `ui_server.py` |

---

## T4 — Food answers are echoed whole, not collapsed

| | |
|---|---|
| **Behaviour** | `USER: 羊肉不错` → echo = `哦，羊肉不错！`, not `哦，不错！` |
| **Why** | ASR produces multi-word food phrases. A partial match to the word tile "不错" used to collapse the echo and transcript display, losing the dish name and reducing learner confidence. |
| **Root fix** | `matchTranscriptToOption` in app.js: when raw transcript is longer than the matched option, the full transcript is used for display, TTS, and echo. `semanticSoftMatch` for `_FOOD_FRAMES` accepts food nouns explicitly. |
| **Test** | `test_food_echo_not_collapsed()` |

---

## T5 — Broad travel answer stays in travel/place engine

| | |
|---|---|
| **Behaviour** | `APP: 你会去别的地方吗?  USER: 我想去中国` → next frame is in travel/place domain, NOT family |
| **Why** | `f_place_travel` is a broad-intent frame. Before the fix, a country name in the answer could trigger the TRAVEL slot and `force_travel_bridge`, unexpectedly jumping to a family question. |
| **Root fix** | `f_place_travel` removed from `_DEPTH_ANCHOR_FRAMES`. Travel soft-matching scoped to explicit travel frames. |
| **Test** | `test_travel_broad_stays_in_engine()` |

---

## T6 — Country-level answer triggers city narrowing

| | |
|---|---|
| **Behaviour** | `APP: 你最想去哪里?  USER: 我想去中国` → `APP: 你想去哪个城市？` |
| **Why** | "中国" is a valid answer but too broad to follow up with "why do you want to go there?" — that follow-up works much better for provinces and cities. The three-tier specificity model routes country-level answers through a narrowing step first. |
| **Root fix** | `_TRAVEL_COUNTRIES` set + `_is_country_level_travel_answer` detector; `_DEPTH_NARROWING_FRAMES["f_want_go_where"]` maps to `f_travel_narrow_city`. |
| **Test** | `test_travel_country_to_narrow()` |

---

## T7 — City/province answer after narrowing triggers depth

| | |
|---|---|
| **Behaviour** | `APP: 你想去哪个城市?  USER: 北京` → `APP: 你为什么想去那里？` |
| **Why** | Once a concrete destination is named, a depth follow-up is natural. `f_travel_narrow_city` is in `_DEPTH_ANCHOR_FRAMES` so its answers are checked against `_TRAVEL_SUBREGIONS`. |
| **Root fix** | `f_travel_narrow_city` added to `_DEPTH_ANCHOR_FRAMES` and `_DEPTH_ANCHOR_SPECIFICITY`. |
| **Test** | `test_travel_city_to_depth()` |

---

## T8 — Province answer directly to destination question triggers depth

| | |
|---|---|
| **Behaviour** | `APP: 你最想去哪里?  USER: 我最想去江苏` → `APP: 你为什么想去那里？` |
| **Why** | Province/city names are depth-ready destinations (Tier 1). The depth rule must fire before any bridge. |
| **Root fix** | `_TRAVEL_SUBREGIONS` contains provinces and cities; `_is_depth_ready_travel_answer` gates `force_depth_followup_frame`. |
| **Test** | `test_travel_province_to_depth()` |

---

## T9 — Garbled ASR destination never echoed or bridged

| | |
|---|---|
| **Behaviour** | `APP: 你最想去哪里?  USER/ASR: 我就想去刚吃` → `APP: 你是说甘肃吗？` — never `哦，我就想去刚吃！你跟谁一起住？` |
| **Why** | "刚吃" is an ASR misrecognition of "甘肃". Echoing it as a destination is wrong and confusing. Bridging to family after an invalid destination is a gross flow error. |
| **Root fix** | `_TRAVEL_ASR_NEAR_MATCHES`, `_detect_travel_asr_near_match()`, `_invalid_dest_answer` flag, TRAVEL echo guard, and `f_travel_dest_generic_clarify` with dynamic `frame_text` injection in the response builder. |
| **Test** | `test_travel_asr_garble_clarify()` — checks frame_id, frame_text, absence of "刚吃", no family bridge |

---

## T10 — Retirement answer suppresses current-job follow-ups

| | |
|---|---|
| **Behaviour** | `APP: 你做什么工作?  USER: 我退休了` → retirement-safe follow-up; never `你在哪个公司上班？` |
| **Why** | Asking a retired person about their current employer is a conversational error that breaks rapport. |
| **Root fix** | `_RETIRED_OR_NONWORKING_SIGNALS` list; `_user_is_retired` flag routes to `p2_wk_retired`. |
| **Test** | `test_work_retirement_safe()` |

---

## T11 — ASR retirement near-miss routes to clarification

| | |
|---|---|
| **Behaviour** | `APP: 你做什么工作?  USER/ASR: 我推销了` → `APP: 你是说你退休了吗？` — never a company follow-up |
| **Why** | "推销" (sales/promotion) and "退休" (retire) are ASR near-homophones. Treating a near-homophone of "retire" as a current job description leads to absurd follow-ups. |
| **Root fix** | `_RETIRE_NEAR_HOMOPHONES` list; `_needs_retire_clarify` flag routes to `f_work_retire_clarify`. |
| **Test** | `test_work_asr_retire_near_miss()` |

---

## T12 — Family member answers accepted (live-with)

| | |
|---|---|
| **Behaviour** | `APP: 你跟谁一起住?  USER: 爸爸妈妈老婆` → accepted; no crash, no wrong-engine jump |
| **Why** | Multi-word family-member strings (no subject pronoun, no verb) were being rejected by overly strict option matching. |
| **Root fix** | `f_live_with_who` added to `isOpenEndedFrame`; family-member keywords added to `semanticSoftMatch` for `_FAMILY_MEMBER_FRAMES`. |
| **Test** | `test_family_live_with_acceptance()` |

---

## T13 — Closest-person answer triggers depth follow-up

| | |
|---|---|
| **Behaviour** | `APP: 你和家里谁最亲近?  USER: 我老婆` → `APP: 你们最喜欢一起做什么？` (same-engine depth) |
| **Why** | `f_probe_family_closest` is a depth anchor. A named family member is a specific entity (Tier 1). The depth rule should fire before bridging. |
| **Root fix** | `f_probe_family_closest` in `_DEPTH_ANCHOR_FRAMES`; `_is_specific_family_entity` detector in `_DEPTH_ANCHOR_SPECIFICITY`. |
| **Test** | `test_family_closest_acceptance()` |

---

## T14 — Family activity answers accepted

| | |
|---|---|
| **Behaviour** | `APP: 你最喜欢和家人一起做什么?  USER: 吃饭` → accepted; no crash |
| **Why** | Short activity words ("吃饭", "散步") have no match in option tiles and were being rejected as empty/nonsense answers. |
| **Root fix** | `p2_fa_activity` added to `isOpenEndedFrame`; `_FAMILY_ACTIVITY_FRAMES` match accepts any 2+ Chinese chars as a valid activity answer. |
| **Test** | `test_family_activity_acceptance()` |

---

---

## T15 — Translation surfaces use learner-natural vocabulary

| | |
|---|---|
| **Behaviour** | Translate button (EN→ZH) and transcript gloss (ZH→EN) must not output formal/written Chinese when spoken equivalents are more natural. Example: "I am closest to my wife." must produce 我跟我老婆最亲近。, never 我离妻子最近。 |
| **Why** | Formal vocabulary (妻子, 父亲, 离…最近) misleads learners and models the wrong register. MandarinOS teaches spoken Mandarin. |
| **Root fix** | `naturalizeZhTranslation(zh, sourceEn)` in `app.js` — applied to every Translate button output. Vocabulary map: 妻子→老婆, 丈夫→老公, 父亲→爸爸, 母亲→妈妈, 父母→爸爸妈妈. Structural fix: "离 X 最近" → "跟 X 最亲近" when English source implies emotional closeness. `_naturalize_en_gloss(en)` in `ui_server.py` — applied to every `/api/gloss` ZH→EN output. |
| **Test** | `test_translation_naturalizer()` — static scan of `app.js` and `ui_server.py` |

---

## Quick reference: never-regress list

| Never do this | Locked by |
|---|---|
| App says 等一下 / 等一等 / 等等 | T1 |
| Echo food answer as just 不错 when full phrase was spoken | T4 |
| Bridge from travel frame to family after a garbled destination | T5, T9 |
| Ask 你在哪个公司上班？ after 我退休了 | T10 |
| Treat 我推销了 as a job title after a work question | T11 |
| Reject 爸爸妈妈老婆 as a live-with answer | T12 |
| Reject 吃饭 as a family-activity answer | T14 |
| Translate button outputs 妻子/父亲/离…最近 | T15 |
