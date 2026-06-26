# KAOS-R5-2 — Zep / Graphiti deep dive

This is a per-tool deep evaluation of Graphiti (and its managed twin Zep), the temporal-knowledge-graph candidate shortlisted in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md). It assesses the approach against the requirements baseline in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and the ecosystem patterns in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). Scope and sources are in the [Context manifest](#context-manifest). Vendor and paper figures are flagged where KAOS cannot independently confirm them.

## At a glance

- **What it is:** Graphiti is an open-source engine that builds and queries a **bi-temporal knowledge graph** from agent interactions — entities and facts (edges) with explicit validity intervals, hybrid (semantic + keyword + graph) retrieval, and incremental updates. Zep is the managed SaaS built on Graphiti.
- **License:** Graphiti `graphiti-core` is Apache-2.0 (library, FastAPI server, MCP server). Zep Cloud is a proprietary SaaS (its SDK is open but the backend is paid). The older self-hostable "Zep Community Edition" is **deprecated** — for OSS self-hosting the path is Graphiti + a graph database.
- **Backing/maturity:** built and maintained by the Zep team; an arXiv paper (2501.13956) reports strong memory benchmarks; active releases (graphiti-core ~0.29.x at time of research).

## Architecture

Graphiti turns each interaction into an **episode** and runs a multi-step LLM pipeline on ingestion (`add_episode`): retrieve recent episodic context, extract entity nodes (NER) with type classification, resolve/deduplicate entities against the existing graph (cosine + LLM), extract relationship edges (RE), resolve and **invalidate** superseded edges, extract/refresh entity summaries, and bulk-save nodes and edges; optionally update communities via Leiden clustering. Source: `graphiti_core/graphiti.py`.

The defining property is the **bi-temporal model**: every fact tracks both *event time* (`valid_at`/`invalid_at` — when the fact was true in the world) and *ingestion/transaction time* (`created_at`/`expired_at` — when the system learned and later superseded it). Source: `graphiti_core/edges.py`. This lets an agent ask "what was true at time T" independently from "what did we know at time T," and — crucially — old facts are **invalidated, not deleted**, preserving provenance and history. This is the structured, time-aware, contradiction-tracking end of the design space and the sharpest contrast to Mem0's vector-first store ([KAOS-R5-1](./KAOS-R5-1-mem0.md)).

## Memory model

Nodes are `EpisodicNode` (raw interaction content with event-time `valid_at`), `EntityNode` (an entity with an evolving LLM `summary`, embedding, and typed `attributes`), and `CommunityNode` (a cluster summary). Edges are `EntityEdge` (a natural-language `fact` with `fact_embedding`, source `episodes` for provenance, and `valid_at`/`invalid_at`/`expired_at`), plus episodic/community/ordering edges. Custom ontologies are expressed as **Pydantic models** passed as `entity_types`/`edge_types` to `add_episode`. Source: `graphiti_core/nodes.py`, `graphiti_core/edges.py`.

This covers, in one model, the long-term semantic memory, knowledge/entity extraction, cross-session synthesis, and principled (invalidation-based, non-destructive) forgetting that [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) lists as entirely absent today.

## APIs and SDK

The Python `Graphiti` class exposes `add_episode` / `add_episode_bulk` (ingestion), `search` (basic hybrid → list of edges) and `search_` (full `SearchConfig`), `retrieve_episodes`, `add_triplet` (direct KG triples), `remove_episode`, `build_communities`, and `build_indices_and_constraints`. Source: `graphiti_core/graphiti.py`. Search recipes (`search_config_recipes.py`) bundle ready configurations (combined/edge/node/community variants with RRF, MMR, node-distance, episode-mentions, or cross-encoder reranking).

Zep Cloud's SDK works at a higher level — `user`, `thread`, and `graph` namespaces, where `thread.get_user_context(thread_id)` returns the most relevant context from the user's whole cross-thread graph (the primary prompt-time memory call).

## Storage backends

Graphiti requires a graph database: **Neo4j ≥5.26** (primary; native full-text for BM25), **FalkorDB** (Redis-based, the MCP bundle default, plus an embedded "Lite" variant), and **Amazon Neptune** (needs OpenSearch Serverless for full-text). **Kuzu is deprecated** (upstream unmaintained). LLM providers must support **structured (JSON-schema) output** (OpenAI, Anthropic, Gemini, Azure, and OpenAI-compatible endpoints like Ollama/vLLM, though smaller models often fail); embedders include OpenAI, Voyage, Gemini, and Sentence Transformers; the default reranker is a cross-encoder. Source: `graphiti_core/pyproject.toml`, README.

For KAOS, the FalkorDB option is notable: it is Redis-protocol-based, partially overlapping the Redis operational surface KAOS already supports, though it is a distinct graph engine, not the same Redis KAOS runs today.

## Retrieval

Retrieval fuses **BM25 keyword**, **cosine semantic**, and **graph BFS** (from a center node), then reranks with RRF, MMR, node-distance, episode-mentions, or a cross-encoder. Read latency is typically sub-second (Zep Cloud advertises sub-200ms at scale — vendor-stated). This is the richest retrieval model of the shortlist and directly addresses the relevance- and relationship-aware recall [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) identifies as best practice.

## Deployment and Kubernetes fit

Three forms: the **Python library** (bring your own Neo4j/FalkorDB), a **FastAPI REST server** (`zepai/graphiti` image; needs Neo4j; a thin wrapper that does not expose every `search_` option), and an **experimental MCP server** (bundles FalkorDB). Neo4j on Kubernetes is well-supported (Neo4j Helm chart and Kubernetes operator), but there is **no Graphiti-native operator, CRD, or Helm chart** — KAOS would orchestrate the graph DB plus the application containers itself. Source: `server/README.md`, `mcp_server/`.

The operational weight here is real: running Neo4j (or FalkorDB) at multi-tenant scale, plus the LLM-heavy ingestion path, is a materially larger delta than KAOS's current Redis-only footprint.

## Pydantic AI integration path

There is **no official Pydantic AI adapter** in the Graphiti or Zep SDKs (the prior assumption in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md) that Zep "ships an official Pydantic AI integration" could **not be verified** and is corrected here). Graphiti's data models are Pydantic v2, and Zep's ontology API accepts Pydantic `BaseModel` subclasses, but that is ontology definition, not a framework plugin. A KAOS integration would be a hand-written `GraphitiMemory(Memory)` backend that calls `add_episode` on write and `search`/`get_user_context` on read, mapping `user_id`/`session_id` onto `group_id`/user graphs. The lossy/blocking nature of ingestion (multiple serial LLM calls) means writes would likely be queued asynchronously rather than run inline on the agent hot path.

## Multi-tenancy and isolation

Graphiti partitions by `group_id` on every node and edge. With Neo4j, a `group_id` routes to a **separate Neo4j database**, giving hard isolation — but multiple databases require **Neo4j Enterprise** (Community supports one), so large per-tenant graphs imply an Enterprise license or a shared-database/field-filter compromise (FalkorDB stores `group_id` as a field). Zep Cloud gives each user an isolated graph. This is stronger isolation than Mem0's application-level filtering, at a higher infrastructure/licensing cost.

## Scaling and performance

Updates are **incremental** — no batch recompute; new facts invalidate old ones in place. The arXiv abstract reports Zep at **94.8% on DMR** (vs MemGPT 93.4%), **up to 18.5%** improvement on LongMemEval, and a **~90% latency reduction** versus unspecified baselines — verified against the abstract but with the baseline undefined, so treat as **approximate/vendor-framed**. The binding constraint is **ingestion**: each episode triggers several serial LLM calls (NER, RE, dedup, attributes), so write throughput is low and costly, gated by a deliberately low concurrency default to avoid rate limits. Community rebuilds are also LLM-expensive.

## Observability

Graphiti has **first-class OpenTelemetry support** — pass an OTel `Tracer` and it emits spans for `add_episode`/bulk and LLM calls with rich attributes (node/edge counts, invalidation counts, duration), plus a token-usage tracker for LLM cost accounting (anonymous PostHog telemetry is also present). Source: `OTEL_TRACING.md`, `graphiti_core/tracer.py`. This aligns well with KAOS's OTel-centric observability — the best fit of the shortlist on this axis.

## Licensing and open-core split

`graphiti-core` (and its FastAPI/MCP servers) is Apache-2.0 — safe to self-host and embed; a contributor CLA applies to the Zep-owned repos. Zep Cloud is proprietary SaaS. The deprecation of Zep Community Edition means the only OSS self-hosting story is Graphiti + a graph DB — there is no self-hostable equivalent of Zep Cloud's dashboard, governance, and SLAs.

## Maturity and ecosystem

Strong: an academic paper, professional SDK tooling (Fern-generated), multi-platform Docker builds, and production validation via Zep Cloud's customers. The library API is active (~0.29.x) and still moving; the MCP server is explicitly experimental; Kuzu support is being removed. The ecosystem leans toward LangGraph examples rather than Pydantic AI.

## Gaps versus KAOS needs

Mapping to [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md):

- **Closes (most completely of the shortlist):** semantic/long-term memory, knowledge/entity extraction with an explicit graph, cross-session synthesis, time-aware reasoning, provenance, principled non-destructive forgetting via edge invalidation, rich hybrid retrieval, and OTel observability that matches KAOS conventions.
- **Leaves open or adds cost:** the heaviest operational footprint of the shortlist (Neo4j/FalkorDB to run, Enterprise for hard multi-tenant isolation at scale); high LLM cost and low throughput on ingestion (writes must be queued off the hot path); no Graphiti-native Helm/operator; no official Pydantic AI integration (must be hand-written); an experimental REST/MCP surface; structured-output LLM requirement that constrains model choice.
- **Architectural note:** like Mem0, Graphiti is a long-term layer that would run alongside KAOS's existing working-memory conversation log, not replace it — but it imports a graph datastore and an LLM-heavy write pipeline as the price of its capabilities.

## Context manifest

In scope (read for this document): the Graphiti/Zep deep-research findings (`getzep/graphiti` and `getzep/zep-python` source paths cited inline, the FastAPI/MCP server READMEs, OTel docs, and the arXiv 2501.13956 abstract); the KAOS requirements baseline [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md); the ecosystem patterns [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md); the shortlist rationale [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md); and the Mem0 deep dive [KAOS-R5-1](./KAOS-R5-1-mem0.md) for cross-comparison.

Out of scope (intentionally excluded): the remaining shortlisted tools (their own R5 documents), the final selection ([KAOS-R6](./KAOS-R6-tool-selection.md)), and the target design ([KAOS-R7](./KAOS-R7-target-picture.md)). Benchmark and latency figures from the paper and vendor pages are reported as approximate or vendor-framed; the previously assumed official Pydantic AI integration is corrected to unverified/absent.
