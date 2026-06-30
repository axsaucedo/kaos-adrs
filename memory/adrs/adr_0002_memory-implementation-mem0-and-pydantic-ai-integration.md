# ADR 0002 — Memory implementation: Mem0 engine and Pydantic AI integration

- **Status.** Proposed
- **Date.** 2026-06-30
- **Component.** 2 of 5 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md), [KAOS-R6](../research/KAOS-R6-tool-selection.md), [KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md), [KAOS-R5-1](../research/KAOS-R5-1-mem0.md)
- **Constrains.** ADR 0003 (runtime interface and data plane), ADR 0004 (deployment topology and control plane).

## Context

[ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) fixes the conceptual model — working memory owned by KAOS, semantic and episodic as the committed long-term core, temporal and procedural deferred, scope anchored to verifiable identity — but deliberately leaves every engine-dependent behaviour as a placeholder. This record closes those placeholders by choosing how memory is actually implemented.

KAOS today ships a working-memory-only `Memory` abstraction with Local, Redis, and Null backends, all variations of one short-term tier ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)). Pydantic AI itself provides message history only, so KAOS owns the long-term layer regardless of engine; the open question is what backs it. The selection pipeline recommended Mem0 as the primary engine with Redis AMS as the infrastructure-minimal alternative ([KAOS-R6](../research/KAOS-R6-tool-selection.md)), and the follow-on assessment confirmed Mem0's capability and maturity, its only material lock-in being graph memory and managed high availability behind its SaaS, neither needed for the committed core ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)).

A verified survey found that no engine ships a maintained Pydantic AI adapter — only a seven-star demonstration repository exists — so the integration is hand-written for any engine and is where most of the implementation effort and most of the KAOS-specific value lands. The peer Kubernetes agent platform kagent independently built an equivalent memory layer (self-hosted pgvector, background extraction every few turns, prefetch on the first turn, embeddings through a model proxy, time-to-live pruning), which validates this shape; KAOS adopts Mem0 to obtain the same capability without building and maintaining the engine.

## Decision

### A single adopted engine: Mem0

KAOS adopts **Mem0** as the long-term memory engine, and adopts exactly one. The long-term tier is not pluggable across multiple shipped backends: there is one engine, implemented and supported. The `Memory` abstraction remains an abstraction, so a future contributor can add another backend, but KAOS does not build, ship, or maintain a second long-term implementation now, and does not water the interface down to a lowest-common-denominator across hypothetical engines. The interface is shaped around Mem0's actual contract — scope identifiers on every operation, infer-on-write extraction, and relevance search — rather than an abstract memory algebra. Redis AMS and Graphiti are recorded as alternatives in research, not as parallel code paths.

### Tier ownership: KAOS keeps working, Mem0 owns long-term

The one firm invariant from [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) holds: KAOS and Pydantic AI own the live per-run message-history bridge through the existing working-memory backends (Local, Redis, Null), unchanged. Mem0 backs only the semantic and episodic long-term tier. Mem0 has no live conversation-buffer concept, so it is never asked to serve working memory. Adoption is therefore additive — existing agents keep working with no long-term tier until one is configured.

### Integration: a hand-written `Mem0Memory` backend behind the existing ABC

The integration is a `Mem0Memory` subclass of the existing `Memory` ABC in the Pydantic AI runtime, running Mem0 in library mode against an external vector store. It calls `mem0.add(...)` on write and `mem0.search(...)` on read, mapping KAOS scope onto Mem0's `user_id`/`agent_id`/`run_id` identifiers, with the scope values drawn from the verifiable identities ADR 0001 anchors to — the user principal and the agent's AIB `client_id` (`kaos://agent/{namespace}/{name}`), never an ephemeral UUID.

```python
class Mem0Memory(Memory):  # extends the existing working-memory ABC; long-term only
    def __init__(self, config: Mem0Config):
        self.m = AsyncMemory(config=config.to_mem0())  # vector store + ModelAPI-backed models

    async def add_event(self, session_id: str, event: MemoryEvent, *, scope: Scope) -> None:
        await super().add_event(session_id, event)            # KAOS working buffer, unchanged
        await self._enqueue_extraction(event, scope)          # long-term write runs in background

    async def recall(self, query: str, *, scope: Scope, top_k: int = 5):
        return await self.m.search(
            query,
            user_id=scope.principal,                          # verifiable user identity
            agent_id=scope.agent_client_id,                   # AIB client_id, not a UUID
            run_id=scope.session_id,
            limit=top_k,
        )
```

Recalled facts are surfaced to the agent as a structured memory block (the presentation contract is finalised in ADR 0003). Embedding and extraction models bind to KAOS `ModelAPI` resources rather than to direct provider keys, consistent with how kagent routes embeddings through its model proxy.

### A reusable Pydantic AI integration

Because no maintained Pydantic AI to Mem0 integration exists, `Mem0Memory` is designed to be the most robust public integration of the two and is intended to be extractable as a reusable open-source adapter rather than buried in KAOS-internal glue. This is a deliberate goal, not a side effect: KAOS fills a genuine ecosystem gap.

### Write path: background extraction, hot-path recall

Mem0's write path is gated by one or more LLM calls for fact extraction, and KAOS autonomous loops emit many events ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)). Long-term writes therefore run as a background task off the agent hot path, while recall stays synchronous and low-latency. The precise queue and worker mechanism is an ADR 0004 concern; this record fixes only that extraction is never inline on the response path.

### Storage and deployment posture

The vector store defaults to **pgvector** — a bring-your-own, operationally familiar backend that adds no new datastore class and is externally operated per the bring-your-own datastore stance of [KAOS-R7](../research/KAOS-R7-target-picture.md); Qdrant remains a supported Mem0 backend option. Mem0 runs as a **central shared service** for a multi-tenant fleet rather than embedded per agent, matching the hot-path central-service topology; its singleton-instance and per-container history-store caveats ([KAOS-R5-1](../research/KAOS-R5-1-mem0.md)) are made highly-available in ADR 0004. Storage selection and the deployment and high-availability engineering are owned by ADR 0004; this record fixes the defaults and the rationale.

### What KAOS supplies around the engine

Mem0's gaps are filled at the KAOS integration layer rather than by the engine: OpenTelemetry instrumentation emitted by KAOS regardless of Mem0's PostHog-based telemetry; tenant-scope enforcement in the `Memory` backend, since Mem0's isolation is application-level filtering with no row-level security; and Kubernetes packaging and CRD wiring. The open-core ceiling is accepted by never depending on it: Mem0's SaaS-gated graph memory and managed high availability are out of scope, and the graph and temporal capability is deferred to a future Graphiti-class tier ([ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) deferred tiers), not obtained from Mem0's paid plane.

## Consequences

- Long-term memory becomes available as an additive tier with no change to existing working-memory behaviour or configuration.
- The semantic and episodic placeholders in [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) can be closed: retrieval is Mem0 relevance search, extraction is Mem0 infer-on-write run in the background, and conflict resolution uses Mem0's update semantics.
- KAOS owns a hand-written Pydantic AI integration as a first-class component, with the upside of a reusable public adapter and the cost of tracking Mem0's API churn ([KAOS-R5-1](../research/KAOS-R5-1-mem0.md)).
- Tenant isolation, OpenTelemetry, and Kubernetes packaging are KAOS responsibilities, deliberately, because Mem0 does not provide them at the level KAOS requires.
- Committing to a single engine removes the cost of maintaining multiple backends but means a future graph or temporal tier is a new backend behind the same ABC, expected and bounded by the deferral in ADR 0001.
- Mem0's SaaS-gated features are permanently out of scope; if graph or temporal memory is later justified it is delivered by a separate engine, not by adopting Mem0's paid plane.

## Alternatives considered

- **Pluggable multiple long-term backends now.** Rejected: the flexibility is speculative for the first implementation, and the `Memory` ABC already makes future extension possible without shipping and maintaining parallel code paths. The seam is kept; the second implementation is not built.
- **Redis AMS as primary.** Retained as the documented alternative where infrastructure delta dominates — it backs both tiers on the Redis KAOS already runs — but set aside as primary on maturity (no tagged releases) and weaker capability and ecosystem than Mem0 ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)).
- **Graphiti as primary.** Rejected as a first step on operational cost (Neo4j, Enterprise for hard per-tenant isolation) and write expense; retained as the deferred temporal-tier reference.
- **Build the engine in-house.** Rejected: it rebuilds roughly an AMS-scale engine (~16k lines) of solved retrieval, extraction, and consolidation work under a permissive licence KAOS can simply adopt ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)).
- **Mem0 SaaS Platform.** Rejected: not self-hostable, conflicting with KAOS's self-hosted multi-tenant model; only the Apache-2.0 OSS core is adopted.

## Follow-up

- ADR 0003 fixes the runtime interface: the long-term operation set, synchronous-versus-asynchronous shape, and how recalled context is presented to the agent.
- ADR 0004 fixes storage selection, the central-service deployment, the background queue and workers, and the high-availability engineering for Mem0's singleton and history-store caveats.
- The reusable Pydantic AI adapter's packaging boundary (in-tree versus a standalone published package) is decided alongside ADR 0003.
