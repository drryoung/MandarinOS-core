#!/usr/bin/env python3
import argparse
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import mimetypes

REPO_ROOT   = Path(__file__).resolve().parents[1]
UI_DIR      = REPO_ROOT / "ui"
RUNTIME_DIR = REPO_ROOT / "runtime"

print("[ui_server] REPO_ROOT =", REPO_ROOT)
print("[ui_server] UI_DIR    =", UI_DIR)
print("[ui_server] RUNTIME_DIR =", RUNTIME_DIR)

# ── Load runtime indexes at startup ──────────────────────────────────────────
_frt_path = RUNTIME_DIR / "out_phase7" / "frame_render_tokens.runtime.json"
_ci_path  = RUNTIME_DIR / "out_phase7" / "cards_index.runtime.json"
_fo_path  = RUNTIME_DIR / "out_phase7" / "frame_options.runtime.json"

_frame_tokens  = {}
_cards_by_word_id = {}
_frame_options = {}
_frames_by_id  = {}

if _frt_path.is_file():
    _frame_tokens = json.loads(_frt_path.read_text(encoding="utf-8")).get("frames", {})
    print(f"[ui_server] frame_render_tokens loaded ({len(_frame_tokens)} frames)")
else:
    print(f"[ui_server] WARNING: frame_render_tokens not found at {_frt_path}")

if _ci_path.is_file():
    _cards_by_word_id = json.loads(_ci_path.read_text(encoding="utf-8")).get("by_word_id", {})
    print(f"[ui_server] cards_index loaded ({len(_cards_by_word_id)} entries)")
else:
    print(f"[ui_server] WARNING: cards_index not found at {_ci_path}")

if _fo_path.is_file():
    _frame_options = json.loads(_fo_path.read_text(encoding="utf-8")).get("frames", {})
    print(f"[ui_server] frame_options loaded ({len(_frame_options)} frames)")
else:
    print(f"[ui_server] WARNING: frame_options not found at {_fo_path}")

# Load frames for frame_text lookup
for _fname in ["p1_frames.json", "p2_frames.json"]:
    _fp = REPO_ROOT / _fname
    if _fp.is_file():
        _fdata = json.loads(_fp.read_text(encoding="utf-8"))
        for _fr in _fdata.get("frames", []):
            _frames_by_id[_fr["id"]] = _fr
print(f"[ui_server] frames_by_id loaded ({len(_frames_by_id)} frames)")


def _stub_card_id(frame_id: str):
    """Return card_id for the first word token in the frame, or None."""
    tokens = _frame_tokens.get(frame_id, [])
    for tok in tokens:
        if tok.get("t") == "word":
            word_id = tok.get("id")
            card_id = _cards_by_word_id.get(word_id)
            print(f"[ui_server] _stub_card_id: frame={frame_id} word_id={word_id} card_id={card_id}")
            return card_id
    print(f"[ui_server] _stub_card_id: no word token found for frame={frame_id}")
    return None


# ── HTTP Handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        if path == "/api/cards":
            rel = qs.get("path", [None])[0]
            if not rel:
                self._json_error(400, "missing path param")
                return
            self._serve_file(REPO_ROOT / rel, path)
            return

        if path.startswith("/runtime/"):
            file_path = RUNTIME_DIR / path[len("/runtime/"):]
        elif path.startswith("/ui/") or path in ("/ui", "/ui/index.html"):
            rel = path[len("/ui/"):] if path.startswith("/ui/") else "index.html"
            file_path = UI_DIR / rel
        elif path.endswith(".json") and "/" not in path.lstrip("/"):
            file_path = REPO_ROOT / path.lstrip("/")
        elif path == "/":
            self.send_response(302)
            self.send_header("Location", "/ui/index.html")
            self.end_headers()
            return
        else:
            file_path = UI_DIR / path.lstrip("/")

        self._serve_file(file_path, path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/api/run_turn":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except Exception as e:
                print(f"[ui_server] bad request body: {e}")
                payload = {}

            print(f"[ui_server] /api/run_turn: {payload}")

            frame_id  = payload.get("frame_id", "unknown")
            engine_id = payload.get("engine_id", "unknown")
            options   = _frame_options.get(frame_id, [])
            card_id   = _stub_card_id(frame_id)
            gold      = next((o for o in options if o.get("is_gold")), None)
            frame_rec = _frames_by_id.get(frame_id, {})

            response = {
                "turn_uid":            payload.get("turn_uid", ""),
                "engine_id":           engine_id,
                "frame_id":            frame_id,
                "frame_text":          frame_rec.get("text", ""),
                "result":              "ok",
                "options":             options,
                "option_count":        len(options),
                "gold_option_present": gold is not None,
                "card_id":             gold["card_id"] if gold else card_id,
                "system_note":         "phase7.4 static options"
            }

            data = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(f"404 Not Found: {path}".encode())

    def _serve_file(self, file_path: Path, original_path: str):
        if file_path.is_file():
            mime, _ = mimetypes.guess_type(str(file_path))
            mime = mime or "application/octet-stream"
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"404 Not Found: {original_path}\nResolved: {file_path}".encode())

    def _json_error(self, code: int, msg: str):
        data = json.dumps({"error": msg}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print(f"[ui_server] {self.address_string()} - {format % args}")


if __name__ == "__main__":
    port = 8765
    print(f"[ui_server] Listening on http://localhost:{port}")
    HTTPServer(("", port), Handler).serve_forever()
