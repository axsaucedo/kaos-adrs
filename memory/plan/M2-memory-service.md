# Central memory service — implementation plan

**Branch (KAOS)**: `feat/memory-service`, stacked off `feat/memory-atomic-stores` (M1); PR targets `feat/memory-atomic-stores`.
**Tracking issue**: TBD (do not reference in commits/branches/PR text).

> **Stacking-base note (read first).** Per [`proposed-split.md`](./proposed-split.md): `M1 → M2 → {M3, M4}`. M2 composes the M1 stores into a deployable central service. It stacks directly on `feat/memory-atomic-stores`. M3 (runtime client) and M4 (operator) are **siblings** off M2; whichever lands first, the other rebases onto its tip. **Before starting, re-read [`../impl/learnings/M1-atomic-stores.md`](../impl/learnings/M1-atomic-stores.md)** and fold its deltas in.

> **As-built note (read second).** This plan captures the original M2 shape. During execution M2 was reconciled with the finalized short-term / medium-term design: the write path became a model-2 cascade (extraction rides eviction, not per turn), writes accept a batch of turns persisted in a single short-term append, the recall response splits the verbatim window (`short_term`) from the rolling digest (`medium_term`), the request path became async over a bounded executor, the compaction-mark / concurrency knobs were surfaced in settings, and the write/forget failure mode became layered (explicit request value, else store-configured `default_failure_mode`, else `soft`). The authoritative as-built record is [`../impl/progress/M2-memory-service.md`](../impl/progress/M2-memory-service.md) and [`../impl/learnings/M2-memory-service.md`](../impl/learnings/M2-memory-service.md); where this plan's TODO wording (per-turn `/v1/write`, `working` recall field) differs, the progress/learnings docs supersede it.

## Recalibration from M1 (fold into the TODOs below)

The M1 stores landed exactly as planned; the following concrete deltas from [`../impl/learnings/M1-atomic-stores.md`](../impl/learnings/M1-atomic-stores.md) refine M2's implementation without changing its scope:

- **Stack: FastAPI + uvicorn** (the runtime's stack — `pydantic-ai-server` depends on `fastapi`/`uvicorn`), not bare Starlette. Use a FastAPI app and `opentelemetry-instrumentation-fastapi` for span context, matching `pais/server.py`.
- **Lazy model binding for readiness.** `LongTermStore`/`ModelClient` dial the endpoint on first use, so `/readyz` must reflect **store reachability** (short-term tier DB ping + Mem0 vector-store reachability), not model reachability — a not-yet-reachable `ModelAPI` must not fail readiness.
- **Recall pass-through.** `LongTermStore.recall` already returns Mem0's native `{"memory": str, score, id, metadata}` dicts; `/v1/recall` passes these through unmodified so the runtime sees scores/metadata for later relevance work. Empty recall is a **valid, common** result (pgvector's 0.1 threshold is strict; Chroma is lenient) — the assembled block must render cleanly when long-term recall is empty, falling back to short-term-only.
- **Dims-per-mode.** Keep `embedding_model_dims` out of the local-mode Mem0 config (Chroma rejects it); only set it for `external`. The M1 `StorageConfig.resolved()` already encodes this — reuse it, do not re-derive the Mem0 config in the service.
- **Reuse the M1 offline test harness.** `tests/_fakes.py::DeterministicEmbedder` + `tests/conftest.py` (`offline_models`, `pgvector_dsn`) let the service suite run without network/API keys; the pgvector path stays opt-in behind the `pgvector` marker, and CI already stands up the `pgvector/pgvector:pg16` service container.
- **`shared` scope carries the reserved owner id** end to end; the service must not treat any scope as owner-less when calling the stores.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message; **no** phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Run unit/integration tests locally; push the PR and confirm CI green. Alpha: breaking changes OK. KIND available for a local single-process run.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all prior phases + this work) posted as a PR comment (not committed). Copy this plan to `plan/M2-memory-service.md` and write `impl/progress/M2-*.md` + `impl/learnings/M2-*.md`.

## Problem statement

Build the **central memory service**: a thin KAOS-owned Python service that imports the M1 stores and exposes the [adr_0003](../adrs/adr_0003_memory-interface-and-runtime-data-plane.md) memory contract over HTTP, so agents call one shared service rather than embedding the engine ([adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md)). It serves **synchronous recall** on the hot path and runs **write/extract, consolidate, and forget asynchronously** as in-process fire-and-forget background tasks bounded by a concurrency setting (no durable queue in this version). It owns the short-term tier and executes the rolling summary server-side using the `summarization` model; injects scope server-side from the request context (never trusting the caller — the data shape lands here, the non-optional enforcement policy is M5); honours the single `storage.type: local | external` switch with idempotent schema setup on boot; degrades fail-soft (recall failure → short-term-memory-only, write failure → background retry); and emits OpenTelemetry spans at the operation boundary. It is packaged as a container image built by the existing pipeline.

## Current-state grounding (researched)

- The two stores (`kaos_memory.longterm.LongTermStore`, `kaos_memory.working.ShortTermStore`) and the config/scope/model modules exist from M1 in the `memory-service/` package; M2 adds the HTTP surface and background runner in the same package.
- The deployment contract is fixed by [adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md): `local` = single container (Chroma + SQLite on one PVC), single replica; `external` = stateless service over shared Postgres, `replicas: 2+`. Background execution is in-process fire-and-forget bounded by `extraction.concurrency`. Degradation is fail-soft with a per-request `failureMode`. Mem0's SQLite change-history log is disabled/ignored so it does not block horizontal scaling.
- The operation split is fixed by [adr_0003](../adrs/adr_0003_memory-interface-and-runtime-data-plane.md): recall synchronous; write/consolidate/forget asynchronous; recall presentation is a structured block by default (the service returns assembled context; the runtime injects it); scope is server-side-injected and fails closed when unresolved.
- The runtime will call this service (M3); the operator will deploy it (M4). M2 is exercised by a local client and tests, with config supplied directly (no CRD yet).

## Design plan (how it fits)

Add to the `memory-service/` package an ASGI app (FastAPI/Starlette, matching the runtime's stack) `kaos_memory/service.py` with an entrypoint `kaos_memory/__main__.py`, plus a `Dockerfile` and a Helm-free container build wired into the existing image pipeline (image name `axsauze/kaos-memory-service`, added to `defaultImages` in M4). Surface:

> **Note (superseded layout).** The HTTP layer has since been consolidated into a single `kaos_memory/app.py` (schemas, routes, presentation, background runner, `main()`), with `settings.py` merged into `config.py` and the entrypoint at `python -m kaos_memory.app` — see [`refactor-store-restructure-and-summarisation.md`](./refactor-store-restructure-and-summarisation.md). The background runner is injected into the short-term store as its summarisation scheduler.


- `POST /v1/recall` — synchronous: body carries the request scope context + query + presentation knobs; returns assembled recalled context (long-term facts block + short-term tier recent turns / rolling summary). Fail-soft: on long-term error, return short-term-only context and mark the response degraded.
- `POST /v1/write` — accepts a turn/events; appends to the short-term tier synchronously (cheap, durable) and **schedules** long-term extraction as a background task; returns immediately. Honours `failureMode: soft|strict`.
- `POST /v1/working/*` — short-term tier ops the runtime needs (append, recent, summarize trigger) if not folded into recall/write.
- `POST /v1/forget` — scope-targeted delete (the synchronous fan-out semantics are completed in M5; M2 ships the endpoint + short-term table + Mem0 delete).
- `GET /healthz`, `GET /readyz` — process up / stores reachable (readiness gates the operator's store-Ready condition in M4).

A `BackgroundRunner` owns an `asyncio` task set bounded by a semaphore of size `extraction.concurrency`; scheduled extractions run off the response path, with bounded retry on failure and a degraded span on give-up. The rolling summary runs server-side using the `summarization` model. Scope is read from the request context object (M2 trusts a `scope` block in the request as the server-injected value the runtime will populate; M5 makes resolution non-optional and fail-closed and removes any client-trust path). OpenTelemetry spans (`kaos.memory.recall|write|consolidate|forget`) wrap each operation with engine sub-spans inside the store calls, following the existing `tracer.start_as_current_span("kaos.…")` convention (`pais/a2a.py`, `pais/server.py`).

## Numbered TODOs

1. **ASGI app + health.** Add `service.py` (ASGI app, dependency-injected `LongTermStore`+`ShortTermStore` from config) and `__main__.py` (load config from env/file, construct stores, run uvicorn). Implement `/healthz` and `/readyz` (readiness pings both stores). **Validate**: unit test with an ASGI test client — health 200, readiness reflects a stubbed store failure; `cd memory-service && pytest tests/test_service_health.py -v && make lint`.

2. **Synchronous recall endpoint.** `POST /v1/recall`: parse scope + query + presentation, call `LongTermStore.recall` and `ShortTermStore.recent`, assemble the structured block + short-term context per [adr_0003](../adrs/adr_0003_memory-interface-and-runtime-data-plane.md), and return it. Fail-soft: long-term error returns short-term-only with a `degraded` flag and a degraded span. **Validate**: tests — scoped recall returns expected facts, long-term failure degrades to short-term-only, response shape matches the presentation contract; `pytest tests/test_recall.py -v`.

3. **Write endpoint + working append.** `POST /v1/write`: synchronously append the turn to the short-term tier (durable), then schedule background extraction; return immediately. Respect `failureMode`. **Validate**: tests — write returns before extraction completes, the working row is present synchronously, `strict` surfaces a working-append failure while `soft` swallows a long-term schedule failure; `pytest tests/test_write.py -v`.

4. **Background runner (fire-and-forget, bounded).** Implement `BackgroundRunner` with an `asyncio` semaphore of `extraction.concurrency`, bounded retry, and a degraded span on exhaustion; wire `write` to schedule extraction through it; ensure graceful drain on shutdown. **Validate**: tests — concurrency cap respected, a failing extraction retries then gives up without crashing the service, pending tasks drain on shutdown; `pytest tests/test_background.py -v`.

5. **Rolling summary + forget endpoint.** Execute the short-term tier rolling summary server-side using the `summarization` model when the token budget is exceeded (per-request budget/toggle supplied as policy). Add `POST /v1/forget` performing the short-term table scope delete + `LongTermStore.delete(scope)` + rolling-summary clear (the synchronous cross-tier fan-out guarantees are completed in M5). **Validate**: tests — overflow summarizes server-side, forget removes scoped items from both tiers and clears the summary; `pytest tests/test_summary_forget.py -v`.

6. **Storage-mode wiring + idempotent schema + OTel.** Honour `storage.type: local|external` end to end (Chroma+SQLite single-process vs pgvector+Postgres), run idempotent `CREATE TABLE IF NOT EXISTS` for the short-term table on boot and let Mem0 self-create its vector schema, disable/ignore Mem0's SQLite change-history log, and add the `kaos.memory.*` spans at the operation boundary. **Validate**: integration test that boots the app in `local` mode and runs write→recall→forget end to end; a pgvector-marked variant in `external` mode against a local Postgres; spans assert via an in-memory OTel exporter; `pytest tests/ -v`.

7. **Container image + local-run + PR.** Add a `Dockerfile` for the service and wire it into the image-build workflow (image `axsauze/kaos-memory-service`; the `defaultImages` entry + chart wiring is M4). Provide a `make run-local` and document a one-command local run in both modes. **Validate**: `docker build` succeeds; the container serves `/readyz` and a write/recall in `local` mode (capture to `./tmp/null`); `make lint && make test`. Write `impl/progress/M2-*.md` + `impl/learnings/M2-*.md`, copy this plan, push `feat/memory-service`, open the stacked PR into `feat/memory-atomic-stores`, confirm CI green, write the gitignored `REPORT.md` (M0–M2) and post it as a PR comment.

## Validation per task

- Per-TODO: `cd memory-service && python -m pytest tests/ -v && make lint`; the `external`-mode tests use a local pgvector/Postgres container (documented in the README).
- The service unit/integration suite runs in CI (the `memory-service` job added in M1). The full container local-run + KIND deploy is local/e2e and documented in `REPORT.md`; promote a minimal deploy check into e2e in M7.

## Commit / PR strategy

- `feat/memory-service` stacked off `feat/memory-atomic-stores`; one comprehensive commit per TODO; PR into `feat/memory-atomic-stores`; Copilot co-author trailer; CI green. `REPORT.md` gitignored, posted as a PR comment.

## Out of scope (later phases)

The runtime client and message-history bridge (M3); the `MemoryStore` CRD and operator deployment of this service (M4 — M2 provides the image + readiness contract the operator consumes); non-optional fail-closed scope resolution, A2A prefix inheritance, and the full synchronous erasure-fan-out guarantees (M5); HA tuning, metrics endpoint, durable-queue decision, e2e promotion, docs (M7).

Two capabilities discussed during design are explicitly deferred to M7 rather than built here. The **session-end flush (idle-TTL sweeper)** — the background sweep that detects idle sessions and folds/flushes their sub-threshold trailing window into the medium-term digest and long-term extraction — is a completeness improvement for stranded session tails, not a correctness blocker, so M2 ships the on-fold cascade only and the sweeper lands in M7. The **native async Postgres data-plane path (asyncpg)** is likewise deferred: M2's async baseline is async FastAPI handlers plus a bounded `run_in_executor` boundary isolating the sync Mem0 client (which already keeps the service non-blocking), while converting the dual SQLite/psycopg backend to async drivers is a throughput optimisation taken up in M7.
