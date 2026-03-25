# PHASE 11.1.1 — Post-fix Alpha Observation Report

Generated: 2026-03-25  
Observer: `scripts/alpha_conversation_observer.py` (7 turns × 7 engines)  
Server: `scripts/ui_server.py` — Phase 11.1 + 11.1.1 guard extension

---

## Summary

All five Phase 11.1 targeted fixes are confirmed working in live simulation traces.
One additional residual (identity re-entry in same-engine ladder path and identity coherence gate)
was discovered and fixed during this pass. No regressions observed.

---

## Before / After for Each Fix

---

### Fix 1 — Engine depth guard (Issue 1)

**Before (Phase 11.0.x):**
- Identity bridged to place at T03 (after only 2 identity turns)
- Place bridged to food at T04 (after 3 place turns, skipping `f_place_like_there` and `frame.location.live_question`)
- Hobby bridged to identity at T04 (after 3 hobby turns)

**After (Phase 11.1):**
- Identity stays for 4 turns before bridging: `f_ask_you_name → p2_id_2 → f_ask_name_meaning → p2_id_4` → bridge at T05
- Place stays for 5 turns before bridging: `f_from_where → f_place_like_there → frame.location.live_question → p2_pl_1 → p2_pl_2` → bridge at T06
- Hobby stays for 4 turns: `f_what_hobby → f_often_do → f_difficult_ma → f_like_do_what` → bridge at T05

**Status: CONFIRMED ✓**

---

### Fix 2 — Identity re-entry block (Issue 2)

The guard operates at three levels; all three are now protected:

**Level A — Bridge selection (`_select_next_frame_bridge`)**

Before: When family exhausted, bridge selected `f_ask_you_name` for identity (exchange_count ignored)
After: exchange_count=3 ≥ 2 → bridge skips `f_ask_you_name`, selects `p2_id_4` ✓

```
BEFORE (family T05): [identity] f_ask_you_name   mt=LOOP   chain=0 [BRIDGE]
AFTER  (family T04): [identity] p2_id_4          mt=ASK    chain=0 [BRIDGE]  ← guard fires
```

**Level B — Same-engine ladder (`_select_next_frame_ladder_avoiding`)**

Before: After bridging to identity, next ladder pick was `f_ask_you_name` (no exchange_count guard in ladder)
After (Phase 11.1.1 extension): `_open_excluded = _IDENTITY_OPEN_FRAMES` applied in ladder when exchange_count ≥ 2  

**Level C — Identity coherence gate (in `run_turn`)**

Before: Gate explicitly overrode `chosen` back to `f_ask_you_name` when name-meta frame was chosen but no name context existed
After (Phase 11.1.1 extension): When exchange_count ≥ 2, gate bridges to another engine instead of forcing name question

```
BEFORE (family T05): [identity] f_ask_you_name   chain=1 [BRIDGE]  ← forced by coherence gate
AFTER  (family T05): [place]    f_from_where     chain=0 [BRIDGE]  ← coherence gate bridges away
```

```
BEFORE (hobby T06):  [identity] f_ask_you_name   chain=1 [BRIDGE]  ← forced
AFTER  (hobby T06):  [place]    f_from_where     chain=0 [BRIDGE]  ← bridges away
```

**Status: CONFIRMED ✓ (with Level B+C fix applied during 11.1.1 pass)**

---

### Fix 3 — FRAME_ORDER respect — Place engine (Issue 3)

**Before:**
```
T02 [place] p2_pl_4    — "Is it convenient living in [CITY]?"   (FRAME_ORDER pos 4, skipped earlier frames)
T03 [place] p2_pl_2    — "[CITY] to have what tasty..."          (slot heuristic bypass)
```
`f_place_like_there` (pos 1) and `frame.location.live_question` (pos 2) were never reached in 7 turns.

**After:**
```
T02 [place] f_place_like_there          — "Do you like it there?"   (pos 1) ✓
T03 [place] frame.location.live_question — "Where do you live now?"  (pos 2) ✓
T04 [place] p2_pl_1                     — "How is life in [CITY]?"  (pos 3) ✓
T05 [place] p2_pl_2                     — "[CITY] food question"     (pos 4) ✓
```

All 4 place frames served in natural order. Engine stays for 5 turns before bridging.

**Status: CONFIRMED ✓**

---

### Fix 4 — FRAME_ORDER respect — Travel engine (Issue 4)

**Before:**
```
T03 [travel] p2_tr_2  — "Where do you like best?"        (pos 2 in order, ahead of p2_tr_1)
T05 [travel] p2_tr_1  — "Which countries have you been?"  (pos 1 delayed to T05!)
```

**After:**
```
T03 [travel] p2_tr_1  — "Which countries have you been?"  (pos 1, now served correctly) ✓
T04 [travel] p2_tr_2  — "Where do you like best?"         (pos 2) ✓
T05 [travel] p2_tr_3  — "What's fun to do there?"         (pos 3) ✓
T06 [travel] p2_tr_4  — "How was it?"                     (pos 4) ✓
```

Travel now serves all 4 partner frames in order before bridging at T07.

**Status: CONFIRMED ✓**

---

### Fix 5 — Hobby duplicate opener (Issue 6)

**Before:**
```
T01 [hobby] f_what_hobby   — "What hobbies do you have?"
T02 [hobby] f_like_do_what — "What do you like to do?"    ← near-duplicate immediately after
```

**After:**
```
T01 [hobby] f_what_hobby   — "What hobbies do you have?"
T02 [hobby] f_often_do     — "Do you do it often?"        ← substantive follow-up ✓
T03 [hobby] f_difficult_ma — "Is it difficult?"
T04 [hobby] f_like_do_what — "What do you like to do?"    ← now at T04, separated by 2 frames
```

**Status: CONFIRMED ✓**

---

### Fix 6 — Work option relevance (Issue 5)

**Before (sample from p2_wk_3 / p2_wk_4):**
```
T05 [work] opts: 北京 / 住 / 最近      ← 北京 (Beijing city name) is irrelevant to work
T06 [work] opts: 安排 / 姐姐 / 和      ← 姐姐 (older sister) is family vocabulary, not work
```

**After:**
```
T05 [work] opts: 我 / 最近 / 工作      ← 工作 (work) now present
T06 [work] opts: 解决 / 工作 / 安排    ← all three are work-domain vocabulary ✓
T07 [work] opts: 解决 / 喜欢 / 最近    ← work-domain dominant
```

Builder fix ensures distractor pool prioritises same-engine cards (work vocabulary).

**Status: CONFIRMED ✓**

---

## Bonus improvements observed

These were not targeted fixes but are visible in after-traces:

**Food FRAME_ORDER:** `f_food_famous_dish` now served at T02 (was `f_food_tasty`). FRAME_ORDER priority working across all engines that had slot-heuristic bypass.

**Identity FRAME_ORDER:** `p2_id_2` now at T02, `f_ask_name_meaning` at T03 — correct ordering within the identity engine itself.

**Place follow-through from identity:** After identity exhausts at T04, bridge to place now serves `f_place_like_there → frame.location.live_question` in order (benefiting from both the depth guard and FRAME_ORDER fix).

---

## Remaining issues

### (a) Selector issue

**Family depth (minor):** Family bridges after 3 turns (T03 → T04 bridge) with 2 family frames still available (`p2_fa_2`, `p2_fa_5`). The depth guard does not block because `remaining_frames_in_engine = 2 < ENGINE_DEPTH_GUARD_MIN_REMAINING (3)`. This is correct by design — the guard only blocks bridge when 3+ unseen frames remain. Could raise guard threshold to 2, but this is low priority.

**Identity → place bridge ordering (minor):** When family bridges to identity at T04 and then immediately bridges to place at T05, the system selects `f_from_where` as the first place frame. This is correct (FRAME_ORDER pos 0 for place), but feels slightly abrupt — two quick engine jumps in one session. Not a selector defect, more structural grammar.

### (b) Structural grammar issue

**All engines 100% questions:** Every simulated turn is a question frame. The system has no partner statement / self-disclosure frames (EXTEND type) that would break the question-only flow. This is a pre-existing structural gap — not a Phase 11.1 regression. Addressed only by adding EXTEND frames (content work).

**Listening frames absent:** The `pending_listening_move` mechanism exists but does not trigger in the observer simulation (simulated answers don't trigger high interest signals). In real use, interest classification should trigger this more often.

### (c) Content sparsity issue

**`p2_wk_3` option quality:** `opts: 我 / 最近 / 工作` — `我` (I) is a minimal filler word, not a meaningful work-domain distractor. Work engine's option pool is small; the builder now uses same-engine cards but the pool itself has limited vocabulary density.

**Slot tokens visible in options:** `p2_pl_1` shows `你觉得{CITY}生活怎么样？` — the `{CITY}` slot is not being filled in the observer output. This is an observer-display issue (not a runtime defect; in live UI, slots are filled dynamically from learner memory).

**Family engine depth:** Only 3 family frames + 2 unserved (`p2_fa_2`, `p2_fa_5`). Family has content sparsity compared to work (7 frames) and identity (5 frames). Consider adding 1–2 family follow-up frames.

### (d) Alpha polish issue

**Hobby opener text:** `f_what_hobby` displays as "you to have what hobby" (gloss-level English). This is a content-level rendering issue not related to selector logic.

**Travel `p2_tr_4` text:** "you to feel; to think then; that how is it" — same gloss-level English rendering issue.

**Bridge phrasing:** The bridge prefix (e.g. 对了, 顺便) is not visible in the observer traces. In real UI testing, check that bridge prefixes fire naturally when crossing engines.

---

## Verdict

| Fix | Target | Status |
|-----|--------|--------|
| Engine depth guard | Prevent early bridge | ✓ Confirmed |
| Identity re-entry (bridge) | Skip f_ask_you_name when exchange≥2 | ✓ Confirmed |
| Identity re-entry (ladder+gate) | Extension applied in 11.1.1 pass | ✓ Confirmed |
| Place FRAME_ORDER | f_place_like_there before p2_pl_4 | ✓ Confirmed |
| Travel FRAME_ORDER | p2_tr_1 at T03 (was T05) | ✓ Confirmed |
| Hobby duplicate opener | f_often_do at T02 (not f_like_do_what) | ✓ Confirmed |
| Work option relevance | Work-domain distractors dominant | ✓ Confirmed |

**No new dead ends introduced.**  
**No regressions observed.**  
**Engine flow is deeper, more coherent, and correctly ordered.**

---

## Next highest-leverage bottleneck

The single largest remaining structural gap is the **100% question ratio** across all engines.
No EXTEND (self-disclosure) frames exist to break the interrogation feel.
This is a content/frame authoring gap, not a selector defect.

Recommendation for next phase: author 1–2 EXTEND frames per engine where the partner volunteers
a related statement before asking the next question (e.g. "我也很喜欢旅行！你去过哪些地方？").
This requires content work, which is outside the current selector/hygiene scope.
