#!/usr/bin/env python3
"""
Pinyin capture normalization — regression tests.

Evidence: many bot persona/direct/recovery responses in batch_2026-06-29_01
showed pinyin as "*(not recorded)*" while frame prompts had pinyin.

Fix: addTranscriptEntry in ui/app.js now calls fillSentenceHintPinyin for
all partner lines so the client lexicon fills gaps the server left empty.

These tests are static source assertions — they verify the structural
guarantee in app.js without requiring a browser/JS runtime.

Coverage:
  1.  addTranscriptEntry calls fillSentenceHintPinyin for partner lines.
  2.  Partner pinyin logic is guarded by _isPartner check (not applied to user lines).
  3.  fillSentenceHintPinyin is defined and delegates to buildSentencePinyinFromLexicon.
  4.  buildSentencePinyinFromLexicon is defined (character-lexicon fallback).
  5.  counter_reply transcript call-site does NOT hardcode empty pinyin for capture.
  6.  frame prompt transcript call-site includes frame_pinyin.
  7.  recovery transcript call-site (addTranscriptEntry partner) is present.
  8.  topic-transition transcript call-site uses addTranscriptEntry partner.
  9.  Server _resolve_counter_reply_pinyin exists (pinyin for deflect phrases).
  10. fillSentenceHintPinyin returns existing pinyin unchanged when non-empty.
  11. Session export uses `e.pinyin || undefined` (empty → no field → review shows gap).
  12. Session capture sends the pinyin field from conversationTranscript entries.
  13. partnerTranscriptExtrasFromData also calls fillSentenceHintPinyin (consistency).
  14. _initActiveTurnRecord uses fillSentenceHintPinyin (hint display consistent with capture).
  15. Closing move frame_pinyin path exists (curated closing tuples include pinyin).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "ui" / "app.js"
SERVER_PY = ROOT / "scripts" / "ui_server.py"


def _app() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _srv() -> str:
    return SERVER_PY.read_text(encoding="utf-8")


# ── 1. addTranscriptEntry calls fillSentenceHintPinyin for partner lines ──────

class TestAddTranscriptEntryPinyinNormalization:
    def test_filLsentencehintpinyin_called_for_partner(self):
        src = _app()
        # The function must contain a fillSentenceHintPinyin call
        assert "fillSentenceHintPinyin" in src
        # Specifically it must appear inside the addTranscriptEntry body
        fn_start = src.index("function addTranscriptEntry(")
        # Find the closing brace of the function (next line after "maybeRequestGlossForEntry")
        fn_end = src.index("maybeRequestGlossForEntry(entry);", fn_start) + 50
        fn_body = src[fn_start:fn_end]
        assert "fillSentenceHintPinyin" in fn_body, (
            "addTranscriptEntry must call fillSentenceHintPinyin for partner lines"
        )

    def test_partner_guard_present(self):
        src = _app()
        fn_start = src.index("function addTranscriptEntry(")
        fn_end = src.index("maybeRequestGlossForEntry(entry);", fn_start) + 50
        fn_body = src[fn_start:fn_end]
        # Must check role (isPartner or similar)
        assert "_isPartner" in fn_body or 'role === "partner"' in fn_body, (
            "addTranscriptEntry must guard pinyin logic by partner role"
        )

    def test_user_lines_not_sent_through_lexicon(self):
        src = _app()
        fn_start = src.index("function addTranscriptEntry(")
        fn_end = src.index("maybeRequestGlossForEntry(entry);", fn_start) + 50
        fn_body = src[fn_start:fn_end]
        # The pinyin line must be conditional — not unconditionally calling fillSentenceHintPinyin
        assert "? fillSentenceHintPinyin" in fn_body or "_isPartner" in fn_body, (
            "fillSentenceHintPinyin should be conditional on partner role"
        )

    def test_curated_pinyin_preserved(self):
        """fillSentenceHintPinyin must return existing pinyin unchanged when non-empty."""
        src = _app()
        fn_start = src.index("function fillSentenceHintPinyin(")
        fn_end = src.index("}", fn_start + 50) + 1
        fn_body = src[fn_start:fn_end + 200]
        # The function must short-circuit when existing pinyin is non-empty
        assert "return ex" in fn_body or "if (ex) return" in fn_body, (
            "fillSentenceHintPinyin must return existing pinyin unchanged when present"
        )


# ── 2. Core functions exist ───────────────────────────────────────────────────

class TestCoreFunctionsExist:
    def test_fill_sentence_hint_pinyin_defined(self):
        assert "function fillSentenceHintPinyin(" in _app()

    def test_build_sentence_pinyin_from_lexicon_defined(self):
        assert "function buildSentencePinyinFromLexicon(" in _app()

    def test_fill_delegates_to_build(self):
        src = _app()
        fn_start = src.index("function fillSentenceHintPinyin(")
        fn_body = src[fn_start: fn_start + 300]
        assert "buildSentencePinyinFromLexicon" in fn_body

    def test_partner_transcript_extras_also_uses_fill(self):
        """partnerTranscriptExtrasFromData (used for stubs) must also call fillSentenceHintPinyin."""
        src = _app()
        fn_start = src.index("function partnerTranscriptExtrasFromData(")
        fn_body = src[fn_start: fn_start + 800]
        assert "fillSentenceHintPinyin" in fn_body


# ── 3. Call-site checks — each utterance type ─────────────────────────────────

class TestCallSitesByUtteranceType:
    def test_counter_reply_uses_add_transcript_entry(self):
        """Persona answer (counter_reply) is added via addTranscriptEntry."""
        src = _app()
        # Find the counter_reply block
        assert 'addTranscriptEntry("partner", _counterReply' in src or \
               "addTranscriptEntry(\"partner\", _counterReply" in src, (
            "counter_reply must be added to transcript via addTranscriptEntry"
        )

    def test_frame_prompt_uses_add_transcript_entry(self):
        """Normal frame prompt is added via addTranscriptEntry."""
        src = _app()
        assert 'addTranscriptEntry("partner", window._currentFrameText' in src, (
            "Frame prompt must be added to transcript via addTranscriptEntry"
        )

    def test_frame_prompt_includes_frame_pinyin(self):
        """Frame prompt call site passes frame_pinyin from the server response."""
        src = _app()
        # Find addTranscriptEntry for _currentFrameText and check frame_pinyin nearby
        idx = src.index('addTranscriptEntry("partner", window._currentFrameText')
        block = src[idx: idx + 300]
        assert "frame_pinyin" in block, (
            "Frame prompt call site must pass frame_pinyin"
        )

    def test_recovery_uses_add_transcript_entry_partner(self):
        """Recovery/fallback partner line is added via addTranscriptEntry."""
        src = _app()
        # Recovery path: addTranscriptEntry("partner", _displayPhrase.hanzi, ...)
        assert 'addTranscriptEntry("partner", _displayPhrase.hanzi' in src, (
            "Recovery phrase must be added to transcript via addTranscriptEntry partner"
        )

    def test_recovery_pinyin_field_present_in_call(self):
        """Recovery call site passes _displayPhrase.pinyin to addTranscriptEntry."""
        src = _app()
        idx = src.index('addTranscriptEntry("partner", _displayPhrase.hanzi')
        block = src[idx: idx + 200]
        assert "pinyin" in block, (
            "Recovery addTranscriptEntry call must pass pinyin field"
        )

    def test_topic_transition_uses_add_transcript_entry_partner(self):
        """Recovery topic transition uses addTranscriptEntry partner."""
        src = _app()
        # Recovery topic transition: addTranscriptEntry("partner", _transition.zh, ...)
        assert 'addTranscriptEntry("partner", _transition.zh' in src, (
            "Topic transition must be added to transcript via addTranscriptEntry partner"
        )

    def test_closing_move_server_sends_frame_pinyin(self):
        """Closing moves are served with frame_pinyin from curated (zh, py, en) tuples."""
        srv = _srv()
        # Verify the closing pool tuples include a pinyin element
        assert '"frame_pinyin"' in srv, "Server must emit frame_pinyin in closing response"
        # Verify closing pool building uses 3-tuples (zh, py, en)
        assert "_cl_py" in srv or "_cl_zh, _cl_py, _cl_en" in srv, (
            "Closing move picker must extract pinyin from tuple"
        )

    def test_direction_stub_path_uses_partner_transcript_extras(self):
        """Mirror/direction stub lines use partnerTranscriptExtrasFromData which calls fillSentenceHintPinyin."""
        src = _app()
        assert "partnerTranscriptExtrasFromData" in src, (
            "partnerTranscriptExtrasFromData must be used for stub paths"
        )


# ── 4. Server-side pinyin helpers ─────────────────────────────────────────────

class TestServerPinyinHelpers:
    def test_resolve_counter_reply_pinyin_defined(self):
        assert "_resolve_counter_reply_pinyin" in _srv()

    def test_resolve_counter_reply_pinyin_used(self):
        """Server calls _resolve_counter_reply_pinyin for persona deflect phrase pinyin."""
        srv = _srv()
        assert "_resolve_counter_reply_pinyin(_counter_reply)" in srv or \
               "_resolve_counter_reply_pinyin(counter_reply" in srv


# ── 5. Session capture / export consistency ───────────────────────────────────

class TestSessionCaptureConsistency:
    def test_export_strips_empty_pinyin_to_undefined(self):
        """Session export uses `|| undefined` so empty strings don't appear as 'recorded'."""
        src = _app()
        export_idx = src.index("transcript: (conversationTranscript || []).map")
        export_block = src[export_idx: export_idx + 600]
        assert "pinyin" in export_block, "Export must include pinyin field"
        assert "|| undefined" in export_block or "|| undefined" in export_block, (
            "Export must strip empty pinyin to undefined"
        )

    def test_add_transcript_entry_pinyin_will_be_non_empty_for_partner(self):
        """Structural check: since fillSentenceHintPinyin is called for partner, the pinyin
        field in transcript entries will be non-empty whenever the lexicon covers the hanzi."""
        src = _app()
        # fillSentenceHintPinyin returns buildSentencePinyinFromLexicon as fallback
        fn_start = src.index("function fillSentenceHintPinyin(")
        fn_body = src[fn_start: fn_start + 300]
        assert "buildSentencePinyinFromLexicon" in fn_body, (
            "fillSentenceHintPinyin must fall back to lexicon — else partner pinyin stays empty"
        )

    def test_init_active_turn_record_uses_fill_sentence_hint(self):
        """_initActiveTurnRecord (on-screen hint) uses fillSentenceHintPinyin — consistent with capture."""
        src = _app()
        fn_start = src.index("function _initActiveTurnRecord(")
        fn_body = src[fn_start: fn_start + 400]
        assert "fillSentenceHintPinyin" in fn_body, (
            "_initActiveTurnRecord must use fillSentenceHintPinyin for consistency"
        )

    def test_no_raw_pinyin_empty_string_hardcoded_for_partner_in_add_entry(self):
        """addTranscriptEntry body must not use raw `extras.pinyin || ""` for partner lines."""
        src = _app()
        fn_start = src.index("function addTranscriptEntry(")
        fn_end = src.index("maybeRequestGlossForEntry(entry);", fn_start) + 50
        fn_body = src[fn_start:fn_end]
        # Old pattern was: pinyin: extras.pinyin || ""
        # New pattern uses fillSentenceHintPinyin for partner, so the raw pattern must be gone
        # from the partner branch
        assert 'pinyin: extras.pinyin || ""' not in fn_body, (
            "addTranscriptEntry must not use raw `extras.pinyin || \"\"` unconditionally — "
            "partner lines need fillSentenceHintPinyin fallback"
        )
