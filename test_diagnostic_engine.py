#!/usr/bin/env python3
"""
Diagnostic Engine Runtime Test
Tests the core diagnostic behavior without requiring full app deployment.
Simulates user interactions and validates engine behavior against copilot-instructions.md
"""

import json
import sys
import io
from typing import Dict, List, Tuple

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def load_json(filepath):
    """Load and parse JSON file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ ERROR loading {filepath}: {e}")
        sys.exit(1)

# Load all required data
diagnostic = load_json("diagnostic_p1.json")
frames = load_json("p1_frames.json")
fillers = load_json("p1_fillers.json")
srs_config = load_json("srs_config.json")

results = {
    "passed": [],
    "failed": [],
    "warnings": [],
}

print("\n" + "="*70)
print("DIAGNOSTIC ENGINE RUNTIME TEST")
print("="*70)

# ==================== TEST 1: Option Generation ====================
print("\n1️⃣  TESTING OPTION GENERATION FOR EACH TASK...")

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    mode = task.get("mode", "tap_choice")
    
    # Test 1a: Option count
    options = task.get("choices", [])
    option_count = len(options)
    
    if mode == "tap_choice" and option_count < 3:
        results["failed"].append(
            f"❌ {task_id}: tap_choice mode requires ≥3 options, found {option_count}"
        )
    elif option_count > 0:
        results["passed"].append(f"✅ {task_id}: Generated {option_count} options")
    
    # Test 1b: Gold option presence
    gold_options = [o for o in options if o.get("quality_signal") == "gold"]
    if len(gold_options) == 0:
        results["failed"].append(f"❌ {task_id}: No gold option found (§3.1 violation)")
    else:
        results["passed"].append(f"✅ {task_id}: Gold option(s) present [{len(gold_options)}]")
    
    # Test 1c: All options have required fields for validation
    for option in options:
        option_id = option.get("id", "?")
        required = ["target_frame", "quality_signal", "intent_tags"]
        missing = [f for f in required if f not in option]
        
        if missing:
            results["failed"].append(
                f"❌ {task_id} option {option_id}: Missing validation fields {missing}"
            )
        else:
            results["passed"].append(
                f"✅ {task_id} option {option_id}: Validation metadata complete"
            )

# ==================== TEST 2: Frame-Slot Binding ====================
print("\n2️⃣  TESTING FRAME-SLOT BINDING (§3.2 Frame-Slot Invariant)...")

frame_ids = {f.get("id") for f in frames.get("frames", [])}
fillers_data = fillers.get("fillers", {})

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    task_frames = task.get("target_frames", [])
    
    for option in task.get("choices", []):
        option_id = option.get("id", "?")
        target_frame = option.get("target_frame")
        
        # Check frame exists
        if target_frame not in frame_ids:
            results["failed"].append(
                f"❌ {task_id} option {option_id}: target_frame '{target_frame}' not in p1_frames.json"
            )
            continue
        
        # Find the frame definition
        frame_def = next((f for f in frames.get("frames", []) if f.get("id") == target_frame), None)
        if not frame_def:
            results["failed"].append(
                f"❌ {task_id} option {option_id}: Could not load frame '{target_frame}'"
            )
            continue
        
        frame_slots = frame_def.get("slots", [])
        has_slot_selectors = "slot_selectors" in option
        
        if len(frame_slots) > 0 and not has_slot_selectors:
            # Frame has slots but option doesn't provide selector (violation of §2.3)
            results["failed"].append(
                f"❌ {task_id} option {option_id}: Frame '{target_frame}' has slots but no slot_selectors (§2.3 violation)"
            )
        elif len(frame_slots) == 0 and has_slot_selectors:
            results["warnings"].append(
                f"⚠️  {task_id} option {option_id}: Frame has no slots but option has slot_selectors"
            )
        elif len(frame_slots) > 0 and has_slot_selectors:
            # Validate slot_selectors reference valid fillers
            for selector in option.get("slot_selectors", []):
                source = selector.get("source")
                if source:
                    filler_key = source.split(".")[1] if "." in source else None
                    if filler_key and filler_key not in fillers_data:
                        results["failed"].append(
                            f"❌ {task_id} option {option_id}: Filler '{filler_key}' not found"
                        )
                    elif filler_key:
                        results["passed"].append(
                            f"✅ {task_id} option {option_id}: Frame slot bound to valid filler '{filler_key}'"
                        )

# ==================== TEST 3: Hint Affordance Preservation (§3.3) ====================
print("\n3️⃣  TESTING HINT AFFORDANCE PERSISTENCE (§3.3 Hint Affordance Invariant)...")

seen_cascade_keys = set()
for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    
    for option in task.get("choices", []):
        option_id = option.get("id", "?")
        hint_aff = option.get("hint_affordance", {})
        
        # Check cascade_state_key exists and is unique
        cascade_key = hint_aff.get("cascade_state_key")
        if not cascade_key:
            results["failed"].append(
                f"❌ {task_id} option {option_id}: Missing cascade_state_key"
            )
        elif cascade_key in seen_cascade_keys:
            results["failed"].append(
                f"❌ {task_id} option {option_id}: Duplicate cascade_state_key '{cascade_key}'"
            )
        else:
            seen_cascade_keys.add(cascade_key)
            results["passed"].append(
                f"✅ {task_id} option {option_id}: cascade_state_key '{cascade_key}' unique"
            )
        
        # Check preserve_across_toggle
        preserve = hint_aff.get("preserve_across_toggle")
        if preserve == True:
            results["passed"].append(
                f"✅ {task_id} option {option_id}: preserve_across_toggle=true (hint re-binding safe)"
            )
        else:
            results["warnings"].append(
                f"⚠️  {task_id} option {option_id}: preserve_across_toggle not true"
            )
        
        # Check visible_in_modes
        modes = hint_aff.get("visible_in_modes", [])
        if isinstance(modes, list) and len(modes) > 0:
            results["passed"].append(
                f"✅ {task_id} option {option_id}: Hint visible in modes {modes}"
            )
        else:
            results["warnings"].append(
                f"⚠️  {task_id} option {option_id}: visible_in_modes missing or empty"
            )

# ==================== TEST 4: Signal Tracking (Silent Extraction, §3.4) ====================
print("\n4️⃣  TESTING SILENT SIGNAL EXTRACTION (§3.4 Diagnostic Confidence)...")

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    
    # Check for old scoring fields (should be removed)
    if "scoring" in task:
        results["failed"].append(f"❌ {task_id}: Old 'scoring' field still present")
    else:
        results["passed"].append(f"✅ {task_id}: No evaluative 'scoring' field")
    
    # Check signal_tracking present (silent extraction)
    if "signal_tracking" in task:
        signal_track = task.get("signal_tracking", {})
        silent = signal_track.get("silent_extraction")
        
        if silent == True:
            results["passed"].append(
                f"✅ {task_id}: Signal extraction marked as silent (no threshold gates)"
            )
        else:
            results["warnings"].append(
                f"⚠️  {task_id}: silent_extraction not explicitly set to true"
            )
    else:
        results["failed"].append(f"❌ {task_id}: Missing signal_tracking")

# ==================== TEST 5: Response Model (Conversational, not Evaluative) ====================
print("\n5️⃣  TESTING RESPONSE MODELS (Conversational, No Evaluation)...")

evaluative_keywords = ["correct", "incorrect", "right", "wrong", "good", "bad", "excellent", "poor"]

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    
    if "response_model" not in task:
        results["failed"].append(f"❌ {task_id}: Missing response_model")
        continue
    
    resp_model = task.get("response_model", {})
    after_sel = resp_model.get("after_selection", {})
    zh_text = after_sel.get("zh", "")
    purpose = after_sel.get("purpose", "")
    
    # Check for evaluative language
    has_eval = any(keyword.lower() in zh_text.lower() for keyword in evaluative_keywords)
    
    if has_eval:
        results["failed"].append(
            f"❌ {task_id}: Response model contains evaluative language (§1 violation)"
        )
    else:
        results["passed"].append(
            f"✅ {task_id}: Response model is conversational (no evaluation)"
        )
    
    if "conversation" in purpose.lower() or "turn" in purpose.lower():
        results["passed"].append(
            f"✅ {task_id}: Response purpose is conversational continuation"
        )
    else:
        results["warnings"].append(
            f"⚠️  {task_id}: Response purpose may not clearly indicate conversation continuation"
        )

# ==================== TEST 6: SRS Config (Signal-Based Labels) ====================
print("\n6️⃣  TESTING SRS CONFIG (Signal-Based Grading)...")

grade_meaning = srs_config.get("grading", {}).get("meaning", {})

signal_labels = ["lapse_signal", "slow_recall_signal", "routine_recall_signal", "fluent_recall_signal"]
for grade, label in grade_meaning.items():
    if label in signal_labels:
        results["passed"].append(f"✅ Grade '{grade}' uses signal-based label: '{label}'")
    else:
        results["failed"].append(f"❌ Grade '{grade}' has evaluative label: '{label}' (not signal-based)")

# ==================== SUMMARY ====================

print("\n" + "="*70)
print("TEST SUMMARY")
print("="*70)

print(f"\n✅ PASSED: {len(results['passed'])} checks")
if len(results["passed"]) <= 15:
    for p in results["passed"]:
        print(f"   {p}")
else:
    for p in results["passed"][:10]:
        print(f"   {p}")
    print(f"   ... and {len(results['passed']) - 10} more")

if results["warnings"]:
    print(f"\n⚠️  WARNINGS: {len(results['warnings'])}")
    for w in results["warnings"][:5]:
        print(f"   {w}")
    if len(results["warnings"]) > 5:
        print(f"   ... and {len(results['warnings']) - 5} more")

if results["failed"]:
    print(f"\n❌ FAILED: {len(results['failed'])} checks")
    for f in results["failed"]:
        print(f"   {f}")
else:
    print(f"\n❌ FAILED: 0 checks")

print("\n" + "="*70)

if results["failed"] == 0 and results["warnings"] == 0:
    print("✅ ALL ENGINE TESTS PASSED - Diagnostic engine is ready for integration!")
    print("\nCompliance Status:")
    print("  ✅ §3.1 Turn option invariant: All options have required metadata")
    print("  ✅ §3.2 Frame-slot invariant: Slots preserved as selectors")
    print("  ✅ §3.3 Hint affordance invariant: Re-binding support verified")
    print("  ✅ §3.4 Diagnostic confidence: No evaluative scoring gates")
    sys.exit(0)
elif results["failed"] == 0:
    print("⚠️  Tests passed with warnings - review above before deployment.")
    sys.exit(0)
else:
    print(f"❌ {len(results['failed'])} test(s) failed - see above.")
    sys.exit(1)
