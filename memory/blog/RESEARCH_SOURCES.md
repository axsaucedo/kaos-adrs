# Verified research source bank — Agentic Memory at Scale

**Status**: v1, 2026-07-15. Compiled from 5 parallel research passes (foundations, benchmarks, security, tenancy/erasure/temporal, production systems). **Every arxiv ID and URL below was verified against the live abstract page / site during research** unless explicitly flagged. Vendor-claimed numbers are flagged. This is the durable source bank — the blog post cites a subset (see `REFERENCES_PROPOSED.md`); the rest is here for later iterations and other posts.

## 1. Foundational tiered-memory architectures

| Source | Year | Link | Citable point |
| --- | --- | --- | --- |
| MemGPT: Towards LLMs as Operating Systems (Packer et al., UC Berkeley) | 2023 | https://arxiv.org/abs/2310.08560 | Origin of OS-style tiered memory (main/external context, paging via function calls); introduced the DMR benchmark (93.4%) |
| Generative Agents (Park et al., Stanford/Google) | 2023 | https://arxiv.org/abs/2304.03442 | Memory stream + reflection + the canonical relevance×importance×recency retrieval scoring |
| CoALA — Cognitive Architectures for Language Agents (Sumers et al.) | 2023 | https://arxiv.org/abs/2309.02427 | Formalizes the episodic/semantic/procedural long-term memory taxonomy |
| A Survey on the Memory Mechanism of LLM-based Agents | 2024 | https://arxiv.org/abs/2404.13501 | Organizes memory by sources/forms/operations (write, read, consolidation, forgetting) |
| Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers | 2026 | https://arxiv.org/html/2603.07670v1 | Catalogs production decay mechanisms: time-based, frequency-based (LRU/Bloom), importance-weighted composite scores |

## 2. Summarization vs extraction — the write-vs-retrieval debate

| Source | Year | Link | Citable point |
| --- | --- | --- | --- |
| Recursively Summarizing Enables Long-Term Dialogue Memory | 2023 | https://arxiv.org/abs/2308.15022 | Research lineage for the rolling narrative digest (recursive re-summarization maintains coherence) |
| Storage Is Not Memory: A Retrieval-Centered Architecture for Agent Recall (Adler & Zehavi) | 2026 | https://arxiv.org/abs/2605.04897 | **The counterpoint**: "content discarded before the query is known cannot be recovered at retrieval time"; verbatim SQLite-only events + retrieval reports 93.0% LoCoMo vs Mem0 61.4% |
| WhenLoss: Diagnosing Write and Retrieval Bottlenecks (Yu, Lin, Wu) | 2026 | https://arxiv.org/abs/2605.24579 | Write-side (compression) gaps exceed retrieval-side gaps for 4/6 baselines; proposes EPC — "write with the future query in mind" |
| Diagnosing Retrieval vs. Utilization Bottlenecks in LLM Agent Memory (Yuan, Su, Yao) | 2026 | https://arxiv.org/abs/2603.02473 | **The counter-counterpoint**: accuracy spans 20pp across retrieval methods but only 3–8pp across write strategies — retrieval quality dominates write-tier choice |
| Beyond the Context Window: Cost-Performance Analysis of Fact-Based Memory vs Long-Context | 2026 | https://arxiv.org/abs/2603.04814 | Break-even heuristic: long-context wins raw recall on 2/3 benchmarks, but fact-memory becomes cost-favorable after ~10 turns at 100k-token scale |

**Editorial note**: the literature genuinely disagrees on whether write-side loss or retrieval-side failure dominates (2605.24579 vs 2603.02473). The post should present this as an open trade-off that the raw-turns-as-durable-source design hedges, not pick a winner.

## 3. Benchmarks and evaluation

| Source | Year | Link | Citable point |
| --- | --- | --- | --- |
| LongMemEval | 2024 | https://arxiv.org/abs/2410.10813 | Full 115K-token histories drop accuracy 30–60% vs oracle retrieval (GPT-4o: 60.6–64% full-context vs 87–92% oracle); five abilities incl. temporal reasoning + abstention |
| LoCoMo | 2024 | https://arxiv.org/abs/2402.17753 | Long-context LLMs and RAG "substantially lag behind human performance," weakest on long-range temporal/causal reasoning |
| Momento: Persistent Memory with Multi-Session Agentic Conversations | 2026 | https://arxiv.org/abs/2606.00832 | Shifts evaluation from chat-recall to agentic tasks; key failure mode is treating stale prior-session state as current (failure to re-validate) |

Unverified benchmark leads (titles found via search only, not fetched — verify before use): MemTrace (2606.17328), DynamicMem (2606.22877), Supersede/Memory-Update Gap (2606.27472), SubtleMemory (2606.05761), "Benchmarking Agent Memory in Interdependent Multi-Session Agentic Tasks" (2602.16313), BEAM.

## 4. Memory security — poisoning, injection, provenance

| Source | Year | Link | Citable point |
| --- | --- | --- | --- |
| AgentPoison: Red-teaming LLM Agents via Poisoning Memory or Knowledge Bases | 2024 | https://arxiv.org/abs/2407.12784 | <0.1% poison rate achieves >80% attack success on agent memory/RAG stores |
| MINJA: Memory Injection Attacks via Query-Only Interaction | 2025 | https://arxiv.org/abs/2503.03704 | Poisons memory through ordinary queries alone — no store access needed; 98%+ injection success. If the agent writes its own memory, every user is a write path |
| What If Prompt Injection Never Left? Cross-Session Stored Prompt Injection | 2026 | https://arxiv.org/abs/2606.04425 | Formalizes "stored XSS for agents": content written in one session executes as instructions in a later session |
| MPBench: From Untrusted Input to Trusted Memory | 2026 | https://arxiv.org/abs/2606.04329 | Taxonomy of 4 write channels / 9 weaknesses; empirical: agents that auto-write/auto-retrieve most aggressively are most exploitable |
| Securing LLM-Agent Long-Term Memory Against Poisoning (TMA-NM) | 2026 | https://arxiv.org/abs/2606.24322 | Proves content-based filtering is insufficient (defeated by "laundering" via summarization/tool echo); write-time origin/provenance binding is necessary |
| MemLineage: Lineage-Guided Enforcement for LLM Agent Memory | 2026 | https://arxiv.org/abs/2605.14421 | Memory as chain-of-custody: signed entries + derivation DAG; untrusted content can never alone justify a sensitive action |
| FARMA/SENTINEL: Forged Reasoning Attacks on Agent Memory | 2026 | https://arxiv.org/abs/2607.05029 | Poisoning stored *reasoning traces* (not facts) evades keyword/consensus filters |
| A Survey on Long-Term Memory Security in LLM Agents | 2026 | https://arxiv.org/abs/2604.16548 | Lifecycle framing: Write→Store→Retrieve→Execute→Share→Forget; retention/decay govern availability *and* confidentiality |
| Eguard: Defending LLM Embeddings Against Inversion | 2024 | https://arxiv.org/abs/2411.05034 | Embeddings alone leak reconstructable source text (95%+ token recovery undefended) — a shared vector index is a data-leak surface without raw-text access |
| Transferable Embedding Inversion Attack (ACL 2024) | 2024 | https://arxiv.org/abs/2406.10280 | Inversion via surrogate model — no query access to the victim embedder needed |

Flagged non-citable: "95%/98–100% cross-tenant leakage" stats circulating in industry blogs (Truto, witness.ai) — anecdotal, not peer-reviewed.

## 5. Multi-tenant vector search and isolation

| Source | Year | Link | Citable point |
| --- | --- | --- | --- |
| Curator: Efficient Indexing for Multi-Tenant Vector Databases (Jin et al.) | 2024 | https://arxiv.org/abs/2401.07119 | Academic treatment of the per-tenant-index vs shared-index-with-filtering trade-off |
| "No pre-filtering in pgvector means reduced ANN recall" (Pachot) | — | https://dev.to/franckpachot/no-pre-filtering-in-pgvector-means-reduced-ann-recall-1aa1 | Concrete demo: HNSW query for 15 filtered items returns only 11 — post-filtering silently drops results below the requested count |
| Qdrant Multitenancy docs | — | https://qdrant.tech/documentation/manage-data/multitenancy/ | Canonical vendor pattern: tenant payload field indexed and applied *inside* HNSW traversal, not post-hoc |
| Qdrant filterable-HNSW deep dive | — | https://qdrant.tech/articles/multitenancy/ | How filterable HNSW preserves recall under high-selectivity filters (extra edges keyed to payload values) |
| Qdrant 1.16 tiered multitenancy | 2026 | https://qdrant.tech/blog/qdrant-1.16.x/ | Noisy-neighbor pattern: shared shards for small tenants, auto-promotion to dedicated shards for large ones |
| pgvector 0.8 iterative index scans | — | (pgvector release notes) | Mitigation: iterative scans re-scan until enough post-filter matches found — trades latency for recall |

## 6. Forgetting, erasure, temporal memory

| Source | Year | Link | Citable point |
| --- | --- | --- | --- |
| When Machine Unlearning Meets RAG (Wang et al.) | 2024/25 | https://arxiv.org/abs/2410.15267 | Practical unlearning by modifying the knowledge base rather than the model — the mechanism for deleting facts from agent memory without retraining |
| (De)-Indexing and the Right to be Forgotten | 2025 | https://arxiv.org/pdf/2501.03989 | Right-to-erasure as an indexing/retrieval problem — analogous to scrubbing embeddings/summaries, not just raw text |
| Zep: Temporal Knowledge Graph Architecture (Rasmussen et al.) | 2025 | https://arxiv.org/abs/2501.13956 | Bi-temporal edges (valid time vs transaction time); superseded facts are **invalidated, not deleted**. DMR 94.8% vs MemGPT 93.4%; LongMemEval up to +18.5% acc, ~90% lower latency (vendor-authored) |
| Control-Plane Placement Shapes Forgetting | 2026 | https://arxiv.org/pdf/2606.15903 | Empirical: where forgetting/invalidation logic sits architecturally changes actual forgetting behavior (13 configurations) |

**Editorial note**: bi-temporal supersession ("invalidate, keep for audit") and hard right-to-erasure are *conflicting* operations on the same store — a nuance worth one sentence in the post.

## 7. Production systems and engineering write-ups

| Source | Year | Link | Citable point |
| --- | --- | --- | --- |
| Mem0 paper (Chhikara et al., ECAI 2025) | 2025 | https://arxiv.org/abs/2504.19413 | **Honest read of Table 2**: full-context J-score 72.9% > Mem0 66.9% (graph 68.4%) — memory's win is p95 latency 1.44s vs 17.1s (−91%) and ~7k vs ~26k tokens/conversation (>90% savings), *not* raw accuracy. +26%-over-OpenAI-memory is vendor-authored |
| Zep paper | 2025 | https://arxiv.org/abs/2501.13956 | See §6; Mem0-vs-Zep comparisons circulating online are disputed/vendor-claimed on both sides |
| Letta (MemGPT) memory-blocks docs | — | https://docs.letta.com/guides/core-concepts/memory/memory-blocks | Agent-editable always-in-context core memory vs archival vector tier — the "agent as editor of its own memory" design point |
| LangGraph persistence docs | — | https://docs.langchain.com/oss/python/langgraph/persistence | Thread-scoped checkpointers (short-term) vs cross-thread Store/`AsyncPostgresStore` (long-term) — ecosystem convergence on the same split |
| LangMem | — | https://langchain-ai.github.io/langmem/ | Memory toolkit over LangGraph `BaseStore` |
| OpenAI "Memory and new controls for ChatGPT" | 2024/25 | https://openai.com/index/memory-and-new-controls-for-chatgpt/ | Two-tier product design: explicit saved memories + inferred chat-history; background "dreaming" curation (direct fetch 403'd; corroborated via snippets) |
| Anthropic "Bringing memory to Claude" | 2025 | https://claude.com/blog/memory | Project-scoped memory isolation; stores an **editable summary** of extracted facts, not raw transcripts — product-level contrast to per-fact retrieval stores |
| Redis "Long-Term Memory Architectures for AI Agents" | 2026 | https://redis.io/blog/long-term-memory-architectures-ai-agents/ | Independent corroboration of the Mem0 LOCOMO numbers |
| Redis Agent Memory Server | — | https://github.com/redis/agent-memory-server | Two-tier (TTL-bound working + vector long-term); extraction async via background task queue — independent instance of the off-hot-path pattern |
| Agent Memory: Characterization and System Implications of Stateful Long-Horizon Workloads | 2026 | https://arxiv.org/abs/2606.06448 | First systems-level characterization across 10 memory systems; write- vs read-path cost split and query-volume amortization — the hot-path/background economics citation |

Vendor-claimed, flag if used: Mem0 "Token Optimization Playbook" (single-pass extraction cuts write-time LLM calls 60–70%); Supermemory latency-budget anecdote (200ms→400ms as index grows).

## Cross-cutting editorial takeaways from this research

1. **Memory systems trade accuracy for latency/cost** — Mem0's own table shows full-context beats it on accuracy; the production case is 10× latency and token reduction. The post must not overclaim accuracy.
2. **The write-vs-retrieval fault line is contested** (WhenLoss vs 2603.02473) — present as a trade-off the durable-raw-turns design hedges.
3. **Memory poisoning is an evidenced attack class, not hypothetical** (AgentPoison, MINJA, stored-XSS framing) — and auto-write/auto-retrieve aggressiveness correlates with exploitability (MPBench), which supports conservative defaults on memory tools.
4. **Provenance beats content filtering** for memory trust (TMA-NM, MemLineage).
5. **Supersession ≠ erasure** — bi-temporal invalidation and GDPR hard-delete conflict.
6. **A break-even exists** (~10 turns @ 100k tokens) for when a memory tier pays for itself.
7. **2026 evaluation is shifting** from recall accuracy to whether agents re-validate stale state (Momento).
