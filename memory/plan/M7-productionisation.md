# Productionisation, hardening, and documentation — implementation plan

**Branch (KAOS)**: `feat/memory-productionisation`, stacked off the later of `feat/memory-multitenancy` (M5) and `feat/memory-cli-install` (M6); PR targets that tip.
**Tracking issue**: TBD (do not reference in commits/branches/PR text).

> **Stacking-base note (read first).** Per [`proposed-split.md`](./proposed-split.md): `{M5, M6} → M7`. M7 is the final phase: it hardens the service for production, finalises the operational behaviour, promotes the M0 harnesses into committed e2e, and brings the docs up to the implementation. It stacks on whichever of M5/M6 lands last. **Before starting, re-read all prior `impl/learnings/` entries** (M0–M6) and fold every recorded delta and deferred decision into the tasks below.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message; **no** phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Run the touched suites locally; push the PR and confirm CI green including the new e2e. Alpha: breaking changes OK.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all phases) posted as a PR comment (not committed). Copy this plan to `plan/M7-productionisation.md` and write `impl/progress/M7-*.md` + `impl/learnings/M7-*.md`.

## Problem statement

Complete the operational correctness story and bring documentation up to the implementation. Harden `external` mode for high availability (stateless `replicas: 2+`, disruption budget, readiness/liveness, Mem0 change-history log disabled/ignored); finalise the `failureMode: soft | strict` behaviour end to end; add the **session-end flush (idle-TTL sweeper)** that consolidates idle sessions' trailing sub-threshold windows and the **native async Postgres data-plane path** deferred from M2; add metrics/health endpoints and the memory-operation metrics; **evaluate and record a decision** on the deferred durable at-least-once extraction queue, building it only if write durability proves a hard requirement; promote the most valuable M0 harnesses into committed e2e tests runnable in CI (KIND); and write the user- and operator-facing documentation and update the repo instructions.

## Scope calibration (trimmed, with tradeoffs)

The original scope was assessed against what is already shipped and the alpha, keep-it-simple posture, to avoid synthetic work. Already in place: `kaos-memory` exposes `/healthz` + `/readyz`; the operator sets `Replicas` (default 1, overridable) plus liveness (`/healthz`) and readiness (`/readyz`) probes; `failure_mode` is implemented in the runtime client and threaded through the server with tests; memory e2e shards are committed and green; `stores.py` is still synchronous (`sqlite3` / `psycopg`).

Decisions:

- **HA hardening — DO (minimal).** External mode defaults to `replicas: 2` and gains a `PodDisruptionBudget`; probes already exist. Small, high-signal, makes the stateless-over-shared-Postgres claim real. Tradeoff: PDB is inert on single-node KIND but cheap to carry.
- **`failureMode` — DO (verify-only).** Add focused coverage that soft degrades and strict surfaces across recall and write plus the store-down condition; no new machinery, since the behaviour is already implemented. Tradeoff: risk of re-verifying what exists — kept to a single decisive test.
- **Durable-queue — DECISION ONLY.** Record keeping in-process fire-and-forget with an explicit trigger condition; do not build the Postgres SKIP-LOCKED queue. Tradeoff: no at-least-once durability guarantee, which alpha does not require.
- **e2e — DO (gap-check only).** Confirm existing memory e2e covers scope-correct recall and restart durability; add at most one missing case. Tradeoff: avoids wholesale promotion and extra CI minutes.
- **Documentation — DO.** The highest-value remaining work: the memory model, `MemoryStore`/Agent surfaces, install flow, operations, and updated repo instructions.
- **Prometheus `/metrics` — DEFER.** OpenTelemetry spans already provide operation observability; a scrape endpoint is a follow-up. Trigger: adopting the sync-service metrics parity or a Prometheus-based SLO need.
- **Idle-TTL sweeper + native async `stores.py` — DEFER (strong).** Highest complexity and risk; async is gated on an upstream Mem0 threading issue and the sweeper handles stranded sub-threshold tails (completeness, not correctness). Trigger: measured extraction loss or a throughput ceiling on the sync request/database path.

The numbered TODOs below reflect this trimmed scope.

## Current-state grounding (researched)

- HA and degradation are fixed by [adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md): `external` mode is stateless over shared Postgres (`replicas: 2+`); `local` mode pins to a single replica; Mem0's SQLite change-history log is disabled/ignored so it does not block scaling; `failureMode: soft|strict` selects fail-soft (short-term-only on recall failure, background retry on write failure) versus strict.
- The durable queue is explicitly deferred: in-process fire-and-forget is the v1 execution model; a durable at-least-once queue (Postgres SKIP-LOCKED job table) is a follow-up to adopt only when write durability becomes a hard requirement ([adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md)). M7 makes the explicit decision.
- Observability rides existing OpenTelemetry; the operation spans were added in M2/M3/M5. Metrics endpoints are new in M7 (mirror the sync-service productionisation precedent in the security work: `prometheus_client`, `/metrics`, readiness/liveness).
- e2e helpers and patterns: `operator/tests/e2e/conftest.py`, `test_modelapi_e2e.py`; the memory e2e files added in M4/M5 are the base to extend.
- Docs: VitePress under `docs/`; repo instructions in `.github/copilot-instructions.md` and `.github/instructions/*` (python/operator/e2e/docs). The memory model and surfaces must be documented and the instructions updated succinctly.

## Design plan (how it fits)

- **HA hardening (`external`).** Confirm/enforce statelessness, set `replicas: 2+` defaults for `external`, add a `PodDisruptionBudget` and readiness/liveness probes on the service Deployment (operator constructs them), and verify a replica restart loses no memory (durable state in Postgres). Confirm Mem0's change-history log is disabled.
- **`failureMode` end to end.** Verify soft (degrade + background retry) and strict (surface the error) across recall and write, from the Agent block through the runtime to the service, including the store-down → Agent-not-Ready-but-serving operator condition.
- **Metrics + health.** Add `prometheus_client` to the service: `/metrics` exposing memory-operation counters/histograms (recall/write/forget counts, extraction queue depth and failures, degraded-recall count, last-write-success gauge) and confirm `/readyz`/`/healthz`; operator exposes the metrics port and probes.
- **Durable-queue decision.** Measure in-process fire-and-forget under autonomous-loop event volume; record a decision in `impl/learnings/M7`: keep fire-and-forget (default) or build the Postgres SKIP-LOCKED durable queue. Build it only if the evidence shows unacceptable extraction loss; otherwise document the trigger condition for a future phase.
- **Session-end flush (idle-TTL sweeper).** Add the mechanism that detects session end without an explicit signal: track `last_write_at` per session, run a periodic sweep that finds sessions idle beyond `idle_ttl` with an un-folded window, and — under the same per-scope Postgres advisory lock used for folding — fold the remaining window into the medium-term digest, feed the evicted batch to long-term extraction, then clear the window. Replica-safe by reusing the fold lock. Reuses the M2 fold + cascade machinery, so the new surface is a `last_write_at` update on write, a sweep query, and a bounded periodic task. Optionally expose an explicit `/v1/session/close` fast path. It is deferred here (not built in M2) because it is a completeness improvement for stranded sub-threshold session tails, not a correctness blocker.
- **Native async Postgres data-plane path.** M2 ships async FastAPI handlers plus a bounded `run_in_executor` boundary isolating the sync Mem0 client, keeping the service non-blocking with the short-term DB path called synchronously behind the executor. M7 takes up the deferred throughput optimisation: convert the dual SQLite/psycopg backend in `stores.py` to async drivers (asyncpg + an async local path) so the cheap request/database path is natively async and only Mem0 sits behind the executor. The conversion cost is concrete — `asyncpg`'s numbered `$1` placeholders need a third placeholder branch, its lack of a DB-API cursor forces ~12 call sites onto `fetch`/`fetchrow` plus a connection pool and `asyncio.Lock`, ~15 `ShortTermStore` methods become `async def`, the `BackgroundRunner` scheduler seam (sync callable) must become event-loop-aware, and ~7 test files move to `pytest-asyncio`; the full breakdown is in [Mem0 async boundary and internals](../impl/learnings/mem0-async-boundary-and-internals.md). Because Mem0 stays threaded until [mem0ai/mem0#6070](https://github.com/mem0ai/mem0/issues/6070) lands, this is a throughput optimisation to gate on measured need rather than build speculatively.
- **e2e promotion.** Promote the decisive M0 harnesses (scope-correct recall on both providers, model routing through a `ModelAPI`, short-term tier summarization, deploy-and-restart durability) into committed `operator/tests/e2e/test_memory_*_e2e.py`, runnable in CI on KIND.
- **Docs.** Add a memory section to `docs/` (the memory model and tiers, the `MemoryStore` and Agent surfaces, install flow, scope/multi-tenancy, operations and degradation), and update `.github/copilot-instructions.md` + the path-specific instructions to describe the memory service, the `memory-service/` package, and the build/test commands. Keep docs succinct and functional; single-line paragraphs.

## Numbered TODOs

1. **HA hardening for `external` mode (minimal).** Operator: default `external`-mode stores to `replicas: 2` (keep `local` single-replica) and add a `PodDisruptionBudget` for the memory-service Deployment; liveness/readiness probes already exist. **Validate**: operator envtest — an `external` store gets 2 replicas + a PDB, a `local` store stays single-replica with no PDB; `cd operator && make test-unit`.

2. **`failureMode` verification (verify-only).** Add decisive coverage that `soft` degrades (empty recall, background-retry write) and `strict` surfaces errors across recall and write, plus the store-down → Agent not-Ready-but-serving condition. No new machinery — the behaviour is already implemented. **Validate**: touched suites `pytest` (`pydantic-ai-server`, `kaos-memory`) and `operator` `make test-unit` as applicable.

3. **Durable-queue decision (record only).** Document the decision to keep in-process fire-and-forget extraction, with the explicit trigger condition for adopting a Postgres SKIP-LOCKED durable queue in a future phase. Do not build the queue. **Validate**: the decision and trigger are written to `impl/learnings/M7-*.md`.

4. **e2e gap-check.** Confirm the committed memory e2e already covers scope-correct recall and deploy-and-restart durability; add at most one missing case if a genuine gap exists. No wholesale promotion. **Validate**: existing memory e2e shard green on CI; any added case green, suppress to `./tmp/null`.

5. **Documentation + instructions.** Add the memory docs section to `docs/` (the memory model and tiers, the `MemoryStore` and Agent surfaces, install flow, scope/multi-tenancy, operations and degradation); update `.github/copilot-instructions.md` and the path-specific instructions for the `kaos-memory/` package, the `MemoryStore`/Agent surfaces, and the build/test commands. Keep docs succinct and functional; single-line paragraphs. **Validate**: `cd docs && npm run build` succeeds; instructions are accurate. Write `impl/progress/M7-*.md` + `impl/learnings/M7-*.md`, copy this plan, push `feat/memory-productionisation`, open the stacked PR, confirm CI green, write the gitignored `REPORT.md` (whole memory effort) and post it as a PR comment.

**Deferred (documented triggers, not built here):** Prometheus `/metrics` endpoint; idle-TTL session-end sweeper; native async `stores.py` (asyncpg) data-plane path. See Scope calibration above and Out of scope below.

## Validation per task

- Per-TODO: run the touched suites (`memory-service`/`pydantic-ai-server` `pytest` + `make lint`, `operator` `make test-unit`, `docs` `npm run build`). The promoted e2e runs in CI on KIND via `workflow_dispatch --ref feat/memory-productionisation`.
- Documentation changes are built (`npm run build`) but not unit-tested beyond that.

## Commit / PR strategy

- `feat/memory-productionisation` stacked on the later of M5/M6; one comprehensive commit per TODO; Copilot co-author trailer; CI green including the new e2e. The final `REPORT.md` (gitignored) summarises the entire memory effort and is posted as a PR comment.

## Out of scope (genuinely deferred)

Deferred with explicit trigger conditions (documented, not built here): the Prometheus `/metrics` endpoint (trigger: sync-service metrics parity or a Prometheus-based SLO need — OpenTelemetry spans already cover operation observability); the idle-TTL session-end sweeper (trigger: measured stranded sub-threshold session tails needing consolidation); the native async `stores.py` (asyncpg) data-plane path (trigger: a measured throughput ceiling on the sync request/database path, and after the upstream Mem0 threading issue is resolved); the durable at-least-once queue if the recorded decision does not justify it (documented trigger for a future phase); temporal/procedural memory tiers behind a future Graphiti-class engine; dynamic cross-cutting agent groups (`MemoryGroup`); per-tenant rate/fair-share quotas, logical export/import, application-level encryption, and proof-of-deletion ledgers ([adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md), [adr_0005](../adrs/adr_0005_multi-tenancy-agent-grouping-and-governance.md)).
