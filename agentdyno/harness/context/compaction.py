"""Context compaction: summarize older turns with a cheap model tier instead
of truncating them away outright. Uses tier="nano" (see agentdyno.gateway.models)
- compaction is exactly the high-frequency/cheap workload Nano is meant for.
"""
from __future__ import annotations

import httpx

from agentdyno.gateway.models import model_id_for_tier

GATEWAY_URL = "http://127.0.0.1:8000/v1/chat/completions"


def compact_messages(messages: list[dict], gateway_url: str = GATEWAY_URL, trial_id: str | None = None) -> list[dict]:
    system = [m for m in messages if m["role"] == "system"][:1]
    rest = [m for m in messages if m["role"] != "system"]
    if len(rest) <= 6:
        return messages

    to_summarize, recent = rest[:-4], rest[-4:]
    summary_prompt = [
        {"role": "system", "content": "Summarize this agent transcript excerpt in 2-3 sentences, preserving key facts."},
        {"role": "user", "content": "\n".join(f"{m['role']}: {m['content']}" for m in to_summarize)},
    ]

    payload = {
        "model": model_id_for_tier("nano"),
        "messages": summary_prompt,
        "tier": "nano",
        "role": "compaction",
        "trial_id": trial_id,
        "stream": True,
    }

    summary_text = ""
    with httpx.stream("POST", gateway_url, json=payload, timeout=30.0) as resp:
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data == "[DONE]":
                break
            import json as _json
            chunk = _json.loads(data)
            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta:
                summary_text += delta

    summary_msg = {"role": "assistant", "content": f"[compacted summary] {summary_text.strip()}"}
    return system + [summary_msg] + recent
