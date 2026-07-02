# ADR 0002 — Memory implementation: Mem0 engine and Pydantic AI integration

- **Status.** Proposed
- **Date.** 2026-06-30
- **Component.** 2 of 5 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md), [KAOS-R6](../research/KAOS-R6-tool-selection.md), [KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md), [KAOS-R5-1](../research/KAOS-R5-1-mem0.md)
- **Constrains.** ADR 0003 (runtime interface and data plane), ADR 0004 (deployment topology and control plane).

## Context

[ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) fixes the conceptual model — short-term memory owned by KAOS, semantic and episodic as the committed long-term core, temporal and procedural deferred, scope anchored to verifiable identity — but deliberately leaves every engine-dependent behaviour as a placeholder. This record closes those placeholders by choosing how memory is actually implemented.

KAOS today ships a short-term-memory-only `Memory` abstraction with Local, Redis, and Null backends, all variations of one short-term tier ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)). Pydantic AI itself provides message history only, so KAOS owns the long-term layer regardless of engine; the open question is what backs it. The selection pipeline recommended Mem0 as the primary engine with Redis AMS as the infrastructure-minimal alternative ([KAOS-R6](../research/KAOS-R6-tool-selection.md)), and the follow-on assessment confirmed Mem0's capability and maturity, its only material lock-in being graph memory and managed high availability behind its SaaS, neither needed for the committed core ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)).

A verified survey found that no engine ships a maintained Pydantic AI adapter — only a seven-star demonstration repository exists — so the integration is hand-written for any engine and is where most of the implementation effort and most of the KAOS-specific value lands. The peer Kubernetes agent platform kagent independently built an equivalent memory layer (self-hosted pgvector, background extraction every few turns, prefetch on the first turn, embeddings through a model proxy, time-to-live pruning), which validates this shape; KAOS adopts Mem0 to obtain the same capability without building and maintaining the engine.

## Decision

### A single adopted engine: Mem0

KAOS adopts **Mem0** as the long-term memory engine, and adopts exactly one. The long-term tier is not pluggable across multiple shipped backends: there is one engine, implemented and supported. The `Memory` abstraction remains an abstraction, so a future contributor can add another backend, but KAOS does not build, ship, or maintain a second long-term implementation now, and does not water the interface down to a lowest-common-denominator across hypothetical engines. The interface is shaped around Mem0's actual contract — scope identifiers on every operation, infer-on-write extraction, and relevance search — rather than an abstract memory algebra. Redis AMS and Graphiti are recorded as alternatives in research, not as parallel code paths.

### Tier ownership: KAOS keeps short-term, Mem0 owns long-term

The one firm invariant from [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) holds: KAOS and Pydantic AI own the live per-run message-history bridge rather than delegating it to Mem0, which has no live conversation-buffer concept and is never asked to serve short-term memory. Mem0 backs only the semantic and episodic **long-term atomic-fact** tier. It does not own the session-scoped verbatim short-term window and it does not own the session-scoped medium-term rolling digest defined in [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md). Long-term adoption is therefore **additive at the feature level** — an existing agent gains no long-term tier until one is configured. This is distinct from the short-term and medium-term tier *internals*: [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md), under the alpha no-backward-compatibility stance, redesigns the short-term tier (session-only, token-budget bound, lazy-read window, relational persistence) and reframes rolling summary as medium-term compaction. So KAOS keeps *owning* conversational memory, while Mem0 owns durable extracted facts.

### Integration: a hand-written `Mem0Memory` backend behind the existing ABC

The integration is a `Mem0Memory`/`LongTermStore` adapter behind the existing `Memory` ABC in the Pydantic AI runtime, running Mem0 in library mode against an external vector store. It calls Mem0 search on recall and Mem0 add only for long-term extraction batches, mapping KAOS scope onto Mem0's `user_id`/`agent_id`/`run_id` identifiers, with the scope values drawn from the verifiable identities ADR 0001 anchors to — the user principal and the agent's AIB `client_id` (`kaos://agent/{namespace}/{name}`), never an ephemeral UUID. The adapter is the only importer of `mem0`; the rest of KAOS speaks the tiered memory contract from [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md).

```python
class LongTermStore:  # the only KAOS adapter that imports mem0
    def __init__(self, config: Mem0Config, executor: BoundedExecutor):
        self.m = Memory.from_config(config.to_mem0())          # vector store + ModelAPI-backed models
        self.executor = executor                              # KAOS owns the sync boundary explicitly

    async def extract_batch(self, evicted_turns: list[MemoryEvent], *, scope: Scope) -> None:
        await self.executor.run(self.m.add, evicted_turns, user_id=scope.principal, agent_id=scope.agent_client_id, run_id=scope.session_id)

    async def recall(self, query: str, *, scope: Scope, top_k: int = 5):
        return await self.executor.run(self.m.search, query, user_id=scope.principal, agent_id=scope.agent_client_id, run_id=scope.session_id, limit=top_k)
```

Recalled facts are surfaced to the agent as a structured memory block alongside the relational short-term window and medium-term digest (the presentation contract is finalised in ADR 0003). Embedding and extraction models bind to KAOS `ModelAPI` resources rather than to direct provider keys, consistent with how kagent routes embeddings through its model proxy. The medium-term digest is never indexed into Mem0; it is injected directly from the KAOS relational store at recall time.

### A reusable Pydantic AI integration

Because no maintained Pydantic AI to Mem0 integration exists, `Mem0Memory` is designed to be the most robust public integration of the two and is intended to be extractable as a reusable open-source adapter rather than buried in KAOS-internal glue. This is a deliberate goal, not a side effect: KAOS fills a genuine ecosystem gap.

### Write path: cascade extraction, hot-path recall

Mem0's write path is gated by one or more LLM calls for fact extraction, and KAOS autonomous loops emit many events ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)). In Mem0 v2.0.10, `_add_to_vector_store` runs one `llm.generate_response` per `add` when `infer=True`, so per-turn Mem0 writes would turn every conversation turn into an extraction call. KAOS therefore adopts the [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) Model 2 cascade: turns enter only the short-term window; when a fold evicts a batch, the raw evicted turns feed both the medium-term digest and Mem0 long-term extraction; and an idle-TTL session-end flush guarantees extraction for sessions that never cross the fold threshold. Long-term extraction is never per-turn and never inline on the response path, while recall stays synchronous and low-latency. The precise background runner, locking, and queue-mitigation mechanism is an ADR 0004 concern.

### Async integration boundary

KAOS consumes Mem0 through an explicit async-hybrid service layer rather than trusting Mem0's async façade as genuinely non-blocking. In Mem0 v2.0.10, `AsyncMemory` methods use `await asyncio.to_thread(...)`, and the OpenAI LLM and embedding integrations in `llms/openai.py` and `embeddings/openai.py` use sync clients rather than `AsyncOpenAI`. KAOS therefore runs async FastAPI handlers and async Postgres operations for its cheap request and relational path, while sync Mem0 calls execute behind a bounded `run_in_executor` pool owned by KAOS. This makes concurrency visible and tunable, prevents unbounded thread creation, and keeps ModelAPI rate limits as the explicit throughput ceiling. Because KAOS is alpha and async-first, the target is the async hybrid service even though the first prototype began with synchronous handlers.

### Storage and deployment posture

The vector store defaults to **pgvector** — a bring-your-own, operationally familiar backend that adds no new datastore class and is externally operated per the bring-your-own datastore stance of [KAOS-R7](../research/KAOS-R7-target-picture.md). [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md) later generalises this into a `storage.type` switch with a zero-dependency `local` mode (embedded Chroma) and an `external` mode (pgvector on shared Postgres); pgvector remains the production default and the choice narrows to Chroma and pgvector — both pre-filter scope during the vector query, which Qdrant-class post-filtering stores do not guarantee for multi-tenant recall. Mem0 runs as a **central shared service** for a multi-tenant fleet rather than embedded per agent, matching the hot-path central-service topology; its singleton-instance and per-container history-store caveats ([KAOS-R5-1](../research/KAOS-R5-1-mem0.md)) are made highly-available in ADR 0004. Storage selection and the deployment and high-availability engineering are owned by ADR 0004; this record fixes the defaults and the rationale.

### What KAOS supplies around the engine

Mem0's gaps are filled at the KAOS integration layer rather than by the engine: OpenTelemetry instrumentation emitted by KAOS regardless of Mem0's PostHog-based telemetry; tenant-scope enforcement in the `Memory` backend, since Mem0's isolation is application-level filtering with no row-level security; Kubernetes packaging and CRD wiring; and an explicit bounded executor around Mem0's synchronous provider calls. The open-core ceiling is accepted by never depending on it: Mem0's SaaS-gated graph memory and managed high availability are out of scope, and the graph and temporal capability is deferred to a future Graphiti-class tier ([ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) deferred tiers), not obtained from Mem0's paid plane. Native async OpenAI provider support in Mem0 would be a high-value upstream contribution, but it is not on the KAOS critical path.

### Mem0 as a library, not its server

KAOS consumes Mem0 as a **library** behind a single `LongTermStore` adapter (the only importer of `mem0`), not Mem0's own OSS REST server or its hosted platform. This keeps Mem0 a swappable long-term engine behind the KAOS memory contract, and lets the KAOS service own the concerns Mem0's server does not: the KAOS-derived tenancy scope (never trusting caller-supplied owner ids), the two-tier composition (Mem0 serves only the long-term/vector tier while KAOS owns the short-term relational buffer and assembles both tiers into one recall block), fail-soft degradation (recall degrades to short-term-only, writes are sync-short-term plus async-long-term), KAOS-native config/lifecycle (ModelAPI bindings, store-reachability readiness, disabled Mem0 telemetry, OTel spans), and container/CRD integration. The trade-off is maintaining a thin KAOS service layer and wire contract instead of adopting Mem0's server as-is; in return KAOS is not coupled to Mem0's server API surface, versioning, or paid platform, and can replace the long-term engine without changing the contract.

- Long-term memory becomes available as an additive, opt-in capability; an agent without a configured store is unaffected at the feature level, even though the short-term tier internals and `MEMORY_*` configuration are themselves redesigned under the alpha breaking-change stance ([ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md)).
- The semantic and episodic placeholders in [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) can be closed: retrieval is Mem0 relevance search, extraction is Mem0 inference over evicted raw-turn batches plus idle-session flushes, and conflict resolution uses Mem0's update semantics.
- KAOS owns a hand-written Pydantic AI integration as a first-class component, with the upside of a reusable public adapter and the cost of tracking Mem0's API churn and synchronous provider behaviour ([KAOS-R5-1](../research/KAOS-R5-1-mem0.md)).
- Tenant isolation, OpenTelemetry, and Kubernetes packaging are KAOS responsibilities, deliberately, because Mem0 does not provide them at the level KAOS requires.
- Committing to a single engine removes the cost of maintaining multiple backends but means a future graph or temporal tier is a new backend behind the same ABC, expected and bounded by the deferral in ADR 0001.
- Mem0's SaaS-gated features are permanently out of scope; if graph or temporal memory is later justified it is delivered by a separate engine, not by adopting Mem0's paid plane.

## Alternatives considered

- **Pluggable multiple long-term backends now.** Rejected: the flexibility is speculative for the first implementation, and the `Memory` ABC already makes future extension possible without shipping and maintaining parallel code paths. The seam is kept; the second implementation is not built.
- **Redis AMS as primary.** Retained as the documented alternative where infrastructure delta dominates — it backs both tiers on the Redis KAOS already runs — but set aside as primary on maturity (no tagged releases) and weaker capability and ecosystem than Mem0 ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)).
- **Graphiti as primary.** Rejected as a first step on operational cost (Neo4j, Enterprise for hard per-tenant isolation) and write expense; retained as the deferred temporal-tier reference.
- **Build the engine in-house.** Rejected: it rebuilds roughly an AMS-scale engine (~16k lines) of solved retrieval, extraction, and consolidation work under a permissive licence KAOS can simply adopt ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md)).
- **Use Mem0 for the medium-term digest.** Rejected: Mem0 decomposes input into atomic facts for vector search, while the medium-term tier is a single evolving session narrative; indexing the digest would pollute search and lose narrative shape.
- **Per-turn Mem0 extraction.** Rejected: Mem0 inference performs an LLM extraction per `add`, so per-turn writes would amplify model calls; [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md) instead feeds Mem0 the raw evicted batch on fold plus a guaranteed session-end flush.
- **Treat `AsyncMemory` as the service concurrency solution.** Rejected: the current implementation wraps sync work in `asyncio.to_thread` and uses sync OpenAI clients, so KAOS owns the bounded executor boundary explicitly.
- **Mem0 SaaS Platform.** Rejected: not self-hostable, conflicting with KAOS's self-hosted multi-tenant model; only the Apache-2.0 OSS core is adopted.

## Follow-up

- ADR 0003 fixes the runtime interface: the short-term window, medium-term digest, long-term operation set, cascade extraction timing, synchronous-versus-asynchronous shape, and how recalled context is presented to the agent.
- ADR 0004 fixes storage selection, the central-service deployment, the background queue and workers, and the high-availability engineering for Mem0's singleton and history-store caveats.
- The reusable Pydantic AI adapter's packaging boundary (in-tree versus a standalone published package) is decided alongside ADR 0003.
