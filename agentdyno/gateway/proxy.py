"""OpenAI-compatible chat-completions streaming proxy.

Every model call in AgentDyno routes through this gateway so telemetry
(TTFT, ITL, decode throughput, token counts) is captured uniformly for any
harness architecture. Locally it streams from MockModelBackend; when
AGENTDYNO_BACKEND=nebius it should forward to Nebius Token Factory.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agentdyno.gateway import budget
from agentdyno.gateway.mock_backend import MockModelBackend
from agentdyno.gateway.models import TIER_MODEL_IDS
from agentdyno.gateway.spans import SPANS_DIR, SpanRecorder

app = FastAPI(title="AgentDyno Telemetry Gateway")

BACKEND = os.environ.get("AGENTDYNO_BACKEND", "mock")
NEBIUS_BASE_URL = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1")
NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")

_mock_backend = MockModelBackend()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = TIER_MODEL_IDS["super"]
    messages: list[ChatMessage]
    stream: bool = True
    tier: str = "super"
    role: str = "agent"
    trial_id: str | None = None


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _stream_mock(req: ChatCompletionRequest, spans_file: Path | None):
    recorder = SpanRecorder(model=req.model, tier=req.tier, role=req.role, trial_id=req.trial_id)
    messages = [m.model_dump() for m in req.messages]

    gen = _mock_backend.stream(messages, tier=req.tier)
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    try:
        while True:
            chunk_text, t = next(gen)
            recorder.record_token(t)
            yield _sse({
                "choices": [{"delta": {"content": chunk_text}, "index": 0, "finish_reason": None}]
            })
    except StopIteration as stop:
        if stop.value:
            usage = stop.value
    span = recorder.finalize(usage["prompt_tokens"], usage["completion_tokens"], spans_file)
    yield _sse({
        "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}],
        "usage": usage,
        "agentdyno_span": span,
    })
    yield "data: [DONE]\n\n"


async def _stream_nebius(req: ChatCompletionRequest, spans_file: Path | None):
    """Forwards to Nebius Token Factory's OpenAI-compatible streaming
    endpoint, parsing SSE chunks and stamping t_first_token / per-chunk
    deltas exactly as _stream_mock does, then records estimated spend
    against the AGENTDYNO_SPEND_CEILING_USD ceiling (see agentdyno.gateway.budget).
    """
    if not NEBIUS_API_KEY:
        raise RuntimeError("NEBIUS_API_KEY is not set; export it or set AGENTDYNO_BACKEND=mock")

    recorder = SpanRecorder(model=req.model, tier=req.tier, role=req.role, trial_id=req.trial_id)
    payload = {
        "model": req.model,
        "messages": [m.model_dump() for m in req.messages],
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {NEBIUS_API_KEY}"}

    prompt_tokens = 0
    completion_tokens = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST", f"{NEBIUS_BASE_URL.rstrip('/')}/chat/completions", json=payload, headers=headers
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data.strip() == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    recorder.record_token(time.monotonic())
                    completion_tokens += 1
                    yield _sse({"choices": [{"delta": {"content": content}, "index": 0, "finish_reason": None}]})
                usage = chunk.get("usage")
                if usage:
                    prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                    completion_tokens = usage.get("completion_tokens", completion_tokens)

    span = recorder.finalize(prompt_tokens, completion_tokens, spans_file)
    new_total = budget.record_spend(req.tier, prompt_tokens, completion_tokens)
    span["cumulative_spend_usd"] = new_total
    yield _sse({
        "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        "agentdyno_span": span,
    })
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, x_agentdyno_trial_id: str | None = Header(default=None)):
    if req.trial_id is None:
        req.trial_id = x_agentdyno_trial_id

    spans_file = None
    if req.trial_id:
        spans_file = SPANS_DIR / f"{req.trial_id}.jsonl"

    if BACKEND != "mock":
        try:
            budget.check_before_call(req.tier)
        except budget.SpendCeilingExceeded as e:
            raise HTTPException(status_code=402, detail=str(e))

    generator = _stream_mock(req, spans_file) if BACKEND == "mock" else _stream_nebius(req, spans_file)
    return StreamingResponse(generator, media_type="text/event-stream")


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "backend": BACKEND, "spend_usd": budget.current_spend_usd(), "spend_ceiling_usd": budget.SPEND_CEILING_USD}
