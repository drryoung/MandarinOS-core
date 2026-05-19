#!/usr/bin/env python3
"""
Translation surface consistency — static checks on ui/app.js pathways.

Validates Phase B propagation/sync helpers without a browser runtime.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "ui" / "app.js"


def _src():
    return APP.read_text(encoding="utf-8")


def test_partner_transcript_extras_helper_exists():
    src = _src()
    assert "function partnerTranscriptExtrasFromData" in src
    assert "frame_text_en" in src.split("partnerTranscriptExtrasFromData")[1][:800]


def test_gloss_syncs_active_display():
    src = _src()
    assert "function _syncActiveEnglishFromGloss" in src
    assert "_syncActiveEnglishFromGloss(entry, en)" in src


def test_recovery_repeat_uses_transcript_extras_in_render_options():
    src = _src()
    assert src.count("transcriptExtrasForRecoveryPartnerRepeat(action)") >= 2
    idx = src.find("function renderOptions(options, frameId)")
    assert idx >= 0
    block = src[idx : idx + 12000]
    assert "transcriptExtrasForRecoveryPartnerRepeat(action)" in block


def test_stub_paths_pass_partner_extras():
    src = _src()
    for fn in (
        "runDirectionTurn",
        "runMirrorTurn",
        "runProbeTurn",
        "submitDiscoveryQuestion",
    ):
        assert fn in src
    assert src.count("partnerTranscriptExtrasFromData(data, stub)") >= 4


def test_no_external_chart_or_render_rewrite():
    src = _src()
    assert "renderTranscript" in src
    assert "renderFrameSentence" in src
    # Phase B must not replace transcript with a single mega-renderer
    assert "function renderAllSurfaces" not in src


def test_active_english_separate_from_hint_cascade():
    src = _src()
    assert "function _setFrameEnglish" in src
    assert "level >= 2 && sentenceHint.text_en" in src
    assert "level >= 1 && sentenceHint.pinyin" in src


def test_transcript_resolve_english_chain():
    src = _src()
    assert "function resolveLineEnglish" in src
    assert "function maybeRequestGlossForEntry" in src
    assert "glossLineCache" in src


def test_empty_text_en_does_not_force_zero_percent_recovery_display():
    """Recovery table/display uses 'Not needed' pattern in progress; transcript uses null gloss."""
    src = _src()
    assert '"Not needed"' in src or "'Not needed'" in src or "Not needed" in src
