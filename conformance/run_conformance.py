"""
run_conformance.py — Full-App Conformance Harness
Per MandarinOS_conformance_harness_directive.txt

Validates golden turn payloads against core->app contract:
1) Schema compliance (TurnResponse, Option, Hint, Effects, Token)
2) Core contract gates (effects presence, no single-answer, forward-path, affordances)
3) Option structure preservation (no flattening)

Error codes:
- SCHEMA_INVALID: JSON fails schema validation
- CONTRACT_EFFECTS_MISSING: Hint available but effects empty/missing
- CONTRACT_HINT_MODEL_SINGLE_ANSWER: Model has exactly 1 option
- CONTRACT_FORWARD_PATH_VIOLATION: No path forward (no options, no template+slots, no hint)
- CONTRACT_AFFORDANCE_MISSING_OPEN_HINT: Hints available but no open_hint affordance
- CONTRACT_OPTION_FLATTENED: Option has required_slots but no tokens/slot_selectors
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
import glob


# Simple schema validation (jsonschema would require extra dependencies)
# For MVP, we'll do structural checks directly


@dataclass
class ValidationResult:
    """Result of validating a single golden fixture."""
    filename: str
    status: str  # "PASS" or "FAIL"
    error_code: Optional[str] = None
    message: str = ""


class ConformanceValidator:
    """Validates TurnResponse payloads against core->app contract."""
    
    ERROR_CODES = {
        "SCHEMA_INVALID": "JSON does not conform to schema",
        "CONTRACT_EFFECTS_MISSING": "Hint available but effects empty/missing",
        "CONTRACT_HINT_MODEL_SINGLE_ANSWER": "Model options count == 1 (violates anti-teacher gate)",
        "CONTRACT_FORWARD_PATH_VIOLATION": "No forward path (no options, no template+slots, no hint with open_hint)",
        "CONTRACT_AFFORDANCE_MISSING_OPEN_HINT": "Hints available but open_hint not in affordances",
        "CONTRACT_OPTION_FLATTENED": "Option has required_slots but no tokens or slot_selectors",
    }
    
    def __init__(self):
        self.results = []
    
    def validate_turn_response(self, payload: Dict, filename: str) -> ValidationResult:
        """Validate a TurnResponse against all contract gates."""
        
        # 1. Structural validation
        if not isinstance(payload, dict):
            return ValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCHEMA_INVALID",
                message="Payload is not a JSON object"
            )
        
        # 2. Required top-level fields
        required = ["turn_id", "options", "affordances"]
        for field in required:
            if field not in payload:
                return ValidationResult(
                    filename=filename,
                    status="FAIL",
                    error_code="SCHEMA_INVALID",
                    message=f"Missing required field: {field}"
                )
        
        # 3. Validate options type
        if not isinstance(payload.get("options"), list):
            return ValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCHEMA_INVALID",
                message="options is not an array"
            )
        
        options = payload["options"]
        affordances = payload.get("affordances", [])
        hints = payload.get("hints", {})
        
        # 4. Gate A: Effects presence (if hints available)
        if hints and hints.get("available", False):
            effects_check = self._check_effects_present(hints, filename)
            if effects_check.status == "FAIL":
                return effects_check
            
            # Gate B: No single-answer modeling
            model_check = self._check_no_single_answer_model(hints, filename)
            if model_check.status == "FAIL":
                return model_check
            
            # Gate D: Affordance preservation (open_hint must be present)
            if "open_hint" not in affordances:
                return ValidationResult(
                    filename=filename,
                    status="FAIL",
                    error_code="CONTRACT_AFFORDANCE_MISSING_OPEN_HINT",
                    message="Hints available but 'open_hint' not in affordances"
                )
        
        # 5. Gate C: Forward-path guarantee
        forward_path_check = self._check_forward_path(options, hints, affordances, filename)
        if forward_path_check.status == "FAIL":
            return forward_path_check
        
        # 6. Contract: No flattened options
        for i, opt in enumerate(options):
            flatten_check = self._check_option_not_flattened(opt, i, filename)
            if flatten_check.status == "FAIL":
                return flatten_check
        
        # 7. Contract: Option structure (if tokens present, validate structure)
        for i, opt in enumerate(options):
            structure_check = self._check_option_structure(opt, i, filename)
            if structure_check.status == "FAIL":
                return structure_check
        
        return ValidationResult(
            filename=filename,
            status="PASS",
            message="All contract gates passed"
        )
    
    def _check_effects_present(self, hints: Dict, filename: str) -> ValidationResult:
        """Gate A: Effects block must be present and non-empty."""
        if not hints.get("available", False):
            return ValidationResult(filename=filename, status="PASS")
        
        payload = hints.get("payload", {})
        effects = payload.get("effects")
        
        if effects is None:
            return ValidationResult(
                filename=filename,
                status="FAIL",
                error_code="CONTRACT_EFFECTS_MISSING",
                message="Hint available but effects block missing"
            )
        
        if isinstance(effects, dict) and len(effects) == 0:
            return ValidationResult(
                filename=filename,
                status="FAIL",
                error_code="CONTRACT_EFFECTS_MISSING",
                message="Hint available but effects block is empty"
            )
        
        return ValidationResult(filename=filename, status="PASS")
    
    def _check_no_single_answer_model(self, hints: Dict, filename: str) -> ValidationResult:
        """Gate B: If effects.model.options exists, must have >=2."""
        payload = hints.get("payload", {})
        effects = payload.get("effects", {})
        
        if not effects or "model" not in effects:
            return ValidationResult(filename=filename, status="PASS")
        
        model = effects["model"]
        if not isinstance(model, dict):
            return ValidationResult(filename=filename, status="PASS")
        
        options = model.get("options", [])
        
        if isinstance(options, list) and len(options) == 1:
            return ValidationResult(
                filename=filename,
                status="FAIL",
                error_code="CONTRACT_HINT_MODEL_SINGLE_ANSWER",
                message="Model options contains exactly 1 option (violates anti-teacher gate)"
            )
        
        return ValidationResult(filename=filename, status="PASS")
    
    def _check_forward_path(self, options: List, hints: Dict, affordances: List,
                           filename: str) -> ValidationResult:
        """Gate C: Forward-path guarantee—at least one path must exist."""
        
        has_options = len(options) >= 1
        
        # Check for template + slot candidates (from hints)
        has_template_with_slots = False
        if hints and hints.get("available", False):
            payload = hints.get("payload", {})
            effects = payload.get("effects", {})
            
            if "structure" in effects:
                structure = effects["structure"]
                template = structure.get("template")
                slot_selectors = structure.get("slot_selectors", {})
                
                if template and any(len(candidates) > 0 for candidates in slot_selectors.values()):
                    has_template_with_slots = True
        
        has_hint_affordance = "open_hint" in affordances
        
        forward_path = has_options or has_template_with_slots or has_hint_affordance
        
        if not forward_path:
            return ValidationResult(
                filename=filename,
                status="FAIL",
                error_code="CONTRACT_FORWARD_PATH_VIOLATION",
                message="No forward path: no options, no template+slots, no hint affordance"
            )
        
        return ValidationResult(filename=filename, status="PASS")
    
    def _check_option_not_flattened(self, option: Dict, index: int, filename: str) -> ValidationResult:
        """Contract: Option is 'flattened' if required_slots but no tokens/selectors."""
        
        required_slots = option.get("required_slots", [])
        tokens = option.get("tokens")
        slot_selectors = option.get("slot_selectors")
        
        # If no required slots, no flattening issue
        if not required_slots:
            return ValidationResult(filename=filename, status="PASS")
        
        # If has required_slots but NEITHER tokens NOR slot_selectors, it's flattened
        has_tokens = tokens is not None and isinstance(tokens, list) and len(tokens) > 0
        has_selectors = slot_selectors is not None and isinstance(slot_selectors, dict) and len(slot_selectors) > 0
        
        if not has_tokens and not has_selectors:
            return ValidationResult(
                filename=filename,
                status="FAIL",
                error_code="CONTRACT_OPTION_FLATTENED",
                message=f"Option[{index}] has required_slots but no tokens or slot_selectors (flattened)"
            )
        
        return ValidationResult(filename=filename, status="PASS")
    
    def _check_option_structure(self, option: Dict, index: int, filename: str) -> ValidationResult:
        """Contract: Validate option structure (if tokens present)."""
        
        tokens = option.get("tokens")
        
        if tokens is None or not isinstance(tokens, list):
            return ValidationResult(filename=filename, status="PASS")
        
        # Validate each token
        for i, token in enumerate(tokens):
            if not isinstance(token, dict):
                return ValidationResult(
                    filename=filename,
                    status="FAIL",
                    error_code="SCHEMA_INVALID",
                    message=f"Option[{index}].tokens[{i}] is not an object"
                )
            
            token_type = token.get("type")
            
            if token_type == "literal":
                if "value" not in token:
                    return ValidationResult(
                        filename=filename,
                        status="FAIL",
                        error_code="SCHEMA_INVALID",
                        message=f"Option[{index}].tokens[{i}] is literal but missing 'value'"
                    )
            elif token_type == "slot":
                if "name" not in token:
                    return ValidationResult(
                        filename=filename,
                        status="FAIL",
                        error_code="SCHEMA_INVALID",
                        message=f"Option[{index}].tokens[{i}] is slot but missing 'name'"
                    )
            else:
                return ValidationResult(
                    filename=filename,
                    status="FAIL",
                    error_code="SCHEMA_INVALID",
                    message=f"Option[{index}].tokens[{i}] has invalid type: {token_type}"
                )
        
        return ValidationResult(filename=filename, status="PASS")


def run_conformance(golden_dir: str = "golden/turns") -> int:
    """Run conformance tests on golden fixtures."""
    
    print("=" * 80)
    print("CONFORMANCE RUNNER — MandarinOS Golden Fixtures")
    print("=" * 80)
    
    validator = ConformanceValidator()
    
    # Collect all golden fixtures
    golden_path = Path(golden_dir)
    
    if not golden_path.exists():
        print(f"ERROR: Golden fixture directory not found: {golden_dir}")
        return 1
    
    pass_dir = golden_path / "pass"
    fail_dir = golden_path / "fail"
    
    pass_files = sorted(glob.glob(str(pass_dir / "*.json")))
    fail_files = sorted(glob.glob(str(fail_dir / "*.json")))
    
    if not pass_files and not fail_files:
        print(f"ERROR: No golden fixtures found in {golden_dir}")
        return 1
    
    print(f"\nFound {len(pass_files)} PASS fixtures and {len(fail_files)} FAIL fixtures\n")
    
    # Run PASS fixtures (should all pass)
    print("PASS FIXTURES (should all PASS):")
    print("-" * 80)
    
    pass_count = 0
    for filepath in pass_files:
        filename = Path(filepath).name
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except json.JSONDecodeError as e:
            result = ValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCHEMA_INVALID",
                message=f"Invalid JSON: {e}"
            )
        else:
            result = validator.validate_turn_response(payload, filename)
        
        status_symbol = "✅" if result.status == "PASS" else "❌"
        print(f"{status_symbol} {filename}")
        if result.error_code:
            print(f"   Error: {result.error_code} — {result.message}")
        
        validator.results.append(result)
        if result.status == "PASS":
            pass_count += 1
    
    print(f"\nPass fixtures: {pass_count}/{len(pass_files)} passed\n")
    
    # Run FAIL fixtures (should all fail)
    print("FAIL FIXTURES (should all FAIL):")
    print("-" * 80)
    
    fail_count = 0
    for filepath in fail_files:
        filename = Path(filepath).name
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except json.JSONDecodeError as e:
            result = ValidationResult(
                filename=filename,
                status="FAIL",
                error_code="SCHEMA_INVALID",
                message=f"Invalid JSON: {e}"
            )
        else:
            result = validator.validate_turn_response(payload, filename)
        
        # For fail fixtures, we want them to have status == "FAIL"
        expected_fail = result.status == "FAIL"
        status_symbol = "✅" if expected_fail else "❌"
        
        print(f"{status_symbol} {filename}")
        if result.error_code:
            print(f"   Expected fail: {result.error_code} — {result.message}")
        else:
            print(f"   ⚠️  Fixture did not fail as expected!")
        
        validator.results.append(result)
        if expected_fail:
            fail_count += 1
    
    print(f"\nFail fixtures: {fail_count}/{len(fail_files)} failed as expected\n")
    
    # Summary
    print("=" * 80)
    all_pass_correct = pass_count == len(pass_files)
    all_fail_correct = fail_count == len(fail_files)
    overall_success = all_pass_correct and all_fail_correct
    
    if overall_success:
        print(f"✅ CONFORMANCE PASSED: {pass_count} pass fixtures + {fail_count} fail fixtures")
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
    exit_code = run_conformance()
    sys.exit(exit_code)
