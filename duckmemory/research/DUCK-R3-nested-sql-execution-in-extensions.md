# DUCK-R3 — Nested SQL execution from DuckDB extensions: spike results and ecosystem survey

Evidence base for [ADR-0008](../adrs/adr_0008_cpp-execution-model-spike.md). Two empirical
sources, both from 2026-07-10: (1) a C++ spike on `duckdb/extension-template` pinned to DuckDB
v1.5.4 (`08e34c447b`), run in `agentmemory/tmp/cpp-spike/`; (2) a survey of open-source extension
codebases, shallow-cloned and audited with file:line citations, run in
`agentmemory/tmp/nested-sql-research/`. Both tmp directories are gitignored working artifacts;
this document is the durable record.

## 1. The question

`agent_memory`'s C-API constraint (P1, [ADR-0002](../adrs/adr_0002_sql-interface-and-embedded-execution-model.md)
amendment): an extension on the stable C ABI cannot execute SQL after LOAD, so the single-call
`add()` (insert turn → check window → fold) lives host-side (ADR-0006 D4). The question: does the
C++ internal API change this — can `CALL memory_add(...)` run the pipeline in-engine, and with
what transaction semantics? And is internal SQL execution an established pattern in the ecosystem,
possibly with a same-transaction route we missed?

## 2. Spike results (C++, DuckDB v1.5.4, macOS arm64)

Three registrations of a minimal table function in the template's extension:

| Route | Mechanism | Result |
|---|---|---|
| `memory_add_spike` | `Connection(*context.db)`, SQL at bind | works |
| `memory_add_spike_execute` | same, SQL at execution callback | works |
| `memory_add_spike_context` | re-entrant `context.Query(...)` | **hangs until killed** |

Verified behaviors of the working (new-connection) route:

- **Multi-statement flow**: insert → count → conditional second insert → return, branching on
  intermediate results, all inside one top-level `CALL`. The mechanical shape of an in-engine
  `memory_add` is proven.
- **Separate transaction, by construction**: caller `BEGIN; CALL ...; ROLLBACK` does **not** undo
  the inner write (row survived); the inner connection does **not** see the caller's uncommitted
  rows (caller-inserted row invisible to the CALL). Each inner `Query` autocommits unless the
  extension opens its own transaction on the inner connection.
- **Errors**: an inner SQL error surfaces cleanly as the CALL's error (no crash), but earlier
  inner statements remain committed — atomicity requires explicit inner BEGIN/COMMIT/ROLLBACK.
- **Concurrency (ADD-only shape)**: caller-held transaction inserting into the same table the
  CALL appends to — no lock error or conflict. (No claim about conflicting updates/deletes.)
- **Build cost**: clean debug build 3m04s (8 jobs, M1 Max, no ccache/ninja), incremental ~19s;
  C++ extensions compile against the version-specific internal C++ ABI → rebuild per exact DuckDB
  version and platform, vs the C-API's build-once stable ABI.

## 3. Ecosystem survey — internal SQL is a common pattern, always separate-transaction

Repositories audited (pinned revisions in parentheses; citations are file:line at those revisions):

- **flockmtl** (`0bfec7ad`) — `Config::GetConnection` constructs `duckdb::Connection con(*Config::db)`
  (`src/core/config/config.cpp:26-31`); used at extension load (schema/table creation with explicit
  `BeginTransaction`/`Commit`, `config.cpp:88-95`), at **parser time** for model/prompt
  CREATE/UPDATE/DELETE (`src/custom_parser/query_parser.cpp:83-96`), and at runtime for model/prompt
  lookup (`src/model_manager/model.cpp:186-206`). Never calls `context.Query`. Parser-time side
  effects are non-atomic with the statement ultimately returned.
- **DuckPGQ** (`ebfa7b50`) — the closest `CALL memory_add` analogue: its table-function execution
  callback (`src/core/functions/table/create_property_graph.cpp:294-435`) mutates in-memory
  registry state, then opens `Connection(*context.db)` and runs SELECT/DELETE/INSERT against its
  metadata table. Writes commit independently under the new connection's autocommit; in-memory
  mutations are outside rollback machinery entirely. Atomicity with the outer statement is
  knowingly given up.
- **duckdb-substrait** (`e61b3bdf`) — `src/substrait_extension.cpp:278-284`: literal comment
  *"Create a new connection to avoid deadlock with the locked context"*, then
  `Connection(*context.db)` at bind; execution callback likewise (`:333-340`). Notes temp objects
  don't round-trip (`:166-167`) — the visible session-state cost of the sibling connection.
- **ggsql-duckdb** (posit-dev) — documents the identical conclusion in prose: *"Calling `Query`
  back into the outer `ClientContext` from inside an executing table function deadlocks on the
  context's mutex, so we open a sibling `Connection`"*; consequently ggsql queries can't see temp
  tables, session `SET` variables, or client-registered relations.
- GitHub code search additionally surfaced `ducksync`, `sirius`, `sidra_client`, `duckdb-raquet`,
  and Paimon/Fluss extensions using the same construct (prevalence evidence only; not
  transaction-audited).

**Conclusion**: `Connection(*context.db)` is the community-standard workaround, used from parser
hooks, load, bind, and execute callbacks. No inspected extension achieves arbitrary
same-transaction nested SQL — every one accepts separate-session/separate-transaction semantics.

## 4. Why re-entrant `context.Query` deadlocks (confirmed at source)

`ClientContext` owns a plain **non-recursive** `mutex context_lock`
(v1.5.4 `src/include/duckdb/main/client_context.hpp:318`); `ClientContextLock` guards it (`:329`)
and string `ClientContext::Query` begins with `auto lock = LockContext()`
(`src/main/client_context.cpp:1042-1047`). A callback executing inside a query already holds the
serialized context; calling `context.Query(...)` on the same thread re-acquires the same
non-recursive mutex → self-deadlock before parsing. Maintainer-consistent:
[duckdb#2540](https://github.com/duckdb/duckdb/issues/2540) (one connection is not re-usable
concurrently; multiple connections to one database are supported).

**Near-miss APIs checked and ruled out:**

- `ClientContext::RunFunctionInTransaction` (`client_context.cpp:1236-1276`) — brackets a supplied
  **C++ closure** in the context's current/new transaction; does not parse/bind/execute SQL, and
  its public entry re-acquires `context_lock`, so it is equally unusable from inside a callback.
  Core uses it for catalog registration and appender metadata binding.
  [duckdb#8124](https://github.com/duckdb/duckdb/issues/8124) records maintainer intent and the
  fix disallowing it during an active transaction.
- Core's `query()`-style dynamic-SQL functions parse/bind the supplied SELECT **into the outer
  plan** (hence inherit the transaction) but are restricted to single-SELECT/non-DDL shapes —
  [duckdb discussion #12985](https://github.com/duckdb/duckdb/discussions/12985). Not a DML route.

## 5. The exception: same-transaction writes WITHOUT SQL (`InternalAppender`)

Core itself writes into the **caller's** transaction from inside table functions — via internal
storage APIs, not SQL: `InternalAppender` takes the caller's `ClientContext` + `TableCatalogEntry`
(`src/main/appender.cpp:725-732`) and flushes through
`table.GetStorage().LocalAppend(table, context, ...)` (`:738-742`) →
`LocalStorage::Get(context, db)` — transaction-local data that rolls back with the outer
transaction, with constraints checked (`src/storage/data_table.cpp:977-1023`). Production uses in
core: TPCH dbgen (`extension/tpch/dbgen/dbgen.cpp:491-510`) and CSV reject/error tables
(`src/execution/operator/csv_scanner/table_function/global_csv_state.cpp:176-198`).

Feasibility for `agent_memory`, if the C++ escape hatch is ever exercised:

- Viable for **append-only INSERT** semantics in the caller's transaction (exactly the ADD-only
  shape) via a small version-pinned C++ shim resolving the `TableCatalogEntry` and appending typed
  `DataChunk`s during the execute callback.
- The **public** `duckdb::Appender(Connection&)` does *not* qualify — it binds to a Connection,
  reintroducing the separate transaction. `InternalAppender` is the relevant class.
- Limits: no UPDATE/DELETE, no SQL expression evaluation/`RETURNING`; defaults/generated columns
  need explicit testing; parallel table-function execution requires single-side-effect discipline;
  C++ internals only — unreachable from the stable C ABI, so unavailable to the current Rust build.

## 6. Adjacent but different: foreign-storage transaction participation

sqlite/postgres/mysql scanners participate in DuckDB transactions by registering a custom
`Catalog` + `TransactionManager` (e.g. `duckdb-sqlite/src/sqlite_storage.cpp:31-40`,
`sqlite_transaction_manager.cpp:10-29`): DuckDB's meta-transaction drives their remote
BEGIN/COMMIT/ROLLBACK. This is coordinated lifecycle, not a shared physical transaction, and a
disproportionately heavy extension point for native `mem.*` tables — recorded to close the "but
scanners write transactionally" line of thought.

## 7. Net answers

1. **Is internal SQL from extensions common?** Yes — `Connection(*context.db)` is the established
   community pattern (flockmtl, DuckPGQ, substrait, ggsql, others).
2. **Did anyone solve same-transaction nested SQL?** No. The mechanism doesn't exist: the context
   mutex is non-recursive, and no supported API executes an arbitrary second statement inside a
   running statement on the same context.
3. **Is same-transaction writing possible at all?** Yes, append-only, without SQL, via
   `InternalAppender`/`LocalAppend` — C++ internals, version-pinned. This upgrades ADR-0008's
   escape hatch from "CALL owns its transaction, period" to "caller-transaction appends are
   achievable via a C++ shim", without changing the decision to stay on Rust/C-API.
