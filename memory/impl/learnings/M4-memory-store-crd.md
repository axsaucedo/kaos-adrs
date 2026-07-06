# M4 — memory store CRD and control plane — learnings

Deltas and decisions that emerged while building the MemoryStore CRD and wiring agents to it. These supersede the corresponding assumptions in the M4 plan where they differ and feed the later phases.

## Degraded-not-blocking memory binding

A memory outage must never remove an **already-running** agent from serving. The agent controller resolves a bound MemoryStore in `Reconcile`, but for an agent whose Deployment already exists an unresolved or not-ready store does not fail reconciliation or tear anything down: the agent stays Ready, `MEMORY_STORE_ENDPOINT` is simply omitted, and the runtime falls back to its pod-local short-term window. The condition surfaces as a `MemoryDegraded=True` entry in `status.conditions` (via `meta.SetStatusCondition`) with the store still recorded in `status.linkedResources.memorystore`. This keeps a memory outage from cascading into an agent outage and makes the degraded state observable without a separate probe.

The agent's **initial creation** is the one gated case. When `waitForDependencies` is set (the default) and the bound store is missing or not yet Ready, the controller checks whether the agent Deployment already exists (`agentDeploymentExists`); if it does not, it withholds creation, sets the Agent to `Waiting`, and requeues — mirroring the ModelAPI/MCPServer dependency gate so an agent never starts up degraded. The MemoryStore watch requeues the agent once the store turns Ready, after which the Deployment is created; from then on a disappearing store degrades rather than gates.

## Effective type is derived, but explicit type is kept

The agent memory `type` is optional and derived from `memoryStore` presence (remote when bound, local otherwise), but the field is retained for explicitness so an operator can assert `type: local` or `type: remote` and have the CEL rules enforce the matching shape (remote requires a store, local forbids one). The controller computes the effective type once and injects `MEMORY_STORE_ENDPOINT` only when the effective type is remote and the resolved endpoint is non-empty; `AGENT_IDENTITY` is always injected when a memory block is present.

## Readiness is store reachability, not model connectivity

The memory service `/readyz` probes only store reachability (short-term and long-term `.ping()`), because models bind lazily on first use. This is what lets a local-mode MemoryStore reach `Ready` in a KIND cluster with only a mock proxy ModelAPI — no real embedding or summarization backend is needed for the store to become ready and for an agent to bind. The reconciler still ready-gates on the referenced ModelAPIs existing and being Ready, so a store with a dangling model reference holds `Pending` rather than deploying a service that can never serve a real call.

## Model base URL comes from the summarization endpoint

The reconciler derives the service model base URL from the resolved summarization ModelAPI endpoint suffixed with `/v1`, and passes the summarization and embedding model names through as separate env. Both model references are required on the spec; there is no implicit default, which keeps the store's model wiring explicit and auditable.

## Threading the endpoint through construction

`constructEnvVars`/`constructDeployment` do not carry a client or context, so the resolved MemoryStore endpoint is computed in `Reconcile` and threaded as a plain `memoryEndpoint string` parameter through the construction call sites rather than re-resolving deeper in the stack. This keeps all cluster reads in the reconcile loop and the construction helpers pure.

## Helmify clobbers hand-maintained chart files

`make helm` regenerates `chart/values.yaml` destructively — it strips the hand-maintained `defaultImages` and `agentDefaults` blocks and introduces unrelated CRD/deployment drift from dependency bumps. The working practice is: run `make helm`, then `git checkout` the clobbered `values.yaml` and any unrelated CRD/deployment churn, and manually re-apply only the intended edits. `operator-configmap.yaml` and `values.yaml` are hand-maintained (they use `.Values` references) and are not helmify output. Chart CRDs live in `chart/crds/` (a Helm special directory that installs but is not rendered by `helm template`).

## Go toolchain pin

`operator/go.mod` requires `go 1.26.0` while the local toolchain is 1.25.1; operator Go builds and tests must run with `GOTOOLCHAIN=go1.26.0`, and a stale cache after the bump needs `go clean -cache`. This is an environment note, not a code change.

## Stacked-PR CI reality

The repo's e2e workflow triggers on PRs targeting `main`, but the M4 branch is stacked on the M3 branch, so e2e does not run automatically on the stacked PR. Local `make test-unit` plus `helm lint` are the green signal on the branch; the e2e suite runs when the stack rebases onto `main`, or on demand via workflow dispatch.
