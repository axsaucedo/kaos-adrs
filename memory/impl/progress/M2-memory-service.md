# M2 — central memory service — progress

Status: complete.

The atomic stores from the previous phase are now wrapped in a deployable HTTP service. The `memory-service/` package (`kaos_memory`) gains a FastAPI application that exposes the memory contract — recall, write, forget — over HTTP, runs long-term extraction off the request path on a bounded background runner, and ships as a container image with both storage modes wired end to end. Implemented on a branch stacked off the atomic-stores branch, every task committed individually with a comprehensive functional message, and the suite is green in both storage modes (50 tests: local Chroma/SQLite plus pgvector/Postgres behind the `pgvector` marker).

## Tasks

1. **ASGI app + probes** — `service.py` adds the `MemoryService` composition object (long-term store, short-term store, scheduler) and a `create_app` FastAPI factory exposing `/healthz` (liveness, store-independent) and `/readyz` (readiness, which pings the stores, not the model endpoint, so a service starts and reports not-ready before its `ModelAPI` is reachable). `settings.py` builds the service from `KAOS_MEMORY_*` env, and `__main__.py` runs it under uvicorn — the same stack as the agent runtime.
2. **Synchronous recall** — `POST /v1/recall` assembles long-term facts (passed through with Mem0's native fields) and the short-term tier slice (rolling summary plus recent turns) into a deterministic injection block via `presentation.assemble_block`. Recall is best-effort: a long-term failure degrades to short-term-only with `degraded=true` rather than erroring. The SQLite short-term store was made threadpool-safe (`check_same_thread=False` plus an `RLock` around its read-modify-write paths) because FastAPI runs sync handlers on a threadpool.
3. **Write + scheduled extraction** — `POST /v1/write` appends the turn to the short-term tier synchronously (durable, in-band) and schedules long-term fact extraction off the request path, returning `202` with `scheduled`/`degraded` flags. Fail-soft swallows scheduling errors and reports degraded; strict surfaces them.
4. **Bounded background runner** — `background.py` adds `BackgroundRunner`, a `ThreadPoolExecutor`-backed scheduler with bounded concurrency, bounded retry with backoff, an `on_giveup` hook, a `failures` counter, and a drain on shutdown. The app lifecycle moved to an `@asynccontextmanager` lifespan that drains the runner on shutdown.
5. **Forget + rolling summary** — `POST /v1/forget` clears a scope's short-term tier and deletes its long-term memories (fail-soft still clears the short-term tier and reports degraded). Server-side rolling summary is verified end to end: overflow folds into the summary while recent turns stay verbatim.
6. **Storage modes end to end** — local (embedded Chroma + SQLite on one PVC) and external (pgvector + Postgres, stateless replicas) are wired through settings, schema creation is idempotent, the Mem0 change-history SQLite log is routed to the PVC for local and an ephemeral tempdir for external (so shared Postgres is the only shared state and replicas stay horizontally scalable), and OpenTelemetry spans wrap recall/write/consolidate/forget. An e2e test drives the full app.
7. **Container image + pipeline** — a `Dockerfile` (python:3.12-slim, uv-resolved deps, non-root user, local-mode default on a `/data/memory` volume, liveness `HEALTHCHECK`), `Makefile` `docker-build`/`run-local` targets, and per-platform build + manifest-merge jobs for `axsauze/kaos-memory-service` in the reusable image-build workflow, with the service path added to the dev build trigger.

## Validation

- `pytest tests/ -v` — 50 passed (local + pgvector).
- `make lint` — `black --check` clean, `ty` clean.
- Container built and run in local mode: `/healthz` and `/readyz` return 200, `POST /v1/write` (infer=false) returns 202 and the turn surfaces in `/v1/recall` short-term context and the assembled block.

Findings and the deltas to fold into M3/M4 are recorded in [`../learnings/M2-memory-service.md`](../learnings/M2-memory-service.md).
