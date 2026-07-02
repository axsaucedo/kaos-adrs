# Memory-service restructure and short-term summarisation redesign — progress

Status: complete.

Driven by a review of the landed M1/M2 implementation against [adr_0002](../../adrs/adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md) and [adr_0003](../../adrs/adr_0003_memory-interface-and-runtime-data-plane.md), the `memory-service/` package was restructured from ~13 small modules into four cohesive ones and the short-term eviction path was redesigned so summarisation is opt-in and off the response hot path. The changes touch only `memory-service/`; the wire contract and the long-term engine (Mem0) are unchanged. They landed as additional commits on the existing stacked branches — `feat/memory-atomic-stores`, `feat/memory-service`, `feat/memory-runtime-client` — propagated up the stack in order, with every suite green at each branch.

## Tasks

1. **Storage layer consolidated into `stores.py`.** The former `scope.py`, `tokens.py`, `models.py`, `shortterm.py` and `longterm.py` are merged into one `kaos_memory/stores.py` holding `Scope`/`ScopeLevel`/`SHARED_OWNER`, `count_tokens`, `scope_key`, the `Summarizer`/`Scheduler` types, `ModelClient`, `ShortTermStore` and `LongTermStore`. `ModelClient` and `Scope` live here because the stores consume them: the model client is the *outbound* dependency the stores call, and `Scope` is the identity every store operation is keyed on. The write verb is unified to `add` on both stores (replacing short-term `append` and long-term `write`), and the unused `metadata` parameter is dropped.

2. **Short-term eviction redesigned.** `ShortTermTierConfig.rolling_summary` now defaults to `False`. On each `add`, after the cheap insert, `_enforce` computes the overflow (oldest turns beyond `token_budget` or `hard_event_cap`, always keeping ≥1). When summarisation is off, the overflow rows are deleted — a pure recency window with no model call. When on, the overflow rows are marked `folded=1` (so `recent()` drops them from the active window immediately) and `summarize_pending(scope)` is scheduled: it reads all pending rows, folds the whole chunk into the rolling summary in **one** summariser call, upserts the summary, and deletes the folded rows so the store stays bounded. An optional `scheduler` seam runs the fold off the response path when injected and inline otherwise. SQLite access is guarded with a `Lock` and `check_same_thread=False` so the fold can run on a background thread.

3. **Service layer consolidated into `app.py`.** The former `api.py`, `service.py`, `presentation.py`, `background.py` and `__main__.py` are merged into one `kaos_memory/app.py` holding the request/response schemas, the recall presentation block, the `BackgroundRunner`, the `MemoryService`, the FastAPI app factory and the `main()` entrypoint. `settings.py` is folded into `config.py` next to the typed config objects. `build_service` now constructs a single bounded background runner and injects it both as the short-term store's `scheduler` (summary folding off the write path) and as the service scheduler (long-term extraction off the response path), sharing one drainable threadpool. The write handler calls `add`; the container entrypoint is `python -m kaos_memory.app`.

4. **Propagated to the runtime client.** `feat/memory-service` was merged up into `feat/memory-runtime-client`. The runtime (`pais`) talks to the service over HTTP and imports no `kaos_memory` module, so this was a clean propagation with no source changes in `pais`.

5. **Pushed and documented.** All three branches pushed; the stacked PRs (`[MEM-1]`/`[MEM-2]`/`[MEM-3]`) carry the changes. This progress note and the paired learnings capture the restructure and eviction redesign for the downstream phases.

## Package layout, before → after

```
before                          after
kaos_memory/                    kaos_memory/
  __init__.py                     __init__.py
  scope.py        ┐               config.py   (+ settings)
  tokens.py       │               stores.py   (scope + tokens + models + shortterm + longterm)
  models.py       ├─ stores.py    app.py      (api + service + presentation + background + __main__)
  shortterm.py    │
  longterm.py     ┘
  config.py       ┐
  settings.py     ┘─ config.py
  api.py          ┐
  service.py      │
  presentation.py ├─ app.py
  background.py   │
  __main__.py     ┘
```

## Validation

- `memory-service`: `pytest tests/ -q` — 49 passed, 4 skipped (offline; `pgvector`-marked tests opt-in); `make lint` — `black --check` and `ty` clean, at each of the atomic-stores and service branches.
- `pydantic-ai-server`: `pytest tests/ -q` — 327 passed, 10 skipped; `make lint` clean, on the runtime-client branch after propagation.
- Package import + entrypoint resolve cleanly; `MemorySettings` defaults reflect the off-by-default rolling summary.

Findings and the deltas to carry into M4+ are recorded in [`../learnings/refactor-store-restructure-and-summarisation.md`](../learnings/refactor-store-restructure-and-summarisation.md).
