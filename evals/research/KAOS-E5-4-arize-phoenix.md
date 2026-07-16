# KAOS-E5-4 — Arize Phoenix

Deep dive on [Arize Phoenix](https://github.com/Arize-ai/phoenix) as the platform alternative to Langfuse for the "results-and-online" half of the KAOS evals stack: trace ingestion, eval-on-traces, datasets/experiments, self-hosting footprint, and the Elastic License question.

All claims verified against the official docs (hosted at [arize.com/docs/phoenix](https://arize.com/docs/phoenix), sourced from the `docs/` tree of the Phoenix repository) and the GitHub repo as of July 2026.

## What Phoenix is

Phoenix is Arize's open-source AI observability and evaluation platform: OpenTelemetry-based tracing, LLM-as-judge and code evals, versioned datasets, experiments, a prompt playground, and prompt management, all served from [one container](https://arize.com/docs/phoenix/self-hosting/architecture) (web UI, trace collector, SQL backend).

It is also the reference backend for [OpenInference](https://github.com/Arize-ai/openinference), Arize's OTel-compatible semantic conventions for LLM spans.

## Tracing: OpenInference vs plain OTel GenAI

- Phoenix ingests standard OTLP — HTTP on port 6006 at `/v1/traces`, gRPC on 4317 (see the [Docker guide](https://arize.com/docs/phoenix/self-hosting/deployment-options/docker)). Any OTel SDK can export to it; the only question is whether span attributes render richly in the UI.

- Phoenix's native attribute format is [OpenInference semantic conventions](https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md) (`llm.input_messages.*`, `llm.token_count.*`, `tool.*`), which predate the OTel GenAI conventions.

- The [Translating Semantic Conventions](https://arize.com/docs/phoenix/tracing/concepts-tracing/translating-conventions) page explains that traces from OpenLIT, OpenLLMetry, and OTel GenAI instrumentations historically needed a client-side `OpenInferenceSpanProcessor` to display fully in Phoenix.

- This changed materially: since **arize-phoenix 15.10.0**, Phoenix [auto-converts OTel GenAI (`gen_ai.*`) attributes to OpenInference at ingest time](https://arize.com/docs/phoenix/release-notes/05-2026/05-15-2026-otel-semconv-conversion) — `gen_ai.input.messages` → `llm.input_messages.*`, `gen_ai.usage.*` → token counts, plus tool definitions and retrieval documents — with no client-side code changes. Existing OpenInference attributes take precedence; conversion only fills gaps. (Background: [GitHub issue #10622](https://github.com/Arize-ai/phoenix/issues/10622).)

- **Pydantic AI path**: Pydantic AI emits OTel GenAI spans natively. Phoenix's [Pydantic AI integration](https://arize.com/docs/phoenix/integrations/python/pydantic/pydantic-tracing) recommends `openinference-instrumentation-pydantic-ai`, which is just an `OpenInferenceSpanProcessor` added to the tracer provider alongside a normal `OTLPSpanExporter`.

- With ingest-time conversion, KAOS could also point Pydantic AI's plain OTLP output straight at Phoenix and keep the runtime vendor-neutral; the OpenInference processor remains the docs-blessed path for the richest rendering, and [extracting dataset examples from spans](https://arize.com/docs/phoenix/tracing/concepts-tracing/translating-conventions) still keys off OpenInference attributes.

## Evaluation: the `phoenix-evals` library

- [`arize-phoenix-evals`](https://arize.com/docs/phoenix/evaluation/evals) (3.x) is an installable library, deliberately usable [independently of the Phoenix server](https://arize.com/docs/phoenix/evaluation/how-to-evals/using-evals-with-phoenix).

- Core API: an `LLM` wrapper, `evaluate_dataframe` / `async_evaluate_dataframe` (with a `concurrency` knob), and built-in evaluators in `phoenix.evals.metrics` — `FaithfulnessEvaluator`, `CorrectnessEvaluator`, `DocumentRelevanceEvaluator`, `ConcisenessEvaluator`, and more — each returning `Score` objects with label, numeric score, and explanation.

- Judge models are configured via [`LLM(provider=..., model=..., **client_kwargs)`](https://arize.com/docs/phoenix/evaluation/how-to-evals/configuring-the-llm), where `base_url`, `api_key`, and `api_version` pass through to the underlying client — so an OpenAI-compatible endpoint like the KAOS LiteLLM proxy works via `provider="openai", base_url=...`.

- There is also a first-class [LiteLLM adapter](https://arize.com/docs/phoenix/evaluation/how-to-evals/configuring-the-llm) (`provider="litellm", client="litellm"`, invoking `litellm.completion()`), covering LiteLLM's entire provider matrix — a natural fit for KAOS.

- Custom judges: [custom LLM evaluators](https://arize.com/docs/phoenix/evaluation/how-to-evals/custom-llm-evaluators) with your own prompt templates (e.g. `ClassificationEvaluator` with weighted label choices), plus plain-Python [code evaluators](https://arize.com/docs/phoenix/evaluation/how-to-evals/code-evaluators). Eval prompts can be versioned in Phoenix Prompt Management and converted via `phoenix_prompt_to_prompt_template` ([docs](https://arize.com/docs/phoenix/evaluation/how-to-evals/using-evals-with-phoenix)).

- **Datasets & experiments**: [versioned datasets](https://arize.com/docs/phoenix/datasets-and-experiments/how-to-datasets) upload from dataframes or extract from spans; [`client.experiments.run_experiment`](https://arize.com/docs/phoenix/datasets-and-experiments/how-to-experiments/run-experiments) runs a task over a dataset with evaluators attached, and any `phoenix-evals` evaluator is drop-in compatible with experiments. There is an [eval-CI-with-pytest](https://arize.com/docs/phoenix/datasets-and-experiments/how-to-experiments/eval-ci-with-pytest) recipe for regression gating.

- **Server evals** (newer): [evaluators can be attached to a dataset in the UI](https://arize.com/docs/phoenix/evaluation/server-evals/overview) — LLM judges backed by Phoenix-managed prompts, sandboxed Python/TypeScript code evaluators, or pre-built deterministic metrics (Contains, Exact Match, Regex, Levenshtein, JSON Distance) — and they run server-side automatically, with every evaluator execution itself traced in its own project.

- Scope caveat: [dataset evaluators auto-run only for experiments executed from the Phoenix UI/Playground](https://arize.com/docs/phoenix/datasets-and-experiments/how-to-experiments/how-to-dataset-evaluators); programmatic experiments must pass evaluators explicitly.

- **Annotations**: evals are stored as span annotations with `annotator_kind` of `LLM`, `CODE`, or `HUMAN` ([Log Evaluation Results](https://arize.com/docs/phoenix/tracing/how-to-tracing/feedback-and-annotations/llm-evaluations)); the UI adds human annotation queues and feedback capture alongside automated scores.

## Online / trace-eval workflow

- The documented loop for evals on live traces is client-driven: [export spans from Phoenix into a dataframe, run `phoenix-evals` over them, and log results back](https://arize.com/docs/phoenix/tracing/how-to-tracing/feedback-and-annotations/evaluating-phoenix-traces).

- Logging back is `Client().spans.log_span_annotations_dataframe(dataframe=..., annotation_name=..., annotator_kind="LLM")` keyed on `span_id`; document-level evals additionally key on `document_position` ([docs](https://arize.com/docs/phoenix/tracing/how-to-tracing/feedback-and-annotations/llm-evaluations)). Scores then appear attached to spans and in project aggregates.

- **There is no built-in scheduler for evals over incoming production traces in OSS Phoenix.** The docs state that continuous monitoring — "evals on production traffic with alerting and threshold-based triggers" — is an [Arize AX feature (Online Evals)](https://arize.com/docs/phoenix/evaluation/llm-evals).

- Phoenix's own [Langfuse comparison page](https://arize.com/docs/phoenix/resources/frequently-asked-questions/langfuse-alternative-arize-phoenix-vs-langfuse-key-differences) leaves the "Online Evals" cell unchecked for Phoenix while checking it for Langfuse. In practice you run the pull-score-log loop yourself — in KAOS terms, we would own that loop (e.g. a CronJob), not the platform.

## Self-hosting

- Single container: `arizephoenix/phoenix` on [Docker Hub](https://hub.docker.com/r/arizephoenix/phoenix/tags) (with `-nonroot` and `-debug` variants) bundles web UI, OTLP collector, and REST/GraphQL API in one process. The docs describe [self-hosting as free with no feature gates](https://arize.com/docs/phoenix/self-hosting), fully air-gappable.

- Storage: [SQLite by default (just mount a volume, data under `PHOENIX_WORKING_DIR`) or PostgreSQL >= 14 for production](https://arize.com/docs/phoenix/self-hosting/architecture) via `PHOENIX_SQL_DATABASE_URL`. No ClickHouse, no Redis, no S3, no queue — decisively lighter than Langfuse v3's web + worker + Postgres + ClickHouse + Redis + blob-storage stack.

- The trade-off is OLAP headroom: for "high-volume ingestion, sub-second queries at scale", the [architecture page](https://arize.com/docs/phoenix/self-hosting/architecture) itself points at Arize AX's proprietary adb database.

- Kubernetes: an official [Helm chart](https://arize.com/docs/phoenix/self-hosting/deployment-options/kubernetes-helm) is published as an OCI artifact (`oci://registry-1.docker.io/arizephoenix/phoenix-helm`), deploying Phoenix with PostgreSQL by default and a `values.yaml` for overrides; uninstall preserves the Postgres PVC.

- Scaling patterns per the [architecture doc](https://arize.com/docs/phoenix/self-hosting/architecture): multiple stateless Phoenix instances behind a load balancer sharing one Postgres; separate instances per environment; schema-isolation via `PHOENIX_SQL_DATABASE_SCHEMA`; even an app-sidecar pattern.

- Auth: off by default; [`PHOENIX_ENABLE_AUTH=true` plus `PHOENIX_SECRET`](https://arize.com/docs/phoenix/self-hosting/features/authentication) enables local accounts, RBAC (admin/member/viewer), and system/user API keys sent as `Authorization: Bearer <token>` (auto-injected by `phoenix.otel` and `phoenix-client` from `PHOENIX_API_KEY`).

- Enterprise identity: [OAuth2/OIDC identity providers](https://arize.com/docs/phoenix/self-hosting/features/authentication#configuring-oauth2-identity-providers) and, since Dec 2025, [LDAP / Active Directory](https://arize.com/docs/phoenix/release-notes/12-2025/12-06-2025-ldap-authentication-support).

- Multi-project yes, multi-tenant no: projects separate traces within an instance, but [a Phoenix instance is a single tenant](https://arize.com/docs/phoenix/self-hosting/architecture) — for hard team isolation you deploy multiple instances. Fine-grained resource tags are only planned ([issue #10504](https://github.com/Arize-ai/phoenix/issues/10504)); organizations/spaces multi-tenancy is an AX feature.

## License: Elastic License 2.0

- Phoenix is licensed under [ELv2](https://github.com/Arize-ai/phoenix/blob/main/LICENSE) — not OSI-approved. The grant is broad (use, copy, distribute, modify); the key limitation is: you may not "provide the software to third parties as a hosted or managed service, where the service provides users with access to any substantial set of the features or functionality of the software". The other two limitations (license-key circumvention, notice removal) are currently moot since Phoenix ships no license-key-gated features.

- The docs' [license page](https://arize.com/docs/phoenix/self-hosting/license) confirms the practical read: self-hosting on your own infrastructure or cloud account is "free and fully permitted" with no feature gates.

- For KAOS itself the risk is low: recommending Phoenix, shipping manifests/Helm values that deploy it, and users running it for their own teams are all ordinary "use" — not providing Phoenix as a service to third parties.

- Internal multi-team use inside one company is safe: ELv2's definitions scope "your company" to all commonly controlled entities, so colleagues are not "third parties".

- The edge case is a KAOS adopter operating a **multi-tenant platform where external customers get access to the Phoenix UI/API as part of the product** — that plausibly crosses the hosted/managed-service line and would need Arize's blessing or a commercial arrangement. This deserves an explicit callout in KAOS docs. Contrast: Langfuse core is [MIT with a gated EE folder](https://github.com/langfuse/langfuse/blob/main/LICENSE).

## Maturity and Arize backing

- [~10.6k GitHub stars, ~1k forks](https://github.com/Arize-ai/phoenix), created November 2022, very active: near-daily pushes, latest release v18.0.0 (July 2026), and monthly [release notes](https://arize.com/docs/phoenix/release-notes) landing substantial features (server evals, OTel GenAI conversion, LDAP, the PXI in-platform debugging agent).

- Backed by Arize AI, whose commercial product [Arize AX](https://arize.com/docs/phoenix/self-hosting) is the upsell path: AX adds online evals with alerting, true multi-tenancy (organizations/spaces), the adb OLAP backend for high-volume ingest, and enterprise support.

- Phoenix is a genuinely full-featured OSS tier, but the seams — online eval automation, multi-tenancy, OLAP scale — are exactly where AX begins. That's a predictable and stable model, with a real steering incentive to be aware of.

## How it would embed in KAOS

- Deploy Phoenix via its Helm chart (or a plain Deployment) alongside Postgres, `PHOENIX_ENABLE_AUTH=true`; one instance per KAOS installation, one Phoenix project per agent or namespace.

- The Pydantic AI runtime keeps emitting OTLP; either add `openinference-instrumentation-pydantic-ai`'s span processor in the server image, or rely on Phoenix's ingest-time [OTel GenAI conversion](https://arize.com/docs/phoenix/release-notes/05-2026/05-15-2026-otel-semconv-conversion) and keep the runtime vendor-neutral — the latter fits KAOS's OTel-first posture and means the same OTLP stream could feed Phoenix or Langfuse interchangeably.

- Offline evals: KAOS eval jobs use `arize-phoenix-evals` with `LLM(provider="openai", base_url=<litellm-proxy>)` or the LiteLLM adapter; datasets and experiments via `phoenix-client`; results land in the Phoenix UI as experiment annotations.

- Online evals: a KAOS-owned CronJob/worker runs the documented [pull-spans → score → `log_span_annotations_dataframe`](https://arize.com/docs/phoenix/tracing/how-to-tracing/feedback-and-annotations/evaluating-phoenix-traces) loop on recent production spans, since the OSS platform will not schedule it for us.

## Risks / gaps

- No automated online/production eval scheduling or alerting in OSS Phoenix — KAOS must build and operate that loop, whereas Langfuse ships UI-configured LLM-as-judge evaluators that run automatically on sampled incoming traces.

- ELv2 is a soft blocker for any KAOS adopter reselling observability to external customers; needs a clear docs callout.

- Single-tenant model: per-team isolation means instance-per-team, which KAOS would have to orchestrate (mitigated somewhat by the tiny footprint and Postgres schema isolation).

- Postgres-only storage may strain at very high trace volume — the docs themselves route that case to Arize's commercial adb.

- OpenInference-vs-GenAI duality is improving (ingest-time conversion) but not fully gone: span-to-dataset extraction still assumes OpenInference attributes.

## Head-to-head vs Langfuse (honest note)

- **License**: Langfuse wins — MIT core (with gated EE extras) vs Phoenix's ELv2 no-managed-service restriction; for a framework recommending a default, MIT is the cleaner story.

- **Ops footprint**: Phoenix wins decisively — one container + Postgres (SQLite for dev) vs Langfuse v3's web/worker/Postgres/ClickHouse/Redis/blob-storage stack.

- **OTel-nativeness**: Phoenix wins — it is an OTLP endpoint with first-class OpenInference plus automatic GenAI-convention conversion at ingest; Langfuse accepts OTLP but maps it onto its own observation model.

- **Eval-on-traces depth**: split — Phoenix has the stronger eval *library* (typed evaluators, LiteLLM adapter, experiments, every judge call itself traced); Langfuse has the stronger *managed online* eval story. Since the "online half" is the reason this category exists in KAOS, Langfuse still holds the one feature Phoenix reserves for Arize AX — with Phoenix you trade that for a far lighter stack and better OTel alignment.
