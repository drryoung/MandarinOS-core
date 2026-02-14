// ui/ttsSpeak.js
// Single boundary for TTS (browser SpeechSynthesis for now).
// IMPORTANT: This is a side-effect module. Reducers must never call this.
// Emits MandarinOS trace entries: { type, timestamp, payload }

export function ttsSpeak({ text, lang = "zh-CN", onEvent, utterance_id }) {
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

  try {
    window.speechSynthesis.cancel();
  } catch (_) {}

  window.speechSynthesis.speak(u);
}
