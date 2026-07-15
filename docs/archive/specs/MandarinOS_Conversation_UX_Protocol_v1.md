# MandarinOS Conversation UX Protocol v1.0

## Purpose

Define the user interaction cascade for MandarinOS as a **conversation
trainer**.

This document specifies the behaviour that the UI must implement. It
does **not** modify runtime logic, speech recognition, or SRS
scheduling.

------------------------------------------------------------------------

# Core Principle

MandarinOS is a **conversation system, not a quiz system**.

The UI must never evaluate responses as correct or incorrect.

The system should behave like a conversational partner that:

-   continues dialogue when possible
-   offers helpful suggestions when needed
-   allows exploration without interrupting the conversation

------------------------------------------------------------------------

# Primary Interaction Loop

Each turn follows this loop:

system utterance ↓ user speaks response ↓ speech recognition result ↓
system reaction ↓ next conversation node

The UI must always keep this loop visible and simple.

------------------------------------------------------------------------

# Turn Start Behaviour

When a new turn begins, the UI shows:

-   the system sentence (large, centered)
-   a microphone button for speaking
-   a help button

Example:

你好

Available actions:

-   Speak response
-   Ask for help
-   Tap words for exploration

No translation or pinyin should appear by default.

------------------------------------------------------------------------

# Speech Recognition Outcomes

The speech engine returns an internal response quality classification.

This classification is **not shown to the user**.

Instead the UI reacts conversationally.

------------------------------------------------------------------------

## Case A --- Strong response

If the response matches an acceptable conversational reply:

The system continues the conversation.

Example:

User: 你好\
System: 你好！很高兴见到你。

No evaluation or scoring is shown.

------------------------------------------------------------------------

## Case B --- Acceptable response

If the response is understandable but imperfect:

The system may either:

-   continue conversation normally
-   or model a slightly better phrase

Example:

System: 你好啊！

Again, no judgement or scoring is displayed.

------------------------------------------------------------------------

## Case C --- Weak response

If the response is incomplete or not a good conversational reply:

The UI shows **suggested responses**.

Example:

You could say:

你好\
你好啊\
很高兴见到你

Each suggestion can be explored.

------------------------------------------------------------------------

## Case D --- Speech not understood

If the speech engine cannot recognize the response:

The UI shows:

I didn't catch that.\
Try one of these:

Then show the same suggested responses panel.

------------------------------------------------------------------------

# Suggested Response Panel

When shown, the panel displays **1--3 possible responses**.

Each response supports:

-   play audio
-   reveal pinyin
-   display tone symbols
-   show translation (optional deeper layer)
-   tap words for exploration

Example:

你好\
nǐ hǎo\
ˇ ˇ

Responses can also be spoken by tapping a "repeat" control.

------------------------------------------------------------------------

# Hint Ladder

Hints are available when the user taps the help button.

Hints appear progressively:

1.  Replay system audio
2.  Show suggested responses
3.  Show pinyin for the system sentence
4.  Show translation for the system sentence

This order supports conversation before translation.

------------------------------------------------------------------------

# Word Exploration

Users may tap any word in the sentence.

First tap shows a small inline panel:

你好\
nǐ hǎo\
hello

Second tap opens the full card panel.

The card panel uses the existing OPEN_CARD mechanism.

------------------------------------------------------------------------

# Character Exploration

Inside the word card, users can tap characters.

Example:

你

This reveals:

-   component breakdown
-   radicals
-   etymology (if available)

Example:

亻 + 尔

Further exploration of radicals may be available.

------------------------------------------------------------------------

# Critical Behaviour Rule

Exploration must **never interrupt the conversation state**.

Clicking tokens must not:

-   advance the conversation
-   reset hints
-   close response suggestions
-   hide the sentence

The sentence must always remain visible.

------------------------------------------------------------------------

# Tone Display

Tone information should be shown using symbols only.

Example:

ˇ ˇ

Do not display textual explanations like "third tone".

------------------------------------------------------------------------

# UI Philosophy

MandarinOS should feel like:

listen\
↓\
speak\
↓\
conversation continues

not like:

question\
↓\
answer\
↓\
correct/incorrect

------------------------------------------------------------------------

# Non-Goals

The UI must not:

-   show correctness or scores
-   force multiple-choice responses
-   hide the conversation sentence during exploration
-   require hints to view suggested responses

------------------------------------------------------------------------

# Implementation Scope

This protocol applies only to the **UI layer**.

Runtime engines for speech recognition, SRS scheduling, and conversation
routing remain unchanged.
