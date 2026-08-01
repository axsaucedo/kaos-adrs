# Stage 3 — Evaluation, safety auditing & governance landscape (2025–2026)

> Migrated from the exploration-phase research (`ethical/xai/tmp/codex-report-governance.md`, a delegated Codex research run). Part of the [research plan](./0-research-plan.md); component **C6 — Decision audit & governance**. Reads alongside the [direction synthesis](./6-direction-synthesis.md) and is deepened by planned [stage 13](./0-research-plan.md) (regulatory evidence requirements). Research current to 31 July 2026. "Gap" means an opportunity relative to accountable agent decisions, not a claim that the project fails at its stated purpose. Regulatory notes are product research, not legal advice.

## Executive finding

The horizontal eval layer is crowded: mature OSS projects already run datasets, LLM judges, RAG metrics, red teams, CI gates, and agent/tool traces. Runtime guardrail projects can block or rewrite unsafe traffic and expose useful diagnostic logs. The material gap is one layer above both:

> **A vendor-neutral, local-first evidence and explanation layer for consequential agent decisions: reconstruct what happened, measure outcome and process disparities across groups/counterfactuals, show which observable factors changed the decision, and export a reviewable audit record.**

No reviewed project is a credible "SHAP/fairlearn for agents." [LangFair](https://github.com/cvs-health/langfair) is the clearest LLM-native fairness library, but it mainly evaluates outputs through toxicity, stereotype, counterfactual, recommendation, and classification metrics. It does not yet explain multi-step tool-using decisions, attribute harm to steps/policies/tools, or produce a durable governance record. Traditional fairness libraries remain centered on supervised predictions and labelled tabular data.

## Evaluation frameworks

| Tool | Focus and OSS status | Gap for responsible agent governance |
|---|---|---|
| **DeepEval** | Apache-2.0 "pytest for LLMs"; end-to-end and span/trace metrics for RAG, conversations, task completion, plans, tools and arguments; many metrics use an LLM judge. [Source](https://github.com/confident-ai/deepeval) | Excellent test harness, but judge rationales are not causal explanations or audit evidence; its single-output "bias" metric is not a group/counterfactual decision audit, and durable dashboards/operations lead toward Confident AI. |
| **Ragas** | Apache-2.0 Python toolkit for LLM-app metrics, synthetic test generation and feedback loops; still RAG-first, with agent evals listed as "coming soon" in the current repository. [Source](https://github.com/vibrantlabsai/ragas) | Strong for grounding/retrieval quality, weak for end-to-end agent accountability, protected-group outcomes, policy provenance, or compliance evidence. |
| **promptfoo** | MIT, local-first CLI/UI/CI for prompt/model/RAG/agent comparison and automated red teaming; now part of OpenAI but remains multi-provider OSS. [Source](https://github.com/promptfoo) | Produces pass/fail matrices and vulnerability findings, not longitudinal disparity analysis, decision reconstruction, stakeholder explanations, or human-review records. |
| **UK AISI Inspect** | MIT, government-backed composable frontier-model eval framework with datasets, solvers/agents, tools, scorers, multi-agent support, a viewer, and 200+ packaged evals. [Source](https://inspect.aisi.org.uk/) | Best general public-interest harness here, but it evaluates capabilities/behaviour; it is not a deployment governance layer and fairness, affected-person explanations, and compliance dossiers are not its core abstraction. |
| **OpenAI Evals** | MIT framework plus benchmark registry for LLMs/systems; supports custom completion functions and local JSONL event logs, while OpenAI's hosted Evals API/dashboard is a separate current path. [OSS source](https://github.com/openai/evals), [API source](https://platform.openai.com/docs/api-reference/evals) | Benchmark/model oriented; limited first-class representation of arbitrary agent traces, group harms, decision lineage, oversight events, or portable compliance artifacts. |
| **Giskard OSS** | OSS Python testing/evaluation library for LLM agents; earlier v2 supplied automated vulnerability Scan and RAGET test generation, while the current product separates basic OSS capabilities from a broader platform. [Source](https://docs.giskard.ai/), [repository](https://github.com/Giskard-AI/giskard-oss) | Broad quality/security testing, but no distinctive model for procedural fairness across action chains or explanations tied to real-world decisions and controls. |
| **Deepchecks** | The classic ML/data testing package is AGPL-3.0 and supports tabular/NLP checks; the current LLM/agent offering is a platform/client workflow for evaluation and production monitoring. [OSS source](https://github.com/deepchecks/deepchecks), [LLM platform](https://llmdocs.deepchecks.com/docs/what-is-deepchecks) | Strong lifecycle evaluation/monitoring, but the LLM offering is not a small embeddable fairness/explanation primitive; governance depends on platform workflows and automated evaluators rather than portable decision evidence. |

### Shared market gaps

- **Scores are not explanations.** An LLM judge's prose reason explains its score, not why an agent reached a consequential decision.
- **Traces are not audit trails.** Raw spans rarely encode policy version, authority, evidence lineage, affected entity, review/override, retention, or the relationship between intermediate steps and the final outcome.
- **Fairness is usually a content-safety check.** "Bias" often means detecting stereotyped/toxic text, not measuring allocation, quality-of-service, procedural, or intersectional disparities in actions.
- **Reproducibility is underspecified.** Stochastic agents, changing tools/data, and external side effects make exact replay impossible; reviewers need captured state, versions, observable evidence, and bounded counterfactual reruns instead.
- **Framework portability is weak.** Each ecosystem has its own test case/trace schema. A governance library should consume OpenTelemetry/JSON traces and export findings back into existing runners rather than compete with them.

## LLM fairness and bias auditing

### What credibly exists

- **LangFair** is the most relevant OSS package found. It explicitly takes a use-case-level, bring-your-own-prompts, black-box approach and implements toxicity, stereotypes, counterfactual similarity/sentiment, recommendation ranking, and classification disparity metrics, plus adversarial generation. [Repository and metric list](https://github.com/cvs-health/langfair), [paper](https://arxiv.org/abs/2501.03112). **Gap:** mostly prompt/response pairs; it does not model tool trajectories, resource allocation over sessions, procedural fairness, intersectional root-cause attribution, human oversight, or evidence export.
- **Benchmarks and research** are plentiful—e.g. stereotype/toxicity/counterfactual datasets and emerging work on [interactional fairness in multi-agent systems](https://ojs.aaai.org/index.php/AIES/article/view/36563)—but they are fragmented and often measure a base model under synthetic prompts, not a deployed system making contextual decisions.
- **General eval suites** sometimes expose a bias/toxicity judge. This is useful screening, but its construct validity, judge bias, sensitivity to wording, and lack of affected-group outcome data make it insufficient for a defensible fairness audit.

### What happened to the tabular fairness stack

| Project | Current direction | LLM adaptation assessment |
|---|---|---|
| **Fairlearn** | Active, community-driven OSS; assessment/mitigation still assumes measurable outcomes/predictions plus sensitive features, with reductions and post-processing for classification/regression. It explicitly frames fairness as sociotechnical harm. [Source](https://fairlearn.org/) | **Not LLM-native.** Its `MetricFrame`-style group analysis remains valuable after agent outcomes are normalized into rows, but it does not ingest conversations/traces or explain agent procedures. |
| **Aequitas** | Active OSS bias audit and mitigation toolkit; v1 adds Aequitas Flow, still built around labels, scores, categorical sensitive attributes and confusion-matrix disparities for binary classification. [Source](https://github.com/dssg/aequitas) | **No meaningful LLM/agent adaptation found.** Useful downstream when an agent decision can be reduced to a labelled binary outcome. |
| **AIF360** | Maintained OSS collection of dataset/model fairness metrics and pre/in/post-processing mitigation algorithms. [Source](https://github.com/Trusted-AI/AIF360) | **No first-class generative/agent workflow found.** Broad metric research remains reusable, but the core abstractions are datasets and conventional model predictions. |

**Bottom line:** classical group metrics survived, but the missing adapter is conceptual as much as technical: convert a variable-length agent trajectory into auditable **decisions, benefits/burdens, process events, evidence used, and oversight outcomes**, then test disparities with uncertainty and context. Text similarity or sentiment parity alone does not solve this.

## EU AI Act pull

### Timeline as of the research date

- The Act entered force on **1 August 2024**; prohibitions and AI-literacy duties have applied since **2 February 2025**; governance and GPAI obligations since **2 August 2025**; most remaining provisions and Article 50 transparency rules apply from **2 August 2026**. [Commission overview](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai)
- Following the **7 May 2026 political agreement on the AI Omnibus**, the Commission's current implementation page gives **2 December 2027** for Annex III high-risk use cases and **2 August 2028** for high-risk AI embedded in Annex I regulated products. These dates are newer than many static 2024–25 summaries. [Commission timeline](https://digital-strategy.ec.europa.eu/en/faqs/navigating-ai-act)
- GPAI duties already require technical documentation, downstream-provider information, a copyright policy, and a training-content summary; systemic-risk GPAI adds evaluation, risk mitigation, incident reporting, and cybersecurity. Commission enforcement powers and fines begin **2 August 2026** for post-August-2025 GPAI models; pre-existing GPAI models have until **2 August 2027**. [GPAI guidance](https://digital-strategy.ec.europa.eu/en/policies/guidelines-gpai-providers)

### Obligations that create engineering demand

For high-risk systems, the Commission summarizes requirements as risk management, data quality, technical documentation, **activity logging for traceability**, deployer information/transparency, human oversight, accuracy, robustness and cybersecurity, with provider post-market monitoring. [Official overview](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai). Article 12 requires logging capabilities appropriate to the system's purpose; Articles 13–14 require interpretable output/instructions and effective oversight; Article 86 establishes a scoped right to a clear, meaningful explanation of the AI system's role and the main elements of certain consequential individual decisions. [Official Act text](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32024R1689).

For agent deployments, the tooling gap is practical:

1. **Classification and scoping:** map an agent/use case/operator role to applicable duties and record the assessment—not merely add an "EU compliant" label.
2. **Decision-centric logging:** capture the final action and its effect, model/prompt/policy/tool/data versions, evidence references, guardrail verdicts, delegation chain, side effects, and responsible human—not only token spans.
3. **Evidence minimisation:** retain enough to reconstruct relevant events while redacting personal/secrets data and enforcing retention/access policy. Full prompt capture can itself create GDPR/security risk.
4. **Human oversight proof:** record escalation triggers, information shown to the reviewer, intervention/override/stop authority, response time, and final disposition.
5. **Meaningful explanations:** generate audience-specific accounts from observable evidence and tested counterfactuals. Hidden chain-of-thought should neither be required nor presented as a faithful causal record.
6. **Continuous monitoring:** detect drift in outcomes, failure modes and group disparities across model, prompt, tool, or policy releases, with reproducible snapshots and signed/versioned reports.

Existing observability products collect spans; eval tools score test cases; GRC products manage controls. Few small OSS components transform all three into a portable, reviewable **decision evidence bundle**.

## Guardrails and runtime safety

| Tool | Runtime role and OSS status | Explanation/audit-trail reality |
|---|---|---|
| **Guardrails AI** | Apache-2.0 framework and validator hub for validating, fixing, re-asking, filtering, or rejecting structured/text outputs. [Repository](https://github.com/guardrails-ai/guardrails) | It has useful per-call history: raw/validated outputs, iterations, validator names, pass/fail results, error messages, fixes and error spans. [Logs](https://guardrailsai.com/guardrails/docs/concepts/logs). This explains **which validator failed**, not why the upstream agent decided as it did; history is an execution diagnostic, not a governance-grade cross-system audit trail. |
| **NVIDIA NeMo Guardrails** | Apache-2.0 programmable input/output/retrieval/dialog/tool rails with content safety, topic, jailbreak and other controls. [Repository](https://github.com/NVIDIA-NeMo/Guardrails) | Strongest diagnostics of the three: activated rails, stopping rail, LLM calls, internal events, stats, and OpenTelemetry traces; content capture is opt-in because of privacy risk. [Diagnostics](https://docs.nvidia.com/nemo-platform/documentation/guardrail-models/core-concepts/running-inference), [tracing](https://docs.nvidia.com/nemo/guardrails/latest/observability/tracing/content-capture). It can explain rail execution, but not provide validated causal explanations, fairness analysis, oversight evidence, or an affected-person narrative. |
| **Meta Llama Guard** | Open-weight safety classifier under Meta's Llama terms (not OSI-style OSS): labels prompt/response `safe` or `unsafe` and returns violated hazard categories; Llama Guard 3 covers 14 categories and tool-call related abuse. [Model card](https://huggingface.co/meta-llama/Llama-Guard-3-8B) | Category labels and unsafe probability are reasons at taxonomy level, not explanations of an agent decision. No persistent audit trail, policy lifecycle, human-review record, group fairness analysis, or multi-step attribution is built in. |

Guardrail logs are valuable **inputs** to an audit record. They should not be conflated with explanations: a rail's allow/block reason describes a safety policy decision, while the agent's business decision may depend on retrieval, tools, rules, external state and human interventions.

## White space for `xai`

### Recommended ownership: Agent Decision Audit (small OSS core)

Build a Python library that accepts completed agent traces plus a small semantic mapping, then emits three things:

1. **Decision ledger:** a normalized, appendable schema for `subject/context → proposed action → executed effect`, with trace references, model/prompt/policy/tool/data versions, evidence provenance, guardrail outcomes, side effects, and human review/override. Accept JSON and OpenTelemetry; adapters for Inspect/DeepEval/promptfoo can follow.
2. **Fairness audit:** define benefits/burdens and protected/intersectional groups; compute selection/error/quality-of-service disparities, uncertainty intervals, minimum-support warnings, repeated-measures handling, and matched counterfactual tests over both final outcomes and process measures (extra steps, escalation rate, latency, refusal, tool access, human review).
3. **Explanation packet:** for one decision, produce a deterministic evidence graph/timeline, decisive observable rules/evidence, tested "what changed the outcome?" counterfactuals, uncertainty/limitations, and review/appeal metadata. Export Markdown/JSON/HTML. Never claim raw chain-of-thought is faithful causality.

### The differentiator

**Explain outcomes and procedures, not model internals.** SHAP-style token attribution is rarely the right unit for agents. The useful units are observable interventions: remove/change a retrieved fact, tool result, policy rule, protected-attribute proxy, reviewer action, or delegation step; rerun safely in a sandbox; measure whether the final action or burden changes. Combine this with classical group fairness metrics and provenance.

This is credible territory for the Institute's heritage:

- extends tabular bias auditing from one prediction row to one **decision trajectory**;
- treats fairness as contextual harm, not a universal "bias score";
- makes transparency actionable for developers, reviewers and affected people;
- complements eval and guardrail frameworks instead of rebuilding them;
- can remain local-first, framework-neutral and useful without a hosted platform.

### Minimal first release

- `DecisionRecord` JSON schema plus OpenTelemetry/JSON trace importer.
- User-supplied outcome/group mapping; no automatic inference of protected traits.
- Group disparity table with bootstrap confidence intervals and small-sample warnings.
- Paired counterfactual runner with explicit mutation log and stochastic repeat support.
- Per-decision evidence timeline and Markdown/JSON audit export.
- A worked hiring/benefits-style synthetic agent example showing final-outcome and process disparity.

### Explicit non-goals

- Do not build another general eval runner, tracing backend, guardrail engine, benchmark registry, or EU AI Act "certification" product.
- Do not expose or depend on private chain-of-thought.
- Do not promise an automatic fairness verdict; require users to name the harm, groups, comparator, outcome and acceptable trade-off.
- Do not begin with every regulation/framework. Provide stable evidence primitives and a thin, clearly caveated EU AI Act mapping template later.

### Strategic verdict

The best revitalization is **not "XAI for LLM text."** It is **explainable, fairness-aware accountability for agent decisions**: a narrow OSS bridge from traces to defensible evidence. That space is materially less occupied than generic evals or runtime safety and is a direct continuation of `xai`'s responsible-ML identity. During synthesis this direction (originally "Proposal C") was demoted from a standalone phase to a downstream recipe of the attribution layer; see [stage 6](./6-direction-synthesis.md) for the reasoning.
