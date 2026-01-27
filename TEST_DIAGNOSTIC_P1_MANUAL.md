# Manual Validation Checklist for diagnostic_p1.json

Use this checklist to manually verify diagnostic_p1.json is correct. Each section can be validated using VS Code's Find/Replace or by reading sections of the file.

## Quick Validation Steps

### 1. Check JSON Syntax
- Open diagnostic_p1.json in VS Code
- If no red squiggly lines → **JSON is valid** ✅
- Run: `Edit > Format Document` to auto-format
- Look for any red error indicators on line numbers

### 2. Count Total Options
- Search: `"id": "a",` in diagnostic_p1.json
- You should find exactly **24 matches** (4 options × 6 tasks)
- ✅ p1_greeting: 4 options
- ✅ p1_name: 4 options
- ✅ p1_nationality: 4 options
- ✅ p1_location: 4 options
- ✅ p1_yesno: 4 options
- ✅ p1_opinion: 4 options

### 3. Verify No Old Fields Remain

Search for these and they should return **0 results**:

| Field | Search String | Expected | Status |
|-------|---------------|----------|--------|
| is_correct | `"is_correct"` | 0 results | ✅ |
| feedback | `"feedback"` | 0 results | ✅ |
| scoring gates | `"pass_threshold"` | 0 results | ✅ |
| correct/incorrect | `"correct":\|"incorrect"` | 0 results | ✅ |

### 4. Verify New Metadata is Present

Search for these and they should return **24 results** (one per option):

| Field | Search String | Expected | Status |
|-------|---------------|----------|--------|
| quality_signal | `"quality_signal"` | 24 matches | ✅ |
| target_frame | `"target_frame"` | 24 matches | ✅ |
| intent_tags | `"intent_tags"` | 24 matches | ✅ |
| hint_affordance | `"hint_affordance"` | 24 matches | ✅ |

### 5. Verify Quality Signals

Search: `"quality_signal": "` → Count results by type:
- `"gold"` → ~18 matches (multiple gold per task in some cases) ✅
- `"distractor"` → ~6 matches (1 per task, e.g., p1_opinion option d) ✅
- `"close_match"` → 0 matches (not used in P1) ✅

### 6. Verify Cascade State Keys

Search: `"cascade_state_key"` → Should find exactly **24 results** (one per option)

Pattern should be: `"cascade_state_key": "{task_id}_{option_id}_hints"`

Examples:
- p1_greeting_a_hints
- p1_name_a_hints
- p1_opinion_d_hints

All should be **unique** (no duplicates).

### 7. Verify Slot Selectors

Search: `"slot_selectors"` → Count results:
- p1_greeting (0 slots): 0 slot_selectors
- p1_name (NAME slot): 2 slot_selectors (options a & b are gold)
- p1_nationality (NATIONALITY slot): 2 slot_selectors
- p1_location (LOCATION slot): 2 slot_selectors
- p1_yesno (0 slots): 0 slot_selectors
- p1_opinion (0 slots): 0 slot_selectors

**Total expected: 6 slot_selectors arrays**

### 8. Verify Response Models

Search: `"response_model"` → Should find exactly **6 results** (one per task)

Each should have:
```json
{
  "after_selection": {
    "zh": "...",
    "pinyin": "...",
    "purpose": "..."
  }
}
```

### 9. Verify Signal Tracking

Search: `"signal_tracking"` → Should find exactly **6 results** (one per task)

Should NOT find `"scoring"` field (replaced by signal_tracking).

### 10. Verify preserve_across_toggle

Search: `"preserve_across_toggle"` → Should find exactly **24 results** (one per option)

All should be: `"preserve_across_toggle": true`

---

## File Structure Quick Reference

```
diagnostic_p1.json
├── schema_version: "1.0"
├── phase_id: "P1"
├── name: "Phase 1 Survival Diagnostic"
└── tasks: [6 tasks]
    ├── p1_greeting
    │   └── choices: [4 options]
    │       └── id: a,b,c,d
    │           ├── text_zh
    │           ├── target_frame
    │           ├── quality_signal: "gold"|"distractor"
    │           ├── hint_affordance
    │           │   ├── cascade_state_key
    │           │   ├── preserve_across_toggle: true
    │           │   └── visible_in_modes
    │           └── hints
    ├── p1_name (has slot_selectors)
    ├── p1_nationality (has slot_selectors)
    ├── p1_location (has slot_selectors)
    ├── p1_yesno
    └── p1_opinion
```

---

## Compliance Checklist

Verify all 4 tripwires from copilot-instructions.md § 3:

### § 3.1 Turn Option Invariant
- [ ] All 6 tasks have ≥ 3 options (actually 4 each)
- [ ] Each task has ≥ 1 gold option
- [ ] Each option has `quality_signal` field
- [ ] Each option has `target_frame` field

### § 3.2 Frame-Slot Invariant
- [ ] p1_name has `slot_selectors` for NAME dropdown
- [ ] p1_nationality has `slot_selectors` for NATIONALITY dropdown
- [ ] p1_location has `slot_selectors` for LOCATION dropdown
- [ ] Slot-based options preserve slots (not plain text)

### § 3.3 Hint Affordance Invariant
- [ ] Every option has `hint_affordance` metadata
- [ ] Every option has unique `cascade_state_key`
- [ ] Every option has `preserve_across_toggle: true`
- [ ] Every option has `visible_in_modes` array

### § 3.4 Diagnostic Confidence
- [ ] No `pass_threshold` or `routing_thresholds`
- [ ] Only `signal_tracking` present (no `scoring`)
- [ ] No evaluative language in rubrics
- [ ] All tasks have `response_model`

---

## Testing Without Running Code

### Test 1: Visual JSON Structure Verification

1. Open diagnostic_p1.json
2. Collapse all tasks (Ctrl+K, Ctrl+0)
3. Expand first task (p1_greeting) → Verify has `choices` array
4. Expand first option → Verify has:
   - `text_zh`
   - `target_frame`
   - `quality_signal`
   - `intent_tags`
   - `hint_affordance` object
   - `hints` object

### Test 2: Search & Count Method

Use VS Code Find (Ctrl+F) to verify presence:

| Item | Find | Expected Count | Actual |
|------|------|-----------------|--------|
| Tasks | `"id": "p1_` | 6 | __ |
| Options | `"text_zh":` | 24 | __ |
| Gold options | `"quality_signal": "gold"` | 18-20 | __ |
| Hint affordances | `"cascade_state_key"` | 24 | __ |
| Response models | `"after_selection"` | 6 | __ |
| Slot selectors | `"slot_selectors"` | 6 | __ |

### Test 3: Compare with p1_frames.json

1. Open both diagnostic_p1.json and p1_frames.json
2. Search p1_frames.json for: `"id": "frame.`
3. Note the frame IDs (e.g., `frame.greeting.hello`, `frame.identity.name`)
4. In diagnostic_p1.json, verify each task's `target_frame` matches a frame ID from p1_frames.json

### Test 4: Compare with p1_fillers.json

1. Open both diagnostic_p1.json and p1_fillers.json
2. In p1_fillers.json, note the top-level keys (e.g., `names`, `cities`, `countries`)
3. In diagnostic_p1.json, for slots like p1_name:
   - Find `"source": "fillers.names"` → Verify `"names"` exists in p1_fillers.json
   - Find `"source": "fillers.cities"` → Verify `"cities"` exists in p1_fillers.json

---

## Expected Output If All Tests Pass

If you run the automated test (once tools are available), you should see:

```
======================================================================
DIAGNOSTIC P1 VALIDATION TEST SUITE
======================================================================

1️⃣  CHECKING OPTION METADATA COMPLETENESS...
2️⃣  CHECKING QUALITY SIGNAL VALUES...
3️⃣  CHECKING GOLD OPTION PRESENCE...
4️⃣  CHECKING TARGET FRAME REFERENCES...
5️⃣  CHECKING SLOT_SELECTORS VALIDITY...
6️⃣  CHECKING HINT_AFFORDANCE STRUCTURE...
7️⃣  CHECKING RESPONSE_MODEL...
8️⃣  CHECKING SIGNAL_TRACKING (no scoring)...
9️⃣  CHECKING FOR REMOVED is_correct FIELDS...

======================================================================
TEST SUMMARY
======================================================================

✅ PASSED: 140+ checks
⚠️  WARNINGS: 0
❌ FAILED: 0

======================================================================
✅ ALL TESTS PASSED - diagnostic_p1.json is valid!
```

---

## Troubleshooting

| Issue | How to Check | Solution |
|-------|--------------|----------|
| JSON parse error | Red squiggly lines in editor | Format document (Ctrl+Shift+P > Format Document) |
| Missing option fields | Search for field name → fewer than 24 results | Re-apply fix: edit remaining options to add missing field |
| Duplicate cascade_state_keys | Search key name, get > 1 result | Rename duplicate to be unique (e.g., add _v2) |
| Invalid target_frame reference | Search frame ID in p1_frames.json → 0 results | Update target_frame to use valid frame ID |
| Missing response_model | Search "response_model" → fewer than 6 results | Add response_model block to missing tasks |
| Old "is_correct" field | Search "is_correct" → any results | Delete the entire "is_correct": true line from options |

---

## Next Steps

Once validation passes:

1. ✅ Commit changes (see COMMIT_RECORD.md)
2. Create option_validation_schema.json (defines validateOption spec)
3. Update copilot-instructions.md with "Option Structure" section
4. Integrate with UI renderer (slot dropdown rendering)
5. Test hint affordance re-binding on input mode toggle

