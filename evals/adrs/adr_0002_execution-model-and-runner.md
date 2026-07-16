# ADR 0002 — Execution model and runner

**Status**: Accepted

## Context

An eval must run a declared suite against a target agent N times with isolation, bounded concurrency, timeouts, and repetition, then score, gate, persist, and report — none of which KAOS can express ([KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) gaps 3, 10–14, 19). The target picture ([KAOS-E7](../research/KAOS-E7-target-picture.md)) commits to evaluating the *deployed* agent through its serving surfaces, with the trace as the canonical trajectory. The engine's span-tree assertions are strictly in-process and cannot see a remote agent's spans ([KAOS-E5-1](../research/KAOS-E5-1-pydantic-evals.md)), which forces an explicit decision about trajectory evaluation. This ADR fixes the runner shape, the target adapters, isolation and failure semantics, results persistence, and the online-evaluation deferral line.

## Decision

### Runner shape: a finite Job workload, not a service

Each eval run executes as a **single finite runner process** packaged as a container image (built by the existing image pipeline) and launched as a Kubernetes **Job** by the operator (ADR [0003](./adr_0003_control-plane-eval-crd-operator-and-cli.md)) — or directly on a developer machine, since the runner is a plain CLI entrypoint over the `kaos-evals[runner]` library. The runner: loads and hash-verifies the suite, resolves the target and judge endpoints from its environment, maps the suite onto the engine, executes cases with the engine's concurrency and repetition controls, computes gates, writes results, and exits with a verdict-encoding exit code. There is no long-running eval service: runs are finite, state lives in the results artifact and CRD status, and a central service earns its existence only when shared query APIs or online scoring arrive ([KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) requirements close reaches the same shape).

### Target adapters

The harness task function is a **target adapter** behind one interface, selected by run configuration:

- **`http` (primary).** Invokes a deployed agent through its OpenAI-compatible chat surface at the in-cluster service DNS (`agent-<name>.<ns>.svc`), exactly as real callers do — so the scored behaviour includes the agent's ModelAPI, MCP tools, memory binding, and delegation. Multi-turn cases replay scripted user turns over one session.
- **`local` (development parity).** Runs the suite against an in-process `AgentServer` or any OpenAI-compatible URL, so suite authors iterate without a cluster; identical contract, identical results schema ([KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) gap 19).
- **`a2a` (later).** Asynchronous task-based invocation for long-running agents; the adapter seam is designed for it but it is not in the first delivery.

Every adapter returns the same envelope per case: output text, duration, usage where available, the propagated **trace ID**, and a typed error on failure.

### Isolation, budgets, and failure kinds

Each case runs in a **fresh session** (unique session ID per case and per repetition), so short-term memory and conversation state never bleed across cases; cases assuming shared state must script it as multi-turn input. The runner enforces a **per-case timeout** KAOS-side (the engine has none — [KAOS-E5-1](../research/KAOS-E5-1-pydantic-evals.md)) and bounded concurrency; repetitions re-run the full case set for flake detection. Failure kinds are held apart end to end: a case whose agent call errors or times out is a **case failure** scored against gates; an evaluator that cannot execute (judge unreachable, malformed verdict after retry) marks the affected results **inconclusive** and the run `Error` unless gates can still be decided without them; runner/infrastructure failure is always run `Error`, never a quality verdict.

### Results persistence

Two artifacts per run, both in the contract schema of ADR [0001](./adr_0001_eval-model-contract-and-harness-engine.md):

- **Summary → CRD status**: verdict, aggregates (pass rate, per-evaluator averages, duration/usage totals), gate evaluation, provenance digest — small and bounded.
- **Full report → a per-run ConfigMap** (`<eval>-results-<runUID>`, owner-referenced to the eval resource, subject to retention): every case with outputs, per-evaluator values and reasons, errors, and trace IDs. The runner truncates oversized case outputs deterministically (recorded as truncated) to respect the ConfigMap 1 MiB bound; suites that outgrow it are the trigger for the recorded follow-up (an object-store/PVC sink or a results service), not a reason to build one now.

Trace IDs per case are recorded from day one, so remote-trajectory evaluation and platform export can land later **without re-running suites**.

### Trajectory evaluation seam

Because in-process span capture cannot observe a remote agent, trajectory evaluators against deployed agents are defined as a **KAOS-built evaluator kind that queries the OTel backend by the case's recorded trace ID** (required/forbidden tool spans, delegation hops, span-attribute predicates). The seam — trace-ID capture, evaluator kind, backend query interface — is part of this design; the implementation is a follow-on and is not on the first delivery's critical path. For `local` targets the engine's native `HasMatchingSpan`/span-tree evaluators work today and are exposed through the same evaluator declaration.

### Observability and export

The runner emits OTel spans under the existing `kaos.*` conventions (one span per run, one per case, child spans per evaluator) and attaches scores using the OTel GenAI evaluation vocabulary (`gen_ai.evaluation.result` — [KAOS-E2](../research/KAOS-E2-agent-evals-ecosystem-research.md)), so Grafana/Langfuse/Phoenix render eval outcomes without bespoke adapters. Pushing results to platform APIs (Langfuse scores/dataset-runs, Phoenix span annotations) is an **optional exporter seam** on the runner, never load-bearing ([KAOS-E5-3](../research/KAOS-E5-3-langfuse.md), [KAOS-E5-4](../research/KAOS-E5-4-arize-phoenix.md)).

### Online evaluation: deferred

Online (production-trace) scoring is an asynchronous worker that samples completed traces and applies reference-free evaluators, emitting evaluation events linked to source traces — designed in the target picture, deliberately **not** built until the offline capability is landed and used. The offline contract anticipates it: evaluator declarations are target-agnostic, and scores already speak the OTel evaluation vocabulary.

## Alternatives considered

- **A long-running eval service executing runs.** Matches the MemoryStore topology but is the wrong shape for finite work: it would hold run state, need its own queue and HA story, and idle between runs. Jobs give versioned, garbage-collectable, horizontally-independent runs with the operator's existing watch machinery. Rejected; a service may still arrive later for shared result queries and online scoring.
- **Re-instantiating the agent inside the runner (in-process evaluation as primary).** Gives full span access and no network, but evaluates a *copy* — not the deployed pod, its image, env, tools, or memory — and drifts from what serves. Rejected as primary; kept as the `local` adapter for development.
- **Sidecar runner in the agent pod.** Co-locates traffic but couples eval lifecycle to serving pods, perturbs the workload under test, and multiplies images. Rejected.
- **Results in the telemetry backend only.** Traces are operational exhaust with retention and sampling policies; gating and comparison need durable, queryable, schema-stable results the control plane owns ([KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) gap 5). Rejected as canonical store; traces remain the trajectory record.
- **Results in a platform (Langfuse/Phoenix) as canonical.** Couples CRD verdicts to a heavy optional dependency's async pipeline; both deep dives recommend against it ([KAOS-E5-3](../research/KAOS-E5-3-langfuse.md)). Rejected; export seam only.
- **PVC or object store for full reports now.** More capacity than ConfigMaps, but adds storage provisioning to every eval and an S3 dependency KAOS does not otherwise have. Rejected for alpha; recorded as the upgrade path when report sizes demand it.

## Consequences

- **Positive.** What is scored is what serves; runs are finite, reproducible, and cheap to operate; developers run the identical harness locally; trace-ID capture future-proofs trajectory evaluation and platform export; failure kinds keep verdicts honest.
- **Negative.** Full remote-trajectory assertions are not available on day one (seam only); ConfigMap-bound reports cap very large suites until the storage follow-up; per-case HTTP invocation makes eval load visible to the serving agent (mitigated by concurrency bounds — and it is honest load).
- **Follow-on.** The OTel-backend trajectory evaluator; the A2A adapter; the object-store results sink; the online scoring worker; Langfuse/Phoenix exporters.
