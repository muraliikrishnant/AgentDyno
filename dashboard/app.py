"""AgentDyno dashboard ("the dyno readout"): Pareto scatter (success vs
cost), TTFT/ITL distributions, single-trajectory drill-in. Run with
`streamlit run dashboard/app.py` after `agentdyno run experiments/mvp.yaml`
has populated data/."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from agentdyno.profiler.derive import DB_PATH, derive
from agentdyno.profiler.ingest import SPANS_DIR

st.set_page_config(page_title="AgentDyno Dashboard", layout="wide")
st.title("AgentDyno — the dyno readout")
st.caption(
    "Success vs inference cost across harness architectures. Model backend is "
    "mocked pending Nebius Token Factory / Nemotron credentials."
)

if not DB_PATH.exists():
    st.warning("No data yet. Run `agentdyno run experiments/mvp.yaml` first.")
    st.stop()

result = derive()
per_arch = result["per_architecture"]
per_trial = result["per_trial"]
frontier = pd.DataFrame(result["pareto_frontier"])

st.header("Pareto frontier: success rate vs cost per solved task")
if not per_arch.empty:
    chart_df = per_arch.copy()
    chart_df["label"] = chart_df["architecture"] + " / " + chart_df["tier"]
    st.scatter_chart(chart_df, x="cost_per_solved_task", y="success_rate", color="label")
    st.dataframe(per_arch)
else:
    st.info("No per-architecture data yet.")

st.header("TTFT / ITL distributions")
col1, col2 = st.columns(2)
with col1:
    st.subheader("TTFT mean by architecture/tier")
    if not per_trial.empty:
        st.bar_chart(per_trial, x="trial_id", y="ttft_mean_s")
with col2:
    st.subheader("ITL P99 by architecture/tier")
    if not per_trial.empty:
        st.bar_chart(per_trial, x="trial_id", y="itl_p99_s")

st.header("Single-trajectory drill-in")
trial_ids = per_trial["trial_id"].tolist() if not per_trial.empty else []
if trial_ids:
    selected = st.selectbox("Trial", trial_ids)
    span_file = SPANS_DIR / f"{selected}.jsonl"
    if span_file.exists():
        spans = [json.loads(line) for line in span_file.read_text().splitlines() if line.strip()]
        span_df = pd.DataFrame(spans)
        if not span_df.empty:
            span_df["call_index"] = range(len(span_df))
            st.line_chart(span_df, x="call_index", y="ttft_s")
            st.dataframe(span_df[["call_index", "role", "tier", "ttft_s", "itl_mean_s", "decode_throughput_tok_s"]])
    else:
        st.info("No span file found for this trial.")
else:
    st.info("No trials available yet.")
