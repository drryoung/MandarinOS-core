# Option Generation Audit: Frame Slots & Hint Re-binding

## Audit Scope

**Requirements from copilot-instructions.md:**
- §2.3 Frame correctness: If frame has slots, gold option must preserve slot as dropdown/selector, not plain text
- §2.4 Hint affordance: If input mode toggles (tap ↔ type), hint affordance must re-render and re-bind

**Tripwires:**
- §3.1 Turn option invariant: `option_count >= 3`, `gold_option_present == true`, option passes `validateOption()`
- §3.2 Frame-slot invariant: If target requires slots, option must carry required slot metadata
- §3.3 Hint affordance invariant: Hint button visible on every user turn; re-binds consistently on mode toggle

---

## Current State Analysis

### Issue 1: Gold Options Don't Explicitly Carry Slot Selectors

**Location:** [diagnostic_p1.json](diagnostic_p1.json) options

**Current Structure (p1_name option a):**
```json
{
  "id": "a",
  "text_zh": "我叫...",
  "frame_slots_satisfied": [{"slot": "NAME", "position": "after_verb"}],
  "quality_signal": "gold"
}
```

**Problem:**
- `text_zh` shows "我叫..." (placeholder only)
- `frame_slots_satisfied` indicates a NAME slot exists
- **Missing:** Explicit `slot_selector` or `dropdown_items` field that tells the UI to render an interactive dropdown/selector for the {NAME} slot
- The diagnostic knows a slot exists, but the option doesn't specify HOW to render it

**Violation of §2.3:**
> "If a frame format includes a slot (e.g. 我叫{NAME}。), then the tap option must preserve the slot as a **dropdown/selector** (or an equivalent structured input), not a plain-text teacher sentence."

**Current behavior:** Option shows "我叫..." but doesn't tell the UI to create a NAME dropdown selector

---

### Issue 2: Distractor Options Don't Carry Slot Metadata (Even When They Shouldn't)

**Location:** [diagnostic_p1.json](diagnostic_p1.json) lines 145-175 (p1_name options c & d)

**Current Structure (p1_name option c):**
```json
{
  "id": "c",
  "text_zh": "你好",
  "hints": {...}
  // Missing: target_frame, quality_signal
}
```

**Problem:**
- Distractor options don't explicitly declare "not a match"
- No `quality_signal: "distractor"` to indicate this is intentionally wrong
- No `target_frame` for validation purposes
- Makes it hard for the runtime to distinguish between "incomplete gold option" vs "intentional distractor"

---

### Issue 3: Hint Affordance Re-binding on Input Mode Toggle

**Location:** Design requirement (§2.4)

**Current State:** Unknown - diagnostics have a `hints` field per option, but:
- No explicit mechanism for re-binding hints when input mode changes
- No `hint_cascade_state` preserved across mode toggles
- No metadata indicating which mode each hint tier is optimized for

**Required:**
```json
{
  "id": "a",
  "text_zh": "我叫...",
  "hints": {
    "layer1": {...},
    "layer2": {...},
    "layer3": {...}
  },
  "hint_affordance": {
    "visible_in_modes": ["tap", "type"],
    "cascade_state_key": "p1_name_a_hints",
    "preserve_across_toggle": true
  }
}
```

---

### Issue 4: No `slot_selector` or `dropdown_template` Field

**Location:** All options with `frame_slots_satisfied`

**Missing Field:** Options with slots should include rendering instructions:
```json
{
  "id": "a",
  "text_zh": "我叫...",
  "frame_slots_satisfied": [{"slot": "NAME", "position": "after_verb"}],
  "slot_selector": {
    "type": "dropdown",
    "slot_name": "NAME",
    "source": "fillers.names",
    "placeholder": "选择一个名字...",
    "examples": ["王明", "李华", "张三"]
  },
  "quality_signal": "gold"
}
```

Without this, the UI can't render the interactive slot selector properly.

---

### Issue 5: No Validation Rule for Multi-Slot Frames

**Location:** All frame definitions (frames.json)

**Current Problem:**
- Frames can have multiple slots: e.g., "我在{CITY}的{LOCATION}住了{TIME}。"
- Options with `frame_slots_satisfied` only track which slots are present
- No validation that ALL required slots are present in the option

**Missing:**
```json
{
  "id": "a",
  "text_zh": "option with slots",
  "frame_slots_satisfied": [
    {"slot": "CITY", "position": 1},
    {"slot": "LOCATION", "position": 2},
    {"slot": "TIME", "position": 3}
  ],
  "slots_complete": true,  // <-- All required slots present
  "quality_signal": "gold"
}
```

---

## Audit Findings

### ✅ Already Compliant (from Fixes 1-5)

1. **Option metadata structure** — All options now carry `target_frame`, `intent_tags`, `quality_signal`
2. **Frame slot awareness** — `frame_slots_satisfied` field present in all gold options
3. **Signal extraction** — Silent tracking (no user-visible scoring)
4. **Intent-based validation** — Rubrics focus on intent, not grammar

### ❌ Gaps Identified

1. **Missing `slot_selector` field** — No rendering instructions for interactive slot dropdowns
2. **Missing `hint_affordance` metadata** — No hint re-binding mechanism on input mode toggle
3. **No `slots_complete` validation** — Multi-slot frames not validated for completeness
4. **Distractor options incomplete** — Missing `quality_signal: "distractor"` and validation metadata
5. **No mode-specific hint optimization** — Hints not optimized for tap vs. type modes

---

## Recommended Single Fix

**Consolidate into ONE fix:** Add comprehensive option metadata for slot rendering and hint re-binding

### Files to Modify
1. **diagnostic_p1.json** — Add slot_selector and hint_affordance to ALL options
2. **diagnostic_p2.json** — Same (once it's extended with options)
3. Create validation schema: `option_validation_schema.json` (new file) — Define validateOption() spec

### Changes Needed

**Per option in choices array:**
```json
{
  "id": "a",
  "text_zh": "我叫...",
  "target_frame": "frame.identity.name",
  "frame_slots_satisfied": [{"slot": "NAME", "position": "after_verb", "source": "fillers.names"}],
  "intent_tags": ["name_introduce"],
  "quality_signal": "gold",
  
  // NEW FIELDS:
  "slots_complete": true,
  "slot_selectors": [
    {
      "slot_name": "NAME",
      "type": "dropdown",
      "source": "fillers.names",
      "placeholder": "选择名字...",
      "required": true
    }
  ],
  "hint_affordance": {
    "visible_in_modes": ["tap", "type"],
    "cascade_state_key": "p1_name_a",
    "preserve_across_toggle": true,
    "optimized_for_mode": "tap"
  },
  "hints": {
    "layer1": "My name is...",
    "layer2": "wǒ jiào...",
    "layer3": "我叫... = My name is..."
  }
}
```

**For distractor options:**
```json
{
  "id": "c",
  "text_zh": "你好",
  "target_frame": null,  // Not a match
  "intent_tags": [],
  "quality_signal": "distractor",  // NEW
  "reason_distracted": "Wrong intent (greeting, not introduction)",  // Diagnostic use only
  "hints": {...}
}
```

---

## Compliance Impact

Once this fix is implemented:

✅ **§2.3 Frame correctness** — Gold options explicitly carry slot_selectors for UI rendering  
✅ **§2.4 Hint affordance** — Hints preserve cascade_state and re-bind across input mode toggles  
✅ **§3.1 Turn option invariant** — validateOption() can verify slots_complete and slot_selector presence  
✅ **§3.2 Frame-slot invariant** — Option structure explicitly declares required slots and rendering mode  
✅ **§3.3 Hint affordance invariant** — hint_affordance metadata ensures consistent re-rendering

---

## Implementation Plan

**Single Fix: "Add Slot-Rendering & Hint Re-binding Metadata to Options"**

1. Update diagnostic_p1.json:
   - Add `slots_complete` flag (all options)
   - Add `slot_selectors` array (gold options with slots)
   - Add `hint_affordance` metadata (all options)
   - Add `quality_signal: "distractor"` (all non-gold options)

2. Create option_validation_schema.json:
   - Define validateOption(option, targetFrame) spec
   - List required fields per option type (gold, close_match, distractor)
   - Specify slot validation rules

3. Update copilot-instructions.md:
   - Add Option Structure section referencing the new schema
   - Document validateOption() implementation requirements

---

## Testing Checklist

- [ ] Verify slot_selector presence in all gold options with slots
- [ ] Verify slots_complete = true iff all required slots present
- [ ] Verify hint_affordance metadata on all options
- [ ] Verify preserve_across_toggle = true allows mode toggle without losing hint state
- [ ] Verify distractor options carry quality_signal = "distractor"
- [ ] Verify validateOption() can process all metadata fields
- [ ] Verify tap mode renders slot dropdowns correctly
- [ ] Verify type mode skips slot_selectors (user types full text)

---

**Status:** Audit complete. Ready for single consolidated fix.
