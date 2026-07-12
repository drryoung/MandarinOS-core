"""
tests/conftest.py — pytest configuration for MandarinOS test suites.

Test tiers
──────────
Core unit/contract suite (default):
    python -m pytest tests/ -m "not live_server"
    • No live server required.
    • No internet access required.
    • No external credentials required.
    • Deterministic; zero failures expected.

Local integration suite:
    python -m pytest tests/ -m "live_server"
    Prerequisite: MandarinOS server running on http://localhost:8765
    Start server: python scripts/ui_server.py
    • Zero failures when the server is running.

Manual JavaScript verification:
    node tests/verify_asr_filler.js
    • 82+ assertions on ASR filler-suppression and semantic-category routing.

Deployment / operational tests:
    python -m pytest tests/test_deployment_hygiene.py
    • No server required; inspects repository and configuration files.
"""

import socket
import sys

import pytest


# ── Standalone scripts that pytest must not collect ────────────────────────────
# These files are standalone Python scripts named with a test_ prefix.  They
# have no pytest test functions and are intended to be run directly, not by
# pytest.  Collecting them causes module-level side effects (sys.stdout
# replacement, hardcoded file opens) that corrupt pytest's capture streams.
collect_ignore = [
    "test_p1_to_p2_transition.py",
    "test_hint_cascade.py",
    "test_scaffolding_transitions_v1.py",
    "test_diagnostic_engine.py",
    "test_diagnostic_integration.py",
    "test_diagnostic_p1.py",
]


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_server: test requires a running MandarinOS server at http://localhost:8765",
    )


def _server_reachable(host: str = "localhost", port: int = 8765, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def live_server_available():
    return _server_reachable()


def pytest_runtest_setup(item):
    if item.get_closest_marker("live_server"):
        if not _server_reachable():
            pytest.skip(
                "live_server: MandarinOS server not running on localhost:8765. "
                "Start with: python scripts/ui_server.py"
            )
