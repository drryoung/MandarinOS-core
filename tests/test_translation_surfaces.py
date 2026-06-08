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
    assert "function _initActiveTurnRecord" in src
    assert "function _refreshActiveDisplayFromTurnRecord" in src


def test_active_turn_record_is_single_source_of_truth():
    """Every path that sets the active sentence must go through _initActiveTurnRecord."""
    src = _src()
    # Stub path (direction/mirror/probe) must use _initActiveTurnRecord, not raw _sentenceHint
    stub_block = src.split("function applyPartnerStubToActiveSentence")[1].split("function runDirectionTurn")[0]
    assert "_initActiveTurnRecord(" in stub_block
    assert "window._sentenceHint = {" not in stub_block
    # Discovery card ack handler must use _initActiveTurnRecord
    disc_block = src.split("function renderDiscoveryPanel")[1].split("function hideDiscoveryPanel")[0]
    assert "_initActiveTurnRecord(" in disc_block
    # Continue → handler must use _initActiveTurnRecord
    cont_idx = src.rfind("继续聊  Continue →")
    assert cont_idx >= 0
    cont_block = src[cont_idx : cont_idx + 900]
    assert "_initActiveTurnRecord(" in cont_block


def test_active_turn_record_prevents_stale_gloss():
    """Async gloss must update _activeTurnRecord before re-rendering EN."""
    src = _src()
    sync_block = src.split("function _syncActiveEnglishFromGloss")[1].split("function _refreshActiveEnglishFromSentenceHint")[0]
    assert "_updateActiveTurnRecordEn(en)" in sync_block
    assert "entryKey !== recordKey" in sync_block or "entryKey !== recordKey && entryKey !== activeKey" in sync_block


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


def test_progress_recovery_display_uses_interpretation_labels():
    """Progress Recovery column uses interpretation labels, not 'Not needed'."""
    src = _src()
    assert "Self-recovered" in src
    assert "Stayed on track" in src
    assert "Not needed" not in src


def test_spoken_register_pairs_in_vocab_and_naturalizer():
    src = _src()
    for formal, spoken in [
        ("同住", "一起住"),
        ("居住", "住"),
        ("您", "你"),
        ("与", "跟"),
        ("共同", "一起"),
    ]:
        assert f'["{formal}",' in src or f'["{formal}", ' in src
        assert f'"{spoken}"' in src
    assert "function _normalizeSpokenRegister" in src
    assert "..._SPOKEN_REGISTER_PAIRS" in src


def test_spoken_register_normalization_logic():
    """Mirror split/join register normalization used in app.js."""

    def normalize(text):
        pairs = [
            ("同住", "一起住"),
            ("居住", "住"),
            ("共同", "一起"),
            ("您", "你"),
            ("与", "跟"),
        ]
        s = text
        for formal, spoken in pairs:
            s = spoken.join(s.split(formal))
        return s

    assert normalize("您与爸爸妈妈同住吗？") == "你跟爸爸妈妈一起住吗？"
    assert normalize("您居住在这里") == "你住在这里"
    assert normalize("我们共同生活") == "我们一起生活"


def test_translation_overrides_spoken_questions():
    src = _src()
    overrides = {
        "do you live with your parents": "你跟爸妈一起住吗？",
        "do you live with your family": "你跟家人一起住吗？",
        "do you live alone": "你一个人住吗？",
        "are you married": "你结婚了吗？",
        "do you have children": "你有孩子吗？",
    }
    for key, zh in overrides.items():
        assert f'"{key}"' in src
        assert f'"{zh}"' in src


def test_client_matching_applies_spoken_register():
    src = _src()
    assert "function normalizeForMatch" in src
    assert "_normalizeSpokenRegister(s.trim())" in src
    nf_block = src.split("function normalizeForMatch")[1].split("function isIncompleteLearnerUtterance")[0]
    assert "_normalizeSpokenRegister" in nf_block
    sm_block = src.split("function semanticSoftMatch")[1].split("function shouldAcceptUnmatchedFreeAnswer")[0]
    assert "_normalizeSpokenRegister" in sm_block


def test_progress_sync_does_not_touch_conversation_dom():
    """renderProgressView must only touch #progressView; server sync must not mutate conversation state."""
    src = _src()
    # renderProgressView scoped to progressView element only
    rv_block = src.split("function renderProgressView")[1].split("\nfunction ")[0]
    assert 'getElementById("progressView")' in rv_block
    # renderProgressView must NOT touch conversation-critical elements
    for bad in ("chatHistory", "transcriptPanel", "optionsContainer", "sentenceOptionsContainer", "_activeTurnRecord"):
        assert bad not in rv_block, f"renderProgressView must not touch {bad!r}"
    # _syncServerProgressIfEmpty must call renderProgressView, not touch conversation DOM
    sync_block = src.split("async function _syncServerProgressIfEmpty")[1].split("\nasync function ")[0]
    assert "renderProgressView()" in sync_block
    assert "_activeTurnRecord" not in sync_block


def test_dedupe_progress_snapshots_function_exists():
    """_dedupeProgressSnapshots must exist and be used inside saveProgressSnapshot."""
    src = _src()
    assert "function _dedupeProgressSnapshots" in src
    save_block = src.split("function saveProgressSnapshot")[1].split("\nfunction ")[0]
    assert "_dedupeProgressSnapshots" in save_block


def test_end_session_button_disabled_during_save():
    """endSession must disable #endSessionBtn before the fetch to prevent double-submission."""
    src = _src()
    end_block = src.split("async function endSession")[1].split("\nwindow.endSession")[0]
    assert "endSessionBtn" in end_block
    assert "_btn.disabled = true" in end_block
    assert "Saving" in end_block


def test_beforeunload_guard_exists():
    """beforeunload handler must be registered and conditioned on conversation-active."""
    src = _src()
    assert 'addEventListener("beforeunload"' in src
    bl_block = src.split('addEventListener("beforeunload"')[1][:300]
    assert "conversation-active" in bl_block


def test_curated_response_patterns_unchanged():
    """Curated JSON content must not be modified by this layer."""
    patterns = (ROOT / "content" / "response_patterns.json").read_text(encoding="utf-8")
    assert "我跟家人一起住" in patterns
    assert "是的，住在一起" in patterns
    frames = (ROOT / "p2_frames.json").read_text(encoding="utf-8")
    assert "你跟家人住在一起吗？" in frames
