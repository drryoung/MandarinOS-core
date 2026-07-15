# MandarinOS — Conversation Flow Design Principles

**Status:** Authoritative. Read before modifying `ui_server.py`, any `*_frames.json`, or any selector/ordering logic.
**Last updated:** 2026-04-05

---

## 0. What MandarinOS is (anchor)

MandarinOS is a **curiosity-led conversation training tool**. Its purpose is to help learners build usable spoken Mandarin through repeated exposure to **standard phrases (frames)** and **inherently interesting topics (engines)**.

Two things make it work:

1. **Predictable pattern** — the question sequence within each engine follows a natural, easily discernible order (greeting → place → distance → character → how long → like it → why). A motivated learner can memorise this and feel confident about what comes next.
2. **Curiosity divergence** — when an answer is interesting or surprising, the conversation should temporarily deviate: ask a follow-up, echo the detail, or bridge to a new topic. Once interest drops, return to the predictable pattern or bridge to a fresh engine.

These two goals are in tension. The architecture must serve both. Complexity arises when people try to serve one goal while forgetting the other.

---

## 1. Question ordering — how it works and how to extend it

### 1.1 The single source of truth

The preferred order of questions **per engine** is stored in one place:

```python
_FRAME_ORDER: dict  # in ui_server.py
# e.g.  "place": ["f_from_where", "frame.location.live_question", "p2_pl_far", ...]
```

This list is guidance, not a rigid script. The selector tries to honour the order, but curiosity, bridges, and user-led moves can defer any frame.

**Rule:** To change question order for an engine, edit `_FRAME_ORDER` for that engine. Do not add imperative `if`-blocks around the selector to route flow.

### 1.2 Skip conditions — declarative, not imperative

Some frames should be skipped for certain learner contexts (e.g. "Is it far?" is trivially answered for Beijing). The correct mechanism is:

**Step 1 — Annotate the frame** in `p2_frames.json` with a `skip_when` field:
```json
{
  "id": "p2_pl_far",
  "text": "离那儿远吗？",
  "skip_when": "city_is_well_known"
}
```

**Step 2 — Register the predicate** in `_check_skip_condition()` in `ui_server.py`:
```python
def _check_skip_condition(frame_id: str, context: dict) -> bool:
    predicate = (frames_by_id[frame_id].get("skip_when") or "").strip()
    if predicate == "city_is_well_known":
        return _should_skip_place_distance_question(context["answer_text"], context["memory"])
    ...
```

**Step 3 — Nothing else changes.** The frame ladder (`_frame_order_priority`), slot followup (`_pick_slot_followup_frame_id`), and the final safety-net guard all call `_check_skip_condition` automatically.

### 1.3 How to add a new skip condition

1. Add `"skip_when": "your_predicate_name"` to the relevant frame(s) in `p2_frames.json`.
2. Add `if predicate == "your_predicate_name": return <bool>` inside `_check_skip_condition()`.
3. Done. No other files need to change.

### 1.4 Slot followup preferences

The `_SLOT_FOLLOWUP_PREFERENCES` dict maps slot types (e.g. `CITY`, `JOB`, `DISH`) to a preferred sub-sequence of frames. These preferences are tried first, before falling back to the engine ladder. Frames in this list are subject to `_check_skip_condition`, so `skip_when` annotations are respected here too.

If a slot needs a different frame sequence, **add or reorder frames in the preference list**. Do not replace the list with a conditional alternative list based on runtime state.

---

## 2. Curiosity-led divergence

### 2.1 The curiosity model

Every answer has an **interest level** (`low` / `medium` / `high`). The selector tracks `curiosity_depth` — how many consecutive follow-up questions have been asked without a topic change.

The conversation flow is:
```
answer received
  ↓
measure interest level
  ↓
low interest → bridge to new engine (or continue FRAME_ORDER)
medium interest → 1-2 follow-up frames (slot followup → curiosity probe → ladder)
high interest → up to curiosity cap follow-ups; oxygen question or bridge
```

### 2.2 Oxygen / echo questions

When a response is surprising or mentions an unusual detail (a foreign city, an unexpected hobby, an unexpected family situation), the first follow-up should **echo the interesting detail** before asking a deeper question.

Pattern:
```
User: 我现在住Dunedin。
Partner: Dunedin！每个地方都有自己的特点。你觉得那儿有什么特色？
```

This "echo + what-is-special" pattern is called an **oxygen question** — it keeps the conversation breathing on an interesting point without forcing a deeper commitment. It maps to `move_type = EXTEND` frames.

Do NOT hard-code oxygen phrases as strings in `ui_server.py`. They belong in frames tagged as `EXTEND` or in curiosity-probe frame definitions.

### 2.3 Bridge questions

When interest drops (curiosity depth reaches cap, or answers become monosyllabic), the selector should **bridge to a new engine**. Bridge questions are lightweight openers for a new topic. They are defined in `_select_next_frame_bridge()`.

The interest drop → bridge rule is implemented via `_curiosity_cap` and the `pending_listening_move` logic. Do not add separate `if interest == "low"` blocks scattered in the turn handler.

### 2.4 When to prioritise geography / descriptor questions

For unfamiliar places (Dunedin, Łódź, Invercargill), the natural question order is:
1. Is it far? (`p2_pl_far`) — skip for very well-known cities (北京, 上海, 广州)
2. What's special about it? (`p2_pl_ext1`) — skip for familiar curriculum cities
3. How long have you lived there? (`f_probe_place_moved`)
4. Do you like it there? (`f_place_like_there`)

This order is encoded in `_FRAME_ORDER["place"]` and the `CITY` slot preference list in `_SLOT_FOLLOWUP_PREFERENCES`. Skip conditions are declared on the frames themselves. No runtime conditional logic should be needed.

---

## 3. Recovery hierarchy

When the learner or the app does not understand a response, the system should escalate through a hierarchy of recovery strategies. This is a distinct layer from curiosity follow-ups.

### 3.1 Recovery escalation order

```
Level 1 — Confidence-keeping: "嗯，[我明白]。" / brief acknowledgement
Level 2 — Clarification probe: "你说的是……？" / echo + check
Level 3 — Targeted repair: "[X] 是什么意思？" / "可以再说一次吗？"
Level 4 — Simplification offer: "你能简单一点说吗？" / guided options
Level 5 — Fallback: show selectable response options + "Need help?" panel
```

### 3.2 Where recovery phrases live

All recovery phrases are in `content/recovery_phrases.json`. Sub-keys:
- `persona_deflect` — partner gracefully deflects (e.g. for age/sensitive topics)
- `deflection_ack` — partner acknowledges learner's non-answer

Do NOT write recovery strings inline in Python. Add them to `recovery_phrases.json`.

### 3.3 What triggers the recovery UI

The client-side "Need help?" panel (`renderRecoveryPanelInto()`) is triggered by `not_understood` signal or by `learner_skip_confusion`. It must always be rendered inside the active container using the canonical `.option-panel` structure. See `.cursor/rules/mandarinos-ui-objects.mdc`.

---

## 4. Content complexity — vocabulary and phrase design

MandarinOS frames should be learnable through repetition. Vocabulary must be accessible.

### 4.1 Vocabulary guidelines

- **Prefer high-frequency vocabulary**: 吗, 呢, 怎么样, 有什么, 喜欢, 多久, 觉得, 是不是
- **Avoid low-frequency grammar patterns** for core frames: potential complements (走得了), complex resultative verbs, 把-sentences unless essential
- **Keep frame sentences short** (≤12 characters preferred for P2 partner questions)
- **Options should be learnable** — if an option requires vocabulary outside the current engine's P1 pack, flag it

### 4.2 The "drift towards complexity" anti-pattern

A recurring failure mode: someone adds a nuanced follow-up phrase, notices it "feels off", then adds more conditional logic to avoid showing it in certain contexts — creating an ever-growing web of guards. The root cause is always a frame that is **too complex for its role**. Fix the frame, not the selector.

---

## 5. Anti-patterns — what to avoid

These are failure modes observed during development. Each one has caused real complexity in the codebase.

### AP-1: Conditional preference lists overriding `_FRAME_ORDER`

**What happened:** `_CITY_FOLLOWUP_UNFAMILIAR_PLACE` was created as a special alternative to the standard `CITY` slot preference list. The selector switched between the two lists based on `_city_seems_unfamiliar()`.

**Why it's bad:** Two sources of truth for ordering. Every new city-related frame had to be added to both lists. The lists drifted apart.

**The fix:** One preference list (`_SLOT_FOLLOWUP_PREFERENCES["CITY"]`). Skip conditions are declared on frames via `skip_when`. `_check_skip_condition` is called in the loop. No runtime list-switching needed.

**Rule:** Never create an alternative version of a preference list or `_FRAME_ORDER` segment. Add the frames, declare `skip_when` conditions.

---

### AP-2: Bypassing `_frame_order_priority` with a wrapper flag

**What happened:** `_skip_frame_order_for_unfamiliar_place()` was added to prevent `_frame_order_priority` from re-ordering frames that had been deliberately chosen for an unfamiliar city. `_maybe_frame_order_priority()` wrapped it.

**Why it's bad:** The bypass negated the whole point of `_FRAME_ORDER`. The system now had two competing ordering systems.

**The fix:** `_frame_order_priority` itself now calls `_check_skip_condition` so it naturally skips well-known-city frames when walking the ladder. The bypass is not needed.

**Rule:** Do not bypass `_frame_order_priority` with runtime guards. If the ladder keeps promoting the wrong frame, the problem is either a missing `skip_when` condition or the wrong frame order in `_FRAME_ORDER`.

---

### AP-3: "Final guard" functions that re-implement selector logic

**What happened:** `_swap_place_like_if_unfamiliar_live_city()` was added as a late override, duplicating the same `_should_skip_place_distance_question` and `_city_seems_unfamiliar` checks that were already scattered elsewhere.

**Why it's bad:** The same decision (skip `p2_pl_far` for Beijing?) was computed in 3+ places. Changing the rule required finding all the places.

**The fix:** All skip decisions flow through `_check_skip_condition`. The guard now just iterates candidates and calls `_check_skip_condition`. A single change to `_check_skip_condition` propagates everywhere.

**Rule:** When you find yourself writing the same city/place/context check in two places, that check belongs in `_check_skip_condition`. Add a predicate there. Wire it via `skip_when` in the frame JSON.

---

### AP-4: Hard-coding question text in `ui_server.py`

**What happened:** Early versions of the "is it far?" feature added the response text as a string in `_place_distance_counter_reply()` in Python.

**Why it's bad:** Questions are not discoverable, translatable, or improvable without touching server code. The content lives in the wrong layer.

**Rule:** All Chinese sentences that the partner might say belong either in a frame definition (`p2_frames.json`), a persona file (`personas/*.json`), or a phrase bank (`content/recovery_phrases.json`, `content/mirror_questions.json`). Never write Chinese sentence strings inline in Python business logic.

---

### AP-5: Duplicating frame-ID normalisation in multiple call sites

**What happened:** Both `p1_frames.json` and word-card flows used different IDs for the same live-location frame (`frame.location.live_question` vs `f_live_where`). Multiple functions independently re-implemented the normalisation check.

**Why it's bad:** One missed call site and the normalisation breaks silently.

**The fix:** `_normalize_frame_id()` in one place; called wherever a frame ID from any source enters the system.

**Rule:** If you find yourself writing `if fid == "f_live_where": fid = "frame.location.live_question"` anywhere except `_normalize_frame_id`, stop and add it there instead.

---

### AP-6: ASR echo loop from concurrent TTS + microphone

**What happened:** The partner's TTS was still audible when ASR was started, causing the app to transcribe its own voice as learner input.

**The fix:** `window.speechSynthesis.cancel()` followed by a 380 ms delay before `rec.start()` in `listenForResponse()` in `ui/app.js`.

**Rule:** Never start ASR while TTS may still be playing. Always cancel synthesis and add a settle delay. Guard against concurrent `runTurn` calls with `_runTurnInFlight`.

---

## 6. Summary of implementation rules

| Rule | Where enforced |
|------|----------------|
| Question order per engine | `_FRAME_ORDER` in `ui_server.py` |
| Skip conditions for specific frames | `skip_when` field in `p2_frames.json`; evaluated by `_check_skip_condition()` |
| New skip predicate | Add one `if predicate == "...": return ...` in `_check_skip_condition()` |
| Slot followup preferences | `_SLOT_FOLLOWUP_PREFERENCES` in `ui_server.py`; `skip_when` respected |
| Partner Chinese sentences | Frame JSON, persona JSON, or phrase-bank JSON — never inline Python strings |
| Recovery phrases | `content/recovery_phrases.json` |
| Recovery UI structure | Canonical `.option-panel` — see `.cursor/rules/mandarinos-ui-objects.mdc` |
| Frame ID normalisation | `_normalize_frame_id()` in `ui_server.py` |
| ASR / TTS timing | Cancel TTS, delay 380ms, then start ASR — in `listenForResponse()` |

---

## 7. Extensibility test (mandatory before any selector change)

Before proposing any change to selector logic, scoring, or ordering, verify:

> **Adding 20–50 new frames to any engine must not require changes to selector logic, `_check_skip_condition`, or runtime architecture.**

If a proposed change fails this test, it is an extensibility risk. Flag it, explain why the lowest-sufficient intervention is not enough, and get explicit approval before proceeding.

---

## 8. Related documents

| Document | Role |
|----------|------|
| `docs/specs/Cursor_Directive_MandarinOS_Extensibility_Strategy.md` | Decision priority order; beta feedback classification |
| `docs/archive/specs/MandarinOS_Repair_Curiosity_Loop.md` | Curiosity trigger and comprehension repair loop design (historical, class C) |
| `docs/specs/MandarinOS_next_question_selector_v1.md` | Selector philosophy and input model |
| `docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md` | Index of all conversation design documents |
| `.cursor/rules/mandarinos-architecture.mdc` | Cursor standing rule; enforced every session |
| `.cursor/rules/mandarinos-ui-objects.mdc` | Canonical UI object rules |
| `AI_CONTEXT.md` | Repo map; read before any architecture change |
