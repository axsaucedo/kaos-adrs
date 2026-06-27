# KAOS-R7 — Target picture

This document describes the ideal target picture for memory in KAOS: a full, end-to-end, production-grade design for what KAOS memory should become. It is grounded in the requirements baseline ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)) and the ecosystem best practice ([KAOS-R2](./KAOS-R2-memory-ecosystem-research.md)), and it is *informed but not constrained* by the tooling research and selection ([KAOS-R3](./KAOS-R3-memory-tooling.md) through [KAOS-R6](./KAOS-R6-tool-selection.md)). Where the selected tools fall short of the ideal, the gap is named as a target capability rather than designed around. The in-scope inputs are listed in the [Context manifest](#context-manifest).

This is an unrestricted long-term vision, not an implementation plan. It deliberately describes the optimal realistic end state — the capabilities, surfaces, and properties KAOS memory should have when fully fledged — so that incremental work (including the [KAOS-R6](./KAOS-R6-tool-selection.md) adoption of Mem0 or the Redis Agent Memory Server) can be steered toward it.

## Design principles

These principles, drawn from the two grounding documents, govern every decision below.

- **KAOS owns the interface; the engine is pluggable.** Pydantic AI provides message history only ([KAOS-R2](./KAOS-R2-memory-ecosystem-research.md)), so KAOS must own the long-term layer regardless of build-versus-adopt. The `Memory` abstraction, the CRD surface, and the tier orchestration are KAOS's; the long-term engine behind them is a swappable implementation. This preserves the clean pluggable boundary [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) already values.
- **Tiered by capability, not by vendor.** The design is organized around memory *types and operations* (the [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) vocabulary), so that a vector-first, profile-first, or graph-first engine can each satisfy part of the picture without changing the contract.
- **Declarative and Kubernetes-native.** Memory is configured through CRDs and reconciled by the operator, consistent with how KAOS configures everything else ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) control-plane section).
- **Multi-tenant by construction.** Isolation between users, agents, and tenants is a first-class property of the data model and the API, not an afterthought left to query hygiene.
- **Observable and governable end to end.** Every memory operation emits OpenTelemetry traces and metrics, and every stored item is auditable, exportable, and subject to retention and access policy.
- **Background by default, hot-path when needed.** Expensive extraction/consolidation runs off the agent's critical path; only low-latency recall and lightweight writes are inline ([KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) hot-path-vs-background trade-off).

## Memory model (the target taxonomy)

The target speaks the full [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) vocabulary, replacing today's single recency-capped event log ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)) with a layered model.

- **Working memory (short-term).** The current per-session conversation tier — messages, tool calls, intermediate state — bounded by token/turn budget with progressive summarization rather than blunt eviction. This is the one tier KAOS already has; the target *keeps* it and fixes its fidelity (tool calls and results re-enter context; summaries replace dropped turns).
- **Episodic memory.** Durable records of past interactions and outcomes, retrievable as dynamic few-shot examples, with provenance back to the originating session and event.
- **Semantic memory.** Extracted, durable facts about the world, the domain, and the user — stored as a collection of atomic, embeddable, individually-revisable facts.
- **User / entity profiles.** A schema-constrained, mutable profile per user (and per significant entity), updated in place — the profile shape from [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) and Memobase ([KAOS-R5-4](./KAOS-R5-4-memobase.md)), complementing (not replacing) the semantic collection.
- **Relational / temporal knowledge.** Entities and the time-bounded facts that relate them, with validity intervals and non-lossy invalidation — the Graphiti model ([KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md)) as the capability ceiling, enabling "what was true at time T" and multi-hop recall.
- **Procedural memory.** Learned "how-to" knowledge realized as self-editing system-prompt fragments and reusable skills, scoped per agent.

Every memory item, in every tier, carries common metadata: a stable id, scope (session/user/agent/tenant), timestamps (event time and ingestion time), source provenance (which event/session produced it), importance/salience, access statistics, a retention/pin policy, and OTel trace linkage. This common envelope is what makes the tiers interoperable and the engine swappable.

## Retrieval, consolidation, and forgetting

The target implements the canonical operations [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) identifies, none of which exist today ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)).

- **Retrieval.** Hybrid recall combining semantic similarity, keyword/lexical match, and (where a graph tier exists) structural traversal, scored by the `relevance × importance × recency` formula with configurable weights and half-life decay. Retrieval is scope-filtered (user/agent/tenant/time) and produces a bounded, token-budgeted context block ready to inject — the "one-call hydration" pattern seen in Redis AMS ([KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md)) and Memobase ([KAOS-R5-4](./KAOS-R5-4-memobase.md)).
- **Consolidation / reflection.** A periodic background process distills raw episodic memory into higher-order semantic facts and insights, deduplicates near-duplicates, reconciles contradictions, and refreshes profiles and summaries — the reflection/consolidation pattern from Generative Agents and LangMem ([KAOS-R2](./KAOS-R2-memory-ecosystem-research.md)). Calibration (over- vs under-extraction) is a first-class tunable.
- **Forgetting.** Principled, policy-driven forgetting that goes beyond today's count-bounded eviction: recency/strength decay, importance thresholds, explicit pinning, non-lossy temporal invalidation for facts that change, and hard deletion for governance (right-to-erasure). Forgetting is auditable.
- **Write discipline.** Lightweight writes (append working memory) are inline; expensive writes (extraction, embedding, graph construction, consolidation) run as background jobs, so KAOS's autonomous loops — which emit many events ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)) — never pay extraction latency on the hot path.

## Control plane (CRD and operator)

Today memory is a per-Agent config block reconciled to `MEMORY_*` env vars, with no shared or scoped memory resource and an operator-level default Redis URL ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)). The target elevates memory to first-class Kubernetes resources.

- **A dedicated memory resource.** A `MemoryStore` (or similar) CRD describes a long-term memory backend — its engine, storage bindings (vector/graph/relational/Redis), embedding and extraction model references (pointing at KAOS `ModelAPI` resources), retention and forgetting policy, consolidation schedule, and multi-tenancy mode. Agents reference a `MemoryStore` rather than each carrying a full backend config.
- **Shared and scoped memory.** Because memory is a referenceable resource, multiple agents (and A2A-delegating fleets) can share a store, or be isolated into per-tenant stores, declaratively — closing the "no shared or organizational memory across agents" gap in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md).
- **Operator responsibilities.** The operator reconciles `MemoryStore` resources: deploying and managing the memory engine workload, **binding to** the required datastores via connection and secret references, wiring credentials as secrets (not operator-wide defaults), scheduling consolidation/forgetting jobs, exposing health and metrics, and validating model references. The Agent CRD keeps a slim memory block that selects a store and sets per-agent scope, context budget, and tier toggles.
- **Datastore lifecycle is out of scope (bring-your-own).** The operator does **not** own the lifecycle of the underlying datastores (Postgres, Redis, a graph database). These are treated as externally-operated dependencies — managed services or purpose-built database operators (for example a Postgres or Redis operator) — that the `MemoryStore` *references and binds to*, never resources KAOS provisions, scales, backs up, or upgrades. This keeps the separation of concerns clean and avoids KAOS reimplementing database operations. Optional convenience provisioning for development or test environments may exist behind an explicit opt-in, but it is never the default and is not relied upon for production.
- **Backend-agnostic schema.** The CRD describes *capabilities and policy*, not a single vendor's knobs, so Mem0, Redis AMS, or a future graph engine can satisfy the same resource ([KAOS-R6](./KAOS-R6-tool-selection.md) engine-agnostic direction).

## Data plane (Pydantic AI runtime)

The runtime keeps and extends the existing `Memory` abstraction ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)).

- **Two-layer interface.** The `Memory` ABC gains a long-term sub-interface (write/extract, search/recall, consolidate, forget) alongside its existing working-memory operations, so a backend implements one or both layers. The Redis AMS two-tier model ([KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md)) shows this is natural.
- **Pluggable long-term backends.** Concrete backends — a Mem0 backend, a Redis AMS backend, a future Graphiti backend, and the existing Redis/local working-memory backends — sit behind the interface, selected by the `MemoryStore` the agent references. The bridge fidelity issues in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) (tool calls not replayed; hard truncation) are fixed in the working-memory layer regardless of long-term engine.
- **Recall and write hooks.** Before a run, the runtime hydrates context from working memory plus a scope-filtered long-term recall; after a run, it appends working memory inline and enqueues long-term extraction/consolidation as background work. Recall results are injected as a structured memory block and/or as tools, per agent configuration.
- **Tenant scope injection.** The backend always injects the agent's user/tenant scope into every read and write, so isolation does not depend on caller discipline — addressing the application-level-isolation caveat shared by Mem0 and Redis AMS ([KAOS-R5-1](./KAOS-R5-1-mem0.md), [KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md)).

## Storage and distribution

- **Polyglot, bound by the CRD.** The target supports a vector store (pgvector/Qdrant/RedisVL), an optional graph store (for the relational/temporal tier), a relational store (profiles, provenance, metadata), and Redis (working memory, queues, caches) — selected per `MemoryStore` and **bound to** by the operator via connection/secret references rather than provisioned by it (see control-plane datastore-lifecycle scope above). KAOS's existing Redis is reused wherever possible to minimize infrastructure delta ([KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md)).
- **Durable, distributed, consistent.** Long-term memory is persistent and shared across replicas (as RedisMemory already is for working memory in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)), with the concurrency hazards noted there (non-atomic get-or-create) fixed via atomic primitives. Background jobs scale horizontally on a Redis-backed queue.
- **No operator-wide datastore default.** Storage endpoints are per-`MemoryStore` and credentialed via secrets, replacing today's single operator-level Redis URL.

## Multi-tenancy, isolation, and security

- **Scope hierarchy.** Session → user → agent → tenant/organization, matching the [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) scoping model, enforced at the data layer (namespacing or per-tenant stores) and in every query.
- **Isolation modes.** The `MemoryStore` declares an isolation mode ranging from shared-store-with-scope-filtering (lowest delta) to store-per-tenant (hard isolation) — letting deployments choose along the spectrum the deep dives revealed (application-level filtering in Mem0/AMS, ACLs in Cognee, database-per-group in Graphiti).
- **Access control and governance.** The always-on `/memory/*` endpoints ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)) become authenticated and scope-aware. Memory supports encryption at rest, per-tenant quotas, audit logging, export/import and backup, schema versioning/migration, and right-to-erasure deletion — all gaps explicitly called out in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md).

## Observability

Every memory operation is OpenTelemetry-instrumented end to end — recall, write, extraction, consolidation, and forgetting emit spans linked to the agent run's trace (extending the per-event trace context KAOS already attaches in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)), plus metrics for retrieval quality, recall latency, extraction/consolidation cost (LLM tokens), eviction/forgetting rates, and store health. Cognee, Graphiti, and Memobase show OTel-native memory is achievable ([KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md), [KAOS-R5-3](./KAOS-R5-3-cognee.md), [KAOS-R5-4](./KAOS-R5-4-memobase.md)); where an adopted engine (Mem0, Redis AMS) lacks OTel, KAOS wraps it to emit native spans rather than accepting the gap.

## Capabilities the surveyed tools do not (yet) fully provide

Per this document's remit, the target names desirable capabilities even where no single surveyed tool delivers them today:

- **Unified multi-tier memory behind one declarative resource.** No surveyed tool offers working + episodic + semantic + profile + temporal-graph + procedural memory as one coherent, CRD-configured surface; KAOS's interface is the place to compose them.
- **Native Kubernetes/CRD-driven memory orchestration.** None of the tools ships a Kubernetes operator or first-class CRD; this is uniquely KAOS's contribution and a differentiator.
- **Procedural / self-editing memory tied to the agent lifecycle.** Largely absent from the dedicated layers; a target capability that connects memory to KAOS's agent and A2A model.
- **Cross-agent / organizational memory for A2A fleets.** Shared, governed memory across delegating agents is under-served by per-user-centric tools and is a natural KAOS extension.
- **Calibrated, auditable consolidation and forgetting as policy.** Tools implement pieces (Zep invalidation, LangMem consolidation, recency decay), but a unified, declarative, auditable retention/forgetting policy is a target KAOS should own.
- **OTel-native instrumentation across whichever engine is plugged in.** A KAOS-level guarantee independent of the backend's own observability maturity.

## Migration from today

The path from the current implementation ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)) to this picture is additive and backward-compatible.

- **Keep working memory.** The existing local/Redis conversation log remains the working-memory tier; fix its fidelity (replay tool calls, summarize instead of truncate) and concurrency hazards.
- **Add a long-term tier behind the interface.** Introduce the long-term sub-interface and a first backend — Mem0 (primary) or Redis AMS (secondary) per [KAOS-R6](./KAOS-R6-tool-selection.md) — running extraction/consolidation as background jobs. Agents opt in via configuration; existing agents keep working unchanged.
- **Introduce the `MemoryStore` CRD.** Move backend configuration out of per-Agent env into a referenceable resource reconciled by the operator, with secret-based credentials and policy fields.
- **Grow into the higher tiers.** Add user/entity profiles, then the temporal-graph tier (Graphiti-class) when relational/temporal recall is justified, then procedural and organizational memory — each as a new backend capability behind the stable interface, never a rewrite.
- **Harden governance.** Layer in authentication on memory endpoints, per-tenant isolation modes, quotas, encryption, audit, export/backup, and erasure as the tiers mature.

The result is an engine-agnostic, capability-tiered, Kubernetes-native memory subsystem: KAOS owns a clean declarative interface and control plane, plugs in the best available long-term engine (today Mem0 or Redis AMS, tomorrow a graph engine), and delivers the full long-term memory ladder — retrieval, consolidation, forgetting, profiles, temporal knowledge, and procedural memory — that [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) shows is entirely absent today, expressed in the vocabulary [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) shows the field has converged on.

## Context manifest

In scope (read for this document): the requirements baseline [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) (the authoritative source of current capabilities, gaps, and the CRD/runtime surfaces being extended); the ecosystem best practice [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) (the taxonomy, operations, and patterns the target must speak); and, as informing-but-not-limiting input, the selection and deep dives [KAOS-R5-1](./KAOS-R5-1-mem0.md) through [KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md) and [KAOS-R6](./KAOS-R6-tool-selection.md).

Out of scope (intentionally excluded): vendor-specific implementation detail beyond what illustrates a target capability, and any commitment to a single engine — the target is engine-agnostic by design. This document describes the ideal end state, not a sequenced delivery plan; the migration section sketches direction only.
