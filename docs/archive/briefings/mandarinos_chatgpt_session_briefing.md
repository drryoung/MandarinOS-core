
# MandarinOS – Architecture Decision Briefing
Date: 2026-03-05
Author: Raymond Young

## Purpose
This document briefs a new ChatGPT session on the current architectural decisions for MandarinOS and the next development tasks.

The project is temporarily pausing major UI feature development while the **conversation architecture** is redesigned to support deeper, more natural conversations.

---

# 1. Core Decision

The project is shifting focus from UI-driven conversation flow to **engine-driven conversation ladders guided by SRS**.

The objective is to ensure conversations support **8–12 natural turns per topic**, making repetition meaningful for learning.

---

# 2. Conversation Ladder Model

Each engine will conceptually follow this structure:

1. Opener  
2. Core Questions  
3. Treasure Questions (depth multipliers)  
4. Oxygen Loops (short reusable follow‑ups)  
5. Bridge Questions (topic transitions)

Typical engine target:

- 1 opener
- 2 core questions
- 2–3 treasure questions
- 6–8 loop questions
- 2 bridges

This allows natural conversation expansion without increasing vocabulary difficulty.

Example (Identity Engine):

你叫什么名字？  
你的名字是什么意思？  
谁给你取的名字？  
为什么？  
大家一般怎么叫你？  

---

# 3. Conversation Oxygen Set

Reusable follow‑up questions that extend almost any conversation:

为什么？ — Why  
谁？ — Who  
什么时候？ — When  
哪里？ — Where  
怎么样？ — How is it  
喜欢吗？ — Do you like it  
跟谁一起？ — With whom  
什么时候开始？ — When did it start  

These loops allow conversations to continue even with very basic vocabulary.

---

# 4. Role of SRS

The SRS **guides which frames appear**, not the conversation structure.

Architecture:

conversation engine  
→ candidate frames  
→ SRS weighting  
→ chosen frame  
→ UI presentation  

The UI should not determine conversation flow.

---

# 5. UI Development Status

Major UI flow work is temporarily paused.

UI infrastructure work may continue:

- clickable word tokens
- card panel
- hint cascade
- audio playback
- speech recognition handling
- option rendering

Areas considered provisional:

- conversation progression logic
- follow‑up question scheduling
- engine switching logic

---

# 6. Current Human Design Work

Raymond is editing a **Conversation Ladder Draft** document containing:

• current P1/P2 frames  
• proposed treasure questions  
• universal loop questions  
• bridge questions  

The goal is for Raymond (human designer) to curate the best conversation flows.

AI suggestions are only a starting point.

---

# 7. Expected Engine Improvements

Once the ladder document is finalized:

- new loop frames may be added
- treasure frames may be added
- bridge frames between engines may be added
- frames may receive tags such as:

treasure  
loop  
bridge  

These changes expand content but should not require runtime redesign.

---

# 8. Immediate Follow‑On Tasks

1. Review and refine the **conversation ladder draft**
2. Ensure each engine supports **8–12 conversational turns**
3. Remove weak or unnatural loop questions
4. Identify missing treasure nodes
5. Confirm bridges between engines

---

# 9. Next Engineering Phase

After ladder refinement:

1. Convert ladder specification into frame definitions
2. Extend engine frame sets
3. Allow SRS to weight candidate frames
4. Finalize conversation UI behaviour

---

# 10. Long‑Term Goal

MandarinOS should feel like a **curious conversation partner**, not a quiz engine.

Design priority:

interesting → natural → educational

---

End of briefing.
