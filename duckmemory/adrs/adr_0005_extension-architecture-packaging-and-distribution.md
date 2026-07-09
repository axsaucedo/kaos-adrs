# ADR-0005 — Extension architecture, packaging, and distribution

**Status:** Accepted

## Context

The engineering shell around the engine: crate architecture, repository, naming, how the `fts`/`vss` dependencies behave, testing for a *stateful* extension, CI, and distribution. The settled direction from the [high-level components index](./adr_high_level_components.md) — Rust in a new dedicated repository, following the `agent_data_duckdb` skeleton inventoried in [DUCK-R2](../research/DUCK-R2-reference-architectures.md) section 2 — is recorded here with its consequences, chief among them the C-API boundary from [DUCK-R1](../research/DUCK-R1-duckdb-extension-ecosystem.md) section 4 that every other ADR's decisions have already been checked against.

## Decision

### Naming and repository

The extension, crate, and repository are all named **`agentmemory`**, hosted at [axsaucedo/agentmemory](https://github.com/axsaucedo/agentmemory). "DuckMemory" remains the design-area name inside `kaos-ai-docs`; the shipped artifact is `agentmemory.duckdb_extension`, loaded as `LOAD agentmemory`, with all SQL surface names carrying the `memory_` prefix and the `memory` schema per [ADR-0002](./adr_0002_sql-interface-and-embedded-execution-model.md). One name across extension/crate/repo is required by the community-extensions descriptor model and avoids a rename later.

### Crate architecture

The `agent_data_duckdb` skeleton is adopted wholesale: a `cdylib` crate pinned to exact `duckdb`/`libduckdb-sys` versions with the `loadable-extension` feature, `#[duckdb_entrypoint_c_api()]` entrypoint, a Makefile including `extension-ci-tools/makefiles/c_api_extensions/rust.Makefile`, and `duckdb-release.toml` pinning the DuckDB release. Source layout by responsibility:

- `src/lib.rs` — entrypoint: schema creation/migration, macro registration, function registration, retained-connection setup.
- `src/schema.rs` — DDL, versioned forward-only migrations ([ADR-0003](./adr_0003_storage-indexing-and-retrieval.md)).
- `src/macros.rs` — the SQL text of the recall/context macros, kept as reviewable constants.
- `src/lifecycle.rs` — fold/erase/purge/reindex/touch/stats over the mutex-guarded retained connection.
- `src/embed.rs` — the Layer 1 embedding client ([ADR-0004](./adr_0004_embedding-and-llm-integration-boundary.md)), feature-gated so a `--no-default-features` build is a pure Layer 0 engine with no HTTP dependency.
- `src/vtab.rs` — the generic table-function plumbing, ported from `agent_data_duckdb/src/vtab.rs` where table functions are needed (stats, fold-result).

### Dependency posture for `fts` and `vss`

Both are **soft dependencies**: the extension never fails to LOAD because they are absent. `fts` is attempted via autoload/`INSTALL`+`LOAD` when `memory_reindex()` is first called, with the [ADR-0003](./adr_0003_storage-indexing-and-retrieval.md) LIKE-fallback covering its absence; `vss` is referenced only by the documented opt-in HNSW recipe and never loaded by the engine itself. This keeps the core path dependency-free and air-gap-safe.

### Testing strategy

Three layers, reflecting that this extension is stateful where `agent_data_duckdb` was read-only:

- **Rust unit tests** for pure logic: scoring math, token estimation, migration step ordering, embedding-response parsing.
- **SQLLogicTest suites** (`make test`) as the primary harness: each `.test` file builds its own state through the public surface (LOAD → INSERT → macro/function calls → pinned assertions), including reopen tests (write, checkpoint, reopen, recall) that lock in the no-persistence-caveats property, erasure fan-out tests, fold threshold tests, and degraded-mode tests (no fts, no embedding endpoint).
- **Stub-server integration tests** for Layer 1: a minimal OpenAI-compatible embeddings stub launched by the test harness, keeping model calls deterministic.

Scratch artifacts and ad-hoc validation scripts live under the repository's `./tmp` (gitignored), never `/tmp`.

### CI and distribution

GitHub Actions builds and tests on Linux x64 and macOS arm64 per push/PR (the two development platforms), deferring the full platform matrix to the community-extensions central CI, which builds, signs, and hosts all platforms once a descriptor is submitted. **Community submission is deliberately deferred** until the surface survives real use — the extension is consumable meanwhile via `LOAD` of release-artifact binaries (unsigned local loading) and building from source. Releases are tagged `vX.Y.Z`; the schema version ([ADR-0003](./adr_0003_storage-indexing-and-retrieval.md)) increments independently and the release notes state which schema version a release writes.

## Consequences

- **Positive.** A proven build/test skeleton is reused rather than invented; the C-API choice keeps the extension portable across DuckDB releases (function-pointer ABI, not C++ ABI); feature-gating keeps the pure-storage build dependency-free; soft `fts`/`vss` dependencies mean LOAD never fails on a clean machine.
- **Negative.** The C API rules out custom index types permanently for this codebase (already absorbed by [ADR-0003](./adr_0003_storage-indexing-and-retrieval.md)); pinned DuckDB versions require an explicit update cadence (the `agent_data_duckdb` update script pattern is ported); deferring community submission means early adopters must allow unsigned extensions.
- **Follow-on.** The retained-connection pattern ([ADR-0002](./adr_0002_sql-interface-and-embedded-execution-model.md)) is the first thing P1 validates in this skeleton; the community-extensions descriptor is drafted but not submitted in P3.

## Alternatives considered

- **C++ extension (official template).** Unlocks custom index types and in-process access to internal APIs, but every ADR decision was deliberately shaped to not need them, the Rust skeleton is proven in-house, and memory-safety matters in a long-lived embedded engine; rejected.
- **Extension name `duckmemory` with repo `agentmemory`.** Mismatched names break the community-descriptor convention and confuse users; the repo name was fixed first, so the extension follows it; rejected.
- **Hard dependency on `fts`/`vss` at LOAD.** Simpler code paths, but makes LOAD fail on offline machines for features many hosts never use; rejected.
- **Community-extensions submission from the first release.** Maximum reach, but freezes the SQL surface under external users before it has survived one real integration; rejected in favour of explicit deferral.
- **Monorepo placement (inside kaos).** Rejected at the components stage: couples release cadence to KAOS and contradicts the standalone positioning.
