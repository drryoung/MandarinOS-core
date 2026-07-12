"""
Two-turn integration regression for the E4 client-merge defect fixed in
ui/app.js (`_runTurnInner()` / `_resolveNextEngineId()`).

Confirmed defect (read-only audit, frozen baseline commit
53584cee9e8c892ff77f12741d1fc89d9d09c7e7):
  * the server correctly writes response["state_update"]["current_engine"];
  * the primary Pattern-A handler `_runTurnInner()` did not consume it — it
    set window._currentEngineId only from top-level data.engine_id (the
    engine of the CURRENT frame), so the handoff never affected the next
    ordinary request;
  * runMirrorTurn() (Pattern B) already consumed the field, but is a
    separate mechanism that does not repair the ordinary conversation path.

This test drives the REAL, in-process HTTP /api/run_turn path exactly like
tests/test_spoken_question_routing_regression.py and tests/test_e4_topic_handoff.py,
and — critically — computes what the client's window._currentEngineId would
become after Turn N by invoking the ACTUAL production merge rule, not a
manual/hand-typed reimplementation of it. That rule lives in ui/app.js as
`_resolveNextEngineId()`; tests/e4_resolve_next_engine_id_cli.js extracts and
executes the verbatim function source (see tests/_load_app_js_helper.js) and
is invoked here via subprocess, so the redirected engine used to build the
Turn N+1 request is the literal output of the shipped client code path, never
inserted by hand.

Requires Node.js on PATH (used only to execute the real client-side helper,
not to reimplement it). Skips with a clear reason if Node is unavailable.
"""

import json
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_UI_SERVER_PATH = _REPO / "scripts" / "ui_server.py"
_RESOLVE_CLI = pathlib.Path(__file__).resolve().parent / "e4_resolve_next_engine_id_cli.js"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import importlib.util

_cache: dict = {}


def _load(name: str, path: pathlib.Path):
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
    return _load("ui_server_e4_client_handoff_tests", _UI_SERVER_PATH)


@pytest.fixture(scope="module")
def server_url(srv):
    """Spin up the real HTTP handler in-process so this test exercises the
    live /api/run_turn control flow exactly as the deployed server does."""
    port = 8993 + (id(srv) % 500)
    httpd = srv.ThreadedHTTPServer(("127.0.0.1", port), srv.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    url = f"http://127.0.0.1:{port}"
    yield url
    httpd.shutdown()


def _post(server_url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{server_url}/api/run_turn",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _run_turn(server_url: str, cs: dict, persona_id: str = "jianguo") -> dict:
    return _post(server_url, {
        "persona_id": persona_id,
        "next_question": True,
        "conversation_state": cs,
    })


def _base_cs(persona_id: str = "jianguo") -> dict:
    return {
        "persona_id": persona_id,
        "current_engine": "identity",
        "last_turn_was_answer": True,
        "last_counter_reply": "",
        "recent_persona_replies": [],
    }


def _resolve_next_engine_id_via_real_client_helper(frame_engine_id, state_update) -> str:
    """Invoke the REAL, verbatim ui/app.js `_resolveNextEngineId()` helper via
    Node — the exact function `_runTurnInner()` calls in production — instead
    of reimplementing its merge rule in Python."""
    if shutil.which("node") is None:
        pytest.skip("Node.js not available on PATH; cannot execute the real client helper")
    result = subprocess.run(
        ["node", str(_RESOLVE_CLI), json.dumps(frame_engine_id), json.dumps(state_update)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, (
        f"e4_resolve_next_engine_id_cli.js failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    return json.loads(result.stdout)["result"]


class TestE4ClientHandoffTwoTurnIntegration:
    """
    Turn N: incoming current_engine="identity"; learner asks a direct place
    question; response has engine_id="identity" (current frame) and
    state_update.current_engine="place" (E4 handoff for the NEXT request).

    Client application: the redirected engine for Turn N+1 is computed by
    calling the real `_resolveNextEngineId()` production helper — never
    inserted manually — after Turn N's frame has already been recorded under
    "identity".

    Turn N+1: the next request carries the redirected engine, and the next
    response's frame belongs to the redirected engine ("place"), proving the
    E4 handoff now has an end-to-end effect on the primary conversation path.
    """

    def test_place_question_handoff_redirects_next_turn_engine(self, server_url):
        cs = _base_cs()
        cs["last_answer"] = {"submitted_text": "重庆有什么特别的"}

        # ── Turn N ──────────────────────────────────────────────────────────
        d1 = _run_turn(server_url, cs)

        assert d1["engine_id"] == "identity", (
            "Turn N's frame must be attributed to the engine active when the "
            "request was made ('identity'), not to any future handoff engine."
        )
        state_update_1 = d1.get("state_update") or {}
        assert state_update_1.get("current_engine") == "place", (
            "Server must write the E4 handoff to state_update.current_engine "
            "for this scenario (place-feature question, direct-persona answer)."
        )

        # ── Client application (real production helper, not a manual insert) ─
        next_engine = _resolve_next_engine_id_via_real_client_helper(
            d1["engine_id"], state_update_1
        )
        assert next_engine == "place", (
            "The real _resolveNextEngineId() helper must resolve the NEXT "
            "request's engine to the handoff value, distinct from Turn N's "
            "current-frame engine_id."
        )

        # ── Turn N+1 ────────────────────────────────────────────────────────
        cs2 = dict(cs)
        cs2["current_engine"] = next_engine
        cs2["last_counter_reply"] = state_update_1.get("last_counter_reply", "")
        cs2["recent_persona_replies"] = state_update_1.get("recent_persona_replies", [])
        cs2["last_turn_was_answer"] = False
        cs2.pop("last_answer", None)

        d2 = _run_turn(server_url, cs2)

        assert d2["engine_id"] == "place", (
            f"Turn N+1's response frame must belong to the redirected engine "
            f"('place'), got {d2['engine_id']!r} — the E4 handoff must have an "
            f"end-to-end effect on the primary Pattern-A conversation path."
        )
        assert d2.get("frame_id"), "Turn N+1 must return a genuine continuation frame"

    def test_no_handoff_present_retains_engine_id_behaviour(self, server_url):
        """Control case: an ordinary answer that produces no E4 handoff must
        leave the next request on the SAME engine as data.engine_id — i.e.
        the fix must not invent a handoff where none exists."""
        cs = _base_cs()
        cs["last_answer"] = {"submitted_text": "小明"}  # plain name answer, no question

        d1 = _run_turn(server_url, cs)
        state_update_1 = d1.get("state_update") or {}
        assert not state_update_1.get("current_engine"), (
            "A plain answer with no learner question must not produce an E4 handoff"
        )

        next_engine = _resolve_next_engine_id_via_real_client_helper(
            d1["engine_id"], state_update_1
        )
        assert next_engine == d1["engine_id"], (
            "With no valid handoff present, the real helper must fall back to "
            "data.engine_id — the pre-fix behaviour — unchanged."
        )
