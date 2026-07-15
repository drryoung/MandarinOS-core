# Strategist briefing — Phase 12B stabilization + UI flow hardening (latest session handoff)

**Purpose:** Bring ChatGPT (strategist) up to date on the latest implementation batch: conversation-flow repairs, sentence-option UI hardening, recovery/topic-shift behavior, and remaining strategic questions about engine diversity (family/work/etc).

**Date:** 2026-03-27  
**Audience:** ChatGPT in strategist role  
**Implementation context:** `scripts/ui_server.py`, `ui/app.js`, `ui/index.html`, `.cursor/rules/mandarinos-ui-objects.mdc`

---

## 1) Executive summary

- Conversation quality improved substantially in-session (user-reported).
- Multiple regressions were fixed across server and UI, especially around sentence options and recovery flow.
- A persistent rule was added to prevent future UI regressions from bypassing canonical option objects.
- One key selector logic bug was fixed: place-thread order now prevents asking "why do you like it there?" before "do you like it there?"
- Remaining strategic question: topic migration breadth (family/work/travel transitions) feels less evident than desired despite smoother local flow.

---

## 2) What shipped in this batch

### A. Stability + server lifecycle

- Recovered from repeated `ERR_CONNECTION_REFUSED` / `ERR_EMPTY_RESPONSE` episodes by restarting `ui_server.py` and validating endpoint health.
- Confirmed some stoppages were manual `KeyboardInterrupt` events (not runtime crashes).

### B. False-positive invariant warnings (tripwire noise)

- Diagnosed `turn_option_invariant_failed` warnings as largely legacy-noise in a sentence-options-first UI.
- Added gating in `ui/app.js` so invariant warnings are suppressed for:
  - direction/probe stub responses (`is_direction_response`, `is_probe_response`), and
  - responses with `sentence_options` (primary path).
- Practical effect: cleaner console signal; fewer misleading "no options" warnings when UI is functioning correctly.

### C. Conversation continuity bug: `slot_followup` engine leakage

- Root cause: follow-up frames like `f_generic_why` have engine `slot_followup`; client then persisted this as `current_engine`, causing immediate bridge drift.
- Fix in `ui_server.py`: when chosen frame engine is `slot_followup`, response `engine_id` now preserves caller engine (topic continuity).
- Effect: curiosity follow-ups stay in-topic instead of snapping to unrelated engines.

### D. Recovery behavior: graceful topic shifts

- Implemented natural transition utterances before bridge on "can't understand" / "move on" recovery actions.
- For `next_turn` recovery phrases, partner now acknowledges difficulty and signals pivot (e.g., "没关系，我们换个话题吧。") before moving on.
- Added zh+en transition variants for transcript readability.
- Effect: less abrupt thread termination; more human-like conversational repair.

### E. UI structure + controls (user-directed refinements)

- Restored and wired a suggestions button in action row.
- Renamed button text to `Suggested responses`.
- Button now truly toggles suggestions container visibility (show/hide), not a no-op.
- Repositioned controls per user preference:
  - `And you?` and `Why?` moved to the action row with microphone/suggestions controls.
  - English input/translate panel positioned above response option cards.
- Preserved canonical option-panel functionality (speaker, hint, token click insights).

### F. Response click behavior restored

- Reinstated behavior where clicking a response card first plays TTS of selected sentence, then advances turn.
- Previous regression had immediate advance without playback.

### G. Place-thread sequencing fix (presupposition repair)

- User-reported sequence issue: app asked `为什么喜欢那儿？` before `你喜欢那儿吗？`.
- Server fixes in `ui_server.py`:
  1. Reordered `_SLOT_FOLLOWUP_PREFERENCES["CITY"]` to ask `f_place_like_there` before `f_place_why_like`.
  2. Added `_FRAME_AFTER_ANY` dependency so `f_place_why_like` requires `f_place_like_there` context.
  3. Added deictic recency guard for `f_place_why_like` in `_deictic_context_fresh`.
- Effect: removes presupposition failures in place engine transitions.

---

## 3) Policy/rule updates for future sessions

### Added persistent Cursor rule

- New file: `.cursor/rules/mandarinos-ui-objects.mdc`
- Rule intent: all interactive response UI must use canonical `option-panel` object path.
- Prevents recurrence of custom rendering paths that lose speaker/hint/token-insight affordances.
- This rule is marked `alwaysApply: true`.

---

## 4) Current system behavior (practical status)

- Conversation now feels stronger and more coherent at local thread level (identity/story/place continuity).
- Recovery handling is less robotic; topic exits are acknowledged before pivot.
- Sentence cards are primary response mechanism; legacy options path remains partly active for compatibility.
- Some legacy validation warnings may still appear depending on payload shape, but they are less noisy and less likely to imply hard failure.

---

## 5) Open strategic question for ChatGPT

Despite strong local flow, user perception is that engine migration breadth is still not fully visible:

- Conversation does not consistently feel like it naturally explores `family`, `work`, and other engines after depth in current thread.
- User asks for strategist analysis of whether additional bridge/selector tuning is needed (without destabilizing current gains).

---

## 6) Suggested strategist focus areas

1. **Engine transition visibility**
   - Is `_BRIDGE_ENGINE_ORDER` / `_RECOVERY_BRIDGE_ENGINE_ORDER` weighting still too conservative?
   - Should there be explicit "topic diversity" pressure after N turns in same engine?

2. **Thread closure heuristics**
   - Define clearer "satisfying closure" detection for a thread before bridging.
   - Avoid both abrupt jumps and over-staying in one engine.

3. **Observability metrics**
   - Recommend concrete metrics (e.g., median engines/session, median turns/engine, bridge quality score, abrupt-bridge rate).

4. **Validation alignment**
   - Should legacy option invariant checks be fully split from sentence-option checks to reduce conceptual mismatch?

---

## 7) Files changed in this session window (high signal)

- `scripts/ui_server.py`
- `ui/app.js`
- `ui/index.html`
- `.cursor/rules/mandarinos-ui-objects.mdc`

---

## 8) Paste-in prompt for ChatGPT strategist

> Read `docs/briefings/PHASE_12B_STABILIZATION_AND_UI_FLOW_STRATEGIST_BRIEFING.md` as the current handoff. Please provide: (A) an assessment of whether engine diversity is under-realized despite improved local flow; (B) the minimum safe selector/bridge changes to improve transitions to family/work/etc; (C) guardrails to preserve the new gains in continuity and repair behavior; and (D) 3-5 measurable diagnostics to validate improvement.

---

*End of briefing.*
