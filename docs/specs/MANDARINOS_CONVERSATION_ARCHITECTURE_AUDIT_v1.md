### MandarinOS Conversation System — Structural Overview (Pre–Phase 11)

> Based on the current repo state (Phase 10 complete, Phase 6 runtime locked). No code changes; descriptive only.

---

## 1. Conversation Engines

**Engines discovered**  
From `p1_frames.json` / `p2_frames.json` and `scripts/ui_server.py`:

- `identity`
- `place`
- `family`
- `work`
- `hobby`
- `travel`
- `food`
- `life`

**Frame counts per engine**  
(From scanning P1+P2 frames; total frames = 92.)

- **identity**: 16 frames  
- **place**: 12 frames  
- **family**: 10 frames  
- **work**: 9 frames  
- **hobby**: 19 frames  
- **travel**: 9 frames  
- **food**: 7 frames  
- **life**: 10 frames  

**Purpose (as implied by names/specs)**

- **identity**: name, how people address you, self-description.
- **place**: where you’re from, where you live, opinions about that place.
- **family**: family, siblings, living arrangements.
- **work**: job / study, work life.
- **hobby**: interests, what you like doing, weekends, culture/collecting.
- **travel**: where you’ve been/want to go, travel experiences.
- **food**: local food, famous dishes, “what’s good there”, spicy/expensive.
- **life**: general life topics; catch‑all engine.

**Likely next engines / routing logic**  
Defined in `scripts/ui_server.py`:

- `_BRIDGE_TARGETS` (Phase 9.2) — “where can we bridge from here?”  

  - `identity` → `place`, `family`, `work`  
  - `place` → `identity`, `family`, `travel`, `food`  
  - `family` → `identity`, `place`, `work`  
  - `work` → `identity`, `place`, `family`  
  - `hobby` → `identity`, `travel`, `food`  
  - `travel` → `place`, `hobby`, `food`  
  - `food` → `place`, `travel`, `hobby`, `life`  
  - `life` → `identity`, `place`, `family`  

- `_FRAME_ORDER` — preferred sequence of **partner‑question frames** per engine (core → treasure/loop). Selector uses this first, then any remaining partner questions.

- **Routing logic in `_select_next_frame_ladder` / `_select_next_frame_bridge`**:
  - Tier 1: stay in current engine, follow `_FRAME_ORDER`, skip used frames, respect dependencies (e.g. name before name‑meaning).
  - Tier 2: if current engine exhausted, bridge to another engine per `_BRIDGE_TARGETS`.
  - Tier 2.5: if all engines exhausted, pick an earlier frame from another engine (avoid dead end).
  - Tier 3: repeat same‑engine as last resort.
  - Phase 10: additionally suppress “ask for fact X” frames when learner memory already has that fact.

---

## 2. Frames

**Total number of frames**

- P1 + P2 combined: **92** frames (from `p1_frames.json`, `p2_frames.json`).

**Frames grouped by engine (counts)**

- identity: 16  
- place: 12  
- family: 10  
- work: 9  
- hobby: 19  
- travel: 9  
- food: 7  
- life: 10  

**Per‑frame structure (from P1/P2)**

Each frame in `p1_frames.json` / `p2_frames.json` typically has:

- `id`: frame id (e.g. `f_ask_you_name`, `frame.identity.name`, `p2_pl_1`)
- `text`: Chinese sentence, e.g.:
  - `f_ask_you_name` — “你叫什么名字？”
  - `frame.identity.name` — “我叫{NAME}。”
  - `p2_pl_1` — “你觉得{CITY}生活怎么样？”
- `pinyin`: full pinyin with tone marks
- `text_en`: English gloss (often present, especially P1; many P2 frames also have `text_en`)
- `engine`: one of the engines above
- `difficulty`: integer (rough level indicator)
- `speaker`: `"partner"` or `"user"` (or empty for some P2 frames)
- `slots`: optional slot list for fillers (e.g. `{CITY}`, `{NAME}`, `{DISH}`)
- `option_tokens`: word ids for building options; `distractor_tokens` sometimes

**Number of response options per frame / words referenced**

- Option data is in `runtime/out_phase7/frame_options.runtime.json`:
  - Top‑level: `"frame_count": 92`, `"frames": { frame_id → { "options": [...], "hint_affordance": {...} } }`.
  - For each frame:
    - `options`: array of 0+ option objects:
      - `card_id` (links to word or frame)
      - `hanzi`
      - `pinyin`
      - `meaning`
      - `is_gold` (true/false)
      - `is_slot` (true for slot‑based frames)
      - `kind`: `"WORD"` or `"FRAME_WITH_SLOTS"`
  - Example:
    - `f_ask_you_name` has 3 sentence options: “我叫小明。”, “我叫丽丽。”, “我叫小红。”
    - `frame.location.live_question` has options like “我现在住在广州。/北京。/上海。”
    - `f_food_what_good` options: “有很多包子。/饺子。/火锅。”
- “Words referenced” are mapped through:
  - `frame_render_tokens.runtime.json` (`frames` = array of `{frame_id, text, tokens[]}` where tokens have `word_id`)
  - `cards_index.runtime.json` (`by_word_id` mapping `w_nihao` → card data id) plus card data in `tools/cards/out/cards_by_id.json` (loaded client‑side, not inspected here in detail).

---

## 3. Response Options

**Storage**

- Built as a runtime artifact: `runtime/out_phase7/frame_options.runtime.json`.
  - Contains **all frame options** for 92 frames.
  - Each frame id (P1 or P2) has a list of discrete options with metadata as above.

**Selection / use**

- In the server (`scripts/ui_server.py`):
  - `_frame_options` is loaded once at startup:
    - `frames` → `_frame_options[frame_id]`.
  - For a chosen `frame_id`, server sets:
    - `fo = _frame_options.get(frame_id, {})`
    - `options = fo.get("options", [])`
    - `gold_option_present` when any `is_gold` is true
    - `card_id` is either the gold option’s `card_id` or a fallback via `_stub_card_id` from word tokens.

- In the UI (`ui/app.js`):
  - Also loads `frame_options.runtime.json` into `frameOptionsRuntime` (`window._frameOptionsRuntime`).
  - When rendering a turn:
    - For a **Next question** (selector chooses frame), it **prefers server‑sent options** (so content matches the selected frame).
    - Otherwise, it can fall back to `frameOptionsRuntime.frames[frame_id].options` or `data.options`.
  - Response options appear as clickable “option panels” and as optional speech‑matched targets.

**Average number of options per frame**

- Not explicitly computed in code, but structurally:
  - Many P1 partner‑question frames have 3 sentence options.
  - Greeting frames and some others have 2–3 word options.
  - Some P2 frames may have 0 explicit options (question frames only).
  - Heuristically: **~2–3 options per frame on average** for frames with options; some frames have none (see §12).

---

## 4. Hint System

Implemented largely in **Phase 6** logic (`ui/app.js` + runtime artifacts).

**Sentence-level hints**

- State:
  - `window._sentenceHint = { pinyin, text_en }` is set from `data.frame_pinyin`, `data.frame_text_en` on each turn.
- Hint cascade:
  - `hint_cascade_state = { level: 0, turn_uid: null }`.
  - `getNextHintLevel(currentLevel)` cycles levels 0–3, skipping levels with no content.
  - `hintLevelHasContent(lvl, sentenceMode, sentenceHint, activeWordId)`:
    - If **sentence mode** (no active word):
      - Level 1: sentence pinyin
      - Level 2: sentence English
      - Level 3: sentence‑level etymology (if present)

**Word-level hints**

- `getWordHintData(wordId)`:
  - If `wordId` is `__opt_X`, uses option `X` from `window._tapOptions`.
  - Otherwise, tries:
    1. Resolved card content (`window._resolvedCard`).
    2. `cardsIndex.by_word_id[wordId]` for pinyin/meaning.
    3. Option whose `card_id` matches `wordId`.
- Hint cascade for words:
  - Level 1: pinyin
  - Level 2: meaning
  - Level 3: etymology (if `word_etymology` entry exists for that `word_id`).
- Word selection:
  - Clicking a token in `frameSentence` sets `window.lastClickedWordId`; hints will then use word mode instead of sentence mode.

**How hints are triggered in the UI**

- User taps the **Hint** button:
  - Hint level advances, either for the sentence or for the currently clicked word.
- Recovery / other flows:
  - Some states (e.g. recovery repeat) also adjust `hint_cascade_state.turn_uid` so hints apply to the right surface text.

---

## 5. Word Interaction Layer

**Clicking / selecting words**

- `frameSentence` is rendered from `frame_render_tokens.runtime.json` or `frame_tokens.runtime.json`:
  - Each Chinese token (with `word_id`) is wrapped in a span/button.
  - Click handlers:
    - Sets the active token (`_microGlossActiveTokenEl`).
    - Updates `window.lastClickedWordId`.
    - Triggers **micro-gloss** (inline tooltip with pinyin + meaning).
- Micro‑gloss (`_openMicroGloss`):
  - Shows a floating box near the token with:
    - Headword (hanzi).
    - If `window._resolvedCard` matches the word id, shows pinyin + meaning.
  - Includes “Open card →” button to open the card panel for that word.

**Card panel behavior**

- Card state is managed by `cardPanelState.js` + UI actions in `ui/app.js`:
  - `dispatch({ type: "OPEN_CARD", payload: { card_id } })` resolves the card.
  - Loads from `tools/cards/out/cards_by_id.json`.
  - Panel shows headword, pinyin, meaning, example sentences, etc.
  - `playBtn` uses `ttsSpeak` to play card audio if configured (or text‑to‑speech).

**Word metadata for learning**

- `cards_index.runtime.json`:
  - `"by_word_id"`: word_id → card_id or object with additional info.
- `word_etymology.runtime.json`:
  - `words[word_id]` → `characters[]` with hanzi, radicals, story; used at hint level 3.
- `frame_render_tokens.runtime.json`:
  - For each frame, token list with `word_id` to wire frames to cards and hints.

---

## 6. Etymology / Character Support

**Availability**

- `runtime/out_phase7/word_etymology.runtime.json`:
  - `word_count`: 14 (at build time).
  - `words`: map of `word_id` → etymology entry with `characters`, each with IDs and metadata.
  - `build_report.missing_character_id_count` indicates some characters are missing from etymology source, but many common words have partial coverage.

**How character data is retrieved**

- Client:
  - Loads `word_etymology.runtime.json` into `wordEtymologyIndex`.
  - Builds `hanzi → word_id` reverse index (`_hanziToWordId`).
- Word-level hint (level 3):
  - `hintLevelHasContent` checks `wordEtymologyIndex[wordId].characters`.
  - If nonempty, level 3 is considered to have content; UI can show etymology.
- UI:
  - Etymology is displayed either via the hint row or via a dedicated etymology view inside the card (etymology panel).

**Coverage**

- Partial:
