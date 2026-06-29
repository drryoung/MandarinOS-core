"""
tests/test_place_deixis_explicit.py

Regression tests for explicit place-name substitution in partner prompts.
Goal: frames that previously used ambiguous 这里/那里 now render explicit city/hometown
names when learner memory is available.

Covers:
  - {CITY} frames: p2_pl_1, p2_pl_2, p2_pl_city_special, f_place_special, f_place_food,
    f_place_why_live, f_probe_place_why_move, f_probe_place_moved, f_probe_place_stay,
    f_food_available
  - {HOMETOWN} frame: p2_pl_home_food
  - Server slot-fill: {CITY} → lives_in, {HOMETOWN} → hometown, fallbacks
  - No deictic raw tokens leak to learner UI
"""
import json
import pathlib
import pytest

REPO = pathlib.Path(__file__).parent.parent
P2_FRAMES_PATH = REPO / "p2_frames.json"
UI_SERVER_PATH = REPO / "scripts" / "ui_server.py"

# ---------------------------------------------------------------------------
# Helper: load all p2_frames keyed by id
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def frames_by_id():
    data = json.loads(P2_FRAMES_PATH.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        items = data.get("frames", data.get("p2_frames", list(data.values())))
    else:
        items = data
    return {f["id"]: f for f in items if isinstance(f, dict) and "id" in f}


# ---------------------------------------------------------------------------
# 1. Frame content: no bare 这里/那里 in the migrated frames
# ---------------------------------------------------------------------------

MIGRATED_CITY_FRAMES = [
    "p2_pl_1",
    "p2_pl_2",
    "p2_pl_city_special",
    "f_place_special",
    "f_place_food",
    "f_place_why_live",
    "f_probe_place_why_move",
    "f_probe_place_moved",
    "f_probe_place_stay",
    "f_food_available",
]

MIGRATED_HOMETOWN_FRAMES = [
    "p2_pl_home_food",
]

DEICTIC_LITERALS = ("这里", "那里", "那边")


@pytest.mark.parametrize("fid", MIGRATED_CITY_FRAMES)
def test_city_frame_has_no_bare_deictics(frames_by_id, fid):
    """Migrated {CITY} frames must not contain literal 这里/那里/那边."""
    frame = frames_by_id[fid]
    text = frame.get("text", "")
    for d in DEICTIC_LITERALS:
        assert d not in text, (
            f"{fid}.text still contains deictic '{d}': {text!r}"
        )


@pytest.mark.parametrize("fid", MIGRATED_CITY_FRAMES)
def test_city_frame_uses_city_slot(frames_by_id, fid):
    """Migrated {CITY} frames must contain the {CITY} slot token."""
    frame = frames_by_id[fid]
    assert "{CITY}" in frame.get("text", ""), (
        f"{fid}.text missing {{CITY}} slot: {frame.get('text')!r}"
    )


@pytest.mark.parametrize("fid", MIGRATED_HOMETOWN_FRAMES)
def test_hometown_frame_has_no_bare_deictics(frames_by_id, fid):
    """Migrated {HOMETOWN} frames must not contain literal 那里."""
    frame = frames_by_id[fid]
    text = frame.get("text", "")
    for d in DEICTIC_LITERALS:
        assert d not in text, (
            f"{fid}.text still contains deictic '{d}': {text!r}"
        )


@pytest.mark.parametrize("fid", MIGRATED_HOMETOWN_FRAMES)
def test_hometown_frame_uses_hometown_slot(frames_by_id, fid):
    """Migrated {HOMETOWN} frames must contain the {HOMETOWN} slot token."""
    frame = frames_by_id[fid]
    assert "{HOMETOWN}" in frame.get("text", ""), (
        f"{fid}.text missing {{HOMETOWN}} slot: {frame.get('text')!r}"
    )


# ---------------------------------------------------------------------------
# 2. Frame pinyin and text_en consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fid", MIGRATED_CITY_FRAMES)
def test_city_frame_pinyin_has_no_bare_deictic_pinyin(frames_by_id, fid):
    """Migrated {CITY} frame pinyin must not contain 'zhèlǐ' or 'nàlǐ'."""
    frame = frames_by_id[fid]
    pinyin = frame.get("pinyin", "")
    for dpy in ("zhèlǐ", "nàlǐ"):
        assert dpy not in pinyin, (
            f"{fid}.pinyin still contains '{dpy}': {pinyin!r}"
        )


@pytest.mark.parametrize("fid", MIGRATED_CITY_FRAMES)
def test_city_frame_text_en_uses_city_placeholder(frames_by_id, fid):
    """Migrated {CITY} frame text_en must use '[CITY]' not 'here'/'there' alone."""
    frame = frames_by_id[fid]
    text_en = frame.get("text_en", "")
    assert "[CITY]" in text_en, (
        f"{fid}.text_en missing '[CITY]' placeholder: {text_en!r}"
    )


@pytest.mark.parametrize("fid", MIGRATED_HOMETOWN_FRAMES)
def test_hometown_frame_text_en_uses_hometown_placeholder(frames_by_id, fid):
    """Migrated {HOMETOWN} frame text_en must use '[HOMETOWN]' placeholder."""
    frame = frames_by_id[fid]
    text_en = frame.get("text_en", "")
    assert "[HOMETOWN]" in text_en, (
        f"{fid}.text_en missing '[HOMETOWN]' placeholder: {text_en!r}"
    )


# ---------------------------------------------------------------------------
# 3. Server slot-fill source checks (static analysis of ui_server.py)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ui_server_src():
    return UI_SERVER_PATH.read_text(encoding="utf-8")


def test_server_slot_fill_detects_hometown_token(ui_server_src):
    """_needs_city_slot check must include {HOMETOWN}."""
    assert '"{HOMETOWN}"' in ui_server_src or "'{HOMETOWN}'" in ui_server_src


def test_server_slot_fill_reads_hometown_from_memory(ui_server_src):
    """Server must read _hometown from slot_mem.get('hometown')."""
    assert "_hometown" in ui_server_src
    assert "get(\"hometown\")" in ui_server_src or "get('hometown')" in ui_server_src


def test_server_slot_fill_replaces_hometown_in_frame_text(ui_server_src):
    """Server must replace {HOMETOWN} in frame_text."""
    assert '"{HOMETOWN}"' in ui_server_src
    assert "replace(\"{HOMETOWN}\"" in ui_server_src or "replace('{HOMETOWN}'" in ui_server_src


def test_server_slot_fill_replaces_hometown_in_pinyin(ui_server_src):
    """Server must replace {HOMETOWN} in frame_pinyin."""
    assert "frame_pinyin" in ui_server_src
    assert "{HOMETOWN}" in ui_server_src


def test_server_slot_fill_replaces_hometown_in_text_en(ui_server_src):
    """Server must replace [HOMETOWN] in frame_text_en."""
    assert "[HOMETOWN]" in ui_server_src


def test_server_slot_fill_hometown_fallback_exists(ui_server_src):
    """Safety net must include {HOMETOWN} → 那儿 fallback."""
    assert '("{HOMETOWN}", "那儿")' in ui_server_src or "'{HOMETOWN}', '那儿'" in ui_server_src or (
        "{HOMETOWN}" in ui_server_src and "那儿" in ui_server_src
    )


def test_server_slot_fill_en_hometown_fallback_exists(ui_server_src):
    """Safety net must include [HOMETOWN] → 'there' fallback."""
    assert '"[HOMETOWN]", "there"' in ui_server_src or "'[HOMETOWN]', 'there'" in ui_server_src or (
        "[HOMETOWN]" in ui_server_src and '"there"' in ui_server_src
    )


# ---------------------------------------------------------------------------
# 4. No raw placeholders in any frame text (JSON-level, scope: all frames)
# ---------------------------------------------------------------------------

def test_no_raw_city_slot_without_slot_declaration(frames_by_id):
    """
    Frames using {CITY} in text must acknowledge it via the slot-fill system —
    the test verifies the token is present (not leaked as literal deictic).
    This is a canary: if content accidentally introduces {CITY} without intending it,
    we catch it here.
    """
    city_frames = [fid for fid, f in frames_by_id.items() if "{CITY}" in f.get("text", "")]
    # All such frames should be in the known set or use it intentionally
    known = set(MIGRATED_CITY_FRAMES) | {
        "p2_pl_4",   # 住在{CITY}方便吗？ — pre-existing slot frame
        "p2_pl_5",   # 我觉得{CITY}{REASON_POS}。 — EXTEND frame, pre-existing slot
    }
    unexpected = [fid for fid in city_frames if fid not in known]
    assert not unexpected, f"Unexpected frames with {{CITY}} slot: {unexpected}"


def test_no_raw_hometown_slot_outside_known_frames(frames_by_id):
    """Only known frames should use {HOMETOWN} slot."""
    hometown_frames = [fid for fid, f in frames_by_id.items() if "{HOMETOWN}" in f.get("text", "")]
    known = set(MIGRATED_HOMETOWN_FRAMES)
    unexpected = [fid for fid in hometown_frames if fid not in known]
    assert not unexpected, f"Unexpected frames with {{HOMETOWN}} slot: {unexpected}"


# ---------------------------------------------------------------------------
# 5. Integration: simulate the server slot-fill pass
# ---------------------------------------------------------------------------

def _simulate_slot_fill(frame_text, frame_pinyin, frame_text_en, lives_in="", hometown=""):
    """Reproduce the Phase 13A slot-fill logic from ui_server.py."""
    _city = (lives_in or hometown or "").strip()
    _hometown_val = (hometown or "").strip()

    for tok in ("{CITY}", "{PLACE}"):
        if tok in frame_text:
            frame_text = frame_text.replace(tok, _city or "那儿")
        if tok in frame_pinyin:
            frame_pinyin = frame_pinyin.replace(tok, _city or "nàr")
    if "[CITY]" in frame_text_en:
        frame_text_en = frame_text_en.replace("[CITY]", _city or "there")

    if "{HOMETOWN}" in frame_text:
        frame_text = frame_text.replace("{HOMETOWN}", _hometown_val or "那儿")
    if "{HOMETOWN}" in frame_pinyin:
        frame_pinyin = frame_pinyin.replace("{HOMETOWN}", _hometown_val or "nàr")
    if "[HOMETOWN]" in frame_text_en:
        frame_text_en = frame_text_en.replace("[HOMETOWN]", _hometown_val or "there")

    return frame_text, frame_pinyin, frame_text_en


def test_city_slot_fills_lives_in(frames_by_id):
    """f_place_special {CITY} → lives_in when learner lives in Suzhou."""
    f = frames_by_id["f_place_special"]
    text, py, en = _simulate_slot_fill(
        f["text"], f["pinyin"], f["text_en"],
        lives_in="苏州", hometown="新西兰"
    )
    assert "苏州" in text
    assert "苏州" in py
    assert "苏州" in en
    assert "这里" not in text
    assert "那里" not in text
    assert "{CITY}" not in text


def test_city_slot_falls_back_to_hometown_when_no_lives_in(frames_by_id):
    """f_place_food {CITY} → hometown when lives_in is absent."""
    f = frames_by_id["f_place_food"]
    text, py, en = _simulate_slot_fill(
        f["text"], f["pinyin"], f["text_en"],
        lives_in="", hometown="新西兰"
    )
    assert "新西兰" in text
    assert "那里" not in text
    assert "{CITY}" not in text


def test_city_slot_falls_back_to_nàr_when_no_memory(frames_by_id):
    """f_place_food {CITY} → 那儿 when neither lives_in nor hometown is known."""
    f = frames_by_id["f_place_food"]
    text, py, en = _simulate_slot_fill(
        f["text"], f["pinyin"], f["text_en"],
        lives_in="", hometown=""
    )
    assert "那儿" in text
    assert "{CITY}" not in text


def test_hometown_slot_fills_from_hometown(frames_by_id):
    """p2_pl_home_food {HOMETOWN} → hometown (New Zealand), not current city (Suzhou)."""
    f = frames_by_id["p2_pl_home_food"]
    text, py, en = _simulate_slot_fill(
        f["text"], f["pinyin"], f["text_en"],
        lives_in="苏州", hometown="新西兰"
    )
    assert "新西兰" in text
    assert "苏州" not in text, "Hometown frame must not use lives_in"
    assert "那里" not in text
    assert "{HOMETOWN}" not in text


def test_hometown_slot_falls_back_to_nàr_when_no_hometown(frames_by_id):
    """p2_pl_home_food {HOMETOWN} → 那儿 when hometown is unknown."""
    f = frames_by_id["p2_pl_home_food"]
    text, py, en = _simulate_slot_fill(
        f["text"], f["pinyin"], f["text_en"],
        lives_in="苏州", hometown=""
    )
    assert "那儿" in text
    assert "{HOMETOWN}" not in text


def test_place_why_live_explicit_city(frames_by_id):
    """f_place_why_live should produce '你为什么住在{city}？' not '你为什么住在这里？'."""
    f = frames_by_id["f_place_why_live"]
    text, _, _ = _simulate_slot_fill(
        f["text"], f["pinyin"], f["text_en"],
        lives_in="苏州"
    )
    assert "苏州" in text
    assert "这里" not in text


def test_probe_place_moved_explicit_city(frames_by_id):
    """f_probe_place_moved: '你在{city}住了多久了？' not '你在那里住了多久了？'."""
    f = frames_by_id["f_probe_place_moved"]
    text, _, _ = _simulate_slot_fill(
        f["text"], f["pinyin"], f["text_en"],
        lives_in="苏州"
    )
    assert "苏州" in text
    assert "那里" not in text


def test_probe_place_stay_explicit_city(frames_by_id):
    """f_probe_place_stay: '你打算在{city}长期住下去吗？' not '那里'."""
    f = frames_by_id["f_probe_place_stay"]
    text, _, _ = _simulate_slot_fill(
        f["text"], f["pinyin"], f["text_en"],
        lives_in="苏州"
    )
    assert "苏州" in text
    assert "那里" not in text


def test_food_available_explicit_city(frames_by_id):
    """f_food_available: '{city}有什么好吃的？' not '那里有什么好吃的？'."""
    f = frames_by_id["f_food_available"]
    text, _, _ = _simulate_slot_fill(
        f["text"], f["pinyin"], f["text_en"],
        lives_in="苏州"
    )
    assert "苏州" in text
    assert "那里" not in text


def test_topic_shift_nz_to_suzhou(frames_by_id):
    """
    After topic shift from New Zealand to Suzhou:
    place-engine frames use lives_in (Suzhou), hometown frame uses hometown (NZ).
    """
    lives_in = "苏州"
    hometown = "新西兰"
    place_frame = frames_by_id["f_place_special"]
    home_frame = frames_by_id["p2_pl_home_food"]

    place_text, _, _ = _simulate_slot_fill(
        place_frame["text"], place_frame["pinyin"], place_frame["text_en"],
        lives_in=lives_in, hometown=hometown
    )
    home_text, _, _ = _simulate_slot_fill(
        home_frame["text"], home_frame["pinyin"], home_frame["text_en"],
        lives_in=lives_in, hometown=hometown
    )

    assert "苏州" in place_text, "Place-engine frame should reference current city"
    assert "新西兰" in home_text, "Hometown frame should reference hometown, not current city"
    assert "苏州" not in home_text, "Hometown frame must not bleed current city"
    assert "新西兰" not in place_text, "Place-engine frame must not bleed hometown"


def test_topic_shift_japan_context_place_engine(frames_by_id):
    """
    After learner mentions Japan, the place-engine still uses lives_in (Suzhou), not Japan.
    Japan context is for learner questions, not partner prompts.
    """
    lives_in = "苏州"
    f = frames_by_id["f_place_food"]
    text, _, _ = _simulate_slot_fill(
        f["text"], f["pinyin"], f["text_en"],
        lives_in=lives_in, hometown="新西兰"
    )
    assert "苏州" in text
    assert "日本" not in text


# ---------------------------------------------------------------------------
# 6. p1_frames.json — those 那边 frames are in p1, out of scope for this fix
# ---------------------------------------------------------------------------

def test_p1_frames_contain_nà_biān(tmp_path):
    """Verify the p1_frames.json deictic frames are separate from p2 scope."""
    p1_path = REPO / "p1_frames.json"
    if not p1_path.exists():
        pytest.skip("p1_frames.json not present in repo root")
    src = p1_path.read_text(encoding="utf-8")
    assert "那边" in src, "p1_frames.json expected to contain 那边 distance frames"


# ---------------------------------------------------------------------------
# 7. Validate p2_frames.json is still valid JSON after all edits
# ---------------------------------------------------------------------------

def test_p2_frames_valid_json():
    raw = P2_FRAMES_PATH.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed, "p2_frames.json should be non-empty after edits"
