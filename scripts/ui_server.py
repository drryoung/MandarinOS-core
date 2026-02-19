#!/usr/bin/env python3
import argparse
from email.mime import base
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

def resolve_frame_path_from_registry(engine_id: str, frame_id: str) -> str:
    """
    Look up the JSON file path for a frame using engine_id + frame_id.

    Expected file: runtime/frames_registry.py
    It must provide a function: get_frame_path(engine_id, frame_id) -> str
    """
    from runtime.frames_registry import get_frame_path  # local import to avoid circular issues
    return get_frame_path(engine_id, frame_id)


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

        try:
            if frame_path:
                frame = safe_load_json(frame_path)
            else:
                frame = load_frame_from_packs(engine_id, frame_id)
        except Exception as e:
            self._set_json(400)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        try:
            cards_index = safe_load_json(cards_index_path)
            cards = safe_load_json(cards_path)
        except Exception as e:
            self._set_json(400)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        eng_aff = data.get("engine_affordances")
        if eng_aff is None:
            eid = frame.get("engine_id") if isinstance(frame, dict) else None
            eng_aff = {eid: {"open_card": True}} if eid else {}

        try:
            from runtime import engine

            emitted = []

            def emitter(ev):
                emitted.append(ev)

            turn_uid = data.get("turn_uid", "ui_sim_turn")
            engine.process_turn(turn_uid, frame, eng_aff, cards_index, cards, emitter, env=env)
            # If the frame includes ui_sim options (fixtures), emit OPTIONS_AVAILABLE
            ui_sim = frame.get("ui_sim") if isinstance(frame, dict) else None
            opts = ui_sim.get("options_available") if isinstance(ui_sim, dict) else None
            if isinstance(opts, dict):
                emitted.append({
                    "type": "OPTIONS_AVAILABLE",
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "payload": opts
                })

            # Also allow options to be provided directly in the POST body (for p1/p2 frames)
            direct_opts = data.get("options_available")
            if isinstance(direct_opts, dict):
                emitted.append({
                    "type": "OPTIONS_AVAILABLE",
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "payload": direct_opts
                })

        except Exception as e:
            self._set_json(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self._set_json(200)
        self.wfile.write(json.dumps({"trace": emitted}, ensure_ascii=False).encode("utf-8"))
        return

        


def load_frame_from_packs(engine_id: str, frame_id: str) -> dict:
    """
    Load a frame from p1_frames.json / p2_frames.json using:
      frame["engine"] == engine_id
      frame["id"] == frame_id

    Then adapt it to runtime format:
      frame["engine_id"] and frame["frame_id"]
    """
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    pack_paths = [
        repo_root / "p1_frames.json",
        repo_root / "p2_frames.json",
    ]

    for path in pack_paths:
        if not path.exists():
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        frames = data.get("frames") or []
        for fr in frames:
            if not isinstance(fr, dict):
                continue
            if fr.get("engine") == engine_id and fr.get("id") == frame_id:
                # copy and adapt to the runtime keys used by runtime.engine.process_turn
                out = dict(fr)

                # adapt keys expected by runtime
                out["engine_id"] = engine_id
                out["frame_id"] = frame_id

                # minimal fields needed for OPEN_CARD resolution
                out["readiness_label"] = "READY_NO_CONVO_HINTS_BUT_CARDS_AVAILABLE"

                # Provide tokens used by cards_index lookup.
                # This lets your existing cards_index map resolve either by token or by frame_id.

                 # Build tokens that match cards_index keys (fixture uses "你好" and "identity.greeting")
                tokens = []

                # 1) token from Chinese text, strip common punctuation/spaces
                txt = out.get("text")
                if isinstance(txt, str):
                    cleaned = txt.strip().replace("！", "").replace("。", "").replace("？", "").replace("，", "").replace(" ", "")
                    if cleaned:
                        tokens.append(cleaned)

                # 2) token from engine + frame "group" (e.g., identity + greeting -> "identity.greeting")
                # frame_id format in packs is like "frame.greeting.hello"
                if isinstance(frame_id, str) and frame_id.startswith("frame."):
                    parts = frame_id.split(".")
                    # parts = ["frame", "greeting", "hello"]
                    if len(parts) >= 3:
                        tokens.append(f"{engine_id}.{parts[1]}")

                out["option_tokens"] = tokens


                # If your runtime expects affordances in the frame, keep open_card enabled.
                out["affordances"] = {"open_card": True}

                return out


    raise KeyError(f"Frame not found in p1/p2 packs for engine_id={engine_id}, frame_id={frame_id}")





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
