
# MandarinOS Conversation Capability Map (v1)

Purpose:
Define how MandarinOS tracks a learner’s real conversational ability so the system can adapt what it asks next.

MandarinOS measures **conversation capability**, not static levels such as beginner/intermediate/advanced.

--------------------------------------------------
1. Core Principle

Learners have uneven abilities.

Example profile:

Identity conversations        strong
Travel conversations          moderate
Work conversations            weak
Listening                     strong
Character recognition         weak
Curiosity questions           moderate
Repair ability                strong

Therefore MandarinOS should track a **capability map**, not a single level.

--------------------------------------------------
2. Capability Categories

MandarinOS tracks capability across several dimensions.

A. Engine Capability
Ability to handle each conversation engine.

Example engines:
- Identity
- Place
- Family
- Travel
- Food
- Study / Work
- Interests

These scores determine which topics are safe or challenging.

--------------------------------------------------
B. Conversation Move Capability

How well the learner performs conversational actions.

Key moves:
- answering questions
- asking follow‑up questions
- expressing preferences
- talking about experiences
- giving reasons
- making recommendations
- reacting naturally

Example profile:

Answering questions         strong
Follow‑up questions         weak
Giving reasons              emerging
Recommendations             weak
Reactions                   moderate

--------------------------------------------------
C. Curiosity Capability

Ability to keep a conversation alive.

Examples:

为什么？       Why?
怎么样？       How is it?
你推荐吗？     Do you recommend it?
你怎么开始的？ How did you start?

These are core MandarinOS conversation skills.

--------------------------------------------------
D. Repair Capability

Ability to recover when understanding fails.

Examples:

什么？           What?
再说一次         Say it again
慢一点           Slower please
我不懂           I don't understand

Repair ability is critical for conversation survival.

--------------------------------------------------
E. Modality Capability

Track different language modalities separately.

Listening comprehension
Spoken response ability
Sentence reading ability
Character recognition
Pinyin dependence
Translation dependence

Example:

Listening            0.78
Speaking             0.52
Reading              0.36
Character recognition 0.22
Pinyin dependence    0.81
Translation dependence 0.64

This allows MandarinOS to adapt the UI presentation.

--------------------------------------------------
F. Lexical / Pattern Capability

Track key reusable patterns rather than isolated vocabulary.

Examples:
- anchor phrases mastered
- sentence patterns mastered
- high frequency words recognized
- character families recognized

--------------------------------------------------
3. Engine Capability Scores

Each conversation engine receives a confidence score.

Example:

Identity        0.85
Place           0.78
Travel          0.66
Food            0.72
Family          0.43
Study/Work      0.29
Interests       0.38

Interpretation:

0.80–1.00  comfortable
0.60–0.79  workable
0.40–0.59  emerging
below 0.40 fragile

--------------------------------------------------
4. Diagnostic Signals

Capability should be updated using behavioral signals.

Signals include:

Response quality
Response speed
Hint usage
Repair usage
Repetition success
Anchor recall

Hint cascade depth is especially informative.

Example interpretation:

No hints used → strong comprehension
Pinyin hint → reading difficulty
Translation hint → vocabulary gap
Word gloss hint → lexical gap
Etymology use → visual learning strategy

--------------------------------------------------
5. Adaptive Decisions Driven by the Map

The capability map influences:

Next question selection
Engine switching
Hint reveal timing
SM‑2 anchor scheduling
Progress feedback

Example adaptation:

If Work capability is weak:
→ ask simpler work questions
→ pivot to other engines when needed

--------------------------------------------------
6. Learner‑Facing Progress Display

Users should see meaningful capability feedback.

Example:

You can comfortably handle:
✓ Identity
✓ Place
✓ Travel

Emerging ability:
• Family
• Interests

Next focus:
• Study / Work

--------------------------------------------------
7. Minimum Viable Capability Map (v1)

Engine capability:
Identity
Place
Family
Travel
Food
Study/Work
Interests

Conversation moves:
Answer
Follow‑up
Give reason
Recommend
React

Curiosity capability

Repair capability

Modality capability:
Listening
Speaking
Reading
Character recognition
Pinyin dependence
Translation dependence

--------------------------------------------------
8. Design Summary

The capability map answers three key questions:

What can this learner talk about?
How independently can they do it?
What is the safest useful next stretch?

This capability‑based approach enables MandarinOS to behave as an
**Adaptive Conversation Operating System** rather than a static curriculum.
