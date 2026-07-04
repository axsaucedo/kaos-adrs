# ADR 0004 — Deployment topology, execution model, and control plane

- **Status.** Proposed
- **Date.** 2026-06-30
- **Component.** 4 of 5 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md), [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md), [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md), [KAOS-R5-1](../research/KAOS-R5-1-mem0.md), [KAOS-R7](../research/KAOS-R7-target-picture.md), [KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md), [KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)
- **Constrains.** ADR 0005 (multi-tenancy and grouping).

## Context

[ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md) selects Mem0 as the long-term atomic-fact engine and [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) fixes the runtime contract — the tiered `Memory` abstraction, the session-only short-term window, the session-scoped medium-term digest, the synchronous-recall/asynchronous-write split, cascade extraction, and server-side scope injection. Both records defer how memory is run and operated to this one. This ADR decides the deployment topology, the staged async-hybrid execution model, the Postgres-backed storage posture, the background execution model, the high-availability and degradation posture, and the control plane — the `MemoryStore` CRD, the Agent memory block, and the operator's responsibilities.

The current control surface is an inline `MemoryConfig` on `AgentSpec.Config.Memory` describing only short-term memory (`enabled`, `type: local|redis`, `contextLimit`, `maxSessions`, `maxSessionEvents`). There is no resource describing a long-term backend, and the runtime has no dedicated background-job system beyond the autonomous-loop `asyncio` tasks in the data plane ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)). Because KAOS is in alpha this surface is redesigned rather than preserved, consistent with [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md). Source surfaces: `operator/api/v1alpha1/agent_types.go`, `operator/controllers/agent_controller.go`, `pydantic-ai-server/pais/memory.py`, `pydantic-ai-server/pais/a2a.py`.

A determining finding from [KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md): the stock Mem0 REST server is long-term-only (`/memories`, `/search`, `/configure`), authenticates with a single shared admin key, rate-limits by client IP, and has no short-term tier, rolling summary, KAOS tenant scoping, or KAOS-format telemetry. KAOS therefore reuses Mem0 as a library inside its own service rather than running that server.

## Decision

### A single central memory service, built around Mem0 as a library

The long-term engine runs as **one central memory service** that all agents call over the network, not as a library embedded in each agent process and not as a per-agent sidecar. The service is a thin KAOS-owned component that imports Mem0 as a library and wraps it with the [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) contract — the short-term tier, rolling summary, recall block assembly, server-side scope injection, and OpenTelemetry. The stock Mem0 server is not used because it provides none of these ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)).

The embedded-in-agent alternative is rejected as a supported path: it pushes LLM-gated extraction onto the serving process, multiplies datastore connections, ships the engine and its vector dependencies into every agent image, and — with a per-pod local store — diverges memory across an agent's replicas. A single shared service is cheap, keeps agents thin, isolates extraction, and preserves cross-agent sharing, which the cross-agent and organizational memory capability in [KAOS-R7](../research/KAOS-R7-target-picture.md) requires. The "no separate pod" and "no network hop" gains of embedding are marginal against LLM-dominated turn latency.

### Packaging: the contract, client, and service ship as one `kaos-memory` library

The memory service, its HTTP client, and the wire contract they share are packaged as a single published `kaos-memory` library rather than split across the service tree and a hand-rolled runtime client. The library layers its surface behind dependency extras: the core install carries the wire contract (`Scope`/`ScopeLevel` and the recall/write/forget schemas) and the framework-agnostic `MemoryServiceClient` on Pydantic, httpx and the OpenTelemetry API only; the `[service]` extra adds Mem0, the vector store and the FastAPI service; and the `[pydantic-ai]` extra adds the message adapters, server-side scope derivation, and the `save_memory`/`search_memory` toolset. This keeps the server and client from drifting — both import the one contract — and lets a Pydantic AI consumer import one coherent feature set without dragging the engine into the agent image.

Because the agent runtime is itself a published standalone package, the library it imports must also be published: `kaos-memory` is a published PyPI project (with a release job that publishes it ahead of the runtime), and the runtime depends on `kaos-memory[pydantic-ai]` while resolving it from the sibling checkout for local dev, CI and the container image. In the runtime, `RemoteMemory` is a thin adapter over `MemoryServiceClient`; it remains the KAOS tiered-contract client and is still not a Mem0 client.

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

- **`local`** — the service runs everything in a single container with no external dependency: Mem0 with an embedded Chroma persistent store for long-term and a SQLite table for the short-term tier, both on one PersistentVolume. It is the least-effort on-ramp for development and small single-store deployments. It pins to a single replica because the embedded store is a single-writer file.
- **`external`** — long-term is pgvector and the short-term tier is a plain table on the **same** external Postgres instance ([ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md), [KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)). The service is stateless and runs `replicas: 2+` for high availability. It is the production path.

Both modes expose one `provider` value today and are structured so a future contributor can add a provider without reshaping the CRD, consistent with the engine-agnostic direction in [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md). The vector provider is chosen for correct pre-filtered multi-tenant recall: both Chroma and pgvector apply the scope filter during the vector query, whereas a post-filtering store would discard a tenant's relevant memories that fall outside an unfiltered nearest-neighbour window — unacceptable for the shared, multi-owner index this service holds.

### Postgres external-mode table posture

In `external` mode the session-scoped short-term window may use a Postgres `UNLOGGED` table because the window is ephemeral and does not need the same durability posture as long-term facts. Redis is explicitly out of scope for this window: Postgres is sufficient for conversational write frequency, keeps all memory coordination in one datastore, and still gives all service replicas a shared table. The accepted trade-off is crash-lossy, primary-only short-term context; long-term Mem0 data and durable metadata remain on logged storage. Tmpfs tablespaces and gateway-level session-affinity routing are deferred optimizations, not correctness requirements. See also: [Decision 14 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-14-the-postgres-short-term-window-is-unlogged-redis-stays-out).

### Background execution: in-process, fire-and-forget, no queue

The memory service is staged async-hybrid. The committed baseline is async FastAPI request handling with sync Mem0 work isolated behind a KAOS-owned bounded executor; native async Postgres access is deferred until the short-term database path justifies the driver-conversion cost. The asynchronous operations from [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) — fold, extract, flush, consolidate, forget — run as **in-process background tasks inside the memory service**, off the recall hot path, bounded by a concurrency setting:

```yaml
extraction:
  concurrency: 4              # max simultaneous background extractions per replica
```

There is no durable job queue in this version. The primary cost lever is batching raw evicted turns once per fold rather than extracting per turn, and background-queue mitigations are staged only as metrics justify: first Model 2 batching, then queue-depth and executor-saturation telemetry, then per-scope coalescing, then bounded-queue backpressure with a degraded flag. A durable at-least-once queue is recorded as a later option only when write durability on crash becomes a hard requirement; it is deliberately not built before measurements show it is needed. See also: [Decision 18 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-18-background-mitigations-are-staged-not-overbuilt).

### High availability and the Mem0 statefulness caveat

In `external` mode the service is **stateless**: all durable state is the shared Postgres (pgvector plus the KAOS relational tables), so high availability is `replicas: 2+` behind a Kubernetes `Service` with no sticky sessions. Short-term and medium-term consolidation is serialized through database-owned fold/flush work, so many replicas can write and fold the same session without lost folds, double folds, single-writer routing, or lossy conflict behaviour. Mem0's node-local history caveat ([KAOS-R5-1](../research/KAOS-R5-1-mem0.md)) is not memory data and is disabled or ignored, so it does not impede horizontal scaling. In `local` mode the embedded store is a single-writer file and the service is intentionally single-replica. See also: [Decision 4 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-4-consolidation-ownership-is-serialized-by-postgres-locking).

### Degradation contract: memory is augmentation, not a hard dependency

A memory outage degrades agents but never stops them ([ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) recall is augmentation):

- **Recall failure** returns short-term-memory-only context and emits a degraded span; the turn completes.
- **Long-term write failure** is retried in the background; it never blocks the response.
- **Store unavailable when an Agent first binds** marks the Agent **not Ready** so the condition is visible to the operator and user, but the agent still starts and serves in short-term-memory-only mode.

A single `failureMode: soft | strict` knob on the Agent memory block selects this fail-soft default versus a strict mode that fails the operation. The standing risk is upstream write durability rather than availability — losing extracted long-term memory matters more than a transient recall miss — which is why the durable-queue follow-up is recorded even though memory remains a non-tier-1 dependency.

### Datastore posture: bind, do not operate; with a CLI-provisioned dev option

The operator **deploys the memory service** (its `Deployment`, `Service`, and — in `local` mode — its `PersistentVolumeClaim`) but does **not** operate the external database. In `external` mode Postgres is a bring-your-own dependency bound through a connection secret reference, consistent with [KAOS-R7](../research/KAOS-R7-target-picture.md) and the security defaults in [adr_high_level_components](./adr_high_level_components.md); KAOS owns no backup, sizing, or failover for it. To keep the on-ramp turnkey, the `kaos` CLI installer can provision an **opt-in** development Postgres as a first-class, explicit step alongside the existing gateway and load-balancer provisioning, never as the production default.

### Control plane: `MemoryStore` defaults and Agent behaviour

The `MemoryStore` CRD describes infrastructure, model bindings, server defaults, and server guardrails. Runtime behaviour can be overridden on the Agent memory block when it is agent-specific, but the service also needs store-level settings because it owns the short-term window, the medium-term digest, sweeps, executor pool, and server-side validation. This reconciles the earlier slim-store posture with the finalized decision that memory knobs must exist at both client-params and server-settings levels.

```yaml
apiVersion: kaos.io/v1alpha1
kind: MemoryStore
metadata:
  name: shared-memory
  namespace: kaos-system
spec:
  engine: mem0                # single-value enum today
  storage:
    type: external            # local | external
    external: { provider: pgvector, connectionSecretRef: { name: memory-postgres, key: dsn } }
  replicas: 2
  models:
    summarization: { modelAPI: default-models, model: openai/gpt-4o-mini }       # medium-term digest and Mem0 extraction prompt model
    embedding:     { modelAPI: default-models, model: openai/text-embedding-3-small }
  serverSettings:
    tokenBudget: 6000
    highWater: 6000
    lowWater: 4500
    hardEventCap: 200
    digestMaxTokens: 1200
    idleTtl: 30m
    sweepInterval: 2m
    rollingSummary: false
    concurrency: 4
```

The Agent CRD keeps the agent-specific memory policy and client parameters, selecting a store by name and overriding the same behavioural knobs when the agent needs a different policy. The store reference is the backend switch: when `memoryStore` is set the operator injects the service endpoint and the runtime uses the network `RemoteMemory` backend; when it is absent the runtime falls back to the in-process short-term `LocalMemory` backend (recent-turn replay only, pod-local, no long-term tier). `RemoteMemory` is the renamed runtime HTTP client for this service — it speaks the KAOS tiered contract and is not a Mem0 client; Mem0 is embedded inside the service as the long-term engine, never called directly from the agent.

```yaml
spec:
  config:
    memory:
      enabled: true                    # false => memory disabled (NullMemory)
      memoryStore: shared-memory       # optional; set => RemoteMemory, absent => LocalMemory
      scope: user
      clientParams:
        tokenBudget: 6000
        compactionTrigger: 6000
        compactionTarget: 4500
        hardEventCap: 200
        digestMaxTokens: 1200
        idleTtl: 30m
        sweepInterval: 2m
        rollingSummary: true
        concurrency: 2
      tools: all                       # all | read | write | (unset = none)
      failureMode: soft                # soft | strict; unset => inherit store default
```

Enabling memory applies the automatic baseline unconditionally: the runtime recalls and injects a context block before each run and flushes the run's turns for extraction after it. The `tools` knob layers **additive** explicit agent-driven tools on top of that baseline — `read` exposes `search_memory` (on-demand retrieval), `write` exposes `save_memory` (on-demand save), `all` exposes both, and unset exposes none. There is no separate automatic-versus-tool mode: the automatic paths are the meaning of enabling memory, and the tools are purely additional. This supersedes the earlier `recall.presentation: block | tools | both` knob. See also: [the runtime memory API and tooling learnings](../impl/learnings/runtime-memory-api-and-tooling.md).

The shared knob set is `token_budget`, `compaction_trigger`, `compaction_target`, `hard_event_cap`, `digest_max_tokens`, `idle_ttl`, `sweep_interval`, `rolling_summary`, and `concurrency`. The operator validates the constraints from [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) at both levels: `compaction_target < compaction_trigger <= token_budget`, `hard_event_cap >= 1`, positive TTL and sweep intervals, positive digest budget when rolling summary is enabled, and `concurrency >= 1`. Store-level values are defaults and service limits; Agent-level values are per-agent policy supplied on requests. The memory service is the executor of the policy because it owns the shared window, digest, locks, sweeper, and Mem0 executor.

The operator additionally enforces two fail-closed binding guards that follow from the backend switch. A `user`- or `shared`-scoped agent **requires** a `memoryStore`, because `LocalMemory` is pod-local and cannot serve cross-agent scopes — across replicas each pod would hold a divergent private copy. Setting `tools` also **requires** a `memoryStore`, because `save_memory` and `search_memory` target the long-term tier that `LocalMemory` lacks, so without a store they would be silent no-ops. Both misconfigurations are rejected rather than silently degraded. A `private`-scoped owner is likewise resolved fail-closed from the agent's fully-qualified `kaos://agent/{namespace}/{name}` identity (minted as `AGENT_AUTH_IDENTITY`), never a name-only or empty owner, so identity-less agents can never collapse onto one shared private partition.

The two model roles mirror the Agent's existing `{modelAPI, model}` shape and reference an existing `ModelAPI` rather than carrying inline credentials; the `summarization` role drives both Mem0's long-term fact extraction prompt path and the medium-term rolling digest when enabled. There is no quota block in this version: capacity is bounded by the PersistentVolume size in `local` mode and by Postgres sizing in `external` mode — meaningful, infrastructure-enforced limits rather than an arbitrary item count. Per-tenant rate and fair-share enforcement is a governance concern deferred to [ADR 0005](./adr_0005_multi-tenancy-agent-grouping-and-governance.md).

### Idle-session sweeper and optional close endpoint

The memory service owns the session-end flush design, but the periodic idle-TTL sweeper is deferred to productionisation rather than built in the initial service cut. The deferred sweeper completes stranded sub-threshold session tails by using the same serialized fold/flush path as normal consolidation, extracting remaining long-term facts, and clearing ephemeral rows. An optional close endpoint may invoke that path explicitly earlier. This remains a service concern, not an operator job, because it needs the service's live config, ModelAPI clients, Mem0 adapter, and executor limits. See also: [Decision 17 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-17-idle-ttl-sweeper-detects-session-end).

### Operator reconciliation and schema ownership

Reconciling a `MemoryStore` deploys the memory-service `Deployment` and `Service` (plus a `PersistentVolumeClaim` in `local` mode), wires the storage secret and the referenced `ModelAPI` endpoints as environment, validates that the model references resolve and are ready, and reports health and the service endpoint in status. Schema setup is automatic and needs no user migration step: the service runs idempotent `CREATE TABLE IF NOT EXISTS` for the KAOS-owned `short_term_memory_window` and `medium_term_memory_summaries` tables on boot, including the configured ephemeral-window posture in external mode, and Mem0 self-creates its own vector schema on first connect. The user supplies only a connection secret in `external` mode or a volume size in `local` mode. Versioned migration tooling is introduced later, when the KAOS-owned schema first evolves, and is then an operator responsibility.

## Consequences

- Memory runs as one central, horizontally scalable service that all agents share, keeping agent images thin and isolating LLM-gated extraction from serving.
- A single `storage.type` switch spans a zero-dependency single-container `local` mode and a high-availability `external` mode, with a clean upgrade path between them.
- Multi-tenant recall is correct by construction because both shipped vector providers pre-filter on scope during the query.
- Asynchronous memory work is simple and staged, with Model 2 batching as the first mitigation, OTel queue-depth metrics as the second, and heavier queue/backpressure mechanisms staged until measurements justify them.
- High availability in `external` mode is a replica count plus database-serialized consolidation, because the service holds no durable node-local memory state.
- A memory outage degrades agents to short-term-memory-only and is surfaced through readiness, but never halts serving; memory is an augmentation, not a tier-1 dependency.
- The control plane exposes the same memory-behaviour knobs as MemoryStore server defaults and Agent client parameters, with identical validation and clear precedence.
- The Agent memory block is a single switch surface: enabling memory turns on the automatic recall-inject and write-extract baseline, the presence of a `memoryStore` reference selects the `RemoteMemory` service backend versus the pod-local short-term `LocalMemory` fallback, and a `tools: all|read|write` knob layers additive `save_memory`/`search_memory` tools; `user`/`shared` scope and any `tools` setting are rejected without a bound store, and `private` ownership resolves fail-closed from the qualified agent identity.
- The operator binds rather than operates the external database, with an opt-in CLI-provisioned development Postgres for the turnkey path.
- Because alpha allows breaking changes, the inline short-term-only `MemoryConfig` is replaced by the `MemoryStore` plus slim Agent block; deployments are migrated rather than transparently upgraded.

## Alternatives considered

- **Embedded library in each agent.** Rejected as a supported path: extraction on the serving process, multiplied datastore connections, engine dependencies in every agent image, and divergent per-replica memory; the latency and pod-count savings are marginal against LLM-dominated turn latency.
- **Sidecar engine per agent pod.** Rejected: it adds a container and a second lifecycle while still failing to share memory across an agent's replicas.
- **Run the stock Mem0 REST server.** Rejected: it is long-term-only, single-admin-key authenticated, IP-rate-limited, and lacks the short-term tier, rolling summary, KAOS scoping, and KAOS telemetry ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)); KAOS reuses Mem0 as a library instead.
- **FAISS as the local vector store.** Rejected: Mem0's FAISS path post-filters metadata after the nearest-neighbour search, so a tenant's relevant memories can be silently dropped from a shared index; Chroma pre-filters and is correct for multi-tenant recall. FAISS remains a possible documented single-tenant, ephemeral option.
- **A durable job queue for background writes in this version.** Rejected now: Mem0 provides none, Model 2 batching is the primary lever, raw turns remain available until locked fold/flush completion, and a queue is added complexity for unproven value at this stage; recorded as a follow-up.
- **Redis for the short-term window.** Rejected: Postgres gives shared ephemeral storage across replicas without a second datastore; Redis is unnecessary for conversational write frequency.
- **Single-writer memory service for consolidation.** Rejected: database-owned consolidation lets many replicas run safely.
- **Gateway session affinity as correctness mechanism.** Rejected: correctness comes from database ownership; affinity is deferred as a possible latency optimization only.
- **A second Postgres or Redis for the short-term tier.** Rejected: consolidating both tiers onto one datastore is a goal, and the short-term tier follows the storage mode automatically ([ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md), [KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)).
- **Application-level per-tenant quotas in this version.** Rejected: the engine provides none, an item count is an arbitrary limit, and infrastructure sizing already bounds capacity; fair-share enforcement is deferred to [ADR 0005](./adr_0005_multi-tenancy-agent-grouping-and-governance.md).
- **Behavioural settings only on the Agent.** Rejected by the finalized service design: the memory service owns sweeps, locks, digest retention, and executor capacity, so server defaults and limits belong on `MemoryStore`; Agent settings remain per-agent client policy.

## Follow-up

- ADR 0005 fixes the full multi-tenancy, agent-grouping, and governance model — including per-tenant rate and fair-share enforcement, the isolation modes, authentication on the memory endpoints, and erasure and export — building on the server-side scope injection this control plane configures.
- A durable, at-least-once background-write mechanism is adopted only if and when queue-depth, executor-saturation, or write-durability metrics show that Model 2 batching, single-flight, and bounded in-process backpressure are insufficient.
- The idle-TTL sweeper is implemented during productionisation if stranded sub-threshold session tails become operationally important enough to justify the background loop.
- Native async Postgres access is adopted when the short-term database path, not Mem0 extraction, becomes a measured service bottleneck.
- Versioned schema migration tooling for the KAOS-owned short-term table is introduced when that schema first evolves.
- The `kaos` CLI installer integration for the opt-in development Postgres is specified alongside the existing system-install provisioning during implementation.
