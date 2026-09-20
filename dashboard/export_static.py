"""Exports a self-contained static HTML snapshot of the dashboard's data
(Pareto frontier, per-trial TTFT/ITL, single-trajectory drill-in) for
hosting on Hugging Face's free Static Space SDK, which can't run a live
Streamlit server. Run after `agentdyno run experiments/mvp.yaml`:

    python -m dashboard.export_static

Writes dashboard/static_export/index.html - a snapshot as of generation
time, not a live app. See dashboard/app.py for the live Streamlit version.
"""
from __future__ import annotations

import json
from pathlib import Path

from agentdyno.profiler.derive import DB_PATH, derive
from agentdyno.profiler.ingest import SPANS_DIR

OUT_DIR = Path(__file__).resolve().parent / "static_export"

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>AgentDyno — the dyno readout</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{
    --bg: #0b0e14; --panel: #131722; --text: #e6e8ec; --muted: #8b93a7;
    --accent: #6ea8fe; --border: #232838;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  h1 {{ font-size: 1.6rem; margin-bottom: 4px; }}
  .caption {{ color: var(--muted); margin-bottom: 24px; }}
  .snapshot-note {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px 16px; margin-bottom: 24px; color: var(--muted); font-size: 0.9rem;
  }}
  .snapshot-note a {{ color: var(--accent); }}
  section {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; margin-bottom: 20px;
  }}
  h2 {{ margin-top: 0; font-size: 1.1rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 600; }}
  select {{
    background: var(--bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 10px; margin-bottom: 12px;
  }}
  .charts-row {{ display: flex; gap: 20px; flex-wrap: wrap; }}
  .chart-col {{ flex: 1; min-width: 280px; }}
  canvas {{ max-height: 360px; }}
</style>
</head>
<body>
<h1>AgentDyno — the dyno readout</h1>
<p class="caption">Success vs inference cost across harness architectures.</p>
<div class="snapshot-note">
  Static snapshot generated {generated_at} from a real <code>agentdyno run</code>.
  Not a live app (Hugging Face's free Static Space tier can't run a Streamlit
  server) — for the live version run <code>streamlit run dashboard/app.py</code>
  locally, or see the canonical repo:
  <a href="https://github.com/muraliikrishnant/AgentDyno">github.com/muraliikrishnant/AgentDyno</a>.
</div>

<section>
  <h2>Pareto frontier: success rate vs cost per solved task</h2>
  <canvas id="paretoChart"></canvas>
  <table id="paretoTable"></table>
</section>

<section>
  <h2>TTFT / ITL by trial</h2>
  <div class="charts-row">
    <div class="chart-col"><canvas id="ttftChart"></canvas></div>
    <div class="chart-col"><canvas id="itlChart"></canvas></div>
  </div>
</section>

<section>
  <h2>Single-trajectory drill-in</h2>
  <select id="trialSelect"></select>
  <canvas id="trialChart"></canvas>
  <table id="trialTable"></table>
</section>

<script>
const PER_ARCH = {per_arch_json};
const PER_TRIAL = {per_trial_json};
const SPANS_BY_TRIAL = {spans_json};

const palette = ["#6ea8fe", "#f2a65a", "#7ee787", "#f97583", "#c297ff", "#79c0ff"];

function labelFor(row) {{ return row.architecture + " / " + row.tier; }}

// Pareto scatter
const archLabels = [...new Set(PER_ARCH.map(labelFor))];
new Chart(document.getElementById("paretoChart"), {{
  type: "scatter",
  data: {{
    datasets: archLabels.map((label, i) => ({{
      label,
      data: PER_ARCH.filter(r => labelFor(r) === label).map(r => ({{
        x: r.cost_per_solved_task, y: r.success_rate
      }})),
      backgroundColor: palette[i % palette.length],
      pointRadius: 8,
    }})),
  }},
  options: {{
    scales: {{
      x: {{ title: {{ display: true, text: "cost per solved task ($)" }}, ticks: {{ color: "#8b93a7" }} }},
      y: {{ title: {{ display: true, text: "success rate" }}, min: 0, max: 1.05, ticks: {{ color: "#8b93a7" }} }},
    }},
    plugins: {{ legend: {{ labels: {{ color: "#e6e8ec" }} }} }},
  }},
}});

const paretoTable = document.getElementById("paretoTable");
const paretoCols = ["architecture", "tier", "n_trials", "success_rate", "ttft_mean_s", "itl_p99_s", "cost_per_solved_task"];
paretoTable.innerHTML = "<tr>" + paretoCols.map(c => `<th>${{c}}</th>`).join("") + "</tr>" +
  PER_ARCH.map(r => "<tr>" + paretoCols.map(c => `<td>${{typeof r[c] === "number" ? r[c].toFixed(6) : r[c]}}</td>`).join("") + "</tr>").join("");

// TTFT / ITL per trial
new Chart(document.getElementById("ttftChart"), {{
  type: "bar",
  data: {{
    labels: PER_TRIAL.map(r => r.trial_id.slice(0, 8)),
    datasets: [{{ label: "ttft_mean_s", data: PER_TRIAL.map(r => r.ttft_mean_s), backgroundColor: "#6ea8fe" }}],
  }},
  options: {{ plugins: {{ legend: {{ labels: {{ color: "#e6e8ec" }} }} }}, scales: {{ x: {{ ticks: {{ color: "#8b93a7" }} }}, y: {{ ticks: {{ color: "#8b93a7" }} }} }} }},
}});
new Chart(document.getElementById("itlChart"), {{
  type: "bar",
  data: {{
    labels: PER_TRIAL.map(r => r.trial_id.slice(0, 8)),
    datasets: [{{ label: "itl_p99_s", data: PER_TRIAL.map(r => r.itl_p99_s), backgroundColor: "#f2a65a" }}],
  }},
  options: {{ plugins: {{ legend: {{ labels: {{ color: "#e6e8ec" }} }} }}, scales: {{ x: {{ ticks: {{ color: "#8b93a7" }} }}, y: {{ ticks: {{ color: "#8b93a7" }} }} }} }},
}});

// Trajectory drill-in
const select = document.getElementById("trialSelect");
Object.keys(SPANS_BY_TRIAL).forEach(id => {{
  const opt = document.createElement("option");
  opt.value = id; opt.textContent = id;
  select.appendChild(opt);
}});

let trialChart = null;
function renderTrial(id) {{
  const spans = SPANS_BY_TRIAL[id] || [];
  const ctx = document.getElementById("trialChart");
  if (trialChart) trialChart.destroy();
  trialChart = new Chart(ctx, {{
    type: "line",
    data: {{
      labels: spans.map((_, i) => i),
      datasets: [{{ label: "ttft_s per call", data: spans.map(s => s.ttft_s), borderColor: "#7ee787", tension: 0.2 }}],
    }},
    options: {{ plugins: {{ legend: {{ labels: {{ color: "#e6e8ec" }} }} }}, scales: {{ x: {{ title: {{ display: true, text: "call index" }}, ticks: {{ color: "#8b93a7" }} }}, y: {{ ticks: {{ color: "#8b93a7" }} }} }} }},
  }});
  const cols = ["role", "tier", "ttft_s", "itl_mean_s", "decode_throughput_tok_s"];
  const table = document.getElementById("trialTable");
  table.innerHTML = "<tr>" + cols.map(c => `<th>${{c}}</th>`).join("") + "</tr>" +
    spans.map(s => "<tr>" + cols.map(c => `<td>${{typeof s[c] === "number" ? s[c].toFixed(6) : s[c]}}</td>`).join("") + "</tr>").join("");
}}

if (select.options.length) {{
  select.value = select.options[0].value;
  renderTrial(select.value);
}}
select.addEventListener("change", () => renderTrial(select.value));
</script>
</body>
</html>
"""


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit("No data yet - run `agentdyno run experiments/mvp.yaml` first.")

    result = derive()
    per_arch = result["per_architecture"].to_dict("records")
    per_trial = result["per_trial"].to_dict("records")

    spans_by_trial: dict[str, list[dict]] = {}
    for trial_id in [r["trial_id"] for r in per_trial]:
        span_file = SPANS_DIR / f"{trial_id}.jsonl"
        if span_file.exists():
            spans = [json.loads(line) for line in span_file.read_text().splitlines() if line.strip()]
            spans_by_trial[trial_id] = spans

    from datetime import datetime, timezone

    html = TEMPLATE.format(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        per_arch_json=json.dumps(per_arch),
        per_trial_json=json.dumps(per_trial),
        spans_json=json.dumps(spans_by_trial),
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(html)
    print(f"Wrote {OUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
