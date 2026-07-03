# Mem0 async boundary and internals — comprehensive engineering findings

## Purpose

This document records the detailed, non-summarised engineering findings about how Mem0 (v2.0.10) actually executes I/O, why KAOS wraps it in a bounded executor, exactly how much a native-async Mem0 would help, and what it would cost KAOS to go fully native. It complements — and does not restate — the design-decision framing in [Decision 19 (service concurrency is async hybrid)](./short-term-medium-term-memory-design.md#decision-19-service-concurrency-is-async-hybrid) and [Decision 20 (native async Mem0 is an upstream opportunity)](./short-term-medium-term-memory-design.md#decision-20-native-async-mem0-is-an-upstream-opportunity-not-a-kaos-blocker). Those decisions state the position; this note is the evidence and the mechanics behind it, so a future contributor can act on the async work without re-deriving it.

## What Mem0's async API actually does

Mem0 exposes `AsyncMemory` with `async def add`, `search`, and `get_all`, so on the surface it looks event-loop friendly. Inspecting `mem0/memory/main.py::AsyncMemory._add_to_vector_store` shows the reality: every underlying I/O is wrapped in `asyncio.to_thread(...)`. The embedding call (`embedding_model.embed`), the extraction LLM call (`llm.generate_response`), the vector-store `search`/`insert`, and the history `db.save_messages` are each dispatched to the default thread pool rather than issued as native non-blocking I/O. The provider integrations underneath confirm this: `llms/openai.py` and `embeddings/openai.py` construct sync `OpenAI` clients, not `AsyncOpenAI`. So `AsyncMemory` is a thread-offload wrapper, not provider-native async.

The practical consequence is that awaiting `AsyncMemory` does not remove threads from the picture — it just hides them inside Mem0's own default (unbounded) `to_thread` executor, which KAOS cannot size or observe. That is strictly worse for a service that needs to bound concurrency against a downstream ModelAPI rate limit.

## The two thread layers

There are two distinct thread layers between a KAOS request and the model call, and they have different removal conditions. Conflating them is the main source of confusion when reasoning about "can we drop the threadpool".

- **Layer A — KAOS `_offload` executor.** The memory service handlers are `async def` and dispatch the sync `Memory` (not `AsyncMemory`) calls through a KAOS-owned bounded `ThreadPoolExecutor` sized by `request_concurrency`. This is the deliberate, observable Mem0 isolation boundary. It is what keeps the event loop free and what the operator tunes.
- **Layer B — Mem0-internal `to_thread`.** Even if KAOS used `AsyncMemory`, Mem0 would still push each I/O onto its own `to_thread` pool because the providers are sync. This layer is inside the library and unbounded by default.

Removal conditions differ. Layer B disappears only when *all four* Mem0 I/O types (LLM, embeddings, vector store, history DB) have native-async implementations — a partial conversion still leaves a `to_thread` on the remaining sync ones. Layer A can be dropped only once Mem0 is fully native end-to-end; dropping it earlier would mean swapping KAOS's *bounded* pool for Mem0's *unbounded default* `to_thread` pool and losing backpressure. Even then, KAOS would not simply delete the boundary — it would replace `_offload` with an `asyncio.Semaphore` to preserve the concurrency ceiling against the ModelAPI. In other words, KAOS keeps a bound either way; the only question is whether the bound guards a thread pool or an await.

## How much native async actually buys — the thread-occupancy analysis

The metric that matters for a service's concurrency ceiling is **thread-occupancy time**: how long a request holds a thread, not end-to-end latency. Each Mem0 `add` with `infer=True` occupies a thread for the sum of its sequential I/O steps, and those steps differ by orders of magnitude:

- LLM extraction (`generate_response`): seconds.
- Embedding (`embed`): tens to low hundreds of milliseconds.
- Vector store search/insert: single-digit milliseconds.
- History DB save: single-digit milliseconds.

The LLM call dominates thread-occupancy by ~1–2 orders of magnitude, with embedding a distant second and the datastores negligible. Therefore converting just the **LLM and embedder** to native async collapses roughly 99% of the thread-occupancy time; the vector/history conversions are rounding error for throughput. This is why native async is **not** all-or-nothing: the highest-value, smallest-surface iteration is `AsyncOpenAI` for LLM and embeddings, and it captures almost all of the concurrency win.

Two caveats that are easy to get wrong:

- **Native async does not reduce single-request latency.** The steps inside `add` are data-dependent and sequential (embed → extract → search → write), so a single request still takes the same wall-clock time. The win is purely that a freed thread (or event loop slot) can service *other* requests during the LLM wait — i.e. higher concurrency at the same latency, not lower latency.
- **The win only materialises if KAOS stops interposing its own thread.** With Layer A in place and sync providers, an async Mem0 method would still block a KAOS thread. So the upstream provider work and the KAOS boundary change are complementary: neither alone removes the thread occupancy.

## Simplest highest-value async iteration

Given the analysis, the smallest change that drives the most value is: add native-async OpenAI **LLM and embedding** providers in Mem0 (via `AsyncOpenAI`), keep an `asyncio.to_thread` fallback in `LLMBase`/`EmbeddingBase` for providers that remain sync, and have KAOS call `AsyncMemory` for those paths. That is a bounded, reviewable contribution that improves Mem0 for every async framework without rewriting all ~20 provider integrations at once. Full end-to-end native async (vector stores + history DBs across all backends) is a much larger project whose marginal throughput benefit over "LLM+embedder native" is small.

## Upstream contribution

The scoped opportunity is filed upstream as [mem0ai/mem0#6070 — "feat(async): Extend AsyncMemory to support true/native async end-to-end"](https://github.com/mem0ai/mem0/issues/6070). The proposal is to extend `AsyncMemory` toward native async starting with the OpenAI LLM and embedding providers using `AsyncOpenAI`, preserving a `to_thread` fallback in the base classes so sync-only providers keep working. This is logged as an opportunity, not a KAOS dependency: KAOS gets predictable, bounded behaviour today with its own executor, and would only simplify its adapter (Layer A → `asyncio.Semaphore`) if and when Mem0 is native end-to-end.

## Native async Postgres data-plane cost (why it is deferred to M7)

Separately from Mem0, KAOS's own short-term store (`stores.py`) is synchronous behind the same executor boundary. Converting it to native async drivers (`asyncpg` for external, an async local path) was deferred to M7 because the cost is real and the payoff is partial while Mem0 stays threaded regardless. The concrete complexity:

- **Placeholder style.** The current `_Backend` swaps `?` → `%s` for psycopg; `asyncpg` uses a third style, numbered `$1, $2, …`, so the placeholder handling needs a third branch rather than a simple swap.
- **No DB-API cursor.** `asyncpg` has no `cursor().fetchone()/.fetchall()` model; the ~12 call sites that use cursor semantics must move to `fetch`/`fetchrow`/`execute`, and a connection **pool** plus an `asyncio.Lock` replaces the single shared connection under a `threading.Lock`.
- **Method colouring.** The ~15 `ShortTermStore` methods become `async def`, which propagates through every caller.
- **Scheduler seam breaks.** The `BackgroundRunner` currently expects a sync callable (it doubles as the store's scheduler); an async store fold path no longer fits a `ThreadPoolExecutor.submit` thunk cleanly and needs an event-loop-aware scheduling seam.
- **Test surface.** ~7 test files move to `pytest-asyncio`.
- **Partial payoff.** Because Mem0 remains threaded until #6070 lands, converting the cheap DB path to native async does not remove the dominant thread occupancy; it is a throughput optimisation to gate on measured need, not a correctness fix.

The M2-shipped position is therefore correct: async FastAPI handlers, sync stores and sync Mem0 behind one bounded KAOS executor, with the native-async Postgres path and the upstream Mem0 async work both tracked for M7 / upstream rather than the initial cut.
