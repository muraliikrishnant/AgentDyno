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

## Status: Week-2 slice — real gateway/inference/orchestration, full Harbor/Nebius-sandbox trial

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
(Nebius Sandboxes / "ConTree") API. Sandboxes beta access was approved on
2026-09-21, and `start()` + chained `exec()` calls are now verified working
live: a file written in one `exec()` call is readable in the next, confirming
state genuinely persists across calls on a real sandbox (not a mock). Getting
here required two real fixes discovered against the live account -
`contree-sdk` runs default to `disposable=True` (each call silently resets
to a fresh image unless you pass `disposable=False`), and the executed
result must be reassigned back onto the environment or later calls revert to
the start()-time image.

**A full `harbor run` trial is now reached.** `experiments/tasks/task1_fix_add`
was converted into Harbor's real task manifest format at
`experiments/tasks/task1_fix_add_harbor/` (`task.toml` with
`[environment].docker_image`, `instruction.md`, `solution/solve.sh`,
`tests/test.sh` + `tests/test_outputs.py` — derived from the real scaffold
Harbor ships at `harbor/cli/template-task/`, not reverse-engineered blind).
Running

```bash
harbor run -p experiments/tasks/task1_fix_add_harbor -a oracle \
  -e agentdyno.harbor_provider.nebius_sandbox:NebiusSandboxEnvironment -y
```

(`oracle` is Harbor's built-in agent that applies a task's reference
`solution/solve.sh` directly — no LLM call, so this proves Harbor's own
`environment.start -> agent.run -> verifier.verify` loop with **zero**
Nemotron inference spend) drives the real `harbor` CLI trial loop end to end
against a live Nebius sandbox: environment starts, the fix is applied on the
sandbox, Harbor's real `Verifier` uploads and runs `tests/test.sh` on that
same sandbox, both `pytest` cases pass, and the trial reports `reward: 1.0`
in `result.json`. Getting the full CLI trial (not just standalone
`start()`/`exec()`) working surfaced two more real, previously-latent bugs
in `NebiusSandboxEnvironment`, now fixed:
1. `start()` never created Harbor's expected `/logs/agent`, `/logs/verifier`,
   `/logs/artifacts`, `/tests`, `/solution` scaffold directories. Docker-based
   providers get these for free via host bind mounts; non-mounted cloud
   providers (Harbor's own `E2BEnvironment` included) must create them
   explicitly with `ensure_dirs(self._mount_targets(...))` before running
   anything — this call was simply missing.
2. `download_dir()` assumed `contree-sdk`'s `image.ls()` entries carry an
   absolute path under the directory queried; they actually carry only the
   bare filename, so the first real recursive log download raised
   `ValueError: 'oracle.txt' is not in the subpath of '/logs/agent'`, and a
   copy-paste slip left the *file* download branch using the bare filename
   again after the directory-recursion branch was fixed — both are corrected
   in `agentdyno/harbor_provider/nebius_sandbox.py`.

`checkpoint`/`branch` semantics (`tag_as`/`use`) are still implemented but
unverified live.

Every remaining integration point is marked with a `# TODO(nebius):`,
`# TODO(harbor):`, or `# TODO(tavily):` comment stating exactly what's
still needed. Search the repo for those.

## Contributing

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup
and how to verify a change. Issues tagged
[`good first issue`](../../issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
are a good place to start.

## Architecture summary

```
experiment.yaml -> CLI expands matrix -> per trial:
  LocalSubprocessEnvironment.start()   (or Harbor-compliant NebiusSandboxEnvironment via real `harbor run`, live-verified end to end on task1_fix_add_harbor)
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
| `NebiusSandboxEnvironment` (Harbor provider) | **Real, working, live-verified, full `harbor run` CLI trial passing.** Real `harbor.environments.base.BaseEnvironment` subclass implementing every abstract method against the real `contree-sdk` API. `experiments/tasks/task1_fix_add_harbor/` is a real Harbor task (`task.toml`, `instruction.md`, `solution/`, `tests/`) derived from Harbor's own `harbor/cli/template-task/` scaffold. `harbor run -p experiments/tasks/task1_fix_add_harbor -a oracle -e agentdyno.harbor_provider.nebius_sandbox:NebiusSandboxEnvironment` runs the full `environment.start -> agent.run -> verifier.verify` loop against a live Nebius sandbox and reports `reward: 1.0` (both pytest cases pass) — zero Nemotron spend, since `oracle` applies the task's reference solution directly rather than calling a model. Four real bugs were found and fixed against the live account along the way: `contree-sdk` runs default to `disposable=True` (each call silently starts from a fresh image unless you pass `disposable=False`); the awaited run result must be reassigned back to `self._image` or every subsequent call reverts to the start()-time base image; `start()` was missing the `ensure_dirs(self._mount_targets(...))` call every non-mounted cloud provider needs to create Harbor's `/logs/*`, `/tests`, `/solution` scaffold directories; and `download_dir()`/`download_file()` assumed `contree-sdk`'s `image.ls()` returns absolute paths when it returns bare filenames. `checkpoint`/`branch` semantics (`tag_as`/`use`) are implemented but still unverified live |
| Harbor CLI integration path | Confirmed real: `harbor` supports `--env module:Class` custom environments with no plugin-registry step (`harbor.cli.plugin_registry.resolve_plugin_import_path`). Not yet exercised end-to-end because of the task-manifest gap above |
| Tavily web search tool | Stub — `# TODO(tavily)`, falls back to a clearly labeled mock result if `TAVILY_API_KEY` unset |
| `FINDINGS.md` narrative | Generated via `agentdyno report`; supports both `MockModelBackend` and a single real Nemotron Ultra call (`AGENTDYNO_BACKEND=nebius agentdyno report`) — default documented here is `mock` for cheap iteration |
| Harbor eval framework integration (full trial execution) | Not yet wired; this repo runs its own minimal task/trial loop instead. See `NebiusSandboxEnvironment` row above for how far the Harbor *environment* integration itself got |

## License

Apache-2.0. See `LICENSE`.
