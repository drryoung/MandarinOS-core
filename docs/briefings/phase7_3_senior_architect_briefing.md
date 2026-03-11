
---

## 14) Design decision log (post-brief)

### 2026-03-05 — Single-tap word interaction (overrides protocol v1 §two-stage tap)
**Decision**: Word token clicks open card panel directly (single tap).
**Rationale**: Two-stage tap (micro-gloss → card) adds friction for the current
shell UI. The UX Protocol v1 two-stage tap is noted but deferred to a future phase
when the mobile UI shell is ready for inline mini-panel rendering.
**Protocol reference**: `MandarinOS_Conversation_UX_Protocol_v1.md` §word-tap.
**Reversibility**: `_openMicroGloss` function is retained in `app.js` and can be
rewired to stage-1 click when the protocol is enforced in a later phase.

