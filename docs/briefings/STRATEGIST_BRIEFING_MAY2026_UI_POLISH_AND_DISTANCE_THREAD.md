# MandarinOS — Strategist Briefing
**Date:** May 2026  
**Prepared by:** Cursor (Claude Sonnet 4.6)  
**For:** ChatGPT Strategist  
**Branch:** `phase10`

---

## Purpose of this briefing

This session completed five separate improvements — UI polish, a new content thread, learner support aids, and a word discoverability fix. None of these touched the core selector, runtime engine, or Phase 6 architecture. All changes were additive. This briefing summarises what was done, why it is safe, and identifies open questions for strategist review.

---

## 1. Partner button UI (cosmetic)

**Problem:** The persona selection buttons (小明, 美玲, etc.) were using the decorative calligraphy font `Ma Shan Zheng` which was hard to read at small size.

**Change:** Switched to `Noto Sans SC / Microsoft YaHei / system Chinese` font family with larger size and weight. No logic changes.

**Status:** Complete. Safe.

---

## 2. PLACE engine — distance conversation thread

**Problem:** The PLACE engine had no way for the learner to ask about distance, travel time, or transport between a persona's city and a reference city. The conversation ran out of depth too quickly on location topics.

**What was added (content-only — no engine changes):**

| Item | Detail |
|------|--------|
| 3 new frames | `f_place_distance_ref`, `f_place_distance_time`, `f_place_distance_transport` in `p1_frames.json` |
| Persona facts | `distance_profile` block added to all 5 personas with persona-specific `reference` city (e.g. 苏州 → 上海, 深圳 → 广州), `far_level`, `time`, `transport` |
| Response patterns | `distance`, `distance_time`, `distance_transport` slots added to `content/response_patterns.json` |
| Mirror support | All 3 frames mapped in `mirror_core_map.json` and `mirror_questions.json` |
| Server stubs | `_mirror_persona_stub`, `_direct_persona_answer`, `_topic_to_fact_key` extended in `ui_server.py` |

**Key constraint obeyed:** No universal "北京" reference city. Each persona uses the most natural nearby major city.

**Status:** Complete. Tested locally. Architecture-safe (purely additive content extension).

**Open question for strategist:** The 3 distance frames are currently in `p1_frames.json` with `speaker: "user"`. In the PLACE conversation flow, the *partner* would normally introduce a topic before the learner responds. Should these be re-tagged as `speaker: "partner"` (the partner asks the learner about *their* home's distance to a city), or is the current framing — where the learner initiates the question — the intended design? This determines whether mirror mode or direct mode is the primary use path.

---

## 3. English translation under partner sentences

**Problem:** The `#frameSentence` area showed only the Chinese sentence. Learners (especially beginners) had no persistent reference for what the partner was saying.

**Change:** Added an always-visible `#frameEnglish` div below the partner sentence. It is populated from `window._sentenceHint.text_en` — the `text_en` field already present on every frame — so no new data was required. Six call sites updated in `app.js` to keep it in sync.

**Status:** Complete. No API changes, no new data fields.

---

## 4. Translate box — pinyin and clickable Chinese

The learner-facing translate tool (English → Chinese) was improved in two ways:

### 4a. Pinyin below translated Chinese
When the external translation API returns a Chinese sentence, the app now generates pinyin client-side using the existing `buildSentencePinyinFromLexicon` function. This appears as a muted line below the Chinese, supporting learners who cannot yet read characters.

### 4b. Clickable tokens in translated text
The translated Chinese is now rendered as tokenised clickable spans, using the same `tokenizeHanziForOption` and `_openWordInsightPopover` infrastructure used everywhere else in the app. Clicking a word in the translated result opens the micro-gloss popover and, if applicable, the full word card panel.

**Status:** Complete. Fully reuses existing infrastructure — no new rendering path.

---

## 5. Word card discoverability fix (Option D)

**Problem:** After implementing clickable translate tokens, some words (specifically 处, 近 from the test phrase "很安静，很方便，到处都很近") could not be explored — clicking showed only a character-level gloss with no "Open Card" button.

**Root cause (two-part):**
1. `cards_index.runtime.json` was generated with only the 175 word cards explicitly referenced in frame tokens. Words like 安静 had full cards in `cards_by_id.json` but were excluded from the runtime index.
2. 近 and 到处 had no word card definitions at all — only character-level entries in `characters_1200.json`.

**Fix:**

| Part | Change |
|------|--------|
| Build filter | `build_cards_index()` in `tools/build_runtime_artifacts.py` now includes ALL 453 cards from `cards_by_id.json`, not just frame-referenced ones. Index grew: 175 → 453 entries. |
| New word cards | Added `w_jin3` (近 jìn, "close, nearby"), `w_chu4` (处 chù, "place, location"), `w_daoc` (到处 dàochù, "everywhere") to `cards_by_id.json`. |
| Rebuild | `python tools/build_runtime_artifacts.py` run and verified. |

**Architecture note:** One rule in `AI_CONTEXT.md` says not to hand-edit generated artifacts. In this case, `cards_by_id.json` is both a generated output *and* the source-of-truth card store. The three new cards were added directly because there is no upstream lexicon source for new ad-hoc word cards — this is an existing workflow gap. The strategist may want to define a canonical process for authoring new word cards (e.g. via `p1_words.json` + a card builder step).

**Status:** Complete. Browser hard-refresh required (no server restart needed — files are served statically).

---

## 6. What was NOT changed

- No changes to the selector, `_frame_order_priority`, or `_check_skip_condition`
- No changes to Phase 6 runtime engine
- No changes to trace contract or OPEN_CARD payload shape
- No new API endpoints
- No changes to difficulty ramp, mutual exclusion, or ASR logic
- The Scorecard & Challenge Mode spec (open in IDE) was **not implemented** — this session was UI polish and content only

---

## Current phase status (unchanged)

| Phase | Status |
|-------|--------|
| 12C — Repair → Comprehension | In progress / next |
| 12C.1 — Reciprocity & exploration | Active / evolving |
| 12D — Meaning + Move overlay | Planned |
| Alpha tuning | Active |

The work done this session sits entirely within **alpha tuning** and **12C.1 learner support** categories. It does not advance or block 12C, 12D, or the Scorecard spec.

---

## Questions for strategist review

1. **Distance frame speaker tagging:** Should `f_place_distance_ref` etc. be learner-initiated (current) or partner-initiated? This affects whether the learner practices *asking* these questions or *answering* them.

2. **Word card authoring workflow:** The three new cards (近, 处, 到处) were added directly to `cards_by_id.json`. Is there a preferred upstream process (e.g. adding to `p1_words.json` + running a card generator) that should be defined and followed for future additions?

3. **Scorecard spec:** The spec is open and ready. Is this the correct next implementation priority after the current session's work, or should 12C (repair ladder) be stabilised first?

4. **English translation display:** The `#frameEnglish` line is always visible. Should there be a toggle to hide it (for learners who want to practice without a crutch), or is always-on the right design for the alpha phase?

---

*Commit: `55db5ea` on branch `phase10`. 19 files, 1,433 insertions.*
