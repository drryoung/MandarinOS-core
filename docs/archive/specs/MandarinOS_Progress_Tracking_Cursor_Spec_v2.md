MandarinOS Progress Tracking Specification
Cursor-ready implementation brief for Standard and Premium progress records
# 1. Purpose
Implement a lightweight progress tracking layer for MandarinOS that saves one summary record at the end of each session. The goal is not academic grading. The goal is to show conversational growth over time using metrics the app already produces.
# 2. Product Decision

Recommendation: build the same underlying snapshot format for Standard and Premium. The tier difference should be retention length and presentation depth, not different measurement logic.
# 3. Keep the First Version Simple
- Save summary metrics only. Do not save audio. Do not save full transcripts in this phase.
- Use existing session metrics from /api/end_session wherever possible.
- Show one graph and one table. Avoid a complex dashboard.
- Use encouraging labels such as Conversation Stability and Initiative, not failure-rate language.
# 4. Core Metrics to Track

# 5. Session Snapshot Schema
Create a compact JSON-compatible record at the end of every session:
{
  "session_id": "2026-05-19T18-42-10-local",
  "created_at": "2026-05-19T18:42:10+12:00",
  "tier": "standard",
  "persona_id": "founder_raymond_v1",
  "mode": "normal",
  "duration_seconds": 870,
  "total_turns": 42,
  "questions_asked": 5,
  "recovery_uses": 4,
  "successful_recoveries": 3,
  "unclear_turns": 2,
  "depth_responses": 6,
  "engines_used": 4,
  "suggestion_clicks": 3,
  "card_opens": 2,
  "conversation_stability_score": 95,
  "recovery_success_rate": 0.75
}
# 6. Storage Strategy - Minimal Code First

Important: localStorage is acceptable for alpha testing, but it is not a true permanent user record. It can be cleared by browser settings and does not follow the user across devices.
# 7. Standard vs Premium Behaviour

# 8. Visual Mock-up Requirement
Add one graph to the progress area. For the first version, show Conversation Stability over the last 10 sessions. Premium can later extend the same graph to all saved sessions.

Figure 1. Mock graph for Premium progress view. Standard can use the same graph limited to the last 10 sessions.
# 9. UI Placement
- Add a new Progress tab or section separate from the live conversation panel.
- Do not put long-term progress inside the active conversation window.
- At end session, keep the existing scorecard; below it add a small “Saved to Progress” message for Standard/Premium users.
- Progress section should show: one headline, one graph, one compact table.
# 10. Suggested User-Facing Labels

# 11. Cursor Implementation Instructions
Cursor should implement this as a minimal additive change. Do not rewrite conversation selection, scoring, recovery, personas, or the Phase 6 runtime boundary.
1. Find where /api/end_session returns the current scorecard metrics in scripts/ui_server.py.
1. Ensure the response includes the raw metrics needed for the snapshot. Do not change existing metric meanings.
1. In ui/app.js, after renderScorecard(), create a progress snapshot object from the returned metrics.
1. Save the snapshot to localStorage under manos_progress_history.
1. Apply retention logic: Standard keeps last 10 snapshots; Premium keeps all snapshots. For now, tier can be simulated by a constant or localStorage value.
1. Create a Progress rendering function that reads manos_progress_history and renders: graph container, summary table, and latest trend headline.
1. Use a simple chart implementation. If avoiding dependencies, use SVG directly or a tiny canvas line chart. Do not add a large charting library unless already present.
1. Add tests that confirm snapshot creation, Standard retention limit, Premium no-limit retention, and score calculation.
# 12. Acceptance Tests

# 13. Suggested Empty-State Copy
No progress record yet. Finish a conversation session and MandarinOS will begin building your speaking progress history.
# 14. Strategic Note
This feature is valuable because it turns MandarinOS from a session-based app into a visible journey. Standard users can see recent improvement. Premium users can build a permanent evidence trail of their conversational development, which supports both retention and the 30-day progress guarantee.

# ADDENDUM — Measurement Philosophy Revision
Purpose of Revision:
This addendum updates the original specification to ensure that MandarinOS measures conversational survivability and participation rather than linguistic perfection. The scoring philosophy must align with the core MandarinOS identity: helping learners stay alive inside real conversations.
## 1. Core Measurement Philosophy
1. Conversation survival matters more than perfection
A long imperfect conversation is usually stronger than a short technically perfect interaction.
1. Support usage is not failure
Hints, repairs, clarification, and scaffolding are legitimate parts of conversational growth. The app should reward successful continuation after support.
1. Ratios matter more than raw counts
Three unclear turns inside a 40-turn conversation may represent a strong session. Metrics must normalize against session length.
1. Initiative is a major indicator of growth
Question-back behaviour, topic continuation, and longer answers are important signs that the learner is becoming an active conversational participant.
1. Emotional tone matters
Progress tracking should feel encouraging and reflective rather than punitive or school-like.
## 2. Revised Metric Interpretation
## 3. Signature Metric Recommendation
Primary MandarinOS Metric:
Conversation Stability should become the signature MandarinOS progress metric. It captures the central philosophy of the product: not perfection, but the ability to remain engaged inside a real conversation.
## 4. Suggested Capability Bands
- Getting started
- Conversation stayed on track
- Recovering well
- Asking more questions back
- Sustaining longer exchanges
- Active conversational participant
## 5. Human Reflection Signal
Recommended optional end-of-session question:
"Did this conversation feel easier, harder, or about the same?"

This creates a human calibration layer. If users consistently feel stronger progress than the metrics indicate, the metrics should be revised.
## 6. Revised Graph Recommendation
The primary graph should NOT represent accuracy.
Instead, the first graph should visualize Conversation Stability over time. This better reflects the MandarinOS philosophy of conversational survivability.

Figure 2. Example progression graph emphasizing conversational stability rather than accuracy.
## 7. Important Implementation Guardrail
MandarinOS is not a testing system.
The progress architecture must reinforce confidence, resilience, initiative, and sustained participation rather than academic correctness scoring.

![Conversation Stability Graph](conversation_stability_graph.png)
