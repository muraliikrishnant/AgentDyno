import json
import pytest

from agentdyno.gateway.spans import SpanRecorder, _percentile


def test_percentile_empty_list():
    assert _percentile([], 0.99) == 0.0


def test_percentile_returns_exact_value_for_single_item():
    assert _percentile([5.0], 0.99) == 5.0


def test_percentile_interpolates_between_values():
    assert _percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5


def test_record_token_stores_first_token_time():
    recorder = SpanRecorder("test-model", "test-tier", "test-role")

    recorder.record_token(10.0)
    recorder.record_token(10.5)
    recorder.record_token(11.0)

    assert recorder.t_first_token == 10.0
    assert recorder._token_times == [10.0, 10.5, 11.0]


def test_finalize_calculates_span_metrics(tmp_path):
    recorder = SpanRecorder("test-model", "test-tier", "test-role")

    recorder.t_request_start = 0.0
    recorder.record_token(0.5)
    recorder.record_token(0.7)
    recorder.record_token(0.9)

    span = recorder.finalize(
        prompt_tokens=100,
        completion_tokens=3,
        spans_file=tmp_path / "spans.jsonl",
    )

    assert span["ttft_s"] == 0.5
    assert span["itl_mean_s"] == 0.2
    assert span["decode_throughput_tok_s"] == 7.5
    assert span["prompt_tokens"] == 100
    assert span["completion_tokens"] == 3
    assert span["wall_clock_s"] == 0.9

def test_finalize_calculates_itl_p99(tmp_path):
    recorder = SpanRecorder("test-model", "test-tier", "test-role")

    recorder.t_request_start = 0.0
    recorder.record_token(0.5)
    recorder.record_token(0.6)
    recorder.record_token(0.8)
    recorder.record_token(1.2)

    span = recorder.finalize(
        prompt_tokens=10,
        completion_tokens=4,
        spans_file=tmp_path / "spans.jsonl",
    )

    assert span["itl_p99_s"] == pytest.approx(0.396)

def test_finalize_writes_jsonl_file(tmp_path):
    spans_file = tmp_path / "spans.jsonl"
    recorder = SpanRecorder("test-model", "test-tier", "test-role")

    recorder.t_request_start = 0.0
    recorder.record_token(0.5)

    recorder.finalize(
        prompt_tokens=20,
        completion_tokens=1,
        spans_file=spans_file,
    )

    assert spans_file.exists()

    lines = spans_file.read_text().splitlines()
    assert len(lines) == 1

    span = json.loads(lines[0])
    assert span["model"] == "test-model"
    assert span["prompt_tokens"] == 20
    assert span["completion_tokens"] == 1

def test_finalize_without_tokens(tmp_path):
    recorder = SpanRecorder("test-model", "test-tier", "test-role")

    recorder.t_request_start = 0.0

    span = recorder.finalize(
        prompt_tokens=50,
        completion_tokens=0,
        spans_file=tmp_path / "spans.jsonl",
    )

    assert span["t_first_token"] is None
    assert span["ttft_s"] is None
    assert span["itl_mean_s"] == 0.0
    assert span["itl_p99_s"] == 0.0
    assert span["decode_throughput_tok_s"] == 0.0
    assert span["completion_tokens"] == 0