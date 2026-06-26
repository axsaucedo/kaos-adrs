# KAOS-R5-1 — Mem0 deep dive

This is a per-tool deep evaluation of Mem0, the vector-first dedicated memory layer shortlisted in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md). It assesses Mem0 against the requirements baseline in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and the ecosystem patterns in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). The scope and sources for this document are listed in the [Context manifest](#context-manifest). Vendor-stated benchmark and maturity figures are flagged as approximate or unverified where KAOS cannot independently confirm them.

## At a glance

- **What it is:** the most widely adopted open-source dedicated agent-memory layer — an LLM-driven extraction-and-retrieval store that turns conversation turns into discrete, searchable "memories" scoped by user, agent, and run.
- **License:** Apache-2.0 (`pyproject.toml`, `LICENSE`). Open-core: a managed Mem0 Platform (SaaS) adds webhooks, export, full graph memory, analytics, org/workspace governance, and managed HA on top of the OSS core.
- **Form factors:** an embeddable Python library (`pip install mem0ai`), a self-hostable FastAPI server with a Next.js dashboard, and the managed Platform. A TypeScript SDK and an MCP server (OpenMemory, being sunset) also exist.
- **Backing/maturity:** mem0.ai (YC S24); one of the highest-starred memory repos (vendor/badge figures suggest ~30–40k GitHub stars, exact count unverified); very active release cadence.

## Architecture

Mem0 ships in three deployment modes from one codebase: the embeddable library (`from mem0 import Memory`), a self-hosted server (`server/`, FastAPI + Postgres/pgvector + dashboard, `uvicorn` on port 8000), and the managed Platform (`from mem0 import MemoryClient`). Source: repository README; `docs.mem0.ai/open-source/overview`.

The core is an LLM-mediated write pipeline. On `add()`, Mem0 extracts salient facts from incoming messages with an LLM, embeds them, and persists them to a vector store, with a SQLite-backed history/audit table recording changes. Historically (the long-documented model) the LLM classified each candidate against existing related memories and emitted `ADD` / `UPDATE` / `DELETE` / `NONE` operations, giving Mem0 its signature self-updating, contradiction-resolving behaviour. Vendor changelog material describes a later single-pass "ADD-only" algorithm revision plus built-in entity linking and the removal of the external graph store from OSS; those revision specifics are vendor-stated and future-dated relative to this research and should be treated as unverified — but the load-bearing architectural fact for KAOS is stable: **Mem0 is a vector-first store whose writes are gated by one or more LLM calls.**

## Memory model

A stored memory (`MemoryItem`, `mem0/configs/base.py`) is a short extracted fact string with a UUID `id`, a dedup `hash`, arbitrary `metadata`, optional `score` (on search results), and `created_at`/`updated_at` timestamps. Scope is expressed by three orthogonal identifiers attached as payload fields: `user_id` (the human), `agent_id` (the AI agent), and `run_id` (a conversation/session run). A separate SQLite `history` table records the change log per memory (`old_memory`, `new_memory`, `event`, `actor_id`, `role`), and a `messages` table retains a short recent-message window per scope.

This is exactly the long-term, cross-session, per-user capability that [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) identifies as missing: memories persist independently of any single session and are recalled by relevance, not recency.

## APIs and SDK

The Python `Memory` class (and async `AsyncMemory`) exposes `add`, `search`, `get_all`, `get`, `update`, `delete`, `delete_all`, `history`, and `reset` (`mem0/memory/main.py`). `add()` defaults to `infer=True`, meaning every write triggers LLM extraction.

The self-hosted server mirrors this over REST: `POST /memories`, `GET /memories` (with `user_id`/`agent_id`/`run_id`/`top_k` filters; unfiltered listing is admin-only), `GET/PUT/DELETE /memories/{id}`, `POST /search`, `GET /memories/{id}/history`, admin `DELETE /memories` and `POST /reset`, plus `/configure`, `/auth/*`, `/api-keys/*`, and `/api/health`. Auth is JWT + `X-API-Key`. Source: `server/main.py`.

## Storage backends

Mem0 is deliberately backend-agnostic on the vector tier, with a large adapter set (Qdrant — the library default; pgvector — the server default; plus Chroma, Pinecone, Milvus, Redis/RedisVL, Weaviate, Elasticsearch, OpenSearch, FAISS, Supabase, and many cloud vector services). LLM providers (~20: OpenAI, Anthropic, Azure, Bedrock, Gemini, Groq, Ollama, LiteLLM, vLLM, and others) and embedders (~15: OpenAI, HuggingFace/sentence-transformers, Gemini, Bedrock, Ollama, FastEmbed, and others) are equally pluggable. History is SQLite. Optional rerankers (Cohere, HuggingFace, LLM-based, SentenceTransformer) can be enabled. Source: `mem0/vector_stores/`, `mem0/llms/`, `mem0/embeddings/`, `mem0/reranker/`.

The pluggable-backend posture maps well onto KAOS: pgvector or Qdrant can be run as cluster services, and the Ollama/LiteLLM providers align with KAOS's existing ModelAPI proxy story.

## Retrieval

Retrieval is `search(query, user_id=..., filters=..., top_k=..., threshold=...)`, returning scored `MemoryItem`s. The baseline is cosine semantic search over the vector store with metadata filtering; vendor material describes a multi-signal variant adding BM25 keyword matching and entity linking with score fusion and time-aware ranking (the keyword/entity path requires the optional NLP extra and a spaCy model). Rerankers are available but off by default. This directly supplies the relevance-ranked recall [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) lists as absent.

## Deployment and Kubernetes fit

The server is a standard `python:3.12-slim` container fronted by `uvicorn`, with a three-service Docker Compose (API + `pgvector/pgvector:pg17` + Next.js dashboard). There is **no official Helm chart or Kubernetes manifest** in the repository — a Kubernetes deployment must be authored by hand (Deployment for the API, a managed/clustered Postgres or external Qdrant, secrets for provider keys). For KAOS this means a new first-class workload plus a vector store to operate; it is self-hostable but not turnkey on Kubernetes. Source: `server/Dockerfile`, `server/docker-compose.yaml`, `server/.env.example`.

A lighter alternative is **library mode**: embed `mem0ai` directly inside the Pydantic AI runtime process and point it at an external vector store, avoiding a separate server entirely.

## Pydantic AI integration path

Because the OSS `Memory` is a plain Python class, the cleanest KAOS integration is library mode behind the existing `Memory` ABC ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)): a `Mem0Memory(Memory)` backend would call `mem0.add(...)` on write and `mem0.search(...)` on read, mapping `user_id`/`session_id` to Mem0's scope identifiers and surfacing recalled facts either as additional `message_history` context or as a system-prompt memory block. This complements rather than replaces KAOS's existing conversation-log working memory: Mem0 becomes the long-term layer while the current backend keeps short-term turn continuity. Alternatively the self-hosted REST server can sit behind the same ABC via an HTTP client.

## Multi-tenancy and isolation

Isolation is **application-level**: every memory carries `user_id`/`agent_id`/`run_id`, and every query must pass the corresponding filters; there is no row-level security in the vector store, so a missing scope filter can leak across tenants. The server adds per-user API keys and admin-gated bulk operations. Org/workspace-level governance is Platform-only. For KAOS's multi-tenant fleets this is workable but places the isolation burden on the integrating code (the `Memory` backend must always inject tenant scope), which is consistent with how KAOS already namespaces Redis keys today.

## Scaling and performance

The vector store carries the scaling load and can be run as an HA cluster (Qdrant, pgvector). The FastAPI server holds a singleton in-process `Memory` instance and a per-container SQLite history file, so naive horizontal replication of the server needs care (shared Postgres is fine; SQLite history is a per-pod bottleneck with no Postgres-history option in OSS). The unfiltered all-memories listing is capped (≈1000 rows). Vendor benchmarks (LoCoMo, LongMemEval, BEAM) report strong accuracy with single-pass retrieval and ~1s p50 latency; these come from Mem0's own harness and are **approximate/unverified** for KAOS conditions.

The dominant runtime cost is the **per-write LLM call** (`infer=True`): high-frequency ingestion is expensive and adds latency on the write path, a material consideration for KAOS autonomous loops that emit many events.

## Observability

Telemetry is **PostHog-based, not OpenTelemetry** — there is no OTel trace/span/metric instrumentation in the OSS code (telemetry is opt-out via `MEM0_TELEMETRY=false`). The server logs HTTP requests to a Postgres table and injects a request id. This is a gap against KAOS's OTel-centric observability ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) notes KAOS already attaches trace context to memory events): integrating Mem0 would mean wrapping it to emit KAOS-native spans/metrics rather than inheriting them.

## Licensing and open-core split

Apache-2.0 core — permissive and safe to embed and redistribute, satisfying the R4 licensing filter. The open-core line places webhooks, memory export, full built-in graph memory, advanced filters, analytics, org/workspace governance, and managed HA in the paid Platform. None of those are blockers for a self-hosted KAOS adoption, but full graph memory and export being Platform-gated is worth noting for the target picture.

## Maturity and ecosystem

Very mature and widely adopted for an agent-memory project: large star count (vendor/badge figures ~30–40k, exact count unverified), frequent releases, a published evaluation harness, and broad framework integrations (LangChain, CrewAI, LlamaIndex, Vercel AI SDK) and IDE/agent plugins. Backed by a funded company (YC S24). The breaking algorithm revisions and the OpenMemory sunset indicate an actively-moving, not-yet-frozen API surface.

## Gaps versus KAOS needs

Mapping to [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md):

- **Closes:** semantic/long-term memory, relevance retrieval with filtering, cross-session and per-user memory, optional reranking, contradiction handling (in the operation-based write model), pluggable vector/LLM/embedder backends including options KAOS already aligns with (pgvector, Ollama, LiteLLM).
- **Leaves open or adds cost:** no official Helm/K8s packaging (new workload + vector store to operate); per-write LLM cost and latency; PostHog rather than OTel observability; application-level-only tenant isolation; SQLite history as a horizontal-scaling rough edge; full graph memory and export gated to the Platform; an actively-changing API/algorithm surface that introduces upgrade risk.
- **Architectural note:** Mem0 is a long-term layer, not a working-memory replacement — KAOS would run it alongside, not instead of, its current conversation-log backend.

## Context manifest

In scope (read for this document): the Mem0 deep-research findings (repository, `docs.mem0.ai`, server/library source paths cited inline); the KAOS requirements baseline [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md); the ecosystem patterns [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md); and the shortlist rationale [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md).

Out of scope (intentionally excluded): the other shortlisted tools (covered in their own R5 documents), the final cross-tool selection ([KAOS-R6](./KAOS-R6-tool-selection.md)), and the target design ([KAOS-R7](./KAOS-R7-target-picture.md)). Vendor-stated benchmark, star-count, and future-dated algorithm/release specifics are reported as approximate or unverified.
