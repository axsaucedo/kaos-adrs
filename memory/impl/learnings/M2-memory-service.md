# Central memory service — findings and plan deltas

## Outcome

The atomic stores are now a deployable FastAPI service with recall/write/forget over HTTP, off-path extraction on a bounded runner, both storage modes wired, OpenTelemetry spans, and a container image. The M1 deltas held: lazy model binding lets the service start before its `ModelAPI` is reachable, recall pass-through preserves Mem0's native fields, empty recall is a normal degraded-to-short-term result, and the local/external switch is a clean field copy. The notes below are the M2-specific learnings to fold into M3 (the runtime client in `pais`) and M4 (the operator that deploys the service).

## Confirmed in code

- **Readiness probes stores, not models.** `/readyz` pings the long-term vector store (`list_cols`) and the short-term store; it deliberately does not dial the model endpoint. A service with an unreachable `ModelAPI` is still ready to serve short-term tier recall and to queue extraction — it just degrades long-term operations. M4's readiness gating on the `MemoryStore` CRD should mirror this: store reachable ⇒ ready, model optional.
- **Recall never blocks the turn.** Long-term failure (model down, store unreachable, empty result) degrades to short-term-only with `degraded=true` and HTTP 200. Write fail-soft returns 202 with `degraded=true` and still durably appends the turn. This is the contract M3's client must preserve: memory is best-effort on the hot path.
- **Short-term append is in-band and durable; long-term extraction rides the eviction.** The split is the load-bearing design choice — the request returns as soon as the turns are persisted to the short-term window, and fact extraction (the LLM call) runs on the background runner. It is **not** per turn: extraction is scheduled only when an append evicts a batch, and it extracts *that evicted batch* (the same eviction that folds the medium-term digest). M3 should treat a `202` with `scheduled=true` as success, treat a `200` buffered write as equally successful, and never wait on extraction.

## Deltas to fold into M3 / M4

1. **[M3] The client speaks four endpoints with a fail-soft default.** `/v1/recall` (sync, returns `block` + `facts` + `short_term` + `medium_term`), `/v1/write` (fire-and-confirm), `/v1/forget`, and the probes. The runtime should inject `RecallResponse.block` verbatim into system context and must tolerate `degraded=true` on every call. `failure_mode` is layered: an explicit per-request value wins, otherwise the store-configured `default_failure_mode` applies, otherwise the service falls back to `soft`. The runtime only sets `strict` where a caller explicitly wants hard failures, and otherwise omits it to inherit the store default.

   - **Recall splits the two conversational tiers.** `short_term.recent` is the verbatim active window; `medium_term.summary` is the rolling digest. The runtime should not conflate them — the block already renders both, but any client-side handling must read the digest from `medium_term`, not from `short_term`.
   - **Write is a batch producer against the cascade.** `/v1/write` accepts a `turns` list and returns `202` with `scheduled=true` only when the appends evicted a batch (which triggered off-path long-term extraction), or `200` with `scheduled=false` when the turns were buffered within budget. Both are success — the client must treat `200`-buffered and `202`-scheduled identically and never wait on extraction. Prefer sending turns in a batch (M3's per-turn loop is the batch producer's target) so the eviction/extraction fires once per flush rather than per turn.

2. **[M3] Owner presence is non-optional per scope, including `shared`.** Reconfirmed at the service boundary: a recall whose scope resolves to no owner id makes Mem0 raise. The client must always populate the field the scope `level` requires (and the reserved shared-owner id for `shared`) before calling.

3. **[M3/M4] Sync handlers run on a threadpool — shared local state needs locking.** FastAPI dispatches sync endpoints to a worker threadpool, so the SQLite short-term store needed `check_same_thread=False` plus an `RLock` around its read-modify-write paths. This only bites the single-container local mode; external mode (Postgres) is unaffected. M4 should keep local mode to one replica (the PVC + SQLite are single-writer); external mode is the path to scale out.

4. **[M4] History DB isolation is what makes external mode horizontally scalable.** Mem0's change-history SQLite log is per-process. Routing it to the PVC for local and to an ephemeral tempdir for external means shared Postgres is the only shared state in external mode, so replicas are stateless. M4's Deployment for external mode can scale replicas freely; local mode is a single-replica StatefulSet-style topology on one PVC.

5. **[M4] One container, two stateful topologies.** Local mode = embedded Chroma + SQLite on one PVC, single replica. External mode = pgvector + Postgres, N stateless replicas, no PVC. The CRD → Deployment mapping is a direct copy of `StorageConfig` with the replica count and volume claim conditioned only on `storage_type`. No bring-your-own Postgres/pgvector provisioning lives in the service; the operator (or the CLI installer) stands up the backing store.

6. **[M4] The CLI installer must provision the external backing store.** External mode assumes a reachable pgvector/Postgres. As with other KAOS dependencies, this should be an explicit, integrated part of the CLI system installer, not an undocumented prerequisite.

## Implementation deviations to carry forward

- **Request path is async over a bounded executor; the background runner stays a threadpool.** The handlers are `async def` and dispatch the sync store/Mem0 calls through a KAOS-owned bounded `ThreadPoolExecutor` (`request_concurrency`), which is the explicit request-path Mem0 isolation boundary (vs FastAPI's implicit ~40-thread pool). The stores remain synchronous behind the executor — native asyncpg is deferred to M7. The off-path `BackgroundRunner` (extraction + summary folding) is a *separate* bounded `ThreadPoolExecutor` exposing `submit`/`__call__` so it doubles as the store's scheduler. M3/M4 should not assume the service exposes an asyncio event loop to callers, and should treat both pools as independently bounded.
- **OpenTelemetry providers are set once per process.** `set_tracer_provider` only takes effect once, so tests use a module-scoped provider/exporter fixture cleared per-test rather than re-installing a provider each test. Any later span-emitting component must reuse the process tracer (`trace.get_tracer("kaos.memory")`), not install its own provider.
- **App lifecycle uses `@asynccontextmanager` lifespan, not `@app.on_event`.** Matches `pais/server.py` and drains the background runner on shutdown. M3's in-runtime client (if it owns any background work) should follow the same lifespan pattern.

## Test infrastructure to reuse downstream

- The offline harness from the previous phase (`tests/_fakes.py::DeterministicEmbedder`, `conftest.py` `offline_models`/`pgvector_dsn`) carries straight into the service tests; `infer=False` writes exercise the short-term tier and presentation without any LLM call.
- FastAPI `TestClient` drives the full app offline; the e2e test asserts the recall/write/forget contract end to end. A module-scoped OTel fixture is required so the once-per-process tracer provider does not leak across tests.
- CI runs the service suite against `pgvector/pgvector:pg16` as a service container, reusing the established job pattern.
