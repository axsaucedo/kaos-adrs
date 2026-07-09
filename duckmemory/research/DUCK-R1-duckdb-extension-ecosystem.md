# DUCK-R1 — DuckDB extension ecosystem and capability constraints

This document establishes what the DuckDB extension ecosystem provides today for building an embedded agent-memory engine, and — equally important — what an extension **cannot** do, so the design in the ADRs rests on verified capability boundaries rather than assumptions. Findings are current as of mid-2026.

## 1. Vector similarity search: the `vss` core extension

- **Status.** `vss` is an official DuckDB core extension, still labeled **experimental**, built on the `usearch` library as a proof-of-concept for custom index types ([repo](https://github.com/duckdb/duckdb-vss), [docs](https://duckdb.org/docs/current/core_extensions/vss)).
- **Capability.** `CREATE INDEX ... USING HNSW (col)` over fixed-size `ARRAY(FLOAT, N)` columns (32-bit floats only). The index accelerates `ORDER BY <distance_fn> LIMIT k` queries and `min_by()` top-k aggregates. Three metrics, each pairing an index metric with a scalar function: `l2sq` (`array_distance`, default), `cosine` (`array_cosine_distance`), `ip` (`array_negative_inner_product`). Tunables: `ef_construction` (default 128), `ef_search` (64), `M` (16).
- **Persistence caveat.** HNSW indexes work on in-memory databases by default; persisting them to a database file requires `SET hnsw_enable_experimental_persistence = true`. The gate exists because **WAL recovery is not implemented for custom index types** — a crash with uncommitted index changes can corrupt the index or lose data. Serialization is non-incremental (the whole index is rewritten at every checkpoint and fully deserialized into RAM on first access after restart).
- **Mutation caveats.** Inserts/updates/deletes are supported, but deletes only mark entries, so the index degrades over time; `PRAGMA hnsw_compact_index('name')` rebuilds it. The index must fit entirely in RAM and its memory is not tracked by DuckDB's `memory_limit`. The `vss_join`/`vss_match` macros are brute-force and do not use the index.
- **Design implication.** Exact brute-force scans with `array_cosine_distance` over `ARRAY` columns need no index, are fully transactional and persistent, and are fast at agent-memory scale (well below the millions-of-rows regime where HNSW pays off). The HNSW index is therefore an opt-in acceleration, not a foundation the engine's correctness depends on ([VSS announcement](https://duckdb.org/2024/05/03/vector-similarity-search-vss)).

## 2. Keyword search: the `fts` core extension

- **Capability.** SQLite-FTS5-style search via `PRAGMA create_fts_index(table, id, cols...)`, materializing an inverted index as tables in an auto-created schema `fts_main_<table>`. Scoring via `match_bm25()` (Okapi BM25) with tunable `k`/`b` and a `conjunctive` (AND-all-terms) option; 25+ Snowball stemmers and configurable stopwords ([docs](https://duckdb.org/docs/current/core_extensions/full_text_search), [repo](https://github.com/duckdb/duckdb-fts)).
- **Limitation.** The index **does not auto-update** when the base table changes — it must be recreated with `overwrite := 1`. No phrase queries, highlighting, or synonyms. For a memory engine with a continuous write path, index recreation policy (on-write, on-recall-if-stale, or explicit) is the main design constraint ([hybrid-search reference](https://motherduck.com/blog/search-using-duckdb-part-3/)).

## 3. LLM and embedding extensions (precedents)

- **flockmtl / flock** (community, C++): deep LLM+RAG integration in SQL — `llm_complete`, `llm_filter`, `llm_rerank`, `llm_embedding`, aggregate LLM functions, hybrid-search fusion functions, with batching and caching, and model/prompt management as SQL resources; backed by a VLDB 2025 paper ([extension page](https://duckdb.org/community_extensions/extensions/flockmtl), [paper](https://arxiv.org/pdf/2504.01157)). Demonstrates that in-database LLM/embedding calls over HTTP are a viable and accepted extension pattern.
- **quackformers** (community, **Rust**): local BERT-family embedding generation in-database, intended to pair with `vss` for RAG ([repo](https://github.com/martin-conur/quackformers), [extension page](https://duckdb.org/community_extensions/extensions/quackformers)). A working precedent that a Rust community extension performing embedding inference ships through the official distribution channel.
- **llm** (community): a further LLM-call extension in the community catalog ([extension page](https://duckdb.org/community_extensions/extensions/llm)).

## 4. Rust extension development: what the C API allows

- **Template.** [duckdb/extension-template-rs](https://github.com/duckdb/extension-template-rs) is the official (experimental) template for pure-Rust extensions against the **C Extension API** — a function-pointer struct passed at load time, more version-portable than the C++ ABI. It demonstrates scalar functions and table functions; community-extension submission of Rust extensions works in practice (quackformers ships this way).
- **Coverage.** The C API supports scalar, aggregate, table, cast, replacement-scan, and copy functions. Safe wrappers exist beyond the template ([quack-rs](https://quack-rs.com/), and the `duckdb`/`libduckdb-sys` crates with the `loadable-extension` feature used by `agent_data_duckdb`).
- **The hard boundary.** The C API does **not** expose custom index types, custom storage, optimizer rules, or parser extensions. Custom indexes (like VSS's HNSW) require the internal C++ API (`BoundIndex`) — which is exactly why `vss` is C++ and why its persistence is fragile. A Rust extension can therefore add functions, macros, and pragmas, and lean on `vss`/`fts` for indexing, but cannot define a new index type itself ([duckdb-rs issue #370](https://github.com/duckdb/duckdb-rs/issues/370)).
- **Design implication.** This settles build-versus-adopt for the vector engine at the capability level: building our own index in Rust is not possible via the C API, so the choice is between reusing `vss`, brute-force scans, or switching the whole project to C++.

## 5. Distribution: DuckDB community extensions

- Publishing works "Homebrew-style": a small descriptor file PR'd into [duckdb/community-extensions](https://github.com/duckdb/community-extensions) points at the extension repository and version; central CI builds for all supported platform/arch combinations, signs the binaries, and hosts them at `community-extensions.duckdb.org` ([announcement](https://duckdb.org/2024/07/05/community-extensions), [development guide](https://duckdb.org/community_extensions/development)).
- Users install with `INSTALL duckmemory FROM community; LOAD duckmemory;` — the signature is verified on `LOAD`, and updates flow via `UPDATE EXTENSIONS`.
- Extensions can declare dependencies so `LOAD` can pull in `vss` and `fts` (both are core extensions that autoload in recent DuckDB versions).

## Bottom line

`vss` + `fts` provide vector and BM25 search today, each with a write-path caveat (experimental HNSW persistence without WAL recovery; FTS full reindex on change) that the storage ADR must design around — with exact brute-force scans as the always-correct fallback at agent-memory scale. A Rust extension via the C API can package the full memory surface as scalar/table functions and macros (including in-engine embedding or LLM calls, per the flockmtl/quackformers precedents) and distribute through the community repository, but custom index types are out of reach without moving to C++.
