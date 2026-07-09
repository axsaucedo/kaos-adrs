# P3 learnings — the embedding layer and shipping v0.1.0

**Source:** [axsaucedo/agentmemory PR #3](https://github.com/axsaucedo/agentmemory/pull/3), tag `v0.1.0`. **Status:** P3 complete — all three plan phases shipped.

## L1 — DuckDB's secrets manager has no C-API surface (ADR-0004 amendment)

The riskiest P3 unknown, resolved first and cheaply: the v1.5.4 C-API bindings (`libduckdb-sys` 1.10504.0) contain no `secret`-related symbol at all — the secrets manager is C++-internal, and `duckdb_secrets()` redacts values in SQL, so neither the extension nor a macro can read a stored key. ADR-0004's "API key resolved through DuckDB's secrets manager" is therefore unimplementable from a C-API extension today. The shipped replacement is one indirection better than a config value: `embed_api_key_env` in `mem.meta` names an *environment variable*, and the Rust scalar reads the process environment at call time — the key never enters SQL text, `mem.*` tables, the database file, or logs. Revisit if a secrets C-API lands.

## L2 — A Rust scalar doing HTTP is exactly as sound as predicted

`memory_embed_http` validates the P2 reassessment in full: `invoke` runs inside query execution on data DuckDB hands it, needing no connection and no post-LOAD SQL, so the P1 C-API finding does not constrain it. Empirical confirmations on the `vscalar` surface:

- **NULL short-circuiting is per-row and mixed-chunk-safe** — but only reachable through the macro's `CASE WHEN query_text IS NULL` guard, which serves double duty: it preserves NULL-in/NULL-out *and* prevents the coalesced configuration arguments from being the only non-NULL inputs (without the guard, an unconfigured endpoint would surface as `error(...)` even for NULL texts).
- **Chunk batching is free**: one `invoke` receives the whole row chunk, so one HTTP request embeds every text in it (asserted in the stub-server test: 3 texts + interleaved NULLs → exactly one request, inputs in order).
- **`volatile() = true` matters for an HTTP-backed scalar** — it stops the optimizer from constant-folding calls at bind time or caching across statements.
- List output is straightforward: flatten the vectors into the child `FLOAT` buffer, then `set_entry(row, offset, len)` per row.

## L3 — Configuration-in-the-macro beats configuration-in-Rust

The raw scalar takes explicit `(text, endpoint, model, timeout_ms, api_key_env)` arguments; the `memory_embed(text)` macro supplies them from `mem.meta` via scalar subqueries. This split kept every P3 property trivial: config changes take effect immediately (no LOAD-time snapshot, unlike the fts flavor), a missing endpoint raises a clear `error('...')` through `coalesce`, defaults live in one SQL expression, and the Rust stays a pure transport with no meta coupling. The same pattern (raw native function + config-supplying macro) is the template for any future native surface.

## L4 — The behavioral-identity invariant was free

`memory_recall_text` is literally `memory_recall(memory_embed(q), query_text := q, ...)`, so the ADR-0004 vector/text identity holds by construction and the test reduces to comparing two result sets. Registering the text macros last (scalar → recall → context → embed → *_text) satisfied eager binding with no new machinery — the P2 ordering lesson generalized without surprises.

## L5 — Release mechanics

`extension-ci-tools` stamps `extension_version.txt` from `git describe --tags`, so the `v0.1.0` tag *is* the release packaging — after tagging, `make configure` writes `v0.1.0` into the binary metadata with no further wiring. The community-extensions descriptor is drafted under `docs/` pinned to the tag (submission deferred per ADR-0005 until the surface settles).

## Closing state

All three phases of the [proposed split](../plan/proposed-split.md) are shipped and green (`make test_debug` / `make test_release`: 5 sqllogictest suites + reopen, fts, hnsw, embed Python tests): P1 core store (PR #1), P2 hybrid retrieval + consolidation (PR #2), P3 embeddings + packaging (PR #3, stacked). Deferred, with seams reserved: Layer-2 in-engine extraction (ADR-0004 revisit criteria), automated HNSW projection management, community-extensions submission.
