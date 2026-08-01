# Deep-research prompt — stage 10: causal attribution methods

Copy everything in the fenced block below into ChatGPT deep-research mode as a single prompt. The block is self-contained (it carries the project context). When results come back, save them as `xai/research/10-causal-attribution-methods.md` with the model's inline citations preserved.

```
You are doing deep research to support a specific open-source engineering decision, not a general literature review. Read the context, then do the task.

CONTEXT — the project. `xai` (github.com/EthicalML/xai) is an open-source library from The Institute for Ethical AI & ML. It began in 2017 as a tabular ML explainability and fairness toolkit (permutation feature importance, fairness-sliced metrics). It is being revitalized in 2026 to provide explainability for agentic LLM systems. The design is a small, provider-neutral analysis layer that sits OVER agent traces (ingesting OpenTelemetry GenAI and OpenInference spans), in three layers: (A) a canonical trajectory schema plus deterministic diagnostics and sliced metrics; (B) causal decision attribution via context ablation and counterfactual replay with stated uncertainty; (F) optional parametric instrumentation of self-hosted open-weights inference servers. Firm non-goals: it will NOT build a trace store, dashboard, eval runner, guardrail engine, agent runtime, sparse-autoencoder trainer, or an "LLM SHAP over prompt tokens" wrapper, and it will never present chain-of-thought or LLM-judge rationales as faithful causal ground truth.

CONTEXT — why this matters. Layer B is the differentiator: no observability vendor answers "why did the agent do X?" in a falsifiable, causal sense. The defensible claim we want to support is: "given recorded agent state and declared interventions, we estimate which components materially changed the probability of an observed action or outcome, with stated uncertainty and coverage limits." We need to know exactly which methods exist, how well they work, and what it takes to package them.

TASK. Survey the 2024–2026 literature and tooling on causal and counterfactual attribution for LLM-agent trajectories. Cover, at minimum:
1. Context ablation and counterfactual replay over stochastic agent runs — how many replays are needed for a target confidence on a stochastic suffix, how the stochasticity is handled statistically, and how external/tool/world state is restored (or approximated) for a valid rerun.
2. Step-level and component-level credit assignment — Monte-Carlo Shapley over steps/agents/tools, structural-causal-model formulations (e.g. Causal Agent Replay), AgentSHAP, AgenTracer, CausalFlow, and any newer entrants; how each handles interactions between causes.
3. RAG/context-attribution methods adaptable to sequential decisions (e.g. multi-armed-bandit context attribution) and how well they transfer from single-answer RAG to multi-step tool use.
4. Falsifiability: how to construct a planted-cause synthetic benchmark, and how to reuse the Who&When failure-attribution dataset, so a method's explanations can be scored against known ground truth. What metrics (localization accuracy, calibration, stability, cost) are used.
5. Statistical treatment: confidence intervals on effect sizes, correction for correlated context, and principled "insufficient evidence" outcomes.

For every method or tool, report: the precise claim it can support; its compute cost; its validation status (synthetic-only vs validated on real deployed agents); and its licensing/availability (paper only, OSS repo + license, or closed). Distinguish research-only, prototype, and production-ready.

OUTPUT. Structured markdown with inline citations to primary sources (papers, official docs, repositories) at each claim. Prefer 2024–2026 sources; note where a date is load-bearing. Explicitly flag any claim that a small runnable spike could verify, so we validate rather than trust it. End with the open problems and design decisions this leaves for a provider-neutral attribution library (replay budget, state restoration, benchmark design, how to differentiate from LLM-judge "root cause" prose).
```
