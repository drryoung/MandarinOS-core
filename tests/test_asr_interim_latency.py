#!/usr/bin/env python3
"""Static regression checks for desktop ASR latency fix (interim preview + single-utterance)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_APP = ROOT / "ui" / "app.js"
_CSS = ROOT / "ui" / "styles.css"


def _app_src():
    return _APP.read_text(encoding="utf-8")


def test_desktop_recognition_continuous_false():
    """1. Desktop (and all platforms) use single-utterance recognition."""
    src = _app_src()
    assert "rec.continuous = false" in src
    assert "rec.continuous = !isMobileListen" not in src


def test_interim_preview_helpers_exist():
    """2. Interim preview helpers render provisional text in #listenStatus."""
    src = _app_src()
    assert "_setAsrInterimPreview" in src
    assert "_clearAsrInterimPreview" in src
    assert "_refreshListenStatusWithPreview" in src
    assert "asr-interim-preview" in src
    assert "asr-preview-interim" in src
    assert "asr-preview-final" in src


def test_interim_rendered_in_absorb_results_not_transcript():
    """2–4. Interim text is shown during listen; not written via addTranscriptEntry."""
    block = _app_src().split("function absorbResults")[1].split("function resetSilenceTimer")[0]
    assert "_setAsrInterimPreview" in block
    assert "addTranscriptEntry" not in block


def test_final_replaces_interim_preview():
    """3. Final transcript updates the preview with isFinal styling."""
    block = _app_src().split("function absorbResults")[1].split("function resetSilenceTimer")[0]
    assert "isFinal: !!finalTranscript" in block or "isFinal: !!finalTranscript" in block.replace(" ", "")
    assert '{ isFinal: !!finalTranscript }' in block


def test_finish_clears_interim_preview():
    """4. Provisional preview cleared when listen cycle completes."""
    finish_block = _app_src().split("function finish(reason)")[1].split("function absorbResults")[0]
    assert "_clearAsrInterimPreview" in finish_block


def test_single_utterance_finish_uses_stop_not_abort_only():
    """2. Browser onend path uses stop + short delay so finals arrive (all platforms)."""
    finish_block = _app_src().split("function finish(reason)")[1].split("function absorbResults")[0]
    assert "rec.stop()" in finish_block
    assert "setTimeout(finalize, 250)" in finish_block
    assert "if (isMobileListen)" not in finish_block.split("rec.stop()")[0].split("const finalize")[1]


def test_run_turn_only_after_listen_resolves():
    """5. runTurn is not called inside listenForResponse (only final path in mic handler)."""
    listen_block = _app_src().split("function listenForResponse")[1].split("}\n\n// Segments for")[0]
    assert "runTurn(" not in listen_block
    assert "resolve({" in listen_block


def test_empty_mic_does_not_add_transcript_in_listen_for_response():
    """6. Empty recognition resolves empty transcript without addTranscriptEntry in listenForResponse."""
    listen_block = _app_src().split("function listenForResponse")[1].split("}\n\n// Segments for")[0]
    assert "addTranscriptEntry" not in listen_block


def test_duplicate_suppression_unchanged():
    """7. ASR duplicate suppression keys still present in mic handler."""
    mic_block = _app_src().split("async function _runChineseMicListen")[1].split("const tryRespondingBtnEl")[0]
    assert "_lastAcceptedAsrKey" in mic_block
    assert "_lastAcceptedAsrTime" in mic_block


def test_mobile_listen_path_preserved():
    """8. Mobile-specific synchronous start and isMobileListen checks remain."""
    src = _app_src()
    assert "if (isMobileListen)" in src
    assert "beginListening();" in src
    assert "setTimeout(beginListening, 380)" in src


def test_perf_logging_gated_behind_diagnostics():
    """Instrumentation: [ASR-PERF] only when AsrDiag.enabled()."""
    perf_block = _app_src().split("const _perfLog = (label) => {")[1].split("const preSpeechSilenceMs")[0]
    assert "AsrDiag.enabled()" in perf_block


def test_interim_preview_css():
    css = _CSS.read_text(encoding="utf-8")
    assert ".asr-interim-preview" in css
    assert ".asr-preview-interim" in css
    assert ".asr-preview-final" in css
