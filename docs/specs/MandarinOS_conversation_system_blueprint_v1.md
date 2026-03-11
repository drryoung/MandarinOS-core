# MandarinOS Conversation System Blueprint v1

## Purpose

This document captures the core conversational architecture of
MandarinOS so that future development and implementation remain
consistent.

The goal of MandarinOS is not vocabulary memorization but **usable
spoken conversation ability**.

MandarinOS should feel like a **conversation simulator** rather than a
textbook exercise.

------------------------------------------------------------------------

# 1. Core Design Philosophy

MandarinOS conversations should be:

-   interesting
-   memorable
-   human-like
-   curiosity-driven

Not:

-   scripted
-   interrogative
-   textbook-like

Conversation topics should focus on **things people remember about each
other**, inspired by principles similar to Dale Carnegie conversation
techniques.

Examples: - hometown - family - work/study - travel - food - personal
interests

------------------------------------------------------------------------

# 2. Conversation Architecture

MandarinOS conversation consists of the following layers:

Conversation Engines\
↓\
Curiosity Triggers\
↓\
Conversation Fillers\
↓\
Repair System\
↓\
Memory Anchors\
↓\
Persona Network

Each layer supports natural conversational flow.

------------------------------------------------------------------------

# 3. Conversation Engines

Conversation engines are topic modules that drive discussion.

Each engine follows the same structural template.

Template fields:

-   Engine Name
-   Purpose
-   Role (Entry / Hub / Secondary)
-   Likely next engines
-   Core Questions \[?\]
-   Treasure Questions \[T\]
-   Loop Questions \[L\]
-   Trigger Patterns
-   Bridges \[B→X\]
-   Typical Paths
-   Example Mini Conversation
-   Notes

Current engines:

-   Identity
-   Place
-   Food

Future engines:

-   Family
-   Study / Work
-   Travel
-   Hobbies

------------------------------------------------------------------------

# 4. P1 Conversation Loop Structure

Every engine should support a simple loop suitable for beginners.

Conversation rhythm:

1.  Question\
2.  Answer\
3.  Short statement\
4.  Reciprocity (**你呢？ -- and you?**)

Example:

你叫什么名字？\
What is your name?

我叫张瑞。\
My name is Zhang Rui.

我是上海人。\
I'm from Shanghai.

你呢？\
And you?

This structure prevents conversations from becoming interrogations.

------------------------------------------------------------------------

# 5. Curiosity Triggers

Curiosity triggers are small statements that naturally encourage
follow-up questions.

Example:

我去过日本。\
I have been to Japan.

Possible learner questions:

什么时候？\
When?

好玩吗？\
Was it fun?

Every persona memory anchor should have at least one curiosity trigger.

Examples:

  Memory Anchor   Trigger        English
  --------------- -------------- -------------------------
  hometown        我老家在成都   My hometown is Chengdu
  sibling         我有一个妹妹   I have a younger sister
  job             我是老师       I am a teacher
  food            我喜欢火锅     I like hotpot
  travel          我去过日本     I have been to Japan

------------------------------------------------------------------------

# 6. Conversation Fillers

Fillers keep conversation flowing naturally.

Examples:

嗯 (èn) -- mm / yeah\
是吗？ (shì ma) -- really?\
真的？ (zhēn de) -- really?\
哦 (ó) -- oh / I see\
这样啊 (zhèyàng a) -- I see\
然后呢？ (ránhòu ne) -- and then?

Without fillers conversations feel robotic.

------------------------------------------------------------------------

# 7. Repair System

Repair phrases allow the learner to recover when comprehension fails.

Examples:

什么？ -- what?\
再说一次 -- say again please\
慢一点 -- slower please\
我不懂 -- I don't understand\
听不懂 -- I can't understand

Repair flow should allow the system to: - repeat - simplify - slow
speech - change topic

------------------------------------------------------------------------

# 8. Conversation Memory Anchors

MandarinOS should store a small set of memorable identity facts.

Example anchors:

-   name
-   hometown
-   family
-   work/study
-   favorite food
-   travel experience

These anchors allow later conversations to reference earlier
information.

Example:

你不是说你老家在苏州吗？\
Didn't you say your hometown was Suzhou?

------------------------------------------------------------------------

# 9. Persona Network

Instead of isolated characters, MandarinOS uses a small connected social
network.

Example:

Li Jianguo (retired teacher)\
↓\
Wang Wei (engineer)\
↓\
Zhang Rui (student)\
↓\
Liu Fang (accountant)\
↓\
Chen Hao (designer)

Relationships enable conversation bridges.

Example:

我有一个女儿。\
I have a daughter.

她叫什么名字？\
What is her name?

张瑞。\
Zhang Rui.

Later the learner can talk with Zhang Rui.

------------------------------------------------------------------------

# 10. Design Principles

1.  Personas should reveal information gradually.
2.  Conversations should balance questions and statements.
3.  Topics should reflect real human curiosity.
4.  Persona networks should remain small (5--7 characters).
5.  Beginner vocabulary must remain simple.

------------------------------------------------------------------------

# 11. Implementation Philosophy

MandarinOS is designed as:

conversation simulator\
not vocabulary trainer

The system should prioritize:

interesting → memorable → usable

rather than

complete → exhaustive → academic
