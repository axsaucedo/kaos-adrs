# KAOS-E6 — Tool selection

This document records the tooling selection for the KAOS eval capability. It decides; the evidence is the shortlist rationale in [KAOS-E4](./KAOS-E4-tool-comparison-and-shortlist.md) and the verified deep dives [KAOS-E5-1](./KAOS-E5-1-pydantic-evals.md) through [KAOS-E5-4](./KAOS-E5-4-arize-phoenix.md), against the requirements baseline of [KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md).

## The selection

**Pydantic Evals is adopted as the harness engine, embedded as a library inside a KAOS-owned eval runner. No results-platform dependency is adopted: KAOS owns the canonical result contract, persistence, and gate semantics, with platform export (Langfuse, Phoenix) kept as an optional, additive integration seam.** This repeats the Mem0 precedent from the memory track: a permissive-license OSS engine embedded as a library behind a KAOS-owned contract, with KAOS supplementing exactly the capabilities the engine does not provide.

## Why Pydantic Evals for the harness

- **Structural alignment.** It is authored by the Pydantic AI team inside the pydantic-ai monorepo, evaluates any sync/async callable as the task, and its `Dataset`/`Case`/`Evaluator` contract maps one-to-one onto the dataset/case/evaluator gaps in [KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md) (gaps 1–3). The KAOS runtime is Pydantic AI, so idioms, typing, and OTel emission match ([KAOS-E5-1](./KAOS-E5-1-pydantic-evals.md)).
- **Judge routing works through `ModelAPI`.** `LLMJudge` accepts any pydantic-ai `Model` object, so judges route through the LiteLLM proxy with `OpenAIChatModel` + `OpenAIProvider(base_url=...)` — the `{modelAPI, model}` reference pattern KAOS already has, closing gap 4 without provider keys ([KAOS-E5-1](./KAOS-E5-1-pydantic-evals.md)).
- **Structured results out.** `EvaluationReportAdapter.dump_json()` exports the full report for a KAOS-owned results store, so the engine does not trap results in a UI ([KAOS-E5-1](./KAOS-E5-1-pydantic-evals.md)).
- **MIT, no server, trivial to run in a Job.** The harness adds no operational footprint; concurrency, repetition, and retry semantics are built in.

DeepEval was the harness alternative and is **not adopted**: it operates library-only but its dataset/report/tracing gravity is the Confident AI SaaS, its agentic metrics require its own `@observe` tracing stack parallel to KAOS OTel, and a current release carries an import-time global TracerProvider hijack risk ([KAOS-E5-2](./KAOS-E5-2-deepeval.md)). Its metric depth (G-Eval, DAG metrics) remains attractive; the evaluator seam stays open so DeepEval metrics can later be wrapped as custom evaluators behind the KAOS contract, treated as an optional extra rather than a core dependency.

## Why no platform dependency

Both platform candidates are capable but neither belongs on the critical path:

- Coupling CRD status and gate verdicts to an external platform's async pipeline is the wrong control-plane dependency — the operator must be able to conclude pass/fail from state it owns ([KAOS-E5-3](./KAOS-E5-3-langfuse.md) reaches the same recommendation from the Langfuse side).
- **Langfuse** is the stronger online-eval platform (OTLP-native, remote dataset runs designed for external harnesses, judge evals MIT since June 2025) but its self-host footprint is heavy (web + worker + Postgres + ClickHouse + Redis + S3; ~12 CPU / 25 GiB minimum) — far too much to make a KAOS dependency ([KAOS-E5-3](./KAOS-E5-3-langfuse.md)).
- **Phoenix** is much lighter (one container + Postgres, ELv2 with no feature gates) and auto-converts OTel GenAI attributes at ingest, but OSS Phoenix has no online-eval scheduler (client-driven loops only) and is single-tenant per instance ([KAOS-E5-4](./KAOS-E5-4-arize-phoenix.md)).

The KAOS-owned result contract therefore stays canonical, and platform export is a seam: results (and later, online scores) can be pushed to Langfuse's scores/dataset-run APIs or logged to Phoenix span annotations by an optional exporter, chosen by the deployment, never load-bearing for reconciliation or gating.

## The build-versus-adopt boundary

Adopted from Pydantic Evals: case/dataset model with YAML/JSON serialization and schema generation, evaluator execution, built-in evaluators including `LLMJudge`, concurrency/repetition/retry, report assembly and JSON export, OTel emission of harness runs.

KAOS owns, regardless of engine (each item traces to a [KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md) gap):

- **The eval contract and result envelope** — a framework-independent Pydantic contract (suite, case refs, evaluator config, run spec, per-case results, aggregates, provenance) so the engine is swappable and results are durable outside the harness process (gaps 1, 5, 15).
- **The runner** — target adapters that invoke deployed agents over their existing surfaces (OpenAI-compatible chat, A2A) as the harness task function, with per-case timeout (absent in the engine), session isolation, and failure-kind separation (gaps 3, 11, 14, 19).
- **Dataset identity** — the engine has no versioning; KAOS derives dataset identity from a content hash recorded in provenance (gap 15).
- **Remote trajectory evaluation** — the engine's span-tree assertions are strictly in-process and cannot see a remote agent's spans; trajectory checks against deployed agents are a KAOS-built evaluator seam over the OTel backend by propagated trace ID, and a first-class reason the runner records trace IDs per case (gaps 11, 12; [KAOS-E5-1](./KAOS-E5-1-pydantic-evals.md)).
- **Gate semantics** — thresholds, required evaluators, pass-rate policy, and the machine-readable conclusion consumed by CRD status and CI (gaps 16, 17).
- **The control plane and CLI** — the eval CRD, Job-backed reconciliation, status/conditions, and the `kaos eval` surface (gaps 7, 8, 9, 18).
- **Version pinning discipline** — the engine is fast-moving (v2.x, API changes on main); KAOS pins and upgrades deliberately ([KAOS-E5-1](./KAOS-E5-1-pydantic-evals.md)).

## Deferred

- **Online (production-trace) evaluation** — built on the OTel GenAI conventions and the `gen_ai.evaluation.result` event vocabulary ([KAOS-E2](./KAOS-E2-agent-evals-ecosystem-research.md)) as an asynchronous scoring worker, optionally paired with Langfuse; deferred until the offline capability is landed.
- **DeepEval metric wrapping, Langfuse/Phoenix exporters** — additive integrations behind existing seams.
- **A second harness engine** — the KAOS contract keeps the seam, but one engine is shipped and supported; the memory track's single-engine discipline applies.
