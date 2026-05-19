# Translation Surface Consistency Audit

**Date:** 2026-05-19  
**Scope:** Phase A audit + Phase B minimal fixes (no rendering-system rewrite)

---

## 1. Audit summary

MandarinOS intentionally uses **different cognitive-load surfaces**: the active turn is lighter (Chinese + optional hints), while the transcript is a richer review surface (toggle EN/PY, global “Show English” mode, async gloss).

The reported issue — **Chinese + pinyin visible in the active area without English, while the same line later shows English in the transcript** — is caused by a mix of:

1. **Intentional hint cascade** (? level 1 = pinyin, level 2 = English; not a bug by itself).
2. **Field propagation gaps** — some `addTranscriptEntry("partner", …)` calls omit `text_en`/`pinyin` even when server data exists.
3. **Async gloss drift** — `/api/gloss` fills `entry.text_en` for transcript review but did not update the active `#frameEnglish` / `_sentenceHint`.
4. **Path divergence** — recovery “repeat/slower” in `renderOptions` did not use `transcriptExtrasForRecoveryPartnerRepeat` (recovery panel path did).

No change to scorecard, selector, recovery escalation, or Phase 6 runtime boundaries.

---

## 2. Rendering surfaces

| Surface | Location | Fields used | Primary functions |
|--------|----------|-------------|-------------------|
| **Active partner sentence** | `#frameSentence` | `zh` (tokens or plain) | `renderFrameSentence`, `setActivePartnerStatement` |
| **Active English (always-on, normal mode)** | `#frameEnglish` | `text_en` / `frame_text_en` | `_setFrameEnglish` ← `_sentenceHint.text_en` |
| **Active hints (? cascade)** | `#hintPinyin`, `#hintMeaning` | `pinyin`, `text_en`, `etymology` | `renderHintAffordance`, `window._sentenceHint` |
| **Partner header** | `#partnerPrefixLine` | prefix only (Phase 11C) | `_updatePartnerHeader` |
| **Transcript log** | `#transcriptContent` | `text_zh`, `text_en`, `pinyin` | `addTranscriptEntry`, `renderTranscript`, `resolveLineEnglish` |
| **Transcript EN toggle / mode** | per-line EN btn; `transcriptDisplayMode` | `zh_en` or per-line `showEn` | `toggleLineEnglish`, toolbar select |
| **Async gloss** | transcript entries | `text_en` via `/api/gloss` | `maybeRequestGlossForEntry`, `glossLineCache` |
| **Suggested responses** | `.option-panel` | `hanzi`, `pinyin`, `meaning`/`text_en` | `renderOptions`, `renderSentenceOptions` |
| **Option ? hints** | `.option-hint-*` in panel | word card or recovery `meaning` | `renderHintAffordance` (option context) |
| **Blue discovery panel** | `#discoveryPanel` | `zh`, `py`, `en` on cards | `renderDiscoveryPanel` |
| **Recovery phrases** | recovery zone / options | `hanzi`, `pinyin`, `text_en`/`meaning` | `renderRecoveryPanelInto`, recovery handlers |
| **English input overlay** | `#engInputPanel` | English → suggested `zh` | translate flow (separate) |
| **Word card panel** | `#cardPanel` | card `pinyin`, `meaning` | `resolveCard`, in-card hints |
| **Scorecard / Progress** | right panel tabs | English reflection copy only | `renderScorecard`, `renderProgressView` |

---

## 3. Display rules (intentional)

| Surface | Chinese | Pinyin | English |
|---------|---------|--------|---------|
| Active (normal) | Always | ? level ≥1 or derived lexicon | `#frameEnglish` when `text_en` known; else ? level ≥2 |
| Active (challenge) | Always | ? cascade | Hidden in `#frameEnglish`; revealed via ? → `#hintMeaning` |
| Transcript default | Always | Per-line PY toggle | Hidden unless `zh_en` mode or EN toggled |
| Options / discovery cards | Always | Often on card | On card or via ? in panel |

**Not a goal:** force English on every surface.

---

## 4. Inconsistent pathways found

| ID | Issue | Type |
|----|-------|------|
| I1 | `renderOptions` recovery repeat omitted `transcriptExtrasForRecoveryPartnerRepeat` | Propagation |
| I2 | Partner stub paths (`runDirectionTurn`, `runMirrorTurn`, `runProbeTurn`, `submitDiscoveryQuestion`) added transcript without `frame_text_en` | Propagation |
| I3 | Gloss completion updated transcript only, not active line | Timing / drift |
| I4 | `fillSentenceHintPinyin` derives pinyin when server `frame_pinyin` empty → pinyin visible at ? L1 while `text_en` still empty | Data + cascade (expected until gloss/sync) |
| I5 | `setActivePartnerStatement(text, null)` clears `#frameEnglish` | Intentional for non-token lines |

---

## 5. Phase B minimal fixes applied

1. **`partnerTranscriptExtrasFromData(data, zh)`** — map `frame_text_en` / `frame_pinyin` (or counter-reply fields) into transcript extras.
2. **Stub transcript paths** — pass extras when adding partner lines.
3. **Recovery repeat in `renderOptions`** — align with recovery panel via `transcriptExtrasForRecoveryPartnerRepeat`.
4. **`_syncActiveEnglishFromGloss(entry, en)`** — when gloss returns, refresh `#frameEnglish` / `_sentenceHint` if entry matches current partner line.
5. **Recovery repeat** — refresh `_setFrameEnglish` from `_sentenceHint` after repeat display.

---

## 6. Files changed

- `ui/app.js` — helpers + propagation + gloss sync
- `docs/specs/Translation_Surface_Consistency_Audit.md` — this note
- `tests/test_translation_surfaces.py` — static consistency checks

---

## 7. Behavior before vs after

| Scenario | Before | After |
|----------|--------|-------|
| Recovery repeat via green option | Transcript missing EN; active relied on stale hint only | Transcript gets EN/PY from `_sentenceHint`; active EN refreshed |
| Mirror/probe/direction stub | Transcript EN empty until gloss; active had EN from stub handler | Transcript populated immediately when server sent `frame_text_en` |
| Gloss returns after partner line shown | Transcript could show EN on toggle; active stayed without EN | Active `#frameEnglish` updates if line is still current |
| ? clicked once | Pinyin only (unchanged) | Pinyin only (unchanged — intentional) |
