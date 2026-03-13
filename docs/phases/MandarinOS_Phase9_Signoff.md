# MandarinOS --- Phase 9 Completion & Strategist Sign‑Off

**Project:** MandarinOS\
**Phase:** Phase 9 --- Conversation Engine Integration\
**Date:** 2026-03-12\
**Reviewer Role:** Senior Strategist / Architecture Reviewer\
**Implementation:** Cursor (architect + programmer)

------------------------------------------------------------------------

# 1. Phase Objective

Phase 9 introduced the **conversation engine selector**, allowing
MandarinOS to automatically choose the next conversational frame during
dialogue.

Prior to Phase 9, conversation flow required manual frame selection.\
Phase 9 enables **automatic dialogue progression** within and across
conversation engines.

This phase completes the **core MandarinOS conversational loop**:

Partner Question\
→ User Response\
→ Partner Acknowledgement\
→ Reciprocity (你呢？)\
→ Selector chooses next question\
→ Conversation continues

This represents the first operational version of a **self-driving
Mandarin conversation system**.

------------------------------------------------------------------------

# 2. Architecture Constraints

Phase 9 was implemented under strict architecture constraints.

The **Phase 6 runtime architecture remains locked and unchanged**.

The selector and conversation control logic were implemented entirely
within:

-   orchestration layer
-   server request path
-   conversation state management

Runtime components that remain untouched:

-   runtime artifacts
-   engine.process_turn
-   runtime schemas
-   trace contract
-   card resolver and hint logic

This preserves the **deterministic runtime architecture** established in
Phase 6.

------------------------------------------------------------------------

# 3. Selector Design

The Phase 9 selector provides deterministic next-frame selection based
on conversation state.

### Inputs

session_id\
current_engine\
last_partner_frame_id\
recent_frame_ids

### Selection Rules

1.  Prefer frames in the **current engine**
2.  Exclude **recently used frames**
3.  Respect **engine frame order and dependencies**
4.  Allow **engine bridges** when appropriate
5.  Prevent conversation dead ends

### Fallback Ladder

If no suitable frame is found:

1.  Same engine excluding recent frames\
2.  Same engine allowing older frames\
3.  Least-recently-used frame fallback

This guarantees **conversation continuity without randomness**.

------------------------------------------------------------------------

# 4. Deterministic Behaviour

The selector deliberately avoids randomness.

This ensures:

-   reproducible debugging
-   consistent transcripts
-   deterministic trace logs
-   predictable conversation flows

Determinism is a **core architectural property of MandarinOS** and was
preserved throughout Phase 9.

------------------------------------------------------------------------

# 5. Conversation Engine Integration

Phase 9 connects three previously independent systems:

  System                    Phase Introduced
  ------------------------- ------------------
  Frame rendering           Phase 7
  Conversation transcript   Phase 8
  Frame selection           Phase 9

Together they produce the full MandarinOS learning loop:

Frame → Response → Acknowledgement → Reciprocity → Next Frame

This is the **minimal viable MandarinOS conversation engine**.

------------------------------------------------------------------------

# 6. Known Limitations (Accepted)

Phase 9 intentionally **does not yet include**:

-   capability tracking
-   learner memory
-   adaptive difficulty
-   persona modelling
-   scoring systems
-   SRS integration
-   energy / fatigue models
-   automatic turn advancement

These features belong to **future phases**.

Phase 9 focuses solely on **stable deterministic conversation flow**.

------------------------------------------------------------------------

# 7. Quality Observations

Early testing indicates one remaining weakness:

**Response option quality varies across frames.**

Some frames allow minimal or fragmentary responses that produce slightly
unnatural transcripts.

Example pattern:

User: 中国\
Partner: 哦，你来自中国。

This does not break the system but may reduce conversational realism.

This issue is considered **conversation design polish**, not an
architectural defect.

------------------------------------------------------------------------

# 8. Phase 9 Acceptance Criteria

Phase 9 is considered successful when:

• the system automatically selects the next question\
• conversations progress without manual frame selection\
• engine transitions occur correctly\
• no conversational dead ends occur\
• runtime architecture remains unchanged

Based on the strategist review and the Phase 9 briefing, **all criteria
have been met**.

------------------------------------------------------------------------

# 9. Phase 9 Strategic Outcome

With Phase 9 complete, MandarinOS now possesses:

• a deterministic conversation selector\
• multi-engine conversation flow\
• transcripted dialogue structure\
• selectable response options\
• hint cascade support\
• clickable word exploration via cards

This is the **first operational MandarinOS conversational learning
system**.

The system is now ready for **alpha testing with real conversations**.

------------------------------------------------------------------------

# 10. Next Step --- Personal Alpha Testing

The recommended next step is **controlled personal alpha testing** by
the project owner.

Objectives:

-   evaluate naturalness of conversation flow\
-   identify weak response options\
-   detect awkward transcript patterns\
-   refine question ordering\
-   observe conversation fatigue or repetition

Alpha testing should precede any major architectural additions.

------------------------------------------------------------------------

# 11. Strategist Sign-Off

After reviewing the Phase 9 implementation summary and architecture
constraints:

**Phase 9 --- Conversation Engine Integration\
is formally approved and closed.**

The system has reached a stable milestone suitable for real
conversational testing.

------------------------------------------------------------------------

Signed:

**ChatGPT --- Senior Strategist / Architecture Reviewer**\
MandarinOS Project
