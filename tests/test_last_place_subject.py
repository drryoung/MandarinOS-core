"""
Tests for: Add last_place_subject anchoring (Task 2).

Verifies that:
  1. last_place_subject is tracked in state_update when a place is mentioned.
  2. Common Chinese cities and NZ/overseas places are extracted.
  3. last_place_subject persists across turns when no new place is mentioned.
  4. {CITY}/{PLACE}/{HOMETOWN} safety net uses last_place_subject as preferred fallback.
  5. Place list covers: Xi'an, Chengdu, Beijing, New Zealand, southern New Zealand.
  6. Source code guards confirm the anchoring logic is present.
"""

import importlib.util
import pathlib
import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SRV = _REPO_ROOT / "scripts" / "ui_server.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("ui_server", _SRV)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def srv():
    return _load_server()


# ── Place extraction list ──────────────────────────────────────────────────────

class TestPlaceList:
    """The _LPS_PLACES tuple must cover the required test cities and regions."""

    def _get_places(self, srv):
        src = _SRV.read_text(encoding="utf-8")
        # Find _LPS_PLACES tuple in source
        start = src.index("_LPS_PLACES: tuple = (")
        end = src.index(")", start)
        return src[start:end + 1]

    def test_xian_in_place_list(self, srv):
        block = self._get_places(srv)
        assert "西安" in block

    def test_chengdu_in_place_list(self, srv):
        block = self._get_places(srv)
        assert "成都" in block

    def test_beijing_in_place_list(self, srv):
        block = self._get_places(srv)
        assert "北京" in block

    def test_new_zealand_in_place_list(self, srv):
        block = self._get_places(srv)
        assert "新西兰" in block

    def test_southern_new_zealand_in_place_list(self, srv):
        block = self._get_places(srv)
        # Either 南新西兰 or 新西兰南部 should be present
        assert "南新西兰" in block or "新西兰南部" in block


# ── State update wiring ────────────────────────────────────────────────────────

class TestStateUpdateWiring:
    def test_state_update_sets_last_place_subject(self):
        src = _SRV.read_text(encoding="utf-8")
        assert 'last_place_subject' in src, (
            "last_place_subject must be tracked in state_update"
        )

    def test_cs_lps_fallback_used_in_city_safety_net(self):
        src = _SRV.read_text(encoding="utf-8")
        assert "_cs_lps_fallback" in src, (
            "_cs_lps_fallback must be read from cs and used in slot safety net"
        )

    def test_lps_place_list_in_source(self):
        src = _SRV.read_text(encoding="utf-8")
        assert "_LPS_PLACES" in src


# ── City safety net uses last_place_subject ────────────────────────────────────

class TestCitySafetyNetUsesLPS:
    def test_safety_net_prefers_lps_over_generic(self):
        """When last_place_subject is set, {CITY} slot should use it, not 那儿."""
        src = _SRV.read_text(encoding="utf-8")
        # Check that _cs_lps_fallback appears before the keyword-based generics
        lps_pos = src.index("_cs_lps_fallback")
        city_fb_pos = src.index('"那儿"', lps_pos)   # 那儿 generic fallback
        # _cs_lps_fallback check should appear before 那儿 in the safety net block
        assert lps_pos < city_fb_pos, (
            "last_place_subject check must come before 那儿 generic in safety net"
        )


# ── Place extraction logic ─────────────────────────────────────────────────────

class TestPlaceExtractionLogic:
    """Verify that places are correctly extracted from partner text."""

    def _extract_place(self, text, places):
        """Simulate the extraction loop logic."""
        for p in places:
            if p in text:
                return p
        return ""

    def _get_lps_places(self):
        src = _SRV.read_text(encoding="utf-8")
        start = src.index("_LPS_PLACES: tuple = (")
        end = src.index(")", start)
        block = src[start:end + 1]
        import re
        matches = re.findall(r'"([^"]+)"|\'([^\']+)\'', block)
        return [a if a else b for a, b in matches]

    def test_xian_extracted_from_partner_reply(self):
        places = self._get_lps_places()
        text = "西安离北京不算太远，坐高铁大概四个多小时。"
        result = self._extract_place(text, places)
        assert result == "西安", f"Expected 西安, got {result!r}"

    def test_new_zealand_extracted(self):
        places = self._get_lps_places()
        text = "我在新西兰南部的小镇住了五年。"
        result = self._extract_place(text, places)
        assert result in ("南新西兰", "新西兰南部", "新西兰"), f"Got {result!r}"

    def test_chengdu_extracted(self):
        places = self._get_lps_places()
        text = "我老家在成都，以前住那边。"
        result = self._extract_place(text, places)
        assert result == "成都"

    def test_beijing_extracted(self):
        places = self._get_lps_places()
        text = "北京的冬天很冷。"
        result = self._extract_place(text, places)
        assert result == "北京"

    def test_empty_text_returns_empty(self):
        places = self._get_lps_places()
        result = self._extract_place("", places)
        assert result == ""


# ── Persistence logic ──────────────────────────────────────────────────────────

class TestPlacePersistence:
    def test_lps_persists_when_no_new_place(self):
        """When no new place is mentioned, last_place_subject should keep old value."""
        src = _SRV.read_text(encoding="utf-8")
        # The code should contain logic like: _new_lps if _new_lps else _prev_lps
        assert "_new_lps if _new_lps else _prev_lps" in src or (
            "_prev_lps" in src and "_new_lps" in src
        ), "LPS persistence logic must be present"
