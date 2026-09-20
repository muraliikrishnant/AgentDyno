# Contributing to AgentDyno

Thanks for looking at this. AgentDyno is a research harness for measuring
the success-vs-inference-cost tradeoff of coding-agent architectures — see
`README.md` for what's built and `AgentDyno-Hackathon-Plan.md` for the full
design doc. Contributions of any size are welcome: bug fixes, a new
orchestration architecture, a new tool, docs, or just filing an issue for
something confusing.

## Setup

Requires Python 3.11+.

```bash
git clone https://github.com/muraliikrishnant/AgentDyno.git
cd AgentDyno
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

(Plain `pip` works too: `python3.11 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.)

No API keys are required for local development — the default
`AGENTDYNO_BACKEND=mock` simulates streaming TTFT/ITL with plausible
latencies, so the full pipeline runs offline.

## Verifying a change

Before opening a PR, run the MVP experiment end to end and confirm it still
completes cleanly:

```bash
agentdyno run experiments/mvp.yaml
```

This starts the telemetry gateway, runs every trial (all architectures x
tasks x tiers x seeds in `experiments/mvp.yaml`) against the local sandbox,
writes data under `data/`, and prints a summary table. If you touched the
profiler or gateway, also check the dashboard renders:

```bash
streamlit run dashboard/app.py
```

If a test suite exists for the area you're changing, run it with `pytest`.
There isn't one for every module yet — adding coverage for a module you're
touching is a welcome contribution on its own.

Never commit against `AGENTDYNO_BACKEND=nebius` in a way that requires real
credentials to pass CI or review — real-backend paths should be reviewable
by reading the diff and, at most, one manual spot-check by someone with
Nebius access.

## Making a change

1. Fork the repo and create a branch off `main`.
2. Make your change. Keep it scoped — a bug fix doesn't need a refactor
   riding along with it.
3. Run the verification above.
4. Open a PR against `main` with a short description of *why*, not just
   *what* (the diff already shows what).

## Code style

- No enforced formatter/linter yet (an easy first contribution). Match the
  surrounding file's style: no unnecessary comments, docstrings only where
  something non-obvious needs explaining (a subtle invariant, a confirmed
  API shape from an external SDK, a `# TODO(nebius)` / `# TODO(harbor)` /
  `# TODO(tavily)` marking a real integration gap).
- Every real-but-incomplete integration point should carry one of those
  `TODO(...)` tags with enough detail (what SDK call, what's unconfirmed)
  that someone else can pick it up without re-deriving context.
- Don't fake a working integration. If something can't be verified end to
  end, say so in the code comment and in `README.md`'s "What's real vs.
  mocked" table rather than claiming it works.

## Where to start

Check the repo's [Issues](../../issues) for ones labeled
[`good first issue`](../../issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
A few areas that are open and self-contained as of this writing:

- `plan_execute` orchestration architecture is a structural stub
  (`agentdyno/harness/orchestration/plan_execute.py`) — implement it the way
  `subagents.py` did for a genuine third condition to compare in the
  experiment matrix.
- A `pytest` suite — most modules have none yet.
- Wiring `experiments/tasks/*` into a real Harbor task manifest (`task.toml`,
  `environment/`) so `harbor run --env agentdyno.harbor_provider.nebius_sandbox:NebiusSandboxEnvironment`
  can execute a real trial — see the "What's real vs. mocked" table in
  `README.md` for exactly where this currently stops.
- Concurrency sweep support (`--n-concurrent`) for observing TTFT under load
  (plan doc section 6).

If you're picking up something not listed here, open an issue first to
avoid duplicate work, especially for anything touching the gateway or
telemetry spans schema (`agentdyno/gateway/spans.py`) — other modules
depend on that shape.

## Reporting bugs / proposing features

Open a GitHub issue. For a bug, include the command you ran and the full
error. For a feature, a sentence on the motivation goes a long way — see
`AgentDyno-Hackathon-Plan.md` section 6 for the experiment axes this
project is designed around, which is useful context for whether a proposal
fits the project's scope.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
