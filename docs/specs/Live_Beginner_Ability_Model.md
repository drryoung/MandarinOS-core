MandarinOS Spec: Live Beginner Ability Model + Controlled Persona Output

Purpose:
Ensure MandarinOS remains usable for P1 / HSK1–2 beginners by continuously estimating learner ability and restricting persona output to language the learner can understand, with only slight stretch.

Core Principle:
The app should not merely select conversation frames by topic. It should adapt every persona turn to the learner’s demonstrated ability.

Target behavior:
For beginner users, each app-side/persona turn should contain:
- mostly known vocabulary
- short sentence length
- familiar grammar
- at most 1–2 unknown or stretch words per turn
- immediate support for any stretch word through clickable tokens / hints

Do not rewrite runtime selection.
Do not replace existing frame selector.
Do not change Phase 6 deterministic runtime behavior.
Add this as an adaptive output-control layer.

Definitions:

1. Known vocabulary
Words the learner has:
- seen before in MandarinOS, or
- clicked and explored, or
- successfully spoken, or
- repeatedly accepted in prior turns, or
- belonging to the active declared level, e.g. HSK1 / HSK2.

2. Stretch vocabulary
Words slightly above current level, allowed in small quantity:
- max 1 unknown word for fragile beginner
- max 2 unknown words for stable beginner
- max 3 only for confident P2 users

3. Unsafe vocabulary
Words too far above the learner’s current profile:
- abstract nouns
- long compounds
- idioms
- advanced connectors
- multi-clause expressions
- low-frequency location/work/family terms

Live Learner Model:

Maintain a lightweight learner_state object.

Suggested fields:

learner_state = {
  declared_level: "P1" | "P2" | "unknown",
  estimated_level: "P1_fragile" | "P1_stable" | "P2_early" | "P2_stable",
  known_words: [],
  seen_words: [],
  clicked_words: [],
  successfully_spoken_words: [],
  recent_failed_words: [],
  recent_repair_count: 0,
  recent_hint_count: 0,
  recent_asr_rejection_count: 0,
  recent_success_count: 0,
  comprehension_confidence: 0.0-1.0,
  production_confidence: 0.0-1.0,
  max_unknown_words_per_turn: 1 | 2 | 3,
  max_sentence_chars: number,
  max_clauses_per_turn: 1 | 2
}

Signals that lower estimated level:
- user clicks pinyin/meaning frequently
- user uses recovery phrases repeatedly
- ASR rejects multiple attempts
- user gives very short or fragmented answers
- user selects hints before answering
- user abandons suggested responses
- repeated confusion after persona answers

Signals that raise estimated level:
- user answers without hints
- user produces full frame successfully
- user asks mirror questions
- user handles persona answer without recovery
- user uses previously introduced stretch words correctly
- user completes multiple turns without repair

Beginner Output Policy:

For P1_fragile:
- max 1 clause
- max 8–10 Chinese characters where possible
- max 1 unknown word
- prefer words from HSK1
- avoid abstract explanations
- avoid 因为/所以 chains unless already trained
- persona answers should be direct and concrete

Example:
Good:
我在奥克兰工作。
我喜欢中国菜。
我家有四个人。

Too hard:
我现在在奥克兰的一家公司做产品方面的工作。

For P1_stable:
- max 1–2 short clauses
- max 1–2 unknown words
- HSK1 + common HSK2
- simple connectors allowed: 也, 和, 但是, 因为

Example:
我在奥克兰工作，也住在奥克兰。

For P2_early:
- allow 2 unknown words
- allow slightly longer persona answers
- allow simple reason-giving
- keep sentence structure transparent

Example:
我喜欢这个工作，因为每天不一样。

Adaptation Rules:

After each turn:
1. Update learner_state from user behavior.
2. Estimate current comprehension and production confidence.
3. Set output limits for next persona turn.
4. Before rendering persona output, check vocabulary load.
5. If output exceeds the user’s limit, simplify it.
6. If simplification is impossible, choose a simpler alternative frame or shorter persona answer.

Vocabulary Load Check:

Before displaying any persona sentence:
- tokenize Chinese output
- compare tokens against learner_state.known_words + active level vocabulary
- count unknown words
- if unknown_count > max_unknown_words_per_turn:
    simplify sentence
- if sentence length > max_sentence_chars:
    shorten sentence
- if clause count > max_clauses_per_turn:
    split or simplify

Required trace fields:

Add debug trace fields so we can see adaptation decisions:

adaptive_trace = {
  estimated_level,
  known_word_count,
  unknown_words_in_output,
  max_unknown_words_allowed,
  sentence_length,
  max_sentence_chars,
  simplification_applied: true/false,
  reason: "...",
  original_output: "...",
  final_output: "..."
}

Beginner Mode UI behavior:

For P1 users:
- keep clickable tokens available
- keep recovery phrases available
- do not hide all support too early
- Challenge Mode should reduce support gradually, not remove core comprehension aids
- mirror/user-led questions should remain available after success

Important distinction:
Challenge Mode should challenge production, not destroy comprehension.

Acceptance tests:

T1 — P1_fragile user receives persona answer.
Expected:
- short sentence
- max 1 unknown word
- clickable support available

T2 — User repeatedly clicks hints and uses recovery.
Expected:
- estimated_level does not rise
- next persona outputs become shorter/simpler

T3 — User answers 5 turns without hints.
Expected:
- production_confidence increases
- max_unknown_words_per_turn may rise from 1 to 2

T4 — Persona output originally contains 4 unknown words.
Expected:
- output is simplified before display
- adaptive_trace records simplification

T5 — Mid-conversation mirror questions still appear.
Expected:
- no regression to existing mirror behavior

T6 — Post-close 明白了 state.
Expected:
- blue mirror/user-led questions appear
- questions respect learner level

Non-goals:
- Do not build a full AI tutor model yet.
- Do not rewrite selector logic.
- Do not create a complex scoring system.
- Do not use opaque LLM judgment as the only level estimator.
- Do not remove existing P1/P2 frame structure.

Architectural position:
This is an output-safety and learner-state layer.

Current flow:
selector → persona/frame output → UI

New flow:
selector → candidate output → learner_state check → simplified/adapted output → UI

Strategic goal:
MandarinOS should become beginner-safe by default:
the learner should rarely face more than 1–2 unknown words per turn, while still being gently stretched.