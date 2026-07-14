<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as a Phase 12C proposed invariant set; some related behaviour may exist, but the document is not verified as a complete current contract.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current code and the applicable approved R2 contracts, especially `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, and `docs/ANSWER_SOURCE_CONTRACT.md`.
> - **Principal caution:** The word `INVARIANTS` does not create current authority. Each invariant must be verified against the R2 baseline before it is treated as protected behaviour.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Phase 12C — Invariants (do not violate without team sign-off)

These are the five invariants that define correct Phase 12C behavior.
They are not aspirational — they describe what the code ALREADY does.
Any future edit that would violate one of these MUST be flagged before merging.

---

## I-1 Unmatched-acceptance is authoritative

`classifyUnmatchedFreeAnswerDecision` is the **single decision point** for whether an
unmatched speech turn is accepted as an answer or rejected into the repair path.

- No other function may call `runTurn(true, { last_turn_was_answer: true })` directly
  on ASR input unless `classifyUnmatchedFreeAnswerDecision` returned `accept: true`.
- The reasons it may accept (`no_options`, `semantic_soft_match`,
  `open_ended_understandable`, `learner_skip_signal`, `one_strike_substantive_fallback`,
  `lexical_content_question`) are the complete list.  Adding a new accept-path requires
  a corresponding entry here.

## I-2 Trigger layer runs only after unmatched rejection

`selectRecoveryPhrase` / `getRecoveryPhraseForNotUnderstood` is called **only** when
`classifyUnmatchedFreeAnswerDecision` returned `accept: false`.

- The trigger layer MUST NOT pre-empt acceptance decisions.
- `computeRecoveryTriggerContext` inputs (asr_confidence, transcript, options,
  repeat_repair_count) must not be derived from accepted turns.

## I-3 probe_depth logic is server-owned and must not be altered client-side

`window._probeDepth` is reset to 0 on `opts.last_turn_was_answer === true` inside
`_runTurnInner`, and is read-only after that point in the request cycle.

- Client code must not mutate `_probeDepth` inside ASR handlers or option-click handlers.
- Server receives it as `conversation_state.probe_depth`; the server owns the reset rule.

## I-4 Selector scoring and _apply_move_type_filter are untouched overlays

`_apply_move_type_filter` (in `ui_server.py`) runs AFTER the Phase 10.5 selector
and BEFORE the Phase 12C arc bias pass.  Its output is the `filtered_chosen` field.

- No code added in Phase 12C may modify the scoring weights, FRAME_ORDER lists, or the
  allowed/fallback move-type tables inside `_apply_move_type_filter`.
- `_apply_discourse_coherence_guard` runs AFTER `_apply_move_type_filter` and may only
  swap `chosen` to an already-available alternative — it cannot inject a frame that
  would be rejected by the move-type filter.

## I-5 Recovery/turnaround options stay in the primary sentence strip

When `#sentenceOptionsContainer` is visible and contains at least one `.option-panel`:

- **All** learner-facing response options — including recovery phrases and turnaround
  phrases — must be appended **inside** `sentenceOptionsContainer` via
  `renderRecoveryPanelInto` or `renderSentenceOptions`.
- `#optionsContainer` (word-tile strip) MUST be hidden (`display:none`) in this state
  so there are never two competing response surfaces active at once.
- This rule is enforced by the post-render block in `_runTurnInner` that checks
  `soc.querySelector('.option-panel')` before hiding the word strip.
- No new code may show `#optionsContainer` while `sentenceOptionsContainer` is visible
  and non-empty.

---

## Verification

Run `tests/verify_phase12c.js` (Node, no dependencies) to check golden cases
for I-1, I-2, and I-5 client-side logic.
