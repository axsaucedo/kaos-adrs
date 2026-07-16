# KAOS evals ADRs — high-level components

This document opens the architecture-decision phase for KAOS evals. The research stages ([KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) through [KAOS-E7](../research/KAOS-E7-target-picture.md)) established the current surface and its gaps, the ecosystem vocabulary, the tooling landscape, a selection, and an unrestricted target picture. This document decomposes that picture into the **high-level components that each require an architecture decision record (ADR)**, so the design work can proceed component by component.

The intent here is deliberately *coarse*. The components below are bundled rather than finely segregated: each one groups a set of closely-coupled decisions that are best made together, so the ADR set stays small and coherent instead of fragmenting into many narrow records. Three components cover the full target surface.

## How this relates to the research

The components are derived directly from the target picture in [KAOS-E7](../research/KAOS-E7-target-picture.md), grounded in the requirements baseline [KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) and the ecosystem vocabulary [KAOS-E2](../research/KAOS-E2-agent-evals-ecosystem-research.md), and constrained by the selection in [KAOS-E6](../research/KAOS-E6-tool-selection.md). Where an ADR weighs an option, the per-tool deep dives ([KAOS-E5-1](../research/KAOS-E5-1-pydantic-evals.md) through [KAOS-E5-4](../research/KAOS-E5-4-arize-phoenix.md)) are the evidence base. ADRs decide; they do not re-litigate the research. Each ADR records what was chosen, why, and the consequences, citing the research rather than repeating it.

The research remit was *informed but not constrained* by the available tooling. The ADRs are the opposite: they reconcile the unrestricted target with what is buildable and adoptable now, producing concrete, committed decisions with a status lifecycle.

## Components requiring an ADR

### 1. Eval model, contract, and harness engine

- **Scope.** What an eval *is* in KAOS and what implements it: the suite/case/evaluator/gate model and its serialized form (schema-validated YAML, content-hash identity); the framework-independent Pydantic contract that keeps the engine swappable (suite, run spec, per-case result, evaluator result, aggregate, verdict, provenance envelope); the adoption of Pydantic Evals as the embedded harness engine and the exact build-versus-adopt boundary; the evaluator taxonomy (deterministic checks, budget metrics, LLM-as-judge, trajectory, custom code) and which ship first; judge-model binding through `{modelAPI, model}` references; and the packaging shape (a `kaos-evals` library mirroring `kaos-memory`'s contract/extras layout).
- **Key decisions.** The contract schema and its stability guarantees; how KAOS types map onto engine types at the harness boundary (and never leak upward); the gate semantics (required evaluators, thresholds, pass rate, critical tags, budget ceilings) and the failure-kind taxonomy (quality failure vs candidate error vs infrastructure error); dataset identity and provenance fields; which built-in evaluators are wrapped vs KAOS-authored.
- **Primary inputs.** [KAOS-E6](../research/KAOS-E6-tool-selection.md) selection and boundary; [KAOS-E5-1](../research/KAOS-E5-1-pydantic-evals.md) verified engine APIs; [KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) gaps 1–6, 15–17; [KAOS-E2](../research/KAOS-E2-agent-evals-ecosystem-research.md) evaluator and judge-calibration vocabulary.
- **Dependencies.** The foundation: defines what the runner (component 2) executes and what the control plane (component 3) declares and reports.

### 2. Execution model and runner

- **Scope.** How an eval actually runs against a target: the runner workload (a finite, containerized process launched per run) and its lifecycle; target adapters that invoke the *deployed* agent through its existing surfaces (OpenAI-compatible chat as the primary path, A2A later) plus an in-process/local adapter for development parity; per-case session isolation, timeout, bounded concurrency, and repetition; trace-ID capture per case and the trajectory-evaluation seam over the OTel backend; where results persist durably (status summary vs full per-case report) and how large results are bounded; and the deferral line for online (production-trace) evaluation and platform exporters.
- **Key decisions.** The runner-as-Job execution shape versus a long-running eval service; the results persistence mechanism for alpha and its upgrade path; how the runner reaches agents in-cluster (service DNS vs gateway) and authenticates; what the runner records so remote-trajectory evaluation can land later without re-running suites; the failure/retry contract per case and per run.
- **Primary inputs.** [KAOS-E7](../research/KAOS-E7-target-picture.md) execution model; [KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) gaps 3, 10–14, 19; [KAOS-E5-1](../research/KAOS-E5-1-pydantic-evals.md) in-process span-capture limitation; [KAOS-E5-3](../research/KAOS-E5-3-langfuse.md)/[KAOS-E5-4](../research/KAOS-E5-4-arize-phoenix.md) platform-seam evidence.
- **Dependencies.** Executes the contract from component 1; is what the control plane (component 3) schedules and observes.

### 3. Control plane: eval CRD, operator reconciliation, and CLI

- **Scope.** The declarative surface and its operation: the new eval CRD (target Agent reference, suite inline or by reference, evaluator/judge configuration, run settings, gates, schedule, retention, optional export sink) and its status contract (phase, progress, conditions, verdict, aggregates, results pointer); the operator controller that validates references fail-closed, materializes runner Jobs with `defaultImages` image selection, watches completion, surfaces status, enforces retention, and handles re-runs and scheduled runs; RBAC, Helm chart, and CRD manifest wiring; and the `kaos eval` CLI verbs with CI-consumable exit semantics, plus the sample and worked-example surface.
- **Key decisions.** One CRD versus a suite/run resource pair; the CRD name and schema; how re-runs are expressed (new resource, annotation trigger, or schedule); status size discipline and the results pointer; scheduling (cron field) and change-triggered runs now versus deferred; which CLI verbs ship first; namespace/tenancy boundaries for suites and results.
- **Primary inputs.** [KAOS-E7](../research/KAOS-E7-target-picture.md) control plane; [KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) gaps 7–9, 18, 20 and its reusable-pattern inventory (MemoryStore controller, `ModelAPI` references, `defaultImages`, install flags); the MemoryStore CRD as the structural template.
- **Dependencies.** Declares and operates components 1 and 2; last in authoring order.

## Cross-cutting concerns

These are not separate components; each ADR addresses them within its own scope.

- **Observability.** Runs and cases emit OTel spans under the existing `kaos.*` conventions; scores adopt the OTel GenAI evaluation vocabulary (`gen_ai.evaluation.result`) so external backends render them without adapters ([KAOS-E2](../research/KAOS-E2-agent-evals-ecosystem-research.md)). Component 2 fixes the instrumentation boundary.
- **Compatibility.** Evals are a purely additive capability — no existing surface is redesigned — so there is no clean-break question; the discipline is that the eval contract itself is versioned from the start.
- **Security defaults.** Suites, reference outputs, and captured candidate outputs are namespace-scoped and treated as sensitive; judge credentials ride existing `ModelAPI` secret handling; no eval surface widens agent access ([KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) gap 20).

## Dependency and sequencing

Component 1 defines what an eval is and what implements it; component 2 decides how it executes and where results live; component 3 makes it declarative and operable. The recommended authoring order is 1, 2, 3 — with the cross-cutting concerns settled inside each.

## ADR conventions

- **Filename.** ADRs use `adr_NNNN_<slug>.md` with a zero-padded sequence number and a short kebab-case slug. This index uses the descriptive name `adr_high_level_components.md` and is not itself a numbered decision.
- **Status lifecycle.** Each ADR carries a status: `Proposed`, `Accepted`, `Superseded` (by a named later ADR), or `Deprecated`. Superseding never edits the original record; it adds a new one and updates the status.
- **Structure.** Each ADR follows a consistent shape: title and status; context (the problem and the relevant research, cited); the decision; consequences (positive, negative, and follow-on work); and alternatives considered with the reason each was not chosen.
- **Authoring style.** ADRs follow the track [CONVENTIONS](../CONVENTIONS.md): single-line paragraphs and list items, Markdown links for cross-references, repository-relative paths for KAOS source, and no references to phases, tasks, or plan steps in the document body.
