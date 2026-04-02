# MandarinOS Phase Alignment Brief (12C, 12C.1, 12D)

## Purpose
Ensure consistent implementation and understanding of:
- Phase 12C (Repair → Comprehension)
- Phase 12C.1 (Reciprocity & Exploration)
- Phase 12D (Meaning + Move Overlay)

This document is authoritative for Cursor.

---

# 1. Phase Definitions (Canonical)

## Phase 12C — Repair to Comprehension

### Core Objective
When the learner is not understood, the system must attempt a **meaningful clarification step** before fallback.

### Trigger
- User input unclear / not understood / ASR mismatch

### Required Behavior
1. Soft repair (low pressure)
2. One targeted clarification attempt
3. Only then fallback

### Examples
- “你是说工作还是学习？”
- “你想表达你很忙吗？”

### Non-goals
- No cultural explanation
- No interpretation of partner meaning
- No strategic advice

---

## Phase 12C.1 — Reciprocity & Exploration Stability

### Core Objective
Ensure conversation can **reverse direction** and allow user to explore persona naturally.

### Trigger
- User asks question
- User shifts direction
- “你呢？” turn

### Required Behavior
1. Recognize user question intent
2. Persona responds coherently
3. Persona reveals progressive depth
4. No forced return to previous flow
5. Smooth continuation after exploration

### Examples
User: “你做什么工作？”
System: responds + continues naturally

### Non-goals
- No repair logic
- No interpretation overlay

---

## Phase 12D — Meaning + Move Overlay

### Core Objective
Help user interpret ambiguous responses and decide next action.

### Trigger
- Ambiguous partner language

### Required Behavior
- Show likely meaning
- Show 2–3 safe next moves

### Non-goals
- No engine changes
- No conversation control

---

# 2. Clean Separation

| Phase | Direction | Function |
|------|--------|---------|
| 12C | User → System | Repair understanding |
| 12C.1 | User ↔ Persona | Enable exploration |
| 12D | Persona → User | Interpret + act |

---

# 3. Implementation Rules

## MUST NOT
- Modify Phase 6 runtime behavior
- Merge these phases into one system
- Add complexity to selector

## MUST
- Keep layers separate
- Implement minimal-diff changes
- Ensure fail-soft behavior

---

# 4. Priority Order

1. Finish 12C (repair stability)
2. Stabilize 12C.1 (reciprocity)
3. Then implement 12D (overlay)

---

# 5. Acceptance Criteria

## 12C
- System attempts clarification before fallback
- Repair feels natural and low-pressure

## 12C.1
- User can ask questions freely
- Persona responds with depth
- No forced topic snapping

## 12D
- Meaning + Move appears when relevant
- Helps decision-making without interrupting flow

---

# 6. Final Principle

Do not optimize for:
- correctness
- completeness

Optimize for:
- conversation survival
- interaction continuity
- user confidence under uncertainty

---

End of Brief
