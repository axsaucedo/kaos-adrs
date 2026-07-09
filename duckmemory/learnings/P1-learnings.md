# P1 learnings — extension scaffold and core memory store

**Source:** [axsaucedo/agentmemory PR #1](https://github.com/axsaucedo/agentmemory/pull/1). **Status:** P1 complete; findings below gate P2 planning.

## L1 — The retained-connection lifecycle pattern is unsound on the C API (ADR-0002 amendment)

P1's first job was to validate the riskiest seam, and the validation failed in both possible implementations:

1. **Retaining the entrypoint connection** (or any clone of it) pins the DatabaseInstance — and its file lock — past the host's close. A subsequent *in-process* reopen of the same database file hangs forever at 100% CPU (bisected to a five-line repro: connect file DB → LOAD → close → reconnect). Fresh-process reopen works, which is why this class of bug survives casual testing.
2. **Retaining the raw `duckdb_database` handle** instead (to `duckdb_connect` per call) dangles: the handle points into a stack-local `DatabaseWrapper` inside DuckDB's extension loader (`extension_load.cpp`, `DuckDBExtensionLoadState`), destroyed when LOAD returns. Later `duckdb_connect` on it fails with a generic connect error.

Exhaustive check of the loadable C API (v1.5.4) confirms every SQL-execution path requires a `duckdb_connection`, and client contexts reachable from function callbacks (`duckdb_scalar_function_get_client_context` etc.) offer no bridge to one. **An extension cannot soundly execute SQL after LOAD returns.**

**Resolution shipped in P1:** lifecycle operations are plain DML documented in `examples/lifecycle.sql` (touch composes as `UPDATE ... WHERE id IN (SELECT id FROM memory_recall(...))`; erase is three DELETEs in one host transaction), with a `memory_expired()` macro keeping the purge preview ergonomic. This is close to ADR-0002's recorded fallback and is strictly *more* transactional — every mutation runs inside the host's own transaction rather than a detached one. ADR-0002's lifecycle-contract section is amended accordingly.

**P2 consequence (largest):** `memory_fold(session)` cannot be a Rust function executing SQL either. Fold must be either (a) a documented multi-statement SQL script/host pattern, or (b) pure-SQL-composable pieces (macros providing the fold *selection* and digest *content*, DML performing the mutation). LLM-based summarisation was already host-side per ADR-0004; this pushes the whole fold orchestration host-side.

## L2 — Deviations forced by DuckDB SQL semantics (all shipped, all cosmetic)

- **Schema is `mem`, not `memory`:** in-memory DuckDB databases have a *catalog* named `memory`, making `CREATE SCHEMA memory` fail with "Ambiguous reference to catalog or schema".
- **Macro scope parameters are `in_namespace`/`for_agent`/`for_user`/`for_session`:** DuckDB resolves unqualified identifiers in a macro body to columns before macro parameters, so a parameter named `namespace` can never be compared against the `namespace` column.
- **`at` is a reserved keyword** in DuckDB 1.5; `memory_context` exposes the timestamp column as `ts`.
- **`memory_stats` is a pure SQL macro,** not a Rust table function — no state needed, one less Rust surface.

## L3 — Tooling gotchas (cost real time; avoid repeating)

- **`extension_version.txt` corruption:** the configure step writes `git describe` output to a file only if missing; in a repo with no commits/tags it wrote a git *error string*, silently corrupting the extension metadata footer ("Unknown ABI type" at LOAD). Tag early; delete the file and re-run configure after tagging.
- **sqllogictest `restart` is unusable** with duckdb-sqllogictest-python on DuckDB 1.5: it replays all settings including non-replayable ones (`__delta_only_variant_encoding_enabled`, ...). The in-process reopen regression therefore lives in a plain Python test (`test/reopen_test.py`) wired into `make test`, with a watchdog turning a hang into a loud failure.
- **NULL arguments short-circuit C-API scalar functions** (function not invoked, row yields NULL) — relevant if P2/P3 ever register scalar functions taking optional arguments; use sentinel values.
- Rust `FlatVector` writes need a two-pass pattern (all `set_null` before `as_mut_slice`) to satisfy the borrow checker — moot for now with no scalar functions, but recorded.

## L4 — Scoring and performance baseline

- The whole fusion computation lives in SQL macros, so scoring correctness is covered by sqllogictests, not Rust unit tests; Rust's testable surface in P1 is schema creation only.
- Brute-force recall (release build, osx_arm64, 384-dim): 10k facts ≈ 51 ms hybrid / 32 ms scoped p50; 100k ≈ 307 ms / 126 ms. Usable for P1; confirms P2's HNSW (`vss`) and BM25 (`fts`) work should be scheduled as planned, with scoped recall already 2.4× cheaper via envelope pre-filtering.

## P2 scope reassessment (milestone gate)

P2 as planned, with these deltas:

1. **Replace "memory_fold as Rust function" with a host-orchestrated fold**: `memory_fold_plan(session, budget)` table macro (which turns to fold, current digest version, verbatim-fallback digest content) + documented single-transaction DML to apply it. Idempotency and threshold tests unchanged in spirit.
2. **`memory_reindex()` cannot be a Rust function either** — index maintenance (fts PRAGMA, staleness stamp) becomes a documented statement pair or macro-assisted host call; staleness tracking in `mem.meta` stays.
3. **Settings via DuckDB settings API are Rust-side and LOAD-scoped only** — budget/target knobs move to `mem.meta` key-values (readable by macros) instead of custom settings.
4. Keyword LIKE fallback must stay behaviourally consistent when fts is present but stale — unchanged.
5. Keep the reopen regression green in every P2 PR; it is the canary for any future temptation to retain handles.
