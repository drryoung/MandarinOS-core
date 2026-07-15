<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class C: Historical or contextual documentation**
>
> - **Current use:** Retained as the historical version-one Trace contract and as context for an earlier diagnostics and observability design.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current diagnostic, session-capture, review, and scorecard code together with the applicable R2 architecture, state, and test documents.
> - **Principal caution:** The word `CONTRACT` in this filename does not make this a current behavioural contract. Trace was replaced by later scorecard and Session Intelligence mechanisms, and every present diagnostic behaviour must be verified against current code.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS TurnState Trace Contract v1

**Integration Guide for Full App Repositories**

---

## Overview

This document describes the canonical trace format that any **full app repository MUST emit** to enable MandarinOS-core to validate real integration behavior:

- Scaffolding transitions (HIGH → MED → LOW)
- Hint cascade continuity across input mode toggles
- Affordance preservation
- No "dead states" or single-answer teaching

**Success metric:** Core CI can reject pulls that violate the contract without needing screenshots or manual QA.

---

## What is a Trace?

A **Trace** is a JSON document representing a sequence of conversation states and transitions **captured at runtime from the full app**. It is **NOT**:
- UI screenshots
- Database dumps
- Event logs with flattened schemas

It **IS**:
- A sequence of (event, before-state, after-state) tuples
- Full TurnState capture (options, hints, affordances, slots)
- Structured, queryable data that validates against `TurnStateTrace.schema.json`

---

## Trace Structure (Quick Reference)

### Top-level Trace object

```json
{
  "trace_version": "1.0",
  "trace_id": "trace_abc123",
  "created_at": "2026-01-28T10:00:00Z",
  "app_build": {
    "repo": "full-app",
    "commit": "abc1234567",
    "env": "dev"
  },
  "locale": "zh-CN",
  "user_profile": {
    "user_id": "anon_user_001",
    "level": "BEGINNER"
  },
  "scenario": {
    "scenario_id": "introduce_yourself",
    "description": "User introduces themselves in a conversation",
    "initial_task_id": "task_intro_name"
  },
  "steps": [ TraceStep, ... ]
}
```

### TraceStep object

```json
{
  "step_id": "step_001",
  "event": {
    "type": "USER_SELECT_OPTION",
    "timestamp": "2026-01-28T10:00:01Z",
    "payload": { "option_id": "opt_frame_job" }
  },
  "before": TurnState,
  "after": TurnState
}
```

### TurnState object (Minimal Required Fields)

```json
{
  "turn_id": "turn_001",
  "scaffolding_level": "HIGH",
  "input_mode": "TAP",
  "affordances": ["what_can_i_say", "open_hint", "select_option"],
  "options": [
    {
      "option_id": "opt_frame_job",
      "option_kind": "FRAME_WITH_SLOTS",
      "frame_id": "frame.work.job",
      "text_zh": "我是{JOB}。",
      "required_slots": ["JOB"],
      "slot_selectors": {
        "JOB": ["医生", "老师", "工程师"]
      }
    }
  ],
  "hints": null,
  "slots": {
    "required": ["JOB"],
    "filled": {},
    "selectors_present": ["JOB"]
  },
  "diagnostic": {
    "mode": "conversation",
    "confidence": null
  }
}
```

---

## Key Concepts

### Affordances

**Must always include** (when applicable):
- `"what_can_i_say"` — action button/hint to explore valid responses
- `"open_hint"` — hint affordance if `hints.available == true`
- `"select_option"` — tap-mode option selection UI
- `"submit_response"` — type-mode submission UI

**Scaffold narrowing may reduce options but NOT remove affordances.**

### Options

Options represent selectable responses. For tap input mode, **must always have >= 3 options** unless hints are available.

**Critical:** If an option has `required_slots`, it must include:
- `tokens` (array of token objects with slot metadata), OR
- `slot_selectors` (map of slot → candidate values)

**Do NOT flatten:** Never replace a frame-with-slots option with a single filled-in sentence as the only choice.

### Hints

If `hints.available == true`:
- `payload` must include an `effects` object (non-null, non-empty)
- `effects` describes what the hint changes: `narrow`, `structure`, `model`, etc.
- `cascade_state_key` preserves hint state across input mode toggles and scaffolding changes

### Slots

Track required slots and what's been filled:
- `required`: list of slot names needed for this turn
- `filled`: map of slot name → filled value (e.g., `"JOB": "医生"`)
- `selectors_present`: list of slots that have UI affordances (dropdowns, etc.)

---

## How to Export Traces

### 1. Capture State at Key Events

In your app, wrap every user interaction and system change in a trace capture:

```typescript
// Pseudocode example
async function handleUserSelectOption(optionId: string) {
  const beforeState = captureCurrentTurnState();
  
  const event: TraceEvent = {
    type: "USER_SELECT_OPTION",
    timestamp: new Date().toISOString(),
    payload: { option_id: optionId }
  };
  
  // Process the selection (update engine state, etc.)
  await processSelection(optionId);
  
  const afterState = captureCurrentTurnState();
  
  traceSteps.push({
    step_id: `step_${stepCounter++}`,
    event,
    before: beforeState,
    after: afterState
  });
}
```

### 2. Preserve Raw Engine Output

Do **NOT** flatten options or discard hint effects when mapping from internal engine to UI:

```typescript
// ❌ BAD: flattens slots
const displayOption = {
  text: "我是医生。"  // Lost slot structure!
};

// ✅ GOOD: preserves structure
const displayOption = {
  text_zh: "我是{JOB}。",
  option_kind: "FRAME_WITH_SLOTS",
  frame_id: "frame.work.job",
  required_slots: ["JOB"],
  slot_selectors: {
    JOB: ["医生", "老师", "工程师"]
  }
};
```

### 3. Export as JSON

At the end of a conversation or session:

```typescript
const trace: TurnStateTrace = {
  trace_version: "1.0",
  trace_id: generateUUID(),
  created_at: new Date().toISOString(),
  app_build: {
    repo: "my-mandarin-app",
    commit: process.env.GIT_COMMIT,
    env: process.env.NODE_ENV
  },
  locale: "zh-CN",
  user_profile: {
    user_id: anonymizedUserId(),
    level: userLevel
  },
  scenario: {
    scenario_id: currentScenario.id,
    description: currentScenario.name,
    initial_task_id: currentScenario.tasks[0]?.id || null
  },
  steps: traceSteps
};

fs.writeFileSync(
  `traces/trace_${trace.trace_id}.json`,
  JSON.stringify(trace, null, 2)
);
```

### 4. Run Conformance in CI

```bash
# In your full app's CI pipeline
python -m conformance.run_trace_conformance /path/to/exported/traces

# Exit code 0 = all traces valid
# Exit code 1 = one or more traces violate contract
```

---

## Hard Gates (Non-negotiable Checks)

### Gate 1: Schema Validity
- Entire trace must validate against `TurnStateTrace.schema.json`
- **Error:** `TRACE_SCHEMA_INVALID`

### Gate 2: Forward-Path Guarantee
- Every AFTER state must have at least one forward path:
  - Non-empty `options` (>= 1 option), OR
  - Slot-fill path (required slots with selectors), OR
  - Hints available + "open_hint" affordance
- **Error:** `DEAD_STATE_NO_FORWARD_PATH`

### Gate 3: Affordance Preservation on Toggle
- TOGGLE_INPUT_MODE events must preserve:
  - `"what_can_i_say"`
  - `"open_hint"` (if hints were available before toggle)
- **Error:** `TOGGLE_AFFORDANCE_DROP`

### Gate 4: Scaffolding Non-Amputation
- Scaffolding changes (HIGH → MED → LOW) must NOT remove:
  - `"what_can_i_say"`
  - `"open_hint"` (if user is uncertain)
- **Error:** `SCAFFOLDING_AFFORDANCE_DROP`

### Gate 5: Hint Effects
- If `hints.available == true`, `payload.effects` must be non-empty
- Hints must not reveal a single "teacher correction" as the only option
- **Errors:** `HINT_NO_EFFECTS_BLOCK`, `TEACHER_SINGLE_ANSWER`

### Gate 6: No Flattened Options
- Options with `required_slots` must have `tokens` or `slot_selectors`
- Slots must be executable (not abstract)
- **Errors:** `CONTRACT_OPTION_FLATTENED`, `CONTRACT_SLOT_UNEXECUTABLE`

---

## Event Types (Standard Enum)

- `USER_SELECT_OPTION` — user tapped/selected an option
- `USER_FILL_SLOT` — user filled a slot (e.g., typed a name)
- `USER_UNCERTAIN` — user clicked "uncertain" / "help" button
- `OPEN_HINT` — user opened hint panel
- `ADVANCE_HINT` — hint step advanced (user clicked "next" on hint)
- `TOGGLE_INPUT_MODE` — user switched TAP ↔ TYPE
- `SYSTEM_REPROMPT` — engine re-prompted the user
- `SYSTEM_NARROW` — engine narrowed options (HIGH → MED → LOW)
- `SYSTEM_MODEL` — engine showed a model/teaching exchange
- `SYSTEM_STRUCTURE` — engine clarified the frame/structure
- `END_TURN` — turn ended (user advanced or timed out)

---

## Testing Locally

### Run Conformance on Golden Traces

```bash
cd /path/to/MandarinOS-core
python conformance/run_trace_conformance.py

# Expected output:
# === PASS TRACES ===
# ✓ 001_high_to_low_with_hints.json (PASS as expected)
# ...
# === FAIL TRACES ===
# ✓ 001_dead_state_after_scaffold.json (FAIL as expected: DEAD_STATE_NO_FORWARD_PATH)
# ...
# ==================================================
# Results: 12/12 passed
# ==================================================
```

### Export and Validate Your App's Traces

```bash
# In your app
npm run export-traces
python /path/to/MandarinOS-core/conformance/run_trace_conformance.py ./exported_traces
```

---

## Troubleshooting

### `DEAD_STATE_NO_FORWARD_PATH`
**Problem:** Your turn state has no options, no slot-fill path, and no hints.  
**Fix:** Ensure every AFTER state either:
- Generates >= 1 option, OR
- Provides a slot-fill UI (selectors), OR
- Has `hints.available == true` + "open_hint" affordance

### `TOGGLE_AFFORDANCE_DROP`
**Problem:** Input mode toggle removed "open_hint" or "what_can_i_say".  
**Fix:** When toggling TAP ↔ TYPE, preserve affordances that existed before the toggle.

### `CONTRACT_OPTION_FLATTENED`
**Problem:** You have a frame option with `required_slots` but no `tokens` or `slot_selectors`.  
**Fix:** Either:
- Include `slot_selectors` (map of slot → candidates), OR
- Include `tokens` (array of token objects), OR
- Fill the slots and change `option_kind` to `FRAME` (not `FRAME_WITH_SLOTS`)

### `HINT_NO_EFFECTS_BLOCK`
**Problem:** `hints.available == true` but `payload.effects` is empty.  
**Fix:** Ensure `payload` includes a non-empty `effects` object describing what changed (e.g., `"narrow"`, `"structure"`, `"model"`).

---

## Full Example: Complete Trace

See `golden/traces/v1/pass/001_high_to_low_with_hints.json` for a complete example.

---

## Questions?

Refer to:
- `schemas/TurnStateTrace.schema.json` — authoritative JSON schema
- `docs/mandarinos_design_constitution.txt` — product constraints
- `golden/traces/v1/pass/` — working examples
- `golden/traces/v1/fail/` — anti-patterns to avoid
