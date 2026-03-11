# MandarinOS Required Scenarios v1

This document specifies the six required scenario IDs and success criteria that the full app MUST implement and export traces for.

Each scenario directly tests a non-negotiable MandarinOS product constraint (see .github/copilot-instructions.md).

## Overview

| ID | Intent | Core Constraint | Min Steps |
|---|---|---|---|
| S1_basic_slot_fill | Frame slots remain executable end-to-end | Forward-path guarantee + no flattening | 3 |
| S2_hint_narrow_structure_model | Hint cascade effects are actionable | Affordance preservation + hint effects | 4 |
| S3_toggle_preserves_affordances | TAP↔TYPE toggle preserves core affordances | Toggle affordance invariant | 3 |
| S4_scaffolding_high_to_low | Narrowing does not amputate affordances | Scaffolding non-amputation | 4 |
| S5_narrow_then_slot_integrity | Narrowing preserves slot executability | Slot structure invariant | 3 |
| S6_diagnostic_confidence_changes | Confidence downgrades don't trigger quiz behavior | No single-answer teaching | 3 |

---

## S1: Basic Slot Fill

**Scenario ID**: `S1_basic_slot_fill`

**Intent**: Ensure that slot-bearing frames remain **executable and unflattened** from prompt to completion.

**Events**:
1. `SYSTEM prompt` (implicit) → user sees frame with required slot
2. `USER_SELECT_OPTION` → user selects slot-bearing frame
3. `USER_FILL_SLOT` (or `USER_SELECT_OPTION` with filled option) → slot is filled
4. `END_TURN` (implicit)

**What must be captured**:
- **Turn 1 (before)**: Frame option with `required_slots`, `tokens` or `slot_selectors`
- **Turn 1 (after)**: Options showing slot choices (e.g., NAME: ["Alice", "Bob"])
- **Turn 2 (after)**: Slot marked as filled in `slots.filled`

**Validation Criteria**:
- ✓ No option with `required_slots` is missing `tokens` or `slot_selectors`
- ✓ `slots.required` matches frame requirements
- ✓ Forward path always available (options OR hints OR selectors)
- ✓ Error code: `CONTRACT_OPTION_FLATTENED` if violated

**Trace file naming**: `traces/scenario_S1_basic_slot_fill.json`

---

## S2: Hint Narrow → Structure → Model

**Scenario ID**: `S2_hint_narrow_structure_model`

**Intent**: Ensure hint cascade **effects are preserved and actionable** through narrowing, structure, and modeling steps.

**Events**:
1. `OPEN_HINT` (step 0) → generic hint ("Try something")
2. `ADVANCE_HINT` (step 1) → narrow hint ("Coffee or tea?") with effects block
3. `ADVANCE_HINT` (step 2) → structured hint ("You should say: ...") with effects
4. `ADVANCE_HINT` (step 3, optional) → modeling hint ("Example: ...") with effects

**What must be captured**:
- **Each after state**: `hints.payload.effects` must be non-empty object
- **Step 0→1**: `effects.narrow == true`
- **Step 1→2**: `effects.structure == true`
- **Step 2→3** (if present): `effects.model == true`
- **Cascade state key**: same `cascade_state_key` preserved across all steps

**Validation Criteria**:
- ✓ Each hint step has actionable effects
- ✓ `hints.available == true` when hints present
- ✓ `cascade_state_key` is consistent within a hint session
- ✓ Error code: `HINT_NO_EFFECTS_BLOCK` if violated
- ✓ Error code: `TEACHER_SINGLE_ANSWER` if hint shows only 1 option + teacher_correction

**Trace file naming**: `traces/scenario_S2_hint_narrow_structure_model.json`

---

## S3: Toggle Preserves Affordances

**Scenario ID**: `S3_toggle_preserves_affordances`

**Intent**: Ensure TAP ↔ TYPE input mode toggles **do not drop core affordances** or hint state.

**Events**:
1. `TOGGLE_INPUT_MODE` TAP → TYPE
2. (Optional) `OPEN_HINT` in TYPE mode
3. `TOGGLE_INPUT_MODE` TYPE → TAP
4. (Optional) `TOGGLE_INPUT_MODE` TAP → TYPE again

**What must be captured**:
- **Before TAP state**: has options, `affordances = ["what_can_i_say", "open_hint", "select_option"]`
- **After TYPE state**: options empty, `affordances = ["what_can_i_say", "open_hint", "submit_response"]`
- **Hint continuity**: if hints available before toggle, cascade state must persist

**Validation Criteria**:
- ✓ `"what_can_i_say"` always present across all modes
- ✓ `"open_hint"` preserved if hints available
- ✓ `hints.cascade_state_key` unchanged across toggles
- ✓ Forward path maintained in all states
- ✓ Error code: `TOGGLE_AFFORDANCE_DROP` if violated

**Trace file naming**: `traces/scenario_S3_toggle_preserves_affordances.json`

---

## S4: Scaffolding High → MED → LOW

**Scenario ID**: `S4_scaffolding_high_to_low`

**Intent**: Ensure scaffolding **narrowing does not amputate affordances** that the user needs.

**Events**:
1. User expresses uncertainty → `SYSTEM_NARROW` HIGH → MED
2. User still stuck → `SYSTEM_NARROW` MED → LOW
3. (Optional) `OPEN_HINT` at LOW level
4. (Optional) Final `USER_UNCERTAIN` or `END_TURN`

**What must be captured**:
- **Turn HIGH**: 4+ options, `affordances = ["what_can_i_say", "open_hint", "select_option"]`
- **Turn MED**: 2 options, same affordances (key: NOT dropped)
- **Turn LOW**: 1 option, `affordances` must still include `"what_can_i_say"`
- If user stuck: `"open_hint"` must remain available

**Validation Criteria**:
- ✓ `"what_can_i_say"` present at all levels
- ✓ If uncertainty signals, `"open_hint"` remains available
- ✓ Forward path always present
- ✓ Options reduced but options array not empty
- ✓ Error code: `SCAFFOLDING_AFFORDANCE_DROP` if violated

**Trace file naming**: `traces/scenario_S4_scaffolding_high_to_low.json`

---

## S5: Narrow Then Slot Integrity

**Scenario ID**: `S5_narrow_then_slot_integrity`

**Intent**: Ensure `SYSTEM_NARROW` does **not drop slot tokens/selectors** that user needs to complete the turn.

**Events**:
1. User sees slot-bearing frame option in HIGH scaffold
2. `SYSTEM_NARROW` HIGH → MED (options reduced)
3. Narrowed option still has same slot metadata
4. `USER_SELECT_OPTION` (select frame) → `USER_FILL_SLOT` or slot selector appears

**What must be captured**:
- **Turn HIGH (after)**: Frame with `required_slots = ["NAME"]`, selectors present
- **Turn MED (after)**: Same frame still in options, `slot_selectors` or `tokens` preserved
- **slots.required** consistent (narrowing doesn't change requirements)
- **slots.selectors_present** non-empty in narrowed state

**Validation Criteria**:
- ✓ Frame options not flattened during narrowing
- ✓ Required slots executable after narrowing
- ✓ `slots.required` ⊆ `slots.selectors_present` for all states
- ✓ Error code: `CONTRACT_SLOT_UNEXECUTABLE` if slot marked required but no selector

**Trace file naming**: `traces/scenario_S5_narrow_then_slot_integrity.json`

---

## S6: Diagnostic Confidence Changes (No Assessment)

**Scenario ID**: `S6_diagnostic_confidence_changes_no_assessment`

**Intent**: Ensure diagnostic **confidence downgrades do not trigger "correct answer" quiz behavior**.

**Events**:
1. User responds correctly → `diagnostic.confidence = HIGH`
2. User shows uncertainty → `USER_UNCERTAIN`
3. Confidence downgrades → `diagnostic.confidence = MED`
4. (Optional) Further uncertainty → confidence → `LOW`

**What must be captured**:
- **Turn 1 (after)**: `diagnostic.mode = "diagnostic"`, `confidence = "HIGH"`, options present
- **Turn 2 (after)**: Same after USER_UNCERTAIN, `confidence = MED`, affordances preserved
- **Affordances not dropped**: `["what_can_i_say", "open_hint", "select_option"]` maintained
- **No teacher correction**: Hints must have effects blocks but NOT `teacher_correction: true` with single option

**Validation Criteria**:
- ✓ Affordances preserved across confidence changes
- ✓ Forward path always available
- ✓ No single-answer "correct response" reveal
- ✓ Hints remain actionable (effects blocks present)
- ✓ Error code: `TEACHER_SINGLE_ANSWER` if hint shows single corrected answer

**Trace file naming**: `traces/scenario_S6_diagnostic_confidence_changes_no_assessment.json`

---

## CI Integration

To integrate these required scenarios into CI:

```yaml
# GitHub Actions example (add to your workflow)
- name: Validate MandarinOS Traces
  run: |
    python3 -m conformance.run_trace_conformance \
      --path traces/ \
      --require-scenarios S1_basic_slot_fill,S2_hint_narrow_structure_model,S3_toggle_preserves_affordances,S4_scaffolding_high_to_low,S5_narrow_then_slot_integrity,S6_diagnostic_confidence_changes_no_assessment
  # (This feature will be added to the conformance runner)
```

For now, manual validation:

```bash
# Local check
./scripts/validate_traces.sh traces/

# Windows
.\scripts\validate_traces.ps1 -Path traces\
```

---

## References

- [MandarinOS Design Constitution](./mandarinos_design_constitution.txt)
- [TurnState Trace Contract v1](./TRACE_CONTRACT_v1.md)
- [Conformance Runner](../conformance/run_trace_conformance.py)
- [Integration Kit Examples](../integration_kit/examples/)
