# KAOS-R5-4 — Memobase deep dive

This is a per-tool deep evaluation of Memobase, the profile-first candidate shortlisted in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md). It assesses Memobase against the requirements baseline in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and the ecosystem patterns in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). Scope and sources are in the [Context manifest](#context-manifest). Vendor figures are flagged where KAOS cannot independently confirm them.

## At a glance

- **What it is:** an Apache-2.0, **user-profile-based** memory backend. Rather than indexing conversation chunks, it distills each user into a structured, schema-controlled profile (topics → sub-topics → values) plus a timeline of tagged events, and serves a ready-to-inject memory string with no LLM on the read path.
- **License:** Apache-2.0 (Memobase / `memodb-io`); a managed Memobase Cloud exists, with no code-level feature gating between OSS and cloud.
- **Form factors:** a self-hostable FastAPI server with Postgres (pgvector) + Redis, SDKs in Python/Node/Go, an OpenAI-compatible proxy wrapper, and an MCP server.
- **Backing/maturity:** the memodb-io company; **pre-1.0** (~0.0.40 at time of research) with a roughly biweekly release cadence and occasional breaking schema migrations.

## Architecture

Memobase separates a fast write path from an amortized extraction path. A client inserts a `ChatBlob` (OpenAI-style message list) which is stored immediately in Postgres and appended to a per-user **buffer zone**; the insert returns at once with **no LLM call**. The buffer accumulates until a token-size or idle-time threshold is crossed, at which point a **flush** (automatic, explicit, or on session close) enqueues the buffer to a **Redis queue** and a background worker — holding a **Redis distributed lock** for single-worker-per-user processing — runs the LLM extraction pipeline. The LLM output updates structured `user_profiles` rows and writes a `user_events` row; the raw blob is deleted by default and the Redis profile cache is invalidated. Source: `controllers/buffer_background.py`, `models/database.py`.

The distinctive property is that **the expensive work is asynchronous and off the agent hot path**, and **reads are pure SQL** (plus an optional Redis cache hit), giving very low retrieval latency. This is the profile-first, user-centric end of the design space — architecturally distinct from the retrieval-centric (Mem0, [KAOS-R5-1](./KAOS-R5-1-mem0.md)) and graph (Graphiti, [KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md)) candidates.

## Memory model

Each user has a set of **profile slots** (`user_profiles`: a `content` fact plus `{topic, sub_topic}` attributes), governed by a fully configurable topic/sub-topic schema in `config.yaml` (built-ins cover basic info, demographics, education, work, interests, psychology; deployments add or overwrite slots with extraction hints and merge semantics). When a topic grows past a cap, a re-organization LLM pass fires. Alongside profiles, **events** (`user_events`) carry structured deltas, summaries, semantic **tags** (e.g. `emotion::happy`, `goal::buy_a_house`), timestamps, and an optional pgvector embedding; fine-grained **event gists** (`user_event_gists`) are the unit of semantic search. All events are timestamped and filterable by time window. Source: `models/database.py`, Memobase event/profile docs.

This delivers exactly the **cross-session, per-user memory** that [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) identifies as missing — and does so as compact, human-readable structured state rather than opaque vectors — but it deliberately does **not** model relationships between facts or entities (no knowledge graph).

## APIs and SDK

The REST API (`/api/v1/...`, bearer auth) covers blob insert, buffer flush/capacity, profile get/update, event get and **semantic search** (events, gists, tags), and the primary `GET /users/context/{user_id}`. The `context()` call is the headline retrieval surface: it runs profile and event-gist retrieval in parallel, applies a token budget split between profiles and events, supports topic preferences/filters and a time window, optionally re-ranks events against recent `chats` via pgvector, and returns a formatted memory block ready to prepend to a prompt (with a customizable template). SDKs exist for Python, Node, and Go, plus an `openai_memory(...)` proxy that auto-injects context and captures turns. Source: `controllers/context.py`, `api.py`, Memobase docs.

## Storage backends

All persistent state lives in **PostgreSQL** (`pgvector/pgvector:pg17`): projects, users (composite PK with `project_id`), blobs, buffer zones, profiles, events, and event gists, with Alembic migrations and pgvector auto-created at startup. **Redis** provides the async buffer queue, per-user processing locks, and the profile cache. Embeddings (OpenAI `text-embedding-3-small` by default, also Jina or Ollama) are used **only** for event-gist semantic search, not for profiles, and can be disabled. The LLM is any OpenAI-compatible endpoint (default `gpt-4o-mini`), called only during flush. Source: `connectors.py`, Memobase config docs.

For KAOS this stack is **Postgres + Redis** — KAOS already supports Redis for its current distributed memory, so the incremental infrastructure is essentially a Postgres-with-pgvector instance, smaller than the graph-database delta of Graphiti/Cognee.

## Retrieval

Profiles are retrieved by SQL (Redis cache → `SELECT ... ORDER BY updated_at`), then prioritized/filtered by topic and truncated to budget — a **lexical, not semantic** profile filter. Events are retrieved either by recency or, when recent `chats` and embeddings are present, by pgvector cosine search over event gists. Context assembly formats both into a single string. Read latency is claimed sub-100ms for profile-only context and ~0.5–1s when semantic event search runs (vendor-stated). This is the lowest-latency read path of the shortlist, at the cost of a narrower (profile + tagged-event) recall model.

## Deployment and Kubernetes fit

The official deployment is **Docker Compose** (pgvector + Redis + the API server), with a single image (`ghcr.io/memodb-io/memobase`) usable against external Postgres/Redis. There is **no Helm chart or Kubernetes manifest** in the repo, though the server has some k8s awareness (a `POD_IP` telemetry attribute). A KAOS deployment would author a Deployment + ConfigMap (`config.yaml`) + Secrets against a managed/clustered Postgres-with-pgvector and Redis. Source: `src/server/docker-compose.yml`, `src/server/readme.md`.

## Pydantic AI integration path

No native Pydantic AI plugin exists. The natural KAOS integration is a `MemobaseMemory(Memory)` backend wrapping the Python SDK: call `user.insert()` on each turn and `user.flush()` at session boundaries on the write side, and `user.context()` on the read side, injecting the returned memory block as a system-prompt prefix — closely matching how the `openai_memory` proxy already works. Because extraction is async/off-hot-path, write integration is cheap; the main mapping work is tenant scoping (see below). The previously unstated assumption of a Pydantic-AI-specific adapter is **unverified/absent**.

## Multi-tenancy and isolation

Memobase has a single-level tenancy concept — **Projects** (org-like), with every user scoped by `project_id`. But the **open-source server is effectively single-project**: it auto-creates one root project, the `Project` table is nearly immutable, and the whole instance is guarded by **one shared `ACCESS_TOKEN`** with no per-project token isolation. Proper multi-tenancy is a Cloud-tier capability. For KAOS's multi-tenant fleets this is a **material limitation**: isolation between tenants would have to be enforced by running multiple instances or by KAOS-side scoping conventions, not by Memobase's own auth. Source: `database.py` event listeners, `connectors.py`, `api.py`.

## Scaling and performance

The design scales reads well (O(1) insert, SQL reads, Redis cache) and amortizes LLM cost by buffering turns before a flush (~3 LLM calls per flush in recent versions, a deliberate cost reduction). The Postgres connection pool is sized for concurrency (≈125 max). Vendor benchmarks claim ~5× cheaper/faster than Mem0 on a long real-world chat and temporal-QA leadership on LOCOMO — **self-reported and unverified**. Embedding dimension is **locked at initialization**, so changing embedding models requires a data migration.

## Observability

Strong and KAOS-aligned: built-in **OpenTelemetry + Prometheus**, with a Prometheus exporter and FastAPI request instrumentation emitting request, LLM-invocation, token-count, and latency metrics, plus structured JSON logging correlated by `project_id`/`user_id` and a per-project usage/billing API. There is no full distributed-tracing span tree beyond the metrics, but the LLM-cost and latency metrics are exactly what KAOS would want to monitor a memory layer. Source: `telemetry/open_telemetry.py`.

## Licensing and open-core split

Apache-2.0 with **no code-level feature gating** between OSS and Cloud — the split is purely operational (managed infra vs self-run). This is a clean licensing posture for KAOS adoption, comparable to Cognee and ahead of the proprietary-backend Zep Cloud.

## Maturity and ecosystem

Actively developed (biweekly releases) with complete multi-language SDKs, an MCP server, and integrations (LiveKit, Dify, Ollama, the OpenAI patch). But it is **pre-1.0**, with breaking schema migrations between minor versions, undisclosed production users, and a deliberately narrow scope. Star count was not directly confirmed.

## Gaps versus KAOS needs

Mapping to [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md):

- **Closes:** cross-session, per-user long-term memory as compact structured profiles; time-aware tagged events with semantic search; an extremely fast, LLM-free read path; OTel+Prometheus observability aligned with KAOS; a modest Postgres+Redis footprint that reuses KAOS's existing Redis support; and a fully Apache-2.0, non-gated posture.
- **Leaves open or adds cost:** no knowledge graph / entity-relationship recall (facts are flattened into independent slots); profile retrieval is lexical, not semantic; **weak self-hosted multi-tenancy** (single shared token, near-immutable single project) that conflicts with KAOS's multi-tenant model; no Helm/K8s packaging; pre-1.0 stability with breaking migrations; embedding-dimension lock-in; and self-reported, unverified benchmarks.
- **Architectural note:** Memobase is a long-term **profile** layer; it complements rather than replaces KAOS's working-memory conversation log, and its profile-first model is the narrowest-but-cheapest of the shortlist.

## Context manifest

In scope (read for this document): the Memobase deep-research findings (`memodb-io/memobase` source paths and `docs.memobase.io` pages cited inline); the KAOS requirements baseline [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md); the ecosystem patterns [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md); the shortlist rationale [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md); and the Mem0, Zep/Graphiti, and Cognee deep dives ([KAOS-R5-1](./KAOS-R5-1-mem0.md), [KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md), [KAOS-R5-3](./KAOS-R5-3-cognee.md)) for cross-comparison.

Out of scope (intentionally excluded): the remaining shortlisted tool (its own R5 document), the final selection ([KAOS-R6](./KAOS-R6-tool-selection.md)), and the target design ([KAOS-R7](./KAOS-R7-target-picture.md)). Vendor benchmark and latency figures are reported as self-reported/unverified.
