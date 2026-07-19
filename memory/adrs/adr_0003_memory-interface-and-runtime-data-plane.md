# ADR 0003 — Memory interface and runtime data plane

- **Status.** Proposed
- **Date.** 2026-06-30
- **Component.** 3 of 5 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md), [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md), [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md), [KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)
- **Constrains.** ADR 0004 (deployment topology and control plane), ADR 0005 (multi-tenancy and grouping).
- **Revised by.** [ADR 0006](./adr_0006_posture-derived-scope-enforcement.md) removes the scope level from the write portion of the operation contract; writes carry attribution identities only.

## Context

[ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) fixes the conceptual model and [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md) chooses Mem0 as the long-term engine while keeping short-term memory owned by KAOS. This record decides the runtime contract that joins them: the `Memory` abstraction in the Pydantic AI data plane, the redesign of the short-term tier, the reframing of rolling summary as medium-term memory, the long-term operation set, how recalled context reaches the agent, and where scope, concurrency, and observability boundaries sit.

The current `Memory` abstraction is short-term tier-only. Sessions hold an event deque bounded by a fixed maximum length, `build_message_history` replays only `user_message` and `agent_response` events while dropping tool calls, tool results, and delegations, and overflow is handled by truncation. There are no long-term operations. KAOS is in alpha, so this record is not constrained by backward compatibility: the interface, configuration keys, table names, and storage choices are redesigned for the target shape rather than preserved. Source surfaces: `pydantic-ai-server/pais/memory.py`, `pydantic-ai-server/pais/server.py` (`_create_memory`), `pydantic-ai-server/pais/serverutils.py`.

[KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md) established that short-term memory must not be delegated to Mem0 — the vector engine embeds every turn, exposes no ordered raw-turn store, and is not replica-safe for high-frequency writes — so the short-term tier stays a KAOS-owned plain store, consolidated onto the same Postgres instance Mem0 uses for its vector store. The finalized implementation decision sharpens that finding: Mem0 is the long-term atomic-fact engine only; the live verbatim window and the rolling digest are KAOS relational tiers injected directly at recall time.

## Decision

### One extended `Memory` abstraction

There is a single `Memory` abstraction, extended from the short-term-only contract into a tiered one. Long-term operations — write/extract, recall, consolidate, forget — are added to the same abstraction; a backend that serves only short-term memory leaves them unimplemented or no-op. The contract is shaped around the realities of [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md): scope is a first-class argument on every operation, writes are extraction-bearing, and recall is relevance search. Because KAOS is in alpha, the existing method surface and `MEMORY_*` configuration are redesigned rather than preserved; there is no compatibility shim. Terminology is standardized around the actual tiers: a short-term memory window, medium-term memory summaries, and pending-summary rows. See also: [Decision 9 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-9-names-should-reveal-intent-not-tables).

### Short-term tier: session-only verbatim window

The verbatim short-term tier is **session-scoped only**. The store keeps a `scope_key` column so rows can be keyed, joined, erased, and locked consistently, but the runtime logic restricts the short-term window to the concrete `session_id`; higher-scope short-term machinery is removed. User-level, agent-level, tenant-level, or shared recency windows are rejected because they would interleave concurrent conversations and pollute the context of active sessions. Cross-session continuity is served by long-term extracted facts and, where needed later, by explicitly designed higher-level narrative tiers, not by merging live verbatim turns across sessions.

Short-term memory is bounded by a configurable token budget rather than a fixed event count, with an event-count ceiling retained only as a hard safety cap. Alpha token counting uses raw message content as a stable relative bound, with the accepted caveat that provider-specific structural overhead is under-counted. See also: [Decision 1 and Decision 8 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-1-short-term-scope-is-session-only).

### Medium-term tier: rolling summary as session-scoped compaction

The existing rolling-summary mechanism is reframed as the **medium-term tier**. This is a conceptual rename and persistence-shape refinement, not a new store, new class, or new extraction engine. Medium-term memory is session-scoped compaction: it preserves conversational continuity when older verbatim turns leave the active window, but it does not claim to extract durable insights, facts, preferences, or profiles. It is a single evolving narrative digest per session, produced by the same summarizer path that already existed in the short-term store.

Mem0 is a structural mismatch for this tier. Mem0 is optimized to decompose input into atomic, embeddable, individually revisable facts for vector retrieval; a rolling conversational digest is a coherent narrative that should be injected directly at recall time. Indexing the digest into Mem0 would shred narrative continuity into fact fragments and pollute vector search with summary text. Therefore the medium-term digest stays in Postgres/SQLite and is included directly in the assembled memory block; Mem0 receives the raw evicted turns for long-term fact extraction instead.

The medium-term digest is append-only and versioned with a retention cap; recall uses the latest retained digest, and a singleton summary is just the retention cap set to one. Versioning is chosen over in-place upsert because it gives auditability and debugging history while avoiding loss of the previous digest when a fold produces a worse one. See also: [Decision 3 and Decision 12 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-3-medium-term-tier-is-session-scoped-versioned-and-append-only).

### Storage: append-only relational rows on the shared store

Short-term memory is persisted as plain relational rows co-located with the long-term store, with no embeddings and recency-ordered retrieval. It is never on Redis and never delegated to Mem0; it is a cheap insert-and-read-window operation rather than a vector operation ([KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)). [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md) realises co-location per storage mode: in `external` mode the short-term window is on the same Postgres instance that backs Mem0's pgvector long-term store; in `local` mode it is a SQLite table in the same single container as the embedded Chroma store. Writes are append-only, do not maintain a mutable active set, do not scan for overflow on every event, and do not run an LLM; batching is the normal endpoint shape. See also: [Decision 6 and Decision 7 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-6-the-smart-server-is-postgres-first-not-redis-backed).

### Lazy-read compaction marks instead of per-write enforcement

The active short-term window is computed on **read**, not maintained on every write. This lazy-read strategy keeps writes append-only and avoids per-write overflow scans. Folding is triggered by a **compaction-trigger** threshold and evicts toward a **compaction-target** level: `compaction_trigger` decides when folding is needed, and `compaction_target` creates headroom so folding does not recur on nearly every subsequent turn. The fold never evicts to zero and never merely trims to just under the cap. See also: [Decision 15 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-15-lazy-read-compaction-marks-replace-trim-to-cap-thrash).

### Folding and extraction are always off the write path

Folding/summarisation is **never** synchronous on the write path. The write endpoint returns after cheap validation and insert. If a fold is warranted, the service schedules background consolidation; a write must never block on an LLM call. Any inline-sync fold branch is removed or constrained to non-request test seams so production writes cannot wait for summarization. The accepted transient is that, while a background fold is pending, some evicted rows may be neither in the active window nor in the latest digest for a short period; this is acceptable because the short-term and medium-term tiers are conversational context, and long-term extraction is also driven from the same evicted raw batch.

Consolidation is serialized per scope in the datastore, not by assuming one service replica. External Postgres mode uses database-level ownership for fold/flush work so many memory-service replicas can coexist without lost folds or double folds; local SQLite mode keeps the simple in-process lock because it is single-replica by design. See also: [Decision 4 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-4-consolidation-ownership-is-serialized-by-postgres-locking).

### Model 2 cascade into medium-term and long-term memory

The finalized write model is **Model 2 cascade**. New turns enter the short-term window only. When folding evicts a batch, the raw evicted turns feed both outputs: the medium-term digest and long-term Mem0 extraction. There is no per-turn Mem0 write. Long-term extraction timing is batched per-fold plus a deferred session-end flush design for short or low-traffic sessions that never cross `compaction_trigger`; extraction is never per-turn. See also: [Decision 10 and Decision 11 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-10-model-2-cascade-feeds-both-medium-term-and-long-term-memory).

### Batch write endpoint

The memory service write endpoint accepts **multiple turns in one call**. The new endpoint shape persists a batch for a session and performs at most one fold-scheduling decision for the resulting window state; single-turn writes remain the degenerate case of a batch of one. See also: [Decision 7 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-7-write-accepts-multiple-turns-in-one-call).

### Idle-TTL session-end flush

The design records an idle-TTL session-end flush, but it is deferred to productionisation rather than required for the initial service cut. When implemented, the service tracks session idleness, performs the same serialized fold/flush path used for normal consolidation, extracts remaining long-term facts, and clears ephemeral rows; an optional close endpoint can request that path explicitly. This is a completeness improvement for stranded sub-threshold session tails, not a correctness blocker for the initial service. See also: [Decision 17 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-17-idle-ttl-sweeper-detects-session-end).

### Configuration knobs and constraints

The data-plane configuration surface exposes the same behavioural knobs at both client-params and server-settings levels, with the control-plane placement finalized in [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md) and [ADR 0005](./adr_0005_multi-tenancy-agent-grouping-and-governance.md): `token_budget`, `compaction_trigger`, `compaction_target`, `hard_event_cap`, `digest_max_tokens`, `idle_ttl`, `sweep_interval`, `rolling_summary`, and `concurrency`. `token_budget` is the recall budget for the active verbatim window; `compaction_trigger` triggers folding; `compaction_target` is the target retained verbatim tail; `hard_event_cap` is the non-token safety cap; `digest_max_tokens` bounds the medium-term summary; `idle_ttl` and `sweep_interval` govern session-end flushing; `rolling_summary` enables the medium-term digest; and `concurrency` bounds off-path LLM work.

Validation is fail-fast and identical wherever the knobs are accepted: `compaction_target < compaction_trigger <= token_budget`, `hard_event_cap >= 1`, `digest_max_tokens >= 1` when rolling summary is enabled, `idle_ttl > 0`, `sweep_interval > 0`, and `concurrency >= 1`. Defaults should make the recency window cheap and safe while making rolling summary an explicit opt-in. The service may reject a request whose per-agent policy violates these constraints rather than silently normalizing it, because silent normalization makes memory behaviour hard to reason about.

The write and forget failure mode (`soft` swallows long-term scheduling errors and returns a degraded acknowledgement; `strict` surfaces them as an error) is resolved by layering rather than a fixed per-request default. An explicit `failure_mode` on the request wins; otherwise the store-configured `default_failure_mode` applies; otherwise the service falls back to `soft`. This lets an operator set a stricter default for a memory store while still letting an individual agent or request opt into the other behaviour, and keeps the durable short-term append independent of the deferred long-term path in both modes.

### Message-history bridge: full-fidelity replay

The Pydantic AI message-history bridge replays the full interaction, including `ToolCallPart`, `ToolReturnPart`, and delegation parts, so a continuing run sees its own prior tool use rather than a text-only reconstruction. The active short-term window and the latest medium-term digest are assembled into context without fabricating recalled facts as prior turns. This corrects the current behaviour where tool and delegation events are stored but dropped on replay.

```text
# replayed message_history for a continuing run
ModelRequest[UserPromptPart "what's the weather in NYC?"]
ModelResponse[ToolCallPart search(city="NYC")]      # previously dropped, now replayed
ModelRequest[ToolReturnPart search -> "rainy, 12C"]  # previously dropped, now replayed
ModelResponse[TextPart "It's rainy and 12C in NYC."]
```

### Long-term operation set and execution shape

The long-term surface is recall, write/extract, consolidate, and forget. **Recall is synchronous** on the agent hot path and low-latency: a relevance search returning scoped facts plus the relational short-term and medium-term context. **Write/extract, consolidate, and forget are asynchronous** where they involve LLM or engine work, because extraction is LLM-gated and KAOS autonomous loops emit many events ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)). The background execution mechanism and replica topology are [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md) concerns; this record fixes only the synchronous-versus-asynchronous split of the interface.

### Async hybrid service layer

The committed baseline is async FastAPI handlers with the sync Mem0 client isolated behind a **bounded** `run_in_executor` pool. Native async Postgres access is explicitly deferred: the executor boundary keeps LLM-gated Mem0 work from blocking the service, while the initial sync short-term database path is cheap enough to defer the cost of converting the dual SQLite/Postgres backend to native async drivers. `concurrency` is a service and per-policy tuning knob, but the downstream ModelAPI rate limit remains the true throughput ceiling. See also: [Decision 19 in the short-term and medium-term memory design learnings](../impl/learnings/short-term-medium-term-memory-design.md#decision-19-service-concurrency-is-async-hybrid).

### Recall presentation: automatic baseline, additive tools

Enabling memory applies an **automatic baseline** on every run: recalled context is assembled into a **structured memory block** and injected into the system context before the run, and the run's turns are flushed for extraction after it — deterministic, always-on, and cheap. The block contains the latest medium-term digest, the active short-term window, and long-term facts returned by Mem0, clearly labelled by tier so a model does not confuse extracted facts with verbatim conversation. On top of that baseline, **additive memory tools** (a save and a search tool, in the kagent and ADK style) are layered by a single `tools` selector — `read` exposes the search tool, `write` exposes the save tool, `all` exposes both, and unset exposes none — so an agent can deliberately store a finding or query memory mid-run. This replaces the earlier presentation selector: there is no separate automatic-versus-tool mode, because the automatic paths are the meaning of enabling memory and the tools are purely additional. The runtime backend that speaks this contract over the network is `RemoteMemory` (the renamed HTTP client for the KAOS memory service, distinct from any Mem0 client); a storeless agent uses the in-process short-term `LocalMemory` instead. Both the baseline and the optional tools are configurable per agent, surfaced through the control plane in [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md). Recalled facts are not injected as fabricated prior turns in the message history. See also: [the runtime memory API and tooling learnings](../impl/learnings/runtime-memory-api-and-tooling.md).

### Scope injection: server-side, never trusted from the caller

Tenant and agent scope on every memory operation is injected at the `Memory` backend boundary from the authenticated request context and the agent's verifiable identity — the user principal and the AIB `client_id` from [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) — and is never read from caller-supplied or model-supplied arguments. Because Mem0's isolation is application-level filtering with no row-level security ([ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md)), the backend is the enforcement point: a recall or write that cannot resolve a trusted scope fails closed rather than querying an unscoped store. A private-scoped operation in particular resolves its owner from the agent's fully-qualified `kaos://agent/{namespace}/{name}` identity and fails closed on an ambiguous or empty owner, so identity-less agents can never collapse onto one shared private partition (a name-only identifier would additionally collide across namespaces). The full multi-tenancy and grouping model is owned by [ADR 0005](./adr_0005_multi-tenancy-agent-grouping-and-governance.md); this record fixes that scope is a server-side-injected, non-spoofable argument and that short-term/medium-term conversational tiers use only the session-scoped key.

### Observability boundary: ABC method spans with engine sub-spans

OpenTelemetry instrumentation sits at the `Memory` abstraction method boundary, so every backend emits uniform spans (`kaos.memory.recall`, `kaos.memory.write`, `kaos.memory.consolidate`, `kaos.memory.forget`, `kaos.memory.fold`, `kaos.memory.flush`), with engine-specific work (embedding, vector search, extraction, summarization) nested as child spans inside the engine backend. Metrics include recall latency, write latency, fold count, folded tokens, queue depth, executor saturation, idle sweeps, degraded writes, and Mem0 extraction failures. This guarantees uniform coverage regardless of backend while still exposing engine detail where it matters, and follows KAOS's existing `tracer.start_as_current_span("kaos.…")` convention (`pydantic-ai-server/pais/a2a.py`, `server.py`). The instrumentation is emitted by KAOS regardless of Mem0's own telemetry.

## Consequences

- The data plane gains three explicitly named tiers behind one abstraction: a session-only verbatim short-term window, a session-scoped medium-term rolling digest, and a Mem0-backed long-term fact tier.
- Cross-session continuity is deliberately not provided by higher-scope short-term windows; it is provided by long-term facts and future explicitly designed higher-level tiers.
- Writes become cheap append-only operations, with multi-turn batching and lazy-read window computation replacing per-write overflow scans.
- Folding is off the write path and serialized through Postgres locks in external mode, so multiple service replicas can safely process the same store without a single-writer topology or lossy fold behaviour.
- The medium-term digest is auditable and debuggable because it is append-only versioned with retention rather than overwritten in place.
- Mem0 write load drops from potential per-turn extraction to batched per-fold, with deferred session-end flush completing short-session tails later.
- The platform consolidates the short-term and long-term tiers onto one datastore — a shared Postgres in `external` mode or a single-container SQLite-plus-Chroma in `local` mode ([ADR 0004](./adr_0004_deployment-topology-and-control-plane.md)) — and drops the separate Redis memory dependency.
- Continuing and autonomous runs replay full-fidelity history including tool and delegation steps, fixing a real loss in the current bridge.
- Recall is cheap and deterministic by default, with agent-driven memory tools available when wanted; both are per-agent configuration consumed by the control plane.
- Tenant isolation is enforced in the data plane at the backend boundary, not delegated to the engine, and fails closed.
- Memory operations are uniformly observable across backends, with queue-depth and executor metrics available before a durable queue is justified.
- Because alpha allows breaking changes, the existing `Memory` surface, table names, and `MEMORY_*` configuration are replaced; deployments are migrated rather than transparently upgraded.

## Alternatives considered

- **Compose separate short-term, medium-term, and long-term interfaces.** Rejected: one abstraction with tier-specific operations is simpler and matches how the runtime already selects a single backend.
- **Delegate short-term or medium-term memory to Mem0.** Rejected on the embedding-per-turn cost, the absence of a public ordered raw-turn store, the process-local non-replica-safe internal buffer, and the mismatch between Mem0's atomic-fact extraction and a single evolving narrative digest ([KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)).
- **Higher-scope short-term windows.** Rejected: user-level or shared recency buffers would interleave unrelated concurrent sessions and pollute live context; long-term facts handle cross-session continuity.
- **Keep short-term memory on Redis.** Rejected: Postgres is sufficient for conversational write frequency, pgvector already requires Postgres in production, and consolidating to one datastore is operationally simpler ([KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)).
- **Fold synchronously on write.** Rejected: every write would risk waiting on an LLM call, exactly the hot-path cost the tiering model is meant to avoid.
- **Per-turn Mem0 extraction.** Rejected: per-turn writes amplify cost and rate-limit pressure; batched per-fold extraction is the accepted cascade.
- **Singleton in-place summary.** Rejected in favour of append-only versioning because versioning costs little and gives auditability, rollback/debugging evidence, and safer concurrent fold semantics.
- **Maintain the active window on write.** Rejected: per-write overflow scans and trim-to-cap behaviour create unnecessary write amplification and fold thrash; lazy-read compaction marks keep writes cheap and amortise consolidation.
- **Use the engine adapter directly as the concurrency model.** Rejected: KAOS should own a bounded executor rather than hide engine work behind an async-looking API.
- **Preserve the current interface for compatibility.** Rejected: alpha permits breaking changes, and the current event-deque-and-text-only contract is the thing being redesigned.

## Follow-up

- ADR 0004 fixes the Postgres deployment posture, background runner and staged queue mitigations, central-service topology, and high-availability engineering; and surfaces the short-term, medium-term, deferred sweep, and concurrency knobs as control-plane configuration.
- ADR 0005 fixes the full multi-tenancy, scope-hierarchy, and agent-grouping model that the server-side scope injection enforces, including the fact that short-term and medium-term tiers remain session-scoped while long-term scope can be private, user, or shared.
- A native-async Mem0 upstream contribution and native async Postgres access are tracked outside the initial service cut; KAOS's committed baseline is async request handling plus a bounded Mem0 executor.
