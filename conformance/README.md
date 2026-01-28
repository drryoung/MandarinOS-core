# MandarinOS Trace Conformance Runner

Ensures all traces pass conformance validation.

## Usage

```bash
python -m conformance.run_trace_conformance [base_path]
```

If `base_path` is omitted, defaults to the workspace root.

## Output

```
=== PASS TRACES ===
✓ 001_high_to_low_with_hints.json (PASS as expected)
...

=== FAIL TRACES ===
✓ 001_dead_state_after_scaffold.json (FAIL as expected: DEAD_STATE_NO_FORWARD_PATH)
...

==================================================
Results: 12/12 passed
==================================================
```

## Exit Codes

- **0**: All fixtures passed conformance (pass traces passed, fail traces failed with expected codes)
- **1**: One or more fixtures failed conformance
