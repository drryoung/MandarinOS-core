<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as the Phase 10 technical proposal and as historical context for ideas considered during that phase.
> - **May guide current implementation:** No.
> - **Current authority:** Verified production code and the applicable documents in the nine-document R2 architecture-governance package.
> - **Principal caution:** A technical proposal is not evidence that its components, boundaries, or behaviours were implemented. Every proposed element must be independently verified against current code and the approved R2 documents.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Phase 10 — Memory + Persona Foundations: Technical Proposal

**Status:** **Approved and closed.** Scope delivered: learner memory capture, persistence by learner_id, memory-aware selector suppression, persona data, persona-aware dialogue stubs, and cross-session continuity. Known follow-up: response-option quality / frame–option alignment (polish; does not block sign-off). Deferred to later phases: recall mode, capability map, energy model, repair logic, selector scoring, and broader adaptive intelligence.  
**Authoritative roadmap:** `docs/project/MandarinOS_project_plan_v2.md`  
**Phase 6 lock:** `docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md` — engine.process_turn, runtime artifacts, runtime schemas, and trace contract remain unchanged.

This document answers the deliverable requested from Cursor before coding: files to be added/modified, schemas, persistence, selector behaviour, contract/state additions, and explicit Phase 11 deferrals.

---

## 0. Approved adjustments (post-approval)

1. **Persistence key:** Use **learner_id** (not session_id) for persistence keys. Client sends learner_id; server loads/saves learner memory keyed by learner_id.
2. **Client never sends learner_memory:** Server is the single authority for learner memory. Client must not send learner_memory in requests; server may include a learner_memory snapshot in the response for display only.
3. **Fact-capture in dedicated module:** All fact-capture logic (mapping frame_id + option/text → learner memory fields) lives in **scripts/learner_memory_capture.py**, not in ui_server.
4. **Recall via explicit recall frames:** Recall is implemented using **explicit recall frames** (concrete frame_ids in frames data), not by filling text templates.
5. **Selector suppression allows recall after interval:** Suppression of “ask for fact X” is not permanent. After an **interval** (e.g. N turns since that question was last asked), the selector may again choose the frame that asks for that fact (intentional recall). Track “last turn when we asked for field F” and allow the question again once the interval has passed.

---

## 1. Files to be added or modified

### 1.1 New files (add)

| File | Purpose |
|------|---------|
| `scripts/learner_memory.py` | Learner memory schema, in-memory store, load/save to persistence file. No dependency on runtime/engine.py. |
| `scripts/learner_memory_capture.py` | Fact-capture logic only: map frame_id + selected option (or submitted text) to learner_memory fields. Called by ui_server after a turn; returns updates to apply. No persistence. |
| `scripts/persona_data.py` | Persona schema and 1–2 built-in persona profiles (persona_id, name, hometown, lives_in, occupation, interests, favourite_food). Read-only data. |
| `data/learner_memory.json` (or `runtime/phase10_learner_memory.json`) | Persistence file for learner memory keyed by **learner_id**. Created when first write occurs; path configurable. |

**Rationale:** Keep memory, capture, and persona in separate modules; ui_server remains the single HTTP entry point. Persistence uses **learner_id** only. Client never sends learner_memory; server is authoritative.

### 1.2 Modified files (minimal changes)

| File | Changes |
|------|----------|
| `scripts/ui_server.py` | (1) Import learner_memory, learner_memory_capture, and persona_data. (2) On POST /api/run_turn: load learner_memory by **learner_id** (required for persistence); load persona by persona_id; pass learner_memory + persona into selector. (3) After a response turn: call learner_memory_capture to get updates from frame_id + selected_option/text; apply updates and persist by learner_id. (4) Selector: suppress “ask for fact” frames only when fact is set **and** interval since last ask has not passed; allow recall after interval; use **explicit recall frames** (frame_ids) for recall turns, not text templates. (5) Add request/response fields per §6. Client never sends learner_memory. |
| `ui/app.js` | (1) Send **learner_id** and persona_id (and session_id if needed for other uses) in conversation_state or top-level. **Do not send learner_memory.** (2) Send response_mode and hint_level_reached when submitting (optional). (3) If server returns turn_type or learner_memory snapshot, use for display only; no change to trace contract. |

**No changes to:**

- `runtime/engine.py` (process_turn)
- Any file under `runtime/` that is a Phase 6 artifact (e.g. frame_render_tokens.runtime.json, cards_index.runtime.json, frame_options.runtime.json) — we do not change their schema or regeneration.
- `docs/design/TRACE_CONTRACT_v1.md` and existing trace event shapes.
- Builders in `tools/` that produce Phase 6 runtime artifacts (unless we add a separate Phase 10 persistence path that is not a “runtime artifact” in the Phase 6 sense).

---

## 2. Learner memory schema

**Scope:** Minimal explicit learner memory only. No inference, no emotional state, no broad user modelling.

**Fields (all optional, string or null):**

```json
{
  "learner_name": null,
  "hometown": null,
  "lives_in": null,
  "job_or_study": null,
  "family": null,
  "favourite_food": null
}
```

**Rules:**

- Store only when we have an explicit fact (e.g. user selected “我叫 Raymond” or typed “Raymond” in a name slot; user selected “我是新西兰人” → hometown or lives_in).
- Do not infer “learner seems tired” or “low energy”; do not store inferred traits.
- Keys match the briefing and v2 plan exactly: `learner_name`, `hometown`, `lives_in`, `job_or_study`, `family`, `favourite_food`.

**In-memory shape (Python):**

- Single dict per “learner” or per session: `Dict[str, Optional[str]]` with exactly these six keys.
- Persistence: one JSON file; top-level keyed by **learner_id**. Example: `{ "learner_001": { "learner_name": "Raymond", "hometown": null, ... } }`.
- **Capture logic** lives in `scripts/learner_memory_capture.py` (see §1.1). ui_server calls it after a turn; it returns a dict of field updates to apply.

**Capture rules (Phase 10 minimal, implemented in learner_memory_capture.py):**

- Map “name” frames (e.g. f_ask_you_name answer, or frame that expects 我叫 X) → `learner_name`.
- Map “origin/live” frames (e.g. f_from_where, frame.location.live_question) → `hometown` / `lives_in` by frame_id.
- Map “work” frame (f_what_work) → `job_or_study`.
- Map “family” frames (f_have_family, f_have_siblings) → `family`.
- Map “food” frame (e.g. f_food_what_good answer) → `favourite_food`.
- Capture only when the user has selected an option or submitted text that we can map unambiguously to one field; do not overgeneralize from free text.

---

## 3. Persona schema

**Minimum Phase 10 persona model (per briefing):**

- `persona_id` (string, stable id)
- `persona_name` (string)
- `hometown` (string)
- `lives_in` (string)
- `occupation` (string)
- `interests` (string or short list; e.g. "reading, travel")
- `favourite_food` (string)

**Implementation:**

- In `scripts/persona_data.py`: define a list or dict of 1–2 personas. Example:

```python
PERSONAS = [
    {
        "persona_id": "zhang_wei",
        "persona_name": "张伟",
        "hometown": "苏州",
        "lives_in": "上海",
        "occupation": "老师",
        "interests": "看书、旅游",
        "favourite_food": "小笼包",
    },
    # optional second persona
]
```

- No persona network yet (no relationships, no graph). Just 1–2 flat profiles for selector and for persona-consistent stubs (e.g. probe response “嗯，因为我很喜欢。” could become “嗯，因为我很喜欢小笼包。” when persona has favourite_food).

**Usage:**

- Request carries `persona_id` (default to first persona if missing). Server loads that persona and passes it to the selector and to any persona-specific response logic (e.g. stub text).

---

## 4. Persistence mechanism

- **What is persisted:** Learner memory only (the six fields keyed by **learner_id**).
- **Where:** Single JSON file, e.g. `data/learner_memory.json` or `runtime/phase10_learner_memory.json`. Prefer `data/learner_memory.json` so we do not mix with Phase 6 runtime artifacts.
- **Format:** `{ "<learner_id>": { "learner_name": "...", ... }, ... }`.
- **When:** Read at start of a turn when we have learner_id; write after a turn when learner_memory was updated (after capture in learner_memory_capture.py).
- **Thread safety:** Single-threaded server; one write per request. No locking in Phase 10.
- **Scope:** Local only. Cross-session continuity: client sends the same **learner_id** across sessions so the same JSON key is used.

---

## 5. Selector changes

**Location:** Selector logic lives in `scripts/ui_server.py` (e.g. `_select_next_frame_ladder`, `_select_next_frame_bridge`). All Phase 10 selector changes are in ui_server and the new modules it calls.

**Allowed new behaviours (Phase 10 only):**

1. **Suppress re-asking known facts, but allow recall after interval**  
   When building the list of candidate frames, **suppress** a frame that asks for a learner_memory field that is already set **only if** we have asked for that fact recently (within the last N turns). After an **interval** (e.g. N turns or N frames since that question was last asked), the selector may again choose that frame (intentional recall).  
   - Track “last turn index (or frame count) when we asked for field F” (e.g. when we asked f_ask_you_name, record that we “asked for learner_name” at turn T).  
   - Suppression rule: exclude frame if (field F is set **and** turns since last ask for F < interval).  
   - Recall rule: once interval has passed, the frame is allowed again so the partner can intentionally ask “你叫什么名字？” again.  
   - Mapping: frame_id → learner_memory field (f_ask_you_name → learner_name, f_from_where → hometown, etc.) as above.

2. **Recall via explicit recall frames**  
   Recall is implemented using **explicit recall frames** (concrete frame_ids in the frame set), not by filling text templates.  
   - Define one or more recall frames (e.g. in p1_frames.json or a Phase 10 list) whose text explicitly references a stored fact (e.g. “你还喜欢{X}吗？” as a fixed frame with slot, or a fixed “你刚才说你来自{X}，常回去吗？”).  
   - Selector may choose a recall frame_id when memory has content and we want a recall turn; the frame’s text is rendered using stored learner_memory (e.g. slot fill from memory). No ad-hoc string formatting in the selector; all recall content comes from explicit frames.

3. **Persona-consistent dialogue**  
   When returning a stub (e.g. probe response or a short persona statement), use persona’s name, hometown, occupation, or favourite_food in the stub text where appropriate. No change to frame selection logic beyond the above; only to the text we return for probe_response or for a future “persona_reveal” turn type.

**Known limitation (post–Step 7):** Response options for the latest questions are sometimes not appropriate (frame–option fit / content quality). Follow-up: option set review or per-question refinement in a later phase.

**Do not add in Phase 10:**

- Weighted scoring of candidates.
- Capability-driven difficulty.
- Fatigue or energy.
- Repair state or repair ladder.
- Content-driven steering (signal extraction from learner text to switch engine).
- Inferred emotion or intent.

---

## 6. Exact request / response / state fields to add now

**Request (POST /api/run_turn) body — additive only:**

| Field | Where | Type | Purpose |
|-------|--------|------|---------|
| `persona_id` | Top-level or conversation_state | string, optional | Which persona is the partner; default to first persona if missing. |
| `learner_id` | Top-level or conversation_state | string | **Required** for persistence. Server loads/saves learner memory keyed by learner_id. |
| `session_id` | conversation_state | string, optional | May still be sent for other uses (e.g. trace); not used as persistence key. |
| `response_mode` | Top-level, optional | string | One of: `free_speech` \| `assisted_selection` \| `repair_supported` \| `no_response`. Sent by client when submitting. |
| `hint_level_reached` | Top-level, optional | number or string | 0–4 or similar; sent by client when submitting; not used by selector in Phase 10. |

**Client must never send learner_memory.** Server is the single authority; server loads learner_memory from persistence by learner_id.

**Conversation state (existing + additive):**

- Existing: `current_engine`, `last_partner_frame_id`, `recent_frame_ids`, `prefer_bridge`, `force_bridge`, `last_turn_was_answer`.
- Add: `learner_id` (required for memory). Add: `persona_id` (optional) if not top-level.
- **Do not** add client-sent learner_memory; server never uses client-supplied memory.

**Response (additive only):**

| Field | Type | Purpose |
|-------|------|---------|
| `turn_type` | string, optional | One of: `question` \| `follow_up` \| `recall` \| `persona_reveal` \| `bridge`. Allows client/trace to distinguish; no change to trace schema. |
| `learner_memory` | object, optional | Snapshot of the six learner memory fields after this turn (if updated or if client needs it). Client may show “You said you’re from X” or store for next request. |
| `persona_id` | string, optional | Echo of the persona used for this turn. |

**State (server-side, not necessarily in response):**

- In-memory: learner_memory dict for current learner_id; current persona dict; optional “last ask” turn index per memory field (for interval-based recall).
- Persistence: learner_memory keyed by **learner_id** only.

No change to existing response fields (frame_id, frame_text, options, etc.); they remain as today.

---

## 7. Explicitly deferred to Phase 11

The following will **not** be implemented in Phase 10:

- **Capability map** — Per-engine or per-move capability scores; any tracking of comprehension, recall, speaking confidence, topic familiarity.
- **Energy model** — Hint usage, response latency, response completeness, conversation length as signals; fatigue or engagement state.
- **Repair ladder / repair state** — STABLE → STRUGGLING → REPAIR_ACTIVE → RECOVERED; repair-state-driven selector behaviour.
- **Selector scoring engine** — Weighted scoring over candidates (comprehensibility, relevance, interest, learning, stretch); difficulty bands; hint-aware adjustment.
- **Content-driven steering** — Extracting signals from learner free text to choose engine or branch (e.g. “我在上海工作” → Place engine).
- **Inferred emotion or intent** — Any storage or use of “learner seems tired”, “low energy”, or similar.
- **Full adaptive intelligence** — Dynamic difficulty adaptation, fatigue-aware steering, capability-driven question choice.
- **Large persona network** — More than 1–2 personas; relationships between personas; persona graph.
- **Changes to Phase 6 runtime** — No changes to `runtime/engine.py`, `engine.process_turn`, runtime artifacts, runtime schemas, or trace contract.

---

## 8. Implementation order (per briefing)

1. **Step 1.** Define and implement learner memory schema (in `scripts/learner_memory.py` + in-memory store; no persistence yet).
2. **Step 2.** Implement fact-capture in `scripts/learner_memory_capture.py`; call from ui_server after a response turn to get updates; apply to learner_memory and (after Step 3) persist by learner_id.
3. **Step 3.** Add simple persistence keyed by **learner_id** (read/write `data/learner_memory.json` from learner_memory module).
4. **Step 4.** Define persona schema and add 1–2 personas (in `scripts/persona_data.py`).
5. **Step 5.** Make selector memory-aware: suppression of “ask for fact” frames when fact set and within interval; allow recall after interval; use explicit recall frames (no text templates).
6. **Step 6.** Make selector persona-aware (persona_id in request; persona-consistent stubs/reveals).
7. **Step 7.** Demonstrate cross-session continuity (same learner_id across sessions; second run skips name or shows recall).
8. **Step 8.** Stop for strategist review.

---

## 9. Summary

| Item | Proposal |
|------|----------|
| **Files added** | `scripts/learner_memory.py`, `scripts/learner_memory_capture.py`, `scripts/persona_data.py`, persistence file (e.g. `data/learner_memory.json`). |
| **Files modified** | `scripts/ui_server.py`; `ui/app.js` (send learner_id, persona_id; **never** send learner_memory; optional response_mode, hint_level_reached). |
| **Learner memory schema** | Six optional fields: learner_name, hometown, lives_in, job_or_study, family, favourite_food. Stored per **learner_id**. Capture in learner_memory_capture.py only. |
| **Persona schema** | persona_id, persona_name, hometown, lives_in, occupation, interests, favourite_food. 1–2 personas in code. |
| **Persistence** | Single JSON file keyed by **learner_id**; learner memory only; server authoritative; client never sends learner_memory. |
| **Selector** | Suppress “ask for fact” frame only when fact set and within interval; allow recall after interval; use **explicit recall frames** (no text templates); persona-consistent stubs. |
| **Contract/state** | Add: learner_id (required for memory), persona_id, response_mode, hint_level_reached; turn_type (optional); learner_memory in **response** only (server → client for display). |
| **Deferred** | Capability map, energy model, repair ladder, selector scoring, content steering, inferred state, full adaptive intelligence, large persona network; Phase 6 runtime unchanged. |

---

*Approved with five adjustments (§0). Phase 10 implementation has begun.*
