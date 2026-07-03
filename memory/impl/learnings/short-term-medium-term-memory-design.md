# Short-term and medium-term memory design — finalized learnings

## Purpose

This document is the comprehensive design-learning record for the KAOS short-term, medium-term, and long-term handoff decisions captured in [ADR 0002](../../adrs/adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md), [ADR 0003](../../adrs/adr_0003_memory-interface-and-runtime-data-plane.md), [ADR 0004](../../adrs/adr_0004_deployment-topology-and-control-plane.md), and [ADR 0005](../../adrs/adr_0005_multi-tenancy-agent-grouping-and-governance.md). It supersedes the partial implementation note in [Memory-service restructure and short-term summarisation redesign](./refactor-store-restructure-and-summarisation.md) for architectural rationale, while that earlier note remains the implementation-specific record of the package restructure and first off-path summarisation refactor.

## Baseline that forced the redesign

The current code baseline had the right primitive pieces but the wrong scaling and tier boundaries. The store used `short_term_turns` and `short_term_summary` tables, a `folded` column, an in-process `threading.Lock`, a per-write overflow scan in `_enforce`, eviction that trimmed only to just-under-cap, a singleton summary upsert, and a service path that looped one Mem0 extraction per turn with an unbounded `ThreadPoolExecutor(max_workers=4)`. That shape works as a prototype but it couples cheap writes to overflow maintenance, makes fold coordination process-local, causes fold thrash once a session hovers around the limit, overwrites digest history, and risks multiplying Mem0 extraction calls during autonomous loops.

The target design keeps the simple KAOS-owned relational store but changes how it is interpreted. Short-term memory is the session-only verbatim window. Medium-term memory is the existing rolling summary reconceptualized as session-scoped compaction. Long-term memory is Mem0 atomic facts. The important shift is not adding another elaborate class hierarchy; it is preventing each tier from doing the wrong job.

## Postgres primer behind the storage decisions

Postgres durability normally comes from WAL plus fsync: data changes are written to the write-ahead log and flushed so the database can recover committed changes after a crash. That durability is valuable for long-term facts and committed metadata, but it is overkill for an ephemeral conversational window whose loss degrades continuity rather than correctness.

Postgres `UNLOGGED` tables skip WAL for table data, which makes writes faster and avoids fsync pressure for that table. They are still normal shared Postgres tables while the primary is running: all memory-service replicas see coherent rows through the same database, and hot pages live in `shared_buffers` so a frequently used window is already RAM-resident between checkpoints. The trade-off is explicit: an `UNLOGGED` table is truncated during crash recovery and does not replicate to standbys, so it is primary-only. That is acceptable for the short-term window because the window is ephemeral and recoverability comes from long-term facts and future turns, not from treating verbatim context as a durable ledger.

Postgres MVCC makes append-only inserts concurrency-safe: multiple service replicas can insert rows for the same session without blocking each other on a shared mutable active-window row. Consolidation is the operation that needs serialization, not append. Postgres advisory locks such as `pg_advisory_xact_lock(hashtext(scope_key))` or row-claiming with `SELECT ... FOR UPDATE SKIP LOCKED` serialize fold/flush ownership across replicas without making all writes single-writer.

## Mem0 facts that shaped the boundary

Mem0 is the right long-term fact engine but the wrong short-term or medium-term engine. In Mem0 v2.0.10, `_add_to_vector_store` runs one `llm.generate_response` per `add` when `infer=True`, so a per-turn Mem0 write is a per-turn LLM extraction call. Its `AsyncMemory` methods use `await asyncio.to_thread(...)`, which means the async API is a thread offload wrapper rather than provider-native non-blocking I/O. Its OpenAI LLM and embedding integrations in `llms/openai.py` and `embeddings/openai.py` use sync clients rather than `AsyncOpenAI`.

Those facts lead to three conclusions. First, Mem0 should receive batches at fold and session-end flush time, not every turn. Second, KAOS should own the async boundary with a bounded executor instead of hiding synchronous provider calls behind Mem0's `AsyncMemory`. Third, Mem0 should store atomic long-term facts only; it should not store the live verbatim window or a single evolving narrative summary.

## Decision 1: short-term scope is session-only

The verbatim short-term window is scoped only to a session. The table keeps a `scope_key` column so rows can be keyed, locked, joined, swept, erased, and related to the wider scope model, but the logic restricts this tier to the concrete `session_id`.

The reason is concurrency pollution. A user-level, agent-level, or shared short-term window would interleave concurrent sessions, so an active run could see verbatim turns from another conversation simply because they share a principal or agent. That would be worse than forgetting: it would inject misleading live context. Cross-session continuity belongs in long-term extracted facts, where facts have provenance and retrieval relevance, not in a merged recency buffer.

This decision updates the earlier broad scope hierarchy by narrowing only the conversational tiers. ADR 0005 still governs long-term private/user/shared memory, but ADR 0003 and ADR 0005 now make clear that `scope: user` does not create a user-scoped short-term window.

## Decision 2: rolling summary is medium-term compaction

The existing rolling-summary mechanism is reframed as the medium-term tier. This is a rename and reconceptualization, not a new store or class. It is still the same kind of summarizer-backed path, but its purpose is now precise: compaction and conversational continuity for one session.

This matters because summary text is not the same as memory insight. A rolling summary says “what has happened in this conversation so far” in compressed narrative form. It should not pretend to be a durable user preference, semantic fact, or cross-session profile. Calling it medium-term makes the tier boundary explicit: it lives longer than the verbatim window but remains session-bound and conversational.

## Decision 3: medium-term tier is session-scoped, versioned, and append-only

The medium-term tier is session-scoped and versioned with a retention cap. It is a reframing of the existing summarizer, so no new class is introduced solely to make it sound like another engine. The storage shape becomes append-only rows of `medium_term_memory_summaries(scope_key, version, text, tokens, created_at)`, with recall reading the latest version by `ORDER BY version DESC LIMIT 1`.

The retention cap turns versioning into a bounded audit trail. Keeping N versions helps explain how a digest evolved, debug a bad fold, and compare summary quality without committing to unbounded storage. A singleton digest is simply N=1, so versioning does not preclude the simplest deployment.

## Decision 4: consolidation ownership is serialized by Postgres locking

Folding is serialized with database locks in external mode: either `pg_advisory_xact_lock(hashtext(scope_key))` around the fold transaction or `SELECT ... FOR UPDATE SKIP LOCKED` to claim pending fold/flush work. This allows many memory-service replicas to run concurrently while ensuring only one owns a session's consolidation at a time.

This avoids a false dichotomy between “single writer” and “lossy background behaviour.” Concurrent writers to the same session are rare but possible, and HA replicas should not double-fold the same rows or race a final flush. The in-process `threading.Lock` only protects one Python process and therefore cannot be the correctness mechanism in a replicated service. Local SQLite mode remains single-replica by design, so the simple in-process lock is acceptable there.

## Decision 5: folding is never synchronous on write

Folding and summarisation are always off the write path. A write inserts rows, updates cheap session metadata, and returns; if thresholds indicate a fold, it schedules background work. No production write should block on an LLM call.

This is the central latency rule. LLM summarisation can be slow, rate-limited, or temporarily unavailable, and the memory write endpoint may be called after every model response. Letting a write wait on summarisation would convert a context-maintenance concern into user-visible latency. The accepted cost is a brief visibility gap where pending rows may no longer be in the active window before the latest digest appears; this is better than blocking every overflow and is mitigated by clear pending-state metrics and the fact that long-term extraction consumes the same raw batch.

## Decision 6: the smart server is Postgres-first, not Redis-backed

The production server is “smart” on Postgres: append-only MVCC inserts, batched multi-row writes, lazy-read active-window computation, optional `UNLOGGED` short-term table, and connection pooling. Redis is explicitly out of scope for this design.

Postgres is sufficient for conversational write frequency, especially when writes are append-only and batched. The system already wants Postgres for pgvector in the production long-term store, so adding Redis for the short-term window would increase operations without solving a correctness problem. `UNLOGGED` Postgres gives the main performance property wanted from Redis — low write overhead for ephemeral data — while preserving one coherent relational coordination point for locks, sweeps, and versioned summaries.

## Decision 7: write accepts multiple turns in one call

The write endpoint accepts multiple turns per request. A single-turn request is just the degenerate case. This replaces the runtime pattern of looping one HTTP write per turn.

Batching collapses N network calls, N commits, and N threshold checks into one operation. It also aligns with the actual semantic unit: after a model response, the runtime often has a small sequence of user, assistant, tool-call, and tool-return parts that belong to one interaction. Persisting them together makes ordering clearer and fold scheduling cheaper. As built this batching runs the whole way down: the short-term store's `add` is array-only (`add(scope, [(role, content), ...])`), so a request's turns land in a single `executemany` insert, one commit, and one overflow scan, and the evicted batch drives a single long-term extraction. The single-turn convenience signature was dropped in favour of the array form because the one-element list is a trivial caller overhead and removing the second code path keeps the eviction seam unambiguous.

## Decision 8: alpha token counting uses raw content

Token counting uses raw content counting for alpha. This gives a stable relative bound at low implementation cost and is enough to prevent unbounded context growth.

The caveat is documented and accepted: raw content counting under-counts structural overhead such as role labels, message wrappers, tool-call JSON, provider-specific framing, and system-injected memory block text. Therefore `token_budget` is a soft operational budget, not an exact provider-token guarantee, and `hard_event_cap` remains as a second safety guard. If exact model-token accounting becomes necessary, it can replace the counter without changing the tiering model.

## Decision 9: names should reveal intent, not tables

The terminology is changed to short-term window and medium-term summaries. Tables become `short_term_memory_window` and `medium_term_memory_summaries`; `folded` becomes `pending_summary`; reads become `active_window()` and `short_term_context()`; folding becomes `fold_pending_into_summary()`; and internals describe behaviour (`_drop_stale_window`, `_ids_exceeding_budget`, `_load_active_window_rows`, `_load_pending_summary_rows`, `_window_token_total`, `_load_summary`). The existing simple verbs `add`, `summary`, `clear`, and `close` stay.

The reason is to make the code backend-agnostic and tier-aware. Names like `_from_db` and `_in_table` encode where data happens to live rather than why it is being loaded. Names like `recent()` also hide whether the result is a budgeted active window, an unbounded recency list, or a summarized context. The ADRs record the terminology even though the actual renames are implementation work.

## Decision 10: Model 2 cascade feeds both medium-term and long-term memory

Turns enter the short-term window only. When a fold evicts the oldest batch, that raw evicted batch feeds both the medium-term digest and Mem0 long-term extraction. There is no per-turn Mem0 write.

This cascade is the main cost-control lever. It avoids Mem0 running one extraction LLM call per turn, keeps the live write path cheap, and uses the moment of eviction as the natural point to decide that raw turns need durable representation elsewhere. It also keeps medium-term and long-term derivations grounded in the same raw input batch, which improves provenance and debugging.

## Decision 11: long-term extraction is per-fold plus guaranteed session-end flush

Long-term extraction timing is Option C: batched per-fold plus a guaranteed session-end flush. The fold path handles long sessions that exceed `compaction_trigger`; the idle-TTL flush handles sessions that never grow enough to fold.

This avoids both extremes. Per-turn extraction is too expensive, and fold-only extraction would miss short sessions. The idle-TTL session-end flush gives eventual extraction for the remaining window without requiring every client or runtime path to emit a perfect close signal.

## Decision 12: the digest is versioned, not a singleton upsert

The medium-term digest is append-only versioned with latest-version recall and a retention cap. A singleton upsert is treated as the N=1 case, not the conceptual model.

Versioning is almost free because folds are already discrete events. It preserves history for audit and debugging, allows operators to inspect whether a fold got worse, and avoids overwriting the only copy of the prior digest before the new one is known to be useful. It also fits the Postgres WAL/MVCC append-only style better than a constantly updated singleton row.

## Decision 13: the digest is not indexed into Mem0

The medium-term digest is injected directly from Postgres at recall time and is not sent to Mem0. Mem0 receives raw evicted turns for fact extraction instead.

The digest is narrative continuity. Mem0 is optimized to break input into atomic facts and retrieve them by vector similarity. If the digest were indexed, Mem0 would shred the narrative into fragments, duplicate facts already extractable from the raw turns, and pollute vector search with “summary of conversation” artifacts. Direct injection preserves the digest shape and keeps vector memory focused on durable facts.

## Decision 14: the Postgres short-term window is UNLOGGED; Redis stays out

In external mode, the short-term window uses a Postgres `UNLOGGED` table. This skips WAL and fsync for ephemeral rows while keeping a shared relational table coherent across service replicas. It is the right compromise between speed and operational simplicity.

The caveats are explicit. `UNLOGGED` tables are truncated after crash recovery and do not replicate to standbys, so the window is primary-only and crash-lossy. That is acceptable because short-term memory is not the durable record. tmpfs tablespaces and gateway-level session-affinity routing are deferred future options: tmpfs could further reduce disk dependence, and affinity could improve locality, but neither is required for correctness because Postgres locks coordinate consolidation.

## Decision 15: lazy-read compaction marks replace trim-to-cap thrash

Writes append rows. Reads compute the active window by scanning newest rows until the token budget is reached, then presenting them chronologically. Folding is triggered at `compaction_trigger` and evicts down to `compaction_target`, not to zero and not merely to just under the cap. The shipped field names are `compaction_trigger`/`compaction_target` (the earlier `high_water`/`low_water` "watermark" naming was renamed as-built because it described the eviction behaviour, not a hydraulic level).

This fixes the previous thrash pattern. If the store trims to just-under-cap, the next turn can immediately exceed the cap again, causing a fold nearly every turn. A lower compaction target amortizes folding by creating headroom. Lazy reads also remove per-write overflow scans, so writes stay cheap even when a session has many historical rows awaiting sweep or retention cleanup.

## Decision 16: compaction marks and execution knobs exist at both store and agent levels

The shared knob set is `token_budget`, `compaction_trigger`, `compaction_target`, `hard_event_cap`, `digest_max_tokens`, `idle_ttl`, `sweep_interval`, `rolling_summary`, and `concurrency`. These appear on the memory/MCP service CRD side as server settings and on the Agent side as client parameters or per-agent policy.

Both levels are necessary. The service owns locks, sweeps, digest retention, executor pools, and safe defaults; the agent owns its desired conversational budget and whether it wants rolling summary. Validation is the same everywhere: `compaction_target < compaction_trigger <= token_budget`, `hard_event_cap >= 1`, positive TTL and sweep interval, positive digest budget when rolling summary is enabled, and `concurrency >= 1`. Surfacing the knobs in both places resolves the earlier conflict where the store was treated as infrastructure-only.

## Decision 17: idle-TTL sweeper detects session end

The memory service design tracks `last_write_at` per session and periodically sweeps sessions idle longer than `idle_ttl`. A sweeper claim uses the same PG-locked path as folding to avoid double flushes across replicas. The flush folds remaining context into the medium-term digest when enabled, extracts long-term facts from the remaining raw window, and clears ephemeral rows. An optional `/v1/session/close` endpoint can request the same path explicitly.

This design is deferred to productionisation rather than built into the initial service cut. It is a completeness improvement for stranded sub-threshold session tails: without it, long sessions still flush on fold, while short sessions may leave a tail in the ephemeral window until a later close path or cleanup. Deferring it avoids adding a background sweep loop, lock-claim path, and operational metrics before the service has enough usage data to justify them. When implemented, idle TTL becomes the practical session-end signal for clients that crash, disconnect, or never send a close event; the sweep interval controls promptness and the lock controls correctness.

## Decision 18: background mitigations are staged, not overbuilt

The mitigation sequence is deliberately staged: Model 2 batching first, queue-depth and executor OTel metrics second, per-scope coalescing or single-flight third, and bounded-queue backpressure with a degraded flag fourth. A durable queue is not built up front.

This keeps the alpha design simple while leaving an escalation path. The biggest avoidable cost is per-turn extraction, so batching is the primary lever. Metrics reveal whether the in-process background runner is actually saturated. Single-flight addresses duplicate fold scheduling for the same session. Bounded backpressure gives a controlled degraded mode if load exceeds configured concurrency. A durable queue only becomes justified when measured loss or backlog risk exceeds the complexity cost.

## Decision 19: service concurrency is async hybrid

KAOS should implement the initial memory service as async FastAPI handlers with sync Mem0 calls isolated behind a bounded `run_in_executor` pool. Native async Postgres access is a deferred optimization, not a requirement for the first service cut. This is the staged target even though the first prototype started sync, because KAOS is async-first and alpha breaking changes are acceptable, but the biggest non-blocking win comes from owning the Mem0 boundary first.

The nuance is that Mem0's own async API is not enough. `AsyncMemory` wraps sync work in `asyncio.to_thread`, and OpenAI provider integrations use sync clients. If KAOS simply awaited Mem0's async methods, it would still be using threads but without owning the executor boundary. Moving to async FastAPI does not make the threadpool disappear; it makes the threadpool the deliberate Mem0 isolation boundary. Converting the dual SQLite/psycopg short-term backend to native async drivers is the real extra cost, and it is deferrable because the sync short-term DB path is cheap, bounded, and not the LLM-gated throughput ceiling. Owning the bounded pool makes concurrency explicit, keeps the event loop from being consumed by Mem0 extraction, and lets the operator tune `concurrency` against the real downstream ModelAPI rate limit.

## Decision 20: native async Mem0 is an upstream opportunity, not a KAOS blocker

A scoped upstream contribution to Mem0 would be straightforward and valuable: add native-async OpenAI LLM and embedding providers using `AsyncOpenAI`, and keep an `asyncio.to_thread` fallback in `LLMBase` and `EmbeddingBase` for providers that remain sync. That would improve Mem0 for async frameworks without requiring all provider integrations to be rewritten at once.

KAOS should not put this on its critical path. Full async across roughly twenty providers is a large upstream project, and KAOS can get predictable behaviour now with the bounded executor. The upstream opportunity is worth logging because it reduces future thread pressure and could simplify the KAOS adapter later, but the KAOS design must work with Mem0 as it exists today.

## Final target shape

The target memory data plane is therefore: multi-turn writes append raw events to a session-only `short_term_memory_window` in a single batched insert; recall lazily computes the active window by token budget; `compaction_trigger` background folds evict down to `compaction_target` and write a versioned `medium_term_memory_summaries` row; the same raw evicted batch feeds Mem0 long-term fact extraction; idle-TTL flush is recorded as a deferred productionisation completion path for final extraction and cleanup; Postgres locks serialize fold/flush ownership across replicas; the Postgres window may be `UNLOGGED`; Mem0 remains a long-term atomic-fact library behind a bounded executor; native async Postgres is deferred until the service needs it; the write/forget failure mode is layered (an explicit per-request value wins, otherwise the store-configured `default_failure_mode`, otherwise fail-soft); and all knobs are validated consistently across MemoryStore server settings and Agent client policy.
