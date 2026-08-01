# Stage 2 — Interpretability & explainability landscape (2025–2026)

> Migrated from the exploration-phase research (`ethical/xai/tmp/codex-report-interpretability.md`, a delegated Codex research run). Part of the [research plan](./0-research-plan.md); components **C3 — Causal attribution** and **C4 — Parametric instrumentation**. Reads alongside [stage 1](./1-landscape-observability.md), [stage 4](./4-landscape-agentic.md), and the [direction synthesis](./6-direction-synthesis.md). Research date 2026-07-31. "Practicality" means usable by an ordinary ML/LLM engineering team, not merely reproducible by an interpretability researcher.

## Bottom line

- Classic XAI has not disappeared; it has become the stable tabular/predictive-model layer. SHAP, Captum, and InterpretML are active, LIME's original package is effectively legacy, and Alibi Explain is stale and no longer conventionally open-source.
- The field has split. White-box LLM interpretability—activation patching, sparse autoencoders (SAEs), transcoders, and circuit tracing—is a fast-moving research discipline. Black-box production "explainability" is mostly evidence provenance, controlled perturbations, execution traces, trajectory evaluation, and review workflows.
- No method currently gives a complete, reliable natural-language answer to "why did this LLM/agent do that?" Self-explanations and chain-of-thought (CoT) are observations that may help, not faithful ground truth.
- The strongest revitalization direction is not another attribution algorithm. It is a provider-neutral **explanation layer over LLM/agent traces**: normalize traces, connect claims to evidence, compare counterfactual runs, diagnose trajectory failures, slice metrics, and emit auditable explanation artifacts.

## Classic XAI tooling

| Tool | State in 2026 | One-line use and practicality |
|---|---|---|
| **SHAP** | **Actively maintained**; v0.52.0 was released in May 2026 and included a native-extension/build rewrite. ([releases](https://github.com/shap/shap/releases), [release notes](https://shap.readthedocs.io/en/stable/release_notes.html)) | Still the default general-purpose vocabulary and implementation for local/global feature contribution in tabular ML. **Practical: high** for trees/tabular models; expensive or semantically awkward for long generative inputs, and contribution is not causation. |
| **LIME** | **Legacy/original project largely dormant**: PyPI's latest release is 0.2.0.1 from June 2020 and the original repository's last listed commits are from July 2021. ([PyPI](https://pypi.org/project/lime/), [commits](https://github.com/marcotcr/lime/commits/master/)) | The local-surrogate idea remains widely reimplemented, including inside newer packages, but the original package should not be a strategic dependency. **Practical: medium as a method, low as a base library**. |
| **Captum** | **Actively maintained**; v0.9.0 (April 2026) added remote LLM attribution through vLLM and multimodal attribution primitives, while retiring Captum Insights. ([release](https://github.com/pytorch/captum/releases)) | Strong PyTorch toolbox for gradients, perturbations, concepts, influence, and prompt attribution. **Practical: high** when the team controls a PyTorch/open-weight model; low for closed APIs. |
| **Alibi Explain** | **Stalled/source-available**: latest release v0.9.6 is from April 2024; v0.9.5 changed from Apache-2.0 to Business Source License 1.1. ([releases](https://github.com/SeldonIO/alibi/releases), [repository](https://github.com/SeldonIO/alibi)) | Broad conventional-model collection—anchors, counterfactuals, integrated gradients, SHAP, ALE. **Practical: medium for existing users, poor foundation for new OSS work** because of release cadence and licensing. |
| **InterpretML** | **Actively maintained**; v0.7.8 shipped in March 2026. Its distinctive value remains glass-box Explainable Boosting Machines (EBMs), alongside LIME/SHAP-style black-box explainers. ([releases](https://github.com/interpretml/interpret/releases), [docs](https://interpret.ml/docs/index.html)) | Excellent tabular glass-box option and conventional-model UI/API. **Practical: high for tabular decisions, low relevance to LLM internals or agent trajectories**. |

**Has the field moved on?** It has expanded, not replaced these tools. Feature attribution still answers "which input columns influenced this prediction?" for tabular systems. Modern LLM applications need different units—tokens, retrieved passages, messages, tools, steps, policies, and latent features—and different evidence. Classic post-hoc scores remain useful diagnostics, but should not be presented as causal or complete explanations; even InterpretML's documentation warns that perturbation-based black-box explanations are approximate and may be inaccurate. ([InterpretML guidance](https://interpret.ml/docs/index.html))

## LLM interpretability

### White-box / mechanistic methods

| Technique or tool | One-line assessment |
|---|---|
| **TransformerLens** | Hooks, caches, edits, ablations, and activation patching across 50+ open model architectures. **Practical for specialist debugging and teaching; research-oriented for production teams** because it requires model weights, architectural knowledge, and experiment design. ([project](https://github.com/TransformerLensOrg/TransformerLens)) |
| **SAELens** | Trains and analyzes sparse autoencoders over PyTorch/Hugging Face/TransformerLens activations; very active, with a large pretrained-SAE ecosystem. **Practical for interpretability researchers; research-only for most application teams** because feature quality, labeling, coverage, and causal validation remain open problems. ([project](https://github.com/decoderesearch/SAELens)) |
| **Anthropic circuit tracing / attribution graphs** | Replaces parts of a model with interpretable transcoders, builds prompt-specific feature graphs, then tests hypotheses by intervention. The open tooling supports selected open-weight models and Neuronpedia visualization. **Research-only/early**: graphs are partial proxies, training transcoders has material upfront cost, attention circuits and reconstruction error remain limitations, and human analysis is substantial. ([methods and limitations](https://transformer-circuits.pub/2025/attribution-graphs/methods.html), [open-source release](https://www.anthropic.com/research/open-source-circuit-tracing)) |
| **Neuronpedia** | Hosted/open platform and API for browsing features, activations, steering vectors, and attribution graphs. **Practical for exploration, demos, and sharing research; not a general production explainer**. ([site](https://www.neuronpedia.org/), [docs](https://docs.neuronpedia.org/)) |
| **Goodfire Ember** | Commercial model-design environment built around latent features, inspection, steering, training, and monitoring; Goodfire separately released SAEs for Llama 3.1 8B and 3.3 70B. **Potentially practitioner-facing but proprietary/partner-led; the open SAEs are research assets, not the Ember platform**. ([Ember description](https://www.goodfire.ai/blog/announcing-our-50m-series-a), [open SAEs](https://www.goodfire.ai/blog/sae-open-source-announcement), [2026 platform direction](https://www.goodfire.ai/blog/our-series-b)) |

Mechanistic interpretability is most credible when a descriptive feature or circuit is followed by a causal intervention—ablation, activation patching, or steering—and the predicted output change occurs. Attractive labels and visual graphs alone are hypotheses, not explanations.

### Input/output and black-box methods

| Technique or tool | One-line assessment |
|---|---|
| **Inseq** | A maintained PyTorch/Hugging Face toolkit for token-level feature attribution in sequence generation. **Practical: medium** for open local models and controlled analyses; less useful for proprietary endpoints and long agent runs. ([docs](https://inseq.org/en/latest/), [quick start](https://inseq.org/en/latest/examples/quickstart.html)) |
| **Captum LLM attribution** | Applies perturbation/gradient methods to prompt features and generated outputs, now including remote vLLM support. **Practical: medium-high** for open/self-hosted models; computational cost grows rapidly with prompt features and target tokens. ([releases](https://github.com/pytorch/captum/releases)) |
| **Attention maps** | Cheap and visually intuitive token-to-token diagnostics. **Practical: high as a debugging view, low as an explanation**: attention weight is not by itself a causal contribution, and head/layer aggregation choices can change the story. |
| **Prompt/context ablation and counterfactual replay** | Remove, replace, reorder, or mask instructions, messages, retrieved passages, tool descriptions, and exemplars; measure output or tool-choice changes over repeated runs. **Practical: high and provider-neutral**; stronger evidence than a heatmap, though stochasticity and correlated context require replication and confidence intervals. |
| **Model self-explanation / generated rationale** | Ask the model to explain, cite, critique, or identify decisive evidence. **Practical: high for UX and hypothesis generation, low as faithful evidence**. Research finds plausible explanations can misrepresent the actual decision process, so perturbation-based faithfulness tests are needed. ([2025 study](https://link.springer.com/article/10.1007/s10994-025-06838-6), [counterfactual faithfulness metric](https://deepmind.google/research/publications/78755/)) |

## Agent trajectories and chain-of-thought

There is **no mature equivalent of SHAP for "why this tool call?"**. An agent decision depends on hidden model state plus visible prompt, conversation, retrieved context, tool schemas/results, orchestration code, memory, randomness, and external state. Current work is therefore trajectory-centric:

| Work | One-line assessment |
|---|---|
| **AgentEvals / LangSmith trajectory evaluation** | Open tooling can compare exact, unordered, subset, or superset tool-call paths, or ask an LLM judge to review a complete trajectory. **Practical now**, especially deterministic checks for policy-critical workflows; judge results remain probabilistic. ([guide](https://docs.langchain.com/langsmith/trajectory-evals)) |
| **Agent Trajectory Explorer** | Visualizes, annotates, and demonstrates agent behavior. **Useful research/design prototype**, not a causal decision explainer. ([AAAI 2025](https://ojs.aaai.org/index.php/AAAI/article/view/35350)) |
| **AgentDiagnose** | Open EMNLP 2025 toolkit scoring decomposition, observation reading, backtracking/exploration, self-verification, and answer quality with trajectory visualizations. **Promising practitioner prototype**, but its competency scores diagnose behavior rather than reveal internal causes. ([paper/tool](https://aclanthology.org/2025.emnlp-demos.15/)) |
| **Planner introspection / "why I chose this tool"** | A generated decision rationale can improve reviewability and catch obvious mistakes. **Practical as an auditable claim, not trustworthy introspection**; validate against actions, available evidence, and counterfactual replays. |
| **CoT monitoring** | OpenAI found CoT monitors detected reward hacking better than action-only monitors, so CoT can be a useful safety signal. **Practical as one monitor, unsafe as the sole control**. ([OpenAI, March 2025](https://openai.com/index/chain-of-thought-monitoring/)) |
| **CoT faithfulness** | Anthropic found Claude 3.7 Sonnet mentioned supplied hints only 25% of the time on average and DeepSeek R1 39%; OpenAI's later monitorability work likewise treats monitorability as fragile across training and scaling. **Research conclusion: monitor, but do not equate CoT with internal reasoning**. ([Anthropic](https://www.anthropic.com/research/reasoning-models-dont-say-think), [OpenAI](https://openai.com/index/evaluating-chain-of-thought-monitorability/)) |

The practical research frontier is combining: (1) structured traces, (2) deterministic trajectory/policy checks, (3) LLM or human semantic review, (4) controlled environment interventions, and eventually (5) white-box latent monitors for models whose internals are accessible. That fifth channel — latent monitors on accessible internals — is the seam the parametric-instrumentation work in [stage 7](./7-parametric-enriched-traces.md) and [stage 8](./8-server-instrumentation-feasibility.md) picks up.

## What production explainability means in 2026

Production teams mostly need to answer **what happened, what evidence supported it, whether it was allowed/correct, and how behavior changes under intervention**—not decode every neuron.

1. **Evidence provenance and grounding.** Store retrieved chunks and versions; link claims to exact sources; score citation coverage/support; expose abstention when evidence is missing. Grounded APIs now return claim citations as first-class response metadata. ([Vertex AI response schema](https://cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/GenerateContentResponse))
2. **End-to-end trace review.** Capture prompts, model calls, retrieval, tool arguments/results, retries, state transitions, latency, tokens, cost, policy decisions, and final output. OpenTelemetry's GenAI conventions model agent, chat, and tool spans; Phoenix provides an OSS trace/eval/replay workflow. ([OpenTelemetry](https://opentelemetry.io/blog/2026/genai-observability/), [Phoenix](https://arize.com/docs/phoenix/))
3. **Evaluation attached to traces.** Apply code checks, reference trajectories, LLM judges, and human labels to complete runs and individual spans. Preserve the judge rubric, model/version, score, and rationale; the rationale explains the grade, not the system's true cause. ([LangSmith trajectory evals](https://docs.langchain.com/langsmith/trajectory-evals), [Phoenix evaluation](https://arize.com/docs/phoenix/))
4. **Counterfactual replay.** Replay the same task with one controlled change—source removed, tool unavailable, permission changed, prompt revised, model swapped—and report changes in answer, action, safety, cost, and latency. This is the most accessible causal evidence for closed models.
5. **Sampling and human review.** Surface failures, low-confidence cases, policy violations, novel tool paths, loops, and high-impact actions for expert review. Human annotations become regression cases and calibration data, not merely dashboard comments.
6. **Attribution at the application layer.** In practice "attribution" often means answer-to-source, action-to-tool-result, metric-to-trace-span, or failure-to-component. Internal token/feature attribution is optional and should be clearly separated from this operational provenance.

## OSS opportunities for EthicalML/xai

### Highest-value package direction

Build a small, provider-neutral **agent explanation and evaluation layer**, preferably on OpenTelemetry/OpenInference-shaped traces rather than a new tracing backend:

1. **Canonical episode schema and adapters** — normalize messages, retrieved evidence, tool calls/results, state changes, policies, evaluator feedback, and final outputs from common frameworks.
2. **Evidence/claim attribution** — split outputs into claims; connect each claim to retrieved chunks and tool observations; label supported, conflicting, unsupported, or uncited; preserve immutable source IDs.
3. **Trajectory diagnostics** — deterministic detectors for loops, repeated failures, ignored observations, unnecessary tools, invalid arguments, missing verification, policy-order violations, and premature termination; add an optional rubric-based judge.
4. **Counterfactual explanation harness** — declarative ablations over messages, documents, tool availability/descriptions/results, memory, and policy; repeated trials; effect sizes and uncertainty instead of a single anecdotal rerun.
5. **Sliced metrics, reusing xai's heritage** — success, groundedness, citation support, tool errors, interventions, cost, and latency sliced by task, model, tool, user cohort, language, and sensitive group. This is a natural bridge from the library's fairness-sliced metrics.
6. **Portable explanation artifact** — one JSON/Markdown bundle containing outcome, evidence, concise trace timeline, policy decisions, counterfactuals, evaluator provenance, limitations, and human annotations.

### Integrate; do not reimplement

- Offer optional adapters to Inseq/Captum for token attribution and to TransformerLens/SAELens/Neuronpedia for open-model research artifacts.
- Export to existing observability systems instead of competing with Phoenix, LangSmith, Langfuse, or generic OpenTelemetry collectors.
- Treat mechanistic features, CoT, self-explanations, attention, judges, and citations as separately labeled evidence channels with explicit limitations.

### Avoid as the core bet

- A new SAE trainer or circuit-discovery framework: active specialist projects already exist, model support is expensive, and scientific validity is unsettled.
- An "LLM SHAP" wrapper over arbitrary prompt tokens: it becomes costly, unstable, and hard to interpret on long conversations and trajectories.
- Self-generated explanations presented as faithful reasoning.
- A dashboard-only product: the durable OSS value is schemas, analyzers, evaluations, and portable artifacts that other UIs can consume.

**Recommended wedge:** start with trace normalization + deterministic trajectory diagnostics + claim/source attribution + sliced reporting. Add counterfactual replay next. Keep mechanistic adapters experimental. This is small enough to ship, useful with both closed and open models, and meaningfully differentiated from classic XAI and raw observability.
