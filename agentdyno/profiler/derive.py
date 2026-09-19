"""Derives per-trial and per-architecture aggregates from the ingested
trials/spans tables: TTFT percentiles, ITL P99, decode throughput, token
counts, model-call/tool-round-trip counts, cost/solved-task, and a Pareto
frontier of success_rate vs cost across architectures."""
from __future__ import annotations

from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "agentdyno.duckdb"

# TODO(nebius): replace with confirmed Nebius Token Factory per-tier pricing
# ($/1K tokens) once the live catalog is available. These are placeholders.
PRICE_PER_1K_TOKENS = {
    "nano": {"prompt": 0.00005, "completion": 0.0002},
    "super": {"prompt": 0.0003, "completion": 0.0012},
    "ultra": {"prompt": 0.0009, "completion": 0.0036},
}


def _cost(tier: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICE_PER_1K_TOKENS.get(tier, PRICE_PER_1K_TOKENS["super"])
    return (prompt_tokens / 1000) * price["prompt"] + (completion_tokens / 1000) * price["completion"]


def per_trial_aggregates(con: duckdb.DuckDBPyConnection) -> "duckdb.DuckDBPyRelation":
    return con.sql("""
        SELECT
            t.trial_id, t.architecture, t.task_id, t.tier, t.seed, t.success,
            t.n_model_calls, t.n_tool_round_trips, t.wall_clock_s AS trial_wall_clock_s,
            COALESCE(SUM(s.ttft_s), 0) AS ttft_tax_s,
            COALESCE(AVG(s.ttft_s), 0) AS ttft_mean_s,
            COALESCE(quantile_cont(s.ttft_s, 0.5), 0) AS ttft_p50_s,
            COALESCE(quantile_cont(s.ttft_s, 0.95), 0) AS ttft_p95_s,
            COALESCE(quantile_cont(s.ttft_s, 0.99), 0) AS ttft_p99_s,
            COALESCE(quantile_cont(s.itl_p99_s, 0.99), 0) AS itl_p99_s,
            COALESCE(AVG(s.decode_throughput_tok_s), 0) AS decode_throughput_tok_s,
            COALESCE(SUM(s.prompt_tokens), 0) AS prompt_tokens,
            COALESCE(SUM(s.completion_tokens), 0) AS completion_tokens
        FROM trials t
        LEFT JOIN spans s ON s.trial_id = t.trial_id
        GROUP BY t.trial_id, t.architecture, t.task_id, t.tier, t.seed, t.success,
                 t.n_model_calls, t.n_tool_round_trips, t.wall_clock_s
    """)


def per_architecture_aggregates(con: duckdb.DuckDBPyConnection) -> "duckdb.DuckDBPyRelation":
    per_trial = per_trial_aggregates(con)
    con.register("per_trial", per_trial)
    rows = con.sql("SELECT * FROM per_trial").fetchdf()

    rows["cost_usd"] = rows.apply(
        lambda r: _cost(r["tier"], r["prompt_tokens"], r["completion_tokens"]), axis=1
    )

    grouped = rows.groupby(["architecture", "tier"]).agg(
        n_trials=("trial_id", "count"),
        n_success=("success", "sum"),
        ttft_mean_s=("ttft_mean_s", "mean"),
        ttft_p99_s=("ttft_p99_s", "mean"),
        itl_p99_s=("itl_p99_s", "mean"),
        decode_throughput_tok_s=("decode_throughput_tok_s", "mean"),
        n_model_calls=("n_model_calls", "mean"),
        n_tool_round_trips=("n_tool_round_trips", "mean"),
        total_cost_usd=("cost_usd", "sum"),
    ).reset_index()

    grouped["success_rate"] = grouped["n_success"] / grouped["n_trials"]
    grouped["cost_per_solved_task"] = grouped.apply(
        lambda r: (r["total_cost_usd"] / r["n_success"]) if r["n_success"] > 0 else float("inf"),
        axis=1,
    )
    return grouped


def pareto_frontier(agg_df) -> list[dict]:
    """Rows on the success_rate-vs-cost Pareto frontier (maximize success,
    minimize cost_per_solved_task)."""
    candidates = agg_df.to_dict("records")
    frontier = []
    for c in candidates:
        dominated = any(
            (o["success_rate"] >= c["success_rate"] and o["cost_per_solved_task"] <= c["cost_per_solved_task"])
            and (o["success_rate"] > c["success_rate"] or o["cost_per_solved_task"] < c["cost_per_solved_task"])
            for o in candidates
        )
        if not dominated:
            frontier.append(c)
    return sorted(frontier, key=lambda r: r["cost_per_solved_task"])


def derive(db_path: Path = DB_PATH) -> dict:
    con = duckdb.connect(str(db_path))
    per_trial = per_trial_aggregates(con).fetchdf()
    agg = per_architecture_aggregates(con)
    frontier = pareto_frontier(agg)
    con.close()
    return {"per_trial": per_trial, "per_architecture": agg, "pareto_frontier": frontier}
