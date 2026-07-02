# ADR 0005 — Multi-tenancy, agent grouping, and governance

- **Status.** Proposed
- **Date.** 2026-06-30
- **Component.** 5 of 5 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md), [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md), [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md), [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md), [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md), [KAOS-R7](../research/KAOS-R7-target-picture.md)
- **Constrains.** None; this is the final component and cross-cuts the data and control planes.

## Context

[ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) defines the scope-addressing model — a hierarchical segmented path anchored to the user principal and the agent's AIB `client_id`, with prefix-sharing and a configurable delegation-propagation rule. [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) injects that scope server-side at the `Memory` boundary and fails closed, while restricting the conversational short-term window and medium-term digest to the concrete session. [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md) makes the `MemoryStore` the coarse deployment and tenancy boundary and exposes memory server defaults alongside Agent-level client policy. This record settles what those leave open: how agents and users are grouped for sharing or isolation, how A2A-delegated sub-agents are placed into long-term scope, how conversational tiers avoid cross-session pollution, how isolation is enforced, how the memory endpoints are authenticated, and which governance features ship now versus later.

This component is broader than generic multi-tenancy because KAOS agents are first-class resources that delegate to one another, so "who can see which memory" is both a tenancy question and an agent-topology question. The delegation surfaces are `pydantic-ai-server/pais/serverutils.py` (`RemoteAgent`, `AgentDeps` carrying `principal`, `scopes`, `session_id`) and `pydantic-ai-server/pais/tools.py` (`DelegationToolset`, which today forwards only a slice of short-term-memory events to the delegate).

## Decision

### Grouping: a three-value scope, with the store as the group

Memory sharing is expressed by a single `scope` value on the Agent memory block, backed by the segmented scope path from [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md):

```yaml
memory:
  storeRef: shared-memory
  scope: user          # private | user | shared
```

- **`private`** — the agent's own memory, isolated to its `client_id`.
- **`user`** — shared across all agents serving the same user principal.
- **`shared`** — pooled across every agent on the same `MemoryStore`.

A logical group is **the set of agents on the same `MemoryStore`**: the store is the group. There is no separate group identifier or grouping CRD in this version, because store membership plus the three scope levels already express agent-private, per-user, and fleet-shared memory without an extra segment. The Agent `scope` governs only the long-term tier. The verbatim short-term window is session-scoped only in every case, and the medium-term rolling digest is also session-scoped because it is compaction of one conversation rather than a user-level narrative. Higher-scope short-term or medium-term context is rejected for this iteration because it would interleave concurrent sessions; cross-session continuity is provided by long-term Mem0 facts. Deeper named sub-groups within one store and any user-level narrative memory are deferred until they have an explicit non-polluting design.

### Scope and retention knobs across store and agent

Memory-policy knobs are surfaced both as `MemoryStore` server defaults and as Agent-level client parameters, as finalized in [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md). The shared set is `token_budget`, `high_water`, `low_water`, `hard_event_cap`, `digest_max_tokens`, `idle_ttl`, `sweep_interval`, `rolling_summary`, and `concurrency`, with the constraints `low_water < high_water <= token_budget`, `hard_event_cap >= 1`, positive TTL and sweep intervals, positive digest budget when rolling summary is enabled, and `concurrency >= 1`. This ADR's governance contribution is scoping: those knobs tune the session-scoped conversational tiers and background execution, while the Agent `scope` value controls long-term sharing. The control plane must not imply that setting `scope: user` creates a user-scoped short-term window or user-level medium-term digest.

### A2A delegation: inherit the prefix, isolated below

When an agent delegates to a sub-agent, the sub-agent inherits the delegator's scope prefix by default — shared above, isolated below — so it reads the shared context (for example the user or session prefix) while writing into its own agent segment. The inherited scope is injected server-side from the delegator's verified scope on the delegation call, never supplied by the model or the caller, extending the `DelegationToolset` path so it carries scope rather than only forwarding events. The default is configurable per agent to full sharing (the delegate operates under the delegator's exact scope) or full isolation (only the forwarded context crosses, with no shared long-term memory).

### Isolation modes: shared-by-default, physical isolation by deploying stores

The default isolation model is a **shared store with scope filtering**: one `MemoryStore` holds many users' and agents' memories in the same tables, separated only by the server-injected scope filter on every operation. **Physical store-per-tenant isolation is emergent**, not a separate mode: deploying one `MemoryStore` per tenant gives each tenant its own datastore, so a filtering defect cannot leak across tenants because the data is not co-located. No isolation-mode field is introduced; the isolation strength is chosen by how many stores are deployed, building directly on the store boundary from [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md).

### Enforcement: the service is the sole, fail-closed enforcement point

Scope filtering is non-optional at the data layer. Because Mem0's isolation is application-level filtering with no row-level security ([ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md)), the memory service is the single enforcement point: every recall, write, and erase carries the server-injected scope filter, no unscoped query path is exposed, and an operation that cannot resolve a trusted scope fails closed rather than querying an unfiltered store ([ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md)). Application-level enforcement is the whole mechanism in this version; Postgres row-level security on the KAOS-owned short-term table is recorded as a defense-in-depth hardening follow-up, noting that Mem0's own vector tables are managed by the engine and are not cleanly governed by row-level security.

### Authentication: the AIB identity is the single source of truth

Callers authenticate to the always-on memory endpoints with their AIB-issued agent identity — the same verifiable `client_id` that anchors scope in [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) — so authentication and scope derivation share one trusted source and scope is non-spoofable. Unauthenticated calls are rejected. Mutual TLS and Kubernetes NetworkPolicy are available as transport-layer hardening on top of identity-based authentication, not as the identity mechanism itself. This replaces the single shared admin key of the stock Mem0 server ([ADR 0004](./adr_0004_deployment-topology-and-control-plane.md)).

### Governance: a minimal core, with infrastructure and deferred tiers

The first-iteration governance set is deliberately small:

- **Core, shipped now.** Enforced scope isolation (above) and right-to-erasure by scope (below). Audit is not a new feature: the OpenTelemetry spans already emitted at the `Memory` boundary ([ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md)) carry the scope attribute, giving a per-operation, scope-tagged trail at no additional cost.
- **Infrastructure-provided.** Encryption at rest and backup or disaster recovery are delegated to the datastore layer — Postgres transparent encryption and managed backups, or PersistentVolume encryption and snapshots — documented as deployment requirements rather than built into the service.
- **Deferred.** Per-tenant quotas and fair-share enforcement (consistent with the capacity-bounded posture of [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md)), logical export and import by scope, and application-level field encryption.

### Erasure: a synchronous, scope-targeted fan-out

Right-to-erasure is a declarative, scope-targeted hard delete that fans out **synchronously** across all tiers that can contain the target's data: a delete on the session-scoped `short_term_memory_window` rows matching the affected sessions, a delete on `medium_term_memory_summaries` for those session scope keys, and a Mem0 `delete_all` filtered by the same trusted long-term scope. Because [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md) disables Mem0's local SQLite change-history log, there is no shadow copy left behind. Erasure is synchronous and best-effort because it is infrequent and correctness matters more than latency. Deletion-verification ledgers and proof-of-deletion, and logical export and import, are deferred.

## Consequences

- Grouping is expressed with one `scope` value and store membership, with no extra resource, keeping the first iteration simple while covering agent-private, per-user, and fleet-shared long-term memory.
- A2A sub-agents are placed into long-term scope by a server-injected, non-spoofable prefix that follows the delegation, with full-share and full-isolation overrides.
- The full isolation spectrum, from cheap shared filtering to physical per-tenant separation, is covered by one mechanism — how many stores are deployed.
- Isolation is enforced at a single fail-closed point with no unscoped path, accepting that application-level filtering is the trust boundary until row-level security is added.
- Authentication and scope share the AIB identity, so tenant separation cannot be spoofed through arguments.
- Governance ships a minimal, mostly free core, pushes encryption and backup to infrastructure, and defers the heavier features, matching the alpha stage.
- Erasure removes scoped memory across short-term, medium-term, and long-term storage in one synchronous operation with no lingering engine copy.
- The static-grouping trade-off below is an accepted limitation of this iteration, kept open for a later additive evolution.

## Alternatives considered

- **Higher-scope short-term or medium-term memory.** Rejected: a user-level or shared verbatim window would interleave concurrent sessions, and a user-level narrative digest would merge unrelated conversations without a clear provenance and conflict model. The accepted cross-session mechanism is long-term facts, with any future user-level narrative designed as a separate tier rather than by widening the session digest.
- **Dynamic groups through a membership-indirection layer.** Rejected for this iteration, recorded as the deferred evolution. Store-as-group is static: changing an agent's group means moving it to a different `MemoryStore`, and its existing memories stay in the old store rather than realigning, so dynamic regrouping requires a data migration. The root cause is write-time scope tagging, which a path-segment group would share — only an indirection layer fixes it, where memories are tagged solely with stable owner identity, a `MemoryGroup` resource defines mutable membership, and recall resolves a group to a set of owner scopes at query time so regrouping takes effect immediately. This is deferred because it adds a membership store and CRD, widens recall from a prefix match to a scope-set filter, and extends the control plane in [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md). It is safe to defer because [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) already stamps every item with owner anchors (principal and `client_id`) independent of the scope path, so a future group layer resolves membership over those anchors without re-tagging or migrating existing data — the static-grouping decision is additive, not a dead end.
- **A dedicated grouping CRD or label selector now.** Rejected: store membership plus the three scope levels already express the needed groupings, and a named-group resource is only warranted once dynamic membership is built.
- **A named group segment in the scope path.** Rejected: it adds a path dimension without delivering retroactive realignment, since past memories keep their old group tag; it offers the cost of more scope structure without the benefit of true dynamic groups.
- **Per-store shared-secret or admin-key authentication.** Rejected: a shared secret gives no per-agent identity and weak tenant separation; reusing the verifiable AIB identity unifies authentication with scope.
- **Engine-native isolation as the trust boundary.** Rejected: Mem0 offers only application-level filtering with no row-level security, so the service must be the enforcement point regardless.
- **A full governance suite in the first iteration.** Rejected: quotas, export and import, application-level encryption, and deletion-verification ledgers are deferred so the first iteration ships enforced isolation and erasure with audit riding existing telemetry.

## Follow-up

- Dynamic groups via a `MemoryGroup` membership layer with query-time scope-set resolution, added additively over the owner anchors guaranteed by [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md), if and when on-the-fly regrouping is required; this is the one evolution that would extend the [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md) control plane.
- Postgres row-level security on the KAOS-owned short-term table as defense-in-depth beneath the service-level enforcement.
- Per-tenant quota and fair-share enforcement, logical export and import by scope, application-level field encryption, deletion-verification, and any explicitly designed user-level narrative tier, as the governance set matures beyond alpha.
