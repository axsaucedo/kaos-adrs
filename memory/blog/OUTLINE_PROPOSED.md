# Proposed outline — "Agentic Memory at Scale"

**Status**: Draft for review (v1). Each section maps to its source material; nothing is drafted until the outline is approved.

**Working title**: *Agentic Memory at Scale: Tiers, Scopes, and the Engineering Behind Agents That Remember*

**Subtitle (italic, matching prior posts)**: *A practical guide to memory tiers, multi-tenant scoping, engine selection, and Kubernetes-native memory infrastructure — using KAOS as the worked example.*

**Thesis callout (stated early, paid off in the close)**:

> Memory is not a vector database bolted onto an agent. Memory is a tiered, scoped, degradable subsystem — and the hard part is not storing memories, it is deciding who sees them, when they fold, and how the agent behaves when memory fails.

**Target shape**: ~12 flowing sections in the style of the autonomous post (concept-first, framework-agnostic, KAOS as worked example), borrowing the OTel post's verifiable walkthrough and closing checklist. ~500–600 lines.

---

## 1. Hook: everyone is adding memory to their agents

- Ecosystem trend framing (mirrors the OpenClaw hook): agents are stateless by default; the ecosystem rush to fix it — Mem0, Zep/Graphiti, Letta (MemGPT), OpenAI memory, framework-native memory in LangGraph/CrewAI/ADK.
- "We went through this journey designing memory for KAOS at fleet scale — research, selection, ADRs, implementation — and this post shares the learnings."
- Promise: the primitives (tiers, scopes, degradation, folding) transfer whatever stack you use.
- Cross-link both prior posts as the series context.
- *Sources*: R2/R3 ecosystem research for links; autonomous post hook as template.

## 2. The useful part of the hype: what "memory" actually means

- Deflate the overloaded term (mirrors "The Useful Part of the Hype"): memory ≠ context window, ≠ RAG, ≠ session history, ≠ task state (callback to the autonomous post's "task state is not memory").
- The taxonomy: short-term/working, episodic, semantic, procedural, temporal — with one-line definitions and citations (MemGPT, Generative Agents, ecosystem surveys).
- Crisp distinction: **conversational continuity** (same session) vs **learned knowledge** (across sessions) — the two problems get conflated and need different machinery.
- *Sources*: R2 taxonomy, R9 tier definitions, adr_0001.

## 3. Memory 101: the naive version everyone starts with

- Naive code (mirrors "AI Agents 101"): append every message to a list, replay the last N turns; then naive v2: embed everything into a vector store and similarity-search it back.
- Why it breaks — the table (naive memory vs production memory): unbounded context vs token budgets; verbatim replay vs distilled facts; one user vs many tenants; no forgetting vs right-to-erasure; blocking writes vs background extraction; single process vs fleet of replicas.
- Thesis callout lands here.
- *Sources*: R1 baseline (the original KAOS deque memory is literally this naive version — honest "we started here too" moment), proposed-split current-state baseline.

## 4. What changes at scale: the fleet questions

- Mirrors "Kubernetes Enters the Picture" positioning but for memory: the questions that become unavoidable with many agents, many users, many sessions:
  - Whose memory is it? (agent's? user's? the fleet's?)
  - Who is allowed to recall it? Can a model-controlled tool choose the scope?
  - What happens to a serving agent when the memory backend dies?
  - Where does extraction (LLM-heavy) run — on the request path?
  - How do you delete a user's memory everywhere, on demand?
- Frame: these are tenancy, topology, and failure-mode questions — distributed-systems plumbing again, not AI.
- *Sources*: adr_0005 scope, R7 target picture, memory-architecture.md.

## 5. Choosing an engine: build, adopt, or wrap (the selection story)

**The differentiator section — neither prior post showed a real selection process.**

- The landscape: ~38 tools screened; hard filters (self-hostable in-cluster, dedicated memory layer not a framework/substrate, maintained) and soft filters (license, infra delta, architectural diversity).
- The shortlist table (condensed from R4): Mem0 (vector-first), Zep/Graphiti (temporal knowledge graph), Cognee (hybrid graph+vector), Memobase (profile-first), Redis Agent Memory Server (Redis-native two-tier), custom baseline.
- The criteria that actually decided it (condensed from R6's C1–C12): capability coverage, retrieval quality, K8s deployability, infra delta, integration fit, multi-tenancy, license, maturity, write-path cost.
- Key reading: **no candidate dominates** — graph leaders buy capability at operational cost; Redis-native buys fit at maturity cost; custom buys fit at build-everything cost.
- The selection: **Mem0 as a library, behind our own interface** — and the crucial nuance: production systems keep their own memory interface regardless (Pydantic AI and peers provide message history only; R8 shows the norm is an external engine wrapped, not adopted wholesale). The gaps you accept (no OTel, app-level isolation, no Helm chart) become *your* integration work — name them.
- Callout: *you are not choosing a memory product; you are choosing which 60% you don't have to build.*
- *Sources*: R4, R6, R8, adr_0002.

## 6. The three tiers: short-term, medium-term, long-term

- The committed tier design with the mermaid tier diagram (adapted from memory-architecture.md):
  - **Short-term**: verbatim recent-turn window, session-scoped, relational rows, bounded by a **token budget** (not turn count), no embeddings.
  - **Medium-term**: one rolling narrative digest per session, append-only + versioned, relational.
  - **Long-term**: semantic/episodic facts extracted by Mem0 into a vector store, cross-session, scope-keyed.
- The counterintuitive insight, given full "if you only remember one pitfall" treatment: **the digest must stay OUT of the vector store.** Mem0 shreds input into atomic facts for retrieval; a narrative digest indexed that way loses continuity and pollutes search. Digest = injected verbatim; only raw evicted turns go to extraction.
- Second insight: **folding and extraction are always off the write path** — compaction and Mem0 extraction are background work; the turn never waits.
- Deferred honestly: temporal (bi-temporal) and procedural tiers, behind a future graph engine.
- *Sources*: memory-architecture.md tiers section, adr_0001, adr_0003, R11.

## 7. Scopes: whose memory is it anyway?

- The flat owner-key scope model as a table: `private` / `user` / `shared` / `session` → owner key → isolation boundary. The `private` vs `shared` sentinel trick (`kaos:shared`).
- **The store is the group** — no group CRD; the set of agents bound to one store *is* the sharing boundary.
- **Isolation strength is a deployment choice, not a code path** — shared store with filtering vs one store per tenant (physical isolation); no isolation-mode flag exists.
- Security callout (ties to the OTel post's redaction discipline): **scope is derived server-side from authenticated identity, fail-closed — never from model- or tool-supplied arguments.** An unresolvable scope fails rather than widening to an unscoped query; vector providers pre-filter inside the query so tenant results are never dropped by an unfiltered nearest-neighbour window.
- Right-to-erasure: one operation fans out synchronously across all three tiers.
- *Sources*: memory-architecture.md scope section, adr_0005, memorystore-crd.md.

## 8. Kubernetes enters the picture: memory as infrastructure

- Topology decision: **one central memory service per store, engine embedded as a library** — vs the rejected alternative (engine embedded in every agent: extraction on the serving process, N datastore connections, image bloat, replica divergence). Mermaid topology diagram.
- The MemoryStore CRD (short YAML): storage `local` (Chroma+SQLite on a PVC, single replica, dev on-ramp) vs `external` (pgvector+Postgres, stateless, 2 replicas + PDB, production); model roles referencing ModelAPI.
- **Memory is augmentation, not a dependency** — the degradation contract as a first-class design choice: recall is *always* soft (failure returns short-term-only context, never fails the turn); writes honour soft/strict; a store outage degrades a running agent (`MemoryDegraded` condition) but never removes it; only initial creation gates on store readiness.
- Fire-and-forget extraction, no durable queue — and *why* that's defensible (LLM-dominated turn latency; short-term tier is the durable path; the queue is a recorded follow-up, built only if measured).
- Design rationale at-a-glance table (decision → why), adopted directly from the docs — the recurring device.
- *Sources*: memory-architecture.md topology/control-plane, memorystore-crd.md, adr_0004, proposed-split.

## 9. Worked example: memory across sessions in ~10 minutes

- Condensed from docs/examples/memory.md, fully CLI/curl-verifiable (improvement over the OTel post's screenshot placeholders):
  1. Apply ModelAPI + local MemoryStore + Agent bound with `scope: shared, tools: all`.
  2. Session 1: tell the agent a fact (`kaos agent invoke`).
  3. Verify against the memory service directly (`curl /v1/recall`) — the turns are in the central store.
  4. Session 2: new session recalls the fact automatically.
- The automatic baseline vs explicit tools table (`read`/`write`/`all` → `search_memory`/`save_memory`) — and the repeat of the scope-never-from-the-model rule at the tool boundary.
- Pointer to the pgvector/semantic variant for real embedding-based recall.
- *Sources*: docs/examples/memory.md.

## 10. Build the minimal version yourself

- Mirrors "How You Could Build the Basics Yourself": the minimal shape of a tiered memory in ~40 lines — a recall-inject-persist wrapper around an agent run: token-budget window read, structured memory block injection, post-run append, threshold-triggered background fold+extract stub.
- Honest caveat list: no scope enforcement, no degradation contract, no erasure, no HA — "add these before the demo becomes a dependency."
- *Sources*: adr_0003 data-plane shape; original pattern from the autonomous post.

## 11. When NOT to add long-term memory

- Mirrors "When Not to Make It Autonomous":
  - Good fit: persistent users/goals, cross-session personalization, fleets sharing operational knowledge, long-horizon autonomous agents (callback to post 2).
  - Poor fit: single-shot tasks; strict data-residency contexts without an erasure story; when session history already covers it; when you can't afford the extraction LLM cost; when scope/tenancy is unclear (memory becomes a leak vector).
- *Sources*: R8 production-adoption findings, adr_0005 governance.

## 12. Lessons for production agentic memory (numbered, one-liners + a sentence)

Draft set (~8, to be tuned):
1. **Memory is augmentation, not a dependency** — design the outage path first; recall must degrade, never fail the turn.
2. **Separate conversational continuity from learned knowledge** — verbatim windows and distilled facts are different tiers with different stores.
3. **Keep narrative digests out of the vector store** — extraction shreds; digests must be injected whole.
4. **Never let the model choose the scope** — derive it server-side from authenticated identity, fail-closed.
5. **The store is the group** — sharing topology can be a deployment choice instead of an authorization system.
6. **Keep extraction off the hot path** — the user is already waiting on an LLM; don't make them wait on a second one.
7. **Adopt the engine, own the contract** — wrap the memory engine behind your own interface; the gaps you accept become your integration layer.
8. **Budget memory in tokens, not turns** — the context window is the real constraint (callback to budgets in post 2).

## 13. Closing + cross-links

- Pay off the thesis: memory done right is "boring" in the same way post 1's debugging is boring — tiered, scoped, observable, degradable plumbing.
- Explicit cross-links: observability post (memory ops emit OTel spans), autonomous post (always-on agents are the biggest memory producers and consumers — the loops that never stop are the ones that must remember).
- Optional appendix checklist (mirrors post 1): tiers / scoping / degradation / erasure / operations checkboxes.

---

## Open questions for review

1. **Selection-story depth** (§5): full condensed scoring matrix, or a lighter shortlist table + prose? The matrix is the differentiator but is the longest table in the post.
2. **Walkthrough depth** (§9): full copy-paste runnable (like the docs example) or condensed narrative with a link out to the docs? Prior posts differ (OTel = full, autonomous = condensed).
3. **Title**: "Agentic Memory at Scale: …" — subtitle variants welcome; prior posts used *how-it-works* subtitles.
4. **Publication target** assumed HackerNoon like the prior two (affects mermaid support — post 2 shipped mermaid, so assumed fine).
