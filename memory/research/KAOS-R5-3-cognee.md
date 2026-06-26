# KAOS-R5-3 — Cognee deep dive

This is a per-tool deep evaluation of Cognee, the hybrid graph-plus-vector candidate shortlisted in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md). It assesses Cognee against the requirements baseline in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and the ecosystem patterns in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). Scope and sources are in the [Context manifest](#context-manifest). Vendor and paper figures are flagged where KAOS cannot independently confirm them.

## At a glance

- **What it is:** an Apache-2.0 "memory engine" that runs an Extract–Cognify–Load (ECL) pipeline turning raw data and interactions into a **tri-store** memory — a knowledge graph, a vector index, and a relational metadata store kept in sync by shared UUIDs — queried through many retrieval modes.
- **License:** Apache-2.0 (Topoteretes UG); a managed Cognee Cloud exists but the research found no proprietary features withheld from the OSS core.
- **Form factors:** primarily an embeddable async **Python library** (`pip install cognee`), plus a FastAPI REST server, an MCP server, and Docker images with Compose profiles and a (minimal, unpublished) Helm chart.
- **Backing/maturity:** Topoteretes UG; version ~1.2.x with a **Beta** development classifier; an arXiv paper (2505.24478) on KG–LLM retrieval tuning; active releases but a history of API churn.

## Architecture

Cognee's core is the **ECL pipeline** run by `cognify()`: **Extract** (classify documents, chunk them), **Cognify** (an LLM extracts entities, relationships, and summaries into a `KnowledgeGraph` Pydantic schema, optionally validated against an RDF/OWL ontology), and **Load** (persist nodes/edges to the graph store, embed indexed fields into the vector store, and record provenance in the relational store). A temporal variant extracts events and timestamps for timeline-oriented graphs. Pipelines are ordered lists of `Task`s (any Python callable) with batching, background execution, incremental loading, and rollback. Source: `cognee/api/v1/cognify/cognify.py`.

The unit of knowledge is a `DataPoint` — a Pydantic model with a shared `id` persisted across all three stores, where `metadata.index_fields` controls what gets embedded and nested DataPoint fields automatically become graph edges. This **hybrid graph+vector** design sits deliberately between Mem0's vector-first store ([KAOS-R5-1](./KAOS-R5-1-mem0.md)) and Graphiti's graph-first engine ([KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md)): vector search finds seed nodes, then graph traversal expands relational context.

## Memory model

The tri-store comprises a relational store (SQLite/Postgres — document/chunk provenance, datasets, users, pipeline runs), a vector store (embeddings of indexed fields, one named collection per class/field), and a graph store (DataPoint nodes and typed edges, Cypher-traversable). **Ontologies** (RDF/OWL) enrich and validate extracted entities. **Node Sets** are first-class tag nodes that group documents/chunks/entities for scoped retrieval — a lightweight intra-dataset organization layer. A separate fast **session memory** (Redis or filesystem) holds ephemeral in-session entries that sync to the permanent graph via `improve()`.

This covers, in one system, the long-term semantic memory, knowledge/entity structuring, summarization, and cross-session recall that [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) lacks — and uniquely among the shortlist it pairs a graph with a vector index natively rather than treating one as primary.

## APIs and SDK

The current memory-oriented V2 API is `remember()`, `recall()`, `improve()`, and `forget()`; the lower-level V1 building blocks (`add`, `cognify`, `search`, `memify`, `run_custom_pipeline`, `prune`) remain. `search()` takes a `query_type` from a large `SearchType` enum (GRAPH_COMPLETION default, plus RAG_COMPLETION, HYBRID_COMPLETION, CHUNKS/CHUNKS_LEXICAL, SUMMARIES, CYPHER, NATURAL_LANGUAGE, TEMPORAL, AGENTIC_COMPLETION, FEELING_LUCKY auto-routing, and several graph-completion variants). The same surface is exposed over REST (`/api/v1/...`, optional JWT auth) and via an MCP server (stdio/SSE/HTTP). Source: `cognee/__init__.py`, `cognee/api/v1/search/search.py`, `cognee/modules/search/types/SearchType.py`.

## Storage backends

Graph: **Kuzu** (default, file-based, single-process), Neo4j, Neptune, Memgraph, FalkorDB. Vector: **LanceDB** (default, file-based), pgvector, Chroma, and community adapters (Qdrant, Redis, FalkorDB, Turbopuffer, Pinecone). Relational: SQLite (dev) → Postgres (prod). Embedders: OpenAI, Azure, Gemini, Mistral, Ollama, Fastembed (local ONNX). LLM access is via LiteLLM, aligning with KAOS's ModelAPI/LiteLLM story. Source: Cognee docs (graph-stores, vector-stores).

The defaults (Kuzu + LanceDB) are zero-setup but file-based and **single-process** — fine for a single embedded agent, but for KAOS's multi-replica, multi-tenant runtime a production deployment must move to Postgres + a server-based graph/vector store, which raises the infrastructure delta toward Graphiti's level.

## Retrieval

`GRAPH_COMPLETION` (default) does vector seed-finding → neighborhood graph expansion → grounded LLM answer, with tunable `top_k`, neighborhood depth, and a triplet-distance penalty. Other modes cover pure RAG, lexical BM25-style chunk search, summaries, chain-of-thought and context-extension graph variants, raw/NL→Cypher, and an agentic tool-calling retriever; `FEELING_LUCKY` routes automatically. Node-set filters scope graph-completion retrieval. This is the broadest *menu* of retrieval strategies in the shortlist, directly serving the relevance- and relationship-aware recall [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) recommends — at the cost of more knobs to tune.

## Deployment and Kubernetes fit

Cognee publishes `cognee/cognee` and `cognee/cognee-mcp` Docker images and a Docker Compose with profiles (UI, MCP, Postgres, Neo4j). A **Helm chart exists** under `deployment/helm/` but is minimal and not published to a registry — usable as a starting point, not turnkey. The cleanest KAOS path may be **library mode**: embed Cognee in the Pydantic AI runtime pointed at external Postgres + a server-based vector/graph store. The base library is heavy (~50 direct dependencies), which enlarges the agent image and the dependency-audit surface. Source: README, `deployment/helm/`, `pyproject.toml`.

## Pydantic AI integration path

Cognee is a pure Python library whose outputs are Pydantic models, so a `CogneeMemory(Memory)` KAOS backend would call `remember()`/`improve()` on write and `recall()` on read, surfacing results as context or as a tool. An `@agent_memory` decorator exists for attaching retrieval to async agent functions. There is **no official Pydantic AI adapter**, but the integration is straightforward; as with the graph systems, the LLM-heavy `cognify` step argues for background/queued ingestion rather than inline hot-path writes. Source: `cognee/__init__.py`, agent-memory-decorator docs.

## Multi-tenancy and isolation

User accounts are JWT-authenticated (`fastapi-users`), and with `ENABLE_BACKEND_ACCESS_CONTROL=true` each user/dataset gets isolated graph and vector files plus dataset-level read/write/admin ACLs enforced in search. This is **richer first-class multi-tenancy than Mem0's application-level filtering**. The caveats are backend-specific: native multi-user mode is supported on Kuzu and FalkorDB, while **self-hosted Neo4j is not supported in multi-user mode** (only auto-provisioned Aura is), and Kuzu's file-locking caps a dataset to one process at a time — a real constraint for concurrent multi-agent access. Source: Cognee permissions docs.

## Scaling and performance

Updates support incremental loading (already-indexed data is skipped). The cost center is `cognify`: every chunk triggers at least one structured LLM call, so large ingestions are expensive and latency-bound, mitigated by background execution and configurable LLM rate limits. Horizontal scale requires abandoning the file-based defaults (Kuzu/LanceDB) for server backends. The only published benchmarks (arXiv 2505.24478, on HotPotQA/2WikiMultiHop/MuSiQue) study hyperparameter sensitivity rather than head-to-head memory comparisons and report no extracted head-line numbers — treat as **preliminary/unverified**.

## Observability

Cognee is **OpenTelemetry-native**: `setup_tracing()` provisions a tracer, **attaches to an existing external OTel provider if one is present** (rather than replacing it), supports OTLP export via `OTEL_EXPORTER_OTLP_ENDPOINT`, and emits spans across pipeline tasks, LLM calls, vector queries, and search with rich semantic attributes and built-in secret redaction; Sentry and Langfuse are optional. Source: `cognee/modules/observability/tracing.py`. This is an excellent fit for KAOS's OTel conventions — comparable to Graphiti and ahead of Mem0 on this axis.

## Licensing and open-core split

Apache-2.0 across the core and adapters, with no proprietary features found withheld from OSS — the most fully-open of the dedicated layers in the shortlist. Cognee Cloud is an optional managed target reached via `cognee.serve(...)`. Community backend adapters live in a separate org and vary in maintenance quality.

## Maturity and ecosystem

Active but **Beta**: frequent Docker publishes, an arXiv paper, JWT auth, OTel, and Alembic migrations signal seriousness, but the **Development Status :: Beta** classifier, the recent V1→V2 API rename, and ongoing reorganization signal a still-moving API and real upgrade risk. Star count is mid-thousands (vendor/badge ~8k, unverified). Some key vector backends (Weaviate/Milvus) are community-only or absent — verify before relying.

## Gaps versus KAOS needs

Mapping to [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md):

- **Closes:** semantic/long-term memory, hybrid graph+vector knowledge structuring, summarization, cross-session recall, a very broad retrieval menu, first-class dataset/user multi-tenancy with ACLs, OTel-native observability matching KAOS conventions, and LiteLLM-based model access aligned with KAOS's ModelAPI.
- **Leaves open or adds cost:** heavy dependency footprint embedded in the agent runtime; LLM-intensive `cognify` (queue off the hot path); file-based defaults that don't scale (production needs Postgres + server graph/vector store); self-hosted Neo4j unsupported in multi-user mode and Kuzu single-process concurrency limits; a minimal unpublished Helm chart; and a Beta, churn-prone API.
- **Architectural note:** Cognee can act as both a long-term layer and, via its session memory, a working-memory cache — but for KAOS it would still complement rather than wholesale replace the existing conversation log, and its breadth comes with more configuration surface than the other candidates.

## Context manifest

In scope (read for this document): the Cognee deep-research findings (`topoteretes/cognee` source paths and `docs.cognee.ai` pages cited inline, plus arXiv 2505.24478); the KAOS requirements baseline [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md); the ecosystem patterns [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md); the shortlist rationale [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md); and the Mem0 and Zep/Graphiti deep dives ([KAOS-R5-1](./KAOS-R5-1-mem0.md), [KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md)) for cross-comparison.

Out of scope (intentionally excluded): the remaining shortlisted tools (their own R5 documents), the final selection ([KAOS-R6](./KAOS-R6-tool-selection.md)), and the target design ([KAOS-R7](./KAOS-R7-target-picture.md)). Star counts and paper results are reported as approximate or preliminary.
