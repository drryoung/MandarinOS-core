<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class D: Superseded**
>
> - **Current use:** Retained for traceability of the original version-one project roadmap.
> - **May guide current implementation:** No.
> - **Current authority:** The nine-document R2 architecture-governance package. Within the roadmap document lineage, `docs/project/MandarinOS_project_plan_v2.md` is the latest named version, but it remains a class-F proposal rather than implementation authority.
> - **Principal caution:** Version one has been superseded within the roadmap lineage. Neither the v1 nor v2 roadmap overrides verified code or the approved R2 governance documents.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS Development Roadmap (Strategic Plan v1)

Purpose: Align ChatGPT (strategist), Cursor (architect/programmer), and
the project owner (reviewer) around a clear development roadmap leading
to personal testing and closed beta.

**Current status (2026-03-12):** Phase 9 signed off by strategist (see
`docs/phases/MandarinOS_Phase9_Signoff.md`). Project owner proceeding to
**personal alpha testing** before Phase 10.

------------------------------------------------------------------------

## Phase Overview

Phase 7 Learning Interaction Layer\
Phase 8 Conversation Loop UI\
Phase 9 Conversation Engine Integration\
Phase 10 Memory + Persona Foundations\
Phase 11 Personal Alpha Testing\
Phase 12 Closed Beta (10--100 users)\
Phase 13 Data‑Driven Iteration

------------------------------------------------------------------------

## Phase 7 --- Learning Interaction Layer

Goal: Ensure the learner can understand sentences and respond.

Scope: - Frame display - Word click → card panel - Hint cascade (pinyin
→ meaning → etymology) - Response options - "You said" confirmation

Acceptance criteria: - Hints render reliably - Response options
selectable - Card panels stable - No runtime crashes - Responses
recorded in trace

Reviewer responsibilities: - Evaluate comprehension flow - Evaluate hint
usefulness - Evaluate clarity of response options

Cursor responsibilities: - Finalize hint cascade - Implement response
options UI - Implement "You said" confirmation

------------------------------------------------------------------------

## Phase 8 --- Conversation Loop UI

Goal: Turn sentence practice into a visible conversation.

New UI component: Conversation transcript panel.

Example flow: AI: 你叫什么名字？ You: 我叫 Raymond。 AI: 很高兴认识你。
AI: 你呢？

Features: - Transcript panel - Partner acknowledgement - Reciprocity
turn - Question audio - Turn markers

Acceptance criteria: User experiences a clear multi‑turn interaction.

------------------------------------------------------------------------

## Phase 9 --- Conversation Engine Activation  ✅ Signed off 2026-03-12

Goal: Activate the Next Question Selector v1.

Inputs: - conversation state - capability map - memory - energy model -
persona data

Outputs: - follow‑up question - bridge to another topic - repair move -
curiosity prompt

Acceptance criteria: - Engine switching works - Conversation continues
across topics - No conversational dead ends

------------------------------------------------------------------------

## Phase 10 --- Memory + Persona

Goal: Make conversations personal and persistent.

Memory items: - name - hometown - job/study - family - favourite food

Persona network: Multiple characters that the learner can talk to.

Acceptance criteria: Conversation feels continuous across sessions.

------------------------------------------------------------------------

## Phase 11 --- Personal Alpha Testing

Goal: Determine whether MandarinOS helps the project owner personally.

Testing duration: 2--4 weeks

Evaluation questions: - Does recall improve? - Does speaking confidence
improve? - Are conversations sustained longer? - Do hints meaningfully
assist comprehension?

Data to collect: - session length - hint usage - response success rate -
topic transitions

------------------------------------------------------------------------

## Phase 12 --- Closed Beta

Participants: 10--100 learners.

Metrics: - session duration - conversation depth - hint usage - drop‑off
points - engine transitions

Critical user feedback question: "Does this feel like a conversation?"

------------------------------------------------------------------------

## Phase 13 --- Iteration Cycle

Improve based on beta feedback: - Next Question Selector logic -
Curiosity prompts - Persona realism - Speech input - Vocabulary coverage

------------------------------------------------------------------------

## Implementation Discipline

Cursor must: - Implement one feature at a time - Modify minimal files
per step - Preserve runtime stability - Stop after each change for
review
