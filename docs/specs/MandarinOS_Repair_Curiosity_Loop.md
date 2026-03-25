# MandarinOS Design Note — Curiosity, Repair, and Comprehension Loop

## Core Insight

MandarinOS must model not only:
- emergency phrases (fallback communication)

but also:
- **curiosity-driven follow-up**
- **comprehension repair before giving up**

The system should behave like a real conversation partner who:
1. becomes curious when something interesting is said
2. tries to understand unfamiliar input
3. only falls back when repair fails

---

## Problem

Current systems typically jump too quickly from:
→ "I don't understand"

to:
→ fallback / simplified options

This creates:
- shallow conversations
- reduced learning opportunity
- lack of realism

---

## Required Behaviour

### 1. Curiosity Trigger

When the user provides:
- interesting detail
- unexpected content
- partial understanding

The system should:
- show curiosity
- ask follow-up questions
- attempt to explore meaning

Examples:
- 这个很有意思，你可以多说一点吗？
- 为什么？可以解释一下吗？

---

### 2. Comprehension Repair Loop (Critical)

Before falling back, the system must attempt:

#### Step 1 — Probe Unknown Elements
Use targeted repair phrases:

- “[X] 是什么意思？”
- “我不明白 [X]。”
- “这个词什么意思？”
- “可以再说一次吗？”
- “可以简单一点说吗？”

#### Step 2 — Narrow Understanding
Try to isolate:
- 1–2 unknown words
- key concept

#### Step 3 — Re-attempt Understanding
- paraphrase
- confirm partial understanding
- ask clarification

---

### 3. Only Then → Fallback

Fallback (options / simplification) should occur:
- **only after repair attempts fail**

Fallback examples:
- selectable options
- simplified phrasing
- guided responses

---

## Design Principle

> **Do not give up early. Try to understand first.**

Conversation should model:
- persistence
- curiosity
- effort to understand

---

## Architectural Implications

### This is NOT:
- scoring problem
- selector problem

### This IS:
- conversation behaviour layer
- move_type / response pattern expansion
- content + flow design

---

## Future Integration

This behaviour will likely require:

- new conversational patterns (e.g. REPAIR + PROBE sequences)
- integration with ASR uncertainty signals
- linking to hint system (word-level understanding)

---

## Success Criteria

The system should:

- attempt to understand unknown input before fallback
- ask natural clarification questions
- isolate unknown vocabulary
- create a realistic “trying to understand” interaction
- only use emergency phrases as a last resort

---

## Summary

MandarinOS should simulate a partner who:

- gets curious
- tries to understand
- asks probing questions
- persists through confusion
- only gives up when necessary

This transforms the system from:
→ reactive chatbot

to:
→ active conversational participant
