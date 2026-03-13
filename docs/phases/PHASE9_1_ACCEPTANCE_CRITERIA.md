# Phase 9.1 — Selector-driven next frame within current engine

**Status:** Acceptance criteria for first implementation step  
**Scope:** Orchestration/server selector only; Phase 6 runtime and builder unchanged.

---

## 1. Goal

Implement the smallest safe version of selector-driven next question: the UI can request "next question" with minimal conversation state; the server chooses the next frame **within the current engine only**, in **deterministic** order, excluding recently used frames; the UI renders the response using the existing path. No engine switching, no auto-advance.

---

## 2. Requirements

### 2.1 UI

- Sends `next_question: true` and minimal `conversation_state` when the user requests the next question.
- Minimal state sent:
  - `session_id`
  - `current_engine`
  - `last_partner_frame_id`
  - `recent_frame_ids` (array of frame_ids)
- Uses a **visible "Next" button** (or equivalent action) for the first pass — **no auto-advance**.
- On response, renders the returned frame and options using the **current** render path (same as after Run Turn).
- Tracks and sends state: after each turn (Run Turn or Next), updates `current_engine`, `last_partner_frame_id`, and `recent_frame_ids` from the response so the next request has correct state.

### 2.2 Server (orchestration)

- When `next_question: true` and `conversation_state` are present:
  - **Selector:** Choose next frame **within `current_engine` only** (no engine switching).
  - **Deterministic:** Frames for the engine in a **stable order** (e.g. by frame_id); choose the **first valid** frame in that order.
  - **Exclude:** Remove any frame_id in `recent_frame_ids` from the candidate set.
  - If all frames in the engine are in `recent_frame_ids`, fallback: choose first in stable order (allow repeat rather than dead-end).
- Returns the **existing** frame + options response shape (same as current `/api/run_turn` when `frame_id` is provided).
- When `next_question` is not set, behaviour unchanged: use `frame_id` (and `engine_id`) from payload as today.

**Fallback ladder (selector tiers):**

1. **Tier 1:** Same engine, excluding `recent_frame_ids`; first valid in stable order.
2. **Tier 2:** If empty, same engine allowing older frames (repeats); first in stable order.
3. **Tier 3:** If still empty (engine has no frames in data), one safe fallback frame so the server never returns 400 (e.g. global first frame by id).

Selector is structured so a bridge tier can be inserted after tier 2. **Phase 9.2** implements that tier (see `PHASE9_2_BRIDGE_TIER.md`).

### 2.3 Constraints

- **Phase 6 runtime:** Unchanged. No change to `engine.process_turn`, injected data, or runtime artifacts.
- **Builder:** Unchanged.
- **No random selection** in the first pass.
- **No engine switching** in the first pass.

---

## 3. Acceptance criteria (checklist)

- [ ] **Next button** visible in the UI (e.g. next to Run Turn or in the current-turn area); no auto-advance.
- [ ] **Next click** sends `POST /api/run_turn` with `next_question: true` and `conversation_state` containing `session_id`, `current_engine`, `last_partner_frame_id`, `recent_frame_ids`.
- [ ] **Server:** For such requests, server selects next frame **only** from frames whose `engine` equals `current_engine`; selection is **deterministic** (stable order, first valid); `recent_frame_ids` are excluded; fallback to first in order if all recent.
- [ ] **Server:** Response shape is unchanged (e.g. `frame_id`, `engine_id`, `frame_text`, `options`, `result`, etc.).
- [ ] **UI:** After response, frame sentence and options render as they do after Run Turn; transcript can show the new partner question.
- [ ] **UI:** After any turn (Run Turn or Next), UI updates internal state so the next "Next" request sends correct `current_engine`, `last_partner_frame_id`, and `recent_frame_ids`.
- [ ] **Runtime and builder:** No modifications; Phase 6 lock respected.

---

## 4. Out of scope for 9.1

- Engine switching (stay in current engine only).
- Auto-advance (user must click Next).
- Random or scored selection (deterministic first-valid only).
- Capability, memory, energy, persona.

---

*Criteria defined for Cursor implementation; one small step, then stop for review.*
