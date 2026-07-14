<!-- MANDARINOS-DOCUMENT-STATUS:BEGIN -->
> **MandarinOS document authority notice — Class D: Superseded**
>
> - **Current use:** Retained as version one of the conversation-memory design lineage.
> - **May guide current implementation:** No.
> - **Current authority:** Verified persistence code and `docs/STATE_CONTRACT.md`. `docs/specs/MandarinOS_conversation_memory_model_v2.md` is the later historical design version, not current behavioural authority.
> - **Principal caution:** Version one is superseded by version two within the design lineage, while the R2 State Contract governs current memory behaviour.
> - **Classification source:** `docs/DOCUMENT_AUTHORITY_INDEX.md`
> - **Classification date:** `2026-07-13`
> - **Notice added:** `2026-07-14`
> - **Original content:** Preserved below without reinterpretation.
<!-- MANDARINOS-DOCUMENT-STATUS:END -->

# MandarinOS Conversation Memory Model v1 (Revised)

Purpose: Define how MandarinOS stores and reuses conversational
information while still allowing phrase drilling and repetition.

MandarinOS must support two learning goals:

1.  Conversation continuity
2.  Phrase drilling / survival fluency

Memory should therefore be **stored across time**, but **not always
activated**.

------------------------------------------------------------------------

# 1. Two Memory Layers

## Persona Memory

Information about the persona.

Examples:

-   Zhang Rui
-   from Shanghai
-   studies computer science
-   likes noodles
-   father is Wang Wei

Persona memory is mostly predefined.

------------------------------------------------------------------------

## Learner Memory

Information learned about the user through conversation.

Examples:

-   name = Raymond
-   hometown = Dunedin
-   likes hotpot
-   has children
-   visited China

This memory is built during conversations.

------------------------------------------------------------------------

# 2. Core Learner Memory Anchors

Identity - name - nickname - age_or_life_stage

Place - hometown - current_city - country

Family - siblings - marital_status - children

Study / Work - job_or_study - workplace_or_school

Food - favorite_food - spicy_preference

Travel - travel_place - favorite_place

------------------------------------------------------------------------

# 3. Memory Confidence

Each memory has a confidence state:

-   known
-   probable
-   unknown

Example:

favorite_food = hotpot (known) siblings = maybe one sister (probable)

This avoids incorrect assumptions.

------------------------------------------------------------------------

# 4. Memory Lifecycle

Each memory supports:

-   create
-   confirm
-   update

Example:

Old memory

current_city = Shanghai

New conversation

我现在住在深圳。 (I now live in Shenzhen.)

Update memory

current_city = Shenzhen

------------------------------------------------------------------------

# 5. Memory Activation Modes

Memory should not always influence conversation in the same way.

MandarinOS supports three session modes.

------------------------------------------------------------------------

## Drill Mode

Purpose:

-   phrase repetition
-   beginner survival fluency
-   P1 loop practice

Behavior:

-   learner memory stored globally
-   but ignored during turn selection
-   system re-asks core questions

Examples:

你叫什么名字？ What is your name?

你是哪里人？ Where are you from?

你喜欢吃什么？ What do you like to eat?

------------------------------------------------------------------------

## Mixed Mode

Purpose:

-   semi-natural conversation
-   some repetition
-   some continuity

Behavior:

-   memory may influence conversation
-   but core questions may still reappear

------------------------------------------------------------------------

## Continue Mode

Purpose:

-   natural conversation continuity
-   relationship feeling
-   follow-up discussion

Behavior:

-   stored memory actively reused

Example:

Raymond，你上次说你喜欢火锅。 Raymond, last time you said you like
hotpot.

现在还喜欢吗？ Do you still like it?

------------------------------------------------------------------------

# 6. Key Design Principle

Memory should be:

available, but not always active.

The system decides whether to activate memory based on session goals.

------------------------------------------------------------------------

# 7. How Memory Is Created

A memory is created when the learner clearly reveals information.

Example:

你喜欢吃什么？ What do you like to eat?

我喜欢火锅。 I like hotpot.

Store:

favorite_food = hotpot

------------------------------------------------------------------------

# 8. How Memory Is Reused

Memory can be reused in three ways.

Confirmation

你喜欢火锅，对吗？ You like hotpot, right?

Recall

上次你说你老家在但尼丁。 Last time you said your hometown is Dunedin.

Follow-up

你的孩子多大？ How old are your children?

------------------------------------------------------------------------

# 9. What Should Not Be Remembered

Do not store trivial facts.

Avoid storing:

-   favorite color
-   temporary moods
-   one-off details

Memory should focus on **conversation anchors**.

------------------------------------------------------------------------

# 10. Session Memory vs Long-Term Memory

Session Memory (temporary)

-   current engine
-   last answers
-   repair state
-   who spoke last

Long-Term Memory (persistent)

-   hometown
-   family
-   job or study
-   favorite food
-   travel experience

------------------------------------------------------------------------

# 11. Reciprocity and Memory

The phrase **你呢？ (and you?)** is a key mechanism for collecting
memory.

Example:

我喜欢面。你呢？ I like noodles. How about you?

Learner response:

我喜欢火锅。 I like hotpot.

Now store:

favorite_food = hotpot

------------------------------------------------------------------------

# 12. Minimal Data Structures

Learner Memory

learner_memory = { name: "", hometown:"", current_city:"", family: {
siblings:"", marital_status:"", children:"" }, work_or_study: "",
favorite_food:"", spicy_preference:"", travel_place:"" }

Persona Memory

persona_memory = { name: "Zhang Rui", hometown: "Hangzhou",
current_city: "Shanghai", family: { father: "Wang Wei" }, work_or_study:
"computer science student", favorite_food: "noodles" }

Session Mode

session_mode = drill \| mixed \| continue

------------------------------------------------------------------------

# 13. Summary

MandarinOS should behave like:

"I remember you, but I choose whether to use that memory based on the
learning goal."

This allows the system to support both:

-   survival phrase drilling
-   relationship-style conversation
