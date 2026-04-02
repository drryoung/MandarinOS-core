# MandarinOS Strategist Briefing
## Phase 12E — Curiosity Probe Frames + Contextual Discovery

**Status: PENDING APPROVAL — do not implement until reviewed**

**Prepared by:** Cursor AI (phase10 branch)
**Date:** 2026-04-01
**Review by:** Strategist ChatGPT

---

## 1. Problem statement

Alpha sessions 5–8 revealed a structural gap in conversational depth:

- When a learner gives a **rich or interesting answer**, the app advances to the next preset frame in the engine ladder rather than going deeper.
- The learner has no natural path to explore what the **persona has just disclosed** — discovery panel questions are generic to the engine, not specific to what was just said.
- The result is a **surface-skimming conversation** that neither rewards interesting answers nor gives the learner tools to dig deeper when they want to.

This is a **category D problem** (structural discourse deficit) in the architectural classification. It cannot be fixed by content alone; it requires a small selector-side mechanism to gate deeper frames based on answer quality.

---

## 2. Existing asset: `interest_level`

A server-side signal already exists:

```
interest_level = "low" | "medium" | "high"
```

It is computed from slot fills, answer length, evaluative/narrative language, and topic novelty. It currently controls:
- Whether the generic probe button row appears in the UI
- Whether the app selects a "listening move" (brief acknowledgement) before the next question

It does **not** currently select different **frames** based on interest level. That gap is what Phase 12E closes.

---

## 3. Proposed solution: Curiosity Probe Frames

### 3.1 What they are

A set of 22 new partner-spoken frames (`speaker: "partner"`) added to `p2_frames.json`, organised by engine. Each frame:

- Asks a **personal or reflective question** that goes deeper than the existing ladder
- Has a **minimum interest level** (`medium` or `high`) that must be met before it can be selected
- Has an optional **content condition** (specific slot filled, or memory state)
- Is difficulty 2 or 3 — appropriate for current learner level

### 3.2 Where they sit in the selector

The selector priority order becomes:

```
1. User question → counter_reply
2. Special content override (retired pivot, etc.)
3. Slot followup preference (immediate first-time slot fill)
4. ← NEW → Curiosity probe frame (medium/high interest, slot ladder exhausted)
5. Generic engine ladder
6. Bridge to new engine
```

This is a **single insertion point** — no other selector logic changes.

### 3.3 The 22 frames by engine

| Engine | Frames | Minimum interest |
|--------|--------|-----------------|
| Identity | 你喜欢自己的名字吗？ / 家里人是怎么叫你的？ / 你觉得名字符合你的性格吗？ | medium / medium / high |
| Place | 你在那里住了多久了？ / 你为什么选择住在那里？ / 你会想念老家吗？ / 你打算在那里长期住下去吗？ | medium (×3, lives_in≠hometown) / high |
| Work | 你是怎么开始做这份工作的？ / 这是你当时想做的工作吗？ / 工作里你最喜欢哪个部分？ / 你以后还想做别的工作吗？ | medium (×3) / high |
| Food | 你会自己做吗？ / 你小时候常吃吗？ / 你愿意教我怎么做吗？ | medium / medium / high |
| Family | 你和家里谁最亲近？ / 家里谁对你的影响最大？ / 你们最喜欢一起做什么？ | medium / high / medium |
| Hobby | 你是怎么开始喜欢这个的？ / 你一般自己做还是跟朋友一起？ / 这个爱好给你的生活带来了什么？ | medium / medium / high |
| Travel | 你旅行的时候喜欢自己去还是跟人一起？ / 旅行让你学到了什么？ | medium / high |

### 3.4 Curiosity exhaust (when to stop probing)

Currently `MAX_PROBE_CHAIN = 2` globally. Proposed change:

| interest_level | max consecutive probe frames |
|----------------|------------------------------|
| high | 4 |
| medium | 2 (unchanged) |
| low | 0 — suppress even if chain < cap |

When the chain is exhausted OR interest drops to low, the selector bridges to a new engine as now.

### 3.5 Contextual discovery questions (mirror side)

When the persona gives a `counter_reply`, the discovery panel currently shows generic engine mirror questions. Proposed addition: **one targeted question at the top of the panel**, derived by scanning the counter_reply text for keywords.

Example keyword → targeted question lookup:

| Keyword in counter_reply | Targeted question shown to learner |
|---|---|
| 教书 / 老师 | 你最喜欢教什么年级？ |
| 主厨 / 厨师 | 你最擅长做什么菜？ |
| 书法 / 练 / 楷书 | 你练了多久了？ |
| 独生 / 兄弟 / 姐妹 | 你们感情好吗？ |
| (city name) | 那里和你住的地方有什么不一样？ |
| 羽毛球 / 爬山 / 吉他 | 你是怎么开始学的？ |

This table is small (15–20 entries), lives in the server, and is additive — no existing discovery logic is removed.

---

## 4. Architectural compliance

| Rule | Status |
|------|--------|
| Additive growth — no existing frames replaced | ✅ |
| Selector independence — no frame-ID-specific selector logic | ✅ (interest_level is content-agnostic) |
| Extensibility test — adding 20 more probe frames requires no selector change | ✅ |
| Builder-first — problem solved with content + minimal logic gate, not rewrite | ✅ |
| `MAX_PROBE_CHAIN` respected | ✅ (extended, not removed) |

The only new logic is one function `_pick_curiosity_probe_frame()` and one dict `_CURIOSITY_PROBE_FRAMES`. No existing functions are modified except for a 3-line insertion in the selector to call the new function.

---

## 5. What this does NOT do

- Does not change the Phase 6 runtime architecture
- Does not touch the scoring engine, TTS, or UI option rendering
- Does not remove or replace any existing frames
- Does not add new move_types or grammar signals
- Does not require changes to persona JSON files

---

## 6. Implementation scope

Three files change:

| File | Change |
|------|--------|
| `p2_frames.json` | Add 22 probe frames |
| `scripts/ui_server.py` | Add `_CURIOSITY_PROBE_FRAMES` dict + `_pick_curiosity_probe_frame()` + 3-line call in selector + keyword lookup for discovery panel |
| (no client changes required) | — |

Estimated effort: medium. No new dependencies. Reversible if behaviour is wrong — removing the 3-line selector call returns to current behaviour.

---

## 7. Questions for strategist review

1. **Probe chain cap**: Is 4 the right maximum for high-interest conversations, or should it be 3? A longer chain risks feeling like an interrogation if the learner's answers are rich but they still want to advance.

2. **Contextual discovery questions**: Should these appear above or below the generic engine questions in the panel? Above feels more useful but may crowd out the learner's current "safe" options.

3. **Probe frame ordering within engine**: Frames are ordered medium-interest first, high-interest last. Is this correct, or should high-interest frames be offered first when the signal is already high?

4. **Scope boundary**: Should Phase 12E include the contextual discovery question enhancement, or should that be deferred to Phase 12F to keep the change set small and testable?

---

## 8. Recommended decision

Approve Phase 12E as described. Begin with the 22 probe frames and the selector gate. Defer the contextual discovery question enhancement to Phase 12F unless strategist confirms it is low-risk enough to include here.
