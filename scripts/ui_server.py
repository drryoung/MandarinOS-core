#!/usr/bin/env python3
import argparse
import json
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[1]
UI_DIR = REPO_ROOT / "ui"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def safe_load_json(rel_path: str):
    p = Path(rel_path)
    if p.is_absolute():
        raise ValueError("Absolute paths are not allowed")
    if ".." in p.parts:
        raise ValueError("Parent directory traversal not allowed")
    full = (REPO_ROOT / p).resolve()
    if not str(full).startswith(str(REPO_ROOT)):
        raise ValueError("Path must be inside repo root")
    if not full.exists():
        raise FileNotFoundError(str(full))
    return json.loads(full.read_text(encoding="utf-8"))


class Handler(BaseHTTPRequestHandler):
    def _set_json(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

    def _set_text(self, code=200, content_type="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            f = UI_DIR / "index.html"
            if not f.exists():
                self._set_text(404)
                self.wfile.write(b"index.html not found")
                return
            self._set_text(200, "text/html; charset=utf-8")
            self.wfile.write(f.read_bytes())
            return
        
        # fixtures files (tests/fixtures) served under /fixtures/
        if path.startswith("/fixtures/"):
            rel = path[len("/fixtures/"):]  # e.g. "frame_open_card.json"
            f = FIXTURES_DIR / rel
            if not f.exists() or not f.is_file():
                self._set_text(404)
                self.wfile.write(b"not found")
                return
            self._set_text(200, "application/json; charset=utf-8")
            self.wfile.write(f.read_bytes())
            return

        # static files
        if path.startswith("/") and not path.startswith("/api/"):
            rel = path.lstrip("/")
            f = UI_DIR / rel
            if not f.exists() or not f.is_file():
                self._set_text(404)
                self.wfile.write(b"not found")
                return
            ctype = "text/javascript; charset=utf-8" if f.suffix == ".js" else "text/css; charset=utf-8" if f.suffix == ".css" else "text/plain; charset=utf-8"
            self._set_text(200, ctype)
            self.wfile.write(f.read_bytes())
            return

        if path == "/api/cards":
            qs = parse_qs(parsed.query)
            p = qs.get("path", ["tests/fixtures/cards.fixture.json"])[0]
            try:
                cards = safe_load_json(p)
            except Exception as e:
                self._set_json(400)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return
            self._set_json(200)
            self.wfile.write(json.dumps(cards, ensure_ascii=False).encode("utf-8"))
            return

        self._set_text(404)
        self.wfile.write(b"not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/run_turn":
            self._set_json(404)
            self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except Exception as e:
            self._set_json(400)
            self.wfile.write(json.dumps({"error": f"invalid json body: {e}"}).encode("utf-8"))
            return

        frame_path = data.get("frame_path")
        cards_index_path = data.get("cards_index_path", "tests/fixtures/cards_index.fixture.json")
        cards_path = data.get("cards_path", "tests/fixtures/cards.fixture.json")
        env = data.get("env", "prod")

        engine_id = data.get("engine_id")
        frame_id = data.get("frame_id")

        if not frame_path and not (engine_id and frame_id):
            self._set_json(400)
            self.wfile.write(json.dumps({"error": "Provide either frame_path OR (engine_id + frame_id)"}).encode("utf-8"))
            return

        # Load frame (Step 5 safety: use frame_path until we wire engine_id/frame_id lookup)
        if not frame_path:
            self._set_json(400)
            self.wfile.write(json.dumps({"error": "engine_id/frame_id lookup not wired yet. Please provide frame_path for now."}).encode("utf-8"))
            return

        try:
            frame = safe_load_json(frame_path)
            cards_index = safe_load_json(cards_index_path)
            cards = safe_load_json(cards_path)
        except Exception as e:
            self._set_json(400)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        # infer engine_affordances
        eng_aff = data.get("engine_affordances")
        if eng_aff is None:
            eid = frame.get("engine_id") if isinstance(frame, dict) else None
            eng_aff = {eid: {"open_card": True}} if eid else {}

        # call engine.process_turn
        try:
            from runtime import engine

            emitted = []

            def emitter(ev):
                emitted.append(ev)

            turn_uid = data.get("turn_uid", "ui_sim_turn")
            engine.process_turn(turn_uid, frame, eng_aff, cards_index, cards, emitter, env=env)

            # UI sim injection: modeled options (fixture-driven)
            ui_sim = frame.get("ui_sim") if isinstance(frame, dict) else None
            opts = ui_sim.get("options_available") if isinstance(ui_sim, dict) else None
            if isinstance(opts, dict):
                emitted.append({
                    "type": "OPTIONS_AVAILABLE",
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "payload": opts
                })

        except Exception as e:
            self._set_json(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self._set_json(200)
        self.wfile.write(json.dumps({"trace": emitted}, ensure_ascii=False).encode("utf-8"))
        return


def run(port: int):
    server = ThreadingHTTPServer(("", port), Handler)
    print(f"Open http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run(args.port)


if __name__ == "__main__":
    main()
