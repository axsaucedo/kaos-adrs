# Atomic stores — findings and plan deltas

## Outcome

The two atomic storage primitives are implemented and green against running Mem0 2.0.10, embedded Chroma, and pgvector/Postgres. The M0 deltas held up in practice: the Mem0 2.x signatures, the reserved shared-owner key, `psycopg[pool]`, telemetry suppression, and the pgvector-only `embedding_model_dims` were all exactly as M0 predicted. The notes below are the additional, finer-grained learnings to fold into M2 (the service that wraps these stores) and M4 (the operator that resolves their config).

## Confirmed in code

- **Pre-filtering is real on both backends.** Scoped recall never returns another owner's fact even when it is the exact nearest neighbour. The `DeterministicEmbedder` (offline, bag-of-words → L2-normalized 64-dim) makes this assertable without network or API keys.
- **One `ModelConfig` covers the whole stack.** Mem0's extraction LLM, Mem0's embedder, and the working-tier summarizer all bind to a single resolved OpenAI-compatible endpoint. There is no need for separate embedder/summarizer endpoint config — only separate *model names* under one base URL.
- **Eviction-by-summarization is cheap.** The working tier is a plain relational table; folding overflow into a rolling summary while keeping recent turns verbatim and retaining raw rows is a handful of SQL statements and works identically on SQLite and Postgres via the placeholder/serial abstraction.

## Deltas to fold into M2 / M4

1. **[M2] The service binds models lazily, not at construction.** `LongTermStore` and `ModelClient` both take a `ModelConfig` but should only dial the endpoint on first use, so the service can start (and report not-ready) before its `ModelAPI` is reachable. M2's readiness probe should reflect store reachability, not model reachability.

2. **[M2] `recall` return shape is a list of `{"memory": str, ...}` dicts** (Mem0 2.x `search` returns `{"results": [...]}` which the adapter unwraps). The HTTP layer should pass these through as-is rather than re-shaping, so the runtime client sees Mem0's native fields (id, score, metadata) for later relevance work.

3. **[M2] pgvector threshold is strict; Chroma is lenient.** pgvector applies Mem0's default similarity threshold (0.1) and returns nothing for a query that shares no tokens with stored facts; Chroma returns loosely. The service must not assume non-empty recall — empty is a valid, common result, and the runtime must degrade gracefully (recall is best-effort, never blocking).

4. **[M2] Chroma rejects `embedding_model_dims`; pgvector requires it.** The config resolver already encodes this (dims only set on `external`). M2 must keep dims out of the local-mode Mem0 config dict, or Chroma construction raises.

5. **[M4] Storage mode is a clean two-way switch.** `local` (embedded Chroma + SQLite, one PVC, single container) vs `external` (pgvector + Postgres, stateless replicas) is fully captured by `StorageConfig.type` plus the `local`/`external` sub-blocks. The operator's `MemoryStore` → service config mapping is a direct field copy; no conditional topology logic leaks into the store layer.

6. **[M3] `shared` scope needs the reserved owner id end-to-end.** The runtime client must send the same reserved shared-owner identifier the store expects; a missing owner makes Mem0 `search` raise `ValueError`. The client contract must make owner presence non-optional for every scope, including `shared`.

## Test infrastructure to reuse downstream

- `tests/_fakes.py::DeterministicEmbedder` and `tests/conftest.py` (`offline_models`, `pgvector_dsn` skip-gating on `KAOS_TEST_PGVECTOR_DSN`) are the offline test harness M2/M3 should reuse so their suites run without network or API keys, with the pgvector path opt-in behind the marker.
- CI now stands up `pgvector/pgvector:pg16` as a service container; M2's service tests can attach to the same job pattern.
