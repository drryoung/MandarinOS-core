# UI vs Full Conversation Loop — Assessment

**Date:** 2026-03-08  
**Question:** Does the current UI support the full conversation loop **Question → Answer → Statement → Reciprocity → Next question**?  
**References:** AI_CONTEXT.md, docs/specs/CONVERSATION_ARCHITECTURE_INDEX.md, docs/phases/PHASE6_RUNTIME_ARCHITECTURE_LOCK.md, ui/app.js, ui/index.html  
**No code was modified.**

---

## 1. Target loop (from conversation design)

From **MandarinOS_conversation_system_blueprint_v1** and **mandarinos_conversation_architecture_v1**:

1. **Question** — Partner asks (e.g. 你叫什么名字？). Display + audio.
2. **Answer** — User answers (e.g. 我叫张瑞。).
3. **Short statement** — Partner makes a short statement (e.g. 我是上海人。).
4. **Reciprocity** — Partner says 你呢？ (And you?).
5. **Next question** — System presents the next question (or user responds to 你呢？).

This structure keeps the exchange from feeling like an interrogation and supports natural flow.

---

## 2. What the current UI does

### 2.1 Flow today

- User picks a **frame** from a dropdown (Frame:) and clicks **Run Turn**.
- UI shows:
  - **Frame sentence** (partner’s question) in `#frameSentence` — clickable word tokens, micro-gloss, “Open card”.
  - **Action Ladder:** “Try responding →”, “Uncertain / Help”.
  - **Hint** rows (pinyin, meaning, etymology) and **Hint →** when affordance is visible.
  - **Response options** (option buttons with hanzi/pinyin/meaning) in `#optionsContainer` (created by `renderOptions()`).
- User clicks **Try responding** → `ui_mode` = RESPOND (options enabled).
- User clicks one **option** → `OPTION_SELECTED` traced, optional **OPEN_CARD** / card panel, option marked “selected”.
- To see another question, user **manually** selects another frame and clicks **Run Turn** again.

There is **no automatic advance** to a partner statement, reciprocity, or next question after an option is selected.

### 2.2 Per-step support

| Loop step | Supported? | How in current UI |
|-----------|------------|--------------------|
| **Question** | ✅ Partially | Frame sentence is shown in `#frameSentence` (partner question). **No** dedicated “Play question” / TTS for the frame sentence in the main view (audio for question is missing). |
| **Answer** | ✅ Yes | User chooses one of the response options; selection is traced and optionally opens card. No conversation transcript showing “You: 我叫张瑞”. |
| **Statement** | ❌ No | No UI that shows a **partner short statement** (e.g. 我是上海人) after the user’s answer. Only one partner utterance per “Run Turn” (the frame sentence). |
| **Reciprocity** | ❌ No | No 你呢？ step: no area, no prompt, no turn type for “reciprocity”. |
| **Next question** | ⚠️ Manual only | “Next question” only by **manually** changing the frame dropdown and clicking **Run Turn**. No Next Question Selector, no automatic progression, no engine-driven next frame. |

---

## 3. Conclusion: does the UI support the full loop?

**No.** The UI supports **Question** (display only; no question audio) and **Answer** (option selection). It does **not** support:

- **Statement** (partner short statement after answer),
- **Reciprocity** (你呢？ as a distinct step),
- **Next question** as an automatic, system-chosen step (only manual frame change).

So the **full** loop (Question → Answer → Statement → Reciprocity → Next question) is **not** implemented in the current UI.

---

## 4. Missing UI components (list)

To support the full conversation loop, the following are missing or only partly present:

1. **Play / speak for the question**
   - A control (e.g. button or icon) next to the frame sentence that speaks the current question (frame text) via TTS, so the “Question” step matches the design (display + audio).

2. **Partner short statement**
   - A dedicated **area or phase** that shows the **partner’s short statement** after the user has answered (e.g. 我是上海人).
   - Requires: (a) data source for the statement (e.g. per-frame or per-turn “statement” from runtime/spec), (b) a place in the layout to show it (e.g. under the frame sentence or in a conversation transcript), (c) optional TTS for the statement.

3. **Reciprocity step (你呢？)**
   - A **reciprocity phase** in the turn flow: show (and optionally speak) 你呢？ (or equivalent) as a distinct partner turn.
   - Requires: (a) a turn phase or “utterance type” for reciprocity in the flow, (b) UI area to display it, (c) optional TTS, (d) logic so the next step can be “user answers 你呢？” or “next question” depending on design.

4. **Conversation transcript / dialogue history**
   - A **transcript** (or scrollable history) that shows the sequence: Partner: Question → You: Answer → Partner: Statement → Partner: 你呢？ → … so the user sees the full loop. Today there is only the current frame sentence and options; no multi-turn transcript.

5. **Automatic next question**
   - **Next question** chosen by the system (Next Question Selector or equivalent), not only by the user via the frame dropdown.
   - Requires: (a) backend/API that returns “next frame” (or next turn content) given conversation state, (b) UI that requests and then displays that next question (and optionally advances to Statement → Reciprocity → Next question) instead of requiring a manual frame change and Run Turn.

6. **Turn progression state machine in the UI**
   - UI (and optionally runtime) model of turn phases: e.g. **Question shown → User answered → Statement shown → Reciprocity shown → Next question**. Today the UI has no notion of “statement phase” or “reciprocity phase”; it only has “frame + options” and “option selected”.

7. **Optional: “You said” display**
   - Showing the **user’s answer** in the conversation (e.g. “You: 我叫张瑞”) so the loop is visible. Today the chosen option is only marked “selected”; it is not echoed as a dialogue line in a transcript.

---

## 5. What already exists (no change needed for this assessment)

- Frame sentence display and tokenization (Phase 7.3/7.4).
- Response options (tap to select), validation, trace (OPTION_SELECTED, OPEN_CARD, etc.).
- Hint cascade (pinyin, meaning, etymology), hint button, ui_mode (READ / RESPOND / REPAIR).
- Card panel, micro-gloss, word-level play (card/word TTS).
- Run Turn: load frame + options from runtime/API; no backend change assumed here (PHASE6 lock).
- Trace area and trace events.

These support **single-turn** “question + answer (option select)” only, not the full **Question → Answer → Statement → Reciprocity → Next question** loop.

---

**Summary:** The current UI does **not** support the full conversation loop. Missing pieces: **statement** display/phase, **reciprocity** (你呢？) phase, **conversation transcript**, **automatic next question**, **play for question**, and a clear **turn progression** (state) for the full loop.
