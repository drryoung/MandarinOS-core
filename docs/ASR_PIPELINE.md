# MandarinOS ASR Pipeline

**Baseline commit:** `3be0315b2c9f7316b03ac2183a887f602ae9a297`
**Baseline tag:** `architecture-baseline-2026-07-12-r2`
**Source documentation branch:** `docs/architecture-v1`
**Approved contracts referenced:** `docs/CONVERSATION_ARCHITECTURE.md`, `docs/STATE_CONTRACT.md`, `docs/ANSWER_SOURCE_CONTRACT.md` (approval commit `63cb80a809d4377e936360b59a09af759f19a81f`)
**Document status:** Candidate v1 — R2 final review
**Last verified date:** 2026-07-12

All line-number citations refer to `ui/app.js`, `scripts/ui_server.py`, `ui/index.html`, or `ui/styles.css` at the baseline commit above unless another file is named. No local filesystem path appears in this document.

---

## 1. Purpose and scope

This document covers the complete R2 path from microphone input or production typed learner text to the normalised text consumed by conversation routing and answer generation. It begins at the browser's speech-recognition API (or the translate-assisted typed-input control) and ends at the point where text becomes available to the mechanisms documented in `docs/ANSWER_SOURCE_CONTRACT.md` — the routing/classification variables `answer_text`, `routing_answer_text`, `_last_text_for_counter`, and `_routing_last_answer`. It also covers the reverse direction where relevant: which version of the text is displayed to the learner, stored in session capture, and subjected to late output-side repair.

**Speech recognition and conversation reasoning are separate layers.** Everything in §§4–9 of this document (browser recognition, transcript assembly, client-side normalisation, client-intercepted recovery, request construction) runs entirely in the browser and produces, at most, a single JSON payload sent to `/api/run_turn`. Everything from §10 onward runs on the server and is agnostic to whether the text originated from speech or typing — the server has no reliable signal that a given turn was spoken (§9, §17).

**Four distinct mechanisms exist, not two.** This document does not use "spoken" and "typed" as a simple binary. It distinguishes:

1. The **Chinese answer microphone** — the `zh-CN` `SpeechRecognition` instance inside `listenForResponse()` (`ui/app.js:3545-4002`), which submits a conversation turn.
2. **Production translate-assisted typed input** — the learner types English into `#engInput`, a translation/lookup step produces Chinese, and the "Use" button (`ui/app.js:9414-9430`) submits that Chinese text as a conversation turn via the same `runTurn()` entry point spoken answers use. **This, not a synthetic payload, is the actual production typed UI path.**
3. **Auxiliary `en-US` recognition** — a second, independent `SpeechRecognition` instance (`ui/app.js:9343-9404`) that only populates `#engInput`; confirmed it never itself submits a conversation turn (no `runTurn`/`fetch` call exists in its `onresult` handler, `ui/app.js:9394-9400`).
4. **Synthetic `/api/run_turn` payload construction used by tests** — e.g. `tests/test_spoken_chinese_routing.py`, `tests/test_spoken_question_routing_regression.py` constructing a `conversation_state.last_answer` payload directly against the server, bypassing every client-side mechanism in §§4-9 entirely. **This is a test/reference harness, not a production input mode**, and this document does not call it one.

**Direct server payload construction is the test/reference path for conversation semantics; translate-assisted typing is the actual production typed UI path; both converge with submitted speech only once the same `conversation_state.last_answer` text fields reach the server.** Prior drafts of this document described "typed input" as a single semantic reference path without this distinction — that framing has been corrected throughout §§1-3, §9, §13, §19, and the traceability appendix (§24).

This document describes **R2 production behaviour as read from the source**, not a proposed ideal. Where behaviour is incomplete, inconsistent, or evidenced as a gap, that is recorded in place (§§4–18) and summarised in §21, not smoothed over.

**Responsibilities that remain in other documents:**

* **`docs/CONVERSATION_ARCHITECTURE.md`** — overall turn lifecycle, frame selection, E4 transport contract, engine/ladder mechanics once text has already reached the server as `answer_text`.
* **`docs/STATE_CONTRACT.md`** — authoritative schema and consumption status of every `conversation_state`/`state_update` field, including counters this document only cross-references (§18).
* **`docs/ANSWER_SOURCE_CONTRACT.md`** — how `counter_reply`/`counter_reply_en`/`counter_reply_pinyin` are produced once routing text is available, including the final ASR-junk output-repair pass, which this document references (§11) rather than re-analyses.

TTS (text-to-speech) synthesis and provider architecture are **out of scope** except where they directly affect microphone state, recognition timing, or recovery interaction (§15).

---

## 2. Input modes and trust boundaries

Four mechanisms exist for getting learner text into the system, plus one non-submitting recovery-interaction mode:

* **Mechanism 1 — Chinese answer microphone (production, submits a turn).** `listenForResponse()` (`ui/app.js:3545-4002`), triggered by `#tryRespondingBtn` (`ui/app.js:8085-8099`). `zh-CN`, `interimResults=true`, `continuous=false`.
* **Mechanism 2 — Translate-assisted typed input (production, submits a turn).** Learner types English into `#engInput`; `doTranslate()` produces a Chinese candidate rendered into `#engTranslated`; the "Use" button submits it (`ui/app.js:9414-9430`). Confirmed identical downstream entry point to speech: `runTurn(true, { last_turn_was_answer: true })` (`ui/app.js:9429`), the same call spoken free-answers use (`ui/app.js:7885`).
* **Mechanism 3 — Auxiliary English recognition (production, does not submit a turn).** A second, independent `SpeechRecognition` instance (`ui/app.js:9343-9404`), `en-US`, `interimResults=false`, `maxAlternatives=1`, `continuous=false`. Its sole effect is `engInput.value = transcript; doTranslate();` (`ui/app.js:9396-9399`) — it feeds Mechanism 2, it does not compete with or replace it.
* **Mechanism 4 — Synthetic test payloads (test/reference harness, not a production input mode).** Constructed directly against `/api/run_turn` or server-internal functions by the test suite. No browser code runs for this mechanism at all.
* **Client-intercepted spoken recovery (non-submitting interaction, Mechanism 1 only).** Certain recognised utterances from Mechanism 1 are handled entirely client-side with no `/api/run_turn` request (§7). Mechanism 2 has no equivalent interception step (§8).

| Input mechanism | Producer | Client transformations | Server fields sent | Visible transcript | Semantic routing source |
|---|---|---|---|---|---|
| 1. Chinese answer mic (submitted) | Browser `SpeechRecognition` (`zh-CN`) via `listenForResponse()` | Interim/final assembly (§5); none of the classification-only transformations in §6 mutate the submitted string itself | `conversation_state.last_answer.submitted_text`, populated with the resolved transcript (`saidTrimmed`) | `saidTrimmed` verbatim, via `addTranscriptEntry` | Server-side `_last_text_for_counter` pipeline (§10) |
| 1a. Chinese answer mic (client-intercepted recovery) | Same recognizer | Interim/final assembly (§5), then exact-match recovery detection (§7) | **None — no request is sent** | `saidTrimmed` is still added to the visible transcript (`ui/app.js:7730`) | Not applicable — no server turn occurs |
| 2. Translate-assisted typed input (production) | Learner keystrokes into `#engInput`, then translation/lookup, then Use-button tap | None from the ASR stack (§§4-6 do not run for this mechanism at all — there is no recognizer session); no client-side filler/recovery classification runs on this path either, since those mechanisms are wired into the Chinese-mic listen loop, not the Use-button handler | `conversation_state.last_answer.submitted_text` = the Chinese candidate string (`ui/app.js:9425`) | The Chinese candidate string, added via `addTranscriptEntry` **before** the request (`ui/app.js:9420-9421`) | Same server-side `_last_text_for_counter` pipeline as Mechanism 1, once the text reaches the server (§10) |
| 3. Auxiliary English recognition | Browser `SpeechRecognition` (`en-US`) | None beyond the recognizer's own final-result trim (`ui/app.js:9396`) | Not applicable — feeds `#engInput` for Mechanism 2's translation step; does not itself construct a `/api/run_turn` payload | The recognized text is placed into the editable `#engInput` field, which the learner can revise before it becomes a Mechanism 2 submission | Not applicable on its own — only reaches routing indirectly, after Mechanism 2 submits whatever text results from translation |
| 4. Synthetic test payload | Test code | Not applicable — no client code runs | Whatever fields the test constructs directly | Not applicable — no UI is exercised | Server-side pipeline (§10), identical code path to 1 and 2 once the payload is received |

Trust-boundary summary: **raw recogniser output** exists only transiently inside `listenForResponse`'s closure (`finalTranscript`/`interimTranscript`, `ui/app.js:3582-3583`) and is not separately preserved once `finish()`/`finalize()` resolve to a single string (§16 — this is where raw evidence is lost, except when diagnostics/ASR-trace capture is separately enabled, §16). **Displayed transcript**, **submitted text**, and **routing text** are three distinct strings from the point the server receives the payload onward (§10); they are frequently, but not always, identical. Mechanism 4 has no displayed transcript or client-side text distinction at all — it is a server-only construct.

---

## 3. End-to-end data flow

**Mechanism 1 — Chinese answer mic (non-intercepted case):**

```text
microphone
→ browser SpeechRecognition (zh-CN, interimResults=true, continuous=false)
→ onresult events → absorbResults() → interim/final transcript assembly (§5)
→ recognition ends (onend) → finish()/finalize() → resolved transcript ("saidTrimmed")
→ filler/recovery classification: matchSpokenRecoveryPhraseExact() against runtime phrase list (§7)
   ├─ MATCH on repeat/slower/meaning action → client-intercepted recovery: TTS replay, no server request (§7/§8)
   └─ NO MATCH (or "next_turn"/unrecognised action) → continue below
→ option-matching / free-answer classification (isIncompleteLearnerUtterance, classifyUnmatchedFreeAnswerDecision, §12)
   ├─ REJECTED (e.g. filler-only) → no server request; local recovery UI shown (§12)
   └─ ACCEPTED → continue below
→ submitted payload: conversation_state.last_answer.submitted_text (+ selected_option_hanzi if an option was matched)
→ server: _normalize_zh_for_routing() → routing_answer_text / _last_text_for_counter (§10)
→ server-side ASR repair (contextual place repair, open-world location extraction, ASR near-match) (§11)
→ semantic classifiers (_is_rr, _is_meaning, _is_example, _is_confusion_signal, direct-persona/mirror/E3) — not all fed the same text (§10)
→ answer source + frame selection (docs/ANSWER_SOURCE_CONTRACT.md, docs/CONVERSATION_ARCHITECTURE.md)
→ response (counter_reply, frame_text, state_update)
→ visible learner transcript (addTranscriptEntry, already added at "saidTrimmed" step above)
→ session-related capture, gated/limited as documented in §16
```

**Mechanism 2 — Translate-assisted typed input (production):**

```text
learner types English into #engInput
→ doTranslate() produces a Chinese candidate string, rendered into #engTranslated
→ learner taps "Use" (ui/app.js:9414-9430)
→ addTranscriptEntry("user", zh, ...) — transcript updated BEFORE the request
→ window._lastAnswer = { frame_id, submitted_text: zh }
→ runTurn(true, { last_turn_was_answer: true }) — same submission entry point as Mechanism 1
→ conversation_state.last_answer.submitted_text = zh
→ server: identical pipeline from _normalize_zh_for_routing() onward (§10)
→ response
```

**Mechanism 4 — Synthetic test payload:**

```text
test code constructs conversation_state.last_answer directly
→ POSTed to /api/run_turn, or the relevant server function called directly in-process
→ server: identical pipeline from _answer_text_from_last_answer() onward (§10)
→ response inspected by test assertions
```

**Where the paths converge:** Mechanisms 1, 2, and 4 all produce (or supply) the same `conversation_state.last_answer` shape and are processed by an identical server-side pipeline from `_answer_text_from_last_answer()` (`scripts/ui_server.py:2620-2627`) onward — the server has no code path that branches on whether text came from speech, translate-assisted typing, or a test harness (confirmed by the absence of any `input_mode`/`is_spoken`/confidence field sent in the request payload, §9). **Where the paths remain different:** (a) the entire browser-recognition/transcript-assembly stack (§4-§5) has no equivalent in Mechanism 2 or 4 at all; (b) client-intercepted recovery (§7) exists only for Mechanism 1 — Mechanism 2 has no interception step, and a translate-assisted "再说一遍" submission is handled (if at all) purely by server-side recovery detection (§8); (c) filler-only or acoustically-noisy utterances are a Mechanism-1-only failure mode (§12); (d) Challenge Mode's transcript-hiding display logic applies regardless of which mechanism supplied the learner's own answer, but its hiding of the **partner's** turn is unconditional and mechanism-independent (§14).

---

## 4. Browser recognition lifecycle

Two independent `SpeechRecognition`/`webkitSpeechRecognition` instances exist (Mechanisms 1 and 3). **No claim of cross-browser support beyond what the code checks is made** — the only feature-detection performed is `window.SpeechRecognition || window.webkitSpeechRecognition` (`ui/app.js:3548`, `9345`); Firefox, which historically lacks both, is not handled specially and falls into the "not available" branch below.

### 4.1 Chinese answer mic (`listenForResponse`, `ui/app.js:3545-4002`)

* **API selection:** `ui/app.js:3548`.
* **Support detection:** if neither global exists, emits a `SPEECH_NOT_AVAILABLE` trace, shows a "Speech recognition is not available in this browser" notice, and resolves the returned promise with `{ transcript: "", matchedOption: null, asr_confidence: null, finishReason: "not_available" }` (`ui/app.js:3549-3553`) — no fallback to Mechanism 2 is triggered automatically; the caller is responsible for that (§17).
* **Insecure-origin check:** on mobile layout (`_isMobileLayout()`), if `location.protocol === "http:"` and the host is not `localhost`/`127.0.0.1`, emits `SPEECH_INSECURE_ORIGIN`, shows a message directing the learner to HTTPS/Safari, and resolves with `finishReason: "insecure_origin"` (`ui/app.js:3555-3561`). This is a custom protocol string check in application JavaScript, **not** `window.isSecureContext`, and **not** influenced by any web app manifest or service worker (§4.6 — neither exists in this repository).
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
  | `grace_error` / `permission_denied` | error during a grace-restart recognizer (`ui/app.js:3755-3763`) |
  | `silence_filler_extended` / `silence` | post-speech silence timers, the former after a one-time filler-triggered extension (`ui/app.js:3888-3900`, §12) |
  | `onend` | recognizer ended and no further restart applies (`ui/app.js:3918, 3937`) |
  | `start_error` | `rec.start()` itself threw (`ui/app.js:3990-3991`) |
  | `error` / `permission_denied` | `onerror` (see below) |

* **Explicit user-initiated stop:** **not found** for the Chinese mic — there is no toggle-to-stop control on `#tryRespondingBtn`; the only way to end a listen session early is timeout/silence/error.

### 4.2 Auxiliary English recognition (`ui/app.js:9343-9404`, Mechanism 3)

* **API selection:** `ui/app.js:9345`.
* **Support detection:** if unsupported, the mic button is disabled and its title set to "Speech recognition not supported in this browser" (`ui/app.js:9346-9349`) — no insecure-origin check exists for this recognizer.
* **Configuration:** `lang = "en-US"`, `interimResults = false`, `maxAlternatives = 1`, `continuous = false` (`ui/app.js:9366-9369`).
* **Start/stop:** click starts (`ui/app.js:9401`); a second click while `_engRecording` is true calls `_engRec.stop()` and returns (`ui/app.js:9361-9363`) — this recognizer **does** have an explicit user-toggle stop, unlike the Chinese mic.

### 4.3 Event handlers

**Chinese mic:**

* `onstart` (`ui/app.js:3940-3945`): sets `micStarted = true`, logs performance/diagnostic events, `_setListenState("listening")`.
* `onresult` (`ui/app.js:3904`): delegates entirely to `absorbResults(e)` (§5).
* `onend` (`ui/app.js:3906-3938`): if already `resolved`, returns. If text is present: on desktop (and under the segment cap) enters the thinking-grace restart (§4.4); on mobile, or once the segment cap is reached, calls `finish("onend")` immediately. If no text is present: retries `rec.start()` on the same instance up to 5 times if time remains (`onendRetryCount < 5 && elapsed < timeoutMs - 500`, `ui/app.js:3922-3932`), otherwise `finish("onend")`.
* `onerror` — verbatim:

  ```3953:3962:ui/app.js
    rec.onerror = (e) => {
      console.log(`[ASR] onerror: ${e.error}`);
      if (e.error === "aborted") return;    // expected when finish() calls rec.abort()
      if (e.error === "no-speech") return;  // let silence/onend handle the empty-speech case
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        finish("permission_denied");
        return;
      }
      finish("error");
    };
  ```

  It explicitly reads `e.error`, classifies `"aborted"`/`"no-speech"` as no-op, `"not-allowed"`/`"service-not-allowed"` as `permission_denied` (which produces the user-visible message "Microphone access denied — allow mic in browser settings" via `_showListenNotice`, `ui/app.js:7561-7575`), and every other error string as the generic `"error"` reason (which produces "Speech recognition error — try again"). The grace-restart recognizer's `onerror` (`ui/app.js:3755-3763`) applies the identical classification.
* Diagnostic-only handlers with no control-flow effect: `onaudiostart`, `onspeechstart`, `onspeechend`, `onaudioend` (`ui/app.js:3948-3951`).

**Auxiliary English recognizer — verbatim, and explicitly NOT identical to the Chinese mic:**

```9365:9400:ui/app.js
        _engRec = new SpeechRec();
        _engRec.lang = "en-US";
        _engRec.interimResults = false;
        _engRec.maxAlternatives = 1;
        _engRec.continuous = false;

        _engRec.onstart = () => {
          _engRecording = true;
          window._micListenArmedAt = Date.now();
          document.body.classList.add("is-listening");
          engMicBtn.classList.add("recording");
          engMicBtn.title = "Listening… (click to stop)";
        };
        _engRec.onend = () => {
          _engRecording = false;
          engMicBtn.classList.remove("recording");
          engMicBtn.title = "Speak in English";
          _engRec = null;
          const st = document.getElementById("listenStatus")?.dataset?.state;
          if (!st || st === "idle") document.body.classList.remove("is-listening");
        };
        _engRec.onerror = () => {
          _engRecording = false;
          engMicBtn.classList.remove("recording");
          engMicBtn.title = "Speak in English";
          _engRec = null;
          const st = document.getElementById("listenStatus")?.dataset?.state;
          if (!st || st === "idle") document.body.classList.remove("is-listening");
        };
        _engRec.onresult = (ev) => {
          const transcript = (ev.results[0]?.[0]?.transcript || "").trim();
          if (transcript) {
            engInput.value = transcript;
            doTranslate();
          }
        };
```

**Definitive comparison — permission-denial handling is DIFFERENT, not identical, between the two recognizers:**

| Aspect | Chinese mic (`rec`/`nextRec`) | Auxiliary English recognizer (`_engRec`) |
|---|---|---|
| `onerror` reads the error event's `error` property | **Yes** — `(e) => { ...e.error... }` | **No** — `onerror = () => { ... }` takes no parameter at all |
| Dedicated `"not-allowed"`/`"service-not-allowed"` branch | **Yes** → `finish("permission_denied")` | **No** — no branching of any kind |
| User-visible error message | **Yes** — `_showListenNotice("Microphone access denied — allow mic in browser settings", ...)` | **No** — `onerror` and `onend` run byte-for-byte identical cleanup (button/title/flag reset), with no message shown to the learner in either case |
| Distinguishes error causes at all | **Yes** (aborted / no-speech / permission / generic) | **No** — every error, including permission denial, is treated as generic cleanup |

**Conclusion for this recognizer, stated precisely:** the auxiliary English recognizer performs generic cleanup only on error; permission denial is not specially classified or messaged by application code for this recognizer. A prior draft of this document's §17 stated that "permission errors [are] handled identically for both recognizers" — that claim is **incorrect** and has been removed; this section and §17 now state the distinction directly.

### 4.4 Automatic restarts (desktop "thinking grace")

Constants: `ASR_THINKING_GRACE_MS = 1800`, `ASR_MAX_SEGMENTS = 4` (`ui/app.js:3435-3437`); `GRACE_MAX_RESTARTS = 8` (`ui/app.js:3702`).

When `onend` fires with text present, on desktop, under the segment cap, `_startThinkingGrace()` (`ui/app.js:3704-3810`) creates a **new** recognizer instance (`nextRec = new SpeechRecognition()`, same `zh-CN`/`interimResults=true`/`continuous=false` configuration, `ui/app.js:3731-3738`), sets `activeRec = nextRec`, and starts it, giving the learner 1800ms to continue speaking. If `nextRec` also ends with no text and time remains, the grace period restarts (up to 8 times, `ui/app.js:3783-3793`); if the deadline expires with no further speech, `finish("thinking_grace_expired")` runs. This mechanism is **disabled on mobile** — mobile `onend` with text goes straight to `finish("onend")` (`ui/app.js:3913-3918`), and the trace payload explicitly records `thinking_grace_ms: 0` for mobile sessions (`ui/app.js:3986`).

### 4.5 Mobile/iPhone differences represented in code

There is no literal `"iPhone"` string in `ui/app.js`; mobile-specific behaviour is gated on `_isMobileLayout()` (`matchMedia("(max-width: 768px)")`, `ui/app.js:10337-10338`) and comments referencing iOS. Concretely: the insecure-origin HTTPS gate (§4.1) only fires on mobile; pre-speech silence timers differ (`SPEECH_PRE_SPEECH_SILENCE_MS_MOBILE = 4000` vs. a desktop value of 4500, `ui/app.js:3425-3426, 3608-3610`); the thinking-grace restart mechanism is desktop-only (§4.4); `beginListening()` runs synchronously rather than after a 380ms delay, to preserve the iOS touch-gesture-to-`start()` chain (`ui/app.js:3995-3997`, comment at `7518`); and the mic button binds `touchstart` (not `click`) on mobile, with `click` debounced 600ms after a touch to avoid a double-fire (`ui/app.js:8087-8099`).

### 4.6 Manifest and service worker

**This repository has no installable PWA web app manifest and no service worker.** Specific findings:

* `ui/index.html` has no `<link rel="manifest">` tag, and no `<meta>` tags related to Permissions-Policy, microphone, or secure context — only `charset` and `viewport` metas exist (`ui/index.html:4-5`).
* The repository-root `manifest.json` and `content_manifest.json` are **content/build inventory manifests** (file lists, `git_commit`, content-pack descriptors), not Web App Manifests — neither contains a `permissions` field or any microphone-related declaration.
* No `sw.js` or `.webmanifest` file exists anywhere in the repository. No `navigator.serviceWorker.register(...)` call exists in `ui/app.js` or `ui/index.html`. No `self.addEventListener("fetch"/"install")` exists anywhere.
* Static files, including `ui/app.js`, are served by `ui_server.py`'s file handler with no `Cache-Control` header set (`scripts/ui_server.py:12558-12561`), and the script tag has no cache-busting query string (`<script type="module" src="/app.js"></script>`, `ui/index.html:662`) — since there is no service worker, this is a plain HTTP-caching consideration only, not an ASR-specific staleness risk this document tracks further.
* **Secure-context enforcement is entirely client-JavaScript-based and browser-enforced**, not manifest- or service-worker-influenced: the only relevant check is the mobile HTTP/non-localhost gate in `listenForResponse()` (§4.1). No manifest field or service-worker registration condition affects whether the recognizer is permitted to run.
* **No PWA install state exists to alter microphone behaviour.** With no manifest enabling `display: standalone` (or similar) and no code branching on `display-mode: standalone`/`navigator.standalone`, running this app as an installed PWA (which is not currently possible without a manifest) would not change microphone behaviour in any way visible in this codebase — behaviour is governed solely by standard browser secure-context rules and the JS check above, identically whether the page is loaded as a normal tab or hypothetically installed.

---

## 5. Interim and final transcript assembly

**Variables** (local to `listenForResponse`'s closure): `finalTranscript`, `interimTranscript` (`ui/app.js:3582-3583`); mirrored to `window._asrInterimPreview`/`window._asrInterimIsFinal` for UI display (`ui/app.js:3450-3463`).

**`absorbResults(e)`** (`ui/app.js:3812-3880`) runs on every `onresult` event:

1. Scans `e.results` from `e.resultIndex` onward, splitting each segment into `chunkFinal`/`chunkInterim` accumulators (diagnostic use only) and separately scans **all** of `e.results` to find `latestAny` (last non-empty transcript of any kind) and `latestFinal` (last non-empty *final* transcript) (`ui/app.js:3816-3833`).
2. If `latestFinal` is present: during a grace continuation, it is **appended** to the existing `finalTranscript` via `_joinSegments()` (see below) and `segmentCount` increments (`ui/app.js:3835-3839`); otherwise it **replaces** `finalTranscript` outright and `segmentCount` resets to 1 (`ui/app.js:3840-3842`). `interimTranscript` is cleared either way (`ui/app.js:3844`).
3. Else if `latestAny` (interim only) is present, `interimTranscript` is set to it directly, or, during a grace continuation, to the join of the existing final text with the new interim text (`ui/app.js:3847-3849`) — this is a preview-only concatenation, not committed to `finalTranscript`.

### `_joinSegments(base, addition)` — exact behaviour

Verbatim definition:

```3635:3649:ui/app.js
    function _joinSegments(base, addition) {
      const b = (base || "").trim();
      const a = (addition || "").trim();
      if (!a) return b;
      if (!b) return a;
      // Check if 'a' starts with a suffix of 'b' (browser sometimes repeats the last few chars).
      // Try progressively shorter overlap lengths (max 8 chars).
      const maxOverlap = Math.min(8, b.length, a.length);
      for (let ol = maxOverlap; ol >= 1; ol--) {
        if (b.endsWith(a.slice(0, ol)) && a.slice(0, ol) === b.slice(-ol)) {
          return b + a.slice(ol);
        }
      }
      return b + a;
    }
```

* **What `base` represents:** the formal first parameter, assigned internally to `b`; at both call sites this is `finalTranscript` — the **existing, previously accumulated** transcript.
* **What `addition` represents:** the formal second parameter, assigned internally to `a`; at both call sites this is the **new, incoming** segment (`latestFinal` or `latestAny`) from the current `onresult` event.
* **Overlap tested:** a **prefix of `a` (new/incoming)** is compared against a **suffix of `b` (existing/previous)** — the comment at `ui/app.js:3640-3641` states this directly ("Check if `a` starts with a suffix of `b`"). The loop tries overlap lengths from `min(8, len(b), len(a))` down to `1`.
* **Return when overlap found:** `return b + a.slice(ol);` (`ui/app.js:3645`) — the existing transcript, plus only the non-overlapping remainder of the new segment.
* **Return when no overlap found:** `return b + a;` (`ui/app.js:3648`) — existing transcript followed directly by the full new segment.
* **Early exits:** `if (!a) return b;` (`ui/app.js:3638`); `if (!b) return a;` (`ui/app.js:3639`).
* **Space or punctuation insertion:** **never** — both return paths are bare string concatenation. No separator of any kind is inserted between the two pieces, in either the overlap or no-overlap case.

**Resolution of the "appended" vs. "`b + a`" apparent contradiction:** there is no contradiction once parameter identity is fixed precisely: `b` is always the *existing* transcript and `a` is always the *new* segment, and the return expression `b + a[...]` places the existing text first and the new text second — this **is** "the new segment appended to the existing transcript." A prior draft of this document used `a`/`b` to mean the opposite roles in prose while quoting the correct code, creating an apparent inconsistency; this section now names the parameters exactly as the source does (`base`→`b`, `addition`→`a`) throughout.

**Call sites** (both inside `absorbResults()`, both passing `finalTranscript` as `base`):

```3834:3843:ui/app.js
      if (latestFinal) {
        if (isGraceContinuation && finalTranscript) {
          // Append to accumulated answer; strip any repeated overlap at the join.
          finalTranscript = _joinSegments(finalTranscript, latestFinal);
          segmentCount++;
          console.log(`[ASR] grace segment joined (${segmentCount}): "${finalTranscript}"`);
        } else {
          if (!isGraceContinuation) segmentCount = 1;
          finalTranscript = latestFinal;
        }
```

```3845:3849:ui/app.js
      } else if (latestAny) {
        // Show interim continuation appended to the already-confirmed final.
        interimTranscript = isGraceContinuation
          ? _joinSegments(finalTranscript, latestAny)
          : latestAny;
      }
```

### Worked example

Given a first final segment `finalTranscript = "今天天气很好"` and a second, continuation final segment `latestFinal = "很好啊"` (the recognizer having re-captured the trailing "很好" before continuing):

* Inside the function, `b = "今天天气很好"`, `a = "很好啊"`, `maxOverlap = min(8, 6, 3) = 3`.
* At `ol = 2`: `b.slice(-2) === "很好"` and `a.slice(0, 2) === "很好"` → match found.
* Return: `b + a.slice(2)` = `"今天天气很好"` + `"啊"` = **`"今天天气很好啊"`**, byte-for-byte, with no inserted separator.

**Retention of previous final segments:** only during grace continuations (§4.4) — a non-grace final result replaces, rather than appends to, `finalTranscript`.

**Transcript submission eligibility:** `listenForResponse` resolves via `finish()`→`finalize()` (`ui/app.js:3667-3686`), which sets `finalTranscript = getBestTranscript()` (`getBestTranscript()` returns `(finalTranscript || interimTranscript || "").trim()`, `ui/app.js:3617-3619`) and clears `interimTranscript`; there is no separate "submit" action — the caller (`_runChineseMicListen`, `ui/app.js:7547+`) receives the resolved transcript and decides what to do with it (§12 for the filler-only rejection path specifically). **Empty-transcript handling:** `_runChineseMicListen` trims the resolved transcript into `saidTrimmed`; if empty, it shows a notice (message varies by `finishReason`) and returns without any server submission (`ui/app.js:7559-7589`). **Punctuation-only transcript rejection:** **not found** as an explicit distinct check at this stage — the closest related mechanism is `isIncompleteLearnerUtterance`/`_isSufficientLinguisticSignal` (§12), which operates on filler-only content, not punctuation per se.

**Learner editing before submission:** the Chinese-mic transcript is shown read-only via `_setAsrInterimPreview` into `#listenStatus` (`ui/app.js:3455-3464`) — **there is no editable field for it**; the learner cannot correct a misrecognised Chinese answer before it is submitted or intercepted. The auxiliary English-recognizer transcript, by contrast, is written into the editable `#engInput` field (`ui/app.js:9397`), which the learner can revise before it feeds Mechanism 2.

---

## 6. Client-side ASR normalisation

This section is scoped to transformations that run **before a server request is constructed**, and applies to Mechanism 1 only — Mechanism 2 has no equivalent pre-submission transformation stage at all, since the Use-button handler submits the already-translated Chinese candidate directly with no recognizer session, filler check, or recovery-match step in between (§2, §3). Mechanism 4 is not applicable (no client code runs).

| Order | Transformation | Function | Applies to Mechanism 1 | Applies to Mechanism 2 | Changes visible text? | Changes submitted text? |
|---|---|---|---|---|---|---|
| 1 | Segment-boundary join with overlap dedup, no inserted spacing | `_joinSegments()` (`ui/app.js:3635-3649`, §5) | Yes (grace-continuation segments only) | No — no recognizer session exists on this path | Yes — it *constructs* the transcript that becomes visible | Yes — same string is submitted |
| 2 | Formal→spoken register substitution (fixed pair list) | `_normalizeSpokenRegister()` (`ui/app.js:2647-2661`), via `normalizeForMatch()` | Yes, but **only for internal comparison** | No | **No** — used only inside `normalizeForMatch`'s return value, which is a separate comparison string, not the transcript itself | **No** |
| 3 | Whitespace/CJK-punctuation strip for exact-match comparison | `normalizeForMatch()` (`ui/app.js:2657-2661`) | Yes, for recovery-phrase matching (§7) | No | No | No |
| 4 | Leading-filler strip (guarded, min. 2 chars remaining) | `normalizeConversationalFillers()` (`ui/app.js:3204-3216`) | Yes, for internal classification (`_detectSemanticCategory`, unmatched-answer classification, §12) | No | **No** — not applied to the visible/submitted transcript on Mechanism 1 either | **No** |
| 5 | Filler-only / incomplete-utterance detection (no mutation) | `isIncompleteLearnerUtterance()`, `_isPureFillerUtterance()`, `_isSufficientLinguisticSignal()` (`ui/app.js:2667-2732`, `3888-3901`) | Yes | No | No | No — this is a classification gate that can **reject the submission entirely** (§12), not a text transform |
| 6 | ASR-duplicate submission suppression (key comparison, not text mutation) | `_lastAcceptedAsrKey`/`_lastAcceptedAsrTime` check (`ui/app.js:7665-7670`) | **Only within the unmatched free-answer branch of Mechanism 1** — see the precise scope in §17 | **No** — confirmed no reference to either identifier exists in the Use-button handler or anywhere in the translate-panel code (`ui/app.js:9231-9432`) | No | No — it can suppress an entire submission within its scope, but does not alter the text of an accepted one |

**Conclusion — literal transcript cleanup vs. semantic reinterpretation:** for Mechanism 1, the client performs **no literal cleanup of the submitted/visible transcript at all** beyond segment-join concatenation (row 1). Every other "normalisation"-adjacent function found (register substitution, whitespace/punctuation stripping for matching, filler stripping, filler-only detection) exists solely to support **internal classification decisions** and explicitly does not mutate `saidTrimmed`. For Mechanism 2, none of rows 1-6 apply at all — the translated Chinese candidate is submitted as-is, with only `_normalize_zh_for_routing()` on the server (§10) applying any routing-text cleanup, identically to how it treats Mechanism 1's submitted text.

**Specific items investigated and their findings, applicable to Mechanism 1:**

* **Whitespace normalisation, punctuation removal, casing:** not applied to the submitted/visible text client-side (see above); `normalizeForMatch` does this only for its own internal return value.
* **Filler removal:** classification-only (row 4), not applied to visible/submitted text.
* **Repeated-token cleanup:** the only mechanism found is `_joinSegments`'s overlap-stripping at segment boundaries (row 1); there is no general repeated-word collapse within a single final segment.
* **Common ASR substitution repair, names/places:** **not found** on the client; this class of repair is entirely server-side (§11).
* **Transcript truncation:** **not found** — no maximum-length truncation of the transcript was located in `ui/app.js`.
* **`等你等`-style repair:** **not found on the client** — `_repair_asr_junk_text()` is a server-side function only (§11).

---

## 7. Client-intercepted spoken recovery

**Applies to Mechanism 1 only.** Mechanism 2 has no client-side recovery interception step (§8).

**Detection function:** `matchSpokenRecoveryPhraseExact(transcript, phrases)` (`ui/app.js:2331-2350`). It normalises the transcript via `normalizeForMatch()` (whitespace/punctuation strip plus register normalisation, §6 rows 2-3 — **not** filler stripping) and checks for **exact equality** (not substring containment) against each phrase's normalised `hanzi`, normalised `pinyin` (spaces stripped), or any entry in that phrase's `alternatives` array (`ui/app.js:2336-2347`). A separate function, `matchTranscriptToLearnerPhrase()` (`ui/app.js:2300-2314`), performs exact-**or**-substring matching but is used elsewhere (`computeRecoveryTriggerContext`, `ui/app.js:2384`, and the tap-driven recovery panel), not for spoken interception.

**Why exact matching exists:** substring containment would cause an ordinary question that happens to contain a recovery-phrase substring — e.g. "你做什么工作" containing "什么" — to be misclassified as the learner asking "什么？" ("what?") and intercepted, silently discarding a genuine question. Exact matching (after whitespace/punctuation/register normalisation only) avoids this false-positive class.

**Phrase source:** loaded at runtime from `/runtime/out_phase7/recovery_phrases.runtime.json` (`ui/app.js:2236-2242`), a gitignored build artifact generated by `tools/build_runtime_artifacts.py::build_recovery_phrases_runtime()` from `content/recovery_phrases.json`. There is **no hardcoded phrase array** in `ui/app.js`. `learnerRecoveryPhrases(data)` (`ui/app.js:2262-2266`) filters the full phrase set to entries whose `use` is `"not_understood"`, `"topic_reset"`, or `"topic_shift"`.

**How filler stripping interacts with matching:** it does not. `normalizeForMatch()` does not call the filler-stripping function (`normalizeConversationalFillers`), so a filler-wrapped recovery utterance only intercepts if its exact normalised form matches a phrase's `hanzi`/`pinyin`/alternatives verbatim.

**Recognised recovery phrases in `content/recovery_phrases.json`** (confirmed entries): "嗯？"/"啊？" (`recovery_action: "soft"`), "什么？" (`"repeat"`), "等一下"/"我想想" (`"soft"`), "再说一遍" (`"repeat"`), "慢一点说" (`"slower"`), "我有点不懂"/"什么意思啊？" (`"meaning"`), "好吧" (`"next_turn"`).

| Recovery type | Detection rule | Client action | Server request? | Frame state changed? | Counter updated? | Transcript shown? |
|---|---|---|---|---|---|---|
| Repeat (`recovery_action: "repeat"`, e.g. "再说一遍") | Exact match, action resolved via `getRecoveryAction()` | Replay partner's last question/statement via TTS; add both learner and partner lines to transcript | No | No | Yes — `_challenge.recoveryCount`, `_tracker.recovery_uses` (§8) | Yes — `saidTrimmed` added via `addTranscriptEntry` (`ui/app.js:7730`) |
| Slower (`"slower"`, e.g. "慢一点说") | Exact match | Same as repeat, but TTS rate `0.82` and a `"好的，慢一点："`-prefixed restatement | No | No | Yes | Yes |
| Meaning (`"meaning"`, e.g. "我有点不懂") | Exact match; `getRecoveryAction()` maps `"meaning"` → `"repeat"` internally (`ui/app.js:5294-5295`) | Same as repeat | No | No | Yes | Yes |
| Soft (`"soft"`, e.g. "嗯？"/"啊？"/"等一下"/"我想想") | Exact match; `getRecoveryAction()`'s final fallthrough resolves unknown/`"soft"` actions to `"repeat"` (`ui/app.js:5296`) | Same as repeat | No | No | Yes | Yes |
| Next-turn (`"next_turn"`, e.g. "好吧") | Exact match, but explicitly **excluded** from interception — the gate at `ui/app.js:7729` only proceeds for `"repeat"`/`"slower"`/`"meaning"` | Falls through to normal `runTurn` flow | **Yes** | Yes — normal server frame selection runs | Not a recovery-counter increment | Yes |
| Any non-matching confusion-adjacent utterance | No exact match found | No interception occurs | Depends on downstream classification (§12) | Determined by server, if reached | Determined by server-side counters | Yes |

**What happens after the first, second, and later recovery attempts (client-side):** `_challenge.recoveryCount` increments on every intercepted (or panel-tapped) recovery regardless of count (`ui/app.js:7735`, `5406`); once `_challenge.recoveryCount >= 2`, `_challengeRevealText()` fires (§14).

**Recovery counters — client-owned:** `_challenge.recoveryCount`, `_tracker.recovery_uses`, `_tracker.successful_recoveries`, `window._consecutiveNotUnderstood`, and `window._recoveryPromptsByFrame` are all plain in-memory JavaScript state, not sent to or read from `conversation_state` for the client-intercepted path (§18).

---

## 8. Spoken-recovery versus server recovery

### Client-intercepted recovery (Mechanism 1 only)

* No `/api/run_turn` request is made (§7 table).
* No semantic frame progression occurs — the frame the learner was answering remains exactly as it was.
* Local replay/reveal behaviour only: TTS restatement of the partner's last line, and, after the second occurrence, Challenge Mode text reveal (§14).
* Applies only to the **exact** phrase set from `content/recovery_phrases.json` filtered to `use ∈ {not_understood, topic_reset, topic_shift}`, and only when the resolved action is `"repeat"`, `"slower"`, or `"meaning"` (§7).

### Server-routed recovery (any mechanism whose text reaches the server)

* Text is submitted as an ordinary turn (via Mechanism 1's non-intercepted path, Mechanism 2, or Mechanism 4).
* Server-side classifiers may respond: `_is_meaning`, `_is_example`, `_is_rr`, `_is_confusion_signal`-gated branches, and `_lexical_definition_reply` (all documented fully in `docs/ANSWER_SOURCE_CONTRACT.md` §4, Priorities 8-15).
* Normal server frame selection still runs on the same turn.
* Cross-turn recovery state may be incomplete — mirror-confusion escalation (`STATE_CONTRACT.md` SIC-1) and noisy-location round-trip (SIC-2) are both documented open gaps that apply here.

### What determines which path handles an utterance

Exactly one gate, and it applies **only to Mechanism 1**: whether `matchSpokenRecoveryPhraseExact()` finds an exact match **and** the resolved action is `"repeat"`/`"slower"`/`"meaning"` (§7). This check runs inside `_runChineseMicListen`, **before** any server request is constructed, and only on that code path. A translate-assisted (Mechanism 2) "再说一遍" submission is never evaluated against this matcher at all — confirmed by the absence of any reference to `matchSpokenRecoveryPhraseExact` in the Use-button handler or the surrounding translate-panel code (`ui/app.js:9231-9432`); it is submitted to the server like any other text and is handled, if at all, by the server-side `_is_rr`/confusion-signal mechanisms in `docs/ANSWER_SOURCE_CONTRACT.md` §4 Priority 10. This is a structural, not incidental, asymmetry between Mechanisms 1 and 2 (§13).

---

## 9. Request construction

The `/api/run_turn` handler reads its JSON body once (`scripts/ui_server.py:8961-8968`). Learner-answer text is **not read from the payload root** — no `payload.get("answer_text")`, `payload.get("submitted_text")`, or `payload.get("selected_option_hanzi")` exists anywhere in `scripts/ui_server.py`.

**Learner text lives inside `conversation_state.last_answer`** (`cs = payload["conversation_state"]`, `scripts/ui_server.py:9138-9139`; `last_answer = cs.get("last_answer")`, `9175`), and this shape is identical regardless of which of the four mechanisms in §2 supplied the text:

| Field | Read site | Purpose | Populated by |
|---|---|---|---|
| `submitted_text` | `last_answer.get("submitted_text")` (`9184, 9242, 9528, 9538, 9878, 10189, 10302, 10436`) | Primary learner-text source | Mechanism 1: `saidTrimmed`; Mechanism 2: the translated Chinese candidate (`ui/app.js:9425`); Mechanism 4: whatever the test constructs |
| `selected_option_hanzi` | `last_answer.get("selected_option_hanzi")` (`9182, 9243, 9529, 9878, 10233`) | Fallback learner-text source (option-tap turns) | Not populated by Mechanism 1's free-answer or recovery-intercept paths, or by Mechanism 2 |
| `selected_option_meaning` | `last_answer.get("selected_option_meaning")` (`9183`) | Not learner text; the tapped option's gloss | — |
| `frame_id` | `last_answer.get("frame_id")` (`9178, 9199, 9541`, etc.) | Which frame the turn answered | All mechanisms |

**Precedence when `submitted_text` and `selected_option_hanzi` disagree:** `submitted_text` wins unconditionally, via `_answer_text_from_last_answer()` (`scripts/ui_server.py:2620-2627`):

```text
scripts/ui_server.py:2620-2627 (paraphrased):
  answer_text = norm_text(last_answer.get("submitted_text")
                          or last_answer.get("selected_option_hanzi")
                          or "")
```

This same fallback order — `submitted_text` before `selected_option_hanzi` — is repeated independently at `scripts/ui_server.py:1798-1801` for a separate helper, and is **not** always applied identically: `_last_user_text` (`scripts/ui_server.py:10434-10436`) uses **only** `submitted_text`, with **no fallback** to `selected_option_hanzi` — an option-tap-only turn (no free-text) has a populated `answer_text` but an empty `_last_user_text`. This divergence is present regardless of which mechanism supplied the text — it is a server-side field-precedence inconsistency, not a client input-mode effect.

**Fields explicitly NOT found in the payload:** `confidence`/`asr_confidence`/`recognition_confidence`, `is_spoken`, `input_mode` (as a client-sent field), `raw_transcript`, any challenge-mode marker. The server-computed `_sel_trace.input_mode` field (§16) is a same-turn, response-only heuristic inferred from which of `submitted_text`/`selected_option_hanzi` are populated — it is **not** sent by the client and does not distinguish Mechanism 1 from Mechanism 2 (both populate `submitted_text` only, so both are labelled `"asr"` by this heuristic — see §16's correction of this specific naming).

**Text appearing in more than one payload location:** confirmed — the same logical learner text is read via both `submitted_text` and `selected_option_hanzi` inside the single `last_answer` object; it does not additionally appear at the payload root. No case was found of the same text appearing in *both* `last_answer` and a separate root-level field.

---

## 10. Server text selection and routing normalisation

### `_normalize_zh_for_routing()` (`scripts/ui_server.py:3753-3766`)

In order: (1) outer `.strip()`; (2) leading-filler removal via `_strip_leading_fillers()`, itself driven by `_FILLER_PREFIX_RE` (`3716-3723` — single-character particles `啊嗯呃哦哎呀唉`, discourse markers `那个|就是|然后|这个|好那|嗯那`, and Latin fillers `ne|ah|um|uh|er`), **guarded** so that if stripping would leave fewer than 2 characters, the original text is kept unchanged (`3737-3738`); (3) CJK inter-character whitespace collapse (`_CJK_SPACING_RE`, `3742-3744`); (4) a second `.strip()`; (5) trailing routing-filler strip (`_TRAILING_ROUTING_FILLER_RE`, `3746` — trailing `啊呢吧嗯哈啦` plus an optional trailing `？?！!。.`). **Not performed:** full-width-to-half-width conversion, general punctuation normalisation beyond the trailing-particle case.

### The four/five text variables and their exact relationships

| Variable | Derivation | Normalised? |
|---|---|---|
| `last_answer.submitted_text` / `.selected_option_hanzi` | Raw client-sent fields (any mechanism) | No |
| `answer_text` | `_answer_text_from_last_answer()`: `submitted_text` or `selected_option_hanzi`, `.strip()`-only | Strip only |
| `routing_answer_text` | `_normalize_zh_for_routing(answer_text)` | Yes, per above |
| `_routing_last_answer` | A shallow copy of `last_answer` with text fields replaced by `routing_answer_text`, when `last_turn_was_answer` and `routing_answer_text` is truthy; otherwise identical to `last_answer` (`scripts/ui_server.py:9208-9217`) | Partial — only the text fields are swapped |
| `_last_text_for_counter` | `routing_answer_text` if truthy, else the raw fallback directly (`scripts/ui_server.py:9875-9879`) | Usually yes |

### Consumer table — **classifiers do not all consume the same text**

| Consumer | Text field selected | Normalisation applied |
|---|---|---|
| `_is_rr`, `_is_meaning`, `_is_example`, `_lexical_definition_reply` (`_lex_ct`) | `_last_text_for_counter` | Routing-normalised |
| `_is_confusion_signal` (most call sites: `10007, 10057, 10091, 10118, 10129, 10144, 10165, 10326, 10330, 10342`) | `_last_text_for_counter` | Routing-normalised |
| `_is_confusion_signal` (`9454, 9492, 10276, 10404, 11409`) | **Raw `answer_text`** | None |
| User-initiative overrides — `_is_frustration_or_insult`, `_is_learner_disclosure`, `_is_persona_challenge`, `_food_responsive_reply`, `_has_volunteered_travel_intent` (`9902-9937`) | **Raw `answer_text`** | None |
| `_is_plain_affirmation` (`9296`) | **Raw `answer_text`** | None |
| `_is_direct_persona_question` (main routing call sites: `10056, 10093, 10120, 10244`) | `_last_text_for_counter` | Routing-normalised |
| `learner_memory_capture.capture_from_turn()` (`9180-9185`) | **Raw** `last_answer.submitted_text`/`.selected_option_hanzi` fields | None |
| `learner_stated_location` (persistent state write, `12132-12133`) | **Raw `answer_text`** | None |
| `_extract_open_world_location()` for routing/clarify purposes (`10148, 11592-11596`) | `_last_text_for_counter` | Routing-normalised |

**Conclusion:** the assumption that "all classifiers consume the same text" is **false**, regardless of which of the four input mechanisms supplied that text — this non-uniformity is a server-side property independent of input mechanism.

---

## 11. Server-side ASR repair and semantic correction

`_repair_asr_junk_text()` (`scripts/ui_server.py:618-629`) has **7 direct call sites** in `scripts/ui_server.py`, classified individually below. There is **no single, uniform timing rule** across them — some run before frame selection, some after, and this section makes no blanket claim otherwise.

```618:629:scripts/ui_server.py
def _repair_asr_junk_text(text: Optional[str]) -> str:
    """Strip known ASR-junk fragments from learner-facing Chinese so corrupted
    stored/echoed values never reach the learner (regression: '等你等…')."""
    if not text:
        return text or ""
    out = text
    for junk in _ASR_JUNK_OUTPUT_FRAGMENTS:
        if junk in out:
            out = out.replace(junk, "")
    # Collapse a leftover leading connective particle from the removed junk.
    out = out.lstrip("的，,。.、 ")
    return out
```

### Call site 1 — `scripts/ui_server.py:4153` (residence prefix-tail extraction)

| Field | Value |
|---|---|
| Pipeline phase | Inside `_extract_open_world_location()` — prefix-tail cleanup after stripping a residence prefix (e.g. `"我住在"`) |
| Input value | `tail` — suffix of the answer text after prefix removal and punctuation strip |
| Output value | `tail` (reassigned); returned by `_extract_open_world_location()` to its caller |
| Visible learner text changes? | **Indirectly** — the return value can feed `state_update.learner_stated_location` or drive a clarify-frame's text, not written to any transcript directly at this site |
| Stored learner facts change? | **No** — `capture_from_turn()` (`9177-9189`) uses its own separate extractors on raw `last_answer` fields and does not call this function |
| EN/pinyin/frame-English recomputed? | Not applicable at this site — no EN/pinyin field is touched here |
| Before/after answer-source resolution? | **Depends entirely on the caller** — three distinct callers exist, with different timing: (a) `10148`, inside the counter-reply priority chain, **before** frame selection completes; (b) `11596`, inside a participation-success escape check, **after** frame selection and response assembly have already run; (c) `12132-12134`, the `learner_stated_location` state write, **after** selection, using **raw** `answer_text` as input (not `_last_text_for_counter`) |
| Session capture sees pre- or post-repair value? | `_diag_cap` captures raw/routing text at `9236-9275`, **before** this repair runs; this specific repaired value is not separately captured in diagnostics |

### Call site 2 — `scripts/ui_server.py:4158` (bare residence answer, same function, different branch)

| Field | Value |
|---|---|
| Pipeline phase | Same function as site 1 — bare-answer path when `frame_is_residence=True` and no prefix matched |
| Input value | `t` — the full stripped input text |
| Output value | `bare` local, returned (or `None`) |
| Visible learner text changes? | Same indirect paths as site 1 |
| Stored learner facts change? | **No** (same reason as site 1) |
| EN/pinyin recomputed? | Not applicable at this site |
| Before/after answer-source resolution? | Same three callers, same mixed timing as site 1 |
| Session capture | Same as site 1 |

### Call site 3 — `scripts/ui_server.py:11679` (learner-memory slot fill, `{CITY}`/`{PLACE}`)

| Field | Value |
|---|---|
| Pipeline phase | Phase 13A learner-memory slot substitution — reads previously stored `lives_in`/`hometown`, repairs before template fill |
| Input value | `_city`, from `_slot_mem.get("lives_in")` or `.get("hometown")` — this is a **read** of already-persisted memory, not the current turn's answer text |
| Output value | `_city` reassigned, then written into `response["frame_text"]`, `response["frame_pinyin"]`, `response["frame_text_en"]` |
| Visible learner text changes? | **Yes** — the repaired value appears directly in the partner's rendered turn |
| Stored learner facts change? | **No write-back** — this is read-time-only repair; the underlying `learner_memory.json` value written earlier by `capture_from_turn()` remains unrepaired |
| EN/pinyin/frame-English recomputed? | **Yes, in this same block** — `[CITY]` in `frame_text_en` and `{CITY}` in `frame_pinyin` are both replaced with the same repaired `_city` value (`11686-11689`) — this call site is the exception to the general "EN/pinyin left stale" pattern seen at the final-repair call sites below |
| Before/after answer-source resolution? | **After** — runs during response assembly, after frame selection has already completed (`11661+`) |
| Session capture | `_diag_cap` input fields were captured earlier, before this repair; `_diag_finalize_response` (`12417`) captures the final post-repair response text, which reflects this call's output |

### Call site 4 — `scripts/ui_server.py:11693` (learner-memory slot fill, `{HOMETOWN}`)

Structurally identical to call site 3 in every respect (same enclosing block, same "read persisted memory → repair → fill template → recompute EN/pinyin in the same block → after frame selection"), differing only in that it targets the `{HOMETOWN}`/`[HOMETOWN]` tokens specifically using `_slot_mem.get("hometown")`.

### Call site 5 — `scripts/ui_server.py:12410` (final `frame_text` guard)

```12407:12417:scripts/ui_server.py
            # ── Final repair guard: no ASR-junk fragment (等你等 …) may reach the ───
            # learner in any rendered Chinese line, whatever path produced it.
            if isinstance(response.get("frame_text"), str):
                response["frame_text"] = _repair_asr_junk_text(response["frame_text"])
            _cr_final = response.get("counter_reply")
            if isinstance(_cr_final, str):
                response["counter_reply"] = _repair_asr_junk_text(_cr_final)
            elif isinstance(_cr_final, dict) and isinstance(_cr_final.get("zh"), str):
                _cr_final["zh"] = _repair_asr_junk_text(_cr_final["zh"])

            _diag_finalize_response(response, _diag_cap)
```

| Field | Value |
|---|---|
| Pipeline phase | Final response-level guard, immediately before JSON serialisation |
| Input value | `response["frame_text"]` |
| Output value | `response["frame_text"]`, overwritten in place |
| Visible learner text changes? | **Yes** — this is the exact text the client displays and sends to TTS |
| Stored learner facts change? | **No** |
| EN/pinyin/frame-English recomputed? | **No** — `frame_text_en` and `frame_pinyin` are not touched by this call; if a junk fragment is stripped from `frame_text` here, English/pinyin can diverge from the (now-shorter) Chinese |
| Before/after answer-source resolution? | **After** — runs after frame selection, discovery-panel logic, session-end handling, slot substitution (sites 3/4), and counter-reply assembly are all already complete |
| Session capture | `_diag_finalize_response` runs immediately after this call and records the **post-repair** value as `final_response_text` |

### Call site 6 — `scripts/ui_server.py:12413` (final `counter_reply` string form)

Same enclosing block as site 5. Input is `_cr_final = response.get("counter_reply")` when it is a plain string; output overwrites `response["counter_reply"]`. Same conclusions as site 5: visible-text change yes, memory-persistence no, EN/pinyin recomputation **no** (`counter_reply_en`/`counter_reply_pinyin` were already set earlier at `11817-11821` and are left stale if this call strips text from the Chinese), timing after answer-source resolution, and diagnostics capture the post-repair value.

### Call site 7 — `scripts/ui_server.py:12415` (final `counter_reply` dict form, `.zh` key)

Same enclosing block; applies when `counter_reply` is a `dict` with a `"zh"` key rather than a plain string — `_cr_final["zh"]` is mutated in place (same object referenced by `response["counter_reply"]`). Identical conclusions to site 6 in every other respect.

### Cross-cutting notes

Call sites 5-7 are the same mechanism documented as the final ASR-junk output-repair pass in `docs/ANSWER_SOURCE_CONTRACT.md` §3.3(4); that document's non-recomputation-of-English/pinyin finding is confirmed directly from this call site's code and is not re-derived independently here. Call sites 1-2 are genuinely input/routing-side (never touch the visible transcript directly, never persist to memory) but have **caller-dependent** before/after-selection timing, not a single fixed phase. Call sites 3-4 are the sole call sites where English/pinyin **are** recomputed in the same block as the repair.

**Other server-side ASR repair/correction mechanisms** (unchanged from the original investigation, timing and scope as previously documented): `_repair_contextual_place_question()` (`4486-4531`, routing-text-only by its own docstring, never touches the raw transcript); `_extract_open_world_location()` (`4126-4160`, split input — routing-normalised for routing/clarify paths, raw for the `learner_stated_location` write); `_detect_travel_asr_near_match()` (`2154-2161`); `_recover_malformed_travel_destination()`/`_extract_travel_destination()` (`5871-5924`); `_detect_near_miss_answer()` (`2203-2217+`); `_is_closing_blocked_by_learner_signal()` (`3917-3956`); `_normalize_place_name()` (applied to stored memory only, `11680-11681, 11694-11695`).

---

## 12. Filler handling

**Exact filler inventory (client, `ui/app.js`):**

* Acoustic filler characters: `_FILLER_CHAR_SET = {嗯, 啊, 呃, 哦, 喔, 哎, 诶, 呀, 唉}` (`ui/app.js:2664`).
* Discourse fragment fillers: `_DISCOURSE_FRAGMENT_FILLERS = {这个, 那个, 就是}` (`ui/app.js:2665`).
* Single-token incomplete-utterance filler set (a superset including `我`): `ui/app.js:2727`.
* Leading-filler regex for internal-classification stripping: `_LEADING_FILLER_PAT` (`ui/app.js:3204`).

**Exact filler inventory (server, `_normalize_zh_for_routing`, §10):** a separate, independently-defined set (`_FILLER_PREFIX_RE`, `scripts/ui_server.py:3716-3723`) covering overlapping but not identical particles/markers to the client list — two distinct filler definitions maintained in two different files, not one shared source.

### Precise conclusion for a filler-only resolved transcript on Mechanism 1

The client's silence timer, not `onend`, is the deciding code path:

```3882:3901:ui/app.js
    function resetSilenceTimer() {
      if (resolved) return;
      if (silenceTid) clearTimeout(silenceTid);
      const silenceDelay = speechStarted ? SPEECH_SILENCE_MS : preSpeechSilenceMs;
      silenceTid = setTimeout(() => {
        if (resolved) return;
        const fillerOnly = isIncompleteLearnerUtterance(getBestTranscript());
        if (!fillerExtendFired && fillerOnly) {
          fillerExtendFired = true;
          console.log(`[ASR] filler-only silence — extending listen ${SPEECH_FILLER_EXTEND_MS}ms`);
          _setListenState("waiting");
          silenceTid = setTimeout(() => {
            console.log(`[ASR] filler extend timeout fired, transcript="${finalTranscript}"`);
            finish("silence_filler_extended");
          }, SPEECH_FILLER_EXTEND_MS);
          return;
        }
        console.log(`[ASR] silence timeout fired, transcript="${finalTranscript}"`);
        finish("silence");
      }, silenceDelay);
    }
```

1. **The client extends listening exactly once** when the silence timer fires on a filler-only transcript (`isIncompleteLearnerUtterance(getBestTranscript())` true), for `SPEECH_FILLER_EXTEND_MS = 2000` ms (`ui/app.js:3430-3431`). This one-shot extension is gated by `fillerExtendFired`, so it cannot recur within the same listen session.
2. If the learner does not produce further speech within that window, `finish("silence_filler_extended")` runs and the (still filler-only) transcript resolves as the session's final text.
3. **The client then rejects this text before any server request is made.** `_runChineseMicListen`'s free-answer classification calls `classifyUnmatchedFreeAnswerDecision()`, which in turn calls `_isSufficientLinguisticSignal()` (`ui/app.js:2707-2719`) — for pure filler, `isIncompleteLearnerUtterance(s)` is true, which makes `_isSufficientLinguisticSignal` return `false`, which makes the decision's `accept` field `false` with `reason: "insufficient_linguistic_signal"` (`ui/app.js:3391-3392`). `substantialAnswer` is therefore `false`, and **no `runTurn()` call occurs on this path.**
4. **No server turn and no server-side frame selection occur for a filler-only transcript rejected this way** — this is a purely client-side rejection, confirmed directly by the absence of any `runTurn`/`fetch` call in the rejected branch, and by an explicit comment in the code acknowledging this: "A rejected spoken turn is NOT submitted to `/api/run_turn`" (`ui/app.js:8006-8008`).
5. **The filler text is nevertheless shown in the local transcript** — `addTranscriptEntry` is called for it (`ui/app.js:8032`), and a client-side partner recovery line is displayed with `setUiMode("RESPOND")` (`ui/app.js:8032-8071`) — this is client-side recovery UI, not the server-routed recovery of §8, and does not touch `_last_text_for_counter`/`_normalize_zh_for_routing()` at all since no request is sent.
6. **Server-side routing normalisation is therefore never applied to this text** in the filler-only-rejection scenario, because the text never reaches the server. `_normalize_zh_for_routing()`'s own independent filler-stripping (§10) is a separate mechanism that applies only to text that *is* submitted (from any of the four mechanisms) and happens to still carry a leading/trailing filler particle around otherwise-substantive content — not to a wholly filler-only rejected utterance.

**Correction of a prior claim:** an earlier draft of this document stated that filler-only text "can still be submitted and is then handled by server-side classification (or rejected there, per `tests/verify_asr_filler.js`'s `insufficient_linguistic_signal` mechanism)." This was incorrect on two counts: (a) `insufficient_linguistic_signal` is a **client-side** rejection reason (`ui/app.js:3392`), not a server-side one, and (b) `tests/verify_asr_filler.js` is **mirrored/static verification** — it re-implements filler-classification logic inside the test file rather than executing the real functions extracted from `ui/app.js` via `tests/_load_app_js_helper.js` — and should never be cited as evidence of actual server (or even actual client, since it's a mirror) behaviour. The conclusion above is instead drawn directly from `ui/app.js`'s own source at the cited lines.

**Filler-wrapped recovery phrases:** as established in §7, filler-wrapped recovery phrases are **not** generically stripped before the exact-match check — a filler-wrapped variant only intercepts if it happens to be listed verbatim as a phrase-bank `alternatives` entry.

**Repeated fillers collapsing:** `_isPureFillerUtterance()` (`ui/app.js:2667-2674`) is a detection function only; repeated fillers are not rewritten into a single instance anywhere found.

**Mechanism 2 and filler handling:** not applicable — Mechanism 2 has no listening session, no silence timer, and no `isIncompleteLearnerUtterance` check in the Use-button handler; a learner could in principle type/translate filler-only English text and have it submitted as-is, with only server-side `_normalize_zh_for_routing()` (§10) applying, if at all.

---

## 13. Input-mechanism parity

| Behaviour | Mechanism 1 (Chinese mic) | Mechanism 2 (translate-assisted typed) | Mechanism 4 (synthetic test payload) | Equivalent across 1 and 2? |
|---|---|---|---|---|
| Direct persona questions, E4 handoff | Reaches the same server pipeline once submitted | Same | Same | Yes, after submission |
| Recovery | Client-intercepted for exact-matching phrases with a `repeat`/`slower`/`meaning` action (§7); no interception exists in the Use-button handler | No client-side interception step exists at all (§8) | Not applicable — no client code | **No** — structurally different; interception exists specifically to avoid a server round-trip during active listening, which Mechanism 2 never enters |
| Filler-only rejection | Rejected client-side before any request (§12) | No equivalent rejection mechanism — Mechanism 2 has no filler classification step at all | Not applicable | **No** |
| Transcript display timing | `addTranscriptEntry` called after the resolved transcript is known, before submission | `addTranscriptEntry` called before the request, immediately in the click handler (`ui/app.js:9420-9421`) | Not applicable | Similar in effect (both display-before-submit), different call sites |
| Duplicate-submission suppression | Applies **only** within the unmatched free-answer branch (§17) | **Confirmed not applicable** — no reference to `_lastAcceptedAsrKey`/`_lastAcceptedAsrTime` exists anywhere in the translate-panel code | Not applicable | **No** |
| Browser permission/error handling | Full lifecycle in §4 | Not applicable — no recognizer is invoked by the Use-button path itself (though the learner may have separately used Mechanism 3 to fill `#engInput`, which has its own, different error handling, §4.3) | Not applicable | **No** |
| Learner-memory extraction | `capture_from_turn()` reads raw `submitted_text`/`selected_option_hanzi` (§10) — identical regardless of mechanism | Same | Same (whatever the test constructs) | Yes |
| Session-capture field shape | Same `last_answer` shape stored either way | Same | Same | Yes, at the stored-field level — but see §16 for what is and is not actually persisted by default |
| Challenge Mode gating | Not gated on input mechanism — mic path has no `_challenge.active` guard | Not gated — Use-button handler has no such guard either | Not applicable | Yes |

**Guaranteed identical after server submission:** answer-source resolution, E4 eligibility, learner-memory capture, session-capture field shape, Challenge Mode gating, and the non-uniform routing/raw-text classifier split documented in §10 (which applies identically regardless of which mechanism supplied the text). **Remains mechanism-specific:** whether client-side recovery interception can occur at all (Mechanism 1 only), whether a filler-only rejection step exists (Mechanism 1 only), whether a listening/silence-extension phase exists (Mechanism 1 only), whether browser permission/support/insecure-origin failure modes apply (Mechanism 1 and, separately, Mechanism 3), and whether the ASR-dedup guard applies (confirmed scoped to a single branch of Mechanism 1 only, §17). Mechanism 4 shares the server-side pipeline with 1 and 2 but exercises none of the client-side mechanisms in §§4-8 and 12, and — per §1 — is not itself a production input mode.

---

## 14. Challenge Mode interaction

**Is speech mandatory?** No. Neither the Use-button handler (Mechanism 2) nor the Chinese-mic path (Mechanism 1) has a `_challenge.active` guard restricting or requiring it.

### Definitive CSS/JS visibility audit

`ui/index.html` links exactly one first-party stylesheet, `ui/styles.css` (via `<link rel="stylesheet" href="/styles.css">`), plus an external Google Fonts stylesheet, and contains one large inline `<style>` block (`ui/index.html:179-641`). Grep of `ui/index.html`'s inline styles for `challenge-mode`/`challenge-text-revealed` returns **zero matches** — all Challenge-Mode-specific CSS lives in `ui/styles.css`, in exactly six rules:

```833:868:ui/styles.css
/* ── Challenge Mode (C1–C4) ───────────────────────────────────────────────── */
/* Additive overlay: body.challenge-mode gates all visibility changes.
   Removing the class fully restores normal mode — no DOM cleanup needed.    */

/* Transcript: hidden so learner relies on audio only */
body.challenge-mode #transcriptPanel { display: none; }

/* Active sentence text: invisible but structurally present so TTS + DOM are unchanged.
   pointer-events: none prevents accidental token clicks before text is revealed.      */
body.challenge-mode #frameSentence {
  visibility: hidden;
  pointer-events: none;
  user-select: none;
}

/* Mirror / reverse question buttons live in #reverseActionsRow (no inline style set by JS) */
body.challenge-mode #reverseActionsRow { display: none; }

/* Text-revealed override: body class added by _challengeRevealText() after cascade threshold */
body.challenge-mode.challenge-text-revealed #frameSentence {
  visibility: visible;
  pointer-events: auto;
  user-select: auto;
}

/* Challenge recovery zone: recovery phrase buttons, always visible in challenge mode */
#challengeRecoveryZone { display: none; }
body.challenge-mode #challengeRecoveryZone { display: block; margin-top: 10px; }
```

Both classes are toggled by JavaScript: `document.body.classList.toggle("challenge-mode", _challenge.active)` in `toggleChallengeMode()` (`ui/app.js:8162`), and `document.body.classList.add("challenge-text-revealed")` in `_challengeRevealText()` (`ui/app.js:8151`).

**Definitive conclusion table** — no row is left as "possibly hidden by CSS not found":

| # | Element | INITIAL state (`body.challenge-mode`, before reveal) | REVEALED state (`.challenge-text-revealed` added) | Control mechanism |
|---|---|---|---|---|
| 1 | Partner Chinese (`#frameSentence`) | **Hidden** — `visibility: hidden` (`ui/styles.css:842-846`) | **Visible** — `visibility: visible` (`ui/styles.css:852-856`) | **CSS** (classes toggled by JS) |
| 2 | Partner pinyin (`#hintPinyin`) | **Hidden** — by JavaScript inline style, not CSS: `hintPinyin.style.display = "none"` while hint-cascade `level` is 0 (`ui/app.js:1894-1900`); **no CSS rule targeting this element exists under `challenge-mode` at all** — confirmed by exhaustive search of `ui/styles.css` | **Still hidden** — `challenge-text-revealed` does not itself advance the hint-cascade level; the learner must separately advance the "?" hint cascade | **JS only** — no challenge CSS rule found for pinyin |
| 3 | Partner English (`#frameEnglish`) | **Hidden** — by JavaScript inline style: `el.style.display = "none"` when `_challenge.active` (`ui/app.js:4023-4025, 4052-4055`); **no CSS rule targeting `#frameEnglish`/`.frame-english` exists under `challenge-mode`** — confirmed by exhaustive search | **Still hidden** — the same JS guard remains in force; English may become visible via a separate `#hintMeaning` element at a later hint-cascade level, not via `#frameEnglish` itself | **JS only** — no challenge CSS rule found |
| 4 | Suggested learner responses (`#sentenceOptionsContainer`, `#optionsContainer`) | **Hidden** — by JavaScript inline style after each turn render (`ui/app.js:7288-7294`), and by an `HTML`-authored default `style="display:none;"` on `#sentenceOptionsContainer` (`ui/index.html:123`); **no CSS rule targeting either container exists under `challenge-mode`** — confirmed | **Still hidden** — `challenge-text-revealed` has no effect on these containers; the learner must tap `#showOptionsBtn` (`ui/app.js:8191-8193`) | **JS only** — no challenge CSS rule found |
| 5 | Learner's own ASR interim preview (`#listenStatus` / `.asr-interim-preview`) | **Not hidden by Challenge Mode at all** — visibility is governed entirely by the `.listen-status[data-state="…"]` rules (`ui/styles.css:1500-1525`), none of which have a `challenge-mode` ancestor; confirmed by exhaustive search | **Same — unaffected** | **CSS + JS, but neither is challenge-gated** |
| 6 | Learner's submitted/visible transcript (`#transcriptPanel`) | **Hidden** — `display: none` (`ui/styles.css:838`) | **Still hidden — no reveal override exists for the transcript panel; it remains hidden for the entire Challenge Mode session**, unlike row 1 | **CSS** (`body.challenge-mode` only, no revealed-state override) |

**A prior draft of this document left rows 1-4 as "possibly in CSS" or "out of scope."** That hedge has been removed: rows 1 and 6 are confirmed CSS-controlled (with a reveal override existing only for row 1); rows 2, 3, and 4 are confirmed JavaScript-inline-style-controlled with **no** corresponding CSS rule of any kind; row 5 is confirmed entirely unaffected by Challenge Mode in either CSS or JS.

**Is hidden transcript text nevertheless submitted or stored?** Yes, unconditionally, for everything except row 6's own display state. The partner's frame text (rows 1-4) is still fully populated into the DOM and into `window._sentenceHint`/`window._currentFrameText`/`window._lastPartnerSpokenText` during ordinary turn processing. The ASR interim preview (row 5) is never suppressed. The conversation transcript (row 6) is likewise never suppressed from `conversationTranscript`'s in-memory array — only its DOM container's `display` is hidden.

**Recovery panel in Challenge Mode:** rendered into `#challengeRecoveryZone` (shown via `body.challenge-mode #challengeRecoveryZone { display: block; }`) instead of the standard sentence-options container.

**Reset behaviour:** unchanged from prior findings — `_resetChallengeHelpState()` (`ui/app.js:8139-8146`) clears `_challenge.recoveryCount`/`helpLevel`/the `challenge-text-revealed` body class at the start of each server turn (`ui/app.js:6640-6641`) and on full session reset (`ui/app.js:6498`); persona switch does **not** trigger this reset (confirmed — the persona-button click handler, `ui/app.js:4973-4984`, only clears `_revealedVoiceLines`/`_revealedPartnerFacts`).

---

## 15. TTS and microphone coordination

**Scope note:** only ASR-relevant TTS behaviour is covered here; TTS provider/synthesis architecture is out of scope.

**Is the microphone disabled while partner audio plays?** There is no explicit disabling of the mic *button* while TTS plays, but the recognizer itself is never automatically started during TTS playback — the mic only opens on an explicit user tap, and `listenForResponse()` proactively **cancels any in-progress partner TTS** the moment it is invoked: `if (window.speechSynthesis) window.speechSynthesis.cancel()` (`ui/app.js:3563-3567`), explicitly to prevent the recognizer from transcribing the app's own speaker output.

**Automatic listening after TTS:** **not found.** No `onended`/`onboundary` handler on TTS output was found that automatically starts the recognizer. The normal turn-submission flow is the reverse: the learner's own speech (or Mechanism 2 text) triggers TTS playback of it, and `runTurn()` is invoked once that TTS completes (`ui/app.js:7641-7653, 7872-7886`) — this is TTS-after-recognition, not recognition-after-TTS.

**Stop/cancel ordering:** `speechSynthesis.cancel()` runs synchronously at the very start of `listenForResponse()`, before the recognizer is created or `beginListening()` is scheduled — cancellation always precedes recognizer start, never the reverse.

**Race-condition guards:** the recovery-panel tap is blocked while `document.body.classList.contains("is-listening")` (`ui/app.js:5391`). No equivalent guard was found preventing a spoken recovery interception from racing with an in-progress TTS replay from a different recovery action.

---

## 16. Transcript and session-capture contract

### There is no production per-turn session-capture writer separate from opt-in diagnostics

Searches for `session_capture`, `turn_record`, `append_turn`, `log_turn`, `SessionWriter` in production code found **no matches** — no default-on, per-turn persistent writer exists. What actually exists:

| Mechanism | Fires | Persists to | Gating |
|---|---|---|---|
| `session_intelligence.py` | Only at `/api/end_session` | `data/sessions/{learner_id}/{session_id}.json` | `MANDARINOS_SESSION_CAPTURE=1` environment variable — **disabled by default** (`scripts/session_intelligence.py:31-32`) |
| `progress_store.py` | At `/api/end_session` | `data/progress/{learner_id}.json` | Runs whenever `learner_id` is present; not ASR-text-focused |
| `_diag_cap`/`_diag_append` (per-turn diagnostics) | Per `/api/run_turn` | Diagnostics trace file | `MANDARINOS_DIAG_TOKEN` server-side flag **and** a client-sent `diag_trace_id` |
| `selector_trace` | Per `/api/run_turn` | **Returned in the JSON response only — never written to disk** | Always computed, but not itself a capture mechanism |

### Fields actually persisted, when session capture is enabled

The client's end-session payload sends a transcript array shaped as follows — **no `submitted_text`, no `selected_option_hanzi`, no ASR raw/resolved-transcript field, and no input-mode marker are included**:

```10651:10663:ui/app.js
    transcript: (conversationTranscript || []).map(function(e) {
      return {
        idx:        e._idx !== undefined ? e._idx : undefined,
        id:         e.id         || undefined,
        role:       e.role       || undefined,
        text_zh:    e.text_zh    || undefined,
        text_en:    e.text_en    || undefined,
        pinyin:     e.pinyin     || undefined,
        frame_id:   e.frame_id   || undefined,
        turn_uid:   e.turn_uid   || undefined,
        created_at: e.created_at || undefined,
      };
    }),
```

`text_zh` is populated by `addTranscriptEntry` from whatever visible-text string was passed in at display time (§16 of the prior draft's table remains accurate for *which* string that is per mechanism) — this is the displayed text, not a separately-tagged raw-ASR field.

**Client-intercepted spoken recovery is absent from server session capture in the sense that matters: it never reaches the server at all** — by construction (§7, §8), no `/api/run_turn` request is made for an intercepted utterance, so the server-side diagnostics/session mechanisms above cannot capture it under any configuration. It **does** still appear in the client's own `conversationTranscript` array (added via `addTranscriptEntry`, `ui/app.js:7730`) and would therefore appear in the end-session transcript payload above, **if** session capture happens to be enabled for that session — but this is a client-side artifact, not a server-observed record of the interaction.

### Does production capture populate a field literally named `asr_raw`?

**No.** Exhaustive search for the literal string `"asr_raw"` across the repository found it only in:

* `docs/session_intelligence_architecture.md:161` — schema documentation (an example only).
* `scripts/session_intelligence.py:95` — an *allow-list* of field names that would be passed through *if* a client ever sent them; this does not mean any production writer populates the field.
* `tests/test_export_session_review_prompt.py:106` — a test fixture's input data.

**Not found** in `ui/app.js` or in the live per-turn writer surface of `scripts/ui_server.py`. The closest field that *is* actually populated live is `selector_trace.asr_raw_text` (name ends in `_text`, not `asr_raw`) inside the `/api/run_turn` **response**:

```9530:9545:scripts/ui_server.py
                _sel_trace: dict = {
                    "final_frame_source": "not_computed",
                    ...
                    "input_mode": (
                        "asr" if _has_submitted_text and _has_selected_hanzi
                        else ("typed" if _has_submitted_text else ("option_tap" if _has_selected_hanzi else "none"))
                    ) if last_turn_was_answer else "none",
                    "asr_raw_text": (
                        (last_answer.get("submitted_text") or "") if isinstance(last_answer, dict) else ""
                    ) if last_turn_was_answer else "",
                    "accepted_text": answer_text,
                    ...
                    "normalized_answer": answer_text,
```

This response field is **not persisted to disk** — it is returned per-request only, and would need to be captured by a client-side or diagnostics-side consumer to survive past that single response. It is also worth noting explicitly, correcting §9's input-mode discussion: this heuristic's `"asr"` branch actually fires whenever **both** `submitted_text` and `selected_option_hanzi` are populated (an option-tap-plus-free-text combination) — it is a misnomer inherited from an earlier assumption and does **not** mean "this text came from the microphone"; Mechanism 1 and Mechanism 2 submissions that populate only `submitted_text` are both labelled `"typed"` by this same heuristic, which is a further confirmation that the server has no reliable spoken-vs-typed signal (§1, §9).

**Conclusion:** export/test tooling expects and can carry an `asr_raw`-named field if supplied, but **no production code path ever writes one** under that literal name; production's closest live analogue (`asr_raw_text`) is response-only and not persisted.

### Where raw evidence is lost

The transient `finalTranscript`/`interimTranscript` closure variables inside `listenForResponse` (§5) are never persisted anywhere once resolved to a single string. Once the client sends `saidTrimmed` (Mechanism 1) or the translated candidate (Mechanism 2) to the server, no interim hypothesis history survives for either mechanism. Only the offline ASR-trace-joining tool (`scripts/report_asr_traces.py`) is capable of reconstructing a client-side vs. server-side comparison, and only when diagnostics were explicitly enabled for that turn.

---

## 17. Error and fallback behaviour

| Scenario | Visible effect | Retry behaviour | Alternative input still available? | State reset | Duplicate-submission risk |
|---|---|---|---|---|---|
| Microphone/recognizer unavailable (`SpeechRecognition` undefined) | "Speech recognition is not available in this browser" notice; `finishReason: "not_available"` | None | Yes — Mechanism 2 is not disabled as a consequence | None needed | None |
| Insecure context (mobile + HTTP, non-localhost) | "Mic needs HTTPS…" notice, 6000ms display; `finishReason: "insecure_origin"` | None | Yes | None | None |
| Chinese mic permission denied (`"not-allowed"`/`"service-not-allowed"`) | `finish("permission_denied")`; user-visible message "Microphone access denied — allow mic in browser settings" (§4.3) | None automatic — a new mic tap re-triggers the browser permission flow | Yes | `resolved` flag set | Low — no partial transcript to resubmit |
| Auxiliary English recognizer permission denied | **No dedicated handling** — generic cleanup only (button state reset), **no message shown to the learner**, error type is never inspected (§4.3) | None | Yes (Mechanism 1/2 unaffected) | `_engRecording = false` | None |
| Recognition unsupported | Handled identically to "unavailable" above | — | Yes | — | — |
| No speech / aborted | Explicitly ignored in Chinese-mic `onerror`; handled via empty-`onend` retry logic instead | Up to 5 same-instance restarts | Yes | — | None |
| Network recognition failure (Chinese mic) | No dedicated branch — falls into the generic `finish("error")` catch-all | None automatic | Yes | — | Low |
| Duplicate final transcript, unmatched free-answer branch only | Suppressed by a 6-second key check (`_lastAcceptedAsrKey`/`_lastAcceptedAsrTime`, §6) | n/a | n/a | On new frame render / beta hygiene init | **Confirmed scoped to this one branch only** — not confirmed for matched-option, Use-button, or recovery-intercept branches (§13, §17 below) |
| Empty final transcript | Caller shows a notice and returns without submitting | Learner must re-tap the mic manually | Yes | `setUiMode("RESPOND")` | None |
| Filler-only resolved transcript | One-shot silence extension, then client-side rejection with no server submission (§12) | Learner must speak more substantively | Yes | — | None (never reaches the server) |

### Post-recognition server-failure behaviour (previously "not determined" — now resolved)

For a spoken transcript accepted client-side (Mechanisms 1 and 2 alike, since both funnel into `runTurn()`/`_runTurnInner`):

* **`addTranscriptEntry()` runs before the fetch, for both mechanisms.** For Mechanism 1's free-answer path: `addTranscriptEntry("user", saidTrimmed)` (`ui/app.js:7862`) happens, then TTS plays, then `runTurn(true, {...})` (which performs the fetch) fires on TTS completion (`ui/app.js:7872-7886`). For Mechanism 2: `addTranscriptEntry("user", zh, ...)` (`ui/app.js:9420-9421`) happens immediately in the click handler, before `runTurn()` is called (`ui/app.js:9429`).
* **On fetch throw:** the `try`/`catch` around the `fetch()` call emits `{ type: "UI_ERROR", payload: { message: String(e) } }` via `emitUITrace()` and then simply `return`s (`ui/app.js:6784-6792`) — no other action.
* **On a non-OK HTTP response:** the response body is read as text, an equivalent `UI_ERROR` trace is emitted with `{ status, body }`, and the function `return`s (`ui/app.js:6794-6800`) — again, no other action.
* **What remains on screen:** the user's transcript entry added before the request **stays visible** — there is no removal, rollback, or failure-marking of that entry in either error branch. No partner reply is added, since that only happens on a successful response.
* **UI mode after failure:** no `setUiMode` call exists in either error branch. Whatever mode was set immediately before the request (typically `"READ"` for the spoken free-answer path, set at `ui/app.js:7891` prior to the TTS-then-fetch sequence) remains active. The `_runTurnInFlight` in-flight guard is released via a `finally` block (`ui/app.js:6632`) regardless of success or failure.
* **Microphone/retry availability:** there is **no automatic retry**. `setUiMode` does not disable the mic button — only CSS classes are toggled — so the learner **can** manually re-tap the mic (or, for Mechanism 2, retype/re-translate and tap "Use" again) to retry. Nothing in the failure path prevents this.
* **Optimistic state not rolled back on failure:** `window._lastAnswer` is set to `null` **before** the fetch is issued (`ui/app.js:6738`, consumed when building the request payload) and is **not restored** if the request subsequently fails — a learner retrying must go through the listen/translate flow again to repopulate it, rather than the failed answer being automatically retried.
* **Duplicate-submission risk on retry:** for the unmatched free-answer branch specifically, `_lastAcceptedAsrKey`/`_lastAcceptedAsrTime` are set **before** `runTurn()` is invoked (`ui/app.js:7783-7784` / `7779-7784`) — so if the first submission's fetch fails and the learner repeats the *same* text within 6 seconds, the dedup guard will **block** the retry until the 6-second window elapses. After 6 seconds, or for any branch not covered by this guard (§6, §17 table above), no such suppression applies.
* **Error message shown to the learner:** **none.** Both error branches only call `emitUITrace()`, which writes into the developer-facing trace panel (`renderTrace()` → `traceEl`), not a learner-visible toast or alert. `console.warn` fires only for a JSON-parse failure on an otherwise-OK response (`ui/app.js:6808`).
* **Typed (Mechanism 2) vs. spoken (Mechanism 1) failure handling:** **shared, not separate.** The Use-button handler calls the identical `runTurn(true, { last_turn_was_answer: true })` entry point, which flows into the same `_runTurnInner` fetch/catch/`!res.ok` logic described above — no mechanism-specific branching exists in the failure path.

---

## 18. State interactions

| Field/variable | Owner | Producer | Consumer | Reset | Transported to server? | Returned by server? |
|---|---|---|---|---|---|---|
| `finalTranscript`/`interimTranscript` | Browser/DOM (closure-local) | `absorbResults()` | `finish()`/`finalize()`, `_setAsrInterimPreview` | Per listen session (new closure each call) | No | No |
| `_micListenInFlight` | Client global | `_runChineseMicListen` entry | Same function (guard) | Cleared at function exit | No | No |
| `_challenge.recoveryCount`, `.helpLevel`, `.active` | Client global | Recovery interception, hint clicks, user toggle | Reveal-timing checks (§14) | Per turn (`recoveryCount`/`helpLevel` via `_resetChallengeHelpState`, called at the start of every server turn and on full session reset); `.active` on explicit toggle only — **not reset by persona switch** (confirmed, §14) | No | No |
| `_tracker.recovery_uses`, `.successful_recoveries` | Client global | Recovery interception / panel tap | Session-end telemetry | New session | Yes — as part of session-end payload, not per-turn `conversation_state` | No |
| **`window._consecutiveNotUnderstood`** | Client global, in-memory only | `selectRecoveryPhrase()` increments it (`ui/app.js:2542`) | Recovery-escalation logic client-side | Cleared at many accept/reset sites: `_resetCurrentSessionState()` (`ui/app.js:6439`), matched-speech acceptance, spoken-repeat acceptance, free-answer acceptance | **Not transported** — no reference to sending this field in `conversation_state` was found; it is a purely client-local counter with no server round-trip in either direction | No |
| **`window._recoveryPromptsByFrame`** | Client global, in-memory only | Incremented per-frame when a recovery line is shown (`ui/app.js:8030`) | Per-frame recovery-line display cap | `_resetCurrentSessionState()` (`ui/app.js:6438`); cleared on accept | **Not transported** — no server round-trip found | No |
| **`_challenge.recoveryCount`** | Client global, in-memory only | Recovery interception (`ui/app.js:7735`) / panel tap (`ui/app.js:5406`) | Challenge reveal-timing check (`>= 2`, §14) | `_resetChallengeHelpState()` — start of every server turn, and full session reset | **Not transported** — no `conversation_state`/`state_update` field carries Challenge Mode state in either direction (confirmed by the absence of any such field in §9's payload audit) | No |
| **`_lastAcceptedAsrKey` / `_lastAcceptedAsrTime`** | Client global, in-memory only | Set only within the unmatched free-answer sub-branches of Mechanism 1 (`ui/app.js:7681-7682, 7783-7784`) | Read only within that same branch's dedup check (`ui/app.js:7665-7670`) | Reset to `""`/`0` on new partner-frame render (`ui/app.js:6985`) and on first-time-beta hygiene init (`ui/app.js:617-618`) | **Not transported** — purely client-local | No |
| `conversation_state.last_answer.submitted_text`/`.selected_option_hanzi` | Server-authoritative once sent; client-produced | Client submission (any of Mechanisms 1, 2, or 4) | `_answer_text_from_last_answer`, `_last_text_for_counter`, learner-memory capture, etc. (§10) | Overwritten every turn | **Yes — this is the transport itself** | Not echoed back as a distinct field |
| `answer_text`, `routing_answer_text`, `_last_text_for_counter`, `_routing_last_answer` | Server-local per-request | Derived server-side (§10) | Answer-source/frame-selection pipeline | Recomputed every request; never persisted | No | No |
| **`learner_stated_location`** | `conversation_state`/`state_update`, session-scoped | `_extract_open_world_location(answer_text, ...)` gated on `_RESIDENCE_QUESTION_FRAME_IDS` | Its own carry-forward; `last_place_subject` seeding; diagnostics | Per `docs/STATE_CONTRACT.md`'s exact scope: reset to `""` on **same-tab new session** (`_resetCurrentSessionState()`, `ui/app.js:6463`); reset to `""` on **page reload**, since `window._learnerStatedLocation` is a top-level script variable re-initialised to `""` at script-load time (`ui/app.js:726`); **not reset on persona switch** (confirmed — the persona-button handler, `ui/app.js:4973-4984`, does not touch this variable at all); and, on **normal turn carry-forward**, merge semantics apply — the value is replaced with a freshly extracted location if one is found this turn, or otherwise kept unchanged from the previous turn (per `docs/STATE_CONTRACT.md` row for `learner_stated_location`, and server-side `scripts/ui_server.py:12135` "Replace with new extraction, or keep previous"). This document does **not** claim it "persists indefinitely" beyond this exact, session-scoped, merge-carry-forward behaviour | Yes | Yes, via `state_update` |
| `learner_memory["lives_in"]` | Persistent, cross-session | `learner_memory_capture.capture_from_turn()` on raw `last_answer` fields | Several place-answer construction helpers | Not reset by ASR-pipeline mechanisms; persists across sessions | N/A — persisted server-side | Indirectly, via continuity fields |

**Cross-reference note:** this table intentionally does not redefine the authoritative schema, consumption status, or reset semantics already established in `docs/STATE_CONTRACT.md`; where this document states a reset scope for `learner_stated_location`, it is quoting/confirming that document's row for the field directly, not introducing new scope of its own.

---

## 19. Enforced ASR invariants

### Enforced invariants

* **Client-intercepted recovery sends no server turn**, for Mechanism 1 only (§7, §8) — verified directly; this document no longer generalises this to "typed input" broadly, since Mechanism 2 has no interception concept at all to compare against.
* **Mechanisms 2 and 4 bypass browser ASR entirely** — no code path routes translate-assisted typed input or synthetic test payloads through `SpeechRecognition` (§2, §3); this is a structural absence, not a configuration flag. Mechanism 4 is explicitly not termed a production input mode anywhere in this document (§1).
* **Semantic frame state is preserved during intercepted recovery**, because no request is sent for an intercepted utterance (§7, §8).
* **Duplicate-submission suppression is scoped to exactly one branch.** `_lastAcceptedAsrKey`/`_lastAcceptedAsrTime` are read and written **only** within the unmatched free-answer sub-branches of Mechanism 1's `_runChineseMicListen` (§6, §17, §18) — confirmed by exhaustive grep of both identifiers across `ui/app.js`. This document does **not** claim the guard applies to matched-option submissions, Mechanism 2 (Use-button) submissions, or client-intercepted-recovery non-submissions, since no read or write of either identifier was found in any of those branches.
* **`submitted_text` takes precedence over `selected_option_hanzi`** for the primary `answer_text`/`_last_text_for_counter` derivation (§9, §10) — though `_last_user_text` (§9) is a specific, narrower exception with no fallback at all.
* **Partner TTS is explicitly cancelled before the Chinese-answer mic opens** (`ui/app.js:3563-3567`) — an unconditional call, enforced regardless of whether TTS happens to be playing at that moment (§15).
* **`_joinSegments()`'s return order is `existing + new-remainder-after-overlap-strip` (or `existing + new` with no overlap), with no separator ever inserted** — confirmed exactly (§5); there is no ambiguity remaining between "appended" framing and the literal `b + a` return expression, since `b` is always the existing/previous segment.
* **Filler-only transcripts are rejected before reaching the server**, for Mechanism 1 (§12) — confirmed by direct code trace, not by any mirrored test file.
* **Challenge Mode's Chinese-text hiding and reveal are CSS-driven; its English/pinyin/options hiding is JavaScript-inline-style-driven, with no corresponding CSS rule; and the ASR interim preview and transcript panel are, respectively, entirely unaffected and permanently hidden with no reveal** (§14) — confirmed exhaustively, not left as an open question.
* **`_repair_asr_junk_text()` has 7 call sites with heterogeneous before/after-frame-selection timing** and heterogeneous English/pinyin-recomputation behaviour (§11) — this document does not claim a single uniform timing rule across them.

### Intended contracts with known gaps

* **Spoken and typed text should yield identical semantic routing.** Not fully enforced: §10 establishes that several high-priority classifiers consume **raw** `answer_text` rather than routing-normalised text, regardless of which of Mechanisms 1/2/4 supplied it — meaning a filler-prefixed or oddly-spaced Mechanism-1 utterance can be classified differently by those specific mechanisms than the same text typed via Mechanism 2 without the artefact, since the raw forms differ even though both would normalise to the same routing text.
* **App TTS should never be re-recognised.** Mitigated (cancel-on-open, §15) but not exhaustively guarded against every timing scenario.
* **Every spoken turn should retain raw recogniser evidence.** Not met by default — raw interim/final segment history is discarded once resolved to a single string (§16); no production writer persists a raw-ASR-specific field under any name, confirmed (§16).
* **Recovery counters should round-trip.** `window._consecutiveNotUnderstood`, `window._recoveryPromptsByFrame`, and `_challenge.recoveryCount` are all confirmed purely client-local with **no** server round-trip in either direction (§18) — this is stated definitively now, not as an open question.
* **Output junk repair should keep Chinese/English/pinyin synchronised.** Confirmed at the call-site level (§11): sites 3-4 recompute EN/pinyin in the same block; sites 5-7 (the final-repair pass documented in `docs/ANSWER_SOURCE_CONTRACT.md` §3.3(4)) do **not**, and this is the one specific, named source of potential Chinese/English/pinyin divergence in the whole repair chain.

---

## 20. Extension rules

| Adding/changing a... | Must consider |
|---|---|
| Filler | Visible transcript (should remain unaffected, per §6's established design); Mechanism-1-only scope (Mechanism 2 has no filler stage at all, and any new filler behaviour intended for typed input must be added separately if desired); false-positive risk against legitimate content; which classification function(s) the new filler should be added to; tests — verify any claimed behavioural coverage exercises the real `ui/app.js` function via `_load_app_js_helper.js`, not a mirrored re-implementation (§12); documentation — update §12's inventory table |
| Spoken recovery phrase | Add to `content/recovery_phrases.json`; confirm the build step regenerates the runtime JSON; preserve exact-match behaviour; note explicitly that Mechanism 2 will **never** intercept the same phrase (§8) — confirm server-side handling for that case is acceptable; tests — extend `tests/verify_spoken_recovery_exact_match.js`, understanding it is a mirrored/static test, not a live-code test; documentation — update §7's table |
| `_repair_asr_junk_text()` call site | State explicitly, for the new call site: pipeline phase, input/output values, before/after frame-selection timing, whether EN/pinyin are recomputed in the same block, and whether the value is persisted or transient (§11's per-site table format) — do not assume any of these properties are shared with existing call sites |
| Duplicate-submission guard | If extending the guard to a new branch (e.g. matched-option submissions or the Use-button path), state explicitly that this is a **scope extension**, not a pre-existing behaviour, and update §6, §17, §18, §19 together, since this document currently states the guard's scope as exactly one branch |
| Challenge-mode visibility rule | Decide explicitly whether the new hiding behaviour should be CSS-based (`ui/styles.css`, following the `#frameSentence` pattern with a `.challenge-text-revealed` override) or JS-inline-style-based (following the `#frameEnglish`/options-container pattern with no CSS involvement) — do not leave it ambiguous; update §14's definitive table |
| New request text field | Payload location (root vs. `conversation_state.last_answer`, §9); precedence when it disagrees with existing fields; whether it is populated by Mechanisms 1, 2, and/or 4 identically or divergently — state this explicitly rather than assuming uniformity, per §10's established non-uniformity precedent; tests; documentation — update §9 |
| Production session-capture writer | If a new default-on (not diagnostics-gated) per-turn writer is introduced, update §16 to state its exact trigger condition, persisted fields, and whether client-intercepted recovery turns (which never reach the server) can ever appear in it — currently, no such writer exists, and §16's "no per-turn writer" finding must be revised if one is added |

---

## 21. Known risks

* **Browser-vendor dependence.** Only `SpeechRecognition`/`webkitSpeechRecognition` are checked (§4.1); browsers exposing neither global receive the "not available" fallback with no alternative recognition strategy. *Observed.*
* **Mobile permission and timing differences.** Distinct insecure-origin gate, silence timers, and disabled thinking-grace restart mechanism on mobile (§4.4, §4.5). *Observed.*
* **English-recognizer permission denial is silent.** Confirmed: no message is shown to the learner and no error classification occurs when the auxiliary English recognizer's permission is denied or any other error occurs (§4.3) — a learner attempting Mechanism 3 with microphone access blocked will see the mic button silently return to its idle state with no explanation, whereas the Chinese mic explicitly tells them what went wrong. *Observed, previously misdocumented as identical to the Chinese mic's handling.*
* **Duplicate final transcripts, outside the one guarded branch.** The dedup guard is confirmed scoped to exactly the unmatched free-answer sub-branches of Mechanism 1 (§17, §19) — matched-option submissions, Mechanism 2 submissions, and any future submission branch have no equivalent protection unless separately added. *Observed gap in scope.*
* **TTS feedback into ASR.** Mitigated by cancel-on-open (§15) but not exhaustively guarded against every hardware-echo timing scenario. *Observed partial mitigation; residual risk inferred, not reproduced.*
* **Client/server normalisation divergence.** Two independently-maintained filler-particle definitions can drift out of sync since neither is generated from the other (§12). *Observed.*
* **Exact-match recovery fragility, and total absence for Mechanism 2.** A learner whose phrasing differs even slightly from a phrase-bank entry will not be intercepted via Mechanism 1, and a learner using Mechanism 2 is never eligible for interception regardless of phrasing (§7, §8, §13). *Observed design property, not merely a fragility risk — it is a structural asymmetry between the two production input mechanisms.*
* **Non-uniform classifier text input.** §10's finding that several mechanisms consume raw rather than routing-normalised text applies identically regardless of which of Mechanisms 1/2/4 supplied the text — it is a server-side property, not an artifact of any one input mechanism. *Observed.*
* **Raw transcript loss, and no production `asr_raw`-named field anywhere.** Interim/final segment history is not retained past a single listen session, and no production writer populates a field literally named `asr_raw` under any configuration — confirmed exhaustively (§16). *Observed.*
* **Hidden Challenge-mode transcript still being stored/submitted.** Confirmed for every hidden element except the transcript panel's own display state — nothing prevents the "hidden" partner Chinese/English/options or the learner's own spoken answer from being fully processed and stored (§14). *Observed — by design, but worth flagging.*
* **Post-request-failure silence.** Confirmed: no learner-visible error message exists for a failed `/api/run_turn` request under either input mechanism, and the previously-added transcript entry remains on screen with no indication that the turn did not reach the server (§17). *Observed — a learner could reasonably believe a turn succeeded when it did not.*
* **No production session-capture writer runs by default.** `session_intelligence.py`'s per-session capture is gated off unless `MANDARINOS_SESSION_CAPTURE=1` is explicitly set — in a default deployment, no persistent per-turn ASR-text record exists outside opt-in diagnostics (§16). *Observed.*
* **Test-coverage overstatement risk.** Several test files with ASR-sounding names (`verify_asr_filler.js`, `verify_spoken_recovery_exact_match.js`) are static-source-verification or mirrored-logic tests, not executions of the real shipped `ui/app.js` functions (§12, §24). *Observed* — a reader citing these files as proof of *behavioural* correctness would be overstating their coverage.
* **Late Chinese-only output repair.** Fully documented in `docs/ANSWER_SOURCE_CONTRACT.md` §3.3(4); confirmed at the specific call sites 5-7 in §11 of this document.

---

## 22. Regression diagnosis guide

* **Microphone button does nothing:** check for `SPEECH_NOT_AVAILABLE`/`SPEECH_INSECURE_ORIGIN` traces first (§4.1); then check `_micListenInFlight` is not stuck `true` from a prior unresolved session.
* **Chinese mic permission rejected with a clear message, but the English (translate) mic fails silently:** this is expected, not a bug — confirmed the two recognizers have deliberately different error-handling code (§4.3); if a message is desired for the English recognizer, that requires a new, explicit code change to its `onerror`, not a fix to an existing inconsistency.
* **Recogniser stops immediately:** check `onend` firing with no text and whether the 5-retry empty-result loop is exhausting immediately.
* **Transcript appears twice, or a repeated word appears once at a segment boundary:** check `_joinSegments`'s overlap-stripping (§5) — remember `b` (existing) is always first and `a` (new) is always second in the return value, and the overlap it strips is a **prefix of the new segment matching a suffix of the existing one**, up to 8 characters; a failure to detect a real overlap will show as a doubled word, while an incorrect overlap match will show as a wrongly-truncated new segment.
* **Interim text submits too early:** confirm whether `finish()` was triggered by a timeout while only interim (never final) results had arrived — `getBestTranscript()` can resolve from interim-derived state under timeout, which is expected behaviour, not necessarily a bug.
* **Spoken recovery reaches server unexpectedly:** check whether the phrase's normalised form exactly matches a `content/recovery_phrases.json` entry, and confirm the resolved `recovery_action` was `"repeat"`/`"slower"`/`"meaning"` and not `"next_turn"` (§7).
* **A translate-assisted (Mechanism 2) recovery-phrase-looking submission reaches the server instead of being intercepted:** this is **expected**, not a bug — Mechanism 2 has no interception step at all (§8, §13); if client-side interception is desired for Mechanism 2, it must be newly implemented, not debugged as broken.
* **Typed/translated (Mechanism 2) submission works but the spoken (Mechanism 1) equivalent does not, or vice versa:** check §10's classifier-input table for whether the specific mechanism involved consumes raw `answer_text` (affected by leading filler/spacing artefacts a recognizer might introduce) vs. `_last_text_for_counter` (routing-normalised) — this remains the most likely root cause and applies identically regardless of mechanism, since the divergence is server-side (§10, §13).
* **The same free-answer text submitted twice within a few seconds is (or is not) suppressed:** check whether the submission is actually within the unmatched free-answer branch of Mechanism 1 — this is the **only** branch the dedup guard covers (§17, §19); a matched-option or Mechanism-2 duplicate will **not** be suppressed by this mechanism, and that is expected given the confirmed scope.
* **A learner reports a turn "went nowhere" after speaking or using the Use button:** check for a `UI_ERROR` trace in the developer trace panel — a fetch failure or non-OK response produces no learner-visible message at all, only a trace-panel entry, and the previously-displayed transcript line remains without any failure indication (§17).
* **Challenge Mode: Chinese text won't reveal even after two recovery attempts, but partner English is visible (or vice versa):** these are governed by entirely different mechanisms — Chinese-text reveal is CSS-driven via the `challenge-text-revealed` body class, while English-hiding has no reveal path tied to that class at all (it depends on a separate hint-cascade level); check which specific mechanism governs the element in question using §14's definitive table before assuming a shared bug.
* **Session review / export shows no ASR-specific raw field despite fixture code expecting `asr_raw`:** this is expected — no production writer populates that literal field name under any configuration (§16); the fixture/export tooling supports the field only for hypothetical or test-supplied data.
* **Junk text remains in learner or persona output:** for persona (partner-side) output, check which of the 7 call sites in §11 was or was not exercised for this specific response field (`frame_text` vs. `counter_reply` vs. a slot-substituted `{CITY}`/`{HOMETOWN}` template) — sites 3-4 recompute EN/pinyin, sites 5-7 do not, so the symptom "Chinese was fixed but English/pinyin still shows the junk" specifically implicates sites 5-7.

---

## 23. Related documents

* `docs/CONVERSATION_ARCHITECTURE.md` — overall turn lifecycle, frame selection, E4 end-to-end transport contract.
* `docs/STATE_CONTRACT.md` — authoritative `conversation_state`/`state_update` field schema, including `learner_stated_location`'s exact reset semantics quoted in §18-§19 of this document.
* `docs/ANSWER_SOURCE_CONTRACT.md` — answer-source priority chain, deduplication, and the final ASR-junk output-repair pass (call sites 5-7 in §11 of this document).
* Repository-root `AI_CONTEXT.md` — orientation map for this repository.
* `.cursor/rules/mandarinos-architecture.mdc`, `.cursor/rules/mandarinos-ui-objects.mdc` — standing architectural and UI-object rules applicable to any future change touching the mechanisms this document describes.

No web app manifest or service worker exists in this repository to document (§4.6); no PWA-specific ASR documentation is linked since none applies.

---

## 24. Traceability appendix

| ASR area | Producer | Mechanism scope | Server consumer/repair | Stored form | Representative tests |
|---|---|---|---|---|---|
| Browser recognition lifecycle (Chinese mic) | `listenForResponse()` (`ui/app.js:3545-4002`) | Mechanism 1 only | n/a (client-only until resolved) | On-screen transcript, `last_answer.submitted_text` once submitted | `tests/test_asr_thinking_grace.py` (static), `tests/test_asr_interim_latency.py` (static) |
| Auxiliary English recognition | `ui/app.js:9343-9404` | Mechanism 3 (feeds Mechanism 2) | n/a — feeds `#engInput`, does not itself reach conversation routing | `#engInput` value only | *(no dedicated test file identified)* |
| Translate-assisted typed submission | Use-button handler (`ui/app.js:9414-9430`) | Mechanism 2 | Identical server pipeline to Mechanism 1 once submitted | `last_answer.submitted_text` = translated candidate | *(covered indirectly by any test exercising `runTurn` semantics generally; no dedicated UI-level test file identified for this specific click path)* |
| Synthetic test payloads | Test code directly | Mechanism 4 — explicitly not a production input mode (§1) | Identical server pipeline | n/a — test-local | `tests/test_spoken_chinese_routing.py`, `tests/test_spoken_question_routing_regression.py` (both behavioural, both construct payloads directly rather than exercising client code) |
| Client-intercepted spoken recovery | `matchSpokenRecoveryPhraseExact()` (`ui/app.js:2331-2350`) | Mechanism 1 only — no equivalent for Mechanism 2 | Not reached — no server request | On-screen transcript only | `tests/verify_spoken_recovery_exact_match.js` (hybrid — mirrored matcher + static wiring) |
| Filler classification and rejection | `isIncompleteLearnerUtterance()`, `_isSufficientLinguisticSignal()`, `classifyUnmatchedFreeAnswerDecision()` (§12) | Mechanism 1 only — confirmed no equivalent check exists in the Mechanism 2 Use-button handler | Not reached for a rejected filler-only turn — server never sees it | Local transcript only (client-side recovery UI shown) | `tests/verify_asr_filler.js` (mirrored/static — does **not** execute real `ui/app.js` filler functions; not evidence of server behaviour), `tests/test_asr_filler_suppression.py` (hybrid — static + subprocess) |
| `_joinSegments()` segment assembly | `ui/app.js:3635-3649` | Mechanism 1 only (grace-continuation segments) | n/a | On-screen transcript, submitted text | *(no dedicated behavioural test file identified; covered indirectly by `tests/test_asr_thinking_grace.py`'s static assertions)* |
| Duplicate-submission suppression | `_lastAcceptedAsrKey`/`_lastAcceptedAsrTime` (`ui/app.js:7665-7670, 7681-7682, 7783-7784`) | Confirmed scoped to the unmatched free-answer sub-branches of Mechanism 1 only — not Mechanism 2, not matched-option submissions | n/a — client-only suppression before any request | n/a | *(no dedicated test file identified for this exact guard)* |
| Challenge Mode reveal/hide | `_challenge` object, `_challengeRevealText()`, `ui/styles.css:833-868` (§14) | Applies to the partner's turn regardless of which mechanism produced the learner's own answer | No server-side Challenge Mode field exists (§9) | Not stored — client session state and CSS-class-driven display only | `tests/test_challenge_recovery.py` (mostly static) |
| TTS/mic coordination | `speechSynthesis.cancel()` in `listenForResponse()` (§15) | Mechanism 1 (mic-open trigger); TTS itself plays for any mechanism's accepted answer | n/a | n/a | *(no dedicated test file identified for this specific interaction)* |
| Request construction / field precedence | `conversation_state.last_answer` assembly | All of Mechanisms 1, 2, 4 converge on the same shape | `_answer_text_from_last_answer()`, `_last_user_text` (§9, `scripts/ui_server.py:2620-2627, 10434-10436`) | `conversation_state.last_answer` as sent | *(covered indirectly by any test constructing a payload, e.g. `tests/test_spoken_chinese_routing.py`)* |
| Server routing normalisation | n/a | Applies identically regardless of which mechanism supplied the text | `_normalize_zh_for_routing()` (§10, `scripts/ui_server.py:3753-3766`) | `routing_answer_text`/`_last_text_for_counter`, server-local only | `tests/test_spoken_chinese_routing.py` (behavioural) |
| Server-side ASR/place repair (7 call sites) | n/a | Applies identically regardless of mechanism | `_repair_asr_junk_text()` (7 sites, §11), `_repair_contextual_place_question()`, `_extract_open_world_location()` | Routing text (not persisted) or `learner_stated_location`/memory slots (persisted, per site) | `tests/test_contextual_place_asr_repair.py` (behavioural), `tests/test_open_world_food_and_location_fixes.py` (behavioural) |
| Post-recognition server-failure handling | `runTurn()`/`_runTurnInner()` fetch/catch logic (`ui/app.js:6777-6809`, §17) | Shared identically by Mechanisms 1 and 2 | n/a — client-side only; server never receives a malformed request in this scenario, the request simply fails to complete | User transcript entry remains; no failure record persisted anywhere | *(no dedicated test file identified for this exact failure path)* |
| Production session-capture / diagnostics | `session_intelligence.py` (opt-in), `_diag_cap` (opt-in), `selector_trace` (response-only, not persisted) (§16) | Applies to any mechanism's text, when enabled | `_diag_cap` capture (`scripts/ui_server.py:9236-9275`), offline joining via `scripts/report_asr_traces.py` | Diagnostics JSONL records, when enabled; session JSON, when `MANDARINOS_SESSION_CAPTURE=1` | `tests/test_report_asr_traces.py` (behavioural) |
| Session review export | n/a | n/a | n/a | Export batch text; `asr_raw` supported only as a pass-through/fixture field, never produced by a production writer (§16) | `tests/test_export_session_review_prompt.py` (behavioural, tangential to ASR) |
| Manifest / service worker | n/a — confirmed absent (§4.6) | n/a | n/a | n/a | *(no test file applicable — no such artifact exists to test)* |

**Baseline commit:** `3be0315b2c9f7316b03ac2183a887f602ae9a297`
**Baseline tag:** `architecture-baseline-2026-07-12-r2`
**Documentation branch:** `docs/architecture-v1`
**Document status:** Candidate v1 — R2 final review
**Last verified date:** 2026-07-12
