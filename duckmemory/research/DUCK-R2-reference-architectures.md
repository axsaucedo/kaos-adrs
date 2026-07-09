# DUCK-R2 — Reference architectures: KAOS memory and the agent_data_duckdb extension

This document distills the two reference systems DuckMemory draws on: the **KAOS memory subsystem** (what a production agent-memory engine must model and do — the domain reference) and the **`agent_data_duckdb` extension** (how a Rust DuckDB extension is structured, built, and tested — the implementation reference). DuckMemory is standalone and owes neither system compatibility; both are mined for proven patterns and known trade-offs.

## 1. Domain reference: the KAOS memory architecture

The KAOS memory design ([memory ADRs](../../memory/adrs/adr_high_level_components.md), [proposed split](../../memory/plan/proposed-split.md)) is a shipped, production-oriented tiered memory system. Its load-bearing concepts, independent of its Kubernetes topology:

- **Three-tier model.** A **short-term tier** of verbatim recent turns bounded by a token budget (plain relational rows, append-only, no embeddings); a **medium-term tier** holding one rolling narrative digest per session (append-only, versioned relational rows, never vector-indexed); and a **long-term tier** of atomic extracted facts retrieved by scope-filtered vector search. Recall assembles all three into one structured block.
- **Cascade write model.** Turns enter the short-term window only; when the window crosses a compaction threshold, evicted turns are folded in a batch — summarized into the medium-term digest and handed to LLM extraction for long-term facts. Extraction is batched per fold plus a session-end flush, never per turn, and always off the recall/write hot path.
- **Scope model.** A flat four-value scope enum (`private | user | shared | session`) mapping to owner keys, enforced **fail-closed at the engine boundary** — no unscoped query path exists, and scope filtering happens **inside** the vector query (pre-filtering), never as a post-filter over an unfiltered k-NN window, because post-filtering silently drops a tenant's relevant memories.
- **Metadata envelope.** Every item carries id, scope owner keys, event/ingestion time, provenance, importance, access stats, and retention/pin policy — the schema that keeps tiers interoperable.
- **Lifecycle operations.** Recall (synchronous), write (append-only), consolidate/fold (asynchronous, threshold-triggered, lazy-read), and forget (scope-targeted erasure that fans out across all tiers synchronously, for right-to-erasure semantics).
- **Degradation contract.** Memory is augmentation: recall failure degrades to short-term-only context and never fails the agent turn.

**What changes in an embedded engine.** KAOS distributes these concerns across a central HTTP service, a background executor, Postgres/Chroma, and an operator. DuckMemory collapses them into one process and one database file, which removes whole problem classes (network degradation, replica coordination, server-side identity injection) and sharpens others: there is no daemon, so *asynchronous consolidation has no home* — folding and extraction must run inside some caller's SQL statement or be explicitly invoked by the host; and there is no trusted server boundary, so scope is a data-organization and correctness feature (pre-filtered retrieval), not a security boundary against the embedding process.

## 2. Implementation reference: the `agent_data_duckdb` extension

`agent_data_duckdb` is a working Rust DuckDB extension (table functions over agent CLI session data) whose skeleton DuckMemory should reuse directly.

- **Build shape.** A `cdylib` crate on `duckdb` / `libduckdb-sys` (pinned versions, `loadable-extension` feature), entered via `#[duckdb_entrypoint_c_api()]` in `agent_data_duckdb/src/lib.rs`, built through a Makefile that includes `extension-ci-tools/makefiles/c_api_extensions/rust.Makefile`, with the DuckDB version pinned in `duckdb-release.toml` and refreshed by an update script. Output is a loadable `.duckdb_extension` binary.
- **Generic table-function pattern.** A single `TableFunc` trait (`agent_data_duckdb/src/vtab.rs`) with three methods — `columns()` (schema), `load_rows()` (I/O), `write_row()` (output) — wrapped by a generic `GenericVTab`, so each function is a small trait impl rather than bespoke bind/init/execute plumbing. Bind stores parameters; execution lazily loads rows and emits them in 2048-row batches via an atomic offset.
- **Lenient data handling.** Serde types with `#[serde(default)]` for sparse/evolving JSON; malformed input becomes rows tagged `_parse_error` rather than query failures, letting SQL consumers filter.
- **Testing.** DuckDB's SQLLogicTest format: deterministic fixtures plus `.test` files with pinned row counts, schema/NULL assertions, cross-source joins, and edge cases (missing paths return zero rows), all run by `make test`.
- **Known gaps to improve on.** Every call re-scans disk (no incremental state), row loading is single-threaded, and there is no filter pushdown — all rows materialize before DuckDB filters. Acceptable for read-only log inspection; a memory engine whose data *lives in DuckDB tables* sidesteps the re-scan and pushdown issues entirely, since ordinary SQL over native tables gets the full optimizer.

## 3. Requirements this implies for DuckMemory

1. A memory record model (envelope, tiers, scope keys) expressible as plain DuckDB tables, so persistence, transactions, and erasure are ordinary SQL — the engine's own storage engine does the heavy lifting.
2. Scope-filtered hybrid retrieval (vector + BM25 + recency/importance) implemented as pre-filtering `WHERE` clauses over native tables, which DuckDB gives for free and which the KAOS research identified as the correctness-critical property.
3. An explicit answer for where consolidation/extraction executes in a daemonless embedded engine, and for whether the engine or the host performs embedding/LLM calls.
4. The `agent_data_duckdb` skeleton (crate layout, `TableFunc` trait, extension-ci-tools build, SQLLogicTest suite, version pinning) as the implementation base, extended with scalar functions and macros for the write/recall surface.
5. Reuse of `vss`/`fts` for indexing per [DUCK-R1](./DUCK-R1-duckdb-extension-ecosystem.md), with brute-force scans as the always-correct default at agent-memory scale.
