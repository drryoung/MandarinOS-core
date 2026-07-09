#!/usr/bin/env python3
"""
Surgical regression fix — acceptance tests A–I.

Covers the regression transcript batch:
  A/B  malformed "等你等…" output + retain 新西兰 as active place
  C    volunteered travel intent (九月我想去中国我想去甘肃) → travel follow-up
  D    persona food preference (成都菜 vs 上海菜) instead of uncertainty fallback
  E    city-special answer for 上海 (concrete fact, not generic uncertainty)
  F    city-special answer for 重庆 (concrete fact, not the hometown line)
  G    second-person question (你住在哪里啊) overrides pending-question recovery
  H    "我问你…" routes strongly to persona-answer mode
  I    frustration / insult → apology / repair, never "这样挺好"

These validate the shared helpers and the mirrored live counter-reply routing,
consistent with the existing test style (see test_stale_counter_reply_loop.py).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_UI_SERVER = ROOT / "scripts" / "ui_server.py"
_LMC = ROOT / "scripts" / "learner_memory_capture.py"

_cache: dict = {}


def _load(name: str, path: Path):
    if name in _cache:
        return _cache[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _cache[name] = mod
    return mod


@pytest.fixture(scope="module")
def srv():
    return _load("ui_server_surgical", _UI_SERVER)


@pytest.fixture(scope="module")
def lmc():
    return _load("lmc_surgical", _LMC)


@pytest.fixture(scope="module")
def jianguo(srv):
    # Chef in Chongqing (hometown 重庆; travelled to 成都/上海).
    return srv._resolve_persona("jianguo")


def _prefix(srv, persona, text, context_reply=""):
    return srv._answer_user_question_prefix(
        {"submitted_text": text}, persona, context_reply=context_reply
    )


# ── Mirrored live counter-reply override (matches ui_server run_turn head) ──────
def _user_initiative_counter(srv, answer_text, *, user_asked_question=False):
    """Replicates the user-initiative override block at the head of the
    counter-reply chain in ui_server.run_turn."""
    _counter_result = None
    if answer_text:
        if srv._is_frustration_or_insult(answer_text):
            _counter_result = srv._frustration_repair_reply(seed="t")
        elif (not user_asked_question) and srv._has_volunteered_travel_intent(answer_text):
            _counter_result = srv._travel_intent_followup(answer_text)
    return _counter_result


_GENERIC_UNCERTAINTY = (
    "这个我不太清楚",
    "这个我不太确定",
    "不好说",
    "我没问过具体的",
    "我真的不太了解",
)


# ── A / B  place normalisation + no malformed 等你等 output ─────────────────────

class TestPlaceNormalizationAndJunk:
    def test_new_zealand_retained(self, lmc):
        assert lmc.normalize_place_name("新西兰") == "新西兰"
        assert lmc.normalize_place_name("新西兰人") == "新西兰"

    def test_south_new_zealand_canonicalised(self, lmc):
        assert lmc.normalize_place_name("新西兰南方") in ("新西兰南岛", "新西兰南部")

    def test_deng_ni_deng_prefix_stripped(self, lmc):
        out = lmc.normalize_place_name("等你等新西兰的南方")
        assert out is not None
        assert "等你等" not in out
        assert "新西兰" in out

    def test_flight_time_not_treated_as_place(self, lmc):
        # "很远乘飞机是12小时" must not corrupt the active place.
        out = lmc.normalize_place_name("很远乘飞机是12小时")
        assert out is None or "新西兰" not in out

    def test_repair_helper_exists(self, srv):
        assert hasattr(srv, "_repair_asr_junk_text")

    def test_repair_strips_junk_from_rendered_line(self, srv):
        bad = "等你等新西兰的南方有什么特别的？"
        fixed = srv._repair_asr_junk_text(bad)
        assert "等你等" not in fixed
        assert "有什么特别的" in fixed

    def test_repair_noop_on_clean_text(self, srv):
        clean = "新西兰南方有什么特别的？"
        assert srv._repair_asr_junk_text(clean) == clean

    def test_confusion_not_flagged_for_nz_statement(self, srv):
        # Retaining 新西兰: a NZ mention must never be read as a garbled/confused turn.
        assert srv._is_confusion_signal("我说新西兰人") is False


# ── C  volunteered travel intent → travel follow-up ────────────────────────────

class TestTravelIntentFollowup:
    Q = "九月我想去中国我想去甘肃"

    def test_intent_detected(self, srv):
        assert srv._has_volunteered_travel_intent(self.Q) is True

    def test_should_route_to_travel(self, srv):
        assert srv._should_route_to_travel(self.Q, "family", False, ["WHO"]) is True

    def test_followup_is_about_destination(self, srv):
        zh, _en = srv._travel_intent_followup(self.Q)
        assert "甘肃" in zh
        assert "?" in zh or "？" in zh

    def test_live_override_produces_travel_not_family(self, srv):
        res = _user_initiative_counter(srv, self.Q, user_asked_question=False)
        assert res is not None
        zh = res[0]
        assert "甘肃" in zh
        assert "一起住" not in zh and "跟谁" not in zh


# ── D  persona food preference (成都菜 vs 上海菜) ───────────────────────────────

class TestFoodPreference:
    @pytest.mark.parametrize("q", [
        "你最喜欢成都菜和上海菜",
        "你喜欢成都菜还是上海菜",
    ])
    def test_food_preference_answered(self, srv, jianguo, q):
        res = _prefix(srv, jianguo, q)
        assert res is not None
        zh = res[0]
        assert not any(g in zh for g in _GENERIC_UNCERTAINTY), f"generic fallback: {zh!r}"
        assert "菜" in zh

    def test_direct_answer_food_preference(self, srv, jianguo):
        ans = srv._direct_persona_answer("你喜欢成都菜还是上海菜", jianguo)
        assert ans and "菜" in ans


# ── E / F  concrete city-special answers ───────────────────────────────────────

class TestCitySpecial:
    def test_shanghai_special_concrete(self, srv, jianguo):
        ans = srv._direct_persona_answer("上海有什么特别的", jianguo)
        assert ans is not None
        assert not any(g in ans for g in _GENERIC_UNCERTAINTY)
        assert "上海" in ans

    def test_chongqing_special_not_hometown_line(self, srv, jianguo):
        ans = srv._direct_persona_answer("重庆有什么特别的", jianguo)
        assert ans is not None
        assert ans.strip() != "我是土生土长的重庆人。"
        assert "重庆" in ans
        # Must contain a concrete feature, not merely restate origin.
        assert any(k in ans for k in ("火锅", "山城", "夜景", "江", "桥", "山"))

    def test_shanghai_special_via_prefix(self, srv, jianguo):
        res = _prefix(srv, jianguo, "上海有什么特别的", context_reply="我们可以聊聊上海")
        assert res is not None
        assert not any(g in res[0] for g in _GENERIC_UNCERTAINTY)


# ── G  second-person question overrides pending-question recovery ───────────────

class TestSecondPersonOverride:
    @pytest.mark.parametrize("q", [
        "你住在哪里啊",
        "你是哪里人",
        "你去过哪里啊",
        "你喜欢什么",
        "你有什么特别的",
    ])
    def test_not_confusion(self, srv, q):
        assert srv._is_confusion_signal(q) is False

    def test_you_live_where_is_direct_persona_question(self, srv):
        assert srv._is_direct_persona_question("你住在哪里啊") is True

    def test_you_live_where_answered(self, srv, jianguo):
        res = _prefix(srv, jianguo, "你住在哪里啊")
        assert res is not None
        assert "我是问" not in res[0]
        assert "重庆" in res[0]


# ── H  "我问你" routes to persona-answer mode ──────────────────────────────────

class TestWoWenNi:
    def test_wo_wen_ni_not_confusion(self, srv):
        assert srv._is_confusion_signal("我问你你是哪里人") is False

    def test_wo_wen_ni_answered(self, srv, jianguo):
        res = _prefix(srv, jianguo, "我问你你是哪里人")
        assert res is not None
        assert "我是问" not in res[0]
        assert "重庆" in res[0]


# ── I  frustration / insult → apology / repair ─────────────────────────────────

class TestFrustrationRepair:
    _INSULTS = [
        "你是傻瓜我不喜欢跟你说说话",
        "算了不说了",
        "你听不懂",
        "你不懂",
        "不说了",
    ]

    @pytest.mark.parametrize("t", _INSULTS)
    def test_detected_as_frustration(self, srv, t):
        assert srv._is_frustration_or_insult(t) is True

    @pytest.mark.parametrize("t", _INSULTS)
    def test_closing_blocked(self, srv, t):
        blocked, reason = srv._is_closing_blocked_by_learner_signal(t)
        assert blocked is True

    def test_repair_reply_is_apology(self, srv):
        zh, en = srv._frustration_repair_reply(seed="x")
        assert zh
        assert any(m in zh for m in ("对不起", "不好意思"))

    def test_live_override_returns_apology_not_positive_ack(self, srv):
        res = _user_initiative_counter(srv, "你是傻瓜我不喜欢跟你说说话")
        assert res is not None
        assert res[0] != "这样挺好。"
        assert any(m in res[0] for m in ("对不起", "不好意思"))


# ── Live-path wiring locks (source inspection, matching existing test style) ────

class TestLiveWiring:
    def test_source_has_user_initiative_override(self):
        src = _UI_SERVER.read_text(encoding="utf-8")
        assert "User-initiative overrides (highest priority)" in src
        assert "_is_frustration_or_insult(answer_text)" in src
        assert "_travel_intent_followup(answer_text)" in src

    def test_source_has_final_junk_guard(self):
        src = _UI_SERVER.read_text(encoding="utf-8")
        assert "_repair_asr_junk_text(response[\"frame_text\"])" in src

    def test_frustration_phrases_loaded(self, srv):
        assert srv._frustration_repair_phrases, "frustration_repair phrases not loaded"


# ── AP-4 compliance: no inline Chinese in _travel_intent_followup / _frustration_repair_reply ──

class TestAP4Compliance:
    """Verify that the two functions that previously contained inline Chinese strings
    now obtain their content from the phrase bank (recovery_phrases.json), not from
    literal Chinese strings embedded in the Python source."""

    # --- AP-4 source-inspection guards ---

    def test_travel_followup_no_inline_hanzi(self):
        """The f-string 'f"{dest}很有意思。你为什么想去{dest}？"' must not exist in source."""
        src = _UI_SERVER.read_text(encoding="utf-8")
        assert '很有意思。你为什么想去' not in src, (
            "AP-4 violation: inline Chinese travel f-string still present in ui_server.py"
        )

    def test_frustration_repair_no_inline_fallback_hanzi(self):
        """_frustration_repair_reply must not contain an inline Chinese tuple fallback.
        The phrase is allowed in recovery_phrases.json (phrase bank), but the Python
        function body must no longer embed it as a literal string."""
        import unicodedata
        lines = _UI_SERVER.read_text(encoding="utf-8").splitlines()
        # Find the def line.
        fn_start = next(
            (i for i, l in enumerate(lines) if l.strip().startswith("def _frustration_repair_reply(")),
            None,
        )
        assert fn_start is not None, "_frustration_repair_reply not found in source"
        # Collect only the indented function body (stop at the first unindented non-empty line
        # after the def line — that marks a new top-level statement).
        fn_lines = [lines[fn_start]]
        for ln in lines[fn_start + 1:]:
            if ln and not ln[0].isspace():
                break
            fn_lines.append(ln)
        fn_body = "\n".join(fn_lines)
        inline_hanzi = [ch for ch in fn_body if '\u4e00' <= ch <= '\u9fff']
        assert not inline_hanzi, (
            f"AP-4 violation: inline Chinese characters found in _frustration_repair_reply body: "
            f"{''.join(inline_hanzi)!r}"
        )

    def test_travel_templates_loaded_from_phrase_bank(self, srv):
        """_travel_intent_followup_templates must be populated at module load (phrase bank present)."""
        assert srv._travel_intent_followup_templates.get("dest"), (
            "travel_intent_dest_followup template not loaded from recovery_phrases.json"
        )
        assert srv._travel_intent_followup_templates.get("generic"), (
            "travel_intent_generic_followup template not loaded from recovery_phrases.json"
        )

    # --- Behaviour preservation: travel follow-up ---

    def test_travel_followup_gansu_contains_dest(self, srv):
        """Regression: '九月我想去中国我想去甘肃' must produce a travel follow-up mentioning 甘肃."""
        zh, en = srv._travel_intent_followup("九月我想去中国我想去甘肃")
        assert zh, "travel followup returned empty string — phrase bank may not be loaded"
        assert "甘肃" in zh, f"Expected 甘肃 in travel followup zh, got: {zh!r}"
        assert "?" in zh or "？" in zh, "Expected a question mark in travel followup"

    def test_travel_followup_generic_not_empty(self, srv):
        """Generic travel followup (no destination extractable) must be non-empty."""
        zh, en = srv._travel_intent_followup("我想去旅行")
        assert zh, "generic travel followup returned empty — phrase bank may not be loaded"
        assert "?" in zh or "？" in zh

    def test_travel_followup_no_latin_in_dest_slot(self, srv):
        """The {DEST} slot must be fully replaced — no leftover brace or English."""
        zh, en = srv._travel_intent_followup("九月我想去中国我想去甘肃")
        assert "{DEST}" not in zh, "Un-replaced {DEST} slot in travel followup"
        assert "{DEST}" not in en, "Un-replaced {DEST} slot in travel followup EN"

    # --- Behaviour preservation: frustration repair ---

    def test_frustration_repair_from_phrase_bank(self, srv):
        """_frustration_repair_reply must return one of the loaded phrase-bank entries."""
        zh, en = srv._frustration_repair_reply(seed="ap4_test")
        assert zh, "frustration repair returned empty — phrase bank not loaded"
        known_zh = [p[0] for p in srv._frustration_repair_phrases]
        assert zh in known_zh, (
            f"frustration reply {zh!r} is not from the phrase bank {known_zh}"
        )

    def test_frustration_repair_zh_is_apology(self, srv):
        """Phrase-bank frustration repair must still be an apology (对不起/不好意思)."""
        zh, _en = srv._frustration_repair_reply()
        assert any(m in zh for m in ("对不起", "不好意思")), (
            f"Frustration repair {zh!r} is not an apology"
        )

    def test_frustration_repair_en_nonempty(self, srv):
        """Every phrase-bank frustration-repair phrase must have a non-empty English translation."""
        for zh, en in srv._frustration_repair_phrases:
            assert en.strip(), f"Empty English translation for frustration phrase {zh!r}"
