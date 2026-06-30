# ADR 0004 — Deployment topology, execution model, and control plane

- **Status.** Proposed
- **Date.** 2026-06-30
- **Component.** 4 of 5 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md), [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md), [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md), [KAOS-R5-1](../research/KAOS-R5-1-mem0.md), [KAOS-R7](../research/KAOS-R7-target-picture.md), [KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md), [KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)
- **Constrains.** ADR 0005 (multi-tenancy and grouping).

## Context

[ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md) selects Mem0 as the long-term engine and [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) fixes the runtime contract — the tiered `Memory` abstraction, the working tier on a plain relational store, the synchronous-recall/asynchronous-write split, and server-side scope injection. Both records defer how memory is run and operated to this one. This ADR decides the deployment topology, the background execution model, the high-availability and degradation posture, and the control plane — the `MemoryStore` CRD, the slim Agent memory block, and the operator's responsibilities.

The current control surface is an inline `MemoryConfig` on `AgentSpec.Config.Memory` describing only working memory (`enabled`, `type: local|redis`, `contextLimit`, `maxSessions`, `maxSessionEvents`). There is no resource describing a long-term backend, and the runtime has no dedicated background-job system beyond the autonomous-loop `asyncio` tasks in the data plane ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)). Because KAOS is in alpha this surface is redesigned rather than preserved, consistent with [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md). Source surfaces: `operator/api/v1alpha1/agent_types.go`, `operator/controllers/agent_controller.go`, `pydantic-ai-server/pais/memory.py`, `pydantic-ai-server/pais/a2a.py`.

A determining finding from [KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md): the stock Mem0 REST server is long-term-only (`/memories`, `/search`, `/configure`), authenticates with a single shared admin key, rate-limits by client IP, and has no working tier, rolling summary, KAOS tenant scoping, or KAOS-format telemetry. KAOS therefore reuses Mem0 as a library inside its own service rather than running that server.

## Decision

### A single central memory service, built around Mem0 as a library

The long-term engine runs as **one central memory service** that all agents call over the network, not as a library embedded in each agent process and not as a per-agent sidecar. The service is a thin KAOS-owned component that imports Mem0 as a library and wraps it with the [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) contract — the working tier, rolling summary, recall presentation, server-side scope injection, and OpenTelemetry. The stock Mem0 server is not used because it provides none of these ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)).

The embedded-in-agent alternative is rejected as a supported path: it pushes LLM-gated extraction onto the serving process, multiplies datastore connections, ships the engine and its vector dependencies into every agent image, and — with a per-pod local store — diverges memory across an agent's replicas. A single shared service is cheap, keeps agents thin, isolates extraction, and preserves cross-agent sharing, which the cross-agent and organizational memory capability in [KAOS-R7](../research/KAOS-R7-target-picture.md) requires. The "no separate pod" and "no network hop" gains of embedding are marginal against LLM-dominated turn latency.

### Storage: a local and an external mode, one provider each today

The memory service stores both tiers through a single storage selection, mirroring the existing `ModelAPI` mode-plus-config pattern:

```yaml
storage:
  type: local                 # local | external
  local:
    provider: chroma          # only provider today; the field is extensible
    persistentVolume: { size: 10Gi }
  # external:
  #   provider: pgvector      # only provider today; the field is extensible
  #   connectionSecretRef: { name: memory-postgres, key: dsn }
```

`storage.type` selects where state lives and governs **both** tiers; the per-tier backend is not separately configurable:

- **`local`** — the service runs everything in a single container with no external dependency: Mem0 with an embedded Chroma persistent store for long-term and a SQLite table for the working tier, both on one PersistentVolume. It is the least-effort on-ramp for development and small single-store deployments. It pins to a single replica because the embedded store is a single-writer file.
- **`external`** — long-term is pgvector and the working tier is a plain table on the **same** external Postgres instance ([ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md), [KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)). The service is stateless and runs `replicas: 2+` for high availability. It is the production path.

Both modes expose one `provider` value today and are structured so a future contributor can add a provider without reshaping the CRD, consistent with the engine-agnostic direction in [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md). The vector provider is chosen for correct pre-filtered multi-tenant recall: both Chroma and pgvector apply the scope filter during the vector query, whereas a post-filtering store would discard a tenant's relevant memories that fall outside an unfiltered nearest-neighbour window — unacceptable for the shared, multi-owner index this service holds.

### Background execution: in-process, fire-and-forget, no queue

The asynchronous operations from [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) — write/extract, consolidate, forget — run as **in-process background tasks inside the memory service**, off the recall hot path, bounded by a concurrency setting:

```yaml
extraction:
  concurrency: 4              # max simultaneous background extractions per replica
```

There is no durable job queue in this version. Mem0 provides none ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)), a single write is a one-LLM-call unit of work rather than a long job, and the raw turn is already durable in the working tier, so a lost in-flight extraction is re-derivable. A crash therefore loses at most the pending extractions of one replica, with no loss of conversational state. A durable at-least-once queue is recorded as a follow-up to adopt only when write durability becomes a hard requirement; it is deliberately not built now.

### High availability and the Mem0 statefulness caveat

In `external` mode the service is **stateless**: all durable state is the shared Postgres (pgvector plus the working table), so high availability is `replicas: 2+` behind a Kubernetes `Service` with no sticky sessions. Mem0's only node-local state is its SQLite change-history audit log ([KAOS-R5-1](../research/KAOS-R5-1-mem0.md)); it is not memory data, KAOS does not consume it, and it is disabled or ignored, so it does not impede horizontal scaling. In `local` mode the embedded store is a single-writer file and the service is intentionally single-replica; availability there is the dev-grade trade-off for zero external dependencies.

### Degradation contract: memory is augmentation, not a hard dependency

A memory outage degrades agents but never stops them ([ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) recall is augmentation):

- **Recall failure** returns working-memory-only context and emits a degraded span; the turn completes.
- **Long-term write failure** is retried in the background; it never blocks the response.
- **Store unavailable when an Agent first binds** marks the Agent **not Ready** so the condition is visible to the operator and user, but the agent still starts and serves in working-memory-only mode.

A single `failureMode: soft | strict` knob on the Agent memory block selects this fail-soft default versus a strict mode that fails the operation. The standing risk is upstream write durability rather than availability — losing extracted long-term memory matters more than a transient recall miss — which is why the durable-queue follow-up is recorded even though memory remains a non-tier-1 dependency.

### Datastore posture: bind, do not operate; with a CLI-provisioned dev option

The operator **deploys the memory service** (its `Deployment`, `Service`, and — in `local` mode — its `PersistentVolumeClaim`) but does **not** operate the external database. In `external` mode Postgres is a bring-your-own dependency bound through a connection secret reference, consistent with [KAOS-R7](../research/KAOS-R7-target-picture.md) and the security defaults in [adr_high_level_components](./adr_high_level_components.md); KAOS owns no backup, sizing, or failover for it. To keep the on-ramp turnkey, the `kaos` CLI installer can provision an **opt-in** development Postgres as a first-class, explicit step alongside the existing gateway and load-balancer provisioning, never as the production default.

### Control plane: `MemoryStore` is infrastructure, the Agent block is behaviour

The `MemoryStore` CRD describes **only infrastructure and models**, carrying no runtime-behaviour knobs:

```yaml
apiVersion: kaos.io/v1alpha1
kind: MemoryStore
metadata:
  name: shared-memory
  namespace: kaos-system
spec:
  engine: mem0                # single-value enum today
  storage:
    type: local
    local: { provider: chroma, persistentVolume: { size: 10Gi } }
  replicas: 1                 # local pins to 1; external allows 2+
  models:
    summarization: { modelAPI: default-models, model: openai/gpt-4o-mini }       # extraction and rolling summary
    embedding:     { modelAPI: default-models, model: openai/text-embedding-3-small }
  extraction: { concurrency: 4 }
```

The two model roles mirror the Agent's existing `{modelAPI, model}` shape and reference an existing `ModelAPI` rather than carrying inline credentials; the `summarization` role drives both Mem0's long-term fact extraction and the working-tier rolling summary. There is no quota block: capacity is bounded by the PersistentVolume size in `local` mode and by Postgres sizing in `external` mode — meaningful, infrastructure-enforced limits rather than an arbitrary item count. Per-tenant rate and fair-share enforcement is a governance concern deferred to [ADR 0005](./adr_high_level_components.md).

The Agent CRD keeps a **slim memory block** holding only runtime behaviour, selecting a store by name and setting per-agent knobs:

```yaml
spec:
  config:
    memory:
      storeRef: shared-memory
      shortTermTokenBudget: 6000
      rollingSummary: true
      recall: { presentation: block }   # block | tools | both
      failureMode: soft                  # soft | strict
```

The working-tier token budget, the summarization toggle, the recall presentation from [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md), and the failure mode live here and nowhere else, removing the duplication of behavioural settings across two resources. The token budget and summarization toggle are **executed by the memory service** — which owns the shared working tier and holds the `summarization` model — and supplied as per-agent policy on each request, while the agent runtime only calls recall and receives assembled context. The per-agent memory `scope` is owned by [ADR 0005](./adr_high_level_components.md) and is not set here.

### Operator reconciliation and schema ownership

Reconciling a `MemoryStore` deploys the memory-service `Deployment` and `Service` (plus a `PersistentVolumeClaim` in `local` mode), wires the storage secret and the referenced `ModelAPI` endpoints as environment, validates that the model references resolve and are ready, and reports health and the service endpoint in status. Schema setup is automatic and needs no user migration step: the service runs idempotent `CREATE TABLE IF NOT EXISTS` for the KAOS-owned working table on boot, and Mem0 self-creates its own vector schema on first connect. The user supplies only a connection secret in `external` mode or a volume size in `local` mode. Versioned migration tooling is introduced later, when the KAOS-owned schema first evolves, and is then an operator responsibility.

## Consequences

- Memory runs as one central, horizontally scalable service that all agents share, keeping agent images thin and isolating LLM-gated extraction from serving.
- A single `storage.type` switch spans a zero-dependency single-container `local` mode and a high-availability `external` mode, with a clean upgrade path between them.
- Multi-tenant recall is correct by construction because both shipped vector providers pre-filter on scope during the query.
- Asynchronous memory work is simple and cheap, accepting bounded re-derivable loss on crash rather than carrying a queue the engine does not provide.
- High availability in `external` mode is a replica count, because the service holds no durable node-local state once Mem0's audit log is set aside.
- A memory outage degrades agents to working-memory-only and is surfaced through readiness, but never halts serving; memory is an augmentation, not a tier-1 dependency.
- The control plane cleanly separates a `MemoryStore` infrastructure resource from a behaviour-only Agent block, ending the cross-resource duplication of runtime settings.
- The operator binds rather than operates the external database, with an opt-in CLI-provisioned development Postgres for the turnkey path.
- Because alpha allows breaking changes, the inline working-only `MemoryConfig` is replaced by the `MemoryStore` plus slim Agent block; deployments are migrated rather than transparently upgraded.

## Alternatives considered

- **Embedded library in each agent.** Rejected as a supported path: extraction on the serving process, multiplied datastore connections, engine dependencies in every agent image, and divergent per-replica memory; the latency and pod-count savings are marginal against LLM-dominated turn latency.
- **Sidecar engine per agent pod.** Rejected: it adds a container and a second lifecycle while still failing to share memory across an agent's replicas.
- **Run the stock Mem0 REST server.** Rejected: it is long-term-only, single-admin-key authenticated, IP-rate-limited, and lacks the working tier, rolling summary, KAOS scoping, and KAOS telemetry ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)); KAOS reuses Mem0 as a library instead.
- **FAISS as the local vector store.** Rejected: Mem0's FAISS path post-filters metadata after the nearest-neighbour search, so a tenant's relevant memories can be silently dropped from a shared index; Chroma pre-filters and is correct for multi-tenant recall. FAISS remains a possible documented single-tenant, ephemeral option.
- **A durable job queue for background writes in this version.** Rejected now: Mem0 provides none, a write is a single-call unit re-derivable from the durable working tier, and a queue is added complexity for unproven value at this stage; recorded as a follow-up.
- **A second Postgres or Redis for the working tier.** Rejected: consolidating both tiers onto one datastore is a goal, and the working tier follows the storage mode automatically ([ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md), [KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)).
- **Application-level per-tenant quotas in this version.** Rejected: the engine provides none, an item count is an arbitrary limit, and infrastructure sizing already bounds capacity; fair-share enforcement is deferred to [ADR 0005](./adr_high_level_components.md).
- **Behavioural settings on the `MemoryStore`.** Rejected: token budget, summarization, recall presentation, and failure mode are per-agent behaviour and belong on the Agent block; the store stores and the agent decides how it uses memory.

## Follow-up

- ADR 0005 fixes the full multi-tenancy, agent-grouping, and governance model — including per-tenant rate and fair-share enforcement, the isolation modes, authentication on the memory endpoints, and erasure and export — building on the server-side scope injection this control plane configures.
- A durable, at-least-once background-write mechanism is adopted only if and when write durability on crash becomes a hard requirement.
- Versioned schema migration tooling for the KAOS-owned working table is introduced when that schema first evolves.
- The `kaos` CLI installer integration for the opt-in development Postgres is specified alongside the existing system-install provisioning during implementation.
