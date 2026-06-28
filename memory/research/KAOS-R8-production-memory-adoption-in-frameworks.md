# KAOS-R8 — Production memory adoption across agent frameworks

This document surveys how widely-used agent frameworks support memory tiers and, more importantly, which tiers are *demonstrably used in production* rather than merely present in an API. It is follow-on research that feeds the architecture-decision phase — specifically the memory-model tiers ([adr_high_level_components](../adrs/adr_high_level_components.md) component 1) and the build-versus-adopt and engine-selection decision (component 2). It complements the earlier ecosystem and tooling research ([KAOS-R2](./KAOS-R2-memory-ecosystem-research.md), [KAOS-R3](./KAOS-R3-memory-tooling.md)) by focusing on real adoption signal as of mid-2026.

## Scope and method

The survey covers LangChain/LangGraph/LangMem, CrewAI, Microsoft AutoGen and Semantic Kernel (now consolidating into the Microsoft Agent Framework), LlamaIndex, Letta (formerly MemGPT), Google Agent Development Kit (ADK), Agno (formerly Phidata), Haystack, the OpenAI Agents SDK, and AutoGPT. For each, the survey records which memory types are natively supported, the implementation mechanism, the production-adoption signal, and the framework's own terminology. Claims are drawn from official documentation, repositories, and primary blog posts. GitHub star counts are approximate (read from page signals, not the API) and should be treated as ±20% as of June 2026; where a number mattered it was sanity-checked (for reference, an API check during this research returned ~140k stars for `langchain-ai/langchain`). Vendor case studies are flagged as strong-but-not-independently-verified.

## Memory-tier support matrix

| Framework | Working / short-term | Long-term semantic | Long-term episodic | Procedural | Temporal | Explicit taxonomy | Native long-term |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LangGraph + LangMem | Checkpointer / thread-scoped buffer | `BaseStore` collections + vector search | LangMem extraction / few-shot store | System-prompt store + reflection | Composite recency decay | Yes — names semantic/episodic/procedural | Yes |
| CrewAI | Task-injected recall | Unified `Memory` vector index | Collapsed into unified memory | No | Recency weight in score | No — collapses into one system | Yes |
| AutoGen (AgentChat) | `model_context` | `ChromaDBVectorMemory` / `RedisMemory` | Not distinct | No | No | No | Via extensions |
| Semantic Kernel / MAF | `ChatHistoryAgentThread` | Vector Store connectors (RC/Preview) | Not distinct | System prompt only | No | No | Preview |
| LlamaIndex | `Memory` / `ChatMemoryBuffer` | `FactExtractionMemoryBlock` | `VectorMemoryBlock` (message batches) | `StaticMemoryBlock` (closest) | No | No (implicit) | Yes |
| Letta (MemGPT) | Memory blocks in context | Archival memory (vector) | Full message DB + archival | Persona block / self-edit | No | Partial (own terms) | Yes |
| Google ADK | Session state + auto-summary | Mentioned; docs unverifiable | Unclear | Unclear | No | No | Unverified |
| Agno | Chat history (DB-backed) | User memory (facts, DB) | Not distinct | Not distinct | No | No | Yes |
| Haystack | Agent state / message list | Document stores + retrievers | Not distinct | Not distinct | No | No | Via components |
| OpenAI Agents SDK | `SQLiteSession` / `RedisSession` | None natively | None natively | None natively | No | No | No |
| AutoGPT | Workflow state buffer | Vector DB (classic) / blocks (new, unverified) | Same store as semantic | No | No | No | Limited |

## Production-adoption signal

| Framework | Stars (approx.) | Memory feature status | Named production users / notes |
| --- | --- | --- | --- |
| LangGraph | ~15k+ | Stable | Klarna, Replit, AppFolio, Elastic (orchestration; specific memory-feature usage not broken out publicly) |
| LangMem | ~2k | Functional but `0.0.x`, evolving | LangGraph Platform users; no named case studies |
| CrewAI | ~30k+ | Stable API, but native memory has production gaps | 100k+ certified devs; native store breaks on redeploy and lacks user isolation (documented community fix via Mem0) |
| AutoGen (AgentChat) | ~46k+ | Maintenance mode | Migrating to Microsoft Agent Framework |
| Semantic Kernel / MAF | ~24k (SK) | SK stable; vector stores RC/Preview | Microsoft enterprise customers; no agent-memory case studies |
| LlamaIndex | ~40k+ | `Memory` + blocks stable; old API deprecated | Stable API; no named memory case studies |
| Letta | ~15k+ | Production API | Most architecturally complete memory; smaller footprint; no named enterprise metrics |
| Google ADK | ~10k+ | Native long-term memory unverifiable / not production-grade default | Google Cloud; `InMemoryMemoryService` explicitly unsuitable for production |
| Agno | ~10k+ | Memory + history stable | AgentOS platform; no external case studies |
| Haystack | ~20k+ | Strong RAG; weak cross-session agent memory | deepset enterprise; cross-session agent memory not in native scope |
| OpenAI Agents SDK | ~10k+ | Sessions stable; no native long-term memory | Long-term memory delegated to external engines by design |
| AutoGPT | ~173k ⚠️ | Classic legacy; new platform pre-GA | Star count reflects 2023 hype, not production adoption |

## The central structural finding: production memory is an external engine

The single most important result of this survey is that, for most frameworks, the production memory layer is an external service rather than the framework itself. This has hardened into an architectural consensus, not a temporary workaround.

- Framework-native memory is designed for development and testing. `InMemoryDocumentStore` (Haystack), `InMemoryMemoryService` (ADK), `ListMemory` (AutoGen), and `SimpleChatStore` (LlamaIndex) are explicitly or effectively unsuitable for multi-tenant, multi-deployment production use.
- External engines solve what frameworks structurally cannot: user/tenant isolation (`user_id` scoping), cross-deployment persistence, multi-signal retrieval, temporal reasoning, and compliance (SOC 2, HIPAA). These are infrastructure concerns that do not belong in an orchestration framework.
- The dominant production pattern is therefore `framework + engine`: LangGraph + Mem0, CrewAI + Mem0, or any framework + Zep. The framework owns agent execution; the engine owns what the agent knows and remembers.
- This directly validates the KAOS direction of owning a clean interface and control plane while plugging in a best-of-breed engine behind it ([KAOS-R6](./KAOS-R6-tool-selection.md), [KAOS-R7](./KAOS-R7-target-picture.md)).

### External memory engine integration map

Mem0 is the most widely integrated external engine (documented integrations across LangGraph, CrewAI, AutoGen, LlamaIndex, Google ADK, Agno, and the OpenAI Agents SDK; 21 framework integrations claimed; named — vendor-authored — case studies with quantitative cost-reduction figures; AWS Strands partnership; a YC S24 commercial cloud). Zep positions as the enterprise, graph-based engine ("works with any framework", named enterprise logos, SOC 2 / HIPAA, sub-200ms retrieval SLA, a third-party S&P Global mention). Cognee released v1 around June 2026 with no named production users yet. Redis is widely used as a session/backing store across frameworks; the Redis Agent Memory Server is covered separately in [KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md).

## Which tiers are supported versus actually used

Most commonly *supported*: short-term session buffers (universal); vector-store long-term with semantic and episodic collapsed (most frameworks natively, all via external engines); conversation summarization (about a third of frameworks); fact extraction / structured user memory (a handful); explicit episodic few-shot retrieval (rare); procedural / system-prompt updating (one or two); temporal / recency-weighted retrieval (one or two natively, plus the external engines).

Most commonly *used in production* (evidence-ranked): short-term session buffers first (universal); then external long-term memory via Mem0 (strongest production evidence of any single memory system in the survey) and Zep (strongest enterprise evidence, graph-based, temporal); then LangGraph's first-party `AsyncPostgresStore`; then Letta's server-side memory and Agno's DB-backed user memory. Episodic-as-a-distinct-tier, procedural memory, and true temporal memory are rarely deployed as separate production tiers.

## Semantic, episodic, and temporal in framework practice

The cognitive-science taxonomy is not universally adopted: only LangGraph/LangMem names semantic, episodic, and procedural explicitly. In practice frameworks collapse the distinctions, and the collapse is a pragmatic production decision rather than a defect — distinguishing a "user fact" (semantic) from a "past interaction" (episodic) in a production vector store adds complexity most teams do not need.

Canonical collapse examples: CrewAI's unified `Memory` stores a user's preference (semantic) and a past project decision (episodic) in one vector store with no way to query by type; AutoGen's `ChromaDBVectorMemory` retrieves preferences and past actions identically by cosine similarity; LlamaIndex's `VectorMemoryBlock` holds episodic message batches but retrieves them by semantic similarity (the content is episodic, the retrieval is semantic — the canonical collapse case); the OpenAI Agents SDK `SQLiteSession` is purely episodic with no extraction. Zep/Graphiti is the exception that separates Episodes from Facts at the graph level. The sharper conceptual treatment of episodic versus semantic versus temporal — and where true temporal memory exists — is developed in [KAOS-R9](./KAOS-R9-procedural-temporal-memory-in-agent-systems.md).

## Caveats and gaps

- Mem0 and Zep case studies are vendor-authored; they contain specific names and metrics but were not independently cross-referenced. Treat as strong primary signal, unverified independently.
- Named LangGraph users (Klarna, Replit, AppFolio) are confirmed framework users, but their specific memory-feature usage (checkpointer versus `BaseStore` versus LangMem) is not broken out publicly; they may use LangGraph primarily for orchestration.
- Google ADK memory documentation pages largely 404'd during research; ADK 2.0 is a breaking change from 1.x and its stable memory API shape is unclear from public docs alone.
- The AutoGPT 173k-star figure reflects 2023 hype; the new platform is pre-GA with no documented at-scale production deployments.
- Semantic Kernel vector stores are RC/Preview and the SK-to-MAF migration is ongoing, so Microsoft's current agent-memory story is in transition.
- Star counts are approximate page-signal reads, not API pulls.

## Context manifest

In scope (informing this document): the production documentation, repositories, and primary blog posts of the surveyed frameworks; the external-engine deep dives [KAOS-R5-1](./KAOS-R5-1-mem0.md) (Mem0) and [KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md) (Redis Agent Memory Server); and the prior ecosystem and tooling research [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) and [KAOS-R3](./KAOS-R3-memory-tooling.md).

Out of scope: the conceptual distinction between procedural, episodic, semantic, and temporal memory and the coding-agent and memory-framework systems that specialise in them, which are covered in [KAOS-R9](./KAOS-R9-procedural-temporal-memory-in-agent-systems.md); and any KAOS design commitment, which is the work of the architecture-decision records the [adr_high_level_components](../adrs/adr_high_level_components.md) index introduces.
