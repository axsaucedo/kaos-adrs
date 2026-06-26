# KAOS-R5-5 — Redis Agent Memory Server deep dive

This is a per-tool deep evaluation of the Redis Agent Memory Server (AMS), the Redis-native, two-tier candidate shortlisted in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md). It assesses AMS against the requirements baseline in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and the ecosystem patterns in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). Scope and sources are in the [Context manifest](#context-manifest). Vendor claims are flagged where KAOS cannot independently confirm them. Its decisive distinguishing axis for KAOS — the infrastructure delta relative to the Redis KAOS already runs — is treated explicitly at the end.

## At a glance

- **What it is:** an **official Redis Inc.** memory-layer microservice giving agents a **two-tier** model — session-scoped *working memory* and cross-session *long-term memory* — over Redis Stack (RediSearch) as the vector and document store, with a REST API, an MCP server, and a Python client.
- **License:** **Apache-2.0** (correcting [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md), which provisionally recorded MIT). GitHub's SPDX detection reports "Other" but the LICENSE file is Apache-2.0.
- **Form factors:** one Docker image run as up to three processes (REST API on 8000, MCP on 9000, background task-worker), all pointing at the same Redis.
- **Backing/maturity:** maintained by Redis Inc.; created early 2025; modest stars and **no tagged releases** yet despite "production-ready" marketing — effectively pre-1.0 in cadence.

## Architecture

AMS implements an explicit **two-tier memory model**. *Working memory* is session-scoped Redis state holding the message list, structured memory records, a progressively-summarized `context` field, arbitrary session JSON, scoping fields, and an optional TTL. *Long-term memory* is cross-session, persisted as Redis HASH documents indexed by a RediSearch **HNSW** vector index. Records flow from working to long-term by **promotion**: when a client writes working-memory records with `persisted_at=null`, the server deduplicates by content hash, embeds via LiteLLM, and indexes them; configurable extraction strategies (discrete, summary, preferences, custom) can also run as **background tasks** (via a Redis-backed Docket queue) that mine messages into discrete memories. Window management progressively summarizes older messages into `context` once a fraction of the model's context window is reached. Source: AMS working-memory and long-term-memory docs, `summarization.py`, `extraction.py`.

This two-tier shape is the closest of the shortlist to **KAOS's own model**: KAOS already has a session-scoped working memory (the conversation log of [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)); AMS keeps that tier and adds the long-term, semantic, cross-session tier KAOS lacks — rather than replacing the working tier with a different paradigm.

## Memory model

The long-term unit is `MemoryRecord`: `text`, a `memory_type` of `semantic | episodic | message`, `topics[]` and `entities[]` (indexed TAG fields), `user_id`/`namespace`/`session_id` scoping, `created_at`/`last_accessed`/`event_date` timestamps, `access_count`, a `memory_hash` for dedup, an `extraction_strategy`, a `pinned` flag (prevents forgetting), and freeform `metadata`. The RediSearch schema indexes text (BM25), all tags, the numeric timestamps and access count, and a 1536-dim cosine HNSW vector. Deduplication is both **hash-based** (exact text) and **semantic** (vector-similarity + LLM merge, run on a compaction schedule). Source: `agent-memory-client/models.py`, `memory_vector_db_factory.py`.

This supplies the long-term semantic/episodic memory, topic/entity structuring, recency/access tracking, and explicit pin-based retention that [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) lists as missing — while keeping the storage model in Redis, which KAOS already understands operationally.

## APIs and SDK

The REST API (`/v1`) covers working memory (`GET`/`PUT`/`DELETE /working-memory/{session_id}`, list), long-term memory (`POST` create, `POST /search`, `GET`/`PATCH`/`DELETE` by id), lifecycle endpoints (`/forget`, `/compact`, `/summary-views`, `/tasks`), and crucially a **prompt-hydration endpoint** (`POST /v1/memory/prompt`) that takes a query plus session/long-term-search config and returns a ready-to-use `messages[]` array with working-memory context and long-term search results already merged — one-call context assembly. The MCP server exposes seven tools mapping to those endpoints (stdio or SSE). A Python client (`agent-memory-client`) wraps the REST API; a LangChain tool adapter ships, but **no native Pydantic AI adapter**. Source: `api.py`, `mcp.py`, AMS MCP docs.

## Storage backends

The default and intended store is **Redis via RedisVL** (`redisvl>=0.6.0`): HASH documents, RediSearch HNSW (or FLAT) vectors, and BM25 full-text — which **requires Redis Stack** (`redis/redis-stack-server`, i.e. Redis with the RediSearch/RedisJSON modules), not plain Redis. Redis Cluster is supported via `redis+cluster://`. A `MEMORY_VECTOR_DB_FACTORY` hook allows alternative vector databases (Pinecone/Chroma/Postgres are *mentioned*), but **no adapters ship** — those are user-implemented. Embeddings go through **LiteLLM** (default `text-embedding-3-small`; OpenAI, Bedrock, Ollama), aligning with KAOS's LiteLLM/ModelAPI story. Source: `memory_vector_db_factory.py`, `pyproject.toml`.

## Retrieval

Search offers three modes — **semantic** (HNSW cosine), **keyword** (RediSearch BM25), and **hybrid** (weighted blend via `hybrid_alpha`) — with rich AND-combinable filters on `user_id`, `namespace` (supports `startswith` for hierarchical tenancy), `memory_type`, `topics`/`entities` (`any`/`all`), `session_id`, and time ranges. A configurable **recency boost** combines semantic score with recency/freshness/novelty weights and exponential decay half-lives, and an optional **LLM query-rewriting** step precedes vector search. This is a strong, production-shaped retrieval surface that directly serves the relevance-and-recency-aware recall [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) recommends. Source: `filters.py`, AMS long-term-memory docs.

## Deployment and Kubernetes fit

Published images (`redislabs/agent-memory-server`, plus an AWS Bedrock variant) run as up to three processes from one image: the REST API, the MCP server, and a background **task-worker** (a `--task-backend=asyncio` mode collapses the worker into the API for development). Production wants separate API and task-worker containers against Redis Stack. There is **no official Helm chart** — Kubernetes deployment is manual (API Deployment, task-worker Deployment, Redis Stack, optional MCP, with auth enabled). Source: `docker-compose.yml`, `Dockerfile`, AMS configuration docs.

## Pydantic AI integration path

No native Pydantic AI adapter ships. Two clean KAOS paths exist: (1) a `RedisAgentMemory(Memory)` backend wrapping the REST/Python client — call `search_long_term_memory` (or the `memory_prompt` hydration endpoint) on read and create/promote records on write; or (2) run the **MCP server as a sidecar** and let agents consume the seven memory tools natively. Because AMS already models a working tier, KAOS could either delegate both tiers to AMS or keep its existing working-memory backend and use AMS only for the long-term tier. As with the other candidates, extraction/summarization invoke an LLM, so the heavy work should be the background task-worker rather than the inline write.

## Multi-tenancy and isolation

Scoping is via indexed TAG fields — `namespace` (logical partition for app/team/tenant, with `startswith` enabling hierarchical namespaces), `user_id`, and `session_id` — all AND-combinable in filters. There is **no built-in RBAC or API-level tenant isolation** beyond field filtering, so the integrating application must enforce namespace/user hygiene. This is the same application-level isolation posture as Mem0 ([KAOS-R5-1](./KAOS-R5-1-mem0.md)), and notably **stronger and more flexible than Memobase's single-token self-hosted model** ([KAOS-R5-4](./KAOS-R5-4-memobase.md)), though weaker than Cognee's per-dataset ACLs and Graphiti's database-per-group isolation.

## Scaling and performance

The hot path (working-memory get/put, vector search) hits Redis directly, inheriting Redis latency; HNSW scales ANN search to large record counts; the stack is async throughout; and background extraction scales via horizontally-scalable Docket workers, with Redis Cluster supported for both data and the work queue. **No benchmarks are published.** The cost center, as with every candidate, is the LLM calls behind extraction, summarization, semantic dedup, and query rewriting.

## Observability

Structured JSON logging via `structlog` with a health endpoint, but **no OpenTelemetry** — no tracing, no metrics endpoint, no spans. This is a confirmed gap against KAOS's OTel-centric observability ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)) and a weaker posture than Cognee, Graphiti, or Memobase; integrating AMS would require KAOS to add its own instrumentation. Source: `logging.py`.

## Licensing and open-core split

Apache-2.0 and an official Redis Inc. project — a clean, low-risk licensing posture (and a correction to the MIT note in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md)). It is the higher-level application layer above RedisVL (Redis's vector-search SDK). There is no obvious feature-gated open-core split; the commercial angle is Redis's broader managed offering rather than withheld AMS features.

## Maturity and ecosystem

Backed by Redis Inc. with good documentation, but young: created in 2025, modest stars, a meaningful open-issue count, **no semver-tagged releases**, and a narrow Python `>=3.12,<3.13` constraint. A pinned-LLiteLLM note referencing a supply-chain incident shows active dependency hygiene but also the churn of a young project. "Production-ready" is claimed but not yet reflected in release cadence.

## Infrastructure delta for KAOS (decisive axis)

KAOS already runs a Redis memory backend on plain `redis:7-alpine` (session hashes, event lists, a sorted-set index, TTL cleanup, pipelined writes — see [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)). Adopting AMS therefore has the **smallest conceptual delta** of the shortlist, but it is **not zero**:

- **Redis Stack required.** AMS needs `redis/redis-stack-server` (RediSearch/RedisJSON), not plain Redis. Redis Stack is backward-compatible with KAOS's existing `HSET`/`RPUSH`/`ZADD` usage (same port, separate `memory_idx:*` keyspace), so the upgrade is additive — but it is still an image/operational change KAOS's operator-level Redis default would need to make.
- **A new AMS service** (API, plus a task-worker for production, optional MCP) layered on that Redis.
- **An LLM key** for the intelligent features (none needed for pure storage).

The honest framing is that AMS **reuses KAOS's storage technology and two-tier mental model** more than any other candidate, but the "we already run Redis" advantage is partial: it is *Redis the technology* that is shared, while AMS still adds a Redis Stack dependency, new workloads, and LLM-backed write costs.

## Gaps versus KAOS needs

Mapping to [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md):

- **Closes:** long-term semantic/episodic memory, relevance + recency retrieval (semantic/keyword/hybrid with rich filters), summarization/consolidation, topic/entity structuring, cross-session/per-user memory, explicit pin-based retention, a built-in two-tier model matching KAOS's working/long-term split, and LiteLLM model access aligned with KAOS — all on Redis, the storage KAOS already operates.
- **Leaves open or adds cost:** requires Redis Stack rather than plain Redis; **no OpenTelemetry** (must add instrumentation); no official Helm chart; no tagged releases / young project; application-level-only tenant isolation; per-write LLM cost for extraction/summarization; no shipped alternative vector backends despite the hook; and no native Pydantic AI adapter (REST or MCP sidecar instead).
- **Architectural note:** uniquely, AMS could serve *both* tiers or just the long-term tier, making it the most natural incremental extension of KAOS's existing Redis memory rather than a parallel paradigm.

## Context manifest

In scope (read for this document): the AMS deep-research findings (`redis/agent-memory-server` source paths and `redis.github.io/agent-memory-server` docs cited inline); the KAOS requirements baseline [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md), especially its description of the existing Redis backend; the ecosystem patterns [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md); the shortlist rationale [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md); and the other four deep dives ([KAOS-R5-1](./KAOS-R5-1-mem0.md), [KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md), [KAOS-R5-3](./KAOS-R5-3-cognee.md), [KAOS-R5-4](./KAOS-R5-4-memobase.md)) for cross-comparison.

Out of scope (intentionally excluded): the final selection ([KAOS-R6](./KAOS-R6-tool-selection.md)) and the target design ([KAOS-R7](./KAOS-R7-target-picture.md)). Maturity counts and the "production-ready" claim are reported as vendor-stated/unverified; the license is corrected to Apache-2.0.
