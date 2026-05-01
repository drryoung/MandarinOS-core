// ui/ttsSpeak.js
// Single boundary for TTS (browser SpeechSynthesis for now).
// IMPORTANT: This is a side-effect module. Reducers must never call this.
// Emits MandarinOS trace entries: { type, timestamp, payload }

/**
 * iOS Safari requires speechSynthesis.speak() to be called synchronously
 * within a user-gesture call stack. Any await (e.g. a fetch) breaks the
 * gesture chain and iOS silently drops subsequent speak() calls.
 *
 * Call ttsUnlock() synchronously at the top of every click handler that will
 * later call ttsSpeak() after an async gap. The zero-length utterance primes
 * the synthesiser inside the gesture window; real speech then works after
 * the await completes.
 *
 * Safe to call on non-iOS browsers — it is a no-op if speech is already
 * unlocked or if SpeechSynthesis is unavailable.
 */
export function ttsUnlock() {
  if (typeof window === "undefined" || !window.speechSynthesis || !window.SpeechSynthesisUtterance) return;
  // Only unlock once per page load — subsequent calls are free no-ops.
  if (window._ttsUnlocked) return;
  try {
    const u = new SpeechSynthesisUtterance("");
    u.volume = 0;
    u.lang = "zh-CN";
    window.speechSynthesis.speak(u);
    window._ttsUnlocked = true;
  } catch (_) {}
}

/**
 * @param {object} opts
 * @param {string} opts.text
 * @param {string} [opts.lang]
 * @param {number} [opts.rate]
 * @param {boolean} [opts.queue] - If true, do not cancel current speech (for chaining).
 * @param {function} [opts.onEvent]
 * @param {string} [opts.utterance_id]
 */
export function ttsSpeak({ text, lang = "zh-CN", rate, queue, onEvent, utterance_id }) {
  const nowIso = () => new Date().toISOString();

  if (!text || typeof text !== "string") {
    onEvent?.({
      type: "AUDIO_ERROR",
      timestamp: nowIso(),
      payload: { utterance_id, error: "No text provided to ttsSpeak()" },
    });
    return;
  }

  if (typeof window === "undefined" || !window.speechSynthesis || !window.SpeechSynthesisUtterance) {
    onEvent?.({
      type: "AUDIO_ERROR",
      timestamp: nowIso(),
      payload: { utterance_id, error: "SpeechSynthesis not available in this browser" },
    });
    return;
  }

  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang;
  if (typeof rate === "number" && rate > 0 && rate <= 2) {
    u.rate = rate;
  }

  let startMs = null;

  u.onstart = () => {
    startMs = Date.now();
    onEvent?.({
      type: "AUDIO_PLAYED",
      timestamp: nowIso(),
      payload: { utterance_id, duration_ms: 0, completed: false },
    });
  };

  u.onerror = (e) => {
    onEvent?.({
      type: "AUDIO_ERROR",
      timestamp: nowIso(),
      payload: { utterance_id, error: String(e?.error || e?.message || "unknown") },
    });
  };

  u.onend = () => {
    const duration = startMs ? Math.max(0, Date.now() - startMs) : 0;
    onEvent?.({
      type: "AUDIO_PLAYED",
      timestamp: nowIso(),
      payload: { utterance_id, duration_ms: duration, completed: true },
    });
  };

  if (!queue) {
    try {
      window.speechSynthesis.cancel();
    } catch (_) {}
  }
  window.speechSynthesis.speak(u);
}
