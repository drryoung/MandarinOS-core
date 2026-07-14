<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class E: Dated report or historical evidence**
>
> - **Current use:** Retained as dated evidence of architecture-alignment options and the preferred or “gold” position identified at that time.
> - **May guide current implementation:** No.
> - **Current authority:** Verified current code and the nine-document R2 architecture-governance package.
> - **Principal caution:** The selected “gold” option records a historical recommendation, not the present architecture contract. Current alignment must be assessed against the R2 baseline.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# Architecture alignment: response options and "gold"

**Purpose:** Ensure implementation stays consistent with the conversation design.  
**References:** Design Constitution, [MandarinOS_Conversation_UX_Protocol_v1.md](../specs/MandarinOS_Conversation_UX_Protocol_v1.md), [CHATGPT_STRATEGIST_CONVERSATION_DESIGN_BRIEFING.md](../briefings/CHATGPT_STRATEGIST_CONVERSATION_DESIGN_BRIEFING.md), [CONVERSATION_ARCHITECTURE_INDEX.md](../specs/CONVERSATION_ARCHITECTURE_INDEX.md).

---

## 1. Design principle: no correct answer

MandarinOS is a **conversation tool**, not a quiz or test.

- **Design Constitution:** "No right/wrong framing. No 'correct answer' reveals. No praise tokens (对, 很好, 正确)."
- **Conversation UX Protocol:** "The UI must **never evaluate responses as correct or incorrect**." "MandarinOS should feel like: listen → speak → conversation continues **not** like: question → answer → correct/incorrect."
- **Goal:** Guide the user to **maintain conversations for as long as their vocabulary can sustain it** — not to pick a "right" answer.

So the system must never show or imply that one response is "correct" and others "wrong."

---

## 2. What response options are

Response options are **suggested ways to keep the conversation going** (suggested responses). They are:

- Possible things the user could say that fit the current turn.
- All valid as conversation-sustaining replies; none is "the" correct answer.

The UX Protocol: when the user needs support, the UI shows "1–3 **possible responses**"; each can be explored (play, pinyin, translation, word tap). No evaluation or scoring.

---

## 3. Meaning of "gold" in the codebase

In the **runtime and builder**, one option per frame is labelled **gold** (`is_gold: true`). This is an **internal/implementation** label only.

- **Intent:** Mark one **suggested response** that fits the sentence template or the current move (e.g. one filled sentence like "我是中国人。" for "你是哪里人？"). Used for: validation (at least one such option exists), default hint target, and trace payloads.
- **Must not mean:** "The correct answer." "The right choice."
- **Must not be shown to the user as:** Correct, best, or preferred in a right/wrong sense.

So: **gold = one conversation-sustaining suggested response**. Terminology in code/comments should avoid "correct," "right," or "best answer."

---

## 4. UI rules

- Do **not** show correctness, scores, or "correct answer" reveals.
- Do **not** visually single out one option as "the right one" (e.g. avoid a styling that clearly reads as "correct").
- Options may be styled for clarity (e.g. borders, spacing) as long as no option is presented as correct and others as wrong.
- Conversation continues regardless of which option the user chooses; the system advances the dialogue and keeps the loop going.

---

## 5. For implementers

- **Builder (frame_options, etc.):** When building options, "gold" means one suggested response for that turn (e.g. one filled template); do not document or comment it as "correct answer."
- **UI:** Do not add labels like "Correct" or "Best choice"; do not use gold to imply correctness. If a visual distinction for "gold" exists (e.g. border), it should read as "one possible reply" or be removed so all options look equal.
- **Trace/analytics:** `is_gold` in payloads is for internal/analytics use (e.g. which option type was chosen); it must not drive any user-facing "correct/incorrect" feedback.

---

**Last updated:** 2026-03-12 — Added to keep options/gold implementation aligned with conversation design and Design Constitution.
