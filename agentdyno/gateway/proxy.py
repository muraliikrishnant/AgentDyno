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
from fastapi import FastAPI, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agentdyno.gateway.mock_backend import MockModelBackend
from agentdyno.gateway.spans import SPANS_DIR, SpanRecorder

app = FastAPI(title="AgentDyno Telemetry Gateway")

BACKEND = os.environ.get("AGENTDYNO_BACKEND", "mock")
# TODO(nebius): set NEBIUS_TOKEN_FACTORY_BASE_URL and NEBIUS_TOKEN_FACTORY_API_KEY
# and point httpx at the real OpenAI-compatible endpoint, e.g.
# https://api.tokenfactory.nebius.com/v1/chat/completions with an
# "Authorization: Bearer <NEBIUS_API_KEY>" header, model IDs like
# nvidia/nemotron-3-super-120b-a12b.
NEBIUS_BASE_URL = os.environ.get("NEBIUS_TOKEN_FACTORY_BASE_URL", "")
NEBIUS_API_KEY = os.environ.get("NEBIUS_TOKEN_FACTORY_API_KEY", "")

_mock_backend = MockModelBackend()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "nvidia/nemotron-3-super-120b-a12b"
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

    for chunk_text, t in _mock_backend.stream(messages, tier=req.tier):
        if chunk_text is None:
            break
        recorder.record_token(t)
        yield _sse({
            "choices": [{"delta": {"content": chunk_text}, "index": 0, "finish_reason": None}]
        })

    usage = getattr(_mock_backend, "_last_usage", {"prompt_tokens": 0, "completion_tokens": 0})
    span = recorder.finalize(usage["prompt_tokens"], usage["completion_tokens"], spans_file)
    yield _sse({
        "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}],
        "usage": usage,
        "agentdyno_span": span,
    })
    yield "data: [DONE]\n\n"


async def _stream_nebius(req: ChatCompletionRequest, spans_file: Path | None):
    """# TODO(nebius): implement real forwarding to Token Factory's
    OpenAI-compatible streaming endpoint via httpx.AsyncClient, parsing SSE
    chunks and stamping t_first_token / per-chunk deltas exactly as
    _stream_mock does for the JSONL span. Requires NEBIUS_TOKEN_FACTORY_BASE_URL
    and NEBIUS_TOKEN_FACTORY_API_KEY.
    """
    raise NotImplementedError(
        "Nebius backend not wired up yet - set AGENTDYNO_BACKEND=mock, "
        "or implement _stream_nebius. # TODO(nebius)"
    )


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, x_agentdyno_trial_id: str | None = Header(default=None)):
    if req.trial_id is None:
        req.trial_id = x_agentdyno_trial_id

    spans_file = None
    if req.trial_id:
        spans_file = SPANS_DIR / f"{req.trial_id}.jsonl"

    generator = _stream_mock(req, spans_file) if BACKEND == "mock" else _stream_nebius(req, spans_file)
    return StreamingResponse(generator, media_type="text/event-stream")


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "backend": BACKEND}
