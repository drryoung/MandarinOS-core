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
