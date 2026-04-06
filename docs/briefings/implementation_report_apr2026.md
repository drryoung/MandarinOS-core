# MandarinOS — Implementation Report (April 2026 Landing)

**Branch:** phase10  
**Date:** 6 April 2026  
**Purpose:** Post-landing containment record for ChatGPT strategic review.  
**Covers:** Changes made in response to strategic review feedback, plus trace instrumentation and brevity guard.

---

## 1. Exact files changed

| File | Nature of change |
|------|-----------------|
| `scripts/ui_server.py` | Priority reorder, reaction dedup, two-slot model, trace instrumentation, brevity guard |
| `ui/app.js` | Round-trip `recent_reactions` state field (send + receive) |

No changes to `p2_frames.json`, `content/recovery_phrases.json`, or `scripts/learner_memory_capture.py` in this landing.

---

## 2. Exact state fields added

### Client → Server (sent in `conversation_state`)
| Field | Type | Description |
|-------|------|-------------|
| `recent_reactions` | `string[]` (max 2) | Last 2 reaction prefix texts used; exclusion pool for deduplication |

### Server → Client (returned in response, round-tripped)
| Field | Type | Description |
|-------|------|-------------|
| `recent_reactions` | `string[]` (max 2) | Updated after each turn; persists across turns via client round-trip |

### New server-side response fields (not persisted in client state, diagnostic only)
| Field | Type | Description |
|-------|------|-------------|
| `selector_trace` | `object` | Frame selection decision trace (see §3) |
| `reaction_trace` | `object` | Reaction composition decision trace (see §3) |

---

## 3. Exact trace fields added

### `selector_trace`

```json
{
  "slot_followup": "<frame_id or null>",
  "ladder": "<frame_id or null>",
  "probe_eligible": true,
  "probe_chosen": "<frame_id or null>",
  "probe_suppressed_reason": "interest_not_high | engine_not_grounded_lt2_turns | no_eligible_probe_frame | null",
  "bridge_considered": false,
  "bridge_rejected_reason": "depth_guard_blocks | bridge_not_allowed | null",
  "final_frame_source": "slot_followup | ladder | curiosity_probe | bridge | other | not_computed"
}
```

- `probe_eligible`: true only when `interest_decayed == "high"` AND `same_engine_chain_count >= 2`
- `bridge_considered`: true when `chosen is None` AND `bridge_allowed` AND gate/force condition met
- `final_frame_source`: set after frame is resolved by comparing `chosen` against the source that produced it

### `reaction_trace`

```json
{
  "ack_slot": true,
  "ack_slot_trigger": "CITY | JOB | COMPANY | DISH | TRAVEL | NAME | null",
  "stance_slot": true,
  "stance_slot_reason": "interest=high | interest=medium | null",
  "pool_before": 5,
  "pool_after": 4,
  "filter_applied": true,
  "composition_mode": "echo_only | stance_only | echo+stance | echo_only (brevity_guard) | none"
}
```

- `pool_before`/`pool_after`: raw pool size vs. post-deduplication pool size for the stance pick
- `filter_applied`: true when at least one recent reaction was excluded from the pool
- `composition_mode`: the final outcome of the two-slot policy; `brevity_guard` suffix means the combined form was truncated back to echo-only

---

## 4. Determinism risks introduced

**None introduced.** The following determinism properties are preserved:

| Property | Status |
|----------|--------|
| Frame selection | Fully deterministic: same inputs → same frame |
| Reaction pool ordering | Stable: pool is `list()` of a dict value, order preserved |
| Deduplication filter | Deterministic exclusion: removes exact string matches |
| `_stable_pick` on filtered pool | Deterministic hash pick on same-sized filtered pool |
| `recent_reactions` round-trip | Stable LIFO list of max 2 items; no randomness |
| Brevity guard | Pure arithmetic check on Chinese char count, no randomness |

**One known hash-collision risk (pre-existing, not introduced here):**  
If two different frames happen to yield the same seed hash modulo pool size, they will pick the same pool entry. This was already present. The fix (including `last_answer_fid` in the seed) reduces but does not eliminate this risk. It is not a new determinism risk from this landing.

---

## 5. Example traces

### Example 1 — Ladder beats curiosity (interest = medium, engine not yet grounded)

**Scenario:** Learner answers `f_what_work` → "我以前是老师" (interest = medium, same_engine_chain_count = 1)

```json
{
  "selector_trace": {
    "slot_followup": "f_probe_work_role_detail",
    "ladder": null,
    "probe_eligible": false,
    "probe_chosen": null,
    "probe_suppressed_reason": "engine_not_grounded_lt2_turns",
    "bridge_considered": false,
    "bridge_rejected_reason": null,
    "final_frame_source": "slot_followup"
  }
}
```

*Note: slot followup fires here (from JOB slot chain) rather than ladder, but the trace correctly shows probe was suppressed because the engine has only 1 turn. If no slot followup existed, the ladder frame would have been chosen and probe suppressed.*

### Example 2 — Curiosity probe overrides ladder (interest = high, engine grounded)

**Scenario:** Learner answers deeply in work engine (chain_count = 3, interest = high, slot followup chain exhausted)

```json
{
  "selector_trace": {
    "slot_followup": null,
    "ladder": "f_work_origin",
    "probe_eligible": true,
    "probe_chosen": "f_probe_work_dream",
    "probe_suppressed_reason": null,
    "bridge_considered": false,
    "bridge_rejected_reason": null,
    "final_frame_source": "curiosity_probe"
  }
}
```

### Example 3 — Echo only (CITY slot, medium interest)

**Scenario:** Learner says "我现在住在苏州" (interest = medium, CITY slot detected)

```json
{
  "reaction_trace": {
    "ack_slot": true,
    "ack_slot_trigger": "CITY",
    "stance_slot": true,
    "stance_slot_reason": "interest=medium",
    "pool_before": 5,
    "pool_after": 4,
    "filter_applied": true,
    "composition_mode": "echo_only"
  }
}
```

*Echo "哦，苏州！" is used. Although stance was computed, the policy is: salient entity + non-HIGH interest → echo only.*

### Example 4 — Stance only (no named entity, medium interest)

**Scenario:** Learner says "教师短缺，所以我试过，而且很擅长" (interesting but no entity slot)

```json
{
  "reaction_trace": {
    "ack_slot": false,
    "ack_slot_trigger": null,
    "stance_slot": true,
    "stance_slot_reason": "interest=medium",
    "pool_before": 5,
    "pool_after": 5,
    "filter_applied": false,
    "composition_mode": "stance_only"
  }
}
```

*No echo candidate possible. Stance reaction "听起来很有意思！" or similar used.*

### Example 5 — Echo + stance (JOB slot, high interest, combined ≤16 Chinese chars)

**Scenario:** Learner says "我曾经是首席信息官" (interest = high, JOB slot, chain_count ≥ 2)

```json
{
  "reaction_trace": {
    "ack_slot": true,
    "ack_slot_trigger": "JOB",
    "stance_slot": true,
    "stance_slot_reason": "interest=high",
    "pool_before": 5,
    "pool_after": 3,
    "filter_applied": true,
    "composition_mode": "echo+stance"
  }
}
```

*Echo "哦，首席信息官！" (6 zh chars) + stance "真的吗，太厉害了！" (8 zh chars) = 14 zh chars total → under the 16-char brevity guard → combined prefix used.*

---

## 6. What was NOT changed (per containment instruction)

- No selector threshold changes
- No bridge logic changes  
- No engine frame wording changes
- No additional reaction heuristics
- No interest scoring changes
- No `p2_frames.json` changes
- No `learner_memory_capture.py` changes

---

## 7. Remaining open items (deferred to next session)

Per strategic review, these were identified as "later design work":

| Item | Deferred reason |
|------|----------------|
| Bridge: disclosure-to-entry-frame scoring | Requires new declarative table; significant design work |
| Interest threshold rebalancing | Requires calibration data from real session logs |
| Common job declarative skip table | Low priority; current slot followup handles most cases |
| Slot followup vs curiosity probe cleaner boundary audit | Content audit; no code changes needed immediately |
