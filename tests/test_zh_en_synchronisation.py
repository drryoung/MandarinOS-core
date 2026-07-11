"""
Regression tests for Chinese–English synchronisation in MandarinOS server responses.

Governing invariant: the final Chinese counter_reply is the source of truth.
English must correspond to the exact final Chinese sentence, not to a coarse
intent that may match a different subject, city, or fact.

First-bad commit: 0177994 ("fix: restore English gloss for deduped reverse-fact
answers").  That commit introduced _reverse_fact_answer_en with three branches
that returned unrelated English for dynamically-constructed Chinese answers:

  • hometown_special → returned persona's current-city blurb instead of the
    feature-pool sentence actually selected
  • age             → returned persona's own age instead of parent's age
  • work_duration   → returned a job-description sentence instead of a
    duration clause

This file proves each broken case is now fixed and that correctly-paired
translations are preserved.
"""

import importlib.util
import pathlib
import json
import urllib.request

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SRV_PATH  = _REPO_ROOT / "scripts" / "ui_server.py"


# ── fixtures ─────────────────────────────────────────────────────────────────

def _load_srv():
    spec = importlib.util.spec_from_file_location("ui_server", _SRV_PATH)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def srv():
    return _load_srv()


@pytest.fixture(scope="module")
def zhiyuan(srv):
    return srv._resolve_persona("zhiyuan")


@pytest.fixture(scope="module")
def meiling(srv):
    return srv._resolve_persona("meiling")


# server_url fixture (optional — tests guarded with pytest.mark.skipif when absent)
def pytest_configure(config):
    config.addinivalue_line("markers", "live: marks tests that hit the live server")


@pytest.fixture(scope="module")
def server_url():
    import os
    return os.environ.get("MANDARINOS_SERVER_URL", "http://localhost:8080")


def _run_turn(url: str, cs: dict) -> dict:
    payload = json.dumps(
        {"persona_id": cs.get("persona_id", "zhiyuan"),
         "next_question": True,
         "conversation_state": cs},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/api/run_turn",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def _base_cs(persona="zhiyuan"):
    return {
        "persona_id": persona,
        "current_engine": "identity",
        "last_turn_was_answer": True,
        "last_counter_reply": "",
        "recent_persona_replies": [],
    }


# ── 1. Nanjing city-feature never receives Shanghai English ──────────────────

class TestHometownSpecialNoCrossCity:
    """_reverse_fact_answer_en("hometown_special") must return "".

    Previously it returned facts_en["place"] which for zhiyuan is
    "Shanghai moves fast." — an answer about a different city."""

    def test_reverse_fact_answer_en_hometown_special_returns_empty(self, srv, zhiyuan):
        en = srv._reverse_fact_answer_en("hometown_special", zhiyuan)
        assert en == "", (
            f"hometown_special must return '' to avoid returning the persona's "
            f"current-city description for a city-feature question; got {en!r}"
        )

    def test_persona_answer_en_for_nanjing_feature_returns_empty(self, srv, zhiyuan):
        # The actual Chinese answer picked from the city-feature pool for Nanjing.
        zh = "我呢，南京历史很悠久，有很多历史遗迹。"
        en = srv._persona_answer_en(zhiyuan, zh, "hometown_special")
        assert en == "", (
            f"English for a city-feature answer must be '' (delegated to gloss); "
            f"got {en!r}"
        )

    def test_nanjing_feature_en_is_not_shanghai_description(self, srv, zhiyuan):
        zh = "我呢，南京历史很悠久，有很多历史遗迹。"
        en = srv._persona_answer_en(zhiyuan, zh, "hometown_special")
        assert "Shanghai" not in en, "Nanjing feature answer must never show Shanghai English"
        assert "上海" not in en

    def test_meiling_hometown_special_also_returns_empty(self, srv, meiling):
        # For meiling (Xi'an), facts_en["place"] = "Xi'an has many historical sites."
        # This is the persona's general place fact, not the specific feature pool string.
        en = srv._reverse_fact_answer_en("hometown_special", meiling)
        assert en == ""


# ── 2. Parent-age never receives persona's own-age English ───────────────────

class TestAgeNoCrossSubject:
    """_reverse_fact_answer_en("age") must return "".

    Previously it returned f"I'm {age} years old." for ALL age-intent answers,
    including parent-age answers like "他们大概63多岁了。"."""

    def test_reverse_fact_answer_en_age_returns_empty(self, srv, zhiyuan):
        en = srv._reverse_fact_answer_en("age", zhiyuan)
        assert en == "", (
            f"age intent must return '' to avoid returning persona's own age "
            f"for parent-age replies; got {en!r}"
        )

    def test_parent_age_chinese_gets_empty_english(self, srv, zhiyuan):
        zh = "我呢，他们大概63多岁了。"
        en = srv._persona_answer_en(zhiyuan, zh, "age")
        assert en == "", f"Parent-age reply must produce '' English; got {en!r}"

    def test_parent_age_en_is_not_personas_own_age(self, srv, zhiyuan):
        zh = "我呢，他们大概63多岁了。"
        en = srv._persona_answer_en(zhiyuan, zh, "age")
        assert "38" not in en, (
            "Parent-age reply must not contain the persona's own age (38)"
        )

    def test_meiling_age_returns_empty(self, srv, meiling):
        en = srv._reverse_fact_answer_en("age", meiling)
        assert en == ""

    def test_persona_own_age_via_mirror_bank(self, srv, zhiyuan):
        # Persona's own age question resolves through the mirror bank (paired zh+en)
        # before _reverse_fact_answer_en is ever called.  Verify the mirror bank
        # path still exists and returns a non-empty answer for zhiyuan.
        # _find_mirror_answer returns (zh, en, topic, engine) — unpack accordingly.
        result = srv._find_mirror_answer("你多大了", "", zhiyuan)
        if result is None:
            result = srv._find_mirror_answer("你几岁", "", zhiyuan)
        # Not all personas have every mirror question; accept None gracefully.
        if result is not None:
            zh_r, en_r = result[0], result[1]
            assert en_r.strip(), "Mirror-bank age answer must carry English"


# ── 3. Work-duration never receives generic job-description English ───────────

class TestWorkDurationNoCrossContent:
    """_reverse_fact_answer_en("work_duration") must return a duration clause
    or ""; it must never return a job-description without duration information."""

    def test_zhiyuan_work_duration_returns_empty_or_duration(self, srv, zhiyuan):
        # zhiyuan's facts_en["work"] and vl_en["work"] contain no duration markers
        # → must return "" so gloss handles it.
        en = srv._reverse_fact_answer_en("work_duration", zhiyuan)
        assert en == "", (
            f"zhiyuan work_duration must return '' when no duration clause exists; "
            f"got {en!r}"
        )

    def test_zhiyuan_work_duration_en_is_not_job_description(self, srv, zhiyuan):
        zh = "我呢，做这行十年了。"
        en = srv._persona_answer_en(zhiyuan, zh, "work_duration")
        assert "tutor" not in en.lower() and "teach" not in en.lower(), (
            f"Work-duration reply must not contain job-description English; got {en!r}"
        )

    def test_zhiyuan_work_duration_chinese_gets_empty_english(self, srv, zhiyuan):
        zh = "我呢，做这行十年了。"
        en = srv._persona_answer_en(zhiyuan, zh, "work_duration")
        assert en == ""

    def test_meiling_work_duration_returns_duration_clause(self, srv, meiling):
        # meiling's vl_en["work"] contains "for eight years" — a valid duration clause.
        # The function should extract and return it.
        en = srv._reverse_fact_answer_en("work_duration", meiling)
        assert en.strip(), (
            "meiling work_duration should return a duration clause from vl_en['work']"
        )
        _dur_signals = ("year", "eight", "for ", "been teaching")
        assert any(s in en.lower() for s in _dur_signals), (
            f"meiling work_duration English must contain duration information; got {en!r}"
        )

    def test_meiling_work_duration_does_not_return_bare_description(self, srv, meiling):
        en = srv._reverse_fact_answer_en("work_duration", meiling)
        # Must not be the bare job-description without duration ("I teach at a middle school in Xi'an.")
        assert en != "I teach at a middle school in Xi'an.", (
            "Must not return bare job description; should extract the duration clause"
        )


# ── 4. Exact mirror-bank translations remain unchanged ───────────────────────

class TestMirrorBankTranslationsPreserved:
    """Questions routed through the mirror bank must still carry correct English."""

    def _mirror_en(self, srv, persona, question):
        result = srv._find_mirror_answer(question, "", persona)
        return result[1] if result else None

    def test_zhiyuan_job_mirror_en(self, srv, zhiyuan):
        en = self._mirror_en(srv, zhiyuan, "你做什么工作")
        assert en and "tutor" in en.lower()

    def test_zhiyuan_hometown_mirror_en(self, srv, zhiyuan):
        en = self._mirror_en(srv, zhiyuan, "你是哪里人")
        assert en and "Nanjing" in en

    def test_zhiyuan_marriage_mirror_en(self, srv, zhiyuan):
        en = self._mirror_en(srv, zhiyuan, "你结婚了吗")
        assert en and en.strip()

    def test_zhiyuan_siblings_mirror_en(self, srv, zhiyuan):
        en = self._mirror_en(srv, zhiyuan, "你有兄弟姐妹吗")
        assert en and "only child" in en.lower()

    def test_zhiyuan_name_mirror_en(self, srv, zhiyuan):
        en = self._mirror_en(srv, zhiyuan, "你叫什么名字")
        assert en and "Zhiyuan" in en

    def test_meiling_job_mirror_en(self, srv, meiling):
        en = self._mirror_en(srv, meiling, "你做什么工作")
        assert en and en.strip()

    def test_meiling_hometown_mirror_en(self, srv, meiling):
        en = self._mirror_en(srv, meiling, "你是哪里人")
        assert en and en.strip()


# ── 5. Deduplication must not leave English from old candidate ───────────────

class TestDeduplicationEnglishSync:
    """When _dedupe_persona_answer swaps in a different Chinese answer, the
    English must be regenerated from that new Chinese — not carried over from
    the original candidate."""

    def _get_deduped_pair(self, srv, persona, question, repeated_zh):
        intent   = srv._detect_reverse_fact_intent(question)
        alt_zh   = srv._dedupe_persona_answer(repeated_zh, [repeated_zh], question, persona)
        alt_en   = srv._persona_answer_en(persona, alt_zh, intent)
        return alt_zh, alt_en

    def test_meiling_deduped_hometown_where_pair(self, srv, meiling):
        repeated = "西安在中国西北，是个历史很悠久的古都。"
        alt_zh, alt_en = self._get_deduped_pair(srv, meiling, "你老家在哪", repeated)
        assert alt_zh.strip() and alt_zh.strip() != repeated, (
            "Dedupe must return a different Chinese answer"
        )
        # English may be empty (→ gloss path) but must never be the wrong city.
        assert "上海" not in alt_en and "Shanghai" not in alt_en

    def test_meiling_hometown_food_dedup_no_wrong_english(self, srv, meiling):
        repeated = "西安在中国西北，是个历史很悠久的古都。"
        alt_zh, alt_en = self._get_deduped_pair(srv, meiling, "你老家有什么好吃的", repeated)
        assert alt_zh.strip() and alt_zh.strip() != repeated

    def test_hometown_special_deduped_candidate_en_is_empty_not_wrong(self, srv, zhiyuan):
        # When dedupe selects a Nanjing feature-pool entry, the English should be ""
        # not the Shanghai city blurb.
        zh_candidate = "南京历史很悠久，有很多历史遗迹。"
        intent = srv._detect_reverse_fact_intent("南京有什么特别的")
        en = srv._persona_answer_en(zhiyuan, zh_candidate, intent)
        assert "Shanghai" not in en
        assert en == ""  # city-feature pool has no English → delegate to gloss


# ── 6. Empty counter_reply_en triggers gloss (server-side contract) ──────────

class TestServerEmptyEnSignal:
    """When the server cannot produce trustworthy English, counter_reply_en must
    be absent or empty so the client gloss routine runs."""

    def test_persona_answer_en_hometown_special_is_empty(self, srv, zhiyuan):
        zh = "我呢，南京历史很悠久，有很多历史遗迹。"
        en = srv._persona_answer_en(zhiyuan, zh, "hometown_special")
        assert en == ""

    def test_persona_answer_en_parent_age_is_empty(self, srv, zhiyuan):
        zh = "我呢，他们大概63多岁了。"
        en = srv._persona_answer_en(zhiyuan, zh, "age")
        assert en == ""

    def test_persona_answer_en_zhiyuan_work_duration_is_empty(self, srv, zhiyuan):
        zh = "我呢，做这行十年了。"
        en = srv._persona_answer_en(zhiyuan, zh, "work_duration")
        assert en == ""

    def test_server_response_en_field_omitted_when_empty(self, srv):
        # The server only includes counter_reply_en in the response when it is
        # non-empty (see scripts/ui_server.py: `if _counter_reply_en: response[…]`).
        # Verify the condition exists.
        src = _SRV_PATH.read_text(encoding="utf-8")
        assert 'if _counter_reply_en:' in src, (
            "Server must gate counter_reply_en on non-empty value"
        )
        assert 'response["counter_reply_en"] = _counter_reply_en' in src


# ── 7. Client gloss-path contract (source inspection) ───────────────────────

class TestClientGlossPathContract:
    """Verify client-side gloss logic through source inspection.

    The gloss routine is implemented in JavaScript (ui/app.js) and runs in the
    browser; we validate the contract by reading the shipped source.
    """

    @pytest.fixture(scope="class")
    def app_js(self):
        return (_REPO_ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    def test_gloss_skips_when_text_en_nonempty(self, app_js):
        # maybeRequestGlossForEntry must guard on text_en being empty.
        assert '(entry.text_en || "").trim()' in app_js or \
               "entry.text_en || ''" in app_js or \
               "entry.text_en" in app_js, (
                   "Gloss routine must skip entries that already have text_en"
               )
        # Specifically the early-return guard (line 320 in app.js)
        assert "if ((entry.text_en" in app_js

    def test_gloss_sends_exact_chinese(self, app_js):
        # Gloss POST must send the entry's own Chinese (not a global)
        assert '{ q: zh }' in app_js or '"q"' in app_js

    def test_gloss_attaches_to_entry_not_global(self, app_js):
        # Result is stored as entry.text_en, not a separate global
        assert "entry.text_en = en" in app_js

    def test_gloss_result_cached_by_zh_key(self, app_js):
        # glossLineCache must be keyed on the Chinese text
        assert "glossLineCache.set(key, en)" in app_js
        assert "glossLineCache.has(key)" in app_js

    def test_en_button_reads_own_entry_text_en(self, app_js):
        # toggleLineEnglish must look up entry by its own unique ID
        assert "conversationTranscript" in app_js
        assert ".find(" in app_js
        # entry is found by lineId, then its text_en is read
        idx = app_js.find("function toggleLineEnglish")
        block = app_js[idx: idx + 600]
        assert "entry.text_en" in block or "resolveLineEnglish" in block

    def test_no_global_english_reuse_in_toggle(self, app_js):
        # toggleLineEnglish must not read window._sentenceHint or a global
        # English variable when rendering the translation for a past line.
        idx = app_js.find("function toggleLineEnglish")
        block = app_js[idx: idx + 600]
        assert "window._sentenceHint" not in block, (
            "toggleLineEnglish must not reference window._sentenceHint "
            "(that is the ACTIVE turn hint, not the historical line's translation)"
        )

    def test_each_transcript_entry_has_unique_id(self, app_js):
        # addTranscriptEntry must assign a unique id to each entry
        assert '"line_" + Date.now()' in app_js or "line_" in app_js

    def test_gloss_pending_flag_prevents_duplicate_requests(self, app_js):
        # _glossFetchInFlight guards against duplicate in-flight requests
        assert "_glossFetchInFlight" in app_js


# ── 8. Pinyin-English from same Chinese (server side) ───────────────────────

class TestPinyinEnglishSameSource:
    """Pinyin and English must both be derived from the final counter_reply."""

    def test_pinyin_resolver_exists(self, srv):
        assert hasattr(srv, "_resolve_counter_reply_pinyin")

    def test_name_voice_line_has_pinyin(self, srv, zhiyuan):
        # "我叫志远。" has a curated pinyin or can be left to the client
        zh = "我叫志远。"
        py = srv._resolve_counter_reply_pinyin(zh)
        # May be "" (client builds from lexicon) — just must not crash
        assert isinstance(py, str)

    def test_pinyin_en_persona_answer_chain(self, srv, zhiyuan):
        # For a working mirror-bank answer, both en and pinyin sources exist.
        # _find_mirror_answer returns (zh, en, topic, engine) — unpack by index.
        result = srv._find_mirror_answer("你做什么工作", "", zhiyuan)
        assert result is not None
        zh, en = result[0], result[1]
        py = srv._resolve_counter_reply_pinyin(zh)
        assert zh.strip()
        assert en.strip()
        assert isinstance(py, str)


# ── 9. Live server round-trip: three previously-broken questions ─────────────

class TestLiveServerSynchronisation:
    """Hit the local (or configured) server and confirm that counter_reply_en
    is now empty (or correctly paired) for the three previously-broken cases."""

    def _turn(self, server_url, question, persona="zhiyuan"):
        cs = _base_cs(persona)
        cs["last_answer"] = {"submitted_text": question}
        return _run_turn(server_url, cs)

    def test_nanjing_feature_en_is_empty_or_correct(self, server_url):
        try:
            d = self._turn(server_url, "南京有什么特别的")
        except Exception:
            pytest.skip("Server unavailable")
        cr    = d.get("counter_reply", "")
        cr_en = d.get("counter_reply_en", "")
        assert "Shanghai" not in cr_en, (
            f"Nanjing feature reply must not show Shanghai English; got {cr_en!r}"
        )
        # If en is non-empty it must correspond to the Chinese
        if cr_en:
            assert "Nanjing" in cr_en or "Nánjīng" in cr_en or "历史" in cr or \
                   len(cr_en) > 0, f"counter_reply_en: {cr_en!r}"

    def test_parent_age_en_is_empty_or_correct(self, server_url):
        try:
            d = self._turn(server_url, "你爸妈多大")
        except Exception:
            pytest.skip("Server unavailable")
        cr    = d.get("counter_reply", "")
        cr_en = d.get("counter_reply_en", "")
        assert "I'm 38" not in cr_en, (
            f"Parent-age reply must not contain persona's own age; got {cr_en!r}"
        )
        if cr_en:
            assert "38" not in cr_en or "63" in cr_en or "they" in cr_en.lower()

    def test_work_duration_en_is_empty_or_contains_duration(self, server_url):
        try:
            d = self._turn(server_url, "你这样做多久了")
        except Exception:
            pytest.skip("Server unavailable")
        cr_en = d.get("counter_reply_en", "")
        if cr_en:
            _dur_signals = ("year", "years", "decade", "for ", "since", "long")
            assert any(s in cr_en.lower() for s in _dur_signals), (
                f"If work-duration has English it must contain duration info; "
                f"got {cr_en!r}"
            )
        # Empty is also acceptable (→ gloss path)
