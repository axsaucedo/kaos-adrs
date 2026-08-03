# xai revitalization — getting started with this effort

This is the entry point to the documentation of the `xai` revitalization: the pivot of [github.com/EthicalML/xai](https://github.com/EthicalML/xai) (a 2017 tabular explainability/fairness toolkit, ~1,150 lines of pandas/matplotlib, v0.3.0) into **explainability for 2026 agentic systems** — a provider-neutral analysis layer that turns agent trajectories, and where possible the model's internal state, into decision evidence. Positioning line: *"xai turned dataframes into fairness evidence in 2017; it turns agent trajectories into decision evidence in 2026."*

## What the library will do (the 60-second version)

Three layers, one foundation, honestly labeled evidence throughout:

- **A — Trajectory Diagnostics.** Load an agent trace from any major source (Langfuse, OTel GenAI / OpenInference, plain JSON) into one canonical pandas dataframe; run deterministic diagnostics. Answers *what happened*. "The pandas of agent traces."
- **B — Decision Attribution.** Counterfactual replay with a real statistical contract — planted-cause-calibrated intervals, controlled false positives, and a ten-state result taxonomy that abstains rather than overclaims. Answers *why*, falsifiably — the cell no observability vendor fills.
- **F — Parametric Instrumentation.** For self-hosted models, instrument the *inference server* (never the agent) to emit internal signals — uncertainty (cheap, always-on), cost (zero-touch), optional probes (opt-in, expensive) — as trace-correlated spans that A and B consume. Additive by design: API-model users lose nothing.

Plus a Textual **TUI debugger** (`xai debug`): trajectory tree → step inspector → live replay panel. No dashboard, no trace store, no server — deliberate non-goals.

## What has been done (status: ready for implementation)

The effort ran research → validation spikes → ADRs → plan → integration prototype, in that order, with every load-bearing claim either validated on runnable evidence or precisely refuted before being claimed:

1. **Research (stages 1–13, complete).** Four landscape reports, direction synthesis, deep-research imports on causal attribution, probe science, OTel transport, and regulatory evidence, plus the canonical schema spec ([stage 9](./research/9-trajectory-schema-canonicalization.md)). Index: [`research/0-research-plan.md`](./research/0-research-plan.md).
2. **Validation campaign (spikes S1–S7, complete).** Eight days of assumptions compressed into measured facts — including a one-day GPU tier on a disposable L4. Highlights: dual-source ingestion proven; the replay statistical contract calibrated at scale (FPR 0/400); server-side uncertainty validated as a transfer-stable signal; the expensive probe tier honestly shown *not* to beat the free channel at small scale; four negative results preserved as first-class findings. One-stop read: [`impl/learnings/campaign-synthesis.md`](./impl/learnings/campaign-synthesis.md).
3. **ADR phase (complete).** Four decisions with options, trade-offs, and consequences, plus the user-facing API overview with per-stack integration workflows and a KAOS production reference.
4. **Plan (complete).** [`plan/proposed-split.md`](./plan/proposed-split.md): how the repository restructures — tabular API frozen (not deleted), new package layout, serve packages as separate distributions, increments 0.4.0 → 1.0.0 with gates.
5. **Integration prototype (spike S8, complete and functional).** Everything assembled on branch **`spike/s8-integration`** of the source repo: `xai_proto` package, 30 tests green, a one-command demo running the full arc against a real local model, and the working three-pane TUI. Six reviewable commits, one per phase. Findings fed back into the plan as ten seam amendments.

## Suggested review order

| Step | Read | Why |
|---|---|---|
| 0 | [`user-guide.md`](./user-guide.md) | **Start here** — a narrative walkthrough of the actual working interface (load → diagnose → explain → signals → TUI), every output real, captured from the prototype. |
| 1 | [`adrs/library-interface-overview.md`](./adrs/library-interface-overview.md) | The user's-eye view of the whole library — API, workflows, production shape. |
| 2 | [`adrs/adr_0001…`](./adrs/adr_0001_trajectory-schema-and-ingestion.md) · [`0002`](./adrs/adr_0002_decision-attribution-replay.md) · [`0003`](./adrs/adr_0003_parametric-instrumentation.md) · [`0004`](./adrs/adr_0004_visualization-tui.md) | The four decisions, each with alternatives and evidence links. |
| 3 | [`plan/proposed-split.md`](./plan/proposed-split.md) | How the repo gets there, increment by increment, including the S8 amendments. |
| 4 | [`impl/learnings/campaign-synthesis.md`](./impl/learnings/campaign-synthesis.md) | The evidence base in one read; per-spike learnings ([S1](./impl/learnings/S1-trace-ingestion.md)–[S8](./impl/learnings/S8-integration.md)) for depth. |
| 5 | The `spike/s8-integration` branch | The working code, commit-per-phase (`816577f` core → `db870bd` hardening); `spike_s8/README.md` is its guide. |

## Try it (hands-on, ~5 minutes)

```bash
cd /Users/asaucedo/Programming/ethical/xai
git checkout spike/s8-integration
uv pip install -e "spike_s8[tui]"
uv run pytest spike_s8/tests                      # 30 tests, incl. the statistical calibration marker
python spike_s8/demo/run_demo.py --recorded       # the full arc: ingest → diagnose → explain → signals → HTML
python -m xai_proto.tui spike_s8/tests/fixtures/signals-trace.json   # the three-pane debugger
```

Live mode (`--live`) additionally runs a real agent against the pinned local Qwen3-0.6B — see `spike_s8/README.md` for the server launch line.

## Where things live

- `research/` — stages 0–13 (stage 0 is the master index and status). `research/deep-research-prompts/` holds the prompts behind imported stages.
- `adrs/` — the four ADRs and the interface overview.
- `plan/` — the proposed split plus per-spike phase-gated execution plans (S3–S8).
- `impl/learnings/` — per-spike learnings and the campaign synthesis; `impl/gpu-validation-cluster-setup.md` is the reproducible GPU-tier infrastructure record.
- Source repo: spike code for S1–S7 under gitignored `tmp/spikes/`; S8 committed on `spike/s8-integration`.

**Next milestone:** implementation increment A (0.4.0) per the proposed split — schema, ingestion, trajectory, diagnostics, with the tabular API moved and shimmed.
