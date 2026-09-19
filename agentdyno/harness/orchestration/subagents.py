"""Parallel-subagents orchestration policy: lead + N concurrent workers.

Per the plan doc (section 6, "Orchestration" axis): a lead agent makes one
decomposition call, then dispatches the task to N subagents that each run
their own independent ReAct-style loop (own copy of the workdir, own gateway
calls tagged `role="subagent_{i}"`, own tool round-trips) concurrently in
real OS threads - `Harness.call_model` blocks on `httpx.stream`, so threads
give genuine wall-clock overlap, not just simulated concurrency. The lead
then merges: first subagent to pass its tests wins and its patched file is
copied back into the trial's workdir; if none pass, the first subagent's
(failed) attempt is used so the trial still produces a diffable result.

This directly tests the hypothesis called out in the plan doc: subagents
should raise success (more independent attempts) but multiply total model
calls (`n_model_calls` = 1 lead call + N subagents x max_steps), so the
profiler's TTFT-tax and cost_per_solved_task numbers should look
measurably different from `single` even when wall-clock is similar or
better under concurrency. Every call - lead and every subagent step - is a
real gateway call, so telemetry captures this for real.

Kept structurally parallel to single.py: same Harness class, same gateway
plumbing (`harness.call_model`), same tool set (`run_tests`), same
scripted-patch-application mechanic (see single.py's module docstring for
why: MockModelBackend text isn't code-aware, so applying the task's known
`solution.py` with a per-tier probability is what drives a believable
success signal until real Nemotron tool-call parsing lands).
"""
from __future__ import annotations

import concurrent.futures
import random
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agentdyno.harness.core import AgentResult, AgentTurn, Harness
from agentdyno.harness.tools.run_tests import run_tests

# Same per-tier "does the model decide to apply its patch this step" knob as
# single.py, so subagents vs single is an architecture comparison, not a
# different success model.
TIER_FIX_PROBABILITY = {
    "nano": 0.35,
    "super": 0.65,
    "ultra": 0.85,
}


@dataclass
class SubagentsConfig:
    n_subagents: int = 3
    max_steps_per_subagent: int = 4
    seed: int | None = None


def _run_one_subagent(
    harness: Harness,
    instruction: str,
    subagent_idx: int,
    subagent_workdir: str,
    broken_file: str,
    solution_file: str,
    max_steps: int,
    seed: int | None,
) -> AgentResult:
    """One subagent's independent ReAct loop, run in its own thread against
    its own copy of the workdir. Mirrors single.py's run_single_agent loop
    body exactly, but tagged with a per-subagent role and seed so every
    subagent's gateway calls are individually attributable in telemetry."""
    rng = random.Random(None if seed is None else seed * 1000 + subagent_idx)
    role = f"subagent_{subagent_idx}"

    messages = [
        {"role": "system", "content": "You are a coding agent. Fix the broken function so tests pass."},
        {"role": "user", "content": instruction},
    ]
    turns: list[AgentTurn] = []
    n_model_calls = 0
    n_tool_round_trips = 0
    success = False
    fix_prob = TIER_FIX_PROBABILITY.get(harness.tier, 0.5)

    for step in range(max_steps):
        action = harness.call_model(messages, role=role)
        n_model_calls += 1
        turns.append(AgentTurn(role=role, content=action))
        messages.append({"role": "assistant", "content": action})

        apply_fix = rng.random() < fix_prob or step == max_steps - 1
        if apply_fix:
            solution_text = Path(solution_file).read_text()
            Path(broken_file).write_text(solution_text)
            observation = "applied candidate patch"
        else:
            observation = "inspected code, no change yet"

        n_tool_round_trips += 1
        turns.append(AgentTurn(role="tool", content=observation))
        messages.append({"role": "user", "content": f"observation: {observation}"})

        result = run_tests(cwd=subagent_workdir, timeout_s=harness.timeout_s)
        if result.passed:
            success = True
            break

    return AgentResult(
        success=success,
        turns=turns,
        n_model_calls=n_model_calls,
        n_tool_round_trips=n_tool_round_trips,
    )


def run_subagents(
    harness: Harness,
    instruction: str,
    workdir: str,
    broken_file: str,
    solution_file: str,
    config: SubagentsConfig | None = None,
) -> AgentResult:
    config = config or SubagentsConfig()
    broken_name = Path(broken_file).name
    solution_name = Path(solution_file).name

    # Lead agent's decomposition call - one real gateway call, tagged
    # role="lead" so its telemetry is distinguishable from subagent calls.
    lead_messages = [
        {
            "role": "system",
            "content": (
                "You are a lead agent. Decompose the task into independent "
                f"attempts for {config.n_subagents} subagents to fix the "
                "broken function in parallel."
            ),
        },
        {"role": "user", "content": instruction},
    ]
    lead_action = harness.call_model(lead_messages, role="lead")
    turns: list[AgentTurn] = [AgentTurn(role="lead", content=lead_action)]
    n_model_calls = 1
    n_tool_round_trips = 0

    # Give each subagent its own isolated copy of the workdir so concurrent
    # writes to broken.py never collide.
    tmp_root = tempfile.mkdtemp(prefix="agentdyno_subagents_")
    subagent_dirs: list[str] = []
    for i in range(config.n_subagents):
        dest = Path(tmp_root) / f"subagent_{i}"
        shutil.copytree(workdir, dest)
        subagent_dirs.append(str(dest))

    try:
        results: list[AgentResult] = [None] * config.n_subagents  # type: ignore[list-item]
        with concurrent.futures.ThreadPoolExecutor(max_workers=config.n_subagents) as pool:
            futures = {
                pool.submit(
                    _run_one_subagent,
                    harness,
                    instruction,
                    i,
                    subagent_dirs[i],
                    str(Path(subagent_dirs[i]) / broken_name),
                    str(Path(subagent_dirs[i]) / solution_name),
                    config.max_steps_per_subagent,
                    config.seed,
                ): i
                for i in range(config.n_subagents)
            }
            for future in concurrent.futures.as_completed(futures):
                i = futures[future]
                results[i] = future.result()

        for r in results:
            turns.extend(r.turns)
            n_model_calls += r.n_model_calls
            n_tool_round_trips += r.n_tool_round_trips

        winner_idx = next((i for i, r in enumerate(results) if r.success), 0)
        winner_broken = Path(subagent_dirs[winner_idx]) / broken_name
        if winner_broken.exists():
            Path(broken_file).write_text(winner_broken.read_text())

        success = any(r.success for r in results)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return AgentResult(
        success=success,
        turns=turns,
        n_model_calls=n_model_calls,
        n_tool_round_trips=n_tool_round_trips,
    )
