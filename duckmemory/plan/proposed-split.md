# DuckMemory — proposed work split and sequencing

**Status:** Accepted. **Scope:** delivery of the `agentmemory` DuckDB extension per [ADR-0001](../adrs/adr_0001_memory-model-and-lifecycle-operations.md)–[ADR-0005](../adrs/adr_0005_extension-architecture-packaging-and-distribution.md).

## Purpose

High-level chunking of the implementation before detailed task plans. The split is deliberately **coarse — three plans** — because each plan is itself executed as one full implementation plan (planned, built, tested, and reviewed as a self-contained pull request against [axsaucedo/agentmemory](https://github.com/axsaucedo/agentmemory)); the complexity lives inside each plan, not in the split.

## Guiding principles for the split

- **Riskiest seam first.** The retained-connection lifecycle pattern ([ADR-0002](../adrs/adr_0002_sql-interface-and-embedded-execution-model.md)) is the one decision with a recorded fallback; P1 validates it before anything is built on top.
- **Layer 0 before Layer 1.** The engine is fully usable with host-provided vectors before any network code exists ([ADR-0004](../adrs/adr_0004_embedding-and-llm-integration-boundary.md)); model integration lands last.
- **Every plan ends green and demoable.** Each PR leaves `make test` passing with SQLLogicTest coverage for everything it shipped, and a runnable SQL demo of its capability.
- **One PR per plan, reviewed sequentially.** Commits within a PR are self-contained and logical (scaffold, then schema, then surface, then tests never interleaved confusingly).
- **Learnings gate the next plan.** After each plan, findings are recorded under [learnings/](../learnings/) and the next plan's scope is re-assessed against them before planning starts.

## Current-state baseline

The design is complete (ADR-0001–0005 accepted); the [axsaucedo/agentmemory](https://github.com/axsaucedo/agentmemory) repository exists and is empty; the `agent_data_duckdb` skeleton (build system, vtab plumbing, SQLLogicTest harness) is available locally to port from; no code exists yet.

## The proposed plans

### P1 — Extension scaffold and core memory store

- **Goal.** A loadable `agentmemory` extension where the full Layer 0 write/recall/lifecycle loop works end to end with host-provided embeddings.
- **Scope.** Repository scaffold from the `agent_data_duckdb` skeleton (Cargo, Makefile, extension-ci-tools, duckdb-release.toml, CI on linux-x64/macos-arm64, `./tmp` gitignored); LOAD-time idempotent schema creation with the `memory.meta` version table; the three data tables per [ADR-0003](../adrs/adr_0003_storage-indexing-and-retrieval.md); the `memory_recall` and `memory_context` table macros with weighted fusion scoring (cosine via `list_cosine_similarity`, recency decay, importance; keyword term stubbed to the LIKE fallback); **validation of the retained-connection pattern** and on it the lifecycle functions `memory_erase`, `memory_purge`, `memory_touch`, `memory_stats`; SQLLogicTest suites including reopen/checkpoint and erasure fan-out; brute-force scan benchmark numbers (10k/100k facts) recorded in the PR.
- **Realises.** ADR-0002 (surface), ADR-0003 (storage/scoring core), ADR-0005 (skeleton, CI, testing).
- **Depends on.** Nothing.
- **Demoable.** A SQL script: LOAD, insert facts with embeddings across scopes, scoped recall with explainable component scores, erase a scope, reopen the database and recall again.

### P2 — Hybrid retrieval and the consolidation lifecycle

- **Goal.** The full [ADR-0001](../adrs/adr_0001_memory-model-and-lifecycle-operations.md) model: real BM25 hybrid recall and the short-term → digest fold loop.
- **Scope.** `fts` soft-dependency integration with staleness tracking in `memory.meta`, `memory_reindex()`, BM25 scoring in the recall macro with min-max normalization and the degraded LIKE fallback kept behaviorally consistent; the short-term tier in earnest — token estimation, budget/target settings, `memory_fold(session)` (evict, mark folded, version the digest with the verbatim-fallback summary, return the folded batch), fold threshold and idempotency tests; pinning/TTL semantics in recall and purge; the documented HNSW opt-in recipe validated once against `vss` in a test.
- **Realises.** ADR-0001 (consolidation/forgetting), ADR-0003 (fts policy, fusion completion).
- **Depends on.** P1 (schema, macros, retained-connection pattern).
- **Demoable.** A SQL script: a scripted conversation whose turns exceed budget, one `memory_fold` call producing a digest version and a folded batch, hybrid recall where a keyword-only match surfaces alongside semantic matches.

### P3 — Embedding integration, packaging, and documentation

- **Goal.** Layer 1 per [ADR-0004](../adrs/adr_0004_embedding-and-llm-integration-boundary.md) and a repository a stranger can adopt.
- **Scope.** The feature-gated `embed` module: `memory_embed(text)`, `memory_recall_text`, `memory_context_text` against an OpenAI-compatible endpoint, settings + DuckDB secrets manager for credentials, batching, 5s timeout, clean-failure degradation tests against a stub server; the vector/text behavioral-identity test invariant; README and usage documentation (quickstart, the fold host pattern, the HNSW recipe, degraded modes); community-extensions descriptor drafted but not submitted; release packaging (`v0.1.0` tag, artifact upload).
- **Realises.** ADR-0004 (Layer 1), ADR-0005 (packaging, distribution posture).
- **Depends on.** P2 (complete recall semantics to wrap).
- **Demoable.** A SQL script against a local stub (or real) endpoint: `SET` two settings, create a secret, then text-in/memories-out recall with no vectors in sight.

## Sequencing at a glance

| Plan | Delivers | Depends on | PR |
|------|----------|------------|----|
| P1 | Scaffold + Layer 0 core store | — | #1 |
| P2 | Hybrid recall + fold lifecycle | P1 | #2 |
| P3 | Layer 1 embeddings + packaging + docs | P2 | #3 |

## Cross-cutting notes

- **Learnings.** Each plan writes `learnings/P<n>-learnings.md` in this design area before the next plan is planned; decision deltas discovered during implementation are recorded there and, if they contradict an ADR, the ADR is superseded rather than silently diverged from.
- **Commit discipline.** Conventional commits, comprehensive bodies, one logical change per commit, sequential-review-friendly ordering within each PR.
- **Scratch discipline.** All ad-hoc validation scripts and artifacts under the repo's `./tmp` (gitignored); output suppression via `./tmp/null`.

## Explicitly later / out of the critical path

Community-extensions submission; in-engine extraction/summarization (Layer 2, revisit criterion in [ADR-0004](../adrs/adr_0004_embedding-and-llm-integration-boundary.md)); engine-managed HNSW projection; profile/temporal/procedural tiers; Windows CI.
