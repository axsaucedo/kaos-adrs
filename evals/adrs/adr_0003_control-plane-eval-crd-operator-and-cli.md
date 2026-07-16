# ADR 0003 — Control plane: AgentEval CRD, operator reconciliation, and CLI

**Status**: Accepted

## Context

KAOS has no declarative evaluation resource, no finite-workload controller, no scheduled/regression execution, and no eval CLI ([KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) gaps 7–9, 18). The operator's established patterns — the MemoryStore controller reconciling a CRD into workloads with owner references and conditions, `{modelAPI, model}` reference resolution, `defaultImages` image selection, fail-closed dependency gating — are the templates to extend, not greenfield ([KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) reusable-pattern inventory). This ADR fixes the CRD shape, the reconciliation contract, and the CLI surface for the runner and contract decided in ADRs [0001](./adr_0001_eval-model-contract-and-harness-engine.md) and [0002](./adr_0002_execution-model-and-runner.md).

## Decision

### One CRD: `AgentEval`

A single namespaced resource, **`AgentEval`**, declares an evaluation of one target Agent. Applying it runs it once; re-runs and recurring runs are expressed on the same resource. There is no separate suite/run resource pair: the suite is data (inline or a ConfigMap reference), each execution is a Job plus a results artifact — Kubernetes-native run records — and status reports the latest run with prior results retained by the retention policy. The name pairs with `Agent` the way `MemoryStore` pairs with memory, and stays open for a later fleet-selector evolution.

### Spec outline

```yaml
apiVersion: kaos.tools/v1alpha1
kind: AgentEval
metadata:
  name: support-regression
  namespace: my-namespace
spec:
  # Required: the deployed Agent under evaluation (same namespace)
  agentRef:
    name: support-agent

  # Required: the suite — exactly one of inline | configMapRef
  suite:
    inline:                      # contract-schema suite (ADR 0001)
      evaluators:
        - kind: llm_judge
          rubric: "Helpful, grounded, no fabricated order data."
          judgeModel:
            modelAPI: my-modelapi
            model: gpt-4o-mini
      cases:
        - name: order-status-happy-path
          input: "Where is my order 1234?"
          evaluators:
            - kind: contains
              value: "1234"
      gates:
        minPassRate: 0.9
    # configMapRef: {name: support-suite, key: suite.yaml}

  # Optional run settings (defaults shown)
  run:
    concurrency: 4
    caseTimeoutSeconds: 120
    repetitions: 1

  # Optional: recurring execution (standard cron); absent = run once on apply
  # schedule: "0 6 * * *"

  # Optional: how many completed run results (Jobs + result ConfigMaps) to keep
  retention:
    runs: 5
```

Judge models are `{modelAPI, model}` references resolved by the controller exactly as MemoryStore resolves its model roles; the suite's schema is validated at admission (inline) or at reconcile (ConfigMap), and the controller records the suite content hash in status.

### Status contract

```yaml
status:
  phase: Pending | Running | Passed | Failed | Error
  ready: false
  suiteHash: "sha256:…"
  lastRun:
    startedAt: …
    completedAt: …
    verdict: Passed | Failed | Error
    passRate: 0.93
    casesTotal: 30
    casesPassed: 28
    resultsRef: {name: support-regression-results-<runUID>}   # full report ConfigMap
  conditions: [...]              # DependenciesReady, SuiteValid, JobComplete, …
  message: "28/30 cases passed; gate minPassRate=0.9 met"
```

`Passed`/`Failed` are quality verdicts from gates; `Error` means no trustworthy verdict (ADR [0002](./adr_0002_execution-model-and-runner.md) failure kinds). The full per-case report lives in the owner-referenced results ConfigMap named by `resultsRef` — status stays bounded.

### Reconciliation contract

The controller (MemoryStore controller as the template): validates fail-closed before launching (target Agent exists and is Ready, judge `ModelAPI`s Ready, suite resolves and validates — otherwise `Pending` with a precise condition, never a half-run); materializes one **Job** per run — runner image from `defaultImages`, suite mounted or inlined via env/volume, target service DNS, resolved judge base URLs, and OTel endpoint injected as environment; watches the Job, parses the runner's summary, and projects it into status; enforces `retention` by garbage-collecting oldest run Jobs and result ConfigMaps; on `schedule`, launches runs on the cron cadence (implemented as controller-managed re-runs so status/retention semantics stay uniform, rather than a fire-and-forget CronJob the controller cannot gate); on suite or spec change, the next run picks up the new content hash. A re-run without editing the spec is requested through a `kaos.tools/rerun` annotation bump (what the CLI uses). RBAC additions, CRD manifests, and the runner image tag ride the existing `make generate manifests` and Helm chart wiring.

Change-triggered runs (re-run when the target Agent's generation changes) are **deferred**: the trigger surface is an opt-in field recorded for later, avoiding surprise eval load on every agent edit while the capability is young.

### CLI surface

`kaos eval` verbs, thin over the CRD and results artifacts, with machine-readable output and CI exit semantics ([KAOS-E1](../research/KAOS-E1-evaluation-features-and-limitations.md) gap 18): `run` (apply/annotate and optionally `--wait`, exiting 0/1/2 for Passed/Failed/Error), `list`, `show` (per-case drill-down from the results ConfigMap, `-o json`), `delete`. `compare` (two runs' reports) and `export` are follow-ons. Samples ship one worked example — a mock-model Agent plus an `AgentEval` with deterministic evaluators — following the executable-docs pattern, CI-runnable without a live LLM; a judge-based variant documents the `ModelAPI` path.

## Alternatives considered

- **A suite/run resource pair (`EvalSuite` + `EvalRun`).** Cleaner run history as first-class objects and suites shared across evals, at the cost of two CRDs, cross-resource lifecycle, and a registry-shaped surface before any user needs it. Rejected for now; the single CRD plus Job/ConfigMap run records covers the walkthroughs, and the pair remains a compatible evolution (an `AgentEval` could later reference an `EvalSuite`).
- **`kaos eval` as a purely client-side harness (no CRD).** Fastest to ship and fine for laptops, but nothing is declarative: no scheduled regression, no in-cluster verdict, no status for GitOps, contradicting how every other KAOS capability is operated. Rejected as the primary; the runner's `local` mode already gives the client-side path.
- **CronJob resources for schedules.** Native cadence but the controller loses gating, status projection, and retention uniformity over what actually ran. Rejected in favour of controller-managed scheduling.
- **Verdict computed by the controller from raw results.** Would put gate logic in Go and duplicate the contract; instead the runner (which owns the contract) concludes, and the controller projects. Decided as stated.
- **Storing full reports in status.** Unbounded status objects hammer etcd and watch streams. Rejected; summary in status, report in the owner-referenced ConfigMap (ADR [0002](./adr_0002_execution-model-and-runner.md)).

## Consequences

- **Positive.** Evals become declarative, GitOps-able resources with fail-closed dependency checking, bounded status, uniform retention, and a CI-consumable CLI; every mechanism reuses a proven operator pattern, keeping the controller thin.
- **Negative.** Run history is Kubernetes-object-shaped (Jobs + ConfigMaps under retention) rather than a queryable store — comparison across many runs stays CLI/artifact-level until a results service is justified; a single CRD means suites are not shareable as cluster objects yet.
- **Follow-on.** `compare`/`export` verbs; the `EvalSuite` extraction if sharing demands it; change-triggered runs; fleet selectors; results-service evaluation alongside the online-scoring worker (ADR [0002](./adr_0002_execution-model-and-runner.md)).
