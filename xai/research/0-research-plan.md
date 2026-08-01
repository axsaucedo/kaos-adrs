# xai revitalization — research plan (stage 0)

This document is the index and plan for the research phase of the `xai` revitalization. It defines the components under investigation, catalogues the research already carried out (migrated in as numbered stages), enumerates the research still needed, and lists the validation spikes that de-risk the load-bearing assumptions before any design is committed. It is the entry point for everything under `xai/` and is read first.

## What this project is

`xai` (`github.com/EthicalML/xai`, source at `/Users/asaucedo/Programming/ethical/xai`) is a 2017-era tabular ML explainability and fairness toolkit — a ~1,150-line pandas/matplotlib library (`imbalance_plot`, `metrics_plot` sliced by `cross_cols`, permutation `feature_importance`, `balanced_train_test_split`), currently v0.3.0, published under The Institute for Ethical AI & ML. The revitalization pivots it from "explainability for tabular models when SHAP was new" to **explainability for 2026 agentic systems**: a small, provider-neutral analysis layer that turns agent trajectories — and, where the model is self-hosted, its internal state — into decision evidence.

The working thesis, refined across the research so far, is a three-layer arc that shares one foundation and sequences naturally:

- **A — Trajectory Diagnostics & Evidence Layer** (the wedge): a canonical trajectory schema plus adapters (OTel GenAI / OpenInference / Langfuse / Phoenix / plain JSON) and deterministic diagnostics and sliced metrics. "The pandas-of-agent-traces." Answers *what happened*.
- **B — Agent Decision Attribution** (the differentiator): context ablation and counterfactual replay with uncertainty, Monte-Carlo Shapley credit across steps/agents/tools, a planted-cause benchmark so explanations are falsifiable. Answers *why*, defensibly — the question no observability vendor answers.
- **F — Parametric Instrumentation** (the internals layer): when the agent runs on a self-hosted open-weights model, instrument the **inference server** (not the agent — the model virtually never runs in-process with the agent) to emit internal-state signals (logit-uncertainty, linear-probe readings, attention/attribution) as trace-correlated OTel spans that A's diagnostics and B's replay consume. Answers *why* with corroborating internal evidence, and is structurally unavailable to both observability vendors (they instrument the agent SDK, never the serving process) and interpretability labs (they work in-process on single models, never trajectories).

Positioning line: **"xai turned dataframes into fairness evidence in 2017; it turns agent trajectories into decision evidence in 2026."**

## Phase order and conventions

This docs area follows the same structure and order as the `memory/` effort in this repository: `research/` → `adrs/` → `plan/` → `impl/` (with `impl/learnings/` and `impl/progress/`) → `blog/`. The current phase is **research only**; documents here describe, compare, recommend, and validate — they do not change `xai` source. The `xai` repository is read-only for this effort; the only writes are to this `kaos-ai-docs` repository, plus throwaway spike code under the source repo's gitignored `tmp/`.

- **Numbering.** Research documents use a plain numeric stage prefix, `<n>-<name>.md`, starting at this plan (`0-research-plan.md`). Stages `1`–`8` migrate and formalize research already carried out; stages `9`+ are research not yet done. Spikes use an `S<n>` label and record their findings under `impl/learnings/`.
- **Cross-references.** Reference another research document as a Markdown link with `./` for same-folder links (e.g. `[stage 1](./1-landscape-observability.md)`). Reference `xai` source as repository-relative paths where a claim needs to be verifiable.
- **Markdown style.** No hard line-wraps inside paragraphs or list items — one continuous line each, soft-wrapped by the editor. Blank lines between paragraphs, lists, headings, tables, and code fences. Do not reference plan-step numbers inside document bodies; describe work by what it is.
- **Spikes.** Runnable validation code lives under the source repo's `./tmp/` (gitignored), in a throwaway venv; only the learnings writeup is committed here. Suppress noise to `./tmp/null`, never `/tmp`.
- **Commits.** One document per commit, `docs(xai): …` conventional form, describing exactly what was added. No session-URL trailer.

## Research components

The research is organized around seven components of the target system. Every research document and spike maps to one or more of these.

| Component | Core question | Primary stages |
|---|---|---|
| **C1 — Trajectory schema & ingestion** | What is the canonical normalized trajectory, and can it be populated from every major trace source? | 1, 9 |
| **C2 — Behavioral diagnostics** | Which deterministic trajectory failures can be detected from traces alone, and how do they map to published taxonomies (MAST, Who&When)? | 4, 10 |
| **C3 — Causal attribution** | Can ablation/counterfactual replay and step-Shapley produce falsifiable "why" with stated uncertainty, and can it be benchmarked against planted causes? | 2, 10 |
| **C4 — Parametric instrumentation** | What internal signals are worth emitting, from which inference engines, at what cost, and how valid are the probes? | 7, 8, 11 |
| **C5 — Signal transport & correlation** | How do internal-state spans correlate to the agent's trace across the agent↔server boundary, and what does one OTLP path plus per-backend flavours look like? | 8, 12 |
| **C6 — Decision audit & governance** | What must a per-decision explanation packet contain, and what does the EU AI Act actually require as evidence? | 3, 13 |
| **C7 — Positioning & ecosystem** | Is the "why" cell still empty, and how does the Institute's curation (awesome-lists) seed adoption? | 5, 6, 14, 15 |

## Research documents — index and status

### Completed — migrate from the source repo's `tmp/`

These four landscape reports and two synthesis documents were produced in the exploration phase (three by delegated Codex research runs against the 2026 landscape, plus the lists review and the direction synthesis). They are complete and their insights are collected; they migrate into `research/` under the numbering below, lightly edited to the conventions here.

- **1 — `1-landscape-observability.md`** (C1). The 2026 tracing/observability market: Langfuse, LangSmith, Arize Phoenix, W&B Weave, AgentOps, Helicone, OpenLLMetry/Traceloop; OTel GenAI semantic conventions and OpenInference; the OTel-collector-tee integration point. Key finding: everything answers *what happened*; nothing answers *why*. Source: `codex-report-observability.md`.
- **2 — `2-landscape-interpretability.md`** (C3, C4). Classic XAI status (SHAP/Captum/InterpretML alive but tabular-shaped; LIME dormant; Alibi stalled+relicensed); mechanistic interp (SAEs, circuit tracing) research-only; CoT unfaithfulness (~25% hint-mention rate — usable as monitor, not ground truth); latent monitors / probing classifiers as the most production-plausible white-box technique; Captum v0.9.0 remote-vLLM attribution, Inseq, SAELens, Goodfire. Source: `codex-report-interpretability.md`.
- **3 — `3-landscape-governance.md`** (C6). EU AI Act timeline (GPAI enforcement Aug 2026; high-risk Annex III Dec 2027 / Annex I Aug 2028 post-Omnibus; Art. 12 logging, Art. 14 oversight, Art. 86 right-to-explanation); the fairness stack (fairlearn/Aequitas/AIF360) never adapted to agents; LangFair as the closest agent-fairness tool (prompt/response only). Source: `codex-report-governance.md`.
- **4 — `4-landscape-agentic.md`** (C2, C3). Agent-analysis research 2025-26: MAST 14-failure-mode taxonomy (NeurIPS 2025), Who&When failure attribution (ICML 2025), τ-bench/τ²-bench `pass^k`, AgentSHAP, Causal Agent Replay, AgenTracer, AgentDebug/AgentRx/AgentDiagnose, Petri/Bloom behavioral audits, AgentHarm, SHADE-Arena — all research-only/prototype, unpackaged for practitioners. Source: `codex-report-agentic.md`.
- **5 — `5-ecosystem-lists-gap.md`** (C7). Gap review of `awesome-production-agentic-systems` and `awesome-agentic-engineering-resources`: the explainability/attribution/audit cell is empty in both, across ~40 tools and 21 topics — independent validation of the white space, and the launch motion (xai anchors a new "Agent Explainability & Audit" category, mirroring the 2017-19 xai ↔ awesome-mlops pairing). Source: `LISTS_GAPS.md`.
- **6 — `6-direction-synthesis.md`** (C7). The A/B/C/D proposal synthesis, the phased A→B→F recommendation, and the explicit non-goals (no trace store, dashboard, eval runner, guardrail engine, agent runtime, SAE trainer, or "LLM SHAP over tokens"; never present CoT/judge rationales as faithful causes; no automatic fairness verdicts). Note during migration: Proposal C (decision audit) was demoted from a standalone phase to a downstream recipe of B after review — its disparity table is a commodity groupby on hand-annotated columns; its real substance (counterfactual proxy-swap, explanation packet) is B's machinery. Source: `PROPOSALS.md`.

### Completed in-session — formalize from conversation

These two were worked out in the current session (with web verification) and are now written up as design-synthesis documents. They are the C4/C5 core and carry the most novel and most load-bearing claims — each flags its feasibility assumptions inline and gates them on the noted spikes and surveys. The factual substrate of stage 8 additionally has its own feasibility deep-research prompt ([`deep-research-prompts/8-support-engine-introspection-and-ebpf.md`](./deep-research-prompts/8-support-engine-introspection-and-ebpf.md)), distinct from the gap-oriented surveys 10–13, so the engine/eBPF claims get an independent source-backed check.

- **7 — `7-parametric-enriched-traces.md`** (C4, C5). The concept: extend A/B so a self-hosted open-weights model enriches traces with parametric channels. Covers the three synergies — (i) internal signals as new A-diagnostics (`STATED_VS_INTERNAL_MISMATCH` as a live CoT-unfaithfulness detector, `INTERNAL_WARNING_IGNORED`), (ii) attribution as a prior that makes B's replay cheaper (guided ablation), (iii) B's replay validating the correlational probes (triangulation → per-probe calibration, the falsifiability signature). Includes the epistemic-status channel labelling (observed / correlational / causal) and the monitor-mode vs deep-mode split.
- **8 — `8-server-instrumentation-feasibility.md`** (C4, C5). The feasibility assessment: the model runs behind an inference server, not inside the agent, so instrumentation belongs at the server and correlates via OTel context propagation. The eBPF assessment (right tool for the *cost* channel — GPU time/memory/kernel timing, zero-touch via eBPF/bpftime/CUPTI; wrong tool for the *interpretability* channel — activations are unlabeled tensors in VRAM, and semantic identity is a model-graph concept absent at the kernel/PTX layer). The engine/server landscape and instrumentation-tier map: PyTorch engines (vLLM, SGLang) are hook-friendly via a load-time forward-hook plugin (not a fork), reaching everywhere they are embedded; TensorRT-LLM (compiled) is hard, logit-signals only; llama.cpp/Ollama (C++/GGML) is medium, callback-level; TGI is dead (maintenance Dec 2025, EOL-directed to vLLM/SGLang/llama.cpp/MLX Mar 2026); Triton is a backend-agnostic *server*, not an engine. The `instrument_<server>` (produce signals, hard) vs `instrument_<otel-backend>` (route signals, thin OTLP adapters for logfire/langfuse) distinction.

### Not yet carried out — planned research

These answer questions raised by the completed stages and gate the ADRs. Ordered roughly by how load-bearing they are.

- **9 — `9-trajectory-schema-canonicalization.md`** (C1). Extract the concrete span shapes from OTel GenAI semantic conventions (current, versioned), OpenInference, and the export formats of Langfuse/Phoenix/Weave, and define the minimal normalized trajectory schema that all of them project into — with an explicit, reserved parametric evidence channel so instrumented-model spans drop in without a schema break. Deliverable: a schema spec plus a coverage matrix (which source populates which field). Gates the A ADR.
- **10 — `10-causal-attribution-methods.md`** (C3). Deep dive on the statistics of ablation/counterfactual replay: how many replays for a given confidence on a stochastic suffix, Monte-Carlo Shapley over steps with uncertainty and "insufficient evidence" outcomes, and how to construct a planted-cause synthetic benchmark plus reuse Who&When traces so explanations are falsifiable. Gates the B ADR. **Strong ChatGPT deep-research candidate** (method survey: AgentSHAP, Causal Agent Replay, CausalFlow, context-attribution).
- **11 — `11-probe-and-latent-monitor-science.md`** (C4). Survey the probe/latent-monitor literature: which probes exist (refusal direction, deception/honesty, sycophancy, uncertainty/confidence), their measured validity and false-positive behavior, reproducibility, layer/architecture dependence, and licensing of any published probe weights. Determines what xai can ship as calibrated vs experimental. **Strong ChatGPT deep-research candidate** (fast-moving academic area).
- **12 — `12-otel-propagation-and-transport.md`** (C5). How `traceparent` propagates across the agent↔server boundary through an OpenAI-compatible call (header pass-through reality across LangGraph/CrewAI/custom loops and across vLLM/Ollama), whether the server can attach a child span to the agent's trace, and the one-OTLP-emitter + per-backend-flavour (otel/logfire/langfuse) adapter shape. Gates the C5 transport decision.
- **13 — `13-regulatory-evidence-requirements.md`** (C6). What the EU AI Act Art. 12/14/86 (and AAS-1 draft auditability) concretely require as *evidence* — what fields an explanation packet must carry for logging, human oversight, and right-to-explanation — expressed as templates, not certification claims. **ChatGPT deep-research candidate**.
- **14 — `14-competitive-positioning-refresh.md`** (C7). Re-check that the "why" cell is still empty: watch observability vendors for a bolt-on causal feature, eval vendors for "root cause" prose, and any new agent-attribution entrant; estimate the window (prior read: ~12-18 months). Light, recurring.
- **15 — `15-data-access-and-export.md`** (C7, C1). The practical reality of getting traces out of Langfuse (OSS, easy), Phoenix (OTLP), and LangSmith (bulk export), and the OTel-collector-tee path that bypasses vendors entirely; plus the frictions (schema instability, semantic unevenness, redaction). Partly resolved in exploration; needs a concrete verified write-up.

## Spikes — assumption validation

Spikes are small runnable harnesses that prove a load-bearing assumption before design commits. Each lives under the source repo's gitignored `./tmp/`; findings are written to `xai/impl/learnings/`. They are ordered so the riskiest, most novel assumption (server-side parametric instrumentation) is validated early rather than assumed.

- **S1 — Trace ingestion → trajectory dataframe** (validates C1, gates A). Ingest one real agent run from at least two sources (a Langfuse export and raw OTLP / OpenInference) and normalize both into the candidate trajectory schema, asserting the same logical events land in the same fields. Success: one run, two sources, one dataframe, fields aligned.
- **S2 — Context ablation replay** (validates C3, gates B). On a small real agent, remove one retrieved document / one memory item, rerun the stochastic suffix N times, and report the outcome flip-rate with a confidence interval. Success: a measurable, reproducible flip-rate delta with stated uncertainty on a planted cause.
- **S3 — vLLM/SGLang parametric span** (validates C4+C5, the load-bearing feasibility). A load-time forward-hook plugin on a small model served by vLLM (or SGLang) that emits, per generation step, logit entropy and one linear-probe scalar into an OTel span, correlated to the agent's trace via `traceparent`. Success: the agent trace and the internal-state span share a trace ID, with per-step scalars attached, and the probe hook is a plugin — no engine fork. This is the make-or-break spike for F.
- **S4 — llama.cpp/Ollama internal signal** (validates C4 on the harder engine tier). Attempt to extract a logit-derived uncertainty (and, if feasible, a residual-stream reading via a ggml callback) from a model served by Ollama/llama.cpp. Success: at minimum the logit-uncertainty channel emitted; documented ceiling on what the C++/GGML tier can expose.
- **S5 — eBPF/CUPTI cost span** (validates the C5 cost channel). Correlate per-request GPU time (via CUPTI or an eBPF/bpftime probe) to a request span, zero-touch. Success: a cost/timing span attributable to a specific request, feeding B's `explain_cost`, with no change to the serving code.
- **S6 — Probe validity sanity check** (validates C4 probe claims, supports stage 11). Take one published probe (e.g. a refusal-direction or uncertainty probe) and confirm it discriminates on a held-out set before any claim that xai can ship it. Success: measured separation, or a documented failure that reclassifies the probe as experimental.

## ChatGPT deep-research candidates

The host has ChatGPT deep-research access and can run stages **10–13** externally, in parallel, and copy the results back for integration — these four are the fast-moving academic surveys plus the regulatory and standards detail, where breadth of current sourcing matters more than repo-grounded verification. Each has a self-contained, copy-paste prompt (project context included, so it is a single paste into ChatGPT) under [`deep-research-prompts/`](./deep-research-prompts/):

- **Stage 10** — causal attribution methods: [`deep-research-prompts/10-causal-attribution.md`](./deep-research-prompts/10-causal-attribution.md) → save result as `10-causal-attribution-methods.md`.
- **Stage 11** — probe/latent-monitor science: [`deep-research-prompts/11-probe-latent-monitors.md`](./deep-research-prompts/11-probe-latent-monitors.md) → save result as `11-probe-and-latent-monitor-science.md`.
- **Stage 12** — OTel propagation & transport: [`deep-research-prompts/12-otel-propagation-transport.md`](./deep-research-prompts/12-otel-propagation-transport.md) → save result as `12-otel-propagation-and-transport.md`. (Partly empirical — a few claims still get confirmed by spike S3 against running code; the prompt says so and asks the model to flag them.)
- **Stage 13** — EU AI Act evidence requirements: [`deep-research-prompts/13-eu-ai-act-evidence.md`](./deep-research-prompts/13-eu-ai-act-evidence.md) → save result as `13-regulatory-evidence-requirements.md`.

Each prompt asks for inline primary-source citations, maturity/cost/licensing per item, and an explicit flag on any claim a runnable spike could verify — so imported output lands as the named stage document with sources intact and validation targets marked, not taken as settled. Stages **9, 14, 15** stay in-house: they depend on reading exact schemas, testing real export paths, and watching the market against running code, not on a literature sweep.

## Sequencing

The intended order of execution, each step gating the next: migrate stages 1–6; write stages 7–8 (the novel C4/C5 core, highest-value to capture while fresh); run spike S3 early (it is the riskiest assumption and reshapes stage 7's claims if it fails); carry out stages 9–12 alongside spikes S1/S2/S4/S5 (schema and attribution are what the first ADRs need); fold in stages 13–15 and spike S6; then move to `adrs/` for the A, B, and F decisions, and only then to `plan/` and `impl/`. Deep-research stages (10–13) can proceed in parallel externally since they do not block the early spikes.

## Open questions carried into the ADR phase

- Does S3 hold — is a load-time forward-hook plugin genuinely sufficient on vLLM/SGLang under continuous batching, or does correct per-request attribution force a heavier integration? This is the single assumption most likely to reshape F.
- Is B's replay-based "why" falsifiable enough on the planted-cause benchmark to differentiate from LLM-judge "root cause" prose, or does the demand risk (a judge substitute may satisfy users) dominate?
- Does the parametric layer's operational cost (running an instrumented inference server) keep F additive-only, so the API-model majority still gets full A/B value without it?
- What is the minimal reserved schema shape in stage 9 that lets instrumented-model spans join without a breaking change later — decided now, in the schema, before any adapter ships.
