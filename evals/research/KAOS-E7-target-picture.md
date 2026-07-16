# KAOS-E7 — Target picture

This document describes the ideal target picture for evals in KAOS: a full, end-to-end, production-grade design for what agent evaluation should become. It is grounded in the requirements baseline ([KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md)) and the ecosystem best practice ([KAOS-E2](./KAOS-E2-agent-evals-ecosystem-research.md)), and it is *informed but not constrained* by the tooling research and selection ([KAOS-E3](./KAOS-E3-evals-tooling-landscape.md) through [KAOS-E6](./KAOS-E6-tool-selection.md)). Where the selected tooling falls short of the ideal, the gap is named as a target capability rather than designed around.

This is an unrestricted long-term vision, not an implementation plan. It deliberately describes the optimal realistic end state — the capabilities, surfaces, and properties KAOS evals should have when fully fledged — so incremental work can be steered toward it.

## Design principles

- **KAOS owns the contract; the engine is pluggable.** The eval contract (suites, cases, evaluators, results, provenance), the CRD surface, and the run orchestration are KAOS's; the harness engine behind them is a swappable implementation ([KAOS-E6](./KAOS-E6-tool-selection.md)). This is the same boundary discipline the memory track applied to Mem0.
- **Evaluate the deployed thing.** An eval targets a *deployed* Agent through the same surfaces users call (OpenAI-compatible chat, A2A) — not a re-instantiated in-process copy — so what is scored is what serves, including its ModelAPI, MCP tools, memory binding, and delegation topology. Local/in-process execution exists for development parity but the deployed target is the primary path ([KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md) gap 19).
- **Declarative and Kubernetes-native.** Evals are configured through CRDs and reconciled by the operator, consistent with how KAOS configures everything else; a run is a finite, versioned, garbage-collectable workload.
- **Trace-first trajectory model.** Agents already emit OpenTelemetry; the canonical trajectory of a case is its trace, correlated by propagated trace ID. Trajectory evaluators read traces; online evaluation consumes the same stream; scores are written back using the OTel GenAI evaluation vocabulary (`gen_ai.evaluation.result`) so any OTel backend can display them ([KAOS-E2](./KAOS-E2-agent-evals-ecosystem-research.md)).
- **Results are durable, comparable, and CI-consumable.** Every run concludes with a machine-readable verdict derived from declared gates; results persist with full provenance so runs are comparable across agent versions, and neither traces nor an external platform is the canonical result store ([KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md) gaps 5–6, 15, 17).
- **Judges are governed models.** LLM-as-judge is an evaluator kind, not a privileged path: judge models are `{modelAPI, model}` references, their usage is metered, their prompts/versions are provenance, and their known biases are mitigated by rubric design and calibration sets ([KAOS-E2](./KAOS-E2-agent-evals-ecosystem-research.md)).

## Evaluation model

- **Suite.** The unit of declaration: a set of cases plus the evaluators and gates that judge them, versioned by content hash. Suites live in Git (YAML, schema-validated) or inline in the CRD for small sets, and are addressable as ConfigMap or file references.
- **Case.** Inputs (single message or scripted multi-turn conversation), optional expected output, optional expected-trajectory declarations (required/forbidden tools, delegation targets, hop bounds), metadata/tags for slicing, and optional fixtures (memory preload, environment expectations).
- **Evaluators.** Deterministic checks (equality, contains, regex, JSON/schema, tool-call correctness), scored metrics (latency, token/cost budgets), LLM-as-judge with rubric and structured verdicts, trajectory evaluators over the case's trace, and custom code evaluators behind the contract seam. Each yields assertion/score/label plus reason, per the harness scoring model.
- **Gates.** Declarative pass policy: required evaluators, per-evaluator thresholds, minimum pass rate, critical-case tags that fail the run outright, and budget ceilings (cost/latency) as first-class gate criteria. Gates make the run conclude `Passed`/`Failed` deterministically; infrastructure failure is distinguished from quality failure.
- **Baselines and comparison.** A run can name a baseline run (or "latest passed on this agent"); reports include per-case and aggregate deltas, and regressions surface as first-class findings.

## Execution model

- **On-demand runs.** Applying an eval resource (or `kaos eval run`) reconciles into a finite runner Job that loads the suite, invokes the target agent case-by-case with bounded concurrency, session isolation, per-case timeout, and repetition for flaky-case detection, then scores, gates, persists results, and reports status.
- **Scheduled regression runs.** A cron schedule on the eval resource yields recurring runs with retention policy — the regression harness for deployed fleets.
- **Change-triggered runs.** An opt-in trigger re-runs the suite when the target Agent's spec generation changes (model, prompt, tools), closing the loop between deploys and quality gates.
- **Online evaluation.** An asynchronous scoring worker samples completed production traces (sampling policy declared per agent or store-wide), applies reference-free evaluators (judge rubrics, policy checks, drift detectors), and emits scores as OTel evaluation events linked to the source trace — never adding judge latency to the serving path. Online findings can be promoted into suite cases (the trace-to-dataset loop from [KAOS-E2](./KAOS-E2-agent-evals-ecosystem-research.md)).
- **Multi-agent evaluation.** Delegating fleets are evaluated recursively through the trace model: the orchestrator's case verdict comes from its end-to-end result, while each delegation hop is a sub-span evaluable against its delegated sub-task, giving structural credit assignment without bespoke plumbing ([KAOS-E2](./KAOS-E2-agent-evals-ecosystem-research.md)).

## Control plane

- **An eval resource.** A namespaced CRD declares: the target (an Agent reference; later a selector for fleets), the suite (inline or reference), evaluator configuration including judge `{modelAPI, model}` references, run settings (concurrency, timeout, repetitions), gates, schedule/trigger, results retention, and an optional platform-export sink. Status carries phase, progress, conditions, the verdict, aggregate scores, and a pointer to the full results.
- **Operator responsibilities.** Reconcile eval resources into runner Jobs (image from `defaultImages`), validate references (target Agent Ready, ModelAPI Ready, suite resolvable) with fail-closed conditions, watch Job completion, surface verdict and summary in status, enforce retention/garbage collection, and schedule cron/trigger runs. The runner, not the operator, contains all evaluation logic.
- **Results persistence.** Run results (per-case evidence, scores, reasons, aggregates, provenance envelope: agent generation and image digest, model endpoint, suite hash, judge versions, engine version, trace IDs) are durable beyond the Job — retrievable through the CLI and API, sufficient for comparison without any external platform.
- **CLI.** `kaos eval` verbs: run, watch, list, show (per-case drill-down), compare, export, delete — with machine-readable output and exit codes for CI gating.

## Observability and governance

- Every run and case emits OTel spans under the existing `kaos.*` conventions; scores are attached with the OTel GenAI evaluation vocabulary so Grafana/Langfuse/Phoenix render them without bespoke adapters; usage (tokens, cost) is recorded per case and per judge.
- Suites, reference outputs, and captured candidate outputs are treated as potentially sensitive data: namespace-scoped access, no cross-tenant reads, declared retention, and redaction hooks before export ([KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md) gap 20).
- Provenance is immutable per run, making results reproducible claims rather than dashboard artifacts.

## Capabilities no selected tool provides

Named as target capabilities per the research remit: remote-trajectory evaluation over the OTel backend (the engine's span assertions are in-process only — [KAOS-E5-1](./KAOS-E5-1-pydantic-evals.md)); dataset/suite versioning by content identity; a self-hosted results/comparison surface (the engine's comparison UI is SaaS-only); gate semantics as a first-class contract; change-triggered runs bound to Agent generations; and an OSS online-eval scheduler (absent in Phoenix, heavy in Langfuse — [KAOS-E5-3](./KAOS-E5-3-langfuse.md), [KAOS-E5-4](./KAOS-E5-4-arize-phoenix.md)).

## Context manifest

In-scope inputs: [KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md), [KAOS-E2](./KAOS-E2-agent-evals-ecosystem-research.md), [KAOS-E6](./KAOS-E6-tool-selection.md), and the deep dives [KAOS-E5-1](./KAOS-E5-1-pydantic-evals.md) through [KAOS-E5-4](./KAOS-E5-4-arize-phoenix.md). Out of scope: implementation sequencing (owned by the plan) and component decomposition (owned by the ADRs).
