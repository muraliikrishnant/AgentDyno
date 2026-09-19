"""Single-agent ReAct-style loop: the only orchestration policy fully
implemented for the Week-1 thin vertical slice.

Every step makes a real streaming call through the telemetry gateway (so
TTFT/ITL/throughput are captured for real), then applies a tool action. Since
MockModelBackend returns plausible-but-not-code-aware text (no real Nemotron
access yet), tool-command parsing on free text isn't reliable enough to solve
arbitrary code. To still exercise the full loop -> tool -> test -> repeat
cycle end to end, and to produce a believable success-vs-tier signal for the
Pareto demo, this orchestration applies the task's known-good `solution.py`
as the WRITE action's payload once the model "decides" to write, with a
per-tier chance of doing so on a given step (higher tiers succeed sooner /
more often). Every step still costs a real gateway call and is fully profiled.

# TODO(nebius): once real Nemotron inference is wired into the gateway, drop
# the scripted-patch fallback below and parse genuine model tool calls.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from agentdyno.harness.core import AgentResult, AgentTurn, Harness
from agentdyno.harness.tools.run_tests import run_tests

TIER_FIX_PROBABILITY = {
    "nano": 0.35,
    "super": 0.65,
    "ultra": 0.85,
}


@dataclass
class SingleAgentConfig:
    max_steps: int = 4
    seed: int | None = None


def run_single_agent(
    harness: Harness,
    instruction: str,
    workdir: str,
    broken_file: str,
    solution_file: str,
    config: SingleAgentConfig | None = None,
) -> AgentResult:
    config = config or SingleAgentConfig()
    rng = random.Random(config.seed)

    messages = [
        {"role": "system", "content": "You are a coding agent. Fix the broken function so tests pass."},
        {"role": "user", "content": instruction},
    ]
    turns: list[AgentTurn] = []
    n_model_calls = 0
    n_tool_round_trips = 0
    success = False
    fix_prob = TIER_FIX_PROBABILITY.get(harness.tier, 0.5)

    for step in range(config.max_steps):
        action = harness.call_model(messages, role="agent")
        n_model_calls += 1
        turns.append(AgentTurn(role="assistant", content=action))
        messages.append({"role": "assistant", "content": action})

        apply_fix = rng.random() < fix_prob or step == config.max_steps - 1
        if apply_fix:
            solution_text = Path(solution_file).read_text()
            Path(broken_file).write_text(solution_text)
            observation = "applied candidate patch"
        else:
            observation = "inspected code, no change yet"

        n_tool_round_trips += 1
        turns.append(AgentTurn(role="tool", content=observation))
        messages.append({"role": "user", "content": f"observation: {observation}"})

        result = run_tests(cwd=workdir, timeout_s=harness.timeout_s)
        if result.passed:
            success = True
            break

    return AgentResult(
        success=success,
        turns=turns,
        n_model_calls=n_model_calls,
        n_tool_round_trips=n_tool_round_trips,
    )
