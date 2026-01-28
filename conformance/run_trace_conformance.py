#!/usr/bin/env python3
"""
MandarinOS Trace Conformance Runner v1

Validates traces against the TurnState Trace Contract v1 schema.
Enforces all six hard gates and reports detailed errors.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from enum import Enum


class ValidationError(Enum):
    """Error codes for trace validation failures."""
    TRACE_SCHEMA_INVALID = "TRACE_SCHEMA_INVALID"
    DEAD_STATE_NO_FORWARD_PATH = "DEAD_STATE_NO_FORWARD_PATH"
    TOGGLE_AFFORDANCE_DROP = "TOGGLE_AFFORDANCE_DROP"
    SCAFFOLDING_AFFORDANCE_DROP = "SCAFFOLDING_AFFORDANCE_DROP"
    HINT_NO_EFFECTS_BLOCK = "HINT_NO_EFFECTS_BLOCK"
    HINT_NON_ACTIONABLE = "HINT_NON_ACTIONABLE"
    TEACHER_SINGLE_ANSWER = "TEACHER_SINGLE_ANSWER"
    CONTRACT_OPTION_FLATTENED = "CONTRACT_OPTION_FLATTENED"
    CONTRACT_SLOT_UNEXECUTABLE = "CONTRACT_SLOT_UNEXECUTABLE"


class TraceValidator:
    """Validates a trace against the TurnState Trace Contract v1."""
    
    REQUIRED_PRESERVE_AFFORDANCES = {"what_can_i_say"}
    
    def __init__(self, trace_path: str):
        self.trace_path = Path(trace_path)
        self.trace = None
        self.errors: List[Tuple[str, ValidationError]] = []
        self.passed = False
    
    def load_trace(self) -> bool:
        """Load and parse trace JSON."""
        try:
            with open(self.trace_path, 'r', encoding='utf-8') as f:
                self.trace = json.load(f)
            return True
        except (json.JSONDecodeError, FileNotFoundError) as e:
            self.errors.append((f"Failed to load trace: {e}", ValidationError.TRACE_SCHEMA_INVALID))
            return False
    
    def validate_schema(self) -> bool:
        """Gate 1: Validate trace schema structure."""
        if not self.trace:
            return False
        
        required_top_level = ["trace_version", "trace_id", "created_at", "app_build", "locale", 
                              "user_profile", "scenario", "steps"]
        
        for field in required_top_level:
            if field not in self.trace:
                self.errors.append(
                    (f"Missing required top-level field: {field}", ValidationError.TRACE_SCHEMA_INVALID)
                )
                return False
        
        if not isinstance(self.trace.get("steps"), list) or len(self.trace["steps"]) == 0:
            self.errors.append(
                ("Steps must be a non-empty array", ValidationError.TRACE_SCHEMA_INVALID)
            )
            return False
        
        return True
    
    def has_forward_path(self, state: Dict[str, Any]) -> bool:
        """Check if state has a forward path (Gate 2)."""
        # Option 1: Non-empty options
        if state.get("options") and len(state["options"]) > 0:
            return True
        
        # Option 2: Slot-fill path exists (has required slots with selectors OR hints available)
        slots = state.get("slots", {})
        required_slots = slots.get("required", [])
        selectors_present = slots.get("selectors_present", [])
        
        if required_slots and any(slot in selectors_present for slot in required_slots):
            return True
        
        # Option 3: Hints available with open_hint affordance
        hints = state.get("hints")
        affordances = state.get("affordances", [])
        
        if hints and hints.get("available") and "open_hint" in affordances:
            return True
        
        return False
    
    def validate_forward_paths(self) -> bool:
        """Gate 2: Validate forward-path guarantee at every AFTER state."""
        for step in self.trace.get("steps", []):
            after_state = step.get("after")
            if not after_state:
                continue
            
            if not self.has_forward_path(after_state):
                self.errors.append(
                    (f"Dead state in step {step.get('step_id')}: no forward path", 
                     ValidationError.DEAD_STATE_NO_FORWARD_PATH)
                )
                return False
        
        return True
    
    def validate_toggle_affordances(self) -> bool:
        """Gate 3: Affordance preservation across TOGGLE_INPUT_MODE events."""
        for step in self.trace.get("steps", []):
            event = step.get("event", {})
            
            if event.get("type") != "TOGGLE_INPUT_MODE":
                continue
            
            before = step.get("before", {})
            after = step.get("after", {})
            
            before_affordances = set(before.get("affordances", []))
            after_affordances = set(after.get("affordances", []))
            
            # Must preserve what_can_i_say
            if "what_can_i_say" not in after_affordances:
                self.errors.append(
                    (f"Toggle in {step.get('step_id')} dropped 'what_can_i_say'",
                     ValidationError.TOGGLE_AFFORDANCE_DROP)
                )
                return False
            
            # If hints available before, must keep open_hint
            before_hints = before.get("hints")
            after_hints = after.get("hints")
            
            if before_hints and before_hints.get("available") and "open_hint" not in after_affordances:
                self.errors.append(
                    (f"Toggle in {step.get('step_id')} dropped 'open_hint' despite hints available",
                     ValidationError.TOGGLE_AFFORDANCE_DROP)
                )
                return False
        
        return True
    
    def validate_scaffolding_affordances(self) -> bool:
        """Gate 4: Scaffolding non-amputation across scaffolding changes."""
        for step in self.trace.get("steps", []):
            event = step.get("event", {})
            
            if not event.get("type", "").startswith("SYSTEM_"):
                continue
            
            before = step.get("before", {})
            after = step.get("after", {})
            
            before_level = before.get("scaffolding_level")
            after_level = after.get("scaffolding_level")
            after_affordances = set(after.get("affordances", []))
            
            # what_can_i_say must always be present
            if "what_can_i_say" not in after_affordances:
                self.errors.append(
                    (f"Scaffolding change in {step.get('step_id')} removed 'what_can_i_say'",
                     ValidationError.SCAFFOLDING_AFFORDANCE_DROP)
                )
                return False
        
        return True
    
    def validate_hint_effects(self) -> bool:
        """Gate 5: Hint cascade continuity and effects blocks."""
        for step in self.trace.get("steps", []):
            after = step.get("after", {})
            hints = after.get("hints")
            
            if hints and hints.get("available"):
                payload = hints.get("payload", {})
                effects = payload.get("effects", {})
                
                # Hints must have effects block (non-empty)
                if not effects or not isinstance(effects, dict) or len(effects) == 0:
                    self.errors.append(
                        (f"Hint in {step.get('step_id')} has no effects block",
                         ValidationError.HINT_NO_EFFECTS_BLOCK)
                    )
                    return False
                
                # Check for teacher single-answer pattern
                if effects.get("teacher_correction"):
                    options_count = len(after.get("options", []))
                    if options_count <= 1:
                        self.errors.append(
                            (f"Step {step.get('step_id')} shows single teacher-corrected answer",
                             ValidationError.TEACHER_SINGLE_ANSWER)
                        )
                        return False
        
        return True
    
    def validate_slot_structure(self) -> bool:
        """Gate 6: No flattened options; slots must be executable."""
        for step in self.trace.get("steps", []):
            after = step.get("after", {})
            options = after.get("options", [])
            slots = after.get("slots", {})
            required_slots = set(slots.get("required", []))
            selectors_present = set(slots.get("selectors_present", []))
            filled_slots = set(slots.get("filled", {}).keys())
            
            # Check: required slots must be either filled or have selectors
            for req_slot in required_slots:
                if req_slot not in filled_slots and req_slot not in selectors_present:
                    self.errors.append(
                        (f"Step {step.get('step_id')} has required slot '{req_slot}' but no selector available",
                         ValidationError.CONTRACT_SLOT_UNEXECUTABLE)
                    )
                    return False
            
            for option in options:
                required_slots_in_option = option.get("required_slots", [])
                
                # If option has required slots, it must have structure
                if required_slots_in_option:
                    has_tokens = bool(option.get("tokens"))
                    has_selectors = bool(option.get("slot_selectors"))
                    has_frame_id = bool(option.get("frame_id"))
                    
                    # Must have both frame_id AND (tokens or selectors)
                    if not has_frame_id or not (has_tokens or has_selectors):
                        self.errors.append(
                            (f"Option {option.get('option_id')} in {step.get('step_id')} is flattened "
                             f"(has required_slots but no complete structure)",
                             ValidationError.CONTRACT_OPTION_FLATTENED)
                        )
                        return False
        
        return True
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        """Run all validation gates. Return (passed, expected_error_code_if_fail)."""
        if not self.load_trace():
            return False, None
        
        # Gate 1: Schema validity
        if not self.validate_schema():
            return False, None
        
        # Gate 3: Affordance preservation on toggles (check before forward path)
        if not self.validate_toggle_affordances():
            expected = self.trace.get("expected", {})
            if expected.get("result") == "FAIL":
                return False, expected.get("error_code")
            return False, None
        
        # Gate 4: Scaffolding non-amputation
        if not self.validate_scaffolding_affordances():
            expected = self.trace.get("expected", {})
            if expected.get("result") == "FAIL":
                return False, expected.get("error_code")
            return False, None
        
        # Gate 2: Forward-path guarantee
        if not self.validate_forward_paths():
            expected = self.trace.get("expected", {})
            if expected.get("result") == "FAIL":
                return False, expected.get("error_code")
            return False, None
        
        # Gate 5: Hint effects
        if not self.validate_hint_effects():
            expected = self.trace.get("expected", {})
            if expected.get("result") == "FAIL":
                return False, expected.get("error_code")
            return False, None
        
        # Gate 6: Slot structure
        if not self.validate_slot_structure():
            expected = self.trace.get("expected", {})
            if expected.get("result") == "FAIL":
                return False, expected.get("error_code")
            return False, None
        
        return True, None
    
    def report(self):
        """Print validation report."""
        if self.errors:
            print(f"❌ {self.trace_path.name}")
            for msg, code in self.errors:
                print(f"   {code.value}: {msg}")
        else:
            print(f"✓ {self.trace_path.name}")


def run_conformance_suite(base_path: str) -> Tuple[int, int]:
    """Run conformance on all pass and fail traces. Return (total, passed)."""
    base = Path(base_path)
    pass_dir = base / "golden" / "traces" / "v1" / "pass"
    fail_dir = base / "golden" / "traces" / "v1" / "fail"
    
    total = 0
    passed = 0
    
    print("\n=== PASS TRACES ===")
    if pass_dir.exists():
        for trace_file in sorted(pass_dir.glob("*.json")):
            validator = TraceValidator(str(trace_file))
            validated, expected_error = validator.validate()
            
            expected_result = validator.trace.get("expected", {}).get("result") if validator.trace else None
            
            if expected_result == "PASS":
                if validated:
                    print(f"✓ {trace_file.name} (PASS as expected)")
                    passed += 1
                else:
                    print(f"❌ {trace_file.name} (should PASS but failed)")
                    for msg, code in validator.errors:
                        print(f"   {code.value}: {msg}")
                total += 1
            else:
                validator.report()
    
    print("\n=== FAIL TRACES ===")
    if fail_dir.exists():
        for trace_file in sorted(fail_dir.glob("*.json")):
            validator = TraceValidator(str(trace_file))
            validated, expected_error = validator.validate()
            
            expected_result = validator.trace.get("expected", {}).get("result") if validator.trace else None
            expected_code = validator.trace.get("expected", {}).get("error_code") if validator.trace else None
            
            if expected_result == "FAIL":
                if not validated and validator.errors:
                    actual_code = validator.errors[0][1].value if validator.errors else "UNKNOWN"
                    if expected_code and actual_code == expected_code:
                        print(f"✓ {trace_file.name} (FAIL as expected: {expected_code})")
                        passed += 1
                    else:
                        print(f"❌ {trace_file.name} (FAIL but wrong error code)")
                        print(f"   Expected: {expected_code}")
                        print(f"   Got: {actual_code}")
                else:
                    print(f"❌ {trace_file.name} (should FAIL but passed)")
                total += 1
            else:
                validator.report()
    
    return total, passed


if __name__ == "__main__":
    if len(sys.argv) > 1:
        base_path = sys.argv[1]
    else:
        base_path = str(Path(__file__).parent.parent)
    
    total, passed = run_conformance_suite(base_path)
    
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed")
    print(f"{'='*50}\n")
    
    sys.exit(0 if passed == total else 1)
