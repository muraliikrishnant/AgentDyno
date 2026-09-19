"""Computes TTFT/ITL/throughput from a stream of token timestamps and appends
one JSON span per model call to a JSONL file under data/spans/."""
from __future__ import annotations

import json
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SPANS_DIR = DATA_DIR / "spans"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


class SpanRecorder:
    """Accumulates timestamps for a single model call and writes a span."""

    def __init__(self, model: str, tier: str, role: str, trial_id: str | None = None):
        self.span_id = str(uuid.uuid4())
        self.model = model
        self.tier = tier
        self.role = role
        self.trial_id = trial_id
        self.t_request_start = time.monotonic()
        self.t_first_token: float | None = None
        self._token_times: list[float] = []
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def record_token(self, t: float) -> None:
        if self.t_first_token is None:
            self.t_first_token = t
        self._token_times.append(t)

    def finalize(self, prompt_tokens: int, completion_tokens: int, spans_file: Path | None = None) -> dict[str, Any]:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        t_end = self._token_times[-1] if self._token_times else time.monotonic()

        deltas = [
            self._token_times[i] - self._token_times[i - 1]
            for i in range(1, len(self._token_times))
        ]
        ttft = (self.t_first_token - self.t_request_start) if self.t_first_token else None
        decode_s = (t_end - self.t_first_token) if self.t_first_token else 0.0
        decode_throughput = completion_tokens / decode_s if decode_s > 0 else 0.0

        span = {
            "span_id": self.span_id,
            "trial_id": self.trial_id,
            "model": self.model,
            "tier": self.tier,
            "role": self.role,
            "t_request_start": self.t_request_start,
            "t_first_token": self.t_first_token,
            "ttft_s": ttft,
            "itl_mean_s": statistics.mean(deltas) if deltas else 0.0,
            "itl_p99_s": _percentile(deltas, 0.99) if deltas else 0.0,
            "decode_throughput_tok_s": decode_throughput,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "wall_clock_s": t_end - self.t_request_start,
        }

        target = spans_file or (SPANS_DIR / "gateway_spans.jsonl")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a") as f:
            f.write(json.dumps(span) + "\n")
        return span
