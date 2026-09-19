"""Plan-then-execute orchestration policy (structural stub).

Intended behavior per the plan doc: a planning call (ideally routed to a
higher-reasoning tier, e.g. Nemotron Ultra) produces a step-by-step plan
once; an execution loop (cheaper tier, e.g. Super) then works through the
plan steps with tools, only returning to the planner on failure. This tests
the model-tier-routing hypothesis "does Ultra-for-planning pay for itself?"
by isolating one expensive high-latency call from many cheap ones.

Not implemented for the Week-1 vertical slice; explicit NotImplementedError
so it fails loudly instead of silently falling back to single-agent.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlanExecuteConfig:
    planner_tier: str = "ultra"
    executor_tier: str = "super"
    max_execute_steps: int = 6


def run_plan_execute(*args, **kwargs):
    raise NotImplementedError(
        "plan_execute orchestration is a structural stub - implement a "
        "planner call (planner_tier) that produces a step list, then an "
        "executor loop (executor_tier) that works through it, per the plan "
        "doc section 6 (model-tier-routing axis)."
    )
