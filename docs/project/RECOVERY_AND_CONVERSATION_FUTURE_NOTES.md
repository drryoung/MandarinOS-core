<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class F: Proposal, plan, or unimplemented specification**
>
> - **Current use:** Retained as forward-looking notes about recovery and future conversation behaviour.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current code, `docs/CONVERSATION_ARCHITECTURE.md`, `docs/ASR_PIPELINE.md`, and the deferred-decision register in `docs/ARCHITECTURAL_DECISIONS.md`.
> - **Principal caution:** These are future notes rather than approved requirements. Proposed recovery or conversation changes require a separate architectural decision or reviewed implementation directive.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Recovery & Conversation — Future Notes

Notes for later implementation. Current behaviour is acceptable for now.

---

## 1. Recovery phrases by user level

**To introduce later:** Recovery phrases (Need help? panel) should be displayed and/or ordered according to the user’s level.

- Content already has `level` (e.g. P1, P2) per phrase.
- Currently the UI shows a fixed set (P1 first, then P2, up to `RECOVERY_PHRASES_MAX`).
- **Future:** Filter or sort recovery options by the learner’s current level (e.g. from profile, placement, or progress) so that:
  - Beginners see only P1 or the most essential phrases.
  - More advanced learners see P2 and/or fuller lists.
- Consider: level in `content/recovery_phrases.json`, runtime shape, and UI in `getRecoveryPanelOption()` / `renderOptions()`.

---

## 2. Smarter conversation flow

**To sort out later:** Conversations can feel “stupid” when recovery and repetition don’t match what the user meant.

**Example of current limitations:**

- Partner: 你是哪里人？  
  You: 我不懂  
  Partner: 你现在住哪里？ *(jumps to a different question)*  
  You: 什么？  
  Partner: 你现在住哪里？ *(repeats same question)*  
  You: 再说一次  
  Partner: 你现在住哪里？ *(same again)*  
  You: 慢一点  
  Partner: 好的，慢一点：你现在住哪里？  
  You: 住 (repeated) *(user trying to answer but only one word; no handling)*  

**Directions for later:**

- **Recovery semantics:** After “我不懂” or “听不懂”, consider repeating the *same* question (or a simpler rephrase) instead of always advancing to next turn, so the flow matches “I didn’t understand *that* question.”
- **Repetition coherence:** When the user says 什么？ / 再说一次 / 慢一点, the app already repeats or slows the *current* question; ensure the “current” question doesn’t change unexpectedly so the dialogue stays coherent.
- **Partial answers:** Handle single-word or fragment answers (e.g. “住”) more intelligently—e.g. prompt to complete, suggest a full sentence, or treat as slot-fill rather than treating as a full turn.
- **Next-turn choice:** When we do advance (e.g. after “我们聊点简单的吧”), the next question could be chosen to be easier or from a different topic, not just “next in ladder.”

These are product/UX and possibly backend (next-question selector, conversation state) changes to be scoped and implemented later.
