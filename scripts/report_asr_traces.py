#!/usr/bin/env python3
"""Offline join-and-report tool for ASR diagnostic traces.

Reads one or more JSONL trace files produced by the diagnostics/asr-trace
instrumentation (see scripts/ui_server.py `_diag_append` and ui/app.js
`AsrDiag`), joins the client (`client_bundle`) and server (`server_turn`)
records by `trace_id`, and prints a per-turn pipeline plus summary counts and
divergence flags.

This tool is READ-ONLY and OFFLINE:
  * it never modifies or overwrites the source files;
  * it never sends any data over the network.

Usage:
    python scripts/report_asr_traces.py [FILE ...] [options]

If no FILE is given it defaults to data/diag/asr_traces.jsonl (relative to the
repo root). See --help for filters and output options.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_FILE = REPO_ROOT / "data" / "diag" / "asr_traces.jsonl"

# Divergence flag names (kept as constants so tests/consumers can reference them).
FLAG_DISPLAY_SUBMIT_MISMATCH = "DISPLAY_SUBMIT_MISMATCH"
FLAG_SUBMIT_SERVER_MISMATCH = "SUBMIT_SERVER_MISMATCH"
FLAG_RAW_ROUTING_MISMATCH = "RAW_ROUTING_MISMATCH"
FLAG_INTERIM_SUBMITTED = "INTERIM_SUBMITTED"
FLAG_NO_FINAL_RESULT = "NO_FINAL_RESULT"
FLAG_INTENT_MISMATCH = "INTENT_MISMATCH"
FLAG_DUPLICATE_TRACE_COMPONENT = "DUPLICATE_TRACE_COMPONENT"
FLAG_MISSING_CLIENT_RECORD = "MISSING_CLIENT_RECORD"
FLAG_MISSING_SERVER_RECORD = "MISSING_SERVER_RECORD"
FLAG_TRACE_TIMESTAMP_ORDER_ERROR = "TRACE_TIMESTAMP_ORDER_ERROR"

# Heuristic markers of a generic "non-answer" partner reply. Used only to
# estimate failure rate when no human label is available; clearly a heuristic.
GENERIC_FALLBACK_MARKERS = [
    "这个我不太清楚",
    "这个我不太确定",
    "我不太清楚",
    "我不太确定",
    "我们可以聊聊",
    "这样挺好",
    "真不错啊",
    "你可以问问别人",
]


# ── Parsing ───────────────────────────────────────────────────────────────────

class ParseError:
    def __init__(self, file: str, lineno: int, error: str):
        self.file = file
        self.lineno = lineno
        self.error = error

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"ParseError({self.file}:{self.lineno}: {self.error})"


def parse_jsonl_files(paths: List[str]) -> Tuple[List[Dict[str, Any]], List[ParseError]]:
    """Parse JSONL files without modifying them.

    Returns (records, parse_errors). Malformed lines are reported (file +
    line number + error) and skipped; processing continues.
    """
    records: List[Dict[str, Any]] = []
    errors: List[ParseError] = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, start=1):
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        rec = json.loads(s)
                    except Exception as e:
                        errors.append(ParseError(str(path), lineno, str(e)))
                        continue
                    if not isinstance(rec, dict):
                        errors.append(ParseError(str(path), lineno, "record is not a JSON object"))
                        continue
                    records.append(rec)
        except FileNotFoundError:
            errors.append(ParseError(str(path), 0, "file not found"))
        except OSError as e:
            errors.append(ParseError(str(path), 0, f"could not read file: {e}"))
    return records, errors


# ── Joining ─────────────────────────────────────────────────────────────────

class Turn:
    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self.clients: List[Dict[str, Any]] = []
        self.servers: List[Dict[str, Any]] = []

    @property
    def client(self) -> Optional[Dict[str, Any]]:
        return self.clients[0] if self.clients else None

    @property
    def server(self) -> Optional[Dict[str, Any]]:
        return self.servers[0] if self.servers else None


def join_records(records: List[Dict[str, Any]]) -> Dict[str, Turn]:
    """Group records into turns keyed by trace_id."""
    turns: Dict[str, Turn] = {}
    for rec in records:
        tid = str(rec.get("trace_id") or "").strip()
        if not tid:
            tid = "(no-trace-id)"
        turn = turns.setdefault(tid, Turn(tid))
        kind = rec.get("kind")
        if kind == "client_bundle":
            turn.clients.append(rec)
        elif kind == "server_turn":
            turn.servers.append(rec)
        else:
            # Unknown kind: attach wherever it looks most useful (heuristic).
            if "events" in rec or "selected_source" in rec:
                turn.clients.append(rec)
            else:
                turn.servers.append(rec)
    return turns


# ── Analysis ──────────────────────────────────────────────────────────────────

def _strip_trailing_punct(s: str) -> str:
    return (s or "").strip().rstrip("？?！!。.，, ").strip()


def _first_nonempty(*vals: Any) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _events(client: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not client:
        return []
    evs = client.get("events")
    return evs if isinstance(evs, list) else []


def interim_transcripts(client: Optional[Dict[str, Any]]) -> List[str]:
    out = []
    for e in _events(client):
        if e.get("type") == "asr_result" and (e.get("chunk_interim") or "").strip():
            out.append(e.get("chunk_interim"))
    return out


def final_transcripts(client: Optional[Dict[str, Any]]) -> List[str]:
    out = []
    for e in _events(client):
        if e.get("type") == "asr_result" and (e.get("chunk_final") or "").strip():
            out.append(e.get("chunk_final"))
    return out


def _device_type(client: Optional[Dict[str, Any]]) -> str:
    if not client:
        return "unknown"
    dev = client.get("device") or {}
    if isinstance(dev, dict) and "is_mobile" in dev:
        return "mobile" if dev.get("is_mobile") else "desktop"
    return "unknown"


def _browser(client: Optional[Dict[str, Any]]) -> str:
    if not client:
        return "unknown"
    dev = client.get("device") or {}
    ua = (dev.get("user_agent") if isinstance(dev, dict) else "") or ""
    ua_l = ua.lower()
    if "edg/" in ua_l or "edge" in ua_l:
        return "Edge"
    if "chrome" in ua_l and "safari" in ua_l:
        return "Chrome"
    if "firefox" in ua_l:
        return "Firefox"
    if "safari" in ua_l:
        return "Safari"
    return "other" if ua else "unknown"


def _looks_like_question(text: str) -> bool:
    t = text or ""
    if any(q in t for q in ("？", "?")):
        return True
    if t.endswith("吗") or t.endswith("呢"):
        return True
    return False


def _is_generic_fallback(text: str, extra_markers: Optional[List[str]] = None) -> bool:
    t = text or ""
    markers = GENERIC_FALLBACK_MARKERS + list(extra_markers or [])
    return any(m in t for m in markers)


def analyze_turn(turn: Turn, extra_fail_markers: Optional[List[str]] = None) -> Dict[str, Any]:
    """Derive a flat row for one turn, including divergence flags."""
    client = turn.client
    server = turn.server
    flags: List[str] = []

    input_path = (client.get("input_path") if client else None) or "unknown"

    displayed = (client.get("displayed_transcript") if client else "") or ""
    submitted = (client.get("submitted_transcript") if client else "") or ""
    selected = (client.get("selected_transcript") if client else "") or ""
    selected_source = (client.get("selected_source") if client else "") or ""
    finish_reason = (client.get("finish_reason") if client else "") or ""
    matched_option = client.get("matched_option") if client else None

    server_raw = (server.get("server_raw_input") if server else "") or ""
    routing = (server.get("routing_text") if server else "") or ""
    normalizer = (server.get("normalizer") if server else "") or ""
    intent = (server.get("intent") if server else "") or ""
    response_source = (server.get("response_source") if server else "") or ""
    final_response = (server.get("final_response_text") if server else "") or ""
    user_asked_question = bool(server.get("user_asked_question")) if server else False

    interims = interim_transcripts(client)
    finals = final_transcripts(client)
    is_mic = input_path == "microphone"
    is_empty = bool(client.get("empty")) if client else False

    # ── Structural join flags ──────────────────────────────────────────────
    if len(turn.clients) > 1 or len(turn.servers) > 1:
        flags.append(FLAG_DUPLICATE_TRACE_COMPONENT)
    if server and not client:
        flags.append(FLAG_MISSING_CLIENT_RECORD)
    if client and not server and not is_empty:
        # Empty (no-speech) mic turns legitimately never submit -> no server half.
        flags.append(FLAG_MISSING_SERVER_RECORD)

    # ── Content divergence flags ───────────────────────────────────────────
    if displayed and submitted and _strip_trailing_punct(displayed) != _strip_trailing_punct(submitted):
        flags.append(FLAG_DISPLAY_SUBMIT_MISMATCH)
    if submitted and server_raw and submitted.strip() != server_raw.strip():
        flags.append(FLAG_SUBMIT_SERVER_MISMATCH)
    if server_raw and routing and server_raw.strip() != routing.strip():
        flags.append(FLAG_RAW_ROUTING_MISMATCH)

    # ── ASR selection flags (microphone only) ──────────────────────────────
    if is_mic and not is_empty:
        if selected_source == "interim":
            flags.append(FLAG_INTERIM_SUBMITTED)
        if not finals and selected_source != "final":
            flags.append(FLAG_NO_FINAL_RESULT)

    # ── Intent heuristic flag ──────────────────────────────────────────────
    # Flag when server thinks the learner asked a question but intent is not
    # user_question, or the submitted text clearly looks like a question yet the
    # server did not classify it as one.
    if server:
        submitted_or_raw = submitted or server_raw
        if user_asked_question and intent and intent != "user_question":
            flags.append(FLAG_INTENT_MISMATCH)
        elif _looks_like_question(submitted_or_raw) and not user_asked_question:
            flags.append(FLAG_INTENT_MISMATCH)

    # ── Timestamp ordering flag (within client events) ─────────────────────
    last_t = None
    order_ok = True
    for e in _events(client):
        t = e.get("t")
        if isinstance(t, (int, float)):
            if last_t is not None and t < last_t:
                order_ok = False
                break
            last_t = t
    if not order_ok:
        flags.append(FLAG_TRACE_TIMESTAMP_ORDER_ERROR)

    # ── Failure heuristic (no human label available) ───────────────────────
    failed = (
        _is_generic_fallback(final_response, extra_fail_markers)
        or FLAG_SUBMIT_SERVER_MISMATCH in flags
        or FLAG_INTENT_MISMATCH in flags
    ) if server else False

    dev = client.get("device") if client else {}
    dev = dev if isinstance(dev, dict) else {}

    return {
        "trace_id": turn.trace_id,
        "input_path": input_path,
        "device_type": _device_type(client),
        "browser": _browser(client),
        "user_agent": dev.get("user_agent", ""),
        "lang": dev.get("lang", ""),
        "continuous": dev.get("continuous", ""),
        "interim_results": dev.get("interim_results", ""),
        "displayed_transcript": displayed,
        "interim_transcripts": interims,
        "final_transcripts": finals,
        "finish_reason": finish_reason,
        "selected_transcript": selected,
        "selected_source": selected_source or ("none" if is_mic else ""),
        "matched_option": matched_option,
        "submitted_transcript": submitted,
        "server_raw_input": server_raw,
        "routing_text": routing,
        "normalizer": normalizer,
        "intent": intent,
        "user_asked_question": user_asked_question,
        "response_source": response_source,
        "final_response_text": final_response,
        "started_at": (client.get("started_at") if client else "") or "",
        "server_received_at": (server.get("server_received_at") if server else "") or "",
        "flags": flags,
        "failed": failed,
        "empty": is_empty,
        "has_client": client is not None,
        "has_server": server is not None,
    }


# ── Filtering ─────────────────────────────────────────────────────────────────

def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def apply_filters(rows: List[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    out = []
    since = _parse_dt(getattr(args, "since", "") or "")
    until = _parse_dt(getattr(args, "until", "") or "")
    for r in rows:
        if args.trace_id and r["trace_id"] != args.trace_id:
            continue
        if args.input_path and r["input_path"] != args.input_path:
            continue
        if args.device_type and r["device_type"] != args.device_type:
            continue
        if args.finish_reason and r["finish_reason"] != args.finish_reason:
            continue
        if args.winner and r["selected_source"] != args.winner:
            continue
        if args.utterance:
            hay = " ".join([
                r["submitted_transcript"], r["displayed_transcript"],
                r["server_raw_input"], r["selected_transcript"],
            ])
            if args.utterance not in hay:
                continue
        if since or until:
            ts = _parse_dt(r["server_received_at"]) or _parse_dt(r["started_at"])
            if ts is not None:
                if since and ts < since:
                    continue
                if until and ts > until:
                    continue
        out.append(r)
    return out


# ── Summary ───────────────────────────────────────────────────────────────────

def _pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d):.1f}%" if d else "n/a"


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    mic = [r for r in rows if r["input_path"] == "microphone"]
    typed = [r for r in rows if r["input_path"] in ("typed", "translated", "typed_or_translated")]
    mic_non_empty = [r for r in mic if not r["empty"]]

    interim_sel = [r for r in mic_non_empty if r["selected_source"] == "interim"]
    final_sel = [r for r in mic_non_empty if r["selected_source"] == "final"]
    no_final = [r for r in mic_non_empty if FLAG_NO_FINAL_RESULT in r["flags"]]

    interim_failed = [r for r in interim_sel if r["failed"]]
    final_failed = [r for r in final_sel if r["failed"]]

    def _counter(key):
        c: Dict[str, int] = {}
        for r in rows:
            v = str(r.get(key) or "")
            c[v] = c.get(v, 0) + 1
        return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))

    def _device_browser_counter():
        c: Dict[str, int] = {}
        for r in rows:
            v = f"{r['device_type']}/{r['browser']}"
            c[v] = c.get(v, 0) + 1
        return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))

    display_submit = sum(1 for r in rows if FLAG_DISPLAY_SUBMIT_MISMATCH in r["flags"])
    submit_server = sum(1 for r in rows if FLAG_SUBMIT_SERVER_MISMATCH in r["flags"])

    return {
        "total_turns": len(rows),
        "total_mic_turns": len(mic),
        "total_typed_translated_turns": len(typed),
        "mic_interim_selected_pct": _pct(len(interim_sel), len(mic_non_empty)),
        "mic_no_final_pct": _pct(len(no_final), len(mic_non_empty)),
        "failure_rate_interim_selected": _pct(len(interim_failed), len(interim_sel)),
        "failure_rate_final_selected": _pct(len(final_failed), len(final_sel)),
        "display_submit_mismatch_count": display_submit,
        "submit_server_mismatch_count": submit_server,
        "counts_by_finish_reason": _counter("finish_reason"),
        "counts_by_device_browser": _device_browser_counter(),
        "counts_by_normalizer": _counter("normalizer"),
        "counts_by_response_source": _counter("response_source"),
    }


# ── Rendering ─────────────────────────────────────────────────────────────────

def _fmt_list(vals: List[str]) -> str:
    return " | ".join(vals) if vals else "(none)"


def format_terminal(rows: List[Dict[str, Any]], summary: Dict[str, Any],
                    parse_errors: List[ParseError]) -> str:
    buf = io.StringIO()
    w = buf.write

    if parse_errors:
        w("== PARSE ERRORS ==\n")
        for e in parse_errors:
            w(f"  {e.file}:{e.lineno}: {e.error}\n")
        w("\n")

    w("== PER-TURN PIPELINE ==\n")
    for r in rows:
        w(f"\ntrace_id: {r['trace_id']}\n")
        w(f"  input_path:          {r['input_path']}\n")
        w(f"  device/browser:      {r['device_type']}/{r['browser']}\n")
        w(f"  recognition config:  lang={r['lang']} continuous={r['continuous']} interim={r['interim_results']}\n")
        w(f"  displayed text:      {r['displayed_transcript'] or '(none)'}\n")
        w(f"  interim transcripts: {_fmt_list(r['interim_transcripts'])}\n")
        w(f"  final transcripts:   {_fmt_list(r['final_transcripts'])}\n")
        w(f"  finish reason:       {r['finish_reason'] or '(none)'}\n")
        w(f"  selected transcript: {r['selected_transcript'] or '(none)'}\n")
        w(f"  selected source:     {r['selected_source'] or '(none)'}\n")
        w(f"  matched option:      {r['matched_option'] if r['matched_option'] is not None else '(none)'}\n")
        w(f"  submitted transcript:{r['submitted_transcript'] or '(none)'}\n")
        w(f"  server raw input:    {r['server_raw_input'] or '(none)'}\n")
        w(f"  server routing text: {r['routing_text'] or '(none)'}\n")
        w(f"  normalizer:          {r['normalizer'] or '(none)'}\n")
        w(f"  detected intent:     {r['intent'] or '(none)'}\n")
        w(f"  response source:     {r['response_source'] or '(none)'}\n")
        w(f"  final response text: {r['final_response_text'] or '(none)'}\n")
        if r["flags"]:
            w(f"  >> FLAGS: {', '.join(r['flags'])}\n")

    w("\n== SUMMARY ==\n")
    for k, v in summary.items():
        if isinstance(v, dict):
            w(f"  {k}:\n")
            for kk, vv in v.items():
                w(f"      {kk or '(empty)'}: {vv}\n")
        else:
            w(f"  {k}: {v}\n")
    return buf.getvalue()


CSV_FIELDS = [
    "trace_id", "input_path", "device_type", "browser", "lang", "continuous",
    "interim_results", "displayed_transcript", "interim_transcripts",
    "final_transcripts", "finish_reason", "selected_transcript",
    "selected_source", "matched_option", "submitted_transcript",
    "server_raw_input", "routing_text", "normalizer", "intent",
    "user_asked_question", "response_source", "final_response_text",
    "started_at", "server_received_at", "failed", "flags",
]


def format_csv(rows: List[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        row = dict(r)
        row["interim_transcripts"] = " | ".join(r["interim_transcripts"])
        row["final_transcripts"] = " | ".join(r["final_transcripts"])
        row["flags"] = ",".join(r["flags"])
        writer.writerow(row)
    return buf.getvalue()


def format_markdown(rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    buf = io.StringIO()
    w = buf.write
    w("# ASR trace report\n\n")
    w("## Summary\n\n")
    for k, v in summary.items():
        if isinstance(v, dict):
            w(f"- **{k}**:\n")
            for kk, vv in v.items():
                w(f"    - `{kk or '(empty)'}`: {vv}\n")
        else:
            w(f"- **{k}**: {v}\n")
    w("\n## Per-turn pipeline\n\n")
    for r in rows:
        w(f"### `{r['trace_id']}` ({r['input_path']})\n\n")
        w(f"- device/browser: {r['device_type']}/{r['browser']}\n")
        w(f"- recognition: lang={r['lang']} continuous={r['continuous']} interim={r['interim_results']}\n")
        w(f"- displayed: {r['displayed_transcript'] or '(none)'}\n")
        w(f"- interim: {_fmt_list(r['interim_transcripts'])}\n")
        w(f"- final: {_fmt_list(r['final_transcripts'])}\n")
        w(f"- finish reason: {r['finish_reason'] or '(none)'}\n")
        w(f"- selected: {r['selected_transcript'] or '(none)'} (source: {r['selected_source'] or '(none)'})\n")
        w(f"- matched option: {r['matched_option'] if r['matched_option'] is not None else '(none)'}\n")
        w(f"- submitted: {r['submitted_transcript'] or '(none)'}\n")
        w(f"- server raw: {r['server_raw_input'] or '(none)'}\n")
        w(f"- routing: {r['routing_text'] or '(none)'}\n")
        w(f"- normalizer: {r['normalizer'] or '(none)'}\n")
        w(f"- intent: {r['intent'] or '(none)'}\n")
        w(f"- response source: {r['response_source'] or '(none)'}\n")
        w(f"- final response: {r['final_response_text'] or '(none)'}\n")
        if r["flags"]:
            w(f"- **FLAGS**: {', '.join(r['flags'])}\n")
        w("\n")
    return buf.getvalue()


# ── Orchestration ─────────────────────────────────────────────────────────────

def build_rows(paths: List[str], extra_fail_markers: Optional[List[str]] = None
               ) -> Tuple[List[Dict[str, Any]], List[ParseError]]:
    records, errors = parse_jsonl_files(paths)
    turns = join_records(records)
    rows = [analyze_turn(t, extra_fail_markers) for t in turns.values()]
    rows.sort(key=lambda r: (r["started_at"] or r["server_received_at"] or "", r["trace_id"]))
    return rows, errors


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="*", help="JSONL trace file(s). Default: data/diag/asr_traces.jsonl")
    p.add_argument("--trace-id", default="", help="only this trace_id")
    p.add_argument("--input-path", default="", help="microphone | typed | translated | typed_or_translated")
    p.add_argument("--device-type", default="", help="mobile | desktop")
    p.add_argument("--finish-reason", default="", help="filter by finish reason")
    p.add_argument("--winner", default="", help="final | interim | none")
    p.add_argument("--utterance", default="", help="substring to match in transcripts")
    p.add_argument("--since", default="", help="ISO datetime lower bound (inclusive)")
    p.add_argument("--until", default="", help="ISO datetime upper bound (inclusive)")
    p.add_argument("--fail-marker", action="append", default=[], help="extra generic-fallback marker (repeatable)")
    p.add_argument("--csv", default="", help="write CSV (one row per turn) to this path")
    p.add_argument("--markdown", default="", help="write Markdown report to this path")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = args.files or [str(DEFAULT_TRACE_FILE)]

    rows, errors = build_rows(paths, args.fail_marker)
    rows = apply_filters(rows, args)
    summary = summarize(rows)

    # Terminal report (UTF-8 safe).
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    print(format_terminal(rows, summary, errors))

    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(format_csv(rows))
        print(f"[report] wrote CSV: {args.csv}")
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as fh:
            fh.write(format_markdown(rows, summary))
        print(f"[report] wrote Markdown: {args.markdown}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
