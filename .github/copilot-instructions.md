# MandarinOS — GitHub Copilot Operating Instructions (v1)
_Last updated: 2026-01-25_

This file is intended to be used as **repository instructions** for GitHub Copilot and as a working contract for contributors.

If there is any conflict, follow .github/copilot-instructions.md first, then Design Constitution, then Developer Handoff. If still ambiguous, ask before coding.

## 1) Product intent (non-negotiable)
MandarinOS is a **mobile-first (iPhone-first)** Mandarin speaking trainer focused on:
- Short, repeatable dialogue turns
- Scaffolding that adapts based on evidence
- A “What can I say?” function that produces **appropriate, selectable answers** for the current turn

Success metric: in a diagnostic or practice session, the user can **almost always** select an answer that is:
1) contextually appropriate, and
2) matches the target frame pattern, and
3) includes required UI affordances (e.g., dropdown slots) when the frame requires them.

## 2) Core constraints (do not violate)
### 2.1 Mobile UX
- Assume primary interaction is iPhone Safari/Chrome and GitHub Mobile.
- UI must remain responsive; avoid heavy synchronous work on the main thread.
- Any new UI affordance must degrade gracefully if unavailable.

### 2.2 Deterministic option quality
- For every **user turn**, if `input_mode` is `tap`, the app must render **>= 3 options** unless explicitly suppressed for a specific step kind.
- One option must be the **gold** (exact target answer or exact target frame with required slots present).
- If gold cannot be generated, fall back to a **closest valid** option + show a clear “no exact match available” explanation in the hint panel (never silently fail).

### 2.3 Frame correctness (slots & dropdowns)
- If a frame format includes a slot (e.g., “我叫{NAME}。” or “我现在住在{CITY}。”), then the tap option must preserve the slot as a **dropdown/selector** (or an equivalent structured input), not a plain-text teacher sentence.
- It is acceptable to show both:
  - a concise frame option with dropdown(s), and
  - a fully-filled example sentence,
  but the dropdown version must not be missing when the step expects it.

### 2.4 Hint system is part of diagnosis
- Diagnostic must not rely on hint-only recovery; it must be able to present correct options without requiring hints.
- Hint button must be present for user turns whenever `hint_affordance_rendered.visible == true`.
- If input method changes (type → tap or tap → type), the hint system must:
  - preserve `hint_cascade_state` and
  - re-render the hint affordance correctly within the same turn.

### 2.5 Scaffolding / level accuracy
- A diagnostic cannot assign a level with “medium confidence” if multiple turns had **no valid options** (i.e., `option_count == 0` on a `tap` user turn, or gold missing repeatedly).
- When the UI/option system is degraded, diagnostic should record a **system fault flag** and output “level uncertain due to option-generation failures”.

## 3) Engineering tripwires (must implement)
These are guardrails that should fail fast in dev, log loudly in prod, and block PRs via tests/CI.

### 3.1 Turn option invariant
For any user turn:
- If `input_mode == "tap"` then:
  - `option_count >= 3`
  - `gold_option_present == true`
  - each option must pass `validateOption(option, targetItem)` (see below)

If any invariant fails:
- emit `turn_option_invariant_failed` event with:
  - run_id, turn_uid, target_item_id, input_mode, option_count, gold_present
  - a short `failure_reason` enum

### 3.2 Frame-slot invariant
If `target_item_id` resolves to a frame with slots:
- ensure at least one option is of type `FRAME_WITH_SLOTS` (or equivalent) and includes the slot metadata
- do not replace it with a fully-instantiated “teacher” sentence as the only valid candidate

If violated:
- emit `frame_slot_invariant_failed` event with `slot_schema`, `options_snapshot`

### 3.3 Hint affordance invariant
If `hint_affordance_rendered.visible == true` for the turn:
- UI must show a hint button
- on input mode toggle within the same turn, hint affordance must re-render consistently

If violated:
- emit `hint_affordance_invariant_failed` with `from_mode`, `to_mode`, `cascade_state_before`, `cascade_state_after`

### 3.4 Diagnostic confidence downgrade
If any invariant failed during diagnostic:
- downgrade `diagnostic_completed.confidence` to `"low"`
- annotate `diagnostic_completed` with `system_faults: [ ... ]`

## 4) Implementation expectations (Copilot guidance)
When asked to implement fixes, Copilot should:
1) **Reproduce from logs first**: identify the exact turn indices where `option_count == 0`, `gold_option_present == false`, or hint affordance mismatch.
2) **Patch the smallest surface area**: do not refactor architecture unless necessary.
3) **Add tests before/with the patch**:
   - Unit tests for option generation & validation
   - Integration-ish tests for “type → tap” and “tap → type” toggles preserving hint cascade
4) **Add explicit logging events** (tripwires above).
5) **Update a short CHANGELOG entry** describing what the user will observe is now fixed.

## 5) Option validation function (spec)
Define `validateOption(option, targetItem)` with these checks:
- `option.kind` matches allowed kinds for step (FRAME, WORD, FILLER, FREE_TEXT)
- If target requires slots, option must carry required slot metadata
- Option must be semantically compatible with the prompt intent (use intent tags if available)
- Option must be renderable in the current input mode (tap/type) without losing structure

## 6) Working protocol for this repo
- Do not change JSON schemas or content pack format without an explicit migration plan and a version bump.
- Treat content packs as user investment; preserve backward compatibility.
- Any PR that touches option generation, hint binding, or diagnostic scoring must include:
  - Before/after log snippets
  - New/updated tests
  - A short “risk and rollback” note

## 7) Where to put this file (recommended)
Place this file at:
- `.github/copilot-instructions.md`

## 8) Authoritative references:
- docs/mandarinos_design_constitution.txt (authoritative for UX rules)
- docs/MandarinOS Developer Handoff.txt (authoritative for architecture + data pack rules)
- `.github/pull_request_template.md` (include “tripwires added?” checkbox)
- `docs/` for the larger design constitution / developer handoff (link from README)

