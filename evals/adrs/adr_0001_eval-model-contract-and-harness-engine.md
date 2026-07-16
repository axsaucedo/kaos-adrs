# ADR 0001 — Eval model, contract, and harness engine

**Status**: Accepted

## Context

KAOS has no representation of an evaluation: no dataset/case type, no evaluator abstraction, no scoring or gate semantics, no result contract ([KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) gaps 1–6, 15–17). The ecosystem vocabulary is settled ([KAOS-E2](../research/KAOS-E2-agent-evals-ecosystem-research.md)): offline suites of cases scored by deterministic checks, budget metrics, and calibrated LLM judges, concluding in gateable verdicts with provenance. The selection ([KAOS-E6](../research/KAOS-E6-tool-selection.md)) adopted Pydantic Evals as the harness engine embedded behind a KAOS-owned contract, with the verified engine surface documented in [KAOS-E5-1](../research/KAOS-E5-1-pydantic-evals.md). This ADR fixes the eval model, the contract, the engine boundary, and the packaging.

## Decision

### The model: suite, case, evaluator, gates

An **EvalSuite** is the unit of declaration and versioning: cases plus suite-level evaluators plus gates, expressed as schema-validated YAML (or constructed programmatically). Suite identity is the SHA-256 content hash of its canonical serialization — there is no server-side dataset registry; suites live in Git or ConfigMaps and the hash in every result's provenance makes runs comparable and reproducible ([KAOS-E5-1](../research/KAOS-E5-1-pydantic-evals.md) confirms the engine has no versioning of its own).

A **case** carries: a stable `name`; `input` (a single user message, or an ordered list of user turns for scripted multi-turn conversations); optional `expected_output`; optional per-case evaluators; and free-form `metadata` for slicing (tags land here). Expected-trajectory declarations (required/forbidden tools, delegation bounds) are part of the model but ship with the trajectory evaluator seam (ADR [0002](./adr_0002_execution-model-and-runner.md)).

**Evaluators** are declared by `kind` plus config, and yield the engine's scoring model: an assertion (bool), a score (number), or a label (string), each with an optional reason. The committed first set: `contains`, `equals`, `regex`, `is_json` (deterministic); `max_duration`, token/cost budget checks (budget); `llm_judge` (rubric, judge model reference, include-input/expected options, structured verdict with reason). Custom code evaluators register through the library seam, not through YAML.

**Gates** turn scores into a machine-readable verdict: `minPassRate` over assertion evaluators, per-evaluator score `thresholds`, `criticalTags` whose case failures fail the run outright, and budget ceilings. The verdict is three-valued by failure kind: `Passed`, `Failed` (quality — gates not met), `Error` (the run could not produce a trustworthy verdict: infrastructure or harness failure). Candidate-agent errors on individual cases count as case failures (quality), not run errors, so a crashing agent fails its gate rather than voiding the run.

### The contract: KAOS-owned, engine-independent

A framework-independent Pydantic contract module defines: `EvalSuite`, `EvalCase`, `EvaluatorSpec`, `GateSpec`, `RunSpec` (target, concurrency, per-case timeout, repetitions), `CaseResult` (output, per-evaluator results with kind/value/reason, duration, usage, trace ID, error), `RunResult` (per-case results, aggregates, gate evaluation, verdict), and `Provenance` (suite hash, agent identity and generation, model endpoint and name, engine and contract versions, judge model and rubric versions, timestamps). This contract is the wire and storage format everywhere — CRD-adjacent, CLI output, results persistence — and engine types never leak above it: the harness maps `EvalSuite` onto the engine's `Dataset`/`Case`/`Evaluator` at the boundary and maps the engine report back into `RunResult` (the engine's `EvaluationReportAdapter.dump_json()` confirms lossless extraction is available — [KAOS-E5-1](../research/KAOS-E5-1-pydantic-evals.md)).

### Judge binding

`llm_judge` evaluators reference models exactly as the rest of KAOS does — `{modelAPI, model}` — resolved to an OpenAI-compatible base URL and injected into the engine as a pydantic-ai `OpenAIChatModel` over `OpenAIProvider(base_url=...)`. The engine's default judge model (a direct OpenAI reference) is never used: the harness requires an explicit judge model and fails closed if the reference does not resolve, preventing the silent-direct-to-OpenAI misconfiguration flagged in [KAOS-E5-1](../research/KAOS-E5-1-pydantic-evals.md). Judge prompt (rubric) text and the resolved judge model are recorded in provenance.

### Packaging

A new **`kaos-evals`** Python package mirrors the `kaos-memory` layout: the core carries the contract and the gate logic (no engine dependency); a `[runner]` extra adds Pydantic Evals, the harness mapping, and the target adapters (ADR [0002](./adr_0002_execution-model-and-runner.md)). Pydantic Evals is version-pinned; upgrades are deliberate ([KAOS-E5-1](../research/KAOS-E5-1-pydantic-evals.md) notes a fast-moving 2.x API).

### Suite YAML outline

```yaml
# eval-suite.yaml — schema-validated; identity = content hash
name: support-agent-regression
evaluators:                      # suite-level, applied to every case
  - kind: llm_judge
    rubric: "The response is helpful, grounded, and does not fabricate order data."
    judgeModel:
      modelAPI: my-modelapi
      model: gpt-4o-mini
cases:
  - name: order-status-happy-path
    input: "Where is my order 1234?"
    expected_output: "status lookup for order 1234"
    evaluators:
      - kind: contains
        value: "1234"
    metadata:
      tags: [orders, critical]
gates:
  minPassRate: 0.9
  criticalTags: [critical]
```

## Alternatives considered

- **Adopt DeepEval as the harness.** Deepest metric library, but library-only operation is the exception rather than the design centre: datasets/reports/tracing gravitate to the Confident AI SaaS, agentic metrics require its own `@observe` tracing stack parallel to KAOS OTel, and a current release carries an import-time global TracerProvider hijack risk ([KAOS-E5-2](../research/KAOS-E5-2-deepeval.md)). Rejected as engine; kept wrappable behind the evaluator seam.
- **Build a fully custom harness.** Maximum control, no third-party API churn — but reinvents dataset serialization, evaluator execution, concurrency/repetition/retry, and report assembly that Pydantic Evals already provides under MIT from the same authors as the runtime. Rejected as unjustified build cost; the KAOS contract already isolates the engine so a later swap stays possible.
- **Adopt a platform SDK idiom (Langfuse/Phoenix datasets and experiments) as the model.** Makes an external platform the source of truth for suites and results, coupling declaration and gating to a heavy optional dependency and its async pipeline ([KAOS-E5-3](../research/KAOS-E5-3-langfuse.md), [KAOS-E5-4](../research/KAOS-E5-4-arize-phoenix.md)). Rejected; platforms remain export sinks.
- **Expose the engine's types directly as the KAOS surface.** Least code, but pins the CRD/CLI/results format to a fast-moving third-party API and forecloses the engine swap. Rejected — the same boundary discipline that kept Mem0 behind the memory contract.
- **A server-side dataset registry with versioning.** Real capability, real service to operate; content-hash identity over Git/ConfigMap-resident suites delivers reproducibility without a new stateful component. Rejected for now; revisit if suite reuse across teams demands it.

## Consequences

- **Positive.** Evals get a stable, versioned, engine-independent contract from day one; judges are governed `ModelAPI` citizens; suites are reviewable Git artifacts with cryptographic identity; the engine can be upgraded or swapped without touching the CRD, CLI, or stored results.
- **Negative.** A mapping layer must be maintained against a fast-moving engine; the first evaluator set is deliberately small, so some ecosystem metrics (G-Eval variants, RAG metrics) arrive only through the custom-evaluator seam; content-hash identity means editing a suite creates a new identity rather than a lineage (lineage is metadata, not enforced).
- **Follow-on.** The trajectory evaluator over the OTel backend (ADR [0002](./adr_0002_execution-model-and-runner.md)); DeepEval metric wrapping as an optional extra; judge calibration tooling (rubric test sets) once real suites exist.
