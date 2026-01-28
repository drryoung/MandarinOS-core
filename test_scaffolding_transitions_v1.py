"""
test_scaffolding_transitions_v1.py — Scaffolding Transition Harness Validator
Per MandarinOS_scaffolding_transition_harness_v1_directive.txt

Validates:
1) Policy compliance (affordances per level)
2) Forward-path guarantee (always way forward)
3) Affordance preservation across transitions
4) Hint continuity across input mode toggles
5) Slot executability preservation during narrowing
6) Non-teacher single-answer gate in modeling

Error codes:
- SCAFFOLDING_DEAD_STATE
- SCAFFOLDING_AFFORDANCE_DROP
- TOGGLE_BREAKS_HINTS
- TOGGLE_BREAKS_SLOTS
- SCAFFOLDING_POLICY_VIOLATION
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import glob


@dataclass
class TransitionValidationResult:
    """Result of validating a single transition trace."""
    filename: str
    status: str  # "PASS" or "FAIL"
    error_code: Optional[str] = None
    message: str = ""
    step_num: Optional[int] = None


class ScaffoldingPolicyValidator:
    """Validates scaffolding transitions against core->app contract."""
    
    ERROR_CODES = {
        "SCAFFOLDING_DEAD_STATE": "No forward path after scaffolding transition",
        "SCAFFOLDING_AFFORDANCE_DROP": "Required affordance missing at this scaffolding level",
        "TOGGLE_BREAKS_HINTS": "Input mode toggle removes affordance while hints available",
        "TOGGLE_BREAKS_SLOTS": "Input mode toggle breaks slot executability",
        "SCAFFOLDING_POLICY_VIOLATION": "Violates scaffolding policy constraints",
    }
    
    def __init__(self, policy_path: str = "policy/scaffolding_policy.json"):
        self.policy = self._load_policy(policy_path)
        self.results = []
    
    def _load_policy(self, policy_path: str) -> Dict:
        """Load scaffolding policy."""
        try:
            with open(policy_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"WARNING: Policy file not found: {policy_path}")
            return {}
        except json.JSONDecodeError as e:
            print(f"ERROR: Policy JSON invalid: {e}")
            return {}
    
    def validate_transition_trace(self, trace: Dict, filename: str) -> TransitionValidationResult:
        """Validate a complete transition trace."""
        
        if not isinstance(trace, dict):
            return TransitionValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCHEMA_INVALID",
                message="Trace is not a JSON object"
            )
        
        if "steps" not in trace:
            return TransitionValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCHEMA_INVALID",
                message="Trace missing 'steps' array"
            )
        
        steps = trace["steps"]
        if not isinstance(steps, list):
            return TransitionValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCHEMA_INVALID",
                message="steps is not an array"
            )
        
        # Validate each step
        for i, step in enumerate(steps):
            step_num = step.get("step_num", i + 1)
            
            # Get before/after states
            before = step.get("before", {})
            after = step.get("after", {})
            event = step.get("event", {})
            
            # Validate based on event type
            event_type = event.get("type")
            
            if event_type == "USER_UNCERTAIN":
                check = self._check_scaffolding_narrowing(before, after, step_num, filename)
            elif event_type == "TOGGLE_INPUT_MODE":
                check = self._check_input_mode_toggle(before, after, step_num, filename)
            elif event_type == "OPEN_HINT":
                check = self._check_hint_advance(before, after, step_num, filename)
            elif event_type == "SCAFFOLDING_NARROW":
                check = self._check_scaffolding_narrowing(before, after, step_num, filename)
            else:
                # Generic validation
                check = self._check_forward_path_and_affordances(after, step_num, filename)
            
            if check.status == "FAIL":
                return check
        
        return TransitionValidationResult(
            filename=filename,
            status="PASS",
            message="All transition steps validated"
        )
    
    def _check_scaffolding_narrowing(self, before: Dict, after: Dict, step_num: int,
                                    filename: str) -> TransitionValidationResult:
        """Validate scaffolding narrowing (HIGH→MED→LOW)."""
        
        # Check policy compliance for target level
        target_level = after.get("scaffolding_level")
        if target_level and target_level in self.policy.get("levels", {}):
            level_policy = self.policy["levels"][target_level]
            
            # Check minimum options
            min_options = level_policy.get("min_options", 1)
            actual_options = len(after.get("options", []))
            if actual_options < min_options:
                return TransitionValidationResult(
                    filename=filename,
                    status="FAIL",
                    error_code="SCAFFOLDING_POLICY_VIOLATION",
                    message=f"Step {step_num}: {target_level} requires min {min_options} options, got {actual_options}",
                    step_num=step_num
                )
            
            # Check required affordances
            required_affordances = level_policy.get("must_have_affordances", [])
            actual_affordances = set(after.get("affordances", []))
            missing = set(required_affordances) - actual_affordances
            
            if missing:
                return TransitionValidationResult(
                    filename=filename,
                    status="FAIL",
                    error_code="SCAFFOLDING_AFFORDANCE_DROP",
                    message=f"Step {step_num}: {target_level} requires affordances {required_affordances}, missing {list(missing)}",
                    step_num=step_num
                )
        
        # Check slot executability preservation
        slot_check = self._check_slots_preserved(before, after, step_num, filename)
        if slot_check.status == "FAIL":
            return slot_check
        
        # Check forward path
        return self._check_forward_path_and_affordances(after, step_num, filename)
    
    def _check_input_mode_toggle(self, before: Dict, after: Dict, step_num: int,
                                 filename: str) -> TransitionValidationResult:
        """Validate input mode toggle (TAP↔TYPE)."""
        
        from_mode = before.get("input_mode")
        to_mode = after.get("input_mode")
        
        # Determine toggle type
        if from_mode == "TAP" and to_mode == "TYPE":
            toggle_key = "TAP_TO_TYPE"
        elif from_mode == "TYPE" and to_mode == "TAP":
            toggle_key = "TYPE_TO_TAP"
        else:
            return TransitionValidationResult(filename=filename, status="PASS")
        
        # Check policy
        toggle_policy = self.policy.get("toggle_invariants", {}).get(toggle_key, {})
        must_preserve = toggle_policy.get("must_preserve_affordances", [])
        
        before_affordances = set(before.get("affordances", []))
        after_affordances = set(after.get("affordances", []))
        
        # Check preserved affordances
        for affordance in must_preserve:
            if affordance in before_affordances and affordance not in after_affordances:
                return TransitionValidationResult(
                    filename=filename,
                    status="FAIL",
                    error_code="TOGGLE_BREAKS_HINTS" if affordance == "open_hint" else "SCAFFOLDING_AFFORDANCE_DROP",
                    message=f"Step {step_num}: {toggle_key} toggle removed '{affordance}'",
                    step_num=step_num
                )
        
        # Check hint preservation
        if toggle_policy.get("must_preserve_hints"):
            before_hints = before.get("hints", {})
            after_hints = after.get("hints", {})
            
            if before_hints.get("available") and not after_hints.get("available"):
                # Hints were available and removed
                if "open_hint" in after_affordances:
                    # But we have open_hint affordance, so it's OK
                    pass
                else:
                    return TransitionValidationResult(
                        filename=filename,
                        status="FAIL",
                        error_code="TOGGLE_BREAKS_HINTS",
                        message=f"Step {step_num}: Hints were available before toggle but not after",
                        step_num=step_num
                    )
            
            # Check cascade state preserved
            if (before_hints.get("available") and after_hints.get("available") and
                before_hints.get("cascade_state_key") != after_hints.get("cascade_state_key")):
                return TransitionValidationResult(
                    filename=filename,
                    status="FAIL",
                    error_code="TOGGLE_BREAKS_HINTS",
                    message=f"Step {step_num}: Cascade state key changed during toggle",
                    step_num=step_num
                )
        
        # Check slot preservation
        slot_check = self._check_slots_preserved(before, after, step_num, filename)
        if slot_check.status == "FAIL":
            return slot_check
        
        return self._check_forward_path_and_affordances(after, step_num, filename)
    
    def _check_hint_advance(self, before: Dict, after: Dict, step_num: int,
                           filename: str) -> TransitionValidationResult:
        """Validate hint cascade advance (monotonic actionability)."""
        
        before_hints = before.get("hints", {})
        after_hints = after.get("hints", {})
        
        # Cascade state should be preserved
        if before_hints.get("cascade_state_key") != after_hints.get("cascade_state_key"):
            return TransitionValidationResult(
                filename=filename,
                status="FAIL",
                error_code="TOGGLE_BREAKS_HINTS",
                message=f"Step {step_num}: Cascade state key changed during hint advance",
                step_num=step_num
            )
        
        # Step should increase (or stay same if exhausted)
        before_step = before_hints.get("step", 0)
        after_step = after_hints.get("step", 0)
        
        if after_step < before_step:
            return TransitionValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCAFFOLDING_POLICY_VIOLATION",
                message=f"Step {step_num}: Hint step decreased (H{before_step}→H{after_step})",
                step_num=step_num
            )
        
        # Effects must be present if hints available
        if after_hints.get("available"):
            payload = after_hints.get("payload", {})
            effects = payload.get("effects")
            
            if not effects or len(effects) == 0:
                return TransitionValidationResult(
                    filename=filename,
                    status="FAIL",
                    error_code="SCAFFOLDING_POLICY_VIOLATION",
                    message=f"Step {step_num}: Hints available but effects missing/empty",
                    step_num=step_num
                )
            
            # Check no single-answer modeling
            if "model" in effects:
                model_options = effects["model"].get("options", [])
                if len(model_options) == 1:
                    return TransitionValidationResult(
                        filename=filename,
                        status="FAIL",
                        error_code="SCAFFOLDING_POLICY_VIOLATION",
                        message=f"Step {step_num}: Model has single option (violates anti-teacher gate)",
                        step_num=step_num
                    )
        
        return self._check_forward_path_and_affordances(after, step_num, filename)
    
    def _check_slots_preserved(self, before: Dict, after: Dict, step_num: int,
                              filename: str) -> TransitionValidationResult:
        """Check that slot executability is preserved during narrowing."""
        
        before_options = before.get("options", [])
        after_options = after.get("options", [])
        
        # For each slot-bearing option in 'before', check if still executable in 'after'
        for b_opt in before_options:
            if not b_opt.get("required_slots"):
                continue
            
            # Find matching option in after (by option_id)
            a_opt = next((o for o in after_options if o.get("option_id") == b_opt.get("option_id")), None)
            
            if not a_opt:
                # Option was removed; that's OK (narrowing)
                continue
            
            # Check that slots are still executable
            b_tokens = b_opt.get("tokens", [])
            a_tokens = a_opt.get("tokens", [])
            b_selectors = b_opt.get("slot_selectors", {})
            a_selectors = a_opt.get("slot_selectors", {})
            
            has_tokens_before = len(b_tokens) > 0
            has_tokens_after = len(a_tokens) > 0
            has_selectors_before = len(b_selectors) > 0
            has_selectors_after = len(a_selectors) > 0
            
            executable_before = has_tokens_before or has_selectors_before
            executable_after = has_tokens_after or has_selectors_after
            
            if executable_before and not executable_after:
                return TransitionValidationResult(
                    filename=filename,
                    status="FAIL",
                    error_code="TOGGLE_BREAKS_SLOTS",
                    message=f"Step {step_num}: Option[{b_opt.get('option_id')}] lost slot executability",
                    step_num=step_num
                )
        
        return TransitionValidationResult(filename=filename, status="PASS")
    
    def _check_forward_path_and_affordances(self, state: Dict, step_num: int,
                                           filename: str) -> TransitionValidationResult:
        """Check dead-state rule and affordance requirements."""
        
        options = state.get("options", [])
        affordances = state.get("affordances", [])
        hints = state.get("hints", {})
        
        # Dead state rule
        has_options = len(options) >= 1
        has_hints = hints.get("available", False) and "open_hint" in affordances
        has_template_with_slots = False  # Simplified; would need to parse hints.payload.effects.structure
        
        forward_path = has_options or has_hints or has_template_with_slots
        
        if not forward_path:
            return TransitionValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCAFFOLDING_DEAD_STATE",
                message=f"Step {step_num}: No forward path (dead state)",
                step_num=step_num
            )
        
        # "what_can_i_say" must always be present
        if "what_can_i_say" not in affordances:
            return TransitionValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCAFFOLDING_AFFORDANCE_DROP",
                message=f"Step {step_num}: 'what_can_i_say' affordance missing (non-removable)",
                step_num=step_num
            )
        
        return TransitionValidationResult(filename=filename, status="PASS")


def run_transition_tests(golden_dir: str = "golden/transitions/v1") -> int:
    """Run transition tests on scaffolding fixtures."""
    
    print("=" * 80)
    print("SCAFFOLDING TRANSITION VALIDATOR — MandarinOS v1")
    print("=" * 80)
    
    validator = ScaffoldingPolicyValidator()
    
    # Collect fixtures
    golden_path = Path(golden_dir)
    
    if not golden_path.exists():
        print(f"ERROR: Golden transition directory not found: {golden_dir}")
        return 1
    
    pass_dir = golden_path / "pass"
    fail_dir = golden_path / "fail"
    
    pass_files = sorted(glob.glob(str(pass_dir / "*.json")))
    fail_files = sorted(glob.glob(str(fail_dir / "*.json")))
    
    if not pass_files and not fail_files:
        print(f"ERROR: No transition fixtures found in {golden_dir}")
        return 1
    
    print(f"\nFound {len(pass_files)} PASS fixtures and {len(fail_files)} FAIL fixtures\n")
    
    # Run PASS fixtures
    print("PASS FIXTURES (should all PASS):")
    print("-" * 80)
    
    pass_count = 0
    for filepath in pass_files:
        filename = Path(filepath).name
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                trace = json.load(f)
        except json.JSONDecodeError as e:
            result = TransitionValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCHEMA_INVALID",
                message=f"Invalid JSON: {e}"
            )
        else:
            result = validator.validate_transition_trace(trace, filename)
        
        status_symbol = "✅" if result.status == "PASS" else "❌"
        print(f"{status_symbol} {filename}")
        if result.error_code:
            print(f"   {result.error_code}: {result.message}")
        
        if result.status == "PASS":
            pass_count += 1
    
    print(f"\nPass fixtures: {pass_count}/{len(pass_files)} passed\n")
    
    # Run FAIL fixtures
    print("FAIL FIXTURES (should all FAIL):")
    print("-" * 80)
    
    fail_count = 0
    for filepath in fail_files:
        filename = Path(filepath).name
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                trace = json.load(f)
        except json.JSONDecodeError as e:
            result = TransitionValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCHEMA_INVALID",
                message=f"Invalid JSON: {e}"
            )
        else:
            result = validator.validate_transition_trace(trace, filename)
        
        expected_fail = result.status == "FAIL"
        status_symbol = "✅" if expected_fail else "❌"
        
        print(f"{status_symbol} {filename}")
        if result.error_code:
            print(f"   Expected fail: {result.error_code} — {result.message}")
        else:
            print(f"   ⚠️  Fixture did not fail as expected!")
        
        if expected_fail:
            fail_count += 1
    
    print(f"\nFail fixtures: {fail_count}/{len(fail_files)} failed as expected\n")
    
    # Summary
    print("=" * 80)
    all_pass_correct = pass_count == len(pass_files)
    all_fail_correct = fail_count == len(fail_files)
    overall_success = all_pass_correct and all_fail_correct
    
    if overall_success:
        print(f"✅ SCAFFOLDING VALIDATION PASSED: {pass_count} pass + {fail_count} fail fixtures")
        print("=" * 80)
        return 0
    else:
        if not all_pass_correct:
            failed_pass = len(pass_files) - pass_count
            print(f"❌ {failed_pass} pass fixture(s) failed unexpectedly")
        if not all_fail_correct:
            passed_fail = len(fail_files) - fail_count
            print(f"❌ {passed_fail} fail fixture(s) passed unexpectedly")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    exit_code = run_transition_tests()
    sys.exit(exit_code)
