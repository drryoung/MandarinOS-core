# MandarinOS — Extensibility & Refinement Strategy Directive

## Core Decision
MandarinOS will evolve primarily by **adding higher-value frames and responses**, not by rewriting existing ones.

---

## Principles

### 1. Stable Backbone
Existing frames remain stable and form the backbone of the system.

### 2. Additive Growth
Improvements come from adding better frames, not replacing or restructuring existing ones.

### 3. Selector Independence
Selector logic must remain agnostic to specific frame IDs.  
**No hardcoding of frame-specific behavior.**

### 4. Competitive Coexistence
New frames should coexist with old ones.  
Higher-value frames will naturally surface through selection.

### 5. Soft Ordering
FRAME_ORDER is guidance, not a rigid script.  
It must allow insertion of new frames without breaking flow.

### 6. Builder-Centric Improvement
Future improvements should focus on:
- Frame quality
- Option relevance
- Distractor quality
- Tagging accuracy

### 7. Extensibility Constraint (Critical Rule)
Adding large numbers of new frames must NOT require changes to:
- selector logic
- scoring system
- runtime architecture

If it does, the architecture is incorrect.

### 8. Beta Testing Guidance
Feedback should be classified as:

| Feedback | Action |
|--------|--------|
| Awkward question | Add better frame |
| Repetition | Add variation |
| Flow issue | Selector tweak |
| Bad options | Builder fix |
| Interview feel | Future grammar (Phase 12) |

### 9. Value Density
Maintain coverage while increasing conversational value:
- more natural
- more specific
- more useful

---

## Summary
MandarinOS should evolve as a **growing network of conversational moves**, not a fixed script.

System stability is preserved while conversational quality improves through **content expansion, not system complexity**.
