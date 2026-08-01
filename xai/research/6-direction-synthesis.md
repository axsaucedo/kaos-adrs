# Stage 6 — Direction synthesis: proposals, phasing, and non-goals

> Migrated from the exploration-phase synthesis (`ethical/xai/tmp/PROPOSALS.md`), updated during migration to record the demotion of Proposal C and to point forward to the parametric-instrumentation layer worked out later in the session. Part of the [research plan](./0-research-plan.md); component **C7 — Positioning & ecosystem**. Synthesizes [stage 1](./1-landscape-observability.md)–[stage 5](./5-ecosystem-lists-gap.md); the internals layer is developed in [stage 7](./7-parametric-enriched-traces.md) and [stage 8](./8-server-instrumentation-feasibility.md). Dated 2026-07-31.

## The landscape in one paragraph

The 2026 observability market (Langfuse, LangSmith, Phoenix, Weave, AgentOps, Helicone) answers **what happened** — traces, spans, costs, judge scores — but nothing answers **why**: no causal attribution of an agent action to context, memory, tools, or prior steps. The eval layer (DeepEval, Ragas, promptfoo, Inspect) is crowded but "scores are not explanations." Classic XAI (SHAP, Captum, InterpretML) is alive but tabular-shaped; mechanistic interp (SAEs, circuit tracing) is research-only; CoT is demonstrably unfaithful (~25% hint-mention rate). The fairness stack (fairlearn, Aequitas, AIF360) never adapted to agents — there is **no "SHAP/fairlearn for agents."** Meanwhile agent-analysis research exploded in 2025-26 (MAST failure taxonomy, Who&When attribution, τ-bench pass^k, Petri/Bloom, causal replay) but remains unpackaged for practitioners. The EU AI Act (GPAI enforcement Aug 2026; high-risk 2027-28; Art. 12 logging, Art. 14 oversight, Art. 86 right-to-explanation) creates pull that no small OSS component serves.

**All four reports independently converge on the same shape: a small, provider-neutral analysis layer OVER traces (OTel GenAI / OpenInference in), producing explanations, attributions, and audit evidence out. Never build another trace store, dashboard, eval runner, or SAE trainer.**

## Proposal A — Trajectory Diagnostics & Evidence Layer ("the practical wedge")

`xai` becomes a **trajectory dataframe + analyzers**: the pandas-of-agent-traces.

- Canonical trajectory schema + adapters: OTel GenAI, OpenInference, Langfuse/Phoenix export, plain JSON. Normalize actors, messages, retrieved evidence, tool calls/results, memory ops, handoffs, outcomes.
- Deterministic trajectory diagnostics: loops, repeated tool failures, ignored observations, invalid arguments, missing verification, premature termination, plan/goal drift checkpoints.
- Claim→evidence attribution: split outputs into claims, link each to retrieved chunks / tool observations, label supported / conflicting / unsupported.
- Failure-taxonomy adapters: executable MAST/AgentError-style classifiers with evidence spans and human correction.
- Sliced metrics — the direct heritage carry-over: success, groundedness, tool errors, escalations, cost, latency sliced by task, model, tool, cohort, language, protected group (today's `imbalance_plot`/`metrics_plot` applied to trajectories instead of dataframe rows).

Fastest to ship, immediately useful with closed models, no causal claims to defend. Risk: closest to what eval vendors could bolt on.

## Proposal B — Agent Decision Attribution ("the why layer")

Own the question no observability vendor answers: **why did the agent do X?**

- `explain_action` / `explain_failure` / `explain_cost` APIs over the trajectory schema.
- Context ablation & counterfactual replay: remove/replace one message, document, memory item, tool description, or step; rerun the stochastic suffix N times; report outcome deltas with confidence intervals — the agent-native analogue of permutation feature importance already in `xai.feature_importance`.
- Monte-Carlo Shapley credit across steps/agents/tools (AgentSHAP, Causal Agent Replay lineage) with explicit uncertainty and "insufficient evidence" outcomes.
- Multi-agent responsibility graph: provenance edges over delegation and handoffs; shared/interacting causes, not single-agent blame.
- Benchmark harness: planted-cause synthetic agents + Who&When traces, so explanations are falsifiable — the key differentiator vs LLM-judge "root cause" prose.

Defensible claim: "given recorded state and declared interventions, we estimate which components materially changed the probability of the observed action, with stated uncertainty." Highest technical differentiation; costs compute (replays) and needs careful causal caveats.

## Proposal C — Agent Decision Audit ("the accountability/heritage play")

> **Status: demoted.** After review, C does not stand as its own phase. Its headline artifact — a group-disparity table — is a commodity `groupby` over hand-annotated protected-attribute columns that real agent traces rarely carry, which makes it an artificial use case on its own. Its genuinely valuable substance (matched counterfactual proxy-swap tests, the per-decision explanation packet) is B's machinery applied to a fairness question. C is therefore retained as a **downstream recipe/application of B**, not a separate milestone. The description below is preserved for that recipe.

The Institute-shaped direction: **fairness-aware accountability for what agents do to people.**

- Decision ledger: `subject/context → proposed action → executed effect`, with model/prompt/policy/tool versions, evidence provenance, guardrail verdicts, delegation chain, human review/override.
- Fairness audit over agent decisions: allocation/quality-of-service disparities across protected & intersectional groups over both final outcomes AND process (extra steps, escalation rate, refusal rate, tool access, latency, human-review rate), with bootstrap CIs and small-sample warnings; matched counterfactual tests (swap protected-attribute proxies, rerun).
- Explanation packet per consequential decision: evidence timeline, decisive observable factors, tested counterfactuals, limitations, review/appeal metadata — Markdown/JSON/HTML export.
- Thin, clearly-caveated EU AI Act mapping (Art. 12/14/86) as templates, not certification.

Strongest identity fit; the counterfactual proxy-swap and explanation packet ride on B. Regulatory tailwind peaks 2026-28. Narrower audience (regulated deployers).

## Proposal D — Modernized classic (baseline, not recommended alone)

Finish the current ROADMAP (pandas compat, multiclass, matplotlib params), keep `xai` as the maintained tabular fairness-analysis toolkit. Honest but ignores the strategic moment; the tabular niche is held by InterpretML/fairlearn.

## Proposal F — Parametric Instrumentation ("the internals layer")

Added after the A/B/C synthesis. When the agent runs on a self-hosted open-weights model, instrument the **inference server** (vLLM/SGLang/…) — not the agent, since the model virtually never runs in-process with the agent — to emit internal-state signals (logit-uncertainty, linear-probe readings, attention/attribution) as trace-correlated OTel spans that A's diagnostics and B's replay consume. This is structurally unavailable to observability vendors (they instrument the agent SDK) and to interpretability labs (they work in-process on single models, not trajectories). Developed in full in [stage 7](./7-parametric-enriched-traces.md) (concept and synergies) and [stage 8](./8-server-instrumentation-feasibility.md) (feasibility, eBPF assessment, engine landscape). F is **additive** — the closed-API majority keeps full A/B value without it.

## Recommendation: one library, phased

These are not competing — they share the same foundation and sequence naturally:

1. **Phase 1 (wedge, ~0.4.x):** Proposal A — trajectory schema + adapters + deterministic diagnostics + sliced metrics. Ship a worked example: one agent trace in, imbalance/disparity/diagnostic plots out. Keeps the existing tabular API alongside.
2. **Phase 2 (differentiator, ~0.5.x):** Proposal B — ablation/counterfactual attribution with uncertainty + planted-cause benchmark. This is the "SHAP moment for agents" if it lands. The fairness recipe (former C) rides on this machinery.
3. **Phase 3 (internals, self-hosted segment):** Proposal F — server-side parametric instrumentation feeding the same schema and replay, for open-weights deployments. Gated on the make-or-break feasibility spike (see the research plan).

Positioning line: **"xai turned dataframes into fairness evidence in 2017; it turns agent trajectories into decision evidence in 2026."**

## Explicit non-goals (from all four reports)

- No trace store, dashboard platform, eval runner, guardrail engine, or agent runtime.
- No SAE/circuit tooling; no "LLM SHAP over prompt tokens."
- Never present CoT/self-explanations or judge rationales as faithful causes — separately-labeled evidence channels only.
- No automatic fairness verdicts; users name the harm, groups, and comparator.
