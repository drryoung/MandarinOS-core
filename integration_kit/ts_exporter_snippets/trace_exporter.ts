/**
 * MandarinOS TurnState Trace Exporter - TypeScript Snippets
 * 
 * WARNING: This is pseudocode and pattern documentation, NOT a complete library.
 * 
 * Your app is responsible for:
 * 1. Defining where/when TurnState is computed
 * 2. Hooking into your event system (Redux, Event Emitter, Signals, etc.)
 * 3. Capturing before/after states at each turn transition
 * 4. Implementing the export logic per your framework
 * 
 * See: https://github.com/drryoung/MandarinOS-examples for real implementations.
 */

// ============================================================================
// INTERFACE: ITraceExporter
// ============================================================================
// Your app must implement this interface to export traces.

export interface ITraceExporter {
  /**
   * Add a step to the current trace.
   * @param event The event that triggered the step
   * @param beforeState TurnState before the event
   * @param afterState TurnState after the event
   */
  step(
    event: TraceEvent,
    beforeState: TurnState,
    afterState: TurnState,
    notes?: string
  ): void;

  /**
   * Export the accumulated trace to a JSON file.
   * @param path File path to write to
   */
  exportToFile(path: string): Promise<void>;

  /**
   * Export the trace as a JSON string.
   */
  exportAsJson(): string;
}

// ============================================================================
// TYPE: TraceEvent (matches Event.schema.json payload shapes)
// ============================================================================

export type TraceEventType =
  | "USER_SELECT_OPTION"
  | "USER_FILL_SLOT"
  | "USER_UNCERTAIN"
  | "OPEN_HINT"
  | "ADVANCE_HINT"
  | "TOGGLE_INPUT_MODE"
  | "SYSTEM_REPROMPT"
  | "SYSTEM_NARROW"
  | "SYSTEM_MODEL"
  | "SYSTEM_STRUCTURE"
  | "END_TURN";

export interface TraceEvent {
  type: TraceEventType;
  timestamp: string; // ISO-8601
  payload?: Record<string, any>;
}

// ============================================================================
// TYPE: TurnState (matches TurnState.schema.json)
// ============================================================================
// Minimal representation; refer to schema for full details.

export interface TurnState {
  turn_id: string;
  scaffolding_level: "HIGH" | "MED" | "LOW";
  input_mode: "TAP" | "TYPE";
  affordances: string[]; // e.g., ["what_can_i_say", "open_hint", "select_option"]
  options: Option[];
  hints: Hint | null;
  slots: {
    required: string[];
    filled: Record<string, string>;
    selectors_present: string[];
  };
  diagnostic: {
    mode: "conversation" | "diagnostic";
    confidence: "HIGH" | "MED" | "LOW" | null;
  };
}

export interface Option {
  option_id: string;
  option_kind?: string;
  text_zh?: string;
  text_en?: string;
  frame_id?: string;
  required_slots?: string[];
  tokens?: Array<{ token: string; type: string; slot?: string }>;
  slot_selectors?: Record<string, string[]>;
}

export interface Hint {
  available: boolean;
  step?: number;
  cascade_state_key?: string;
  payload?: Record<string, any>;
}

// ============================================================================
// CLASS: TraceBuilder (pseudocode pattern)
// ============================================================================

export class TraceBuilder implements ITraceExporter {
  private trace: any;
  private steps: any[] = [];

  constructor(config: {
    trace_id: string;
    app_build: {
      repo: string;
      commit: string;
      env: "dev" | "staging" | "prod";
    };
    locale: string;
    user_profile: {
      user_id: string;
      level: string;
    };
    scenario: {
      scenario_id: string;
      description: string;
      initial_task_id?: string | null;
    };
  }) {
    this.trace = {
      trace_version: "1.0",
      trace_id: config.trace_id,
      created_at: new Date().toISOString(),
      app_build: config.app_build,
      locale: config.locale,
      user_profile: config.user_profile,
      scenario: config.scenario,
      steps: this.steps,
    };
  }

  step(
    event: TraceEvent,
    beforeState: TurnState,
    afterState: TurnState,
    notes?: string
  ): void {
    const stepId = `step_${String(this.steps.length + 1).padStart(3, "0")}`;

    this.steps.push({
      step_id: stepId,
      event,
      before: beforeState,
      after: afterState,
      notes: notes || null,
    });
  }

  exportAsJson(): string {
    return JSON.stringify(this.trace, null, 2);
  }

  async exportToFile(path: string): Promise<void> {
    // TODO: Implement file writing for your platform/framework
    // Example (Node.js):
    // const fs = require('fs/promises');
    // await fs.writeFile(path, this.exportAsJson());
    throw new Error(
      "exportToFile() must be implemented for your platform (Node.js, Deno, etc.)"
    );
  }
}

// ============================================================================
// HELPER: How to capture TurnState in your app
// ============================================================================
/**
 * CAPTURE CHECKLIST:
 * 
 * At each turn boundary, you must capture:
 * 1. turn_id: Unique per turn (e.g., UUID or sequential)
 * 2. scaffolding_level: Current scaffolding level (HIGH/MED/LOW)
 * 3. input_mode: Current input method (TAP/TYPE)
 * 4. affordances: List of available interactions
 *    - "what_can_i_say": Available if user can see options/hints
 *    - "open_hint": Available if hints are present
 *    - "select_option": Available in TAP mode with options
 *    - "submit_response": Available in TYPE mode
 * 5. options: Current selectable options (MUST preserve structure):
 *    - Do NOT flatten slot-bearing frames (frame.intro.name with {NAME} → preserve tokens)
 *    - Include: option_id, option_kind, frame_id, required_slots, tokens, slot_selectors
 * 6. hints: Current hint state (null or { available, step, cascade_state_key, payload })
 *    - payload MUST have non-empty effects block
 * 7. slots: Summary of required/filled/selectors
 * 8. diagnostic: { mode: "conversation" | "diagnostic", confidence }
 * 
 * ⚠️  CRITICAL: Do not flatten options!
 *     If an option represents "我叫{NAME}。" with selectors ["Alice", "Bob"],
 *     it must be captured as:
 *     {
 *       option_id: "frame_name",
 *       option_kind: "FRAME_WITH_SLOTS",
 *       frame_id: "frame.intro.name",
 *       text_zh: "我叫{NAME}。",
 *       required_slots: ["NAME"],
 *       slot_selectors: { "NAME": ["Alice", "Bob"] }
 *     }
 */

// ============================================================================
// EXAMPLE: Pseudo-integration in a React component
// ============================================================================

/**
 * export function useTraceCapture() {
 *   const traceRef = useRef<TraceBuilder | null>(null);
 *   const [turnState, setTurnState] = useState<TurnState>(...);
 *
 *   useEffect(() => {
 *     // Initialize trace on scenario start
 *     traceRef.current = new TraceBuilder({
 *       trace_id: crypto.randomUUID(),
 *       app_build: {
 *         repo: "my-mandarin-app",
 *         commit: process.env.REACT_APP_GIT_COMMIT || "dev",
 *         env: process.env.NODE_ENV as "dev" | "staging" | "prod",
 *       },
 *       locale: "zh-CN",
 *       user_profile: { user_id: "user_123", level: "BEGINNER" },
 *       scenario: { scenario_id: "S1_basic_slot_fill", description: "..." },
 *     });
 *   }, []);
 *
 *   const captureStep = (event: TraceEvent) => {
 *     const beforeState = turnState;
 *     // ... compute afterState ...
 *     traceRef.current?.step(event, beforeState, afterState);
 *     setTurnState(afterState);
 *   };
 *
 *   const exportTrace = async () => {
 *     await traceRef.current?.exportToFile("traces/my_scenario.json");
 *   };
 *
 *   return { captureStep, exportTrace, traceJson: traceRef.current?.exportAsJson() };
 * }
 */

// ============================================================================
// EXPORT
// ============================================================================

export { TraceBuilder };
