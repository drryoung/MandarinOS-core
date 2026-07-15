# MandarinOS Conversation Engine — Architecture Briefing (April 2026)

**Audience:** Strategic review (ChatGPT as conversation architect)  
**Purpose:** Review whether the current implementation approach is systematic and principled, or accumulating ad hoc patches. Request guidance before further development.

---

## 1. What MandarinOS Is

A Mandarin language learning app where the learner has a spoken conversation with a partner persona (P2). The partner asks questions in Chinese, the learner responds in Chinese via speech (ASR), and the system reacts, echoes, and probes to create a natural small-talk conversation. The learner practices speaking and listening; the system never teaches or corrects explicitly.

**Core design goals:**
- Feel like a genuine curious conversation partner
- Ask questions that lead naturally from what the learner just said
- Stay on a topic long enough to discover genuinely interesting details
- Bridge to related topics smoothly when a topic is exhausted
- Handle ASR failures gracefully without killing the conversation

---

## 2. Current Architecture — The Five Layers

### Layer 1: Frame Database
- **`p2_frames.json`**: ~120 partner question frames (the P2 asks these)
- **`p1_frames.json`**: ~65 learner response frames (options the learner can select)
- Each frame has: `id`, `text` (Chinese), `pinyin`, `text_en`, `engine`, `difficulty`, `move_type`, `skip_when` (optional)
- Engines: identity, place, work, family, hobby, travel, food, life

### Layer 2: Frame Selector (`ui_server.py`)
The selector chooses the next partner question each turn. Priority order:

```
1. SLOT FOLLOWUP PREFERENCES   (content-responsive; interest-gated)
2. CURIOSITY PROBE FRAMES      (depth questions; interest-gated)
3. FRAME ORDER LADDER          (default linear progression per engine)
4. BRIDGE                      (switch to another engine)
```

**Interest gating**: Slot followup + curiosity probes only fire when `interest_level` is medium or high. The system falls back to the frame ladder for low-interest turns.

### Layer 3: Interest Scoring
Scores each learner answer (0–7+):
- Slot detected: +2
- Memory written: +1
- Answer length ≥4 chars: +1
- Reasoning words (因为, 所以, 觉得...): +1
- Evaluative words (有意思, 喜欢, 好吃...): +1
- Novelty markers (以前, 曾经, 有一次...): +1
- Notable job title (首席, 总裁, 博主...): +1 (new)

Thresholds: medium ≥1, high ≥3.

### Layer 4: Reaction + Echo Layer
After every learner answer, the system prepends a short reaction to the next question:
- **Curiosity reaction** (from engine-specific pool): fires when interest ≥ medium
- **Echo** (personalised slot value): fires when reaction is short/bland (≤4 Chinese chars), overrides with "哦，苏州！" or "哦，首席信息官！"
- Both are prepended to the next question frame text

### Layer 5: Bridge System
When an engine is exhausted or interest drops, bridge to another engine:
- **Static bridge targets**: `_BRIDGE_TARGETS["work"] = ["family", "identity", "place", "hobby"]`
- **Seeded bridge queue**: engines discovered from learner answers (e.g., mentions "苏州" → seeds place engine) are tried first
- **Depth guard**: prevents bridging while ≥2 unseen frames remain in current engine

---

## 3. Key Data Structures

### `_FRAME_ORDER` (per engine)
Linear progression of frames within an engine. The selector walks this when slot followup and curiosity probes are exhausted.

```python
_FRAME_ORDER["work"] = [
    "f_what_work",        # What do you do?
    "f_work_company",     # Which company?
    "f_work_tenure",      # How long?
    "f_work_where",       # Where?
    "f_probe_work_origin",# How did you start?
    "f_probe_work_future",# Do you still want to do this?
    "f_probe_work_why_quit",  # Why not?
]
```

### `_SLOT_FOLLOWUP_PREFERENCES` (per slot type)
When a specific slot is detected in the learner's answer, the selector prefers these frames **instead of** the normal frame order. This is the primary content-responsive mechanism.

```python
_SLOT_FOLLOWUP_PREFERENCES["JOB"] = [
    "f_probe_work_role_detail",  # What kind of work is that? (new)
    "f_work_company",            # Which company?
    "f_work_tenure",             # How long?
    ...
]
_SLOT_FOLLOWUP_PREFERENCES["COMPANY"] = [
    "f_probe_work_company_vibe", # What's that company like? (new)
    "f_work_tenure",
    ...
]
```

### `_CURIOSITY_PROBE_FRAMES` (per engine)
Extra depth questions, ordered by interest threshold. Only fire after slot followups are exhausted.

```python
_CURIOSITY_PROBE_FRAMES["work"] = [
    {"id": "f_probe_work_role_detail", "interest_min": "medium"},  # new
    {"id": "f_probe_work_dream",       "interest_min": "medium"},
    {"id": "f_probe_work_best",        "interest_min": "medium"},
]
```

### `_MUTUAL_EXCLUSION_FRAMES`
Prevents semantically identical questions from being asked twice (e.g., "你是哪里人？" and "你老家在哪儿？").

### `_FRAME_ID_TO_SEED`
Maps a specific answered frame to an engine that should be queued for future bridging.
```python
_FRAME_ID_TO_SEED = {"f_work_where": "place"}
```

---

## 4. Recent Changes (Phase 13C — April 2026)

These changes were made iteratively in response to observed conversation failures. The concern is whether they are principled or ad hoc.

| Change | Rationale | Assessment |
|--------|-----------|------------|
| Add `f_probe_work_role_detail` to JOB slot followup | Any interesting job should prompt "what kind of work is that?" | **Principled** — extends existing slot followup mechanism |
| Add `COMPANY` slot + `f_probe_work_company_vibe` | After naming any company, ask what it's like | **Principled** — extends existing slot followup mechanism |
| Echo condition changed to `_zh_chars_in_reaction <= 4` | Echo fires for bland reactions; curiosity reactions (≥5 chars) preserved | **Somewhat ad hoc** — relies on character count as proxy for "bland"; fragile |
| `exchange_count` gate for curiosity reactions removed | First disclosure in any engine deserves curiosity | **Principled** |
| `_JOB_NOTABLE_ROLE_MARKERS` bonus to interest score | "首席信息官", "博主" etc. should score HIGH interest | **Principled** — extends interest scoring |
| "曾经是X的Y" pattern in memory capture | Extracts company from job disclosure to suppress redundant question | **Principled** — closes gap in memory capture |
| Curiosity reaction pools expanded to 5 items | Reduces repetition | **Principled** |
| `_depth_guard_blocks` decoupled from `same_engine_chain_count` | Repair turns inflated the chain count, causing premature bridges | **Principled** — removes incorrect dependency |

---

## 5. Known Remaining Issues

### Issue A: Curiosity reaction still repeats
Despite 5-item pools, "真的吗，太厉害了！" appeared 4 times in one session. The `_stable_pick` hash seed includes `session_id + exchange_count + engine`, but all 4 turns were in the same engine with different exchange counts. The hash function is biased.

**Root cause**: `_stable_pick` uses a simple `char * 131` hash which for small pools (5 items) can have collisions across similar seeds. Need: (a) include the frame_id being asked in the seed, or (b) track last-used reaction in state and exclude it.

### Issue B: Work location → place bridge asks wrong question
After the learner says they work in "澳大利亚悉尼", the bridge seeds the place engine and asks "这里有什么特别的？" (what's special here?). But the learner may not LIVE in Sydney — they just WORK there. The system should first ask "你现在住哪里？" before exploring a place.

**Root cause**: The place engine's frame order starts with "f_place_special" (what's special here?) but doesn't first confirm whether the learner LIVES there. `f_work_where` and `f_live_where` are different frames but the bridge doesn't distinguish between "work location" and "home location" when entering the place engine.

### Issue C: f_probe_work_role_detail fires redundantly for known jobs
"那是什么样的工作？" makes sense for "首席信息官" or "社交媒体博主" but sounds odd when asked of a teacher or doctor — everyone knows what those are. There's no mechanism to skip the role-detail probe for common/well-known job types.

### Issue D: Same curiosity reaction appearing for multiple different disclosures
The reaction pool is per-engine, not per-turn. All work engine disclosures draw from the same 5-item pool with the same seed logic, making repetition likely in a long work engine session.

### Issue E: Bridge targets still somewhat static
After the work engine, the bridge order is `["family", "identity", "place", "hobby"]`. The seeded bridge queue adds dynamic priority, but if no seeds were collected, the fallback is static. Ideally, the bridge should always follow what the learner disclosed.

---

## 6. Architectural Questions for the Strategist

1. **Reaction selection**: Is a hash-based deterministic selection the right approach for curiosity reactions? Should reactions be tracked in session state and excluded if recently used? Or should the seed include more entropy (frame_id, recent frame count)?

2. **Echo vs. reaction priority**: Currently, echo overrides the reaction when the reaction is short (≤4 chars). Is this the right heuristic? Should echo ALWAYS fire for JOB/CITY/COMPANY slots regardless of the curiosity reaction, or is the enthusiasm signal more important than the echo?

3. **Slot followup vs. curiosity probe distinction**: Currently, `f_probe_work_role_detail` is in BOTH `_SLOT_FOLLOWUP_PREFERENCES["JOB"]` AND `_CURIOSITY_PROBE_FRAMES["work"]`. Is this duplication appropriate, or should the two mechanisms be kept cleanly separate?

4. **Work location → place bridge**: Should the bridge from work (specifically from `f_work_where`) target a special "confirm residence" frame before entering the place engine? Or should the `skip_when` predicate on place frames handle this?

5. **Common job skip**: Should `f_probe_work_role_detail` have a `skip_when` condition that fires for common/known job types (teacher, doctor, engineer)? If so, where should the "known job" list live?

6. **Interest scoring calibration**: The current thresholds (medium ≥1, high ≥3) mean most answers score medium (slot alone gives +2). Is the distinction between medium and high actually driving meaningful behaviour differences? Should the thresholds be raised?

7. **Bridge seeding scope**: Currently, only `f_work_where` seeds the place engine. Should other frames also seed engines? E.g., `f_work_company` + a foreign company name → seeds a "culture" or "travel" engine?

8. **Systematic vs. content-specific frames**: The current approach adds content-responsive frames to slot followup preferences. Is this the right pattern to continue for other engines (family, place, hobby)? Should each engine have an equivalent of `f_probe_work_role_detail`?

---

## 7. The Ad Hoc Risk

The core risk is that each new content-responsive behaviour requires:
1. A new frame in `p2_frames.json`
2. A new slot detection rule in `_infer_slot_names_from_answer`
3. A new entry in `_SLOT_FOLLOWUP_PREFERENCES`
4. Possibly a new memory capture pattern in `learner_memory_capture.py`
5. Possibly a new `_FRAME_ID_TO_SEED` entry

This is 4-5 touch points per new content-responsive behaviour. The touch points are consistent (all additive, no control flow changes) but the number of files makes the system hard to audit. A possible improvement: a single declarative config table that specifies slot → probe frame → seed → memory field in one place.

---

## 8. Summary of Files Touched

| File | Role | Frequency of change |
|------|------|---------------------|
| `scripts/ui_server.py` | Frame selector, reaction layer, bridge, interest scoring | Every session |
| `p2_frames.json` | Partner question content | Every content addition |
| `scripts/learner_memory_capture.py` | Fact extraction from answers | Rare |
| `ui/app.js` | Client state, recovery panel, seeded bridge | Occasional |
| `content/recovery_phrases.json` | Repair phrases | Rare |

---

*Prepared for strategic review, April 2026. Requesting guidance on: reaction deduplication, echo/reaction priority, systematic extension patterns, and bridge target confirmation logic.*
