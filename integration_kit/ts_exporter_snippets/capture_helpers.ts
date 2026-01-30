/**
 * MandarinOS TurnState Capture Helpers
 * 
 * These are utility functions to help construct TurnState objects
 * according to the schema. Adapt these patterns to your app's state structure.
 */

import { TurnState, Option } from "./trace_exporter";

/**
 * Construct a TurnState object from app state.
 * 
 * Your app should call this at each turn boundary.
 */
export function buildTurnState(config: {
  turn_id: string;
  scaffolding_level: "HIGH" | "MED" | "LOW";
  input_mode: "TAP" | "TYPE";
  affordances: string[];
  options: Option[];
  hints: any | null;
  slots: {
    required: string[];
    filled: Record<string, string>;
    selectors_present: string[];
  };
  cardPanel?: {
    open: boolean;
    card_id?: string | null;
    reveal_level?: number | null;
  };
  diagnostic?: {
    mode: "conversation" | "diagnostic";
    confidence: "HIGH" | "MED" | "LOW" | null;
  };
}): TurnState {
  return {
    turn_id: config.turn_id,
    scaffolding_level: config.scaffolding_level,
    input_mode: config.input_mode,
    affordances: config.affordances,
    options: config.options,
    hints: config.hints,
    slots: config.slots,
    diagnostic: config.diagnostic || { mode: "conversation", confidence: null },
    cardPanel: config.cardPanel,
  };
}

/**
 * Build affordances array based on current state.
 * 
 * Core affordances that should almost always be present:
 * - "what_can_i_say": user can see options or get help
 * - "open_hint": user can open a hint (if hints available)
 * 
 * Input-mode-specific affordances:
 * - "select_option" (TAP mode with options)
 * - "submit_response" (TYPE mode)
 */
export function buildAffordances(config: {
  hasOptions: boolean;
  hasHints: boolean;
  inputMode: "TAP" | "TYPE";
  canRequestHelp: boolean;
}): string[] {
  const aff: string[] = ["what_can_i_say"];

  if (config.hasHints) {
    aff.push("open_hint");
  }

  if (config.inputMode === "TAP" && config.hasOptions) {
    aff.push("select_option");
  }

  if (config.inputMode === "TYPE") {
    aff.push("submit_response");
  }

  if (config.canRequestHelp) {
    // optional, for user-initiated help requests
  }

  return aff;
}

/**
 * Validate that an option with required_slots has structure.
 * 
 * ⚠️ IMPORTANT: Do not flatten slots!
 * 
 * This helper checks that your option is structured correctly
 * for the trace.
 */
export function validateOptionStructure(option: Option): {
  valid: boolean;
  reason?: string;
} {
  const hasRequiredSlots = option.required_slots && option.required_slots.length > 0;

  if (!hasRequiredSlots) {
    return { valid: true };
  }

  // If option has required slots, it must have either tokens or slot_selectors
  const hasTokens = option.tokens && option.tokens.length > 0;
  const hasSelectors = option.slot_selectors && Object.keys(option.slot_selectors).length > 0;

  if (!hasTokens && !hasSelectors) {
    return {
      valid: false,
      reason: `Option ${option.option_id} has required_slots but no tokens or slot_selectors (flattened!)`,
    };
  }

  return { valid: true };
}

/**
 * Validate hint payload has effects block.
 */
export function validateHintStructure(hint: any): {
  valid: boolean;
  reason?: string;
} {
  if (!hint || !hint.available) {
    return { valid: true };
  }

  if (!hint.payload) {
    return {
      valid: false,
      reason: "Hint is available but payload is missing",
    };
  }

  if (!hint.payload.effects || Object.keys(hint.payload.effects).length === 0) {
    return {
      valid: false,
      reason: "Hint payload missing effects block",
    };
  }

  return { valid: true };
}

/**
 * Validate forward path (must have at least one way to proceed).
 */
export function validateForwardPath(state: TurnState): {
  hasPath: boolean;
  reason?: string;
} {
  // Path 1: Has options
  if (state.options && state.options.length > 0) {
    return { hasPath: true };
  }

  // Path 2: Has executable slots
  const { required, filled, selectors_present } = state.slots;
  if (required.length > 0) {
    const unfilled = required.filter((r) => !filled[r]);
    const hasSelectors = unfilled.some((u) => selectors_present.includes(u));
    if (hasSelectors) {
      return { hasPath: true };
    }
  }

  // Path 3: Has hints
  if (state.hints && state.hints.available && state.affordances.includes("open_hint")) {
    return { hasPath: true };
  }

  return {
    hasPath: false,
    reason: "No options, no slot selectors, no hint",
  };
}

/**
 * Example: Build a step event
 */
export function buildStepEvent(
  type: string,
  payload?: Record<string, any>
): {
  type: string;
  timestamp: string;
  payload?: Record<string, any>;
} {
  return {
    type,
    timestamp: new Date().toISOString(),
    payload: payload || {},
  };
}
