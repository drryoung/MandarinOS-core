# Integration Kit: Trace Export & Validation v1

This kit enables full-app repositories to **instrument trace capture, validate conformance locally, and integrate with CI** to guarantee MandarinOS contract compliance.

## What Is This Kit?

The integration kit provides:

1. **JSON Schemas** (`schemas/`): Canonical trace format
2. **Example Traces** (`examples/`): Reference implementations of all 6 required scenarios
3. **TypeScript Capture Patterns** (`ts_exporter_snippets/`): Framework-agnostic pseudocode for trace export
4. **Validation Scripts** (`../scripts/`): Local validation (bash/PowerShell) + Python conformance runner

**Goal**: Enable your full app to export traces that guarantee all 9 MandarinOS constraints are met.

---

## Quick Start: Export & Validate

### Step 1: Export Traces from Your App

Use the `TraceBuilder` class (from `ts_exporter_snippets/trace_exporter.ts`) to capture state transitions:

```typescript
// In your React component or framework handler:
import { TraceBuilder, ITraceExporter } from './trace_exporter';
import { buildTurnState, validateForwardPath } from './capture_helpers';

const tracer = new TraceBuilder('my_session_id', 'v1.0.0', 'S1_basic_slot_fill');

// Before/after capture:
tracer.step(
  { type: 'USER_SELECT_OPTION', option_id: 'frame_001' },
  buildTurnState({ /* before state */ }),
  buildTurnState({ /* after state */ })
);

// Export to file
await tracer.exportToFile('./traces/my_trace.json');
```

**Critical**: See [Capture Checklist](#capture-checklist) below—do NOT flatten structured options.

### Step 2: Validate Locally

**Bash** (macOS / Linux):
```bash
./scripts/validate_traces.sh ./traces
```

**PowerShell** (Windows):
```powershell
.\scripts\validate_traces.ps1 -Path .\traces
```

**Expected output**:
```
✓ Trace: traces/scenario_S1_basic_slot_fill.json
  - TurnStateTrace schema: PASS
  - Gate 1 (Turn option invariant): PASS
  - Gate 2 (Forward-path guarantee): PASS
  - Gate 3 (Affordances): PASS
  - Gate 4 (Slot executability): PASS
  - Gate 5 (Hint effects): PASS
  - Gate 6 (No flattening): PASS
  Exit code 0
```

### Step 3: Integrate with CI

Add to your GitHub Actions workflow:

```yaml
- name: Validate MandarinOS Traces
  run: ./scripts/validate_traces.sh ./traces
  # or on Windows: .\scripts\validate_traces.ps1 -Path .\traces

- name: Comment PR on validation failure
  if: failure()
  uses: actions/github-script@v7
  with:
    script: |
      github.rest.issues.createComment({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        body: '❌ Trace validation failed. See logs for details.'
      })
```

---

## Capture Checklist

Before exporting traces, ensure each `TurnState` includes:

- [ ] `turn_id`: unique string for this turn
- [ ] `scaffolding_level`: "HIGH" | "MED" | "LOW"
- [ ] `input_mode`: "tap" | "type"
- [ ] `affordances`: array of available affordance strings
  - [ ] Always includes `"what_can_i_say"`
  - [ ] Includes `"open_hint"` if hints available
  - [ ] Includes mode-appropriate actions (`"select_option"` for tap, `"submit_response"` for type)
- [ ] `options`: array of option objects (if `input_mode == "tap"`)
  - [ ] **Each option with `required_slots` has `tokens` OR `slot_selectors` (not flattened)**
  - [ ] One gold option present matching target frame/intent
  - [ ] >= 3 options total (or scaffolding justifies fewer)
- [ ] `hints.available`: true if hints shown
  - [ ] `hints.payload.cascade_state_key`: consistent across cascade
  - [ ] `hints.payload.effects`: non-empty object (not `{}`)
    - Must have one of: `narrow`, `structure`, `model`, or other action key
- [ ] `slots.required`: frame-required slot names
- [ ] `slots.filled`: names of slots user has filled
- [ ] `slots.selectors_present`: true if slot selector UI shown
- [ ] `diagnostic`: (if in diagnostic mode)
  - [ ] `mode`: "diagnostic"
  - [ ] `confidence`: "HIGH" | "MED" | "LOW"

### What NOT to Do

❌ **DO NOT flatten options**:
```typescript
// WRONG: This loses slot structure
{
  "kind": "FRAME",
  "text": "我叫Alice。",  // FLATTENED — slot tokens are gone!
  "required_slots": ["NAME"]
}

// RIGHT: This preserves slot executability
{
  "kind": "FRAME",
  "text": "我叫{NAME}。",
  "required_slots": ["NAME"],
  "tokens": [
    { "type": "text", "value": "我叫" },
    { "type": "slot", "slot_name": "NAME", "value": "Alice" },
    { "type": "text", "value": "。" }
  ]
}
```

❌ **DO NOT drop affordances during scaffolding changes**:
```typescript
// WRONG: HIGH→MED transition loses "open_hint"
{
  "before": { "affordances": ["what_can_i_say", "open_hint", "select_option"] },
  "after": { "affordances": ["what_can_i_say", "select_option"] }  // ❌ Dropped open_hint
}

// RIGHT: Preserve core affordances across scaffolding
{
  "before": { "affordances": ["what_can_i_say", "open_hint", "select_option"] },
  "after": { "affordances": ["what_can_i_say", "open_hint", "select_option"] }  // ✓ Same
}
```

❌ **DO NOT leave hints without effects**:
```typescript
// WRONG: No effects
{
  "hint": "Try: 我叫...",
  "effects": {}  // Empty!
}

// RIGHT: Hints must indicate what they do
{
  "hint": "Try: 我叫...",
  "effects": { "structure": true }  // Shows this is a structure hint
}
```

---

## Error Codes & Recovery

If validation fails, check the error code in the output:

| Code | Meaning | Fix |
|------|---------|-----|
| `TRACE_SCHEMA_INVALID` | Trace JSON does not match TurnStateTrace.schema.json | Validate JSON structure against schemas/ |
| `TURN_OPTION_INVARIANT_FAILED` | >= 3 options or gold missing on tap turn | Add more options or ensure gold is present |
| `DEAD_STATE_NO_FORWARD_PATH` | Turn has no viable exit (no options, no hints, no slots) | Add options, hints, or slot selectors |
| `TOGGLE_AFFORDANCE_DROP` | TAP↔TYPE toggle lost an affordance | Re-capture; preserve affordances across toggles |
| `SCAFFOLDING_AFFORDANCE_DROP` | HIGH→MED→LOW narrowing lost affordance | Preserve "what_can_i_say" at all levels |
| `SLOT_UNEXECUTABLE` | Slot marked required but no selectors present | Add slot.selectors_present or tokens |
| `HINT_NO_EFFECTS_BLOCK` | Hint has empty effects {} | Add actionable effects (narrow, structure, model, etc.) |
| `HINT_NON_ACTIONABLE` | Hint exists but cascade_state_key missing or cascade incomplete | Ensure cascade_state_key present + effects block |
| `CONTRACT_OPTION_FLATTENED` | Option with required_slots missing tokens/slot_selectors | Preserve slot structure; do NOT flatten to plain text |

---

## Example Traces

The `examples/` folder contains three working traces:

1. **example_trace_minimal.json** → `S1_basic_slot_fill`
   - Demonstrates slot preservation across option selection and fill
   - Use this as a template for simple slot-fill scenarios

2. **example_trace_toggle.json** → `S3_toggle_preserves_affordances`
   - Shows TAP ↔ TYPE toggle with affordance preservation
   - Illustrates correct cascade_state_key continuity across mode changes

3. **example_trace_hint_cascade.json** → `S2_hint_narrow_structure_model`
   - Multi-step hint cascade: generic → narrow → structure → model
   - Demonstrates effects blocks and actionable hint progression

**To use as a template**: Copy an example, modify `trace_id`, `app_build`, `run_id`, and event details to match your scenario.

---

## Required Scenarios

Your app MUST export traces for all six required scenarios. See [SCENARIOS_REQUIRED_v1.md](./SCENARIOS_REQUIRED_v1.md) for full details:

- **S1_basic_slot_fill**: Frame slots remain executable
- **S2_hint_narrow_structure_model**: Hint cascade effects are actionable
- **S3_toggle_preserves_affordances**: TAP↔TYPE toggle preserves affordances
- **S4_scaffolding_high_to_low**: Narrowing doesn't amputate affordances
- **S5_narrow_then_slot_integrity**: Narrowing preserves slot executability
- **S6_diagnostic_confidence_changes_no_assessment**: Confidence downgrades don't trigger quiz behavior

---

## Framework Integration Examples

### React (with hooks)

```typescript
// hooks/useTraceCapture.ts
import { TraceBuilder } from './trace_exporter';

export function useTraceCapture(scenarioId: string, appBuild: string) {
  const tracer = useRef(new TraceBuilder(`session_${Date.now()}`, appBuild, scenarioId));
  
  const captureStep = (event, beforeState, afterState) => {
    tracer.current.step(event, beforeState, afterState);
  };
  
  const exportTraces = async (dir: string) => {
    await tracer.current.exportToFile(`${dir}/${scenarioId}.json`);
  };
  
  return { captureStep, exportTraces };
}
```

### Vue / Svelte / Angular

Adapt the React hook pattern to your framework. The key requirement is:
- Intercept turn completion events
- Capture before/after TurnState objects
- Call `tracer.step(event, before, after)`
- Export on session end

See `ts_exporter_snippets/trace_exporter.ts` for the full interface; it is framework-agnostic.

---

## Debugging: Manual Inspection

To inspect a trace manually:

```bash
# Pretty-print a trace
cat traces/my_trace.json | jq .

# Extract just the steps
cat traces/my_trace.json | jq '.steps[]'

# Find traces with dead states
cat traces/my_trace.json | jq '.steps[] | select(.after.options | length == 0 and .after.hints.available == false)'
```

---

## Conformance Runner Details

The conformance runner (`../conformance/run_trace_conformance.py`) applies 6 sequential gates:

1. **Schema**: Trace matches TurnStateTrace.schema.json
2. **Forward-path**: Every turn has a viable exit
3. **Affordances**: Tap/type affordances are correct
4. **Slots**: Required slots are executable (have selectors/tokens)
5. **Hints**: All hints have non-empty effects blocks
6. **Flattening**: No options flatten required_slots

Each gate must pass. If any gate fails, the exit code is 1 and a diagnostic event is emitted.

---

## What's Next?

Once traces are exported and validated:

1. **Commit trace files** to your repo (suggest `traces/scenario_*.json`)
2. **Add trace validation** to your CI/CD pipeline
3. **Link traces in PRs** when UX/scaffolding changes (allows reviewers to inspect turn transitions)
4. **Archive passing traces** as regression test fixtures

---

## Support

- **Questions about scenarios?** See [SCENARIOS_REQUIRED_v1.md](./SCENARIOS_REQUIRED_v1.md)
- **Questions about trace format?** See [TurnStateTrace.schema.json](./schemas/TurnStateTrace.schema.json)
- **Questions about validation?** See [run_trace_conformance.py](../conformance/run_trace_conformance.py)
- **Questions about capture?** See [trace_exporter.ts](./ts_exporter_snippets/trace_exporter.ts)

---

## Files in This Kit

```
integration_kit/
├── README.md (this file)
├── schemas/
│   ├── TurnStateTrace.schema.json
│   ├── TraceStep.schema.json
│   ├── Event.schema.json
│   ├── TurnState.schema.json
│   ├── Option.schema.json
│   ├── Hint.schema.json
│   ├── Effects.schema.json
│   ├── Token.schema.json
│   └── TurnResponse.schema.json
├── examples/
│   ├── example_trace_minimal.json
│   ├── example_trace_toggle.json
│   └── example_trace_hint_cascade.json
└── ts_exporter_snippets/
    ├── trace_exporter.ts
    └── capture_helpers.ts

scripts/
├── validate_traces.sh (bash/Unix/macOS)
└── validate_traces.ps1 (PowerShell/Windows)

docs/
├── SCENARIOS_REQUIRED_v1.md
└── TRACE_CONTRACT_v1.md (reference)
```

---

**Integration Kit v1 Release Date**: 2026-01-25
