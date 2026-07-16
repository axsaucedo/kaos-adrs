# KAOS-E3 — Evals tooling landscape

This document surveys the LLM/agent evaluation tooling landscape as of mid-2026, assessed against the needs of a KAOS eval capability: offline dataset-driven eval of deployed agents, an evaluator library including LLM-as-judge, trajectory/tool-call evaluation, results storage/reporting, and eventually online trace-based eval. KAOS context: runtime is Pydantic AI (Python), observability is OpenTelemetry-first, everything is self-hosted on Kubernetes via CRDs and an operator, and the established pattern for adopted engines is an OSS library embedded in a KAOS-owned central service (as done with Mem0 for memory).

Each tool is assessed on the same axes: (a) evaluation model, (b) evaluator library incl. LLM-as-judge, (c) dataset handling, (d) OpenTelemetry/tracing integration, (e) Pydantic AI compatibility, (f) deployment shape, (g) Kubernetes/self-hosting story, (h) license and maturity, (i) how it would embed in a KAOS-owned service or Job.

## Scope and method

- Claims below were checked against each tool's own documentation or GitHub repository (2025-2026 state), with sources linked inline; star counts and cadence are approximate as of July 2026.

- "Trajectory eval" means evaluating the intermediate steps of an agent run (tool calls, spans, multi-turn state), as opposed to end-to-end input/output scoring only.

- "Deployment shape" distinguishes three archetypes that matter for KAOS: pure library (embeddable in a KAOS-owned service or Job), self-hostable OSS platform (deployable next to the operator via Helm), and SaaS/commercial platform (self-hosting gated behind enterprise licensing, if available at all).

- This is a survey, not a selection — no recommendation is made here; that is a later stage.

## Pydantic Evals (pydantic-evals)

- **Evaluation model**: offline, code-first experiments — you define [Datasets of Cases and run them against a task function](https://pydantic.dev/docs/ai/evals/evals/), producing an `EvaluationReport`; the same `Evaluator` classes are reusable for [online evals on production traffic via Logfire](https://pydantic.dev/articles/online-evals-pydantic-logfire). Trajectory evaluation is supported by evaluating over the captured span tree of a run, not just final output.
- **Evaluators / LLM-as-judge**: [built-in evaluators](https://ai.pydantic.dev/evals/evaluators/built-in/) include `LLMJudge` (natural-language rubrics, per-case or dataset-wide), `EqualsExpected`, `Contains`, `IsInstance`, `MaxDuration`, span-based checks, plus arbitrary custom Python evaluators returning scores/labels/assertions.
- **Datasets**: `Dataset`/`Case` defined in Python or serialized to YAML/JSON with generated JSON Schema for editor support; datasets carry dataset-level and case-level evaluators ([quick start](https://ai.pydantic.dev/evals/quick-start/)).
- **OTel**: every experiment [emits OpenTelemetry traces](https://pydantic.dev/docs/ai/evals/how-to/logfire-integration/) (experiment span, case spans, task spans, evaluator spans) to any OTel backend; Logfire is optional sugar, not required.
- **Pydantic AI fit**: same authors, same repo family — the task under eval is naturally a Pydantic AI agent; zero-friction alignment with the KAOS runtime.
- **Deployment shape**: pure Python library ([pydantic-evals on PyPI](https://pypi.org/project/pydantic-evals/)); no server component. Results storage/reporting UI is delegated to whatever OTel/trace backend you point it at.
- **Kubernetes fit**: trivial — runs anywhere Python runs; a K8s Job or a KAOS-owned service can invoke it directly.
- **License / maturity**: MIT, part of the pydantic-ai monorepo (~15k+ stars), backed by Pydantic (the company), fast release cadence; younger than DeepEval/Ragas as an evals library specifically.
- **KAOS embed**: cleanest library-embed candidate — a KAOS eval service or Job imports it, runs datasets against deployed agents, and ships result spans through the existing OTel pipeline; storage/reporting would need to be built or paired with a trace backend.

## DeepEval (Confident AI)

- **Evaluation model**: offline pytest-style unit tests and bulk evaluation, plus component-level (span-level) evals over traces; [DeepEval 4.0 adds agent-native workflows](https://github.com/confident-ai/deepeval/releases) for end-to-end and mid-trajectory evaluation.
- **Evaluators / LLM-as-judge**: [50+ metrics](https://deepeval.com/docs/metrics-introduction) — G-Eval (LLM-as-judge with rubric), task completion, tool correctness, answer relevancy, hallucination, RAG, conversational, safety, multimodal; judges run against any LLM provider.
- **Datasets**: `EvaluationDataset` of goldens, loadable from CSV/JSON or synthesized; dataset storage/versioning UI lives in the commercial Confident AI platform.
- **OTel**: has an [OTel integration layer](https://deepwiki.com/confident-ai/deepeval/5.3-framework-integrations) that converts OTel `ReadableSpan`s into DeepEval span types (LlmSpan, AgentSpan, ToolSpan) for evaluating instrumented apps.
- **Pydantic AI fit**: [first-class Pydantic AI integration](https://deepeval.com/integrations/frameworks/pydanticai) that auto-instruments agents via OTel so every agent run, tool call, and LLM call becomes an evaluable span.
- **Deployment shape**: open-source library, [local-first](https://deepeval.com/docs/introduction) (evals run in your environment; only judge LLM keys leave); the results platform (Confident AI) is SaaS/commercial.
- **Kubernetes fit**: the library runs fine in a Job/service; there is no OSS self-hostable results UI — reporting beyond CLI output requires Confident AI or your own storage.
- **License / maturity**: Apache-2.0, [~10k+ stars](https://github.com/confident-ai/deepeval), VC-backed (Confident AI), very active release cadence through 2025-2026.
- **KAOS embed**: good metric-library embed (especially its agent/tool-call metrics consuming OTel spans); KAOS would own results persistence itself.

## Ragas

- **Evaluation model**: offline metric computation over samples; originated in RAG evaluation, now also covers [agentic workflows](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) (tool call accuracy, tool call F1, agent goal accuracy). No online/trace-native evaluation loop of its own.
- **Evaluators / LLM-as-judge**: strong library of LLM-based metrics (faithfulness, context precision/recall, response relevancy, aspect critique) plus traditional non-LLM metrics; metrics are the product.
- **Datasets**: `EvaluationDataset`/sample abstractions plus notable [synthetic test-data generation](https://github.com/vibrantlabsai/ragas) for building eval sets from documents.
- **OTel**: no native OTel ingestion — it consumes explicit sample objects; tracing integrations exist via third-party platforms (Langfuse, Phoenix, LangSmith) that run Ragas metrics over their traces.
- **Pydantic AI fit**: no dedicated integration; usable by mapping Pydantic AI run/message history into Ragas sample types by hand.
- **Deployment shape**: pure Python library; no server, no UI — results are DataFrames/scores you store yourself.
- **Kubernetes fit**: trivial to run in a Job; nothing to host.
- **License / maturity**: Apache-2.0, [~8k+ stars](https://github.com/vibrantlabsai/ragas), repo moved from explodinggradients to [Vibrant Labs](https://vibrantlabs.com/) (same team, commercializing), active releases (v0.4.x in 2025).
- **KAOS embed**: fits the embed pattern as a supplementary metric library (esp. RAG metrics and test-set generation) rather than a full eval engine.

## promptfoo

- **Evaluation model**: offline, declarative config-driven evals of prompts/agents/RAG via CLI and CI ([docs](https://www.promptfoo.dev/docs/intro/)); its center of gravity is [red teaming / vulnerability scanning](https://www.promptfoo.dev/docs/red-team/) (50+ attack types) rather than trajectory-quality evaluation.
- **Evaluators / LLM-as-judge**: rich assertion system — deterministic asserts, model-graded asserts (llm-rubric, factuality, answer-relevance), classifier asserts, custom JS/Python.
- **Datasets**: test cases in YAML/CSV/JS config files; dataset generation helpers; results in a local SQLite store with a web viewer.
- **OTel**: not OTel-native; it drives targets via providers/HTTP rather than consuming traces.
- **Pydantic AI fit**: no dedicated integration; a deployed KAOS agent could be targeted as a generic HTTP provider.
- **Deployment shape**: Node.js CLI/library, [runs completely locally](https://www.promptfoo.dev/docs/faq/); optional self-hosted shared server, plus Enterprise on-prem.
- **Kubernetes fit**: CLI runs in a Job; self-hosted server is deployable (e.g. [Railway template](https://railway.com/deploy/promptfoo-llm-evaluation)) but the ecosystem is Node/TS, not Python.
- **License / maturity**: MIT, [~8k+ stars](https://github.com/promptfoo/promptfoo); [acquired by OpenAI in March 2026](https://openai.com/index/openai-to-acquire-promptfoo/) — stated to remain open source under the current license, but long-term roadmap now points into OpenAI Frontier.
- **KAOS embed**: awkward as a core engine (TS stack, prompt/security focus, acquisition uncertainty); plausible as a complementary security/red-team Job.

## OpenAI Evals

- **Evaluation model**: offline benchmark harness — a [framework plus an open registry of benchmarks](https://github.com/openai/evals) for evaluating models/completions against datasets; no trajectory/agent-trace concepts.
- **Evaluators / LLM-as-judge**: templated eval classes (match, includes, fuzzy match) and model-graded evals (judge prompts); registry-oriented rather than a composable metric library.
- **Datasets**: JSONL samples registered in the eval registry; tightly coupled to the registry layout.
- **OTel**: none.
- **Pydantic AI fit**: none; built around the OpenAI API's completion functions.
- **Deployment shape**: Python library/CLI; results logging is local or to Snowflake/OpenAI tooling; the maintained successor surface is really the [hosted OpenAI Evals product](https://evals.openai.com/) and [openai/frontier-evals](https://github.com/openai/frontier-evals).
- **Kubernetes fit**: runnable in a Job but there is nothing to host and little reason to.
- **License / maturity**: MIT, ~17k stars, but effectively in maintenance mode — the companion [simple-evals is explicitly no longer updated](https://github.com/openai/simple-evals) (July 2025) and the main repo is not accepting new evals; OpenAI's energy has moved to hosted evals and (post-acquisition) promptfoo.
- **KAOS embed**: poor fit — model-benchmark orientation, stagnant OSS trajectory, OpenAI-centric APIs.

## Langfuse

- **Evaluation model**: both offline and online — [dataset experiments via SDK](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk) plus [managed LLM-as-judge evaluators that run automatically over production traces](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge); trajectory context available since scores attach to traces/observations/sessions.
- **Evaluators / LLM-as-judge**: platform-managed LLM-as-judge (fully [MIT-licensed since June 2025](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge) for self-hosters), plus custom scores ingested via SDK/API from any external evaluator library (Ragas/DeepEval cookbooks exist).
- **Datasets**: first-class datasets/items/runs with UI comparison; the experiment runner supports [Langfuse-hosted or local datasets](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk), and remote dataset runs can be triggered via webhook against your own runner.
- **OTel**: [OTel-native ingestion](https://langfuse.com/integrations/native/opentelemetry) — accepts spans from any OTel-instrumented app; SDKs are built on OTel.
- **Pydantic AI fit**: [documented Pydantic AI integration](https://langfuse.com/integrations/frameworks/pydantic-ai) via `Agent.instrument_all()` exporting OTel spans to Langfuse.
- **Deployment shape**: self-hostable platform (web + worker + Postgres + ClickHouse + Redis + S3), not a library.
- **Kubernetes fit**: strong — [official Helm chart, production self-hosting on K8s is the documented path](https://langfuse.com/faq/all/self-hosting-langfuse), free under MIT with EE add-ons (SCIM, audit logs) behind a [commercial license key](https://langfuse.com/self-hosting/license-key).
- **License / maturity**: MIT core, [~15k+ stars](https://github.com/langfuse/langfuse), YC-backed, very active releases.
- **KAOS embed**: not a library embed — it is a platform KAOS would deploy alongside the operator; attractive as the results-storage/online-eval half of a stack where a library (e.g. pydantic-evals) does offline runs and pushes scores/traces in.

## Arize Phoenix

- **Evaluation model**: offline experiments (datasets + tasks + evaluators) and trace-based evaluation of live/collected traces; strong agent focus including [trace-level and span-level evals](https://arize.com/docs/phoenix).
- **Evaluators / LLM-as-judge**: `phoenix-evals` library with pre-tested LLM-judge templates (hallucination, relevance, QA correctness, toxicity, agent tool-selection) plus code evaluators; usable standalone from the platform.
- **Datasets**: datasets and experiments are first-class with versioning and UI comparison; datasets can be built from traces.
- **OTel**: the most OTel-native of the platforms — [built on OpenTelemetry with OpenInference semantic conventions](https://arize.com/docs/phoenix); any OTLP source works.
- **Pydantic AI fit**: documented Pydantic AI tracing via OpenInference/OTel instrumentation; evals then run over those traces.
- **Deployment shape**: self-hostable platform (single container with Postgres/SQLite) plus separable Python libraries (`arize-phoenix`, `phoenix-evals`, `phoenix-client`).
- **Kubernetes fit**: good — [Docker, Docker Compose, and a Kubernetes Helm chart for production](https://arize.com/docs/phoenix) are documented self-hosting paths; fully self-contained, no feature gates.
- **License / maturity**: [Elastic License 2.0](https://github.com/Arize-ai/phoenix/blob/main/LICENSE) (free to self-host; cannot be offered as a managed service to third parties — worth legal review if KAOS is redistributed), ~7k+ stars, backed by Arize AI, active cadence.
- **KAOS embed**: dual-mode fit — embed `phoenix-evals` as a library in a KAOS service, and/or run the Phoenix server as the results/trace store; ELv2 is the main caveat versus MIT/Apache peers.

## MLflow (GenAI evaluation)

- **Evaluation model**: MLflow 3 rebuilt GenAI evals around [`mlflow.genai.evaluate` with scorers over datasets or traces](https://mlflow.org/docs/latest/genai/eval-monitor/); supports offline harness runs, trace-attached feedback, and production monitoring; judges can [inspect the entire execution trace, including an Agent-as-a-Judge mode](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/agentic-overview/).
- **Evaluators / LLM-as-judge**: [built-in research-validated judges](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/predefined) (relevance, safety, groundedness, correctness) plus custom code/LLM scorers via a unified `Scorer` interface.
- **Datasets**: evaluation datasets as MLflow entities (or plain lists/DataFrames); results stored as runs/experiments in the tracking server with UI comparison.
- **OTel**: MLflow Tracing is OTel-compatible (spans can be exported to OTel collectors, and MLflow ingests OTel-instrumented GenAI libraries).
- **Pydantic AI fit**: MLflow ships autologging/tracing integrations for many frameworks including Pydantic AI (via its tracing integrations); not as central as its LangChain/DSPy support.
- **Deployment shape**: library plus self-hostable tracking server; the most polished experience (judge alignment, monitoring) is on Databricks Managed MLflow.
- **Kubernetes fit**: mature — the MLflow tracking server is routinely self-hosted on K8s (community Helm charts, simple Python server + artifact store + DB).
- **License / maturity**: Apache-2.0, ~20k+ stars, Linux Foundation project driven by Databricks, steady release cadence; GenAI eval APIs are newer than the core.
- **KAOS embed**: viable "library + KAOS-deployed tracking server" pattern; heavier general-ML surface area than a purpose-built LLM eval tool, and best features gravitate to Databricks.

## Braintrust

- **Evaluation model**: offline `Eval()` experiments (task + dataset + scorers) with CI integration, plus online scoring of logged production traffic; strong loop between logs, datasets, and experiments ([docs](https://www.braintrust.dev/docs)).
- **Evaluators / LLM-as-judge**: [autoevals](https://github.com/braintrustdata/autoevals) — an open-source scorer library (factuality, closed-QA, moderation, RAG scorers, custom LLM classifiers) usable standalone; the platform adds a judge-authoring UI and human review.
- **Datasets**: first-class versioned datasets in the platform, built from logs or uploads; experiment diffing UI is a highlight.
- **OTel**: accepts OTel trace ingestion into its logging system, but its SDK data model is proprietary-first.
- **Pydantic AI fit**: no first-class integration; generic Python SDK wrapping works.
- **Deployment shape**: SaaS platform; [self-hosting is a hybrid model](https://www.braintrust.dev/docs/guides/self-hosting) — data plane in your infra, control plane (UI/auth/metadata) remains Braintrust-hosted, under an enterprise agreement.
- **Kubernetes fit**: partial — the data plane can run in your cloud, but there is no fully self-contained OSS deployment; the [core platform is proprietary](https://www.braintrust.dev/pricing).
- **License / maturity**: platform closed-source; autoevals is MIT. Well-funded, popular with frontier labs, fast iteration.
- **KAOS embed**: platform does not fit the self-hosted OSS pattern; only autoevals is embeddable as a scorer library.

## LangSmith

- **Evaluation model**: offline [dataset experiments with evaluators](https://docs.langchain.com/langsmith/evaluation), online evaluators over sampled production traces, pairwise comparisons, and annotation queues; agent trajectory evaluation supported over run trees.
- **Evaluators / LLM-as-judge**: LLM-as-judge, heuristic, and custom Python/TS evaluators; the companion [openevals](https://github.com/langchain-ai/openevals) library provides ready-made judges as OSS.
- **Datasets**: strong — datasets with versioning/splits, one-click conversion of production traces into examples, experiment comparison UI.
- **OTel**: [supports OTel](https://www.langchain.com/langsmith/observability) both directions (ingest OTel traces, export LangSmith data to OTel pipelines), though its native format is the LangChain run tree.
- **Pydantic AI fit**: [documented Pydantic AI tracing](https://docs.langchain.com/langsmith/trace-with-pydantic-ai) via OTel; evaluation over those traces works, but the deepest integration is with LangChain/LangGraph.
- **Deployment shape**: SaaS platform; [self-hosted option runs on your Kubernetes cluster](https://www.langchain.com/langsmith/observability) (AWS/GCP/Azure) — but only under an enterprise license.
- **Kubernetes fit**: technically good (Helm-based enterprise self-host), commercially gated; no OSS server.
- **License / maturity**: proprietary platform (openevals/SDKs are MIT); LangChain Inc. backing, large user base, rapid cadence.
- **KAOS embed**: platform conflicts with the OSS self-host pattern; only the openevals judge library is a plausible embed.

## W&B Weave

- **Evaluation model**: offline `Evaluation` objects (dataset + scorers + model/task) with versioned comparisons, plus [online evaluations scoring live production traces](https://weave-docs.wandb.ai/); trajectory data available through its call-tree tracing.
- **Evaluators / LLM-as-judge**: built-in and custom `Scorer` classes including LLM judges (hallucination, context relevance, moderation); automatic versioning of scorers/datasets/code is a differentiator.
- **Datasets**: versioned `Dataset` objects tracked as Weave objects; lineage between dataset versions, evals, and traces.
- **OTel**: [OTel is a supported ingest path](https://weave-docs.wandb.ai/guides/tracking/otel/), but the native data model is W&B-proprietary; not OTel-first.
- **Pydantic AI fit**: no dedicated integration; generic OTel ingest or manual `weave.op` wrapping.
- **Deployment shape**: SaaS-first platform on top of W&B; self-hosting means running [W&B Server (Dedicated or customer-managed)](https://docs.wandb.ai/guides/hosting/) under an enterprise license — the server is not OSS.
- **Kubernetes fit**: W&B Server ships as a K8s operator/Helm deployment for enterprises; heavyweight and license-gated.
- **License / maturity**: SDK Apache-2.0, platform proprietary; W&B acquired by CoreWeave (2025), mature company, active cadence.
- **KAOS embed**: poor fit for the OSS embed pattern — value is concentrated in the proprietary platform.

## Opik (Comet)

- **Evaluation model**: offline experiments (datasets + metrics + prompts) and online evaluation rules (LLM-as-judge over production traces), with agent/trajectory support via full trace logging and [agent optimizer tooling](https://github.com/comet-ml/opik).
- **Evaluators / LLM-as-judge**: [30+ built-in metrics](https://www.comet.com/docs/opik/) — hallucination, moderation, answer relevance, RAG metrics, G-Eval-style judges, plus heuristic metrics and custom Python metrics; human annotation queues.
- **Datasets**: first-class datasets with items, experiment runs, and UI comparison; datasets can be created from traces via the SDK/UI.
- **OTel**: supports OTel ingestion and ships framework integrations (OpenAI, LangChain, LiteLLM, etc.); SDK-native tracing is its primary path.
- **Pydantic AI fit**: has a documented Pydantic AI integration (via OTel-based instrumentation) among its framework integrations.
- **Deployment shape**: full open-source platform (backend in Java + ClickHouse/MySQL/Redis + web UI) with Python/TS SDKs; Comet offers a managed cloud too.
- **Kubernetes fit**: strong — local `opik.sh` for dev and [production-ready Kubernetes Helm charts](https://www.comet.com/docs/opik/self-host/kubernetes) for self-hosting; built on standard OSS infra.
- **License / maturity**: [Apache-2.0](https://github.com/comet-ml/opik), ~10k+ stars, backed by Comet, very active 2025-2026 cadence.
- **KAOS embed**: like Langfuse, a deploy-alongside platform rather than a library embed; its permissive license and Helm story make it one of the stronger self-hosted platform candidates.

## TruLens

- **Evaluation model**: offline and lightweight online — wrap an app (`TruApp`), record traces, and run feedback functions/metrics over records; known for the RAG triad (context relevance, groundedness, answer relevance); [now positioned as "evals and tracing for agents"](https://www.trulens.org/).
- **Evaluators / LLM-as-judge**: feedback functions — LLM-judge metrics against many providers (incl. Snowflake Cortex) plus programmatic checks; a newer [`Metric` class replaces the legacy Feedback API](https://github.com/truera/trulens/releases).
- **Datasets**: weaker — evaluation is record/trace-centric rather than dataset/experiment-centric; no rich dataset versioning story.
- **OTel**: moved to OpenTelemetry-based tracing in its recent architecture (OTel spans as the record format), aligning it with OTel-first stacks.
- **Pydantic AI fit**: no dedicated integration; generic app wrapping or OTel instrumentation required.
- **Deployment shape**: Python library with a local dashboard (Streamlit) and pluggable DB (SQLite/Postgres); deeper hosted experience lives in Snowflake AI Observability.
- **Kubernetes fit**: library runs in Jobs easily; the dashboard is not a real multi-user server — results persistence would be a shared Postgres.
- **License / maturity**: [MIT, Snowflake-backed after the TruEra acquisition](https://www.snowflake.com/en/blog/trulens-open-source-ai/), ~2-3k stars, steady but slower cadence; gravity pulling toward Snowflake-native usage.
- **KAOS embed**: embeddable as a feedback-function library, but overlaps what pydantic-evals/DeepEval/Ragas already cover with less momentum outside Snowflake.

## Comparison table

| Tool | Offline / online | Trajectory eval | LLM-judge | Datasets | OTel | Pydantic AI | Shape | K8s self-host | License |
|---|---|---|---|---|---|---|---|---|---|
| [Pydantic Evals](https://ai.pydantic.dev/evals/quick-start/) | Offline (+online via Logfire) | Yes (span tree) | Yes (`LLMJudge`) | Code + YAML/JSON | Native emit | Same authors | Library | Trivial (no server) | MIT |
| [DeepEval](https://github.com/confident-ai/deepeval) | Offline + span-level | Yes (agent/tool metrics) | Yes (G-Eval, 50+) | Goldens, CSV/JSON | Ingests OTel spans | First-class integration | Library (+SaaS UI) | Library only; UI is SaaS | Apache-2.0 |
| [Ragas](https://github.com/vibrantlabsai/ragas) | Offline | Partial (tool-call metrics) | Yes | Samples + synthetic gen | No | No (manual mapping) | Library | Trivial (no server) | Apache-2.0 |
| [promptfoo](https://github.com/promptfoo/promptfoo) | Offline / CI + red team | No (I/O-level) | Yes (model-graded asserts) | YAML/CSV configs | No | No (HTTP target) | CLI/library (Node) + server | Possible; Node stack | MIT (OpenAI-owned) |
| [OpenAI Evals](https://github.com/openai/evals) | Offline benchmarks | No | Yes (model-graded) | JSONL registry | No | No | Library/CLI | N/A | MIT (maintenance mode) |
| [Langfuse](https://github.com/langfuse/langfuse) | Offline + online | Via trace scores | Yes (managed, MIT) | First-class + runs UI | OTel-native ingest | Documented | Platform | Helm, production-grade | MIT core (+EE) |
| [Phoenix](https://github.com/Arize-ai/phoenix) | Offline + trace-based | Yes (span/trace evals) | Yes (`phoenix-evals`) | First-class + from traces | OTel/OpenInference native | Via OpenInference | Platform + libraries | Helm, self-contained | ELv2 |
| [MLflow](https://mlflow.org/docs/latest/genai/eval-monitor/) | Offline + monitoring | Yes (trace-inspecting judges) | Yes (built-in + agent-judge) | MLflow datasets/runs | OTel-compatible | Tracing integration | Library + server | Mature self-host | Apache-2.0 |
| [Braintrust](https://www.braintrust.dev/docs/guides/self-hosting) | Offline + online | Via logs | Yes (autoevals + UI) | First-class, versioned | Ingest supported | No | SaaS (hybrid self-host) | Data plane only | Proprietary (autoevals MIT) |
| [LangSmith](https://docs.langchain.com/langsmith/evaluation) | Offline + online | Yes (run trees) | Yes (+openevals) | First-class, from traces | Both directions | Via OTel | SaaS (enterprise self-host) | Helm, license-gated | Proprietary |
| [W&B Weave](https://weave-docs.wandb.ai/) | Offline + online | Via call trees | Yes (scorers) | Versioned objects | Secondary ingest | No | SaaS (W&B Server) | Enterprise-gated | SDK Apache-2.0, platform proprietary |
| [Opik](https://github.com/comet-ml/opik) | Offline + online rules | Via traces + agent tooling | Yes (30+) | First-class + from traces | Ingest supported | Integration available | Platform + SDK | Helm, production-grade | Apache-2.0 |
| [TruLens](https://github.com/truera/trulens) | Offline + record-based | Partial (trace records) | Yes (feedback fns) | Weak (record-centric) | OTel-based tracing | No | Library + local dashboard | Library in Jobs | MIT |

## Observations

- **Libraries vs platforms**: pure libraries are Pydantic Evals, Ragas, TruLens, OpenAI Evals, and (effectively) DeepEval and autoevals; self-hostable OSS platforms are Langfuse, Phoenix, Opik, and MLflow; Braintrust, LangSmith, and W&B Weave are commercial platforms whose self-hosting is enterprise-license-gated or hybrid, which sits poorly with a fully self-hosted OSS stack.

- **OTel-native**: Phoenix and Langfuse are OTel-native ingestors; Pydantic Evals natively emits OTel; MLflow, TruLens, DeepEval, Opik, and LangSmith have real but secondary OTel paths; promptfoo, Ragas, and OpenAI Evals have none. This axis matters because KAOS agents already emit OTel traces.

- **Pydantic-AI-aligned**: Pydantic Evals is by the same team and evaluates Pydantic AI agents natively; DeepEval, Langfuse, and Opik have documented Pydantic AI integrations; Phoenix and LangSmith work via OTel instrumentation; the rest need manual glue.

- **KAOS embed-an-OSS-engine candidates**: the Mem0-style pattern (permissive-license library inside a KAOS-owned service/Job) is best matched by Pydantic Evals as the harness, optionally augmented by DeepEval and/or Ragas metric libraries; none of these provides results storage/reporting on its own, so a platform-shaped component (Langfuse, Phoenix, or Opik — all Helm-deployable; note Phoenix's ELv2) or a KAOS-owned results store would cover the reporting and online-eval halves.

- **Risk notes**: OpenAI Evals is effectively legacy; promptfoo's OpenAI acquisition (March 2026) adds roadmap uncertainty despite the open-source commitment; Phoenix's ELv2 restricts offering it as a managed service; Braintrust/LangSmith/Weave concentrate their value in proprietary control planes.
