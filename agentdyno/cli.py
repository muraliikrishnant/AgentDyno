"""AgentDyno CLI: `agentdyno run experiments/mvp.yaml`, `agentdyno
serve-gateway`, `agentdyno report`."""
from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

import httpx
import typer
import uvicorn
import yaml
from rich.console import Console
from rich.table import Table

from agentdyno.gateway.models import model_id_for_tier
from agentdyno.harbor_provider.nebius_sandbox import LocalSubprocessEnvironment
from agentdyno.harness.core import Harness
from agentdyno.harness.orchestration.single import SingleAgentConfig, run_single_agent
from agentdyno.harness.orchestration.subagents import SubagentsConfig, run_subagents
from agentdyno.profiler.derive import derive
from agentdyno.profiler.ingest import ingest
from agentdyno.report.analyze import write_findings

app = typer.Typer(help="AgentDyno: inference-aware coding-agent harness lab")
console = Console()

REPO_ROOT = Path(__file__).resolve().parents[1]


def _start_gateway_in_background(host: str = "127.0.0.1", port: int = 8000) -> None:
    from agentdyno.gateway.proxy import app as gateway_app

    config = uvicorn.Config(gateway_app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://{host}:{port}/healthz"
    for _ in range(50):
        try:
            httpx.get(url, timeout=1.0)
            return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError("gateway failed to start")


@app.command()
def run(experiment_path: str):
    """Expand the experiment matrix, run each trial, and write results."""
    config = yaml.safe_load(Path(experiment_path).read_text())
    gateway_url = config.get("gateway_url", "http://127.0.0.1:8000/v1/chat/completions")
    max_steps = config.get("max_steps", 4)
    timeout_s = config.get("timeout_s", 20)

    backend = os.environ.get("AGENTDYNO_BACKEND", "mock")
    console.print(f"[bold cyan]Starting telemetry gateway ({backend} backend)...[/bold cyan]")
    _start_gateway_in_background()

    trials = [
        {"architecture": arch, "task": task, "tier": tier, "seed": seed}
        for arch in config["architectures"]
        for task in config["tasks"]
        for tier in config["model_tiers"]
        for seed in config["seeds"]
    ]
    console.print(f"Expanded matrix to {len(trials)} trials.")

    results = []
    for trial in trials:
        if trial["architecture"] not in ("single", "subagents"):
            console.print(f"[yellow]Skipping unimplemented architecture: {trial['architecture']}[/yellow]")
            continue

        trial_id = str(uuid.uuid4())
        task_dir = REPO_ROOT / trial["task"]
        instruction = (task_dir / "instruction.txt").read_text()

        env = LocalSubprocessEnvironment(task_dir=str(task_dir))
        workdir = env.start()
        t_start = time.monotonic()
        try:
            harness = Harness(
                gateway_url=gateway_url,
                model=model_id_for_tier(trial["tier"]),
                tier=trial["tier"],
                trial_id=trial_id,
                max_steps=max_steps,
                timeout_s=timeout_s,
            )
            if trial["architecture"] == "subagents":
                result = run_subagents(
                    harness=harness,
                    instruction=instruction,
                    workdir=workdir,
                    broken_file=str(Path(workdir) / "broken.py"),
                    solution_file=str(Path(workdir) / "solution.py"),
                    config=SubagentsConfig(max_steps_per_subagent=max_steps, seed=trial["seed"]),
                )
            else:
                result = run_single_agent(
                    harness=harness,
                    instruction=instruction,
                    workdir=workdir,
                    broken_file=str(Path(workdir) / "broken.py"),
                    solution_file=str(Path(workdir) / "solution.py"),
                    config=SingleAgentConfig(max_steps=max_steps, seed=trial["seed"]),
                )
            wall_clock_s = time.monotonic() - t_start
            results.append({
                "trial_id": trial_id,
                "architecture": trial["architecture"],
                "task_id": Path(trial["task"]).name,
                "tier": trial["tier"],
                "seed": trial["seed"],
                "success": result.success,
                "n_model_calls": result.n_model_calls,
                "n_tool_round_trips": result.n_tool_round_trips,
                "wall_clock_s": wall_clock_s,
            })
        finally:
            env.stop(delete=True)

    console.print(f"[green]Completed {len(results)} trials.[/green]")

    ingest(results)
    derived = derive()

    table = Table(title="AgentDyno MVP Run Summary")
    for col in ["architecture", "tier", "n_trials", "success_rate", "ttft_mean_s", "itl_p99_s", "cost_per_solved_task"]:
        table.add_column(col)
    for _, row in derived["per_architecture"].iterrows():
        table.add_row(
            row["architecture"], row["tier"], str(row["n_trials"]),
            f"{row['success_rate']:.2f}", f"{row['ttft_mean_s']:.3f}",
            f"{row['itl_p99_s']:.3f}", f"{row['cost_per_solved_task']:.6f}",
        )
    console.print(table)
    console.print(f"Data written under [bold]{REPO_ROOT / 'data'}[/bold]. Run `streamlit run dashboard/app.py` to view it.")


@app.command("serve-gateway")
def serve_gateway(host: str = "127.0.0.1", port: int = 8000):
    """Launch the FastAPI telemetry proxy in the foreground."""
    from agentdyno.gateway.proxy import app as gateway_app

    uvicorn.run(gateway_app, host=host, port=port)


@app.command()
def report(gateway_url: str = "http://127.0.0.1:8000/v1/chat/completions"):
    """Run report/analyze.py to (re)generate FINDINGS.md."""
    out = write_findings(gateway_url=gateway_url)
    console.print(f"[green]Wrote {out}[/green]")


if __name__ == "__main__":
    app()
