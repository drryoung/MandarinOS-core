"""
Regression tests for the "corrupted place / sticky reverse-question" transcript.

These tests reflect the DESIRED post-fix behaviour. They exercise the smallest
routing/normalisation helpers that regressed, plus acceptance checks through the
live entry point `_answer_user_question_prefix`.

Transcript-derived acceptance criteria (item 7):
  - No stored/echoed output contains "等你等".
  - "风景很好看山水不错很多动物" advances place_special.
  - "九月我去中国我想去甘肃" triggers a travel follow-up (routes to travel).
  - "你做什么工作" answers job, not marriage or age.
  - "你做这个工作多久了" answers duration.
  - "为什么当老师" answers reason.
  - "西安有什么特别的" answers special features.
  - "西安有什么好吃的东西" answers food.
"""

import importlib.util
import pathlib
import json
import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SRV = _REPO_ROOT / "scripts" / "ui_server.py"
_LMC = _REPO_ROOT / "scripts" / "learner_memory_capture.py"
_MEILING = _REPO_ROOT / "personas" / "meiling.json"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def srv():
    return _load("ui_server", _SRV)


@pytest.fixture(scope="module")
def lmc():
    return _load("learner_memory_capture", _LMC)


@pytest.fixture(scope="module")
def meiling():
    return json.loads(_MEILING.read_text(encoding="utf-8"))


# ── Item 1: corrupted place entity never stored ────────────────────────────────

class TestPlaceNormalization:
    def test_normalize_function_exists(self, lmc):
        assert hasattr(lmc, "normalize_place_name")

    def test_garbage_prefix_stripped(self, lmc):
        out = lmc.normalize_place_name("等你等新西兰的南方")
        assert out is not None
        assert "等你等" not in out
        assert out in ("新西兰南岛", "新西兰南部", "新西兰")

    def test_pure_garbage_rejected(self, lmc):
        assert lmc.normalize_place_name("等你等") is None

    def test_clean_south_island_preserved(self, lmc):
        assert lmc.normalize_place_name("新西兰南岛") == "新西兰南岛"

    def test_dunedin_hanzi_preserved(self, lmc):
        assert lmc.normalize_place_name("达尼丁") == "达尼丁"

    def test_dunedin_english_normalized(self, lmc):
        assert lmc.normalize_place_name("Dunedin") == "达尼丁"

    def test_south_normalized_cautiously(self, lmc):
        out = lmc.normalize_place_name("新西兰南方")
        assert out in ("新西兰南岛", "新西兰南部")

    def test_plain_city_preserved(self, lmc):
        assert lmc.normalize_place_name("北京") == "北京"

    def test_new_zealand_english_alias(self, lmc):
        assert lmc.normalize_place_name("new zealand") == "新西兰"
        assert lmc.normalize_place_name("New Zealand") == "新西兰"

    def test_south_new_zealand_english_not_concatenated(self, lmc):
        # Regression: must NOT produce "新西兰south new zealand"; the English text
        # must be replaced (not concatenated) and canonicalised to an NZ south form.
        out = lmc.normalize_place_name("south new zealand")
        assert out is not None
        assert "new zealand" not in out.lower()
        assert not any("a" <= c.lower() <= "z" for c in out)
        assert out in ("新西兰南岛", "新西兰南部")

    def test_north_new_zealand_english(self, lmc):
        assert lmc.normalize_place_name("north new zealand") == "新西兰北岛"

    def test_english_alias_result_has_no_latin(self, lmc):
        for raw in ("new zealand", "South New Zealand", "north new zealand"):
            out = lmc.normalize_place_name(raw)
            assert out is None or not any("a" <= c.lower() <= "z" for c in out)

    def test_extract_city_never_returns_garbage(self, lmc):
        out = lmc._extract_city_from_hanzi("我现在住在等你等新西兰的南方")
        assert out is None or "等你等" not in out
        assert out in ("新西兰南岛", "新西兰南部", "新西兰")

    def test_capture_from_turn_no_garbage(self, lmc):
        updates = lmc.capture_from_turn(
            "f_live_where",
            submitted_text="我现在住在等你等新西兰的南方",
        )
        lives = updates.get("lives_in")
        if lives is not None:
            assert "等你等" not in lives


# ── Item 2: place_special accepts broad semantic content ───────────────────────

class TestPlaceSpecialContent:
    def test_helper_exists(self, srv):
        assert hasattr(srv, "_is_place_special_answer")

    @pytest.mark.parametrize("word", [
        "风景", "山", "水", "漂亮", "动物", "羊", "牛肉", "羊肉", "冰淇淋",
        "方便", "安静", "小", "干净", "海", "港口", "食物",
    ])
    def test_semantic_words_accepted(self, srv, word):
        assert srv._is_place_special_answer(word) is True, f"{word} should count as place content"

    def test_transcript_answer_advances(self, srv):
        ans = "风景很好看山水不错很多动物"
        assert srv._is_place_special_answer(ans) is True
        # Also suppresses noisy-location re-ask via _is_place_description
        assert srv._is_place_description(ans) is True

    def test_empty_not_place_content(self, srv):
        assert srv._is_place_special_answer("") is False


# ── Item 3: volunteered travel intent routes to travel ─────────────────────────

class TestTravelIntent:
    def test_helper_exists(self, srv):
        assert hasattr(srv, "_has_volunteered_travel_intent")

    @pytest.mark.parametrize("text", [
        "九月我去中国我想去甘肃",
        "九月我去中国，我想去甘肃",
        "我想去甘肃",
        "我要去日本",
        "我打算去云南",
        "明年想去西藏",
        "下个月去成都",
    ])
    def test_intent_detected(self, srv, text):
        assert srv._has_volunteered_travel_intent(text) is True

    @pytest.mark.parametrize("text", [
        "我住在西安",
        "我在新西兰南岛",
        "我喜欢吃火锅",
    ])
    def test_non_intent_not_detected(self, srv, text):
        assert srv._has_volunteered_travel_intent(text) is False

    def test_destination_extracted(self, srv):
        assert srv._extract_travel_destination("九月我去中国我想去甘肃") == "甘肃"
        assert srv._extract_travel_destination("我想去甘肃") == "甘肃"

    def test_followup_mentions_destination(self, srv):
        zh, en = srv._travel_intent_followup("九月我去中国我想去甘肃")
        assert "甘肃" in zh
        assert ("为什么" in zh) or ("看什么" in zh) or ("？" in zh)

    def test_should_route_to_travel_true(self, srv):
        assert srv._should_route_to_travel(
            "九月我去中国我想去甘肃", "place", False, ["CITY"],
        ) is True

    def test_should_not_route_when_already_travel(self, srv):
        assert srv._should_route_to_travel(
            "我想去甘肃", "travel", False, [],
        ) is False

    def test_should_not_route_plain_residence(self, srv):
        assert srv._should_route_to_travel(
            "我住在西安", "place", False, ["CITY"],
        ) is False


# ── Items 4 & 5: reverse-question routing + reverse_fact_map ────────────────────

class TestReverseRouting:
    def _answer(self, srv, persona, text):
        res = srv._answer_user_question_prefix({"submitted_text": text}, persona)
        return (res[0] if res else None)

    def test_job_not_marriage_or_age(self, srv, meiling):
        a = self._answer(srv, meiling, "你做什么工作")
        assert a and "美术老师" in a
        assert "结婚" not in a and "岁" not in a

    def test_work_type_answers_job(self, srv, meiling):
        a = self._answer(srv, meiling, "什么类型的工作")
        assert a and "美术老师" in a

    def test_duration_answers_duration(self, srv, meiling):
        a = self._answer(srv, meiling, "你做这个工作多久了")
        assert a and ("年" in a)
        # must not be the work-origin *reason* line
        assert "从小喜欢画画" not in a

    def test_reason_answers_reason(self, srv, meiling):
        a = self._answer(srv, meiling, "为什么当老师")
        assert a and ("画画" in a or "喜欢" in a)

    def test_special_answers_features(self, srv, meiling):
        a = self._answer(srv, meiling, "西安有什么特别的")
        assert a and ("兵马俑" in a or "历史" in a or "古都" in a)

    def test_food_answers_food(self, srv, meiling):
        a = self._answer(srv, meiling, "西安有什么好吃的东西")
        assert a and ("肉夹馍" in a or "凉皮" in a)

    def test_hometown_where_not_city_brief(self, srv, meiling):
        a = self._answer(srv, meiling, "你的家乡在哪里")
        assert a is not None
        # must be a personal hometown answer, not the bare encyclopedic brief
        assert a.startswith("我") or "老家" in a or "家乡" in a
        assert a != "西安在中国西北，是个历史很悠久的古都。"

    def test_marriage_answers_marriage(self, srv, meiling):
        a = self._answer(srv, meiling, "你结婚了吗")
        assert a and ("还没有" in a or "没有结婚" in a)

    def test_age_answers_age(self, srv, meiling):
        a = self._answer(srv, meiling, "你几岁")
        assert a and "32" in a


class TestReverseFactMap:
    def test_helpers_exist(self, srv):
        assert hasattr(srv, "_reverse_fact_answer")
        assert hasattr(srv, "_detect_reverse_fact_intent")

    def test_all_intents_distinct(self, srv, meiling):
        intents = [
            "hometown_where", "hometown_location", "hometown_special",
            "hometown_food", "job", "work_duration", "work_reason",
            "age", "marriage",
        ]
        answers = {i: srv._reverse_fact_answer(i, meiling) for i in intents}
        for i, a in answers.items():
            assert a, f"intent {i} produced no answer"
        vals = list(answers.values())
        assert len(set(vals)) == len(vals), f"answers not distinct: {answers}"

    def test_specific_intent_content(self, srv, meiling):
        assert "西安" in srv._reverse_fact_answer("hometown_where", meiling)
        assert "美术老师" in srv._reverse_fact_answer("job", meiling)
        assert "32" in srv._reverse_fact_answer("age", meiling)
        assert "年" in srv._reverse_fact_answer("work_duration", meiling)

    def test_detect_intent(self, srv):
        assert srv._detect_reverse_fact_intent("你做什么工作") == "job"
        assert srv._detect_reverse_fact_intent("你几岁") == "age"
        assert srv._detect_reverse_fact_intent("你结婚了吗") == "marriage"


# ── Item 6: anti-repetition guard ──────────────────────────────────────────────

class TestAntiRepetition:
    def test_helper_exists(self, srv):
        assert hasattr(srv, "_dedupe_persona_answer")

    def test_repeated_location_brief_blocked(self, srv, meiling):
        brief = "西安在中国西北，是个历史很悠久的古都。"
        out = srv._dedupe_persona_answer(brief, [brief], "西安有什么好吃的", meiling)
        assert out != brief
        assert ("肉夹馍" in out or "凉皮" in out or "好吃" in out)

    def test_non_repeat_passes_through(self, srv, meiling):
        cand = "我今年32岁。"
        out = srv._dedupe_persona_answer(cand, ["别的回答。"], "你几岁", meiling)
        assert out == cand

    def test_repeat_returns_different(self, srv, meiling):
        cand = "西安在中国西北，是个历史很悠久的古都。"
        out = srv._dedupe_persona_answer(cand, [cand], "西安有什么特别的", meiling)
        assert out != cand


# ── Dedupe alternative answers must carry a non-empty English translation ───────

class TestDedupeTranslation:
    """When dedupe swaps in an alternative reverse-fact answer, the English gloss
    must not be empty for dynamically-built answers (e.g. "我老家在西安。")."""

    _BRIEF = "西安在中国西北，是个历史很悠久的古都。"

    def test_helper_exists(self, srv):
        assert hasattr(srv, "_persona_answer_en")
        assert hasattr(srv, "_reverse_fact_answer_en")

    def _deduped_pair(self, srv, meiling, question):
        alt = srv._dedupe_persona_answer(self._BRIEF, [self._BRIEF], question, meiling)
        intent = srv._detect_reverse_fact_intent(question)
        en = srv._persona_answer_en(meiling, alt, intent)
        return alt, en

    def test_hometown_where_alt_has_zh_and_en(self, srv, meiling):
        alt, en = self._deduped_pair(srv, meiling, "你老家在哪")
        assert alt.strip() and alt.strip() != self._BRIEF
        assert "西安" in alt                     # dynamic "我老家在西安。"
        assert en.strip()                        # non-empty English

    def test_hometown_food_alt_has_zh_and_en(self, srv, meiling):
        alt, en = self._deduped_pair(srv, meiling, "你老家有什么好吃的")
        assert alt.strip() and alt.strip() != self._BRIEF
        assert en.strip()

    def test_dynamic_hometown_where_translation_nonempty(self, srv, meiling):
        # Directly translate a dynamic reverse-fact answer.
        en = srv._persona_answer_en(meiling, "我老家在西安。", "hometown_where")
        assert en.strip()

    def test_dynamic_work_duration_translation_nonempty(self, srv, meiling):
        en = srv._persona_answer_en(meiling, "我已经教了八年了。", "work_duration")
        assert en.strip()

    def test_age_translation_nonempty(self, srv, meiling):
        en = srv._persona_answer_en(meiling, "我今年32岁。", "age")
        assert en.strip()
        assert "32" in en

    def test_voice_line_translation_still_works(self, srv, meiling):
        # A persona voice_line must map to its voice_lines_en counterpart.
        zh = meiling["voice_lines"]["place"]
        en = srv._persona_answer_en(meiling, zh)
        assert en.strip() == meiling["voice_lines_en"]["place"].strip()

    def test_deflection_translation_still_works(self, srv, meiling):
        # A predefined deflection phrase must still resolve via the deflection map.
        phrase = srv._persona_deflect("marriage", "")
        expected = srv._persona_deflect_en(phrase)
        if expected:  # only assert when a curated EN gloss exists
            assert srv._persona_answer_en(meiling, phrase).strip() == expected.strip()
