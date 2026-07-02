# Memory-service restructure and short-term summarisation redesign — implementation plan

**Branches (KAOS)**: applied bottom-up on the existing memory stack — `feat/memory-atomic-stores` (storage layer), then merged up through `feat/memory-service` (HTTP layer) and `feat/memory-runtime-client`. No new PRs; the changes land as additional commits on the open stacked PRs, which are then propagated up.

> **Read first.** This is a revision of already-landed M1/M2 code, driven by review of the implementation against [adr_0002](../adrs/adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md) and [adr_0003](../adrs/adr_0003_memory-interface-and-runtime-data-plane.md). It changes structure and short-term eviction behaviour; it does **not** change the HTTP wire contract or the long-term engine choice. Keep every suite green at each branch and propagate merges up the stack in order.

## Motivation

Two problems surfaced in review of the memory-service package:

1. **Over-fragmentation.** The package is split into ~13 modules of 18–220 lines each. This is artificial complexity that works against the KEEP IT SIMPLE principle. Group by layer into a few cohesive modules, each well under an ~800-line ceiling.
2. **Short-term summarisation in hot paths.** The short-term store folds overflow into a rolling summary with **one blocking LLM call per evicted turn, synchronously inside the insert path**, and retains folded rows forever. Summarisation is also enabled by default, so every agent pays for it. Redesign per [adr_0003](../adrs/adr_0003_memory-interface-and-runtime-data-plane.md): summarisation is opt-in (default off), evicts by a recency window when off, and — when on — folds the whole overflow chunk in one call, off the response hot path, deleting folded rows once absorbed.

Two smaller consistency fixes ride along: unify the write verb to `add` on both stores, and drop the unused `metadata` parameter from the short-term store.

## Target module layout

`memory-service/kaos_memory/`:

- `stores.py` — the storage engine: `Scope`/`ScopeLevel`/`SHARED_OWNER`, `count_tokens`, `scope_key`, the `Summarizer` type, `ModelClient`, `ShortTermStore`, `LongTermStore`. (Merges the former `scope.py`, `tokens.py`, `models.py`, `shortterm.py`, `longterm.py`.)
- `config.py` — typed config dataclasses (`StorageConfig`, `LocalStorage`, `ExternalStorage`, `ModelConfig`, `ShortTermTierConfig`) **and** environment resolution (merges the former `settings.py`, added on the service branch).
- `app.py` — the HTTP surface: request/response schemas, the FastAPI app and routes, the recall presentation block, the bounded background runner, and the `main()` entrypoint. (Merges the former `api.py`, `service.py`, `presentation.py`, `background.py`, `__main__.py`.)
- `__init__.py` — package exports.

Rationale for `ModelClient` and `Scope` living in `stores.py`: both are consumed by the stores (the model client is an *outbound* dependency the stores call; `Scope` is the identity every store operation is keyed on). The `app.py` layer is KAOS's *inbound* HTTP surface, a different direction of dependency.

## Short-term eviction design (the summarisation redesign)

`ShortTermStore` gains an optional `scheduler: Callable[[Callable[[], None]], None]`. On each `add`, after the cheap insert, `_enforce` computes the overflow (oldest turns beyond `token_budget`, or beyond `hard_event_cap`, always keeping ≥1 turn):

- **`rolling_summary` disabled (the default):** delete the overflow rows. Pure recency window, no model call.
- **`rolling_summary` enabled:** mark the overflow rows pending (`folded=1`) so `recent()` drops them from the active window immediately, then schedule `summarize_pending(scope)`. If a scheduler is injected (the service passes its background runner), the call runs off the response path; if not (tests / local), it runs inline. `summarize_pending` reads all pending rows for the scope, folds them into the rolling summary in **one** `summarizer` call, upserts the summary, and **deletes** the folded rows so the store does not grow unboundedly.

The wire contract (`POST /v1/write` → `add`; `POST /v1/recall` reads the stored summary + active window) is unchanged. Recall never triggers a model call.

## Tasks

Each task keeps the relevant suite green and lands as one comprehensive, functional commit (KAOS commits carry the Copilot co-author trailer). Do not reference phases/tasks in commit messages, branches, or PR text.

1. **Restructure the storage layer (`feat/memory-atomic-stores`).** Create `stores.py` merging `scope.py`, `tokens.py`, `models.py`, `shortterm.py`, `longterm.py`; delete those modules; update `__init__.py` exports. Rename the short-term write verb `append` → `add` and the long-term `write` → `add`. Drop the unused `metadata` parameter. Update all M1 tests to import from `kaos_memory.stores` and use `add`. **Validate**: `cd memory-service && make test && make lint` (offline suite green; `pgvector`-marked tests opt-in). Commit.

2. **Short-term eviction redesign (`feat/memory-atomic-stores`).** Default `ShortTermTierConfig.rolling_summary` to `False`. Implement the two-mode `_enforce` (recency-window delete when off; mark-pending + batched `summarize_pending` when on), the optional `scheduler` seam (inline when absent), and folded-row deletion after summarisation. Update the short-term tests: default-off drops overflow, opt-in summarises the overflow chunk in one call and retains no folded rows, `clear` still removes turns + summary, hard cap still bounds the window. **Validate**: short-term + smoke suites green; `make lint`. Commit.

3. **Restructure the service layer + wire the scheduler (`feat/memory-service`).** Merge M1 up. Create `app.py` merging `api.py`, `service.py`, `presentation.py`, `background.py`, `__main__.py`; delete those modules. Merge `settings.py` into `config.py`; delete `settings.py`. Point the container entrypoint at `python -m kaos_memory.app`. Pass the bounded background runner into `ShortTermStore` as its `scheduler` so opt-in summarisation runs off the response path. Update the write handler to call `add`. Update all M2 tests and imports. **Validate**: full memory-service suite green; `make lint`; `docker build` succeeds. Commit.

4. **Propagate to the runtime client (`feat/memory-runtime-client`).** Merge M2 into `feat/memory-runtime-client` (the runtime talks to the service over HTTP and imports no `kaos_memory` module, so this is a clean propagation). **Validate**: `cd pydantic-ai-server && python -m pytest tests/ -q` green and `make lint` clean. Commit the merge if one is produced.

5. **Push and document.** Push all three branches. Refresh the gitignored `REPORT.md` and post it as the stacked-PR comment. Write `impl/progress/*` and `impl/learnings/*` entries capturing the restructure and the eviction redesign for downstream phases (M4+).

## Risks and mitigations

- **Import churn across branches.** The restructure only touches `memory-service/`; the runtime client (`pais/`) imports none of it, so M3 propagation is a clean merge. Resolve any merge markers in favour of the restructured files.
- **Default-off summarisation changes behaviour.** Agents that relied on a rolling summary must set `rolling_summary: true`; this is surfaced as control-plane config in [adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md). Alpha allows the breaking default.
- **Async fold visibility gap.** With a scheduler, folded turns leave the active window before the summary lands, a brief window where those turns are in neither `recent` nor `summary`. This is the accepted trade-off of moving summarisation off the hot path for the short-term (non-durable) tier; the long-term tier holds the durable record.
