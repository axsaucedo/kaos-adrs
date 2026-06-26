# KAOS-R2 — Agentic memory ecosystem research

This document surveys the current state of the art and practice of memory for LLM agents. It establishes the conceptual vocabulary, the key academic results, the architectural patterns that production systems use, and how mainstream agent frameworks expose memory. It is written to inform — but not constrain — the KAOS-specific selection and target design in later stages, and it reads alongside the baseline in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md).

Throughout, findings are tied back to KAOS: a Kubernetes-native agent orchestration framework whose data plane runs on Pydantic AI, and whose current memory is a per-session conversation log with local and Redis backends (see [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)). The in-scope sources for this survey are listed under [Context manifest](#context-manifest); the substantive citations appear inline.

## Why memory matters for agents

LLMs are stateless across calls: each request only "knows" what is in its context window. Memory is the discipline of deciding what an agent stores beyond a single call and what it brings back into context at inference time. Anthropic frames "retrieval, tools, and memory" as the three augmentation pillars of the augmented-LLM building block (`https://www.anthropic.com/engineering/building-effective-agents`), and a useful practitioner distinction has emerged between **memory** (what is persistently stored and retrieved on demand) and **context engineering** (the broader problem of what occupies the context window on any given turn, including system prompt, tool docs, retrieved memories, and few-shot examples). KAOS today addresses only the narrowest slice of this: replaying recent turns.

## Conceptual taxonomies

### Working (short-term) vs long-term memory

The most fundamental divide separates **working / short-term memory** — what the agent holds for the current turn or session (conversation history, intermediate tool outputs, the immediate focus) — from **long-term memory** — what persists across sessions and time (durable facts, summaries of past episodes, learned relationships). Mem0's documentation articulates this split and adds a four-layer lifetime model of **conversation → session → user → organization**, each with a different retention horizon (`https://docs.mem0.ai/core-concepts/memory-types`). In KAOS terms, the existing event log is purely working memory bounded by count; everything in the long-term column is absent.

### The cognitive split: episodic, semantic, procedural

The dominant framing for long-term memory, adopted almost universally, comes from cognitive science and was systematized for agents in **CoALA — "Cognitive Architectures for Language Agents"** (Sumers et al., 2023, `https://arxiv.org/abs/2309.02427`):

- **Semantic memory** — declarative facts about the world and the user (preferences, domain facts); implemented as a fact/knowledge repository.
- **Episodic memory** — records of the agent's own past events and actions; often reused as dynamic few-shot examples.
- **Procedural memory** — "how to" knowledge, residing in model weights and agent code, with the practical self-updating form being the agent editing its own system prompt.

CoALA further distinguishes the storage modalities: **in-context (working)** memory, **external** memory (databases, knowledge graphs, document stores), and **in-weights** memory (frozen at training). LangChain's "Memory for Agents" post applies the same triad to production systems — semantic memory via fact extraction into a vector store, episodic memory as retrieved few-shot examples, and procedural memory as system-prompt self-editing (`https://www.langchain.com/blog/memory-for-agents`).

### Entity and user memory

Both literature and frameworks separate **entity / user-level memory** — a structured record of facts about a specific person or thing — from raw episodic logs. Two shapes recur: a **profile** (a single, mutable, schema-constrained document updated in place) versus a **collection** (an unbounded, growing bag of atomic facts). LangMem implements exactly this distinction, and Mem0 scopes memories by `user_id`, `run_id`, and `org_id` so that user-level memory outlives any one session. KAOS currently stores `user_id` on a session but performs no cross-session aggregation, so it has neither profiles nor collections.

## Key academic literature

The following results define the field and recur as reference points in later stages.

- **MemGPT — "Towards LLMs as Operating Systems"** (Packer et al., 2023, `https://arxiv.org/abs/2310.08560`). Draws an OS analogy: a fixed main context (RAM) plus larger external storage (disk), with the model given explicit function calls to page information in and out (`archival_memory_search`, `conversation_search`, etc.). Introduced the **Deep Memory Retrieval (DMR)** benchmark for multi-session recall (93.4%). Productized as **Letta** (`https://letta.com`).
- **Generative Agents ("Smallville")** (Park et al., 2023, `https://arxiv.org/abs/2304.03442`). Introduced the **memory stream** and the canonical retrieval formula scoring each memory by **recency** (exponential decay), **importance** (an LLM-rated 1–10 salience), and **relevance** (embedding similarity to the query). Also introduced **reflection**: a periodic background process that synthesizes higher-order insight memories from many low-level observations. This paper established the vocabulary most production systems still use.
- **Reflexion — "Language Agents with Verbal Reinforcement Learning"** (Shinn et al., 2023, `https://arxiv.org/abs/2303.11366`). Maintains verbal short-term and long-term memory; on task failure the agent writes a textual self-reflection that is prepended to the next attempt, enabling multi-trial self-improvement without weight updates.
- **A-MEM — "Agentic Memory for LLM Agents"** (2025, `https://arxiv.org/abs/2502.12110`). A Zettelkasten-inspired design where the agent autonomously generates contextual notes for each memory, links related memories with typed edges, and evolves existing memories as new experience arrives — placing the structure of memory itself under agentic control.
- **A Survey on the Memory Mechanism of LLM-based Agents** (2024, `https://arxiv.org/abs/2404.13501`). The most comprehensive academic survey; organizes memory along **sources** (conversations, feedback, knowledge bases), **forms** (natural language, embeddings, structured DBs, model weights), and **operations** (write, read, consolidation, forgetting).

### Benchmarks and knowledge-graph memory

- **LoCoMo — "Evaluating Very Long-Term Conversational Memory of LLM Agents"** (2024, `https://arxiv.org/abs/2402.17753`). 50 dialogues of ~300 turns / ~9K tokens across up to 35 sessions. Long-context LLMs plus RAG improve memory QA by 22–66% over a no-memory baseline but remain ~56% below humans overall and ~73% below on temporal reasoning; RAG over per-speaker assertion databases is the strongest balanced approach.
- **LongMemEval — "Benchmarking Chat Assistants on Long-Term Interactive Memory"** (2024, `https://arxiv.org/abs/2410.10813`). 500 questions across information extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention. Long-context models drop 30–60% on the ~115K-token setting; design insights include round-level storage granularity, **multi-key indexing** (+9.4% recall@k, +5.4% QA accuracy), time-aware query expansion (+6.8–11.3% temporal recall), and Chain-of-Note reading (up to +10 absolute QA points).
- **Zep — "A Temporal Knowledge Graph Architecture for Agent Memory"** (2025, `https://arxiv.org/abs/2501.13956`). The Graphiti engine builds a temporally-aware knowledge graph with validity intervals on edges; contradicted facts are **invalidated, not deleted** (non-lossy history). Reports DMR 94.8% (vs MemGPT 93.4%) and LongMemEval gains up to 18.5% accuracy with ~90% lower latency than a baseline RAG implementation. Graphiti is open source (`https://github.com/getzep/graphiti`).
- **HippoRAG** (2024, `https://arxiv.org/abs/2405.14831`) — a neurobiologically inspired KG of OpenIE triples retrieved with Personalized PageRank, strong on multi-hop associative recall. **EM-LLM** (2024, `https://arxiv.org/abs/2407.09450`) — segments long context into "events" via surprise-based boundary detection for episodic KV-cache paging.

## Architectural patterns

These are the building blocks a production memory layer combines.

- **Summarization / progressive summarization.** Replace old turns with a running compressed summary, keeping recent turns verbatim. LangChain's buffer/summary/window/summary-buffer memory variants codify the spectrum (`https://www.pinecone.io/learn/series/langchain/langchain-conversational-memory/`); the summary-buffer hybrid (recent verbatim + summarized older history) is the common default.
- **RAG over conversation history.** Index turns into a retrieval store and pull only relevant ones into context. Empirically, **round-level granularity with multi-key indexing** (storing both the raw turn and extracted facts as keys) outperforms flat session-level storage (LongMemEval).
- **Vector retrieval of memories.** Embed each memory and retrieve by similarity, typically blended with importance and recency per the Generative Agents formula. This is the workhorse of production systems and is store-agnostic (Pinecone, Weaviate, Qdrant, pgvector, in-process stores).
- **Knowledge-graph / temporal-graph memory.** Encode facts as typed subject–relation–object triples with temporal validity, enabling multi-hop traversal, entity resolution, and "what was true at time T" queries. The Graphiti/Zep pipeline — entity extraction, resolution, fact extraction, temporal invalidation, community summarization, then hybrid BM25+vector+reranker retrieval — is the reference design.
- **Reflection / consolidation / insight extraction.** Periodically distill many raw memories into higher-order insights (Generative Agents), or consolidate, update, and generalize a memory store with an LLM (LangMem's `create_memory_manager`). The core risk is calibration: over-extraction hurts precision, under-extraction hurts recall.
- **Importance scoring and forgetting.** Beyond similarity, recall should weight a memory's importance and its "strength" (a function of how recently and frequently it was used), per the LangMem conceptual guide (`https://langchain-ai.github.io/langmem/concepts/conceptual_guide/`). Forgetting strategies range from recency half-life decay (CrewAI exposes `recency_half_life_days`) to non-lossy temporal invalidation (Zep) to OS-style eviction to archival storage (MemGPT). KAOS today only has the crudest form — count-bounded eviction of the oldest events, which is information loss, not consolidation (see [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)).
- **Hot-path vs background writing.** Memory can be written **inline** (the agent calls a memory tool during the turn — immediate but adds latency and conflates memory with task execution) or in the **background** (a separate post-session process extracts memories — zero live latency, deeper analysis, but delayed availability). The LangChain blog and LangMem guide formalize this trade-off; production systems often combine both.
- **Scoping.** Memory is organized hierarchically — thread/session, user, agent, and organization — with namespaces or scope trees controlling what each agent may read or write. Mem0 (`conversation → session → user → org`), LangMem (namespace tuples), and CrewAI (a filesystem-like scope tree with per-agent subtrees and cross-scope slices) all implement this. For KAOS, scoping is the natural bridge between memory and its multi-tenant, multi-agent, A2A-delegating execution model, where today there is only per-session isolation.

## Framework-native memory

- **LangGraph + LangMem.** LangGraph separates short-term memory (thread-scoped checkpointers over Postgres/Redis/SQLite) from long-term memory (a cross-thread `BaseStore` with `put/get/search`, optional vector index). LangMem layers semantic collections, schema-constrained profiles, episodic few-shot memories, and procedural prompt-optimization on top, offering both hot-path tools and a background memory manager (`https://langchain-ai.github.io/langmem/`).
- **LlamaIndex.** A `ChatStore` + `ChatMemoryBuffer` architecture with many backends (in-memory/JSON, Redis, Postgres, DynamoDB, Azure, AlloyDB), plus `VectorMemory` and `SimpleComposableMemory` for hybrid recent-plus-semantic recall (`https://developers.llamaindex.ai/python/framework/module_guides/storing/chat_stores/`).
- **Pydantic AI.** Memory is **message history only**: `result.all_messages()` / `new_messages()` return typed `ModelMessage` objects, `message_history` injects prior turns, `conversation_id` auto-correlates runs in a thread, and `ModelMessagesTypeAdapter` serializes history to JSON. There is **no native vector memory, semantic retrieval, cross-session user memory, or importance scoring** (`https://pydantic.dev/docs/ai/core-concepts/message-history/`). This is directly relevant: KAOS's current memory is essentially the Pydantic AI message-history pattern wrapped with persistence and bounded retention, so any long-term capability must be added above the framework — by extending KAOS or integrating a dedicated layer.
- **CrewAI.** A unified `Memory` API with a hierarchical scope tree, composite semantic+recency+importance scoring, LLM-based `extract_memories`, and automatic store-after-task / recall-before-task behavior (`https://docs.crewai.com/v1.14.7/en/concepts/memory.md`).
- **Others.** AutoGen 0.4+ exposes a `Memory` protocol (`ListMemory`, `ChromaDBMemory`) attachable to an agent; OpenAI's ChatGPT uses hot-path user memory (no developer API for the memory layer; Assistants threads auto-truncate); Google's Vertex AI Agent Engine / ADK offers a managed **Memory Bank** (preview) with `add/get/search_memory` over managed vector search. (The ADK and AutoGen docs were partially unreachable during this survey and are reported at lower confidence.)

## Synthesis for KAOS

Several conclusions carry directly into KAOS selection and design:

- KAOS today implements only the first rung — bounded working memory — of a well-understood ladder that climbs through summarization, vector retrieval, reflection/consolidation, knowledge-graph structuring, and principled forgetting.
- The field has converged on a stable conceptual model (working vs long-term; semantic/episodic/procedural; profiles vs collections; hierarchical scoping) and a canonical retrieval formula (relevance × importance × recency). Any KAOS target design should speak this vocabulary.
- Two architectural families dominate production long-term memory: **vector-first** layers (Mem0, LangMem, LlamaIndex VectorMemory) and **graph-first** temporal-knowledge-graph layers (Zep/Graphiti), with credible benchmark evidence (LongMemEval, DMR, LoCoMo) that structured temporal approaches improve accuracy and latency on long horizons.
- Because Pydantic AI deliberately provides only message history, KAOS must own the long-term layer regardless of build-versus-adopt — either by extending its custom implementation or by integrating a dedicated memory system behind its existing `Memory` interface.
- The hot-path versus background trade-off and hierarchical scoping map naturally onto KAOS's Kubernetes-native, multi-tenant, A2A-delegating runtime, and should be first-class concerns in the later target picture.

The tooling that realizes these patterns — and KAOS's own implementation as a baseline option — is catalogued and compared in the stages that follow.

## Context manifest

In scope (consulted for this survey): primary academic sources (CoALA `2309.02427`, Generative Agents `2304.03442`, MemGPT `2310.08560`, Reflexion `2303.11366`, A-MEM `2502.12110`, Memory Survey `2404.13501`, LoCoMo `2402.17753`, LongMemEval `2410.10813`, Zep `2501.13956`, HippoRAG `2405.14831`, EM-LLM `2407.09450`); framework and vendor documentation (Pydantic AI message history, LangGraph/LangMem, LlamaIndex chat stores, CrewAI memory, Mem0 memory types); and practitioner write-ups (LangChain "Memory for Agents", Pinecone conversational-memory tutorial, Anthropic "Building Effective Agents"). The KAOS baseline is taken from [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md).

Out of scope (deferred to later stages): the full tool-by-tool catalogue with licensing and Kubernetes-deployment detail, the shortlist comparison, per-tool deep dives, the final selection, and the KAOS target design. Vendor benchmark claims are reported with their source so they can be weighed, not taken as settled, in selection.
