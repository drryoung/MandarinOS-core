#!/usr/bin/env python3
"""Mobile conversation-first layout — wiring checks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_UI = ROOT / "ui"


def test_mobile_breakpoint_in_styles():
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    assert "@media (max-width: 768px)" in css
    assert ".mobile-right-sheet" in css
    assert "#cardPanel" in css
    assert "max-height: 52vh" in css


def test_mobile_html_structure():
    html = (_UI / "index.html").read_text(encoding="utf-8")
    assert 'id="mobileRightSheet"' in html
    assert 'id="mobilePanelFab"' in html
    assert 'id="mobileSheetBackdrop"' in html
    assert 'id="mobileSheetClose"' in html


def test_mobile_js_wiring():
    src = (_UI / "app.js").read_text(encoding="utf-8")
    assert "initMobileLayout" in src
    assert "_isMobileLayout" in src
    assert "_syncMobileCardSheet" in src
    assert "_setConversationActive" in src
    assert "card-sheet-open" in src
    assert "conversation-active" in src
    assert "session-ended" in src
    assert "mobile-guide-collapsed" in src
    assert "_dismissMobileGuidePeek" in src


def test_mobile_guide_collapse_in_styles():
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    assert "mobile-guide-collapsed" in css


def test_mobile_button_density_in_styles():
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    assert "Mobile button density" in css
    assert "min-height: 38px" in css
    assert "min-height: 42px" in css


def test_mobile_transcript_does_not_steal_viewport():
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    html = (_UI / "index.html").read_text(encoding="utf-8")
    assert "min(40vh, 280px)" not in css
    assert "min(40vh, 280px)" not in html
    assert "min(20vh, 112px)" in css
    assert "body.conversation-active .transcript-panel" in css
    mobile = css.split("@media (max-width: 768px)")[1]
    assert "body.conversation-active .controls" in css
    assert "body.conversation-active .controls #runBtn" in css


def test_mobile_session_controls_stay_reachable():
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    src = (_UI / "app.js").read_text(encoding="utf-8")
    hidden = css.split("body.conversation-active .controls .frame-label")[1].split("body.conversation-active .remembered-facts")[0]
    assert "#runBtn" in hidden
    assert "#nextBtn" not in hidden
    assert "#endSessionBtn" not in hidden
    assert "#changeTopicBtn" not in hidden
    assert "_scrollSetupChromeAwayIfMobile" not in src
    assert "interimTranscript" in src
    assert "getBestTranscript" in src
    assert "isMobileListen" in src
    assert "rec.continuous = !isMobileListen" in src


def test_recovery_collapsed_on_mobile():
    src = (_UI / "app.js").read_text(encoding="utf-8")
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    assert "recovery-panel-collapsible" in src
    assert "is-listening" in src
    assert "body.is-listening .current-turn-options" in css
    assert "_micListenArmedAt" in src


def test_active_turn_split_scroll():
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    html = (_UI / "index.html").read_text(encoding="utf-8")
    src = (_UI / "app.js").read_text(encoding="utf-8")
    assert ".current-turn-focus" in css
    assert ".current-turn-options" in css
    assert ".active-partner-stack" in css
    assert 'class="current-turn-options"' in html
    assert 'class="active-partner-stack"' in html
    assert "_scrollOptionsIntoViewIfDesktop" in src


def test_active_turn_hides_partner_header():
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    src = (_UI / "app.js").read_text(encoding="utf-8")
    assert ".current-turn #partnerHeader" in css
    assert "_syncActiveEnglishDisplay" in src
    assert 'header.style.display = "none"' in src


def test_empty_mic_does_not_trigger_recovery():
    src = (_UI / "app.js").read_text(encoding="utf-8")
    assert "SPEECH_EMPTY_NO_RECOVERY" in src
    assert "SPEECH_MIN_LISTEN_GRACE_MS_MOBILE" in src
    assert "onend empty" in src
    assert "_runChineseMicListen" in src
    assert "finishReason" in src
    assert "_showListenNotice" in src
    assert "Listening…" in src


def test_listen_status_below_mics():
    html = (_UI / "index.html").read_text(encoding="utf-8")
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    mics = html.split('class="current-turn-mics"')[1][:600]
    assert mics.index('id="actionLadder"') < mics.index("listenStatus")
    assert 'data-state="notice"' in css
    assert "background:" not in css.split(".listen-status[data-state=\"listening\"]")[1].split("}")[0]


def test_mobile_no_auto_explore_word_open():
    src = (_UI / "app.js").read_text(encoding="utf-8")
    assert "_closeExploreWordPanelIfMobile" in src
    assert "if (data.card_id && _shouldAlsoOpenCardPanel())" in src
    assert "opt.card_id && opt.kind !== \"FRAME_WITH_SLOTS\" && _shouldAlsoOpenCardPanel()" in src
    assert "matchedOption.card_id && matchedOption.kind !== \"FRAME_WITH_SLOTS\" && _shouldAlsoOpenCardPanel()" in src
    html = (_UI / "index.html").read_text(encoding="utf-8")
    assert "frame-sentence-actions" in html
    assert html.count('id="reverseActionsRow"') == 1


def test_header_hides_when_session_active():
    """The page header (starting-point-bar + persona-bar) must be hidden on mobile
    once a session is running so the conversation area gets maximum vertical space."""
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    # Rule must exist inside the mobile media-query section (after the 768px breakpoint)
    mobile_section = css.split("@media (max-width: 768px)")[1]
    assert "body.conversation-active header" in mobile_section
    assert "display: none" in mobile_section.split("body.conversation-active header")[1].split("}")[0]


def test_speaker_hint_buttons_inline_with_chinese():
    """🔊 and ? buttons must live inside a .frame-sentence-row wrapper so they
    appear on the same visual row as the partner Chinese text, not a separate row below."""
    html = (_UI / "index.html").read_text(encoding="utf-8")
    # Capture content between frame-sentence-row opening and its closing tag
    row_start = html.index('class="frame-sentence-row"')
    row_block = html[row_start:row_start + 600]
    assert 'id="frameSentence"' in row_block
    assert 'class="frame-sentence-actions"' in row_block
    css = (_UI / "styles.css").read_text(encoding="utf-8")
    assert ".active-partner-stack .frame-sentence-row" in css


def test_start_button_reappears_after_end_session():
    """endSession() must remove conversation-active so the Start/Frame controls
    are not permanently hidden by the mobile CSS rule."""
    src = (_UI / "app.js").read_text(encoding="utf-8")
    # Find endSession function body
    end_fn = src.split("async function endSession()")[1].split("\nwindow.endSession")[0]
    assert 'classList.remove("conversation-active")' in end_fn
