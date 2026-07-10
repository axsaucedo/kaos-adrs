# ADR-0008 — C++ execution-model spike: in-engine orchestration via CALL, and staying on Rust/C-API

**Status:** Accepted (decision: retain Rust/C-API; C++ recorded as a validated escape hatch with revisit criteria).

## Context

[ADR-0002](./adr_0002_sql-interface-and-embedded-execution-model.md) (as amended by P1) established
the hard C-API constraint: an extension built on DuckDB's stable C ABI has no sound way to execute
SQL after LOAD, which is why lifecycle, fold-apply, and reconcile-apply are documented host DML and
why [ADR-0006](./adr_0006_consolidation-cadence-observability-and-mem0-parity-surface.md) D4 places
the single-call `add()` experience in the host SDK rather than the engine. The owner asked the
natural follow-up: if the extension were C++ (full internal API, flockmtl-style), could
`CALL memory_add('user: call me Alex')` run the whole pipeline — insert turn, inspect window, fold,
extract, embed, store — inside the engine? Per the owner's directive, an empirical spike was run
before recording a decision.

**Spike setup** (evidence in `agentmemory/tmp/cpp-spike/`, `FINDINGS.md` + `test-results.log`;
nothing committed or pushed): `duckdb/extension-template` pinned exactly to DuckDB v1.5.4
(`08e34c447b`), macOS arm64, a minimal table function registered three ways —
`memory_add_spike` (new `Connection(*context.db)`, SQL at bind), `memory_add_spike_execute`
(same route, SQL at execution), `memory_add_spike_context` (recursive `context.Query(...)`).

## Findings

- **A. Execution route.** The flockmtl-style route — construct a fresh `duckdb::Connection` on the
  calling context's `DatabaseInstance` and run SQL through it — works, at both bind time and
  execution time. Reusing the calling `ClientContext` recursively compiled but **hung until killed**:
  there is no same-context nested-SQL route in this shape on v1.5.4.
- **B. Transaction semantics.** The working route is a **second, independent connection**. Verified:
  a caller `BEGIN … CALL … ROLLBACK` does not undo the inner write (the inner row survived the
  rollback), and the inner connection cannot see the caller's uncommitted writes (a caller-inserted
  uncommitted row was invisible to the CALL). Each inner `Query` autocommits unless the extension
  opens its own transaction.
- **C. Concurrency.** Caller-held transaction inserting into the same table the CALL appends to:
  no lock error or conflict for the ADD-only append shape. (No claim about conflicting updates.)
- **D. Multi-statement flow.** insert → check → conditional second insert → return, branching on
  intermediate results, works in one top-level `CALL` — the exact mechanical shape of
  turn-insert + window-check + conditional fold/extract.
- **E. Errors.** An inner SQL error surfaces cleanly as the CALL's error (no crash), but earlier
  inner statements **remain committed** — atomicity requires the extension to explicitly
  `BEGIN`/`COMMIT`/`ROLLBACK` on its inner connection.
- **F. Distribution cost.** Clean debug build 3m04s (8 jobs, M1 Max, no ccache/ninja); incremental
  ~19s; C++ extensions compile against DuckDB's version-specific internal C++ ABI and must be
  rebuilt per exact DuckDB version and platform — versus the C-API's build-once stable ABI that
  `agent_memory` ships on today.

**Net:** `CALL memory_add(...)` is mechanically viable in C++, but only as a **self-contained
transaction owner** — it cannot participate in the caller's transaction under either tested route.
The honest API contract would be "CALL owns its transaction; do not wrap it with related
uncommitted caller DML expecting shared visibility or rollback."

## Options and trade-offs

- **Option 1 — migrate to C++.** Gains the in-engine orchestration CALL (strongest possible SQL
  ergonomics, no SDK needed for single-call add). Costs: per-version/per-platform rebuild and
  publish, internal-API churn exposure, LLM/HTTP calls inside query execution as engine surface,
  and the transaction caveat above — the CALL is *not* transparently composable, so the ergonomic
  win is smaller than it first appears.
- **Option 2 — stay on Rust/C-API; SDK is the single-call surface (status quo per ADR-0006 D4,
  ADR-0007).** Build-once distribution, the shipped and green v0.2 surface, and the SDK `add()`
  delivers the same one-call experience host-side — where a multi-statement pipeline *can* be one
  real caller transaction, which is strictly better transactional composition than the C++ CALL.
- **Option 3 — hybrid (C++ companion extension exposing only `CALL` wrappers over the same schema).**
  Deferred without evidence of demand: doubles the release matrix for ergonomics the SDK already
  provides.

## Decision

**Option 2 — remain on Rust/C-API.** The spike converts the C++ question from an unknown into a
recorded, evidence-backed escape hatch: the mechanics are proven (route, flow, error behavior,
build cost quantified), so a future migration is de-risked, but the trade is now clearly a
product/distribution decision rather than a capability gap — and the decisive technical point is
that the C++ CALL cannot join the caller's transaction, while the SDK pipeline can *be* one.

**Revisit criteria** (any of):
1. Real hosts demonstrably reject the SDK/3-call loop and demand a pure-SQL single-call `add()`
   (e.g. non-Python hosts, BI tools, `duckdb` CLI-only users) as an adoption blocker.
2. DuckDB ships a stable C-API surface for nested query execution (which would give the CALL
   without leaving build-once distribution — the ideal outcome).
3. The distribution calculus changes (e.g. community-extensions CI absorbs the per-version rebuild
   cost for C++ extensions).

## Consequences

- **Positive.** The v0.2 architecture (engine SQL truth + SDK front door) is confirmed with
  empirical evidence rather than assumption; the transaction-semantics finding is recorded before
  anyone designs against a wrong mental model of a C++ CALL; the spike artifacts pin exact
  revisions and observed outputs for future re-validation.
- **Negative.** The pure-SQL user still has no single-statement `add()` with fold orchestration
  (the one-statement extract→embed→insert from ADR-0006 Option A remains the ceiling); the answer
  "use the SDK" must be documented prominently to prevent repeated re-litigation.
- **Follow-on.** Spike directory stays in gitignored `tmp/` (evidence, not product). Next planned
  work after the review pause: SDK package (`agent_memory` Python client per ADR-0007), MERGE
  spike (ADR-0006 Option B), structured-digest design at Layer-2 summarizer time.
