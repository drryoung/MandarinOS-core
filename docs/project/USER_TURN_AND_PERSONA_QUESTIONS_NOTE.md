# User turn (你呢？) and persona treasure/loop/bridge questions

**Purpose:** Note for implementation — either in current phase (Phase 9 polish / alpha prep) or in Phase 10 when personas are implemented.

---

## 1. Interrupt constant questioning — let the user turn and ask 你呢？

**Need:** The app currently drives the conversation with a steady stream of partner questions. There should be a way for the **user** to take the turn and ask the partner something (e.g. 你呢？ “And you?”), so the flow is not one-sided.

**Possible implementations:**

- **Now (Phase 9 polish / pre–Phase 10):**
  - Add a **“你呢？” / “My turn”** control (e.g. button or menu) that inserts a **reciprocity turn**: the learner asks 你呢？ and the next system move is the **persona answering** (e.g. 我叫…) rather than the app asking another question.
  - Requires: (a) UI affordance to trigger “user asks 你呢？”; (b) a single “persona answer” frame or stub (e.g. 我叫李明。) so the app can respond in character; (c) next-question logic that, after such a turn, chooses a sensible follow-up (e.g. partner asks the next question) instead of immediately asking again.
- **Phase 10:** If the persona network and persona memory are implemented first, the same “user asks 你呢？” turn can be wired to **persona-specific** answers and follow-ups.

**Recommendation:** Implement a minimal “你呢？” / “My turn” flow **now** (button + one persona-answer response + selector awareness) so the user can break the question stream; refine with full persona answers in Phase 10.

---

## 2. Use treasure, loop, and bridge questions of the persona

**Need:** Once we have **personas**, questions should use that persona’s **treasure**, **loop**, and **bridge** questions (per engine specs and persona data), not only a global frame list.

**Scope:**

- **Treasure questions** — deeper follow-ups (e.g. 你的名字是什么意思？, 你常做吗？) that fit the persona.
- **Loop questions** — recurring patterns (e.g. 为什么？, 大家一般怎么叫你？) that fit the persona.
- **Bridge questions** — transitions to another topic or to another persona (e.g. 那儿有什么好吃的？, persona-linked bridges in the persona network spec).

**Implementation:**

- Depends on **persona data** (e.g. persona profile, interests, conversation style, bridge tendencies) as in `MandarinOS_next_question_selector_v1.md` and persona network docs.
- **Recommendation:** Do this in **Phase 10** when Memory + Persona foundations and persona network are in place. Then:
  - Attach or filter frame sets (core/treasure/loop/bridge) per persona.
  - Feed persona data into the next-question selector so it prefers persona-appropriate treasure/loop/bridge questions.
  - Optionally tag frames with `question_type` (core/treasure/loop) and/or bridge targets per persona if needed.

---

## 3. Summary

| Item | Do now? | Phase 10? |
|------|--------|-----------|
| Interrupt questioning — user can ask 你呢？ (e.g. “My turn” button + one persona answer + selector) | ✅ Yes (minimal) | Refine with full persona answers |
| Persona-specific treasure / loop / bridge questions | Optional (only if persona stubs exist) | ✅ Yes (with persona data and selector integration) |

*Created 2026-03. Update when Phase 10 scope or persona implementation is agreed.*
