# ADR 0004 — Component architecture and projection

- **Status.** Proposed
- **Date.** 2026-07-07
- **Component.** 4 of 4 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md), [ADR 0002](./adr_0002_identity-and-authentication.md), [ADR 0003](./adr_0003_authorization-models-and-policy-data.md)

## Context

KAOS today runs a **standalone sync-service** that projects agents, services, permission-sets, and credentials into the AIB admin API. It is a controller-runtime manager — the same framework as the operator — with a single whole-world sentinel reconciler (`cmd/main.go`, `internal/sync/reconciler.go`, `internal/projection/projection.go`, `internal/aib/client.go`), in its own Go module, using unstructured clients. This creates a split-brain: the sync-service mints and writes the per-agent credential Secret while the operator only mounts it, and the `kaos-aib-<name>` naming convention is duplicated across both modules. With [ADR 0003](./adr_0003_authorization-models-and-policy-data.md) adding a Model-1 data emitter and manual override modes, this ADR settles where that logic lives and how it is structured.

## Decision

### Fold the sync-service into the operator

The sync-service is **folded into the operator** as a whole-world projection controller. It is already a controller-runtime manager, so folding relocates the essential logic (projection plus AIB admin client) and deletes a large amount of incidental complexity: a separate deployable, Helm chart, container image, CI job, second leader election, and second informer cache over the same three CRDs. The operator gains typed CRD inputs in place of unstructured clients and becomes the single owner of the credential-Secret lifecycle, ending the split-brain. The one real cost is that the operator gains a dependency on the AIB admin API; this is contained by making projection a **separate controller** with its own requeue and backoff (below).

### Two controllers, isolated failure domains

The operator runs **two independent controllers in one manager**:

- The **workload reconciler** (Agent, MCPServer, ModelAPI) manages Deployments, Services, Gateway resources, and the ext_proc `EnvoyExtensionPolicy`. It **never calls AIB**.
- The **projection reconciler** (whole-world sentinel) is the **sole** caller of the AIB admin API, the **sole** writer of the Model-1 policy-data ConfigMap, and the **sole** minter of credential Secrets.

If the broker is down, only the projection reconciler requeues with backoff; workloads keep reconciling and health probes stay green. The only felt impact is that new agents lack a credential Secret until the broker returns (the actor-token module stays inert or fail-closed until the Secret appears); existing agents are unaffected.

### Shared projection core, thin per-model adapters

The pure function `Project(resources) → DesiredState` is the **shared core** for both models — a model-agnostic grant graph built from typed CRDs. AIB-specific serialisation (`AdminBody()`) is stripped off the `DesiredState` types into the Model-2 adapter, so:

- The **Model-2 adapter** (AIB admin client, request payloads, and prune) is the **only bespoke integration code**.
- The **Model-1 adapter** is a pure serialisation step: it renders `DesiredState → data.json` and writes it into a ConfigMap using the operator's existing Kubernetes client — no external integration. The generic static rego ([ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md)) ships as an asset; the operator writes **data only**, plus `data.kaos.jwks` when verification is enabled ([ADR 0002](./adr_0002_identity-and-authentication.md)).

This keeps custom code confined to the AIB admin surface, exactly as intended.

### Prune and garbage collection

Cleanup uses a **whole-world sentinel sweep** for AIB records (services, permission-sets, agents) plus **owner-reference GC** for per-agent credential Secrets (`ownerReference: Secret → Agent`), which replaces the bespoke `pruneSecrets()` code. A per-Agent finalizer for AIB records is rejected: the synthetic services and permission-sets are **shared** across agents, so finalizer deletion would need reference-counting and race handling, whereas the whole-world sweep is simpler and self-heals drift. Credential Secrets are per-agent (not shared), so owner-reference GC is safe. All prune is **mode-gated** per the prune-safety invariant in [ADR 0003](./adr_0003_authorization-models-and-policy-data.md): external and manual modes never prune.

### Data delivery and reload posture

Model-1 data is delivered as a **ConfigMap mounted into the AIB ext_proc pod**, with OPA using `policy.path` (static, compile-once). A data change therefore restarts the ext_proc pod; this is the simplest correct posture to start. **ConfigMap-as-local-bundle hot-reload** (`policy.config_file`) is a later enhancement gated on a spike against #222; the rego stays static in either case and only `data.json` is regenerated. Wiring the ext_proc OPA on (policy path, package, decision) is done through the PR #397 chart values.

### Security-config decoupling

Removing the AIB-#398 assumption requires decoupling the operator's "security enabled" predicate from `ExtAuthzURL`. Today `IsOperational() == (ExtAuthzURL != "")` also gates credential mounting and the NetworkPolicy, so dropping the ext_authz default would silently switch those off. A broader **"security enabled"** predicate is introduced so credentials and NetworkPolicy stay on independently of the (now optional, default-off) ext_authz seam.

## Consequences

Positive: one binary with typed inputs replaces a second manager and its whole deployment surface; custom code shrinks to the AIB admin adapter while Model 1 is pure serialisation; two-controller isolation means a broker outage never stalls workload reconciliation; whole-world sweep plus owner-reference GC is simpler than finalizer reference-counting and self-heals drift. Negative: the operator takes on an external dependency on the AIB admin API (contained but real); the static `policy.path` posture restarts ext_proc on Model-1 data changes until bundle hot-reload lands; decoupling the security predicate touches config paths that currently double as the ext_authz switch and must be changed carefully. Follow-on: the bundle-hot-reload spike, and the AIB-less standalone path (KAOS-run OPA plus AIB-less issuer) tracked in [followups](../plan/followups.md).

## Alternatives considered

Keep the sync-service as a separate deployable — rejected: it duplicates the manager, chart, image, CI, and the credential-Secret contract for no benefit now that Model 1 also needs operator-side emission. Per-Agent finalizer for AIB prune — rejected: shared synthetic records need reference-counting; whole-world sweep is simpler and self-healing. Fold everything into one reconciler — rejected: mixing AIB calls into the workload reconciler would let a broker outage stall Deployment reconciliation. Bundle-server data delivery from day one — deferred: adds a deployment; ConfigMap plus `policy.path` is correct and simplest to start.
