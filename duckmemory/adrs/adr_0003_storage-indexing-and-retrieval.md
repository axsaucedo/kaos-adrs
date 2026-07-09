# ADR-0003 — Storage, indexing, and retrieval

**Status:** Accepted (reindex wording amended by P2 — see [learnings/P2-learnings.md](../learnings/P2-learnings.md))

## Context

This record fixes the physical realisation beneath the [ADR-0002](./adr_0002_sql-interface-and-embedded-execution-model.md) surface: the native table schemas, the embedding column type, how vector and keyword search execute given the `vss`/`fts` caveats established in [DUCK-R1](../research/DUCK-R1-duckdb-extension-ecosystem.md) (experimental HNSW persistence without WAL recovery; FTS indexes that never auto-update), the fusion implementation for the [ADR-0001](./adr_0001_memory-model-and-lifecycle-operations.md) scoring model, and schema versioning. The settled direction from the [high-level components index](./adr_high_level_components.md) — reuse `vss`+`fts`, iterate after an MVP — is recorded here with its precise shape.

## Decision

### Table schemas

Three data tables plus a meta table in the `memory` schema, each carrying the [ADR-0001](./adr_0001_memory-model-and-lifecycle-operations.md) envelope with scope keys as ordinary columns:

- `memory.turns` — id, session_id (required), scope keys, role, content, token_estimate, folded (boolean, default false), event/created timestamps, metadata JSON.
- `memory.digests` — id, session_id (required), version (monotonic per session), content, covers_turns_to (timestamp watermark), created_at, metadata JSON.
- `memory.facts` — full envelope (id, kind, content, embedding, namespace, agent_id, user_id, session_id, event_at, created_at, source, importance, access_count, last_accessed_at, pinned, expires_at, metadata JSON).
- `memory.meta` — key/value store holding `schema_version` and engine defaults recorded at creation.

### Embedding column: `FLOAT[]` (LIST), not fixed `ARRAY`

`memory.facts.embedding` is a variable-length `FLOAT[]` list. This is the pivotal storage choice: a fixed-size `ARRAY(FLOAT, N)` would require knowing the embedding dimension at table-creation time, which conflicts with LOAD-time idempotent schema creation ([ADR-0002](./adr_0002_sql-interface-and-embedded-execution-model.md)) and welds one model's dimension into the schema. LIST storage lets any dimension coexist (facts recall filters to the query's dimension via `len(embedding) = len(query)`), costs nothing at brute-force scan time (`list_cosine_similarity` is DuckDB-native), and keeps the schema stable if the host changes embedding models. The trade-off is that `vss` HNSW indexes require fixed `ARRAY` columns — accepted, because HNSW is an opt-in acceleration, not the default path.

### Retrieval: exact scan by default, HNSW as documented opt-in

- **Default vector search is an exact brute-force scan** — `list_cosine_similarity(embedding, query)` under the scope pre-filter, `ORDER BY score DESC LIMIT k`. It is fully transactional, WAL-safe, persistence-caveat-free, correct under any filter, and fast at agent-memory scale ([DUCK-R1](../research/DUCK-R1-duckdb-extension-ecosystem.md) section 1): a scoped scan over even hundreds of thousands of facts is milliseconds in DuckDB's vectorized engine.
- **HNSW is a documented opt-in for large stores**: the host materializes a fixed-`ARRAY` projection (`memory.facts_indexed`) and creates the `vss` index over it, accepting the experimental-persistence flag and compaction duty. The engine documents the recipe but does not manage it in v1 — automating the projection is deferred until a real deployment hits scan limits.

### Keyword search and the reindex policy

BM25 uses the `fts` extension over `memory.facts(content)`. Because the FTS index never auto-updates, the engine tracks staleness explicitly: `memory.meta` records `fts_indexed_at`, writes are visible via `max(created_at)`, and reindexing is a documented two-statement host pattern — `PRAGMA create_fts_index(..., overwrite = 1)` plus stamping `fts_indexed_at` *(amended: originally a `memory_reindex()` lifecycle function, superseded with the rest of the native-lifecycle surface by the P1 C-API finding recorded in [ADR-0002](./adr_0002_sql-interface-and-embedded-execution-model.md))*. `memory_recall` treats BM25 as **best-effort**: when the index is absent or stale, keyword scoring degrades to a documented LIKE-based containment score (weaker but never wrong-schema), and `memory_stats` surfaces staleness so hosts know to reindex. Rebuild-on-every-write is explicitly rejected as pathological for a continuous write path.

### Fusion implementation

The [ADR-0001](./adr_0001_memory-model-and-lifecycle-operations.md) weighted fusion runs in pure SQL inside the recall macro: cosine similarity mapped to [0,1], BM25 min-max normalized within the candidate set, recency as `exp(-ln(2) * age_days / half_life)`, importance clamped with a pinned bonus. Component scores are returned alongside the total so ranking is explainable and the weights tunable against real data. RRF remains the recorded fallback if score-scale pathologies appear in practice.

### Schema versioning and migration

`memory.meta.schema_version` is written at creation; on LOAD the entrypoint compares versions and applies forward-only idempotent migrations (numbered SQL steps compiled into the extension). Loading a newer schema with an older extension fails loudly rather than guessing.

## Consequences

- **Positive.** Zero persistence caveats on the default path — all memory state is ordinary DuckDB tables with full WAL/checkpoint/transaction semantics; any embedding dimension without DDL ceremony; scope pre-filtering is trivially correct (a `WHERE` clause, not an index feature); the whole retrieval path is testable with deterministic fixtures.
- **Negative.** Brute-force scans eventually hit a scale wall (mitigated: the opt-in HNSW recipe, and the scan is scope-pre-filtered so the wall is per-scope, not per-store); LIST storage forfeits transparent HNSW; BM25 quality depends on the host running reindex (mitigated by observable staleness and the degraded fallback).
- **Follow-on.** P1 benchmarks the exact scan at 10k/100k/1M facts to put numbers on the wall; the `fts` LIKE-fallback scoring needs calibration so weight defaults stay sensible in both modes.

## Alternatives considered

- **Fixed `ARRAY(FLOAT, N)` with dimension configuration.** Enables transparent `vss` HNSW, but forces an init-time dimension decision, breaks LOAD-time creation, and welds the schema to one model; the opt-in projection recipe recovers HNSW when actually needed; rejected as default.
- **HNSW on by default.** Inherits the experimental-persistence flag (no WAL recovery — crash can corrupt the index), unbounded untracked index RAM, and delete-degradation for a benefit that only materializes at scales most memory stores never reach; rejected.
- **Bundling a non-DuckDB vector index (custom Rust HNSW in extension state).** Duplicates storage outside transactions, must solve its own persistence/recovery — precisely the failure mode `vss` demonstrates — and the C API cannot register it as a real index ([DUCK-R1](../research/DUCK-R1-duckdb-extension-ecosystem.md) section 4); rejected.
- **Rebuild FTS on every write.** Correctness by brute force, but full-index recreation per insert is pathological for a memory engine's continuous write path; rejected for staleness-tracked explicit reindex.
- **RRF as the shipped fusion.** Robust but opaque and signal-lossy for recency/importance; kept as recorded fallback rather than default.
