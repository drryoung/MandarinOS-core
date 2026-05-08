# MandarinOS — Response Option Style Guide

Defines the rules for every learner-facing Chinese response option shown in the UI.

**Apply these rules to every option in:**
- `content/response_patterns.json`
- Any future learner sentence file

**Reference audit:** `docs/MANDARINOS_REGRESSION_LOCK.md` tracks regression-locked behaviors.  
**Known violations to fix:** See the 2026-05 Response Options Audit results.

---

## 1. Core Principle — The One Breath Rule

> A learner must be able to say the response in one breath, without planning, under conversational pressure.

If it requires a pause to construct, it fails.  
If it requires reading before speaking, it fails.  
If it sounds like a written sentence, it fails.

This is the master rule. All other rules exist to enforce it.

---

## 2. Length Rule

| Zone | Characters | Status |
|---|---|---|
| Ideal | 2–6 chars | Always valid |
| Acceptable | 7–10 chars | Valid if it passes the One Breath Rule |
| Warning | 11–12 chars | Needs justification — split if possible |
| Never | 13+ chars | Invalid for a learner response option |

Count Chinese characters only. Punctuation is ignored.

**Multi-clause sentences are never allowed**, regardless of total length.  
A comma separating two full clauses creates a multi-clause sentence.

```
✅  很好吃！          (4 chars — ideal)
✅  我想去日本！       (7 chars — good)
✅  喜欢，但有点辣。   (8 chars — acceptable)
⚠️  我想去日本，喜欢那里的文化。  (13 chars + 2 clauses — invalid)
❌  一起旅行，这对我们来说很重要。  (14 chars + formal structure — invalid)
```

---

## 3. Spoken Chinese Only

Response options model what the learner says out loud. They must use **spoken, everyday register** — not written, formal, or literary Chinese.

### Required substitutions

| Avoid (written) | Use instead (spoken) | Meaning |
|---|---|---|
| 妻子 | 老婆 | wife |
| 丈夫 | 老公 | husband |
| 父母 / 父母亲 | 爸爸妈妈 | parents |
| 父亲 | 爸爸 | father |
| 母亲 | 妈妈 | mother |
| 非常 | 很 (in most cases) | very |
| 景色 | 风景 | scenery |
| 游览 | 到处玩 / 去玩 | sightsee |
| 通勤 | 去上班 | commute |
| 换一个方向 | 换个工作 | change direction/career |

### Register test

Read the option out loud in a casual conversation with a friend. If it sounds like you are reading from a textbook, rewrite it.

---

## 4. No Abstract Vocabulary

Learner response options should describe **felt, concrete experience** — not abstract concepts.

### Words to avoid in response options

| Word | Why | Replace with |
|---|---|---|
| 成就感 | Abstract compound noun; mid-advanced | 很开心 / 很有意思 |
| 代表 | Formal/literary | 是 / 有 |
| 方向 (as metaphor) | Abstract; written | 工作 / 打算 |
| 文化 (abstract use) | Academic register | 那里很有意思 / 很好玩 |
| 了解文化 | Academic phrase | just 聊天 / 去看看 |
| 景色 | Literary | 风景 |
| 通勤 | Technical | 去上班 |
| 游览 | Formal/tour-guide | 到处走走 / 去玩 |
| 偶然的机会 | Formal compound | 偶然的 / 刚好 |
| 正面的意思 | Formal/abstract | 好的意思 |

### Preferred vocabulary for feelings and responses

```
开心     喜欢     好吃     好玩
很累     很忙     还好     不错
有意思   想一下   不知道   说不清楚
```

---

## 5. No Multi-Clause Structures

A response option must be **one thought, one unit**. It should not contain subordinate or coordinate clauses that require mental assembly before speaking.

### Banned structures

| Pattern | Example | Problem |
|---|---|---|
| 因为…，所以… | 因为有文化，所以喜欢 | Logical chain; too constructed |
| 对…来说… | 这对我们来说很重要 | Written-register structure |
| 越…越… | 越远越好 | Requires planning to execute |
| Relative clause inside response | 没去过的地方的文化 | Nested clause |
| Comma-joined full clauses | 风景很美，特别适合走路探索 | Two sentences |

### Allowed connectives

These are fine **only when short and natural**:

```
但      不过     有时候     一般
所以（standalone clause use）
```

---

## 6. Modular Response Design

Long responses that cover two ideas must be **split into two separate options** — not combined with a comma.

The learner can choose one and expand naturally. Two shorter options give more flexibility than one long one.

### Rule

> If a response contains a comma-separated second clause that adds extra content, split it into two options.

```
❌ Single long option:
我想去日本，喜欢那里的文化。

✅ Two modular options:
Option A:  我想去日本！
Option B:  喜欢那里的文化。
```

```
❌ Single long option:
我喜欢和当地人聊天，了解文化。

✅ Two modular options:
Option A:  我喜欢和当地人聊天！
Option B:  可以学到很多。
```

Modular options:
- are easier to say quickly
- can be combined by the learner freely in later stages
- prevent the learner from reciting memorized scripts rather than constructing speech

---

## 7. Conversation Utility

Every response option must **keep the conversation moving**.

Ask: does this response give the partner something to respond to?

### Good conversation utility

```
还不错。            → easy to follow up on
我想去日本！        → natural next question: 为什么？
我以前是老师。      → natural next question: 多久了？
很忙，最近事情多。  → natural follow-up
```

### Poor conversation utility

```
说不太清楚，还在想。   ← closes conversation
有很多，不确定。        ← vague non-answer
这个不好说。            ← deflects (valid for REPAIR, not for content responses)
```

Deflection options belong in `content/recovery_phrases.json`, not in content responses.

---

## 8. Natural Spoken Patterns

Some patterns feel natural in speech but are often missing from learner materials because they are not found in formal texts.

### Prefer these natural spoken patterns

| Natural | Avoid | EN |
|---|---|---|
| 好啊 | 当然可以 | Sure / Yeah |
| 可以 | 没有问题 | OK / Fine |
| 我也是 | 我也一样 | Me too |
| 不太会 | 我不擅长 | I'm not great at it |
| 我想一下 | 我需要考虑一下 | Let me think |
| 说不清楚 | 很难表达 | Hard to explain |
| 没想到 | 出乎意料 | Didn't expect |
| 就是这样 | 情况就是如此 | That's just how it is |
| 你也试试！ | 我很推荐 | You should try it! |
| 还好 | 还可以接受 | It's OK / not bad |

---

## 9. Family Vocabulary Standard

MandarinOS teaches spoken Mandarin. The family vocabulary below is **non-negotiable** — no exceptions in learner response options.

| Always use | Never use | Meaning |
|---|---|---|
| 老婆 | 妻子 | wife |
| 老公 | 丈夫 | husband |
| 爸爸妈妈 | 父母 / 父母亲 | parents |
| 爸爸 | 父亲 | father |
| 妈妈 | 母亲 | mother |
| 家人 | 家庭成员 | family members |
| 孩子 | 子女 | children |

This applies to **both** response option files and the EN→ZH translation system.  
The `naturalizeZhTranslation()` function in `app.js` enforces this for dynamic translations.  
Static content files must be edited directly to comply.

---

## 10. The Test Rule

Before finalising any response option, apply this checklist:

```
□ Can I say this instantly, without planning?
□ Would a real person say this casually to a friend?
□ Is it under 10 characters?
□ Does it use only one clause?
□ Does it use spoken vocabulary?
□ Does it avoid abstract nouns?
□ Does it give the partner something to respond to?
□ Does it pass the One Breath Rule?
```

If any answer is no → rewrite.  
If two or more answers are no → discard and start again.

---

## Good vs Bad Examples

### Name / identity

| ❌ Bad | ✅ Good | Why |
|---|---|---|
| 有正面的意思，代表美好的东西。 | 有好的意思。 | Removes 正面/代表/美好 (all formal); cuts from 14 to 5 chars |
| 我有个中文名，叫___。 | 我有中文名！叫___。 | Comma clause → two short bursts (still 1 option — borderline OK here) |

### Family

| ❌ Bad | ✅ Good | Why |
|---|---|---|
| 当然是父母。 | 当然是爸爸妈妈。 | 父母 → spoken equivalent |
| 我跟妻子和父母住在一起。 | 我跟老婆和爸爸妈妈住在一起。 | Formal vocab → spoken vocab |
| 是我老婆，她支持我做的一切。 | 是我老婆。她很支持我。 | Split: one clause per option; also removes 一切 |

### Travel

| ❌ Bad | ✅ Good | Why |
|---|---|---|
| 我想去欧洲，历史很丰富。 | 我想去欧洲！ | Second clause removed; 丰富 is advanced |
| 我想去日本，喜欢那里的文化。 | 我想去日本！ / 喜欢那里。 | Modularised; each is one breath |
| 我想去没去过的地方，越远越好。 | 我想去没去过的地方！ | Removed 越…越 structure |
| 风景很美，特别适合走路探索。 | 风景很美！可以走路。 | 探索/适合 → simpler; clauses split |

### Work

| ❌ Bad | ✅ Good | Why |
|---|---|---|
| 因为有成就感。 | 因为做完了很开心。 | 成就感 → concrete felt word 开心 |
| 完成工作很有成就感。 | 完成工作很开心！ | Same substitution |
| 在公司办公室，每天通勤。 | 在公司，每天去上班。 | 通勤 → spoken 去上班 |
| 不，我想换一个方向。 | 不，我想换个工作。 | 换一个方向 → concrete 换个工作 |

### Recommendations

| ❌ Bad | ✅ Good | Why |
|---|---|---|
| 很好吃！我很推荐。 | 很好吃！你也试试！ | 推荐 sounds like a review; 试试 is natural conversation |

### Hobbies

| ❌ Bad | ✅ Good | Why |
|---|---|---|
| 是偶然的机会，没想到这么喜欢。 | 是偶然的！没想到这么喜欢。 | 偶然的机会 → just 偶然的; still natural |
| 一起旅行，这对我们来说很重要。 | 一起旅行！很重要。 | 对…来说 removed; cut from 14 to 7 chars |
| 我喜欢和当地人聊天，了解文化。 | 我喜欢和当地人聊天！ | 了解文化 removed (academic); stands alone well |
| 非常重要，少了它不行。 | 很重要，没有不行。 | 非常 → 很 |

---

## Changelog

| Date | Change |
|---|---|
| 2026-05 | Initial guide created following Response Options Audit |
