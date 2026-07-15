# Phase 9.2 — Bridge tier (engine switching)

**Status:** Implemented  
**Scope:** Orchestration selector only; Phase 6 runtime and builder unchanged.

---

## 1. Goal

Enable **engine switching** via a bridge tier in the next-frame ladder: after at least 2 turns in the current engine, the selector may choose a frame from a **bridge target** engine so conversation can continue across topics.

---

## 2. Behaviour

- **When:** Bridge tier runs only when **tier 1 and tier 2** (same engine, exclude recent; same engine allow repeats) have already been applied. We then try bridge only if `len(recent_frame_ids) >= 2` (at least 2 turns in session).
- **How:** `_select_next_frame_bridge(current_engine, recent_frame_ids)` uses a fixed map `_BRIDGE_TARGETS`: for each engine, a list of target engines we can bridge to (from conversation specs). For each target engine (in order), we take frames in stable order, exclude `recent_frame_ids`, and return the first valid frame. If none, return `None` and fall through to tier 3.
- **Deterministic:** No random choice; first valid frame from first target engine that has one.
- **Response:** When the chosen frame is from a bridge, the server returns that frame’s **engine** in the response so the UI updates `current_engine` and subsequent “Next” requests stay in the new engine.

---

## 3. Bridge targets (minimal map)

| Current engine | Bridge targets (order) |
|----------------|------------------------|
| identity       | place, family, work    |
| place          | identity, family, travel |
| family         | identity, place, work |
| work           | identity, place, family |
| hobby          | identity, travel      |
| travel         | place, hobby           |
| life           | identity, place, family |

Extend `_BRIDGE_TARGETS` in `scripts/ui_server.py` when adding engines or changing topology.

---

## 4. Acceptance

- [ ] After 2+ turns in one engine, clicking **Next** can return a frame from a different engine (bridge).
- [ ] UI transcript and state show the new question and `current_engine` updates to the new engine.
- [ ] Next “Next” uses the new engine (tier 1/2 in that engine).
- [ ] No change to Phase 6 runtime or builder.

---

*Phase 9.2 follows Phase 9.1; bridge tier inserted after tier 2 in the ladder.*
