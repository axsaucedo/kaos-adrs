# KAOS-E4 — Tool comparison and shortlist

This document scores the [KAOS-E3](./KAOS-E3-evals-tooling-landscape.md) landscape against the requirements baseline of [KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md) and the vocabulary of [KAOS-E2](./KAOS-E2-agent-evals-ecosystem-research.md), and fixes the shortlist for the stage-5 deep dives. It compares and narrows; the selection itself is made in [KAOS-E6](./KAOS-E6-tool-selection.md) after the deep dives.

## Hard constraints

Derived from the KAOS architecture and the [KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md) requirements close, a candidate must satisfy all of these to be shortlisted:

- **OSS and self-hostable without license gates.** KAOS is fully self-hosted on Kubernetes; anything whose evaluation capability, results store, or UI is SaaS-only or enterprise-license-gated cannot be the load-bearing engine. This excludes Braintrust, LangSmith, and W&B Weave outright, whatever their feature depth.
- **Python-embeddable or OTLP-consumable.** The KAOS runtime is Python/Pydantic AI and the established adoption pattern is a permissive-license library embedded in a KAOS-owned workload (the Mem0 precedent). A candidate must either embed as a Python library in a KAOS-owned runner, or consume the OTel traces KAOS agents already emit.
- **Agent-shaped evaluation, not just I/O pairs.** [KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md) gaps 11–12 require trajectory access (tool calls, delegation hops, usage); a purely prompt-in/text-out harness cannot express them.
- **Model access through `{modelAPI, model}` references.** LLM-as-judge calls must route through a KAOS `ModelAPI` (OpenAI-compatible base URL), so judges must accept a custom OpenAI-compatible endpoint rather than demanding provider-specific SDK keys.
- **Maintained.** Active 2025–2026 release cadence; effectively-frozen projects are excluded as load-bearing dependencies.

## Scoring against the baseline

The [KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md) requirements decompose the needed capability into two halves that no single OSS tool covers alone (the closing observation of [KAOS-E3](./KAOS-E3-evals-tooling-landscape.md)): an **offline harness half** (dataset/case contract, run orchestration against a target agent, evaluator library including LLM-as-judge, gate semantics) and a **results-and-online half** (durable results, comparison/reporting, trace-based online scoring). Candidates are scored per half.

### Harness-half candidates

- **Pydantic Evals** — strongest structural fit: same authors as the KAOS runtime, `Dataset`/`Case`/`Evaluator` contract with YAML/JSON dataset serialization, `LLMJudge` with configurable OpenAI-compatible models, span-tree access for trajectory assertions, native OTel emission, MIT, pure library with no server to operate. Weaknesses: a leaner built-in metric library than DeepEval and no results persistence (by design).
- **DeepEval** — the deepest evaluator library (G-Eval, 50+ metrics, agent/tool-call metrics) with a documented Pydantic AI integration; Apache-2.0 library. Weaknesses: the experience is built around the Confident AI SaaS for anything beyond library use (reporting, datasets at rest), pulling against the self-hosted constraint; heavier dependency surface.
- **Ragas** — RAG-centric metric library; partial tool-call metrics; no OTel; manual Pydantic AI mapping. Useful as a supplementary metric source at most; not shortlisted as a deep dive because it cannot be the harness and overlaps DeepEval as a metric library.
- **promptfoo** — CI-shaped and red-team-strong but I/O-level (no trajectory), Node stack, no OTel, and post-acquisition roadmap uncertainty. Excluded.
- **OpenAI Evals** — maintenance mode; fails the maintained constraint. Excluded.
- **TruLens** — OTel-based but record-centric with a weak dataset story, no Pydantic AI integration, and momentum concentrated in Snowflake-native usage. Excluded.

### Results-and-online-half candidates

- **Langfuse** — OTel-native trace ingestion, first-class datasets and experiment runs, LLM-as-judge over production traces fully MIT for self-hosters since June 2025, production-grade Helm chart. The most complete self-hosted platform for the online half. Weakness: its harness/SDK is its own idiom, so pairing it with a Pydantic-Evals-shaped harness needs an integration boundary decision (score export vs dataset-run API).
- **Arize Phoenix** — OTel/OpenInference-native, span/trace evals, self-contained single-container self-host, strong eval libraries (`phoenix-evals`). Weakness: Elastic License 2.0 — free to self-host but restricts offering it as a managed service, a real constraint if KAOS deployments are themselves multi-tenant platforms.
- **Opik** — Apache-2.0, Helm-deployable, 30+ metrics, online rules. Weakness: heavyweight stack (Java backend + ClickHouse + MySQL + Redis) — a large operational footprint for KAOS to recommend as a dependency; its differentiation over Langfuse does not justify the heavier stack. Near-miss: excluded from deep dives, revisitable.
- **MLflow** — mature self-host and real GenAI eval features, but its centre of gravity is the ML-experiment platform; the GenAI eval surface is younger than Langfuse/Phoenix and its tracing path is secondary. Excluded from deep dives.

## Shortlist for stage-5 deep dives

The deep-dive set pairs the two strongest candidates per half, so the selection stage can weigh one-per-half against alternatives:

1. `KAOS-E5-1-pydantic-evals` — presumptive harness engine; verify the Dataset/Case/Evaluator/LLMJudge APIs, custom-endpoint judge support, span-tree trajectory assertions, dataset serialization, concurrency/retry semantics, and OTel emission shape.
2. `KAOS-E5-2-deepeval` — the harness alternative and supplementary-metric source; verify library-only operation without the SaaS, the Pydantic AI integration depth, agent metrics, and judge model routing through custom endpoints.
3. `KAOS-E5-3-langfuse` — presumptive online/results platform; verify OTel ingestion of KAOS agent traces, dataset/experiment APIs, self-hosted LLM-as-judge configuration with custom endpoints, score export, and the Helm/self-host operational shape.
4. `KAOS-E5-4-arize-phoenix` — the platform alternative; verify OpenInference/OTel compatibility with KAOS spans, trace-eval workflow, ELv2 implications for KAOS adopters, and operational footprint versus Langfuse.

## Exclusion record

| Tool | Excluded because |
|---|---|
| Braintrust, LangSmith, W&B Weave | evaluation/results value concentrated in proprietary or enterprise-gated control planes; fails the self-hosted OSS constraint |
| OpenAI Evals | maintenance mode; fails the maintained constraint |
| promptfoo | I/O-level only (no trajectory), Node stack, no OTel; acquisition roadmap risk |
| Ragas | metric library only, RAG-centric, no OTel; overlaps DeepEval without the agent metrics |
| TruLens | weak dataset story, no Pydantic AI path, Snowflake-gravitating momentum |
| Opik | near-miss: capable and Apache-2.0 but operationally heavyweight (ClickHouse/MySQL/Redis/Java) relative to its differentiation over Langfuse |
| MLflow | GenAI eval surface younger and secondary to its ML-platform core |

## What KAOS owns regardless of shortlist outcome

Consistent across every pairing, and carried into the deep dives as the evaluation lens: KAOS owns the declarative control plane (an eval CRD and its reconciliation into finite runs), the framework-independent result contract and its persistence ([KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md) gap 5 — neither traces nor a third-party platform should be the canonical result store for CRD status and gating), the runner that targets deployed agents through their existing invocation surfaces, judge-model routing through `ModelAPI` references, and the gate/threshold semantics that make an eval run conclude pass or fail.
