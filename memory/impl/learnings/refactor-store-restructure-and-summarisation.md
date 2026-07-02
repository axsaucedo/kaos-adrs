# Memory-service restructure and short-term summarisation redesign — findings and deltas

## Outcome

The memory-service package is now four modules (`stores.py`, `config.py`, `app.py`, `__init__.py`) instead of eleven, and short-term summarisation is opt-in and off the response hot path. The wire contract and the long-term engine are unchanged, so the change is invisible to the runtime client and to any deployed operator. This document remains the implementation-specific restructure note; the comprehensive finalized architecture rationale for session-only short-term memory, medium-term compaction, Postgres locking, lazy-read watermarks, cascade extraction, and async-hybrid execution now lives in [Short-term and medium-term memory design](./short-term-medium-term-memory-design.md).

## Confirmed in code

- **Grouping by dependency direction is the simplifying rule.** The stores are the outbound edge (they call the model client and Mem0, keyed on `Scope`), so `ModelClient` and `Scope` belong in `stores.py`. `app.py` is the inbound HTTP edge (schemas, routes, presentation, background runner). `config.py` is plain data plus env mapping. This split keeps each module cohesive and well under the ~800-line ceiling without re-introducing micro-modules. Future additions should join the module that matches their dependency direction rather than spawning a new file.

- **Summarisation is a cost, not a default.** The original implementation folded one turn per blocking LLM call, synchronously inside the insert path, with summarisation on by default — so every agent paid a model call on every overflow, on the hot path, and folded rows were retained forever. The redesign makes it opt-in (`rolling_summary` defaults `False`), evicts by a recency window when off (no model call), and — when on — folds the whole overflow chunk in one call, off the response path, deleting folded rows once absorbed. A bounded recency window is the right default for most agents; the durable record lives in the long-term tier.

- **The single background runner backs both off-path paths.** `build_service` injects one `BackgroundRunner` as both the short-term store's `scheduler` (summary folding) and the service scheduler (long-term extraction). All deferred work shares one bounded, retrying, drainable threadpool, so there is a single place to reason about off-path concurrency and shutdown draining.

## Deltas to fold into M4+

1. **[M4] `rolling_summary` is control-plane config, defaulting off.** The `MemoryStore` CRD → `KAOS_MEMORY_*` env mapping must expose `rolling_summary` (env `KAOS_MEMORY_ROLLING_SUMMARY`) and default it off. Agents that want a rolling summary opt in explicitly; alpha allows this breaking default relative to the first M1/M2 cut.

2. **[M4] The summariser model binding only matters when summarisation is on.** With the default off, a memory service needs no reachable summarisation model to serve short-term recall and long-term extraction still uses its own model binding. Readiness must remain store-reachability-only (unchanged from M2): do not gate readiness on the summarisation model.

3. **[M4] Local mode stays single-writer.** The short-term SQLite store is guarded with a `Lock` and `check_same_thread=False` so the background fold thread can touch it, but that is still one process, one PVC, one writer. Keep local mode to a single replica; external mode (Postgres) is the scale-out path. Unchanged from M2, reconfirmed by the fold-on-a-thread change.

4. **[downstream] Accept the async fold visibility gap for the short-term tier.** With a scheduler, folded turns leave the active window (`recent()`) before the summary lands, a brief window where those turns are in neither `recent` nor `summary`. This is the deliberate trade-off of moving summarisation off the hot path for the non-durable short-term tier; the long-term tier holds the durable record, so no information is lost. Any UI or diagnostic that reads short-term state should tolerate this transient gap rather than treat it as data loss.

## Implementation deviations to carry forward

- **`add` is the single store verb.** Both stores expose `add` (mirroring Mem0's `.add()`), replacing the earlier short-term `append` / long-term `write` split. Any downstream code or test double must implement `add`, not the old verbs.

- **`metadata` was vestigial and is gone.** The short-term store's `metadata` parameter had no representation in the wire contract and was dropped. If per-turn metadata is needed later, add it to the wire schema first, then thread it through — do not re-introduce a silently-ignored parameter.

- **Entrypoint is `python -m kaos_memory.app`.** The package no longer has a `__main__.py`; `app.py` runs `main()` under `python -m kaos_memory.app`. The Dockerfile CMD reflects this; any operator-managed command override must match.

## Test infrastructure

- The offline harness (`tests/_fakes.py`, `conftest.py` `offline_models`/`pgvector_dsn`) and the FastAPI `TestClient` e2e path carry through unchanged. The summarisation tests now assert the two modes explicitly: default-off drops overflow with no summariser call, and opt-in (`rolling_summary=True`) folds the whole pending set in a single summariser call and retains no folded rows. A scheduler seam test confirms the fold is deferred off the write path until the scheduled thunk runs.
