"""Tests for the offline ASR trace join-and-report tool.

Covers: complete joined trace, interim-selected failure, final-selected
success, missing client half, missing server half, duplicate records,
malformed JSON, displayed/submitted mismatch, and Unicode Chinese text.
The source fixture file is never modified by the tool (read-only guarantee).
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "report_asr_traces", _REPO / "scripts" / "report_asr_traces.py"
)
rpt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rpt)


def _client(trace_id, **kw):
    rec = {"kind": "client_bundle", "trace_id": trace_id, "input_path": "microphone",
           "device": {"is_mobile": False, "user_agent": "Mozilla/5.0 Chrome/120 Safari/537",
                      "lang": "zh-CN", "continuous": True, "interim_results": True},
           "events": []}
    rec.update(kw)
    return rec


def _server(trace_id, **kw):
    rec = {"kind": "server_turn", "trace_id": trace_id, "normalizer": "_normalize_zh_for_routing"}
    rec.update(kw)
    return rec


def _write_jsonl(records, extra_lines=None):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    for r in records:
        tmp.write(json.dumps(r, ensure_ascii=False) + "\n")
    for line in (extra_lines or []):
        tmp.write(line + "\n")
    tmp.close()
    return tmp.name


def _row_by_id(rows, tid):
    return next(r for r in rows if r["trace_id"] == tid)


class TestReportAsrTraces(unittest.TestCase):
    def test_complete_joined_trace(self):
        recs = [
            _client("t-complete",
                    displayed_transcript="重庆有什么特别的",
                    submitted_transcript="重庆有什么特别的",
                    selected_transcript="重庆有什么特别的",
                    selected_source="final", finish_reason="silence",
                    events=[{"t": 1, "type": "asr_result", "is_final": True,
                             "chunk_final": "重庆有什么特别的", "chunk_interim": ""}]),
            _server("t-complete", server_raw_input="重庆有什么特别的",
                    routing_text="重庆有什么特别的", intent="user_question",
                    user_asked_question=True, response_source="counter_reply",
                    final_response_text="重庆的夜景非常漂亮。"),
        ]
        path = _write_jsonl(recs)
        rows, errors = rpt.build_rows([path])
        self.assertEqual(errors, [])
        r = _row_by_id(rows, "t-complete")
        self.assertTrue(r["has_client"] and r["has_server"])
        self.assertEqual(r["flags"], [])
        self.assertFalse(r["failed"])

    def test_interim_selected_failure(self):
        recs = [
            _client("t-interim",
                    displayed_transcript="重庆好吃",
                    submitted_transcript="重庆好吃",
                    selected_transcript="重庆好吃",
                    selected_source="interim", finish_reason="silence",
                    events=[{"t": 1, "type": "asr_result", "is_final": False,
                             "chunk_final": "", "chunk_interim": "重庆好吃"}]),
            _server("t-interim", server_raw_input="重庆好吃", routing_text="重庆好吃",
                    intent="question", user_asked_question=False,
                    response_source="frame_text",
                    final_response_text="这个我不太清楚，我们可以聊聊别的。"),
        ]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-interim")
        self.assertIn(rpt.FLAG_INTERIM_SUBMITTED, r["flags"])
        self.assertTrue(r["failed"])  # generic fallback marker
        summary = rpt.summarize(rows)
        self.assertEqual(summary["mic_interim_selected_pct"], "100.0%")
        self.assertEqual(summary["failure_rate_interim_selected"], "100.0%")

    def test_final_selected_success(self):
        recs = [
            _client("t-final", displayed_transcript="你做什么工作",
                    submitted_transcript="你做什么工作", selected_transcript="你做什么工作",
                    selected_source="final", finish_reason="onend",
                    events=[{"t": 1, "type": "asr_result", "is_final": True,
                             "chunk_final": "你做什么工作", "chunk_interim": ""}]),
            _server("t-final", server_raw_input="你做什么工作", routing_text="你做什么工作",
                    intent="user_question", user_asked_question=True,
                    response_source="counter_reply", final_response_text="我是软件工程师。"),
        ]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-final")
        self.assertNotIn(rpt.FLAG_INTERIM_SUBMITTED, r["flags"])
        self.assertFalse(r["failed"])
        summary = rpt.summarize(rows)
        self.assertEqual(summary["failure_rate_final_selected"], "0.0%")

    def test_missing_client_half(self):
        recs = [_server("t-noclient", server_raw_input="你好", routing_text="你好",
                        intent="statement", final_response_text="你好。")]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-noclient")
        self.assertIn(rpt.FLAG_MISSING_CLIENT_RECORD, r["flags"])
        self.assertFalse(r["has_client"])

    def test_missing_server_half(self):
        recs = [_client("t-noserver", submitted_transcript="重庆好吃的",
                        displayed_transcript="重庆好吃的", selected_source="final")]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-noserver")
        self.assertIn(rpt.FLAG_MISSING_SERVER_RECORD, r["flags"])

    def test_empty_mic_turn_not_flagged_missing_server(self):
        recs = [_client("t-empty", empty=True, submitted_transcript="",
                        selected_source="none", finish_reason="onend")]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-empty")
        self.assertNotIn(rpt.FLAG_MISSING_SERVER_RECORD, r["flags"])

    def test_duplicate_records(self):
        recs = [
            _client("t-dup", submitted_transcript="你好", displayed_transcript="你好"),
            _client("t-dup", submitted_transcript="你好", displayed_transcript="你好"),
            _server("t-dup", server_raw_input="你好", routing_text="你好"),
        ]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-dup")
        self.assertIn(rpt.FLAG_DUPLICATE_TRACE_COMPONENT, r["flags"])

    def test_malformed_json_is_reported_and_skipped(self):
        recs = [_client("t-ok", submitted_transcript="你好", displayed_transcript="你好")]
        path = _write_jsonl(recs, extra_lines=["{not valid json", "   ", "42"])
        original = Path(path).read_text(encoding="utf-8")
        rows, errors = rpt.build_rows([path])
        # Two malformed lines: invalid JSON and a non-object (42).
        self.assertTrue(any("t-ok" == r["trace_id"] for r in rows))
        self.assertGreaterEqual(len(errors), 2)
        self.assertTrue(all(isinstance(e.lineno, int) for e in errors))
        # Source file must be untouched.
        self.assertEqual(Path(path).read_text(encoding="utf-8"), original)

    def test_display_submit_mismatch(self):
        recs = [
            _client("t-mismatch", displayed_transcript="不错",
                    submitted_transcript="羊肉不错", selected_transcript="羊肉不错",
                    selected_source="final"),
            _server("t-mismatch", server_raw_input="羊肉不错", routing_text="羊肉不错",
                    intent="statement", final_response_text="羊肉好吃。"),
        ]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-mismatch")
        self.assertIn(rpt.FLAG_DISPLAY_SUBMIT_MISMATCH, r["flags"])

    def test_submit_server_mismatch(self):
        recs = [
            _client("t-ssm", displayed_transcript="重庆有什么特别的",
                    submitted_transcript="重庆有什么特别的", selected_source="final"),
            _server("t-ssm", server_raw_input="刚吃有什么特别的",
                    routing_text="刚吃有什么特别的", intent="statement",
                    final_response_text="嗯。"),
        ]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-ssm")
        self.assertIn(rpt.FLAG_SUBMIT_SERVER_MISMATCH, r["flags"])
        self.assertTrue(r["failed"])

    def test_raw_routing_mismatch_and_display_of_normalization(self):
        recs = [
            _client("t-norm", displayed_transcript="重 庆 有 什么 特别",
                    submitted_transcript="重 庆 有 什么 特别", selected_source="final"),
            _server("t-norm", server_raw_input="重 庆 有 什么 特别",
                    routing_text="重庆有什么特别", intent="user_question",
                    user_asked_question=True, final_response_text="重庆有火锅。"),
        ]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-norm")
        self.assertIn(rpt.FLAG_RAW_ROUTING_MISMATCH, r["flags"])

    def test_intent_mismatch(self):
        recs = [
            _client("t-intent", displayed_transcript="你住在哪里啊",
                    submitted_transcript="你住在哪里啊？", selected_source="final"),
            _server("t-intent", server_raw_input="你住在哪里啊？",
                    routing_text="你住在哪里啊", intent="question",
                    user_asked_question=False, final_response_text="我是问：你叫什么？"),
        ]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-intent")
        self.assertIn(rpt.FLAG_INTENT_MISMATCH, r["flags"])

    def test_timestamp_order_error(self):
        recs = [
            _client("t-order", submitted_transcript="你好", displayed_transcript="你好",
                    events=[{"t": 5, "type": "asr_result", "chunk_interim": "你"},
                            {"t": 2, "type": "asr_result", "chunk_final": "你好"}]),
            _server("t-order", server_raw_input="你好", routing_text="你好"),
        ]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-order")
        self.assertIn(rpt.FLAG_TRACE_TIMESTAMP_ORDER_ERROR, r["flags"])

    def test_no_final_result(self):
        recs = [
            _client("t-nofinal", submitted_transcript="重庆好吃", displayed_transcript="重庆好吃",
                    selected_source="interim",
                    events=[{"t": 1, "type": "asr_result", "is_final": False,
                             "chunk_interim": "重庆好吃", "chunk_final": ""}]),
            _server("t-nofinal", server_raw_input="重庆好吃", routing_text="重庆好吃",
                    intent="user_question", user_asked_question=True,
                    final_response_text="重庆有火锅。"),
        ]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        r = _row_by_id(rows, "t-nofinal")
        self.assertIn(rpt.FLAG_NO_FINAL_RESULT, r["flags"])
        self.assertIn(rpt.FLAG_INTERIM_SUBMITTED, r["flags"])

    def test_unicode_in_outputs(self):
        recs = [
            _client("t-uni", displayed_transcript="你结婚了吗",
                    submitted_transcript="你结婚了吗？", selected_source="final"),
            _server("t-uni", server_raw_input="你结婚了吗？", routing_text="你结婚了吗",
                    intent="user_question", user_asked_question=True,
                    response_source="counter_reply", final_response_text="还没有，一个人也挺自在的。"),
        ]
        path = _write_jsonl(recs)
        rows, errors = rpt.build_rows([path])
        summary = rpt.summarize(rows)
        term = rpt.format_terminal(rows, summary, errors)
        md = rpt.format_markdown(rows, summary)
        csv_text = rpt.format_csv(rows)
        self.assertIn("还没有，一个人也挺自在的。", term)
        self.assertIn("你结婚了吗", md)
        self.assertIn("你结婚了吗", csv_text)

    def test_filters(self):
        recs = [
            _client("t-mic", input_path="microphone", submitted_transcript="重庆好吃",
                    displayed_transcript="重庆好吃", selected_source="final"),
            _server("t-mic", server_raw_input="重庆好吃", routing_text="重庆好吃"),
            _client("t-typed", input_path="typed_or_translated", submitted_transcript="你好",
                    displayed_transcript="你好", device={"is_mobile": False}),
            _server("t-typed", server_raw_input="你好", routing_text="你好"),
        ]
        path = _write_jsonl(recs)
        rows, _ = rpt.build_rows([path])
        args = rpt.build_arg_parser().parse_args(["--input-path", "microphone"])
        filtered = rpt.apply_filters(rows, args)
        self.assertEqual([r["trace_id"] for r in filtered], ["t-mic"])
        args2 = rpt.build_arg_parser().parse_args(["--utterance", "重庆"])
        self.assertEqual([r["trace_id"] for r in rpt.apply_filters(rows, args2)], ["t-mic"])

    def test_csv_and_markdown_files_written(self):
        recs = [
            _client("t-out", submitted_transcript="你好", displayed_transcript="你好",
                    selected_source="final"),
            _server("t-out", server_raw_input="你好", routing_text="你好",
                    final_response_text="你好。"),
        ]
        path = _write_jsonl(recs)
        with tempfile.TemporaryDirectory() as d:
            csv_path = str(Path(d) / "out.csv")
            md_path = str(Path(d) / "out.md")
            rc = rpt.main([path, "--csv", csv_path, "--markdown", md_path])
            self.assertEqual(rc, 0)
            self.assertTrue(Path(csv_path).exists())
            self.assertTrue(Path(md_path).exists())
            self.assertIn("你好", Path(md_path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
