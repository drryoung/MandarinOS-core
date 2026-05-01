# Phase 7 completion — how to review and test

Use this when you start again to check that the Phase 7 directives were implemented as you hoped.

---

## What was implemented

1. **"You said" confirmation** — After you select a response option, the UI shows a line like **"You said: [the text you chose]"**. That text is also stored in a **transcript array** (for Phase 8) so the data structure is ready for the conversation loop UI.
2. **Play question (TTS)** — A **"Play question"** button under the frame sentence. Clicking it speaks the current question (the frame sentence) aloud so you can hear it before answering.

---

## Before you start

1. From the repo root, start the UI server:
   ```text
   python -m scripts.ui_server
   ```
2. In your browser, open: **http://localhost:8765/ui/index.html**  
   (If the server prints a different port, use that instead.)
3. Make sure a frame is loaded (the Frame dropdown should list frames like `p1_identity :: frame_...`). If it’s empty, the pack files may not be loading; check the server console for errors.

---

## Mobile / LAN testing (e.g. iPhone on same Wi‑Fi)

- You can open the UI from a phone using **`http://<laptop-LAN-IP>:8765`** (same paths as on desktop, e.g. `/ui/index.html`). The dev server binds so it is reachable on the LAN; use your laptop’s IPv4 address from `ipconfig` / System Settings.
- **Microphone / speech input does not work** when the page is loaded as **plain HTTP to a LAN IP**. Browser speech APIs (`SpeechRecognition` / Web Speech API) require a [**secure context**](https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts) (`https:` or special cases like `localhost`). **`http://192.168.x.x` is not a secure context** on iPhone Safari. **This is treated as a browser/environment constraint for alpha, not as an app bug.**
- **Typed-input mobile testing** (tapping options, English → Chinese field, etc.) **remains fully valid** without HTTPS or extra setup.

To exercise speech input from a phone later, serve the same UI over **HTTPS** to the device (e.g. reverse proxy with TLS, dev certificate, or tunnel)—out of scope for this note.

---

## Test 1: Play question (TTS)

**Goal:** The current question can be heard via a single click.

1. In the **Frame** dropdown, select any frame.
2. Click **Run Turn**.
3. You should see the **frame sentence** (the question) appear in Chinese, and a **"Play question"** button below it.
4. Click **Play question**.
5. **Expected:** The sentence is spoken aloud (TTS). If your system has no Chinese TTS or sound is off, you may hear nothing—but the button should not cause an error.
6. **Check:** In the Trace area at the bottom, you should see an event like `AUDIO_PLAY_REQUESTED` with `"source": "play_question"` after you click.

**Pass:** You see the button, clicking it triggers speech (or at least no error), and the trace shows the play-request event.

---

## Test 2: "You said" confirmation

**Goal:** After you choose an option, the UI confirms what you “said” and that text is stored for Phase 8.

1. With the same or any frame, click **Run Turn** so the frame sentence and response options appear.
2. Click **Try responding →** so the option buttons are active (not greyed out).
3. Click **one of the response options** (e.g. an answer in Chinese).
4. **Expected:**  
   - A line appears below the frame sentence area: **"You said: [the Chinese text of the option you chose]"**.  
   - The option you clicked is visually marked as selected (e.g. highlighted).
5. Click **Run Turn** again (same or different frame).
6. **Expected:** The **"You said"** line disappears (or clears) for the new question. You can select another option and see "You said" update again.

**Pass:** Selecting an option shows "You said: [text]"; starting a new turn clears that line.

---

## Test 3: Transcript array (for Phase 8)

**Goal:** Confirm that your choices are being stored so Phase 8 can use them for the full conversation transcript.

This step is optional and uses the browser console (F12 or right‑click → Inspect → Console).

1. After you have selected at least one option (so "You said" has appeared at least once), open the browser **Developer Tools** (F12) and go to the **Console** tab.
2. In the console, type:
   ```text
   conversationTranscript
   ```
   and press Enter.  
   (If that shows "not defined", the app may not expose it globally; in that case skip this test—the implementation may still store it internally for Phase 8.)
3. **Expected:** You see an array of objects, e.g. `[{ role: "user", text: "我叫..." }, ...]`. Each time you selected an option, one more `role: "user"` entry should appear with the text you chose.

**Pass:** The array exists and contains one entry per option you selected (with `role: "user"` and the correct `text`), or you’ve confirmed with the developer that the transcript is stored internally for Phase 8.

---

## Quick checklist (when you start again)

- [ ] Server runs and UI loads at http://localhost:8765/ui/index.html (or the port shown).
- [ ] **Play question:** Button is visible; clicking it speaks the frame sentence (or trace shows `AUDIO_PLAY_REQUESTED` with `source: "play_question"`).
- [ ] **"You said":** Selecting an option shows "You said: [chosen text]"; running a new turn clears it.
- [ ] (Optional) **Transcript:** In console, `conversationTranscript` (or equivalent) holds `{ role: "user", text: "..." }` entries for Phase 8.

---

## If something doesn’t match

- **No "Play question" button:** Check that you’re on the latest `ui/index.html` and `ui/app.js` (Phase 7 completion edits are in those two files only).
- **"You said" never appears:** Make sure you clicked **Try responding →** before clicking an option, and that the option has text (hanzi).
- **Transcript not in console:** The transcript may be internal to the app; Phase 8 will still be able to use it if the implementation stores it in the same `app.js` module. You can ask Cursor to confirm where `conversationTranscript` is used and whether it’s exposed for debugging.

When in doubt, you can ask ChatGPT (strategist) to review the Phase 7 completion against the project plan and this guide, and ask Cursor to confirm the implementation matches the two Phase 7 directives (You said + Play question) and the transcript data structure for Phase 8.
