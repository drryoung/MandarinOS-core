"""
Beta-code handoff — server-side validation module tests.

Coverage:
  1. is_well_formed: accepts exactly the website's MOS-BETA-XXXXXX format,
     rejects everything else (wrong length, wrong alphabet, missing prefix,
     empty, non-string-shaped garbage).
  2. validate_beta_code: malformed codes short-circuit to "invalid" without
     a network call (rule C).
  3. validate_beta_code: an upstream {"valid": true}/{"valid": false}
     response is honoured for well-formed codes -> "valid"/"invalid".
  4. validate_beta_code: upstream timeout, connection failure, non-2xx
     (5xx) status, and malformed/unexpected JSON all resolve to
     "temporarily_unavailable" — NEVER "valid". This is the tri-state
     contract correction: an earlier version of this module collapsed all
     of these into a plain `True`, making an outage indistinguishable
     from a confirmed-active code.
  5. validate_beta_code: only a definitive "valid"/"invalid" result is
     cached; a second call within the TTL does not call the website again.
  6. validate_beta_code: "temporarily_unavailable" outcomes are NEVER
     cached — the next call retries rather than sticking on a guess (and
     an outage can never "poison" the cache with a false negative either).
"""

import importlib
import socket
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


class TestValidateBetaCodeTriState:
    """validate_beta_code() must return exactly one of the three string
    constants — VALID, INVALID, TEMPORARILY_UNAVAILABLE — never a bool."""

    def test_malformed_code_short_circuits_without_network_call(self):
        bcv = _import_bcv()
        with mock.patch.object(bcv, "_call_website") as mocked:
            result = bcv.validate_beta_code("not-a-real-code")
        assert result == bcv.INVALID
        mocked.assert_not_called()

    def test_upstream_active_response_is_valid(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv, "_call_website", return_value=True):
            assert bcv.validate_beta_code(VALID_CODE) == bcv.VALID

    def test_upstream_inactive_or_nonexistent_response_is_invalid(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv, "_call_website", return_value=False):
            assert bcv.validate_beta_code(VALID_CODE) == bcv.INVALID

    def test_indeterminate_call_website_result_is_temporarily_unavailable(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv, "_call_website", return_value=None):
            assert bcv.validate_beta_code(VALID_CODE) == bcv.TEMPORARILY_UNAVAILABLE

    def test_result_is_never_a_plain_boolean(self):
        """Regression guard for the outage/validity conflation this pass
        corrected: the return value must always be a status string."""
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv, "_call_website", return_value=True):
            result = bcv.validate_beta_code(VALID_CODE)
        assert not isinstance(result, bool)
        assert isinstance(result, str)


class TestCallWebsiteTransportOutcomes:
    """_call_website() must map every non-definitive transport outcome to
    None (never raise, never guess True), which validate_beta_code() then
    surfaces as TEMPORARILY_UNAVAILABLE."""

    def test_timeout_is_temporarily_unavailable(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv.urllib.request, "urlopen", side_effect=socket.timeout("timed out")):
            assert bcv.validate_beta_code(VALID_CODE) == bcv.TEMPORARILY_UNAVAILABLE

    def test_connection_failure_is_temporarily_unavailable(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(
            bcv.urllib.request, "urlopen", side_effect=bcv.urllib.error.URLError("connection refused")
        ):
            assert bcv.validate_beta_code(VALID_CODE) == bcv.TEMPORARILY_UNAVAILABLE

    def test_upstream_5xx_is_temporarily_unavailable(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        http_error = bcv.urllib.error.HTTPError(
            bcv._VALIDATE_URL, 503, "Service Unavailable", {}, None
        )
        with mock.patch.object(bcv.urllib.request, "urlopen", side_effect=http_error):
            assert bcv.validate_beta_code(VALID_CODE) == bcv.TEMPORARILY_UNAVAILABLE

    def test_malformed_upstream_json_is_temporarily_unavailable(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()

        class _FakeResponse:
            status = 200

            def read(self):
                return b"not valid json {{{"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch.object(bcv.urllib.request, "urlopen", return_value=_FakeResponse()):
            assert bcv.validate_beta_code(VALID_CODE) == bcv.TEMPORARILY_UNAVAILABLE

    def test_unexpected_json_shape_is_temporarily_unavailable(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()

        class _FakeResponse:
            status = 200

            def read(self):
                return b'{"something_else": true}'

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch.object(bcv.urllib.request, "urlopen", return_value=_FakeResponse()):
            assert bcv.validate_beta_code(VALID_CODE) == bcv.TEMPORARILY_UNAVAILABLE


class TestCacheBehavior:
    def test_caches_a_valid_result_within_ttl(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        clock = {"t": 0.0}
        with mock.patch.object(bcv, "_call_website", return_value=True) as mocked:
            bcv.validate_beta_code(VALID_CODE, _time_fn=lambda: clock["t"])
            clock["t"] += 1.0
            bcv.validate_beta_code(VALID_CODE, _time_fn=lambda: clock["t"])
        assert mocked.call_count == 1

    def test_caches_an_invalid_result_within_ttl(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        clock = {"t": 0.0}
        with mock.patch.object(bcv, "_call_website", return_value=False) as mocked:
            bcv.validate_beta_code(VALID_CODE, _time_fn=lambda: clock["t"])
            clock["t"] += 1.0
            bcv.validate_beta_code(VALID_CODE, _time_fn=lambda: clock["t"])
        assert mocked.call_count == 1

    def test_does_not_cache_a_temporarily_unavailable_outcome(self):
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv, "_call_website", return_value=None) as mocked:
            bcv.validate_beta_code(VALID_CODE)
            bcv.validate_beta_code(VALID_CODE)
        assert mocked.call_count == 2

    def test_an_outage_does_not_poison_the_cache_for_the_next_real_check(self):
        """An unavailable outcome must never get cached as either valid or
        invalid — the very next call must still hit the network."""
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv, "_call_website", side_effect=[None, True]) as mocked:
            first = bcv.validate_beta_code(VALID_CODE)
            second = bcv.validate_beta_code(VALID_CODE)
        assert first == bcv.TEMPORARILY_UNAVAILABLE
        assert second == bcv.VALID
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

    def test_cache_keys_are_not_logged(self, capsys):
        """No log/print of the code itself anywhere in the validation path."""
        bcv = _import_bcv()
        bcv._reset_cache_for_tests()
        with mock.patch.object(bcv, "_call_website", return_value=True):
            bcv.validate_beta_code(VALID_CODE)
        captured = capsys.readouterr()
        assert VALID_CODE not in captured.out
        assert VALID_CODE not in captured.err
