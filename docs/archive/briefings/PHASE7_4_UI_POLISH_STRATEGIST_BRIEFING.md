# Phase 7.4 — UI Polish and Learner-Legibility Briefing (for Strategist / Reviewer)

**Date:** 2026-03-08  
**Purpose:** Brief ChatGPT (strategist/reviewer) on the final Phase 7.4 UI and legibility decisions so you can review and confirm that the Learning Interaction Layer and its presentation are ready to lock.  
**Your role:** Review the changes and rationale below; confirm acceptance or request adjustments. No code edits are required from you.

---

## 1. Scope of this review

This briefing covers **small but high-impact UI refinements** to the Phase 7 Learning Interaction Layer:

- Hint and `?` behaviour consistency (no “phantom” steps with no data).
- Color coding for **response options** (align with “user” color).
- Chinese **font strategy**: legible default vs artistic accents.

Core Phase 7 behaviour (frame display, card panel, hint cascade, options, “You said…”, trace/`conversationTranscript`) was already signed off in `PHASE7_COMPLETE_STRATEGIST_BRIEFING.md`. This is a **polish and legibility pass**, not a new feature phase.

---

## 2. Changes implemented

### 2.1 Hint / `?` consistency (“no step without data”)

- The main **Hint button** and each option’s **`?` button** now share a **single helper** to decide the button label based on **which hint levels actually have content** (pinyin, meaning, etymology).
- For both sentence and word/option contexts:
  - We **never show** a step label (e.g. “Meaning →”, “Etymology →”) if that level has **no content**.
  - Empty levels are skipped, and the cascade falls back to **“Hide hints →”** when there is nothing further to reveal.
  - This applies uniformly to:
    - Sentence-level hints
    - Word-in-frame hints
    - Option-level hints (when clicking `?` on a response option)

### 2.2 Response options in user green

- The **Chinese text for each response option** uses the **same green** as the user’s text in the transcript.
- This aligns color semantics:
  - **Partner text**: partner color (blue).
  - **User text + chosen response options**: user green.
- The intent is to make it visually obvious which side of the conversation the options belong to (they are potential *user* utterances).

### 2.3 Chinese font strategy (legibility first, Ma Shan Zheng as accent)

- **Default Chinese UI font** (for reading and choices) is now a **standard sans Chinese stack** (e.g. `Noto Sans SC`, `Microsoft YaHei`, system UI fallbacks).
- This applies to:
  - The **frame sentence** line.
  - The **Chinese transcript text**.
  - The **card main headword**.
  - The **Chinese in response options**.
- **Ma Shan Zheng** is no longer used for all Chinese, but is **retained as an accent** in the **etymology / character-components context**, where:
  - The learner is focused on **shape and components**, not fast reading.
  - The brush-style aesthetic adds value without harming legibility of the main flow.

---

## 3. Rationale for key decisions

### 3.1 Hint / `?` behaviour

- Strategically, hints are meant to be **predictable and trustworthy**: when the UI promises “Etymology →”, the learner should reliably see something, not a blank.
- A single helper for button labels:
  - Reduces divergence between Hint and `?`.
  - Makes future modifications to hint behaviour less error-prone.
  - Implements the agreed rule: **“don’t show options when there is no data.”**

### 3.2 Color semantics for options

- Using **user green** for response options reinforces that:
  - These are candidate **user utterances**.
  - The learner’s eventual choice (“You said: …”) is visually anchored in the same color space as their role in the transcript.
- This also cleans up the previous ambiguity where options were visually closer to partner text.

### 3.3 Fonts: aesthetics vs readability

- For **learners**, especially at early stages, legibility beats aesthetics.
- The prior “all Ma Shan Zheng” approach looked good but made longer texts and multi-turn review harder to parse at speed.
- The new strategy:
  - Keeps the main interaction layer in **highly readable, screen-optimised Chinese fonts**.
  - Preserves **Ma Shan Zheng** where it supports the learning goal (components, etymology) rather than where it competes with it.

---

## 4. Out of scope / unchanged

- No change to:
  - Trace / event schemas or contract.
  - Option generation logic, frame content, or correctness of distractors (still content/engine scope).
  - Phase locks or Design Constitution.
- This pass is **purely UI/UX polish** on top of already-signed-off Phase 7 behaviour.

---

## 5. How to spot-check (optional)

If you wish to verify:

- Run the UI server and open the UI as before.
- Confirm:
  - **Hint and `?`**: On sentences and options, you see no label for a level that has no content; cascade ends in **“Hide hints →”**.
  - **Colors**: Transcript: partner blue vs user green; response options’ Chinese text matches **user green**.
  - **Fonts**: Frame sentence, transcript Chinese, card headword, and options use a **clear sans Chinese font**; the **etymology / component view** uses **Ma Shan Zheng** for the character glyphs.

---

## 6. Requested sign-off

- Please confirm whether you:
  - **Approve** these UI and font-tuning decisions as aligned with Phase 7 goals and learner-first design, or
  - **Request adjustments** (e.g. different default font stack, color tweaks, or a different rule for when to show “Hide hints →”).

A simple affirmative (e.g. “Approved as briefed”) is sufficient for sign-off.

---

*Briefing prepared for ChatGPT as strategist/reviewer. Implementation by Cursor; Phase 7.4 scope and rationale agreed with project owner.*
