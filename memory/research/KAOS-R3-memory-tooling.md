# KAOS-R3 — Memory tooling landscape

This document is a broad, deliberately wide inventory of memory tooling for LLM agents — open source and commercial — together with the KAOS custom implementation as a baseline option. Its goal is completeness: to surface as many genuinely relevant, currently maintained tools as possible so that the shortlist in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md) is drawn from a full field rather than a convenient few. It reads against the requirements baseline in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and the patterns and vocabulary in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md).

Each entry records purpose, category, license and hosting model, core memory capability, storage backends, self-host / Kubernetes viability, language/SDK, a maturity signal, and notable differentiators, with source links. For KAOS the **self-host / Kubernetes** axis is decisive: it runs a Pydantic AI (Python) data plane and a Go operator control plane, is multi-tenant, and must be deployable into a customer's own cluster, so SaaS-only options are noted but weighted accordingly.

A note on confidence: maturity figures (star counts, contributor counts) and vendor benchmark claims below are reported as **approximate and vendor-stated, not independently verified**. Several reflect fast-moving projects and should be re-checked at selection time. Items that could not be verified are flagged under [Gaps and uncertainties](#gaps-and-uncertainties). The in-scope sources are summarized in the [Context manifest](#context-manifest).

## Category 1 — Dedicated agent-memory layers

These are purpose-built memory systems (not general frameworks), the primary candidates for KAOS to adopt behind its existing `Memory` interface.

### Mem0 (`mem0ai/mem0`)

- Purpose: adaptive memory layer for personalized agents — add/search/update memories across user/session/agent scopes.
- License / hosting: Apache-2.0 library and self-hosted server; managed SaaS (`app.mem0.ai`). Both.
- Core capability: multi-signal retrieval (semantic + keyword + entity linking), temporal reasoning, entity extraction, multi-level memory (user/session/agent), background extraction pipeline.
- Storage backends: Qdrant (default local) + SQLite history; self-host server commonly Postgres + pgvector; configurable across Qdrant, Weaviate, Chroma, Pinecone, pgvector, Redis.
- Self-host / K8s: excellent — `docker compose` full stack, published image, embeddable via `pip install mem0ai`.
- Language/SDK: Python, TypeScript/JS, CLI.
- Maturity: widely adopted, very active, VC-backed (order ~10^4 stars; treat as approximate).
- Differentiators: strong reported results on LoCoMo/LongMemEval (vendor-stated; verify at selection); OSS benchmark harness published.
- Source: `https://github.com/mem0ai/mem0`, `https://docs.mem0.ai`.

### Graphiti (`getzep/graphiti`)

- Purpose: temporal context-graph engine that tracks how facts change over time with provenance.
- License / hosting: Apache-2.0 OSS library; self-host only (the managed form is Zep Cloud).
- Core capability: temporal knowledge graph with per-edge validity windows (true now vs was true), episode provenance, hybrid retrieval (semantic + keyword + graph traversal), Pydantic-model ontologies, incremental updates.
- Storage backends: Neo4j (graph) plus an embedding provider; FalkorDB also supported in the broader Zep stack.
- Self-host / K8s: good — Python library (`pip install graphiti-core`) and bundled MCP server; needs an accessible Neo4j; no official Helm chart.
- Language/SDK: Python; MCP server.
- Maturity: actively maintained, backed by the Zep team; arXiv paper `https://arxiv.org/abs/2501.13956`.
- Differentiators: the leading OSS option with true per-fact temporal validity; strong reported DMR/LongMemEval results (see [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md)).
- Source: `https://github.com/getzep/graphiti`.

### Letta (`letta-ai/letta`, formerly MemGPT)

- Purpose: stateful agent framework with persistent, self-editing memory blocks.
- License / hosting: Apache-2.0 OSS server; Letta Cloud managed. Both.
- Core capability: in-context memory blocks the agent edits directly, archival (vector) memory for overflow, full message-history persistence, agent-invoked memory tools (the MemGPT paging model).
- Storage backends: PostgreSQL (prod) / SQLite (default); archival vector index with pgvector.
- Self-host / K8s: good — REST API server (`pip install letta`), Docker image, SDKs; no official Helm chart.
- Language/SDK: Python, TypeScript.
- Maturity: large community, originates from the MemGPT research project.
- Differentiators: agent-as-memory-manager model; opinionated stateful-agent runtime (which is also a coupling concern for KAOS, since KAOS already owns the agent runtime).
- Source: `https://github.com/letta-ai/letta`, `https://docs.letta.com`.

### Cognee (`topoteretes/cognee`)

- Purpose: OSS memory platform that builds a self-hosted knowledge graph via an Extract–Cognify–Load (ECL) pipeline from documents, conversations, and structured data.
- License / hosting: Apache-2.0 OSS; Cognee Cloud managed. Both.
- Core capability: graph + vector hybrid storage, auto-ontology generation, multi-tenant isolation, OTel tracing, `remember`/`recall`/`forget`/`improve` API, session memory plus permanent KG.
- Storage backends: default LanceDB + NetworkX; supports Neo4j, pgvector, Qdrant, Weaviate.
- Self-host / K8s: excellent — published Docker images (`cognee/cognee`, `cognee/cognee-mcp`), Compose profiles for Postgres/Neo4j/UI/MCP.
- Language/SDK: Python (async), MCP server.
- Maturity: active; arXiv paper `https://arxiv.org/abs/2505.24478`.
- Differentiators: explicit multi-tenant isolation and OTel — both directly aligned with KAOS operability needs.
- Source: `https://github.com/topoteretes/cognee`, `https://docs.cognee.ai`.

### Memobase (`memodb-io/memobase`)

- Purpose: user-profile-based memory — structured user profiles plus event timelines, optimized for low-latency profile access.
- License / hosting: Apache-2.0 OSS server; Memobase Cloud. Both.
- Core capability: structured JSON user profiles, event timelines for temporal queries, controllable profile schema, time-aware memory; profile retrieval is SQL-only (no embedding on the hot path).
- Storage backends: FastAPI + Postgres + Redis.
- Self-host / K8s: good — fully Dockerized server with auth, caching, telemetry.
- Language/SDK: Python, Node.js, Go; REST API.
- Maturity: newer, active; vendor SOTA claim on LoCoMo (verify).
- Differentiators: profile-first design with very low retrieval latency; natural fit where KAOS tenants map to persistent user profiles.
- Source: `https://github.com/memodb-io/memobase`, `https://docs.memobase.io`.

### ReMe / MemoryScope (`agentscope-ai/ReMe`)

- Purpose: file-based long-term memory toolkit — Markdown memory nodes with wikilinks (formerly ModelScope MemoryScope).
- License / hosting: Apache-2.0; self-host only.
- Core capability: memory as Markdown files with frontmatter and wikilinks; auto-consolidation ("Auto Memory/Dream"); hybrid wikilink + BM25 + embedding search.
- Storage backends: filesystem (Markdown) + configurable embeddings.
- Self-host / K8s: good as a library/local service (`reme start`); K8s via Pod + PVC; no Helm chart.
- Language/SDK: Python 3.11+.
- Maturity: active; backed by the Alibaba/AgentScope team.
- Differentiators: human-readable, editable memory files; appealing for transparency but file-on-PVC storage is less natural for KAOS multi-replica concurrency.
- Source: `https://github.com/agentscope-ai/ReMe`.

### Memary (`memary` on PyPI)

- Purpose: long-term memory for autonomous agents using a Neo4j knowledge graph plus entity tracking.
- License / hosting: MIT; self-host only.
- Core capability: ReAct routing agent, KG creation/retrieval, memory stream and entity knowledge store, user persona management.
- Storage backends: Neo4j (required); optional Ollama/OpenAI.
- Self-host / K8s: library only (Streamlit demo); needs a separate Neo4j.
- Language/SDK: Python.
- Maturity: research-grade; the GitHub repo was unreachable during research and the package appears minimally maintained — treat as potentially unmaintained.
- Source: `https://pypi.org/project/memary/`.

### Honcho (`plastic-labs/honcho`)

- Purpose: memory infrastructure for stateful agents — reasoning-first memory that models changing "peers" (users, agents, groups).
- License / hosting: AGPL-3.0 OSS server; managed at `api.honcho.dev`. Both.
- Core capability: peer-centric model (workspaces → peers → sessions → messages), background LLM reasoning that extracts conclusions, multi-peer perspectives, BM25 + vector hybrid search, a `chat` endpoint to query about a peer.
- Storage backends: FastAPI server, PostgreSQL, Redis for queuing.
- Self-host / K8s: good — FastAPI server with Docker, configurable base URL.
- Language/SDK: Python, TypeScript; MCP server.
- Maturity: active, VC-backed lab; vendor "Pareto frontier" evals (verify).
- Differentiators: peer/multi-tenant model is unusually aligned with KAOS's multi-agent, multi-user, A2A-delegating world; note the AGPL license implications for distribution.
- Source: `https://github.com/plastic-labs/honcho`, `https://honcho.dev`.

### Redis Agent Memory Server (`redis/agent-memory-server`)

- Purpose: Redis-backed REST + MCP memory server with two-tier (working + long-term) memory.
- License / hosting: MIT OSS; self-host (requires Redis). 
- Core capability: working memory (session-scoped) plus persistent long-term memory; configurable extraction strategies (facts, summaries, preferences); semantic + keyword + hybrid search; topic/entity extraction; multi-provider LLM via LiteLLM.
- Storage backends: Redis (RediSearch / RedisVL), Redis 7.x+ or Redis Cloud.
- Self-host / K8s: excellent — multi-container Compose (api + worker + redis + mcp), published image.
- Language/SDK: Python server + client; LangChain integration; MCP.
- Maturity: backed by Redis; active.
- Differentiators: Redis-native, and KAOS already supports Redis for its current distributed memory — the lowest-friction infrastructure delta of the dedicated layers.
- Source: `https://github.com/redis/agent-memory-server`.

### txtai (`neuml/txtai`)

- Purpose: all-in-one embeddings database (dense + sparse vectors + graph + relational) for semantic search, RAG, and LLM orchestration; usable as a memory/embeddings layer.
- License / hosting: Apache-2.0 OSS; self-host.
- Core capability: embeddings database combining vector + SQL + graph, LLM pipelines (summarization, Q&A), REST + MCP APIs, workflows.
- Storage backends: in-memory / SQLite-backed file storage; external vector stores.
- Self-host / K8s: excellent — FastAPI server, Docker images, multi-language bindings.
- Language/SDK: Python core; JS/Java/Rust/Go REST bindings.
- Maturity: long-running, active, ~10^4 stars (approximate).
- Differentiators: a substrate-plus-pipeline toolkit rather than an opinionated agent-memory model; would require KAOS to build the memory semantics on top.
- Source: `https://github.com/neuml/txtai`.

## Category 2 — Framework-native memory

Memory embedded in agent frameworks. For KAOS these are mostly relevant as design references or embeddable libraries, since KAOS already provides its own agent runtime on Pydantic AI.

### Pydantic AI (`pydantic/pydantic-ai`)

- Purpose: the KAOS data-plane framework; provides message history only.
- License / hosting: MIT; embeddable.
- Core capability: `message_history` for short-term context, `ModelMessagesTypeAdapter` serialization, `conversation_id` correlation. No native vector/semantic/long-term/user memory.
- Self-host / K8s: embeddable library.
- Relevance: KAOS's current memory is effectively this pattern with persistence and bounded retention added (see [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)); any long-term capability must be layered above it, and several dedicated layers (e.g. Zep) ship Pydantic AI integrations.
- Source: `https://github.com/pydantic/pydantic-ai`, `https://pydantic.dev/docs/ai/`.

### LangGraph Store + LangMem (`langchain-ai/langgraph`, `langchain-ai/langmem`)

- Purpose: a persistent `BaseStore` for cross-thread long-term memory plus extraction/consolidation/search tools.
- License / hosting: MIT OSS; LangSmith managed deployment. Both.
- Core capability: namespaced key-value + vector store; hot-path memory tools and a background memory manager; profiles, collections, episodic, and procedural (prompt-optimization) memory types.
- Storage backends: in-memory or PostgreSQL (`AsyncPostgresStore`).
- Self-host / K8s: good — embeddable libraries with a Postgres backend.
- Maturity: heavily used; LangChain-backed.
- Relevance: the richest design reference for memory types and hot-path/background patterns; adopting it would pull in the LangGraph programming model, which is a coupling cost for a Pydantic AI runtime.
- Source: `https://github.com/langchain-ai/langmem`.

### LlamaIndex memory (`run-llama/llama_index`)

- Purpose: chat-history and long-term vector memory components.
- License / hosting: MIT; embeddable.
- Core capability: `ChatMemoryBuffer`, `VectorMemory`, `SimpleComposableMemory`, `ChatStore` with many backends (Redis, Postgres, DynamoDB, Azure, AlloyDB).
- Self-host / K8s: embeddable; backed by any deployed vector store.
- Relevance: widest vector-store support; useful as a reference for composable recent-plus-semantic memory.
- Source: `https://github.com/run-llama/llama_index`.

### CrewAI memory (`crewAIInc/crewAI`)

- Purpose: built-in short-term / long-term / entity / user memory for crews.
- License / hosting: MIT OSS; CrewAI Cloud. Both.
- Core capability: short-term RAG over Chroma, long-term task outcomes in SQLite, entity memory in Chroma, user memory via Mem0 integration; composite semantic+recency+importance scoring; hierarchical scope tree.
- Self-host / K8s: embeddable (in-process Chroma + SQLite).
- Relevance: a strong reference for the scope-tree and composite-scoring model; Mem0 as its user-memory backend is a notable signal.
- Source: `https://github.com/crewAIInc/crewAI`.

### Microsoft Agent Framework / Semantic Kernel / AutoGen

- Microsoft Agent Framework (`microsoft/agent-framework`): MIT; successor to AutoGen and Semantic Kernel; graph workflows with state checkpointing, OTel, memory via storage integrations (Azure AI Search, Cosmos DB); Python + .NET. New but production-positioned.
- Semantic Kernel (`microsoft/semantic-kernel`): MIT; `TextMemoryPlugin` plus the widest storage-connector ecosystem (Azure AI Search, Elasticsearch, Chroma, Qdrant, Redis, SQLite, Pinecone, pgvector, Weaviate, Mongo); being superseded by the Agent Framework.
- AutoGen / AG2 (`microsoft/autogen`, `ag2ai/ag2`): Apache-2.0; conversation-history memory and a teachable-agent vector extension; AutoGen is now in maintenance mode (migrate to the Agent Framework).
- Relevance to KAOS: primarily .NET/Azure-oriented references; limited direct fit for a Python/Pydantic AI runtime, though Semantic Kernel's connector breadth is instructive.

### Haystack memory (`deepset-ai/haystack`)

- Purpose: pipeline-based orchestration with composable memory components.
- License / hosting: Apache-2.0 OSS; deepset enterprise platform. Both.
- Core capability: `InMemoryChatMessageStore`, `ChatMessageRetriever`/`Writer` pipeline components, pluggable external document stores; `Hayhooks` to expose REST/MCP.
- Self-host / K8s: good — Python library with Docker and Hayhooks.
- Relevance: transparent, explicit memory-pipeline control; a reference rather than a drop-in for KAOS.
- Source: `https://github.com/deepset-ai/haystack`.

### Google ADK memory (`google/adk-python`)

- Purpose: ADK session state plus a `MemoryService` abstraction integrating Vertex AI Agent Engine Memory Bank.
- License / hosting: Apache-2.0 ADK library; Memory Bank is GCP-managed only.
- Core capability: session state, `MemoryService` with `add/get/search_memory`; Memory Bank stores conversation history and extracted facts; Zep Cloud available as a provider.
- Self-host / K8s: mixed — ADK self-hostable, Memory Bank GCP-only.
- Relevance: the `MemoryService` interface is a useful API reference; the managed backend is not self-hostable.
- Source: `https://github.com/google/adk-python`.

## Category 3 — Vector store substrates

Not memory layers themselves, but the persistence/retrieval substrate a memory layer (custom or adopted) sits on. Listed briefly because the substrate choice is part of any KAOS design.

- pgvector (`pgvector/pgvector`): Postgres extension; HNSW/IVFFlat; permissive license; excellent K8s fit via standard Postgres; used by Mem0 server, Cognee, LangGraph. `https://github.com/pgvector/pgvector`.
- Qdrant (`qdrant/qdrant`): Apache-2.0 Rust engine; quantization, payload filtering, multi-tenancy; official Helm chart; default for Mem0 OSS. `https://github.com/qdrant/qdrant`.
- Weaviate (`weaviate/weaviate`): BSD-3; hybrid search, built-in vectorizers, multi-tenancy, RBAC; K8s-native Helm chart. `https://github.com/weaviate/weaviate`.
- Milvus (`milvus-io/milvus`): Apache-2.0; distributed, billion-scale, Milvus Operator — the most K8s-native vector DB here. `https://github.com/milvus-io/milvus`.
- Chroma (`chroma-core/chroma`): Apache-2.0; embeddable SQLite-backed, simple server mode; CrewAI default. `https://github.com/chroma-core/chroma`.
- LanceDB (`lancedb/lancedb`): Apache-2.0; embedded columnar (Lance) with vector + FTS + SQL; default substrate for Cognee. `https://github.com/lancedb/lancedb`.
- Pinecone: proprietary SaaS only; no self-host — excluded for KAOS's self-host requirement. `https://www.pinecone.io`.
- Redis (RedisVL / vector search): MIT client over Redis; vector + hybrid search, semantic caching; KAOS already runs Redis. `https://github.com/redis/redis-vl-python`.

## Category 4 — Knowledge-graph substrates

- Neo4j (`neo4j/neo4j`): Community Edition GPL-3.0 / Enterprise commercial / Aura managed; property graph + Cypher + vector index; official Helm chart and Kubernetes operator; substrate for Graphiti, Cognee, Memary. `https://github.com/neo4j/neo4j`.
- FalkorDB (`FalkorDB/FalkorDB`): SSPLv1; Redis-module property graph with sparse-matrix engine, very low latency for LLM query patterns; Redis-compatible deployment. `https://github.com/FalkorDB/FalkorDB`.
- Microsoft GraphRAG (`microsoft/graphrag`): MIT; an LLM-driven batch KG-construction and global-summarization pipeline, not a real-time memory layer; high LLM cost. `https://github.com/microsoft/graphrag`.

## Category 5 — Managed / commercial memory services

These are SaaS and therefore weighted against KAOS's self-host requirement, but matter as managed counterparts and integration targets.

- Mem0 Platform (`app.mem0.ai`): managed Mem0; zero-ops, hosted vectors, org management. SaaS only.
- Zep Cloud (`getzep`): managed Graphiti; per-entity context graphs at scale, sub-200ms retrieval claim, broad framework integrations including Pydantic AI. SaaS only (the OSS Community Edition is deprecated; Graphiti is the self-host path).
- Letta Cloud (`app.letta.com`): managed Letta. SaaS (OSS for self-host).
- Honcho managed (`api.honcho.dev`): managed Honcho. SaaS (OSS for self-host).
- OpenAI memory (Responses API / ChatGPT memory): managed conversation-fact retention; `store=True` / `previous_response_id` continuity. SaaS only; no developer API for the user-memory layer.
- Pinecone Assistant: managed RAG over Pinecone vectors. SaaS only.
- Google Vertex AI Agent Engine Memory Bank: managed fact + conversation storage integrated with ADK. GCP only.

## The KAOS custom implementation (baseline option)

Carried as a first-class option per the investigation's scope. KAOS today implements a custom per-session conversation log behind a clean `Memory` ABC, with `LocalMemory` (in-process, deque-bounded), `RedisMemory` (distributed, hash + list + sorted-set index, TTL), and `NullMemory`, wired through an Agent CRD `MemoryConfig` block and `MEMORY_*` env vars and bridged to Pydantic AI message history. Its strengths are simplicity, a clean pluggable interface, native Kubernetes/CRD configuration, and an existing distributed backend; its gaps are the absence of every long-term capability (semantic retrieval, summarization, consolidation, cross-session/user memory, knowledge structuring, principled forgetting). The full account is in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md). The build-versus-adopt question this catalogue informs is whether to extend this baseline to production grade or to adopt one of the dedicated layers above behind the same interface.

## Self-host / Kubernetes viability matrix

A condensed view of the axis that matters most for KAOS. "Server" means it ships a deployable service (image/REST); "library" means embeddable only; "SaaS" means managed-only.

| Tool | Type | K8s self-host | Notes |
|------|------|---------------|-------|
| Mem0 | server + library | strong | Compose stack, published image |
| Graphiti | library | good | needs Neo4j; MCP server bundled |
| Letta | server + library | good | REST API + Docker; opinionated agent runtime |
| Cognee | server + library | strong | Docker images, multi-tenant, OTel |
| Memobase | server | good | Dockerized FastAPI + Postgres + Redis |
| ReMe | library/service | good | file-on-PVC; concurrency caveat |
| Memary | library | weak | needs Neo4j; possibly unmaintained |
| Honcho | server | good | FastAPI + Docker; AGPL-3.0 |
| Redis Agent Memory Server | server | strong | Redis-native; KAOS already runs Redis |
| txtai | server + library | strong | substrate + pipelines, not an opinionated memory model |
| LangGraph + LangMem | library | good | Postgres backend; pulls in LangGraph model |
| LlamaIndex memory | library | embeddable | any vector store |
| CrewAI memory | library | embeddable | in-process; reference model |
| MS Agent Framework | library + server | good | .NET/Azure-leaning |
| Semantic Kernel | library | embeddable | widest connectors; being superseded |
| Haystack | library + API | good | Hayhooks REST/MCP |
| Pydantic AI | library | embeddable | message history only (KAOS data plane) |
| Google ADK | library | mixed | Memory Bank is GCP-only |
| pgvector / Qdrant / Weaviate / Milvus | server | strong | substrates; Helm charts / operators |
| Chroma / LanceDB | library/server | good | embeddable substrates |
| Pinecone | SaaS | none | no self-host |
| Neo4j / FalkorDB | server | strong | graph substrates |
| GraphRAG | library | library | batch pipeline; costly |
| Zep Cloud / Mem0 Platform / Letta Cloud / Honcho managed / OpenAI / Pinecone Assistant / Vertex Memory Bank | SaaS | none | managed only |

## Observations toward the shortlist

- The most KAOS-relevant field is **Category 1 dedicated, self-hostable layers**: Mem0, Graphiti (with Zep Cloud as its managed twin), Cognee, Memobase, Honcho, Redis Agent Memory Server, and Letta — each ships a deployable server or embeddable library and runs in a customer cluster.
- Two architectural families recur, matching [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md): **vector-first** (Mem0, Memobase, Redis Agent Memory Server, txtai) and **graph-first / temporal** (Graphiti, Cognee, Memary). Several are hybrids.
- **Infrastructure delta** is a real differentiator for KAOS: Redis-native options (Redis Agent Memory Server) reuse infrastructure KAOS already supports, whereas graph-first options add a Neo4j (or FalkorDB) dependency.
- **Licensing** needs weighting at selection: Apache/MIT (Mem0, Graphiti, Cognee, Memobase, Redis Agent Memory Server, txtai, Letta) versus AGPL-3.0 (Honcho) versus SSPL (FalkorDB) and GPL (Neo4j Community).
- **Framework-native** options are mostly references, not drop-ins, because KAOS already owns the runtime; their value is design vocabulary (scope trees, profiles vs collections, hot-path vs background) for the target picture.

These observations seed the shortlist in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md), which narrows the field to a small set for deep evaluation alongside the KAOS-custom baseline.

## Gaps and uncertainties

- Maturity figures and vendor benchmark claims (e.g. Mem0/Memobase/Honcho/Zep accuracy and latency numbers) are vendor-reported and were not independently reproduced; treat them as directional and re-verify at selection.
- Memary's GitHub repository was unreachable during research and the package appears minimally maintained — classified as research-grade / possibly unmaintained.
- Several newer entrants (e.g. names like MemDB/Membank/MemU, and the Memobase team's "Acontext") could not be verified as actively maintained and were deliberately excluded rather than described speculatively.
- Zep's open-source Community Edition is deprecated; only Graphiti (OSS) and Zep Cloud (SaaS) are forward paths.
- A standalone "LangCache" OSS product was not found; the semantic-cache capability lives within RedisVL.
- AutoGen is in maintenance mode; new Microsoft work consolidates on the Agent Framework.

## Context manifest

In scope: project repositories and documentation for the tools catalogued above (GitHub repos and official docs as cited inline), the KAOS baseline from [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md), and the patterns/benchmarks framing from [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). The self-host / Kubernetes viability axis was treated as primary given KAOS's deployment model.

Out of scope (deferred): the narrowed shortlist and comparison matrix ([KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md)), the per-tool deep dives whose set is fixed by that shortlist, the final selection, and the target design. Independent benchmark reproduction is out of scope here and flagged for selection-time verification.
