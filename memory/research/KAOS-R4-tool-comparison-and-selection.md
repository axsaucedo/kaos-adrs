# KAOS-R4 — Shortlist, comparison, and selection for deep evaluation

This document narrows the broad catalogue in [KAOS-R3](./KAOS-R3-memory-tooling.md) to a small set of candidates worth deep evaluation, alongside the KAOS custom implementation as a baseline. It explains the screening logic, gives a high-level summary of each shortlisted option, presents a first-pass comparison matrix, and records which candidates advance to per-tool deep dives. It builds on the requirements baseline in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and the patterns in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). The in-scope inputs are listed in the [Context manifest](#context-manifest).

This is a first-pass screen, not the final decision. The final selection (top one or two) is made in [KAOS-R6](./KAOS-R6-tool-selection.md) after the deep dives, against criteria derived explicitly from KAOS requirements.

## Screening logic

KAOS is Kubernetes-native, multi-tenant, self-hostable, with a Pydantic AI (Python) data plane behind a clean pluggable `Memory` interface and a Go operator control plane (see [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)). From the ~38 entries in [KAOS-R3](./KAOS-R3-memory-tooling.md), candidates were screened on hard and soft filters.

Hard filters (a candidate must pass all):

- **Self-hostable in a customer Kubernetes cluster.** This eliminates SaaS-only services (Zep Cloud as a product, Mem0 Platform, Letta Cloud, OpenAI memory, Pinecone, Pinecone Assistant, Vertex Memory Bank) as primary options, though their OSS counterparts remain in scope.
- **A dedicated memory layer, not merely a substrate or a whole agent framework.** This sets aside pure vector/graph substrates (pgvector, Qdrant, Weaviate, Milvus, Chroma, LanceDB, Neo4j, FalkorDB) — they are backend choices within a design, not the memory layer — and framework-native memory (LangMem, LlamaIndex, CrewAI, Semantic Kernel, Haystack, ADK) whose adoption would import a second agent runtime competing with KAOS's own.
- **Currently maintained.** This drops Memary (unreachable repo, minimal maintenance) and AutoGen memory (maintenance mode).

Soft filters (used to rank and balance the shortlist):

- Permissive licensing (Apache/MIT preferred; AGPL/SSPL/GPL weighted as distribution risk).
- Low infrastructure delta relative to what KAOS already runs (notably Redis).
- Coverage of the long-term capabilities KAOS lacks (semantic retrieval, summarization/consolidation, cross-session/user memory, knowledge structuring, forgetting).
- Architectural diversity, so the deep dives compare genuinely different approaches (vector-first, graph-first/temporal, hybrid, profile-first, Redis-native) rather than five variations of one.
- Alignment with KAOS operability concerns (multi-tenancy isolation, observability/OTel, a clean server/REST or embeddable boundary that fits behind the `Memory` ABC).

## Shortlist

Five external candidates advance to deep evaluation, chosen for architectural diversity and KAOS fit, plus the KAOS-custom baseline.

### Mem0 (vector-first dedicated layer)

The most widely adopted OSS dedicated memory layer. Apache-2.0, ships an embeddable library and a Compose/Docker self-host server, multi-level memory (user/session/agent), multi-signal retrieval, background extraction, and configurable vector backends (Qdrant default, pgvector, others). Strong reported long-term benchmarks (vendor-stated). Represents the mainstream vector-first approach and is the natural "default adopt" candidate to beat.

### Zep / Graphiti (graph-first, temporal knowledge graph)

The leading temporal-knowledge-graph approach, with strong published results (DMR, LongMemEval; see [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md)). Graphiti is the Apache-2.0 OSS self-host engine (on Neo4j or FalkorDB); Zep Cloud is its managed twin and ships an official Pydantic AI integration. Represents the structured, time-aware, provenance-preserving end of the design space — the strongest contrast to vector-first.

### Cognee (hybrid graph + vector)

An Apache-2.0 OSS memory platform with an Extract–Cognify–Load pipeline producing a hybrid graph+vector store, explicit multi-tenant isolation, OTel tracing, and published Docker images with Compose profiles. Its multi-tenancy and observability posture map directly onto KAOS operability requirements, and its hybrid model sits between Mem0 and Graphiti.

### Memobase (profile-first)

An Apache-2.0 OSS layer built around structured, schema-controlled user profiles plus event timelines, with very low-latency SQL-based profile retrieval (no embedding on the hot path) on a FastAPI + Postgres + Redis stack. Represents the profile-first, user-centric approach — directly relevant to KAOS tenants modeled as persistent users, and architecturally distinct from the retrieval-centric options.

### Redis Agent Memory Server (Redis-native, two-tier)

An MIT OSS server providing two-tier (working + long-term) memory with configurable extraction strategies, semantic/keyword/hybrid search, and a REST + MCP interface, on Redis (RedisVL). Its decisive KAOS advantage is the **lowest infrastructure delta**: KAOS already supports Redis for its current distributed memory, so this option reuses existing operational surface. Represents the "extend what we already run" path realized as a dedicated server.

### KAOS custom implementation (baseline)

Carried as a first-class option: harden and extend the existing custom layer to production grade rather than adopt. Its deep evaluation already exists as [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md), so it is not repeated as a separate deep dive; it re-enters the comparison in [KAOS-R6](./KAOS-R6-tool-selection.md). Strengths: clean pluggable interface, native CRD configuration, an existing Redis backend, zero new dependencies. Gap: every long-term capability must be built.

### Honorable mentions (screened out, with reasons)

- **Letta (MemGPT):** strong stateful-memory model, but it is an opinionated agent runtime that persists full agent state and drives execution; adopting it would duplicate or conflict with KAOS's own Pydantic AI runtime and A2A model. Kept as a design reference, not a deep-dive candidate.
- **Honcho:** a compelling peer-centric, multi-tenant model that fits KAOS's multi-agent world well, but its **AGPL-3.0** license is a meaningful distribution-risk for a self-hosted, embedded component; revisit only if licensing is acceptable.
- **txtai:** an excellent embeddings-database substrate-plus-pipelines toolkit, but it provides primitives rather than an opinionated agent-memory model, so it overlaps more with the substrate layer than with the dedicated-memory decision.

## First-pass comparison matrix

Qualitative, for screening only; the rigorous scored comparison is in [KAOS-R6](./KAOS-R6-tool-selection.md). "Infra delta" is relative to what KAOS already runs (Redis present; Postgres/Neo4j would be new).

| Candidate | Architecture | License | Self-host server | Primary backend | Infra delta for KAOS | Long-term capabilities | Pydantic AI fit |
|-----------|--------------|---------|------------------|-----------------|----------------------|------------------------|-----------------|
| Mem0 | vector-first, multi-level | Apache-2.0 | yes (Compose/image) | Qdrant / pgvector | medium (vector store) | semantic + entity + temporal, background extraction | strong (Python SDK + REST) |
| Zep / Graphiti | temporal knowledge graph | Apache-2.0 (Graphiti) | yes (lib + MCP); Zep Cloud SaaS | Neo4j / FalkorDB | high (graph DB) | temporal KG, provenance, consolidation | strong (official Pydantic AI integration) |
| Cognee | hybrid graph + vector | Apache-2.0 | yes (images + Compose) | LanceDB/NetworkX → Neo4j/pgvector | medium–high | KG + vector, multi-tenant, OTel | good (Python + REST/MCP) |
| Memobase | profile-first + timeline | Apache-2.0 | yes (Dockerized) | Postgres + Redis | low–medium (Postgres) | user profiles, event timelines, time-aware | good (Python + REST) |
| Redis Agent Memory Server | Redis-native, two-tier | MIT | yes (multi-container) | Redis (RedisVL) | low (Redis already supported) | working + long-term, extraction strategies, hybrid search | good (Python + REST + MCP) |
| KAOS custom | conversation-log baseline | (KAOS) | n/a (in-runtime) | in-proc / Redis | none | none beyond bounded recency | native (it is the runtime) |

## Outcome — what advances

The following advance to standard-depth deep dives, one document and one commit each:

- `KAOS-R5-1-mem0.md`
- `KAOS-R5-2-zep-graphiti.md`
- `KAOS-R5-3-cognee.md`
- `KAOS-R5-4-memobase.md`
- `KAOS-R5-5-redis-agent-memory-server.md`

The KAOS custom baseline does not get a separate `KAOS-R5` document because its deep evaluation is [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md); it is carried into the final scored comparison in [KAOS-R6](./KAOS-R6-tool-selection.md). The deep dives apply a common structure — architecture, memory model, APIs, storage backends, retrieval, Kubernetes/deployment fit, Pydantic AI integration path, multi-tenancy, scaling, observability, licensing, maturity, and gaps versus KAOS needs — so they can be scored side by side.

## Context manifest

In scope: the tooling catalogue and self-host/Kubernetes matrix in [KAOS-R3](./KAOS-R3-memory-tooling.md), the KAOS requirements baseline in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md), and the architectural taxonomy and benchmark framing in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). Screening prioritized self-hostability, dedicated-layer scope, maintenance, licensing, infrastructure delta, capability coverage, and architectural diversity.

Out of scope (deferred): the per-tool deep dives themselves, independent benchmark verification, and the final scored selection and criteria, which are produced in [KAOS-R6](./KAOS-R6-tool-selection.md) after the deep dives.
