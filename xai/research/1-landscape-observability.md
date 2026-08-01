# Stage 1 — Observability & tracing landscape (2025–2026)

> Migrated from the exploration-phase research (`ethical/xai/tmp/codex-report-observability.md`, a delegated Codex research run). Part of the [research plan](./0-research-plan.md); component **C1 — Trajectory schema & ingestion**. Reads alongside [stage 2](./2-landscape-interpretability.md), [stage 4](./4-landscape-agentic.md), and the [direction synthesis](./6-direction-synthesis.md). Research cut-off 31 July 2026. "Why" below means evidence-backed attribution of an action or outcome, not merely displaying the prompt or reasoning text that preceded it.

## Executive finding

The established products answer **what happened**: they capture nested model calls, prompts, retrievals, tool calls, state, errors, latency, tokens and cost; then add search, replay, annotations and output/trajectory scores. Some UIs call this "why," but the mechanism remains trace inspection or an LLM judge.

They generally do **not** establish that a particular observation, memory item, prompt fragment, agent, tool, or earlier step caused a later decision. They do not routinely test counterfactuals, assign causal credit with uncertainty, expose alternative actions considered, distinguish the decision point from the downstream failure manifestation, or validate explanations against known causal ground truth. This gap is now becoming an explicit research area, but the implementations are young and fragmented.

## Tool landscape

| Tool | What it does / source status | Crucial gap |
|---|---|---|
| **Langfuse** | Broad OSS/open-core LLM engineering platform: traces and agent graphs, sessions, token/cost tracking, prompt management, datasets, experiments, human and LLM-judge evaluation. Core is self-hostable and MIT-licensed; some enterprise controls are commercial. [Docs](https://langfuse.com/docs/observability/overview) · [licensing](https://langfuse.com/pricing-self-host) | Excellent trace reconstruction and scoring, but no native causal attribution of a chosen action to evidence or prior steps; an agent graph is an execution visualization, not a causal graph. |
| **LangSmith** | Proprietary LangChain platform for framework-agnostic traces, debugging, datasets, offline/online evaluation, monitoring, annotation and agent deployment. Self-hosting is licensed/enterprise-oriented; LangChain states LangSmith is not open source. [Tracing](https://docs.langchain.com/langsmith/observability-quickstart) · [status](https://docs.langchain.com/langsmith/faq) | Deep LangGraph integration and trace analysis still explain failures through recorded inputs/outputs, feedback or judges—not interventions or defensible decision attribution. Vendor/schema dependence also limits an OSS extension point. |
| **Arize Phoenix** | Self-hostable AI observability/evaluation system with OTLP ingestion, OpenInference instrumentation, traces, evals, datasets, experiments, prompt playground and span replay. Public source is under **Elastic License 2.0**, which forbids offering it as a managed service; it is source-available rather than OSI open source. [Capabilities](https://arize.com/docs/phoenix) · [license](https://raw.githubusercontent.com/Arize-ai/phoenix/main/LICENSE) | Span replay asks whether a modified invocation improves an output, but Phoenix does not automatically identify the causal decision point, decompose interacting causes, or attach calibrated attribution uncertainty. |
| **W&B Weave** | Apache-2.0 toolkit/platform focused on function/LLM call tracing, versioned operations, evaluation datasets and scorers, production monitors and agent integrations. [Repository](https://github.com/wandb/weave) · [trace model](https://docs.wandb.ai/weave/guides/tracking/tracing) | Calls form an execution tree and scorers label quality. Neither structure identifies causal edges or computes which context/tool/step made the action occur; scorer "reasoning" is evaluator text, not causal evidence. |
| **AgentOps** | Agent-focused monitoring SDK/dashboard: sessions, agent/LLM/tool/action events, errors, replay-style inspection, cost/token analytics and framework integrations. SDK/repository is MIT-licensed. [Repository](https://github.com/AgentOps-AI/agentops) · [session model](https://docs.agentops.ai/v1/concepts/sessions) | Agent-native vocabulary improves visibility but attribution remains manual/correlational. A recorded "action" or end-state reason does not establish why it was selected or which upstream step caused failure. |
| **Helicone** | Apache-2.0 self-hostable AI gateway plus request logging, sessions/agent traces, cost/latency/quality analytics, prompt management, playground and routing/fallbacks. [Repository](https://github.com/Helicone/helicone) · [sessions](https://docs.helicone.ai/features/sessions) | Gateway capture is strongest at request boundaries. Session paths reconstruct flow, but internal state, rejected alternatives and causal dependencies require manual instrumentation and are not attributed. |
| **OpenLLMetry / Traceloop** | OpenLLMetry is Apache-2.0 OpenTelemetry instrumentation for model providers, vector stores and frameworks, exportable to standard OTel backends. Traceloop is the commercial observability/evaluation layer above it. [OpenLLMetry](https://github.com/traceloop/openllmetry) · [Traceloop](https://docs.traceloop.com/docs/introduction) | Primarily a collection/transport layer. It standardizes emitted events but supplies no general decision model, counterfactual runner or causal attribution algorithm. Instrumentation coverage also determines what can be explained. |

### Common gaps across the category

- Trace trees encode **temporal/parent-child execution**, not causal influence.
- Evals answer "was it good?"; LLM-judge rationales are uncalibrated hypotheses about "why."
- Replay is usually deterministic debugging or prompt experimentation, not controlled intervention over stochastic trajectories.
- Little support exists for responsibility shared across interacting agents/steps, uncertainty intervals, or ground-truth validation.
- Decision evidence—available context, actually attended/used evidence, constraints, alternatives, commitments and side effects—is not represented consistently.
- Privacy controls often redact the very prompts/state needed for explanation; tools do not quantify the resulting explanation blind spots.
- Cross-vendor export preserves spans better than higher-level agent state, evaluation meaning, provenance and explanations.

## Standards

### OpenTelemetry GenAI semantic conventions

OpenTelemetry now has a dedicated Apache-2.0 [GenAI semantic-conventions repository](https://github.com/open-telemetry/semantic-conventions-genai) covering GenAI clients, agents, tool execution, MCP, metrics and evaluation events. The main conventions have added `invoke_agent`, `execute_tool`, tool definitions/results, reasoning-token data and evaluation events, showing serious ecosystem momentum. [Release history](https://github.com/open-telemetry/semantic-conventions/releases)

**Maturity:** active and increasingly comprehensive, but not settled. The dedicated repository still shows a TODO for its schema URL, many GenAI groups have been evolving with breaking changes, and OTel's convention lifecycle explicitly includes development/alpha/beta/RC before stable. Instrumentations therefore need version pinning and schema translation.

**Adoption:** strongest neutral convergence point. OpenLLMetry emits OTel; Phoenix accepts OTLP; Langfuse, LangSmith and multiple general APM backends support OTel paths. Adoption is uneven at the semantic level: tools can accept OTLP while mapping richer agent fields differently.

**Gap:** the conventions describe observations—messages, calls, tools, agents, results and evaluations. They do not define causal claims, intervention records, candidate actions, explanation confidence, responsibility allocation or causal-ground-truth tests.

### OpenInference

[OpenInference](https://github.com/Arize-ai/openinference) is an Apache-2.0, OTel-compatible set of AI-specific semantic conventions and instrumentations. It has broad Python integrations plus Java and Go support, and can export to any OTel collector, although Phoenix/Arize is its native ecosystem.

**Maturity/adoption:** practically useful and relatively mature as instrumentation—especially for Phoenix, LangChain/LlamaIndex and major provider SDKs—but remains an Arize-led parallel convention rather than the neutral OTel GenAI standard. Coexistence with OpenLLMetry and fast-moving OTel GenAI conventions creates translation and duplicate-span risks.

**Gap:** like OTel GenAI, it standardizes trace facts, not explanations. `AGENT`, `TOOL`, `RETRIEVER` and `LLM` span kinds do not imply causal semantics.

## Does anything answer "why"?

**Mainstream answer: no, not in the causal/attribution sense.** Today's production tools can support a human hypothesis: "the agent called X because this prompt/state appeared immediately before it." They may also ask an LLM to summarize a trace or diagnose a likely root cause. Both are useful, but neither demonstrates that changing/removing the alleged cause changes the action or outcome.

A defensible "why" facility needs at least:

1. A typed trajectory with decisions, observations, state, tools, agents, outcomes and provenance.
2. A declared target: explain an action, final output, policy violation, cost spike or failure.
3. Controlled interventions/replay, with downstream re-execution and stochasticity handled explicitly.
4. Effect estimates versus baselines, interaction-aware credit allocation and confidence intervals.
5. Faithfulness tests and known-cause benchmarks; natural-language summaries only after attribution.

The first credible implementations of this pattern appeared in research prototypes in 2025–2026, not in the established observability platforms.

## Emerging explainability and audit work

- **Who&When / automated failure attribution (ICML 2025):** formalizes identifying the responsible agent and step in failed multi-agent runs; provides an MIT-licensed benchmark and methods. It establishes the task but is not a production observability layer. [Paper](https://proceedings.mlr.press/v267/zhang25cq.html) · [code/data](https://github.com/ag2ai/Agents_Failure_Attribution)
- **AgentSHAP (2025/2026):** black-box Monte Carlo Shapley attribution over available tool subsets, answering which tools contributed to response quality. This is close to classic XAI, but tool-set ablation is expensive and does not localize evidence, state or within-trajectory decisions. [Paper](https://arxiv.org/abs/2512.12597) · [implementation](https://github.com/GenAISHAP/TokenSHAP)
- **Causal Agent Replay (2026):** models a run as a structural causal model, intervenes at steps, reruns the stochastic suffix and reports contrastive/Shapley effects with confidence intervals. This most directly answers "which step caused the failure," but is a new research package validated mainly on synthetic planted-cause cases. [Paper](https://arxiv.org/abs/2606.08275) · [package](https://pypi.org/project/causal-agent-replay/)
- **CausalFlow (2026):** step-level counterfactual intervention, causal-responsibility scores and minimal repairs that flip failed outcomes; promising attribution-to-repair loop, still a research framework rather than an interoperable trace-analysis standard. [Paper](https://arxiv.org/abs/2605.25338)
- **AgentDebugX (July 2026):** open-source detect → attribute → recover → rerun workflow using multi-turn, structure-guided trajectory diagnosis. It improves strict agent-and-step localization but remains model-mediated diagnosis (28.8% strict accuracy on one reported setup), not guaranteed causal identification. [Paper](https://arxiv.org/abs/2607.18754) · [console](https://agentdebugx.com/overview)
- **AgentSight (2025):** open-source eBPF boundary tracing for code-independent system-level visibility, including loops, prompt injection and multi-agent bottlenecks. Valuable for tamper resistance and hidden effects, but observes stable system boundaries rather than explaining internal decisions. [Paper/project](https://arxiv.org/abs/2508.02736)
- **Auditable Agents (2026):** frames auditability as action recoverability, lifecycle coverage, policy checkability, responsibility attribution and evidence integrity; emphasizes tamper-evident records and pre-execution mediation. This is governance/audit architecture, complementary to causal XAI. [Paper](https://arxiv.org/abs/2604.05485)
- **AAS-1 v0.1 (May 2026):** early proposed agent auditability standard. Relevant signal, but too new to treat as established or broadly adopted. [Specification](https://aas-1.org/)

## White space for a focused OSS library

### Best-owned niche: attribution over traces, not another trace store

Build a small, backend-neutral Python library that consumes OTel GenAI/OpenInference traces and produces **testable decision-attribution artifacts**. Do not compete with Langfuse/Phoenix on ingestion, dashboards, prompt management or generic evals.

Core ownership could be:

- **Canonical trajectory graph:** normalize agents, decisions, candidate/selected actions, observations, memory/retrieval evidence, tools, side effects and outcomes from multiple trace schemas; retain provenance and missing-data flags.
- **Attribution API:** `explain_action`, `explain_failure` and `explain_cost`, with simple ablation first and optional counterfactual replay/Monte Carlo Shapley for interactions.
- **Adapters, not infrastructure:** import/export for OTLP JSON, OpenInference, Langfuse and Phoenix; return scores/annotations that existing UIs can display.
- **Uncertainty and faithfulness by default:** effect sizes, confidence intervals, replay counts, assumptions, sensitivity to seed/model and explicit "insufficient evidence."
- **Evidence slices:** extend xai's original fairness-slicing instinct to trajectories—compare attribution/failure rates by user cohort, task type, tool, agent role, language or protected group without claiming causality from group differences.
- **Audit bundle:** compact, redaction-aware record of target decision, evidence, interventions, outputs, policy checks and hashes; separate observed fact, inferred attribution and model-generated narrative.
- **Benchmark harness:** planted-cause synthetic agents plus Who&When-style traces to measure localization, calibration, stability and cost. This is essential because plausible explanations are easy to generate and hard to falsify.

### What is genuinely defensible

The strongest claim is not "we reveal the model's true thoughts." It is: **given recorded agent state and declared interventions, we estimate which components materially changed the probability of an observed action or outcome, with stated uncertainty and coverage limits.** That is narrower, testable and differentiated.

### Risks / boundaries

- Counterfactual replay can be costly and invalid when external state cannot be restored.
- Removing a tool/context item changes the policy's input distribution; causal assumptions must be surfaced.
- Hidden provider reasoning and redacted context cap identifiability.
- LLM-generated diagnoses should be treated as hypotheses or presentation, never as the attribution ground truth.
- "Responsibility" is partly normative; technical causal contribution should remain distinct from organizational/legal accountability.

## Recommendation for EthicalML/xai

Prototype an **`xai.agents` attribution layer** with three deliberately small pieces:

1. A typed trajectory model plus OTel GenAI/OpenInference adapters.
2. Step/evidence/tool ablation with outcome-delta estimates and confidence intervals.
3. A static HTML/JSON explanation report that clearly separates facts, interventions, effects and caveats.

Validate it on a planted-cause mini-benchmark and a subset of Who&When before adding dashboards or broad integrations. This reuses the project's historic strengths—feature importance, sliced metrics, fairness analysis—while moving them from tabular rows/features to trajectories/decisions, in a space the major observability vendors still do not own.
