<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class C: Historical context**
>
> - **Current use:** Retained as a historical selector-design specification.
> - **May guide current implementation:** No.
> - **Current authority:** Verified selector code and `docs/CONVERSATION_ARCHITECTURE.md`.
> - **Principal caution:** Its internal `LOCKED` language records design-phase intent and does not define the current selector implementation.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->


# MandarinOS Next Question Selector (v1) — LOCKED

Purpose:
Define how MandarinOS chooses the best next conversational move during a session.

The selector uses:
- conversation state
- learner capability map
- conversation energy model
- memory model
- persona data
- learning constraints

to choose the most natural and achievable next move.

--------------------------------------------------
1. Core Principle

MandarinOS prioritizes conversational continuity over difficulty escalation.

Questions should normally be:
- at the learner's comfort level
or
- slightly above comfort level

The goal is not to constantly push difficulty higher.

The goal is to keep the conversation alive and natural.

--------------------------------------------------
2. Selector Philosophy

MandarinOS is a conversation trainer.

Therefore the selector must optimize for:

1. conversational logic
2. learner success
3. topic continuity
4. anchor pattern reinforcement
5. slight stretch (only when natural)

Stretch is desirable only when it does not disrupt conversation flow.

--------------------------------------------------
3. Inputs to the Selector

The selector reads from six input groups.

A. Conversation State
- current engine
- conversation depth
- recent turns
- who spoke last

B. Capability Map
- engine capability scores
- move capability scores
- modality capability scores
- curiosity capability
- repair capability

C. Energy Model
- conversation momentum
- hesitation
- hint burden
- engagement signals

D. Memory Model
- facts learner shared
- what has already been asked
- persona knowledge

E. Persona Data
- persona interests
- persona conversation style
- persona bridge tendencies

F. Learning Constraints
- anchor phrases due
- vocabulary budget
- hint burden already used

--------------------------------------------------
4. Possible Output Types

The selector chooses among different conversational move types.

A. Simple question
Example:
你喜欢做什么？

B. Follow-up question
Example:
为什么？

C. Bridge question
Example:
那里的菜怎么样？

D. Simpler recovery question
Example:
好玩吗？

E. Repair support
Allow repair phrases or hints

F. Memory recall
Example:
你刚才说你喜欢成都，还想再去吗？

--------------------------------------------------
5. Candidate Question Generation

Candidate questions come from:

- current conversation engine
- engine bridge questions
- curiosity toolkit
- repair toolkit
- memory recall
- anchor reinforcement questions

The selector generates a small candidate set before scoring.

--------------------------------------------------
6. Hard Filters

Before scoring, eliminate candidates that are:

- recently asked
- contradictory to conversation memory
- too difficult for current capability
- lexically overloaded
- unrelated to current topic
- repetitive

--------------------------------------------------
7. Scoring Dimensions

Each candidate question receives scores in five areas.

A. Comprehensibility
Likelihood the learner can answer.

B. Relevance
Connection to the immediately previous turn.

C. Interest Value
Likelihood the answer will produce meaningful conversation.

D. Learning Value
Does the question reinforce useful patterns or anchors.

E. Stretch Value
Is the question slightly above comfort level.

Stretch value should have low weight compared to the other factors.

--------------------------------------------------
8. Scoring Priority

The selector should prioritize:

1. relevance / conversational logic
2. comprehensibility
3. interest value
4. learning value
5. stretch value

Stretch is a tiebreaker, not the main driver.

--------------------------------------------------
9. Engine Switching

The selector may switch engines when:

- learner stalls repeatedly
- current engine energy drops
- a natural bridge exists
- another engine has higher learner capability

Example:

Travel → Food

你去过成都吗？
那里的菜怎么样？

--------------------------------------------------
10. Hint-Aware Adjustment

If many hints were used recently:

The selector should:

- shorten sentence length
- reduce lexical complexity
- favor familiar patterns

Avoid introducing deeper questions immediately after heavy hint use.

--------------------------------------------------
11. Persona Realism

Questions should remain consistent with persona identity.

Example:

Travel persona:
travel, food, cities

Business persona:
work, companies, industry

This prevents the system from feeling artificial.

--------------------------------------------------
12. Memory Integration

Memory-aware questions receive a bonus score when:

- recall is natural
- topic continuity exists
- recall frequency is low enough to avoid repetition

Example:

你刚才说你喜欢摄影，现在还常拍吗？

--------------------------------------------------
13. Difficulty Bands

The selector should operate mostly within two bands.

Safe Zone
Questions comfortably answerable.

Comfort-Growth Zone
Questions slightly above current capability.

Avoid the Break Zone where questions are likely to stall conversation.

--------------------------------------------------
14. Example Decision

Learner says:
我去过成都，很喜欢。

Candidate questions:

什么时候去的？
成都怎么样？
那里的菜怎么样？
为什么喜欢？
你推荐吗？

Best likely selections:

那里的菜怎么样？
为什么喜欢？

These maintain conversation flow and learner success.

--------------------------------------------------
15. Minimum Viable Selector (v1)

Implementation steps:

1. Generate candidate questions
2. Filter unsuitable candidates
3. Score candidates using the five dimensions
4. Select highest score
5. Adjust difficulty if hint burden is high

--------------------------------------------------
16. Design Summary

The Next Question Selector answers:

What is the most natural, useful, and achievable next move for this learner right now?

This component operationalizes MandarinOS as an

Adaptive Conversation Operating System.
