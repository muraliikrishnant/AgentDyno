# AgentDyno

**A dynamometer for coding agents.** AgentDyno runs coding agents against
software-engineering tasks and, for every harness *architectural decision*
you flip (orchestration policy, model-tier routing, context management,
tools), measures both **task success** and the **full inference workload it
costs** — TTFT, ITL, decode throughput, tokens, tool-call round-trips, and $
— then plots the success-vs-cost Pareto frontier.

Coding agents are the fastest-growing driver of AI inference demand, yet
teams pick harness architectures by task-success leaderboards alone, blind
to what those choices cost in latency and compute. AgentDyno makes that
tradeoff measurable.

See `AgentDyno-Hackathon-Plan.md` for the full design doc (architecture,
experiment matrix, methodology, week-by-week plan). This README covers what
is built and how to run it today.

## Status: Week-2 slice — real gateway/inference/orchestration, partial Harbor/Nebius-sandbox

This repo ships a **fully working local slice** end to end: telemetry
gateway -> single-agent *and* parallel-subagents harness -> local sandbox ->
profiler -> dashboard -> auto-generated findings. The gateway supports both
a `MockModelBackend` (default, realistic simulated streaming TTFT/ITL, no
API keys/network calls) and **real streaming calls to Nebius Token Factory /
Nemotron Nano/Super/Ultra** (`AGENTDYNO_BACKEND=nebius`, confirmed working
against live model IDs, budget-capped via `AGENTDYNO_SPEND_CEILING_USD`).

Two orchestration architectures are real: `single` (ReAct loop) and
`subagents` (lead decomposition + N concurrent worker loops, each with its
own gateway calls — see `agentdyno/harness/orchestration/subagents.py`).
`plan_execute` remains a structural stub.

`NebiusSandboxEnvironment` is a real `harbor.environments.base.BaseEnvironment`
subclass (the actual `harbor` PyPI package's ABC, not a standalone stand-in)
implementing every abstract method against the real, installed `contree-sdk`
(Nebius Sandboxes / "ConTree") API — confirmed by introspecting the
installed package source, not just docs. A standalone test successfully
constructed it, called `start()`, and had `exec()` reach the real
`https://api.tokenfactory.nebius.com/sandboxes/` endpoint (a real HTTP round
trip, not a mock), which returned a real permission-scoped error because
this Nebius account is missing `NEBIUS_PROJECT_ID`/sandbox entitlements —
a credentials/access gap, not a code gap. Full `harbor run` against one of
AgentDyno's toy tasks was **not** reached this session: `harbor`'s CLI does
support pointing at a custom environment by import path
(`--env module:Class`, no plugin-registry hacking needed — see
`harbor.cli.plugin_registry.resolve_plugin_import_path`), but AgentDyno's
toy tasks (`experiments/tasks/*`) don't have Harbor's task manifest format
(`task.toml`, `environment/`, etc.), and building one compliant task is a
separate, non-trivial follow-up.

Every remaining integration point is marked with a `# TODO(nebius):`,
`# TODO(harbor):`, or `# TODO(tavily):` comment stating exactly what's
still needed. Search the repo for those.

## Architecture summary

```
experiment.yaml -> CLI expands matrix -> per trial:
  LocalSubprocessEnvironment.start()   (Harbor-compliant NebiusSandboxEnvironment: BaseEnvironment tier reached, not wired into `harbor run` yet)
  -> Harness.run() -> gateway /v1/chat/completions (streaming, telemetry-captured)
       -> MockModelBackend | real Nebius Token Factory / Nemotron (AGENTDYNO_BACKEND)
  -> run_tests() -> pass/fail
  -> environment.stop()
-> profiler.ingest() -> DuckDB/Parquet
-> profiler.derive() -> TTFT/ITL/cost aggregates + Pareto frontier
-> dashboard (Streamlit) + report.analyze() -> FINDINGS.md
```

Every model call goes through `agentdyno/gateway/proxy.py`, an
OpenAI-compatible streaming proxy, so TTFT/ITL/throughput are captured
uniformly regardless of harness architecture. See the plan doc section 4 for
the full target architecture (Nebius Sandboxes, Harbor, real Nemotron
tiers).

## Quickstart

Requires Python 3.11+.

```bash
# with uv
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# or with plain pip
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the MVP experiment (single + subagents architectures, 5 toy coding
tasks, 2 simulated model tiers, 2 seeds — all local, no API keys, no network
calls by default):

```bash
agentdyno run experiments/mvp.yaml
```

This starts the telemetry gateway in the background, runs every trial
against `LocalSubprocessEnvironment` (a local-temp-dir sandbox fallback),
writes JSONL spans under `data/spans/` and a DuckDB/Parquet store under
`data/`, and prints a Rich summary table.

To run against real Nebius Token Factory / Nemotron inference instead of
the mock backend (requires `NEBIUS_API_KEY` in `.env`; spend is capped by
`AGENTDYNO_SPEND_CEILING_USD`, default $40):

```bash
AGENTDYNO_BACKEND=nebius agentdyno run experiments/mvp.yaml
```

Generate the findings report (default: written against `MockModelBackend`;
pass `AGENTDYNO_BACKEND=nebius` to use one real Nemotron Ultra call for the
narrative instead):

```bash
agentdyno report
# or, for one real call:
AGENTDYNO_BACKEND=nebius agentdyno report
```

View the dashboard (Pareto scatter, TTFT/ITL distributions, single-trial
drill-in):

```bash
streamlit run dashboard/app.py
```

Run the gateway standalone (useful for manual `curl` testing against
`/v1/chat/completions`):

```bash
agentdyno serve-gateway
```

## What's real vs. mocked

| Component | Status |
|---|---|
| Telemetry gateway (FastAPI, SSE streaming, TTFT/ITL/throughput capture) | **Real**, works today |
| Real Nebius Token Factory / Nemotron Nano/Super/Ultra inference | **Real** — confirmed live model IDs, streaming, budget-capped. Set `AGENTDYNO_BACKEND=nebius` (default: `mock`) |
| `MockModelBackend` (randomized-but-plausible streaming latencies per tier) | **Real**, default backend for cheap/fast local iteration |
| `single` orchestration (ReAct loop) | **Real**, works today against mock and Nebius backends |
| `subagents` orchestration (lead decomposition + N concurrent workers) | **Real** — see `agentdyno/harness/orchestration/subagents.py`; verified to multiply model-call count vs `single` (~4x with N=3) in real profiler output |
| `plan_execute` orchestration | Structural stub — raises `NotImplementedError` |
| Tools (shell/edit/run_tests), context truncate/compaction | **Real**, works today |
| `LocalSubprocessEnvironment` | **Real** local sandbox fallback, used by `agentdyno run` today |
| `NebiusSandboxEnvironment` (Harbor provider) | **Partial / Tier 2 of 3.** Real `harbor.environments.base.BaseEnvironment` subclass implementing every abstract method against the real, installed `contree-sdk` API (confirmed by introspecting the package source: real default `base_url`, real `image.run()`/`.result`/`.apply_files()`/`.read()`/`.ls()` shapes). Verified standalone: `start()` + `exec()` reach the real Nebius Sandboxes endpoint and get back a real permission error (missing `NEBIUS_PROJECT_ID`/entitlements on this account — a credentials gap, not a code gap; see `# TODO(nebius)` comments). **Not yet reached:** a full `harbor run` trial — AgentDyno's toy tasks lack Harbor's task manifest format, and `checkpoint`/`branch` semantics are implemented via `contree-sdk`'s `tag_as`/`use` as the closest confirmed primitive, but unverified against a live account |
| Harbor CLI integration path | Confirmed real: `harbor` supports `--env module:Class` custom environments with no plugin-registry step (`harbor.cli.plugin_registry.resolve_plugin_import_path`). Not yet exercised end-to-end because of the task-manifest gap above |
| Tavily web search tool | Stub — `# TODO(tavily)`, falls back to a clearly labeled mock result if `TAVILY_API_KEY` unset |
| `FINDINGS.md` narrative | Generated via `agentdyno report`; supports both `MockModelBackend` and a single real Nemotron Ultra call (`AGENTDYNO_BACKEND=nebius agentdyno report`) — default documented here is `mock` for cheap iteration |
| Harbor eval framework integration (full trial execution) | Not yet wired; this repo runs its own minimal task/trial loop instead. See `NebiusSandboxEnvironment` row above for how far the Harbor *environment* integration itself got |

## License

Apache-2.0. See `LICENSE`.
