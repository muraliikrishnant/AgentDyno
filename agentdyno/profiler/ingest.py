"""Reads per-trial JSONL spans + trial results into DuckDB tables backed by
Parquet files under data/."""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SPANS_DIR = DATA_DIR / "spans"
RESULTS_DIR = DATA_DIR / "results"
DB_PATH = DATA_DIR / "agentdyno.duckdb"


def load_spans(trial_id: str) -> list[dict]:
    path = SPANS_DIR / f"{trial_id}.jsonl"
    if not path.exists():
        return []
    spans = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                spans.append(json.loads(line))
    return spans


def ingest(trial_results: list[dict]) -> Path:
    """trial_results: list of dicts with trial_id, architecture, task_id,
    tier, seed, success, n_model_calls, n_tool_round_trips, wall_clock_s."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_spans = []
    for tr in trial_results:
        for span in load_spans(tr["trial_id"]):
            span["architecture"] = tr["architecture"]
            span["task_id"] = tr["task_id"]
            span["seed"] = tr["seed"]
            all_spans.append(span)

    con = duckdb.connect(str(DB_PATH))
    con.execute("DROP TABLE IF EXISTS trials")
    con.execute("""
        CREATE TABLE trials (
            trial_id VARCHAR, architecture VARCHAR, task_id VARCHAR, tier VARCHAR,
            seed INTEGER, success BOOLEAN, n_model_calls INTEGER,
            n_tool_round_trips INTEGER, wall_clock_s DOUBLE
        )
    """)
    for tr in trial_results:
        con.execute(
            "INSERT INTO trials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                tr["trial_id"], tr["architecture"], tr["task_id"], tr["tier"],
                tr["seed"], tr["success"], tr["n_model_calls"],
                tr["n_tool_round_trips"], tr["wall_clock_s"],
            ],
        )

    con.execute("DROP TABLE IF EXISTS spans")
    if all_spans:
        con.execute("""
            CREATE TABLE spans (
                span_id VARCHAR, trial_id VARCHAR, model VARCHAR, tier VARCHAR,
                role VARCHAR, architecture VARCHAR, task_id VARCHAR, seed INTEGER,
                t_request_start DOUBLE, t_first_token DOUBLE, ttft_s DOUBLE,
                itl_mean_s DOUBLE, itl_p99_s DOUBLE, decode_throughput_tok_s DOUBLE,
                prompt_tokens INTEGER, completion_tokens INTEGER, wall_clock_s DOUBLE
            )
        """)
        for s in all_spans:
            con.execute(
                "INSERT INTO spans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    s.get("span_id"), s.get("trial_id"), s.get("model"), s.get("tier"),
                    s.get("role"), s.get("architecture"), s.get("task_id"), s.get("seed"),
                    s.get("t_request_start"), s.get("t_first_token"), s.get("ttft_s"),
                    s.get("itl_mean_s"), s.get("itl_p99_s"), s.get("decode_throughput_tok_s"),
                    s.get("prompt_tokens"), s.get("completion_tokens"), s.get("wall_clock_s"),
                ],
            )
    else:
        con.execute("""
            CREATE TABLE spans (
                span_id VARCHAR, trial_id VARCHAR, model VARCHAR, tier VARCHAR,
                role VARCHAR, architecture VARCHAR, task_id VARCHAR, seed INTEGER,
                t_request_start DOUBLE, t_first_token DOUBLE, ttft_s DOUBLE,
                itl_mean_s DOUBLE, itl_p99_s DOUBLE, decode_throughput_tok_s DOUBLE,
                prompt_tokens INTEGER, completion_tokens INTEGER, wall_clock_s DOUBLE
            )
        """)

    con.execute(f"COPY trials TO '{RESULTS_DIR / 'trials.parquet'}' (FORMAT PARQUET)")
    con.execute(f"COPY spans TO '{RESULTS_DIR / 'spans.parquet'}' (FORMAT PARQUET)")
    con.close()
    return DB_PATH
