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

## Status: Week-1 thin vertical slice + scaffolding

This repo currently ships a **fully working local slice** end to end:
telemetry gateway -> single-agent harness -> local sandbox -> profiler ->
dashboard -> auto-generated findings, using a `MockModelBackend` that
simulates realistic streaming TTFT/ITL instead of a real model. It also
ships the **structural scaffolding** for the rest of the plan (Nebius
Sandbox provider, subagents/plan-execute orchestration, Nemotron tier
routing) as explicit stubs.

**Real Nebius Token Factory / Nemotron / Harbor / Tavily integration is
stubbed pending credentials.** Every integration point is marked with a
`# TODO(nebius):`, `# TODO(harbor):`, or `# TODO(tavily):` comment stating
exactly what SDK call, endpoint, or credential is needed. Search the repo
for those to find every remaining integration task. Nemotron model IDs used
as config placeholders (`nvidia/nemotron-3-nano-*`,
`nvidia/nemotron-3-super-120b-a12b`, `nvidia/nemotron-3-ultra-*`) are taken
from the plan doc and are **not yet verified** against the live Token
Factory catalog.

## Architecture summary

```
experiment.yaml -> CLI expands matrix -> per trial:
  LocalSubprocessEnvironment.start()          (Nebius Sandbox provider: stub)
  -> Harness.run() -> gateway /v1/chat/completions (streaming, telemetry-captured)
       -> MockModelBackend                     (real Nebius/Nemotron: stub)
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

Run the MVP experiment (single-agent architecture, 5 toy coding tasks, 2
simulated model tiers, 2 seeds — all local, no API keys, no network calls):

```bash
agentdyno run experiments/mvp.yaml
```

This starts the telemetry gateway in the background, runs every trial
against `LocalSubprocessEnvironment` (a local-temp-dir sandbox fallback),
writes JSONL spans under `data/spans/` and a DuckDB/Parquet store under
`data/`, and prints a Rich summary table.

Generate the findings report (written against `MockModelBackend` standing
in for Nemotron Ultra):

```bash
agentdyno report
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
| `MockModelBackend` (randomized-but-plausible streaming latencies per tier) | **Real**, stands in for Nebius Token Factory inference |
| Single-agent harness loop, tools (shell/edit/run_tests), context truncate/compaction | **Real**, works today |
| `LocalSubprocessEnvironment` | **Real** local sandbox fallback |
| Profiler (DuckDB ingest, TTFT/ITL/cost aggregates, Pareto frontier) | **Real**, works today |
| Streamlit dashboard | **Real**, works today |
| `NebiusSandboxEnvironment` (Harbor provider) | Stub — `# TODO(nebius)`, needs Token Factory Sandboxes SDK confirmed live |
| Real Nebius Token Factory / Nemotron inference in the gateway | Stub — `# TODO(nebius)`, needs API base URL + key |
| `subagents` / `plan_execute` orchestration | Structural stubs — raise `NotImplementedError`, documented intended behavior |
| Tavily web search tool | Stub — `# TODO(tavily)`, falls back to a clearly labeled mock result if `TAVILY_API_KEY` unset |
| Nemotron-Ultra-written `FINDINGS.md` | Currently written against `MockModelBackend`; `# TODO(nebius)` to swap in real Ultra |
| Harbor eval framework integration | Not yet wired; this repo runs its own minimal task/trial loop instead |

## License

Apache-2.0. See `LICENSE`.
