"""
tests/test_challenge_recovery.py

Regression tests for recovery phrase handling in challenge mode.

Evidence: session_1782704586839 showed 再说一遍 / 不明白 falling through to
generic uncertainty or advancing to a different frame.

Fixes:
  1. Server: _REPEAT_REQUEST_MARKERS + _is_rr short-circuit → always routes
     再说一遍 / 慢一点 / bare 什么意思 to _clarify_app_question regardless of
     _prev_counter_reply.
  2. Client: spoken recovery intercept before classifyUnmatchedFreeAnswerDecision
     → simulates recovery panel tap; frame never advances for repeat/slower/meaning.

Covers:
  - 再说一遍 — explicit repeat request
  - 慢一点说 — slow-down request
  - 我不明白 — confusion signal
  - 什么意思 — meaning query (short standalone form)
"""
import json
import pathlib
import pytest

REPO = pathlib.Path(__file__).parent.parent
UI_SERVER_PATH = REPO / "scripts" / "ui_server.py"
APP_JS_PATH = REPO / "ui" / "app.js"


@pytest.fixture(scope="module")
def server_src():
    return UI_SERVER_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_js_src():
    return APP_JS_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. _REPEAT_REQUEST_MARKERS constant defined at module level
# ---------------------------------------------------------------------------

def test_repeat_request_markers_defined(server_src):
    """_REPEAT_REQUEST_MARKERS tuple must be defined at module level."""
    assert "_REPEAT_REQUEST_MARKERS" in server_src


def test_repeat_request_markers_contains_zai_shuo(server_src):
    """再说一遍 must be in _REPEAT_REQUEST_MARKERS."""
    idx = server_src.find("_REPEAT_REQUEST_MARKERS")
    assert idx != -1
    block = server_src[idx: idx + 400]
    assert "再说一遍" in block


def test_repeat_request_markers_contains_man_yi_dian(server_src):
    """慢一点 must be in _REPEAT_REQUEST_MARKERS."""
    idx = server_src.find("_REPEAT_REQUEST_MARKERS")
    assert idx != -1
    block = server_src[idx: idx + 400]
    assert "慢一点" in block


def test_repeat_request_markers_contains_qing_zai_shuo(server_src):
    """请再说 must be in _REPEAT_REQUEST_MARKERS."""
    idx = server_src.find("_REPEAT_REQUEST_MARKERS")
    assert idx != -1
    block = server_src[idx: idx + 400]
    assert "请再说" in block


# ---------------------------------------------------------------------------
# 2. _is_rr short-circuit in counter-reply block
# ---------------------------------------------------------------------------

def test_is_rr_computed_in_counter_reply_block(server_src):
    """_is_rr must be computed inside the counter-reply block."""
    assert "_is_rr" in server_src


def test_is_rr_uses_repeat_request_markers(server_src):
    """_is_rr must reference _REPEAT_REQUEST_MARKERS."""
    idx = server_src.find("_is_rr")
    assert idx != -1
    block = server_src[idx: idx + 200]
    assert "_REPEAT_REQUEST_MARKERS" in block


def test_is_rr_handles_short_shenme_yisi(server_src):
    """_is_rr must also catch short (≤5 chars) 什么意思 utterances."""
    idx = server_src.find("_is_rr")
    assert idx != -1
    block = server_src[idx: idx + 400]
    assert "什么意思" in block
    # Should use a length guard
    assert "len(" in block or "strip()" in block


def test_is_rr_routes_to_clarify_app_question(server_src):
    """When _is_rr is True, server must call _clarify_app_question."""
    idx = server_src.find("if _is_rr:")
    assert idx != -1, "'if _is_rr:' block not found"
    block = server_src[idx: idx + 300]
    assert "_clarify_app_question" in block


def test_is_rr_sets_confusion_about_app_q(server_src):
    """_is_rr block must set _confusion_about_app_q = True."""
    idx = server_src.find("if _is_rr:")
    assert idx != -1
    block = server_src[idx: idx + 500]
    assert "_confusion_about_app_q = True" in block


def test_is_rr_uses_last_partner_frame_text(server_src):
    """_is_rr block must read cs.last_partner_frame_text to re-ask the question."""
    idx = server_src.find("if _is_rr:")
    assert idx != -1
    block = server_src[idx: idx + 300]
    assert "last_partner_frame_text" in block


def test_is_rr_short_circuits_before_lex_ct(server_src):
    """_is_rr block must appear BEFORE the _lex_ct check (elif _lex_ct must follow)."""
    is_rr_idx = server_src.find("if _is_rr:")
    lex_ct_idx = server_src.find("elif _lex_ct:")
    assert is_rr_idx != -1, "'if _is_rr:' not found"
    assert lex_ct_idx != -1, "'elif _lex_ct:' not found (must become elif after _is_rr)"
    assert is_rr_idx < lex_ct_idx, "_is_rr check must precede _lex_ct check"


def test_is_rr_short_circuits_before_confusion_pool(server_src):
    """'if _is_rr:' check must appear before the generic _confusion_recovery_reply branch."""
    is_rr_idx = server_src.find("if _is_rr:")
    # Find the _confusion_recovery_reply call that is inside the elif (no mirror topic) branch
    confusion_pool_idx = server_src.find("elif _lex_ct:")
    assert is_rr_idx != -1, "'if _is_rr:' not found"
    assert confusion_pool_idx != -1, "'elif _lex_ct:' not found"
    # _is_rr fires before _lex_ct which itself precedes confusion pool
    assert is_rr_idx < confusion_pool_idx, "_is_rr check must precede elif _lex_ct:"


# ---------------------------------------------------------------------------
# 3. Python logic simulation — verify routing decisions
# ---------------------------------------------------------------------------

def _is_rr_simulate(text: str) -> bool:
    """Reproduce the _is_rr check from ui_server.py."""
    MARKERS = (
        "再说一遍", "再说一次", "再说一起", "再说一下", "请再说",
        "慢一点", "说慢", "慢慢说",
    )
    if not text:
        return False
    return (
        any(m in text for m in MARKERS)
        or (len(text.strip()) <= 5 and "什么意思" in text)
    )


@pytest.mark.parametrize("phrase,expected", [
    ("再说一遍", True),
    ("再说一遍好吗？", True),
    ("请再说一次", True),
    ("慢一点说", True),
    ("慢一点", True),
    ("慢慢说", True),
    ("什么意思", True),          # short, standalone
    ("什么意思？", True),         # with question mark (5 chars)
    ("什么意思啊", True),         # 5 chars — within limit
    # must NOT fire for these
    ("我不明白", False),          # confusion but NOT a repeat-request; handled separately
    ("好的谢谢", False),
    ("我在苏州住", False),
    ("碗是什么意思", False),      # 7 chars — vocabulary question, too long
    ("这句话是什么意思", False),   # longer — vocabulary question
    ("你做什么工作", False),
])
def test_is_rr_simulate(phrase, expected):
    """Reproduce server _is_rr classification for known recovery phrases."""
    assert _is_rr_simulate(phrase) == expected, (
        f"_is_rr({phrase!r}) expected {expected}"
    )


# ---------------------------------------------------------------------------
# 4. _is_confusion_signal still covers 我不明白 (regression guard)
# ---------------------------------------------------------------------------

def test_confusion_signal_covers_bu_ming_bai(server_src):
    """_is_confusion_signal must still include 不明白 — regression guard."""
    idx = server_src.find("def _is_confusion_signal")
    assert idx != -1
    body = server_src[idx: idx + 2000]
    assert "不明白" in body


def test_confusion_signal_covers_shenme_yisi(server_src):
    """_is_confusion_signal must still include 什么意思."""
    idx = server_src.find("def _is_confusion_signal")
    assert idx != -1
    body = server_src[idx: idx + 2000]
    assert "什么意思" in body


def test_confusion_signal_covers_zai_shuo(server_src):
    """_is_confusion_signal must still include 再说一遍."""
    idx = server_src.find("def _is_confusion_signal")
    assert idx != -1
    body = server_src[idx: idx + 2000]
    assert "再说一遍" in body


# ---------------------------------------------------------------------------
# 5. Client: spoken recovery intercept present before classifyUnmatched
# ---------------------------------------------------------------------------

def test_client_spoken_recovery_intercept_exists(app_js_src):
    """Spoken recovery intercept must exist in app.js."""
    assert "matchTranscriptToLearnerPhrase" in app_js_src
    # The intercept comment is the anchor
    assert "Spoken recovery intercept" in app_js_src or "_spokenRecoveryPhrase" in app_js_src


def test_client_spoken_recovery_before_classify_unmatched(app_js_src):
    """Spoken recovery intercept must appear before classifyUnmatchedFreeAnswerDecision call."""
    srp_idx = app_js_src.find("_spokenRecoveryPhrase")
    classify_idx = app_js_src.find("classifyUnmatchedFreeAnswerDecision(saidTrimmed")
    assert srp_idx != -1, "_spokenRecoveryPhrase not found in app.js"
    assert classify_idx != -1, "classifyUnmatchedFreeAnswerDecision(saidTrimmed) not found"
    assert srp_idx < classify_idx, (
        "Spoken recovery intercept must precede classifyUnmatchedFreeAnswerDecision"
    )


def test_client_spoken_recovery_handles_repeat_action(app_js_src):
    """Intercept must handle 'repeat' action."""
    idx = app_js_src.find("_spokenRecoveryPhrase")
    assert idx != -1
    block = app_js_src[idx: idx + 1500]
    assert '"repeat"' in block or "'repeat'" in block


def test_client_spoken_recovery_handles_slower_action(app_js_src):
    """Intercept must handle 'slower' action."""
    idx = app_js_src.find("_spokenRecoveryPhrase")
    assert idx != -1
    block = app_js_src[idx: idx + 1500]
    assert '"slower"' in block or "'slower'" in block


def test_client_spoken_recovery_handles_meaning_action(app_js_src):
    """Intercept must handle 'meaning' action (e.g. 我不明白, 什么意思 from panel)."""
    idx = app_js_src.find("_spokenRecoveryPhrase")
    assert idx != -1
    block = app_js_src[idx: idx + 1500]
    assert '"meaning"' in block or "'meaning'" in block


def test_client_spoken_recovery_returns_without_runTurn(app_js_src):
    """Intercept must return early (no runTurn) for repeat/slower/meaning."""
    idx = app_js_src.find("_spokenRecoveryPhrase")
    assert idx != -1
    block = app_js_src[idx: idx + 2500]
    assert "return;" in block, "Intercept must return early to avoid advancing frame"


def test_client_spoken_recovery_uses_setActivePartnerStatement(app_js_src):
    """Intercept must call setActivePartnerStatement to display the repeated question."""
    idx = app_js_src.find("_spokenRecoveryPhrase")
    assert idx != -1
    block = app_js_src[idx: idx + 2500]
    assert "setActivePartnerStatement" in block


def test_client_spoken_recovery_tracks_challenge_helpLevel(app_js_src):
    """Intercept must update _challenge.helpLevel in challenge mode."""
    idx = app_js_src.find("_spokenRecoveryPhrase")
    assert idx != -1
    block = app_js_src[idx: idx + 2500]
    assert "_challenge.helpLevel" in block


def test_client_spoken_recovery_allows_next_turn_fallthrough(app_js_src):
    """next_turn phrases (好吧) must fall through to normal runTurn flow."""
    idx = app_js_src.find("_spokenRecoveryPhrase")
    assert idx != -1
    block = app_js_src[idx: idx + 2500]
    assert "next_turn" in block


# ---------------------------------------------------------------------------
# 6. Recovery phrases JSON has entries for all four tested phrases
# ---------------------------------------------------------------------------

RECOVERY_JSON_PATH = REPO / "content" / "recovery_phrases.json"


@pytest.fixture(scope="module")
def recovery_phrases():
    if not RECOVERY_JSON_PATH.exists():
        pytest.skip("content/recovery_phrases.json not found")
    data = json.loads(RECOVERY_JSON_PATH.read_text(encoding="utf-8"))
    phrases = (data.get("phrases") or []) if isinstance(data, dict) else data
    return phrases


def _any_phrase_matches(phrases, hanzi_fragment: str) -> bool:
    for p in phrases:
        all_hanzi = [p.get("hanzi", "")] + list(p.get("paraphrase_variants", []))
        if any(hanzi_fragment in h for h in all_hanzi):
            return True
    return False


def test_recovery_phrase_zai_shuo_yi_bian(recovery_phrases):
    """recovery_phrases.json must include a 再说一遍 entry."""
    assert _any_phrase_matches(recovery_phrases, "再说一遍"), (
        "No recovery phrase matching '再说一遍'"
    )


def test_recovery_phrase_man_yi_dian(recovery_phrases):
    """recovery_phrases.json must include a 慢一点 entry."""
    assert _any_phrase_matches(recovery_phrases, "慢一点"), (
        "No recovery phrase matching '慢一点'"
    )


def test_recovery_phrase_bu_ming_bai(recovery_phrases):
    """recovery_phrases.json must include a 不明白 entry."""
    assert _any_phrase_matches(recovery_phrases, "不明白") or _any_phrase_matches(recovery_phrases, "不懂"), (
        "No recovery phrase matching '不明白' or '不懂'"
    )


def test_recovery_phrase_shenme_yisi(recovery_phrases):
    """recovery_phrases.json must include a 什么意思 entry."""
    assert _any_phrase_matches(recovery_phrases, "什么意思"), (
        "No recovery phrase matching '什么意思'"
    )


def test_recovery_phrase_zai_shuo_has_repeat_action(recovery_phrases):
    """再说一遍 recovery phrase must have recovery_action 'repeat'."""
    for p in recovery_phrases:
        if "再说一遍" in p.get("hanzi", ""):
            assert p.get("recovery_action") == "repeat", (
                f"再说一遍 should have action 'repeat', got {p.get('recovery_action')!r}"
            )
            return
    pytest.skip("再说一遍 phrase not found")


def test_recovery_phrase_man_yi_dian_has_slower_action(recovery_phrases):
    """慢一点说 recovery phrase must have recovery_action 'slower'."""
    for p in recovery_phrases:
        if "慢一点" in p.get("hanzi", ""):
            assert p.get("recovery_action") == "slower", (
                f"慢一点 should have action 'slower', got {p.get('recovery_action')!r}"
            )
            return
    pytest.skip("慢一点 phrase not found")


# ---------------------------------------------------------------------------
# 7. Regression guard: challenge mode tracking constants still exist in app.js
# ---------------------------------------------------------------------------

def test_challenge_active_flag_exists(app_js_src):
    """_challenge.active flag must still be defined in app.js."""
    assert "_challenge.active" in app_js_src or '"active": false' in app_js_src


def test_challenge_recovery_count_exists(app_js_src):
    """_challenge.recoveryCount must still be tracked."""
    assert "recoveryCount" in app_js_src


def test_challenge_reveal_text_exists(app_js_src):
    """_challengeRevealText function must still be called on second recovery."""
    assert "_challengeRevealText" in app_js_src


# ---------------------------------------------------------------------------
# 8. Frame-advance guard: learner_skip_confusion path not triggered for
#    strong confusion (我不明白) — strong confusion goes to server, not silent skip
# ---------------------------------------------------------------------------

def test_strong_confusion_does_not_weak_skip(app_js_src):
    """'不明白' is caught by _isStrongConfusionText so it should NOT weak-skip.
    Verify _isStrongConfusionText regex includes 不明白."""
    idx = app_js_src.find("_isStrongConfusionText")
    assert idx != -1
    body = app_js_src[idx: idx + 500]
    assert "不明白" in body


def test_weak_skip_only_for_truly_weak_confusion(app_js_src):
    """learner_skip_confusion (frame advance) must only trigger in the else branch
    (not strong confusion), not for any confusion with 不明白."""
    # Find the learner_skip_signal handler block that contains the isStrongConfusionText check
    idx = app_js_src.find("if (unmatchedDecision.reason === \"learner_skip_signal\")")
    assert idx != -1, "learner_skip_signal handler not found"
    block = app_js_src[idx: idx + 1200]
    assert "_isStrongConfusionText" in block, "_isStrongConfusionText check must be in handler"
    assert "learner_skip_confusion" in block, "learner_skip_confusion must be in handler"
    # learner_skip_confusion must be in the else branch (not the strong-confusion if branch)
    strong_idx = block.find("_isStrongConfusionText")
    else_idx = block.find("} else {")
    skip_idx = block.find("learner_skip_confusion")
    assert else_idx != -1, "Must have else branch after _isStrongConfusionText"
    assert else_idx < skip_idx, "learner_skip_confusion must be in the else branch"
    assert strong_idx < else_idx, "_isStrongConfusionText check must precede else branch"
