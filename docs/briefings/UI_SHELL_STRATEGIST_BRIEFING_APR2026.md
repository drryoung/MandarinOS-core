# MandarinOS UI Shell — Strategist Briefing (Apr 2026)

**Purpose:** Give ChatGPT (or any strategist/reviewer) a single, current picture of **what has been done to the learner-facing UI shell** (`ui/`), without re-reading code or prior threads.

**Scope:** The static HTML/CSS/JS shell served by `scripts/ui_server.py` — conversation layout, controls, options, hints, discovery, recovery, Explore Word, mobile behaviour. **Not** server-side conversation logic except where noted (e.g. mirror gating, reciprocal cards).

**Primary files:** `ui/index.html`, `ui/styles.css`, `ui/app.js`, `ui/ttsSpeak.js`.

---

## 1. Interaction model (what the learner sees)

- **Partner line:** Active question/statement in the **Active conversation** panel, with 🔊 (speak) and **?** (hints).
- **Transcript:** Shaded “Record of what was said” above; **Active conversation** label shortened to **“Active conversation — last statement”** (removed “from MandarinOS” for space).
- **Suggested responses:** Sentence/word options in **standard `option-panel`** structure (speaker, ?, tokenised hanzi) — see `.cursor/rules/mandarinos-ui-objects.mdc`.
- **Reversal / discovery:** **Blue** ask-back / discovery cards only (green “steer” cards removed earlier).
- **Recovery (“Need help?”):** Phrases for repair / not-understood flows; formatted like other response rows (see §4).
- **Explore Word:** Right-hand **Explore word** card panel; word insight popover on token tap.

---

## 2. Mobile and device constraints (documented + implemented)

- **Layout:** Responsive grid/stack; reduced horizontal overflow on narrow viewports; safe-area padding where relevant.
- **Input:** Larger touch targets for typing row (input height, buttons ~44px min where specified for thumbs).
- **iPhone LAN testing:** Documented in project briefings — UI over `http://<LAN-IP>:8765`; **speech recognition** may not work on iPhone over plain HTTP (secure context); typed testing is still valid.
- **TTS after “Start” on iPhone:** `speechSynthesis.speak()` must run in the user-gesture stack; async `fetch` breaks that. **`ttsUnlock()`** in `ttsSpeak.js` primes synthesis synchronously on relevant clicks (`Start`, discovery submit, etc.) so partner speech works after the server returns.

---

## 3. Typography and controls (cleaner scale)

- Font sizes were **consolidated** to a small set of **rem** stops (XL / LG / BASE / SM / XS) plus one **large** size for character-drill chips in Explore Word.
- **Frame** row: smaller label; frame `<select>` and transcript toolbar selects use **XS**-scale text; **Start** has green outline; **Clear memory** (formerly “Start Fresh” styling) without aggressive red border.
- **Partner** bar: moved to header; **no “No partner”** — first persona auto-selected when available.

---

## 4. Hints, speakers, and “Need help?” (recent behaviour)

### 4.1 Speaker and ? size

- Frame-line **🔊** and **?**, and per-option speaker/?, were **reduced** (target ~**32px** circles) for a lighter chrome; **right-aligned** in option rows via existing `option-actions` / flex layout.

### 4.2 Main ? in active conversation

- **English translation** for the **sentence** hint now appears when hints are first shown at **level 1** (with pinyin), not only after a second tap to “level 2”. This matches learner expectation that **?** reveals “what this says” in one action when data exists.

### 4.3 Need help? — order and format

- **Order (top → bottom)** inside the response area:
  1. English input / translate row (`engInputPanel`)
  2. **Need help?** recovery block **first**
  3. **Suggested responses** (white/green option panels)
  4. **Blue** discovery / mirror questions (`#discoveryPanel`) — inserted **after** `sentenceOptionsContainer` / `optionsContainerParent` so blue stays **at the bottom** of the suggested-response stack.

- **Recovery rows** were refactored to use **canonical `option-panel` + `option-btn`** pattern: each phrase shows **hanzi**, **pinyin**, and **English** inline (no extra ? clicks); 🔊 on the right. Header text **“Need help?”** precedes the phrase panels.

---

## 5. Explore Word and scrolling

- **Clickable tokens** in the active line use **persistent underline** (and dotted underline for unknown tokens) so tap targets are obvious without hover.
- **Scroll to Explore Word:** When the card panel **newly opens**, the view **smooth-scrolls** to `#cardPanel`. Scrolling runs only on **transition hidden → visible**, not on every re-render (avoids aggressive scroll on unrelated clicks).

---

## 6. Server-adjacent features referenced by the UI (context only)

These affect **what** appears in the shell, not the shell’s component rules:

- **Mirror routing:** Tighter gating so mirror persona answers fire only on **genuine questions**; **您 → 你** normalization for matching.
- **Reciprocal blue cards:** After certain partner questions, a **single** blue reciprocal ask-back can appear; mapping includes `mirror_core_map.json` + **`reciprocal_aliases`** (e.g. slotted `f_from_where` → `place_from` without changing live frame JSON).

---

## 7. Rules that still bind UI work

- **Option panels:** Learner-facing choices stay on **`div.option-panel`** with **🔊**, **?**, tokenised hanzi — do not fork a parallel UI path (see `mandarinos-ui-objects.mdc`).
- **Recovery:** `renderRecoveryPanelInto` must append into the **active** sentence/options container; behaviour was extended but remains within the same containers.
- **Extensibility:** Prefer content/ordering/CSS over new architectural branches unless explicitly requested.

---

## 8. Quick file map

| Area | Where |
|------|--------|
| Layout, inline chrome CSS | `ui/index.html` |
| Shared component styles | `ui/styles.css` |
| Turn flow, rendering, hints, recovery, discovery | `ui/app.js` |
| TTS + iOS unlock | `ui/ttsSpeak.js` |

---

**End of briefing.** For phase-specific strategist sign-offs, see existing `docs/briefings/PHASE7_*.md` and related Phase 8–12 briefs; this document is **UI-shell–focused** and current as of **Apr 2026**.
