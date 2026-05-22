#!/usr/bin/env python3
"""ASR filler suppression — client wiring and regression checks."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_UI = ROOT / "ui"
_VERIFY_JS = Path(__file__).resolve().parent / "verify_asr_filler.js"


def _app_src() -> str:
    return (_UI / "app.js").read_text(encoding="utf-8")


def test_filler_helpers_present_in_app_js():
    src = _app_src()
    assert "_FILLER_CHAR_SET" in src
    assert "_isPureFillerUtterance" in src
    assert "_isSufficientLinguisticSignal" in src
    assert "insufficient_linguistic_signal" in src
    assert "SPEECH_FILLER_EXTEND_MS" in src
    assert "fillerExtendFired" in src


def test_classify_inserts_signal_check_before_no_options():
    src = _app_src()
    block = src.split("function classifyUnmatchedFreeAnswerDecision")[1].split("function listenForResponse")[0]
    sig_idx = block.index("insufficient_linguistic_signal")
    no_opts_idx = block.index('reason: "no_options"')
    assert sig_idx < no_opts_idx


def test_verify_asr_filler_js_passes():
    result = subprocess.run(
        ["node", str(_VERIFY_JS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
