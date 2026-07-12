# MandarinOS ASR Pipeline

**Baseline commit:** `3be0315b2c9f7316b03ac2183a887f602ae9a297`
**Baseline tag:** `architecture-baseline-2026-07-12-r2`
**Source documentation branch:** `docs/architecture-v1`
**Approved contracts referenced:** `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md` (approval commit `63cb80a809d4377e936360b59a09af759f19a81f`)
**Document status:** Draft v1
**Last verified date:** 2026-07-12

All line-number citations refer to `ui/app.js` or `scripts/ui_server.py` at the baseline commit above unless another file is named. No local filesystem path appears in this document.

---

## 1. Purpose and scope

This document covers the complete R2 path from microphone input or typed learner text to the normalised text consumed by conversation routing and answer generation. It begins at the browser's speech-recognition API (or the typed-input control) and ends at the point where text becomes available to the mechanisms documented in `docs/ANSWER_SOURCE_CONTRACT.md` — the routing/classification variables `answer_text`, `routing_answer_text`, `_last_text_for_counter`, and `_routing_last_answer`. It also covers the reverse direction where relevant: which version of the text is displayed to the learner, stored in session capture, and subjected to late output-side repair.

**Speech recognition and conversation reasoning are separate layers.** Everything in §§4–9 of this document (browser recognition, transcript assembly, client-side normalisation, client-intercepted recovery, request construction) runs entirely in the browser and produces, at most, a single JSON payload sent to `/api/run_turn`. Everything from §10 onward runs on the server and is agnostic to whether the text originated from speech or typing — the server has no reliable signal that a given turn was spoken (§9, §17).

**Typed input is the semantic reference path.** Because the server cannot distinguish spoken from typed text with certainty, and because typed text bypasses the entire browser-recognition/transcript-assembly/client-normalisation stack, typed submission is the mechanism by which routing and answer-generation behaviour is defined and tested independently of ASR noise. Divergences between typed and spoken outcomes for the same intended utterance are ASR-pipeline-attributable; divergences that persist even for identical *submitted* text are conversation-engine-attributable and out of this document's scope (see `docs/ANSWER_SOURCE_CONTRACT.md`).

This document describes **R2 production behaviour as read from the source**, not a proposed ideal. Where behaviour is incomplete, inconsistent, or evidenced as a gap, that is recorded in place (§§4–18) and summarised in §21, not smoothed over.

**Responsibilities that remain in other documents:**

* **`docs/CONVERSATION_ARCHITECTURE.md`** — overall turn lifecycle, frame selection, E4 transport contract, engine/ladder mechanics once text has already reached the server as `answer_text`.
* **`docs/STATE_CONTRACT.md`** — authoritative schema and consumption status of every `conversation_state`/`state_update` field, including counters this document only cross-references (§18).
* **`docs/ANSWER_SOURCE_CONTRACT.md`** — how `counter_reply`/`counter_reply_en`/`counter_reply_pinyin` are produced once routing text is available, including the final ASR-junk output-repair pass, which this document references (§11) rather than re-analyses.

TTS (text-to-speech) synthesis and provider architecture are **out of scope** except where they directly affect microphone state, recognition timing, or recovery interaction (§15).

---

## 2. Input modes and trust boundaries

Two production input modes exist for submitting a learner turn, plus one non-submitting recovery-interaction mode and one mode-specific display variation:

* **Typed submission** — text entered directly (there is no dedicated "type an answer" text box for the main Chinese-answer turn in the reviewed code paths; the reviewed typed-equivalent path is the English-translate-then-Chinese-lookup flow via `#engInput`, `ui/app.js:9232`, `9397`, and Use-button submission, `ui/app.js:9414-9430`). Server-side test suites (`tests/test_spoken_chinese_routing.py`, `tests/test_spoken_question_routing_regression.py`) construct typed-equivalent payloads directly against `/api/run_turn` and `ui_server` functions, independent of any client UI, and this is the practical typed/reference path exercised in this repository's test suite.
* **Browser-recognised speech (Chinese answer mic)** — `listenForResponse()` (`ui/app.js:3545-4002`), triggered by `#tryRespondingBtn` (`ui/app.js:8085-8099`).
* **Browser-recognised speech (English translate mic)** — a second, independent `SpeechRecognition` instance (`ui/app.js:9343-9404`) that fills an editable field (`#engInput`) rather than submitting a turn.
* **Client-intercepted spoken recovery** — a non-submitting mode: certain recognised utterances are handled entirely client-side with no `/api/run_turn` request (§7).
* **Challenge Mode** — not a distinct input mode; it is a display-and-reveal variation layered on top of the Chinese answer mic and the typed/translate path (§14). Speech is not mandatory in Challenge Mode.

| Input mode | Initial producer | Client transformations | Server fields sent | Visible transcript | Semantic routing source |
|---|---|---|---|---|---|
| Typed / translated submission | Learner keystrokes into `#engInput` or a test-harness-constructed payload | None from the ASR stack (§4-§6 do not run); server-side `_normalize_zh_for_routing` still applies (§10) | `conversation_state.last_answer.submitted_text` (and/or `.selected_option_hanzi`) | The exact submitted string, rendered via `addTranscriptEntry` | `_last_text_for_counter` (routing-normalised submitted text) |
| Chinese answer mic (spoken, submitted) | Browser `SpeechRecognition` (`zh-CN`) via `listenForResponse()` | Interim/final assembly (§5), then none of §6's transformations are applied to the *submitted* string itself — see §6 for the precise scope of client-side normalisation | Same fields as typed, populated with `saidTrimmed` (the resolved transcript) | `saidTrimmed` verbatim, via `addTranscriptEntry` (`ui/app.js:7730` for the recovery-intercept path; matched/unmatched answer paths add it similarly) | Same server-side `_last_text_for_counter` pipeline as typed |
| Chinese answer mic (spoken, client-intercepted recovery) | Same recognizer | Interim/final assembly (§5), then exact-match recovery detection (§7) | **None — no request is sent** | `saidTrimmed` is still added to the visible transcript (`ui/app.js:7730`) | Not applicable — no server turn occurs |
| English translate mic | Browser `SpeechRecognition` (`en-US`) | None beyond the recognizer's own final-result trim (`ui/app.js:9396`) | Not applicable to `/api/run_turn` — feeds `#engInput` for a separate translate/lookup feature, not the conversation turn | The recognized text, placed into an editable field the learner can revise (`ui/app.js:9397`) | Not applicable — this text does not reach conversation routing |

Trust-boundary summary: **raw recogniser output** exists only transiently inside `listenForResponse`'s closure (`finalTranscript`/`interimTranscript`, `ui/app.js:3582-3583`) and is not separately preserved once `finish()`/`finalize()` resolve to a single string (§16 — this is where raw evidence is lost, except when diagnostics/ASR-trace capture is separately enabled, §16). **Displayed transcript**, **submitted text**, and **routing text** are three distinct strings from the point the server receives the payload onward (§10); they are frequently, but not always, identical.

---

## 3. End-to-end data flow

**Speech path (Chinese answer mic, non-intercepted case):**

```text
microphone
→ browser SpeechRecognition (zh-CN, interimResults=true, continuous=false)
→ onresult events → absorbResults() → interim/final transcript assembly (§5)
→ recognition ends (onend) → finish()/finalize() → resolved transcript ("saidTrimmed")
→ filler/recovery classification: matchSpokenRecoveryPhraseExact() against runtime phrase list (§7)
   ├─ MATCH on repeat/slower/meaning action → client-intercepted recovery: TTS replay, no server request (§7/§8)
   └─ NO MATCH (or "next_turn"/unrecognised action) → continue below
→ option-matching / free-answer classification (isIncompleteLearnerUtterance, semantic category match)
→ submitted payload: conversation_state.last_answer.submitted_text (+ selected_option_hanzi if an option was matched)
→ server: _normalize_zh_for_routing() → routing_answer_text / _last_text_for_counter (§10)
→ server-side ASR repair (contextual place repair, open-world location extraction, ASR near-match) (§11)
→ semantic classifiers (_is_rr, _is_meaning, _is_example, _is_confusion_signal, direct-persona/mirror/E3) — not all fed the same text (§10)
→ answer source + frame selection (docs/ANSWER_SOURCE_CONTRACT.md, docs/CONVERSATION_ARCHITECTURE.md)
→ response (counter_reply, frame_text, state_update)
→ visible learner transcript (addTranscriptEntry, already added at "saidTrimmed" step above)
→ session capture / diagnostics (§16)
```

**Typed path:**

```text
typed/translated text (e.g. via #engInput → translate → Chinese lookup, or a test-harness payload)
→ client submission: conversation_state.last_answer.submitted_text
→ server: _normalize_zh_for_routing() → routing_answer_text / _last_text_for_counter (§10)
→ semantic classifiers (same functions as the speech path)
→ answer source + frame selection
→ response
```

**Where the paths converge:** both paths produce the same `conversation_state.last_answer` shape and are processed by an identical server-side pipeline from `_answer_text_from_last_answer()` (`scripts/ui_server.py:2620-2627`) onward — the server has no code path that branches on whether text came from speech or typing (§9, confirmed by the absence of any `input_mode`/`is_spoken`/confidence field in the payload). **Where the paths remain different:** (a) the entire browser-recognition/transcript-assembly stack (§4-§5) has no typed equivalent at all; (b) client-intercepted recovery (§7) has no typed equivalent — a learner who types "再说一遍" is not intercepted client-side and the string is submitted to the server like any other turn, where it is handled (if at all) by server-side recovery detection (§8); (c) filler-only or acoustically-noisy utterances are a speech-only failure mode (§12); (d) Challenge Mode's transcript-hiding display logic applies to the rendered partner Chinese/English regardless of input mode, but its *reveal* triggers are recovery-count-driven and therefore speech-recovery-shaped even though typed input can also trigger a reveal via the "?" hint click (§14).

---

## 4. Browser recognition lifecycle

Two independent `SpeechRecognition`/`webkitSpeechRecognition` instances exist. **No claim of cross-browser support beyond what the code checks is made** — the only feature-detection performed is `window.SpeechRecognition || window.webkitSpeechRecognition` (`ui/app.js:3548`, `9345`); Firefox, which historically lacks both, is not handled specially and falls into the "not available" branch below.

### 4.1 Chinese answer mic (`listenForResponse`, `ui/app.js:3545-4002`)

* **API selection:** `ui/app.js:3548`.
* **Support detection:** if neither global exists, emits a `SPEECH_NOT_AVAILABLE` trace, shows a "Speech recognition is not available in this browser" notice, and resolves the returned promise with `{ transcript: "", matchedOption: null, asr_confidence: null, finishReason: "not_available" }` (`ui/app.js:3549-3553`) — no fallback to typed input is triggered automatically; the caller is responsible for that (§17).
* **Insecure-origin check:** on mobile layout (`_isMobileLayout()`), if `location.protocol === "http:"` and the host is not `localhost`/`127.0.0.1`, emits `SPEECH_INSECURE_ORIGIN`, shows a message directing the learner to HTTPS/Safari, and resolves with `finishReason: "insecure_origin"` (`ui/app.js:3555-3561`). This is a custom protocol string check, **not** `window.isSecureContext` — that global is not read anywhere in `ui/app.js`.
* **Recognizer creation:** `new SpeechRecognition()` (`ui/app.js:3569`).
* **Configuration:** `continuous = false`, `lang = "zh-CN"`, `interimResults = true` (`ui/app.js:3572-3574`). `maxAlternatives` is **not set** (absent from both the initial recognizer and the grace-restart `nextRec`, `ui/app.js:3736-3738`).
* **Start conditions:** `beginListening()` (`ui/app.js:3964-4000`) calls `rec.start()` (`ui/app.js:3974`); on mobile it runs synchronously (to preserve the iOS user-gesture chain, per comment at `ui/app.js:7518`); on desktop it is deferred via `setTimeout(beginListening, 380)` (`ui/app.js:3995-4000`).
* **Duplicate-start suppression:** outer guard `_micListenInFlight` in the caller (`ui/app.js:7520, 7528-7529`, checked before invoking `listenForResponse` at all); inner idempotency via a `resolved` flag checked at multiple points (`ui/app.js:3585, 3654-3655, 3705, 3766, 3883, 3887, 3910, 3965`) so `finish()`/`beginListening()` are safe to call more than once. There is **no** `isListening` boolean; the closest equivalent is the `armsMic` set of UI states (`preparing`, `listening`, `waiting`, `processing`, `reconnect`) toggling the `is-listening` body class via `_setListenState()` (`ui/app.js:3490-3492`).
* **Stop conditions — all routed through `finish(reason)`** (`ui/app.js:3654-3691`, idempotent, sets `resolved = true`, stops timers, calls `activeRec.stop()` with an `abort()` fallback, then `setTimeout(finalize, 250)`):

  | Reason | Trigger |
  |---|---|
  | `wall_clock_active` | 20s elapsed since first detected speech (`ui/app.js:3625-3628`) |
  | `wall_clock` | caller-supplied `timeoutMs` elapsed (7000ms from `_runChineseMicListen`, `ui/app.js:7519`, `3966-3968`) |
  | `thinking_grace_expired` | grace-restart deadline elapsed with no further speech (`ui/app.js:3717-3720`) |
  | `segment_cap` | `ASR_MAX_SEGMENTS` (4) reached during grace restarts (`ui/app.js:3777-3778`) |
  | `grace_error` / `permission_denied` | error during a grace-restart recognizer (`ui/app.js:3755-3762`) |
  | `silence_filler_extended` / `silence` | post-speech silence timers, the former after a one-time filler-triggered extension (`ui/app.js:3888-3900`) |
  | `onend` | recognizer ended and no further restart applies (`ui/app.js:3918, 3937`) |
  | `start_error` | `rec.start()` itself threw (`ui/app.js:3990-3991`) |
  | `error` / `permission_denied` | `onerror` (see below) |

* **Explicit user-initiated stop:** **not found** for the Chinese mic — there is no toggle-to-stop control on `#tryRespondingBtn`; the only way to end a listen session early is timeout/silence/error.

### 4.2 English translate mic (`ui/app.js:9343-9404`)

* **API selection:** `ui/app.js:9345`.
* **Support detection:** if unsupported, the mic button is disabled and its title set to "Speech recognition not supported in this browser" (`ui/app.js:9346-9349`) — no insecure-origin check exists for this recognizer.
* **Configuration:** `lang = "en-US"`, `interimResults = false`, `maxAlternatives = 1`, `continuous = false` (`ui/app.js:9366-9369`).
* **Start/stop:** click starts (`ui/app.js:9401`); a second click while `_engRecording` is true calls `_engRec.stop()` and returns (`ui/app.js:9361-9363`) — this recognizer **does** have an explicit user-toggle stop, unlike the Chinese mic.

### 4.3 Event handlers

**Chinese mic:**

* `onstart` (`ui/app.js:3940-3945`): sets `micStarted = true`, logs performance/diagnostic events, `_setListenState("listening")`.
* `onresult` (`ui/app.js:3904`): delegates entirely to `absorbResults(e)` (§5).
* `onend` (`ui/app.js:3906-3938`): if already `resolved`, returns. If text is present: on desktop (and under the segment cap) enters the thinking-grace restart (§4.4); on mobile, or once the segment cap is reached, calls `finish("onend")` immediately. If no text is present: retries `rec.start()` on the same instance up to 5 times if time remains (`onendRetryCount < 5 && elapsed < timeoutMs - 500`, `ui/app.js:3922-3932`), otherwise `finish("onend")`.
* `onerror` (`ui/app.js:3953-3962`): `"aborted"` and `"no-speech"` are explicitly ignored (return, since `finish()`/`onend` handle those cases elsewhere); `"not-allowed"`/`"service-not-allowed"` → `finish("permission_denied")`; **every other error string** (including `"network"`, `"audio-capture"`, etc. — none of which have a dedicated branch) → `finish("error")`.
* Diagnostic-only handlers with no control-flow effect: `onaudiostart`, `onspeechstart`, `onspeechend`, `onaudioend` (`ui/app.js:3948-3951`).

**English mic:** `onstart` sets `_engRecording = true` and UI classes (`ui/app.js:9371-9377`); `onend`/`onerror` both perform identical cleanup with **no error-type discrimination** (`ui/app.js:9378-9393`); `onresult` reads `ev.results[0]?.[0]?.transcript`, trims it, and if non-empty sets `engInput.value` and calls `doTranslate()` (`ui/app.js:9394-9400`).

**Permission errors:** handled identically for both recognizers via the `"not-allowed"`/`"service-not-allowed"` error strings; there is no separate "permission was previously denied, don't prompt again" state — each listen attempt re-triggers the browser's own permission UI if applicable.

### 4.4 Automatic restarts (desktop "thinking grace")

Constants: `ASR_THINKING_GRACE_MS = 1800`, `ASR_MAX_SEGMENTS = 4` (`ui/app.js:3435-3437`); `GRACE_MAX_RESTARTS = 8` (`ui/app.js:3702`).

When `onend` fires with text present, on desktop, under the segment cap, `_startThinkingGrace()` (`ui/app.js:3704-3810`) creates a **new** recognizer instance (`nextRec = new SpeechRecognition()`, same `zh-CN`/`interimResults=true`/`continuous=false` configuration, `ui/app.js:3731-3738`), sets `activeRec = nextRec`, and starts it, giving the learner 1800ms to continue speaking. If `nextRec` also ends with no text and time remains, the grace period restarts (up to 8 times, `ui/app.js:3783-3793`); if the deadline expires with no further speech, `finish("thinking_grace_expired")` runs. This mechanism is **disabled on mobile** — mobile `onend` with text goes straight to `finish("onend")` (`ui/app.js:3913-3918`), and the trace payload explicitly records `thinking_grace_ms: 0` for mobile sessions (`ui/app.js:3986`).

`minListenGraceMs`/`SPEECH_MIN_LISTEN_GRACE_MS_*` constants exist (`ui/app.js:3428-3429`, assigned `3611-3613`) but are **only referenced in the trace payload** (`ui/app.js:3984`) — they do not gate any timer or control-flow decision. This is recorded as a dead/diagnostic-only variable, not an enforced grace floor.

### 4.5 Mobile/iPhone differences represented in code

There is no literal `"iPhone"` string in `ui/app.js`; mobile-specific behaviour is gated on `_isMobileLayout()` (`matchMedia("(max-width: 768px)")`, `ui/app.js:10337-10338`) and comments referencing iOS. Concretely: the insecure-origin HTTPS gate (§4.1) only fires on mobile; pre-speech silence timers differ (`SPEECH_PRE_SPEECH_SILENCE_MS_MOBILE = 4000` vs. a desktop value of 4500, `ui/app.js:3425-3426, 3608-3610`); the thinking-grace restart mechanism is desktop-only (§4.4); `beginListening()` runs synchronously rather than after a 380ms delay, to preserve the iOS touch-gesture-to-`start()` chain (`ui/app.js:3995-3997`, comment at `7518`); and the mic button binds `touchstart` (not `click`) on mobile, with `click` debounced 600ms after a touch to avoid a double-fire (`ui/app.js:8087-8099`).

---

## 5. Interim and final transcript assembly

**Variables** (local to `listenForResponse`'s closure): `finalTranscript`, `interimTranscript` (`ui/app.js:3582-3583`); mirrored to `window._asrInterimPreview`/`window._asrInterimIsFinal` for UI display (`ui/app.js:3450-3463`).

**`absorbResults(e)`** (`ui/app.js:3812-3880`) runs on every `onresult` event:

1. Scans `e.results` from `e.resultIndex` onward, splitting each segment into `chunkFinal`/`chunkInterim` accumulators (diagnostic use only) and separately scans **all** of `e.results` to find `latestAny` (last non-empty transcript of any kind) and `latestFinal` (last non-empty *final* transcript) (`ui/app.js:3816-3833`).
2. If `latestFinal` is present: during a grace continuation, it is **appended** to the existing `finalTranscript` via `_joinSegments()` and `segmentCount` increments (`ui/app.js:3835-3839`); otherwise it **replaces** `finalTranscript` outright and `segmentCount` resets to 1 (`ui/app.js:3840-3842`). `interimTranscript` is cleared either way (`ui/app.js:3844`).
3. Else if `latestAny` (interim only) is present, `interimTranscript` is set to it directly, or, during a grace continuation, to the join of the existing final text with the new interim text (`ui/app.js:3847-3849`) — this is a preview-only concatenation, not committed to `finalTranscript`.

**`_joinSegments(a, b)`** (`ui/app.js:3635-3648`): trims both inputs, attempts to strip up to an 8-character prefix overlap of `b` against the tail of `a` (to avoid a repeated word/phrase at a segment boundary), and otherwise concatenates `b + a` — **no space or punctuation is inserted between joined segments.** This is the entire mechanism for Chinese/Latin spacing across segment boundaries; there is no separate spacing pass.

**Retention of previous final segments:** only during grace continuations (§4.4) — a non-grace final result replaces, rather than appends to, `finalTranscript`.

**Transcript submission eligibility:** `listenForResponse` resolves via `finish()`→`finalize()` (`ui/app.js:3667-3686`), which sets `finalTranscript = getBestTranscript()` and clears `interimTranscript`; there is no separate "submit" action — the caller (`_runChineseMicListen`, `ui/app.js:7547+`) receives the resolved transcript and decides what to do with it. **Empty-transcript handling:** `_runChineseMicListen` trims the resolved transcript into `saidTrimmed`; if empty, it shows a notice (message varies by `finishReason`) and returns without any server submission (`ui/app.js:7559-7589`). **Punctuation-only transcript rejection:** **not found** as an explicit distinct check at this stage — the closest related mechanism is `isIncompleteLearnerUtterance`/`_isSufficientLinguisticSignal` (§12), which operates on filler-only content, not punctuation per se.

**When recognition ends with no final transcript at all:** the empty-result retry logic in `onend` (§4.3) attempts up to 5 same-instance restarts before giving up via `finish("onend")`, at which point the caller's empty-transcript handling above applies.

**Learner editing before submission:** the Chinese-mic transcript is shown read-only via `_setAsrInterimPreview` into `#listenStatus` (`ui/app.js:3455-3464`) — **there is no editable field for it**; the learner cannot correct a misrecognised Chinese answer before it is submitted or intercepted. The English-mic transcript, by contrast, is written into the editable `#engInput` field (`ui/app.js:9397`), which the learner can revise before using it.

---

## 6. Client-side ASR normalisation

This section is scoped to transformations that run **before a server request is constructed**. Investigation confirms most transcript-shape handling in `ui/app.js` is used for internal classification (recovery matching, filler/incomplete-utterance detection, semantic category matching) rather than mutating the string that is ultimately submitted or displayed.

| Order | Transformation | Function | Applies to speech | Applies to typed text | Changes visible text? | Changes submitted text? |
|---|---|---|---|---|---|---|
| 1 | Segment-boundary join with overlap dedup, no inserted spacing | `_joinSegments()` (`ui/app.js:3635-3648`) | Yes (grace-continuation segments only) | No | Yes — it *constructs* the transcript that becomes visible | Yes — same string is submitted |
| 2 | Formal→spoken register substitution (fixed pair list) | `_normalizeSpokenRegister()` (`ui/app.js:2647-2661`), via `normalizeForMatch()` | Yes, but **only for internal comparison** | Yes, same internal comparison applies if the string reaches these functions | **No** — used only inside `normalizeForMatch`'s return value, which is a separate comparison string, not the transcript itself | **No** |
| 3 | Whitespace/CJK-punctuation strip for exact-match comparison | `normalizeForMatch()` (`ui/app.js:2657-2661`) | Yes, for recovery-phrase matching (§7) | Yes, if the same comparison path is invoked | No | No |
| 4 | Leading-filler strip (guarded, min. 2 chars remaining) | `normalizeConversationalFillers()` (`ui/app.js:3204-3216`) | Yes, for internal classification (`_detectSemanticCategory`, unmatched-answer classification, §12) | Yes, same classification path | **No** — not applied to the visible/submitted transcript | **No** |
| 5 | Filler-only / incomplete-utterance detection (no mutation) | `isIncompleteLearnerUtterance()`, `_isPureFillerUtterance()`, `_isSufficientLinguisticSignal()` (`ui/app.js:2667-2731`, `3888-3896`) | Yes | Yes | No | No — this is a classification gate (extends listening silence once), not a text transform |
| 6 | ASR-duplicate submission suppression (key comparison, not text mutation) | `_lastAcceptedAsrKey`/`_lastAcceptedAsrTime` check (`ui/app.js:7662-7670`) | Yes | Yes (same key mechanism applies to any accepted text) | No | No — it can suppress an entire submission, but does not alter the text of an accepted one |

**Conclusion — literal transcript cleanup vs. semantic reinterpretation:** the client performs **no literal cleanup of the submitted/visible transcript at all** beyond segment-join concatenation (row 1). Every other "normalisation"-adjacent function found (register substitution, whitespace/punctuation stripping for matching, filler stripping, filler-only detection) exists solely to support **internal classification decisions** (does this match a recovery phrase? is this utterance too sparse to submit? which semantic category does this fall into?) and explicitly does not mutate `saidTrimmed`, the string that is displayed and submitted. This is a deliberate, evidenced design property, not an omission — `_normalize_zh_for_routing()` on the server (§10) is where literal routing-text cleanup actually happens.

**Specific items investigated and their findings:**

* **Whitespace normalisation, punctuation removal, casing:** not applied to the submitted/visible text client-side (see above); `normalizeForMatch` does this only for its own internal return value.
* **Filler removal:** classification-only (row 4), not applied to visible/submitted text.
* **Repeated-token cleanup:** the only mechanism found is `_joinSegments`'s overlap-stripping at segment boundaries (row 1); there is no general repeated-word collapse within a single final segment.
* **Common ASR substitution repair, names/places:** **not found** on the client; this class of repair is entirely server-side (§11).
* **Empty-string handling:** covered in §5 (submission-eligibility check).
* **Transcript truncation:** **not found** — no maximum-length truncation of the transcript was located in `ui/app.js`.
* **`等你等`-style repair:** **not found on the client** — `_repair_asr_junk_text()` is a server-side function only (§11, `docs/ANSWER_SOURCE_CONTRACT.md` §3.3(4)).
* **Mobile-specific cleanup:** none beyond the lifecycle/timing differences already covered in §4.5; no mobile-specific text transformation was found.

---

## 7. Client-intercepted spoken recovery

**Detection function:** `matchSpokenRecoveryPhraseExact(transcript, phrases)` (`ui/app.js:2331-2350`). It normalises the transcript via `normalizeForMatch()` (whitespace/punctuation strip plus register normalisation, §6 row 2-3 — **not** filler stripping) and checks for **exact equality** (not substring containment) against each phrase's normalised `hanzi`, normalised `pinyin` (spaces stripped), or any entry in that phrase's `alternatives` array (`ui/app.js:2336-2347`). A separate function, `matchTranscriptToLearnerPhrase()` (`ui/app.js:2300-2314`), performs exact-**or**-substring matching but is used elsewhere (`computeRecoveryTriggerContext`, `ui/app.js:2384`, and the tap-driven recovery panel), not for spoken interception.

**Why exact matching exists (as evidenced by `tests/verify_spoken_recovery_exact_match.js`):** substring containment would cause an ordinary question that happens to contain a recovery-phrase substring — e.g. "你做什么工作" containing "什么" — to be misclassified as the learner asking "什么？" ("what?") and intercepted, silently discarding a genuine question. Exact matching (after whitespace/punctuation/register normalisation only) avoids this false-positive class.

**Phrase source:** loaded at runtime from `/runtime/out_phase7/recovery_phrases.runtime.json` (`ui/app.js:2236-2242`), a gitignored build artifact generated by `tools/build_runtime_artifacts.py::build_recovery_phrases_runtime()` from `content/recovery_phrases.json` (verified: `tools/build_runtime_artifacts.py:235-241, 679-692`). There is **no hardcoded phrase array** in `ui/app.js`; the exact phrase set is whatever `content/recovery_phrases.json` contains at build time. `learnerRecoveryPhrases(data)` (`ui/app.js:2262-2266`) filters the full phrase set to entries whose `use` is `"not_understood"`, `"topic_reset"`, or `"topic_shift"`.

**How filler stripping interacts with matching:** it does not. `normalizeForMatch()` does not call the filler-stripping function (`normalizeConversationalFillers`), so a filler-wrapped recovery utterance (e.g. "嗯…再说一遍" with a leading filler) will only intercept if its *exact* normalised form matches a phrase's `hanzi`/`pinyin`/alternatives verbatim — filler-wrapped variants are not generically absorbed unless the phrase-bank content itself lists that exact wrapped form as an alternative.

**Recognised recovery phrases in `content/recovery_phrases.json`** (confirmed entries): "嗯？"/"啊？" (`recovery_action: "soft"`), "什么？" (`"repeat"`), "等一下"/"我想想" (`"soft"`), "再说一遍" (`"repeat"`), "慢一点说" (`"slower"`), "我有点不懂"/"什么意思啊？" (`"meaning"`), "好吧" (`"next_turn"`).

| Recovery type | Detection rule | Client action | Server request? | Frame state changed? | Counter updated? | Transcript shown? |
|---|---|---|---|---|---|---|
| Repeat (`recovery_action: "repeat"`, e.g. "再说一遍") | Exact match, action resolved via `getRecoveryAction()` | Replay partner's last question/statement via TTS; add both learner and partner lines to transcript | No | No — semantic frame state is preserved, since no turn is submitted | Yes — `_challenge.recoveryCount`, `_tracker.recovery_uses` (§8) | Yes — `saidTrimmed` added via `addTranscriptEntry` (`ui/app.js:7730`) |
| Slower (`"slower"`, e.g. "慢一点说") | Exact match | Same as repeat, but TTS rate `0.82` and a `"好的，慢一点："`-prefixed restatement | No | No | Yes | Yes |
| Meaning (`"meaning"`, e.g. "我有点不懂") | Exact match; `getRecoveryAction()` maps `"meaning"` → `"repeat"` internally (`ui/app.js:5294-5295`), so meaning-tagged phrases are handled identically to repeat, not with a distinct meaning-specific client action | Same as repeat | No | No | Yes | Yes |
| Soft (`"soft"`, e.g. "嗯？"/"啊？"/"等一下"/"我想想") | Exact match; `getRecoveryAction()`'s final fallthrough resolves unknown/`"soft"` actions to `"repeat"` (`ui/app.js:5296`) | Same as repeat (an evidenced consequence of the fallthrough, not a documented distinct "soft" behaviour) | No | No | Yes | Yes |
| Next-turn (`"next_turn"`, e.g. "好吧") | Exact match, but explicitly **excluded** from interception — the gate at `ui/app.js:7729` only proceeds for `"repeat"`/`"slower"`/`"meaning"` | Falls through to normal `runTurn` flow (comment at `ui/app.js:7776-7777`) | **Yes** | Yes — normal server frame selection runs | Not a recovery-counter increment | Yes |
| Any non-matching confusion-adjacent utterance (e.g. bare "我不懂" not present verbatim in the phrase bank) | No exact match found | No interception occurs | Depends on downstream classification (`classifyUnmatchedFreeAnswerDecision`, regex checks at `ui/app.js:3160, 3372`) — may still reach the server as an ordinary or confusion-flagged turn | Determined by server (§8) | Determined by server-side counters (`docs/STATE_CONTRACT.md`) | Yes |

**How accidental recovery interception is prevented:** exclusively by exact matching (as opposed to substring containment) plus the action-type gate (`"repeat"`/`"slower"`/`"meaning"` only — `"next_turn"` phrases and unmatched text fall through). There is no additional confidence threshold or contextual gate found.

**What happens after the first, second, and later recovery attempts (client-side):** `_challenge.recoveryCount` increments on every intercepted (or panel-tapped) recovery regardless of count (`ui/app.js:7735`, `5406`); once `_challenge.recoveryCount >= 2`, `_challengeRevealText()` fires (§14). There is no separate client-side "third attempt" behaviour beyond the reveal — repeated recovery attempts beyond the second simply keep replaying/repeating without a further escalation step client-side (escalation *is* handled server-side once a turn actually reaches the server via `_is_confusion_signal`-driven paths and repair escalation, per `docs/ANSWER_SOURCE_CONTRACT.md` §9 — but client-intercepted recovery, by construction, never reaches the server, so that server-side escalation only applies to turns that were *not* client-intercepted).

**Challenge-mode transcript reveal timing:** covered fully in §14; the two-recovery-attempt threshold above is the primary driver.

**Audio replay/slower-replay behaviour:** both the spoken-intercept path and a parallel tap-driven recovery-panel path (`renderRecoveryPanelInto`, `ui/app.js:5389-5468`) use `ttsSpeak()` to replay the partner's last question, at a reduced rate (`0.82`) for the slower action. The recognizer is already closed by the time this TTS replay runs (interception happens after `listenForResponse` has resolved), so no explicit `rec.stop()` call is needed at this point — see §15 for the separate guard that stops *partner* TTS before *opening* the mic.

**Recovery counters — client-owned:** `_challenge.recoveryCount`, `_tracker.recovery_uses`, `_tracker.successful_recoveries`, `window._consecutiveNotUnderstood`, and `window._recoveryPromptsByFrame` are all plain in-memory JavaScript state (not `localStorage`, not sent to or read from `conversation_state` for the client-intercepted path). One asymmetry worth noting: `_tracker.successful_recoveries` increments only via the tap-driven panel's `_pendingRecovery` flag (`ui/app.js:5394`, `6877-6879`) — the spoken-intercept path increments `recovery_uses` but never sets `_pendingRecovery`, so a spoken recovery interception can never itself register as a "successful recovery" by this counter's definition. **Cross-reference `docs/STATE_CONTRACT.md`:** the mirror-confusion escalation counter (`mirror_confusion_count`, server-side, SIC-1) and these client-only counters are **separate mechanisms** — client-intercepted recovery, by design, never touches server-side confusion counters at all, since no request is sent.

---

## 8. Spoken-recovery versus server recovery

### Client-intercepted recovery

* No `/api/run_turn` request is made (§7 table).
* No semantic frame progression occurs — the frame the learner was answering remains exactly as it was.
* Local replay/reveal behaviour only: TTS restatement of the partner's last line, and, after the second occurrence, Challenge Mode text reveal (§14).
* Applies only to the **exact** phrase set from `content/recovery_phrases.json` filtered to `use ∈ {not_understood, topic_reset, topic_shift}`, and only when the resolved action is `"repeat"`, `"slower"`, or `"meaning"` (§7).

### Server-routed recovery

* Speech (not intercepted) or typed text is submitted as an ordinary turn.
* Server-side classifiers may respond: `_is_meaning`, `_is_example`, `_is_rr`, `_is_confusion_signal`-gated branches, and `_lexical_definition_reply` (all documented fully in `docs/ANSWER_SOURCE_CONTRACT.md` §4, Priorities 8-15).
* Normal server frame selection still runs on the same turn (`docs/ANSWER_SOURCE_CONTRACT.md` §9's precise, non-absolute wording: the frame may advance, remain in the engine, or be explicitly repeated/rephrased).
* Answer-source priority applies in full (`docs/ANSWER_SOURCE_CONTRACT.md` §4).
* Cross-turn recovery state may be incomplete — mirror-confusion escalation (`STATE_CONTRACT.md` SIC-1) and noisy-location round-trip (SIC-2) are both documented open gaps that apply here.

### What determines which path handles an utterance

Exactly one gate: whether `matchSpokenRecoveryPhraseExact()` finds an exact match **and** the resolved action is `"repeat"`/`"slower"`/`"meaning"` (§7). This check happens **only** on the spoken (Chinese-mic) path, inside `_runChineseMicListen`, **before** any server request is constructed. Typed text is never evaluated against this matcher at all (§3) — a typed "再说一遍" is submitted to the server like any other text and is handled, if at all, by the server-side `_is_rr`/confusion-signal mechanisms in `docs/ANSWER_SOURCE_CONTRACT.md` §4 Priority 10, not by client interception. This is a structural, not incidental, asymmetry between the two input modes (§13).

---

## 9. Request construction

The `/api/run_turn` handler reads its JSON body once (`scripts/ui_server.py:8961-8968`). Learner-answer text is **not read from the payload root** — no `payload.get("answer_text")`, `payload.get("submitted_text")`, or `payload.get("selected_option_hanzi")` exists anywhere in `scripts/ui_server.py`.

**Learner text lives inside `conversation_state.last_answer`** (`cs = payload["conversation_state"]`, `scripts/ui_server.py:9138-9139`; `last_answer = cs.get("last_answer")`, `9175`):

| Field | Read site | Purpose |
|---|---|---|
| `submitted_text` | `last_answer.get("submitted_text")` (`9184, 9242, 9528, 9538, 9878, 10189, 10302, 10436`) | Primary learner-text source |
| `selected_option_hanzi` | `last_answer.get("selected_option_hanzi")` (`9182, 9243, 9529, 9878, 10233`) | Fallback learner-text source (option-tap turns) |
| `selected_option_meaning` | `last_answer.get("selected_option_meaning")` (`9183`) | Not learner text; the tapped option's gloss |
| `frame_id` | `last_answer.get("frame_id")` (`9178, 9199, 9541`, etc.) | Which frame the turn answered |

**Root-level payload fields unrelated to the main answer path** (early-return/stub branches only): `direction_question_zh`/`direction_question_topic`/`direction_intent` (mirror/direction stub, `8989, 8999-9000, 9047`), `probe_id`/`probe_hanzi` (oxygen-probe stub, `9078, 9084`), `learner_skip_confusion` (read from `cs`, not payload root, `9145-9147, 11417`), `diag_trace_id` (`8978`, diagnostics only).

**Fields explicitly NOT found in the payload:** `confidence`/`asr_confidence`/`recognition_confidence`, `is_spoken`, `input_mode` (as a client-sent field), `raw_transcript`, any challenge-mode marker. Challenge-mode-driven behaviour is entirely a client-side display concern (§14) with no corresponding server-side signal in the request.

**Precedence when `submitted_text` and `selected_option_hanzi` disagree:** `submitted_text` wins unconditionally, via `_answer_text_from_last_answer()` (`scripts/ui_server.py:2620-2627`):

```text
scripts/ui_server.py:2620-2627 (paraphrased):
  answer_text = norm_text(last_answer.get("submitted_text")
                          or last_answer.get("selected_option_hanzi")
                          or "")
```

This same fallback order — `submitted_text` before `selected_option_hanzi` — is repeated independently at `scripts/ui_server.py:1798-1801` for a separate helper, and is **not** always applied identically: `_last_user_text` (`scripts/ui_server.py:10434-10436`) uses **only** `submitted_text`, with **no fallback** to `selected_option_hanzi` — an option-tap-only turn (no free-text) has a populated `answer_text` but an empty `_last_user_text`. This is a genuine, evidenced divergence in field precedence between two different consumers, not a single uniform rule (§10).

**Text appearing in more than one payload location:** confirmed — the same logical learner text is read via both `submitted_text` and `selected_option_hanzi` inside the single `last_answer` object; it does not additionally appear at the payload root. No case was found of the same text appearing in *both* `last_answer` and a separate root-level field.

---

## 10. Server text selection and routing normalisation

### `_normalize_zh_for_routing()` (`scripts/ui_server.py:3753-3766`)

In order: (1) outer `.strip()`; (2) leading-filler removal via `_strip_leading_fillers()`, itself driven by `_FILLER_PREFIX_RE` (`3716-3723` — single-character particles `啊嗯呃哦哎呀唉`, discourse markers `那个|就是|然后|这个|好那|嗯那`, and Latin fillers `ne|ah|um|uh|er`), **guarded** so that if stripping would leave fewer than 2 characters, the original text is kept unchanged (`3737-3738`); (3) CJK inter-character whitespace collapse (`_CJK_SPACING_RE`, `3742-3744`); (4) a second `.strip()`; (5) trailing routing-filler strip (`_TRAILING_ROUTING_FILLER_RE`, `3746` — trailing `啊呢吧嗯哈啦` plus an optional trailing `？?！!。.`). **Not performed:** full-width-to-half-width conversion, general punctuation normalisation beyond the trailing-particle case. The function's own docstring states it does not mutate its input and that the original is preserved separately for display/memory purposes (`3756-3757`).

### The four/five text variables and their exact relationships

| Variable | Derivation | Normalised? |
|---|---|---|
| `last_answer.submitted_text` / `.selected_option_hanzi` | Raw client-sent fields | No |
| `answer_text` | `_answer_text_from_last_answer()`: `submitted_text` or `selected_option_hanzi`, `.strip()`-only | Strip only |
| `routing_answer_text` | `_normalize_zh_for_routing(answer_text)` | Yes, per above |
| `_routing_last_answer` | A shallow copy of `last_answer` with `submitted_text` (always) and `selected_option_hanzi` (only if it was originally non-empty) replaced by `routing_answer_text`, when `last_turn_was_answer` and `routing_answer_text` is truthy; otherwise identical to `last_answer` (`scripts/ui_server.py:9208-9217`) | Partial — only the text fields are swapped; all other keys (`frame_id`, `selected_option_meaning`, etc.) are untouched |
| `_last_text_for_counter` | `routing_answer_text` if truthy, else the raw `submitted_text`/`selected_option_hanzi` fallback directly (**not** via `_answer_text_from_last_answer`) (`scripts/ui_server.py:9875-9879`) | Usually yes (in practice equal to `routing_answer_text` whenever `answer_text` is non-empty) |

### Consumer table — **classifiers do not all consume the same text**

| Consumer | Text field selected | Normalisation applied | Fallback order | Original text preserved elsewhere? |
|---|---|---|---|---|
| `_is_rr`, `_is_meaning`, `_is_example`, `_lexical_definition_reply` (`_lex_ct`) | `_last_text_for_counter` | Routing-normalised | `_last_text_for_counter`'s own (see above) | Yes — `answer_text` unchanged in parallel |
| `_is_confusion_signal` (most call sites: `10007, 10057, 10091, 10118, 10129, 10144, 10165, 10326, 10330, 10342`) | `_last_text_for_counter` (or, once, `_routing_text_for_place_q`, a further place-repaired variant, `10007`) | Routing-normalised | As above | Yes |
| `_is_confusion_signal` (`9454, 9492, 10276, 10404, 11409`) | **Raw `answer_text`** | None | n/a | n/a — this *is* the raw form |
| User-initiative overrides — `_is_frustration_or_insult`, `_is_learner_disclosure`, `_is_persona_challenge`, `_food_responsive_reply`, `_has_volunteered_travel_intent` (`9902-9937`) | **Raw `answer_text`** | None | n/a | n/a |
| `_is_plain_affirmation` (`9296`) | **Raw `answer_text`** | None | n/a | n/a |
| `_is_direct_persona_question` (main routing call sites: `10056, 10093, 10120, 10244`) | `_last_text_for_counter` | Routing-normalised | As above | Yes |
| `_is_user_question` (`9218-9219`) | `_routing_last_answer` (a dict, with text fields already routing-normalised) | Routing-normalised | n/a | Yes — `last_answer` itself unmodified |
| `learner_memory_capture.capture_from_turn()` (`9180-9185`) | **Raw** `last_answer.submitted_text`/`.selected_option_hanzi` fields directly | None | Internal to that module | Yes — this *is* the raw form |
| `learner_stated_location` (persistent state write, `12132-12133`) | **Raw `answer_text`** | None | n/a | n/a |
| `_extract_open_world_location()` for routing/clarify purposes (`10148, 11592-11596`) | `_last_text_for_counter` | Routing-normalised | As above | Yes |

**Conclusion:** the assumption that "all classifiers consume the same text" is **false**. The main recovery/meaning/example/lexical ladder and most direct-persona/confusion-signal routing is uniformly fed `_last_text_for_counter` (routing-normalised), but the highest-priority user-initiative overrides (frustration, disclosure, persona-challenge, responsive-food, volunteered-travel), plain-affirmation detection, several confusion-signal call sites, and both learner-memory capture and the persistent `learner_stated_location` write, all consume **raw** `answer_text` instead. This means leading-filler stripping and CJK-spacing collapse (§10's normalisation) do not apply when those specific mechanisms evaluate the text — a filler-prefixed frustration/insult utterance, for example, is matched against its *raw* form, not its routing-normalised form.

---

## 11. Server-side ASR repair and semantic correction

| Mechanism | Lines | Input | Effect scope |
|---|---|---|---|
| `_repair_asr_junk_text()` | `618-629` | Location-extraction tails (`4153, 4158`); learner-memory slot values (`11679, 11693`); the **final** `response["frame_text"]` and `response["counter_reply"]` (`12409-12415`) | Both routing-adjacent (extraction) and **visible/response-level** (final pass) — this is the same mechanism documented as a post-chain output-repair gap in `docs/ANSWER_SOURCE_CONTRACT.md` §3.3(4); see below for the distinction |
| `_repair_contextual_place_question()` | `4486-4531` | `_last_text_for_counter` (`9999`) | **Routing text only** — its own docstring states "the raw learner transcript is never touched" (`4494-4496`); output feeds `_routing_text_for_place_q` (`10002`), never the visible transcript or learner memory |
| `_extract_open_world_location()` | `4126-4160` | `_last_text_for_counter` for routing/clarify (`10148, 11596`); **raw** `answer_text` for the persistent `learner_stated_location` write (`12132-12133`) | Split — routing paths get the normalised input; the persisted learner-fact does not |
| `_detect_travel_asr_near_match()` | `2154-2161` | Raw `answer_text` (`9345`, i.e. `9552-9554` in context) | Sets `_travel_asr_candidate`; feeds repair-escalation counter-reply text (`docs/ANSWER_SOURCE_CONTRACT.md` §9), not the visible transcript |
| `_recover_malformed_travel_destination()` / `_extract_travel_destination()` | `5871-5887` / `5890-5924` | Volunteered-travel statement text (`answer_text` via `_travel_intent_followup`, `9937`) | Follow-up reply construction only |
| `_detect_near_miss_answer()` | `2203-2217+` | Raw `answer_text` (`10453`) | Selector clarification-frame choice |
| `_is_closing_blocked_by_learner_signal()` | `3917-3956` | Raw `answer_text` (`11103-11104`) | Gates whether a closing move fires; internally computes a `"low_asr_confidence"` heuristic from non-CJK/single-character content — this is a **server-computed heuristic**, not a client-sent confidence value (§9 confirms no such field is sent) |
| `_normalize_place_name()` (imported) | Call sites `11680-11681, 11694-11695` | Values already extracted into learner-memory slots (`lives_in`/`hometown`) | Applied to **stored memory**, not to live routing text |

**Safeguards against over-correction found:** the leading/trailing-filler-strip length guard in `_normalize_zh_for_routing` (§10, keeps original if stripped result would be under 2 characters); `_repair_contextual_place_question`'s explicit routing-only scope (never touches the raw transcript); `_repair_asr_junk_text`'s fragment list (`_ASR_JUNK_OUTPUT_FRAGMENTS`, `613-615`) is a fixed, curated set (e.g. `"等你等"`, `"等一等"`) rather than a general heuristic, limiting false-positive removal of legitimate content that happens to contain similar substrings — though no explicit test was found proving that constraint is sufficient in all cases (§21).

**Distinguishing input repair from output repair:** every mechanism in this table operates on *routing* text (used to decide which answer-source branch fires, §10) or on values about to be *persisted* to memory, and runs **before** answer-source resolution. The **output** repair documented in `docs/ANSWER_SOURCE_CONTRACT.md` §3.3(4) — the final `_repair_asr_junk_text()` pass over `response["counter_reply"]`/`response["frame_text"]` at lines 12409-12415 — is the *same function* but a **distinct call site**, running *after* the entire answer-source/dedup/repair-escalation chain has already finalised `counter_reply`, and is explicitly documented there as not recomputing English or pinyin. This document treats that specific late call site as belonging to `docs/ANSWER_SOURCE_CONTRACT.md`'s scope (output finalisation) and does not re-analyse it here; the earlier call sites of the same function (location-tail/memory-slot cleanup) are genuinely input-side and are this document's scope.

**Aliases/island/region normalisation:** `_TRAVEL_ASR_NEAR_MATCHES` (`2129-2132`, ASR-confusion pairs such as `"刚吃"→"甘肃"`); `_TRAVEL_SUBREGIONS`/`_TRAVEL_COUNTRIES` (`2324-2340`); `_KNOWN_PLACE_NAMES` (`4470-4472`, union of the above plus `_CITY_LOCATION_BRIEF` keys); `_CITY_LOCATION_BRIEF` (`4361-4373`). No English-place-name-to-Chinese alias table was found in `scripts/ui_server.py`; Latin text of 3+ characters is accepted as a plausible location by a length heuristic (`4087-4089`) rather than translated.

---

## 12. Filler handling

**Exact filler inventory (client, `ui/app.js`):**

* Acoustic filler characters: `_FILLER_CHAR_SET = {嗯, 啊, 呃, 哦, 喔, 哎, 诶, 呀, 唉}` (`ui/app.js:2664`).
* Discourse fragment fillers: `_DISCOURSE_FRAGMENT_FILLERS = {这个, 那个, 就是}` (`ui/app.js:2665`).
* Single-token incomplete-utterance filler set (a superset including `我`): `ui/app.js:2727`.
* Leading-filler regex for internal-classification stripping: `_LEADING_FILLER_PAT` (`ui/app.js:3204`), matching repeated leading acoustic particles, discourse markers (`那个|就是|然后|这个|好那|嗯那`), or Latin fillers (`ne|ah|um|uh|er`).

**Exact filler inventory (server, `_normalize_zh_for_routing`, §10):** a separate, independently-defined set (`_FILLER_PREFIX_RE`, `scripts/ui_server.py:3716-3723`) covering overlapping but not identical particles/markers to the client list above — these are two distinct filler definitions maintained in two different files/languages, not one shared source.

**Removed globally or only for classification?** On the client, fillers are stripped **only for internal classification** (recovery matching uses `normalizeForMatch`, which does not strip fillers at all; semantic-category/unmatched-answer classification uses `normalizeConversationalFillers`, which does) — the visible and submitted transcript is never filler-stripped client-side (§6). On the server, `_normalize_zh_for_routing` **does** strip leading/trailing fillers from the routing text that several (not all — §10) classifiers consume, but never from `answer_text` itself or from anything persisted to learner memory.

**Repeated fillers collapsing:** `_isPureFillerUtterance()` (`ui/app.js:2667-2674`) treats a string as pure filler if every CJK character is in `_FILLER_CHAR_SET` or the whole string is a discourse-fragment filler — this is a detection function, not a text-rewriting collapse; repeated fillers are not rewritten into a single instance anywhere found.

**Fillers surrounding a recovery phrase:** as established in §7, filler-wrapped recovery phrases are **not** generically stripped before the exact-match check — a filler-wrapped variant only intercepts if it happens to be listed verbatim as a phrase-bank `alternatives` entry.

**Filler-only utterances — are they submitted?** Not blocked outright; `isIncompleteLearnerUtterance()` (`ui/app.js:2722-2731`) detection triggers a one-time silence extension (`SPEECH_FILLER_EXTEND_MS`, `ui/app.js:3888-3896`) to give the learner a chance to continue speaking, rather than an automatic rejection. If the learner does not continue, the filler-only text can still be submitted and is then handled by server-side classification (or rejected there, per `tests/verify_asr_filler.js`'s `insufficient_linguistic_signal` mechanism).

**Filler cleanup and the visible transcript:** confirmed **no** effect — §6 and §7 both establish that the displayed/submitted string is never filler-stripped client-side.

**Risk of legitimate content being incorrectly stripped:** the length guard on both the client's `normalizeConversationalFillers` (keeps original if stripped result is under 2 characters, `ui/app.js:3214-3215`) and the server's `_normalize_zh_for_routing` (same 2-character floor, `scripts/ui_server.py:3737-3738`) is the only evidenced safeguard against this; no test was found that specifically probes a legitimate multi-word statement beginning with what looks like a filler character used as a real word (e.g. "哦" used as an exclamation within a longer sentence) to confirm the guard is sufficient in all cases.

**Test evidence and its limits:** `tests/verify_asr_filler.js` exercises **mirrored** JavaScript filler-classification logic (re-implemented in the test file), not the real functions extracted from `ui/app.js` via `tests/_load_app_js_helper.js` — this is a meaningful distinction from, for example, the E4 client-handoff regression tests, which do use the real extracted helper. `tests/test_asr_filler_suppression.py` performs static source-string assertions on `ui/app.js` (confirming the relevant identifiers exist and are wired in the expected order) plus a subprocess invocation of `verify_asr_filler.js`. **Neither test executes the actual shipped `ui/app.js` filler functions.** This is recorded as a specific, evidenced gap in behavioural test coverage for this subsystem (§21).

---

## 13. Typed-versus-spoken parity

| Behaviour | Typed | Spoken | Equivalent? | Difference and rationale |
|---|---|---|---|---|
| Direct persona questions | Reaches `_direct_persona_answer` via the same server pipeline once submitted | Same, once submitted (i.e. not client-intercepted) | Yes, after submission | No client-side difference once text reaches the server (§3) |
| E4 handoff | Computed from `user_asked_question`/mirror/E3 flags on submitted text | Same | Yes, after submission | E4 eligibility (`docs/ANSWER_SOURCE_CONTRACT.md` §15) has no input-mode dependency in the server code |
| Recovery | No client-side interception exists for typed text at all — a typed recovery phrase is submitted and handled only by server-side mechanisms (§8) | Client-intercepted for exact-matching phrases with a `repeat`/`slower`/`meaning` action; everything else submitted | **No** — structurally different paths | Client interception exists specifically to avoid a server round-trip for spoken utterances during active listening; there is no equivalent "intercept before submit" step in the typed flow, since typed submission has no listening session to intercept during |
| Filler handling | No filler-only silence-extension mechanism applies (there is no "listening" phase for typed text) | `isIncompleteLearnerUtterance`-driven silence extension (§12) | **No** | Filler handling before submission is inherently speech-specific; both modes are subject to the *same* server-side `_normalize_zh_for_routing` filler-stripping once submitted (§10) |
| Transcript display | Displayed exactly as submitted | Displayed as `saidTrimmed` (post interim/final assembly, pre any filler stripping) | Yes, once resolved to a final string | Both paths call the same `addTranscriptEntry` |
| Punctuation | Whatever the learner typed | Browser-recognizer-supplied (typically none, or minimal, depending on the recognizer's own behaviour — `ui/app.js` adds none itself, §5/§6) | **Not guaranteed** | The recognizer's own punctuation insertion (if any) is outside application code's control; typed punctuation is exactly what the learner entered |
| Names | Typed verbatim | Subject to ASR mis-hearing with no name-specific repair mechanism found (§11's alias tables cover places, not personal names) | **No** | No client- or server-side name-correction mechanism was found for either path; typed names are simply not subject to the ASR mis-hearing failure mode at all |
| Places | Typed verbatim, then server routing/repair applies identically to any text | Subject to ASR mis-hearing, mitigated by `_repair_contextual_place_question`, `_TRAVEL_ASR_NEAR_MATCHES`, and open-world location extraction (§11) | Converges after server repair, but only for the specific malformed patterns those mechanisms recognise — an unrecognised mis-hearing is not repaired for either path, since the repair mechanisms are pattern-matched, not a general phonetic corrector | Same server-side mechanisms apply to typed near-miss strings too (they operate on submitted text regardless of origin), but typed input by construction rarely produces the ASR-confusion patterns these mechanisms target |
| Learner-memory extraction | `capture_from_turn()` reads raw `submitted_text`/`selected_option_hanzi` (§10) — identical regardless of input mode | Same | Yes | This consumer is explicitly input-mode-agnostic (§9/§10) |
| Session capture | Same `last_answer` shape stored either way | Same | Yes, at the stored-field level; **no** input-mode marker is stored to later distinguish spoken from typed turns (§9, §16) | The absence of an input-mode field means session review cannot, from stored data alone, determine which turns were spoken vs. typed |
| Challenge mode | Not gated on input mode at all — typed/translated submission works without any Challenge Mode guard (§14) | Same — mic path also has no Challenge Mode guard | Yes | Confirmed by the absence of any `_challenge.active` check on either submission path |
| Browser permission/error handling | **Not applicable** — no browser API is invoked for typed submission | Full lifecycle in §4 (permission denial, unsupported browser, insecure origin, etc.) | **No** | Structurally different; typed input has no failure mode analogous to microphone permission |

**Guaranteed identical after server submission:** answer-source resolution, E4 eligibility, learner-memory capture, session-capture field shape, Challenge Mode gating. **Remains input-mode-specific:** whether client-side recovery interception can occur at all (spoken-only), whether a listening/silence-extension phase exists (spoken-only), whether browser permission/support/insecure-origin failure modes apply (spoken-only), and the specific class of noisy/malformed text each mode is prone to producing (ASR mis-hearing patterns vs. typing errors, which are not addressed by any repair mechanism in this codebase).

---

## 14. Challenge Mode interaction

**Is speech mandatory?** No. The typed/translate-then-submit path (`#engInput` → `doTranslate()` → Use-button submission, `ui/app.js:9414-9430`) has no `_challenge.active` guard, and the mic path (`_runChineseMicListen`, `ui/app.js:8085-8099`) likewise has no Challenge-Mode-specific gate blocking or requiring it. Both input modes remain available regardless of Challenge Mode state.

**Transcript visibility rules:** `#frameEnglish` is forced to `display: none` while `_challenge.active` (`ui/app.js:4023-4025, 4052-4055`); the suggested-response containers (`#sentenceOptionsContainer`, `#optionsContainer`) are also set to `display: none` after turn render (`ui/app.js:7289-7294`). The partner's **Chinese** text in `#frameSentence` is **not** hidden via any JavaScript `style.display` toggle found in `ui/app.js` — `renderFrameSentence()` always populates it (`ui/app.js:4125-4139`); if Chinese-text hiding exists in Challenge Mode, it is driven by a CSS rule keyed on the `challenge-mode` body class (`ui/app.js:8162`) that lives outside `ui/app.js` itself and was not verified as part of this investigation (out of scope: CSS files were not audited).

**First/second/later recovery behaviour and reveal timing:**

1. **First recovery** (spoken-intercepted or panel-tapped): `_challenge.recoveryCount` increments to 1; no reveal.
2. **Second recovery:** `_challenge.recoveryCount >= 2` triggers `_challengeRevealText()` (`ui/app.js:5408, 7737`), which sets `helpLevel = 3`, adds a `challenge-text-revealed` class to `document.body`, and calls `renderHintAffordance()` (`ui/app.js:8148-8156`).
3. **Independent reveal trigger:** the **first** click of the "?" hint button, while `helpLevel < 3`, also calls `_challengeRevealText()` regardless of recovery count (`ui/app.js:7353-7357`, comment: "first ? click reveals Chinese characters").
4. **Suggested-response reveal:** tapping `#showOptionsBtn` reveals the options containers and sets `helpLevel` to 4 (`ui/app.js:8194-8195`) — a separate, later reveal stage from the text reveal above.

**No timer-based reveal was found** — reveal is strictly interaction-count-driven (recovery count or hint-button click), never elapsed-time-driven.

**Audio replay controls:** identical mechanism to non-Challenge-Mode recovery (§7) — `ttsSpeak()` at normal or `0.82` (slower) rate; in Challenge Mode, the recovery panel is rendered into a dedicated `#challengeRecoveryZone` container rather than the standard sentence-options container (`ui/app.js:6063-6067, 5915-5917`).

**Is hidden transcript text nevertheless submitted or stored?** Yes, unconditionally. Challenge Mode's hiding is purely a **display** concern — the partner's frame text is still fully populated into the DOM and into `window._sentenceHint`/`window._currentFrameText`/`window._lastPartnerSpokenText` during ordinary turn processing (`ui/app.js`'s normal turn-render path, not specially bypassed for Challenge Mode). The ASR interim preview (`_setAsrInterimPreview`, §5) has **no** Challenge-Mode guard and displays during listening regardless of Challenge state. The conversation transcript (`addTranscriptEntry`) is likewise never suppressed by Challenge Mode.

**Reset behaviour:**

| Trigger | Effect |
|---|---|
| Start of each server turn while Challenge is active | `_resetChallengeHelpState()` called from `_runTurnInner` (`ui/app.js:6640-6641`), clearing `_challenge.recoveryCount`, `helpLevel`, and the `challenge-text-revealed` class |
| `_resetCurrentSessionState()` (new session/page reload path), when Challenge is active | Same reset (`ui/app.js:6498`) |
| Persona selection change | Resets reveal maps for persona facts/voice-lines (`ui/app.js:4977-4978`) — does **not** reset `_challenge.recoveryCount`/`helpLevel` |
| Beginner difficulty level | `_challenge.active` is force-disabled (`ui/app.js:631-632`) |
| User toggle | `toggleChallengeMode()` explicitly flips `_challenge.active` and the body class (`ui/app.js:8160-8162`) |

**State ownership:** entirely client-owned, in-memory (`_challenge` object, `ui/app.js:118-123`); no `conversation_state`/`state_update` field carries Challenge Mode state to or from the server (confirmed by the absence of any such field in §9's payload audit).

---

## 15. TTS and microphone coordination

**Scope note:** only ASR-relevant TTS behaviour is covered here; TTS provider/synthesis architecture is out of scope.

**Is the microphone disabled while partner audio plays?** There is no explicit disabling of the mic *button* while TTS plays, but the recognizer itself is never automatically started during TTS playback — the mic only opens on an explicit user tap (`#tryRespondingBtn`), and `listenForResponse()` proactively **cancels any in-progress partner TTS** the moment it is invoked: `if (window.speechSynthesis) window.speechSynthesis.cancel()` (`ui/app.js:3563-3567`), with a comment stating the purpose is explicitly to prevent the recognizer from transcribing the app's own speaker output.

**Can recognition capture the app's own TTS?** No dedicated guard against this scenario beyond the cancel-on-open behaviour above was found — since the mic is never auto-started during TTS and TTS is cancelled the instant the mic is about to open, the practical window for self-capture is a user tapping the mic button while TTS audio is *already* mid-playback through hardware output devices that echo into the microphone (e.g. speakers instead of headphones) — the cancel call stops further TTS output at the moment of that tap, but any TTS audio already emitted before the tap is not otherwise excluded from being picked up. No additional isolation mechanism (e.g. muting during a synthesis window, or comparing recognized text against recently-spoken TTS text) was found.

**Automatic listening after TTS, if implemented:** **not found.** No `onended`/`onboundary` handler on TTS output was found that automatically starts the recognizer. The normal turn-submission flow is the reverse: the learner's *own* speech (or typed text) triggers TTS playback of it, and `runTurn()` is invoked once that TTS completes (`ui/app.js:7641-7653, 7872-7886`) — this is TTS-after-recognition, not recognition-after-TTS.

**Stop/cancel ordering:** `speechSynthesis.cancel()` runs synchronously at the very start of `listenForResponse()`, before the recognizer is created or `beginListening()` is scheduled (§4.1) — cancellation always precedes recognizer start, never the reverse.

**Replay interaction:** recovery/recovery-panel TTS replay (§7) runs entirely after `listenForResponse()` has already resolved and the recognizer is closed, so no recognizer-state interaction is needed at that point. A separate transcript-panel replay feature (`replayTranscriptLine`/`speakTranscriptLine`, `ui/app.js:2136-2157`, and `stopTranscriptReplay` at `ui/app.js:2126-2131`) also only calls `speechSynthesis.cancel()`/`ttsSpeak()` and is unrelated to the recovery-intercept logic.

**Race-condition guards:** the one explicit guard found is the recovery-panel tap being blocked while `document.body.classList.contains("is-listening")` (`ui/app.js:5391`) — i.e. the learner cannot trigger a panel-based recovery replay while a listening session is active. No equivalent guard was found preventing a *spoken* recovery interception from racing with an in-progress TTS replay from a *different* recovery action, since spoken interception only evaluates the transcript after the listening session (which itself cancels TTS on open) has already ended.

**Mobile autoplay/permission implications:** covered under §4.5's insecure-origin gate; no additional TTS-specific mobile-autoplay restriction handling was found in `ui/app.js`.

---

## 16. Transcript and session-capture contract

| Storage | Form stored |
|---|---|
| On-screen conversation history (`conversationTranscript`, `addTranscriptEntry`) | The resolved client string at submission/interception time — `saidTrimmed` for speech, the typed/translated string for typed input. This is **pre**-server-routing-normalisation and, for speech, **post**-interim/final-assembly but **pre**-any-filler-stripping (§5, §6) |
| Browser session state (`window._tracker`, `window._learnerObs`, `_challenge`) | Counters and flags, not transcript text itself, except where a transcript string is passed as a parameter to a logging call |
| Server session capture (`conversation_state.last_answer`, persisted turn-by-turn) | `submitted_text`/`selected_option_hanzi` exactly as sent by the client — i.e. the same string as the on-screen transcript entry, **not** independently re-normalised for storage |
| Diagnostics/trace records (`_diag_cap`, when `diag_trace_id` is set and diagnostics are enabled) | **Multiple versions side by side**: `la_submitted_text`/`la_selected_option_hanzi` (raw), `server_raw_answer_text` (= `answer_text`, strip-only), `routing_text` (= `routing_answer_text`, fully normalised) — captured at `scripts/ui_server.py:9236-9275` |
| Parallel selector trace (`_sel_trace`) | `asr_raw_text` (raw `submitted_text`), `accepted_text`/`normalized_answer` (both actually equal to `answer_text`, **not** routing-normalised despite the `normalized_answer` name — an evidenced naming/content mismatch) (`scripts/ui_server.py:9533-9545`) |
| Persistent learner memory (`learner_memory_capture.capture_from_turn`) | Raw `last_answer` fields (§10) — not routing-normalised |
| Export/session-review batches (`export_session_review_prompt.py`, exercised by `tests/test_export_session_review_prompt.py`) | Renders whatever is in the stored transcript record, including an `asr_raw` field distinct from the rendered/display text where present in the input data — confirming the export tool is capable of carrying a raw-vs-display distinction *if* the upstream data supplies it, though this document did not verify that the live `/api/run_turn` capture path actually populates a comparably-named `asr_raw` field itself (not found in the `_diag_cap`/`_sel_trace` field lists above under that exact name) |

**Where raw evidence is lost:** the transient `finalTranscript`/`interimTranscript` closure variables inside `listenForResponse` (§5) are never persisted anywhere once resolved to a single string — if a grace-restart join (`_joinSegments`) makes an incorrect overlap-strip decision, the pre-join individual segments are not recoverable from any stored record. Similarly, once the client sends `saidTrimmed` to the server, the browser's own interim hypotheses for that utterance are gone; only the offline ASR-trace-joining tool (`scripts/report_asr_traces.py`, exercised by `tests/test_report_asr_traces.py`) is capable of reconstructing a client-side vs. server-side comparison, and only when both a client-side trace event and a server-side trace record exist for the same turn (that tool explicitly handles and flags missing-half cases, per the test file's evidence).

**Where reconstruction is impossible:** the exact raw browser recognizer hypothesis for any turn that was routing-normalised, filler-classified-away, or client-intercepted-and-never-submitted cannot be reconstructed from server-side session capture alone, since the server never receives that turn's text at all in the intercepted case, and only receives the already-resolved `saidTrimmed` string (not the interim history) in the submitted case.

---

## 17. Error and fallback behaviour

| Scenario | Visible effect | Retry behaviour | Typed input still available? | State reset | Duplicate-submission risk |
|---|---|---|---|---|---|
| Microphone/recognizer unavailable (`SpeechRecognition` undefined) | "Speech recognition is not available in this browser" notice; promise resolves `finishReason: "not_available"` (§4.1) | None | Yes — no code disables the typed/translate path as a consequence | None needed (nothing started) | None |
| Insecure context (mobile + HTTP, non-localhost) | "Mic needs HTTPS…" notice, 6000ms display; `finishReason: "insecure_origin"` | None | Yes | None | None |
| Permission denied (`"not-allowed"`/`"service-not-allowed"`) | `finish("permission_denied")` → standard finish/finalize path; caller shows a notice (exact wording keyed by `finishReason`, `ui/app.js:7566-7573`) | None automatic — a new mic tap re-triggers the browser permission flow | Yes | `resolved` flag set; no counters specifically reset | Low — no partial transcript to resubmit |
| Recognition unsupported | Handled identically to "unavailable" above (same code path) | — | Yes | — | — |
| No speech (`"no-speech"` error) | Explicitly ignored in `onerror` (§4.3); handled instead via the empty-`onend` retry logic (up to 5 retries) or eventual `finish("onend")` | Up to 5 same-instance restarts | Yes | — | None — empty transcript is not submitted |
| Aborted recognition (`"aborted"` error) | Explicitly ignored — expected side effect of `finish()` calling `rec.stop()`/`abort()` | None (by design, this is not a failure) | Yes | — | None |
| Network recognition failure | **No dedicated branch** — falls into the generic `finish("error")` catch-all (§4.3) | None automatic | Yes | — | Low |
| Recogniser ending unexpectedly (`onend` with no text, retries exhausted) | `finish("onend")`; caller's empty-transcript handling shows a notice | Exhausted at 5 retries, then stops | Yes | — | None |
| Duplicate recogniser callbacks | Guarded by the `resolved` flag (idempotent `finish()`) and `_micListenInFlight` at the caller level (§4.1) | n/a | n/a | n/a | Mitigated by design, not observed as a live incident in the evidence gathered |
| Empty final transcript | Caller (`_runChineseMicListen`) shows a notice and returns without submitting (§5) | Learner must re-tap the mic manually | Yes | `setUiMode("RESPOND")` (`ui/app.js:7559-7589`) | None |
| Server failure after successful recognition | Not specifically traced in this investigation's scope (this is a network/HTTP-layer concern of `runTurn()`'s own fetch error handling, not the ASR pipeline); **not found** as an ASR-specific fallback | Not determined in this document | Presumed yes, but not verified here | Not determined here | Not determined here — recorded as an open question rather than asserted either way |
| User presses stop/cancel | **No explicit stop control exists for the Chinese mic** (§4.1) — the closest equivalent is the English mic's toggle-stop (`ui/app.js:9361-9363`), which is a separate feature | n/a for the Chinese mic | Yes | `_engRecording = false` for the English mic | None |
| TTS overlap | Mitigated by `speechSynthesis.cancel()` at the start of `listenForResponse()` (§15) | n/a | n/a | n/a | n/a |

**Risk of duplicate submission generally:** mitigated specifically for the ASR-accepted-answer path by the `_lastAcceptedAsrKey`/`_lastAcceptedAsrTime` 6-second dedup window keyed on transcript text plus frame ID (`ui/app.js:7662-7670`), reset on each new partner frame (`ui/app.js:6985`). This guard applies to the unmatched-free-answer branch specifically (per the citing subagent's investigation); it was not confirmed to apply uniformly to every submission branch (e.g. the matched-option branch), which is recorded as an unverified scope boundary rather than asserted as either present or absent there.

---

## 18. State interactions

| Field/variable | Owner | Producer | Consumer | Reset | Transported to server? | Returned by server? |
|---|---|---|---|---|---|---|
| `finalTranscript`/`interimTranscript` | Browser/DOM (closure-local) | `absorbResults()` | `finish()`/`finalize()`, `_setAsrInterimPreview` | Per listen session (new closure each call) | No — resolved to `saidTrimmed` before any request | No |
| `_micListenInFlight` | Client global | `_runChineseMicListen` entry | Same function (guard) | Cleared at function exit | No | No |
| `_challenge.recoveryCount`, `.helpLevel`, `.active` | Client global | Recovery interception, hint clicks, user toggle | Reveal-timing checks (§14) | Per turn (`recoveryCount`/`helpLevel` via `_resetChallengeHelpState`); `.active` on explicit toggle or beginner-level force-off | No | No |
| `_tracker.recovery_uses`, `.successful_recoveries` | Client global | Recovery interception / panel tap | Session-end telemetry (`endSession()`) | New session | Yes — as part of session-end payload, not per-turn `conversation_state` | No |
| `window._consecutiveNotUnderstood` | Client global | `selectRecoveryPhrase` | Various accept/reset call sites | New session, or on accepted answer | Not confirmed as part of `conversation_state` in this investigation | No |
| `window._lastAcceptedAsrKey`/`._lastAcceptedAsrTime` | Client global | ASR-accepted-answer path | Dedup-suppression check | On new partner frame | No | No |
| `conversation_state.last_answer.submitted_text`/`.selected_option_hanzi` | Server-authoritative once sent; client-produced | Client submission | `_answer_text_from_last_answer`, `_last_text_for_counter`, learner-memory capture, etc. (§10) | Overwritten every turn | **Yes — this is the transport itself** | Echoed back only insofar as the next turn's request reconstructs it client-side; the server does not return the learner's own prior text as a distinct field |
| `answer_text`, `routing_answer_text`, `_last_text_for_counter`, `_routing_last_answer` | Server-local per-request | Derived server-side (§10) | Answer-source/frame-selection pipeline | Recomputed every request; never persisted | No — server-local only | No |
| `learner_stated_location` | `conversation_state`/`state_update`, session-scoped | `_extract_open_world_location(answer_text, ...)` gated on `_RESIDENCE_QUESTION_FRAME_IDS` | Its own carry-forward; `last_place_subject` seeding; diagnostics (fully detailed in `docs/ANSWER_SOURCE_CONTRACT.md` §10/§17 — not redefined here) | Carried forward indefinitely unless overwritten by a fresh residence answer | Yes | Yes, via `state_update` |
| `learner_memory["lives_in"]` | Persistent, cross-session (`learner_memory` module) | `learner_memory_capture.capture_from_turn()` on raw `last_answer` fields | Several place-answer construction helpers (`docs/ANSWER_SOURCE_CONTRACT.md` §10/§17) | Not reset by ASR-pipeline mechanisms; persists across sessions | N/A — persisted server-side, not part of the per-turn client payload | Indirectly, via `response["learner_memory"]` continuity fields |
| `mirror_confusion_count`, `location_retry_count`, `location_clarify_hint`, `pending_dest_candidate`, `repair_attempt_count`, `recent_confusion_count`, `consecutive_not_understood` (server-side confusion/recovery counters) | Server-local/`state_update`, per `docs/STATE_CONTRACT.md` | Server-side recovery/confusion mechanisms | Server-side recovery escalation (`docs/ANSWER_SOURCE_CONTRACT.md` §9) | Per `docs/STATE_CONTRACT.md`'s SIC-1/SIC-2/SIC-3 gaps — several do **not** round-trip | Partial — see `docs/STATE_CONTRACT.md` for the authoritative per-field consumption table | Per `docs/STATE_CONTRACT.md` |
| `_diag_cap` fields (`la_submitted_text`, `routing_text`, `server_raw_answer_text`, etc.) | Server-local, diagnostics-only | `/api/run_turn` handler when `diag_trace_id` is present and diagnostics enabled | `response["diag"]`, offline `report_asr_traces.py` tooling | Per request | Client sends `diag_trace_id` only (opt-in) | Yes, as `response["diag"]`, when enabled |

**Cross-reference note:** this table intentionally does not redefine the authoritative schema, consumption status, or reset semantics already established in `docs/STATE_CONTRACT.md` for the server-owned counters listed in the second-to-last row; it only identifies which of them are ASR/recovery-adjacent so this document's scope is clear.

---

## 19. Enforced ASR invariants

### Enforced invariants

* **Client-intercepted recovery sends no server turn.** Verified directly: the intercept branch (`ui/app.js:7729-7774`) returns before any `fetch`/`runTurn` call, for the `"repeat"`/`"slower"`/`"meaning"` action classes (§7, §8).
* **Typed input bypasses browser ASR entirely.** No code path routes typed/translated submission through `SpeechRecognition` (§2, §3) — this is a structural absence, not a configuration flag.
* **Semantic frame state is preserved during intercepted recovery.** Because no request is sent, the server-side frame/engine state that would otherwise be mutated by turn processing is never touched for an intercepted utterance (§7, §8).
* **Server classifiers use a partially-deterministic but non-uniform text-precedence order.** `_last_text_for_counter`'s own fallback order is deterministic (§10), and it is verified which specific classifiers use it vs. raw `answer_text` — but the overall claim that *all* classifiers share one precedence order is **not** enforced; §10's consumer table is the authoritative per-classifier answer, not a single blanket rule.
* **`submitted_text` takes precedence over `selected_option_hanzi` when both are present**, for the primary `answer_text`/`_last_text_for_counter` derivation (§9, §10) — though `_last_user_text` (§9) is a specific, narrower exception with no fallback at all, not a violation of this invariant for the fields it actually governs.
* **The recovery-panel/spoken-intercept TTS replay always occurs after the listening session has ended**, since interception logic runs only on the resolved transcript, after `listenForResponse()` has already returned (§7, §15) — there is no code path attempting a replay while the Chinese-answer recognizer is still active.
* **Partner TTS is explicitly cancelled before the Chinese-answer mic opens** (`ui/app.js:3563-3567`) — this is an unconditional call, not a conditional guard, so it is enforced regardless of whether TTS happens to be playing at that moment (§15).

**Candidate areas from the task brief that are NOT enforced as stated, with correction:**

* *"Only final recognition results are submitted"* — **not accurate as a blanket claim.** `finish()`/`finalize()` resolves to `getBestTranscript()`, which is built from whatever combination of final and (during grace continuations) interim-derived preview text existed at stop time (§4.4, §5) — an *interim*-only transcript at the moment of a timeout-driven `finish()` can still become the resolved, submitted text if no final result ever arrived. This is recorded as an evidenced correction, not an enforced invariant.
* *"Duplicate submission guards exist"* — **partially enforced**, specifically for the ASR-accepted unmatched-answer path via the 6-second dedup key (§7, §17), not confirmed as a universal guard across every submission branch.
* *"Challenge transcript reveal follows recovery count"* — **partially enforced**: the recovery-count-driven reveal (`>= 2`) is one of two independent triggers; the "?" hint-button click is an equally valid, recovery-count-independent trigger (§14). The claim holds for one of the two paths, not exclusively.

### Intended contracts with known gaps

* **Spoken and typed text should yield identical semantic routing.** Not fully enforced: §10 establishes that several high-priority classifiers (user-initiative overrides, plain-affirmation, some confusion-signal call sites, learner-memory capture, `learner_stated_location`) consume **raw** `answer_text` rather than routing-normalised text — meaning a filler-prefixed or oddly-spaced *spoken* utterance can be classified differently by those specific mechanisms than the same *typed* text would be if a learner typed it without the filler/spacing artefact, since the raw forms differ even though both would normalise to the same routing text.
* **App TTS should never be re-recognised.** Mitigated (cancel-on-open, §15) but not exhaustively guarded against every timing scenario (e.g. a tap during active hardware audio-output-to-microphone echo before the cancel call takes effect) — no test was found specifically reproducing and asserting against this race.
* **Every spoken turn should retain raw recogniser evidence.** Not met by default — raw interim/final segment history is discarded once resolved to a single string (§16); only turns with diagnostics explicitly enabled retain a raw-vs-routing comparison, and even then not the full interim history, only the final resolved values.
* **Names and open-world places should survive normalisation unchanged.** Partially met for places with a known repair mechanism (§11's alias/near-match tables); **not** addressed at all for personal names, which have no dedicated repair or preservation mechanism found in either client or server code.
* **ASR repair should not alter learner intent.** The routing-only scoping of `_repair_contextual_place_question` (never touches the raw transcript, §11) is the strongest evidenced safeguard; the fixed, curated fragment list for `_repair_asr_junk_text` (§11) is a narrower, lower-risk design than a general heuristic, but no test was found proving the fragment list can never match legitimate content.
* **Recovery counters should round-trip.** Client-side Challenge/telemetry counters (§7, §14) are explicitly single-session, in-memory, and never sent as part of `conversation_state` for round-trip purposes; server-side confusion/mirror counters have their own, separately-documented round-trip gaps in `docs/STATE_CONTRACT.md` (SIC-1, SIC-2) — reference that document rather than duplicating its analysis here.
* **Output junk repair should keep Chinese/English/pinyin synchronised.** This is the final-ASR-repair-pass gap already fully documented in `docs/ANSWER_SOURCE_CONTRACT.md` §3.3(4)/§13/§18 — referenced here, not re-analysed, per that document's own scoping.

---

## 20. Extension rules

| Adding/changing a... | Must consider |
|---|---|
| Filler | Visible transcript (should remain unaffected, per §6's established design); submitted text (same); typed parity (typed text has no equivalent filler-stripping-before-submission step, only server-side routing normalisation, §13); false-positive risk against legitimate content starting with the same character (respect the length-guard pattern in both client and server filler strippers, §12); which classification function(s) the new filler should be added to — recovery matching (`normalizeForMatch`, does not strip fillers, §7), general classification (`normalizeConversationalFillers`), or both; tests — add both a unit test and, if claiming behavioural coverage, verify it exercises the real `ui/app.js` function via `_load_app_js_helper.js` rather than a mirrored re-implementation (§12's documented gap); documentation — update §12's inventory table |
| Spoken recovery phrase | Add to `content/recovery_phrases.json` with the correct `use`/`recovery_action`; verify the build step (`tools/build_runtime_artifacts.py`) regenerates the runtime JSON; confirm exact-match behaviour is preserved (do not weaken to substring matching, §7's false-positive rationale); typed parity (a typed version of the same phrase will **not** be intercepted — confirm server-side handling for that case is acceptable, §8); false-positive risk (does the phrase's normalised form collide with a plausible genuine question?); state reset (recovery counters increment regardless of which phrase triggered them, no phrase-specific reset needed); tests — extend `tests/verify_spoken_recovery_exact_match.js` with the new phrase and its plausible false-positive counter-examples; documentation — update §7's table |
| ASR alias (place/travel near-match) | Add to the relevant table (`_TRAVEL_ASR_NEAR_MATCHES`, `_CITY_LOCATION_BRIEF`, etc., §11); server routing only — confirm it does not touch the raw transcript or learner memory unless deliberately intended to; E4 — confirm the alias does not change which engine a question routes to unexpectedly (`docs/ANSWER_SOURCE_CONTRACT.md` §15); tests — add a regression test analogous to `tests/test_contextual_place_asr_repair.py` |
| Place/name repair | Same as above, plus explicit consideration of whether the repair should be routing-only (preferred, per `_repair_contextual_place_question`'s own documented design) or should also affect visible transcript/learner memory (higher risk, requires explicit justification and documentation here) |
| Transcript transformation (client) | Visible transcript effect (state explicitly whether it should propagate to `addTranscriptEntry`); submitted text effect (same); typed parity (does an equivalent server-side transformation already cover typed text, avoiding the need for a client-only duplicate, §6's established pattern of "classification-only, not transcript-mutating"); tests; state reset; documentation — update §6's table |
| Browser recognition setting (e.g. `continuous`, `interimResults`, `maxAlternatives`) | Verify against both existing recognizer configurations (§4.1, §4.2) to avoid unintended divergence between the two; mobile/desktop timing interactions (§4.4, §4.5); false-positive/duplicate-result risk if `maxAlternatives` is introduced where it does not currently exist; tests — extend `tests/test_asr_thinking_grace.py`-style static checks; documentation — update §4 |
| Challenge-mode recovery behaviour | Reveal-timing interaction with the two existing independent triggers (§14); whether hidden-but-stored text behaviour should change (currently always stored/submitted regardless of display, §14); state reset points (§14's table); tests — extend `tests/test_challenge_recovery.py`; documentation — update §14 |
| New request text field | Payload location (root vs. `conversation_state.last_answer`, §9's established convention); precedence when it disagrees with existing fields (document explicitly, following §9's precedent for `submitted_text`/`selected_option_hanzi`); server routing (does `_normalize_zh_for_routing` need to apply to it, §10); answer-source priority and E4 (`docs/ANSWER_SOURCE_CONTRACT.md`); learner memory/session capture (§16); tests; documentation — update §9 |
| Server routing normaliser | Which classifiers should consume the normalised output vs. raw `answer_text` — make this an explicit decision, not an accident, given §10's documented non-uniformity; whether it should also gate the persistent `learner_stated_location`/learner-memory writes (currently raw-text-only, §10); false-positive risk on legitimate content; tests; documentation — update §10 |
| Late output repair | This belongs to `docs/ANSWER_SOURCE_CONTRACT.md`'s scope (§3.3(4)) — any new late-output-repair mechanism must also address whether it recomputes English/pinyin/working-memory fields, per that document's enforced invariant scoping; cross-reference rather than duplicate |

---

## 21. Known risks

* **Browser-vendor dependence.** Only `SpeechRecognition`/`webkitSpeechRecognition` are checked (§4.1); browsers exposing neither global receive the "not available" fallback with no alternative recognition strategy. *Observed.*
* **Mobile permission and timing differences.** Distinct insecure-origin gate, silence timers, and disabled thinking-grace restart mechanism on mobile (§4.4, §4.5) mean the two platforms are not behaviourally identical even before any recognizer-vendor difference is considered. *Observed.*
* **Recogniser event races.** No guard was found preventing a `rec.start()` retry (empty-`onend` path, §4.3) from racing with a nearly-simultaneous natural `onstart`/`onresult` from a just-restarted instance beyond the general `resolved` idempotency flag; this is a structural exposure inferred from the retry design, not a reproduced failure. *Inferred structural exposure.*
* **Duplicate final transcripts.** Mitigated only for the specific unmatched-free-answer path via a 6-second dedup key (§7, §17); not confirmed to cover every submission branch. *Observed gap in scope, not a demonstrated double-submission incident.*
* **TTS feedback into ASR.** Mitigated by cancel-on-open (§15) but not exhaustively guarded against every hardware-echo timing scenario. *Observed partial mitigation; residual risk inferred, not reproduced.*
* **Client/server normalisation divergence.** Two independently-maintained filler-particle definitions (client `_FILLER_CHAR_SET`/`_LEADING_FILLER_PAT` vs. server `_FILLER_PREFIX_RE`, §12) can drift out of sync since neither is generated from the other. *Observed.*
* **Exact-match recovery fragility.** A learner whose phrasing differs even slightly from a phrase-bank entry (and its `alternatives`) will not be intercepted and will instead reach the server as an ordinary or confusion-flagged turn (§7, §8) — a deliberate trade-off against false-positive interception, but still a source of missed intercepts for near-miss phrasing. *Observed design trade-off.*
* **Non-uniform classifier text input.** §10's finding that user-initiative overrides, affirmation detection, and learner-memory/`learner_stated_location` writes consume raw rather than routing-normalised text is a concrete, evidenced source of typed-vs-spoken behavioural divergence for filler-prefixed or oddly-spaced utterances specifically at those mechanisms. *Observed.*
* **Open-world names/places being altered.** The curated ASR-junk-fragment and near-match tables (§11) are narrow by design, but any future broadening risks altering a legitimate open-world place/name that happens to resemble a listed fragment; no test was found guarding against this specific risk category. *Inferred structural exposure.*
* **Raw transcript loss.** Interim/final segment history is not retained past a single listen session except when diagnostics are explicitly enabled, and even then only the resolved values, not the full interim sequence (§16). *Observed.*
* **Hidden Challenge-mode transcript still being stored/submitted.** Confirmed — Challenge Mode is display-only; nothing prevents the "hidden" partner Chinese or the learner's own spoken answer from being fully processed, stored, and (for the learner's answer) submitted exactly as it would be outside Challenge Mode (§14). *Observed — by design, but worth flagging since "hidden" could otherwise be assumed to mean "not retained."*
* **Different text fields feeding different classifiers.** The core finding of §10 — restated here as a risk because any future change to `_normalize_zh_for_routing` or to `answer_text`'s construction must account for the fact that some mechanisms will see the change and others will not, unless the inconsistency is deliberately resolved first.
* **Late Chinese-only output repair.** Fully documented in `docs/ANSWER_SOURCE_CONTRACT.md` §3.3(4)/§18; referenced here as a risk that originates conceptually in this pipeline's "treat recognised speech as potentially noisy" philosophy but is implemented, and risk-tracked, in that document.
* **Test-coverage overstatement risk.** Several test files with ASR-sounding names (`verify_asr_filler.js`, `verify_spoken_recovery_exact_match.js`, most of `test_asr_thinking_grace.py`/`test_asr_interim_latency.py`, most of `test_challenge_recovery.py`) are static-source-verification or mirrored-logic tests, not executions of the real shipped `ui/app.js` functions (§12, and the full test classification in the traceability appendix, §24). *Observed* — a reader citing these files as proof of *behavioural* correctness would be overstating their coverage.

---

## 22. Regression diagnosis guide

* **Microphone button does nothing:** check for `SPEECH_NOT_AVAILABLE`/`SPEECH_INSECURE_ORIGIN` traces first (§4.1); then check `_micListenInFlight` is not stuck `true` from a prior unresolved session.
* **Permission rejected:** confirm the `onerror` branch matched `"not-allowed"`/`"service-not-allowed"` specifically (§4.3) rather than falling into the generic `"error"` catch-all, which would indicate a different underlying issue misclassified as a permission problem.
* **Recogniser stops immediately:** check `onend` firing with no text and whether the 5-retry empty-result loop (§4.3) is exhausting immediately — often indicates the recognizer never actually captured audio (check `onaudiostart`/`onspeechstart` diagnostic events, §4.3).
* **Transcript appears twice:** check `_joinSegments`'s overlap-stripping logic (§5) for a grace-continuation join that failed to detect the overlap, versus a genuine duplicate-final-result scenario (§17) that the `resolved`/`_micListenInFlight` guards did not catch.
* **Interim text submits too early:** confirm whether `finish()` was triggered by a timeout (`wall_clock`/`wall_clock_active`) while only interim (never final) results had arrived — per §19's correction, `getBestTranscript()` can resolve from interim-derived state, so this is expected behaviour under timeout, not necessarily a bug; check whether the timeout value itself needs adjustment instead.
* **Spoken recovery reaches server unexpectedly:** check whether the phrase's normalised form (via `normalizeForMatch`, §7) exactly matches a `content/recovery_phrases.json` entry's `hanzi`/`pinyin`/`alternatives` — a near-miss phrasing will not intercept by design; also confirm the resolved `recovery_action` was one of `"repeat"`/`"slower"`/`"meaning"` and not `"next_turn"` or an unrecognised value that fell through the gate at `ui/app.js:7729`.
* **Genuine learner statement is intercepted as recovery:** check whether the statement happens to exactly equal (after `normalizeForMatch`'s whitespace/register normalisation only) a phrase-bank entry — this is the specific false-positive class exact-matching is designed to avoid, so an occurrence here indicates either an overly generic phrase-bank entry or an `alternatives` list entry that is too broad.
* **Typed question works but spoken equivalent does not:** check §10's classifier-input table for whether the specific mechanism involved consumes raw `answer_text` (unaffected by routing normalisation, but affected by any leading filler/spacing artefact the recognizer introduced) vs. `_last_text_for_counter` (routing-normalised, so filler/spacing differences are already resolved there) — this is the most likely single root cause for this exact symptom given §10's findings.
* **Wrong place/name is extracted:** check which of §11's mechanisms fired (contextual place-question repair, ASR near-match, open-world extraction) and whether the input text to that specific mechanism was raw `answer_text` or `_last_text_for_counter` (§11's table) — a mismatch here (e.g. a near-match table checked against routing-normalised text but built from raw-text examples) is a plausible root cause.
* **Visible transcript differs from semantic routing:** expected and by design once the server applies `_normalize_zh_for_routing` (§10) — the visible transcript (§16) is never updated to reflect routing normalisation. Confirm this is the explanation, not a bug, before investigating further; if the discrepancy is larger than routing normalisation alone would explain, check whether a server-side repair mechanism (§11) silently altered the routing text in a way that should also be reflected to the learner.
* **E4 fires for typed but not spoken input (or vice versa):** given E4 computation itself has no input-mode dependency (`docs/ANSWER_SOURCE_CONTRACT.md` §15), investigate whether the *triggering text* differs between the two modes due to §10's non-uniform classifier-input finding, before assuming an E4-specific defect.
* **App hears its own TTS:** confirm the `speechSynthesis.cancel()` call (§15) actually executed before the mic opened for that specific session (check for a race where the mic tap and a still-in-flight TTS call overlapped in a way the synchronous cancel could not catch).
* **Challenge transcript reveals too soon or never reveals:** check both independent triggers separately (§14) — recovery-count `>= 2` and the first "?" hint click — a "too soon" report may indicate the hint-button trigger fired when only the recovery-count trigger was expected, and vice versa for "never reveals."
* **Transcript disappears after server error:** not determined by this investigation (§17); treat as an open question requiring separate investigation of `runTurn()`'s own error-handling path, which was out of this document's traced scope.
* **Session review contains different text from the UI:** check §16's table for which of the several stored forms (on-screen transcript, `conversation_state.last_answer`, diagnostics `_diag_cap`, learner memory) is being compared, and against which — several are expected to differ from each other by design (raw vs. routing-normalised), and only a genuine mismatch *within* a single stored form's own definition indicates a bug.
* **Junk text remains in learner or persona output:** for persona (partner-side) output, this is `docs/ANSWER_SOURCE_CONTRACT.md`'s scope (§3.3(4)) — check whether the final ASR-junk repair pass ran and check its documented English/pinyin non-recomputation gap; for learner-side stored text, check whether the specific storage location (§16) is one that receives `_repair_asr_junk_text` treatment (location-tail/memory-slot cleanup, §11) or one that does not (raw transcript display, §16).

---

## 23. Related documents

* `docs/CONVERSATION_ARCHITECTURE.md` — overall turn lifecycle, frame selection, E4 end-to-end transport contract.
* `docs/STATE_CONTRACT.md` — authoritative `conversation_state`/`state_update` field schema, including the recovery/confusion counters cross-referenced in §18-§19 of this document.
* `docs/ANSWER_SOURCE_CONTRACT.md` — answer-source priority chain, deduplication, and the final ASR-junk output-repair pass referenced in §11/§19 of this document.
* Repository-root `AI_CONTEXT.md` — orientation map for this repository.
* `.cursor/rules/mandarinos-architecture.mdc`, `.cursor/rules/mandarinos-ui-objects.mdc` — standing architectural and UI-object rules applicable to any future change touching the mechanisms this document describes.

No existing UI/mobile deployment documentation file was found in this repository beyond the code-level mobile-behaviour evidence already cited in §4.5; no such document is listed here since none exists to link.

---

## 24. Traceability appendix

| ASR area | Client producer | Client transformation | Server consumer/repair | Stored form | Representative tests |
|---|---|---|---|---|---|
| Browser recognition lifecycle (Chinese mic) | `listenForResponse()` (`ui/app.js:3545-4002`) | Interim/final assembly, grace-restart segment join (§4, §5) | n/a (client-only until resolved) | On-screen transcript, `last_answer.submitted_text` once submitted | `tests/test_asr_thinking_grace.py` (static), `tests/test_asr_interim_latency.py` (static) |
| Browser recognition lifecycle (English mic) | `ui/app.js:9343-9404` | None beyond final-result trim | n/a — feeds `#engInput`, not conversation routing | `#engInput` value only | *(no dedicated test file identified)* |
| Client-intercepted spoken recovery | `matchSpokenRecoveryPhraseExact()` (`ui/app.js:2331-2350`) | Whitespace/register normalisation for exact-match comparison only (§7) | Not reached — no server request | On-screen transcript only | `tests/verify_spoken_recovery_exact_match.js` (hybrid — mirrored matcher + static wiring) |
| Filler classification | `_FILLER_CHAR_SET`, `normalizeConversationalFillers()`, `isIncompleteLearnerUtterance()` (§6, §12) | Classification-only, never mutates visible/submitted text | `_normalize_zh_for_routing()`'s independent filler-strip (§10, §12) | Neither client nor server filler-stripped form is separately stored — only raw and routing-normalised forms exist (§16) | `tests/verify_asr_filler.js` (hybrid — mirrored logic + static wiring), `tests/test_asr_filler_suppression.py` (hybrid — static + subprocess) |
| Challenge Mode reveal/hide | `_challenge` object, `_challengeRevealText()` (§14) | Display-only DOM/class toggles | No server-side Challenge Mode field exists (§9) | Not stored — client session state only | `tests/test_challenge_recovery.py` (mostly static), `tests/test_turbulence_signal.py` (hybrid) |
| TTS/mic coordination | `speechSynthesis.cancel()` in `listenForResponse()` (§15) | n/a | n/a | n/a | *(no dedicated test file identified for this specific interaction)* |
| Request construction / field precedence | `conversation_state.last_answer` assembly (client-side, not fully traced as part of this ASR-scoped investigation beyond confirming the field names §9 documents) | n/a | `_answer_text_from_last_answer()`, `_last_user_text` (§9, `scripts/ui_server.py:2620-2627, 10434-10436`) | `conversation_state.last_answer` as sent | *(covered indirectly by any test constructing a payload, e.g. `tests/test_spoken_chinese_routing.py`)* |
| Server routing normalisation | n/a | n/a | `_normalize_zh_for_routing()` (§10, `scripts/ui_server.py:3753-3766`) | `routing_answer_text`/`_last_text_for_counter`, server-local only | `tests/test_spoken_chinese_routing.py` (behavioural) |
| Server-side ASR/place repair | n/a | n/a | `_repair_contextual_place_question()`, `_extract_open_world_location()`, ASR near-match tables (§11) | Routing text (not persisted) or `learner_stated_location`/memory slots (persisted) | `tests/test_contextual_place_asr_repair.py` (behavioural), `tests/test_open_world_food_and_location_fixes.py` (behavioural) |
| Spoken-question routing regressions | n/a | n/a | Direct-persona/mirror routing on spaced/malformed ASR-shaped input (§13) | n/a | `tests/test_spoken_question_routing_regression.py` (behavioural) |
| Late output repair (Chinese-only) | n/a | n/a | `_repair_asr_junk_text()` final pass (§11, §19; full analysis in `docs/ANSWER_SOURCE_CONTRACT.md` §3.3(4)) | `response["counter_reply"]`/`["frame_text"]` | *(see `docs/ANSWER_SOURCE_CONTRACT.md`'s own traceability appendix)* |
| Diagnostics / ASR trace reporting | Client emits trace events (various `emitUITrace`/`AsrDiag` calls throughout §4) | n/a | `_diag_cap` capture (§16, `scripts/ui_server.py:9236-9275`), offline joining via `scripts/report_asr_traces.py` | Diagnostics JSONL records, when enabled | `tests/test_report_asr_traces.py` (behavioural) |
| Session review export | n/a | n/a | n/a | Export batch text (§16) | `tests/test_export_session_review_prompt.py` (behavioural, tangential to ASR) |

**Baseline commit:** `3be0315b2c9f7316b03ac2183a887f602ae9a297`
**Baseline tag:** `architecture-baseline-2026-07-12-r2`
**Documentation branch:** `docs/architecture-v1`
**Document status:** Draft v1
**Last verified date:** 2026-07-12
