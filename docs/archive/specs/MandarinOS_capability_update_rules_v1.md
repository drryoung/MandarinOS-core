<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class C: Historical context**
>
> - **Current use:** Retained as historical capability-update design rationale.
> - **May guide current implementation:** No.
> - **Current authority:** Verified code and `docs/CONVERSATION_ARCHITECTURE.md`.
> - **Principal caution:** Its internal `LOCKED` language does not establish current behavioural authority.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->


# MandarinOS Capability Map Update Rules (v1) — LOCKED

Purpose:
Define how MandarinOS updates the learner capability map after each conversation turn and session.

These rules convert real conversation behaviour into adaptive capability signals so the system can choose better next questions.

--------------------------------------------------
1. Core Principle

Capability must update gradually.

Small signals accumulate over time rather than large jumps from single events.

Many small updates → stable learner profile

--------------------------------------------------
2. Three Update Time Scales

A. Turn-level updates
Triggered after each question / response.

Used for:
- immediate adaptation
- next question selection

B. Session-level updates
Triggered after a 10-minute session.

Used for:
- engine readiness adjustments
- stronger confidence changes

C. Long-term updates
Aggregated across many sessions.

Used for:
- stable learner capability profile
- progress display
- SRS scheduling priorities

--------------------------------------------------
3. Diagnostic Signals

Each conversation turn produces signals.

A. Response Success
Was the answer appropriate?

Levels:
- strong success
- partial success
- failed response

B. Response Latency

Fast response → stronger retrieval
Moderate → workable
Long hesitation → fragile knowledge

C. Hint Depth Used

Hint levels:

0  no hint
1  pinyin
2  translation
3  word gloss
4  etymology
5  radical breakdown

Deeper hints indicate more support required.

D. Repair Usage

Examples:
什么？
再说一次
慢一点
我不懂

Using repair successfully is positive behaviour.

E. Repeat Improvement

If second attempt improves after hint usage,
penalties should be reduced.

--------------------------------------------------
4. Update Targets

Each turn updates multiple capability areas.

Example question:

你去过哪里？

Possible update targets:

- Travel engine capability
- Answer move capability
- Experience narrative move
- Listening ability
- Reading ability
- Anchor phrase mastery

--------------------------------------------------
5. Turn-Level Update Logic

Strong Success
Conditions:
- appropriate answer
- minimal hints
- reasonable response speed

Update:
+0.02 engine capability
+0.01 move capability
+0.01 modality capability

Partial Success
Conditions:
- understandable answer
- hint usage
- hesitation

Update:
+0.005 engine capability
0 move capability
+0.01 support dependence

Failure
Conditions:
- no usable answer
- heavy hint usage

Update:
-0.01 engine capability
-0.005 move capability
+0.02 translation dependence

--------------------------------------------------
6. Hint-Based Interpretation

No hint used
→ strong independent comprehension

Pinyin used
→ reading support needed

Translation used
→ vocabulary gap

Word gloss used
→ lexical gap but sentence structure understood

Etymology or radical exploration
→ visual learning behaviour (not necessarily failure)

--------------------------------------------------
7. Repair Logic

Successful repair:

Example:
再说一次 → learner answers successfully

Update:
+ repair capability
minimal penalty to engine capability

Silent breakdown:

No repair attempt and no answer

Update:
larger capability decrease

Successful repair is better than silent failure.

--------------------------------------------------
8. Engine Capability Updates

Each conversation turn belongs primarily to one engine.

Example:

你有兄弟姐妹吗？ → Family engine

Successful response:
small positive update

Repeated struggle:
small negative update

Engine scores reflect rolling confidence.

--------------------------------------------------
9. Conversation Move Updates

Moves tracked:

- answer
- follow-up question
- give reason
- recommend
- react naturally

Example:

Learner asks:
为什么？

Update:
+ curiosity capability
+ follow-up move capability

--------------------------------------------------
10. Modality Updates

Listening
Speaking
Reading
Character recognition
Pinyin dependence
Translation dependence

Example case:

Learner hears sentence, uses pinyin, answers correctly.

Updates:

Listening +
Speaking +
Reading slight –
Pinyin dependence +

--------------------------------------------------
11. Session-Level Aggregation

After a session:

Example summary:

Identity: strong
Travel: moderate with pinyin
Food: strong
Repair used successfully

Updates:

Identity +
Travel slight +
Food +
Repair capability +

--------------------------------------------------
12. Confidence Smoothing

Capability scores use moving averages.

Recent turns matter more than older turns,
but old knowledge still influences scores.

This prevents unstable behaviour.

--------------------------------------------------
13. Update Boundaries

Capability range:

0.00 → 1.00

Typical turn change limits:

+0.02 maximum increase
-0.02 maximum decrease

Session changes:

±0.03 to ±0.05 maximum

--------------------------------------------------
14. Stretch-Zone Rule

Next questions should target slightly above comfort level.

Example:

Travel = 0.68
Food = 0.74
Work = 0.28

System should:

- expand Travel
- bridge to Food
- delay deep Work topics

--------------------------------------------------
15. Simplified Update Formula

new_score =
old_score
+ success_bonus
- support_penalty
+ repair_bonus
+ improvement_bonus

This keeps the system simple and robust.

--------------------------------------------------
16. Learner-Facing Feedback

Learners should see interpretations, not scores.

Example:

You are becoming more confident in Travel conversations.
You can now handle basic Family questions.
You still rely on pinyin for Work conversations.

--------------------------------------------------
17. Minimum Viable Capability Dimensions

Engine capability
Identity
Place
Family
Travel
Food
Study/Work
Interests

Conversation moves
Answer
Follow-up
Give reason
Recommend
React

Curiosity capability
Repair capability

Modality capability
Listening
Speaking
Reading
Pinyin dependence
Translation dependence

--------------------------------------------------
18. Design Summary

The update rules reward:

successful communication
independent comprehension
strategic repair
curiosity
improvement over time

These rules support MandarinOS as an
Adaptive Conversation Operating System.
