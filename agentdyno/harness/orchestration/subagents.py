"""Parallel-subagents orchestration policy (structural stub).

Intended behavior per the plan doc (section 6): a lead agent decomposes the
task into subtasks, dispatches each to a subagent that runs its own
model-call/tool loop concurrently (own gateway calls, own spans, tagged with
a subagent role), then a lead agent merges results and decides whether to
retry. This is the config that tests the hypothesis "subagents raise success
but multiply model calls - does the TTFT tax eat the wall-clock win?" since
each subagent pays its own TTFT on every round trip, potentially in parallel
(reducing wall-clock) but not reducing total token/$-cost.

Not implemented for the Week-1 vertical slice; explicit NotImplementedError
so it fails loudly instead of silently behaving like single-agent.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SubagentsConfig:
    n_subagents: int = 3
    max_steps_per_subagent: int = 4


def run_subagents(*args, **kwargs):
    raise NotImplementedError(
        "subagents orchestration is a structural stub - implement lead "
        "decomposition + concurrent subagent loops + merge, per the plan "
        "doc section 6 (orchestration axis)."
    )
