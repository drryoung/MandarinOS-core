#!/usr/bin/env python3
"""
Test suite for diagnostic_p1.json
Validates structure, metadata completeness, and compliance with copilot-instructions.md
"""

import json
import sys
import io
from collections import defaultdict

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

# Load files
diagnostic = load_json("diagnostic_p1.json")
frames = load_json("p1_frames.json")
fillers = load_json("p1_fillers.json")

# Tracking
passed = []
failed = []
warnings = []

print("\n" + "="*70)
print("DIAGNOSTIC P1 VALIDATION TEST SUITE")
print("="*70)

# ==================== TEST 1: Metadata Completeness ====================
print("\n1️⃣  CHECKING OPTION METADATA COMPLETENESS...")
required_fields = ["id", "text_zh", "target_frame", "intent_tags", "quality_signal"]
optional_fields = ["hint_affordance", "slots_complete"]

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    for option in task.get("choices", []):
        option_id = option.get("id", "?")
        
        # Check required fields
        missing = [f for f in required_fields if f not in option]
        if missing:
            failed.append(f"❌ {task_id} option {option_id}: Missing fields [{', '.join(missing)}]")
        else:
            passed.append(f"✅ {task_id} option {option_id}: All required metadata present")
        
        # Check optional but recommended
        for f in optional_fields:
            if f not in option:
                warnings.append(f"⚠️  {task_id} option {option_id}: Missing recommended field '{f}'")

# ==================== TEST 2: Quality Signal Validity ====================
print("\n2️⃣  CHECKING QUALITY SIGNAL VALUES...")
valid_signals = ["gold", "distractor", "close_match"]

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    for option in task.get("choices", []):
        option_id = option.get("id", "?")
        signal = option.get("quality_signal")
        
        if signal and signal not in valid_signals:
            failed.append(f"❌ {task_id} option {option_id}: Invalid quality_signal '{signal}'")
        elif signal:
            passed.append(f"✅ {task_id} option {option_id}: quality_signal='{signal}'")

# ==================== TEST 3: Gold Option Presence ====================
print("\n3️⃣  CHECKING GOLD OPTION PRESENCE...")

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    gold_options = [o for o in task.get("choices", []) if o.get("quality_signal") == "gold"]
    
    if len(gold_options) == 0:
        failed.append(f"❌ {task_id}: No gold options found")
    else:
        gold_ids = [o.get("id") for o in gold_options]
        passed.append(f"✅ {task_id}: {len(gold_options)} gold option(s) [{', '.join(gold_ids)}]")

# ==================== TEST 4: Target Frame References ====================
print("\n4️⃣  CHECKING TARGET FRAME REFERENCES...")
valid_frame_ids = {f.get("id") for f in frames.get("frames", [])}

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    
    # Check task-level target_frames
    for target_frame in task.get("target_frames", []):
        if target_frame not in valid_frame_ids:
            failed.append(f"❌ {task_id}: target_frame '{target_frame}' not in p1_frames.json")
        else:
            passed.append(f"✅ {task_id}: target_frame '{target_frame}' valid")
    
    # Check option-level target_frames
    for option in task.get("choices", []):
        option_id = option.get("id", "?")
        opt_frame = option.get("target_frame")
        
        if opt_frame and opt_frame not in valid_frame_ids:
            failed.append(f"❌ {task_id} option {option_id}: target_frame '{opt_frame}' not found")
        elif opt_frame:
            passed.append(f"✅ {task_id} option {option_id}: target_frame '{opt_frame}' valid")

# ==================== TEST 5: Slot Selectors ====================
print("\n5️⃣  CHECKING SLOT_SELECTORS VALIDITY...")

# Extract fillers data (nested under "fillers" key)
fillers_data = fillers.get("fillers", {})

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    for option in task.get("choices", []):
        option_id = option.get("id", "?")
        
        if "slot_selectors" in option:
            for selector in option.get("slot_selectors", []):
                source = selector.get("source")
                if source:
                    parts = source.split(".")
                    if len(parts) == 2 and parts[0] == "fillers":
                        filler_key = parts[1]
                        if filler_key not in fillers_data or not isinstance(fillers_data[filler_key], list):
                            failed.append(f"❌ {task_id} option {option_id}: Filler '{filler_key}' not found or invalid")
                        else:
                            slot_name = selector.get("slot_name", "?")
                            count = len(fillers_data[filler_key])
                            passed.append(f"✅ {task_id} option {option_id}: slot '{slot_name}' → '{filler_key}' ({count} items)")
                    else:
                        failed.append(f"❌ {task_id} option {option_id}: Invalid source format '{source}'")

# ==================== TEST 6: Hint Affordance ====================
print("\n6️⃣  CHECKING HINT_AFFORDANCE STRUCTURE...")
seen_cascade_keys = set()

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    for option in task.get("choices", []):
        option_id = option.get("id", "?")
        
        if "hint_affordance" in option:
            h = option.get("hint_affordance", {})
            
            # Check cascade_state_key
            cascade_key = h.get("cascade_state_key")
            if not cascade_key:
                failed.append(f"❌ {task_id} option {option_id}: hint_affordance missing 'cascade_state_key'")
            elif cascade_key in seen_cascade_keys:
                failed.append(f"❌ {task_id} option {option_id}: Duplicate cascade_state_key '{cascade_key}'")
            else:
                seen_cascade_keys.add(cascade_key)
                passed.append(f"✅ {task_id} option {option_id}: cascade_state_key '{cascade_key}' unique")
            
            # Check preserve_across_toggle
            if h.get("preserve_across_toggle") != True:
                warnings.append(f"⚠️  {task_id} option {option_id}: preserve_across_toggle is not true")
            else:
                passed.append(f"✅ {task_id} option {option_id}: preserve_across_toggle=true")
            
            # Check visible_in_modes
            visible = h.get("visible_in_modes")
            if not visible or not isinstance(visible, list):
                failed.append(f"❌ {task_id} option {option_id}: visible_in_modes missing/invalid")
            else:
                passed.append(f"✅ {task_id} option {option_id}: visible_in_modes={visible}")
        elif "hints" in option:
            warnings.append(f"⚠️  {task_id} option {option_id}: Has hints but no hint_affordance metadata")

# ==================== TEST 7: Response Model ====================
print("\n7️⃣  CHECKING RESPONSE_MODEL...")

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    
    if "response_model" not in task:
        failed.append(f"❌ {task_id}: Missing response_model")
    else:
        rm = task.get("response_model", {})
        after_sel = rm.get("after_selection", {})
        
        if not after_sel.get("zh"):
            failed.append(f"❌ {task_id}: response_model.after_selection.zh missing")
        else:
            zh_text = after_sel.get("zh", "")[:30]
            passed.append(f"✅ {task_id}: response_model has conversational response")

# ==================== TEST 8: Signal Tracking ====================
print("\n8️⃣  CHECKING SIGNAL_TRACKING (no scoring)...")

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    
    if "signal_tracking" not in task:
        failed.append(f"❌ {task_id}: Missing signal_tracking")
    else:
        passed.append(f"✅ {task_id}: signal_tracking present")
    
    if "scoring" in task:
        failed.append(f"❌ {task_id}: Old 'scoring' field still present")

# ==================== TEST 9: No is_correct Fields ====================
print("\n9️⃣  CHECKING FOR REMOVED is_correct FIELDS...")
found_is_correct = False

for task in diagnostic.get("tasks", []):
    task_id = task.get("id", "?")
    for option in task.get("choices", []):
        option_id = option.get("id", "?")
        if "is_correct" in option:
            failed.append(f"❌ {task_id} option {option_id}: Old 'is_correct' field present")
            found_is_correct = True

if not found_is_correct:
    passed.append("✅ No 'is_correct' fields found")

# ==================== SUMMARY ====================
print("\n" + "="*70)
print("TEST SUMMARY")
print("="*70)

print(f"\n✅ PASSED: {len(passed)} checks")
if len(passed) <= 15:
    for p in passed:
        print(f"   {p}")
else:
    for p in passed[:10]:
        print(f"   {p}")
    print(f"   ... and {len(passed)-10} more")

if warnings:
    print(f"\n⚠️  WARNINGS: {len(warnings)}")
    for w in warnings[:10]:
        print(f"   {w}")
    if len(warnings) > 10:
        print(f"   ... and {len(warnings)-10} more")

if failed:
    print(f"\n❌ FAILED: {len(failed)} checks")
    for f in failed:
        print(f"   {f}")
else:
    print(f"\n❌ FAILED: 0 checks")

print("\n" + "="*70)

# Exit code
if not failed and not warnings:
    print("✅ ALL TESTS PASSED - diagnostic_p1.json is valid!")
    sys.exit(0)
elif not failed:
    print("⚠️  Tests passed with warnings - review them above.")
    sys.exit(0)
else:
    print(f"❌ {len(failed)} test(s) failed.")
    sys.exit(1)
