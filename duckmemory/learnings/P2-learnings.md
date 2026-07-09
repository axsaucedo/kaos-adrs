# P2 learnings — hybrid retrieval and the consolidation lifecycle

**Source:** [axsaucedo/agentmemory PR #2](https://github.com/axsaucedo/agentmemory/pull/2). **Status:** P2 complete; findings below gate P3 planning.

## L1 — Eager macro binding shapes how soft dependencies integrate (ADR-0003 refinement)

DuckDB validates macro bodies at creation, so a `memory_recall` referencing `fts_mem_facts.match_bm25` cannot even be registered unless the fts index exists. The shipped pattern: the entrypoint probes for the `fts_mem_facts` schema (it persists in the database file) and registers the BM25 flavor when found, falling back to the LIKE flavor if the index is absent *or the BM25 registration fails* (e.g. fts cannot autoload offline) — LOAD never fails on account of a soft dependency. Consequences:

- An fts index created mid-session upgrades recall **on the next open**, not immediately (a loaded extension's entrypoint does not re-run). Documented in `examples/hybrid.sql`; acceptable because agent processes reopen regularly.
- `memory_reindex()` collapsed to a documented two-statement pattern (`PRAGMA create_fts_index(..., overwrite = 1)` + stamping `fts_indexed_at` in `mem.meta`) exactly as the P1 reassessment predicted; ADR-0003's "lifecycle function" wording for reindex is superseded the same way ADR-0002's lifecycle section was.

## L2 — Behavioral consistency between BM25 and LIKE is a per-row property

The stale-index problem (fts never auto-updates) is handled *inside* the BM25 flavor: raw `match_bm25` is min-max normalized over the candidate set, and rows where BM25 yields NULL — unindexed rows and true non-matches alike — degrade per-row to the LIKE containment score. A fact written seconds ago therefore scores identically in both flavors, and reindexing only ever improves ranking granularity. Two normalization edge cases worth remembering: min-max maps the *lowest-scoring matched* row to 0.0 (indistinguishable from a non-match — the recorded ADR-0003 trade-off), and equal-tf documents produce identical BM25 scores, collapsing the range (degenerate min-max → all matched rows score 1.0). Test fixtures need graded term frequencies.

## L3 — fts/vss empirical facts (DuckDB 1.5.4)

- The index schema for `mem.facts` is `fts_mem_facts`; UUID docid columns work directly; index tables *and* the `match_bm25` macro persist in the file and autoload fts on first use after reopen.
- vss HNSW: index creation syntax is `USING HNSW (col) WITH (metric = 'cosine')`, and the optimizer plans `HNSW_INDEX_SCAN` only when the query uses the metric-matching function (`array_cosine_distance` for cosine — plain `array_distance` silently falls back to a full scan). The projection recipe (fixed-`ARRAY` side table joined back through `memory_recall`) works end to end and is validated in `test/hnsw_test.py`.

## L4 — SQL gotchas that cost time

- Macro parameters referenced in a grouped SELECT are treated like columns by the binder ("must appear in the GROUP BY clause"); wrap them in `any_value(...)`.
- sqllogictest expected blocks cannot express multi-line string values (rows are parsed line-by-line, columns tab-separated); flatten with `replace(content, chr(10), ' / ')` in the query.

## L5 — The fold plan as pure SQL worked cleanly

The window-sum selection (`sum(tokens) OVER (ORDER BY event_at DESC)` — fold rows whose kept-cumulative exceeds the target) expresses the whole budget/target semantics in one macro, and the apply DML is idempotent by construction because the plan is derived from the `folded` flag it updates. No Rust state, no new failure modes; `mem.meta` key-values as budget knobs (instead of custom extension settings) were sufficient and plain-UPDATE overridable.

## P3 scope reassessment (milestone gate)

P3 as planned, with these deltas:

1. **`memory_embed` as a Rust scalar function is still sound** — it performs HTTP, not SQL, so the P1 C-API finding does not constrain it. Re-add the `vscalar` crate feature dropped in P1. Mind the P1 finding that NULL arguments short-circuit C-API scalar functions (the function is not invoked; the row yields NULL) — fine for `memory_embed(text)`, where NULL-in/NULL-out is the desired semantics.
2. **Configuration via `mem.meta` + DuckDB secrets, not custom extension settings** — consistent with the fold knobs; ADR-0004's `SET memory_embed_*` wording adjusts to `mem.meta` keys (`embed_endpoint`, `embed_model`, `embed_timeout_ms`) with the API key in the secrets manager (or an `embed_api_key_env` meta key pointing at an environment variable, whichever the secrets C-API surface supports from Rust — validate first, it is the riskiest unknown of P3).
3. **`memory_recall_text` / `memory_context_text` are thin macros** delegating to `memory_recall(memory_embed(query_text), query_text := query_text, ...)` — they must be registered *after* the scalar function and inherit the recall flavor automatically. The vector/text behavioral-identity invariant tests exactly this delegation.
4. **Registration-order note:** `register_macros` already sequences context after recall; the text macros extend that chain (embed scalar → recall → context → *_text).
5. Keep the reopen, fts and hnsw Python tests green in every P3 PR; add a stub-server embed test in the same plain-Python family (sqllogictest cannot host an HTTP stub).
