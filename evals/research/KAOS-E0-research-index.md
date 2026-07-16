# KAOS evals research index

This document opens the research phase for KAOS agent evaluation ("evals"). It defines the staged research pipeline at a high level so each stage can be carried out, reviewed, and cited independently. The staging mirrors the memory track ([`../../memory/research/`](../../memory/research/)): establish the current state and requirements first, survey the problem space and the tooling informed-but-not-constrained by what exists, narrow to a shortlist, deep-dive the shortlisted tools, select, and close with an unrestricted target picture that the architecture-decision records then reconcile with what is buildable now.

The remit: KAOS deploys and operates Pydantic AI agents on Kubernetes through CRDs (Agent, ModelAPI, MCPServer, MemoryStore) with an operator, a Python runtime (`pydantic-ai-server/pais`), a CLI, and OpenTelemetry throughout. Evals must become a first-class, scalable capability of that system — declarative, multi-agent-aware, and consistent with the existing architectural style (central services where warranted, CRDs describing infrastructure and policy, thin agents) — rather than a bolted-on script.

## Stages

### KAOS-E1 — Current KAOS evaluation surface and limitations

The requirements baseline. What KAOS has today that is evaluation-adjacent: the runtime's testing and mock surfaces (`DEBUG_MOCK_RESPONSES`, deterministic examples), OpenTelemetry traces of agent runs and tool calls, the e2e test harness, CLI invocation paths (`kaos agent invoke`), A2A/delegation and autonomous-loop surfaces that evals must be able to exercise, and the ModelAPI/MemoryStore control-plane patterns an eval capability would reuse. Closes with the gap list: what "evaluating an agent" requires that KAOS cannot express today.

### KAOS-E2 — Agent evaluation ecosystem research

The conceptual survey, tool-agnostic. The evaluation taxonomy for LLM agents: offline (dataset-driven) versus online (production-trace-driven) evaluation; end-to-end task success versus stepwise/trajectory evaluation (tool selection, argument correctness, path efficiency); evaluator kinds (deterministic assertions, LLM-as-judge, human annotation, code-based scorers); dataset and golden-set management; regression gating and CI integration; scoring, aggregation, and experiment comparison; production practices (sampling, guardrails-versus-evals boundary, drift monitoring); and multi-agent/delegation evaluation. Establishes the vocabulary later stages use.

### KAOS-E3 — Evals tooling landscape

The broad survey of frameworks and platforms, each characterised on the same axes: evaluation model (offline/online, e2e/trajectory), evaluator library, dataset handling, LLM-as-judge support, OpenTelemetry/tracing integration, Pydantic AI compatibility, deployment shape (library, service, platform), Kubernetes fit, license and maturity. Candidates include (not limited to): Pydantic Evals, DeepEval, Ragas, promptfoo, OpenAI Evals, Langfuse, Arize Phoenix, MLflow evaluation, Braintrust, LangSmith, W&B Weave, Opik/Comet, TruLens.

### KAOS-E4 — Tool comparison and shortlist

Scores the KAOS-E3 landscape against the KAOS-E1 requirements baseline and the KAOS-E2 vocabulary, applying KAOS's hard constraints (OSS/self-hostable, Pydantic AI runtime, Kubernetes-native operation, OTel-first observability). Produces the fixed shortlist for the stage-5 deep dives and records why each excluded tool was excluded.

### KAOS-E5-<n> — Per-tool deep dives

One document per shortlisted tool (`KAOS-E5-1-<toolname>` …): actual APIs and extension points verified against the tool's documentation and source, how it would embed in the KAOS runtime and control plane, what KAOS would own around it, operational shape, and the specific risks or gaps KAOS must supplement.

### KAOS-E6 — Tool selection

The selection record: which engine (or engines) back the KAOS eval capability, the build-versus-adopt boundary, and what stays KAOS-owned regardless of engine. Decides, not surveys; cites KAOS-E4/E5 evidence.

### KAOS-E7 — Target picture

The unrestricted target: what a production-grade, Kubernetes-native eval capability for KAOS looks like — the evaluation model (suites, cases, evaluators, datasets), the execution model (on-demand runs, scheduled regression runs, online trace evaluation), the control plane (CRD shapes and status/reporting), multi-agent and delegation evaluation, gating and lifecycle integration, and observability. Deliberately not constrained to the selected tooling; the ADRs reconcile it with what is adoptable now.

## Downstream

The research feeds [`../adrs/adr_high_level_components.md`](../adrs/adr_high_level_components.md), which decomposes the target picture into the small set of components requiring an ADR; the ADRs feed [`../plan/proposed-split.md`](../plan/proposed-split.md), which phases the implementation into stacked PRs.

Conventions for all documents in this track: [`../CONVENTIONS.md`](../CONVENTIONS.md).
