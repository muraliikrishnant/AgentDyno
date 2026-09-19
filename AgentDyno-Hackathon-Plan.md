# AgentDyno — Inference-Aware Coding-Agent Harness Lab
### Build plan for the Nebius × NVIDIA Global AI Hackathon (Coding & Agentic Engineering Track)

> **One-liner:** AgentDyno runs coding agents against real software-engineering tasks in Nebius Token Factory Sandboxes and, for every harness *architectural decision* you flip, measures both **task success** and the **full inference workload it costs** (TTFT, ITL, decode throughput, tokens, tool-call round-trips, sandbox time, $) — then plots the success-vs-cost Pareto frontier.

- **Hackathon deadline:** Oct 5, 2026 @ 10:00am PDT
- **Track:** Coding and Agentic Engineering (prize: NVIDIA Jetson Orin Nano) + eligible for Grand ($20k) and Best Use of Tavily ($3k)
- **Target role this project is engineered to support:** NVIDIA — *Software Engineer, Coding Agent Harness Engineering, New College Grad 2026* (JR2023749)
- **Required by rules:** must run on Nebius Token Factory **or** Nebius AI Cloud, and use ≥1 NVIDIA open-source model (Nemotron). ✅ AgentDyno uses both Token Factory (inference + Sandboxes) and Nemotron Nano/Super/Ultra.

---

## 1. Why this project (strategy)

The hackathon's coding track is already crowded with "plan → patch → test → open a PR" agents (SandForge, sdlc-code, nemotron-auto-dev-agent, etc.). Competing on *"my coding agent writes better PRs"* is a coin-flip.

Your NVIDIA JD is **not** about building a coding agent. It's about **harness engineering** and **profiling inference workload dynamics**:

> *"profile real coding agent workloads to develop a world-class understanding of how these agents evolve"* … *"Building and modifying coding agent harnesses to research the impact of different architectural decisions"* … *"Architecting AI-driven systems that analyze inference workload dynamics of leading agentic harnesses under realistic conditions."*

AgentDyno **is that job**, delivered as an open-source project. It changes the question from *"can this agent solve the task?"* to *"what does each architectural choice cost in latency and compute, and where is the sweet spot?"* — which is exactly the frontier the NVIDIA team works on.

### The real-world problem (the pitch to judges)
Coding agents are the fastest-growing driver of AI inference demand. New agentic patterns — reasoning models, parallel subagents, long-horizon tool use — are scaling inference workloads fast. Yet teams pick harness architectures by **task-success leaderboards alone**, blind to what those choices cost in **latency and compute**. AgentDyno makes the **success-vs-inference-cost tradeoff measurable**, so anyone deploying coding agents (including Nebius/NVIDIA themselves) can choose harness architectures that are both capable *and* affordable.

---

## 2. What "differentiated and rigorous" means here (4 pillars)

1. **Nebius Sandbox provider for Harbor.** Harbor (the eval framework literally named in your JD, from the Terminal-Bench / Laude Institute team) ships providers for Daytona, Modal, Novita, Blaxel, Runta… but **not Nebius**. AgentDyno contributes a `NebiusSandboxEnvironment` adapter so Harbor trials can execute in Token Factory Sandboxes (microVM isolation + Git-like checkpoint/branch). This is a genuine, upstream-able OSS contribution and directly demonstrates "modifying coding agent harnesses at scale."
2. **A model-traffic telemetry gateway.** Harbor "does not provide a gateway that … mediates the harness's model traffic." AgentDyno adds an OpenAI-compatible streaming proxy in front of Token Factory that captures per-call **TTFT / ITL / decode throughput / token counts** without touching agent code. This is the "AI-driven system that analyzes inference workload dynamics" from the JD.
3. **A real scientific result.** The core finding you demonstrate: *in agentic workloads you pay a TTFT tax on every tool-call round trip, and that tax — not raw tokens/sec — dominates wall-clock cost for many architectures.* You quantify it per architecture.
4. **Nemotron tiering as an experimental variable.** Nano/Super/Ultra routing isn't a checkbox — it's one axis of the experiment matrix. The required model usage *is* the science.

---

## 3. JD → project mapping (bring this table to the interview)

| JD requirement | How AgentDyno satisfies it |
|---|---|
| *Building and modifying coding agent harnesses to research architectural decisions* | The **Harness Core** is modular with swappable architecture configs (single-agent / parallel subagents / plan-execute / ReAct / compaction / routing). Flipping a config *is* the experiment. |
| *Architecting AI-driven systems that analyze inference workload dynamics under realistic conditions* | **Telemetry Gateway + Profiler** capture and analyze TTFT/ITL/throughput/token dynamics across realistic SWE tasks in sandboxes. |
| *Familiarity with agent evaluation frameworks such as Harbor* | You **extend** Harbor (new Nebius sandbox provider) and run real Harbor benchmarks (Terminal-Bench / SWE-bench-style tasks). |
| *Inference performance metrics including TTFT, throughput, and ITL* | These are AgentDyno's **primary measured quantities**, captured per model call and aggregated to percentiles. |
| *Hands-on use of frontier coding agents such as Codex and Claude Code* | Harbor runs Claude Code / Codex CLI / OpenHands / Aider as installed agents; you profile them side-by-side with your Nemotron harness. |
| *Rigorous, scientific approach to data collection, analysis, research* | Warmup runs, percentile reporting (P50/P95/P99), controlled variables, reproducible configs, phase-separated (prefill/decode) measurement — documented as methodology. |
| *(Stand out) Open source projects showcasing agentic AI applications* | Entire repo is open source (Apache-2.0), including the upstream-able Harbor provider. |
| *(Stand out) Translate data into specific product improvements with the end user in mind* | The **auto-generated analysis report** (written by Nemotron Ultra) turns the data into concrete "use architecture X for tasks like Y" recommendations. |
| *(Stand out) Experience building modern agentic / AI-backed systems; MS in CS* | Covered by your background; AgentDyno is the flagship artifact. |

> Apply to the role **now** — the posting closes Sept 19. AgentDyno is what you point to in the interview and in follow-ups; the hackathon result (and the open-source Harbor PR) are the proof.

---

## 4. System architecture

```
                                 ┌───────────────────────────────────────────────┐
                                 │                 AGENTDYNO                        │
                                 │        (inference-aware harness lab)             │
                                 └───────────────────────────────────────────────┘

  ┌────────────────┐   experiment matrix (YAML)   ┌──────────────────────────────────────┐
  │  Experiment    │ ───────────────────────────▶ │           HARBOR RUNNER              │
  │  Runner / CLI  │   arch configs × tasks ×      │  (task load → agent → verifier loop) │
  │  (agentdyno    │   models × seeds              │                                      │
  │   run ...)     │ ◀─────────────────────────    │  environment.start()                 │
  └────────────────┘   results + telemetry         │  agent.run(instruction, env)         │
                                                    │  verifier.verify()                   │
                                                    └───────────┬──────────────────────────┘
                                                                │
                        ┌───────────────────────────────────────┼───────────────────────────────────┐
                        │                                       │                                    │
                        ▼                                       ▼                                    ▼
        ┌──────────────────────────────┐        ┌──────────────────────────────┐    ┌──────────────────────────────┐
        │   HARNESS CORE (swappable)   │        │  NEBIUS SANDBOX PROVIDER      │    │   VERIFIER / BENCHMARK        │
        │  ┌────────────────────────┐  │  exec  │  (new Harbor environment)     │    │  Terminal-Bench / SWE-bench   │
        │  │ orchestration policy   │  │ ─────▶ │  Token Factory Sandboxes:     │    │  tasks; pass/fail + rubric    │
        │  │  • single agent        │  │  code  │  • microVM isolation          │    │  reward (ATIF trajectory)     │
        │  │  • parallel subagents  │  │        │  • checkpoint / branch / fork │    └──────────────────────────────┘
        │  │  • plan-then-execute   │  │ ◀───── │  • logs / files / artifacts   │
        │  │  • ReAct               │  │ result └──────────────────────────────┘
        │  ├────────────────────────┤  │
        │  │ tools                  │  │
        │  │  • shell / edit / read │  │
        │  │  • run_tests (sandbox) │  │
        │  │  • tavily_search  ◀────┼──┼──── web search (profiled tool, $3k prize)
        │  ├────────────────────────┤  │
        │  │ context manager        │  │
        │  │  • truncate / summarize│  │
        │  │  • compaction (Nano)   │  │
        │  └────────────────────────┘  │
        └──────────────┬───────────────┘
                       │ every model call goes through the gateway
                       ▼
        ┌────────────────────────────────────────────────────────────┐
        │            TELEMETRY GATEWAY (OpenAI-compatible proxy)      │
        │  streams tokens; stamps per-call:                          │
        │   t_request_start ─▶ t_first_token (TTFT)                  │
        │   inter-token deltas (ITL series)                          │
        │   decode throughput = out_tokens / decode_seconds         │
        │   prompt_tokens / completion_tokens / model / tier / role │
        │   emits a JSONL span per call  ──────────────┐            │
        └──────────────────────────┬───────────────────┼────────────┘
                                   │ routes to          │
                                   ▼                    │ spans
        ┌────────────────────────────────────────────┐ │
        │        NEBIUS TOKEN FACTORY (inference)     │ │
        │  nvidia/nemotron-3-nano-*   (fast tier)     │ │
        │  nvidia/nemotron-3-super-120b-a12b (coder)  │ │
        │  nvidia/nemotron-3-ultra-*  (reasoning)     │ │
        └────────────────────────────────────────────┘ │
                                                        ▼
                         ┌───────────────────────────────────────────────────────┐
                         │   PROFILER + DATA STORE (DuckDB / Parquet + JSONL)     │
                         │  joins: trajectory (ATIF) × telemetry spans × verdict │
                         │  derives: TTFT-tax/task, cost/solved-task,            │
                         │  prefill-vs-decode split, tool-round-trip counts      │
                         └───────────────────────────┬───────────────────────────┘
                                                     │
                          ┌──────────────────────────┴──────────────────────────┐
                          ▼                                                      ▼
          ┌──────────────────────────────────┐              ┌──────────────────────────────────────┐
          │  DASHBOARD ("the dyno readout")   │              │  AUTO-ANALYSIS REPORT                 │
          │  Streamlit/Next: success × cost   │              │  Nemotron Ultra reads the aggregate   │
          │  Pareto frontier; per-arch cards; │              │  tables → writes findings +           │
          │  TTFT/ITL distributions; drill-in │              │  "use arch X for task class Y"        │
          │  to a single trajectory timeline  │              │  product recommendations              │
          └──────────────────────────────────┘              └──────────────────────────────────────┘
```

### Component responsibilities

- **Experiment Runner / CLI (`agentdyno`)** — reads an experiment matrix (architectures × tasks × models × seeds), fans out trials through Harbor, collects results + telemetry, writes to the data store. One command reproduces an entire study.
- **Harbor Runner** — the standard Harbor task/trial loop (`environment.start → agent.run → verifier.verify → environment.stop`). You reuse Harbor's benchmark registry and verifiers rather than reinventing eval infra.
- **Harness Core (the thing you "build and modify")** — a modular coding agent whose **orchestration policy, tool set, and context manager are configuration, not code changes**. Each config is one experimental condition.
- **Nebius Sandbox Provider** — a Harbor `Environment` implementation backed by Token Factory Sandboxes; exposes `start / exec / checkpoint / branch / read_files / stop`. The checkpoint/branch feature lets you profile "backtracking" architectures cleanly.
- **Telemetry Gateway** — OpenAI-compatible streaming proxy; the only thing that touches model traffic, so it captures TTFT/ITL/throughput uniformly for *every* harness config and for third-party agents (Claude Code, Codex) too.
- **Profiler + Data Store** — joins agent trajectories (Harbor/ATIF) to inference telemetry spans and task verdicts; derives the second-order metrics.
- **Dashboard + Auto-Analysis** — the human-facing payoff: the Pareto plot and a Nemotron-written findings report.

---

## 5. The measurement pipeline (end-to-end data flow)

```
 [experiment.yaml]
      │  architectures: [single, subagents, plan_execute, react]
      │  tasks:         terminal-bench@2.0 subset (N tasks)
      │  model_tiers:   [nano_only, super_only, ultra_plan_super_code, routed]
      │  tools:         [core, core+tavily]
      │  seeds:         [1,2,3]
      ▼
 (1) EXPAND MATRIX  ──▶ list of Trials  (arch × task × tier × tools × seed)
      ▼
 (2) FOR EACH TRIAL:
        a. Harbor: environment.start()  ── Nebius Sandbox provider spins a microVM,
                                            clones the task repo, restores baseline checkpoint
        b. Harness.run(instruction, env):
              loop:
                 ├─ model call ──▶ TELEMETRY GATEWAY ──▶ Token Factory (Nemotron)
                 │                     ▲ captures TTFT, ITL[], decode_tps, tokens, role, tier
                 ├─ tool call  ──▶ sandbox exec (run_tests / shell / edit)  ── capture exec_ms
                 ├─ (optional) tavily_search  ── capture round-trip + added context tokens
                 └─ context manager: compact/summarize when window pressure hits
        c. Harbor: verifier.verify()  ── pass/fail (+ rubric reward), emit ATIF trajectory
        d. environment.stop(delete=True)
      ▼
 (3) INGEST: write one Parquet row per trial + JSONL span per model call
      ▼
 (4) DERIVE (Profiler):
        • task_success (bool), rubric_reward
        • n_model_calls, n_tool_round_trips
        • TTFT: mean / P50 / P95 / P99  (and summed "TTFT tax" per task)
        • ITL: mean / P99  ;  decode throughput tokens/s
        • prompt_tokens vs completion_tokens (prefill-heavy vs decode-heavy signature)
        • wall_clock_s, sandbox_exec_s, $cost (tokens × per-tier price)
        • cost_per_solved_task = Σcost / Σsolved
      ▼
 (5) ANALYZE:
        • success-rate vs cost/latency  → Pareto frontier per architecture
        • TTFT-tax attribution: how much wall-clock is "waiting on first token" vs decoding vs sandbox
        • ablations: subagents parallelism vs serialized TTFT; compaction on/off; tavily on/off
      ▼
 (6) PRESENT:
        • Dashboard (interactive)
        • Nemotron-Ultra auto-report (markdown) checked into repo as FINDINGS.md
```

### What makes it "realistic conditions" (JD language)
- Real benchmark tasks (Terminal-Bench / SWE-bench-family) in real containers, not synthetic prompts.
- Real tool-use loops with real sandbox execution latency between model calls.
- Concurrency knob (`--n-concurrent`) so you can also observe how TTFT inflates under load (queuing delay), which is the production-relevant regime.

---

## 6. The experiment matrix (your "research")

The point of the harness being modular is that each row below is a **controlled experiment**. Start small (MVP = 2 architectures × 10 tasks × 2 tiers × 2 seeds = 80 trials) and expand.

| Axis | Conditions to profile | Hypothesis you're testing |
|---|---|---|
| **Orchestration** | single-agent · parallel subagents · plan-then-execute · ReAct | Subagents raise success but multiply model calls → does the TTFT tax eat the wall-clock win? |
| **Model tier routing** | Nano-only · Super-only · Ultra-plan+Super-code · dynamic routed | Where's the accuracy/$ sweet spot? Does Ultra-for-planning pay for itself? |
| **Context management** | truncate · summarize-with-Nano compaction · none | Compaction cuts prompt tokens (lower TTFT) — but does the extra summarize call cost more than it saves? |
| **Thinking budget** | low · high reasoning effort | How much does "more thinking" cost in decode tokens per solved task? |
| **Tools** | core tools · core + Tavily web search | Does web search improve success enough to justify the extra round-trip + context growth (TTFT tax)? |
| **Concurrency** | 1 · 4 · 16 concurrent trials | How does queuing delay inflate TTFT P99 under load? |

**Deliverable finding (example shape):** *"Parallel-subagents + Super lifts Terminal-Bench resolution by X points but pays a 2.3× TTFT tax per task; routing planning to Ultra and code to Super recovers most of the accuracy at 0.6× the cost. For short tasks, single-agent Nano is Pareto-optimal."* — This is precisely "translate data into specific product improvements with the end user in mind."

---

## 7. Metrics & methodology (the rigor section — put this in the README)

**Primary (measured per model call, at the gateway):**
- **TTFT** = `t_first_token − t_request_start`. Perceived responsiveness; dominated by prefill compute + queue delay. In agentic loops it is paid on *every* tool-call round trip.
- **ITL** (inter-token latency) = mean gap between consecutive output tokens; reflects decode phase; report **P99** to expose stalls/preemption.
- **Decode throughput** = `output_tokens / (t_last_token − t_first_token)`.
- **Token counts** — prompt vs completion (the prefill-heavy vs decode-heavy signature of each architecture).

**Derived (per trial / per architecture):**
- `TTFT_tax_per_task` = Σ TTFT over all calls in a task (the number nobody else reports).
- `cost_per_solved_task`, `wall_clock`, `sandbox_exec_s`, `n_tool_round_trips`.
- Success rate, rubric reward.

**Methodology guardrails (say these out loud — it's the "scientific approach"):**
- **Warmup** runs discarded before timing (avoid weight-load/compile/KV-cache artifacts).
- **Percentiles not just means** (P50/P95/P99) — means hide the tail that hurts under load.
- **Phase separation** — never conflate TTFT (prefill/queue) with ITL (decode).
- **Controlled variables** — change one axis at a time; fix seeds; pin model IDs and sampling params.
- **Reproducibility** — every result reconstructable from a committed `experiment.yaml` + `agentdyno run`.
- **Confounder note** — TTFT includes queue wait, so report concurrency alongside every latency number.

---

## 8. Tech stack & required-tool usage

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11 | Harbor + Nebius SDKs are Python-first |
| Eval framework | **Harbor** (`uv tool install harbor`) | benchmark registry, verifiers, ATIF trajectories |
| Benchmarks | Terminal-Bench 2.0 subset; SWE-bench-lite subset | start with ~10–20 tasks for iteration speed |
| Sandboxes | **Nebius Token Factory Sandboxes** (Python SDK / REST / MCP) | microVM + checkpoint/branch; free while in beta |
| Inference | **Nebius Token Factory** (OpenAI-compatible) | your promo credits |
| Models (NVIDIA, required) | **Nemotron 3 Nano** (fast/plan/compaction), **Nemotron 3 Super 120B-a12b** (coder/tool-heavy), **Nemotron 3 Ultra** (reasoning + auto-report) | confirm exact model IDs in the live Token Factory catalog; they can change |
| Gateway | FastAPI + httpx streaming (or extend LiteLLM) | OpenAI-compatible; captures token timestamps |
| Data | DuckDB + Parquet + JSONL spans | zero-infra analytics |
| Dashboard | Streamlit (fast) or Next.js (polished) | the "dyno readout" |
| Web search tool | **Tavily** | one profiled harness tool → Best Use of Tavily ($3k) eligibility |
| License | **Apache-2.0** (visible at repo top) | required by rules |

> **Credit discipline:** use Nano for the high-frequency cheap calls (planning, compaction, summaries), Super as the workhorse coder, and Ultra sparingly for the reasoning-tier condition + the single end-of-run analysis report. This mirrors the hackathon's own Nano/Super/Ultra guidance and keeps your promo credits stretching across 6 weeks of experiments.

---

## 9. Repository structure

```
agentdyno/
├── LICENSE                      # Apache-2.0 (visible at top of repo)
├── README.md                    # problem, architecture diagram, quickstart, findings summary
├── FINDINGS.md                  # auto-generated by Nemotron Ultra from the data
├── pyproject.toml
├── experiments/
│   ├── mvp.yaml                 # 2 arch × 10 tasks × 2 tiers × 2 seeds
│   └── full_study.yaml
├── agentdyno/
│   ├── cli.py                   # `agentdyno run experiments/mvp.yaml`
│   ├── harness/
│   │   ├── core.py              # the agent loop
│   │   ├── orchestration/       # single.py, subagents.py, plan_execute.py, react.py
│   │   ├── tools/               # shell.py, edit.py, run_tests.py, tavily_search.py
│   │   └── context/             # truncate.py, compaction.py (Nano)
│   ├── harbor_provider/
│   │   └── nebius_sandbox.py    # NebiusSandboxEnvironment (Harbor provider) ← OSS contribution
│   ├── gateway/
│   │   ├── proxy.py             # OpenAI-compatible streaming proxy
│   │   └── spans.py             # TTFT/ITL/throughput capture → JSONL
│   ├── profiler/
│   │   ├── ingest.py            # trajectories × spans × verdicts → Parquet
│   │   └── derive.py            # TTFT-tax, cost/solved, pareto
│   └── report/
│       └── analyze.py           # Nemotron-Ultra writes FINDINGS.md
├── dashboard/                   # Streamlit or Next.js
└── data/                        # parquet + jsonl (gitignored except sample)
```

---

## 10. Week-by-week build plan (Sept 18 → Oct 30)

**Guiding rule:** get a *thin vertical slice* working end-to-end (one architecture, one task, telemetry captured, one chart) by end of Week 1. Everything after is breadth + polish.

### Week 0 (this weekend) — Foundations
- Register for the hackathon; redeem the Nebius promo code; confirm Token Factory access + Nemotron model IDs.
- Get a Token Factory Sandbox running from the Python SDK ("hello world": create → exec `python -c 'print(1)'` → read logs → stop).
- `uv tool install harbor`; run `harbor run --dataset terminal-bench@2.0 --agent oracle` (or a tiny subset) locally with Docker to learn the loop.
- Create repo with Apache-2.0 license + README skeleton.

### Week 1 — Thin vertical slice ⭐ (most important week)
- **Telemetry Gateway v0:** OpenAI-compatible proxy that forwards to Token Factory and logs TTFT + tokens per call to JSONL. Verify streaming timestamps are real.
- **Harness Core v0:** single-agent ReAct loop with shell + edit + read_file tools, all model calls routed through the gateway, using Nemotron Super.
- Run it against **one** Terminal-Bench task inside a **local** Harbor Docker env first (fastest debug), capture a trajectory + telemetry, produce **one** chart (TTFT per call across the task). *This is your proof-of-life.*

### Week 2 — Nebius Sandbox provider for Harbor
- Implement `NebiusSandboxEnvironment` (`start/exec/checkpoint/branch/read/stop`) against Token Factory Sandboxes.
- Swap Harbor's env to Nebius; re-run the Week-1 task in a real microVM. Now the whole loop runs on Nebius.
- Add ITL series + decode throughput to the gateway. Add `run_tests` sandbox tool.

### Week 3 — Make architecture a variable
- Refactor orchestration into swappable policies: `single`, `subagents`, `plan_execute`. Add model-tier routing (Nano/Super/Ultra) as config.
- Add context manager (truncate + Nano compaction).
- Add the **Experiment Runner**: expand a matrix YAML → fan out trials → collect → Parquet.
- Run the **MVP study** (2 arch × 10 tasks × 2 tiers × 2 seeds). Get real numbers.

### Week 4 — Profiler + Dashboard
- Profiler derives TTFT-tax, cost/solved-task, prefill/decode split, Pareto frontier.
- Dashboard v1 (Streamlit): Pareto scatter (success vs cost), per-architecture cards, TTFT/ITL distributions, single-trajectory drill-in timeline.
- Add **Tavily** as a profiled tool; add the `core+tavily` condition to the matrix.

### Week 5 — Scale, analysis, third-party agents
- Expand to the fuller experiment matrix; add concurrency runs (1/4/16) to show TTFT-under-load.
- Profile at least one **frontier agent through Harbor** (Claude Code or Codex CLI) alongside your Nemotron harness for a headline comparison (uses your gateway for uniform capture where possible).
- **Auto-analysis:** Nemotron Ultra reads aggregate tables → writes `FINDINGS.md` with concrete recommendations.

### Week 6 — Polish + submit (buffer built in)
- README with architecture diagram + quickstart + headline findings; ensure Apache-2.0 visible at top.
- Record the **3-minute demo video** (script below) — this is heavily weighted; do it with time to spare.
- Working demo URL (hosted dashboard) + reproducible `agentdyno run`.
- Write the Nebius/Nemotron/Tavily **feedback** (Most Valuable Feedback prize = $100 ×10; easy points).
- Submit well before Oct 30 @ 10am PDT. **Open a PR upstreaming the Nebius provider to Harbor** — great signal for the NVIDIA interview even if it isn't merged in time.

---

## 11. Minimum viable demo vs. stretch

**MVP (must work for a valid, competitive submission):**
- Harness runs a real SWE task in a **Nebius Sandbox** using **Nemotron**, through the **telemetry gateway**.
- At least **2 architectures** compared on **≥10 tasks** with **TTFT/ITL/throughput/cost** captured.
- One **Pareto chart** + a short written finding.

**Stretch (for Grand Prize contention):**
- Frontier-agent (Claude Code/Codex) comparison through Harbor.
- Concurrency/TTFT-under-load study.
- Dynamic router that picks the tier per step from live telemetry.
- Upstreamed Harbor PR merged/open.
- Nemotron-Ultra `FINDINGS.md` with product recommendations.

---

## 12. Three-minute demo video script

- **0:00–0:25 — Problem.** "Coding agents are the fastest-growing driver of AI inference. But we choose harness architectures by success leaderboards alone — blind to what they cost in latency and compute." Show the crowded leaderboard.
- **0:25–0:55 — Idea.** "AgentDyno is a dynamometer for coding agents: same task, flip an architectural decision, measure success *and* the inference workload it costs." Show the architecture diagram.
- **0:55–1:45 — Live run.** `agentdyno run experiments/mvp.yaml`. Show a task executing in a **Nebius Token Factory Sandbox**, model calls hitting **Nemotron** through the gateway, TTFT/ITL streaming in live. Narrate the Sandbox + Nemotron usage (required by rules).
- **1:45–2:35 — The payoff.** Open the dashboard: Pareto frontier of success vs cost across architectures; drill into one trajectory's TTFT timeline; call out the **TTFT-tax** finding.
- **2:35–3:00 — Result + why it matters.** Read the headline recommendation from `FINDINGS.md`; mention the open-source Harbor provider + Tavily tool. "AgentDyno turns harness architecture from vibes into measurement."

---

## 13. Submission checklist (from the rules)

- [ ] Runs on Nebius Token Factory / AI Cloud ✅ (inference + Sandboxes)
- [ ] Uses ≥1 NVIDIA open-source model ✅ (Nemotron Nano/Super/Ultra)
- [ ] Track selected: **Coding and Agentic Engineering**
- [ ] Project description (what / why / how)
- [ ] Working demo URL (hosted dashboard or test build)
- [ ] ≤3-min public YouTube demo video with audio covering Token Factory + Nemotron usage
- [ ] Public repo (GitHub) with **Apache-2.0 license visible at top**
- [ ] README with setup + run instructions; highlights of Nemotron + Token Factory + Tavily usage
- [ ] Feedback on Token Factory / AI Cloud / NVIDIA tools (also targets the Feedback prize)
- [ ] (If pre-existing code) note what was significantly updated during the period — start fresh to avoid this
- [ ] (If attended a Builders & Brews city event) select the city for the City Winner award

---

## 14. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Sandboxes beta quirks / access delays | Build the harness against a **local Docker Harbor env first** (Week 1); Nebius provider swaps in Week 2. Keep a local fallback path (like SandForge's local mode) so the loop always runs. |
| Gateway timestamps unreliable via proxy | Validate streaming deltas against a known-latency call early; if the provider exposes usage/timing fields, cross-check. Report methodology honestly. |
| Credits burn too fast | Nano for high-frequency calls; small task subsets during dev; cache task builds; cap `max_tokens`; only run the full matrix once, late. |
| Model IDs / catalog change | Pin IDs in config; confirm against the live Token Factory catalog at Week 0 and again before the final run. |
| Scope creep | MVP is sacred (Sec. 11). Everything else is optional breadth. Video by Week 6 with buffer. |
| Exact Nemotron model IDs uncertain here | Verify in the Token Factory console; this doc uses `nvidia/nemotron-3-super-120b-a12b` as the confirmed coder ID and placeholders for Nano/Ultra tiers. |

---

## 15. Interview framing (for NVIDIA)

Lead with the thesis, not the feature list:
> "I built AgentDyno because I noticed the coding-agent ecosystem optimizes for task success and ignores inference cost. I extended **Harbor** with a **Nebius sandbox provider**, put a **telemetry gateway** in front of the model traffic, and profiled how harness architectural decisions — subagents, tier routing, context compaction, tool use — trade off task success against **TTFT, ITL, and throughput** under realistic SWE workloads. The headline finding was the **per-tool-call TTFT tax**, and I translated it into concrete architecture recommendations."

That paragraph hits: harness building/modification, Harbor, TTFT/ITL/throughput, workload-dynamics analysis, rigorous method, open source, and data→product translation — i.e. the entire JD.

---

*Confirm live details before your final run: exact Nemotron model IDs, Sandboxes beta access status, and Token Factory pricing per tier (for the $-cost metric). These can change between now and Oct 30.*
