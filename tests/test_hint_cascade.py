"""
test_hint_cascade.py — Hint Cascade Contract Validator
Per MandarinOS_hint_cascade_directive.txt

Validates:
1) Hint effects blocks are present and non-empty
2) Actionability monotonically increases (H0→H1→H2→H3)
3) No teacher single-answer modeling
4) Forward-path guarantee preserved through hint steps
5) Affordances don't drop after hint invocation

Error codes:
- HINT_NO_EFFECTS_BLOCK: Effects missing/empty
- HINT_NON_ACTIONABLE: Hint fails to change state
- TEACHER_SINGLE_ANSWER: model.options length == 1
- DEAD_STATE_NO_FORWARD_PATH: No actionable next step
- AFFORDANCE_DROP_ON_HINT: Affordances removed after hint
"""

import json
import sys
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class HintMetrics:
    """Pre/post metrics for a hint step."""
    step: int
    num_options: int
    num_frames: int
    slot_candidate_counts: Dict[str, int] = field(default_factory=dict)
    has_template: bool = False
    affordances: set = field(default_factory=set)
    
    def __repr__(self):
        return (f"H{self.step}(opts={self.num_options}, frames={self.num_frames}, "
                f"template={self.has_template}, affordances={self.affordances})")


@dataclass
class EffectsBlock:
    """Parsed effects block from hint payload."""
    narrow_frames: Optional[List[str]] = None
    narrow_options: Optional[List[str]] = None
    narrow_slot_domains: Dict[str, List[str]] = field(default_factory=dict)
    structure_template: Optional[List[str]] = None
    structure_slot_selectors: Dict[str, List[str]] = field(default_factory=dict)
    model_options: Optional[List[Dict]] = None
    
    def is_empty(self) -> bool:
        """Check if effects block has any content."""
        return (not self.narrow_frames and not self.narrow_options and 
                not self.narrow_slot_domains and not self.structure_template and
                not self.structure_slot_selectors and not self.model_options)
    
    def narrowed_dimension(self) -> Optional[str]:
        """Return which dimension was narrowed, if any."""
        if self.narrow_frames:
            return "frames"
        if self.narrow_options:
            return "options"
        if self.narrow_slot_domains:
            return "slots"
        return None
    
    def structured_dimension(self) -> Optional[str]:
        """Return which dimension was structured, if any."""
        if self.structure_template:
            return "template"
        if self.structure_slot_selectors:
            return "slot_selectors"
        return None


class HintCascadeValidator:
    """Validates hint cascade contracts per directive."""
    
    ERROR_CODES = {
        "HINT_NO_EFFECTS_BLOCK": "Effects missing or empty on hint",
        "HINT_NON_ACTIONABLE": "Hint fails to change state (not narrowing/structuring/modeling)",
        "TEACHER_SINGLE_ANSWER": "Model options == 1 (teacher single-answer violation)",
        "DEAD_STATE_NO_FORWARD_PATH": "No forward path after hint (no options, no template, no affordance)",
        "AFFORDANCE_DROP_ON_HINT": "Affordances removed after hint invocation",
    }
    
    def __init__(self):
        self.failures = []
        self.warnings = []
    
    def parse_effects(self, effects_dict: Dict) -> EffectsBlock:
        """Parse effects dictionary into structured EffectsBlock."""
        ef = EffectsBlock()
        
        if not effects_dict:
            return ef
        
        # Narrow dimension
        if "narrow" in effects_dict:
            narrow = effects_dict["narrow"]
            if "frames_allowed" in narrow:
                ef.narrow_frames = narrow["frames_allowed"]
            if "options_allowed" in narrow:
                ef.narrow_options = narrow["options_allowed"]
            if "slot_domains" in narrow:
                ef.narrow_slot_domains = narrow["slot_domains"]
        
        # Structure dimension
        if "structure" in effects_dict:
            structure = effects_dict["structure"]
            if "template" in structure:
                ef.structure_template = structure["template"]
            if "slot_selectors" in structure:
                ef.structure_slot_selectors = structure["slot_selectors"]
        
        # Model dimension
        if "model" in effects_dict:
            model = effects_dict["model"]
            if "options" in model:
                ef.model_options = model["options"]
        
        return ef
    
    def compute_metrics(self, turn_data: Dict) -> HintMetrics:
        """Compute metrics for a turn (pre-hint state)."""
        step = turn_data.get("hint_step", 0)
        options = turn_data.get("options", [])
        
        num_options = len(options)
        frames = set()
        slot_counts = {}
        has_template = False
        affordances = set(turn_data.get("affordances", []))
        
        for opt in options:
            if "frame_id" in opt:
                frames.add(opt["frame_id"])
            
            if "slot_selectors" in opt:
                for slot_name, candidates in opt.get("slot_selectors", {}).items():
                    if slot_name not in slot_counts:
                        slot_counts[slot_name] = 0
                    slot_counts[slot_name] = max(slot_counts[slot_name], len(candidates))
            
            if "tokens" in opt:
                if any(isinstance(t, dict) and t.get("type") == "slot" for t in opt["tokens"]):
                    has_template = True
        
        return HintMetrics(
            step=step,
            num_options=num_options,
            num_frames=len(frames),
            slot_candidate_counts=slot_counts,
            has_template=has_template,
            affordances=affordances
        )
    
    def check_effects_present(self, hint_payload: Dict, turn_id: str) -> bool:
        """Fail if effects missing."""
        effects = hint_payload.get("effects")
        if not effects:
            self.failures.append({
                "error_code": "HINT_NO_EFFECTS_BLOCK",
                "turn_id": turn_id,
                "message": "Hint payload missing 'effects' block",
                "hint_payload": hint_payload
            })
            return False
        
        ef = self.parse_effects(effects)
        if ef.is_empty():
            self.failures.append({
                "error_code": "HINT_NO_EFFECTS_BLOCK",
                "turn_id": turn_id,
                "message": "Effects block is empty (no narrow/structure/model)",
                "effects": effects
            })
            return False
        
        return True
    
    def check_actionability(self, pre_metrics: HintMetrics, post_metrics: HintMetrics, 
                           turn_id: str) -> bool:
        """Check hint-step delta rule: at least one dimension improves."""
        
        # Actionability criteria
        narrowed_frames = pre_metrics.num_frames > post_metrics.num_frames
        narrowed_options = pre_metrics.num_options > post_metrics.num_options
        slot_narrowed = self._slots_narrowed(pre_metrics.slot_candidate_counts, 
                                            post_metrics.slot_candidate_counts)
        slot_structured = self._slots_structured(pre_metrics.slot_candidate_counts,
                                                post_metrics.slot_candidate_counts)
        new_template = not pre_metrics.has_template and post_metrics.has_template
        new_affordances = post_metrics.affordances > pre_metrics.affordances
        
        actionable = (narrowed_frames or narrowed_options or slot_narrowed or 
                     slot_structured or new_template or new_affordances)
        
        if not actionable:
            self.failures.append({
                "error_code": "HINT_NON_ACTIONABLE",
                "turn_id": turn_id,
                "message": "Hint fails to narrow/structure/model (no state change)",
                "pre_metrics": str(pre_metrics),
                "post_metrics": str(post_metrics)
            })
            return False
        
        return True
    
    def check_no_teacher_single_answer(self, effects: EffectsBlock, turn_id: str) -> bool:
        """Fail if model.options == 1."""
        if effects.model_options and len(effects.model_options) == 1:
            self.failures.append({
                "error_code": "TEACHER_SINGLE_ANSWER",
                "turn_id": turn_id,
                "message": "Model options == 1 (violates anti-teacher gate)",
                "model_options_count": 1
            })
            return False
        
        if effects.model_options and len(effects.model_options) >= 2:
            # Verify all options are selectable (not teacher language)
            for i, opt in enumerate(effects.model_options):
                if self._has_teacher_language(opt.get("text_zh", "")):
                    self.warnings.append({
                        "code": "TEACHER_LANGUAGE_IN_MODEL",
                        "turn_id": turn_id,
                        "option_index": i,
                        "text": opt.get("text_zh")
                    })
        
        return True
    
    def check_forward_path(self, post_metrics: HintMetrics, turn_id: str) -> bool:
        """Ensure forward path exists after hint."""
        has_options = post_metrics.num_options >= 1
        has_template_with_slots = (post_metrics.has_template and 
                                   any(count > 0 for count in post_metrics.slot_candidate_counts.values()))
        has_hint_affordance = "open_hint" in post_metrics.affordances
        
        forward_path = has_options or has_template_with_slots or has_hint_affordance
        
        if not forward_path:
            self.failures.append({
                "error_code": "DEAD_STATE_NO_FORWARD_PATH",
                "turn_id": turn_id,
                "message": "No forward path after hint (no options, template+slots, or hint affordance)",
                "metrics": str(post_metrics)
            })
            return False
        
        return True
    
    def check_affordance_preservation(self, pre_affordances: set, post_affordances: set,
                                     turn_id: str) -> bool:
        """Fail if affordances dropped."""
        if pre_affordances > post_affordances:
            dropped = pre_affordances - post_affordances
            self.failures.append({
                "error_code": "AFFORDANCE_DROP_ON_HINT",
                "turn_id": turn_id,
                "message": f"Affordances removed: {dropped}",
                "pre_affordances": list(pre_affordances),
                "post_affordances": list(post_affordances),
                "dropped": list(dropped)
            })
            return False
        
        return True
    
    def _slots_narrowed(self, pre_counts: Dict, post_counts: Dict) -> bool:
        """Check if any slot domain narrowed."""
        for slot, post_count in post_counts.items():
            pre_count = pre_counts.get(slot, float('inf'))
            if pre_count > post_count:
                return True
        return False
    
    def _slots_structured(self, pre_counts: Dict, post_counts: Dict) -> bool:
        """Check if any slot went from 0 to >0 candidates."""
        for slot, post_count in post_counts.items():
            pre_count = pre_counts.get(slot, 0)
            if pre_count == 0 and post_count > 0:
                return True
        return False
    
    def _has_teacher_language(self, text: str) -> bool:
        """Check for teacher-feedback phrases."""
        forbidden = ["对", "错", "正确", "错误", "很棒", "太好了", "你说对了", 
                    "你做错了", "答对了", "答错了"]
        return any(phrase in text for phrase in forbidden)
    
    def validate_hint_sequence(self, sequence: List[Dict]) -> bool:
        """Validate a complete hint cascade H0→H1→H2→H3."""
        all_valid = True
        metrics_history = []
        
        for step_data in sequence:
            turn_id = step_data.get("turn_id", f"step_{len(metrics_history)}")
            hint_payload = step_data.get("hint_payload", {})
            post_turn = step_data.get("post_turn", {})
            
            # 1. Effects present
            if not self.check_effects_present(hint_payload, turn_id):
                all_valid = False
                continue
            
            # 2. Parse effects
            effects = self.parse_effects(hint_payload.get("effects", {}))
            
            # 3. No teacher single answer
            if not self.check_no_teacher_single_answer(effects, turn_id):
                all_valid = False
            
            # 4. Compute post-hint metrics
            post_metrics = self.compute_metrics(post_turn)
            
            # 5. Check forward path
            if not self.check_forward_path(post_metrics, turn_id):
                all_valid = False
            
            # 6. Check affordance preservation
            pre_metrics = self.compute_metrics(step_data.get("pre_turn", {}))
            if not self.check_affordance_preservation(pre_metrics.affordances,
                                                     post_metrics.affordances, turn_id):
                all_valid = False
            
            # 7. Check actionability (if not first step)
            if metrics_history:
                if not self.check_actionability(metrics_history[-1], post_metrics, turn_id):
                    all_valid = False
            
            metrics_history.append(post_metrics)
        
        return all_valid
    
    def report(self) -> Dict:
        """Generate validation report."""
        return {
            "total_failures": len(self.failures),
            "total_warnings": len(self.warnings),
            "failures": self.failures,
            "warnings": self.warnings,
            "passing": len(self.failures) == 0
        }


# ============================================================================
# SYNTHETIC FIXTURES
# ============================================================================

def fixture_hint_no_effects() -> List[Dict]:
    """MUST FAIL: Hint opens but effects block missing."""
    return [{
        "turn_id": "fixture_A_step0",
        "pre_turn": {
            "hint_step": 0,
            "options": [{"frame_id": "frame.greeting", "intent_tags": ["greeting"]}],
            "affordances": ["open_hint", "select_option"]
        },
        "hint_payload": {
            "text": "Try greeting someone",
            "effects": {}  # ❌ Empty effects
        },
        "post_turn": {
            "hint_step": 1,
            "options": [{"frame_id": "frame.greeting", "intent_tags": ["greeting"]}],
            "affordances": ["open_hint", "select_option"]
        }
    }]


def fixture_hint_narrows() -> List[Dict]:
    """PASS: Narrow works—frame domain reduced."""
    return [{
        "turn_id": "fixture_B_step0",
        "pre_turn": {
            "hint_step": 0,
            "options": [
                {"frame_id": "frame.greeting.hello", "intent_tags": ["greeting"]},
                {"frame_id": "frame.greeting.hihi", "intent_tags": ["greeting"]},
                {"frame_id": "frame.identity.name", "intent_tags": ["greeting"]}  # distractor
            ],
            "affordances": ["open_hint", "select_option"]
        },
        "hint_payload": {
            "text": "Focus on ways to say hello",
            "effects": {
                "narrow": {
                    "frames_allowed": ["frame.greeting.hello", "frame.greeting.hihi"]
                }
            }
        },
        "post_turn": {
            "hint_step": 1,
            "options": [
                {"frame_id": "frame.greeting.hello", "intent_tags": ["greeting"]},
                {"frame_id": "frame.greeting.hihi", "intent_tags": ["greeting"]}
            ],
            "affordances": ["open_hint", "select_option"]
        }
    }]


def fixture_hint_structures() -> List[Dict]:
    """PASS: Structure works—template + slot candidates provided."""
    return [{
        "turn_id": "fixture_C_step0",
        "pre_turn": {
            "hint_step": 0,
            "options": [],  # No options yet
            "affordances": ["open_hint"]
        },
        "hint_payload": {
            "text": "Tell them your name with this pattern",
            "effects": {
                "structure": {
                    "template": [
                        {"type": "text", "value": "我叫"},
                        {"type": "slot", "name": "NAME"},
                        {"type": "text", "value": "。"}
                    ],
                    "slot_selectors": {
                        "NAME": ["张三", "李四", "王五", "赵六"]
                    }
                }
            }
        },
        "post_turn": {
            "hint_step": 1,
            "options": [{
                "frame_id": "frame.identity.name",
                "tokens": [
                    {"type": "text", "value": "我叫"},
                    {"type": "slot", "name": "NAME"},
                    {"type": "text", "value": "。"}
                ],
                "slot_selectors": {
                    "NAME": ["张三", "李四", "王五", "赵六"]
                }
            }],
            "affordances": ["open_hint", "select_option", "fill_slot"]
        }
    }]


def fixture_hint_models() -> List[Dict]:
    """PASS: Model works—2+ complete options, no teacher language."""
    return [{
        "turn_id": "fixture_D_step0",
        "pre_turn": {
            "hint_step": 0,
            "options": [{"frame_id": "frame.opinion", "text_zh": "A"}],
            "affordances": ["open_hint", "select_option"]
        },
        "hint_payload": {
            "text": "Here are two ways to express an opinion",
            "effects": {
                "model": {
                    "options": [
                        {
                            "frame_id": "frame.opinion.like",
                            "text_zh": "我喜欢这个。",
                            "intent_tags": ["opinion_express"]
                        },
                        {
                            "frame_id": "frame.opinion.dislike",
                            "text_zh": "我不喜欢这个。",
                            "intent_tags": ["opinion_express"]
                        }
                    ]
                }
            }
        },
        "post_turn": {
            "hint_step": 1,
            "options": [
                {
                    "frame_id": "frame.opinion.like",
                    "text_zh": "我喜欢这个。",
                    "intent_tags": ["opinion_express"]
                },
                {
                    "frame_id": "frame.opinion.dislike",
                    "text_zh": "我不喜欢这个。",
                    "intent_tags": ["opinion_express"]
                }
            ],
            "affordances": ["open_hint", "select_option"]
        }
    }]


def fixture_teacher_single_answer() -> List[Dict]:
    """MUST FAIL: Model provides only 1 option (teacher single-answer)."""
    return [{
        "turn_id": "fixture_E_step0",
        "pre_turn": {
            "hint_step": 0,
            "options": [{"frame_id": "frame.greeting"}],
            "affordances": ["open_hint", "select_option"]
        },
        "hint_payload": {
            "text": "The correct answer is here",
            "effects": {
                "model": {
                    "options": [
                        {"frame_id": "frame.greeting.hello", "text_zh": "你好"}  # ❌ Only 1
                    ]
                }
            }
        },
        "post_turn": {
            "hint_step": 1,
            "options": [{"frame_id": "frame.greeting.hello", "text_zh": "你好"}],
            "affordances": ["open_hint", "select_option"]
        }
    }]


def fixture_affordance_drop() -> List[Dict]:
    """MUST FAIL: Affordances removed after hint."""
    return [{
        "turn_id": "fixture_F_step0",
        "pre_turn": {
            "hint_step": 0,
            "options": [{"frame_id": "frame.greeting"}],
            "affordances": ["open_hint", "select_option", "what_can_i_say"]
        },
        "hint_payload": {
            "text": "Hint",
            "effects": {
                "narrow": {
                    "frames_allowed": ["frame.greeting.hello"]
                }
            }
        },
        "post_turn": {
            "hint_step": 1,
            "options": [{"frame_id": "frame.greeting.hello"}],
            "affordances": ["select_option"]  # ❌ Lost open_hint and what_can_i_say
        }
    }]


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_tests():
    """Run all synthetic fixtures."""
    fixtures = [
        ("fixture_hint_no_effects", fixture_hint_no_effects(), True),  # Should fail
        ("fixture_hint_narrows", fixture_hint_narrows(), False),       # Should pass
        ("fixture_hint_structures", fixture_hint_structures(), False), # Should pass
        ("fixture_hint_models", fixture_hint_models(), False),         # Should pass
        ("fixture_teacher_single_answer", fixture_teacher_single_answer(), True),  # Should fail
        ("fixture_affordance_drop", fixture_affordance_drop(), True),  # Should fail
    ]
    
    total_tests = len(fixtures)
    passed = 0
    failed = 0
    
    print("=" * 80)
    print("HINT CASCADE VALIDATOR — SYNTHETIC FIXTURES")
    print("=" * 80)
    
    for fixture_name, sequence, should_fail in fixtures:
        validator = HintCascadeValidator()
        validator.validate_hint_sequence(sequence)
        report = validator.report()
        
        # Determine if test passed
        test_passed = (report["passing"] != should_fail)
        
        status = "✅ PASS" if test_passed else "❌ FAIL"
        expected = "should fail" if should_fail else "should pass"
        
        print(f"\n{fixture_name}")
        print(f"  Expected: {expected}")
        print(f"  Result: {'failed' if not report['passing'] else 'passed'}")
        print(f"  Status: {status}")
        
        if report["failures"]:
            print(f"  Failures: {len(report['failures'])}")
            for failure in report["failures"]:
                print(f"    - {failure['error_code']}: {failure['message']}")
        
        if report["warnings"]:
            print(f"  Warnings: {len(report['warnings'])}")
        
        if test_passed:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"RESULTS: {passed}/{total_tests} tests passed")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
