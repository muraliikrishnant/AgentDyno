"""Minimal agent loop: system prompt + user task -> tool-call loop -> stop
condition. All model calls go through the telemetry gateway via httpx so
every architecture's traffic is captured uniformly, never via a model SDK
directly.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import httpx

from agentdyno.harness.tools.edit import read_file, write_file
from agentdyno.harness.tools.run_tests import run_tests
from agentdyno.harness.tools.shell import run_shell

SYSTEM_PROMPT = """You are a coding agent fixing a broken Python function so \
it passes its tests. You have tools: READ <path>, WRITE <path> <content>, \
SHELL <command>, TEST. Respond with exactly one tool call per turn, prefixed \
with the tool name in caps. When tests pass, respond with DONE."""


@dataclass
class AgentTurn:
    role: str
    content: str


@dataclass
class AgentResult:
    success: bool
    turns: list[AgentTurn]
    n_model_calls: int
    n_tool_round_trips: int


class Harness:
    """Calls the gateway's /v1/chat/completions instead of a model SDK."""

    def __init__(
        self,
        gateway_url: str,
        model: str,
        tier: str,
        trial_id: str,
        max_steps: int = 6,
        timeout_s: float = 30.0,
    ):
        self.gateway_url = gateway_url
        self.model = model
        self.tier = tier
        self.trial_id = trial_id
        self.max_steps = max_steps
        self.timeout_s = timeout_s

    def call_model(self, messages: list[dict], role: str = "agent") -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "tier": self.tier,
            "role": role,
            "trial_id": self.trial_id,
            "stream": True,
        }
        text = ""
        with httpx.stream("POST", self.gateway_url, json=payload, timeout=self.timeout_s) as resp:
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    text += delta
        return text.strip()

    def apply_tool(self, action: str, workdir: str, default_path: str) -> str:
        if action.startswith("READ"):
            path = action.split(maxsplit=1)[1].strip() if len(action.split(maxsplit=1)) > 1 else default_path
            try:
                return read_file(path)
            except OSError as e:
                return f"error: {e}"
        if action.startswith("WRITE"):
            m = re.match(r"WRITE\s+(\S+)\s+(.*)", action, re.DOTALL)
            if not m:
                return "error: WRITE requires <path> <content>"
            path, content = m.group(1), m.group(2)
            write_file(path, content)
            return "wrote file"
        if action.startswith("SHELL"):
            cmd = action[len("SHELL"):].strip()
            r = run_shell(cmd, cwd=workdir, timeout_s=self.timeout_s)
            return f"exit={r.exit_code}\nstdout={r.stdout}\nstderr={r.stderr}"
        if action.startswith("TEST"):
            r = run_tests(cwd=workdir, timeout_s=self.timeout_s)
            return f"passed={r.passed}\nstdout={r.stdout}\nstderr={r.stderr}"
        return "error: unknown tool"
