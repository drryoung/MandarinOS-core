import * as fs from "fs";

// Load diagnostic and supporting files
const diagnostic = JSON.parse(fs.readFileSync("diagnostic_p1.json", "utf8"));
const frames = JSON.parse(fs.readFileSync("p1_frames.json", "utf8"));
const fillers = JSON.parse(fs.readFileSync("p1_fillers.json", "utf8"));

const results = {
  passed: [],
  failed: [],
  warnings: [],
};

// ==================== VALIDATION TESTS ====================

// Test 1: All options have required metadata fields
console.log("\n1️⃣  CHECKING OPTION METADATA COMPLETENESS...");
const requiredFields = [
  "id",
  "text_zh",
  "target_frame",
  "intent_tags",
  "quality_signal",
];
const optionalButRecommended = ["hint_affordance", "slots_complete"];

diagnostic.tasks.forEach((task) => {
  task.choices.forEach((option) => {
    const missing = requiredFields.filter((f) => !(f in option));
    if (missing.length > 0) {
      results.failed.push(
        `❌ ${task.id} option ${option.id}: Missing fields [${missing.join(", ")}]`
      );
    } else {
      results.passed.push(
        `✅ ${task.id} option ${option.id}: All required metadata present`
      );
    }

    // Check recommended fields
    optionalButRecommended.forEach((f) => {
      if (!(f in option)) {
        results.warnings.push(
          `⚠️  ${task.id} option ${option.id}: Missing recommended field '${f}'`
        );
      }
    });
  });
});

// Test 2: All quality_signal values are valid
console.log("\n2️⃣  CHECKING QUALITY SIGNAL VALUES...");
const validSignals = ["gold", "distractor", "close_match"];
diagnostic.tasks.forEach((task) => {
  task.choices.forEach((option) => {
    const signal = option.quality_signal;
    if (signal && !validSignals.includes(signal)) {
      results.failed.push(
        `❌ ${task.id} option ${option.id}: Invalid quality_signal '${signal}'`
      );
    } else if (signal) {
      results.passed.push(
        `✅ ${task.id} option ${option.id}: quality_signal='${signal}'`
      );
    }
  });
});

// Test 3: Exactly >= 1 gold option per task
console.log("\n3️⃣  CHECKING GOLD OPTION PRESENCE...");
diagnostic.tasks.forEach((task) => {
  const goldOptions = task.choices.filter((o) => o.quality_signal === "gold");
  if (goldOptions.length === 0) {
    results.failed.push(`❌ ${task.id}: No gold options found`);
  } else if (goldOptions.length >= 1) {
    results.passed.push(
      `✅ ${task.id}: ${goldOptions.length} gold option(s) found [${goldOptions.map((o) => o.id).join(", ")}]`
    );
  }
});

// Test 4: target_frame references are valid
console.log("\n4️⃣  CHECKING TARGET FRAME REFERENCES...");
const validFrameIds = frames.frames.map((f) => f.id);
diagnostic.tasks.forEach((task) => {
  const targetFrame = task.target_frames?.[0];
  if (targetFrame && !validFrameIds.includes(targetFrame)) {
    results.failed.push(
      `❌ ${task.id}: target_frame '${targetFrame}' not found in p1_frames.json`
    );
  } else if (targetFrame) {
    results.passed.push(
      `✅ ${task.id}: target_frame '${targetFrame}' exists in p1_frames.json`
    );
  }

  task.choices.forEach((option) => {
    const optionFrame = option.target_frame;
    if (optionFrame && !validFrameIds.includes(optionFrame)) {
      results.failed.push(
        `❌ ${task.id} option ${option.id}: target_frame '${optionFrame}' not found`
      );
    } else if (optionFrame) {
      results.passed.push(
        `✅ ${task.id} option ${option.id}: target_frame '${optionFrame}' valid`
      );
    }
  });
});

// Test 5: slot_selectors reference valid filler sources
console.log("\n5️⃣  CHECKING SLOT_SELECTORS VALIDITY...");
diagnostic.tasks.forEach((task) => {
  task.choices.forEach((option) => {
    if (option.slot_selectors && Array.isArray(option.slot_selectors)) {
      option.slot_selectors.forEach((selector) => {
        const source = selector.source; // e.g., "fillers.names"
        if (source) {
          const [fillerType, fillerKey] = source.split(".");
          if (fillerType !== "fillers") {
            results.failed.push(
              `❌ ${task.id} option ${option.id}: Invalid filler type '${fillerType}'`
            );
          } else if (
            !fillers[fillerKey] ||
            !Array.isArray(fillers[fillerKey])
          ) {
            results.failed.push(
              `❌ ${task.id} option ${option.id}: Filler source '${fillerKey}' not found or not an array`
            );
          } else {
            results.passed.push(
              `✅ ${task.id} option ${option.id}: slot '${selector.slot_name}' references valid filler '${fillerKey}' (${fillers[fillerKey].length} items)`
            );
          }
        }
      });
    }
  });
});

// Test 6: hint_affordance has valid structure
console.log("\n6️⃣  CHECKING HINT AFFORDANCE STRUCTURE...");
const seenCascadeKeys = new Set();
diagnostic.tasks.forEach((task) => {
  task.choices.forEach((option) => {
    if (option.hint_affordance) {
      const h = option.hint_affordance;

      // Check required fields
      if (!h.cascade_state_key) {
        results.failed.push(
          `❌ ${task.id} option ${option.id}: hint_affordance missing 'cascade_state_key'`
        );
      } else {
        // Check for duplicates
        if (seenCascadeKeys.has(h.cascade_state_key)) {
          results.failed.push(
            `❌ ${task.id} option ${option.id}: Duplicate cascade_state_key '${h.cascade_state_key}'`
          );
        } else {
          seenCascadeKeys.add(h.cascade_state_key);
          results.passed.push(
            `✅ ${task.id} option ${option.id}: cascade_state_key '${h.cascade_state_key}' is unique`
          );
        }
      }

      if (h.preserve_across_toggle !== true) {
        results.warnings.push(
          `⚠️  ${task.id} option ${option.id}: hint_affordance 'preserve_across_toggle' is not true`
        );
      } else {
        results.passed.push(
          `✅ ${task.id} option ${option.id}: preserve_across_toggle=true`
        );
      }

      if (!h.visible_in_modes || !Array.isArray(h.visible_in_modes)) {
        results.failed.push(
          `❌ ${task.id} option ${option.id}: hint_affordance 'visible_in_modes' missing or not array`
        );
      } else {
        results.passed.push(
          `✅ ${task.id} option ${option.id}: visible_in_modes=${JSON.stringify(h.visible_in_modes)}`
        );
      }
    } else if (option.hints) {
      results.warnings.push(
        `⚠️  ${task.id} option ${option.id}: Has hints but no hint_affordance metadata`
      );
    }
  });
});

// Test 7: response_model structure
console.log("\n7️⃣  CHECKING RESPONSE_MODEL...");
diagnostic.tasks.forEach((task) => {
  if (!task.response_model) {
    results.failed.push(`❌ ${task.id}: Missing response_model`);
  } else {
    const rm = task.response_model;
    if (!rm.after_selection || !rm.after_selection.zh) {
      results.failed.push(
        `❌ ${task.id}: response_model.after_selection.zh missing`
      );
    } else {
      results.passed.push(
        `✅ ${task.id}: response_model has conversational continuation`
      );
    }
  }
});

// Test 8: signal_tracking present (no scoring)
console.log("\n8️⃣  CHECKING SIGNAL TRACKING (no scoring gates)...");
diagnostic.tasks.forEach((task) => {
  if (!task.signal_tracking) {
    results.failed.push(`❌ ${task.id}: Missing signal_tracking`);
  } else {
    results.passed.push(`✅ ${task.id}: signal_tracking present (no scoring)`);
  }

  // Check for old "scoring" field (should be removed)
  if (task.scoring) {
    results.failed.push(
      `❌ ${task.id}: Old 'scoring' field still present (should be removed)`
    );
  }
});

// Test 9: No is_correct fields (should all be replaced)
console.log("\n9️⃣  CHECKING FOR REMOVED is_correct FIELDS...");
let foundIsCorrect = false;
diagnostic.tasks.forEach((task) => {
  task.choices.forEach((option) => {
    if ("is_correct" in option) {
      results.failed.push(
        `❌ ${task.id} option ${option.id}: Old 'is_correct' field still present`
      );
      foundIsCorrect = true;
    }
  });
});
if (!foundIsCorrect) {
  results.passed.push(`✅ No 'is_correct' fields found (all removed correctly)`);
}

// ==================== SUMMARY ====================

console.log("\n" + "=".repeat(70));
console.log("TEST RESULTS SUMMARY");
console.log("=".repeat(70));

console.log(`\n✅ PASSED: ${results.passed.length} checks`);
if (results.passed.length <= 20) {
  results.passed.forEach((p) => console.log(`   ${p}`));
} else {
  console.log(`   (showing first 10 of ${results.passed.length})`);
  results.passed.slice(0, 10).forEach((p) => console.log(`   ${p}`));
  console.log(`   ... and ${results.passed.length - 10} more`);
}

if (results.warnings.length > 0) {
  console.log(`\n⚠️  WARNINGS: ${results.warnings.length}`);
  results.warnings.forEach((w) => console.log(`   ${w}`));
}

if (results.failed.length > 0) {
  console.log(`\n❌ FAILED: ${results.failed.length} checks`);
  results.failed.forEach((f) => console.log(`   ${f}`));
} else {
  console.log(`\n❌ FAILED: 0 checks`);
}

console.log("\n" + "=".repeat(70));

if (results.failed.length === 0 && results.warnings.length === 0) {
  console.log("✅ ALL TESTS PASSED - diagnostic_p1.json is valid!");
  process.exit(0);
} else if (results.failed.length === 0) {
  console.log(
    "⚠️  Tests passed with warnings - review them above before committing."
  );
  process.exit(0);
} else {
  console.log(`❌ ${results.failed.length} test(s) failed - see above.`);
  process.exit(1);
}
