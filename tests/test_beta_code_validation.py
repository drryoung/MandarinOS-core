"""
Beta-code handoff — server-side validation module tests.

Coverage:
  1. is_well_formed: accepts exactly the website's MOS-BETA-XXXXXX format,
     rejects everything else (wrong length, wrong alphabet, missing prefix,
     empty, non-string-shaped garbage).
  2. validate_beta_code: malformed codes short-circuit to False without a
     network call.
  3. validate_beta_code: a website response of {"valid": true}/{"valid":
     false} is honoured for well-formed codes.
  4. validate_beta_code: any network/timeout/parse failure fails OPEN
     (returns True) — a transient outage must never strip a legitimate
     participant's code.
  5. validate_beta_code: a definitive result is cached; a second call
     within the TTL does not call the website again.
  6. validate_beta_code: an unknown/failed result is NOT cached — the next
     call retries rather than sticking on a guess.
"""

import importlib
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _import_bcv():
    if "beta_code_validation" in sys.modules:
        del sys.modules["beta_code_validation"]
    return importlib.import_module("beta_code_validation")


VALID_CODE = "MOS-BETA-234789"


class TestIsWellFormed:
    def test_accepts_valid_code(self):
        bcv = _import_bcv()
        assert bcv.is_well_formed(VALID_CODE) is True

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "MOS-BETA-23478",       # too short
            "MOS-BETA-2347890",     # too long
            "mos-beta-234789",      # lowercase
            "MOS-BETA-000000",      # excluded chars (0)
            "MOS-BETA-1I1O1L",      # excluded chars
            "NOT-A-CODE-234789",
            "MOS-BETA234789",       # missing hyphen
        ],
    )
    def test_rejects_malformed(self, bad):
        bcv = _import_bcv()
        assert bcv.is_well_formed(bad) is False

    def test_trims_whitespace_before_matching(self):
        bcv = _import_bcv()
        assert bcv.is_well_formed(f"  {VALID_CODE}  ") is True


class TestValidateBetaCode:
    def test_malformed_code_short_circuits_without_network_call(self):
        bcv = _import_bcv()
        with mock.patch.object(bcv, "_call_website") as mocked:
            result = bcv.validate_beta_code("not-a-real-code")
        assert result is False
        mocked.assert_not_called()

    def test_honours_definitive_true_from_website(self):
        bcv = _import_bcv()
        with mock.patch.object(bcv, "_call_website", return_value=True):
            assert bcv.validate_beta_code(VALID_CODE) is True

    def test_honours_definitive_false_from_website(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv, "_call_website", return_value=False):
            assert bcv.validate_beta_code(VALID_CODE) is False

    def test_fails_open_on_network_error(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv, "_call_website", return_value=None):
            assert bcv.validate_beta_code(VALID_CODE) is True

    def test_caches_a_definitive_result_within_ttl(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        clock = {"t": 0.0}
        with mock.patch.object(bcv, "_call_website", return_value=False) as mocked:
            bcv.validate_beta_code(VALID_CODE, _time_fn=lambda: clock["t"])
            clock["t"] += 1.0
            bcv.validate_beta_code(VALID_CODE, _time_fn=lambda: clock["t"])
        assert mocked.call_count == 1

    def test_does_not_cache_an_unknown_outcome(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv, "_call_website", return_value=None) as mocked:
            bcv.validate_beta_code(VALID_CODE)
            bcv.validate_beta_code(VALID_CODE)
        assert mocked.call_count == 2

    def test_cache_expires_after_ttl(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        clock = {"t": 0.0}
        with mock.patch.object(bcv, "_call_website", return_value=False) as mocked:
            bcv.validate_beta_code(VALID_CODE, _time_fn=lambda: clock["t"])
            clock["t"] += bcv._CACHE_TTL_SECONDS + 1
            bcv.validate_beta_code(VALID_CODE, _time_fn=lambda: clock["t"])
        assert mocked.call_count == 2
