# ADR-0002 — SQL interface and embedded execution model

**Status:** Accepted (amended by P1 validation — see [learnings/P1-learnings.md](../learnings/P1-learnings.md))

## Context

In an embedded extension the API is SQL, so this record fixes the entire user-facing surface: how a database becomes a memory store, how hosts write and recall, what form each operation takes (native table DML, SQL macro, or Rust-registered function), configuration, transactional semantics, and — the most consequential embedded-versus-service divergence identified in [DUCK-R2](../research/DUCK-R2-reference-architectures.md) — where consolidation executes in a daemonless engine. The C-API capability boundary from [DUCK-R1](../research/DUCK-R1-duckdb-extension-ecosystem.md) section 4 constrains the options: extension entrypoints receive a full connection at LOAD time, but functions registered through the C API do not naturally execute SQL against the host's connection mid-query.

## Decision

### Initialization

`LOAD agentmemory` idempotently creates the `memory` schema and its tables (turns, digests, facts, plus a `memory.meta` version table) through the entrypoint connection, so a database becomes a memory store by loading the extension — no separate init call. Creation is `IF NOT EXISTS` and skipped gracefully on read-only databases.

### The surface: tables are the write contract, macros are the read contract, documented DML is the lifecycle contract

- **Writes are plain DML on the native tables.** `INSERT INTO memory.facts (content, embedding, user_id, ...)` with every envelope column defaulted (`id` via `uuid()`, timestamps via `now()`, `importance` 0.5) *is* the public write API. This makes writes fully transactional **with the host's own transaction** — a memory write commits or rolls back atomically with whatever else the host is doing — and costs zero API invention. The table schemas are therefore versioned public contract, not internals.
- **Reads are table macros registered at LOAD.** `memory_recall(query_embedding, query_text, k, namespace, agent_id, user_id, session_id, weights...)` is a table macro composing scope pre-filtering and the [ADR-0001](./adr_0001_memory-model-and-lifecycle-operations.md) fusion scoring in pure SQL, returning envelope columns plus `score` and per-signal component scores (explainable ranking). `memory_context(session_id, k, ...)` is a convenience macro assembling the full tiered block — live window, latest digest, top-k facts — as one result set with a `tier` column. Macros are pure reads: recall does **not** update access statistics inline (refining ADR-0001 — a SELECT surface cannot write); an explicit `memory_touch(ids)` records access when the host cares.
- **Lifecycle operations are plain, documented DML on the memory tables** *(amended: the original decision — Rust scalar functions executing multi-statement SQL through a connection retained from the entrypoint — was invalidated by P1 validation)*. Retaining the entrypoint connection pins the DatabaseInstance and its file lock past the host's close, hanging any in-process reopen of the same file; retaining the raw `duckdb_database` handle instead dangles once LOAD returns, because the handle is owned by a stack-local wrapper inside DuckDB's extension loader. An exhaustive review of the loadable C API (v1.5.4) confirms every SQL-execution path requires a connection an extension cannot soundly hold after LOAD. The shipped resolution is essentially the fallback this record anticipated: touch, purge and erase are documented DML patterns (e.g. touch as `UPDATE mem.facts ... WHERE id IN (SELECT id FROM memory_recall(...))`; erase as scoped DELETEs in one host transaction), assisted by pure-SQL macros — `memory_expired()` previews the purge set and `memory_stats()` ships as a plain table macro rather than a Rust table function. This is strictly *more* transactional than the original design: every mutation runs inside the host's own transaction instead of a detached one. Full failure analysis in [learnings/P1-learnings.md](../learnings/P1-learnings.md).

### Configuration

Engine defaults are extension settings (`SET memory_budget_tokens = 8000`, `memory_fold_target_tokens`, `memory_recency_half_life_days`, weight defaults) readable by macros and functions; every recall-time knob is also a macro parameter so per-call overrides need no session state. Embedding-related configuration is defined in [ADR-0004](./adr_0004_embedding-and-llm-integration-boundary.md).

### Consolidation execution model

Folding is **explicitly host-invoked**, with the documented host pattern being one fold check per turn boundary or write batch. *(Amended: since lifecycle cannot be a Rust function executing SQL, fold is host-orchestrated — a `memory_fold_plan(session, budget)` table macro supplies the fold selection and digest content, and documented single-transaction DML applies it; see P2 scope in [learnings/P1-learnings.md](../learnings/P1-learnings.md).)* No opportunistic piggybacking on writes or recalls in v1: piggybacked folding makes an innocent INSERT unpredictably expensive, entangles a maintenance transaction with a host transaction, and destroys determinism in tests. The fold call is cheap when under budget (one aggregate check), so calling it every turn is the intended usage.

### Concurrency

DuckDB's native model is inherited and documented rather than papered over: one writer process at a time, many readers; all memory state lives in ordinary tables so checkpointing, WAL recovery, and reopen semantics are DuckDB's own. *(Amended: no connection is retained past LOAD — the extension holds no state at all after the entrypoint returns, so there is nothing extension-side to serialize; lifecycle DML inherits the host connection's ordinary transaction semantics.)*

## Consequences

- **Positive.** The smallest possible invented surface (pure-SQL macros plus documented tables, zero Rust-registered functions in P1); *all* writes — hot-path and lifecycle alike — are transactional with the host's own transaction; everything is plain SQL and testable with SQLLogicTest; explainable scores; per-call configurability without session state.
- **Negative.** Table-schema-as-contract means schema changes are API changes (mitigated by the `memory.meta` versioning in [ADR-0003](./adr_0003_storage-indexing-and-retrieval.md)); lifecycle operations are multi-statement patterns hosts must copy from documentation rather than one-call functions; hosts must remember to run the fold pattern (documented, and `memory_stats` exposes over-budget sessions so neglect is observable).
- **Follow-on.** ~~P1 must validate retained-connection DML under concurrent host queries before the lifecycle surface hardens~~ *(done: validation failed in both implementations; lifecycle is DML as amended above, and an in-process reopen regression test guards against any future handle retention)*; the touch/access-stats pattern needs a benchmark before recommending it as default-on.

## Alternatives considered

- **Everything as Rust functions (memory_write(...), no public tables).** A conventional API façade, but write functions through a retained connection would put *hot-path* writes in a separate transaction (losing host atomicity), and the C API offers no clean in-statement DML; the table contract is both simpler and strictly more transactional; rejected.
- **Everything as SQL macros.** Macros cannot perform DML or multi-statement operations, so fold/erase/purge are inexpressible; rejected as a complete answer, adopted for the read path.
- **Opportunistic fold on write/recall.** Removes the host's obligation to call fold, but makes write latency unpredictable and couples maintenance to host transactions; rejected for v1, revisitable once fold cost is measured.
- **Companion client library owning lifecycle.** Moves the daemonless-consolidation problem to a helper package per language, contradicting the engine-in-the-database goal and multiplying maintenance; rejected.
- **Explicit memory_init() instead of LOAD-time creation.** More ceremonial control, but adds a failure mode (querying before init) for no benefit given creation is idempotent and cheap; rejected.
